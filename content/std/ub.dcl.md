---
title: 核心 UB 目录 · 第 [dcl] 章
summary: 第 9 章明文写出的九条未定义行为：修改 const 对象、绕过 volatile 访问、引用绑定到类型不符的函数或对象、在初始化前使用引用、对未挂起的协程 resume 或 destroy、不成立的 assume 假设、返回了的 noreturn 函数。
status: done
related: ub, dcl.type.cv, dcl.ref, dcl.fct.def.coroutine, dcl.attr.assume, dcl.attr.noreturn
tags: UB, 附录, 声明, 协程, 属性
updated: 2026-10-19
---

!!! tldr
    - 修改 const 对象是未定义行为，这里的 const 对象指定义时就是 const 的对象；通过 `const_cast` 去掉指向非 const 对象的指针上的 const 再写入，是合法的。
    - 引用绑定时就要求类型正确：把 `int&` 绑定到一个 `float` 对象，哪怕之后从不通过它读写，也已经是未定义行为。
    - 只有挂起的协程才能被 `resume` 或 `destroy`；在协程运行时销毁它，会让它在已释放的协程帧上继续执行。
    - `[[assume]]` 的条件不成立、`[[noreturn]]` 函数返回，都是运行时未定义行为：运行时与普通 UB 相同，常量求值中是否据此判定为非常量由实现决定。

Annex F 汇总了核心语言中明文写出的未定义行为，总览见 [[ub]]。它的 F.5 节对应第 9 章 [dcl]，共九条。

下文的运行结果都来自本机 Clang 23（arm64 macOS），默认用 `-O0 -g -fsanitize=address,undefined` 编译，也就是同时开启 ASan（检查内存访问）和 UBSan（检查一部分未定义行为）。常量求值指把同样的操作放进 `constexpr` 变量的初始化里，按 [[expr.const.core]]，编译器必须拒绝其中的核心语言未定义行为。

## cv 限定

### F.5.1 在 const 对象的生命周期内修改它 {#dcl.type.cv.modify.const.obj}

