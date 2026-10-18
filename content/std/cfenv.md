---
title: 浮点环境
summary: <cfenv> 只是 C <fenv.h> 的子集；FENV_ACCESS 编译指示是否支持由实现定义，因此用这些函数检测异常标志、切换舍入模式是否真的生效也由实现定义；浮点环境具有线程存储期，子线程在 thread/jthread 构造时继承父线程的环境
status: done
covers: *
related: numerics, c.math, library.c, cpp.pragma, expr.const, thread.thread.class, basic.stc.thread
tags: 标准库, 浮点, 舍入模式, 浮点异常, 线程
updated: 2026-10-18
---

IEEE 754 规定了一组**浮点状态**：五个异常标志（除以零、不精确、无效、上溢、下溢）和若干**控制模式**（最重要的是舍入方向）。C 通过 `<fenv.h>` 让程序读写它们，C++ 的 `<cfenv>` 把这套接口原样搬过来——但没有搬来让它可靠工作的那一半：编译器必须知道"这段代码会观察或修改浮点环境"，否则它会按默认环境做常量折叠、指令重排，测试标志和切换舍入模式都可能失效。

本节回答两个问题：`<cfenv>` 里有什么、标准对它保证了多少（[cfenv.syn]）；多线程下每个线程看到的是哪个环境（[cfenv.thread]）。

## 头文件内容与 FENV_ACCESS（[cfenv.syn]）

概要声明了：

- 异常宏 `FE_DIVBYZERO`、`FE_INEXACT`、`FE_INVALID`、`FE_OVERFLOW`、`FE_UNDERFLOW`（均标注 *optional*：实现不支持某个异常就不定义对应的宏）与 `FE_ALL_EXCEPT`；
- 舍入宏 `FE_DOWNWARD`、`FE_TONEAREST`、`FE_TOWARDZERO`、`FE_UPWARD`（同样 *optional*）；
- `FE_DFL_ENV`，以及对象类型 `fenv_t`、`fexcept_t`；
- 函数：异常标志的 `feclearexcept`/`fegetexceptflag`/`feraiseexcept`/`fesetexceptflag`/`fetestexcept`，舍入的 `fegetround`/`fesetround`，整个环境的 `fegetenv`/`feholdexcept`/`fesetenv`/`feupdateenv`。

¶1 规定内容与含义是 C `<fenv.h>` 的子集，**只有**概要中列出的声明存在。C23 在 `<fenv.h>` 里新增的 `fesetexcept`、`fetestexceptflag`、`femode_t`/`fegetmode`/`fesetmode` 等都不在概要中，因而不属于 `<cfenv>`。

关键在 ¶1 的注释：

!!! std
    This document does not require an implementation to support the FENV_ACCESS pragma; it is implementation-defined whether the pragma is supported.

    本标准不要求实现支持 `FENV_ACCESS` 编译指示；是否支持由实现定义（[[cpp.pragma]]）。

注释接着推出两个后果：

1. 因此，**这些函数能否用于检测浮点状态标志、设置控制模式、或在非默认模式下运行，是实现定义的**。换言之，`fesetround(FE_UPWARD)` 返回 0 只说明调用"成功"，不说明后续 `a + b` 真的向上舍入。
2. 如果用这个编译指示开启了对浮点环境的控制，标准**不规定**它对常量表达式中浮点求值的影响。

为什么 `FENV_ACCESS` 这么关键？因为在默认状态（C 中称 `FENV_ACCESS OFF`）下，编译器被允许假定程序处在默认浮点环境：舍入到最近、不关心异常标志。它可以在编译期把 `1.0 / 3.0` 算好、把没被用到的除法删掉、把运算移过 `fesetround` 调用。开启 `FENV_ACCESS` 就是告诉编译器"这些假设在这里不成立"。

```cpp run title="fenv.cpp" impl
#include <cfenv>
#include <cstdio>

#pragma STDC FENV_ACCESS ON   // 是否支持：实现定义

int main() {
  std::feclearexcept(FE_ALL_EXCEPT);
  volatile double zero = 0.0;
  double r = 1.0 / zero;                    // 引发 FE_DIVBYZERO，结果 +inf
  std::printf("%g %d\n", r, std::fetestexcept(FE_DIVBYZERO) != 0);

  std::fesetround(FE_UPWARD);
  volatile double one = 1.0, three = 3.0;
  std::printf("%.17g\n", one / three);      // 运行期：向上舍入
  constexpr double c = 1.0 / 3.0;           // 常量求值：标准不规定受不受影响
  std::printf("%.17g\n", c);
}
```

在本机（Clang 23，arm64 macOS，`-O2`）上，第一行打印 `inf 1`；向上舍入下运行期的 `1/3` 打印 `0.33333333333333338`，而 `constexpr` 的那个打印 `0.33333333333333332`——两者差一个 ulp，常量求值用的是默认的舍入到最近。

