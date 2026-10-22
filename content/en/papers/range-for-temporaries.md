---
title: Fixing temporaries in range-based for (P2718)
summary: C++23 keeps every temporary in a range-based for initializer alive until the loop ends. Why the fix took thirteen years, which alternatives the committee weighed, what the final wording changed, and which dangling cases it still leaves behind.
tags: proposal, range-based for, temporaries, lifetime, dangling, C++23
updated: 2026-10-21
---

!!! tldr
    - Up to C++20, in `for (auto x : make().items())` the temporary returned by `make()` is destroyed before the loop starts. The reference returned by `items()` dangles, and the behavior is undefined.
    - The cause is that range-based for is defined as a rewrite: the initializer first initializes an `auto&&` reference on its own, and a reference only extends the temporary bound directly to it.
    - C++23's [[P2718R0]] adds a special case to [[class.temporary#7]]: every temporary in the initializer that would otherwise be destroyed at the end of the full-expression lives until the loop ends.
    - The committee rejected rewriting the loop as several declarations, rewriting it as a lambda call, extending lifetimes in general, and relying on `lifetimebound` annotations. The chosen fix introduces no new lifetime model; it only changes what range-based for itself guarantees.
    - The cost is that some destructors run later, and a temporary holding a lock now carries the lock into the loop body. By-value parameters, ordinary `auto&&` declarations and views stored in variables still dangle.

## The problem: two statements without a semicolon

Replacing a public data member with a getter is about as ordinary as refactoring gets. The two snippets below differ by exactly that step. The left one is correct; the right one is undefined behavior in C++20:

<div class="compare" markdown="1">

```cpp
struct Person {
  std::vector<int> values{1, 2, 3, 4};
};
Person createPerson();

for (int v : createPerson().values)
  use(v);
```

```cpp
class Person {
  std::vector<int> values{1, 2, 3, 4};
public:
  const std::vector<int>& getValues() const
  { return values; }
};
Person createPerson();

for (int v : createPerson().getValues())
  use(v);   // C++20: UB
```

</div>

