---
title: 数值数组 valarray
summary: valarray 及其四种切片代理（slice_array、gslice_array、mask_array、indirect_array）——"无别名"的设计承诺与它给实现的优化空间；允许返回表达式模板这一替代类型规则及 auto 悬垂陷阱；各运算的长度相等前置条件、"左侧元素不得相互依赖"的别名前置条件、重复下标与退化 gslice 的 UB；resize 会覆盖全部元素；加固的 operator[]
status: done
covers: *
related: numeric.requirements, numerics, linalg, simd, views.multidim, basic.lval, dcl.spec.auto
tags: 标准库, valarray, 别名, 表达式模板
updated: 2026-10-18
---

`valarray` 是 C++98 为数值计算设计的一维数组：逐元素的算术运算（`a * b + c`）、数学函数（`sqrt(a)`）、以及类似 Fortran 90 的切片（`a[slice(0, n, 2)] = …`）。它的核心设计目标写在脚注 227 里：用**最少的功能**来解决**别名歧义**和**临时对象泛滥**这两个问题，从而让编译器能像优化 Fortran 数组那样优化它。

今天它用得不多：没有成员 `push_back`、没有分配器、与标准算法和范围的配合一直不顺，表达式模板实现带来的 `auto` 陷阱也令人头疼。多维数值计算现在更常用 `mdspan`（[[views.multidim]]）配合 [[linalg]]，向量化则有 [[simd]]。但它的规范里有几条关于别名的规则，对理解"库如何用前置条件换取优化空间"很有代表性。这一页按主题讲，不逐个罗列四种代理类的每个运算符。

## 头文件与"无别名"承诺（[valarray.syn]）

¶1：`<valarray>` 定义五个类模板（`valarray`、`slice_array`、`gslice_array`、`mask_array`、`indirect_array`）、两个类（`slice`、`gslice`）和一系列函数模板。

¶2：`valarray` 数组类被定义为**不存在某些形式的别名**，从而允许对它们的运算进行优化。具体的承诺分散在 [valarray.access] 里（见下文）：不同数组的元素地址互不相同。这相当于给每个 `valarray` 的存储隐式加上了 C 的 `restrict` 语义——编译器看到 `a[i] = b[i] + c[i]` 时可以假定写 `a` 不会改变 `b`、`c`，从而向量化、融合循环。

### 替代类型：表达式模板（¶3–¶5）

¶3：任何返回 `valarray<T>` 的函数，**允许**返回另一个类型的对象，只要 `valarray<T>` 除 `begin`/`end` 外的所有 const 成员函数都适用于该类型。这个替代类型相对最深的实参类型，增加的模板嵌套不得超过两层（脚注 226：联系 [implimits] 中对模板递归深度的建议）。

¶4–¶5：引入这种替代类型的实现，必须为每个接受 `const valarray<T>&` 的函数提供接受替代类型的版本（两个参数时要覆盖所有组合），并允许用替代类型构造和赋值给 `valarray<T>` 及四种代理类。

这条规则就是为**表达式模板**开的口子：`a + b * c` 不立即计算，而是返回一个记录了"加法节点(a, 乘法节点(b, c))"的轻量对象，等到赋值给 `valarray` 时才在一个循环里逐元素求值，省去中间临时数组。libc++ 正是这样实现的（内部类型 `__val_expr`）。

!!! pitfall "auto 与表达式模板：悬垂引用"
    表达式模板对象按**引用**持有操作数。如果操作数是临时对象，临时对象在完整表达式结束时销毁（[[class.temporary]]），而 `auto` 推导出的表达式对象还活着：

    ```cpp run title="valarray-auto.cpp" ub
    #include <valarray>

    std::valarray<int> make(int k) { return std::valarray<int>(k, 3); }

    int main() {
      auto e = make(1) + make(2);   // libc++：e 是表达式对象，引用两个已销毁的临时数组
      return e[0];                  // UB：读已结束生命周期的对象
    }
    ```

    本机用 `-fsanitize=address` 运行，报告 stack-use-after-scope。标准层面，`auto` 推导出的类型是"实现选择的替代类型"，¶3 允许它引用操作数，于是悬垂是程序的问题而不是实现的问题。对策：结果一律写明类型 `std::valarray<int> e = …;`，强制当场求值。即使操作数不是临时对象，`auto e = a + b; a[0] = 99; e[0]` 读到的也是修改**之后**的值——这与 `valarray` 对象的值语义直觉不符。

