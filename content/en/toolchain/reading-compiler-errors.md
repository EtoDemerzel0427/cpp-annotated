---
title: Reading compiler errors
summary: "What a Clang diagnostic is made of, how to read candidate lists and instantiation chains, which language rule each of a dozen or so of the most common and most puzzling compile and link errors corresponds to and how to fix it, and the compiler options that control diagnostic output."
group: Debugging and diagnostics
tags: toolchain, diagnostics, compile errors, link errors, overload resolution, templates, concepts
updated: 2026-10-19
---

!!! tldr
    - A diagnostic consists of one `error` or `warning` followed by some `note`s. A note isn't a new problem; it explains the error before it: why a candidate isn't viable, or which template instantiation the error came out of.
    - For an error reported deep inside a standard library header, first look down for the first `in instantiation of ... requested here` located in your own file; that line is the call you wrote. Then look at the `static_assert` message and the reason after `substitution failure`, which usually say directly what is really missing.
    - Fix only the first error, then recompile. Later errors are often knock-on effects of the first.
    - The linker's `Undefined symbols` and `duplicate symbol` correspond to ODR rules that require no diagnostic. To read them, compare the reported function signature character by character with the signature you defined, using `llvm-nm` and `c++filt` to see the real symbol names when needed.
    - `-ferror-limit`, `-ftemplate-backtrace-limit` and `-fdiagnostics-show-template-tree` control how much is output and in what form; when you can't make sense of it, compiling again with a different compiler (Compiler Explorer) often gives you a different, more direct wording.

The standard's requirement for compiler errors is a single sentence: if a program violates a **diagnosable rule** ([[g:diagnosable-rule|diagnosable rule]], i.e. a syntactic or semantic rule not marked as requiring no diagnostic and not undefined behavior), the implementation must issue at least one diagnostic message ([[intro.compliance.general#2.3]]). What the message says, how many there are and how much explanation comes with them are entirely up to the implementation. So reading error messages means reading a particular compiler's output format, not reading the standard.

Still, behind every message there is a specific rule. Recognize the rule, and you know where to make the fix.

!!! note "Test setup"
    All output below comes from Homebrew Clang 23.1.3 and libc++ on our test machine (Apple M2 Pro, macOS), with the command `clang++ -std=c++2c -Wall -Wextra -pedantic`, and the system linker `ld-1266.8` selected with `--ld-path=/usr/bin/ld`. The long libc++ header path `/opt/homebrew/Cellar/llvm/23.1.3_2/bin/../include/c++/v1/` is shortened to `.../c++/v1/`; the rest of the text is unchanged, and the middle parts of longer outputs are cut and marked. Our test machine has no GCC (`/usr/bin/g++` is actually Apple clang 21), MSVC, GNU ld or lld, so their output isn't quoted.

## The structure of a diagnostic

```cpp title="nomatch.cpp" run error
#include <string>
void greet(const std::string& name, int times);
void greet(const char* name);
int main() {
  greet(42);
}
```

```text
nomatch.cpp:5:3: error: no matching function for call to 'greet'
    5 |   greet(42);
      |   ^~~~~
nomatch.cpp:3:6: note: candidate function not viable: no known conversion from 'int' to 'const char *' for 1st argument
    3 | void greet(const char* name);
      |      ^     ~~~~~~~~~~~~~~~~
nomatch.cpp:2:6: note: candidate function not viable: requires 2 arguments, but 1 was provided
    2 | void greet(const std::string& name, int times);
      |      ^     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1 error generated.
```

Each one starts with `file:line:column: level: message`, followed by the source line and markers. `^` points at the location of the diagnostic, and `~~~` marks related ranges. In the example, the `error` points at the call, and the two `note`s point at the declarations of the two candidates, with `~~~` marking the problematic parameters.

