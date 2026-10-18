---
title: 表达式拼接（splice 表达式）
summary: C++26 静态反射中把一个 std::meta::info 值"拼回"代码的表达式形式 [: r :]：它可以指代变量、函数、数据成员、基类子对象、枚举项或值，并规定了结果的类型与值类别。
status: draft
since: c++26
papers: P2996R13
related: basic.splice, expr.reflect, dcl.type.splice, temp.dep.splice, expr.prim.id, expr.ref, meta.reflection
tags: 反射, C++26, 元编程
updated: 2026-10-17
---

{{c++26}} 静态反射（[[P2996R13]]）引入了两个相互对应的操作：

- **反射**：`^^x`（[[expr.reflect]]）把一个程序构造（变量、类型、函数、命名空间、成员……）变成一个 `std::meta::info` 类型的**值**；
- **拼接**（splice）：`[: r :]`（[[basic.splice]]）把一个 `std::meta::info` 常量值**变回**它所代表的程序构造。

拼接可以出现在多种语法位置上：作为**类型**（`typename [: r :]`，[[dcl.type.splice]]）、作为**嵌套名说明符**（`[: r :]::member`，[[expr.prim.id.qual]]）、作为**命名空间名**、作为**模板名**……本节规定的是它作为**表达式**出现的情形——*splice-expression*。

!!! warning "编译器支持"
    截至写作时，主流发行版编译器对静态反射的支持仍在实验阶段（本机 Clang 23 不支持 `^^`/`[: :]` 语法；有实验性分支实现）。本页的例子按标准草案给出判定，**未经本机编译器验证**。

阅读前请先了解：*splice-specifier* 的定义与"指代"（designate）的含义（[[basic.splice]]）、反射运算符 `^^`（[[expr.reflect]]）、id 表达式的类型与值类别（[[expr.prim.id]]）——splice 表达式的规则有意与 id 表达式平行，区别之处才是重点。

## 文法

```text
splice-expression:
    splice-specifier                              // [: r :]
    template splice-specifier                     // template [: r :]
    template splice-specialization-specifier      // template [: r :]<args>

splice-specifier:                 [: constant-expression :]
splice-specialization-specifier:  splice-specifier < template-argument-list(可选) >
```

