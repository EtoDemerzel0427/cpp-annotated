---
title: Trivial relocation (P2786 and P1144)
summary: When moving an object to new memory, can a single memcpy replace a move construction plus destruction? The library practice of twenty years, where the two competing proposals disagreed on assignment semantics, explicit declarations and whether memcpy is enough, how P2786 entered C++26 and was then removed, and what libc++ already does today when growing a vector.
tags: proposal, trivial relocation, move semantics, object model, vector, C++26
group: C++26
updated: 2026-10-19
---

!!! tldr
    - Relocation means moving an object to a new address: move-construct it at the new location, then destroy the old object. For types like `std::unique_ptr`, these two steps together amount to copying the bytes and forgetting the source object; this is called trivial relocation.
    - Libraries such as Folly, BSL, Qt and Abseil have long done this with their own type traits plus `memcpy`, but under the standard's object model, moving objects that are not trivially copyable this way is undefined behavior.
    - P1144 wants a single property: trivially relocatable means `memcpy`-able, and it requires a type's assignment to be consistent with destroy-then-construct. P2786 splits it into two properties, trivially relocatable and replaceable, declared with contextual keywords such as `trivially_relocatable_if_eligible`, and allows polymorphic types to have their vptr fixed up after the move.
    - P2786 was merged into the C++26 working draft in early 2025, and removed entirely the same year while resolving national body comments (P3920R0). There is no trivial relocation in [class.prop], [obj.lifetime] or `<type_traits>` in the current draft.
    - libc++ internally uses `__libcpp_is_trivially_relocatable` to turn `vector` growth into a single `memcpy`. In our measurements, one growth of a `vector<unique_ptr<int>>` is about 4 times faster than for a type with the same layout that is not trivially relocatable.

## One move and one destruction per element when growing

