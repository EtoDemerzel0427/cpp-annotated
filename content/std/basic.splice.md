---
title: 拼接说明符
summary: C++26 的拼接 [: r :] 把一个反射值变回程序里的构造（变量、类型、模板、命名空间、值……）；本节规定它指称什么，以及 [: r :] 后面的 < 什么时候开始模板实参列表。
status: done
since: c++26
papers: P2996R13
related: basic.pre, expr.prim.splice, dcl.type.splice, expr.reflect, expr.const, temp.names, basic.def.odr, basic.link
tags: 反射, C++26, splice
updated: 2026-10-19
---

!!! tldr
    - `^^x` 把程序里的构造变成 `std::meta::info` 类型的值，`[: r :]` 反过来把这个值变回构造，放到源代码的某个位置上。
    - `[: r :]` 里的 `r` 必须是常量表达式。即使在 `consteval` 函数里，函数形参也不行，要按参数拼接就把反射值作为模板实参传进去。
    - 拼接一个别名，得到的是别名背后的实体：`[:^^I:]` 就是 `int`。
    - `[: r :]` 后面的 `<` 默认是小于号；前面写了 `template` 或 `typename`，或者处在只能出现类型的位置，它才开始模板实参列表。

## 反射和拼接

{{c++26}} 静态反射（[[P2996R13]]）给 C++ 加了两个方向相反的运算：

- **反射**（reflect）：`^^x` 把变量、函数、类型、模板、命名空间等构造变成一个值，类型是 `std::meta::info`（[[expr.reflect]]）。这个值可以在常量求值中传递、存进容器，或交给 `std::meta::members_of` 这样的元函数查询。
- **拼接**（splice）：`[: r :]` 把一个常量 `std::meta::info` 值变回构造，让它出现在源代码的某个位置上，作为表达式、类型、模板名、命名空间名，或 `X::` 前缀。

```cpp
struct S { static constexpr int a = 1; using type = int; };

constexpr auto r = ^^S;               // 反射：r 的类型是 std::meta::info
constexpr int c = [:r:]::a;           // 拼接：[:r:] 就是 S，c == 1
typename [:^^S::type:] *p = nullptr;  // 拼接一个类型：p 是 int*
```

C++23 及以前，没有办法把关于程序的信息再变回程序本身。类型可以作为模板实参来回传递，函数、成员、命名空间都不行，只能靠宏。没有拼接，反射只能用来查看，不能用来生成代码。

!!! warning "编译器支持"
    截至写作时，主流编译器的正式版本（包括本机的 Clang 23）不支持静态反射，也没有 `<meta>` 头文件。反射有实验性实现，例如基于 Clang 的实验分支。下面的例子都按标准草案判定，没有在本机编译，也不提供一键运行按钮。

## 文法

```text
splice-specifier:
    [: constant-expression :]

splice-specialization-specifier:
    splice-specifier < template-argument-list(opt) >
```

`[:` 和 `:]` 是两个新的记号（[[lex.operators]]），这样写是为了和数组下标 `[ ]`、属性 `[[ ]]`、lambda 的 `[ ]` 都区分开。

本节只定义这两个语法单元和它们指称什么。它们在表达式、类型、`X::` 前缀里的具体用法，分别由 [[expr.prim.splice]]、[[dcl.type.splice]]、[[expr.prim.id.qual]]、[[temp.names]] 规定，下文末尾有一张汇总表。

## 拼接指称什么（¶1）

¶1 `[: … :]` 中的表达式必须是类型为 `std::meta::info` 的**转换后的常量表达式**（converted constant expression，[[expr.const.const]]），也就是隐式转换到 `std::meta::info` 之后能在编译期求值的表达式。如果这个值代表构造 `X`，拼接说明符就**指称**（designate）：

