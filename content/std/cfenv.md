---
title: 浮点环境
summary: <cfenv> 是 C <fenv.h> 的子集；FENV_ACCESS 编译指示是否支持由实现定义，所以测试异常标志、切换舍入模式是否真的生效也由实现定义；浮点环境每个线程一份，新线程继承创建者当时的环境。
status: done
covers: *
related: numerics, c.math, library.c, cpp.pragma, expr.const, thread.thread.class, basic.stc.thread
tags: 标准库, 浮点, 舍入模式, 浮点异常, 线程
updated: 2026-10-19
---

!!! tldr
    - `<cfenv>` 提供读写浮点异常标志和舍入模式的函数，是 C `<fenv.h>` 的一个子集，C23 新增的函数不在其中。
    - 标准不要求实现支持 `#pragma STDC FENV_ACCESS`。所以 `fesetround` 返回成功，也不保证之后的运算真的按新模式舍入。
    - 常量求值不跟随运行期设置的舍入模式；会引发 inexact 以外浮点异常的 C 库调用不是常量表达式。
    - 浮点环境每个线程一份。标准规定新线程继承创建者当时的环境，本机 libc++ 在 macOS 上没有做到。

## 浮点环境是什么

```cpp
std::fesetround(FE_UPWARD);
double x = a / b;              // 向上舍入？不一定
if (std::fetestexcept(FE_INEXACT)) { /* 结果不精确 */ }
```

IEEE 754 规定了一组**浮点状态**：五个异常标志（除以零、不精确、无效运算、上溢、下溢），以及若干控制模式，其中最重要的是舍入方向。这些状态合称**浮点环境**（floating-point environment）。C 用 `<fenv.h>` 让程序读写它们，C++ 的 `<cfenv>` 照搬了这套接口。

问题在于编译器。优化器默认假设程序处在默认浮点环境里：舍入到最近，没人关心异常标志。基于这个假设，它可以在编译期算好 `1.0 / 3.0`，删掉结果没被用到的除法，把运算挪过 `fesetround` 调用。上面两行代码因此都可能不按预期工作。

## 头文件内容（[cfenv.syn]）

概要声明了：

- 异常宏 `FE_DIVBYZERO`、`FE_INEXACT`、`FE_INVALID`、`FE_OVERFLOW`、`FE_UNDERFLOW` 和 `FE_ALL_EXCEPT`；
- 舍入宏 `FE_DOWNWARD`、`FE_TONEAREST`、`FE_TOWARDZERO`、`FE_UPWARD`；
- `FE_DFL_ENV`，类型 `fenv_t`、`fexcept_t`；
- 异常标志函数 `feclearexcept`、`fegetexceptflag`、`feraiseexcept`、`fesetexceptflag`、`fetestexcept`；
- 舍入函数 `fegetround`、`fesetround`；
- 整个环境的 `fegetenv`、`feholdexcept`、`fesetenv`、`feupdateenv`。

异常宏和舍入宏都标为 optional：实现不支持某种异常或舍入方向，就不定义对应的宏。

¶1 头文件的内容和含义是 C `<fenv.h>` 的子集，只有概要中列出的声明存在。C23 新增的 `fesetexcept`、`fetestexceptflag`、`femode_t`、`fegetmode`、`fesetmode` 等不在概要中，不属于 `<cfenv>`。

## FENV_ACCESS 与实现定义（¶1 注 1）

C 用 `#pragma STDC FENV_ACCESS ON` 告诉编译器：这段代码会观察或修改浮点环境，默认环境的假设在这里不成立。C++ 没有要求支持它：

!!! std
    This document does not require an implementation to support the FENV_ACCESS pragma; it is implementation-defined whether the pragma is supported.

注 1 接着推出两点。第一，这些函数能否用来测试异常标志、设置控制模式、在非默认模式下运行，都由实现定义。`fesetround(FE_UPWARD)` 返回 0 只说明调用本身成功。第二，即使用这个编译指示开启了对浮点环境的控制，标准也不规定它对常量表达式中浮点求值的影响。

```cpp run title="fenv.cpp" impl
#include <cfenv>
#include <cstdio>

#pragma STDC FENV_ACCESS ON   // 是否支持：实现定义

int main() {
  std::feclearexcept(FE_ALL_EXCEPT);
  volatile double zero = 0.0;
  double r = 1.0 / zero;          // 引发 FE_DIVBYZERO，结果 +inf
  std::printf("%g %d\n", r, std::fetestexcept(FE_DIVBYZERO) != 0);

  std::fesetround(FE_UPWARD);
  volatile double one = 1.0, three = 3.0;
  std::printf("%.17g\n", one / three);   // 运行期：向上舍入
  constexpr double c = 1.0 / 3.0;        // 常量求值：不受影响
  std::printf("%.17g\n", c);
}
```

本机（Clang 23，arm64 macOS，`-O2`）输出 `inf 1`、`0.33333333333333338`、`0.33333333333333332`。运行期的除法向上舍入，常量求值的结果仍是舍入到最近，两者差一个 ulp。

