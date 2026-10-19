---
title: 上下文依赖
summary: 未求值操作数（sizeof、decltype、noexcept 等的操作数）不被求值；弃值表达式只为副作用而求值，什么时候会读取 volatile 对象、什么时候实质化临时对象。
status: done
papers: P0135R1, P1152R4
related: basic.lval, conv.lval, conv.rval, basic.def.odr, class.temporary, stmt.expr, expr.comma, dcl.type.decltype
tags: 未求值操作数, 弃值表达式, volatile
updated: 2026-10-19
---

!!! tldr
    - `sizeof`、`decltype`、`noexcept`、requires 表达式等的操作数是未求值操作数：不会被求值，其中的名字不需要定义，但照常做全部语义检查。
    - 只为副作用而写的表达式（表达式语句、逗号左边、`(void)e`）是弃值表达式：会被求值，结果丢弃。
    - 弃值表达式不读取普通变量；只有 volatile glvalue 写成名字、`*p`、`a[i]`、`s.m` 这类形式时才真的读一次，`vi = 1;` 不会再多读。
    - 弃值的类类型 prvalue 会实质化一个临时对象，所以 `make();` 也要求析构函数可用。

## 未求值操作数（¶1）

```cpp ok
#include <utility>
struct S { int m; static int sm; };   // sm 只声明，从未定义
int g();                              // 只声明，从未定义

auto a = sizeof(g());                 // g 不会被调用，也不需要定义
auto b = sizeof(S::m);                // 不借助对象就可以命名非静态成员
auto c = sizeof(S::sm);               // 不构成 odr-use
using T = decltype(std::declval<S>().m);   // declval 只有声明，从来不能被求值

int n = 0;
auto d = sizeof(n++);                 // n 仍然是 0
constexpr bool e = noexcept(g());     // false：g 没有声明 noexcept，但并没有被调用
```

¶1 某些语境中的操作数是**未求值操作数**（[[g:unevaluated-operand]]）：

!!! std
    An unevaluated operand is not evaluated.

当前草案列出的语境有：requires 表达式中的简单要求和复合要求（[[expr.prim.req.simple]]、[[expr.prim.req.compound]]），`typeid` 的操作数（多态类的 glvalue 除外，[[expr.typeid]]），`sizeof`（[[expr.sizeof]]），`noexcept` 运算符（[[expr.unary.noexcept]]），{{c++26}} 反射运算符 `^^`（[[expr.reflect]]），`decltype`（[[dcl.type.decltype]]），以及模板约束和概念定义中的约束表达式（[[temp.pre]]、[[temp.concept]]）。`alignof` 的操作数是类型而不是表达式，不在其中。

注 1 列出了三个推论：

1. 可以不借助对象命名非静态类成员，如 `sizeof(S::m)`（[[expr.prim.id]]）。
2. 命名一个对象或函数本身不要求它有定义。未求值操作数中的名字不构成 **odr-use**（[[g:odr-use]]，需要定义的那种使用，[[basic.def.odr]]），所以 `std::declval` 可以只声明不定义。
3. 未求值操作数被看作一个完整表达式（[[g:full-expression]]）。

### 不求值，但照常检查

