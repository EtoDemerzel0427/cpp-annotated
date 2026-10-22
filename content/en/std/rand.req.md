---
title: Requirements for random number facilities
summary: "What a type must satisfy to count as a seed sequence, a URBG, an engine, an engine adaptor or a distribution; what == compares for engines and distributions; and which types template parameters such as IntType, RealType and UIntType accept."
updated: 2026-10-19
---

!!! tldr
    - The concept `uniform_random_bit_generator` checks only syntax: callable as a non-const lvalue, returns an unsigned integral type, has `constexpr` static `min() < max()`. Whether it is uniform can only be checked statistically.
    - An engine is specified by its state, transition algorithm and generation algorithm. Two engines being `==` means the infinite sequences they will produce are the same, not that their internal bytes are the same.
    - A distribution may have internal state (such as a cached second normal value), which `reset()` clears; `d(g, p)` generates with temporary parameters without changing `d`.
    - The textual representation of engines is portable across implementations; the textual format of distributions is implementation-defined.
    - `uniform_int_distribution<char>`, `<bool>` and `<const int>` are all ill-formed; `signed char` and `unsigned char` are fine.

[rand.req] defines no concrete classes; it only specifies what a type must satisfy to count as a seed sequence, URBG, engine, adaptor or distribution. The standard's own `mt19937` and `normal_distribution` are specified against these requirements, and user-written types that meet them can be combined freely with the standard components. For an overview of each kind of entity, see [[rand]].

## Uniform random bit generators ([rand.req.urng])

First, a generator written by hand:

```cpp run title="urbg-concept.cpp" ok
#include <cstdint>
#include <random>

struct Counter {
  using result_type = std::uint32_t;
  static constexpr result_type min() { return 0; }
  static constexpr result_type max() { return 0xFFFF'FFFF; }
  result_type n = 0;
  result_type operator()() { return n++; }
};
static_assert(std::uniform_random_bit_generator<Counter>);

// no static min()/max()
using Lambda = decltype([s = 0u]() mutable { return s++; });
static_assert(!std::uniform_random_bit_generator<Lambda>);

struct Degenerate {                     // min < max does not hold
  using result_type = unsigned;
  static constexpr unsigned min() { return 5; }
  static constexpr unsigned max() { return 5; }
  unsigned operator()() { return 5; }
};
static_assert(!std::uniform_random_bit_generator<Degenerate>);

struct Signed {                         // the result must be unsigned
  static constexpr int min() { return 0; }
  static constexpr int max() { return 9; }
  int operator()() { return 3; }
};
static_assert(!std::uniform_random_bit_generator<Signed>);

int main() {}
```

`Counter` is obviously not random, yet it satisfies the concept. A concept can check only syntax; that every value is equally likely can be ensured only by documentation and statistical testing. Passing `Counter` to a distribution is well-formed and gives a deterministic sequence, which is handy for testing distribution implementations.

¶1 A **uniform random bit generator** ([[g:uniform-random-bit-generator]]) `g` is a function object returning unsigned integers, with every value in its range (ideally) equally likely. Since C++20 there is a corresponding concept:

```cpp
template<class G>
  concept uniform_random_bit_generator =
    invocable<G&> && unsigned_integral<invoke_result_t<G&>> &&
    requires {
      { G::min() } -> same_as<invoke_result_t<G&>>;
      { G::max() } -> same_as<invoke_result_t<G&>>;
      requires bool_constant<(G::min() < G::max())>::value;
    };
```

Item by item:

- `invocable<G&>`: called as a non-const lvalue, so `operator()` may, and usually must, modify state;
- `unsigned_integral`: the result is an unsigned integral type. `bool` also satisfies `unsigned_integral`; the concept itself does not exclude it;
- `G::min()` and `G::max()` are static members whose return type is exactly that of `g()`;
- `bool_constant<(G::min() < G::max())>` forces both to be constant expressions and `min < max`.

¶2 To model the concept, the semantic requirements must also hold: `G::min() <= g()`, `g() <= G::max()`, and `g()` has amortized constant complexity.

¶3 The **named requirement** *uniform random bit generator* adds two things to the concept: `invoke_result_t<G&>` must be an unsigned integer type ([[basic.fundamental]]; `bool` does not count), and there must be a nested `result_type` naming the same type. Older code and template parameters named `URBG` rely on this `result_type`.

## Seed sequences ([rand.req.seedseq])

