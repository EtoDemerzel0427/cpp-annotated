---
title: Reflection queries
summary: "Given a std::meta::info, ask what it is, what it is called, what its type and value are, what it belongs to, what members it has, how it is laid out in memory, and what annotations it carries."
updated: 2026-10-19
---

!!! tldr
    - The query functions in `<meta>` are all `consteval` functions: the parameter is a reflection, and the result is a `bool`, a string, another reflection, or a `vector` of reflections; when not applicable they throw `std::meta::exception`, while the `is_*` predicates never throw.
    - Query results depend on where the evaluation happens: which declarations are reachable and whether a class is complete are judged from the program points visible to this constant evaluation.
    - `members_of`, `bases_of` and friends must be given an `access_context`: `current()` filters by the access rights at the call site, and only `unchecked()` sees private members.
    - The type reflections returned by `template_arguments_of` and `type_of` always have aliases stripped; to compare types, use `dealias` or `is_same_type`, not `==` directly.
    - `offset_of` and `size_of` can give the bit offset of bit-fields and the offset of base class subobjects; for reference types, `size_of` returns the size of a pointer, unlike `sizeof`.

!!! note "About the examples on this page"
    Clang 23 does not support C++26 reflection yet (no `^^` operator and no `<meta>`). The code on this page is written from the current draft and the standard's own examples, has not been compiled, and therefore carries no verdict. For brevity, most examples omit `#include <meta>` and `using namespace std::meta;`.

## An example: printing every field of a struct

```cpp
#include <meta>
#include <print>

struct Point { int x; int y; };

template<class T>
void dump(const T& obj) {
  constexpr auto ctx = std::meta::access_context::current();
  template for (constexpr auto m :
      std::define_static_array(std::meta::nonstatic_data_members_of(^^T, ctx)))
    std::println("{} = {}", std::meta::identifier_of(m), obj.[:m:]);
}

int main() { dump(Point{1, 2}); }   // prints x = 1 and y = 2
```

`^^T` yields the reflection of type `T` ([[expr.reflect]]), a value of type `std::meta::info`. `nonstatic_data_members_of` returns reflections of `T`'s non-static data members, `identifier_of` gets a member's name, and `obj.[:m:]` uses a splice ([[basic.splice]]) to turn the reflection back into a member access. `define_static_array` turns the compile-time `vector` into a static array so that `template for` can expand it element by element (see [[meta.reflection]]).

Every function on this page, like `nonstatic_data_members_of` and `identifier_of` here, takes a reflection and answers a question about it. They are all in namespace `std::meta`, all `consteval`, and can only be called during constant evaluation. When a function is not applicable (for example, asking a type for its value), it throws `std::meta::exception`, and an exception not caught during constant evaluation makes the evaluation fail.

