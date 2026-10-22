---
title: Class template vector
summary: "The full contract of std::vector: only the first size elements of its contiguous storage are objects, why growth must be geometric, what reserve guarantees, which iterators insertion and erasure invalidate, and why the strong exception guarantee of push_back depends on a noexcept move constructor."
updated: 2026-10-19
---

!!! tldr
    - A `vector` holds one block of contiguous storage, and only the first `size()` positions contain objects; accessing `[size, capacity)` through `data()` is undefined behavior.
    - The standard's complexity requirements (amortized constant insertion at the end, O(log N) reallocations for range construction) force implementations to grow geometrically; libc++'s factor is 2.
    - After `reserve(n)`, insertion is guaranteed not to reallocate as long as the element count does not exceed the capacity, and existing elements keep their addresses.
    - Reallocation invalidates all iterators; otherwise insertion or erasure invalidates only iterators at and after the point of the operation.
    - Inserting a single element at the end has the strong exception guarantee, provided `T` is copyable or its move constructor does not throw. A type whose move constructor is not `noexcept` is copied, not moved, when the vector grows.

`std::vector` is the standard library's default sequence container. [vector] itself has only six subclauses, because most of its semantics come from the sets of general requirements it meets: the container requirements ([[container.requirements.general]]) and the sequence container requirements ([[sequence.reqmts]]). [vector] only adds the operations those requirements do not cover or that need extra explanation.

`vector<bool>` is a partial specialization that behaves very differently; see [[vector.bool]].

## What is in memory

Almost every implementation represents a `vector` with three pointers:

```text
 begin            end              end_cap
   │               │                  │
   ▼               ▼                  ▼
  ┌───┬───┬───┬───┬───┬───┬───┬───┐
  │ T │ T │ T │ T │   │   │   │   │      ← storage from one allocate(capacity())
  └───┴───┴───┴───┴───┴───┴───┴───┘
  └─ size() objects ──┘└─ raw storage ─┘
```

With libc++ (Clang 23), `sizeof(std::vector<int>) == 24`: exactly three pointers. `size()` is the number of elements, and `capacity()` the number of elements that fit without reallocating. **Reallocation** means requesting a larger block of storage, moving the elements over, and releasing the old storage.

`allocator<T>::allocate(n)` only starts the lifetime of an array object; it creates no elements ([[default.allocator]]). The container constructs elements one by one through `allocator_traits::construct` ([[container.alloc.reqmts]]). So the storage in `[data() + size(), data() + capacity())` contains no `T` objects, and reading or writing it through `data()` is undefined behavior, even though the memory has really been allocated:

```cpp title="beyond-size.cpp" run ub
#include <vector>
#include <cstdio>

int main() {
  std::vector<int> v;
  v.reserve(8);
  v.push_back(1);
  int* p = v.data();
  std::printf("%d\n", p[3]);   // UB: there are no objects in [size, capacity)
}
```

In AddressSanitizer builds, libc++ adds container annotations to `vector`, marking `[size, capacity)` as inaccessible. Running the program above with `-fsanitize=address` in our tests reports `container-overflow`. This is one of the few tools that can catch "past size but not past capacity" at run time.

## Overview ([vector.overview])

¶1 A `vector` supports amortized constant-time insertion and erasure at the end; insertion and erasure in the middle take linear time. Storage management is handled automatically, and the program can give hints to improve efficiency, namely `reserve`.

