---
title: 表达式拼接（splice 表达式）
summary: C++26 静态反射中，把一个 std::meta::info 常量写成 [: r :] 放回表达式位置：它可以得到函数、变量、数据成员、基类子对象、枚举项或值，以及它与普通名字的几处关键区别。
status: draft
since: c++26
papers: P2996R13
related: basic.splice, expr.reflect, dcl.type.splice, temp.dep.splice, expr.prim.id, expr.ref, meta.reflection
tags: 反射, C++26, 元编程
updated: 2026-10-19
---

!!! tldr
    - `^^x` 把程序里的一个构造变成 `std::meta::info` 类型的值，`[: r :]` 把这样一个常量值变回它代表的构造；出现在表达式位置的 `[: r :]` 就是 splice 表达式。{{c++26}}
    - `[: r :]` 的结果取决于 `r` 代表什么：函数得到重载集，变量和数据成员得到左值，枚举项和值得到纯右值，类型、命名空间之类不能当表达式。
    - 和普通名字不同，指代非静态成员的 `[: r :]` 不会自动变成 `this->m`，也不做访问检查。
    - 不能在 lambda 内以求值的方式拼接外层函数的局部变量；作为模板实参时必须加括号 `([: r :])`。

!!! warning "编译器支持"
    本机 Clang 23 不支持 `^^` 和 `[: :]` 语法。本页的例子按草案分析，没有经过编译验证，因此都不标判定。可以在 Compiler Explorer 上用 P2996 的实验性 Clang 分支试验。

## 反射与拼接

静态反射（[[P2996R13]]）提供一对相反的操作：

- **反射运算符**（[[g:reflection-operator|reflection operator]]）`^^`（[[expr.reflect]]）：`^^x` 是一个 `std::meta::info` 类型的纯右值，代表变量 `x`；`^^int` 代表类型 `int`；`^^S::m` 代表数据成员 `S::m`。
- **拼接说明符**（[[g:splice-specifier|splice specifier]]）`[: r :]`（[[basic.splice]]）：方括号冒号里必须是一个 `std::meta::info` 类型的常量表达式，它代表的构造称为这个说明符所**指代**的构造。

```cpp
struct S { int m; };

void f(S s) {
  constexpr std::meta::info r = ^^S::m;
  s.[: r :] = 42;          // 等价于 s.m = 42
}
```

`r` 必须是常量，因为 `[: r :]` 是什么（变量还是函数、什么类型）决定了周围的代码怎么解析和检查类型，编译器必须在编译期知道它的值。`consteval` 函数的形参不是常量表达式，所以 `consteval int get(std::meta::info v) { return [: v :]; }` 非良构（[[basic.splice]] 例 1）。需要把反射值当作模板实参传入，或者在展开语句 `template for` 里使用。

拼接可以出现在多种语法位置：类型（`typename [: r :]`，[[dcl.type.splice]]）、嵌套名说明符（`[: r :]::x`）、模板名等。本节只管它作为表达式出现的情形：

```text
splice-expression:
    [: r :]                       // splice-specifier
    template [: r :]              // 指代函数模板
    template [: r :]< 实参 >      // 函数模板或变量模板的特化
```

## 什么时候 `[: :]` 不是表达式（¶1）

¶1 *splice-specifier* 如果后面紧跟 `::`，或者前面有 `typename`，就不会被解释为 splice 表达式。前者是嵌套名说明符，后者是类型。这是纯语法的规则：解析器看到 `[:` 时不知道里面代表什么，只能靠前后的记号决定。

标准例 1（加了注释）：

