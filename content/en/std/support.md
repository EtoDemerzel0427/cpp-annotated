---
title: Language support library
summary: "A guide to Clause 17: the functions the core language calls implicitly behind the scenes and the types of the objects it creates implicitly are defined here, such as operator new, type_info, initializer_list and the comparison category types."
updated: 2026-10-19
---

!!! tldr
    - After reading this clause you can answer questions such as: which function does `new T` actually call? Why must `<compare>` be included before using `<=>`? Which objects does `std::exit` destroy?
    - The components of this clause are referenced directly by the core language clauses; they are effectively language features defined in headers.
    - Some language features require the corresponding header to be included first, otherwise the program is ill-formed; the global `operator new`, on the other hand, is declared without including any header, and programs can replace it.
    - Most headers in this clause must be provided by freestanding implementations too, because without them the corresponding language features can't be used.

## The library the language calls behind the scenes

¶1 Clause 17, [support], describes the functions that are implicitly called during the execution of certain C++ programs, the types of objects that are implicitly generated, and the headers that declare them.

"Implicitly" is the key word. A program doesn't write `operator new(sizeof(T))`, but `new T` calls it; it doesn't write `throw std::bad_cast()`, but a failed `dynamic_cast<T&>` throws one; it doesn't construct a `std::initializer_list`, but `{1, 2, 3}` produces one in certain contexts; it never mentions `std::coroutine_traits`, but every coroutine relies on it to find its promise type. The core language names library components directly in these places, so these components are in effect part of the language.

## Map of the clause

¶2 Table 42 lists the subclauses and their headers:

| Subclause | Headers | Connection to the core language |
|---|---|---|
| [[support.types]] Common definitions | `<cstddef>`, `<cstdlib>` | `size_t`, the type of `sizeof`; `ptrdiff_t`, the type of pointer subtraction; `nullptr_t`, the type of `nullptr`; `std::byte` |
| [[support.limits]] Implementation properties | `<cfloat>`, `<climits>`, `<limits>`, `<version>` | Querying the implementation-determined properties in [[basic.fundamental]]; library feature-test macros |
| [[support.arith.types]] Arithmetic types | `<cstdint>`, `<stdfloat>` | Fixed-width integers; aliases for extended floating-point types ([[basic.extended.fp]]) |
| [[support.start.term]] Start and termination | `<cstdlib>` | Returning from `main` is equivalent to calling `exit` ([[basic.start.main]]); the order of `atexit` and destruction of static objects ([[basic.start.term]]) |
| [[support.dynamic]] Dynamic memory management | `<new>` | The allocation and deallocation functions called by new-expressions and delete-expressions ([[new.delete]]), `bad_alloc`, `std::launder` |
| [[support.rtti]] Type identification | `<typeinfo>`, `<typeindex>` | `type_info`, the result of `typeid`; `bad_cast`, `bad_typeid` |
| [[support.srcloc]] Source location | `<source_location>` | The file name and line number of a call site |
| [[support.exception]] Exception handling | `<exception>` | `std::terminate` ([[except.terminate]]), `uncaught_exceptions`, `exception_ptr` |
| [[support.contract]] Contract-violation handling | `<contracts>` | The `contract_violation` passed to the contract-violation handler ([[basic.contract]]) |
| [[support.initlist]] Initializer lists | `<initializer_list>` | The `initializer_list` produced by list-initialization ([[dcl.init.list]]) |
| [[cmp]] Comparisons | `<compare>` | The result types of `<=>` ([[expr.spaceship]]) |
| [[support.coroutine]] Coroutines | `<coroutine>` | Promise type lookup, coroutine handles ([[dcl.fct.def.coroutine]]) |
| [[support.runtime]] Other runtime support | `<csetjmp>`, `<csignal>`, `<cstdarg>`, `<cstdlib>` | Variadic arguments ([[expr.call]]), `longjmp`, what can be done in a signal handler |
| [[support.c.headers]] C headers | `<stdio.h>` and others | Interoperation with C code |

## Three ways the language and the library are coupled

**The header must be included first.** `<typeinfo>` must be included before using `typeid` ([[expr.typeid]]), `<compare>` before using `<=>` ([[expr.spaceship]]), `std::initializer_list` must already be declared when list-initialization uses it ([[dcl.init.list]]), and coroutines need `std::coroutine_traits` ([[dcl.fct.def.coroutine]]). Without the header the program is ill-formed.

<div class="compare" markdown="1">

```cpp run error
struct P {
  int x;
  auto operator<=>(const P&) const
    = default;
};
// error: <compare> not included
```

```cpp run ok
#include <compare>
struct P {
  int x;
  auto operator<=>(const P&) const
    = default;
};
```

</div>

**Implicitly declared, replaceable.** The global `operator new` and `operator delete` are implicitly declared in every translation unit, without including `<new>`. A program can supply its own versions to replace them ([[dcl.fct.def.replace]]), but the replacements must meet the requirements of [[new.delete]]. Whether the contract-violation handler can be replaced is up to the implementation ([[basic.contract.handler]]).

**Library in form, implemented by the compiler.** `offsetof`, `std::launder`, `std::source_location::current` and the operations of `coroutine_handle` can't be written in ordinary C++ code. Clang implements them with built-ins, such as `__builtin_offsetof` and `__builtin_launder`.

## Kinds of requirements to tell apart when reading library clauses

Library clauses describe each function with a fixed set of elements ([[structure.specifications]]). Their consequences differ, so keep track of them when reading this clause:

| Element | Consequence if not met | Example in this clause |
|---|---|---|
| *Mandates* | The program is ill-formed, diagnostic required | `std::launder<T>` requires `T` not to be a function type or `void` |
| *Constraints* | The declaration doesn't participate in overload resolution | The shift operators of `std::byte` require the shift amount to be an integer type |
| *Preconditions* | Undefined behavior | `coroutine_handle::resume` requires the coroutine to be suspended and not at its final suspend point |
| *Required behavior* | Requirements on replacement and handler functions; undefined behavior on violation | A replacement `operator new` must throw `bad_alloc` on failure; a `terminate_handler` must not return |

When *Effects* says "Equivalent to", the specified semantics are those of that code, undefined behavior included.

## Freestanding implementations

A freestanding implementation is one that can run without an operating system, as is common in kernel and embedded development, and it need provide only a subset of the standard library ([[compliance]]). This clause's `<cstddef>`, `<limits>`, `<new>`, `<typeinfo>`, `<exception>`, `<initializer_list>`, `<compare>`, `<coroutine>`, `<source_location>`, `<contracts>`, `<cstdarg>` and others are all in that subset, because without them language features such as `new`, `typeid`, `<=>` and coroutines couldn't be used.
