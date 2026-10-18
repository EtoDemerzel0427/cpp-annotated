---
title: 指针对齐
summary: std::align 在缓冲区里找一块对齐的空间并就地更新指针与剩余长度；assume_aligned 是向优化器做出的对齐承诺，违反即 UB；C++26 的 is_sufficiently_aligned 用来在运行期检查这一承诺
status: done
related: basic.align, memory, conv.qual, mem.res.monotonic.buffer, ptrtag
tags: 标准库, 对齐, assume_aligned, UB
papers: P1007R3, P2897R7
updated: 2026-10-18
---

对齐（alignment）是核心语言的概念（[[basic.align]]）：每个对象类型都有对齐要求，对象只能放在满足该要求的地址上。[ptr.align] 提供三个与之配套的库函数，分别回答三个不同的问题：

| 函数 | 回答的问题 | 引入 |
|---|---|---|
| `std::align` | 这块缓冲区里，**第一个**满足对齐的、放得下 `size` 字节的位置在哪？ | C++11 |
| `std::assume_aligned<N>` | 我**承诺**这个指针是 `N` 对齐的，请据此优化 | C++20（[[P1007R3]]） |
| `std::is_sufficiently_aligned<N>` | 这个指针**实际上**是不是 `N` 对齐的？ | C++26（[[P2897R7]]） |

## `std::align`（¶1–¶4）

```cpp
void* align(size_t alignment, size_t size, void*& ptr, size_t& space);
```

¶1 前置条件：`alignment` 是 2 的幂；`ptr` 表示一块至少 `space` 字节的连续存储的地址。违反即 {{ub}}。

¶2 效果：若能在 `[ptr, ptr + space)` 中放下 `size` 字节、按 `alignment` 对齐的存储，就把 `ptr` 更新为**第一个**这样的地址，并把 `space` **减去为对齐跳过的字节数**；否则什么也不做。

¶3 返回：放不下时返回空指针，否则返回调整后的 `ptr`。

¶4 的注说明了这种"引用参数就地修改"设计的意图：可以对同一块缓冲区反复调用，每次用不同的对齐和大小。

```cpp title="std-align.cpp" ok
#include <memory>
#include <cstdio>
#include <cstddef>

int main() {
    alignas(16) std::byte buf[64];
    void* p = buf + 1;                // 故意错开 1 字节
    std::size_t space = sizeof(buf) - 1;
    if (void* q = std::align(16, 32, p, space)) {
        std::printf("offset: %zu, space left: %zu\n",
                    (std::size_t)((std::byte*)q - buf), space);   // offset: 16, space left: 48
    }
    void* r = buf;
    std::size_t s2 = 8;
    std::printf("fits? %s\n", std::align(16, 16, r, s2) ? "yes" : "no");   // no：只有 8 字节
}
```

!!! pitfall "space 没有减去 size"
    成功后 `space` 只减去了对齐填充（上例中从 63 减去 15 得到 48），**没有**减去 `size`。如果你要接着在后面分配下一块，必须自己写 `p = static_cast<std::byte*>(p) + size; space -= size;`。这是手写 bump allocator 时最常见的 bug：忘了这一步，下一次 `align` 会返回同一个地址。

`std::align` 只做算术，不创建对象、不开始任何生命周期。拿到地址后仍需 placement new 或 `construct_at`（[[memory]]）。[[mem.res.monotonic.buffer]] 的 `monotonic_buffer_resource` 本质上就是"`std::align` + 指针前移 + 用完向上游要新块"。

## `std::assume_aligned`（¶5–¶9）

```cpp
template<size_t N, class T> constexpr T* assume_aligned(T* ptr);
```

- ¶5 *Mandates*：`N` 是 2 的幂。
- ¶6 *Preconditions*：`ptr` 指向一个类型与 `T` **相似**（[[conv.qual]]）的对象 `X`，且 `X` 具有对齐 `N`。
- ¶7–¶8：返回 `ptr`，不抛异常。

¶9 的注把它的性质说得很清楚：

!!! std "[ptr.align]/9"
    It is up to the program to ensure that the assumption actually holds. The call does not cause the implementation to verify or enforce this.

    由程序负责保证假设成立。调用本身不会让实现去验证或强制它。

这是一个**向优化器作出的承诺**，类似于 `[[assume]]`（[[dcl.attr.assume]]）。编译器可以据此生成要求对齐的 SIMD 指令（如 x86 的 `movaps`），省去处理未对齐头部的"剥离循环"。承诺若是假的，后果是 {{ub}}——在 x86 上常见的表现是对齐 SIMD 指令触发段错误。

注里还有一句容易被忽略的话：实现可能**只对通过返回值进行的访问**应用这个假设。所以必须用返回值，而不是继续用原来的指针：

```cpp
float* a = std::assume_aligned<64>(p);   // 用 a 访问才能确保享受优化
```

¶6 有两个容易漏读的推论：

