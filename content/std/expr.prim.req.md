---
title: requires 表达式
summary: 一个 bool 类型的 prvalue，在编译期检查一组表达式和类型是否有效：四种要求、局部形参、替换失败为什么得到 false，以及这条规则只在直接语境中成立。
status: done
since: c++20
covers: expr.prim.req.general, expr.prim.req.simple, expr.prim.req.type, expr.prim.req.compound, expr.prim.req.nested
papers: P1452R2
related: temp.constr, temp.constr.atomic, temp.pre, temp.deduct.general, temp.concept, expr.context
tags: 概念, 约束, SFINAE, 泛型编程
updated: 2026-10-19
---

!!! tldr
    - requires 表达式是 `bool` 类型的 prvalue：`requires (T t) { t.size(); }` 在 `t.size()` 有效时为 `true`，否则为 `false`。
    - 要求有四种：简单要求 `e;` 只查表达式是否有效，类型要求 `typename X;` 只查类型能否形成，复合要求 `{ e } noexcept -> C;` 还查不抛异常和类型，嵌套要求 `requires 约束;` 才查值。
    - 替换失败只有发生在直接语境里才得到 `false`；类模板实例化内部、函数体里的错误仍然是硬错误。要求按书写顺序检查，第一个失败就停止。
    - 复合要求的返回类型检查用的是 `decltype((e))`，所以左值表达式得到引用类型，`{ t.x } -> std::same_as<int>` 通常不成立。
    - 局部形参只是记号，没有存储也没有值；它在要求里是左值。

## 用法

C++20 之前，检测一个类型有没有 `size()` 成员要借助 SFINAE 和偏特化；requires 表达式把同样的检查直接写出来：

<div class="compare" markdown="1">

```cpp ok
// C++17
#include <type_traits>
#include <utility>
template<class T, class = void>
struct has_size : std::false_type {};
template<class T>
struct has_size<T, std::void_t<
  decltype(std::declval<T&>().size())>>
  : std::true_type {};
```

```cpp ok
// C++20
template<class T>
concept has_size = requires (T& t) {
  t.size();
};
```

</div>

¶2 **requires 表达式**（[[g:requires-expression|requires-expression]]）是 `bool` 类型的 prvalue，可以用在任何需要 `bool` 常量的地方：概念定义、*requires-clause*、`static_assert`、`if constexpr` 的条件。

¶3 标准例 1 给出两种典型用法。一是定义概念：

```cpp run ok
#include <concepts>

template<typename T>
concept R = requires (T i) {
  typename T::type;                                        // 类型要求
  { *i } -> std::convertible_to<const typename T::type&>;  // 复合要求
};

struct It { using type = int; int operator*() const; };
static_assert(R<It>);
static_assert(!R<int>);   // int 没有 ::type：结果是 false，不是编译错误

int main() {}
```

二是直接写在 *requires-clause* 里（[[temp.pre]]），形成 `requires requires`：

```cpp run ok
template<typename T>
  requires requires (T x) { x + x; }
T add(T a, T b) { return a + b; }

int main() { return add(1, 2) - 3; }
```

第一个 `requires` 引入 *requires-clause*，第二个开始一个 requires 表达式。这样写合法，但通常应该把这组要求提取成一个有名字的概念。原因不只是可读性：两个模板各自写的 requires 表达式即使逐字相同，也是两个不同的原子约束，无法比较哪个更受约束（[[temp.constr.order]]）。

## 文法与局部形参（¶1、¶4）

¶1 requires 表达式由关键字 `requires`、可选的形参列表和花括号里的要求序列组成：

```text
requires-expression:  requires ( parameter-declaration-clause )opt { requirement-seq }
requirement:          simple-requirement | type-requirement
                    | compound-requirement | nested-requirement
```

*requirement-seq* 不可省略，所以 `requires {}` 不合法。

| 种类 | 写法 | 检查什么 |
|---|---|---|
| 简单要求 | `e;` | 表达式有效 |
| 类型要求 | `typename T::type;` | 类型能形成 |
| 复合要求 | `{ e } noexcept -> C;` | 表达式有效，可选地要求不抛异常、类型满足概念 |
| 嵌套要求 | `requires 约束;` | 约束被满足，可以检查值 |

¶4 形参列表引入**局部形参**。它们的类型按函数形参的规则确定（[[dcl.fct]]），所以数组会调整为指针、顶层 cv 被去掉。局部形参没有链接、没有存储、没有生命周期，只是用来书写要求的记号。它们不能有默认实参，形参列表也不能以 `...` 结尾。

```cpp error
template<typename T>
concept C = requires(T t, ...) {   // error: 以省略号结尾
  t;
};

template<typename T>
concept C2 = requires(T p[2]) {
  (decltype(p))nullptr;            // OK：p 的类型是 T*
};
```

