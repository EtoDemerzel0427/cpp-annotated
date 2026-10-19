---
title: 函数模板
summary: 函数模板定义一族函数；非模板函数永远不是模板特化；函数模板可以重载出同类型的不同特化；签名中涉及模板形参的表达式是签名的一部分；表达式、template-head、模板形参的等价与功能等价，以及功能等价但不等价为何是 IFNDR
status: done
covers: temp.fct.general, temp.over.link
since: c++98
related: temp.func.order, temp.decls, temp.over, temp.deduct, basic.def.odr, basic.scope.scope, basic.link, intro.defs, temp.constr.decl, temp.class
tags: 模板, 函数模板, 等价, 功能等价, IFNDR, 签名
updated: 2026-10-18
---

函数模板是 C++ 泛型编程的主要工具。13.7.7 [temp.fct] 有三个小节：本页覆盖 13.7.7.1 [temp.fct.general]（函数模板与非模板函数的关系）和 13.7.7.2 [temp.over.link]（两个函数模板声明什么时候是同一个，即等价与功能等价）；13.7.7.3 的偏序另见 [[temp.func.order]]。

[temp.over.link] 的标题是"函数模板重载"，但它真正回答的问题是：两个声明什么时候声明同一个函数模板（重声明，可以链接到一起），什么时候声明两个不同的重载？对普通函数，答案很简单，比较参数类型即可。对函数模板，签名中可能出现 `A<I+J>` 这样的表达式，比较表达式就成了问题：`I+J` 和 `J+I` 一样吗？`I+10` 和 `I+1+2+3+4` 呢？标准给出的是一个精心设计的折中：按记号结构比较（等价），把结构不同但语义相同的情形（功能等价）定为 IFNDR。

---

## 13.7.7.1 概述

### 函数模板定义一族函数（¶1）

¶1 函数模板定义一个无界的相关函数集合：

```cpp run ok
template<class T> class Array { };
template<class T> void sort(Array<T>&) { }   // 对每个 T 一个 sort
int main() { Array<int> a; sort(a); }
```

### 非模板函数与函数模板无关（¶2）

¶2 先是一个注：函数模板可以与其他函数模板、非模板函数在同一作用域中同名（[[dcl.fct]]，即重载）。接着是规范性规则：

!!! std
    A non-template function is not related to a function template (i.e., it is never considered to be a specialization), even if it has the same name and type as a potentially generated function template specialization.

**非模板函数与函数模板无关，永远不会被看作特化**，即使它与函数模板可能生成的某个特化同名同类型。脚注 108 解释说，非模板函数的声明并不只是引导重载决议去选那个特化；如果它被 odr-use，就必须有定义，编译器不会用函数模板的定义来隐式实例化它。

```cpp
void f(int);                     // 非模板函数：只有声明
template<class T> void f(T) { }  // 函数模板

int main() { f(1); }             // 选中非模板 f(int)（平局时非模板优先）→ 链接错误：f(int) 未定义
```

重载决议在 `f(int)` 与 `f<int>(int)` 之间选择了非模板（[[over.match.best]]），而它没有定义。很多人以为编译器会用模板为非模板声明生成定义，实际上不会。要为特定类型定制模板的行为，应写显式特化 `template<> void f<int>(int) { ... }`（[[temp.expl.spec]]），它才是模板的特化；非模板重载是另一个函数。

!!! note "显式特化 vs 非模板重载"
    | | 非模板重载 `void f(int)` | 显式特化 `template<> void f(int)` |
    |---|---|---|
    | 是否是模板的特化 | 否 | 是 |
    | 是否参与重载决议 | 作为独立候选 | 不直接参与：先选中模板，再用特化的定义 |
    | 平局时 | 优先于模板特化 | 与模板同进退 |
    | 允许隐式转换 | 是（不需推导） | 否（只有推导成功才会用到） |

    一般来说，想改变某些类型的行为时优先用重载；只在必须时（如定制点要求特化）才显式特化函数模板。

---

## 13.7.7.2 函数模板重载与等价

### 不同模板的特化可以同类型（¶1–2）

¶1 函数模板可以重载，使两个不同的函数模板特化具有相同的类型：

