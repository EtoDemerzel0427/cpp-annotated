---
title: Views
summary: "span and mdspan are non-owning handles that only record where someone else's storage starts, how long it is and what shape to index it with; they divide the work with string_view and ranges views."
updated: 2026-10-19
---

!!! tldr
    - `span` and `mdspan` do not own their elements: their destructors do nothing, copying copies only a pointer and a length, and the lifetime of the storage they view is the caller's responsibility.
    - Their const is shallow: the elements of a `const span<int>` are still writable; for read-only access write `span<const int>`.
    - `span` is a one-dimensional contiguous view satisfying `ranges::view` and `borrowed_range`; `mdspan` is a multidimensional view and not a range.
    - Neither has `operator==`; both are trivially copyable types and are idiomatically passed by value.
    - `dynamic_extent` is the run-time extent marker shared by both, provided by both `<span>` and `<mdspan>`.

## One parameter that accepts any contiguous storage

```cpp run title="span-param.cpp" ok
#include <array>
#include <span>
#include <vector>

int sum(std::span<const int> s) {
  int t = 0;
  for (int x : s) t += x;
  return t;
}

int main() {
  int raw[] = {1, 2, 3};
  std::array<int, 2> arr{4, 5};
  std::vector<int> vec{6, 7, 8, 9};
  return sum(raw) + sum(arr) + sum(vec) - 45;   // returns 0
}
```

`sum` does not care whether the elements live in a built-in array, a `std::array` or a `std::vector`; it only needs a starting point and a length. `std::span` combines the `(const int* p, size_t n)` of a C interface into a single type.

The other class templates in the containers chapter ([[containers]]), `vector`, `deque`, `map` and so on, all allocate storage and construct and destroy elements. The two class templates in [views] do none of this; they are only given a block of storage **owned by someone else** and record where it starts, how long it is and what shape to index it with:

- `std::span<T, Extent>` ([[views.contiguous]]): one-dimensional and contiguous; its contents are a pointer plus a length.
- `std::mdspan<T, Extents, Layout, Accessor>` ([[views.multidim]]): multidimensional. Indices first go through a **layout mapping** to compute a one-dimensional offset, then through an **accessor** to obtain a reference to the element; both can be customized.

## Three conventions of views

The standard defines `span` in a single sentence:

!!! std
    A `span` is a view over a contiguous sequence of objects, the storage of which is owned by some other object.

The storage is owned by some other object. Three conventions follow from this, and they hold for `mdspan` as well.

**Non-owning.** The destructor does nothing, and copying just copies the pointer and length. Whether the storage it views is still alive is entirely the caller's responsibility. So `span<const int> s = make_vector();` compiles but dangles as soon as the statement ends; see the pitfalls section of [[views.contiguous]] and [[class.temporary]].

**Shallow const.** `const` qualifies only the view's own pointer and length, not the elements. This is the opposite of `const vector<int>`:

<div class="compare" markdown="1">

```cpp run ok
#include <span>
void f(const std::span<int> s) {
  s[0] = 1;   // OK: the elements are still writable
}
```

```cpp run error
#include <span>
void f(std::span<const int> s) {
  s[0] = 1;   // error: the elements are const
}
```

</div>

**Cheap to copy.** `span` is specified to be a trivially copyable type ([[span.overview#3]], [[basic.types.general]]). So is `mdspan` when its accessor, layout mapping and data handle are all trivially copyable ([[mdspan.mdspan.overview#5]]). Passing by value is the idiom: a dynamic-extent `span` takes only two machine words, which common ABIs pass in two registers, saving one indirection compared with passing `const span&`.

## How the views divide the work

| | `std::string_view` | `std::span<T>` | `std::mdspan` | ranges views (`views::filter` and so on) |
|---|---|---|---|---|
| Clause | [[string.view]] | [[views.contiguous]] | [[views.multidim]] | [[range.adaptors]] |
| Dimensions | 1 | 1 | Any (including 0) | 1 |
| Storage | Contiguous characters | Contiguous objects | Decided by layout and accessor | Any range |
| Elements writable | No | Decided by the const-ness of `T` | Decided by `T` and the accessor | Depends on the underlying range |
| Compile-time extent | None | Optional (`Extent`) | Optional per dimension | None |
| `ranges::view` / `borrowed_range` | Yes / yes | Yes / yes | Not a range | Yes / it depends |
| `operator==` | Yes, compares contents | No | No | It depends |

`string_view` is not an alias for `span<const char>`. It carries text semantics: it has `char_traits`, `find`, `substr` and `starts_with`, and `==` compares contents. `span<const char>` is just a run of bytes with no `==` (see [[views.contiguous]] for why). The two convert into each other: `string_view` is a contiguous, sized, borrowed range, so it converts implicitly to `span<const char>`; the other direction must be explicit, because `string_view`'s constructor from a range is `explicit`.

`span` satisfies `ranges::view` because [[span.syn]] specializes both `ranges::enable_view` and `ranges::enable_borrowed_range` to `true`. The latter means that calling `ranges::find` on an rvalue `span` returns a usable iterator rather than `ranges::dangling` ([[range.range]]).

`mdspan` has no `begin` or `end` and is not a range. Its main interface is the multidimensional subscript `m[i, j]`, which relies on `operator[]` accepting multiple arguments since C++23 ([[expr.sub]], [[P2128R6]]). For layouts that are non-contiguous or map several indices to the same element, iterating over all elements in some order has no natural definition.

## The two paragraphs of [views.general]

¶1 `<span>` defines `span`; `<mdspan>` defines `mdspan` and its supporting facilities: `extents`, the various layouts, accessors, `submdspan`, and the multidimensional `copy` and `fill` added in more recent drafts.

¶2 `dynamic_extent` is provided by `<span>`, and is also available when `<mdspan>` is included. Its value is `numeric_limits<size_t>::max()`, and as an extent argument it means the extent is determined only at run time. `span<int, dynamic_extent>` and `extents<int, 3, dynamic_extent>` use the same constant, so a file that includes only `<mdspan>` can still write `std::dynamic_extent` directly.

## Related language rules

- Element type conversion: `span<const T>` can be constructed from `span<T>`, but `span<Base>` cannot be constructed from `span<Derived>`. The library uses `is_convertible_v<U(*)[], T(*)[]>` to restrict the allowed conversions to qualification conversions ([[conv.qual]]).
- Byte views: `as_bytes` turns a `span<T>` into a `span<const byte>`; its legitimacy comes from object representations ([[basic.types.general]]) and the rule that any object may be accessed through `std::byte` ([[basic.lval#11]]).
- Hardening: most of the subscript, subview and extent checks of `span` and `mdspan` are written as *Hardened preconditions*. In a [[g:hardened-implementation|hardened implementation]], violating them terminates the program; in other implementations it is UB.

| Subclause | Contents |
|---|---|
| [[views.contiguous]] | `<span>`: construction, subviews, element access, iterators, `as_bytes` |
| [[views.multidim]] | `<mdspan>`: `extents`, layout mappings and the standard layouts, accessors, `mdspan`, `submdspan`, multidimensional `copy`/`fill` |
