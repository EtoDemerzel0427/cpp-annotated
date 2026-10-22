---
title: Constraints on implementations
summary: "What a standard library implementation must guarantee and what it may decide freely: transitive inclusion of headers, function signatures and ADL, data races, properties of library classes, exceptions, and the state of moved-from objects."
updated: 2026-10-19
---

!!! tldr
    - A standard header may include other headers along the way, but a program can rely only on the inclusions written in the synopsis. Using a name from a header you didn't include may fail to compile on another implementation.
    - Implementations may add overloads and default arguments to member functions, so taking the address of a standard library function or forming a pointer to a member function isn't portable.
    - When several threads call const member functions of the same object at the same time, or each operate on different objects, the library guarantees no data race results.
    - Library destructors don't throw; implementations may add `noexcept` to non-virtual functions but may not add `constexpr` on their own.
    - A standard library object that has been moved from is in a valid but unspecified state: you can assign to it and call functions without preconditions, but you don't know its value.

[[constraints]] specifies the rules a program must follow when using the standard library; this subclause, [conforming], constrains the implementation in turn: which behaviors the implementation must guarantee, and which details it may decide freely. Portable code relies only on the former.

## Headers may include each other [res.on.headers]

<div class="compare" markdown="1">

```cpp run ifndr
#include <vector>
int main() {
  std::vector<int> v{3, 1, 2};
  std::sort(v.begin(), v.end());
}
```

```cpp run ok
#include <algorithm>
#include <vector>
int main() {
  std::vector<int> v{3, 1, 2};
  std::sort(v.begin(), v.end());
}
```

</div>

With libc++ (Clang 23), the program on the left fails with "no member named 'sort'", while on another implementation it may compile fine. Both outcomes conform to the standard.

¶1 A C++ header may include other C++ headers. It must provide all the declarations in its own synopsis, and if its synopsis says it includes another header, it must also provide all the declarations of that header. For example, the synopsis of `<iostream>` says it includes `<ios>`, `<streambuf>`, `<istream>` and `<ostream>`, so including only `<iostream>` is enough to use `std::ostream`; all the container headers and `<utility>` state that they include `<compare>` and `<initializer_list>`.

