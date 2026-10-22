---
title: Requirements on types and expressions
summary: "The Cpp17 named requirements the standard library places on user types: comparison (equivalence relations, strict weak ordering), construction and assignment, non-throwing destruction; swappability and the two-step swap; Cpp17NullablePointer; Cpp17Hash; Cpp17Allocator and the defaults allocator_traits provides, and the allocator completeness requirements that let vector be instantiated with an incomplete type."
updated: 2026-10-19
---

!!! tldr
    - The Cpp17 named requirements (*Cpp17CopyConstructible*, *Cpp17Hash* and so on) are written in prose, and the compiler doesn't check their semantics. If a type doesn't meet them, the program has undefined behavior.
    - A comparator must be a strict weak ordering. Writing `<` as `<=` can make `std::sort` read and write out of bounds, and the compiler won't complain.
    - A moved-from object's state is unspecified, but it must still meet the library's requirements, self-move-assignment included; destructors must not throw exceptions.
    - Swapping happens in the two-step context: the candidate set includes `std::swap` and any `swap` found by ADL. In generic code, use `using std::swap; swap(a, b);` or `std::ranges::swap`.
    - A custom allocator only needs to provide `value_type`, `allocate`, `deallocate`, a converting constructor and `==`; `allocator_traits` fills in defaults for the other members.

When you hand your own type to the standard library, for example putting it in a container, passing it to an algorithm, or using it as a hash function or allocator, the library places requirements on that type. Newer components since C++20 mostly express these requirements with concepts (`std::regular`, `std::sortable`…), but many components, such as the containers, the classic algorithms, `unique_ptr` and the unordered containers, are still described with the **Cpp17 named requirements** ([[g:cpp17-named-requirement]]) defined in this subclause.

