---
title: 表达式
summary: 第 7 章导读：表达式的性质、标准转换、各类运算符（按语法推导出的优先级排列）与常量求值是如何组织起来的
status: draft
related: expr.pre, basic.lval, conv, expr.arith.conv, topics/value-categories
tags: 表达式, 导读
updated: 2026-10-17
---

第 7 章 [expr] 是整本标准里篇幅最大、被引用最多的一章之一。几乎所有"这段代码是什么意思"的问题，最后都会落到这里：一个表达式**是什么类型**、**是什么值类别**、**求值时做了哪些隐式转换**、**什么时候是 UB**、**能不能在编译期求值**。

读这一章之前，最好先熟悉第 6 章的几个概念：对象与生命周期（[[basic.life]]）、类型的分类与转换等级（[[basic.types]]、[[conv.rank]]）、求值顺序与"先序于"（[[intro.execution]]）、odr-use（[[basic.def.odr]]）。

## 本章的组织方式

第 7 章的结构是"先总则、再分则"，而分则部分基本上**按语法从紧到松**（即优先级从高到低）排列：

| 小节 | 内容 | 本站笔记 |
|---|---|---|
| 7.1 | 序言：表达式、运算符重载与内置运算符的关系、算术表达式的 UB | [[expr.pre]] |
| 7.2 | 表达式的性质：值类别、类型调整、上下文（未求值操作数、弃值表达式） | [[expr.prop]]、[[basic.lval]]、[[expr.type]]、[[expr.context]] |
| 7.3 | 标准转换：左值到右值、数组到指针、临时量实质化、限定转换、整型提升…… | [[conv]] |
| 7.4 | 寻常算术转换 | [[expr.arith.conv]] |
| 7.5 | 初等表达式：字面量、`this`、名字、lambda、折叠表达式、requires 表达式、拼接表达式 | [[expr.prim]] |
| 7.6 | 复合表达式：后缀 → 一元 → 强制转换 → 成员指针 → 乘法 → … → 逗号 | [[expr.compound]] |
| 7.7 | 常量求值：核心常量表达式、常量初始化、立即函数、反射相关的常量求值 | [[expr.const]] |

前四节（7.1–7.4）是"横切"的规则：后面每个运算符的描述里都会说"对操作数施行左值到右值转换""施行寻常算术转换"，这些术语的定义都在这里。所以 7.2–7.4 是阅读后面所有运算符条款的前置知识。

## 标准里没有优先级表

很多人第一次翻标准时会找"运算符优先级表"——找不到。[[expr.pre]] 的脚注明确说：运算符的优先级并没有直接规定，而是**从语法推导出来的**。

!!! std
    The precedence of operators is not directly specified, but it can be derived from the syntax.

    优先级不是独立规定的，而是语法的推论。

具体做法是：每一级运算符都对应一个语法非终结符，它的操作数是**更紧一级**的非终结符。例如：

```text
additive-expression:
    multiplicative-expression
    additive-expression + multiplicative-expression
    additive-expression - multiplicative-expression
```

`+` 的右操作数只能是 *multiplicative-expression*，所以 `a + b * c` 只能解析为 `a + (b * c)`；左操作数是 *additive-expression* 本身（左递归），所以 `a - b - c` 只能解析为 `(a - b) - c`——这就是"左结合"。右结合的运算符（赋值、条件、一元）则写成右递归。

### 从语法推导出的优先级表

下表从高到低排列，每一行对应一个语法非终结符（C++26 草案）：

| 级别 | 非终结符 | 运算符 / 形式 | 结合性 | 条款 |
|---|---|---|---|---|
| 1 | *primary-expression* | 字面量、`this`、`( e )`、*id-expression*、lambda、折叠表达式、requires 表达式、`[: r :]` | — | [[expr.prim]] |
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
| 16 | *conditional-expression* / *assignment-expression* | `?:` `=` `op=` `throw` `co_yield` | 右 | [[expr.cond]]、[[expr.assign]]、[[expr.throw]]、[[expr.yield]] |
| 17 | *expression* | `,` | 左 | [[expr.comma]] |

几点只有看语法才能看清楚的细节：

