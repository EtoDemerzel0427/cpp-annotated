---
title: "Method of description: how to read library wording"
summary: "A library function's specification is a sequence of labeled elements, and labels such as Constraints, Mandates, Preconditions and Hardened preconditions each decide whether a violation removes the function from overload resolution, is a compile error, is undefined behavior, or terminates; how to read the code after Equivalent to; and how Cpp17 named requirements differ from library concepts."
updated: 2026-10-19
---

!!! tldr
    - The label a library function's condition is written under decides the consequence of violating it: *Constraints* removes the function from overload resolution, *Mandates* makes the program ill-formed, *Preconditions* is undefined behavior.
    - *Hardened preconditions* are always checked in a hardened implementation, and a violation terminates the program; in a non-hardened implementation they are still undefined behavior.
    - `requires` expressions and type traits can see *Constraints* but not *Mandates*.
    - The code after *Effects: Equivalent to* describes effects, not the means of implementation; the preconditions, exceptions and other specifications of each call in the code carry over with it.
    - An italic *Cpp17Xxx* is a written requirement given in a table, a monospaced `xxx` is a real C++ concept, and the two are not equivalent.

## One condition, three consequences

```cpp run ok
#include <algorithm>
#include <functional>
#include <tuple>
#include <type_traits>
#include <vector>

// 1. std::function's constructor: invocability is under Constraints
static_assert(!std::is_constructible_v<std::function<void()>, int>);

// 2. std::get<T>: "T occurs exactly once" is under Mandates
std::tuple<int, int> t;
static_assert(requires { std::get<int>(t); });   // the check says it can be called

// 3. std::lower_bound: "the range is partitioned" is under Preconditions
int f(std::vector<int>& v) {
  return *std::lower_bound(v.begin(), v.end(), 2);
}
int main() {}
```

All three library functions impose conditions on the call, but the consequences are completely different:

- `std::function<void()>` can't be constructed from `int`; the type trait truthfully reports `false`, with no error at all.
- Using `std::get<int>` on a `tuple<int, int>` is wrong, yet the `requires` expression reports that it can be called. When you actually write `std::get<int>(t)`, libc++ (with Clang 23) reports a static_assert failure: "type occurs more than once in type list".
- When `f` is given an unsorted `vector`, the compiler says nothing, and nothing is guaranteed about the result at run time.

The difference comes from which label of the function specification the condition is written under. The core language speaks in syntactic and semantic rules, while the library clauses give each function a list of **elements** with italic labels, and each kind of label has a fixed meaning. [description] is the legend for this notation, and Clauses 17–33 ([[support]] to [[exec]]) and Annex [[depr]] are all read according to it.

## Elements of a function specification [structure.specifications]

¶3 Descriptions of function semantics contain the following elements as appropriate; elements that don't apply are simply omitted (a function with no preconditions has no *Preconditions*). The first five are about what the call must satisfy; the rest are about what the implementation promises to do:

| ¶ | Element | Content | If not met |
|---|---|---|---|
| 3.1 | *Constraints* | Conditions for the function's participation in overload resolution | The function is not viable and silently drops out of the candidate set |
| 3.2 | *Mandates* | Conditions that, if not met, render the program ill-formed | {{ill-formed}}, diagnostic required |
| 3.3 | *Constant When* | Conditions for the call to be a constant subexpression | The call can't be evaluated at compile time |
| 3.4 | *Preconditions* | Conditions the function assumes to hold whenever it is called | {{ub}} |
| 3.5 | *Hardened preconditions* | As above, checked in a hardened implementation | Hardened implementation: termination; otherwise {{ub}} |
| 3.6 | *Effects* | Actions performed by the function | |
| 3.7 | *Synchronization* | Applicable synchronization operations | |
| 3.8 | *Postconditions* | Conditions established by the function | |
| 3.9 | *Result* | Meaning of a type name, or the type and value category of an expression | |
| 3.10 | *Returns* | The value returned | |
| 3.11 | *Throws* | Exceptions thrown and the conditions for throwing them | |
| 3.12 | *Complexity* | Time and space complexity (upper bounds) | |
| 3.13 | *Remarks* | Additional semantic constraints | |
| 3.14 | *Error conditions* | Errors reported through error codes | |