The difference is in checking. The syntactic part of a concept is checked by the compiler; Cpp17 requirements are pure prose, and when they aren't met the compiler mostly won't report an error; the consequence is undefined behavior ([[res.on.functions#2.3]]).

## Notation in these tables ([utility.arg.requirements] ¶1)

¶1 The requirements in this subclause are all given as tables: one column of expressions, one of return types, and one of semantic requirements or postconditions. The letters in the tables have fixed meanings:

| Notation | Meaning |
|---|---|
| `T` | An object or reference type supplied by the program to instantiate a library template |
| `a`, `b`, `c` | Values of type `T` or `const T` |
| `s`, `t` | Modifiable lvalues of type `T` |
| `u` | The name of a variable being declared |
| `rv` | An rvalue of type `T` |
| `v` | An lvalue of type `T` or `const T`, or an rvalue of type `const T` |

The tables only require the expressions to be valid and have the specified semantics; they don't say how they are implemented. For example, `==` may be a member or a non-member ([[structure.requirements#3]]).

## Comparison: equivalence relations and strict weak ordering (Tables 28, 29)

```cpp ub
#include <algorithm>
#include <vector>
int main() {
  std::vector<int> v(100, 1);
  std::sort(v.begin(), v.end(), [](int a, int b) { return a <= b; });
  // UB: <= is not a strict weak ordering (a <= a is true)
}
```

This isn't just a theoretical problem. Quicksort's partition loop relies on the comparison result to stop scanning, and `<=` can make the scan run past the end of the array. Compiled with libc++ and `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` (Clang 23), the program reports "Would read out of bounds, does your comparator satisfy the strict-weak ordering requirement?" and terminates.

| Requirement | Expression | Semantics |
|---|---|---|
| *Cpp17EqualityComparable* | `a == b` | `==` is an **equivalence relation**: reflexive (`a == a`), symmetric, transitive |
| *Cpp17LessThanComparable* | `a < b` | `<` is a strict weak ordering ([[alg.sorting]]) |

Both return types must model *boolean-testable* ([[g:boolean-testable]]): the result is convertible to `bool`, and applying `!` to it also yields something convertible to `bool`. This rules out types whose `!` or `&&` is overloaded to behave strangely.

A **strict weak ordering** ([[g:strict-weak-ordering]]) is the foundation of sorting and of the ordered associative containers. It requires `<` to be irreflexive (`!(a < a)`) and transitive, and incomparability (`!(a < b) && !(b < a)`) to be an equivalence relation. Common violations: using `<=` as the comparator; comparing floating-point numbers that include NaN; getting the logic wrong when comparing by several fields, such as `a.x < b.x || a.y < b.y`.

!!! lawyer "Does double meet these requirements?"
    NaN makes `double`'s `==` not reflexive, and `<` isn't a strict weak ordering either, so taken literally the type `double` doesn't meet Tables 28 and 29. The usual reading is that the requirements apply to the values actually involved: sorting a range without NaN is well-defined, and with NaN it is UB. On the concepts side, [[structure.requirements#8]] states explicitly that required operations need not be total functions, putting this into normative wording.

## Construction, assignment and destruction (Tables 30–35)

| Requirement | Expression | Postcondition |
|---|---|---|
| *Cpp17DefaultConstructible* (Table 30) | `T t;` | `t` is default-initialized |
| | `T u{};`, `T()`, `T{}` | Value-initialized or aggregate-initialized |
| *Cpp17MoveConstructible* (Table 31) | `T u = rv;`, `T(rv)` | The result equals the value of `rv` before the construction; `rv`'s state is unspecified |
| *Cpp17CopyConstructible* (Table 32) | `T u = v;`, `T(v)` | The result equals `v`; `v` is unchanged |
| *Cpp17MoveAssignable* (Table 33) | `t = rv`, returns `T&`, which is `t` | If `t` and `rv` don't refer to the same object, `t` equals the value of `rv` before the assignment; `rv`'s state is unspecified |
| *Cpp17CopyAssignable* (Table 34) | `t = v`, returns `T&`, which is `t` | `t` equals `v`; `v` is unchanged |
| *Cpp17Destructible* (Table 35) | `a.~T()` | No exception is propagated |

Tables 32 and 34 are in addition to Tables 31 and 33, so *Cpp17CopyConstructible* includes *Cpp17MoveConstructible*.

### Requirements are on expressions, not member functions

```cpp error
#include <vector>
struct M {
  M() = default;
  M(const M&) = default;
  M(M&&) = delete;   // move constructor explicitly deleted
};
int main() {
  std::vector<M> v;
  M m;
  v.push_back(m);   // error: growing requires constructing M from an rvalue
}
```

Table 31 requires `T u = rv;` to be valid; it doesn't require `T` to have a move constructor. A type with only a copy constructor meets it too, because an rvalue can bind to `const T&`.

Conversely, the type `M`, with its move constructor explicitly deleted, meets neither requirement. A deleted function still participates in overload resolution, so `M u = rv;` selects it and is ill-formed. libc++ (with Clang 23) reports "The specified type does not meet the requirements of Cpp17MoveInsertable". So if you don't want move semantics, don't declare a move constructor rather than deleting it; when it isn't declared, rvalues fall back to the copy constructor.

### The compiler doesn't check the semantic part

"Equals" is a semantic requirement: after a copy the two objects are equal. C++98's `std::auto_ptr` quietly transferred ownership on copy; it met Table 32 syntactically but not semantically, and putting it in a container was UB. This is the root reason `auto_ptr` was deprecated and eventually removed.

### Moved-from objects (the notes to Tables 31, 33)

Note 1 to Table 31 and Note 2 to Table 33 say that although `rv`'s state after being moved from is unspecified, it must still meet the requirements of the library component that uses it, and the operations listed in those requirements must work as specified. Containers and algorithms assign to and destroy moved-from objects, and sometimes compare them.

Note 2 also specifically says "whether or not `t` and `rv` refer to the same object". This settles the requirement for self-move-assignment `x = std::move(x)`: the value of `x` can be anything (the value postcondition only holds when the two differ), but `x` must still be a usable object. The behavior of standard library types themselves is in [[lib.types.movedfrom#2]].

### Destruction must not throw

Table 35 requires that no exception propagates from destruction, consistent with [[res.on.functions#2.4]]: a container element whose destructor throws is UB. Since C++11 destructors are `noexcept` by default ([[except.spec]]), so only an explicit `noexcept(false)` runs into this rule. Note 3 adds that array types and non-object types don't meet *Cpp17Destructible*.

## Swappable [swappable.requirements]

```cpp run ok
#include <string>
#include <type_traits>
#include <utility>
namespace lib {
  struct Widget { std::string name; };
  void swap(Widget& a, Widget& b) noexcept { a.name.swap(b.name); }
}
static_assert(std::is_nothrow_swappable_v<lib::Widget>);
int main() {
  lib::Widget a{"a"}, b{"b"};
  std::swap(a, b);          // qualified call: bypasses lib::swap, does three moves
  using std::swap;
  swap(a, b);               // two-step: ADL finds lib::swap
  std::ranges::swap(a, b);  // C++20: does the two-step for you internally
  return a.name == "b" ? 0 : 1;
}
```

¶1 Let `t` be an expression of type `T` and `u` an expression of type `U`.

¶2 An object `t` is **swappable with** `u` ([[g:swappable-with]]) if and only if:

- ¶2.1 the expressions `swap(t, u)` and `swap(u, t)` are valid when evaluated in the context described below; and
- ¶2.2 their effect is to exchange the values: the object referred to by `t` has the value originally held by `u`, and the object referred to by `u` has the value originally held by `t`.

¶3 The context in which `swap(t, u)` is evaluated shall ensure that a binary non-member function named `swap` is selected via overload resolution on a candidate set that includes the two `swap` function templates in `<utility>` (the one for single objects and the one for arrays, ¶3.1) and the functions found by argument-dependent lookup (ADL, ¶3.2).

This is the **two-step** ([[g:swap-two-step]]): `using std::swap;` puts `std::swap` in the candidate set, and the unqualified call `swap(a, b)` then adds the user's own `swap` through ADL. [[contents#3]] says that unqualified calls to `swap` in the library's description are evaluated in this context, so when `std::sort` swaps elements it uses the `swap` you defined in your type's namespace. The body of libc++'s `std::iter_swap` is a single unqualified `swap(*__a, *__b);`: it is itself in `std`, so ordinary lookup finds `std::swap`, and ADL adds the user's version.

Note 1 points out that when `T` and `U` are both fundamental types or arrays of fundamental types, this candidate set is the same as the lookup result of the qualified call `std::swap(t, u)`. Note 2 says it is unspecified whether a library component that has a swappable requirement includes `<utility>` itself.

Building on these definitions:

- ¶4 An rvalue or lvalue `t` is **swappable** if and only if `t` is swappable with any rvalue or lvalue, respectively, of type `T`.
- ¶5 A type `X` meets ***Cpp17Swappable*** if lvalues of type `X` are swappable.
- ¶6 A type `X` meeting any of the iterator requirements meets ***Cpp17ValueSwappable*** if, for any dereferenceable `x`, `*x` is swappable. Algorithms such as `std::iter_swap` and `std::reverse` use it.

¶7 Example 1 shows how user code can call `swap` in the right context, including swapping between different types: `N::A` and a proxy type `N::Proxy`. It defines both `swap(A&, Proxy)` and `swap(Proxy, A&)`, the latter only to meet the symmetry required by ¶2.1.

Since C++20, `std::ranges::swap` is recommended. It is a [[g:customization-point-object]] that performs the two-step internally and falls back to a move-based swap when it finds no user `swap`.

## *Cpp17NullablePointer* [nullablepointer.requirements]

```cpp run ok
#include <cstddef>
#include <cstdio>
#include <memory>

struct Fd {                                    // file descriptor handle
  int fd = -1;                                 // value-initialization gives the null value
  Fd() = default;
  Fd(std::nullptr_t) noexcept {}
  Fd(int f) noexcept : fd(f) {}
  explicit operator bool() const noexcept { return fd != -1; }
  friend bool operator==(Fd, Fd) = default;
  friend bool operator==(Fd a, std::nullptr_t) noexcept { return a.fd == -1; }
};

struct FdCloser {
  using pointer = Fd;                          // unique_ptr uses this as its pointer type
  void operator()(Fd f) const noexcept { std::printf("close(%d)\n", f.fd); }
};

int main() {
  std::unique_ptr<int, FdCloser> p(Fd{3});     // prints close(3) on destruction
  std::unique_ptr<int, FdCloser> q;            // null: the deleter isn't called on destruction
  return p && !q ? 0 : 1;
}
```

What `std::unique_ptr<T, D>` manages isn't necessarily a pointer: if the deleter `D` defines a `pointer` type, `unique_ptr` stores an object of that type. The example above uses this to manage a file descriptor. That type must meet *Cpp17NullablePointer*.

¶1 A ***Cpp17NullablePointer*** type is a pointer-like type that supports null values. A type `P` meets it if:

- ¶1.1 it meets *Cpp17EqualityComparable*, *Cpp17DefaultConstructible*, *Cpp17CopyConstructible*, *Cpp17CopyAssignable*, *Cpp17Swappable* and *Cpp17Destructible*;
- ¶1.2 the expressions in Table 36 are valid and have the specified semantics; and
- ¶1.3 it meets the other requirements of this subclause.

¶2 A value-initialized object of type `P` is the null value of the type, and the null value compares equal only to itself. A default-initialized object of type `P` may have an indeterminate or erroneous value; Note 1 warns that using the former may be UB and using the latter may be erroneous behavior ([[basic.indet]]).

¶3 An object `p` of type `P` can be contextually converted to `bool`, with the effect as if `p != nullptr` had been evaluated.

¶4 No operation that is part of the *Cpp17NullablePointer* requirements shall exit via an exception.

¶5 In Table 36, `t` is a non-const lvalue of type `P`, `a` and `b` are values of type `P`, and `np` is a value of type `std::nullptr_t`:

| Expression | Semantics |
|---|---|
| `P u(np);`, `P u = np;`, `P(np)` | The result equals `nullptr` |
| `t = np` | Returns `P&`; afterwards `t == nullptr` |
| `a != b` | `!(a == b)` |
| `a == np`, `np == a` | `a == P()` |
| `a != np`, `np != a` | `!(a == np)` |

With C++20's rewritten operator rules, the example above only needs to define two `operator==`; `!=` and `np == a` come automatically. Besides `unique_ptr::pointer`, the various pointer types of allocators ([[allocator.requirements.general#92]]) and `std::exception_ptr` also meet this requirement.

## *Cpp17Hash* [hash.requirements]

```cpp run ok
#include <cstddef>
#include <functional>
#include <unordered_set>

struct Point {
  int x, y;
  bool operator==(const Point&) const = default;
};

template<> struct std::hash<Point> {   // allowed: depends on a program-defined type
  std::size_t operator()(const Point& p) const noexcept {
    std::size_t h = std::hash<int>{}(p.x);
    return h ^ (std::hash<int>{}(p.y) + 0x9e3779b9 + (h << 6) + (h >> 2));
  }
};

int main() {
  std::unordered_set<Point> s{{1, 2}, {3, 4}, {1, 2}};
  return s.size() == 2 ? 0 : 1;
}
```

To provide a hash for your own type, you usually specialize `std::hash`, which [[namespace.std#2]] explicitly allows. The resulting specialization must meet *Cpp17Hash*.

¶1 A type `H` meets ***Cpp17Hash*** if it is a function object type ([[function.objects]]), meets *Cpp17CopyConstructible* and *Cpp17Destructible*, and the expressions in Table 37 are valid and have the specified semantics.

¶2 In Table 37, `Key` is an argument type for `H`, `h` is a value of type `H`, `u` is an lvalue of type `Key`, and `k` is a value of a type convertible to `Key`:

| Expression | Return type | Requirement |
|---|---|---|
| `h(k)` | `size_t` | The value returned depends only on `k` and doesn't change for the duration of the program; for distinct values `t1` and `t2`, the probability of `h(t1) == h(t2)` should be very small, approaching `1.0 / numeric_limits<size_t>::max()` |
| `h(u)` | `size_t` | Shall not modify `u` |

Three points about this table:

- Note 1 is more explicit: the result is consistent only within a single execution of the program. Hash values may change between runs, and implementations can use a random seed to resist hash-flooding attacks. libc++'s `std::hash<std::string>` is currently deterministic, but writing results of `std::hash` to a file or sending them over the network isn't portable.
- The low collision probability is a "should", only a recommendation. In libc++ and libstdc++, `std::hash<int>` is the identity function, so distinct values never collide, but the low-bit distribution is poor for some inputs (for example, all multiples of 8); the unordered containers of these two implementations mitigate this with a prime number of buckets.
- Table 37 doesn't require equal keys to have equal hash values. That is a requirement the unordered containers place on the combination of `Hash` and `Pred` ([[unord.req]]), at a different level.

Which specializations of `std::hash` are enabled, and the properties of disabled ones, are covered in [[unord.hash]].

## *Cpp17Allocator* [allocator.requirements]

### A minimal allocator

```cpp run ok
#include <cstddef>
#include <cstdio>
#include <new>
#include <vector>

template<class T>
struct Counting {
  using value_type = T;
  static inline std::size_t allocs = 0;
  Counting() = default;
  template<class U> Counting(const Counting<U>&) noexcept {}
  T* allocate(std::size_t n) {
    ++allocs;
    return static_cast<T*>(::operator new(n * sizeof(T)));
  }
  void deallocate(T* p, std::size_t n) noexcept {
    ::operator delete(p, n * sizeof(T));
  }
  template<class U>
  bool operator==(const Counting<U>&) const noexcept { return true; }
};

int main() {
  std::vector<int, Counting<int>> v;
  for (int i = 0; i < 100; ++i) v.push_back(i);
  std::printf("allocations: %zu\n", Counting<int>::allocs);   // libc++ in our tests prints 8
}
```

¶1 An **allocator** is an object of class type that encapsulates an allocation model: which pointer type to use, which types to use for pointer differences and object sizes, and how to allocate and deallocate memory under that model. All the string types, the containers other than `array` and `inplace_vector`, the string streams and `match_results` are parameterized in terms of allocators.

¶3 Containers don't use an allocator directly; they access it through the class template `allocator_traits` ([[allocator.traits]]). If a requirement specifies a default, it is optional: when the allocator doesn't provide it, `allocator_traits` uses the default instead. Note 1 says that programs can't specialize `allocator_traits`.

So `Counting` above writes only five things: `value_type`, `allocate`, `deallocate`, a constructor converting from `Counting<U>`, and `==`. `pointer`, `rebind`, `construct`, `propagate_on_container_*` and the rest are filled in by `allocator_traits`. libc++ implements these defaults by detecting whether members exist; for example, for `pointer` it first looks for `_Alloc::pointer` and uses `T*` if there is none.

¶98 Example 2 gives a minimal interface consisting of exactly these five things. ¶99 expresses the same minimal requirements with an exposition-only concept *simple-allocator*: dereferencing the result of `allocate` gives `value_type&`, it can `deallocate`, it is copy constructible, and it can be compared with `==`. A type that meets the requirements of this subclause models this concept. Newer components refer to it, for example the `get_allocator` query of `std::execution` ([[exec.get.allocator]]).

### Summary of the requirements (¶4–¶91)

¶2 defines the notation used in the table: `X` is an allocator type for `T`, `Y` is the corresponding allocator type for `U`, and `XX` is `allocator_traits<X>`; `a`, `a1` and `a2` are lvalues of type `X`, and `b` is a value of type `Y`; `p` is a pointer returned by `a1.allocate` (with `a1 == a`); `n` is a value of type `XX::size_type`.

| Expression | Result or semantics | Default |
|---|---|---|
| `X::value_type` | Identical to `T` | Must be provided |
| `X::pointer` | | `T*` |
| `X::const_pointer`, `void_pointer`, `const_void_pointer` | `pointer` is convertible to them | Obtained through `rebind` of `pointer_traits` |
| `X::size_type` | An unsigned integer type that can represent the size of the largest object | `make_unsigned_t<difference_type>` |
| `X::difference_type` | A signed integer type that can represent the difference between any two pointers | `pointer_traits<pointer>::difference_type` |
| `X::rebind<U>::other` | `Y` | Replaces `SomeAllocator<T, Args>` with `SomeAllocator<U, Args>` |
| `a.allocate(n)` | Allocates memory for an array of `n` `T` | Must be provided |
| `a.allocate_at_least(n)` {{c++23}} | Returns `{ptr, count}` with `count >= n` | `{a.allocate(n), n}` |
| `a.deallocate(p, n)` | Deallocates; doesn't throw | Must be provided |
| `a.max_size()` | The largest `n` that can meaningfully be passed to `allocate` | `numeric_limits<size_type>::max() / sizeof(value_type)` |
| `a1 == a2` | Whether memory allocated by one can be deallocated by the other; doesn't throw | Must be provided |
| `X u(b);` | Converting construction from `Y`, with `Y(u) == b` and `u == X(b)`; doesn't throw | Must be provided |
| `X u(a);`, `X u(std::move(a));` | `u == a`; doesn't throw | |
| `a.construct(c, args...)`, `a.destroy(c)` | Constructs or destroys an object at `c` | `construct_at`, `destroy_at` |
| `a.select_on_container_copy_construction()` | The allocator the new container uses when a container is copied | `return a;` |
| `X::propagate_on_container_copy_assignment` and the other two | Whether the allocator is propagated along with container copy assignment, move assignment and swap | `false_type` |
| `X::is_always_equal` | Whether any two `X` always compare equal | `is_empty<X>::type` |

Several of these deserve more explanation.

¶36 `allocate` doesn't just allocate memory; it also **creates an array object of `n` `T`**, without constructing its elements. Pointer arithmetic is defined only within an array object ([[expr.add]]), and this sentence is what makes `p + i` valid when a container works within allocated memory. Example 1 shows how to do this when reusing storage: `launder(reinterpret_cast<T*>(new (p) byte[n * sizeof(T)]))` can implicitly create a suitable array object and obtain a pointer to it ([[intro.object]]).

¶48 The preconditions of `deallocate` are strict: `p` must come from `allocate`, and `n` must equal the value originally passed to `allocate`; if it came from `allocate_at_least`, `n` may be anything between the requested number and the `count` actually obtained. So allocators don't need to record the size of each block, and `std::allocator` can call the sized `operator delete(void*, size_t)` directly.

¶54 Two allocators being equal doesn't mean the objects are identical; it means **memory allocated by one can be deallocated by the other**. Stateless allocators are always equal; `std::pmr::polymorphic_allocator`s are equal when they point to the same memory resource. Equality decides whether a container's move assignment can take over the other's memory directly: when the allocators aren't equal and don't propagate on assignment, elements can only be moved one by one.

¶80–¶91 The three `propagate_on_container_*` traits decide whether the allocator is copied, moved or swapped along with the container's contents; all default to `false_type`, meaning a container keeps its original allocator after assignment. `std::pmr::polymorphic_allocator` doesn't change these three defaults; by design, its allocator doesn't follow the data. `is_always_equal` defaults to `is_empty<X>`: an allocator with no data members can't have state, so it is necessarily always equal.

### Fancy pointers (¶92–¶95)

¶92 An allocator type shall meet *Cpp17CopyConstructible*. Its four pointer types shall meet *Cpp17NullablePointer*, and their construction, comparison, copy, move and swap operations shall not throw exceptions. `pointer` and `const_pointer` shall also meet *Cpp17RandomAccessIterator*, and the elements they point to shall be contiguous: when `p` and `p + n` are both dereferenceable, `addressof(*(p + n)) == addressof(*p) + n`.

These requirements are there for **fancy pointers** ([[g:fancy-pointer]]), pointer types that aren't built-in pointers. The typical example is an offset pointer used in shared memory, such as `boost::interprocess::offset_ptr`: it stores an offset relative to its own address, so the same data structure can be mapped at different addresses in different processes. Containers must therefore always use `allocator_traits<A>::pointer` internally and can't quietly store raw pointers instead.

¶93 defines **equivalently-valued** ([[g:equivalently-valued]]): two pointer values that compare equal after both are converted to `const_pointer` using only `static_cast` between these four pointer types. ¶94 and ¶95 say that comparisons between `void_pointer`s, and comparison and subtraction between `pointer`s, keep their semantics when either operand is replaced with an equivalently-valued `const` version.

### Allocators may reject some types (¶96, ¶97)

¶96 An allocator may constrain the types on which it can be instantiated and the arguments for which `construct` and `destroy` may be called. If a type can't be used with a particular allocator, the allocator class itself or the call to `construct` / `destroy` may fail to instantiate.

¶97 If the alignment required by an over-aligned type isn't supported by an allocator, instantiating the allocator with that type may fail, or the allocator may silently ignore the alignment requirement; Note 4 adds that `allocate` may also throw `bad_alloc`. So when an `alignas(64)` type is put into a container with a custom allocator, whether the alignment is honored depends on the allocator. `std::allocator` uses C++17's aligned `operator new` and honors the alignment requirement.

### Allocator completeness requirements [allocator.requirements.completeness]

```cpp run ok
#include <list>
#include <vector>
struct Node {
  int value;
  std::vector<Node> children;   // OK: Node is still incomplete here
  std::list<Node> siblings;     // likewise
};
int main() {
  Node n{1, {}, {}};
  n.children.push_back({2, {}, {}});
  return n.children.size() == 1 ? 0 : 1;
}
```

¶1 If `X` is an allocator type for `T`, `X` meets the **allocator completeness requirements** ([[g:allocator-completeness-requirements]]) if, whether or not `T` is complete, `X` is a complete type (¶1.1), and all the member types of `allocator_traits<X>` other than `value_type` are complete types (¶1.2).

This requirement is the basis on which C++17 allows `vector`, `list` and `forward_list` to be instantiated with incomplete types ([[N4510]]). The subclauses for these containers say that if the allocator meets the completeness requirements, `T` may be incomplete when the container is instantiated, as long as it becomes complete before certain members are used. `std::allocator` meets this requirement, so recursive data structures like the one above can be written directly.

`std::map<K, Node>`, `std::deque<Node>`, `std::unordered_map` and others have no such permission, and instantiating them with an incomplete type is UB ([[res.on.functions#2.5]]), even though in practice it often compiles.

## Common misconceptions

!!! pitfall "Writing `std::swap(a, b)` in generic code"
    A qualified call bypasses the `swap` users have customized for their types, losing its efficiency and its `noexcept`. Generic code should use the two-step or `std::ranges::swap`.

!!! pitfall "`==` of a stateful allocator always returns true"
    `==` means whether the two can deallocate each other's memory. If two allocators can't actually deallocate each other's memory but `==` returns `true`, a container will hand memory to the wrong allocator to deallocate during move assignment, `swap` or `splice`, which is UB.

## Questions

!!! question "Question 1"
    An allocator has `is_always_equal` as `true_type` and `propagate_on_container_move_assignment` as `false_type`. What is the complexity of move assignment for `std::vector<T, A>`? Can it throw?

<details markdown="1">
<summary>Answer</summary>

Since the allocators are always equal, the target container's allocator can deallocate the source container's memory, so move assignment can take over the source's buffer directly: apart from the linear time to destroy the target's existing elements, it takes constant time, with no element-by-element moves, and it doesn't throw. The standard's exception specification for `vector`'s move assignment is exactly `noexcept(allocator_traits<A>::propagate_on_container_move_assignment::value || allocator_traits<A>::is_always_equal::value)` ([[vector.overview]]).

If both are `false` and the two allocators compare unequal at run time, the container can only move-construct the elements one by one into its own storage, which takes linear time and may throw.
</details>

!!! question "Question 2"
    A type's `operator<` compares only the field `x`, while its `operator==` compares both `x` and `y`. Is there a problem putting it into a `std::set`?

<details markdown="1">
<summary>Answer</summary>

`<` itself is still a strict weak ordering: looking only at `x`, irreflexivity and transitivity hold, and incomparability is just equality of `x`, which is an equivalence relation. So the behavior of `std::set` is well-defined.

The problem is that `std::set` uses only `<` to decide whether two elements are the same: two objects with the same `x` but different `y` are treated as the same element, and the one inserted later is rejected. This is inconsistent with the type's own `==` and easily misunderstood, but it isn't UB.
</details>
