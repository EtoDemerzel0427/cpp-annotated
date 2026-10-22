---
title: "Synchronized output streams: osyncstream"
summary: "C++20's <syncstream> keeps whole chunks of output from interleaving when several threads write to the same stream: an osyncstream accumulates characters in its own buffer and, on emit() or destruction, hands them atomically as one unit to the target stream buffer."
updated: 2026-10-19
---

!!! tldr
    - Each thread wraps the shared stream in its own `std::osyncstream`; characters go into a private buffer first and are handed to the target all at once on `emit()` or destruction, so a whole chunk of output does not interleave with output from other `osyncstream`s.
    - All `emit()` calls to the same target form a total order, each synchronizing with the next, much like unlocking and locking a mutex.
    - By default, `flush()` and `std::endl` only record that a flush is needed; the target is actually flushed at the next `emit()`. `std::emit_on_flush` and `std::flush_emit` change this.
    - `osyncstream` wraps a stream buffer, not a stream object, and does not inherit the target stream's format state.
    - libc++ in our tests needs `-fexperimental-library` to provide `<syncstream>`.

```cpp title="osyncstream-threads.cpp" run ok
#include <iostream>
#include <syncstream>
#include <thread>
#include <vector>

int main() {
  std::vector<std::jthread> ts;
  for (int id = 0; id < 4; ++id)
    ts.emplace_back([id] {
      for (int i = 0; i < 3; ++i)
        std::osyncstream(std::cout) << "thread " << id << " step " << i << '\n';
    });
}
```

The order of the lines depends on thread scheduling, but every line is complete. If `std::osyncstream(std::cout)` is replaced with `std::cout`, the program has no data race (synchronized standard stream objects may be used concurrently, see [[iostream.objects]]), but `<<` from different threads can interleave, and fragments from another thread may end up in the middle of a line.

`<syncstream>` provides two class templates, `basic_syncbuf` and `basic_osyncstream`, plus the aliases `syncbuf`, `osyncstream` and the `w`-prefixed ones. [syncstream.syn] ¶1 states its purpose: synchronizing writes from multiple execution agents (threads and so on) to the same stream. `basic_syncbuf` is a stream buffer (see [[stream.buffers]]), and `basic_osyncstream` is an output stream that holds a `basic_syncbuf`.

!!! impl "libc++ needs `-fexperimental-library`"
    libc++ (Clang 23) marks `<syncstream>` as experimental. Without `-fexperimental-library`, `std::osyncstream` does not exist and `__cpp_lib_syncbuf` is not defined; with it, all the examples on this page compile and run, and the example above reports no data race under `-fsanitize=thread`. libc++ uses a global table of mutexes keyed by the address of the target stream buffer to make `emit`s to the same target mutually exclusive.

## Accumulate, then hand over at once [syncstream.syncbuf.overview]

¶1 Characters written to a `basic_syncbuf` are called its **associated output** ([[g:associated-output|associated output]]) and are stored in an internal buffer allocated with the object's own allocator. When `emit()` is called or the object is destroyed, the associated output is transferred to the wrapped stream buffer `*wrapped`. Each transfer is atomic with respect to transfers by other `basic_syncbuf` objects wrapping the same stream buffer.

The atomicity is only with respect to transfers by other `basic_syncbuf`s. Another thread that bypasses `osyncstream` and writes to `std::cout` directly is not bound by this lock, and its characters may appear in the middle of a transferred chunk.

```cpp title="emit-observe.cpp" run ok
#include <iostream>
#include <sstream>
#include <syncstream>

int main() {
  std::ostringstream sink;
  {
    std::osyncstream out(sink);
    out << "buffered";
    std::cout << "before emit: [" << sink.str() << "]\n";   // []
    out.emit();
    std::cout << "after emit:  [" << sink.str() << "]\n";   // [buffered]
    out << " tail";
  }                                                          // emits once more on destruction
  std::cout << "after scope: [" << sink.str() << "]\n";     // [buffered tail]
}
```

## What `emit` guarantees [syncstream.syncbuf.members]

¶1 `emit()` atomically transfers the associated output to `*wrapped`, so that it appears in the output as a contiguous sequence of characters. If `sync()` has been called since the last `emit()`, it calls `wrapped->pubsync()` after the transfer; otherwise it does not.

¶2 All `emit()` calls transferring characters to the same stream buffer behave as if executed in a total order consistent with the happens-before relation, and each `emit()` synchronizes with ([[intro.races]]) the `emit()` that follows it in that order.

