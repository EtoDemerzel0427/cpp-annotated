---
title: Type erasure from the ground up
summary: "Run-time polymorphism without a common base class and with value semantics: hand-building a Drawable step by step from an internal virtual interface, adding copying, moving, a small buffer and a hand-written vtable, explaining the rules of placement new, launder, lifetimes and noexcept moves, then looking at what each type-erasing type in the standard library erases and what it costs."
tags: type erasure, polymorphism, value semantics, small-object optimization, std::function, std::any, design patterns
updated: 2026-10-19
---

!!! tldr
    - Type erasure lets unrelated types that share the same operations (all having `draw()`, say) be held in a single type, copied and moved by value and put in containers, without the user's types inheriting from any base class.
    - The classic implementation is a private virtual interface (the concept) plus a class template implementation (the model), with the outer class holding the model through a pointer; copying goes through a virtual `clone()`, and the constructor template must exclude the outer class itself.
    - The small buffer optimization constructs small objects directly inside the outer object, avoiding the heap allocation; it requires correct alignment and manual lifetime management, and can only be used for types whose move constructor doesn't throw, otherwise the outer `noexcept` move can't hold.
    - Replacing virtual functions with a struct of function pointers lets the whole object go into the buffer and saves one indirection per call; the cost is having to recover the object from the buffer address with `std::launder`.
    - The standard library's `function`, `move_only_function`, `copyable_function`, `function_ref`, `any`, `shared_ptr`'s deleter, `pmr::memory_resource` and C++26's `polymorphic` are all type erasure; they differ in what they erase, whether they own the object, whether they are copyable, and what happens when an empty one is used.

## The problem: polymorphism without a common base

A drawing program needs to put various shapes into one container and call `draw()` on each. The shapes come from different libraries: `Circle` is our own, `Text` comes from a third-party library we can't modify. Both have `void draw() const`, but no common base class.

<div class="compare" markdown="1">

```cpp
// inheritance: every type must derive from Shape
struct Shape {
  virtual ~Shape() = default;
  virtual void draw() const = 0;
};
struct Circle : Shape {
  double r;
  void draw() const override;
};
// Text can't be changed; it needs another wrapper
std::vector<std::unique_ptr<Shape>> v;
// v can't be copied, elements may be null
```

```cpp
// type erasure: only requires draw()
struct Circle {
  double r;
  void draw() const;
};
struct Text {              // a third-party type
  std::string s;
  void draw() const;
};
std::vector<Drawable> v{Circle{1},
                        Text{"hi"}};
auto w = v;                // deep copy
```

</div>

On the left is classic virtual-function polymorphism, which has three limitations. First, types must inherit `Shape` beforehand; this is called an **intrusive** design, and types you can't modify need yet another adapter class. Second, objects can only be used through pointers or references, and the container holds `unique_ptr`s, losing value semantics: no direct copying, and elements may be null. Third, `Shape`'s interface is fixed in the base class, and for a type to take part in another interface it has to inherit again.

Templates (or concepts) are another road: `template <class T> void render(const T&)` doesn't require inheritance, but each type generates its own code, and a `vector` can still hold only one type.

**Type erasure** ([[g:type-erasure]]) takes the best of both: `Drawable` is an ordinary value type that can be constructed from any object with `draw()`; at construction it records how to call, copy and destroy the concrete type, after which the concrete type vanishes from the static type. Calls go through run-time dispatch, just as with virtual functions; but user types don't have to inherit anything, and `Drawable` itself can be copied, moved and put in containers.

## Step 1: concept and model

```cpp run title="step1.cpp" ok
#include <cstdio>
#include <memory>
#include <string>
#include <utility>
#include <vector>

// two unrelated types with no common base
struct Circle { double r; void draw() const { std::printf("circle %g\n", r); } };
struct Text   { std::string s; void draw() const { std::printf("text %s\n", s.c_str()); } };

class Drawable {
  struct Concept {                         // internal interface
    virtual ~Concept() = default;
    virtual void draw() const = 0;
  };
  template <class T>
  struct Model final : Concept {           // one implementation per concrete type
    T obj;
    explicit Model(T x) : obj(std::move(x)) {}
    void draw() const override { obj.draw(); }
  };
  std::unique_ptr<Concept> self;

public:
  template <class T>
  Drawable(T x) : self(std::make_unique<Model<T>>(std::move(x))) {}
  void draw() const { self->draw(); }
};

int main() {
  std::vector<Drawable> v;
  v.emplace_back(Circle{1.5});
  v.emplace_back(Text{"hi"});
  for (const Drawable& d : v) d.draw();
}
```

The structure has three layers:

1. `Concept` is an abstract base visible only inside `Drawable`, listing the operations the erased types must support. It is conventionally called the concept, unrelated to the C++20 `concept` keyword.
2. `Model<T>` is a class template derived from `Concept` that holds a `T` and forwards each virtual function to `T`'s operation of the same name. Every time `Drawable` is constructed from a new type, the compiler instantiates a new `Model<T>`, along with its vtable.
3. `Drawable` holds a `unique_ptr<Concept>` and offers a non-virtual `draw()` that forwards to `self->draw()`.

