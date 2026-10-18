---
title: requires 表达式
summary: 一个 bool 类型的 prvalue，用来检查一组表达式与类型是否有效：简单要求、类型要求、复合要求、嵌套要求；替换失败得到 false 而不是错误，但只限于直接语境。
status: draft
since: c++20
covers: expr.prim.req.general, expr.prim.req.simple, expr.prim.req.type, expr.prim.req.compound, expr.prim.req.nested
related: temp.constr, temp.pre, temp.deduct.general, temp.constr.atomic, temp.concept, expr.context
tags: 概念, 约束, SFINAE, 泛型编程
updated: 2026-10-17
---

**requires 表达式**（*requires-expression*）是 C++20 概念（concepts）用来探测类型性质的工具。给它一组要求，比如 `a + b` 要合法、`T::value_type` 要是一个类型、`*it` 的类型要满足 `std::same_as<...>`，它就在编译期求值为 `true` 或 `false`。

它解决的问题与 C++20 之前的 SFINAE 技巧相同，即检测某个表达式是否合法，但写法直接、可读：

```cpp
// C++17：检测 T 是否有 size() 成员
template<class T, class = void> struct has_size : std::false_type {};
template<class T> struct has_size<T, std::void_t<decltype(std::declval<T&>().size())>> : std::true_type {};

// C++20：
template<class T> concept has_size2 = requires (T& t) { t.size(); };
```

阅读本页需要了解约束与原子约束的满足（[[temp.constr]]、[[temp.constr.atomic]]）、模板实参推导中的直接语境（immediate context，[[temp.deduct.general]]），以及未求值操作数（[[expr.context]]）。

## 文法与基本性质（[expr.prim.req.general]）

### 文法（¶1）

¶1 requires 表达式提供了一种简洁的方式来表达对模板实参的要求，这些要求可以通过名字查找或检查类型与表达式的性质来验证。

```text
requires-expression:
    requires requirement-parameter-list(可选) requirement-body

requirement-parameter-list:  ( parameter-declaration-clause )
requirement-body:            { requirement-seq }
requirement:   simple-requirement | type-requirement | compound-requirement | nested-requirement
```

四种要求：

| 种类 | 形式 | 检查什么 |
|---|---|---|
| 简单要求 | `expr;` | 表达式合法 |
| 类型要求 | `typename T::type;` | 类型合法 |
| 复合要求 | `{ expr } noexcept -> Concept;` | 表达式合法；可选地要求不抛异常、类型满足概念 |
| 嵌套要求 | `requires constraint;` | 约束被满足（对值的判断） |

注意 `requirement-body` 至少要有一个要求：`requires {}` 是非良构的。

### 类型与值（¶2–3）

¶2 [[g:requires-expression|requires 表达式]]是 **`bool` 类型的 prvalue**。因此它可以出现在任何需要 `bool` 常量的地方：概念定义、*requires-clause*、`static_assert`、`if constexpr`、`constexpr bool` 变量的初始化器，等等。

¶3（示例）两种典型用法：

```cpp run ok
#include <concepts>

template<typename T>
concept R = requires (T i) {
  typename T::type;                                        // 类型要求
  { *i } -> std::convertible_to<const typename T::type&>;  // 复合要求
};

struct It { using type = int; int operator*() const; };
static_assert(R<It>);
static_assert(!R<int>);       // int 没有 ::type，也不能 *i —— 结果为 false 而不是错误

template<typename T>
  requires requires (T x) { x + x; }       // 第一个 requires 是 requires-clause，第二个是 requires-expression
T add(T a, T b) { return a + b; }

int main() { return add(1, 2) - 3; }
```

!!! note "`requires requires`"
    第一个 `requires` 引入 *requires-clause*（[[temp.pre]]），它后面要跟一个约束表达式；第二个 `requires` 开始一个 requires 表达式，充当那个约束表达式。这种写法合法，但通常说明应该给这组要求起个名字。把它提取成一个概念，可读性更好，而且只有命名的概念才能参与约束的包含（subsumption）比较（[[temp.constr.order]]）：两个 requires 表达式即使逐字相同，也是两个不同的原子约束。

