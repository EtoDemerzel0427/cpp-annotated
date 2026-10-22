---
title: Class template hash
summary: "Every specialization of std::hash is either enabled or disabled: a disabled specialization exists but cannot be constructed or called, so it can be detected at compile time; an enabled specialization must agree with ==, must not throw, and its hash values are stable only within one execution of a program."
updated: 2026-10-19
---

!!! tldr
    - `std::hash<Key>` is the default hash function of the unordered containers. The standard guarantees usable specializations for `nullptr_t` and for all cv-unqualified arithmetic, enumeration and pointer types.
    - A type without a specialization (including `pair`, `tuple` and your own classes) corresponds to a disabled specialization: it exists but cannot be constructed or called, so `is_default_constructible_v<hash<T>>` can be used to tell whether `T` is hashable.
    - An enabled specialization must satisfy: if `k1 == k2` then `h(k1) == h(k2)`; and specializations provided by the standard library do not throw.
    - Hash values are stable only within the current execution of the program and must not be written to files or passed between processes.
    - `hash<const int>` is disabled, and `hash<const char*>` hashes the pointer, not the contents of the string.

## Starting from a compile error

```cpp run title="disabled_use.cpp" error
#include <unordered_set>
struct Point { int x, y; bool operator==(const Point&) const = default; };
std::unordered_set<Point> s;   // error: hash<Point> is a disabled specialization and cannot be default-constructed
int main() {}
```

Paragraph 1 of [unord.hash] specifies that the unordered associative containers (`unordered_map`, `unordered_set` and so on, [[unord.req]]) use `std::hash<Key>` as their default hash function. The standard library provides no specialization for `Point`, so the container above cannot use the default hash. libc++ in our tests reports "call to implicitly-deleted default constructor of 'hasher'".

To understand where this error comes from, first look at the standard's general requirements on hash functions, then at enabling and disabling `std::hash`.

## The Cpp17Hash requirements ([hash.requirements])

Paragraph 1 of [hash.requirements] specifies that a type `H` meets the *Cpp17Hash* requirements if and only if it is a function object type ([[function.objects]]), meets the requirements for being copy-constructible and destructible, and the expressions in the table below are valid and have the indicated semantics. Paragraph 2 fixes the notation: `h` is a (possibly const) value of type `H`, `u` is an lvalue of type `Key`, and `k` is a value of a type convertible to (possibly const) `Key`.

| Expression | Return type | Requirement |
|---|---|---|
| `h(k)` | `size_t` | the value returned depends only on the argument `k` for the duration of the program; the probability of two different values having equal hashes should be very small, approaching `1.0 / numeric_limits<size_t>::max()` |
| `h(u)` | `size_t` | shall not modify `u` |

Three things in this table deserve attention:

1. Stability is limited to the duration of the program. Note 1 says it more plainly: within the same execution, `h(k)` gives the same result for the same value. There is no guarantee whatsoever across executions; an implementation may randomize a seed at startup to resist hash-flooding attacks, and may change algorithms between versions. Writing the results of `std::hash` to a file, sending them over the network or using them as persistent keys all rely on something the standard does not guarantee.
2. The collision probability uses "should", so it is only a recommendation. libc++ returns integers no wider than `size_t` unchanged, which is fully conforming, since different integers never collide at all, but it distributes poorly for a set of keys with identical low bits. This is a quality issue, not a conformance issue.
3. `h` may be const, so `operator()` must be callable on a const object.

## Enabled and disabled specializations (¶2–¶4)

¶2 Each specialization of `hash` is either **enabled** or **disabled**. Note 1 says that enabled specializations meet *Cpp17Hash* and disabled ones do not.

Each header that declares the `hash` template provides enabled specializations for `nullptr_t` and for all cv-unqualified arithmetic, enumeration and pointer types. For any other type `Key`, if neither the standard library nor the user provides an explicit or partial specialization, `hash<Key>` is disabled ([[g:disabled-hash-specialization]]).

¶3 Specializations provided by the standard library are enabled unless otherwise specified, and their member functions are `noexcept` unless otherwise specified. The typical "otherwise specified" is conditional enabling: `hash<optional<T>>` is enabled if and only if `hash<remove_const_t<T>>` is enabled, and `hash<variant<Ts...>>` and `hash<unique_ptr<T, D>>` are similar.

¶4 specifies what a disabled specialization looks like:

!!! std
    If H is a disabled specialization of hash, these values are false: is_default_constructible_v&lt;H&gt;, is_copy_constructible_v&lt;H&gt;, is_move_constructible_v&lt;H&gt;, is_copy_assignable_v&lt;H&gt;, and is_move_assignable_v&lt;H&gt;.

In addition, a disabled specialization is not a function object type. Note 2 sums it up: the specialization exists, but any attempt to use it as a *Cpp17Hash* is ill-formed.

```cpp run title="enabled_disabled.cpp" ok
#include <functional>
#include <string>
#include <type_traits>
#include <unordered_set>
#include <utility>
#include <cstdio>

struct Opaque { int v; };
enum class Color { red, green };

// disabled specializations: the type exists but cannot be constructed or called
static_assert(!std::is_default_constructible_v<std::hash<Opaque>>);
static_assert(!std::is_copy_constructible_v<std::hash<Opaque>>);
static_assert(!std::is_invocable_v<std::hash<Opaque>, Opaque>);
static_assert(!std::is_default_constructible_v<std::hash<std::pair<int, int>>>);  // the standard provides none for pair
static_assert(!std::is_default_constructible_v<std::hash<const int>>);           // only cv-unqualified types are provided
// enabled specializations
static_assert(std::is_default_constructible_v<std::hash<Color>>);
static_assert(std::is_nothrow_invocable_v<std::hash<int*>, int*>);
static_assert(std::is_default_constructible_v<std::hash<std::nullptr_t>>);

struct Point { int x, y; bool operator==(const Point&) const = default; };
template<> struct std::hash<Point> {          // specialization for a program-defined type, must precede first use
  std::size_t operator()(const Point& p) const noexcept {
    std::size_t h = std::hash<int>{}(p.x);
    return h ^ (std::hash<int>{}(p.y) + 0x9e3779b97f4a7c15 + (h << 6) + (h >> 2));
  }
};

int main() {
  std::unordered_set<Point> s{{1, 2}, {3, 4}, {1, 2}};
  std::printf("%zu\n", s.size());                                               // 2
  std::printf("%d\n", std::hash<double>{}(0.0) == std::hash<double>{}(-0.0));  // 1
}
```

### Why disabled specializations exist

In C++11 the primary template `hash<T>` was only declared, not defined, so unsupported types corresponded to an incomplete type. This had two problems:

- Using traits such as `is_default_constructible` on an incomplete type is {{ub}} (a precondition in [[meta.unary.prop]]), and the result gets fixed at the first instantiation, so it cannot be detected reliably.
- The standard library itself needs conditionally enabled specializations: when `hash<T>` is unusable, `hash<optional<T>>` should be unusable too. If "unusable" meant an incomplete type, `hash<optional<T>>` could only be written as a complicated set of partial specializations.

C++17's [[P0513R0]] switched to disabled specializations: the type is complete but cannot be constructed, copied or called. This made `is_default_constructible_v<hash<T>>` a reliable way to tell whether something is hashable, and lets containers give clear diagnostics based on it.

!!! impl "What libc++ does"
    libc++'s `hash<T>` inherits from `__hash_impl<T>`. The primary template of `__hash_impl` declares the default constructor, copy constructor and copy assignment as `= delete`, so no move operations are implicitly declared, and it has no `operator()`. Only the partial specializations for cv-unqualified enumeration, integral and floating-point types provide a real implementation; the `__is_unqualified_v<_Tp>` in their conditions corresponds exactly to "cv-unqualified" in ¶2.

!!! lawyer "`hash<const int>` is disabled"
    ¶2 only guarantees cv-unqualified types. `std::hash<const int>` has no library specialization and is disabled by the fallback rule. Containers use `hash<Key>`, and `Key` usually has no const, so this rarely comes up. In generic code that writes `std::hash<T>` where `T` may be deduced as `const U`, apply `remove_const_t` first. The standard library's `hash<optional<T>>` relies on `hash<remove_const_t<T>>` for exactly this reason.

## What an enabled specialization must do (¶5)

An enabled specialization `hash<Key>`:

- ¶5.1 meets *Cpp17Hash* with `Key` as the argument type, and also *Cpp17DefaultConstructible*, *Cpp17CopyAssignable* and *Cpp17Swappable*. This asks much more than *Cpp17Hash* itself, because containers need to default-construct and swap hash function objects.
- ¶5.2 If `k1 == k2` is true, then `h(k1) == h(k2)` is also true; that is, the hash agrees with `operator==`.
- ¶5.3 `h(k)` does not throw, unless `hash<Key>` is a program-defined specialization. So the enabled specializations of the standard library, including `hash<std::string>`, do not throw; users' own specializations may.