Inheritance is still there, just moved from the user's types into the library's internals: it is `Model<Circle>` that inherits `Concept`, not `Circle`. `Circle` knows nothing about `Drawable`, and all `Drawable` requires of `Circle` is that the expression `obj.draw()` compiles.

This version still lacks two things: it can't be copied (its member is a `unique_ptr`), and the constructor template is unconstrained, so any type can attempt construction, with errors appearing only when `Model<T>::draw` is instantiated.

## Step 2: copying and moving

```cpp run title="step2.cpp" ok
#include <concepts>
#include <cstdio>
#include <memory>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

struct Circle { double r; void draw() const { std::printf("circle %g\n", r); } };
struct Text   { std::string s; void draw() const { std::printf("text %s\n", s.c_str()); } };

template <class T>
concept CanDraw = requires(const T& t) { t.draw(); };

class Drawable {
  struct Concept {
    virtual ~Concept() = default;
    virtual void draw() const = 0;
    virtual std::unique_ptr<Concept> clone() const = 0;
  };
  template <class T>
  struct Model final : Concept {
    T obj;
    template <class U>
    explicit Model(U&& u) : obj(std::forward<U>(u)) {}
    void draw() const override { obj.draw(); }
    std::unique_ptr<Concept> clone() const override {
      return std::make_unique<Model>(obj);
    }
  };
  std::unique_ptr<Concept> self;

public:
  template <class T>
    requires (!std::same_as<std::remove_cvref_t<T>, Drawable>)
             && CanDraw<std::remove_cvref_t<T>>
  Drawable(T&& x)
      : self(std::make_unique<Model<std::remove_cvref_t<T>>>(std::forward<T>(x))) {}

  Drawable(const Drawable& o) : self(o.self->clone()) {}
  Drawable(Drawable&&) noexcept = default;
  Drawable& operator=(const Drawable& o) { return *this = Drawable(o); }
  Drawable& operator=(Drawable&&) noexcept = default;

  void draw() const { self->draw(); }
};

int main() {
  std::vector<Drawable> v{Circle{1.5}, Text{"hi"}};
  std::vector<Drawable> w = v;         // deep copy: each element is cloned once
  w[0] = Text{"replaced"};
  for (const Drawable& d : v) d.draw();
  for (const Drawable& d : w) d.draw();
}
```

In our tests it prints `circle 1.5`, `text hi`, `text replaced`, `text hi`: modifying `w` doesn't affect `v`. That is value semantics.

First, copying. `Drawable`'s copy constructor doesn't know the concrete type `self` points to; only `Model<T>` does, so copying also has to go through a virtual function: `clone()` in `Model<T>` makes a new `Model` with `T`'s copy constructor. This is the same trick as a virtual `clone()` in a hand-written polymorphic hierarchy, except it is written once and generated by the template for every `T`.

Copy assignment constructs a copy first and then move-assigns it. If constructing the copy fails, `*this` is unchanged: the strong exception guarantee; see [[topics/exception-safety]].

Moving just reuses `unique_ptr`'s move: it swaps pointers without touching the erased object, so it can be `noexcept`. A moved-from `Drawable` has a null `self`; it can only be destroyed or assigned to, and calling `draw()` on it dereferences a null pointer. This matches the standard library's convention: a moved-from object is in a valid but unspecified state ([[g:valid-but-unspecified-state]]), and must be assigned to before calling operations with preconditions.

The constructor template has two constraints: `CanDraw` excludes types that can't `draw()` during overload resolution, so the error message points at the call site; `!same_as<..., Drawable>` keeps it from competing with the copy constructor. The second looks redundant; the traps section below shows what happens without it.

`Model` stores `remove_cvref_t<T>`: when constructing from an lvalue `Circle&`, a `Circle` is copied in, not a reference stored. Value-semantic type erasure always owns its object.

## Step 3: the small buffer optimization

The `Drawable` above `new`s a `Model` on every construction, even if the erased object is only 8 bytes. The **small-object optimization** (SBO, [[g:small-object-optimization]]) reserves a buffer inside the outer object; objects that fit are constructed directly in it, and only those that don't go on the heap.