¶1 A **seed sequence** ([[g:seed-sequence]]) consumes a sequence of integers and then produces, on request, any number of unsigned integers in [0, 2³²). A note explains the purpose: to avoid several engines producing duplicate random streams, particularly useful in programs needing many engines. The seed sequence the standard provides is `seed_seq` ([[rand.util]]).

The requirements of Table 126 (`S` is the type, `q` a value, `r` a possibly const value):

| Expression | Requirement |
|---|---|
| `S::result_type` | an unsigned integer type of at least 32 bits |
| `S()` | the same initial state as all other default-constructed `S` |
| `S(ib, ie)`, `S(il)` | internal state depends on some or all of the bits of the input sequence |
| `q.generate(rb, re)` | fills `[rb, re)` with 32-bit quantities; the result depends on the input at construction and may also depend on the history of previous `generate` calls |
| `r.size()` | how many 32-bit units `param` will write |
| `r.param(ob)` | writes a sequence of 32-bit units such that constructing another `S` from it gives a state indistinguishable from `r` |

`generate` is not a const member and may depend on call history. So if the same seed sequence object is fed to two engines in turn, the two engines may get different seeds. The standard `seed_seq` happens not to depend on history, but generic code cannot assume that. `size` and `param` are for saving and rebuilding a seed sequence.

## Random number engines ([rand.req.eng])

¶1 A **random number engine** ([[g:random-number-engine]]) is a URBG that additionally meets requirements for seeding, input/output and so on.

### State, transition and generation (¶2–¶3)

¶2 At any point an engine `e` is in some state eᵢ (i ≥ 0), and after construction in its initial state e₀. A state can be established by a constructor, `seed`, assignment, or `operator>>`.

¶3 The specification of each engine must define three things:

1. the size of the state, as a multiple of the size of `result_type`;
2. the **transition algorithm** TA, which advances eᵢ to its successor state eᵢ₊₁;
3. the **generation algorithm** GA, which maps a state to a `result_type` value.

`e()` advances the state to eᵢ₊₁ = TA(eᵢ) and returns GA(eᵢ). GA acts on the state before the transition, but its definition may refer to the result of the transition. For example, the linear congruential engine defines GA(xᵢ) = xᵢ₊₁, returning exactly the new state ([[rand.eng]]).

### Key points of Table 127 (¶4)

| Expression | Semantics |
|---|---|
| `E()` | the same initial state as all other default-constructed `E` |
| `E(s)` | initial state determined by a single `result_type` value `s` |
| `E(q)` | initial state depends on a single call to `generate` on the seed sequence `q` |
| `e.seed()`, `e.seed(s)`, `e.seed(q)` | postconditions `e == E()`, `e == E(s)`, `e == E(q)` respectively |
| `e()` | advances to TA(eᵢ) and returns GA(eᵢ); amortized constant complexity |
| `e.discard(z)` | advances to eᵢ₊z, with effect equivalent to calling `e()` z times in a row |
| `x == y` | if and only if the infinite sequences produced by infinitely many future calls to `x` and `y` are the same |

`==` compares future behavior, not internal representation. Two engines with different internal bytes but identical future output must compare equal; for example, the cached outputs in `philox_engine` can be rebuilt from the key and counter. Conversely, equal engines are substitutable for each other without changing the observable behavior of the program.

Footnote 220 points out that `discard` can often be implemented far faster than a loop in an engine-specific way: a linear congruential engine can jump by fast exponentiation, and `philox_engine` only needs to change its counter. The standard requires only that it be no slower than the loop; libc++'s `mersenne_twister_engine::discard` simply calls `operator()` in a loop.

¶5 Engines must be copy constructible and copy assignable, with complexity no worse than O(size of state). Copying an `mt19937` copies about 2.5 KB of state. Passing engines by value is both slow and error-prone: the copy is advanced, the original is not, and the next call yields the same numbers again.

### Textual representation (¶6–¶17)

On a hosted implementation, `os << x` writes the textual representation of `x`'s current state in decimal, left-aligned, space-filled, and then restores the stream's format flags (¶7–¶11). `is >> v` reads the state back; on a read failure `v` is unchanged and `failbit` is set (¶12–¶17). After writing and reading back, `x == v`, provided neither is invoked in between.

The content of the textual representation is specified by each engine ([[rand.eng]]), so an `mt19937` state written by one implementation can be read by another.

```cpp run title="engine-roundtrip.cpp" ok
#include <cassert>
#include <random>
#include <sstream>

int main() {
  std::mt19937 a(42);
  a.discard(100);
  std::stringstream ss;
  ss << a;              // save the full state (624 numbers)
  std::mt19937 b;
  ss >> b;              // restore
  assert(a == b);       // compares future sequences
  assert(a() == b());
}
```

