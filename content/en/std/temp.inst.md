---
title: Implicit instantiation
summary: "When the compiler automatically generates definitions from templates: a class template specialization is instantiated when a complete type is needed, and only its member declarations are generated; member functions, static data members, default arguments and noexcept-specifiers are each instantiated on demand; being needed for constant evaluation or for determining a type also counts; implementations must not instantiate more than needed, and infinite recursive instantiation is undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - A class template specialization is instantiated only when a complete type is needed. Pointers, references, type aliases and non-defining declarations don't trigger it.
    - Instantiating a class generates only the declarations of its members. Member function bodies, initializers of static data members and so on are generated only when actually used, so a class template can have members that are valid only for some arguments.
    - If a static data member isn't used, its initialization and side effects don't happen, which is why self-registration in templates often fails.
    - When constant evaluation or determining an expression's type needs the definition of a function or variable, it is instantiated even if it isn't odr-used.
    - Whether a virtual function is instantiated is unspecified; in practice it almost always is. Infinite recursive instantiation is undefined behavior.

## Only what is used is generated

```cpp run ok
template<class T>
struct C {
  void f() { T x; }   // ill-formed when T is void
  void g() { }
};

C<void> c;            // OK
int main() { c.g(); }
```

The body of `C<void>::f` contains `void x;`, but as long as nobody calls `f`, the program is well-formed. When the compiler instantiates `C<void>` it generates only the declaration of `f`, leaving the body until it is needed. This is the laziness of **implicit instantiation** ([[g:implicit-instantiation]]): the compiler generates a specialization's definition automatically when it is used, and only the parts that are used.

This is why `std::vector<T>::resize(n)` requires `T` to be default-constructible while a non-default-constructible `T` can still use the rest of `vector<T>`. Where in the source an instantiation happens is specified by [[temp.point]]; this subclause specifies whether it happens.

Most rules here start with "unless it is a declared specialization". A **declared specialization** ([[g:declared-specialization]]) is a specialization whose definition comes from elsewhere, for example an explicit specialization written by the programmer, or one specified to be generated elsewhere with `template class X<int>;` ([[temp.spec]]). The compiler shouldn't generate another one itself. The precise definition from ¶1 is in the last section of this page.

## When a class template specialization is instantiated (¶2)

¶2 A class template specialization is implicitly instantiated in two cases: when it is referenced in a context that requires a completely-defined object type, or when the completeness of the class type affects the semantics of the program.

The first is intuitive: defining a variable, `sizeof`, member access, `new`, use as a base class, and pointer arithmetic all need a complete type. The second is subtler; Note 2 gives two examples: the semantics of `delete p` depend on whether the class declares a destructor, and conversion from `D*` to `B*` depends on the inheritance relationship.

```cpp run ok title="needs_complete.cpp"
template<class T> class B { };
template<class T> class D : public B<T> { };

void f(void*);
void f(B<int>*);

void g(D<int>* p, D<char>* pp, D<double>* ppp) {
  f(p);              // instantiates D<int> to know it converts to B<int>*
  B<char>* q = pp;   // instantiates D<char> to know it's a derived-to-base conversion
  delete ppp;        // instantiates D<double>
  (void)q;
}
```

None of the following uses need a complete type, and none instantiate:

<div class="compare" markdown="1">

```cpp run ok
template<class T> struct Bad {
  static_assert(sizeof(T) == 0);
};
Bad<int>* p = nullptr;
void take(Bad<int>&);
using U = Bad<int>;
extern Bad<int> obj;
int main() {}
```

```cpp run error
template<class T> struct Bad {
  static_assert(sizeof(T) == 0);
};
Bad<int>* p = nullptr;
auto n = sizeof(*p);
// error: instantiates Bad<int>,
// static_assert fails
int main() {}
```

</div>

¶2 ends by specifying that if the template selected for the specialization (the primary template or a partial specialization, [[temp.spec.partial.match]]) is declared but not defined at the point of instantiation, the instantiation yields an incomplete type.

