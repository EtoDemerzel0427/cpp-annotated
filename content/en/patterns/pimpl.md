---
title: Pimpl and the compilation firewall
summary: "Hiding a class's data members behind a pointer to an incomplete type: the recompilation cascades and shared-library ABI problems it solves, where the special members of a unique_ptr implementation must be defined, const propagation, copying and the empty state after a move, C++26's std::indirect, fast pimpl, and its run-time costs and alternatives."
tags: pimpl, compilation firewall, ABI, incomplete types, idiom
updated: 2026-10-19
---

!!! tldr
    - When a class's private data members are written in its header, their types, sizes and offsets are compiled into every translation unit that includes it. Change one private member and every user must be recompiled; if the user lives in another shared library, not recompiling means reading and writing misaligned memory.
    - Pimpl moves the data members into an `Impl` defined only in the `.cpp` file and leaves a single pointer in the header. The outer class's `sizeof` is fixed from then on, and changes to `Impl` don't affect users.
    - With `unique_ptr<Impl>`, the destructor, every constructor and the move assignment instantiate `delete`, so they must be defined in the `.cpp` file after `Impl` is complete, even if they are just `= default`.
    - The pointer doesn't propagate `const`, doesn't deep-copy automatically, and leaves a null pointer behind after a move. All three must be handled by hand; C++26's `std::indirect<Impl>` solves the first two at once.
    - The costs are one heap allocation per object, one extra indirection per access, and no inlining across translation units. Fast pimpl uses a fixed-size buffer inside the object to avoid the allocation, at the price of writing the size constants into the ABI.

## Change one private member, recompile the whole project

A class defined the usual way:

```cpp title="widget.h"
#pragma once
#include <map>
#include <regex>
#include <string>
#include <vector>

class Widget {
public:
  explicit Widget(std::string pattern);
  bool match(const std::string& s) const;
  int hits() const { return hits_; }
private:
  std::regex re_;
  std::map<std::string, std::vector<double>> cache_;
  mutable int hits_ = 0;
};
```

Users only call `match` and `hits` and never touch `re_` or `cache_`. Yet every `.cpp` that includes `widget.h` has to parse `<regex>` and `<map>`, and its object code depends on `Widget`'s layout: putting a `Widget` on the stack requires `sizeof(Widget)`, and the inline `hits()` requires the offset of `hits_`.

