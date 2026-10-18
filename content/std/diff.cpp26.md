---
title: C++ 与 ISO C++ 2026 的差异
summary: Annex C.1：C++26 发布后并入工作草案、会破坏 C++26 合法代码的三处改动——抛异常的释放函数非良构、聚合基类的指派初始化引入重载歧义、显式默认化的赋值运算符不得带 cv/&& 限定。附例子与 Clang 23 实测（均未实现）。
status: draft
covers: *
related: diff, diff.cpp23, basic.stc, dcl.init.aggr, dcl.fct.def
tags: 附录, 兼容性, 迁移, C++26
updated: 2026-10-18
---

[diff.cpp26] 是当前工作草案相对 **C++26** 的不兼容清单，是 [[diff]] 里最新的一节。它只有三条，都来自 C++26 定稿之后并入草案的改动，所以下面统一标 {{c++29}}（指"C++26 之后的下一版"）。

三条都是"原来良构、现在非良构"，没有静默改变行为的条目。截至 Clang 23.1.3，三条都**没有实现**：用 `-std=c++2c` 和 `-std=c++2d`（Clang 为下一版预留的模式，`__cplusplus` 为 `202700L`）编译，旧代码照常通过。

¶1 [diff.cpp26.general] 只有一句话：本小节按正文章节列出与 ISO C++ 2026 的差异。

## Clause [basic] {#diff.cpp26.basic}

### ¶1 释放函数不得带"可能抛出"的异常说明

**受影响小节**：[[basic.stc.dynamic.deallocation]]

**改动**：声明一个带**可能抛出**（potentially-throwing）异常说明的释放函数（`operator delete` / `operator delete[]`）是非良构的。

**理由**：消除潜在的未定义行为。释放函数在 *delete-expression*、构造失败时的清理等场合被调用，这些地方大多处在 `noexcept` 上下文或析构过程中；在当前规则下，释放函数抛出异常导致的是 UB，而不是一个有意义的错误处理路径。与其保留一个"能声明但不能用"的形式，不如直接禁止。

**对旧代码的影响**：

```cpp error
struct T {
  void operator delete(void*) noexcept(false);   // error: 现在非良构；C++26 中良构
};
```

释放函数默认就是 `noexcept` 的（[[except.spec]] 对释放函数的隐式异常说明），所以只有**显式**写了 `noexcept(false)` 或带可能为 false 的 `noexcept(expr)` 的声明会受影响。

**Clang 23 实测**：`-std=c++2c` 与 `-std=c++2d` 下都没有任何诊断，尚未实现。

**改写难度**：容易。删掉 `noexcept(false)`；如果释放函数里真有可能抛出的操作，那本来就是 bug，需要改成不抛出（记录日志、`std::terminate`）。

## Clause [dcl] {#diff.cpp26.dcl}

### ¶1 聚合的基类可以用指派初始化，导致重载歧义

**受影响小节**：[[dcl.init]]（具体规则在 [[dcl.init.aggr]]）

**改动**：*designated-initializer* 可以指派聚合**基类**中的成员（C++26 只能指派本类的直接非静态数据成员）。

**理由**：新功能。C++17 起聚合可以有基类（见 [[diff.cpp14]] [dcl.init.aggr] 一条），但指派初始化一直无法触及基类成员，只能退回到位置初始化 `{{1}, 2}`。

**对旧代码的影响**：指派初始化器参与重载决议时，原来只能匹配一个候选的列表，现在可能同时匹配多个：

```cpp
struct A { int a; };
struct B : A { int b; };

void f(A);              // #1
void f(B);              // #2

void g() {
  f({.a = 1});          // 现在：#1 与 #2 之间有歧义；C++26：调用 #1
}
```

在 C++26 中，`{.a = 1}` 只能初始化 `A`（`B` 没有名叫 `a` 的直接成员），所以只有 #1 可行。新规则下 `.a` 也可以指派 `B` 的基类 `A` 的成员，两个转换都是用户定义的列表初始化转换序列，没有优劣之分，于是歧义。这是一个"新功能让旧的唯一解变成多解"的典型例子，与 [[diff.cpp20]] 里 UTF-8 字面量初始化 `char` 数组导致的歧义同一类。

**Clang 23 实测**：`-std=c++2c` 与 `-std=c++2d` 下都选 #1，没有歧义，新规则尚未实现。

**改写难度**：容易，但只有编译器实现之后才能发现。给实参写明类型：`f(A{.a = 1})`。

### ¶2 显式默认化的赋值运算符不得带 cv 或 `&&` 限定

**受影响小节**：[[dcl.fct.def.default]]

**改动**：显式默认化（`= default`）的赋值运算符不能带 *cv-qualifier-seq*，也不能带 `&&` *ref-qualifier*；显式默认化的移动赋值运算符的形参不能是"到 cv 限定 `T` 的引用"。

**理由**：移除少见且令人困惑的写法。这些写法在 C++26 中要么"良构但被定义为删除"（`const` 限定、`const T&&` 形参），要么良构但语义奇怪（`&&` 限定的默认赋值只能对右值调用）。

**对旧代码的影响**：

```cpp error
struct S {
  S& operator=(const S&) && = default;       // error: 现在非良构；C++26 中良构
};
struct T {
  T& operator=(const T&) const = default;    // error: 现在非良构；C++26 中良构但被删除
};
struct U {
  U& operator=(const U&&) = default;         // error: 现在非良构；C++26 中良构但被删除
};
```

注意 `T` 和 `U` 在 C++26 里虽然能编译，但这两个赋值运算符是**被删除**的，任何使用都会报错；真正会改变的只是"声明本身"从被静默删除变成直接报错。只有 `S` 那种 `&&` 限定、在 C++26 中确实可用的写法，才是实打实的功能移除。

**Clang 23 实测**：

```text
$ clang++ -std=c++2d -fsyntax-only -Wall c26c.cpp
c26c.cpp:2:15: warning: explicitly defaulted copy assignment operator is implicitly deleted [-Wdefaulted-function-deleted]
c26c.cpp:3:15: warning: explicitly defaulted move assignment operator is implicitly deleted [-Wdefaulted-function-deleted]
```

`T` 和 `U` 只得到"被隐式删除"的警告，`S` 没有任何诊断。新规则尚未实现。

**改写难度**：容易。`T`、`U` 的声明本来就无用，删掉即可；`S` 去掉 `&&`，或者改成用户提供的函数体。

## 小结

| 条目 | 旧行为（C++26） | 新行为 | Clang 23 |
|---|---|---|---|
| `operator delete(void*) noexcept(false)` | 良构 | 非良构 | 未实现 |
| `f({.a = 1})` 在 `f(A)` / `f(B : A)` 间 | 调用 `f(A)` | 歧义 | 未实现 |
| 默认化赋值带 `const` / `&&` / `const T&&` | 良构（部分被删除） | 非良构 | 未实现 |
