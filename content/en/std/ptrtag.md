---
title: Pointer tagging with pointer_tag_pair
summary: "pointer_tag_pair, added to the draft after C++26, stores a small integer in the unused low bits of an aligned pointer; it is the same size as the pointer, trivially copyable, and usable in constant evaluation."
updated: 2026-10-19
---

!!! tldr
    - A pointer to an 8-byte-aligned object always has its low 3 bits zero, so they can hold a tag from 0 to 7. `std::pointer_tag_pair` {{c++29}} turns this trick into a standard type with a clear contract.
    - A hand-written version has to do bit operations on an integer, with implementation-defined results, and cannot be used in constant evaluation; construction and access of `pointer_tag_pair` are all `constexpr`.
    - Its size and alignment are the same as the original pointer's and it is trivially copyable, so it fits into `std::atomic`, and a single CAS updates pointer and tag together.
    - How many bits are available is decided by `pointer_bits_available(alignof(T))`, usually the number of trailing zeros of the alignment.
    - `tagged_pointer()` returns the encoded raw pointer, which can only be handed back unchanged to `from_tagged` and cannot be dereferenced.

## Hand-written pointer tagging

```cpp run impl
#include <cassert>
#include <cstdint>

struct alignas(8) Node { int v; };

// a hand-written tagged pointer: the tag lives in the low 3 bits
struct TaggedNode {
  std::uintptr_t bits;
  TaggedNode(Node* p, unsigned tag)
      : bits(reinterpret_cast<std::uintptr_t>(p) | tag) {
    assert(tag < 8);
  }
  Node* ptr() const {
    return reinterpret_cast<Node*>(bits & ~std::uintptr_t{7});
  }
  unsigned tag() const { return bits & 7; }
};

int main() {
  Node n{42};
  TaggedNode t(&n, 5);
  static_assert(sizeof(TaggedNode) == sizeof(Node*));
  assert(t.ptr()->v == 42 && t.tag() == 5);
}
```

**Pointer tagging** exploits alignment: `Node` is 8-byte aligned, so the low 3 bits of a pointer to it are always zero and can store a small integer. Red-black trees store the node color in the parent pointer, lock-free data structures store a version number or deletion flag in a pointer, interpreters store type tags in value pointers, all to save the memory of one field.

This code runs correctly on mainstream platforms, but the standard guarantees very little about it. [[expr.reinterpret.cast]] only guarantees that converting a pointer to a sufficiently large integer and back unchanged yields the original pointer. What you get back after doing bit operations on the integer in between depends on how the implementation defines the mapping between pointers and integers, so the verdict here is {{impl}}. In addition:

- `reinterpret_cast` cannot appear in a constant expression, so this type cannot be used in constant evaluation;
- how many bits are available is the programmer's own assumption, and if the type's alignment is later reduced, the code silently breaks.

[ptrtag] solves these problems with a standard class template. It was added to the working draft by [[P3125R6]] after C++26 was finalized and is expected to be part of C++29. At the time of writing libc++ (with Clang 23) does not implement it yet, so none of the `pointer_tag_pair` examples below have been compiled.

## Basic usage

```cpp
#include <cassert>
#include <memory>

struct alignas(8) Node { int v; };
enum class Color : unsigned { red, black };

int main() {
  Node n{42};
  std::pointer_tag_pair<Node*, 1, Color> p(&n, Color::black);   // uses only 1 bit
  static_assert(sizeof(p) == sizeof(Node*));
  auto [ptr, color] = p;                                         // tuple interface
  assert(ptr->v == 42 && color == Color::black);
}
```

The three template parameters are, in order, the pointer type, the number of bits requested, and the tag type:

```cpp
template<class Ptr, unsigned BitsRequested = bits-available<element-of<Ptr>>,
         class TagT = unsigned>
class pointer_tag_pair;
```

The exposition-only `element-of<Ptr>` is `pointer_traits<Ptr>::element_type`, and `bits-available<T>` is `pointer_bits_available(alignof(T))` (see the synopsis in [[memory]]). So by default all available bits are requested: `pointer_tag_pair<Node*>` requests 3 bits for an 8-byte-aligned `Node`.

## Available bits [ptrtag.bits]

```cpp
inline constexpr unsigned max_pointer_bits_available = /* implementation-defined */;
constexpr unsigned pointer_bits_available(size_t alignment);
```

¶1 `max_pointer_bits_available` is the implementation's upper limit on the number of bits usable for tagging.

