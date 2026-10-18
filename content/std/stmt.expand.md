---
title: 展开语句（template for）
summary: C++26 的展开语句：对表达式列表、编译期可迭代的范围、可解构的对象，把循环体复制 N 次，每份都是独立的实例化；三种形式的精确改写、break/continue 的语义与各种限制。
status: draft
since: c++26
papers: P1306R5
related: stmt.ranged, stmt.label, stmt.cont, stmt.break, dcl.struct.bind, class.temporary, temp.decls.general, temp.pre, temp.res.general
tags: 语句, 模板, 编译期, C++26
updated: 2026-10-17
---

{{c++26}} **展开语句**（[[g:expansion-statement|expansion statement]]）`template for` 看起来像范围 for，本质上却完全不同。它不是循环，而是在编译期把循环体**按元素复制 N 份**，每一份都是一次独立的实例化，循环变量在每一份里可以有不同的类型。

它要解决的是在编译期遍历异构对象的问题，对象可以是参数包、`std::tuple`、聚合体的成员，或者（配合静态反射）类型的成员列表。在 C++26 之前，这类代码只能借助 `std::index_sequence` + 折叠表达式 + 泛型 lambda，或者递归模板：

```cpp
// C++17/20 的写法
template<class Tuple>
void print(const Tuple& t) {
    std::apply([](const auto&... xs) { ((std::cout << xs << '\n'), ...); }, t);
}
// C++26
template<class Tuple>
void print(const Tuple& t) {
    template for (const auto& x : t) { std::cout << x << '\n'; }
}
```

本节由 [[P1306R5]] 引入。它和 [[stmt.ranged]] 共用 *for-range-declaration* 的语法以及 *begin-expr*/*end-expr* 的定义，但它不是迭代语句（[[stmt.iter]]），而是第 8 章中单独的一类语句。

## 语法（¶1）

¶1 展开语句"指定其子语句的重复实例化"（[[temp.decls.general]]）。

```text
template for ( init-statement(opt) for-range-declaration : expansion-initializer ) compound-statement

expansion-initializer:
    expression
    expansion-init-list
expansion-init-list:
    { expression-list ,(opt) }
    { }
```

有两个要点：

1. 循环体必须是复合语句。（Clang 作为扩展接受非复合语句的体，但在 `-pedantic` 下会警告"ISO C++ 要求展开语句的体是复合语句"。）
2. *expansion-init-list* 不是 *braced-init-list*。`{a, b, c}` 在这里不会推导为 `std::initializer_list`，而是由若干独立表达式组成的列表，所以元素的类型可以各不相同。这是它与范围 for 中 `for (int x : {1, 2, 3})` 的根本区别。

## 体是控制流受限语句（¶2）

¶2 展开语句的 *compound-statement* 是**控制流受限语句**（[[stmt.label#3]]）：不能从外面 `goto` 进去，外层 `switch` 的 `case` 标号也不能出现在里面。此外，[[stmt.label#4]] 规定体内（以及整个展开语句内）不能有标识符标号，因为体会被复制 N 份，同一个标号会被定义 N 次。

```cpp error
void f() {
    goto in;                                  // error（且标号本身也非法）
    template for (auto x : {1}) {
        (void)x;
    in:;                                      // error: 标识符标号被展开语句包围
    }
}
```

从体内往外跳是允许的，`goto` 外面的标号、`return`、`break` 都可以。

```cpp ok
int f(int k) {
    int r = 0;
    template for (auto x : {1, 2, 3}) {
        if (x == k) goto out;                 // OK: 跳到展开语句之外
        r += x;
    }
out:
    return r;
}
```

## 可展开迭代的表达式（¶3）

¶3 对表达式 E，按 [[stmt.ranged]] 的规则确定 *begin-expr* 和 *end-expr*。E 是**可展开迭代的**（expansion-iterable），当且仅当它不是数组类型，并且：

- ¶3.1 *begin-expr*/*end-expr* 是成员形式 `E.begin()`/`E.end()`；或
- ¶3.2 对 `begin(E)` 和 `end(E)` 的 ADL 各自找到至少一个可行（viable）候选函数。

有两个细节需要注意：

- 数组被排除在外。数组走解构路线（见下文），每个元素一份实例化，不需要在编译期求值迭代器。
- ¶3.2 的判据是找到可行候选，比 [[stmt.ranged]] 的找到声明更宽松。如果 ADL 找到的 `begin` 根本不能用 E 调用，E 就不是可展开迭代的，展开语句会转而尝试解构，而不是直接报错。

## 三种展开语句（¶4）

¶4 按以下优先顺序分类：

