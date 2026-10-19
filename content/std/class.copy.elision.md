---
title: 复制/移动消除
summary: 实现在哪些场合可以省掉一次复制或移动（NRVO、throw、协程形参、catch），即使构造函数有副作用；它与 C++17 起 prvalue 根本不产生复制是两回事；NRVO 失败时的隐式移动；常量求值中不允许消除。
status: done
papers: P0135R1, P1825R0, P2266R3, CWG1579
related: class.temporary, basic.lval, dcl.init, stmt.return, expr.prim.id.unqual, expr.throw, except.handle, dcl.fct.def.coroutine, class.copy.ctor, expr.const.const, topics/special-members-and-elision, topics/value-categories
tags: 复制消除, NRVO, RVO, 移动语义, 值类别
updated: 2026-10-19
---

!!! tldr
    - `return T(...);` 和 `T x = f();` 这类用 prvalue 初始化的写法从 C++17 起根本没有复制，复制和移动构造函数甚至可以不存在。
    - `T t; ...; return t;` 中的复制可以省略（NRVO），但不保证，所以复制或移动构造函数必须可用。省略时构造函数的副作用也一起消失。
    - NRVO 没有发生时，`return 局部变量;` 会自动移动而不是复制；`return std::move(local);` 反而阻止 NRVO。
    - 允许省略的场合只有四种：`return` 局部对象、`throw` 局部对象、协程复制形参、`catch` 按值捕获。
    - 常量求值中不允许省略，所以 `constexpr` 的结果不取决于编译器是否做了这项优化。

## 两种不同的复制消除

```cpp run title="no-copy-at-all.cpp" ok
struct NM {
  NM() {}
  NM(const NM&) = delete;   // 不可复制
  NM(NM&&) = delete;        // 也不可移动
};

NM make()  { return NM(); }
NM make2() { return {}; }

int main() {
  NM a = make();            // OK
  NM b = NM(NM(NM()));      // OK: 只构造一次
  auto c = make2();         // OK
  (void)a; (void)b; (void)c;
}
```