```cpp title="tu1.cpp"
template<class T> void f(T*);
void g(int* p) {
    f(p);            // 调用 f<int>(int*)，来自 template<class T> void f(T*)
}
```

```cpp title="tu2.cpp"
template<class T> void f(T);
void h(int* p) {
    f(p);            // 调用 f<int*>(int*)，来自 template<class T> void f(T)
}
```

¶2 这两个特化是不同的函数，即使它们的函数类型都是 `void(int*)`，也不违反 ODR。这之所以可能，是因为**函数模板特化的签名**（[[intro.defs]]）**不只包含函数类型，还包含模板形参列表、模板实参和返回类型**。在 Itanium ABI 中，`f<int>(int*)` 的 mangled 名编码的是 `T*` 形参与 `T = int`，`f<int*>(int*)` 编码的是 `T` 形参与 `T = int*`，所以链接器把它们看作两个符号。

### 签名与形参名（¶3）

¶3 函数模板的签名在 [[intro.defs]] 中定义。模板形参的名字只用来建立形参与签名其余部分的联系，名字本身无关紧要。注 1 指出，两个不同的函数模板可以有完全相同的返回类型和函数参数列表，即使重载决议无法单独区分它们：

```cpp run ok
template<class T> void f() { }
template<int I>   void f() { }   // OK: 重载第一个模板；模板形参的种类不同
int main() {
    f<int>();                    // 第一个
    f<1>();                      // 第二个
}
```

### 签名中的表达式（¶4）

¶4 如果函数模板声明的函数参数列表或返回类型中使用了引用模板形参的表达式，这个表达式就是函数模板签名的一部分。这样规定，是为了让一个 TU 中的声明能与另一个 TU 中的声明链接起来，同时确保本意不同的函数模板不会链接到一起。

```cpp error
template<int> struct A { };
template<int I, int J> A<I+J> f(A<I>, A<J>);                     // #1
template<int K, int L> A<K+L> f(A<K>, A<L>) { return { }; }      // 与 #1 相同（重声明并定义 #1）
template<int I, int J> A<I-J> f(A<I>, A<J>) { return { }; }      // 与 #1 不同：另一个重载

void t() { f(A<1>{}, A<2>{}); }   // error: 歧义——两个模板都能推导，参数类型相同，偏序无法区分
```

返回类型 `A<I+J>` 与 `A<I-J>` 使两个模板成为不同的重载；调用时它们的函数参数一模一样，重载决议无法区分。这正是注 1 说的情形，需要用别的手段（如取地址时指定目标类型）才能区分。

注 2 补充说，大多数涉及模板形参的表达式使用的是常量模板形参，但也可以引用类型形参，例如 `sizeof(T)`。

### 表达式的等价（¶5）

¶5 是本节的核心定义，分四部分：

**(1) 涉及模板形参的表达式**：两个这样的表达式[[g:expression-equivalent-template|**等价**]]（equivalent），是指包含它们的两个函数定义满足 ODR（[[basic.def.odr]]），只不过指称模板形参的记号可以不同，前提是一边指称某个形参的记号，在另一边换成了指称同一个形参的记号。直观地说，就是按记号逐一比较，模板形参可以按位置换名。所以 `A<I+J>`（用 `I, J`）与 `A<K+L>`（用 `K, L`）等价，而 `I+J` 与 `J+I` 不等价（记号顺序不同）。

**(2) 不涉及模板形参的不求值操作数**：两个这样的不求值操作数等价，是指包含它们的两个函数定义满足 ODR，只不过指称类型和声明的记号可以不同（只要指称同一实体），构成 concept-id 的记号也可以不同（只要两个 *template-id* 相同，[[temp.type]]）。注 3 举的例子是 `A<42>` 和 `A<40+2>` 指称同一个类型。

**(3) lambda 表达式永远不等价。** 注 4 说明，这样做的目的是避免 lambda 出现在具有外部链接的函数模板的签名中。每个 lambda 都有唯一的闭包类型，两个 TU 中写法相同的 lambda 是否是同一类型无法保证。

