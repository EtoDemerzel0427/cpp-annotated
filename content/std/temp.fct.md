---
title: 函数模板
summary: 函数模板与同名非模板函数的关系，以及两个函数模板声明在什么条件下是同一个模板、什么条件下是两个重载，签名中的表达式怎样比较。
status: done
covers: temp.fct.general, temp.over.link
since: c++98
related: temp.func.order, temp.decls, temp.over, temp.deduct, basic.def.odr, basic.scope.scope, basic.link, intro.defs, temp.constr.decl, temp.class
tags: 模板, 函数模板, 等价, 功能等价, IFNDR, 签名
updated: 2026-10-19
---

!!! tldr
    - 与函数模板同名同类型的非模板函数不是它的特化。被调用时它必须有自己的定义，编译器不会用模板替它生成。
    - 函数模板特化的签名包含模板形参列表和模板实参，所以两个不同模板可以生成类型相同、互不冲突的特化。
    - 签名里引用模板形参的表达式（如 `A<I+J>`）是签名的一部分。两个声明是否为同一个模板，按记号逐一比较，形参可以换名。
    - 写法不同但对任何实参结果都相同（功能等价）的两个声明，例如 `A<I+10>` 与 `A<I+1+2+3+4>`，程序非良构且不要求诊断。

函数模板是一族函数的定义（[temp.fct.general] ¶1）。例如 `template<class T> void sort(Array<T>&);` 对每个 `T` 定义一个 `sort`。本页讨论两个问题：函数模板和同名的普通函数是什么关系；两个函数模板声明什么时候是同一个模板。函数模板之间怎样排序见 [[temp.func.order]]。

## 非模板函数不是模板的特化 [temp.fct.general]

```cpp run
void f(int);                      // 非模板函数，只有声明
template<class T> void f(T) { }   // 函数模板，有定义

int main() { f(1); }              // 选中 f(int)，链接失败
```

调用 `f(1)` 时有两个候选：非模板的 `f(int)`，以及模板推导出的 `f<int>(int)`。两者同样好时，重载决议优先选非模板（[[over.match.best]]）。可是 `f(int)` 没有定义，本机 Clang 23 编译通过，链接时报 `f(int)` 未定义。

¶2 标准明确规定，非模板函数与函数模板无关，即使它与模板可能生成的某个特化同名同类型，也永远不会被看作那个特化。脚注说明，这样的非模板声明不只是给重载决议指路；它被 odr-use 时就必须有定义，编译器不会用模板的定义去实例化它。

要为某个类型定制模板的行为，有两种写法，它们是不同的东西：

| | 非模板重载 `void f(int)` | 显式特化 `template<> void f(int)` |
|---|---|---|
| 是否是模板的特化 | 否，是另一个函数 | 是 |
| 怎样参与重载决议 | 作为独立的候选 | 不单独参与：先选中模板，再使用特化的定义 |
| 与模板打平时 | 优先于模板 | 跟随模板 |
| 实参可否隐式转换 | 可以，不需要推导 | 只有模板推导成功才会用到它 |

一般优先用重载。只有接口明确要求特化时（例如某些定制点），才显式特化函数模板（[[temp.expl.spec]]）。

## 两个声明是不是同一个模板 [temp.over.link]

对普通函数，比较参数类型就能判断两个声明是重声明还是重载。函数模板的签名里可能出现 `A<I+J>` 这样的表达式，比较就难了：`I+J` 和 `J+I` 算一样吗？`I+10` 和 `I+1+2+3+4` 呢？本节的回答是：按记号结构比较；结构不同而语义相同的情形，程序非良构且不要求诊断。

### 不同模板的特化可以类型相同（¶1–¶3）

¶1 函数模板可以重载，使两个不同的特化有相同的类型：

```cpp title="tu1.cpp"
template<class T> void f(T*);
void g(int* p) {
  f(p);    // 调用 f<int>(int*)，来自 f(T*)
}
```

```cpp title="tu2.cpp"
template<class T> void f(T);
void h(int* p) {
  f(p);    // 调用 f<int*>(int*)，来自 f(T)
}
```