`NM` 既不能复制也不能移动，这段代码却从 C++17 起合法。原因是 `NM()`、`make()` 这样的表达式是 **prvalue**（[[g:prvalue]]），它不是一个对象，而是对怎样初始化一个对象的描述；被它初始化的那个对象叫它的**结果对象**（[[g:result-object|result object]]，[[basic.lval#5]]）。用同类型的 prvalue 初始化对象时，目标对象就是结果对象（[[dcl.init#15.6.1]]），中间没有临时对象，也没有复制。

用 `-std=c++14` 编译，除了 `make2` 里的 `return {};` 之外，每一处都报告调用了被删除的构造函数。C++14 中这些地方语义上存在临时对象和复制，只是允许实现省略，所以构造函数必须可用。

返回一个有名字的局部变量，情况就不同了：

```cpp error
struct NM {
  NM() {}
  NM(NM&&) = delete;
};
NM bad() {
  NM n;
  return n;   // error: 需要移动构造函数
}
```

这里确实有一次从 `n` 到返回值的初始化。本节 [class.copy.elision] 允许实现省略它，但不要求，所以构造函数必须存在并可访问。两种情况对比如下：

| | prvalue 初始化 | 允许的复制消除（本节） |
|---|---|---|
| 例子 | `return T(...);`、`T x = f();` | `T t; return t;`（NRVO） |
| 实质 | 根本没有复制 | 有一次复制或移动，实现可以省略 |
| 是否保证 | 是，属于语言语义 | 否，由实现决定 |
| 复制/移动构造函数 | 不需要 | 必须可用 |
| 常量求值中 | 照常 | 不允许省略 |

左栏常被称为保证的复制消除（guaranteed copy elision），但标准里没有这个说法：C++17 的 [[P0135R1]] 把它从复制消除中拿出来，改成 prvalue 的语义。标准里没有被省略的复制，只有从未发生的复制。

左栏也有两个会产生临时对象的例外。一是**临时量实质化**：把 prvalue 绑定到引用、访问它的成员等，会把它变成一个临时对象（[[class.temporary#2]]）。二是平凡可复制的小类型：[[class.temporary#3]] 允许实现为传参和返回创建额外的临时对象，这样小结构体可以经寄存器传递，代价是对象的地址会变。

## 允许的复制消除（¶1）

```cpp run title="thing.cpp" ok
#include <cstdio>

class Thing {
public:
  Thing()             { std::puts("Thing()"); }
  ~Thing()            { std::puts("~Thing()"); }
  Thing(const Thing&) { std::puts("Thing(const Thing&)"); }
};

Thing f() {
  Thing t;
  return t;     // 复制可以省略：t 直接构造成 t2
}

Thing t2 = f();

int main() { std::puts("main"); }
```

本机 Clang 23 打印 `Thing()`、`main`、`~Thing()`，复制构造函数里的输出没有出现。这是标准例 1（¶2）的可运行版：`t` 的构造可以看作直接初始化 `t2`，这个对象在程序退出时销毁。给 `Thing` 加上移动构造函数，结果一样，只是被省略的变成了移动。

¶1 满足一定条件时，实现可以省略从同类型（忽略 cv 限定）的源对象创建一个类对象，即使所选的构造函数或析构函数有副作用。此时源和目标只是同一个对象的两种称呼。这叫**复制消除**（[[g:copy-elision|copy elision]]）。

!!! std
    In such cases, the implementation treats the source and target of the omitted initialization as simply two different ways of referring to the same object.

一般的优化受 as-if 规则约束（[[intro.abstract]]），只能在可观察行为不变时进行。复制消除是少数明确允许改变可观察行为的优化，复制构造函数里的 `puts` 可以不执行。

### 合并后的对象何时销毁

两个对象合成一个，就只剩一次析构。如果所选构造函数的第一个形参是该类型的右值引用（本来是一次移动），合并后的对象在目标本应销毁时销毁；否则在两者本应销毁的时刻中较晚的那个销毁。注 1 指出，少构造一个对象，也少销毁一个，构造与销毁依然一一对应。

### 四种允许的场合

¶1.1 **`return` 语句**：在返回类类型的函数里，如果 `return` 的操作数是一个非 volatile 自动存储期对象 *o* 的名字，可以把 *o* 直接构造在函数调用的结果对象里。这就是通常说的 **NRVO**（named return value optimization）。条件比较严：

- 必须是名字，可以加括号；`return c ? x : y;`、`return std::move(x);`、`return p.a;` 都不是；
- 必须是自动存储期的对象，`static` 局部变量、引用、结构化绑定都不行；
- 不能是函数形参，也不能是 `catch` 子句声明的变量。形参由调用方构造，被调用方无法把它放进返回值的位置。

¶1.2 **`throw` 表达式**：操作数是同样条件的局部对象 *o*，并且 *o* 所在的作用域不包含最内层外围 `try` 块的复合语句时，可以把 *o* 直接构造成异常对象。如果 `throw x;` 位于 `x` 作用域内部的 `try` 块里，异常可能被这个 `try` 捕获，之后代码还会用 `x`，所以 `x` 和异常对象必须是两个对象。

¶1.3 **协程**：协程会把形参复制到协程帧里（[[dcl.fct.def.coroutine]]）。如果除了副本的构造和析构之外程序含义不变，这个复制可以省略，对副本的引用改成对原形参的引用。

¶1.4 **`catch` 子句**：*handler* 声明了一个对象 *o* 时，如果除了 *o* 的构造和析构之外程序含义不变，可以把 *o* 当作异常对象的别名。注 2 指出这里不可能是移动，因为异常对象总是左值。

这几种场合可以组合，一次省掉多次复制。

## NRVO 没发生时：隐式移动（¶3）

实现不省略 `return t;` 时，用哪个构造函数初始化返回值？C++23 起，答案由 [[expr.prim.id.unqual#15]] 给出：

- **可隐式移动的实体**是自动存储期的变量，它是非 volatile 对象，或者是指向非 volatile 对象类型的右值引用；
- 如果一个名字指代这样的实体，是 `return`、`co_return` 或 `throw` 的操作数（可以加括号），并且从实体的声明到这个表达式之间只隔着块作用域（对 `throw` 还不能隔着 `try` 块的作用域），这个表达式就是 **move-eligible** 的（[[g:move-eligible]]）；
- move-eligible 的表达式是 xvalue（[[expr.prim.id.unqual#12]]），重载决议因此优先选择移动构造函数。

¶3 是标准例 2：

```cpp title="implicit-move.cpp" error
class Thing {
public:
  Thing();
  ~Thing();
  Thing(Thing&&);
private:
  Thing(const Thing&);
};

Thing f(bool b) {
  Thing t;
  if (b)
    throw t;     // OK: 用（或省略）Thing(Thing&&)
  return t;      // OK: 用（或省略）Thing(Thing&&)
}

Thing t2 = f(false);   // OK: t2 由 f 的调用构造

struct Weird {
  Weird();
  Weird(Weird&);
};

Weird g(bool b) {
  static Weird w1;
  Weird w2;
  if (b)
    return w1;   // OK: 静态变量不会隐式移动，用 Weird(Weird&)
  else
    return w2;   // error: w2 是 xvalue，绑定不到 Weird&
}

int& h(bool b, int i) {
  static int s;
  if (b)
    return s;    // OK
  else
    return i;    // error: i 是 xvalue，int& 绑定不到
}

decltype(auto) h2(Thing t) {
  return t;      // OK: decltype(t) 是 Thing，返回类型 Thing
}

decltype(auto) h3(Thing t) {
  return (t);    // OK: (t) 是 xvalue，返回类型 Thing&&
}
```

- `throw t;` 和 `return t;` 都选中移动构造函数，复制构造函数是 `private` 也没关系。
- `return w2;` 是 C++23 [[P2266R3]] 带来的不兼容变化。C++20 先把操作数当右值做一次重载决议，失败了再当左值做一次，`Weird(Weird&)` 在第二次能匹配。C++23 起它直接是 xvalue，没有第二次。本机 Clang 在 `-std=c++20` 下接受，在 `-std=c++23` 及以上拒绝。
- `return i;` 返回对形参的引用，必然悬垂。C++23 起它直接非良构，C++20 下 Clang 只给出 `-Wreturn-stack-address` 警告。
- `h3` 中 `decltype(auto)` 按 `(t)` 推导出 `Thing&&`（[[dcl.type.decltype]]），返回的引用指向形参，同样悬垂。它是良构的，但不应这样写。

隐式移动和复制消除是两层机制：前者决定需要初始化返回值时用哪个构造函数，后者决定这次初始化能否省掉。只要表达式是 move-eligible 的，NRVO 没发生时得到的是移动，不是复制。

### `throw` 与 `try` 块（¶4）

¶4 是标准例 3：

```cpp title="throw-scope.cpp" error
template<class T> void g(const T&);

template<class T> void f() {
  T x;
  try {
    T y;
    try { g(x); }
    catch (...) {
      if (/*...*/ true)
        throw x;   // 不移动
      throw y;     // 移动
    }
    g(y);
  } catch (...) {
    g(x);
    g(y);          // error: y 不在作用域内
  }
}
```

从 `x` 的声明到 `throw x;` 之间隔着外层 `try` 块的作用域，所以 `x` 不是 move-eligible 的，只能复制。这符合需要：异常被外层 `catch` 捕获后，`g(x)` 还要用 `x`。`y` 声明在外层 `try` 块里面，到 `throw y;` 之间只隔着 `catch` 子句的块作用域，所以移动。异常离开外层 `try` 块时 `y` 已经销毁，移走它的资源没有问题。

## 常量求值中不允许消除

¶1 最后规定：在要求常量表达式的语境中（[[expr.const.const]]）以及常量初始化中（[[basic.start.static]]），不允许复制消除。注 3 补充，同一个表达式在别的语境中求值时仍可能被消除。

```cpp title="constexpr-elision.cpp" error
struct A {
  void* p;
  constexpr A() : p(this) {}   // 记下自己的地址
};

constexpr A g() {
  A loc;
  return loc;
}

constexpr A a;          // OK: a.p 指向 a
constexpr A b = g();    // error: b 是 loc 的复制，b.p 悬垂
void h() {
  A c = g();            // OK: c.p 可能指向 c，也可能悬垂
}
```

这是标准例 1 的后半部分。`A` 记录自己的地址，于是能观察到复制是否被省略。如果常量求值允许消除，`b.p` 的值就取决于编译器的选择；禁止之后结果是确定的：`b` 是 `loc` 的复制，`b.p` 指向已经结束生命期的 `loc`，不能作为常量表达式的结果。本机 Clang 的附注是 `pointer to 'loc' is not a constant expression`。

`h` 中的 `c` 在运行时两种结果都允许。本机 Clang 在 `-O0` 和 `-O2` 下都得到 `c.p != &c`：`A` 是 8 字节的平凡可复制类型，按 [[class.temporary#3]] 经寄存器返回，`loc` 与 `c` 必然是两个对象。

改用 prvalue 就没有这个问题，因为根本没有复制：

```cpp run title="constexpr-ok.cpp" ok
struct A {
  void* p;
  constexpr A() : p(this) {}
};

constexpr A mk() { return A(); }   // prvalue，没有复制
constexpr A c = mk();
static_assert(c.p == &c);          // c 就是 A() 的结果对象

int main() {}
```

## 编译器实际做了什么

```cpp run title="observe.cpp" ok
#include <cstdio>

struct T {
  T()             { std::puts("  T()"); }
  T(const T&)     { std::puts("  T(const T&)"); }
  T(T&&) noexcept { std::puts("  T(T&&)"); }
  ~T()            { std::puts("  ~T()"); }
};

T make()      { return T(); }          // prvalue
T nrvo()      { T t; return t; }       // 可以 NRVO
T two(bool b) { T x, y; if (b) return x; return y; }
T param(T p)  { return p; }            // 形参

int main() {
  std::puts("make:");  { T a = make(); }
  std::puts("nrvo:");  { T b = nrvo(); }
  std::puts("two:");   { T c = two(true); }
  std::puts("param:"); { T d = param(T()); }
}
```

本机 Clang 23（`-O0`）下的构造函数调用（不计析构）：

| 函数 | C++26 | C++26，`-fno-elide-constructors` | C++14，`-fno-elide-constructors` |
|---|---|---|---|
| `make()` | `T()` | `T()` | `T()` + 2 次移动 |
| `nrvo()` | `T()` | `T()` + 1 次移动 | `T()` + 2 次移动 |
| `two(true)` | 2 次 `T()` + 1 次移动 | 同左 | 2 次 `T()` + 2 次移动 |
| `param(T())` | `T()` + 1 次移动 | 同左 | `T()` + 3 次移动 |

- `-fno-elide-constructors`（GCC 和 Clang 都有）关掉的是允许的消除。C++17 及以后，`make()` 不受影响，因为那里本来就没有复制；只有 `nrvo()` 多出一次移动。C++14 下所有临时对象都显现出来。
- `two`：两个局部变量都可能被返回，编译器无法事先决定把哪一个放在返回值的位置，NRVO 失败，退回隐式移动。
- `param`：形参不能 NRVO，但会隐式移动。
- Clang 在 `-O0` 下也做 NRVO，它在前端决定，不依赖优化级别。`return (t);` 加了括号同样会 NRVO。

`throw` 和 `catch` 虽然也允许消除，本机 Clang 两者都没做：

```cpp run title="throw-catch.cpp" ok
#include <cstdio>

struct T {
  T()             { std::puts("  T()"); }
  T(const T&)     { std::puts("  T(const T&)"); }
  T(T&&) noexcept { std::puts("  T(T&&)"); }
  ~T()            { std::puts("  ~T()"); }
};

void f1() { T t; throw t; }

int main() {
  try { f1(); } catch (T e) { std::puts("  in handler"); }
  // T() / T(T&&) / ~T() / T(const T&) / in handler / ~T() / ~T()
}
```

`throw t;` 把 `t` 移动到异常对象。异常对象由运行时库（`__cxa_allocate_exception`）在堆上分配，不可能和栈上的 `t` 共用存储。`catch (T e)` 从异常对象复制出 `e`，因为异常对象是左值。所以通常建议按值抛出、按 `const&` 捕获。

!!! impl "返回值的位置"
    在 Itanium C++ ABI 下，返回非平凡类类型的函数会收到一个隐藏参数：调用方准备好的结果对象的地址（AArch64 用 `x8` 传递，x86-64 System V 用 `rdi` 传递并从 `rax` 返回）。`return T(...);` 直接在这个地址上构造；NRVO 就是把局部变量 `t` 放在这个地址上，于是 `return t;` 什么都不用做；`two` 里的 `x` 和 `y` 不能同时放在同一地址，所以失败。

    平凡可复制的小类型按 ABI 经寄存器返回，没有结果对象的地址可传，结果对象必然是调用方的另一个对象。这就是 [[class.temporary#3]] 允许额外临时对象的原因。

!!! impl "相关警告"
    Clang 的 `-Wall` 包含这两个警告。`-Wpessimizing-move`：`return std::move(local);` 阻止了 NRVO。`-Wredundant-move`：在本来就会隐式移动的地方多写了 `std::move`，如 `T d(T p) { return std::move(p); }`。

!!! history
    - C++98 已允许省略 `return` 和 `throw`/`catch` 中的复制，即使有副作用；被省略的复制构造函数仍须可访问。
    - C++11 引入移动语义，规定可以省略复制的 `return`/`throw` 先把操作数当右值做重载决议，这是隐式移动的开端。[[CWG1579]] 又把它推广到返回类型与局部变量类型不同的情形，例如局部变量是 `unique_ptr<Derived>`、返回类型是 `unique_ptr<Base>`。
    - C++17 的 [[P0135R1]] 让 prvalue 不再产生复制，本节只剩允许的消除。
    - C++20 的 [[P1825R0]] 让右值引用类型的局部变量也能隐式移动，并取消了所选构造函数的形参必须是右值引用的限制。
    - C++23 的 [[P2266R3]] 直接把 move-eligible 的名字定为 xvalue，取消了两次重载决议；返回对局部变量的左值引用因此变成非良构。

## 常见误解

!!! pitfall "`return std::move(local);` 更快"
    `std::move(local)` 不是名字，第 1.1 项不适用，NRVO 无法进行，结果多了一次本可避免的移动。直接写 `return local;`，即使不做 NRVO 也会隐式移动。

!!! pitfall "`return cond ? a : b;` 会移动"
    条件表达式不是名字，既不能 NRVO，也不会隐式移动（它是左值），结果是一次复制。改写成 `if (cond) return a; return b;` 至少能保证移动。

!!! pitfall "返回成员、结构化绑定或 `*this` 会移动"
    `return p.a;`、`auto [a, b] = ...; return a;`、`return *this;` 都不是 move-eligible 的：成员访问不是对变量的命名，结构化绑定不是变量。它们都会复制，需要移动时显式写 `std::move`。

!!! pitfall "NRVO 一定发生，所以不需要移动构造函数"
    NRVO 是允许的，不是保证的。对不可移动的类型，`NM n; return n;` 依然非良构。只有返回 prvalue 才能摆脱对构造函数的要求。

!!! pitfall "可以依赖复制构造函数的副作用"
    在复制构造函数里计数、打日志、注册对象都不可靠，NRVO 发生与否取决于编译器和代码结构。复制构造函数应当只做复制。

## 思考题

!!! question "1. 下面三个函数哪些可能 NRVO？不 NRVO 时各调用哪个构造函数？（`T` 同 `observe.cpp`）"
    ```cpp nocheck
    T a()      { T t; return (t); }
    T b()      { static T t; return t; }
    T c(T&& r) { return r; }
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：`(t)` 是加了括号的名字。括号表达式与内部表达式完全等同（[[expr.prim.paren]]），Clang 和 GCC 都对它做 NRVO；即使不做，[[expr.prim.id.unqual#15.2]] 明确允许加括号，所以会移动。
- `b`：静态存储期，不能 NRVO，也不是可隐式移动的实体，所以复制。本机 Clang 打印 `T(const T&)`。
- `c`：`r` 是右值引用类型的自动变量，C++20 起是可隐式移动的实体，所以移动。它是引用而不是对象，不能 NRVO。
</details>

!!! question "2. `T x = T(T(T()));` 在 C++14 和 C++17 中各调用几次构造函数？"

<details markdown="1">
<summary>答案</summary>

C++14：语义上是 1 次默认构造加 3 次移动，移动都允许省略，所以实际可能 1 到 4 次，移动构造函数必须可用。C++17：只有 1 次默认构造。`T(prvalue)` 仍是同一个 prvalue，`x` 就是最内层 `T()` 的结果对象（[[dcl.init#15.6.1]]），复制和移动从未发生，所以它们可以被删除。
</details>

!!! question "3. 为什么 NRVO 不能用于函数形参，而形参却可以隐式移动？"

<details markdown="1">
<summary>答案</summary>

NRVO 要让局部变量直接住在结果对象的存储里。形参的存储由调用方在调用之前分配并初始化（Itanium ABI 中，非平凡类型的形参是调用方栈帧里的临时对象），被调用方无法让它与调用方提供的返回值位置重合。隐式移动只改变重载决议的结果，对存储位置没有要求；形参在函数返回后马上销毁，移走它的资源是安全的。
</details>
