---
title: Exam 6 · New rules from C++20 to C++26
summary: 25 questions on the edges of rules added since C++20 - explicit object parameters, a few C++23 syntax relaxations, coroutine restrictions and parameter lifetimes, defaulted comparison and rewritten candidates, consteval and if consteval, exposures in modules, and C++26 erroneous behavior, the _ placeholder, pack indexing, structured binding packs and conditions, delete with a reason, static_assert messages, constexpr placement new, contracts and static reflection.
tags: exam, C++20, C++23, C++26, coroutines, defaulted comparison, consteval, modules, erroneous behavior, contracts, reflection
updated: 2026-10-20
---

!!! tldr
    - Scope: explicit object parameters ([[dcl.fct]]), C++23's `[[assume]]` and labels at the end of compound statements, coroutines ([[dcl.fct.def.coroutine]]), defaulted comparison and rewriting of `==` ([[class.compare.default]], [[over.match.oper]]), `if consteval` ([[expr.const.imm]]), exposures in module interfaces ([[basic.link]]), and C++26 erroneous behavior, `_`, pack indexing, structured bindings, `= delete("…")`, `static_assert` messages, constexpr placement new, contracts and reflection.
    - Lifetime, initialization, the classic rules of name lookup and overload resolution, templates, and the general rules of constant evaluation each have their own exam; this one cites them only where the new rules need them.
    - For quite a few questions the standard's verdict differs from what Clang 23 does: sometimes Clang only warns, sometimes the feature is not implemented yet. The explanations note each case; always answer according to the current draft.
    - Suggested time: 100 minutes. For verdict questions, give the most severe verdict for the whole program; choice questions that ask about output have all been checked by actually running them.

## 1. Explicit object parameters and small C++23 changes

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++23}} Judge the whole program.

```cpp run
struct Counter {
  int n = 0;
  int next(this Counter& self) {
    self.n += 1;
    return n;
  }
};

int main() {
  Counter c;
  return c.next();
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; `return n;` is not allowed.**

The first parameter of `next` is marked with `this`, so it is an explicit object member function ([[dcl.fct#8]]). The problem is the unqualified `n` in the function body.

1. [[expr.prim.id.general#2]]: when an *id-expression* denotes a non-static member of a class and appears within that class's scope, it is transformed into a class member access using `(*this)` as the object expression. `n` meets the condition and becomes `(*this).n`.
2. [[expr.prim.this#4]]: `this` shall not appear within the declaration of a static member function or an explicit object member function. The `this` produced by the transformation counts too, so the program is ill-formed. Note 2 in [[expr.prim.id.general#2]] points this out directly.

This is precisely the design of explicit object member functions: there is no `this` and no implicit member access in the body; everything goes through `self`. `self.n += 1` is valid, and changing `return n;` to `return self.n;` makes the program well-formed. Clang 23 reports invalid use of member 'n' in explicit object member function.

The other restrictions on explicit object parameters are in [[dcl.fct#7]]: it can only be the first parameter, and the function cannot have cv-qualifiers or a ref-qualifier, nor be declared `static` or `virtual`.

```cpp error
struct S {
  void a(this S&) const;     // error: cannot have a cv-qualifier
  virtual void b(this S&);   // error: cannot be virtual
  static void c(this S&);    // error: cannot be static
};
```

For background see [[papers/deducing-this]].

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

{{c++23}} Given the class below and `S s;`, which snippet is well-formed when placed in a function body?

```cpp
struct S {
  int v = 7;
  int get(this const S& s) { return s.v; }
  int via_this() const;
};
```

- A. `int (S::*p)() const = &S::get;`
- B. `auto p = &S::get; int r = (s.*p)();`
- C. `int (*p)(const S&) = &S::get; int r = p(s);`
- D. In the definition of `S::via_this`, write `auto p = &get; return p(*this);`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

[[expr.unary.op#3]] splits taking an address into two cases. ¶3.1 says that taking the address of a *qualified-id* naming a non-static member `m` yields a "pointer to member of class `C`", but explicit object member functions are explicitly excluded. So it falls under ¶3.2: the result is an ordinary "pointer to `T`", where `T` is the function type `int(const S&)`.

- C is correct: `&S::get` has type `int(*)(const S&)`, and the object is passed as the first argument.
- A is wrong: the types do not match; a pointer to member function requires a function without an explicit object parameter.
- B is wrong: `p` is not a pointer to member, and the right operand of `.*` must be a "pointer to member of `T`" ([[expr.mptr.oper#2]]). Clang reports right hand operand to .* has non-pointer-to-member type.
- D is wrong: the last sentence of ¶3.2 requires that when taking the address of an explicit object member function, the operand be a *qualified-id* or a *splice-expression*. A bare `&get` is not allowed; write `&S::get`. This is consistent with implicit object member functions, which form a pointer to member only when written `&S::f` ([[expr.unary.op#4]]).

From outside, an explicit object member function is still a non-static member function, called as `s.get()`; from the point of view of pointers, it behaves more like a static member function.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

{{c++23}} Judge the whole program. If it is well-formed, give the output.

```cpp run
#include <cstdio>