¶2 这两个特化是不同的函数，虽然类型都是 `void(int*)`，却不违反 ODR。原因是函数模板特化的签名不只是函数类型，还包括模板形参列表、模板实参和返回类型（[[intro.defs]]）。在 Itanium ABI 下，两者的修饰名分别编码了 `T*` 加 `T = int` 和 `T` 加 `T = int*`，链接器看到的是两个符号。

¶3 函数模板签名中，模板形参的名字只用来把形参和签名的其余部分联系起来，名字本身无关紧要。注 1 指出，两个模板的返回类型和函数参数列表可以完全相同：

```cpp run ok
template<class T> void f() { }
template<int I>   void f() { }   // OK: 另一个模板，形参种类不同
int main() {
  f<int>();   // 第一个
  f<1>();     // 第二个
}
```

只凭重载决议分不开它们，但显式模板实参可以。

### 签名里的表达式（¶4）

¶4 如果函数模板的参数列表或返回类型里用了引用模板形参的表达式，这个表达式就是签名的一部分。这样一个翻译单元里的声明才能和另一个翻译单元里的声明链接到一起，本意不同的模板也不会被错误地链接。

```cpp error
template<int> struct A { };
template<int I, int J> A<I+J> f(A<I>, A<J>);                  // #1
template<int K, int L> A<K+L> f(A<K>, A<L>) { return { }; }   // 与 #1 相同：定义 #1
template<int I, int J> A<I-J> f(A<I>, A<J>) { return { }; }   // 与 #1 不同：另一个重载

void t() { f(A<1>{}, A<2>{}); }   // error: 歧义
```

返回类型 `A<I+J>` 和 `A<I-J>` 使两个模板成为不同的重载。调用时它们的参数完全一样，偏序也分不出高下，所以调用歧义。注 2 补充，这类表达式大多用常量模板形参，但也可以引用类型形参，例如 `sizeof(T)`。

### 等价：按记号比较（¶5）

¶5 两个引用模板形参的表达式是**等价**的（equivalent），如果把它们分别放进两个函数定义，这两个定义满足 ODR（[[basic.def.odr]]），只是指称模板形参的记号可以不同，只要两边在相同位置指称同一个形参。

直观地说，就是逐个记号比较，允许模板形参按位置换名。所以：

- `A<I+J>`（形参 `I, J`）与 `A<K+L>`（形参 `K, L`）等价；
- `I+J` 与 `J+I` 不等价，记号顺序不同；
- `N*2` 与 `(N*2)` 不等价，括号也是记号。

¶5 还有三条补充规则：

- **不涉及模板形参的不求值操作数**（例如 `sizeof` 或 `decltype` 的操作数），只要指称的类型、声明是同一个实体就算等价，记号可以不同。注 3 的例子是 `A<42>` 和 `A<40+2>` 指同一个类型。
- **两个 lambda 表达式永远不等价。** 注 4 说明，目的是不让 lambda 出现在具有外部链接的函数模板的签名里：每个 lambda 都有唯一的闭包类型，两个翻译单元里写法相同的 lambda 无法保证是同一个类型。
- **依赖名**（[[temp.dep]]）只比较名字本身，不比较名字查找的结果。注 5 指出，签名中未限定的依赖名，从函数模板的第一个声明处查找（[[temp.res.general]]）。

最后一条的例子：

```cpp
template<class T> decltype(g(T())) h();
int g(int);
template<class T> decltype(g(T())) h()   // h 的重声明，沿用第一个声明处的查找
  { return g(T()); }                     // 尽管在这里能找到 g(int)
int i = h<int>();                        // 代入失败：第一个声明处看不到 g(int)
```

两个 `decltype(g(T()))` 里的名字都是 `g`，所以等价，第二个声明是第一个的重声明。签名中 `g` 的查找发生在第一个声明处，那时 `g(int)` 还没声明。实例化时依赖调用只追加实参依赖查找，而 `int` 没有关联命名空间，找不到 `g(int)`，于是代入失败。

