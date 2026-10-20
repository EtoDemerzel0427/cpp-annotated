---
title: 静态反射（P2996）
summary: C++26 让程序在编译期把类型、成员、枚举项当作 std::meta::info 值来查询，再用 [: :] 拼回代码；它为什么选了基于值的单一不透明类型、为什么记号是 ^^、访问控制和错误处理怎样定下来，以及哪些能力被推迟了。
status: draft
order: 30
group: C++26
since: c++26
papers: P2996R13, P1240R2, P3381R0, P3547R1, P3560R2, P4101R1, P3394R4, P3289R1, P1306R5, P3491R3, P3294R2, P2237R0
related: expr.reflect, basic.splice, expr.prim.splice, meta.reflection, expr.const.const, expr.const.reflect, stmt.expand, history/template-metaprogramming, history/constexpr, topics/compile-time-programming, patterns/factory-and-registration
tags: 反射, 元编程, consteval, C++26, 提案
updated: 2026-10-19
---

!!! tldr
    - C++26 之前，枚举转字符串、遍历结构体成员只能靠宏、代码生成或依赖编译器细节的模板技巧，因为语言不提供成员的名字和列表。
    - [[P2996R13]] 把每个程序构造表示成同一个不透明类型 `std::meta::info` 的值：`^^X` 取得反射，`consteval` 函数查询它，`[: r :]` 把它拼回代码。
    - 选单一类型而不是一族类型，是为了不把语言的分类写死进库的类型系统；记号从 `reflexpr` 换成 `^`，又因为与 Clang 的 block 扩展冲突换成 `^^`。
    - 访问控制由调用者显式传入的 `access_context` 决定，`unchecked()` 是可审查的越权入口；查询失败抛出 `std::meta::exception`。
    - 区间拼接、表达式反射和通用的代码注入都被推迟，C++26 只能用 `define_aggregate` 补全一个类的定义。

## 反射之前

一个最常见的需求是把枚举值转成它的名字。语言不提供枚举项的名字，常见的做法是 X-macro：把枚举项列表写成一个宏，再展开两次，一次生成枚举定义，一次生成 `switch`。

```cpp run title="xmacro.cpp" ok
#include <cstdio>
#include <string_view>

#define COLORS(X) X(red) X(green) X(blue)

enum class Color {
#define AS_ENUM(name) name,
  COLORS(AS_ENUM)
#undef AS_ENUM
};

constexpr std::string_view to_string(Color c) {
  switch (c) {
#define AS_CASE(name) case Color::name: return #name;
    COLORS(AS_CASE)
#undef AS_CASE
  }
  return "<unnamed>";
}

static_assert(to_string(Color::green) == "green");

int main() {
  std::printf("%s\n", to_string(Color::blue).data());
}
```

它能工作，代价是枚举必须按宏的格式定义。第三方库里已有的枚举用不上这个办法。

另一类做法依赖编译器扩展。`__PRETTY_FUNCTION__` 的内容里带着模板实参，magic_enum 一类的库就是从这个字符串里截出枚举项的名字：

```cpp run title="pretty.cpp" impl
#include <cstdio>
#include <string_view>

enum class Color { red, green, blue };

template <auto V>
constexpr std::string_view name_of() {
  return __PRETTY_FUNCTION__;  // 编译器扩展，格式由实现决定
}

int main() {
  std::printf("%s\n", name_of<Color::green>().data());
  std::printf("%s\n", name_of<static_cast<Color>(7)>().data());
}
```

本机 Clang 23 输出 `std::string_view name_of() [V = Color::green]` 和 `std::string_view name_of() [V = (Color)7]`。库要按编译器解析这种字符串，再对一个整数范围逐个实例化模板，看哪些值打印出了名字。

结构体也有同样的问题。Boost.PFR 的思路是用一个能转换成任何类型的占位对象去试聚合初始化，从能接受多少个初始化器推出字段个数，再用结构化绑定取出字段：

