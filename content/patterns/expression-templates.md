---
title: 表达式模板
summary: 让 a + b + c 在一个循环里算完、不产生临时向量：运算符返回记录运算结构的轻量对象，赋值时才逐元素求值；用概念限定运算符，处理 auto 悬垂和别名问题，并与 valarray、ranges 的 zip_transform、std::linalg 和 Eigen 对照。
status: draft
order: 80
since: c++98
papers: P2321R2, P1673R13
related: over.match.oper, over.match.viable, class.temporary, valarray.syn, numarray, range.zip.transform, range.all.general, linalg, topics/dangling-references, topics/concepts, topics/ranges-design, history/template-metaprogramming, patterns/crtp
tags: 表达式模板, 运算符重载, 惰性求值, 悬垂, 别名, 惯用法
updated: 2026-10-19
---

!!! tldr
    - 按值返回的 `operator+` 让 `x = a + b + c` 产生一个临时向量、走两遍循环。表达式模板让 `+` 只返回一个记录"左操作数、右操作数、运算"的小对象，赋值时用一个循环逐元素算完。
    - 表达式的结构编码在类型里：`a + b * c` 的类型是 `Binary<plus, Vec, Binary<multiplies, Vec, Vec>>`。内联之后，这棵类型树在 -O2 下变成一个向量化的循环。
    - 运算符模板必须用概念限定，而且最好是选择加入式的概念。按结构判断（有 `operator[]` 和 `size()`）的概念会把 `std::vector` 也卷进来。
    - 表达式对象引用着操作数。`auto e = a + b + c;` 会留下悬垂引用，连内层的表达式节点都是临时对象；`x = …` 写成一个完整表达式才安全。
    - 逐元素运算里 `a = b + a` 没有问题，矩阵乘法 `a = a * b` 却会读到已经写入的元素。标准允许 `valarray` 用表达式模板（libc++ 就是这样做的），C++26 的 `<linalg>` 改用函数调用并把别名写成前置条件。

## 每个 + 都分配一次

```cpp run title="naive.cpp" ok
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <vector>

int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Vec {
  std::vector<double> d;
  explicit Vec(std::size_t n) : d(n) {}
  std::size_t size() const { return d.size(); }
  double& operator[](std::size_t i) { return d[i]; }
  double operator[](std::size_t i) const { return d[i]; }
};

Vec operator+(const Vec& a, const Vec& b) {
  Vec r(a.size());                       // 每个 + 分配一次
  for (std::size_t i = 0; i < a.size(); ++i)
    r[i] = a[i] + b[i];
  return r;
}

int main() {
  Vec a(1000), b(1000), c(1000), x(1000);
  allocs = 0;
  x = a + b + c;
  std::printf("allocations: %d\n", allocs);  // 2
}
```

`x = a + b + c` 按 `(a + b) + c` 求值。第一个 `+` 分配一个临时向量 `t` 并走一遍循环，第二个 `+` 再分配一个结果向量、再走一遍循环，最后移动赋值给 `x`。本机 -O0 和 -O2 都打印 2。

除了分配，中间结果 `t` 先写进内存，下一个循环再读出来。如果向量比缓存大，这一写一读就是额外的内存流量。手写的循环只有一行：`x[i] = a[i] + b[i] + c[i]`，没有分配，只走一遍。

给 `operator+` 加一个接受 `Vec&&` 的重载，就地复用左边临时对象的缓冲区，可以把分配降到一次，但循环仍然是两遍。要做到和手写循环一样，`+` 就不能立即计算。

## 一步一步写出表达式模板

**表达式模板**（expression template）的做法是：运算符不计算结果，而是返回一个记录了操作数和运算种类的对象；这个对象可以像向量一样按下标取元素，取到哪个元素才计算哪个。真正的循环只在赋值时出现一次。

