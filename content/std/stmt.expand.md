---
title: 展开语句（template for）
summary: C++26 的 template for 不是循环，而是把循环体按元素复制成若干份独立的实例化，用来遍历参数包、tuple、聚合体的成员和编译期范围。
status: done
since: c++26
papers: P1306R5
related: stmt.ranged, stmt.label, stmt.cont, stmt.break, dcl.struct.bind, class.temporary, temp.decls.general, temp.pre, temp.res.general
tags: 语句, 模板, 编译期, C++26
updated: 2026-10-19
---

!!! tldr
    - `template for` 在编译期把循环体复制 N 份，每份是一次独立的实例化，所以循环变量在每一份里可以是不同的类型。
    - 初始化器是 `{...}` 列表时逐个表达式展开（枚举式）；是编译期可迭代的范围时按迭代器展开（迭代式）；其余情况按结构化绑定拆开（解构式），数组、`std::tuple`、聚合体都走这条路。
    - 循环体必须是复合语句，不能从外面跳进去，里面也不能有标号；可以用 `break`、`continue`、`return` 往外跳。
    - 循环体被当作模板定义，所以即使所在函数不是模板，体里也能用 `if constexpr` 按元素类型丢弃分支。
    - `break` 只影响执行，不影响实例化：N 份体都会被实例化。

{{c++26}} **展开语句**（[[g:expansion-statement|expansion statement]]）`template for` 由 [[P1306R5]] 引入。它和范围 for 长得很像，但不是迭代语句：它在编译期遍历一组类型可能各不相同的东西，对每个元素生成一份循环体。

<div class="compare" markdown="1">

```cpp ok
#include <cstdio>
#include <tuple>
// C++17：apply + 折叠表达式
void print17(const auto& t) {
  std::apply([](const auto&... xs) {
    ((std::printf("%d\n", (int)xs)), ...);
  }, t);
}
```

```cpp run ok
#include <cstdio>
#include <tuple>
// C++26：展开语句
void print26(const auto& t) {
  template for (const auto& x : t)
  {
    std::printf("%d\n", (int)x);
  }
}
int main() {
  print26(std::tuple{1, 'c', 2.5});
}
```

</div>

右边打印 `1`、`99`、`2`。三份循环体里，`x` 的类型依次是 `const int&`、`const char&`、`const double&`。

## 语法与限制

¶1 展开语句的语法是：

```text
template for ( init-statement(opt) for-range-declaration : expansion-initializer ) compound-statement

expansion-initializer:
    expression
    { expression-list ,(opt) }
    { }
```

循环体必须是复合语句。Clang 23 接受不带花括号的体，但在 `-pedantic` 下警告 ISO C++ 要求复合语句。

花括号形式叫 *expansion-init-list*，它不是普通的花括号初始化列表：`{a, b, c}` 不会推导成 `std::initializer_list`，而是若干个独立的表达式，类型可以各不相同。范围 for 里的 `for (int x : {1, 2, 3})` 则要求所有元素同类型。