- **一元运算符的操作数是 *cast-expression***，所以 `-(int)x`、`!(bool)p` 都能直接写；但 `sizeof` 的操作数是 *unary-expression*，于是 `sizeof (int)x` 被解析成 `sizeof(int)` 后面跟着一个多余的 `x`，是语法错误。
- **条件运算符的三个操作数不对称**：第一个是 *logical-or-expression*，第二个是任意 *expression*（可以含逗号），第三个是 *assignment-expression*。因此 `c ? a : b = x` 解析为 `c ? a : (b = x)`，而不是 C 里那样的 `(c ? a : b) = x`（C 中这其实是错误）。
- **赋值的左操作数是 *logical-or-expression***：`a = b ? c : d` 中 `?:` 先结合；`a ? b : c = d` 见上一条。
- **`throw` 与 `co_yield` 是 *assignment-expression***：所以 `cond ? x : throw std::runtime_error("…")` 合法，但 `throw` 不能作为 `+` 的操作数而不加括号。
- 同一级的 `?:` 与 `=` 没有"谁比谁高"的问题：它们都是右递归，`a = b ? c : d = e` 解析为 `a = (b ? c : (d = e))`。

```cpp run title="grammar.cpp" ok
#include <cstdio>
int a = 1, b = 2, c = 3;

int f(bool q) {
    q ? a : b = c;            // 解析为 q ? a : (b = c)
    int x = -(int)2.5;        // 一元 - 的操作数是 cast-expression：x == -2
    int y = q ? 1 : throw 0;  // throw-expression 可作 ?: 的第三操作数
    return x + y;
}

int main() {
    int r = f(true);          // q 为真：b 不被赋值，也不会抛出
    std::printf("%d %d\n", b, r);   // 打印 2 -1
}
```

```cpp error
int x;
auto s = sizeof (int)x;     // error: sizeof 的操作数是 unary-expression，不是 cast-expression
```

!!! pitfall "优先级 ≠ 求值顺序"
    优先级（更准确地说：语法结构）只决定**操作数怎么分组**，不决定**谁先求值**。`f() + g() * h()` 中三个调用之间的顺序由 [[intro.execution#10]] 决定（未定序，即 unsequenced——对函数调用而言是"不确定定序"），与 `*` 比 `+` 优先无关。C++17 起，少数运算符（`<<`、`>>`、`=`、`[]`、`->*`、`.*`、函数调用的后缀表达式等）增加了定序保证，见 [[expr.pre]] 的"历史与演进"。

## 运算符重载如何嵌入这套规则

第 7 章只描述**内置运算符**（built-in operator）的含义。当某个操作数是类类型或枚举类型时，表达式 `a @ b` 会先经过重载决议（[[over.match.oper]]）：候选包括成员 `operator@`、非成员 `operator@`、以及 [[over.built]] 列出的内置候选。选中用户定义函数时，表达式被改写为函数调用（[[over.oper]]），此时：

- **语法不变**：优先级、结合性、操作数个数都沿用内置运算符（你不能让重载的 `+` 比 `*` 优先）。
- **求值顺序沿用内置运算符**（C++17 起，[[over.match.oper#2]]）：例如重载的 `<<` 仍然保证左操作数先于右操作数。
- **操作数的类型、值类别要求改由函数参数决定**：内置 `=` 要求左操作数是可修改左值，但 `operator=` 是成员函数，可以在右值上调用。
- **运算符之间的恒等关系不再保证**：内置的 `++a` 等价于 `a += 1`，重载的则没有这种保证。

详见 [[expr.pre#2]] 与 [[expr.pre#3]] 的释义。

## 建议的阅读路线

1. 先读 [[basic.lval]]（值类别）和 [[topics/value-categories]]：这是理解后面所有"结果是左值还是纯右值"表述的钥匙。
2. 再读 [[conv]]，重点是左值到右值转换、临时量实质化、限定转换。
3. 然后读 [[expr.arith.conv]]：几乎所有二元算术/比较运算符都引用它。
4. 剩下的运算符条款可以按需查阅；遇到常量表达式问题时读 [[expr.const]]。

!!! summary "小结"
    - 第 7 章 = 横切规则（7.1–7.4）+ 按优先级排列的各运算符（7.5–7.6）+ 常量求值（7.7）。
    - 标准没有优先级表，优先级和结合性都由语法推导；记住几个"不对称"的位置（`sizeof`、`?:` 的第二/第三操作数、赋值左操作数）。
    - 重载运算符继承语法与求值顺序，但不继承类型/值类别要求与运算符间的恒等式。
