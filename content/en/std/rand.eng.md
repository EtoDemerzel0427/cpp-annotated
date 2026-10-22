---
title: Random number engines and engine adaptors
summary: "How the four standard engines (linear congruential, Mersenne Twister, subtract with carry, Philox) and three adaptors each work and are seeded; the required outputs of predefined aliases such as mt19937; and why mt19937 g(s) does not mistakenly select the seed sequence constructor."
updated: 2026-10-19
---

!!! tldr
    - The state, transition algorithm, output algorithm, seeding procedure and textual representation of the standard engines are specified bit for bit, so the same seed produces the same sequence on any implementation. Every predefined alias has a specified 10000th output.
    - The template parameters must satisfy certain relationships (for example, the linear congruential engine requires `a < m`); otherwise the program is ill-formed.
    - When `mt19937` is seeded with a single integer, the whole state of about 19937 bits is determined by that integer.
    - The `X(Sseq&)` constructor does not participate in overload resolution for types implicitly convertible to `result_type`, so `std::mt19937 g(s)` works as intended even for `int s`.
    - Which engine `default_random_engine` is is implementation-defined (`minstd_rand` in libc++). When you need quality or reproducibility, name a specific engine type.

## Engine output is specified ([rand.predef])

```cpp run title="required-behavior.cpp" ok
#include <cassert>
#include <random>

template<class E> auto nth10000() {
  E e;               // default-constructed
  e.discard(9999);
  return e();        // the 10000th invocation
}

int main() {
  assert(nth10000<std::mt19937>() == 4123659995u);
  assert(nth10000<std::mt19937_64>() == 9981545732273789042u);
  assert(nth10000<std::minstd_rand>() == 399268537u);
  assert(nth10000<std::ranlux24>() == 9901578u);
}
```

[rand.predef] attaches a *Required behavior* to each predefined alias: the 10000th invocation of a default-constructed object must produce a given value. This can be required because everything about engines is deterministic: the meaning of the state, every transition step, the computation of each output, the seeding procedure and the textual format are all specified bit for bit. libc++ in our tests passes this check for every alias it implements.

| Alias | Definition | 10000th output |
|---|---|---|
| `minstd_rand0` | `linear_congruential_engine<uint_fast32_t, 16807, 0, 2147483647>` | 1043618065 |
| `minstd_rand` | same, with a = 48271 | 399268537 |
| `mt19937` | `mersenne_twister_engine<uint_fast32_t, 32, 624, 397, 31, …>` | 4123659995 |
| `mt19937_64` | `mersenne_twister_engine<uint_fast64_t, 64, 312, 156, 31, …>` | 9981545732273789042 |
| `ranlux24_base` | `subtract_with_carry_engine<uint_fast32_t, 24, 10, 24>` | 7937952 |
| `ranlux48_base` | `subtract_with_carry_engine<uint_fast64_t, 48, 5, 12>` | 61839128582725 |
| `ranlux24` | `discard_block_engine<ranlux24_base, 223, 23>` | 9901578 |
| `ranlux48` | `discard_block_engine<ranlux48_base, 389, 11>` | 249142670248501 |
| `knuth_b` | `shuffle_order_engine<minstd_rand0, 256>` | 1112339016 |
| `philox4x32` {{c++26}} | `philox_engine<uint_fast32_t, 32, 4, 10, …>` | 1955073260 |
| `philox4x64` {{c++26}} | `philox_engine<uint_fast64_t, 64, 4, 10, …>` | 3409172418970261260 |

The `result_type` is `uint_fast32_t`, which on 64-bit Linux is usually the 64-bit `unsigned long`. The word size w of `mt19937` is still 32 and its output is still in [0, 2³² − 1]; it is just that each state word may take 8 bytes in the object.

¶10 Which engine `default_random_engine` is is implementation-defined. A note says implementations may choose based on performance, size and quality, with the aim of providing at least acceptable behavior for casual, lightweight use; different implementations may choose different engines, so code using it cannot expect the same sequence across implementations. In libc++ in our tests it is `minstd_rand`, a linear congruential engine with a period of about 2³¹ and mediocre statistical quality.

The four engine templates are introduced below in turn. Before reading them you need the model from [[rand.req]]: an engine has a state, and each call first advances the state one step with the **transition algorithm** TA, then computes the output from the state with the **generation algorithm** GA. The formulas in [rand] are all computed over the mathematical reals ([[rand]]).

## Linear congruential engine ([rand.eng.lcong])