### 局部形参（¶4）

¶4 requires 表达式可以用形参声明子句引入**局部形参**：

- 不能有默认实参；
- 类型按函数形参的规则确定（[[dcl.fct]]），所以数组退化为指针、函数退化为函数指针、顶层 cv 被丢弃；
- 它们没有链接、没有存储、没有生命周期，只是用于书写要求的记号；
- 形参子句不能以 `...`（C 风格可变参数）结尾。

有了局部形参，就有一个该类型的左值可以直接使用，不必写 `std::declval<T&>()`。注意 `(T t)` 中的 `t` 在要求中是一个 lvalue（它是一个有名字的变量），这对复合要求的类型检查影响很大（见下文）。

```cpp
template<typename T>
concept C = requires(T t, ...) {      // error: 以省略号结尾
  t;
};

template<typename T>
concept C2 = requires(T p[2]) {
  (decltype(p))nullptr;               // OK：p 的类型按函数形参规则调整为 T*
};
static_assert(C2<int>);
```

!!! tip "选择局部形参的类型"
    `requires (T t)` 中的 `t` 是 `T` 类型的 lvalue；如果要检查对 const 对象或右值的操作，应当相应地写 `requires (const T& t)` 或 `requires (T&& t)`（后者在表达式中依然是 lvalue，需要 `std::move(t)` 或 `static_cast<T&&>(t)` 才得到右值）。标准库的概念大多写 `requires (T& t)` 或 `requires (const T& t)`，以避免对不可移动类型的意外影响。

### 替换失败 → false（¶5）

¶5 规定了 requires 表达式的核心语义：

!!! std
    The substitution of template arguments into a *requires-expression* can result in the formation of invalid types or expressions in the immediate context of its *requirements* or the violation of the semantic constraints of those *requirements*. In such cases, the *requires-expression* evaluates to `false`; it does not cause the program to be ill-formed.

    如果在要求的直接语境中产生了无效的类型或表达式，或者违反了要求的语义约束，requires 表达式求值为 false，程序不因此非良构。

逐条来看：

1. 直接语境（immediate context）的范围与 SFINAE 相同（[[temp.deduct.general]]）。替换过程中，直接写在要求里的类型和表达式无效时，结果为 `false`。但如果替换触发了某个类模板的实例化，而那个实例化内部出错（例如类模板体内的 `static_assert` 失败），那就不在直接语境中，是硬错误。
2. 替换按词法顺序进行，遇到能决定结果的条件就停止：一旦某个要求失败，后面的要求就不再替换。这既是性能优化，也是一种可以利用的保护。把开销小、能筛掉不合适类型的要求放在前面，后面可能引发硬错误的要求就不会被触及。
3. 全部成功则为 `true`。

```cpp ok
template<class T> struct Bad { static_assert(sizeof(T) == 0); using type = int; };

template<class T> concept Safe = requires {
  typename T::type;          // 对 int：失败，立即停止
  typename Bad<T>::type;     // 不会被替换，因而不会实例化 Bad<int>
};
static_assert(!Safe<int>);
```

```cpp error
template<class T> struct Bad { static_assert(sizeof(T) == 0); using type = int; };

template<class T> concept HB = requires { typename Bad<T>::type; };
bool hb = HB<int>;   // error: 实例化 Bad<int> 时 static_assert 失败——不在直接语境中，是硬错误
```

### 模板之外的 requires 表达式（¶5 注释 1）

注释 1 指出，如果 requires 表达式的要求中含有无效的类型或表达式，而它不在模板化实体的声明中，程序非良构。

道理很简单：不在模板里就没有替换，那些要求在解析时就会检查，无效就是普通的编译错误。所以在非模板代码里，requires 表达式只能得到 `true`，要么合法，要么报错。它在非模板中的实际用处有限，例如用 `static_assert(requires { ... })` 对具体类型做断言，诊断位置会比单纯的表达式无效更集中。

