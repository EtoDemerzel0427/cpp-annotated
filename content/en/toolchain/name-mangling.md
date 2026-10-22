---
title: Name mangling (Itanium C++ ABI)
summary: How GCC and Clang encode C++ functions, variables and template specializations into symbol names the linker can compare, and how that encoding corresponds to the standard's notion of a signature.
group: Toolchain
tags: toolchain, ABI, Itanium, name mangling, linking
updated: 2026-10-19
---

!!! tldr
    - A mangled name encodes the signature as the standard defines it: the name, the enclosing scope and the parameter-type-list; member functions add cv- and ref-qualifiers, and function template specializations add the return type, template arguments and constraints.
    - The return type of a non-template function and the type of a variable aren't in the mangled name, so the linker can't detect mismatches in either.
    - The skeleton of the Itanium scheme is `_Z` + name + parameter types; nested names go inside `N…E`, and repeated parts are referred to by substitutions such as `S_` and `S0_`.
    - Lambdas, local static variables, unnamed namespaces and entities attached to modules all have dedicated encodings, so that the same entity gets the same name in every translation unit.
    - `extern "C"` entities aren't mangled, dropping the namespace and parameter types; MSVC uses a different scheme that also encodes return types, calling conventions and access control.

Linkers only understand strings. C++, though, allows overloaded functions with the same name, same-named entities in different namespaces and classes, and templates that generate countless same-named specializations. These different same-named entities must become different strings, while the same entity in different translation units (TUs) must become the same string. The rules for encoding C++ entities into symbol names are called **name mangling**.

The standard doesn't prescribe a mangling scheme, but it does prescribe what mangling is based on: the **signature**. The note in [[defns.signature]] says signatures are used as a basis for name mangling and linking. Per [[defns.signature]], [[defns.signature.member]] and [[defns.signature.templ]]:

| Entity | Signature contains |
|---|---|
| Function | Name, parameter-type-list, enclosing namespace |
| Member function | Name, parameter-type-list, class of which it is a member, cv-qualifiers, ref-qualifier, trailing requires-clause |
| Function template | Name, parameter-type-list, enclosing namespace, return type, template-head, trailing requires-clause |

What is in the signature is in the mangled name; what isn't in the signature, such as the return type of a non-template function, usually isn't in the mangled name either. [[toolchain/linking-and-symbols]] demonstrates the consequences.

This page covers the Itanium C++ ABI scheme that GCC and Clang use on almost every platform other than Windows. All examples are compiled with Clang 23 using `clang++ -std=c++2c --target=x86_64-linux-gnu -c`, with symbols listed by `llvm-nm` and demangled by `llvm-cxxfilt`. Mach-O symbols on macOS have an extra leading underscore (`_Z3apiv` becomes `__Z3apiv`) and are otherwise identical.

## The skeleton: `_Z` + name + parameter types

```cpp
void f() {}
void f(int) {}
void f(int, double, char) {}
```

```text
_Z1fv                                    f()
_Z1fi                                    f(int)
_Z1fidc                                  f(int, double, char)
```

Taking `_Z1fidc` apart:

| Piece | Meaning |
|---|---|
| `_Z` | Marks a mangled C++ name. Identifiers starting with `_Z` are reserved for the implementation ([[lex.name]]), so they can't clash with user names |
| `1f` | The source-name: length plus identifier |
| `idc` | Parameter types: `int`, `double`, `char` |

No parameters is written `v` (void). The return type of a non-template function isn't encoded: overload resolution doesn't look at return types ([[over.load]]), and the signature doesn't contain it.

### Builtin type codes

```text
_Z1fmxbfwDuDsDi       f(unsigned long, long long, bool, float, wchar_t, char8_t, char16_t, char32_t)
_Z1fahstjeDn          f(signed char, unsigned char, short, unsigned short, unsigned int, long double, std::nullptr_t)
_Z1fiz                f(int, ...)
```

