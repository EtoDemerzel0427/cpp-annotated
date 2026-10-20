---
title: 变参模板
summary: 包和包展开：四种包，包展开能出现在哪些地方，一个包由哪个展开来展开，以及 sizeof...、包索引、折叠表达式等各种展开的实例化结果。
status: done
covers: temp.variadic
since: c++11
papers: N2242, N4295, P0036R0, P0780R2, P2662R3, P1061R10, P2893R3, P0195R2
related: temp.param, expr.prim.fold, expr.prim.id, dcl.struct.bind, expr.prim.lambda, temp.deduct.type, temp.func.order, temp.constr.fold, dcl.fct
tags: 模板, 变参模板, 包展开, 折叠表达式, 包索引
updated: 2026-10-19
---

!!! tldr
    - 包是代表零个或多个元素的名字，共四种：模板形参包、函数形参包、init-capture 包（C++20）和结构化绑定包（C++26）。
    - 包展开是一个模式后跟 `...`，实例化时对每个元素各实例化一次模式。它只能出现在标准列出的 18 种语境里，`ts...;` 这样的语句不合法。
    - 一个包名只由包住它的最内层展开来展开；同一个展开里的几个包同步展开，元素个数必须相同；包名没有被展开是错误。
    - 一元折叠遇到空包时，只有 `&&`（`true`）、`||`（`false`）和 `,`（`void()`）有值，`(ts + ...)` 对空包非良构。
    - 空包展开不改变语法解释：模板定义时解析成变量声明的语句，实例化时不会因为实参变空而变成函数声明。

## 包与包展开

```cpp run ok
#include <cstdio>
template<class... Ts>
int print(const Ts&... ts) {
    ((std::printf("%d ", ts)), ...);
    std::puts("");
    return sizeof...(ts);
}
int main() {
    print();            // 空行
    print(1, 2, 3);     // 1 2 3
}
```

**变参模板**（variadic template）能接受任意多个模板实参或函数实参。C++11 之前，`std::bind`、`make_shared` 这类组件只能用预处理器为 0、1、2、…、N 个参数分别生成重载；有了变参模板，一个声明就覆盖所有个数。

上例中的 `Ts` 和 `ts` 都是**包**（pack）：一个代表零个或多个元素的名字。`((std::printf("%d ", ts)), ...)` 是一个**包展开**（pack expansion），由**模式**（pattern）`std::printf("%d ", ts)` 和省略号组成，实例化时对包里的每个元素各实例化一次模式。`sizeof...(ts)` 给出元素个数。

相关的语法规则分散在其他条款：模板形参包在 [[temp.param]]，函数形参包在 [[dcl.fct]]，捕获在 [[expr.prim.lambda.capture]]，结构化绑定包在 [[dcl.struct.bind]]，折叠在 [[expr.prim.fold]]，包索引在 [[expr.prim.id]]。本节规定它们共同的部分。

## 四种包（¶1–5）

### 模板形参包（¶1）

¶1 **模板形参包**（template parameter pack）是接受零个或多个模板实参的模板形参。

```cpp error
template<class... Types> struct Tuple { };

Tuple<> t0;                     // Types 为空
Tuple<int> t1;                  // Types = {int}
Tuple<int, float> t2;           // Types = {int, float}
Tuple<0> bad;                   // error: 0 不是类型
```

三种模板形参都可以是包：类型形参包 `class... Ts`，常量形参包 `int... Ns` 或 `auto... Vs`，模板模板形参包 `template<class> class... TTs`。C++26 起还有变量模板和概念作模板模板形参的包（[[temp.param]]）。

### 函数形参包（¶2）

¶2 **函数形参包**（function parameter pack）是接受零个或多个函数实参的函数形参：

```cpp run ok
template<class... Types> int f(Types... args) { return sizeof...(args); }

int main() {
    return f()            // args 为空
         + f(1)           // args: int
         + f(2, 1.0)      // args: int, double
         - 3;
}
```

声明 `Types... args` 本身就是一个包展开（下文的 ¶6.1）：模式是 `Types args`，它展开了模板形参包 `Types`，同时声明了包 `args`。

### init-capture 包（¶3）

¶3 **init-capture 包**（init-capture pack）是一个 lambda 捕获，它为初始化器展开出的每个元素各引入一个带初始化器的捕获。这是 C++20 的 [[P0780R2]] 加入的：

