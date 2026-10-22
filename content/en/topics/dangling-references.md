---
title: A catalogue of dangling references
summary: The many ways a reference, pointer or view can go on being used after the object it refers to has died, the standard's basis for each, whether compilers can diagnose it, and what AddressSanitizer reports.
tags: dangling references, lifetime, temporaries, ASan, topic
updated: 2026-10-19
---

!!! tldr
    - A reference, pointer or view that is still used after the lifetime of the object it refers to has ended is dangling. Accessing the object through it is UB.
    - A temporary has its lifetime extended only when a reference binds directly to it. Any function call in between (`std::move`, `std::max`, a getter) breaks the extension.
    - `string_view`, `span` and `initializer_list` are not references and never extend the lifetime of anything.
    - Lambdas, coroutines and callbacks defer execution, and dangle most easily when they capture by reference or take parameters by reference.
    - C++23 turned some cases of "returning a reference to a local variable" into compile errors and fixed range-based for; C++26 forbids `return` from binding a reference to a temporary. The remaining cases rely on the `-Wdangling` family of warnings, `[[clang::lifetimebound]]` and ASan.

## What dangling means

```cpp run title="view.cpp" ub
#include <cstdio>
#include <string>
#include <string_view>
std::string make_name() { return "a name long enough to defeat SSO"; }
int main() {
  std::string_view sv = make_name();   // the temporary string is destroyed at the end of this line
  std::printf("%c\n", sv[0]);          // UB: reads freed heap memory
}
```

The `std::string` returned by `make_name()` is a [[g:temporary-object|temporary object]], destroyed at the end of the [[g:full-expression|full-expression]] it appears in, that is, at the semicolon on this line. `sv` holds a pointer to its buffer, and reading it on the next line reads memory that has already been freed.

A reference, pointer or view that is still used after the lifetime of the object it refers to has ended is called **dangling**. Two rules in the standard govern it:

- When an object's lifetime has ended but its storage remains, accessing the object or calling a non-static member function through a glvalue referring to it is UB ([[basic.life#8]]);
- When the storage has also been released, pointers to it are no longer valid in later evaluations, and indirection through them is UB ([[basic.compound#6]]).

The rules themselves are simple; the hard part is seeing that the object is already dead. C++ references don't own objects, and the compiler doesn't track who borrowed what. When an object dies is determined by its storage duration ([[basic.stc]]) and the rules for temporaries ([[class.temporary]]), and the latter have quite a few exceptions.

The table below classifies the cases by how the object died; the following sections go through them one by one:

| # | Route | How the object died | Standard's verdict | Clang default warning | ASan report |
|---|---|---|---|---|---|
| 1 | Returning a reference to a local variable | The function returns and automatic variables are destroyed | Partly ill-formed since C++23, otherwise UB | `-Wreturn-stack-address` | stack-use-after-return\* |
| 2 | Returning a reference bound to a temporary | End of the full-expression | Ill-formed since C++26 | Error | — |
| 3 | A temporary passed through a function call, then bound to a reference | End of the full-expression | UB | Partly (`-Wdangling`) | stack-use-after-scope |
| 4 | Reference members of aggregates | Parenthesized or `new` initialization doesn't extend lifetime | UB | `-Wdangling`, `-Wdangling-field` | stack-use-after-scope |
| 5 | `string_view` or `span` pointing to a temporary | Views aren't references; no lifetime extension | UB | `-Wdangling-gsl` | heap-use-after-free |
| 6 | Temporaries in a range-based for initializer | C++20: destroyed at the end of the initializer | UB in C++20, fixed in C++23 | None | stack-use-after-scope |
| 7 | A lambda capturing by reference escapes | The enclosing function returns | UB | Usually none | stack-use-after-return\* |
| 8 | Reference parameters of coroutines | The caller's full-expression ends | UB | None | stack-use-after-scope |
| 9 | Returning or storing an `initializer_list` | The underlying array is a temporary | UB | `-Wreturn-stack-address` | stack-use-after-return\* |
| 10 | Iterator and reference invalidation | The container reallocates | UB (violates a library precondition) | None | heap-use-after-free |

\* ASan on macOS arm64 with Clang 23 does not detect stack-use-after-return by default; run with `ASAN_OPTIONS=detect_stack_use_after_return=1`.

## 1. Returning a reference to a local variable

```cpp
int& r1()        { int x = 0; return x; }
const int& r1c() { int x = 0; return x; }
int& r1p()       { int x = 0; return (x); }
int& r1r()       { int x = 0; int& y = x; return y; }
```

In C++20 all four functions are well-formed; only using the return value after the call is UB, and Clang gives a `-Wreturn-stack-address` warning for each one.

C++23's [[P2266R3]] changed the value category of local variable names in `return` statements: the `x` in `return x;` and `return (x);` is a [[g:move-eligible|move-eligible]] id-expression and is an xvalue ([[expr.prim.id.unqual]]). A non-const lvalue reference can't bind to an xvalue, so:

| | C++20 | Since C++23 | Reason |
|---|---|---|---|
| `r1`: `int&` returning `x` | Warning | Error | A non-const lvalue reference can't bind to an xvalue |
| `r1p`: `return (x);` | Warning | Error | Parenthesized, it is still move-eligible |
| `r1c`: `const int&` returning `x` | Warning | Warning | A const lvalue reference can bind to an xvalue, and still dangles |
| `r1r`: returning through the reference `y` | Warning | Warning | `y` is a reference variable and isn't move-eligible |

Clang 23's error message for `r1` says "cannot bind to a temporary of type 'int'", but `x` is actually an xvalue, not a temporary. This change is a side effect of P2266 and wasn't designed for dangling, which is why `r1c` and `r1r` are still only warnings.

Code the compiler can't see through doesn't even get a warning:

```cpp run title="escape.cpp" ub
#include <cstdio>
int* make() {
  int local = 42;
  int* p = &local;
  return p;                  // no warning
}
int main() {
  int* p = make();
  std::printf("%d\n", *p);   // UB: local has been destroyed
}
```

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=address escape.cpp && ./a.out
42
$ ASAN_OPTIONS=detect_stack_use_after_return=1 ./a.out
==ERROR: AddressSanitizer: stack-use-after-return on address 0x000105fa0020 ...
READ of size 4 at 0x000105fa0020 thread T0
    #0 ... in main escape.cpp:9
Address 0x000105fa0020 is located in stack of thread T0 at offset 32 in frame
    #0 ... in make() escape.cpp:2
  This frame has 1 object(s):
    [32, 36) 'local' (line 3) <== Memory access at offset 32 is inside this variable
```

The first run printed `42`, because the old value on the stack hadn't been overwritten yet. Dangling code usually seems to work, which is exactly what makes it dangerous.

## 2. Returning a reference bound to a temporary {{c++26}}

```cpp run title="return-temp.cpp" error
const int& f1() { return 42; }                        // reference bound to a temporary int
const double& f2() { static int x = 42; return x; }   // int to double creates a temporary
struct R { const int& r; };
R f3() { return {42}; }                               // the returned object's reference member binds to a temporary
```

In C++23 these are all well-formed, just guaranteed to dangle. C++26's [[P2748R5]] says that if a `return` statement binds the returned reference to a temporary expression, the program is ill-formed ([[stmt.return#6]]). The current draft also counts the **constituent references** of the returned object (references among the object itself and the reference members of its subobjects, [[intro.object#12]]) ([[stmt.return#6.2]]), which is the case for `f3`. Clang 23 reports "returning reference to local temporary object" for all three under `-std=c++2c`, and only warns under `-std=c++23`.

!!! lawyer "The rule only looks at syntactic temporary expressions"
    ```cpp
    auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
    auto&& f4() { return id(42); }   // well-formed, but guaranteed to dangle
    ```
    `id(42)` is a function call, not a temporary expression, so the rule doesn't reach it. The standard's own example comments it the same way: "OK, but probably a bug". Also, `return R{42};` literally also binds a temporary to a constituent reference of the returned object under [[stmt.return#6.2]], but Clang 23 only diagnoses the `return {42};` form.

## 3. The rules for lifetime extension and their exceptions

[[g:lifetime-extension|Lifetime extension]] is the only mechanism that lets a temporary outlive its full-expression: when a reference binds directly to a temporary (or a subobject of one), the temporary's lifetime is extended to match the reference's ([[class.temporary#6]]).

Whether the binding is direct is decided syntactically. Only glvalues obtained through the expressions listed in items 6.1–6.9 of [[class.temporary#6]] count: temporary materialization itself, parentheses, subscripting an array temporary, `.` access to a non-reference data member, `.*`, the four casts without user-defined conversions, a braced functional cast to a reference type, the conditional expression, and the comma expression.

Function calls are not on the list. As soon as a temporary goes through one function call and comes back out, the extension is broken:

```cpp
#include <algorithm>
#include <string>
#include <utility>
std::string make();
struct Person {
  std::string name;
  const std::string& get_name() const { return name; }
};
Person make_person();

const std::string& a = make();                    // extended: direct binding
const std::string& b = make_person().name;        // extended: member access; the whole Person lives as long as b
const std::string& c = make_person().get_name();  // dangling: goes through a member function call (no warning)
const std::string& d = std::move(make());         // dangling: std::move is a function call (-Wdangling)
const int& m = std::max(1, 2);                    // dangling: max returns a reference to a parameter (-Wdangling)
```

The last line is the hardest to spot, because the signature `const T& max(const T&, const T&)` looks fine:

```cpp run title="max.cpp" ub
#include <algorithm>
#include <cstdio>
int main(int argc, char**) {
  const int& m = std::max(argc, 2);   // 2 is a temporary bound to a parameter, destroyed at the end of this line
  std::printf("%d\n", m);             // UB
}
```

```text
max.cpp:4:33: warning: temporary bound to local reference 'm' will be destroyed at the end of the full-expression [-Wdangling]
==ERROR: AddressSanitizer: stack-use-after-scope ...
    #0 ... in main max.cpp:5
    [48, 52) 'ref.tmp' (line 4) <== Memory access at offset 48 is inside this variable
```

Clang can warn about `std::max` and `std::move` because libc++ annotates their parameters with `[[clang::lifetimebound]]` (see section 11). Your own `get_name()` without the annotation gets no diagnostic.

The same paragraph goes on to list three explicit exceptions that do not extend (items 6.10–6.12): binding to a reference parameter in a function call, binding to a reference member in parenthesized aggregate initialization, and binding to a reference in a *new-initializer*. Two other cases are simply ill-formed: a constructor's *mem-initializer* binding a reference member to a temporary ([[class.base.init#8]]), and the `return` from the previous section.

## 4. Reference members in aggregates

```cpp run title="agg-ref.cpp" ub
#include <cstdio>
#include <string>
struct Ref { const std::string& s; };
std::string temp() { return "a string long enough to be heap allocated"; }
int main() {
  Ref a{temp()};                 // OK: braced aggregate initialization, temporary extended to the end of a
  Ref b(temp());                 // C++20 parenthesized aggregate initialization: not extended ([class.temporary]/6.11)
  Ref* c = new Ref{temp()};      // new-initializer: not extended ([class.temporary]/6.12)
  std::printf("%zu\n", a.s.size());
  std::printf("%zu\n", b.s.size());   // UB
  std::printf("%zu\n", c->s.size());  // UB
  delete c;
}
```

Clang 23 gives `-Wdangling` for `b` and `-Wdangling-field` for `c`. ASan reports stack-use-after-scope on the read of `b.s`.

The difference between braces and parentheses is intentional. C++20's parenthesized aggregate initialization was designed on the model of "calling a constructor" ([[dcl.init#15]] Note 7), and a constructor's reference parameter doesn't extend the lifetime of its argument, so `Ref(temp())` doesn't extend either.

A type with reference members should usually only be constructed from lvalues. The way to write that constraint into the type is to delete the rvalue overload:

```cpp ok
#include <string>
struct NameRef {
  const std::string& s;
  explicit NameRef(const std::string& x) : s(x) {}
  explicit NameRef(std::string&&) = delete;   // reject temporaries
};
std::string temp();
std::string keep = "x";
NameRef ok{keep};
// NameRef bad{temp()};                       // error: call to deleted constructor
```

## 5. View types: `string_view`, `span`

`std::string_view` and `std::span` are not references but ordinary class types that hold pointers. Lifetime extension applies only to references, so views never extend the lifetime of anything. The opening `view.cpp` is this case, and Clang and ASan report:

```text
view.cpp:6:25: warning: object backing the pointer will be destroyed at the end of the full-expression [-Wdangling-gsl]
==ERROR: AddressSanitizer: heap-use-after-free ...
    #0 ... in main view.cpp:7
freed by thread T0 here:
    #1 ... in std::__1::basic_string<...>::~basic_string()
    #2 ... in main view.cpp:6
```

If the string is short enough to fit in the internal buffer of the [[g:short-string-optimization|short string optimization]] (SSO), the data lives inside the temporary `string` object itself, and ASan reports stack-use-after-scope instead.

Clang's `-Wdangling-gsl` family works through two kinds of type annotations, Owner and Pointer: libc++ marks `std::string` and `std::vector` as Owners, and `string_view`, `span` and iterators as Pointers. Clang 23 recognizes these patterns:

```cpp
#include <span>
#include <string>
#include <string_view>
#include <vector>
std::string make_name();
std::vector<int> make_vec();
std::string_view f() { std::string s = "abc"; return s; }   // -Wreturn-stack-address
void g() {
  std::string_view sv = make_name();          // -Wdangling-gsl
  std::span<const int> sp = make_vec();       // -Wdangling-gsl
  std::string_view v; v = std::string("t");   // -Wdangling-assignment-gsl
}
```

Add a single layer of your own function in between and it can no longer see it. When designing interfaces, `string_view` is safe as a parameter; when returning it or storing it as a member, first establish who owns the underlying string and how long it lives.

## 6. The range-based for initializer {{c++23}}

```cpp run title="range-for.cpp" std=c++20 ub
#include <cstdio>
#include <string>
#include <vector>
struct Doc {
  std::vector<std::string> lines{"first line, long enough to live on the heap"};
  const std::vector<std::string>& get() const { return lines; }
};
Doc load() { return {}; }
int main() {
  for (const std::string& s : load().get())   // C++20: the temporary Doc is destroyed before the loop starts
    std::printf("%zu\n", s.size());
}
```

Range-based for is rewritten as `auto&& __range = load().get();` followed by the loop ([[stmt.ranged#1]]). `__range` binds to the return value of `get()`, which again went through a function call, so by the rules of section 3 the temporary `Doc` is destroyed at the end of that declaration. With Clang 23 and ASan: `-std=c++20` reports stack-use-after-scope, and `-std=c++23` prints `43` normally.

C++23's [[P2718R0]] added [[class.temporary#7]]: all temporaries created in the range-based for initializer that would otherwise be destroyed at the end of that full-expression are extended to the lifetime of `__range`. The C++20 version gets no warning at all. Code still on C++20 can hold the object explicitly with an *init-statement*: `for (auto d = load(); const auto& s : d.get())`.

The fix only covers temporaries in the initializer. Function parameters are not temporaries, so `const T& f2(T t) { return t; }` with `for (auto e : f2(g()))` still dangles; see [[stmt.ranged]].

## 7. Lambdas capturing by reference

```cpp run title="lambda-ref.cpp" ub
#include <cstdio>
#include <functional>
std::function<int()> make_counter() {
  int count = 0;
  return [&] { return ++count; };   // captures a local by reference, and the closure leaves the scope
}
int main() {
  auto next = make_counter();
  std::printf("%d\n", next());      // UB: count no longer exists
}
```

For an entity captured by reference, the reference in the closure refers to the original entity. Calling the closure after the entity has died is, as the note in [[expr.prim.lambda.capture#17]] points out, likely to result in UB. Clang 23 gives no warning for the example above (the closure was put into a `std::function`); with stack-use-after-return detection enabled, ASan reports:

```text
==ERROR: AddressSanitizer: stack-use-after-return ...
    #0 ... in make_counter()::$_0::operator()() const lambda-ref.cpp:5
```

Problems of the same kind:

- `[=]` in a member function implicitly captures `this`, which in effect captures the whole object by reference. C++20 deprecated this implicit capture; write `[=, this]`, or copy the object with `[=, *this]`.
- Asynchronous callbacks: a callback handed to `std::thread`, a thread pool or an I/O library captures a local variable by reference, and runs only after the function has returned.

Whenever a closure might outlive the current scope, don't use `[&]`.

## 8. Reference parameters of coroutines

When a coroutine is called, its parameters are copied into the coroutine state, but the copy of a reference parameter is still a reference ([[dcl.fct.def.coroutine#13.1]]). Note 3 in the same paragraph warns that if a coroutine has a parameter passed by reference, resuming the coroutine after the referenced entity has died is likely to result in UB.

```cpp run title="coro-ref.cpp" ub
#include <coroutine>
#include <cstdio>
#include <exception>
#include <string>
#include <utility>

struct Lazy {                 // minimal lazy coroutine: suspended on creation, runs only on get()
  struct promise_type {
    std::size_t value = 0;
    Lazy get_return_object() { return Lazy{Handle::from_promise(*this)}; }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_value(std::size_t v) { value = v; }
    void unhandled_exception() { std::terminate(); }
  };
  using Handle = std::coroutine_handle<promise_type>;
  explicit Lazy(Handle h) : h(h) {}
  Lazy(Lazy&& o) noexcept : h(std::exchange(o.h, {})) {}
  ~Lazy() { if (h) h.destroy(); }
  std::size_t get() { h.resume(); return h.promise().value; }
  Handle h;
};

Lazy length(const std::string& s) {   // the coroutine stores only a reference
  co_return s.size();
}

int main() {
  Lazy t = length(std::string(100, 'x'));   // the temporary string is destroyed at the end of this line
  std::printf("%zu\n", t.get());            // the coroutine only starts running now: s dangles
}
```

ASan reports stack-use-after-scope inside `s.size()`.

For an ordinary function, a `const std::string&` parameter receiving a temporary is safe; for a coroutine, the execution of the body is deferred until after the call expression, which makes this the most dangerous form. Coroutine parameters should be passed by value; `std::string_view` and `std::span` parameters have the same problem. For more lifetime problems specific to coroutines, see [[topics/coroutines]].

## 9. The array behind `std::initializer_list`

`std::initializer_list<E>` is just a pair of pointers to a compiler-generated `const E[N]` array, which the standard calls the [[g:backing-array|backing array]]. This array is like any other temporary, except that initializing an `initializer_list` object from it extends its lifetime as a reference binding would ([[dcl.init.list#6]]). The extension doesn't carry over to copies of the `initializer_list`:

```cpp run title="ilist.cpp" ub
#include <cstdio>
#include <initializer_list>
std::initializer_list<int> defaults(int a) { return {a, a + 1, a + 2}; }  // the array is a local temporary
int main(int argc, char**) {
  for (int x : defaults(argc)) std::printf("%d ", x);   // UB
  std::puts("");
}
```

Clang gives a `-Wreturn-stack-address` warning, and ASan reports stack-use-after-return.

C++26's [[P2752R3]] allows implementations to put a backing array whose elements are all constants into static storage, but only the storage location changed, not the lifetime rules; the standard's example also stresses that the array does not outlive the function call. Don't store an `initializer_list` in a member or return it; when you need to keep it, copy it into a `std::vector` or `std::array`.

## 10. Iterator and reference invalidation

Every modifying operation of a standard library container specifies which references, pointers and iterators it [[g:iterator-invalidation|invalidates]]. For example, `vector::push_back` reallocates when the new size exceeds the capacity, invalidating all references, pointers and iterators ([[vector.modifiers#2]]). Using them afterwards violates a library precondition and is likewise UB.

```cpp run title="invalidate.cpp" ub
#include <cstdio>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  int& first = v[0];
  v.push_back(4);                  // not enough capacity: reallocates, first dangles
  std::printf("%d\n", first);      // UB
}
```

ASan reports heap-use-after-free. Common variants: `push_back` or `erase` while iterating; storing `&v[i]` in another container; continuing to use an earlier `c_str()` after modifying a `std::string`. The rules differ a lot between containers: `std::list` and `std::map` invalidate nothing on insertion; inserting at either end of a `std::deque` invalidates iterators but not references; rehashing an `unordered_map` invalidates iterators but not references. Go by each container's clauses.

## 11. Tools

### Compiler warnings

`diagtool tree dangling` lists Clang 23's `-Wdangling` group:

```text
-Wdangling
  -Wdangling-assignment
  -Wdangling-assignment-gsl
  -Wdangling-capture
  -Wdangling-field
  -Wdangling-initializer-list
  -Wdangling-gsl
  -Wreturn-stack-address
```

All the ones that appear on this page are on by default and need no extra `-W` option. They only look at patterns within a single declaration or `return` statement; reasoning across functions needs annotations.

### `[[clang::lifetimebound]]`

This attribute tells the compiler that the lifetime of the return value is bounded by a parameter:

```cpp
#include <map>
#include <string>
const std::string& get_or(const std::map<int, std::string>& m, int key,
                          const std::string& fallback [[clang::lifetimebound]]) {
  auto it = m.find(key);
  return it == m.end() ? fallback : it->second;
}
struct Person {
  std::string name;
  const std::string& get_name() const [[clang::lifetimebound]] { return name; }
};
Person make_person();
void use(const std::map<int, std::string>& m) {
  const std::string& a = get_or(m, 1, "none");      // warning: temporary string bound to a lifetimebound parameter
  const std::string& b = make_person().get_name();  // warning: temporary Person
  const std::string& c = make_person().name;        // OK: member access, the whole Person is extended
  (void)a; (void)b; (void)c;
}
```

Clang 23 gives `-Wdangling` for the `a` and `b` lines; with the two annotations removed, the same code gets no warnings at all. `[[clang::lifetimebound]]` written after a member function's declarator applies to `*this`. The attribute doesn't change the program's semantics; it only adds diagnostics.

### AddressSanitizer

| Report category | Corresponding dangling | Notes |
|---|---|---|
| `heap-use-after-free` | Heap memory has been freed (a `string`'s buffer, `vector` reallocation) | On by default |
| `stack-use-after-scope` | A temporary or block-scope variable has been destroyed, but we're still in the same stack frame | On by default |
| `stack-use-after-return` | The function has returned | On macOS needs `ASAN_OPTIONS=detect_stack_use_after_return=1`; has extra overhead |

ASan can only report accesses that actually execute, and only when the memory the object occupied has been marked inaccessible. Memory pools and custom allocators can make it miss things.

With Homebrew Clang 23 and the system linker on macOS, ASan's symbolizer can't read the default DWARF 5 debug info, and reports show only offsets like `main+0x70`. Add `-gdwarf-4` to get file names and line numbers as shown above.

## Questions

!!! question "1"
    In `const auto& [k, v] = *map.find(key);`, do `k` and `v` dangle? What if `find` is replaced with a function that returns a `std::pair` by value?

<details markdown="1">
<summary>Answer</summary>

`*map.find(key)` is an lvalue referring to an element of the map. The hidden variable behind the structured binding is a reference to that element, there is no temporary, and nothing dangles as long as the element isn't erased.

With a function returning `std::pair` by value, the initializer is a prvalue, the hidden variable `const auto& e = f();` binds directly to the materialized temporary, whose lifetime is extended by [[class.temporary#6.1]], and `k` and `v` refer to the members of that temporary pair, so nothing dangles either. Only a form like `const auto& [k, v] = f().get_pair_ref();`, going through a function call that returns a reference, dangles.
</details>

!!! question "2"
    What is the difference between `std::string_view sv = "literal";` and `std::string_view sv = std::string("literal");`?

<details markdown="1">
<summary>Answer</summary>

String literal objects have static storage duration ([[lex.string]]), so the `sv` in the first never dangles. The second constructs a temporary `std::string`, `sv` points to its buffer, the temporary is destroyed at the semicolon, and `sv` dangles immediately; Clang gives `-Wdangling-gsl`. Likewise, after `using namespace std::literals;`, `std::string_view sv = "x"s;` dangles, while `"x"sv` doesn't.
</details>

!!! question "3"
    C++26 made a `return` binding a temporary ill-formed. Why didn't it also make `const int& m = std::max(1, 2);` ill-formed?

<details markdown="1">
<summary>Answer</summary>

The `return` case can be decided purely syntactically: what is bound is a temporary expression, and it is certainly destroyed once the function returns. The `std::max` case requires knowing which parameter the returned reference comes from, which is a property of the function body and not visible in the declaration, so the standard can't decide it at the call site (`max` could also return a reference to a static object). Expressing such cross-function information needs an annotation like `[[clang::lifetimebound]]`, and the standard currently has no corresponding language mechanism.
</details>