`linear_congruential_engine<UIntType, a, c, m>` is the simplest engine.

¶1 The state is a single integer xᵢ. The transition algorithm is TA(xᵢ) = (a·xᵢ + c) mod m, and the generation algorithm is GA(xᵢ) = xᵢ₊₁, returning the new state itself. `max()` is m − 1; `min()` is 1 when `c == 0` and 0 otherwise. The reason is that when `c == 0`, state 0 is a fixed point, and the engine never produces 0.

¶2 If the template argument `m` is 0, the modulus is `numeric_limits<result_type>::max() + 1`, a value that need not be representable as `result_type`. So `m = 0` means modulo 2ʷ.

¶3 If `m` is not 0, then `a < m` and `c < m` are required.

¶5 `explicit linear_congruential_engine(result_type s)`: if `c mod m` and `s mod m` are both 0, the state is set to 1, otherwise to `s mod m`. This step specifically avoids the fixed point 0 when `c == 0`, so `minstd_rand(0)` is equivalent to `minstd_rand(1)`.

¶6 When seeding from a seed sequence, let k = ⌈log₂ m / 32⌉; it requests k + 3 32-bit values, skips the first 3, and assembles the state from the last k, again replacing 0 with 1.

a·xᵢ may exceed the range of `UIntType`, but the formula is computed over the mathematical reals, and implementations must obtain the mathematically correct modular result.

## Mersenne Twister engine ([rand.eng.mers])

`mersenne_twister_engine<UIntType, w, n, m, r, a, u, d, s, b, t, c, l, f>` is the most commonly used engine; `mt19937` is a specialization of it.

¶1 It produces integers in [0, 2ʷ − 1]; the state is a sequence X of n w-bit values, with indices taken modulo n. Footnote 221 explains the name: with suitably chosen parameters, the period is closely related to a large Mersenne prime; the period of `mt19937` is 2¹⁹⁹³⁷ − 1.

¶2 The transition algorithm is a twisted generalized feedback shift register:

1. concatenate the upper w − r bits of Xᵢ₋ₙ with the lower r bits of Xᵢ₊₁₋ₙ to form Y;
2. let α = a·(Y bitand 1), and set Xᵢ = Xᵢ₊ₘ₋ₙ xor (Y rshift 1) xor α.

¶3 The generation algorithm applies four steps of shifts, masks and xors to Xᵢ, called **tempering**, to improve the uniformity of the output. Tempering is an invertible linear transformation, so the state can be recovered from the output, which is why it cannot be used for cryptography ([[rand]]).

¶4 lists relationships among the parameters, such as `0 < m <= n`, `2u < w`, `w <= numeric_limits<UIntType>::digits`, and each mask not exceeding 2ʷ − 1.

¶6 `explicit mersenne_twister_engine(result_type value)` first sets X₋ₙ = value mod 2ʷ, then computes the remaining Xᵢ for i = 1 − n, …, −1 with a fixed recurrence. The whole state of about 19937 bits is determined by this one value, so an `mt19937` seeded with a single integer has at most 2³² initial states.

¶8 When seeding from a seed sequence, let k = ⌈w/32⌉; it requests n·k 32-bit values and assembles each Xᵢ from k of them. The all-zero state is a fixed point, so if the assembled state (excluding the low r bits of X₋ₙ) is all 0, X₋ₙ is changed to 2ʷ − 1.

## Subtract with carry engine ([rand.eng.sub])

`subtract_with_carry_engine<UIntType, w, s, r>` is a lagged Fibonacci generator and the basis of the `ranlux` family.

¶2–¶4 The state is r integers 0 ≤ Xᵢ < m = 2ʷ plus a **carry** c ∈ {0, 1}. Each step computes Y = Xᵢ₋ₛ − Xᵢ₋ᵣ − c, sets Xᵢ = Y mod m and c = 1 if Y < 0, else c = 0, and returns the new Xᵢ. A note points out that this is equivalent to a multiplicative congruential generator with an enormous modulus.

¶5 The parameters require `0 < s < r` and `0 < w <= digits`.

¶7 `explicit subtract_with_carry_engine(result_type value)` first constructs a `linear_congruential_engine<uint_least32_t, 40014u, 0u, 2147483563u>` seeded with `value == 0 ? default_seed : value % 2147483563u`, and assembles the initial state from its output. The default constructor and the default argument of `seed()` are both `0u`, so default seeding actually uses `default_seed` (19780503). Here `default_seed` has type `uint_least32_t`, not `result_type`.