This follows directly from the language rules. Wherever a type must be complete (defining an object of that type, `sizeof`, member access), the class definition must be reachable ([[basic.def.odr#14]]). The definition includes the private members; `private` only restricts whether names can be accessed, not whether the layout is visible to users.

We ran a small experiment: `widget.cpp` plus 20 users each including `widget.h`, built with a Makefile using `-MMD` dependency tracking, `-O2`, single-threaded. After adding a private member `std::vector<int> extra_;` to `Widget`:

| | Translation units recompiled | Incremental build time | Preprocessed lines of one user | Compile time of one user |
|---|---|---|---|---|
| Members in `widget.h` | 21 | 7.4 s | 56070 | 0.32 s |
| pimpl, members in `widget.cpp` | 1 | 1.0 s | 27691 | 0.16 s |

The pimpl version's header includes only `<memory>` and `<string>`, so each user also compiles faster. Changes to implementation details are contained in the single file `widget.cpp`, which is where the alternative name **compilation firewall** comes from.

## Shared libraries: `sizeof` is compiled into the caller

The second problem is more serious. Suppose `Widget` is provided by a shared library, and the application was compiled against the v1 header. When the library is upgraded to v2, a private array is added to `Widget`:

<div class="compare" markdown="1">

```cpp title="v1.h"
class Widget {
public:
  Widget();
  int get() const;
  static unsigned lib_size();
private:
  int a_;
};
```

```cpp title="v2.h"
class Widget {
public:
  Widget();
  int get() const;
  static unsigned lib_size();
private:
  long log_[4];   // new in v2
  int a_;
};
```

</div>

```cpp title="app.cpp"
#include <cstdio>
#include "v1.h"
int main() {
  int guard = 7;
  Widget w;                       // reserves 4 bytes on the stack, per v1
  std::printf("app sizeof=%zu lib sizeof=%u get=%d guard=%d\n",
              sizeof(Widget), Widget::lib_size(), w.get(), guard);
}
```

Not a word of the public interface changed, and neither did the mangled function names, so the v2 `.dylib` can replace v1 directly and dynamic linking succeeds. But `app` reserved only 4 bytes on the stack, while the constructor in the library writes 40 bytes according to v2's layout. Run with `-fsanitize=address` in our tests, ASan reports `stack-buffer-overflow`, with a `WRITE of size 32` in the library's `Widget::Widget()`; without ASan the process just segfaults.

The standard does not know shared libraries exist. From its point of view, `Widget` has two different definitions in the same program, which violates [[basic.def.odr#16]] and is **ill-formed, no diagnostic required** (IFNDR: the program is invalid, but neither compiler nor linker has to report it). In practice we say the change breaks the **ABI** (application binary interface, the binary-level contract including type sizes, member offsets, calling conventions and symbol names); see [[toolchain/linking-and-symbols]].

Turn the same class into a pimpl, and the header contains only a pointer:

```cpp title="p.h"
#include <memory>
class Widget {
public:
  Widget();
  ~Widget();
  int get() const;
  static unsigned lib_size();
private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
```

The library defines `Impl` in its `.cpp`, and v2 adds the same array to `Impl`. Repeating the experiment in our tests, without recompiling the application, both library versions work: `sizeof(Widget)` is always 8, while `sizeof(Widget::Impl)` goes from 4 to 40, known only to the library.

What pimpl fixes is the size and layout of the outer class. Public member function signatures and the virtual function table are still part of the ABI, and changing them breaks compatibility just the same; layout issues are covered in [[toolchain/object-layout-and-vtables]].

## The classic implementation

```cpp title="widget.h"
#pragma once
#include <memory>
#include <string>

class Widget {
public:
  explicit Widget(std::string name);
  ~Widget();
  Widget(const Widget&);
  Widget& operator=(const Widget&);
  Widget(Widget&&) noexcept;
  Widget& operator=(Widget&&) noexcept;

  void add(int x);
  int total() const;
  const std::string& name() const;

private:
  struct Impl;                    // declared only, not defined
  std::unique_ptr<Impl> impl_;
};
```

```cpp title="widget.cpp" ok
#include "widget.h"
#include <numeric>
#include <vector>

struct Widget::Impl {             // the private members all move here
  std::string name;
  std::vector<int> items;
};

Widget::Widget(std::string name)
    : impl_(std::make_unique<Impl>(std::move(name))) {}
Widget::~Widget() = default;      // Impl is complete from here on

Widget::Widget(const Widget& o)   // deep copy
    : impl_(o.impl_ ? std::make_unique<Impl>(*o.impl_) : nullptr) {}
Widget& Widget::operator=(const Widget& o) {
  if (this != &o) *this = Widget(o);   // copy first, then commit with a move
  return *this;
}
Widget::Widget(Widget&&) noexcept = default;
Widget& Widget::operator=(Widget&&) noexcept = default;

void Widget::add(int x) { impl_->items.push_back(x); }
int Widget::total() const {
  return std::accumulate(impl_->items.begin(), impl_->items.end(), 0);
}
const std::string& Widget::name() const { return impl_->name; }
```

```cpp title="main.cpp" ok
#include "widget.h"
#include <cstdio>

int main() {
  Widget a("a");
  a.add(1); a.add(2);
  Widget b = a;                   // copies into an independent Impl
  b.add(10);
  Widget c = std::move(b);        // only hands over the pointer
  std::printf("%s %d %d %zu\n", a.name().c_str(), a.total(), c.total(),
              sizeof(Widget));
}
```

Run under ASan and UBSan in our tests, it prints `a 3 13 8` with no reports. `Impl` is a nested class of `Widget`, so it can access `Widget`'s private members; conversely, `Widget`'s member functions access the implementation through `impl_->`.

None of the six special members in the header can be omitted, and none can be `= default` inside the class. The next section explains why.

## Where the special members must be defined

`struct Impl;` only declares `Impl`, so in the header it is an **incomplete type** ([[g:incomplete-type]]): known to be a class, but with unknown size and members. Pointers to incomplete types can be stored and passed around, and `unique_ptr` also allows `T` to be incomplete ([[unique.ptr.general#4]]). The problem is destruction.

### `delete` requires a complete type

The default deleter of `unique_ptr<Impl>` is `default_delete<Impl>`, whose `operator()` requires `T` to be complete ([[unique.ptr.dltr.dflt#3]]) and then executes `delete ptr`. Writing `delete` directly is the same:

```cpp run title="delete-incomplete.cpp" error
struct Impl;
void f(Impl* p) { delete p; }   // error: Impl is incomplete
```

!!! std
    If the object being deleted has incomplete class type at the point of deletion, the program is ill-formed. ([[expr.delete#4]])

    Deleting an object whose type is incomplete at that point makes the program ill-formed.

This is the C++26 rule ([[P3144R2]]). Previously it was UB only if the complete type had a non-trivial destructor or a class-specific `operator delete`; compilers usually only warned, and the program silently skipped the destructor. Clang 23 gives a `-Wdelete-incomplete` warning for the example above with `-std=c++23`, and the error `cannot delete pointer to incomplete type 'Impl'` with `-std=c++2c`. `default_delete`'s completeness requirement is older; libc++ in our tests enforces it in `operator()` with `static_assert(sizeof(_Tp) >= 0, ...)`, so the `unique_ptr` version has always been a compile error.

### Which members instantiate `~unique_ptr<Impl>`

`~unique_ptr<Impl>` is a member function of a class template and is instantiated only when its definition is needed ([[temp.inst]]). The following rules determine which members of `Widget` need it:

1. After executing its body, `Widget`'s destructor calls the destructor of each data member ([[class.dtor#13]]). So the definition of `~Widget` instantiates `~unique_ptr<Impl>`.
2. A non-delegating constructor **potentially invokes** ([[g:potentially-invoked]]) the destructor of each subobject ([[class.base.init#14]]), because if an exception is thrown halfway through construction, the members already constructed must be destroyed. So the definition of every constructor, including parameterized, copy and move constructors, instantiates it as well.
3. A potentially invoked destructor counts as an odr-use ([[basic.def.odr#9]]). Move assignment destroys `*this`'s old `Impl`, and copy assignment and copy construction use `Impl`'s copy constructor; they too require a complete type.
4. A special member implicitly declared, or written `= default` inside the class, is not defined at the class definition but implicitly defined where it is first odr-used ([[dcl.fct.def.default#5]]). That place is usually in a user's `.cpp`, where `Impl` is incomplete.

Rule 4 is the source of most errors. Without a declared destructor, the implicit `~Widget` is defined in the user's code:

```cpp run title="implicit-dtor.cpp" error
#include <memory>
class Widget {
public:
  Widget();
  int value() const;
private:
  struct Impl;
  std::unique_ptr<Impl> impl;
};
void user() { Widget w; }   // error: ~Widget is implicitly defined here
```

The libc++ diagnostic in our tests is about applying `sizeof` to the incomplete type `Widget::Impl`, and the last entry of the instantiation chain points at `user()`: `in implicit destructor for 'Widget' first required here`.

The fix is to only declare in the header and write `= default` in the `.cpp` after `Impl`'s definition. A function written `= default` after its first declaration is user-provided, and it is defined at the point where `= default` is written ([[dcl.fct.def.default#5]]).

| Member | Defaulted in class, or not declared | Reason |
|---|---|---|
| Destructor | defined at the point of use, error | [[class.dtor#13]] |
| Any constructor (body defined in class) | error | [[class.base.init#14]] |
| Default constructor `= default` | defined at the point of use, error | same |
| Move constructor `= default` | defined at the point of use, error | same |
| Move assignment `= default` | defined at the point of use, error | destroys the old `Impl` |
| Copy constructor, copy assignment | implicitly declared as deleted, because `unique_ptr` is not copyable | deep copy must be written by hand |

Every error in the table was verified with Clang 23; for example, an in-class `Widget(Widget&&) = default;` fails at `Widget b(std::move(a));` with `in defaulted move constructor for 'Widget' first required here`. A member that is declared but never used is never defined and so never errors, but a header cannot assume users won't use it.

The full derivation and the details of `make_unique` are in the section on incomplete types in [[topics/ownership-and-smart-pointers]].

!!! tip "Why `shared_ptr<Impl>` doesn't need any of this"
    `shared_ptr` requires the type to be complete at construction ([[util.smartptr.shared.const#4]]) and records how to delete in the control block; destruction afterwards no longer needs `T` to be complete. So with a `shared_ptr<Impl>` member, the implicit destructor can stay in the header. But it makes two copied `Widget`s share the same `Impl`, which is discussed below.

## `const` does not pass through the pointer

```cpp run title="const-leak.cpp" ok
#include <memory>
#include <vector>

class Widget {
public:
  Widget();
  ~Widget();
  int total() const;
private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

struct Widget::Impl { std::vector<int> items; };
Widget::Widget() : impl_(std::make_unique<Impl>()) {}
Widget::~Widget() = default;

int Widget::total() const {
  impl_->items.clear();           // compiles: const does not reach *impl_
  return 0;
}
int main() { Widget w; return w.total(); }
```

The program is well-formed, yet `total()` is a `const` member function that empties the object's contents. Inside a `const` member function, `impl_` has type `const unique_ptr<Impl>`, and `unique_ptr`'s `operator->` is a `const` member function returning `Impl*` ([[unique.ptr.single.observers#6]]). The pointer itself is `const`; the object it points to is not.

With the data members written directly in the class, the compiler rejects such code. Moving them behind a pointer loses that protection. The fix is to wrap the pointer so that a `const` wrapper only hands out `const Impl*`:

```cpp run title="deep-const.cpp" error
#include <memory>
#include <utility>
#include <vector>

template <class T>
class deep_const_ptr {            // hand-written const-propagating wrapper
  std::unique_ptr<T> p_;
public:
  deep_const_ptr() = default;
  explicit deep_const_ptr(std::unique_ptr<T> p) noexcept : p_(std::move(p)) {}
  T* operator->() noexcept { return p_.get(); }
  const T* operator->() const noexcept { return p_.get(); }
  T& operator*() noexcept { return *p_; }
  const T& operator*() const noexcept { return *p_; }
  explicit operator bool() const noexcept { return static_cast<bool>(p_); }
};

class Widget {
public:
  Widget();
  ~Widget();
  int total() const;
private:
  struct Impl;
  deep_const_ptr<Impl> impl_;
};

struct Widget::Impl { std::vector<int> items; };
Widget::Widget() : impl_(std::make_unique<Impl>()) {}
Widget::~Widget() = default;

int Widget::total() const {
  impl_->items.clear();           // error: impl_-> returns const Impl*
  return 0;
}
int main() { Widget w; return w.total(); }
```

`deep_const_ptr`'s implicit destructor instantiates `~unique_ptr<Impl>`, but it is only used at the definition of `~Widget`, where `Impl` is complete, so the rules of the previous section are unchanged.

Version 2 of the Library Fundamentals TS provides `std::experimental::propagate_const<std::unique_ptr<Impl>>` for the same purpose ([[N4388]]). libc++ in our tests has `<experimental/propagate_const>`, and with it the example above fails on the same line with the same error. It never made it into the standard, so portable code usually writes a wrapper like the one above. Another common approach uses no wrapper, accessing the implementation only through a pair of private accessors `Impl& impl()` and `const Impl& impl() const`, with a convention not to use `impl_` directly, enforced by code review.

## Copying, moving and the empty state

### Deep copy

`unique_ptr` is not copyable, so `Widget`'s implicit copy constructor is defined as deleted. For `Widget` to copy like an ordinary value, the copy constructor must copy `*impl_`, not the pointer:

```cpp
Widget::Widget(const Widget& o)
    : impl_(o.impl_ ? std::make_unique<Impl>(*o.impl_) : nullptr) {}
Widget& Widget::operator=(const Widget& o) {
  if (this != &o) *this = Widget(o);
  return *this;
}
```

Copy assignment first constructs a complete copy, then commits it with a non-throwing move assignment. If constructing the copy fails, `*this` is untouched: the strong exception safety guarantee; see [[topics/exception-safety]]. The price is a new `Impl` allocation on every assignment; if `Impl`'s copy assignment can reuse existing memory and the basic guarantee is enough, it can be written as `*impl_ = *o.impl_` (provided neither side is null).

### Consequences of declaring only the destructor

A pimpl class that declares only a destructor and no move operations can be neither copied nor moved. A user-declared destructor prevents the implicit declaration of the move constructor ([[class.copy.ctor#8]]), so `std::move(a)` falls back to the copy constructor, which is deleted because of `unique_ptr`. That is why the header above declares all five members.

### The null pointer after a move

Move construction just hands over the pointer, leaving the moved-from object with a null `impl_`. Calling its member functions afterwards dereferences a null pointer:

```cpp title="moved.cpp" ub
#include "widget.h"
#include <cstdio>
int main() {
  Widget b("b");
  Widget c = std::move(b);
  std::printf("%d\n", b.total());   // b.impl_ is null
}
```

UBSan in our tests reports `member access within null pointer of type 'Widget::Impl'`, followed by an ASan SEGV report.

There are three ways to handle this. The first is the convention that a moved-from object may only be assigned to or destroyed, which matches the standard library's convention for most types. The second is to check `impl_` in every member function, adding branches. The third is to have the move constructor allocate a new `Impl` too, so it is never null, but then the move is no longer `noexcept`, and `std::vector` falls back to copying when it grows. The first is the most common; the `o.impl_ ? … : nullptr` in the copy constructor exists so that a moved-from object can still be copied and assigned.

### A shared immutable implementation

If `Impl` is never modified after construction, `std::shared_ptr<const Impl>` works: copying a `Widget` only increments a reference count, and two objects sharing the same `Impl` is unobservable. As soon as `Impl` is mutable, sharing breaks value semantics: modifying one object changes the other.

This structure shows up in standard library implementations too. In libc++ in our tests, `std::locale` has a single `__imp*` member and `sizeof(std::locale)` is 8; `std::filesystem::directory_iterator` has a single `shared_ptr` to internal state and is 16 bytes.

## C++26's `std::indirect`

`std::indirect<T>` holds a `T` on the heap but behaves like a value of type `T` ([[P3019R14]]). Using it as the pimpl holder:

```cpp title="widget.h"
#include <memory>
#include <string>
class Widget {
public:
  explicit Widget(std::string name);
  ~Widget();
  Widget(const Widget&);
  Widget& operator=(const Widget&);
  Widget(Widget&&) noexcept;
  Widget& operator=(Widget&&) noexcept;
  int total() const;
private:
  struct Impl;
  std::indirect<Impl> impl_;
};
```

```cpp title="widget.cpp"
#include "widget.h"
#include <numeric>
#include <vector>
struct Widget::Impl { std::string name; std::vector<int> items; };

Widget::Widget(std::string name) : impl_(std::in_place, std::move(name)) {}
Widget::~Widget() = default;
Widget::Widget(const Widget&) = default;            // indirect does the deep copy
Widget& Widget::operator=(const Widget&) = default;
Widget::Widget(Widget&&) noexcept = default;
Widget& Widget::operator=(Widget&&) noexcept = default;

int Widget::total() const {
  // impl_->items.clear();                          // error: *impl_ is const Impl
  return std::accumulate(impl_->items.begin(), impl_->items.end(), 0);
}
```

libc++ in our tests does not implement `std::indirect` yet (`no template named 'indirect' in namespace 'std'`), so the code above has not been compiled and carries no verdict. According to the draft, it differs from `unique_ptr<Impl>` as follows:

- The copy constructor constructs a new `T` from `*other` ([[indirect.ctor#9]]), and copy assignment likewise ([[indirect.assign#2]]), so `Widget`'s copy members can simply be `= default`.
- `operator->` of a `const indirect<T>` returns `const_pointer` ([[indirect.obs]]), so `const` propagates automatically, with no hand-written wrapper.
- The default constructor also allocates and constructs a `T` ([[indirect.ctor#5]]), so there is no empty state. After being moved from, it becomes **valueless** ([[g:valueless]], [[indirect.general#1]]), and dereferencing it then violates a precondition ([[indirect.obs#1]]). Compared with `unique_ptr`'s null pointer, the only addition is that `valueless_after_move()` can be queried.
- `T` may be incomplete ([[indirect.general#6]]), but the destructor requires `T` to be complete ([[indirect.dtor#1]]), and the copy constructor requires `is_copy_constructible_v<T>` ([[indirect.ctor#8]]), which itself requires a complete type. So the rules of the previous section about where special members go still apply: the header must still declare all five members and `= default` them in the `.cpp`.

| | `unique_ptr<Impl>` | `deep_const_ptr<Impl>` (hand-written) | `indirect<Impl>` |
|---|---|---|---|
| `const` propagation | no | yes | yes |
| Copying | hand-written deep copy | hand-written deep copy | `= default` is a deep copy |
| After a move | null pointer | null pointer | valueless, queryable |
| Default construction | may be null | may be null | always allocates |
| Special members defined in `.cpp` | required | required | required |
| Availability | C++11 | anywhere | C++26, not implemented in libc++ in our tests |

## Fast pimpl: a version without allocation

If one heap allocation per object is unacceptable, you can reserve a fixed-size, aligned byte array inside the object and construct `Impl` in place there:

```cpp title="widget.h"
#pragma once
#include <cstddef>
#include <string>

class Widget {
public:
  explicit Widget(std::string name);
  ~Widget();
  Widget(const Widget&);
  Widget& operator=(const Widget&);
  void add(int x);
  int total() const;
private:
  struct Impl;
  static constexpr std::size_t impl_size = 48, impl_align = 8;
  alignas(impl_align) std::byte buf_[impl_size];   // Impl is constructed in place here
  Impl& impl() noexcept;
  const Impl& impl() const noexcept;
};
```

```cpp title="widget.cpp" ok
#include "widget.h"
#include <new>
#include <numeric>
#include <vector>

struct Widget::Impl {
  std::string name;
  std::vector<int> items;
};

Widget::Impl& Widget::impl() noexcept {
  return *std::launder(reinterpret_cast<Impl*>(buf_));
}
const Widget::Impl& Widget::impl() const noexcept {
  return *std::launder(reinterpret_cast<const Impl*>(buf_));
}

Widget::Widget(std::string name) { ::new (buf_) Impl{std::move(name), {}}; }
Widget::~Widget() {
  static_assert(sizeof(Impl) <= impl_size, "enlarge impl_size");
  static_assert(alignof(Impl) <= impl_align, "enlarge impl_align");
  impl().~Impl();
}
Widget::Widget(const Widget& o) { ::new (buf_) Impl(o.impl()); }
Widget& Widget::operator=(const Widget& o) {
  impl() = o.impl();
  return *this;
}
void Widget::add(int x) { impl().items.push_back(x); }
int Widget::total() const {
  return std::accumulate(impl().items.begin(), impl().items.end(), 0);
}
```

With a `main.cpp` that copies, assigns and prints the results, it runs under ASan and UBSan without reports in our tests, and `sizeof(Widget)` is 48. A few details:

- A `std::byte` array can **provide storage** for objects created in it ([[intro.object#3]]). But the array and the `Impl` newly created in it are not pointer-interconvertible ([[basic.compound#7]]): the pointer from `reinterpret_cast` still points to the array's bytes, and only `std::launder` turns it into a pointer to the `Impl` ([[ptr.launder]]). The alternative is to store the pointer returned by placement new as a member, at the cost of 8 more bytes.
- The `static_assert` can only be written where `Impl` is complete; applying `sizeof` to `Impl` in the header is ill-formed ([[expr.sizeof#1]]). `Impl` and both constants are private, so the check goes into a member function; the destructor is always defined, so it is the safest place. Change `impl_size` to 40 and we get `static assertion failed due to requirement 'sizeof(Widget::Impl) <= impl_size': enlarge impl_size`.
- `std::aligned_storage` is deprecated from C++23 ([[P1413R3]], [[depr.meta.types]]); an `alignas`-qualified `std::byte` array replaces it.

This keeps the first benefit: the header no longer includes `<vector>`, and as long as `Impl` stays within 48 bytes, users don't need recompiling. The second benefit is diminished: 48 and 8 are written into the header and become part of the ABI. When `Impl` outgrows the reserved size, the only option is to change the constants, which breaks the ABI. The constants also depend on the standard library implementation: 48 is the size of `std::string` (24 bytes) plus `std::vector<int>` (24 bytes) in libc++ in our tests, while libstdc++'s `std::string` is 32 bytes, so the same header has to give different values per platform.

It also loses the cheap move of the pointer version: moving a `Widget` moves every member of `Impl`. The example declares only copy operations, so there are no implicit move operations ([[class.copy.ctor#8]]), and `std::move(w)` copies. The exception safety of copy assignment is only whatever `Impl`'s own copy assignment provides.

## Costs

### One allocation, one indirection

We compared two classes containing just one `int` at `-O2`, with member functions defined in another translation unit, one storing directly and one using `unique_ptr<Impl>`, measuring 10 million objects each:

| | Construct + destroy | Sequential `get()` over all | Traversal after shuffling the `vector` |
|---|---|---|---|
| Direct storage | 1.5 ns | 0.9 ns each | 1.0 ns each |
| pimpl | 24 ns | 1.2 ns each | 7.8 ns each |

The construction gap comes from `operator new` and `operator delete`. Sequential traversal shows little difference, because `Impl`s allocated in order also happen to be adjacent on the heap; after shuffling the `vector<Widget>`, each access jumps to an unrelated address, and cache misses make traversal about 7 times slower. Directly stored objects live in the `vector`'s contiguous memory, so shuffling has no effect.

### Lost inlining

<div class="compare" markdown="1">

```cpp godbolt flags="-std=c++2c -O2" ok
class Counter {
public:
  int get() const { return n_; }
private:
  int n_ = 0;
};
int sum(const Counter& c, int k) {
  int s = 0;
  for (int i = 0; i < k; ++i)
    s += c.get();
  return s;
}
```

```cpp godbolt flags="-std=c++2c -O2" ok
#include <memory>
class Counter {
public:
  Counter(); ~Counter();
  int get() const;  // in counter.cpp
private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
int sum(const Counter& c, int k) {
  int s = 0;
  for (int i = 0; i < k; ++i)
    s += c.get();
  return s;
}
```

</div>

On arm64 in our tests, the loop on the left is folded away entirely, and `sum` is left with one load, one multiplication and one conditional select:

```text
ldr  w8, [x0]
mul  w8, w8, w1
cmp  w1, #0
csel w0, w8, wzr, gt
ret
```

On the right, `get()` is defined in another translation unit; the compiler can't see it and doesn't know it has no side effects, so it has to call `bl __ZNK7Counter3getEv` `k` times in the loop. `get()` itself is two dependent loads, first `impl_` and then `n`:

```text
ldr  x8, [x0]
ldr  w0, [x8]
ret
```

Link-time optimization (`-flto`) can optimize the translation units of one executable together. With `sum`, `get` and a `main` that constructs a `Counter` and calls `sum` in three files compiled with `-flto`, `main` was optimized to three instructions in our tests, and even the `Impl` allocation was eliminated. Calls across shared libraries cannot get this, and ABI stability is precisely one of the main reasons to use pimpl, so in that case the lost inlining is real.

## Alternatives

### An abstract interface plus a factory

```cpp run title="interface.cpp" ok
#include <memory>
#include <string>

class Widget {                     // widget.h: interface only
public:
  virtual ~Widget() = default;
  virtual void add(int x) = 0;
  virtual int total() const = 0;
  static std::unique_ptr<Widget> create(std::string name);
};

#include <numeric>                 // widget.cpp
#include <vector>
namespace {
class WidgetImpl final : public Widget {
  std::string name_;
  std::vector<int> items_;
public:
  explicit WidgetImpl(std::string n) : name_(std::move(n)) {}
  void add(int x) override { items_.push_back(x); }
  int total() const override {
    return std::accumulate(items_.begin(), items_.end(), 0);
  }
};
}
std::unique_ptr<Widget> Widget::create(std::string name) {
  return std::make_unique<WidgetImpl>(std::move(name));
}

int main() {
  auto w = Widget::create("w");
  w->add(1); w->add(2);
  return w->total() == 3 ? 0 : 1;
}
```

An interface class also keeps the data members out of the header, and needs no forwarding functions: the implementation class implements the virtual functions directly. The price is that users get a `unique_ptr<Widget>`; they can't create a `Widget` directly on the stack or copy it by value, and every call goes through the virtual function table. It suits cases that need several implementations anyway, or need to swap the implementation in tests; registering multiple implementations is covered in [[patterns/factory-and-registration]].

| | pimpl | abstract interface + factory |
|---|---|---|
| Type the user sees | value type `Widget` | `unique_ptr<Widget>` or a reference |
| Call overhead | direct call plus one indirection | virtual call |
| Copying | deep copy can be hand-written | needs a virtual `clone()` |
| Multiple implementations | not supported | supported |
| ABI change points | public function signatures | order and signatures of virtual functions |
| Boilerplate | one forwarding function per public function | no forwarding |

If you want a copyable value type and also run-time interchangeable implementations, that is the problem [[patterns/type-erasure]] solves.

### Modules don't hide layout

C++20 modules let importers read a compiled module interface instead of parsing headers over and over, which greatly reduces the preprocessing and parsing cost of the first problem. But they don't hide layout:

```cpp title="widget.cppm"
export module widget;
import std;
export class Widget {
public:
  int total() const { return n_; }
private:
  std::vector<int> items_;
  int n_ = 0;
};
```

```cpp title="use.cpp" ok
import widget;
static_assert(sizeof(Widget) == 32);   // the importer knows the layout
int f() { Widget w; return w.total(); }
```

This compiles with Clang 23 and libc++'s `std` module in our tests. For the importer to create a `Widget` object, the type must be complete, so the class definition, private members and all, must be reachable from it ([[basic.def.odr#14]]). Whether a declaration is exported has nothing to do with whether it is reachable ([[module.reach#4]]), and reachable declarations determine whether a type is complete ([[module.reach#5]]). Changing a private member changes the module interface, and importers must be recompiled; the shared-library ABI problem is there just the same. How modules are built is covered in [[toolchain/modules-in-practice]].

## Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Not declaring a destructor in the header, or `= default` in the class | users' `.cpp` files fail to compile | `= default` the destructor in the `.cpp` |
| Constructors or move operations defined in the class | same | define all of them in the `.cpp` |
| Only the destructor declared | `Widget` can be neither copied nor moved | declare all five special members |
| A `const` member function modifies the implementation through `impl_` | compiles, violates `const` semantics | `deep_const_ptr` or accessor functions |
| The copy constructor copies the pointer (using `shared_ptr` for copyability) | two objects share mutable state | deep copy, or `indirect` |
| Using a moved-from object | null pointer dereference, UB | convention: only assign or destroy |
| An inline function in the header accesses `impl_->` | doesn't compile, `Impl` is incomplete | move the function definition to the `.cpp` |
| Fast pimpl constants verified on only one platform | `static_assert` fails on another platform | per-platform constants |

## When to use it

| Situation | Recommendation |
|---|---|
| A public class of a shared library that must keep its ABI across versions | pimpl (or a C interface, or an abstract interface) |
| A class with heavy header dependencies (platform headers, regex, third-party libraries) included by many files | pimpl |
| Large numbers of objects, frequent creation, or member functions called in hot loops | don't; store directly, and replace heavy dependencies with forward declarations where possible |
| Multiple implementations, or swapping the implementation in tests | an abstract interface plus a factory |
| Heap allocation is unacceptable, but dependencies should be hidden | fast pimpl, accepting constants in the ABI |
| The project already uses modules throughout and only cares about build speed | modules may already be enough; they provide no ABI isolation |
| The compiler and standard library support C++26 `indirect` | use `indirect<Impl>` instead of `unique_ptr<Impl>` plus hand-written copying |

## Questions

!!! question "1"
    `Widget` declares only `explicit Widget(std::string)` and `~Widget()`, both defined in the `.cpp`, and its member is a `unique_ptr<Impl>`. Does `void f(Widget a) { Widget b = std::move(a); }` compile?

<details markdown="1">
<summary>Answer</summary>

No. The user-declared destructor prevents the move constructor from being implicitly declared ([[class.copy.ctor#8]]), so `std::move(a)` can only match the copy constructor. The implicit copy constructor would have to copy the `unique_ptr`, whose copy constructor is deleted, so `Widget`'s copy constructor is defined as deleted as well. Clang 23 reports `call to implicitly-deleted copy constructor of 'Widget'`. Declare `Widget(Widget&&) noexcept;` in the header and `= default` it in the `.cpp`.
</details>

!!! question "2"
    Change the member to `std::shared_ptr<Impl>`, initialize it with `make_shared<Impl>()` in a constructor in the `.cpp`, and declare no destructor in the header. Does a user's `{ Widget w; Widget c = w; }` compile? What is wrong with this `Widget`?

<details markdown="1">
<summary>Answer</summary>

It compiles, and runs without reports under ASan in our tests. `shared_ptr` allows `T` to be incomplete ([[util.smartptr.shared.general#3]]), records how to delete at construction ([[util.smartptr.shared.const#6]]), and on destruction only calls the recorded deleter ([[util.smartptr.shared.dest#1]]), without needing `T` to be complete. Only the constructor that creates the `Impl` needs it complete.

The problem is semantic: the implicit copy constructor copies the `shared_ptr`, so `c` and `w` share the same `Impl`, modifying one affects the other, and `const` still doesn't propagate. Unless `Impl` is immutable after construction (in which case it should be `shared_ptr<const Impl>`), this is not value semantics.
</details>

!!! question "3"
    In fast pimpl, why can't `static_assert(sizeof(Impl) <= impl_size)` go in the class definition in the header? What happens if it is put in a member function that is only called in some configurations?

<details markdown="1">
<summary>Answer</summary>

In the header `Impl` is an incomplete type, and `sizeof` cannot be applied to an incomplete type ([[expr.sizeof#1]]); that is exactly what pimpl wants: users can't see `Impl`. The `static_assert` can only go after `Impl` is complete.

A `static_assert` declaration outside a template is checked whenever the function definition containing it is compiled, regardless of whether the function is ever called. So it is checked in any member function definition that gets compiled; the destructor is chosen only because every fast pimpl class must define one, so it won't disappear in a refactoring. If the check is put in a function that `#ifdef` excludes from some configurations, those configurations lose the check.
</details>
