---
title: Sequential execution
summary: "In what order the evaluations in one thread happen: value computations and side effects, sequenced before, unsequenced and indeterminately sequenced, full-expressions, and why unsequenced conflicting accesses are undefined behavior."
updated: 2026-10-19
---

!!! tldr
    - Evaluations within one thread are only partially ordered. Two evaluations may be ordered (sequenced before), ordered in an unspecified way but not overlapping (indeterminately sequenced), or completely unordered and able to overlap.
    - If a modification of a memory location is unsequenced relative to another modification or read of it, the behavior is undefined. `i = i++ + i` is UB; `i = i++ + 1` is not, since C++17.
    - C++17 specified an order for `<<`, `>>`, `=`, `[]`, `->*` and the called function in a call; the operands of operators like `+` and `==`, and the function arguments among themselves, still have no specified order.
    - A function call does not interleave with the caller's other evaluations: the result of `i + f()` is unspecified, but not UB.
    - All evaluations of one full-expression come before the next full-expression. Temporaries are generally destroyed at the end of the full-expression.

## The order of evaluation is only a partial order

```cpp run title="seq-std.cpp"
void g(int i) {
  i = 7, i++, i++;              // OK: i becomes 9

  i = i++ + 1;                  // OK (since C++17): i is incremented
  i = i++ + i;                  // UB
  i = i + 1;                    // OK

  union U { int x, y; } u;
  (u.x = 1, 0) + (u.y = 2, 0);  // UB
}
int main() { g(0); }
```

This is Example 3 in the standard. All four lines read and write `i` several times within one expression, yet they split into well-defined and UB. To explain the difference, we first need to take an evaluation apart.

### Value computations and side effects (¶7)

¶7 The following are **side effects**, i.e. changes in the state of the execution or translation environment:

- reading an object designated by a volatile glvalue (reading a device register may change the device's state);
- modifying an object;
- {{c++26}} producing an injected declaration ([[expr.const.reflect]]), an effect of static reflection at translation time, which is why the definition mentions the translation environment;
- calling a library I/O function;
- calling a function that does any of these.

**Evaluation** of an expression in general includes two parts. **Value computation** is, for a glvalue, determining the identity of the object it refers to, and for a prvalue, fetching a value from an object. The other part is initiating side effects. For `i++`, the value computation yields the old value of `i`, and the side effect adds 1 to `i`; the two can be separated in time.

When a call to a library I/O function returns, or an access through a volatile glvalue is evaluated, the side effect is considered complete, even if the actual I/O has not yet happened.

### Three relations (¶8)

¶8 [[g:sequenced-before|**Sequenced before**]] is a relation between two evaluations within a single thread; it is asymmetric and transitive, forming a partial order. A sequenced before B means the execution of A shall precede that of B. Besides it there are two other possibilities:

| Relation | Meaning | Can they overlap? | Example |
|---|---|---|---|
| sequenced before | A finishes, then B runs | no | two statements separated by a semicolon; the left operand of `&&` or `,` before the right |
| **indeterminately sequenced** | A before B or B before A, unspecified which | no | a function call and evaluations outside it (¶12); the initializations of the parameters ([[expr.call#8]]) |
| **unsequenced** | no sequenced-before in either direction | yes | the two operands of `+`, `*`, `==` |

Notes 3 and 4 point out the difference: unsequenced evaluations can overlap, so the compiler can interleave the instructions computing `a` and `b` in `a + b`; two indeterminately sequenced evaluations are each a unit, and only which comes first is undetermined.

Saying that an expression X is sequenced before an expression Y means every value computation and side effect of X is sequenced before every value computation and side effect of Y. When C++17 says the left operand of `<<` is sequenced before the right, it uses this strong sense: the left side's side effects are all completed first too.

### Unsequenced conflicting accesses are UB (¶10)

¶10 Except where noted, evaluations of operands of individual operators and of subexpressions of individual expressions are unsequenced. Note 5 adds that when the same expression is evaluated more than once in a loop, the unsequenced or indeterminately sequenced parts may be ordered differently each time.

The value computations of the operands of an operator are sequenced before the value computation of the operator's result: `a` and `b` must be known before `a + b` can be computed. But this covers only value computations, not side effects.

!!! std
    The behavior is undefined if a side effect on a memory location […] is unsequenced relative to […] another side effect on the same memory location […] or a value computation using the value of any object in the same memory location.

The full rule: if

- ¶10.1 a side effect on a memory location, or ¶10.2 starting or ending the lifetime of an object in a memory location,

is unsequenced relative to any of:

- ¶10.3 another side effect on the same memory location;
- ¶10.4 starting or ending the lifetime of an object occupying storage that overlaps with the memory location;
- ¶10.5 a value computation using the value of any object in the same memory location;

and the two evaluations are not potentially concurrent, the behavior is undefined. Potentially concurrent means they are in different threads, or one is in a signal handler ([[intro.races#17]]); that case is handled by the data race rules in the next subclause, which is also what note 7 says.

The rule talks about [[intro.memory|memory locations]] (a scalar object, or a sequence of adjacent non-zero-width bit-fields), not variables. Adjacent bit-fields may share a memory location, and union members share storage. ¶10.2 and ¶10.4 bring the start and end of lifetimes in too, because assigning to a union member changes the active member. Note 6 explains that starting the lifetime of an object in a memory location can end the lifetime of objects in other memory locations ([[basic.life]]).

Back to Example 3:

- `i = 7, i++, i++;`: the left operand of the comma operator is sequenced before the right ([[expr.comma]]), so `i` becomes 7, 8, 9 in turn.
- `i = i++ + 1;`: [[expr.assign]] specifies that the right operand is sequenced before the left, and the side effect of the assignment itself comes after the value computations of both sides. The side effect of `i++` belongs to the right operand and completes before the assignment, so the two are sequenced. In C++11/14 these two side effects were unsequenced, which was UB.
- `i = i++ + i;`: inside the right operand, the two operands of `+` are unsequenced, so the side effect of `i++` is unsequenced relative to the value computation of the right-hand `i`, hitting ¶10.5.
- The union line: `u.x = 1` starts the lifetime of `u.x` and `u.y = 2` starts the lifetime of `u.y`; both are in the same storage and belong to the two unsequenced operands of `+`, hitting ¶10.2 and ¶10.4.

<div class="compare" markdown="1">

```cpp run title="seq-ok.cpp" ok
#include <cstdio>
int a[4] = {};
int main() {
  int x = 5;
  x = x++;    // x stays 5
  int i = 0;
  a[i] = i++ + 10;
  // the right side is evaluated first: i becomes 1,
  // then the left side a[i], i.e. a[1]
  std::printf("%d %d %d\n",
              x, a[0], a[1]);
}
```

```cpp run title="seq-ub.cpp" ub
int h(int i) {
  // both operands of + modify i,
  // unsequenced with each other
  return i++ + i++;
}
int main() { return h(0); }
```

</div>

The left one prints `5 0 10`. Clang 23 gives a `-Wunsequenced` warning (included in `-Wall`) for the right one and no warning for the left.

### Where there is an order since C++17

¶10 only says "except where noted"; the specific rules are scattered across Clause 7:

| Expression | Order | Source |
|---|---|---|
| `a && b`, <code>a &#124;&#124; b</code> | if b is evaluated, a is sequenced before b | [[expr.log.and#2]], [[expr.log.or#2]] |
| `a ? b : c` | a before b or c | [[expr.cond]] |
| `a , b` | a before b | [[expr.comma#1]] |
| `a << b`, `a >> b` | a before b (C++17) | [[expr.shift#4]] |
| `a = b`, `a += b`, etc. | b before a; the assignment after the value computations of both sides (C++17) | [[expr.assign#1]] |
| `a[b]` | a before b (C++17) | [[expr.sub#1]] |
| `a->*b`, `a.*b` | a before b (C++17) | [[expr.mptr.oper#4]] |
| `f(args…)` | f before every argument and default argument (C++17); the initializations of the parameters are indeterminately sequenced with each other | [[expr.call#8]] |
| `{a, b, c}` | left to right, even when used as constructor arguments | [[dcl.init.list#4]] |
| `new T(args)` | the allocation function call is sequenced before the expressions in the initializer; initialization is sequenced before the value computation of the new-expression | [[expr.new#25]] |
| `a + b`, `a == b`, `a < b`, `a & b`, etc. | unsequenced | ¶10 |

```cpp run title="cpp17-order.cpp" ok
#include <cstdio>
#include <iostream>
#include <map>
int main() {
  int i = 0;
  std::cout << i++ << ' ' << i++ << '\n';   // guaranteed to print "0 1" since C++17

  std::map<int, int> m;
  m[0] = m.size();      // the right side first: size() before the insertion, so m[0] == 0
  std::printf("%d\n", m[0]);
}
```

When an overloaded operator is called with operator notation, its operands are evaluated in the order of the corresponding built-in operator ([[over.match.oper]]), so `std::cout << i++ << i++` is guaranteed. Written in function-call notation, `operator<<(operator<<(std::cout, i++), i++)`, it falls back to the rules for ordinary function calls: the two arguments are indeterminately sequenced and the result is unspecified. Example 5 in [[expr.call]] contrasts exactly these two forms.

In C++14, `operator[]` and `size()` in `m[0] = m.size()` were two indeterminately sequenced function calls, and `m[0]` could be 0 or 1.

!!! note "Why not specify a complete order of evaluation"
    C and C++ have always left the order of operand evaluation to the implementation: a compiler can evaluate first the side needing more registers, choose the direction of argument evaluation by calling convention, and merge and reorder more freely. The price is that code like `f(i++, i++)` gives different results on different compilers. C++17's [[P0145R3]] added an order only for the few operators readers habitually read left to right; it left ordinary arithmetic operators alone, and did not specify an order among arguments.

## Full-expressions (¶2–¶6, ¶9)

```cpp run title="full-expr.cpp" ok
#include <cstdio>
struct T {
  const char* n;
  T(const char* s) : n(s) { std::printf("ctor %s\n", n); }
  ~T() { std::printf("dtor %s\n", n); }
  int v() const { return 1; }
};
int use(int a, int b) { std::printf("use\n"); return a + b; }

int main() {
  int x = use(T("a").v(), T("b").v());  // the whole initialization is one full-expression
  std::printf("next %d\n", x);
}
```

Which of `T("a")` and `T("b")` is constructed first is unspecified; they belong to two indeterminately sequenced parameter initializations. But both are destroyed after `use` returns and before `next` is printed, because temporaries are destroyed at the end of the full-expression they belong to ([[class.temporary]]). In our tests the output is `ctor a`, `ctor b`, `use`, `dtor b`, `dtor a`, `next 2`.

¶9 Every value computation and side effect of a full-expression is sequenced before every value computation and side effect of the next full-expression to be evaluated. Footnote 29 adds that after a full-expression is evaluated, a sequence of zero or more destructor calls for temporaries takes place, usually in reverse order of construction.

¶5 A [[g:full-expression|**full-expression**]] is one of:

| | Kind | Example |
|---|---|---|
| ¶5.1 | an unevaluated operand | the `f()` in `sizeof(f())` |
| ¶5.2 | a *constant-expression* | array bounds, `case` labels |
| ¶5.3 | an immediate invocation | {{c++20}} a call to a `consteval` function |
| ¶5.4 | an *init-declarator* (including structured bindings) or a *mem-initializer*, together with its initializer | `int x = use(...);` |
| ¶5.5 | a destructor call generated at the end of an object's lifetime, other than for temporaries or temporaries whose lifetime was extended | destruction of local variables at the end of a block |
| ¶5.6 | the predicate of a contract assertion | {{c++26}} the `n > 0` in `pre(n > 0)` |
| ¶5.7 | an expression that is not a subexpression of another expression and not otherwise part of a full-expression | expression statements, the operand of `return`, the condition of `if` |

¶5 adds three more points. If a language construct is defined to produce an implicit function call (for example, range-for calling `begin()`), the construct is considered an expression for this purpose. Conversions applied to the result to satisfy the requirements of the language construct (converting an `if` condition to `bool`, the lvalue-to-rvalue conversion) are part of the full-expression. For an initializer, performing the initialization itself (including default member initializers of an aggregate) is also part of the full-expression.

One line of Example 2 shows what the last point leads to:

```cpp run title="noexcept-dtor.cpp" ok
struct S {
  S(int) noexcept {}
  ~S() noexcept(false) {}
};
static_assert(!noexcept(S(4)));   // the temporary's destruction is part of this full-expression too
int main() {}
```

The operand of `noexcept(S(4))` is an unevaluated operand and a full-expression in its own right, and the destructor call destroying the temporary at its end counts too. The destructor is `noexcept(false)`, so the result is `false`.

### Default arguments belong to the caller

¶2–¶4 define a set of auxiliary concepts to say exactly what a full-expression contains:

- ¶2 **Constituent expressions** flatten initializers: the constituent expressions of `B b = { 5, { 1+1 } };` are `5` and `1+1`.
- ¶3 The **immediate subexpressions** of E include the operands of E, the functions E implicitly calls, the initializations of a lambda's by-copy captures, and ¶3.4 the default arguments used by E and ¶3.5 the default member initializers used by an aggregate initialization.
- ¶4 **Subexpressions** are the transitive closure of the immediate-subexpression relation. Note 1 points out that the expressions in a lambda's body are not subexpressions of the lambda expression, since the body runs only when the closure is called. ¶4 also defines **potentially-evaluated subexpressions**: excluding those nested in unevaluated operands ([[expr.context]]).

The effect of ¶3.4 and ¶3.5 is that default arguments and default member initializers, though written elsewhere, are evaluated at the point of call or initialization and belong to the caller's full-expression. The temporaries they create are destroyed only at the end of the caller's full-expression, and their side effects take part in the ordering analysis of the caller's expression. Note 2 in ¶6 says exactly this.

!!! note "Temporaries in range-for"
    The boundary of a full-expression determines how long temporaries live. `for (auto x : make().items())` produces a dangling reference in C++20 and earlier: the temporary returned by `make()` is destroyed at the end of the *for-range-initializer* full-expression. C++23 added a lifetime-extension case in [[class.temporary]] that makes the temporaries here live until the end of the whole loop.

## Function calls (¶11–¶14)

¶11 When calling a function f (whether or not f is inline), the following are sequenced before one another in turn:

1. every argument expression and the postfix expression designating f;
2. {{c++26}} every precondition assertion of the call;
3. every expression and statement in the function body;
4. {{c++26}} every postcondition assertion of the call.

"Whether or not inline" means inline expansion cannot change this order.

### Function calls don't interleave (¶12)

```cpp run title="no-interleave.cpp" unspecified
#include <cstdio>
int i = 0;
int f() { return ++i; }
int main() {
  int r = i + f();          // not UB: reading i and the ++i in f() are indeterminately sequenced
  std::printf("%d\n", r);   // 1 or 2, unspecified
}
```

`i + i++` is UB, but `i + f()` is not; the difference is that the increment happens inside a function.

¶12 Let F be a function call (¶12.1), an evaluation of an *await-expression* (¶12.2), or an evaluation of a *throw-expression* (¶12.3). Every evaluation on the same thread (in a signal handler, within the same handler invocation) that does not occur within F is either sequenced before all evaluations within F or sequenced after all of them. Footnote 30 sums it up: the executions of functions do not interleave with each other. So reading `i` happens either entirely before `f` or entirely after it, and there are only two possible results.

When F calls or resumes a coroutine, only the evaluations after the previous suspension and before the next suspension count as within F; each contiguous stretch of a coroutine's execution is treated as a unit.

¶13 Some contexts call functions without function-call syntax: a *new-expression* calls an allocation function and a constructor, and an implicit conversion calls a conversion function. ¶14 specifies that the ordering constraints above are properties of the function call itself, regardless of the syntax used to invoke it, so they hold for these implicit calls too.

C++17's parameter initialization rule together with ¶12 fixed a classic memory leak:

```cpp run title="no-leak.cpp" ok
#include <memory>
struct A {};
int g() { throw 0; }
void h(std::unique_ptr<A>, int) {}
int main() {
  try {
    h(std::unique_ptr<A>(new A), g());   // since C++17: no leak when g throws
  } catch (int) {}
}
```

In C++14 the subexpressions of different arguments were unsequenced, so a compiler could execute `new A`, then `g()`, then construct the `unique_ptr`, leaking the memory from `new A` when `g()` threw. Since C++17, [[expr.call#8]] specifies that the initialization of each parameter, with all its value computations and side effects, is indeterminately sequenced with respect to the other parameters. `new A` and constructing the `unique_ptr` belong to the same parameter's initialization, and `g()` cannot get in between.

C++17's rule that the postfix expression of the called function comes before the arguments also makes chained calls run left to right. Here is an adaptation of Example 4 in [[expr.call]]:

```cpp run title="chain.cpp" ok
#include <cassert>
#include <string>
int main() {
  std::string s = "but I have heard it works even if you don't believe in it";
  s.replace(0, 4, "").replace(s.find("even"), 4, "only").replace(s.find(" don't"), 6, "");
  assert(s == "I have heard it works only if you believe in it");
}
```

In C++14, `s.find("even")` might be evaluated before the first `replace`, giving the wrong index. Since C++17, the postfix expression of a member call `E.replace(...)` (including `E`, i.e. the previous `replace` call) is evaluated before the arguments.

## Signal handlers (¶15)

¶15 A signal handler executed as a result of a call to `std::raise` executes after the call to `raise` and before it returns, like an ordinary function call. Note 8 adds that signal handlers triggered for other reasons are usually unsequenced with the rest of the program. That is why asynchronous signal handlers can safely access only `volatile std::sig_atomic_t` or lock-free atomic objects ([[intro.races#18]], [[support.signal]]).

## Lexical order in constant evaluation (¶16)

¶16 When an expression is evaluated as a core constant expression ([[expr.const.core]]), operands and subexpressions that would otherwise be unsequenced or indeterminately sequenced are evaluated in lexical order. Default arguments used by a function call are sequenced as if arguments had been written in the corresponding positions.

The results of constant evaluation enter the type system (array bounds, template arguments) and must agree across all implementations. With lexical order specified, nothing in constant evaluation has an unspecified order anymore.

```cpp run title="constexpr-order.cpp" ok
constexpr int h() {
  int i = 0;
  int r = i++ + i++;    // in constant evaluation, lexical order: 0 + 1
  return r * 10 + i;
}
static_assert(h() == 12);
int main() {}
```

!!! lawyer "Is `i++ + i++` still UB in constant evaluation?"
    The UB of ¶10 presupposes the evaluations being unsequenced, while ¶16 says they are evaluated in lexical order during constant evaluation. Read literally, the example has a determinate result in constant evaluation. Clang 23 accepts it and gets 12, while still giving the usual `-Wunsequenced` warning. When the same function is called at run time, `i++ + i++` is still UB. This paragraph is new wording after C++23; don't rely on it in portable code.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 Each time a block is entered, a new instance of each of its automatic-storage-duration objects is created. The object exists and retains its last-stored value during the execution of the block, including while the block is suspended: when another function is called, when a coroutine suspends ([[expr.await]]), or when a signal is received, local variables keep their values. This is the basis for each level of recursion having its own local variables, and for a coroutine's local variables having their pre-suspension values after it resumes.

</details>

!!! impl
    - The direction of argument evaluation varies by compiler. A common observation is that GCC on x86-64 mostly evaluates arguments right to left and Clang left to right; with Clang 23, `f(i++, i++)` passes `0 1`.
    - Clang 23 does not warn about `a[i] = i++ + 10` or `i += i++`, which are well-defined since C++17, but still reports multiple unsequenced modifications for `f(i++, i++)`. Per [[expr.call#8]], the two parameter initializations are indeterminately sequenced rather than unsequenced; this is not UB, only an unspecified result. The warning should be read as a portability reminder. GCC's corresponding option is `-Wsequence-point`.

!!! history "From sequence points to sequenced before"
    - C++98/03 followed C's sequence point model: between two adjacent sequence points, an object could be modified at most once, and its old value could be read only to compute the new value. `i = ++i + 1` was UB.
    - For the multithreaded memory model, C++11 replaced sequence points with sequenced before, unsequenced and indeterminately sequenced, and described value computations and side effects separately. Some expressions that used to be UB became well-defined, such as `i = ++i + 1`: the side effect of the prefix increment is sequenced before its value computation, and the assignment comes after.
    - C++17's [[P0145R3]] specified an order for `<<`, `>>`, assignment, `[]`, `->*`, `.*` and the called function, and made parameter initialization indeterminately sequenced. The proposal discussed strictly left-to-right argument evaluation, but in the end only the weaker indeterminate sequencing was adopted.
    - C++20 added coroutines, bringing *await-expressions* under the no-interleaving rule; immediate invocations became full-expressions.
    - In C++26 the predicates of contract assertions became full-expressions, preconditions and postconditions were added to the ordering chain of a function call, and injected declarations from reflection were added to the definition of side effects.

## Common misconceptions

!!! pitfall "C++17 specified the order of evaluation"
    Only part of it. The operands of `a + b` and `a == b`, and the calls to `g` and `h` in `f(g(), h())`, still have an unspecified order. What C++17 changed for arguments is only that each argument is evaluated as a whole and no longer overlaps other arguments. `std::printf("%d %d", i++, i++)` is not UB, but its output is unspecified.

!!! pitfall "Every comma is the comma operator"
    The commas in `f(a, b)` separate arguments and impose no order. The comma in `int x = i++, y = i++;` separates two *init-declarators*, each a full-expression (¶5.4), so they are ordered. Only the comma operator, as in `(a, b)`, guarantees left to right. An overloaded `operator,` called with operator notation also follows left to right since C++17.

!!! pitfall "The order is the same on every loop iteration"
    For `sum += f() * g();` in a loop, you cannot assume `f` is called first on every iteration (note 5). Optimized code may peel off the first iteration and change its call order.

## Questions

!!! question "1. Which of these are UB? (C++17 and later)"
    ```cpp
    int i = 0, a[4] = {};
    i = ++i + i++;        // (a)
    a[i++] = i;           // (b)
    i += i++;             // (c)
    i = (i++, i);         // (d)
    ```

<details markdown="1">
<summary>Answer</summary>

- (a) UB. In the right operand `++i + i++`, both operands of `+` modify `i` and are unsequenced with each other.
- (b) Well-defined. The right operand `i` of the assignment is sequenced before all evaluation of the left operand `a[i++]` (including the side effect of `i++`). If `i` was 0: the right side reads 0, the left side `a[i++]` designates `a[0]`, then `i` becomes 1, and finally `a[0] = 0`. In C++14 it was UB.
- (c) Well-defined. Compound assignment also evaluates the right side first: if `i` was 0, the right side yields 0 and `i` becomes 1; then reading the left `i` gives 1, and the result is `i = 1 + 0 = 1`.
- (d) Well-defined. The comma operator's left is sequenced before its right: `i` is incremented first, then the new value is read and assigned back.
</details>

!!! question "2. Why are indeterminately sequenced conflicting accesses merely unspecified, while unsequenced ones are UB?"

<details markdown="1">
<summary>Answer</summary>

The basis is notes 3 and 4. Unsequenced evaluations can overlap: the compiler may split a write into several instructions interleaved with another read or write, and the result could be anything. The standard does not constrain this case and makes it UB in exchange for freedom to optimize. Two indeterminately sequenced evaluations are guaranteed not to overlap; one simply completes first, so there are only finitely many possible results, and it is merely unspecified.
</details>

!!! question "3. In `std::cout << f() << g();`, is `f` always called before `g`? What if `operator<<` is a member function?"

<details markdown="1">
<summary>Answer</summary>

Always, since C++17. Whether `operator<<` is a member or a non-member, as long as operator notation is used, the operands are evaluated as specified for the built-in `<<` ([[over.match.oper]], [[expr.shift#4]]). In `(cout << f()) << g()`, the left operand of the outer `<<` is `cout << f()`, which as a whole is sequenced before `g()`. In C++14, if `operator<<` was a member function, there was no order between the postfix expression `(cout << f()).operator<<` and the argument `g()`, so `g` might be called first.
</details>
