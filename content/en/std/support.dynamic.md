---
title: Dynamic memory management
summary: "What is in the header <new>: the global allocation and deallocation functions, the three tag types nothrow_t / align_val_t / destroying_delete_t, new_handler, std::launder, and the two cache-line size constants used to avoid false sharing."
updated: 2026-10-19
---

!!! tldr
    - `new` and `delete` are expressions in the language, but the `operator new` / `operator delete` they call to obtain and return memory are provided by the library and declared in `<new>`.
    - These global functions are implicitly declared in every translation unit and can be used without including `<new>`; only `std::nothrow`, `std::align_val_t` and the placement forms require including it.
    - `nothrow_t`, `align_val_t` and `destroying_delete_t` are tag types whose purpose is to select, in overload resolution, allocation or deallocation functions with different semantics.
    - `hardware_destructive_interference_size` is for separating two objects written by different threads, and `hardware_constructive_interference_size` for placing data accessed together in the same cache line. Both are implementation-defined, and an `alignas` using them in a header carries ABI risk.

## What is in `<new>` [new.syn]

```cpp
std::string* p = new std::string("hi");   // calls operator new(sizeof(std::string)), then constructs
delete p;                                 // destroys, then calls operator delete(p, ...)
```

A *new-expression* has two steps: first it calls an **allocation function** to obtain raw memory, then it constructs the object in it ([[expr.new]]). A *delete-expression* does the reverse: it destroys first, then calls a **deallocation function** to return the memory ([[expr.delete]]). The core language specifies the forms of these two kinds of functions and the conventions they must follow in [[basic.stc.dynamic]]; the library provides their default versions and the supporting types in this subclause.

¶1 [support.dynamic.general] is a single sentence: `<new>` defines functions that manage dynamic storage, and components that report storage management errors. The whole header is freestanding, so even freestanding implementations without an operating system must provide it. Grouped by purpose, its contents are:

```cpp
namespace std {
  class bad_alloc;                       // allocation failure, see [alloc.errors]
  class bad_array_new_length;            // invalid array length

  struct destroying_delete_t { explicit destroying_delete_t() = default; };
  inline constexpr destroying_delete_t destroying_delete{};

  enum class align_val_t : size_t {};    // passes an alignment value

  struct nothrow_t { explicit nothrow_t() = default; };
  extern const nothrow_t nothrow;

  using new_handler = void (*)();        // callback on memory exhaustion, see [alloc.errors]
  new_handler get_new_handler() noexcept;
  new_handler set_new_handler(new_handler new_p) noexcept;

  template<class T> constexpr T* launder(T* p) noexcept;   // see [ptr.launder]

  inline constexpr size_t hardware_destructive_interference_size  = implementation-defined;
  inline constexpr size_t hardware_constructive_interference_size = implementation-defined;
}
// global scope: the 22 declarations of operator new / new[] / delete / delete[], see [new.delete]
```

The allocation and deallocation functions are declared in the global namespace, not in `std`. [[basic.stc.dynamic.general]] requires them to be implicitly declared in every translation unit, so `::operator new(16)` can be called without including any header. The placement form `operator new(size_t, void*)` isn't implicitly declared; include `<new>` before using `new (buf) T`.

| Subclause | Contents | Details |
|---|---|---|
| [new.delete] | The contracts and default behavior of the 22 global `operator new` / `operator delete` | [[new.delete]] |
| [alloc.errors] | `bad_alloc`, `bad_array_new_length`, `new_handler` | [[alloc.errors]] |
| [ptr.launder] | `std::launder` | [[ptr.launder]] |
| [hardware.interference] | The two cache-line size constants | Below on this page |

## Three tag types

Tag types carry no data (`align_val_t` is the exception); they exist only to make overload resolution select a particular function.

### `std::nothrow`: a null pointer on failure

```cpp
T* p1 = new T;                 // throws std::bad_alloc on failure
T* p2 = new (std::nothrow) T;  // gives a null pointer on failure
```

