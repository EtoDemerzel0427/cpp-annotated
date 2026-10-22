---
title: Reading compiler-generated assembly
summary: "The minimum assembly knowledge needed to check what the compiler turned your C++ into: how to get the assembly, the AArch64 and x86-64 calling conventions, what common C++ constructs look like once compiled, and how to spot redundant calls, register spills and unvectorized loops in the assembly."
tags: performance, assembly, AArch64, x86-64, calling convention, code generation
updated: 2026-10-19
group: Measurement
---

!!! tldr
    - `clang++ -O2 -S x.cpp -o -` prints assembly, and `--target=x86_64-linux-gnu` switches to x86-64; object files are disassembled with `llvm-objdump -d -C`, and mangled symbol names are demangled with `llvm-cxxfilt`.
    - Arguments and return values live in registers: AArch64 passes arguments in x0–x7 and returns in x0; x86-64 System V passes in rdi, rsi, rdx, rcx, r8, r9 and returns in rax. Values that must survive a call go in callee-saved registers, which the function's prologue and epilogue save and restore.
    - A reference compiles to a pointer; small trivially copyable structs are split into registers, while classes with a user-provided copy constructor are passed by address; a virtual call is two loads plus an indirect jump; a dense `switch` may become a jump table.
    - Exceptions add no instructions to the normal path; cleanup code goes into landing pads at the end of the function. libc++ hardening adds one comparison and one branch to `operator[]`, which costs almost nothing when it can be hoisted out of the loop; when it can't, we measured about 7% slower.
    - When reading assembly, look mainly for three things: unexpected `bl`/`call` (`memcpy`, `operator new`), stack loads and stores marked Spill/Reload, and loop bodies that should be vector instructions but are still scalar.

## Getting the assembly

Start with a minimal function:

```cpp godbolt title="square.cpp" flags="-std=c++2c -O2" ok
int square(int x) { return x * x; }
```

Two commands on our test machine (Apple M2 Pro, Homebrew Clang 23.1.3): the first generates native AArch64 assembly, the second cross-compiles to x86-64 Linux, generating assembly only, with no linking needed:

```bash
clang++ -std=c++2c -O2 -S square.cpp -o -
clang++ -std=c++2c -O2 -S --target=x86_64-linux-gnu square.cpp -o -
```

After removing the assembler directives that start with a dot, what remains is:

<div class="compare" markdown="1">

```asm title="AArch64"
__Z6squarei:            ; @_Z6squarei
; %bb.0:
  mul   w0, w0, w0
  ret
```

```asm title="x86-64 (AT&T syntax)"
_Z6squarei:             # @_Z6squarei
# %bb.0:
  movl  %edi, %eax
  imull %edi, %eax
  retq
```

</div>

Line by line:

- `__Z6squarei:` is a **label**, the symbol name of the function's entry. `_Z6squarei` is the mangled name of `square(int)` (rules in [[toolchain/name-mangling]]); macOS's Mach-O format prefixes every C symbol with another underscore.
- `; %bb.0:` is a comment marking LLVM's internal **basic block** 0, a stretch of straight-line code entered only at the top and left only at the bottom. AArch64 assembly comments start with `;` (AArch64 assembly on Linux uses `//`), x86-64 comments with `#`.
- AArch64's `w0` is the low 32 bits of the 64-bit register `x0`; `int` is 32 bits, so `w` is used. The argument comes in in `w0` and the result goes back in `w0`.
- On x86-64 the argument comes in in `edi` and the result goes in `eax`. AT&T syntax puts the destination operand last, prefixes registers with `%`, and uses instruction suffixes `l` for 32 bits and `q` for 64 bits. `-masm=intel` switches to Intel syntax: destination first, no `%` and no suffix (`mov eax, edi`, `imul eax, edi`).

The removed lines are all for the assembler and linker: `.cfi_*` describes stack frames for exception unwinding and debuggers (see [[toolchain/exception-implementation]]); `.p2align` is alignment; `.globl` declares externally visible symbols. You can skip them when reading code.

<details class="fine" markdown="1"><summary>Other ways to get assembly</summary>

- Compiler Explorer. Code blocks on this site with a `godbolt ↗` button open in Compiler Explorer with one click, using Clang trunk and GCC trunk on x86-64 by default; the buttons here all include `-O2`. By default it hides assembler directives and color-codes source lines against assembly lines; you can also add an ARM64 compiler from the compiler list for comparison.
- Disassembling object files. After `clang++ -O2 -g -c f.cpp`, `llvm-objdump -d -C --no-show-raw-insn f.o` disassembles; `-C` also demangles, `-S` interleaves source lines before the corresponding instructions (needs `-g`), and `-r` shows relocations, that is, which symbol a `bl`/`call` is looking for while its target is not yet filled in. The `objdump` that ships with macOS is Apple's LLVM version, used the same way. When disassembling Mach-O object files on our test machine, the first function is often labeled `<ltmp0>` instead of its name; disassemble after linking into an executable, or just use the `-S` output.
- `-fverbose-asm`. With Clang 23 on our test machine, the output is exactly the same with or without this option, because Clang's `-S` output already includes comments like `; @_Z6squarei` and `; %bb.0` by default; only `-fno-verbose-asm` removes them. GCC's option of the same name adds more comments, which you can compare in Compiler Explorer.
- Demangling. `llvm-cxxfilt` and `c++filt` read symbol names from standard input, and both handle the extra leading underscore of Mach-O:

```text
$ echo __Z6squarei | llvm-cxxfilt
square(int)
$ nm f.o | llvm-cxxfilt
```

</details>