| Code | Type | Code | Type | Code | Type |
|---|---|---|---|---|---|
| `v` | void | `c` | char | `a` | signed char |
| `h` | unsigned char | `s` | short | `t` | unsigned short |
| `i` | int | `j` | unsigned int | `l` | long |
| `m` | unsigned long | `x` | long long | `y` | unsigned long long |
| `b` | bool | `w` | wchar_t | `f` | float |
| `d` | double | `e` | long double | `z` | `...` |
| `Du` | char8_t | `Ds` | char16_t | `Di` | char32_t |
| `Dn` | `std::nullptr_t` | `Da` | `auto` | `Dc` | `decltype(auto)` |

`char`, `signed char` and `unsigned char` are three distinct types ([[basic.fundamental]]), so they have three distinct codes. `int` and `long` have different codes even on platforms where they are the same size.

### Compound types

```cpp
void f(int*, const int*, int&, const int&, int&&, volatile int*) {}
void f(int[3], int (*)[3], int (&)[4]) {}
void f(void (*)(int), int (*)(double, char)) {}
```

```text
_Z1fPiPKiRiRS0_OiPVi                     f(int*, int const*, int&, int const&, int&&, int volatile*)
_Z1fPiPA3_iRA4_i                         f(int*, int (*) [3], int (&) [4])
_Z1fPFviEPFidcE                          f(void (*)(int), int (*)(double, char))
```

| Code | Meaning |
|---|---|
| `P` | Pointer |
| `R` / `O` | Lvalue reference / rvalue reference |
| `K` / `V` / `r` | const / volatile / restrict, written before the type they qualify: `PKi` is a pointer to `const int` |
| `A3_i` | `int[3]` |
| `F…E` | Function type: return type plus parameter types |
| `M<class><member type>` | Pointer to member |

The first parameter of the second function is written `int[3]` in the source, but the mangled name has `Pi`. That is because the parameter-type-list is determined after adjustment ([[dcl.fct]]): array parameters are adjusted to pointers, function parameters to function pointers, and top-level cv-qualifiers are dropped. So each of the two pairs of declarations below is the same function:

```cpp error
void f(int[3]) {}
void f(int*) {}         // error: redefinition of 'f'
void g(const int) {}
void g(int) {}          // error: redefinition of 'g'
```

The array bound in `int (*)[3]` (`PA3_i`) isn't adjusted; it is part of the pointed-to type.

### Substitutions: `S_`, `S0_`, `S1_`

Mangled names easily get long, so the ABI specifies that components that have already appeared (qualified names, compound types, template parameters and so on, but not builtin types) are numbered in order of appearance and referred to by **substitution** when they reappear. The first is `S_`, the second `S0_`, then `S1_`, with sequence numbers in base 36 (digits plus uppercase letters).

In `_Z1fPiPKiRiRS0_OiPVi`:

| Number | Component |
|---|---|
| `S_` | `Pi` (`int*`) |
| `S0_` | `Ki` (`const int`) |
| `S1_` | `PKi` |
| `S2_` | `Ri` |

So the fourth parameter `const int&` is written `RS0_` rather than `RKi`. Namespaces are components too:

```text
_ZN2ns5inner1hENS0_3TagES1_              ns::inner::h(ns::inner::Tag, ns::inner::Tag)
```

Here `S_` is `ns` and `S0_` is `ns::inner`. `NS0_3TagE` is `ns::inner::Tag`, which becomes `S1_`, so the second parameter is simply `S1_`.

## Namespaces and classes: nested names `N…E`

```cpp
namespace ns { void g(int) {} int var; }
struct S { static int count; };
int S::count;
int ns_var;
```

```text
_ZN2ns1gEi                         ns::g(int)
_ZN2ns3varE                        ns::var
_ZN1S5countE                       S::count
ns_var                             ns_var
```

Between `N` and `E` are the names at each level, from outermost to innermost. The last three lines are variables: a variable in a namespace or class encodes only its qualified name, not its type. The variable `ns_var` in the global namespace isn't mangled at all, the same as a C variable name. This is what [[dcl.link#7]] relies on in saying that a variable with C language linkage and a same-named variable at global scope are the same entity.

### cv- and ref-qualifiers on member functions

