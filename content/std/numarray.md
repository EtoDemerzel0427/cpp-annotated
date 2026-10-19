---
title: 数值数组 valarray
summary: valarray 及其四种切片代理：无别名的设计承诺和它带来的前置条件；实现可以返回表达式模板，因而 auto 可能悬垂；长度不等、自我别名、重复下标是 UB；resize 会覆盖全部元素。
status: done
covers: *
related: numeric.requirements, numerics, linalg, simd, views.multidim, basic.lval, dcl.spec.auto, class.temporary
tags: 标准库, valarray, 别名, 表达式模板
updated: 2026-10-19
---

!!! tldr
    - `valarray` 是 C++98 为数值计算设计的一维数组，支持逐元素运算、数学函数和切片。标准保证不同数组的元素互不重叠，实现可以据此做无别名优化。
    - 返回 `valarray` 的运算可以返回表达式模板之类的替代类型，所以 `auto e = a + b;` 可能持有对临时对象的悬垂引用。
    - 从切片代理赋值或复合赋值时，左侧任一元素的值不能依赖左侧另一个元素，否则是 UB；数组与数组的运算要求长度相等。
    - `operator[]` 的非 const 版本对切片、掩码、下标数组返回引用原数组的代理对象，const 版本返回新的 `valarray`。
    - `resize` 会把每个元素都重新赋值，不保留原有元素；`valarray(5, 3)` 是 3 个 5。

## 逐元素运算与切片

```cpp run title="valarray-slices.cpp" ok
#include <cstdio>
#include <valarray>

int main() {
  std::valarray<double> a{1, 2, 3}, b{4, 5, 6};
  std::valarray<double> c = a * b + 1.0;   // {5, 11, 19}
  std::printf("%g %g\n", c.sum(), std::sqrt(c).max());

  std::valarray<char> v0("abcdefghijklmnop", 16);
  std::valarray<char> v1("ABCDE", 5);
  v0[std::slice(2, 5, 3)] = v1;    // 位置 2, 5, 8, 11, 14
  for (char ch : v0) std::putchar(ch);   // abAdeBghCjkDmnEp
  std::putchar('\n');

  std::valarray<int> m{1, -2, 3, -4};
  m[m < 0] = 0;                    // 掩码赋值：{1, 0, 3, 0}
  for (int x : m) std::printf("%d ", x);
}
```

`valarray` 的运算都是逐元素的：`a * b + 1.0` 对每个下标计算一次，`sqrt(c)` 对每个元素开方。切片 `slice(2, 5, 3)` 选出从 2 开始、步长为 3 的 5 个元素，`m < 0` 得到一个 `valarray<bool>` 掩码。中间那段切片赋值是标准在 [valarray.sub] 第 3 段给的例子。

脚注 227 说明了设计意图：用最少的功能解决别名歧义和临时对象泛滥这两个问题，让编译器能像优化 Fortran 数组一样优化它。今天它用得不多：没有 `push_back`，没有分配器，与标准算法配合不顺。多维数值计算现在更常用 `mdspan`（[[views.multidim]]）配合 [[linalg]]，向量化有 [[simd]]。但它关于别名的几条规则，很好地展示了库如何用前置条件换取优化空间。

## 无别名承诺

¶2 [valarray.syn] 说，`valarray` 被定义为不存在某些形式的别名，从而允许优化对它的运算。具体承诺在 [valarray.access]：

- ¶3 `addressof(a[i + j]) == addressof(a[i]) + j`，元素连续存储；
- ¶4 对任意两个数组 `a`、`b`，`addressof(a[i]) != addressof(b[j])`。注释点明这表示不存在别名，编译器可以借此做内联、常量传播、循环融合等优化。

效果相当于给每个 `valarray` 的存储加上了 C 的 `restrict`：编译器看到 `a[i] = b[i] + c[i]` 时可以假定写 `a` 不会改变 `b`、`c`，从而向量化。

¶4 也意味着复制得到的是一个不同的数组。脚注 230 允许实现让数组共享存储，但这样的实现必须在访问时复制，保证各个数组在概念上互不相同。

¶5 `operator[]` 返回的引用在调用 `resize` 或数组生命周期结束之前一直有效。按第 1 段，下标必须小于 `size()`，这是一条加固前置条件（[[g:hardened-precondition]]）{{c++26}}：加固实现会检查它，其他情况下越界是 UB。

## 表达式模板与 auto（[valarray.syn] ¶3–¶5）

