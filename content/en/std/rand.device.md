---
title: random_device
summary: "The non-deterministic random number source random_device: the standard allows it to degrade to a deterministic engine, and the meaning of the token and the accuracy of entropy() are up to the implementation; it is suited to supplying seeds, not to generating large quantities of random numbers directly."
updated: 2026-10-19
---

!!! tldr
    - `random_device` is the only URBG in `<random>` expected to be non-deterministic; it usually reads bits from the operating system's entropy source.
    - When the implementation is limited, the standard allows it to use a deterministic engine instead, in which case `entropy()` returns 0. Conversely, `entropy()` returning 0 does not necessarily mean it is deterministic.
    - What the constructor's token argument means is implementation-defined; portable code uses only the default constructor.
    - Both construction and invocation may throw exceptions derived from `std::exception`.
    - The idiom is to use it to seed an engine, and let the engine generate the bulk of the random numbers.

## Using it for seeding

```cpp run title="seed-from-device.cpp" ok
#include <array>
#include <random>

int main() {
  std::random_device rd;                  // entropy source
  std::array<unsigned, 8> e;
  for (auto& x : e) x = rd();
  std::seed_seq seq(e.begin(), e.end());
  std::mt19937_64 g(seq);                 // workhorse engine
  std::uniform_real_distribution<double> u(0.0, 1.0);
  double sum = 0;
  for (int i = 0; i < 1000; ++i) sum += u(g);
  return sum > 0 ? 0 : 1;
}
```

`random_device` supplies only 8 32-bit seed values, and the 1000 random numbers after that all come from the engine. There are several reasons for this division of labor:

1. each `rd()` may be a system call, much slower than advancing an engine one step;
2. record `e` and you can replay the whole run, whereas `random_device` itself cannot be replayed;
3. `random_device`'s `operator()` may throw, while the engine's does not;
4. the standard's guarantees about `random_device` are weak; see below.

## The shape of the class

- `result_type` is `unsigned int`, and `min()` and `max()` are `static constexpr` functions covering its full range, so it satisfies the `uniform_random_bit_generator` concept ([[rand.req]]);
- the default constructor delegates to `random_device(implementation-defined token)`, and there is also `explicit random_device(const string& token)`;
- the only member functions are `operator()` and `double entropy() const noexcept`;
- the copy constructor and copy assignment are deleted, and no move operations are declared, so it can be neither copied nor moved. It represents an external resource, such as a file descriptor or device handle.

It is not an engine: no seeding, no `==`, no textual representation, no `discard`; it can be used only where a URBG is required.

## What the standard guarantees (¶1–¶7)

¶1 `random_device` produces non-deterministic random numbers. But ¶2 immediately relaxes this:

!!! std
    If implementation limitations prevent generating nondeterministic random numbers, the implementation may employ a random number engine.

So a conforming `random_device` may output the same sequence on every run. This actually happened: libstdc++ on early MinGW platforms was implemented this way, and programs seeded from `random_device` gave the same results every time they ran.

¶5 `entropy()` is the probe the standard leaves. If the implementation uses an engine, it returns 0.0; otherwise it returns an estimate of the entropy of `operator()`'s output, in the range `min()` to log₂(`max()` + 1), with an upper bound of 32 for a 32-bit `unsigned int`. Footnote 223 gives the definition of entropy: for a device with n states with probabilities P₀ … Pₙ₋₁, the entropy is S = −Σ Pᵢ·log Pᵢ.

This is only an estimate, and the standard places no requirement on its accuracy. An implementation may well report 0 in every case, even if it is non-deterministic; and when it returns a non-zero value, the standard has no way to verify it. So `entropy() == 0` can only serve as a warning that it might be deterministic, not as a reliable criterion.

¶4 The meaning of the token parameter, and the token value used by the default constructor, are implementation-defined. Footnote 222 says the intent is to let implementations distinguish different sources of randomness. Implementations often interpret the token as a device path or entropy source name, such as `"/dev/urandom"` or `"rdrand"`, but the strings accepted vary.

¶3, ¶7 Failure to initialize at construction, or failure to obtain a random number on invocation, throws an exception of an implementation-defined type derived from `exception`. ¶6 Each invocation returns a non-deterministic value uniformly distributed between `min()` and `max()`, generated in an implementation-defined way.

!!! impl "libc++ on macOS"
    In libc++ in our tests, the default constructor delegates to `random_device("/dev/urandom")`, but on Apple platforms it actually calls `arc4random()` and ignores the token: passing `"/dev/random"`, `"rdrand"` or even `"foo"` all construct successfully, and `entropy()` returns 32 in every case.

## It is not a cryptographic building block

The standard places no security requirements on `random_device`; it may even be deterministic (¶2). When you need cryptographically secure random numbers, use the interfaces provided by the operating system directly.
