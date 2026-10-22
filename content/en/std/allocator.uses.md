---
title: uses_allocator and uses-allocator construction
summary: "How a container passes its allocator to the constructors of its elements: the allocator_arg tag, the uses_allocator trait, the leading and trailing conventions, and the member-wise treatment of pair."
updated: 2026-10-19
---

!!! tldr
    - Uses-allocator construction is a convention: when a container constructs an element whose type uses a compatible allocator, it also passes the container's allocator to the element's constructor.
    - Whether an element uses an allocator is decided by `uses_allocator<T, Alloc>`, which by default checks whether `T::allocator_type` is convertible from `Alloc`.
    - There are two ways to pass the allocator: the leading convention `T(allocator_arg, alloc, args...)` is preferred, then the trailing convention `T(args..., alloc)`; a type that claims to use an allocator but supports neither makes the program ill-formed.
    - `pair` does not use an allocator itself, but uses-allocator construction goes through it, passing the allocator to `first` and `second` separately.
    - Only the `construct` of allocators like `polymorphic_allocator` and `scoped_allocator_adaptor` follows this convention; `std::allocator` does not.

## The allocator has to reach the elements

```cpp run ok
#include <cassert>
#include <memory_resource>
#include <string>
#include <utility>
#include <vector>

using S = std::pmr::string;

int main() {
  std::pmr::monotonic_buffer_resource mr;
  std::pmr::vector<std::pair<S, S>> v(&mr);
  v.emplace_back("a string long enough to avoid SSO",
                 "another string long enough to avoid SSO");
  // the allocator goes through pair to first and second separately
  assert(v[0].first.get_allocator().resource() == &mr);
  assert(v[0].second.get_allocator().resource() == &mr);

  std::vector<std::pair<S, S>> w;   // the outer container uses std::allocator
  w.emplace_back("x", "y");
  assert(w[0].first.get_allocator().resource() ==
         std::pmr::get_default_resource());
}
```

`v`'s buffer comes from `mr`, and so does the character buffer of each string. `emplace_back` was given only two string literals and no allocator; `v`'s allocator passed itself in automatically when constructing the element. The point of an arena allocator is locality and bulk release, and if the elements each allocated from the global heap, that point would be only half achieved.

`w` uses `std::allocator`, whose `construct` just does a plain `construct_at`, so the strings in its elements use the default resource.

This automatic passing convention is called **uses-allocator construction** ([[g:uses-allocator-construction]]). It has three parts: a tag type `allocator_arg_t`, a trait `uses_allocator`, and a set of functions that rewrite the constructor arguments. It is carried out by `polymorphic_allocator::construct` ([[mem.poly.allocator.class]]) and `scoped_allocator_adaptor::construct` ([[allocator.adaptor]]); the `allocator_arg_t` constructors of types such as `tuple` also use it to construct their elements.

## The tag `allocator_arg_t` [allocator.tag]

```cpp
struct allocator_arg_t { explicit allocator_arg_t() = default; };
inline constexpr allocator_arg_t allocator_arg{};
```

¶1 `allocator_arg_t` is an empty class used as a unique type to disambiguate constructor overloads. Types such as `tuple` have constructors whose first parameter is `allocator_arg_t`, followed by an allocator parameter.

The tag is needed because argument types alone cannot tell the cases apart. `tuple<A, B>` has a constructor `tuple(const A&, const B&)`; if `A` happens to be an allocator type, an allocator in first position cannot be distinguished from an ordinary first element. Putting a dedicated type in front removes the ambiguity.

The default constructor is `explicit`, so `{}` cannot be implicitly converted to the tag:

```cpp run error
#include <memory>
void f(std::allocator_arg_t);
void g() {
  f(std::allocator_arg);   // OK
  f({});                   // error: the tag cannot be implicitly constructed from {}
}
```

Otherwise a call meant to pass `{}` as an empty first element might silently select the overload taking an allocator. Tags such as `in_place_t` and `nullopt_t` are designed the same way.

## The trait `uses_allocator` [allocator.uses.trait]

¶1 If `T::allocator_type` exists and denotes a type, and `is_convertible_v<Alloc, T::allocator_type>` is true, `uses_allocator<T, Alloc>` derives from `true_type`; otherwise it derives from `false_type`.

A program may specialize it as `true_type` for a program-defined type ([[g:program-defined-type]]) that has no `allocator_type` member but can in fact accept an allocator in one of two ways:

