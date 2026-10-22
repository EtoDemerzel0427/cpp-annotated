---
title: Built-in operators
summary: "The list of candidate functions imagined so that built-in operators can take part in overload resolution for operators, and the ambiguities and surprises they cause when competing with user-written operators."
updated: 2026-10-19
---

!!! tldr
    - Whenever an operator has an operand of class or enumeration type, overload resolution is performed. Built-in operators enter the candidate set as a set of imagined functions (such as `int operator+(int, int)`); this page is that list.
    - Built-in candidates compete on equal terms with user-written `operator@`: they may win, or they may cause ambiguity. They aren't a fallback used only when nothing else is available.
    - Arithmetic candidates exist only for promoted types; there are no candidates for `const` lvalues, incrementing `bool`, or dereferencing or doing arithmetic on `void*`.
    - After a built-in candidate is selected, an operand of class type undergoes only the user-defined conversion itself, and is then checked against the requirements of the built-in operator in [[expr.compound]]; this step can still fail.
    - Two-way implicit conversions, multiple conversion functions, and converting to both a pointer and `bool` are the three most common sources of trouble; marking conversion functions `explicit` solves most of them.

## Why built-in candidates are needed

```cpp run ok
struct Meters {
  double v;
  operator double() const { return v; }   // implicitly convertible to double
};
int main() {
  Meters m{1.5};
  double d = m + 1;   // no operator+ taking Meters; this actually does double(m) + 1
  return d == 2.5 ? 0 : 1;
}
```

`m + 1` has an operand of class type, so overload resolution is done per [[over.match.oper]]. The user didn't write `operator+`, yet it should work. The compiler has to decide which conversion function converts `m` and to which arithmetic type, and the most direct way is to write the built-in `+` as a set of functions too and put them in the candidate set.

More important is the case where the user did write `operator+` and the class can also convert to an arithmetic type. Then the user version and the built-in versions must be put together and compared per [[over.match.best]] to find the best. That's what the built-in candidates are imagined for.

¶1 This subclause specifies the candidate functions that represent the built-in operators of [[expr.compound]]. They take part only in overload resolution for operators per [[over.match.oper]] and serve no other purpose: their address can't be taken, they can't be called explicitly, and name lookup doesn't find them.

Note 1 adds three points:

1. Built-in operators accept only operands of non-class type, while overload resolution for operators happens only when some operand originally has class or enumeration type. So selecting a built-in candidate means either the class has a user-defined conversion to a suitable non-class type, or the enumeration can be converted to a suitable type.
2. Some candidates are more permissive than the built-in operator itself. Once selected, the expression must still meet the requirements of [[expr.compound]] ([[over.match.oper#11]]); there are examples below.
3. If the user writes a non-template non-member function with exactly the same parameter types as some built-in candidate, that built-in candidate doesn't enter the candidate set ([[over.match.oper#3.3.4]]).

## The candidate list (¶2–¶25)

¶2 A **[[g:promoted-integral-type|promoted integral type]]** is a cv-unqualified integral type that is unchanged by integral promotion, such as `int`, `unsigned`, `long`, `long long`; `char`, `short` and `bool` promote to other types, so they don't count ([[conv.prom]]). Note 2 points out that wherever a promoted integral type is required, an unscoped enumeration is also accepted via integral promotion.

Candidates use only promoted types because built-in arithmetic does integral promotion first anyway ([[expr.arith.conv]]); `char + char` is really `int + int`:

```cpp run ok
struct C { operator char() const { return 'a'; } };
int main() {
  C c;
  auto x = c + c;   // int operator+(int, int): C converts to char, then promotes to int
  static_assert(__is_same(decltype(x), int));
  return x == 2 * 'a' ? 0 : 1;
}
```

¶3 Below, *vq* stands for `volatile` or no qualifier, not including `const`. These parameters are all lvalues to be modified, and `const` lvalues can't be modified, so the corresponding candidates aren't generated at all.

The table lists all the candidates by paragraph. `L` and `R` are generally cv-unqualified floating-point types or promoted integral types, and `LR` is the type resulting from the usual arithmetic conversions on them.

| ¶ | For which types | Candidates |
|---|---|---|
| ¶4 | `T`: an arithmetic type other than `bool`, or a pointer to object type | `vq T& operator++(vq T&)`, `T operator++(vq T&, int)`, likewise `--` |
| ¶5 | `T`: an object type, or a function type without cv- or ref-qualifiers | `T& operator*(T*)` |
| ¶6 | any type `T` | `T* operator+(T*)` |
| ¶7 | `T`: a floating-point type or promoted integral type | `T operator+(T)`, `T operator-(T)` |
| ¶8 | `T`: a promoted integral type | `T operator~(T)` |
| ¶9 | `C1` is `C2` or derived from it, `T` is an object or function type | `cv12 T& operator->*(cv1 C1*, cv2 T C2::*)` |
| ¶10 | `L`, `R`: floating-point types or promoted integral types | `LR operator* / + -(L, R)`; `bool operator== != < > <= >=(L, R)` |
| ¶11 | `T`: an integral type | `std::strong_ordering operator<=>(T, T)` |
| ¶12 | `L`, `R`: floating-point types | `std::partial_ordering operator<=>(L, R)` |
| ¶13 | `T`: an object type | `T* operator+(T*, ptrdiff_t)`, `T* operator+(ptrdiff_t, T*)`, `T* operator-(T*, ptrdiff_t)`, `T& operator[](T*, ptrdiff_t)`, `T& operator[](ptrdiff_t, T*)` |
| ¶14 | `T`: a pointer to object type | `ptrdiff_t operator-(T, T)` |
| ¶15 | `T`: an enumeration or pointer type | `bool operator== != < > <= >=(T, T)`, `R operator<=>(T, T)` |
| ¶16 | `T`: a pointer-to-member type, `std::meta::info`, `std::nullptr_t` | `bool operator==(T, T)`, `bool operator!=(T, T)` |
| ¶17 | `L`, `R`: promoted integral types | `LR operator% & ^ \|(L, R)`; `L operator<< >>(L, R)` |
| ¶18 | `L`: an arithmetic type; `R`: a floating-point type or promoted integral type | `vq L& operator= *= /= += -=(vq L&, R)` |
| ¶19 | any type `T` | `T* vq& operator=(T* vq&, T*)` |
| ¶20 | `T`: an enumeration or pointer-to-member type | `vq T& operator=(vq T&, T)` |
| ¶21 | `T`: an object type | `T* vq& operator+= -=(T* vq&, ptrdiff_t)` |
| ¶22 | `L`: an integral type; `R`: a promoted integral type | `vq L& operator%= <<= >>= &= ^= \|=(vq L&, R)` |
| ¶23 | | `bool operator!(bool)`, `bool operator&&(bool, bool)`, `bool operator\|\|(bool, bool)` |
| ¶24 | `L`, `R`: floating-point types or promoted integral types | `LR operator?:(bool, L, R)` |
| ¶25 | `T`: a pointer, pointer-to-member or scoped enumeration type | `T operator?:(bool, T, T)` |

Wherever the table says object type, cv-qualification is allowed. A few points need explanation:

- The return type in ¶9 is only illustrative; the type and value category of the result are determined by [[expr.mptr.oper]].
- The result types of ¶11 and ¶12, `std::strong_ordering` and `std::partial_ordering`, are defined in `<compare>`. Without that header, Clang reports `cannot use builtin operator '<=>' because type 'std::strong_ordering' was not found`. The `R` in ¶15 is determined by [[expr.spaceship]].
- `std::meta::info` in ¶16 {{c++26}} is the value type of static reflection; it can only be compared for equality, not ordered.
- `?:` can't be overloaded; the `operator?:` of ¶24 and ¶25 is just a description written for the overload resolution in [[expr.cond#6]] (note 3). An unscoped enumeration matches ¶24 through promotion; a scoped enumeration can't be promoted, and ¶25 fills the gap.
- The list has a few deliberate gaps: `bool` has no `++` or `--`; `void*` has no `*`, `++` or pointer addition and subtraction (`void` isn't an object type); `const` lvalues have no assignment or increment candidates at all.

## Using built-in operations through conversions

### Classes convertible to pointers

As long as a class can be implicitly converted to a pointer, all the built-in operations on pointers can be used on it directly:

```cpp run ok
int arr[3] = {10, 20, 30};
struct P { operator int*() const { return arr; } };
int main() {
  P p;
  int a = *p;       // ¶5: int& operator*(int*)
  int b = p[1];     // ¶13: int& operator[](int*, ptrdiff_t)
  int c = 2[p];     // ¶13: int& operator[](ptrdiff_t, int*)
  int* d = p + 1;   // ¶13
  auto e = p - p;   // ¶14: ptrdiff_t operator-(int*, int*)
  return a + b + c + *d + int(e) - 80;
}
```

The closure type of a capture-less lambda has a conversion function to function pointer, and `+[]{}` uses exactly ¶6's `T* operator+(T*)` (with `T` a function type) to turn a lambda into a function pointer. Likewise, `*[]{}` gets a function reference through ¶5:

```cpp run ok
int main() {
  auto p = +[](int x) { return x + 1; };
  static_assert(__is_same(decltype(p), int (*)(int)));
  auto& r = *[](int x) { return x * 2; };
  static_assert(__is_same(decltype(r), int (&)(int)));
  return p(1) + r(1) - 4;
}
```

### When there's no candidate

```cpp
int g;
struct R  { operator int&() { return g; } };
struct BR { operator bool&(); };
struct CR { operator const int&(); };
struct VP { operator void*(); };
void f(R r, BR b, CR c, VP v) {
  ++r; r++;          // OK: ¶4, int& operator++(int&)
  ++b;               // error: no ++ candidate for bool
  ++c;               // error: no const version of the candidate
  ++v;               // error: void* doesn't point to an object type
  (void)*v;          // error: ¶5 doesn't include void
  (void)(v == v);    // OK: ¶15 applies to all pointer types
}
```

### The left operand of assignment

[[over.match.oper#5]] specifies that for the first parameter of a built-in assignment operator only standard conversion sequences are considered. So even though the class can convert to `int&`, `r = 1` can't select `int& operator=(int&, int)`:

```cpp error
int g;
struct R { operator int&() { return g; } };
void f(R r) { r = 1; }   // error: the built-in candidate isn't viable, and R's implicit copy and move assignment don't accept 1
```

The right operand has no such restriction; the `s` in `i = s` can become `int` through a user-defined conversion.

!!! lawyer "Are compound assignments restricted too?"
    The *assignment-operator* of [[expr.assign]] includes `=` and all compound assignments, so read literally, [[over.match.oper#5]] covers `+=` and the rest too, and `r += 1` shouldn't select the ¶18 candidate either. At the time of writing, Clang 23 accepts `r += 1`, applying the restriction only to `=`.

## Ambiguities and surprises

Built-in candidates compete on equal terms with user candidates. The following cases are all common in real code.

### Two-way conversions

```cpp error
struct S {
  S(int);           // int → S
  operator int();   // S → int
};
S operator+(S, S);
void f(S s) {
  s + 1;            // error: ambiguous
}
```

The user's `operator+(S, S)`: `s` needs no conversion, `1` has to become `S` through a user-defined conversion. The built-in `operator+(int, int)`: `s` has to become `int` through a user-defined conversion, `1` needs no conversion. Each candidate is better on one argument, so it's ambiguous ([[over.match.best]]). Mark one of the conversions `explicit` (most commonly `explicit operator int()`) and the built-in candidate is no longer viable.

### Multiple conversion functions

```cpp error
struct S {
  operator int();
  operator double();
};
void f(S s) {
  (void)(s + 1);   // error: ambiguous
}
```

The first arguments of `int operator+(int, int)` and `double operator+(double, int)` convert through `operator int()` and `operator double()` respectively. User-defined conversion sequences through different conversion functions can't be compared ([[over.ics.rank#3.3]]), and the second argument needs no conversion in either, so they can't be told apart.

For the same reason, `d % 2` on a type `D` with only an `operator double()` is ambiguous, rather than reporting that `double` can't be used with modulo. ¶17 generates candidates for every pair of promoted integral types, and the sequences that convert `D` through `double` to `int`, `long` or `unsigned` have the same rank and can't be distinguished. Clang reports `use of overloaded operator '%' is ambiguous`.

Types with a template conversion function are the same: `a + 1` for `struct Any { template<class T> operator T(); };` is ambiguous, because a `T` can be deduced for every arithmetic candidate.

### Both pointer and `bool` conversions

```cpp run ok
int x = 5;
struct Ptr {
  operator int*() const { return &x; }
  operator bool() const { return true; }
};
int main() {
  Ptr p;
  auto r = p + 1;   // not int* + 1, but integer addition after bool promotes to int
  static_assert(__is_same(decltype(r), int));
  return r - 2;
}
```

The pointer candidate `int* operator+(int*, ptrdiff_t)` needs its second argument converted from `int` to `ptrdiff_t`; the integer candidate `int operator+(int, int)` converts its first argument through `operator bool` and then promotes, and its second argument needs no conversion. The first arguments use different conversion functions and can't be compared, and on the second argument the integer candidate is better, so integer addition wins. C++11 introduced `explicit operator bool` precisely to avoid problems like this.

### Checks after selection

[[over.match.oper#11]] specifies that after a built-in candidate is selected, an operand of class type undergoes only the user-defined conversion itself, without the second standard conversion after it, and is then checked per [[expr.compound]]. A combination that looks viable in the candidate list may not be accepted by the built-in operator itself:

```cpp error
struct Inc;
struct P { operator Inc*(); };
enum E { e };
struct S { operator E(); };
void f(P p, S s) {
  (void)(p + 1);     // error: the ¶13 candidate exists for any object type, but built-in + requires a complete type
  (void)(s + 1.0);   // error: (int, double) is selected, but s converts only to E, and mixed enumeration/floating arithmetic is ill-formed
}
```

In the second line, if the full conversion sequence `S → E → int` were performed, `s + 1.0` would be a valid `int + double`. But the standard converts only to `E`, which falls under C++26's prohibition of mixed enumeration and floating-point arithmetic ([[P2864R2]], [[expr.arith.conv]]). This way, a class taking part in a built-in operation through a conversion behaves the same as applying the built-in operation directly to the conversion result.

### `explicit operator bool` and `&&`

```cpp run ok
struct B { explicit operator bool() const { return true; } };
int main() {
  B b;
  bool r = b && !b;   // accepted by all major compilers
  return r;
}
```

[[expr.log.and]] and [[expr.unary.op]] specify that the operands of `&&`, `||` and `!` are contextually converted to `bool`, and explicit conversion functions are designed precisely for contextual conversion. Yet read strictly by the letter of this subclause and [[over.match.oper]], the operand has class type, so overload resolution is done against ¶23's `bool operator&&(bool, bool)`, and the parameter's implicit conversion sequence is modeled on copy-initialization, in which explicit conversion functions don't take part. The wording doesn't say clearly how contextual conversion is used here. All major compilers accept this code, and code like `if (p && q)` depends on it.

## The conditional operator (¶24–¶25)

`?:` can't be overloaded. But when the second and third operands have different types and at least one has class type, [[expr.cond#6]] borrows [[over.match.oper]] and the candidates of this subclause to decide how to convert the operands:

```cpp run ok
struct S { operator int() const { return 1; } };
struct T { operator double() const { return 2.5; } };
int main(int argc, char**) {
  auto x = argc > 0 ? S{} : T{};   // ¶24: double operator?:(bool, int, double)
  static_assert(__is_same(decltype(x), double));
  return x == 1.0 ? 0 : 1;
}
```

!!! impl
    - The families of candidates are infinite, and compilers don't actually generate them all. Clang first collects the pointer, enumeration, pointer-to-member and other types that each class-type operand's conversion functions can produce, and adds the relevant candidates from ¶4–¶25 only for those types; the arithmetic candidates are a fixed set of combinations of promoted types.
    - Because only the return types of non-template conversion functions are looked at, Clang can't enumerate all `T*` for a template conversion function such as `template<class T> operator T*()`, and `*s` directly reports `indirection requires pointer operand`. The conclusion (ill-formed) is the same as derived from the standard, but for a different reason.
    - In diagnostics, built-in candidates usually show up as notes like `built-in candidate operator+(int, int)`.

## History

!!! history
    - C++98 already had this candidate list, including describing the conditional operator with `operator?:`.
    - C++11 added the equality comparison candidates for `std::nullptr_t` and the `?:` candidate for scoped enumerations.
    - C++17 removed increment of `bool`, which is why ¶4 says other than `bool`.
    - C++20 added the `<=>` candidates (¶11, ¶12, ¶15).
    - C++26 added equality comparison for `std::meta::info` (¶16). [[P2864R2]] made mixed arithmetic between enumerations and floating-point types, and between two different enumerations, ill-formed, so some combinations selected through ¶10 fail in the subsequent check.

## Common misconceptions

!!! pitfall "Built-in candidates are used only when there's no user operator"
    They compete on equal terms with user candidates, may win (like `Ptr` above), or may cause ambiguity. Only `,`, unary `&` and `->` fall back to the built-in operator when there's no viable function ([[over.match.oper#13]]).

!!! pitfall "A class with implicit conversions to both a pointer and `bool`"
    `p + 1` selects integer addition. Conversion to `bool` should use `explicit operator bool`.

## Questions

!!! question "1. Which candidate does `s - t` below select? What type is the result?"
    ```cpp
    struct S { operator short() const; };
    struct T { operator unsigned char() const; };
    auto f(S s, T t) { return s - t; }
    ```

<details markdown="1">
<summary>Answer</summary>

`int operator-(int, int)`, that is, ¶10 with `L = R = int`. Both arguments are a user-defined conversion plus an integral promotion. For other combinations (such as `long - long`) the second standard conversion is an integral conversion, which ranks below a promotion; user-defined conversion sequences through the same conversion function can be compared by their second standard conversion ([[over.ics.rank#3.3]]), so `int, int` wins. After selection, `s` and `t` convert only to `short` and `unsigned char`, then the built-in `-` applies the usual arithmetic conversions, and the result is still `int`.
</details>

!!! question "2. Is `struct E { operator int*(); operator long*(); }; E e; *e;` valid?"

<details markdown="1">
<summary>Answer</summary>

Ill-formed, ambiguous. `int& operator*(int*)` and `long& operator*(long*)` are both viable, each through a different conversion function, and can't be compared.
</details>
