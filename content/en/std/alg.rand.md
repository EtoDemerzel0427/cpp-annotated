---
title: Specialized <random> algorithms
summary: "C++26's ranges::generate_random fills a range in bulk with a random number engine or distribution; it tries the engine's own bulk interface, then batched calls, then one call at a time, but the result must be the same as calling g() one element at a time."
updated: 2026-10-19
---

!!! tldr
    - `std::ranges::generate_random(r, g)` fills the range `r` using engine `g`; the effect must be the same as calling `g()` element by element with `ranges::generate(r, ref(g))`, except that bulk generation is allowed.
    - It first tries the engine's member function `g.generate_random(r)`, then generates in batches for ranges of known size, and finally falls back to calling element by element.
    - The version that fills with a distribution, `generate_random(r, g, d)`, has the same structure; the note only requires the bulk version to have the same distribution.
    - At the time of writing, the libc++ we test with does not provide this function yet.

{{c++26}} The interface of random number engines produces one value at a time: `g()`. Programs that need large quantities of random numbers (Monte Carlo simulation, noise generation) read and write the engine state on every call when calling one at a time, and compilers find it hard to vectorize. On the other hand, counter-based engines like Philox ([[P2075R6]]) and hardware random number generators are naturally suited to producing a batch at a time.

`std::ranges::generate_random` ([[P1068R11]]) provides a bulk interface without changing the sequence of values produced. [alg.rand.general] ¶1 says it is declared in `<random>`.

```cpp
#include <random>
#include <vector>

int main() {
    std::vector<double> v(1'000'000);
    std::philox4x32 g(42);                      // C++26's counter-based engine
    std::normal_distribution<double> d(0.0, 1.0);
    std::ranges::generate_random(v, g, d);      // the implementation may generate in bulk
}
```

At the time of writing, the libc++ we test with has neither `std::philox4x32` nor `std::ranges::generate_random`; the example above follows the standard's text and has not been compiled. Until it is supported, `std::ranges::generate(v, [&] { return d(g); })`, which has the same semantics, can be used instead.

## Filling with an engine ([alg.rand.generate] ¶1–¶4)

```cpp
template<class R, class G>
  requires output_range<R, invoke_result_t<G&>> &&
           uniform_random_bit_generator<remove_cvref_t<G>>
  constexpr borrowed_iterator_t<R> ranges::generate_random(R&& r, G&& g);
```

The effects in ¶1 try three approaches in order:

1. ¶1.1 If `g.generate_random(std::forward<R>(r))` is well-formed, call it, letting the engine provide its own bulk implementation;
2. ¶1.2 Otherwise, if `R` is a `sized_range`, fill `ranges::size(r)` values with an unspecified number of calls of the form `g()` or `g.generate_random(s)`, where `s` is a `span<invoke_result_t<G&>, N>`. Note 1 says N may differ between calls, so an implementation can chunk into fixed-size blocks and use an engine's bulk interface that takes a `span`;
3. ¶1.3 Otherwise, call `ranges::generate(std::forward<R>(r), ref(g))`, generating one at a time.

¶2 returns `ranges::end(r)`. ¶4 The iterator-plus-sentinel version is equivalent to wrapping them in a `subrange` and calling that.

!!! std
    The effects of `generate_random(r, g)` shall be equivalent to `ranges::generate(std::forward<R>(r), ref(g))`.

¶3 is the most important requirement in this subclause. Note 2 points out that this means `g.generate_random(a)` must fill `a` with the same values as successive calls to `g()`. Equivalent effects also mean that after the call, the engine's state is the same as after N calls to `g()`.

Bulk generation is only a performance optimization and must not change the random sequence. So a program using a fixed seed remains reproducible after switching to `generate_random`.

## Filling with a distribution (¶5–¶8)

```cpp
template<class R, class G, class D>
  requires output_range<R, invoke_result_t<D&, G&>> && invocable<D&, G&> &&
           uniform_random_bit_generator<remove_cvref_t<G>> &&
           is_arithmetic_v<invoke_result_t<D&, G&>>
  constexpr borrowed_iterator_t<R> ranges::generate_random(R&& r, G&& g, D&& d);
```

The three approaches in ¶5 are the same as for the engine version: first try `d.generate_random(r, g)`; then, for ranges of known size, call `invoke(d, g)` or `d.generate_random(s, g)` in batches; finally `ranges::generate(r, [&d, &g] { return invoke(d, g); })`.

¶7 likewise requires the effects to be equivalent to calling `invoke(d, g)` one at a time. But the wording of Note 4 differs: the bulk version of a distribution fills `a` with values that have the same random distribution as successive calls, without saying the values are identical. A distribution's implementation may consume different amounts of engine output depending on how it is called; for example, the method commonly used for `normal_distribution` produces two values at a time. There is this discrepancy between the normative ¶7 and the explanatory Note 4; when reading, take ¶7 as authoritative and use Note 4 to understand the design intent.

## Questions

!!! question "Question"
    A user-defined engine provides a member function `generate_random(span<uint32_t>)`, but for performance the values it produces differ from successive calls to `operator()`. What happens when it is used with `ranges::generate_random`?

<details markdown="1">
<summary>Answer</summary>

It violates the equivalence requirement of ¶3. This is a requirement on a program-provided type, and violating it is undefined behavior ([[res.on.functions]]). The more practical consequence: some standard library implementations call the member `generate_random` and others call `g()` one at a time, so the same program gets different random sequences on different implementations.
</details>