```cpp error
template<class T> class X;
X<char> ch;   // error: X<char> is an incomplete type
```

Traits like `std::tuple_size` rely on exactly this: the primary template isn't defined, so unspecialized arguments give an incomplete type, which SFINAE can detect.

## What is generated when a class is instantiated (¶3)

¶3 The implicit instantiation of a class template specialization:

- ¶3.1 instantiates only the declarations, not the definitions, of non-deleted member functions, member classes, scoped member enumerations, static data members, member templates and friends;
- ¶3.2 instantiates the definitions of deleted member functions, unscoped member enumerations and member anonymous unions.

The definitions in the second group can't be deferred: the definition of a deleted function is `= delete`; the enumerators of an unscoped enumeration and the members of an anonymous union become members of the enclosing class, and without instantiating the definitions it isn't known what names the class has.

So the following explicit specialization is a redefinition:

```cpp error
template<class T>
struct C {
  void g() = delete;
};
C<int> c;                        // g's definition = delete is instantiated with the class
template<> void C<int>::g() { }  // error: redefinition of C<int>::g
```

!!! impl "Clang deviates"
    Clang 23 accepts this code and reports no redefinition. Per ¶3.2 it is ill-formed.

### A declaration corresponding to a definition counts as a definition

The second half of ¶3 says that, when determining whether a redeclaration is valid under [[basic.def.odr]] and [[class.mem]], an instantiated declaration that corresponds to a definition in the template is considered a definition. Laziness only defers generating function bodies; it doesn't mean there is no definition.

The most common consequence involves friend functions defined in class templates:

```cpp error
template<typename T> struct Friendly {
  template<typename U> friend int f(U) { return sizeof(T); }
};
Friendly<char> fc;
Friendly<float> ff;   // error: second definition of f(U)
```

Every `Friendly<X>` declares the same function template `f` in the enclosing namespace, and each time it counts as a definition, so two instantiations mean two definitions. Make the friend's signature depend on `T`, for example `friend int f(Friendly<T>)`, and each specialization defines a different function.

The first half of Example 4 applies the same principle to partial specializations of a member class template:

```cpp error
template<class T, class U>
struct Outer {
  template<class X, class Y> struct Inner;
  template<class Y> struct Inner<T, Y>;       // #1a
  template<class Y> struct Inner<T, Y> { };   // #1b: OK, valid redeclaration of #1a
  template<class Y> struct Inner<U, Y> { };   // #2
};
Outer<int, int> outer;   // error at #2
```

With `T` and `U` both `int`, #2 and #1b become two definitions of the same partial specialization `Inner<int, Y>`.

## When members, functions and variables are instantiated (¶4–¶7)

¶4 A member of a templated class is implicitly instantiated only when it is referenced in a context that requires the member definition to exist, or when the existence of the definition affects the semantics of the program. In particular, the initialization (and any associated side effects) of a static data member does not occur unless the static data member is itself used in a way that requires its definition to exist.

This sentence is why self-registration in templates fails:

```cpp run ok title="autoreg.cpp"
#include <cstdio>
int reg(const char* n) { std::printf("registered %s\n", n); return 0; }

template<class T> struct AutoReg {
  static inline int token = reg(T::name);
};

struct Foo : AutoReg<Foo> {
  static constexpr const char* name = "Foo";
};
struct Bar : AutoReg<Bar> {
  static constexpr const char* name = "Bar";
  static constexpr auto* force = &token;   // uses token
};

int main() { std::puts("main"); }
// Output:
// registered Bar
// main
```

`AutoReg<Foo>` is instantiated as a base class, but that only generates the declaration of `token`. Nobody uses `token`, so its definition and initializer are never instantiated and `reg` isn't called. `Bar` takes `&token`, forcing the instantiation. In a non-template class, `static inline int token = reg(...)` is always initialized; this is why registration stops working when a non-template version is rewritten as CRTP.

