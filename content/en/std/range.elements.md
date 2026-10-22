---
title: Elements, keys and values views
summary: "views::elements<N> takes the N-th component of each tuple-like element, and views::keys and views::values are shorthands for N = 0 and 1; when the underlying elements are references the result is a reference to the component, and when they are temporaries the result is a copy of the component, so nothing dangles."
updated: 2026-10-19
---

!!! tldr
    - `views::elements<N>` applies `std::get<N>` to each element; `views::keys` is `elements<0>` and `views::values` is `elements<1>`.
    - The elements must be standard library tuple-like types: `pair`, `tuple`, `array`, `subrange`, `complex`. A struct of your own does not qualify even if it specializes `tuple_size` and provides `get`.
    - When the underlying elements are references (like the elements of a `map`), the result is a reference to the component: `values` can be written back, `keys` is read-only because the key is `const`.
    - When the underlying elements are temporaries, the result returns a copy of the component by value and does not dangle.
    - The iterator category, sizedness, commonness and borrowedness are all the same as the underlying range's.

```cpp run ok
#include <cstdio>
#include <map>
#include <ranges>
#include <string>

int main() {
  std::map<std::string, int> m{{"x", 1}, {"y", 2}};
  for (auto& k : m | std::views::keys) std::printf("%s", k.c_str());   // xy
  for (int& v : m | std::views::values) v *= 10;                       // writes back to the map
  std::printf(" %d\n", m["y"]);                                        // 20
}
```

Taking all the keys of a `map`, or one column of a `vector<tuple<...>>`, both project each element onto its N-th component. `transform([](auto& p) -> auto& { return std::get<N>(p); })` can do this too, but such a hand-written lambda returns a dangling reference when the elements are temporaries; the rules of `elements_view` handle exactly that case.

## `views::elements<N>` [range.elements.overview]

¶1 `elements_view` takes a view of tuple-like values and a `size_t` N, and produces a view whose value type is the N-th element of the underlying value type. ¶2 `views::elements<N>(E)` is equivalent to `elements_view<views::all_t<decltype((E))>, N>{E}`. `views::elements<N>` is itself an object that can go directly to the right of `|`, without being called with parentheses.

¶3 `keys_view<R>` is an alias for `elements_view<R, 0>`, and ¶4 `values_view<R>` is an alias for `elements_view<R, 1>`; the corresponding adaptors are `views::keys` and `views::values`. They are mainly used with associative containers. The three standard examples in ¶2–¶4 use the same `map`:

```cpp run ok
#include <algorithm>
#include <iostream>
#include <map>
#include <ranges>
#include <string_view>
using namespace std::literals;

int main() {
  auto historical_figures = std::map{
    std::pair{"Lovelace"sv, 1815}, {"Turing"sv, 1912},
    {"Babbage"sv, 1791}, {"Hamilton"sv, 1936}};
  for (auto&& name : historical_figures | std::views::keys)
    std::cout << name << ' ';          // Babbage Hamilton Lovelace Turing
  auto is_even = [](const auto x) { return x % 2 == 0; };
  std::cout << std::ranges::count_if(historical_figures | std::views::values, is_even)
            << '\n';                   // 2
}
```

## Which elements are allowed [range.elements.view]

The constraints of `elements_view` use two exposition-only concepts:

- *has-tuple-element*: the type is *tuple-like*, N is less than `tuple_size_v`, and `std::get<N>(t)` is usable. Both the value type and the reference type must satisfy it.
- *returnable-element*: the underlying element is a reference, or the N-th component is move constructible. When the element is not a reference, the component is returned by value, so it must be movable.

*tuple-like* ([[tuple.like]]) only recognizes the few templates listed by the standard library: `array`, `complex`, `pair`, `tuple`, `ranges::subrange`. A user-defined type does not satisfy this concept even if it specializes `tuple_size` and `tuple_element` and provides `get`, so it cannot be used with `elements_view`. Use `transform` with a projection instead.

