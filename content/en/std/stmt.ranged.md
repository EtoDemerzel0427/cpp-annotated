---
title: The range-based for statement
summary: "Range-based for is defined as a rewrite into an ordinary for loop; that rewrite decides how begin/end are found, what the loop variable binds to, and how long temporaries in the initializer live."
updated: 2026-10-21
---

!!! tldr
    - Range-based for has no semantics of its own; it is equivalent to an ordinary `for` loop written with `auto&& range`, `begin` and `end`.
    - Arrays use pointers directly; a class type uses member functions only if both `begin` and `end` are found among its members, and otherwise free functions `begin`/`end` are found by ADL only, with no ordinary lookup.
    - Since C++17, `begin` and `end` can have different types, and `end` can be a sentinel.
    - Since C++23, every temporary created in the initializer lives until the loop ends, so `for (int x : get().value())` no longer dangles; but a function returning a reference to its parameter still dangles.
    - `begin` and `end` are computed only once, before the loop starts; invalidating the iterators in the loop body (for example with `push_back` on a `vector`) is undefined behavior.

## The rewrite

¶1 The range-based for statement

```text
for ( init-statement(opt) for-range-declaration : for-range-initializer ) statement
```

is equivalent to

```text
{
    init-statement(opt)
    auto && range = for-range-initializer ;
    auto begin = begin-expr ;
    auto end = end-expr ;
    for ( ; begin != end; ++begin ) {
        for-range-declaration = * begin ;
        statement
    }
}
```

¶1.2 *range*, *begin* and *end* are exposition-only variables, and the program cannot refer to them by name. Every line of the rewrite has consequences:

| Line | Consequence |
|---|---|
| `auto&& range = init;` | An lvalue binds directly, without a copy; a prvalue is materialized as a temporary whose lifetime is extended to the whole loop |
| `auto begin = ...; auto end = ...;` | Two separate declarations, so the two can have different types; each is computed only once |
| `begin != end`, `++begin` | The iterator only needs to support `!=` and prefix `++` |
| `decl = *begin;` | The loop variable is declared anew in the block of the loop body each iteration |

¶1.1 If the initializer is an expression, it is regarded as if surrounded by parentheses, so that a comma is not misread as separating two declarators. So `for (int x : a, b)` iterates over the result of the comma expression `(a, b)`, that is, `b`.

The initializer can also be a braced list. Then `auto&& range = {1, 2, 3};` deduces `std::initializer_list<int>` ([[dcl.type.auto.deduct]]), and `<initializer_list>` must be included:

```cpp run ok
#include <initializer_list>
int main() {
    int s = 0;
    for (int x : {1, 2, 3}) s += x;
    return s == 6 ? 0 : 1;
}
```

## Where begin and end come from

¶1.3 Three cases are checked in order.

### Arrays

¶1.3.1 If *range* is a reference to an array, *begin-expr* is `range` (decayed to a pointer) and *end-expr* is `range + N`, where N is the array bound. If the bound is unknown or the element type is incomplete, the program is ill-formed, because `end` cannot be computed:

```cpp error
extern int arr[];               // unknown bound
int h() {
    int s = 0;
    for (int x : arr) s += x;   // error
    return s;
}
```

### Class types: members

¶1.3.2 If *range* is a reference to a class `C`, and searches in the scope of `C` for the names `begin` and `end` each find at least one declaration, `range.begin()` and `range.end()` are used.

The test is name lookup, not whether a call works. Any member named `begin` or `end` counts, including data members, types and enumerators. Once this path is taken, if `range.begin()` cannot be called, that is a compile error; there is no fallback to free functions.

Requiring both names to be found was a C++20 change, [[P0962R1]]. Before it, finding either one was enough to take the member path, which hurt classes derived from `std::ios_base`: `std::ios_base::end` is an enumerator, so these classes were considered to have a member `end`, and free `begin`/`end` written for them could never be used.

```cpp run ok
namespace N {
    struct R { int a[3]; int end; };   // has a member named end, but no begin
    int* begin(R& r) { return r.a; }
    int* end(R& r) { return r.a + 3; }
}
int main() {
    N::R r{{1, 2, 3}, 0};
    int s = 0;
    for (int x : r) s += x;   // takes the ADL path, using N::begin and N::end
    return s == 6 ? 0 : 1;
}
```

### Otherwise: ADL only

¶1.3.3 Otherwise, *begin-expr* and *end-expr* are `begin(range)` and `end(range)`, where `begin` and `end` undergo argument-dependent lookup only (ADL, which looks for functions in the namespaces associated with the argument types, see [[basic.lookup.argdep]]), not ordinary unqualified lookup (Note 1).