**(4) 依赖名**：判断两个依赖名（[[temp.dep]]）是否等价，只看名字本身，不看名字查找的结果。注 5 指出，未限定的依赖名从函数模板的第一个声明处查找（[[temp.res.general]]）。

```cpp error
template<int> struct A { };
template<int I, int J> void f(A<I+J>);          // #1
template<int K, int L> void f(A<K+L>);          // 与 #1 相同

template<class T> decltype(g(T())) h();
int g(int);
template<class T> decltype(g(T())) h()          // h 的重声明：沿用第一个声明处的查找……
    { return g(T()); }                          // ……尽管在这里查找能找到 g(int)
int i = h<int>();                               // 标准：代入失败——在 h 的第一个声明处 g(int) 不可见
```

`h` 这个例子说明了依赖名只比较名字的意义。两个 `decltype(g(T()))` 等价（名字都是 `g`），所以第二个是第一个的重声明；而签名中 `g` 的查找发生在第一个声明处，那时 `g(int)` 还未声明。`g(T())` 是依赖调用，实例化时只追加 ADL，而 `int` 没有关联命名空间，ADL 找不到 `g(int)`，所以代入失败，`h<int>` 没有可行的候选。

!!! warning "编译器现状"
    截至写作时，本机 Clang 23 接受 `int i = h<int>();`，没有报错，它在实例化签名时找到了第一个声明之后才声明的 `g(int)`。按标准这里应当代入失败。这属于编译器与标准的偏差，可移植代码不应依赖签名中的依赖调用能找到后声明函数的行为。

标准例子的后半部分：

```cpp
// IFNDR：两个表达式功能等价但不等价
template<int N> void foo(const char (*s)[([]{}, N)]);
template<int N> void foo(const char (*s)[([]{}, N)]);

// 两个不同的声明：非依赖部分不被认为等价
template<class T> void spam(decltype([]{}) (*s)[sizeof(T)]);
template<class T> void spam(decltype([]{}) (*s)[sizeof(T)]);
```

- `foo`：数组界 `([]{}, N)` 是涉及模板形参的表达式，其中含有 lambda，因此两个表达式不等价（(3)）；但对任何 `N` 它们的值都相同，所以是功能等价的，落入 ¶7 的 IFNDR。
- `spam`：`decltype([]{})` 是不涉及模板形参的不求值操作数，两个 lambda 不等价，所以两个 `decltype` 是不同类型。这两个声明声明的是不同的函数模板，结论是确定的两个重载，而不是 IFNDR。

[[g:functionally-equivalent|**功能等价**]]（functionally equivalent）的定义（¶5 末）：

- 两个不等价的、涉及模板形参的潜在求值表达式，如果对任何给定的模板实参集合求值结果都相同，就是功能等价的；
- 两个不等价的不求值操作数，如果对任何给定的模板实参集合，它们都以相同的顺序对相同的实体执行相同的操作，就是功能等价的。注 6 举的例子是多了冗余的括号。

```cpp run ok
template<int I> concept C = true;
template<typename T> struct A {
    void f() requires C<42>;       // #1
    void f() requires true;        // OK: 不同的函数（见下）
};
int main() { }
```

例 4 有点微妙：`C<42>` 与 `true` 的值都是 `true`，为什么不是 IFNDR？因为 ¶5 中功能等价的定义只覆盖两类东西：涉及模板形参的潜在求值表达式，以及不求值操作数。`C<42>` 与 `true` 都不涉及模板形参（`C<42>` 的实参是字面量，与外围的 `T` 无关），也不是不求值操作数，功能等价的概念根本不适用于它们。它们记号不同，因此不等价；两个尾随 *requires-clause* 不等价，两个 `f` 也就不对应，是两个不同的成员函数（不过调用 `f()` 时，两者的约束都满足且互不更受约束，会产生歧义）。

### template-head 的等价（¶6）

¶6 两个 *template-head* 等价，当且仅当：

- 模板形参列表长度相同，对应的模板形参等价；
- 如果任一形参带 *type-constraint*，那么两者都带，且 *type-constraint* 等价；
- 如果任一 *template-head* 有 *requires-clause*，那么两者都有，且约束表达式等价。