The example comes from [[P2012R2]], whose author says it is a bug they actually ran into. To see the difference you need to know how range-based for is defined. [[stmt.ranged#1]] says it is equivalent to a rewrite, roughly:

```cpp
{
  auto&& __range = createPerson().getValues();   // a separate declaration
  auto __begin = __range.begin();
  auto __end = __range.end();
  for (; __begin != __end; ++__begin) {
    int v = *__begin;
    use(v);
  }
}
```

The first line is a declaration, and its initializer is a **full-expression** ([[g:full-expression]]): an expression that is not part of another expression. Temporaries created in a full-expression are by default destroyed when the full-expression finishes evaluating ([[class.temporary#4]]). The exception is **lifetime extension** ([[g:lifetime-extension]]): when a reference binds directly to a temporary or to a subobject of one, the temporary lives as long as the reference ([[class.temporary#6]]).

On the left, `createPerson().values` is a member access on a temporary. `__range` binds to a subobject of the temporary `Person`, so the whole `Person` is extended. On the right there is a function call in between, and `__range` binds to whatever object the reference returned by `getValues()` refers to. The compiler does not look into the function body and cannot know where that reference points, so it extends nothing. The temporary `Person` is destroyed at the end of the first line, and `__range` dangles from the very start of the loop. The details of the extension rules and their exceptions are covered in [[topics/dangling-references|the topic page on dangling references]].

Here is a runnable version to compare the two language modes:

```cpp run title="person.cpp" std=c++20 ub
#include <cstdio>
#include <vector>
class Person {
  std::vector<int> values{1, 2, 3, 4};
public:
  const std::vector<int>& getValues() const { return values; }
};
Person createPerson() { return {}; }
int main() {
  int sum = 0;
  for (int v : createPerson().getValues()) sum += v;
  std::printf("%d\n", sum);
}
```

Tested with Clang 23 and `-fsanitize=address`: `-std=c++20` reports `stack-use-after-scope`, while `-std=c++23` prints `10` as expected. In C++20 mode the compiler gives no warning at all.

[[P2012R2]] makes an observation about why this trap is especially dangerous. Other dangling references usually require two visible things at once: a reference declaration (`&`, `&&`) and a semicolon ending the statement. `const auto& s = get().name();` has both, so a reader at least has a chance to get suspicious. The head of a range-based for looks like a single unit, with no semicolon and no reference written anywhere, yet the dangling happens inside it.

The same problem shows up in a long list of common idioms. The comparison table in [[P2644R1]] lists `getVector()[0]`, `get<0>(getTuple())`, `getOptionalColl().value()`, `get<string>(getVariant())`, `std::span(getVector().data(), 2)`, and `co_await` on a coroutine that returns a reference. Whenever the initializer first produces a temporary and then goes through a call that returns a reference or a non-owning view, it dangles in C++20.

### The C++20 workaround

C++20's [[P0614R1]] gave range-based for an *init-statement*, so you can store the object in a named variable first:

```cpp run title="init-statement.cpp" std=c++20 ok
#include <cstdio>
#include <vector>
class Person {
  std::vector<int> values{1, 2, 3, 4};
public:
  const std::vector<int>& getValues() const { return values; }
};
Person createPerson() { return {}; }
int main() {
  int sum = 0;
  for (auto p = createPerson(); int v : p.getValues()) sum += v;
  std::printf("%d\n", sum);
}
```

This works, but it does not solve the problem. [[P2012R2]] gives the reason: the person writing this line has to know about the trap in the first place, and the people who don't know are exactly the ones who fall into it. Even when someone who knows writes it, a later maintainer may simplify it back and reintroduce the bug.

## Thirteen years without a fix

The problem was raised as [[CWG900]] in 2009, and again as [[CWG1498]] in 2012, which was closed as a duplicate. The initial response to CWG900 was that the rewrite uses the initializer to initialize a reference, so the temporary is extended to the whole statement. That response only considered the one temporary bound directly to `__range`, which is precisely the problem.

In 2014 the issue went to EWG (the Evolution Working Group, responsible for language design direction). According to the minutes quoted in [[P2012R2]], EWG wanted someone to write a proposal, but raised two concerns: don't introduce a new lifetime model; and the rule that temporaries are destroyed at the end of the full-expression exists precisely because it uses less memory than destroying them at the end of the block, and it suits RAII. In 2017 CWG said it was inclined to accept a change but felt EWG needed to decide first.

[[P2012R2]] put forward a concrete design in 2020–2021, and EWG agreed the problem needed fixing. According to [[P2644R1]], when the final wording was discussed, some people wanted to wait for a broader fix, so it did not pass. As C++23 was about to be finalized, no broader proposal had appeared. P2644R1 argued for going back to the original approach, pointing out that it does not prevent a bigger fix later. The wording that came out of CWG review is [[P2718R0]], which went into C++23 in November 2022 and also resolved CWG900.

## The design space

### The goal

[[P2012R2]] describes the desired effect as a series of declarations: the intermediate result of every step in the initializer behaves as if it were stored in a variable.

```cpp
// for (auto elem : foo().bar().getValues()) should be equivalent to
auto&& tmp1 = foo();            // extended
auto&& tmp2 = tmp1.bar();       // extended
auto&& rg   = tmp2.getValues();
// ...then iterate over rg
```

The question is how to turn that into wording. The paper lists three ways to do it, and the discussion produced a few more. Here they all are.

### Rewrite as several declarations, or as a function call

The first approach keeps today's rewrite but declares that its internal declarations are not separate statements that end temporary lifetimes. The second rewrites the loop as a call to a lambda, with the initializer as the argument:

```cpp
[&](auto&& rg) {
  auto pos = rg.begin(), end = rg.end();
  for (; pos != end; ++pos) { auto elem = *pos; /* loop body */ }
}(foo().bar().getValues());   // temporaries in the argument live until the call ends
```

Temporaries in a function argument live until the end of the full-expression containing the call, so the whole loop runs within their lifetime. The 2017 notes on [[CWG900]] mention a similar idea: treat the initializer as if it were a function argument.

The model is intuitive, but awkward to write as wording. `return`, `break`, `goto`, `co_yield` and `co_return` in the loop body all mean something completely different inside a lambda, and each would need its own rule. [[P2012R2]] did not choose it for that reason.

### Add a special case to the rules for temporaries

The paper chose the third approach: leave the rewrite alone and add one more case to the list of special destruction points in [[class.temporary]], namely that temporaries in a range-based for initializer live until the loop ends.

This answers both of EWG's concerns directly. There is no new lifetime model: [[class.temporary]] already has several cases where a temporary is not destroyed at the end of its full-expression. The general rule of destruction at the end of the full-expression is unchanged as well; only the guarantee that range-based for gives is changed.

### Extend temporary lifetimes in general

A more radical approach is to change the general rule so that references extend more temporaries, for example ones reached through a reference returned from a function call. Proposals like this have come up several times before and were all rejected.

[[P2012R2]] quotes Stroustrup's recollection: in the 1980s, objects declared in the init part of a `for` lived until the end of the block (this is documented in the ARM). He initially thought that was safer, then changed his mind after many complaints. The most serious complaint was about matrix temporaries living too long: the memory they held made initialization inside a `for` almost unusable. Today's rule of destruction at the end of the full-expression is the result of that lesson.

### Annotations or warnings instead of a language change

[[P0936R0]] proposed an annotation on a parameter or on `*this` (tentatively called `lifetimebound` in the paper) declaring that the lifetime of the return value depends on it. With that information a compiler could either extend the temporary or just warn. The paper lists `for (auto x : reversed(make_vector()))` among the cases to solve, but does not decide between the two options, and cautions that if only some cases are extended automatically, dangling becomes even harder to spot at the call site.

Clang offers the warning option as the extension attribute `[[clang::lifetimebound]]`. [[P2012R2]] argues that warnings cannot replace a fix: the annotation is not in the standard; someone has to go and annotate every getter that returns a reference to a member; many projects ignore warnings; and when the function body is not visible, the compiler cannot tell whether `getName()` (returns a member) or `getAnswer()` (returns a `static` object) is the one that dangles, so making it an error would produce false positives.

### Leave the language alone

The last option is to change nothing: teach people to use the *init-statement*, or design a new kind of loop. The problem with the former has already been covered. The latter only helps if the old range-based for is deprecated and people are forced to change their code, and deprecating the most commonly used loop syntax is not realistic.

### Comparison

| Approach | Fixes `make().items()` | Cost or obstacle |
|---|---|---|
| Internal declarations are not separate statements | Yes | Needs a special case for declarations in the rewrite; awkward wording |
| Rewrite as a lambda call | Yes | `return`, `goto` and coroutine statements all need special rules |
| Special case in [[class.temporary]] (adopted) | Yes | Later destruction |
| Extend lifetimes in general | Yes | Changes memory use and RAII behavior of all code; rejected before |
| `lifetimebound` annotation | Only warns, or needs per-function annotation | Not in the standard; false negatives and false positives |
| Only promote the *init-statement* | No | Relies on programmers knowing the trap in advance |

## The cost: later destruction

The new rule only delays destruction; it adds no operations. The change is observable only when a destructor has side effects. Here is a type that only prints, standing in for `std::lock_guard`:

```cpp run title="lock.cpp" ok
#include <cstdio>
#include <vector>
struct Lock {   // stands in for lock_guard: only prints
  Lock()  { std::printf("lock\n"); }
  ~Lock() { std::printf("unlock\n"); }
};
std::vector<int> snapshot(const Lock&) { return {1, 2}; }
int main() {
  for (int x : snapshot(Lock{}))
    std::printf("body %d\n", x);
}
```

Output with Clang 23:

```text
-std=c++20      -std=c++23
lock            lock
unlock          body 1
body 1          body 2
body 2          unlock
```

In C++20 the lock only protects the single call to `snapshot`. In C++23 the lock is held until the loop ends. If the loop body locks the same mutex again, there is trouble. [[diff.cpp20]] records exactly this example, saying the code was fine in C++20 and now deadlocks. Strictly speaking, calling `lock()` on a `std::mutex` the same thread already owns violates its precondition ([[thread.mutex.requirements.mutex.general#6]]) and is undefined behavior; deadlock is just the most common symptom.

[[P2012R2]] argues that such code was already fragile: if `snapshot` returned a reference instead of a copy, the C++20 loop body would be accessing shared data outside the lock. The paper also reports a sampling analysis on a large codebase: there were about ten thousand destructions in range-based for initializers, and after grouping them by type none were found that would be affected. On the contrary, many of those destructions belonged to helper classes written specifically to work around this bug.

The other cost is memory. A large object in the initializer used to be freed before the loop started in C++20; now it is held for the whole loop. [[P2012R2]] admits this could exceed a memory limit in rare cases. When that matters, an *init-statement* or a plain `for` loop lets you control the lifetime yourself.

## The final wording

### A fourth case in [class.temporary]

[[P2718R0]] changed "three contexts" in [[class.temporary#5]] to "four" and added a new paragraph, today's ¶7:

!!! std
    If such a temporary object would otherwise be destroyed at the end of the *for-range-initializer* full-expression, the object persists for the lifetime of the reference initialized by the *for-range-initializer*. ([[class.temporary#7]])

    A temporary in the initializer that would otherwise die at the end of that full-expression lives as long as the reference the initializer initializes, which is `__range`.

The qualification "would otherwise be destroyed at the end of the full-expression" excludes three things. A temporary that is already extended (the one bound directly to `__range`) lives long enough anyway. A function parameter is not a temporary; when it is destroyed is specified separately by [[expr.call#7]]. Temporaries created inside a called function belong to a different full-expression.

The extended temporaries are destroyed together with `__range`, in the order given by [[class.temporary#11]]: the reverse of the order in which their construction completed.

```cpp run title="order.cpp" ok
#include <cstdio>
#include <vector>
struct T {
  const char* n;
  explicit T(const char* s) : n(s) { std::printf("  make %s\n", n); }
  ~T() { std::printf("  kill %s\n", n); }
};
struct Box {
  T tag{"Box"};
  std::vector<int> v{1, 2};
  const std::vector<int>& items() const { return v; }
};
Box make(const T&) { return {}; }
int main() {
  std::printf("before\n");
  for (int x : make(T{"arg"}).items())
    std::printf("  body %d\n", x);
  std::printf("after\n");
}
```

Under `-std=c++23`, Clang 23 prints `make arg`, `make Box`, `body 1`, `body 2`, `kill Box`, `kill arg`, in that order. The argument `T{"arg"}` would normally fall under the exception in [[class.temporary#6]], which says a temporary bound to a reference parameter in a function call lives until the end of the full-expression; now it is extended too. Compiled with `-std=c++20`, the same program destroys both objects in the same order before the loop starts. The loop body reads a `vector` that has already been freed, and in our run `body` was never printed at all.

### Related changes

To give multiple extended temporaries a well-defined destruction order, [[P2718R0]] also changed what is now [[class.temporary#11]]. The old wording only covered temporaries bound to references, destroyed in reverse order of construction. The objects extended by the new range-based for rule are not necessarily bound to a reference (`Box` in the example is not), so the wording now covers temporaries "with lifetimes extending beyond the full-expressions in which they were created".

[[stmt.ranged]] gained Note 2 and Example 2, which point to the new rule and mark its limits (see "What still dangles" below). [[diff.cpp20]] gained the incompatibility entry discussed above.

<details class="fine" markdown="1">
<summary>How the wording evolved</summary>

[[P2012R2]] wrote that such temporaries "persist until the completion of the statement". [[P2644R1]] added two restrictions: only temporaries that would otherwise be destroyed at the end of the full-expression are covered, and function parameter objects are excluded. After CWG review, [[P2718R0]] changed "persist until the completion of the statement" to "persist for the lifetime of the reference initialized by the initializer", which ties the destruction point directly to `__range` in the rewrite.

The P2718R0 wording says "a temporary object other than a function parameter object". Today's draft of [[class.temporary#7]] does not have that phrase. A parameter is not a temporary in the first place, so dropping it does not change the meaning. No document recording its removal could be found, so this only notes the difference.

The same idea was later applied to C++26 expansion statements: [[class.temporary#8]] and [[class.temporary#9]] give corresponding extension rules for the initializer of `template for`; see [[stmt.expand]].
</details>

## Consequences

### Compatibility and compiler support

The change went into the standard as a new C++23 feature, not as a defect report (DR) against earlier standards, so compilers only enable it in C++23 and later modes. The feature-test macro `__cpp_range_based_for` was updated to `202211L` accordingly ([[cpp.predefined]]).

Clang 23 behaves accordingly: under `-std=c++20` the macro is `201603` and all the examples above follow the old rule; under `-std=c++23` and `-std=c++2c` it is `202211` and they follow the new rule. Other compilers have not been checked here.

This means the same source code can behave differently in the two modes. A loop that is correct in C++23 is undefined behavior when compiled with `-std=c++20`, and in most cases the compiler will not warn. Libraries that must support both modes should still use the *init-statement* form.

### What still dangles

The rule only covers temporaries in the range-based for initializer that would otherwise be destroyed at the end of the full-expression. None of the following qualify.

The first case is by-value parameters. This is Example 2 in [[stmt.ranged]]:

```cpp run title="f2.cpp" ub
#include <list>
using T = std::list<int>;
const T& f1(const T& t) { return t; }
const T& f2(T t)        { return t; }
T g() { return {1, 2, 3}; }
int main() {
  int s = 0;
  for (int e : f1(g())) s += e;   // OK: the temporary from g() is extended
  for (int e : f2(g())) s += e;   // UB: returns a reference to parameter t
  return s;
}
```

Here there is no temporary to extend at all. Since C++17 the prvalue `g()` initializes the parameter `t` directly ([[dcl.init.general#15.6.1]]), with no temporary in between. `f2` returns a reference to `t`, and a parameter is not a temporary, so the new rule does not reach it. A parameter is destroyed either when the function returns or at the end of the full-expression (which one is implementation-defined, [[expr.call#7]]); either way, that is before the loop body. Clang warns with `-Wreturn-stack-address` at the definition of `f2`. Notably, running it with `-std=c++23` and ASan reported no error; the second loop just silently ran zero times. ASan staying quiet does not mean the program is correct.

The second case is anywhere outside range-based for. An ordinary declaration has no such special case:

```cpp
auto&& r = make().items();   // the temporary from make() is destroyed at the end of this line
for (int x : r) { }          // UB, in C++23 as well
```

This includes storing a view in a variable before iterating over it. In `auto v = load().items() | std::views::filter(p);`, `load().items()` is an lvalue, so `views::all` picks `ref_view`, which only stores a pointer, and the temporary is gone at the end of that declaration (see the opening example of [[topics/ranges-design|the ranges design topic]]). The same pipeline written directly in the range-based for initializer is safe in C++23.

The third case is temporaries inside a called function, and temporaries in the loop body. For example, a function that returns a `string_view` into its own local `std::string` dangles wherever it is called.

These all belong to the more general dangling problem, which [[topics/dangling-references|the topic page on dangling references]] sorts into categories. Range-based for is just the least visible case, which is why it got its own fix.

## Questions

!!! question "1. What is the behavior of this loop in C++20 and in C++23?"
    ```cpp
    std::string make();   // returns a fairly long string
    for (char c : std::string_view(make())) use(c);
    ```

<details markdown="1">
<summary>Answer</summary>

In C++20 it is undefined behavior. The temporary `string` returned by `make()` is used to construct a `string_view`. `__range` binds to the `string_view` temporary, and only that one is extended. The `string` is destroyed at the end of the initializer, leaving the `string_view` pointing at freed memory. With `-std=c++20`, Clang 23 gives a `-Wdangling-gsl` warning, and ASan reports `heap-use-after-free`.

From C++23 on, the `string` is a temporary in the initializer that would otherwise be destroyed at the end of the full-expression, so by [[class.temporary#7]] it lives until the loop ends and the loop is correct. With `-std=c++23` there is no warning and it runs normally.
</details>

!!! question "2. Change `for (int x : make().items())` to `for (auto&& r = make().items(); int x : r)`. Is it still safe in C++23?"

<details markdown="1">
<summary>Answer</summary>

No. The extension rule only applies to the *for-range-initializer*, the part to the right of the colon. The *init-statement* is an ordinary declaration: the temporary from `make()` is destroyed at its end, and `r` dangles. The C++20 workaround must store the object itself: `for (auto m = make(); int x : m.items())`.
</details>
