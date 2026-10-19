---
title: 表达式
summary: 第 7 章的结构：表达式的性质、标准转换、按优先级排列的各类运算符和常量求值；标准没有优先级表，优先级和结合性都由语法推导出来。
status: draft
related: expr.pre, basic.lval, conv, expr.arith.conv, topics/value-categories
tags: 表达式, 导读
updated: 2026-10-19
---

!!! tldr
    - 第 7 章先给出贯穿全章的规则（值类别、标准转换、寻常算术转换），再按优先级从高到低逐个描述运算符，最后讲常量求值。
    - 标准里没有运算符优先级表。每一级运算符对应一个语法非终结符，优先级和结合性都由语法推导出来。
    - 语法里有几处不对称：`sizeof (int)x` 是语法错误，`c ? a : b = x` 是 `c ? a : (b = x)`，`throw` 可以作 `?:` 的操作数。
    - 优先级只决定操作数怎样分组，不决定谁先求值。
    - 重载的运算符沿用内置运算符的语法和求值顺序，但不沿用对操作数类型、值类别的要求。

一个表达式是什么类型、是什么值类别、求值时做了哪些隐式转换、什么时候是 UB、能不能在编译期求值，这些问题的答案大多在第 7 章。它也依赖第 6 章的几个概念：对象与生命周期（[[basic.life]]）、类型（[[basic.types]]）、求值顺序（[[intro.execution]]）和 odr 使用（[[basic.def.odr]]）。

## 本章的组织

| 小节 | 内容 | 本站笔记 |
|---|---|---|
| 7.1 | 序言：表达式、重载运算符与内置运算符的关系、算术表达式的 UB | [[expr.pre]] |
| 7.2 | 表达式的性质：值类别、类型调整、未求值操作数、弃值表达式 | [[expr.prop]]、[[basic.lval]]、[[expr.type]]、[[expr.context]] |
| 7.3 | 标准转换：左值到右值、数组到指针、临时量实质化、限定转换、整型提升等 | [[conv]] |
| 7.4 | 寻常算术转换 | [[expr.arith.conv]] |
| 7.5 | 初等表达式：字面量、`this`、名字、lambda、折叠表达式、requires 表达式、拼接 | [[expr.prim]] |
| 7.6 | 复合表达式：后缀、一元、强制转换、成员指针、乘法……一直到逗号 | [[expr.compound]] |
| 7.7 | 常量求值：核心常量表达式、常量初始化、立即函数 | [[expr.const]] |

7.2–7.4 是后面所有运算符条款的基础。每个运算符的描述里都会说对操作数施行左值到右值转换、施行寻常算术转换、结果是左值还是纯右值，这些术语都在这几节定义。其中值类别另有专题 [[topics/value-categories]]。

## 优先级由语法推导

标准里找不到运算符优先级表。[[expr.pre]] 的脚注 33 说明了原因：

!!! std
    The precedence of operators is not directly specified, but it can be derived from the syntax.

每一级运算符对应一个语法非终结符，它的操作数是更紧一级的非终结符。例如加法：

```text
additive-expression:
    multiplicative-expression
    additive-expression + multiplicative-expression
    additive-expression - multiplicative-expression
```

`+` 的右操作数只能是 *multiplicative-expression*，所以 `a + b * c` 只能解析为 `a + (b * c)`。左操作数是 *additive-expression* 本身（左递归），所以 `a - b - c` 只能解析为 `(a - b) - c`，这就是左结合。右结合的运算符（赋值、条件、一元）写成右递归。

### 推导出的优先级表

下表从高到低排列，每一行对应一个非终结符：