¶3 任何返回 `valarray<T>` 的函数，都允许返回另一个类型的对象，只要 `valarray<T>` 除 `begin`、`end` 以外的所有 const 成员函数也适用于这个类型。这个替代类型相对最深的实参类型，增加的模板嵌套不得超过两层。

¶4–¶5 引入替代类型的实现，必须为每个接受 `const valarray<T>&` 的函数提供接受替代类型的版本，并允许用替代类型构造 `valarray`、给 `valarray` 和四种代理赋值。

这条规则是为**表达式模板**（expression template）开的口子：`a + b * c` 不立即计算，而是返回一个记录了运算结构的轻量对象，赋值给 `valarray` 时才在一个循环里逐元素求值，省掉中间的临时数组。libc++ 就是这样实现的。

问题在于这种对象按引用持有操作数：

```cpp run title="valarray-auto.cpp" ub
#include <valarray>

std::valarray<int> make(int k) { return std::valarray<int>(k, 3); }

int main() {
  auto e = make(1) + make(2);   // libc++：e 引用两个临时数组
  return e[0];                  // UB：临时数组已经销毁
}
```

两个临时数组在完整表达式结束时销毁（[[class.temporary]]），而 `auto` 推导出的表达式对象还活着。本机用 `-fsanitize=address` 运行，报告 stack-use-after-scope。标准允许替代类型引用操作数，所以悬垂是程序的问题。

即使操作数不是临时对象，结果也可能出人意料：`auto e = w + w; w[0] = 99;` 之后读 `e[0]`，本机得到 198，读到的是修改之后的值。对策是明确写出结果类型 `std::valarray<int> e = …;`，让它当场求值。

## 构造与赋值（[valarray.cons]、[valarray.assign]）

<div class="compare" markdown="1">

```cpp ok
#include <valarray>
// 值在前，个数在后：{5, 5, 5}
std::valarray<int> a(5, 3);
```

```cpp ok
#include <valarray>
// 列表初始化：{5, 3}
std::valarray<int> b{5, 3};
```

</div>

构造函数有：默认构造（长度 0）；`explicit valarray(size_t n)`，n 个值初始化的元素；`valarray(const T& v, size_t n)`，参数顺序与 `vector(n, v)` 相反；`valarray(const T* p, size_t n)`，要求 `[p, p + n)` 是有效范围；复制、移动；`initializer_list`；以及从四种代理的转换构造。`T` 必须是数值类型（[[numeric.requirements]]）。

¶1–¶3 复制赋值在长度不同时先调整长度再赋值。¶8 `operator=(const T&)` 把标量赋给每个元素。

¶10 从四种代理赋值时，前置条件有两条：代理所引用的长度等于 `size()`；左侧任何元素的值不依赖左侧另一个元素的值。第二条是无别名承诺的另一面，它让实现可以按任意顺序甚至并行地赋值。右侧通过代理引用了左侧自己的其他元素时，结果就取决于赋值顺序：

```cpp run title="valarray-self-alias.cpp" ub
#include <cstdio>
#include <valarray>

int main() {
  std::valarray<int> v{1, 2, 3, 4};
  // UB：v[0] 的新值依赖 v[3]，……
  v = v[std::valarray<std::size_t>{3, 2, 1, 0}];
  for (int x : v) std::printf("%d ", x);   // 本机：4 3 3 4
}
```

要原地反转，先复制一份：`v = std::valarray<int>(v[idx]);`。

## 子集运算与代理类

¶1 [valarray.sub] `operator[]` 有四对重载，分别接受 `slice`、`gslice`、`valarray<bool>`（掩码）、`valarray<size_t>`（下标数组）。const 版本复制被选中的元素，返回新的 `valarray`；非 const 版本返回代理对象 `slice_array<T>`、`gslice_array<T>`、`mask_array<T>`、`indirect_array<T>`，它们引用原数组的元素。

四种代理的结构完全相同：默认构造函数被删除，只能由 `operator[]` 创建或复制已有的代理；有 `operator=(const valarray<T>&)`、十个复合赋值和一个把标量赋给所有选中元素的 `operator=(const T&)`。这些赋值运算符都是 const 成员，因为代理本身不变，变的是它引用的数组。

**`slice(start, length, stride)`**（[class.slice]）描述从 `start` 开始、每隔 `stride` 取一个、共 `length` 个的下标序列，与 BLAS 的切片相同。`slice(3, 8, 2)` 选中 3, 5, 7, …, 17。