两个模板形参等价的条件是：

- ¶6.1 种类相同（类型 / 常量 / 类型模板模板 / 变量模板模板 / 概念）；
- ¶6.2 如果一个是包，另一个也是包；
- ¶6.3 如果是常量模板形参，类型等价（忽略占位类型上的 *type-constraint*）；
- ¶6.4 如果是模板模板形参，它们的 *template-head* 等价。

比较类型或 *type-constraint* 中涉及模板形参的表达式时，用 ¶5 的规则。

如果两个 *template-head* 接受并被满足于（[[temp.constr.constr]]）相同的模板实参列表集合，它们就是功能等价的。

```cpp
template<class T> concept Int = __is_integral(T);

template<Int T>                   void g(T);   // #1
template<class T> requires Int<T> void g(T);   // #2：template-head 与 #1 功能等价但不等价 → IFNDR
template<Int T> requires true     void g(T);   // #3：与 #1 不等价（多了 requires-clause）
```

`template<Int T>` 与 `template<class T> requires Int<T>` 是 C++20 约束的两种写法，规范化后的约束相同，接受的实参集合也相同；但 ¶6 要求一方带 *type-constraint* 时另一方也要带，所以它们不等价。

### IFNDR（¶7）

¶7 包含两条规则。

**第一句**：如果程序的有效性或含义取决于两个结构是否等价，而它们**功能等价但不等价**，程序非良构，不要求诊断（{{ifndr}}）。

**第二句**：如果两个函数模板声明 A 和 B

- ¶7.1 引入同一个名字，
- ¶7.2 有对应的签名（[[basic.scope.scope]]），
- ¶7.3 在把 A、B 看作对应的前提下会声明同一实体（[[basic.link]]，即同一作用域、链接兼容），
- ¶7.4 接受并被满足于相同的模板实参列表集合，

但它们不对应（因为 template-head 或尾随约束不等价），程序 {{ifndr}}。

第二句补上了第一句的漏洞。上面的 #1 和 #2，*template-head* 功能等价但不等价，因此不对应，于是它们是重载还是重声明取决于等价性，落入 IFNDR。实践中，编译器（按记号比较）把它们当作两个不同的重载，调用时则往往报歧义。

### 为什么这样设计（¶8）

¶8 的注解释了设计意图：这条规则保证等价的声明一定会链接到一起，同时不要求实现付出过大的代价去保证功能等价的声明被当作不同的声明。

```cpp
template<int> struct A { };

// 保证是同一个
template<int I> void f(A<I>, A<I+10>);
template<int I> void f(A<I>, A<I+10>);

// 保证是不同的
template<int I> void f(A<I>, A<I+10>);
template<int I> void f(A<I>, A<I+11>);

// IFNDR
template<int I> void f(A<I>, A<I+10>);
template<int I> void f(A<I>, A<I+1+2+3+4>);
```

为什么不直接规定功能等价的声明就是同一个？因为判断两个任意表达式是否对所有实参求值都相同，在一般情况下是不可判定的（等价于程序等价问题）。为什么不直接规定不等价的声明就是不同的？因为那样的话，编译器在 mangling 时就必须精确保留源码中的每个记号（包括冗余括号），而很多实现会对表达式做规范化；一旦两个 TU 中写法不同但规范化后相同的声明链接到了一起，程序的含义就取决于编译器的规范化策略。标准用 IFNDR 把这两种实现都纳入允许的范围。

!!! impl "实现视角：mangling 中的表达式"
    Itanium ABI 对签名中的依赖表达式按表达式树编码（例如 `A<I+10>` 编码为对 `T_` 与字面量 `10` 的 `pl` 运算）。所以 `A<I+10>` 与 `A<I+1+2+3+4>` 的 mangled 名不同，对 Clang 和 GCC 来说它们是两个函数模板。在同一 TU 中调用时，两者推导结果相同、参数相同，于是报歧义；在不同 TU 中分别声明与定义时，则表现为链接错误（找不到符号）。这都是 IFNDR 允许的结果。