| 种类 | 条件 | 典型用途 |
|---|---|---|
| 枚举式（enumerating）¶4.1 | 初始化器是 *expansion-init-list* `{...}` | 遍历参数包 `{xs...}`、一组异构表达式 |
| 迭代式（iterating）¶4.2 | 否则，初始化器是可展开迭代的表达式 | 遍历编译期已知的范围（`constexpr std::array`、反射得到的成员序列） |
| 解构式（destructuring）¶4.3 | 否则 | 遍历 `std::tuple`/`std::pair`/聚合体/数组（任何可以做结构化绑定的对象） |

由此可知，既可迭代又可解构的类型（例如 `std::array`）会按**迭代式**处理，这要求它的迭代在编译期可求值。

## 语义：等价的改写（¶5）

¶5 展开语句 S 等价于一个复合语句，其中包含 *for-range-declaration*（连同其隐含的初始化）和 S 的 *compound-statement* 的若干份实例化。

### 枚举式（¶5.1）

```text
{
    init-statement
    S0
    ...
    SN−1
}
其中 Si 是
    {
        for-range-declaration = Ei ;
        compound-statement
    }
```

N 是 *expression-list* 的元素个数，Ei 是第 i 个元素。每个 Si 独立地用 Ei 初始化循环变量，所以 `auto` 在每一份里推导出不同的类型。

```cpp run ok
#include <cstdio>
template<class... Ts>
void print_all(const Ts&... xs) {
    template for (const auto& x : {xs...}) {     // 枚举式：x 在每一份中类型不同
        std::printf("%d\n", static_cast<int>(x));
    }
}
int main() { print_all(1, 2L, 'c'); }            // 打印 1、2、99
```

标准例 1（改编）遍历一组数组，每个数组长度不同，因而类型也不同：

```cpp ok
consteval int f(auto const&... Containers) {
    int result = 0;
    template for (auto const& c : {Containers...}) {   // 枚举式
        result += c[0];
    }
    return result;
}
constexpr int c1[] = {1, 2, 3};
constexpr int c2[] = {4, 3, 2, 1};
static_assert(f(c1, c2) == 5);
```

空列表 `{}` 时 N = 0，体一次也不实例化。

