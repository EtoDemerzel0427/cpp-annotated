---
title: Factories and self-registration
summary: "Creating objects by name or ID without the caller knowing the concrete type: factory functions returning unique_ptr, clone and covariant return types, a registry mapping names to creator functions, self-registration through static objects in each translation unit and why it breaks with static libraries, deferred initialization, initialization order and threads, compile-time registries, and abstract factories."
tags: design patterns, factory, registry, static initialization, static libraries, linking
updated: 2026-10-19
---

!!! tldr
    - A factory function returns `std::unique_ptr<Base>`: ownership goes to the caller, and a caller that needs sharing can convert it straight to a `shared_ptr`. Covariant return types work only for pointers and references, so `unique_ptr<Derived>` cannot override a virtual function returning `unique_ptr<Base>`.
    - A registry maps names to creator functions. Self-registration puts the registration into the initialization of a global variable in each concrete type's `.cpp` file, so adding a type does not require changing any central file.
    - Self-registration depends on three things that neither the standard nor the linker guarantees: that the object file gets linked in (unreferenced members of a static library are dropped), that dynamic initialization happens before `main` (the standard allows deferring it), and that the registry is constructed before anything registers (initialization order across translation units is unspecified).
    - Putting the registry in a function-local static variable fixes the third. The first two require linker options (`-force_load`, `--whole-archive`) or having the main program explicitly reference every module.
    - When the set of types is known at compile time, generating the factory from a type list at compile time is simpler: no static initialization, no linking problems, and duplicate names can be rejected with `static_assert`.

## Creating objects by name

A configuration file says `circle` or `square`, and the program must create the corresponding object. The most direct approach is a long `if` chain:

```cpp run title="switch-factory.cpp" ok
#include <cstdio>
#include <memory>
#include <string_view>

struct Shape {
  virtual ~Shape() = default;
  virtual double area() const = 0;
};
struct Circle : Shape { double area() const override { return 3.14159; } };
struct Square : Shape { double area() const override { return 1.0; } };

std::unique_ptr<Shape> make_shape(std::string_view name) {
  if (name == "circle") return std::make_unique<Circle>();
  if (name == "square") return std::make_unique<Square>();
  return nullptr;                        // unknown name
}

int main() {
  for (auto n : {"circle", "square", "hexagon"}) {
    auto s = make_shape(n);
    std::printf("%s: %s\n", n, s ? "ok" : "unknown");
  }
}
```

The caller knows only `Shape` and a string and does not need to include `Circle`'s header. That is the whole point of a **factory**: the decision of which concrete type to create moves from the caller to one place.

The problem is that place itself. `make_shape` has to see the definitions of all concrete types, and every new type means changing and recompiling it. When types come from different teams, different libraries, or even plugins loaded at run time, this central file becomes a bottleneck.

## Factory functions return `unique_ptr<Base>`

The object a factory creates is handed to the caller, and the return type should express that transfer of ownership. The three common choices mean different things:

| Return type | Meaning | Problem |
|---|---|---|
| `Shape*` | unclear whether the caller must `delete` | leaks if the caller forgets to free it, or if an exception is thrown midway through an expression |
| `std::unique_ptr<Shape>` | the caller becomes the sole owner | none |
| `std::shared_ptr<Shape>` | the caller shares with the factory | forces every caller to pay for a control block |

`unique_ptr<Shape>` is the default choice. It is the same size as a raw pointer, and a caller that wants sharing can initialize a `shared_ptr<Shape>` directly from it; the reverse is impossible. Why `Shape` must have a virtual destructor, and the size and generated code of `unique_ptr`, are covered in [[topics/ownership-and-smart-pointers]].

You also have to choose how the factory fails. Above, a null pointer means the name is unknown, and the caller must check it; alternatives are throwing an exception or returning `std::expected<std::unique_ptr<Shape>, Error>`. When names come from external input, an unknown name is a normal situation, and a null pointer or `expected` fits better than an exception.

## Virtual constructors: clone

Constructors cannot be virtual: before a constructor is called, the type being constructed must already be known. Yet copying an object known only through a base reference requires exactly that, constructing by dynamic type. The idiomatic solution is a virtual function `clone`, in which each derived class copies itself; this idiom is often called a **virtual constructor**.

### Covariant return types apply only to pointers and references

