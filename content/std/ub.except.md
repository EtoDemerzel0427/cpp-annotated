---
title: 核心 UB 目录 · 第 [except] 章
summary: 在构造函数或析构函数的 function-try-block 处理器中引用该对象的非静态成员或基类是未定义行为，因为此时它们已经被销毁或从未构造。
status: done
related: ub, except.handle, except.ctor, class.cdtor
tags: UB, 附录, 异常, 构造
updated: 2026-10-19
---

!!! tldr
    - 构造函数的 function-try-block 能捕获成员初始化和基类构造中抛出的异常，但进入处理器时，已经构造好的成员和基类都已被销毁。
    - 所以在这个处理器里引用对象的任何非静态成员或基类都是未定义行为；析构函数的 function-try-block 同理。
    - 处理器里能安全使用的只有函数的参数、静态成员和全局状态。
    - 处理器执行到末尾时，异常会被自动重新抛出，对象的构造仍然失败；在构造函数的处理器里写 `return` 是非良构的。

Annex F 汇总了核心语言中明文写出的未定义行为，总览见 [[ub]]。它的 F.8 节对应第 14 章 [except]，只有一条。

**function-try-block** 指把整个函数体（对构造函数来说还包括成员初始化列表）包在 `try` 里的写法：`A() try : x(...) { ... } catch (...) { ... }`。它是捕获成员或基类构造时抛出的异常的唯一办法。

### F.8.1 在 function-try-block 的处理器中引用成员或基类 {#except.handle.handler.ctor.dtor}

`[ub:except.handle.handler.ctor.dtor]` · 正文 [[except.handle#11]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

struct A {
  A() try : x(0 ? 1 : throw 1) {
  } catch (int) {
    std::printf("y: %d\n", y);   // UB：在处理器中引用非静态成员 y
  }   // 执行到处理器末尾：异常被自动重新抛出
  int x;
  int y = 42;
};

int main() {
  try { A a; } catch (int) {}
}
```

`x` 的初始化器抛出异常，控制转到处理器。按 [[except.ctor]]，这时已经构造完成的子对象都已析构，尚未构造的那些，比如这里的 `y`，从来没有存在过。所以处理器里读 `y` 读到的不是任何对象。析构函数的 function-try-block 也一样：进入处理器时，成员和基类已经析构完毕。

本机 Clang 23 在编译时给出警告 `cannot refer to a non-static member from the handler of a constructor function try block [-Wexceptions]`。运行时 ASan 和 UBSan 都没有报告，程序打印 `y: 0`：`y` 的初始化器 `= 42` 根本没有执行，读到的 0 只是那块栈内存碰巧的内容。

这样的处理器适合做的事是记录日志，或者把异常换成另一种类型再抛出。它能用的只有构造函数的参数、静态成员和全局状态。

### 两条相关的规则

下面两条规则常和这条 UB 一起出现，但它们不是 UB。

[[except.handle#14]]：控制到达构造函数或析构函数的 function-try-block 处理器末尾时，当前处理的异常会被自动重新抛出。处理器无法吞掉异常让构造成功，对象就是没有构造出来。上例中 `main` 里的 `catch (int)` 接住的就是这次重新抛出。

[[except.handle#13]]：在构造函数的 function-try-block 处理器里写 `return` 语句，程序是非良构的，编译器必须诊断。

```cpp error
struct A {
  int x;
  A() try : x(0) {
  } catch (...) {
    return;   // error: 构造函数的处理器里不能有 return
  }
};
```

本机 Clang 23 报 `return in the catch of a function try block of a constructor is illegal`。