¶5 Function template specializations work the same way: they are instantiated when the function definition is required to exist or its existence affects the semantics. Functions whose declarations are instantiated from in-class friend function definitions too. Requiring the function definition to exist is basically **odr-use** ([[basic.def.odr]]: uses such as calls or taking the address, which need the entity to have a definition). Appearing only in an unevaluated operand like `sizeof` or `decltype` usually needs only a declaration.

Example 5 under ¶6 puts these rules together:

```cpp ok
template<class T> struct Z {
  void f();
  void g();
};

void h() {
  Z<int> a;      // instantiates class Z<int>
  Z<char>* p;    // doesn't instantiate Z<char>
  Z<double>* q;  // doesn't instantiate Z<double>

  a.f();         // instantiates Z<int>::f()
  p->g();        // instantiates class Z<char> and Z<char>::g()
}
```

`Z<double>`, `Z<int>::g()` and `Z<char>::f()` are never instantiated. (`f` and `g` have no definitions, so linking would fail, but that has nothing to do with instantiation.)

¶7 Variable template specializations follow the same rules as functions. A default template argument of a variable template is instantiated only when its value is needed.

## Constant evaluation and type deduction need definitions too (¶8–¶9)

### Needed for constant evaluation (¶8)

```cpp error title="needed_for_ce.cpp"
template<typename T> constexpr int f() { return T::value; }

template<bool B, typename T> void g(decltype(B ? f<T>() : 0));
template<bool B, typename T> void g(...);
template<bool B, typename T> void h(decltype(int{B ? f<T>() : 0}));
template<bool B, typename T> void h(...);

void x() {
  g<false, int>(0);   // OK
  h<false, int>(0);   // error: instantiates f<int>, int::value is ill-formed
}
```

¶8 If a variable or function is **needed for constant evaluation** by some expression ([[expr.const.defns]]), the existence of its definition is considered to affect the semantics of the program, even if the expression doesn't require constant evaluation, or constant evaluation wouldn't actually use the definition.

The parameter type of `h` contains a list-initialization `int{…}`. Deciding whether it narrows ([[dcl.init.list]]) depends on whether the source expression is a constant expression and what its value is, so `B ? f<T>() : 0` becomes a potentially constant evaluated expression, and `f<int>` must be instantiated. That holds even though `B` is `false`, and even though `int` to `int` can't possibly narrow. The error in the body of `f<int>` isn't in the immediate context of deduction ([[temp.deduct]]), so it is a hard error and doesn't make SFINAE discard this overload.

The `decltype` in `g` only cares about the type, and the type of `f<T>()` is known to be `int` from the declaration, so the definition needn't be instantiated.

In C++17 and earlier, when constexpr functions were instantiated wasn't clearly specified, and compilers behaved differently. C++20's [[P0859R0]] introduced the notions of potentially constant evaluated and needed for constant evaluation, giving ¶8.

### Needed to determine a type (¶9)

```cpp
template<typename T> struct X {
  static inline int arr[] = {1, 2, T::error};
};
decltype(+X<int>::arr) r;    // error: definition instantiated to complete the type of arr

template<typename T> struct X2 {
  static inline int arr[3] = {1, 2, T::error};
};
decltype(+X2<int>::arr) r2;  // OK: the type is already complete, arr isn't odr-used
```

¶9 If instantiation is needed to determine the type of some expression in the program, the existence of the definition also affects the semantics, even if the variable or function isn't odr-used. `X<int>::arr` is declared with type `int[]`, and the number of elements has to come from the initializer; the type of `X2<int>::arr` is already complete. Functions with an `auto` return type are the same: to know `decltype(f<int>())`, the body of `f<int>` must be instantiated.

!!! impl "Clang deviates"
    Clang 23 accepts `decltype(+X<int>::arr) r;` without instantiating the initializer of `arr`. Per ¶9 this is ill-formed.

## When instantiation may be skipped (¶10–¶11)

```cpp ok
template <class T> struct S {
  operator int();
};

void f(int);
void f(S<int>&);
void f(S<float>);

void g(S<int>& sr) {
  f(sr);   // instantiation of S<int> and S<float> allowed but not required
}
```