| 级别 | 非终结符 | 运算符或形式 | 结合性 | 条款 |
|---|---|---|---|---|
| 1 | *primary-expression* | 字面量、`this`、`( e )`、名字、lambda、折叠表达式、requires 表达式、`[: r :]` | | [[expr.prim]] |
| 2 | *postfix-expression* | `a[b]` `f(args)` `T(args)` `T{args}` `a.b` `a->b` `a++` `a--` `*_cast<T>(e)` `typeid` | 左 | [[expr.post]] |
| 3 | *unary-expression* | `*a` `&a` `+a` `-a` `!a` `~a` `++a` `--a` `co_await` `sizeof` `alignof` `noexcept` `new` `delete` `^^` | 右 | [[expr.unary]] |
| 3′ | *cast-expression* | `(T) e` | 右 | [[expr.cast]] |
| 4 | *pm-expression* | `.*` `->*` | 左 | [[expr.mptr.oper]] |
| 5 | *multiplicative-expression* | `*` `/` `%` | 左 | [[expr.mul]] |
| 6 | *additive-expression* | `+` `-` | 左 | [[expr.add]] |
| 7 | *shift-expression* | `<<` `>>` | 左 | [[expr.shift]] |
| 8 | *compare-expression* | `<=>` | 左 | [[expr.spaceship]] |
| 9 | *relational-expression* | `<` `>` `<=` `>=` | 左 | [[expr.rel]] |
| 10 | *equality-expression* | `==` `!=` | 左 | [[expr.eq]] |
| 11 | *and-expression* | `&` | 左 | [[expr.bit.and]] |
| 12 | *exclusive-or-expression* | `^` | 左 | [[expr.xor]] |
| 13 | *inclusive-or-expression* | `\|` | 左 | [[expr.or]] |
| 14 | *logical-and-expression* | `&&` | 左 | [[expr.log.and]] |
| 15 | *logical-or-expression* | `\|\|` | 左 | [[expr.log.or]] |
| 16 | *conditional-expression*、*assignment-expression* | `?:` `=` `op=` `throw` `co_yield` | 右 | [[expr.cond]]、[[expr.assign]]、[[expr.throw]]、[[expr.yield]] |
| 17 | *expression* | `,` | 左 | [[expr.comma]] |

### 只有看语法才看得清的几处

```cpp run title="grammar.cpp" ok
#include <cstdio>
int a = 1, b = 2, c = 3;

int f(bool q) {
    q ? a : b = c;            // 解析为 q ? a : (b = c)
    int x = -(int)2.5;        // 一元 - 的操作数是 cast-expression：x == -2
    int y = q ? 1 : throw 0;  // throw 表达式可以作 ?: 的第三个操作数
    return x + y;
}

int main() {
    int r = f(true);          // q 为真：b 不被赋值，也不抛出
    std::printf("%d %d\n", b, r);   // 打印 2 -1
}
```

- 一元运算符的操作数是 *cast-expression*，所以 `-(int)x`、`!(bool)p` 可以直接写。但 `sizeof` 的操作数是 *unary-expression*，`sizeof (int)x` 会被解析成 `sizeof(int)` 后面多出一个 `x`，是语法错误。
- 条件运算符的三个操作数不对称：第一个是 *logical-or-expression*，第二个是任意 *expression*（可以含逗号），第三个是 *assignment-expression*。所以 `c ? a : b = x` 解析为 `c ? a : (b = x)`。C 的语法不同，同一行代码在 C 里解析为 `(c ? a : b) = x`，并因为结果不是左值而报错。
- 赋值的左操作数是 *logical-or-expression*，右侧是右递归，所以 `a = b ? c : d = e` 解析为 `a = (b ? c : (d = e))`。
- `throw` 和 `co_yield` 是 *assignment-expression*，所以 `cond ? x : throw std::runtime_error("…")` 合法；但不加括号时，`throw` 不能作 `+` 的操作数。

<div class="compare" markdown="1">

```cpp run ok
int x;
auto s = sizeof (int) + x;
// sizeof(int) 加上 x
```

```cpp run error
int x;
auto s = sizeof (int)x;
// error: sizeof 的操作数
// 不能是 cast-expression
```

</div>

!!! pitfall "优先级决定求值顺序"
    优先级只决定操作数怎样分组，不决定谁先求值。`f() + g() * h()` 中三个调用的先后由 [[intro.execution]] 决定，标准没有规定，与 `*` 比 `+` 优先无关。C++17 起，`<<`、`>>`、赋值、`[]`、`.*`、`->*` 和函数调用的被调函数部分有了先后保证，见 [[expr.pre]] 的历史一节。

## 重载运算符怎样融入这套规则

第 7 章描述的是**内置运算符**（built-in operator）的含义。操作数是类类型或枚举类型时，`a @ b` 先经过重载决议（[[over.match.oper]]），候选包括成员 `operator@`、非成员 `operator@` 和 [[over.built]] 列出的内置候选。选中用户定义的函数时，表达式改写为函数调用（[[over.oper]]），这时语法和求值顺序沿用内置运算符，操作数的类型和值类别要求改由函数形参决定，`++a` 等价于 `a += 1` 这类恒等关系不再保证。详细规则见 [[expr.pre]]。

## 小结

!!! summary
    - 第 7 章分三部分：贯穿全章的规则（7.1–7.4），按优先级排列的运算符（7.5–7.6），常量求值（7.7）。
    - 标准没有优先级表，优先级和结合性都由语法推导；要记住 `sizeof`、`?:` 的第二和第三个操作数、赋值的左操作数这几处不对称。
    - 优先级决定分组，不决定求值顺序。
    - 重载运算符沿用语法和求值顺序，不沿用类型、值类别要求和运算符之间的恒等关系。