```cpp run title="pfr.cpp" ok
#include <cstddef>
#include <cstdio>
#include <string>
#include <tuple>
#include <utility>

struct any_init {
  template <class T> operator T() const;  // 只声明，不定义
};

// 能用 N 个 any_init 聚合初始化 T，说明 T 至少有 N 个字段
template <class T, std::size_t... I>
consteval bool init_with(std::index_sequence<I...>) {
  return requires { T{(void(I), any_init{})...}; };
}

template <class T, std::size_t N = 0>
consteval std::size_t field_count() {
  if constexpr (!init_with<T>(std::make_index_sequence<N + 1>{}))
    return N;
  else
    return field_count<T, N + 1>();
}

template <class T>
auto to_tuple(T& t) {
  constexpr auto n = field_count<T>();
  if constexpr (n == 1) { auto& [a] = t; return std::tie(a); }
  else if constexpr (n == 2) { auto& [a, b] = t; return std::tie(a, b); }
  else if constexpr (n == 3) { auto& [a, b, c] = t; return std::tie(a, b, c); }
  else static_assert(n <= 3, "要支持更多字段就再写一行");
}

struct Point { int x; double y; std::string label; };
static_assert(field_count<Point>() == 3);

int main() {
  Point p{1, 2.5, "origin"};
  auto [x, y, label] = to_tuple(p);
  std::printf("%d %g %s\n", x, y, label.c_str());
}
```

这个技巧只对聚合有效，还会被大括号省略骗过：本机验证，`struct Pair { int a[2]; int b; }` 只有两个成员，`field_count<Pair>()` 却得到 3，因为数组成员的两个元素各自吃掉了一个 `any_init`。它也拿不到字段的名字，而序列化恰恰需要名字。

C++26 的展开语句 `template for`（[[P1306R5]]，[[stmt.expand]]）能遍历一个可以做结构化绑定的对象，本机 Clang 23 已经支持：

```cpp run title="values.cpp" ok
#include <iostream>
#include <string>

struct Point { int x; double y; std::string label; };

template <class T>
void print_values(const T& obj) {
  template for (const auto& v : obj) {  // 解构式展开语句
    std::cout << v << ' ';
  }
  std::cout << '\n';
}

int main() {
  print_values(Point{1, 2.5, "origin"});  // 1 2.5 origin
}
```

拿到的仍然只有值。成员叫什么、是不是 `private`、带着什么属性，这些信息编译器都有，语言却没有给程序一条读取它们的通道。这就是反射要补上的东西。

## 设计空间

### 反射的结果是类型还是值

C++ 的第一套反射设计是 Reflection TS：`reflexpr(X)` 产生一个元对象类型，查询都是 traits 风格的模板。后来的 [[P1240R2]] 改成基于值：所有反射都是同一个类型 `std::meta::info` 的值，查询是普通的 `consteval` 函数（即**立即函数**，每次调用都必须在编译期求值，[[g:immediate-function]]）。这次转向的来龙去脉、两种写法的对比和编译开销上的理由，见 [[history/template-metaprogramming|模板元编程的沿革]]第六节，这里不再重复。

基于值的直接好处是元编程变成了普通编程。`members_of` 返回 `std::vector<std::meta::info>`，可以用 `for` 循环、`if`、下标和标准算法处理，不必再写递归模板。这依赖 C++20 允许在常量求值中使用 `new`（[[history/constexpr]]）。

### 一个类型还是一族类型

P2996 说，对 P1240 最常见的修改建议是把单一的 `info` 拆成一族类型，例如 `std::meta::type`、`std::meta::variable`，这样函数签名就能表达它接受哪种反射。作者认为这是一个后果严重的错误（P2996R13 §2.2）。

理由是这会把语言的分类方式写死进库的类型系统。论文举的例子是：假如 C++03 标准化了一个表示变量的 `std::meta::variable`，C++11 把变量的定义扩展到引用时，大量代码已经依赖了旧的类型划分，扩展就很难做。标准类型的语义一旦发布几乎改不动，而语言的分类今后还会变。

论文还列了几条附带的好处：

- 不对编译器内部的表示做任何假设，不偏向某一家实现；
- 语言增加新构造时，不必增加新类型；
- `std::vector<std::meta::info>` 可以装一个混合的模板实参列表，类型和值放在一起，不会出现基类、派生类之间的切片问题。

