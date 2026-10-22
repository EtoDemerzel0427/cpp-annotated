---
title: Random number generation
summary: "<random> splits random numbers into a source of bits (engines) and a transformation (distributions); which parts are reproducible across implementations, how to seed correctly, and where rand()/srand() stand."
updated: 2026-10-19
---

!!! tldr
    - `<random>` produces random numbers in two steps: an engine produces uniform unsigned integers, and a distribution transforms them into the desired form. The two combine as `d(g)`.
    - Engine algorithms are specified bit for bit, so the same seed produces the same sequence on any implementation; distribution algorithms are implementation-defined, so switching standard libraries may change the results.
    - `std::mt19937 g(seed)` seeds from a single 32-bit integer, so there are at most 2³² initial states. Use `seed_seq` when you need more entropy.
    - The formulas in `<random>` are computed over the mathematical reals; implementations are responsible for avoiding overflow in intermediate results.
    - The algorithm of `rand()` is unspecified and it may race, and `rand() % n` is biased; none of the engines in `<random>` are cryptographically secure either.

## Starting from rand() % 6

```cpp run title="dice.cpp" ok
#include <cstdlib>
#include <random>

int roll_c() { return std::rand() % 6 + 1; }    // biased

int roll_cpp(std::mt19937& g) {
  std::uniform_int_distribution<int> die(1, 6);
  return die(g);                                // each face has probability exactly 1/6
}

int main() {
  std::mt19937 g(2024);
  return roll_c() + roll_cpp(g) > 0 ? 0 : 1;
}
```

The C approach welds two things together: where the bits come from (what algorithm `rand` uses and where its state lives are both unspecified), and how the bits become a face from 1 to 6 (modulo, which is biased; see below).

`<random>` separates them. The side that produces bits is a **uniform random bit generator** (URBG): an object that can be called repeatedly, returning an unsigned integer each time, with every value in its range (ideally) equally likely. One with deterministic, seedable state is a **random number engine**, such as the Mersenne Twister engine `mt19937`. The side that transforms is a **random number distribution**, such as `uniform_int_distribution`.

There is only one interface between the two: a distribution's `operator()` takes an lvalue reference to any URBG. So any engine can be paired with any distribution, including user-written engines and distributions.

## Four kinds of entities ([rand.general] ¶2)

¶2 The standard divides the components of `<random>` into four kinds. These category names refer to the types meeting the corresponding requirements, to objects of those types, and to templates whose instantiations are those types.

| Kind | What it is | Examples |
|---|---|---|
| URBG | function object: `g()` returns an unsigned integer; has static `min()`/`max()` | `random_device`, and all the engines below |
| engine | a URBG with deterministic state that can be seeded, compared and serialized | `mt19937`, `minstd_rand`, `philox4x32` |
| engine adaptor | an engine wrapping another engine (the base engine) | `discard_block_engine`, `shuffle_order_engine` |
| distribution | function object: `d(g)` uses a URBG to produce values following some distribution | `uniform_int_distribution`, `normal_distribution` |

The precise requirements for each kind are in [[rand.req]], the concrete engines and adaptors in [[rand.eng]], and distributions in [[rand.dist]].

The note in ¶2 says the design aims to let any URBG object `e` be bound to any distribution object `d`, giving a nullary function object like `bind(d, e)`. Today you would more often write a lambda `[&] { return d(e); }`. With `bind`, note that it copies `e`, so each call advances the copy; to share the original engine, write `bind(d, ref(e))`.

## result_type and computational conventions (¶3–¶5)

¶3 Each entity has an associated arithmetic type `result_type`, called `T`. By `T`, entities fall into three kinds:

- ¶3.1 `T` is `bool`: a **boolean-valued** entity, such as `bernoulli_distribution`;
- ¶3.2 otherwise, if `numeric_limits<T>::is_integer` is true: an **integer-valued** entity, further divided by `is_signed` into signed and unsigned;
- ¶3.3 otherwise: a **real-valued** entity, such as `normal_distribution<double>`.