This means: if thread A's output appears before thread B's output, every memory write A made before its `emit()` is visible to B after its `emit()`. It is the same as an unlock/lock pair on one mutex.

¶3 After success, the associated output is empty. ¶4 Returns `true` if all three of the following hold, otherwise `false`: `wrapped` is not null; all characters were transferred successfully; the call to `pubsync()` (if any) succeeded.

¶5 `emit()` may call member functions of `*wrapped` while holding a lock uniquely associated with `*wrapped`. The note in [syncstream.osyncstream.cons] ¶2 warns accordingly that improper use may deadlock. For example, if the wrapped stream buffer, in its `overflow`, logs through an `osyncstream` wrapping the same target, it tries to acquire the same lock again.

¶6–¶8 The other members: `get_wrapped()` returns `wrapped`, `get_allocator()` returns a copy of the allocator, and `set_emit_on_sync(b)` sets the *emit-on-sync* flag discussed below.

## A flush is only recorded [syncstream.syncbuf.virtuals]

¶1 `sync()` records that the wrapped stream buffer is to be flushed; then, if the *emit-on-sync* flag is true, it calls `emit()`. A note explains that when the flag is false (the default), the actual flush is deferred until the next `emit()`. ¶2 If `emit()` was called and returned `false`, `sync()` returns −1; otherwise 0.

So calling `flush()` or writing `std::endl` on an `osyncstream` outputs nothing immediately by default. This protects atomicity: if `flush` handed over half a chunk right away, the chunk would be split. The standard uses an example to show how `emit` relates to flushing ([syncstream.osyncstream.members] ¶2):

```cpp title="emit-and-flush.cpp" run ok
#include <iostream>
#include <syncstream>

int main() {
  std::osyncstream bout(std::cout);
  bout << "Hello," << '\n';      // no flush
  bout.emit();                   // characters transferred; cout not flushed
  bout << "World!" << std::endl; // flush noted; cout not flushed
  bout.emit();                   // characters transferred; cout flushed
  bout << "Greetings." << '\n';  // no flush
}                                // destruction: characters transferred; cout not flushed
```

Three manipulators in `<ostream>` ([[output.streams]]) change this behavior:

| Manipulator | Effect when the stream buffer is a `basic_syncbuf` |
|---|---|
| `emit_on_flush` | `set_emit_on_sync(true)`: every subsequent flush emits immediately |
| `noemit_on_flush` | `set_emit_on_sync(false)`: back to the default |
| `flush_emit` | `flush()` first, then `emit()` immediately; sets `badbit` on failure |

For a stream whose stream buffer is not a `basic_syncbuf`, the first two have no effect and `flush_emit` is just `flush()`. So generic code can write `os << std::flush_emit` unconditionally.

## Construction, moving and destruction [syncstream.syncbuf.cons], [syncstream.syncbuf.assign]

¶1–¶2 `basic_syncbuf(obuf, allocator)` sets `wrapped` to `obuf` and records the allocator. ¶3 The constructor throws nothing, except possibly when constructing a mutex or allocating memory. ¶4 The internal buffer is allocated with a copy of `allocator`.

¶5 After move construction, `*this` wraps the target `other` used to wrap, and the output in `other` not yet handed over is transferred to `*this`; `other`'s buffer is empty and `other.get_wrapped() == nullptr`. ¶6 This disassociates `other` from the target, ensuring that destroying `other` produces no output.

¶7–¶8 The destructor calls `emit()` and throws nothing: any exception thrown by `emit()` is caught and ignored. When exceptions thrown by the target stream need handling, call `emit()` explicitly inside a `try` block ([syncstream.osyncstream.members] ¶3).

[syncstream.syncbuf.assign] ¶1 Move assignment first calls `emit()` to hand over its own pending output, then move-assigns from `rhs`, with the result as if move-constructed from `rhs`. ¶2 Afterwards `rhs.get_wrapped() == nullptr`; the allocator propagates along if `propagate_on_container_move_assignment` is true and is otherwise unchanged. ¶4 This likewise disassociates `rhs`.

## `basic_osyncstream` [syncstream.osyncstream]

`basic_osyncstream` derives from `basic_ostream` and holds an exposition-only `basic_syncbuf sb`. When constructed from a `basic_ostream& os`, what it wraps is `os.rdbuf()`. So the format state of `os` (`hex`, `width` and so on) is not inherited; the `osyncstream` has its own; conversely, setting a format on the `osyncstream` does not affect `os`.

