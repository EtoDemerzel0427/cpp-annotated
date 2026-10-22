---
title: Policy-based design
summary: "Splitting a class template's behavior into several orthogonal dimensions, each provided by a template argument (a policy): how policies get into the host class, how they achieve zero overhead, policies in the standard library, constraining policies with concepts, and combinatorial explosion, type incompatibility and compile-time costs."
tags: idiom, design patterns, templates, policies, empty base optimization, no_unique_address, concepts
updated: 2026-10-19
---

!!! tldr
    - Policy-based design splits a class template's behavior into several unrelated dimensions (checking, releasing, locking, …), each supplied by a template argument; users assemble the class they need by choosing the arguments.
    - A policy can enter the host as static member functions, as a base class, as a `[[no_unique_address]]` member, or as type aliases. Empty policies take no space, and at `-O2` their calls are fully inlined, generating the same code as hand-written versions.
    - The standard library is full of policies: `Allocator`, `char_traits`, `Compare`, `Hash`, `unique_ptr`'s deleter, `mdspan`'s layout and accessor. Execution policies (`std::execution::par`) are something else: tags for choosing overloads.
    - Specializations with different policies are unrelated types: `Ptr<T, A>` cannot be assigned to `Ptr<T, B>` directly and needs a converting constructor; each combination also instantiates its own copy of the code.
    - A policy's requirements should be written as a concept, not just documented: the error is then reported on the line that writes `Ptr<int, BadCheck>`, not inside some member function of the host.

## One pointer, several behaviors

Suppose you are writing a smart pointer with exclusive ownership. Different uses want different things from it:

- Whether dereferencing checks for null: release builds don't check, while debug builds or code facing external input throw;
- How the object is released: `delete`, `delete[]`, `free`, or some C library's `xxx_destroy`;
- A reference-counted version must also decide whether the counter needs atomic operations.

Writing one class per combination gives two checking modes times three release modes, six classes, and every further dimension doubles that. Most of the code in those classes is identical; they differ in a few lines. Choosing behavior at run time with virtual functions would also work, but every pointer would carry an extra vtable pointer and every dereference an extra indirect call, which is unacceptable for a smart pointer.

**Policy-based design** writes each dimension as a small class, called a **policy**, and the smart pointer as a class template, called the **host**, with one template parameter per dimension. The host specifies only how it uses the policy, e.g. calling `Checking::check(p)`; the actual behavior is determined by the argument the user chooses.

```cpp run title="ptr.cpp" ok
#include <cstdio>
#include <stdexcept>
#include <utility>

// checking policies: provide only static member functions
struct NoCheck {
  static void check(const void*) noexcept {}
};
struct ThrowOnNull {
  static void check(const void* p) {
    if (!p) throw std::logic_error("null dereference");
  }
};

// deletion policies: stateless function objects
struct DeleteOne {
  template<class T> void operator()(T* p) const noexcept { delete p; }
};
struct DeleteArray {
  template<class T> void operator()(T* p) const noexcept { delete[] p; }
};

template<class T, class Checking = NoCheck, class Deleter = DeleteOne>
class Ptr : private Deleter {            // private inheritance: the empty base takes no space
  T* p_ = nullptr;
  Deleter& deleter() noexcept { return *this; }
public:
  Ptr() = default;
  explicit Ptr(T* p, Deleter d = Deleter()) noexcept
      : Deleter(std::move(d)), p_(p) {}
  Ptr(Ptr&& o) noexcept
      : Deleter(std::move(o.deleter())), p_(std::exchange(o.p_, nullptr)) {}
  Ptr& operator=(Ptr&& o) noexcept {
    Ptr tmp(std::move(o));
    std::swap(p_, tmp.p_);
    std::swap(deleter(), tmp.deleter());
    return *this;
  }
  ~Ptr() { if (p_) deleter()(p_); }

  T& operator*() const  { Checking::check(p_); return *p_; }
  T* operator->() const { Checking::check(p_); return p_; }
  T* get() const noexcept { return p_; }
};

struct Widget { int id; };

int main() {
  Ptr<Widget> a(new Widget{1});                      // default policies
  Ptr<Widget, ThrowOnNull> b;                        // null; dereferencing throws
  Ptr<int, NoCheck, DeleteArray> c(new int[4]{});    // released with delete[]
  std::printf("%d %d\n", a->id, c.get()[3]);
  try { (void)b->id; } catch (const std::logic_error& e) { std::puts(e.what()); }
}
```

In our tests it prints `1 0` and `null dereference`, with no ASan or UBSan reports. Six combinations take one host and four small policy classes, and another checking mode needs only one more policy class.