¶2 循环体是控制流受限语句（[[g:control-flow-limited-statement|control-flow-limited statement]]，[[stmt.label#3]]）：不能从外面 `goto` 进去，外层 `switch` 的 `case` 标号也不能出现在里面。另外 [[stmt.label#4]] 规定展开语句里不能有标识符标号，因为循环体会被复制 N 份，同一个标号会被定义 N 次。

<div class="compare" markdown="1">

```cpp error
void f() {
  template for (auto x : {1}) {
    (void)x;
  in:;   // error: 不能有标号
  }
}
```

```cpp ok
int f(int k) {
  int r = 0;
  template for (auto x : {1, 2, 3}) {
    if (x == k) goto out;  // OK：往外跳
    r += x;
  }
out:
  return r;
}
```

</div>

## 三种展开方式

¶4 按下面的顺序决定一个展开语句属于哪一种：

| 种类 | 条件 | 典型用途 |
|---|---|---|
| 枚举式（enumerating） | 初始化器是 `{...}` 列表 | 遍历参数包 `{xs...}`、一组异构表达式 |
| 迭代式（iterating） | 否则，初始化器是可展开迭代的表达式 | 遍历编译期已知的范围，例如 `constexpr std::array`、反射得到的成员列表 |
| 解构式（destructuring） | 否则 | 遍历 `std::tuple`、`std::pair`、聚合体、数组 |

¶3 定义了**可展开迭代的**（[[g:expansion-iterable|expansion-iterable]]）表达式 E：E 不是数组类型，并且按 [[stmt.ranged]] 的规则找到的是成员 `E.begin()`、`E.end()`，或者对 `begin(E)`、`end(E)` 的 ADL 各自找到至少一个可行的候选函数。

两个细节值得注意。数组被排除在外，因为数组可以逐个元素解构，不需要在编译期跑迭代器。其次，ADL 这一支要求找到可行的候选，比范围 for 只要找到声明更严格；ADL 找到的 `begin` 不能用 E 调用时，E 不算可展开迭代的，展开语句会转而尝试解构。

一个既有 `begin`/`end` 又能解构的类型，例如 `std::array`，按迭代式处理，所以它的迭代必须能在编译期求值。

## 每种方式的改写

¶5 展开语句等价于一个复合语句，里面是循环变量的声明及其初始化，加上循环体的若干份实例化。

### 枚举式

```text
{
    init-statement
    S0  ...  SN−1
}
其中 Si 是
    {
        for-range-declaration = Ei ;
        compound-statement
    }
```

¶5.1 N 是列表里表达式的个数，Ei 是第 i 个。每一份 Si 单独用 Ei 初始化循环变量，所以 `auto` 在每一份里推导出不同的类型：

```cpp run ok
#include <cstdio>
template<class... Ts>
void print_all(const Ts&... xs) {
    template for (const auto& x : {xs...}) {
        std::printf("%d\n", static_cast<int>(x));
    }
}
int main() { print_all(1, 2L, 'c'); }   // 1、2、99
```

¶6 标准例 1 遍历几个长度不同、因而类型也不同的数组：

```cpp ok
consteval int f(auto const&... Containers) {
    int result = 0;
    template for (auto const& c : {Containers...}) {
        result += c[0];
    }
    return result;
}
constexpr int c1[] = {1, 2, 3};
constexpr int c2[] = {4, 3, 2, 1};
static_assert(f(c1, c2) == 5);
```

列表为空时 N 为 0，循环体一次也不实例化。在某个 Ei 里创建的临时对象，活到用 Ei 初始化的那个循环变量结束，也就是那一份 Si 结束（[[class.temporary#8]]）。

### 迭代式

```text
{
    init-statement
    constexpr(opt) decltype(auto) range = ( expansion-initializer ) ;
    constexpr(opt) auto begin = begin-expr ;
    S0  ...  SN−1
}
其中 Si 是
    {
        constexpr(opt) auto iter = begin + decltype(begin - begin){i} ;
        for-range-declaration = * iter ;
        compound-statement
    }
```

¶5.2 N 由一个 consteval lambda 在编译期从 `begin` 数到 `end` 得出。所以 *begin-expr* 和 *end-expr* 必须能在常量求值中使用，范围本身实际上要是常量。几点要注意：

- `decltype(auto) range = (init)` 带括号，左值初始化器得到引用，不拷贝。
- 第 i 份直接用 `begin + i` 取迭代器，所以迭代器要支持与差值类型相加。
- 只有循环变量声明带 `constexpr` 时，*range*、*begin*、*iter* 的声明上才有 `constexpr`。这时整条迭代链都必须是常量表达式。
- *i* 是 `std::ptrdiff_t` 类型的 prvalue，表示不了时程序非良构。

¶7 标准例 2（这里补上了 `#include`）：

```cpp
#include <array>
consteval int f() {
    constexpr std::array<int, 3> arr {1, 2, 3};
    int result = 0;
    template for (constexpr int s : arr) {   // s 是常量，可作数组边界
        result += sizeof(char[s]);
    }
    return result;
}
static_assert(f() == 6);
```

本机 Clang 23 还不支持迭代式展开语句（报告 iterating expansion statements are not yet supported），这个例子无法在本地验证。

因为 N 要在编译期算出，运行期容器不能用于 `template for`。`std::vector<int> v; template for (auto x : v) { }` 中 `v` 有成员 `begin`/`end`，按迭代式处理，而 `v` 的迭代无法在常量求值中进行，程序非良构。需要运行期循环就用范围 for。

### 解构式

```text
{
    init-statement
    constexpr(opt) auto&& [u0, ..., uN−1] = expansion-initializer ;
    S0  ...  SN−1
}
其中 Si 是
    {
        for-range-declaration = vi ;
        compound-statement
    }
```

¶5.3 N 是初始化器类型的[[g:structured-binding-size|结构化绑定大小]]（[[dcl.struct.bind]]）。任何能写 `auto&& [a, b, c] = x;` 的类型都能解构展开：数组、`std::tuple` 这类 tuple-like 类型，以及非静态数据成员全部公开、且属于同一个类的类。

初始化器是左值时 vi 就是 ui；否则 vi 是 `static_cast<decltype(ui)&&>(ui)`，循环变量可以从元素移动构造。N 为 0 时（例如空结构体）改写成只有 `auto&& range = expansion-initializer;`，初始化器仍会求值。

¶8 标准例 3：

```cpp ok
struct S {
    int i;
    short s;
};
consteval long f(S s) {
    long result = 0;
    template for (auto x : s) {   // x 依次是 int、short
        result += sizeof(x);
    }
    return result;
}
static_assert(f(S{}) == sizeof(int) + sizeof(short));
```

迭代式和解构式初始化器里创建的临时对象，活到 *range* 或结构化绑定那个引用的生命周期结束（[[class.temporary#9]]）。

!!! lawyer "constexpr 循环变量与临时对象"
    `template for (constexpr auto e : std::tuple{1, 'c'})` 非良构。按 ¶5.3，它改写成块作用域里的 `constexpr auto&& [u0, u1] = std::tuple{1, 'c'};`，一个 constexpr 引用绑定到自动存储期的临时对象上，这不是常量表达式。把 tuple 声明为 `static constexpr` 变量再展开就可以了。

## 循环体是模板定义

[[temp.decls.general#3]] 规定，就名字查找和实例化而言，展开语句的循环体视为模板定义；[[temp.pre#8]] 规定在循环变量声明或循环体里定义、创建的实体都是模板化实体。所以体里依赖循环变量的表达式是依赖的，像在模板里一样延迟到每一份实例化时检查。

这意味着即使所在的函数不是模板，也可以在循环体里用 `if constexpr` 按元素类型丢弃分支：

```cpp run ok
#include <string>
#include <tuple>
#include <type_traits>
std::size_t total() {          // 不是模板
    std::tuple<int, std::string, double> t{3, "abcd", 1.5};
    std::size_t n = 0;
    template for (auto& e : t) {
        using E = std::remove_cvref_t<decltype(e)>;
        if constexpr (std::is_same_v<E, std::string>)
            n += e.size();     // 在 int、double 那两份里不实例化
        else
            n += static_cast<std::size_t>(e);
    }
    return n;
}
int main() { return total() == 3 + 4 + 1 ? 0 : 1; }
```

按 [[temp.res.general#6]]，如果循环体不可能产生任何有效的实例化，而它又从未被实例化（例如 N 为 0），程序非良构，不要求诊断；失败的 `static_assert` 不计在内。

## break 和 continue

[[stmt.break]] 和 [[stmt.cont]] 都把展开语句列为可以包围它们的语句。`break` 结束整个展开语句，剩下的 Si 都不执行；`continue` 跳到当前 Si 的复合语句末尾，也就是进入下一份。

```cpp ok
consteval int count() {
    int n = 0;
    template for (auto x : {1, 2, 3, 4}) {
        if (x == 2) continue;   // 跳过这一份
        if (x == 4) break;      // 结束整个展开语句
        ++n;
    }
    return n;
}
static_assert(count() == 2);    // x 为 1 和 3
```

`break` 和 `continue` 只改变执行时的控制流，N 份循环体都已经实例化了。要让某一份不被实例化，得用 `if constexpr`。

[[dcl.attr.fallthrough#1]] 还要求 `[[fallthrough]];` 所在的最内层 `switch` 位于它的最内层展开语句之内，也就是说，展开语句里的 fallthrough 不能把控制交给外面那个 `switch` 的下一个 `case`。

## 与范围 for 的对比

| | 范围 for | `template for` |
|---|---|---|
| 类别 | 迭代语句 | 展开语句 |
| 执行 | 运行期循环 | 编译期复制 N 份体 |
| 元素类型 | 全部相同 | 每份可以不同 |
| `{a, b, c}` | `std::initializer_list` | 若干独立表达式 |
| tuple、聚合体 | 不支持 | 解构式 |
| 容器 | 任意运行期范围 | 只有编译期可迭代的范围 |
| 循环体 | 任意语句 | 复合语句；不能跳入；不能有标号 |
| 代码量 | 一份 | N 份 |

展开语句最主要的用途是配合 C++26 的静态反射：把反射查询得到的成员列表放进编译期数组，再用迭代式展开语句为每个成员生成代码，例如自动序列化。本机 Clang 23 既不支持迭代式展开，也没有实现反射，所以这里不给例子，见 [[expr.reflect]]。

## 思考题

!!! question "1. 下面是哪一种展开语句？循环体实例化几次？"
    ```cpp
    int a[3] = {1, 2, 3};
    template for (int x : a) { }
    ```

<details markdown="1">
<summary>答案</summary>

解构式，3 次。¶3 规定数组不是可展开迭代的，初始化器又不是 `{...}` 列表，所以按 ¶4.3 归为解构式，改写成 `auto&& [u0, u1, u2] = a;`。因为不走迭代，`a` 不必是常量。
</details>

!!! question "2. 在 `template for` 的循环体里写 `return;`、跳到外面的 `goto`、`break`，分别合法吗？"

<details markdown="1">
<summary>答案</summary>

都合法。控制流受限只禁止从外面跳进来，往外跳没有问题，`break` 还被 [[stmt.break]] 明确允许。唯一的限制是循环体里不能有标号（[[stmt.label#4]]），所以 `goto` 只能跳到展开语句外面的标号。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 本质 | 循环体的 N 份独立实例化，不是循环 |
| 分类顺序 | `{...}` → 枚举式；可展开迭代 → 迭代式；其他 → 解构式 |
| 枚举式 | 每份 `decl = Ei;` |
| 迭代式 | `decltype(auto) range = (init)`；N 在编译期数出；第 i 份用 `begin + i` |
| 解构式 | `auto&& [u0, ...] = init;`，右值初始化器时转发 |
| `constexpr` | 只有循环变量带 `constexpr` 时才加到改写中的变量上 |
| 控制流 | 不能跳入；不能有标号；`break` 结束全部，`continue` 进入下一份 |
| 模板性 | 循环体视为模板定义，体内实体是模板化实体 |
