---
title: std::generator (P2502)
summary: C++20 had coroutines but no coroutine types, so everyone wrote their own generators. How C++23's std::generator decided that its first template argument is the reference type, that it yields T&& by default, and that co_yield of an lvalue copies; why recursive generation uses one type and one active stack; why the allocator is passed in as a parameter; and why it is only a single-pass, move-only view.
tags: generator, coroutines, ranges, views, allocators, proposal, C++23
group: Library
updated: 2026-10-19
---

!!! tldr
    - C++20 has only the language machinery for coroutines, no coroutine types. A usable generator needs a hand-written promise, iterator and ownership handling, and one mistake means dangling or double destruction; with recursion, elements are forwarded level by level, and the number of coroutines resumed per element grows with the depth.
    - [[P2502R2]] (built on [[P2168R3]]) provides `std::generator<Ref, V = void, Allocator = void>`. The first argument determines the reference type, and `generator<T>` yields `T&&`; this was chosen after comparing three defaults: by value, `const T&` and `T&&`.
    - `co_yield` only stores the address of its operand in the promise, without copying. The single exception is `co_yield` of an lvalue into a `T&&` generator, which makes a copy so that the consumer moving from it does not hollow out the variable in the coroutine.
    - Recursive generation uses a single type: `co_yield ranges::elements_of(g)` pushes the child generator onto an active stack and switches to it directly with symmetric transfer, so getting one element resumes only one coroutine. Exceptions are rethrown level by level along this stack.
    - The allocator for the coroutine frame is passed in through two leading arguments, `allocator_arg, alloc`, and is type-erased by default. A generator is a move-only, single-pass view, and `begin()` may be called only once.

## C++20: coroutines, but no generator

C++20 added **coroutines** ([[g:coroutine|coroutine]]): a function whose body contains `co_yield`, `co_await` or `co_return` can suspend partway through and later resume from where it suspended ([[dcl.fct.def.coroutine]]). But the standard only specifies a rewriting protocol; it provides no type you can write directly in the return type position. The mechanism itself is covered in [[topics/coroutines]]; here we only look at what it takes to write a generator.

A **generator** is the simplest coroutine type: each time the coroutine executes `co_yield`, the loop iterating over it gets one element. Below is a minimal implementation that can be connected to range adaptors:

```cpp title="gen.cpp" run ok
#include <coroutine>
#include <cstddef>
#include <cstdio>
#include <exception>
#include <iterator>
#include <memory>
#include <ranges>
#include <utility>

template<class T>
class gen : public std::ranges::view_interface<gen<T>> {
public:
  struct promise_type {
    const T* cur = nullptr;            // points to the operand of co_yield
    gen get_return_object() {
      return gen{handle::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    std::suspend_always yield_value(const T& v) noexcept {
      cur = std::addressof(v);
      return {};
    }
    void return_void() noexcept {}
    void unhandled_exception() { throw; }
  };
  using handle = std::coroutine_handle<promise_type>;

  struct iterator {
    using value_type = T;
    using difference_type = std::ptrdiff_t;
    handle h;
    const T& operator*() const { return *h.promise().cur; }
    iterator& operator++() { h.resume(); return *this; }
    void operator++(int) { ++*this; }
    bool operator==(std::default_sentinel_t) const { return h.done(); }
  };

  gen(gen&& o) noexcept : h_(std::exchange(o.h_, {})) {}
  gen& operator=(gen o) noexcept { std::swap(h_, o.h_); return *this; }
  ~gen() { if (h_) h_.destroy(); }

  iterator begin() { h_.resume(); return {h_}; }
  std::default_sentinel_t end() const noexcept { return {}; }

private:
  explicit gen(handle h) : h_(h) {}
  handle h_;
};

gen<int> fib() {
  int a = 0, b = 1;
  while (true) {
    co_yield a;
    a = std::exchange(b, a + b);
  }
}

static_assert(std::ranges::input_range<gen<int>>);
static_assert(std::ranges::view<gen<int>>);

int main() {
  for (int x : fib() | std::views::take(8))
    std::printf("%d ", x);             // 0 1 1 2 3 5 8 13
  std::printf("\n");
}
```