关于临时对象，[[class.temporary#8]] 规定：在枚举式展开语句的某个元素 E 中创建的临时对象，如果本应在 E 的完整表达式结束时销毁，就延长到用 E 初始化的 *for-range-declaration* 的生命周期结束，也就是那一份 Si 结束。

### 迭代式（¶5.2）

```text
{
    init-statement
    constexpr(opt) decltype(auto) range = ( expansion-initializer ) ;
    constexpr(opt) auto begin = begin-expr ;
    S0
    ...
    SN−1
}
其中 Si 是
    {
        constexpr(opt) auto iter = begin + decltype(begin - begin){i} ;
        for-range-declaration = * iter ;
        compound-statement
    }
```

N 是下面这个 consteval lambda 的求值结果，也就是在编译期从头到尾数一遍：

```text
[&] consteval {
    std::ptrdiff_t result = 0;
    auto b = begin-expr;
    auto e = end-expr;
    for (; b != e; ++b) ++result;
    return result;
}()
```

逐条解读如下：

- `decltype(auto) range = (init)` 加了括号，所以左值初始化器得到的是引用（`decltype((x))` 是 `T&`），不拷贝；prvalue 则得到对象本身。
- 当且仅当 *for-range-declaration* 带 `constexpr` 时，*range*、*begin*、*iter* 的声明上才出现 `constexpr`。写 `template for (constexpr auto x : r)` 时，整条迭代链都必须是常量表达式。
- 第 i 份用 `begin + i` 得到迭代器，所以迭代器需要支持与差值类型相加（随机访问风格的 `+`）。第 i 份独立地从 *begin* 出发，而不是从上一份的迭代器递增而来。
- 因为 N 要在编译期算出来，*begin-expr*/*end-expr* 必须能在常量求值中使用。实际上范围本身需要是常量，如 `static constexpr` 的数组容器，或反射生成的静态数组。
- *i* 视为 `std::ptrdiff_t` 的 prvalue；如果无法表示，程序非良构。
- 关于临时对象，[[class.temporary#9]] 规定初始化器中的临时对象活到 *range* 引用的生命周期结束。

标准例 2：

```cpp
#include <array>
consteval int f() {
    constexpr std::array<int, 3> arr {1, 2, 3};
    int result = 0;
    template for (constexpr int s : arr) {      // 迭代式：s 是常量，可以用作数组边界
        result += sizeof(char[s]);
    }
    return result;
}
static_assert(f() == 6);
```

!!! impl "编译器支持"
    截至写作时，本机 Clang 23 已经支持枚举式和解构式展开语句，但对迭代式报告"iterating expansion statements are not yet supported"，因此上面的例 2 未能在本地验证。对这个例子，Clang 还额外报告 `constexpr` 的 `__range1` 不是常量表达式，因为它引用了一个非 `static` 的局部 `constexpr` 变量 `arr`，而后者的地址在每次调用中可能不同；把 `arr` 改为 `static constexpr` 可以消除这一条。GCC 的支持情况请以其发布说明为准。

### 解构式（¶5.3）

N 为 0 时：

```text
{
    init-statement
    constexpr(opt) auto&& range = expansion-initializer ;
}
```

否则：

```text
{
    init-statement
    constexpr(opt) auto&& [u0, u1, ..., uN−1] = expansion-initializer ;
    S0
    ...
    SN−1
}
其中 Si 是
    {
        for-range-declaration = vi ;
        compound-statement
    }
```

- N 是初始化器类型的**结构化绑定大小**（structured binding size，[[dcl.struct.bind#2]]）。也就是说，任何可以写 `auto&& [a, b, c] = x;` 的类型都可以解构展开，包括数组、tuple-like 类型（`std::tuple`、`std::pair`、`std::array` 等，但 `std::array` 会先按迭代式处理），以及所有非静态数据成员都是公开直接成员的类。
- 初始化器是左值时，vi 就是 ui；否则 vi 是 `static_cast<decltype(ui)&&>(ui)`，相当于对右值初始化器做完美转发，让循环变量可以从元素移动构造。
- 同样，当且仅当 *for-range-declaration* 带 `constexpr` 时，结构化绑定声明上才出现 `constexpr`。
- N = 0 时（例如空结构体）仍然会绑定 *range*，因此初始化器仍会求值。

标准例 3：

```cpp ok
struct S {
    int i;
    short s;
};
consteval long f(S s) {
    long result = 0;
    template for (auto x : s) {           // 解构式：x 依次为 int、short
        result += sizeof(x);
    }
    return result;
}
static_assert(f(S{}) == sizeof(int) + sizeof(short));
```

遍历 `std::tuple` 时，每一份里 `e` 的类型不同。由于体是一个模板定义（[[temp.decls.general#3]]），即使所在的函数不是模板，也可以用 `if constexpr` 按元素类型丢弃分支：

```cpp run ok
#include <string>
#include <tuple>
#include <type_traits>
std::size_t total() {                      // 不是模板
    std::tuple<int, std::string, double> t{3, "abcd", 1.5};
    std::size_t n = 0;
    template for (auto& e : t) {
        if constexpr (std::is_same_v<std::remove_cvref_t<decltype(e)>, std::string>)
            n += e.size();                 // e 为 int/double 的那几份里不实例化
        else
            n += static_cast<std::size_t>(e);
    }
    return n;
}
int main() { return total() == 3 + 4 + 1 ? 0 : 1; }
```

!!! lawyer "constexpr 解构一个临时对象"
    `template for (constexpr auto e : std::tuple{1, 'c'})` 是非良构的。按 ¶5.3，它改写为块作用域中的 `constexpr auto&& [u0, u1] = std::tuple{1, 'c'};`，这是一个绑定到（自动存储期）临时对象的 constexpr 引用，而常量表达式不允许引用自动存储期的对象。Clang 会报告"reference to temporary is not a constant expression"。把 tuple 声明为 `static constexpr` 变量再展开即可。

## 展开语句的模板性

第 13 章中有几条分散的规则决定了体的行为：

- [[temp.decls.general#3]]：就名字查找和实例化而言，展开语句的 *compound-statement* 视为模板定义；
- [[temp.pre#8]]：在 *for-range-declaration* 或体中定义/创建的实体是模板化实体（templated entity）；
- [[temp.res.general#6]]：如果体不可能产生任何有效特化，且从未实例化（例如 N = 0），程序 IFNDR（失败的 `static_assert` 不计在内）。

因此，体中依赖于循环变量的表达式是依赖的，像在模板里一样延迟检查。每一份实例化都是独立的，所以体中的 `static_assert`、`if constexpr`、`decltype` 可以对每个元素给出不同的结果。

## break 与 continue

[[stmt.break]] 和 [[stmt.cont]] 都把展开语句列为合法的包围语句：

- `break` 终止整个展开语句，控制转到展开语句之后（剩余的 Si 都不执行）；
- `continue` 把控制转到当前 Si 的复合语句末尾，也就是进入下一份 S(i+1)。

```cpp ok
consteval int count() {
    int n = 0;
    template for (auto x : {1, 2, 3, 4}) {
        if (x == 2) continue;      // 跳过本份
        if (x == 4) break;         // 结束整个展开语句
        ++n;
    }
    return n;
}
static_assert(count() == 2);       // x = 1 和 x = 3
```

注意，这里的 `break`/`continue` 是运行期控制流（在 consteval 函数里则是常量求值期间的控制流）。即使执行了 `break`，所有 N 份体也都已经实例化了。`break` 不能用来阻止某一份的实例化，那要用 `if constexpr`。

关于 fallthrough，[[dcl.attr.fallthrough#1]] 要求 fallthrough 语句的最内层 `switch` 位于其最内层展开语句之内。换言之，展开语句内的 `[[fallthrough]];` 不能把控制交给展开语句外的 `switch` 的下一个 `case`。

## 与范围 for 的对比

| | 范围 for | `template for` |
|---|---|---|
| 类别 | 迭代语句 | 展开语句 |
| 执行 | 运行期循环 | 编译期复制 N 份体 |
| 元素类型 | 全部相同 | 每份可以不同 |
| `{a, b, c}` | `std::initializer_list`（同类型） | *expansion-init-list*（异构） |
| tuple / 聚合体 | 不支持 | 解构式 |
| 容器 | 任意运行期范围 | 只有编译期可迭代的范围 |
| 体 | 任意语句 | 必须是复合语句；控制流受限；不得有标识符标号 |
| 代码体积 | 一份 | N 份 |

## 与静态反射配合

展开语句最主要的使用场景是 C++26 的静态反射。反射查询返回的成员列表是 `std::meta::info` 的序列，把它转为编译期静态数组后用迭代式展开语句遍历，就可以为每个成员生成代码（例如自动序列化、打印结构体）。由于本机 Clang 尚不支持迭代式展开，也未实现反射，这里不给出可运行的例子，详见 [[expr.reflect]] 及相关章节。

## 陷阱

!!! pitfall "`template for` 不会让运行期容器变成编译期的"
    `std::vector<int> v; template for (auto x : v)` 是非良构的。N 必须在编译期算出，而 `v.begin()`/`v.end()` 无法在常量求值中对一个运行期对象求值。需要运行期循环就用范围 for。

!!! pitfall "N 份体意味着 N 份代码"
    每一份都是独立实例化的代码。对很长的列表展开较大的循环体，会显著增加编译时间和代码体积。

!!! pitfall "解构式要求所有成员可访问"
    与结构化绑定一样，解构一个类要求其所有非静态数据成员都是公开的，并且属于同一个类（[[dcl.struct.bind]]）。有私有成员的类不能直接解构展开，除非它提供 tuple-like 协议。

## 思考题

!!! question "1. 下面的展开语句是哪一种？体被实例化几次？"
    ```cpp
    int a[3] = {1, 2, 3};
    template for (int x : a) { }
    ```

<details markdown="1">
<summary>答案</summary>

解构式，3 次。¶3 明确规定数组类型不是可展开迭代的，初始化器也不是 *expansion-init-list*，所以按 ¶4.3 归为解构式，改写为 `auto&& [u0, u1, u2] = a;`，每一份用一个元素初始化 `x`。因为不走迭代路线，`a` 不必是常量。
</details>

!!! question "2. 在 `template for` 的体里写 `return;`、`goto`（到外面）、`break`、`co_return` 分别合法吗？"

<details markdown="1">
<summary>答案</summary>

都合法（`co_return` 要求所在函数是协程）。控制流受限只禁止从外面跳进来，从体内跳出去没有问题。[[stmt.break]] 明确允许 `break`，它终止整个展开语句。唯一禁止的是体内的标识符标号（[[stmt.label#4]]），所以体内的 `goto` 只能跳到展开语句外的标号。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 本质 | 体的 N 份独立实例化，不是循环 |
| 分类优先级 | `{...}` → 枚举式；可展开迭代（非数组且 begin/end 可用）→ 迭代式；其他 → 解构式 |
| 枚举式 | 每份 `decl = Ei;`，元素类型可不同 |
| 迭代式 | `decltype(auto) range = (init)`；N 由 consteval lambda 计数；第 i 份用 `begin + i` |
| 解构式 | `auto&& [u0...] = init;`；右值初始化器时转发绑定 |
| `constexpr` | 当且仅当循环变量带 `constexpr` 时传播到说明用变量 |
| 控制流 | 体是控制流受限语句；不得有标识符标号；`break` 结束全部，`continue` 进入下一份 |
| 模板性 | 体被视为模板定义，体内实体是模板化实体 |