int main() {
  int i = 0;
  [[assume(++i == 1)]];
  std::printf("%d\n", i);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed; it prints `0`.**

[[dcl.attr.assume#1]] specifies three things:

1. The assumed expression is not evaluated, so `++i` does not happen, and `i` stays 0.
2. If the expression would evaluate to `true` at that point, the assumption has no effect. `i` is 0 here, so `++i == 1` would be `true`.
3. Only if it would evaluate to `false` does executing the statement have runtime-undefined behavior.

So there is neither a side effect nor UB here. The draft's own example `[[assume(++y == 43)]]` also notes that `y` is not incremented. Note 1 under ¶2 adds that the expression is still potentially evaluated, so variables used in it are still odr-used.

Clang 23 warns assumption is ignored because it contains (potential) side-effects, and prints 0 at both `-O0` and `-O2`.

Change the initial value to 1, and the assumption is false at that point, so the program has undefined behavior:

```cpp ub
int f() {
  int i = 1;
  [[assume(++i == 1)]];   // UB: would evaluate to false
  return i;
}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++23}} Judge the function below.

```cpp run
void f(bool b) {
  if (b) goto done;
  int n = 42;
  (void)n;
done:
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed. The label at the end is fine; the problem is jumping past the initialization of `n`.**

First the part new in C++23. The grammar in [[stmt.block#1]] is `{ statement-seq(opt) label-seq(opt) }`: a compound statement may end with labels that are not followed by a statement; [[stmt.label#1]] also says labels may appear anywhere in a compound statement. In C++20, `done:` had to be followed by a `;`.

Now the jump. [[stmt.dcl#2]] says that when control transfers from P to Q, automatic variables that are active at Q (in scope and past their point of declaration) but not at P are initialized in declaration order, and such a transfer shall not be a jump unless all of those variables have vacuous initialization. `done:` is within the scope of `n` and after its declaration, so `n` is active at Q but not at the `goto`. `int n = 42;` has an initializer and is not vacuous initialization (defined in [[basic.life#2]] as default-initialization with no other initialization performed), so the `goto` is ill-formed. Clang reports cannot jump from this goto statement to its label.

Remove the initializer and it is well-formed, even though in C++26 the value of `n` is an erroneous value (see question 14):

```cpp run ok
void f(bool b) {
  if (b) goto done;
  int n;
  (void)n;
done:
}
int main() { f(true); }
```

</details>
</div>

## 2. Coroutines

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++20}} Judge the whole program. `task` is a return type that meets the coroutine requirements, and its `promise_type` provides `return_void`.

```cpp
template<bool Early>
task work() {
  if constexpr (Early) {
    return task{{}};
  }
  co_return;
}

int main() { work<false>().run(); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

[[dcl.fct.def.coroutine#1]]: a function whose body contains `co_return`, `co_await` or `co_yield` is a coroutine. `work` contains `co_return`, so it is a coroutine whatever the value of `Early`.

[[stmt.return.coroutine#1]]: a coroutine shall not contain a `return` statement. The note that follows says that whether the `return` is in a discarded statement does not matter for this rule. So the `return` branch in `work<false>`, which is never instantiated, still makes the program ill-formed.

The tempting answer is well-formed, on the grounds that discarded branches are not instantiated. But whether a function is a coroutine and whether it has a `return` statement are both judged from the text of the body, not from the condition of `if constexpr`. Clang 23 reports return statement not allowed in coroutine; did you mean 'co_return'?

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

{{c++20}} Each of the four functions below has just `co_return;` as its body, and `task` meets the coroutine requirements. Which one can be a coroutine?

- A. `constexpr task a() { co_return; }`
- B. `task b(int, ...) { co_return; }`
- C. The constructor in `struct C { C() { co_return; } };`
- D. The function call operator of the closure type in `auto d = []() -> task { co_return; };`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: D.**

Checking each against the wording:

- A: [[dcl.constexpr#3]] says a coroutine is not constexpr-suitable, and a non-template constexpr function must be constexpr-suitable. Ill-formed.
- B: [[dcl.fct.def.coroutine#1]] requires that a coroutine's parameter list not end with an ellipsis that is not part of a parameter declaration, that is, it cannot be a C-style variadic function. Ill-formed. Note that the `...` in `template<class... Args> task g(Args&&...)` is a pack expansion and is not affected.
- C: [[class.ctor.general#6]]: a constructor shall not be a coroutine. Likewise for destructors ([[class.dtor#20]]), and `main` cannot be a coroutine either ([[basic.start.main#3]]).
- D: a lambda's function call operator is an ordinary member function, with no such restriction. Correct.

A has a subtlety: [[dcl.constexpr#3]] constrains only non-template constexpr functions, so the wording does not forbid a constexpr function template from being a coroutine; its instances just cannot be used in constant evaluation. Clang 23 also rejects `template<class T> constexpr task c(T) { co_return; }` with 'co_return' cannot be used in a constexpr function, which is stricter than the draft.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

{{c++20}} Judge the whole program. `task`'s `initial_suspend` returns `std::suspend_always`, `run()` calls `resume()`, and the destructor destroys the coroutine.

```cpp
#include <cstdio>
#include <string>
#include <string_view>

task greet(std::string_view name) {
  std::printf("hello, %.*s\n", int(name.size()), name.data());
  co_return;
}

int main() {
  task t = greet(std::string(40, 'x'));
  t.run();
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: undefined behavior.**

The parameter is passed by value, which looks safe, but only the `string_view` itself is copied into the coroutine frame.

1. [[dcl.fct.def.coroutine#13]]: when a coroutine is invoked, a copy is created for each parameter at the beginning of the replacement body. The copy of a non-reference parameter is direct-initialized from the original parameter (¶13.2); the copy of a reference parameter is a reference bound to the same object (¶13.1). The copy of `name` is a `string_view` pointing into the buffer of the caller's temporary `std::string`.
2. The coroutine suspends at its initial suspend point and control returns to `main`. The temporary `std::string` is destroyed at the end of the full-expression `task t = greet(...)` ([[class.temporary#4]]), and its buffer is freed.
3. `t.run()` resumes the coroutine, and the storage `name.data()` points to has reached the end of its duration. Indirection through a pointer value that is invalid in that evaluation is undefined behavior (¶6.1 of [[basic.compound#6]]).

Note 3 under ¶13 is exactly this warning: if a coroutine has a reference parameter, resuming it after the lifetime of the referenced entity has ended is likely to result in undefined behavior. By-value view types such as `string_view` and `span` have the same problem; the note just does not name them.

Running with `-fsanitize=address` in our tests, ASan reports heap-use-after-free. Change the parameter to `std::string name`, so the copy owns its own buffer, and the program prints normally.

```cpp ok
task greet(std::string name) {   // the copy owns the data
  std::printf("hello, %s\n", name.c_str());
  co_return;
}
```

For more dangling scenarios see [[topics/dangling-references]] and [[topics/coroutines]].

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

{{c++23}} Both member coroutines below are called on a temporary, with the result saved immediately and resumed later (`task` as in the previous question, initially suspended). Decide for `a.run()` and `b.run()` whether there is undefined behavior, and explain the difference with the rules for copying coroutine parameters.

```cpp
struct Widget {
  std::string name = std::string(40, 'w');
  task show() { std::printf("%s\n", name.c_str()); co_return; }
  task show_copy(this Widget self) { std::printf("%s\n", self.name.c_str()); co_return; }
};

int main() {
  task a = Widget{}.show_copy();
  a.run();
  task b = Widget{}.show();
  b.run();
}
```

<details class="quiz-key" markdown="1"><summary>Key points</summary>

**Key points: `a.run()` is well-formed with defined behavior; `b.run()` is undefined behavior.**

1. `show` is an implicit object member function. Per [[dcl.fct.def.coroutine#4]], its q1 is an lvalue denoting `*this`, not a parameter that gets copied. [[dcl.fct.def.coroutine#13]] creates copies only for function parameters, and the implicit object parameter is not a function parameter (it is not even in the parameter-type-list), so the coroutine frame stores only the value of the `this` pointer.
2. The temporary `Widget` is destroyed at the end of the full-expression `task b = Widget{}.show();` ([[class.temporary#4]]). Accessing `name` after resumption accesses an object whose lifetime has ended: undefined behavior.
3. The object parameter of `show_copy` is a written-out by-value parameter `Widget self`. It is an ordinary function parameter, so ¶13.2 applies: the coroutine frame holds a copy direct-initialized (move-constructed) from `self`, and `self` in the function body refers to that copy ([[expr.prim.id.unqual#5]]). Destroying the temporary does not affect the copy, and `a.run()` prints normally.
4. Written as `this Widget& self` or `this const Widget& self`, the copy is again just a reference (¶13.1) and dangles just like `show`.

In our tests ASan reports stack-use-after-scope for `b.run()`, and running the `a` part alone prints 40 `w`s. Note that when ASan aborts, `a`'s output may still be sitting in the stdout buffer and never get flushed.

This shows that explicit object parameters are not only for deducing `Self`: a by-value object parameter lets a coroutine own its object.

</details>
</div>

## 3. Comparison, consteval and modules

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++20}} Judge the class definition below.

```cpp run
struct P {
  int x, y;
  bool operator==(P) const = default;
};
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed.**

¶1.3 of [[class.compare.default#1]] requires a defaulted comparison operator function to have either two parameters of type `const C&` or two parameters of type `C`, counting the implicit object parameter (if any) as the first parameter.

The implicit object parameter of a `const` member function has type `const P&` ([[over.match.funcs.general#4]]), while the second parameter is `P`. They differ, so ¶1.3 is not satisfied. Clang 23 reports invalid parameter type for defaulted equality comparison operator; found 'P', expected 'const P &'.

There are two fixes: as a member, write `bool operator==(const P&) const = default;`; or make it a friend, `friend bool operator==(P, P) = default;`, where both parameters are `P` and passing by value is allowed. Conversely, `bool operator==(const P&) = default;` without the `const` is also ill-formed, because the implicit object parameter becomes `P&`.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

{{c++20}} Which of the four functions below are ill-formed?

```cpp
#include <compare>

struct Ver {
  int major, minor;
  auto operator<=>(const Ver&) const = default;
  bool operator==(int m) const { return major == m; }
};

bool lt(Ver a, Ver b) { return a < b; }
bool eq(Ver a, Ver b) { return a == b; }
bool ne(Ver a, Ver b) { return a != b; }
bool eqi(Ver a) { return a == 1 && 1 == a; }
```

- A. Only `eq`
- B. `eq` and `ne`
- C. `eq`, `ne` and `eqi`
- D. All are well-formed

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: B.**

1. [[class.compare.default#4]]: a defaulted `operator==` is implicitly declared for a defaulted `operator<=>` only if the class's member-specification does not explicitly declare any member or friend named `operator==`. `Ver` declares `operator==(int)`, so no `operator==(const Ver&)` is generated.
2. `a == b`: `==` is never rewritten to `<=>`. The only candidates are `operator==(int)` and its reversed form; `Ver` does not convert to `int`, so neither is viable. Ill-formed.
3. `a != b`: per ¶3.4.3 of [[over.match.oper#3]], the rewritten candidates for `!=` come from the candidates for `x == y`, again only `operator==(int)`, not viable. Ill-formed.
4. `a < b`: the rewritten candidates for relational operators include `x <=> y` (¶3.4.1); the defaulted `<=>` is viable. Well-formed.
5. `eqi`: `a == 1` calls the member directly; `1 == a` uses the reversed synthesized candidate (¶3.4.4), also viable. Well-formed.

Clang 23 reports invalid operands to binary expression ('Ver' and 'Ver') for `eq` and `ne`. Adding `bool operator==(const Ver&) const = default;` makes everything well-formed.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++20}} Judge the whole program (by the standard, ignoring compiler extensions).

```cpp run
struct Id {
  int v;
  int operator==(const Id& o) const { return v == o.v; }
};

int main() {
  Id a{1}, b{2};
  return a != b;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed. Clang only gives a warning.**

`Id` has no `operator!=`. Per ¶3.4.3 of [[over.match.oper#3]], the rewritten candidates for `a != b` include the non-rewritten candidates for `a == b`, so `Id::operator==` is selected.

[[over.match.oper#10]]: if overload resolution selects a rewritten `operator==` candidate, its return type shall be cv `bool`, and then `x != y` is interpreted as `!(x == y)`. Here it returns `int`, violating this "shall", so the program is ill-formed.

Why the rule? Rewriting hands the result to the built-in `!`, and the standard does not want `!` applied to arbitrary types via user-defined conversions. Writing `a == b` directly involves no rewriting, and returning `int` is fine there.

Clang 23 only gives the `-Wrewrite-not-bool` warning, ISO C++20 requires return type of selected 'operator==' function for rewritten '!=' comparison to be 'bool', not 'int', and compiles anyway. This is an extension for compatibility with old code.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++23}} Judge the whole program.

```cpp run
consteval int sq(int x) { return x * x; }

constexpr int area(int side) {
  if !consteval {
    return side * side;
  }
  return sq(side);
}

int main() {
  static_assert(area(4) == 16);
  int n = 5;
  return area(n);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; `return sq(side);` is not in an immediate function context.**

Intuitively, `return sq(side);` can only run at compile time, because at run time the function has already returned from the `if !consteval` branch. But the rule looks at syntactic position, not control flow.

1. [[stmt.if#6]]: `if ! consteval { A }` is not itself a consteval if statement; it is equivalent to `if consteval { } else { A }`.
2. [[expr.const.imm#1]]: only expressions in the first substatement of a consteval if statement (the compound statement following `if consteval`) are in an immediate function context (¶1.3). `return sq(side);` is outside the `if` statement, so that does not hold; `area` is not an immediate function either, so ¶1.1 does not hold.
3. So `sq(side)` is an immediate invocation. `side` is a function parameter, so it is not a constant expression, and per ¶2.2 of [[expr.const.imm#2]] it is an immediate-escalating expression.
4. The last sentence of [[expr.const.imm#3]]: an immediate-escalating expression shall appear only in an immediate-escalating function. `area` is a non-template, user-written constexpr function, none of the three kinds listed in ¶3, so the program is ill-formed.

Clang 23 reports call to consteval function 'sq' is not a constant expression. Putting `sq(side)` in an else branch makes it well-formed, because `if !consteval { A } else { B }` is equivalent to `if consteval { B } else { A }`:

```cpp run ok
consteval int sq(int x) { return x * x; }
constexpr int area(int side) {
  if !consteval {
    return side * side;
  } else {
    return sq(side);      // in the first substatement of a consteval if
  }
}
int main() { static_assert(area(4) == 16); int n = 5; return area(n); }
```

If `area` were a function template, its instances would be immediate-escalating functions (¶3.3) and would escalate to immediate functions (¶4.2), moving the error to the call `area(n)`: it becomes an immediate invocation that is not a constant expression. Clang reports call to immediate function 'area<int>' is not a constant expression for that version.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++20}} Judge the module interface unit below.

```cpp
export module geom;

namespace {
  int scale(int x) { return 2 * x; }
}

inline int area(int w, int h) { return scale(w) * h; }

export int volume(int w, int h, int d) { return area(w, h) * d; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; the definition of `area` exposes the TU-local entity `scale`. Clang only gives a warning.**

1. An unnamed namespace has internal linkage, and so does `scale` declared in it ([[basic.link#4]]). A function with a name having internal linkage is a TU-local entity (¶15.1.1 of [[basic.link#15]]).
2. [[basic.link#14]]: a declaration is an exposure if it names a TU-local entity. The function body of a non-inline function is ignored for this purpose (¶14.1), but the body of an inline function is not. `area` is an inline function whose body names `scale`, so the definition of `area` is an exposure.
3. `area` is not exported, but it is in the module's interface unit and has module linkage, so it is not TU-local. [[basic.link#17]]: if a declaration of a non-TU-local entity in a module interface unit is an exposure, the program is ill-formed.

Why? The definition of an inline function must be usable in translation units that import it, and those cannot refer to an internal-linkage function of another translation unit. It is easy to think only `export`ed declarations are checked, but this rule covers every non-TU-local entity in the interface unit.

Remove `inline` and the body is ignored when computing exposures, so the program is well-formed; the same goes for the body of `volume`. Clang 23 only gives the `-WTU-local-entity-exposure` warning TU local entity 'scale' is exposed for the code above; with `inline` removed it compiles even with `-Werror`.

</details>
</div>

## 4. C++26: values, names, packs and constant evaluation

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

{{c++26}} The four functions below are independent and each is called once. Which one has undefined behavior (not erroneous behavior)?

```cpp
int a() { int x; int y = x; return y; }

unsigned char b() {
  unsigned char* p = new unsigned char;
  unsigned char c = *p;
  delete p;
  return 0;
}

int c() { int* q = new int; int d = *q; delete q; return d; }

int d() { unsigned char e; int f = e; return f; }
```

- A. `a`
- B. `b`
- C. `c`
- D. `d`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

[[basic.indet#1]] distinguishes initial values by storage duration: objects with dynamic storage duration, and variables marked `[[indeterminate]]`, have bytes with indeterminate values; other objects with automatic storage duration have bytes with erroneous values, chosen by the implementation independently of the state of the program.

[[basic.indet#2]] then says: an evaluation that produces an indeterminate value is undefined behavior; one that produces an erroneous value is erroneous behavior, and the result is that erroneous value. Unsigned narrow character types and `std::byte` have a few exceptions.

- `a`: `x` is an automatic variable whose value is erroneous; `int y = x;` is erroneous behavior {{erroneous}}.
- `b`: `*p` is an indeterminate value, but it is an `unsigned char`, and using it to initialize an `unsigned char` object falls under the exception in ¶2.3: `c` also gets an indeterminate value, with no UB.
- `c`: `*q` is an `int` with dynamic storage duration whose value is indeterminate; reading it is undefined behavior {{ub}}.
- `d`: `e` holds an erroneous value. Converting it to `int` is not among the exceptions and produces an erroneous value, so it is erroneous behavior. The draft's example `int e = d;` is also marked erroneous behavior.

C++26 did not make every uninitialized read erroneous: objects on the heap and `[[indeterminate]]` variables are still UB. That is also what `[[indeterminate]]` is for: it buys back the old semantics, and with them the old risks ([[dcl.attr.indet#1]]).

Clang 23 does not recognize `[[indeterminate]]` (unknown attribute warning) and gives `-Wuninitialized` warnings for `a` and `d`; neither ASan nor UBSan reports anything for `c`, since UB is not guaranteed to be observable. See [[papers/erroneous-behaviour]].

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

{{c++26}} Which declaration below is ill-formed?

- A. `struct S { int _; int _; };`
- B. `void f() { auto [_, _] = std::pair{1, 2}; }`
- C. `void f(int _, int _) {}`
- D. `void f() { static int _; int _; }`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: C.**

[[basic.scope.scope#6]]: if two declarations A (earlier) and B (later) in the same scope potentially conflict, the program is ill-formed unless B is name-independent. [[basic.scope.scope#5]] lists which declarations named `_` are name-independent:

- ¶5.1: a variable with automatic storage duration, except a function parameter;
- ¶5.2: a structured binding with no storage-class specifier, not at namespace scope;
- ¶5.3: a result binding (the `post(r: …)` of a contract);
- ¶5.4: a variable introduced by an *init-capture*;
- ¶5.5: a non-static data member (other than a member of an anonymous union).

Item by item:

- A: non-static data members fall under ¶5.5; well-formed. A later `s._` would just be ambiguous.
- B: structured bindings fall under ¶5.2; well-formed.
- C: function parameters are explicitly excluded by ¶5.1; the second `_` conflicts with the first, so it is ill-formed. Clang reports redefinition of parameter '_'.
- D: the easy one to get wrong. The rule only requires the later declaration B to be name-independent. Here A is `static int _` (static storage duration, not name-independent) and B is the automatic variable `int _`, which is name-independent, so it is well-formed. In the reverse order it is ill-formed; the draft's example `int _; static int _;` is marked as an error.

Declarations may repeat, but uses may not. After the second `_` is introduced, writing `_` makes name lookup find two declarations, neither of which is a function, and the result is ambiguous ([[basic.lookup.general#1]]; note 3 under ¶6). Question 25 relies on this.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++26}} Judge the whole program.

```cpp run
template<class... T>
auto first(T...[0] x) { return x; }

int main() {
  return first(42);
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; there is no viable function for `first(42)`.**

1. `T...[0]` is a pack-index-specifier ([[dcl.type.pack.index]]). By ¶5.2 of [[temp.deduct.type#5]], a pack index is a non-deduced context, so the argument `42` cannot be used to deduce `T`.
2. `T` appears only in a non-deduced context and is not explicitly specified. [[temp.deduct.type#4]] says deduction then fails; even if the trailing pack were deduced as empty per the note in [[temp.arg.explicit#4]], substituting into `T...[0]` would then fail because the index 0 does not satisfy 0 ≤ V < `sizeof...(T)` from [[dcl.type.pack.index#2]].
3. The only candidate is not viable, and the call is ill-formed.

Clang 23 reports no matching function for call to 'first', with the note substitution failure [with T = <>]: invalid index 0 for pack 'T' of size 0.

Giving the template argument explicitly makes it well-formed:

```cpp run ok
template<class... T>
auto first(T...[0] x) { return x; }
int main() { return first<int>(42); }
```

For why the proposal does not let pack indexing take part in deduction, and how the meaning of an unnamed parameter `T...[n]` changed in C++26, see [[papers/pack-indexing]].

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++26}} Judge the whole program.

```cpp run
#include <tuple>

int sum3() {
  auto [...xs] = std::tuple{1, 2, 3};
  return (xs + ...);
}

int main() { return sum3(); }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; a structured binding pack can only appear in a templated entity.**

`...xs` is a structured binding pack ([[temp.variadic#4]]). In itself it is fine: the structured binding size is 3, and the pack contains three structured bindings ([[dcl.struct.bind#2]]).

The problem is [[dcl.pre#7]]: if a structured binding declaration contains an *sb-identifier* with an ellipsis, it shall declare a templated entity. Per [[temp.pre#8]], templated entities include templates, entities defined in templated entities, entities defined in expansion statements, and so on. `sum3` is an ordinary function, and the variables in it are not templated entities, so it is ill-formed. Clang 23 reports pack declaration outside of template.

This restriction lets the compiler always handle packs within the framework of template instantiation. Inside a generic lambda it is well-formed, since the lambda's function call operator is a template:

```cpp run ok
#include <tuple>
int sum3() {
  auto f = [](auto t) { auto [...xs] = t; return (xs + ...); };
  return f(std::tuple{1, 2, 3});
}
int main() { return sum3(); }   // returns 6
```

By ¶8.2, entities defined in the body of a `template for` are also templated, so a structured binding pack in an expansion statement inside an ordinary function is valid too. Clang 23 crashes when compiling that form, so no code is given for it here.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

{{c++26}} What does the program print?

```cpp run
#include <cstdio>
#include <tuple>

struct R {
  int code, value;
  explicit operator bool() const { std::puts("bool"); return code == 0; }
};
template<std::size_t I> int get(const R& r) {
  std::puts("get");
  return I == 0 ? r.code : r.value;
}
template<> struct std::tuple_size<R> : std::integral_constant<std::size_t, 2> {};
template<std::size_t I> struct std::tuple_element<I, R> { using type = int; };

R parse() { return {0, 7}; }

int main() {
  if (auto [code, value] = parse())
    std::printf("%d %d\n", code, value);
}
```

- A. `bool`, `get`, `get`, `0 7` (one per line)
- B. `get`, `get`, `bool`, `0 7`
- C. `get`, `get`, `0 7`, with `operator bool` never called
- D. Compilation fails: a structured binding cannot be used as a condition

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: A.**

C++26 allows a structured binding declaration in a condition (the *condition* grammar in [[stmt.pre]]).

1. Which value is tested? [[stmt.pre#6]]: the value of a condition that is not an expression is the value of the decision variable contextually converted to `bool`. [[dcl.struct.bind#4]]: when a structured binding declaration is a condition, the decision variable is the introduced unnamed variable *e*, that is, the whole `R` object, not `code` or `value`. So `R::operator bool` is called; `explicit` does not prevent a contextual conversion.
2. In what order? `R` specializes `tuple_size`, so it is bound in the tuple-like way. [[dcl.struct.bind#7]] says the initialization of *e* and any conversion of *e* considered as a decision variable are sequenced before the initialization of any ri, that is, before the calls to `get`. So `bool` is printed first, then `get` twice.

B reflects the intuition that a structured binding is unpacked first and tested afterward. C assumes the first binding is what gets tested. The order is deliberate: if the conversion yields false, the object is often in a state that cannot be decomposed (for example, a result type representing failure), and `get` should not be called.

Running it with Clang 23 gives the output in A.

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++26}} Judge the whole program.

```cpp run
int legacy(int) = delete("use modern(int) instead");
long legacy(long);

constexpr auto n = sizeof(legacy(0L));
constexpr auto m = sizeof(legacy(0));

int main() { return n + m; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; `sizeof(legacy(0))` refers to a deleted function.**

1. Overload resolution for `legacy(0L)` selects `legacy(long)`; no problem.
2. `legacy(0)` selects the exact match `legacy(int)`. Deleted functions still take part in overload resolution; deletion is checked only after selection.
3. [[dcl.fct.def.delete#2]]: a construct that refers to a deleted function implicitly or explicitly, other than to declare it or as the operand of a reflection expression `^^`, is ill-formed. Note 1 says this applies even to expressions that are not potentially evaluated. The operand of `sizeof` is unevaluated, but it is still ill-formed.

What C++26 adds is the string in parentheses: an *unevaluated-string*, and the "recommended practice" in ¶2 suggests that the diagnostic include its text. Clang 23 reports call to deleted function 'legacy': use modern(int) instead.

Another restriction: a deleted definition must be the first declaration of the function ([[dcl.fct.def.delete#4]]), with or without a reason.

```cpp error
void f();
void f() = delete("no");   // error: deleted definition must be first declaration
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

{{c++26}} Judge the whole program (by the standard, ignoring the compiler's default diagnostic settings).

```cpp run
#include <cstddef>

struct Msg {
  std::size_t size() const;
  const char* data() const;
};

static_assert(sizeof(long) >= sizeof(int), Msg{});

int main() {}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: well-formed.**

C++26 allows the second operand of `static_assert` to be an expression, not just a string literal.

1. [[dcl.pre#12]]: if the message is not a string literal, it must be an expression M such that `M.size()` is implicitly convertible to `std::size_t` and `M.data()` is implicitly convertible to "pointer to `const char`". These are only type requirements, and `Msg` meets them: both member functions are declared with the right return types; whether they are defined or constexpr does not matter.
2. [[dcl.pre#13]]: if the condition is true, the declaration has no effect and the message is an unevaluated operand. Only when the assertion fails does ¶13.2 require `M.size()` to be a constant expression and `M.data()` a core constant expression.
3. Per [[basic.fundamental#1]], `long int` provides at least as much storage as `int`, so `sizeof(long) >= sizeof(int)` is always true; the message is never evaluated and need not be a constant expression.

Clang 23 reports the message in this static assertion is not a constant expression under `-Winvalid-static-assert-message`. This diagnostic is a warning that defaults to an error; with `-Wno-invalid-static-assert-message` it compiles. Clang checks the message even when the condition is true, which is stricter than the draft.

When the assertion fails, the message must be computable at compile time; then `Msg{}` does not satisfy ¶13.2, Clang reports the message in a static assertion must be produced by a constant expression, and the program is of course ill-formed as well.

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

{{c++26}} Which of the four functions below can be called in a constant expression (for example, `constexpr int r = a();`)?

```cpp
#include <memory>
#include <new>

constexpr int a() {
  std::allocator<int> al;
  int* p = al.allocate(1);
  int* q = ::new (p) int(42);
  int r = *q;
  al.deallocate(p, 1);
  return r;
}

constexpr int b() {
  std::allocator<double> al;
  double* p = al.allocate(1);
  int* q = ::new (static_cast<void*>(p)) int(42);
  int r = *q;
  al.deallocate(p, 1);
  return r;
}

int g = 0;
constexpr int c() { return *::new (&g) int(42); }

constexpr int d() {
  std::allocator<int> al;
  int* p = al.allocate(1);
  return *::new (p) int(42);
}
```

- A. `a`
- B. `b`
- C. `c`
- D. `d`

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: A.**

C++26 allows non-allocating placement new in constant evaluation. The conditions are in ¶2.20.2 of [[expr.const.core#2]]: with E the expression being evaluated and T the allocated type,

- ¶2.20.2.1: the object pointed to by the placement argument is transparently replaceable by the new object ([[basic.life#9]]);
- ¶2.20.2.2: the storage pointed to by the placement argument has a duration that began within the evaluation of E.

One by one:

- `a`: `allocate(1)` returns a pointer to the first element of an array of `int` ([[allocator.members#3]]) whose lifetime has not begun. Creating an `int` there makes the new object that array element per [[intro.object#2]], transparently replacing the original element. The storage is allocated in E and also freed in E (¶2.22, ¶2.23). It is a constant expression.
- `b`: the storage was allocated for `double`, and the new object is an `int`. The types differ, so it does not become the array element (¶2.4 of [[intro.object#2]]) and is not a corresponding direct subobject of the original `double` element; the original element is not a complete object either, so neither case of [[basic.life#9]] holds. It is not transparently replaceable, violating ¶2.20.2.1. Clang 23's note is placement new would change type of storage from 'double' to 'int'.
- `c`: the storage duration of `g` began at program start, not within E, violating ¶2.20.2.2. Clang 23's note is a constant expression cannot modify an object that is visible outside that expression.
- `d`: the allocated storage is not freed within E, violating ¶2.22. Clang 23's note is allocation performed here was not deallocated.

Clang 23 already implements constexpr placement new, and all four judgments above match it. Throwing and catching exceptions during constant evaluation, also new in C++26, is not yet implemented in Clang 23; see [[papers/constexpr-exceptions]].

</details>
</div>

## 5. C++26: contracts and static reflection

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++26}} Judge the two declarations below.

```cpp
int add_nonneg(int x, int delta)
  pre(delta >= 0)
  post(r : r >= x);

int add_nonneg(int x, int delta) { return x + delta; }
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; the postcondition uses the non-`const` by-value parameter `x`.**

1. The second declaration has no contract specifiers, which is allowed ([[dcl.contract.func#4]]: a declaration that is not the first may omit them or repeat exactly the same sequence).
2. [[dcl.contract.func#7]]: if the predicate of a postcondition of function *f* odr-uses a non-reference parameter of *f*, that parameter and the corresponding parameter in all declarations of *f* shall have `const` type. `post(r : r >= x)` odr-uses `x`, and `x` is `int` in both declarations: ill-formed.
3. Using `delta` in `pre(delta >= 0)` is fine; ¶7 constrains only postconditions.

Why? A postcondition is evaluated when the function returns and sees the parameter's value at that time. If the function body modified `x`, `r >= x` would no longer compare against the value the caller passed in, and the postcondition would silently lose its meaning. Requiring `const` rules this out. Note 4 stresses that the requirement also applies to declarations that do not spell out the postcondition, so both places must change:

```cpp
int add_nonneg(const int x, int delta)
  pre(delta >= 0)
  post(r : r >= x);

int add_nonneg(const int x, int delta) { return x + delta; }
```

At the time of writing, Clang 23 does not implement contracts and reports expected function body after function declarator on `pre(`, so this question and the other contract code in this section have not been compiled; the verdicts rest on the draft wording. For the design background see [[papers/contracts]].

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++26}} Judge the whole program.

```cpp
#include <meta>

[:^^int:] g = 1;

int main() {
  [:^^int:] n = g;
  return n;
}
```

<details class="quiz-key" markdown="1"><summary>Answer and explanation</summary>

**Answer: ill-formed; the `[:^^int:] n = g;` in `main` cannot be a declaration.**

`^^int` is a reflection of `int`, and `[: … :]` is a splice. The question is when a splice is treated as a type.

1. [[dcl.type.splice#1]]: a splice-specifier without a leading `typename` is interpreted as a *splice-type-specifier* only in a type-only context.
2. [[temp.res.general#4]] lists the type-only contexts. ¶4.4.1 includes a *decl-specifier* of a *simple-declaration* at namespace scope, and the last sentence of ¶4 says a splice-specifier is treated like a qualified name in the same position, so the first line `[:^^int:] g = 1;` is a declaration and is well-formed. A simple declaration at block scope is not on the list.
3. So the `[:^^int:]` in `main` can only be a splice expression. It designates a type, and ¶2.7 of [[expr.prim.splice#2]] says that if what is spliced is not a function, object, variable, value or the like, the expression is ill-formed.

This is the same reason `T::type` needs `typename`: inside a function body, the compiler cannot know in advance whether a construct that depends on a constant value is a type or an expression, so it parses it as an expression by default. Writing `typename [:^^int:] n = g;` makes it well-formed; the draft's example `typename [:^^S::type:] *var;` is written the same way.

At the time of writing, Clang 23 does not implement reflection: libc++ has no `<meta>` header, and `^^` is parsed as Clang's blocks extension, so this question has not been compiled. See [[papers/reflection]].

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

{{c++26}} The program below calls `f(-1)`, and the precondition does not hold. For each of the four evaluation semantics ignore, observe, enforce and quick-enforce, describe how the program may execute and what `checks` may end up as, and say who decides the semantic.

```cpp
#include <cstdio>

int checks = 0;
bool audit(int v) { ++checks; return v > 0; }

int f(int v) pre(audit(v)) { return v; }

int main() {
  f(-1);
  std::printf("%d\n", checks);
}
```

<details class="quiz-key" markdown="1"><summary>Key points</summary>

**Key points: the implementation decides the semantic; under ignore the output is 0; under observe the contract-violation handler is called and execution continues, and `checks` may be 0, 1 or more; under enforce and quick-enforce the program terminates and prints nothing.**

First confirm the program is well-formed. The `v` named directly in the predicate is treated as `const int` per [[expr.prim.id.unqual#7]], but `audit(v)` passes it by value and does not modify it; `audit` modifying a global variable is not restricted, since the const-ification applies only to names appearing directly in the predicate.

1. Which semantic? [[basic.contract.eval#2]]: which semantic is used for each evaluation is implementation-defined, and different evaluations of the same assertion may differ. ¶3 recommends that implementations provide options to make all evaluations use ignore and to make them all use enforce, with enforce as the default.
2. ignore: per [[basic.contract.eval#4]] the evaluation has no effect; the predicate is not evaluated and `audit` is not called. The function returns normally and `0` is printed.
3. What the checking semantics share: [[basic.contract.eval#5]] says it is unspecified whether the predicate is actually evaluated; the implementation may determine its value in another way that has no side effects and gives the same result. In addition, per [[expr.call#8]], preconditions are evaluated in sequence, and [[basic.contract.eval#18]] allows each assertion to be repeated an implementation-defined number of times. So under a checking semantic, `audit` may be called 0, 1 or more times.
4. observe: the predicate is false, a contract violation occurs (¶7.1), and the contract-violation handler is invoked (¶11). If the handler returns normally, execution continues (note 10 under ¶14); `f` returns −1 and the value of `checks` is printed, which by point 3 may be 0, 1 or more.
5. enforce: the contract-violation handler is invoked as well. If it returns normally, the program is contract-terminated (¶13), meaning `std::terminate` or `std::abort` is called or execution ends directly, which one being implementation-defined (¶9); nothing is printed. The handler may also throw, in which case the effect is as if the exception were thrown from the body of `f` (¶17).
6. quick-enforce: the contract-violation handler is not called; the program is contract-terminated directly (¶10), and nothing is printed.

So a program whose predicates have side effects is not portable: its output depends on the semantic the implementation chooses and on how many times the predicate is evaluated. This is also why the `assert(++nIter < 6)` discussed in [[papers/contracts]] has to be adjusted when rewritten as a contract.

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

{{c++26}} A synthesis question. Judge #1, #2 and #3 line by line and give the verdict for the whole program; then say what happens if the last line is changed to `double s = pick(1);` (with the other problems fixed).

```cpp run
#include <tuple>

template<class... Ts>
auto pick(Ts... xs) {
  auto [_, ...rest] = std::tuple{xs...};   // #1
  int _ = 0;                                // #2
  return rest...[0] + _;                    // #3
}

double r = pick(1, 2.5);
```

<details class="quiz-key" markdown="1"><summary>Key points</summary>

**Key points: #1 and #2 are well-formed, #3 is ill-formed, so the whole program is ill-formed. After changing to `pick(1)`, `rest` is an empty pack, `rest...[0]` is out of range, and instantiation fails.**

1. #1: the structured binding declaration has the pack `...rest`, and it is in a function template, hence a templated entity, satisfying [[dcl.pre#7]] (compare question 17). The first binding is named `_`, which per ¶5.2 of [[basic.scope.scope#5]] is a name-independent declaration. For `pick(1, 2.5)` the structured binding size is 2; `_` binds to `1` and `rest` contains one element, `2.5` ([[dcl.struct.bind#2]]).
2. #2: another automatic variable `_` is declared. It potentially conflicts with the `_` from #1, but it is itself a name-independent declaration (¶5.1), so per [[basic.scope.scope#6]] it is well-formed.
3. #3: `rest...[0]` is a pack-index expression, and the index 0 is less than `sizeof...(rest)`, which is 1, so it is valid ([[expr.prim.pack.index#2]]). The problem is `_`: there are now two variable declarations named `_` in scope; name lookup finds two declarations, neither a function and denoting different entities, so the result is ambiguous and ill-formed ([[basic.lookup.general#1]]; note 3 in [[basic.scope.scope#6]]). `_` does not depend on a template parameter, so this can be diagnosed at template definition time. Clang 23 reports ambiguous reference to placeholder '_', which is defined multiple times.
4. Change to `pick(1)` and drop the `+ _`: the structured binding size is 1, `_` binds to `1`, and `rest` is an empty pack, which is allowed. But `rest...[0]` requires 0 < `sizeof...(rest)`, i.e. 0 < 0, which fails [[expr.prim.pack.index#2]], so the instantiation of `pick<int>` is ill-formed. This happens in the function body, not while substituting into the function type, so it is a hard error, not SFINAE. Clang 23 reports invalid index 0 for pack 'rest' of size 0.

This question shows the design trade-off behind `_`: you can declare as many names you never use as you like, but once you have declared a second one, you can no longer read any of them.

</details>
</div>

## Clauses at a glance

| No. | Topic | Clauses |
|---|---|---|
| 1 | Implicit member access in an explicit object member function | [[expr.prim.id.general#2]], [[expr.prim.this#4]], [[dcl.fct#7]] |
| 2 | The address of an explicit object member function is an ordinary function pointer | [[expr.unary.op#3]], [[expr.mptr.oper#2]] |
| 3 | The expression of `[[assume]]` is not evaluated | [[dcl.attr.assume#1]] |
| 4 | Labels at the end of a compound statement; jumping past an initialized declaration | [[stmt.block#1]], [[stmt.dcl#2]], [[basic.life#2]] |
| 5 | A `return` in a discarded statement still makes a coroutine ill-formed | [[dcl.fct.def.coroutine#1]], [[stmt.return.coroutine#1]] |
| 6 | Which functions cannot be coroutines | [[dcl.fct.def.coroutine#1]], [[dcl.constexpr#3]], [[class.ctor.general#6]] |
| 7 | Coroutine parameter copies and by-value views | [[dcl.fct.def.coroutine#13]], [[class.temporary#4]], [[basic.compound#6]] |
| 8 | The implicit object parameter is not copied; by-value explicit object parameters | [[dcl.fct.def.coroutine#4]], [[dcl.fct.def.coroutine#13]] |
| 9 | Parameter types of defaulted comparison operators | [[class.compare.default#1]] |
| 10 | A user-declared `operator==` suppresses the implicit `==` | [[class.compare.default#4]], [[over.match.oper#3]] |
| 11 | A rewritten `!=` requires `operator==` to return `bool` | [[over.match.oper#3]], [[over.match.oper#10]] |
| 12 | `if !consteval` and immediate function contexts | [[stmt.if#6]], [[expr.const.imm#1]], [[expr.const.imm#3]] |
| 13 | An inline function in a module interface exposing a TU-local entity | [[basic.link#14]], [[basic.link#15]], [[basic.link#17]] |
| 14 | Erroneous versus indeterminate values; the unsigned narrow character exceptions | [[basic.indet#1]], [[basic.indet#2]] |
| 15 | Name-independent declarations | [[basic.scope.scope#5]], [[basic.scope.scope#6]] |
| 16 | Pack indexing is a non-deduced context | [[temp.deduct.type#5]], [[dcl.type.pack.index#2]] |
| 17 | Structured binding packs only in templated entities | [[dcl.pre#7]], [[temp.pre#8]] |
| 18 | Structured bindings as conditions: the decision variable and evaluation order | [[stmt.pre#6]], [[dcl.struct.bind#4]], [[dcl.struct.bind#7]] |
| 19 | Deletion with a reason; no references even in unevaluated contexts | [[dcl.fct.def.delete#2]], [[dcl.fct.def.delete#4]] |
| 20 | A `static_assert` message is not evaluated when the condition is true | [[dcl.pre#12]], [[dcl.pre#13]] |
| 21 | Placement new in constant evaluation | [[expr.const.core#2]], [[basic.life#9]], [[intro.object#2]] |
| 22 | By-value parameters used in a postcondition must be `const` | [[dcl.contract.func#4]], [[dcl.contract.func#7]] |
| 23 | A splice at block scope is an expression by default | [[dcl.type.splice#1]], [[temp.res.general#4]], [[expr.prim.splice#2]] |
| 24 | The four contract evaluation semantics | [[basic.contract.eval#2]], [[basic.contract.eval#5]], [[basic.contract.eval#18]] |
| 25 | `_`, structured binding packs and pack indexing combined | [[basic.scope.scope#6]], [[basic.lookup.general#1]], [[expr.prim.pack.index#2]] |
