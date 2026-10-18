---
title: C 兼容：检查整数运算
summary: C23 <stdckdint.h> 在 C++ 中的形态——ckd_add/ckd_sub/ckd_mul 是三个类型各自独立的函数模板，按无限精度计算、把结果按模写回并返回是否溢出；Mandates 排除 bool、char 与枚举；与 C 宏版本和 GCC/Clang 内建函数的关系；与饱和算术的对比
status: done
covers: *
related: numerics, numeric.sat, basic.fundamental, expr.pre, conv.integral, support.c.headers
tags: 标准库, C 兼容, 整数溢出, stdckdint
updated: 2026-10-18
---

有符号整数溢出在 C 和 C++ 中都是 UB（[[expr.pre#4]]）。检测溢出的传统写法——先算再检查、或者预先比较 `a > INT_MAX - b`——前者本身就是 UB，后者容易写错且对混合类型很繁琐。C23 引入 `<stdckdint.h>`，提供三个"带检查的"整数运算；当前草案的 [numerics.c] 把它带进 C++ {{c++26}}。

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

注意两点：

- 头文件名是 `<stdckdint.h>`，**没有** `<cstdckdint>` 版本；声明在**全局命名空间**中，没有 `std::ckd_add`。[[support.c.headers]] 的表 47 把它列为 C 头文件，而 [support.c.headers.other] 把它和 `<stdbit.h>`（[[stdbit.h.syn]]）、`<stdatomic.h>` 等一起排除在"`<name.h>` 如同 `<cname>` 再把名字放进全局命名空间"的通用规则之外——它没有对应的 `<cname>` 头文件。
- 在 C 中，`ckd_add` 等是**类型泛型宏**；在 C++ 中，它们被规定为**函数模板**，三个类型参数相互独立。

## 语义（[numerics.c.ckdint]）

¶1 *Mandates*：`type1`、`type2`、`type3` 都是**有符号或无符号整数类型**（[[basic.fundamental]]）。这排除了 `bool`、`char`（普通 `char` 既不算有符号整数类型也不算无符号整数类型）、`char8_t` 等字符类型、枚举类型，以及浮点类型。

¶2 *Remarks*：每个函数模板与 C 中同名类型泛型宏的语义相同。C23 规定的语义是：

1. 把 `a` 与 `b` 视为**数学整数**（无限精度），计算 a + b、a − b 或 a × b；
2. 把数学结果**按 2ᴺ 取模**（N 为 `*result` 类型的宽度）写入 `*result`——即"环绕"后的值；
3. 若数学结果能被 `*result` 的类型精确表示，返回 `false`；否则（溢出）返回 `true`。

关键在于"数学整数"：混合类型时不做通常算术转换（[[expr.arith.conv]]），不会因为一个操作数是 `unsigned` 就把负数变成大正数。

```cpp run title="ckd.cpp" ok
#include <climits>
#include <cstdio>
#include <stdckdint.h>

int main() {
  int r;
  bool ovf = ckd_add(&r, INT_MAX, 1);
  std::printf("%d %d\n", ovf, r);           // 1 -2147483648：溢出，结果按模环绕

  unsigned char uc;
  ovf = ckd_mul(&uc, 16, 16);
  std::printf("%d %d\n", ovf, uc);          // 1 0：256 不能用 unsigned char 表示

  long long ll;
  ovf = ckd_sub(&ll, 0u, 1);
  std::printf("%d %lld\n", ovf, ll);        // 0 -1：数学上 0 − 1 = −1，long long 装得下
}
```

最后一行值得对比：内建表达式 `0u - 1` 先按通常算术转换把 `1` 转成 `unsigned`，结果是 `UINT_MAX`；`ckd_sub` 按数学整数计算，得到 −1 且不算溢出。

```cpp title="ckd-mandates.cpp" error
#include <stdckdint.h>

bool f(bool* r)  { return ckd_add(r, 1, 1); }      // error：bool 不是有符号/无符号整数类型
bool g(char* r)  { return ckd_add(r, 1, 1); }      // error：char 同理
```

## 实现视角

!!! impl "本机：Clang 的 C 头文件"
    libc++ 没有自己的 `<stdckdint.h>`。本机能编译上面的例子，是因为 Clang 自带的 `<stdckdint.h>`（在资源目录中，C 与 C++ 共用）把 `ckd_add(R, A, B)` 定义为**宏**，展开为 `__builtin_add_overflow((A), (B), (R))`。所以：

    - 行为与标准一致（GCC/Clang 的 `__builtin_*_overflow` 正是按无限精度计算并按模写回）；
    - 但它们不是函数模板：不能取地址、不能显式指定模板实参、不能被 `using` 引入；
    - `bool*` 结果被内建函数拒绝，诊断说结果实参必须指向"除普通 `char`、`bool`、位精确整数、枚举之外的"非 const 整数类型——与 *Mandates* 的要求吻合。

## 与饱和算术的比较

C++26 在 `<numeric>` 中还提供了饱和算术 `saturating_add`、`saturating_sub`、`saturating_mul`、`saturating_div`、`saturating_cast`（见 [[numeric.sat]]）。两者解决的是不同的问题：

| | `ckd_add` 等 | `saturating_add` 等 |
|---|---|---|
| 溢出时的结果 | 按模环绕的值 + `true` | 夹紧到类型的最小/最大值 |
| 是否告知溢出 | 是（返回值） | 否 |
| 操作数类型 | 三个独立的整数类型，按数学值计算 | 两个操作数与结果同一类型 |
| 适用场景 | 需要检测并处理溢出（报错、换大整数） | 信号处理、像素运算等"溢出就取极值"的场合 |
| `constexpr` | 否 | 是 |

## 小结

- `<stdckdint.h>` 只有 C 形式的头文件，名字在全局命名空间。
- C++ 中是三个类型独立的函数模板；三个类型都必须是有符号或无符号整数类型（*Mandates*）。
- 按无限精度计算，结果按模写回，返回值表示是否溢出——没有 UB。
- 本机通过 Clang 的宏版本可用，语义一致但形式不同。
