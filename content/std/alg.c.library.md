---
title: C 库算法
summary: <cstdlib> 的 qsort 与 bsearch：为 C 链接和 C++ 链接的比较函数各提供一个重载；qsort 要求元素可平凡复制；语义沿用 C 标准；比较函数抛出的异常可以穿过它们传播。
status: done
related: library.c, res.on.exception.handling, alg.sorting, alg.binary.search, basic.types.general, dcl.link
tags: 标准库, C 兼容, qsort, bsearch
updated: 2026-10-19
---

!!! tldr
    - `qsort` 和 `bsearch` 各有两个重载，分别接受 `extern "C"` 和 `extern "C++"` 的比较函数，因为语言链接是函数类型的一部分。
    - `qsort` 按字节搬动元素，所以要求元素是可平凡复制类型，否则是未定义行为；`std::pair<int, int>` 也不满足。
    - 其余语义沿用 C 标准：`qsort` 不稳定、没有复杂度保证，`bsearch` 在有多个匹配时返回其中任意一个。
    - 比较函数抛出的异常可以穿过 `qsort`、`bsearch` 传播出来。
    - 在 C++ 里几乎总是应该改用 `std::sort` 和 `std::lower_bound`。

```cpp run title="qsort.cpp" ok
#include <cassert>
#include <cstdlib>

int cmp_int(const void* x, const void* y) {
    int l = *static_cast<const int*>(x);
    int r = *static_cast<const int*>(y);
    return (l > r) - (l < r);   // 不要写 l - r：可能有符号溢出
}

int main() {
    int a[] = {3, 1, 2};
    std::qsort(a, 3, sizeof(int), cmp_int);
    assert(a[0] == 1 && a[2] == 3);

    int key = 2;
    auto* p = static_cast<int*>(
        std::bsearch(&key, a, 3, sizeof(int), cmp_int));
    assert(p == a + 1);
}
```

`cmp_int` 是一个普通的 C++ 函数，具有 C++ 语言链接，而 C 库里的 `qsort` 期望的是 C 函数。这段代码能够通过编译，靠的是 [alg.c.library] 的第一条规定。

## 两套比较函数类型（¶1）

¶1 的注 1 说明这些函数声明在 `<cstdlib>` 中。概要里每个函数都有两个重载：

```cpp
void qsort(void* base, size_t nmemb, size_t size, c-compare-pred* compar);
void qsort(void* base, size_t nmemb, size_t size, compare-pred* compar);
// bsearch 同理，并且对 const 和非 const 的 base 各有一组
```

仅用于说明的 *c-compare-pred* 是具有 `extern "C"` 链接的函数类型 `int(const void*, const void*)`，*compare-pred* 是具有 `extern "C++"` 链接的同一函数类型，两者定义在 [[cstdlib.syn]]。

需要两个重载，是因为按 [[dcl.link]]，语言链接是函数类型的一部分。指向 `extern "C"` 函数的指针和指向 `extern "C++"` 函数的指针是不同的类型，调用约定也可以不同。只提供 C 链接的版本，就不能直接传入普通的 C++ 函数，也不能传入无捕获 lambda 转换得到的函数指针。主流实现上两种链接的调用约定相同，Clang 和 GCC 甚至不区分这两种函数类型，但标准为了可移植性做了这样的规定。

`bsearch` 还按 `base` 是否 const 重载，分别返回 `void*` 和 `const void*`。C 的 `bsearch` 接受 `const void*` 却返回 `void*`，悄悄去掉了 const；C++ 的重载修正了这一点。

## `qsort` 要求元素可平凡复制（¶2）

!!! std
    *Preconditions*: For `qsort`, the objects in the array pointed to by `base` are of trivially copyable type.

`qsort` 只知道每个元素占 `size` 个字节，它通过逐字节复制来交换元素。对不是**可平凡复制**（[[g:trivially-copyable-type]]，[[basic.types.general]]）的类型，字节复制得不到有效的对象。例如采用小字符串优化的 `std::string`，内部指针可能指向对象自身，复制字节后新对象的指针仍指向旧位置。违反这一条是 {{ub}}。

`bsearch` 不移动元素，所以没有这个要求。

## 语义来自 C 标准（¶3）

¶3 规定这些函数具有 C 标准库规定的语义（ISO/IEC 9899:2024 7.24.6）。于是：

- 比较函数返回负数、零或正数，而且必须对数组元素给出一致的顺序，否则行为未定义；
- `qsort` 不稳定，也没有复杂度要求。C 标准没有规定 O(N log N)，名字里的 q 也不意味着必须用快速排序；
- `bsearch` 要求数组相对于键已经排好（准确地说是已划分）；有多个匹配元素时，返回其中任意一个。

!!! pitfall "`return l - r;`"
    C 代码里常见的比较函数写法 `return *(int*)x - *(int*)y;`，在 `l = INT_MIN`、`r = 1` 时有符号溢出，是 {{ub}}，溢出后结果的符号也可能是错的。应写成 `(l > r) - (l < r)`。

## 比较函数可以抛出异常（¶4）

¶4 *Throws*：`compar` 抛出的任何异常。

C 标准库函数一般不得抛出异常，[[res.on.exception.handling]] 的 ¶2 把调用了会抛异常的、由程序提供的函数的情况列为例外，`qsort`、`bsearch` 正是这种情况。这对实现提出了要求：即使 `qsort` 本身是用 C 写的，C++ 异常也必须能从比较函数穿过它传播出来，实现需要为这部分 C 代码生成栈展开信息。本机（macOS 的 libc 与 libc++abi）上，比较函数抛出的 `std::runtime_error` 能在 `qsort` 调用之外被正常捕获。

## 为什么 C++ 中应当用 `std::sort`

| | `qsort` | `std::sort` |
|---|---|---|
| 类型安全 | `void*`，由程序员保证 | 模板，编译器检查 |
| 元素类型 | 只能是可平凡复制类型 | 任何可移动、可交换的类型 |
| 复杂度保证 | 没有 | O(N log N) |
| 比较能否内联 | 通过函数指针调用，难以内联 | 函数对象通常会被内联 |
| `constexpr` | 否 | C++20 起是 |

`qsort` 的优势只有代码体积（一份实现服务所有类型）和与 C 接口互通。

## 思考题

!!! question "思考题"
    用 `std::qsort` 排序一个 `std::pair<int, int>` 数组，合法吗？

<details markdown="1">
<summary>答案</summary>

不合法。标准把 `pair` 的复制赋值运算符声明为一个普通的成员函数，而不是默认化的，这样才能正确处理引用类型的成员。它因此不是平凡的，`pair<int, int>` 不是可平凡复制类型，用 `qsort` 排序违反 ¶2 的前置条件，{{ub}}。本机 libc++ 上 `std::is_trivially_copyable_v<std::pair<int, int>>` 为 `false`。改用 `std::sort` 即可。
</details>