¶6：这些库函数在资源不足时**允许**抛出 `bad_alloc`，但不是必须。

## valarray 类（[template.valarray]）

### 概述与构造（[template.valarray.overview]、[valarray.cons]）

`valarray<T>` 是一维的"智能数组"，元素从 0 开始编号；更高维度靠计算下标和广义切片模拟。`T` 必须是数值类型（[[numeric.requirements]]）。

构造函数（¶1–¶10）：默认（长度 0）；`explicit valarray(size_t n)`（n 个值初始化元素）；`valarray(const T& v, size_t n)`（**注意参数顺序：值在前、个数在后**，与 `vector(n, v)` 相反）；`valarray(const T* p, size_t n)`（前置条件：`[p, p + n)` 是有效范围）；复制、移动（常数复杂度）；`initializer_list`；以及从四种代理类的转换构造。

```cpp title="valarray-ctor-order.cpp" ok
#include <valarray>

std::valarray<int> a(5, 3);    // 3 个 5：{5, 5, 5}
std::valarray<int> b{5, 3};    // 两个元素：{5, 3}
```

### 赋值（[valarray.assign]）

- ¶1–¶3：复制赋值在长度不同时先 `resize(v.size())` 再赋值。
- ¶8：`operator=(const T&)` 把标量赋给每个元素。
- ¶10：从四种代理类赋值时，*Preconditions*：代理所引用的长度等于 `size()`；**并且左侧任何元素的值不依赖于左侧另一个元素的值**。

第二个前置条件是 ¶2"无别名"承诺的另一面：实现可以按任意顺序（包括并行）逐元素赋值。如果右侧通过代理引用了左侧自身的其他元素，结果就取决于赋值顺序。

```cpp run title="valarray-self-alias.cpp" ub
#include <cstdio>
#include <valarray>

int main() {
  std::valarray<int> v{1, 2, 3, 4};
  v = v[std::valarray<std::size_t>{3, 2, 1, 0}];   // UB：v[0] 的新值依赖 v[3]，……
  for (int x : v) std::printf("%d ", x);           // 本机 libc++ 输出 4 3 3 4，而不是 4 3 2 1
}
```

想"原地反转"，要先复制：`v = std::valarray<int>(v[idx]);`，或者对 const 数组下标（const 版本直接返回新的 `valarray`）。

### 元素访问（[valarray.access]）

- ¶1 *Hardened preconditions* {{c++26}}：`n < size()`。在加固实现中越界被检查（[[g:hardened-precondition]]），否则是 UB。
- ¶2：返回对应元素的引用；注释：`(a[i] = q, a[i]) == q` 恒为真。
- ¶3：`addressof(a[i + j]) == addressof(a[i]) + j`——元素**连续存储**。
- ¶4：对任意两个数组 `a`、`b`，`addressof(a[i]) != addressof(b[j])`。注释点明：这表示不存在别名，优化编译器可以利用它（内联、常量传播、循环融合、追踪从 `operator new` 得到的指针等）。
- ¶5：返回的引用在调用 `resize` 或数组生命周期结束前一直有效。

¶4 看似显然，其实是一条对实现的约束：它禁止 `valarray` 用写时复制或共享存储来实现"按值复制"（脚注 228 也说，共享存储的实现必须做到"概念上不同"）。

### 子集运算（[valarray.sub]）

¶1：`operator[]` 有四对重载，分别接受 `slice`、`gslice`、`valarray<bool>`（掩码）、`valarray<size_t>`（下标数组）。**const 版本返回新的 `valarray`**（复制被选元素），**非 const 版本返回代理对象**（`slice_array<T>` 等），它引用原数组的元素，配合其 `operator=`、复合赋值运算符实现"选择性替换"。无论哪种，被选中的元素都必须存在。

