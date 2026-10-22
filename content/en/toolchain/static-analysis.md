---
title: Compiler warnings and static analysis
summary: "Finding defects before running: what the standard requires compilers to diagnose and what it doesn't, which warnings -Wall, -Wextra and -pedantic actually enable, a recommended set of warning options and the errors each catches, -Werror and third-party headers, lifetime and thread-safety annotations, using clang-tidy, the Clang static analyzer and clang-format, and what static analysis can't do."
group: Engineering practice
tags: toolchain, warnings, clang-tidy, static analysis, UB, IFNDR
updated: 2026-10-19
---

!!! tldr
    - The standard only requires compilers to issue at least one diagnostic for programs that violate diagnosable rules; rules that require no diagnostic (IFNDR) and undefined behavior (UB) aren't included. Warnings are the implementation's own addition, and how many are on is decided by the command line.
    - `-Wall` isn't all warnings: with Clang 23 it enables only 59 more than the default, and `-Wextra` 19 more. Common mistakes such as implicit conversions, shadowing, non-virtual destructors, old-style casts and `switch` fall-through all need their own options.
    - `-Weverything` includes many warnings unrelated to correctness (C++98 compatibility, struct padding); it is good for discovering which warnings exist, not for building with directly.
    - Annotations (`[[clang::lifetimebound]]`, thread-safety attributes) write conventions the compiler can't see into the code, letting local analysis cross function boundaries. clang-tidy checks style and idioms, and the static analyzer follows execution paths to find null pointers and leaks.
    - Static analysis works per translation unit and reasons without knowing run-time data; ODR violations across translation units and input-dependent UB need link-time checks, tests and sanitizers.

!!! note "Test setup"
    Homebrew Clang 23.1.3 (libc++), clang-tidy 23.1.3, scan-build (installed with Homebrew LLVM), CMake 3.29, Ninja, Apple M2 Pro. GCC wasn't installed; anything about GCC is description only and wasn't verified. Long paths in output have been shortened.

## Code that `-Wall -Wextra` doesn't warn about

```cpp title="misc.cpp"
#include <string>

struct Shape {
  virtual double area() const = 0;
  ~Shape() = default;               // non-virtual destructor
};

class Account {
  int balance;
public:
  explicit Account(int balance) : balance(balance) {}
  void deposit(int amount) {
    int balance = this->balance + amount;  // shadows the member
    (void)balance;
  }
};

int parse_level(const char* s) {
  int level = 0;
  switch (s[0]) {
  case 'e': level = 3;              // forgot break
  case 'w': level = 2; break;
  default:  level = 1;
  }
  return level;
}

void write(const std::string& s) {
  char* p = (char*)s.data();        // casts away const
  p[0] = 'X';
}
```

