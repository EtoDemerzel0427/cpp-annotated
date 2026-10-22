---
title: Execution policies
summary: "The four execution policy objects in <execution>, seq, par, par_unseq and unseq, and their types; the type trait is_execution_policy; and the rule shared by all four policies: terminate is called when an element access function throws."
updated: 2026-10-19
---

!!! tldr
    - The standard defines four execution policy objects, `seq`, `par`, `par_unseq` and `unseq`; they are tags used to select the parallel overloads of algorithms.
    - A policy says which kind of parallelism is allowed, not that parallelism will happen. Which thread each call runs on, and in what order, under each policy is specified in [[algorithms.parallel]].
    - All four policies specify that `std::terminate` is called when an element access function throws.
    - `is_execution_policy<T>` tells whether `T` is an execution policy type, and users may not specialize it. The policy objects are `const`, so generic code must strip cv-qualifiers and references first.

```cpp run title="execpol.cpp" ok flags="-std=c++2c -fexperimental-library"
#include <algorithm>
#include <cassert>
#include <execution>
#include <functional>
#include <numeric>
#include <type_traits>
#include <vector>

namespace ex = std::execution;
static_assert(std::is_execution_policy_v<ex::parallel_policy>);
static_assert(!std::is_execution_policy_v<decltype(ex::par)>);  // const parallel_policy
static_assert(std::is_execution_policy_v<
                std::remove_cvref_t<decltype(ex::par)>>);

int main() {
  std::vector<int> v(100000);
  std::iota(v.begin(), v.end(), 0);
  std::sort(ex::par, v.begin(), v.end(), std::greater<>{});
  long long sum = std::reduce(ex::par_unseq, v.begin(), v.end(), 0LL);
  assert(v.front() == 99999 && sum == 99999LL * 100000 / 2);
  std::for_each(ex::unseq, v.begin(), v.end(), [](int& x) { x *= 2; });
  assert(v.front() == 199998);
}
```

The libc++ we test with provides these names only with `-fexperimental-library`; see the implementation status at the end of [[algorithms.parallel]].

## The four policies [execpol.general]

¶1 An object of an execution policy type indicates the kinds of parallelism allowed in the execution of an algorithm, and expresses the consequent requirements on the **element access functions** ([[g:element-access-function]]: iterator operations, element operations, user-provided function objects and so on). These types are declared in `<execution>`.

[execpol.objects] declares an `inline constexpr` object for each type. Each type is defined as `{ unspecified }`; the only use the standard has for them is to be a distinct type that selects the parallel overloads in overload resolution:

| Object | Type | Allows | Execution |
|---|---|---|---|
| `seq` | `sequenced_policy` | no parallelism | all on the calling thread, not interleaved |
| `par` | `parallel_policy` | multiple threads | may run on several threads; not interleaved on the same thread |
| `par_unseq` | `parallel_unsequenced_policy` | multiple threads and vectorization | may run on several threads; may interleave on the same thread |
| `unseq` {{c++20}} | `unsequenced_policy` | single-threaded vectorization | all on the calling thread, may interleave |

The precise rules for the last column are in [[algorithms.parallel.exec]] ¶4–¶7. Calls on the same thread being allowed to interleave means locking inside them is undefined behavior, for both `unseq` and `par_unseq`.

What `par` means is: the caller guarantees these element accesses can run in parallel without error, and the implementation may run them in parallel. The implementation may also not do so; falling back to sequential execution when resources are short is fully conforming ([[algorithms.parallel.exec#8]]).

Note 1 says implementations may provide additional execution policies beyond the standard ones, as extensions for special parallel architectures.

## Throwing means termination (¶2 of each subclause)

!!! std
    During the execution of a parallel algorithm with the `execution::parallel_policy` policy, if the invocation of an element access function exits via an exception, `terminate` is invoked.

¶2 of [execpol.seq], [execpol.par], [execpol.parunseq] and [execpol.unseq] are worded the same way: all four policies call `terminate` ([[except.terminate]]). In `std::sort(first, last, comp)` without a policy, an exception thrown by the comparison propagates to the caller; with `seq` added, it no longer does. Several exceptions may be thrown on several threads at once, and the standard has no mechanism to collect them.

## `is_execution_policy` [execpol.type]

¶2 `is_execution_policy<T>` is a unary type trait. It derives from `true_type` if `T` is a standard or implementation-defined execution policy type, and from `false_type` otherwise. ¶1 explains its purpose: to distinguish execution policies from other arguments and avoid ambiguity in overload resolution. `sort(policy, first, last)` and `sort(first, last, comp)` both have three arguments, and this trait is what tells them apart ([[algorithms.parallel.overloads#4]]).

¶3 A program adding specializations of `is_execution_policy` is {{ub}}. Note 1 says this preserves the implementation's exclusive right to create non-standard execution policies.

!!! pitfall "`decltype(std::execution::par)` is `const`"
    The policy objects are declared `inline constexpr`, so `decltype(std::execution::par)` is `const parallel_policy`, and `is_execution_policy_v<const parallel_policy>` is `false`. Generic code needs `remove_cvref_t` first, which is exactly how the standard's *execution-policy* concept is written ([[algorithms.parallel.defns#2]]).

## Evolution

C++17's [[P0024R2]] merged the Parallelism TS into the standard, introducing `seq`, `par`, `par_unseq` and `is_execution_policy`. C++20's [[P1001R2]] added `unseq`. C++26's parallel `ranges` overloads reuse these four policies without changing them.

C++26's sender/receiver framework in [[exec]] also lives in namespace `std::execution` and header `<execution>`, but it is a separate facility from the execution policies here.

## Questions

!!! question "Question"
    Is calling `new` and `delete` inside a `par_unseq` lambda undefined behavior? What about `std::atomic<int>::fetch_add`? And `std::mutex::lock`?

<details markdown="1">
<summary>Answer</summary>

`new` and `delete` are fine: the definition of vectorization-unsafe explicitly excludes memory allocation and deallocation functions ([[algorithms.parallel.defns#5]]).

When `std::atomic<int>` is lock-free, `fetch_add` is fine: lock-free atomic read-modify-write operations are excluded too.

`mutex::lock` synchronizes with the preceding `unlock`, making it a vectorization-unsafe function; calling it in `par_unseq` is undefined behavior ([[algorithms.parallel.exec#7]]).
</details>