## Philox engine ([rand.eng.philox]) {{c++26}}

`philox_engine<UIntType, w, n, r, consts...>`, introduced by [[P2075R6]], is a **counter-based** generator. The previous three engines advance their state by recurrence; Philox instead encrypts a counter through r rounds of a substitution–permutation network, and the output is the encrypted result.

¶1 The state consists of: a counter X of n w-bit values (viewed as an n·w-bit integer Z), n/2 keys K, a batch of n buffered outputs Y, and an index i. The keys are generated from the seed and do not change unless reseeded.

¶2–¶3 Each call first increments i; when i reaches n, it computes Y = Philox(K, X), increments the counter Z, and resets i to zero. It then returns Yᵢ.

¶4–¶5 One Philox round first permutes X per Table 129, then for each pair of values takes the high and low halves of a multiplication and xors with the round key. The result after r rounds is Y.

¶6 *Mandates*: `sizeof...(consts) == n`, n is 2 or 4, `0 < r`, `0 < w <= digits`. ¶7 `consts` alternates multipliers and round constants: [M₀, C₀, M₁, C₁, …].

¶9–¶10 Seeding sets only the keys K; the counter is zeroed and i is set to n − 1. ¶11 `set_counter(c)` sets the counter directly; note that the order of the elements of `c` is the reverse of X.

The counter-based design has two advantages. `discard(z)` just adds z to the counter, in constant time. Multiple threads or GPU threads can use the same keys with different counter ranges and get non-overlapping streams without passing large blocks of state around. libc++ in our tests does not yet implement `philox_engine`.

## Engine adaptors ([rand.adapt])

An **engine adaptor** wraps another engine (the **base engine**) and changes the properties of its output sequence ([[rand.req]]).

### discard_block_engine ([rand.adapt.disc])

`discard_block_engine<Engine, p, r>` uses only the first r of every p values the base engine produces, discarding the other p − r.

¶1–¶3 The state is the base engine's state plus a count n. On each call, if n ≥ r, it first advances the base engine p − r steps and sets n to 0; then it increments n and returns the base engine's next output. ¶4 requires `0 < r <= p`.

This is RANLUX's approach. Adjacent outputs of a subtract with carry engine are fairly strongly correlated, and discarding most of them buys very good statistical quality at the cost of speed. `ranlux24` uses only 23 of every 223 values.

### independent_bits_engine ([rand.adapt.ibits])

`independent_bits_engine<Engine, w, UIntType>` assembles the base engine's outputs into results of exactly w bits.

¶1 The state is just the base engine's state. ¶2–¶4 With R the size of the base engine's range, the algorithm decides how many times to call the base engine and how many low bits to take each time, rejecting and redrawing values that fall in the tail of the range. That way, even when R is not a power of 2 (for example the range [1, 2³¹ − 2] of `minstd_rand`), each bit of the result is uniform and independent. ¶5 requires `0 < w <= numeric_limits<result_type>::digits`.

When using it to get uniform random bytes from a 32-bit engine, `UIntType` must be at least as wide as `short` ([[rand.req]]), so you cannot write `unsigned char` directly:

```cpp run title="random-bytes.cpp" ok
#include <algorithm>
#include <random>
#include <vector>

int main() {
  std::independent_bits_engine<std::mt19937, 8, unsigned short>
      bytes(1);
  static_assert(bytes.min() == 0 && bytes.max() == 255);
  std::vector<unsigned char> buf(16);
  std::ranges::generate(buf, [&] {
    return static_cast<unsigned char>(bytes());
  });
}
```

### shuffle_order_engine ([rand.adapt.shuf])

`shuffle_order_engine<Engine, k>` produces the same values as the base engine but shuffles the order in which they are delivered (the Bays–Durham shuffle).

¶1 The state is the base engine's state, a value Y and a table V of k entries. ¶2–¶3 Each call computes an index j from Y, sets Y = Vⱼ, refills Vⱼ with the base engine's next output, and returns Y. ¶4 requires `0 < k`. `knuth_b` is `shuffle_order_engine<minstd_rand0, 256>`.

## Seeding with an integer does not select the Sseq constructor ([rand.eng.general] ¶7)

Every engine and adaptor `X` has a constructor and a `seed` overload taking a seed sequence:

```cpp
template<class Sseq> explicit X(Sseq& q);
template<class Sseq> void seed(Sseq& q);
```

Consider this code:

```cpp run title="sseq-overload.cpp" ok
#include <random>

int main() {
  int s = 42;
  std::mt19937 g(s);   // selects mt19937(result_type)
  std::mt19937 h(42u);
  return g == h ? 0 : 1;
}
```

