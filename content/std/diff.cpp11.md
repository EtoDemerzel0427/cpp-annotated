---
title: C++ 与 ISO C++ 2011 的差异
summary: Annex C.6：从 C++11 升级到 C++14 会遇到的 7 条不兼容——数字分隔符改变宏实参的切分、带大小的 operator delete 成为常规释放函数、条件运算符中 throw 分支不再触发转换、constexpr 成员函数不再隐式 const、带默认成员初始化器的类可以是聚合、gets 删除。逐条给出前后对比与 Clang 23 实测。
status: draft
covers: *
related: diff, diff.cpp14, diff.cpp03, lex.icon, basic.stc, expr.cond, dcl.constexpr, dcl.init.aggr
tags: 附录, 兼容性, 迁移, C++14
updated: 2026-10-18
---

[diff.cpp11] 列出 C++11 → C++14 这一步引入的不兼容。C++14 是一次小版本，只有 7 条，但其中两条很典型：数字分隔符 `'` 改变了**分词**，导致同一段宏调用在两个标准下展开成不同的东西；`constexpr` 成员函数不再隐式 `const`，导致一组重载变成重复声明。

实测环境：Clang 23.1.3，对比 `-std=c++11` 与 `-std=c++14`。

¶1 [diff.cpp11.general]：本小节列出与 ISO C++ 2011 的差异，是在前面各小节所列差异**之外**的部分。

## Clause [lex]：词法约定 {#diff.cpp11.lex}

### ¶1 *pp-number* 可以包含单引号

**受影响小节**：[[lex.ppnumber]]

**改动**：预处理数（[[g:pp-number]]）的文法允许数字之间出现 `'`，作为数字分隔符（`1'000'000`，见 [[lex.icon]]）。

**影响**：C++11 中 `1'2` 是 `1` 后跟一个字符字面量的开头 `'2,3'`。这在宏实参的切分上会造成差别：

```cpp run title="digit_sep.cpp" ok
#include <cstdio>
#define M(x, ...) __VA_ARGS__
int x[2] = { M(1'2,3'4, 5) };
int main() { std::printf("%d %d\n", x[0], x[1]); }
// C++11：'2,3' 是一个字符字面量，M 的实参是 1'2,3'4 与 5，展开为 { 5 }
// C++14：1'2 与 3'4 是两个数，M 的实参是 1'2、3'4、5，展开为 { 3'4, 5 }
```

这个例子在两个标准下**都是良构的**，只是结果不同，属于静默改变。

**Clang 23 实测**：

```text
-std=c++11:  5 0
-std=c++14:  34 5
```


**改写难度**：实际代码中几乎不会出现，无需特别处理。

## Clause [basic]：基础 {#diff.cpp11.basic}

### ¶1 新的常规（非布置）释放函数

**受影响小节**：[[basic.stc.dynamic.deallocation]]

**改动**：`operator delete(void*, std::size_t)` 成为**常规释放函数**（带大小的释放，sized deallocation）。

**理由**：支持带大小的释放：编译器把对象大小传给 `operator delete`，分配器就不必自己记录块大小。

**影响**：C++11 中可以这样声明一对全局的**布置**分配/释放函数：

```cpp
void* operator new(std::size_t, std::size_t);
void operator delete(void*, std::size_t) noexcept;
```

C++11 里第二个声明是与第一个配对的布置释放函数。现在它的签名与预定义的常规 `operator delete(void*, std::size_t)` 相同。如果一个布置 `new` 表达式找到的匹配释放函数恰好是一个常规释放函数，程序非良构（类成员版本一直就是这样，见 [[expr.new]]）。

**Clang 23 实测**：两个声明本身在两种模式下都能编译；问题出在使用处。加上

```cpp
struct T { T(); };
T* f() { return new (8) T; }
```

之后，`-std=c++11` 通过，`-std=c++14` 报 `'new' expression with placement arguments refers to non-placement 'operator delete'`。

**改写难度**：容易。给布置形式换一个不会撞车的标签类型作第二形参。

## Clause [expr]：表达式 {#diff.cpp11.expr}

### ¶1 条件表达式中的 `throw` 分支保留另一分支的类型和值类别

**受影响小节**：[[expr.cond]]

**改动**：条件表达式的第二或第三操作数是 *throw-expression* 时，结果的类型和值类别就是另一个操作数的类型和值类别。C++11 要求对另一个操作数施加左值到右值、数组到指针、函数到指针转换。

**理由**：原来强制的转换（特别是左值到右值转换产生的临时对象）被认为是多余且令人意外的。