```cpp run title="et.cpp" ok
#include <cstddef>
#include <cstdio>
#include <functional>
#include <type_traits>
#include <vector>

namespace la {

template <class T>
constexpr bool enable_vec_expr = false;      // 选择加入：默认不是表达式

template <class E>
concept vec_expr = enable_vec_expr<std::remove_cvref_t<E>>;

class Vec {
  std::vector<double> d_;
public:
  explicit Vec(std::size_t n) : d_(n) {}
  std::size_t size() const { return d_.size(); }
  double& operator[](std::size_t i) { return d_[i]; }
  double operator[](std::size_t i) const { return d_[i]; }

  template <vec_expr E>
  Vec(const E& e) : d_(e.size()) { assign(e); }
  template <vec_expr E>
  Vec& operator=(const E& e) { assign(e); return *this; }

private:
  template <class E>
  void assign(const E& e) {                  // 唯一的循环（假定长度相等）
    for (std::size_t i = 0; i < d_.size(); ++i)
      d_[i] = e[i];
  }
};

template <class Op, class L, class R>
struct Binary {                              // 一个尚未计算的 l op r
  const L& l;
  const R& r;
  std::size_t size() const { return l.size(); }
  double operator[](std::size_t i) const {
    return Op{}(l[i], r[i]);                 // 用到哪个元素才算哪个
  }
};

template <>
constexpr bool enable_vec_expr<Vec> = true;
template <class Op, class L, class R>
constexpr bool enable_vec_expr<Binary<Op, L, R>> = true;

template <vec_expr L, vec_expr R>
Binary<std::plus<>, L, R> operator+(const L& l, const R& r) {
  return {l, r};
}
template <vec_expr L, vec_expr R>
Binary<std::multiplies<>, L, R> operator*(const L& l, const R& r) {
  return {l, r};
}

} // namespace la

int main() {
  la::Vec a(3), b(3), c(3), x(3);
  for (std::size_t i = 0; i < 3; ++i) { a[i] = i; b[i] = 10 * i; c[i] = 100; }
  x = a + b * c;                             // 一个循环，没有临时 Vec
  std::printf("%g %g %g\n", x[0], x[1], x[2]);  // 0 1001 2002
}
```

程序分三部分，下面逐一说明。

### 第一步：运算符返回一个描述

`Binary<Op, L, R>` 是表达式树的一个节点。它保存对两个操作数的引用，`operator[]` 在被调用时才对第 `i` 个元素做运算。操作数既可以是 `Vec`，也可以是另一个 `Binary`，所以节点可以层层嵌套。

`b * c` 返回 `Binary<multiplies<>, Vec, Vec>`，`a + (b * c)` 返回 `Binary<plus<>, Vec, Binary<multiplies<>, Vec, Vec>>`。表达式的形状完整地写在类型里：模板实参推导把每个操作数的类型记进了 `L` 和 `R`。运算种类用空的函数对象类型 `Op` 表示，节点里不存它，`sizeof` 只有两个引用，本机为 16 字节。

### 第二步：赋值触发唯一的循环

`Vec` 有一个接受任意表达式的构造函数模板和赋值运算符模板，二者都调用 `assign`。`x = a + b * c` 里，`assign` 的循环体对每个 `i` 调用一次 `e[i]`，`e[i]` 再递归调用两个子节点的 `operator[]`，最后落到 `Vec::operator[]` 读取元素。所有这些函数都很小，内联之后循环体就是 `x[i] = a[i] + b[i] * c[i]`。