有了局部形参，就不用写 `std::declval<T&>()`。要注意 `t` 是一个有名字的变量，在要求里是左值。要检查对 const 对象的操作，写 `requires (const T& t)`；要检查对右值的操作，写 `std::move(t)`。

## 替换失败得到 false（¶5）

¶5 requires 表达式的值这样确定：把模板实参代入各个要求。如果在要求的直接语境里形成了无效的类型或表达式，或者违反了要求的语义约束（比如复合要求的返回类型约束不满足），结果就是 `false`，程序不会因此非良构。全部通过则为 `true`。

**直接语境**（[[g:immediate-context|immediate context]]）的范围和 SFINAE 相同（[[temp.deduct.general]]）：只包括直接写在要求里的类型和表达式。如果代入时需要实例化某个类模板或函数模板，而错误发生在那个实例化的内部，就不是替换失败，而是硬错误。

```cpp error
template<class T> struct Bad { static_assert(sizeof(T) == 0); using type = int; };

template<class T> concept HB = requires { typename Bad<T>::type; };
bool hb = HB<int>;   // error: 实例化 Bad<int> 时 static_assert 失败，不在直接语境中
```

¶5 还规定，代入和检查按词法顺序进行，遇到能决定结果的条件就停止。所以第一个要求失败后，后面的要求根本不会被代入。把能筛掉不合适类型的要求写在前面，就能避免后面的要求触发硬错误：

```cpp ok
template<class T> struct Bad { static_assert(sizeof(T) == 0); using type = int; };

template<class T> concept Safe = requires {
  typename T::type;          // 对 int：失败，到此为止
  typename Bad<T>::type;     // 不会被代入，Bad<int> 不会实例化
};
static_assert(!Safe<int>);
```

### 不在模板里的 requires 表达式

注 1 说，如果 requires 表达式不在**模板化实体**（[[g:templated-entity|templated entity]]，模板以及模板里定义的东西，[[temp.pre]]）的声明中，而它的要求含有无效的类型或表达式，程序非良构。没有模板实参可以代入，这些要求在解析时就被检查，无效就是普通的编译错误。

但这不等于非模板代码里的 requires 表达式只能是 `true`。表达式全都有效、而语义约束不满足时，结果仍然是 `false`：

```cpp ok
#include <concepts>

constexpr bool b1 = requires { 1 + 1; };                            // true
constexpr bool b2 = requires { requires false; };                   // false：嵌套要求不满足
constexpr bool b3 = requires { { 1 } -> std::same_as<long>; };      // false：返回类型约束不满足
static_assert(b1 && !b2 && !b3);
```

```cpp error
constexpr bool b4 = requires { nonexistent(); };      // error: 不在模板中，名字未声明
constexpr bool b5 = requires (int x) { x.foo(); };    // error: int 没有成员
```

泛型 lambda 的函数体、类模板的成员函数也是模板化实体，所以在这些地方写 `if constexpr (requires { t.size(); })` 是常见用法：

```cpp run ok
#include <vector>

template<class T> auto describe(T t) {
  if constexpr (requires { t.size(); }) return t.size();
  else return 0;
}

int main() { return describe(1) + int(describe(std::vector<int>{})); }
```

### 永远失败的要求

¶5 最后一句：如果无论用什么模板实参，对某个要求的代入总是失败，程序**非良构，不要求诊断**（IFNDR）{{ifndr}}，也就是编译器可以不报错，但程序没有任何保证。

```cpp ifndr
template<typename T> concept C =
  requires {
    new decltype((void)T{});   // 对任何 T 都是 new void，永远无效
  };
```

这条规则和 [[temp.res]] 中"模板没有任何有效特化时 IFNDR"是同一个思路：允许编译器在定义处就报告显然写错的要求，又不强迫它去证明一个要求永远失败。本机 Clang 23 对上例不报错，这是合规的。

## 简单要求 [expr.prim.req.simple]

¶1 简单要求 `e;` 断言表达式 `e` 有效。`e` 是**未求值操作数**（[[g:unevaluated-operand|unevaluated operand]]，[[expr.context]]），不会执行，也不会 odr-use 任何东西。

```cpp ok
template<typename T> concept Addable = requires (T a, T b) {
  a + b;   // 只要求 a + b 有效，不关心结果
};
static_assert(Addable<int> && !Addable<int*>);
```

¶2 以 `requires` 记号开头的要求永远不是简单要求，而是嵌套要求。`requires C<T>;` 如果当成简单要求，检查的就是一个 requires 表达式或概念特化本身是否有效，这几乎总是成立，没有意义。