¶2 A nonzero value means the implementation promises that tags round-trip: the non-arithmetic operations done on the encoded pointer, although they act on an invalid pointer value and have implementation-defined behavior ([[basic.compound]]), preserve enough information for `from_tagged` to recover the original object.

¶3–¶5 `pointer_bits_available(alignment)` returns the number of unused bits in a pointer to a hypothetical object with alignment `alignment`; the exact value is implementation-defined. The precondition is that `alignment` is a power of 2; when the precondition holds, the call is a constant expression.

¶6–¶7 recommend that the result be nonzero when the alignment is greater than 1. Note 1 says that on most platforms the result is the smaller of `countr_zero(alignment)` and `max_pointer_bits_available`: 8-byte alignment gives 3 bits.

Only the low bits from alignment are used here. On x86-64 and AArch64 the high bits of a pointer are usually unused too, but whether they can be exploited depends on the platform and OS configuration, and the standard leaves all of that implementation-defined.

## Class template `pointer_tag_pair` [ptrtag.pair.general]

### Layout guarantees (¶1–¶3)

¶1–¶2 An object of `pointer_tag_pair<Ptr, BitsRequested, TagT>` represents a pair of values: a pointer of type `Ptr` and a tag of type `TagT`.

¶3 Every specialization `PT` is trivially copyable, models `copyable`, and satisfies `sizeof(PT) == sizeof(Ptr)` and `alignof(PT) == alignof(Ptr)`.

The equal size is the reason this type exists; otherwise `struct { T* p; unsigned tag; }` would do. Trivial copyability means it can be `memcpy`ed and put into `std::atomic` ([[atomics.types.generic]] requires trivially copyable types). That is exactly what lock-free algorithms need: one compare-and-swap updating pointer and version number together.

### Requirements on the template parameters (¶4–¶5)

¶4 The program is ill-formed if any of the following is not met:

- ¶4.1–¶4.2 neither `Ptr` nor `TagT` is cv-qualified or a reference;
- ¶4.3 `Ptr` is an object pointer type, not a function pointer, a `unique_ptr` or a fancy pointer;
- ¶4.4 `TagT` is an unsigned integer type or an enumeration whose underlying type is an unsigned integer type;
- ¶4.5 `sizeof(TagT) <= sizeof(void*)`;
- ¶4.6 `BitsRequested <= max_pointer_bits_available`.

¶5 The exposition-only `tag-bit-width(v)` equals `bit_width(v)`, with enumerations first passed through `to_underlying`; that is, the minimum number of bits needed to represent the tag value. The preconditions of the operations are all written as `tag-bit-width(t) <= bits_requested`: the tag must fit in the requested bits.

### Which `U*` can go in

The constructors take `U* p`, where `U` must satisfy the exposition-only concept `tagging-compatible-pointee<U, PtrT, Bits, Alignment = alignof(U)>`:

- `U*` is convertible to `PtrT`;
- `pointer_bits_available(Alignment) >= Bits`, checking the bits by `U`'s alignment rather than by the alignment of `PtrT`'s pointee;
- `element-of<PtrT>` is `void`, a scalar type, a union, or a pointer-interconvertible base class of `U` ([[g:pointer-interconvertible]]).

The last condition rules out pointer adjustment. Converting a `Derived*` to a `Base*` that is not the first base adds an offset to the address, and the offset address need not satisfy `Derived`'s alignment, so the low bits the tag needs might no longer be zero. Converting to a pointer-interconvertible base, such as the first base of a standard-layout class, leaves the address unchanged.

## Construction [ptrtag.pair.cons]

¶1 Default construction gives `pointer() == nullptr` and `tag() == TagT()`.

¶2–¶5 `pointer_tag_pair(U* p, tag_type t)` and `pointer_tag_pair(nullptr_t, tag_type t)` have two preconditions: ¶3.1 `p` is not a past-the-end pointer, and ¶3.2 the tag fits in the requested bits. When the preconditions hold, the construction is a constant expression. Construction throws nothing.

### Objects aligned more strictly than their type [ptrtag.pair.overalign]

`int` only requires 4-byte alignment, which leaves 2 bits. If the program knows that its `int`s all come from a 64-byte-aligned memory pool, it can use `from_overaligned<64>(p, t)` to use a few more bits.

¶2 Its preconditions add one more: `p == nullptr || is_sufficiently_aligned<PromisedAlignment>(p)` ([[ptr.align]]). The `tagging-compatible-pointee` in the constraint computes the available bits with `PromisedAlignment` instead.

