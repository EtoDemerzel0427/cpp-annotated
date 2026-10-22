---
title: Pointer alignment
summary: "std::align finds an aligned block of space in a buffer and updates the pointer and remaining length in place; assume_aligned is an alignment promise to the optimizer, and breaking it is undefined behavior; C++26's is_sufficiently_aligned checks at run time whether a pointer is aligned."
updated: 2026-10-19
---

!!! tldr
    - `std::align` finds the first position in a buffer that satisfies the alignment and has room for `size` bytes; on success `space` is reduced only by the bytes skipped for alignment, not by `size`.
    - `std::assume_aligned<N>(p)` is a promise, not a check: if the pointer is not actually `N`-aligned, the behavior is undefined, and accesses should go through its return value.
    - C++26's `std::is_sufficiently_aligned<N>(p)` checks alignment at run time and fits naturally before `assume_aligned`.
    - Both of the latter functions require the pointer to point to an object; passing a null pointer violates the precondition too.

Alignment is a core-language concept ([[basic.align]]): every object type has an alignment requirement, and an object can only be placed at an address that satisfies it. [ptr.align] provides three companion library functions, each answering one question:

| Function | Question it answers | Introduced |
|---|---|---|
| `std::align` | Where in this buffer is the first aligned position with room for `size` bytes? | C++11 |
| `std::assume_aligned<N>` | I promise this pointer is `N`-aligned; optimize accordingly | C++20 ([[P1007R3]]) |
| `std::is_sufficiently_aligned<N>` | Is this pointer actually `N`-aligned? | C++26 ([[P2897R7]]) |

## `std::align`

```cpp run title="std-align.cpp" ok
#include <cstddef>
#include <cstdio>
#include <memory>

int main() {
    alignas(16) std::byte buf[64];
    void* p = buf + 1;                    // deliberately off by 1 byte
    std::size_t space = sizeof(buf) - 1;  // 63
    if (void* q = std::align(16, 32, p, space)) {
        std::printf("offset: %zu, space left: %zu\n",
                    (std::size_t)((std::byte*)q - buf), space);   // offset: 16, space left: 48
    }
    void* r = buf;
    std::size_t s2 = 8;
    std::printf("fits? %s\n", std::align(16, 16, r, s2) ? "yes" : "no");   // no: only 8 bytes
}
```

```cpp
void* align(size_t alignment, size_t size, void*& ptr, size_t& space);
```

¶1 Preconditions: `alignment` is a power of two; `ptr` represents the address of contiguous storage of at least `space` bytes.

¶2 If `size` bytes aligned by `alignment` fit into the buffer starting at `ptr` of length `space`, `ptr` is updated to the first such address and `space` is decreased by the number of bytes skipped for alignment; otherwise nothing is done.

¶3 It returns a null pointer if they do not fit, and the adjusted `ptr` otherwise. The note in ¶4 explains the point of modifying the reference arguments in place: the function can be called repeatedly on the same buffer, with different alignments and sizes each time.

!!! pitfall "space is not reduced by size"
    After success, `space` has been reduced only by the alignment padding (63 minus 15 gives 48 in the example), not by `size`. To go on to allocate the next block, you have to write `p = static_cast<std::byte*>(p) + size; space -= size;` yourself. In a hand-written sequential allocator, forgetting this step makes the next `align` return the same address.

`std::align` only computes addresses; it does not create objects or begin any lifetime. After getting the address you still have to construct the object with placement new or `construct_at` ([[memory]]). `monotonic_buffer_resource` in [[mem.res.monotonic.buffer]] is essentially `std::align` plus a pointer bump, asking upstream for a new block when it runs out.

## `std::assume_aligned`

```cpp
template<size_t N, class T> constexpr T* assume_aligned(T* ptr);
```

- ¶5 *Mandates*: `N` is a power of two.
- ¶6 *Preconditions*: `ptr` points to an object `X` of a type similar ([[conv.qual]]) to `T`, where `X` has alignment `N`.
- ¶7–¶8 Returns `ptr`; throws nothing.

!!! std
    It is up to the program to ensure that the assumption actually holds. The call does not cause the implementation to verify or enforce this.

The note in ¶9 says it is up to the program to ensure the assumption holds; the call does not make the implementation verify or enforce it. It is a promise to the optimizer, similar to `[[assume]]` ([[dcl.attr.assume]]). The compiler may use it to emit SIMD instructions that require alignment and to drop the code that handles an unaligned prefix. If the promise does not hold, the behavior is {{ub}}.

