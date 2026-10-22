---
title: The vector<bool> specialization
summary: "vector<bool> packs each element into one bit, at the cost of v[i] returning a proxy object instead of bool&; it is not contiguous, does not meet the container requirements, and concurrent writes to adjacent elements are a data race."
updated: 2026-10-19
---

!!! tldr
    - `vector<bool>` is a partial specialization of `vector` with recommended bit-packed storage; `v[i]` returns the proxy class `reference`, and `const_reference` is `bool`.
    - Since a single bit cannot be referenced, `bool& b = v[0];` fails to compile; generic code has to write `auto&&`.
    - `auto x = v[i];` gives you a proxy that refers to the vector's storage and dangles once the vector is destroyed.
    - Concurrently modifying different elements of the same container is normally not a data race; `vector<bool>` is the one exception.
    - Under libc++'s default ABI, `const_reference` is not `bool`, contrary to the standard.

## A single bit cannot be referenced

```cpp title="no-bool-ref.cpp" error
#include <vector>
void f(std::vector<bool>& v) {
  bool& b = v[0];   // error: v[0] is a vector<bool>::reference prvalue
  (void)b;
}
```

To save space, `std::vector<bool>` packs each element into a single bit. The smallest addressable unit in C++ is the byte, and a `bool&` cannot refer to one bit within a byte, so `operator[]` can only return a **proxy** object: it remembers the underlying word and bit mask, changes that bit on assignment, and reads that bit when converted to `bool`.

As a result, `vector<bool>` does not meet the container requirement that `reference` be `T&` ([[container.requirements.general]]), and it is not a contiguous container. It is still called `vector`, and generic code that writes `T& x = c[i];` or `for (T& x : c)` fails to compile on it. The generic spelling is `auto&& x = c[i];` and `for (auto&& x : c)`; a forwarding reference can bind to the proxy prvalue.

## The partial specialization ([vector.bool.pspc] ¶1–¶3)

¶1 To optimize space allocation, the standard provides the partial specialization `vector<bool, Allocator>`. The interface is almost the same as the primary template; the differences are concentrated in the types:

| Member | Primary template `vector<T>` | `vector<bool>` |
|---|---|---|
| `reference` | `T&` | Nested class `reference` (a proxy) |
| `const_reference` | `const T&` | `bool` (by value) |
| `pointer`, `iterator` | Point to `T` | Implementation-defined; the iterator is not a contiguous iterator |
| `data()` | Yes | No |
| Extra members | None | `flip()`, `reference::flip()` |

¶2 Unless described below, all operations have the same requirements and semantics as the primary template, except that operations dealing with `bool` values are mapped to bits in storage, and those values are not constructed with `allocator_traits::construct`. So an allocator that records every `construct` call records nothing for a `vector<bool>`; the allocator only provides storage for the underlying words.

¶3 There is no requirement that the data be stored as a contiguous array of `bool`; bit-packed storage is recommended. It is only a recommendation, but mainstream implementations all pack bits.

{{impl}} libc++ uses `size_type` (64 bits with Clang 23) as its storage unit. `sizeof(std::vector<bool>)` is 24 bytes (begin pointer, bit count, word capacity); a `vector<bool>` with a single element allocates one 8-byte word, and `capacity()` is 64.

## The proxy class reference (¶4–¶11)

¶4 `reference` is a class that simulates a reference to a single bit in the sequence. Its members:

- ¶5–¶6 Copy construction yields a proxy referring to the same bit; the destructor does nothing.
- ¶7–¶8 `operator=(bool)`, `operator=(const reference&)`, and the `const`-qualified `operator=(bool) const`: set or clear the referenced bit according to the value of the argument.
- ¶9 `operator bool() const`: reads the bit.
- ¶10 `flip()`: equivalent to `*this = !*this`.
- ¶11 Three friend `swap`s: `swap(reference, reference)`, `swap(reference, bool&)` and `swap(bool&, reference)`, with effects as if by `bool b = x; x = y; y = b;`.

The `const`-qualified assignment operator was added in C++23. Assigning to a const object looks odd, but for a proxy, assignment modifies the proxied bit, not the proxy itself. C++20's `indirectly_writable` requires writing to be possible through a const reference type, and with this operator the iterators of `vector<bool>` can be used with range algorithms that require output iterators.

```cpp title="vector-bool-proxy.cpp" run ok
#include <vector>
#include <type_traits>
#include <format>
#include <cassert>
#include <ranges>

static_assert(!std::is_same_v<std::vector<bool>::reference, bool&>);
static_assert(!std::ranges::contiguous_range<std::vector<bool>>);

int main() {
  std::vector<bool> v{true, false, true};
  auto r = v[1];          // r is a vector<bool>::reference, not a bool
  r = true;               // writes to v[1]
  assert(v[1]);
  v[0].flip();
  assert(!v[0]);
  using std::swap;
  swap(v[0], v[2]);       // swap between proxies (friend function)
  assert(v[0] && !v[2]);
  assert(std::format("{}", v[0]) == "true");   // [vector.bool.fmt]
}
```

