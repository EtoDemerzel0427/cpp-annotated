---
title: Trivially copyable types
summary: "Objects of trivially copyable types can be copied byte by byte: storing the bytes away and copying them back, or copying between two objects, preserves the value; exactly which value an object gets when it acquires a value representation is specified by a value-set model."
updated: 2026-10-19
---

!!! tldr
    - For an object of a trivially copyable type, copying its bytes into a `char`, `unsigned char` or `std::byte` array and back restores the original value, even if the original value was indeterminate.
    - Copying bytes between two such objects of the same type gives the destination the source's value. `memcpy`, `bit_cast` and type punning with `memcpy` all rest on this.
    - Base class subobjects and `[[no_unique_address]]` members are outside the guarantee, because their tail padding may be occupied by other objects.
    - For types that are not trivially copyable (such as `std::string`), `memcpy` guarantees nothing.
    - A bit pattern may correspond to no value at all (like `0x02` for `bool`), or, for pointers, to several values; when such a pattern is acquired, one value that gives the program defined behavior is chosen.

[[basic.types.general#7]] defines [[g:trivially-copyable-type|trivially copyable types]]: scalar types, trivially copyable classes ([[class.prop#1]]), arrays of these, and their cv-qualified versions. This subclause explains what the category guarantees: for these types, copying bytes is copying the value.

## Storing the bytes away and copying them back (¶3)

```cpp run ok
#include <cstring>
#include <cstddef>

struct T { int a; double b; char c; };   // trivially copyable, with padding

int main() {
  constexpr std::size_t N = sizeof(T);
  std::byte buf[N];
  T obj{1, 2.5, 'x'};
  std::memcpy(buf, &obj, N);   // store the bytes away
  obj.a = 100; obj.c = 'y';    // obj may be modified in between
  std::memcpy(&obj, buf, N);   // copy them back: every scalar subobject regains its original value
  return (obj.a == 1 && obj.b == 2.5 && obj.c == 'x') ? 0 : 1;
}
```

This is a runnable version of Example 1 in the standard.

¶3 For an object of trivially copyable type `T` that is not a potentially-overlapping subobject (see below), whether or not it holds a valid value of type `T`, the underlying bytes making up the object can be copied into an array of `char`, `unsigned char` or `std::byte`, for example with `std::memcpy` or `std::memmove`. If the contents of the array are copied back into the object, the object acquires its original value representation. What acquiring a value representation means exactly is given by the value-set model later; for types like integers and floating-point, the result is the original value.

Two points deserve attention:

- Whether or not it holds a valid value. Even if the object's value is indeterminate ([[basic.indet]]), it can be stored and restored. Code that saves context or rolls back transactions only copies bytes without interpreting them, and is therefore valid.
- The element type of the intermediate array can only be `char`, `unsigned char` or `std::byte`. This corresponds to [[basic.lval#11]], which allows accessing the bytes of any object through these three types. `signed char` is not among them.

## Copying between two objects (¶4)

```cpp run ok
#include <cstring>

struct Point { int x, y; };

int main() {
  Point a{1, 2}, b{};
  std::memcpy(&b, &a, sizeof(Point));   // b acquires a's value representation
  return (b.x == 1 && b.y == 2) ? 0 : 1;
}
```

¶4 For two distinct such objects `obj1` and `obj2`, if the underlying bytes of `obj1` are copied into `obj2`, `obj2` acquires the value representation of `obj1`.

The comment in Example 2 of the standard says that after the copy, every subobject of trivially copyable type in `*t1p` contains the same value as the corresponding subobject in `*t2p`. What is guaranteed is the same value, not the same bytes. The standard does not care whether padding bytes match.

## Cases the guarantee does not cover

### Potentially-overlapping subobjects

A [[g:potentially-overlapping-subobject|potentially-overlapping subobject]] is a base class subobject or a non-static data member with `[[no_unique_address]]` ([[intro.object#7]]). The ABI may place members of a derived class in the tail padding of a base class, so writing a whole `sizeof(Base)` block into a base class subobject overwrites bytes that do not belong to it:

```cpp run
#include <cstdio>
#include <cstring>
#include <type_traits>

struct Base {
  int i;
  char get() const { return c; }
private:
  char c = 0;  // different access control: Base is not standard-layout,
};             // so the Itanium ABI may reuse its tail padding
struct Derived : Base { char d; };

static_assert(std::is_trivially_copyable_v<Base>);

int main() {
  Derived x{};
  x.d = 'Z';
  Base b{};
  Base& rb = x;                        // a base class subobject: potentially overlapping
  std::memcpy(&rb, &b, sizeof(Base));  // outside the guarantee
  std::printf("%zu %zu %d\n", sizeof(Base), sizeof(Derived), x.d);
}
```

In our tests (arm64 macOS, Clang 23) the output is `8 8 0`: `Derived` is the same size as `Base`, `d` sits in `Base`'s tail padding, and this `memcpy` zeroed it. The layout is the same on x86-64 Linux.

### Types that are not trivially copyable

For other types this subclause guarantees nothing; the standard does not say what value the destination holds after the copy. Overwriting a `std::string` with `memcpy` is such a case:

```cpp run ub
#include <cstring>
#include <string>

int main() {
  std::string a = "a fairly long string that defeats SSO";
  std::string b;
  std::memcpy(static_cast<void*>(&b), &a, sizeof a);  // UB: string is not trivially copyable
}   // a and b free the same heap memory when destroyed
```

The practical consequences depend on the string's length:

- A long string's characters live on the heap. After the copy, the internal pointers of `a` and `b` point to the same heap block, and the two destructions are a double free. Running it with `-fsanitize=address` in our tests, ASan reports `attempting double-free`.
- A short string may use the small string optimization (SSO), storing characters directly inside the object. If the implementation's internal pointer points into the object's own buffer (as libstdc++'s does), the copied pointer still points into `a`, and `b` dangles once `a` is destroyed.

GCC has a `-Wclass-memaccess` warning for such calls.

### const objects

¶3 and ¶4 say that copying bytes makes the object acquire a value representation, but modifying a const complete object is UB in itself ([[basic.life]], [[dcl.type.cv]]). Trivial copyability cannot be used to get around const.

## Which value is obtained when acquiring a value representation (¶1–¶2)

For `int`, copying the original bytes back gives the original value; that goes without saying. But two cases need a more precise rule: a bit pattern may correspond to no value, or to more than one.

### The value-set model

¶1 sets up the following model for each trivially copyable type `T`:

1. `T` has an implementation-defined, discrete set of **values**.
2. Each possible value representation of an object corresponds to a subset of this set, with distinct value representations corresponding to distinct subsets.
3. The union of all the subsets is the whole set of values. For scalar types other than object pointer types, each subset has at most one value.
4. Some operations make an object [[g:acquire-value-representation|acquire a value representation]]: the object's value is replaced with a member of the corresponding subset. Which one is unspecified, but it is one that gives the program defined behavior, if any.

!!! std
    the object's value is replaced with an unspecified member of the corresponding subset that would result in the program having defined behavior, if any.

This kind of rule, where the interpretation that makes the program valid is chosen whenever one exists, is often called **angelic choice**.

### A bit pattern with no value: `bool`

"At most one" means a subset can be empty. `bool` usually occupies 8 bits, but only `0x00` and `0x01` correspond to `false` and `true` ([[basic.fundamental#10]]); the other 254 bit patterns correspond to no value on mainstream implementations.

```cpp run ub
#include <cstdio>
#include <cstring>

int main() {
  unsigned char byte = 2;
  bool b;
  std::memcpy(&b, &byte, 1);  // b acquires the value representation 0x02, which corresponds to no bool value
  if (b)  std::puts("true");  // UB
  if (!b) std::puts("false");
}
```

With Clang 23 on arm64, it prints `true` at `-O0` and `false` at `-O2`: the same program behaves differently. Run with `-fsanitize=undefined`, UBSan reports `load of value 2, which is not a valid value for type 'bool'`.

`std::bit_cast` specifies this case explicitly: if an object in the result would get no value, the behavior is undefined ([[bit.cast#3]]).

### A bit pattern with several values: pointers

For object pointers, one value representation can correspond to several values. Note 1 in ¶2 gives one case: at the same address there can be a pointer to an old object that has been destroyed and a pointer to a new object allocated later at the same place, where the durations of their storage do not overlap.

Another case is past-the-end pointers. In `int a, b;`, if `b` happens to immediately follow `a`, `&a + 1` and `&b` have exactly the same bits, but the former is the past-the-end pointer of `a` and does not point to `b` ([[basic.compound#3]]).

So when a pointer's bytes are copied back, the standard cannot simply say the original value is obtained, because when copying between objects as in ¶4, the destination does not know which value the source held at the time. Angelic choice answers this: pick one of the candidate values that gives the program defined behavior.

```cpp run ok
#include <cstring>

int main() {
  int x = 42;
  int* p = &x;
  unsigned char buf[sizeof p];
  std::memcpy(buf, &p, sizeof p);   // store the bytes away
  int* q;
  std::memcpy(&q, buf, sizeof q);   // q acquires p's value representation
  return *q == 42 ? 0 : 1;          // OK: the value that makes this defined is a pointer to x
}
```

When an integer is converted to a pointer, [[expr.reinterpret.cast#5]] uses the same wording: a pointer value that gives the program defined behavior is chosen, and if there is none the behavior is undefined.

!!! note "This model is new wording after C++23"
    In C++23 and earlier, this guarantee was just two sentences in [[basic.types.general]]: if the bytes are stored away and copied back, the object subsequently holds its original value; if bytes are copied between two objects, the destination holds the same value as the source. The current draft split it into its own subclause and introduced value sets and acquiring a value representation, mainly to answer the pointer question above. The rules in [[basic.compound]] ¶4–¶6 about when pointers are valid are part of the same change.

## Relation to other tools

| Tool | Type requirement | Relation to this subclause |
|---|---|---|
| `std::memcpy`, `std::memmove` | none | first implicitly create objects at the destination ([[intro.object#13]]), then copy bytes; when the destination is an object of trivially copyable type, ¶3 and ¶4 give the value after the copy |
| `std::bit_cast` ([[bit.cast]]) | source and destination both trivially copyable, of equal size | objects in the result acquire value representations; UB if no value is obtained; usable in constant evaluation |
| `std::atomic<T>` | `T` trivially copyable | atomic operations compare and exchange by value representation; since C++20 `compare_exchange` ignores padding bits |
| `std::start_lifetime_as<T>` ([[obj.lifetime]]) | `T` a complete implicit-lifetime type | starts the lifetime of a `T` over existing bytes, treating them as the value representation of the `T` |

!!! note "The right way to type-pun"
    To look at the bits of a `float` as a `std::uint32_t`, use `std::bit_cast<std::uint32_t>(f)` since C++20, and `std::memcpy(&u, &f, sizeof u)` before that. Both rely on this subclause: both types are trivially copyable, and the value representation the destination acquires is interpreted as a `uint32_t` value. Writing `*(std::uint32_t*)&f` instead violates the aliasing rule of [[basic.lval#11]] and is UB.

!!! impl
    - GCC and Clang both treat `memcpy` as a builtin; a small `memcpy` of fixed length compiles to one or two load and store instructions, so using it for type punning costs nothing.
    - `std::copy` and `std::uninitialized_copy` in libc++ and libstdc++ switch to `memmove` when the element type is trivially copyable.
    - In LLVM IR, copying a pointer byte by byte preserves its provenance (the information about which object a pointer points to), consistent with the model in ¶1 where one value representation corresponds to several pointer values.

## History

!!! history
    - In C++98 this guarantee applied only to POD types and excluded base class subobjects; the wording was that the object subsequently holds its original value.
    - C++11 widened the scope from POD to trivially copyable types, because whether something can be `memcpy`ed has nothing to do with whether it is standard-layout.
    - C++17 added `std::byte` as a valid intermediate buffer type.
    - C++20, with `[[no_unique_address]]`, changed the excluded objects from base class subobjects to potentially-overlapping subobjects; added `std::bit_cast`; and specified that `memcpy` and `memmove` implicitly create objects ([[P0593R6]]).
    - The post-C++23 draft split this part into its own subclause 6.9.2 and introduced the model of value sets and acquiring a value representation.

## Common misconceptions

!!! pitfall "Equal under `memcmp` means equal values"
    This subclause only guarantees that copying preserves values, not that equal values are equivalent to equal bytes. Padding bytes, `+0.0` and `-0.0`, multiple NaN bit patterns, and pointers with different provenance all make the two diverge. Before comparing or hashing byte by byte, check `std::has_unique_object_representations_v<T>` ([[basic.types]]).

!!! pitfall "A `signed char` buffer works too"
    ¶3 lists only `char`, `unsigned char` and `std::byte`. Using a `signed char` array as the intermediary works in practice, but is outside the standard's guarantee.

## Questions

!!! question "1. Does `int* p = new int(1); delete p; int* q; std::memcpy(&q, &p, sizeof p);` have UB? What about then executing `if (q) {}`?"

<details markdown="1">
<summary>Answer</summary>

The copy itself has no UB. ¶3 and ¶4 say bytes can be copied whether or not the object holds a valid value, and in the current draft a pointer's value does not change when the storage is released; it merely becomes invalid in later evaluations ([[basic.compound#6]]). `q` acquires `p`'s value representation.

`if (q)` is a boolean conversion that uses a pointer value invalid in that evaluation, which per [[basic.compound#6.2]] is implementation-defined behavior, not UB. Only an indirection like `*q` is UB.
</details>

!!! question "2. Why does ¶1 say that for scalar types other than object pointers each subset has at most one value, rather than exactly one?"

<details markdown="1">
<summary>Answer</summary>

"At most one" allows a subset to be empty, meaning some bit patterns correspond to no value. The classic example is `bool`: it has only two values, but its value representation usually has 8 bits. If exactly one were required, the implementation would have to assign a `bool` value to `0x02`, and compilers could no longer assume a `bool` is only 0 or 1. Empty subsets, together with the rule in [[bit.cast#3]] that getting no value is UB, make this case clearly UB.
</details>
