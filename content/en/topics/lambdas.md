---
title: Lambdas and closures
summary: "What a lambda expression actually creates: the closure class the compiler writes for you, the rules and costs of capture, the various forms of the call operator, the ODR problems that come from closure types being unique, and dangling caused by captures."
tags: lambda, closures, capture, ODR, dangling, topic
updated: 2026-10-19
---

!!! tldr
    - A lambda expression defines an unnamed class (the closure type) and creates an object of it (the closure object). Variables captured by copy are data members of that class, and the lambda body is its `operator()`.
    - Capture by copy takes a snapshot when the closure is created; capture by reference is just an alias. Variables with static storage duration are never captured, and `[=]` in a member function captures the pointer `this`, not the object.
    - The call operator is `const` by default; `auto` parameters make it a member template; C++23's `this auto self` lets a lambda call itself recursively.
    - Every lambda expression has a unique type, even `decltype([]{})`. Using a lambda's type in a namespace-scope alias in a header makes different translation units see different types.
    - Whenever a closure may outlive the current scope, don't capture local variables by reference, and don't capture non-owning values such as pointers and `string_view` by copy.

## The class the compiler writes for you

```cpp
int n = 10, total = 0;
auto f = [n, &total](int x) {
  total += x * n;
  return total;
};
f(1);   // total == 10
```