`mt19937(result_type)` needs a conversion from `int` to `uint_fast32_t`, whereas the template `X(Sseq&)` deduces successfully with `Sseq = int`, and binding `int&` to an `int` lvalue is an exact match, better per [[over.ics.rank]]. Overload resolution would select it and then fail to compile at the call to `q.generate(...)`.

¶7 specifies that when these two functions are called with a type that cannot qualify as a seed sequence, they do not participate in overload resolution. How far an implementation goes in determining this is unspecified, but at minimum types implicitly convertible to `X::result_type` must be excluded. With this rule, `std::mt19937 g(s)` works as you would expect. Implementations usually do this check with SFINAE or a `requires` clause.

## Parameter relationships and choosing an engine

[rand.eng.general] ¶6 and [rand.adapt.general] ¶6 specify that each template requires certain relationships among its constant template parameters, and the program is ill-formed if they are not satisfied. `a < m`, `0 < s < r` and `0 < r <= p` listed in the sections above are all of this kind.

The rough characteristics of each engine are below. These quality assessments are common knowledge in the field; the standard itself specifies only the algorithms, not their quality.

| Engine | State size | Speed | Quality | Notes |
|---|---|---|---|---|
| `minstd_rand` | 4–8 bytes | fast | poor | short period in the low bits; range is not a power of 2 |
| `mt19937`, `mt19937_64` | about 2.5 KB | fast | good, but with known linear artifacts | most common; seeding needs enough entropy |
| `ranlux24`, `ranlux48` | small | slow | very good | the traditional choice for physics simulation |
| `knuth_b` | about 1 KB | medium | fair | mainly of historical interest |
| `philox4x32`, `philox4x64` | small | fast, easy to parallelize | good | C++26; `discard` is constant time |

<details class="fine" markdown="1"><summary>Remaining wording</summary>

¶1–¶5 of [rand.eng.general] and [rand.adapt.general] say the same things: the types obtained by instantiation meet the engine (or adaptor) requirements; unless otherwise specified, each function has constant complexity and throws no exceptions; a function with a parameter `Sseq& q` where `Sseq` is not `seed_seq` throws whatever `q.generate` throws; and copying, the stream operators and the equality operators are not listed in the synopses, their semantics being given in [[rand.req]].

Textual representations of the engines: for the linear congruential engine, xᵢ ([rand.eng.lcong] ¶4); for the Mersenne Twister, Xᵢ₋ₙ, …, Xᵢ₋₁ ([rand.eng.mers] ¶5); for subtract with carry, Xᵢ₋ᵣ, …, Xᵢ₋₁ followed by c ([rand.eng.sub] ¶6); for Philox, K, X and i, with Y not written out and rebuilt from K and X on input ([rand.eng.philox] ¶8). The textual representation of an adaptor contains that of its base engine, followed by its own additional state.

[rand.adapt.disc] ¶6 and [rand.adapt.shuf] ¶6: each constructor other than the copy constructor, after initializing the base engine, sets the count n to 0, or fills V and then Y in order with outputs of the base engine, respectively.

[rand.eng.sub] ¶8–¶9: seeding with an integer calls the auxiliary engine exactly n·r times; seeding with a seed sequence is similar to the Mersenne Twister.

</details>

## Questions

!!! question "Question 1"
    Is `std::linear_congruential_engine<std::uint32_t, 5, 3, 4> e;` well-formed? What about `<std::uint32_t, 5, 3, 0>`?

<details markdown="1">
<summary>Answer</summary>

The first is ill-formed. `m = 4` is not 0, and [rand.eng.lcong] ¶3 requires `a < m`, but 5 ≥ 4, so per [rand.eng.general] ¶6 the program is ill-formed.

The second is well-formed. `m = 0` means the modulus is 2³² (¶2), and the relationships in ¶3 are required only when `m != 0`.
</details>

!!! question "Question 2"
    Why does `std::mt19937 g(std::seed_seq{1, 2, 3});` not compile?

<details markdown="1">
<summary>Answer</summary>

The parameter of the seed sequence constructor is `Sseq&`, and a non-const lvalue reference cannot bind to a temporary. The `result_type` constructor is not viable either, because `seed_seq` cannot be converted to an integer. You must declare a named `seed_seq` variable first and pass that. The parameter is a non-const reference because `generate` is not a const member and may depend on call history ([[rand.req]]).
</details>