**`gslice`**（[class.gslice]）是广义切片：由起点 s、一组长度 lⱼ 和同样个数的一组步长 dⱼ 定义，把多维下标 (i₀, i₁, …) 映射为 s + Σ iⱼ·dⱼ，最后一个下标变化最快。它用一维 `valarray` 模拟多维数组，作用与 `layout_stride`（[[views.multidim]]）类似。按 [class.gslice.overview] 第 4–6 段，广义切片可能是退化的，即同一个下标出现多次，例如把步长都设成 1。把退化切片用于非 const 的 `operator[](const gslice&)` 是 UB，因为通过它赋值时同一元素会被写多次。

**`mask_array`** 选中掩码为真的元素。**`indirect_array`** 按下标数组的顺序选中元素。[indirect.array.assign] ¶2 和 [indirect.array.comp.assign] ¶2 规定，下标数组中同一个元素出现多次时，赋值或复合赋值是 UB。第 3 段的标准例子中下标 `{2, 3, 1, 4, 4}` 里 4 出现了两次。

## 其他运算

### 复合赋值（[valarray.cassign]）

与数组的复合赋值要求（第 2 段） `size() == v.size()`，并且与代理赋值一样要求左侧元素互不依赖。与复制赋值不同，`a += b` 不会调整长度，长度不同是 UB。与标量的复合赋值没有长度要求。

### 二元运算和比较（[valarray.binary]、[valarray.comparison]）

数组与数组、数组与标量、标量与数组；数组与数组时要求长度相同。比较运算返回 `valarray<bool>`，所以 `a == b` 不是判断两个数组是否相等，而是逐元素比较的掩码。要得到一个 `bool`，可以写 `(a == b).min()`，前提是数组非空。

### 数学函数（[valarray.transcend]）

`abs`、`exp`、`sqrt`、`pow`、`atan2` 等。*Mandates* 要求存在唯一的同名函数能以非限定方式应用于 `T`，所以它们通过 ADL 找到用户类型的数学函数。

### 成员函数（[valarray.members]）



| 成员 | 要点 |
|---|---|
| `sum` | 要求 `size() > 0`；以未指明的顺序用 `+=` 累加，浮点结果可能随实现不同 |
| `min`、`max` | 要求 `size() > 0`；用 `operator<` 比较 |
| `shift(n)` | 返回左移 n 位（n 为负则右移）、空位补 `T()` 的新数组 |
| `cshift(n)` | 循环移位 |
| `apply(f)` | 返回逐元素应用 `f` 的新数组 |
| `resize(sz, c = T())` | 改变长度，然后把每个元素都赋为 `c`；使所有指针和引用失效 |

!!! pitfall "resize 不保留已有元素"
    `std::valarray<int> r{1, 2, 3}; r.resize(5);` 之后 `r` 是 `{0, 0, 0, 0, 0}`，不是 `{1, 2, 3, 0, 0}`。[valarray.members] 第 16 段写的是改变长度，然后给每个元素赋第二个实参的值。这与 `vector::resize` 完全不同。

### 迭代器（[valarray.range]）

当前草案中 `valarray` 有成员类型 `iterator`、`const_iterator` 和成员函数 `begin()`、`end()`，迭代器建模 `contiguous_iterator`，在 `resize` 或数组生命周期结束之前有效。这是 C++23 之后的新措辞，此前只有非成员的 `std::begin(v)` 和 `std::end(v)`，返回类型未指明。本机 libc++ 仍是旧形式：`std::begin(v)` 可用，`v.begin()` 不能编译。

<details class="fine" markdown="1"><summary>其余条文</summary>

[valarray.syn] ¶1 列出头文件定义的五个类模板、两个类和一系列函数模板。第 6 段：这些函数在资源不足时可以抛出 `bad_alloc`，但不是必须。脚注 226 把模板嵌套层数的限制与 [implimits] 中对模板递归深度的建议联系起来。

[valarray.unary]：一元 `+ - ~ !` 要求运算符适用于 `T`，返回 `T`（`!` 返回 `bool`）或可无歧义地转换为它。

[valarray.cassign] ¶5、¶9：数组出现在复合赋值左侧，不会使指向其元素的引用或指针失效。

[valarray.members]：`swap` 常数时间且 `noexcept`；`size` 常数时间。

[cons.slice] ¶1、[gslice.cons] ¶1：默认构造的 `slice` 等价于 `slice(0, 0, 0)`，存在的目的是能声明切片的数组。`slice` 支持 `==`。

</details>