This way, whether a type can be used in a range-based for depends only on the type and its namespace, not on where the loop is written or what `using`s are around it. The price is that adding a `begin`/`end` pair for a third-party type in some other namespace does not work:

```cpp error
namespace M { struct Q { int a[2]; }; }
int* begin(M::Q& q) { return q.a; }   // in the global namespace, invisible to ADL
int* end(M::Q& q) { return q.a + 2; }
int g(M::Q& q) {
    int s = 0;
    for (int x : q) s += x;   // error: begin not found
    return s;
}
```

### begin and end can have different types {{c++17}}

The C++11 rewrite was `auto __begin = begin-expr, __end = end-expr;`. In one declaration, `auto` must deduce the same type, so the two had to have the same type. [[P0184R0]] in C++17 split it into two declarations, so `end` can be a **sentinel**: an object used only for comparison with the iterator to decide whether the end has been reached. That `std::default_sentinel_t` and `std::unreachable_sentinel_t` from the C++20 Ranges library work directly in range-based for relies on this change.

```cpp run ok
struct ZStr {                       // a string terminated by '\0'
    const char* p;
    struct Sentinel {};
    const char* begin() const { return p; }
    Sentinel end() const { return {}; }
};
bool operator!=(const char* it, ZStr::Sentinel) { return *it != '\0'; }
int main() {
    int n = 0;
    for (char c : ZStr{"hello"}) { (void)c; ++n; }   // no need to compute the length first
    return n == 5 ? 0 : 1;
}
```

## The loop variable

The *for-range-declaration* can be an ordinary declaration or a structured binding declaration. It is declared anew each iteration, with `*begin` as its initializer.

| Form | Effect |
|---|---|
| `for (auto x : r)` | each element is copied |
| `for (auto& x : r)` | lvalue reference; elements can be modified; cannot bind to a prvalue |
| `for (const auto& x : r)` | read-only, no copy |
| `for (auto&& x : r)` | binds to anything; suits generic code and iterators that return proxy objects |
| `for (const auto& [k, v] : m)` | structured binding |

Dereferencing an iterator of `std::vector<bool>` gives a proxy object (a prvalue), to which a non-const lvalue reference cannot bind:

<div class="compare" markdown="1">

```cpp error
#include <vector>
void f(std::vector<bool>& v) {
    for (auto& b : v)   // error
        b = true;
}
```

```cpp ok
#include <vector>
void f(std::vector<bool>& v) {
    for (auto&& b : v)  // OK
        b = true;       // written back through the proxy
}
```

</div>

The loop variable and the loop body are in the same block, so a variable of the same name cannot be declared at the outermost level of the loop body:

```cpp error
void k(int (&v)[3]) {
    for (int x : v) {
        int x = 1;   // error: x redeclared
        (void)x;
    }
}
```

!!! pitfall "Getting the element type wrong when iterating a map"
    The element type of `std::map<K, V>` is `std::pair<const K, V>`. Writing `for (const std::pair<K, V>& p : m)` mismatches the type, so each element is converted into a temporary `pair` and the reference binds to that temporary: one copy per iteration, and the address taken is not that of the element in the container. `const auto&` or a structured binding avoids this.

## Temporaries in the initializer {{c++23}}

### The problem

`auto&& range = ...;` extends only the temporary bound directly to `range`. If the initializer calls a member function on a temporary that returns a reference into it, the temporary is destroyed at the end of that declaration, and `range` becomes a dangling reference:

```cpp run ok
#include <optional>
#include <vector>
std::optional<std::vector<int>> get() {
    return std::vector<int>{1, 2, 3};
}
int main() {
    int s = 0;
    for (int x : get().value()) s += x;
    return s == 6 ? 0 : 1;
}
```

`value()` returns a reference to the `vector` inside the `optional`, and the `optional` returned by `get()` is a temporary. Run with Clang 23 and `-fsanitize=address`, it reports `stack-use-after-scope` under `-std=c++20` and runs normally under `-std=c++23`.

### The fix