```cpp
constexpr bool b1 = requires { 1 + 1; };                   // OK：true
constexpr bool b2 = requires { nonexistent(); };           // error: 不在模板中，名字未声明直接报错
constexpr bool b3 = requires (int x) { x.foo(); };         // error: 不在模板中，int 没有成员
```

模板化实体（templated entity，[[temp.pre]]）的范围比模板宽，类模板的非模板成员函数、泛型 lambda 的函数体等都算。所以在泛型 lambda 中写 `if constexpr (requires { t.size(); })` 是没问题的：

```cpp run ok
#include <vector>

template<class T> auto describe(T t) {
  if constexpr (requires { t.size(); }) return t.size();   // 模板中：无效 → false
  else return 0;
}

int main() { return describe(1) + int(describe(std::vector<int>{})); }
```

### 总是失败的要求（IFNDR）

¶5 最后规定：如果无论用什么实参，对一个要求的模板实参替换总是会失败，程序非良构，不要求诊断 {{ifndr}}。

```cpp ifndr
template<typename T> concept C =
  requires {
    new decltype((void)T{});      // 对任何 T，new void 都无效 —— IFNDR
  };
```

为什么是 IFNDR，而不是简单地得到 `false`？这条规则与 [[temp.res]] 中"模板不存在有效特化则 IFNDR"同源：它允许实现在定义时（而不必等到实例化）就诊断明显错误的要求，又不强制实现去证明一个要求总是失败（这在一般情况下不可判定）。Clang 目前对上例不报错；既然不要求诊断，接受也是合规的。

## 简单要求（[expr.prim.req.simple]）

```text
simple-requirement:  expression ;
```

¶1 简单要求断言一个表达式有效。该表达式是未求值操作数（[[expr.context]]），不会被求值，所以没有任何副作用，也不会 odr-use 任何东西。如果模板实参替换失败，所在的 requires 表达式为 `false`。

```cpp ok
template<typename T> concept Addable =
  requires (T a, T b) {
    a + b;            // 只要求 a + b 合法；不关心其类型
  };
static_assert(Addable<int> && !Addable<int*>);
```

¶2 以 `requires` 记号开头的要求永远不会解释为简单要求。为什么需要这条？因为 `requires { ... };` 本身也是一个表达式（嵌套的 requires 表达式），把 `requires C<T>;` 解释为检查某个 requires 表达式是否合法毫无意义，它总是合法的。所以标准规定，以 `requires` 开头的一律是嵌套要求。

!!! pitfall "简单要求只检查合法性，不检查值"
    ```cpp
    template<class T> concept Wrong = requires { sizeof(T) > 4; };      // 只检查 sizeof(T) > 4 是否"合法"——对任何完整类型都合法，于是总为 true
    template<class T> concept Right = requires { requires sizeof(T) > 4; };  // 嵌套要求：检查值
    template<class T> concept Best  = sizeof(T) > 4;                    // 更简单：直接写约束表达式
    ```
    这是初学概念时最常见的错误之一。

## 类型要求（[expr.prim.req.type]）

```text
type-requirement:
    typename nested-name-specifier(可选) type-name ;
    typename splice-specifier ;                          {{c++26}}
    typename splice-specialization-specifier ;           {{c++26}}
```

¶1 类型要求断言一个类型有效。它的组成名字就是 *nested-name-specifier* 和 *type-name* 的组成名字。典型用途有：

- 检查嵌套类型存在：`typename T::value_type;`
- 检查某个类模板特化 *template-id* 合法（满足其模板形参的要求，例如默认模板实参能替换）：`typename S<T>;`
- 检查别名模板替换成功：`typename Ref<T>;`（`Ref<void>` 即 `void&`，失败）
- {{c++26}} 检查 splice 得到类型：`typename [: T::r1 :];`