代价是类型检查推迟到了调用时：把一个类型的反射传给只接受枚举的 `enumerators_of`，要到常量求值时才报错，错误的形式见下文的错误处理一节。

### 记号：从 reflexpr 到 ^^

P1240 沿用 TS 的关键字 `reflexpr(e)`。讨论中大家觉得它太重，看起来又像函数调用，SG7 改成了一元 `^`，取向上箭头提升的意思（P2996R13 §4.1.1）。

`^` 后来被发现与 Clang 的 block 扩展冲突。block 是 Apple 为 C 和 Objective-C 加的闭包语法，Clang 在 C++ 中也支持。[[P3381R0]] 指出，`type-id(^ident)();` 既可以读成声明一个 block 变量，也可以读成把 `ident` 的反射转换成 `type-id` 再调用。本机的 Clang 23 就会把 `^` 当成 block：

```cpp run title="blocks.cpp" impl cc=clang_trunk flags="-std=c++2c -fblocks"
int main() {
  int (^ident)() = ^{ return 42; };  // Clang 的 block 扩展：ident 是一个 block
  return ident() == 42 ? 0 : 1;
}
```

加上 `-fblocks` 后这段代码能编译运行；不支持反射的 Clang 23 遇到 `^^int`，给出的诊断也是 `block pointer to non-function type is invalid`。

P3381R0 逐个排除了其他单字符：`#e` 在宏里已有字符串化的含义；`$e` 与很多编译器允许的 `$` 开头的标识符冲突；`%e` 写成 `C<%T>` 时 `<%` 是 `{` 的二连符。最后选了 `^^`，作为一个新的记号。论文也解释了为什么不回到关键字：反射本身不是代码想表达的东西，它是因为实体不是普通的值才需要付出的代价，写成 `f(^^int, ^^float)` 已经是退而求其次，没有理由把它写得更醒目。

### 拼接：[: :]

把反射变回代码的操作叫**拼接**（splice）。早期设计用 `unreflexpr(...)`，P1240R0 发现单一的拼接语法无法解析，必须区分类型和模板，SG7 最终选了 `[: r :]`，需要时前面加 `typename` 或 `template` 消歧（P2996R13 §4.2.4）。