## Engine adaptors ([rand.req.adapt])

¶1 A **random number engine adaptor** ([[g:random-number-engine-adaptor]]) `a` is an engine that takes values produced by another engine `b` (the **base engine**) and applies some algorithm to obtain a sequence with different randomness properties. `a.base()` returns a const reference to the base engine.

¶2–¶9 carry the engine requirements over to adaptors: default construction, `A(s)`, `A(q)` and the `seed` overloads all forward to the base engine; `a1 == a2` if and only if their base engines are equal.

¶10 also requires: the complexity of each function does not exceed that of the corresponding function on the base engine; the adaptor's state includes the base engine's state; copying an adaptor copies the base engine's state; and the textual representation includes the base engine's textual representation.

!!! lawyer "== looks only at the base engine?"
    ¶4 says two adaptors compare equal if their base engines are equal. But Table 127 requires an engine's `==` to mean the future sequences are the same. Two `discard_block_engine`s with equal base engines but different in-block counts obviously have different future sequences. Read together, ¶4 can only be understood as a simplified description for adaptors constructed the same way and put through the same operations. libc++'s `discard_block_engine::operator==` compares both the base engine and the count, and `shuffle_order_engine` compares both the internal table and the cached value.

## Random number distributions ([rand.req.dist])

¶1 A **random number distribution** ([[g:random-number-distribution]]) `d` is a function object returning values distributed according to some probability density function p(z) or discrete probability function P(zᵢ). ¶2 A probability function usually contains externally supplied quantities called the distribution's **parameters**, written p(z | a, b) or p(z | {p}).

### Key points of Table 128 (¶3)

| Expression | Semantics |
|---|---|
| `D::param_type` | the parameter pack type, written `P` below |
| `D()`, `D(p)` | default parameters, or constructed with the parameters in `p` |
| `d.reset()` | subsequent uses of `d` do not depend on values produced by any engine before the reset |
| `x.param()`, `d.param(p)` | read and write the parameters; `D(p).param() == p` |
| `d(g)` | successive calls with the same `g` give results distributed per p(z \| {d.param()}); invokes `g` a constant number of times on average |
| `d(g, p)` | generates with parameters `p` without changing `d`'s own parameters |
| `x.min()`, `x.max()` | the greatest lower bound and least upper bound of possible return values |
| `x == y` | the parameters are equal, and when `g1 == g2` the two will produce the same future sequences |

The existence of `reset` shows that distributions may have internal state. The typical example is the Box–Muller or polar method for the normal distribution, which computes two values at once and caches one; `reset` clears such caches (the question in [[rand]] demonstrates its effect).

`d(g, p)` lets one distribution object generate with different parameters. In the shuffle below, the upper bound differs at every step:

```cpp run title="dist-param.cpp" ok
#include <random>
#include <utility>
#include <vector>

template<class T, class G>
void shuffle_vec(std::vector<T>& v, G& g) {
  std::uniform_int_distribution<std::size_t> d;
  using P = decltype(d)::param_type;
  for (std::size_t i = v.size(); i > 1; --i)
    std::swap(v[i - 1], v[d(g, P(0, i - 1))]);
}

int main() {
  std::vector<int> v{1, 2, 3, 4, 5};
  std::mt19937 g(1);
  shuffle_vec(v, g);
}
```

### Other requirements (¶4–¶20)

- ¶4 Distributions are copy constructible and copy assignable.
- ¶5 Calling `os << d` or any const member function between two calls to `d(g)` does not change the sequence produced. Querying parameters or printing state does not disturb the random stream.
- ¶6 If `x` is written out and read back into a `y` of the same type, `y(g)` thereafter produces the same sequence as `x(g)`. The textual representation includes the parameters and internal data, such as the normal distribution's cached value. The textual format is implementation-defined, and reading across implementations is not guaranteed, unlike engines.
- ¶7 Whether `D::param_type` is a nested class or a typedef is unspecified. So you cannot forward-declare `std::normal_distribution<double>::param_type`.
- ¶8–¶10 `P` is copyable and equality comparable; for each constructor of `D` taking parameters, `P` has a constructor with the same parameters; for each member function of `D` returning a parameter, `P` has a member function of the same name; `P` declares `using distribution_type = D;`.
- ¶11–¶20 Stream insertion and extraction; on a read failure `d` is unchanged.

## Restrictions on template arguments ([rand.req.genl])

