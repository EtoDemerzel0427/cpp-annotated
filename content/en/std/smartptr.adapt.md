---
title: out_ptr and inout_ptr
summary: "Two C++23 adaptors that pass a smart pointer directly to a C-style T** output parameter: the temporary hands the result back to the smart pointer only at the end of the full-expression; out_ptr with shared_ptr requires a deleter, and inout_ptr cannot be used with shared_ptr."
updated: 2026-10-19
---

!!! tldr
    - `f(std::out_ptr(sp))` creates a temporary; the C function writes the result into the raw pointer inside it, and when the temporary is destroyed at the end of the full-expression, it `reset`s the result into `sp`.
    - `out_ptr` clears `sp` before the C function is called; when the C function needs to read and dispose of the old value, use `inout_ptr`, which `release()`s the old value at the end instead of deleting it.
    - Reading `sp` within the same full-expression still sees the cleared value.
    - `shared_ptr` with `out_ptr` must be given a deleter, otherwise the program is ill-formed; `shared_ptr` with `inout_ptr` is always ill-formed.
    - It can be passed to a `void**` parameter, but the same temporary can be converted only once.

## Why it is needed

Many C APIs return newly allocated resources through an output pointer parameter, for example `int sqlite3_open(const char*, sqlite3**)`. Handing the result to a `unique_ptr` traditionally takes an intermediate raw pointer:

```cpp
sqlite3* raw = nullptr;
int rc = sqlite3_open(name, &raw);
std::unique_ptr<sqlite3, closer> db(raw);   // an exception or early return in between leaks raw
```

C++23's `out_ptr` and `inout_ptr` ([[P1132R8]]) fold these three steps into one expression:

```cpp run title="out-ptr.cpp" ok
#include <memory>
#include <cstdio>
#include <cstdlib>

// a simulated C API
struct widget { int id; };
extern "C" int widget_create(widget** out, int id) {
  if (id < 0) return -1;                     // on failure, *out is not written
  *out = static_cast<widget*>(std::malloc(sizeof(widget)));
  (*out)->id = id;
  return 0;
}
extern "C" int widget_recreate(widget** inout, int id) {
  std::free(*inout);                         // free the old object first
  *inout = nullptr;
  return widget_create(inout, id);
}
extern "C" int any_create(void** out) {
  *out = std::malloc(4);
  return 0;
}
struct free_deleter {
  void operator()(void* p) const noexcept { std::free(p); }
};

int main() {
  std::unique_ptr<widget, free_deleter> w;
  if (widget_create(std::out_ptr(w), 7) == 0)
    std::printf("created %d\n", w->id);
  widget_recreate(std::inout_ptr(w), 8);
  std::printf("recreated %d\n", w->id);

  std::shared_ptr<widget> s;
  widget_create(std::out_ptr(s, free_deleter{}), 9);
  std::printf("shared %d\n", s->id);

  std::unique_ptr<int, free_deleter> raw;
  any_create(std::out_ptr(raw));             // int* passed to void** via operator void**()
  std::printf("void** ok: %d\n", raw != nullptr);
}
```

In our tests it prints `created 7`, `recreated 8`, `shared 9`, `void** ok: 1`, with no reports from ASan or UBSan. `widget_recreate` frees the old object itself, and `inout_ptr` does not make the `unique_ptr` free it again.

## How out_ptr_t works [out.ptr.t]

`std::out_ptr(s, args...)` returns an `out_ptr_t<Smart, Pointer, Args...>` temporary. It has three exposition-only members: a reference `s` to the target smart pointer, a `tuple<Args...> a` holding the extra arguments (usually a deleter), and a raw pointer `p`. The C function gets `&p` through a conversion function and writes the result into `p`. The temporary is destroyed at the end of the full-expression ([[class.temporary]]), and its destructor then hands `p` to `s`.

### Construction: the target is cleared first (¶6–¶7)

¶6 The constructor stores the reference and the arguments, value-initializes `p`, then clears the target: it calls `s.reset()` if that is well-formed, otherwise does `s = Smart()` if `Smart` is default constructible, and is ill-formed if neither works.

So the resource the smart pointer held is released before the C function is called. For a pure output parameter this is right, since the old value would be overwritten anyway. If the C function needs to read the old value, use `inout_ptr`.

¶7 Note 2 explains that the constructor is deliberately not `noexcept`: an implementation may preallocate the control block for `shared_ptr` during construction, so that the destructor does not need to allocate and therefore cannot throw.

### Destruction: handing back the result (¶8–¶9)

¶8 Let `SP` be *POINTER_OF_OR*(Smart, Pointer), i.e. the smart pointer's own `pointer` type ([[memory]]). ¶9 If `p` is non-null, it calls `s.reset(static_cast<SP>(p), args...)` with the stored arguments expanded; if that expression is not well-formed, it uses `s = Smart(static_cast<SP>(p), args...)` instead; if neither works, the program is ill-formed. When `p` is null (the C function failed and did not write), nothing is done and `s` stays in the cleared state from construction.

### Conversion functions (¶10–¶17)

`operator Pointer*()` returns the address of `p`. `operator void**()` is for APIs whose parameter is `void**`: ¶12 requires `Pointer` not to be `void*`, and ¶13 requires `Pointer` to be a pointer type; ¶15 it returns some `void**` value `v` such that the initial value of `*v` equals `static_cast<void*>(p)`, and any modification of `*v` is reflected in `p` at destruction. ¶16 Accessing `*v` outside the lifetime of the temporary is UB.

