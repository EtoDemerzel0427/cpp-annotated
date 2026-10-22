---
title: Non-virtual interface and template method
summary: A public non-virtual function does the checking, locking and logging, then calls a private virtual function for the customizable step. Why private virtual functions can be overridden, why access checks and default arguments both use the static type, why the template method cannot run during construction, why final does not necessarily devirtualize here, and how the standard library itself uses this structure.
tags: idiom, virtual functions, access control, template method, devirtualization
updated: 2026-10-19
---

!!! tldr
    - The non-virtual interface (NVI) splits a virtual function into two layers: the outer public non-virtual function is the caller's only entry point, where precondition checks, locking, logging and statistics are written once; the inner private virtual function is the only part derived classes can change.
    - Private virtual functions can be overridden, because overriding ignores access. Access to a virtual call is checked using the static type of the call expression, so a derived class making its overrider public cannot open the base's door.
    - Default arguments of virtual functions follow the static type, and writing a different default in an overrider only creates two behaviors. NVI puts the default arguments on the non-virtual wrapper, and the problem disappears.
    - During construction and destruction, virtual calls dispatch only to the current class's version, so a template method cannot be started from a base constructor; dispatching to a pure virtual function is UB.
    - In NVI, `final` does not necessarily let Clang devirtualize, because the virtual call is written in the base's wrapper, where the static type is the base. Writing the wrapper with deducing this, or switching entirely to compile-time polymorphism ([[patterns/crtp|CRTP]]), is what allows a direct call by derived type.

## One virtual function doing two jobs

Below is an abstract interface for reading data. Callers use it through `Source&`, and derived classes implement concrete data sources.

```cpp title="public-virtual.cpp" ok
#include <cstddef>
#include <span>

class Source {
public:
  virtual ~Source() = default;
  // contract: buf must not be empty, the return value is at most buf.size(),
  // and with multiple threads the caller is responsible for locking
  virtual std::size_t read(std::span<char> buf) = 0;
};
```

`read` is two things at once: an interface for callers (which preconditions must hold, what is guaranteed) and a customization point for derived classes (where the data comes from). The two have different audiences and evolve at different paces.

With both on one function, the interface's contract can only live in comments. Every derived class must check arguments, lock and count on its own, and every place that forgets is a bug; if the base later wants to add a log line, every derived class has to change.

The **non-virtual interface** (NVI) separates the two: the public function is not virtual; it does what every derived class should do, then calls a private virtual function for the step that actually varies.

```cpp run title="nvi.cpp" ok
#include <cassert>
#include <cstddef>
#include <cstdio>
#include <mutex>
#include <span>
#include <string_view>

class Source {
public:
  virtual ~Source() = default;

  // the only entry point: checking, locking and counting all happen here
  std::size_t read(std::span<char> buf) {
    assert(!buf.empty());                  // precondition
    std::lock_guard lk(m_);
    std::size_t n = do_read(buf);
    assert(n <= buf.size());               // postcondition
    total_ += n;
    return n;
  }
  std::size_t total() const { return total_; }

private:
  // customization point: derived classes only decide where the data comes from
  virtual std::size_t do_read(std::span<char> buf) = 0;

  std::mutex m_;
  std::size_t total_ = 0;
};

class StringSource final : public Source {
  std::string_view s_;
public:
  explicit StringSource(std::string_view s) : s_(s) {}
private:
  std::size_t do_read(std::span<char> buf) override {
    std::size_t n = s_.copy(buf.data(), buf.size());
    s_.remove_prefix(n);
    return n;
  }
};

int main() {
  StringSource src("hello, world");
  Source& s = src;
  char buf[5];
  while (std::size_t n = s.read(buf))
    std::printf("[%.*s]", int(n), buf);
  std::printf("\ntotal = %zu\n", s.total());
}
```

Run with Clang 23 under ASan and UBSan, it prints `[hello][, wor][ld]` and `total = 12`. `StringSource` has seven lines of logic and never touches the lock or the counter; nor can it bypass the checks, because the outside world cannot call `do_read` at all.

The general form of this structure is called the **template method**: a non-virtual function in the base fixes the skeleton of an algorithm, and some steps of the skeleton are virtual functions filled in by derived classes. NVI is the special case where the skeleton has a single step. "Template" here has nothing to do with C++ templates; it refers to the skeleton itself.

