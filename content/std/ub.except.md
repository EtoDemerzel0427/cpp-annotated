---
title: 核心 UB 目录 · 第 [except] 章
summary: Annex F.8 唯一的一条：在构造函数或析构函数的 function-try-block 的处理器中引用该对象的非静态成员或基类——此时它们已被销毁。
status: draft
related: ub, except.handle, class.cdtor, except.ctor
tags: UB, 附录, 异常, 构造
updated: 2026-10-18
---

这一页是 [[ub]] 的一部分，对应 Annex F.8：第 14 章 [except] 中唯一的显式 UB。

### F.8.1 [ub:except.handle.handler.ctor.dtor] {#except.handle.handler.ctor.dtor}

**在构造/析构函数的 function-try-block 处理器中引用对象的成员或基类** · 正文 [[except.handle#11]]

构造函数的 *function-try-block* 能捕获成员初始化器和基类构造函数抛出的异常。但当控制进入处理器时，已构造完成的成员和基类子对象**已经被析构了**（[[except.ctor]]），尚未构造的那些则从未存在过。所以处理器里引用任何非静态成员或基类都是 UB——只剩下参数和全局状态可以用。析构函数的 *function-try-block* 同理：进入处理器时成员与基类已经析构完毕。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

struct A {
  A() try : x(0 ? 1 : throw 1) {
  } catch (int) {
    std::printf("y: %d\n", y);   // UB：在 function-try-block 的处理器中引用非静态成员 y
  }   // 流出处理器末尾：异常被自动重新抛出
  int x;
  int y = 42;
};

int main() {
  try { A a; } catch (int) {}
}
```

**实测**：无 sanitizer 报告，打印 `y: 0`——`y` 的初始化器 `= 42` 根本没有执行（`x` 的初始化就抛出了）。

两条相关但**不是** UB 的规则，常与此混淆：

- 构造函数（或析构函数）的 *function-try-block* 处理器流出末尾时，当前异常会被**自动重新抛出**（[[except.handle#14]]）——你无法"吞掉"它让构造成功，对象就是没有构造出来。上例中 `main` 里的 `catch (int)` 接住的就是这次重新抛出。
- 在构造函数的 *function-try-block* 处理器里写 `return` 语句是**非良构**的（[[except.handle#13]]），编译器必须诊断。