!!! impl "实现视角"
    - Clang 识别 `#pragma STDC FENV_ACCESS ON`，在其作用范围内改用"受约束的浮点"中间表示，禁止跨越环境修改的重排和按默认环境的折叠；也可以用 `-ffp-model=strict` 在整个 TU 上达到类似效果。
    - GCC 长期不支持这个编译指示，一般改用 `-frounding-math`、`-ftrapping-math` 等选项控制同类假设。
    - 在一些 ABI 下（例如 x87），舍入模式对 `long double` 和 `double` 的影响还取决于精度控制位。这些都是"实现定义"四个字背后的现实。

### 与常量求值的关系

[[library.c#3]] 规定：C 标准库函数的调用如果引发 `FE_INEXACT` 以外的浮点异常，就是[[g:non-constant-library-call|非常量库调用]]，不能出现在常量表达式中；常量求值中 C 库函数的语义按 C 附录 F（IEEE 754 绑定）。结合本节的注释可以得出：常量表达式里的浮点运算**总是**按默认环境理解——标准不承诺编译期运算会跟随你在运行期设置的舍入模式。

## 线程（[cfenv.thread]）

¶1：浮点环境具有**线程存储期**（[[basic.stc.thread]]）。线程的浮点环境初始状态，等于构造对应 `thread` 或 `jthread` 对象的那个线程**在构造对象那一刻**的浮点环境。注释说得更直白：子线程继承父线程在创建它时的浮点状态。

¶2：每个线程维护独立的浮点环境；每个函数访问的是**调用线程**的环境。

所以在一个线程里 `fesetround` 不会影响其他已经存在的线程；但在 `fesetround` 之后创建的 `std::thread`，按标准应以同样的舍入模式起步。

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

!!! warning "实测：libc++ on macOS 不满足 ¶1"
    在本机（arm64 macOS，Clang 23 + libc++）上运行上例，父线程是 `FE_UPWARD`，子线程读到的却是 `0`（`FE_TONEAREST`）——新线程从默认浮点环境起步，没有继承。libc++ 的 `std::thread` 直接用 pthread 创建线程，没有额外复制创建者的浮点控制状态，而该平台的新线程以默认浮点环境起步。要在子线程里使用非默认模式，可移植的做法是**在线程函数开头自己设置**，不要依赖继承。

## 陷阱

!!! pitfall "以为 fesetround 一调用就生效"
    没有 `FENV_ACCESS`（或等价编译选项）时，编译器可以把 `fesetround` 之后的运算挪到它前面，或在编译期按默认舍入算好。标准把这一切都归入"实现定义"。测试舍入敏感的代码时，至少要确认编译器支持该编译指示，并检查优化后的行为。

!!! pitfall "忘了恢复环境"
    浮点环境是线程级全局状态。库函数里改了舍入模式而不恢复，会污染调用者的所有后续计算。惯用法是 `feholdexcept` 保存、`feupdateenv` 恢复，或写一个 RAII 守卫：构造时 `fegetenv`，析构时 `fesetenv`。

## 思考题

!!! question "1"
    `constexpr double x = std::nextafter(1.0, 2.0);` 在 C++26 中是否可能是常量表达式？`constexpr double y = 1e308 * 10;` 呢？

<details markdown="1">
<summary>答案</summary>

`nextafter` 在当前 [[cmath.syn]] 中声明为 `constexpr`。它的这个调用不引发 `FE_INEXACT` 以外的异常，所以按 [[library.c#3]] 不是非常量库调用，可以是常量表达式（前提是实现真的提供了 `constexpr` 版本；本机 libc++ 尚未提供）。

`1e308 * 10` 是内建运算，不涉及库。数学结果超出 `double` 的范围，按 IEEE 754 舍入为 `+inf`。[[expr.pre#4]] 说只要结果"是该类型拥有的无穷"就不是 UB；但 [[expr.const.core]] ¶2.9.1 另行规定：所有操作数有限而结果非有限的算术表达式不是核心常量表达式。所以按当前草案 `y` 非良构。

实测：本机 Clang 23 接受这一行而不报错——这条常量求值规则是 C++23 之后的新措辞，Clang 尚未实现。
</details>

## 小结

| 规则 | 出处 | 要点 |
|---|---|---|
| `<cfenv>` 是 `<fenv.h>` 的子集 | [cfenv.syn] ¶1 | 只有概要中的声明 |
| `FENV_ACCESS` 是否支持 | ¶1 注释 | 实现定义；因此测试标志/改舍入是否有效也实现定义 |
| 常量求值 | ¶1 注释、[[library.c#3]] | 不受运行期环境影响；引发非 inexact 异常的库调用不是常量 |
| 线程存储期 | [cfenv.thread] ¶1–¶2 | 每线程一份；子线程继承创建者当时的环境（libc++/macOS 实测不继承） |
