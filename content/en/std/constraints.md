---
title: Constraints on programs
summary: "The rules a program using the standard library must follow: arguments must be valid, and rvalue reference arguments are treated as unique references; accessing library objects across threads must not cause data races; replacement functions, handler functions and types used as template arguments must meet the library's requirements; a program in which a concept is satisfied but not modeled is IFNDR."
updated: 2026-10-19
---

!!! tldr
    - Arguments passed to library functions must be valid. Passing values such as dangling pointers or out-of-range iterators is undefined behavior, even if the function's description lists no precondition.
    - Passing an object to a library function with `std::move(x)` lets the library assume no other reference refers to it, so `v.push_back(std::move(v[0]))` isn't guaranteed to work, while `v.push_back(v[0])` is.
    - Several threads calling `const` members of one library object at the same time is safe; modifying it while another thread reads it is a data race. An object's construction must happen before every access, and every access before its destruction, `std::mutex` included.
    - If what users supply to the library (a replacement `operator new`, a `terminate_handler`, a type put in a container, a comparator) doesn't meet the library's requirements, the behavior is undefined; so is instantiating a template such as `std::map` with an incomplete type when that isn't explicitly allowed.
    - Concepts check only syntax. When a type satisfies a concept but doesn't meet its semantic requirements, the program is ill-formed, no diagnostic required.

