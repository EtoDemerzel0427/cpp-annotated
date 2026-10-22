---
title: Names (id-expressions)
summary: "When a name is used as an expression: how its type and value category are determined, when it is rewritten to (*this).m, when it is implicitly moved, and the rules for qualified names, pack indexing and pseudo-destructors."
updated: 2026-10-19
---

!!! tldr
    - Writing a member name `m` in a member function rewrites it to `(*this).m`, after which its type follows the member access rules, so `m` is const in a `const` member function.
    - A non-static member name can do only three things without an object: take part in a member access, form a pointer to member, and (for data members) appear in unevaluated operands such as `sizeof`.
    - A named variable is an lvalue, rvalue reference variables included; only as the operand of `return`, `co_return` or `throw`, and when the conditions are met, is it an xvalue and thus implicitly moved.
    - In a non-`mutable` lambda, names captured by copy are const; a non-type template parameter of class type is a const lvalue, while one of scalar type is a prvalue whose address can't be taken.
    - C++26's `ts...[I]` takes the I-th element of a pack; an out-of-range or negative index is ill-formed.

An **id-expression** is a name used as an expression: `x`, `N::x`, `operator+`, `~T`, `f<int>`, and C++26's `ts...[0]`. Name lookup ([[basic.lookup]]) determines which entity the name denotes; this subclause determines what comes next: what type the expression has, which value category ([[basic.lval]]), and where it can be used.

## Member names and the implicit this [expr.prim.id.general]

```cpp run ok
struct Base  { int bm; };
struct Other { int om; };

struct Der : Base {
  int dm;
  void h() const {
    (void)dm;                 // (*this).dm, a const int lvalue
    (void)bm;                 // (*this).bm, Base is a base class
    (void)Base::bm;           // (*this).Base::bm
    (void)sizeof(Other::om);  // not rewritten: see ¶4.3 below
  }
};

int main() { }
```

You can write plain `dm` in a member function because the compiler rewrites it to `(*this).dm`.

¶2 Let an id-expression `E` denote a non-static member (data member or member function) of some class `C`, and let the current class ([[g:current-class]], the innermost class containing that point) at the point of `E` be `X`. If all four of the following hold, `E` is transformed into a class member access with `(*this)` as the object:

- (2.1) `E` is potentially evaluated ([[g:potentially-evaluated]], roughly: not inside an unevaluated operand such as `sizeof` or `decltype`), or `C` is `X` or a base class of `X`;
- (2.2) `E` is not the name in a member access `a.E` or `p->E`;
- (2.3) `E` is not the operand of a reflection expression `^^E` {{c++26}};
- (2.4) if `E` is a qualified name, it is not the unparenthesized operand of unary `&`.

After the rewrite, everything is handled as a member access ([[expr.ref]]). In a `const` member function `*this` is const, so `m` is a const lvalue.

(2.1) distinguishes two cases. In the example above, `sizeof(Other::om)` is unevaluated and `Other` is not a base of `Der`, so there is no rewrite, and it is valid by ¶4.3 below. If it were changed to the potentially-evaluated `(void)Other::om;`, it would be rewritten to `(*this).Other::om`, and since `Other` is not a base of `Der`, that is ill-formed (Note 2).

(2.4) applies only to qualified names. `&X::m` forms a pointer to member ([[expr.unary.op]]) and must not be rewritten; `&(X::m)` has parentheses and is rewritten as usual to `&(*this).X::m`, giving an ordinary pointer. This is one of the cases where parentheses change meaning ([[expr.prim.paren]]).

No rewrite happens in a template definition ([[temp.dep.type]]), because whether it is needed may depend on a dependent base class, which isn't known until instantiation.