```cpp run title="sbo.cpp" ok
#include <concepts>
#include <cstddef>
#include <cstdio>
#include <new>
#include <string>
#include <type_traits>
#include <utility>

template <class T>
concept CanDraw = requires(const T& t) { t.draw(); };

class Drawable {
  static constexpr std::size_t Size = 3 * sizeof(void*);
  static constexpr std::size_t Align = alignof(void*);

  struct Concept {
    virtual void draw() const = 0;
    virtual Concept* copy_to(void* buf) const = 0;      // returns the new object's address
    virtual Concept* move_to(void* buf) noexcept = 0;   // same; *this is invalid afterwards
    virtual void destroy() noexcept = 0;                // destroys, freeing if necessary
  protected:
    ~Concept() = default;                               // destroyed only through destroy()
  };

  template <class T, bool Inline>
  struct Model final : Concept {
    T obj;
    template <class... A> explicit Model(A&&... a) : obj(std::forward<A>(a)...) {}
    void draw() const override { obj.draw(); }
    Concept* copy_to(void* buf) const override {
      if constexpr (Inline) return ::new (buf) Model(obj);
      else return new Model(obj);
    }
    Concept* move_to(void* buf) noexcept override {
      if constexpr (Inline) {
        Concept* p = ::new (buf) Model(std::move(obj));
        this->~Model();                                 // the object in the old buffer ends here
        return p;
      } else {
        return this;                                    // object on the heap: just hand over the pointer
      }
    }
    void destroy() noexcept override {
      if constexpr (Inline) this->~Model();
      else delete this;
    }
  };

  template <class T>
  static constexpr bool fits = sizeof(Model<T, true>) <= Size
                            && alignof(Model<T, true>) <= Align
                            && std::is_nothrow_move_constructible_v<T>;

  alignas(Align) std::byte buf[Size];
  Concept* self;                                        // points into buf or to the heap

public:
  template <class T, class D = std::remove_cvref_t<T>>
    requires (!std::same_as<D, Drawable>) && CanDraw<D>
  Drawable(T&& x) {
    if constexpr (fits<D>) self = ::new (buf) Model<D, true>(std::forward<T>(x));
    else                   self = new Model<D, false>(std::forward<T>(x));
  }
  Drawable(const Drawable& o) : self(o.self->copy_to(buf)) {}
  Drawable(Drawable&& o) noexcept : self(o.self->move_to(buf)) { o.self = nullptr; }
  Drawable& operator=(Drawable o) noexcept {            // a variant of copy-and-swap
    if (self) self->destroy();
    self = o.self->move_to(buf);
    o.self = nullptr;
    return *this;
  }
  ~Drawable() { if (self) self->destroy(); }

  void draw() const { self->draw(); }
};

struct Circle { double r; void draw() const { std::printf("circle %g\n", r); } };
struct Text   { std::string s; void draw() const { std::printf("text %s\n", s.c_str()); } };

int main() {
  Drawable a = Circle{1.5};                     // goes into buf
  Drawable b = Text{"a string that is long enough to allocate"};  // on the heap
  Drawable c = a, d = std::move(b);
  a = d;
  Drawable e = std::move(c);                   // object in buf: moved member by member
  a.draw(); d.draw(); e.draw();
  std::printf("sizeof(Drawable)=%zu\n", sizeof(Drawable));
}
```

ASan and UBSan report nothing in our tests, and `sizeof(Drawable)` is 32: a 24-byte buffer plus a pointer. `Model` gained a template parameter `Inline`, and any given `T` uses only one of the two. `Concept` no longer has a virtual destructor; destruction always goes through `destroy()`: objects in the buffer only have their destructor called, while objects on the heap also have their memory freed.

The following goes through the rules this code relies on, one at a time.

### Creating objects in a byte array

