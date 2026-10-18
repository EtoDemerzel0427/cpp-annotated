---
title: 变参模板
summary: 四种包（模板形参包、函数形参包、init-capture 包、结构化绑定包）；包展开 = 模式 + 省略号，以及它能出现的全部 18 种语境；未展开包、最内层展开、同步展开要求等长；实例化规则：sizeof...、包索引、折叠表达式的展开形状与空包值、空展开不改变语法解释
status: done
covers: temp.variadic
since: c++11
papers: N2242, N4295, P0036R0, P0780R2, P2662R3, P1061R10, P2893R3, P0195R2
related: temp.param, expr.prim.fold, expr.prim.id, dcl.struct.bind, expr.prim.lambda, temp.deduct.type, temp.func.order, temp.constr.fold, dcl.fct
tags: 模板, 变参模板, 包展开, 折叠表达式, 包索引
updated: 2026-10-18
---

**变参模板**（variadic template）让一个模板接受**任意多个**模板实参或函数实参。C++11 之前，`std::tuple`、`std::bind`、`make_shared` 这类组件只能靠"重载 0、1、2、……、N 个参数"的预处理器宏堆出来；有了变参模板，一个声明就覆盖所有元数。

这一节的核心是两个概念：

- [[g:pack|**包**]]（pack）：一个"装着零个或多个元素"的名字；
- [[g:pack-expansion|**包展开**]]（pack expansion）：一个**模式**（pattern）后跟 `...`，实例化时对包中每个元素实例化一次模式，产生一个列表。

本节先定义四种包（¶1–5），再规定包展开能出现在哪里（¶6）、怎样判定哪些包被哪个展开所展开（¶7–8），最后规定各种展开的实例化结果（¶9–17）。语法细节分散在 [[temp.param]]（模板形参包）、[[dcl.fct]]（函数形参包）、[[expr.prim.lambda.capture]]（捕获）、[[dcl.struct.bind]]（结构化绑定包）、[[expr.prim.fold]]（折叠）、[[expr.prim.id]]（包索引表达式）。

---

## 四种包（¶1–5）

### 模板形参包（¶1）

¶1 [[g:template-parameter-pack|**模板形参包**]]（template parameter pack）是接受零个或多个模板实参的模板形参。

```cpp error
template<class... Types> struct Tuple { };

Tuple<> t0;                     // Types 为空
Tuple<int> t1;                  // Types = {int}
Tuple<int, float> t2;           // Types = {int, float}
Tuple<0> bad;                   // error: 0 不是类型
```

三种模板形参都可以是包：类型形参包 `class... Ts`、常量形参包 `int... Ns` / `auto... Vs`、模板模板形参包 `template<class> class... TTs`（C++26 起还有变量模板模板形参包与概念模板形参包，[[temp.param]]）。

### 函数形参包（¶2）

¶2 [[g:function-parameter-pack|**函数形参包**]]（function parameter pack）是接受零个或多个函数实参的函数形参：

```cpp run ok
template<class... Types> int f(Types... args) { return sizeof...(args); }

int main() {
    return f()            // args 为空
         + f(1)           // args: int
         + f(2, 1.0)      // args: int, double
         - 3;
}
```

函数形参包的声明 `Types... args` 本身就是一个**包展开**（¶6.1）：模式是 `Types args`，它展开模板形参包 `Types`，同时声明了包 `args`。

### init-capture 包（¶3）

¶3 [[g:init-capture-pack|**init-capture 包**]]是一个 lambda 捕获，它对其初始化器的包展开中的**每个元素**引入一个 init-capture（C++20，[[P0780R2]]）：

```cpp run ok
#include <memory>
#include <utility>
template<class... Args>
auto make_task(Args... args) {
    return [...xs = std::move(args)]() mutable {   // xs 是 init-capture 包：每个元素一个按移动初始化的捕获
        return (0 + ... + *xs);
    };
}
int main() {
    auto t = make_task(std::make_unique<int>(1), std::make_unique<int>(2));   // 只能移动的类型
    return t() - 3;
}
```

注意 `...` 在 init-capture 中写在名字**之前**（`...xs = expr`），与声明形参包时写在名字之前（`Ts... ts` 中 `...` 在 `ts` 之前）一致：`...` 出现在被声明的名字左边，表示"这个名字是一个包"。