1. 前置条件要求 `ptr` **指向一个对象**。空指针不指向任何对象，所以 `assume_aligned<N>(nullptr)` 也是 UB，即使 0 地址在算术上"对齐"于任何 `N`。
2. 要求的是对象 `X`"**具有**对齐 `N`"——也就是其地址满足 `N` 对齐。这与对象类型的 `alignof` 无关：一个 `float` 当然可以恰好放在 64 字节边界上。

```cpp title="assume-aligned-ub.cpp" ub
#include <memory>
#include <cstdio>

float sum(float* p, int n) {
    float* a = std::assume_aligned<64>(p);
    float s = 0;
    for (int i = 0; i < n; ++i) s += a[i];
    return s;
}

int main() {
    alignas(64) float data[32] = {};
    std::printf("%d\n", std::is_sufficiently_aligned<64>(data + 1));   // 0
    std::printf("%f\n", sum(data + 1, 8));   // UB: data + 1 只是 4 字节对齐
}
```

本机实测：`-fsanitize=undefined` 报告 "assumption of 64 byte alignment for pointer of type 'float *' failed"；在 libc++ 加固模式 `extensive` 或 `debug` 下，非常量求值时会断言 `reinterpret_cast<uintptr_t>(ptr) % N == 0` 并终止程序（`fast` 模式不检查）。

!!! impl "实现与常量求值"
    libc++ 用 `__builtin_assume_aligned` 实现。在**常量求值**中这个内建函数无法检查真实地址，libc++ 只是调用它而不使用其结果、原样返回 `ptr`——所以 `assume_aligned` 在 `constexpr` 函数里可用但没有任何效果。

## `std::is_sufficiently_aligned`（¶10–¶13）{{c++26}}

```cpp
template<size_t Alignment, class T> bool is_sufficiently_aligned(T* ptr);
```

- ¶10 *Mandates*：`Alignment` 是 2 的幂（这条由 [[LWG4290]] 补上）。
- ¶11 *Preconditions*：指针指向一个与 `T` 相似类型的对象 `X`。（草案此处写的是 `p`，与形参名 `ptr` 不一致，是编辑性笔误。）
- ¶12：若 `X` 的对齐至少为 `Alignment`，返回 `true`。
- 不是 `constexpr`——在常量求值中无法观察真实地址。

它与 `assume_aligned` 是一对：先用 `is_sufficiently_aligned` 检查，再用 `assume_aligned` 承诺。它随 `mdspan` 的 `aligned_accessor` 一起加入 C++26：[[mdspan.accessor.aligned]] ¶5 用它定义 `aligned_accessor` 的"可访问范围"，该条的示例也正是"先用 `is_sufficiently_aligned` 检查，成立时才切换到 `aligned_accessor`"；[[ptrtag]] 的 `pointer_tag_pair::from_overaligned` 也以它表述前置条件。

注意它**同样**要求指针指向一个对象：对空指针或悬空指针调用是 UB，不是"返回 false"。libc++ 的实现只是 `reinterpret_cast<uintptr_t>(ptr) % Alignment == 0`，实际上对空指针返回 `true`，但这是实现细节，不能依赖。

## 思考题

<details markdown="1">
<summary>1. 能否用 `std::align` 判断一个已有指针是否 N 对齐？</summary>

可以，但很别扭：`void* q = p; size_t s = 1; std::align(N, 1, q, s) == p`——只要 `p` 已对齐，`align` 不需要跳过任何字节，返回 `p` 本身。但它的前置条件要求 `p` 表示至少 `space` 字节的连续存储，必须保证 `p` 处真有 1 字节可用。C++26 起直接用 `is_sufficiently_aligned` 更清楚；在此之前通常写 `reinterpret_cast<std::uintptr_t>(p) % N == 0`，这依赖于由实现定义的指针到整数映射（[[expr.reinterpret.cast]]），但所有主流平台都按地址值映射。
</details>

<details markdown="1">
<summary>2. 为什么 `assume_aligned` 是 `constexpr`，而 `is_sufficiently_aligned` 不是？</summary>

`assume_aligned` 的语义是"返回 `ptr`"，常量求值时把它当恒等函数即可，承诺无从验证也无需验证（违反前置条件本应使表达式不是常量表达式，但实现无法检测到实际地址）。`is_sufficiently_aligned` 的结果**取决于**对象的实际地址，而常量求值中对象没有确定的运行期地址，结果无法计算。
</details>

## 小结

- `std::align`：就地更新 `ptr` 和 `space`；`space` 只扣对齐填充，不扣 `size`；放不下返回空指针。
- `std::assume_aligned<N>(p)`：承诺而非检查；违反即 UB；必须通过**返回值**访问；空指针也违反前置条件。
- `std::is_sufficiently_aligned<N>(p)`：C++26 的运行期检查，非 `constexpr`，同样要求 `p` 指向对象。