```cpp
// template method: fixed skeleton, three customizable steps
void Exporter::run() {
  auto data = do_collect();
  if (do_validate(data))
    do_write(data);
}
```

## Why private virtual functions can be overridden

Beginners often assume private members are invisible to derived classes and so cannot be overridden. In fact, overriding has nothing to do with access: if a member function in a derived class corresponds to a base virtual function in name, parameter list, cv-qualification and ref-qualifier, it overrides that virtual function ([[class.virtual#2]]). A footnote in [[class.virtual]] states explicitly that access control is not considered in determining overriding.

Access control governs whether a member can be **named** ([[class.access]]). Overriding doesn't name the base function; the derived class just declares a function of its own. So a derived class can override `Base::step` but cannot call it:

<div class="compare" markdown="1">

```cpp title="private-hook.cpp" error
class Base {
public:
  void run() { step(); }
  virtual ~Base() = default;
private:
  virtual void step() {}
};
class Derived : public Base {
  void step() override { // OK: overrides
    Base::step();  // error: private
  }
};
```

```cpp run title="protected-hook.cpp" ok
class Base {
public:
  void run() { step(); }
  virtual ~Base() = default;
protected:
  virtual void step() {}
};
class Derived : public Base {
  void step() override {
    Base::step();  // OK: protected
  }
};
int main() { Derived d; d.run(); }
```

</div>

On the left Clang reports `'step' is a private member of 'Base'`. A qualified call like `Base::step()` doesn't go through virtual dispatch ([[class.virtual#16]]); it names `Base::step`, so access checking applies.

This gives the rule for choosing a hook's access. If the derived overrider needs to call the base's default implementation first, make the hook protected; if the base implementation is just a default or is pure virtual and derived classes have no reason to call it, make it private. The standard library uses both: `std::pmr::memory_resource`'s `do_allocate` is private, while `std::basic_streambuf`'s `sync`, `overflow` and the like are protected (see below).

Destructors are the exception. A base destructor is either public and virtual, allowing `delete` through a base pointer, or protected and non-virtual, forbidding it. It cannot be a private hook, because the derived destructor implicitly calls it.

## Access checks use the static type

A derived class can widen access when overriding, but that doesn't affect calls through the base:

```cpp title="access-static-type.cpp" error
class Base {
public:
  void run() { step(); }
  virtual ~Base() = default;
private:
  virtual void step() {}
};
class Derived : public Base {
public:
  void step() override {}  // made public when overriding
};
int main() {
  Derived d;
  Base& b = d;
  d.step();   // OK: checked against Derived::step, public
  b.step();   // error: checked against Base::step, private
}
```

!!! std "[class.access.virt] ¶2"
    Access is checked at the call point using the type of the expression used to denote the object for which the member function is called.

The access of a virtual function is determined by its own declaration and is not affected by the functions that override it ([[class.access.virt#1]]). In `b.step()` the static type of `b` is `Base`, name lookup finds `Base::step`, which is private, so it is an error; which function would be dispatched at run time is irrelevant. The full discussion is in the virtual functions section of [[class.access]].

For NVI this rule guarantees that only the base can open the base's door. A derived class making `do_read` public only lets code holding a `StringSource&` bypass the checks; all code going through `Source&` still has to use `read`.

## Default arguments: only on the non-virtual wrapper

```cpp run title="virtual-default-arg.cpp" ok
#include <cstdio>
struct Shape {
  virtual ~Shape() = default;
  virtual void draw(int width = 1) const {
    std::printf("Shape  width=%d\n", width);
  }
};
struct Circle : Shape {
  void draw(int width = 3) const override {
    std::printf("Circle width=%d\n", width);
  }
};
int main() {
  Circle c;
  const Shape& s = c;
  c.draw();   // Circle width=3
  s.draw();   // Circle width=1
}
```

Both calls execute `Circle::draw`, but `width` is 3 once and 1 once. Default arguments are filled in at the call site at compile time, where the compiler only knows the static type, so the default from the declaration of the static type is used; overriders don't inherit the default arguments of the functions they override either ([[dcl.fct.default#10]]). The program is well-formed and its behavior entirely determined; the two call sites just see two different defaults. Clang 23 with `-Wall -Wextra` gives no warning.

NVI never gives this problem a chance: the default argument is on the non-virtual `draw`, the virtual `do_draw` has no default argument, and derived classes have no default to override.

<div class="compare" markdown="1">

```cpp run title="nvi-default-arg.cpp" ok
#include <cstdio>
class Shape {
public:
  virtual ~Shape() = default;
  void draw(int width = 1) const {
    do_draw(width);
  }
private:
  virtual void do_draw(int w) const = 0;
};
class Circle : public Shape {
  void do_draw(int w) const override {
    std::printf("Circle w=%d\n", w);
  }
};
int main() {
  Circle c;
  const Shape& s = c;
  c.draw();   // Circle w=1
  s.draw();   // Circle w=1
}
```

```cpp
// the standard library's approach: wrapper and virtual
// function carry the same default ([streambuf])
pos_type pubseekoff(off_type off,
    ios_base::seekdir way,
    ios_base::openmode which
      = ios_base::in | ios_base::out);
// protected:
virtual pos_type seekoff(off_type off,
    ios_base::seekdir way,
    ios_base::openmode which
      = ios_base::in | ios_base::out);
```

</div>

The virtual function `seekoff` of `basic_streambuf` also has a default argument ([[streambuf.virt.buffer]]), the same as that of the wrapper `pubseekoff`. Outside code can only call `pubseekoff`; the default on `seekoff` matters only for direct calls inside derived classes, and as long as the two agree, the split above cannot happen.

## A template method cannot start during construction or destruction

The skeleton of a template method calls virtual functions. Running the skeleton in a base constructor looks like a convenient way to initialize, but at that point the derived part has not been constructed yet:

```cpp run title="template-method-in-ctor.cpp" ub
#include <cstdio>
class Plugin {
public:
  Plugin() { init(); }          // starts the template method during construction
  virtual ~Plugin() = default;
  void init() {
    std::puts("Plugin::init begin");
    do_init();                  // dispatches to Plugin::do_init: pure virtual
    std::puts("Plugin::init end");
  }
private:
  virtual void do_init() = 0;
};
class Audio : public Plugin {
  void do_init() override { std::puts("Audio::do_init"); }
};
int main() { Audio a; }
```

A virtual call made (directly or indirectly) from a constructor or destructor on the object under construction or destruction calls the final overrider in the constructor's or destructor's class, not an overrider in a more derived class ([[class.cdtor#4]]). Here that function is the pure virtual `Plugin::do_init`, and such a virtual call to a pure virtual function is UB ([[class.abstract#6]]).

Clang 23 compiles it without any warning: Clang only warns when a constructor calls a pure virtual function directly, and here the non-virtual `init` sits in between. At run time libc++abi prints `Pure virtual function called!` and aborts with exit code 134. If `do_init` were not pure virtual, the program wouldn't crash; it would silently run the base version, which is harder to notice. Details in [[class.cdtor]].

When the skeleton must run right after construction, split construction and start-up into two steps, and have a factory function guarantee both happen:

```cpp run title="two-phase.cpp" ok
#include <cstdio>
#include <memory>
class Plugin {
public:
  virtual ~Plugin() = default;
  template <class T> static std::unique_ptr<Plugin> create() {
    std::unique_ptr<Plugin> p = std::make_unique<T>();
    p->init();                  // construction has finished; dispatches to T::do_init
    return p;
  }
  void init() { std::puts("init: begin"); do_init(); std::puts("init: end"); }
protected:
  Plugin() = default;
private:
  virtual void do_init() = 0;
};
class Audio : public Plugin {
  void do_init() override { std::puts("Audio::do_init"); }
};
int main() { auto p = Plugin::create<Audio>(); }
```

Destruction is the symmetric problem: when the base destructor runs, the derived part has already been destroyed, and a hook called there also dispatches only to the base version. When a cleanup step needs the derived class's participation, either the derived destructor does it itself, or a `close()` is provided to call before destruction.

## Non-virtual interfaces in the standard library

The standard library uses this structure systematically in three places, each with different hook access.

| Class | Public non-virtual functions | Virtual functions | Hook access |
|---|---|---|---|
| `std::basic_streambuf` | `pubsync`, `pubseekoff`, `sgetc`, `sputc`… | `sync`, `seekoff`, `underflow`, `overflow`… | protected |
| `std::num_put` and other locale facets | `put`, `get`… | `do_put`, `do_get`… | protected |
| `std::pmr::memory_resource` | `allocate`, `deallocate`, `is_equal` | `do_allocate`, `do_deallocate`, `do_is_equal` | private |

`basic_streambuf` shows another use of NVI: an inline fast path, with virtual calls only on the slow path. `pubsync()` just returns `sync()` ([[streambuf.buffer#4]]), but `sgetc()` returns `*gptr()` directly while there are characters left in the buffer, and calls the virtual `underflow()` only when the buffer is exhausted ([[streambuf.pub.get#5]]). The vast majority of character-by-character reads are therefore one comparison and one memory read.

Every public member function of a locale facet just forwards; for example `num_put::put` returns `do_put(...)` ([[facet.num.put.members#1]]). To customize formatting, users derive a facet and override `do_put`, while callers still call `put`.

`memory_resource`'s wrapper does more than forward. Besides calling `do_allocate`, `allocate` specifies that objects are implicitly created in the allocated storage ([[mem.res.public#2]]), semantics that derived classes cannot and need not care about. `do_allocate` has the precondition that the alignment is a power of two ([[mem.res.private#1]]).

```cpp run title="counting-resource.cpp" ok
#include <cstddef>
#include <cstdio>
#include <memory_resource>
#include <vector>

class counting_resource : public std::pmr::memory_resource {
  std::pmr::memory_resource* up_;
public:
  std::size_t live = 0;
  explicit counting_resource(std::pmr::memory_resource* up) : up_(up) {}
private:  // stays private, as in the base
  void* do_allocate(std::size_t n, std::size_t align) override {
    void* p = up_->allocate(n, align);   // through the upstream's public wrapper
    live += n;
    return p;
  }
  void do_deallocate(void* p, std::size_t n, std::size_t align) override {
    up_->deallocate(p, n, align);
    live -= n;
  }
  bool do_is_equal(const memory_resource& o) const noexcept override {
    return this == &o;
  }
};

int main() {
  counting_resource r(std::pmr::new_delete_resource());
  {
    std::pmr::vector<int> v(&r);
    v.resize(100);
    std::printf("live = %zu\n", r.live);   // live = 400
  }
  std::printf("live = %zu\n", r.live);     // live = 0
}
```

With libc++ in our tests it prints `live = 400` and `live = 0`. The overriders call the upstream resource through `allocate` too, not `do_allocate`: the latter is private in `memory_resource`, and writing `r.do_allocate(8, 8)` from outside gives `'do_allocate' is a private member of 'std::pmr::memory_resource'`. Full usage of memory resources is in [[topics/allocators-and-pmr]].

## C++26 contracts go on the wrapper

The non-virtual wrapper is the natural place for preconditions and postconditions anyway. C++26 function contract assertions ([[dcl.contract.func]]) make these conditions part of the declaration, visible to callers and tools:

```cpp
class Source {
public:
  virtual ~Source() = default;
  std::size_t read(const std::span<char> buf)
    pre(!buf.empty())
    post(n : n <= buf.size())
  {
    return do_read(buf);
  }
private:
  virtual std::size_t do_read(std::span<char> buf) = 0;
};
```

The `n` in `post(n : ...)` refers to the return value. The `const` before `buf` is not decoration: the postcondition odr-uses a by-value parameter, which must then have const type in every declaration of the function ([[dcl.contract.func#7]]); otherwise the function body could modify `buf` first, and the postcondition would no longer be checking the value the caller passed.

With the assertions on the non-virtual wrapper, the precondition is written once, holds for every derived class, and cannot be weakened by a derived class. Two things to note: contract assertions are evaluated before the function body, so the check happens before the wrapper's body takes the lock; and whether each evaluation uses the ignore, observe, enforce or quick-enforce semantic is implementation-defined ([[basic.contract.eval#2]]), and they can be switched off wholesale. So they suit expressing the caller's obligations, but cannot replace run-time validation that must happen no matter what.

The code above carries no verdict: Clang 23 does not implement contracts yet and reports a syntax error at `pre`.

## `final` and devirtualization

**Devirtualization** means the compiler determines the target of a virtual call at compile time, replaces the indirect call with a direct one, and can then inline it. The most common basis is `final`: if the static type of the object is a `final` class, the final overrider can only be the one in that class.

```cpp title="final-direct.cpp" ok
struct Base {
  virtual ~Base() = default;
  virtual int do_run(int x) = 0;
};
struct Twice final : Base {
  int do_run(int x) override { return x * 2; }
};
int call(Twice& t, int x) { return t.do_run(x) + 1; }
```

Compiling `call` with Clang 23 `-O2 --target=x86_64-linux-gnu`, without and with `final`:

<div class="compare" markdown="1">

```text
; without final
pushq   %rax
movq    (%rdi), %rax   ; load the vptr
callq   *16(%rax)      ; indirect call
incl    %eax
popq    %rcx
retq
```

```text
; with final
leal    1(,%rsi,2), %eax  ; x*2+1
retq
```

</div>

NVI is different. Take the same `Twice final`, but with a private hook called through `run`:

```cpp title="final-nvi.cpp" ok
struct Base {
  virtual ~Base() = default;
  int run(int x) { return do_run(x) + 1; }
private:
  virtual int do_run(int x) = 0;
};
struct Twice final : Base {
private:
  int do_run(int x) override { return x * 2; }
};
int call(Twice& t, int x) { return t.run(x); }
```

Clang 23 at `-O2` generates exactly the same code for `call` as without `final`: still a vptr load plus an indirect call (on both x86-64 and arm64). The reason is that the virtual call `do_run(x)` is written in `Base::run`, where the static type of `*this` is `Base`. The front end generates an ordinary virtual call based on `Base`; once `run` is inlined into `call`, the optimizer sees only a vptr loaded from some object whose dynamic type it does not know.

Clang can still devirtualize in these cases:

- The object is constructed in the same function (e.g. `Twice t; return t.run(x);`): the optimizer sees the vptr written by the constructor and inlines to `x*2+1`, with or without `final`;
- With LTO plus `-fwhole-program-vtables -fvisibility=hidden`, the linker finds that `do_run` has only one implementation in the whole program and inlines it too; `final` isn't needed then either;
- The wrapper is written as a deducing-this function template, so the static type at the call site enters the wrapper (next section).

These observations apply only to Clang 23 in our tests; GCC's interprocedural type propagation works differently and was not tested.

How much difference this makes depends on the size of the hook. On an Apple M2 Pro in our tests, calling `run` through `Base&` 500 million times in a loop took about 480 ms, i.e. about 1 ns per call; through the devirtualized path, Clang folded the whole loop into a closed-form computation and it took close to 0. The real gain comes from the further optimizations that inlining enables, not from the one indirect jump saved. When the hook itself does I/O, allocation or locking, that 1 ns is irrelevant.

## Compile-time alternatives: deducing this and CRTP

C++23's explicit object parameters (deducing this, [[P0847R7]]) let the wrapper see the static type at the call site:

```cpp title="deducing-this-nvi.cpp" ok
struct Base {
  virtual ~Base() = default;
  template <class Self>
  int run(this Self& self, int x) {
    return self.do_run(x) + 1;   // do_run is looked up in Self
  }
private:
  virtual int do_run(int x) = 0;
};
struct Twice final : Base {
private:
  friend Base;                   // lets Base::run name Twice::do_run
  int do_run(int x) override { return x * 2; }
};
int call(Twice& t, int x) { return t.run(x); }       // inlined directly
int call_base(Base& b, int x) { return b.run(x); }   // virtual call
```

With Clang 23 at `-O2`, `call` compiles to a single `leal 1(,%rsi,2), %eax`, while `call_base` is still an indirect call. The same interface supports both uses: code holding a base reference gets run-time polymorphism, and code that knows the concrete type gets a direct call.

The price is access control. When `Self` is `Twice`, `self.do_run` finds `Twice::do_run`, which is private in `Twice`, and this code belongs to `Base`, which is neither a member nor a friend of `Twice`. Remove `friend Base;` and Clang reports `'do_run' is a private member of 'Twice'`. Every derived class has to write that friend declaration, or make the hook public, which gives up NVI's encapsulation. Also, `run` becomes a template and must be defined in a header.

If run-time polymorphism isn't needed at all, you can drop the virtual functions and write the same skeleton with [[patterns/crtp|CRTP]] or with deducing this without virtual functions. Then there is no vptr, no common base type to put in containers, and errors in derived classes are reported only at instantiation. A comparison of the approaches:

| | NVI (virtual hook) | deducing-this wrapper + virtual hook | CRTP / purely static |
|---|---|---|---|
| Run-time polymorphism, fits in `vector<unique_ptr<Base>>` | yes | yes | no |
| Devirtualized when the concrete type is known | depends on the optimizer; Clang can't in our tests | yes | no virtual calls |
| Hook can be private | yes | needs `friend Base` | needs a friend |
| Wrapper can live in a `.cpp` file | yes | no (template) | no |
| Object size | one extra vptr | one extra vptr | unchanged |

When the algorithm itself should be replaceable at run time, rather than having derived classes fill in steps, see [[patterns/strategy]].

## When to use it

| Situation | Recommendation |
|---|---|
| A public polymorphic base whose interface has checking, locking, logging or statistics | NVI with a private hook |
| Derived classes need to call the base's default implementation in their overrides | NVI with a protected hook |
| An algorithm with a fixed skeleton and a few variable steps | template method |
| A virtual function needs default arguments | put the defaults on the non-virtual wrapper |
| The interface only forwards, with no common logic, now or ever | a public virtual function is fine; NVI only adds a name |
| A tiny hook called on a hot path, with the concrete type known at compile time | a deducing-this wrapper or CRTP |
| Wanting to run the skeleton from a constructor | don't; use two-phase construction and a factory function |

NVI's run-time cost is usually zero: the non-virtual wrapper is inlined, and the remaining virtual call is the same as with a public virtual function. Its main cost is one extra name per operation, and looking redundant when the interface has no common logic. Its benefit shows when the interface evolves: when the base later needs checks or statistics, only one place changes and derived classes are untouched.

## Questions

!!! question "1"
    `Base` has a public non-virtual function `run()` that calls a private virtual function `step()`. `Derived` declares its override of `step()` public, and `main` writes `Derived d; d.step();`. Does it compile? Does it bypass the checks in `run()`? What about `Base& b = d; b.step();`?

<details markdown="1">
<summary>Answer</summary>

`d.step()` compiles. Access is checked using the static type of the call expression ([[class.access.virt#2]]); the static type of `d` is `Derived`, and the `Derived::step` it finds is public. It does bypass the checks in `run()`, but only for code holding a `Derived`. `b.step()` does not compile: the static type is `Base`, `Base::step` is private, and the access of a virtual function is determined by its own declaration, not affected by overriders ([[class.access.virt#1]]). So a derived class widening access affects only its own users, not code that uses it through the base interface.
</details>

!!! question "2"
    A class's public virtual function `virtual void log(Level lv = Level::info);` is already overridden by dozens of derived classes, some of which write `Level lv = Level::debug`. How do you convert it to NVI without changing the behavior of calls through a base pointer? After the change, does the behavior of calling `log()` directly on a derived object change?

<details markdown="1">
<summary>Answer</summary>

Add a public non-virtual function `void log(Level lv = Level::info) { do_log(lv); }` to the base, rename the virtual function to a private `do_log(Level)`, drop all its default arguments, and rename the derived overriders accordingly. Calls through a base pointer already used the default from the base declaration, `Level::info` ([[dcl.fct.default#10]]), so their behavior is unchanged. A direct call to `log()` on a derived object used to take the default from that derived class's declaration, e.g. `Level::debug`; after the change the derived class no longer declares `log`, name lookup finds the base's wrapper, and the default is uniformly `Level::info`. That is a behavior change, but what it removes is exactly the split of one object having two sets of defaults.
</details>

!!! question "3"
    In `template-method-in-ctor.cpp` above, change `do_init` from a pure virtual function to an ordinary virtual function with an empty body. Is the program still UB? What does it print?

<details markdown="1">
<summary>Answer</summary>

It is no longer UB. While the `Plugin` base subobject is being constructed, `do_init()` dispatches to the final overrider in the constructor's class `Plugin` ([[class.cdtor#4]]), which is now an ordinary virtual function with a definition, so the call is entirely legal. The program prints `Plugin::init begin` and `Plugin::init end`, and `Audio::do_init` never runs. This is worse than a crash: there is no diagnostic at all, and the derived class's initialization is silently skipped.
</details>