This subclause lists the constraints a program must obey when using the standard library. The library's implementation takes these constraints as given, and compilers usually can't check them, so the consequence of a violation is almost always **undefined behavior** (UB: the standard places no requirements on the program's behavior) or **IFNDR** (ill-formed, no diagnostic required: the program is ill-formed, but the compiler need not report it; see [[intro.compliance]]).

The use of namespaces ([[namespace.constraints]]) and reserved names ([[reserved.names]]) involve more material, and each has its own page.

## Arguments passed to library functions [res.on.arguments]

### Invalid values are always UB (¶1.1, ¶1.2)

```cpp ub
#include <cstring>
int main() {
  const char* p = nullptr;
  return std::strlen(p);   // UB: a null pointer isn't a valid string
}
```

¶1 The following three rules apply to all arguments to all functions in the standard library, unless a function explicitly states otherwise.

¶1.1 If an argument has an invalid value, the behavior is undefined. Invalid values include values outside the domain of the function and pointers invalid for their intended use. This is a catch-all rule: even if a function's description lists no *Preconditions*, passing it a dangling pointer, an out-of-range iterator or a null `const char*` is UB.

¶1.2 If an argument is described as an array, the pointer passed must actually point to a large enough array, and all address computations and object accesses the function makes when accessing it as an array must be valid.

### Rvalue reference arguments are treated as unique references (¶1.3)

<div class="compare" markdown="1">

```cpp run ok
#include <string>
#include <vector>
int main() {
  std::vector<std::string> v{"a", "b"};
  v.push_back(v[0]);
  // the library must handle the case
  // where the argument is one of its own elements
}
```

```cpp run
#include <string>
#include <vector>
int main() {
  std::vector<std::string> v{"a", "b"};
  v.push_back(std::move(v[0]));
  // not guaranteed: the library may assume the argument
  // doesn't overlap the container's elements
}
```

</div>

`push_back` may need to grow the storage. When it does, the library moves the old elements into the new storage, and if the argument happens to refer to one of the old elements, the order of operations matters. For lvalue arguments the standard gives the library no exemption, so the library must handle this aliasing case correctly.

¶1.3 If an argument binds to an rvalue reference parameter, the implementation may assume that this parameter is a unique reference to that argument. Note 2 explains what this means: when a program passes an lvalue to a library function with `std::move(x)`, it is telling the library that it may treat `x` as a temporary, so the library can skip aliasing checks. So the code on the right violates the library's assumptions. `v.insert(pos, std::move(v.back()))` and `s.append(std::move(s))` are the same situation.

This rule has two qualifications:

- Note 1: if the parameter is a forwarding reference (`T&&` with `T` deduced) and is deduced as an lvalue reference, the argument isn't bound to an rvalue reference. So `v.emplace_back(v[0])` isn't affected, and the library still has to handle aliasing.
- The argument passed to a move assignment operator may be `*this`. So self-move-assignment `x = std::move(x)` on a standard library type isn't UB; [[lib.types.movedfrom#2]] says the object is afterwards in a valid but unspecified state.

## Accessing library objects across threads [res.on.objects]

¶1 If calling standard library functions from different threads may introduce a **data race** ([[g:data-race]]: two threads access the same memory location, at least one access is a write, and there is no synchronization), the behavior of the program is undefined. When data races occur is specified by [[res.on.data.races]].

Together, the two subclauses form the standard library's thread-safety model, often summarized as "the same as `int`":

| Operation | Result |
|---|---|
| Several threads call `const` member functions of the same object at the same time | Safe: the library doesn't modify shared state in `const` calls |
| One thread modifies an object while another reads it | Data race, UB |
| Several threads each operate on different objects | Safe: the library doesn't access shared objects other than the arguments |
| Objects explicitly specified as shareable (`std::atomic`, `std::mutex`, `std::cout`…) | As specified for each |

```cpp ub
#include <mutex>
#include <thread>
int main() {
  auto* m = new std::mutex;
  std::thread t([m] { std::lock_guard g(*m); });
  delete m;   // UB: the access to *m in the thread doesn't necessarily happen before the destruction
  t.join();
}
```

¶2 When an object of a standard library type is accessed, the beginning of the object's lifetime must **happen before** ([[g:happens-before]]) the access, and the access must happen before the end of its lifetime; otherwise the behavior is undefined. Note 2 specifically points out that this holds even for objects such as `std::mutex` that are themselves used for synchronization.

A mutex can protect other data, but it can't protect its own creation and destruction. In the example above, constructing `*m` happens before the thread is started, which is fine; but there is no ordering at all between `delete m` and the locking in the thread. The correct way is `t.join()` first, then `delete m`.

## User-supplied components must meet the requirements [res.on.functions]

¶1 In certain cases the library depends on components supplied by the program: replacement functions, handler functions, and operations on types used to instantiate library templates. If these components don't meet their requirements, the standard places no requirements on the implementation.

¶2 In particular, the behavior is undefined in the following cases:

| ¶ | Case | Example |
|---|---|---|
| 2.1 | A replacement function doesn't implement the semantics of its *Required behavior* paragraph | A replacement `operator new` returns a null pointer on failure |
| 2.2 | A handler function doesn't implement the semantics of its *Required behavior* paragraph | A `terminate_handler` returns |
| 2.3 | Operations on a type used as a template argument don't implement the semantics of the applicable requirements subclause | A comparator isn't a strict weak ordering; `==` isn't an equivalence relation |
| 2.4 | A replacement function, handler function or destructor operation exits via an exception, unless specifically allowed | A container element's destructor throws |
| 2.5 | A library template is instantiated, or a concept evaluated, with an incomplete type, unless specifically allowed for that component | See the example below |

***Required behavior*** is a kind of paragraph in library function descriptions that says what a replacement or user-installed version must do ([[structure.specifications#5]]).

¶2.3 is the legal consequence of all the Cpp17 named requirements ([[utility.requirements]]): when a type doesn't meet requirements such as *Cpp17LessThanComparable* or *Cpp17Hash*, the compiler mostly won't complain, but the program has UB. The second half of ¶2.3 is just as important: unless otherwise specified, these operations may report failure by throwing an exception, and the library must handle that correctly. The exception safety guarantees of the containers are built on this.

```cpp ub
#include <map>
#include <vector>
struct Node {
  std::vector<Node> children;   // OK: vector explicitly allows incomplete types
  std::map<int, Node> index;    // UB: map has no such permission (¶2.5)
};
int main() {}
```

Inside the definition of `Node`, `Node` is still an incomplete type. Components that explicitly allow incomplete element types include `vector`, `list` and `forward_list` (when the allocator meets the [[allocator.requirements.completeness|completeness requirements]], and the element type must become complete before certain members are used), as well as `unique_ptr`, `shared_ptr` and others. `map`, `deque` and `unordered_map` aren't among them; the example compiles in practice, but the standard doesn't guarantee it.

Type traits have their own rule ([[meta.rqmts]]): most traits allow incomplete types, but if the result could differ once the type later becomes complete, the behavior is undefined, for example asking `is_trivially_copyable` about an incomplete type.

## Replacement functions [replacement.functions]

```cpp run ok
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <vector>

static std::size_t count = 0;

void* operator new(std::size_t n) {   // replaces the global operator new
  ++count;
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc{};             // must throw on failure
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  std::vector<int> v(100);
  std::printf("allocations: %zu\n", count);   // prints 1 in our tests
}
```

Some library functions are **replaceable**: a program can supply a definition with the same signature, called a **replacement function** ([[g:replacement-function]]), which displaces the default version supplied by the implementation before the program starts ([[dcl.fct.def.replace]]).

¶1 For replaceable functions, the semantic descriptions in the library clauses apply both to the default version and to the program's replacement. A replacement function must meet its *Required behavior* paragraph, otherwise it is the UB of ¶2.1 in the previous section.

The replaceable functions in the current draft are:

| Function | Subclause |
|---|---|
| All forms of the global `operator new`, `operator new[]`, `operator delete` and `operator delete[]` (including the `nothrow`, aligned and sized versions, but not the placement forms) | [[new.delete]] |
| `std::is_debugger_present()` {{c++26}} | [[debugging]] |
| The contract-violation handler `::handle_contract_violation`; whether it is replaceable is implementation-defined | [[basic.contract.handler]] |
| `std::execution::parallel_scheduler_replacement::query_parallel_scheduler_backend()` {{c++26}} | [[exec.parschedrepl]] |

Common mistakes when replacing `operator new`:

- Returning a null pointer on failure instead of throwing `bad_alloc`. The `new` expression would construct an object at the null pointer, which is the UB of ¶2.1.
- Replacing only `operator new` without the matching `operator delete`. If your own `new` isn't implemented with `malloc`, deallocation will be mismatched.
- Declaring the replacement function `inline`, which is IFNDR ([[dcl.fct.def.replace#1]]). Declaring it `static` is outright ill-formed, because global allocation functions can't have internal linkage ([[basic.stc.dynamic.allocation]]); Clang 23 reports an error.
- Calling functions in the replacement that themselves allocate memory, such as `std::cout`, causing infinite recursion.

## Handler functions [handler.functions]

```cpp run ok
#include <cstdio>
#include <new>

void my_new_handler() {
  std::fputs("out of memory\n", stderr);
  throw std::bad_alloc{};   // must free memory and return, throw bad_alloc, or terminate
}

int main() {
  std::set_new_handler(my_new_handler);
  return std::get_new_handler() == my_new_handler ? 0 : 1;
}
```

A **handler function** is a function the program installs at run time and the library calls when a particular event occurs. The standard library has two kinds:

- [[g:new-handler|`new_handler`]]: called when allocation in `operator new` fails, installed with `set_new_handler` (¶2.1) and read with `get_new_handler` (¶3.1);
- [[g:terminate-handler|`terminate_handler`]]: called by `std::terminate`, installed with `set_terminate` (¶2.2) and read with `get_terminate` (¶3.2).

¶1 The library provides a default version only for `terminate_handler`. `new_handler` is null by default, in which case `get_new_handler()` returns a null pointer and `operator new` throws `bad_alloc` directly when allocation fails.

What a handler function must do is written in the *Required behavior* of [[new.handler]] and [[terminate.handler]]. For example, a `terminate_handler` must end the program and can't return to its caller; if it returns, that is the UB of [res.on.functions] ¶2.2.

¶4 Calls to the `set_*` and `get_*` functions don't introduce data races. A call to one of the `set_*` functions **synchronizes with** ([[g:synchronizes-with]]) subsequent calls to the same `set_*` function and to the corresponding `get_*` function. In other words, after one thread calls `set_terminate(h)`, a subsequent `get_terminate()` in another thread sees `h`. Implementations usually achieve this with atomic variables.

## Deriving from standard library classes [derived.classes]

¶1 Virtual member functions of standard library base classes may be overridden in program-defined derived classes ([[class.virtual]]). This is one of the extension mechanisms the library explicitly leaves to users:

| Base class | Commonly overridden virtual functions |
|---|---|
| `std::exception` and its derived classes | `what()` |
| `std::basic_streambuf` | `overflow`, `underflow`, `sync`… |
| `std::pmr::memory_resource` | `do_allocate`, `do_deallocate`, `do_is_equal` |
| `std::error_category` | `name`, `message`… |
| The derived classes of `std::locale::facet` | The various `do_*` functions |

```cpp run ok
#include <ostream>
#include <sstream>
#include <streambuf>

// a streambuf that uppercases letters and forwards them
class upper_buf : public std::streambuf {
  std::streambuf* dest_;
protected:
  int_type overflow(int_type ch) override {
    if (traits_type::eq_int_type(ch, traits_type::eof()))
      return traits_type::not_eof(ch);
    char c = traits_type::to_char_type(ch);
    if (c >= 'a' && c <= 'z') c = static_cast<char>(c - 'a' + 'A');
    return dest_->sputc(c);
  }
public:
  explicit upper_buf(std::streambuf* d) : dest_(d) {}
};

int main() {
  std::stringbuf sink;
  upper_buf ub(&sink);
  std::ostream os(&ub);
  os << "hello";
  return sink.str() == "HELLO" ? 0 : 1;
}
```

An overriding function must still meet the semantics specified for the base class's virtual function. For example, `memory_resource::do_allocate` must return suitably aligned storage or throw an exception.

This rule is only about virtual functions. Publicly deriving from a class without a virtual destructor, such as `std::vector`, isn't prohibited, but `delete`-ing a derived object through a base class pointer is UB ([[expr.delete]]).

## Satisfying and modeling [res.on.requirements]

```cpp ifndr
#include <algorithm>
#include <vector>
struct Weird {
  int v;
  bool operator==(const Weird&) const { return false; }   // a == a is false
};
int main() {
  std::vector<Weird> w{{1}, {2}};
  auto it = std::ranges::find(w, Weird{1});   // requires Weird to model equality_comparable
  return it == w.end();
}
```

When the compiler checks a concept it looks only at syntax: whether expressions are valid and whether types match up. This is called **satisfying** the concept ([[temp.constr.decl]]). But a concept's description also contains **semantic requirements** written in prose; for example, `equality_comparable` requires `==` to mean equality, so it must be reflexive. `Weird` above satisfies `equality_comparable` but doesn't meet it semantically.

¶1 A sequence of template arguments is said to **model** ([[g:models-concept]]) a concept `C` if it satisfies `C` and meets all the semantic requirements of `C`.

¶2 If the validity or meaning of a program depends on whether a sequence of template arguments models a concept, and the concept is satisfied but not modeled, the program is ill-formed, no diagnostic required.

¶3 If the semantic requirements of a declaration's constraints ([[structure.requirements]]) are not modeled at the point of use, the program is likewise ill-formed, no diagnostic required. The call to `ranges::find` above is such a case.

Why is this IFNDR, while failing a Cpp17 requirement in the previous section is UB? Concepts take part in overload resolution and in `requires` checks, so whether they are modeled can change which function a program selects and which code is valid; it affects the meaning of the program, not just the behavior of one run. The core language uses IFNDR for similar problems, for example an atomic constraint with different satisfaction results at different points ([[temp.constr.atomic]]).

## Don't impersonate standard headers [alt.headers]

¶1 If a file that isn't provided by the implementation has a name equivalent to a standard library header and is placed in one of the standard places for included files (system include directories, directories given with `-isystem` and so on), the behavior is undefined.

The typical scenario is a polyfill: the compiler doesn't have `<expected>` yet, so you write a file named `expected` yourself and put it on the system include path. Other headers of the standard library may have their own assumptions about the contents of `<expected>`, and after a compiler upgrade there will be two `<expected>`s.

The right way is to use your own header name and namespace (such as `<tl/expected.hpp>`) and choose between them with `__has_include(<expected>)` or the feature-test macro `__cpp_lib_expected`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[constraints.overview] ¶1 merely lists the contents of the subclauses of this section: use of namespaces, reserved names, headers, using library classes as base classes, replacement functions, and installing handler functions at run time.

</details>

## Questions

!!! question "Question 1"
    Does calling `std::printf` for logging inside your replacement `operator delete(void*)` violate the standard? What about `std::cout << "freed\n"`?

<details markdown="1">
<summary>Answer</summary>

At the level of the standard, the *Required behavior* of `operator delete` only requires it to deallocate the memory correctly (doing nothing for a null pointer) and not throw. Calling `printf` doesn't violate that in itself.

In practice it is dangerous. Output to `std::cout` may allocate memory, and allocation and deallocation go through your replacement `operator new` / `operator delete`, causing recursion or reentrancy; some C libraries' `printf` also allocates a buffer on its first call. `operator delete` may also be called during the destruction of static objects, when other global state may already have been destroyed. So replacement functions usually log only with primitives that don't allocate, such as POSIX `write`.
</details>

!!! question "Question 2"
    Is `std::string s = "abc"; s = std::move(s);` UB? Can you still call `s.size()` afterwards?

<details markdown="1">
<summary>Answer</summary>

It isn't UB. [res.on.arguments] ¶1.3 explicitly allows the argument passed to a move assignment operator to be `*this`, and [[lib.types.movedfrom#2]] says a standard library type is in a valid but unspecified state after self-move-assignment. So `s.size()` can be called, though its return value is unknown; operations without preconditions, such as `s.clear()` and `s = "x"`, can be used as well.

For a user type, the result of self-move-assignment depends on the type's own implementation. But library algorithms may self-move-assign the same element internally, so types put into containers or handed to algorithms must cope with it: Note 2 of *Cpp17MoveAssignable* requires that `rv` still meet the component's requirements even when `t` and `rv` are the same object ([[utility.arg.requirements]]).
</details>