!!! impl "编译器怎样处理"
    - Clang 识别 `#pragma STDC FENV_ACCESS ON`，在其作用范围内禁止跨越环境修改的重排和按默认环境的常量折叠。`-ffp-model=strict` 可以在整个翻译单元上达到类似效果。
    - GCC 长期不支持这个编译指示，一般改用 `-frounding-math`、`-ftrapping-math` 等选项控制同类假设。

### 与常量求值的关系

[[library.c#3]] 规定，C 标准库函数的调用如果会引发 `FE_INEXACT` 以外的浮点异常，就是[[g:non-constant-library-call|非常量库调用]]，不能出现在常量表达式中。常量求值中 C 库函数的语义按 C 标准附录 F（IEEE 754 绑定）理解。

结合上面的注 1，可以这样理解：编译期的浮点运算按默认环境进行，标准不承诺它跟随运行期设置的舍入模式。

## 线程（[cfenv.thread]）

¶1 浮点环境具有线程存储期（[[basic.stc.thread]]）。新线程浮点环境的初始状态，等于构造对应 `thread` 或 `jthread` 对象的那个线程在构造时刻的浮点环境。注 1 的说法更直接：子线程继承父线程在创建它时的浮点状态。

¶2 每个线程维护各自的浮点环境，每个函数访问的都是调用线程的环境。

所以一个线程里的 `fesetround` 不影响已经存在的其他线程；在它之后创建的 `std::thread`，按标准应以同样的舍入模式起步。

```cpp run title="fenv-thread.cpp" impl
#include <cfenv>
#include <cstdio>
#include <thread>

int main() {
  std::fesetround(FE_UPWARD);
  int child = -1;
  std::thread t([&] { child = std::fegetround(); });   // 标准：应等于 FE_UPWARD
  t.join();
  std::printf("parent=%d child=%d FE_UPWARD=%d\n",
              std::fegetround(), child, FE_UPWARD);
}
```

!!! warning "本机 libc++ 不满足 ¶1"
    在 arm64 macOS、Clang 23 + libc++ 上，父线程是 `FE_UPWARD`，子线程读到的是 `0`（`FE_TONEAREST`）。libc++ 的 `std::thread` 直接用 pthread 创建线程，没有复制创建者的浮点控制状态，而该平台的新线程从默认浮点环境起步。要在子线程里使用非默认模式，可移植的做法是在线程函数开头自己设置。

## 常见误解

!!! pitfall "以为 fesetround 一调用就生效"
    没有 `FENV_ACCESS` 或等价的编译选项时，编译器可以把 `fesetround` 之后的运算挪到它前面，或者在编译期按默认舍入算好。标准把这些都归为实现定义。测试舍入敏感的代码时，先确认编译器支持这个编译指示，再检查优化后的行为。

!!! pitfall "改了环境不恢复"
    浮点环境是线程级的全局状态。库函数改了舍入模式而不恢复，会影响调用者之后的所有计算。常见做法是用 `feholdexcept` 保存、`feupdateenv` 恢复，或者写一个 RAII 守卫：构造时 `fegetenv`，析构时 `fesetenv`。

## 思考题

!!! question "思考题 1"
    `constexpr double x = std::nextafter(1.0, 2.0);` 在当前草案下可以是常量表达式吗？`constexpr double y = 1e308 * 10;` 呢？

<details markdown="1">
<summary>答案</summary>

`nextafter` 在 [[cmath.syn]] 中声明为 `constexpr`。这次调用不引发 `FE_INEXACT` 以外的异常，按 [[library.c#3]] 不是非常量库调用，所以可以是常量表达式。本机 libc++ 还没有提供 `constexpr` 版本，实际编译会失败。

`1e308 * 10` 是内建运算，与库无关。数学结果超出 `double` 的范围，按 IEEE 754 舍入为 `+inf`。按 [[expr.pre#4]]，结果是该类型拥有的无穷，所以不是 UB。但 [[expr.const.core]] ¶2.9.1 规定，所有操作数有限而结果不有限的算术表达式不是核心常量表达式，所以 `y` 的声明非良构。本机 Clang 23 接受了这一行，这条规则是 C++23 之后的新措辞，Clang 尚未实现。
</details>

## 小结

| 规则 | 出处 | 要点 |
|---|---|---|
| `<cfenv>` 是 `<fenv.h>` 的子集 | [cfenv.syn] ¶1 | 只有概要中的声明 |
| `FENV_ACCESS` 是否支持 | ¶1 注 1 | 实现定义；所以测试标志、改舍入是否生效也是实现定义 |
| 常量求值 | ¶1 注 1、[[library.c#3]] | 不跟随运行期环境；引发非 inexact 异常的库调用不是常量 |
| 线程 | [cfenv.thread] ¶1–¶2 | 每线程一份，子线程继承创建者当时的环境（本机 libc++ 未做到） |