A reflection can represent many kinds of things: values, objects, variables, functions, types, type aliases, namespaces, templates, concepts, enumerators, non-static data members, function parameters, annotations, and two constructs that correspond to no declaration: a **direct base class relationship** `(D, B)`, meaning class `D` has `B` as a direct base; and a **data member description** ([[g:data-member-description]]) produced by `data_member_spec`. The full list is in [[basic.fundamental#17]].

## What is it: kind predicates [meta.reflection.queries]

```cpp
int v;
using Int = int;
template<class T> struct Box {};

static_assert(is_variable(^^v));
static_assert(is_type(^^Int) && is_type_alias(^^Int));
static_assert(is_template(^^Box) && is_class_template(^^Box));
static_assert(!is_template(^^Box<int>));   // a specialization of a template is not a template (Note 5)
```

¶11 From paragraph 11 through paragraph 49, most functions are specified with the same sentence pattern: return `true` if `r` represents some kind of thing, and `false` otherwise. These predicates never throw and can safely be called on any reflection. Grouped by topic:

| Topic | Functions |
|---|---|
| Kind of entity | `is_variable`, `is_type`, `is_namespace`, `is_type_alias`, `is_namespace_alias`, `is_function`, `is_value`, `is_object`, `is_structured_binding`, `is_enumerator`, `is_annotation` |
| Templates | `is_template`, `is_function_template`, `is_variable_template`, `is_class_template`, `is_alias_template`, `is_concept`, plus template versions for conversion functions, operator functions, literal operators and constructors |
| Membership | `is_class_member`, `is_namespace_member`, `is_nonstatic_data_member`, `is_static_member`, `is_base`, `is_bit_field`, `is_mutable_member`, `has_default_member_initializer` |
| Access specifiers | `is_public`, `is_protected`, `is_private` (class members, unnamed bit-fields, direct base class relationships) |
| Virtual functions | `is_virtual` (virtual member function or virtual base relationship), `is_pure_virtual`, `is_override`, `is_final` (final class or final member function) |
| How a function is defined | `is_deleted`, `is_defaulted`, `is_user_provided`, `is_user_declared`, `is_explicit`, `is_noexcept` |
| Special functions | `is_special_member_function`, `is_constructor`, `is_default_constructor`, `is_copy_constructor`, `is_move_constructor`, `is_assignment`, `is_copy_assignment`, `is_move_assignment`, `is_destructor`, `is_conversion_function`, `is_operator_function`, `is_literal_operator` |
| Parameters | `is_function_parameter`, `is_explicit_object_parameter`, `has_default_argument`, `is_vararg_function` |
| Qualifiers | `is_const`, `is_volatile`, `is_lvalue_reference_qualified`, `is_rvalue_reference_qualified` |
| Storage duration | `has_static_storage_duration`, `has_thread_storage_duration`, `has_automatic_storage_duration` |
| Linkage | `has_internal_linkage`, `has_module_linkage`, `has_external_linkage`, `has_linkage`, `has_c_language_linkage` |
| Completeness | `is_complete_type`, `is_enumerable_type` |

A few are easy to misunderstand:

- ¶17 `is_explicit` and `is_noexcept` are always `false` for templates. `explicit(expr)` and `noexcept(expr)` on a template generally depend on the template arguments and cannot be answered before a specialization is obtained (Notes 1 and 2).
- ¶21 `is_const` and `is_volatile` first check whether `r` has a type: for variables, members, values and so on they look at `type_of(r)`; for a type they look at the type itself (with aliases removed). So both the reflection of a `const int` variable and the reflection of the type `const int` give `true`. ¶22 The `const`-qualified function type `void() const` also gives `true`, unlike `std::is_const_v`.
- ¶26 There is `has_automatic_storage_duration` but no version for dynamic storage duration: a reflection can never represent an object or variable with dynamic storage duration (Note 3).
- ¶29 `is_complete_type(r)` returns `true` as long as the type is complete at some point in the evaluation context. What evaluation context means is explained below.

## Types, objects and constant values [meta.reflection.queries]

### `type_of` (¶1–¶3)

¶2 `type_of(r)` returns the type of what `r` represents. Some special cases:

- for a function parameter, it returns the type in the parameter-type-list, i.e. the type after adjustments such as array-to-pointer ([[dcl.fct]]);
- for an annotation, the type of its constant value;
- for a direct base class relationship `(D, B)`, `B`;
- for an enumerator, outside the enumeration definition the enumeration type itself; inside the *enum-specifier* (i.e. within the enumeration's braces) the type the enumerator has at that point, which may be the underlying integer type rather than the enumeration ([[dcl.enum]]).

¶1 Reflections whose type can be asked are: values, annotations, objects, variables, enumerators, non-static data members, unnamed bit-fields, direct base class relationships, data member descriptions, function parameters, and functions other than constructors and destructors whose type contains no undeduced placeholder (such as an `auto` return type not yet deduced). ¶3 Calling `type_of` on any other reflection throws.

### `object_of`: a variable and its object (¶4–¶6)

```cpp
int x;
int& y = x;
static_assert(^^x != ^^y);                          // two different variables
static_assert(object_of(^^x) == object_of(^^y));    // the same object
```

¶4 Variables and objects are different things: a variable is a name introduced by a declaration, an object is a region of typed storage. `object_of` goes from a variable (or reference) to the object, and returns objects unchanged. ¶5 It only accepts objects with static storage duration; if `r` represents a reference variable, that reference must also be usable in constant expressions or have begun its lifetime during the current constant evaluation.

### `constant_of`: getting the value out (¶7–¶10)

```cpp
constexpr int a = 0, b = 0;
static_assert(^^a != ^^b);                              // two variables
static_assert(constant_of(^^a) == constant_of(^^b));    // the same value 0
static_assert(constant_of(^^a) == reflect_constant(0));
```

¶8 `constant_of(r)` returns the underlying constant for an annotation; for other reflections it first splices `r` into the expression `[: r :]`, then hands it to `reflect_constant_array` (arrays), `reflect_function` (functions) or `reflect_constant` (everything else) according to its type. ¶9 It throws if `[: r :]` is not a valid splice expression.

For class types, the result is the **template parameter object** that is template-argument-equivalent ([[g:template-argument-equivalent]]) to the original object, not the original object:

```cpp
struct S { int m; };
constexpr S s {42};
static_assert(constant_of(^^s) != reflect_object(s));                // different objects
static_assert(constant_of(^^s) == constant_of(reflect_object(s)));   // the same template parameter object

consteval info fn() { constexpr int x = 42; return ^^x; }
constexpr info r = constant_of(fn());   // error: x is outside its lifetime
```

The rules for `reflect_constant` and `reflect_object` are in [[meta.reflection.extract]].

## Names and source locations [meta.reflection.names]

### What has a name (¶1)

```cpp
struct S { S(); int operator+(int); };
static_assert(has_identifier(^^S));
static_assert(!has_identifier(^^int));                 // built-in types have no identifier
static_assert(!has_identifier(^^std::vector<int>));    // neither do template specializations
static_assert(identifier_of(^^S) == "S");
```

¶1 `has_identifier(r)` tells whether `r` has an identifier that can be returned, specified case by case by the kind of reflection:

| The reflection represents | Condition for `has_identifier` to be `true` |
|---|---|
| An entity with a typedef name for linkage purposes (`typedef struct {} T;`) | Always |
| An unnamed entity | Never |
| A type alias | Not a specialization of an alias template |
| A type | A cv-unqualified class type that is not a template specialization, or a cv-unqualified enumeration type |
| A function | Not a template specialization, and not a constructor, destructor, operator function or conversion function |
| A template | Not a constructor template, operator function template or conversion function template |
| A variable | Not instantiated from a function parameter pack, and not a template specialization |
| A structured binding | Not instantiated from a structured binding pack |
| An enumerator, non-static data member, namespace or namespace alias | Always |
| A direct base class relationship | Depends on the base class type |
| A data member description | Has a name |
| A function parameter | See the next section |

¶3 `identifier_of(r)` returns this identifier, and `u8identifier_of(r)` the UTF-8 version (¶2). An entity with a typedef name for linkage purposes returns that typedef name, a literal operator returns its *ud-suffix* (such as `_km`), and a direct base class relationship returns the name of the base. ¶4 It throws if `has_identifier(r)` is false or the name cannot be represented in the target encoding.

### Parameter names: the result depends on where you ask (¶1.7–¶1.8)

C++ allows different declarations of the same function to give a parameter different names, or none. ¶1.8 specifies that a parameter has an identifier if and only if, among all reachable declarations, at least one names it and no declaration uses a different name:

```cpp
void fun(int);
constexpr std::meta::info r = parameters_of(^^fun)[0];
static_assert(!has_identifier(r));     // so far no declaration gives a name

void fun(int x);
static_assert(has_identifier(r));      // now there is x

void fun(int x);
static_assert(has_identifier(r));      // same name, still consistent

void poison() {
  void fun(int y);                     // a block-scope declaration uses another name
}
static_assert(!has_identifier(r));     // inconsistent names: no identifier
```

The same `r` gets different answers at different places in the file. The reason is that queries judge which declarations are reachable by the **evaluation context** ([[g:evaluation-context]], [[expr.const.reflect]]): roughly, the program point where the current constant evaluation occurs, plus the points visible from its instantiation context. `is_complete_type`, `members_of` and `annotations_of` below follow the same rule.

¶1.7 Another rule: a parameter of a function template specialization that comes from a parameter pack (such as some `ts` of `template<class... Ts> void f(Ts... ts)`) has no identifier.

### `display_string_of` and `source_location_of` (¶5–¶8)

¶5 `display_string_of(r)` can be called on any reflection and returns an implementation-defined string. ¶6 The recommended practice is to return text suitable for identifying the construct, such as `std::vector<int>`. It is suitable for diagnostics and logs, but not for program logic, because the contents are not portable.

¶7 `source_location_of(r)` returns an empty `source_location{}` for values, types that are neither classes nor enumerations, the global namespace and data member descriptions, and an implementation-defined location otherwise. ¶8 It is recommended to return the location of a reachable definition.

## Navigating the program structure [meta.reflection.queries]

### The parent: `parent_of` (¶50–¶53)

```cpp
struct I { };
struct F : I {
  union { int o; };
  enum N { A };
};
constexpr auto ctx = std::meta::access_context::current();

static_assert(parent_of(^^F) == ^^::);
static_assert(parent_of(bases_of(^^F, ctx)[0]) == ^^F);
static_assert(is_union_type(parent_of(^^F::o)));
static_assert(parent_of(^^F::N) == ^^F);
static_assert(parent_of(^^F::A) == ^^F::N);
```

¶51 The parent is generally the innermost class, function or namespace enclosing the declaration. There are three exceptions: the parent of a member of an anonymous union is that anonymous union; the parent of an enumerator is its enumeration type (even for an unscoped enumeration); the parent of a direct base class relationship `(D, B)` is `D`.

¶50 `has_parent(r)` returns `false` for the global namespace, entities with C language linkage, and types that are neither classes nor enumerations. ¶52 Calling `parent_of` on these throws.

### Stripping aliases: `dealias` (¶54–¶55)

```cpp
using X = int;
using Y = X;
static_assert(^^Y != ^^int);            // the reflection of an alias does not equal that of the type
static_assert(dealias(^^Y) == ^^int);   // aliases of aliases are stripped all the way down
```

¶54 `dealias` replaces type aliases and namespace aliases with the entities they denote, and returns other reflections unchanged. `==` on reflections compares the represented constructs themselves, and an alias and a type are two different constructs, so you usually need to `dealias` before comparing types.

### Templates and template arguments (¶56–¶61)

```cpp
template<class T, class U = T> struct Pair { };
template<class T> using PairPtr = Pair<T*>;

static_assert(template_of(^^Pair<int>) == ^^Pair);
static_assert(template_arguments_of(^^Pair<int>).size() == 2);   // default arguments count too
static_assert(template_of(^^PairPtr<int>) == ^^PairPtr);         // a specialization of an alias template
static_assert(template_arguments_of(^^PairPtr<int>).size() == 1);

struct S { };
int i;
template<int, int&, S, template<class> class> struct X { };
constexpr auto T = ^^X<1, i, S{}, PairPtr>;
static_assert(is_value(template_arguments_of(T)[0]));     // 1: a value
static_assert(is_object(template_arguments_of(T)[1]));    // i: an object
static_assert(is_object(template_arguments_of(T)[2]));    // S{}: a template parameter object
static_assert(template_arguments_of(T)[3] == ^^PairPtr);
```

¶56 `has_template_arguments(r)` tells whether `r` is a specialization of a function template, variable template, class template or alias template. ¶57 `template_of` returns its template, and ¶59 `template_arguments_of` returns reflections of the template arguments in order:

- type arguments always represent types, never aliases (Note 7);
- template template arguments represent the template;
- among constant arguments, a parameter of reference type gives the referenced object or function, a parameter of class type gives the template parameter object, and anything else gives a value.

### Parameters and return types (¶62–¶67)

¶62 `parameters_of(r)` returns reflections of each parameter for a function, and of each type in the parameter-type-list for a function type. ¶66 `return_type_of(r)` returns the return type of a function or function type.

¶64 `variable_of(r)` turns the reflection of a parameter into the reflection of the **parameter variable**. A parameter belongs to the function's declarations and may have a different name in each declaration; a parameter variable belongs to the function definition and is what the function body uses. ¶65 So `variable_of` can only be called within the function body of that function (precisely, within its function parameter scope).

## Access control [meta.reflection.access.context]

### Why member queries need an access context

```cpp
class Account {
  int balance;
public:
  int id;
};
// at namespace scope:
static_assert(nonstatic_data_members_of(^^Account,
                access_context::current()).size() == 1);     // only id
static_assert(nonstatic_data_members_of(^^Account,
                access_context::unchecked()).size() == 2);   // balance included
```

If reflection could list private members unconditionally, access control would be meaningless. So functions like `members_of` all require the caller to give an **access context** ([[g:access-context]]) explicitly. The default spelling `current()` is subject to access control just like ordinary code; to bypass it you must write `unchecked()`, which stands out in code review.

### `access_context` (¶1–¶11)

```cpp
struct access_context {
  access_context() = delete;
  consteval info scope() const;
  consteval info designating_class() const;
  static consteval access_context current() noexcept;
  static consteval access_context unprivileged() noexcept;
  static consteval access_context unchecked() noexcept;
  consteval access_context via(info cls) const;
};
```

¶1 An access context consists of two parts: a scope, i.e. the namespace, class or function from which access checking is done; and an optional **designating class** ([[g:designating-class]]), i.e. the class through which a member is accessed ([[class.access.base]]), like the `T` in `p->T::m`.

| Construction | Scope | Designating class | Effect |
|---|---|---|---|
| `current()` | The function, class or namespace enclosing the call | Null reflection | Same as ordinary code written at the call site |
| `unprivileged()` | The global namespace | Null reflection | Only public members accessible |
| `unchecked()` | Null reflection | Null reflection | No access checking |
| `ctx.via(cls)` | Same as `ctx` | `cls` | Specifies the class through which members are accessed |

¶3 `access_context` is a structural type and can be used as a constant template argument. ¶6 `current()`, like `current_function()` below, takes information from the call site and cannot have its address taken; in a template it is value-dependent ([[g:value-dependent]]), and each specialization gets its own result. ¶11 `via(cls)` requires `cls` to be a null reflection or a complete class type.

### `is_accessible` ([meta.reflection.access.queries])

```cpp
consteval access_context fn() { return access_context::current(); }

class Cls {
  int mem;
  friend consteval access_context fn();
public:
  static constexpr auto r = ^^mem;
};

static_assert( is_accessible(Cls::r, fn()));                        // in the friend function
static_assert(!is_accessible(Cls::r, access_context::current()));   // at namespace scope
static_assert( is_accessible(Cls::r, access_context::unchecked()));
```

`is_accessible(r, ctx)` answers: starting from `ctx`'s scope and going through `ctx`'s designating class, can `r` be accessed? The steps:

1. A reflection that is neither a class member nor a direct base class relationship is always accessible. Unnamed bit-fields are treated as data members with the same access.
2. If `r` is not a member of the designating class at all (when no designating class is given, the class `r` belongs to is used), it is not accessible.
3. If the scope is null (`unchecked()`), it is accessible.
4. Otherwise it is judged by the rules of [[class.access.base]], ignoring the effects of using-declarations and without considering whether declarations are reachable from that point (Note 2).

Paragraphs 6–10 also provide three summary functions: `has_inaccessible_nonstatic_data_members`, `has_inaccessible_bases` and `has_inaccessible_subobjects`. They list all members or bases with `unchecked()` and then check whether any is inaccessible under `ctx`. When writing generic code such as member-wise serialization or comparison, use them first to decide whether a class can be handled. Calling the first one on a closure type throws, because which members a closure has is up to the implementation.

## Listing members [meta.reflection.member.queries]

### What `members_of` returns

```cpp
class B {};
struct S : B {
private:
  class I;
public:
  int m;
};

static_assert(members_of(^^S, access_context::current()).size() == 7);     // 6 special members + m
static_assert(members_of(^^S, access_context::unchecked()).size() == 8);   // plus the private S::I
```

¶4 `members_of(r, ctx)` returns those members of a class or namespace that are accessible and representable, in declaration order. Note 2 adds two points: base classes are not members and are not in the result; implicitly declared special members come after all user-declared members. In the example, the six special members of `S` (default constructor, copy constructor, move constructor, copy assignment, move assignment, destructor) are all implicitly declared, so they come after `m`.

¶3 The following members do not appear in the result (Note 1):

- enumerators of unscoped enumerations (they are members of the enclosing scope, but are obtained through `enumerators_of`);
- specializations and partial specializations of templates;
- closure types (the types of lambdas);
- functions introduced by friend declarations;
- variant members inside nested anonymous unions;
- variables and functions whose types contain undeduced placeholders, functions whose constraints are not satisfied, and prospective destructors that were not selected.

¶5 `r`, after stripping aliases, must be a class that is complete from some point in the evaluation context, or a namespace; otherwise it throws. For classes, accessible unnamed bit-fields are included as well.

<details class="fine" markdown="1"><summary>The precise definition of members-of (¶1–¶3)</summary>

¶1 A declaration `D` *members-of-precedes* a point `P` if `D` precedes either `P` or the point immediately following the *class-specifier* of the outermost class for which `P` is in a complete-class context ([[g:complete-class-context]]).

¶2 A declaration `D` of a member `M` of a class or namespace `Q` is *Q-members-of-eligible* if and only if: the host scope of `D` is the scope of `Q`; `D` is not a friend declaration; `M` is not a closure type and not a template specialization; if `Q` is a non-closure class, `M` is a direct member of `Q` and not a variant member of a nested anonymous union; if `Q` is a closure type, `M` is a function call operator or its template. Whether other members of a closure are eligible is implementation-defined.

¶3 `M` is *Q-members-of-representable* from `P` if and only if it has an eligible declaration that members-of-precedes `P`, and `M` is a class or enumeration type, a type alias, a class template, function template, variable template, alias template or concept, a variable whose type contains no undeduced placeholder, a function meeting conditions such as satisfied constraints, a non-static data member, a namespace, or a namespace alias.

The example in ¶6 also shows the effect of modules: a `static int l;` with internal linkage in a module interface is not reachable in a translation unit that imports it, so `members_of(^^NS, ...)` there has one fewer element.

</details>

### Enumerable types ([meta.reflection.queries] ¶30–¶32)

```cpp
class S;
enum class E;
static_assert(!is_enumerable_type(^^S));
static_assert(!is_enumerable_type(^^E));

class S {
  void mfn() {
    static_assert(is_enumerable_type(^^S));    // a function body is a complete-class context
  }
  static_assert(!is_enumerable_type(^^S));     // elsewhere inside the class definition
};
static_assert(is_enumerable_type(^^S));

enum class E {
  A = is_enumerable_type(^^E) ? 1 : 2          // inside the enum-specifier: not enumerable
};
static_assert(is_enumerable_type(^^E));
static_assert(static_cast<int>(E::A) == 2);
```

¶30 Before listing members, it must be established that all members have been declared. A type `T` is **enumerable** ([[g:enumerable-type]]) from a point `P` if it is a class type complete at `P`, or an enumeration type whose definition is reachable from `P` while `P` is not inside the braces of that definition. `members_of` requires the class to be complete, and `enumerators_of` requires the enumeration to be enumerable.

### Convenience functions (¶7–¶16)

| Function | Returns |
|---|---|
| `bases_of(type, ctx)` | The accessible direct base class relationships, in *base-specifier-list* order |
| `static_data_members_of(type, ctx)` | The variables in `members_of` |
| `nonstatic_data_members_of(type, ctx)` | The non-static data members in `members_of` |
| `subobjects_of(type, ctx)` | `bases_of` first, then `nonstatic_data_members_of` |
| `enumerators_of(type_enum)` | All enumerators, in declaration order; no access context, since enumerators have no access control |

## Where am I: scope identification [meta.reflection.scope]

```cpp
consteval info current_function();
consteval info current_class();
consteval info current_namespace();
```

¶1 These three functions return the function, class and namespace enclosing the place where they are called. ¶2 So none of them can have its address taken: an indirect call through a function pointer has no call site to speak of.

```cpp
consteval std::string_view caller_name(
    std::meta::info f = std::meta::current_function()) {
  return std::meta::identifier_of(f);
}

void work() {
  static_assert(caller_name() == "work");   // not "caller_name"
}
```

¶3 `current_function()` in a default argument is evaluated at the location where `caller_name` is called, so it gives the caller `work`. Reflection values can only exist during constant evaluation, so a function with an `info` parameter has to be declared `consteval` ([[expr.const.const]]). This is the same idea as using `std::source_location::current()` as a default argument. ¶3 uses *eval-point* to specify precisely where the call site is; the other special locations are:

- in a default member initializer: evaluated at the aggregate initialization that uses it, or at the constructor that uses it (for an inheriting constructor, the class scope);
- in the parameter list of a function declaration or in a trailing *requires-clause*: evaluated in the enclosing scope of the function declaration;
- in a lambda's trailing return type or trailing *requires-clause*: evaluated at the point of the lambda introducer;
- inside a `consteval` block ([[dcl.pre]]): evaluated in the scope of the outermost `consteval` block.

¶5 From the resulting location it then looks outward for the nearest function, class or namespace. ¶8 `current_function()` throws when that is not a function; ¶12 `current_class()` returns the class in a class, or the class a member function belongs to in a member function, and ¶13 throws otherwise; ¶16 `current_namespace()` returns the nearest enclosing namespace. ¶6 In templates all three are value-dependent, and each specialization gets its own result.

## Layout [meta.reflection.layout]

```cpp
struct member_offset {
  ptrdiff_t bytes;
  ptrdiff_t bits;
  constexpr ptrdiff_t total_bits() const;      // bytes * CHAR_BIT + bits
  auto operator<=>(const member_offset&) const = default;
};
consteval member_offset offset_of(info r);
consteval size_t size_of(info r);
consteval size_t alignment_of(info r);
consteval size_t bit_size_of(info r);
```

```cpp
struct Flags {
  unsigned a : 3;
  unsigned b : 5;
};
static_assert(offset_of(^^Flags::b).total_bits() == 3);   // so on common ABIs
static_assert(bit_size_of(^^Flags::b) == 5);
```

How bit-fields are arranged within an allocation unit is implementation-defined ([[class.bit]]), so the result of the first assertion depends on the ABI; the width 5 is certain.

¶2 `offset_of(r)` computes the bit offset `V` from the start of a complete object of type `parent_of(r)` to the subobject corresponding to `r`, and ¶3 returns `{V / CHAR_BIT, V % CHAR_BIT}`. Compared with the `offsetof` macro, it handles bit-fields (giving bit-level offsets) and base class subobjects, and does not require the class to be standard-layout. ¶4 It applies to non-static data members, unnamed bit-fields and direct base class relationships, except virtual base relationships of abstract classes.

¶5 `size_of(r)` returns `sizeof` for a type, the `sizeof` of its type for a non-static data member or data member description, and `size_of(type_of(r))` for anything else with a type. For a reference type `T&` it returns `size_of(^^T*)`, the size of a pointer, roughly the space a reference occupies as a member; whereas `sizeof(T&)` is `sizeof(T)`. Note 1 also points out that a direct base class relationship `b` with an empty base has `size_of(b) > 0` too: what is returned is the `sizeof` of the base class type, not the space it actually occupies in the derived class. ¶6 Calling `size_of` on a bit-field or an incomplete type throws.

¶7 `alignment_of(r)` returns the alignment requirement for a type (references again counted as pointers), takes `alignas` into account for a variable or object, returns the actual alignment within the complete object for a non-static data member, and returns the alignment value in a data member description (or the type's alignment if there is none).

¶9 `bit_size_of(r)` returns the width for a bit-field, and `CHAR_BIT * size_of(r)` otherwise.

## Annotations [meta.reflection.annotation]

Annotations ([[g:annotation]]) are the new C++26 `[[=expr]]` syntax ([[dcl.attr.annotation]], [[P3394R4]]): they attach a constant value to a declaration for reflection to read, without affecting any other semantics of the program.

```cpp
struct Option { bool value; };
struct C {
  [[=Option{true}]] int a;
  [[=Option{false}]] int b;
};
static_assert(extract<Option>(annotations_of(^^C::a)[0]).value);
static_assert(!extract<Option>(annotations_of(^^C::b)[0]).value);
```

¶2 `annotations_of(item)` returns all annotations that apply to `item`:

- a function's annotations are collected from all its reachable declarations, and a function parameter's from that parameter in each declaration;
- a direct base class relationship takes the annotations on the corresponding *base-specifier*;
- any other entity takes the annotations on each of its reachable declarations.

¶2 The result is in order of appearance, with annotations from the same translation unit grouped together; the order between annotations from different translation units is unspecified (Note 1). ¶3 Annotations can be queried for types, type aliases, variables, functions, function parameters, namespaces, enumerators, direct base class relationships and non-static data members.

```cpp
[[=1]] void f();
[[=2, =3]] void g();
void g [[=4]] ();

static_assert(annotations_of(^^f).size() == 1);
static_assert(annotations_of(^^g).size() == 3);                 // annotations on both declarations count
static_assert([: constant_of(annotations_of(^^g)[0]) :] == 2);
static_assert(extract<int>(annotations_of(^^g)[2]) == 4);

template<class T> struct [[=42]] D { };
constexpr std::meta::info a1 = annotations_of(^^D<int>)[0];
constexpr std::meta::info a2 = annotations_of(^^D<char>)[0];
static_assert(a1 != a2);                                        // annotations on different specializations are different annotations
static_assert(constant_of(a1) == constant_of(a2));              // but with the same value

[[=1]] int x, y;
static_assert(annotations_of(^^x)[0] == annotations_of(^^y)[0]);   // the same annotation in the same declaration
```

¶5 `annotations_of_with_type(item, type)` keeps only annotations whose type is the same as `type` (ignoring top-level `const`). This is the most common usage: serialization frameworks use it to read field options, and command-line parsing libraries to read argument descriptions.

## Common misconceptions

!!! pitfall "Treating query results as globally fixed facts"
    The results of `has_identifier`, `is_complete_type`, `members_of` and `annotations_of` all depend on which declarations are reachable in the evaluation context. Storing a result in a `constexpr` variable gives a snapshot at that location, and declarations added later are not reflected in it.

!!! pitfall "Thinking `members_of` sees all members"
    When called outside the class with `access_context::current()`, private and protected members are filtered out, without any notice. When you need all members, use `unchecked()` explicitly, or check with `has_inaccessible_nonstatic_data_members` first.

!!! pitfall "Comparing types with `==`"
    `^^Int == ^^int` is `false` when `Int` is an alias for `int`. The results of `template_arguments_of` and `type_of` already have aliases stripped, but a `^^Int` you write yourself does not. `dealias` before comparing, or use `is_same_type` from [[meta.reflection.traits]].
