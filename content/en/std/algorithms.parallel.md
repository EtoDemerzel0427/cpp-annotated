---
title: Parallel algorithms
summary: "What an algorithm may do with your code once you pass an execution policy: the notion of element access functions, which threads and in what order calls happen under seq, unseq, par and par_unseq, what counts as a data race or undefined behavior, why an exception from an element access function calls terminate, and how the complexity of parallel overloads is relaxed."
updated: 2026-10-19
---

!!! tldr
    - The rules for parallel algorithms are stated in terms of element access functions: iterator operations, operations on elements, the lambda you pass in, and copies of that lambda all count.
    - `par` allows them to be invoked on multiple threads, with calls on the same thread not interleaved; `unseq` and `par_unseq` also allow calls on the same thread to interleave, and locking inside them is then undefined behavior.
    - An execution policy is only a permission. The implementation may fall back to sequential execution, so you must not write code that depends on another call running at the same time.
    - When an element access function throws, all four standard policies call `std::terminate`; the exception does not reach the caller, even with `seq`.
    - Complexity of the form "exactly N" or "at most N" in non-parallel versions is generally relaxed to O(N) in parallel versions.

C++17 merged the Parallelism TS into the standard ([[P0024R2]]). Most algorithms gained an overload taking an **execution policy** ([[g:execution-policy]]) as the first argument:

```cpp
std::sort(std::execution::par, v.begin(), v.end());
```

This page is about what the algorithm may do with your iterators, elements and function objects once a policy is passed, and what your code must therefore tolerate. The policy types and objects themselves are in [[execpol]].

¶1 [algorithms.parallel] describes components for performing operations on containers and other sequences in parallel. ¶2 A function template with a template parameter named `ExecutionPolicy`, or one constrained by the exposition-only concept *execution-policy*, is a **parallel algorithm** ([[g:parallel-algorithm]]). Such a template parameter is an **execution policy template parameter** ([[g:execution-policy-template-parameter]]):

```cpp
template<class Ep>
  concept execution-policy = is_execution_policy_v<remove_cvref_t<Ep>>;   // exposition only
```

The classic parallel overloads use `class ExecutionPolicy`; the parallel `ranges` overloads added in C++26 ([[P3179R9]]) use `execution-policy Ep`.

## Element access functions [algorithms.parallel.defns]

¶3 Parallel algorithms access objects indirectly accessible via their arguments by invoking the following kinds of functions:

- ¶3.1 all operations of the categories of the iterator, sentinel or `mdspan` types that the algorithm is instantiated with;
- ¶3.2 operations on sequence elements that are required by its specification;
- ¶3.3 user-provided invocable objects to be applied during the execution, if required by the specification;
- ¶3.4 operations on those invocable objects required by the specification, for example copying them.

These are collectively called **element access functions** ([[g:element-access-function]]). Example 1 in ¶4 uses `sort`: the operations of the random access iterator, the `swap` applied to elements, and the user-provided `Compare` are all element access functions.

The later rules about which thread runs what, whether calls are ordered, and what happens on an exception are all stated per element access function. It is not just your lambda: an iterator's `operator++` and an element's move assignment are included. An iterator that logs or takes a lock in its `operator*` is bound by these rules too.

## How the four policies execute [algorithms.parallel.exec]

¶1 The execution policy template parameter describes the manner in which the execution of a parallel algorithm may be parallelized and how element access functions are invoked. The rules for the four standard policies:

| Policy | Threads the calls run on | Between calls on the same thread | Paragraph |
|---|---|---|---|
| `seq` (`sequenced_policy`) | all on the calling thread | not interleaved | ¶4 |
| `unseq` (`unsequenced_policy`) | all on the calling thread | unsequenced, may interleave | ¶5 |
| `par` (`parallel_policy`) | the calling thread, or threads the library creates for this | indeterminately sequenced, not interleaved | ¶6 |
| `par_unseq` (`parallel_unsequenced_policy`) | unspecified threads | unsequenced, may interleave | ¶7 |

Two evaluations are **indeterminately sequenced** ([[g:indeterminately-sequenced]]) when one completes before the other, but it is unspecified which. Two evaluations are **unsequenced** ([[g:unsequenced]]) when their executions may overlap. In ordinary code, function calls are at least indeterminately sequenced with respect to each other; the execution of one function does not interleave with another ([[intro.execution]]).

Notes 4 and 7 in ¶5 and ¶7 point out specifically that `unseq` and `par_unseq` overturn this usual guarantee. That is exactly what vectorization needs: the compiler fuses the instructions of four loop iterations into one set of SIMD instructions, and the four calls' executions are interwoven on the same thread.