- ¶1.1 a constructor whose first argument type is `allocator_arg_t` and whose second is `Alloc`; this is the **leading-allocator convention**;
- ¶1.2 a constructor whose last argument type is `Alloc`; this is the **trailing-allocator convention**.

`std::tuple` in the standard library is such a type: it has no `allocator_type`, but the standard specializes `uses_allocator` as `true_type` for it.

## Uses-allocator construction [allocator.uses.construction]

### Definition and the three cases (¶1–¶3)

¶1 Uses-allocator construction of a type `T` with allocator `alloc` and arguments `args...` means: if `T` uses an allocator compatible with `alloc`, pass `alloc` to `T`'s constructor. The effect is equivalent to initializing the object with the value of `make_obj_using_allocator<T>(alloc, args...)`.

¶2 There are three cases, checked in order:

1. `T` does not use a compatible allocator: `alloc` is ignored;
2. otherwise, if `T(allocator_arg_t{}, alloc, args...)` can be called: the leading convention is used;
3. otherwise, if `T(args..., alloc)` can be called: the trailing convention is used.

¶3 `uses_allocator_construction_args` takes an allocator and an argument list and returns the rewritten argument list packed in a `tuple`. It has dedicated overloads for `pair` that apply uses-allocator construction to `first` and `second` separately. `make_obj_using_allocator` and `uninitialized_construct_using_allocator` construct a `T` from the rewritten arguments; the former returns a value, the latter constructs at a given address. Note 1 reminds that `T` cannot be deduced and must be written explicitly in the call.

```cpp run ok
#include <cassert>
#include <memory>
#include <memory_resource>
#include <string>
#include <utility>
#include <vector>

using Alloc = std::pmr::polymorphic_allocator<>;

struct Leading {   // leading convention
  using allocator_type = Alloc;
  Leading(std::allocator_arg_t, const Alloc& a, int x)
      : alloc(a), v(x) {}
  Alloc alloc;
  int v;
};

struct Trailing {  // trailing convention
  using allocator_type = Alloc;
  Trailing(int x, const Alloc& a = {}) : alloc(a), v(x) {}
  Alloc alloc;
  int v;
};

int main() {
  std::pmr::monotonic_buffer_resource mr;
  Alloc pa(&mr);

  static_assert(std::uses_allocator_v<Leading, Alloc>);
  auto l = std::make_obj_using_allocator<Leading>(pa, 1);   // Leading(allocator_arg, pa, 1)
  auto t = std::make_obj_using_allocator<Trailing>(pa, 2);  // Trailing(2, pa)
  assert(l.alloc.resource() == &mr);
  assert(t.alloc.resource() == &mr);
}
```

These functions were added in C++20 by [[P0591R4]]. Before that, `scoped_allocator_adaptor::construct` and `polymorphic_allocator::construct` each described this logic in a long, nearly identical passage, and each needed several separate `construct` overloads for `pair`; now both delegate to `uses_allocator_construction_args`.

### Rewriting rules for ordinary types (¶4–¶5)

¶4 This overload requires that `remove_cv_t<T>` is not a specialization of `pair`.

¶5 The return value is determined by the table below, where `UA` stands for `uses_allocator_v<remove_cv_t<T>, Alloc>`:

| | Condition | Returns |
|---|---|---|
| ¶5.1 | `UA` is false and `is_constructible_v<T, Args...>` | `forward_as_tuple(std::forward<Args>(args)...)` |
| ¶5.2 | `UA` is true and `is_constructible_v<T, allocator_arg_t, const Alloc&, Args...>` | `tuple<allocator_arg_t, const Alloc&, Args&&...>(allocator_arg, alloc, args...)` |
| ¶5.3 | `UA` is true and `is_constructible_v<T, Args..., const Alloc&>` | `forward_as_tuple(args..., alloc)` |
| ¶5.4 | Otherwise | The program is {{ill-formed}} |

The purpose of ¶5.4 is given in Note 2: to prevent the allocator from silently not being passed. A type that claims through `allocator_type` to use an allocator but has no constructor accepting one is most likely a mistake. Rather than falling back to construction without the allocator and letting the element allocate from the global heap, it is better to report an error.