¶4 Unless otherwise specified, all computations in [rand] are carried out over the mathematical reals. The transition algorithms of the engines later on are written as (a·x + c) mod m, which is exact mathematical arithmetic, not C++ arithmetic on `UIntType`. For example, `minstd_rand0` is `linear_congruential_engine<uint_fast32_t, 16807, 0, 2147483647>`; a·x may exceed 32 bits, and the implementation must use a wider type or Schrage's method to compute the correct modular result.

¶5 specifies notation for bitwise operations: `bitand`, `bitor` and `xor` are the usual bitwise operations; `rshift` is a right shift filling the high bits with zeros; `lshift`<sub>w</sub> is a left shift filling the low bits with zeros, with the result taken modulo 2ʷ.

## Which results are reproducible across implementations

The same seed rolling different dice on Linux and Windows is not a defect. The standard specifies the parts to different degrees:

| Component | Reproducible across implementations | Basis |
|---|---|---|
| engines (`mt19937` and so on) | yes; the algorithms are specified bit for bit, and the required 10000th output is even given | [[rand.eng]] |
| textual representation of engines | yes | [[rand.req]] |
| `seed_seq::generate` | yes; the algorithm is specified step by step | [[rand.util]] |
| `generate_canonical` | yes under the current specification, but implementations may not have caught up | [[rand.util]] |
| `default_random_engine` | no; which engine is chosen is implementation-defined | [[rand.eng]] |
| all distributions | no; the algorithms are implementation-defined | [[rand.dist]] |
| `random_device` | no; it is non-deterministic | [[rand.device]] |

`uniform_int_distribution<int>(1, 6)(g)` uses different rejection sampling algorithms on libc++, libstdc++ and the MSVC STL, and consumes engine output differently. Where cross-platform reproducibility is needed, such as game replays, repeatable scientific experiments and test cases, you can only use the engine's raw output directly and write the distribution transformation yourself (or use a fixed third-party implementation).

## Seeding mt19937

### Default construction is the same every time

`std::mt19937 g;` seeds with the fixed default seed 5489. Every run of the program produces exactly the same sequence, which is useful for testing but is not random.

### One 32-bit seed is not enough

`std::mt19937 g(std::random_device{}());` looks random, but the state of `mt19937` is 624 32-bit words, about 19937 bits, while this constructor accepts a single `result_type` value and expands it into the whole state with a fixed recurrence ([[rand.eng]]). So an engine constructed this way has at most 2³² possible initial states.

The consequences can be estimated. If you seed 100,000 objects each this way, by the birthday problem the probability that at least two of them have identical sequences is about 1 − e^(−n²/2³³), close to 69%. And anyone who enumerates the 2³² seeds can find your initial state.

To supply more entropy, use a **seed sequence** ([[g:seed-sequence]]): an object that takes a sequence of integers and produces as many 32-bit values as needed. The seed sequence the standard provides is `seed_seq`.

```cpp run title="seed-mt19937.cpp" ok
#include <algorithm>
#include <array>
#include <functional>
#include <random>

std::mt19937 make_engine() {
  std::random_device rd;
  std::array<std::uint32_t, std::mt19937::state_size> data;
  std::ranges::generate(data, std::ref(rd));   // 624 32-bit values
  std::seed_seq seq(data.begin(), data.end());
  return std::mt19937(seq);                     // construct from the seed sequence
}

int main() {
  auto g = make_engine();
  std::uniform_int_distribution<int> die(1, 6);
  return die(g) >= 1 ? 0 : 1;
}
```

This approach still has two limitations. The mixing algorithm of `seed_seq` is fixed, and the standard does not require it to be injective; analyses have pointed out that for outputs on the scale of `mt19937` it cannot reach every state ([[rand.util]]). Also, `random_device` can be deterministic on some implementations ([[rand.device]]). For the vast majority of uses, none of this matters.

!!! warning "The Mersenne Twister is not cryptographically secure"
    The output of `mt19937` is an invertible linear transformation of its state. Observe 624 consecutive outputs and you can recover the full state and predict all later outputs. Don't use any engine in `<random>` to generate tokens, keys or session IDs; the standard library currently has no cryptographically secure generator.

