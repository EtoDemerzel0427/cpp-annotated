---
title: C++ 与 ISO C++ 2026 的差异
summary: C++26 定稿后并入工作草案的三处不兼容改动：带可能抛出异常说明的释放函数、可以指派基类成员的指派初始化、带 cv 或 && 限定的默认化赋值运算符。
status: done
covers: *
related: diff, diff.cpp23, basic.stc.dynamic.deallocation, dcl.init.aggr, dcl.fct.def.default
tags: 附录, 兼容性, 迁移, C++26
updated: 2026-10-19
---

!!! tldr
    - 这一节列出 C++26 定稿后才并入工作草案、会让 C++26 合法代码失效的改动，目前只有三条，下面统一标 {{c++29}}。
    - `operator delete` 不能再声明成可能抛出异常，例如写上 `noexcept(false)`。
    - 指派初始化可以指派聚合基类的成员，原本只匹配一个重载的 `f({.a = 1})` 可能变成歧义。
    - `= default` 的赋值运算符不能再带 `const`、`&&` 限定，移动赋值的形参也不能是 `const T&&`。
    - 截至 Clang 23.1.3，三条都还没有实现，旧代码在 `-std=c++2c` 和 `-std=c++2d` 下照常编译。

三条改动都是原来良构、现在非良构，没有静默改变行为的。Clang 用 `-std=c++2d` 表示 C++26 之后的下一版（`__cplusplus` 为 `202700L`），但这三条在两个模式下都没有生效。

## 释放函数不能声明为可能抛出 [diff.cpp26.basic]

```cpp error
struct T {
  void operator delete(void*) noexcept(false);   // error: 现在非良构；C++26 中良构
};
```

¶1 改动落在 [[basic.stc.dynamic.deallocation]]。**释放函数**（deallocation function）指 `operator delete` 和 `operator delete[]`。它们在 *delete-expression* 中、在构造函数抛出异常后的清理中被调用，C++26 规定释放函数以抛出异常结束时行为未定义。既然能声明的东西用起来必然是 UB，新规则干脆不让声明，条文给出的理由是消除潜在的未定义行为。

释放函数没有写异常说明时，本来就隐式是 `noexcept` 的（[[except.spec]]）。所以受影响的只有显式写了 `noexcept(false)`，或者写了可能求值为 `false` 的 `noexcept(expr)` 的声明。改法是删掉它；如果函数体里真有可能抛出的操作，那本来就是缺陷，需要改成不抛出。

## 指派初始化可以指派基类成员 [diff.cpp26.dcl]

```cpp
struct A { int a; };
struct B : A { int b; };

void f(A);              // #1
void f(B);              // #2

void g() {
  f({.a = 1});          // 现在：#1 与 #2 歧义；C++26：调用 #1
}
```

¶1 改动落在 [[dcl.init]]，规则细节在 [[dcl.init.aggr]]。这是一个新功能：C++17 起聚合可以有基类，但 C++26 的指派初始化只能指派本类的直接非静态数据成员，基类成员只能用位置初始化 `B{{1}, 2}`。现在 `.a` 也可以指派基类 `A` 的成员。

新功能让旧代码失效的方式是重载决议。C++26 中 `{.a = 1}` 只能初始化 `A`，只有 #1 可行。新规则下它也能初始化 `B`，两个候选都需要一次列表初始化转换，没有优劣之分，于是歧义。[[diff.cpp20]] 里 UTF-8 字面量可以初始化 `char` 数组带来的歧义是同一类问题。

本机 Clang 23 在两个模式下都选 #1。编译器实现新规则之前发现不了这个问题；改法是写明类型：`f(A{.a = 1})`。

## 默认化的赋值运算符不能带 cv 或 && 限定

```cpp error
struct S {
  S& operator=(const S&) && = default;      // error: 现在非良构；C++26 中良构
};
struct T {
  T& operator=(const T&) const = default;   // error: 现在非良构；C++26 中良构但被删除
};
struct U {
  U& operator=(const U&&) = default;        // error: 现在非良构；C++26 中良构但被删除
};
```

¶2 改动落在 [[dcl.fct.def.default]]。显式默认化的赋值运算符不能再带 *cv-qualifier-seq* 或 `&&` *ref-qualifier*；显式默认化的移动赋值运算符，形参不能是到 cv 限定的 `T` 的引用。条文给出的理由是移除少见且容易误解的写法。

三种写法在 C++26 中的处境不同：

- `T` 和 `U` 的声明能编译，但类型与隐式声明的赋值运算符不符，函数被定义为删除，任何调用都会报错。新规则只是把静默删除改成了直接报错。
- `S` 的 `&&` 限定版本在 C++26 中可以正常调用，只是只能对右值调用。这是真正被移除的功能，改法是去掉 `&&`，或者写一个用户提供的函数体。

本机 Clang 23 对 `T` 和 `U` 只给出 `-Wdefaulted-function-deleted` 警告（explicitly defaulted ... is implicitly deleted），对 `S` 没有任何诊断。

<details class="fine" markdown="1"><summary>其余条文</summary>

[diff.cpp26.general] ¶1 只说明本小节按正文章节列出与 ISO C++ 2026 的差异。

</details>

## 小结

| 条目 | C++26 | 当前草案 | Clang 23 |
|---|---|---|---|
| `operator delete(void*) noexcept(false)` | 良构 | 非良构 | 未实现 |
| `f({.a = 1})`，重载 `f(A)`、`f(B)`，`B` 派生自 `A` | 调用 `f(A)` | 歧义 | 未实现 |
| 默认化赋值带 `const`、`&&` 或形参为 `const T&&` | 良构（后两种被删除） | 非良构 | 未实现 |