```cpp ok
template<typename T, typename T::type = 0> struct S;
template<typename T> using Ref = T&;

template<typename T> concept C = requires {
  typename T::inner;   // 需要嵌套成员名 inner
  typename S<T>;       // 需要有效的 template-id：T::type 存在且 0 能转换为它
  typename Ref<T>;     // 需要别名模板替换成功：T 为 void 时失败
};

struct Good { using inner = int; using type = int; };
static_assert(C<Good>);
static_assert(!C<int>);
```

¶2 命名类模板特化的类型要求不要求该类型完整（[[basic.types.general]]）。换言之，`typename S<T>;` 只检查这个名字能否形成，不会隐式实例化 `S<T>` 的定义。上例中 `S` 只有声明没有定义，`C<Good>` 依然为 `true`。这也是类型要求能避免硬错误的原因：不实例化，就不会触发类模板体内的错误。

## 复合要求（[expr.prim.req.compound]）

```text
compound-requirement:     { expression } noexcept(可选) return-type-requirement(可选) ;
return-type-requirement:  -> type-constraint
```

¶1 复合要求断言表达式 `E` 的若干性质。`E` 是未求值操作数。检查按以下顺序进行：

- (1.1) 替换模板实参到 `E` 中；
- (1.2) 如果有 *noexcept-specifier*：(1.2.1) 替换到其常量表达式中；(1.2.2) 如果其值为 `true`，`E` 不得是潜在抛出的表达式（[[except.spec]]）；
- (1.3) 如果有返回类型要求：(1.3.1) 替换到 *type-constraint* 中；(1.3.2) 该类型约束对 `decltype((E))` 的直接声明约束（immediately-declared constraint，[[temp.param]]）必须被满足。

(1.3.2) 是关键。`{ E } -> C<Args...>;` 检查的是 `C<decltype((E)), Args...>`，**注意这里是双括号的 `decltype((E))`**，它保留值类别：lvalue 得到 `T&`，xvalue 得到 `T&&`，prvalue 得到 `T`。

标准用等价改写说明这一点：

```cpp
requires {
  { E1 } -> C;
  { E2 } -> D<A1, A2>;
};
// 等价于
requires {
  E1; requires C<decltype((E1))>;
  E2; requires D<decltype((E2)), A1, A2>;
};
```

!!! note "noexcept 说明在复合要求中的形式"
    C++20 的文法中这里只能写裸的 `noexcept`。当前草案的文法是 *noexcept-specifier*，因此也可以写 `noexcept(常量表达式)`（(1.2.1) 描述了对该常量表达式的替换），`noexcept(false)` 则不施加任何要求，便于在泛型代码中按条件要求不抛出。截至写作时，本机 Clang 尚不接受 `{ e } noexcept(true);` 这种写法（报"期望 `->`"），只接受裸 `noexcept`。

!!! pitfall "`{ t.x } -> std::same_as<int>` 为什么失败"
    ```cpp
    struct P { int x; };
    template<class T> concept HasX  = requires (T t) { { t.x } -> std::same_as<int>; };
    template<class T> concept HasX2 = requires (T t) { { t.x } -> std::same_as<int&>; };
    static_assert(!HasX<P>);   // decltype((t.x)) 是 int&，不是 int
    static_assert(HasX2<P>);
    ```
    `t` 是 lvalue，`t.x` 也是 lvalue，所以 `decltype((t.x))` 是 `int&`。因此检查返回类型时，通常用 `std::convertible_to<int>` 或 `std::same_as<std::remove_cvref_t<...>>` 之类更宽松的写法，而不是 `same_as<int>`。

¶2 的示例总结了三种常见形态：

```cpp ok
#include <concepts>
#include <vector>

template<typename T> concept C1 = requires(T x) {
  {x++};                                           // 等价于简单要求 x++;
};
template<typename T> concept C2 = requires(T x) {
  {*x} -> std::same_as<typename T::inner>;         // *x 合法、T::inner 是类型、same_as<decltype((*x)), T::inner> 满足
};
template<typename T> concept NoThrowSwap = requires(T& a, T& b) {
  { a.swap(b) } noexcept;                          // a.swap(b) 合法且不是潜在抛出的
};

static_assert(C1<int>);
static_assert(NoThrowSwap<std::vector<int>>);
```

