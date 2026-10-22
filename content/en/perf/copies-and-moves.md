---
title: Avoiding unnecessary copies
summary: "Using a counting type and timing to find the copies and moves a program can drop: how to pass parameters, when return values are elided, where range-for, structured bindings, const, emplace, map insertion and initializer_list each make an extra copy, and why small objects are faster passed by value."
tags: performance, copy, move, copy elision, NRVO, ABI
updated: 2026-10-19
group: Code
---

!!! tldr
    - Count before you change anything: give the type copy and move counters, or replace `operator new` to count allocations. Counts are unaffected by machine load and are more reliable than timing.
    - Pass large read-only objects by `const&`. For parameters that are stored, take them by value and move in constructors; in setters, provide both `const&` and `&&` overloads so the member's existing capacity can be reused.
    - `return local;` usually copies nothing (NRVO); returning different locals from two branches, returning a parameter, `return std::move(local);` and `return b ? x : y;` each add a move or a copy.
    - `for (auto s : v)`, `auto [k, v] = *it`, calling `std::move` on a `const` object, classes with `const` members, and `std::initializer_list` all look harmless but copy.
    - Small trivially copyable types (two or three integers, `string_view`, `span`) passed by value go in registers, saving a round trip through memory compared with `const&`, and cannot alias other pointers.