Any other transitive inclusion is an implementation detail. [[using.headers#3]] requires a program to include the header declaring a name before using it, with no diagnostic required on violation. So the program on the left compiling on some implementation doesn't mean it is correct. libc++ has been reducing transitive inclusions between headers in recent years, and this kind of code is what most often breaks when upgrading the compiler.

¶2 Entities defined in several headers, such as `size_t` and `NULL`, must have compatible definitions everywhere, so including these headers in any order never produces a redefinition error. ¶3 A C header (of the `<stdlib.h>` form) may include only its corresponding C++ header ([[headers]]).

## Function signatures and lookup

### Non-member functions [global.functions]

¶1 It is unspecified whether any non-member functions in the standard library are defined as `inline`. A program can rely neither on a function having a symbol in the library binary nor on it not having one.

¶2 An implementation may declare additional non-member functions, such as helpers with reserved names or additional overloads of standard names. The condition is that the results of calls in valid programs are unaffected: a call to a signature described in the standard behaves as if the implementation declared no additional signatures. ¶3 An implementation shall not add default arguments to non-member functions. An extra default argument amounts to an extra signature and would make an otherwise non-viable call viable.

Precisely because extra overloads may exist, taking the address of a standard library function may be ambiguous or give an unexpected type. [[namespace.std#6]] says that unless the standard designates a function as an addressable function, the result of a program taking the address of, or a reference to, a standard library function is unspecified, possibly ill-formed.

¶4 Unless otherwise specified, when a standard library function calls a non-operator, non-member function internally, it doesn't use functions from other namespaces found by argument-dependent lookup (ADL, which looks up function names in the namespaces of the argument types; see [[basic.lookup.argdep]]). That is why library implementation code is full of qualified calls such as `std::move(x)` and `std::__invoke(...)`: functions in user namespaces that happen to have the same name won't be called by mistake.

Operators are the exception: when the library calls `==`, `<` or `<<` it must go through ADL, otherwise operators users defined for their own types couldn't be found. Note 1 also mentions cases specified otherwise, such as swap: [[swappable.requirements]] requires the user's `swap` to be found through ADL.

```cpp run ok
#include <algorithm>
#include <vector>
namespace app {
  struct X { int v; };
  bool operator==(X a, X b) { return a.v == b.v; }
}
int main() {
  std::vector<app::X> v{{1}, {2}};
  // *it == value inside std::find finds app::operator== via ADL
  return std::find(v.begin(), v.end(), app::X{2}) != v.end() ? 0 : 1;
}
```

### Member functions [member.functions]

¶2 For a non-virtual member function, an implementation may declare a different set of signatures, provided that any call that would select an overload from the standard's signatures behaves the same as if that overload were selected. Note 1 gives examples: adding parameters with default values, replacing a function with default arguments by several overloads, or adding signatures for the same name.

Users can't redeclare or overload member functions outside the class, so implementations have more freedom here than with non-member functions. The cost is that the type of `&std::vector<int>::push_back` isn't guaranteed, which is why [[namespace.std#6]] also prohibits forming a pointer to member designating a non-static standard library member function. Virtual functions are excluded: their signatures decide whether derived classes can override them, so they must match the standard.

¶1 As with non-member functions, whether member functions are `inline` is unspecified.

### Hidden friends [hidden.friends]

¶1 If the standard declares a function as a friend in a class definition, that friend declaration must be the only declaration the implementation provides; there can be no other declaration of it at namespace scope. Note 2 explains that such a function is called a **hidden friend**: ordinary unqualified and qualified lookup can't find it, only ADL can ([[class.friend]]).

<div class="compare" markdown="1">

```cpp run ok
#include <compare>
int main() {
  auto r = std::strong_ordering::less;
  return r < 0;   // ADL finds the hidden friend
}
```

```cpp run error
#include <compare>
int main() {
  auto r = std::strong_ordering::less;
  return std::operator<(r, 0);
  // error: there is no operator< in std
}
```

</div>

The comparison operators of the comparison category types, the `iter_move` and `iter_swap` of iterators, and the `==` of many view iterators are hidden friends. They participate in overload resolution only when the arguments involve the class, so they can't be selected for unrelated types through implicit conversions, and they also reduce the number of candidate functions the compiler has to consider.

### constexpr functions [constexpr.functions]

¶1 The standard explicitly requires certain library functions to be `constexpr`, and an implementation shall not declare any other library function `constexpr`. If a header contains a non-defining declaration of a `constexpr` function, it must also provide the definition, otherwise the function couldn't be called during constant evaluation.

Why prohibit implementations from adding `constexpr`? Because it is observable. If an implementation declared `std::strlen` `constexpr`, `constexpr auto n = std::strlen("abc");` would compile on that implementation and fail on others, and code using a `requires` expression to detect whether a call can be constant-evaluated would get different answers on different implementations.

!!! impl "The state of implementations"
    This rule isn't strictly followed. GCC treats many `<cmath>` functions as built-ins and evaluates them directly in constant expressions, so `constexpr double x = std::sqrt(2.0);` has compiled with GCC for a long time. Lagging in the other direction exists too: C++23 already requires `std::abs` from `<cstdlib>` to be `constexpr`, yet with Clang 23 + libc++ `constexpr int y = std::abs(-1);` is still an error.

## Concurrent access [res.on.data.races]

### Library functions promise not to create data races

When two threads access the same object without synchronization and at least one access is a modification, there is a **data race**, and the program's behavior is undefined ([[intro.races]]). The following paragraphs guarantee that, as long as the program itself doesn't share objects, calling library functions won't create a data race out of nowhere.

¶2 A library function may access only objects that might be accessed by other threads if those objects are reachable, directly or indirectly, through its arguments (including `this`). ¶3 A library function may modify such objects only if they are reachable through its non-const arguments (including `this`). ¶4 Note 1 points out that this means implementations can't use internal objects with static storage duration without synchronization.

¶5 A library function accessing the elements of a container argument may do so only through the functions its specification requires it to call. ¶6 Operations on iterators obtained from member functions of a container or string may access the underlying container but may not modify it. ¶7 Implementations may share their own internal objects between threads, provided those objects aren't visible to users and are protected.

¶8 Unless otherwise specified, operations with user-visible effects must be performed in the current thread. ¶9 Note 3 adds that this allows implementations to parallelize operations when there are no visible side effects. The execution policies of the parallel algorithms are the "otherwise specified" here.

### Conclusions users can rely on

| Case | Safe? | Basis |
|---|---|---|
| Several threads call const member functions of the same object at the same time, such as `v.size()` or `m.find(k)` | Safe | ¶3 |
| Several threads each operate on different objects, even of the same type | Safe | ¶2, ¶4 |
| One thread modifies a container while another reads the same container | Data race | [[res.on.objects]] |
| Different threads modify different elements of the same `vector` | Safe, except for `vector<bool>` | [[container.requirements.dataraces]] |
| `std::rand`, `std::strtok`, `std::localtime` | May race | Their specifications say otherwise, allowing internal static state |

Containers have an additional rule: [[container.requirements.dataraces]] says that functions such as `begin`, `end`, `data`, `find` and `at` are treated as const for the purpose of determining data races, even when the non-const overload is called. So one thread calling `v.size()` while another calls the non-const `data()` on the same `v` isn't a race.

`shared_ptr` has a dedicated rule too ([[util.smartptr.shared]]): for the purpose of determining data races, member functions access only the `shared_ptr` object itself, and changes to the reference count don't count as modifications. So two threads each copying or destroying different `shared_ptr` objects that point to the same control block is safe; two threads assigning to the same `shared_ptr` object at the same time is still a data race, and `std::atomic<std::shared_ptr<T>>` should be used instead.

### Reentrancy [reentrancy]

¶1 Except where explicitly specified in the standard, it is implementation-defined which library functions can be recursively reentered.

¶2 During the execution of a non-static member function F on an object, if the program accesses that object through another path, i.e. through a glvalue not obtained from F's object parameter, and the access could conflict with an access F is permitted to perform, the behavior is undefined unless otherwise specified.

```cpp run ub
#include <functional>
std::function<void()> f;
int main() {
  f = [] { f = nullptr; };   // while f's operator() is executing,
  f();                       // f itself is modified through the global name f: UB
}
```

`operator()` reads `*this` while it executes, and the lambda modifies the same object through the global variable name `f`, destroying the very callable that is running. Similar problems include inserting elements into a `std::map` from within that map's comparator, and resetting a `shared_ptr` from within its own deleter.

## Properties of library classes

### Trivially copyable or not [library.class.props]

¶1 Unless explicitly stated otherwise, it is unspecified whether any class in the standard library is a trivially copyable class, a standard-layout class or an implicit-lifetime class ([[class.prop]]). So `memcpy` or `std::bit_cast` on standard library objects, or passing them between processes through shared memory, is portable only where the standard explicitly says so. The results with libc++:

| Type | Trivially copyable | Specified by the standard? |
|---|---|---|
| `std::pair<int, int>` | No | Not specified |
| `std::tuple<int, int>` | No | Not specified |
| `std::optional<int>` | Yes | Specified: when `T`'s copy, move and destruction are trivial, so are the corresponding operations of `optional<T>` |
| `std::array<int, 3>` | Yes | It is an aggregate, so its properties follow from the element |
| `std::span<int>`, `std::string_view` | Yes | Specified since C++23 ([[P2251R1]]) |
| `std::chrono::seconds` | Yes | Not specified |

`std::pair<int, int>` isn't trivially copyable because `pair` must support reference members: assignment of a `pair<int&, int&>` assigns to the referenced objects rather than rebinding. libc++ uses one user-provided `operator=` for all `pair`s, so it is non-trivial for every `pair`. Changing this would affect the ABI, for example how function arguments are passed.

### Friends and derivation [protection.within.classes] [derivation]

[protection.within.classes] ¶1 says it is unspecified whether any function or class in the standard library is a friend of another library class. Implementations may make library classes friends of each other, and user code can't rely on it.

[derivation] ¶1–¶2 allow implementations to derive any library class from a class with a name reserved to the implementation, and where a class is required to derive from some library class, it may do so indirectly through such intermediate base classes. For example, libstdc++'s `std::vector` derives from the internal `_Vector_base`. So when using `std::is_base_of` to probe relationships between library classes, you can rely only on those the standard states, such as `std::runtime_error` deriving from `std::exception`.

¶3 However the derivation is done, a base class specified as virtual must be virtual, and one not specified as virtual must not be. Types with distinct names must be distinct types unless the standard says otherwise; Note 1 points out that typedef names described as synonyms, such as `size_t`, are an exception.

¶4 Unless otherwise specified, types in the standard library are not `final` and can be derived from (`std::is_final_v<std::vector<int>>` is `false` with libc++). Being able to derive doesn't mean you should; for example, `std::vector`'s destructor isn't virtual.

## Exceptions [res.on.exception.handling]

¶1 When a library function reports a failure, it throws an exception of a type listed in its *Throws* paragraph, or of a derived type that a handler for that type would catch. ¶4 A function with no *Throws* paragraph but with a potentially-throwing exception specification may throw implementation-defined exceptions; footnote 147 explains that they may throw `bad_alloc` or a class derived from it to report allocation failure. Implementations should throw only standard exception classes or classes derived from them.

¶2 Functions from the C standard library don't throw exceptions unless they call a program-supplied function that throws. Footnote 146 points out that `qsort` and `bsearch` are such cases.

¶3 Destructors in the standard library don't throw; they all behave as if they had a non-throwing exception specification ([[except.spec]]).

¶5 An implementation may add a non-throwing exception specification to a non-virtual function. libc++ adds `noexcept` to `vector::operator[]`:

```cpp run impl
#include <vector>
std::vector<int> v;
// the standard doesn't declare vector::operator[] noexcept
static_assert(noexcept(v[0]));   // holds with libc++; not portable
int main() {}
```

So `noexcept(f())` for a library function the standard doesn't declare `noexcept` isn't necessarily `false`. This rule applies only to non-virtual functions: once a virtual function is `noexcept`, every function overriding it must be `noexcept` too ([[except.spec]]), so an implementation adding it on its own would make users' previously valid overriders ill-formed.

## Contract assertions [res.contract.assertions] {{c++26}}

¶1 Unless otherwise specified, an implementation may check the specified preconditions and postconditions of a library function with contract assertions ([[basic.contract]]), for example writing `pre(!empty())` on `std::vector::front()`. This is a permission, not a requirement: whether to check and which evaluation semantic to use are up to the implementation. Only hardened preconditions in a hardened implementation must be checked; see [[structure.specifications]].

## The state of moved-from objects [lib.types.movedfrom]

¶1 Objects of standard library types may be moved from. Unless otherwise specified, a moved-from object is placed in a **valid but unspecified state** ([[defns.valid]]): the object's invariants still hold and operations without preconditions can be called, but its value isn't known. ¶2 A standard library object may be move-assigned to itself, and the result is likewise a valid but unspecified state.

```cpp run ok
#include <string>
#include <utility>
#include <vector>
int main() {
  std::vector<int> a{1, 2, 3};
  std::vector<int> b = std::move(a);
  [[maybe_unused]] auto n = a.size(); // OK: value unknown
  // a.front();   // not allowed: precondition !empty(), and a's value is unknown
  a.clear();      // OK: a is now definitely empty
  a.push_back(4); // OK

  std::string s = "hello";
  std::string& r = s;
  s = std::move(r);  // self-move-assignment: not UB (¶2)
  s = "again";       // OK
  return a.size() == 1 && s == "again" ? 0 : 1;
}
```

Many types say otherwise and give stronger guarantees: `unique_ptr` and `shared_ptr` are empty after being moved from; a moved-from `optional` still has a value, which is itself in `T`'s moved-from state; `thread`, `unique_lock` and `promise` are no longer associated with anything after being moved from. After move construction of `string` and `vector`, the source object is empty in the major implementations, but the standard doesn't guarantee it.

## Error codes [value.error.codes]

¶1 Some library functions report errors through an `error_code`. For errors originating from the operating system, its `category()` returns `system_category()`; errors from other sources return an implementation-defined error category. Example 1 recommends that POSIX-based implementations make the values of `system_category()` the same as `errno`.

So when a `std::filesystem` operation fails, `ec.value()` on Linux and macOS is the value of `errno`, such as `ENOENT`. The portable way is to compare with `std::errc::no_such_file_or_directory`, which is an `error_condition`; the comparison maps between categories and doesn't depend on specific numeric values.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[conforming.overview] ¶1–¶2 are the table of contents of this subclause: they list which subclauses discuss the implementation's use of headers, macros, non-member functions, member functions, data race avoidance, access specifiers, class derivation, exceptions and contract assertions.

[res.on.macro.definitions] ¶1: the names and global function signatures described in [[contents]] are reserved to the implementation. ¶2: all object-like macros defined by the C standard library and described as expanding to integral constant expressions, such as `INT_MAX`, `CHAR_BIT`, `EOF` and `SIZE_MAX`, are usable in `#if` directives. This rules out implementing these macros with `sizeof` or enumeration constants.

[algorithm.stable] ¶1 specifies the meaning of "stable" in algorithm descriptions. For sorting algorithms (such as `stable_sort`), the relative order of equivalent elements is preserved; for remove and copy algorithms (such as `remove_if` and `copy_if`), the relative order of the remaining elements is preserved; for merge algorithms (such as `merge`), among equivalent elements those from the first range precede those from the second, each keeping its original order.

</details>

## Questions

!!! question "Question 1"
    Implementation A's `<algorithm>` includes `<string>`, and implementation B's doesn't. A program includes only `<algorithm>` and uses `std::string`. Is it a correct program on implementation A?

<details markdown="1">
<summary>Answer</summary>

No. [res.on.headers] ¶1 allows implementation A to include it like that, but the synopsis of `<algorithm>` doesn't say it includes `<string>`. [[using.headers#3]] requires the header declaring `std::string` to be included before `std::string` is used, with no diagnostic required on violation. Happening to compile on implementation A is the typical symptom of this kind of no-diagnostic-required error.
</details>

!!! question "Question 2"
    One thread calls `size()` on a `std::vector<int>` object while another thread calls the non-const `data()` on the same object. Is there a data race?

<details markdown="1">
<summary>Answer</summary>

No. Under [res.on.data.races] ¶3, the non-const `data()` is in principle allowed to modify the object; but [[container.requirements.dataraces]] ¶1 says that `data`, `begin`, `find` and similar functions are treated as const for the purpose of determining data races. Both calls only read, so they don't conflict. If `data()` were replaced by `push_back`, they would conflict, and by [[res.on.objects]] the behavior would be undefined.
</details>

## Summary

!!! summary "What you can rely on and what you can't"
    | Can rely on | Can't rely on |
    |---|---|
    | A header provides the declarations in its synopsis, including the stated inclusions | Any other transitive inclusion |
    | Valid calls always select the non-member overloads the standard specifies; non-member functions have no extra default arguments | Whether a function is inline; the set of signatures of a member function; whether you can take an address |
    | The library doesn't use ADL internally for non-operator functions, and does for operators | Whether library classes are friends of each other |
    | Functions specified as friends can be found only through ADL | |
    | Implementations don't add constexpr on their own | Implementations already provide all the required constexpr |
    | Concurrent const calls are safe; concurrency on different objects is safe | Whether the library executes in parallel internally (as long as there are no visible side effects) |
    | The specified virtual base relationships; types aren't final | Whether there are extra base classes with reserved names; whether a class is trivially copyable |
    | Only types in *Throws* or derived from them are thrown; destructors don't throw; C functions don't throw | The result of the `noexcept` operator for functions not declared noexcept |
    | Moved-from objects are valid, can be assigned, and operations without preconditions can be called | The value of a moved-from object |
