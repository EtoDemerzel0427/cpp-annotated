---
title: Exception propagation
summary: "Holding an exception outside its handler with exception_ptr, passing it across threads and rethrowing it later: the contracts of current_exception, rethrow_exception, make_exception_ptr and exception_ptr_cast; and exception chains built from nested_exception, throw_with_nested and rethrow_if_nested."
updated: 2026-10-19
---

!!! tldr
    - An exception object is destroyed when its handler exits. Calling `std::current_exception()` in the handler gives an `exception_ptr` that keeps the exception object alive, to hand to another thread or rethrow later.
    - `exception_ptr` is like a reference-counted smart pointer: it can be null, it can be copied, and it compares equal when pointing to the same exception.
    - `rethrow_exception(p)` requires `p` to be non-null; what it throws may be the original object or a copy.
    - `make_exception_ptr(e)` is equivalent to throwing `e` and catching it; the newly added `exception_ptr_cast<E>(p)` lets you inspect the exception without rethrowing.
    - `throw_with_nested` wraps the current exception inside a new one, and `rethrow_if_nested` gets the inner exception out; they can only be used in a handler.

## Taking an exception out of its handler [propagation]

```cpp run title="exception-ptr.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <thread>

int main() {
  std::exception_ptr err;               // default-constructed: null
  std::thread worker([&] {
    try {
      throw std::logic_error("from worker");
    } catch (...) {
      err = std::current_exception();   // obtain the exception inside the handler
    }                                   // err keeps the exception object alive
  });
  worker.join();                        // reading err after join has no data race

  if (err) {                            // rethrow_exception requires non-null
    try {
      std::rethrow_exception(err);
    } catch (const std::logic_error& e) {
      std::printf("main got: %s\n", e.what());
    }
  }
}
```

At the language level, only code inside a handler can reach the exception object, through the `catch` parameter or `throw;`, and it is destroyed as soon as the handler exits ([[except.throw]]). But an exception in a worker thread has to be handed to the thread waiting for the result, which `std::future`, `std::async` and thread pools all need to do; sometimes errors must be collected first and handled together later, or an exception must pass through a C callback that doesn't support exceptions. C++11's `std::exception_ptr` ([[N2179]]) solves this.

### Properties of `exception_ptr` (¶1–¶8)

```cpp
using exception_ptr = unspecified;
```

- ¶1 An `exception_ptr` can be used to refer to an exception object.
- ¶2 It meets *Cpp17NullablePointer* ([[nullablepointer.requirements]]): it can be default-constructed and copied, compared with `nullptr`, and tested in a condition.
- ¶3 Two non-null `exception_ptr`s compare equal if and only if they refer to the same exception.
- ¶4 Default construction gives the null value.
- ¶5 It doesn't implicitly convert to any arithmetic, enumeration or pointer type.
- ¶6 Note 1 says an implementation might use a reference-counted smart pointer. Both libc++ and libstdc++ do: internally a pointer to the exception object, with copying atomically incrementing the reference count in the Itanium ABI exception header.
- ¶8 All its member functions are `constexpr`.

¶7 deals with data races: operations on an `exception_ptr` access and modify only the `exception_ptr` object itself, not the exception it refers to. So two threads each copying and destroying `exception_ptr`s that refer to the same exception don't race; nor does calling `rethrow_exception` or `exception_ptr_cast` on them. Note 2 warns that if `rethrow_exception` throws the same exception object rather than a copy, two threads concurrently accessing that rethrown object may still race.

### `current_exception` (¶9)

```cpp
constexpr exception_ptr current-exception() noexcept;   // exposition only
exception_ptr current_exception() noexcept;
```

¶9 Returns an `exception_ptr` referring to the **currently handled exception** ([[g:currently-handled-exception]]) or a copy of it; returns the null value if no exception is being handled. There are four specific rules:

1. The referenced object remains valid at least as long as there is an `exception_ptr` referring to it. This is why the exception object in the example outlives the handler.
2. If memory needs to be allocated and the allocation fails, it returns an `exception_ptr` referring to a `bad_alloc` object. The function is `noexcept` and can't throw.
3. Whether two calls refer to the same object is unspecified, i.e. whether a copy is made each time is unspecified (Note 3). In our tests the results of two calls compare equal: the Itanium ABI implementation just increments the reference count without copying.
4. If copying the current exception throws, it returns an `exception_ptr` referring to that new exception; if that isn't possible, it refers to a `bad_exception` object ([[bad.exception]]). Note 4 explains that copying the new exception could fail too, and substituting `bad_exception` avoids infinite recursion.

The currently handled exception isn't limited to `catch` blocks. When `std::terminate` is entered because of an uncaught exception, an implicit handler is active ([[except.handle]]), so a custom terminate_handler can also get that exception with `current_exception()` (see [[support.exception]] for an example).

The exposition-only *`current-exception`* is `constexpr`, while the public `current_exception()` isn't. `make_exception_ptr` below is `constexpr`, and its specification is written as throw-then-catch, which needs a version usable during constant evaluation to describe it.

### `rethrow_exception` (¶10–¶11)

```cpp
[[noreturn]] constexpr void rethrow_exception(exception_ptr p);
```

¶10 Precondition: `p` is not a null pointer. Passing a null `exception_ptr` is undefined behavior; this is the most common misuse, so check `if (p)` before calling.

¶11 Let *u* be the exception object referred to by `p`, or a copy of it. Whether a copy is made is unspecified, and memory for the copy is allocated in an unspecified way.

- ¶11.1 If allocating memory for *u* fails, throws `bad_alloc`;
- ¶11.2 otherwise, if copying throws an exception, throws that exception;
- ¶11.3 otherwise, throws *u*.

Since no copy may be made, if you modify `e` in `catch (std::runtime_error& e)`, other threads may see the modification through the same `exception_ptr`; that is exactly the data race Note 2 of paragraph 7 mentions. Catching by `const&` avoids it.

### `make_exception_ptr` (¶12)

```cpp
template<class E> constexpr exception_ptr make_exception_ptr(E e) noexcept;
```

¶12 Creates an `exception_ptr` referring to a copy of `e`, as if by:

```cpp
try { throw e; } catch (...) { return current-exception(); }
```

Actually throwing means going through the full exception throw and handler search, which is expensive. "As if" leaves implementations room to construct the exception object directly.

`e` is passed by value, so passing a base class reference bound to a derived object slices it. Pass the exception's most derived type.

!!! impl "libc++ doesn't really throw"
    When conditions allow (exceptions and RTTI enabled, and the runtime library providing `__cxa_init_primary_exception`), libc++ allocates the exception object with `__cxa_allocate_exception`, copy-constructs `e` in it, and fills in the type information and destructor with `__cxa_init_primary_exception`, producing an exception object identical to one from a real `throw`. Only in special cases such as Objective-C++ does it fall back to `try { throw e; } catch (...)`.

### `exception_ptr_cast` (¶13–¶14)

```cpp
template<class E>
  constexpr optional<const E&> exception_ptr_cast(const exception_ptr& p) noexcept;
template<class E> void exception_ptr_cast(const exception_ptr&&) = delete;
```

Previously, the only way to find out what an `exception_ptr` held was to `rethrow_exception` and `catch`, at the cost of a full throw. `exception_ptr_cast` is a function added in a recent working draft that lets you inspect it without rethrowing (the feature-test macro `__cpp_lib_exception_ptr_cast` has the value `202603L`). At the time of writing, libc++ doesn't provide it yet.

¶14 If `p` is non-null and a handler of type `const E&` would be a match for the exception object ([[except.handle]]), returns an `optional` holding a reference to that exception object; otherwise returns `nullopt`.

¶13 Mandates: `E` is a cv-unqualified complete object type that is not an array type, a pointer type, or a pointer-to-member type. Note 5 explains the last item: when `E` is a pointer, a `const E&` handler can match through a conversion, binding to a temporary rather than to the exception object itself, so no reference to the exception object could be returned.

The rvalue version is deleted to reject `exception_ptr_cast<E>(std::make_exception_ptr(x))`: the temporary `exception_ptr` is the only owner of the exception object, which is destroyed at the end of the full-expression, leaving the returned reference dangling.