Every one of these fifty lines matters. `initial_suspend` returns `suspend_always`, which is what makes the generator lazy; `final_suspend` must suspend too, otherwise the frame is destroyed automatically when the coroutine finishes and `h.done()` reads freed memory. `yield_value` only stores the address, relying on the operand of `co_yield` living until the coroutine resumes. The base class `view_interface` makes `enable_view` true, which is what makes it a view ([[range.view]]).

Ownership is the easiest thing to get wrong. A coroutine frame may be destroyed only once, so the generator object must be move-only. Forget the move constructor and the compiler implicitly generates a copy constructor:

```cpp title="copy.cpp" ub
#include <coroutine>
struct gen {
  struct promise_type {
    gen get_return_object() {
      return gen{std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    std::suspend_always yield_value(int) noexcept { return {}; }
    void return_void() noexcept {}
    void unhandled_exception() { throw; }
  };
  std::coroutine_handle<promise_type> h;
  ~gen() { if (h) h.destroy(); }
};

gen g() { co_yield 1; }

int main() {
  gen a = g();
  gen b = a;     // implicitly generated copy constructor: two objects hold the same handle
}                // UB: b and a are destroyed in turn, destroying the same coroutine frame twice
```

Compiled with `-Wall -Wextra` there is no warning at all; AddressSanitizer reports heap-use-after-free at the second `destroy()`.

The hand-written version has two more design problems. One is the element type: the iterator above yields `const T&`, so the consumer cannot move elements out, and move-only types cannot be used at all; yield `T&` instead and the consumer can modify the coroutine's local variables. The other is recursion, covered in the next section. cppcoro, folly and range-v3 each have their own generator, differing in whether they support recursion and how they manage ownership (the Implementation and experience section of [[P2502R2]]).

## The cost of recursion

The most natural way to traverse a tree in order is recursion: subtrees are generators too, and the parent generator forwards the child generator's elements one by one. The problem is that every time the consumer asks for an element, `++` resumes the outermost coroutine, whose `for` loop resumes the next level, and so on down to the level that actually produces the element. At depth d, getting one element resumes d coroutines.

[[P2168R3]]'s approach is to let a generator hand the child generator over directly, with the consumer side remembering the current innermost coroutine:

<div class="compare" markdown="1">

```cpp
// forward level by level
gen<int> slow(int n) {
  if (n == 0) co_return;
  co_yield n;
  for (int x : slow(n - 1))
    co_yield x;
}
```

```cpp
// hand over to the child coroutine
rgen<int> fast(int n) {
  if (n == 0) co_return;
  co_yield n;
  co_yield nested<int>{fast(n - 1)};
}
```

</div>

The `rgen` on the right is a recursive generator written by hand following the standard's rules. The outermost generator owns a stack recording all currently nested coroutines, with the one currently producing elements on top:

- `co_yield nested{child}` pushes the child coroutine onto the stack and then switches to it directly;
- the iterator's `++` always resumes the coroutine on top of the stack, and `*` always reads that coroutine's value;
- when a child coroutine finishes, it pops itself off the stack in `final_suspend` and switches directly back to the parent coroutine.