The standard says a lambda expression is a prvalue whose type is a unique unnamed class called the [[g:closure-type|closure type]] ([[expr.prim.lambda.closure#1]]); the object obtained by evaluating it is called the [[g:closure-object|closure object]] ([[expr.prim.lambda.general#2]]). The code above is roughly equivalent to the version on the right:

<div class="compare" markdown="1">

```cpp
auto f = [n, &total](int x) {
  total += x * n;
  return total;
};
```

```cpp
class __lambda_1 {
  int __n;         // by copy: a copy
  int& __total;    // by reference: illustrative
public:
  __lambda_1(int& n, int& total)
    : __n(n), __total(total) {}
  int operator()(int x) const {
    __total += x * __n;
    return __total;
  }
};
auto f = __lambda_1{n, total};
```

</div>

This is only a model. The real closure type has no such constructor, and its members have no names; whether capturing by reference creates data members is unspecified ([[expr.prim.lambda.capture#12]]). Still, nearly every property of lambdas can be derived from this model:

| Lambda syntax | Corresponding thing in the closure type | Source |
|---|---|---|
| Capture by copy `[n]`, `[=]` | An unnamed data member of the same type as `n` (keeping `const`) | [[expr.prim.lambda.capture#10]] |
| Capture by reference `[&total]`, `[&]` | Usually a pointer or reference member; the standard doesn't specify | [[expr.prim.lambda.capture#12]] |
| Lambda body | A public, inline `operator()` | [[expr.prim.lambda.closure#5]] |
| Default | `operator()` is a `const` member function | [[expr.prim.lambda.closure#7]] |
| `mutable` | `operator()` is not `const` | Same as above |
| `static` {{c++23}} | `operator()` is a static member function | Same as above |
| `auto` parameters, `<class T>` | `operator()` is a member function template | [[expr.prim.lambda.closure#5]] |
| No captures | An additional conversion function to a function pointer | [[expr.prim.lambda.closure#11]] |

The `operator()` in the model is `const`, yet it can modify `total`. The reason is that what a const member function can't change is the members themselves; `__total` is a reference, and what gets modified is the outside variable it refers to. Lambdas work the same way: a lambda with `[&total]` can modify `total` without `mutable`.

The full rules for each feature are in [[expr.prim.lambda]]; this page only covers how to use the model to understand and avoid problems.

## Properties of closure types

### Every lambda is a new type

```cpp run title="unique.cpp" ok
#include <type_traits>
int main() {
  auto a = [] { return 1; };
  auto b = [] { return 1; };
  static_assert(!std::is_same_v<decltype(a), decltype(b)>);
  static_assert(!std::is_same_v<decltype([] {}), decltype([] {})>);   // C++20
  return a() - b();
}
```

Two character-for-character identical lambda expressions are still two classes, just like writing `struct {}` twice. So the type of a closure can only be obtained through `auto`, `decltype` or template argument deduction, and storing closures in variables of one uniform type needs a type-erasing wrapper such as `std::function`.

### Not an aggregate; special members depend on captures

A closure type is not an aggregate ([[expr.prim.lambda.closure#4]]), so you can't forge a closure object with `decltype(f){…}`. Its default constructor and assignment operators depend on whether it has captures ([[expr.prim.lambda.closure#17]]):

| | No captures | With captures |
|---|---|---|
| Default construction | Yes {{c++20}} | No |
| Copy and move construction | Yes | Yes (move-only if a member is non-copyable) |
| Copy assignment | Yes {{c++20}} | Deleted |
| Move assignment | Yes {{c++20}} | Not declared; assignment selects the deleted copy assignment |

Verified with `<type_traits>` on Clang 23: for a closure with no captures, `is_default_constructible` and `is_copy_assignable` are both true, and `is_empty` is true; after capturing an `int`, both are false; after capturing a `std::unique_ptr`, `is_copy_constructible` is false and `is_move_constructible` is true.

Closures with captures can't be assigned, which you run into when using a lambda as a container's template argument; see the last section.

### Size

A closure's size is its data members plus alignment. Measured with Clang 23 (arm64, libc++):

| Lambda | `sizeof` | Notes |
|---|---|---|
| `[] {}` | 1 | Empty class |
| `[a] { return a; }` | 4 | One `int` member |
| `[a, d] { return a + d; }` | 16 | `int` + `double`, aligned to 8 |
| `[&a] { return a; }` | 8 | One pointer |
| `[&a, &b]`, `[&]` using `a` and `b` | 16 | One pointer per variable captured by reference |
| `[=] { return N + 1; }`, `const int N = 10` | 1 | No member for `N`; see below |
| `[=] { return &N; }` | 4 | Takes the address, so a member is required |
| `[s]`, `std::string s` | 24 | One `std::string` |
| `[this]` | 8 | One pointer |
| `[*this]`, object with three `int`s | 12 | A copy of the whole object |

The standard allows the size, alignment, trivial copyability and standard-layout-ness of closure types to vary between implementations ([[expr.prim.lambda.closure#4]]); don't rely on these numbers.

## Captures

### By copy is a snapshot, by reference is an alias

```cpp run title="snapshot.cpp" ok
#include <cstdio>
int main() {
  int x = 1;
  auto byval = [x] { return x; };    // copies x now
  auto byref = [&x] { return x; };   // remembers x itself
  x = 2;
  std::printf("%d %d\n", byval(), byref());   // 1 2
}
```

Members captured by copy are direct-initialized when the lambda expression is evaluated ([[expr.prim.lambda.capture#16]]) and are unrelated to the original variable from then on. However many times it is called later and however the original variable changes, `byval` sees the value from creation time.

### Only what is used gets captured

With a **capture-default** `[=]` or `[&]`, the compiler captures only the enclosing local entities that the lambda body actually names and that are potentially evaluated ([[expr.prim.lambda.capture#7]]). Variables that aren't used don't go into the closure.

Only [[g:local-entity|local entities]] can be captured: variables with automatic storage duration, structured bindings, and `*this` in member functions. Global variables and static local variables need not and cannot be captured; the lambda body accesses the original objects directly:

```cpp run title="static.cpp" ok
#include <cstdio>
int g_count = 0;
int main() {
  static int s = 1;
  auto l = [=] { return s + g_count; };   // nothing captured
  s = 10;
  g_count = 5;
  std::printf("%d %zu\n", l(), sizeof l);   // 15 1
}
```

`[=]` looks as if it copies everything, but neither `s` nor `g_count` is a local entity; `l()` reads the values at call time, 15, and the closure's size is 1.

Constants are another special case. Reading a constant's value is not an [[g:odr-use]] (using it in a way that requires the variable itself to exist, such as taking its address or binding a reference to it); the compiler just uses its value. So a lambda can read a constant without capturing it, and while reading a constant under `[=]` counts as an implicit capture, by [[expr.prim.lambda.capture#11]] the name still refers to the enclosing variable, and the implementation may not allocate a member for it. That's why `[=] { return N + 1; }` has size 1 in the table above. Once you take its address or bind it to a `const int&` parameter (for example by passing it to `std::max`), it must really be captured.

### `this` and `*this`

A lambda in a member function that accesses the member `id` actually accesses `this->id`. What's captured is the pointer `this`, which amounts to capturing the whole object by reference:

```cpp run title="this.cpp" ub
#include <cstdio>
#include <functional>
#include <memory>
struct Widget {
  int id = 7;
  std::function<int()> getter() {
    return [=] { return id; };   // captures this, not a copy of id
  }
};
int main() {
  auto w = std::make_unique<Widget>();
  auto g = w->getter();
  w.reset();
  std::printf("%d\n", g());      // UB: reads a member through a dangling this
}
```

`[=]` makes people think the object was copied, so C++20 deprecated `[=]` implicitly capturing `this` ([[expr.prim.lambda.capture#7]], [[depr.capture.this]], [[P0806R2]]). Clang 23 warns `-Wdeprecated-this-capture` under `-std=c++20` and later, but not under `-std=c++17`; ASan reports heap-use-after-free at `g()`.

Two explicit forms:

<div class="compare" markdown="1">

```cpp
// by reference: the object must live longer
return [=, this] { return id; };
```

```cpp
// C++17: copy the whole object
return [*this] { return id; };
```

</div>

`[*this]` copies the object into the closure ([[P0018R3]]); destroying or modifying the object afterwards has nothing to do with the closure. The cost is copying the whole object, which doesn't suit large or non-copyable objects. Another common approach in asynchronous callbacks is to capture a `shared_ptr` (for example `[self = shared_from_this()]`), so that the closure shares ownership of the object.

### init-capture and move capture

`[name = initializer]` is called an **init-capture**, and is as if the closure declared a member `auto name = initializer;` ([[expr.prim.lambda.capture#6]]). It solves two problems: giving the member a different name or initializing it from an arbitrary expression, and moving move-only objects into the closure.

```cpp run title="move-capture.cpp" ok
#include <cstdio>
#include <memory>
#include <vector>
int main() {
  auto buf = std::make_unique<std::vector<int>>(1000, 1);
  auto task = [b = std::move(buf)] { return b->size(); };   // the closure owns the buffer
  std::printf("%d %zu\n", buf == nullptr, task());          // 1 1000
}
```

If a move-only member is captured by copy, the closure's copy constructor is deleted and the closure is move-only too. `std::function` requires the callable to be copyable, so `std::function<std::size_t()> f = std::move(task);` is ill-formed; libc++ in our tests reports a call to the closure's implicitly deleted copy constructor. C++23's `std::move_only_function` was designed for exactly this case; libc++ with Clang 23 doesn't provide it yet.

init-capture differs from simple capture in two more ways:

- It deduces like `auto`, dropping top-level `const`: given `const std::string s;`, the member for `[s]` is a `const std::string`, while for `[s = s]` it is a `std::string`.
- Explicitly captured members are initialized in the order of the capture list ([[expr.prim.lambda.capture#15]]), so `[n = v.size(), v = std::move(v)]` takes the size first and then moves; the other way round it would read a moved-from object.

### Structured bindings and packs

Since C++20, structured bindings are local entities that can be captured ([[P1091R3]]), and a function parameter pack can be moved into the closure as a whole with an init-capture ([[P0780R2]]):

```cpp run title="pack.cpp" ok
#include <utility>
template<class... Ts> constexpr auto bind_all(Ts... ts) {
  return [...xs = std::move(ts)](auto f) { return f(xs...); };   // init-capture pack
}
static_assert(bind_all(1, 2, 3)([](int a, int b, int c) { return a + b + c; }) == 6);

int sum_pair() {
  auto [p, q] = std::pair{1, 2};
  return [p, &q] { return p + q; }();   // captures structured bindings
}
int main() { return sum_pair() - 3; }
```

Under `-std=c++17`, Clang 23 gives only C++20 extension warnings for both forms. The rules for where the `...` goes in pack expansions are in [[expr.prim.lambda.capture#18]] and [[expr.prim.lambda]].

## The call operator

### `const` and `mutable`

The call operator is `const` by default, so members captured by copy can't be modified in the lambda body. `mutable` removes that `const`, and the closure becomes a stateful function object:

```cpp run title="mutable.cpp" ok
#include <algorithm>
#include <cstdio>
#include <vector>
int main() {
  auto counter = [n = 0]() mutable { return ++n; };
  std::vector<int> v(3);
  std::generate(v.begin(), v.end(), counter);   // passed by value; a copy is modified
  std::printf("%d %d %d | %d\n", v[0], v[1], v[2], counter());   // 1 2 3 | 1
}
```

The state lives in the closure object, and copying the closure copies the state. Most standard algorithms take function objects by value, so `counter`'s own `n` didn't change, and the last call returns 1. When the caller needs to see the state, capture an outside variable by reference, or pass `std::ref(counter)`.

<div class="compare" markdown="1">

```cpp
auto d = [n = 0] { return ++n; };
// error: operator() is const,
// member n can't be modified
```

```cpp
const auto c = [n = 0]() mutable {
  return ++n;
};
c();   // error: non-const operator()
       // can't be called on a const object
```

</div>

### Generic lambdas and template lambdas

A lambda with `auto` in its parameters is called a [[g:generic-lambda|generic lambda]]. Its `operator()` is a member function template, with one template parameter for each `auto` ([[expr.prim.lambda.closure#5]]). Since C++20 a template parameter list can also be written directly ([[P0428R2]]):

```cpp run title="generic.cpp" ok
#include <cstdio>
#include <vector>
int main() {
  auto count = [](auto&&... args) { return sizeof...(args); };   // template<class... Ts>
  auto first = []<class T>(const std::vector<T>& v) -> T { return v.front(); };
  auto make  = []<class T>() { return T{42}; };                   // T can't be deduced
  std::printf("%zu %d %g\n", count(1, 'a', "s"), first(std::vector{7, 8}),
              make.operator()<double>());
}
```

A template parameter list suits three situations: you need a name for the type (`T`), you need to constrain the shape of a parameter (`const std::vector<T>&`), or for perfect forwarding you'd rather write `std::forward<T>(x)` than `std::forward<decltype(x)>(x)`. When a template parameter can't be deduced from the arguments, it has to be given explicitly as in `make.operator()<double>()`; such a lambda is usually better rewritten as an ordinary function template.

`auto` parameters of generic lambdas are deduced by the rules of template argument deduction, exactly as for function templates; see [[topics/type-deduction]].

### `constexpr`, `consteval`, `static`

| Syntax | Meaning |
|---|---|
| Nothing | If it meets the requirements of a constexpr function, `operator()` is automatically constexpr {{c++17}} ([[P0170R1]]) |
| `constexpr` | Requires it to be a constexpr function |
| `consteval` {{c++20}} | `operator()` is an immediate function, callable only at compile time |
| `static` {{c++23}} | `operator()` is a static member function, and there may be no captures ([[P1169R4]]) |

```cpp run title="specifiers.cpp" ok
auto sq = [](int x) { return x * x; };   // implicitly constexpr
static_assert(sq(4) == 16);
auto inc = [](int x) consteval { return x + 1; };
static_assert(inc(1) == 2);
auto twice = [](int x) static { return 2 * x; };
static_assert(decltype(twice)::operator()(3) == 6);   // no object needed
int main() { return twice(0); }
```

The non-static `operator()` of a lambda without captures still takes an object parameter pointing to the empty closure. `static` removes that parameter, and is commonly used for stateless function objects such as comparators and projections for standard algorithms. More on compile-time computation is in [[topics/compile-time-programming]].

### Recursion: the explicit object parameter

The closure type has no name, and `this` inside a lambda body refers to the enclosing object, so before C++23 a lambda had no direct way to call itself. C++23's explicit object parameter ([[P0847R7]]) makes the first parameter the closure object itself:

<div class="compare" markdown="1">

```cpp
// C++14: pass itself in as an argument
auto fib = [](auto& self, int n)
    -> int {
  return n < 2 ? n
       : self(self, n - 1)
       + self(self, n - 2);
};
fib(fib, 20);   // 6765
```

```cpp
// C++23: this auto self
auto fib = [](this auto self, int n)
    -> int {
  return n < 2 ? n
       : self(n - 1) + self(n - 2);
};
fib(20);        // 6765
```

</div>

Both versions write `-> int` explicitly. There is only one `return` here, and the recursive calls are inside it; at that point the return type hasn't been deduced yet, and calling the function is ill-formed ([[dcl.spec.auto.general#13]]). If you write `if (n < 2) return n;` first, the later recursive calls can use the type already deduced.

Another common form is `std::function<int(int)> fib = [&fib](int n) {…};`. It works, but every recursive call goes through a type-erased indirect call, and the closure captures `fib` itself by reference, which easily dangles once `fib` is copied or moved.

When `self` is passed by value, each level of recursion copies the closure once; with captures, write `this const auto& self` to avoid the copy.

## Conversion to a function pointer

A lambda with no captures, that isn't generic and has no explicit object parameter, can be implicitly converted to a function pointer with the same signature ([[expr.prim.lambda.closure#11]]). A function pointer is just an address with nowhere to keep captured state, so lambdas with captures can't be converted.

```cpp run title="fnptr.cpp" ok
#include <cstdio>
#include <cstdlib>
int main() {
  int a[] = {3, 1, 2};
  std::qsort(a, 3, sizeof(int), [](const void* l, const void* r) {   // converted to a function pointer
    int x = *static_cast<const int*>(l), y = *static_cast<const int*>(r);
    return (x > y) - (x < y);
  });
  auto p = +[](int i) { return i * 2; };   // unary + triggers the conversion; p has type int(*)(int)
  std::printf("%d %d %d %d\n", a[0], a[1], a[2], p(21));   // 1 2 3 42
}
```

C-style callback interfaces usually take a `void*` user-data parameter; a stateful lambda can put its state there, while the callback itself is still a lambda without captures. A generic lambda without captures has a conversion function template; the rules are in [[expr.prim.lambda]].

## Unevaluated contexts and the ODR

Since C++20, lambdas may appear in unevaluated operands such as `decltype` and `sizeof` ([[P0315R4]]), and together with closures without captures being default-constructible ([[P0624R2]]), `decltype([](int a, int b) { return a > b; })` can be used directly as a comparator type. But each occurrence is a new type, even in an alias template: in `template<class T> using A = decltype([] {});`, `A<int>` and `A<char>` are different closure types ([[temp.alias#5]]).

Put such an alias in a header and trouble starts:

```cpp title="cmp.h"
#include <set>
using ByDesc = decltype([](int a, int b) { return a > b; });
using DescSet = std::set<int, ByDesc>;
int largest(const DescSet& s);
```

```cpp title="a.cpp"
#include "cmp.h"
int largest(const DescSet& s) { return *s.begin(); }
```

```cpp title="b.cpp" ifndr
#include "cmp.h"
#include <cstdio>
int main() { DescSet s{1, 3, 2}; std::printf("%d\n", largest(s)); }
```

`cmp.h` is included twice, so the lambda expression appears twice, and `ByDesc` in `a.cpp` and in `b.cpp` are two different types. So the parameter types of `largest` in the two files differ, making them two different functions: the one `b.cpp` calls is never defined, and by [[basic.def.odr#12]] the program is ill-formed, no diagnostic required. Clang 23 gives `largest` internal linkage and warns "function 'largest' has internal linkage but is not defined", and linking fails with an undefined symbol.

The ODR's guarantee for lambdas covers only the inside of definitions of entities that may be defined repeatedly in several translation units ([[g:definable-item|definable items]]: inline functions and variables, classes, templates and so on): corresponding lambdas in those definitions are treated as the same closure type ([[basic.def.odr#16]], [[basic.def.odr#18]]). A type alias at namespace scope is not a definable item and doesn't get this guarantee. The fix is to put the lambda in the initializer of an inline variable:

```cpp title="cmp.h" ok
#include <set>
inline constexpr auto by_desc = [](int a, int b) { return a > b; };
using DescSet = std::set<int, decltype(by_desc)>;
int largest(const DescSet& s);
```

Now `by_desc` is the same variable in every translation unit, and its type is the same closure type. Clang 23 emits a symbol with external linkage, which `c++filt` demangles to `largest(std::__1::set<int, by_desc::'lambda'(int, int) const, ...> const&)`; the closure type is named after the variable `by_desc`, the program links normally and prints 3.

<details class="fine" markdown="1"><summary>Other related rules</summary>

- A lambda inside the body of an inline function is safe: when the function definition appears in several translation units, it behaves as if there were only one definition (`f` in Example 8 of [[basic.def.odr#19]]).
- A lambda in a default argument of an inline function is not protected: each translation unit gets a different closure type, and the program is ill-formed, no diagnostic required (`g` in the same example). Default arguments of member functions within a class definition are an exception (`X::h` in the example).
- By [[basic.def.odr#18]], a lambda written in a class definition (for example `struct H { using type = decltype([](int a, int b) { return a > b; }); };`) should also be the same type in every translation unit. Clang 23 still gives this form an internal mangled name, and the example above still fails to link, so an inline variable is the safer choice for now.

</details>

## Dangling and the lifetime of captures

A closure object is an ordinary object: members captured by copy are constructed, copied and destroyed along with the closure.

```cpp run title="lifetime.cpp" ok
#include <cstdio>
struct T {
  T() { std::puts("T()"); }
  T(const T&) { std::puts("T(const T&)"); }
  T(T&&) noexcept { std::puts("T(T&&)"); }
  ~T() { std::puts("~T()"); }
};
int main() {
  T t;                            // T()
  {
    auto l = [t] {};              // T(const T&): copied when the closure is created
    auto l2 = l;                  // T(const T&): copying the closure copies the member
  }                               // ~T() ~T(): both closures destroyed
  {
    auto m = [u = static_cast<T&&>(t)] {};   // T(T&&)
  }                               // ~T()
}                                 // ~T(): t itself
```

All that capture by copy guarantees is the lifetime of the member itself. When the member is a non-owning value, the closure dangles all the same. Three common cases:

1. Capturing a local variable by reference, with the closure returned, stored or handed to another thread; see section 7 of [[topics/dangling-references]].
2. `this` captured by `[=]` or `[this]` in a member function, with the object destroyed before the closure; see `this.cpp` above.
3. Capturing by copy a pointer, `std::string_view`, `std::span` or iterator whose referent dies first.

```cpp run title="view-capture.cpp" ub
#include <cstdio>
#include <functional>
#include <string>
#include <string_view>
std::function<std::size_t()> make() {
  std::string name = "a name long enough to live on the heap";
  std::string_view sv = name;
  return [sv] { return sv.size() + sv[0]; };   // copies the view, not the string
}
int main() { std::printf("%zu\n", make()()); }  // UB: name has been destroyed
```

Clang 23 gives no warning for this code, and ASan reports heap-use-after-free at `sv[0]`. When a closure is to outlive the current scope, capture only owning values: `std::string`, containers, `unique_ptr`, `shared_ptr`, or `[*this]`. Calling a closure after the lifetime of an entity captured by reference has ended is, as the note in [[expr.prim.lambda.capture#17]] points out, likely to result in UB.

## Using lambdas as container comparators and hashes

```cpp run title="containers.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>
#include <unordered_set>
struct Point { int x, y; };
int main() {
  // no captures: the type is enough; the container default-constructs the comparator (C++20)
  std::set<std::string, decltype([](const std::string& a, const std::string& b) {
             return a.size() < b.size(); })> by_len{"ccc", "a", "bb"};
  std::printf("%s\n", by_len.begin()->c_str());   // a

  auto h  = [](const Point& p) { return std::hash<int>{}(p.x) ^ (std::hash<int>{}(p.y) << 1); };
  auto eq = [](const Point& a, const Point& b) { return a.x == b.x && a.y == b.y; };
  std::unordered_set<Point, decltype(h), decltype(eq)> pts{{1, 2}, {1, 2}, {3, 4}};
  std::printf("%zu\n", pts.size());                // 2

  // with captures: the comparator object must be passed to the constructor
  int pivot = 10;
  auto near = [pivot](int a, int b) { return std::abs(a - pivot) < std::abs(b - pivot); };
  std::set<int, decltype(near)> s(near);
  s.insert({3, 12, 20});
  std::printf("%d\n", *s.begin());                 // 12
}
```

The type of a lambda without captures is default-constructible, so `std::set<K, decltype(lambda)>` needs no comparator object. Before C++20, closures couldn't be default-constructed, and you had to write `std::set<K, decltype(cmp)> s(cmp);`.

A comparator with captures has two limitations:

- It can't be default-constructed: `std::set<int, decltype(near)> s2;` is ill-formed. The default constructor of an associative container requires the comparator to meet *Cpp17DefaultConstructible* ([[associative.reqmts.general#20]]).
- It can't be assigned. libc++'s `set` assigns the comparator during copy assignment, and `s2 = s;` fails with "cannot be assigned because its copy assignment operator is implicitly deleted".

So when you need state and also need the container to be assignable, write the comparator as a named class; it can also define `is_transparent` to enable heterogeneous lookup, which a lambda can't do either, because nested types can't be added to a closure type.

## Questions

!!! question "1"
    What is the `sizeof` of each of the two closures below on Clang? Why do they differ?
    ```cpp
    void f() {
      const int N = 10;
      auto a = [=] { return N * 2; };
      auto b = [=] { const int& r = N; return r; };
    }
    ```

<details markdown="1">
<summary>Answer</summary>

On Clang 23, `a` is 1 and `b` is 4. Both lambdas implicitly capture `N`: `N` is named in a potentially evaluated way in the body, which satisfies [[expr.prim.lambda.capture#7]]. The difference is whether it is odr-used. `N * 2` only reads the constant's value, which isn't an odr-use, so by [[expr.prim.lambda.capture#11]] it refers to the enclosing `N`, and Clang allocates no member for it; `const int& r = N` binds a reference, which is an odr-use, and the reference must bind to the copy in the closure, so an `int` member is needed. The standard doesn't specify the size of a closure ([[expr.prim.lambda.closure#4]]).
</details>

!!! question "2"
    After `auto l = [v = std::vector<int>(100)]() mutable { v.push_back(1); };`, what do `std::function<void()> f = l;` and `std::function<void()> g = std::move(l);` each do? Can `l` still be used?

<details markdown="1">
<summary>Answer</summary>

Both are valid: `vector` is copyable, so the closure is copyable. `f = l` copies the whole closure, and `f` holds an independent 100-element `vector`; `g = std::move(l)` moves the closure, and `l`'s member `v` is moved out, left in a valid but unspecified state (empty on libc++). `l` can still be called, because the closure object is still alive; its `v` just no longer has the original contents. Copying and moving a closure are memberwise copy and move ([[expr.prim.lambda.closure#17]]).
</details>

!!! question "3"
    Before C++23, why couldn't you write a recursive lambda like this?
    ```cpp
    auto fact = [](int n) { return n < 2 ? 1 : n * fact(n - 1); };
    ```

<details markdown="1">
<summary>Answer</summary>

`fact` is declared with `auto`, so its type has to be deduced from the initializer, and the initializer uses `fact`. Referring to a name before its type has been deduced makes the program ill-formed ([[dcl.spec.auto.general#13]]); Clang 23 reports "variable 'fact' declared with deduced type 'auto' cannot appear in its own initializer". Changing to `[&fact]` doesn't help: the problem isn't capture but type deduction.

And the lambda body isn't in the scope of the closure type, so there is no name that refers to the closure itself. That's why C++23 introduced `this auto self`; the C++14 approach was to pass the closure itself in as an argument, or use a variable whose type is known in advance, such as a `std::function`.
</details>