```cpp title="inttype.cpp" error
#include <random>

std::uniform_int_distribution<signed char> a(-5, 5);    // OK
std::uniform_int_distribution<unsigned char> b(0, 9);   // OK
std::uniform_int_distribution<char> c;      // error: char is not an IntType
std::uniform_int_distribution<const int> d; // error: cv-qualified
std::linear_congruential_engine<unsigned char, 3, 1, 0>
    e;                          // error: UIntType narrower than short
```

¶1 When a template parameter in [rand] is not constrained by a concept, the parameter's name itself states the requirements on the argument:

| Parameter name | The argument must be | Consequence of violation |
|---|---|---|
| `Sseq`, `URBG`, `Engine`, `RealType`, `IntType`, `UIntType` | a cv-unqualified type (¶1.1) | ill-formed |
| `Sseq` / `URBG` / `Engine` | meets the seed sequence / URBG / engine requirements (¶1.2–¶1.4) | violates library requirements, UB |
| `RealType` | a standard floating-point type, or an extended floating-point type chosen by the implementation (¶1.5) | ill-formed |
| `IntType` | a standard signed or unsigned integer type; an extended integer type with width between that of `char` and `long long`; or another integer type chosen by the implementation (¶1.6) | ill-formed |
| `UIntType` | a standard or extended unsigned integer type with width between that of `short` and `long long`; or another unsigned integer type chosen by the implementation (¶1.7) | ill-formed |

There are only five standard signed integer types: `signed char`, `short`, `int`, `long` and `long long` ([[basic.fundamental]]); `char`, `bool` and the various character types are not among them. So `uniform_int_distribution<char>` is ill-formed, while `uniform_int_distribution<signed char>` (usually just `int8_t`) is valid. `unsigned char` can be an `IntType` but not a `UIntType`, because an engine's `UIntType` must be at least as wide as `short`. For random booleans, use `bernoulli_distribution`.

!!! impl "libc++"
    libc++ checks `IntType` with a whitelist and a `static_assert`, so `char`, `bool` and `const int` all get "IntType must be a supported integer type". `__int128` is accepted, as another integer type chosen by the implementation. `UIntType = unsigned char`, however, is not checked directly: merely declaring an object of `linear_congruential_engine<unsigned char, 3, 1, 0>` compiles fine, and only calling `operator()` errors in the instantiation of an internal template. Per ¶1.7 this should be diagnosed at instantiation, so the last declaration in the example above does not actually error on libc++.

¶3 Any constructor in [rand] that can be called with a single argument and that satisfies one of the requirements in this subclause must be `explicit`. So `std::mt19937 g = 42;` is ill-formed, and you must write `std::mt19937 g(42);`. That way `void f(std::mt19937)` does not silently construct a new engine from `f(42)`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[rand.req.genl] ¶2: in [rand], "x is some kind of iterator" reads as "x is a value of a type meeting the corresponding iterator requirements".

[rand.req.eng] ¶4 also lists `E(x)` (compares equal to `x`) and the complexity of each operation: construction, `seed` and `==` are all O(size of state); `E(q)` is of the same order as `q.generate` filling a sequence of the state's size; `discard(z)` is no worse than z calls to `e()`.

</details>

## Questions

!!! question "Question 1"
    Are `std::uniform_int_distribution<bool>` and `std::uniform_int_distribution<std::int8_t>` well-formed? What if, on some platform, `std::int8_t` is an extended integer type rather than `signed char`?

<details markdown="1">
<summary>Answer</summary>

`bool` is neither a standard nor an extended integer type, so unless the implementation puts it in its own chosen set, it is ill-formed per [rand.req.genl] ¶1.6. libc++ rejects it.

`int8_t` is usually an alias for `signed char`, a standard signed integer type, so it is well-formed. If it is an extended integer type, ¶1.6 requires its width to be no less than that of `char` and no greater than that of `long long`; 8 bits equals the width of `char`, so it is also well-formed.
</details>

!!! question "Question 2"
    After `std::mt19937 a, b; b.discard(1); a();`, is `a == b`? Are their internal bytes necessarily the same?

<details markdown="1">
<summary>Answer</summary>

They are equal. `discard(1)` is equivalent to calling `b()` once (Table 127), after which the two have the same infinite future sequences, so they compare equal.

The standard does not care about internal bytes; `==` is defined by future behavior. The two paths of `mt19937` perform exactly the same operations, so the bytes are in fact the same too; but a general engine may let `discard` take a jumping shortcut, reaching a state with a different representation and the same future sequence, and those must compare equal as well.
</details>