```cpp ifndr
template<int> struct A { };
template<int I> void f(A<I>, A<I+10>);
template<int I> void f(A<I>, A<I+1+2+3+4>) { }
void t() { f(A<1>{}, A<11>{}); }   // Clang：调用歧义（它把两者当作不同的模板）——IFNDR 程序的一种表现
```

---

## 历史与演进

!!! history "历史与演进"
    - **C++98**：等价/功能等价的框架已经存在，针对的是 `A<I+J>` 这类常量表达式。
    - **C++11**：`decltype` 让任意表达式（包括函数调用）进入签名，依赖名只比较名字这条规则变得更加重要（表达式 SFINAE）。
    - **C++20**：约束进入 *template-head* 与尾随 *requires-clause*，¶6 扩展到 *type-constraint* 与 *requires-clause* 的等价；lambda 可以出现在不求值操作数中，于是加上了 lambda 永不等价的规则；¶7 第二句处理功能等价的不同约束写法。
    - **C++26**：模板形参的种类扩展到变量模板模板形参与概念模板形参（¶6.1）。

## 陷阱

!!! pitfall "常见误解"
    - 误以为声明一个同名同类型的非模板函数后，编译器会用模板生成它的定义。不会（[temp.fct.general] ¶2），它是另一个函数，必须自己定义。
    - 误以为 `template<C T>` 和 `template<class T> requires C<T>` 是同一个声明的两种写法，可以在声明和定义中混用。它们功能等价但不等价，混用是 IFNDR（Clang 实际会报错）。
    - 误以为 `A<I+J>` 和 `A<J+I>` 是一样的。它们不等价；对整数加法它们功能等价，所以混用是 IFNDR。
    - 误以为两个函数类型相同的函数模板特化违反 ODR。不违反，它们是不同模板的特化，签名不同。

## 思考题

!!! question "思考题 1"
    下面各对声明中，哪些是同一个模板，哪些是不同的模板，哪些是 IFNDR？

    ```cpp
    template<int> struct A {};
    template<int N> void f(A<N*2>);   // (a)
    template<int M> void f(A<M*2>);   // (b)
    template<int N> void f(A<(N*2)>); // (c)
    template<int N> void f(A<2*N>);   // (d)
    template<int N> void f(A<N*3>);   // (e)
    ```

<details markdown="1">
<summary>答案</summary>

- (a)(b)：等价（只是形参换名），是同一个模板。
- (a)(c)：多了冗余括号。括号本身是记号，所以两个表达式不等价；但对所有 `N` 值都相同，是功能等价的，因此是 IFNDR（注 6 正是以冗余括号为例）。
- (a)(d)：`N*2` 与 `2*N` 记号顺序不同，不等价；值相同，功能等价，因此是 IFNDR。
- (a)(e)：不等价，且对 `N = 1` 值不同，不是功能等价的，保证是不同的模板（重载）。
</details>

!!! question "思考题 2"
    `template<class T> void f(T); void f(int);` 中，`f<int>` 与 `f(int)` 是同一个函数吗？`&f<int>` 和 `static_cast<void(*)(int)>(&f)` 得到的指针相等吗？

<details markdown="1">
<summary>答案</summary>

不是同一个函数（[temp.fct.general] ¶2）。`&f<int>` 指向模板特化；`static_cast<void(*)(int)>(&f)` 对重载集取地址（[[over.over]]），候选是非模板 `f(int)` 与推导出的 `f<int>`，非模板优先，结果指向非模板 `f(int)`。两个指针指向不同的函数，比较不相等。
</details>

!!! summary "小结"
    - 非模板函数永远不是函数模板的特化；被 odr-use 时必须自己有定义。
    - 函数模板特化的签名包含模板形参列表与模板实参，所以不同模板可以产生同类型的不同特化。
    - 签名中涉及模板形参的表达式是签名的一部分；比较时按记号结构判断等价，形参可换名，依赖名只比较名字，lambda 永不等价。
    - template-head 等价要求形参逐一等价（种类、包、类型、嵌套 template-head），约束写法也要一致。
    - 功能等价但不等价是 IFNDR；声明同名、签名对应、接受同样的实参，却因 template-head 或约束不等价而不对应，也是 IFNDR。