注意 C2：如果 `T::inner` 不存在，失败发生在 (1.3.1) 的替换阶段，结果也是 `false`；如果 `*x` 返回 `inner&`（例如迭代器），`same_as<inner&, inner>` 不满足，结果同样是 `false`。

## 嵌套要求（[expr.prim.req.nested]）

```text
nested-requirement:  requires constraint-expression ;
```

¶1 嵌套要求用于借助局部形参表达额外的约束。其约束表达式必须被替换后的模板实参满足（[[temp.constr.decl]]）。对嵌套要求的替换不会导致对约束表达式的替换，除非按 [[temp.constr.constr]] 规定的方式进行。也就是说，约束表达式按约束的规则（范式化、逐个检查原子约束、`&&`/`||` 短路）处理，而不是作为一个普通表达式整体替换。

```cpp ok
template<typename U> concept C = sizeof(U) == 1;

template<typename T> concept D = requires (T t) {
  requires C<decltype (+t)>;     // +t 对 char 会整型提升为 int
};
static_assert(!D<char>);         // decltype(+t) 是 int，sizeof(int) != 1
```

在 requires 表达式内部，嵌套要求是根据值做判断的唯一方式。但要注意，约束必须是常量表达式。局部形参没有值，所以 `requires t > 0;` 不是一个可以求值的约束：替换后的结果不是常量表达式，程序非良构（原子约束的规则，[[temp.constr.atomic]]）。局部形参只能出现在嵌套要求的未求值部分（如 `decltype(t)`、`sizeof(t)`）中。

```cpp error
template<class T> concept V = requires (T t) { requires t > 0; };
bool v = V<int>;     // error: 替换后的约束表达式不是常量表达式
```

```cpp ok
template<class T> concept Big = requires (T t) { requires sizeof(t) > 4; };   // OK：sizeof 不求值
static_assert(Big<double> && !Big<char>);
```

!!! tip "嵌套的 requires 表达式"
    `requires requires { ... };` 在 requires 表达式内部也可以出现：外层 `requires` 是嵌套要求，内层是一个 requires 表达式。最常见的用法是表达否定：
    ```cpp
    template<class T> concept NoFoo = requires (T t) {
      *t;
      requires !requires { t.foo(); };   // t 必须"没有"foo()
    };
    ```
    注意，在约束中对 requires 表达式取 `!`，得到的是一个原子约束（`!` 不是约束的逻辑运算符），它不参与包含判断。

## 实现视角

!!! impl
    - **缓存**：在一个翻译单元中，概念特化（`C<int>`）的满足结果会被缓存。标准规定，同一原子约束对相同模板实参在程序不同位置的满足结果不同时，IFNDR（[[temp.constr.atomic]]），这正是为了允许缓存。因此，借助 requires 表达式检测类型是否已完整这类有状态的技巧是不可移植的。
    - **诊断质量**：概念不满足时，Clang 和 GCC 会指出是哪个要求失败（"because 'a + b' would be invalid" 之类的说明）。requires 表达式的粒度越细，诊断越精确，这是它相对于 SFINAE 的一大实际优势。
    - **总是失败的 IFNDR 情形**：本机 Clang 不诊断标准示例中的 `new decltype((void)T{})`。
    - **非模板中的 requires 表达式**：Clang 对其中的无效表达式直接给出普通的语义错误（例如"使用未声明的标识符"），与注释 1 相符。

## 历史与演进

!!! history
    - **Concepts TS**（ISO/IEC TS 19217:2015）中已有 requires 表达式；当时复合要求的返回类型部分可以直接写一个类型（`{ e } -> Type;`，表示可隐式转换）。
    - **C++20**：随概念一并进入标准；返回类型要求只能是 `-> type-constraint`，`-> Type` 形式被移除，要求可转换时需要显式写成 `-> std::convertible_to<Type>`，含义一目了然。
    - **C++26**（当前草案）：类型要求支持 splice 说明符（静态反射）；复合要求中的 `noexcept` 推广为 *noexcept-specifier*。