```cpp run error
#include <memory>
#include <memory_resource>
struct Liar {
  using allocator_type = std::pmr::polymorphic_allocator<>;
  Liar(int) {}   // no constructor accepting an allocator
};
std::pmr::polymorphic_allocator<> pa;
auto x = std::make_obj_using_allocator<Liar>(pa, 1);   // error: ¶5.4
```

libc++ reports this error with a `static_assert` whose message is "If uses_allocator_v<Type> is true, the type has to be allocator-constructible".

### Handling `pair` (¶6–¶22)

`pair` has no `allocator_type` and no `uses_allocator` specialization; it does not use an allocator itself, but its members may. So all the `pair` overloads end up as **piecewise construction**: the arguments for `first` and `second` are rewritten separately. These overloads all require `remove_cv_t<T>` to be a specialization of `pair`, so constructing a `const pair<A, B>` takes this path too ([[LWG3677]]).

| Paragraphs | Argument form | Rewritten as |
|---|---|---|
| ¶6–¶8 | `(alloc, piecewise_construct, x, y)` | Recursively apply `uses_allocator_construction_args<T1>` to the elements of `x` and `<T2>` to `y`, returning `make_tuple(piecewise_construct, new x, new y)` |
| ¶9–¶10 | `(alloc)` | Two empty `tuple`s |
| ¶11–¶12 | `(alloc, u, v)` | `forward_as_tuple(u)` and `forward_as_tuple(v)` |
| ¶13–¶16 | `(alloc, pr)`, where `pr` is an lvalue or rvalue `pair<U, V>` | Take `first` and `second` out separately |
| ¶17–¶18 | `(alloc, p)`, where `p` satisfies `pair-like` but is not a `ranges::subrange` | Split with `get<0>` and `get<1>` ([[LWG3821]]) |
| ¶19–¶22 | `(alloc, u)`, where `u` cannot be split | See below |

The last case handles objects that are convertible to `pair` but are neither a `pair` nor `pair-like`, such as a class with `operator pair<A, B>()`. The constraint in ¶20 uses an exposition-only function template `FUN(const pair<A, B>&)` to exclude `pair` and classes derived from it, which are handled by the overloads above; `ranges::subrange`, although it satisfies `pair-like`, also takes this path.

Such a `u` cannot be split and passed to the two members separately. The solution in ¶21 is to return a proxy object: the exposition-only class `pair-constructor` holds `alloc` and a reference to `u`, and provides a conversion function to `pair`. ¶22 returns `make_tuple(pc)`.

The conversion function is called only when the target object is finally initialized from `pc`. It first converts `u` to a temporary `pair`, then calls `make_obj_using_allocator` on that temporary, i.e. recursively takes the path for construction from a `pair` rvalue. This way the conversion is deferred to the moment of construction, and the returned `tuple` holds only a cheap proxy.

### The two construction functions (¶23–¶24)

¶23 `make_obj_using_allocator<T>(alloc, args...)` is equivalent to `make_from_tuple<T>(uses_allocator_construction_args<T>(alloc, args...))`.

¶24 `uninitialized_construct_using_allocator(p, alloc, args...)` is equivalent to expanding the rewritten arguments with `apply` and handing them to `construct_at(p, ...)`. This is exactly what `polymorphic_allocator::construct` does.

## Questions

!!! question "Question 1"
    A type has both `T(allocator_arg_t, const A&, int)` and `T(int, const A&)`. Which one does uses-allocator construction choose?

<details markdown="1">
<summary>Answer</summary>

The leading form. ¶5.2 is checked before ¶5.3, and as long as `is_constructible_v<T, allocator_arg_t, const Alloc&, Args...>` holds, the trailing form is never considered.
</details>

!!! question "Question 2"
    In `std::pmr::vector<std::pmr::vector<int>>`, do the inner vectors allocate from the outer resource? What about `std::vector<std::pmr::vector<int>>`?

<details markdown="1">
<summary>Answer</summary>

The former does. The outer `polymorphic_allocator::construct` performs uses-allocator construction on the elements; the `allocator_type` of `pmr::vector<int>` is `polymorphic_allocator<int>`, which is convertible from `polymorphic_allocator<pmr::vector<int>>`, so the outer resource is passed in by the trailing convention.

The latter does not. The outer container uses `std::allocator`, whose `allocator_traits` `construct` just calls `construct_at` and performs no uses-allocator construction. The inner vectors use a default-constructed `polymorphic_allocator`, i.e. the resource returned by `get_default_resource()`.
</details>
