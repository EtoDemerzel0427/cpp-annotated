---
title: Mutual exclusion
summary: "Which mutexes, locks and call-once utilities <mutex> and <shared_mutex> provide and when each is used; why only std::mutex is guaranteed constant initialization."
updated: 2026-10-19
---

!!! tldr
    - A mutex by itself does not prevent data races. What it provides is synchronization: `unlock()` synchronizes with a subsequent lock operation that acquires the same mutex. Protection comes from holding the same lock on every access to the shared data.
    - `<mutex>` provides four mutexes, three RAII locks, `std::lock`/`std::try_lock` and `call_once`; `<shared_mutex>` provides two reader-writer locks and `shared_lock`.
    - Use `std::mutex` by default; `shared_mutex` when reads far outnumber writes; the timed versions only when a timeout is needed; a recursive mutex usually indicates a design that could be improved.
    - Only `std::mutex` has a `constexpr` default constructor, so a namespace-scope `std::mutex` is always constant-initialized and has no initialization order problem.

¶1 [thread.mutex] provides three mechanisms for mutual exclusion: mutexes, locks and call once. The standard says they make it easier to write race-free programs ([[intro.multithread]]). That phrasing is accurate: a mutex is only a means of establishing happens before, and the programmer must still ensure that the same lock is held whenever the shared data is accessed.

## Components at a glance

| Subclause | Contents | Note on this site |
|---|---|---|
| [mutex.syn], [shared.mutex.syn] | the synopses of the two headers | this page |
| [thread.mutex.requirements] | the synchronization semantics of mutexes and the six mutex classes | [[thread.mutex.requirements]] |
| [thread.lock] | the RAII locks `lock_guard`, `scoped_lock`, `unique_lock`, `shared_lock`, and the tags `defer_lock`, `try_to_lock`, `adopt_lock` | [[thread.lock]] |
| [thread.lock.algorithm] | `std::try_lock`, `std::lock`: locking several objects without deadlock | [[thread.lock]] |
| [thread.once] | `once_flag`, `call_once` | [[thread.once]] |

`<mutex>` ([mutex.syn]) declares four classes, `mutex`, `recursive_mutex`, `timed_mutex` and `recursive_timed_mutex`; three locks, `lock_guard`, `scoped_lock` and `unique_lock`; `try_lock` and `lock` taking at least two arguments; and `once_flag` and `call_once`.

The default constructors of the three tag types `defer_lock_t`, `try_to_lock_t` and `adopt_lock_t` are all `explicit`. So `{}` cannot implicitly convert to some tag, and an ambiguous form like `unique_lock lk(m, {})` does not compile.

`<shared_mutex>` ([shared.mutex.syn]) declares `shared_mutex`, `shared_timed_mutex` and `shared_lock`. `shared_timed_mutex` was added in C++14, earlier than `shared_mutex` (C++17): C++14 standardized the version with timeouts first, and C++17 added the simpler, possibly faster version without them.

## Choosing among the six mutexes

| Type | Recursive | Timeout | Shared | When to use |
|---|---|---|---|---|
| `mutex` | no | no | no | the default choice |
| `recursive_mutex` | yes | no | no | a function holding the lock calls another function that also takes it (usually a sign the design could be improved) |
| `timed_mutex` | no | yes | no | wait at most for some time |
| `recursive_timed_mutex` | yes | yes | no | both of the above |
| `shared_mutex` | no | no | yes | reads far outnumber writes |
| `shared_timed_mutex` | no | yes | yes | reads far outnumber writes, and timeouts are needed |

## Only std::mutex is guaranteed constant initialization

In [[thread.mutex.requirements]], only `mutex`'s default constructor is declared `constexpr mutex() noexcept;`. So a namespace-scope `std::mutex` is always **constant-initialized** ([[basic.start.static]]) and is ready before any dynamic initialization. If dynamic initialization code in another translation unit locks it, it will never meet a mutex that has not yet been constructed.

The constructors of the other five mutexes are not `constexpr`; when using them at namespace scope, the initialization order across translation units must be considered.

## The implementation's view

!!! impl "Sizes and implementation in libc++/macOS (Clang 23, Apple Silicon)"
    | Type | `sizeof` | Underlying |
    |---|---|---|
    | `mutex` | 64 | `pthread_mutex_t`, static initializer `PTHREAD_MUTEX_INITIALIZER` |
    | `recursive_mutex` | 64 | `pthread_mutex_t` with the `PTHREAD_MUTEX_RECURSIVE` attribute |
    | `timed_mutex` | 120 | a `mutex`, a `condition_variable` and a `bool` |
    | `shared_mutex` | 168 | a `mutex`, two `condition_variable`s and a state word |
    | `shared_timed_mutex` | 168 | same as above |
    | `condition_variable` | 48 | `pthread_cond_t` |
    | `once_flag` | 8 | a state word |

    `timed_mutex` and `shared_mutex` are implemented by libc++ itself with condition variables, rather than wrapping native objects such as `pthread_rwlock_t`; macOS pthreads also lack `pthread_mutex_timedlock`. So their `try_lock_for` is affected by the condition variable timing behavior described in [[thread.req]].
