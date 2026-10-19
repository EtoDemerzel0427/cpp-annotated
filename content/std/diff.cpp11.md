---
title: C++ 与 ISO C++ 2011 的差异
summary: 从 C++11 升级到 C++14 时，哪些原来合法的代码会报错或改变行为：数字分隔符改变宏实参的切分、带大小的 operator delete 成为常规释放函数、条件运算符的 throw 分支、constexpr 成员函数不再隐式 const、带默认成员初始化器的聚合、gets 删除。
status: done
covers: *
related: diff, diff.cpp14, diff.cpp03, lex.icon, basic.stc, expr.cond, dcl.constexpr, dcl.init.aggr
tags: 附录, 兼容性, 迁移, C++14
updated: 2026-10-19
---

!!! tldr
    - C++14 只有 7 条不兼容，大多数只在刻意构造的代码里出现。
    - 最可能真正碰到的是 `constexpr` 非静态成员函数不再隐式是 `const` 的：依赖这个隐式 `const` 的重载会变成重复声明。
    - 数字分隔符 `'` 改变了分词，同一个宏调用在两个标准下可以展开成不同的结果。
    - 带默认成员初始化器的类可以是聚合，`S b{a};` 可能改用另一个转换函数，结果静默改变。
    - `gets` 被删除；`operator delete(void*, std::size_t)` 成为常规的释放函数，与它同签名的自定义布置释放函数会出问题。

[diff.cpp11] 列出 C++14 相对 C++11 的不兼容：原来良构的代码，在 C++14 中变成非良构，或者含义改变。每一条在标准里都写成同样的格式：受影响的条款、改了什么、为什么改、对旧代码有什么影响。

¶1 这一节列的是在前面各节之外的差异：从 C++11 升级到当前草案，还要再看 [[diff.cpp14]] 及之后各节。条目按正文的章节顺序排列。文中的实测都用本机 Clang 23.1.3，对比 `-std=c++11` 与 `-std=c++14`。

## 词法约定 [diff.cpp11.lex] {#diff.cpp11.lex}

### 数字分隔符改变宏实参的切分

```cpp run title="digit_sep.cpp" ok
#include <cstdio>
#define M(x, ...) __VA_ARGS__
int x[2] = { M(1'2,3'4, 5) };
// C++11：int x[2] = { 5 };
// C++14：int x[2] = { 3'4, 5 };
int main() { std::printf("%d %d\n", x[0], x[1]); }
```

¶1 C++14 允许在数字之间写单引号作分隔符，例如 `1'000'000`（[[lex.icon]]）。为此，预处理阶段的数字记号，即**预处理数**（[[g:pp-number]]），可以包含单引号（[[lex.ppnumber]]）。

C++11 中，`1'2,3'4` 里的 `'2,3'` 是一个字符字面量，所以 `M` 的实参是 `1'2,3'4` 和 `5`，展开为 `{ 5 }`。C++14 中 `1'2` 和 `3'4` 是两个数，实参变成三个，展开为 `{ 3'4, 5 }`。两种结果都是良构的，只是含义不同，编译器不会提示。

本机运行，`-std=c++11` 输出 `5 0`，`-std=c++14` 输出 `34 5`。实际代码中几乎不会这样写。

## 基础 [diff.cpp11.basic] {#diff.cpp11.basic}

### 带大小的 `operator delete` 成为常规释放函数

```cpp
void* operator new(std::size_t, std::size_t);         // 布置分配函数
void operator delete(void*, std::size_t) noexcept;    // C++11：与之配对的布置释放函数
                                                       // C++14：与常规释放函数同签名

struct T { T(); };
T* f() { return new (8) T; }   // error: C++11 中良构
```

¶1 C++14 引入了带大小的释放：`delete p` 时编译器把对象大小一并传给 `operator delete(void*, std::size_t)`，分配器就不必自己记录每块内存的大小（[[basic.stc.dynamic.deallocation]]）。这个函数因此成为一个**常规释放函数**，即 `delete` 表达式会调用的那一类，而不是只在布置 `new` 构造失败时才调用的布置释放函数。

C++11 中，上例的第二个声明是与第一个布置分配函数配对的布置释放函数。C++14 中它与预定义的常规释放函数同签名。布置 `new` 表达式在构造函数抛出异常时要调用与之配对的释放函数，如果找到的恰好是一个常规释放函数，程序非良构；类成员版本一直就是这个规则（[[expr.new]]）。

Clang 23 在 `-std=c++14` 下对 `new (8) T` 报错，提示带布置实参的 `new` 引用了非布置的 `operator delete`。修正方法是给这对布置函数换一个不会撞车的第二形参类型，比如一个自定义的标签类型。

## 表达式 [diff.cpp11.expr] {#diff.cpp11.expr}

### 条件表达式中的 `throw` 分支