```cpp run ok
#include <memory>
#include <utility>
template<class... Args>
auto make_task(Args... args) {
    return [...xs = std::move(args)]() mutable {   // 每个元素一个移动初始化的捕获
        return (0 + ... + *xs);
    };
}
int main() {
    auto t = make_task(std::make_unique<int>(1), std::make_unique<int>(2));
    return t() - 3;
}
```

在 init-capture 里，`...` 写在名字前面（`...xs = expr`），和声明形参包 `Ts... ts` 一致：`...` 紧挨在被声明的名字左边，表示这个名字是包。

### 结构化绑定包（¶4）{{c++26}}

¶4 **结构化绑定包**（structured binding pack）是一个带 `...` 的结构化绑定名字，引入零个或多个结构化绑定（[[dcl.struct.bind]]，[[P1061R10]]）：

```cpp run ok
struct Point3 { int x, y, z; };

template<class T>
int sum_fields(const T& t) {
    auto& [...fs] = t;                 // fs: x, y, z
    return (fs + ... + 0);
}
template<class T>
int tail_count(const T& t) {
    auto& [first, ...rest] = t;        // rest: y, z
    (void)first;
    return sizeof...(rest);
}
int main() {
    Point3 p{1, 2, 3};
    return sum_fields(p) - 6 + tail_count(p) - 2;
}
```

