---
title: Node handles and insert_return_type
summary: A node handle is a move-only object that owns a single element extracted from a map, set or unordered container, and can insert it unchanged into another compatible container.
updated: 2026-10-19
---

!!! tldr
    - `extract` detaches an element, together with the node it lives in, from an associative container and hands it to a node handle; `insert(std::move(nh))` links the node back into a container. The element itself is never copied or moved.
    - Nodes can be exchanged only between containers with the same key type, mapped type and allocator type, both ordered or both unordered; the comparators and hashes may differ, and `map` and `multimap` can trade nodes.
    - A node handle's `key()` returns a non-const reference, and the standard explicitly allows modifying a `map` key through it. It is the only way to change a key without reallocating.
    - `insert(nh)` on a unique-key container returns `{position, inserted, node}`; on a key conflict the element comes back in `node` and is not lost.
    - A moved-from handle is always empty; an empty handle holds no allocator; discarding a non-empty handle destroys the element and deallocates the node normally.

## Changing a map key without copying the element

The element type of `std::map` is `pair<const Key, T>`. The key is const because changing it directly would break the order of the tree. Before C++17, changing an element's key meant `erase` followed by `insert`: the element was copied or moved once, and the node was deallocated and allocated again. `extract`, added in C++17, solves this ([[P0083R3]]):

```cpp title="node-handle.cpp" run ok
#include <map>
#include <string>
#include <cassert>

int main() {
  std::map<int, std::string> m{{1, "one"}, {2, "two"}, {3, "three"}};
  const std::string* p = &m.at(2);

  auto nh = m.extract(2);          // the node leaves m; the element stays where it is
  assert(nh && nh.key() == 2);
  nh.key() = 20;                   // allowed: key() returns a non-const reference
  auto [pos, inserted, node] = m.insert(std::move(nh));
  assert(inserted && !node && pos->first == 20);
  assert(&pos->second == p);       // the same std::string object

  std::multimap<int, std::string> mm;
  mm.insert(m.extract(1));         // map and multimap nodes are compatible
  assert(mm.count(1) == 1 && !m.contains(1));

  auto again = m.extract(3);
  m.emplace(3, "THREE");
  auto r = m.insert(std::move(again));   // key conflict: insertion fails
  assert(!r.inserted && r.node.mapped() == "three");
  assert(r.position->second == "THREE");
}
```

`&pos->second == p` shows that the `std::string` object never moved during the whole process: `extract` only unhooks the node from the tree, and `insert` hooks it back in.

A **node handle** ([[g:node-handle]]) is the object `extract` returns. It is move-only and owns a node and the element in it. Besides changing keys, it enables two things that were impossible before: transferring non-copyable, even non-movable, elements between containers, and keeping an element outside any container for a while before putting it back.