!!! warning "编译器现状"
    本机 Clang 23 接受 `int i = h<int>();`，它在实例化签名时找到了后声明的 `g(int)`。按标准这里应当代入失败。可移植代码不要依赖签名中的依赖调用能找到后声明的函数。

### 功能等价（¶5 末）

两个不等价的表达式，如果对任何一组模板实参都给出相同的结果，就是**功能等价**的（functionally equivalent）。具体地说：

- 潜在求值的表达式，对任何模板实参求值结果都相同；
- 不求值操作数，对任何模板实参都以相同的顺序对相同的实体做相同的操作。注 6 举的例子是多了一对冗余的括号。

标准例子的后半段：

```cpp
// IFNDR：两个表达式功能等价，但不等价
template<int N> void foo(const char (*s)[([]{}, N)]);
template<int N> void foo(const char (*s)[([]{}, N)]);

// 两个不同的声明：非依赖的部分不等价
template<class T> void spam(decltype([]{}) (*s)[sizeof(T)]);
template<class T> void spam(decltype([]{}) (*s)[sizeof(T)]);
```

`foo` 的数组界 `([]{}, N)` 引用了模板形参，又含有 lambda，所以两边不等价；但对任何 `N` 它的值都是 `N`，两边功能等价，落入下文 ¶7 的 IFNDR。`spam` 中的 `decltype([]{})` 不涉及模板形参，两个 lambda 不等价，所以两个 `decltype` 是不同的类型，这两行确定地声明了两个不同的模板。

功能等价只覆盖上面两类表达式，例 4 说明了它的边界：

```cpp run ok
template<int I> concept C = true;
template<typename T> struct A {
  void f() requires C<42>;   // #1
  void f() requires true;    // OK: 另一个函数
};
int main() {}
```

`C<42>` 和 `true` 的值都是 `true`，但两者都不引用模板形参，也不是不求值操作数，功能等价的定义不适用。它们的记号不同，所以不等价，两个 `f` 是不同的成员函数。这个类本身合法，但调用 `f()` 时两者的约束都满足，又互不更受约束，本机 Clang 23 报告调用歧义。

### template-head 的等价（¶6）

¶6 两个 *template-head*（`template<...>` 加可选的 requires 子句）等价，要满足三点：

- 模板形参列表长度相同，对应的形参等价；
- 只要一边的形参带 *type-constraint*（如 `template<Int T>` 中的 `Int`），另一边也要带，而且二者等价；
- 只要一边有 requires 子句，另一边也要有，而且约束表达式等价。

两个模板形参等价，要求：

- ¶6.1 种类相同：类型、常量、类型模板模板、变量模板模板或概念；
- ¶6.2 一个是包，另一个也是包；
- ¶6.3 常量形参的类型等价，忽略占位类型上的 *type-constraint*；
- ¶6.4 模板模板形参的 *template-head* 等价。

两个 *template-head* 如果接受、并被同样的一组模板实参列表满足，就是功能等价的。

```cpp
template<class T> concept Int = __is_integral(T);

template<Int T>                   void g(T);   // #1
template<class T> requires Int<T> void g(T);   // #2：与 #1 功能等价但不等价，IFNDR
template<Int T> requires true     void g(T);   // #3：与 #1 不等价，多了 requires 子句
```

`template<Int T>` 和 `template<class T> requires Int<T>` 是两种约束写法，接受的实参完全相同。但 ¶6 要求一边带 *type-constraint* 时另一边也带，所以它们不等价。

### 功能等价但不等价：IFNDR（¶7–¶8）

¶7 第一句：如果程序的合法性或含义取决于两个结构是否等价，而它们功能等价却不等价，程序{{ifndr}}。

第二句补上了一个漏洞。设两个函数模板声明 A、B：

- ¶7.1 引入同一个名字；
- ¶7.2 签名对应（[[basic.scope.scope]]）；
- ¶7.3 如果把它们看作对应，它们会声明同一个实体（[[basic.link]]）；
- ¶7.4 接受、并被同样的一组模板实参列表满足；

但由于 *template-head* 或尾随约束不等价，它们实际上并不对应。这样的程序也是 IFNDR。上面的 #1 和 #2 就是这种情况。实践中，Clang 按记号比较，把它们当成两个不同的模板，`g(1)` 报告调用歧义。