The AArch64 assembly below is from macOS on our test machine, and the x86-64 assembly from `--target=x86_64-linux-gnu`. For examples using standard library headers, our test machine has no Linux headers and libraries, so `--target=x86_64-apple-macos` is used instead; both use the same x86-64 System V calling convention, differing only in the leading underscore of symbol names and the default frame pointer setting. For layout, tabs in the listings have been replaced with spaces, and assembler directives and some comments removed; the instructions themselves are unchanged.

## The skeleton of a function

Parameter names are invisible in assembly; only registers are visible. Which register holds which argument and the return value, and which registers must be preserved across a call, is specified by the **calling convention**. It is part of the platform ABI, not of the C++ standard; the standard only requires the program's observable behavior to match the abstract machine ([[intro.abstract#1]]), and register allocation is entirely up to the implementation.

```cpp godbolt title="call.cpp" flags="-std=c++2c -O2" ok
long g(long);                 // defined in another TU

long f(long a, long b) {
  long t = g(a);              // a is passed to g
  return t + b;               // b must survive this call
}
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z1fll:
  stp  x20, x19, [sp, #-32]!
  stp  x29, x30, [sp, #16]
  add  x29, sp, #16
  mov  x19, x1        ; save b in x19
  bl   __Z1gl         ; a is already in x0
  add  x0, x0, x19    ; g's result + b
  ldp  x29, x30, [sp, #16]
  ldp  x20, x19, [sp], #32
  ret
```

```asm title="x86-64"
_Z1fll:
  pushq %rbx
  movq  %rsi, %rbx    # save b in rbx
  callq _Z1gl@PLT     # a is already in rdi
  addq  %rbx, %rax    # g's result + b
  popq  %rbx
  retq
```

</div>

`a` is already in the first argument register, so nothing has to move to call `g`. `b` is in the second argument register, but `g` is free to overwrite argument registers, so `f` first moves `b` into a register `g` promises not to change: `x19` on AArch64, `rbx` on x86-64.

Such registers are called **callee-saved**: whichever function wants to use one must first save the old value and restore it before returning. Conversely, **caller-saved** registers may be changed by a call, so the caller either keeps no value that must be preserved in them or saves it first. That is why `f` saves `x19` before using it; this is the **prologue** at the start of the function. Restoring it before returning is the **epilogue**.

AArch64's `bl` writes the return address to `x30` (the link register, lr) instead of pushing it, so a function that calls other functions must save `x30`. `x29` is the frame pointer, and `stp x29, x30, [sp, #16]` plus `add x29, sp, #16` is the fixed pattern every non-leaf function has on Apple platforms. `x20` is saved along with it only because `stp` stores two registers at a time and the stack must stay 16-byte aligned.

x86-64's `call` pushes the return address. `pushq %rbx` both saves `rbx` and brings the stack pointer back to 16-byte alignment for the next `call`. `--target=x86_64-linux-gnu -O2` does not keep the frame pointer by default, so there is no `push rbp; mov rbp, rsp`.