All measurements on this page were made on the same machine: Apple M2 Pro, macOS, Homebrew Clang 23.1.3 + libc++, arm64, `clang++ -std=c++2c -O2`. The machine was heavily loaded at the time of writing, so absolute times are slow and scattered; the page therefore mainly reports three kinds of evidence: counts of copies, moves and allocations; time ratios measured alternately in the same process (the range over three runs); and assembly. Different hardware, compilers or standard libraries will change the numbers. The timing harness is [[perf/measuring#harness|bench.hpp]]; `bench::compare(a, b)` measures two versions alternately in ABBA order and prints the ratio.

The rules themselves, copy elision and implicit move, are covered in [[topics/special-members-and-elision]] and [[topics/value-categories]]; here we only care what they save and what they miss in real code.

## Count first

Timing is affected by noise; counts are not. Add a counter to each of a type's four special member functions, and you know exactly how many copies and moves a line of code makes:

```cpp run title="counted.cpp" ok
#include <cstdio>
#include <map>
#include <utility>
#include <vector>

struct Counted {
  static inline int copies = 0, moves = 0;
  int v = 0;
  Counted() = default;
  Counted(int x) : v(x) {}
  Counted(const Counted& o) : v(o.v) { ++copies; }
  Counted(Counted&& o) noexcept : v(o.v) { ++moves; }
  Counted& operator=(const Counted& o) { v = o.v; ++copies; return *this; }
  Counted& operator=(Counted&& o) noexcept { v = o.v; ++moves; return *this; }
};

#define SHOW(label, ...) do {                                   \
    Counted::copies = Counted::moves = 0;                       \
    { __VA_ARGS__; }                                            \
    std::printf("%-30s copy %d  move %d\n", label,              \
                Counted::copies, Counted::moves);               \
  } while (0)

Counted one()        { Counted c(1); return c; }
Counted two(bool b)  { Counted a(1), c(2); if (b) return a; return c; }
Counted param(Counted p) { return p; }
Counted cond(bool b) { Counted a(1), c(2); return b ? a : c; }

int main() {
  SHOW("return c;", Counted r = one(); (void)r);
  SHOW("if (b) return a; return c;", Counted r = two(true); (void)r);
  SHOW("return p; (parameter)", Counted r = param(Counted(1)); (void)r);
  SHOW("return b ? a : c;", Counted r = cond(true); (void)r);

  std::vector<Counted> v;
  v.reserve(8);
  SHOW("push_back(Counted(1))", v.push_back(Counted(1)));
  SHOW("emplace_back(1)", v.emplace_back(1));
  SHOW("vector<Counted> w{1, 2, 3}", std::vector<Counted> w{1, 2, 3});

  std::vector<Counted> vs(4);
  SHOW("for (auto x : vs)", for (auto x : vs) (void)x);
  SHOW("for (const auto& x : vs)", for (const auto& x : vs) (void)x);

  std::map<int, Counted> m{{1, Counted(1)}};
  SHOW("auto [k, c] = *m.begin()", auto [k, c] = *m.begin(); (void)k; (void)c);
  SHOW("auto& [k, c] = *m.begin()", auto& [k, c] = *m.begin(); (void)k; (void)c);
}
```

Compiled with `-O2` and run on our test machine, the output is (the same at `-O0`; these counts are determined by language rules, not by optimization):

```text
return c;                      copy 0  move 0
if (b) return a; return c;     copy 0  move 1
return p; (parameter)          copy 0  move 1
return b ? a : c;              copy 1  move 0
push_back(Counted(1))          copy 0  move 1
emplace_back(1)                copy 0  move 0
vector<Counted> w{1, 2, 3}     copy 3  move 0
for (auto x : vs)              copy 4  move 0
for (const auto& x : vs)       copy 0  move 0
auto [k, c] = *m.begin()       copy 1  move 0
auto& [k, c] = *m.begin()      copy 0  move 0
```

The following sections explain this table line by line. For types that manage their own heap memory, like `std::string` and `std::vector`, another reliable count is the number of allocations: replace the global `operator new` and increment on each call. How to do it is in [[perf/allocation]].

The counters have one side effect to keep in mind: they make the copy and move constructors non-trivial, which changes how the type is passed (see the ABI section below). They are good for answering how many times something happened, not for timing.

## Parameters: `const&`, `&&` or by value

When a function only reads its parameter, the answer is simple: large objects by `const&`, small trivially copyable objects by value (next section). The hard case is when the function stores the parameter, as setters and constructors do. Three common forms:

<div class="compare" markdown="1">

```cpp
struct ByRef {
  std::string m;
  void set(const std::string& s) {
    m = s;                   // copy
  }
};
struct BySink {
  std::string m;
  void set(std::string s) {  // take by value
    m = std::move(s);        // then move
  }
};
```

```cpp
struct ByBoth {
  std::string m;
  void set(const std::string& s) {
    m = s;
  }
  void set(std::string&& s) {
    m = std::move(s);
  }
};
```

</div>

Taking by value and then moving is often called a sink parameter. With an lvalue argument it copies once and moves once; with an rvalue it moves twice (or, when the argument is a prvalue, the parameter is directly its result object and there is only one move). The `const&` version copies once even for rvalues. Counting operations alone, taking by value costs at most one extra move compared with two overloads.

But setters have one more factor counts don't show: `m = s` is copy assignment, and when `m`'s existing buffer is big enough, libc++ copies the characters straight into it without allocating. The by-value version first copy-constructs the parameter, which necessarily allocates, and then move-assigns, discarding `m`'s old buffer. In a loop calling the setter repeatedly, counting with a replaced `operator new` on our test machine gives:

| Form | Lvalue argument, allocations per call | Rvalue argument (caller first constructs a temporary `std::string`), allocations per call |
|---|---|---|
| `const&` | 0 | 1 (the temporary itself) |
| By value | 1 | 1 |
| `const&` + `&&` | 0 | 1 |

Timing results (`bench::compare`, ratio range over three runs; a ratio above 1 means B is slower):

| Scenario | A | B | B/A |
|---|---|---|---|
| `string(10)`, lvalue | `const&` | by value | 1.25 |
| `string(100)`, lvalue | `const&` (about 4 ns) | by value | 6.6 – 18 |
| `string(100)`, rvalue | `const&` | by value | 0.91 |
| `string(100)`, rvalue | `const&` | `const&` + `&&` | 0.89 |
| `vector<int>(1000)`, lvalue | `const&` | by value | 1.3 – 1.7 |
| `vector<int>(1000)`, rvalue | `const&` | by value | 0.51 – 0.74 |
| `vector<int>(1000)`, rvalue | `const&` | `const&` + `&&` | 0.56 – 0.85 |

The rvalue-argument times include the caller's allocation and copy for the temporary, so none of the columns are small. Three things can be read from the table:

1. Short strings (at most 22 characters in libc++, stored inside the object; see [[perf/allocation]]) differ by only a fraction of a nanosecond however they are passed.
2. With an lvalue argument to a setter, taking by value is much slower, because it gives up `m`'s existing capacity. This column fluctuates most; what it mainly measures is the allocator.
3. With an rvalue argument, taking by value is as fast as the `&&` overload, and both save one element copy compared with `const&`.

Constructors have no existing capacity to reuse, so taking by value and moving costs only one extra move compared with two overloads, in exchange for one function instead of 2^n overloads, which is usually a reasonable trade. For setters and `assign`-like functions that are called repeatedly, the two overloads `const&` + `&&` are better. A forwarding reference (`template<class T> void set(T&& s)`) achieves the same counts, at the price of making the interface a template, with hard-to-read error messages.

## Pass small objects by value

```cpp godbolt title="abi.cpp" flags="-std=c++2c -O2" ok
struct P { int x, y; };
int use_val(P p);
int use_ref(const P& p);
int call_val(int a, int b) { return use_val({a, b}); }
int call_ref(int a, int b) { return use_ref({a, b}); }
```

The arm64 assembly generated at `-O2`:

<div class="compare" markdown="1">

```asm
call_val:
  mov  w8, w0
  orr  x0, x8, x1, lsl #32
  b    use_val      ; tail call
```

```asm
call_ref:
  sub  sp, sp, #32
  stp  x29, x30, [sp, #16]
  add  x29, sp, #16
  stp  w0, w1, [sp, #8] ; store to the stack
  add  x0, sp, #8       ; pass the address
  bl   use_ref
  ldp  x29, x30, [sp, #16]
  add  sp, sp, #32
  ret
```

</div>

Passed by value, the two `int`s of `P` are packed into one 64-bit register `x0`, and the caller does not even need a stack frame. Passed by `const&`, the reference requires the object to have an address, so the caller has to store it on the stack first and pass a pointer, and the callee has to load it back from memory.

The standard permits this by [[class.temporary#3]]: if all eligible copy and move constructors of a class type are trivial and the destructor is trivial or deleted, the implementation may create an extra temporary object to pass the argument or return value. The note to that sentence states the purpose: to allow passing in registers. Conversely, types that do not meet this condition (such as `std::unique_ptr`, `std::string`, or `Counted` with counters from the previous section), even if only 8 bytes, are passed by value under the Itanium C++ ABI (used by Linux and macOS) by having the caller build the object on the stack and pass its address.

`const&` has another cost: the reference may point to the same memory as other pointers.

```cpp godbolt title="alias.cpp" flags="-std=c++2c -O2" ok
void scale_ref(double* v, int n, const double& k) {
  for (int i = 0; i < n; ++i) v[i] *= k;
}
void scale_val(double* v, int n, double k) {
  for (int i = 0; i < n; ++i) v[i] *= k;
}
```

`scale_ref(v, n, v[0])` is a valid call, and in it the first write to `v[0]` changes `k`. So Clang generates a run-time check for `scale_ref` (`cmp x2, x9` / `ccmp`, testing whether `&k` falls within `v[0..n)`): without overlap it runs the vectorized loop; with overlap, a scalar loop that reloads `k` with `ldr d0, [x2]` on every iteration. In `scale_val`, `k` is in register `d0`, with no check and only the vectorized loop. The two functions also give different results when `k` aliases an element of `v`; this is not only a performance issue.

So `int`, `double`, pointers, iterators, `std::string_view`, `std::span`, and structs of two or three scalars should all be passed by value. The boundary is roughly two registers (16 bytes): under AAPCS64 and x86-64 System V, trivially copyable aggregates of at most 16 bytes passed by value go in registers; larger ones passed by value actually require the caller to copy them to the stack, and then `const&` is cheaper.

## Return values

### When the copy is elided

In the count table above, `return c;` has no copy or move at all. This is NRVO (named return value optimization): [[class.copy.elision#1.1]] allows a local automatic object being returned to be constructed directly in the caller's result object. The assembly shows it clearly:

```cpp godbolt title="nrvo.cpp" flags="-std=c++2c -O2" ok
#include <string>
#include <utility>
void fill(std::string&);
std::string nrvo()  { std::string s; fill(s); return s; }
std::string moved() { std::string s; fill(s); return std::move(s); }
```

<div class="compare" markdown="1">

```asm
nrvo:
  ...
  mov  x19, x8       ; x8: address of the result object
  stp  xzr, xzr, [x8]
  str  xzr, [x8, #16] ; construct s right there
  mov  x0, x8
  bl   fill
  ...
  ret
```

```asm
moved:
  sub  sp, sp, #64
  ...
  mov  x19, x8
  stp  xzr, xzr, [sp, #8] ; s on the stack
  str  xzr, [sp, #24]
  add  x0, sp, #8
  bl   fill
  ldur q0, [sp, #8]   ; move: shift 24 bytes
  str  q0, [x19]
  ldr  x8, [sp, #24]
  str  x8, [x19, #16]
  ...
```

</div>

`std::move(s)` is an xvalue expression, no longer the name of a local variable; the condition of [[class.copy.elision#1.1]] is not met, NRVO cannot happen, and only a move construction is possible. Clang warns about this under `-Wall` with `-Wpessimizing-move`. For `std::string` the move just shifts 24 bytes; for types with expensive moves the cost is higher.

### When it isn't

The four forms in the count table that add a move or copy:

| Form | Count on our test machine | Reason |
|---|---|---|
| `if (b) return a; return c;` | 1 move | Two variables cannot both be constructed in the result object's place; Clang gives up NRVO |
| `return p;` (`p` is a parameter) | 1 move | Parameters are constructed by the caller; [[class.copy.elision#1.1]] excludes them explicitly |
| `return std::move(local);` | 1 move | The operand is no longer a name |
| `return b ? a : c;` | 1 copy | The conditional expression is an lvalue, not a move-eligible name |

The first three cannot be elided, but they still move rather than copy. This is because when the operand of `return` names a local variable or parameter, it is [[g:move-eligible]] and treated as an xvalue ([[expr.prim.id.unqual#15]]). This rule has been relaxed several times: C++20's [[P1825R0]] brought local variables of rvalue reference type under it, and C++23's [[P2266R3]] changed it to the current form, which treats the expression directly as an xvalue. Details in [[topics/special-members-and-elision]].

So writing `return std::move(p);` for a parameter is redundant, and Clang points this out with `-Wredundant-move` (included in `-Wall` with Clang 23). The fourth form must be rewritten as `if (b) return a; return c;`, trading a copy for a move.

The move when two branches return different variables is cheap for `std::string`. For large trivially copyable objects, moving is copying:

```cpp godbolt title="two-returns.cpp" flags="-std=c++2c -O2" ok
#include <array>
using Arr = std::array<double, 512>;   // 4 KiB
void fill(Arr&);
Arr two(bool b) {
  Arr a, c; fill(a); fill(c);
  if (b) return a;
  return c;
}
```

At `-O2` on our test machine, `two` ends with `csel x1, x21, x22, ne` selecting the source address, then `bl _memcpy` copying 4096 bytes. Compared with a version that does the same two `fill`s but always does `return a;`, `two` is 1.4 – 1.8 times slower (measured alternately in the same process, three runs).

One counterexample is worth a look: for this `Arr`, a single-variable `return std::move(a);` generates exactly the same code at `-O2` as `return a;`, both just `mov x0, x8` followed by a jump to `fill`. Copying a trivially copyable object has no observable side effects, so under the as-if rule ([[intro.abstract#1]]) the optimizer can let `fill` write straight into the result object and delete the `memcpy`. This is not copy elision but ordinary optimization, so it holds only for trivial types and only with optimization enabled.

### Large return values use sret

```cpp godbolt title="sret.cpp" flags="-std=c++2c -O2" ok
struct P   { int x, y; };
struct Big { double a[8]; };
P   make_p(int v)      { return {v, v + 1}; }
Big make_big(double d) {
  Big b;
  for (auto& e : b.a) e = d;
  return b;
}
```

`make_p` packs two `int`s into `x0` and returns them. `make_big` returns 64 bytes, which don't fit in registers; the caller allocates the result object in advance and passes its address as a hidden parameter. This is called **sret** (structure return). arm64 passes this address in the dedicated register `x8`; x86-64 System V uses the first argument register `rdi` and returns it in `rax`:

<div class="compare" markdown="1">

```asm
; arm64
make_big:
  dup.2d v0, v0[0]
  stp  q0, q0, [x8]
  stp  q0, q0, [x8, #32]
  ret
```

```asm
; x86-64 (--target=x86_64-linux-gnu)
make_big:
  mov    rax, rdi
  movlhps xmm0, xmm0
  movups [rdi + 16], xmm0
  movups [rdi], xmm0
  movups [rdi + 48], xmm0
  movups [rdi + 32], xmm0
  ret
```

</div>

sret is exactly the physical basis of NRVO and direct initialization from prvalues: the result object's address is known before the function starts, so the function can construct in place from its first instruction. So returning a large object by value is not expensive in itself; what is expensive is only the forms that defeat NRVO.

## Copies in loops and structured bindings

### Range `for`

[[stmt.ranged#1]] expands `for (decl : range)` into a loop that executes `decl = *begin;` on each iteration. When `decl` is written `auto s`, this is copy-initialization, copying each element once; written `const auto& s`, it only binds a reference.

| 1000 elements | A: `const auto&` | B: `auto` | B/A |
|---|---|---|---|
| `std::string(10)` (SSO) | about 0.47 µs | | 1.4 – 3.0 |
| `std::string(40)` (each allocates) | about 0.47 µs | | 160 – 220 |

Clang's `-Wrange-loop-construct` (included in `-Wall`) only warns on the form `for (const auto s : v)`, not on plain `for (auto s : v)`, since that may be an intentional copy. clang-tidy's `performance-for-range-copy` check covers that case.

The same warning catches another hidden copy:

```cpp
void walk(const std::map<std::string, int>& m) {
  for (const std::pair<std::string, int>& e : m)  // copies a pair every time
    (void)e;
}
```

The element type of `map` is `pair<const std::string, int>`, one `const` away from the declared type. The reference cannot bind directly, so each iteration constructs a temporary `pair<std::string, int>` and binds the reference to it. Clang 23 reports `-Wrange-loop-construct` for it. Using `const auto&` or `const value_type&` avoids the mistake.

### Structured bindings

`auto [k, v] = *it;` looks like it just names two members. But [[dcl.struct.bind#1]] says a structured binding declaration first introduces an unnamed variable `e`, initialized with the initializer, and `k` and `v` then refer to members of `e`. The `auto` written in the declaration applies to `e`, so `auto [k, v] = *it` copies the whole element; only `auto& [k, v]` or `const auto& [k, v]` avoid the copy.

| Iterating a 1000-element `map<string, string>` (33-byte keys, 40-byte values) | B/A |
|---|---|
| A: `for (const auto& [k, v] : m)`, B: `for (auto [k, v] : m)` | 75 – 108 |

## `const` turns moves into copies

`std::move` is just a cast to an rvalue reference ([[topics/value-categories]]). Applied to a `const T`, it yields `const T&&`, which `T(T&&)` cannot bind to, and overload resolution picks `T(const T&)`:

```cpp run title="const-move.cpp" ok
#include <cstdio>
#include <utility>

struct Counted {
  static inline int copies = 0, moves = 0;
  Counted() = default;
  Counted(const Counted&) { ++copies; }
  Counted(Counted&&) noexcept { ++moves; }
};

struct Rec {
  const Counted id;   // const member
  Counted data;
};

int main() {
  const Counted c;
  Counted x = std::move(c);        // copy
  std::printf("copy %d move %d\n", Counted::copies, Counted::moves);

  Counted::copies = Counted::moves = 0;
  Rec r{};
  Rec r2 = std::move(r);           // id copied, data moved
  std::printf("copy %d move %d\n", Counted::copies, Counted::moves);
}
```

The output is `copy 1 move 0` and `copy 1 move 1`. No warning, no error; the move silently degrades into a copy. The second case is easier to miss: a class's implicit move constructor moves member by member, and a `const` member can only be copied. Making a member `const` also deletes the implicit copy assignment and move assignment, so the type cannot be assigned once it is in a `std::vector`. To express immutability, making the member `private` and providing only a getter is usually cheaper than a `const` member.

## Putting elements into containers

### `push_back` and `emplace_back`

In the count table, `push_back(Counted(1))` first constructs a temporary and then moves it into the container; `emplace_back(1)` forwards the argument to the constructor and constructs directly in the container's memory, with zero moves.

The only difference is whether the argument is an already constructed object. `emplace_back(Counted(1))` and `emplace_back(std::move(x))` are exactly the same as the corresponding `push_back`. `push_back("text")` into a `vector<std::string>` first constructs a temporary `std::string` and then moves it, while `emplace_back("text")` does not; for short strings that move just copies 24 bytes.

`emplace_back` calls explicit constructors, so it also accepts conversions `push_back` rejects, such as `vector<std::unique_ptr<T>>::emplace_back(raw_ptr)`, and `vector<std::vector<int>>::emplace_back(100)` creating a 100-element vector. Switching to `emplace_back` everywhere just to save a move gains far less than this risk.

### `std::initializer_list` can only copy

In the count table, `std::vector<Counted> w{1, 2, 3}` copied 3 times. The elements in the braces are first copy-initialized into a **backing array** of type `const E[N]` ([[dcl.init.list#5]]), and the `vector` constructor then copies from that array. The array elements are `const` and cannot be moved from.

!!! std
    An object of type `std::initializer_list<E>` is constructed from an initializer list as if the implementation generated and materialized a prvalue of type "array of N `const E`".

    Behind an `initializer_list` is an array whose elements are `const E` ([[dcl.init.list#5]]).

Two direct consequences: move-only types cannot initialize a container with braces at all; `std::vector<std::unique_ptr<int>> v{std::make_unique<int>(1)};` fails with Clang 23 / libc++ (`no matching function for call to '__construct_at'`, ultimately needing the deleted copy constructor). And when copying elements is expensive, use `reserve` followed by `emplace_back` one by one instead; the count on our test machine is 0 copies and 0 moves. Lifetime problems with the backing array are in [[topics/dangling-references]].

### Inserting into a `map`

When the key already exists, how much wasted work do the different insertion functions do? With `map<std::string, std::string>`, 33-byte keys and 64-byte values, counting with a replaced `operator new` (libc++ on our test machine):

| Call when the key already exists | Allocations |
|---|---|
| `m.emplace("…33-byte literal…", val)` | 3 |
| `m.insert({"…", val})` | 2 |
| `m.try_emplace("…", val)` | 1 |
| `m.emplace(k, val)`, `k` is a `std::string` | 0 |
| `m.try_emplace(k, val)` | 0 |

`emplace` is specified to construct a `value_type` from its arguments and insert only if the key is not present. The key has to be constructed before it can be compared; in the general case libc++ first allocates a node, constructs the key and value inside it, and destroys everything after finding the duplicate, which is where the 3 allocations (node, key, value) come from. When the argument is exactly one `key_type`, libc++ looks it up first, so the fourth row is 0; this is a libc++ implementation detail, don't rely on it. `insert({…})` first constructs a temporary `pair` (one allocation each for key and value).

`try_emplace`'s specification says it explicitly: if the key already exists there is no effect ([[map.modifiers#4]]), and the value's constructor arguments are neither used nor moved from. The 1 remaining allocation comes from its parameter type being `const key_type&`, so the literal has to be converted to a temporary `std::string` first; passing a `std::string` gives 0. When you need insert-or-overwrite, use `insert_or_assign`: it assigns if the key exists and constructs directly from the arguments if it does not. `m[k] = v` first default-constructs a value and then assigns when the key is absent, and requires the value type to be default-constructible.

## Views instead of copies

```cpp
std::size_t len_ref(const std::string& s);
std::size_t len_sv(std::string_view s);

void caller() {
  len_ref("0123456789012345678901234567890123456789");  // temporary string
  len_sv("0123456789012345678901234567890123456789");   // pointer and length
}
```

40 characters exceeds libc++'s SSO capacity, so the caller of `len_ref` has to allocate a temporary `std::string`, copy the characters, and free it after the call. `len_sv`'s parameter is in two registers, `x0` and `x1`, and the callee is a single `mov x0, x1`. Measured alternately on our test machine, `len_ref` takes 70 – 110 ns per call and `len_sv` under 1 ns.

`std::span<const T>` does the same for contiguous arrays: one function can accept `std::vector<T>`, `std::array` and C arrays without copying and without forcing the caller to build a particular container first.

Views do not own their data; the price is that you must ensure the referenced object outlives the view yourself. Storing a `string_view` in a member, or returning a `string_view` to a temporary `std::string` from a function, are common sources of dangling; see [[topics/dangling-references]]. The rule of thumb: views make good parameters; convert to an owning type when storing.

## Checklist

| Form | Extra work | Fix |
|---|---|---|
| Large read-only object passed by value | 1 copy | `const&` |
| Small trivially copyable type passed by `const&` | A round trip through memory, possible aliasing | By value |
| Setter takes by value and moves, passed an lvalue | 1 allocation (gives up existing capacity) | `const&` + `&&` overloads |
| `return std::move(local);` | 1 move, loses NRVO | `return local;` |
| `return b ? x : y;` | 1 copy | Two `return` statements |
| Two branches return different locals | 1 move (`memcpy` for trivial types) | Use a single result variable |
| `for (auto s : v)` | 1 copy per element | `const auto&` or `auto&` |
| `auto [k, v] = *it` | Copies the whole element | `const auto& [k, v]` |
| `std::move` of a `const` object, or a class with `const` members | Move becomes copy | Drop the `const` |
| `vector<T> v{a, b, c}` with expensive-to-copy `T` | 1 copy per element | `reserve` + `emplace_back` |
| `map::emplace` / `insert` when the key often exists | Whole node constructed then discarded | `try_emplace` |
| `const std::string&` parameter receiving a literal | 1 allocation | `std::string_view` |

When hunting these problems, first confirm the counts with counters or allocation counts, then use a [[perf/measuring|benchmark]] to see whether it is worth changing on the hot path. Clang's `-Wpessimizing-move`, `-Wredundant-move` and `-Wrange-loop-construct` are all in `-Wall`; how to read assembly is in [[perf/reading-assembly]].

!!! question "Questions"
    1. How many copies or moves happen in `std::optional<std::string> f() { std::string s = g(); return s; }`? And if the return type is changed to `std::string`?
    2. The struct `struct S { int a; std::string_view b; };` is 24 bytes. On arm64, is it passed in registers when passed by value?

<details markdown="1">
<summary>Answer</summary>

1. With return type `std::optional<std::string>`, `s` and the return type differ, so [[class.copy.elision#1.1]] does not apply (it requires the same type) and NRVO is impossible. But `s` is still move-eligible ([[expr.prim.id.unqual#15]]), and `optional`'s converting constructor accepts `std::string&&`, so there is 1 move. With return type `std::string`, NRVO usually applies, giving 0; even if not elided, it is 1 move.

2. Not entirely in registers. AAPCS64 puts only composite types of at most 16 bytes in general-purpose registers; larger composite types are copied to memory by the caller, which passes their address. You can compile `int f(S s) { return s.a; }` to check: the callee reads `a` from the memory `x0` points to. Split into `f(int a, std::string_view b)`, three registers suffice.

</details>