```cpp
struct S {
  int x = 1;
  void mf() { x = 2; }
};
int f(bool cond) {
  S s;
  (cond ? s : throw 0).mf();   // C++14：在 s 本身上调用；C++11：在 s 的副本上
  return s.x;
}
// f(true)：C++14 返回 2，C++11 返回 1
// sizeof(true ? "" : throw 0)：C++14 是 sizeof(const char[1])，C++11 是 sizeof(const char*)
```

¶1 条件表达式 `c ? a : b` 的一个分支是 throw 表达式时，C++14 规定结果的类型和值类别就是另一个分支的类型和值类别（[[expr.cond]]）。C++11 则要求先对另一个分支做左值到右值、数组到指针、函数到指针的转换，于是左值 `s` 变成了一个临时副本，`""` 退化成了指针。这些转换，尤其是左值到右值转换产生的那个临时对象，被认为既多余又出人意料。

Clang 23 把这条当作缺陷修正，`-std=c++11` 下也是新行为：`f(true)` 返回 2，`sizeof` 的结果是 1。只有依赖那份多余副本的代码受影响，实际中几乎没有。

## 声明 [diff.cpp11.dcl.dcl] {#diff.cpp11.dcl.dcl}

### `constexpr` 成员函数不再隐式 `const`

<div class="compare" markdown="1">

```cpp error
struct S {
  constexpr const int& f();
  int& f();   // error
};
```

```cpp ok
struct S {
  constexpr const int& f() const;
  int& f();   // OK
};
```

</div>

¶1 C++11 中，`constexpr` 非静态成员函数隐式就是 `const` 成员函数，C++14 取消了这条隐式规则（[[dcl.constexpr]]）。C++14 允许 `constexpr` 函数修改对象，`constexpr` 成员函数也就需要能修改 `*this`，不能再一律是 `const` 的。

左边在 C++11 中声明了两个不同的重载：一个 `const`，一个非 `const`。C++14 中两个都是非 `const` 成员函数，只有返回类型不同，程序非良构。按右边那样给原来依赖隐式 `const` 的函数显式写上 `const`，在两个标准下含义一致。

Clang 23 在 `-std=c++11` 下就会给出 `-Wconstexpr-not-const` 警告，提示加上 `const`；`-std=c++14` 下报错。

### 带默认成员初始化器的类可以是聚合

```cpp run title="aggr14.cpp" ok
#include <cstdio>
struct S { int m = 1; };   // C++14 起是聚合
struct X {
  operator int() { std::puts("operator int"); return 5; }
  operator S()   { std::puts("operator S");   return S{}; }
};
int main() {
  X a{};
  S b{a};   // C++14：聚合初始化，b.m 由 int(a) 初始化
            // C++11：经 operator S 再复制
  std::printf("b.m=%d\n", b.m);
}
```

¶2 C++11 中，有默认成员初始化器（如 `int m = 1;`）的类不是**聚合**，C++14 取消了这个限制（[[dcl.init.aggr]]），让聚合初始化也能使用默认成员初始化器。

于是 `S b{a}` 从复制初始化（先用 `operator S` 把 `a` 转换成 `S`）变成了聚合初始化（用 `a` 初始化第一个成员 `m`，经 `operator int`）。本机运行，`-std=c++11` 输出 `operator S` 和 `b.m=1`，`-std=c++14` 输出 `operator int` 和 `b.m=5`。结果静默改变，但同时提供到类类型和到它首个成员类型的转换函数的写法很少见。

## 库引言 [diff.cpp11.library] {#diff.cpp11.library}

¶1 C++14 新增头文件 `<shared_mutex>`（[[headers]]）。项目里有同名头文件并用 `#include <...>` 包含时，可能拿到标准库的版本。

## 输入/输出库 [diff.cpp11.input.output] {#diff.cpp11.input.output}

¶1 C++14 不再定义 `gets`（[[c.files]]），C11 也已删除它。`gets` 无法限制读入的长度，输入一长就会写出缓冲区。改用 `fgets(buf, sizeof buf, stdin)`（注意它会保留换行符）或 `std::getline`。本机 `-std=c++11` 下有一条来自 macOS SDK 头文件的弃用警告，`-std=c++14` 下 `std::gets` 不存在。

## 小结

| 条目 | 旧代码的结局 | Clang 23 |
|---|---|---|
| 数字分隔符 | 宏展开结果改变 | 已实现 |
| 带大小的 `operator delete` | 非良构 | 已实现 |
| `throw` 分支 | 结果改变 | 已实现，C++11 模式同样处理 |
| `constexpr` 成员函数不再隐式 `const` | 非良构 | 已实现，C++11 下警告 |
| 带默认成员初始化器的聚合 | 结果改变 | 已实现 |
| `gets` | 非良构 | 已删除 |