### *Constraints*: not met means out of overload resolution (¶3.1)

!!! std
    *Constraints*: the conditions for the function's participation in overload resolution.

¶3.1 [[g:constraints-element|*Constraints*]] are the conditions for the function to participate in overload resolution. Note 1 explains that when they aren't met, the function is silently non-viable: it simply disappears from the candidate set, which isn't an error. Example 1 points out that an implementation can express such a condition with a `requires` clause; implementations before C++20 used `enable_if`, with the same effect.

Because it isn't an error, this kind of condition can be detected. Type traits such as `is_constructible`, `is_invocable` and `is_convertible`, and `requires` expressions, can all see it and yield `false`; if there are other candidates, overload resolution simply picks another one.

```cpp run ok
#include <memory>
template<class T>
concept can_make_unique = requires { std::make_unique<T>(); };
static_assert( can_make_unique<int>);
static_assert(!can_make_unique<int[3]>);
int main() {}
```

The case of `make_unique<int[3]>()` is written differently. The standard declares a dedicated deleted overload for arrays of known bound, whose *Constraints* is "T is an array of known bound". This overload participates in overload resolution and is selected, and the call is then ill-formed because the function is deleted, so the `requires` expression yields `false` too. Example 2 in the next section describes exactly this technique.

### *Mandates*: not met means a compile error (¶3.2)

!!! std
    *Mandates*: the conditions that, if not met, render the program ill-formed.

¶3.2 When [[g:mandates-element|*Mandates*]] aren't met, the program is ill-formed and the compiler must diagnose it. Example 2 gives two ways to implement this:

1. a `static_assert` in the function body, which is the most common approach;
2. if the error should come only after overload resolution has selected the function, a constraint expression, with the function defined as deleted.

When implemented with `static_assert`, *Mandates* don't affect overload resolution. Type traits and `requires` expressions check only the declaration, while the `static_assert` is in the function body and fires only when the body is instantiated, which is outside the range where substitution failure can be handled silently ([[temp.deduct]]). So the `requires { std::get<int>(t); }` at the start yields `true`, and the error appears only on an actual call.

<div class="compare" markdown="1">

```cpp run ok
#include <tuple>
std::tuple<int, int> t;
// a requires expression can't see Mandates
static_assert(requires { std::get<int>(t); });
```

```cpp run error
#include <tuple>
std::tuple<int, int> t;
// error: Mandates not met, int occurs twice
int x = std::get<int>(t);
```

</div>

!!! tip "Why not make everything Constraints"
    *Constraints* suit dispatching between several overloads, for example choosing among the constructors of `optional<T>` according to whether `T` is constructible from `U` and whether the conversion is implicit. *Mandates* suit cases where the call itself is a mistake: if `get<int>` silently disappeared, the user would only see "no matching function", which is far less clear than "the type occurs more than once". Putting the condition into the signature also increases compile time and can trigger unwanted recursive constraint checks.

### *Preconditions*: a violation is undefined behavior (¶3.4)

!!! std
    *Preconditions*: conditions that the function assumes to hold whenever it is called; violation of any preconditions results in undefined behavior.

¶3.4 [[g:preconditions-element|*Preconditions*]] are conditions the caller is responsible for ensuring; the function doesn't have to check them. If any precondition is violated, the behavior is undefined. Example 3 mentions that an implementation can express some of them with contract assertions (such as `pre`, [[dcl.contract.func]]), and [[res.contract.assertions]] allows this too; but at the level of the standard, a violation is UB whether or not the implementation checks.

