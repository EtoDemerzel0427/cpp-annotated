---
title: C 兼容：检查整数运算
summary: C23 的 <stdckdint.h> 在 C++ 中提供 ckd_add、ckd_sub、ckd_mul 三个函数模板：按数学整数计算，把结果按模写回，并用返回值报告是否溢出，从而不会触发有符号溢出的 UB。
status: done
covers: *
related: numerics, numeric.sat, basic.fundamental, expr.pre, conv.integral, support.c.headers
tags: 标准库, C 兼容, 整数溢出, stdckdint
updated: 2026-10-19
---

!!! tldr
    - `ckd_add(&r, a, b)` 把 `a + b` 当作数学上的整数计算，结果按模写进 `r`，溢出时返回 `true`。整个过程没有 UB。
    - 三个操作数的类型互相独立，不做通常算术转换，所以 `ckd_sub(&ll, 0u, 1)` 得到 −1，而不是 `UINT_MAX`。
    - 三个类型都必须是有符号或无符号整数类型；`bool`、普通 `char`、字符类型和枚举都不行。
    - 只有 `<stdckdint.h>` 这个头文件，名字在全局命名空间，没有 `<cstdckdint>`，也没有 `std::ckd_add`。

## 溢出检测为什么难写

有符号整数溢出是 UB（[[expr.pre#4]]）。先算 `a + b` 再看结果是否变号，这种写法本身就已经触发了 UB；先比较 `a > INT_MAX - b` 能避免 UB，但容易写错，遇到混合类型时更麻烦。

C23 为此加入了 `<stdckdint.h>`，C++26 {{c++26}} 在 [numerics.c] 中把它引入 C++：

```cpp run title="ckd.cpp" ok
#include <climits>
#include <cstdio>
#include <stdckdint.h>

int main() {
  int r;
  bool ovf = ckd_add(&r, INT_MAX, 1);
  std::printf("%d %d\n", ovf, r);      // 1 -2147483648

  unsigned char uc;
  ovf = ckd_mul(&uc, 16, 16);
  std::printf("%d %d\n", ovf, uc);     // 1 0

  long long ll;
  ovf = ckd_sub(&ll, 0u, 1);
  std::printf("%d %lld\n", ovf, ll);   // 0 -1
}
```

第一行溢出了，`r` 里是按模回绕后的值，返回 `true`。第二行 256 装不进 `unsigned char`，同样返回 `true`。第三行最值得注意：内建表达式 `0u - 1` 会先把 `1` 转成 `unsigned`，结果是 `UINT_MAX`；`ckd_sub` 按数学整数计算，得到 −1，`long long` 装得下，所以不算溢出。

## 头文件（[stdckdint.h.syn]）

```cpp
#define __STDC_VERSION_STDCKDINT_H__ 202311L

template<class type1, class type2, class type3>
  bool ckd_add(type1* result, type2 a, type3 b);
template<class type1, class type2, class type3>
  bool ckd_sub(type1* result, type2 a, type3 b);
template<class type1, class type2, class type3>
  bool ckd_mul(type1* result, type2 a, type3 b);
```

在 C 里，`ckd_add` 等是类型泛型宏；在 C++ 里，它们被规定为函数模板，三个类型参数各自独立。

这个头文件只有 `<stdckdint.h>` 一种形式，声明在全局命名空间里。大多数 C 头文件 `<name.h>` 的规则是"和 `<cname>` 一样，再把名字放进全局命名空间"，但 [[support.c.headers.other]] 把 `<stdckdint.h>`、`<stdbit.h>`（[[stdbit.h.syn]]）、`<stdatomic.h>` 等几个头文件排除在这条规则之外，它们没有对应的 `<cname>`。

## 语义（[numerics.c.ckdint]）

¶1 *Mandates*：`type1`、`type2`、`type3` 都是有符号或无符号整数类型（[[basic.fundamental]]）。

这排除了 `bool`、普通 `char`（它既不算有符号整数类型，也不算无符号整数类型）、`char8_t` 等字符类型、枚举和浮点类型。

```cpp title="ckd-mandates.cpp" error
#include <stdckdint.h>

bool f(bool* r) { return ckd_add(r, 1, 1); }   // error: bool 不是有符号或无符号整数类型
bool g(char* r) { return ckd_add(r, 1, 1); }   // error: 普通 char 也不是
```

¶2 *Remarks*：每个函数模板的语义与 C 中同名的类型泛型宏相同。C23 规定的语义分三步：

1. 把 `a` 和 `b` 当作数学整数（精度无限），计算 a + b、a − b 或 a × b；
2. 把数学结果按 2ᴺ 取模后写入 `*result`，N 是 `*result` 类型的宽度；
3. 如果数学结果能用 `*result` 的类型精确表示，返回 `false`，否则返回 `true`。

!!! impl "本机：Clang 自带的宏版本"
    libc++ 没有自己的 `<stdckdint.h>`。本机能编译上面的例子，用的是 Clang 资源目录里 C 和 C++ 共用的版本，它把 `ckd_add(R, A, B)` 定义成宏，展开为 `__builtin_add_overflow((A), (B), (R))`。

    行为与标准一致：GCC 和 Clang 的 `__builtin_*_overflow` 本来就按无限精度计算、按模写回。但它们是宏而不是函数模板，所以不能取地址，不能显式指定模板实参，也不能用 `using` 引入。对 `bool*` 和 `char*` 结果，内建函数给出的错误说明结果必须指向除普通 `char`、`bool`、位精确整数和枚举之外的非 const 整数类型，与 *Mandates* 相符。

## 与饱和算术的对比

C++26 的 `<numeric>` 还提供饱和算术 `saturating_add`、`saturating_sub`、`saturating_mul`、`saturating_div` 和 `saturating_cast`（[[numeric.sat]]）。两者解决的问题不同：

| | `ckd_add` 等 | `saturating_add` 等 |
|---|---|---|
| 溢出时的结果 | 按模回绕的值，并返回 `true` | 夹到类型的最小值或最大值 |
| 是否告诉你溢出了 | 是 | 否 |
| 操作数类型 | 三个独立的整数类型，按数学值计算 | 两个操作数与结果是同一类型 |
| 典型用途 | 检测溢出后报错或改用更宽的整数 | 信号处理、像素运算等溢出时取极值就行的场合 |
| `constexpr` | 否 | 是 |