When a `std::vector` runs out of capacity, it allocates a larger block of memory, moves the old elements over, and frees the old memory. `reserve` only requires the elements to be move-insertable ([[vector.capacity#3]]), and implementations do two steps for each element: move-construct an element in the new memory, then destroy the old element.

```cpp title="grow-count.cpp" run ok
#include <cstdio>
#include <memory>
#include <vector>

int moves = 0, dtors = 0;

struct Box {
  std::unique_ptr<int> p;
  explicit Box(int i) : p(new int(i)) {}
  Box(Box&& o) noexcept : p(std::move(o.p)) { ++moves; }
  ~Box() { ++dtors; }
};

int main() {
  std::vector<Box> v;
  v.reserve(4);
  for (int i = 0; i < 4; ++i) v.emplace_back(i);
  moves = dtors = 0;
  v.reserve(8);              // reallocates, moving 4 elements
  std::printf("moves=%d dtors=%d\n", moves, dtors);
}
```

Clang 23 (libc++) prints `moves=4 dtors=4`. Each move nulls out the source object's pointer, for the sole purpose of making the destructor that immediately follows do nothing. The net effect of the two steps is just that the new location gets the old location's bytes, and the old object is gone.

Moving an object from one address to another, with the source object's lifetime ending as a result, is called **relocation**. If, for some type, relocation is equivalent to copying the object's bytes and no longer caring about the source (not calling its destructor), the type is said to be **trivially relocatable**. `std::unique_ptr`, `std::shared_ptr` and most `std::vector` implementations are like this; for them, growth could be one block `memcpy`.

Why `vector` only moves when the move constructor doesn't throw, and otherwise falls back to copying, is covered in [[topics/special-members-and-elision]]. Trivial relocation solves that problem along the way: `memcpy` doesn't throw.

## The `memcpy` the standard can't express

### What libraries do

Many libraries give types a trait of their own and choose `memcpy` based on it. [[P3559R0]] lists their names: Folly's `folly::IsRelocatable`, BSL's `bslmf::IsBitwiseMoveable`, Qt's `Q_IS_RELOCATABLE`, Abseil's `absl::is_trivially_relocatable`, and so on. The code looks roughly like this:

```cpp title="lib-relocate.cpp" run ub
#include <cstring>
#include <memory>
#include <new>
#include <type_traits>

template<class T>
struct is_relocatable : std::is_trivially_copyable<T> {};
template<class T>
struct is_relocatable<std::unique_ptr<T>> : std::true_type {};

template<class T>
void relocate_n(T* from, std::size_t n, T* to) {
  if constexpr (is_relocatable<T>::value) {
    std::memcpy(static_cast<void*>(to), from, n * sizeof(T));
  } else {
    for (std::size_t i = 0; i < n; ++i) {
      ::new (static_cast<void*>(to + i)) T(std::move(from[i]));
      from[i].~T();
    }
  }
}

int main() {
  using P = std::unique_ptr<int>;
  alignas(P) unsigned char a[sizeof(P)], b[sizeof(P)];
  ::new (static_cast<void*>(a)) P(new int(1));
  relocate_n(std::launder(reinterpret_cast<P*>(a)), 1,
             reinterpret_cast<P*>(b));
  P* q = std::launder(reinterpret_cast<P*>(b));
  int r = **q - 1;           // UB: there is no unique_ptr object in b
  q->~P();
  return r;
}
```

This program returns 0 as expected, and ASan and UBSan report nothing, but by the standard its behavior is undefined. The problem is not the source object: [[basic.life#6]] allows an object's lifetime to end without calling its destructor, as long as its storage is reused or released. The problem is the destination.

[[basic.types.trivial#3]] and [[basic.types.trivial#4]] only guarantee that copying bytes copies the value for trivially copyable types; `memcpy` can implicitly create objects ([[intro.object#13]]), but only objects of implicit-lifetime types, and `unique_ptr` has a user-provided destructor, so it is neither. So after the `memcpy`, there is no `unique_ptr` object in `b`, and `*q` accesses an object that does not exist. Library authors rely on compilers not exploiting this.

### Types that can't be trivially relocated

Not every type can be moved this way. If an object stores a pointer to itself, then after copying the bytes, the pointer in the new object still points to the old address. libstdc++'s `std::string` is like this: short strings are stored in a buffer inside the object, and the data pointer points to that buffer.

```cpp title="self-pointer.cpp" run ub
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>

struct SsoStr {                      // mimics libstdc++'s layout
  char* p;                           // for short strings, points to its own buf
  char buf[16];
  explicit SsoStr(const char* s) : p(buf) { std::strcpy(buf, s); }
  SsoStr(SsoStr&& o) noexcept : p(buf) { std::strcpy(buf, o.p); }
  ~SsoStr() {}
};

int main() {
  void* from = std::malloc(sizeof(SsoStr));
  void* to   = std::malloc(sizeof(SsoStr));
  auto* s = new (from) SsoStr("hi");
  std::memcpy(to, s, sizeof(SsoStr));   // pretend to trivially relocate
  std::free(from);                      // the source is discarded without being destroyed
  auto* t = static_cast<SsoStr*>(to);   // (t doesn't even point to an object)
  std::puts(t->p);                      // t->p still points to the old buf
  std::free(to);
}
```

Running with `-fsanitize=address`, ASan reports heap-use-after-free at `puts`. The move constructor re-points `p` at its own `buf`; copying bytes doesn't. Others of the same kind include `std::list` implementations that keep the sentinel node inside the object (the first and last nodes point back to the container object), and types that register their own address in an external registry. libc++'s `std::string` uses a flag bit to distinguish long and short strings and stores no self-pointer, so it can be trivially relocated.

So trivial relocatability cannot be inferred automatically by the compiler for all types: when the user writes a move constructor and a destructor, the compiler can't tell whether the two together amount to copying bytes. What is needed is a rule that infers it for simple types, plus a way for authors to declare it.

## The two proposals

### P1144: relocation is move plus destroy, and trivial means `memcpy`

[[P1144R12]] defines the **relocation operation** as a move construction immediately followed by destruction of the source, performed by a new function `std::relocate_at(source, dest)`; if the type is trivially relocatable, the operation is equivalent to copying bytes. Its rules have three parts:

1. Implicit inference. A class is trivially relocatable if none of its eligible copy and move constructors, copy and move assignment operators or destructor is user-provided, it has no virtual functions or virtual bases, and all its members and bases are trivially relocatable. All trivially copyable types are included.
2. Explicit declaration. The `[[trivially_relocatable]]` attribute is written on the class definition, optionally with a `bool` constant expression as a condition. It is an unchecked knife: even if some member is not itself trivially relocatable, the attribute makes the whole class trivially relocatable, and if the declaration is wrong, programs relying on it have undefined behavior.
3. A semantic requirement. The new concept `std::relocatable` requires that if the type is assignable, assignment must have the same effect as destroying and then constructing in place. This requirement lets `vector::insert` and `vector::erase` move bytes as well.

The attribute's wording states the semantics directly:

!!! note "P1144R12 [dcl.attr.trivreloc]"
    "specifies that a class type's relocation operation has no visible side-effects other than a copy of the underlying bytes, as if by the library function `std::memcpy`."

### P2786: two independent properties

[[P2786R13]] also starts from move plus destroy, but splits the problem into two independent properties:

- Trivially relocatable: move construction plus destruction is equivalent to the effect of the library function `std::trivially_relocate`. Note that it does not say equivalent to `memcpy`.
- **Replaceable**: move-assigning an object of this type is equivalent to destroying it and then move-constructing it from the same xvalue.

Both have an implicit rule and an explicit declaration. The implicit rule requires the class to be default-movable: the functions selected for move construction and move assignment, and the destructor, are neither user-provided nor deleted. Explicit declarations use two contextual keywords, written after the class name in the same position as `final`:

<div class="compare" markdown="1">

```cpp title="P1144's syntax"
struct [[trivially_relocatable]] Buf {
  Buf(Buf&&);
  Buf& operator=(Buf&&);
  ~Buf();
};
```

```cpp title="P2786's syntax"
struct Buf trivially_relocatable_if_eligible
           replaceable_if_eligible {
  Buf(Buf&&);
  Buf& operator=(Buf&&);
  ~Buf();
};
```

</div>

Neither snippet carries a verdict: the current draft has neither the attribute nor the two keywords. Clang 23 treats the right snippet as a variable declaration and reports an error, and only gives an unknown-attribute warning for the left one.

`if_eligible` means the keyword takes effect only if the class is eligible in the first place. Eligibility requires no virtual bases and that all bases and non-static data members are trivially relocatable (similarly for replaceability). If a member is not eligible, the keyword is silently ignored, and the class is not trivially relocatable after all.

P2786 also provides the library function `std::trivially_relocate(first, last, result)`. It is the only sanctioned means of trivial relocation: it ends the lifetime of the source objects and begins the lifetime of the destination objects, without calling any constructor or destructor. Users calling `memcpy` themselves is still not allowed. Another function, `std::relocate`, calls it for trivially relocatable types and moves-then-destroys one by one for other types.

P2786 uses a table to show why the two properties are independent (`string1` means a `std::string` implementation that stores a self-pointer, `string2` one that doesn't; `list1` and `list2` similarly mean `std::list` with the sentinel node inside the object and on the heap):

| | Not replaceable | Replaceable |
|---|---|---|
| Not trivially relocatable | `pmr::list1<T>`, `tuple<pmr::string1>` | `list1<T>`, `string1` |
| Trivially relocatable | `tuple<T&>`, `pmr::vector<T>`, `pmr::list2<T>` | `shared_ptr<T>`, `vector<T>`, `string2`, `list2<T>` |

## Where they disagree

### Does assignment count

The specification of `vector::erase` is written in terms of assignment: each element after the erased one is moved to the previous position by the assignment operator, and then the last one is destroyed ([[vector.modifiers#6]]). For `unique_ptr`, using `memmove` to shift the following elements forward gives exactly the same result; for some other types it doesn't.

```cpp title="erase-assigns.cpp" run ok
#include <cstdio>
#include <tuple>
#include <vector>

int main() {
  int a = 1, b = 2, c = 3;
  std::vector<std::tuple<int&>> v{{a}, {b}, {c}};
  v.erase(v.begin());          // v[0] = std::move(v[1]); ...
  std::printf("a=%d b=%d c=%d  v: %d %d\n",
              a, b, c, std::get<0>(v[0]), std::get<0>(v[1]));
  std::get<0>(v[0]) = 100;
  std::printf("a=%d b=%d\n", a, b);
}
```

It prints `a=2 b=3 c=3  v: 2 3` and `a=100 b=3`. Assignment of `tuple<int&>` writes through to the referenced variable, so `erase` rewrites `a` and `b`, and `v[0]` still refers to `a`. If `erase` moved bytes instead, `a`, `b` and `c` would all be unchanged, and `v[0]` would refer to `b`.

Allocator-aware types are the same. `std::pmr::polymorphic_allocator` does not propagate on assignment (its copy assignment is deleted, [[mem.poly.allocator.class]]), so after assignment the target keeps its own memory resource:

```cpp title="pmr-erase.cpp" run ok
#include <cstdio>
#include <memory_resource>
#include <string>
#include <vector>

int main() {
  std::pmr::monotonic_buffer_resource r1, r2;
  std::vector<std::pmr::string> v;
  v.emplace_back("first, a fairly long string", &r1);
  v.emplace_back("second, a fairly long string", &r2);
  v.erase(v.begin());            // v[0] = std::move(v[1])
  std::printf("v[0] uses r1? %d  r2? %d\n",
              v[0].get_allocator().resource() == &r1,
              v[0].get_allocator().resource() == &r2);
}
```

It prints `v[0] uses r1? 1  r2? 0`. Moving bytes would make `v[0]` take `r2` with it.

For both types, move construction plus destruction still amounts to copying bytes: the new object refers to the same variable, uses the same resource. So they can be `memcpy`d when growing, but not when erasing. This is where the two proposals part ways:

- P1144 considers one trait sufficient, corresponding to the property library authors actually care about: any move can be replaced by copying bytes. The cost is that `tuple<int&>` and classes containing `pmr` containers don't count as trivially relocatable, and don't get `memcpy` even when growing.
- P2786 considers that the two things should be separate: growing only needs trivial relocatability, while `erase` and `swap` also need replaceability. So a `pmr::vector` can be `memcpy`d when growing; but a library that wants to optimize `erase` has to check both traits.

[[P3233R0]], addressing an early version of P2786, pointed out that the model at the time couldn't distinguish `tuple<int&>` from `unique_ptr`, so operations like `erase` couldn't be optimized; later revisions of P2786 added the replaceable property in response. [[P3559R0]], on the other hand, argues that third-party libraries already use the name `is_trivially_relocatable` with P1144's meaning, and if the standard uses the same name for a weaker property, those libraries will wrongly hand types that only satisfy P2786 to `memswap` and `memmove`.

### Inference or declaration, and whether a declaration is a knife or a switch

The implicit rules of the two proposals differ little; both require the special member functions not to be user-provided. The difference is in explicit declarations:

- P1144's attribute overrides. [[P1144R13]] gives an example: a container with a member like `offset_ptr` that stores a relative address; the member itself can't be trivially relocated, but the whole container can, and the author just declares it with the attribute. P2786's `if_eligible` can't do this.
- P2786's keywords only take effect when eligible, with the benefit that a change in a member's implementation can't silently introduce undefined behavior. P2786's reasoning: the same `std::list` may or may not be trivially relocatable in different standard libraries, and a class with a `std::list` member that adds the keyword is well-formed on both implementations, just with different results. [[P3236R1]] argues conversely that this forces every layer of member types to be marked first, so the marking cascades all the way down.
- Attributes can be supported by implementations in older language modes; contextual keywords can only be used with the new standard, and they change the meaning of existing code. P2786 added an Annex C entry for this: `struct C {}; struct C replaceable_if_eligible {};` declares a variable named `replaceable_if_eligible` in C++23, but redefines `C` in C++26.

### Is `memcpy` enough

P2786's `trivially_relocate` specifies that the destination object's object representation is the same as the source's, with one exception:

!!! note "P2786R13's [obj.lifetime] wording at the time"
    "except for any parts of the object representations used by the implementation to represent type information"

This exception is for platforms like arm64e, where pointer authentication signs the vptr together with its own storage address; when the object changes address, the vptr must be re-signed, and simply copying bytes gives an invalid vptr. P2786 therefore allows polymorphic types to be trivially relocatable, with `trivially_relocate` responsible for the fix-up; whether unions with polymorphic members are trivially relocatable is implementation-defined, because the compiler doesn't know which member is active.

The author of P1144 and several national body comments argued that trivially relocatable must mean `memcpy`-able and `realloc`-able, otherwise it is useless to libraries like Qt that grow with `realloc`; therefore polymorphic types should not count as trivially relocatable. [[P4197R0]] lists this as one of the questions C++29 must answer first, and points out a related problem: type-erasing wrappers that store objects in a byte buffer (such as `std::function` with small-object optimization) don't know, when copying bytes, that the object in the buffer needs fixing up.

### Common types under the three positions

| Type | P1144R12 | P2786R13 trivially relocatable | P2786R13 replaceable | libc++ internal trait (tested) |
|---|---|---|---|---|
| `unique_ptr<int>`, `shared_ptr<int>` | Declared by the library | Declared by the library | Declared by the library | Yes |
| `tuple<int&>` | No (assignment writes through the reference) | Yes | No | No |
| `pmr::string` (implementation without self-pointer) | No | Can be | No | Yes |
| `string` with a self-pointer, `list` with an internal sentinel | No | No | Yes | `list<int>`: no |
| `struct A { const int i; };` | Yes | No (see CWG3049 below) | No | Yes |
| `struct W { virtual void f(); };` | No | Yes | Yes | No |

The P1144 and P2786 columns come from their respective wording and examples. Both proposals leave it to implementations whether standard library types are trivially relocatable, hence the first row's "declared by the library". The last column is the measured value of libc++'s internal trait, described below.

## Into C++26, and out again

P2786R13 was merged into the C++26 working draft in early 2025, bringing definitions in [class.prop] such as default-movable, eligible for trivial relocation, trivially relocatable class and replaceable class; `is_trivially_relocatable`, `is_replaceable` and `is_nothrow_relocatable` in `<type_traits>`; `trivially_relocate` and `relocate` in `<memory>`; and the feature-test macros `__cpp_trivial_relocatability` and `__cpp_lib_trivially_relocatable`.

Among the national body comments on the C++26 committee draft was a group targeting trivial relocation. [[P3915R0]] sorts them into several categories, including: remove the `*_if_eligible` keywords; make trivial relocation equivalent to `memcpy`; replace `std::relocate` with algorithms such as [[P3516R2]]'s `uninitialized_relocate`; allow `const` types; and a wording defect, [[CWG3049]].

CWG3049 shows a hole in the implicit rule. Default-movable requires that the function selected for move assignment is not deleted, while `const` members and reference members cause the assignment operator to be implicitly deleted:

```cpp
struct A { const int i; };  // trivially copyable, but not trivially relocatable per P2786R13
struct B { int& r; };       // same
```

This contradicts P2786's own design statement (that trivially copyable types are all trivially relocatable).

The committee finally removed the whole feature from C++26 by consensus, hoping to resolve these issues in C++29. [[P3920R0]] is the removal wording. It is essentially the inverse of P2786R13, but keeps a few improvements P2786 made along the way, such as the grammar of *class-property-specifier* in [class.pre] and the first paragraph of [library.class.props].

### What the current draft says

There is no trace of trivial relocation in the current draft:

- [[class.prop]] only defines trivially copyable classes (¶1), standard-layout classes (¶2) and implicit-lifetime classes (¶8); there is no trivially relocatable or replaceable.
- The identifiers with special meaning in Table 4 of [[lex.name]] are `final`, `import`, `module`, `override`, `post` and `pre`, without the two `_if_eligible`s.
- [[class.pre]] keeps the grammar name *class-property-specifier*, but its only alternative is `final`, and ¶5 only discusses `final`.
- [[library.class.props]] has just one paragraph: whether standard library classes are trivially copyable, standard-layout or implicit-lifetime is unspecified unless stated otherwise.
- [[obj.lifetime]] has only `start_lifetime_as` and `start_lifetime_as_array`; [[meta.unary.prop]] has no `is_trivially_relocatable`; `<version>` has no `__cpp_lib_trivially_relocatable`.

Since the feature never appeared in a published standard, there are no related entries in Annex C either.

[[P4197R0]] lists the design questions C++29 must first agree on: whether trivial relocation is copying bytes or a dedicated abstract machine operation, whether non-bitwise relocation is allowed, whether constant evaluation is supported, whether users opt in through traits, keywords or by leaving it to the compiler, and whether non-trivial relocation and full library support must be provided at the same time. The long line from C++11 move semantics to this attempt is in [[history/move-semantics]].

## What libc++ already does

The standard doesn't provide this property, but standard library implementers can rely on compiler behavior inside the implementation. libc++ has an internal trait `std::__libcpp_is_trivially_relocatable<T>`: by default it equals `is_trivially_copyable<T>`; if the type declares a member alias `__trivially_relocatable` that is the type itself, the trait is true.

`unique_ptr`, `shared_ptr`, `weak_ptr`, `basic_string`, `vector`, `deque`, `array`, `pair`, `tuple`, `optional`, `variant`, `expected`, `locale` and others all declare this alias, most with conditions depending on member types. Comments explain why; for example, `basic_string` only uses a flag bit to distinguish long and short strings and stores no pointer to itself. Checked results: true for `unique_ptr<int>`, `string`, `pmr::string`, `pmr::vector<int>` and `tuple<string>`; false for `tuple<int&>`, `function<void()>` and `list<int>`.

There is only one place where this trait is actually used to choose an algorithm: the internal function `__uninitialized_allocator_relocate`, called when `vector` (and the `__split_buffer` it relies on) reallocates. When all the following conditions hold, it calls `__builtin_memcpy` directly; otherwise it move-constructs and destroys one by one:

- the element type satisfies `__libcpp_is_trivially_relocatable`;
- the allocator has no custom `construct` and `destroy` (`std::allocator` qualifies);
- it is not in constant evaluation.

`erase` and `insert` that doesn't need to reallocate still move elements with assignment. So what libc++ actually adopts is P2786-style trivial relocatability (true for `pmr::string` too), used only when growing, which involves no assignment, sidestepping the replaceability question.

The effect of the allocator condition can be seen in assembly: at `-O2`, `reserve` on `std::vector<std::pmr::string>` calls `memcpy`, while `reserve` on `std::pmr::vector<std::pmr::string>` constructs elements one by one, because `polymorphic_allocator` has its own `construct` (it does [[g:uses-allocator-construction|uses-allocator construction]]).

### Count, then measure

Hook the `Box` from the beginning into libc++'s hook, and growth no longer calls the move constructor or destructor:

```cpp title="hooked.cpp" run ifndr
#include <cstdio>
#include <memory>
#include <type_traits>
#include <vector>

int moves = 0, dtors = 0;

template<bool Hook>
struct Box {
  std::unique_ptr<int> p;
  explicit Box(int i) : p(new int(i)) {}
  Box(Box&& o) noexcept : p(std::move(o.p)) { ++moves; }
  ~Box() { ++dtors; }
  // libc++'s internal hook: declares that move plus destroy is equivalent to memcpy
  using __trivially_relocatable =
      std::conditional_t<Hook, Box, void>;
};

template<class T>
void grow(const char* name) {
  std::vector<T> v;
  v.reserve(4);
  for (int i = 0; i < 4; ++i) v.emplace_back(i);
  moves = dtors = 0;
  v.reserve(8);
  std::printf("%-8s moves=%d dtors=%d  *v[3]=%d\n",
              name, moves, dtors, *v[3].p);
}

int main() {
  grow<Box<false>>("plain");
  grow<Box<true>>("hooked");
}
```

It prints `plain moves=4 dtors=4  *v[3]=3` and `hooked moves=0 dtors=0  *v[3]=3`, with no reports from ASan or UBSan. The verdict is IFNDR because identifiers containing a double underscore are reserved for the implementation ([[lex.name#4]]), and user programs should not declare them; it is used here only to observe libc++'s behavior, so don't do this in your code. It also illustrates the risk of P1144's attribute knife: the library trusts this declaration completely, and `Box`'s counting side effects simply vanish.

Next, compare `std::unique_ptr<int>` with a type of the same layout and semantics that has an empty destructor written out and is therefore not trivially relocatable:

```cpp title="reserve-bench.cpp" run ok
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <memory>
#include <vector>

struct Plain {                       // same size and semantics as unique_ptr
  std::unique_ptr<int> p;
  Plain() = default;
  Plain(Plain&&) noexcept = default;
  ~Plain() {}                        // user-provided: no longer trivially copyable
};

template<class T>
double reserve_ns_per_elem(std::size_t n) {
  std::vector<double> t;
  for (int s = 0; s < 31; ++s) {
    std::vector<T> v(n);
    auto a = std::chrono::steady_clock::now();
    v.reserve(2 * n);                // one reallocation
    auto b = std::chrono::steady_clock::now();
    asm volatile("" : : "r"(v.data()) : "memory");
    t.push_back(std::chrono::duration<double, std::nano>(b - a).count() / n);
  }
  std::nth_element(t.begin(), t.begin() + 15, t.end());
  return t[15];
}

int main() {
  for (std::size_t n : {1u << 10, 1u << 16, 1u << 22}) {
    double u = reserve_ns_per_elem<std::unique_ptr<int>>(n);
    double p = reserve_ns_per_elem<Plain>(n);
    std::printf("n=%-8zu unique_ptr %.3f  Plain %.3f ns/elem\n", n, u, p);
  }
}
```

Five runs on an Apple M2 Pro (`-O2`), each taking the median of 31 samples:

| Elements | `unique_ptr<int>` | `Plain` | Ratio |
|---|---|---|---|
| 1 024 | 0.16 – 0.33 ns/element | 0.57 – 1.02 ns/element | 3.1 – 3.7 |
| 65 536 | 0.14 – 0.28 ns/element | 0.62 – 1.10 ns/element | 3.9 – 4.8 |
| 4 194 304 | 0.17 – 0.26 ns/element | 0.69 – 0.97 ns/element | 3.8 – 4.1 |

The machine was under heavy load during measurement (load average between 29 and 118), so the absolute numbers are high and noisy, but the ratios are fairly stable. The times include allocating the new buffer. In the `-O2` assembly, the `unique_ptr` version of `reserve` has just one `bl _memcpy` after `operator new`; the `Plain` version is a loop that, for each element, reads the pointer, writes it to the new location and zeroes the source, followed by a second loop that checks each pointer for null and decides whether to call `operator delete`. The cost of allocation itself is covered in [[perf/allocation]].

## Compiler support

The status of Clang 23.1.3 / libc++ matches the current draft:

- `trivially_relocatable_if_eligible` and `replaceable_if_eligible` are not recognized as keywords;
- `std::is_trivially_relocatable_v` and `std::trivially_relocate` don't exist, and `<version>` does not define `__cpp_lib_trivially_relocatable`.

But Clang keeps some things at the implementation level. The builtins `__builtin_is_cpp_trivially_relocatable(T)` and `__builtin_trivially_relocate` are still available, the former computed by P2786R13's rules: in our tests, a class with only virtual functions gives true, `struct A { const int i; }` gives false (exactly the CWG3049 case), and `unique_ptr<int>` gives false (the keyword that marked it is gone). The predefined macro `__cpp_trivial_relocatability` is still defined as `202502L`, even under `-std=c++17`. The older `__is_trivially_relocatable` has been marked deprecated. GCC and MSVC were not tested.

## Questions

!!! question "1. Why libc++ dares to `memcpy` a `pmr::string`"
    The text above says `pmr::string` is not replaceable, so `erase` can't move it as bytes. Yet libc++ makes `__libcpp_is_trivially_relocatable<pmr::string>` true. Can this go wrong?

<details markdown="1">
<summary>Answer</summary>

No. libc++ only uses this trait when reallocating: the destination is uninitialized new memory, the source objects are discarded afterwards, and the operation the standard requires is move construction plus destruction, with no assignment involved. Moving a `pmr::string` takes the source object's memory resource along with it, and copying bytes has the same effect. `erase` involves assignment, and libc++ doesn't use the trait there, so the assignments [[vector.modifiers#6]] requires happen as usual. This is exactly why P2786 distinguishes trivially relocatable from replaceable.

</details>

!!! question "2. A class with a `const` member"
    Is `struct A { const int i; };` trivially copyable? Is it trivially relocatable under P1144R12 and under P2786R13?

<details markdown="1">
<summary>Answer</summary>

It is trivially copyable: the copy and move constructors are trivial, the copy and move assignment operators are deleted and therefore not eligible, and the destructor is trivial, satisfying [[class.prop#1]]. P1144R12 counts every trivially copyable type as trivially relocatable. P2786R13's default-movable requires the function selected for move assignment not to be deleted, so `A` is not trivially relocatable, even though P2786 itself says `const` members don't prevent trivial relocation. This contradiction is [[CWG3049]], and the authors of P2786 suggested in [[P3915R0]] changing the condition to not explicitly deleted. Clang 23's `__builtin_is_cpp_trivially_relocatable(A)` is false, consistent with the original wording of P2786R13.

</details>