The standard does not directly specify that `operator void**()` returns `reinterpret_cast<void**>(&p)`. Reinterpreting an `int**` as `void**` and writing through it accesses an `int*` object with type `void*`, violating the type aliasing rules ([[basic.lval]]); on platforms where `T*` and `void*` have different representations it is simply wrong. So an implementation may store a separate `void*` in the object and convert it back at destruction. ¶17 Note 3 points out that `reinterpret_cast` is a viable strategy for some implementations.

¶5 Evaluating both conversion functions on the same object may conflict ([[intro.races]]). The preconditions in ¶10 and ¶14 go further: once one of them has been called, the other may not be. The practical meaning is that the same temporary can be converted only once.

### shared_ptr requires a deleter (¶3)

```cpp title="out-ptr-shared.cpp" error
#include <memory>
struct widget;
extern "C" int widget_create(widget** out, int id);
void f() {
    std::shared_ptr<widget> s;
    widget_create(std::out_ptr(s), 1);   // error: no deleter
}
```

¶3 specifies that if `Smart` is a specialization of `shared_ptr` and there are no extra arguments, the program is ill-formed. Note 1 explains why: `shared_ptr::reset(p)` would switch to `delete` as the deleter, and resources obtained from a C API should almost never be released with `delete`, so omitting the deleter is most likely a mistake. libc++ (with Clang 23) rejects it with a `static_assert` whose message is `Using std::shared_ptr<> without a deleter in std::out_ptr is not supported.`

¶3 also requires `Pointer` to meet *Cpp17NullablePointer*. ¶4 allows programs to specialize `out_ptr_t` for specializations that depend on program-defined types without meeting the primary template's requirements, so that custom smart pointers such as COM's `CComPtr` can be adapted.

## out_ptr [out.ptr]

```cpp
template<class Pointer = void, class Smart, class... Args>
  constexpr auto out_ptr(Smart& s, Args&&... args);
```

¶1 If a non-`void` `Pointer` is given explicitly, that is the pointer type the C function sees; otherwise it is the smart pointer's `pointer` type. Giving it explicitly is useful when the C function's parameter type differs from the smart pointer's; the standard's example is `std::out_ptr<std::FILE*>(file_ptr)`. ¶2 Returns `out_ptr_t<Smart, P, Args&&...>(s, std::forward<Args>(args)...)`. What is stored is `Args&&`, i.e. references, so passing a temporary deleter is fine: it lives until the end of the full-expression, just like the `out_ptr_t`.

## inout_ptr [inout.ptr.t] [inout.ptr]

¶1 `inout_ptr_t` is for C functions that first read and possibly release the old value, then write a new one. In the standard's example, `star_fish_populate(std::inout_ptr(peach), ...)` makes the C function responsible for disposing of `peach`'s original object.

¶6 At construction `p` is initialized to `smart.get()`, or to `smart` when `Smart` is itself a raw pointer type, so the C function sees the old value. ¶7 An implementation may call `s.release()` already in the constructor.

¶10–¶11 At destruction, if the constructor did not `release()`, it first does `s.release()`, giving up ownership of the old value because the C function has taken responsibility for disposing of it; then, if `p` is non-null, it does `s.reset(static_cast<SP>(p), args...)` just like `out_ptr_t`. `release()` is used here rather than `reset()` because the old resource has already been released or reused by the C function, and the smart pointer must not delete it again. If the C function sets the pointer to null, `release()` is still done and no `reset` follows, so `s` ends up empty.

¶11.1 When `Smart` is a raw pointer, it unconditionally assigns `s = Smart(static_cast<SP>(p), ...)`, without `if (p)`. The wording before [[LWG3897]] had that test, so after the C function set the pointer to null, the user's raw pointer would keep the already-freed old value. libc++ (with Clang 23) already implements the new wording: after the C function frees and nulls it, the original raw pointer becomes a null pointer.

¶3 specifies that the program is ill-formed if `Smart` is a specialization of `shared_ptr`, with or without a deleter. Note 1 explains that under the shared ownership model there is no way to correctly take exclusive ownership of the resource: `shared_ptr` has no `release()`, and after the C function releases the old resource, other copies of the `shared_ptr` would dangle.

The conversion functions of `inout_ptr_t` (¶12–¶19) are the same as those of `out_ptr_t`.

## Common misconceptions

!!! pitfall "The smart pointer is already updated within the same full-expression"
    ```cpp run title="same-expr.cpp" ok
    #include <memory>
    #include <cstdio>
    #include <cstdlib>
    struct widget { int id; };
    extern "C" int widget_create(widget** out, int id) {
      *out = static_cast<widget*>(std::malloc(sizeof(widget)));
      (*out)->id = id;
      return 0;
    }
    struct free_deleter {
      void operator()(void* p) const noexcept { std::free(p); }
    };
    int main() {
      std::unique_ptr<widget, free_deleter> w;
      bool ok = widget_create(std::out_ptr(w), 7) == 0
                && w != nullptr;                 // w has not been updated yet
      std::printf("%d %d\n", ok, w != nullptr);  // 0 1
    }
    ```
    The result is written back only when the temporary is destroyed, i.e. at the end of the full-expression. Reading `w` within the same expression sees the null pointer left by the constructor. Code like `if (create(std::out_ptr(p)) == 0 && p->ready())` dereferences a null pointer. Split the call and the use into two statements.

## Summary

| | `out_ptr` | `inout_ptr` |
|---|---|---|
| At construction | Clears the target | `p` takes the old value |
| C function | Writes the new value | Disposes of the old value, writes the new value |
| At destruction | `reset(p)` if `p` is non-null | `release()` the old value, `reset(p)` if `p` is non-null |
| `shared_ptr` | Requires a deleter | Ill-formed |