The design rests on the dimensions being **orthogonal**: the checking mode doesn't care how the object is released, and the release mode doesn't care whether anything is checked. If two policies must cooperate (say, a certain ownership policy works only with a certain checking policy), the combinations are no longer a free product, and the host has to deal with invalid combinations.

## A policy's requirements are a set of expressions

All that `Ptr` requires of `Checking` is that `Checking::check(p)` is a valid expression for `p` of type `const void*`. It doesn't require `Checking` to derive from any base class, nor does it care whether `check` is `noexcept` or what it returns. Requirements described purely by expressions are the same kind of thing as the standard library's named requirements (such as *Cpp17Hash*).

Such requirements are checked only at template instantiation. When a class template specialization is implicitly instantiated, member functions are instantiated as declarations only, not definitions ([[temp.inst#3]]); a member function definition is instantiated only when it is used ([[temp.inst#4]]). So if a `Ptr<Widget, ThrowOnNull>` is never dereferenced, `ThrowOnNull::check` is never even called. This property is useful (the interface injection below depends on it), but it also makes errors appear late (see constraining policies with concepts below).

## Ways a policy enters the host

### Static member functions

`Checking::check(p_)` is the simplest form: the policy has no object, and the host calls its static member function through `::`. No space, no state, and no possibility of state.

If you later want to support stateful checking policies (counting dereferences, say), you can switch to storing a policy object and writing `checking_.check(p_)`. Static member functions can also be called with member access syntax ([[class.static.general#1]]), so existing stateless policies need no change.

### As a base class: the empty base optimization

A deleter may have state (a pointer to a memory pool, say), so the host has to store a deleter object. Written directly as a data member `Deleter d_;`, it takes at least one byte even if `Deleter` is an empty class ([[intro.object#8]]), padded to 8 bytes for pointer alignment.

`Ptr` instead inherits privately from `Deleter`. A base class subobject is a **potentially-overlapping subobject** ([[g:potentially-overlapping-subobject]]), which may have zero size and share an address with other subobjects ([[intro.object#7]], [[intro.object#10]]). This is the **empty base optimization** (EBO). Private rather than public inheritance keeps `Ptr` from being implicitly convertible to `Deleter&`.

!!! std
    Otherwise, if the object is a base class subobject of a standard-layout class type with no non-static data members, it has zero size.

    This is the only case where the standard requires an empty base to have zero size ([[intro.object#8]]); otherwise the conditions for zero size are implementation-defined. Mainstream ABIs apply the optimization to empty bases, so the sizes below are {{impl}}.

### As a base class: injecting interface into the host

When a policy is inherited publicly, its public members become part of the host's interface. The `Handle` below gains a `deref_count()` when using the `CountDerefs` policy, and has no such member with the default policy:

```cpp run title="inject.cpp" ok
#include <cstddef>
#include <cstdio>

struct NoStats {
  void on_deref() const noexcept {}
protected:
  ~NoStats() = default;            // the host cannot be destroyed through a NoStats*
};
struct CountDerefs {
  void on_deref() const noexcept { ++derefs_; }
  std::size_t deref_count() const noexcept { return derefs_; }
protected:
  ~CountDerefs() = default;
private:
  mutable std::size_t derefs_ = 0;
};

template<class T, class Stats = NoStats>
class Handle : public Stats {      // public inheritance: the policy's public members join the host's interface
  T* p_;
public:
  explicit Handle(T* p) noexcept : p_(p) {}
  T& operator*() const noexcept {
    this->on_deref();              // members of a dependent base need this->
    return *p_;
  }
};

int main() {
  int x = 7;
  Handle<int, CountDerefs> h(&x);
  *h; *h;
  std::printf("%zu\n", h.deref_count());          // 2
  std::printf("%zu %zu\n", sizeof(Handle<int>),
              sizeof(Handle<int, CountDerefs>));  // 8 16
  // Handle<int> g(&x); g.deref_count();          // error: no such member
}
```

Three details:

1. `Stats` is a base class that depends on a template parameter, and unqualified name lookup does not look into it, so `this->on_deref()` is required. The reason is explained in [[topics/two-phase-lookup]].
2. Public inheritance means `Handle<int, CountDerefs>*` converts implicitly to `CountDerefs*`. If someone `new`s a host and `delete`s it through a policy pointer, and the policy's destructor is not virtual, that is UB ([[expr.delete#3]]). Giving the policy a `protected` non-virtual destructor makes such a `delete` fail to compile, while the host can still call it.
3. Host member functions can also be available only for some policies: member function definitions are instantiated on demand, and an unused member doesn't cause an error even if it is invalid for the current policy. A clearer approach is a `requires` clause on that member; see [[topics/concepts]].

Injecting interface through a base is more common in [[patterns/mixin|mixins]] and [[patterns/crtp|CRTP]]. The difference is direction: a policy is an implementation detail the host chooses and calls; a mixin layers functionality onto a class; with CRTP, the base calls back into the derived class through the template argument.

### As a member: `[[no_unique_address]]` {{c++20}}

Inheritance has side effects: the policy's member names mix with the host's in lookup, the host can implicitly convert to a reference to the policy (with public inheritance), and a `final` class cannot be a base. C++20's `[[no_unique_address]]` ([[P0840R2]]) makes a data member a potentially-overlapping subobject too ([[dcl.attr.nouniqueaddr#1]]), giving the same layout without inheritance:

<div class="compare" markdown="1">

```cpp
template<class T, class D>
class Ptr : private D {
  T* p_;
  // the deleter is obtained via *this
};
```

```cpp
template<class T, class D>
class Ptr {
  T* p_;
  [[no_unique_address]] D d_;
};
```

</div>

Comparing the sizes of several variants in our tests:

```cpp run title="size.cpp" impl
#include <cstdio>

struct Empty  { void operator()(int*) const noexcept {} };
struct Empty2 { void operator()(int*) const noexcept {} };
struct Final final { void operator()(int*) const noexcept {} };
struct Stateful { int* count; void operator()(int*) const noexcept { ++*count; } };

template<class D> struct AsBase : private D { int* p; };
template<class D> struct AsMember { D d; int* p; };
template<class D> struct AsNua { [[no_unique_address]] D d; int* p; };
struct TwoSame     { [[no_unique_address]] Empty a; [[no_unique_address]] Empty  b; int* p; };
struct TwoDistinct { [[no_unique_address]] Empty a; [[no_unique_address]] Empty2 b; int* p; };

int main() {
  std::printf("%zu\n", sizeof(AsBase<Empty>));      // 8
  std::printf("%zu\n", sizeof(AsMember<Empty>));    // 16
  std::printf("%zu\n", sizeof(AsNua<Empty>));       // 8
  std::printf("%zu\n", sizeof(AsNua<Final>));       // 8: final works too
  std::printf("%zu\n", sizeof(AsNua<Stateful>));    // 16: state must be stored
  std::printf("%zu\n", sizeof(TwoSame));            // 8
  std::printf("%zu\n", sizeof(TwoDistinct));        // 8
  TwoSame t; TwoDistinct u;
  std::printf("%td %td\n", (char*)&t.b - (char*)&t.a,   // 1
                           (char*)&u.b - (char*)&u.a);  // 0
}
```

The comments are Clang 23's output on arm64. The last line shows a restriction: two zero-size subobjects of the same type cannot have the same address ([[intro.object#10]] bullet 10.3 requires them not to be similar types). `TwoSame`'s `b` is therefore placed at offset 1; both empty members still overlap `p`, so the total size is unchanged. When a host has two policies of the same type (e.g. two dimensions both using the same empty class), the size may grow because of this.

`AsBase<Final>` doesn't compile, because a `final` class cannot be inherited from; `[[no_unique_address]]` has no such restriction.

!!! impl "Implementation differences"
    For ABI compatibility, MSVC does not make the standard `[[no_unique_address]]` take effect; you have to write `[[msvc::no_unique_address]]`. With multiple inheritance, it also compresses only the first empty base by default, and needs `__declspec(empty_bases)`. Cross-platform code usually wraps both in macros.

    libc++'s `unique_ptr` has switched internally from EBO to `[[no_unique_address]]`, but to stay binary-compatible with the old layout it adds padding for `final` empty deleters: in our tests `sizeof(std::unique_ptr<int, FinalDel>)` is 16 (with `FinalDel` a `final` empty function object). Once a layout is published it is part of the ABI, and switching from EBO to `[[no_unique_address]]` can change it.

### Providing only types

A policy can also provide only types, from which the host picks the types of its data members. Whether a reference count needs atomic operations is such a dimension:

```cpp ok
#include <atomic>
struct SingleThreaded { using counter = long; };
struct MultiThreaded  { using counter = std::atomic<long>; };

template<class Threading>
struct RefBlock {
  typename Threading::counter refs{1};
  void retain() noexcept { ++refs; }
};
```

At `-O2` in our tests, `RefBlock<SingleThreaded>::retain` compiles to three ordinary instructions (load, add, store), and `RefBlock<MultiThreaded>::retain` to a single `ldaddal` (arm64's atomic add with acquire and release semantics). Single-threaded code pays nothing for atomics, and the choice is transparent to the rest of the host.

## Policies get inlined away

A policy's member functions are defined in the class and so implicitly inline; when the host calls them, the types are known at compile time and there are no indirect calls. As long as the optimizer inlines them, the policy leaves no trace. Compare these four functions in pairs:

```cpp
// continuing with Ptr, NoCheck and ThrowOnNull from ptr.cpp above
int raw(int* const& p)           { return *p; }
int unchecked(const Ptr<int>& p) { return *p; }

int raw_checked(int* const& p) {
  if (!p) throw std::logic_error("null dereference");
  return *p;
}
int checked(const Ptr<int, ThrowOnNull>& p) { return *p; }
```

With Clang 23 `-O2` (arm64), `raw` and `unchecked` are both the three instructions `ldr`, `ldr`, `ret`; `raw_checked` and `checked` have identical instruction sequences, each with one `cbz` to the throwing path. Apart from first loading the pointer from the object, `Ptr`'s destructor generates the same code as a hand-written `delete p;`.

`Ptr<int>` is passed by reference to keep the comparison fair. `Ptr` has a non-trivial destructor, so under the Itanium C++ ABI it cannot be passed by value in a register, just like `unique_ptr`; see the ABI section at the end of [[unique.ptr]].

## Policies in the standard library

Many class templates in the standard library have policy parameters; the standard just doesn't use that name and calls them named requirements:

| Host | Policy parameter | Requirement | What it decides |
|---|---|---|---|
| All allocator-aware containers | `Allocator` | *Cpp17Allocator* ([[allocator.requirements.general]]) | where memory comes from and what type pointers are |
| `basic_string`, `basic_string_view`, iostreams | `traits` | character traits ([[char.traits.require#1]]) | how characters are compared, copied and searched |
| `set`, `map`, `priority_queue` | `Compare` | strict weak ordering ([[associative.reqmts.general#2]]) | element order |
| `unordered_set`, `unordered_map` | `Hash`, `Pred` | *Cpp17Hash* ([[unord.req.general#3]]) | hashing and equality |
| `unique_ptr` | `D` (the deleter) | [[unique.ptr.general]] | how the object is released |
| `mdspan` | `LayoutPolicy`, `AccessorPolicy` | [[mdspan.layout.policy.reqmts#1]], [[mdspan.accessor.reqmts#1]] | how multidimensional indices map to offsets, how elements are accessed |

`char_traits` is the classic example. Replace just the comparison-related functions and you get a case-insensitive string:

```cpp run title="ci.cpp" ok
#include <cctype>
#include <cstdio>
#include <string>

struct ci_traits : std::char_traits<char> {
  static char up(char c) {
    return static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
  }
  static bool eq(char a, char b) { return up(a) == up(b); }
  static bool lt(char a, char b) { return up(a) < up(b); }
  static int compare(const char* a, const char* b, std::size_t n) {
    for (std::size_t i = 0; i < n; ++i) {
      if (lt(a[i], b[i])) return -1;
      if (lt(b[i], a[i])) return 1;
    }
    return 0;
  }
  static const char* find(const char* s, std::size_t n, char c) {
    for (std::size_t i = 0; i < n; ++i)
      if (eq(s[i], c)) return s + i;
    return nullptr;
  }
};
using ci_string = std::basic_string<char, ci_traits>;

int main() {
  ci_string a = "Hello";
  std::printf("%d\n", a == "HELLO");          // 1
  std::printf("%zu\n", a.find('L'));          // 2
  std::string s = "hello";
  // ci_string b = s;                         // error: unrelated types
  ci_string b(s.data(), s.size());            // explicit conversion needed
  std::printf("%d\n", a == b);                // 1
}
```

The commented-out line shows the most common nuisance of policy-based design: `ci_string` and `std::string` are two unrelated types that cannot be assigned to each other, and `std::cout << a` doesn't compile either, because the stream's `operator<<` only accepts strings with the same traits. A section below deals with this problem.

`mdspan`'s `LayoutPolicy` is worth noting: it is not itself a mapping but a type with a member template, and `LayoutPolicy::mapping<E>` is the mapping for a particular `extents` ([[mdspan.layout.policy.reqmts#1]]). This is a way to defer supplying all of a policy's arguments until inside the host, the same idea as allocator rebind below.

### Execution policies are not this kind of policy

The `par` in `std::sort(std::execution::par, first, last)` is also called an **execution policy** ([[g:execution-policy]]), but it works differently:

- It is an object passed to a function, not a class template argument. The parallel algorithms are a separate set of overloads whose extra first parameter has an execution policy template parameter as its type ([[algorithms.parallel.overloads#1]]).
- Its type only selects the overload and states which kind of parallelism is permitted; how the algorithm is parallelized is up to the library implementation, and the policy class provides no behavior itself.
- The set is closed: adding specializations of `is_execution_policy` is UB ([[execpol.type#3]]), i.e. users cannot write their own execution policies.

So execution policies are closer to the tags of [[patterns/tag-dispatch]] than to the policy parameters of a class template.

### Moving the policy to run time

The standard library also has the opposite design. `shared_ptr`'s deleter is not a template argument; it is passed at construction and stored type-erased in the control block, so `shared_ptr<T>`s with different deleters are still the same type (see [[topics/ownership-and-smart-pointers]]). `std::pmr::polymorphic_allocator` replaces the allocation policy with a pointer to a `memory_resource`, making containers that use different memory sources the same type (see [[topics/allocators-and-pmr]]). Both trade one indirect call for a unified type.

## Constraining policies with concepts

When a policy's requirements are only documented, passing the wrong policy fails only when the host uses it internally:

<div class="compare" markdown="1">

```cpp title="no-concept.cpp" error
template<class T, class Checking>
struct Ptr {
  T* p_;
  T& operator*() const {
    Checking::check(p_);
    return *p_;
  }
};
struct BadCheck {
  static bool verify(const void*);
};
int main() {
  int x = 0;
  Ptr<int, BadCheck> p{&x}; // no error here
  return *p;  // error: appears in the
}             // instantiation of operator*
```

```cpp title="concept.cpp" error
template<class P>
concept CheckingPolicy =
  requires(const void* p) {
    P::check(p);
  };
template<class T, CheckingPolicy Checking>
struct Ptr {
  T* p_;
  T& operator*() const {
    Checking::check(p_);
    return *p_;
  }
};
struct BadCheck {
  static bool verify(const void*);
};
int main() {
  int x = 0;
  Ptr<int, BadCheck> p{&x}; // error: constraints
  return *p;                // not satisfied
}
```

</div>

For the left side, Clang 23 reports `no member named 'check' in 'BadCheck'` inside `Ptr::operator*`, with a note pointing back to `return *p;`. For the right side it reports `constraints not satisfied for class template 'Ptr'` on exactly the line that writes `Ptr<int, BadCheck>`, followed by two notes explaining that `BadCheck` does not satisfy `CheckingPolicy` because `P::check(p)` is invalid.

In this example both diagnostics are only a few lines long. The gap shows when the host is more complex: instantiating `std::unordered_map` with a key type that has no `std::hash` specialization and calling `operator[]`, Clang reported 5 errors totaling 79 lines in our tests, all inside libc++ headers. *Cpp17Hash* is a named requirement, not a concept, so libc++ can only improve the diagnostics with internal `static_assert`s.

When writing your own policy-based class templates, each policy dimension should have a concept. It doubles as checkable documentation: readers learn what to provide from the definition of `CheckingPolicy`, without reading the host's implementation. How concepts are written and satisfaction is checked is covered in [[topics/concepts]].

!!! pitfall "The concept must match how the host uses the policy"
    The `CheckingPolicy` above requires `P::check(p)`, so it rejects policies whose `check` is a non-static member function. If the host switches to storing a policy object and writing `checking_.check(p_)`, the concept must change accordingly to `requires(const P& c, const void* p) { c.check(p); }`. A concept wider than the host's actual use sends errors back inside the host; one narrower than the actual use needlessly rejects valid policies.

## Combinatorial explosion and type incompatibility

Policies spare the class author from combinatorial explosion, but the combinations don't vanish; they move into the type system: `Ptr<Widget, NoCheck>` and `Ptr<Widget, ThrowOnNull>` are two unrelated types. A function taking `const Ptr<Widget>&` cannot accept a `Ptr` with other policies.

There are three solutions:

1. If the function doesn't need ownership, just take `Widget&` or `Widget*`, independent of policies (see the parameter passing section of [[topics/ownership-and-smart-pointers]]).
2. Make the function a template accepting any policies: `template<class C, class D> void f(const Ptr<Widget, C, D>&);`. The price is one instantiation per combination, and the function must live in a header.
3. Provide converting constructors in the host, letting the policies decide which conversions are valid.

The third is how `unique_ptr` does it. `unique_ptr<U, E>` converts to `unique_ptr<T, D>` if the pointer converts implicitly and `E` converts implicitly to `D` ([[unique.ptr.single.ctor#19]]). In other words, the deleter policy's own converting constructors decide whether `unique_ptr`s convert. `Ptr` can copy this rule:

```cpp run title="convert.cpp" ok
#include <concepts>
#include <utility>

struct NoCheck     { static void check(const void*) noexcept {} };
struct ThrowOnNull {
  ThrowOnNull() = default;
  ThrowOnNull(NoCheck) noexcept {}   // allows only NoCheck → ThrowOnNull
  static void check(const void* p) { if (!p) throw 0; }
};

template<class T, class Checking = NoCheck>
class Ptr {
  T* p_ = nullptr;
  template<class, class> friend class Ptr;  // other specializations need access to p_
public:
  Ptr() = default;
  explicit Ptr(T* p) noexcept : p_(p) {}
  Ptr(Ptr&& o) noexcept : p_(std::exchange(o.p_, nullptr)) {}
  template<class U, class C2>
    requires std::convertible_to<U*, T*> && std::convertible_to<C2, Checking>
  Ptr(Ptr<U, C2>&& o) noexcept : p_(std::exchange(o.p_, nullptr)) {}
  ~Ptr() { delete p_; }
};

struct Base { virtual ~Base() = default; };
struct Derived : Base {};

int main() {
  Ptr<Derived>              a(new Derived);
  Ptr<Base, ThrowOnNull>    b = std::move(a);   // OK: both dimensions widen
  // Ptr<Derived, NoCheck>  c = std::move(b);   // error: Base* → Derived* not allowed
  Ptr<Base, ThrowOnNull>    d(new Base);
  // Ptr<Base, NoCheck>     e = std::move(d);   // error: checking cannot be dropped
}
```

Different specializations of `Ptr` have no special access to each other, so a friend template declaration `template<class, class> friend class Ptr;` lets them access each other's `p_`. Uncomment the last line and Clang reports `no viable conversion`, with a note saying the converting constructor's constraints are not satisfied.

## Template template parameters or type parameters

A host often needs to apply a policy to a type the user did not give directly. A linked list's allocator policy is an example: the user thinks of allocating `T`, but the list actually allocates `Node`s. There are two ways to write this:

```cpp run title="rebind.cpp" ok
#include <cstddef>
#include <memory>

template<class T, std::size_t Align = 64>
struct AlignedAlloc {                   // the second parameter has a default
  using value_type = T;
  template<class U> struct rebind { using other = AlignedAlloc<U, Align>; };
  AlignedAlloc() = default;
  template<class U> AlignedAlloc(const AlignedAlloc<U, Align>&) noexcept {}
  T* allocate(std::size_t n) {
    return static_cast<T*>(::operator new(n * sizeof(T), std::align_val_t{Align}));
  }
  void deallocate(T* p, std::size_t) noexcept {
    ::operator delete(p, std::align_val_t{Align});
  }
  friend bool operator==(AlignedAlloc, AlignedAlloc) = default;
};

// approach 1: template template parameter; the host supplies the type argument itself
template<class T, template<class> class Alloc = std::allocator>
class ListA {
  struct Node { T value; Node* next; };
  Alloc<Node> alloc_;                   // instantiated with Node directly
public:
  void push(T v) { Node* n = alloc_.allocate(1); alloc_.deallocate(n, 1); (void)v; }
};

// approach 2: type parameter; the host swaps the type argument with rebind
template<class T, class Alloc = std::allocator<T>>
class ListB {
  struct Node { T value; Node* next; };
  using NodeAlloc = std::allocator_traits<Alloc>::template rebind_alloc<Node>;
  NodeAlloc alloc_;
public:
  void push(T v) { Node* n = alloc_.allocate(1); alloc_.deallocate(n, 1); (void)v; }
};

template<class T> using Align128 = AlignedAlloc<T, 128>;

int main() {
  ListA<int, AlignedAlloc> a;           // Align uses the default 64
  ListA<int, Align128> c;               // an alias template works as an argument too
  ListB<int, AlignedAlloc<int, 128>> b; // rebind keeps the 128
  a.push(1); c.push(2); b.push(3);
}
```

(`push` just allocates and frees one node, to make the member functions get instantiated.)

The template template parameter ([[g:template-template-parameter]]) approach looks more direct but has several problems:

- The argument must be a template; users cannot pass a type of allocator that has already been configured, such as `AlignedAlloc<int, 128>`. Configuring a non-type argument requires writing a separate alias template.
- The parameter's template head fixes the shape of the argument. `template<class> class` accepts `AlignedAlloc`, which has two parameters, because the second has a default: since C++17 ([[P0522R0]]), a template template parameter matches as long as it is at least as specialized as the argument ([[temp.arg.template#4]]). Before that, the two parameter lists had to match exactly.
- The policy itself cannot be an ordinary class; a non-template policy like `NoCheck` cannot be passed to a template template parameter.

A type parameter plus rebind is the standard library's choice: the user gives a complete type, and the host gets the allocator for nodes through `allocator_traits<Alloc>::rebind_alloc<Node>` ([[allocator.traits.types#11]]). If the allocator has no `rebind` member, `allocator_traits` rewrites a type of the form `SomeAllocator<T, Args>` to `SomeAllocator<U, Args>`, but only if `Args` are all type arguments ([[allocator.requirements.general#18]]). `AlignedAlloc`'s second argument is a value, which fails that condition, so it must write `rebind` itself. Delete that line and libc++ in our tests reports `This allocator has to implement rebind`.

## Default policies and named template arguments

Template arguments correspond to parameters by position. `Ptr<int, NoCheck, DeleteArray>` only wants to change the deleter but must spell out the checking policy before it, even though that is the default. The more policies there are, the worse this gets, and reordering the parameters breaks every existing use.

C++ has no named template arguments. A common substitute packs a set of policies into one type; users derive from the default pack and override only the members they need to change:

```cpp run title="named.cpp" ok
#include <cstdio>
#include <type_traits>

struct NoCheck     { static constexpr bool checked = false; };
struct ThrowOnNull { static constexpr bool checked = true; };
struct DeleteOne   { static constexpr bool array = false; };
struct DeleteArray { static constexpr bool array = true; };

// a set of policies packed into one type
struct DefaultPtrPolicies {
  using checking = NoCheck;
  using deleter  = DeleteOne;
};

template<class T, class P = DefaultPtrPolicies>
class Ptr {
  using Checking = typename P::checking;
  using Deleter  = typename P::deleter;
public:
  static void describe() {
    std::printf("checked=%d array=%d\n", Checking::checked, Deleter::array);
  }
};

struct ArrayPolicies : DefaultPtrPolicies {
  using deleter = DeleteArray;            // change only the deleter; checking stays default
};

// options as values: a constant template parameter of class type (C++20)
struct PtrOptions {
  bool checked = false;
  bool array   = false;
};
template<class T, PtrOptions O = {}>
class Ptr2 {
public:
  static void describe() { std::printf("checked=%d array=%d\n", O.checked, O.array); }
};

int main() {
  Ptr<int>::describe();                         // checked=0 array=0
  Ptr<int, ArrayPolicies>::describe();          // checked=0 array=1
  Ptr2<int, {.array = true}>::describe();       // checked=0 array=1
  static_assert(std::is_same_v<Ptr2<int, {.array = true}>,
                               Ptr2<int, {false, true}>>);
}
```

The drawback of policy packs is that type identity follows the pack: someone else's `struct MyArrayPolicies : DefaultPtrPolicies { using deleter = DeleteArray; };` has the same contents as `ArrayPolicies`, but `Ptr<int, MyArrayPolicies>` and `Ptr<int, ArrayPolicies>` are still different types.

When the options are just switches or numbers, C++20 allows class types as constant template parameters ([[P0732R2]]), which combine with designated initializers as `Ptr2<int, {.array = true}>`. The parameter's type must be a structural type ([[g:structural-type]], [[temp.param#12]]); two template arguments with equal values give the same type ([[temp.type#1]]), which the `static_assert` above verifies. The limitation is that only values can be passed, not types, and the host has to select behavior from the values with `if constexpr`. More approaches are in [[patterns/named-parameters]].

## Compile-time costs

Each combination of policies is a separate class template specialization, and each member function used is instantiated once per specialization. We ran a comparison with the `Ptr` from `ptr.cpp` above: 64 functions, each constructing, moving, move-assigning and dereferencing a `Ptr`.

| Case | `-O0` object file | `Ptr` member functions at `-O0` | `-O2` object file |
|---|---|---|---|
| 1 function, 1 combination | 3.5 KB | 9 | 0.5 KB |
| 64 functions, same 1 combination | 27 KB | 9 | 4.8 KB |
| 64 functions, 64 combinations (4 × 4 × 4) | 120 KB | 576 | 8.5 KB |

At `-O0`, each of the 64 combinations generates all 9 member functions, 576 in total, and the object file is more than 4 times that of a single combination. At `-O2` all of these functions are inlined, no `Ptr` member function remains, and the difference comes mainly from the different managed types.

At this scale compile times were all around 0.1 s, with no visible difference. In real projects the cost shows elsewhere: debug build size and link time grow with the number of combinations; every policy type appears in mangled names, e.g. the symbol of `checked` is `_Z7checkedRK3PtrIi11ThrowOnNull9DeleteOneE`, and with nesting, type names in symbols and error messages get very long; all the code is in headers, so changing a policy recompiles every translation unit that includes it.

## Compared with the run-time strategy pattern

The classic strategy pattern ([[patterns/strategy]]) chooses behavior at run time: the host holds a pointer to an abstract base or a `std::function` and executes the strategy through a virtual or indirect call. Both solve the same problem with opposite trade-offs:

| | Policy-based design (compile time) | Strategy pattern (run time) |
|---|---|---|
| When chosen | at compile time, written into the type | at run time, changeable at any time |
| Objects with different choices | different types, can't share a container | same type |
| Call overhead | none, usually inlined | one indirect call, usually not inlinable |
| Space overhead | zero for empty policies | at least one pointer |
| Where the code lives | entirely in headers | implementation can be in a `.cpp` |
| Code size | one copy per combination | one copy |
| Error detection | compile time (with concepts) | run time |

The two can be combined: use compile-time policies for the performance-sensitive parts, then wrap the different combinations behind one interface type with [[patterns/type-erasure]], the way `shared_ptr` erases the deleter and `pmr` erases the allocator.

## Common pitfalls

### Deleting the host through a policy pointer

When the host inherits a policy publicly, a host pointer converts implicitly to a policy pointer; if the policy's destructor is not virtual, `delete`ing the host through it is UB. Policies should declare their destructors `protected`. Private inheritance or a `[[no_unique_address]]` member avoids the problem.

### Name clashes between policies

When the host inherits two policies that both have a member named `check`, writing `this->check(p)` in the host is an ambiguous name lookup and fails to compile. Policy member names should carry a prefix for their dimension, or the policies should be members instead of bases.

### Assuming EBO always applies

An empty policy as an ordinary data member takes at least one byte plus alignment padding; a `final` empty policy cannot be a base; two empty subobjects of the same type cannot overlap at one address; MSVC needs special attributes. When changing how policies are stored, put the expected size in the code with `static_assert(sizeof(...) == ...)`.

### Describing policy requirements only in documentation

A wrong policy can go unnoticed as long as the host never uses it, and once it is used, the error appears inside the host. Constrain every policy parameter with a concept.

### Dimensions that aren't orthogonal

If one policy makes sense only when another has a particular value, the combinations are no longer free, and the host fills up with `if constexpr` or `static_assert` to exclude invalid combinations. Merge the two dimensions into one policy.

## When to use it

| Situation | Recommendation |
|---|---|
| Generic libraries with clear, orthogonal behavior dimensions and performance sensitivity (containers, smart pointers, allocators, logging) | policy-based design, with a concept for each dimension |
| Behavior must switch at run time, or differently configured objects must share a container | the run-time strategy pattern or type erasure |
| Just a few boolean switches or numbers | a constant template parameter of class type, or simply constructor arguments |
| Only one dimension with two or three choices | a plain function object parameter (like `Compare`), without bringing in the notion of policies |
| Policies that depend on each other | merge them into one policy, or redraw the dimensions |
| Code published across an ABI boundary | be careful: policy types enter mangled names and layout, and changing any policy changes the ABI |

## Questions

!!! question "1"
    In `struct H { [[no_unique_address]] Empty a; [[no_unique_address]] Empty b; int* p; };`, `Empty` is an empty class. Can `&h.a == &h.b` be true? Must `sizeof(H)` be larger than `sizeof(int*)`?

<details markdown="1">
<summary>Answer</summary>

`&h.a == &h.b` cannot be true. By [[intro.object#10]], two subobjects may share an address only if at least one has zero size and they are not of similar types; `a` and `b` have the same type, so their addresses must differ. But that doesn't mean `H` must be larger: each can overlap a different byte of `p`. Clang 23 places `a` at offset 0 and `b` at offset 1, and `sizeof(H)` is still 8. Since whether an empty member can have zero size is itself implementation-defined ([[intro.object#8]]), another implementation giving a larger result would also conform.
</details>

!!! question "2"
    A library has `void render(const Ptr<Widget>& w);`. The caller holds a `Ptr<Widget, ThrowOnNull>`, which can't be passed in. `render` only reads the `Widget` and doesn't store it. How should the signature change?

<details markdown="1">
<summary>Answer</summary>

Change it to `void render(const Widget& w);` and call it as `render(*p)`. `render` has nothing to do with ownership, so a smart pointer shouldn't appear in its parameter at all, and it is then naturally independent of policies; the dereference happens in the caller, using the caller's own checking policy. If the `Widget` might not exist, use `const Widget*`. Only when the function takes over or shares ownership should the parameter be a `Ptr`, and then templates or converting constructors come into consideration.
</details>

!!! question "3"
    Why is `std::execution::par` called a policy, yet users can't write their own execution policy the way they write a `Compare`?

<details markdown="1">
<summary>Answer</summary>

`Compare` is a policy parameter of a class template: the standard specifies the expressions it must provide (a strict weak ordering comparison), the container calls it, and the behavior is determined by the user's implementation. An execution policy provides no behavior: the parallel algorithm overloads only look at whether the argument's type is an execution policy (`is_execution_policy_v`), use that to select the overload and relax the requirements on element access functions, and how to parallelize is entirely up to the library implementation ([[algorithms.parallel.overloads#1]]). Adding specializations of `is_execution_policy` is UB ([[execpol.type#3]]), so the set is closed, containing only the execution policies defined by the standard and the implementation. Mechanically it is a tag, not a replaceable implementation.
</details>
