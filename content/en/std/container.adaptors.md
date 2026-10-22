---
title: Container adaptors
summary: "stack, queue and priority_queue wrap an underlying container and expose only part of its interface, inheriting its complexity, exceptions and preconditions; why pop() returns void, priority_queue's strict-weak-ordering assumption, and the deduction and invalidation rules shared by all adaptors."
updated: 2026-10-19
---

!!! tldr
    - An adaptor holds an underlying container, and most member functions are one-line forwards; `stack::top()`, for example, is just `c.back()`. Complexity, exception guarantees, reference invalidation and preconditions all depend on the underlying container.
    - `pop()` returns `void` to separate "retrieving the element" from "removing the element", so that no data is lost if a copy throws.
    - `priority_queue` is a max-heap ordered by the comparator, which must be a strict weak ordering; using `double`s that include NaN scrambles the dequeue order, usually undetectably.
    - The `protected` members `c` and `comp` are an interface specified by the standard, and derived classes may rely on them, for example to add `reserve` to a `priority_queue`.
    - The classic adaptors have no iterators and are not ranges; formatting prints the underlying container's storage order; `priority_queue` has no `==`.

A **container adaptor** ([[g:container-adaptor]]) does not manage memory or implement a data structure itself. It holds an ordinary container and narrows its interface to some abstraction: a stack can only operate on its top, a queue only adds at the back and removes from the front, a priority queue only shows its largest element.

[container.adaptors] has seven class templates in total:

| Adaptor | Header | Default underlying container | Underlying container must support | Iterators |
|---|---|---|---|---|
| `stack` | `<stack>` | `deque<T>` | `back`, `push_back`, `pop_back` | None |
| `queue` | `<queue>` | `deque<T>` | `front`, `back`, `push_back`, `pop_front` | None |
| `priority_queue` | `<queue>` | `vector<T>` | Random access iterators, `front`, `push_back`, `pop_back` | None |
| `flat_map`, `flat_multimap` | `<flat_map>` | Two `vector`s | Random-access sequence containers | Random access |
| `flat_set`, `flat_multiset` | `<flat_set>` | `vector<Key>` | Random-access sequence containers | Random access (constant) |

The first three have existed since C++98 and are called the classic adaptors below. The last four are the flat associative containers added in C++23 ([[P0429R9]], [[P1222R4]]), much larger and more complex in semantics; see [[flat.map]] and [[flat.set]]. The rules shared by all adaptors ([container.adaptors.general]) are covered together at the end.

## All behavior comes from the underlying container

Almost all members of the classic adaptors are defined directly in the class synopsis: `queue::front()` is simply `{ return c.front(); }`, `stack::pop()` is simply `{ c.pop_back(); }`. So the following conclusions are not written out literally in the wording, but they are entirely determined:

1. **Complexity** equals that of the underlying operation. `stack<T, vector<T>>::push` is amortized constant time; `stack<T, list<T>>::push` is strictly constant time.
2. **Exception guarantees** depend on the underlying operation. Whether `push` has the strong guarantee depends on whether `c.push_back` has it; for [[vector]], it does not when the element type is not copyable and its move constructor may throw.
3. **Preconditions** likewise. Calling `front()`, `back()`, `top()` or `pop()` on an empty adaptor has the consequences of calling `c.front()`, `c.back()`, `c.pop_front()` or `c.pop_back()` on an empty container. Since C++26 these four operations have hardened preconditions in [[sequence.reqmts]] ([[sequence.reqmts#72]], [[sequence.reqmts#76]], [[sequence.reqmts#114]], [[sequence.reqmts#118]]): in a hardened implementation a violation terminates as a contract violation, and in a non-hardened implementation it is still {{ub}}.
4. **Reference invalidation** likewise. The reference returned by `top()` of a `stack<int, vector<int>>` dangles after the next `push` that triggers a reallocation; the default `stack<int>` uses [[deque]], whose insertion at either end does not invalidate references, so it does not.

Compiled with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` in our tests, libc++ terminates with `SIGTRAP` on `stack::pop`, `queue::pop`, `priority_queue::pop` and `priority_queue::top` called on empty adaptors. libc++ does no separate checking at the adaptor level; what fires is the underlying container's assertion.

`priority_queue::pop()` is not a one-line forward but `pop_heap(c.begin(), c.end(), comp); c.pop_back();`. [[pop.heap#2]] requires the range to be a valid non-empty heap, which is an ordinary precondition, not hardened. So strictly speaking, `pop()` on an empty `priority_queue` is already UB before any hardening check. libc++'s `pop_heap` does nothing for an empty range, and then the hardening check in `c.pop_back()` terminates the program.

## queue and stack

### Requirements on the underlying container ([queue.defn] ¶1, [stack.general] ¶1)

[queue.defn] ¶1 Any sequence container supporting `front()`, `back()`, `push_back()` and `pop_front()` can be used to instantiate `queue`, in particular [[list]] and [[deque]]. [[vector]] has no `pop_front`.

[stack.general] ¶1 `stack` needs only `back()`, `push_back()` and `pop_back()`; `vector`, `list` and `deque` all work.

These requirements are not *Constraints* (the kind that removes a function from overload resolution when unmet) but a description of the template argument. Member functions of a class template are instantiated only when used ([[temp.inst]]), so a container that does not meet the requirements causes an error only when a missing member is actually called:

<div class="compare" markdown="1">

```cpp run ok
#include <queue>
#include <vector>
int main() {
  std::queue<int, std::vector<int>> q;
  q.push(1);         // needs only push_back
  return q.back();
}
```

```cpp run error
#include <queue>
#include <vector>
int main() {
  std::queue<int, std::vector<int>> q;
  q.push(1);
  q.pop();   // error: no pop_front
}
```

</div>

### Interface ([queue.defn], [stack.defn])

| Member | `queue` | `stack` |
|---|---|---|
| Access | `front()` is `c.front()`, `back()` is `c.back()` | `top()` is `c.back()` |
| Insertion | `push(x)` is `c.push_back(x)` | Same |
| In-place construction | `emplace(args...)` is `return c.emplace_back(args...)` | Same |
| Range insertion {{c++23}} | `push_range(rg)` ([queue.mod] ¶1) | `push_range(rg)` ([stack.mod] ¶1) |
| Removal | `pop()` is `c.pop_front()` | `pop()` is `c.pop_back()` |
| Swap | `swap(q)`, `noexcept(is_nothrow_swappable_v<Container>)` | Same |

The return type of `emplace` is `decltype(auto)`. Since C++17, `emplace_back` of the sequence containers returns a reference to the new element, and the adaptor returns it unchanged. `priority_queue::emplace`, however, returns `void`, because after `push_heap` the new element's position is no longer known.

In the current draft, all members (constructors included) are `constexpr`.

[queue.mod] ¶1 `push_range(rg)` uses `c.append_range(std::forward<R>(rg))` if that is a valid expression, and otherwise falls back to `ranges::copy(rg, back_inserter(c))`. So custom containers without `append_range` work too.

### Constructors ([queue.cons], [stack.cons])

| Paragraph | Signature | Effect |
|---|---|---|
| ¶1 | `explicit queue(const Container& cont)` | Initializes `c` with `cont` |
| ¶2 | `explicit queue(Container&& cont)` | Initializes `c` with `std::move(cont)` |
| ¶3 | `queue(InputIterator first, InputIterator last)` {{c++23}} | Initializes `c` with `first, last` |
| ¶4 | `queue(from_range_t, R&& rg)` {{c++23}} | Initializes `c` with `ranges::to<Container>(std::forward<R>(rg))` |

[stack.cons] ¶1–¶4 are the same. The iterator-pair constructors come from [[P1425R4]], and `from_range` construction and `push_range` from [[P1206R7]].

The default constructor is written separately as `queue() : queue(Container()) {}` and is not `explicit`. Before C++20 it was provided through an `explicit` constructor with a default argument, which made default construction `explicit` too, so copy-list-initialization like `std::queue<int> q = {};` failed. C++20 split it out.

### Allocator-extended constructors ([queue.cons.alloc], [stack.cons.alloc])

¶1 is the switch for the whole subclause:

!!! std
    If `uses_allocator_v<container_type, Alloc>` is `false` the constructors in this subclause shall not participate in overload resolution.

¶2–¶8 all pass the allocator as the last argument to the construction of `c`: `queue(a)` initializes `c` with `a`, `queue(cont, a)` with `cont, a`, `queue(q, a)` with `q.c, a`, and the `from_range` version calls `ranges::to<Container>(std::forward<R>(rg), a)`.

These constructors let adaptors take part in uses-allocator construction ([[allocator.uses]]). The standard specializes `uses_allocator` for each adaptor to inherit from `uses_allocator<Container, Alloc>`. So the outer allocator of a `std::pmr::vector<std::stack<int, std::pmr::vector<int>>>` is automatically passed to the underlying container of each inner `stack`.

### Comparison ([queue.ops], [stack.ops])

¶1–¶6 The six relational operators all return `x.c op y.c`; ¶7's `operator<=>` requires `three_way_comparable<Container>` and returns `x.c <=> y.c`. Two stacks are equal if and only if their underlying sequences are equal element by element, not merely when their tops match.

Besides `==` and `<=>`, `!=`, `<` and the rest are still declared separately. That way, when the underlying container has only `<` and no `<=>`, the adaptor's `<` still works.

## Why pop() returns void

```cpp run title="pop-returns-void.cpp" error
#include <stack>

int main() {
  std::stack<int> s;
  s.push(1);
  int x = s.pop();   // error: pop() returns void
}
```

`pop()` of all three classic adaptors returns `void`, so retrieving and removing takes two statements: `auto x = s.top(); s.pop();`. This is for exception safety. Suppose `pop()` returned the element:

```cpp
T pop() {
  T tmp = std::move(c.back());   // (a)
  c.pop_back();                  // (b) the element has been removed from the container
  return tmp;                    // (c) constructing the return value: may throw
}
```

If step (c) throws while copying `tmp` to the caller, the element has already been removed from the stack without reaching the caller; the data is lost, and a strong exception guarantee is impossible. Separating observation (`top`) from modification (`pop`) means `top()` returns a reference and cannot throw, the copy happens on the caller's side, and even if it throws the stack is intact; `pop()` only destroys and can be non-throwing. This problem was first raised by Tom Cargill in his 1994 article *Exception Handling: A False Sense of Security*.

C++17's guaranteed copy elision did not make this reasoning obsolete. `return tmp;` returns a named object, and named return value optimization is still optional; besides, an assignment like `x = s.pop();` may throw as well. Modern concurrent queues often provide variants like `bool try_pop(T& out)` or one returning `optional<T>`, at the cost of requiring `T`'s move not to throw or accepting a weaker guarantee.

!!! lawyer "Stealing the element out of priority_queue::top()"
    `priority_queue::top()` has only a const version returning `const_reference`, because modifying the top could break the heap property. A common idiom is `T x = std::move(const_cast<T&>(pq.top())); pq.pop();`. The underlying element is not itself a const object, so modifying it after `const_cast` does not violate [[dcl.type.cv]].

    But the following `pop()` calls `pop_heap`, whose precondition requires the whole range to be a valid heap ([[pop.heap#2]]). The moved-from top (say, now an empty string) may already be less than its children, which by the letter of the wording is {{ub}}. libc++'s `pop_heap` moves the top out first and then sifts the hole down, never comparing the original top again, so the idiom happens to work, but it relies on an implementation detail.

## priority_queue

### Heaps and strict weak ordering ([priqueue.overview] ¶1)

¶1 Any sequence container with random access iterators that supports `front()`, `push_back()` and `pop_back()` can be used to instantiate `priority_queue`, in particular `vector` (the default) and `deque`. The same paragraph states an assumption:

> the library assumes that the function or function object defines a strict weak ordering.

The library assumes the comparator is a **strict weak ordering** ([[g:strict-weak-ordering]], [[alg.sorting]]). If this assumption fails, the preconditions of all later `make_heap`, `push_heap` and `pop_heap` calls lose their meaning. The preconditions of the constructors repeat this too ([priqueue.cons] ¶1, ¶3, ¶5, ¶7).

The entire state of a `priority_queue` is `c` and `comp`, and `c` is always a max-heap with respect to `comp` ([[alg.heap.operations]]). `top()` returns `c.front()`; the top of the heap is the first element of the range, the largest element according to `comp`. So `priority_queue<int, vector<int>, greater<int>>` is a min-heap: the comparison is reversed, and so is "largest".

### Violating strict weak ordering: NaN

`double`'s `<` is not a strict weak ordering when NaN is involved: `NaN < x` and `x < NaN` are both false, so NaN is equivalent to every number, and equivalence is no longer transitive (1 is equivalent to NaN, NaN to 5, but 1 < 5).

```cpp run title="pq-nan.cpp" ub
#include <queue>
#include <limits>
#include <cstdio>

int main() {
  constexpr double nan = std::numeric_limits<double>::quiet_NaN();
  std::priority_queue<double> pq;
  for (double d : {1.0, 2.0, nan, 3.0, 4.0, 5.0})
    pq.push(d);   // UB: NaN breaks the strict weak ordering
  while (!pq.empty()) { std::printf("%g ", pq.top()); pq.pop(); }
  std::printf("\n");
}
```

With libc++ (Clang 23) this prints `4 5 3 2 1 nan`, with 4 ahead of 5, and a different insertion order gives a different result. Turning on `_LIBCPP_HARDENING_MODE_DEBUG` does not catch it either: the library cannot verify a global ordering relation within an O(log N) `push`. The fix is to make the comparator handle NaN explicitly (for example treating NaN as smallest), or to filter NaNs out before enqueueing.

### Constructors ([priqueue.cons], [priqueue.cons.alloc])

Every constructor that puts elements in finishes with `make_heap(c.begin(), c.end(), comp)`, turning an arbitrary sequence into a heap. [[make.heap]] makes at most 3N comparisons, linear time.

| Paragraph | Signature | Effect |
|---|---|---|
| ¶1–¶2 | `priority_queue(const Compare& x, const Container& y)`, and the `Container&&` version | Initializes `comp` with `x`, constructs `c` from `y`, then `make_heap` |
| ¶3–¶4 | `priority_queue(first, last, const Compare& x = Compare())` | Initializes `c` with `first, last` and `comp` with `x`, then `make_heap` |
| ¶5–¶6 | `priority_queue(first, last, x, const Container& y)`, and the `Container&&` version | Initializes `c` with `y` first, then `c.insert(c.end(), first, last)`, finally `make_heap` |
| ¶7–¶8 | `priority_queue(from_range_t, R&& rg, const Compare& x = Compare())` {{c++23}} | `c` is `ranges::to<Container>(std::forward<R>(rg))`, then `make_heap` |

Handing a whole batch of data to the constructor at once is O(N); `push`ing one at a time is O(N log N). Collecting first and building the heap afterwards is a common optimization.

[priqueue.cons.alloc] ¶1 is the same as for queue and stack: if `uses_allocator_v<container_type, Alloc>` is false, all these constructors drop out of overload resolution. ¶2–¶13 follow the same pattern too: the allocator goes to the construction of `c`; versions that take no comparator value-initialize `comp`; versions that put elements in end with `make_heap`; ¶6–¶7, which only copy or move from another `priority_queue`, do not need to, because the source is already a heap.

### Members ([priqueue.members])

| Paragraph | Member | Effect |
|---|---|---|
| ¶1–¶2 | `push(x)` | `c.push_back(x); push_heap(c.begin(), c.end(), comp);` |
| ¶3–¶4 | `push_range(rg)` {{c++23}} | Appends all elements first (`append_range` or `ranges::copy`), then restores the heap property as if by `make_heap`; postcondition `is_heap(c.begin(), c.end(), comp)` |
| ¶5 | `emplace(args...)` | `c.emplace_back(...); push_heap(...)`, returns `void` |
| ¶6 | `pop()` | `pop_heap(c.begin(), c.end(), comp); c.pop_back();` |

`push_range` does not specify one `push_heap` per element (M log(N+M) for M elements); it says the heap property is restored as if by `make_heap` (O(N+M)), and ¶4 only requires the result to be a heap. When M is much smaller than N, inserting one by one is actually faster, so the implementation can choose the algorithm based on M and N. It also follows that neither the arrangement of equivalent elements in the heap nor the order in which equivalent elements are later `pop`ped can be relied upon.

The class synopsis ends with the comment "no equality is provided": `priority_queue` has no `==` and no `<=>`. Two heaps containing the same elements can be arranged differently internally, comparing `c` element by element is meaningless, and comparing as multisets would take O(N log N).

```cpp run title="pq-no-equality.cpp" error
#include <queue>

int main() {
  std::priority_queue<int> a, b;
  return a == b;   // error: priority_queue has no operator==
}
```

[priqueue.special] ¶1–¶2 The non-member `swap` requires both `is_swappable_v<Container>` and `is_swappable_v<Compare>` to be true, with effects as if by `x.swap(y)`. The member `swap` swaps `c` and then `comp`.

## The protected member c: an interface for derived classes

The class definitions of all three classic adaptors contain:

```cpp
protected:
  Container c;          // stack, queue, priority_queue
  Compare comp;         // priority_queue only
```

These are not exposition-only members (the private members marked `// exposition only` in the flat family are); they are part of the normative interface: the members must be named `c` and `comp`, and their access must be `protected`. So derived classes may legitimately rely on them; a common use is adding `reserve` or `clear` to a `priority_queue`:

```cpp run title="reservable-pq.cpp" ok
#include <queue>
#include <cassert>

template<class T>
struct reservable_pq : std::priority_queue<T> {
  void reserve(std::size_t n) { this->c.reserve(n); }
  void clear() noexcept { this->c.clear(); }   // an empty sequence is always a heap
  const auto& underlying() const { return this->c; }
};

int main() {
  reservable_pq<int> pq;
  pq.reserve(1024);
  for (int i : {3, 1, 4, 1, 5}) pq.push(i);
  assert(pq.top() == 5);
  assert(pq.underlying().capacity() >= 1024);
  pq.clear();
  assert(pq.empty());
}
```

!!! pitfall "A derived class must maintain the heap invariant itself"
    All public members of `priority_queue` assume `c` is a valid heap with respect to `comp`. If a derived class rewrites elements of `c` directly without re-running `make_heap`, subsequent `push` and `pop` calls violate the preconditions of [[push.heap]] and [[pop.heap]], which is {{ub}}. `clear()` in the example is safe because an empty range is always a heap.

## C++23 range support and formatting

```cpp run title="adaptors-ranges.cpp" ok
#include <queue>
#include <stack>
#include <vector>
#include <list>
#include <ranges>
#include <cassert>
#include <type_traits>

int main() {
  std::vector<int> v{3, 1, 4, 1, 5};

  std::stack s(v.begin(), v.end());              // iterator pair + deduction guide
  static_assert(std::is_same_v<decltype(s), std::stack<int>>);   // underlying container is deque<int>

  std::queue q(std::from_range, v | std::views::take(3));
  q.push_range(std::vector{9, 2, 6});
  assert(q.size() == 6 && q.front() == 3 && q.back() == 6);

  std::priority_queue pq(std::from_range, v);
  pq.push_range(std::list{9, 2});                // any input range with a convertible element type
  assert(pq.top() == 9);

  std::stack<int, std::vector<int>> sv;
  int& top = sv.emplace(42);                     // returns the result of emplace_back
  assert(&top == &sv.top());

  // the adaptors themselves are not ranges: no begin() and end()
  static_assert(!std::ranges::range<std::stack<int>>);
  static_assert(!std::ranges::range<std::priority_queue<int>>);
}
```

The last two lines show the essence of the classic adaptors: no iterators. A stack's contract is that only the top is visible; providing traversal would amount to admitting it is just a `deque`. When you really need to traverse, use the underlying container directly, or access `c` through a derived class as in the previous section.

### Formatting ([container.adaptors.format])

¶1 For `queue`, `priority_queue` and `stack`, the standard library provides `formatter` specializations, which require the underlying container itself to be formattable. It has a single exposition-only member `underlying_`, a range formatter for the underlying container. ¶2 `parse` forwards to `underlying_`. ¶3:

!!! std
    *Effects*: Equivalent to: `return underlying_.format(r.c, ctx);`

So what gets printed is the underlying container's storage order, not the pop order and not the priority order:

```cpp run title="adaptor-format.cpp" ok
#include <queue>
#include <stack>
#include <print>

int main() {
  std::stack<int> s;
  for (int i : {3, 1, 4}) s.push(i);
  std::priority_queue<int> pq;
  for (int i : {3, 1, 4, 1, 5}) pq.push(i);

  std::println("{}", s);    // [3, 1, 4]: bottom on the left, top on the right
  std::println("{}", pq);   // the heap array's arrangement; [5, 4, 3, 1, 1] with libc++ (Clang 23)
}
```

Range format specifiers work as usual; for example `"{::02}"` applies to each element. This specialization was added with the C++23 range formatting proposal [[P2286R8]].

The synopses of the three headers also specialize `enable_nonlocking_formatter_optimization` to `false` for these three adaptors. `std::print` by default locks the output stream during formatting; types for which this variable is true allow the implementation to format into a buffer first and then write it out at once ([[format.formatter.spec]]). Formatting an adaptor calls the formatters of the underlying container and element type, and the library cannot tell whether that user code interacts safely with the stream lock, so it conservatively sets the variable to `false`.

## Rules shared by all adaptors ([container.adaptors.general])

The rules in this subclause also apply to the flat family, and several were written mainly for it.

### T must be Container::value_type (¶1–¶2)

¶1 lists which adaptors each header defines. ¶2 specifies the basic shape of an adaptor: each adaptor has one or more template parameters named `Container`, `KeyContainer` or `MappedContainer`; at least one constructor takes such a container by reference and copies or moves it in; if the container takes an allocator, a compatible allocator can also be passed to the constructor.

!!! std
    For the container adaptors that take a single container template parameter `Container`, the first template parameter `T` of the container adaptor shall denote the same type as `Container::value_type`.

Only "shall" is written here, with no consequence stated for violations; the flat family, in [[flat.map#8]], makes the same kind of requirement explicitly ill-formed. In practice the two have the same effect: libc++ puts a `static_assert` in the class body of `stack`, `queue` and `priority_queue`:

```cpp run title="value-type-mismatch.cpp" error
#include <stack>
#include <vector>

int main() {
  std::stack<long, std::vector<int>> s;   // error: T is long, Container::value_type is int
  s.push(1);
}
```

The adaptor's `value_type` and other member types are all taken from `Container`, and `T` is hardly used in the class definition. It is redundant information, and redundant information must be consistent, or you get confusing results like `stack<long, vector<int>>::value_type` being `int`.

### swap throws nothing extra (¶3)

¶3 An adaptor's `swap` throws only if the `swap` of the underlying container or of `Compare` throws. For each adaptor, the member `swap` is `noexcept(is_nothrow_swappable_v<Container>)` (plus `Compare` for `priority_queue`); the non-member `swap` is `noexcept(noexcept(x.swap(y)))` and requires `is_swappable_v<Container>` (¶1–¶2 of [queue.special], [stack.special] and [priqueue.special]).

### Reference invalidation is that of the underlying container (¶5)

!!! std
    the `insert`, `emplace`, and `erase` members affect the validity of iterators, references, and pointers to the adaptor's container(s) in the same way that the containers' respective `insert`, `emplace`, and `erase` members do.

This rule was written mainly for the flat family. The wording's own example says `flat_map::insert` may invalidate all iterators, because the default underlying container is `vector`. The flat containers state in [[flat.map#2]] that they do not meet the invalidation requirements of associative containers (insertion into a `std::map` invalidates no iterators), and ¶5 is the replacement rule. The classic adaptors have no `insert` or `erase`; for `emplace`, see item 4 in the first section.

### Excluding unqualified types during deduction (¶4, ¶6–¶8)

¶4 A constructor template with an `InputIterator` template parameter does not participate in overload resolution if the deduced type does not qualify as an input iterator.

¶6 A deduction guide does not participate in overload resolution in the following cases:

| Item | Condition | Misdeduction prevented |
|---|---|---|
| ¶6.1 | `InputIterator` is deduced to a type that is not an input iterator | Treating two integers as an iterator pair |
| ¶6.2 | `Compare` is deduced to an allocator | `priority_queue(first, last, alloc)` taking the allocator as the comparator |
| ¶6.3 | `Container`, `KeyContainer` or `MappedContainer` is deduced to an allocator | Taking an allocator as the container |
| ¶6.4 | There is no container parameter but there is an `Allocator` parameter, and it is deduced to something that is not an allocator | Taking a comparator as the allocator |
| ¶6.5, ¶6.6, ¶6.8 | There are both a container parameter and `Allocator`, but `uses_allocator_v<container, Allocator>` is false | Pairing an incompatible container with an allocator |
| ¶6.7 | There are `KeyContainer` and `Compare`, but `Compare` cannot compare two `const KeyContainer::value_type&` | Taking a container or allocator as the comparator |

What qualifies as an input iterator or allocator is specified by [[container.reqmts#69]], with deliberate latitude: the extent to which an implementation determines that a type is not an input iterator or not an allocator is unspecified. The standard only sets a minimum: integral types never qualify as input iterators; a type `A` qualifies as an allocator only if at least `A::value_type` exists and `declval<A&>().allocate(size_t{})` is well-formed. This is a purely syntactic test that does not check semantics.

```cpp run title="adaptor-ctad.cpp" ok
#include <queue>
#include <flat_map>
#include <deque>
#include <vector>
#include <string>
#include <memory_resource>
#include <type_traits>
#include <cassert>

int main() {
  std::vector<int> v{5, 1, 4};
  std::pmr::polymorphic_allocator<int> pa;

  // ¶6.2: the third argument is an allocator, so guides with a Compare parameter are excluded
  std::priority_queue pq(v.begin(), v.end(), pa);
  static_assert(std::is_same_v<decltype(pq),
      std::priority_queue<int, std::vector<int, std::pmr::polymorphic_allocator<int>>>>);

  // two containers: all five template parameters of flat_map are deduced
  std::deque<std::string> ks{"b", "a"};
  std::deque<double> vs{2.0, 1.0};
  std::flat_map fm(std::move(ks), std::move(vs));
  static_assert(std::is_same_v<decltype(fm),
      std::flat_map<std::string, double, std::less<std::string>,
                    std::deque<std::string>, std::deque<double>>>);
  assert(fm.begin()->first == "a" && fm.begin()->second == 1.0);
}
```

¶6.5 seen from the other side: pairing an ordinary `std::vector<int>` with a `pmr::polymorphic_allocator` makes `uses_allocator_v` false, the `stack(Container, Allocator)` deduction guide drops out, and there is no other candidate:

```cpp run title="ctad-uses-allocator.cpp" error
#include <stack>
#include <vector>
#include <memory_resource>

int main() {
  std::vector<int> v;
  std::pmr::polymorphic_allocator<int> a;
  std::stack s(v, a);   // error: no viable deduction guide (¶6.5)
}
```

¶7–¶8 say the deduction guides may use several exposition-only alias templates: `iter-value-type` ([[sequences.general]]), `iter-key-type`, `iter-mapped-type`, `range-key-type` and `range-mapped-type` ([[associative.general]]), and `alloc-rebind`, newly defined in ¶8 as `allocator_traits<A>::rebind_alloc<T>`. The `from_range` deduction guides of the flat family use it to rebind one allocator for the key container and the value container separately.

## Implementation status

{{impl}} Test results with Homebrew Clang 23 and libc++:

- `priority_queue` is already fully `constexpr`; heaps can be built and popped in a `static_assert`.
- The members of `queue` and `stack` are not yet marked `constexpr`, and using them in constant evaluation fails. Yet libc++'s `<queue>` already defines `__cpp_lib_constexpr_queue` as `202502L`, inconsistent with the actual state of `std::queue`; `__cpp_lib_constexpr_stack` is not defined. Keep this in mind when writing `constexpr` code based on feature-test macros.
- The C++23 iterator-pair constructors, `from_range` and `push_range`, and formatting are all available.

## History

| Version | Change |
|---|---|
| C++98 | `stack`, `queue`, `priority_queue`; `protected` members `c` and `comp`; `pop()` returns `void` |
| C++11 | Move construction, `emplace`, allocator-extended constructors and `uses_allocator` specializations, member `swap` |
| C++17 | Deduction guides; `emplace` changed to return `decltype(auto)` |
| C++20 | `operator<=>`; the default constructor is no longer `explicit` |
| C++23 | Iterator-pair construction, `from_range` construction and `push_range`, formatting, the flat family |
| C++26 | All members `constexpr`; `front`, `back`, `pop_front` and `pop_back` of the underlying sequence containers become hardened preconditions, and the adaptors benefit through delegation |

## Questions

!!! question "Question 1"
    Why doesn't the standard use *Constraints* to reject `std::queue<int, std::vector<int>>` as soon as it is declared?

<details markdown="1">
<summary>Answer</summary>

[queue.defn] ¶1 only says that sequence containers supporting these operations can be used to instantiate `queue`; it is a description of the template argument. *Constraints* can only be attached to functions or function templates, deciding whether they participate in overload resolution ([[structure.specifications]]). Constraining the whole class template with a concept would break partially valid uses, like a queue that only uses `push` and `back`, and would break compatibility going back to C++98.
</details>

!!! question "Question 2"
    Why does `priority_queue::push_range` state the postcondition `is_heap(...)` explicitly while `push` does not?

<details markdown="1">
<summary>Answer</summary>

The effect of `push` is "as if by" a definite piece of code, `push_back` plus `push_heap`, and [[push.heap]] itself guarantees the result is a heap, so nothing more needs saying. The effect of `push_range` is that it restores the heap property as if by `make_heap`; by stating the postcondition explicitly, ¶4 makes clear that what is really constrained is the property that the result is a heap: the implementation is free to rebuild the whole range with `make_heap` or to `push_heap` element by element. For users, this means the arrangement of equivalent elements in the heap cannot be relied upon to follow any particular algorithm.
</details>

!!! question "Question 3"
    Two `std::stack<int>`s: one has 1, 2, 3 pushed in order; the other has 1, 2, 3, 4 pushed and then one `pop()`. Are they `==`? What about with `std::priority_queue<int>`?

<details markdown="1">
<summary>Answer</summary>

The underlying `deque`s of both `stack`s are `[1, 2, 3]`, and [stack.ops] ¶1 says `==` is just `x.c == y.c`, so they are equal. The comparison looks only at the currently stored sequence, not at the history of operations.

`priority_queue` has no `==`, so writing that is a compile error. Even comparing `c` through a derived class, two heaps containing the same elements may have different array arrangements, which is exactly why the standard does not provide `==`.
</details>

## Summary

| Aspect | Rule |
|---|---|
| Behavior | Complexity, exception guarantees, reference invalidation and preconditions (including hardened ones) are all determined by the underlying container |
| `pop()` | Returns `void`; separating observation from removal ensures exception safety |
| `priority_queue` | A max-heap with respect to `comp`; the comparator must be a strict weak ordering; no equality comparison |
| `c`, `comp` | A `protected` normative interface usable by derived classes, which must maintain the heap invariant |
| Traversal and output | No iterators, not a range; formatting prints the underlying container's storage order |
| Deduction | The rules of ¶6 tell containers, comparators, allocators and iterators apart; `uses_allocator` specializations let adaptors take part in uses-allocator construction |
