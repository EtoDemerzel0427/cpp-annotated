---
title: type_index
summary: "std::type_index wraps the non-copyable type_info into a copyable, comparable, hashable value usable as a key of map or unordered_map; equality forwards to type_info::operator==, ordering uses before, and the hash equals hash_code()."
updated: 2026-10-19
---

!!! tldr
    - `type_info` can't be copied, has no `<` and no `std::hash` specialization, so it can't be used directly as a container key; `std::type_index` stores a `const type_info*` internally and adds these operations.
    - The constructor is implicit, so `m[typeid(T)]` can be written directly.
    - `==` compares the `type_info`s, not the pointers; `<` and the rest are implemented with `type_info::before`, whose order is unspecified, so the iteration order of a `std::map<type_index, T>` isn't portable.
    - The result of `std::hash<type_index>` equals `hash_code()`, and different types may collide.

## Types as keys

```cpp run title="type-index.cpp" ok
#include <cassert>
#include <map>
#include <string>
#include <typeindex>
#include <unordered_map>

struct Base { virtual ~Base() = default; };
struct Derived : Base {};

int main() {
  std::unordered_map<std::type_index, std::string> names{
    {typeid(int), "int"},          // type_info converts implicitly to type_index
    {typeid(Derived), "Derived"},
  };
  Derived d;
  Base& b = d;
  assert(names.at(typeid(b)) == "Derived");   // polymorphic glvalue: dynamic type
  assert(std::type_index(typeid(const int)) == typeid(int));

  std::map<std::type_index, int> ordered;     // ordered by before()
  ordered[typeid(double)] = 1;
  ordered[typeid(char)] = 2;

  std::type_index ti = typeid(int);
  assert(std::hash<std::type_index>{}(ti) == ti.hash_code());
  assert((ti <=> std::type_index(typeid(int))) == 0);
}
```

Registries that dispatch by type, event buses, and service locators with one instance per type all need to look things up with a type as the key. `typeid` gives a `const std::type_info&`, and `type_info` can be neither copied nor assigned ([[type.info]]), so it can't go into a container. `std::type_index` (C++11, header `<typeindex>`) is the wrapper made for this.

The rules of `typeid` apply as usual: top-level cv-qualifiers and references are ignored; applied to a glvalue of polymorphic type, it gives the dynamic type.

## Definition [type.index.synopsis], [type.index]

`<typeindex>` includes `<compare>` and `<typeinfo>` and declares `type_index`, the `hash` primary template, and the `hash<type_index>` specialization.

The only exposition-only member of `type_index` is `const type_info* target;`. A comment in the synopsis explains why it is a pointer rather than a reference: a class with a reference member has its implicit copy assignment operator defined as deleted ([[class.copy.assign]]), and only a pointer lets the default copy and move operations work.

¶1 `type_index` is a simple wrapper for `type_info` that can be used as an index type in associative containers ([[associative]]) and unordered associative containers ([[unord]]).

| Member | Effect | Paragraph |
|---|---|---|
| `type_index(const type_info& rhs) noexcept` | `target = &rhs`, an implicit conversion | ¶2 |
| `==` | `*target == *rhs.target` | ¶3 |
| `<`, `>`, `<=`, `>=` | All expressed with `type_info::before`; for example `<` is `target->before(*rhs.target)` | ¶4–¶7 |
| `<=>` | Returns `equal` if equal, `less` if `before` is true, otherwise `greater`; the type is `strong_ordering` | ¶8 |
| `hash_code()` | `target->hash_code()` | ¶9 |
| `name()` | `target->name()` | ¶10 |
| `hash<type_index>` | For any `index`, the result is the same as `index.hash_code()` | ¶11 |

¶3 compares the two `type_info`s, not the two pointers. The standard doesn't guarantee that every `typeid` of the same type yields the same object, and across shared libraries it often doesn't, so comparing pointers would go wrong. How `type_info`'s `==` is implemented on each platform is described in the implementation note in [[support.rtti]].

The order of `before` is unspecified and may vary between programs ([type.info] paragraph 1); it has nothing to do with the lexicographic order of type names or declaration order. `hash_code()` only guarantees the same value for the same type within one execution.

`!=` is obtained by rewriting `==`, and `<=>` was added in C++20 by [[P1614R2]]. None of `type_index`'s members are `constexpr`, even though `type_info::operator==` has been `constexpr` since C++23.

!!! pitfall "Assuming `name()` is readable or portable"
    `name()` returns an implementation-defined string. GCC and Clang return the mangled name (`"i"` for `int`), and MSVC returns a readable name. Don't use it as a serialization key, and don't compare it across processes.