```cpp
struct S {
    void m() {}
    void m() const {}
    void m() volatile {}
    void r() & {}
    void r() && {}
    static void s() {}
};
```

```text
_ZN1S1mEv                          S::m()
_ZNK1S1mEv                         S::m() const
_ZNV1S1mEv                         S::m() volatile
_ZNR1S1rEv                         S::r() &
_ZNO1S1rEv                         S::r() &&
_ZN1S1sEv                          S::s()
```

A member function's cv-qualifiers and ref-qualifier follow right after `N` (`NK`, `NV`, `NR`, `NO`), corresponding to those two items in a member function's signature. The static member function `s()` has the same mangled name as a non-static, non-const member function with the same parameters, because the two can't overload each other anyway ([[over.load]]).

### Operators and conversion functions

```text
_ZN1SaSERKS_                       S::operator=(S const&)
_ZNK1SeqERKS_                      S::operator==(S const&) const
_ZN1SixEi                          S::operator[](int)
_ZNK1ScviEv                        S::operator int() const
_ZN1SclEv                          S::operator()()
```

Operators are encoded with two lowercase letters: `aS` is `=`, `eq` is `==`, `ix` is `[]`, `cl` is `()`, `cv` is a conversion function (followed by the target type), and there are also `nw` (new), `pl` (+), `gt` (>), `st` (sizeof a type) and so on. The `S_` in `RKS_` is the class `S` itself, the first component to appear.

### Constructor and destructor variants

Constructors and destructors have no usable name, so they are mangled as `C` or `D` plus a digit. One constructor produces more than one symbol:

```cpp
struct T { T(); ~T(); virtual void v(); };
T::T() {} T::~T() {} void T::v() {}
```

```text
$ llvm-nm ctor.o
0000000000000060 T _ZN1TC1Ev
0000000000000060 T _ZN1TC2Ev
0000000000000080 T _ZN1TD1Ev
0000000000000080 T _ZN1TD2Ev
...
```

| Code | Meaning |
|---|---|
| `C1` | **Complete object constructor**: constructs the whole object, including virtual bases |
| `C2` | **Base object constructor**: used when this class is constructed as a base of another class; doesn't construct virtual bases |
| `D0` | **Deleting destructor**: calls `operator delete` after destruction; `delete p` calls it through the vtable |
| `D1` | Complete object destructor |
| `D2` | Base object destructor |

C1 and C2 are distinguished because of virtual bases: a virtual base may be constructed only once, by the most derived class ([[class.base.init]]). Without virtual bases the two have identical code, which is why `C1` and `C2` have the same address above; Clang targeting Linux makes C1 an alias of C2 by default. `D0` is generated only when the destructor is virtual; `T`'s destructor isn't, so it doesn't exist. How the VTT uses C2 to pass vtables during construction is covered in [[toolchain/object-layout-and-vtables]].

## Templates

```cpp
template <class T> T twice(T x) { return x + x; }
template <class T> void ignore(T) {}
template <class T, int N> struct Arr { T data[N]; void fill(T) {} };
template <class... Ts> void pack(Ts...) {}
template <auto V> void val() {}
template <class T> auto deduced(T x) { return x; }
template <class T> struct Outer { template <class U> static void mem(T, U) {} };
template <class T> void cond(T) requires (sizeof(T) > 1) {}
```

```text
_Z5twiceIiET_S0_                     int twice<int>(int)
_Z5twiceIdET_S0_                     double twice<double>(double)
_Z6ignoreIiEvT_                      void ignore<int>(int)
_Z6ignoreIPKcEvT_                    void ignore<char const*>(char const*)
_ZN3ArrIcLi16EE4fillEc               Arr<char, 16>::fill(char)
_Z4packIJidcEEvDpT_                  void pack<int, double, char>(int, double, char)
_Z4packIJEEvDpT_                     void pack<>()
_Z3valITnDaLi42EEvv                  void val<42>()
_Z3valITnDaLc97EEvv                  void val<(char)97>()
_Z3valITnDaLb1EEvv                   void val<true>()
_Z7deducedIlEDaT_                    auto deduced<long>(long)
_ZN5OuterIiE3memIfEEviT_             void Outer<int>::mem<float>(int, float)
_Z4condIiEvT_QgtstS0_Li1E            void cond<int>(int) requires (sizeof (int) > 1)
```

