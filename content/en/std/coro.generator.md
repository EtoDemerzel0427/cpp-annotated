---
title: Range generators (std::generator)
summary: "C++23's std::generator turns a coroutine into a single-pass view: how the element types are derived from the template arguments, why co_yield of an lvalue makes a copy, how elements_of implements recursive generation, and pitfalls such as dangling reference parameters and begin being callable only once."
updated: 2026-10-19
---

!!! tldr
    - `std::generator<T>` is a coroutine return type that is also a view: each time the function body executes a `co_yield`, the loop traversing it gets one element.
    - It models only `input_range`: it is move-only and can be traversed only once; calling `begin()` twice on the same object is undefined behavior.
    - The default `generator<T>` hands out elements as `T&&`. When an lvalue is `co_yield`ed, the standard library first copies it, so a consumer moving from the element does not hollow out the coroutine's local variable.
    - `co_yield ranges::elements_of(g)` hands over another generator's elements one by one, and in a recursive generator the cost of each step does not depend on the recursion depth.
    - A coroutine stores only the reference parameter itself, not the referred-to object. Pass generator parameters by value where possible.

C++20 provided only the language machinery for coroutines ([[dcl.fct.def.coroutine]]), with no ready-made coroutine types. To write a function that can `co_yield`, you had to implement the promise type and the iterator yourself. C++23's [[P2502R2]] filled in the most common one: `std::generator` ([[g:range-generator]]), declared in `<generator>`.

!!! impl "The examples on this page have no verdict marks"
    Clang 23 + libc++ in our tests has no `<generator>` header yet, so the examples below are written to the standard and have not been compiled locally. libstdc++ (since GCC 14) already provides it; use the godbolt button to run them on GCC.

## The simplest generator [coroutine.generator.overview]

```cpp run
#include <generator>
#include <ranges>
#include <cstdio>
std::generator<int> ints(int start = 0) {
  while (true)
    co_yield start++;
}
int main() {
  for (int i : ints() | std::views::take(3))
    std::printf("%d ", i);       // 0 1 2
}
```

¶1 A `generator` presents a view of the elements yielded by the evaluation of a coroutine. ¶2 It produces its elements by repeatedly resuming the coroutine from which it was returned; each time the coroutine executes a `co_yield` statement, one element is produced.

`ints` is an infinite loop, yet the program ends normally. The reason is that generators are lazy: the coroutine suspends immediately after it is created, and runs to the next `co_yield` only when the loop traversing it asks for the next element. Once `take(3)` has three elements it stops asking, the coroutine stops running, and it is finally destroyed along with the generator object.

¶3 Every specialization of `generator` models `view` and `input_range`, so it can be connected directly to range adaptors like `views::take` ([[range.view]]). It owns the coroutine frame; its copy constructor is deleted and it can only be moved.

## Where the element types come from [coro.generator.class]

```cpp
template<class Ref, class Val = void, class Allocator = void>
class generator;
```

`Ref` and `Val` determine three types. *value* is the value type of the elements and *reference* is the type obtained by dereferencing the iterator, both exposition-only names; the public member type `yielded` is the type that `co_yield` accepts:

```cpp
using value     = conditional_t<is_void_v<Val>, remove_cvref_t<Ref>, Val>;
using reference = conditional_t<is_void_v<Val>, Ref&&, Ref>;
using yielded   = conditional_t<is_reference_v<reference>, reference, const reference&>;
```

| Form | *value* | *reference* | `yielded` |
|---|---|---|---|
| `generator<int>` | `int` | `int&&` | `int&&` |
| `generator<const int&>` | `int` | `const int&` | `const int&` |
| `generator<std::string&>` | `std::string` | `std::string&` | `std::string&` |
| `generator<int, int>` | `int` | `int` (prvalue) | `const int&` |

The first row is the most common. With a single argument, `generator<T>`, elements are handed to the consumer as the rvalue reference `T&&`, and the consumer may move from them. To make the consumer read-only, write `generator<const T&>`. To hand out elements by value, also write `Val` explicitly.

¶1 uses *Mandates* to check that these types are sensible: *value* must be a cv-unqualified object type, *reference* must be a reference type or a copy-constructible object type, and they must have a common reference type. Note 1 explains that these conditions ensure the iterator satisfies `input_iterator`.

## What `co_yield` does [coro.generator.promise]

`co_yield e` in a coroutine calls the promise object's `yield_value(e)` ([[expr.yield]]). `generator`'s promise type has two overloads for a single value:

```cpp
suspend_always yield_value(yielded val) noexcept;
auto yield_value(const remove_reference_t<yielded>& lval)
  requires is_rvalue_reference_v<yielded> && /* copy-constructible from lval */;
```

¶4 The first overload just records the address of its argument, `value_ = addressof(val)`, copying nothing. This is safe: if the operand of `co_yield` is a temporary, it is not destroyed until the end of the full-expression containing the `co_yield`, and the coroutine suspends in the middle of that expression, so the temporary is still alive when the consumer dereferences the iterator.

The second overload exists only when `yielded` is an rvalue reference, i.e. for the default `generator<T>`. When an lvalue is `co_yield`ed, the rvalue reference `T&&` cannot bind to it, so this overload is chosen. ¶7 The awaitable it returns stores a copy made from the lvalue, and `value_` points to that copy.

```cpp run
#include <generator>
#include <string>
#include <vector>
std::generator<std::string> names() {
  std::string s = "alice";
  co_yield s;                    // lvalue: a copy is handed out
  co_yield std::string("bob");   // prvalue: binds to string&&, no copy
  // s is still "alice"
}
int main() {
  std::vector<std::string> out;
  for (auto&& n : names())
    out.push_back(std::move(n)); // moves from the copy or the temporary
}
```

Without this copy, a consumer moving from the `T&&` would hollow out `s` in the coroutine directly, and the coroutine might still need it after resuming.

## Laziness, `begin()` and the iterator [coro.generator.members]

The promise's `initial_suspend()` returns `suspend_always`, so calling `ints()` executes not a single line of the function body. ¶9 Only the first call to `begin()` resumes the coroutine, which runs to the first `co_yield` or to the end of the function.

¶8 The precondition of `begin()` is that the coroutine is suspended at its initial suspend point. Note 4 accordingly points out that calling `begin()` twice on the same generator is {{ub}}: by the second call the coroutine has long left its initial suspend point.

The iterator ([[coro.generator.iterator]]) is simple:

- `*it` returns `static_cast<reference>(*p.value_)`, where `p` is the promise of the coroutine currently producing elements;
- `++it` resumes that coroutine, running it to the next `co_yield`;
- `it == default_sentinel` is true once the coroutine has finished, and `end()` returns exactly `default_sentinel`.

The iterator stores only a coroutine handle, not the address of the generator object. So Note 1 says that after a generator is moved, iterators obtained earlier remain valid and become iterators into the new object.

## Recursive generation: `elements_of`

The most natural way to traverse a tree in order is recursion. `co_yield ranges::elements_of(r)` yields each element of range `r` in turn as an element of this generator:

```cpp run
#include <generator>
#include <memory>
#include <ranges>
#include <cstdio>
struct Node { int v; std::unique_ptr<Node> l, r; };
std::generator<int> inorder(const Node* n) {
  if (!n) co_return;
  co_yield std::ranges::elements_of(inorder(n->l.get()));
  co_yield n->v;                 // a const int lvalue: a copy is handed out
  co_yield std::ranges::elements_of(inorder(n->r.get()));
}
int main() {
  Node root{2, std::make_unique<Node>(1, nullptr, nullptr),
               std::make_unique<Node>(3, nullptr, nullptr)};
  for (int x : inorder(&root)) std::printf("%d ", x);   // 1 2 3
}
```

### `elements_of` is a tag [range.elementsof]

`ranges::elements_of` is an aggregate with just two members, declared in `<ranges>`:

```cpp
template<range R, class Allocator = allocator<byte>>
struct elements_of {
  [[no_unique_address]] R range;
  [[no_unique_address]] Allocator allocator = Allocator();
};
```

Its role is to distinguish two meanings in overload resolution. For a `generator<std::any>`, `co_yield r` yields the range `r` itself as one element, while `co_yield ranges::elements_of(r)` yields the elements of `r` one by one.

### The active stack

The promise has two kinds of overloads for `elements_of`.