| Level | Meaning |
|---|---|
| `error` | The program is ill-formed, or the implementation can't continue; no object file is produced |
| `warning` | The program is well-formed (or the compiler isn't sure), but likely not what you meant; the `[-Wxxx]` at the end is the option controlling it |
| `note` | An explanation attached to the preceding `error`/`warning`, not a problem in itself |
| `fatal error` | Compilation stops immediately, for example when a header can't be found or the error limit is reached |

An error may also end with `[-Wxxx]`, such as `[-Wc++11-narrowing]` below. That means the error is controlled by a warning option and can be downgraded or even turned off.

### Candidate lists

The notes after `no matching function` are a record of overload resolution. Overload resolution first collects the **candidate functions** ([[g:candidate-function|candidate function]]) and then filters out the **viable functions** ([[g:viable-function|viable function]]): the number of parameters must fit ([[over.match.viable#2]]), constraints must be satisfied ([[over.match.viable#3]]), and every argument must be implicitly convertible to the corresponding parameter ([[over.match.viable#4]]). Clang writes a `candidate ... not viable` for each eliminated candidate, saying which step it failed at:

| What the note says | Which step it failed |
|---|---|
| `requires 2 arguments, but 1 was provided` | Wrong number, [[over.match.viable#2]] |
| `no known conversion from 'X' to 'Y' for Nth argument` | No implicit conversion sequence for the Nth argument, [[over.match.viable#4]] |
| `expects an lvalue for Nth argument` | An rvalue passed to a non-const lvalue reference parameter, see below |
| `candidate template ignored: could not match ...` | Template argument deduction failed |
| `candidate template ignored: substitution failure [...]: reason` | Deduction succeeded, substitution failed (SFINAE) |
| `candidate template ignored: constraints not satisfied` | Constraints not satisfied, followed by a `because` chain |
| `explicit constructor is not a candidate` | Copy-initialization doesn't consider explicit constructors |

If there is no viable function at all, it is `no matching function`; if there are several and none is best, it is `ambiguous` ([[over.match.best.general#3]]). The rules themselves are in [[topics/overload-resolution-walkthrough]].

### Instantiation chains

When an error occurs inside a template, Clang first reports the line that actually failed (often in a library header), then uses a series of notes to explain how the template got instantiated there. Below is the first error from calling `std::sort` on a `std::list` (4 errors and 114 lines of output in total):

```cpp title="sortlist.cpp" run
#include <algorithm>
#include <list>
int main() {
  std::list<int> xs{3, 1, 2};
  std::sort(xs.begin(), xs.end());
}
```

```text
In file included from sortlist.cpp:1:
In file included from .../c++/v1/algorithm:1928:
.../c++/v1/__algorithm/make_heap.h:37:31: error: invalid operands to binary expression ('std::__list_iterator<int, void *>' and 'std::__list_iterator<int, void *>')
   37 |   const __diff_t __n = __last - __first;
      |                        ~~~~~~ ^ ~~~~~~~
.../c++/v1/__algorithm/partial_sort.h:41:8: note: in instantiation of function template specialization 'std::__make_heap<std::_ClassicAlgPolicy, std::__less<void, void> &, std::__list_iterator<int, void *>>' requested here
.../c++/v1/__algorithm/partial_sort.h:65:12: note: in instantiation of function template specialization 'std::__partial_sort_impl<...>' requested here
.../c++/v1/__algorithm/sort.h:936:10: note: in instantiation of function template specialization 'std::__partial_sort<...>' requested here
.../c++/v1/__algorithm/sort.h:947:8: note: in instantiation of function template specialization 'std::__sort_impl<...>' requested here
.../c++/v1/__algorithm/sort.h:953:8: note: in instantiation of function template specialization 'std::sort<std::__list_iterator<int, void *>, std::__less<void, void>>' requested here
sortlist.cpp:5:8: note: in instantiation of function template specialization 'std::sort<std::__list_iterator<int, void *>>' requested here
    5 |   std::sort(xs.begin(), xs.end());
      |        ^
.../c++/v1/__iterator/reverse_iterator.h:279:36: note: candidate template ignored: could not match 'reverse_iterator' against 'std::__list_iterator'
.../c++/v1/__iterator/move_iterator.h:306:36: note: candidate template ignored: could not match 'move_iterator' against 'std::__list_iterator'
```

(The source lines and template arguments of some notes in the middle have been removed.)

Read it in this order:

1. The leading `In file included from` lines only say how the file containing the error was included, and can be skipped.
2. The `error` line describes the symptom: two `__list_iterator`s can't be subtracted.
3. The `in instantiation of` notes go from innermost outward; **the last one located in your own file** is the line of code that triggered the instantiation (`sortlist.cpp:5:8`). The `__make_heap` and `__partial_sort_impl` in between are library implementation details you needn't understand.
4. The `candidate template ignored` notes after the instantiation chain belong to the same error; they list why other overloads of `operator-` don't apply. Both here are irrelevant to the problem.

This chain corresponds to **implicit instantiation** in the standard ([[g:implicit-instantiation|implicit instantiation]], [[temp.inst#5]]): a function template specialization's definition is instantiated when it is used, and the instantiation in turn uses other templates. Each note is one level of such use. By default Clang shows at most 10 levels, folding the rest into `(skipping N contexts in backtrace; use -ftemplate-backtrace-limit=0 to see all)`.

An experiment with a class template recursing 30 levels deep printed 10 `in instantiation of` notes and one `skipping 20 contexts`.

GCC expresses the same chain with different wording. There is no GCC on our test machine; when you need to compare, give the same code to both compilers on Compiler Explorer (the godbolt button at the top right of code blocks opens Clang and GCC side by side by default).

## Template errors deep inside the standard library

What these errors have in common: you violated a requirement the standard library places on template arguments, but that requirement isn't written as a constraint that can be checked at the call site, so the error only surfaces when the library implementation uses some operation internally.

The standard doesn't require a diagnostic for all such violations. For example, `std::sort`'s template parameter is named `RandomAccessIterator`, and [[algorithms.requirements#4.7]] only says the argument shall meet the *Cpp17RandomAccessIterator* requirements. So the two examples below carry no verdict marker; in practice implementations do report errors at instantiation.

### `std::sort` on a `std::list`

The output in the previous section already shows the problem: `std::sort` subtracts iterators, and `std::list`'s iterators are bidirectional iterators that don't support `-`. The fix is to use `list`'s own member function `xs.sort()`, or to copy into a `vector` first.

Compare C++20's `std::ranges::sort`. Its requirements are written as concept constraints, so the error stops at the call site, with one error and one `because` chain:

```cpp title="rsort.cpp" run error
#include <algorithm>
#include <list>
int main() {
  std::list<int> xs{3, 1, 2};
  std::ranges::sort(xs);
}
```

```text
rsort.cpp:5:3: error: no matching function for call to object of type 'const __sort'
    5 |   std::ranges::sort(xs);
      |   ^~~~~~~~~~~~~~~~~
.../c++/v1/__algorithm/ranges_sort.h:64:3: note: candidate template ignored: constraints not satisfied [with _Range = std::list<int> &, _Comp = ranges::less, _Proj = identity]
.../c++/v1/__algorithm/ranges_sort.h:61:13: note: because 'std::list<int> &' does not satisfy 'random_access_range'
.../c++/v1/__ranges/concepts.h:116:59: note: because 'iterator_t<std::list<int, std::allocator<int>> &>' (aka '__list_iterator<int, void *>') does not satisfy 'random_access_iterator'
.../c++/v1/__iterator/concepts.h:218:36: note: because 'derived_from<_ITER_CONCEPT<std::__list_iterator<int, void *> >, random_access_iterator_tag>' evaluated to false
.../c++/v1/__concepts/derived_from.h:27:24: note: because 'is_base_of_v<std::random_access_iterator_tag, std::bidirectional_iterator_tag>' evaluated to false
.../c++/v1/__algorithm/ranges_sort.h:57:3: note: candidate function template not viable: requires at least 2 arguments, but 1 was provided
1 error generated.
```

(Source lines removed.) `[with ...]` gives the deduced template arguments; `(aka ...)` after an alias gives the real type it stands for.

### A `std::map` key without `operator<`

```cpp title="mapkey.cpp" run
#include <map>
struct Point { int x, y; };
int main() {
  std::map<Point, int> m;
  m[{1, 2}] = 3;
}
```

```text
.../c++/v1/__utility/lazy_synth_three_way_comparator.h:45:21: error: no matching function for call to object of type 'const std::less<void>'
   45 |     bool __result = __comp_(__lhs_, __rhs_);
      |                     ^~~~~~~
.../c++/v1/__tree:1962:20: note: in instantiation of member function 'std::__lazy_compare_result<std::less<void>, Point, Point>::__less' requested here
(3 notes in between omitted)
mapkey.cpp:5:4: note: in instantiation of member function 'std::map<Point, int>::operator[]' requested here
    5 |   m[{1, 2}] = 3;
      |    ^
.../c++/v1/__functional/operations.h:374:60: note: candidate template ignored: substitution failure [with _T1 = const Point &, _T2 = const Point &]: invalid operands to binary expression ('const Point' and 'const Point')
```

The error line mentions `std::less<void>`, whereas what you wrote is `std::less<Point>` (`map`'s default comparator). This is a substitution internal to libc++ and needn't be chased when reading. The real reason follows `substitution failure` in the last note: there is no `<` between two `const Point`s.

`map` requires its comparator to induce a strict weak ordering ([[associative.reqmts.general]]). The fix is to give `Point` a comparison operator, for example `auto operator<=>(const Point&) const = default;`, or to pass `map` a custom comparator.

### A `std::unordered_map` key without a hash

```cpp title="umap.cpp" run error
#include <unordered_map>
struct Point {
  int x, y;
  bool operator==(const Point&) const = default;
};
int main() {
  std::unordered_map<Point, int> m;
  m[{1, 2}] = 3;
}
```

```text
.../c++/v1/unordered_map:653:9: error: call to implicitly-deleted default constructor of 'std::hash<Point>'
umap.cpp:7:34: note: in instantiation of member function 'std::unordered_map<Point, int>::unordered_map' requested here
.../c++/v1/__functional/hash.h:438:15: note: default constructor of 'hash<Point>' is implicitly deleted because base class '__hash_impl<Point>' has a deleted default constructor
.../c++/v1/__hash_table:592:17: error: static assertion failed due to requirement 'std::integral_constant<bool, false>::value': the specified hash does not meet the Hash requirements
.../c++/v1/unordered_map:658:75: error: type 'const std::hash<Point>' does not provide a call operator
(5 errors and 79 lines in total; only the first line and key notes of each error are kept here)
```

The first error says `std::hash<Point>` can't be default-constructed, which at first glance has nothing to do with hashing. The reason is that the standard says when no `hash` specialization is provided for a type, `hash<Key>` is a **disabled specialization**: it exists, but isn't default constructible, copyable or movable, and isn't a function object type ([[unord.hash#4]]). The note in that paragraph says using it as a hash function is ill-formed.

The `static_assert` message in the second error is the direct explanation. Library authors use `static_assert` to translate requirements into plain language, and such messages are worth looking for first. The fix is to specialize `std::hash` for `Point`:

```cpp run ok
#include <cstddef>
#include <functional>
#include <unordered_map>
struct Point {
  int x, y;
  bool operator==(const Point&) const = default;
};
template <>
struct std::hash<Point> {
  std::size_t operator()(const Point& p) const noexcept {
    std::size_t h = std::hash<int>{}(p.x);
    return h ^ (std::hash<int>{}(p.y) + 0x9e3779b9 + (h << 6) + (h >> 2));
  }
};
int main() {
  std::unordered_map<Point, int> m;
  m[{1, 2}] = 3;
}
```

## Concepts: the `because` chain

```cpp title="concept.cpp" run error
#include <concepts>
#include <string>
template <class T>
concept Shape = requires(const T& s) {
  { s.area() } -> std::convertible_to<double>;
  s.name();
};
struct Square {
  double side;
  double area() const { return side * side; }
};
void print(const Shape auto& s);
int main() {
  print(Square{2.0});
}
```

```text
concept.cpp:14:3: error: no matching function for call to 'print'
   14 |   print(Square{2.0});
      |   ^~~~~
concept.cpp:12:6: note: candidate template ignored: constraints not satisfied [with s:auto = Square]
   12 | void print(const Shape auto& s);
      |      ^
concept.cpp:12:18: note: because 'Square' does not satisfy 'Shape'
   12 | void print(const Shape auto& s);
      |                  ^
concept.cpp:6:5: note: because 's.name()' would be invalid: no member named 'name' in 'Square'
    6 |   s.name();
      |     ^
1 error generated.
```

A candidate whose constraints aren't satisfied isn't viable ([[over.match.viable#3]]), so the outer error is still `no matching function`. The `because` chain expands the concept's definition level by level until it reaches the unsatisfied **atomic constraint** ([[g:atomic-constraint|atomic constraint]]). An atomic constraint is checked by substituting the template arguments into the expression; if substitution fails, it isn't satisfied ([[temp.constr.atomic#3]]). The last item in the chain is the answer: `Square` has no `name()`.

The chain for `rsort.cpp` is longer, ending at `is_base_of_v<random_access_iterator_tag, bidirectional_iterator_tag>`, which likewise means list's iterators are only bidirectional. Concepts themselves are covered in [[topics/concepts]].

## Other overload resolution failures

### Ambiguous calls

```cpp title="ambig.cpp" run error
void f(long);
void f(double);
int main() {
  f(42);
}
```

```text
ambig.cpp:4:3: error: call to 'f' is ambiguous
    4 |   f(42);
      |   ^
ambig.cpp:1:6: note: candidate function
    1 | void f(long);
      |      ^
ambig.cpp:2:6: note: candidate function
    2 | void f(double);
      |      ^
1 error generated.
```

Both candidates are viable; the notes only list them without saying why neither wins. You have to work out the reason from the rules: `int` to `long` is an integral conversion and `int` to `double` a floating-integral conversion, both of Conversion rank in the table in [[over.ics.scs]], neither better than the other, so there is no unique best viable function ([[over.match.best.general#3]]). The fix is to make the argument type exactly match one of them: `f(42L)`, or an explicit conversion.

### `no viable conversion`

```cpp title="noconv.cpp" run error
#include <optional>
#include <string>
#include <string_view>
struct Meters { explicit Meters(double); };
int main() {
  std::string s = std::string_view("abc");
  std::optional<int> o = 3;
  int n = o;
  Meters m = 2.0;
}
```

```text
noconv.cpp:6:15: error: no viable conversion from 'std::string_view' (aka 'basic_string_view<char>') to 'std::string' (aka 'basic_string<char>')
(5 candidate constructor not viable notes omitted)
.../c++/v1/string:1091:42: note: explicit constructor is not a candidate
noconv.cpp:8:7: error: no viable conversion from 'std::optional<int>' to 'int'
noconv.cpp:9:10: error: no viable conversion from 'double' to 'Meters'
noconv.cpp:4:8: note: candidate constructor (the implicit copy constructor) not viable: no known conversion from 'double' to 'const Meters &' for 1st argument
noconv.cpp:4:8: note: candidate constructor (the implicit move constructor) not viable: no known conversion from 'double' to 'Meters &&' for 1st argument
noconv.cpp:4:26: note: explicit constructor is not a candidate
3 errors generated.
```

All three are copy-initializations of the form `T x = expression;`. When such a conversion is done by a constructor, only non-explicit constructors are candidates ([[over.match.copy#1.1]]); explicit constructors are used only in direct-initialization and explicit conversions ([[class.conv.ctor#2]]). So the key note is `explicit constructor is not a candidate`. Constructing a `string` from a `string_view` and a `Meters` from a `double` are both explicit; switch to direct-initialization: `std::string s{sv};`, `Meters m{2.0};`.

`optional<int>` to `int` has no conversion function at all, so Clang has no note to give. Here you must spell out how to get the value, for example `o.value()` or `*o`.

### Binding a non-const lvalue reference to a temporary

```cpp title="tempref.cpp" run error
#include <string>
void append(std::string& out, const char* s);
std::string make();
int main() {
  append(make(), "x");
  std::string& r = std::string("tmp");
}
```

```text
tempref.cpp:5:3: error: no matching function for call to 'append'
    5 |   append(make(), "x");
      |   ^~~~~~
tempref.cpp:2:6: note: candidate function not viable: expects an lvalue for 1st argument
    2 | void append(std::string& out, const char* s);
      |      ^      ~~~~~~~~~~~~~~~~
tempref.cpp:6:16: error: non-const lvalue reference to type 'basic_string<...>' cannot bind to a temporary of type 'basic_string<...>'
    6 |   std::string& r = std::string("tmp");
      |                ^   ~~~~~~~~~~~~~~~~~~
2 errors generated.
```

[[dcl.init.ref#5.2]] says that when the initializer expression isn't a suitable lvalue, the reference must be a const (and non-volatile) lvalue reference or an rvalue reference, otherwise the program is ill-formed. The `basic_string<...>` in the second message is Clang eliding template arguments that are the same on both sides; see `-fno-elide-type` below.

The same rule shows up in the library in another guise. `std::thread` copies its arguments and then passes them to the thread function as rvalues, so a function with a `std::string&` parameter can't be called:

```cpp title="thread_ref.cpp" run error
#include <string>
#include <thread>
void work(std::string& out);
int main() {
  std::string s;
  std::thread t(work, s);
  t.join();
}
```

```text
.../c++/v1/__thread/thread.h:221:19: error: static assertion failed due to requirement '__is_invocable_v<void (*)(std::string &), std::string>': 
thread_ref.cpp:6:15: note: in instantiation of function template specialization 'std::thread::thread<void (&)(std::string &), std::string &, 0>' requested here
.../c++/v1/__thread/thread.h:170:3: error: no matching function for call to '__invoke'
(the rest omitted; 2 errors in total)
```

The `static_assert` condition reads: can `void(*)(std::string&)` be called with a `std::string` rvalue? No, because an rvalue can't bind to a non-const lvalue reference. The fix is `std::thread t(work, std::ref(s));`. Value categories are covered in [[topics/value-categories]].

## Incomplete types

```cpp title="incomplete.cpp" run error
struct Widget;
Widget* make();
int main() {
  Widget* w = make();
  return w->size;
}
```

```text
incomplete.cpp:5:11: error: member access into incomplete type 'Widget'
    5 |   return w->size;
      |           ^
incomplete.cpp:1:8: note: forward declaration of 'Widget'
    1 | struct Widget;
      |        ^
1 error generated.
```

A class that is declared but not defined is an **incomplete type** ([[g:incomplete-type|incomplete type]], [[basic.types.general#3]]). Pointers to it can be passed around freely, but member access requires the class to be complete ([[expr.ref#5]]). The note points to the forward declaration; the fix is to include the header that defines `Widget` in this TU.

Harder to recognize is a `unique_ptr` member with a forward declaration:

```cpp title="incomplete2.cpp" run error
#include <memory>
struct Impl;
struct Handle {
  std::unique_ptr<Impl> p;
};
int main() {
  Handle h;
}
```

```text
.../c++/v1/__memory/unique_ptr.h:72:19: error: invalid application of 'sizeof' to an incomplete type 'Impl'
   72 |     static_assert(sizeof(_Tp) >= 0, "cannot delete an incomplete type");
      |                   ^~~~~~~~~~~
.../c++/v1/__memory/unique_ptr.h:264:7: note: in instantiation of member function 'std::default_delete<Impl>::operator()' requested here
.../c++/v1/__memory/unique_ptr.h:229:71: note: in instantiation of member function 'std::unique_ptr<Impl>::reset' requested here
incomplete2.cpp:3:8: note: in instantiation of member function 'std::unique_ptr<Impl>::~unique_ptr' requested here
    3 | struct Handle {
      |        ^
incomplete2.cpp:7:10: note: in implicit default constructor for 'Handle' first required here
    7 |   Handle h;
      |          ^
incomplete2.cpp:2:8: note: forward declaration of 'Impl'
1 error generated.
```

`unique_ptr<T>` allows `T` to be incomplete, but the default deleter's `default_delete<T>::operator()` requires `T` to be complete (the standard writes this requirement as *Mandates*, so a violation is ill-formed, [[unique.ptr.dltr.dflt#3]]). The last two items in the chain say who needs the deletion: `Handle`'s implicitly defined default constructor. A constructor potentially invokes the destructor of every member ([[class.base.init#14]]), to clean up if an exception is thrown midway through construction, and these implicit members are all generated inline at `Handle`'s definition, where `Impl` is still incomplete.

The fix is the standard pimpl pattern: only declare `Handle`'s constructor and destructor in the header, and define them in the `.cpp` after `Impl`'s definition (`Handle::~Handle() = default;`). See [[patterns/pimpl]].

## Using a deleted function

```cpp title="deleted.cpp" run error
#include <memory>
int main() {
  auto p = std::make_unique<int>(1);
  auto q = p;
}
```

```text
deleted.cpp:4:8: error: call to implicitly-deleted copy constructor of 'unique_ptr<int>'
    4 |   auto q = p;
      |        ^   ~
.../c++/v1/__memory/unique_ptr.h:181:55: note: copy constructor is implicitly deleted because 'unique_ptr<int>' has a user-declared move constructor
1 error generated.
```

Using a deleted function is ill-formed ([[dcl.fct.def.delete#2]]). The reason the note gives is a general rule: if a class declares a move constructor, the implicitly declared copy constructor is defined as deleted ([[class.copy.ctor#6]]). The standard's `unique_ptr` synopsis actually spells out `unique_ptr(const unique_ptr&) = delete;` ([[unique.ptr.single.general]]); libc++ omits that declaration and achieves the same effect by implicit deletion, which is why the message says implicitly-deleted. The fix is `auto q = std::move(p);`; the meaning of ownership is covered in [[topics/ownership-and-smart-pointers]].

Hide this error inside a container, and you get a long chain:

```text
(deleted2.cpp line 6: std::vector<std::unique_ptr<int>> w = v;)
.../c++/v1/__memory/allocator_traits.h:362:5: error: no matching function for call to '__construct_at'
(5 in instantiation of notes omitted)
deleted2.cpp:6:41: note: in instantiation of member function 'std::vector<std::unique_ptr<int>>::vector' requested here
.../c++/v1/__memory/construct_at.h:43:58: note: candidate template ignored: substitution failure [with _Tp = std::unique_ptr<int>, _Args = <const std::unique_ptr<int> &>]: call to implicitly-deleted copy constructor of 'std::unique_ptr<int>'
```

The error line says there is no match for `__construct_at`, without saying why. The reason follows `substitution failure` in the last note: copying a `vector` requires copying its elements, and `unique_ptr` isn't copyable.

## Dependent names missing `typename` or `template`

```cpp title="depname.cpp" run error
template <class C>
void first(const C& c) {
  C::const_iterator it = c.begin();
}
template <class T>
struct Box {
  template <class U> U get() const;
};
template <class T>
int peek(const Box<T>& b) {
  return b.get<int>();
}
```

```text
depname.cpp:3:3: error: missing 'typename' prior to dependent type name 'C::const_iterator'
    3 |   C::const_iterator it = c.begin();
      |   ^~~~~~~~~~~~~~~~~
      |   typename 
depname.cpp:11:12: error: use 'template' keyword to treat 'get' as a dependent template name
   11 |   return b.get<int>();
      |            ^
      |            template 
2 errors generated.
```

The extra line below the source line is a **fix-it**: Clang shows what to insert where.

A template definition must be parsable before instantiation, and `C::const_iterator` depends on `C`, so at the point of definition the compiler doesn't know whether it is a type or a value. Only in a **type-only context** (for example a function return type, or the right side of a `using` alias) is such a name automatically taken as a type ([[temp.res.general#5]]); a declaration statement in a function body isn't such a context, so `typename` is required. Likewise, `b.get` depends on `T`, and the `<` after it is taken as the start of a template argument list only if `template` is written before `get` ([[temp.names#7]]); otherwise it is parsed as less-than. The fixed versions are `typename C::const_iterator it` and `b.template get<int>()`. Why lookup happens in two phases is covered in [[topics/two-phase-lookup]].

## Narrowing in braces

```cpp title="narrow.cpp" run error
#include <vector>
int main() {
  double d = 3.7;
  int a{d};
  long long big = 1LL << 40;
  std::vector<int> v{1, 2, big};
  unsigned u{-1};
}
```

```text
narrow.cpp:4:9: error: type 'double' cannot be narrowed to 'int' in initializer list [-Wc++11-narrowing]
    4 |   int a{d};
      |         ^
narrow.cpp:4:9: note: insert an explicit cast to silence this issue
    4 |   int a{d};
      |         ^
      |         static_cast<int>( )
narrow.cpp:6:28: error: non-constant-expression cannot be narrowed from type 'long long' to 'value_type' (aka 'int') in initializer list [-Wc++11-narrowing]
narrow.cpp:7:14: error: constant expression evaluates to -1 which cannot be narrowed to type 'unsigned int' [-Wc++11-narrowing]
(notes and two unused variable warnings omitted)
```

When list-initialization requires a **narrowing conversion** ([[g:narrowing-conversion|narrowing conversion]], defined in [[dcl.init.list#7]]), the program is ill-formed (for example [[dcl.init.list#3.9]]). The three messages correspond to the three cases of narrowing: floating to integer; a source that isn't a constant expression; and a source that is a constant expression whose value doesn't fit. The third implies that constants whose value fits, such as `unsigned u{1};`, are allowed.

If you really want truncation, write a `static_cast` as the note suggests, so the intent shows in the code. The forms of initialization are covered in [[topics/initialization]].

!!! pitfall "Don't silence it with `-Wno-c++11-narrowing`"
    This error hangs on a warning option. With `-Wno-c++11-narrowing` added on our test machine, `narrow.cpp` compiled with no diagnostics at all. The compiler then accepts an ill-formed program without issuing the at least one diagnostic required by [[intro.compliance.general#2.3]]. This switch exists for migrating old code and shouldn't be used to fix errors.

## The most vexing parse

```cpp title="vexing.cpp" run error
struct Timer { Timer(); void start(); };
int main() {
  Timer t();
  t.start();
}
```

```text
vexing.cpp:3:10: warning: empty parentheses interpreted as a function declaration [-Wvexing-parse]
    3 |   Timer t();
      |          ^~
vexing.cpp:3:10: note: remove parentheses to declare a variable
    3 |   Timer t();
      |          ^~
vexing.cpp:4:3: error: base of member reference is a function; perhaps you meant to call it with no arguments?
    4 |   t.start();
      |   ^
      |    ()
1 warning and 1 error generated.
```

`Timer t();` by itself is well-formed: it declares a function `t` taking no arguments and returning `Timer`. `()` isn't part of the initializer grammar, so the line can only be parsed as a function declaration (the note in [[dcl.init.general#15.4]]). Clang warns about this, and the real error comes on the next line, which uses the function as an object. If `t` weren't used that way later, there would be only a warning.

The lesson: sometimes the `warning` before an `error` is the actual cause.

The version with arguments is more insidious:

```cpp title="vexing2.cpp" run error
#include <string>
struct Logger {
  explicit Logger(std::string name);
  void log(const char*);
};
int main() {
  Logger lg(std::string());
  lg.log("hi");
}
```

```text
vexing2.cpp:7:12: warning: parentheses were disambiguated as a function declaration [-Wvexing-parse]
    7 |   Logger lg(std::string());
      |            ^~~~~~~~~~~~~~~
vexing2.cpp:7:13: note: add a pair of parentheses to declare a variable
    7 |   Logger lg(std::string());
      |             ^            
      |             (            )
vexing2.cpp:8:5: error: member reference base type 'Logger (std::string (*)())' (aka 'Logger (basic_string<char> (*)())') is not a structure or union
1 warning and 1 error generated.
```

`std::string()` can be read as an unnamed parameter whose type is a function returning `std::string` (adjusted to a function pointer). Anything that can be parsed as a declaration is treated as one ([[dcl.ambig.res#1]]); this is the [[g:most-vexing-parse|most vexing parse]]. The type `Logger (std::string (*)())` in the error message is exactly that function's type. Using braces, `Logger lg{std::string()};`, removes the ambiguity.

## Lambda capture errors

```cpp title="capture.cpp" run error
struct Counter {
  int n = 0;
  auto inc() { return [] { ++n; }; }
};
int main() {
  int total = 0;
  auto add = [](int x) { total += x; };
  auto add2 = [total](int x) { total += x; };
}
```

```text
capture.cpp:3:30: error: 'this' cannot be implicitly captured in this context
    3 |   auto inc() { return [] { ++n; }; }
      |                              ^
capture.cpp:3:24: note: explicitly capture 'this'
    3 |   auto inc() { return [] { ++n; }; }
      |                        ^
      |                        this
capture.cpp:7:26: error: variable 'total' cannot be implicitly captured in a lambda with no capture-default specified
    7 |   auto add = [](int x) { total += x; };
      |                          ^
capture.cpp:6:7: note: 'total' declared here
capture.cpp:7:14: note: lambda expression begins here
capture.cpp:7:15: note: capture 'total' by value
capture.cpp:7:15: note: capture 'total' by reference
capture.cpp:7:15: note: default capture by value
capture.cpp:7:15: note: default capture by reference
capture.cpp:8:38: error: cannot assign to a variable captured by copy in a non-mutable lambda
    8 |   auto add2 = [total](int x) { total += x; };
      |                                ~~~~~ ^
3 errors generated.
```

(The source lines of the four fix-its for the second error are omitted; in the original output each one shows its insertion point.)

The first two errors are the same rule: a local entity (including `*this`) odr-used in a scope where it isn't **odr-usable** ([[g:odr-usable|odr-usable]]) makes the program ill-formed ([[basic.def.odr#10]]). The lambda's scope lies between the lambda body and the enclosing function, and the entity is usable only if the lambda has a capture-default or explicitly captures it. The four fix-its Clang lists are the four ways of satisfying that condition. In a member function, `n` is really `this->n`, so what must be captured is `this`.

The third error: a closure type's function call operator is a `const` member function by default ([[expr.prim.lambda.closure#7]]), and a by-copy capture is a data member of the closure, so it can't be modified. To modify the copy, add `mutable`; to modify the outer `total`, capture by reference. Another common error is the same name appearing twice in a capture list ([[expr.prim.lambda.capture#2]]), for which Clang reports `'arr' can appear only once in a capture list`. The closure model is covered in [[topics/lambdas]].

## Link errors

If the last line of the compiler's output is `linker command failed with exit code 1`, the error comes from the linker. Every TU has compiled successfully by then; the problem is that symbols don't match up between TUs. In the standard, these problems correspond to ODR rules that require no diagnostic ([[basic.def.odr#12]], [[basic.def.odr#16]]); the linker can find them only because they happen to be visible at the symbol level. Where symbols come from is covered in [[toolchain/linking-and-symbols]].

### Undefined symbols

```cpp title="shape.h"
#pragma once
#include <string>
namespace geo {
struct Circle {
  double r;
  double area() const;
};
std::string describe(const Circle& c, int precision);
}
```

```cpp title="shape.cpp"
#include "shape.h"
namespace geo {
double Circle::area() const { return 3.14159 * r * r; }
std::string describe(const Circle& c, long precision) {
  return "circle";
}
}
```

```cpp title="main.cpp"
#include "shape.h"
#include <cstdio>
int main() {
  geo::Circle c{1.0};
  std::printf("%f %s\n", c.area(), geo::describe(c, 2).c_str());
}
```

```text
$ clang++ -std=c++2c --ld-path=/usr/bin/ld main.cpp shape.cpp -o app
Undefined symbols for architecture arm64:
  "geo::describe(geo::Circle const&, int)", referenced from:
      _main in main-1135e2.o
ld: symbol(s) not found for architecture arm64
clang++: error: linker command failed with exit code 1 (use -v to see invocation)
```

The `describe` in `shape.cpp` has a `long` parameter; it is a different overload, not the definition of the declaration in the header. The linker has already demangled the symbol name into a readable signature, and the way to read it is to compare it character by character with the definition you wrote: namespace, class, parameter types, cv-qualifiers and references must all match.

The names before demangling can be seen with `llvm-nm`, and `c++filt` or `llvm-cxxfilt` demangles them:

```text
$ clang++ -std=c++2c -c main.cpp shape.cpp
$ llvm-nm main.o | grep describe
                 U __ZN3geo8describeERKNS_6CircleEi
$ llvm-nm shape.o | grep describe
0000000000000038 T __ZN3geo8describeERKNS_6CircleEl
$ echo __ZN3geo8describeERKNS_6CircleEi | c++filt
geo::describe(geo::Circle const&, int)
```

`U` means referenced but undefined, and `T` means defined in the code section. The two names differ only in the last letter: `i` is `int`, `l` is `long`. The encoding rules are in [[toolchain/name-mangling]].

Two equally common variants:

- A template declared only in a header and defined in a `.cpp`. The using TU can't see the definition and can only leave a reference to the specialization; on our test machine this reported `"int sum<int>(std::__1::vector<int, std::__1::allocator<int>> const&)", referenced from: _main`. `std::__1` is the inline namespace libc++ uses to distinguish ABI versions. The fix is to put the definition in the header, or explicitly instantiate it in the `.cpp`.
- A class declares a virtual function but doesn't define it. The system linker on our test machine adds a hint:

```text
Undefined symbols for architecture arm64:
  "Base::~Base()", referenced from:
      Derived::~Derived() in vt-1068a8.o
  "typeinfo for Base", referenced from:
      typeinfo for Derived in vt-1068a8.o
  "vtable for Base", referenced from:
      Base::Base() in vt-1068a8.o
   NOTE: a missing vtable usually means the first non-inline virtual member function has no definition.
```

`vtable for Base` is undefined because the vtable is emitted only in the TU that defines the key function (the first non-inline, non-pure virtual function, here `~Base`); see [[toolchain/object-layout-and-vtables]].

### Duplicate definitions

```cpp title="util.h"
#pragma once
int clamp01(int x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
int counter = 0;
```

When two `.cpp` files both include this header:

```text
duplicate symbol '_counter' in:
    /private/var/folders/.../T/a-80a5f1.o
    /private/var/folders/.../T/b-316e7d.o
duplicate symbol 'clamp01(int)' in:
    /private/var/folders/.../T/a-80a5f1.o
    /private/var/folders/.../T/b-316e7d.o
ld: 2 duplicate symbols
```

A non-inline, non-template function or variable with a definition in each of several TUs makes the program ill-formed, no diagnostic required ([[basic.def.odr#16.1]]). The fix is to write `inline int clamp01(...)` and `inline int counter = 0;` in the header, or move the definitions into one `.cpp`. The linker can only catch duplicates of strong definitions like these; inline functions defined inconsistently in different TUs are accepted by the linker all the same, see [[toolchain/linking-and-symbols]].

On Linux, GNU ld and lld word these two errors differently; with neither linker on our test machine, we can't quote them. The content is the same: a symbol name, plus the object files that reference or define it.

## Controlling diagnostic output

| Option | Effect | Observed on our test machine |
|---|---|---|
| `-ferror-limit=N` | Stop after the Nth error | With the default (the driver passes `-ferror-limit 19` to the frontend), a file with 30 errors outputs 19 errors plus a `fatal error: too many errors emitted`, for `20 errors generated` in total; `=0` means no limit |
| `-ftemplate-backtrace-limit=N` | Maximum levels of instantiation chain shown | 10 levels by default; set to 2, `sortlist.cpp`'s chain folds into one level at each end plus `(skipping 4 contexts ...)` |
| `-fno-elide-type` | Stop eliding the common parts of two types with `[...]` | See below |
| `-fdiagnostics-show-template-tree` | Draw the difference between two template types as a tree | See below; off by default, and Clang 23 doesn't accept the spelling `-fno-diagnostics-show-template-tree` (`unknown argument`) |
| `-fno-caret-diagnostics` | Don't print source lines and markers | Output becomes one line per diagnostic, good for grep |
| `-fdiagnostics-format=sarif` | Output JSON in SARIF format for tools to read | Also reports `diagnostic formatting in SARIF mode is currently unstable` |

When types are long, the default elision, `-fno-elide-type` and the template tree each have their uses:

```cpp title="tree.cpp" run error
#include <map>
#include <string>
#include <vector>
using Index = std::map<std::string, std::vector<int>>;
void load(const Index& idx);
int main() {
  std::map<std::string, std::vector<long>> idx;
  load(idx);
}
```

```text
$ clang++ -std=c++2c -fsyntax-only tree.cpp
tree.cpp:5:6: note: candidate function not viable: no known conversion from 'map<[...], vector<long>>' to 'const map<[...], vector<int>>' for 1st argument

$ clang++ -std=c++2c -fsyntax-only -fno-elide-type tree.cpp
tree.cpp:5:6: note: candidate function not viable: no known conversion from 'map<std::string, vector<long>>' to 'const map<std::string, vector<int>>' for 1st argument

$ clang++ -std=c++2c -fsyntax-only -fdiagnostics-show-template-tree tree.cpp
tree.cpp:5:6: note: candidate function not viable: no known conversion from argument type to parameter type for 1st argument
  [(no qualifiers) != const] map<
    [...], 
    vector<
      [long != int]>>
```

The template tree pins the difference down to `[long != int]`, which reads better than one long string when there are many levels of nesting.

Recommended habits for reading errors:

1. Look only at the first error. Fix it, recompile, then look at the next. One missing semicolon or type name can produce dozens of knock-on errors.
2. When the error is in a library header, find the last `in instantiation of` located in your own code; then look for the `static_assert` message and the reason after `substitution failure`.
3. When there is a `warning` before the error, read the warning first; the most vexing parse is a case in point.
4. For link errors, compare the reported signature character by character with your own definition.
5. If it still makes no sense, compile the same code with another compiler on Compiler Explorer. Different compilers pick out different key information, and the two outputs together often make it clear.

Problems after the code compiles belong to [[toolchain/debugging]] and [[toolchain/static-analysis]].

## Questions

!!! question "1"
    Why does `void f(int&); f(1);` report `expects an lvalue` while `void g(const int&); g(1);` compiles? What if `f` is changed to `void f(int&&);`?

<details markdown="1">
<summary>Answer</summary>

[[dcl.init.ref#5.2]]: when the initializer expression is an rvalue, a non-const lvalue reference can't bind to it and the program is ill-formed; a const lvalue reference can, in which case a temporary is materialized and bound. `int&&` is an rvalue reference, which can likewise bind to the prvalue `1`, so `f(1)` compiles too.
</details>

!!! question "2"
    `std::sort` on a `std::list` reports 4 errors in 114 lines, while `std::ranges::sort` reports only 1 error. Where in the standard does the difference come from?

<details markdown="1">
<summary>Answer</summary>

`std::sort`'s requirement on iterators is in [[algorithms.requirements#4.7]], a textual requirement on template arguments that doesn't take part in overload resolution, so the call itself goes through, and the error only appears when the implementation uses `-` internally, once for every place that uses `-`. `std::ranges::sort` constrains its parameter with the `random_access_range` concept, so the candidate whose constraint isn't satisfied is eliminated during overload resolution ([[over.match.viable#3]]); the error stops at the call site, and the `because` chain says which atomic constraint isn't satisfied.
</details>

!!! question "3"
    Changing `int counter = 0;` in `util.h` to `static int counter = 0;` also gets rid of `duplicate symbol`. How does it differ from `inline int counter = 0;`?

<details markdown="1">
<summary>Answer</summary>

`static` gives `counter` internal linkage, so every TU that includes the header has its own independent `counter`; the linker sees no duplicates, but a change made in one TU isn't visible in another. An `inline` variable is still a single entity with external linkage, whose definitions in several TUs are merged into one by the linker ([[basic.def.odr#16]] allows inline variables to be defined in several TUs). To share state, use `inline`.
</details>

## Summary

| Message | Rule | Look first at |
|---|---|---|
| `no matching function` + `not viable` | [[over.match.viable]] | Each candidate's note says which step it failed |
| `call to ... is ambiguous` | [[over.match.best.general#3]] | Compare the conversion ranks of the arguments yourself |
| `constraints not satisfied` + `because` | [[temp.constr.atomic#3]] | The last item of the `because` chain |
| Error in a library header + `in instantiation of` | [[temp.inst]] | The last instantiation note in your own file; the `static_assert` message |
| `incomplete type` | [[basic.types.general#3]] | The `forward declaration` note; who triggered the destruction |
| `implicitly-deleted` / `deleted function` | [[dcl.fct.def.delete#2]] | The note gives the reason for deletion |
| `missing 'typename'` / `use 'template' keyword` | [[temp.res.general#5]], [[temp.names#7]] | Insert the keyword as the fix-it says |
| `cannot be narrowed` | [[dcl.init.list#7]] | State the intent with `static_cast` |
| `-Wvexing-parse` | [[dcl.ambig.res#1]] | Use braces or drop the empty parentheses |
| `cannot be implicitly captured` | [[basic.def.odr#10]] | Pick one of the captures the notes suggest |
| `Undefined symbols` | [[basic.def.odr#12]] | Compare signatures character by character; `llvm-nm` + `c++filt` |
| `duplicate symbol` | [[basic.def.odr#16]] | Add `inline` to definitions in headers |