```cpp error
#include <ranges>
#include <vector>

struct P { int a; int b; };
template<> struct std::tuple_size<P> : std::integral_constant<std::size_t, 2> {};
template<std::size_t I> struct std::tuple_element<I, P> { using type = int; };
template<std::size_t I> int& get(P& p) { return I == 0 ? p.a : p.b; }

std::vector<P> v;
auto k = v | std::views::keys;   // error: P is not tuple-like
```

## Reference or copy [range.elements.iterator]

¶3 Dereferencing the iterator is done by the exposition-only function *get-element*:

```cpp
if constexpr (is_reference_v<range_reference_t<Base>>) {
  return std::get<N>(*i);
} else {
  using E = remove_cv_t<tuple_element_t<N, range_reference_t<Base>>>;
  return static_cast<E>(std::get<N>(*i));
}
```

When the underlying element is a reference, such as a `map`'s `pair<const K, V>&`, it returns the reference obtained from `std::get<N>`: the value can be written back, while the key is `const K` and read-only.

When the underlying element is a temporary, such as a `pair` produced by `transform`, `*i` is a temporary tuple. Returning a reference from `get<N>` would refer into that temporary and dangle as soon as the full-expression ended. So in this case a copy of the component is returned by value. The original C++20 wording lacked this branch; [[LWG3502]] added it.

```cpp run ok
#include <cstdio>
#include <ranges>
#include <utility>
#include <vector>

int main() {
  auto pairs = std::views::iota(0, 3)
             | std::views::transform([](int i) { return std::pair{i, i * i}; });
  auto sq = pairs | std::views::values;
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(sq)>, int>);  // a copy
  for (int x : sq) std::printf("%d ", x);       // 0 1 4

  std::vector<int> a{1, 2};
  std::vector<char> b{'x', 'y'};
  auto vs = std::views::zip(a, b) | std::views::values;
  static_assert(std::same_as<std::ranges::range_reference_t<decltype(vs)>, char&>);
  for (char& c : vs) c = 'z';                    // writes back to b
  std::printf("%c%c\n", b[0], b[1]);             // zz
}
```

The second example is a case that is easy to get wrong. The elements of `zip(a, b)` are temporary `tuple<int&, char&>`s, so the else branch is taken; but `E` is `remove_cv_t<char&>`, i.e. `char&`, so what is returned is still a reference to the element in `b`. When the tuple holds references, the result is a reference too: it does not dangle, and it can be written back.

## Other properties

- The iterator just wraps the underlying iterator, and `++`, `+=` and the rest are forwarded directly. ¶1 The iterator category is the same as the underlying range's (contiguous is lowered to random access); sizedness and commonness are also the same as the underlying range's.
- ¶2 `iterator_category` is `input_iterator_tag` when `std::get<N>(*current_)` is an rvalue, for the same reason as in [[range.transform]]: old-style forward iterators require dereferencing to yield an lvalue reference.
- It is a [[g:borrowed-range|borrowed range]] when the underlying range is, because the iterator needs no access to the view object. This is an advantage over `transform` with a lambda: `ranges::find(views::keys(m), k)` returns a real iterator, whereas `transform_view` is never a borrowed range, so the same call through it could only give `ranges::dangling`.

## Summary

| | `elements<N>`, `keys`, `values` |
|---|---|
| Applicable elements | standard library tuple-like types: `pair`, `tuple`, `array`, `subrange`, `complex` |
| Result of dereference | underlying reference: a reference to the component; underlying temporary: a copy of the component (still a reference if the component itself is a reference) |
| Iterator category, sized, common | same as underlying (contiguous lowered to random access) |
| Borrowed range | when the underlying range is |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[range.elements.view] ¶1: the constructor stores the underlying view.

[range.elements.iterator] ¶4–¶7 are the constructors and `base()`; the remaining paragraphs forward `++`, `--`, `+=`, comparison, subtraction and so on directly to the underlying iterator. The sentinel in [range.elements.sentinel] stores the underlying end, and comparison and subtraction are likewise forwarded to the underlying range.

</details>