## Thread safety

Neither engines nor distributions have internal synchronization. Under the library's general rules ([[res.on.data.races]]), two threads calling `operator()` on the same engine at the same time is a data race. The usual approach is one engine per thread:

```cpp run title="thread-local-engine.cpp" ok
#include <random>

std::mt19937_64& local_engine() {
  // only a single 32-bit seed, for brevity
  thread_local std::mt19937_64 g{std::random_device{}()};
  return g;
}

int main() { (void)local_engine()(); }
```

## rand and srand ([c.math.rand])

¶2 These two functions are declared in `<cstdlib>` with the same semantics as in the C standard library: `srand(seed)` sets the starting point of the pseudo-random sequence, and without a call to `srand` it is as if `srand(1)` had been called; `rand()` returns an integer between 0 and `RAND_MAX`, where `RAND_MAX` is at least 32767.

¶3 The standard guarantees very little about them:

- an implementation may specify that some library functions call `rand`, so your sequence may have a few values consumed by them;
- whether `rand` may introduce data races is implementation-defined ([[res.on.data.races]]). It usually has global state, and simultaneous calls from multiple threads may be UB;
- a note directly recommends using the other facilities of [rand], because the algorithm of `rand` is unspecified, so neither its quality nor its performance can be predicted.

The bias of `rand() % 6` can be computed. With `RAND_MAX` at 32767 there are 32768 = 6 × 5461 + 2 possible values, so remainders 0 and 1 each occur once more than the others. The bias is small, but the distribution is wrong. `uniform_int_distribution` requires each value to have probability exactly 1/(b − a + 1) ([[rand.dist]]), and implementations must eliminate this kind of bias with something like rejection sampling.

## Components new in C++26 {{c++26}}

- The counter-based engine `philox_engine` and the aliases `philox4x32` and `philox4x64` ([[P2075R6]], see [[rand.eng]]).
- `ranges::generate_random` ([[P1068R11]]): fills a range in bulk using an engine, or an engine plus a distribution. Engines and distributions may provide a faster bulk member function `generate_random`; the normative text is in [[alg.rand]].

libc++ in our tests provides neither yet.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1 [rand] defines facilities for generating (pseudo-)random numbers.

The freestanding annotations in [rand.synopsis]: the concept `uniform_random_bit_generator` and the predefined aliases `minstd_rand0`, `minstd_rand`, `mt19937`, `mt19937_64`, `ranlux24_base`, `ranlux48_base`, `ranlux24`, `ranlux48`, `philox4x32` and `philox4x64` are marked freestanding; `linear_congruential_engine`, `subtract_with_carry_engine`, `philox_engine`, `discard_block_engine`, `independent_bits_engine` and `uniform_int_distribution` are marked partially freestanding (except the stream operators). The `mersenne_twister_engine` template itself is not annotated, yet its alias `mt19937` is freestanding; providing the alias requires providing that specialization, so this looks like an oversight in the annotations. `shuffle_order_engine`, `knuth_b`, `default_random_engine`, `random_device`, `seed_seq`, `generate_canonical` and the other distributions are not annotated.

</details>

## Questions

!!! question "Question 1"
    In `std::mt19937 a(1), b(1); std::normal_distribution<double> d; double x = d(a), y = d(b);`, does `x == y` necessarily hold? Would the value of `x` change on another standard library implementation?

<details markdown="1">
<summary>Answer</summary>

Not necessarily. The two engines have the same initial state, but the distribution `d` is the same object. `normal_distribution` commonly uses the Box–Muller or polar method, which computes two values at once and caches one, and [[rand.req]] allows distributions to have such internal state. After `d(a)`, `d` may hold a cached value, and `d(b)` returns it directly without consuming anything from `b`.

That is exactly what happens with libc++ in our tests: `x = -1.40287` and `y = -0.549746`, and after the calls `a != b`, because `b` has not had a single value consumed. To make `x == y`, use two distribution objects, or call `d.reset()` between the two calls.

On another implementation `x` will generally change, because distribution algorithms are implementation-defined ([[rand.dist]]).
</details>