未求值操作数仍然要通过全部语义检查：重载决议、访问控制、类型完整性（`sizeof` 要求完整类型）都照常进行。[[class.temporary#1]] 还规定，即使创建临时对象这件事是不求值的，也要满足如同真的创建并销毁了它时的全部语义限制，包括构造函数和析构函数可访问、没有被删除。例外只有 `decltype` 的操作数，它不引入临时对象（[[dcl.type.decltype#2]]）。

<div class="compare" markdown="1">

```cpp ok
struct NoDtor { ~NoDtor() = delete; };
NoDtor make();
// decltype 不引入临时对象
using T = decltype(make());
```

```cpp error
struct NoDtor { ~NoDtor() = delete; };
NoDtor make();
// 不求值，但仍要求析构函数可用
auto s = sizeof(make());   // error
```

</div>

## 弃值表达式（¶2）

¶2 有些语境中的表达式只是为了副作用而出现，这样的表达式叫做**弃值表达式**（[[g:discarded-value-expression]]）。常见的有：

| 语境 | 条款 |
|---|---|
| 表达式语句 `e;` | [[stmt.expr]] |
| 逗号运算符的左操作数 `e, x` | [[expr.comma]] |
| 转换为 `void`：`(void)e`、`static_cast<void>(e)` | [[expr.static.cast#4]] |
| `for` 语句的第三个子句 | [[stmt.for]] |
| 用 `.` 访问静态成员或枚举项时左边的对象表达式 | [[expr.ref#2]] |

对弃值表达式，¶2 按下面的步骤处理：

1. 不施行数组到指针和函数到指针转换，所以 `arr;`、`func;` 什么也不做。
2. 当且仅当表达式是 volatile 限定类型的 glvalue，并且是下面的形式之一时，施行左值到右值转换，也就是真的读一次（[[conv.lval]]）：
    - ¶2.1 `( e )`，`e` 是本列表中的形式；
    - ¶2.2 *id-expression*（名字）；
    - ¶2.3 {{c++26}} 拼接表达式；
    - ¶2.4 下标 `a[i]`；
    - ¶2.5 类成员访问 `s.m`、`p->m`；
    - ¶2.6 间接 `*p`；
    - ¶2.7 成员指针运算 `s.*pm`、`p->*pm`；
    - ¶2.8 第二、第三操作数都是本列表形式的条件表达式；
    - ¶2.9 右操作数是本列表形式的逗号表达式。
3. 如果（可能已经转换过的）表达式是对象类型的 prvalue，施行临时量实质化转换（[[conv.rval]]）。
4. 求值表达式，丢弃结果。

注 2 说明，上面的列表只针对具有内置含义的运算符。使用重载的运算符就是调用函数，不在其中。

### volatile 读取的清单

volatile 访问是可观察行为（[[intro.abstract]]），程序员需要能准确预测一条语句会不会读内存。典型的场景是读一次硬件状态寄存器来清除某个标志位：

```cpp
volatile unsigned* const STATUS = /* 设备地址 */ nullptr;
void clear_flag() { *STATUS; }   // ¶2.6：间接，读一次
```

清单收录的是语法上明显在指代一个对象的形式。写下名字、`*p`、`a[i]`、`s.m` 的人显然想访问那个对象。赋值 `vi = 1`、前置自增 `++vi` 的结果虽然也是 volatile lvalue，但写下它们的人想要的是写入，再额外读一次就违背直觉了，所以不在清单中。

```cpp ok
void demo(volatile int& vi, int x) {
    vi;              // ¶2.2：读一次
    (void)vi;        // 转换为 void 的操作数是弃值表达式：读一次
    vi = 1;          // 只写一次，不会再读结果
    x ? vi : vi;     // ¶2.8：读一次（只求值其中一个操作数）
    (x, vi);         // ¶2.9：读一次
}
```

用 Clang 23 `-O2 -emit-llvm` 编译这段代码，`vi;`、`(void)vi;`、`x ? vi : vi;`、`(x, vi);` 各产生一条 `load volatile`，`vi = 1;` 只产生一条 `store volatile`。

!!! note "与 C 的差异"
    C 中赋值表达式的结果是一个值而不是 lvalue，`vi = 1;` 之后要不要重新读 `vi` 在 C 里曾有争议。C++ 的赋值结果是 lvalue，而清单里没有赋值，所以明确不会重新读。C++11 之前，`vi;` 是否读取在 C++ 标准里也不明确，C++11 通过 [[CWG1054]] 引入了今天这种列清单的规定。

注 3 指出，如果原来的表达式是类类型的 lvalue，左值到右值转换要用它复制初始化一个临时对象（[[conv.lval]]），这要求类有一个接受 volatile 实参的复制构造函数。隐式声明的复制构造函数的形参是 `const S&`，绑定不了 `volatile S` 的 lvalue：

```cpp error
struct S { int x; };
void f(volatile S& s) {
    s;     // 按标准：需要 S(const volatile S&)，非良构
}
```

截至写作时，Clang 23 不按这条规则诊断上例，只给出 `-Wunused-volatile-lvalue` 警告，也不生成复制。这是实现与条文的分歧，不过这种代码本身几乎没有用处。

### 弃值的 prvalue 会被实质化

按第 3 步，`make();` 中如果 `make` 返回类类型，会实质化一个临时对象，它在完整表达式结束时销毁，所以析构函数必须可用：

```cpp error
struct NoDtor { ~NoDtor() = delete; };
NoDtor make();
void use() {
    make();          // error: 弃值的 prvalue 被实质化，需要析构函数
}
```

这是 C++17 起对象类型的 prvalue 总有结果对象（[[basic.lval#5]] 注 4）在弃值语境下的体现：结果虽然没用，对象也要短暂存在一下。

!!! note "`[[nodiscard]]` 与 `(void)`"
    `[[nodiscard]]`（[[dcl.attr.nodiscard]]）鼓励实现在潜在求值的弃值表达式中调用 nodiscard 函数时给出警告，但显式转换为 `void` 的除外。所以 `(void)f();` 是压制这个警告的惯用写法，它同样是弃值表达式，只是被明确豁免了。

### 与 ODR 的联系

[[basic.def.odr#5]] 规定，变量 `x` 的名字出现在一个弃值表达式的潜在结果中，并且没有对它施行左值到右值转换时，这次出现不构成 odr-use。所以普通变量的 `x;` 不 odr-use `x`；volatile 变量的 `vx;` 要读取它，构成 odr-use。

## 历史与演进

!!! history
    - C++98/03 只说表达式语句的结果被丢弃，volatile lvalue 是否被读取并不明确。
    - C++11 通过 [[CWG1054]] 引入弃值表达式这个术语和 volatile 清单。
    - C++17 随 [[P0135R1]] 的新 prvalue 模型加入了弃值 prvalue 实质化临时对象的规则。
    - C++20 的 [[P1152R4]] 弃用了大量 volatile 用法，其中包括把 volatile 赋值表达式的结果再当作值使用（如 `a = vi = 1`）。弃值的 `vi = 1;` 不受影响（[[expr.assign#5]]）。
    - C++26 的未求值语境加入了反射运算符的操作数，弃值清单加入了拼接表达式。

## 常见误解

!!! pitfall "`typeid` 的操作数从不求值"
    `sizeof(i++)`、`decltype(launch())` 都不求值。但 `typeid(*p)` 中 `*p` 是多态类类型的 lvalue 时会被求值，因为要读取动态类型；`p` 为空时抛出 `std::bad_typeid`。

!!! pitfall "`(void)x` 只是消除警告"
    对普通变量是这样。对 volatile 对象，`(void)status_reg;` 会产生一次真实的硬件读取。只想压制未使用警告时，应该给声明加 `[[maybe_unused]]`。

## 思考题

!!! question "思考题 1"
    设 `volatile int vi;`。`vi += 1;`、`++vi;`、`vi++;`、`(vi, vi);` 各读取 `vi` 几次？

<details markdown="1">
<summary>答案</summary>

- `vi += 1;`：复合赋值要读出旧值再写回，读 1 次。复合赋值不在清单中，弃值语境不会追加读取。
- `++vi;`：等价于 `vi += 1`，读 1 次。
- `vi++;`：读出旧值作为结果并写回新值，读 1 次；结果是 prvalue，不在清单中。
- `(vi, vi);`：左操作数 `vi` 是弃值表达式，读 1 次；整个逗号表达式也是弃值表达式，右操作数是名字，按 ¶2.9 再读 1 次，共 2 次。

另外，C++20 起对 volatile 对象用 `+=`、`++` 已被弃用（C++23 恢复了 `|=`、`&=`、`^=`），这里只讨论读写次数。
</details>

!!! question "思考题 2"
    `struct S { static int n; }; S make(); int k = make().n;` 会调用 `make()` 吗？

<details markdown="1">
<summary>答案</summary>

会。按 [[expr.ref#2]]，`.` 右边是静态成员时，左边的表达式是弃值表达式。它被求值，所以 `make()` 被调用；结果是 prvalue，先实质化再丢弃。这保证了 `obj.static_member` 和 `obj.nonstatic_member` 在左边是否求值这一点上表现一致。
</details>
