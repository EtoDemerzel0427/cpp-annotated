---
title: 指针对齐
summary: std::align 在缓冲区里找一块对齐的空间并就地更新指针和剩余长度；assume_aligned 是对优化器作出的对齐承诺，违反就是未定义行为；C++26 的 is_sufficiently_aligned 在运行时检查指针是否对齐。
status: done
related: basic.align, memory, conv.qual, mem.res.monotonic.buffer, ptrtag
tags: 标准库, 对齐, assume_aligned, UB
papers: P1007R3, P2897R7
updated: 2026-10-19
---

!!! tldr
    - `std::align` 在缓冲区里找第一个满足对齐、放得下 `size` 字节的位置；成功时 `space` 只减去为对齐跳过的字节，不减去 `size`。
    - `std::assume_aligned<N>(p)` 是承诺，不是检查：指针实际上没有 `N` 对齐就是未定义行为，而且应当通过它的返回值访问。
    - C++26 的 `std::is_sufficiently_aligned<N>(p)` 在运行时检查对齐，适合放在 `assume_aligned` 之前。
    - 后两个函数都要求指针指向一个对象，传空指针同样违反前置条件。

对齐是核心语言的概念（[[basic.align]]）：每个对象类型都有对齐要求，对象只能放在满足要求的地址上。[ptr.align] 提供三个配套的库函数，分别回答三个问题：

| 函数 | 回答的问题 | 引入 |
|---|---|---|
| `std::align` | 这块缓冲区里，第一个对齐的、放得下 `size` 字节的位置在哪？ | C++11 |
| `std::assume_aligned<N>` | 我承诺这个指针是 `N` 对齐的，请据此优化 | C++20（[[P1007R3]]） |
| `std::is_sufficiently_aligned<N>` | 这个指针实际上是不是 `N` 对齐的？ | C++26（[[P2897R7]]） |

## `std::align`

```cpp run title="std-align.cpp" ok
#include <cstddef>
#include <cstdio>
#include <memory>

int main() {
    alignas(16) std::byte buf[64];
    void* p = buf + 1;                    // 故意错开 1 字节
    std::size_t space = sizeof(buf) - 1;  // 63
    if (void* q = std::align(16, 32, p, space)) {
        std::printf("offset: %zu, space left: %zu\n",
                    (std::size_t)((std::byte*)q - buf), space);   // offset: 16, space left: 48
    }
    void* r = buf;
    std::size_t s2 = 8;
    std::printf("fits? %s\n", std::align(16, 16, r, s2) ? "yes" : "no");   // no：只有 8 字节
}
```

```cpp
void* align(size_t alignment, size_t size, void*& ptr, size_t& space);
```

¶1 前置条件：`alignment` 是 2 的幂；`ptr` 表示一块至少 `space` 字节的连续存储的地址。

¶2 如果能在 `ptr` 开始、长 `space` 的缓冲区里放下按 `alignment` 对齐的 `size` 字节，就把 `ptr` 更新为第一个这样的地址，并把 `space` 减去为对齐跳过的字节数；否则什么也不做。

¶3 放不下时返回空指针，否则返回调整后的 `ptr`。¶4 的注说明了就地修改引用参数的用意：可以对同一块缓冲区反复调用，每次用不同的对齐和大小。

!!! pitfall "space 没有减去 size"
    成功后 `space` 只减去了对齐填充（上例中 63 减去 15 得到 48），没有减去 `size`。要接着分配下一块，必须自己写 `p = static_cast<std::byte*>(p) + size; space -= size;`。手写顺序分配器时，忘了这一步，下一次 `align` 就会返回同一个地址。

`std::align` 只做地址计算，不创建对象，也不开始任何生命周期。拿到地址后仍要用 placement new 或 `construct_at` 构造对象（[[memory]]）。[[mem.res.monotonic.buffer]] 的 `monotonic_buffer_resource` 本质上就是 `std::align` 加指针前移，用完了再向上游要新的块。

## `std::assume_aligned`

```cpp
template<size_t N, class T> constexpr T* assume_aligned(T* ptr);
```

- ¶5 *Mandates*：`N` 是 2 的幂。
- ¶6 *Preconditions*：`ptr` 指向一个对象 `X`，`X` 的类型与 `T` 相似（[[conv.qual]]），并且 `X` 具有对齐 `N`。
- ¶7–¶8 返回 `ptr`，不抛异常。

!!! std
    It is up to the program to ensure that the assumption actually holds. The call does not cause the implementation to verify or enforce this.

¶9 的注说，由程序保证假设成立，调用本身不会让实现去验证或强制它。这是对优化器的承诺，与 `[[assume]]`（[[dcl.attr.assume]]）类似。编译器可以据此生成要求对齐的 SIMD 指令，省去处理未对齐开头的代码。承诺不成立就是 {{ub}}。

