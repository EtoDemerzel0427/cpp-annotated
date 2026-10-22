---
title: Storage allocation errors
summary: "The two layers of handling allocation failure: first call the new_handler installed by the program to try to free memory, then throw bad_alloc; for an invalid array length the new-expression throws bad_array_new_length (Clang actually throws bad_alloc)."
updated: 2026-10-19
---

!!! tldr
    - When the default `operator new` fails to allocate, it first calls the current new_handler; with no new_handler installed, it throws `std::bad_alloc`.
    - A new_handler may do only one of three things: free memory and return, throw an exception of the `bad_alloc` family, or terminate the program.
    - The initial new_handler is a null pointer; `set_new_handler` returns the old value, and `get_new_handler` reads the current one.
    - When the `n` in `new T[n]` is negative or too large, the *new-expression* itself throws `bad_array_new_length`, which derives from `bad_alloc`. Clang 23 actually throws `bad_alloc`, so portable code should catch the base class.

## new_handler: asking for help on failure [new.handler]

```cpp run title="new-handler.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

char* reserve = nullptr;   // emergency memory set aside

void on_oom() {
  if (reserve) {
    std::free(reserve);    // free memory and return: operator new retries
    reserve = nullptr;
    return;
  }
  throw std::bad_alloc();  // nothing left to free: throw
}

int main() {
  reserve = static_cast<char*>(std::malloc(1 << 20));
  std::new_handler old = std::set_new_handler(on_oom);
  std::printf("%d %d\n", old == nullptr,
              std::get_new_handler() == on_oom);   // 1 1
  std::set_new_handler(old);
  std::free(reserve);
}
```

Set aside a block of memory at startup and release it when memory runs out, giving the program one chance to rescue itself. That is the typical use of a new_handler.

¶1 `new_handler` is `void (*)()`, the type of a **handler function** ([[g:new-handler]]). `operator new` and `operator new[]` call it when they can't satisfy a request for storage. The call happens in the loop of the default `operator new` ([[new.delete.single#3]]): allocation fails, the handler is called, and after it returns, allocation is tried again.

¶2 Required behavior: a new_handler shall do one of the following three things.

- ¶2.1 make more storage available for allocation and then return;
- ¶2.2 throw an exception of type `bad_alloc` or a class derived from it;
- ¶2.3 terminate the program without returning to the caller, for example by calling `std::abort`.

This is a requirement on the program. If the handler returns without freeing memory, `operator new` keeps retrying forever and the program hangs. If the handler throws an exception outside the `bad_alloc` family, it violates the Required behavior and the behavior is undefined ([[res.on.functions]]).

## Installing and reading [set.new.handler], [get.new.handler]

```cpp
new_handler set_new_handler(new_handler new_p) noexcept;
new_handler get_new_handler() noexcept;
```

`set_new_handler` makes `new_p` the current handler (¶1) and returns the previous handler (¶2). Paragraph 3 says the initial handler is a null pointer, so by default `operator new` throws `bad_alloc` directly on failure. `get_new_handler` returns the current handler, and Note 1 reminds us that it may be a null pointer. Concurrent calls to the two don't introduce data races ([[res.on.data.races]]).

!!! pitfall "The new_handler is called only by `operator new`"
    A `malloc` failure doesn't call it. In a program that replaces `operator new`, if the replacement doesn't call `get_new_handler()` itself, the installed handler is never called either: the standard only requires replacements to meet the Required behavior, not to call the handler ([[new.delete]]).

!!! note "Per-class handlers"
    *Effective C++* describes a technique: a class's member `operator new` first installs a class-specific handler with `set_new_handler`, calls `::operator new`, and then restores the original handler with RAII. It relies on `set_new_handler` returning the old value. The new_handler is global state, so this technique isn't safe in multithreaded programs.

## `bad_alloc` [bad.alloc]

```cpp
class bad_alloc : public exception {
public:
  constexpr const char* what() const noexcept override;
};
```

¶1 When the implementation reports a failure to allocate storage, the type of the exception object thrown is `bad_alloc`.

¶2 `what()` returns an implementation-defined null-terminated byte string. Default construction, copy construction and copy assignment don't throw, and after copying, `what()` has the same contents; these are conventions shared by all standard exception classes ([[exception#2]]).

Where `bad_alloc` is thrown:

- when the global `operator new` / `operator new[]` fails to allocate ([[new.delete.single#2]]), and replacements must do the same;
- when standard library containers fail to allocate through `std::allocator<T>::allocate`;
- when a new_handler throws it deliberately (¶2.2);
- its derived class `bad_array_new_length` is thrown for an invalid array length (see below).

`what()` became `constexpr` in C++26, to go with exceptions during constant evaluation. Clang 23 doesn't yet support throwing exceptions during constant evaluation, and libc++'s `bad_alloc::what()` isn't `constexpr` yet either.

## `bad_array_new_length` [new.badlength]

```cpp run title="bad-array-new-length.cpp" impl
#include <cstdio>
#include <new>

int main(int argc, char**) {
  long n = argc - 2;              // -1 at run time
  try {
    int* p = new int[n];
    std::printf("%p\n", (void*)p);
    delete[] p;
  } catch (const std::bad_array_new_length&) {
    std::puts("bad_array_new_length");  // required by the standard
  } catch (const std::bad_alloc&) {
    std::puts("bad_alloc");             // what Clang 23 does
  }
}
```

`n * sizeof(int)` can overflow `size_t`. Early implementations would silently allocate a block that was too small, causing a buffer overflow. Since C++11, the *new-expression* must check the array length first ([[expr.new#8]]). The length is invalid if it is negative before conversion, if the total size to allocate exceeds the implementation's limit, or if the number of initializers exceeds the number of array elements.

When the length is invalid, the allocation function isn't called:

- If the length expression is a potentially-evaluated core constant expression, the program is ill-formed. Clang 23 reports "array is too large" for `new int[-1]`.
- Otherwise, if the allocation function that would be called is non-throwing (for example `new (std::nothrow) int[n]`), the value of the *new-expression* is a null pointer.
- Otherwise, the *new-expression* throws an exception of a type that would match a handler of type `std::bad_array_new_length`.

¶1 `bad_array_new_length` derives from `bad_alloc` and is used to report an array length less than zero or greater than an implementation-defined limit. `catch (const std::bad_alloc&)` catches it too.

!!! impl "Clang throws `bad_alloc`"
    When Clang finds an invalid length at run time, it doesn't throw `bad_array_new_length`; instead it passes `size_t(-1)` as the size to `operator new[]` and relies on the allocation failing with `bad_alloc`. So the program above prints `bad_alloc` with Clang 23 at both `-O0` and `-O2`, which doesn't conform to the standard. GCC calls the runtime library's `__cxa_throw_bad_array_new_length` instead.

    There is also a side effect: if the `printf` in the example is removed, `p` is unused, and `-O2` deletes the whole `new` / `delete` pair, so not even `bad_alloc` is thrown. The nothrow form isn't affected: `new (std::nothrow) int[n]` returns a null pointer with Clang 23, as the standard requires.

## Questions

!!! question "Question"
    Can a new_handler call `operator new`?

<details markdown="1">
<summary>Answer</summary>

The standard doesn't prohibit it, but it is dangerous. If the inner `operator new` also fails, the same handler is called again, possibly recursing forever. A handler should only free memory; if it really needs to allocate, it should first uninstall itself with `set_new_handler(nullptr)`.
</details>