[syncstream.osyncstream.cons] ¶1 The constructor initializes `sb` with the target stream buffer and allocator, then initializes the base class with `addressof(sb)`. ¶3 Afterwards `get_wrapped()` returns that target. ¶4–¶5 The move constructor moves the base class and `sb` first, then calls `set_rdbuf(addressof(sb))`; afterwards `other.get_wrapped()` is null.

[syncstream.osyncstream.members] ¶1 The member `emit()` behaves as an unformatted output function: after constructing a sentry object it calls `sb.emit()`, and calls `setstate(badbit)` if that returns `false`. ¶4 `get_wrapped()` returns `sb.get_wrapped()`.

[syncstream.osyncstream.overview] ¶2–¶3 give two examples showing the two typical uses: a named object for a block, a temporary object for a single statement.

```cpp title="osyncstream-usage.cpp" run ok
#include <iostream>
#include <syncstream>

int main() {
  {
    std::osyncstream bout(std::cout);       // named object: for a block
    bout << "Hello, ";
    bout << "World!";
    bout << std::endl;                      // only notes that a flush is needed
    bout << "and more!\n";
  }                                         // destruction: transfers all characters and flushes cout

  std::osyncstream(std::cout) << "Hello, " << "World!" << '\n';   // temporary object: cout not flushed
}
```

The example in ¶5 shows that you can obtain the target with `get_wrapped()` and wrap it again. The following outputs two non-interleaved lines, with `Goodbye, Planet!` first, because the inner temporary is destroyed, and emits, first:

```cpp title="nested-wrap.cpp" run ok
#include <iostream>
#include <syncstream>

int main() {
  std::osyncstream bout1(std::cout);
  bout1 << "Hello, ";
  {
    std::osyncstream(bout1.get_wrapped()) << "Goodbye, " << "Planet!" << '\n';
  }
  bout1 << "World!" << '\n';
}
// Output:
// Goodbye, Planet!
// Hello, World!
```

## Common misconceptions

!!! pitfall "Using `osyncstream` as a long-lived log stream"
    All output stays in its buffer until destruction or an explicit `emit()`, and by default `flush` and `endl` do not make it appear either. If the program crashes, all of that output is lost, and in a long-running program the memory keeps growing. The intended use is one object per logical chunk of output: a temporary for a statement, or a named object for a block. If you really need to hold one for a long time, at least set `emit_on_flush`, or call `emit()` at suitable boundaries.

## Questions

!!! question "Question 1"
    Two threads each execute `std::osyncstream o(std::cout); o << std::hex << x;`. Does this change `std::cout`'s format flags?

<details markdown="1">
<summary>Answer</summary>

No. An `osyncstream` is an independent `basic_ostream` object with its own `basic_ios` state; it wraps `cout.rdbuf()`, not `cout` itself. Conversely, a `hex` already set on `cout` is not inherited by the `osyncstream`.
</details>

!!! question "Question 2"
    Thread A first assigns to a global variable `int n = 42;`, then executes `std::osyncstream(std::cout) << "ready\n";`. Thread B later writes a line to `std::cout` through an `osyncstream`, and that line appears after `ready`. Is B's subsequent read of `n` a data race?

<details markdown="1">
<summary>Answer</summary>

No. Both `emit()` calls transfer to `cout.rdbuf()`, so by [[syncstream.syncbuf.members#2]] they are in one total order, with A's `emit()` first, synchronizing with B's `emit()`. Hence A's write to `n` happens before B's read after its `emit()`, and B reads 42. Still, synchronization that depends on output order is hard to reason about; real code should use explicit synchronization.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[syncstream.syn]: the header includes `<ostream>` and declares `basic_syncbuf`, its non-member `swap`, `basic_osyncstream`, and the aliases `syncbuf`, `wsyncbuf`, `osyncstream`, `wosyncstream`.

[syncstream.syncbuf.assign] ¶3: move assignment returns `*this`. ¶5–¶6: `swap` requires `propagate_on_container_swap` to be true or the two allocators to be equal, and exchanges the state of the two. [syncstream.syncbuf.special] ¶1: the non-member `swap` is equivalent to `a.swap(b)`.

[syncstream.osyncstream.overview] ¶1: `Allocator` shall meet the *Cpp17Allocator* requirements.

</details>