### `par`: data races and deadlocks are the caller's responsibility

Note 6 in ¶6 says that under `par`, it is the caller's responsibility to ensure the invocations do not introduce data races or deadlocks. Three standard examples illustrate this:

```cpp
int a[] = {0, 1};
std::vector<int> v;
std::for_each(std::execution::par, std::begin(a), std::end(a), [&](int i) {
  v.push_back(i * 2 + 1);   // UB: two threads may modify v at once, a data race
});
```

In Example 2, the two invocations wait for each other through an `atomic`, spinning until the other changes its value. Under `par` this is not guaranteed to terminate: the implementation may well run both invocations one after the other on the same thread, and the first would spin forever. `par` only allows parallelism; it does not guarantee it.

Example 3 protects a shared counter with a `std::mutex`, which is correct under `par`, if possibly slow.

### `unseq` and `par_unseq`: no locking

```cpp
std::mutex m;
int x = 0;
int a[] = {1, 2};
std::for_each(std::execution::par_unseq, std::begin(a), std::end(a), [&](int) {
  std::lock_guard<std::mutex> guard(m);   // UB: lock_guard's constructor calls m.lock()
  ++x;
});
```

The two invocations may interleave on the same thread: the first acquires the lock, the second calls `m.lock()` again on the same thread, and it deadlocks.

