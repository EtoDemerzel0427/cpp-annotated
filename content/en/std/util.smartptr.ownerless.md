---
title: owner_less, owner_hash and owner_equal
summary: "Three function objects that compare and hash shared_ptr and weak_ptr by ownership (the control block) rather than by stored pointer: owner_less lets weak_ptr be the key of an ordered container, and C++26's owner_hash and owner_equal let it be the key of an unordered one."
updated: 2026-10-19
---

!!! tldr
    - `shared_ptr` has two kinds of equality: `==` compares stored pointers, while ownership equivalence asks whether they belong to the same ownership group. The two can disagree.
    - `weak_ptr` only has ownership-based comparison, because its stored pointer may dangle.
    - `owner_less` gives a strict weak ordering by ownership; `std::map<std::weak_ptr<X>, V, std::owner_less<>>` is the common usage.
    - After the object is destroyed, comparisons of `weak_ptr` keys give the same results, so the container's invariants are not broken.
    - C++26's `owner_hash` and `owner_equal` let `weak_ptr` be the key of an unordered container; libc++ (with Clang 23) does not implement them yet.

## Two kinds of equality

```cpp run title="two-equalities.cpp" ok
#include <memory>
#include <cstdio>
int main() {
    std::shared_ptr<int> a, b;
    std::shared_ptr<int> c(nullptr, [](int*) {});
    std::printf("a,b: == %d  owner %d\n", a == b,
                !a.owner_before(b) && !b.owner_before(a));
    std::printf("a,c: == %d  owner %d\n", a == c,
                !a.owner_before(c) && !c.owner_before(a));
}
```

In our tests it prints `a,b: == 1  owner 1` and `a,c: == 1  owner 0`. `a` and `b` are both empty and equal by both criteria. `c` owns a null pointer and a deleter, so it is not empty; its stored pointer and `a`'s are both null, so `==` is true, but they do not belong to the same ownership group. Conversely, an aliasing `shared_ptr<int>(sp, &sp->b)` is ownership-equivalent to `sp`, yet `==` is false ([[util.smartptr.shared]]).

The precise definition of ownership equivalence is in the member function `owner_equal`: the two share ownership, or are both empty. `owner_before` gives a strict weak ordering consistent with it, and `owner_hash` a hash value consistent with it. The three function objects `owner_less`, `owner_hash` and `owner_equal` merely wrap these three member functions into comparators and hashers that containers can use.

## owner_less [util.smartptr.ownerless]

```cpp run title="owner-less-map.cpp" ok
#include <memory>
#include <map>
#include <cassert>
struct P { int a, b; };
int main() {
    auto sp = std::make_shared<P>();
    std::shared_ptr<int> alias(sp, &sp->b);
    std::weak_ptr<P> w = sp;
    std::map<std::weak_ptr<void>, int, std::owner_less<>> m;
    m[w] = 1;
    m[alias] = 2;                     // same group as w: the same key
    assert(m.size() == 1 && m.begin()->second == 2);
    sp.reset();
    alias.reset();
    assert(w.expired() && m.find(w) != m.end());   // an expired key can still be looked up
}
```

¶1 `owner_less` allows ownership-based mixed comparisons of shared and weak pointers. It comes in three forms: `owner_less<shared_ptr<T>>` and `owner_less<weak_ptr<T>>` each have three `operator()`s accepting the various combinations of `shared_ptr` and `weak_ptr`; `owner_less<void>` since C++17 (the default argument of the primary template is `void`) accepts any `T` and `U` and has `is_transparent`, so a `shared_ptr` can be used directly to look up in a container keyed by `weak_ptr` without first constructing a temporary `weak_ptr`.

¶2 `operator()(x, y)` returns `x.owner_before(y)`. Note 1 points out that it is a strict weak ordering ([[alg.sorting]]), and that `!op(a, b) && !op(b, a)` holds if and only if `a.owner_equal(b)`.

The last line of the example shows the value of comparing by ownership. After a key expires, the control block still exists (the `weak_ptr` in the map itself keeps the weak count nonzero) at the same address, so the comparison results do not change. If you compared by `lock().get()` instead, an expired key would suddenly become a null pointer, equal to every other expired key, and the ordering of the red-black tree would be silently broken.

## owner_hash and owner_equal {{c++26}}

### owner_hash [util.smartptr.owner.hash]

¶1 `owner_hash` provides ownership-based hashing. It has one `operator()` each for `shared_ptr<T>` and `weak_ptr<T>`, and has `is_transparent`. ¶2 `operator()(x)` returns `x.owner_hash()`. ¶3 Note 1: for any `y` such that `x.owner_equal(y)`, `x.owner_hash() == y.owner_hash()`, which meets the unordered containers' requirement that hashing and equality be consistent ([[unord.req]]).

### owner_equal [util.smartptr.owner.equal]

¶1 `owner_equal` provides ownership-based mixed equality comparison, with four `operator()`s for the pairwise combinations of `shared_ptr` and `weak_ptr`, and also has `is_transparent`. ¶2 `operator()(x, y)` returns `x.owner_equal(y)`; ¶3 Note 1 says this is true if and only if `x` and `y` share ownership or are both empty.

`owner_equal` is `constexpr`: deciding whether two objects point to the same control block can be done in constant evaluation. `owner_hash` and `owner_before` need the numeric value of the control block address, so they are not `constexpr`.

Together, they let you write `std::unordered_map<std::weak_ptr<X>, V, std::owner_hash, std::owner_equal>`. Before [[P1901R2]], the standard had no portable way to get at the identity of the control block for hashing, and `weak_ptr` could only go into ordered containers. At the time of writing, libc++ (with Clang 23) does not define `__cpp_lib_smart_ptr_owner_equality` and does not provide these two classes, so this section has no compilable example.

## Questions

!!! question "Question"
    Can `std::set<std::shared_ptr<X>>` be used instead of `std::set<std::shared_ptr<X>, std::owner_less<>>`? When do the two behave differently?

<details markdown="1">
<summary>Answer</summary>

The default `std::less<std::shared_ptr<X>>` compares stored pointers with `<=>` (the comparison part of [[util.smartptr.shared]]). As long as the set contains no aliasing `shared_ptr`s and no `shared_ptr`s owning a null pointer, the two group elements the same way. They differ in two situations: two aliasing `shared_ptr`s pointing to different members of the same object are equivalent under `owner_less<>` but not under the default comparison; an empty `shared_ptr` and a `shared_ptr` owning a null pointer are equivalent under the default comparison but not under `owner_less<>`. For `shared_ptr` either can be used; for `weak_ptr` only `owner_less` works.
</details>

## Summary

| Tool | Basis | Use |
|---|---|---|
| `==`, `<=>`, `hash<shared_ptr>` | The stored pointer `get()` | Distinguishing where it points |
| `owner_less` | A strict weak ordering of control blocks | `weak_ptr` and `shared_ptr` as keys of ordered containers |
| `owner_hash` + `owner_equal` {{c++26}} | The identity of the control block | Keys of unordered containers |