```cpp run title="valarray-slices.cpp" ok
#include <cstdio>
#include <valarray>

int main() {
  std::valarray<char> v0("abcdefghijklmnop", 16);
  std::valarray<char> v1("ABCDE", 5);
  v0[std::slice(2, 5, 3)] = v1;            // 位置 2, 5, 8, 11, 14
  for (char c : v0) std::putchar(c);       // abAdeBghCjkDmnEp
  std::putchar('\n');

  std::valarray<int> m{1, -2, 3, -4};
  m[m < 0] = 0;                            // 掩码赋值：{1, 0, 3, 0}
  for (int x : m) std::printf("%d ", x);
}
```

（这正是 ¶3 的标准例子。）

### 一元运算与复合赋值（[valarray.unary]、[valarray.cassign]）

- 一元 `+ - ~ !`：*Mandates*：运算符可用于 `T` 并返回 `T`（`!` 返回 `bool`）或可无歧义地隐式转换为它。
- 与数组的复合赋值（¶1–¶5）：*Mandates*：运算符可用于两个 `T`；*Preconditions*：`size() == v.size()`，**并且**与 ¶10 相同的"左侧元素互不依赖"要求。¶5：出现在复合赋值左侧不会使引用或指针失效。
- 与标量的复合赋值（¶6–¶9）：无长度要求。

注意数组复合赋值的长度前置条件：与复制赋值不同，`a += b` 不会自动调整长度，长度不同是 UB。

### 范围访问（[valarray.range]）

当前草案中，`valarray` 有成员类型 `iterator`/`const_iterator` 和成员函数 `begin()`/`end()`：迭代器满足 *Cpp17RandomAccessIterator* 并建模 `contiguous_iterator`，`value_type` 为 `T`，引用类型为 `T&`/`const T&`（¶1）；在 `resize` 或数组生命周期结束前有效（¶2）。这是 C++23 之后的新措辞——此前标准只提供非成员的 `std::begin(valarray&)`/`std::end`，返回类型未指明。本机 libc++ 仍是旧形式：`std::begin(v)` 可用，`v.begin()` 不能编译。

### 成员函数（[valarray.members]）

| 成员 | 要点 |
|---|---|
| `swap` | 常数复杂度，`noexcept` |
| `size` | 常数时间 |
| `sum` | *Preconditions*：`size() > 0`；用 `+=` 以**未指明的顺序**累加——浮点结果可能随实现不同 |
| `min`、`max` | *Preconditions*：`size() > 0`；用 `operator<` 比较 |
| `shift(n)` | 返回左移 n 位（n 为负则右移）、空位补 `T()` 的新数组 |
| `cshift(n)` | 循环移位 |
| `apply(f)` | 返回逐元素应用 `f` 的新数组；`f` 是 `T(T)` 或 `T(const T&)` 函数指针 |
| `resize(sz, c = T())` | 改变长度，**然后把每个元素都赋为 `c`**；使所有指针和引用失效 |

!!! pitfall "resize 不保留已有元素"
    `std::valarray<int> r{1, 2, 3}; r.resize(5);` 之后 `r` 是 `{0, 0, 0, 0, 0}`，而不是 `{1, 2, 3, 0, 0}`。¶16 写的是"改变长度，然后对每个元素赋第二个实参的值"。这与 `vector::resize` 完全不同。

## 非成员运算（[valarray.nonmembers]）