Note 2 points to [[class.temporary#7]]: since C++23 ([[P2718R0]]), temporaries created in the initializer that would otherwise be destroyed at the end of that full-expression are all extended to the end of the loop. What is extended is every temporary in the initializer, not just the one bound directly to `range`.

The cost is that the initializer of a range-based for no longer behaves like an ordinary declaration `auto&& r = ...;`, and some temporaries (such as objects holding a lock) live longer than expected. C++23 accepted this cost because dangling is far more harmful.

### What the fix does not reach

Example 2 in the standard draws the boundary:

```cpp ub
#include <list>
using T = std::list<int>;
const T& f1(const T& t) { return t; }
const T& f2(T t)        { return t; }
T g();

void foo() {
    for (auto e : f1(g())) {}   // OK: the temporary from g() is extended
    for (auto e : f2(g())) {}   // UB
}
```

`f2` returns a reference to its own parameter `t`. A parameter is not a temporary and is not extended; it is destroyed when the function returns or at the end of the full-expression containing the call (which one is implementation-defined, see [[expr.call]]), either way before the loop body runs. Nor is there any other temporary to extend here: `g()` is a prvalue that directly initializes the parameter `t` ([[dcl.init.general#15.6.1]]), without going through a temporary. Clang gives a `-Wreturn-stack-address` warning at the definition of `f2`.

Likewise, temporaries created in the loop body, and temporaries created inside functions called by the initializer, are not extended.

## init-statement {{c++20}}

[[P0614R1]] in C++20 allows a range-based for to have an *init-statement*, placed before `auto&& range` in the rewrite. There are two common uses: holding a temporary explicitly to avoid dangling before C++23, and adding a counter to the iteration.

```cpp run ok
#include <cstddef>
#include <optional>
#include <vector>
std::optional<std::vector<int>> get() {
    return std::vector<int>{1, 2, 3};
}
int main() {
    int s = 0;
    for (auto opt = get(); int x : opt.value())  // held explicitly
        s += x;
    std::vector<int> v{10, 20, 30};
    for (std::size_t i = 0; int x : v) {         // with a counter
        s += static_cast<int>(i) * x;
        ++i;
    }
    return s == 6 + 20 + 60 ? 0 : 1;
}
```

## Modifying the container in the loop body

`begin` and `end` are computed only once, before the loop starts. If the loop body invalidates them, the subsequent `++begin`, `begin != end` and `*begin` all use invalid iterators, and the behavior is undefined:

```cpp ub
#include <vector>
int main() {
    std::vector<int> v{1, 2, 3};
    for (int x : v)
        if (x == 1) v.push_back(4);   // may reallocate, invalidating begin/end
}
```

## History

!!! history
    - C++11 introduced range-based for. At the time `begin` and `end` were in one declaration, and member lookup used the members if it found either one.
    - C++17: `begin` and `end` can have different types ([[P0184R0]]).
    - C++20: an *init-statement* is allowed ([[P0614R1]]); member lookup must find both `begin` and `end` ([[P0962R1]]).
    - C++23: temporaries in the initializer live until the end of the loop ([[P2718R0]]).
    - C++26's expansion statement `template for` ([[stmt.expand]]) reuses this subclause's definitions of *begin-expr* and *end-expr*.

## Questions

!!! question "1. How many times does the loop below iterate?"
    ```cpp
    int a[] = {1, 2, 3}, b[] = {4, 5};
    for (int x : a, b) { }
    ```

<details markdown="1">
<summary>Answer</summary>

Twice. By ¶1.1, the initializer is regarded as `(a, b)`, and the result of the comma expression is its right operand `b`, an lvalue of type `int[2]`. Clang warns that the left operand of the comma has no effect.
</details>

!!! question "2. A class has a member function `begin()` and no member named `end`, and its namespace has free functions `begin` and `end`. Which pair does range-based for use?"

<details markdown="1">
<summary>Answer</summary>

Since C++20, member lookup did not find both names, so ¶1.3.3 applies and both are the free functions found by ADL. In C++17 and earlier, finding the member `begin` meant taking the member path, and since `range.end()` does not exist, the program was ill-formed.
</details>

!!! question "3. Under C++23, are `for (char c : std::string("abc").substr(1))` and `for (char c : std::string_view(std::string("abc")))` safe?"

<details markdown="1">
<summary>Answer</summary>

Both are safe. In the first, `substr` returns a prvalue `std::string` that binds directly to `range`, which has been extended since C++11. In the second, `std::string("abc")` is a temporary created in the initializer; since C++23 it lives until the end of the loop, so the buffer the `string_view` points to stays valid; in C++20 and earlier this dangled.
</details>

## Summary

| Aspect | Rule |
|---|---|
| Rewrite | `auto&& range = init; auto begin = ...; auto end = ...; for (; begin != end; ++begin) { decl = *begin; body }` |
| Arrays | `range` and `range + N`; ill-formed if the bound is unknown or the element type incomplete |
| Classes | member functions if both `begin` and `end` are found among the members, otherwise `begin(range)` and `end(range)` looked up only by ADL |
| Types of `begin`/`end` | may differ since C++17 |
| Temporaries | since C++23, temporaries in the initializer live until the end of the loop; parameters and objects inside called functions are not covered |
| init-statement | allowed since C++20, placed before `range` |