¶2 A `vector` meets the requirements of a container, reversible container, allocator-aware container and sequence container, and, for element types other than `bool`, of a contiguous container. Of the optional sequence container operations, it does not provide `push_front`, `prepend_range`, `pop_front` or `emplace_front`, because those operations cannot be amortized constant time on a `vector` ([[sequence.reqmts#70]]).

¶3 The iterators meet the constexpr iterator requirements. Since C++20 all members of `vector` are `constexpr`; see below.

¶4 If the allocator meets the allocator completeness requirements ([[allocator.requirements.completeness]], which `std::allocator` does), an incomplete type `T` may be used when instantiating `vector<T>`, as long as `T` is complete before any member is used. This C++17 guarantee lets recursive data structures be written directly:

```cpp title="vector-basics.cpp" run ok
#include <vector>
#include <cassert>

struct Node {
  int value;
  std::vector<Node> children;   // OK: Node is incomplete here (¶4)
};

int main() {
  std::vector<int> a(3);        // 3 value-initialized ints: {0, 0, 0}
  std::vector<int> b{3};        // the initializer-list constructor wins: {3}
  assert(a.size() == 3 && b.size() == 1);

  Node root{1, {{2, {}}, {3, {}}}};
  assert(root.children.size() == 2);
}
```

`b{3}` is a vector with a single element, 3. In list-initialization, initializer-list constructors are considered first, in a separate phase ([[over.match.list]]), and other constructors only if none is viable. For 3 elements, use parentheses.

## Why growth must be geometric ([vector.cons])

| Constructor | Preconditions | Complexity |
|---|---|---|
| `explicit vector(const Allocator&) noexcept` | None | Constant (¶1–¶2) |
| `explicit vector(size_type n, const Allocator& = …)` | *Cpp17DefaultInsertable* | n default-inserted elements, linear (¶3–¶5) |
| `vector(size_type n, const T& value, const Allocator& = …)` | *Cpp17CopyInsertable* | Linear (¶6–¶8) |
| `vector(InputIterator first, InputIterator last, …)` | See [[sequence.reqmts]] | See below |
| `vector(from_range_t, R&& rg, …)` | See [[sequence.reqmts]] | See below |

¶10 The complexity of iterator-range construction unusually mentions the number of reallocations directly. If the iterators meet *Cpp17ForwardIterator*, it makes only N calls to the copy constructor and no reallocations: it computes the distance first and allocates once. With mere input iterators the length is not known in advance:

!!! std
    It makes order N calls to the copy constructor of T and order log N reallocations if they are just input iterators.

O(log N) reallocations with only O(N) copies in total can be achieved only by geometric growth. If each reallocation added a fixed k slots, there would be N/k reallocations, each moving all existing elements, for O(N²) copies in total. With geometric growth, the numbers of elements moved at each reallocation form a geometric series that sums to O(N). The amortized constant time of insertion at the end rests on the same argument.

¶11–¶13 `from_range` construction initializes exactly N elements. It performs no reallocation in two cases: `R` models `approximately_sized_range` and `ranges::distance(rg) <= ranges::reserve_hint(rg)`, or `R` is a forward range that does not model `approximately_sized_range` (it can traverse once to find the length). Otherwise it performs O(log N) reallocations and O(N) copy or move constructions. `reserve_hint` lets views like `views::filter`, which know only an upper bound on their length, still provide a capacity hint ([[range.approximately.sized]]).

## Capacity ([vector.capacity])

### What reserve guarantees

¶1 `capacity()` is the total number of elements the vector can hold without requiring reallocation.

¶3–¶7 The rules of `reserve(n)`:

- The precondition is that `T` is move-insertable (*Cpp17MoveInsertable*).
- If and only if `n > capacity()`, reallocation happens at this point, and afterwards `capacity() >= n`; otherwise `capacity()` is unchanged. `reserve` never shrinks the capacity.
- If `n > max_size()`, it throws `length_error`. If another exception is thrown there is no effect, unless the exception comes from the move constructor of a non-copyable type.
- Reallocation invalidates all references, pointers and iterators, including the past-the-end iterator.

¶7's last sentence is `vector`'s most useful positive guarantee:

!!! std
    No reallocation shall take place during insertions that happen after a call to reserve() until an insertion would make the size of the vector greater than the value of capacity().

Call `reserve(n)` first and then insert no more than n elements, and no reallocation happens in between. `push_back` inserts at the end, so pointers and references to existing elements stay valid throughout. This is the canonical way to keep element addresses safely in a `vector`.

### shrink_to_fit, swap, resize

¶8–¶11 `shrink_to_fit()` is a non-binding request: the implementation may reduce the capacity to `size()` or do nothing, but it never increases the capacity. If reallocation happens, all iterators are invalidated.

¶12–¶13 `swap` exchanges contents and capacity, in constant time.

¶14–¶19 `resize(sz)` requires `T` to be move-insertable and default-insertable. If `resize(sz)` throws, there is no effect (again except when the move constructor of a non-copyable type throws); if `resize(sz, c)` throws, there is always no effect.

!!! note "What is the capacity after `clear()`?"
    [vector] does not say. [[sequence.reqmts#54]] only says `clear()` destroys all elements and `empty()` is true afterwards. Mainstream implementations keep the capacity: with libc++ (Clang 23), a `vector<int>(100)` still has capacity 100 after `clear()`, and 0 after a further `shrink_to_fit()`. To release the memory reliably, write `std::vector<T>().swap(v);`, which exchanges `v`'s storage with that of an empty vector.

## data ([vector.data])

¶1 `data()` returns a pointer such that `[data(), data() + size())` is a valid range; for a non-empty vector, `data() == addressof(front())`.

The `data()` of an empty vector may or may not be a null pointer; the standard only guarantees that `[data(), data())` is a valid empty range. With libc++ (Clang 23), an empty vector that has never allocated returns a null pointer. Check `empty()` before passing it to a C interface that requires a non-null pointer (such as `memcpy`, even with length 0).

## Insertion ([vector.modifiers])

### Complexity and invalidation (¶1–¶2)

¶1 If insertion reallocates, the time is linear in the number of elements of the resulting vector; otherwise it is linear in the number of elements inserted plus the distance from the insertion point to the end.

¶2 Reallocation always happens if the new size is greater than the old capacity, and it invalidates all references, pointers and iterators, including the past-the-end iterator. Without reallocation, those before the insertion point remain valid, and those at or after it (including the past-the-end iterator) are invalidated.

```cpp title="range-for-push.cpp" run ub
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  for (int x : v)          // the range-based for caches begin() and end()
    v.push_back(x);        // UB: after the first reallocation, the cached iterators are all invalid
}
```

A range-based `for` evaluates and saves `begin` and `end` before the loop starts ([[stmt.ranged]]), so changing the container's size in the loop body is almost always wrong. In our tests AddressSanitizer reports `heap-use-after-free`.

### The strong guarantee and move_if_noexcept (¶2)

¶2, in its second half, specifies what happens when insertion throws, in three tiers:

1. If the exception is not thrown by `T`'s copy constructor, move constructor, copy assignment or move assignment, nor by an operation of an input iterator (for example, the allocator throwing `bad_alloc`): no effect.
2. When inserting a single element at the end (`push_back`, `emplace_back`), as long as `T` is copy-insertable or `is_nothrow_move_constructible_v<T>` is true: no effect. This is the strong exception guarantee.
3. Otherwise, if the exception is thrown by the move constructor of a non-copyable `T`: the effects are unspecified.

The difficulty in tier 2 is growth: the old elements have to be relocated to the new storage. If they are relocated by move construction and the kth element's move constructor throws, the first k−1 old elements have already been moved from and cannot be restored. If they are relocated by copy construction, on failure the new storage is simply discarded and the old storage is untouched.

So the implementation chooses: move if the move constructor does not throw; otherwise copy if possible; only when neither works (move-only, and the move may throw) does it fall back to moving and give up the strong guarantee, which is tier 3. The standard library function `std::move_if_noexcept` encodes exactly this decision.

```cpp title="move-if-noexcept.cpp" run ok
#include <vector>
#include <cstdio>

struct MayThrow {               // move constructor without noexcept
  MayThrow() = default;
  MayThrow(const MayThrow&) { std::puts("copy"); }
  MayThrow(MayThrow&&)      { std::puts("move"); }
};
struct NoThrow {
  NoThrow() = default;
  NoThrow(const NoThrow&) { std::puts("copy"); }
  NoThrow(NoThrow&&) noexcept { std::puts("move"); }
};

int main() {
  std::vector<MayThrow> a(1);
  std::puts("-- MayThrow");
  a.emplace_back();             // grows; the old element is copied
  std::vector<NoThrow> b(1);
  std::puts("-- NoThrow");
  b.emplace_back();             // grows; the old element is moved
}
```

In our tests the output is `-- MayThrow`, `copy`, `-- NoThrow`, `move`, in that order. The practical conclusion: move constructors should be `noexcept`. An implicitly generated move constructor gets the correct exception specification automatically ([[except.spec]]); a hand-written one needs it added, or it will be copied on every growth once placed in a `vector`.

!!! warning "Insertion in the middle has no strong guarantee"
    When `insert` or `emplace` in the middle throws from `T`'s copy or move constructor or assignment, the standard does not guarantee there is no effect, because some elements may already have been shifted. If you need the strong guarantee, operate on a copy and swap after success.

### Range insertion reallocates at most once (¶3)

¶3 `insert_range` and `append_range` reallocate at most once under the same two conditions as range construction (see ¶13 above); the iterator-pair versions at most once if the iterators meet *Cpp17ForwardIterator*. This rules out the naive implementation of repeated `push_back`.

## Erasure ([vector.modifiers], [vector.erasure])

¶4–¶6 `erase` and `pop_back`:

- invalidate iterators and references at or after the point of the erase, including the past-the-end iterator;
- throw nothing unless `T`'s copy assignment or move assignment throws;
- call the destructor of `T` as many times as the number of elements erased, and the assignment operator as many times as the number of elements after the erased elements.

The third point specifies the "assign the later elements forward one by one" implementation and excludes relocating to new storage. So `erase` never reallocates, and pointers before the erasure point are always valid.

[vector.erasure] ¶1–¶2 The C++20 non-member functions `std::erase(c, value)` and `std::erase_if(c, pred)` are equivalent to the remove-erase idiom: `remove` or `remove_if` first, then `c.erase(it, c.end())`, returning the number of elements erased.

```cpp run ok
#include <vector>
#include <cassert>

int main() {
  std::vector<int> c{1, 2, 3, 4, 5, 6};
  auto n = std::erase_if(c, [](int x) { return x % 2 == 0; });
  assert(n == 3 && (c == std::vector<int>{1, 3, 5}));
}
```

In the current draft, the second template parameter of `erase` is written `class U = T`, so for a `vector<pair<int, int>>` you can also write `std::erase(v, {1, 2})`, with the braced argument deduced as `T`. libc++ in Clang 23 does not have this default argument yet, and that call reports no matching function.

## constexpr vector

Since C++20, `vector` can be used in constant evaluation, but memory allocated during constant evaluation must be released before that same evaluation ends ([[expr.const]]; see [[g:transient-allocation]]). Using a `vector` inside a `constexpr` function that returns only a scalar is fine; a `constexpr` variable that is itself a `vector` is not:

<div class="compare" markdown="1">

```cpp run ok
#include <vector>
constexpr int sum_squares(int n) {
  std::vector<int> v;
  for (int i = 1; i <= n; ++i)
    v.push_back(i * i);
  int s = 0;
  for (int x : v) s += x;
  return s;   // v has been released inside the function
}
static_assert(sum_squares(3) == 14);
```

```cpp run error
#include <vector>
// error: the allocated memory is not
// released before constant evaluation ends
constexpr std::vector<int> v{1, 2, 3};
```

</div>

Clang's diagnostic for the right-hand side is `constexpr variable 'v' must be initialized by a constant expression`.

## The libc++ implementation

{{impl}} The following comes from testing and reading the source (`<__vector/vector.h>`) of libc++ with Homebrew Clang 23.

- **Growth factor 2**: when growth is needed, the new capacity is `max(2 * capacity(), new_size)`, or `max_size()` near the limit. With 2000 successive `push_back`s, the capacity goes 1, 2, 4, …, 2048. libstdc++ also uses 2, MSVC STL uses 1.5. The standard only requires amortized constant time and does not prescribe a factor.
- **Relocation**: on growth, each element is relocated with `allocator_traits::construct(…, std::move_if_noexcept(*it))`, and on failure an exception guard destroys the new elements already constructed; this implements the strong guarantee described above.
- **Trivial relocation**: if libc++ considers `T` trivially relocatable (trivially copyable types, plus types libc++ explicitly marks such as `unique_ptr` and `string`) and the allocator's `construct` and `destroy` are the defaults, growth simply `memcpy`s the old storage without calling move constructors and destructors. By the as-if rule this does not change observable behavior.
- **Hardening modes**: under `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG`, an out-of-bounds `operator[]` prints `vector[] index out of bounds` and terminates; in `_FAST` mode it traps and terminates without a message.
- **Container annotations**: see the `container-overflow` at the start of this page.

## Common misconceptions

!!! pitfall "Saving `&v[i]` and then continuing to `push_back`"
    Unless enough capacity was `reserve`d beforehand, the next growth leaves this pointer dangling. If you need stable addresses, use `reserve` to establish a no-reallocation guarantee, switch to `deque` (insertion at either end does not invalidate references to elements), or store indices instead of pointers.

!!! pitfall "`std::vector<T> v(n);` followed by `push_back`"
    `v(n)` has already created n elements, and `push_back` puts the new element in position n+1. If you only want to reserve space, write `v.reserve(n)`.

!!! pitfall "`shrink_to_fit()` always releases memory"
    It is a non-binding request (¶9). When you need a reliable release, swap with an empty vector.

## Questions

!!! question "Question 1"
    Does `std::vector<std::unique_ptr<int>>::push_back` have the strong exception guarantee?

<details markdown="1">
<summary>Answer</summary>

Yes. `unique_ptr` is not copyable, but its move constructor is `noexcept`, which satisfies the condition in ¶2 that `is_nothrow_move_constructible_v<T>` is true. So if inserting a single element at the end throws (which can only be an allocation failure), there is no effect. The guarantee is lost only for move-only types whose move constructor may throw, such as a user type with a deleted copy constructor and a move constructor not declared `noexcept`.
</details>

!!! question "Question 2"
    `v.insert(v.begin(), x)` does not reallocate. Is a reference `r` previously bound to `v[0]` still valid?

<details markdown="1">
<summary>Answer</summary>

No. Per ¶2, without reallocation, references at and after the insertion point are invalidated, and `v[0]` is right at the insertion point. Physically `r` still points to the same memory, which now holds the newly inserted `x`, but the standard does not guarantee what an invalidated reference refers to. In practice it will most likely read `x`, but relying on that is relying on an implementation detail.
</details>

## Summary

| Aspect | Rule |
|---|---|
| Storage | One block of contiguous storage; no objects in `[size, capacity)` |
| Growth | The complexity requirements force geometric growth; libc++ uses a factor of 2 |
| `reserve` | Only grows, never shrinks; insertions afterwards are guaranteed not to reallocate until the capacity is used up |
| Invalidation | Reallocation: everything; otherwise at and after the point of insertion or erasure (including the past-the-end iterator) |
| Exceptions | Single-element insertion at the end: strong guarantee if `T` is copyable or its move does not throw; none for insertion in the middle |
| `erase` | Never reallocates; the number of assignments equals the number of elements after the erasure point |
| constexpr | Usable in constant evaluation since C++20; allocations must be released within the same evaluation |