!!! warning "While the element is in a handle, do not access it through old pointers"
    In the example, `p` must not be dereferenced after `extract` and before `insert`. [[associative.reqmts#176]] says that accessing the element through previously obtained pointers and references while it is owned by a node handle is {{ub}}; once the element is successfully inserted, those pointers and references refer to the element in the container again. The example compares `p` only after insertion.

## Which containers can exchange nodes [container.node.overview]

¶1 A node handle accepts ownership of a single element from an associative container ([[associative.reqmts]]) or unordered associative container ([[unord.req]]), and can transfer that ownership to another container with compatible nodes. Containers with compatible nodes have the same `node_type`. Table 75 lists the combinations that can transfer in both directions:

| Container | Containers it can exchange nodes with |
|---|---|
| `map<K, T, C1, A>` | `map<K, T, C2, A>`, `multimap<K, T, C2, A>` |
| `set<K, C1, A>` | `set<K, C2, A>`, `multiset<K, C2, A>` |
| `unordered_map<K, T, H1, E1, A>` | `unordered_map<K, T, H2, E2, A>`, `unordered_multimap<K, T, H2, E2, A>` |
| `unordered_set<K, H1, E1, A>` | `unordered_set<K, H2, E2, A>`, `unordered_multiset<K, H2, E2, A>` |

The key type, mapped type and allocator type must be the same; the comparator, hash function and equality predicate may differ; transfer works between unique keys and equivalent keys. It does not work between ordered and unordered containers, because their node structures differ: one is a tree node, the other a node in a hash chain.

```cpp title="node-type-identity.cpp" run ok
#include <functional>
#include <set>
#include <type_traits>
using A = std::set<int>;
using B = std::multiset<int, std::greater<>>;
static_assert(std::is_same_v<A::node_type, B::node_type>);
int main() {}
```

On insertion, the node is positioned using the target container's own comparator or hash. Beyond type compatibility, at run time the two containers' allocators must compare equal; that is a precondition of `insert(nh)` ([[associative.reqmts#85]]).

## Structure of a node handle

¶3 The standard describes node handles with an exposition-only class template *node-handle*; each container's `node_type` is an unspecified specialization of it. It has two data members:

- `ptr_`: a pointer to a container node, of the allocator's `pointer` type rebound to the node type, which may be a fancy pointer;
- `alloc_`: an `optional<allocator_type>`.

¶2 A non-empty handle contains an allocator equal to the container's allocator at the time the element was extracted. An empty handle contains no allocator: `alloc_` is `nullopt`.

The public interface is small: default construction (giving an empty handle), move construction, move assignment, destruction; the observers `value()`, `key()`, `mapped()`, `get_allocator()`, `explicit operator bool` and `empty()`; and `swap`. There is no copy construction or copy assignment. Handles of the `set` family have `value()` but no `key()`/`mapped()`; those of the `map` family are the opposite. Every member except `key()` is `constexpr`.

## Moving and destruction [container.node.cons]

¶1 The move constructor takes over `nh.ptr_`, move constructs `alloc_`, and then sets `nh.ptr_` to null and `nh.alloc_` to `nullopt`. So a moved-from handle is always empty, not in a valid-but-unspecified state.

¶2–¶5 Move assignment first deals with its own node: if non-empty, it destroys the element with the allocator's `destroy` and deallocates the node. It then takes over `nh.ptr_`; if it was empty itself, or the allocator's `propagate_on_container_move_assignment` (POCMA) is true, it move assigns `alloc_`; finally it makes `nh` empty. It does not throw.

The precondition is: it is empty, or POCMA is true, or the two allocators compare equal. The reason is that if it is non-empty and does not take over the other allocator, it will later have to deallocate the node allocated by `nh`'s allocator using its own allocator, so the two must be equal.

### Destruction [container.node.dtor]

¶1 The destructor likewise destroys the element first and then deallocates the node. Dropping a non-empty handle does not leak; the element is destroyed normally.

## Observers and key() [container.node.observers]

| Member | Precondition | Returns |
|---|---|---|
| `value()` | Non-empty | A reference to the `value_type` object in the node (¶1–¶3) |
| `key()` | Non-empty | A non-const reference to the key member of `value_type` (¶4–¶7) |
| `mapped()` | Non-empty | A reference to the mapped member of `value_type` (¶8–¶10) |
| `get_allocator()` | Non-empty | `*alloc_` (¶11–¶13) |
| `operator bool` / `empty()` | None | `ptr_ != nullptr` / `ptr_ == nullptr` (¶14–¶15) |

None of these throw, but calling the first four on an empty handle violates the precondition and is {{ub}}.

¶7 The description of `key()` contains an unusual sentence:

!!! std
    *Remarks*: Modifying the key through the returned reference is permitted.

By the core-language rules, `first` of a `pair<const Key, T>` is a const object, and modifying it is UB ([[dcl.type.cv]]). This *Remarks* is a guarantee from the library: modifying the key through a node handle's `key()` is legal, and it is up to the implementation to deliver it in a way the compiler accepts.

Paragraph 4 of the overview ([[container.node.overview#4]]) hints at the usual implementation technique:

!!! std
    If a user-defined specialization of pair exists for pair<const Key, T> or pair<Key, T>, ... the behavior of operations involving node handles is undefined.

The implementation needs to access the same object sometimes as a `pair<const Key, T>` and sometimes as a `pair<Key, T>`, which requires the two to have the same layout. A user specialization of `pair` would break that assumption, so the standard makes it UB. `key()` is the only observer not marked `constexpr`; a reasonable guess is that this technique cannot work in constant evaluation.

## swap [container.node.modifiers]

¶1 Precondition: either handle is empty, or the allocator's `propagate_on_container_swap` (POCS) is true, or the two allocators compare equal. ¶2 The effect is to swap `ptr_`; if either handle is empty or POCS is true, `alloc_` is swapped as well. The exception specification is `noexcept(POCS || is_always_equal)`.

This is where an empty handle holding no allocator pays off: swapping with an empty handle is always valid, and the allocator travels with the node.

## insert_return_type [container.insert.return]

¶1 The associative and unordered containers with unique keys each have an `insert(node_type&&)` that returns the nested type `insert_return_type`. It is a specialization of the following exposition-only template:

```cpp
template<class Iterator, class NodeType>
struct insert-return-type {
  Iterator position;
  bool     inserted;
  NodeType node;
};
```

¶2 It has exactly these three data members, no base classes and no other members. So it is an aggregate and can be unpacked with a structured binding in the order `position`, `inserted`, `node`, as in the opening example.

The values of the three fields are specified by [[associative.reqmts#87]] and [[unord.req#118]]:

| Case | `inserted` | `position` | `node` |
|---|---|---|---|
| `nh` is empty | `false` | `end()` | Empty |
| Insertion succeeded | `true` | Points to the new element | Empty |
| An equivalent key already exists | `false` | Points to the existing element | The original `nh` |

`insert(nh)` on an equivalent-key container (`multimap` and so on) always succeeds and returns a plain `iterator`. The hinted `insert(p, nh)` returns `iterator` for every container; when insertion fails, `nh` is unchanged ([[associative.reqmts#97]]).

## Questions

!!! question "Question"
    Can a node of `std::map<int, std::string, std::less<>, A>` be inserted into `std::map<int, std::string, std::less<int>, A>`? Into `std::unordered_map<int, std::string>`?

<details markdown="1">
<summary>Answer</summary>

The first, yes. The key type, mapped type and allocator type are all the same and only the comparator differs, so per Table 75 the nodes are compatible and `node_type` is the same type. Insertion positions the node using the target container's comparator and may fail on a key conflict, in which case the node is returned through `insert_return_type::node`. At run time the two containers' allocators must also compare equal, or the precondition is violated.

The second, no. The `node_type` of an ordered container and that of an unordered container are different types, `unordered_map::insert` has no overload accepting it, and compilation fails.
</details>