[[algorithms.parallel.defns#5]] defines **vectorization-unsafe** ([[g:vectorization-unsafe]]) standard library functions: those specified to synchronize with another function invocation, or another invocation specified to synchronize with them, except memory allocation and deallocation functions and lock-free atomic read-modify-write operations. `mutex::lock`, `mutex::unlock` and condition variable waits are all in this category.

Per [algorithms.parallel.exec] ¶5 and ¶7, calling a vectorization-unsafe function in user code invoked by an `unseq` or `par_unseq` algorithm is {{ub}}. Note 2 there also requires implementations to ensure that synchronization inside standard library functions does not prevent threads with only weakly parallel forward progress guarantees from making progress, so `new` and `delete` are fine there.

### Forward progress

¶6 specifies that if the threads created by `std::thread` and `std::jthread` provide concurrent forward progress guarantees, then the threads implicitly created by the library for `par` provide **parallel forward progress guarantees** ([[g:parallel-forward-progress]]); otherwise it is implementation-defined. ¶7 Under `par_unseq`, threads created by the library provide only **weakly parallel forward progress guarantees** ([[g:weakly-parallel-forward-progress]]). For the meaning of these levels, see [[intro.progress]].

### A policy is a permission, not an order (¶8–¶9)

Note 9 in ¶8 says that the semantics of `unseq`, `par` and `par_unseq` allow the implementation to fall back to sequential execution if the system cannot parallelize, for example due to lack of resources. So passing `par` does not guarantee multiple threads; it only means your code must be able to tolerate them.

¶9 If a parallel algorithm uses threads created by the library, the calling thread either blocks with **forward progress guarantee delegation** ([[g:forward-progress-delegation]]) until they complete, or executes element access functions itself until the algorithm finishes. Intuitively, a parallel algorithm is a synchronous call: when it returns, all work is done and no invocation is still running in the background.

## Requirements on your function objects

### No modification through arguments [algorithms.parallel.user]

¶1 Unless otherwise specified, objects of type `Predicate`, `BinaryPredicate`, `Compare`, `UnaryOperation`, `BinaryOperation`, `BinaryOperation1`, `BinaryOperation2` or `BinaryDivideOp` passed to parallel algorithms, and objects constrained by a concept whose semantic requirements include `regular_invocable`, must not directly or indirectly modify objects via their arguments, nor rely on the identity of the provided objects. When the default predicate or operation is used, the corresponding operators must meet the same requirements.

This is stricter than the non-parallel versions. The non-parallel `std::transform` only forbids `op` from modifying elements of the ranges; the parallel version's `op` must not modify any object through its arguments.

Examples of "otherwise specified": in the parallel `for_each` and `for_each_n`, `f` may modify objects through its argument ([[alg.foreach#19]]); so may `generate`'s `gen` ([[alg.generate#6]]).

### Implementations may copy elements

[[algorithms.parallel.exec#3]] gives implementations a freedom:

!!! std
    Unless otherwise stated, implementations may make arbitrary copies of elements (with type `T`) from sequences where `is_trivially_copy_constructible_v<T>` and `is_trivially_destructible_v<T>` are true.

For example, a vectorizing implementation loads a batch of `int`s into SIMD registers, and a chunking implementation copies elements into a thread's own buffer. Note 2 points out that this means, for such sequences, function objects cannot rely on the object identity of their arguments; a test like `&x == &v[i]` is no longer reliable. `for_each` and `for_each_n` are exceptions: their *Remarks* deny implementations this freedom, because `for_each` is often used precisely to modify elements in place.

[[algorithms.parallel.exec#2]] is the promise in the other direction: while an object is being modified by an element access function, the algorithm performs no other unsynchronized accesses to it. Note 1 lists the modifying operations: `swap`, `++`, `--`, `@=`, and assignment (for assignment and compound assignment, only the left operand). So `std::sort(par, ...)` never has two threads swap the same element at once.

## Exceptions [algorithms.parallel.exceptions]

```cpp run title="parex.cpp" flags="-std=c++2c -fexperimental-library" ok
#include <algorithm>
#include <cstdio>
#include <execution>
#include <stdexcept>
#include <vector>

int main() {
  std::vector<int> v(1000, 1);
  try {
    std::for_each(std::execution::seq, v.begin(), v.end(), [](int x) {
      if (x == 1) throw std::runtime_error("boom");
    });
  } catch (...) {
    std::puts("caught");   // never reached
  }
}
```

With Clang 23 + libc++ in our tests, it prints `libc++abi: terminating due to uncaught exception of type std::runtime_error: boom` and the process ends with SIGABRT; the `catch (...)` never gets a chance to run. The program is well-formed; its behavior is simply to terminate.

¶2 When an element access function exits via an uncaught exception, the behavior is determined by the execution policy. The four standard policies each specify in their ¶2 that `std::terminate` is called ([[execpol]], [[except.terminate]]). So `std::for_each(std::execution::seq, ...)` is not equivalent to `std::for_each` without a policy: in the latter, an exception thrown by `f` propagates to the caller normally.

¶1 If temporary memory needed for parallelization cannot be allocated, the algorithm throws `std::bad_alloc`. This is the only exception a parallel algorithm throws outward. It refers to the algorithm's own allocation failing, and has nothing to do with a `bad_alloc` thrown by an element access function, which likewise leads to `terminate`.

!!! note "Why not collect the exceptions"
    The Parallelism TS once designed `exception_list` to collect multiple exceptions thrown on multiple threads. When it was merged into C++17, this mechanism was dropped in favor of always calling `terminate`. ¶2 leaves the behavior to the execution policy, which leaves room for future policy types to provide other behavior.

## General rules for parallel overloads [algorithms.parallel.overloads]

¶1 Each parallel overload has, compared with its non-parallel counterpart, an extra first function parameter of type `T&&`, where `T` is the execution policy template parameter. Note 1 reminds us that not every algorithm has a parallel overload. `accumulate`, `partial_sum`, `iota`, `push_heap`, `lower_bound` and `next_permutation` have none. `accumulate` and `partial_sum` specify a strict left-to-right order of computation, which rules out parallelism by itself; their parallel replacements are `reduce` and `inclusive_scan` ([[numeric.ops]]).

¶2 Unless otherwise specified, the semantics of calling a parallel overload are the same as calling the corresponding non-parallel overload with the first argument removed. There are quite a few "otherwise specified" cases:

- the parallel `for_each` does not return the function object: the classic version returns `void`, and the `ranges` version returns only the iterator;
- the parallel `adjacent_difference` does not allow the output range to overlap the input range, while the non-parallel version allows `result == first` ([[numeric.ops]]);
- the parallel `shift_left` does not specify the order in which elements are moved.

¶3 Relaxed complexity: when the non-parallel version's guarantee is written as "at most *expr*" or "exactly *expr*", does not specify the number of assignments or swaps, and *expr* is not already in O() form, the complexity of the parallel version is O(*expr*). So `std::find(par, ...)` may do a constant factor more comparisons than the non-parallel version, for instance each thread searching its own block; `std::count(par, ...)` no longer promises exactly N applications.

Some algorithms specify the complexity of their parallel versions separately: `nth_element` is O(N) predicate applications and O(N log N) swaps, `partition` is O(N log N) swaps. `transform`, on the other hand, states that its exactly-N requirement applies to the parallel overloads as well ([[alg.transform#5]]).

¶4 Parallel algorithms with a template parameter named `ExecutionPolicy` take part in overload resolution only if that parameter satisfies *execution-policy*. Without this rule, the three-argument call `std::sort(first, last, comp)` would also try to match the template `std::sort(policy, first, last)`.

The iterator parameters of the classic parallel overloads are at least `ForwardIterator`, not `InputIterator`, because splitting up the work needs multiple passes. C++26's parallel `ranges` overloads require `random_access_iterator` plus `sized_sentinel_for`, or *sized-random-access-range* ([[range.req]]), i.e. the ability to split into pieces in constant time.

## Implementation status

!!! impl "libc++ (LLVM 23)"
    - Parallel algorithms are an experimental feature and need `-fexperimental-library`; without that option, `std::execution::par` does not exist at all. `__cpp_lib_parallel_algorithm` in `<version>` is not defined.
    - The backend is chosen when libc++ is built. The `__config_site` of the Homebrew build we test with defines `_LIBCPP_PSTL_BACKEND_LIBDISPATCH`, i.e. it dispatches with GCD on macOS.
    - Only some algorithms have parallel overloads, such as `all_of`, `copy`, `count`, `equal`, `fill`, `find`, `for_each`, `generate`, `merge`, `replace`, `sort`, `stable_sort`, `transform`, `reduce` and `transform_reduce`. In our tests, calling `inclusive_scan`, `min_element` or `remove` with `par` finds no matching overload.
    - C++26's parallel `ranges` overloads are not implemented yet; `std::ranges::sort(std::execution::par, v)` is an error.
    - The policy types are not copyable: `auto p = std::execution::par;` reports call to deleted constructor of 'parallel_policy'. The standard only says these classes are defined as `{ unspecified }` and does not promise they are copyable, so this does not violate the standard. To store a policy, use `const auto& p = std::execution::par;`.

## Questions

!!! question "Question 1"
    In `std::sort(std::execution::par, v.begin(), v.end(), comp)`, `comp` protects an external counter with a `std::mutex` to count how many times it is called. Is this valid? What about with `par_unseq`?

<details markdown="1">
<summary>Answer</summary>

It is valid under `par`. Calls on the same thread do not interleave, so the lock cannot wait on itself; this is exactly what Example 3 of [algorithms.parallel.exec] ¶6 does. The counter is an external object, not modified through an argument, so it does not violate [algorithms.parallel.user] ¶1.

Under `par_unseq`, `mutex::lock` is a vectorization-unsafe function, and calling it is undefined behavior (¶7). Use a lock-free `std::atomic<int>::fetch_add` instead; lock-free atomic read-modify-write operations are not vectorization-unsafe.
</details>

!!! question "Question 2"
    An iterator's `operator++` loads data blocks on demand and may throw `std::bad_alloc`. If it is used with `std::count(std::execution::par, ...)`, what happens when it throws?

<details markdown="1">
<summary>Answer</summary>

Iterator operations are element access functions (¶3.1); when an element access function exits with an exception, the behavior is determined by the policy, and `par` specifies that `terminate` is called ([[execpol]]). The `bad_alloc` in [algorithms.parallel.exceptions] ¶1 refers to the algorithm's own allocation for parallelization failing, and is unrelated.
</details>

!!! question "Question 3"
    Is the result of `std::reduce(std::execution::seq, v.begin(), v.end(), 0.0)` necessarily equal to `std::accumulate(v.begin(), v.end(), 0.0)`?

<details markdown="1">
<summary>Answer</summary>

Not necessarily. `seq` only specifies that all element access functions run on the calling thread without interleaving. The result of `reduce` is defined by *GENERALIZED_SUM* ([[numerics.defns]]), which allows arbitrary grouping and reordering, independent of the policy. Floating-point addition is not associative, so the results may differ.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[algorithms.parallel.exec] ¶10: the semantics of invoking a parallel algorithm with an execution policy object of implementation-defined type are implementation-defined. This leaves an opening for vendor extensions such as GPU policies; see [[execpol]].

</details>

## Summary

| Question | Answer |
|---|---|
| Unit of the rules | element access functions: iterator operations, element operations, user invocables and operations on them |
| `seq` | the calling thread, not interleaved |
| `par` | multiple threads, not interleaved on the same thread; the caller avoids data races and deadlocks |
| `unseq`, `par_unseq` | may interleave on the same thread; calling vectorization-unsafe functions is UB |
| User function objects | must not modify objects through arguments or rely on object identity |
| Exceptions | `bad_alloc` if temporary memory is unavailable; `terminate` if an element access function throws |
| Complexity | "exactly N", "at most N" generally relaxed to O(N) |