### auto and dangling proxies

`auto x = v[i];` deduces the proxy, not `bool`. The proxy holds a pointer to the underlying word, and if it outlives the vector, it dangles:

```cpp title="dangling-proxy.cpp" run ub
#include <vector>
#include <cstdio>
std::vector<bool> make() { return {true, false}; }
int main() {
  auto b = make()[0];             // b is a proxy into the temporary vector's storage
  std::printf("%d\n", bool(b));   // UB: the temporary vector has been destroyed
}
```

The temporary `make()` is destroyed at the end of the full-expression ([[class.temporary]]), and in our tests AddressSanitizer reports `heap-use-after-free`. For any other `vector<T>`, `auto b = make()[0];` would be a safe copy. The fix is to write `bool b = make()[0];`.

## flip, hash and formatting (¶12–¶14, [vector.bool.fmt])

¶12 The member `flip()` replaces each element with its complement. An implementation can flip whole words, which is fast.

¶13 `hash<vector<bool, Allocator>>` is an enabled specialization ([[unord.hash]]), so `vector<bool>` can be used directly as an `unordered_set` key.

¶14 The exposition-only variable template `is-vector-bool-reference<T>` is true if `T` is some `vector<bool, Alloc>::reference` and that `vector<bool, Alloc>` is not a program-defined specialization.

[vector.bool.fmt] provides `formatter<T, charT>` for `T` satisfying `is-vector-bool-reference`; the `parse` and `format` of ¶1–¶2 both forward to an internal `formatter<bool, charT>`. So `std::format("{}", v[0])` outputs `true` and `std::format("{:d}", v[0])` outputs `1`, just like formatting a real `bool`.

## The data race exception

The general rule is that concurrently modifying different elements of the same container is not a data race ([[container.requirements.dataraces#2]]). That rule explicitly excludes `vector<bool>`, and the note in paragraph 3 explains that `y[0] = true` and `y[1] = true` executed concurrently may be a data race.

The reason is that hardware has no ordinary store instruction for a single bit. Setting a bit is a read-modify-write of the whole word, and two threads changing different bits of the same word at the same time overwrite each other. Using a `vector<bool>` as an array of completion flags for multiple threads is a common bug; use `vector<char>`, `vector<std::atomic<bool>>` (with the size fixed before concurrent use), or have each thread own different words.

## Where libc++ departs from the standard

{{impl}} In libc++ (Clang 23), `std::vector<bool>::const_reference` is not `bool` but the internal type `std::__bit_const_reference<…>`, inconsistent with the class synopsis in [vector.bool.pspc]. It is `bool` only when the ABI macro `_LIBCPP_ABI_BITSET_VECTOR_BOOL_CONST_SUBSCRIPT_RETURN_BOOL` is defined (automatically in ABI version 2); the default ABI version 1 keeps the old behavior for binary compatibility. `__bit_const_reference` converts implicitly to `bool`, so the practical impact is small, but `static_assert(std::is_same_v<std::vector<bool>::const_reference, bool>)` fails on libc++.

## Why not remove it

The problems with `vector<bool>` were recognized early, and there have been repeated proposals to deprecate or rename it, none adopted. Turning it back into an ordinary `vector` would make all existing code that relies on bit packing silently use 8 times the memory, and would change the ABI.

The current approach is to keep it and avoid it in new code: for a fixed-size set of bits use `std::bitset`; for a container that really stores `bool`s use `std::vector<char>` or `std::deque<bool>`.

## Questions

!!! question "Question"
    For `std::vector<bool> v`, does `std::span<bool> s(v);` compile? What about `std::ranges::sort(v)`?

<details markdown="1">
<summary>Answer</summary>

`span<bool>` does not. The range constructor of `span` requires the argument to be a contiguous range whose element reference type can be used as an lvalue of `bool` ([[views.contiguous]]), and `vector<bool>` fails both.

`ranges::sort(v)` does. `sort` requires a random access range that satisfies `sortable`, which is built on `indirectly_swappable` and `indirectly_movable_storable`. The proxy iterator satisfies these concepts through customized `iter_swap` and `iter_move` and the const assignment operator. Both conclusions were verified with Clang 23 and libc++.
</details>

## Summary

- The `reference` of `vector<bool>` is a proxy class and `const_reference` is `bool`; it is not contiguous, has no `data()`, and does not use `allocator_traits::construct`.
- `auto x = v[i]` gives a proxy; beware of dangling. Generic code uses `auto&&`.
- Concurrent writes to adjacent elements may be a data race, the one exception to the container data race rule.
- `flip()` and the enabled `hash` and `formatter` specializations make it somewhat more usable in practice; under libc++'s default ABI, `const_reference` differs from the standard.
