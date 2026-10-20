---
title: 包索引（P2662）
summary: C++26 用 Ts...[N] 和 args...[N] 直接取包的第 N 个类型或元素：在此之前的递归模板、借道 tuple 和继承推导各要付出多少编译期代价，提案比较过的几种语法和库方案为什么落选，负下标与推导为什么被排除，以及无名 T...[n] 形参因此改变含义。
status: draft
order: 42
group: C++26
since: c++26
papers: P2662R3, P1858R2, P1985R1, P2671R0, P1803R0, P0535R0, N4235, N3761, P1061R10, P3670R4, P2996R13, CWG2858, CWG3027, CWG3191
related: temp.variadic, expr.prim.id, dcl.type, temp.deduct.type, temp.type, dcl.type.decltype, diff.cpp23, history/template-metaprogramming, topics/compile-time-programming, papers/reflection
tags: 包索引, 变参模板, 包展开, 模板元编程, 编译期, 提案, C++26
updated: 2026-10-19
---

!!! tldr
    - C++26 之前，取包的第 N 个类型要靠递归特化、`std::tuple_element` 或继承加推导这类技巧，取第 N 个实参要递归调用或先打包成 `tuple`。本机测量中，递归写法取遍 256 个类型要 3 秒，包索引不到 0.1 秒。
    - [[P2662R3]] 引入 `Ts...[N]`（得到类型）和 `args...[N]`（得到表达式）。`...` 表明这里涉及包，`[]` 表明是下标，而直接写 `P[i]` 会和对每个数组元素取下标冲突。
    - 提案没有采用库方案 `std::nth_type`：库方案的实例化次数随下标线性增长，类型、值、模板要三套写法，也没有通往切片的路。
    - 下标必须在 `[0, sizeof...(P))` 内，负数不表示从末尾数；包索引是非推导语境；只能索引一个包的名字，不能索引任意的模式。
    - 代价是一处 Annex C 条目：C++23 里无名的函数形参包 `T... [1]`（一组数组形参）现在被解析成包索引。

## 取第 N 个元素有多难