`new (std::nothrow) T` passes `std::nothrow` as a placement argument and therefore calls `operator new(size_t, const nothrow_t&)`, which returns a null pointer on failure ([[new.delete.single#5]]).

The default constructor of `nothrow_t` is `explicit`, as with all standard library tag types. This prevents `{}` from implicitly converting to a tag: `std::nothrow_t t = {};` is ill-formed, and `f({})` won't accidentally match an overload with a tag parameter. Clang 23 reports "chosen constructor is explicit in copy-initialization" for the former.

### `std::align_val_t`: over-aligned types {{c++17}}

```cpp run title="align-val.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

void* operator new(std::size_t n, std::align_val_t al) {
  auto a = static_cast<std::size_t>(al);
  std::printf("new(%zu, align %zu)\n", n, a);
  if (void* p = std::aligned_alloc(a, (n + a - 1) / a * a))
    return p;
  throw std::bad_alloc();
}
void operator delete(void* p, std::align_val_t) noexcept {
  std::free(p);
}

struct alignas(64) Line { char data[64]; };

int main() {
  Line* p = new Line;   // prints: new(64, align 64)
  delete p;
  int* q = new int;     // ordinary alignment: prints nothing
  delete q;
}
```

The macro `__STDCPP_DEFAULT_NEW_ALIGNMENT__` gives the alignment guaranteed by the ordinary `operator new(size_t)`; it is 16 in our tests. A type whose alignment requirement exceeds it has a **new-extended alignment** ([[basic.align]]). When a *new-expression* allocates memory for such a type, it passes an extra `std::align_val_t` argument and calls the version with an alignment parameter ([[expr.new]]).

`align_val_t` is a scoped enumeration with underlying type `size_t`, not `size_t` itself. This keeps it from clashing with a user-defined placement form `operator new(size_t, size_t)`. `aligned_alloc` requires the size to be a multiple of the alignment, so the example rounds `n` up.

### `std::destroying_delete`: an `operator delete` that does its own destruction {{c++20}}

If a class's member `operator delete` has `std::destroying_delete_t` as the type of its second parameter, it is a **destroying operator delete** ([[g:destroying-operator-delete]]). When a *delete-expression* encounters one, it doesn't call the destructor but hands the not-yet-destroyed object to it, and the function is responsible for destruction and deallocation ([[expr.delete]], [[basic.stc.dynamic.deallocation]]).

```cpp run title="destroying-delete.cpp" ok
#include <cstdio>
#include <new>

struct Shape {
  enum Kind { circle, square } kind;
  void operator delete(Shape* p, std::destroying_delete_t);
};
struct Circle : Shape {
  double r;
  ~Circle() { std::puts("~Circle"); }
};
struct Square : Shape {
  double a;
  ~Square() { std::puts("~Square"); }
};

void Shape::operator delete(Shape* p, std::destroying_delete_t) {
  // *p hasn't been destroyed on entry; dispatch on kind
  if (p->kind == circle) ::delete static_cast<Circle*>(p);
  else                   ::delete static_cast<Square*>(p);
}

int main() {
  Shape* s = new Circle{{Shape::circle}, 1.0};
  delete s;   // calls Shape::operator delete, prints ~Circle
}
```

`Shape` has no virtual destructor, so `delete` through a base class pointer would ordinarily be undefined behavior. The destroying `operator delete` lets the class itself find the right derived class from the `kind` field, then destroy and deallocate with the correct static type, saving the vtable pointer.

Inside, you must write `::delete`. `Circle` doesn't declare its own `operator delete`, so class-scope lookup would find this destroying version in the base class, and without `::` it would recurse infinitely.

## Hardware interference size [hardware.interference] {{c++17}}

```cpp run title="interference.cpp" ok
#include <atomic>
#include <new>
#include <thread>

struct Counters {
  alignas(std::hardware_destructive_interference_size)
    std::atomic<long> a{0};   // written by thread 1
  alignas(std::hardware_destructive_interference_size)
    std::atomic<long> b{0};   // written by thread 2
};

struct Together { std::atomic<int> dog; int puppy; };
static_assert(sizeof(Together)
              <= std::hardware_constructive_interference_size);

int main() {
  Counters c;
  std::thread t1([&] { for (int i = 0; i < 100000; ++i) ++c.a; });
  std::thread t2([&] { for (int i = 0; i < 100000; ++i) ++c.b; });
  t1.join(); t2.join();
}
```

If `a` and `b` were adjacent, they would fall in the same cache line. Each of two cores writes its own variable, but every write invalidates that line in the other core's cache; this is called **false sharing**. The two pieces of data are logically unrelated, yet performance is as if they were contending for the same variable.

¶1 `hardware_destructive_interference_size` is the minimum recommended offset between two concurrently-accessed objects to avoid this kind of contention introduced by the implementation. The typical use is the `alignas` above.

¶2 `hardware_constructive_interference_size` is the maximum recommended size of contiguous memory occupied by two objects accessed with temporal locality by concurrent threads. Keeping `dog` and `puppy` within this size makes it likely they are in the same cache line, so a single cache miss brings both in. The typical use is the `static_assert` above.

Both constants are implementation-defined; the standard only requires them to be at least `alignof(max_align_t)`. On AArch64 macOS, Clang 23 gives 128 for destructive and 64 for constructive, and `sizeof(Counters)` is 256. Destructive being larger than constructive is common: some CPUs prefetch adjacent cache lines in pairs, so to avoid interference you need to separate by two lines, while to guarantee togetherness you can only count on one.

!!! impl "Values vary with compiler options: an ABI risk"
    libc++ defines these two constants with the compiler-predefined macros `__GCC_DESTRUCTIVE_SIZE` and `__GCC_CONSTRUCTIVE_SIZE`, which may change with `-mcpu` and `-mtune`. If a class in a header uses them in `alignas`, two translation units compiled with different options derive different layouts for the same class, violating the ODR ([[basic.def.odr]]). GCC provides the `-Winterference-size` warning for this. Types that cross an ABI boundary should use a concrete number directly, such as 64 or 128.

## Questions

!!! question "Question"
    Given `struct alignas(32) S { int x; };` on a platform where `__STDCPP_DEFAULT_NEW_ALIGNMENT__` is 16, which allocation function does `new S[10]` call? What if `S` declares a member `operator new[](size_t)` but no version taking `align_val_t`?

<details markdown="1">
<summary>Answer</summary>

`alignof(S)` is 32, which exceeds 16, so it has new-extended alignment. The *new-expression* looks up `operator new[]` with the arguments `(size, std::align_val_t(32))`, and with no member version it finds the global `operator new[](size_t, align_val_t)`.

If `S` has a member `operator new[](size_t)`, class-scope lookup finds it first. After overload resolution with the alignment argument fails, [[expr.new#20]] says to try again without the alignment argument, so the member `operator new[](size_t)` is called, and meeting the 32-byte alignment becomes that function's own responsibility. A member `operator new` declared only for non-arrays has nothing to do with `new S[10]`.
</details>