### Template arguments

Template arguments go between `I…E`: `IiE` is `<int>`. Non-type arguments are encoded as literals `L<type><value>E`: `Li16E` is `16`, `Lc97E` is `(char)97`, `Lb1E` is `true`. An argument pack is written `J…E`, and a pack expansion in the function parameters is written `Dp`. `TnDa` marks a non-type template parameter of type `auto`.

### Function template specializations encode the return type

In `twice<int>`'s mangled name, after `IiE` comes the return type `T_` and then the parameter `S0_`; the `v` in `ignore<int>` is likewise the return type. This corresponds to [[defns.signature.templ]]: a function template's signature includes its return type.

So two function templates differing only in return type can coexist, and their specializations have different symbols:

```cpp
template <class T> int  h(T) { return 0; }
template <class T> long h(T) { return 0; }
```

```text
_Z1hIiEiT_                     int h<int>(int)
_Z1hIiElT_                     long h<int>(int)
```

Calling `h(1)` directly is ambiguous; you need something like `static_cast<long (*)(int)>(&h<int>)` to pick one.

### Types are encoded as written in the template

The return type and parameter of `twice<int>` are written `T_` (the first template parameter), not `i`. The mangled name encodes the types as written in the template declaration, not the result after substitution. In `_Z5twiceIiET_S0_`, `S_` is the template name `twice` and `S0_` is `T_`.

The two parameters of `Outer<int>::mem<float>` are written `i` and `T_`. The outer class template's `T` is already fixed as `int` here, and only the member template's own parameter `U` is written `T_`. This way, two function template declarations that are functionally equivalent but written differently get different names ([[temp.over.link]]).

`deduced`'s return type is encoded as `Da` (`auto`), because the return type in the signature is the placeholder `auto`. The `Q…` at the end of `cond` encodes the trailing requires-clause, in which `gt` is `>` and `st` is `sizeof(type)`. The signature includes constraints, so two same-named templates with different constraints can have different symbols.

### Expressions

Expressions can also appear in mangled names, for example in a `decltype` return type:

```cpp
template <class T> auto add(T a, T b) -> decltype(a + b) { return a + b; }
```

```text
_Z3addIiEDTplfp_fp0_ET_S1_  decltype(fp + fp0) add<int>(int, int)
```

`DT…E` is `decltype(expression)`, `pl` is `+`, and `fp_` and `fp0_` are the first and second function parameters.

## Standard library names

### Abbreviations for `std`

Names in `std` are extremely common, and the ABI reserves fixed abbreviations for them that don't take substitution numbers:

| Abbreviation | Meaning |
|---|---|
| `St` | `::std::` |
| `Sa` | `std::allocator` |
| `Sb` | `std::basic_string` |
| `Ss` | `std::basic_string<char, std::char_traits<char>, std::allocator<char>>` |
| `Si` / `So` / `Sd` | `std::basic_istream<char, ...>` / `basic_ostream` / `basic_iostream` |

Below, a few declarations are written by hand in `std` to see how the compiler uses these abbreviations. This is only for observing mangling: adding declarations to `std` is undefined behavior ([[namespace.std]]).

```text
_Z1gSt5thing                             g(std::thing)
_Z1gSaIiE                                g(std::allocator<int>)
_Z1gRKSs                                 g(std::string const&)
_Z1gSt6vectorISsSaISsEE                  g(std::vector<std::string, std::allocator<std::string>>)
```

### Inline namespaces and ABI versions

Real standard libraries rarely get to use these abbreviations directly, because they put their implementations in inline namespaces:

- libc++ uses `std::__1`. Natively compiling `void f(const std::string&)` on our test machine gives `__Z1fRKNSt3__112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEEE`. `Ss` only matches a `basic_string` located directly in `::std`, so it can't be used here; `NS_` is the first substitution, `std::__1`.
- In libstdc++ since GCC 5, `std::string` is `std::__cxx11::basic_string` (according to libstdc++'s documentation on its dual ABI; our test machine has no libstdc++). Its default constructor is `_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC1Ev`. Classes not put in an inline namespace, such as `std::ostream`, still use the abbreviations: `std::cout << 1` calls `_ZNSolsEi`.

Standard libraries manage ABI versions precisely through inline namespaces. When the layout of `std::string` changes, switching to a different inline namespace changes every symbol name that uses it. When old and new binaries are mixed, the error appears at link time rather than at run time.

### `abi_tag`

libstdc++ also uses the GCC extension attribute `abi_tag`. If the return type carries a tag and the parameters don't, the tag is attached to the function name; otherwise two functions differing only in return type would get the same symbol:

```cpp
namespace std { inline namespace __cxx11 __attribute__((abi_tag("cxx11"))) { struct string {}; } }
std::string make() { return {}; }
void take(std::string) {}
```

```text
_Z4makeB5cxx11v                make[abi:cxx11]()
_Z4takeNSt7__cxx116stringE     take(std::__cxx11::string)
```

`B5cxx11` is the tag. `take`'s parameters already contain a tagged type, so no extra tag is needed.

## Local entities, lambdas and unnamed namespaces

### Local entities: `Z <function> E <name>`

```cpp
int init();
int local_static() {
    static int counter = init();
    struct Local { int get() { return 1; } };
    return counter + Local{}.get();
}
inline int locals(bool b) {
    if (b) { static int n = 1; return n; }
    else   { static int n = 2; return n; }
}
```

```text
_ZZ12local_staticvE7counter              local_static()::counter
_ZGVZ12local_staticvE7counter            guard variable for local_static()::counter
_ZZ12local_staticvEN5Local3getEv         local_static()::Local::get()
_ZZ6localsbE1n                           locals(bool)::n
_ZZ6localsbE1n_0                         locals(bool)::n
```

The mangled names of static variables inside functions and of member functions of local classes start with `Z <full encoding of the enclosing function> E`. Same-named local entities in the same function are distinguished by a **discriminator**: the two `static int n` in the two blocks of `locals` are `1n` and `1n_0` respectively.

The `_ZGV` prefix denotes a **guard variable**. A local static variable is initialized the first time control passes through its declaration, and other threads entering concurrently must wait ([[stmt.dcl#3]]); the guard variable records whether initialization has completed. Only local static variables needing dynamic initialization have one; the constant-initialized `n`s in `locals` don't.

Local entities also need names that are stable across TUs, because they may be in inline functions. [[basic.def.odr]] requires `locals(bool)::n` to be the same variable in every TU, and the linker can only merge them by their names being identical.

### Lambdas: `Ul <parameters> E <number> _`

Closure types have no name ([[expr.prim.lambda.closure]]). When a lambda appears somewhere that may be defined in several TUs, such as an inline function, a template or an inline variable, its closure type needs a name that is consistent across TUs:

```cpp
template <class F> void call(F f) { f(); }
inline void twolambdas() {
    call([] {});
    call([] {});
    auto l = [](int, char) {}; l(1, 2);
}
inline auto lam_var = [] { return 0; };
```

```text
_Z4callIZ10twolambdasvEUlvE_EvT_             void call<twolambdas()::'lambda'()>(twolambdas()::'lambda'())
_Z4callIZ10twolambdasvEUlvE0_EvT_            void call<twolambdas()::'lambda0'()>(twolambdas()::'lambda0'())
_ZZ10twolambdasvENKUlvE_clEv                 twolambdas()::'lambda'()::operator()() const
_ZZ10twolambdasvENKUlicE_clEic               twolambdas()::'lambda'(int, char)::operator()(int, char) const
_ZNK7lam_varMUlvE_clEv                       lam_var::'lambda'()::operator()() const
```

`UlvE_` is the first lambda with parameters `()`, `UlvE0_` the second, and `UlicE_` the first with parameters `(int, char)`. Lambdas are numbered separately for each distinct parameter list. The lambda in `lam_var`'s initializer has the prefix `7lam_varM`, where `M` means it belongs to that variable's initializer.

As long as an inline function's definition is the same in every TU (which the ODR requires), each lambda gets the same name in every TU, and only then can the multiple definitions of `call<that lambda>` be merged by the linker.

For a lambda in a non-inline function, the closure type only ever appears in this TU. Clang then doesn't use the ABI's numbering but gives it an internal name:

```cpp
void use() {
    call([] {});
    auto g = [](auto x) { return x; };
    g(1);
}
```

```text
_Z4callIZ3usevE3$_1EvT_                  void call<use()::$_1>(use()::$_1)
_ZZ3usevENK3$_1clEv                      use()::$_1::operator()() const
_ZZ3usevENK3$_0clIiEEDaT_                _ZZ3usevENK3$_0clIiEEDaT_
```

`$_0` and `$_1` are neither valid C++ identifiers nor encodings specified by the ABI. These symbols are all local and needn't be consistent across TUs. The last line is a generic lambda's `operator()<int>`; `llvm-cxxfilt` on our test machine can't demangle such names and outputs them unchanged.

### Unnamed namespaces: `_GLOBAL__N_1`

```cpp
namespace { int anon_fn(int x) { return x; } struct Hidden { void m() {} }; }
static int file_static(int x) { return x; }
```

```text
_ZN12_GLOBAL__N_17anon_fnEi              (anonymous namespace)::anon_fn(int)
_ZN12_GLOBAL__N_16Hidden1mEv             (anonymous namespace)::Hidden::m()
_ZL11file_statici                        file_static(int)
```

An unnamed namespace is encoded as a namespace named `_GLOBAL__N_1`, the same name in every TU. Same-named symbols from different TUs don't collide because they are all local symbols: an unnamed namespace has internal linkage, and so do the entities in it ([[basic.link#4]]). A `static` function instead gets an `L` before its name to mark internal linkage: `_ZL11file_statici`.

## Module attachment: `W`

Since C++20, an entity attached to a named module is a different entity from a same-named entity in the global module ([[module.unit]]). The Itanium ABI encodes the module an entity is attached to with `W`:

```cpp title="mm.cppm"
module;
int from_gmf(int x) { return x; }
export module app.core;
export import :detail;
export int answer() { return 42; }
int helper() { return 1; }
export namespace ns {
    struct Widget { void draw() {} };
    void use(Widget w) { w.draw(); }
}
extern "C++" int legacy() { return 0; }
```

```cpp title="mp.cppm"
export module app.core:detail;
int part_fn() { return 3; }
```

```text
_Z8from_gmfi                             from_gmf(int)
_ZW3appW4core6answerv                    answer@app.core()
_ZW3appW4core6helperv                    helper@app.core()
_ZN2nsW3appW4core3useENS_S1_6WidgetE     ns::use@app.core(ns::Widget@app.core)
_ZN2nsW3appW4core6Widget4drawEv          ns::Widget@app.core::draw()
_Z6legacyv                               legacy()
_ZGIW3appW4core                          initializer for module app.core
_ZW3appW4core7part_fnv                   part_fn@app.core()
_ZGIW3appW4coreWP6detail                 initializer for module app.core:detail
```

The output shows:

- The dotted module name `app.core` is encoded segment by segment as `W3appW4core`.
- Exporting doesn't affect symbols. `answer` (exported) and `helper` (not exported) both carry `W` and are both global symbols.
- Partitions don't appear in entity names. `part_fn` is defined in the partition `:detail`, but it is attached to module `app.core`, and its symbol is `_ZW3appW4core7part_fnv`. Only the partition's initialization function carries `WP6detail`.
- `from_gmf` in the global module fragment and `legacy` in `extern "C++"` are attached to the global module, and their symbols are exactly the same as in ordinary non-module code. This is exactly what `extern "C++"` is for in a module: letting the module provide entities that are binary-compatible with old code.
- Namespaces aren't attached to modules, so `ns` itself doesn't carry `W`; the `W` is inserted after `ns` and before the name of the attached entity.

The `export import :detail;` in the primary module interface can't be omitted: all interface partitions of a module must be exported, directly or indirectly, by the primary module interface, otherwise the program is ill-formed, no diagnostic required ([[module.unit#3]]). The module build process is covered in [[toolchain/modules-in-practice]].

## `noexcept` in function types

Since C++17, `noexcept` is part of the function type ([[except.spec]]), so it appears in the encoding of function types:

```cpp
void take_fp(void (*)() noexcept, void (*)()) {}
void nx() noexcept {}
```

```text
_Z7take_fpPDoFvvEPFvvE                   take_fp(void (*)() noexcept, void (*)())
_Z2nxv                                   nx()
```

`Do` marks a noexcept function type. The function `nx`'s own symbol, though, is `_Z2nxv`: you can't overload on noexcept alone, and it isn't in the signature.

## `extern "C"`: no mangling

```cpp
extern "C" int c_func(int x) { return x; }
extern "C" int c_var = 1;
namespace ns { extern "C" int c_in_ns(int x) { return x; } }
```

```text
0000000000000000 T c_func
0000000000000010 T c_in_ns
0000000000000000 D c_var
```

Functions and variables with C language linkage ([[dcl.link]]) are named by C's rules: the symbol is just the identifier (with a `_` added on Mach-O). The namespace is dropped, and `ns::c_in_ns` has the same symbol as a global `c_in_ns`. That is why [[dcl.link#7]] says same-named functions with C language linkage in different namespaces declare the same function. The parameter types are dropped too, so functions with C language linkage can't be overloaded.

!!! lawyer "Language linkage of function types: the standard says different types, compilers don't"
    Per [[dcl.link#1]], two function types with different language linkages are different types, even if otherwise identical. The Itanium ABI even reserves an encoding for this, a `Y` before the function type. But GCC and Clang both ignore the language linkage of function types:

    ```cpp
    extern "C" typedef void CFn();
    typedef void CppFn();
    void take(CFn*) {}
    void take(CppFn*) {}   // a valid overload according to the standard
    ```

    Clang 23 reports `error: redefinition of 'take'`. `llvm-cxxfilt` can parse mangled names containing `Y` (`_Z4takePFYvvE` demangles to `take(void (*)())`), but the compiler never generates them. This is a long-standing nonconformance in mainstream implementations.

## Special names generated by the compiler

The ABI also specifies names for auxiliary entities the compiler generates. Every entry in the table below appeared in object files from our experiments:

| Prefix | Meaning | Example |
|---|---|---|
| `_ZTV` | Virtual table (vtable) | `_ZTV5Shape` |
| `_ZTI` | `type_info` object | `_ZTI5Shape` |
| `_ZTS` | Type name string, the source of `type_info::name()` | `_ZTS5Shape` |
| `_ZTT` | VTT, the table of vtables used when constructing objects with virtual bases | `_ZTT1D` |
| `_ZTC` | Construction vtable | `_ZTC1D0_1L` (`L` as a base of `D`) |
| `_ZTh` | Non-virtual thunk: adjusts `this` by a fixed amount | `_ZThn16_N1C2fbEv` |
| `_ZTv` | Virtual thunk: looks up the adjustment through the vtable | `_ZTv0_n24_N1D2fvEv` |
| `_ZGV` | Guard variable | `_ZGVZ12local_staticvE7counter` |
| `_ZGR` | Temporary bound to a reference, with extended lifetime | `_ZGR1r_` (`const int& r = 42;`) |
| `_ZTW` | Wrapper function for a thread_local variable | `_ZTWN2ns1tE` |
| `_ZGI` | Module initialization function | `_ZGIW1m` |

The contents of vtables, VTTs and thunks are covered in [[toolchain/object-layout-and-vtables]].

## Demangling

```text
$ echo _ZN2ns5inner1hENS0_3TagES1_ | llvm-cxxfilt
ns::inner::h(ns::inner::Tag, ns::inner::Tag)
$ echo __Z5twiceIiET_S0_ | c++filt          # also handles Mach-O's extra underscore
int twice<int>(int)
$ llvm-nm -C a.o                              # demangle while listing symbols
$ llvm-objdump -d -C a.o                      # demangle while disassembling
```

Inside a program, you can call the Itanium ABI's `abi::__cxa_demangle` (`<cxxabi.h>`). On Itanium platforms, `typeid(T).name()` returns the `_ZTS` string minus its prefix, for example `"5Shape"`.

!!! note "Demangling loses information"
    Demangling produces text for humans and doesn't keep all the information. `_Z1fSs` demangles to `f(std::string)`, and the text doesn't tell you whether the original used the `Ss` abbreviation or the expanded form. Comparing demangled text to decide whether two symbols are the same may give the wrong answer.

## MSVC's mangling scheme

The MSVC mangled names below were generated by Clang with `--target=x86_64-pc-windows-msvc` and demangled with `llvm-undname`. Clang implements MSVC-compatible mangling on Windows targets so that it can interoperate with code compiled by MSVC; there is no MSVC on our test machine, and we didn't check character by character that the two agree.

```text
?f@@YAXH@Z                   void __cdecl f(int)
?f@@YAXHND@Z                 void __cdecl f(int, double, char)
?f2@@YAHH@Z                  int __cdecl f2(int)
?g@ns@@YAXPEAH@Z             void __cdecl ns::g(int *)
?m@S@@QEBAXXZ                public: void __cdecl S::m(void) const
??0S@@QEAA@XZ                public: __cdecl S::S(void)
??1S@@UEAA@XZ                public: virtual __cdecl S::~S(void)
??_GS@@UEAAPEAXI@Z           public: virtual void * __cdecl S::`scalar deleting dtor'(unsigned int)
??_7S@@6B@                   const S::`vftable'
?count@S@@2HA                public: static int S::count
??$twice@H@@YAHH@Z           int __cdecl twice<int>(int)
c_func                       (extern "C", not mangled)
```

The main differences from the Itanium scheme:

- Names start with `?`, qualifiers are written from innermost to outermost, separated by `@`, and terminated by `@@`.
- Non-template functions encode their return type too (the first `H` in `?f2@@YAHH@Z` is the returned `int`), and variables encode their type (the `H` in `?count@S@@2HA`). The example in [[toolchain/linking-and-symbols]] where mismatched return types still link would have different symbol names under this scheme and fail to link.
- The calling convention (`A` is `__cdecl`) and access control (`Q` is a public member function, `2` a public static data member) are encoded. Changing a member from `private` to `public` changes its symbol name and breaks binary compatibility; Itanium doesn't encode access control.
- Constructors are `??0`, destructors `??1`, vtables `??_7`, and RTTI-related objects `??_R0` through `??_R4`.

## Questions

!!! question "Question 1"
    `a.cpp` defines `long size() { return 1; }`, and `b.cpp` declares `int size();` and calls it. What happens when compiled and linked with GCC on Linux? With MSVC on Windows?

<details markdown="1">
<summary>Answer</summary>

The two sides declare the same function with different types. The two declarations aren't reachable from each other, so the program is ill-formed, no diagnostic required ([[basic.link#11]]). The Itanium scheme doesn't encode the return type of non-template functions, so both sides' symbols are `_Z4sizev`, linking succeeds, and the run-time result is not guaranteed. The MSVC scheme encodes the return type; the two symbols are `?size@@YAJXZ` and `?size@@YAHXZ`, and linking reports an unresolved external symbol.
</details>

!!! question "Question 2"
    Why do lambdas in inline functions use sequentially numbered names like `UlvE_`, while lambdas in ordinary functions can use implementation-chosen names like `$_0`?

<details markdown="1">
<summary>Answer</summary>

An inline function can be defined in several TUs, and [[basic.def.odr]] requires these definitions to denote the same entity, so the lambda closure types in them must also be the same type in every TU. Template specializations with them as arguments (such as `call<that lambda>`) are generated in several TUs, and the linker can only merge them by their names being identical, so the names must be determined by rules every TU can compute independently. An ordinary function is defined in only one TU, its lambdas never appear in other TUs, and the related symbols are all local, so what they are called doesn't affect linking.
</details>
