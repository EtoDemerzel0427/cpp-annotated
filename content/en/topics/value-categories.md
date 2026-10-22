---
title: Value categories in practice
summary: How to tell whether any expression is an lvalue, xvalue or prvalue, and how value categories determine reference binding, overload resolution, decltype, move semantics and copy elision.
tags: value categories, move semantics, copy elision, decltype
updated: 2026-10-19
---

!!! tldr
    - Every expression belongs to exactly one of lvalue, xvalue and prvalue; the value category is a property of the expression and is independent of its type. In `int&& r`, the expression `r` is an lvalue.
    - Names are almost always lvalues; for function calls and casts, look at the return or target type: `T&` gives an lvalue, `T&&` an xvalue, and a non-reference a prvalue.
    - `decltype((e))` encodes the value category in the type: an lvalue gives `T&`, an xvalue `T&&`, a prvalue `T`.
    - `std::move` is just a cast to an xvalue; what actually moves the resources is the function that overload resolution selects as a result.
    - Since C++17 a prvalue isn't an object but a way of initializing one; initializing an object of the same type from a prvalue involves no copy and needs no copy or move constructor.

## A named rvalue reference is an lvalue

```cpp run title="overload.cpp" ok
#include <cstdio>
#include <utility>

void take(const int&) { std::puts("const&"); }
void take(int&&)      { std::puts("&&"); }

int main() {
    int i = 0;
    take(i);              // const&: an lvalue can't bind to &&
    take(1);              // &&: prvalue
    take(std::move(i));   // &&: xvalue
    int&& r = 2;
    take(r);              // const&: r is an lvalue
}
```

`r` has type `int&&`, yet `take(r)` picks the `const int&` version. The reason is that overload resolution doesn't look at what type the variable was declared with, but at the **value category** of the argument expression. The expression `r` is a name, and names are lvalues.

The value category is a property of expressions, not of values or objects. It is specified in [[basic.lval]]; this page covers how to determine it and use it.

## The three categories