注里还有一句：实现可能只对经由返回值进行的访问应用这个假设。所以要用返回值，不要继续用原来的指针：

```cpp
float* a = std::assume_aligned<64>(p);   // 经 a 访问才能确保得到优化
```

¶6 有两个容易漏掉的推论：

1. 前置条件要求 `ptr` 指向一个对象。空指针不指向任何对象，所以 `assume_aligned<N>(nullptr)` 也是未定义行为，尽管地址 0 在算术上对任何 `N` 都对齐。
2. 要求的是对象 `X` 具有对齐 `N`，即它的地址满足 `N` 对齐，与 `alignof` 无关：一个 `float` 完全可以恰好放在 64 字节边界上。

```cpp run title="assume-aligned-ub.cpp" ub
#include <cstdio>
#include <memory>

float sum(float* p, int n) {
    float* a = std::assume_aligned<64>(p);
    float s = 0;
    for (int i = 0; i < n; ++i) s += a[i];
    return s;
}

int main() {
    alignas(64) float data[32] = {};
    std::printf("%d\n", std::is_sufficiently_aligned<64>(data + 1));   // 0
    std::printf("%f\n", sum(data + 1, 8));   // UB: data + 1 只有 4 字节对齐
}
```

本机实测：加 `-fsanitize=undefined` 时，UBSan 报告 assumption of 64 byte alignment for pointer of type 'float *' failed。libc++ 加固模式为 `extensive` 或 `debug` 时，`assume_aligned` 在运行时断言地址对齐并终止程序；`fast` 模式不检查。

!!! impl "常量求值中的 assume_aligned"
    libc++ 用 `__builtin_assume_aligned` 实现它。常量求值中无法检查真实地址，libc++ 在这种情况下直接返回 `ptr`。所以 `assume_aligned` 可以在 `constexpr` 函数里使用，但在常量求值中没有任何效果。

## `std::is_sufficiently_aligned` {{c++26}}

```cpp
template<size_t Alignment, class T> bool is_sufficiently_aligned(T* ptr);
```

- ¶10 *Mandates*：`Alignment` 是 2 的幂。这一条由 [[LWG4290]] 补上。
- ¶11 *Preconditions*：指针指向一个对象 `X`，`X` 的类型与 `T` 相似。草案这里写的是 `p`，与形参名 `ptr` 不一致，属于编辑性笔误。
- ¶12–¶13 如果 `X` 的对齐至少为 `Alignment`，返回 `true`，否则返回 `false`；不抛异常。

它不是 `constexpr` 的，因为结果取决于对象的实际地址。

它与 `assume_aligned` 是一对：先用 `is_sufficiently_aligned` 检查，成立时再用 `assume_aligned` 承诺。它随 `mdspan` 的 `aligned_accessor` 一起加入 C++26：[[mdspan.accessor.aligned]] 用它描述 `aligned_accessor` 的可访问范围，那里的示例就是先检查、成立时才换用 `aligned_accessor`。[[ptrtag]] 的 `pointer_tag_pair::from_overaligned` 也用它表述前置条件。

`is_sufficiently_aligned` 同样要求指针指向一个对象：对空指针或悬空指针调用是未定义行为，而不是返回 `false`。libc++ 的实现只是 `reinterpret_cast<uintptr_t>(ptr) % Alignment == 0`，对空指针实际返回 `true`，但这是实现细节，不能依赖。

## 思考题

!!! question "思考题 1"
    能用 `std::align` 判断一个已有的指针是否 `N` 对齐吗？

<details markdown="1">
<summary>答案</summary>

可以，但很别扭：`void* q = p; size_t s = 1; std::align(N, 1, q, s) == p`。`p` 已经对齐时，`align` 不需要跳过任何字节，返回 `p` 本身。不过它的前置条件要求 `p` 处确实有至少 1 字节的存储。

C++26 起直接用 `is_sufficiently_aligned` 更清楚。在此之前通常写 `reinterpret_cast<std::uintptr_t>(p) % N == 0`，它依赖由实现定义的指针到整数的映射（[[expr.reinterpret.cast]]），但所有主流平台都按地址值映射。
</details>

!!! question "思考题 2"
    为什么 `assume_aligned` 是 `constexpr` 的，而 `is_sufficiently_aligned` 不是？

<details markdown="1">
<summary>答案</summary>

`assume_aligned` 的结果就是 `ptr`，常量求值时把它当作恒等函数即可，承诺无法验证，也不需要验证。`is_sufficiently_aligned` 的结果取决于对象的实际地址，而常量求值中的对象没有确定的运行时地址，结果无法计算。
</details>
