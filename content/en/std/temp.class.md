---
title: Class templates
summary: "A class template defines a family of unrelated class types; how to define its member functions, member classes, member enumerations and static data members outside the class; how deduction guides are written and how they are found."
updated: 2026-10-19
---

!!! tldr
    - `Array<int>` and `Array<long>` are two completely unrelated classes: there is no conversion between them, each has its own copy of the static members, and neither can see the other's private members.
    - When a member is defined outside the class, the *template-head* must be equivalent to the class template's, and the template name is followed by the parameters in their original order (a pack written as `Ts...`); parameter names may change. If the constraints are written differently but have the same effect, the program is IFNDR.
    - An ordinary member function of a class template is not a function template: its template arguments come from the object's type, no deduction happens at the call, and arguments can be implicitly converted.
    - A deduction guide tells CTAD which specialization to deduce for certain constructor arguments. It isn't found by name lookup and must be declared in the scope of the class template; an `explicit` guide only takes part in direct-initialization.
    - The out-of-class definition of a static data member is itself a template definition and can go in a header; an explicit specialization of a member array of unknown bound can use a different bound.

## A class template defines a family of types [temp.class.general]

```cpp run ok
template<class T> class Array {
    T* v;
    int sz;
public:
    explicit Array(int n) : v(new T[n]{}), sz(n) { }
    ~Array() { delete[] v; }
    Array(const Array&) = delete;      // Array means Array<T>
    T& operator[](int i) { return v[i]; }
    T& elem(int i) { return v[i]; }
};

int main() {
    Array<int> a(3);
    a[1] = 7;
    return a.elem(1) - 7;
}
```

¶1 A **class template** defines the layout and operations for an unbounded set of related types. The example in ¶2 is this `Array`: the prefix `template<class T>` says that a template is being declared, and that `T` may be used as a type name in the declaration. In other words, `Array` is a parameterized type with `T` as its parameter.

`Array` itself is not a type; `Array<int>` is. `Array<int>` is called a **specialization** of the class template. Writing just `Array` where a type is needed outside the class template either triggers class template argument deduction (CTAD, see deduction guides below) or is ill-formed.

Inside the class template, `Array` on its own is the **injected-class-name**, referring to the current specialization `Array<T>` ([[temp.local]]). So the copy constructor above can be written `Array(const Array&)` without repeating `<T>`.

Each specialization is an independent class. `Array<int>` and `Array<long>` have no inheritance or conversion relationship, each has its own copy of the static members, and one specialization can't access another's private members unless declared a friend ([[temp.friend]]).

## Defining members outside the class (¶3)

<div class="compare" markdown="1">

```cpp ok
template<class T1, class T2>
struct A { void f1(); };

// parameters renamed: OK
template<class X, class Y>
void A<X, Y>::f1() { }

template<class... Types>
struct B { void f3(); };

template<class... Ts>
void B<Ts...>::f3() { }
```

```cpp error
template<class T1, class T2>
struct A { void f2(); };

// order differs from the template-head
template<class T2, class T1>
void A<T1, T2>::f2() { }  // error

template<class... Types>
struct B { void f4(); };

template<class... Types>
void B<Types>::f4() { }   // error: pack not expanded
```

</div>

¶3 is a note that summarizes normative rules spread over [[temp.mem.func]] and [[temp.over.link]] into three points:

1. An out-of-class member definition is itself a template definition, and its *template-head* (the `template<...>` part) must be **equivalent** to the class template's ([[temp.over.link#6]]).
2. The parameter names may differ from those in the class template definition.
3. The class template name is followed by the template argument list of this *template-head* ([[temp.arg]]), that is, the parameters written in their original order, with a parameter pack written as `Ts...`.

Why is `A<T1, T2>` on the right wrong? The argument list of `template<class T2, class T1>` is `<T2, T1>`; what matters is the position of a parameter, and the name is just a label. Writing `A<T1, T2>` names a specialization with the two arguments swapped, which isn't the primary template, and there is no corresponding member declaration in the class template.

### Constraints must be equivalent too

If the class template is constrained, the constraints in the *template-head* of an out-of-class definition must be written the same way as the original:

```cpp error
template<typename T> concept C = true;
template<typename T> concept D = true;

template<C T> struct S {
    void f();
    void g();
    template<D U> struct Inner;
};

template<C A> void S<A>::f() { }        // OK: template-heads are equivalent
template<typename T> void S<T>::g() { } // error: constraint missing, no matching declaration
template<C X> template<D Y>
struct S<X>::Inner { };                 // OK: both template-heads are equivalent
```

The standard's example has one more form:

```cpp ifndr
template<typename T> concept C = true;
template<C T> struct S { void h(); };

template<typename T> requires C<T>   // IFNDR
void S<T>::h() { }
```

`template<C T>` and `template<typename T> requires C<T>` accept the same template arguments, so they are **functionally equivalent**, but they are written differently and so are not **equivalent**. Per [[temp.over.link#7]], such a program is ill-formed, no diagnostic required (IFNDR): the standard places no requirements on it, and the compiler may reject it or silently accept it.

The rule is this way because deciding whether two arbitrary constraints mean the same thing is in general impossible. The standard only requires compilers to compare the written structure, and leaves structurally different but semantically equal cases to IFNDR. Clang 23 rejects this line outright (type constraint differs in template redeclaration), which is allowed.

### The class-key must agree (¶4)

¶4 The *class-key* used in a partial specialization, explicit specialization or explicit instantiation of a class template must agree in kind with the original template declaration ([[dcl.type.elab]]). `class` and `struct` are the same kind; `union` only matches `union`.

```cpp error
template<class T> struct S { };
template<class T> class S<T*> { };      // OK: class and struct are the same kind
template<> union S<int> { };            // error: union and struct are different kinds
```

## Member functions [temp.mem.func]

### Out-of-class definitions (¶1)

¶1 A member function of a class template may be defined outside the class template definition:

```cpp run ok
#include <cstdio>
#include <cstdlib>
template<class T> class Array {
    T* v;
    int sz;
public:
    explicit Array(int);
    ~Array();
    T& operator[](int);
};

template<class T> Array<T>::Array(int n) : v(new T[n]{}), sz(n) { }
template<class T> Array<T>::~Array() { delete[] v; }
template<class T> T& Array<T>::operator[](int i) {
    if (i < 0 || sz <= i) { std::puts("Array: range error"); std::abort(); }
    return v[i];
}

int main() { Array<double> a(2); a[0] = 1.5; return int(a[0]) - 1; }
```

The qualifier must be written `Array<T>::`. Outside the class, `Array` is not the injected-class-name, so `template<class T> void Array::f()` is wrong. Once inside `Array<T>::`, the parameter list and function body are in class scope and can use plain `Array`, which is why the constructor is written `Array<T>::Array`.

A return type written before the declarator isn't in class scope yet and must be spelled out; a trailing return type is already in class scope:

```cpp run ok
template<class T> struct Node {
    Node* next();
    Node* prev();
};
template<class T> Node<T>* Node<T>::next() { return this; }
template<class T> auto Node<T>::prev() -> Node* { return this; }
int main() { Node<int> n; return n.next() == n.prev() ? 0 : 1; }
```

For a constrained member function, the out-of-class definition must repeat the same *requires-clause*. The trailing *requires-clause* is taken into account when matching an out-of-class definition to an in-class declaration ([[basic.scope.scope]]):

```cpp error
template<typename T> concept C = requires { typename T::type; };

template<typename T> struct S {
    void f() requires C<T>;
    void g() requires C<T>;
};

template<typename T>
void S<T>::f() requires C<T> { }      // OK
template<typename T>
void S<T>::g() { }                    // error: S<T> has no unconstrained g
```

### Template arguments come from the object (¶2)

¶2 The template arguments of a member function of a class template are determined by the type of the object on which it is called. `v1` is an `Array<int>`, so `v1[3]` calls `Array<int>::operator[]`.

It follows that an ordinary member function of a class template is not a function template. Once the class specialization is fixed, it is an ordinary function with fixed parameter types; no template argument deduction is done at the call, and arguments can undergo any implicit conversion:

```cpp run ok
template<class T> struct Wrap {
    void set(T) { }                     // the parameter type is fixed once Wrap<T> is determined
};
template<class T> void free_set(Wrap<T>&, T) { }   // function template: T deduced from each argument separately

int main() {
    Wrap<long> w;
    w.set(1);                           // OK: int implicitly converted to long
    // free_set(w, 1);                  // error: conflicting deductions for T (long and int)
    free_set<long>(w, 1);               // OK: specified explicitly
}
```

When a class template is implicitly instantiated, only the declarations of its member functions are instantiated; a member function's definition is instantiated only when it is needed ([[temp.inst]]). That's why `std::vector<std::unique_ptr<int>>` works: its copy constructor would fail if instantiated, but as long as nothing copies it, it isn't instantiated.

## Member classes [temp.mem.class]

¶1 A member class of a class template may be defined outside the class template definition. Note 1 reminds us that the definition must appear before the first use that requires it to be instantiated. If only pointers or references are used, the member class needn't be complete:

<div class="compare" markdown="1">

```cpp ok
template<class T>
struct A { class B; };

A<int>::B* b1;  // OK: only A<int> needed
template<class T>
class A<T>::B { };
A<int>::B b2;   // OK: definition has appeared
```

```cpp error
template<class T>
struct A { class B; };

A<int>::B b0;   // error: B not defined yet
template<class T>
class A<T>::B { };
```

</div>

## Member enumerations [temp.mem.enum]

¶1 A member enumeration of a class template may also be defined outside the class. This requires that the enumeration can be declared in the class without being defined, i.e. it has a fixed underlying type or is a scoped enumeration ([[dcl.enum]]):

```cpp run ok
template<class T> struct A {
    enum E : T;                         // underlying type depends on T
};
template<class T> enum A<T>::E : T { e1, e2 };
A<int>::E e = A<int>::e1;
int main() { return e; }
```

## Static data members [temp.static]

¶1 A definition of a static data member or static data member template may be provided in a namespace scope enclosing the definition of the class template:

```cpp run ok
template<class T> class X {
public:
    static T s;
};
template<class T> T X<T>::s = 0;        // itself a template definition

struct limits {
    template<class T>
    static const T min;                 // static data member template: declaration
};
template<class T>
const T limits::min = { };              // definition

int main() { return X<int>::s + limits::min<int>; }
```

`template<class T> T X<T>::s = 0;` is a template definition; it can go in a header included by several translation units without violating the ODR ([[basic.def.odr]]). A static data member definition of an ordinary class placed in a header would cause multiple definitions.

Since C++17 the more common style is to define it inside the class with `inline` or `constexpr` (implicitly inline), with no out-of-class definition:

```cpp run ok
template<class T> struct Counter {
    static inline int count = 0;
    static constexpr T zero{};
};
int main() {
    ++Counter<int>::count;
    ++Counter<long>::count;
    return Counter<int>::count - 1 + int(Counter<long>::zero);
}
```

`Counter<int>::count` and `Counter<long>::count` are two objects. To share one counter across all specializations, put the static member in a non-template base class.

!!! warning "Initialization order"
    Initialization of an implicitly instantiated static data member of a class template is unordered ([[basic.start.dynamic]]): if it needs dynamic initialization, there is no ordering guarantee relative to any other dynamic initialization, even in the same translation unit. Constant initialization with `constexpr` or `constinit` avoids the problem.

### Arrays of unknown bound (¶2)

¶2 If a static data member is declared as an array of unknown bound, an explicit specialization of it may use a different bound from the general definition:

```cpp run ok
template<class T> struct A {
    static int i[];
};
template<class T> int A<T>::i[4];       // general definition: 4 elements
template<> int A<int>::i[] = { 1 };     // explicit specialization: 1 element
static_assert(sizeof(A<char>::i) == 4 * sizeof(int));
static_assert(sizeof(A<int>::i) == sizeof(int));
int main() { }
```

The explicit specialization of `A<int>::i` is not instantiated from `A<T>::i[4]`; it directly provides the definition of member `i` of `A<int>`, so it can complete it with a different bound.

## Deduction guides [temp.deduct.guide]

```cpp run ok
#include <string>
#include <type_traits>
template<class T> struct S {
    T data;
    S(T t) : data(t) { }
};
S(const char*) -> S<std::string>;       // deduction guide

S a(42);                                // S<int>: deduced from the constructor
S b("hello");                           // S<std::string>: decided by the deduction guide
static_assert(std::is_same_v<decltype(a), S<int>>);
static_assert(std::is_same_v<decltype(b), S<std::string>>);
int main() { }
```

Since C++17 a variable can be declared with just the class template name, and the template arguments are deduced from the initializer. This is **class template argument deduction** (CTAD, [[dcl.type.class.deduct]]). The compiler generates a set of implicit deduction rules from the class template's constructors; without this deduction guide, `S b("hello")` would deduce `S<const char*>`.

A **deduction guide** is a user-supplied deduction rule: given constructor arguments like these, deduce this specialization. The full deduction algorithm is in [[over.match.class.deduct]]; this subclause only covers how deduction guides are declared.

```text
deduction-guide:
    explicit-specifier(opt) simple-template-name ( parameter-declaration-clause ) -> simple-template-id requires-clause(opt) ;
```

It looks like a constructor declaration with a trailing return type, but has no body, and after the arrow comes a specialization. A deduction guide may be preceded by a *template-head* to make it a template, or not.

### How guides are found (¶1)

¶1 Deduction guides are used when a class template name (or, in C++26, a *splice-type-specifier* designating a class template) appears as a deduced class type specifier.

!!! std
    Deduction guides are not found by name lookup. Instead, when performing class template argument deduction, all reachable deduction guides declared for the class template are considered.

A deduction guide is not a function: it can't be called and has no name that can be referred to. Using-declarations, using-directives and ADL have nothing to do with it. When CTAD is performed, every deduction guide declared for this class template that is reachable from that point ([[module.reach]]) takes part. Within a single translation unit, reachable roughly means appearing before the use.

The example in ¶2 is a template deduction guide:

```cpp run ok
#include <type_traits>
template<class T, class D = int>
struct S { T data; };

template<class U>
S(U) -> S<typename U::type>;

struct A {
    using type = short;
    operator type() { return 0; }
};
S x{A()};
static_assert(std::is_same_v<decltype(x), S<short, int>>);
int main() { }
```

The deduction guide gives `S<short>`, and the default template argument completes it to `S<short, int>`. Then `short data` is initialized from `A()`, using `A`'s conversion function.

A deduction guide only decides which specialization is deduced. After deduction, initialization proceeds by the ordinary rules for that specialization: in the first example, `S b("hello")` calls the constructor of `S<std::string>`, converting `const char*` to `std::string`. If that specialization has no suitable constructor, deduction succeeds and initialization still fails.

### Five restrictions (¶3)

¶3 imposes five requirements on deduction guide declarations:

1. The parameter list has the same restrictions as in a function declaration ([[dcl.fct]]), except that `auto` parameters are not allowed. For a template, write the *template-head* explicitly.
2. The *simple-template-id* after the arrow must name a class template specialization.
3. The name before the arrow must be the same identifier as the template name after it; `X(...) -> Y<...>` is ill-formed.
4. A deduction guide must be in the scope the class template belongs to; for a member class template, it must also have the same access.
5. If two deduction guides for the same class template have equivalent parameter lists and one is reachable from the other, the program is ill-formed. Deduction guides can't be redeclared.

```cpp error
#include <string>
template<class T> struct Z { Z(T) { } };
Z(int) -> Z<int>;
Z(int) -> Z<int>;                       // error: redeclaration

template<class T> struct Q { Q(T) { } };
Q(int) -> Z<int>;                       // error: different template name

class O {
    template<class T> struct In { In(T) { } };   // private
public:
    In(const char*) -> In<std::string>;          // error: access differs from In
};
```

```cpp
template<class T> struct W { W(T) { } };
W(auto) -> W<int>;                      // ill-formed per ¶3: no auto parameters
```

!!! warning "Clang deviates"
    Clang 23 accepts `W(auto) -> W<int>;`, using it as a template deduction guide with no diagnostic. This doesn't conform to the standard, which is why the snippet above has no verdict label.

Restriction 4 means that for a class template at namespace scope, the deduction guides must be in the same namespace; you can't add deduction guides for `std::vector` in your own namespace. Deduction guides for a member class template go in the enclosing class:

```cpp run ok
#include <string>
#include <type_traits>
struct Outer {
    template<class T> struct In { In(T) { } };
    In(const char*) -> In<std::string>;   // public, like In
};
Outer::In i("x");
static_assert(std::is_same_v<decltype(i), Outer::In<std::string>>);
int main() { }
```

### explicit deduction guides

An `explicit` deduction guide, like an explicit constructor, takes no part in copy-initialization; if it is selected in copy-list-initialization, the program is ill-formed ([[over.match.class.deduct]]). So the same initializer can deduce different types with `=` and with `()`:

```cpp run ok
#include <string>
#include <type_traits>
template<class T> struct S {
    T data;
    S(T t) : data(t) { }
};
explicit S(const char*) -> S<std::string>;

S a("hi");             // direct-initialization: the explicit guide takes part
S b = "hi";            // copy-initialization: only the constructor-generated rules remain
static_assert(std::is_same_v<decltype(a), S<std::string>>);
static_assert(std::is_same_v<decltype(b), S<const char*>>);
int main() { }
```

### Constrained deduction guides

A deduction guide can have a *requires-clause* or constrained template parameters. When several guides match, constraints take part in the comparison ([[over.match.best]], [[temp.func.order]]):

```cpp run ok
#include <concepts>
#include <type_traits>
template<class T> struct Num { T v; };
template<std::integral I>       Num(I) -> Num<long long>;
template<std::floating_point F> Num(F) -> Num<double>;

Num a{1};
Num b{1.0f};
static_assert(std::is_same_v<decltype(a), Num<long long>>);
static_assert(std::is_same_v<decltype(b), Num<double>>);
int main() { }
```

!!! history "History"
    CTAD and deduction guides were introduced in C++17 by [[P0091R3]]. C++20 added CTAD for aggregates and alias templates ([[over.match.class.deduct]]). C++26 static reflection allows CTAD with a *splice-type-specifier* designating a class template, and the wording of ¶1 was extended accordingly.

!!! impl "Implementation notes"
    Each member function that is used is instantiated in every translation unit that uses it and emitted as a COMDAT (weak) symbol, which the linker deduplicates; unused ones generate no code. Template static members such as `X<int>::s` are likewise emitted as weak symbols, and if they need dynamic initialization, a guard variable ensures they are initialized only once. Deduction guides only take part in CTAD at compile time and produce no symbols.

## Questions

!!! question "Question 1"
    What are the types of `x` and `y`? What if the deduction guide is made `explicit`?

    ```cpp
    template<class T> struct Box { Box(T) {} };
    Box(int) -> Box<long>;
    Box x(1);
    Box y = 1;
    ```

<details markdown="1">
<summary>Answer</summary>

There are two candidates: `template<class T> Box(T) -> Box<T>`, generated from the constructor, and the user-written `Box(int) -> Box<long>`. For the argument `1`, both are exact matches; by [[over.match.best]] a non-template is better than a template, so the user guide is chosen, and both `x` and `y` are `Box<long>`.

With `explicit`, `x` is direct-initialization and the result is unchanged, still `Box<long>`. `y` is copy-initialization, the explicit guide doesn't take part, only the constructor-generated rule remains, and `y` is `Box<int>`.
</details>

!!! question "Question 2"
    Why is #1 correct and #2 wrong?

    ```cpp
    template<class T, class U> struct M { void f(); };
    template<class U, class T> void M<U, T>::f() { }   // #1
    template<class T, class U> void M<U, T>::f() { }   // #2
    ```

<details markdown="1">
<summary>Answer</summary>

The *template-head* of #1 is `template<class U, class T>`, whose argument list is `<U, T>`, matching `M<U, T>`; that the first parameter is called `U` doesn't matter. The argument list of #2 is `<T, U>`, but it is written as `M<U, T>`, a specialization with the two arguments swapped. That isn't the primary template, and no corresponding member declaration can be found.
</details>