```cpp run ub
#include <algorithm>
#include <vector>
int main() {
  std::vector<int> v{3, 1, 2};   // not sorted
  // [lower.bound]: the range must be partitioned with respect to e < value
  auto it = std::lower_bound(v.begin(), v.end(), 2);  // UB
  return *it;
}
```

Binary search itself doesn't go out of bounds, so in practice this code always returns some position; in our tests it returns 2. But the standard places no requirements on the result, and the compiler may assume the precondition holds and optimize accordingly.

Preconditions usually involve run-time values: a pointer is non-null, an index is in range, a range is sorted. The compiler can't decide these conditions statically, so they can't be written as *Constraints* or *Mandates*, which involve only types and compile-time properties.

### *Hardened preconditions*: checked by hardened implementations (¶3.5){{c++26}}

¶3.5 [[g:hardened-precondition|*Hardened preconditions*]] are likewise conditions the function assumes to hold whenever it is called; the difference is that the consequence of a violation depends on whether the implementation is hardened. A **hardened implementation** is one whose standard library checks such conditions; whether an implementation is hardened is implementation-defined ([[intro.compliance#8]]), and in practice it is usually a compiler option.

- ¶3.5.1 In a hardened implementation, before any other observable side effects of the function, a contract assertion whose predicate is the hardened precondition is evaluated with a terminating semantic ([[basic.contract.eval]]). A terminating semantic means enforce or quick-enforce: when the check fails the program terminates and does not continue.
- ¶3.5.2 In a non-hardened implementation, violating a hardened precondition is undefined behavior.

Most conditions marked as hardened preconditions guard against out-of-bounds access, for example `a[n]` on a sequence container requires `n < a.size()`, `optional::operator*` requires `has_value()`, and `span::operator[]` requires the index to be in range. Out-of-bounds access is the main source of memory safety vulnerabilities, and a hardened implementation guarantees it can't happen silently.

```cpp run ub
#include <cstdio>
#include <vector>
int main(int argc, char**) {
  std::vector<int> v{1, 2, 3};
  if (argc > 1)
    std::printf("%d\n", v[3]);  // non-hardened implementation: UB; hardened: termination
}
```

Running this with libc++ (Clang 23) and one argument: in the default configuration nothing is checked and the out-of-bounds memory is read directly; with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` the process receives `SIGTRAP` (exit code 133); with `_LIBCPP_HARDENING_MODE_DEBUG` it first prints `libc++ Hardening assertion __n < size() failed` and then aborts.

A hardened implementation must also define a set of feature-test macros such as `__cpp_lib_hardened_vector` and `__cpp_lib_hardened_optional` ([[version.syn#3]]), which code can use to tell whether it is running on a hardened implementation. Hardening was introduced into C++26 by [[P3471R4]] and was designed together with contracts ([[P2900R14]]), so a violation is handled the same way as a user-written `pre` assertion.

### *Constant When*: whether the call can happen at compile time (¶3.3)

¶3.3 *Constant When* specifies the conditions for a call to be a constant subexpression ([[defns.const.subexpr]]). It is used for functions that are themselves `constexpr` but whose calls can't all be completed at compile time. For example, the specification of `std::bit_cast` says:

!!! std
    *Constant When*: Neither `To` nor `From` has constexpr-unknown representation.

That is, if the types involved contain parts whose bit pattern can't be determined at compile time, such as pointers, unions or reference members ([[expr.const]]), the call isn't a constant subexpression, and using it where a constant expression is required is ill-formed.

The difference from *Mandates* is that when *Constant When* isn't met, the call is still valid at run time; it just can't be evaluated at compile time. Another form is "*Constant When*: Preconditions are met", which means that violating a precondition during constant evaluation isn't UB but makes the expression not a constant expression, which the compiler must diagnose. This is consistent with the core language's design of disallowing UB during constant evaluation. *Constant When* is new wording after C++23.

### What the implementation promises (¶3.6–¶3.14)

¶3.6 *Effects* describes the actions performed by the function. The most common form is "*Effects*: Equivalent to" followed by some code; how to read it is explained in the next section.

¶3.7 *Synchronization* describes the synchronization operations the function involves ([[intro.multithread]]). For example, the *Synchronization* of `std::thread`'s constructor says that the completion of the constructor invocation synchronizes with the beginning of the invocation of the copy of `f`. Whether there is an ordering between library functions is determined by this element.

¶3.8 *Postconditions* describes conditions that are guaranteed to hold after the function returns; Example 4 points out that an implementation can express them with `post` assertions.

¶3.9 *Result* is used for type names or expressions: for a type name, it describes the named type; for an expression, it gives the type, and the value category follows from the type: an lvalue reference type means an lvalue, an rvalue reference type means an xvalue, and otherwise a prvalue ([[topics/value-categories]]). It appears mainly in requirements tables; for example, in [[allocator.requirements]] the *Result* of `a.allocate(n)` is `XX::pointer`.

¶3.10 *Returns* describes the value returned. ¶3.11 *Throws* describes the exceptions thrown and the conditions for throwing them. The exact meanings of common phrasings are:

| Phrasing | Meaning |
|---|---|
| *Throws*: Nothing. | Throws no exceptions, but this isn't the same as being declared `noexcept` (see Common misconceptions below) |
| *Throws*: `out_of_range` if `pos > size()`. | Throws `out_of_range` or a class derived from it ([[res.on.exception.handling#1]]) |
| *Throws*: Any exception thrown by the constructor of `T`. | Whatever `T`'s constructor throws is passed through |
| No *Throws*, and the function isn't `noexcept` | May throw implementation-defined exceptions ([[res.on.exception.handling#4]]), typically `bad_alloc` |

¶3.12 *Complexity* gives the time or space complexity. ¶7 says these are all upper bounds, so implementations that do better also conform; ¶6 says that a formula yielding a negative number of operations means zero operations, so phrasings like "at most `N - 1` comparisons" need no special case for `N == 0`. The standard counts operations such as comparisons, predicate invocations and assignments, not machine instructions or time. For example, `std::lower_bound` performs at most log₂(last − first) + O(1) comparisons, but for non-random-access iterators the number of iterator moves can be linear.

¶3.13 *Remarks* holds additional semantic constraints. Common ones are: the exact condition of an exception specification (corresponding to `noexcept(see below)` in the synopsis), the condition of `explicit(see below)`, when a constructor is trivial or `constexpr`, and a few old-style "This function shall not participate in overload resolution unless …", which means the same as *Constraints*.

¶3.14 *Error conditions* lists the errors the function reports through error codes. ¶8 adds that these conditions are given as constants of `enum class errc` ([[syserr]]). For example, the error conditions of `std::mutex::lock()` include `resource_deadlock_would_occur` and `operation_not_permitted`.

## How to read Equivalent to (¶4)

The most common sentence in library specifications is "*Effects*: Equivalent to" followed by some code. Take [utility.exchange] as an example:

```cpp
template<class T, class U = T>
  constexpr T exchange(T& obj, U&& new_val) noexcept(see below);
// Effects: Equivalent to:
//   T old_val = std::move(obj);
//   obj = std::forward<U>(new_val);
//   return old_val;
// Remarks: The exception specification is equivalent to:
//   is_nothrow_move_constructible_v<T> && is_nothrow_assignable_v<T&, U>
```

¶4 says the semantics of a function F are determined in this order:

1. F's own *Constraints* and *Mandates* are applied first.
2. The semantics of the code sequence are determined by all the elements (*Constraints*, *Mandates*, *Preconditions*, *Effects*, *Throws*, *Complexity* and so on) of each function call in it. The specifications of the called functions carry over in full.
3. The return value is determined by F's *Returns*; if F has no *Returns*, by the `return` statements in the code.
4. If F itself has *Throws*, *Postconditions* or *Complexity*, F's own element applies, overriding the elements of the same name of the calls in the code.

Applying these to `exchange`: its preconditions and possible exceptions are those of `T`'s move construction and of assigning from `U` to `T&`; it has no *Throws* of its own, so nothing is overridden; the return value is determined by `return old_val;`.

[[structure.requirements#7]] says that semantics given as code specify only equivalence, not the means of implementation. Still, the way the code is written has consequences of its own:

- Copies, moves and temporaries written in the code are part of the semantics. If the equivalent code says `return T(x);`, that implies a requirement on `T`'s copy constructor.
- Unqualified names in the code are interpreted by unqualified lookup at the point of declaration, without argument-dependent lookup (ADL), except for a few names such as `swap` ([[contents#3]]). So `move` in the code is `std::move`.
- "Equivalent to: `return f(args...);`" doesn't mean F has the same `noexcept` as `f(args...)`; the exception specification is given by the synopsis and *Remarks*.

There are two related phrasings. "As if" is looser than "equivalent to"; it usually comes with explanatory code describing the effects and doesn't carry over all the elements precisely. **Expression-equivalent** ([[defns.expression.equivalent]]) is stronger: the two expressions have the same effects, either both are potentially-throwing or neither is, and either both are constant subexpressions or neither is. Customization point objects and range adaptors ([[conventions]]) use this phrasing heavily.

!!! lawyer "UB in Equivalent to code counts against F"
    If F's *Effects* are equivalent to some code and the precondition of a call in that code is violated, calling F violates a precondition, even if F itself has no *Preconditions* element.

## Requirements on user types [structure.requirements]

A function specification governs a single call. The library also has another kind of requirement, on types users write: putting your own type into `std::vector<T>`, passing a comparator to `std::sort`, deriving from `std::streambuf`, or writing an iterator to hand to standard algorithms all require these types to meet conditions set by the library.

¶1 Such requirements are what Requirements subclauses contain; they constrain programs that extend the standard library. Extensions are usually one of three kinds: template arguments (¶1.1), derived classes (¶1.2), and containers, iterators and algorithms that meet an interface convention or model a concept (¶1.3). The consequences of violations are in [[res.on.functions#2.3]] (UB) and [[res.on.requirements]].

### Requirements are on expressions, not members (¶3–¶4)

¶3 Interface requirements are stated as generally as possible. Instead of saying that class `X` has to define a member function `operator++()`, the standard says that for any object `x` of type `X`, `++x` is defined. So whether an operator is a member is unspecified.

For users, an iterator's `++it` can be implemented as a member function, a non-member function, a hidden friend or an inherited member. For the library implementation, it can only use your type in the form of expressions, writing `++it` and never `it.operator++()`.

¶4 Each such group of expression requirements corresponds either to a named concept or to a table listing the valid expressions and their semantics. Generic algorithms ([[algorithms]]) are described in terms of valid expressions on their template parameters.

### *Cpp17Xxx* and library concepts (¶5)

¶5 Library specifications use typography to distinguish two kinds of named requirements:

| Notation | What it refers to | Examples |
|---|---|---|
| Italic, starting with *Cpp17* | Expression requirements given in tables, possibly with additional prose ([[g:cpp17-named-requirement]]); the compiler knows nothing of them | *Cpp17Destructible* ([[utility.arg.requirements]]), *Cpp17InputIterator* |
| Monospaced | Library concepts, defined with `concept` ([[temp]]), possibly with semantic requirements in prose | `destructible`, `input_iterator` |

When C++20 introduced the concepts library, many old named requirements shared names with new concepts but meant something different, so the old table-style requirements all got the *Cpp17* prefix. The two are not equivalent. For example, *Cpp17InputIterator* requires the nested types in `iterator_traits` to be complete and requires equality comparison, while the `input_iterator` concept requires neither copyability nor equality comparison. An iterator can model `std::input_iterator` without meeting *Cpp17InputIterator*, and the converse is also possible.

### Required operations need not be defined for all values (¶8)

¶8 Required operations of a concept need not be total functions: some arguments may make the required semantics fail to hold. The standard's example is that the `<` required by `totally_ordered` doesn't meet the semantic requirements of that concept on NaN, but this doesn't affect whether the type models the concept.

If `double` didn't model `totally_ordered` because NaN exists, `std::ranges::sort` couldn't be used on `double`. What ¶8 means is that it is the type that models the concept; whether particular values fall within the range where the required operations are meaningful is a condition each call must satisfy.

```cpp run ok
#include <algorithm>
#include <concepts>
#include <vector>
static_assert(std::totally_ordered<double>);    // holds at the type level
int main() {
  std::vector<double> v{3.0, 1.0, 2.0};
  std::ranges::sort(v);    // OK: no NaN
  return v.front() == 1.0 ? 0 : 1;
}
```

If `v` contained NaN, `<` would no longer be a strict weak ordering, this call to `sort` would violate its semantic requirements, and the behavior would be undefined. But that is a problem with this one call, not with the type `double`.

### Concepts in constraints carry their semantic requirements (¶9)

¶9 A declaration may impose requirements through its associated constraints ([[temp.constr.decl]]). When a constraint refers to a concept, the semantic requirements of that concept are also imposed on uses of the declaration.

So when a library function template is written `template<std::regular T>`, it doesn't just mean that the compiler checks that `regular<T>` is **satisfied** (holds syntactically); it also requires `T` to **model** `regular`, that is, to meet all the semantic requirements described in prose, such as `==` being an equivalence relation and two objects being equal after a copy. The compiler can only check the former; if the latter doesn't hold, the program is ill-formed, no diagnostic required ([[res.on.requirements#3]]).

## Required and default behavior of replacement functions (¶5)

¶5 For functions a program may replace (such as the global `operator new`) and handler functions (such as `new_handler`), [[support]] specifies two kinds of behavior separately:

- **default behavior**: what the definition supplied by the implementation does;
- **required behavior**: the semantics any definition must have, whether supplied by the implementation or by the program.

Where no distinction is made explicitly, the description is of the required behavior. For example, the required behavior of the global `operator new(size_t)` is to return a non-null pointer to suitably aligned storage of at least `size` bytes, or else throw `bad_alloc`. Its default behavior is more specific: it attempts to allocate in a loop, and on failure throws `bad_alloc` if the current new_handler is null, and otherwise calls it and tries again. A replacement only needs to meet the required behavior; otherwise it is UB ([[res.on.functions#2.1]]). See [[constraints]] for details.

## Implementation view

The three major standard libraries implement these elements in broadly similar ways:

| Element | libc++ | libstdc++ | MSVC STL |
|---|---|---|---|
| *Constraints* | `requires`, `enable_if` in older modes | `requires` / `enable_if` / `_Require<...>` | `enable_if_t` / `requires` |
| *Mandates* | `static_assert` | `static_assert` | `static_assert` |
| *Preconditions* and hardening checks | The `_LIBCPP_ASSERT_*` family of macros, with `_LIBCPP_HARDENING_MODE` (none / fast / extensive / debug) deciding which are enabled | `__glibcxx_assert`, enabled by `_GLIBCXX_ASSERTIONS` | `_STL_VERIFY` and others, controlled by switches such as `_ITERATOR_DEBUG_LEVEL` |

libc++'s check macros are divided into categories (`_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS`, `_LIBCPP_ASSERT_NON_NULL` and so on), and fast mode enables only the security-critical, constant-time checks. Here is `vector::operator[]` in the libc++ we tested:

```cpp
reference operator[](size_type __n) _NOEXCEPT {
  _LIBCPP_ASSERT_VALID_ELEMENT_ACCESS(__n < size(), "vector[] index out of bounds");
  return this->__layout_.__begin_ptr()[__n];
}
```

The standard's `vector::operator[]` isn't `noexcept`; libc++ adds it under the permission of [[res.on.exception.handling#5]]. This doesn't get in the way of hardening checks, because a failed check traps or aborts rather than throwing. libc++ also provides `_LIBCPP_ASSERTION_SEMANTIC`, with values ignore / observe / quick-enforce / enforce, corresponding one to one to the four evaluation semantics of contracts.

## History

!!! history
    - In C++17 and earlier, function specifications had a *Requires:* element whose meaning wasn't consistent: sometimes it meant a violation was UB, sometimes that a violation was ill-formed, and sometimes it was understood as "doesn't participate in overload resolution if not met". The last had its own fixed phrasing, written under *Remarks*: "This function shall not participate in overload resolution unless …".
    - In C++20, [[P0788R3]] split *Requires:* into the well-defined *Constraints:*, *Mandates:* and *Expects:* (preconditions), and introduced *Ensures:*; a series of later papers then rewrote all the library clauses one by one. Before C++20 was finalized, *Expects:* and *Ensures:* were renamed *Preconditions:* and *Postconditions:*. Around the same time, the old table-style named requirements got the *Cpp17* prefix.
    - In C++26, [[P3471R4]] introduced standard library hardening and *Hardened preconditions*; [[P2900R14]] introduced contracts, giving Example 3 of ¶3.4 and ¶3.5.1 a basis in the language. *Constant When* is new wording after C++23.

## Common misconceptions

!!! pitfall "Thinking Preconditions are checked"
    Violating *Preconditions* is UB, and the standard never requires a check. Calling `front()` on an empty container, or `binary_search` on an unsorted range, can look perfectly fine on a non-hardened implementation. Only *Hardened preconditions* are guaranteed to be checked, and only in a hardened implementation.

!!! pitfall "Detecting Mandates with a requires expression"
    `requires { std::get<T>(t); }` and `std::is_invocable_v<...>` can only detect *Constraints*. Relying on them to decide whether *Mandates* are met gives false positives, followed by a compile error on the actual call.

!!! pitfall "*Throws*: Nothing equals noexcept"
    *Throws*: Nothing is a behavioral promise. If a function has preconditions, the standard usually deliberately doesn't declare it `noexcept` (a convention often called the Lakos rule), so that a debugging implementation can throw an exception when a precondition is violated, which helps testing. So the result of `noexcept(v[0])` varies by implementation: with libc++ it is `true`, because libc++ strengthens the exception specification. Portable code shouldn't rely on it.

!!! pitfall "Treating Complexity as a performance guarantee"
    *Complexity* is an upper bound, and it counts only specific operations; it doesn't constrain the number of memory allocations or cache behavior. `std::unordered_map::find` is constant on average and linear in the worst case, and both are written in its *Complexity*.

## Questions

!!! question "Question 1"
    The converting constructor of `std::optional<T>`, `template<class U = T> constexpr explicit(see below) optional(U&& v);`, puts conditions such as `is_constructible_v<T, U>` under *Constraints*. If they were under *Mandates* instead, what would `std::is_convertible_v<int, std::optional<std::string>>` be? What would the effect be on overload resolution?

<details markdown="1">
<summary>Answer</summary>

Under *Constraints*, `std::string` can't be constructed from `int`, so this constructor doesn't participate in overload resolution, and `is_convertible_v<int, optional<string>>` is `false`.

With *Mandates* (a `static_assert` in the function body), the constructor always participates in overload resolution, and `is_convertible_v`, which looks only at the declaration, would be `true`; the error would appear during instantiation only when you write `std::optional<std::string> o = 42;`. Overload resolution is affected too: with both `f(std::optional<std::string>)` and `f(std::optional<int>)`, `f(42)` can currently only choose the latter; after the change both are viable user-defined conversions and the call becomes ambiguous. This is exactly why ¶3.1 and ¶3.2 distinguish the two elements.
</details>

!!! question "Question 2"
    On a non-hardened implementation, what is the behavior of `std::optional<int> o; int x = *o;`? On a hardened implementation? What if the contract-violation handler simply returns?

<details markdown="1">
<summary>Answer</summary>

The hardened precondition of `optional::operator*` is that `has_value()` is `true` ([[optional.observe]]).

On a non-hardened implementation, by ¶3.5.2, the behavior is undefined. On a hardened implementation, by ¶3.5.1, `has_value()` is checked with a terminating semantic before any other side effects; the result is false, and a contract violation occurs. Under the enforce semantic the violation handler is called first, and if it returns normally the program still terminates in an implementation-defined fashion; under the quick-enforce semantic the handler isn't called and the program terminates immediately ([[basic.contract.eval]]). Either way, execution never continues to the dereference, and a handler that simply returns doesn't help.
</details>

!!! question "Question 3"
    What is the difference between "*Effects*: Equivalent to: `return std::invoke(f, args...);`" and "a call to F is expression-equivalent to `std::invoke(f, args...)`"?

<details markdown="1">
<summary>Answer</summary>

The former carries over effects, preconditions, return value, exceptions and so on according to ¶4, but doesn't guarantee that F has the same `noexcept` as `invoke`, nor that both are or both aren't constant subexpressions; those depend on F's own synopsis and *Remarks*. The `return` statement itself also introduces an initialization of the return value.

The latter is expression equivalence ([[defns.expression.equivalent]]): same effects, same exception specification, and the same answer to whether it can be evaluated at compile time. It is the stronger guarantee: a probe such as `noexcept(F(args...))` gives exactly the same result as for `invoke`.
</details>

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[description.general] ¶1: [description] describes the conventions used to specify the standard library; [structure] describes the structure of each library clause, and [[conventions]] the other editorial conventions.

[structure.elements] ¶1: each library clause contains, as appropriate, a summary, requirements, detailed specifications, and references to the C standard library; parts that don't apply are omitted. Taking [[containers]] as an example, [containers.general] is the summary, [container.requirements] has the requirements tables shared by all containers, and [sequences], [associative] and so on are the detailed specifications of each container.

[structure.summary] ¶1–¶2: the summary introduces the first-level subclauses of the category; each subclause also has a summary listing the headers it specifies and the entities each header provides, i.e. the familiar header synopsis (such as [utility.syn]). The contents include macros, values, types and alias templates, classes and class templates, functions and function templates, objects and variable templates, and concepts. The declarations in a synopsis are normative ([[contents#1]], [[res.on.headers#1]]), including their `constexpr`, `noexcept` and `explicit`; an implementation may strengthen `noexcept` ([[res.on.exception.handling#5]]) but may not add `constexpr` on its own ([[constexpr.functions]]). The meaning of comments such as `// freestanding` and `// exposition only` is covered in [[conventions]].

[structure.requirements] ¶2: the string and iostream components use the class template `char_traits` to express requirements on character types explicitly. ¶6: requirements on template arguments are sometimes referenced by name; see [[type.descriptions]]. ¶7: semantic requirements given as C++ code specify only equivalence; a footnote adds that sometimes the code given is plainly the optimal implementation.

[structure.specifications] ¶1: each detailed specification contains the name and a brief description, a synopsis, restrictions on template arguments, class invariants, and the semantics of functions. ¶2: class member functions are described in the order constructors and destructor, copying, moving and assignment, comparison operators, modifiers, observers, and non-member functions, which is why [optional.ctor] comes before [optional.assign].

[structure.see.also] ¶1: paragraphs labeled "See also" point to relevant parts of other standards ([[intro.refs]]), mostly the C standard, for example "See also: ISO/IEC 9899:2024, 7.26" after `<cstring>`. The detailed rules are in [[library.c]].

</details>