The note also says that an implementation might only apply the assumption to accesses made through the return value. So use the return value, not the original pointer:

```cpp
float* a = std::assume_aligned<64>(p);   // only accesses through a are sure to be optimized
```

¶6 has two consequences that are easy to miss:

1. The precondition requires `ptr` to point to an object. A null pointer points to no object, so `assume_aligned<N>(nullptr)` is undefined behavior too, even though address 0 is arithmetically aligned for every `N`.
2. What is required is that the object `X` has alignment `N`, i.e. its address is `N`-aligned; it has nothing to do with `alignof`: a `float` may well happen to sit on a 64-byte boundary.

```cpp run title="assume-aligned-ub.cpp" ub
#include <cstdio>
#include <memory>

float sum(float* p, int n) {
    float* a = std::assume_aligned<64>(p);
    float s = 0;
    for (int i = 0; i < n; ++i) s += a[i];
    return s;
}

int main() {
    alignas(64) float data[32] = {};
    std::printf("%d\n", std::is_sufficiently_aligned<64>(data + 1));   // 0
    std::printf("%f\n", sum(data + 1, 8));   // UB: data + 1 is only 4-byte aligned
}
```

In our tests: with `-fsanitize=undefined`, UBSan reports assumption of 64 byte alignment for pointer of type 'float *' failed. With libc++ hardening mode `extensive` or `debug`, `assume_aligned` asserts at run time that the address is aligned and terminates the program; `fast` mode does not check.

!!! impl "assume_aligned in constant evaluation"
    libc++ implements it with `__builtin_assume_aligned`. The real address cannot be checked during constant evaluation, so in that case libc++ simply returns `ptr`. So `assume_aligned` can be used in a `constexpr` function, but it has no effect during constant evaluation.

## `std::is_sufficiently_aligned` {{c++26}}

```cpp
template<size_t Alignment, class T> bool is_sufficiently_aligned(T* ptr);
```

- ¶10 *Mandates*: `Alignment` is a power of two. This was added by [[LWG4290]].
- ¶11 *Preconditions*: the pointer points to an object `X` of a type similar to `T`. The draft writes `p` here, inconsistent with the parameter name `ptr`; this is an editorial slip.
- ¶12–¶13 Returns `true` if `X` has alignment at least `Alignment`, otherwise `false`; throws nothing.

It is not `constexpr`, because the result depends on the actual address of the object.

It pairs with `assume_aligned`: check with `is_sufficiently_aligned` first, and when it holds, promise with `assume_aligned`. It came into C++26 together with `mdspan`'s `aligned_accessor`: [[mdspan.accessor.aligned]] uses it to describe the accessible range of `aligned_accessor`, and the example there checks first and switches to `aligned_accessor` only when the check succeeds. `pointer_tag_pair::from_overaligned` in [[ptrtag]] also states its precondition with it.

`is_sufficiently_aligned` likewise requires the pointer to point to an object: calling it on a null or dangling pointer is undefined behavior, not a `false` result. The libc++ implementation is just `reinterpret_cast<uintptr_t>(ptr) % Alignment == 0` and actually returns `true` for a null pointer, but that is an implementation detail and cannot be relied on.

## Questions

!!! question "Question 1"
    Can `std::align` be used to tell whether an existing pointer is `N`-aligned?

<details markdown="1">
<summary>Answer</summary>

Yes, though awkwardly: `void* q = p; size_t s = 1; std::align(N, 1, q, s) == p`. When `p` is already aligned, `align` does not need to skip any bytes and returns `p` itself. Its precondition does require that there really is at least 1 byte of storage at `p`.

Since C++26, `is_sufficiently_aligned` is clearer. Before that the usual way was `reinterpret_cast<std::uintptr_t>(p) % N == 0`, which relies on the implementation-defined mapping from pointers to integers ([[expr.reinterpret.cast]]), although all mainstream platforms map by address value.
</details>

!!! question "Question 2"
    Why is `assume_aligned` `constexpr` while `is_sufficiently_aligned` is not?

<details markdown="1">
<summary>Answer</summary>

The result of `assume_aligned` is just `ptr`, so during constant evaluation it can be treated as the identity function; the promise cannot be verified and does not need to be. The result of `is_sufficiently_aligned` depends on the actual address of the object, and objects in constant evaluation have no definite run-time address, so the result cannot be computed.
</details>
