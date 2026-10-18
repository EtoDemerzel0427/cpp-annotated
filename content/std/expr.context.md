---
title: 上下文依赖
summary: 未求值操作数（sizeof、decltype、noexcept 等的操作数不被求值）与弃值表达式（只为副作用而求值；何时会读取 volatile、何时实质化临时量）
status: draft
related: basic.lval, conv.lval, conv.rval, basic.def.odr, stmt.expr, expr.comma, dcl.type.decltype
tags: 未求值操作数, 弃值表达式, volatile
updated: 2026-10-17
---

同一个表达式写在不同位置，效果可能完全不同：`f()` 写在 `sizeof(f())` 里不会调用 `f`；`x;` 对普通变量什么也不做，对 `volatile` 变量却会产生一次真正的内存读取。[expr.context] 定义了两种特殊语境：

- **未求值操作数**（[[g:unevaluated-operand]]，¶1）：根本不求值；
- **弃值表达式**（[[g:discarded-value-expression]]，¶2）：要求值，但只取其副作用，结果丢弃。

ODR（[[basic.def.odr]]）、临时对象（[[class.temporary]]）、volatile 语义（[[intro.execution]]）等条款都大量引用这两个概念。

## 未求值操作数（¶1）

¶1 某些语境中会出现未求值操作数。当前草案列出的语境包括：

| 语境 | 条款 |
|---|---|
| requires 表达式中的简单要求、复合要求 | [[expr.prim.req.simple]]、[[expr.prim.req.compound]] |
| `typeid` 的操作数（非多态类左值以外的情形） | [[expr.typeid]] |
| `sizeof` 的操作数 | [[expr.sizeof]] |
| `noexcept` 运算符的操作数 | [[expr.unary.noexcept]] |
| 反射运算符 `^^` 的操作数 {{c++26}} | [[expr.reflect]] |
| `decltype` 的操作数 | [[dcl.type.decltype]] |
| requires 子句等模板约束、概念定义中的约束表达式 | [[temp.pre]]、[[temp.concept]] |

（`alignof` 的操作数是类型，不是表达式，所以不在此列。）

!!! std
    An unevaluated operand is not evaluated.

    未求值操作数不会被求值。

注释 1 列出了由此得出的三个推论：

1. 可以不借助对象而命名非静态类成员：`sizeof(S::m)` 是合法的（[[expr.prim.id]]）。
2. 命名对象或函数本身不要求提供定义。未求值操作数中的名字不构成 odr-use（[[basic.def.odr]]），所以 `decltype(f())` 中的 `f` 可以只有声明。`std::declval` 能够只声明不定义，原因就在这里。
3. 未求值操作数被视为一个完整表达式（full-expression）。

```cpp ok
#include <utility>
struct S { int m; static int sm; };   // sm 只声明，从未定义
int g();                              // 只声明，从未定义

auto a = sizeof(g());                 // OK：g 未被调用，也不需要定义
auto b = sizeof(S::m);                // OK：未求值操作数中可以命名非静态成员
auto c = sizeof(S::sm);               // OK：不构成 odr-use
using T = decltype(std::declval<S>().m);   // OK：declval 永远不能被求值

int n = 0;
auto d = sizeof(n++);                 // n 仍然是 0
constexpr bool e = noexcept(g());     // false：g 未声明 noexcept，但并未调用
```