¶10 If the function selected by overload resolution can be determined without instantiating a class template definition, whether that instantiation actually takes place is {{unspec}}. `f(S<int>&)` is an exact match, and reference binding doesn't need to look inside `S<int>`; `f(S<float>)` would require instantiating `S<float>` to know whether there's a conversion. The compiler may skip it or instantiate as usual. So if instantiating `S<float>` were itself an error, this code would compile on some implementations and not on others.

¶11 When a function template specialization is used in a way that involves overload resolution, its declaration is implicitly instantiated ([[temp.over]]). The body isn't instantiated at that point, unless the specialization is ultimately selected and odr-used.

## Implementations must not instantiate more than needed (¶12)

¶12 An implementation shall not implicitly instantiate a function template, a variable template, a member template, a non-virtual member function, a member class or static data member of a templated class, or a substatement of a constexpr if statement ([[stmt.if]]) that isn't taken, unless such instantiation is required. Note 4 adds that when the function containing a generic lambda is instantiated, the substatements of constexpr if statements inside it aren't instantiated as long as the lambda's function call operator template isn't instantiated.

This is a guarantee to programmers: a class template can contain non-virtual members that are valid only for some `T`, without worrying that the compiler will generate them all.

Virtual functions are the exception: whether a virtual member function that wouldn't otherwise be instantiated is instantiated is unspecified. Implementations need to put the addresses of virtual functions into the vtable, so they usually instantiate all virtual functions when the class is instantiated:

<div class="compare" markdown="1">

```cpp run ok
template<class T> struct W {
  void nv() { T::nope(); }
};
W<int> w;   // OK: nv is never instantiated
int main() {}
```

```cpp unspecified
template<class T> struct W {
  virtual void v() { T::nope(); }
};
W<int> w;
// unspecified; Clang 23 instantiates v
// and reports an error
```

</div>

¶12 also covers default arguments and default member initializers: using a template specialization in one doesn't by itself cause the template to be instantiated, unless instantiation is needed to determine their own correctness; the specializations in them are instantiated only when a default argument is actually used in a function call, or a default member initializer is actually used in a constructor definition or aggregate initialization.

```cpp
template<class T> struct S {
  int m = T::value;     // default member initializer
  S(int) : m(0) {}      // doesn't use it
  S() {}                // uses it
};
S<int> a(1);   // OK: the initializer is never instantiated
S<int> b;      // error: S() uses the default member initializer of m
```

## Default arguments and other separately instantiated constructs (¶13–¶16)

The default arguments, noexcept-specifiers and function contract specifiers of a function template are, like its body, **separately instantiated constructs** ([[temp.decls.general]]): each is instantiated only when needed.

### Default arguments (¶14–¶15)

```cpp error
template<class T> void f(T x, T y = ydef(T()), T z = zdef(T()));

class A { };
A zdef(A);

void g(A a, A b, A c) {
  f(a, b, c);   // no default argument is instantiated
  f(a, b);      // instantiates z's default argument: OK
  f(a);         // error: instantiates y's default argument, ydef not declared
}
```

¶14 If a call to a templated function uses a default argument, the compiler instantiates that default argument: dependent names in it are looked up, semantic constraints are checked, and templates used in it are instantiated, as if it were an initializer in the same scope, with the same template parameters and the same access. This process is called **default argument instantiation** ([[g:default-argument-instantiation]]). The one difference is that the scope in which the closure types of lambdas in it are declared (and hence their associated namespaces) is still determined by where the default argument is defined.

¶15 Each default argument is instantiated independently (Note 6). `ydef` is never declared, but as long as nobody uses `y`'s default argument, the program is well-formed. `ydef(T())` is a dependent call, so ADL is also done at instantiation ([[temp.dep.res]]): if `A ydef(A)` were declared before the call, `f(a)` would be valid.

### noexcept and contract specifiers (¶16)

¶16 The other separately instantiated constructs are also instantiated only when needed; the typical ones are noexcept-specifiers ([[except.spec]]) and {{c++26}} function contract specifiers ([[dcl.contract.func]]). Lookup and checking during instantiation behave as if the specialization's declaration were instantiated at that point.