`buf` is a `std::byte` array. When a complete object is created with `new` in the storage of an `unsigned char` or `std::byte` array, and the new object lies entirely within the array, the array is said to **provide storage** for it ([[g:provides-storage]], [[intro.object#3]]). The array's own lifetime is unaffected, and `Drawable` remains a complete, normal object.

`::new (buf) Model(...)` is a **placement new-expression** ([[g:placement-new-expression]]): the extra argument `buf` is passed to the non-allocating `operator new(size_t, void*)`, which returns that address as is and does nothing else ([[new.delete.placement#2]]). The object is then initialized in that storage, and its lifetime begins when initialization completes ([[basic.life#2]]). Writing `::new` bypasses any class-specific `operator new`; `Model` is our own type, so here it is just habit; it only really matters in step 4, where the user type `T` is constructed directly.

### Alignment

[[basic.life#2.1]] requires storage with suitable size and alignment for `T`, and creating an object in misaligned storage is UB ([[basic.align#1]]). A `std::byte` array itself has alignment 1, so `alignas(Align)` is required, and `fits` must check `alignof(Model<T, true>) <= Align`. Checking only the size would construct an `alignas(16)` type at an 8-byte-aligned address.

### Who ends the lifetime

An object placed in `buf` is not destroyed by `Drawable`'s implicit destructor; the compiler only knows there is a `std::byte` array here. Not calling the destructor before the storage is reused or released is allowed by the standard, but that object's destructor then never runs ([[basic.life#6]]), and members such as a `std::string` leak. So `~Drawable` must call `destroy()` explicitly, and `move_to` must destroy the original immediately after moving the object out.

`move_to` returns right after `this->~Model()`, without accessing any member. Accessing members or calling member functions through the original pointer after the lifetime has ended is UB ([[basic.life#7.2]]), but returning a `p` computed earlier is no such access.

### Why store `self` instead of computing it from `buf` each time

`self` is the result of the placement new-expression; it points directly to the newly created `Model`, then converted to a base pointer. If the object were obtained each time with `reinterpret_cast<Concept*>(buf)` instead, the resulting pointer would not point to the `Model`:

- `reinterpret_cast` between object pointers is equivalent to converting to `void*` and then `static_cast` ([[expr.reinterpret.cast#7]]). Converting from `void*`, the result points to an object of the target type only if the originally pointed-to object is **pointer-interconvertible** ([[g:pointer-interconvertible]]) with it; otherwise the pointer value is unchanged ([[expr.static.cast#12]]).
- The array element `buf[0]` and the `Model` placed there are not pointer-interconvertible ([[basic.compound#7]]), so the converted pointer still points to a `std::byte`, and calling `draw()` through it is UB.
- `std::launder` exists for exactly this: as long as there is an object of a similar type within its lifetime at address A, `std::launder(p)` returns a pointer to it ([[ptr.launder#2]]). But `Concept` is a base class subobject of `Model`, and whether it sits at the start of `buf` is up to the implementation, so `std::launder(reinterpret_cast<Concept*>(buf))` may not meet the precondition.

Storing the pointer returned by placement new avoids all of these issues, at the price of 8 more bytes per `Drawable`. The hand-written vtable version below takes another road: it stores only the vtable pointer and recovers the object from the buffer with `launder`.

### Why only types with non-throwing moves go in

The third condition of `fits` is `is_nothrow_move_constructible_v<T>`. `Drawable`'s move constructor is `noexcept`; when the object is on the heap it just hands over the pointer, but when the object is in the buffer it must call `T`'s move constructor. If `T`'s move could throw, the exception would leave a `noexcept` function, and the program calls `std::terminate` ([[except.terminate#1.3]]).

Conversely, dropping `noexcept` from `Drawable`'s move constructor to accommodate such a `T` would make `std::vector<Drawable>` copy elements one by one when it grows, one `clone()` per element. Neither outcome is acceptable, so throwing types can only go on the heap: an object on the heap is moved by handing over a pointer, which never throws. The standard places the same restriction on the small-object optimization of `any`, `move_only_function` and `copyable_function` ([[any.class.general#3]], [[func.wrap.move.class#2]]).

### The outer class can't be copied byte by byte

`self` points into `Drawable`'s own `buf`. An implicit copy constructor would copy `self` as is, so the new object's `self` would point into the old object's buffer, dangling as soon as the old object is destroyed. So copying, moving and assignment must all be hand-written, making the new object reconstruct the `Model` in its own `buf`.

### Measured in our tests

Putting the step 2 version and the SBO version in the same program, with a replacement global `operator new` counting allocations, at `-O2`: construct 1 million `Drawable`s each wrapping a `Circle{double}` (with the `vector` already reserved), call `draw()` on each, then copy the whole `vector`:

```text
heap  sizeof=8   build: allocs=1000000 12–14ms  copy: allocs=1000001
sbo   sizeof=32  build: allocs=0       1–5ms    copy: allocs=1
```

The SBO version makes no allocations at all during construction, and copying the `vector` takes only the one allocation for the new array. The costs are each `Drawable` growing from 8 bytes to 32, and types that don't fit still allocating. The times are ranges over three runs and only indicate orders of magnitude.

`Text` (libc++'s `std::string` is 24 bytes) plus `Model`'s vtable pointer is 32 bytes, which doesn't fit in the 24-byte buffer. The vtable pointer is taking up buffer space, and the next step moves it out.

## Step 4: a hand-written vtable

In the virtual function versions, every `Model<T>` object carries a vtable pointer inside it. The vtable can be moved outside the object: generate a struct of function pointers for each `T`, have `Drawable` store only a pointer to it, and leave the entire buffer to `T` itself.

```cpp run title="vtable.cpp" ok
#include <concepts>
#include <cstddef>
#include <cstdio>
#include <new>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

template <class T>
concept CanDraw = requires(const T& t) { t.draw(); };

class Drawable {
  static constexpr std::size_t Size = 3 * sizeof(void*);
  static constexpr std::size_t Align = alignof(void*);

  struct VTable {                                   // hand-written vtable
    void (*draw)(const void* buf);
    void (*copy)(void* dst, const void* src);
    void (*move)(void* dst, void* src) noexcept;    // afterwards src only needs destroying
    void (*destroy)(void* buf) noexcept;
  };

  template <class T>
  static constexpr bool fits = sizeof(T) <= Size && alignof(T) <= Align
                            && std::is_nothrow_move_constructible_v<T>;

  // buf holds either a T directly or a T*
  template <class T> static T* get(void* b) {
    if constexpr (fits<T>) return std::launder(static_cast<T*>(b));
    else return *std::launder(static_cast<T**>(b));
  }
  template <class T> static const T* get(const void* b) {
    return get<T>(const_cast<void*>(b));
  }

  template <class T>
  static constexpr VTable vtable_for = {
    [](const void* b) { get<T>(b)->draw(); },
    [](void* dst, const void* src) {
      if constexpr (fits<T>) ::new (dst) T(*get<T>(src));
      else ::new (dst) T*(new T(*get<T>(src)));
    },
    [](void* dst, void* src) noexcept {
      if constexpr (fits<T>) ::new (dst) T(std::move(*get<T>(src)));
      else ::new (dst) T*(std::exchange(*std::launder(static_cast<T**>(src)), nullptr));
    },
    [](void* b) noexcept {
      if constexpr (fits<T>) get<T>(b)->~T();
      else delete get<T>(b);
    },
  };

  alignas(Align) std::byte buf[Size];
  const VTable* vt;

public:
  template <class T, class D = std::remove_cvref_t<T>>
    requires (!std::same_as<D, Drawable>) && CanDraw<D>
  Drawable(T&& x) : vt(&vtable_for<D>) {
    if constexpr (fits<D>) ::new (buf) D(std::forward<T>(x));
    else ::new (buf) D*(new D(std::forward<T>(x)));
  }
  Drawable(const Drawable& o) : vt(o.vt) { vt->copy(buf, o.buf); }
  Drawable(Drawable&& o) noexcept : vt(o.vt) { vt->move(buf, o.buf); }
  Drawable& operator=(Drawable o) noexcept {
    vt->destroy(buf);
    vt = o.vt;
    vt->move(buf, o.buf);
    return *this;
  }
  ~Drawable() { vt->destroy(buf); }

  void draw() const { vt->draw(buf); }
};

struct Circle { double r[3]; void draw() const { std::printf("circle %g\n", r[0]); } };
struct Text   { std::string s; void draw() const { std::printf("text %s\n", s.c_str()); } };
struct Poly   { std::vector<double> xs; std::string name;
                void draw() const { std::printf("poly %s\n", name.c_str()); } };

int main() {
  Drawable a = Circle{{1.5}};   // 24 bytes: goes into buf
  Drawable b = Text{"label"};   // libc++'s string is 24 bytes: also goes into buf
  Drawable p = Poly{{1, 2}, "a name long enough to allocate"};  // 48 bytes: on the heap
  Drawable c = a, d = std::move(b), e = p, f = std::move(p);
  a = d;
  a.draw(); c.draw(); e.draw(); f.draw();
  std::printf("sizeof(Drawable)=%zu\n", sizeof(Drawable));
}
```

`sizeof(Drawable)` is still 32, but now the 24-byte `Circle` and `Text` both fit in the buffer. `vtable_for<T>` is a `constexpr` variable template, one per `T`, placed in the read-only data section and shared by all `Drawable`s wrapping the same type, exactly like a compiler-generated vtable. Captureless lambdas convert implicitly to function pointers, which is just what the table needs.

This version differs from the virtual function versions in two places.

First, recovering the object needs `launder`. The object exists only in `buf`, with no separately stored pointer. The result of `static_cast<T*>(b)` still points to the first byte of `buf` ([[expr.static.cast#12]]), and `std::launder` turns it into a pointer to the `T` there ([[ptr.launder#3]]). This time the precondition is met: `T` is a complete object starting right at the beginning of `buf`. For types that don't fit, `buf` holds a `T*` object, and getting it out also requires `launder`.

Second, a moved-from object still has a type. `vt` stays unchanged after a move; the moved-from `Drawable` still contains a moved-from `T` (or a null `T*`), its destructor calls `destroy` as usual, and no empty-state check is needed.

### The cost per call

With Clang 23 `-O2` (arm64), the code generated for `void call_draw(const Drawable& d) { d.draw(); }` in the three versions:

```text
// step 2 (Model on the heap)   // SBO + virtual functions     // hand-written vtable
ldr x0, [x0]       // self       ldr x0, [x0, #24]  // self    ldr x8, [x0, #24]  // vt
ldr x8, [x0]       // vptr       ldr x8, [x0]       // vptr    ldr x1, [x8]       // draw
ldr x1, [x8, #16]  // draw       ldr x1, [x8]       // draw    br  x1
br  x1                           br  x1
```

The first two versions are both three dependent loads: load `self`, load the vtable pointer in the object, load the function pointer from the vtable. In the SBO version the second load falls inside `Drawable`'s own buffer, with better cache locality, but the dependency chain is no shorter. The hand-written vtable saves one load, because the vtable pointer is stored directly in `Drawable`. `draw` sits at offset 16 in the step 2 vtable because the Itanium C++ ABI reserves two slots for the virtual destructor; see [[toolchain/object-layout-and-vtables]].

Going further, the most frequently called function pointer can be stored directly in `Drawable`, so a call reads only once; each one stored makes the object 8 bytes bigger. `function_ref` uses exactly this layout: an invoker function pointer plus a pointer to the object ([[func.wrap.ref.class#1]]).

The cost common to all three versions is the indirect call itself: the compiler can't see the target function at the call site and can't inline it, unless the optimizer can prove `vt` or the dynamic type has only one possibility. Each newly erased type also instantiates a set of `Model<T>` or `vtable_for<T>`, adding object code size and compile time.

## Type erasure in the standard library

| Type | What is erased | Owns the object | Copyable | Empty state | `sizeof` with libc++ in our tests |
|---|---|---|---|---|---|
| `function<R(A...)>` | the type of the callable | yes | yes, requires a copyable target | yes; calling throws `bad_function_call` | 32 |
| `move_only_function<R(A...)>` {{c++23}} | same | yes | no, move-only | yes; calling violates a precondition | not implemented |
| `copyable_function<R(A...)>` {{c++26}} | same | yes | yes | yes; calling violates a precondition | not implemented |
| `function_ref<R(A...)>` {{c++26}} | same | no, only refers | trivially copyable | none | not implemented |
| `any` | any copyable type | yes | yes | yes; `any_cast` throws `bad_any_cast` | 32 |
| `shared_ptr<T>` | the deleter, allocator and actual pointer type | shared | yes (shared ownership) | yes | 16 |
| `pmr::polymorphic_allocator<T>` | the type of the memory resource | no | yes | none | 8 |
| `polymorphic<T>` {{c++26}} | the type of the class derived from `T` | yes | yes, copies by dynamic type | only after being moved from | not implemented |

libc++ in our tests doesn't implement `move_only_function`, `copyable_function`, `function_ref` or `polymorphic` yet, so those cells give no values, and the code below involving them carries no verdict.

### Function wrappers

`std::function` is this page's `Drawable`, with the erased operation being `operator()(A...)` instead of `draw()`. The full comparison of the four function wrappers is in [[func.wrap]]; here we only look at points related to the type erasure implementation.

- `function` requires a copyable target because it is itself copyable, and copying goes through a `clone()`-like virtual function. A move-only lambda (one capturing a `unique_ptr`, say) can't go in, which is why `move_only_function` ([[P0288R9]]) exists.
- `function::operator()` is a `const` member but calls the target in a non-`const` way; `copyable_function` ([[P2548R6]]) makes the `const` in the signature actually constrain how the target is called.
- `function_ref` ([[P0792R14]]) doesn't own the object; it stores only a pointer to the object and an invoker function pointer, never allocates, and suits function parameters.

For `function`'s small-object optimization, the standard only gives a recommended practice: small targets such as an object pointer plus a member function pointer should be stored without dynamic allocation ([[func.wrap.func.con#15]]). For `move_only_function` and `copyable_function`, the standard also notes that the small-object optimization can only be applied to types whose move constructor doesn't throw ([[func.wrap.move.class#2]]).

### `any`

`any` erases the fewest operations: copy, move, destroy, and type queries through `type()` and `any_cast`. It has no call interface, and getting a value out requires naming the exact type, so it is more like a type-safe `void*` than a substitute for polymorphism. It requires stored types to be copy-constructible ([[any.cons#6]]), and its move constructor is `noexcept` ([[any.cons#4]]), so its small-object optimization likewise only applies to types with non-throwing moves ([[any.class.general#3]]). Implementation details are in [[any]].

### The threshold of the small buffer

```cpp run title="std-sbo.cpp" impl
#include <any>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

template <std::size_t N> struct Bytes { char c[N]; void operator()() const {} };
struct ThrowMove {                     // 1 byte, but copying and moving may throw
  ThrowMove() = default;
  ThrowMove(const ThrowMove&) {}
  ThrowMove(ThrowMove&&) {}
  void operator()() const {}
};

template <class W, class F> int count(F f) {
  int before = allocs;
  W w(f);
  return allocs - before;
}

int main() {
  using F = std::function<void()>;
  std::printf("function: 16B=%d 24B=%d throw=%d\n",
              count<F>(Bytes<16>{}), count<F>(Bytes<24>{}), count<F>(ThrowMove{}));
  std::printf("any:      24B=%d 32B=%d throw=%d\n",
              count<std::any>(Bytes<24>{}), count<std::any>(Bytes<32>{}),
              count<std::any>(ThrowMove{}));
}
```

Output with libc++ in our tests:

```text
function: 16B=0 24B=1 throw=1
any:      24B=0 32B=1 throw=1
```

Both are 32 bytes, but the thresholds differ: `any` can store a 24-byte object in place, while `function` can only store 16 bytes. libc++'s `function` puts a wrapper object with virtual functions in its buffer, whose vtable pointer takes 8 bytes, just like the `Model` in step 3; `any` keeps its manager function pointer outside the buffer, as in step 4. The 1-byte `ThrowMove` can only go on the heap in both; libc++'s `function` in our tests checks that copy construction doesn't throw, `any` that move construction doesn't throw. These thresholds are implementation details that differ in libstdc++ and MSVC, and code should not depend on them.

### `shared_ptr`'s deleter

`shared_ptr<T>`'s type doesn't include the deleter; construction with `shared_ptr(p, d)` stores the deleter together with `p`'s actual type in the control block ([[util.smartptr.shared.const#11]]), and destruction calls it through a virtual function of the control block. So a `vector<shared_ptr<int>>` can hold objects released in different ways, and a `shared_ptr<Base>` can correctly destroy a derived object even when `Base` has no virtual destructor. This and measurements of the cost are in [[topics/ownership-and-smart-pointers]]. Contrast `unique_ptr<T, D>`: the deleter is part of the type, not erased, and so there is no indirect call.

### `pmr::memory_resource`: the virtual interface kind

`std::pmr::memory_resource` is an ordinary abstract base class, and concrete resources (`monotonic_buffer_resource`, `unsynchronized_pool_resource`, users' own resources) all inherit from it ([[mem.res.class]]). It is itself classic intrusive polymorphism, with the public non-virtual `allocate` calling the private virtual `do_allocate`, the [[patterns/nvi|non-virtual interface]] technique.

Type erasure happens one level up: `polymorphic_allocator<T>` stores only a `memory_resource*`, so a `pmr::vector<int>` is the same type whatever resource it uses. An ordinary `vector<int, MyAlloc>` writes the allocator into the type. In our tests `pmr::vector<int>` is 32 bytes, and the 8 bytes more than `vector<int>` are that pointer. Details in [[topics/allocators-and-pmr]].

This shows type erasure and virtual functions aren't opposites: a library author can require users to inherit an interface, and then hide the concrete type behind a pointer at the point of use. The difference is only whether the user's type needs to know about the interface.

### `polymorphic`: value semantics for a closed hierarchy {{c++26}}

`std::polymorphic<T>` ([[P3019R14]]) solves the other half of the problem. It requires the object's type to derive from `T` ([[polymorphic.ctor#12]]), so it is not non-intrusive; but like this page's `Drawable`, it provides value semantics:

```cpp
struct Shape {
  virtual ~Shape() = default;
  virtual void draw() const = 0;
};
struct Circle : Shape { double r = 1; void draw() const override; };

std::vector<std::polymorphic<Shape>> v;
v.emplace_back(std::in_place_type<Circle>);
auto w = v;          // each element copied by dynamic type, no virtual clone() needed
w[0]->draw();
```

libc++ in our tests doesn't implement `polymorphic` yet, so this code has not been compiled. At construction, `polymorphic` records the actual type `Circle`, and copying calls `Circle`'s copy constructor ([[polymorphic.ctor#8]]); what it erases is exactly the derived class's type. Its move constructor is allowed to move-construct a new object rather than take over the pointer ([[polymorphic.ctor#10]]), leaving room for the small-object optimization. The full rules are in [[polymorphic]].

When a class hierarchy already exists, `polymorphic<Base>` is much simpler than hand-written type erasure; non-intrusive designs like `Drawable` are needed only when types come from everywhere and can't be modified.

## Traps

### The constructor template hijacks copying

If the `!same_as<..., Drawable>` constraint from step 2 is removed, the problem is that `Drawable` itself has `draw()`, so it satisfies `CanDraw`:

```cpp run title="hijack.cpp"
#include <cstdio>
#include <memory>
#include <type_traits>
#include <utility>

struct Circle { void draw() const { std::puts("circle"); } };

class Drawable {
  struct Concept {
    virtual ~Concept() = default;
    virtual void draw() const = 0;
    virtual std::unique_ptr<Concept> clone() const = 0;
  };
  template <class T> struct Model final : Concept {
    T obj;
    template <class U> explicit Model(U&& u) : obj(std::forward<U>(u)) {}
    void draw() const override { obj.draw(); }
    std::unique_ptr<Concept> clone() const override { return std::make_unique<Model>(obj); }
  };
  std::unique_ptr<Concept> self;
public:
  template <class T>                         // doesn't exclude Drawable itself
    requires requires(const T& t) { t.draw(); }
  Drawable(T&& x)
      : self(std::make_unique<Model<std::remove_cvref_t<T>>>(std::forward<T>(x))) {}
  Drawable(const Drawable& o) : self(o.self->clone()) {}
  Drawable(Drawable&&) noexcept = default;
  void draw() const { self->draw(); }
};

int main() {
  Drawable a = Circle{};
  const Drawable& ca = a;
  Drawable b = ca;   // const lvalue: the copy constructor is chosen
  Drawable c = a;    // non-const lvalue: the template is chosen, T = Drawable&
  c.draw();
}
```

`Drawable c = a;` has two candidates: the copy constructor `Drawable(const Drawable&)`, and the `Drawable(Drawable&)` instantiated from the template. Both are reference bindings; the latter binds to a less cv-qualified type, so its implicit conversion sequence is better ([[over.ics.rank#3.2.6]]). The rule preferring non-templates ([[over.match.best.general#2.4]]) only applies when the two candidates are equally good, so the template wins. A template constructor is never a copy constructor ([[class.copy.ctor#1]]), but that doesn't stop it from beating the copy constructor in overload resolution.

The template then constructs a `Model<Drawable>`, whose member `obj` is initialized with `std::forward<U>(u)`, where `u` is again a non-`const` `Drawable&`, so the template is chosen again, constructing another `Model<Drawable>`... and the recursion never ends. In our tests it overflows the stack at run time, and ASan reports `stack-overflow`, with repeated `make_unique<Drawable::Model<Drawable>, Drawable&>` in the call stack.

So a forwarding-reference constructor template must always exclude the outer class itself; the standard library's `function` and `any` both carry this constraint ([[func.wrap.func.con#9]], [[any.cons#6]]).

### A type with a throwing move in the small buffer

Remove the `is_nothrow_move_constructible_v<T>` condition from `fits` in `sbo.cpp`, and put in a type whose move constructor throws:

```cpp
struct Flaky {
  Flaky() = default;
  Flaky(const Flaky&) = default;
  Flaky(Flaky&&) { throw 42; }      // the move may throw (here it always does)
  void draw() const {}
};

int main() {
  Flaky f;
  Drawable a = f;                   // copied into buf
  try { Drawable b = std::move(a); } catch (int) { std::puts("caught"); }
}
```

The `catch` never runs. The exception is thrown from the `noexcept` `move_to`, and the search for a handler leaves a non-throwing function, so the program calls `std::terminate` ([[except.terminate#1.3]]). In our tests it prints `libc++abi: terminating due to uncaught exception of type int`. The program's behavior is well defined; it is just that the behavior is termination.

### Calling an empty wrapper

```cpp run title="empty.cpp" ok
#include <cstdio>
#include <functional>

int main() {
  std::function<void()> f;            // empty
  try {
    f();
  } catch (const std::bad_function_call& e) {
    std::puts("bad_function_call");
  }
}
```

Calling an empty `std::function` throws `bad_function_call` ([[func.wrap.func.inv#2]]), so every call implies a null check. `move_only_function` and `copyable_function` instead make non-emptiness a precondition ([[func.wrap.move.inv#2]], [[func.wrap.copy.inv#2]]), and violating a precondition is UB ([[structure.specifications#3.4]]). This saves the null check and allows `noexcept` signatures, at the cost of no protection at all against empty calls.

Your own `Drawable` has to decide this too. In the step 2 and 3 versions, `self` is null after a move, and calling `draw()` dereferences a null pointer; `draw()` could check and throw, or, like the later standard wrappers, make non-emptiness a precondition. What matters is documenting it.

### `function_ref` dangling

```cpp
#include <functional>

int main() {
  int base = 40;
  std::function_ref<int(int)> r = [base](int x) { return base + x; };
  return r(2);   // UB: the temporary lambda was destroyed at the end of the previous line
}
```

When `function_ref` is constructed from a callable object, it stores `addressof(f)` ([[func.wrap.ref.ctor#8]]) without copying the object. The lambda above is a temporary destroyed at the end of the full-expression declaring `r`, and the pointer in `r` dangles immediately. libc++ in our tests doesn't implement `function_ref` yet, so this code has not been compiled and carries no verdict.

`function_ref`, like `std::string_view`, is a borrowing type: safe as a function parameter, because the argument lives for the whole call; as a variable or member, the referenced object must be guaranteed to outlive it. The full picture of this kind of problem is in [[topics/dangling-references]].

## When to use it

| Need | Choice |
|---|---|
| A closed set of types, all known in advance | `std::variant` + `std::visit`; see [[patterns/visitor\|the visitor page]] |
| Your own class hierarchy needing polymorphism | virtual functions; `polymorphic<Base>` when value semantics are needed |
| Concrete types known at compile time, inlining wanted | templates with concepts; see [[patterns/crtp\|CRTP]], [[patterns/policy-based-design\|policy-based design]] |
| Open types from everywhere that can't be modified, stored by value | type erasure (the standard library's or hand-written) |
| Just passing a callback that won't be used after the call | `function_ref` or a template parameter, not `const std::function&` |
| Storing a callback to call later | `move_only_function` (when copying isn't needed), `copyable_function` or `function` |
| Storing arbitrary values whose type is known when retrieving | `any` |

The cost of hand-written type erasure isn't the first version, but getting copying, moving, the small buffer and exception safety all right. When the erased interface has only one call operation, just use a standard library function wrapper; hand-writing is worth it only when the interface has several operations (such as `draw` plus `bounds`). A comparison of the forms in which strategy objects can be passed is in [[patterns/strategy]].

## Questions

!!! question "1"
    What happens if `sbo.cpp`'s `Drawable` doesn't hand-write its copy constructor but uses `Drawable(const Drawable&) = default;`, and one object wrapping a `Circle` is copied into another?

<details markdown="1">
<summary>Answer</summary>

The defaulted copy constructor copies member by member: `buf` is copied byte by byte (copying a `std::byte` array doesn't create a `Model` object in the new `buf`), and `self` is copied as is, still pointing into the source object's `buf`. Then both `Drawable`s' destructors call `destroy()` on the same `Model`, the second time calling a member function on an object whose lifetime has ended, which is UB ([[basic.life#7.2]]). If the source is destroyed first, the copy's `self` dangles immediately. An object in the buffer can only be recreated at a new address through its own copy constructor, so classes with a small buffer must hand-write copying and moving.
</details>

!!! question "2"
    `any` and this page's `sbo.cpp` `Drawable` both use a 24-byte buffer. Why can libc++'s `any` store a 24-byte object in place, while `sbo.cpp` can only store 16 bytes?

<details markdown="1">
<summary>Answer</summary>

`sbo.cpp` constructs a `Model<T, true>` in the buffer, which has virtual functions and so carries an 8-byte vtable pointer inside the object, leaving only 16 bytes for `T`. `any` doesn't put an object with virtual functions in the buffer; it keeps the type-specific operations in a function (pointer) outside the object, giving the whole buffer to `T`, the same as step 4's hand-written vtable. libc++'s `function` uses the former layout, which is why in our measurements it can only store 16-byte targets in place.
</details>

!!! question "3"
    A function only calls the callback passed to it synchronously, internally. Should the signature be `void each(const std::function<void(int)>& f)`, `void each(std::function_ref<void(int)> f)`, or `template <class F> void each(F&& f)`?

<details markdown="1">
<summary>Answer</summary>

`const std::function&` is the worst: when the caller passes a lambda, a temporary `function` must be constructed first, possibly allocating, and calls also go through an indirect call and a null check. `function_ref` doesn't allocate and is trivially copyable, calls cost just one extra indirection, and `each` can live in a `.cpp` file compiled separately, which suits interfaces that don't want their implementation in a header. A template parameter has no indirection at all and the lambda can be inlined, but each callback type instantiates its own `each`, and the implementation must live in a header. The callback isn't stored, so there is no need for an owning `function` or `move_only_function`.
</details>