| | AArch64 (AAPCS64, Apple platforms) | x86-64 System V (Linux, macOS) |
|---|---|---|
| Integer and pointer arguments | x0–x7 | rdi, rsi, rdx, rcx, r8, r9 |
| Floating-point arguments | d0–d7 (s0–s7 for `float`) | xmm0–xmm7 |
| Integer return value | x0; x0 and x1 for 16 bytes | rax; rax and rdx for 16 bytes |
| Floating-point return value | d0 / s0 | xmm0 |
| Large object return | Caller passes the result address in x8 | Caller passes the address in rdi; the function returns it in rax |
| Return address | x30 (lr) | Top of stack |
| Callee-saved | x19–x28, x29 (frame pointer), sp; d8–d15 | rbx, rbp, r12–r15, rsp |
| Caller-saved | x0–x17 (x18 is reserved by the platform, don't use it); v0–v7, v16–v31, and the upper 64 bits of v8–v15 | rax, rcx, rdx, rsi, rdi, r8–r11; all xmm |
| Stack alignment at calls | 16 bytes | 16 bytes |

<details class="fine" markdown="1"><summary>Examples verifying the return-value conventions</summary>

```cpp godbolt title="ret.cpp" flags="-std=c++2c -O2" ok
struct P { long x, y; };
struct B { long a, b, c; };
P make_p(long v) { return {v, v + 1}; }
B make_b(long v) { return {v, v, v}; }
double half(double d, int) { return d / 2; }
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z6make_pl:
  add   x1, x0, #1     ; x0 unchanged
  ret
__Z6make_bl:
  stp   x0, x0, [x8]   ; write to where x8 points
  str   x0, [x8, #16]
  ret
__Z4halfdi:
  fmov  d1, #0.50000000
  fmul  d0, d0, d1
  ret
```

```asm title="x86-64"
_Z6make_pl:
  movq  %rdi, %rax
  leaq  1(%rdi), %rdx
  retq
_Z6make_bl:
  movq  %rdi, %rax     # return the address
  movq  %rsi, (%rdi)   # v is in rsi
  movq  %rsi, 8(%rdi)
  movq  %rsi, 16(%rdi)
  retq
_Z4halfdi:
  mulsd .LCPI2_0(%rip), %xmm0
  retq
```

</div>

`make_b` returns a 24-byte object; x86-64 passes the result address in rdi, so `v` moved to rsi. `d / 2` was replaced by multiplication by 0.5, because 0.5 is exactly representable and the two give the same result for all inputs; this is a transformation the as-if rule permits.

</details>

Assembly at `-O0` is almost useless for judging performance: every local variable lives on the stack and is reloaded from the stack on every use. Everything below discusses `-O2` output.

## What C++ constructs look like compiled

### A reference is a pointer

```cpp godbolt title="ref.cpp" flags="-std=c++2c -O2" ok
void by_ref(int& r) { r += 1; }
void by_ptr(int* p) { *p += 1; }
```

The assembly for the two functions is identical: on AArch64 `ldr w8, [x0]`, `add w8, w8, #1`, `str w8, [x0]`; on x86-64 a single `incl (%rdi)`. A reference parameter is just an address in the ABI. The standard says it is unspecified whether a reference requires storage ([[dcl.ref#4]]), which gives the compiler freedom to optimize local references away entirely; but when passed across a function boundary it has to be passed in some form, and mainstream ABIs choose a pointer.

### Small structs: registers or memory

```cpp godbolt title="structs.cpp" flags="-std=c++2c -O2" ok
struct P {                    // trivially copyable
  long x, y;
};
struct Q {                    // user-provided copy constructor
  long x, y;
  Q(const Q& o) : x(o.x), y(o.y) {}
};
long sum_p(P p) { return p.x + p.y; }
long sum_q(Q q) { return q.x + q.y; }
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z5sum_p1P:
  add   x0, x0, x1      ; both members in registers
  ret
__Z5sum_q1Q:
  ldp   x8, x9, [x0]    ; x0 is an address
  add   x0, x9, x8
  ret
```

```asm title="x86-64"
_Z5sum_p1P:
  leaq  (%rdi,%rsi), %rax
  retq
_Z5sum_q1Q:
  movq  8(%rdi), %rax   # rdi is an address
  addq  (%rdi), %rax
  retq
```

</div>

`P` and `Q` have exactly the same layout but are passed differently. `P`'s two members go straight into two argument registers; for `Q`, the caller copies an object onto its own stack and passes its address. The caller side makes this clearer:

```cpp godbolt title="caller.cpp" flags="-std=c++2c -O2" ok
struct Q {
  long x, y;
  Q(const Q& o) : x(o.x), y(o.y) {}
};
long sum_q(Q q);
long call_q(const Q& q) { return sum_q(q); }
```

```asm title="AArch64"
__Z6call_qRK1Q:
  sub   sp, sp, #32
  stp   x29, x30, [sp, #16]
  add   x29, sp, #16
  ldr   q0, [x0]          ; read 16 bytes
  str   q0, [sp]          ; copy the parameter object onto the stack
  mov   x0, sp            ; pass its address
  bl    __Z5sum_q1Q
  ldp   x29, x30, [sp, #16]
  add   sp, sp, #32
  ret
```

The reason is in the standard. When passing by value, the parameter object is initialized from the argument and has its own address, which a copy constructor could record. Only when all of the type's copy and move constructors are trivial and the destructor is trivial or deleted does [[class.temporary#3]] allow implementations to create extra temporaries to pass parameters or return values, that is, to split the object into registers and reassemble it in the callee. `Q` has a user-provided copy constructor and does not meet this condition, so the object must stay in memory and be passed by address.

!!! std
    if X is ... a class type that has at least one eligible copy or move constructor, where each such constructor is trivial, and the destructor of X is either trivial or deleted, implementations are permitted to create temporary objects to hold the function parameter or result object
    
    When types meeting these conditions (and scalar types) are passed by value, the implementation may route them through temporary objects. ABIs use exactly this rule to put small objects in registers ([[class.temporary#3]]).

This condition is close to, but not the same as, being a [[g:trivially-copyable-class]]: trivially copyable also requires trivial copy and move assignment operators, while [[class.temporary#3]] ignores assignment operators.

Meeting the condition does not guarantee registers either; size matters too. `B` below is trivially copyable but 24 bytes:

```cpp godbolt title="big.cpp" flags="-std=c++2c -O2" ok
struct B { long a, b, c; };   // 24 bytes, trivially copyable
long sum_b(B b) { return b.a + b.b + b.c; }
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z5sum_b1B:
  ldp   x8, x9, [x0]   ; caller copies, passes the address
  ldr   x10, [x0, #16]
  add   x8, x9, x8
  add   x0, x8, x10
  ret
```

```asm title="x86-64"
_Z5sum_b1B:
  movq  16(%rsp), %rax  # copied into the argument area on the stack
  addq  8(%rsp), %rax
  addq  24(%rsp), %rax
  retq
```

</div>

For structs larger than 16 bytes, AArch64 has the caller make a copy and pass its address; x86-64 copies the whole object into the argument area on the stack, and the callee reads upward from `rsp` (`0(%rsp)` is the return address). Broadly, both ABIs split only classes of at most 16 bytes that meet the triviality conditions above into registers. AArch64 has one exception: structs with at most 4 members, all of the same floating-point type, are passed in d0–d3; on our test machine the 32-byte `struct V4 { double a, b, c, d; }` is passed entirely in d0–d3, while x86-64 still reads it from the stack.

### Virtual calls

```cpp godbolt title="virt.cpp" flags="-std=c++2c -O2" ok
struct Shape {
  virtual ~Shape() = default;
  virtual double area() const = 0;
};
double area_of(const Shape& s) {
  return s.area();
}
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z7area_ofRK5Shape:
  ldr   x8, [x0]       ; load the vptr
  ldr   x1, [x8, #16]  ; load the 3rd slot
  br    x1             ; jump there
```

```asm title="x86-64"
_Z7area_ofRK5Shape:
  movq  (%rdi), %rax   # load the vptr
  jmpq  *16(%rax)      # TAILCALL
```

</div>

The object starts with the vptr, which the first load reads; the first two slots of the vtable are the two variants of the virtual destructor (complete-object destructor and deleting destructor), and `area` is in the third slot at offset 16; the second load reads the function address, and finally an indirect jump. The full vtable structure is in [[toolchain/object-layout-and-vtables]].

Here `br`/`jmp` is used instead of `blr`/`call`: calling `area` is the last thing `area_of` does, and the return value is passed through unchanged, so the compiler jumps directly and lets `area` return to `area_of`'s caller. This is called a **tail call**.

If the compiler can determine the dynamic type, no table lookup is needed. Change the parameter to a reference to a `final` class:

```cpp godbolt title="final.cpp" flags="-std=c++2c -O2" ok
struct Shape {
  virtual ~Shape() = default;
  virtual double area() const = 0;
};
struct Square final : Shape {
  double side;
  double area() const override { return side * side; }
};
double area_of(const Square& s) {
  return s.area();
}
```

The AArch64 output becomes `ldr d0, [x0, #8]`, `fmul d0, d0, d0`, `ret`: it reads `side` directly (after the vptr, at offset 8), and the call has been inlined. x86-64 likewise gives `movsd 8(%rdi), %xmm0` plus `mulsd`. This optimization, turning a virtual call into a direct call, is called devirtualization; when it is possible is covered in [[perf/compiler-optimizations]].

### Inlined and not inlined

```cpp godbolt title="inl.cpp" flags="-std=c++2c -O2" ok
static int twice(int x) { return 2 * x; }
int opaque(int x);            // defined in another TU

int a(int x) { return twice(x) + 1; }
int b(int x) { return opaque(x) + 1; }
```

<div class="compare" markdown="1">

```asm title="AArch64"
__Z1ai:
  mov   w8, #1
  orr   w0, w8, w0, lsl #1
  ret
__Z1bi:
  stp   x29, x30, [sp, #-16]!
  mov   x29, sp
  bl    __Z6opaquei
  add   w0, w0, #1
  ldp   x29, x30, [sp], #16
  ret
```

```asm title="x86-64"
_Z1ai:
  leal  1(,%rdi,2), %eax
  retq
_Z1bi:
  pushq %rax           # only to align the stack
  callq _Z6opaquei@PLT
  incl  %eax
  popq  %rcx
  retq
```

</div>

Once `twice` is inlined into `a`, `2 * x + 1` is just one or two instructions: AArch64 shifts `x` left by one and ORs in 1, x86-64 computes `x*2 + 1` with a single `lea`. `twice` itself does not appear in the output, because it is `static` and every call has been inlined, so there is no need to emit it. `opaque`, called by `b`, is in another translation unit; the compiler cannot see its body, so it must dutifully `bl`, paying for a prologue and epilogue as a result.

To tell whether something was inlined, check whether the assembly still has a `bl`/`call` to that function. Inlining across translation units requires LTO; see [[perf/lto-pgo]].

### Loops and their vectorized form

```cpp godbolt title="sum.cpp" flags="-std=c++2c -O2" ok
int sum(const int* p, long n) {
  int s = 0;
  for (long i = 0; i < n; ++i)
    s += p[i];
  return s;
}
```

First turn off vectorization and unrolling with `-fno-vectorize -fno-unroll-loops` to see what the loop looks like by itself:

<div class="compare" markdown="1">

```asm title="AArch64"
  cmp   x1, #1
  b.lt  LBB0_4         ; n < 1: return 0 directly
  mov   w8, #0
LBB0_2:                ; loop header
  ldr   w9, [x0], #4   ; load *p, p += 4
  add   w8, w9, w8
  subs  x1, x1, #1     ; --n, set flags
  b.ne  LBB0_2         ; continue while n != 0
```

```asm title="x86-64"
  xorl  %eax, %eax
  testq %rsi, %rsi
  jle   .LBB0_3        # skip if n <= 0
  xorl  %ecx, %ecx
.LBB0_2:               # loop header
  addl  (%rdi,%rcx,4), %eax
  incq  %rcx
  cmpq  %rcx, %rsi
  jne   .LBB0_2
```

</div>

The way to recognize a loop is to find a conditional branch that jumps backward: `b.ne LBB0_2` jumps back to the label above it. Clang also adds the comment `=>This Inner Loop Header: Depth=1` after the loop header label.

AArch64's `[x0], #4` is post-indexed addressing: load from `x0`, then add 4 to `x0`. x86-64's `(%rdi,%rcx,4)` means the address `rdi + rcx*4`, used directly as `addl`'s memory operand.

The default `-O2` vectorizes this loop. The main loop becomes:

```asm title="AArch64"
LBB0_7:
  ldp    q4, q5, [x8, #-32]
  ldp    q6, q7, [x8], #64
  add.4s v0, v4, v0
  add.4s v1, v5, v1
  add.4s v2, v6, v2
  add.4s v3, v7, v3
  subs   x11, x11, #16
  b.ne   LBB0_7
```

```asm title="x86-64"
.LBB0_6:
  movdqu (%rdi,%rax,4), %xmm2
  paddd  %xmm2, %xmm1
  movdqu 16(%rdi,%rax,4), %xmm2
  paddd  %xmm2, %xmm0
  addq   $8, %rax
  cmpq   %rax, %rcx
  jne    .LBB0_6
```

`q4` is a 128-bit vector register holding 4 `int`s; `add.4s` is a 4-lane 32-bit integer addition. Each iteration reads 16 `int`s and spreads them over 4 accumulators `v0`–`v3`, which are added together after the loop, with `addv.4s` summing a vector's 4 elements horizontally. `add.4s v0, v4, v0` is the Apple assembler's notation; AArch64 assembly on Linux writes `add v0.4s, v4.4s, v0.4s`, the same instruction.

x86-64 can only use SSE2 by default: `movdqu` loads 16 bytes and `paddd` does a 4-lane 32-bit addition, 8 `int`s per iteration. With `-march=x86-64-v3` allowing AVX2, we see `vpaddd` operating on 256-bit `ymm` registers.

The vectorized function is much longer than the original: before the main loop it checks whether `n` is big enough, and after it there is a loop for the remaining elements, so you see three loop headers in the same function. When reading, first find the loop using `q`/`v` registers (or `xmm`/`ymm`); that is the hot path. Conditions and costs of vectorization are in [[perf/vectorization]].

### switch and jump tables

```cpp godbolt title="dispatch.cpp" flags="-std=c++2c -O2" ok
void on_a(); void on_b(); void on_c();
void on_d(); void on_e();

void dispatch(int op) {
  switch (op) {
    case 0: on_a(); break;
    case 1: on_b(); break;
    case 2: on_c(); break;
    case 3: on_d(); break;
    case 4: on_e(); break;
  }
}
```

```asm title="x86-64"
_Z8dispatchi:
  cmpl    $4, %edi
  ja      .LBB0_7                  # unsigned > 4: not in the table
  movl    %edi, %eax
  leaq    .LJTI0_0(%rip), %rcx     # address of the table
  movslq  (%rcx,%rax,4), %rax      # fetch entry op
  addq    %rcx, %rax
  jmpq    *%rax                    # jump there
.LBB0_2:
  jmp     _Z4on_av@PLT             # TAILCALL
  ...
.LBB0_7:
  retq
.LJTI0_0:
  .long   .LBB0_2-.LJTI0_0
  .long   .LBB0_3-.LJTI0_0
  ...
```

A **jump table** is an array whose entry `i` holds the offset of `case i`'s code relative to the table. A single unsigned comparison first excludes both negative values and values above 4 (negative numbers are huge when viewed as unsigned); then the entry is fetched by index, added to the table address, and jumped to indirectly. However many cases there are, dispatch costs a fixed handful of instructions.

The same code on AArch64 on our test machine compiles into a comparison tree: `cmp w0, #1`, `b.le`, `cmp w0, #2`, `b.eq`… comparing one by one. With this version on our test machine, AArch64 needs 10 consecutive cases before it generates a jump table (entries are one byte, read with `ldrb`, shifted left by 2 and added to the base, then `br`), while x86-64 generates one from 4 cases on. These are each backend's heuristic thresholds, varying with compiler version and `-mcpu`; the standard places no requirement on how `switch` ([[stmt.switch]]) is implemented.

### Exceptions: no instructions on the normal path

```cpp godbolt title="eh.cpp" flags="-std=c++2c -O2" ok
struct Guard {
  ~Guard();                   // non-trivial destructor, defined elsewhere
};
void work();                  // may throw

int run() {
  Guard g;
  work();
  return 0;
}
```

```asm title="AArch64"
__Z3runv:
Lfunc_begin0:
  sub   sp, sp, #48
  stp   x20, x19, [sp, #16]
  stp   x29, x30, [sp, #32]
  add   x29, sp, #32
Ltmp0:                        ; EH_LABEL
  bl    __Z4workv
Ltmp1:                        ; EH_LABEL
  add   x0, sp, #15           ; normal path: destroy g
  bl    __ZN5GuardD1Ev
  mov   w0, #0
  ldp   x29, x30, [sp, #32]
  ldp   x20, x19, [sp, #16]
  add   sp, sp, #48
  ret
LBB0_2:                       ; landing pad
Ltmp2:                        ; EH_LABEL
  mov   x19, x0               ; save the exception object pointer
  add   x0, sp, #15
  bl    __ZN5GuardD1Ev        ; destroy g
  mov   x0, x19
  bl    __Unwind_Resume       ; continue propagating upward
GCC_except_table0:
  ...                         ; calls between Ltmp0..Ltmp1
  ...                         ; jump to Ltmp2 on an exception
```

On the normal path from `bl __Z4workv` to `ret` there are no checks or branches at all: after calling `work`, it destroys `g` and returns, just like the version compiled with `-fno-exceptions`. When an exception is thrown, the runtime library uses the table `GCC_except_table0` to find the **landing pad** `Ltmp2` for the call site of `work`, jumps there to destroy `g`, then calls `_Unwind_Resume` to continue unwinding. x86-64 has the same structure, with the landing pad keeping the exception object pointer in `rbx`.

The cost is not zero: the landing pad needs a callee-saved register (here `x19`), so the prologue saves an extra pair of registers; the `-fno-exceptions` version on our test machine saves only `x29` and `x30`. The landing pad and the table also take code size. The table format and the unwinding process are in [[toolchain/exception-implementation]].

### Bounds checks under hardening

The requirement on the index of `vector::operator[]` is a [[g:hardened-precondition]]: `n < a.size()` ([[sequence.reqmts#122]]). In a hardened implementation, violating it is a contract violation rather than UB ([[intro.compliance.general#8]]). Whether an implementation is hardened is implementation-defined; libc++ selects it with the macro `_LIBCPP_HARDENING_MODE`, and the default for Homebrew libc++ on our test machine is no hardening.

```cpp godbolt title="index.cpp" flags="-std=c++2c -O2" ok
#include <vector>
int at_index(const std::vector<int>& v, std::size_t i) {
  return v[i];
}
```

<div class="compare" markdown="1">

```asm title="AArch64, default"
  ldr   x8, [x0]       ; begin
  ldr   w0, [x8, x1, lsl #2]
  ret
```

```asm title="AArch64, FAST hardening"
  ldp   x8, x9, [x0]   ; begin, end
  sub   x9, x9, x8
  cmp   x1, x9, asr #2 ; i vs size()
  b.hs  LBB0_2         ; unsigned >=
  ldr   w0, [x8, x1, lsl #2]
  ret
LBB0_2:
  brk   #0x1           ; trap
```

</div>

The right side is compiled with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST`. The additions are one load, one subtraction, one comparison and a branch that is almost never taken; when the check fails, `brk` executes (`ud2` on x86-64), and the process is terminated by a signal. Running a program compiled this way with an out-of-range index on our test machine gives exit code 133, i.e. SIGTRAP.

`(end - begin) >> 2` computes the element count, and `b.hs` is unsigned greater-or-equal. A negative index converted to `size_t` is a huge number, so one unsigned comparison checks both the lower and upper bounds.

In loops, the check can often be hoisted out. With hardening, `for (i = 0; i < v.size(); ++i) s += v[i];` has no `brk` at all in the assembly, because the loop condition already guarantees the precondition. `for (i = 0; i < n; ++i) s += v[i];` compares `n - 1` with `size()` once before the loop starts and traps immediately on failure, and the loop body is vectorized as usual. Trapping early is allowed: the summation itself has no observable behavior, so terminating early is indistinguishable from outside from running until the first out-of-range index and then terminating ([[intro.abstract#1]]).

When the index comes from data, the check can't be hoisted. The benchmark below sums at random indices:

```cpp run title="hardening_bench.cpp" ok flags="-std=c++2c -O2"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <random>
#include <vector>

// keep the compiler from deleting the result as unused:
// the empty inline asm claims to read v, so the compiler has to actually compute v.
template <class T> void keep(T const& v) {
  asm volatile("" : : "r"(v) : "memory");
}

__attribute__((noinline))
long gather(const std::vector<int>& v,
            const std::vector<unsigned>& idx) {
  long s = 0;
  for (unsigned k : idx) s += v[k];   // checks k < size() every time
  return s;
}

__attribute__((noinline))
long linear(const std::vector<int>& v) {
  long s = 0;
  for (std::size_t i = 0; i < v.size(); ++i) s += v[i];
  return s;
}

template <class F> double median_ns(F f, std::size_t n) {
  std::vector<double> t;
  for (int r = 0; r < 4; ++r) keep(f());      // warm-up
  for (int r = 0; r < 31; ++r) {
    auto t0 = std::chrono::steady_clock::now();
    keep(f());
    auto t1 = std::chrono::steady_clock::now();
    t.push_back(std::chrono::duration<double, std::nano>(t1 - t0).count() / n);
  }
  std::ranges::sort(t);
  return t[t.size() / 2];
}

int main() {
  const std::size_t n = 1 << 16;            // 256 KiB of int, fits in L2
  std::vector<int> v(n, 1);
  std::vector<unsigned> idx(n);
  std::mt19937 rng(42);
  for (auto& k : idx) k = rng() % n;
  std::printf("gather: %.3f ns/elem\n",
              median_ns([&] { return gather(v, idx); }, n));
  std::printf("linear: %.3f ns/elem\n",
              median_ns([&] { return linear(v); }, n));
}
```

The timing harness is simple: time with `steady_clock`, do 4 dry runs to warm up the cache, then measure 31 times and take the median. The empty `asm volatile` in `keep` tells the compiler it reads the result, so the summation is not deleted for lack of use. The meaning of an `asm` declaration is implementation-defined ([[dcl.asm#1]]); this is the GCC/Clang extension syntax. Measurement methods themselves are in [[perf/measuring]].

Compiled on our test machine with `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_NONE` and with `..._FAST`, plus `-std=c++2c -O2`, run alternately 5 times:

| | No hardening | FAST hardening |
|---|---|---|
| `gather` (random indices) | 0.387–0.388 ns/element | 0.415–0.419 ns/element |
| `linear` (sequential indices) | 0.046 ns/element | 0.046 ns/element |

`gather` is about 7% slower. The assembly gives the reason: without hardening the loop is unrolled 4 ways with 4 accumulators; with hardening every element needs a `cmp` plus `b.ls`, and the loop is no longer unrolled. `linear`'s check is eliminated entirely; the two modes produce the same assembly for the hot loop and the same time. This is an observation on the M2 Pro of our test machine; other hardware, compilers or data sizes may differ.

## Finding problems in the assembly

### Unexpected calls

First list all the calls in a function:

```bash
clang++ -std=c++2c -O2 -S copy.cpp -o - | grep -E '\b(bl|call)'
```

```cpp godbolt title="copy.cpp" flags="-std=c++2c -O2" ok
#include <vector>
long count(std::vector<int> v);   // takes by value

long caller(const std::vector<int>& v) {
  return count(v);                 // makes a copy
}
```

The AArch64 output on our test machine shows, in order, `bl __Znwm` (`operator new(unsigned long)`), `bl _memcpy`, `bl __Z5countNSt3__16vector...` and `bl __ZdlPvm` (`operator delete`), followed by cold paths throwing `length_error` and calling `_Unwind_Resume`. A harmless-looking pass by value bought a heap allocation, a memory copy and a deallocation. x86-64 (`--target=x86_64-apple-macos`) has the same call sequence.

Passing large objects by value also produces `memcpy`:

```cpp godbolt title="msg.cpp" flags="-std=c++2c -O2" ok
struct Msg { char buf[1024]; };
void send(Msg m);
void forward(const Msg& m) { send(m); }
```

On AArch64 on our test machine this is `sub sp, sp, #1040` plus `bl _memcpy`; x86-64 first copies once with `callq memcpy@PLT`, then copies it into the argument area with `rep movsq`, copying the same data twice. Shrunk to 256 bytes, AArch64 switches to 8 pairs of `ldp`/`stp` (32 bytes each) copying inline with no `memcpy` call, but the amount copied is unchanged.

The AArch64 output here also has a load of `___stack_chk_guard` and a call to `___stack_chk_fail`; this is stack protection: the function has a character array on the stack, and before returning the compiler checks whether the canary value after the array has been overwritten. Clang on our test machine enables it by default for macOS targets (`-fno-stack-protector` turns it off), and not by default under `--target=x86_64-linux-gnu`. When you see an unfamiliar call, first demangle the name with `llvm-cxxfilt`, then decide whether it comes from your own code, the standard library or a compiler option. When copies happen and how to avoid them is covered in [[perf/copies-and-moves]]; heap allocation in [[perf/allocation]].

### Spills

When there are not enough registers, the compiler temporarily stores values on the stack and reloads them when needed; this is called a **spill**. Clang annotates these instructions with `Folded Spill` / `Folded Reload`, so `grep -E 'Spill|Reload'` finds them. However, the instructions in the prologue that save callee-saved registers carry the same annotation, so tell them apart.

```cpp godbolt title="spill.cpp" flags="-std=c++2c -O2" ok
long h(long);
long many(const long* p) {
  long a = p[0], b = p[1], c = p[2], d = p[3],
       e = p[4], f = p[5], g = p[6], i = p[7],
       j = p[8], k = p[9], l = p[10], m = p[11];
  long r = h(0);              // all 12 values must survive this call
  return r + a*b + c*d + e*f + g*i + j*k + l*m;
}
```

```asm title="AArch64"
__Z4manyPKl:
  sub   sp, sp, #112
  stp   x28, x27, [sp, #16]     ; 16-byte Folded Spill  ← prologue
  ...                           ;  x19–x28, x29, x30 all saved
  ldp   x9, x8, [x0]            ; load p[0], p[1]
  stp   x8, x9, [sp]            ; 16-byte Folded Spill  ← a real spill
  ldp   x21, x22, [x0, #16]
  ldp   x23, x24, [x0, #32]
  ldp   x25, x26, [x0, #48]
  ldp   x27, x28, [x0, #64]
  ldp   x19, x20, [x0, #80]
  mov   x0, #0
  bl    __Z1hl
  ldp   x9, x8, [sp]            ; 16-byte Folded Reload ← reload
  mul   x8, x9, x8
  madd  x8, x22, x21, x8        ; x8 += x22 * x21
  ...
```

`h` may modify `*p`, so the 12 values must be loaded before the call. The compiler chose to do the multiplications after the call, so all 12 values have to survive it, and there are only 10 callee-saved registers, x19–x28; the remaining 2 have to be spilled to the stack.

The same code on x86-64 makes a different choice: it computes the 6 products before the call and partially adds them, leaving only 3 values to cross the call, kept in `rbx`, `r14` and `r15`, with no spill. x86-64 has only 6 callee-saved registers, and the backend's scheduling compresses live values earlier. Both results are correct; this example only shows that spills are determined jointly by register pressure and scheduling, and you only know by looking at the actual assembly.

Spills are only worth worrying about in hot loops, where every iteration pays an extra store and load. One-time saves at the start and end of a function usually don't matter.

### Loops that weren't vectorized

Change `sum`'s `int` to `float`:

```cpp godbolt title="fsum.cpp" flags="-std=c++2c -O2" ok
float fsum(const float* p, long n) {
  float s = 0;
  for (long i = 0; i < n; ++i)
    s += p[i];
  return s;
}
```

`-Rpass=loop-vectorize -Rpass-missed=loop-vectorize -Rpass-analysis=loop-vectorize` makes Clang report its vectorization decisions. The two targets report differently on our test machine:

```text
# --target=x86_64-linux-gnu
fsum.cpp:4:7: remark: loop not vectorized: cannot prove it is safe to
reorder floating-point operations; ...
# native AArch64
fsum.cpp:3:3: remark: vectorized loop (vectorization width: 4,
interleaved count: 4) [-Rpass=loop-vectorize]
```

AArch64 claims to have vectorized it, but the assembly shows the additions are still scalar, chained one after another on the same register `s0`:

```asm title="AArch64 main loop (excerpt)"
LBB0_7:
  ldp   q1, q2, [x10, #-32]   ; vector load
  mov   s3, v1[3]             ; extract the elements one by one
  mov   s4, v1[2]
  mov   s5, v1[1]
  ...
  fadd  s0, s0, s1            ; scalar additions, strictly in order
  fadd  s0, s0, s5
  fadd  s0, s0, s4
  fadd  s0, s0, s3
  ...
  subs  x11, x11, #16
  b.ne  LBB0_7
```

On x86-64 it is 8 `addss` chained on `xmm0` (`ss` means scalar single, one `float`; `ps` is packed single, 4 `float`s). The two are essentially the same: each addition depends on the previous result and cannot run in parallel.

The reason is that floating-point addition is not associative; `(a + b) + c` and `a + (b + c)` may give different results. Under the as-if rule the compiler may only make transformations that don't change observable behavior ([[intro.abstract#1]]), and the value of `s` will eventually be output, so it cannot split one chain of additions into 4 independent accumulators. With `-ffast-math` (or the narrower `-fassociative-math -fno-signed-zeros -fno-trapping-math`), real vector additions `fadd.4s` / `addps` appear on both sides. These options make the compiler give up strict IEEE semantics, and the result may differ from the value computed in source order.

This example shows that vectorization remarks are only leads; what matters in the end is the instructions in the loop body: vector operations like `.4s`, `ps`, `pd`, `ymm`, or scalar operations one element at a time. The difference between integers and floating point in this respect, and other things that prevent vectorization, are covered in [[perf/vectorization]].

## Instruction quick reference

The left column is AArch64 in Apple assembler notation, the right column x86-64 in AT&T syntax. x86-64 instruction suffixes `b`/`w`/`l`/`q` mean 8/16/32/64 bits; AArch64 distinguishes width by register name: `w` is 32-bit, `x` 64-bit, and `s`/`d`/`q` are 32/64/128-bit floating-point or vector registers.

| Purpose | AArch64 | x86-64 |
|---|---|---|
| Register copy | `mov x0, x1` | `movq %rsi, %rdi` (source first) |
| Load | `ldr w8, [x0, #8]`, `ldr w8, [x0, x1, lsl #2]` | `movl 8(%rdi), %eax`, `movl (%rdi,%rsi,4), %eax` |
| Store | `str w8, [x0]` | `movl %eax, (%rdi)` |
| Paired load/store | `ldp x8, x9, [x0]`, `stp x29, x30, [sp, #16]` | None; save registers with `pushq`/`popq` |
| Post-/pre-indexed | `ldr w9, [x0], #4` (`x0 += 4` after the load), `stp ..., [sp, #-32]!` (decrement, then store) | None |
| Address computation | `add x0, x1, x2, lsl #2`; globals via `adrp` + `add` | `leaq 8(%rdi,%rsi,4), %rax`; globals via `leaq sym(%rip)` |
| Add, subtract, multiply | `add`, `sub`, `mul`, `madd` (multiply-add), `neg` | `addq`, `subq`, `imulq`, `incq`, `negq` |
| Division | `sdiv`, `udiv` | `idivq`, `divq` (dividend in rdx:rax) |
| Bitwise and shifts | `and`, `orr`, `eor`, `lsl`, `lsr`, `asr` | `andq`, `orq`, `xorq`, `shlq`, `shrq`, `sarq` |
| Zeroing | `mov w8, #0` | `xorl %eax, %eax` |
| Compare, set flags | `cmp x0, x1`, `tst w8, #0x80` | `cmpq %rsi, %rdi`, `testq %rdi, %rdi` |
| Conditional select | `csel x0, x1, x2, eq`, `cset w0, lt` | `cmoveq %rsi, %rax`, `setl %al` |
| Signed conditional jumps | `b.lt`, `b.le`, `b.gt`, `b.ge` | `jl`, `jle`, `jg`, `jge` |
| Unsigned conditional jumps | `b.lo`, `b.ls`, `b.hi`, `b.hs` | `jb`, `jbe`, `ja`, `jae` |
| Equal, zero | `b.eq`, `b.ne`, `cbz x0`, `cbnz x0` | `je`, `jne` |
| Unconditional jump, tail call | `b label`, `b func` | `jmp label`, `jmp func` |
| Indirect jump | `br x8` | `jmpq *%rax`, `jmpq *16(%rax)` |
| Call | `bl func`; indirect call `blr x8` | `callq func`; indirect call `callq *%rax` |
| Return | `ret` (jumps to x30) | `retq` (pops the return address) |
| Scalar floating point | `fadd s0, s0, s1`, `fmul d0, d0, d1` | `addss`, `mulsd` (`ss` single precision, `sd` double precision) |
| Vector load | `ldr q0, [x0]`, `ldp q0, q1, [x0]` | `movdqu`, `movups` (`ymm` for AVX) |
| Vector operations | `add.4s`, `fadd.4s`, `addv.4s` (horizontal sum) | `paddd`, `addps`, `vpaddd` (`ps`/`pd` are packed) |
| Trap | `brk #0x1` | `ud2` |

A few more comments in Clang's output are worth recognizing: `=>This Inner Loop Header` marks a loop header, `TAILCALL` marks a tail call, `Folded Spill`/`Folded Reload` mark saves to and reloads from the stack, and `EH_LABEL` marks positions referenced by the exception table. `# kill: def $edi ...` in x86-64 output is a note left by the register allocator saying only part of a register is used; it corresponds to no instruction.

## Questions

!!! question "A virtual call"
    Below is the entire AArch64 assembly of some function whose parameter is a reference to a polymorphic class. What does it do? Roughly where in the class definition is the called virtual function?

    ```asm
    ldr   x8, [x0]
    ldr   x1, [x8, #24]
    br    x1
    ```

<details markdown="1">
<summary>Answer</summary>

The first instruction reads the vptr from the start of the object, the second reads the function pointer at offset 24 in the vtable, and the third jumps there, as a tail call: this function makes a single virtual call and returns its result unchanged. Offset 24 is the 4th 8-byte slot (the 3rd counting from 0). Under the Itanium ABI, if the class's first virtual function is a virtual destructor, it occupies the first two slots, so the function called here is the second virtual function declared after the destructor. The vtable slot rules are in [[toolchain/object-layout-and-vtables]].

</details>

!!! question "Trapping early"
    With libc++ FAST hardening, `for (std::size_t i = 0; i < n; ++i) s += v[i];` compares `n - 1` with `v.size()` before the loop starts and executes `brk` immediately if the check fails. If `n == v.size() + 1`, the first `v.size()` accesses would have been valid. Does the compiler change the program's behavior by doing this?

<details markdown="1">
<summary>Answer</summary>

It does not change observable behavior. Executed step by step as written, the first `v.size()` iterations only read memory and add, none of which is observable behavior ([[intro.abstract#8]] lists only volatile accesses, writing files, and input and output on interactive devices); the `v.size() + 1`th access violates the hardened precondition and the program terminates. Terminating early and terminating after a few additions are indistinguishable in observable behavior, so the as-if rule ([[intro.abstract#1]]) allows merging the checks into one. If the loop contained a `printf`, the compiler could not trap early like this; it would have to produce the earlier output first.

</details>

## Summary

| What you want to confirm | What to look for in the assembly |
|---|---|
| Was the function inlined? | Whether the caller still has a `bl`/`call` to it |
| How are arguments passed? | Whether the function uses x0/rdi's value directly, or loads from `[x0]`/`(%rdi)` |
| Any redundant copies or allocations? | `memcpy`, `__Znwm` (`operator new`), `__ZdlPv` (`operator delete`) |
| Was the virtual call devirtualized? | Whether `ldr`+`ldr`+`blr`/`br`, or `call *off(%reg)`, is still there |
| Was the loop vectorized? | Whether the loop body uses `.4s`/`q` registers, `ps`/`xmm`/`ymm`, or element-by-element scalar instructions |
| Any register spills? | `str`/`ldr` in the loop body annotated `Folded Spill`/`Folded Reload` |
| Does the hardening check stay in the hot loop? | A comparison plus `b.hs`/`b.ls`/`jae` in the loop body, and `brk`/`ud2` at the end of the function |