[[basic.splice#1]] 规定 `[: ... :]` 里必须是 `std::meta::info` 类型的**转换常量表达式**。若它代表的构造 X 是一个实体，*splice-specifier* **指代**（designate）X 的底层实体（例如别名的话就是被别名的东西）；否则指代 X 本身（例如一个值、一个基类关系）。

为什么 splice 需要常量表达式？因为拼接是**编译期**的代码生成：`[: r :]` 的含义（它是变量还是函数？什么类型？）决定了周围代码如何解析和类型检查，所以 `r` 的值必须在编译期已知。在 `consteval` 函数里对**形参** `v` 写 `[: v :]` 是非良构的——形参不是常量表达式（[[basic.splice]] 中的例子）。

## 什么时候 [: :] 不是表达式（¶1）

¶1 *splice-specifier* 或 *splice-specialization-specifier* 若**紧跟** `::` 或**前面有** `typename`，就永远不会被解释为 splice 表达式的一部分。

前者是嵌套名说明符（`[: ^^S :]::a`，见 [[expr.prim.id.qual]]），后者是类型拼接（`typename [: ^^int :]`，见 [[dcl.type.splice]]）。这是一个**纯语法**的消歧规则：解析器看到 `[:` 时无法知道里面代表什么，只能依靠周围的记号来决定。

```cpp
struct S { static constexpr int a = 1; };
template<typename> struct TCls { static constexpr int b = 2; };

constexpr int c = [:^^S:]::a;                   // OK：[:^^S:] 后跟 ::，是嵌套名说明符而非表达式
constexpr int d = template [:^^TCls:]<int>::b;  // OK：同上，template [:^^TCls:]<int> 不是表达式
template<auto V> constexpr int e = [:V:];       // OK：V 是常量（模板形参），依赖的 splice 表达式
constexpr int f = template [:^^e:]<^^S::a>;     // OK：变量模板特化的 splice 表达式，值为 1

constexpr auto g = typename [:^^int:](42);      // OK：typename [:^^int:] 是类型，这是函数式转换

constexpr auto h = ^^g;
constexpr auto i = e<[:^^h:]>;                  // error: 未加括号的 splice 表达式作模板实参
constexpr auto j = e<([:^^h:])>;                // OK
```

最后两行值得解释：在模板实参列表中，一个**未加括号**的 `[: r :]` 被禁止作为表达式实参。原因是模板实参可以是类型、表达式或模板，而 `[:^^h:]` 单看语法无法判断属于哪一类——若把它当作表达式，那么当 `h` 实际代表一个类型时就会产生令人困惑的错误。要求加括号 `([:^^h:])` 强制它被解析为表达式（括号里只能是表达式），消除歧义。这是 [[expr.prim.paren]] "括号通常不改变含义"的又一个例外。

## splice-specifier 形式的语义（¶2）

¶2 对形如 `[: r :]` 的 splice 表达式 E，令 S 为 splice 说明符所指代的构造：

### 不可拼接的构造（¶2.1）

E 非良构，若 S 是：

- (2.1.1) **构造函数**、(2.1.2) **析构函数**——它们在 C++ 中本来就不能通过名字"作为表达式"使用（构造函数没有名字可以引用，析构函数只能以 `obj.~T()` 形式调用，[[expr.prim.id.dtor]]）；
- (2.1.3) **无名位域**——没有名字，也不能被访问；
- (2.1.4) 满足以下两个条件的**局部实体**：(2.1.4.1) 在表达式与 S 被引入的位置之间隔着一个 **lambda 作用域**，且 (2.1.4.2) 若忽略外围 `typeid` 的影响，表达式会被潜在求值。

(2.1.4) 是对 lambda 捕获规则的呼应：lambda 的隐式捕获是**语法驱动**的（[[expr.prim.lambda.capture#7]]）——编译器扫描 lambda 体中的名字决定捕获什么。而 `[: r :]` 中的 `r` 只是一个常量表达式，扫描时看不出它会指向哪个局部变量，所以**无法驱动捕获**。与其让捕获集合依赖于常量求值的结果，不如直接禁止跨 lambda 拼接局部实体（在未求值操作数里则无妨，例如 `sizeof([: r :])`）。

```cpp
void f() {
  int x = 0;
  constexpr auto r = ^^x;
  [: r :] = 1;                        // OK：没有中间的 lambda 作用域
  [&] { [: r :] = 2; }();             // error: 跨越 lambda 作用域拼接局部实体
  [&] { (void)sizeof([: r :]); }();   // OK：未求值
}
```

同样的考虑也体现在反射运算符一侧：[[expr.reflect]] 规定，若 `^^x` 与局部实体 `x` 的引入点之间隔着 lambda 作用域，`^^x` 本身就非良构。所以在 lambda 内部既不能反射外部局部变量，也不能（潜在求值地）拼接从外部带进来的反射。

### 函数：重载集（¶2.2）

(2.2) 若 S 是函数 F，表达式指代一个**重载集**，包含 F 的所有声明中位于以下位置之前的那些：表达式本身，或者（若表达式处于某个类的完整类上下文中）最外层类的 *class-specifier* 结束处。然后执行重载决议（[[over.match]]、[[over.over]]）。

为什么是"F 的所有声明"而不是"所有同名函数"？因为反射值 `^^f` 代表的是**一个特定的函数**（[[expr.reflect]] 要求 `&f` 能唯一确定一个函数，否则 `^^f` 非良构；有重载时通常要借助 `std::meta::members_of` 之类的元函数取得某个具体重载的反射），所以 splice 只会得到"这一个函数"的各次声明（它们可能有不同的默认实参），而不会把同名的其他重载混进来。重载决议在这里主要用来处理默认实参与形参匹配。

### 对象与非静态数据成员（¶2.3）

(2.3) 若 S 是**对象**或**非静态数据成员**，表达式是指代 S 的 **lvalue**，类型与 S 相同；当且仅当 S 是位域时它是位域。

注释 1 强调了与 id 表达式最大的不同：

!!! std
    The implicit transformation whereby an *id-expression* denoting a non-static member becomes a class member access does not apply to a *splice-expression*.

    id 表达式指代非静态成员时会被隐式改写为 `(*this).m`；splice 表达式不会。

也就是说，在成员函数里写 `[: ^^S::m :]`（不加对象）**不**等于 `this->m`。指代非静态数据成员的 splice 表达式只能用在 [[expr.prim.id.general#4]] 允许的场合：作为类成员访问的右操作数（`obj.[: r :]`）、形成成员指针（`&[: r :]`）、或位于未求值操作数中。

```cpp
struct S { int m; };
int S::* k = &[:^^S::m:];            // OK：形成成员指针（[expr.prim.id.general] 例 4）

void g(S s) {
  s.[:^^S::m:] = 42;                 // OK：类成员访问的右操作数
  int n = sizeof([:^^S::m:]);        // OK：未求值操作数
}
struct T {
  int m;
  void h() { [:^^T::m:] = 1; }       // error: 不会改写为 this->m，单独使用非静态数据成员
};
```

为什么不做隐式变换？一个合理的解释是：splice 表达式的主要用途是元编程，如"遍历某个类的所有数据成员并访问之"，这时被访问的对象几乎总是**显式给出**的（`obj.[: member :]`），而不是隐式的 `*this`。省去隐式变换，使 splice 的语义更加局部、可预测——`[: r :]` 的含义只取决于 `r`，不取决于它碰巧出现在哪个类的成员函数中。

### 直接基类关系（¶2.4）

(2.4) 若 S 是一个**直接基类关系** (D, B)（由 `std::meta::bases_of` 之类的元函数得到），表达式是指代 S 的 lvalue，类型为 `B`。结合 [[expr.prim.id.general#5]]：这样的 splice 表达式只能作为类成员访问的第二个操作数，`d.[: base_rel :]` 得到 `d` 的 `B` 基类子对象。这是 C++ 中第一次可以"按名字之外的方式"访问基类子对象——即使基类名字有歧义或不可访问。

### 变量与结构化绑定（¶2.5）

(2.5) 若 S 是**变量**或**结构化绑定**，S 要么具有静态或线程存储期，要么必须位于**包含该表达式的作用域**中。E 是指代与 S 关联的或被 S 引用的对象或函数 X 的 **lvalue**；当且仅当 X 是位域时 E 是位域。

- "位于包含该表达式的作用域"：防止你把一个反射值从一个函数带到另一个函数中拼接——那个局部变量在别处根本不存在（或者属于另一次调用）。
- "被 S 引用的对象或函数"：若 S 是引用变量，E 直接指代被引用者（与 id 表达式一样，引用类型按 [[expr.type]] 调整为非引用类型，见注释 2）。

类型：若 E 出现在契约断言 C 的谓词中，且 S 是 C 之外声明的对象类型变量、引用变量或结构化绑定，则类型为 `const T`（与 [[expr.prim.id.unqual#7]] 平行）；否则类型与 S 相同。

注意 ¶2.5 与 id 表达式的差异：id 表达式命名变量时，变量可能是 **move-eligible** 的（[[expr.prim.id.unqual#15]] 明确把 *splice-expression* 也列入），所以 `return [: ^^x :];` 同样可以隐式移动。

### 值与枚举项（¶2.6）

(2.6) 若 S 是一个**值**（例如 `std::meta::reflect_constant(42)` 得到的反射）或**枚举项**，表达式是一个计算 S 的 **prvalue**，类型与 S 相同。这与 id 表达式中枚举项是 prvalue（[[expr.prim.id.unqual#12]]）一致。

### 其他（¶2.7）

(2.7) 否则（例如 S 是类型、命名空间、模板、概念……）表达式非良构。类型要拼接成类型（`typename [: r :]`），命名空间要拼接成嵌套名说明符或用于 using 指令——它们不是表达式。

## template [: r :] 形式（¶3）

¶3 对 `template [: r :]`，splice 说明符必须指代一个**函数模板** T（且不是构造函数模板）。表达式指代 T 的所有（位于表达式之前，或类的完整类上下文中最外层类定义结束前的）声明组成的重载集，并执行重载决议；注释 3：候选函数模板会经过模板实参推导，推导出的特化作为候选函数。

为什么必须写 `template`？因为若 `[: r :]` 代表一个函数模板，后面紧接 `(` 进行调用时，编译器在解析阶段无法知道 r 代表的是模板——`template` 关键字告诉它"这是一个模板，请按模板处理"，这与依赖名字前的 `template` 消歧（[[temp.names]]）同理。

## template [: r :]<args> 形式（¶4）

¶4 对 `template [: r :]<args>`，splice 说明符必须指代一个**模板** T：

- (4.1) 若 T 是**函数模板**，表达式指代 T 的（如上范围内的）声明组成的重载集，执行重载决议（显式模板实参为 `args`）；
- (4.2) 若 T 是**变量模板**，令 S 为对应 `args` 的特化，表达式是指代与 S 关联的对象的 lvalue，类型与 S 相同；
- (4.3) 否则非良构（类模板特化是类型，不是表达式；概念特化则应当用作约束……）。

```cpp
template<int V> constexpr int e = V;
template<class T> constexpr T twice(T t) { return t + t; }

constexpr int a = template [:^^e:]<3>;            // OK：变量模板特化，lvalue
constexpr int b = template [:^^twice:]<int>(4);   // OK：函数模板，显式模板实参后调用
constexpr int c = template [:^^twice:](5);        // OK：¶3 形式，推导 T = int
```

## 访问控制（¶4 注释 4）

注释 4 指出了 splice 与普通名字的一个重要差异：

- 通过 splice 表达式指代的类成员，在**任何位置都是可访问的**（[[class.access.base]]）——访问检查发生在**获取反射值**的时候（例如 `std::meta::members_of` 可以按访问上下文过滤，[[meta.reflection.access.context]]），而不是在拼接时；
- 右操作数是 splice 表达式的类成员访问，若左操作数（视为指针）不能隐式转换为指向右操作数**指名类**（designating class）的指针，则非良构——即不能通过一个无关类型的对象访问成员。

第一点是有意的设计：反射的核心用例之一是序列化、调试打印等需要"看到所有成员"的库，若每次拼接都做访问检查，这些库将无法实现。代价是：拿到了私有成员的反射，就能访问它——反射是一种**显式的、可审计的**绕过访问控制的方式（就像 `reinterpret_cast` 之于类型系统）。

## 与 id 表达式对比

| | id 表达式 | splice 表达式 |
|---|---|---|
| 如何确定实体 | 名字查找 | 常量求值得到的反射值 |
| 非静态成员的隐式 `(*this).` 变换 | 有（[[expr.prim.id.general#2]]） | **无** |
| 访问检查 | 在使用点 | 不检查（在获取反射时检查） |
| 跨 lambda 引用局部实体 | 触发捕获 | 潜在求值时**非良构** |
| 函数 → 重载集 | 所有同名可见声明 | 仅该函数（模板）的先前声明 |
| 作为模板实参 | 直接写 | 必须加括号 |
| 基类子对象 | 不可能 | `obj.[: base :]` |
| move-eligible | 是 | 是（[[expr.prim.id.unqual#15]]） |

## 实现视角

!!! impl
    - P2996 的参考实现是 Bloomberg 维护的 Clang 分支（"clang-p2996"），在 Compiler Explorer 上可选用；EDG 也有实验性实现。主线 Clang 截至写作时尚未完整支持。
    - `std::meta::info` 在实现中通常是一个指向编译器内部 AST 节点的不透明句柄，只在常量求值中有意义，不能流入运行期代码。
    - 拼接在模板中可能是**依赖**的（`[: V :]`，`V` 为模板形参），此时推迟到实例化再解析（[[temp.dep.splice]]）。

## 历史与演进

!!! history
    - 反射的研究持续了十余年（Reflection TS 基于类型的反射，之后转向基于值的 `std::meta::info` 设计）。
    - **C++26**：[[P2996R13]]（Reflection for C++26）被采纳，引入 `^^`、`[: :]` 与 `<meta>` 头文件。在此之前，C++ 中没有任何把"编译期计算出的东西"变回名字/表达式的机制，只能借助宏或模板技巧。
    - `^^` 运算符的拼写在提案演化过程中几经修改（早期版本使用 `^`，因与 Objective-C++ 的块语法冲突而改为 `^^`）。

## 陷阱

!!! pitfall "模板实参中忘记加括号"
    `foo<[: r :]>` 非良构；写 `foo<([: r :])>`。若 `r` 代表类型，则写 `foo<typename [: r :]>`。

!!! pitfall "在成员函数中拼接数据成员"
    `[: member :]` 不会变成 `this->[: member :]`。写 `this->[: member :]` 或 `(*this).[: member :]`。

!!! pitfall "在 consteval 函数中对形参拼接"
    `consteval int get(std::meta::info r) { return [: r :]; }` 非良构：`r` 是函数形参，不是常量表达式。需要把反射值作为**模板实参**传入（`template<std::meta::info R> ... [: R :]`），或者在 `template for`（展开语句）中使用常量。

## 思考题

!!! question "思考题 1"
    下面的代码是否良构？
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

- `#1` 良构：id 表达式 `x` 被隐式变换为 `(*this).x`（[[expr.prim.id.general#2]]）。
- `#2` 非良构：splice 表达式不做隐式变换（¶2.3 注释 1），于是"单独使用非静态数据成员"违反 [[expr.prim.id.general#4]]（潜在求值、不是成员访问、不是形成成员指针）。
- `#3` 良构：类成员访问，`this` 可以隐式转换为 `B*`（右操作数的指名类是 `B`）。
</details>

!!! question "思考题 2"
    为什么跨越 lambda 拼接一个局部变量是非良构的，而不是让它被隐式捕获？

<details markdown="1">
<summary>答案</summary>

隐式捕获由 lambda 体中出现的**名字**在语法上决定（[[expr.prim.lambda.capture#7]]），捕获集合需要在不做常量求值的情况下就能确定（它影响闭包类型的布局）。`[: r :]` 中只有一个常量表达式，必须先常量求值才知道它指向哪个变量；让捕获依赖于常量求值会把两个阶段纠缠在一起。因此标准选择禁止（未求值操作数中不需要捕获，所以允许）。若确实需要，在捕获列表中显式捕获该变量，并在 lambda 内对**捕获**进行反射。
</details>

## 小结

!!! summary
    - `[: r :]` 作为表达式时：不能紧跟 `::`、不能前有 `typename`（那些是其他语法）；作为模板实参必须加括号。
    - 构造函数、析构函数、无名位域不能拼接；跨 lambda 作用域潜在求值地拼接局部实体非良构。
    - 函数 → 重载集（仅该函数的先前声明）；对象/数据成员/变量/结构化绑定 → lvalue；基类关系 → 类型为基类的 lvalue；值/枚举项 → prvalue。
    - 与 id 表达式最大的区别：**没有**隐式 `(*this).` 变换，**不做**访问检查。
    - `template [: r :]` 用于函数模板；`template [: r :]<args>` 用于函数模板或变量模板。