Switching directly uses **symmetric transfer** ([[P0913R1]]): when `await_suspend` returns a coroutine handle, the implementation resumes it ([[expr.await#5.1.1]]). Implementations compile this resumption as a tail call, so however deep the nesting, the native call stack does not grow ([[topics/coroutines]] has more detail).

<details class="fine" markdown="1"><summary>Full program: a hand-written recursive generator with counting</summary>

```cpp title="rec.cpp" run ok
#include <coroutine>
#include <cstdio>
#include <exception>
#include <iterator>
#include <memory>
#include <utility>
#include <vector>

long resumes = 0;   // counts how many times coroutines are resumed

template<class T>
class rgen;

template<class T>
struct nested { rgen<T> g; };          // corresponds to ranges::elements_of

template<class T>
class rgen {
public:
  struct promise_type;
  using handle = std::coroutine_handle<promise_type>;
  using stack_t = std::vector<handle>;

  struct promise_type {
    const T* cur = nullptr;
    stack_t* stack = nullptr;          // points to the stack owned by the outermost rgen
    std::exception_ptr ex;

    rgen get_return_object() { return rgen{handle::from_promise(*this)}; }
    std::suspend_always initial_suspend() noexcept { return {}; }

    // on finishing, pop self off the stack and go straight to the parent
    auto final_suspend() noexcept {
      struct pop {
        bool await_ready() noexcept { return false; }
        std::coroutine_handle<> await_suspend(handle h) noexcept {
          stack_t& s = *h.promise().stack;
          s.pop_back();
          if (s.empty()) return std::noop_coroutine();
          ++resumes;
          return s.back();             // symmetric transfer
        }
        void await_resume() noexcept {}
      };
      return pop{};
    }

    std::suspend_always yield_value(const T& v) noexcept {
      cur = std::addressof(v);
      return {};
    }

    // co_yield nested{child}: push the child and go straight to it
    auto yield_value(nested<T> n) noexcept {
      struct push {
        rgen<T> child;
        bool await_ready() noexcept { return false; }
        std::coroutine_handle<> await_suspend(handle h) noexcept {
          stack_t& s = *h.promise().stack;
          child.h_.promise().stack = &s;
          s.push_back(child.h_);
          ++resumes;
          return child.h_;             // symmetric transfer
        }
        void await_resume() {
          if (auto e = child.h_.promise().ex) std::rethrow_exception(e);
        }
      };
      return push{std::move(n.g)};
    }

    void return_void() noexcept {}
    void unhandled_exception() {
      if (stack->size() == 1) throw;   // outermost: throw to the consumer
      ex = std::current_exception();   // nested: let the parent's co_yield rethrow it
    }
  };

  struct iterator {
    using value_type = T;
    using difference_type = std::ptrdiff_t;
    handle root;
    stack_t* stack;
    const T& operator*() const { return *stack->back().promise().cur; }
    iterator& operator++() { ++resumes; stack->back().resume(); return *this; }
    void operator++(int) { ++*this; }
    bool operator==(std::default_sentinel_t) const { return root.done(); }
  };

  rgen(rgen&& o) noexcept
    : h_(std::exchange(o.h_, {})), stack_(std::move(o.stack_)) {}
  ~rgen() { if (h_) h_.destroy(); }

  iterator begin() {
    stack_ = std::make_unique<stack_t>();
    h_.promise().stack = stack_.get();
    stack_->push_back(h_);
    ++resumes;
    h_.resume();
    return {h_, stack_.get()};
  }
  std::default_sentinel_t end() const noexcept { return {}; }

private:
  explicit rgen(handle h) : h_(h) {}
  handle h_;
  std::unique_ptr<stack_t> stack_;
};

// a generator that can only forward level by level, for comparison
template<class T>
class gen {
public:
  struct promise_type {
    const T* cur = nullptr;
    gen get_return_object() { return gen{handle::from_promise(*this)}; }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    std::suspend_always yield_value(const T& v) noexcept { cur = &v; return {}; }
    void return_void() noexcept {}
    void unhandled_exception() { throw; }
  };
  using handle = std::coroutine_handle<promise_type>;
  struct iterator {
    using value_type = T;
    using difference_type = std::ptrdiff_t;
    handle h;
    const T& operator*() const { return *h.promise().cur; }
    iterator& operator++() { ++resumes; h.resume(); return *this; }
    void operator++(int) { ++*this; }
    bool operator==(std::default_sentinel_t) const { return h.done(); }
  };
  gen(gen&& o) noexcept : h_(std::exchange(o.h_, {})) {}
  ~gen() { if (h_) h_.destroy(); }
  iterator begin() { ++resumes; h_.resume(); return {h_}; }
  std::default_sentinel_t end() const noexcept { return {}; }
private:
  explicit gen(handle h) : h_(h) {}
  handle h_;
};

gen<int> slow(int n) {
  if (n == 0) co_return;
  co_yield n;
  for (int x : slow(n - 1)) co_yield x;   // forward level by level
}
rgen<int> fast(int n) {
  if (n == 0) co_return;
  co_yield n;
  co_yield nested<int>{fast(n - 1)};      // hand over to the child coroutine
}
struct oops {};
rgen<int> thrower() { co_yield 0; throw oops{}; }
rgen<int> catcher() {
  bool caught = false;
  try { co_yield nested<int>{thrower()}; } catch (oops) { caught = true; }
  if (caught) co_yield -1;            // co_yield is not allowed inside a handler
  co_yield 1;
}

int main() {
  for (int n : {10, 100, 1000}) {
    resumes = 0;
    for (int x : slow(n)) (void)x;
    long r1 = std::exchange(resumes, 0);
    for (int x : fast(n)) (void)x;
    std::printf("n=%4d: %6ld vs %4ld\n", n, r1, resumes);
  }
  // n=  10:     66 vs   31
  // n= 100:   5151 vs  301
  // n=1000: 501501 vs 3001
  for (int x : catcher()) std::printf("%d ", x);   // 0 -1 1
}
```

</details>

`slow(n)` and `fast(n)` both produce n elements, and both nest to depth n. Counting in our test, forwarding level by level resumes coroutines (n+1)(n+2)/2 times in total, 501501 times for n = 1000; with the stack and symmetric transfer it is 3n+1 times, 3001 for n = 1000. Timed at `-O2` with n = 1000, the former takes about 4.7 ms and the latter about 0.05 ms; `fast(1000000)` runs to completion even at `-O0`, with no stack overflow.

## The design space

### One type or two

cppcoro puts this capability in a separate `recursive_generator`; its ordinary `generator` does not support recursion. [[P2168R3]] lists three approaches, and [[P2502R2]] keeps them unchanged:

| Approach | Problem |
|---|---|
| One `generator` that supports recursion | Two extra pointers of overhead per generator |
| A separate `recursive_generator` that can nest both kinds | Very small performance gain, same memory |
| A separate `recursive_generator` that can only nest its own kind | When writing a generator you have to guess whether it will ever be nested |

The third has the most practical problem. If a function returning `generator` later needs to be used in a `recursive_generator`, you can only forward element by element or wrap it in an adapter function, and either way each element costs one more coroutine resumption. The paper reports measurements: without nesting there is no visible difference between the two implementations, and supporting recursion does not prevent HALO (the compiler optimizing away the heap allocation of the coroutine frame); with deep nesting, the version supporting symmetric transfer is much faster. The proposal chose the first approach.

A single type also allows a relaxation. The only interface in the promise type that depends on the generator's template arguments is `yield_value`, so as long as the types accepted by `co_yield` are the same, generators with different value types or allocators can be nested in each other. The constraint in the current draft is exactly `same_as<typename generator<R2, V2, Alloc2>::yielded, yielded>` ([[coro.generator.promise#10]]).

### `elements_of`: yielding the range or its elements

If `co_yield g` itself meant yielding all the elements of g, some cases would be ambiguous:

```cpp
std::generator<int> f() { co_yield 42; }
std::generator<std::any> g() {
  co_yield f();   // yield 42, or yield a generator<int> object?
}
```

`std::any` can hold any copyable object, so a `generator<int>` could legitimately be yielded as an element. From R1 on, [[P2168R3]] introduced the tag `ranges::elements_of`: `co_yield e` always yields e itself, and only `co_yield ranges::elements_of(e)` yields e's elements. Once there was a tag, it was generalized to any `input_range` along the way: for `co_yield ranges::elements_of(v)` on a `vector`, the standard specifies that the range is first wrapped in an internal generator and then goes through the nested-generator path ([[coro.generator.promise#13]]).

[[P2502R2]] simplified `elements_of` into an aggregate with just two members, `range` and `allocator` ([[range.elementsof]]).

### The first template argument: the reference type

A range has two associated types: the **value type** (`range_value_t`, the type used when storing a copy) and the **reference type** (`range_reference_t`, the type you get by dereferencing an iterator); see [[topics/ranges-design]]. How the generator's template arguments determine these two types is the part of the proposal that changed most often, going through three answers in all.

In [[P2168R3]] the first argument is the reference type, and the value type defaults to it with cv-qualifiers and references removed. This is the simplest, but then every dereference of a `generator<std::string>` iterator returns a new `string` prvalue. The earlier discussion preserved in [[P2502R2]] calls it a serious performance trap: the user just wrote the most natural `generator<string>`, and each `co_yield` costs two extra copies.

So early revisions of [[P2502R2]] changed it: when the first argument is not a reference, the reference type is `const T&`. That avoids copying, but the consumer can only read. [[P2529R0]] argued for `T&&` instead, for three reasons:

- Performance and move-only types. With `const T&`, `ranges::copy`, `ranges::to<vector>()` and `for (auto s : g)` all have to copy, and when the elements are move-only types like `unique_ptr` it simply doesn't compile; adding `views::move` doesn't help either.
- Consistency with functions returning `T`. A `generator<T>` can be seen as a function that repeatedly returns `T`; the caller gets its own object, which it can move from or modify.
- A simple rule: dereferencing always gives `FirstArg&&`, and reference collapsing automatically handles spellings like `generator<T&>`.

The objection was that `T&&` makes it easy for elements to be moved from by accident. [[P2502R2]]'s example is a predicate that takes its argument by value: `views::filter` calls it with the result of dereferencing, and the element is moved into the parameter. The libc++ used here has no `<generator>`, but `views::as_rvalue` produces the same `std::string&&` reference type and reproduces the effect:

```cpp title="footgun.cpp" run unspecified
#include <cstdio>
#include <ranges>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> v{"footgun"};
  // dereferencing gives std::string&&, just like generator<std::string>
  auto r = v | std::views::as_rvalue
             | std::views::filter([](std::string s) {   // takes it by value
                 return !s.empty();
               });
  for (auto&& x : r)
    std::printf("[%s]\n", x.c_str());   // prints [] in our test
}
```

The predicate's parameter is move-constructed from `std::string&&`, and the original element is left in a moved-from state. Standard library types are left in a valid but unspecified state after being moved from ([[lib.types.movedfrom#1]]), so the output is unspecified; the libc++ used here leaves it as an empty string, so `[]` is printed.

[[P2529R0]]'s response was that ranges whose reference type is an rvalue reference are already valid input ranges, adaptors like `views::move` produce them too, and generic code has to handle them correctly sooner or later; and the most common usage is range-based for, where the named `x` in the loop is an lvalue and is not moved from implicitly. The committee finally adopted `T&&`, and kept the ability to specify the value type and reference type separately; the result is these three lines in the current draft ([[coro.generator.class]]):

```cpp
using value     = conditional_t<is_void_v<Val>, remove_cvref_t<Ref>, Val>;
using reference = conditional_t<is_void_v<Val>, Ref&&, Ref>;
using yielded   = conditional_t<is_reference_v<reference>, reference, const reference&>;
```

With just one argument, the reference type is `Ref&&`. When `Ref` is itself a reference, reference collapsing applies: `generator<const T&>` yields `const T&`, and `generator<T&>` yields `T&`. A table of the types each spelling gives is in [[coro.generator]].

The proposal also lists several rejected defaults:

| Candidate | Reason for rejection |
|---|---|
| No default; force writing `generator<const int&>` | There is a reasonable default, so no need to make users suffer |
| `T&` | Allows modifying objects in the coroutine frame, too dangerous as a default; the expressions that can be `co_yield`ed are also very limited |
| `T&` for move-only types, `const T&` otherwise | Adding a copy constructor to `T` would change the meaning of code |
| Special handling of `reference_wrapper<T>` and the like | No other view does this, and there is no clear definition of a reference-like type |

### `co_yield` of an lvalue copies

Once the reference type became `T&&`, `yield_value(T&&)` does not accept lvalues, so `co_yield local;` could not be written. [[P2502R2]] added a second overload in R1: when `co_yield` is given a copyable lvalue, a copy is made and stored in the awaitable that `co_yield` returns, and the consumer gets an xvalue referring to that copy ([[coro.generator.promise#7]]). As the paper puts it, this saves users from writing `co_yield auto(lvalue)`.

The copy guarantees that the consumer moving from an element does not hollow out the coroutine's variable, which the coroutine can keep using after it resumes. [[coro.generator]] has a complete example. The paper says this is to be closer to a function returning a prvalue: the caller always gets an object of its own.

### Storing an address, not a value

The paper also compared how the promise should store the current element. The earliest revisions always stored a copy, costing one extra copy per element. The final approach relies on a language rule: if the operand of `co_yield` is a temporary, it is not destroyed until the end of the full-expression containing the `co_yield`, and the coroutine suspends right in the middle of that expression. So the promise stores only a pointer ([[coro.generator.promise#4]]), the parameter of `yield_value` is always the reference type `yielded`, and any needed conversions happen inside the coroutine.

The cost is that temporaries live rather long. The paper's example is `(co_yield x, co_yield y);`: if `x` needs to be converted into a temporary, that temporary is not destroyed until `y` has also been yielded.

### The second argument: specifying the value type separately

`V` is reserved for the few cases that need proxy references. The paper's example is writing `zip` with a generator, where the reference type is a `tuple` of two references and the value type is a `tuple` of two values. Another example shows that the value type affects the type the consumer uses when storing copies:

```cpp
std::generator<std::string_view, std::string> strings() {
  std::string s;
  for (auto sv : {"a", "b"}) {
    s = sv;
    s += '!';
    co_yield s;                      // yields a string_view referring to s
  }
}
auto v = std::ranges::to<std::vector>(strings());   // vector<std::string>
```

Elements are yielded as `string_view`, without copying. But `ranges::to` builds the container from the value type, giving `vector<string>`. If the value type were also `string_view`, `v` would store views referring to the coroutine variable `s`, and the next assignment to `s` would invalidate them.

The order of the three arguments was also changed twice. In R1, [[P2502R2]] finally put `Allocator` back last, because that is how every other template in the standard library orders them, and an exception would cost too much.

### The allocator comes in through parameters

The coroutine frame is allocated by the promise type's `operator new`, and when the compiler calls it, it appends the coroutine's arguments as-is after the size ([[dcl.fct.def.coroutine#9.1]]). The generator's promise can therefore recognize an allocator among the arguments. Following the model in section 2 of [[P1681R0]], the proposal specifies: when the first two parameters of the coroutine are `allocator_arg_t` and an allocator, that allocator is used to allocate the coroutine frame ([[coro.generator.promise#17]]).

```cpp
template<class Alloc>
std::generator<int> ints(std::allocator_arg_t, const Alloc&, int n) {
  for (int i = 0; i < n; ++i) co_yield i;
}

std::pmr::monotonic_buffer_resource mr;
auto g = ints(std::allocator_arg,
              std::pmr::polymorphic_allocator<>(&mr), 10);
```

Why must they come first? A coroutine's parameters may include several allocators, some of which are for use in the function body. Only a conventional position can tell which one is for allocating the coroutine frame. The paper acknowledges that this restricts parameter order, but could not think of a case where the first parameter must be used for something else.

When `Allocator` is `void` (the default), the allocator type is erased: the type of `g` is still `generator<int>`, and the allocator is stored in the coroutine frame together with the information needed for deallocation. Code that only wants one stateless allocator can write `generator<T, void, Alloc>`, which needs no argument and takes no extra space.

Using `void` to mean erasing any allocator drew criticism. The paper discussed replacing it with a dedicated tag type and concluded that a single-purpose tag brings too little benefit; `monostate` already has a clear purpose and should not be borrowed. `void` cannot be mistaken for an allocator, so it stayed.

Why not add allocator support later? Because the allocator is a template argument, and adding a template argument after the generator ships would break ABI. [[P2502R2]] therefore insisted on getting it in from the start.

### A single-pass, move-only view

A coroutine frame is an exclusively owned resource: the handle can be copied, the frame cannot. So the generator is move-only, its iterator is move-only too, and the range can only be an `input_range`: after one traversal, the coroutine has run to the end. [[coro.generator.members#8]] makes it a precondition of `begin()` that the coroutine is suspended at its initial suspend point, so calling `begin()` a second time is {{ub}} (Note 4).

It is still a **view** ([[g:range-view|view]]) and can be connected directly to adaptors. In the days of [[P2168R3]] this was in doubt: views were required to have O(1) destruction at the time, while a generator taking a `vector` by value destroys the whole `vector` when its coroutine frame is destroyed. [[P2415R2]] relaxed the semantic requirements on views; now destroying N copies plus M elements only needs to be O(N+M) ([[range.view#2.3]]), which generators satisfy without question.

### Exceptions propagate along the stack

An exception thrown in a child generator and not caught there is not thrown directly from the outermost `++`; instead it is rethrown at the parent generator's `co_yield ranges::elements_of(...)`. The paper's reasoning is that `co_yield elements_of(g)` should have the same semantics as the hand-written `for (auto&& x : g) co_yield x;`, where the exception emerges from the parent coroutine's loop and the parent can catch it with `try`. In `rec.cpp` above, `catcher` catches `thrower`'s exception and prints `0 -1 1`.

The standard specifies `unhandled_exception()` in two cases ([[coro.generator.promise#16]]): when the stack contains only itself it is equivalent to `throw;`; otherwise the exception is stored in the promise and rethrown by the parent coroutine's `await_resume` ([[coro.generator.promise#11]]).

The promise also has a deleted `await_transform()`, which makes `co_await` in a generator coroutine ill-formed. Generators are synchronous: when the consumer's `++` returns, there must already be a next element or the end must have been reached; the coroutine cannot stop to wait for something else.

## Wording

!!! std
    Specializations of `generator` model `view` and `input_range`. ([[coro.generator.class#3]])

    Every specialization of `generator` models `view` and `input_range`.

The wording of [[P2502R2]] is based on N4910 and consists entirely of new library text. Organized by location in the current draft, with explanations of each in [[coro.generator]]:

| Subclause | Contents |
|---|---|
| [[coroutine.generator.overview]] | A generator presents a view of the elements produced by a coroutine; `co_yield elements_of(r)` produces the elements of r in turn |
| [[generator.syn]] | The new header `<generator>`; the `pmr::generator` alias (added later by [[P2787R1]]) |
| [[coro.generator.class]] | The three template arguments determine *value*, *reference* and `yielded`; *Mandates* ensure the iterator satisfies `input_iterator` |
| [[coro.generator.members]] | Move-only; existing iterators remain valid after a move; `begin()` may be called only once |
| [[coro.generator.promise]] | The `yield_value` overloads, the active stack, exceptions, `operator new` |
| [[coro.generator.iterator]] | `*` reads the value of the coroutine on top of the stack, `++` resumes it |
| [[range.elementsof]] | The tag `ranges::elements_of` |

The feature-test macro `__cpp_lib_generator` currently has the value `202207L` ([[version.syn]]).

## Consequences

### Compatibility

A pure library extension. The only related Annex C entry is about the new header: a project that has its own header named `generator` and includes it with `#include <generator>` may get the standard library's version instead ([[diff.cpp20.library#1]]).

### Later library issues

- [[LWG3894]]: `yield_value(elements_of<R, Alloc>)`, which accepts any range, was originally declared `noexcept`. It has to call `ranges::begin`, allocate a new coroutine frame and copy iterators, all of which may throw, so the `noexcept` was removed.
- [[LWG3899]]: `co_yield elements_of(g)` takes the fast nested-generator path for an rvalue `g`, but an lvalue `g` fell through to the generic range overload, creating an extra coroutine frame and losing symmetric transfer. The fix added an overload accepting `elements_of<generator&>`, which is why the current draft has two declarations side by side.
- [[P2787R1]] added `std::pmr::generator<R, V>`, an alias with `Allocator` fixed to `polymorphic_allocator<>`, so that a requirement to allocate with pmr is written into the type.

### Implementation status

The libc++ that ships with Homebrew Clang 23 does not have `<generator>` yet; `#include <generator>` reports that the file does not exist. So none of the examples on this page that use `std::generator` carry a verdict, and the mechanism could only be verified locally with the hand-written `gen` and `rgen` above. libstdc++ (since GCC 14) and MSVC's standard library already provide it; use the godbolt button to run on GCC.

Reference and `string_view` parameters of a generator coroutine may already be dangling when the coroutine resumes; for these traps see [[coro.generator]] and [[topics/coroutines]].

## Questions

!!! question "1"
    Can `std::generator<std::unique_ptr<int>>` be used? If the default reference type were `const T&` as in early revisions of [[P2502R2]], would the loop below compile?

    ```cpp
    std::generator<std::unique_ptr<int>> make();
    std::vector<std::unique_ptr<int>> v;
    for (auto&& p : make()) v.push_back(std::move(p));
    ```

<details markdown="1">
<summary>Answer</summary>

Under the current rules it can be used: the reference type is `unique_ptr<int>&&`, `std::move(p)` gives an rvalue, and `push_back` move-constructs. In the coroutine body, `co_yield std::make_unique<int>(1);` yields a prvalue, which binds to `yielded`, i.e. `unique_ptr<int>&&`, with no copy.

If the reference type were `const unique_ptr<int>&`, `std::move(p)` would give `const unique_ptr<int>&&`, which can only match the deleted copy constructor, and compilation fails. That is one of the reasons [[P2529R0]] lists. One other change: `co_yield` of a `unique_ptr` lvalue in the coroutine body is now ill-formed, because the copying `yield_value` overload requires copy-constructibility ([[coro.generator.promise]]); you have to write `co_yield std::move(p);`.

</details>

!!! question "2"
    In `rec.cpp`, `fast(n)` resumes coroutines 3n+1 times. Where does each of these resumptions happen? With `std::generator` and `co_yield std::ranges::elements_of(fast(n - 1))` instead, would the order of magnitude change?

<details markdown="1">
<summary>Answer</summary>

Each non-empty `fast(k)` contributes three: one symmetric transfer in when the parent pushes it, one resumption by the consumer's `++` after its `co_yield k`, and one symmetric transfer back to the parent when it finishes (when the outermost one finishes it transfers to `noop_coroutine`, which is not counted). The entry into the outermost one is the one in `begin()`, and its exit is not counted; `fast(0)` is also a coroutine, with one entry and one exit. In total 3n − 1 + 2 = 3n+1.

With `std::generator` the order of magnitude stays the same. The standard's `elements_of` overload pushes the child generator onto *active_* and resumes it ([[coro.generator.promise#11]]), `final_suspend` pops the stack and resumes the new top ([[coro.generator.promise#3]]), and the iterator's `++` only resumes the top of the stack ([[coro.generator.iterator#7]]). The standard does not require symmetric transfer, but the number of coroutines resumed per element is independent of depth.

</details>

## Summary

| Design question | Final choice | Rejected options |
|---|---|---|
| Default reference type | `generator<T>` yields `T&&` | By value (copy on every dereference), `const T&`, `T&`, forcing a reference to be written |
| `co_yield` of an lvalue | Copies for a `T&&` generator | Requiring users to write `co_yield auto(x)` |
| Storing the current element | Store only the address | Always store a copy |
| Recursion | Same type, `elements_of` tag, active stack | A separate `recursive_generator` |
| Exceptions from nested generators | Rethrown at the parent's `co_yield` | Thrown directly from the outermost `++` |
| Allocator | Leading `allocator_arg, alloc`; erased when `Allocator = void` | Adding it later (would break ABI); a dedicated tag instead of `void` |
| Range category | Move-only `input_range` view | Copyable, multi-pass |
