---
title: "Visitors: double dispatch and std::visit"
summary: "Adding operations to a fixed set of types without changing them: how the classic visitor gets double dispatch from two virtual calls, the two directions of the expression problem, the acyclic visitor, the closed-set approach with std::variant and std::visit, exhaustiveness checking, multiple dispatch and how it is implemented, the indirection a recursive variant needs, and the measured costs of both approaches."
tags: visitor, double dispatch, variant, visit, design patterns
updated: 2026-10-19
---

!!! tldr
    - Overload resolution looks at the static types of expressions, and a virtual call dispatches on the dynamic type of only one object. The classic visitor puts together dispatch on two dynamic types out of two virtual calls (one to `accept`, one to `visit`).
    - Virtual functions make adding types easy and adding operations hard; the visitor is exactly the reverse. This tension is called the expression problem, and which approach to choose depends on which direction changes more often.
    - When the set of types is closed, `std::variant` with `std::visit` is the more direct approach: value semantics, no `accept` boilerplate, a missed type fails to compile, and dispatch on several variants at once.
    - `std::visit` uses a table of function pointers to turn a run-time index into a call chosen at compile time; with few alternatives, Clang optimizes it into a few comparisons plus direct calls.
    - A recursive variant must go through a level of indirection (`unique_ptr`, a hand-written value-semantic box, or C++26's `std::indirect`), because a variant stores its alternative's value directly inside itself.

## The problem: one expression tree, many operations

The expression `(1 + 2) * 4` can be represented as a tree: leaves are numbers, internal nodes are additions and multiplications. There are many things to do with this tree: evaluate, print, fold constants, type-check, generate code. The kinds of nodes rarely change, but the operations keep growing.

With virtual functions, each operation is a virtual function of the base class:

```cpp
struct Expr {
  virtual double eval() const = 0;
  virtual std::string print() const = 0;
  virtual std::unique_ptr<Expr> fold() const = 0;   // a new operation: every derived class must change
  virtual ~Expr() = default;
};
```

Every new operation adds a function to every node class and recompiles all code that includes `Expr`. And the logic of a single operation is scattered across the classes: part of the evaluation rules is in `Add`, part in `Mul`. The visitor pattern inverts this relationship, putting all the logic of one operation in one class, with the node classes only providing a fixed entry point.

## Why overloading alone isn't enough

The most direct idea is to write an overload for each kind of node and let the compiler choose:

```cpp run title="static-type.cpp" ok
#include <cstdio>
struct Expr { virtual ~Expr() = default; };
struct Num : Expr { double value = 1; };

void print(const Expr&) { std::printf("Expr\n"); }
void print(const Num&)  { std::printf("Num\n"); }

int main() {
  Num n;
  const Expr& e = n;
  print(n);   // Num: the static type is Num
  print(e);   // Expr: the static type is Expr, even though the object is a Num
}
```

Overload resolution ([[g:overload-resolution]]) happens at compile time and compares the **static types** of the argument expressions ([[g:static-type]], the types the compiler can see from declarations), regardless of what `e` actually refers to at run time ([[over.match.general#1]]). Child nodes in a tree can only be stored as `Expr&` or `Expr*`, so calling `print` on a child always selects `print(const Expr&)`; without that overload, it simply fails to compile.

The type known only at run time is the **dynamic type** ([[g:dynamic-type]], the most derived class the object actually belongs to). The only language mechanism in C++ that chooses a function by dynamic type is a virtual function call: what is called is the final overrider in the object's dynamic type ([[g:final-overrider]], [[expr.call#2]]). And it looks at only one object, the one to the left of `.` or `->`.

So the problem becomes: one call must depend on the dynamic types of two objects at once (which kind of node, which kind of operation), while the language only provides dispatch on one object.

## The classic visitor

```cpp run title="classic-visitor.cpp" ok
#include <cstdio>
#include <memory>

struct Num; struct Add; struct Mul;

struct Visitor {                   // one visit per kind of node
  virtual void visit(const Num&) = 0;
  virtual void visit(const Add&) = 0;
  virtual void visit(const Mul&) = 0;
  virtual ~Visitor() = default;
};

struct Expr {
  virtual void accept(Visitor& v) const = 0;
  virtual ~Expr() = default;
};
using Ptr = std::unique_ptr<Expr>;

struct Num : Expr {
  double value;
  explicit Num(double v) : value(v) {}
  void accept(Visitor& v) const override { v.visit(*this); }
};
struct Add : Expr {
  Ptr lhs, rhs;
  Add(Ptr l, Ptr r) : lhs(std::move(l)), rhs(std::move(r)) {}
  void accept(Visitor& v) const override { v.visit(*this); }
};
struct Mul : Expr {
  Ptr lhs, rhs;
  Mul(Ptr l, Ptr r) : lhs(std::move(l)), rhs(std::move(r)) {}
  void accept(Visitor& v) const override { v.visit(*this); }
};

// one operation = one visitor class
struct Eval : Visitor {
  double result = 0;
  double of(const Expr& e) { e.accept(*this); return result; }
  void visit(const Num& n) override { result = n.value; }
  void visit(const Add& a) override { result = of(*a.lhs) + of(*a.rhs); }
  void visit(const Mul& m) override { result = of(*m.lhs) * of(*m.rhs); }
};
struct Print : Visitor {
  void visit(const Num& n) override { std::printf("%g", n.value); }
  void visit(const Add& a) override { bin(*a.lhs, '+', *a.rhs); }
  void visit(const Mul& m) override { bin(*m.lhs, '*', *m.rhs); }
  void bin(const Expr& l, char op, const Expr& r) {
    std::printf("(");
    l.accept(*this);
    std::printf(" %c ", op);
    r.accept(*this);
    std::printf(")");
  }
};

int main() {
  Ptr e = std::make_unique<Mul>(               // (1 + 2) * 4
      std::make_unique<Add>(std::make_unique<Num>(1),
                            std::make_unique<Num>(2)),
      std::make_unique<Num>(4));
  Print p;
  e->accept(p);
  std::printf(" = %g\n", Eval{}.of(*e));     // ((1 + 2) * 4) = 12
}
```

Adding an operation only requires another class derived from `Visitor`; not a line of the node classes changes.

### Double dispatch: two virtual calls

Take `Eval{}.of(*e)` with `e` pointing to a `Mul`, and trace one `e.accept(*this)`:

1. `accept` is virtual and selects `Mul::accept` by `e`'s dynamic type. This step dispatches on the node type.
2. Inside `Mul::accept`, the static type of `*this` is `const Mul`. Overload resolution for `v.visit(*this)` selects `visit(const Mul&)` at compile time.
3. `visit` is also virtual and selects `Eval::visit(const Mul&)` by `v`'s dynamic type. This step dispatches on the operation type.

This is **double dispatch**: the function finally executed is determined jointly by the dynamic types of two objects. The key is step 2: overload resolution doesn't know dynamic types, but the virtual call has already brought `accept` into the right derived class, where the static type of `*this` happens to be the dynamic type.

This also explains why every node class repeats the same line `v.visit(*this);`. Writing it in the base `Expr` doesn't work, because there the static type of `*this` is `const Expr`; see Question 1. To remove the repetition, a class template can generate `accept` for each node, i.e. [[patterns/crtp|CRTP]].

The cost is two indirect calls per node visited, each first loading the vptr from the object and then the function address from the vtable (see [[toolchain/object-layout-and-vtables]]). Both calls cross boundaries the compiler can't see through and usually can't be inlined.

### The expression problem

Virtual functions and visitors each make one direction easy and the other hard:

| Approach | Adding a kind of node | Adding an operation |
|---|---|---|
| One virtual function per operation | write a derived class, old code untouched | every node class must change |
| Classic visitor | the `Visitor` base and every visitor must change | write a visitor class, old code untouched |
| `variant` + `visit` | change the variant's type list; every `visit` that doesn't handle it fails to compile | write a function, old code untouched |

This tension is called the **expression problem**: supporting both new types and new operations without modifying or recompiling existing code. Each of these C++ approaches solves only half. Visitors suit cases where the kinds of nodes are basically fixed and operations keep growing: compilers, interpreters and document format converters are all like this. When node kinds change often, virtual functions fit better.

### The acyclic visitor

In the classic visitor, `Visitor` mentions every kind of node, and every node mentions `Visitor` through `accept`, forming a dependency cycle: adding a node kind changes `Visitor`, and all visitors and nodes must be recompiled. The **acyclic visitor** splits `Visitor` apart and uses `dynamic_cast` to ask at run time whether a visitor supports the current node:

```cpp run title="acyclic.cpp" ok
#include <cstdio>

struct VisitorBase { virtual ~VisitorBase() = default; };   // empty root
template<class T>
struct VisitorOf {
  virtual void visit(const T&) = 0;
  virtual ~VisitorOf() = default;
};

struct Expr {
  virtual void accept(VisitorBase&) const = 0;
  virtual ~Expr() = default;
};
template<class Self>
struct Acceptor : Expr {
  void accept(VisitorBase& v) const override {
    if (auto* p = dynamic_cast<VisitorOf<Self>*>(&v))   // ask at run time
      p->visit(static_cast<const Self&>(*this));
    else
      std::printf("<unhandled>");
  }
};
struct Num : Acceptor<Num> { double value = 2; };
struct Neg : Acceptor<Neg> {};   // a new node: existing visitors don't change

struct PrintNums : VisitorBase, VisitorOf<Num> {
  void visit(const Num& n) override { std::printf("%g", n.value); }
};

int main() {
  PrintNums p;
  Num n;
  Neg g;
  n.accept(p);
  std::printf(" ");
  g.accept(p);
  std::printf("\n");   // 2 <unhandled>
}
```

`VisitorBase` and `VisitorOf<Num>` are two sibling bases of `PrintNums`; converting from one to the other is called a cross cast, and the run-time check first has to find the most derived object and then look for the target type among its bases ([[expr.dynamic.cast#9]]). It is much more expensive than a virtual call, and forgetting to handle a node kind is no longer a compile error, only discoverable at run time. So the acyclic visitor is worth it only when the dependencies really are a problem (for instance, node types spread across several libraries).

## std::variant and std::visit

If the node kinds form a closed set fixed at compile time, no inheritance hierarchy is needed. A `std::variant<Num, Add, Mul>` is an object that holds a value of one of those types at any time ([[variant.variant.general#1]]), and `std::visit` calls the corresponding function based on the type it currently holds ([[variant.visit]]):

```cpp run title="variant-ast.cpp" ok
#include <cstdio>
#include <format>
#include <memory>
#include <string>
#include <variant>

template<class T>   // a value-semantic heap box: deep copies on copy, see below
class box {
  std::unique_ptr<T> p_;
public:
  box(T v) : p_(std::make_unique<T>(std::move(v))) {}
  box(const box& o) : p_(std::make_unique<T>(*o.p_)) {}
  box& operator=(const box& o) {
    p_ = std::make_unique<T>(*o.p_);
    return *this;
  }
  box(box&&) noexcept = default;
  box& operator=(box&&) noexcept = default;
  const T& operator*() const { return *p_; }
};

template<class... Fs>
struct overloaded : Fs... { using Fs::operator()...; };

struct Expr;   // declared first so box<Expr> can be written
struct Num { double value; };
struct Add { box<Expr> lhs, rhs; };
struct Mul { box<Expr> lhs, rhs; };
struct Expr : std::variant<Num, Add, Mul> { using variant::variant; };

double eval(const Expr& e) {
  return std::visit(overloaded{
    [](const Num& n) { return n.value; },
    [](const Add& a) { return eval(*a.lhs) + eval(*a.rhs); },
    [](const Mul& m) { return eval(*m.lhs) * eval(*m.rhs); },
  }, e);
}

std::string show(const Expr& e) {
  return e.visit(overloaded{   // C++26 member visit
    [](const Num& n) { return std::format("{}", n.value); },
    [](const Add& a) {
      return "(" + show(*a.lhs) + " + " + show(*a.rhs) + ")";
    },
    [](const Mul& m) {
      return "(" + show(*m.lhs) + " * " + show(*m.rhs) + ")";
    },
  });
}

Expr num(double v)       { return Num{v}; }
Expr add(Expr l, Expr r) { return Add{std::move(l), std::move(r)}; }
Expr mul(Expr l, Expr r) { return Mul{std::move(l), std::move(r)}; }

// constant folding: returns a new tree, the original is unchanged
Expr fold(const Expr& e) {
  return std::visit(overloaded{
    [](const Num& n) -> Expr { return n; },
    [](const auto& op) -> Expr {   // Add and Mul share one branch
      using Op = std::decay_t<decltype(op)>;
      Expr l = fold(*op.lhs), r = fold(*op.rhs);
      bool constant = std::holds_alternative<Num>(l) &&
                      std::holds_alternative<Num>(r);
      Expr out = Op{std::move(l), std::move(r)};
      return constant ? Num{eval(out)} : out;
    },
  }, e);
}

int main() {
  Expr e = mul(add(num(1), num(2)), num(4));
  Expr copy = e;   // deep-copies the whole tree
  std::printf("%s = %g\n", show(copy).c_str(), eval(copy));
  // ((1 + 2) * 4) = 12
  Expr f = fold(add(num(1), mul(num(2), num(3))));
  std::printf("%s\n", show(f).c_str());   // 7
}
```

Compared with the classic visitor, there are a few differences:

- The node types need no common base class and no `accept`. `Num`, `Add` and `Mul` are ordinary aggregates and can go into any other variant.
- Value semantics. `Expr` itself is a value that can be copied, compared and put in containers, without `unique_ptr<Expr>` and a virtual destructor.
- Operations are functions. `eval`, `show` and `fold` are three ordinary functions, each with all its logic in one place. Adding an operation touches no existing code.
- One branch can handle several types. `fold` uses one generic lambda for both `Add` and `Mul`, which in the classic visitor would require a default implementation in the base class.

`overloaded`, which combines a set of lambdas into one visitor, relies on inheriting from closure types, `using Ts::operator()...` and class template argument deduction for aggregates; how it works is explained in [[patterns/mixin]] and the overload pattern section of [[variant.visit]]. The `e.visit(f)` in `show` is the member `visit` added in C++26 ([[P2637R3]]), equivalent to `std::visit(f, e)` ([[variant.visit#11]]), and libc++ in our tests already supports it.

`Expr` is written as a struct derived from the variant rather than `using Expr = std::variant<Num, Add, Mul>;`, because an alias cannot be declared first and defined later, and `Add` has to mention `Expr` first. `std::visit` accepts such derived classes directly ([[variant.visit#1]]).

### Exhaustiveness checking

After adding a type to the variant, every `visit` that doesn't handle it fails to compile:

```cpp title="missing-case.cpp" error
#include <variant>
template<class... Fs>
struct overloaded : Fs... { using Fs::operator()...; };

struct Num { double value; };
struct Add {};
struct Neg {};   // the newly added node type
using Node = std::variant<Num, Add, Neg>;

double eval(const Node& n) {
  return std::visit(overloaded{
    [](const Num& x) { return x.value; },
    [](const Add&)   { return 0.0; },
  }, n);   // error: Neg is not handled
}
```

The rule is in [[variant.visit#5]]: the call to the visitor must be valid for every possible combination of indices; this is a *Mandates*, and violating it makes the program ill-formed.

The diagnostic from Clang 23 with libc++ is not direct: the first error is the library-internal "no matching function for call to '__invoke'", and only by finding `const __alt<2UL, Neg> &` in the following notes can you tell that `Neg` is missing. libc++ has a `static_assert` reading "`std::visit` requires the visitor to be exhaustive.", but with this form the return type deduction of the internal wrapper fails first and the assertion never gets a chance to fire; it appears only when `std::visit<double>(...)` is used.

!!! pitfall "Exhaustiveness checking can be bypassed by implicit conversions and generic branches"
    Exhaustiveness checking only requires the visitor to be callable for every type, not that each type has exactly one branch written for it. Two situations let a missed type slip through: a branch that can accept it through an implicit conversion, for example a `char` being promoted into the `int` branch when there is no `char` branch (example in the overload pattern section of [[variant.visit]]); and a catch-all branch such as `[](const auto&)` in the visitor. The generic branch in `fold` is like this: if `Neg` is added later, it will be treated as a binary operation, and only because `Neg` has no `lhs` or `rhs` will it then fail to compile. Catch-all branches are best restricted to the types they really handle with `if constexpr` or concepts.

### Return types

Without a specified return type, all branches must have exactly the same return type and value category ([[variant.visit#5]]), regardless of which branch is actually taken at run time. Both lambdas in `fold` write `-> Expr` because the first branch would otherwise return `Num` and the second `Expr`, and differing types are a compile error.

Another option is C++20's `std::visit<R>(f, v)` ([[P0655R1]]): each branch's result is implicitly converted to `R`, and when `R` is `void` the result is discarded (*INVOKE*<R> in [[variant.visit#4]]). The full rules are in [[variant.visit]].

### Multiple dispatch

`std::visit` can take several variants at once, and the visitor chooses a branch by the combination of types they currently hold. This is exactly what the classic visitor needs two virtual calls for, and it isn't limited to two:

```cpp run title="multi-dispatch.cpp" ok
#include <cstdio>
#include <variant>

template<class... Fs>
struct overloaded : Fs... { using Fs::operator()...; };

struct Circle { double x, y, r; };
struct Rect   { double x0, y0, x1, y1; };
using Shape = std::variant<Circle, Rect>;

bool hit(const Shape& a, const Shape& b) {
  return std::visit(overloaded{
    [](const Circle& c, const Circle& d) {
      double dx = c.x - d.x, dy = c.y - d.y, s = c.r + d.r;
      return dx * dx + dy * dy <= s * s;
    },
    [](const Rect& p, const Rect& q) {
      return p.x0 <= q.x1 && q.x0 <= p.x1 &&
             p.y0 <= q.y1 && q.y0 <= p.y1;
    },
    [](const Circle& c, const Rect& r) {   // rough: uses the bounding square
      return c.x + c.r >= r.x0 && c.x - c.r <= r.x1 &&
             c.y + c.r >= r.y0 && c.y - c.r <= r.y1;
    },
    [](const Rect& r, const Circle& c) {   // swap the arguments and dispatch again
      return hit(c, r);
    },
  }, a, b);
}

int main() {
  Shape c = Circle{0, 0, 1}, r = Rect{0.5, 0.5, 3, 3};
  std::printf("%d %d %d\n", hit(c, c), hit(c, r), hit(r, c));   // 1 1 1
}
```

Two variants of 2 types each have 2×2 = 4 combinations, and the visitor must handle all of them. The number of combinations is the product of the variants' type counts, so the standard requires constant time only for a single variant and imposes no complexity requirement for multiple variants ([[variant.visit#8]]). The actual cost is mainly at compile time: one function is instantiated per combination, and with many combinations compile time and code size both grow.

## How std::visit is implemented

The standard requires visiting a single variant in constant time, independent of the number of alternatives ([[variant.visit#8]]). libc++ instantiates a dispatch function for each index at compile time, puts their addresses in a `constexpr` array, and at run time fetches an entry with `index()` and calls it. With multiple variants the array is multidimensional.

There is one more check before the call. A variant can be in a state where it holds no value, called **valueless by exception** ([[g:valueless-by-exception]]): this can happen when an assignment or `emplace` that changes the alternative throws partway through, for example after the old value has been destroyed and the construction of the new one fails ([[variant.status#2]]). Then `index()` returns `variant_npos` ([[variant.status#3]]), which is not a valid table index, so `visit` must check first and throw `bad_variant_access` ([[variant.visit#7]]).

The optimizer can see through this `constexpr` table. On our test machine (Apple M2 Pro, arm64, Clang 23, `-O2`), calling `std::visit([](auto y) { return f(y); }, x)` on a variant with 5 alternatives, where `f` is overloaded as 5 external functions, generates:

```text
ldr   w8, [x0, #4]        ; load the index
cmn   w8, #1              ; index == -1? i.e. valueless
b.eq  throw_bad_variant_access
ldr   w0, [x0]            ; load the alternative's value (an int)
cmp   w8, #1
b.le  ...                 ; binary comparisons on the index
...
b     f(D)                ; each branch is a direct tail call
```

There is no indirect jump; every branch is a direct call to `f`. Increasing the number of alternatives one at a time from 5 to 12 in our tests: up to 10 it is always such a comparison tree; from 11 on, Clang keeps the function pointer table and generates an indirect call, `ldr x8, [table, index, lsl #3]` plus `blr x8`. This threshold is a heuristic of the compiler we tested, not a semantic guarantee.

For comparison, under the same settings a virtual call `b.g()` compiles to three instructions: load the vptr, load the function address from the vtable, jump indirectly.

## A recursive variant needs indirection

The expression tree is recursive: an `Add`'s children are `Expr`s again. Writing `struct Add { Expr lhs, rhs; };` directly is ill-formed, for two reasons:

- When `Add` is written, `Expr` is still an incomplete type, and a non-static data member cannot have an incomplete type ([[class.mem.general#20]]).
- Even if it could be written, it would make no sense. A variant nests its current alternative's value directly in its own storage ([[variant.variant.general#1]]); `Expr` contains `Add`, and `Add` contains two `Expr`s, giving infinite size.

So there must be a level of pointers. Three choices:

| Indirection | Allows incomplete types | Copyable | Notes |
|---|---|---|---|
| `std::unique_ptr<Expr>` | yes ([[unique.ptr.general#4]]) | no | the whole tree is move-only; copying requires a hand-written deep copy |
| A hand-written value-semantic box, like `box` above | yes | deep copy | you handle the null pointer after a move yourself |
| `std::indirect<Expr>` {{c++26}} | yes ([[indirect.general#6]]) | deep copy | a standardized `box`; `const` propagates |

Standard library templates generally may not be instantiated with incomplete types, or the behavior is undefined ([[res.on.functions#2.5]]); only components explicitly permitting it are exceptions, and `unique_ptr`, `vector` and `indirect` are among them, `variant` is not. In the code above, `Add` is already complete when `std::variant<Num, Add, Mul>` is instantiated; only the `Expr` inside `box<Expr>` is incomplete, so there is no problem.

With C++26's `std::indirect` ([[P3019R14]]), the tree definition is almost the same as the `box` version:

```cpp
#include <memory>
#include <variant>

struct Expr;
struct Num { double value; };
struct Add { std::indirect<Expr> lhs, rhs; };
struct Mul { std::indirect<Expr> lhs, rhs; };
struct Expr : std::variant<Num, Add, Mul> { using variant::variant; };

Expr add(Expr l, Expr r) {
  return Add{std::indirect<Expr>(std::move(l)),   // this constructor is explicit
             std::indirect<Expr>(std::move(r))};
}
```

This code carries no verdict: at the time of writing, libc++ (shipped with Clang 23) in our tests doesn't implement `std::indirect` yet, so it can't be verified. The full rules of `indirect` and its comparison with `unique_ptr` are in [[topics/ownership-and-smart-pointers]].

!!! pitfall "A moved-from box is empty"
    Both `box` and `indirect` no longer own an object after being moved from. `indirect` calls this valueless ([[g:valueless]], [[indirect.general#1]]), queryable with `valueless_after_move()`; dereferencing it is undefined behavior. The `box` above provides no query, and copying a moved-from `box` dereferences a null pointer. The tree constructors take subtrees by value and move them in, which is safe; just don't keep using the original variable after moving from it.

## Costs, measured

As for `sizeof`, with libc++ in our tests `Expr` (two `unique_ptr`s plus an index) is 24 bytes; in the virtual function version `Num` is 16 bytes (vptr plus `double`) and `Add` 24 bytes. A variant's size is its largest alternative plus the index, rounded up for alignment, and every node is the same size.

Below are measurements on our test machine (Apple M2 Pro, Clang 23, `-O2`), taking the fastest of 7 runs. The first group is a random full binary expression tree of about 4.2 million nodes (2^21 leaves), with the three approaches allocating nodes in the same order and evaluating the whole tree. The second group sums the areas of 10 million shapes of random type.

| Scenario | Approach | Time |
|---|---|---|
| Tree evaluation | classic visitor (two virtual calls per node) | about 16 ms |
| Tree evaluation | one virtual function per operation (one virtual call per node) | about 15 ms |
| Tree evaluation | `variant` + `visit`, `unique_ptr` children | about 12–13 ms |
| Flat sequence | `vector<unique_ptr<Shape>>`, in allocation order | about 57 ms |
| Flat sequence | same, with the pointers shuffled | about 147 ms |
| Flat sequence | `vector<variant<C, S, T>>` | about 42 ms |

A few observations:

- On the tree, the three approaches differ little. Every node requires chasing a pointer, and memory access dominates; the extra indirect call of double dispatch over a single virtual call adds about 7%.
- On the flat sequence, the variant's advantage comes mainly from memory layout, not from dispatch itself. The variant's elements are stored contiguously in the `vector`; the pointer version is about 35% slower even when the heap blocks happen to be allocated in order, and more than 3 times slower after shuffling (closer to what the heap looks like in a long-running program).
- With types randomly distributed, both approaches suffer unpredictable branches: the virtual call's indirect jump is hard to predict, and so are the variant's comparison branches.

These numbers describe only this one workload on our test machine; with bigger nodes, heavier operations or more regular type distributions, the ratios will change.

## Pattern matching: not in the standard yet

Many languages use pattern matching for this: an expression chooses a branch by the shape of a value (type, structure, values), and the compiler checks that the branches are exhaustive. The corresponding C++ proposal is [[P2688]], which introduces a `match` expression that can match directly on a variant's alternatives, the dynamic type of a polymorphic object, or structured values. It didn't make it into C++26, and the current draft has no `match` keyword. Until it is adopted, `std::visit` with `overloaded` is the closest thing in C++.

## Traps

!!! pitfall "accept during construction and destruction"
    Calling `accept` in a node's constructor or destructor dispatches the virtual call according to the class layer currently being constructed or destroyed ([[class.cdtor]]), possibly landing on a pure virtual function of the base. Before visiting a tree, make sure it is fully constructed.

!!! pitfall "Recursive visiting and stack depth"
    The `eval`, `show` and `fold` above, and the `Eval` visitor, are all recursive. A deep tree degenerated into a linked list (say ten thousand levels of `1 + (1 + (1 + ...))`) makes the recursion depth equal the tree height. When the tree's shape comes from external input, switch to traversal with an explicit stack, or limit the depth. Destroying a chain of `unique_ptr`s is recursive too.

!!! pitfall "Combinatorial explosion with multiple variants"
    Visiting three variants of 10 types each instantiates 1000 dispatch functions, and the visitor must be callable for every combination. Often only a few combinations really need special handling; cover the rest with generic branches, while keeping in mind, as mentioned above, that catch-all branches can hide omissions.

## Which to use when

| Situation | Choice |
|---|---|
| A closed set of types defined in one place, with operations added often | `std::variant` + `std::visit` |
| Value semantics and contiguous storage in containers needed | `std::variant` |
| Dispatching on the types of two or more objects at once | the multi-variant form of `std::visit` |
| An open set of types, to which third parties can add new types | virtual functions; directly as virtual functions when the operations are few and stable |
| An existing type hierarchy that must be kept, with operations being added continually | the classic visitor |
| Node types spread across several libraries that can't depend on each other | the acyclic visitor, accepting the cost of run-time checks |
| Just replacing an algorithm at run time | no visitor needed; see [[patterns/strategy]] |
| A uniform interface over arbitrary types without a common base | [[patterns/type-erasure]] |

## Questions

!!! question "1"
    To avoid repeating `accept` in every node class, someone writes it in the base class:
    ```cpp
    struct Expr {
      void accept(Visitor& v) const { v.visit(*this); }
    };
    ```
    Does that work?

<details markdown="1">
<summary>Answer</summary>

No. In `Expr::accept` the static type of `*this` is `const Expr`, and overload resolution, done at compile time, can only look among the candidates `visit(const Num&)`, `visit(const Add&)` and so on for one accepting a `const Expr`. There is no implicit conversion from base to derived, so no function is viable and the program is ill-formed; Clang 23 reports "no viable conversion from 'const Expr' to ...". If `Visitor` happened to have a `visit(const Expr&)`, it would be selected every time, and double dispatch would degrade to single dispatch.

`accept` must be written separately in each derived class so that the static type of `*this` equals the dynamic type. A CRTP intermediate layer, `template<class Self> struct Node : Expr { void accept(Visitor& v) const override { v.visit(static_cast<const Self&>(*this)); } };`, lets a template generate it for each class; the `Acceptor` above does exactly this.
</details>

!!! question "2"
    Does the following visitor compile for a `std::variant<int, long>`?
    ```cpp
    std::visit(overloaded{
      [](int)    { return 1; },
      [](double) { return 2; },
    }, v);
    ```

<details markdown="1">
<summary>Answer</summary>

No. The `int` branch matches `int` exactly, so that's fine; the problem is `long`. `long` to `int` is an integral conversion and `long` to `double` a floating-integral conversion; both have Conversion rank ([[over.ics.scs]] table 19), neither is better than the other, and the call with `long` is ambiguous. [[variant.visit#5]] requires the call to be valid for every combination, so the whole `visit` is ill-formed. libc++ in our tests again reports "no matching function for call to '__invoke'", with a note pointing to `__alt<1UL, long>` as the culprit.

This shows that exhaustiveness checking checks callability: with only the `[](double)` branch, both `int` and `long` can convert to it, the program actually compiles, and both integer types silently take the `double` branch.
</details>

!!! question "3"
    Replace the `std::visit(..., a, b)` above with a visit of three variants of 5 types each. How many combinations must the visitor handle? Does the standard impose a complexity requirement on this call? How does libc++ implement it?

<details markdown="1">
<summary>Answer</summary>

5×5×5 = 125 combinations, and the visitor must be callable for every one, or the program is ill-formed ([[variant.visit#5]]). The standard imposes no complexity requirement on visiting more than one variant ([[variant.visit#8]]), because a table covering all combinations grows exponentially with the number of variants, and the standard doesn't want to force implementations to do that. libc++ still builds a 5×5×5 three-dimensional array of function pointers, indexed dimension by dimension with the three indices, constant time at run time; the cost moves to compile time: instantiating 125 dispatch functions and their object code.
</details>