Deferring instantiation of noexcept-specifiers is useful. If `noexcept(noexcept(T(std::declval<T&&>())))` on a member function of a class template were instantiated together with the class, it could fail prematurely while `T` is still incomplete. Instantiating it only when we really need to know whether it is noexcept (when it is called, queried by the `noexcept` operator, or checked for virtual overriding) makes uses like `std::vector<Incomplete>` possible.

### Local classes and non-generic lambdas are instantiated with the enclosing function (¶13)

¶13 If a templated function `F` is a member of a local class (¶13.1) or the function call operator of a non-generic lambda (¶13.2), its separately instantiated constructs are instantiated when the declaration of `F` is instantiated. In other words, as soon as a specialization of the enclosing function template is instantiated, the member function bodies of local classes and the bodies of non-generic lambdas are instantiated too, even if they're never called:

<div class="compare" markdown="1">

```cpp error
template<class T> void outer() {
  struct Local {
    void f() { T::nope(); }
  };
}
template void outer<int>();
// error
```

```cpp error
template<class T> void outer() {
  auto l = [] { T::nope(); };
  (void)l;
}
template void outer<int>();
// error: l is never called
```

</div>

Local classes and lambdas can't be referenced outside the enclosing function; if they aren't instantiated now, there will never be template arguments to trigger it. Note 5 explains that, for instantiation, they are still constructs separate from the enclosing function; only the timing is tied together. The call operator of a generic lambda is a member template whose body depends on its own template parameters, so it is still instantiated only when called.

## Recursive instantiation (¶18)

```cpp error
template<class T> class X {
  X<T>* p;    // OK: a pointer doesn't need a complete type
  X<T*> a;    // X<T> needs X<T*>, X<T*> needs X<T**>, ...
};
X<int> x;
```

¶18 There is an implementation-defined limit on the total depth of recursive instantiations, which could involve more than one template. The result of an infinite recursion in instantiation is {{ub}}. Annex [[implimits]] recommends a limit of at least 1024.

Clang 23 reports recursive template instantiation exceeded maximum depth of 1024; the limit can be adjusted with `-ftemplate-depth=N`, and GCC has an option of the same name. The standard makes this UB rather than ill-formed because whether a recursion terminates is undecidable in general. In practice compilers report an error when they reach the limit.

Deep recursion commonly comes from recursively implemented tuples or type lists, constexpr recursive functions with one specialization per level, and partial specializations with wrong termination conditions. C++17 fold expressions and C++26 pack indexing `Ts...[I]` and expansion statements can often eliminate such recursion.

## Constraints aren't instantiated with the specialization (¶19)

¶19 The *type-constraint*s and *requires-clause* of a template specialization or member function are not instantiated along with the specialization or function itself, and the same holds for member functions of local classes. Atomic constraints are substituted per [[temp.constr.decl]] and [[temp.constr.atomic]] only when checking whether constraints are satisfied or comparing two declarations. Note 8 points out that satisfaction is checked during template argument deduction and overload resolution.

```cpp error
template<typename T> concept C = sizeof(T) > 2;
template<typename T> concept D = C<T> && sizeof(T) > 4;

template<typename T> struct S {
  S() requires C<T> { }   // #1
  S() requires D<T> { }   // #2
};

S<char[8]> s2;   // OK: both satisfied, #2 is more constrained
S<char> s1;      // error: no matching constructor
```

When `S<char>` is instantiated, both constructors are members of it; their constraints just aren't satisfied. They still suppress the declaration of the implicit default constructor ([[class.default.ctor]]), so `s1` has no viable constructor.

