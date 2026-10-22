---
title: The asm declaration
summary: "An asm declaration hands its contents to the implementation, usually to embed assembly; it is conditionally-supported, what goes in the parentheses and what it means are implementation-defined, and evaluating one during constant evaluation makes the expression not a constant expression."
updated: 2026-10-19
---

!!! tldr
    - `asm( ... );` is conditionally-supported: an implementation may not support it, but if it doesn't, it must issue a diagnostic.
    - What may be written in the parentheses, and what it means, is entirely implementation-defined. GCC's and Clang's extended assembly syntax is such an implementation-defined meaning.
    - It is a block declaration and can appear at namespace scope or in a function body.
    - Since C++20 a constexpr function can contain an asm declaration, as long as constant evaluation doesn't reach it.

## The rule (¶1)

```cpp title="asm-basic.cpp" impl
asm(".globl my_marker_sym");      // namespace scope: GCC/Clang emit it verbatim into the assembly file

int f(int x) {
    asm("nop");                    // block scope: a declaration statement
    return x;
}

int main() { return f(0); }
```

¶1 An asm declaration has the form:

```text
asm-declaration:
    attribute-specifier-seq(opt) asm ( balanced-token-seq ) ;
```

A *balanced-token-seq* is any token sequence with balanced brackets ([[dcl.attr.grammar]]). The standard says only one thing about it:

!!! std
    The `asm` declaration is conditionally-supported; any restrictions on the *balanced-token-seq* and its meaning are implementation-defined.

A [[g:conditionally-supported|conditionally-supported]] construct may be unsupported by an implementation, but then the implementation must diagnose programs that use it ([[intro.compliance]]). Implementation-defined behavior must be documented by the implementation {{impl}}. So the standard says nothing at all about how an asm declaration relates to the assembler, registers or the memory model. Note 1 only says it is typically used to pass information through the implementation to an assembler.

The optional leading attributes appertain to the asm declaration. Clang 23 doesn't accept attributes in this position; `[[maybe_unused]] asm("nop");` is an error.

An *asm-declaration* is a kind of block declaration ([[dcl.pre]]), so it can appear at namespace scope (often called top-level assembly) or as a declaration statement in a function body.

## What goes in the parentheses

Through C++23 the parentheses could only contain a string literal; C++26's unevaluated strings proposal ([[P2361R6]]) first changed it to an unevaluated string, and the current draft relaxed it further to a balanced token sequence. This way, the extended assembly syntax widely used by GCC and Clang becomes implementation-defined restrictions and meaning rather than a syntactic extension:

```cpp title="asm-extended.cpp" impl
int add_one(int x) {
    int r;
#if defined(__x86_64__)
    asm("leal 1(%1), %0" : "=r"(r) : "r"(x));     // output operands : input operands
#elif defined(__aarch64__)
    asm("add %w0, %w1, #1" : "=r"(r) : "r"(x));
#else
    r = x + 1;
#endif
    return r;
}

void barrier() {
    asm volatile("" ::: "memory");                // compiler barrier
}

int main() { barrier(); return add_one(41) - 42; }
```

The qualifiers `volatile`, `goto` and `inline`, and the output, input and clobber lists separated by `:`, are all GNU conventions. The instructions in the string are mostly opaque to the C++ compiler: GCC only substitutes operands and doesn't parse the instructions; Clang's integrated assembler checks their syntax at compile time.

## asm in constant evaluation

Per [[expr.const.core#2]], evaluating an asm declaration makes an expression not a core constant expression. The key word is evaluating: since C++20 ([[P1668R1]]), a constexpr function can contain an asm declaration as long as constant evaluation doesn't reach it.

```cpp title="asm-constexpr.cpp" error
constexpr int g(int x) {
    if consteval { return x; }
    else { asm("nop"); return x; }     // never reached during constant evaluation
}
static_assert(g(3) == 3);              // OK

constexpr int h(bool b) {
    if (b) asm("nop");
    return 1;
}
static_assert(h(false) == 1);          // OK: the asm isn't evaluated
static_assert(h(true) == 1);           // error: evaluates an asm declaration, not a constant expression
```

Before C++20, an asm declaration couldn't appear in a constexpr function body at all, whether reached or not. Back then a function couldn't be both usable at compile time and use hardware instructions at run time. Now the two paths can be separated with `if consteval` (C++23) or `std::is_constant_evaluated()`.

## Implementation notes

!!! impl "Compilers"
    - GCC and Clang support basic assembly `asm("...")` and extended assembly `asm("..." : outputs : inputs : clobbers)`. The keyword can also be spelled `__asm__`, which works in non-GNU modes like `-std=c++XX` too. Only basic assembly is allowed at namespace scope.
    - MSVC doesn't support the standard `asm` keyword. It has its own `__asm { ... }` block syntax, and only for 32-bit x86; on x64 and ARM64 there is no inline assembly, only compiler intrinsics or separate assembly files. Conditional support exists for exactly this kind of situation.
    - Inline assembly is a black box to the optimizer, which can only infer its effects from the operand constraints and clobber list. `asm volatile("" ::: "memory")` generates no instructions but tells the compiler that memory may have been modified, so the compiler won't reorder memory accesses across it. It is a compiler barrier and doesn't constrain the CPU.

## Common misconceptions

!!! pitfall "A compiler barrier can be used for thread synchronization"
    `asm volatile("" ::: "memory")` only constrains the compiler; the CPU can still reorder memory accesses. Synchronization between threads needs `std::atomic` and `std::atomic_thread_fence` ([[intro.races]]).

!!! pitfall "asm that compiles is portable"
    Even if the syntax is accepted, the meaning is entirely implementation-defined, and with another compiler or target architecture it may mean something different or not compile at all. When you need hardware features, prefer the standard library (`<bit>`, `<atomic>`) or compiler intrinsics.

## Questions

!!! question "Question"
    An implementation doesn't support asm declarations. What must it do with the following program?

    ```cpp
    constexpr int f() { if consteval { return 1; } else { asm("nop"); return 0; } }
    int main() { return f(); }
    ```

<details markdown="1">
<summary>Answer</summary>

It must issue a diagnostic, after which it may refuse to compile. An asm declaration is a conditionally-supported construct, and an implementation that doesn't support it must diagnose programs that use it ([[intro.compliance]]), regardless of whether the code would be executed. Whether it is evaluated only matters for the rules of constant evaluation ([[expr.const.core#2]]), not for whether it is supported.
</details>