### 结构化绑定包（¶4） {{c++26}}

¶4 **结构化绑定包**（structured binding pack）是一个带 `...` 的 *sb-identifier*，引入零个或多个结构化绑定（[[dcl.struct.bind]]，[[P1061R10]]）：

```cpp run ok
#include <utility>
struct Point3 { int x, y, z; };

template<class T>
int sum_fields(const T& t) {
    auto& [...fs] = t;                 // fs 是结构化绑定包：x, y, z
    return (fs + ... + 0);
}
template<class T>
int tail_count(const T& t) {
    auto& [first, ...rest] = t;        // rest 包含 y, z
    (void)first;
    return sizeof...(rest);
}
int main() {
    Point3 p{1, 2, 3};
    return sum_fields(p) - 6 + tail_count(p) - 2;
}
```

一个结构化绑定声明中最多一个包；包的元素个数 = 结构化绑定大小 − 非包名字的个数，可以为零。并且，含结构化绑定包的声明**必须声明模板化实体**（[[dcl.pre#7]]）——也就是说只能出现在模板（或泛型 lambda 等模板化语境）中：

```cpp error
struct P { int a, b; };
int f() {
    auto [...xs] = P{1, 2};    // error: 不在模板化语境中
    return sizeof...(xs);
}
```

为什么有这个限制？因为包的展开机制建立在"模板实例化"之上：包展开是在实例化时才被替换成元素列表的。允许在非模板中使用会要求编译器在普通代码中引入"隐式的模板语境"，提案最终选择了更保守的方案。（在非模板函数中可以把代码包进一个泛型 lambda 来绕过。）

### 包的统称与元素个数（¶5）

¶5 **包**是以上四者的统称。元素个数：

- 模板形参包、函数形参包：为该包提供的实参个数；
- init-capture 包：其初始化器中包展开的元素个数；
- 结构化绑定包：见 [[dcl.struct.bind]]。

---

## 包展开与它的 18 种语境（¶6）

¶6 **包展开**由一个**模式**（pattern）和一个省略号组成，实例化时产生零个或多个模式的实例化组成的列表。模式的形式取决于展开出现的语境。下表列出全部语境：

| ¶ | 语境 | 模式 | 例子 |
|---|---|---|---|
| 6.1 | 函数形参包 [[dcl.fct]] | 去掉省略号的 *parameter-declaration* | `void f(Ts... ts)` |
| 6.2 | *using-declaration* [[namespace.udecl]] | *using-declarator* | `using Bs::operator()...;`（C++17） |
| 6.3 | *friend-type-declaration* [[class.mem]] {{c++26}} | *friend-type-specifier* | `friend Ts...;` |
| 6.4 | 本身是包展开的模板形参包 [[temp.param]] | 去掉省略号的形参声明 | `template<Ts... vs>` |
| 6.5 | *initializer-list* [[dcl.init]] | *initializer-clause* | `g(args...)`、`int a[]{ts...}` |
| 6.6 | *base-specifier-list* [[class.derived]] | *base-specifier* | `struct D : Bs...` |
| 6.7 | 指称**基类**的 *mem-initializer* | *mem-initializer* | `D() : Bs(0)...` |
| 6.8 | *template-argument-list* [[temp.arg]] | *template-argument* | `tuple<Ts*...>` |
| 6.9 | *attribute-list* [[dcl.attr.grammar]] | *attribute* | `[[vendor::attr...]]` |
| 6.10 | *annotation-list* {{c++26}} | *annotation* | `[[=Vs...]]` |
| 6.11 | *alignment-specifier* [[dcl.align]] | 去掉省略号的 *alignment-specifier* | `alignas(Ts...)` |
| 6.12 | *capture-list* [[expr.prim.lambda.capture]] | 去掉省略号的 *capture* | `[args...]`、`[&args...]`、`[...xs = args]` |
| 6.13 | `sizeof...` 表达式 | *identifier* | `sizeof...(Ts)` |
| 6.14 | *pack-index-expression* {{c++26}} | *identifier* | `ts...[0]` |
| 6.15 | *pack-index-specifier* {{c++26}} | *typedef-name* | `Ts...[0]` |
| 6.16 | *pack-index-template-name* {{c++26}} | *simple-template-name* | `TTs...[0]<int>` |
| 6.17 | *fold-expression* [[expr.prim.fold]] | 含未展开包的 *cast-expression* | `(ts + ...)` |
| 6.18 | 折叠展开约束 [[temp.constr.fold]] {{c++26}} | 该约束的约束 | `requires (C<Ts> && ...)` |

`f(&rest...)` 中，`&rest...` 是包展开，`&rest` 是它的模式。

几个要点：

- **哪里不能展开**：表中没有的地方都不行。最常见的误用是**语句**和**表达式中的任意位置**：`ts...;` 或 `g(ts)...;` 不是合法的语句；`x = ts...;` 也不行——在 C++17 之前，人们用 `int dummy[] = {(g(ts), 0)...};` 这个"数组初始化技巧"把展开放进 *initializer-list*（6.5）；C++17 起用逗号折叠 `(g(ts), ...);`（6.17）。
- **成员初始化器只能展开基类**（6.7）：`: a(as)...` 展开到非静态数据成员是非良构的——数据成员是具名的，没有"成员包"。
- **6.9 属性**：语法允许，但每个属性要自己允许 `...`，标准属性没有一个允许，所以实际只用于厂商属性。
- **6.4** 允许"形参的类型来自外层包"：`template<class... Ts> struct X { template<Ts... vs> struct Y; };`——`X<int, char>::Y` 接受一个 `int` 和一个 `char` 常量实参。

```cpp run ok
#include <cstdio>
// 6.2 + 6.6：经典的 overload 惯用法
template<class... Fs> struct overload : Fs... { using Fs::operator()...; };

// 6.6 + 6.7：每个基类一个 mem-initializer
struct B1 { int a; };
struct B2 { int b; };
template<class... Bases> struct D : Bases... {
    D(Bases... bs) : Bases(bs)... { }
};

// 6.11：alignas 展开，取最严格者
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

## 包作为"它会变成的实体"（¶7）

¶7 判断一个包是否满足某条**针对非包实体**的规则时，把这个包看作**模式实例化后得到的实体**。例如 [[dcl.fct]] 中针对"函数形参"的规则同样适用于函数形参包——函数形参包被当作它将展开出的那些函数形参来检查；一条要求"模板形参的类型必须是结构化类型"的规则，同样适用于常量模板形参包 `template<double... Ds>`。这条元规则省去了在全书每一处都写"……或……包"。

## 谁展开谁：未展开包与最内层展开（¶8）

¶8 是变参模板中最重要的结构性规则：

1. 名字出现在某个包展开**模式中**的包，被这个包展开所展开；
2. 一个包名的出现**只被最内层**的外围包展开所展开；
3. 包展开的模式必须指名**一个或多个**未被嵌套包展开所展开的包——它们称为模式中的[[g:unexpanded-pack|**未展开包**]]（unexpanded packs）；
4. 同一包展开所展开的所有包，**元素个数必须相同**（同步展开，lockstep）；
5. 包名出现而**没有被展开**，程序非良构。

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
void g(Args... args) {                      // OK: Args 被函数形参包 args 展开
    f(const_cast<const Args*>(&args)...);   // OK: Args 和 args 同步展开
    f(5 ...);                               // error: 模式中没有包
    f(args);                                // error: args 未展开
    f(h(args...) + args...);                // OK: 第一个 args 在 h 内展开，第二个在 f 内展开
}
```

最后一行值得逐字分析：`h(args...) + args...` 中，第一个 `args` 的最内层外围展开是 `args...`（h 的实参），它在那里被**完全展开**；外层展开 `(h(args...) + args)...` 的模式是 `h(args...) + args`，其中**未展开的**包只有第二个 `args`。所以对 `args = {a, b}`，结果是 `f(h(a, b) + a, h(a, b) + b)`。

### 嵌套展开：笛卡尔积

最内层规则使得"同一个包在内外两层展开"产生**笛卡尔积**式的结果：

```cpp run ok
#include <tuple>
#include <type_traits>
template<class... Ts>
auto square(Ts... ts) {
    return std::tuple{ std::tuple{ts, ts...}... };   // 内层 ts... 完全展开；外层模式 tuple{ts, ts...} 中只有第一个 ts 未展开
}
int main() {
    auto p = square(1, 2);
    // p == tuple{ tuple{1, 1, 2}, tuple{2, 1, 2} }
    static_assert(std::is_same_v<decltype(p),
        std::tuple<std::tuple<int, int, int>, std::tuple<int, int, int>>>);
    return std::get<2>(std::get<0>(p)) - 2;
}
```

### 同步展开：成对处理两个包

同步展开要求元素个数相同，这一点被大量用来"把一个包与一个下标序列配对"：

```cpp run ok
#include <cstddef>
#include <tuple>
#include <type_traits>
#include <utility>
template<class T, std::size_t... Is>
auto reverse_impl(const T& t, std::index_sequence<Is...>) {
    return std::tuple{ std::get<sizeof...(Is) - 1 - Is>(t)... };   // 模式中只有 Is 一个未展开包
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

注意 `sizeof...(Is)` 本身也是一个包展开（6.13），它把 `Is` 完全展开了，所以在外层模式 `std::get<sizeof...(Is) - 1 - Is>(t)` 中只有最后那个 `Is` 是未展开的。

---

## 实例化（¶9–17）

### 基本模型：E₁…E_N（¶9）

¶9 包展开的实例化考虑 E₁, E₂, …, E_N，N 是展开参数（被展开的包）的元素个数。每个 Eᵢ 通过实例化模式、并把每个被展开的包替换为它的第 i 个元素得到。在实例化的语境中，这个"元素"被解释为：

- ¶9.1 模板形参包：类型形参包的元素是一个 *typedef-name*，常量形参包的元素是一个 *id-expression*，模板模板形参包的元素是一个 *template-name*——各自指称第 i 个实参；
- ¶9.2 函数形参包：*id-expression*，指称实例化后的第 i 个函数形参；
- ¶9.3 init-capture 包：*id-expression*，指称第 i 个 init-capture 引入的变量；
- ¶9.4 结构化绑定包：*id-expression*，指称包中第 i 个结构化绑定。

"元素是 *typedef-name*"这一点有实际后果：替换不是文本替换。`const Ts&` 对 `Ts = {int&}` 得到的是 `int&`（引用折叠，cv 加在引用上被忽略），而不是 `const int& &`。

!!! std
    When N is zero, the instantiation of a pack expansion does not alter the syntactic interpretation of the enclosing construct, even in cases where omitting the pack expansion entirely would otherwise be ill-formed or would result in an ambiguity in the grammar.

N 为零时，包展开的实例化**不改变外围结构的语法解释**——即使把展开整个删掉会导致非良构或文法歧义。语法分析在模板定义时就完成了，实例化不会"重新解析"。¶17 的例子展示了这一点：

```cpp run ok
template<class... T> struct X : T... { int v; };
template<class... T> int f(T... values) {
    X<T...> x(values...);      // 语法上是"用 values... 直接初始化变量 x"
    return x.v;
}
template int f<>();            // OK: X<> 没有基类；x 是值初始化的变量（不是函数声明！）
int main() { return f<>(); }   // 返回 0
```

若把 `values...` 直接删去，得到 `X<> x();`——这在普通代码中是**函数声明**（most vexing parse）。但这里 `x` 的身份在模板定义时就已确定为变量，实例化不改变它；`()` 初始化器意味着值初始化，`x.v` 为 0。

### sizeof...（¶10）

¶10 `sizeof...` 表达式的实例化产生值为 N 的整型常量（类型为 `std::size_t`，[[expr.sizeof]]）。`sizeof...` 的操作数必须是**包名**（标识符），不能是任意表达式或类型：

```cpp error
template<class... Ts> int h(Ts... ts) { return sizeof...(ts) + sizeof...(Ts); }   // OK
int x = 3;
int k = sizeof...(x);           // error: x 不是包
```

### 包索引（¶11–13） {{c++26}}

¶11–13 包索引（[[P2662R3]]）：*pack-index-expression* `P...[K]` 的实例化是 *id-expression* E_K；*pack-index-specifier*（类型）的实例化是 *typedef-name* E_K；*pack-index-template-name* 的实例化是 *simple-template-name* E_K。K 是索引——必须是 `std::size_t` 类型的转换常量表达式，`0 ≤ K < N`（[[expr.prim.id]]、[[dcl.type]]、[[temp.names]]）。

```cpp run ok
#include <type_traits>
template<class... Ts> using First = Ts...[0];                   // pack-index-specifier
template<class... Ts> using Last  = Ts...[sizeof...(Ts) - 1];
template<auto... Vs>  constexpr auto second = Vs...[1];          // pack-index-expression（常量形参包）

template<class... Ts>
auto last_arg(Ts... ts) { return ts...[sizeof...(ts) - 1]; }     // 函数形参包

static_assert(std::is_same_v<First<int, char, double>, int>);
static_assert(std::is_same_v<Last<int, char, double>, double>);
static_assert(second<1, 2, 3> == 2);
int main() { return last_arg(1, 2.0, 3) - 3; }
```

```cpp error
template<class... Ts> using At5 = Ts...[5];
At5<int, char> a;               // error: 索引越界
```

包索引同时是包展开（它"展开"整个包然后取一个元素），所以模式中的包被它展开，不需要再写 `...`。

!!! warning "编译器现状"
    截至写作时，本机 Clang 23 支持类型与表达式的包索引，但尚不支持 *pack-index-template-name*（`TTs...[0]<int>` 会报语法错误）。

### 对齐说明符（¶14）

¶14 带省略号的 *alignment-specifier* `alignas(Ts...)` 的实例化产生 `alignas(E₁) alignas(E₂) … alignas(E_N)`——多个 `alignas` 取最严格者（[[dcl.align]]）。N 为零时什么也不产生，等于没有对齐要求。

### 折叠表达式（¶15）

¶15 折叠表达式的实例化（*op* 为折叠运算符，E 为二元折叠中不含未展开包的那一侧）：

| 形式 | 名称 | 展开为 |
|---|---|---|
| `(pack op ...)` | 一元右折叠 | `(E₁ op (… op (E_{N−1} op E_N)))` |
| `(... op pack)` | 一元左折叠 | `(((E₁ op E₂) op …) op E_N)` |
| `(pack op ... op init)` | 二元右折叠 | `(E₁ op (… op (E_N op init)))` |
| `(init op ... op pack)` | 二元左折叠 | `(((init op E₁) op E₂) op … op E_N)` |

记忆法：省略号在哪一边，括号就往哪一边堆——`...` 在左，是左结合。

```cpp run ok
template<class... Args>
bool all(Args... args) { return (... && args); }   // ((E1 && E2) && E3) && E4

template<class... Args>
int minus_left(Args... args)  { return (... - args); }   // ((1 - 2) - 3) = -4
template<class... Args>
int minus_right(Args... args) { return (args - ...); }   // 1 - (2 - 3) = 2

int main() {
    bool b = all(true, true, true, false);
    return (b ? 1 : 0) + (minus_left(1, 2, 3) + 4) + (minus_right(1, 2, 3) - 2);
}
```

**空包**：一元折叠的 N 为零时，只有三个运算符有定义的值（表 20 [tab:temp.fold.empty]）：

| 运算符 | 空包时的值 |
|---|---|
| `&&` | `true` |
| `\|\|` | `false` |
| `,` | `void()` |

其他运算符（包括 `+`、`*`）的一元折叠对空包实例化是**非良构**的。二元折叠永远有定义：空包时结果就是 `init`。

```cpp error
template<class... Ts> auto sum(Ts... ts) { return (ts + ...); }
template<class... Ts> auto sum0(Ts... ts) { return (ts + ... + 0); }
int a = sum0();                 // OK: 二元折叠，空包结果为 0
int b = sum(1, 2);              // OK
int c = sum();                  // error: + 的一元折叠不能为空
```

为什么 `+` 没有默认值 0？因为 `+` 可以被重载，"零元"随类型而变（字符串拼接的零元是空串，矩阵加法的零元是零矩阵）；最初的提案（[[N4295]]）曾为 `+`、`*`、`&`、`|` 也规定空包值，C++17 发布前被 [[P0036R0]] 删去，只剩三个与类型无关的（详见 [[expr.prim.fold]]）。需要零元时写二元折叠，明确给出初值。

### 折叠展开约束（¶16） {{c++26}}

¶16 **折叠展开约束**不被实例化（[[temp.constr.fold]]）：`template<class... Ts> requires (C<Ts> && ...)` 中的折叠在约束规范化时变为折叠展开约束，满足性检查对每个元素逐一进行，并按 `&&`/`||` 短路。它不像普通折叠表达式那样"实例化为一个大表达式"——这使得约束之间的包含（subsumption）比较可以穿过折叠进行（[[temp.constr.order]]）。

### 其他展开（¶17）

¶17 其他包展开的实例化产生列表 E₁, E₂, …, E_N；列表的种类视语境而定（*expression-list*、*base-specifier-list*、*template-argument-list* 等）。N 为零时产生**空列表**：`struct X : T...` 对空包没有基类，`f(args...)` 对空包是无实参调用，`tuple<Ts...>` 是 `tuple<>`。

---

## 推导与偏序中的包

包展开在**推导**中也有特殊规则，散见于其他条款，这里汇总：

- 函数形参包只有位于形参列表**末尾**时才能从调用实参推导；在中间时它是**非推导语境**（[[temp.deduct.type]]），只能通过显式模板实参指定或者推导为空。
- 主类模板的模板形参包必须是最后一个模板形参（[[temp.param]]）；函数模板则不必，只要后面的形参能被推导或有默认值。
- 偏序中，带包的模板通常**不如**不带包的更特化（[[temp.deduct.partial#11]]），见 [[temp.func.order]]。

下例中，看似可以把前两个实参分给 `Ts`、最后一个给 `Last`，但不在末尾的函数形参包不参与推导，`Ts` 被推导为空包，函数只剩一个形参：

```cpp error
template<class... Ts, class Last>
void back(Ts..., Last) { }
int main() {
    back(1, 2, 3);             // error: Ts 推导为空，形参只有一个
    back<int, int>(1, 2, 3);   // OK: 显式指定 Ts = {int, int}，Last 从第三个实参推导
}
```

---

## 实现视角

!!! impl "实现视角"
    - **实例化深度与编译开销**：C++11/14 时代的变参技巧大量依赖**递归实例化**（剥离第一个元素再递归），对 N 个元素产生 O(N) 个类模板特化，每个特化又可能携带 O(N) 长度的实参列表，总代价 O(N²)。折叠表达式、包索引、`std::index_sequence` 配合同步展开都能把很多 O(N) 深度的递归变成单层展开。编译器对递归实例化深度有上限（Clang 和 GCC 默认 1024 量级，可用 `-ftemplate-depth=` 调整）。
    - **包索引的实现**：编译器直接按下标取元素，不需要实例化任何辅助模板；这比 `std::tuple_element_t<I, std::tuple<Ts...>>` 便宜得多。
    - **mangling**：包展开在 Itanium ABI 中有专门的编码（`Dp` 表示 pack expansion，`J...E` 包裹实参包），所以 `f<int, char>` 与"一个接受两个参数的普通模板 `f<int, char>`"的符号不同。

## 历史与演进

!!! history "历史与演进"
    | 标准 | 变化 |
    |---|---|
    | C++11 | 变参模板、模板/函数形参包、包展开、`sizeof...`（[[N2242]] 系列提案） |
    | C++17 | 折叠表达式（[[N4295]]）；*using-declaration* 中的包展开 `using Bs::f...;`（[[P0195R2]]） |
    | C++20 | lambda 中的 init-capture 包 `[...xs = args]`（[[P0780R2]]） |
    | C++26 | 包索引 `Ts...[I]`（[[P2662R3]]）；结构化绑定包（[[P1061R10]]）；变参友元 `friend Ts...;`（[[P2893R3]]）；注解列表中的展开；折叠展开约束；概念/变量模板模板形参包 |

## 陷阱

!!! pitfall "常见误解"
    - "`args...` 可以出现在任何地方"——只能出现在 ¶6 列出的 18 种语境中；语句级的"对每个元素做某事"要用逗号折叠 `(f(args), ...);`。
    - "`(args + ...)` 对空包是 0"——一元 `+` 折叠对空包非良构；只有 `&&`、`||`、`,` 有空包值。
    - "`f(h(args...) + args...)` 会产生 N² 个实参"——不会：内层 `args...` 先完全展开，外层只展开第二个 `args`，结果是 N 个实参，每个都含有完整的 `h(...)` 调用。真正的 N² 要两个包展开**嵌套在模式里**（如 `tuple{tuple{ts, ts...}...}` 产生 N 个长度为 N+1 的元组）。
    - "逗号折叠 `(f(args), ...)` 的求值顺序未指定"——内置逗号运算符从左到右求值，所以顺序是确定的；但若 `f` 返回的类型重载了 `operator,`，折叠会调用那个重载。常见防御：`(void(f(args)), ...)`。
    - "可以在非模板函数里用 `auto [...xs] = s;`"——不行，结构化绑定包只能在模板化语境中使用。

## 思考题

!!! question "思考题 1"
    对 `args = {a, b}`、`Args = {A, B}`，下面每个展开得到什么？

    ```cpp
    f(g(args)...);              // (1)
    f(g(args...));              // (2)
    f(g(args, args...)...);     // (3)
    f(sizeof...(Args) + args...);  // (4)
    ```

<details markdown="1">
<summary>答案</summary>

1. `f(g(a), g(b))`——模式 `g(args)`。
2. `f(g(a, b))`——展开在 `g` 的实参列表中。
3. `f(g(a, a, b), g(b, a, b))`——内层 `args...` 完全展开；外层模式 `g(args, args...)` 中只有第一个 `args` 未展开。
4. `f(2 + a, 2 + b)`——`sizeof...(Args)` 自身是一个完整的展开（6.13），外层模式中的未展开包只有 `args`。
</details>

!!! question "思考题 2"
    下面的代码对 `T = {}` 实例化时，`x` 是变量还是函数？`x.v` 的值是什么？为什么？

    ```cpp
    template<class... T> struct X : T... { int v; };
    template<class... T> int f(T... values) { X<T...> x(values...); return x.v; }
    template int f<>();
    ```

<details markdown="1">
<summary>答案</summary>

是变量，`x.v` 为 0。¶9 末句规定 N 为零时包展开不改变外围结构的语法解释：`X<T...> x(values...)` 在模板定义时被解析为带 `(…)` 初始化器的变量声明，实例化时 `values...` 变为空，初始化器变成 `()`，这是**值初始化**（[[dcl.init]]），而不是把整句重新解析成函数声明 `X<> x();`。值初始化对没有用户提供构造函数的类先零初始化，所以 `v == 0`。
</details>

!!! question "思考题 3"
    为什么 `template<class... Ts> void f(Ts..., int)` 用 `f(1, 2)` 调用会失败，而 `f<int>(1, 2)` 成功？

<details markdown="1">
<summary>答案</summary>

不在形参列表末尾的函数形参包是非推导语境（[[temp.deduct.type]]），推导不会为它分配实参，`Ts` 被推导为空包（一个未被推导、也未被显式指定的尾随模板形参包被推导为空，[[temp.arg.explicit]]）。于是函数类型为 `void(int)`，两个实参对一个形参，不可行。显式指定 `Ts = {int}` 后，函数类型为 `void(int, int)`，可行。
</details>

!!! summary "小结"
    - 四种包：模板形参包、函数形参包、init-capture 包（C++20）、结构化绑定包（C++26，只能在模板化语境）。
    - 包展开 = 模式 + `...`，只能出现在 ¶6 的 18 种语境中。
    - 包名只被**最内层**展开所展开；一个展开中的所有未展开包同步展开，长度必须相同；未展开的包名是错误。
    - 实例化：每个元素替换为 *typedef-name* / *id-expression* / *template-name*（不是文本替换）；N = 0 不改变语法解释。
    - `sizeof...` → N；包索引 → 第 K 个元素；`alignas(Ts...)` → 多个 alignas；折叠 → 按左/右结合的嵌套表达式，空包只对 `&&`（true）、`||`（false）、`,`（void()）有定义。