`[ub:dcl.type.cv.modify.const.obj]` · 正文 [[dcl.type.cv#4]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

const int g = 3;

int main() {
  int i = 2;
  const int* cip = &i;
  *const_cast<int*>(cip) = 4;   // OK：i 本身不是 const 对象

  const int* ciq = new const int(3);
  *const_cast<int*>(ciq) = 4;   // UB：修改 const 对象（动态分配的也算）
  delete ciq;

  *const_cast<int*>(&g) = 4;    // UB：修改 const 对象
  std::printf("%d\n", g);
}
```

这条规则针对的是 const 对象本身，而不是通过 const 路径访问的对象。`i` 定义时不是 const，所以去掉 `cip` 上的 const 再写入完全合法。只有对象定义为 const，或者用 `new const T` 创建时，写入才是未定义行为。类的 `mutable` 成员不受这条限制。

本机运行时，堆上那一处没有任何报告，写入成功了。全局 `g` 那一处，ASan 报告 `BUS on unknown address`：`g` 被放进了只读段，写入引发总线错误。常量求值中修改 const 对象会被拒绝，诊断是 `modification of object of const-qualified type 'const int' is not allowed in a constant expression`。

### F.5.2 通过非 volatile glvalue 访问定义为 volatile 的对象 {#dcl.type.cv.access.volatile}

`[ub:dcl.type.cv.access.volatile]` · 正文 [[dcl.type.cv#5]]

```cpp ub
#include <cstdio>

volatile int x = 0;

void f() {
  int& y = const_cast<int&>(x);
  std::printf("%d\n", y);   // UB：通过非 volatile glvalue 访问 volatile 对象
}
```

对 volatile 对象的每次读写，编译器都必须照原样执行，不能合并或删除（见 [[intro.abstract]] 的可观察行为）。如果用一个没有 volatile 限定的引用或指针去访问定义为 volatile 的对象，编译器就会把这些访问当作普通访问来优化，volatile 的保证随之失效。所以标准把这种访问定为未定义行为。

## 引用

### F.5.3 函数引用绑定到类型不兼容的函数 {#dcl.ref.incompatible.function}

`[ub:dcl.ref.incompatible.function]` · 正文 [[dcl.ref#6]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

void f(float x) { std::printf("%f\n", x); }
void (&g)(int) = reinterpret_cast<void (&)(int)>(f);   // UB：绑定时即 UB

int main() { g(1); }
```

函数引用的类型必须与被绑定函数的定义调用兼容（[[g:call-compatible]]），大致是类型相同，或者只差一个 `noexcept`。这是 [[ub.expr#expr.call.different.type|F.3.11]] 的引用版本，但未定义行为发生得更早：绑定本身就是未定义行为，不必等到调用。

本机编译时，Clang 给出 `-Wcast-function-type-mismatch` 警告。运行时，UBSan 的 `function` 检查在调用处报告 `call to function f(float) through pointer to incorrect function type 'void (*)(int)'`，随后程序打印了一个与 1 无关的浮点数。工具只能在调用时发现问题，标准的判定点在绑定处。

### F.5.4 对象引用绑定到不能通过该类型访问的对象 {#dcl.ref.incompatible.type}

`[ub:dcl.ref.incompatible.type]` · 正文 [[dcl.ref#6]]

```cpp ub
float g;
int& i = reinterpret_cast<int&>(g);   // UB：float 对象不能通过 int glvalue 访问
```

被引用的对象必须能通过引用的类型访问（[[g:type-accessible]]），这就是通常所说的严格别名规则（见 [[ub.expr#expr.basic.lvalue.strict.aliasing.violation|F.3.2]]）。判定点同样是绑定：即使之后从不通过 `i` 读写，上面的代码也已经是未定义行为。正文的注补充，被引用的对象可以处在生命周期之外，那种情况由 [[basic.life]] 管。

本机运行没有任何报告。

### F.5.5 在引用初始化之前对它求值 {#dcl.ref.uninitialized.reference}

`[ub:dcl.ref.uninitialized.reference]` · 正文 [[dcl.ref#6]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int& g();
extern int& ir3;
int i2 = ir3;      // UB：ir3 尚未初始化（它的初始化在后面）
int& ir3 = g();
int& g() { static int v = 17; return v; }

int main() { std::printf("%d\n", i2); }
```

对引用的求值必须发生在它的初始化之后（happens after，见 [[intro.races]]）。最常见的违反方式是全局变量的动态初始化顺序：同一个翻译单元里，动态初始化按定义顺序进行，`i2` 初始化时 `ir3` 还没有绑定。

本机运行时，ASan 报告 `SEGV on unknown address 0x000000000000`。引用在实现中就是一个指针，静态存储在动态初始化之前先被零初始化，所以读出的是空指针。

!!! lawyer "附录原例其实没有 UB"
    附录写的是 `int& ir1 = i3;`，`i3` 是全局 `int`。这个初始化器是常量表达式（静态存储期对象的地址），所以 `ir1` 是常量初始化的，属于静态初始化。按 [[basic.start.static]]，静态初始化先于一切动态初始化完成，`int i2 = ir1;` 执行时 `ir1` 早已绑定好了。本机运行附录原例，打印 `17`。正文 [[dcl.ref#6]] 的例子用的是 `int& ir3 = g();`，这是动态初始化，才真正演示了这条规则；上面的例子就是按正文改写的。

## 协程

下面两条都要求协程处于挂起状态。协程在 `co_await`、`co_yield` 处，或者在初始、最终挂起点停下时是挂起的；正在执行函数体时不是。

### F.5.6 对未挂起的协程调用 resume {#dcl.fct.def.coroutine.resume.not.suspended}

`[ub:dcl.fct.def.coroutine.resume.not.suspended]` · 正文 [[dcl.fct.def.coroutine#8]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <coroutine>

struct gen {
  struct promise_type {
    int val = 0;
    gen get_return_object() {
      return {std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_void() noexcept {}
    void unhandled_exception() { throw; }
    std::suspend_always yield_value(int v) noexcept { val = v; return {}; }
  };
  std::coroutine_handle<promise_type> h;
  ~gen() { h.destroy(); }
  bool next() { h.resume(); return !h.done(); }
};

gen f(int n) { for (int i = 0; i < n; ++i) co_yield i; }

int main() {
  gen g = f(3);
  int sum = 0;
  while (g.next()) sum += g.h.promise().val;
  g.next();   // UB：协程已停在最终挂起点，done() 为真
  return sum;
}
```

这是附录例子的改写（附录原例中 `suspend_always`、`coroutine_handle` 漏写了 `std::`）。循环结束时，协程已经执行完函数体，停在最终挂起点上，再调用 `resume()` 就是未定义行为。

严格地说，停在最终挂起点的协程也是挂起的，所以这个例子落在库的规则上：[[coroutine.handle.resumption]] 规定 `resume()` 的前置条件是协程处于挂起状态，并且不在最终挂起点。核心语言这一条针对的是另一种情况：协程正在运行时被恢复。两种情况都是未定义行为。

本机运行时，ASan 报告 `SEGV on unknown address 0x000000000000 (pc 0x000000000000 …)`。Clang 的协程帧到达最终挂起点时会把 resume 函数指针置空，再次 resume 就跳到了地址 0。

### F.5.7 对未挂起的协程调用 destroy {#dcl.fct.def.coroutine.destroy.not.suspended}

`[ub:dcl.fct.def.coroutine.destroy.not.suspended]` · 正文 [[dcl.fct.def.coroutine#11]]

`destroy()` 销毁协程状态并释放协程帧。如果协程此刻正在执行，比如在自己的函数体里拿到自己的句柄并销毁自己，之后的执行就发生在已经释放的帧上。

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <coroutine>

struct task {
  struct promise_type {
    task get_return_object() {
      return {std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_never initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_void() noexcept {}
    void unhandled_exception() {}
  };
  std::coroutine_handle<promise_type> h;
};

std::coroutine_handle<> self;

struct grab {
  bool await_ready() { return false; }
  // 返回 false：拿到句柄，但不挂起
  bool await_suspend(std::coroutine_handle<> h) { self = h; return false; }
  void await_resume() {}
};

task f() {
  co_await grab{};   // 拿到自己的句柄，协程继续运行
  self.destroy();    // UB：协程正在执行，没有挂起
}

int main() { f(); }
```

本机运行时，ASan 报告 `heap-use-after-free`：`destroy()` 释放了协程帧，协程随后继续在帧上执行。

附录的例子在 `current_value()` 里调用 `destroy()`，可那时协程停在 `co_yield` 处，其实是挂起的。那个例子真正的问题是销毁之后又访问 promise，以及析构函数里第二次调用 `destroy()`，所以这里换了一个例子。

## 属性

最后两条在正文中写的是**运行时未定义行为**（runtime-undefined behavior，[[defns.undefined.runtime]]）：在运行时它和普通的未定义行为一样；在常量求值中，是否因此把表达式判定为非常量由实现定义（[[expr.const.core#3]]），除此之外没有别的影响。

### F.5.8 假设在其出现处不成立 {#dcl.attr.assume.false}

`[ub:dcl.attr.assume.false]` · 正文 [[dcl.attr.assume#1]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int g(int x) {
  [[assume(x >= 0)]];   // 允许编译器把 x / 32 编译成一次右移
  return x / 32;
}

int main(int argc, char**) {
  std::printf("%d\n", g(-10 * argc));   // UB：假设不成立
}
```

`[[assume(expr)]]`（C++23）中的表达式不会被求值，它只是告诉编译器在这一点上 `expr` 一定为真。如果实际上不为真，这条假设的求值就是运行时未定义行为。写错的假设会让优化器生成错误的代码，所以只应在确有把握时使用。

本机运行时，UBSan 报告 `assumption is violated during execution`。常量求值中的 `g(-10)` 被 Clang 拒绝，诊断是 `assumption evaluated to false`。这是运行时未定义行为，拒绝与否由实现定义，Clang 选择了拒绝。

### F.5.9 声明为 `[[noreturn]]` 的函数返回了 {#dcl.attr.noreturn.eventually.returns}

`[ub:dcl.attr.noreturn.eventually.returns]` · 正文 [[dcl.attr.noreturn#2]]

```cpp run ub flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

[[noreturn]] void f(int i) {
  if (i > 0)
    throw "positive";
}   // i <= 0 时会返回

int main(int argc, char**) {
  f(argc - 1);   // UB：f(0) 返回了
  std::puts("returned");
}
```

`[[noreturn]]` 函数可以通过抛出异常离开，但不能正常返回。这同样是运行时未定义行为。

本机编译时，Clang 给出警告 `function declared 'noreturn' should not return [-Winvalid-noreturn]`，这是 [[dcl.attr.noreturn#3]] 推荐实现给出的警告。运行时 UBSan 报告 `execution reached an unreachable program point`。用 `-O2` 编译时，`puts` 被整个删掉，进程异常终止。

常量求值中，Clang 接受对一个返回了的 `[[noreturn]] constexpr` 函数的调用，并不因此把表达式判定为非常量。这与它对 `[[assume]]` 的处理不同，但两种选择都符合标准，这正是由实现定义的含义。