## Exception chains [except.nested]

```cpp run title="nested-exception.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <string>

void print(const std::exception& e, int depth = 0) {
  std::printf("%*s%s\n", depth * 2, "", e.what());
  try {
    std::rethrow_if_nested(e);       // throw the inner exception if there is one
  } catch (const std::exception& inner) {
    print(inner, depth + 1);
  } catch (...) {}
}

void open_file(const std::string& name) {
  throw std::runtime_error("cannot open " + name);
}

void load_config() {
  try {
    open_file("app.toml");
  } catch (...) {
    std::throw_with_nested(std::runtime_error("load_config failed"));
  }
}

int main() {
  try {
    load_config();
  } catch (const std::exception& e) {
    print(e);
  }
}
```

The program prints:

```text
load_config failed
  cannot open app.toml
```

After catching a low-level exception, high-level code often wants to throw a new exception with more context without losing the original one. Exception chains are designed for this.

### `nested_exception` (¶1–¶5)

```cpp
class nested_exception {
public:
  nested_exception() noexcept;
  nested_exception(const nested_exception&) noexcept = default;
  nested_exception& operator=(const nested_exception&) noexcept = default;
  virtual ~nested_exception() = default;
  [[noreturn]] void rethrow_nested() const;
  exception_ptr nested_ptr() const noexcept;
};
```

¶1 `nested_exception` is designed for use as a mixin through multiple inheritance; it captures and stores the currently handled exception.

¶3 Its constructor calls `current_exception()` and stores the result, so the inner exception is captured only if it is constructed inside a handler.

¶2 Note 1 says it has a virtual destructor, making it a polymorphic class, so its presence can be tested for with `dynamic_cast`. It doesn't derive from `std::exception` and has no `what()`.

¶4 `rethrow_nested()`: if the stored `exception_ptr` is null, calls `std::terminate`; otherwise throws the stored exception. `nested_ptr()` returns the stored `exception_ptr` (¶5).

### `throw_with_nested` (¶6–¶8)

```cpp
template<class T> [[noreturn]] void throw_with_nested(T&& t);
```

¶6–¶7 Let `U` be `decay_t<T>`; the precondition is that `U` meets *Cpp17CopyConstructible*.

¶8 If `U` is a class type that is not final and doesn't already have `nested_exception` as a base, throws an exception of unspecified type that is publicly derived from both `U` and `nested_exception`, constructed from `std::forward<T>(t)`. Otherwise throws `std::forward<T>(t)` directly. That is, for `int`, final classes, and types that already have `nested_exception`, `throw_with_nested` degenerates to an ordinary `throw`, and the inner exception isn't saved.

### `rethrow_if_nested` (¶9)

```cpp
template<class E> void rethrow_if_nested(const E& e);
```

¶9 If `E` isn't a polymorphic class type, or `nested_exception` is an inaccessible or ambiguous base class of `E`, does nothing. Otherwise executes:

```cpp
if (auto p = dynamic_cast<const nested_exception*>(addressof(e)))
  p->rethrow_nested();
```

The `dynamic_cast` here is a cross-cast: from `E` to its sibling base class `nested_exception`. A cross-cast requires the class to be polymorphic, which is why paragraph 2 gives `nested_exception` a virtual destructor.

!!! pitfall "Calling `throw_with_nested` outside a handler"
    ```cpp run title="nested-outside.cpp"
    #include <cstdio>
    #include <exception>
    #include <stdexcept>

    int main() {
      try {
        std::throw_with_nested(std::runtime_error("outside"));  // not in a handler
      } catch (const std::exception& e) {
        std::puts(e.what());
        std::rethrow_if_nested(e);   // nested_ptr() is null: calls std::terminate
      }
    }
    ```
    The `nested_exception` base of the synthesized type calls `current_exception()` at construction, and outside a handler it stores a null pointer. Afterwards `rethrow_if_nested` reaches the null-pointer branch of `rethrow_nested()` and calls `std::terminate` (¶4), rather than doing nothing because there is no inner exception. In our tests this program prints `outside` and is then terminated.