A consequence of ¶5.2: `0.0 == -0.0`, so `hash<double>` must give the two values the same result, even though their bit patterns differ. libc++ writes `if (__v == 0.0f) return 0;` specifically for this. NaN is unequal to every value, so ¶5.2 places no constraint on it; put NaN into an unordered container as a key and you will never find it again.

## Providing a hash for your own type

There are two ways:

1. Specialize `std::hash`. [[namespace.std]] allows adding specializations of class templates in `std` for program-defined types, provided the specialization meets the requirements of the original template, that is, all of ¶5 above. The specialization must be declared before every use that would cause an implicit instantiation; otherwise the program is ill-formed, no diagnostic required ([[temp.expl.spec#7]]). In practice Clang reports "explicit specialization of 'std::hash&lt;Point&gt;' after instantiation" directly.
2. Write a separate hash function object and pass it as the container's template argument: `std::unordered_set<Point, PointHash>`. This does not touch `std` and has no declare-first restriction.

Either way, the hash must agree with the equality predicate used by the container; otherwise the container will exhibit "inserts fine, cannot be found".

## Heterogeneous lookup and transparent hashes

Since C++20, unordered containers can look up with a type different from `Key` ([[P0919R3]] and others), provided both the hash and the equality predicate declare an `is_transparent` member type ([[function.objects]]). `std::hash<std::string>` is not transparent, so you need to wrap it yourself. [[basic.string.hash]] guarantees that `hash<string>` and `hash<string_view>` give the same value for the same contents, so implementing a transparent hash with `hash<string_view>` is safe:

```cpp run title="transparent_hash.cpp" ok
#include <functional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <cstdio>

struct sv_hash {
  using is_transparent = void;          // both the hash and the equality predicate must be transparent
  std::size_t operator()(std::string_view s) const noexcept {
    return std::hash<std::string_view>{}(s);
  }
};

int main() {
  std::unordered_map<std::string, int, sv_hash, std::equal_to<>> m{{"one", 1}};
  std::string_view k = "one";
  std::printf("%d\n", m.find(k)->second);    // no temporary std::string is constructed
  std::printf("%d\n", std::hash<std::string>{}("abc") == std::hash<std::string_view>{}("abc"));  // 1
}
```

!!! pitfall "`hash<const char*>` hashes the address"
    `const char*` is a pointer type, and `std::hash<const char*>` is the pointer specialization from ¶2: it hashes the pointer value itself, regardless of the contents of the string pointed to. In a `std::unordered_set<const char*>`, two strings with the same contents at different addresses are two different keys.

## Which types have enabled specializations

Besides the fundamental types of ¶2, the standard library provides specializations for many types in their respective headers. Common ones are `basic_string`, `basic_string_view`, `unique_ptr`, `shared_ptr`, `optional` (conditionally enabled), `variant` (conditionally enabled), `monostate`, `bitset`, `vector<bool>`, `error_code`, `error_condition`, `type_index`, `thread::id`, `coroutine_handle`, `filesystem::path`, and, since C++26, various `chrono` time types.

`pair`, `tuple`, `array`, `vector<T>` (other than `bool`) and the other containers have no specializations. The standard does not specify a way to combine several hash values; you have to write it yourself.

The `hash` class template itself is marked freestanding in `<functional>`.

## Questions

!!! question "Question 1"
    Can the following concept be used to determine whether `T` is hashable?
    `template<class T> concept hashable = requires(T t) { std::hash<T>{}(t); };`

<details markdown="1">
<summary>Answer</summary>

Yes. For a disabled specialization, `std::hash<T>{}` itself is ill-formed (the default constructor is deleted), so the `requires` expression is false; for an enabled specialization it is true. Note that `T` may be `const U`: `hashable<const int>` is false, because `hash<const int>` is disabled.
</details>

!!! question "Question 2"
    A program writes `std::hash<std::string>{}(username)` to a database as a shard number, and after upgrading the standard library the data ends up in the wrong places. Is this a defect in the standard library?

<details markdown="1">
<summary>Answer</summary>

No. [hash.requirements] only requires the returned value to depend only on the argument for the duration of the program; it may differ between executions, versions and implementations. When a stable hash is needed, use a hash function whose algorithm is precisely specified (for example a fixed version of FNV or xxHash), not `std::hash`.
</details>