This code is well-formed, and `clang++ -std=c++2c -Wall -Wextra -pedantic` gives no warnings. But it has four defects: deleting a derived object through a `Shape*` is UB ([[expr.delete#3]]); `deposit` modifies a local variable instead of the member; `'e'` falls into the `'w'` branch; and `write` casts away `const`, so if the argument refers to a `const` object, the write is UB.

Add four options that aren't in `-Wall` or `-Wextra`, and the compiler points out all of them:

```text
$ clang++ -std=c++2c -Wall -Wextra -pedantic -Wshadow-all -Wnon-virtual-dtor \
    -Wold-style-cast -Wimplicit-fallthrough -fsyntax-only misc.cpp
misc.cpp:5:3: warning: 'Shape' has virtual functions but non-virtual destructor [-Wnon-virtual-dtor]
misc.cpp:11:24: warning: constructor parameter 'balance' shadows the field 'balance' of 'Account' [-Wshadow-field-in-constructor]
misc.cpp:13:9: warning: declaration shadows a field of 'Account' [-Wshadow]
misc.cpp:22:3: warning: unannotated fall-through between switch labels [-Wimplicit-fallthrough]
misc.cpp:22:3: note: insert '[[fallthrough]];' to silence this warning
misc.cpp:22:3: note: insert 'break;' to avoid fall-through
misc.cpp:29:13: warning: use of old-style cast [-Wold-style-cast]
5 warnings generated.
```

Why aren't these warnings in `-Wall`? Because they also fire on correct code: a constructor parameter with the same name as a member is a common idiom, and deliberate fall-through is common too. Compilers enable by default only warnings with very few false positives, and leave the rest for each project to choose according to its own style.

## What the standard requires to be diagnosed

The standard divides rules into two kinds. **Diagnosable rules** are all syntactic and semantic rules except those explicitly marked "no diagnostic is required" and those that result in UB ([[intro.compliance.general#1]]). ¶2.3 says that if a program violates any diagnosable rule, a conforming implementation must issue at least one **diagnostic message**.

!!! std
    If a program contains a violation of a rule for which no diagnostic is required, this document places no requirement on implementations with respect to that program.

This is ¶2.2: if a rule that requires no diagnostic is violated, the standard places no requirements on the implementation at all, and it may silently compile to anything. That gives three kinds of program error:

| Kind | Examples | What the standard requires of implementations | Effect in practice |
|---|---|---|---|
| Ill-formed, diagnostic required | An array of size 0 ([[dcl.array#1]]), narrowing list-initialization ([[dcl.init.list#3]]) | At least one diagnostic ([[intro.compliance.general#2]]) | Usually an error; a warning when accepted as an extension |
| Ill-formed, no diagnostic required ([[g:ifndr]]) | Different definitions of a same-named class in two translation units ([[basic.def.odr#16]]), an odr-used function with no definition ([[basic.def.odr#12]]) | Nothing | May compile and link successfully, with unpredictable behavior |
| Undefined behavior ([[g:undefined-behavior]]) | Signed overflow, null pointer dereference, data races ([[intro.races#17]]) | Nothing | Depends on run-time values; the optimizer assumes it doesn't happen |

IFNDR usually exists because a diagnosis would be too expensive or impossible: checking the ODR requires seeing all translation units at once, while the compiler processes one at a time. UB mostly depends on run-time data; when compiling `a + b`, the compiler doesn't know whether it will overflow. So compilers in principle can't diagnose every error, and warnings and static analysis are best-effort within these two categories. UB is discussed in full in [[topics/undefined-behavior]].

What a diagnostic message is is implementation-defined ([[defns.diagnostic]]); the standard doesn't distinguish warnings from errors. A single warning satisfies the obligation to diagnose, after which the implementation may still compile the program. That is exactly how compiler extensions work ([[intro.compliance.general#11]]):

```cpp title="ext.cpp" error
struct Packet {
  int len;
  char data[0];                        // zero-length array
};

int pick(int* p, int fallback) {
  int* q = p ?: &fallback;             // ?: with the middle operand omitted
  return ({ int t = *q; t + 1; });     // statement expression
}
```

None of the three is C++: an array's size must be greater than zero ([[dcl.array#1]]), and the other two are GNU extension syntax. Clang reports nothing by default or with `-Wall -Wextra`; only `-pedantic` gives three warnings, and `-pedantic-errors` turns them into errors:

```text
$ clang++ -std=c++2c -Wall -Wextra -pedantic -fsyntax-only ext.cpp
ext.cpp:3:13: warning: zero size arrays are an extension [-Wzero-length-array]
ext.cpp:7:15: warning: use of GNU ?: conditional expression extension, omitting middle operand [-Wgnu-conditional-omitted-operand]
ext.cpp:8:11: warning: use of GNU statement expression extension [-Wgnu-statement-expression]
3 warnings generated.
```

In other words, Clang without `-pedantic` isn't a conforming implementation on this example. When code needs to compile on other compilers, turn on `-pedantic` (the same as `-Wpedantic`). Variable-length arrays `int buf[n];` are an exception: Clang 23 warns about them with `-Wvla-cxx-extension` by default.

The standard also directly encourages some warnings. The recommended practice for `[[fallthrough]]` is that it suppress warnings about fall-through ([[dcl.attr.fallthrough#2]]), and for `[[nodiscard]]` that a warning be issued when the return value is discarded ([[dcl.attr.nodiscard#4]]). These are Recommended practice, not requirements.

## What `-Wall`, `-Wextra` and `-pedantic` enable

Homebrew LLVM comes with `diagtool`, which lists the warnings actually enabled under a set of options. Counts on our test machine for an empty file (each line is one warning, counted by Clang's internal diagnostic ID):

| Option | Warnings enabled | More than default |
|---|---|---|
| Default | 1450 | 0 |
| `-Wall` | 1509 | 59 |
| `-Wextra` | 1469 | 19 |
| `-pedantic` | 1623 | 173 |
| `-Weverything` | 2265 | 815 |

```text
$ diagtool show-enabled --no-levels -Wall e.cpp | wc -l
    1509
$ diagtool tree -Wextra
-Wextra
  -Wdeprecated-copy
  -Wmissing-field-initializers
  -Wignored-qualifiers
  -Wsign-compare
  -Wunused-parameter
  ...
```

The 1450 on by default include many warnings directly related to correctness: returning the address of a local variable (`-Wreturn-stack-address`), dangling references (`-Wdangling`), ignoring a `[[nodiscard]]` return value (`-Wunused-result`), and a `switch` missing enumerators (`-Wswitch`). `-Wall` adds things like unused variables, uninitialized reads, `printf` formats, member initialization order and redundant `std::move`. `-Wextra` adds signed/unsigned comparisons, unused parameters and so on. Almost all of the 173 added by `-pedantic` are extension diagnostics whose names start with `ext_`.

Together the three add 246 over the default, while `-Weverything` adds 815; the remaining 569 are never enabled by these three options, and the warnings recommended in the next section are all among them.

### The noise of `-Weverything`

The program below has no defects, and `-Wall -Wextra -pedantic` gives no warnings:

```cpp title="clean.cpp" run ok
#include <cstdio>
#include <span>
#include <string>
#include <vector>

struct Point {
  double x;
  char tag;
};

double total(std::span<const double> xs) {
  double s = 0;
  for (std::size_t i = 0; i < xs.size(); ++i) s += xs[i];
  return s;
}

int main(int argc, char** argv) {
  std::vector<double> v{1.0, 2.0, 3.0};
  auto label = std::string("sum");
  Point p{total(v), 'a'};
  std::printf("%s: %s = %g %c\n", argv[0], label.c_str(), p.x, p.tag);
  return argc > 1;
}
```

`-Weverything` gives 7 warnings:

```text
clean.cpp:11:8: warning: no previous prototype for function 'total' [-Wmissing-prototypes]
clean.cpp:18:24: warning: generalized initializer lists are incompatible with C++98 [-Wc++98-compat]
clean.cpp:18:24: warning: initialization of initializer_list object is incompatible with C++98 [-Wc++98-compat]
clean.cpp:19:3: warning: 'auto' type specifier is incompatible with C++98 [-Wc++98-compat]
clean.cpp:20:10: warning: generalized initializer lists are incompatible with C++98 [-Wc++98-compat]
clean.cpp:6:8: warning: padding size of 'Point' with 7 bytes to alignment boundary [-Wpadded]
clean.cpp:21:3: warning: function 'printf' is unsafe [-Wunsafe-buffer-usage-in-libc-call]
```

Four say this code can't be compiled as C++98, one reports that a struct has padding (layout is covered in [[toolchain/object-layout-and-vtables]]), one wants non-`static` functions to have a prior declaration, and one belongs to `-Wunsafe-buffer-usage`, a group of checks designed for rewriting an entire codebase. Each of these warnings has its uses, but none of them is a defect.

Recommendation: use `-Weverything` for browsing: run it once on your code to see which warnings are worth adding to the project's list, then build with an explicit list of `-W...` options. Some projects do the reverse, `-Weverything` plus a string of `-Wno-...`; the cost is that every compiler upgrade brings new warning groups, which may break the build.

## A recommended set of warnings

A suggested starting point (Clang; GCC's option names are mostly the same, but the grouping isn't entirely):

```text
-Wall -Wextra -Wpedantic
-Wconversion            # includes -Wsign-conversion, -Wshorten-64-to-32, etc.
-Wshadow                # or the stricter -Wshadow-all
-Wnon-virtual-dtor
-Wold-style-cast
-Wimplicit-fallthrough
-Wthread-safety         # only fires on code with annotations
```

The `-Wdangling` family and `-Wnull-dereference` are already on by default in Clang and needn't be written. Below, each is described with the errors it catches and the rule behind it. In CMake, set them as PRIVATE options of the target; see [[toolchain/cmake]].

### `-Wconversion`: implicit conversions that silently change values

```cpp title="conv.cpp"
#include <cstdint>
#include <vector>

int sum(const std::vector<int>& v) {
  int n = v.size();                 // size_t -> int
  int s = 0;
  for (int i = 0; i < n; ++i)
    s += v[i];                      // int -> size_t
  return s;
}

std::uint8_t clamp_byte(int x) {
  return x;                         // int -> uint8_t
}

float half(double d) { return d / 2; }  // double -> float
```

Conversions between integers are always defined: the result is the value of the destination type congruent to the source value modulo 2^N ([[conv.integral#3]]). So `clamp_byte(300)` returns 44, with no UB and no indication. Floating-point conversions are different: if a `double` value is out of `float`'s range, the behavior is undefined ([[conv.double#2]]).

These conversions are all well-formed. Only in list-initialization is a narrowing conversion ([[g:narrowing-conversion]], defined in [[dcl.init.list#7]]) ill-formed. `-Wconversion` reports narrowing in other contexts too:

```text
conv.cpp:8:12: warning: implicit conversion changes signedness: 'int' to 'size_type' (aka 'unsigned long') [-Wsign-conversion]
conv.cpp:5:13: warning: implicit conversion loses integer precision: 'size_type' (aka 'unsigned long') to 'int' [-Wshorten-64-to-32]
conv.cpp:13:10: warning: implicit conversion loses integer precision: 'int' to 'std::uint8_t' (aka 'unsigned char') [-Wimplicit-int-conversion]
conv.cpp:16:33: warning: implicit conversion loses floating-point precision: 'double' to 'float' [-Wimplicit-float-conversion]
```

In Clang, `-Wconversion` already includes `-Wsign-conversion`. `-Wsign-conversion` fires a lot in code that indexes with `size_t`; the usual fix is to change the variable's type (use `std::size_t`, `std::ssize`) or write a `static_cast`, so that the conversion shows in the code. The rules of integer arithmetic are covered in [[topics/arithmetic]].

### `-Wshadow`: inner names hiding outer ones

`deposit` in `misc.cpp` declares a local variable with the same name as a member, after which every `balance` in the function body finds the local variable ([[basic.lookup]]). `-Wshadow` reports local variables that shadow members, outer local variables and global variables. `-Wshadow-all` also reports constructor parameters with the same name as members, which fires on the idiomatic `: balance(balance)` too; whether to enable it depends on the project's style.

### `-Wnon-virtual-dtor`: reported at the declaration

`-Wall` already includes `-Wdelete-non-virtual-dtor`, but that reports at the `delete` expression. With `std::unique_ptr<Shape>`, the `delete` is inside libc++'s `default_delete`, and on our test machine the warning pointed at `unique_ptr.h:74` followed by a long instantiation path. `-Wnon-virtual-dtor` reports at the class definition: a class with virtual functions but a non-virtual destructor gets a warning. The rule behind it is [[expr.delete#3]]: if the static type differs from the dynamic type, the static type must have a virtual destructor, otherwise it is UB.

### `-Wold-style-cast`: what `(T)x` actually does

A C-style cast tries, in order, `const_cast`, `static_cast`, `static_cast` followed by `const_cast`, `reinterpret_cast`, and `reinterpret_cast` followed by `const_cast`, taking the first that works ([[expr.cast#4]]). So `(char*)s.data()` silently casts away `const`, while `static_cast<char*>(s.data())` doesn't compile and forces you to write `const_cast` explicitly. The value of this warning is that it lets readers see what kind of conversion it is; see [[topics/casts]].

### `-Wimplicit-fallthrough`

The `case` labels of a `switch` don't change control flow by themselves, so execution falls from one branch into the next ([[stmt.switch#6]]). With the warning on, intentional fall-through must be written `[[fallthrough]];`, exactly the protocol the standard recommends ([[dcl.attr.fallthrough#2]]). Clang's hint gives both fixes: add `[[fallthrough]];` or add `break;`.

### `-Wnull-dereference`: a narrow scope in Clang

Clang's `-Wnull-dereference` is on by default, but it only looks at literal null pointers:

```cpp title="nd.cpp"
struct Node { int value; Node* next; };
int f() { return *(int*)nullptr; }              // warning
int g() { Node* n = nullptr; return n->value; } // no warning
int h() { int* p = 0; return *p; }              // no warning
```

```text
nd.cpp:2:18: warning: indirection of non-volatile null pointer will be deleted, not trap [-Wnull-dereference]
```

Once the null pointer goes through a variable, the compiler's warning can't see it. The static analyzer below reports `core.NullDereference` for all three functions. According to GCC's documentation, GCC's option of the same name relies on data-flow analysis during optimization and has a different scope; not verified on our test machine.

### `-Wdangling` and `[[clang::lifetimebound]]`

The compiler analyzes within one function. If a function returns a reference that may refer to its argument, the caller's side can't tell. `[[clang::lifetimebound]]` writes this convention on the parameter:

```cpp title="lb.cpp" run ub
#include <map>
#include <string>
#include <string_view>

using Config = std::map<std::string, std::string>;

const std::string& get_or(const Config& c, const std::string& key,
                          const std::string& fallback) {
  auto it = c.find(key);
  return it != c.end() ? it->second : fallback;
}

const std::string& get_or_lb(const Config& c [[clang::lifetimebound]],
                             const std::string& key,
                             const std::string& fallback [[clang::lifetimebound]]) {
  auto it = c.find(key);
  return it != c.end() ? it->second : fallback;
}

std::size_t demo(const Config& c) {
  const std::string& a = get_or(c, "port", "8080");     // dangles, no warning
  const std::string& b = get_or_lb(c, "port", "8080");  // dangles, warning
  return a.size() + b.size();
}

int main() { Config c; return demo(c) == 8 ? 0 : 1; }
```

The temporary `std::string` constructed from `"8080"` is destroyed at the end of the full-expression, so both `a` and `b` dangle. Only the annotated version gets a warning:

```text
lb.cpp:22:47: warning: temporary bound to local reference 'b' will be destroyed at the end of the full-expression [-Wdangling]
```

ASan reports `stack-use-after-scope` at run time for `a.size()`. libc++ puts this annotation on the parameters of functions such as `std::min`, `std::max` and `std::move`, so `const int& m = std::max(1, 2);` also gets a warning. Which dangling cases warnings can catch is covered in [[topics/dangling-references]].

Clang has no option named `-Wlifetimebound`; the annotation feeds the `-Wdangling` family. Clang 23 also has a set of lifetime analyses, `-Wlifetime-safety`, off by default, in which `-Wlifetime-safety-suggestions` suggests where to add annotations. The result of adding `-Wlifetime-safety-all` to the example above:

```text
lb.cpp:7:42: warning: parameter in intra-TU function should be marked [[clang::lifetimebound]] [-Wlifetime-safety-intra-tu-suggestions]
lb.cpp:10:10: note: param returned here
lb.cpp:8:54: warning: parameter in intra-TU function should be marked [[clang::lifetimebound]] [-Wlifetime-safety-intra-tu-suggestions]
lb.cpp:10:10: note: param returned here
lb.cpp:22:47: warning: temporary object does not live long enough [-Wlifetime-safety-use-after-scope]
```

### `-Wthread-safety`: locking conventions as annotations

Data races are UB ([[intro.races#17]]). Which mutex protects which member is normally written only in comments. Clang's thread safety analysis makes it a checkable annotation:

```cpp title="ts.cpp"
#include <mutex>

#define GUARDED_BY(m) __attribute__((guarded_by(m)))
#define REQUIRES(m)   __attribute__((requires_capability(m)))

class Counter {
  std::mutex mu_;
  long hits_ GUARDED_BY(mu_) = 0;
  void bump() REQUIRES(mu_) { ++hits_; }
public:
  void hit() {
    std::lock_guard g(mu_);
    bump();
  }
  long peek() { return hits_; }   // no lock
  void hit_capped() {
    mu_.lock();
    if (hits_ >= 100) return;     // early return, lock not released
    bump();
    mu_.unlock();
  }
  void reset() { bump(); }        // caller doesn't hold the lock
};
```

```text
$ clang++ -std=c++2c -Wall -Wextra -pedantic -Wthread-safety -fsyntax-only ts.cpp
ts.cpp:15:24: warning: reading variable 'hits_' requires holding mutex 'mu_' [-Wthread-safety-analysis]
ts.cpp:21:3: warning: mutex 'mu_' is not held on every path through here [-Wthread-safety-analysis]
ts.cpp:17:9: note: mutex acquired here
ts.cpp:22:18: warning: calling function 'bump' requires holding mutex 'mu_' exclusively [-Wthread-safety-analysis]
```

The libc++ on our test machine already puts capability annotations on `std::mutex` and `std::lock_guard`, so you only need to annotate the protected data and the functions' preconditions. The analysis is static and per function: it checks that the right lock is held on every path, not the actual interleaving of threads, and it doesn't understand atomic operations. For run-time race detection, use TSan; see [[topics/memory-model]].

## `-Werror` and third-party code

`-Werror` turns warnings into errors. Turn it on in CI, and off in developers' local builds and in build scripts shipped to users: new compiler versions add warnings, and a hard-coded `-Werror` makes downstream users unable to build with a new compiler. CMake 3.24's `CMAKE_COMPILE_WARNING_AS_ERROR` is designed for this (see [[toolchain/cmake]]).

Third-party headers shouldn't break your build. Directories brought in with `-isystem` are treated as system headers, and warnings arising in them aren't shown. The header below has an old-style cast and a deprecated function:

```cpp title="third_party/legacy/legacy.h"
#pragma once
inline int legacy_scale(double x) { return (int)(x * 100); }
[[deprecated("use parse_v2")]] inline int parse_v1(const char*) { return 0; }
```

```cpp title="app.cpp"
#include <legacy/legacy.h>
int run(double x) { return legacy_scale(x) + parse_v1("1"); }
```

```text
$ W="-Wall -Wextra -pedantic -Wconversion -Wold-style-cast -Werror"
$ clang++ -std=c++2c $W -Ithird_party -fsyntax-only app.cpp
third_party/legacy/legacy.h:2:44: error: use of old-style cast [-Werror,-Wold-style-cast]
app.cpp:2:46: error: 'parse_v1' is deprecated: use parse_v2 [-Werror,-Wdeprecated-declarations]
$ clang++ -std=c++2c $W -isystem third_party -fsyntax-only app.cpp
app.cpp:2:46: error: 'parse_v1' is deprecated: use parse_v2 [-Werror,-Wdeprecated-declarations]
$ clang++ -std=c++2c $W -Wno-error=deprecated-declarations -isystem third_party -fsyntax-only app.cpp
app.cpp:2:46: warning: 'parse_v1' is deprecated: use parse_v2 [-Wdeprecated-declarations]
```

The first comes from inside the header, and `-isystem` removes it. The second is your own code calling a deprecated function; that is your problem, and it isn't removed. `-Wno-error=<name>` keeps that kind of warning as a warning, which suits a migration period. In CMake, imported targets (from `find_package`) are brought in with `-isystem` by default, and your own subdirectories can use `target_include_directories(... SYSTEM ...)`.

Templates are an exception: when a template in a system header is instantiated in your code, some warnings are still shown; `-Wdelete-non-virtual-dtor` pointing into `unique_ptr.h` is one example.

When you can't change how a header is included, you can turn warnings off locally at the inclusion:

```cpp
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wold-style-cast"
#include <legacy/legacy.h>
#pragma clang diagnostic pop
```

!!! pitfall "Unknown warning options"
    When the compiler is passed a `-W...` option it doesn't recognize, Clang warns `-Wunknown-warning-option`. With `-Werror` on, that becomes an error too, so build scripts written with warning names from a new compiler fail outright on an older one. Projects spanning compiler versions can test with CMake's `check_cxx_compiler_flag` before adding an option.

## clang-tidy

clang-tidy parses source files with Clang's frontend and then runs a set of checks on the AST. It finds problems compiler warnings don't cover: idioms, performance, code that can be modernized, known bug patterns. Homebrew's LLVM includes it:

```text
$ clang-tidy --version
Homebrew LLVM version 23.1.3
$ clang-tidy --list-checks --checks='*' | wc -l       # about 600 checks
```

Checks are grouped by prefix. Counts on our test machine: `bugprone-*` 109, `performance-*` 22, `modernize-*` 49, `cppcoreguidelines-*` 43, `readability-*` 62, `clang-analyzer-*` 131 (the static analyzer, below).

### Running it on a small file

```cpp title="inventory.cpp"
#include <algorithm>
#include <map>
#include <string>
#include <utility>
#include <vector>

struct Item {
  std::string name;
  int count;
};

class Inventory {
public:
  virtual ~Inventory() = default;
  virtual void add(std::string name, int n) {
    items_.push_back(Item{name, n});
  }
  std::vector<std::string> names() const {
    std::vector<std::string> out;
    for (int i = 0; i < items_.size(); ++i)
      out.push_back(items_[i].name);
    return out;
  }
  double average() const {
    int total = 0;
    for (auto it : items_) total += it.count;
    return total / items_.size();
  }
  void prune() {
    std::remove_if(items_.begin(), items_.end(),
                   [](const Item& it) { return it.count == 0; });
  }
private:
  std::vector<Item> items_;
};

class Logged : public Inventory {
public:
  void add(std::string name, int n) {
    log_.push_back(std::move(name));
    Inventory::add(name, n);
  }
private:
  std::vector<std::string> log_;
};
```

The compiler with `-Wall -Wextra` gives just two warnings: the signed/unsigned comparison on line 20, and the discarded return value of `remove_if` on line 30 (libc++ marks it `[[nodiscard]]`). clang-tidy with four groups of checks enabled:

```text
$ clang-tidy --checks='-*,bugprone-*,performance-*,modernize-*,cppcoreguidelines-*' \
    inventory.cpp -- -std=c++20
inventory.cpp:12:7: warning: class 'Inventory' defines a default destructor but does not define a copy constructor, a copy assignment operator, a move constructor or a move assignment operator [cppcoreguidelines-special-member-functions]
inventory.cpp:16:26: warning: use designated initializer list to initialize 'Item' [modernize-use-designated-initializers]
inventory.cpp:16:27: warning: parameter 'name' of type 'std::string' (aka 'basic_string<char>') is passed by value and only copied once; consider moving it to avoid unnecessary copies [performance-unnecessary-value-param]
inventory.cpp:18:3: warning: function 'names' should be marked [[nodiscard]] [modernize-use-nodiscard]
inventory.cpp:18:28: warning: use a trailing return type for this function [modernize-use-trailing-return-type]
inventory.cpp:20:5: warning: use range-based for loop instead [modernize-loop-convert]
inventory.cpp:21:7: warning: 'push_back' is called inside a loop; consider pre-allocating the container capacity before the loop [performance-inefficient-vector-operation]
inventory.cpp:21:27: warning: possibly unsafe 'operator[]', consider bounds-safe alternatives [cppcoreguidelines-pro-bounds-avoid-unchecked-container-access]
inventory.cpp:24:3: warning: function 'average' should be marked [[nodiscard]] [modernize-use-nodiscard]
inventory.cpp:24:10: warning: use a trailing return type for this function [modernize-use-trailing-return-type]
inventory.cpp:26:15: warning: loop variable is copied but only used as const reference; consider making it a const reference [performance-for-range-copy]
inventory.cpp:27:12: warning: narrowing conversion from 'size_type' (aka 'unsigned long') to 'double' [bugprone-narrowing-conversions,cppcoreguidelines-narrowing-conversions]
inventory.cpp:27:12: warning: result of integer division used in a floating point context; possible loss of precision [bugprone-integer-division]
inventory.cpp:30:5: warning: the value returned by this function should not be disregarded; neglecting it may lead to errors [bugprone-unused-return-value]
inventory.cpp:30:5: warning: use a ranges version of this algorithm [modernize-use-ranges]
inventory.cpp:31:20: warning: use a trailing return type for this lambda [modernize-use-trailing-return-type]
inventory.cpp:39:8: warning: annotate this function with 'override' or (rarely) 'final' [cppcoreguidelines-explicit-virtual-functions,modernize-use-override]
inventory.cpp:41:20: warning: 'name' used after it was moved [bugprone-use-after-move]
Suppressed 2471 warnings (2470 in non-user code, 1 with check filters).
```

These 18 vary greatly in value:

- Real defects: `bugprone-use-after-move` (line 41 passes the already moved-from `name` to the base class, which usually receives an empty string); `bugprone-integer-division` (`average` does integer division and then converts to `double`, losing the fractional part); `bugprone-unused-return-value` (`remove_if` doesn't remove elements, it only returns the new end; you must call `erase` afterwards, or use `std::erase_if` instead).
- Performance problems: copying after passing by value, `push_back` one at a time in a loop, a range `for` copying elements.
- Modernization: `override`, range `for`, `ranges` algorithms. Of these, `override` is worth enforcing, since it turns signature mismatches into compile errors.
- Style preferences: trailing return types, `[[nodiscard]]` everywhere, designated initializers, banning `operator[]`. Whether to adopt these depends on the project; turning them off is recommended.

`Suppressed 2471 warnings` shows clang-tidy also checked the standard library headers, but by default it only shows results in user code.

clang-tidy's judgment on using a moved-from object is conservative: a standard library type is left in a valid but unspecified state after being moved from, and reading it isn't UB, but it is almost always a logic error.

### The `.clang-tidy` configuration file

Put the selection in a `.clang-tidy` at the project root; clang-tidy searches for it upward from the source file's directory:

```yaml title=".clang-tidy"
Checks: >
  -*,
  bugprone-*,
  performance-*,
  modernize-*,
  cppcoreguidelines-*,
  -modernize-use-trailing-return-type,
  -modernize-use-nodiscard,
  -modernize-use-designated-initializers,
  -cppcoreguidelines-pro-bounds-avoid-unchecked-container-access,
  -cppcoreguidelines-avoid-magic-numbers
WarningsAsErrors: 'bugprone-use-after-move,bugprone-unused-return-value'
HeaderFilterRegex: '^.*/(src|include)/.*'
CheckOptions:
  cppcoreguidelines-special-member-functions.AllowSoleDefaultDtor: true
```

`Checks` first disables everything with `-*`, then enables groups and excludes individual checks. `WarningsAsErrors` promotes to errors only the checks that are certainly defects, in which case clang-tidy's exit code is 1, which can fail CI. `HeaderFilterRegex` decides which headers' results are shown. `CheckOptions` tunes individual checks; here it allows declaring only a `= default` virtual destructor without the other special members. Run with this configuration, 10 warnings remain, two of which have become errors:

```text
inventory.cpp:30:5: error: the value returned by this function should not be disregarded; neglecting it may lead to errors [bugprone-unused-return-value,-warnings-as-errors]
inventory.cpp:41:20: error: 'name' used after it was moved [bugprone-use-after-move,-warnings-as-errors]
```

### The compilation database `compile_commands.json`

Above, the compile options were written by hand after `--`. In a real project each file has different include paths, macros and standard version, and clang-tidy needs to know them to parse like the compiler does. With `CMAKE_EXPORT_COMPILE_COMMANDS ON`, CMake writes a compilation database in the build directory:

```text
$ cmake -S . -B build -G Ninja -DCMAKE_CXX_COMPILER=clang++
$ cat build/compile_commands.json
[
{
  "directory": "<proj>/build",
  "command": "clang++ -std=gnu++20 -isysroot <sdk> -Wall -Wextra -Wpedantic -o CMakeFiles/inv.dir/src/inventory.cpp.o -c <proj>/src/inventory.cpp",
  "file": "<proj>/src/inventory.cpp",
  "output": "CMakeFiles/inv.dir/src/inventory.cpp.o"
}
]
$ clang-tidy -p build src/inventory.cpp
...
Suppressed 2453 warnings (2451 in non-user code, 2 with check filters).
```

`-p` points at the directory containing `compile_commands.json`. Compiler warnings produced by options such as `-Wall` in the compilation database appear in clang-tidy as `clang-diagnostic-*` checks; the configuration above doesn't enable them, so they are filtered (`2 with check filters`). To run over a whole project in parallel, use `run-clang-tidy -p build`. CMake can also run clang-tidy alongside every compile; see [[toolchain/cmake]].

`--fix` makes clang-tidy apply the changes the checks offer directly. The diff after running with only `modernize-use-override`, `performance-for-range-copy` and `modernize-loop-convert` enabled:

```diff
-    for (int i = 0; i < items_.size(); ++i)
-      out.push_back(items_[i].name);
+    for (const auto & item : items_)
+      out.push_back(item.name);
...
-    for (auto it : items_) total += it.count;
+    for (const auto& it : items_) total += it.count;
...
-  void add(std::string name, int n) {
+  void add(std::string name, int n) override {
```

Automatic fixes should be applied in batches, one check at a time, and reviewed one by one. The resulting formatting doesn't necessarily match the project's style (note the spaces in `const auto & item`); you can run clang-format again afterwards.

## The Clang static analyzer

Compiler warnings and most clang-tidy checks match patterns on the syntax tree. The **Clang Static Analyzer** is different: it performs symbolic execution on each function, proceeding along every possible path, tracking the possible values of each variable, and reporting when a null pointer dereference, memory leak or use of freed memory occurs on some feasible path. So its reports come with a path.

```cpp title="cache.cpp"
#include <cstdio>

struct Entry { int key; char* value; };

int key_of(const Entry* e, bool verbose) {
  if (verbose && !e)
    std::puts("no entry");
  return e->key;
}

char* load(const char* path) {
  char* buf = new char[256];
  std::FILE* f = std::fopen(path, "r");
  if (!f) return nullptr;
  std::size_t got = std::fread(buf, 1, 255, f);
  std::fclose(f);
  buf[got] = '\0';
  return buf;
}
```

The compiler with `-Wall -Wextra -pedantic -Wconversion` gives no warnings. `clang++ --analyze` runs the analyzer, and `--analyzer-output text` prints the path in the terminal:

```text
$ clang++ -std=c++2c --analyze --analyzer-output text cache.cpp
cache.cpp:8:10: warning: Access to field 'key' results in a dereference of a null pointer (loaded from variable 'e') [core.NullDereference]
cache.cpp:6:7: note: Assuming 'verbose' is true
cache.cpp:6:7: note: Left side of '&&' is true
cache.cpp:6:18: note: Assuming 'e' is null
cache.cpp:6:3: note: Taking true branch
cache.cpp:8:10: note: Access to field 'key' results in a dereference of a null pointer (loaded from variable 'e')
cache.cpp:14:18: warning: Potential leak of memory pointed to by 'buf' [cplusplus.NewDeleteLeaks]
cache.cpp:12:15: note: Memory is allocated
cache.cpp:14:8: note: 'f' is null
cache.cpp:14:3: note: Taking true branch
cache.cpp:14:18: note: Potential leak of memory pointed to by 'buf'
```

The reasoning behind the first report: the code checks `!e`, which means the author thinks `e` may be null; continuing along that branch dereferences a null pointer. If `e` is never null, the check is redundant. The second report finds that `buf` isn't freed on the path where `fopen` fails; the fix is to use `std::unique_ptr<char[]>` or `std::vector<char>`, see [[topics/ownership-and-smart-pointers]].

To run over a whole build, wrap the build command in `scan-build`. It replaces the compiler with a wrapper that also runs the analyzer, and produces an HTML report at the end:

```text
$ scan-build -o report clang++ -std=c++2c -c cache.cpp -o cache.o
scan-build: Using '/opt/homebrew/Cellar/llvm/23.1.3_2/bin/clang-23' for static analysis
cache.cpp:8:10: warning: Access to field 'key' results in a dereference of a null pointer (loaded from variable 'e') [core.NullDereference]
cache.cpp:14:18: warning: Potential leak of memory pointed to by 'buf' [cplusplus.NewDeleteLeaks]
2 warnings generated.
scan-build: Analysis run complete.
scan-build: 2 bugs found.
scan-build: Run 'scan-view report/2026-10-19-190212-55347-1' to examine bug reports.
```

scan-build works by replacing `CC` and `CXX`, but CMake records the compiler path at configure time, so a CMake project needs a build directory configured under scan-build: `scan-build cmake -S . -B build-scan -G Ninja`, then `scan-build -o report cmake --build build-scan`. Adding `cache.cpp` to the CMake project from the previous section and running it this way also gave `2 bugs found`. clang-tidy's `clang-analyzer-*` checks run the same analyzer.

!!! impl "Reports the analyzer gives up to reduce false positives"
    The analyzer inlines called functions. If a null pointer comes from some `return nullptr` in an inlined function, it isn't reported by default: such paths often don't occur in practice, and reporting them would mostly produce false positives. For example, in `Entry* e = find(table, n, key); return e->key;`, where `find` returns a null pointer when nothing is found, nothing is reported by default on our test machine; only with `-Xclang -analyzer-config -Xclang suppress-null-return-paths=false` is it reported. The analyzer also has a cap on the number of exploration steps per function and stops early when there are too many paths. So no report doesn't mean no defect.

## clang-format

clang-format only deals with formatting and doesn't change semantics. Its value is that formatting no longer comes up in code review:

```text
$ cat .clang-format
BasedOnStyle: LLVM
IndentWidth: 2
ColumnLimit: 80
$ cat fmt.cpp
int  f(int a,int b){if(a>b) return a; else return b;}
$ clang-format fmt.cpp
int f(int a, int b) {
  if (a > b)
    return a;
  else
    return b;
}
$ clang-format --dry-run -Werror fmt.cpp; echo $?
fmt.cpp:1:4: error: code should be clang-formatted [-Wclang-format-violations]
...
1
```

`-i` modifies in place, and `--dry-run -Werror` only checks, which suits CI. `git clang-format` formats only the changed lines in the staging area, which suits gradually adopting it in an existing codebase.

## What static analysis can't do

Static analysis reasons without running the program, and its limitations have two sources.

First, it looks at only one translation unit at a time. Two `.cpp` files each defining a `struct Config` with different members are each correct on their own, and neither the compiler, clang-tidy nor the analyzer will report anything; this is IFNDR ([[basic.def.odr#16]]), and the linker usually accepts it silently too, see [[toolchain/linking-and-symbols]] and [[toolchain/dependencies]].

Second, it doesn't know run-time data. Whether an index is out of bounds, whether a multiplication overflows, whether two threads really access something at the same time all depend on the input. The analyzer can only report when the code itself hints at a possibility (such as having checked `!e`); otherwise it stays silent to avoid false positives.

These problems need run-time tools: ASan detects out-of-bounds accesses and use of freed memory, UBSan detects core-language UB such as signed overflow and invalid shifts, and TSan detects data races (overview in [[topics/undefined-behavior]]). Sanitizers can only find problems on paths that actually execute, so they must be paired with tests, see [[toolchain/testing]]; how to locate a problem once it appears is covered in [[toolchain/debugging]].

| Tool | When it runs | Typical findings | Sources of misses |
|---|---|---|---|
| Compiler warnings | Every compile | Implicit conversions, shadowing, fall-through, dangling temporaries | Only within a function, only known patterns |
| Annotations + warnings | Every compile | Violated locking conventions, dangling through annotated parameters | Code without annotations |
| clang-tidy | CI, editor | Use of moved-from objects, integer division, performance problems | Pattern matching |
| Static analyzer | CI (slower) | Null pointers, leaks, double frees along paths | Deliberately gives up to suppress false positives, limited exploration |
| Sanitizers | When tests run | Out-of-bounds accesses, UB, data races | Only covers paths that execute |

## Questions

!!! question "1"
    Clang accepts `char data[0];` by default without any diagnostic. Does this violate the standard? What about with `-Wall -Wextra`?

<details markdown="1">
<summary>Answer</summary>

It does. An array's size must be greater than zero ([[dcl.array#1]]); this is a diagnosable rule, and [[intro.compliance.general#2]] requires at least one diagnostic; an implementation may accept it as an extension, but ¶11 still requires a diagnostic. Clang on our test machine diagnoses nothing by default or with `-Wall -Wextra`; only `-pedantic` gives a `-Wzero-length-array` warning. A warning satisfies the requirement to diagnose, and continuing to compile doesn't violate the standard.
</details>

!!! question "2"
    `std::uint8_t b = 300;` compiles, but `std::uint8_t b{300};` doesn't. Why? What does `-Wconversion` say about the former?

<details markdown="1">
<summary>Answer</summary>

Both convert an `int` to `unsigned char`. The conversion itself is defined, with the result 44 after reduction modulo 256 ([[conv.integral#3]]). But in list-initialization, converting a constant whose value can't be represented in the target type is a narrowing conversion and ill-formed ([[dcl.init.list#3]], [[dcl.init.list#7]]), which the compiler must diagnose. Copy-initialization has no such restriction. For the former, Clang warns about the constant overflow by default (`-Wconstant-conversion`), and `-Wconversion` also gives `-Wimplicit-int-conversion` for the same kind of conversion of non-constants.
</details>

!!! question "3"
    After adding `std::lock_guard g(mu_);` to `peek` in `ts.cpp`, `-Wthread-safety` no longer reports anything. Does that show `Counter` has no data races?

<details markdown="1">
<summary>Answer</summary>

No. The analysis only checks that members annotated `GUARDED_BY` are accessed while holding the corresponding lock. Members without annotations, data that escapes the class through pointers or references, and logic errors caused by stale values read outside the lock are all outside its scope. A data race is a run-time property ([[intro.races#17]]), and needs TSan to detect it under real thread interleavings.
</details>

## Summary

| Question | Recommendation |
|---|---|
| Basic warnings | `-Wall -Wextra -Wpedantic`, plus `-Wconversion -Wshadow -Wnon-virtual-dtor -Wold-style-cast -Wimplicit-fallthrough` |
| `-Weverything` | For browsing which warnings exist, not for building |
| `-Werror` | On in CI; `-isystem` for third-party headers; `-Wno-error=…` during migrations |
| Conventions the compiler can't see | `[[clang::lifetimebound]]`, thread-safety annotations, `[[nodiscard]]` |
| clang-tidy | Enable `bugprone` and `performance` in `.clang-tidy`, pick from `modernize` and `cppcoreguidelines`; point `-p` at the compilation database |
| Path-dependent defects | `clang++ --analyze`, `scan-build`, `clang-analyzer-*` |
| Formatting | `.clang-format` + `--dry-run -Werror` in CI |
| Beyond static analysis | Cross-TU ODR, input-dependent UB: sanitizers plus tests |
