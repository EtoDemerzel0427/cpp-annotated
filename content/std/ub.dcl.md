---
title: 核心 UB 目录 · 第 [dcl] 章
summary: Annex F.5 的 9 条：修改 const 对象、以非 volatile glvalue 访问 volatile 对象、引用绑定到不兼容的函数或对象、在初始化前使用引用、对未挂起的协程 resume/destroy、假设为假、noreturn 函数返回——正文出处、例子与 Clang 23 实测。
status: draft
related: ub, dcl.type.cv, dcl.ref, dcl.fct.def.coroutine, dcl.attr.assume, dcl.attr.noreturn
tags: UB, 附录, 声明, 协程, 属性
updated: 2026-10-18
---

这一页是 [[ub]] 的一部分，对应 Annex F.5：第 9 章 [dcl] 中的显式 UB。其中最后两条（`[[assume]]` 与 `[[noreturn]]`）在正文中写的是 **runtime-undefined behavior**（[[g:runtime-undefined-behavior]]）：在运行时与普通 UB 无异，但在常量求值中，是否因此判定表达式非常量由实现定义（[[expr.const.core#3]]）。实测环境同 [[ub.basic]]。

## cv 限定

### F.5.1 [ub:dcl.type.cv.modify.const.obj] {#dcl.type.cv.modify.const.obj}

**在 const 对象的生命周期内修改它** · 正文 [[dcl.type.cv#4]]

UB 的对象是"const **对象**"，不是"通过 const 路径访问的对象"。`const_cast` 掉一个指向非 const 对象的 `const int*` 再写入完全合法；只有对象本身被定义为 const（或用 `new const T` 创建）时，写入才是 UB。`mutable` 成员不受此限。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
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

**实测**：堆上那一处无任何报告（写入成功）；全局 `g` 那一处 ASan 报 `BUS on unknown address`——`g` 被放进了只读段，写入触发总线错误。**常量求值**被拒：`modification of object of const-qualified type 'const int' is not allowed in a constant expression`。

### F.5.2 [ub:dcl.type.cv.access.volatile] {#dcl.type.cv.access.volatile}

**通过非 volatile glvalue 访问定义为 volatile 的对象** · 正文 [[dcl.type.cv#5]]

volatile 访问的语义由实现定义（通常意味着"每次都真的读写内存，不合并、不删除"）。若绕过 volatile 限定去访问一个**定义为** volatile 的对象，编译器就会按普通对象优化这些访问，破坏 volatile 的本意。

```cpp ub
#include <cstdio>

volatile int x = 0;

void f() {
  int& y = const_cast<int&>(x);
  std::printf("%d\n", y);   // UB：通过非 volatile glvalue 访问 volatile 对象
}
```

## 引用

### F.5.3 [ub:dcl.ref.incompatible.function] {#dcl.ref.incompatible.function}

**把函数引用绑定到类型不调用兼容的函数** · 正文 [[dcl.ref#6]]

这是 F.3.11 的引用版，但 UB 发生得更早：**绑定**本身就是 UB，不必等到调用。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

void f(float x) { std::printf("%f\n", x); }
void (&g)(int) = reinterpret_cast<void (&)(int)>(f);   // UB：绑定时即 UB

int main() { g(1); }
```

**实测**：UBSan 的 `function` 检查在**调用**处报告：`call to function f(float) through pointer to incorrect function type 'void (*)(int)'`。工具只能在调用时发现，标准的判定点更早。

### F.5.4 [ub:dcl.ref.incompatible.type] {#dcl.ref.incompatible.type}

**把对象引用绑定到不能通过该类型访问的对象** · 正文 [[dcl.ref#6]]

同样，判定点是**绑定**：被引用的对象必须能通过引用的类型访问（[[g:type-accessible]]，即严格别名规则）。所以 `int& i = reinterpret_cast<int&>(some_float);` 哪怕从未通过 `i` 读写，也已经是 UB。正文的注补充：被指代的对象可以在生命周期之外（那由 [[basic.life]] 管）。

```cpp ub
float g;
int& i = reinterpret_cast<int&>(g);   // UB：float 对象不能通过 int glvalue 访问
```

**实测**：无报告。

### F.5.5 [ub:dcl.ref.uninitialized.reference] {#dcl.ref.uninitialized.reference}

**在引用初始化之前对它求值** · 正文 [[dcl.ref#6]]

对引用的求值必须 *happens after* 它的初始化。典型场景是跨变量的动态初始化顺序。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int& g();
extern int& ir3;
int i2 = ir3;      // UB：ir3 尚未初始化（它的初始化是动态的，排在后面）
int& ir3 = g();
int& g() { static int v = 17; return v; }

int main() { std::printf("%d\n", i2); }
```

**实测**：ASan 报 `SEGV on unknown address 0x000000000000`——引用在实现中是一个指针，静态存储先被零初始化，于是读出了空指针。

!!! lawyer "附录原例其实没有 UB"
    附录写的是 `int& ir1 = i3;`（`i3` 是全局 `int`）。这个初始化器是常量表达式（静态存储期对象的地址），所以 `ir1` 是**常量初始化**的，属于静态初始化，按 [[basic.start.static]] 先于一切动态初始化完成——`int i2 = ir1;` 执行时 `ir1` 早已绑定好了。本机运行附录原例打印 `17`，没有任何问题。正文 [[dcl.ref#6]] 的例子用的是 `int& ir3 = g();`（动态初始化），那才真正演示了这条规则；上面的例子按正文改写。

## 协程

### F.5.6 [ub:dcl.fct.def.coroutine.resume.not.suspended] {#dcl.fct.def.coroutine.resume.not.suspended}

**对未挂起的协程调用 resume** · 正文 [[dcl.fct.def.coroutine#8]]

只有**挂起**的协程才能被恢复。停在**最终挂起点**（`final_suspend` 返回 `suspend_always`）的协程虽然没被销毁，但也不算"可恢复的挂起"——[[coroutine.handle.resumption]] 要求 `resume()` 的前提是 `!done()`。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <coroutine>

struct gen {
  struct promise_type {
    int val = 0;
    gen get_return_object() { return {std::coroutine_handle<promise_type>::from_promise(*this)}; }
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
  g.next();   // UB：协程已在最终挂起点，done() 为真
  return sum;
}
```

**实测**：ASan 报 `SEGV on unknown address 0x000000000000 (pc 0x000000000000 …)`。Clang 的协程帧在到达最终挂起点时把 resume 函数指针置空，再 resume 就跳到了地址 0。（附录原例写 `suspend_always`、`coroutine_handle` 时漏了 `std::`，这里补上了。）

### F.5.7 [ub:dcl.fct.def.coroutine.destroy.not.suspended] {#dcl.fct.def.coroutine.destroy.not.suspended}

**对未挂起的协程调用 destroy** · 正文 [[dcl.fct.def.coroutine#11]]

`destroy()` 会释放协程帧。若协程此刻正在执行（例如在自己的函数体里拿到自己的句柄并销毁），之后的执行就是在已释放的帧上进行。附录原例在 `current_value()` 里调用 `destroy()`——那时协程其实已经挂起了，严格说那个例子演示的是另一个问题（销毁后再次访问 promise 与 double destroy）。下面的例子让协程在**运行中**销毁自己：

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <coroutine>

struct task {
  struct promise_type {
    task get_return_object() { return {std::coroutine_handle<promise_type>::from_promise(*this)}; }
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
  bool await_suspend(std::coroutine_handle<> h) { self = h; return false; }   // 返回 false：不挂起
  void await_resume() {}
};

task f() {
  co_await grab{};   // 拿到自己的句柄，但并未挂起
  self.destroy();    // UB：协程正在执行，没有挂起
}

int main() { f(); }
```

**实测**：ASan 报 `heap-use-after-free`——`destroy()` 释放了帧，协程随后继续在帧上执行。

## 属性

### F.5.8 [ub:dcl.attr.assume.false] {#dcl.attr.assume.false}

**假设在其出现处不为真** · 正文 [[dcl.attr.assume#1]]

`[[assume(expr)]]`（C++23）的表达式**不求值**；它只是告诉编译器"这里 expr 必为真"。若实际上不为真，求值这条假设就是 **runtime-undefined behavior**。它是一把双刃剑：写错的假设会让优化器生成错误的代码。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
#include <cstdio>

int g(int x) {
  [[assume(x >= 0)]];   // 允许编译器把 x / 32 编译成简单的右移
  return x / 32;
}

int main(int argc, char**) {
  std::printf("%d\n", g(-10 * argc));   // UB：假设为假
}
```

**实测**：UBSan 报 `assumption is violated during execution`。**常量求值**：`constexpr int v = g(-10);` 被 Clang 拒绝（`assumption evaluated to false`）。因为这是 runtime-undefined，拒绝与否由实现定义——Clang 选择了拒绝，这是一个有用的选择。

### F.5.9 [ub:dcl.attr.noreturn.eventually.returns] {#dcl.attr.noreturn.eventually.returns}

**声明为 [[noreturn]] 的函数返回了** · 正文 [[dcl.attr.noreturn#2]]

`[[noreturn]]` 函数可以通过抛异常离开，但不能正常返回。这同样是 **runtime-undefined behavior**。

```cpp ub run flags="-std=c++2c -O0 -g -fsanitize=address,undefined" cc=clang_trunk
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

**实测**：

- 编译期：`warning: function declared 'noreturn' should not return [-Winvalid-noreturn]`（[[dcl.attr.noreturn#3]] 的推荐实践）。
- `-O0 -fsanitize=undefined`：`execution reached an unreachable program point`。
- `-O2`：`puts` 被整个删掉，进程异常终止（本次退出码 137）。
- **常量求值**：与 `[[assume]]` 不同，Clang **接受**在常量求值中调用一个返回了的 `[[noreturn]] constexpr` 函数——同样是 runtime-undefined，Clang 在这里选择了"不作为非常量的理由"。两种选择都符合标准，这正是"由实现定义"的含义。