Example 12 is an IFNDR (ill-formed, no diagnostic required) case involving constraints: a member class template with `requires false` has no valid specialization, so per [[temp.res.general#6]] the program is IFNDR.

## Declared specializations (¶1)

¶1 A specialization `E` is a declared specialization if there is a reachable explicit instantiation definition or explicit specialization declaration for `E`; or if there is a reachable explicit instantiation declaration (`extern template`) for `E` and `E` is not one of the following:

| Exception | Why implicit instantiation is still needed |
|---|---|
| ¶1.1 an inline function | for inline expansion (¶5, Note 3) |
| ¶1.2 an entity whose type is deduced from its initializer or return value (`auto`) | the type isn't known without instantiating |
| ¶1.3 a potentially-constant variable ([[expr.const.init]]) | constant expressions need its value |
| ¶1.4 a specialization of a templated class | the class must be complete to be used; `extern template` only prevents generating member definitions |

Note 3 under ¶5 explains the first item: with `extern template` on an inline function, it is still implicitly instantiated when odr-used and its body can be inlined; this translation unit just doesn't emit an out-of-line copy. See the multi-translation-unit example in [[temp.explicit]] for the effect.

Note 1 reminds us that an implicit instantiation in a translation unit that imports a module can't use names with internal linkage from the imported translation units ([[basic.link]]).

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶17 is a note pointing out that the point of instantiation is specified by [[temp.point]].

</details>

## Common misconceptions

!!! pitfall "If it compiles, all members are valid"
    Member functions are instantiated only when used. If your tests only use `push_back`, an error in `resize` won't be found. When writing a library, use an explicit instantiation definition `template class MyVec<SomeType>;` in tests to force instantiation of all defined members ([[temp.explicit#9]]).

!!! pitfall "`decltype` and `sizeof` never instantiate"
    A function call in an unevaluated operand usually doesn't instantiate the function body. But when the return type is `auto`, the body must be instantiated to know the type; and if the expression is potentially constant evaluated, it must be instantiated too (¶8). Errors in the body are then hard errors.

## Questions

!!! question "Question 1"
    Which of the following lines cause `Big<int>` to be implicitly instantiated?
    ```cpp
    template<class T> struct Big { T data[1000]; };
    Big<int>* a;                         // (1)
    Big<int>& f();                       // (2)
    auto g() -> Big<int>;                // (3)
    void h(Big<int>* p) { p = p + 1; }   // (4)
    bool b = std::is_class_v<Big<int>>;  // (5)
    ```

<details markdown="1">
<summary>Answer</summary>

Only (4). (1) and (2) are a pointer and a reference; (3) is a function declaration, and the return type only needs to be complete at the function definition and at calls. (4) Pointer arithmetic requires a pointer to a complete object type ([[expr.add]]). (5) `std::is_class` doesn't require a complete type; libraries usually implement it with a compiler builtin, and with Clang 23 + libc++ it doesn't instantiate. Putting `static_assert(sizeof(T) == 0)` in `Big` confirms that only (4) triggers it.
</details>

!!! question "Question 2"
    ```cpp
    template<class T> struct A {
      static constexpr int v = T::value;
      int arr[2];
    };
    int n = sizeof(A<int>);
    ```
    Is this code well-formed?

<details markdown="1">
<summary>Answer</summary>

Yes. `sizeof(A<int>)` instantiates the class `A<int>`, which per ¶3.1 generates only the declaration of the static data member `v`; the in-class initializer belongs to its definition, and `T::value` isn't substituted. Clang 23 accepts it. If the value of `A<int>::v` is used later, the initializer is instantiated and an error is reported.
</details>

!!! question "Question 3"
    Why is the body of a non-generic lambda instantiated with the enclosing function (¶13), but not that of a generic lambda?

<details markdown="1">
<summary>Answer</summary>

The call operator of a non-generic lambda is an ordinary member function. Once the enclosing function specialization is instantiated, it is already a concrete function, and there will never be template arguments to trigger its instantiation later, so it has to be instantiated now. The call operator of a generic lambda is a member template whose body depends on its own `auto` parameters, so it can wait until it is called, and ¶12 applies. However, parts of the body that only depend on the enclosing `T` are non-dependent once `T` is substituted, and implementations may diagnose them early per [[temp.res.general#6]].
</details>
