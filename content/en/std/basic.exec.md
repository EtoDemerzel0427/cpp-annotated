---
title: Program execution
summary: "A guide to 6.10: the order of evaluation within a thread, visibility between threads, whether a thread can keep making progress, how a program starts and terminates, and the ordering relations that tie these together."
updated: 2026-10-19
---

!!! tldr
    - 6.10 specifies how the [[intro.abstract|abstract machine]] runs, in four parts: single-threaded order of evaluation, multithreaded data races, forward progress guarantees, and program start and termination.
    - Order within a single thread is described by sequenced before; adding synchronization edges between threads gives happens before.
    - The two most common kinds of UB have the same structure: unsequenced conflicting accesses within one thread, and conflicting accesses between threads with no happens before (data races).
    - The initialization order and destruction order of static variables are described with the same relations.

6.10 [basic.exec] has no text of its own; it is just a container for four subclauses:

| Subclause | Question it answers | Notes on this site |
|---|---|---|
| 6.10.1 Sequential execution | In one thread, in what order do evaluations happen? Why is `i = i++ + i` UB? | [[intro.execution]] |
| 6.10.2.1–2 Multi-threaded executions and data races | When is a write by one thread visible to another? What is a data race? | [[intro.multithread]] |
| 6.10.2.3 Forward progress | Why can compilers delete infinite loops without side effects? Is a thread guaranteed to make progress? | [[intro.progress]] |
| 6.10.3 Start and termination | What happens before and after `main`? In what order are static variables initialized and destroyed? | [[basic.start]] |

The next subclause, 6.11 [[basic.contract]], is C++26's contract assertions, whose run-time semantics are also described with the relations defined here; for example, a precondition is sequenced before the function body.

## The ordering relations

```
sequenced before          order within the same thread ([intro.execution]/8)
synchronizes with         synchronization edges between threads, provided by atomic operations, mutexes, thread creation and join ([intro.races]/6)
happens before            the two above combined, then the transitive closure ([intro.races]/7)
strongly happens before   the part of happens before that the seq_cst total order must respect ([intro.races]/8)
```

These relations tie the four subclauses together:

- Within a single thread, if a modification of a memory location and another access to it are unsequenced, the behavior is undefined ([[intro.execution#10]]). Between threads, if neither of two conflicting accesses happens before the other, it is a data race, also UB ([[intro.races#17]]). The former is about sequenced before, the latter about happens before.
- All static initialization strongly happens before any dynamic initialization ([[basic.start.static#2]]). Variables with ordered initialization in the same translation unit are initialized in the order of their definitions ([[basic.start.dynamic#3]]). Static objects are destroyed in the reverse order of their construction, and this order is also judged by strongly happens before ([[basic.start.term#4]]).
- Forward progress guarantees answer a different question: however these relations are arranged, is a thread guaranteed to reach its next step?

## Reading order

1. [[intro.execution]]: first get clear on single-threaded sequenced before, and which operators C++17 gave an order of evaluation.
2. [[intro.multithread]]: add synchronization on top of sequenced before and understand the memory model. Read together with [[atomics.order]] and [[atomics.fences]].
3. [[intro.progress]]: why compilers can delete infinite loops, and what parallel algorithms promise about threads.
4. [[basic.start]]: static initialization order and termination order, the part most likely to cause trouble in practice.
5. [[basic.contract]]: the run-time semantics of C++26 contracts.

!!! history "Evolution at a glance"
    - C++98/03 described single-threaded order of evaluation with sequence points, and the standard had no threads. The rules for start and termination were essentially in place: initialization in order within a translation unit, unspecified order across translation units.
    - C++11 replaced sequence points with sequenced before, added threads, the memory model, data races and forward progress guarantees, made initialization of function-local static variables thread-safe, and added `thread_local`.
    - C++17 gave operators like `<<`, `=` and `[]` an order of evaluation ([[P0145R3]]); parallel algorithms brought forward progress guarantees of different strengths; inline variables introduced partially-ordered initialization.
    - C++20 revised the semantics of seq_cst and redefined strongly happens before ([[P0668R5]]), weakened release sequences ([[P0982R1]]), and added `constinit`.
    - C++26 removed `memory_order::consume` from the core memory model ([[P3475R2]]); trivial infinite loops are no longer UB; contract assertions were added.
