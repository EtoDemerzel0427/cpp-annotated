---
title: Standard library hardening (P3471)
summary: How C++26 turns library UB such as vector out-of-bounds access or dereferencing an empty optional into guaranteed termination. A subset of existing preconditions is marked as hardened preconditions, and whether a hardened implementation is provided is implementation-defined. Why only cheap bounds checks were chosen, why the contract violation mechanism was borrowed, and why the observe semantic was later excluded.
tags: hardening, safety, preconditions, contracts, UB, libc++, proposal
group: Library
updated: 2026-10-19
---

!!! tldr
    - C++26 re-labels the preconditions of a set of functions such as `vector::operator[]`, `optional::operator*` and `span::front()` as **hardened preconditions**: in a hardened implementation, violating them is a contract violation handled with a terminating semantic; in other implementations it is still UB ([[structure.specifications#3.5]]).
    - Whether an implementation is hardened is implementation-defined ([[intro.compliance#8]]). Like a freestanding implementation, it is a kind of implementation; the standard specifies neither how to turn it on nor that it be on by default.
    - There is only one kind of criterion for inclusion: a violation would cause an out-of-bounds access or a read of a nonexistent element, the call site has enough information to check, and the check is constant time. Checking all preconditions is explicitly listed as a non-goal.
    - P3471R4 originally allowed checking with the observe semantic, with UB after the contract-violation handler returns; [[P3878R1]] changed it so that only enforce or quick-enforce may be used.
    - libc++'s `_LIBCPP_HARDENING_MODE` is the predecessor of these rules: a check in FAST mode costs just one extra comparison and a `brk`, but it does not yet cover all the hardened preconditions C++26 lists, and does not define the `__cpp_lib_hardened_*` macros.

## One out-of-bounds read, three outcomes

```cpp title="oob.cpp" run ub
#include <cstdio>
#include <optional>
#include <string_view>
#include <vector>

int main(int argc, char** argv) {
  std::vector<int> v{1, 2, 3};
  std::optional<int> o;
  std::string_view s;
  switch (argv[1][0]) {
    case 'v': std::printf("%d\n", v[argc + 2]); break;  // out of bounds
    case 'o': std::printf("%d\n", *o); break;           // empty optional
    case 's': std::printf("%c\n", s.front()); break;    // empty string_view
  }
}
```

In C++23 all three violate the function's *Preconditions*, and the result is undefined behavior ([[structure.specifications#3.4]]). The standard library need not check, and the compiler gives no error. Compiled with Clang 23 + libc++ at `-O2` and run with `v`, `o` and `s` as arguments, the results in three configurations are:

| Configuration | `./oob v` | `./oob o` | `./oob s` |
|---|---|---|---|
| Default (not hardened) | Prints `5`, exit code 0 | Prints `0`, exit code 0 | Prints nothing, exit code 0 |
| `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` | SIGTRAP, exit code 133 | Same | Same |
| `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` | Prints an assertion message, then SIGABRT, exit code 134 | Same | Same |

Without hardening, the program reads some value past the end of `v`'s buffer and exits normally. The `s` line prints nothing: the `data()` of an empty `string_view` is a null pointer, reading it is UB, and the assembly shows the optimizer deleted the whole branch. Out-of-bounds reads can leak data and out-of-bounds writes can overwrite adjacent objects, which is exactly the most common source of memory safety vulnerabilities. The messages printed in DEBUG mode name the specific condition, for example:

```text
vector.h:414: libc++ Hardening assertion __n < size() failed: vector[] index out of bounds
optional:513: libc++ Hardening assertion this->has_value() failed: optional operator* called on a disengaged value
string_view:425: libc++ Hardening assertion !empty() failed: string_view::front(): string is empty
```

These switches existed before C++26. Each of the three major standard library implementations has its own: libc++'s `_LIBCPP_HARDENING_MODE`, libstdc++'s `_GLIBCXX_ASSERTIONS`, and MSVC STL's `_MSVC_STL_HARDENING`. MSVC STL's documentation says it checks exactly out-of-bounds element access, `pop_back()` on an empty container, and access to an empty `optional`/`expected`, ultimately calling `__fastfail` on failure. Only Clang and libc++ were available here, so the other two were not verified.

[[P3471R4]]'s starting question is: if every vendor already has one, why standardize? The paper gives three reasons. First, what matters most is making existing code safer, not demanding rewrites; changing `v[i]` to `v.at(i)` is not realistic for hundreds of millions of lines of code. Second, vendors differ in coverage, performance promises and how to turn it on, so users get no portable guarantee. Third, secure coding guidelines need wording they can cite, which vendor extensions cannot provide.

## Deployment experience

The paper's argument rests mainly on deployment. It cites a public report from Google: enabling this hardening across hundreds of millions of lines of code had a performance impact as low as 0.3%, and found over a thousand bugs, including security-relevant ones. The paper also mentions deployments in several codebases on Apple platforms, and a large amount of informal feedback received by libc++ maintainers.

This experience directly determined the direction of the design. The paper argues that checks enabled only in debug builds do nothing substantial for security; they must be light enough to stay on in production. From this follows a trade-off: a small set of checks that is widely enabled is worth more than a large set that few dare to enable. Fortunately, the most valuable checks (container bounds) are also the cheapest.

## The design space

### Check every precondition

The most thorough approach would have a hardened implementation check every precondition in the library. P3471 explicitly lists this as a non-goal, for two reasons.

First, it can't be done. Many preconditions are semantic requirements, such as the comparator given to `std::sort` being a strict weak ordering ([[alg.sorting]]), which the library cannot verify at reasonable cost. Second, it is too expensive. The goal is to be always on in production, and every check's cost is multiplied by the number of calls.

What was chosen in the end is a very narrow set. The first version of the paper only covered conditions that lead to out-of-bounds access; the later [[P3697R1]] states the criteria more explicitly: a violation would cause a memory safety problem (out-of-bounds access or reading uninitialized memory); the call site has all the data needed for the check; and the check is constant time with small overhead.

### What happens after a violation

Having settled which conditions to check, the behavior on a failed check still had to be specified. The paper's revisions went down three paths:

| Approach | Source | Outcome |
|---|---|---|
| Terminate the program in an implementation-defined way | P3471R0 | Replaced in R1 |
| Erroneous behavior | Discussed in the paper | Rejected |
| Contract violation | From P3471R1 on | Adopted |

**Erroneous behavior** is a new category of behavior in C++26: the program is wrong, but the behavior is well-defined, and implementations may diagnose it (see [[papers/erroneous-behaviour]]). The paper's reason for rejecting it is concrete: erroneous behavior only says the code is wrong, not what to do when the error happens. Under erroneous behavior, returning the last element when `vector::operator[]` is out of bounds would be conforming: well-defined, but useless; what users want is for the program to stop.

**Contract violation** comes from the contemporaneous contracts proposal ([[P2900R14]], see [[papers/contracts]]). A contract violation happens when a contract assertion is checked and its predicate is false, and what happens next is determined by the **evaluation semantic** ([[g:evaluation-semantic|evaluation semantic]]): ignore does not check; observe calls the contract-violation handler and continues once the handler returns; enforce calls the handler and then terminates; quick-enforce terminates directly ([[basic.contract.eval#1]]). The last two are called **terminating semantics**.

The paper chose contracts for two reasons: the language and the library get a unified framework for handling errors, which existing users had repeatedly asked for; and the contract-violation handler is replaceable, so users can log as they need. The paper also states that implementations need not actually write these checks as contract assertions; macros are fine too, as long as a violation goes through the contract violation handling mechanism.

The paper also discussed Profiles. If Profiles enter the standard in the future, hardening could be expressed as one of the profiles, but the paper argues against waiting for a larger feature that is still experimental.

### ignore and observe

Having borrowed contracts, the question was which of the four semantics may be used.

ignore was excluded from the start. P3471's reasoning: the standard specifies that violating a hardened precondition is in itself a contract violation, and by then we are past the point where ignore could skip the check. In other words, an implementation using ignore is not a hardened implementation.

observe was allowed in P3471R4. The paper argued that deployment experience showed observe is very useful for rolling out at scale: first only log without terminating, then switch to terminating after fixing the problems in the logs. R4's wording therefore said: evaluated with a checking semantic; if a non-terminating semantic is used and the contract-violation handler returns, the behavior is undefined.

[[P3878R0]] objected to this, and more thoroughly: its title says, in effect, that C++26 contracts are unsuitable for standard library hardening. Its technical arguments are two:

1. Under observe, after the handler returns, the function continues executing and the out-of-bounds access happens anyway. A hardened implementation that allows this outcome is not a memory safety mechanism.
2. C++26 contracts have no way to specify the semantic of a single assertion. A standard library has to support multiple compilers and cannot guarantee that hardened preconditions are always evaluated with a terminating semantic; and users may run their own contracts with ignore or observe, which hardening must be independent of.

The revision [[P3878R1]] narrowed its goal, proposing only to change checking semantic to terminating semantic and delete the sentence about UB after the handler returns. The paper says the authors of P3471 also considered this a defect fix. It also points out that this change does not guarantee the program terminates: if the implementation supports replacing the contract-violation handler, the handler can throw an exception, but even then the rest of the library function is not executed, so no UB occurs. Vendors that still want a log-only mode can provide a mode that checks but is not called hardening.

The libc++ used here still keeps an observe option (experimental, requiring `-fexperimental-library`). Running `./oob v` with FAST mode plus `-D_LIBCPP_ASSERTION_SEMANTIC=_LIBCPP_ASSERTION_SEMANTIC_OBSERVE`, the program first prints the assertion message, then goes on to print a value read out of bounds, with exit code 0. This is exactly the situation P3878 describes: the check happened, and so did the UB.

### A kind of implementation, not default behavior

P3471 did not make checking an obligation of every implementation; modelled on freestanding implementations, it adds a new kind of implementation. Whether an implementation is hardened is implementation-defined, and so is how to turn it on. The paper expects toolchains to provide a compiler option like `-fhardened`, but turning it on with a macro like `-D_LIBCPP_HARDENING_MODE=...` is also conforming.

The paper also writes down two constraints. Hardening should not require an ABI change, and implementations may allow hardened and non-hardened code to be mixed in one program; but whether mixing is allowed is deliberately left unspecified by the standard, to avoid over-constraining implementations.

This choice has a direct consequence: for programs that do not violate preconditions, hardened and non-hardened implementations behave identically. Hardening only specifies an outcome for executions that were UB to begin with. So P3471 left no incompatibility entry in Annex C.

## The final rules

### A new specification element ([[structure.specifications#3.5]])

The specification of a library function consists of a series of labelled elements, each specifying the consequences of violating it (see [[description]]). C++26 adds an element after *Preconditions* (¶3.4):

!!! std
    *Hardened preconditions*: … When invoking the function in a hardened implementation, prior to any other observable side effects of the function, contract assertions whose predicates are as described in the hardened precondition are evaluated with a terminating semantic.

    In a hardened implementation, when the function is invoked, contract assertions whose predicates are these conditions are evaluated with a terminating semantic before any other observable side effects of the function (¶3.5.1); in a non-hardened implementation, violating them is UB (¶3.5.2).

Compared with P3471R4 there are two changes. One is that checking semantic became terminating semantic and the sentence about UB after the handler returns was deleted; this is P3878R1's change. The other is that R4's one or more contract assertions is written as contract assertions in the current draft.

[[intro.compliance#8]] gives the other half:

!!! std
    It is implementation-defined whether the implementation is a *hardened implementation*. If it is a hardened implementation, violating a hardened precondition results in a contract violation.

    Whether an implementation is hardened is implementation-defined; in a hardened implementation, violating a hardened precondition results in a contract violation.

[[structure.specifications#4]] was changed accordingly: when *Effects* are written as *Equivalent to* some code, the *Hardened preconditions* of the function calls in that code apply as well. So `basic_string::front()`, specified as equivalent to `return operator[](0);`, brings in the hardened preconditions of `operator[]` too.

Ordinary *Preconditions* do not lose the possibility of being checked. [[res.contract.assertions#1]] allows implementations to check any precondition and postcondition with contract assertions, without requiring it. The difference is that *Hardened preconditions* must be checked in a hardened implementation, while *Preconditions* may go unchecked in any implementation.

### Which functions were included

P3471R4's changes concentrate on two categories: access functions that might access nonexistent elements, and modifiers that assume the container is non-empty.

| Class | `operator[]` | `front()` | `back()` | `pop_front()` | `pop_back()` |
|---|---|---|---|---|---|
| `array` | ✓ | ✓ | ✓ | | |
| `basic_string` | ✓ | ✓ | ✓ | | ✓ |
| `deque` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `forward_list` | | ✓ | | ✓ | |
| `inplace_vector` | ✓ | ✓ | ✓ | | ✓ |
| `list` | | ✓ | ✓ | ✓ | ✓ |
| `vector` | ✓ | ✓ | ✓ | | ✓ |
| `span` | ✓ | ✓ | ✓ | | |
| `basic_string_view` | ✓ | ✓ | ✓ | | |
| `mdspan` | ✓ | | | | |
| `bitset` | ✓ | | | | |
| `valarray` | ✓ | | | | |

In addition: `operator->` and `operator*` of `optional` and `expected`, and `expected::error()` (which requires `has_value()` to be false); `first`, `last` and `subspan` of `span`, and the requirement that the length equal the extent when a fixed-extent `span` is constructed from a run-time length; `remove_prefix` and `remove_suffix` of `string_view`; and the converting constructor from another `mdspan`.

The conditions for sequence containers are written in the general requirements in [[sequence.reqmts]]; for example, `a[n]` requires `n < a.size()` ([[sequence.reqmts#122]]), and `a.front()` requires `a.empty()` to be false ([[sequence.reqmts#72]]). Along the way, the paper wrote out some preconditions that had been implicit: previously the precondition of `vector::operator[]` could only be inferred from iterator validity.

Note that two similar conditions differ. `basic_string::operator[]` requires `pos <= size()` ([[string.access#1]]), so the terminating null character can be read; `basic_string_view::operator[]` requires `pos < size()`.

Before C++26 was finalized, [[P3697R1]] added a few more, which it calls omissions from the original proposal: `operator[]` and `current(skip, max_depth)` of `basic_stacktrace`, `shared_ptr<T[N]>::operator[]` ([[util.smartptr.shared.obs#9]]), `front`/`back` of `view_interface` ([[view.interface.members#1]]), and several members of `counted_iterator` and `common_iterator`. `counted_iterator` records the remaining length to the end, so it can check going past the end but not going back before the beginning; the paper considers checking half better than checking nothing. [[version.syn#3]] in the current draft lists the corresponding feature-test macros, with value `202502L` for the P3471 group and `202506L` for the group added by P3697; [[version.syn#7]] recommends that non-hardened implementations not define them.

### What was not included

P3471 devotes a section to some obvious omissions:

- **`erase(iterator)`**: requires the iterator to point to an element of this container. Contiguous containers can lower the iterator to a pointer and check whether it falls within the buffer; non-contiguous containers have no way to check without an ABI change or significant overhead.
- **Associative containers**: most of their preconditions are not directly related to spatial safety, and there is not enough implementation experience.
- **Algorithms**: almost all algorithms require valid ranges as input, but only contiguous iterators can be partially checked; whether two iterators belong to the same container or whether input and output ranges overlap generally cannot be checked (input iterators cannot go back).
- **The extents and layout mappings of `mdspan`**, and **the parts of `valarray` other than `operator[]`**: the interactions between classes are complex and need separate study, to avoid missing checks or checking twice.

New C++26 types are not necessarily hardened either. A `std::indirect` is valueless after being moved from, and dereferencing it then is still an ordinary *Preconditions* in the current draft ([[indirect.obs#1]]). [[P4349R0]] proposes making such preconditions of `indirect` and `polymorphic` hardened preconditions too; at the time of writing it had not been merged into the draft.

## Checking against libc++

### What a check compiles to

Compiling `int get(const std::optional<int>& o) { return *o; }` at `-O2` gives this AArch64 assembly:

<div class="compare" markdown="1">

```asm title="Not hardened"
ldr  w0, [x0]
ret
```

```asm title="FAST (quick-enforce)"
ldrb w8, [x0, #4]   ; load the engaged flag
tbz  w8, #0, LBB0_2
ldr  w0, [x0]
ret
LBB0_2:
brk  #0x1           ; trap
```

</div>

FAST adds one byte load and a branch that is almost never taken. DEBUG mode's fast path is the same as FAST; the difference is only in the failure branch: it loads a message string and calls `std::__libcpp_verbose_abort` to print and abort, rather than a single `brk` instruction. This corresponds to the two terminating semantics of contracts: quick-enforce terminates directly, enforce calls the handler first and then terminates. Comments in libc++'s headers say FAST and EXTENSIVE use quick-enforce by default, and DEBUG uses enforce.

The assembly of `vector::operator[]` and how the check is hoisted out of loops is covered in [[perf/reading-assembly]] and not repeated here.

### FAST mode is not yet a C++26 hardened implementation

libc++ 23 is a predecessor of C++26 hardening, not a hardened implementation in the standard's sense. A program that triggers each of the hardened preconditions listed above, run in four modes:

| Hardened precondition violated | NONE | FAST | EXTENSIVE | DEBUG |
|---|---|---|---|---|
| `span::subspan` out of range, `[]` out of bounds on `bitset`/`valarray`/`deque`/`string` | Not checked | 133 | 133 | 134 |
| `expected::error()` while holding a value, `mdspan` subscript out of bounds | Not checked | 133 | 133 | 134 |
| `pop_back()` on an empty `string`, `front()` of a `ref_view` (from `view_interface`) | Not checked | 133 | 133 | 134 |
| `counted_iterator(p, -5)` | Not checked | Not checked | 133 | 134 |
| `p[5]` on a `shared_ptr<int[3]>` | Not checked | Not checked | Not checked | Not checked |

133 is SIGTRAP and 134 is SIGABRT. libc++ classifies the check in `counted_iterator`'s constructor as uncategorized, which FAST mode does not enable; `shared_ptr::operator[]` has no check at all in this version, so that item of P3697 is not implemented yet. In addition, libc++'s `<version>` defines none of the `__cpp_lib_hardened_*` macros, and Clang 23 does not define `__cpp_contracts` either, so a failed check does not go through a replaceable contract-violation handler.

So today, portable reliance on hardening can go no further than what each implementation's documentation promises. The standard's role is to set a target all implementations will converge on.

### The overhead depends on whether checks can be eliminated

Whether a check can be proven redundant determines how large the overhead is. In the histogram counts below, the index in `hist_vec` comes from data, and the compiler cannot decide it in advance; the index in `hist_arr` is a `uint8_t`, and the array has exactly 256 elements, so the check is always true.

```cpp title="hist.cpp" run ok flags="-std=c++2c -O2 -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST"
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>

[[gnu::noinline]] void hist_vec(const std::vector<std::uint32_t>& keys,
                                std::vector<std::uint32_t>& h) {
  for (std::size_t i = 0; i < keys.size(); ++i) ++h[keys[i]];
}

[[gnu::noinline]] void hist_arr(const std::vector<std::uint8_t>& keys,
                                std::array<std::uint32_t, 256>& h) {
  for (std::size_t i = 0; i < keys.size(); ++i) ++h[keys[i]];
}

template <class F> double best_ms(F f) {
  double best = 1e30;
  for (int r = 0; r < 15; ++r) {
    auto t0 = std::chrono::steady_clock::now();
    f();
    auto t1 = std::chrono::steady_clock::now();
    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    if (ms < best) best = ms;
  }
  return best;
}

int main() {
  const std::size_t N = 1 << 24, B = 1 << 12;
  std::mt19937 g(42);
  std::vector<std::uint32_t> k32(N);
  std::vector<std::uint8_t> k8(N);
  for (std::size_t i = 0; i < N; ++i) { k32[i] = g() % B; k8[i] = g(); }
  std::vector<std::uint32_t> h(B);
  std::array<std::uint32_t, 256> a{};
  double t1 = best_ms([&] { hist_vec(k32, h); });
  double t2 = best_ms([&] { hist_arr(k8, a); });
  std::printf("vec %.2f arr %.2f (%u %u)\n", t1, t2, h[0], a[0]);
}
```

On an M2 Pro, compiled with NONE and with FAST, alternating 9 runs and taking the median (the machine was under heavy load, so only the ratios matter):

| Function | FAST / NONE | `brk` in the assembly |
|---|---|---|
| `hist_vec` | About 1.32 | 1, with one `cmp` plus `b.ls` per iteration in the hot loop |
| `hist_arr` | About 1.00 | 0, the check is eliminated entirely |

`hist_vec` is about 30% slower, partly from the comparison and branch on each iteration and partly because the loop is no longer unrolled 2-way. This is a microbenchmark that does nothing but subscript access, representing one of the worst cases; it does not contradict Google's whole-program 0.3%, since real programs spend most of their time outside such loops. When a check needs to go from a hot spot, you can let the compiler see that the condition is always true (as with the `uint8_t` index above), or, for sequential traversal, use a range-based `for`, which does not go through `operator[]`.

## Follow-up and current status

- **C++26**: [[P3471R4]] was merged together with contracts ([[P2900R14]]); [[P3697R1]] added `stacktrace`, `shared_ptr<T[N]>`, `view_interface`, `counted_iterator` and `common_iterator`; [[P3878R1]] removed observe. The history of contracts themselves is in [[history/contracts]].
- **After C++26**: there are proposals to extend the scope further, such as [[P4349R0]].
- **Implementations**: libc++'s FAST/EXTENSIVE/DEBUG modes, libstdc++'s `_GLIBCXX_ASSERTIONS` and MSVC STL's `_MSVC_STL_HARDENING` all predate the standard and differ in coverage. A list of each mode's semantics is in [[topics/undefined-behavior]]; how to use them in a project together with assertions and contracts is in [[toolchain/error-handling-strategy]].

What turning on hardening most often exposes is code that has always run by luck:

```cpp title="end.cpp" run ub
#include <cstdio>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  int* e = &v[v.size()];   // violates n < a.size()
  std::printf("%td\n", e - v.data());
}
```

This way of getting a past-the-end pointer has always been UB; it just looks fine on implementations that don't check. Without hardening it prints `3`; in FAST mode it gets SIGTRAP at `v[v.size()]`. [[P3878R0]] mentions that this idiom really does exist in real code. The correct way is `v.data() + v.size()`.

## Questions

!!! question "1. Can a hardened implementation use ignore?"
    An implementation provides a switch: hardened preconditions are compiled into the library as usual, but evaluated with the ignore semantic. Can it call itself a hardened implementation?

<details markdown="1">
<summary>Answer</summary>

No. [[structure.specifications#3.5]] requires these assertions to be evaluated with a terminating semantic in a hardened implementation, and ignore is not a terminating semantic ([[basic.contract.eval#1]]). P3471 excluded ignore from its first version, and P3878R1 excluded observe as well. Comments in libc++'s headers also say that choosing the ignore semantic does not give a conforming hardened implementation.

</details>

!!! question "2. A throwing contract-violation handler"
    In a hardened implementation that uses the enforce semantic and supports replacing the contract-violation handler, the user's handler throws an exception. When `v[10]` is out of bounds, does the library go on to perform the out-of-bounds read?

<details markdown="1">
<summary>Answer</summary>

No. By [[basic.contract.eval#11]], under enforce the contract-violation handler is called when a contract violation occurs; the handler exits via an exception, which propagates outward from the call site, and the body of `operator[]` is not executed further. [[structure.specifications#3.5.1]] also requires the check to happen before any other observable side effect of the function. P3878R1 discusses exactly this case: the program does not necessarily terminate, but it never enters the rest of the library function, so there is no UB.

</details>

!!! question "3. Why is there no Annex C entry?"
    C++26 makes some programs that used to run normally terminate in a hardened implementation. Why doesn't Annex C list this as an incompatibility?

<details markdown="1">
<summary>Answer</summary>

Only executions that violate preconditions are affected, and those executions were UB in C++23; the standard places no requirements on them, and termination is one of the outcomes UB allows. P3471 only re-labels existing preconditions as hardened preconditions and adds no new conditions (the paper states explicitly that it only writes out implicit conditions). For every program whose behavior is well-defined in C++23, hardened and non-hardened implementations behave the same, so there is no incompatibility to record.

</details>