一个结构化绑定声明里最多有一个包，它的元素个数是总个数减去其他名字的个数，可以为零。含结构化绑定包的声明必须声明模板化实体（[[dcl.pre#7]]），所以只能出现在模板或泛型 lambda 这类模板化语境中：

```cpp error
struct P { int a, b; };
int f() {
    auto [...xs] = P{1, 2};    // error: 不在模板化语境中
    return sizeof...(xs);
}
```

包展开要到模板实例化时才替换成元素列表，非模板代码里没有实例化这一步。在普通函数里需要时，可以把代码包进一个泛型 lambda。

### 元素个数（¶5）

¶5 包是以上四种的统称。模板形参包和函数形参包的元素个数，是为它提供的实参个数；init-capture 包的元素个数，是它的初始化器展开出的元素个数；结构化绑定包的元素个数由 [[dcl.struct.bind]] 规定。

## 包展开能出现在哪里（¶6）

¶6 包展开由模式和省略号组成，实例化后产生一个列表，含零个或多个模式的实例。模式的形式取决于展开所在的语境，能出现的语境只有下面这些：

| ¶ | 语境 | 模式 | 例子 |
|---|---|---|---|
| 6.1 | 函数形参包 [[dcl.fct]] | 去掉省略号的形参声明 | `void f(Ts... ts)` |
| 6.2 | using 声明 [[namespace.udecl]] | *using-declarator* | `using Bs::operator()...;` |
| 6.3 | 友元类型声明 [[class.mem.general]] {{c++26}} | *friend-type-specifier* | `friend Ts...;` |
| 6.4 | 本身是包展开的模板形参包 [[temp.param]] | 去掉省略号的形参声明 | `template<Ts... vs>` |
| 6.5 | *initializer-list* [[dcl.init]] | *initializer-clause* | `g(args...)`、`int a[]{ts...}` |
| 6.6 | 基类列表 [[class.derived]] | *base-specifier* | `struct D : Bs...` |
| 6.7 | 指名基类的成员初始化器 | *mem-initializer* | `D() : Bs(0)...` |
| 6.8 | 模板实参列表 [[temp.arg]] | 模板实参 | `tuple<Ts*...>` |
| 6.9 | 属性列表 [[dcl.attr.grammar]] | 属性 | `[[vendor::attr...]]` |
| 6.10 | 注解列表 {{c++26}} | 注解 | `[[=Vs...]]` |
| 6.11 | 对齐说明符 [[dcl.align]] | 去掉省略号的 `alignas` | `alignas(Ts...)` |
| 6.12 | 捕获列表 [[expr.prim.lambda.capture]] | 去掉省略号的捕获 | `[args...]`、`[&args...]`、`[...xs = args]` |
| 6.13 | `sizeof...` | 标识符 | `sizeof...(Ts)` |
| 6.14 | 包索引表达式 {{c++26}} | 标识符 | `ts...[0]` |
| 6.15 | 包索引类型 {{c++26}} | *typedef-name* | `Ts...[0]` |
| 6.16 | 包索引模板名 {{c++29}} | *simple-template-name* | `TTs...[0]<int>` |
| 6.17 | 折叠表达式 [[expr.prim.fold]] | 含未展开包的那个操作数 | `(ts + ...)` |
| 6.18 | 折叠展开约束 [[temp.constr.fold]] {{c++26}} | 该约束 | `requires (C<Ts> && ...)` |

标准的例 5 是 `f(&rest...)`：`&rest...` 是包展开，`&rest` 是它的模式。

表外的地方都不能展开。`ts...;`、`g(ts)...;`、`x = ts...;` 都不合法。C++17 之前，要对每个元素执行一条语句，只能借数组初始化把展开放进 *initializer-list*（6.5）：`int dummy[] = {(g(ts), 0)...};`。C++17 起改写成逗号折叠 `(g(ts), ...);`（6.17）。

另外几点：

- 成员初始化器只能展开基类（6.7）。数据成员都有各自的名字，不存在成员包，所以 `: a(as)...` 非良构。
- 属性列表在语法上可以展开，但每个属性得自己允许 `...`，标准属性都不允许，所以这只对厂商属性有意义。
- 6.4 让形参的类型来自外层的包：`template<class... Ts> struct X { template<Ts... vs> struct Y; };` 中，`X<int, char>::Y` 接受一个 `int` 常量和一个 `char` 常量。

```cpp run ok
#include <cstdio>
// 6.2 + 6.6：overload 惯用法
template<class... Fs> struct overload : Fs... { using Fs::operator()...; };

// 6.6 + 6.7：每个基类一个成员初始化器
struct B1 { int a; };
struct B2 { int b; };
template<class... Bases> struct D : Bases... {
    D(Bases... bs) : Bases(bs)... { }
};

// 6.11：取最严格的对齐
template<class... Ts> struct alignas(Ts...) Storage { unsigned char buf[16]; };
static_assert(alignof(Storage<char, double, short>) == alignof(double));

// 6.4：形参的类型来自外层包
template<class... Ts> struct X { template<Ts... vs> struct Y { }; };
X<int, char>::Y<1, 'c'> y;

// 6.12：按引用捕获包
template<class... Args> auto summer(Args&... args) { return [&args...] { return (args + ...); }; }

int main() {
    auto o = overload{[](int) { return 1; }, [](double) { return 2; }};
    D<B1, B2> d{B1{1}, B2{2}};
    int a = 1, b = 2;
    std::printf("%d %d %d\n", o(1), o(1.0), summer(a, b)());   // 1 2 3
    (void)d; (void)y;
}
```

¶7 很多规则是针对非包实体写的，比如 [[dcl.fct]] 对函数形参的要求，或者常量模板形参必须是结构化类型。判断一个包是否满足这类规则时，把它看作模式实例化后得到的那些实体。有了这一条，标准就不必在每处都写上"或……的包"。

## 谁展开谁（¶8）

¶8 规定了一个包由哪个展开来展开：

1. 包名出现在某个包展开的模式里，就由这个展开来展开它。
2. 包名的每一次出现，只由包住它的最内层展开来展开。
3. 模式里必须至少有一个包没有被内层展开展开掉，这些包叫做模式的**未展开包**（unexpanded packs）。
4. 一个展开所展开的所有包，元素个数必须相同，它们同步展开。
5. 包名出现了却没有被任何展开展开，程序非良构。

```cpp error
template<typename...> struct Tuple { };
template<typename T1, typename T2> struct Pair { };

template<class... Args1> struct zip {
    template<class... Args2> struct with {
        typedef Tuple<Pair<Args1, Args2>...> type;   // Args1 与 Args2 同步展开
    };
};

typedef zip<short, int>::with<unsigned short, unsigned>::type T1;
    // OK: Tuple<Pair<short, unsigned short>, Pair<int, unsigned>>
typedef zip<short>::with<unsigned short, unsigned>::type T2;
    // error: Args1 与 Args2 元素个数不同

template<class... Args> void f(Args...);
template<class... T> int h(T...);

template<class... Args>
void g(Args... args) {                      // OK：Args 由函数形参包 args 展开
    f(const_cast<const Args*>(&args)...);   // OK：Args 和 args 同步展开
    f(5 ...);                               // error: 模式中没有包
    f(args);                                // error: args 没有展开
    f(h(args...) + args...);                // OK
}
```

最后一行有两个 `args`。第一个的最内层展开是 `h` 的实参 `args...`，在那里已经展开完毕；外层展开的模式是 `h(args...) + args`，未展开包只剩第二个 `args`。所以当 `args` 为 `{a, b}` 时，结果是 `f(h(a, b) + a, h(a, b) + b)`。

同一个包在内外两层各展开一次，就得到两两组合：

```cpp run ok
#include <tuple>
#include <type_traits>
template<class... Ts>
auto square(Ts... ts) {
    return std::tuple{ std::tuple{ts, ts...}... };   // 外层模式中只有第一个 ts 未展开
}
int main() {
    auto p = square(1, 2);
    // p == tuple{ tuple{1, 1, 2}, tuple{2, 1, 2} }
    static_assert(std::is_same_v<decltype(p),
        std::tuple<std::tuple<int, int, int>, std::tuple<int, int, int>>>);
    return std::get<2>(std::get<0>(p)) - 2;
}
```

同步展开常用来把一个包和一列下标配对：

```cpp run ok
#include <cstddef>
#include <tuple>
#include <type_traits>
#include <utility>
template<class T, std::size_t... Is>
auto reverse_impl(const T& t, std::index_sequence<Is...>) {
    return std::tuple{ std::get<sizeof...(Is) - 1 - Is>(t)... };
}
template<class... Ts>
auto reverse(const std::tuple<Ts...>& t) {
    return reverse_impl(t, std::index_sequence_for<Ts...>{});
}
int main() {
    auto r = reverse(std::tuple{1, 2.0, 'c'});
    static_assert(std::is_same_v<decltype(r), std::tuple<char, double, int>>);
    return std::get<2>(r) - 1;
}
```

`sizeof...(Is)` 本身也是一个包展开（6.13），把 `Is` 完全展开了。所以外层模式 `std::get<sizeof...(Is) - 1 - Is>(t)` 中，未展开的只有最后那个 `Is`。

## 实例化（¶9–17）

### 逐个替换元素（¶9）

¶9 实例化一个包展开时，设被展开的包有 N 个元素，依次生成 E₁、E₂、…、E_N：第 i 项是把模式中每个被展开的包替换成它的第 i 个元素得到的。替换进去的元素按下面的方式理解：

- ¶9.1 模板形参包：类型形参包的元素是一个 *typedef-name*，常量形参包的元素是一个 *id-expression*，模板模板形参包的元素是一个 *template-name*，都指第 i 个实参；
- ¶9.2 函数形参包：指第 i 个函数形参的 *id-expression*；
- ¶9.3 init-capture 包：指第 i 个捕获引入的变量的 *id-expression*；
- ¶9.4 结构化绑定包：指第 i 个结构化绑定的 *id-expression*。

元素是 *typedef-name* 意味着替换不是文本替换。`Ts` 为 `{int&}` 时，`const Ts&` 得到 `int&`：加在引用类型上的 const 被忽略，两层引用折叠成一层。文本替换会得到不合法的 `const int& &`。

### 空包不改变语法（¶9）

!!! std
    When N is zero, the instantiation of a pack expansion does not alter the syntactic interpretation of the enclosing construct, even in cases where omitting the pack expansion entirely would otherwise be ill-formed or would result in an ambiguity in the grammar.

N 为零时，包展开不改变外围结构的语法解释，即使把展开整个删掉会导致非良构或文法歧义。语法分析在模板定义时已经完成，实例化时不会重新解析。¶17 的例子演示了这一点：

```cpp run ok
template<class... T> struct X : T... { int v; };
template<class... T> int f(T... values) {
    X<T...> x(values...);      // 定义时已解析为变量 x 的直接初始化
    return x.v;
}
template int f<>();            // OK：X<> 没有基类
int main() { return f<>(); }   // 返回 0
```

把 `values...` 删掉，得到的 `X<> x();` 在普通代码里是函数声明（最令人烦恼的解析）。但这里 `x` 在模板定义时已经确定是变量，实例化不改变这一点。空的 `()` 初始化器表示值初始化，`X<>` 没有用户提供的构造函数，所以先零初始化，`x.v` 为 0。

### sizeof...（¶10）

¶10 `sizeof...` 表达式实例化为值为 N 的整型常量，类型是 `std::size_t`（[[expr.sizeof]]）。它的操作数只能是包名：

```cpp error
template<class... Ts> int h(Ts... ts) { return sizeof...(ts) + sizeof...(Ts); }   // OK
int x = 3;
int k = sizeof...(x);           // error: x 不是包
```

### 包索引（¶11–13）{{c++26}}

¶11–13 C++26 的包索引（[[P2662R3]]）直接取包的第 K 个元素：包索引表达式 `ts...[K]` 实例化为 E_K 这个 *id-expression*，包索引类型 `Ts...[K]` 实例化为 *typedef-name* E_K，包索引模板名实例化为 *simple-template-name* E_K。K 必须是 `std::size_t` 类型的转换常量表达式，且 0 ≤ K < N（[[expr.prim.id]]、[[dcl.type]]、[[temp.names]]）。

```cpp run ok
#include <type_traits>
template<class... Ts> using First = Ts...[0];
template<class... Ts> using Last  = Ts...[sizeof...(Ts) - 1];
template<auto... Vs>  constexpr auto second = Vs...[1];

template<class... Ts>
auto last_arg(Ts... ts) { return ts...[sizeof...(ts) - 1]; }

static_assert(std::is_same_v<First<int, char, double>, int>);
static_assert(std::is_same_v<Last<int, char, double>, double>);
static_assert(second<1, 2, 3> == 2);
int main() { return last_arg(1, 2.0, 3) - 3; }
```

```cpp error
template<class... Ts> using At5 = Ts...[5];
At5<int, char> a;               // error: 索引越界
```

包索引本身就是一个包展开，所以不必再写 `...`。编译器直接按下标取元素，不必像 `std::tuple_element_t<I, std::tuple<Ts...>>` 那样实例化辅助模板。

!!! warning "Clang 的支持情况"
    本机 Clang 23 支持包索引类型和包索引表达式，但还不支持包索引模板名：`TTs...[0]<int>` 会报语法错误。

### 对齐说明符（¶14）

¶14 `alignas(Ts...)` 实例化为 `alignas(E₁) alignas(E₂) … alignas(E_N)`，多个 `alignas` 取最严格的（[[dcl.align]]）。N 为零时什么也不产生，等于没有对齐要求。

### 折叠表达式（¶15）

¶15 折叠表达式实例化成的形状如下，*op* 是折叠运算符，二元折叠中的 E 是不含未展开包的那个操作数：

| 形式 | 名称 | 展开为 |
|---|---|---|
| `(... op pack)` | 一元左折叠 | `(((E₁ op E₂) op …) op E_N)` |
| `(pack op ...)` | 一元右折叠 | `(E₁ op (… op (E_{N−1} op E_N)))` |
| `(init op ... op pack)` | 二元左折叠 | `(((init op E₁) op E₂) op … op E_N)` |
| `(pack op ... op init)` | 二元右折叠 | `(E₁ op (… op (E_N op init)))` |

`...` 在左边就是左结合，在右边就是右结合。

```cpp run ok
template<class... Args>
bool all(Args... args) { return (... && args); }   // ((E1 && E2) && E3) && E4

template<class... Args>
int minus_left(Args... args)  { return (... - args); }   // (1 - 2) - 3 == -4
template<class... Args>
int minus_right(Args... args) { return (args - ...); }   // 1 - (2 - 3) == 2

int main() {
    bool b = all(true, true, true, false);
    return (b ? 1 : 0) + (minus_left(1, 2, 3) + 4) + (minus_right(1, 2, 3) - 2);
}
```

一元折叠遇到空包时，只有三个运算符有值（表 20 [tab:temp.fold.empty]），其他运算符的实例化非良构：

| 运算符 | 空包时的值 |
|---|---|
| `&&` | `true` |
| `\|\|` | `false` |
| `,` | `void()` |

二元折叠总有值，空包时结果就是 `init`：

```cpp error
template<class... Ts> auto sum(Ts... ts) { return (ts + ...); }
template<class... Ts> auto sum0(Ts... ts) { return (ts + ... + 0); }
int a = sum0();                 // OK：二元折叠，结果为 0
int b = sum(1, 2);              // OK
int c = sum();                  // error: + 的一元折叠不能用空包
```

`+` 没有默认值 0，是因为 `+` 可以重载，单位元随类型而变：字符串拼接的单位元是空串，矩阵加法的是零矩阵。最初的提案 [[N4295]] 为 `+`、`*`、`&`、`|` 也规定了空包值，C++17 发布前被 [[P0036R0]] 删去，只留下与类型无关的三个（另见 [[expr.prim.fold]]）。需要单位元时就写二元折叠，明确给出初值。

### 折叠展开约束（¶16）{{c++26}}

¶16 折叠展开约束不做实例化。`template<class... Ts> requires (C<Ts> && ...)` 中的折叠在约束规范化时变成折叠展开约束（[[temp.constr.fold]]），检查时按顺序对每个元素检查 `C`；对 `&&`，遇到第一个不满足的元素就停止，后面的元素不再替换。它不会先实例化成一个大表达式，所以两个这样的约束可以逐元素比较包含关系（[[temp.constr.order]]）。

### 其他展开（¶17）

¶17 其余包展开实例化为列表 E₁, E₂, …, E_N，列表的种类视语境而定，如表达式列表、基类列表、模板实参列表。N 为零时得到空列表：空包时 `struct X : T...` 没有基类，`f(args...)` 是无实参调用，`tuple<Ts...>` 是 `tuple<>`。

## 推导中的包

下面几条规则在其他条款里，但写变参模板时经常碰到：

- 函数形参包只有位于形参列表末尾时，才能从调用实参推导。位于中间时它是非推导语境（[[temp.deduct.type]]），没有显式指定就推导为空包。
- 主类模板、主变量模板和别名模板的模板形参包必须是最后一个模板形参。函数模板的形参包后面可以还有模板形参，只要它们能被推导或有默认值（[[temp.param]]）。
- 偏序中，两个模板难分高下时，没有尾随函数形参包的那个更特化（[[temp.deduct.partial#11]]），见 [[temp.func.order]]。

```cpp error
template<class... Ts, class Last>
void back(Ts..., Last) { }
int main() {
    back(1, 2, 3);             // error: Ts 推导为空，函数只有一个形参
    back<int, int>(1, 2, 3);   // OK：Ts = {int, int}，Last 从第三个实参推导
}
```

!!! impl "编译开销"
    C++11/14 的变参技巧大多靠递归实例化：剥掉第一个元素，对剩下的递归。N 个元素会产生 N 个特化，每个特化又带着长度为 O(N) 的实参列表，总代价是 O(N²)。折叠表达式、包索引、`std::index_sequence` 配合同步展开，都能把这种递归换成一层展开。编译器对递归实例化深度有上限，Clang 和 GCC 可以用 `-ftemplate-depth=` 调整。

!!! history "演进"
    | 标准 | 变化 |
    |---|---|
    | C++11 | 变参模板、模板和函数形参包、包展开、`sizeof...`（[[N2242]]） |
    | C++17 | 折叠表达式（[[N4295]]）；using 声明中的展开 `using Bs::f...;`（[[P0195R2]]） |
    | C++20 | init-capture 包 `[...xs = args]`（[[P0780R2]]） |
    | C++26 | 包索引（[[P2662R3]]）；结构化绑定包（[[P1061R10]]）；变参友元 `friend Ts...;`（[[P2893R3]]）；注解列表中的展开；折叠展开约束 |

!!! pitfall "逗号折叠与重载的逗号"
    内置逗号运算符从左到右求值，所以 `(f(args), ...)` 按实参顺序调用 `f`。但如果 `f` 的返回类型重载了 `operator,`，折叠会调用那个重载。稳妥的写法是 `(void(f(args)), ...)`。

## 思考题

!!! question "思考题 1"
    设 `args` 为 `{a, b}`、`Args` 为 `{A, B}`，下面每个展开得到什么？

    ```cpp
    f(g(args)...);                 // (1)
    f(g(args...));                 // (2)
    f(g(args, args...)...);        // (3)
    f(sizeof...(Args) + args...);  // (4)
    ```

<details markdown="1">
<summary>答案</summary>

1. `f(g(a), g(b))`，模式是 `g(args)`。
2. `f(g(a, b))`，展开发生在 `g` 的实参列表里。
3. `f(g(a, a, b), g(b, a, b))`。内层 `args...` 先完全展开，外层模式 `g(args, args...)` 中只有第一个 `args` 未展开。
4. `f(2 + a, 2 + b)`。`sizeof...(Args)` 自己是一个完整的展开，外层模式中的未展开包只有 `args`。
</details>

!!! question "思考题 2"
    为什么 `template<class... Ts> void f(Ts..., int)` 用 `f(1, 2)` 调用会失败，而 `f<int>(1, 2)` 成功？

<details markdown="1">
<summary>答案</summary>

不在形参列表末尾的函数形参包是非推导语境（[[temp.deduct.type]]），推导不会给它分配实参。没有被推导也没有显式指定的尾随模板形参包推导为空包（[[temp.arg.explicit]]），于是函数类型是 `void(int)`，两个实参对一个形参，不可行。显式指定 `Ts = {int}` 后，函数类型是 `void(int, int)`，可行。
</details>