这个赋值运算符模板不会取代复制赋值。`x = y`（`y` 是 `Vec`）时，两者都是精确匹配，非模板函数优先于函数模板的特化（[[over.match.best#2.4]]），仍然走隐式声明的复制赋值。

### 第三步：用概念限定运算符

`operator+` 的两个形参类型都由推导决定。如果不加限制，它会接受任何类型。下面的库省掉了约束，用户代码用了一个 using 指令：

```cpp run title="hijack.cpp" error
#include <cstddef>

namespace la {
template <class L, class R>
struct Sum {
  const L& l;
  const R& r;
  double operator[](std::size_t i) const { return l[i] + r[i]; }
};
template <class L, class R>               // 没有约束
Sum<L, R> operator+(const L& l, const R& r) { return {l, r}; }
}

using namespace la;
enum Color { red, green, blue };

int main() {
  int n = green + 1;                       // error: Sum<Color, int> 不能转换为 int
  return n;
}
```

`green + 1` 有一个枚举类型的操作数，所以要做重载决议（[[over.match.oper#2]]）。候选里有内置的 `operator+(int, int)`，它需要把 `Color` 整型提升为 `int`；`la::operator+` 推导出 `L = Color`、`R = int`，两个实参都是精确匹配，于是模板胜出。本机 Clang 23 报告 `no viable conversion from 'Sum<Color, int>' to 'int'`。

限定之后，`Color` 不满足 `vec_expr`，这个模板不可行（[[over.match.viable#3]]），内置运算符照常工作。约束怎样写也有讲究：

- 按结构判断，例如要求 `e[i]` 可以转换为 `double` 并且有 `e.size()`，`std::vector<double>` 也满足。本机在 using 指令之下，`auto w = v + v;`（`v` 是 `std::vector<double>`）能编译，得到一个 `Sum<vector, vector>`，这多半不是用户想要的。
- 选择加入，像 `et.cpp` 那样用一个默认为 `false` 的变量模板 `enable_vec_expr`，只有库自己的类型显式特化为 `true`。标准库的 `ranges::enable_view`、`enable_borrowed_range` 是同样的设计（见 [[topics/ranges-design]]）。

即使没有 using 指令，`la::operator+` 也会通过实参依赖查找（[[basic.lookup.argdep]]）被找到：只要有一个操作数的类型与命名空间 `la` 相关联，例如一个 `la::Vec`。约束是防止它误匹配的唯一手段。概念的写法与检查方式见 [[topics/concepts]]。

## 让它成立的语言规则

1. **运算符就是函数调用。** 操作数有类类型时，`a + b` 被改写为 `operator+(a, b)` 去做重载决议（[[over.match.oper#2]]），候选包括成员、非成员和内置运算符（[[over.match.oper#3]]）。表达式模板所需的只是一个返回类型可以自定义的函数。
2. **推导把结构记进类型。** 每一层 `operator+` 都从实参推导出 `L`、`R`，嵌套的表达式就成了嵌套的模板特化。类型在编译期完全已知，所以每个 `operator[]` 都是可以内联的直接调用，没有虚函数，也没有函数指针。
3. **临时节点活到完整表达式结束。** `a + b + c` 先创建一个 `Binary<plus, Vec, Vec>` 临时对象，外层节点的引用成员绑定到它。临时对象在包含它的完整表达式求值的最后一步销毁（[[class.temporary#4]]）；它绑定到函数的引用形参时也不延长寿命（[[class.temporary#6.10]]）。所以 `x = a + b + c;` 是安全的：整棵树在赋值的循环结束之后才销毁。下文的 `auto` 陷阱正是这条规则的另一面。

!!! std
    Temporary objects are destroyed as the last step in evaluating the full-expression that (lexically) contains the point where they were created.

    临时对象在包含它的完整表达式求值的最后一步销毁（[[class.temporary#4]]）。

## 代价，实测

### 运行时间

下面是本机（Apple M 系列，Clang 23，-O2）上计算 `x = a + b + c + d` 的观测值，单位是每个元素的纳秒数。reuse 指给 `operator+` 加了 `Vec&&` 重载、复用左操作数缓冲区的版本：

| n | 按值返回 | reuse | 表达式模板 | 每次赋值的分配次数 |
|---|---|---|---|---|
| 1 000 | 0.70 | 0.45 | 0.22 | 3 / 1 / 0 |
| 100 000 | 0.76 | 0.69 | 0.38 | 3 / 1 / 0 |
| 10 000 000 | 1.4–1.8 | 0.97 | 0.55–0.58 | 3 / 1 / 0 |

向量能放进缓存时，差距主要来自循环次数和分配；向量远大于缓存时，差距来自中间结果的写回与重读。这些数字只说明本机的情况，换机器、换元素类型、换表达式长度都会变。

### 生成的代码

把 `x = a + b + c` 单独放进一个函数，用 `-O2 -S` 查看本机生成的 arm64 汇编：没有任何函数调用，`Binary` 对象完全消失。函数先做一次运行期重叠检查（编译器不知道 `x` 的缓冲区是否与 `a`、`b`、`c` 重叠），不重叠时进入向量化的主循环，每次迭代处理 8 个 `double`：

```text
LBB0_8:
	ldp	q0, q1, [x14, #-32]      ; a 的 4 个 double
	ldp	q2, q3, [x14], #64       ; 再 4 个
	ldp	q4, q5, [x15, #-32]      ; b
	ldp	q6, q7, [x15], #64
	fadd.2d	v0, v0, v4
	...                          ; 共 8 条 fadd.2d：先加 b，再加 c
	stp	q0, q1, [x16, #-32]      ; 写入 x
	stp	q2, q3, [x16], #64
	subs	x0, x0, #8
	b.ne	LBB0_8
```

重叠时退回逐元素的标量循环（`ldr d0` / `fadd d0` / `str d0`）。这和手写 `for` 循环得到的代码是同一种形状。代价是：这一切依赖内联。-O0 下每个 `operator[]` 都是一次真正的调用。

### 编译期与调试构建

每一种不同形状的表达式都是一个新类型，都要实例化一套 `operator[]`、`size()`、`assign`。把 `x = v[0] + v[1] + … + v[N-1]` 编译成目标文件，本机观测：

| N | -O0 中定义的函数 | 最长的修饰名（字符） | -O0 目标文件 | -O2 编译时间 |
|---|---|---|---|---|
| 8 | 25 | 175 | 6.5 KB | 0.25 s |
| 64 | 137 | 905 | 86 KB | 0.27 s |
| 256 | 521 | 3 401 | 978 KB | 0.80 s |

同样的表达式用按值返回的 `operator+` 写，-O0 目标文件只有 21–46 KB，函数个数不随 N 变化。不过它在 -O2 下反而编译得更慢（N = 256 时 3.98 s），因为优化器要处理 255 个被内联的循环。所以表达式模板的编译期代价主要落在调试构建、符号表和调试信息上，在这个玩具实现里并不体现为 -O2 的编译时间。真实的库有几十种节点和大量重载，头文件本身的解析和实例化也是成本。

### 错误信息

`x = a + b * c + 1.0` 在 `et.cpp` 里是错的，因为 `double` 不是表达式。有约束时，Clang 在用户写的那一行报 `invalid operands to binary expression`，最后几条注释指出 `'double' does not satisfy 'vec_expr'`；但它也逐一列出了所有不匹配的 `operator+` 候选（包括 `<string>` 里的十几个），本机共 67 行。

去掉约束之后，`operator+` 照单全收，错误推迟到 `assign` 的循环里实例化 `Binary<…, double>::operator[]` 时才出现：`subscripted value is not an array, pointer, or vector`，位置在库的头文件里，下面跟着一串 `in instantiation of …` 的注释，每条都带着完整的嵌套类型名。这次只有 14 行，但表达式越长，类型名越长，读者也要自己从实例化栈里找回出错的那一行。

## 陷阱

### auto 留住了一棵悬垂的树

```cpp ub
// 接 et.cpp 中的 la 命名空间
int main() {
  la::Vec a(3), b(3), c(3);
  auto e = a + b + c;      // Binary<plus, Binary<plus, Vec, Vec>, Vec>
  la::Vec x = e;           // UB：e.l 引用的内层节点已经销毁
}
```

`a`、`b`、`c` 都还活着，但 `a + b` 产生的内层节点是一个临时对象，在第一条声明结束时就销毁了（[[class.temporary#4]]）。`auto` 推导出的外层节点还保存着对它的引用。本机加 `-fsanitize=address` 运行，报告 `stack-use-after-scope`，出错位置在 `Binary<plus, Vec, Vec>::size()`。编译时没有任何警告。

改进有两层：

<div class="compare" markdown="1">

```cpp
template <class Op, class L, class R>
struct Binary {
  const L& l;  // 节点也按引用
  const R& r;
  // ...
};
```

```cpp
template <class E>
using stored_t = std::conditional_t<
    std::is_same_v<E, Vec>, const E&, E>;

template <class Op, class L, class R>
struct Binary {
  stored_t<L> l;  // 叶子引用，节点值
  stored_t<R> r;
  // ...
};
```

</div>

右边按值保存内层节点，只对 `Vec` 这样的叶子保存引用。节点很小，复制它不涉及元素。这样改之后上面的程序在本机 ASan 下运行正常，`x = a + b + c` 的 -O2 代码仍然是同样的向量化循环，`sizeof(a + b + c)` 从 16 变成 24 字节。libc++ 的 `valarray` 也是这样分的（见下一节）。

但叶子本身是临时对象时，按值保存节点也救不了：

```cpp ub
la::Vec make() { return la::Vec(3); }

int main() {
  la::Vec a(3);
  auto e = a + make();     // e.r 引用临时 Vec
  la::Vec x = e;           // UB
}
```

本机 ASan 同样报告 `stack-use-after-scope`。给 `operator+` 的形参加上 `[[clang::lifetimebound]]`，Clang 会对这两个例子都给出 `-Wdangling` 警告（`temporary whose address is used as value of local variable 'e' will be destroyed at the end of the full-expression`），而 `x = a + b + c;` 和 `la::Vec y = a + b + c;` 不受影响。这是 Clang 的扩展，不是标准属性，用法见 [[topics/dangling-references]]。

!!! pitfall "auto 换了类型"
    使用表达式模板库时，`auto` 推导出的不是向量，而是一个引用着操作数的表达式对象。即使没有悬垂，它的值也会跟着操作数变：先 `auto e = a + b;` 再修改 `a`，之后读 `e[0]` 得到的是修改后的结果。需要结果时，把类型写出来：`la::Vec e = a + b;`。

### 别名：逐元素可以，矩阵乘法不行

`a = b + a` 写回的是 `a` 自己。表达式模板的循环对每个 `i` 先读 `b[i]` 和 `a[i]`，再写 `a[i]`；第 `i` 个结果只依赖第 `i` 个元素，写入之后不会再被读到，所以结果正确。只要每个输出元素只依赖同一下标的输入元素，就可以就地计算。

矩阵乘法不满足这个条件：

```cpp run title="matmul-alias.cpp" ok
#include <cstddef>
#include <cstdio>
#include <vector>

struct Mat {
  std::size_t n;
  std::vector<double> d;
  Mat(std::size_t n, std::vector<double> v) : n(n), d(v) {}
  double& operator()(std::size_t i, std::size_t j) { return d[i * n + j]; }
  double operator()(std::size_t i, std::size_t j) const { return d[i * n + j]; }
  template <class E>
  Mat& operator=(const E& e) {           // 逐元素写回
    for (std::size_t i = 0; i < n; ++i)
      for (std::size_t j = 0; j < n; ++j)
        (*this)(i, j) = e(i, j);
    return *this;
  }
};

struct Prod {                            // 尚未计算的 l * r
  const Mat& l;
  const Mat& r;
  double operator()(std::size_t i, std::size_t j) const {
    double s = 0;
    for (std::size_t k = 0; k < l.n; ++k) s += l(i, k) * r(k, j);
    return s;
  }
};
inline Prod operator*(const Mat& l, const Mat& r) { return {l, r}; }

int main() {
  Mat a(2, {1, 2, 3, 4});
  Mat b(2, {0, 1, 1, 0});                // 交换两列
  a = a * b;                             // 期望 2 1 4 3
  std::printf("%g %g %g %g\n", a(0, 0), a(0, 1), a(1, 0), a(1, 1));
}
```

程序打印 `2 2 4 4`。结果的 `(0, 1)` 要读 `a` 的整个第 0 行，而 `(0, 0)` 已经被改写成 2。这不是未定义行为，每一步都有明确定义，只是算法错了。

解决办法是让乘积先求值到一个临时矩阵，再赋给左边。乘法本身是 O(n³) 的，多一次 O(n²) 的复制可以忽略。Eigen 就是这样做的：矩阵乘积默认先求值到临时对象，用户能保证不重叠时写 `c.noalias() = a * b` 省掉它。C++26 的 `<linalg>` 则把不重叠写成前置条件：输出参数不得与其他参数重叠，除非该函数明确允许（[[linalg.helpers.concepts#3]]）；`add` 允许输出与输入别名（[[linalg.algs.blas1.add#6]]），`matrix_product(A, B, C)` 不允许。

## 标准库里的表达式模板：valarray

`std::valarray` 的运算符在概要里写作返回 `valarray<T>`，但 [[valarray.syn#3]] 给了实现一个口子：

!!! std
    Any function returning a `valarray<T>` is permitted to return an object of another type, provided all the const member functions of `valarray<T>` other than `begin` and `end` are also applicable to this type.

    任何返回 `valarray<T>` 的函数都可以改为返回另一种类型，只要 `valarray<T>` 除 `begin`、`end` 外的 const 成员函数对它也适用（[[valarray.syn#3]]）。

同一段还限制这种替代类型相对最深的实参类型最多增加两层模板嵌套；¶4–¶5 要求实现为替代类型补齐所有接受 `valarray` 的函数，并允许用它构造、赋值给 `valarray` 和四种切片代理。这是允许，不是要求：实现完全可以老老实实返回 `valarray<T>`。

本机的 libc++ 用了这个许可：

```cpp run title="valarray-type.cpp"
#include <cstdio>
#include <valarray>

template <class T>
void show() { std::puts(__PRETTY_FUNCTION__); }  // GCC/Clang 扩展

int main() {
  std::valarray<double> a(1.0, 4), b(2.0, 4), c(3.0, 4);
  auto e = a + b + c;
  show<decltype(e)>();
  std::valarray<double> x = e;             // 在这里才计算
  std::printf("%zu %g\n", sizeof(e), x[0]);
}
```

本机输出（换行是为了排版）：

```text
void show() [T = std::__val_expr<std::_BinaryOp<std::plus<double>,
    std::__val_expr<std::_BinaryOp<std::plus<double>,
        std::valarray<double>, std::valarray<double>>>,
    std::valarray<double>>>]
40 6
```

结构和 `et.cpp` 一样：`a + b` 是一个 `_BinaryOp` 节点，外面再套一层 `__val_expr` 包装，这正好是 ¶3 允许的两层嵌套。读 libc++ 的 `<valarray>` 可以看到，通用的 `_BinaryOp` 按值保存子表达式，而两个操作数都是 `valarray` 的偏特化保存 `const valarray<T>&`，也就是上一节右边那种叶子引用、节点值的分法。所以 `auto e = make() + make();` 在 libc++ 上悬垂，例子见 [[numarray]]。

因为是否使用替代类型由实现决定，依赖它的代码不可移植。最常见的是对运算结果用范围 for，见思考题 2。

## 现代的替代方案

### ranges：views::zip_transform {{c++23}}

C++23 的 `views::zip_transform` 接受一个可调用对象和若干个范围，产生一个视图，它的第 M 个元素是把可调用对象作用于各范围第 M 个元素的结果（[[range.zip.transform.overview#1]]），由 [[P2321R2]] 加入。视图本身就是惰性的：

```cpp run title="zip-transform.cpp" ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<double> a{1, 2, 3}, b{10, 20, 30}, c{100, 200, 300};
  auto sum3 = [](double x, double y, double z) { return x + y + z; };
  auto e = std::views::zip_transform(sum3, a, b, c);  // 惰性：尚未计算
  std::vector<double> x(e.begin(), e.end());          // 一个循环
  std::printf("%g %g %g\n", x[0], x[1], x[2]);        // 111 222 333
}
```

本机 -O2 下，`std::ranges::copy(views::zip_transform(…, a, b, c), x.begin())` 同样编译成每次迭代 8 条 `fadd.2d` 的向量化循环，没有函数调用。它和手写的表达式模板有几处不同：

- 运算写在一个 lambda 里，而不是写成 `a + b + c`。不需要重载任何运算符，也就没有劫持的问题。
- 长度不等时取最短的那个，不报错。
- 传入右值容器时，`views::all` 把它移进一个 `owning_view`（[[range.all.general#2]]），所以 `auto e = views::zip_transform(std::plus{}, make(1), make(2));` 之后再遍历 `e` 是安全的，本机 ASan 没有报告。传入左值时视图仍然只是引用，原容器先销毁照样悬垂。

### std::linalg {{c++26}}

`<linalg>` 是 BLAS 的 C++ 接口，向量和矩阵用 `mdspan` 表示（[[linalg.overview#1]]）。它不重载运算符，每个运算是一个函数调用，输出作为参数传入：

```cpp
namespace la = std::linalg;
la::add(x, y, z);                          // z = x + y
la::add(la::scaled(2.0, x), y, z);         // z = 2x + y
la::matrix_product(A, B, C);               // C = AB，C 不得与 A、B 重叠
```

`scaled`、`transposed` 返回的是换了访问器或布局的 `mdspan`，访问元素时才乘上系数，这一部分和表达式模板的思路一致：不复制数据，到用的时候再算。本机 libc++ 没有 `<linalg>` 头文件，以上代码没有经过编译验证，因此不带判定。详见 [[linalg]]。

### Eigen

Eigen 是 C++ 里使用表达式模板最广泛的线性代数库。下面的代码不是标准 C++ 的一部分，只用来说明设计：

```cpp
Eigen::VectorXd a(n), b(n), c(n), x(n);
x = a + b + c;              // 一个融合的循环
Eigen::MatrixXd A(n, n), B(n, n), C(n, n);
C = A * B;                  // 先求值到临时矩阵，处理别名
C.noalias() = A * B;        // 用户保证不重叠，直接写入 C
auto e = a + b;             // 表达式对象，不是向量
```

它的选择与上文分析的一致：子表达式按值保存，矩阵按引用保存；逐元素运算融合成一个循环，矩阵乘积默认先求值到临时对象；文档专门提醒不要对表达式使用 `auto`，需要时调用 `.eval()`。Eigen 的表达式类型通过一个 CRTP 基类共享接口，这种写法见 [[patterns/crtp|CRTP 与静态多态]]。

| | 手写表达式模板 | `valarray` | `views::zip_transform` | `<linalg>` |
|---|---|---|---|---|
| 写法 | `x = a + b * c` | `x = a + b * c` | lambda + 视图 | 函数调用 |
| 是否融合成一个循环 | 是 | 由实现决定 | 是 | 一次调用一个运算 |
| `auto` 的风险 | 悬垂 | 取决于实现 | 右值被持有，左值仍可能悬垂 | 不适用 |
| 别名 | 自己处理 | 前置条件（[[numarray]]） | 自己处理 | 前置条件 |
| 本机 libc++ | 可用 | 可用，使用表达式模板 | 可用 | 没有 |

## 什么时候用

| 情况 | 建议 |
|---|---|
| 一次性的逐元素计算 | 手写循环或 `views::zip_transform`，不必引入运算符重载 |
| 数值库的公共接口，用户要写大量 `a + b * c` 式的公式 | 表达式模板，或直接使用 Eigen 这类成熟的库 |
| 运算涉及跨下标的依赖（乘积、卷积、转置后赋值） | 先求值到临时对象，或像 `<linalg>` 那样把不重叠作为前置条件 |
| 用户代码里大量使用 `auto` | 表达式模板容易悬垂；考虑在接口上用 `[[clang::lifetimebound]]`，或提供显式的 `.eval()` |
| 调试构建的体积和速度很重要 | 表达式模板的 -O0 代价很高，权衡后再用 |
| 需要运行期才知道的表达式形状 | 表达式模板做不到，形状必须在编译期确定 |

## 思考题

!!! question "1"
    在 `et.cpp` 里，`x = x + x;` 和 `x = a + x * x;` 的结果正确吗？如果给 `la` 加一个节点 `Shift<E>`，它的 `operator[](i)` 返回 `e[i + 1]`（最后一个元素返回 0），`x = shift(x);` 呢？

<details markdown="1">
<summary>答案</summary>

前两个正确：每个 `x[i]` 只依赖同一下标的 `x[i]`，赋值循环在写 `x[i]` 之前已经读完了它需要的所有值。

`x = shift(x)` 也恰好正确，因为写 `x[i]` 时读的是还没被改写的 `x[i + 1]`。但反方向的移位（`operator[](i)` 返回 `e[i - 1]`，第 0 个元素返回 0）就会出错：写完 `x[0]` 之后计算 `x[1]` 时读到的是新的 `x[0]`，依此类推，结果每个元素都是 0。凡是一个输出元素依赖别的下标的输入，就要逐个分析循环方向，最稳妥的办法是先求值到临时对象。
</details>

!!! question "2"
    下面的代码在本机 libc++ 上编译失败，报告 `no viable 'begin' function available`。这是 libc++ 的缺陷吗？

    ```cpp
    std::valarray<double> a(1.0, 3), b(2.0, 3);
    for (double v : a + b) std::printf("%g\n", v);
    ```

<details markdown="1">
<summary>答案</summary>

不是。范围 for 需要 `begin` 和 `end`，而它们只为 `valarray<T>` 本身提供：当前草案里是成员函数（[[valarray.range]]，C++23 之后的新措辞），本机 libc++ 仍是旧形式的非成员 `std::begin`、`std::end` 重载。[[valarray.syn#3]] 允许 `a + b` 返回另一种类型，并且明确把 `begin` 和 `end` 排除在替代类型必须支持的成员之外。libc++ 返回 `__val_expr<…>`，它既没有成员 `begin`，也没有可用的非成员重载。在返回 `valarray<double>` 的实现上这段代码能编译，所以它不可移植。写成 `for (double v : std::valarray<double>(a + b))` 就在所有实现上都可行。
</details>

!!! question "3"
    把 `et.cpp` 的 `Vec::assign` 改成按 `e.size()` 而不是 `d_.size()` 循环，有什么风险？标准的 `valarray` 怎样处理长度不等的情况？

<details markdown="1">
<summary>答案</summary>

`Binary::size()` 只返回左操作数的长度。左边比右边长时，`e[i]` 会读右操作数越界；目标比表达式短时，`d_[i]` 会写越界。两者都是 UB，`et.cpp` 的 `assign` 按目标长度循环也只是把问题换了个位置，真正的库要么检查长度，要么把长度相等写成前置条件。`valarray` 选择了后者：两个数组之间的运算和赋值都要求长度相等，否则是 UB（见 [[numarray]]）。
</details>