!!! pitfall "简单要求不检查值"
    ```cpp
    template<class T> concept Wrong = requires { sizeof(T) > 4; };           // 只查表达式有效，对完整类型总是 true
    template<class T> concept Right = requires { requires sizeof(T) > 4; };  // 嵌套要求：查值
    template<class T> concept Best  = sizeof(T) > 4;                         // 最直接的写法
    ```

## 类型要求 [expr.prim.req.type]

¶1 类型要求 `typename …;` 断言一个类型有效。常见的用法：

```cpp ok
template<typename T, typename T::type = 0> struct S;
template<typename T> using Ref = T&;

template<typename T> concept C = requires {
  typename T::inner;   // 嵌套类型存在
  typename S<T>;       // template-id 有效：T::type 存在且 0 能转换为它
  typename Ref<T>;     // 别名模板代入成功：T 为 void 时失败
};

struct Good { using inner = int; using type = int; };
static_assert(C<Good>);
static_assert(!C<int>);
```

C++26 起，类型要求也可以是一个拼接 `typename [: r :];`，在 `r` 不是类型的反射时失败（[[expr.prim.splice]]）。{{c++26}}

¶2 命名类模板特化的类型要求不要求这个类型完整。上例中 `S` 只有声明没有定义，`C<Good>` 仍然成立。`typename S<T>;` 只检查这个名字能否形成，不会实例化 `S<T>` 的定义，因此也不会触发类模板体内的错误。

## 复合要求 [expr.prim.req.compound]

```text
compound-requirement:  { expression } noexcept-specifier(opt) return-type-requirement(opt) ;
return-type-requirement:  -> type-constraint
```

¶1 复合要求断言表达式 `E` 的若干性质。`E` 是未求值操作数。检查按下面的顺序进行，任一步失败结果都是 `false`：

1. (1.1) 代入 `E`；
2. (1.2) 有 *noexcept-specifier* 时，代入其中的常量表达式；如果它的值为 `true`，`E` 不能是可能抛出异常的表达式（[[except.spec]]）；
3. (1.3) 有返回类型要求时，代入 *type-constraint*，然后检查它对 `decltype((E))` 的直接声明约束（[[g:immediately-declared-constraint|immediately-declared constraint]]，[[temp.param]]）是否满足。

第 3 步的意思是：`{ E } -> C<A>;` 检查的是 `C<decltype((E)), A>`。标准例 1 用等价改写说明了这一点：

<div class="compare" markdown="1">

```cpp
requires {
  { E1 } -> C;
  { E2 } -> D<A1, A2>;
};
```

```cpp
requires {
  E1; requires C<decltype((E1))>;
  E2; requires D<decltype((E2)), A1, A2>;
};
```

</div>

双括号的 `decltype((E))` 保留值类别：左值得到 `T&`，亡值得到 `T&&`，纯右值得到 `T`。这是复合要求最容易出错的地方：

```cpp ok
#include <concepts>

struct P { int x; };
template<class T> concept HasX  = requires (T t) { { t.x } -> std::same_as<int>; };
template<class T> concept HasX2 = requires (T t) { { t.x } -> std::same_as<int&>; };
static_assert(!HasX<P>);   // t.x 是左值，decltype((t.x)) 是 int&
static_assert(HasX2<P>);
```

所以检查返回类型时，通常写 `std::convertible_to<int>`，而不是 `std::same_as<int>`。

¶2 标准例 2 归纳了三种常见写法：

```cpp ok
#include <concepts>
#include <vector>

template<typename T> concept C1 = requires(T x) {
  {x++};                                     // 等价于简单要求 x++;
};
template<typename T> concept C2 = requires(T x) {
  {*x} -> std::same_as<typename T::inner>;   // *x 有效、T::inner 是类型、same_as<decltype((*x)), T::inner>
};
template<typename T> concept NoThrowSwap = requires(T& a, T& b) {
  { a.swap(b) } noexcept;                    // 有效且不可能抛出
};

static_assert(C1<int>);
static_assert(NoThrowSwap<std::vector<int>>);
```

!!! note "`noexcept(条件)`"
    C++20 的文法在这里只允许裸的 `noexcept`。当前草案改成了 *noexcept-specifier*，因此也可以写 `noexcept(常量表达式)`，`noexcept(false)` 则不施加任何要求，方便在泛型代码里按条件要求不抛出。这是 C++23 之后的新措辞。截至写作时，本机 Clang 23 还不接受 `{ e } noexcept(true);`，报错说期望 `->`。

## 嵌套要求 [expr.prim.req.nested]