Note 2 also points out that in a static member function or an explicit object member function (deducing this), the rewritten member access is ill-formed because there is no `this` there ([[expr.prim.this#4]]). In an explicit object member function you must write `self.m`.

```cpp error
struct Other { int om; };
struct Der {
  int dm;
  void h() { (void)Other::om; }          // error: Other is not a base class
  void k(this Der& self) { (void)dm; }   // error: no implicit this
};
```

The last sentence of ¶2 is an extra C++26 rule: if the rewrite happens in a precondition of a constructor of `X` or a postcondition of a destructor of `X`, the expression is ill-formed {{c++26}}. When a precondition is checked, the members have not been initialized yet; when a postcondition is checked, they have already been destroyed. The unevaluated `sizeof(b)` and the non-reading `&this->b` can still be used.

!!! lawyer "`sizeof(m)` in a static member function"
    Write `sizeof(m)` in a static member function of class `X`, where `m` is a non-static data member of `X`. Under the current wording, the second half of (2.1), "`C` is `X`", holds, so `m` is rewritten to `(*this).m`, which is ill-formed in a static member function. The C++11 wording rewrote only where `this` could be used, so under those rules it was valid. Clang 23 accepts `sizeof(m)` in a function body but rejects it in a declaration, for example in the trailing return type `-> decltype(sizeof(m))`. The portable way is `sizeof(std::declval<X&>().m)`, or simply write the type.

### Where non-static member names can be used

¶4 An id-expression (or splice-expression) that denotes a non-static data member or implicit object member function can only be used:

- (4.1) as part of a class member access (including the result of the ¶2 rewrite) in which the object expression has the member's class or a class derived from it;
- (4.2) to form a pointer to member (`&C::m`);
- (4.3) if it denotes a data member, in an unevaluated operand ([[g:unevaluated-operand]], the operand of `sizeof`, `decltype`, `noexcept` etc.).

<div class="compare" markdown="1">

```cpp ok
struct S { int m; void mf() {} };

int i = sizeof(S::m);       // (4.3)
int j = sizeof(S::m + 42);  // (4.3)
int S::* pm = &S::m;        // (4.2)
void (S::* pmf)() = &S::mf; // (4.2)
```

```cpp error
struct S { int m; void mf() {} };

int a = S::m;           // error: no object
auto b = S::mf;         // error
auto c = sizeof(S::mf); // error: member function
```

</div>

(4.3) was added in C++11; before that you had to write `sizeof(((S*)0)->m)`. It is open only to data members: a member function name without an object doesn't even have a type that could be described.

¶5 {{c++26}} A splice-expression that designates a direct base class relationship can only be the second operand of a member access (`obj.[: base :]`), used to obtain the base class subobject; see [[expr.prim.splice]].

### Overload sets and unsatisfied constraints

¶6 If the name denotes an overload set, overload resolution ([[over.match]]; [[over.over]] when taking the address) selects a unique function. Note 4 draws the consequence: a function whose trailing *requires-clause* is not satisfied is never selected, so it can't be referred to at all, not even in an unevaluated operand like `decltype`.

```cpp error
template<typename T> struct A {
  static void f(int) requires false;
};

void g() {
  A<int>::f(0);                        // error: can't be called
  void (*p1)(int) = A<int>::f;         // error: can't take its address
  decltype(A<int>::f)* p2 = nullptr;   // error: also requires the constraints to be satisfied
}
```

This lets constrained member functions stay safely in class templates: when the constraints aren't satisfied, instantiating the class template is not an error; the function is simply invisible to overload resolution ([[temp.constr]]).

### Members of anonymous unions

¶3 A member name of an anonymous union ([[class.union.anon]]) is interpreted as a member access into that unnamed object. An anonymous union in a class is an unnamed non-static data member, so `o.x` is interpreted as `o.u.x` (with `u` standing for that unnamed member). An anonymous union at namespace or block scope is an unnamed variable, so `N::x` is interpreted as `N::u.x`. Note 3 points out that in the latter case `x` no longer counts as a non-static data member, so it can be used like an ordinary variable, not subject to ¶4.

```cpp run ok
namespace N { static union { int x; float f; }; }  // at namespace scope it must be static

struct O {
  union { int a; char c; };   // a and c are variant members of O
};

int main() {
  N::x = 1;    // N::<unnamed variable>.x
  O o;
  o.a = 2;     // o.<unnamed member>.a
  return N::x + o.a - 3;
}
```

## The type of an unqualified name [expr.prim.id.unqual]

¶1 An *unqualified-id* is an identifier, an operator function name like `operator+`, a conversion function name `operator T`, a literal operator name `operator""_x`, a destructor name `~T`, or a *template-id*. An identifier is an id-expression only if it has been declared (or is being declared as a declarator); ADL is the exception: the `f` in `f(x)` may be found by no ordinary lookup at all ([[basic.lookup.argdep]]).

¶3 The result is the entity found by name lookup ([[basic.lookup.unqual]]). Its type is determined by checking the table below in order; the first case that applies wins:

| Paragraph | Case | Type of the expression |
|---|---|---|
| ¶4 | Naming a local entity captured by copy in a lambda | The type of the corresponding closure member, const if not `mutable` |
| ¶5 | A coroutine parameter | The type of the copy in the coroutine frame; the result is that copy too |
| ¶6 {{c++26}} | A postcondition's result binding `post(r: ...)` | `const T` |
| ¶7 {{c++26}} | Naming, in a contract predicate, a variable declared outside the predicate | `const T` |
| ¶9 | A template parameter object of class type | `const T` |
| ¶10 | Everything else | The type of the entity |

The note in ¶11 reminds that the resulting type is further adjusted by [[expr.type]]: a reference type loses the reference, and a prvalue of non-class type loses its cv-qualifiers.

### Names captured by copy in a lambda

```cpp
void f() {
  int x = 0;
  auto a = [x] { decltype((x)) r = x; };          // const int&
  auto b = [x] mutable { decltype((x)) r = x; };  // int&
  auto c = [&x] { decltype((x)) r = x; };         // int&
}
```

When a lambda body uses an `x` captured by copy, what it actually accesses is a data member of the closure object ([[expr.prim.lambda.capture#11]]). The call operator of a non-`mutable` lambda is a const member function, so the member access is const and `x` can't be modified.

But that rewrite only applies to odr-uses, i.e. uses that really need to read or write the object. The operand of `decltype((x))` is unevaluated and doesn't trigger the rewrite. ¶4 fills that gap so that `decltype((x))` also gives the actual type of `x` inside the lambda. Its four conditions are:

- (4.1) the name appears at some point P within a lambda expression;
- (4.2) the entity is a local entity ([[basic.pre]]) or a variable declared by an init-capture;
- (4.3) naming the entity from within the compound statement of the innermost lambda enclosing P would refer to an entity captured by copy in some intervening lambda;
- (4.4) P is in the function parameter scope, but not in the parameter-declaration-clause, of the innermost such lambda `E`, i.e. in its trailing return type, `noexcept` specifier or body.

When these hold, the type of the expression is the type of a class member access to that capture member through the object parameter of `E`'s call operator.

```cpp run
#include <type_traits>

void f() {
  float x, &r = x;

  [=]() -> decltype((x)) {     // returns const float&
    decltype(x) y1;            // float: without parentheses, the declared type
    decltype((x)) y2 = y1;     // const float&
    decltype(r) r1 = y1;       // float&: declared type
    decltype((r)) r2 = y2;     // const float&: what is captured is the referenced float
    static_assert(std::is_same_v<decltype(y2), const float&>);
    static_assert(std::is_same_v<decltype(r2), const float&>);
    (void)r1;
    return y2;
  };

  [=](decltype((x)) y) {       // the parameter list fails (4.4): float&
    static_assert(std::is_same_v<decltype(y), float&>);
  };

  [=] {
    [](decltype((x)) y) { };   // standard: const float&; Clang 23: float&
  };
}

int main() { }
```

The last example tests your understanding of (4.4). P is in the parameter list of the inner lambda, but (4.4) talks about the innermost such lambda, i.e. the outer `[=]` that captured `x` by copy. P is in the body of the outer lambda, not in its parameter list, so the condition holds and the type is `const float&`. That is how the standard's example is annotated.

This code block has no verdict mark because Clang 23 gives `float&` for the nested case, disagreeing with the standard; the other cases agree with the standard. If you add `static_assert(std::is_same_v<decltype(y), const float&>)` to the last lambda, Clang reports an assertion failure.

The parameter list is excluded because parameter types determine the call operator's signature, and the signature should depend only on externally visible information. Besides, with implicit captures you can't know which variables are captured until you have seen the whole body.

### Coroutine parameters

¶5 When a coroutine starts executing, its parameters are copied or moved into the coroutine frame ([[dcl.fct.def.coroutine]]), and from then on a parameter name in the coroutine body refers to that copy. A parameter taken by reference only has the reference itself copied, so it may dangle after the first suspension.

### Template parameter objects

¶9 A non-type template parameter of class type names a **template parameter object** ([[g:template-parameter-object|template parameter object]], [[temp.param]]): a const object with static storage duration, shared by all arguments with the same value across the program. So the expression's type is `const T`, it is an lvalue by ¶12, and its address can be taken. A non-type template parameter `N` of scalar type falls into the "otherwise" case of ¶12: it is a prvalue, and `&N` is ill-formed.

```cpp run ok
#include <type_traits>

struct P { int x; };

template<P p> constexpr const P* addr() {
  static_assert(std::is_same_v<decltype((p)), const P&>);  // const lvalue
  return &p;                                               // OK: has an address
}
template<int N> void nn() {
  static_assert(std::is_same_v<decltype((N)), int>);       // prvalue
}

static_assert(addr<P{1}>() == addr<P{1}>());   // same value, same object

int main() { nn<1>(); }
```

### Names in contract predicates {{c++26}}

A contract assertion should only observe program state. So when a predicate names an outside variable, its type is always const, but this const is shallow: it applies only to the name itself.

¶6 A postcondition's result binding ([[dcl.contract.res]], the `r` in `post(r: r > 0)`): if the function returns `T&`, `r` has type `const T`; otherwise `const U` (where `U` is the return type).

¶7 In the predicate of a contract assertion `C`, naming the following entities gives type `const T`: a variable of object type declared outside `C` (of type `T`), a variable of reference type or a template parameter declared outside `C` (of type reference to `T`), and a structured binding whose corresponding variable is declared outside `C`.

¶8 is a long example; the key points are:

- `pre(++i)`, `pre(++r)` and `pre(x.m())` are ill-formed because `i`, `r` and `x` are treated as const;
- `pre(++(*p))` and `pre(px->m())` are well-formed: the const applies only to `p` itself, not to the object it points to;
- with template parameters `template<int N, int& R>`, `pre(++N)` is ill-formed because `N` is a prvalue, and `pre(++R)` is ill-formed because `R` is treated as const;
- `[=] mutable { ++p; }` in a predicate is well-formed, since `p` in the lambda body refers to the closure's own member; but an `i` captured by reference still refers, inside the lambda, to the outer entity that is treated as const, so `++i` is ill-formed.

As of this writing, Clang 23 doesn't support contracts yet, so these rules couldn't be verified locally.

## Value category [expr.prim.id.unqual]

¶12 The value category of an unqualified name:

- an xvalue if it is move-eligible (see the next section);
- an lvalue if the entity is a function, variable, structured binding, result binding, data member or template parameter object;
- a prvalue otherwise (enumerators, non-type template parameters of scalar type, etc.).

If the name denotes a bit-field, the expression is a bit-field too.

Variables include variables of reference type. After `int&& rr = 1;`, `rr` is an lvalue of type `int`. The common saying "a named rvalue reference is an lvalue" is this rule.

## Implicit move [expr.prim.id.unqual]

<div class="compare" markdown="1">

```cpp ok
#include <memory>
using U = std::unique_ptr<int>;

U f1(U p)   { return p; }
U f2()      { U p; return (p); }
U f3(U&& p) { return p; }
U&& f4(U&& p) { return p; }
U f5() { U p; { { return p; } } }
void t1()   { U p; throw p; }
```

```cpp error
#include <memory>
using U = std::unique_ptr<int>;

void t2() {
  U p;
  try { throw p; } catch (...) {}
}
U f6() { static U p; return p; }
U f7() {
  U p;
  return [&] { return p; }();
}
struct H { U m; U get() { return m; } };
```

</div>

Every `p` on the left is moved; every case on the right tries to copy a `unique_ptr` and is an error. The difference is whether the name is move-eligible.

¶15 An **implicitly movable entity** ([[g:implicitly-movable-entity|implicitly movable entity]]) is a variable with automatic storage duration that is either a non-volatile object or an rvalue reference to a non-volatile object type. An id-expression is [[g:move-eligible|**move-eligible**]] if and only if:

- (15.1) it names an implicitly movable entity;
- (15.2) it is the (possibly parenthesized) operand of a `return` or `co_return` statement or a `throw` expression;
- (15.3) every scope between the entity's declaration and the innermost scope enclosing the expression is a block scope; for `throw`, those block scopes also must not be the scope of a `try` block.

A move-eligible name is an xvalue (¶12), so overload resolution naturally picks the move constructor. The four examples on the right are, respectively: a `try` block in between, static storage duration, a lambda's scope in between, and `m` being a data member rather than a variable.

!!! pitfall "An incompatible change in C++23"
    Since C++23, `return` of an rvalue reference variable yields an xvalue, and the following previously valid code becomes ill-formed:
    ```cpp
    std::string& bad(std::string&& s) {
      return s;   // C++20 OK; C++23 error: an xvalue can't bind to a non-const lvalue reference
    }
    ```
    Clang 23 accepts it under `-std=c++20` and rejects it under `-std=c++23`.

!!! pitfall "Only the name itself counts"
    `return s.member;`, `return *p;`, `return std::get<0>(t);` and `return cond ? a : b;` are not move-eligible names and copy. A structured binding is not a variable, so `return b;` (with `auto [b] = ...`) doesn't move implicitly either.

<details class="fine" markdown="1"><summary>Parameters and temporaries in contracts (¶13–14)</summary>

¶13 [[class.temporary]] allows implementations to pass trivially copyable parameters through temporary objects so they can go in registers. In that case, if the predicate of a function contract assertion names a parameter: when the precondition is evaluated before the parameter object is initialized, the name refers to the most recently initialized such temporary; in a postcondition, it is unspecified whether the name refers to the temporary or the parameter object, but the choice is consistent within one evaluation.

¶14 The same goes for the result binding in a postcondition: if it is evaluated before the result object is initialized, it refers to the most recently initialized temporary.

These two paragraphs acknowledge how calling conventions actually work; as long as you don't rely on object address identity, you can't tell the difference.

</details>

## Qualified names [expr.prim.id.qual]

A *qualified-id* consists of a *nested-name-specifier* (the part before `::`) and an *unqualified-id*. A nested-name-specifier can be `::`, a type name, a namespace name, `decltype(...)`, or C++26's splice specifier `[: r :]`.

### Out-of-class definitions only in an enclosing scope

¶3 A nested-name-specifier that appears in the name being declared is called **declarative** ([[g:declarative-nested-name-specifier|declarative]]), as in an out-of-class definition `void N::f() {}` or a class head `struct N::S { ... };`. It has two restrictions: it can't contain `decltype(...)` or a splice; and the declaration using it must be either a friend declaration or inhabit a scope that contains the entity being redeclared.

```cpp error
namespace N { namespace M { void g(); } void h(); }

void N::h() {}                      // OK: the global scope contains N::h
namespace X { void N::M::g() {} }   // error: X doesn't contain N::M::g
```

### Value category

¶9 A qualified name is an lvalue in the following cases, and a prvalue otherwise:

- (9.1) a non-member function or a static member function;
- (9.2) a non-static member function, when the qualified name is the operand of unary `&`;
- (9.3)–(9.5) a variable, a structured binding, a data member.

(9.2) means `X::mf` is an lvalue only in `&X::mf`, so that `&` can apply to it. C++ has no standalone lvalue of non-static member function type.

¶6–¶8 say the result is the entity found by qualified name lookup ([[basic.lookup.qual]]) and the type is its type; the const rule in contract predicates is the same as [[expr.prim.id.unqual#7]].

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 The component names of a *qualified-id* are those of its nested-name-specifier and *unqualified-id*. **Component name** ([[g:component-name|component name]]) and **terminal name** ([[g:terminal-name|terminal name]], the component name that appears lexically last, like `f` in `N::C<int>::f`) are terms introduced when C++23 rewrote name lookup; they are defined in [[expr.prim.id.unqual#2]], and [[basic.lookup.qual]] uses them to say which name is looked up in which scope.

¶2 {{c++26}} A splice specifier not followed by `::` is never treated as part of a nested-name-specifier. The `template` in `template [: r :]<args>::` can be omitted only when preceded by `typename`. So `[:^^TCls:]<3>::type v6 = 6;` is ill-formed: the `<` is treated as less-than.

¶4 says what a nested-name-specifier designates: `::` the global namespace; `decltype(E)::` that type, which must be a class or enumeration; `[: r :]::` the class, enumeration or namespace reflected by `r`. (4.5) handles out-of-class definitions of members of class templates: in `template<class T> void TT<T>::f() {}`, if the argument list is exactly the parameter list of the corresponding template head, it designates the primary template, and the two template heads must be equivalent; otherwise it designates the corresponding partial specialization, and is ill-formed if there is none. (4.6) says a non-declarative nested-name-specifier can't designate a template itself: you can't write `std::vector::size_type`.

¶5 The forms `N::~decltype(x)` and `decltype(x)::~T` are not allowed. `~decltype(x)` can only appear unqualified, as in `p->~decltype(*p)()`.

</details>

## Pack indexing {{c++26}} [expr.prim.pack.index]

```cpp run ok
#include <cstddef>
#include <type_traits>
#include <utility>

template<class... Ts> constexpr auto first(Ts... ts) { return ts...[0]; }

template<std::size_t I, class... Ts>
constexpr decltype(auto) nth(Ts&&... ts) {
  return std::forward<Ts...[I]>(ts...[I]);   // type pack index + expression pack index
}

template<class... Ts> void g(Ts... ts) {
  static_assert(std::is_same_v<decltype(ts...[0]), int>);     // declared type
  static_assert(std::is_same_v<decltype((ts...[0])), int&>);  // lvalue
}

static_assert(first(1, 2.0, 'c') == 1);

int main() {
  g(1, 'x');
  int x = 3;
  static_assert(std::is_same_v<decltype(nth<0>(x, 2)), int&>);
  static_assert(std::is_same_v<decltype(nth<1>(x, 2)), int&&>);
}
```

¶1 The `ts` in `ts...[I]` must be an identifier that denotes a pack: a function parameter pack, a non-type template parameter pack, an init-capture pack or a structured binding pack. Pack indexing for types, `Ts...[I]`, is in [[dcl.type.pack.index]].

¶2 The index must be a converted constant expression ([[expr.const.const]]) of type `std::size_t` whose value V satisfies 0 ≤ V < `sizeof...(ts)`. Converted constant expressions forbid narrowing, so `ts...[-1]` is simply ill-formed; it doesn't wrap around to a huge number.

```cpp error
template<class... Ts> auto bad(Ts... ts)  { return ts...[3]; }
int x = bad(1, 2);                                               // error: out of range

template<class... Ts> auto bad2(Ts... ts) { return ts...[-1]; }  // error: narrowing
```

¶3 A pack index expression itself counts as a pack expansion ([[temp.variadic]]), even though it produces only one element. This is a technical necessity: the `ts` in it counts as already expanded, so an enclosing `...` won't expand it again. On instantiation it is replaced directly by the name of the V-th element ([[temp.variadic#11]]), so its type and value category are exactly those of writing that element directly.

!!! history
    Before C++26, taking the N-th element of a pack required recursive templates or `std::get<N>(std::forward_as_tuple(ts...))`, which was slow to compile and hard to read. Pack indexing was introduced by [[P2662R3]]. It changed the meaning of an old form: in C++23, `template<class... T> void f(T...[1]);` declares an unnamed pack of array parameters; in C++26, `T...[1]` is a pack index ([[diff.cpp23.dcl.dcl#2]]).

## Pseudo-destructors [expr.prim.id.dtor]

```cpp run ok
template<class T> void destroy(T* p) { p->~T(); }

int main() {
  using T = int;
  int i = 0;
  i.~T();             // ends the lifetime of i
  int j = 0;
  j.~decltype(j)();   // the ~decltype(...) form
  int k = 0;
  destroy(&k);        // T is int: a pseudo-destructor call
}
```

Generic code needs to call the destructor of an arbitrary type, and `destroy<int>` must compile too. For that, scalar types also have a callable destructor name.

¶1 The name `~T` denotes the destructor of type `T`. If `T` is a class type, it is a real destructor ([[class.dtor]]); otherwise it names a [[g:pseudo-destructor|**pseudo-destructor**]].

¶2 A pseudo-destructor can only be used for scalar types, and only in the complete call form `obj.~T()` or `p->~T()`. Note 1 points out that such a call ends the object's lifetime ([[basic.life]]). Up to C++17, a pseudo-destructor call did nothing except evaluate the expression on the left; since C++20 it ends the lifetime, so `std::destroy_at` behaves consistently for scalar and class types. Reading `i` afterward reads an object whose lifetime has ended, and the constant evaluator rejects that:

```cpp error
constexpr int g() {
  int i = 1;
  using T = int;
  i.~T();
  return i;   // reads an object whose lifetime has ended
}
constexpr int v = g();   // error: not a constant expression
```

¶3 The standard's example also covers several edge cases:

```cpp ub
struct C { };
void f() {
  C* pc = new C;
  using C2 = C;
  pc->C::~C2();   // OK: destroys *pc, ~C2 refers to C through the alias
  C().C::~C();    // UB: the temporary is destroyed twice
  using T = int;
  0 .T::~T();     // OK: no effect
  ::operator delete(pc);
}
```

`C().C::~C()` explicitly destroys the temporary, and it is destroyed again at the end of the full-expression.

The space in `0 .T::~T()` is essential. Written as `0.T::~T()`, `0.T` is lexed as a single token, which the standard says is a user-defined floating-point literal ([[lex.ext]]) and is ill-formed; Clang 23 reports `invalid suffix 'T' on floating constant`. `i.~int()` is ill-formed too: `~` must be followed by a type name or `decltype`, and `int` is a keyword.

!!! lawyer "`~T()` is not a destructor call"
    Writing `~T();` by itself (with `T` being `int`) applies bitwise complement to the value-initialized `T()`, giving `-1`. [[expr.unary.op]] says that when `~` is followed by a type name, this ambiguity is resolved as the unary operator. Only after `.` or `->` is `~T` a destructor name.

## Implementation view

!!! impl
    In Clang's AST, an implicit member access is a `MemberExpr` whose object is a `CXXThisExpr` marked implicit; `-Xclang -ast-dump` shows the ¶2 rewrite directly. Pack indexing is replaced by the corresponding element on instantiation and produces no runtime code. A pseudo-destructor call usually generates no instructions after optimization, but the constant evaluator and sanitizers use the "lifetime has ended" information to diagnose later reads.

## History

!!! history
    The implicit `this->` for member names has existed since C++98. C++11 allowed non-static data members in unevaluated operands (¶4.3) and introduced lambdas, which created the question of the types of names inside lambdas; C++14's init-captures meant the rule had to cover variables declared by init-captures. C++20 made non-type template parameters of class type name template parameter objects, made pseudo-destructors end lifetimes, and through [[P1825R0]] extended implicit move to rvalue reference variables, still using the two-phase overload resolution of trying as an rvalue first and falling back to an lvalue. C++23 settled, through [[P2036R3]], the type of names captured by copy in a lambda's trailing return type, and through [[P2266R3]] simplified implicit move to "a move-eligible name is an xvalue". C++26 added pack indexing, the const rules in contracts, and the reflection-related rules.

## Questions

!!! question "1. What are the types of the three `r`s below?"
    ```cpp
    void f() {
      int x = 0;
      auto a = [x]() mutable { decltype((x)) r = x; };   // #1
      auto b = [&x] { decltype((x)) r = x; };             // #2
      auto c = [y = x] { decltype((y)) r = y; };          // #3
    }
    ```

<details markdown="1">
<summary>Answer</summary>

`#1` is `int&`: the lambda is `mutable`, so the call operator is not const and the closure member doesn't get const.

`#2` is `int&`: ¶4 only deals with capture by copy ((4.3)); with capture by reference, `x` is just the outer variable, and `decltype((x))` gives `int&` by the ordinary rules.

`#3` is `const int&`: (4.2) explicitly includes variables declared by init-captures; `y` is captured by copy and the lambda is not `mutable`.
</details>

!!! question "2. Is the following function well-formed in C++20 and in C++23? What is its return type?"
    ```cpp
    decltype(auto) pass(std::string&& s) { return s; }
    ```

<details markdown="1">
<summary>Answer</summary>

The return type is `std::string&&` in both versions: `decltype(auto)` gives the declared type for an unparenthesized `s`. The difference is whether `s` can initialize that return value.

In C++20, `s` is an lvalue. The two-phase rule of [[P1825R0]] is only used to select a constructor, and this is reference binding, which involves no constructor, so the lvalue can't bind to `std::string&&` and the function is ill-formed.

In C++23, `s` is a move-eligible xvalue, it can bind, and the function is well-formed. Clang 23 behaves accordingly: under `-std=c++20` it reports `rvalue reference to type ... cannot bind to lvalue`, and under `-std=c++23` it compiles.
</details>

!!! question "3. In a member function of class `X`, what are the types of `&X::m` and `&(X::m)`? If `m` is declared in `X`'s base class `B`, what is the type of `&X::m`?"

<details markdown="1">
<summary>Answer</summary>

`&X::m` is not rewritten ((2.4)) and forms the pointer to member `int X::*`; `&(X::m)` has parentheses, so (2.4) doesn't apply and it is rewritten to `&(*this).X::m`, giving `int*`. If `m` is declared in base class `B`, `&X::m` has type `int B::*`: [[expr.unary.op]] says the class of a pointer to member is the class in which the member is declared, not the class written in the qualified name. It converts implicitly to `int X::*`.
</details>