¶8 的注举了一组对照：

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

注 7 说明了设计意图：保证等价的声明一定链接到一起，同时不要求实现费力去保证功能等价的声明被当作不同的声明。

为什么不规定功能等价的声明就是同一个？因为判断两个任意表达式是否对所有实参结果相同，一般情况下是不可判定的。为什么不规定不等价的声明一定不同？因为那样编译器在生成修饰名时就必须保留源码的每个记号，包括冗余的括号，而不少实现会先把表达式规范化。标准用 IFNDR 把两种做法都纳入允许范围。

!!! impl "修饰名里的表达式"
    Itanium ABI 把签名中的依赖表达式按表达式树编码，所以 `A<I+10>` 和 `A<I+1+2+3+4>` 的修饰名不同，Clang 和 GCC 把它们当作两个模板。在同一个翻译单元里调用时，两者推导结果和参数都相同，于是报歧义；在不同翻译单元里分别声明和定义时，则表现为链接时找不到符号。这些都是 IFNDR 允许的结果。

```cpp ifndr
template<int> struct A { };
template<int I> void f(A<I>, A<I+10>);
template<int I> void f(A<I>, A<I+1+2+3+4>) { }
void t() { f(A<1>{}, A<11>{}); }   // Clang 23：调用歧义
```

## 历史与演进

!!! history
    - C++98 就有等价与功能等价的框架，当时针对的是 `A<I+J>` 这类常量表达式。
    - C++11 的 `decltype` 让任意表达式（包括函数调用）进入签名，依赖名只比较名字这条规则因此变得重要。
    - C++20 引入约束，¶6 随之扩展到 *type-constraint* 和 requires 子句，¶7 第二句处理约束写法不同的情形；lambda 可以出现在不求值操作数中，于是加上了 lambda 永不等价的规则。
    - C++26 增加了变量模板模板形参和概念模板形参，¶6.1 的形参种类随之扩展。

## 常见误解

!!! pitfall "声明一个同名同类型的非模板函数，编译器会用模板生成它的定义"
    不会（[temp.fct.general] ¶2）。它是另一个函数，被用到时必须自己有定义。

!!! pitfall "`template<C T>` 和 `template<class T> requires C<T>` 可以在声明和定义里混用"
    它们功能等价但不等价，混用是 IFNDR。Clang 把两者当作不同的模板，调用时报歧义。

!!! pitfall "`A<I+J>` 和 `A<J+I>` 是一样的"
    它们不等价。对整数加法它们功能等价，所以在两个声明里混用是 IFNDR。

!!! pitfall "两个函数类型相同的特化违反 ODR"
    不违反。它们是不同模板的特化，签名不同。

## 思考题

!!! question "思考题 1"
    下面哪些声明是同一个模板，哪些是不同的模板，哪些是 IFNDR？

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

- (a) 与 (b)：只是形参换了名，等价，是同一个模板。
- (a) 与 (c)：多了冗余括号。括号是记号，两个表达式不等价；但对所有 `N` 值相同，功能等价，所以是 IFNDR（注 6 正以冗余括号为例）。
- (a) 与 (d)：`N*2` 和 `2*N` 记号顺序不同，不等价；值相同，功能等价，IFNDR。
- (a) 与 (e)：不等价，`N = 1` 时值不同，也不功能等价，保证是两个不同的模板。
</details>

!!! question "思考题 2"
    有 `template<class T> void f(T) {}` 和 `void f(int) {}`。`&f<int>` 与 `static_cast<void(*)(int)>(&f)` 得到的指针相等吗？

<details markdown="1">
<summary>答案</summary>

不相等。`&f<int>` 指向模板特化。`static_cast<void(*)(int)>(&f)` 对重载集取地址（[[over.over]]），候选是非模板 `f(int)` 和推导出的 `f<int>`，非模板优先，结果指向非模板的 `f(int)`。两者是不同的函数（[temp.fct.general] ¶2）。本机 Clang 23 运行比较结果为 0。
</details>
