---
title: C 库算法
summary: <cstdlib> 的 qsort 与 bsearch——为 extern "C" 与 extern "C++" 比较函数各提供一个重载、qsort 要求元素可平凡复制（否则 UB）、语义交给 C 标准、比较函数抛出的异常允许传播；以及为什么在 C++ 中几乎总该用 std::sort / std::lower_bound
status: done
related: library.c, res.on.exception.handling, alg.sorting, alg.binary.search, basic.types.general, dcl.link
tags: 标准库, C 兼容, qsort, bsearch
updated: 2026-10-18
---

C 标准库的两个“算法”`qsort`、`bsearch` 也是 C++ 标准库的一部分。[alg.c.library] 只有四段，但几乎每一段都在处理 C 与 C++ 的边界问题：链接性、对象模型、异常。

## 声明：两套比较函数类型（¶1）

注 1：`<cstdlib>` 声明这些函数。概要中每个函数都有**两个**重载：

```cpp
void qsort(void* base, size_t nmemb, size_t size, c-compare-pred* compar);
void qsort(void* base, size_t nmemb, size_t size, compare-pred* compar);
// bsearch 同理，且对 const/非 const 的 base 各有一组
```

其中仅用于说明的 *c-compare-pred* 是 `extern "C"` 链接的函数类型 `int(const void*, const void*)`，*compare-pred* 是 `extern "C++"` 链接的同一函数类型（定义在 [[cstdlib.syn]]）。

为什么要两个？因为按 [[dcl.link]]，**语言链接是函数类型的一部分**：`extern "C"` 函数的指针与 `extern "C++"` 函数的指针在理论上是不同类型，调用约定可以不同。若只提供 C 链接的版本，传入一个普通 C++ 函数（或无捕获 lambda 转换得到的函数指针）就需要跨链接转换。提供两个重载后两者都能直接传入。（主流实现上两种链接的调用约定相同，Clang/GCC 甚至不区分这两种函数类型，但标准为可移植性做了规定。）

`bsearch` 还按 `base` 的 const 性重载，返回 `void*` 或 `const void*`——这是 C++ 修正 C 中 `bsearch` 返回非 const `void*`（丢掉 const）的做法。

## `qsort` 要求可平凡复制（¶2）

!!! std
    *Preconditions*: For `qsort`, the objects in the array pointed to by `base` are of trivially copyable type.

`qsort` 只知道元素的字节大小 `size`，它通过 `memcpy` 式的字节复制交换元素。对非平凡可复制类型（[[basic.types.general]]）——如 `std::string`（小字符串优化时内部指针指向自身）、带虚函数或自引用指针的类——字节复制不会得到有效对象。违反为 {{ub}}。

`bsearch` 没有这一要求，因为它不移动元素。

## 语义来自 C 标准（¶3）与异常（¶4）

¶3：这些函数具有 C 标准库规定的语义（引用 ISO/IEC 9899:2024 7.24.6）。所以：

- 比较函数返回负数/零/正数；必须对数组元素给出**一致的全序**（C 标准的要求），否则行为未定义；
- `qsort` **不稳定**，复杂度**未规定**（C 标准没有要求 O(N log N)，名字里的 “q” 也不代表必须是快速排序）；
- `bsearch` 要求数组已按比较函数排好序（更精确地说是相对键划分）；多个匹配元素时返回其中**任意一个**。

¶4 *Throws*：比较函数 `compar` 抛出的任何异常（[[res.on.exception.handling]]）。这是对实现的要求：即使 `qsort` 本身是用 C 写的，也必须允许 C++ 异常从比较函数穿过它传播出来（实现需要为 C 代码生成 unwind 表）。[[res.on.exception.handling]] 中相应地把 `qsort`、`bsearch` 列为 C 标准库函数“不抛异常”规则的例外。

```cpp run title="qsort.cpp" ok
#include <cassert>
#include <cstdlib>

int main() {
    int a[] = {3, 1, 2};
    std::qsort(a, 3, sizeof(int), [](const void* x, const void* y) {
        int l = *static_cast<const int*>(x), r = *static_cast<const int*>(y);
        return (l > r) - (l < r);          // 不要写 l - r：可能有符号溢出
    });
    assert(a[0] == 1 && a[2] == 3);
    int key = 2;
    auto* p = static_cast<int*>(std::bsearch(&key, a, 3, sizeof(int), [](const void* x, const void* y) {
        int l = *static_cast<const int*>(x), r = *static_cast<const int*>(y);
        return (l > r) - (l < r);
    }));
    assert(p == a + 1);
}
```

本机（macOS libc + libc++abi）上，比较函数中 `throw std::runtime_error` 能被 `qsort` 调用外的 `catch` 正常捕获。

!!! pitfall "`return l - r;`"
    C 代码中常见的比较函数写法 `return *(int*)x - *(int*)y;` 在 `l = INT_MIN, r = 1` 时有符号溢出，是 {{ub}}；即便不溢出，差值符号也可能错误。使用 `(l > r) - (l < r)`，或在 C++ 中干脆不用 `qsort`。

## 为什么 C++ 中应当用 `std::sort`

| | `qsort` | `std::sort` |
|---|---|---|
| 类型安全 | `void*`，靠程序员保证 | 模板，类型检查 |
| 元素类型 | 仅可平凡复制 | 任何可移动、可交换类型 |
| 复杂度保证 | 无 | O(N log N) |
| 比较内联 | 通过函数指针，难以内联 | 函数对象通常被内联 |
| `constexpr` | 否 | 是（C++20 起） |

`qsort` 唯一的优势是代码体积（一份实现服务所有类型）以及与 C 接口互操作。

## 思考题

<details markdown="1">
<summary>`std::qsort` 一个 `std::pair<int, int>` 数组是否合法？</summary>

不合法。标准中 `pair` 的复制赋值运算符是一个**用户提供**的成员函数（为了正确处理引用成员等情况，它不是默认化的），因而不平凡，于是 `pair<int, int>` **不是**可平凡复制类型，`qsort` 它违反 ¶2 的前置条件，{{ub}}。本机 libc++ 上 `std::is_trivially_copyable_v<std::pair<int, int>>` 为 `false`。用 `std::sort` 即可。
</details>

## 小结

- `qsort`/`bsearch` 为 C 链接和 C++ 链接的比较函数各提供重载；`bsearch` 按 const 性重载。
- `qsort` 要求元素可平凡复制，否则 UB。
- 语义完全遵循 C 标准：不稳定、无复杂度保证、`bsearch` 返回任一匹配。
- 比较函数抛出的异常可以穿过它们传播。