The return type of an overriding function must generally be the same as that of the overridden function. ¶8 allows one exception: both are pointers to classes (or both references to classes), and the class returned by the derived version has the class returned by the base version as an accessible, unambiguous base. This is a **covariant return type** ([[g:covariant-return-type]], [[class.virtual#8]]).

<div class="compare" markdown="1">

```cpp title="raw.cpp" ok
struct Shape {
  virtual ~Shape() = default;
  virtual Shape* clone() const = 0;
};
struct Circle : Shape {
  Circle* clone() const override {
    return new Circle(*this);  // OK: covariant
  }
};
```

```cpp title="smart.cpp" error
#include <memory>
struct Shape {
  virtual ~Shape() = default;
  virtual std::unique_ptr<Shape>
  clone() const = 0;
};
struct Circle : Shape {
  std::unique_ptr<Circle>
  clone() const override;  // error
};
```

</div>

The right side is rejected because `unique_ptr<Circle>` is a class type, not a pointer to a class. `unique_ptr<Circle>` implicitly converts to `unique_ptr<Shape>`, but the two template specializations have no inheritance relationship, so none of ¶8's conditions hold. Clang reports `virtual function 'clone' has a different return type ('unique_ptr<Circle>') than the function it overrides`.

Why do covariant pointers work? When called through a `Shape&`, what actually runs is `Circle::clone`, and the `Circle*` it returns is converted to the return type of the statically chosen function, `Shape*` ([[class.virtual#9]]). For a pointer, this derived-to-base conversion is just an address adjustment, which the compiler can insert at the entry of the overrider or at the call site. Converting an arbitrary class type would require calling a converting constructor, which the standard does not let the virtual function mechanism do.

### Wrapping it in a non-virtual `clone`

To get both, separate the public interface that returns a smart pointer from the virtual function that does the work:

```cpp run title="clone.cpp" ok
#include <cstdio>
#include <memory>

class Shape {
public:
  virtual ~Shape() = default;
  std::unique_ptr<Shape> clone() const {
    return std::unique_ptr<Shape>(clone_impl());
  }
  virtual double area() const = 0;
private:
  virtual Shape* clone_impl() const = 0;
};

class Circle : public Shape {
public:
  explicit Circle(double r) : r_(r) {}
  std::unique_ptr<Circle> clone() const {  // hides Shape::clone
    return std::unique_ptr<Circle>(clone_impl());
  }
  double area() const override { return 3.14159 * r_ * r_; }
private:
  Circle* clone_impl() const override {    // covariant: raw pointers are fine
    return new Circle(*this);
  }
  double r_;
};

int main() {
  Circle c(2);
  std::unique_ptr<Circle> c2 = c.clone();  // static type is Circle
  const Shape& s = c;
  std::unique_ptr<Shape> s2 = s.clone();   // dispatches dynamically to Circle
  std::printf("%.2f %.2f\n", c2->area(), s2->area());
}
```

The raw pointer exists only for an instant between `clone_impl` and the wrapper, and is immediately handed to a `unique_ptr`. `Circle::clone` does not override `Shape::clone`, it hides it: calling through a `Circle` gives a `unique_ptr<Circle>`, calling through a `Shape` gives a `unique_ptr<Shape>`, and both dispatch dynamically through `clone_impl`. A non-virtual public function and a private virtual one is exactly the structure of [[patterns/nvi|the non-virtual interface]]; the two functions each derived class repeats can be generated by a [[patterns/crtp|CRTP]] base.

C++26's `std::polymorphic<T>` ([[polymorphic]]) makes this a library facility: it holds an object whose dynamic type may be a class derived from `T`, and copying it deep-copies by dynamic type without requiring the hierarchy to provide `clone`. At the time of writing, libc++ in our tests does not provide it yet.

## A registry: from names to creator functions

The first step in removing the central `if` chain is to turn it into data: a map from names to **creator** functions. The `shape.h` below contains only the `Shape` interface from the beginning.

```cpp title="registry.h"
#pragma once
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <string_view>
#include "shape.h"

class ShapeRegistry {
public:
  using Creator = std::unique_ptr<Shape> (*)();
  bool add(std::string name, Creator c) {
    return creators_.emplace(std::move(name), c).second;
  }
  std::unique_ptr<Shape> create(std::string_view name) const {
    auto it = creators_.find(name);
    return it == creators_.end() ? nullptr : it->second();
  }
  std::size_t size() const { return creators_.size(); }
private:
  std::map<std::string, Creator, std::less<>> creators_;
};

ShapeRegistry& shape_registry();
```

```cpp title="registry.cpp"
#include "registry.h"
ShapeRegistry& shape_registry() {
  static ShapeRegistry r;   // constructed on first call
  return r;
}
```

A few details:

- `std::less<>` is a transparent comparator, so `find` can look up a `string_view` directly without first constructing a `std::string`.
- Creators are plain function pointers. A non-capturing lambda converts implicitly to a function pointer, so you can still register lambdas. `std::function` is needed only when a creator must carry state (a configuration object, say); with libc++ in our tests it takes 32 bytes, against 8 for a function pointer.
- `add` returns `false` for a duplicate name. Whether to overwrite, ignore or report an error is a registry policy that should be decided in one place.
- The registry lives in a local static variable inside a function, not in a namespace-scope global. The reason is in the initialization order section below.

## Self-registration

With a registry in place, someone still has to call `add`. If a central function registers each type in turn, the problem has only moved. **Self-registration** has each concrete type register itself in its own `.cpp` file:

```cpp title="circle.cpp"
#include "registry.h"
namespace {
struct Circle : Shape {
  double area() const override { return 3.14159; }
};
const bool registered = shape_registry().add(
    "circle", [] () -> std::unique_ptr<Shape> {
      return std::make_unique<Circle>();
    });
}
```

`square.cpp` is written the same way. The main program depends only on the registry:

```cpp title="main.cpp"
#include <cstdio>
#include "registry.h"
int main(int argc, char** argv) {
  std::printf("%zu shapes registered\n", shape_registry().size());
  for (int i = 1; i < argc; ++i) {
    if (auto s = shape_registry().create(argv[i]))
      std::printf("%s: %.2f\n", argv[i], s->area());
    else
      std::printf("%s: unknown\n", argv[i]);
  }
}
```

`registered` is a namespace-scope variable with **static storage duration** ([[g:static-storage-duration]], [[basic.stc.static#1]]). Its initial value requires a function call to compute, so this is not constant initialization but **dynamic initialization** ([[g:dynamic-initialization]], [[basic.start.static#2]]). `add` is called during that dynamic initialization. `registered` itself is never read, but its initialization has side effects, so the implementation may not eliminate it as unused ([[basic.stc.static#2]]).

`Circle` is in an unnamed namespace, invisible to other translation units. Adding a shape only requires adding a `.cpp` file to the build; neither `main.cpp` nor the registry changes. Google Test's `TEST` macro works this way: each test expands to a class and a static member whose initialization registers the test in a global list.

Linking the four object files directly works fine:

```text
$ clang++ --ld-path=/usr/bin/ld main.o registry.o circle.o square.o -o direct
$ ./direct circle square
2 shapes registered
circle: 3.14
square: 1.00
```

This and the linking experiments below were done on arm64 macOS with Homebrew Clang 23 and the system linker `/usr/bin/ld` (`ld-1266.8`).

## Why self-registration breaks

Self-registration makes the existence of a type depend on a side effect: the initialization of some global variable having run before `main` queries the registry. That can fail in three places.

### Static libraries: unreferenced members are not linked

Pack `circle.o` and `square.o` into a static library, changing nothing else:

```text
$ llvm-ar rcs libshapes.a circle.o square.o
$ clang++ --ld-path=/usr/bin/ld main.o registry.o libshapes.a -o fromlib
$ ./fromlib circle square
0 shapes registered
circle: unknown
square: unknown
```

There is no error or warning, and both shapes have vanished. The linker links in every `.o` file on the command line, but from a static library it only extracts members that resolve some currently undefined symbol (see [[toolchain/linking-and-symbols]]). `main.o` and `registry.o` reference nothing in `circle.o`, and they cannot:

```text
$ llvm-nm -m --defined-only circle.o | grep ' external' | grep -vc weak
0
```

`circle.o` defines no non-weak external symbols. `Circle`, `registered` and the creator are all in an unnamed namespace with internal linkage; the remaining external symbols are weak definitions of inline functions from `std::map`, `std::string` and so on, which `registry.o` already has. This is exactly what self-registration wanted: nobody depends on the concrete type. To the linker, a member nobody depends on need not be linked, and so its global variable initialization does not exist.

The standard says nothing about this. Translation phase 8 only says library components are linked to satisfy references to entities not defined in the current translation ([[lex.phases#1]]); whether unreferenced components are part of the program, the standard does not say. This is a linker convention, not a language rule.

The fix is to make the linker pull in the whole library, or to make the main program reference each module explicitly:

```text
$ clang++ --ld-path=/usr/bin/ld main.o registry.o -Wl,-force_load,libshapes.a -o force
$ ./force circle
2 shapes registered
circle: 3.14
$ clang++ --ld-path=/usr/bin/ld main.o registry.o libshapes.a -Wl,-all_load -o allload
$ ./allload circle square
2 shapes registered
circle: 3.14
square: 1.00
```

| Method | What it does | Cost |
|---|---|---|
| Apple ld `-force_load,<lib>` | unconditionally extracts every member of this one library | unrelated members of the library come in too |
| Apple ld `-all_load` | does that for every static library | same, on a larger scale |
| GNU ld, lld `--whole-archive <lib> --no-whole-archive` (per documentation) | extracts every member of the enclosed libraries | forgetting to turn it off pulls in system libraries whole as well |
| MSVC `link /WHOLEARCHIVE:<lib>` (per documentation) | same | same |
| No static library; link object files directly (e.g. a CMake OBJECT library) | every `.o` is on the command line | the build scripts change |
| Anchor function: `circle.cpp` defines `void link_circle() {}`, and the main program calls it | the main program references each module | back to a central list |

`-Wl,-why_load` makes Apple ld print why each member was extracted, which helps when investigating:

```text
$ clang++ --ld-path=/usr/bin/ld main.o registry.o libshapes.a -Wl,-all_load -Wl,-why_load -o x
-force_load caused load of .../libshapes.a[3](square.o)
-force_load caused load of .../libshapes.a[2](circle.o)
```

We also verified the anchor function approach: add `void link_circle() {}` at the end of `circle.cpp` and call it from `main`, and `circle.o` is extracted from the library, bringing the count to 1 (`square.o` is still missing).

!!! note "Dead stripping is not a problem"
    Once an object file is linked in, its self-registration is not removed by `-Wl,-dead_strip`. Linking the four `.o` files with `-dead_strip` in our tests still registered both shapes. The initialization functions for global variables are listed in the Mach-O `__mod_init_func` section (`.init_array` on ELF), which the linker treats as roots, and everything reachable from them is kept. This agrees with [[basic.stc.static#2]].

### Dynamic initialization can be deferred

Even when the object file is linked in, the standard does not guarantee that `registered` is initialized before `main`. For a non-block, non-inline variable with static storage duration, whether dynamic initialization completes before the first statement of `main` or is deferred is implementation-defined ([[basic.start.dynamic#5]]) {{impl}}.

If it is deferred, the standard only requires it to happen before any **non-initialization odr-use** ([[g:non-initialization-odr-use]], i.e. an [[g:odr-use|odr-use]] not caused directly or indirectly by the initialization of some static variable, [[basic.start.dynamic#4]]) of any non-inline function or variable defined in the same translation unit. A footnote adds that at that point, every variable in the same translation unit whose initialization has side effects must be initialized, even if it is not itself odr-used.

Apply this rule to `circle.cpp`: the whole purpose of self-registration is that nobody uses anything in this translation unit. Looking up the registry calls the creator through a function pointer, which does not name any function in `circle.cpp`, so it is not an odr-use. If the implementation chooses to defer, nothing ever forces `registered` to be initialized, and the standard allows `circle` never to appear in the registry.

Mainstream implementations do not defer initialization of ordinary globals (see the implementation notes in [[basic.start]]), so in statically linked programs this rule is mostly theoretical. The real-world reason for allowing deferral is dynamic libraries: the globals of a shared library loaded with `dlopen` can only be initialized when it is loaded. In our tests, with `square.cpp` built as `libsquare.dylib` and the registry in a `libreg.dylib` shared by the main program and the plugin:

```text
$ ./m
before dlopen: 1
after dlopen: 2
```

The plugin's self-registration runs before `dlopen` returns. This is exactly what a plugin system wants, but it means registration can happen after `main` has started, while other threads are querying the registry; see the thread safety section below.

### The registry's own initialization order

Suppose the registry is an ordinary global variable, and its constructor does something, such as pre-registering a built-in type (with a corresponding constructor declaration added to `registry.h`):

```cpp title="registry.cpp (broken version)" ub
#include "registry.h"
namespace {
struct Empty : Shape { double area() const override { return 0; } };
}
ShapeRegistry::ShapeRegistry() {
  add("empty", [] () -> std::unique_ptr<Shape> {
    return std::make_unique<Empty>();
  });
}
ShapeRegistry g_registry;                     // namespace scope
ShapeRegistry& shape_registry() { return g_registry; }
```

`registered` in `circle.cpp` and `g_registry` in `registry.cpp` are in different translation units. Both are ordered variables, but ordered variables are ordered by definition only within the same translation unit ([[basic.start.dynamic#3]]); the order across translation units is unspecified. If `registered` is initialized first, `add` accesses a `std::map` that has not been constructed yet. This is the **static initialization order fiasco** ([[g:static-initialization-order-fiasco]]), UB.

In our tests the result depends on link order:

```text
$ clang++ --ld-path=/usr/bin/ld main.o registry.o circle.o square.o -o g1 && ./g1 circle empty
3 shapes registered
circle: 3.14
empty: 0.00
$ clang++ --ld-path=/usr/bin/ld main.o circle.o square.o registry.o -o g2 && ./g2 circle empty
Segmentation fault: 11
```

With `-fsanitize=address,undefined`, UBSan first reports `member access within null pointer` in libc++'s `__tree`, then ASan reports a SEGV whose stack bottoms out in `__cxx_global_var_init` at `circle.cpp:6`. dyld in our tests runs each translation unit's initialization functions in the order the object files appear on the command line; this is an observation, not a guarantee of any specification.

!!! impl "Why nothing went wrong without the constructor"
    Remove the constructor above, leaving just a `std::map` member, and both link orders work in our tests. The reason is that Clang turns the construction of `g_registry` into static initialization: the generated initialization function only registers the destructor with `__cxa_atexit`, and the contents of the `map` come straight from zero-initialization and constant data. [[basic.start.static#3]] allows implementations to do this, even though the standard does not require it (`constinit ShapeRegistry r;` is rejected, showing it is not constant initialization). That the code happens not to crash does not make it correct.

The fix is what `registry.cpp` above already does: put the registry in a function-local static variable. A block-scope static variable is initialized the first time control passes through its declaration ([[stmt.dcl#3]]), so whichever translation unit calls `shape_registry()` first gets an already constructed object. With this version, both link orders gave the same result in our tests. This technique and its destruction-order problems are discussed in detail in [[patterns/singleton]].

## Registering in a header: inline variables

Sometimes you want the registration in a header, for a header-only library, or so that registration travels with the type definition. A header is included by several translation units, and the variable's linkage determines how many times registration happens:

```cpp title="triangle.h"
#pragma once
#include <cstdio>
#include "registry.h"
struct Triangle : Shape {
  double area() const override { return 0.5; }
};
inline const bool triangle_registered = [] {  // what happens without inline?
  bool ok = shape_registry().add("triangle", [] () -> std::unique_ptr<Shape> {
    return std::make_unique<Triangle>();
  });
  std::printf("add(\"triangle\") -> %s\n", ok ? "true" : "false");
  return ok;
}();
```

Two `.cpp` files include this header. Running it in our tests:

| Declaration | Output |
|---|---|
| `inline const bool` | `add("triangle") -> true`, called once |
| `const bool` or `static const bool` | one `true` and one `false`; each translation unit registers once |

A namespace-scope `const` variable that is neither `inline` nor declared `extern` has internal linkage ([[basic.link#3.2]]), so every translation unit including the header has its own copy and initializes it separately. An `inline` variable ({{c++17}}, [[P0386R2]]) can be defined in multiple translation units but is one entity with one address ([[dcl.inline#2]]), and the implementation uses a guard variable to ensure it is initialized only once.

The initialization of an inline variable is **partially-ordered** ([[basic.start.dynamic#1]]), and if deferred it need only happen before a non-initialization odr-use of that variable itself ([[basic.start.dynamic#6]]). It does not solve the static library problem: registration happens only if some object file that includes `triangle.h` is linked in.

### Automatic registration through a static member of a class template

A more common approach has each concrete type inherit from a template base whose static data member performs the registration, so the concrete type writes no registration code at all:

```cpp title="autoreg.h"
#pragma once
#include "registry.h"

template <class D>
struct AutoRegister {
  static std::unique_ptr<Shape> create() { return std::make_unique<D>(); }
  static inline const bool registered =
      shape_registry().add(D::name, &create);
};
```

```cpp title="circle.h"
#pragma once
#include "autoreg.h"
struct Circle : Shape, AutoRegister<Circle> {
  static constexpr const char* name = "circle";
  double area() const override { return 3.14159; }
};
```

In our tests, with `circle.h` included in two translation units, the program prints `0 shapes registered`.

The reason is in [[temp.inst#4]]: when a class template specialization is implicitly instantiated, only the declarations of its static data members are instantiated; a member's definition is instantiated, and its initialization and side effects happen, only when the member is used in a way that requires its definition to exist. `AutoRegister<Circle>` is instantiated (it is a base of `Circle`), but nobody uses `registered`, so its initialization does not exist at all. [[temp.inst#12]] also explicitly forbids implementations from instantiating a static data member when it is not required.

The fix is to put an odr-use in each concrete type, forcing instantiation:

```cpp
struct Square : Shape, AutoRegister<Square> {
  static constexpr const char* name = "square";
  static constexpr const bool& anchor = registered;  // odr-use
  double area() const override { return 1.0; }
};
```

Binding a reference uses the address of `registered` without reading its value; that is an odr-use, and the definition of `registered` is instantiated along with it. With this line added, `square` appears in the registry in our tests, and it registers only once even though two translation units include `square.h`. Initialization of a static data member of a class template is **unordered** ([[basic.start.dynamic#1]]), with no specified order relative to any variable in other translation units, so the registry still has to be a function-local static.

!!! pitfall "Triggering instantiation through a virtual function is not portable"
    Another technique that circulates puts a virtual function that uses `registered` into `AutoRegister`, hoping the virtual function is instantiated together with the class's vtable. [[temp.inst#12]] says it is unspecified whether a virtual member function that would not otherwise be instantiated is implicitly instantiated {{unspec}}. The trick may work with one compiler and silently fail with another.

## Thread safety

The registry may be accessed at three times, with different safety requirements:

1. During static initialization before `main`. If the program starts no other threads at that point, initializations of ordered variables in the same translation unit are ordered by definition, and the rest are at most indeterminately sequenced ([[basic.start.dynamic#3]]), never simultaneous. Once some initialization starts a thread, which thread each initialization runs on is unspecified, and they may be concurrent.
2. Read-only after `main` starts. Multiple threads calling `const` member functions of `std::map` concurrently do not cause a data race ([[res.on.data.races]]), so no lock is needed.
3. Plugins loaded while running. `dlopen` triggers registration (a write) on one thread while other threads look things up (reads): that is a **data race** ([[g:data-race]]), UB ([[intro.races]]).

Initialization of a function-local static variable is itself thread-safe: if several threads enter the declaration for the first time concurrently, the others wait for initialization to complete ([[stmt.dcl#3]]). But that only protects construction, not the later `add` and `create`. For case 3, use a reader-writer lock:

```cpp run title="locked-registry.cpp" ok
#include <cstdio>
#include <map>
#include <memory>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <string_view>
#include <thread>

struct Shape {
  virtual ~Shape() = default;
  virtual double area() const = 0;
};
struct Circle : Shape { double area() const override { return 3.14; } };

class ShapeRegistry {
public:
  using Creator = std::unique_ptr<Shape> (*)();
  bool add(std::string name, Creator c) {
    std::unique_lock lock(m_);                 // write: exclusive
    return creators_.emplace(std::move(name), c).second;
  }
  std::unique_ptr<Shape> create(std::string_view name) const {
    Creator c = nullptr;
    {
      std::shared_lock lock(m_);               // read: shared
      auto it = creators_.find(name);
      if (it == creators_.end()) return nullptr;
      c = it->second;
    }
    return c();                                // construct the object outside the lock
  }
private:
  mutable std::shared_mutex m_;
  std::map<std::string, Creator, std::less<>> creators_;
};

ShapeRegistry& shape_registry() {
  static ShapeRegistry r;                      // initialization is thread-safe
  return r;
}

int main() {
  auto make = [] () -> std::unique_ptr<Shape> { return std::make_unique<Circle>(); };
  shape_registry().add("circle", make);
  std::jthread plugin([&] {                    // simulates loading a plugin while running
    for (int i = 0; i < 1000; ++i) shape_registry().add("p" + std::to_string(i), make);
  });
  int found = 0;
  for (int i = 0; i < 1000; ++i) found += shape_registry().create("circle") != nullptr;
  std::printf("%d\n", found);
}
```

Run with `-fsanitize=thread` in our tests, it reports nothing. Remove the two locking statements and TSan reports a `data race` in libc++'s `__tree_balance_after_insert`. The creator is called outside the lock, so even if a shape's constructor queries the registry in turn, it cannot deadlock on the same lock.

Programs that don't need run-time registration can be simpler: agree that all registration finishes before `main`, after which the registry is read-only and unlocked. Calling a `freeze()` at the start of `main`, after which every `add` reports an error, turns the convention into a check.

## Compile-time registries

All the trouble with self-registration comes from one premise: the set of types is not settled until link time or even run time. If the set of types is known at compile time, the same factory can be generated entirely at compile time:

```cpp run title="type-list-factory.cpp" ok
#include <array>
#include <cstdio>
#include <memory>
#include <string_view>

struct Shape {
  virtual ~Shape() = default;
  virtual double area() const = 0;
};
struct Circle : Shape {
  static constexpr std::string_view name = "circle";
  double area() const override { return 3.14159; }
};
struct Square : Shape {
  static constexpr std::string_view name = "square";
  double area() const override { return 1.0; }
};

template <class... Ts> struct type_list {};
using all_shapes = type_list<Circle, Square>;  // the only list to maintain

template <class... Ts>
consteval bool unique_names(type_list<Ts...>) {
  std::array<std::string_view, sizeof...(Ts)> n{Ts::name...};
  for (std::size_t i = 0; i < n.size(); ++i)
    for (std::size_t j = i + 1; j < n.size(); ++j)
      if (n[i] == n[j]) return false;
  return true;
}
static_assert(unique_names(all_shapes{}), "duplicate shape name");

template <class... Ts>
std::unique_ptr<Shape> make_shape(std::string_view name, type_list<Ts...>) {
  std::unique_ptr<Shape> r;
  (void)((name == Ts::name && (r = std::make_unique<Ts>(), true)) || ...);
  return r;
}

int main(int argc, char** argv) {
  for (int i = 1; i < argc; ++i) {
    auto s = make_shape(argv[i], all_shapes{});
    std::printf("%s: %s\n", argv[i], s ? "ok" : "unknown");
  }
}
```

The fold expression in `make_shape` expands over `||`; each term compares one name, and on a match creates the object and short-circuits. At `-O2` in our tests the whole of `make_shape` is inlined into `main`: it calls `strlen`, returns null immediately if the length is not 6, and otherwise checks the 6 bytes with two integer comparisons. There is no `std::map`, no heap nodes, and the program needs no dynamic initialization at all. Duplicate names are rejected at compile time by `static_assert`, whereas the self-registration version can only detect them at run time from the return value of `add`.

The cost is that `all_shapes` is a central list again, and its translation unit must see the complete definition of every type. This is the same dependency as the `if` chain at the start, just more compact and checkable at compile time. When one team controls the set of types, this is usually the best choice; when the set must be extended by modules that don't know about each other, you are back to run-time registration. Techniques such as type lists and fold expressions are covered in [[topics/compile-time-programming]].

### C++26 static reflection

C++26 static reflection ([[meta.reflection]], [[P2996R13]]) offers another way to produce the type list: `std::meta::members_of` can list the members of a namespace declared before the current point ([[meta.reflection.member.queries]]), and `is_base_of_type` filters out the classes derived from `Shape`, so `all_shapes` need not be written by hand. Below is a sketch based on the current draft; Clang 23 does not provide `<meta>`, so it has not been verified and carries no verdict:

```cpp
#include <meta>
namespace shapes { /* all concrete shapes are defined here */ }

consteval auto shape_types() {
  std::vector<std::meta::info> v;
  for (auto r : members_of(^^shapes, std::meta::access_context::unprivileged()))
    if (is_type(r) && is_class_type(r) && is_complete_type(r) &&
        is_base_of_type(^^Shape, r))
      v.push_back(r);
  return std::define_static_array(v);
}
```

It can still see only types already declared in the current translation unit, so you still need one translation unit that includes every shape header. What it saves is the hand-written list; it does not change the dependency structure of a compile-time registry.

## Abstract factories

The factories so far create one object at a time. Sometimes you need a family of matching objects, such as the buttons and checkboxes of one UI theme, where mixing widgets from two themes is a bug. An **abstract factory** puts a family of creator functions into one interface:

```cpp run title="abstract-factory.cpp" ok
#include <cstdio>
#include <memory>

struct Button   { virtual ~Button() = default;   virtual void draw() const = 0; };
struct Checkbox { virtual ~Checkbox() = default; virtual void draw() const = 0; };

struct WidgetFactory {
  virtual ~WidgetFactory() = default;
  virtual std::unique_ptr<Button>   button() const = 0;
  virtual std::unique_ptr<Checkbox> checkbox() const = 0;
};

struct DarkButton : Button { void draw() const override { std::puts("dark button"); } };
struct DarkCheckbox : Checkbox { void draw() const override { std::puts("dark checkbox"); } };
struct DarkFactory : WidgetFactory {
  std::unique_ptr<Button> button() const override { return std::make_unique<DarkButton>(); }
  std::unique_ptr<Checkbox> checkbox() const override { return std::make_unique<DarkCheckbox>(); }
};

void build_dialog(const WidgetFactory& f) {  // doesn't know which theme
  f.button()->draw();
  f.checkbox()->draw();
}

int main() { build_dialog(DarkFactory{}); }
```

The widgets `build_dialog` gets always come from the same factory. The concrete factory itself can be created by name through the registry above; the two patterns often appear together. When the theme is fixed at compile time, the factory can become a template parameter instead, see [[patterns/policy-based-design]], which removes the virtual calls and lets the compiler inline.

## Costs

The numbers below come from arm64 macOS, Clang 23 `-O2`, libc++, with 32 entries in the registry, averaged over ten million iterations.

| Item | Observation |
|---|---|
| Create and destroy one object directly with `make_unique` | about 25 ns, mostly one `new` and one `delete` |
| Create and destroy by name through the registry | about 36 ns |
| Of which `std::map` lookup by `string_view` | about 12 ns |
| Creator: function pointer / `std::function` | 8 / 32 bytes |
| Each self-registered type | one function call before `main`, one `map` node, one string |
| Type-list factory | inlined into length and integer comparisons, no dynamic initialization |

Lookup by name costs about as much as one heap allocation. Factories are typically used where strings are being parsed anyway, such as reading configuration or deserializing, so this overhead is rarely a problem; creating objects by name in a hot loop is a design problem, and the lookup result (the creator function pointer) should be cached.

The bigger cost is not at run time but in understandability: which types a self-registering program contains cannot be seen by reading the source; you have to look at the build system and the linker options.

## Common pitfalls

!!! pitfall "Self-registration in a static library silently disappears"
    No link error, no warning, just something missing from the registry. Unit tests linking the `.o` files directly pass, and the release built as a static library fails: this is the most typical failure of the pattern. When the registration count is wrong, first check whether the object file was extracted, with `-Wl,-why_load` (Apple ld) or the linker map file.

!!! pitfall "Writing `const bool registered` in a header"
    A namespace-scope `const` variable has internal linkage by default, so every translation unit including the header registers once. Use `inline`.

!!! pitfall "Using the registry during static initialization"
    If another global variable's initialization calls `shape_registry().create(...)`, whether it finds a given type depends on whether that type's self-registration has already run, and the order across translation units is unspecified. A function-local static only guarantees that the registry itself has been constructed, not that its contents are complete.

!!! pitfall "The registry is destroyed before its users"
    Function-local statics are destroyed at `exit` in reverse order of the completion of their construction ([[basic.start.term#4]]). If some static object finishes construction before the registry is constructed and then accesses the registry in its destructor, it accesses a destroyed object. The usual workaround is to never destroy the registry: `static auto* r = new ShapeRegistry; return *r;`, at the cost of leak detectors reporting it.

## When to use it

| Situation | Recommendation |
|---|---|
| A small set of types maintained by one team | a compile-time type list, or just write the `if` chain |
| Creation by name, with the set of types fixed at build time, but adding a type should not touch a central file | self-registration with the registry in a function-local static; link object files directly, or use whole-archive linker options for static libraries |
| Plugins loaded at run time | an explicit registration entry point (the plugin exports a `register_plugin(Registry&)` function that the loader calls), with a locked registry |
| Copying an object known only through its base | a non-virtual `clone` wrapping a private virtual `clone_impl`; in C++26 consider `std::polymorphic` |
| A family of matching objects | an abstract factory; a template parameter when the theme is fixed at compile time |
| Just hiding construction details | an ordinary factory function is enough, no registry needed |

For plugins, an explicit entry point is recommended over self-registration: after `dlopen`, find the entry function with `dlsym` and call it. The loader then decides when and on which thread registration happens, nothing depends on global variable initialization, and errors can be reported against a specific plugin.

## Questions

!!! question "1"
    `registered` in `circle.cpp` is never read, and `Circle` is not referenced by any other translation unit. Why does registration still work when `circle.o` is linked directly with `-Wl,-dead_strip`? And it fails when `circle.o` is put in a static library; what is the difference between the two cases?

<details markdown="1">
<summary>Answer</summary>

`-dead_strip` marks reachable code and data starting from roots, and each translation unit's initialization function is listed in the `__mod_init_func` section, which is a root. The initialization function calls `add` and refers to the creator, so both are kept. This agrees with [[basic.stc.static#2]]: an initialization with side effects may not be eliminated.

The static library problem happens at an earlier stage: the linker never treats `circle.o` as part of the program. Phase 8 in [[lex.phases#1]] only says library components are linked to satisfy references to external entities; an unreferenced library member is not part of the program, and rules like [[basic.stc.static#2]] never get to apply. The former is an optimization of the program, constrained by language rules; the latter decides what the program consists of, which the standard does not govern.
</details>

!!! question "2"
    `registered` in `AutoRegister<D>` is a `static inline const bool`. If it were instead a `static inline` member of an ordinary, non-template class, would `anchor` still be needed?

<details markdown="1">
<summary>Answer</summary>

No. The rule in [[temp.inst#4]] applies only to members of templated entities: when a class template specialization is instantiated, the definitions of its static data members are not instantiated with it. An inline static data member of an ordinary class is a definition right there in the class definition, every translation unit that includes it has that definition, and its dynamic initialization, like that of any other inline variable, is partially-ordered ([[basic.start.dynamic#1]]) and runs before `main` on mainstream implementations.

The price is losing the automation: every class has to write its own registration statement. The `anchor` line essentially gives the template version the definition an ordinary class has anyway.
</details>

!!! question "3"
    A self-registering shape module defines a static object `Unregistrar` whose destructor calls `shape_registry().remove("circle")`. Is this safe at program exit?

<details markdown="1">
<summary>Answer</summary>

If `Unregistrar` called `shape_registry()` during its construction (for example, if its constructor performs the registration), it is safe. The registry's construction completes before `Unregistrar`'s, and [[basic.start.term#4]] says objects whose construction completed first are destroyed later, so the registry still exists when `Unregistrar` is destroyed.

If `Unregistrar`'s constructor did not call `shape_registry()`, and the registry was constructed later by someone else's first call, then the registry's construction completes later and it is destroyed first; `Unregistrar`'s destructor accesses a destroyed object, which is UB. Whether it is safe depends on whether the registry was touched first during construction, which is exactly why the never-destroyed registry technique is popular.
</details>

## Summary

| Question | Conclusion | Source |
|---|---|---|
| Can `unique_ptr<Derived>` be a covariant return type? | No; covariance applies only to pointers and references to classes | [[class.virtual#8]] |
| Result of a covariant overrider | converted to the return type of the statically chosen function | [[class.virtual#9]] |
| Is a self-registration variable that nobody reads removed? | No; an initialization with side effects may not be eliminated | [[basic.stc.static#2]] |
| Are globals always initialized before `main`? | implementation-defined; it may be deferred | [[basic.start.dynamic#5]] |
| Initialization order across translation units | unspecified | [[basic.start.dynamic#3]] |
| When is a function-local static initialized, and is it thread-safe? | the first time control passes its declaration; concurrent threads wait | [[stmt.dcl#3]] |
| A `const` variable in a header | internal linkage, one copy per translation unit | [[basic.link#3.2]] |
| Inline variables | defined in many places, one entity | [[dcl.inline#2]] |
| When is a static data member of a class template initialized? | only instantiated and initialized when used in a way that requires its definition | [[temp.inst#4]] |
| Are static library members linked? | the standard doesn't say; linkers extract only referenced members | [[lex.phases#1]] |