[[basic.lval#1]] defines three primary categories, and every expression belongs to exactly one of them:

- **lvalue**: an expression that designates an object or function, such as the variable name `x`, `*p`, `a[i]`.
- **xvalue** (eXpiring value): also designates an object, but one whose resources can be reused, usually because it is near the end of its lifetime, such as `std::move(x)`.
- **prvalue** (pure rvalue): doesn't designate an existing object; its evaluation initializes an object or computes the value of an operand, such as `42`, `a + b`, `std::string("hi")`.

On top of these there are two combined categories:

- A **glvalue** is an lvalue or an xvalue; its evaluation determines the identity of an object, function (and, since C++26, a non-static data member or direct base class relationship).
- An **rvalue** is an xvalue or a prvalue; it can bind to an rvalue reference `T&&`.

| | Resources can be reused | Resources can't be reused |
|---|---|---|
| Designates an existing entity (glvalue) | xvalue | lvalue |
| Doesn't designate an existing entity | prvalue | |

Since C++17 a prvalue isn't an object but a way of initializing one. The object a prvalue initializes is called its **result object**, and is provided by the context the prvalue appears in ([[basic.lval#5]]). Treating a prvalue as a temporary object is the pre-C++17 model.

## Determining the category of any expression

### A probe

`decltype((e))` encodes the value category in the type ([[dcl.type.decltype]]): an lvalue gives `T&`, an xvalue `T&&`, a prvalue `T`. From this you can write a compile-time probe:

```cpp run title="probe.cpp" ok
#include <cstdio>
#include <utility>

template<class T> constexpr const char* category      = "prvalue";
template<class T> constexpr const char* category<T&>  = "lvalue";
template<class T> constexpr const char* category<T&&> = "xvalue";
#define CATEGORY(...) category<decltype((__VA_ARGS__))>

struct A { int m; };
A make();

int main() {
    int i = 0;
    int&& rr = 1;
    std::printf("%s %s %s %s %s\n",
        CATEGORY(i),              // lvalue
        CATEGORY(rr),             // lvalue: a named rvalue reference
        CATEGORY(std::move(i)),   // xvalue
        CATEGORY(i + 1),          // prvalue
        CATEGORY(make().m));      // xvalue
}
```

Clang 23 prints `lvalue lvalue xvalue prvalue xvalue`. The two layers of parentheses in the macro are necessary: with only one, `decltype(name)` gives the declared type of the name rather than the category of the expression (see below). The operand of `decltype` isn't evaluated, so `make` only needs a declaration, not a definition.

### Steps for determining it by hand

1. Names (*id-expressions*) are almost always lvalues. Variables (including variables of rvalue reference type), functions, data members, structured bindings and template parameter objects all are. There are two kinds of exceptions: enumerators, constant template parameters of non-class type and `this` are prvalues; move-eligible local variables in `return x;`, `co_return x;` and `throw x;` are xvalues (since C++23, [[expr.prim.id.unqual]]).
2. For function calls, including overloaded operators and conversion functions, look at the return type: `T&` gives an lvalue, `T&&` for an object type gives an xvalue, and a non-reference gives a prvalue. Returning an rvalue reference to a function gives an lvalue.
3. For casts, in whatever notation, look at the target type, with the same rules: `static_cast<T&>(e)` is an lvalue, `static_cast<T&&>(e)` an xvalue, `static_cast<T>(e)` a prvalue.
4. For built-in operators, consult the table below. Roughly: arithmetic, comparison, logical and bitwise operations and postfix `++` and `--` give prvalues; dereference `*p`, prefix `++` and `--`, and assignment give lvalues designating the original object.
5. Subobject access follows the object: for member access `e.m`, array subscripting and `.*`, the result is an lvalue when the object is an lvalue, and an xvalue when the object is an xvalue (or a prvalue converted into a temporary object). Static data members and reference members are exceptions and are always lvalues.
6. Parentheses don't change the value category: `(e)` is the same as `e`. But in `decltype` parentheses do change the result; see below.

### Reference table

| Expression | Category | Notes |
|---|---|---|
| Variable name `x`, of any type, including `T&&` | lvalue | [[expr.prim.id.unqual]] |
| A move-eligible `x` in `return x;` | xvalue | Since C++23 ([[P2266R3]]) |
| Function name `f` | lvalue | |
| Enumerator `Red` | prvalue | |
| Constant template parameter `N` of non-class type | prvalue | A template parameter object of class type is an lvalue |
| `this` | prvalue | [[expr.prim.this]] |
| String literal `"abc"` | lvalue | It is an array object with static storage duration; `&"abc"` is valid |
| Other literals `42`, `'a'`, `nullptr`, `true` | prvalue | |
| User-defined literal `"x"s` | Per the return type of `operator""` | |
| Lambda expression | prvalue | Initializes a closure object |
| `T(args)`, `T{args}` | prvalue | Per the rules for references when `T` is a reference type |
| `f()` | Per the return type | [[expr.call]] |
| `static_cast<T&>(e)`, `<T&&>`, `<T>` | lvalue, xvalue, prvalue | An lvalue when the target is an rvalue reference to a function |
| `std::move(x)` | xvalue | It's just `static_cast<T&&>` |
| `std::forward<T>(x)` | lvalue if `T` is an lvalue reference, otherwise xvalue | |
| `*p` | lvalue | [[expr.unary.op]] |
| `&x` | prvalue | |
| `++i`, `--i` | lvalue | [[expr.pre.incr]], designates `i` itself |
| `i++`, `i--` | prvalue | [[expr.post.incr]], the value is the old value before modification |
| `a = b`, `a += b` | lvalue | [[expr.assign]], designates the left operand |
| `a + b`, `-a`, `a < b`, `!a`, `a & b` | prvalue | Built-in arithmetic, comparison, logical and bitwise operations |
| Built-in `a[i]` | lvalue if the array operand is an lvalue or the operand is a pointer; xvalue if the array is an rvalue | [[expr.sub]] |
| `e.m`, non-static, non-reference data member | Same as `e` | If `e` is a prvalue it is first converted into a temporary object, and the result is an xvalue |
| `e.m`, reference member | lvalue | [[expr.ref]] |
| `e.s`, static data member | lvalue | |
| `e.f`, non-static member function | prvalue | Can only be called immediately |
| `p->m` | lvalue | Equivalent to `(*p).m` |
| `e.*pm`, pointer to data member | Same as `e` | [[expr.mptr.oper]] |
| `p->*pm`, pointer to data member | lvalue | |
| `c ? a : b` | When both sides are glvalues of the same type and category, that category; otherwise prvalue | [[expr.cond]] |
| `a, b` | Same as `b` | [[expr.comma]] |
| `throw e` | prvalue, type `void` | |
| `typeid(e)` | lvalue | Designates a `const std::type_info` object |
| `sizeof e`, `alignof(T)`, `noexcept(e)` | prvalue | |
| `new T` | prvalue | |
| `co_await e` | Per the return type of `await_resume()` | [[expr.await]] |

Note 3 in [[basic.lval#4]] lists all the sources of xvalues, which fall into three groups:

1. Returning or converting to an rvalue reference to an object: function calls, `static_cast<T&&>`, `std::move`.
2. Move-eligible names, such as `x` in `return x;`.
3. Subobject access on an xvalue or on a prvalue converted into a temporary object.

## decltype and value categories

[[dcl.type.decltype]] has two sets of rules, and the difference is that one layer of parentheses:

| Form | Rule | Result |
|---|---|---|
| Unparenthesized `decltype(name)`, `decltype(e.member)` | The declared type of the entity | May or may not be a reference, regardless of value category |
| Every other case, including `decltype((name))` | The expression's type plus its value category | An xvalue gives `T&&`, an lvalue `T&`, a prvalue `T` |

```cpp ok
#include <type_traits>
#include <utility>
int i = 0;
int&& rr = 0;
struct S { int m; };
const S cs{};

static_assert(std::is_same_v<decltype(i), int>);           // declared type
static_assert(std::is_same_v<decltype((i)), int&>);        // lvalue expression
static_assert(std::is_same_v<decltype(rr), int&&>);        // declared type
static_assert(std::is_same_v<decltype((rr)), int&>);       // rr as an expression is an lvalue
static_assert(std::is_same_v<decltype(std::move(i)), int&&>);
static_assert(std::is_same_v<decltype(i + 0), int>);
static_assert(std::is_same_v<decltype(cs.m), int>);        // declared type of the member
static_assert(std::is_same_v<decltype((cs.m)), const int&>); // expression: a member of a const S is a const lvalue
```

`decltype(auto)` follows the same rules, so an extra pair of parentheses in a `return` statement changes the return type from a value to a reference:

```cpp ok
int g;
decltype(auto) f1() { return g; }     // int
decltype(auto) f2() { return (g); }   // int&: parenthesized, returns a reference
```

Doing this with a local variable returns a dangling reference; since C++23 it deduces `int&&`, which dangles just the same. See [[topics/type-deduction]].

## Reference binding and overload resolution

The main use of value categories is deciding what a reference can bind to ([[dcl.init.ref]]):

| Reference type | Expressions it can bind to | Notes |
|---|---|---|
| `T&` | Non-const lvalues of `T` | Can't bind rvalues; that is, a non-const reference can't bind a temporary |
| `const T&` | Any expression of `T`, and expressions convertible to `T` | Binding a prvalue creates a temporary and extends its lifetime |
| `T&&` | rvalues of `T`, and expressions convertible to `T` (creating a new temporary) | Can't bind lvalues directly; binding a prvalue likewise creates a temporary and extends its lifetime |
| Forwarding references `auto&&`, `T&&` in templates | Any expression | For an lvalue argument `T` deduces `U&`, collapsing to `U&`; for an rvalue `T` deduces `U` |

In overload resolution, when two candidates differ only in `T&` versus `T&&`, an rvalue prefers to bind `&&`, and an lvalue can only choose `&` ([[over.ics.rank]]). The `take` example at the start, and the choice between a move constructor and a copy constructor, both rely on this rule.

## std::move and std::forward are just casts

`std::move` does nothing at run time; it is only a compile-time type conversion. Without `constexpr`, its whole implementation is:

```cpp
#include <type_traits>
template<class T>
std::remove_reference_t<T>&& move(T&& t) noexcept {
    return static_cast<std::remove_reference_t<T>&&>(t);
}
```

It converts any expression into an xvalue, so overload resolution selects the function that accepts `T&&`, such as the move constructor or move assignment operator. What actually transfers the resources is the function selected. It follows that:

- `std::move` on a const object gives a `const T&&`, which can't bind to the `T&&` parameter of the move constructor; overload resolution selects the `const T&` copy constructor, and it silently becomes a copy.
- For a type without a move constructor, `std::move` likewise becomes a copy.
- For scalars such as `int` and pointers, `std::move` has no effect; the result is just a copy of the value.

In `template<class T> void f(T&& x)`, whatever is passed in, the expression `x` in the function body is an lvalue, because it has a name. Passing `x` directly to the next function loses the information that the caller passed an rvalue. `std::forward<T>(x)` uses the information recorded in `T` to restore the original category:

```cpp run title="forward.cpp" ok
#include <cstdio>
#include <utility>

void sink(int&)  { std::puts("lvalue"); }
void sink(int&&) { std::puts("rvalue"); }

template<class T>
void relay(T&& x) {
    sink(x);                     // always an lvalue
    sink(std::forward<T>(x));    // restores the original category
}

int main() {
    int i = 0;
    relay(i);    // lvalue lvalue
    relay(1);    // lvalue rvalue
}
```

`std::forward<T>(x)` is essentially just `static_cast<T&&>(x)` too. When an lvalue is passed, `T = U&`, `U& &&` collapses to `U&`, and the result is an lvalue; when an rvalue is passed, `T = U`, and the result is an xvalue. Reference collapsing and the deduction rules are covered in [[topics/type-deduction]].

## Guaranteed copy elision {{c++17}}

In C++14 and earlier, return value optimization (RVO) was only an optimization the standard permitted: even if the compiler elided the copy, the elided copy or move constructor still had to be usable. So for types that can be neither copied nor moved, such as `std::mutex` and `std::atomic`, you couldn't even write a factory function that returns a new object by value.

C++17's [[P0135R1]] changed the model: when an object of the same type is initialized from a prvalue, the prvalue initializes the target object directly, with no temporary in between, so semantically there is no copy or move, and no corresponding constructor is needed ([[dcl.init.general#15]], [[class.copy.elision]]):

```cpp ok
#include <atomic>
#include <mutex>

struct Pinned {
    Pinned() = default;
    Pinned(const Pinned&) = delete;
    Pinned(Pinned&&) = delete;
};

Pinned make() { return Pinned{}; }   // OK: the prvalue directly initializes the caller's object
Pinned a = make();                   // OK
Pinned b = Pinned(Pinned(Pinned())); // OK: only one object
auto c = std::atomic<int>(0);        // OK: ill-formed in C++14 (atomic isn't copyable)
std::mutex m = std::mutex();         // OK: likewise
```

Returning a named local variable isn't covered by the guarantee:

```cpp error
struct Pinned {
    Pinned() = default;
    Pinned(const Pinned&) = delete;
    Pinned(Pinned&&) = delete;
};
Pinned make_named() {
    Pinned p;
    return p;          // error: needs a move constructor (NRVO is only permitted, not guaranteed)
}
```

| Situation | Since C++17 |
|---|---|
| `return T(...);`, returning a prvalue | Guaranteed: no copy or move |
| `T x = T(...);` | Guaranteed |
| `T x = cond ? T(1) : T(2);` | Guaranteed; the result of the conditional expression is a prvalue |
| `return local;`, named return value optimization (NRVO) | Elision permitted but not guaranteed; the type must be movable or copyable |
| `return param;`, a function parameter | NRVO not possible, but it is implicitly moved |
| `return std::move(local);` | Prevents NRVO and forces a move (Clang's `-Wpessimizing-move` warns) |

## Temporaries and lifetime extension

A prvalue is converted into a temporary object when an object is needed; this is called **temporary materialization** ([[class.temporary#2]]). A temporary is normally destroyed at the end of the full-expression it appears in. Binding a temporary directly to a reference (`const T&` or `T&&`) extends its lifetime to match the reference's. But "directly" is narrow:

```cpp run title="lifetime.cpp" ub
#include <cstdio>
#include <string>
#include <utility>

struct A { std::string s = "a string long enough to live on the heap"; };
A make() { return {}; }

int main() {
    const auto& r1 = make().s;           // OK: member access on a temporary; the whole temporary is extended
    auto&& r2 = std::move(make());       // dangling: the return value of std::move isn't the temporary itself
    std::printf("%zu\n", r1.size());     // OK
    std::printf("%zu\n", r2.s.size());   // UB: the temporary was destroyed at the end of the previous full-expression
}
```

`std::move` is a function call; `r2` binds to the reference it returns, not to the temporary itself, so there's no lifetime extension. Clang 23 gives a `-Wdangling` warning at compile time, and ASan reports `stack-use-after-scope` on the last line.

When a reference binds to a temporary or one of its subobjects via `.`, `[]`, `?:`, `,` and certain casts, the lifetime is extended; via any function call, including `std::move`, `std::min`, or a member function returning `*this`, it isn't, and the temporary is destroyed at the end of the full-expression as usual ([[class.temporary#6]]).

## Common misconceptions

!!! pitfall "An rvalue reference is an rvalue"
    Type and value category are two different things. In `int&& r = 1;`, `r` has type `int&&`, but the expression `r` is an lvalue. [[expr.type#1]] even adjusts the type of this expression to `int` first. One way to remember it: if it has a name, it's an lvalue.

!!! pitfall "Rvalues can't be modified"
    An xvalue is an rvalue but designates a real object: `std::move(v).push_back(1)` legitimately modifies `v`. A prvalue of class type can also call non-const member functions, such as `std::string().append("x")`. The restriction applies only to built-in operators: for `int f();`, `f() = 1` is ill-formed ([[basic.lval#10]] Note 10).

!!! pitfall "Literals are all rvalues"
    String literals are lvalues. A string literal is an array object with static storage duration; `&"abc"` is valid, with type `const char(*)[4]`.

!!! pitfall "After std::move the object is empty"
    `std::move` itself doesn't change the object. A moved-from standard library object is in a valid but unspecified state; a moved-from `int` keeps its value.

!!! pitfall "Adding std::move on return is faster"
    `return std::move(local);` turns an expression that could have had NRVO or an implicit move into an xvalue, preventing NRVO in exchange for an avoidable move. Since C++11 `return local;` moves implicitly, and C++20 and C++23 widened that rule further; when returning a local variable, just write `return local;`.

!!! pitfall "An xvalue is always about to be destroyed"
    An xvalue only means its resources may be reused, not that it is really about to be destroyed. `std::move(global)` is an xvalue designating a global object that lives until the end of the program.

## History

!!! history
    - C++98 had only lvalues and rvalues. `const T&` could bind rvalues, but there was no way to distinguish objects whose resources could be reused.
    - C++11 introduced xvalues for rvalue references and move semantics, and named glvalues and prvalues ([[N3055]]).
    - C++17's [[P0135R1]] made prvalues no longer objects, introducing result objects and temporary materialization, and copy elision became guaranteed.
    - C++20 extended implicit moves to local variables of rvalue reference type, operands of `throw`, and other places ([[P1825R0]]).
    - C++23's [[P2266R3]] made move-eligible names in `return` xvalues directly, and the results of `decltype(auto)` changed accordingly.
    - C++26's splice expressions (reflection) can designate non-static data members and direct base class relationships, and the definition of glvalue was extended accordingly.

## Questions

!!! question "Question 1"
    Given `std::vector<std::string> v;`, what is the category of `std::move(v)[0]`? And of `std::move(v[0])`?

<details markdown="1">
<summary>Answer</summary>

`std::move(v)[0]` is an lvalue. `vector::operator[]` is an overloaded operator returning `std::string&`, and by the rule for function calls (look at the return type), the result is an lvalue, even though `v` was converted to an xvalue. The built-in `[]` on an xvalue array gives an xvalue, but the standard containers' `operator[]` isn't overloaded on value category.

`std::move(v[0])` is an xvalue of type `std::string`. That's how to move a single element out of a container.
</details>

!!! question "Question 2"
    In `template<class T> void f(T&& x)`, why does `f(std::move(i))` deduce `T = int`, while `f(i)` deduces `T = int&`?

<details markdown="1">
<summary>Answer</summary>

Deduction looks at the value category of the argument expression. [[temp.deduct.call#3]] has a special rule for forwarding references: when the argument is an lvalue, the lvalue reference to `A` is used in place of `A` for deduction, so `T = int&`, and `T&&` collapses to `int&`. When the argument is an rvalue (xvalue or prvalue), deduction follows the ordinary rules: `T = int`, and the parameter type is `int&&`. `std::forward<T>` can restore the original category because of the `T` deduced here.
</details>

!!! question "Question 3"
    Is `const std::string& r = std::string("a") + "b";` safe? What about `const char* p = (std::string("a") + "b").c_str();`?

<details markdown="1">
<summary>Answer</summary>

The first is safe. `operator+` returns a `std::string` prvalue; binding it to `const std::string&` creates a temporary and extends its lifetime to the end of `r`'s scope.

The second dangles. The temporary `std::string` is used to call `c_str()`, which is a function call returning a pointer; no reference binds directly to the temporary, so its lifetime isn't extended. The temporary is destroyed at the end of the full-expression, `p` points to a freed buffer, and reading through `p` afterwards is undefined behavior.
</details>