**包**（[[g:pack|pack]]）是模板形参包、函数形参包这类可以容纳零个或多个元素的实体，包的名字只能出现在**包展开**（[[g:pack-expansion|pack expansion]]）里，例如 `f(args...)`（[[temp.variadic#5]]、[[temp.variadic#8]]）。C++11 引入变参模板时，对包能做的只有两件事：整体展开，以及用 `sizeof...` 求长度。下标访问这个最基本的序列操作不在其中。

于是取第 N 个类型只能绕路。下面是三种常见写法：

```cpp title="before.cpp" run ok
#include <cstddef>
#include <tuple>
#include <type_traits>
#include <utility>

// ① 递归：每次剥掉一个
template <std::size_t I, class T0, class... Ts>
struct nth { using type = typename nth<I - 1, Ts...>::type; };
template <class T0, class... Ts>
struct nth<0, T0, Ts...> { using type = T0; };

// ② 借道 tuple
template <std::size_t I, class... Ts>
using nth_tuple = std::tuple_element_t<I, std::tuple<Ts...>>;

// ③ 继承加推导：一次展开出 N 个带下标的基类
template <std::size_t I, class T> struct leaf {};
template <class Seq, class... Ts> struct leaves;
template <std::size_t... I, class... Ts>
struct leaves<std::index_sequence<I...>, Ts...> : leaf<I, Ts>... {};
template <std::size_t I, class T> T pick(leaf<I, T>);   // 只声明
template <std::size_t I, class... Ts>
using nth_inherit = decltype(pick<I>(
    leaves<std::index_sequence_for<Ts...>, Ts...>{}));

static_assert(std::is_same_v<nth<2, int, char, double>::type, double>);
static_assert(std::is_same_v<nth_tuple<2, int, char, double>, double>);
static_assert(std::is_same_v<nth_inherit<2, int, char, double>, double>);
int main() {}
```

① 是 [[P2662R3]] 引用的写法，标准库实现内部大多藏着一份类似的元函数。`nth<5, …>` 要实例化 `nth<5>`、`nth<4>`……`nth<0>` 共 6 个特化，而 `nth<6, …>` 用不上其中任何一个，因为每一层的实参列表都不同。取遍长度为 N 的包，总共要 N(N+1)/2 个特化，每个特化还带着一条 O(N) 长的实参列表。

② 把问题交给标准库，标准库自己也得用某种办法解决。本机 libc++ 的 `tuple_element<I, tuple<Ts...>>` 和 `variant_alternative` 都直接调用 Clang 的内建模板 `__type_pack_element<I, Ts...>`，所以代价取决于实现。③ 的思路是用一次包展开生成 N 个基类 `leaf<0, T0>`、`leaf<1, T1>`……，再让函数模板实参推导从派生类到基类的转换里找出唯一匹配 `leaf<I, T>` 的那个，`T` 就是答案。它不递归，但每次查找都要在 N 个基类里做一次推导。

取第 N 个实参也一样。没有包索引时，要么递归调用，要么先用 `std::forward_as_tuple` 打包成 `tuple` 再 `std::get`：

```cpp title="values.cpp" run ok
#include <cstddef>
#include <cstdio>
#include <tuple>
#include <utility>

template <std::size_t I, class T0, class... Ts>
constexpr decltype(auto) nth_value(T0&& t0, Ts&&... ts) {
  if constexpr (I == 0) return std::forward<T0>(t0);
  else return nth_value<I - 1>(std::forward<Ts>(ts)...);
}

template <std::size_t I, class... Ts>
constexpr decltype(auto) nth_tuple(Ts&&... ts) {
  return std::get<I>(std::forward_as_tuple(std::forward<Ts>(ts)...));
}

template <std::size_t I, class... Ts>             // C++26
constexpr decltype(auto) nth_index(Ts&&... ts) {
  return std::forward<Ts...[I]>(ts...[I]);
}

int main() {
  int a = 0, b = 1, c = 2, d = 3, e = 4, f = 5;
  std::printf("%d %d %d\n", nth_value<5>(a, b, c, d, e, f),
              nth_tuple<5>(a, b, c, d, e, f),
              nth_index<5>(a, b, c, d, e, f));    // 5 5 5
}
```

提案指出，库方案在不优化的编译中会生成大量符号和小函数。本机用 Clang 23 `-O0` 分别只调用其中一个函数，再用 `llvm-nm` 数目标文件里定义的函数（不计 `main`）：递归版本生成 `nth_value<0>` 到 `nth_value<5>` 共 6 个函数；`tuple` 版本生成 14 个，包括 `tuple` 的构造函数、6 个 `__tuple_leaf` 构造函数和 `get`；包索引版本只有 `nth_index<5>` 一个。

### 本机测量

下面的测量构造一个包 `E<0>, E<1>, …, E<N-1>`（`E` 是以 `int` 为形参的空类模板），用 `list<at<I, Ts...>...>` 取出每一个元素并与原序列比较，因此一共做 N 次查找。`at` 分别用上面的几种办法实现，外加内建的 `__type_pack_element` 和 C++26 的 `Ts...[I]`。表中是本机 Clang 23（arm64 macOS）`-fsyntax-only` 三次运行的最短墙钟时间，单位为秒；基线是不做查找、直接写 `E<I>` 的版本。

| N | 基线 | ① 递归 | ③ 继承推导 | `void*` 技巧 | `__type_pack_element` | `Ts...[I]` |
|---|---|---|---|---|---|---|
| 128 | 0.07 | 0.33 | 0.09 | 0.09 | 0.07 | 0.06 |
| 256 | 0.07 | 3.06 | 0.15 | 0.15 | 0.07 | 0.08 |
| 512 | 0.09 | 128–264 | 0.39 | 0.39 | 0.12 | 0.11 |
| 1024 | 0.16 | 未测 | 1.48 | 1.51 | 0.28 | 0.24 |
| 2048 | 0.49 | 未测 | 6.10 | 6.25 | 0.89 | 0.75 |

`void*` 技巧是另一种不递归的写法：为下标 I 生成一个函数模板 `template<class T> T f(V0, …, V(I-1), T*, ...)`，前 I 个形参都是 `const void*`，把 `static_cast<Ts*>(nullptr)...` 传进去，第 I+1 个实参就推导出 `T`。

用 `-Xclang -print-stats` 数类模板特化，N = 128 时，递归写法比基线多 8256 个，正好是 128 × 129 / 2；继承推导多 131 个；`void*` 技巧多 256 个，外加 128 个形参越来越长的函数模板；`__type_pack_element` 和 `Ts...[I]` 一个也不多。递归写法在 N = 256 时常驻内存约 1 GB。N = 512 时只单独编译了两次，分别用了 264 秒和 128 秒；后一次用 `/usr/bin/time -l` 测量，其中 79 秒是系统时间，峰值内存占用约 7 GB。耗时的涨幅远超过实例化个数的增长，主要耗在内存上。

这些数字只说明本机的情况，换一个编译器或版本会不同。趋势是清楚的：递归随 N² 增长，继承推导和 `void*` 技巧每次查找要扫一遍整个包，总体也是 N²，只是常数小得多；内建和包索引的每次查找接近常数时间。

## 设计空间

### 语法候选

[[P2662R3]] 的语法 `name-of-a-pack ... [constant-expression]` 来自 [[P1858R2]]，Circle 编译器早已用同样的写法实现。R1 应演化组的要求，把其他候选逐一比较了一遍：

| 候选 | 出处 | 落选的理由 |
|---|---|---|
| `pack.[N]` | [[N4235]] | 单个点在 C++ 里表示成员访问；[[P1858R2]] 还想把 `tuple.[N]` 留给对 tuple-like 对象取下标 |
| `pack<N>`、`pack...<N>` | | 绝大多数语言用 `[]` 做下标和切片；包索引常出现在尖括号很多的代码里，再用尖括号并不更清楚 |
| `std::nth_type<N, pack...>`、`std::nth_value<N>(pack...)` | 已有的库实践；[[N3761]] 提议过 `type_at<>` | 见下一节 |
| `packexpr(pack, N)` | [[P1803R0]] | 要找一个对所有种类的包都有意义、又没人用过的名字，而且必须是全局保留的关键字，因为类型和表达式出现的地方都可能用到它；切片还要再起一个名字 |
| `[N]pack` | [[P0535R0]] | 可能需要向前看才能和 lambda 区分；除了这个位置还空着，没有别的理由 |
| 包对象 `pack![N]` | [[P2671R0]] | 只对表达式有效；切片之后得到包对象还是包说不清，于是又要发明 `ts![1:]~...` 这类记号 |

作者的结论是：任何一种语法都比现状好，但 `...[N]` 是现有文法最自然的延伸。`...` 在 C++ 里一直标记包，读者一眼能看出哪里涉及包；把 `...` 后缀的语法只留给包相关的特性，等于给将来的包操作保留了一块设计空间。反对意见主要是点太多，作者承认大量操作包的代码确实满是点，但认为这样的代码仍然可读。

### 为什么不能直接写 P[i]

最直接的写法是 `Ts[N]`，但包的元素本身可能是数组或带 `operator[]` 的类型，这时有四种不同的操作，而且都有用：取第 N 个数组、对每个数组取下标、用一个下标包对一个数组取下标、两个等长的包逐对取下标。`...` 放在 `[` 之前还是之后，正好把前两种区分开：

```cpp title="arrays.cpp" run ok
#include <cstdio>

void print(auto... xs) { ((std::printf("%d ", xs)), ...); std::puts(""); }

template <class... A>
void demo(A&... arr) {
  print(arr...[1][0]);          // 第 1 个数组的第 0 个元素：一个值
  print(arr[0]...);             // 每个数组的第 0 个元素：一列值
  auto& second = arr...[1];     // 第 1 个数组本身
  std::printf("%zu\n", sizeof second / sizeof second[0]);
}

int main() {
  int a[2] = {1, 2}, b[3] = {10, 20, 30}, c[1] = {100};
  demo(a, b, c);   // 输出 10 / 1 10 100 / 3
}
```

### 为什么不做成库

库方案的好处是不改语言。提案列出了它的四个缺点：

1. 类型和值要两套写法，模板的包还要第三个名字和第三种语法。
2. 递归深度是 O(下标)，不同下标的实例化不能复用，`nth_type<5, …>` 和 `nth_type<6, …>` 加起来就是 11 个实例化。上一节的测量就是这个问题。
3. 包不是一等的对象或类型，库里的元函数没法返回一个尚未展开的包，所以库方案没有通往切片的路。
4. 对 [[P1985R1]] 提议的通用模板形参（universal template parameter）不适用。

编译器可以提供内建设施降低代价，Clang 的 `__type_pack_element` 就是一例，本机 libc++ 的 `tuple_element` 正是用它实现的。提案的回答是：标准不能保证每个实现都这样做；即使库模板内部调用内建设施，这层模板本身仍要实例化一次。更根本的是，这样的内建设施本来就是编译器给出的包索引，只是名字是保留标识符，而且只对类型有效。把它标准化成语法，才能让类型、表达式和将来的模板名用同一种写法。

### 用反射来写

[[P2671R0]] 的包对象可以用反射建模，[[P2662R3]] 也承认包索引等价于把包反射成一组值、按下标取出再拼接回去。用 C++26 静态反射（[[P2996R13]]，见 [[papers/reflection|静态反射]]）的写法，取类型大致是：

```cpp
#include <array>
#include <cstddef>
#include <meta>

template <std::size_t I, class... Ts>
using at = typename [: std::array{^^Ts...}[I] :];
```

本机 Clang 23 不支持反射（没有定义 `__cpp_impl_reflection`），这段代码无法在本机验证，所以没有标判定。作者的看法是：编译器要么真的构造一个常量求值的数组再拼接，比包索引慢；要么把整个写法识别成一次包索引，那它就只是换了一种拼法。

### 负下标

[[P1858R2]] 的切片里，`Ts...[:-1]` 表示去掉最后一个，Circle 也支持用负数从末尾索引。[[P2662R3]] 没有采纳，理由是负数常常来自计算错误：

```cpp
// 返回 Pack 中第一个能转换为 Needle 的类型的下标，找不到时返回 -1
template <class Needle, class... Pack>
constexpr int find_convertible = /* … */;

// 找不到时，T 会悄悄变成最后一个类型
using T = Types...[find_convertible<Foo, Types...>];
```

如果 `-1` 表示最后一个，这个错误就变成了一个错的类型，而不是编译错误。C# 的 `^1` 和 D 的 `$ - 1` 这类专门的语法可以以后再加，提案没有使用经验，所以先不做。

今天的规则是：下标是 `std::size_t` 类型的转换常量表达式（[[expr.const.const]]），转换常量表达式不允许窄化转换，`-1` 转换到 `std::size_t` 是窄化，因此非良构；越界和对空包取下标也都非良构：

```cpp title="bad-index.cpp" error
template <class... T> struct S { using A = T...[3]; };
using X = S<int, int>::A;      // error: 下标 3 越界，包只有 2 个元素

template <class... T> void neg() { using A = T...[-1]; }   // error: -1 窄化到 std::size_t
template <class... T> void none() { using A = T...[0]; }
template void none<>();        // error: 空包不能索引
```

### 能不能推导

`template<class... T> void f(T...[0]);` 能不能从 `f(0)` 推导出 `T`？提案的回答是不能，包索引始终是非推导语境。审查时出现过一个可以推导的例子：

```cpp title="nondeduced.cpp" run ok
#include <cstdio>
#include <tuple>

template <class... T>
void f(T...[0] x, std::tuple<T...>) {
  std::printf("%u\n", x);
}

int main() {
  f(-1, std::tuple(5u, 1));   // T... 从 tuple 推导为 unsigned, int
}
```

按提案的规则，`T...` 只从第二个实参推导，`T...[0]` 是 `unsigned`，`-1` 被转换成 4294967295。如果允许从第一个实参推导，就会得到 `int`，与 tuple 推导出的 `unsigned` 冲突而失败。提案专门让演化组表态，因为先规定为非推导、以后再放开，会改变这类已有代码的含义。

放开推导的困难在于包的长度。`template<class... T> int f(T...[0], int);` 调用 `f(0, 1)` 时，`T` 是一个元素还是两个都说得通；只有当包的长度另有来源时，推导单个元素才有意义，而那时整个包往往已经推导出来了。提案找不到值得这样复杂化的用例，还指出它会牵动偏序规则。

这条规则在 [[temp.deduct.type#5.2]]。像 `g(0)` 这样只有包索引的调用，`T` 推导为空包，随后 `T...[0]` 越界，替换失败。

### 只索引名字，不索引模式

`args...[0]` 中 `...` 前面只能是一个指代包的标识符。提案讨论过更一般的形式：

```cpp
g(std::forward<T...[0]>(t...[0]));   // 采纳的写法
g(std::forward<T>(t)...[0]);         // 没有提议，也没有实现
```

后者先构造一个任意复杂的模式，展开之后只留一个元素，编译器可能要实例化许多用不到的表达式，其中还可能发生替换失败。先取元素再在外面构造表达式，读起来更清楚，编译器也更省事。这被列为将来可以探索的方向。

## 最终设计与措辞

!!! std
    *pack-index-specifier*: *typedef-name* `...` `[` *constant-expression* `]` ([[dcl.type.pack.index]])

    *pack-index-expression*: *id-expression* `...` `[` *constant-expression* `]` ([[expr.prim.pack.index]])

两种形式的规则平行：`...` 前面必须是指代包的标识符（¶1），下标是值在 `[0, sizeof...(P))` 内的 `std::size_t` 转换常量表达式（¶2），整个结构本身就是一个包展开，所以后面不再写 `...`（¶3）。语义只在 [[temp.variadic]] 里给出：实例化时，包索引表达式就是第 K 个元素对应的 *id-expression*，包索引类型就是第 K 个 *typedef-name*（[[temp.variadic#11]]、[[temp.variadic#12]]）。

这种定义方式保证包索引表达式的行为和直接写出那个元素一模一样。提案特别要求 `decltype(pack...[0])` 和 `decltype(id-expression)` 一致：不加括号时得到声明的类型，加括号时按值类别得到引用（[[dcl.type.decltype#1]] 的例子）。

```cpp title="basic.cpp" run ok
#include <cstdio>
#include <type_traits>

template <typename... T>
constexpr auto first_plus_last(T... values) -> T...[0] {
  return T...[0](values...[0] + values...[sizeof...(values) - 1]);
}

template <class... Ts>
void show(Ts&&... args) {
  static_assert(std::is_same_v<decltype(args...[0]), Ts...[0]&&>);
  static_assert(std::is_same_v<decltype((args...[0])),
                               std::remove_reference_t<Ts...[0]>&>);
  std::printf("%d\n", args...[0]);
}

int main() {
  static_assert(first_plus_last(1, 2, 10) == 11);
  int x = 7;
  show(x, 1.0, 'c');   // 7
}
```

包索引类型是一种**计算类型说明符**（computed-type-specifier），和 `decltype` 并列，所以 `decltype` 能出现的地方它都能出现：作为基类说明符、嵌套名说明符、显式析构调用里的类型名（见 [[dcl.type]]、[[class.derived]]）：

```cpp title="contexts.cpp" run ok
#include <cstdio>
#include <new>
#include <string>

struct A { static constexpr int id = 1; void hi() const { std::puts("A"); } };
struct B { static constexpr int id = 2; };

template <class... Ts>
struct D : Ts...[0] {                              // 基类
  static constexpr int first_id = Ts...[0]::id;    // 嵌套名说明符
};

template <class... Ts>
void destroy_first(void* p) {
  static_cast<Ts...[0]*>(p)->~Ts...[0]();          // 显式析构调用
}

int main() {
  D<A, B> d;
  d.hi();                                          // A
  static_assert(D<B, A>::first_id == 2);
  alignas(std::string) unsigned char buf[sizeof(std::string)];
  ::new (buf) std::string(100, 'x');
  destroy_first<std::string, int>(buf);
}
```

措辞改动按当前草案的位置整理如下，逐条的释义见各条款页：

| 条款 | 改动 |
|---|---|
| [[expr.prim.pack.index]] | 新增包索引表达式；*id-expression* 的文法增加这一分支（[[expr.prim.id]]） |
| [[dcl.type.pack.index]] | 新增包索引说明符；`decltype` 和它合称计算类型说明符（[[dcl.type]]） |
| [[temp.variadic#6]] | 包展开语境增加 ¶6.14、¶6.15 |
| [[temp.variadic#11]]、[[temp.variadic#12]] | 包索引的实例化结果 |
| [[temp.type#5]] | 待决的包索引类型何时是同一类型 |
| [[temp.dep.type#10]] | 包索引类型是依赖类型（¶10.12） |
| [[temp.dep.expr]] | 包索引表达式在其 *id-expression* 类型依赖时类型依赖 |
| [[temp.deduct.type#5]] | 包索引是非推导语境（¶5.2） |
| [[diff.cpp23.dcl.dcl#2]] | 无名的 `T...[n]` 形参改变含义 |

特性测试宏是 `__cpp_pack_indexing`（[[cpp.predefined]]）。P2662R3 规定它取提案被采纳时的日期，本机 Clang 23 定义为 `202311L`；下文的 [[P3670R4]] 要求把它更新为自己被采纳的日期，当前草案中的值是 `202606L`。

## 后果

### Annex C：无名的数组形参包

C++23 里，`T... [1]` 已经是合法的函数形参声明：一个无名的函数形参包，每个形参的类型是 `T` 的数组，随即调整为指针。C++26 中同一串记号被解析成包索引：

<div class="compare" markdown="1">

```cpp
// C++23：两个形参 int*, double*
template <typename... T>
void f(T... [1]);

f<int, double>(nullptr, nullptr);
// OK
```

```cpp
// C++26：一个形参，类型是 T...[1]
template <typename... T>
void f(T... [1]);

f<int, double>(nullptr, nullptr);
// error
f<int, double>(1.0);   // OK
```

</div>

给形参起名就能保留原意：`void g(T... ptr[1]);` 中 `...` 后面跟着名字，只能是包展开，两个标准里含义相同（[[diff.cpp23.dcl.dcl#2]]）。[[P1858R2]] 在代码搜索中只找到 11 处这样的写法，都在编译器测试里；P2662R3 补充说 GCC 和 MSVC 一直没有实现这种语法，它在编译器测试之外没有出现过。这是作者认为可以接受这个不兼容的依据。

本机 Clang 23 在 `-std=c++23` 甚至 `-std=c++20` 下也按新规则解析：给出 `-Wc++26-extensions` 和 `-Wpre-c++26-compat` 两条警告，然后拒绝左边的调用。按 C++23 标准左边是良构的，所以这是 Clang 在旧模式下偏离标准的地方。Clang 在 C++23 模式下也把包索引作为扩展接受，并定义 `__cpp_pack_indexing`。[[diff.cpp23]] 有同一条目的释义。

### 后续修正和扩展

| 编号 | 内容 | 状态 |
|---|---|---|
| [[CWG2858]] | 声明性嵌套名说明符（类外定义成员时 `X::f` 里的 `X::`）不能用包索引，措辞从 *decltype-specifier* 改为 *computed-type-specifier* | CD7 |
| [[CWG3027]] | 两个待决的包索引类型相同，还要求它们索引的是同一个形参包（[[temp.type#5.1]]） | DR，已并入当前草案 |
| [[CWG3191]] | 引用折叠规则和忽略引用上的 cv 限定的规则（[[dcl.ref#1]]、[[dcl.ref#7]]）没有提到包索引和拼接 | tentatively ready，当前草案尚未修改 |
| [[P1061R10]] | 结构化绑定可以引入包，这种包也能索引 | C++26 |
| [[P3670R4]] | 包索引模板名 `TT...[0]<T>`，对模板模板形参包取下标 | C++26 之后并入工作草案 |

CWG3191 说的是 `T...[0]&&` 在 `T...[0]` 为 `int&` 时应该折叠成 `int&`。建议的修正把 *computed-type-specifier* 加进 [[dcl.ref#7]]，它目前的字面只列出 *typedef-name* 和 *decltype-specifier*。本机 Clang 23 已经按修正后的规则折叠，`const T...[0]` 在 `T...[0]` 为 `int&` 时也得到 `int&`。

[[P2662R3]] 的未来方向一节说，对模板模板形参包的索引要等概念模板形参、变量模板形参的提案落定再做。[[P3670R4]] 补上了这一块，措辞落在 [[temp.names]]、[[temp.variadic#13]] 和 [[temp.type#6]]，作者说明它尚无实现。从末尾索引、切片、索引任意表达式，仍然只是提案里列出的可能演进。

```cpp title="sb-pack.cpp" run ok
#include <cstdio>

struct P { int a; double b; char c; };

template <class T>
void last_member(const T& t) {
  auto& [...ms] = t;                                  // 结构化绑定包
  std::printf("%c %zu\n", ms...[sizeof...(ms) - 1],   // 最后一个成员
              sizeof...(ms));
}

int main() { last_member(P{1, 2.0, 'z'}); }           // z 3
```

### 编译器支持

本机 Clang 23 实现了类型和表达式的包索引，`__cpp_pack_indexing` 定义为 `202311L`；结构化绑定包也能索引。本页上述例子的表现都与标准一致，例外是上面说的 C++23 模式下的 Annex C 行为。Clang 23 还不支持 [[P3670R4]] 的包索引模板名，`TT...[0]<T>` 报语法错误。本机 libc++ 已经在 C++26 模式下的 `std::get(integer_sequence)` 里使用 `_Indices...[_Ip]`。其他编译器本页没有验证；[[P3670R4]] 的作者说 GCC 也已实现 P2662R3。

## 思考题

!!! question "思考题 1"
    下面的 `f<int>` 和 `f<int, double>` 各是什么函数类型？对它们取地址会怎样？
    ```cpp
    template <typename... T> void f(T... [1]);
    ```

<details markdown="1">
<summary>答案</summary>

在 C++26 中，`T... [1]` 是包索引 `T...[1]`。`f<int, double>` 的类型是 `void(double)`。`f<int>` 在替换时下标 1 越界（[[dcl.type.pack.index#2]]），这是替换失败，所以 `&f<int>` 找不到可用的特化，非良构。本机 Clang 23 对 `decltype(f<int>)` 报告无法解析重载函数的引用。

在 C++23 中，两者分别是 `void(int*)` 和 `void(int*, double*)`。
</details>

!!! question "思考题 2"
    `template<class... Ts> void g(Ts... ts) { auto x = (ts + 1)...[0]; }` 为什么非良构？怎样改写？

<details markdown="1">
<summary>答案</summary>

*pack-index-expression* 的 `...` 前面只能是一个指代包的标识符（[[expr.prim.pack.index#1]]），`(ts + 1)` 不是标识符；而 `ts` 出现在一个没有展开的表达式里，也违反了 [[temp.variadic#8]]。改成先取元素再运算：`ts...[0] + 1`。提案把索引任意模式列为将来可能的方向，没有提议。
</details>

## 小结

| 决定 | 选择 | 理由 |
|---|---|---|
| 核心语言还是库 | 核心语言 | 库方案实例化 O(下标) 次，类型、值、模板要三套写法，无法切片 |
| 语法 | `pack...[N]` | 沿用 `...` 标记包、`[]` 表示下标；与 `pack[N]...` 区分开 |
| 下标范围 | `0 ≤ N < sizeof...(pack)`，越界非良构 | 负下标容易掩盖计算错误，从末尾索引留给专门的语法 |
| 推导 | 非推导语境 | 部分推导要先知道包的长度；以后再放开会改变已有代码 |
| 可索引的对象 | 只限包的名字 | 避免实例化用不到的表达式；任意模式留作将来的演进 |
| 兼容性 | 无名的 `T... [n]` 改变含义 | 代码搜索只在编译器测试里找到这种写法 |

变参模板从递归走向包展开、折叠表达式、包索引的整个过程，见 [[history/template-metaprogramming]]；包展开的规则本身见 [[temp.variadic]]。