```cpp
struct S { static constexpr int a = 1; };
template<typename> struct TCls { static constexpr int b = 2; };

constexpr int c = [:^^S:]::a;                   // OK：后跟 ::，是嵌套名说明符
constexpr int d = template [:^^TCls:]<int>::b;  // OK：同上
template<auto V> constexpr int e = [:V:];       // OK：依赖于模板形参的 splice 表达式
constexpr int f = template [:^^e:]<^^S::a>;     // OK：变量模板特化，值为 1

constexpr auto g = typename [:^^int:](42);      // OK：前有 typename，是类型；这是函数式转换

constexpr auto h = ^^g;
constexpr auto i = e<[:^^h:]>;                  // error: 未加括号的 splice 表达式作模板实参
constexpr auto j = e<([:^^h:])>;                // OK
```

最后两行的规则写在 [[temp.arg.general#10]]：模板实参的常量表达式不能是一个未加括号的 splice 表达式。模板实参可以是类型、表达式或模板，光看 `[:^^h:]` 无法判断是哪一种；加上括号后，括号里只能是表达式，歧义就消除了。这条规则只针对整个实参就是 `[: r :]` 的情形，`S<[:r:] + 1>` 不受影响。

## `[: r :]` 的结果（¶2）

¶2 设 S 是 `[: r :]` 所指代的构造。下表按 ¶2 的顺序列出结果：

| S 是 | 表达式的结果 |
|---|---|
| 构造函数、析构函数、无名位域 | 非良构（¶2.1.1–¶2.1.3） |
| 跨 lambda 的局部实体（见下） | 非良构（¶2.1.4） |
| 函数 F | 由 F 的各个声明组成的重载集，再做重载决议（¶2.2） |
| 对象或非静态数据成员 | 指代 S 的左值，类型与 S 相同（¶2.3） |
| 直接基类关系 (D, B) | 类型为 B 的左值（¶2.4） |
| 变量或结构化绑定 | 指代对应对象或函数的左值（¶2.5） |
| 值或枚举项 | 计算 S 的纯右值（¶2.6） |
| 其他（类型、命名空间、模板、概念…） | 非良构（¶2.7） |

下面几行需要解释。

### 不会隐式加上 `this->`（¶2.3）

在成员函数里写一个非静态数据成员的名字 `m`，它会被改写成 `(*this).m`（[[expr.prim.id.general#2]]）。注 1 说，splice 表达式没有这种改写：

!!! std
    The implicit transformation whereby an *id-expression* denoting a non-static member becomes a class member access does not apply to a *splice-expression*.

所以指代非静态数据成员的 `[: r :]` 只能用在 [[expr.prim.id.general#4]] 允许的三种地方：类成员访问的右操作数（`obj.[: r :]`）、取成员指针（`&[: r :]`）、未求值操作数。

```cpp
struct S { int m; };
int S::* k = &[:^^S::m:];            // OK：形成成员指针

void g(S s) {
  s.[:^^S::m:] = 42;                 // OK：类成员访问
  int n = sizeof([:^^S::m:]);        // OK：未求值操作数
}

struct T {
  int m;
  void h() {
    [:^^T::m:] = 1;                  // error: 不会改写为 this->m
    this->[:^^T::m:] = 1;            // OK
  }
};
```

这样设计的效果是，`[: r :]` 的含义只取决于 `r`，不取决于它碰巧出现在哪个类的成员函数里。拼接的典型用途是遍历一个类的数据成员并逐个访问，被访问的对象本来就是显式写出来的。

### 函数只得到它自己的声明（¶2.2）

`^^f` 代表一个确定的函数：[[expr.reflect]] 要求 `&f` 能唯一选出一个函数，否则 `^^f` 非良构。因此拼接得到的重载集里只有这一个函数的各个声明（位于表达式之前，或者在完整类上下文中位于最外层类定义结束之前），不会混入同名的其他重载。各个声明可能给出不同的默认实参，重载决议在这里主要处理这一点。

### 直接基类关系（¶2.4）

`std::meta::bases_of` 之类的元函数返回直接基类关系的反射。拼接这样一个反射得到类型为 B 的左值，而且按 [[expr.prim.id.general#5]]，它只能作为类成员访问的第二个操作数：`d.[: base :]` 就是 `d` 的那个 B 基类子对象。这样访问基类子对象不需要写出基类的名字。

### 变量和结构化绑定（¶2.5）

S 是变量或结构化绑定时，它要么具有静态或线程存储期，要么位于包含这个表达式的某个作用域里。后一条防止把一个函数里局部变量的反射带到另一个函数里拼接，那个变量在别处根本不存在。

结果是一个左值。S 是引用时，结果直接指代被引用的对象或函数，类型按 [[expr.type]] 去掉引用（注 2）。在契约断言的谓词里拼接断言外声明的变量时，类型加上 `const`，和普通名字的规则一致（[[expr.prim.id.unqual#7]]）。

和普通名字一样，`return [: ^^x :];` 也可以隐式移动：[[expr.prim.id.unqual#15]] 定义可移动时把 *splice-expression* 和 *id-expression* 并列。

### 不能跨 lambda 拼接局部实体（¶2.1.4）

¶2.1.4 规定，如果 S 是**局部实体**（[[g:local-entity|local entity]]，函数里的自动变量、形参、结构化绑定等），表达式和 S 的声明之间隔着一个 lambda 作用域，而且忽略外围 `typeid` 后表达式会被潜在求值，那么表达式非良构。

```cpp
void f() {
  int x = 0;
  constexpr auto r = ^^x;
  [: r :] = 1;                        // OK：中间没有 lambda
  [&] { [: r :] = 2; }();             // error: 跨 lambda 拼接局部实体
  [&] { (void)sizeof([: r :]); }();   // OK：未求值
}
```

原因在于 lambda 的捕获。[[expr.prim.lambda.capture#7]] 的隐式捕获由 lambda 体里出现的名字决定，编译器扫描名字就能确定要捕获什么。`[: r :]` 里只有一个常量表达式，要先做常量求值才知道它指向哪个变量。为了不让捕获依赖常量求值，标准直接禁止了这种用法。

反射一侧有对应的限制：[[expr.reflect#7]] 规定，`^^x` 与局部实体 `x` 的声明之间隔着 lambda 作用域时，`^^x` 非良构；init-capture 引入的变量也不能被反射。所以在 lambda 里既不能反射外层的局部变量（捕获了也不行），也不能以求值的方式拼接从外面带进来的局部变量的反射。

## 带 `template` 的两种形式（¶3–¶4）

¶3 `template [: r :]` 要求 `r` 指代一个函数模板（不能是构造函数模板）。结果是由它的各个声明组成的重载集，调用时照常做模板实参推导。

这里必须写 `template`：解析 `[: r :](5)` 时编译器不知道 `r` 是不是模板，`template` 告诉它按模板处理。这与在依赖名字前写 `template`（[[temp.names]]）是同一个道理。

¶4 `template [: r :]<实参>` 要求 `r` 指代一个模板：函数模板得到重载集（显式给出模板实参）；变量模板得到对应特化的左值；其他模板（类模板、别名模板、概念）非良构，它们的特化不是表达式。

```cpp
template<int V> constexpr int e = V;
template<class T> constexpr T twice(T t) { return t + t; }

constexpr int a = template [:^^e:]<3>;            // 变量模板特化，左值
constexpr int b = template [:^^twice:]<int>(4);   // 函数模板，显式模板实参
constexpr int c = template [:^^twice:](5);        // ¶3 的形式，推导出 T = int
```

## 访问检查（注 4）

注 4 指出两点。第一，通过 splice 表达式指代的类成员在任何位置都可以访问（[[class.access.base]]）。访问控制在取得反射值时生效，例如 `std::meta::members_of` 按访问上下文过滤成员（[[meta.reflection.access.context]]），拼接时不再检查。

第二，`obj.[: r :]` 中，左操作数（看作指针）必须能隐式转换为指向右操作数的**指名类**（[[g:designating-class|designating class]]）的指针，否则非良构。不能通过一个无关类型的对象访问成员。

第一点是有意的设计。序列化、调试打印这类库需要看到一个类的全部成员，如果拼接时还做访问检查，它们就无法实现。代价是拿到了私有成员的反射就能访问它，不过这种绕过是显式写出来的，可以在代码审查中找到。

## 与普通名字对比

| | 名字（id 表达式） | splice 表达式 |
|---|---|---|
| 如何确定实体 | 名字查找 | 常量求值得到的反射值 |
| 非静态成员隐式加 `(*this).` | 有 | 无 |
| 访问检查 | 在使用处 | 不检查（在取得反射时检查） |
| 在 lambda 里用外层局部变量 | 触发捕获 | 潜在求值时非良构 |
| 函数 → 重载集 | 所有可见的同名声明 | 只有这个函数（模板）自己的声明 |
| 作模板实参 | 直接写 | 必须加括号 |
| 基类子对象 | 只能经由转换 | `obj.[: base :]` |
| `return` 时隐式移动 | 可以 | 可以 |

## 实现视角

!!! impl
    - P2996 有一个由 Bloomberg 维护的 Clang 分支实现，可以在 Compiler Explorer 上选用；EDG 也有实验性实现。本机 Clang 23 尚不支持。
    - `std::meta::info` 在实现里通常是指向编译器内部语法树节点的不透明句柄，只在常量求值中有意义，不能出现在运行期。
    - `[: V :]` 中的 `V` 依赖模板形参时，拼接推迟到实例化时进行（[[temp.dep.splice]]）。

!!! history
    在 P2996 之前，C++ 没有办法把编译期算出来的东西变回名字或表达式，只能借助宏和模板技巧。反射运算符早期拼作单个 `^`，因为与 Clang 的 blocks 扩展语法冲突，后来改为 `^^`。

## 常见错误

!!! pitfall "模板实参里忘了加括号"
    `foo<[: r :]>` 非良构，应写 `foo<([: r :])>`。`r` 代表类型时写 `foo<typename [: r :]>`。

!!! pitfall "在成员函数里直接拼接数据成员"
    `[: member :]` 不会变成 `this->[: member :]`，要自己写出 `this->[: member :]`。

## 思考题

!!! question "思考题 1"
    下面三行是否良构？
    ```cpp
    struct B { int x; };
    struct D : B { void f(); };
    void D::f() {
      constexpr auto r = ^^B::x;
      int a = x;              // #1
      int b = [: r :];        // #2
      int c = this->[: r :];  // #3
    }
    ```

<details markdown="1">
<summary>答案</summary>

`#1` 良构：名字 `x` 隐式改写为 `(*this).x`（[[expr.prim.id.general#2]]）。`#2` 非良构：splice 表达式不做这种改写（¶2.3 注 1），于是在潜在求值的位置单独使用了非静态数据成员，违反 [[expr.prim.id.general#4]]。`#3` 良构：这是类成员访问，`this` 能隐式转换为 `B*`，而 `B` 是右操作数的指名类。
</details>

!!! question "思考题 2"
    在 lambda 里以求值方式拼接外层的局部变量是非良构的。如果先在捕获列表里写上 `[x]`，再在 lambda 体里写 `^^x` 并拼接，能绕过这个限制吗？

<details markdown="1">
<summary>答案</summary>

不能。lambda 体里的名字 `x` 仍然指代外层函数里的那个局部实体（捕获只是改变了 odr-use 时访问的对象），它与 `^^x` 之间隔着 lambda 作用域，按 [[expr.reflect#7]] 的 7.1.4，`^^x` 本身就非良构。改用 init-capture `[y = x]` 也不行：7.1.1 禁止反射 init-capture 引入的变量。在 lambda 里需要这个变量时，直接用它的名字就行；如果一定要通过反射，就在 lambda 之外完成拼接。
</details>