选左右不同的定界符，一是因为被拼接的表达式可能含有低优先级的运算符，二是为了允许嵌套拼接。`[:` 和 `:]` 被做成单个记号，这样 `arr[[:r:]]` 好处理；代价是要像处理 `<::` 一样加特殊规则，保留 `arr[::N]` 原来的含义（[[lex.pptoken#5.3]]）。

P1240 还有一种区间拼接 `[: ... r :]`，把一列反射展开成一个包。P2996 没有收入它，理由是对依赖实参做区间拼接的实现难度高出至少一个数量级，不收入它能提高赶上 C++26 的机会。今天它的用途由 `template for` 承担。

### 访问控制：谁在问

能不能用反射看到 `private` 成员，是反射讨论里最老的争论之一。[[P3547R1]] 总结了各方的立场：有人认为能完整内省类是反射的基本要求，有人担心用户会意外拿到私有成员的反射，要求必须明确表达意图，还有少数人认为根本不该提供这种能力。

最直接的想法是加一个 `is_accessible(r)`，按调用点检查访问权限。P3547R1 说明这样写出来的库无法组合（以下按论文改写，未经编译）：

```cpp
consteval auto accessible_nsdms_of(info cls) -> vector<info> {
  vector<info> result;
  for (auto m : nonstatic_data_members_of(cls))
    if (is_accessible(m))   // 从哪里检查？
      result.push_back(m);
  return result;
}

class Cls {
  int priv;
  friend void client();
};

void client() {
  static_assert(accessible_nsdms_of(^^Cls).size() > 0);  // 失败
}
```

`is_accessible` 是在 `accessible_nsdms_of` 里调用的，那个函数不是 `Cls` 的友元，所以 `client` 的友元身份被丢掉了。改成从常量求值开始的位置检查也不行：一个 `consteval` 友元函数如果从 `main` 里被调用，求值开始于 `main`，友元关系同样失效。

P3547R1 的结论是不去猜，让调用者显式传入上下文。最终设计中，`members_of`、`nonstatic_data_members_of`、`bases_of` 等函数都要求第二个实参 `std::meta::access_context`（[[meta.reflection.access.context]]），它只能从三个函数得到：

| 函数 | 代表的上下文 |
|---|---|
| `access_context::current()` | 调用处最近的外层命名空间、类或函数（[[meta.reflection.access.context#5]]） |
| `access_context::unprivileged()` | 全局命名空间，只能看到公有成员 |
| `access_context::unchecked()` | 所有成员都可访问 |

没有办法伪造一个更有特权的上下文。需要看私有成员的库必须写出 `unchecked()`，代码审查时一眼就能找到。库函数把 `ctx` 当作形参一路传下去，调用者的友元身份也就跟着传了过去。

另一半规则在拼接这边：成员一旦经由 `[: m :]` 指称，从任何位置都可以访问（[[class.access.base#5]]）。访问控制在取得反射的时候检查一次，不在使用时再检查。

### 查询失败怎么办

`template_of(^^int)` 这样的调用没有合理的结果。[[P3560R2]] 列出了四种选择：返回一个类似 NaN 的无效反射；返回 `std::expected`；让调用不是常量表达式；抛出异常。

无效反射不适用于返回 `vector` 的函数；不是常量表达式虽然一致，但用户没有办法恢复。P2996R13 偏向异常，并举了一个 `std::expected` 会出错的例子：`requires (template_of(^^T) == ^^std::optional)` 中，`expected` 与 `info` 的比较会安静地得到 `false`，掩盖了错误。异常的常见顾虑，比如运行期开销和目标文件大小，在编译期都不存在。最终 C++26 采用异常：查询失败时抛出 `std::meta::exception`（[[meta.reflection.exception]]），它可以在同一次常量求值中被捕获。编译期异常本身见 [[papers/constexpr-exceptions|编译期异常]]。

### 删掉和推迟的

P2996 明确说自己是 P1240 的一个子集，先做小是为了更早进入语言（§2）。下面这些被推迟了：

- 表达式反射。早期修订版允许反射常量表达式。P2996 自己引入了常量求值的副作用之后，同一个常量表达式每次拼接都要重新求值，这条路走不通，论文把它推迟到以后的 `^^(expr)` 语法（§4.1）。
- 区间拼接，理由见上。
- 通用的代码注入。P2996 认为沿着 [[P2237R0]] 的方向做代码注入是值得追求的，但 C++26 只有 `define_aggregate`，给一个不完整的类补上数据成员。用记号序列描述注入代码的 [[P3294R2]] 截至写作时没有被采纳。

## 最终设计和措辞

### 一个例子

下面按当前草案写一个打印结构体字段名和值的函数。本机 Clang 23 不支持 `^^`，也没有 `<meta>` 头文件，所以这段代码没有经过编译，不标判定：

```cpp
#include <meta>
#include <print>
#include <string>

struct Point { int x; double y; std::string label; };

template <class T>
void print_fields(const T& obj) {
  constexpr auto ctx = std::meta::access_context::current();
  template for (constexpr std::meta::info m :
                std::define_static_array(
                    std::meta::nonstatic_data_members_of(^^T, ctx))) {
    std::println("{} = {}", std::meta::identifier_of(m), obj.[:m:]);
  }
}

int main() {
  print_fields(Point{1, 2.5, "origin"});
}
```

每一个部件对应一处措辞：

| 部件 | 作用 | 条款 |
|---|---|---|
| `^^T` | 反射运算符，得到 `std::meta::info` 类型的纯右值 | [[expr.reflect#1]] |
| `std::meta::info` | 新的基本类型；它的值叫做反射，有唯一的空反射 | [[basic.fundamental#17]] |
| `nonstatic_data_members_of(^^T, ctx)` | 按 `ctx` 筛出可访问的成员，按声明顺序返回 | [[meta.reflection.member.queries#4]] |
| `define_static_array` | 把编译期的 `vector` 复制成静态存储的数组 | [[meta.define.static]] |
| `template for` | 对每个元素实例化一次循环体，`m` 每次都是常量 | [[stmt.expand#5]] |
| `obj.[:m:]` | 拼接成员，构成成员访问表达式 | [[basic.splice#1]]、[[expr.prim.splice]] |
| `identifier_of(m)` | 取得成员的名字 | [[meta.reflection.names]] |

`define_static_array` 不能省。循环变量声明为 `constexpr` 时，展开语句把区间保存在一个 `constexpr` 变量里（[[stmt.expand#5.2]]），而 `std::vector` 在常量求值中分配的内存不能留到求值结束之后。[[P3491R3]] 提供的 `define_static_string`、`define_static_array` 正是为了在编译期分配还不能保留的时候，把结果提升到静态存储。

### 新增的条款

反射在草案里分布在语言和库两部分：

- [[expr.reflect]]：反射运算符的语法和每种操作数得到什么。`^^` 后面尽量吞下最长的记号序列，`^^int && true` 中的 `&&` 会被当成右值引用声明符（[[expr.reflect#3]]）。
- [[basic.splice]]、[[expr.prim.splice]]、[[dcl.type.splice]]：拼接说明符，以及它出现在表达式和类型位置时的含义。
- [[expr.const.const]]：哪些值只能留在编译期，下一节详细讲。
- [[expr.const.reflect]]：`define_aggregate` 产生的**注入声明**（injected declaration）放在什么位置，怎样保证结果不依赖求值顺序。
- [[meta.reflection]]：头文件 `<meta>` 里的全部查询函数、`access_context` 和 `std::meta::exception`。

### 配套的几篇提案

几篇提案和 P2996 一起进入 C++26，各自补一块：

| 提案 | 内容 | 条款 |
|---|---|---|
| [[P1306R5]] | 展开语句 `template for` | [[stmt.expand]] |
| [[P3289R1]] | `consteval { ... }` 块 | [[dcl.pre#15]] |
| [[P3394R4]] | 注解 `[[=expr]]` | [[dcl.attr.annotation]] |
| [[P3491R3]] | `define_static_string`、`define_static_array` 等 | [[meta.define.static]] |

consteval 块的动机来自 `define_aggregate`。这个调用的意义全在副作用上，以前只能塞进 `static_assert(is_type(define_aggregate(...)))`，读起来像在断言什么。P3289R1 提供了一个专门的位置，草案规定能产生注入声明的表达式只能出现在 consteval 块里（[[expr.const.core#2.32]]）：

```cpp
struct Storage;
consteval {
  std::meta::define_aggregate(^^Storage, {
    std::meta::data_member_spec(^^int, {.name = "x"}),
  });
}
Storage s{42};   // Storage 现在有一个 int 成员 x
```

注解解决的是给声明附加信息的问题。属性不行，因为属性可以被实现忽略，也没有一个值可以返回。P3394R4 在属性语法上加了一个 `=`，后面跟一个常量表达式，它的值可以用 `annotations_of` 读出来：

```cpp
struct Skip {};
struct Config {
  int port;
  [[=Skip{}]] std::string cache;   // 序列化时跳过
};
// annotations_of_with_type(^^Config::cache, ^^Skip) 非空
```

以上两段同样没有经过编译。

### 附录 C 里的不兼容

新记号破坏了两种极少见的旧代码：

<div class="compare" markdown="1">

```cpp
struct C { int operator^(int); };
int operator^(int (C::*p)(int), C);
int i = &C::operator^^C{};
// 现在 ^^ 是一个记号：非良构
```

```cpp
struct [[using CC:]] C;
// 现在 :] 是一个记号：非良构
struct [[using DD: ]] D;  // OK
```

</div>

左边见 [[diff.cpp23.lex#1]]，右边见 [[diff.cpp23.dcl.dcl#3]]。此外 `<meta>` 成了新的标准头文件名（[[diff.cpp23.library]]）。

## 后果

### 反射值不能进入运行期

反射在运行期没有意义，所以必须挡在编译期。P2996R13 的做法是**编译期专用类型**（consteval-only type）：`info` 以及任何含有 `info` 的类型，包括 `info*` 和带 `info` 成员的类，它们的对象只能存在于编译期（§4.3.3）。

这个规则后来出了问题。[[P4101R1]] 记录了 [[CWG3150]] 的例子：一个类是不是编译期专用类型取决于它的成员，而类可能还不完整。

```cpp
struct S;
void f(S*);    // #1
struct S {     // #2
  std::meta::info x;
};
```

`#2` 的定义是否让 `#1` 事后变成非良构？如果 `S` 是模板特化，判断它还要求实例化，而现有的大量代码依赖于此处不实例化。P4101R1 把规则改成按值判断，已被采纳进草案，论文标题写明它针对 C++26。当前草案里，**编译期专用值**（consteval-only value，[[g:consteval-only-value]]）是非空的反射，或者指向立即函数的指针（[[expr.const.const#1]]）；含有这种值的对象叫**立即对象**（immediate object），只能是 `constexpr` 变量的对象、模板形参对象，或者生存期完全在一次常量求值之内的对象（[[expr.const.const#3]]）。两种模型的区别在空反射上：

<div class="compare" markdown="1">

```cpp
// P2996R13：按类型判断
std::meta::info null;      // 非良构
auto f(std::meta::info) {} // 非良构：
                           // 须为 consteval
auto r = ^^int;            // 非良构
```

```cpp
// 当前草案：按值判断
std::meta::info null;      // OK：空反射
auto f(std::meta::info) {} // OK
auto r = ^^int;            // 非良构：
                           // 不是 constexpr
```

</div>

两边都来自 P4101R1 §4.3，没有编译验证。真正带着反射的对象两边都拒绝，只是理由从类型换成了值。

### 编译期的代价

反射把元编程搬进了常量求值器。常量求值是解释执行的，步数受实现限制（[[topics/compile-time-programming]]）。基于值的设计避免了为每一步创建一个类型，但遍历一个大命名空间、对每个成员实例化一次循环体，开销仍然要在编译时付。本机没有可用的实现，这里不给测量数字。

### 实现状况

本机 Homebrew Clang 23 不支持 `^^`、consteval 块和注解，也没有 `<meta>`，但已经支持 `template for`。据 P2996R13 §2.3，EDG 有一个实验实现，Bloomberg 开源了一个 Clang 分支（clang-p2996），两者都能在 Compiler Explorer 上使用，论文说两者都不完整。前文未经编译的例子是按当前草案写的，没有在这些实现上核对，不给出判定。

用反射生成编译期注册表的写法见 [[patterns/factory-and-registration]]。

## 思考题

!!! question "1"
    下面的库函数想返回调用者能访问的所有数据成员。它有什么问题？怎样改？
    ```cpp
    consteval auto visible_members(std::meta::info cls) {
      return std::meta::nonstatic_data_members_of(
          cls, std::meta::access_context::current());
    }
    ```

<details markdown="1">
<summary>答案</summary>

`current()` 代表它在源码中出现的位置，也就是 `visible_members` 自己（[[meta.reflection.access.context#5]]），而不是调用者。如果调用者是 `cls` 的友元，友元身份在这里丢掉了，结果只剩 `visible_members` 能访问的成员。正确的做法是把 `access_context` 作为形参，由调用者在自己的位置写 `access_context::current()` 传进来。这正是 [[P3547R1]] 反对隐式按调用点检查的理由。
</details>

!!! question "2"
    `template for (constexpr auto e : std::meta::enumerators_of(^^E))` 为什么不行，要先套一层 `std::define_static_array`？

<details markdown="1">
<summary>答案</summary>

循环变量是 `constexpr` 时，展开语句把区间保存在一个 `constexpr` 变量里（[[stmt.expand#5.2]]）。`enumerators_of` 返回的 `std::vector` 在常量求值中分配了内存，这块内存不能在求值结束后继续存在，所以不能初始化一个 `constexpr` 变量。`define_static_array` 把元素复制进一个静态存储的数组，返回指向它的 `span`，就可以了（[[meta.define.static]]）。
</details>