```cpp
struct S {
  int x = 1;
  void mf() { x = 2; }
};
int f(bool cond) {
  S s;
  (cond ? s : throw 0).mf();   // C++11：在 s 的副本上调用 mf；现在：在 s 本身上调用
  return s.x;
}
// f(true)：C++11 返回 1，现在返回 2

// sizeof(true ? "" : throw 0)：C++11 为 sizeof(const char*)，现在为 sizeof(const char[1])
```

**Clang 23 实测**：两种模式下 `f(true)` 都返回 2，`sizeof` 都是 1。Clang 把这条作为 DR 回溯到了 C++11。

**改写难度**：只有依赖那份"多余副本"的代码受影响，实际中几乎没有。

## Clause [dcl]：声明 {#diff.cpp11.dcl.dcl}

### ¶1 `constexpr` 非静态成员函数不再隐式 `const`

**受影响小节**：[[dcl.constexpr]]

**改动**：C++11 中 `constexpr` 非静态成员函数隐式是 `const` 成员函数，C++14 取消了这个隐式规则。

**理由**：C++14 放宽了 `constexpr` 函数的限制，允许修改对象，所以 `constexpr` 成员函数需要能修改 `*this`。

```cpp error
struct S {
  constexpr const int& f();   // C++11：隐式 const，即 f() const
  int& f();                   // C++11：与上一个是两个不同的重载
};
// 现在：两个都是非 const 成员函数，只有返回类型不同 → 非良构
```

**Clang 23 实测**：

```text
$ clang++ -std=c++11 ...
warning: 'constexpr' non-static member function will not be implicitly 'const' in C++14; add 'const' to avoid a change in behavior [-Wconstexpr-not-const]
$ clang++ -std=c++14 ...
error: functions that differ only in their return type cannot be overloaded
```

**改写难度**：容易。按 Clang 提示的那样，给原来依赖隐式 `const` 的 `constexpr` 成员函数显式加上 `const`。这样的代码在 C++11 和 C++14 下含义一致。

### ¶2 带默认成员初始化器的类可以是聚合

**受影响小节**：[[dcl.init.aggr]]

**改动**：类有默认成员初始化器（`int m = 1;`）不再妨碍它成为聚合。

**理由**：让聚合初始化也能使用默认成员初始化器。

**影响**：`S b{a}` 从"复制初始化（经用户定义转换）"变成"聚合初始化（第一个成员从 `a` 初始化）"，可能选择不同的转换函数：

```cpp run title="aggr14.cpp" ok
#include <cstdio>
struct S { int m = 1; };   // C++14 起是聚合
struct X {
  operator int() { std::puts("operator int"); return 5; }
  operator S()   { std::puts("operator S");   return S{}; }
};
int main() {
  X a{};
  S b{a};   // C++11：用 operator S 再复制；现在：聚合初始化 b.m = int(a)
  std::printf("b.m=%d\n", b.m);
}
```

**Clang 23 实测**：

```text
-std=c++11:  operator S / b.m=1
-std=c++14:  operator int / b.m=5
```

静默改变。

**改写难度**：需人工审查，但同时提供到类类型和到其首成员类型的转换函数的写法很少见。

## Clause [library]：库引言 {#diff.cpp11.library}

### ¶1 新头文件 `<shared_mutex>`

**受影响小节**：[[headers]]

**改写难度**：容易。

## Clause [input.output]：输入/输出库 {#diff.cpp11.input.output}

### ¶1 不再定义 `gets`

**受影响小节**：[[c.files]]

**改动**：`<cstdio>` 不再声明 `gets`（C11 也已删除它）。

**理由**：`gets` 无法限制读入长度，必然有缓冲区溢出的风险。

**Clang 23 实测**：

```text
$ clang++ -std=c++11 ...
warning: 'gets' is deprecated: This function is provided for compatibility reasons only. ... [-Wdeprecated-declarations]
$ clang++ -std=c++14 ...
error: no type named 'gets' in namespace 'std'
```

（C++11 下的警告来自 macOS SDK 的 C 头文件。）

**改写难度**：容易。`fgets(buf, sizeof buf, stdin)`（注意它保留换行符）或 `std::getline`。

## 小结

| 条目 | 类型 | Clang 23 |
|---|---|---|
| 数字分隔符 | 静默改变 | 已实现 |
| 带大小的 `operator delete` | 非良构 | — |
| `throw` 分支 | 静默改变 | 已实现并回溯 |
| `constexpr` 成员函数不再隐式 `const` | 非良构 | 已实现，C++11 下有预警 |
| 带默认成员初始化器的聚合 | 静默改变 | 已实现 |
| `gets` | 非良构 | 已实现 |