!!! warning "未求值 ≠ 不检查"
    未求值操作数仍然要通过全部的语义检查，重载决议、访问控制、类型完整性（`sizeof` 要求完整类型）等都照常进行。而且 [[class.temporary#1]] 规定，即使临时对象的创建是未求值的，也必须满足如同创建并销毁了它时的全部语义限制（构造函数与析构函数可访问、未被删除）。唯一的例外是 `decltype` 的操作数（[[dcl.type.decltype#2]]）。

    ```cpp error
    struct NoDtor { ~NoDtor() = delete; };
    NoDtor make();
    using T = decltype(make());     // OK：decltype 不引入临时量
    auto s  = sizeof(make());       // error: 未求值，但仍要求析构函数可用
    ```

## 弃值表达式（¶2）

¶2 在有些语境中，表达式只是为了其副作用而出现，这样的表达式称为弃值表达式。常见的弃值语境有：

| 语境 | 条款 |
|---|---|
| 表达式语句 `e;` | [[stmt.expr]] |
| 逗号运算符的左操作数 `e, x` | [[expr.comma]] |
| 转换为 `void`：`(void)e`、`static_cast<void>(e)` | [[expr.static.cast#4]] |
| `for` 语句的第三个子句 | [[stmt.for]]（等价改写为表达式语句） |
| 访问静态成员或枚举项时 `.` 左边的对象表达式：`obj.static_member` | [[expr.ref#2]] |

对弃值表达式，¶2 规定了一个精确的转换流程：

1. 不施行数组到指针、函数到指针转换（所以 `arr;`、`func;` 什么也不做）。
2. 当且仅当表达式是 **volatile 限定类型的 glvalue**，并且是下列形式之一时，施行左值到右值转换（即真的读取一次）：
    - ¶2.1 `( e )`，其中 `e` 是本列表中的形式；
    - ¶2.2 *id-expression*；
    - ¶2.3 拼接表达式 {{c++26}}；
    - ¶2.4 下标 `a[i]`；
    - ¶2.5 类成员访问 `s.m`、`p->m`；
    - ¶2.6 间接 `*p`；
    - ¶2.7 成员指针运算 `s.*pm`、`p->*pm`；
    - ¶2.8 第二、第三操作数都是本列表形式的条件表达式；
    - ¶2.9 右操作数是本列表形式的逗号表达式。
3. 如果（可能经过转换的）表达式是对象类型的 prvalue，施行临时量实质化转换（[[conv.rval]]）。
4. 求值表达式，丢弃其结果（如果有）。

注释 2：上述列表只涉及具有内置含义的运算符；使用重载运算符就是函数调用，不在其中。

### 为什么 volatile 读取要列一个清单

volatile 访问是可观察行为（[[intro.abstract]]），程序员需要能准确预测一条语句会不会产生内存读取。典型的场景是读取一个硬件状态寄存器来清除标志位。

```cpp
volatile unsigned* const STATUS = /* 设备地址 */ nullptr;
void clear_flag() { *STATUS; }   // ¶2.6：间接 → 产生一次读取
```

清单的选择原则是：表达式在语法上看起来就是在指代一个对象。写下名字、`*p`、`a[i]`、`s.m` 的程序员，显然是想访问那个对象。而像赋值 `vi = 1`、前置自增 `++vi` 这样的表达式，虽然结果也是 volatile 左值，但写下它的人想要的是写入，再额外读一次就违背直觉了。

```cpp ok
void demo(volatile int& vi, int x) {
    vi;              // ¶2.2：读一次
    (void)vi;        // 转换到 void 的操作数是弃值表达式：读一次
    vi = 1;          // 只写一次；结果左值不会再被读取（赋值不在清单中）
    x ? vi : vi;     // ¶2.8：读一次（只求值其中一个操作数）
    (x, vi);         // ¶2.9：读一次
}
```

!!! impl "实现视角"
    用 Clang `-O2 -emit-llvm` 编译上面的写法可以验证：`vi;`、`(void)vi;`、`x ? vi : vi;` 各产生一条 `load volatile`，`vi = 1;` 只产生一条 `store volatile`。
    
    Clang 对单独的 `vi;` 会给出 `-Wunused-volatile-lvalue` 警告，提示如果想强制读取，请赋给一个变量。这一警告针对的是可读性，在语义上读取确实会发生。

!!! note "与 C 的差异"
    C 中赋值表达式的结果是一个值（不是左值），`vi = 1;` 是否要重新读取 `vi`，在 C 里曾有争议。C++ 的赋值结果是左值，这条规则明确规定不会重新读取。C++11 之前，`vi;` 这种表达式语句是否读取，标准里也不明确；C++11 通过 [[CWG1054]] 引入了今天这种列清单的规定方式。

### 类类型的 volatile 左值：注释 3

注释 3 指出，如果原表达式是类类型的左值（volatile 限定，属于清单中的形式），左值到右值转换会复制初始化一个临时对象（[[conv.lval#3]] ¶3.2），这要求该类有一个接受 volatile 实参的复制构造函数。隐式声明的复制构造函数的形参是 `const S&`，绑定不了 `volatile S` 左值，所以：

```cpp error
struct S { int x; };
void f(volatile S& s) {
    s;     // 按标准：施行左值到右值转换 → 需要 S(const volatile S&) → 非良构
}
```

!!! impl "Clang 的处理"
    截至写作时，Clang 23 不按此规则诊断上例，只给出 `-Wunused-volatile-lvalue` 警告，也不生成复制。这是实现与条文的分歧，不过这种代码本身几乎没有意义。

### 弃值的 prvalue 会被实质化

按第 3 步，如果 `make` 返回类类型，`make();` 这样的语句会实质化一个临时对象。该对象随后在完整表达式结束时销毁，因此要求析构函数可用：

```cpp error
struct NoDtor { ~NoDtor() = delete; };
NoDtor make();
void use() {
    make();          // error: 弃值的 prvalue 被实质化，需要析构函数
}
```

这也是 C++17 起 prvalue 总有结果对象（[[basic.lval#5]] 注释 4）在弃值语境下的体现：即使结果没有用处，对象也要短暂存在。

!!! note "`[[nodiscard]]` 与弃值"
    `[[nodiscard]]` 属性（[[dcl.attr.nodiscard]]）鼓励实现在潜在求值的弃值表达式中调用 nodiscard 函数时给出警告，除非显式转换为 `void`。所以 `(void)f();` 是压制该警告的惯用写法。它同样是弃值表达式，但标准明确豁免了这种形式。

### 与 ODR 的联系

[[basic.def.odr]] ¶5 规定，如果变量 `x` 出现在一个未施行左值到右值转换的弃值表达式的潜在结果集中，该次出现就不构成 odr-use。所以对普通变量，`x;` 不 odr-use `x`；而对 volatile 变量，`vx;` 会读取它，因此构成 odr-use。

## 历史与演进

!!! history
    - C++98/03：只说表达式语句中表达式的结果被丢弃，volatile 左值是否被读取并不明确。
    - C++11：引入弃值表达式这一术语和 volatile 清单（[[CWG1054]]）。
    - C++17：随着 [[P0135R1]] 的新 prvalue 模型，加入了弃值 prvalue 实质化临时量的规则。
    - C++20：[[P1152R4]] 弃用了大量 volatile 用法，其中包括把 volatile 赋值表达式的结果再用作值（如 `a = vi = 1`）；弃值的 `vi = 1;` 不受影响（[[expr.assign#5]]）。
    - C++26：未求值语境加入了反射运算符的操作数，弃值清单加入了拼接表达式。

## 陷阱

!!! pitfall "`sizeof` 里的副作用不会发生"
    `sizeof(i++)`、`decltype(launch_missiles())` 都不求值。但如果 `*p` 是多态类类型的左值，`typeid(*p)` 会求值（它需要读取动态类型），这时 `p` 为空会抛出 `std::bad_typeid`。这是 `typeid` 与其他未求值语境的区别。

!!! pitfall "`(void)x` 并不能消除 volatile 读取"
    如果只是想让编译器不再警告未使用而写 `(void)status_reg;`，对 volatile 对象会产生一次真实的硬件读取。要对 volatile 对象压制未使用警告，应该用 `[[maybe_unused]]`。

## 思考题

!!! question "1. 下列语句各会对 `vi`（`volatile int vi;`）产生几次读取？`vi += 1;`、`++vi;`、`vi++;`、`(vi, vi);`"

<details markdown="1">
<summary>答案</summary>

- `vi += 1;`：复合赋值需要读出旧值再写回，读 1 次（写 1 次）。复合赋值不在清单中，所以弃值语境不会追加读取。（注：C++20 曾弃用 volatile 的复合赋值，C++23 又恢复了按位复合赋值，此处只讨论读写次数。）
- `++vi;`：前置 `++vi` 等价于 `vi += 1`，读 1 次。
- `vi++;`：后置自增读出旧值作为结果并写回新值，读 1 次；结果是 prvalue，不在清单中。
- `(vi, vi);`：左操作数 `vi` 是弃值表达式，读 1 次；整个逗号表达式又是弃值表达式，右操作数是 *id-expression*，按 ¶2.9 再读 1 次。共 2 次。
</details>

!!! question "2. 为什么 `struct S { static int n; }; S make(); int k = make().n;` 会调用 `make()`？"

<details markdown="1">
<summary>答案</summary>

根据 [[expr.ref#2]]，点运算符右边指代静态成员时，左边的表达式是弃值表达式。它会被求值（所以 `make()` 被调用），结果被丢弃（弃值的 prvalue 实质化后再销毁）。这保证了 `obj.static_member` 与 `obj.nonstatic_member` 在左边是否求值这一点上行为一致。
</details>

## 小结

!!! summary
    | | 未求值操作数 | 弃值表达式 |
    |---|---|---|
    | 是否求值 | 否 | 是，结果丢弃 |
    | 是否 odr-use 其中的名字 | 否 | 通常否（除非施行了左值到右值转换） |
    | 数组/函数到指针 | — | 不施行 |
    | 左值到右值 | — | 仅对 volatile glvalue 且属于清单形式 |
    | prvalue | `decltype` 中不实质化；其他语境仍检查语义限制 | 对象类型的 prvalue 被实质化 |
    | 典型语境 | `sizeof`、`decltype`、`noexcept`、`typeid`（非多态）、requires | 表达式语句、逗号左操作数、`(void)e` |