- ¶1.1 `X` 是实体（[[basic.pre#8]]）时，`X` 的底层实体；
- ¶1.2 否则就是 `X` 本身。

这一段有三点值得展开。

### 必须是常量表达式

拼接在编译期完成，编译器要据此决定这段源代码到底是变量、类型还是模板，所以反射值必须在翻译时已知。

```cpp
consteval int bad_splice(std::meta::info v) {
    return [:v:];          // error: v 是函数形参，不是常量表达式
}

template<std::meta::info R>
consteval int good_splice() {
    return [:R:];          // OK：R 是模板参数，每个特化各自确定 [:R:] 是什么
}
```

`bad_splice` 是 `consteval` 函数，每次调用都在编译期进行，但它的形参在函数体里仍然不是常量表达式。函数体只分析一次，不可能针对每个实参分别决定 `[:v:]` 是变量还是枚举项。把反射值作为模板实参传进去，每个特化单独实例化一次，问题就解决了。

### 别名拼回去是底层实体

`^^I`（`I` 是 `using I = int;` 定义的别名）代表别名本身。别名是一个独立的实体，反射能区分 `I` 和 `int`，`std::meta::dealias` 才把它还原成 `int`。但拼接回去时，按 ¶1.1，`[:^^I:]` 指称的是底层实体 `int`。这和名字的规则一致：[[basic.pre#8]] 规定名字指代它所声明的实体的底层实体，拼接的效果就像写了一个名字。

### 也可以拼接非实体

反射值除了代表实体，还可以代表值（`std::meta::reflect_constant(42)`）、对象、直接基类关系、非静态数据成员的描述、注解等（[[basic.fundamental]]）。按 ¶1.2，拼接这些构造时，指称的就是构造本身。例如 [[expr.prim.splice]] 规定，拼接一个值得到计算这个值的纯右值；拼接一个直接基类关系 (D, B) 得到一个类型为 B 的左值。

注 1 指出，如果其中的常量表达式是值依赖的（值取决于模板参数），拼接说明符就是依赖的（[[temp.dep.splice]]）。模板里的 `[:R:]` 要等到实例化才知道指称什么，所以和依赖名一样，需要用 `typename`、`template` 消歧义。

## 拼接成模板特化（¶2）

¶2 在 `[: r :]<args>` 中，不依赖模板参数的 `[: r :]` 必须指称一个模板（类模板、函数模板、变量模板、别名模板或概念）。实参列表和它一起构成这个模板的特化，相当于把反射值当作模板名使用。

## `<` 什么时候开始模板实参列表（¶3）

¶3 注 2 说明，`[: r :]` 后面的 `<` 只在下面两种情况下开始模板实参列表：

- 前面有关键字 `template` 或 `typename`；
- 拼接出现在**仅类型上下文**（type-only context）中，即只可能出现类型的位置，例如别名声明 `using A = …;` 的右边（[[temp.res.general]]）。

其他情况下 `<` 是小于号。

这是老问题的新形式。`[:r:]` 指称什么，可能要等到实例化才知道，也可能要先对常量表达式求值，而解析器必须当场决定 `<` 的含义。标准采用了和依赖名一样的办法：默认当作小于号，需要模板实参列表时由程序员写出 `template` 或 `typename`（参见 [[temp.res]] 中 `t.template foo<int>()` 的规则）。在仅类型上下文里只可能是类型，没有歧义，可以省略。

标准例 1：

```cpp
constexpr int v = 1;
template<int V> struct TCls {
    static constexpr int s = V + 1;
};

using alias = [:^^TCls:]<([:^^v:])>;
    // OK：别名声明的右边是仅类型上下文，< 开始模板实参列表；
    //     模板实参 ([:^^v:]) 是加了括号的拼接表达式
static_assert(alias::s == 2);

auto o1 = [:^^TCls:]<([:^^v:])>();            // error: 这里的 < 是小于号
auto o2 = typename [:^^TCls:]<([:^^v:])>();   // OK：o2 是 TCls<1> 类型的对象
```

`o1` 这一行，`[:^^TCls:]` 处在表达式位置，`<` 被当作小于号，而一个类模板不能作为比较的操作数，所以非良构。

作为模板实参的拼接表达式必须加括号：`TCls<[:^^v:]>` 是错的，要写 `TCls<([:^^v:])>`（[[expr.prim.splice#1]]）。在模板实参的位置上，不加括号的 `[:^^v:]` 也可能被理解为类型或模板，加括号就确定它是表达式。

## 拼接在各处的用法

| 写法 | 可以指称 | 规定在 | 例子 |
|---|---|---|---|
| `[: r :]`（拼接表达式） | 变量、函数、枚举项、值、非静态数据成员、结构化绑定…… | [[expr.prim.splice]] | `int n = [:^^x:];` |
| `template [: r :]<...>` | 函数模板及其特化 | [[expr.prim.splice]] | `template [:^^f:]<int>(0)` |
| `typename [: r :]` | 类型、类模板、别名模板 | [[dcl.type.splice]] | `typename [:^^int:] i = 0;` |
| `[: r :]::` | 类、命名空间、枚举 | [[expr.prim.id.qual]] | `[:^^S:]::a` |
| `namespace A = [: r :];` | 命名空间 | [[namespace.alias]] | |
| `using namespace [: r :];` | 命名空间 | [[namespace.udir]] | |
| 模板实参 | 类型、模板、值 | [[temp.arg.general]] | `std::vector<typename [:t:]>` |

```cpp
struct S { static constexpr int a = 1; using type = int; };

constexpr int c = [:^^S:]::a;          // OK：[:^^S:]:: 是 X:: 前缀，不是表达式
void fn() {
    typename [:^^S::type:] *p;         // OK：声明 int* 类型的变量
    [:^^S::type:] *q;                  // error: 既不在仅类型上下文、又没有 typename，
                                       //        [:^^S::type:] 被当作表达式
}
using T = [:^^S::type:];               // OK：仅类型上下文
```

## 与 ODR、链接和访问控制的关系

拼接是不通过名字也能指称实体的方式，所以标准中凡是依赖“用名字指代”的规则，都补上了拼接：

- [[basic.def.odr#3]]：拼接表达式和普通的名字表达式一样，构成表达式的潜在结果；[[basic.def.odr#5]]：拼接表达式指称的变量同样算作被命名，可能被 odr-use。
- [[basic.def.odr#16]]：同一实体在多个翻译单元中的定义里，对应的反射表达式必须算出等价的值（¶16.12）。
- [[basic.link#13]]：声明中的拼接说明符指称某个实体时，这个声明就算命名了它。这影响对翻译单元局部实体的暴露判定：模块接口不能借拼接把内部链接的实体泄漏出去。
- [[class.access.base#5]]：拼接表达式指称的成员总是可访问的。能不能拿到私有成员的反射，由反射查询函数的 `access_context` 参数把关。

!!! impl "实现视角"
    - 解析器看到 `[:` 时，要知道接下来是否需要先做常量求值。不依赖模板参数的拼接在解析时立即求值；依赖的拼接和依赖名一样，推迟到实例化。
    - 拼接不做名字查找：`[:^^x:]` 不会再查找一次 `x`，而是直接用反射值里记录的那个声明或实体，所以能指称被隐藏的声明。
    - `std::meta::info` 是只能在常量求值中存在的类型，运行期不会出现。但它可以作为模板实参出现在特化里，因此需要相应的名字修饰规则，这属于 ABI 规范的工作。

!!! history "历史与演进"
    静态反射的主提案 [[P2996R13]] 于 2025 年并入 C++26 工作草案。早期版本的反射运算符写作 `^`，后来改为 `^^`，因为 `^` 和 Clang 的 blocks 扩展（Objective-C 及 C/C++ 中的闭包语法）冲突。C++23 及以前没有拼接，最接近的做法是把类型作为模板实参传递，或用宏拼接记号。

## 常见误解

!!! pitfall "consteval 函数的形参是常量表达式"
    `consteval void f(std::meta::info r) { [:r:]; }` 是错的。正确做法是把反射值放进模板参数，`template<std::meta::info R> consteval void f() { [:R:]; }`；或者用展开语句 `template for (constexpr auto m : …)`（[[stmt.expand]]），每次展开时循环变量都是常量。

!!! pitfall "`[:r:]<int>` 一定是模板特化"
    在表达式里，`<` 默认是小于号。要写 `template [:r:]<int>` 或 `typename [:r:]<int>`。

## 思考题

!!! question "思考题"
    `using I = int; constexpr auto r = ^^I;` 那么 `r == ^^int` 吗？`typename [:r:]` 是什么类型？

<details markdown="1">
<summary>答案</summary>

`r == ^^int` 为假。`^^I` 代表的是类型别名 `I` 这个实体本身（[[basic.pre#8]] 把类型别名列为一种实体，它的底层实体是 `int`），和 `^^int` 不是同一个反射值；`std::meta::dealias(r) == ^^int` 才为真。

`typename [:r:]` 就是 `int`，因为按 ¶1.1，拼接说明符指称实体的底层实体。
</details>
