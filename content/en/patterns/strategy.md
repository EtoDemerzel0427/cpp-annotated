---
title: Five ways to write a strategy
summary: "Extracting the replaceable step of an algorithm and implementing the same pricing strategy with a virtual interface, std::function and its successors, a template parameter, a function pointer and std::variant; comparing ownership, run-time replaceability, size, allocation, levels of indirection, inlining and error messages, ending with a selection table."
tags: design patterns, strategy, virtual functions, std::function, variant, templates, type erasure
updated: 2026-10-19
---

!!! tldr
    - The strategy pattern hands the step of an algorithm that varies (here, the discount rule at checkout) to a replaceable object. C++ has at least five carriers for it: a virtual interface with `unique_ptr`, the `std::function` family, a template parameter, a function pointer, and `std::variant` with `std::visit`.
    - The five differ on a few questions: whether the strategy can be replaced at run time (templates can't), whether the set of strategies is open or closed (`variant` is closed), and who owns the strategy object (`function_ref` and function pointers own no state).
    - The cost on a hot path depends mainly on whether the call site can see the strategy's body. With Clang 23 `-O2`, templates and a `variant` with `visit` hoisted out of the loop can be inlined and vectorized, about 0.15 ns per call; virtual functions, `std::function` and function pointers are each one indirect call, about 0.9 ns per call.
    - `std::function` copies its target, so a stateful strategy silently splits into several copies; `function_ref` doesn't own its target and dangles when bound to a temporary; a lambda strategy that captures `this` breaks when the enclosing object is copied or destroyed.

## A replaceable step

Checkout computes prices by promotion rules: no discount, 20% off, or a coupon off the total. Rules will be added and may be switched at run time. The most direct approach hardcodes the rules in a `switch`:

```cpp run title="switch.cpp" ok
#include <cstdio>

enum class Rule { none, percent, coupon };

struct Checkout {
  Rule rule = Rule::none;
  int arg = 0;
  int total(int cents) const {
    switch (rule) {
      case Rule::none:    return cents;
      case Rule::percent: return cents * (100 - arg) / 100;
      case Rule::coupon:  return cents > arg ? cents - arg : 0;
    }
    return cents;
  }
};

int main() {
  Checkout c{Rule::percent, 20};
  std::printf("%d\n", c.total(1000));   // 800
}
```

Every new rule means changing `Checkout`, and rule parameters all have to squeeze into a single `arg`. The **strategy pattern** extracts the varying step into a separate object, and `Checkout` only calls it at the right moment. The five implementations below all use these three rules, with prices in cents.

## ① A virtual interface and `unique_ptr`

```cpp run title="virtual.cpp" ok
#include <cstdio>
#include <memory>

struct Pricing {
  virtual ~Pricing() = default;
  virtual int price(int cents) const = 0;
};
struct Percent final : Pricing {
  int pct;
  explicit Percent(int p) : pct(p) {}
  int price(int c) const override { return c * (100 - pct) / 100; }
};
struct Coupon final : Pricing {
  int off;
  explicit Coupon(int o) : off(o) {}
  int price(int c) const override { return c > off ? c - off : 0; }
};

class Checkout {
  std::unique_ptr<Pricing> pricing_;
public:
  explicit Checkout(std::unique_ptr<Pricing> p) : pricing_(std::move(p)) {}
  void set_pricing(std::unique_ptr<Pricing> p) { pricing_ = std::move(p); }
  int total(int cents) const { return pricing_->price(cents); }
};

int main() {
  Checkout c{std::make_unique<Percent>(20)};
  std::printf("%d\n", c.total(1000));            // 800
  c.set_pricing(std::make_unique<Coupon>(150));
  std::printf("%d\n", c.total(1000));            // 850
}
```

`price` is a **virtual function** ([[g:virtual-function]], [[class.virtual#1]]). `pricing_->price(cents)` is a virtual function call: what gets called is the final overrider in the dynamic type of `*pricing_` (the actual type of the object at run time, [[g:dynamic-type]]) ([[expr.call#2]]). A new strategy only needs to derive from `Pricing`, can be written in another translation unit, and `Checkout` doesn't need recompiling.

Ownership is expressed by `unique_ptr`: `Checkout` exclusively owns the strategy object and destroys it along with itself. The costs are one heap allocation per strategy, and `Checkout` can only be moved, not copied; copying would require adding a virtual `clone()` to `Pricing`. If someone else guarantees the strategy's lifetime, storing just a `const Pricing&` also works; the ownership trade-offs are in [[topics/ownership-and-smart-pointers]].

Two more details:

- `override` turns a wrong signature into a compile error ([[class.virtual#5]]). With a missing `const` and no `override`, the derived function is just a new function, the derived class remains abstract, and the error doesn't appear until `make_unique`; see the error comparison below.
- Calling `->` on an empty `unique_ptr` violates a precondition ([[unique.ptr.single.observers#5]]) and is UB, with no check at all.

## ② `std::function` and its successors

```cpp run title="function.cpp" ok
#include <cstdio>
#include <functional>

class Checkout {
  std::function<int(int)> pricing_;
public:
  explicit Checkout(std::function<int(int)> p) : pricing_(std::move(p)) {}
  void set_pricing(std::function<int(int)> p) { pricing_ = std::move(p); }
  int total(int cents) const { return pricing_(cents); }
};

int half(int c) { return c / 2; }

int main() {
  int pct = 20;
  Checkout c{[pct](int x) { return x * (100 - pct) / 100; }};
  std::printf("%d\n", c.total(1000));   // 800
  c.set_pricing(half);                  // function pointers work too
  std::printf("%d\n", c.total(1000));   // 500
  Checkout d = c;                       // copyable; the target is copied along
  std::printf("%d\n", d.total(1000));   // 500
}
```

`std::function<int(int)>` can hold any object callable with an `int` whose result converts to `int`: lambdas, function pointers, classes with `operator()`. Strategies no longer need a common base class; this technique is called **type erasure** ([[g:type-erasure]]), and how it works is covered in [[patterns/type-erasure]].

It has value semantics: copying a `function` copies its target object ([[func.wrap.func.con#3]]), so the target must be copyable ([[func.wrap.func.con#10]]). Not allocating for small targets is only a recommendation ([[func.wrap.func.con#15]]); libc++'s `function` in our tests is 32 bytes and stores targets of at most 16 bytes whose copy doesn't throw inside the object, allocating otherwise; measurements are in [[func.wrap.func]]. Calling an empty `function` throws `bad_function_call` ([[func.wrap.func.inv#2]]).

`std::function` has two design flaws: its `operator()` is a `const` member function, yet it calls the target as a non-const lvalue; and it requires the target to be copyable, so it can't hold a lambda that captures a `unique_ptr`. C++23 and C++26 each added a wrapper, and C++26 also added a non-owning reference:

| | Owns the target | Copyable | `const`, `&&`, `noexcept` in the signature | Empty state |
|---|---|---|---|---|
| `function` {{c++11}} | yes | yes | not supported | calling throws |
| `move_only_function` {{c++23}} | yes | no, move-only | supported | calling is UB |
| `copyable_function` {{c++26}} | yes | yes | supported | calling is UB |
| `function_ref` {{c++26}} | no | yes, trivially | `const`, `noexcept` | none |

The full comparison of all four is in [[func.wrap]].

!!! impl "Not yet implemented in libc++ in our tests"
    In LLVM 23's libc++, `__cpp_lib_move_only_function`, `__cpp_lib_copyable_function` and `__cpp_lib_function_ref` are all undefined, so the two snippets below can't be compiled in our tests and carry no verdict. The godbolt button on the code blocks also compiles them with GCC trunk.

For strategies that need exclusive resources, use `move_only_function`. With `const` in the signature, the target must be callable as a const lvalue (*is-callable-from* in [[func.wrap.move.class]]):

```cpp run title="move-only.cpp"
#include <functional>
#include <memory>
#include <vector>

struct PriceTable { std::vector<int> cap; };

struct Checkout {
  std::move_only_function<int(int) const> pricing;
  int total(int cents) const { return pricing(cents); }
};

int main() {
  auto table = std::make_unique<PriceTable>(PriceTable{{500}});
  Checkout c{[t = std::move(table)](int x) {
    return x < t->cap[0] ? x : t->cap[0];
  }};
  return c.total(1000) == 500 ? 0 : 1;
}
```

With `std::function<int(int)>` instead, this code is rejected at construction, because the `unique_ptr` in the closure cannot be copied ([[func.wrap.func.con#10]]).

When a strategy is used only during one call and doesn't need to be stored, make the parameter a `function_ref`. It stores only a pointer to the target and a function pointer ([[func.wrap.ref.class#1]]), without allocating or copying the target:

```cpp run title="function-ref.cpp"
#include <functional>
#include <span>

long sum(std::span<const int> xs,
         std::function_ref<int(int) const> pricing) {
  long s = 0;
  for (int x : xs) s += pricing(x);
  return s;
}

int main() {
  int pct = 20;
  int xs[] = {1000, 2000};
  return sum(xs, [pct](int x) { return x * (100 - pct) / 100; }) == 2400 ? 0 : 1;
}
```

The temporary lambda lives until the end of the whole call expression, so the reference stays valid while `sum` runs. Storing a `function_ref` is another matter; see the traps below.

## ③ A template parameter

```cpp run title="template.cpp" ok
#include <concepts>
#include <cstdio>

struct NoDiscount {
  int operator()(int c) const { return c; }
};
struct Percent {
  int pct;
  int operator()(int c) const { return c * (100 - pct) / 100; }
};

template <class Pricing>
  requires std::invocable<const Pricing&, int>
class Checkout {
  [[no_unique_address]] Pricing pricing_;
public:
  explicit Checkout(Pricing p = {}) : pricing_(p) {}
  int total(int cents) const { return pricing_(cents); }
};

int main() {
  Checkout a{Percent{20}};      // Checkout<Percent>
  Checkout<NoDiscount> b;
  std::printf("%d %d\n", a.total(1000), b.total(1000));   // 800 1000
  std::printf("%zu %zu\n", sizeof a, sizeof b);           // in our tests: 4 1
}
```

The strategy becomes part of the type and is chosen at compile time. `Checkout<Percent>` and `Checkout<NoDiscount>` are two unrelated types: they can't share a container, can't be swapped at run time, and each instantiation generates its own code. In return, the call site can see the strategy's body, the optimizer can inline it, and with `[[no_unique_address]]` ([[dcl.attr.nouniqueaddr#1]]) an empty strategy takes no extra space.

The standard library uses this approach extensively: the comparators of `std::sort` and `std::set`, the deleter of `unique_ptr`, the allocators and hash functions of containers are all template parameters. When one class has several such replaceable steps, that is [[patterns/policy-based-design]]. The `requires` clause makes an unsuitable strategy fail at the entry of the class template rather than inside a member function; see [[topics/concepts]].

Template parameters and run-time strategies aren't mutually exclusive: `Checkout<std::function<int(int)>>` is a `Checkout` whose strategy can be replaced at run time, leaving it to the user to decide whether to pay that cost.

## ④ A function pointer

```cpp run title="fnptr.cpp" ok
#include <cstdio>

int no_discount(int c) { return c; }
int half(int c) { return c / 2; }

struct Checkout {
  int (*pricing)(int) = no_discount;
  int total(int cents) const { return pricing(cents); }
};

int main() {
  Checkout c;
  std::printf("%d\n", c.total(1000));          // 1000
  c.pricing = half;
  std::printf("%d\n", c.total(1000));          // 500
  c.pricing = [](int x) { return x - 100; };   // a captureless lambda converts
  std::printf("%d\n", c.total(1000));          // 900
}
```

A function pointer is the lightest run-time strategy: 8 bytes, trivially copyable, no ownership issues, and no state. Only lambdas that capture nothing have a conversion function to a function pointer ([[expr.prim.lambda.closure#11]]), so the 20 in "20% off" either has to be hardcoded in the function or passed as an extra `void*` context argument, as C interfaces do.

Calling a function through a function pointer of a mismatched type is UB ([[expr.call#6]]), commonly seen when a function pointer is `reinterpret_cast` to another signature and called. Calling a null function pointer is UB as well.

## ⑤ `std::variant` and `std::visit`

```cpp run title="variant.cpp" ok
#include <cstdio>
#include <variant>

struct NoDiscount { int operator()(int c) const { return c; } };
struct Percent {
  int pct;
  int operator()(int c) const { return c * (100 - pct) / 100; }
};
struct Coupon {
  int off;
  int operator()(int c) const { return c > off ? c - off : 0; }
};

using Pricing = std::variant<NoDiscount, Percent, Coupon>;

struct Checkout {
  Pricing pricing;
  int total(int cents) const {
    return std::visit([cents](const auto& p) { return p(cents); }, pricing);
  }
};

int main() {
  Checkout c{Percent{20}};
  std::printf("%d\n", c.total(1000));   // 800
  c.pricing = Coupon{150};
  std::printf("%d\n", c.total(1000));   // 850
  std::printf("%zu\n", sizeof c);       // in our tests: 8
}
```

The available strategies are all listed in the type `Pricing`; the set is closed. The strategy object is embedded directly in the `variant` ([[variant.variant.general#1]]), with no allocation; `Checkout` can be copied and compared, and the strategies' parameters are plain to see.

Being closed cuts both ways. Adding a strategy means changing `Pricing`, and all code using it must be recompiled; conversely, the visitor must handle every alternative, or the program is ill-formed ([[variant.visit#5]]), so forgetting a strategy won't compile. `visit` on a single `variant` is required to take constant time ([[variant.visit#8]]), and is usually implemented as an index lookup table or branches. If the `variant` is valueless because a construction threw, `visit` throws `bad_variant_access` ([[variant.visit#7]]); the strategies in this example are all trivial types and never get into that state. More uses are in [[patterns/visitor]].

## Costs: measured in our tests

### Size and allocation

The program below constructs each of the five `Checkout`s once, counting allocations with a replacement `operator new`:

```cpp run title="five.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <memory>
#include <new>
#include <variant>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct NoDiscount { int operator()(int c) const { return c; } };
struct Percent { int pct; int operator()(int c) const { return c * (100 - pct) / 100; } };
struct Coupon  { int off; int operator()(int c) const { return c > off ? c - off : 0; } };

struct Pricing {
  virtual ~Pricing() = default;
  virtual int price(int cents) const = 0;
};
struct PercentPricing final : Pricing {
  int pct;
  explicit PercentPricing(int p) : pct(p) {}
  int price(int c) const override { return c * (100 - pct) / 100; }
};

struct CheckoutV {     // ①
  std::unique_ptr<Pricing> strategy;
  int total(int c) const { return strategy->price(c); }
};
struct CheckoutF {     // ②
  std::function<int(int)> strategy;
  int total(int c) const { return strategy(c); }
};
template <class S>
struct CheckoutT {     // ③
  [[no_unique_address]] S strategy;
  int total(int c) const { return strategy(c); }
};
int half(int c) { return c / 2; }
struct CheckoutP {     // ④
  int (*strategy)(int);
  int total(int c) const { return strategy(c); }
};
struct CheckoutX {     // ⑤
  std::variant<NoDiscount, Percent, Coupon> strategy;
  int total(int c) const {
    return std::visit([c](const auto& s) { return s(c); }, strategy);
  }
};

template <class F> void measure(const char* what, F make) {
  allocs = 0;
  auto c = make();
  std::printf("%-10s sizeof=%2zu allocs=%d total=%d\n",
              what, sizeof(c), allocs, c.total(1000));
}

int main() {
  measure("virtual",  [] { return CheckoutV{std::make_unique<PercentPricing>(20)}; });
  measure("function", [] { return CheckoutF{Percent{20}}; });
  measure("template", [] { return CheckoutT<Percent>{{20}}; });
  measure("fnptr",    [] { return CheckoutP{half}; });
  measure("variant",  [] { return CheckoutX{Percent{20}}; });
}
// Output with libc++ in our tests (arm64 macOS):
//   virtual    sizeof= 8 allocs=1 total=800
//   function   sizeof=32 allocs=0 total=800
//   template   sizeof= 4 allocs=0 total=800
//   fnptr      sizeof= 8 allocs=0 total=500
//   variant    sizeof= 8 allocs=0 total=800
```

The `variant`'s 8 bytes are the largest alternative (4 bytes) plus the index. `std::function` holding a `Percent` doesn't allocate, because a 4-byte target fits in its internal buffer; a lambda capturing three `int`s would allocate once ([[func.wrap.func]] has the full measurements).

### One call on a hot path

Put the call in a function of its own and look at the arm64 code generated at `-O2`. The strategy object comes in as a parameter, so the compiler doesn't know its concrete type:

<div class="compare" markdown="1">

```text
; ① p.price(x)
ldr  x8, [x0]       ; load the vptr
ldr  x2, [x8, #16]  ; load the vtable slot
br   x2             ; indirect jump
```

```text
; ② f(x), libc++ std::function
stur w1, [x29, #-4] ; store x on the stack
ldr  x0, [x0, #24]  ; load __f_
cbz  x0, LBB1_2     ; throw if empty
ldr  x8, [x0]       ; load the vptr
ldr  x8, [x8, #48]  ; load the vtable slot
sub  x1, x29, #4    ; pass &x
blr  x8             ; indirect call
```

</div>

A virtual call is two memory loads plus an indirect jump. libc++'s `function` is also a virtual call internally, preceded by a null check, and the argument has to be passed through an address on the stack because the internal virtual function takes it as `int&&`. For a function pointer `f(x)`, the pointer is already in a register; apart from two register-to-register `mov`s, only a single `br x2` remains.

<div class="compare" markdown="1">

```text
; ③ p(x), template parameter: inlined directly
ldr   w8, [x0]      ; p.pct
mov   w9, #100
sub   w8, w9, w8
mul   w8, w8, w1
; ... multiply and shift for the division by 100
ret
```

```text
; ⑤ visit: branch on the index, then inlined
ldr   w8, [x0, #4]  ; load the index
cmp   w8, #0
b.le  LBB4_3        ; NoDiscount
cmp   w8, #1
b.ne  LBB4_5        ; Coupon
; Percent's code is right here
```

</div>

All three strategies of the `variant` are inlined, with no indirect calls. libc++'s `visit` is implemented with a table of function pointers in the source, but the table is small and the index's range is known, so Clang turns it into comparisons and branches.

### When the compiler can see the concrete type

When the call site can see the object's concrete type, the indirection of virtual functions and `std::function` disappears too. At `-O2` in our tests:

- `int f(const PercentPricing& p, int x) { return p.price(x); }`: `PercentPricing` is a `final` class, so `price` cannot be overridden again, and Clang inlines it directly. Remove `final` and it's back to the three-instruction virtual call.
- `make_unique<PercentPricing>(20)` followed by a call in the same function, or constructing a `std::function` and then calling it: both are fully inlined, and even the heap allocation is eliminated.

So the cost of indirect calls appears where the strategy is stored and called elsewhere, which is exactly the typical use of the strategy pattern.

### Calls in a loop

Summing one million prices, repeated 100 times, with the five versions in separate translation units and no LTO. In our tests (Apple Silicon, Clang 23 `-O2`), the average time per strategy call:

| Approach | ns/call | What happens in the loop |
|---|---|---|
| ① virtual function | 0.92 | each iteration reloads the vptr and vtable slot, then makes an indirect call |
| ② `std::function` | 0.94 | each iteration checks for null, loads two levels of pointers, makes an indirect call |
| ④ function pointer | 0.92 | one indirect call per iteration |
| ⑤ `visit` inside the loop | 0.82 | each iteration branches on the index; all three strategies inlined, not vectorized |
| ⑤ `visit` outside the loop | 0.15 | strategy chosen first; the loop body has a fixed type and is vectorized |
| ③ template parameter | 0.16 | inlined, then vectorized |

This is a microbenchmark whose strategy body is only a few instructions with perfectly predictable branches; the gaps come mainly from whether inlining and vectorization are possible, not from the indirect jump itself. When the strategy body is heavier, the differences between these approaches are diluted.

The two `variant` rows illustrate a practical technique: hoist `visit` out of the loop and put the loop inside the lambda, so each alternative gets its own inlined, vectorizable loop:

```cpp
long sum(const Pricing& v, std::span<const int> xs) {
  return std::visit([xs](const auto& p) {
    long s = 0;
    for (int x : xs) s += p(x);
    return s;
  }, v);
}
```

The virtual version can do something similar: add a virtual function to the interface that processes a whole batch, trading one indirect call for an entire loop.

## What the errors look like

When a strategy is wrong, the diagnostics of the five approaches differ greatly. Here is Clang 23's first error for each:

| What is wrong | Approach | Error |
|---|---|---|
| Overrider missing `const`, no `override` | ① | inside `make_unique<Bad>()`: "allocating an object of abstract class type 'Bad'", with the note "unimplemented pure virtual method 'price'" |
| Same, with `override` | ① | at the declaration: "non-virtual member function marked 'override' hides virtual member function" |
| Strategy has the wrong call signature | ② | "no viable conversion from 'Wrong' to 'std::function<int (int)>'" |
| Same, unconstrained template | ③ | in the body of `total`: "no matching function for call to object of type 'const Wrong'" |
| Same, template with `requires` | ③ | at the point of use: "constraints not satisfied for class template 'Checkout'", with a note on which constraint failed |
| A capturing lambda assigned to a function pointer | ④ | "no viable conversion from '(lambda at …)' to 'int (*)(int)'" |
| The visitor misses a strategy | ⑤ | inside libc++'s `<variant>`: "no matching function for call to '__invoke'", followed by about 70 lines of instantiation stack |

The `variant` error is the hardest to read, but the mistake it catches can't be checked at all with open-set approaches: forgetting to handle a strategy.

## Traps

### `std::function` copies stateful strategies

```cpp run title="stateful.cpp" ok
#include <cstdio>
#include <functional>

struct CountingPricing {   // stateful: counts calls
  int calls = 0;
  int operator()(int c) { ++calls; return c; }
};

int main() {
  CountingPricing counter;
  std::function<int(int)> s = counter;     // makes a copy of counter
  s(100); s(200);
  std::printf("%d\n", counter.calls);      // 0

  auto s2 = s;                             // copies again, along with calls == 2
  s2(300);
  std::printf("%d %d\n", s.target<CountingPricing>()->calls,
                         s2.target<CountingPricing>()->calls);   // 2 3

  std::function<int(int)> r = std::ref(counter);   // stores only a reference
  r(100);
  std::printf("%d\n", counter.calls);      // 1
}
```

A `function` owns a copy of its target, and the original `counter` is never called. Copying the `function` copies the state again, and from then on the two count separately. Note that `CountingPricing::operator()` is not `const`, yet it can be called through the `const` `function::operator()` ([[func.wrap.func.inv#1]] calls the target as a non-const lvalue). `copyable_function<int(int) const>` would reject such a target; putting `const` into the signature is how the new wrappers close this gap.

To share state, wrap it in `std::ref`, so the `function` stores only a reference, at the price of ensuring `counter` lives long enough yourself. Standard algorithms also take function objects by value, so stateful comparators and predicates get copied too.

### `function_ref` bound to a temporary

When a `function_ref` is constructed from a callable object, it stores that object's address ([[func.wrap.ref.ctor#8]]). A temporary in parameter position lives until the end of the call, but a `function_ref` stored in a variable outlives the temporary:

```cpp run title="dangling-ref.cpp"
#include <functional>

struct Percent {
  int pct;
  int operator()(int c) const { return c * (100 - pct) / 100; }
};

int main() {
  std::function_ref<int(int) const> r = Percent{20};   // the temporary is destroyed at the end of this line
  return r(1000);   // UB: called through a dangling address
}
```

This code can't be compiled in our tests, so it carries no verdict; by the standard it is UB. A `function_ref` constructed from a function pointer doesn't have this problem, because it stores the function pointer itself ([[func.wrap.ref.ctor#5]]), and functions are never destroyed. The same reasoning applies to storing a `function_ref` as a member: like `string_view`, it is suited only to parameters; the general rules of dangling are in [[topics/dangling-references]].

### A lambda strategy that captures `this`

```cpp run title="this-capture.cpp" ub
#include <cstdio>
#include <functional>
#include <memory>

struct Checkout {
  int points = 100;
  std::function<int(int)> strategy = [this](int c) { return c - points; };
  int total(int c) const { return strategy(c); }
};

int main() {
  auto a = std::make_unique<Checkout>();
  Checkout b = *a;                      // the this inside b.strategy still points to *a
  a->points = 300;
  std::printf("%d\n", b.total(1000));   // 700, reading a's points
  a.reset();
  std::printf("%d\n", b.total(1000));   // UB: *a has been destroyed
}
```

The lambda in the default member initializer captures the `this` at construction. The implicit copy constructor copies member by member, so `b.strategy` copies the closure, and the pointer in the closure is still `a`'s address. ASan in our tests reports heap-use-after-free at the second `total`.

The fix is not to let the strategy remember its host, and to pass in what it needs as arguments instead:

<div class="compare" markdown="1">

```cpp
// captures this: after a copy it points to the old object
std::function<int(int)> strategy =
  [this](int c) { return c - points; };
int total(int c) const {
  return strategy(c);
}
```

```cpp
// the host is passed in as an argument
std::function<int(int, const Checkout&)>
  strategy = [](int c, const Checkout& k) {
    return c - k.points;
  };
int total(int c) const {
  return strategy(c, *this);
}
```

</div>

Another approach is to forbid copying and moving `Checkout`. The general rules of capturing `this` are in [[topics/lambdas]].

## How to choose

| Need | Approach | Reason |
|---|---|---|
| Fixed at compile time, performance matters | ③ template parameter | inlinable and vectorizable, empty strategies take no space; costs code bloat, and each instantiation is a different type |
| A fixed, known set of strategies, with value semantics | ⑤ `variant` | no allocation, copyable and comparable, a missed strategy is an error; adding one requires recompiling |
| Strategies from external modules or plugins, an open set | ① virtual interface | new strategies just derive; a full interface of several virtual functions is possible |
| A single call signature, strategies from varied sources | ② `function`; `move_only_function` when move-only | no base class needed; lambdas, functions and function objects all work |
| Used only during one call | a `function_ref` parameter, or a function template parameter | non-owning, no allocation; don't store it |
| Stateless, interoperating with C interfaces | ④ function pointer | smallest, trivially copyable; state must be passed separately |

Summary of the five approaches (sizes and allocations are for libc++ on arm64 in our tests):

| | Replaceable at run time | Set | Ownership | `sizeof` | Allocation | Hot call |
|---|---|---|---|---|---|---|
| ① virtual interface + `unique_ptr` | yes | open | exclusive, on the heap | 8 | 1 per strategy | load vptr, load slot, indirect call |
| ② `std::function` | yes | open | holds a copy | 32 | 1 for large targets | null check, two pointer loads, indirect call |
| ③ template parameter | no | open (at compile time) | by value | the strategy itself | 0 | inlined |
| ④ function pointer | yes | open | stateless | 8 | 0 | indirect call |
| ⑤ `variant` | yes, among the listed types | closed | by value | largest alternative + index | 0 | branch, then inlined |

## Questions

!!! question "1"
    The virtual-function version in "Calls in a loop" above sums `p.price(prices[i])` in a loop. Clang reloads `p`'s vptr on every iteration. `p` is a `const Pricing&`, and nothing in the loop modifies it; why can't these two loads be hoisted out of the loop?

<details markdown="1">
<summary>Answer</summary>

The called `price` is opaque to the compiler, and in principle it could end the lifetime of `*p` and create an object of another derived class in the same storage with placement new, after which the vptr would change. By [[basic.life#9]], a new object of a different type cannot transparently replace the old one, and calling through the old reference `p` afterwards is UB, so by the standard the compiler could actually assume the vptr doesn't change. Clang doesn't make this assumption by default; with `-fstrict-vtable-pointers` in our tests, the vptr and vtable slot are loaded only once before the loop, leaving just `blr` in the loop body. This option requires code to obtain a new pointer with `std::launder` after replacing an object; see [[basic.life]].
</details>

!!! question "2"
    Which of these lines compile? Why?
    ```cpp
    void f(int k) {
      int (*a)(int) = [](int c) { return c / 2; };
      int (*b)(int) = [k](int c) { return c - k; };
      std::function<int(int)> g = [k](int c) { return c - k; };
    }
    ```

<details markdown="1">
<summary>Answer</summary>

`a` and `g` compile; `b` doesn't. Only the closure type of a lambda that captures no entities has a conversion function to a function pointer ([[expr.prim.lambda.closure#11]]); `b`'s closure must store `k`, and a function pointer has no room for that state; Clang reports "no viable conversion". `std::function` stores the closure object along with `k`, so `g` is fine.
</details>

!!! question "3"
    The `std::variant<NoDiscount, Percent, Coupon>` strategy should support a fourth rule loaded from a configuration file, whose implementation lives in a separately compiled plugin. Is `variant` still suitable?

<details markdown="1">
<summary>Answer</summary>

No. A `variant`'s alternatives must all be listed where it is defined, and the plugin's type doesn't exist yet when `Checkout` is compiled. A common compromise adds an open alternative to the `variant`, e.g. `std::variant<NoDiscount, Percent, Coupon, std::unique_ptr<Pricing>>`: known rules keep value semantics and inlining, while unknown rules go through a virtual interface. The cost is that visitors must handle one more case, and the `variant`'s size becomes a pointer plus the index.
</details>