The first kind takes another `generator` and requires its `yielded` type to be the same. The returned awaitable moves the child generator in, pushes the child's handle onto a stack, and then resumes the child directly. That stack is `generator`'s private member `active_`, which records all the currently nested coroutines, with the one producing elements on top ([[coro.generator.promise#11]]).

The iterator's `++` always resumes the coroutine on top of the stack, and `*` always reads the value of the top coroutine. When a child generator finishes, its `final_suspend` pops itself off the stack and resumes the new top, i.e. the parent coroutine ([[coro.generator.promise#3]]). So however deep the recursion, getting the next element resumes only one coroutine. If each level forwarded with `for (auto x : child) co_yield x;`, getting one element would resume every level in turn, at a cost proportional to the depth.

The second kind takes any `input_range`. Per [[coro.generator.promise#13]], it wraps the range into a `generator<yielded, void, Alloc>` using an internal generator lambda, and hands that to the first kind of overload.

Note 2 of [[coro.generator.members#4]] adds that a child generator is owned by an awaitable in the parent coroutine's frame, so destroying the outermost generator destroys the whole stack along with it.

## Exceptions and `co_await`

When an exception thrown in the coroutine body is not caught, the promise's `unhandled_exception()` is called ([[coro.generator.promise#16]]):

- If this coroutine is the only one on the stack, i.e. the outermost generator, it is equivalent to `throw;`, and the exception propagates directly to the consumer from `begin()` or `++`;
- Otherwise it is a child generator nested via `elements_of`; the exception is first stored in the promise and rethrown by the awaitable's `await_resume` when the parent coroutine resumes. In this way the exception propagates outward along the stack, level by level.

The promise also declares a deleted `await_transform` with no parameters. Per [[expr.await]], as soon as the promise type has a member named `await_transform`, `co_await e` is rewritten to `co_await p.await_transform(e)`. This member is deleted and takes no arguments, so writing `co_await` in a generator coroutine is ill-formed. A generator is a synchronous pull model and cannot wait for asynchronous operations inside.

## Allocating the coroutine frame

The coroutine frame is allocated with `std::allocator` by default. Per [[coro.generator.promise#17]], there are two ways to use a different allocator:

- In the type: when the `Allocator` of `generator<T, V, Alloc>` is not `void`, it is used to allocate the coroutine frame. `std::pmr::generator<T, V>` is just an alias with `Allocator` fixed to `polymorphic_allocator<>`.
- In the parameters: when the coroutine's first two parameters are `allocator_arg_t, const Alloc&` (following the object parameter for member functions), the promise's `operator new` receives these two arguments and uses them to allocate the coroutine frame. This is the general convention for coroutine allocators.

## Common pitfalls

!!! pitfall "Dangling reference parameters"
    ```cpp
    std::generator<char> chars(const std::string& s) {
      for (char c : s) co_yield c;
    }
    auto g = chars("temporary");   // the temporary string is destroyed at the end of this line
    for (char c : g) { }           // UB: the object s refers to is gone
    ```
    A coroutine copies its parameters into the coroutine frame, but for a reference parameter only the reference itself is copied ([[dcl.fct.def.coroutine]]). Not a line of the body has run by the time `chars(...)` returns, and by the time it is traversed the temporary has been destroyed. Pass generator parameters by value where possible.

    Writing `for (char c : chars("temporary"))` directly is safe since C++23: temporaries created in the initializer of a range-based `for` live until the loop ends ([[P2718R0]], [[stmt.ranged]]). In C++20, writing it this way dangles too.

!!! pitfall "Using it as a forward range"
    `generator` is only an `input_range`: it cannot be traversed twice, `views::reverse` does not work on it, and `ranges::distance(g)` consumes it. When you need multiple passes, store it first with `std::ranges::to<std::vector>()`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[coro.generator.class] ¶1.1 and ¶2: when `Allocator` is not `void`, its `pointer` must be a pointer type, and it must meet the *Cpp17Allocator* requirements. ¶4: a program adding a specialization of `generator` is {{ub}}.

[coro.generator.members] ¶5–¶7: the move assignment operator takes the other generator by value and swaps coroutine handles and active stacks with `*this`. Note 3 likewise says that iterators obtained earlier become iterators into `*this`.

[coro.generator.promise] ¶1: the generator returned by `get_return_object()` holds this coroutine's handle and an empty active stack. ¶9, ¶12, Note 1: the type of a `co_yield` expression that calls these `yield_value` overloads is `void`.

[coro.generator.iterator] ¶1–¶3: the iterator is move-only and takes over the coroutine handle when moved.

</details>

## Summary

| Question | Answer |
|---|---|
| What does `generator<T>` hand out | `T&&`; `generator<const T&>` hands out read-only references |
| Does `co_yield` copy | usually it only stores an address; the default rvalue-reference generator copies when given an lvalue |
| How many times can it be traversed | once; `begin()` can be called only once |
| Recursion | `co_yield ranges::elements_of(child)`, resuming only one coroutine per step |
| Exceptions | propagate outward along the active stack, finally thrown from `begin()` or `++` |
| `co_await` | ill-formed |