## Exchanging the encoded pointer with outside code [ptrtag.pair.tagops]

```cpp
using tagged_pointer_type = cv void*;   // the same cv as the type Ptr points to
tagged_pointer_type tagged_pointer() const noexcept;
static pointer_tag_pair from_tagged(tagged_pointer_type p) noexcept;
```

These two functions are for handing the already-encoded raw pointer to outside code, for example storing it through a C interface that only accepts `void*`, and getting it back later.

¶2 `tagged_pointer()` returns an unspecified value `tp`. The standard guarantees that as long as the bit-count and alignment conditions hold, `from_tagged(tp)` recovers the original pointer and tag. Note 1 says this is an **invalid pointer value** ([[g:invalid-pointer-value]], [[basic.compound]]), and operations on it have implementation-defined behavior. So the result of `tagged_pointer()` cannot be dereferenced; it can only be handed back unchanged to `from_tagged`.

¶3 If `p` really came from `tagged_pointer()` of a compatible object, `from_tagged(p)` recovers an equivalent pair of values; otherwise the `pointer()` and `tag()` of the result are unspecified values, which in itself is not undefined behavior.

Neither function is `constexpr`, because constant evaluation cannot really encode the tag into the bits of an address. This also hints at the implementation approach: during constant evaluation, the compiler can track the pointer and the tag separately internally; only `tagged_pointer()` needs real bit encoding.

## Access, comparison and the tuple interface

[ptrtag.pair.accessors] `pointer()` and `tag()` return the represented pointer and tag; both are `constexpr` and `noexcept`. [ptrtag.pair.swap] `swap` exchanges the values of two objects.

[ptrtag.pair.comp] `<=>` and `==` are equivalent to comparing `pair(pointer(), tag())` lexicographically, and require `tag_type` to support the corresponding comparison. The recommended practice: when the tag comparison is a built-in operation, compare the internal bit representation directly, which takes a single integer compare instruction. Note 1 reminds that comparing unrelated pointers gives an unspecified result, as with ordinary pointers ([[expr.rel]]).

[ptrtag.pair.get] `tuple_size` is 2, `get<0>` returns the pointer and `get<1>` the tag, so structured bindings are supported, as in the example above.

!!! lawyer "The second deduction guide"
    ```cpp
    template<class Ptr, class TagT>
      pointer_tag_pair(Ptr*, TagT)
        -> pointer_tag_pair<Ptr*, bits-available<element-of<Ptr>>, TagT>;
    ```
    Here `Ptr` is deduced as the pointee type, such as `Node`. `element-of<Node>` is `pointer_traits<Node>::element_type`, but `Node` has neither an `element_type` member nor is it a template specialization, so by [[pointer.traits.types#2]] that specialization has no members. Read literally, this guide fails substitution for ordinary class types; the intent is clearly `bits-available<Ptr>`. This is a wording problem in the new text; read it as intended.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

The wording of [ptrtag.bits] ¶2 and [ptrtag.pair.tagops] ¶3 uses names such as `tagged_pointer_pair`, `tp.tagged()` and `pointer_tag_type`, which do not match the class name `pointer_tag_pair` or the member name `tagged_pointer()`. These are editorial leftovers and do not affect the meaning.

</details>

## Questions

!!! question "Question 1"
    Why can the `Ptr` of `pointer_tag_pair` only be a plain pointer, not a `unique_ptr` or a fancy pointer?

<details markdown="1">
<summary>Answer</summary>

First, the layout guarantees. `sizeof(PT) == sizeof(Ptr)` and trivial copyability only make sense for plain pointers: `unique_ptr` is not copyable, and a fancy pointer may take more than one word. Second, the tag bits come from the zero bits left by address alignment, and the implementation must know that the value of `Ptr` is the address; the bit pattern of a fancy pointer (an offset pointer, say) has no fixed relation to the address. So ¶4.3 requires `is_pointer_v<Ptr>`.
</details>

!!! question "Question 2"
    Is it undefined behavior for `from_tagged` to receive an arbitrarily constructed `void*`?

<details markdown="1">
<summary>Answer</summary>

No. ¶3.2 specifies that `pointer()` and `tag()` then have unspecified values. But dereferencing that unspecified pointer afterwards is an ordinary invalid pointer dereference and is undefined behavior. `from_tagged` itself can always be called; the danger lies in how its result is used.
</details>