## 陷阱

!!! pitfall "以为 requires 表达式可以吞掉所有错误"
    只有直接语境中的无效才变成 `false`。函数体内的错误（`auto` 返回类型的函数需要实例化函数体来推导返回类型）、类模板实例化中的错误、`static_assert` 失败，都是硬错误。一个典型的陷阱是：在 `requires (T t) { f(t); }` 中，如果 `f` 是 `auto` 返回类型的函数模板，检查 `f(t)` 是否合法就需要推导返回类型，于是要实例化其函数体，而函数体中的错误是硬错误。

!!! pitfall "局部形参的值类别"
    `requires (T t)` 中的 `t` 是 lvalue。要检查能否对右值调用，可以写 `std::move(t).f()`，或者改用 `requires (T&& t)` 并配合 `std::forward`。

!!! pitfall "两个相同的 requires 表达式不能互相包含"
    判断两个原子约束是否相同，要看它们是不是源码中同一位置的同一个表达式（[[temp.constr.atomic]]）。在两个模板中各写一份 `requires requires (T t) { t.f(); }`，即使字面相同，也无法比较哪个更受约束，可能导致重载歧义。解决办法是给它起一个概念名。

## 思考题

!!! question "思考题 1"
    下面三个概念对 `std::string` 分别是 `true` 还是 `false`？
    ```cpp
    template<class T> concept A = requires (T t) { { t.size() } -> std::same_as<std::size_t>; };
    template<class T> concept B = requires (T t) { { t[0] } -> std::same_as<char>; };
    template<class T> concept D = requires (const T t) { { t[0] } -> std::same_as<const char&>; };
    ```

<details markdown="1">
<summary>答案</summary>

- `A`：`true`。`t.size()` 是 prvalue，`decltype((t.size()))` 是 `std::size_t`（`std::string::size_type` 就是 `std::size_t`）。
- `B`：`false`。`t[0]` 返回 `char&`，是 lvalue，`decltype((t[0]))` 是 `char&`。
- `D`：`true`。const 对象上 `operator[]` 返回 `const char&`。

（注意 `const T t` 作为局部形参的声明：按函数形参规则，顶层 const 会从形参类型中去掉，但在函数体里，`t` 仍然是 const 的。这里的函数体就是要求体。）
</details>

!!! question "思考题 2"
    为什么 `template<class T> concept C = requires { sizeof(T) == 4; };` 对任何完整类型都是 `true`？怎么改？

<details markdown="1">
<summary>答案</summary>

`sizeof(T) == 4;` 是一个简单要求，只检查这个表达式是否合法（对完整类型总是合法），不检查它的值。可以改为嵌套要求 `requires sizeof(T) == 4;`，或者干脆不用 requires 表达式：`concept C = sizeof(T) == 4;`。对不完整类型，原写法中 `sizeof(T)` 替换失败，`C` 为 `false`；改写后的 `concept C = sizeof(T) == 4;` 也不会产生硬错误，因为原子约束中的替换失败同样只是不满足（[[temp.constr.atomic]]）。
</details>

## 小结

!!! summary
    | 要求 | 写法 | 检查 |
    |---|---|---|
    | 简单 | `e;` | `e` 合法（未求值）；不检查值 |
    | 类型 | `typename T::X;` / `typename S<T>;` | 类型能形成；不要求完整、不实例化 |
    | 复合 | `{ e } noexcept -> C<A>;` | `e` 合法；不潜在抛出；`C<decltype((e)), A>` 满足 |
    | 嵌套 | `requires 约束;` | 约束被满足（常量）；局部形参只能用于未求值部分 |

    - requires 表达式是 `bool` prvalue；替换失败（仅限直接语境）得到 `false`，按词法顺序检查，遇到第一个失败即停止。
    - 不在模板化实体中时，无效要求直接导致非良构。
    - 总是失败的要求：IFNDR。
    - 局部形参是 lvalue，没有存储也没有值；复合要求用 `decltype((e))`，注意引用。