¶1 嵌套要求 `requires 约束表达式;` 要求这个约束表达式被代入后的模板实参满足（[[temp.constr.decl]]）。约束表达式按约束的规则处理：先规范化成原子约束的合取与析取，再逐个检查，`&&` 和 `||` 短路（[[temp.constr.constr]]），而不是作为一个普通表达式整体代入。

```cpp ok
template<typename U> concept C = sizeof(U) == 1;

template<typename T> concept D = requires (T t) {
  requires C<decltype(+t)>;   // 对 char，+t 提升为 int
};
static_assert(!D<char>);
```

嵌套要求是在 requires 表达式里检查值的唯一方式，但检查的必须是常量表达式。局部形参没有值，`requires t > 0;` 代入后不是常量表达式，程序非良构（[[temp.constr.atomic]]），而不是得到 `false`。局部形参在嵌套要求里只能出现在 `sizeof`、`decltype` 这类不求值的位置：

<div class="compare" markdown="1">

```cpp error
template<class T>
concept V = requires (T t) {
  requires t > 0;
};
bool v = V<int>;
// error: 不是常量表达式
```

```cpp ok
template<class T>
concept Big = requires (T t) {
  requires sizeof(t) > 4;
};
static_assert(Big<double>);
static_assert(!Big<char>);
```

</div>

嵌套要求里也可以再写一个 requires 表达式，常用来表达否定：

```cpp ok
template<class T> concept NoFoo = requires (T t) {
  *t;
  requires !requires { t.foo(); };   // t 不能有 foo()
};
static_assert(NoFoo<int*>);
```

`!requires {…}` 整体是一个原子约束（`!` 不是约束的逻辑运算符），不参与包含比较。

## 实现视角

!!! impl
    - 编译器会缓存概念特化的满足结果。标准规定，同一原子约束对相同模板实参在不同位置的满足结果不同，程序 IFNDR（[[temp.constr.atomic]]），缓存因此是合规的。用 requires 表达式检测一个类型此刻是否完整这类依赖位置的技巧，不可移植。
    - 概念不满足时，Clang 和 GCC 会指出是哪一个要求失败。要求写得越细，诊断越具体，这是它相比 SFINAE 的实际好处之一。

## 历史与演进

!!! history
    - Concepts TS 的复合要求允许 `{ e } -> Type;`，意思是 `e` 能隐式转换为 `Type`。这和 `-> Concept` 的含义不一致，C++20 合入概念时由 [[P1452R2]] 删去，要求可转换须写成 `-> std::convertible_to<Type>`。
    - C++26 的类型要求可以使用拼接说明符（静态反射）。

## 常见错误

!!! pitfall "以为 requires 表达式能吞掉所有错误"
    只有直接语境里的无效才得到 `false`。一个典型例子：`f` 是返回类型为 `auto` 的函数模板，`requires (T t) { f(t); }` 要知道 `f(t)` 的类型，就得实例化 `f` 的函数体来推导返回类型，函数体里的错误是硬错误。

!!! pitfall "忘了局部形参是左值"
    `requires (T t) { { t } -> std::same_as<T>; }` 对任何非引用类型 `T` 都不成立，因为 `decltype((t))` 是 `T&`。

## 思考题

!!! question "思考题 1"
    下面三个概念对 `std::string` 分别为 `true` 还是 `false`？
    ```cpp
    template<class T> concept A = requires (T t) { { t.size() } -> std::same_as<std::size_t>; };
    template<class T> concept B = requires (T t) { { t[0] } -> std::same_as<char>; };
    template<class T> concept D = requires (const T t) { { t[0] } -> std::same_as<const char&>; };
    ```

<details markdown="1">
<summary>答案</summary>

`A` 为 `true`：`t.size()` 是纯右值，`decltype((t.size()))` 是 `std::size_t`。`B` 为 `false`：`t[0]` 返回 `char&`，是左值，`decltype((t[0]))` 是 `char&`。`D` 为 `true`：`t` 声明为 `const T`，作为形参类型时顶层 const 被去掉，但在要求里 `t` 仍是 const 左值，`operator[]` 选中 const 版本，返回 `const char&`。本机 Clang 23 确认了这三个结果。
</details>

!!! question "思考题 2"
    `template<class T> concept C = requires { sizeof(T) == 4; };` 为什么对所有完整类型都成立？对不完整类型呢？

<details markdown="1">
<summary>答案</summary>

`sizeof(T) == 4;` 是简单要求，只检查表达式是否有效，不看它的值（[expr.prim.req.simple]/1）。对完整类型它总是有效，所以 `C` 为 `true`。对不完整类型，`sizeof(T)` 代入失败，`C` 为 `false`。想检查值，改成嵌套要求 `requires sizeof(T) == 4;`，或者直接写 `concept C = sizeof(T) == 4;`。
</details>