- 二元算术与位运算（[valarray.binary]）：数组 op 数组、数组 op 标量、标量 op 数组。*Mandates*：运算符可用于 `T` 并返回 `T` 或可无歧义转换为 `T`；数组与数组时 *Preconditions*：长度相同。
- 逻辑与比较运算（[valarray.comparison]）：返回 `valarray<bool>`，数组与数组时同样要求长度相同。所以 `a == b` **不是**"两个数组相等吗"，而是逐元素比较的掩码；要得到 `bool` 需要 `(a == b).min()` 之类的写法（且要求非空）。
- 超越函数（[valarray.transcend]）：`abs`、`exp`、`sqrt`、`pow`、`atan2` 等；*Mandates*：存在唯一的同名函数，能以**非限定**方式应用于 `T`。这意味着它们靠 ADL 找到用户类型的数学函数。
- `swap`（[valarray.special]）。

## 切片与代理类

### slice 与 slice_array（[class.slice]、[template.slice.array]）

`slice(start, length, stride)` 描述"从 start 开始、每隔 stride 取一个、共 length 个"的下标序列（BLAS 风格，脚注 231）；默认构造等价于 `slice(0, 0, 0)`，只为了能声明 `slice` 数组。`slice(3, 8, 2)` 选中 3, 5, 7, …, 17。`slice` 支持 `==`。

`slice_array<T>` 由 `valarray<T>::operator[](slice)` 创建（默认构造函数被删除，用户无法凭空构造，只能复制已有的代理），对所选元素具有**引用语义**：赋值、复合赋值、填充都作用于原数组。

### gslice 与 gslice_array（[class.gslice]、[template.gslice.array]）

¶1–¶2：广义切片由起点 s、一组长度 lⱼ 和同样个数的一组步长 dⱼ 定义，把多维下标 (i₀, i₁, …) 映射为 k = s + Σ iⱼ·dⱼ；最高序（最后一个）的下标变化最快。这是用一维 `valarray` 模拟多维数组的工具——作用与 `layout_stride` 映射（[[views.multidim]]）类似。

¶4–¶6：可能出现**退化**的广义切片，同一个地址出现多次（例如把步长都设为 1）。把退化切片用于**非 const** 的 `operator[](const gslice&)`，行为未定义——因为通过它赋值时同一元素会被写多次，结果取决于顺序。

### mask_array 与 indirect_array

- `mask_array<T>`（[template.mask.array]）：`a[mask]` 选中 `mask[i]` 为真的元素。
- `indirect_array<T>`（[template.indirect.array]）：`a[idx]` 选中下标数组中列出的元素，顺序按 `idx`。[indirect.array.assign] ¶2 与 [indirect.array.comp.assign] ¶2：若下标数组中同一个元素出现多次，赋值或复合赋值的行为**未定义**。¶3 的标准例子：`{2, 3, 1, 4, 4}` 中 4 出现两次，`a[indirect] = b` 是 UB。

四种代理类的结构完全平行：默认构造函数被删除、有复制构造函数；`operator=(const valarray<T>&) const`、十个复合赋值 `const` 成员；以及标题为"Fill function"的 `operator=(const T&) const`（把一个标量赋给所有选中元素）。它们的赋值运算符都是 `const` 成员——代理本身不变，变的是它引用的数组。

## 小结

| 规则 | 出处 | 后果 |
|---|---|---|
| 不同数组元素地址不同；元素连续 | [valarray.access] ¶3–¶4 | 实现可按无别名优化 |
| 返回 `valarray` 的函数可返回替代类型 | [valarray.syn] ¶3 | 表达式模板；`auto` 可能悬垂 |
| 代理赋值/复合赋值：左侧元素互不依赖 | [valarray.assign] ¶10、[valarray.cassign] ¶2 | 否则 UB |
| 数组与数组的运算长度必须相同 | [valarray.binary]、[valarray.cassign] | 否则 UB（复制赋值除外，它会 resize） |
| `operator[]` 越界 | [valarray.access] ¶1 | 加固前置条件 |
| 退化 gslice 用于非 const 下标；indirect 重复下标赋值 | [class.gslice.overview] ¶6、[indirect.array.assign] ¶2 | UB |
| `resize` | [valarray.members] ¶16 | 覆盖全部元素，使引用失效 |
| `sum`/`min`/`max` | ¶6–¶10 | 要求非空；`sum` 累加顺序未指明 |
