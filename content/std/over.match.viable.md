---
title: 可行函数
summary: 重载决议的第二步：从候选函数里筛掉根本不能用这组实参调用的函数，筛选只看实参个数、约束和隐式转换序列三件事。
status: done
related: over.match, over.match.funcs, over.match.best, over.best.ics, over.ics.ref, dcl.fct.default, temp.constr.constr
tags: 重载决议
updated: 2026-10-19
---

!!! tldr
    - 一个候选函数要成为可行函数，必须依次满足三条：形参个数对得上，关联约束得到满足，每个实参都能隐式转换到对应形参。
    - 可行性只回答能不能调用，不比较好坏。比较好坏是下一步 [[over.match.best]] 的事。
    - 访问权限、`= delete`、窄化、位域、explicit 都不影响可行性。带这些问题的函数照样参与比较，被选中之后才报错。
    - 声明里写了省略号不算劣势。`f(int)` 和 `f(int, ...)` 对 `f(1)` 有歧义。
    - C++26 精确规定了默认实参来自哪个声明：被选中的函数用到的默认实参必须来自唯一一个作用域。

重载决议分三步：先按调用的语境收集**候选函数**（candidate functions，[[over.match.funcs]]），再从中筛出**可行函数**（viable functions），最后在可行函数里挑出最佳的一个（[[over.match.best]]）。

```cpp run ok
#include <cstdio>
void f(int&)       { std::puts("f(int&)"); }
void f(const int&) { std::puts("f(const int&)"); }
int main() {
  int i = 0;
  f(i);   // 两个都可行，f(int&) 更好
  f(1);   // f(int&) 不可行：非 const 左值引用不能绑定到右值
}
```

第一个调用里两个候选都可行，由下一步比较决定。第二个调用里 `f(int&)` 在筛选可行函数时就被排除了，根本不参与比较。问为什么没选某个函数时，答案常常是它不可行。

¶1 筛选可行函数时，只看关联约束和实参与形参之间的关系，不看转换序列谁好谁坏。下面三节依次讲三条要求。

## 第一条：形参个数（¶2）

¶2 设调用有 `m` 个实参。候选函数要在个数上对得上，有三种情况：

- ¶2.1 恰好有 `m` 个形参：可行。
- ¶2.2 形参少于 `m` 个：只有形参列表带省略号 `...` 时才可行。多出来的实参都算作匹配省略号（[[over.ics.ellipsis]]）。
- ¶2.3 形参多于 `m` 个：多出来的形参都要有默认实参。C++26 对默认实参来自哪个声明有更精确的规定，详见下文。

```cpp run ok
#include <cstdio>
void f(int)      { std::puts("f(int)"); }
void f(int, ...) { std::puts("f(int, ...)"); }
void g(...)      { std::puts("g(...)"); }
int main() {
  f(1, 2);     // 只有 f(int, ...) 可行：实参 2 匹配省略号
  g();         // 纯省略号也接受 0 个实参
  g(1, "a");
}
```

那么 `f(1)` 呢？两个候选都可行，而且对实参 `1` 都是 `int` 到 `int` 的恒等转换。决胜规则里没有不带省略号者优先这一条，所以调用有歧义：

```cpp error
void f(int);
void f(int, ...);
void use() {
  f(1);      // error: 歧义
}
```

省略号只在某个实参真的匹配了它时才处于劣势，因为省略号转换序列排在所有转换序列的最后（[[over.ics.rank#2]]）。声明里有省略号本身不构成劣势。

## 第二条：约束（¶3）

¶3 如果候选函数有关联约束（[[temp.constr.decl]]），也就是 `requires` 子句或受约束的模板形参引入的条件，这些约束必须得到满足（[[temp.constr.constr]]）。

函数模板的约束在模板实参推导时就检查过了，不满足约束的特化根本不会成为候选（[[temp.deduct]]）。所以这一条主要作用于非模板函数上的约束，典型的是类模板里普通成员函数的尾随 `requires` 子句：

```cpp error
#include <concepts>
template<class T>
struct Wrapper {
  void reset() requires std::default_initializable<T>;
  void set(int) requires std::integral<T>;
  void set(double);
};
struct NoDefault { NoDefault(int); };
void use(Wrapper<int>& wi, Wrapper<NoDefault>& wn, Wrapper<double>& wd) {
  wi.set(1);    // OK：两个 set 都可行，set(int) 精确匹配
  wd.set(1);    // OK：set(int) 的约束不满足，不可行，选 set(double)
  wi.reset();   // OK
  wn.reset();   // error: 唯一的候选不可行
}
```

`wi.set(1)` 和 `wd.set(1)` 的候选集相同，可行集不同。约束表达的是能不能用，所以它属于可行性。更受约束者优先是另一条规则（[[over.match.best#2.6]]），只在两个候选都可行时才用得上。

## 第三条：每个实参都能转换（¶4）

¶4 对每个实参，都必须存在一个把它转换成对应形参类型的**隐式转换序列**（implicit conversion sequence，ICS，[[over.best.ics]]），也就是编译器为传参自动插入的那串转换。

形参是引用时，转换序列包括绑定引用这一步。非 const 左值引用不能绑定到右值、右值引用不能绑定到左值，这两条限制会让候选不可行（[[over.ics.ref#3]]）：

```cpp error
void f(int&);
void g(int&&);
void h(const int&);
void use(int i) {
  f(i);   // OK
  f(1);   // error: 唯一的候选不可行：右值不能绑定到 int&
  g(i);   // error: 唯一的候选不可行：左值不能绑定到 int&&
  g(1);   // OK
  h(i);   // OK
  h(1);   // OK：const 左值引用可以绑定到临时对象
}
```

这里每个函数只有一个候选，所以不可行就直接报错。有其他重载时，不可行的候选会被静默排除，调用改选别的函数。`T&`、`const T&`、`T&&` 三种重载能按值类别分派，靠的就是这一点。

## 可行性不看的东西

只要类型上能转换，候选就可行。下面这些与类型无关的性质不参与可行性判断，候选被选中之后才检查，出问题时程序非良构（[[over.best.ics#2]]、[[over.ics.ref#4]]）：

| 性质 | 例子 | 出错的位置 |
|---|---|---|
| 访问权限 | 选中了 `private` 成员函数 | 选定之后（[[over.match#3]]） |
| 被删除 | 选中了 `= delete` 的函数 | 选定之后（[[dcl.fct.def.delete]]） |
| 位域 | `int&` 形参，实参是 `int` 位域 | 选定之后，绑定引用时（[[dcl.init.ref]]） |
| 窄化 | `f({1.5})`，形参是 `int` | 选定之后（[[dcl.init.list]]） |
| 歧义的转换序列 | 一个实参到形参有两条用户定义转换路径 | 选定之后（[[over.best.ics#12]]） |

```cpp error
struct S { int bf : 4; };
void f(int&);
void f(long);
void use(S s) {
  f(s.bf);   // error: 选中 f(int&)，然后发现 int& 不能绑定到位域
}
```

计算转换序列时，`s.bf` 被当作普通的 `int` 左值，`f(int&)` 是精确匹配，胜过需要整型转换的 `f(long)`。被选中之后才发现非 const 引用不能绑定到位域。这种设计让与类型无关的性质不会静默地改变重载的结果。

拷贝列表初始化里的 explicit 构造函数也是一样：它照样参与 ICS 的构造，只有在它真的被用来完成初始化时才报错（[[over.match.list]] 注 1）。

```cpp
struct X { explicit X(int); };
struct Y { Y(int); };
void f(X);
void f(Y);
void use() {
  f({1});   // 按标准：f(X) 与 f(Y) 都可行，歧义
}
```

按标准，`{1}` 到 `X` 和到 `Y` 都有用户定义转换序列，两个候选无法区分。本机 Clang 23 没有把 explicit 构造函数算进来，接受了这个调用并选择 `f(Y)`。

## 默认实参来自哪里（¶2.3）{{c++26}}

同一个函数可以有多个声明，每个声明都可以添加默认实参。这些声明可能分布在不同的作用域里：命名空间里一个，某个函数体内又重新声明一个；或者两个命名空间各有一个 `extern "C"` 声明，它们是同一个函数，又被 *using-declaration* 一起引入。这时调用到底用哪一套默认实参？

块作用域里的重新声明是最常见的情形，它会隐藏外层的声明：

```cpp run ok
#include <cstdio>
void h(int x = 7) { std::printf("%d\n", x); }
void local() {
  void h(int = 8);   // 块作用域里重新声明，换了默认实参
  h();               // 打印 8：只看到块作用域里的声明
}
int main() { h(); local(); }
```

¶2.3 用**宿主作用域**（host scope，[[basic.scope.scope#2]]）来描述这种情况，大致就是声明所在的那个作用域。设候选函数 `C` 有多于 `m` 个形参，定义作用域集合 `G`，其中每个作用域 `X` 满足：

- ¶2.3.1 重载决议考虑的 `C` 的声明中，有一个的宿主作用域是 `X`；
- ¶2.3.2 对第 `m` 个之后的每个形参，都有一个宿主作用域为 `X` 的可达声明为它提供了默认实参。

`G` 非空，`C` 就在个数上可行。如果 `C` 最终被选中，还要满足：

- ¶2.3.3 `G` 恰好只有一个作用域，记作 `S`；
- ¶2.3.4 如果候选是通过 *splice-expression*（反射里的 `[: r :]`）得到的，`S` 不能是块作用域；
- ¶2.3.5 调用使用的默认实参，就是宿主作用域为 `S` 的那些可达声明提供的默认实参。

为了重载决议，形参列表从右边截断到恰好 `m` 个。

换句话说，判断可行时只问有没有某个作用域能凑齐所需的全部默认实参；真正选中时，这样的作用域必须唯一，否则无法决定用哪一套。

```cpp
namespace A {
  extern "C" void f(int, int = 5);
  extern "C" void f(int = 6, int);   // 同一作用域里逐步补上默认实参
}
namespace B {
  extern "C" void f(int, int = 7);   // 与 A::f 是同一个函数
}
void use() {
  using A::f;
  using B::f;
  f(3, 4);   // OK：没有用到默认实参
  f(3);      // error: A 和 B 都能提供第二个默认实参，G 有两个作用域
  f();       // OK：只有 A 能凑齐两个默认实参
}
```

形参包展开出来的形参没有默认实参：

```cpp error
template<typename... Ts>
int k(int = 3, Ts...);
int i = k<int>();   // error: 第二个形参（由包展开得到）没有默认实参
int j = k<>();      // OK：只有一个形参，它有默认实参
```

!!! impl "Clang 的偏离"
    本机 Clang 23 在 *using-declaration* 的例子上与标准相反：它接受 `f(3)`，却拒绝 `f()`，报告至少需要 1 个实参，没有把 `A` 中两个声明的默认实参合在一起看。块作用域和形参包的例子与标准一致。标准例子里用 *splice-expression* 的部分需要静态反射，本机 Clang 不能编译。

C++23 及以前，¶2.3 只说多出来的形参都要有默认实参，没有说用哪个声明的默认实参，多个作用域的情况由 [[dcl.fct.default]] 处理，措辞也不完整。C++26 引入反射后，`[:^^f:]()` 这样的调用不经过名字查找，没有调用点可见的声明这一说，于是必须明确规定用哪套默认实参。

## 常见误解

!!! pitfall "被删除、私有或会窄化的函数不可行"
    它们都可行，可能被选中，然后才报错。想在可行性阶段排除某个重载，要用约束（`requires`）或 SFINAE。

!!! pitfall "在不同作用域给同一个函数不同的默认实参"
    这是合法的，但哪套默认实参生效取决于调用点能看到哪些声明。按 C++26 的规则，两个作用域的默认实参同时可用时，调用非良构。

## 思考题

!!! question "思考题 1"
    下面的 `f(x)` 调用哪个函数？如果把 #2 换成 `void f(Base) = delete;` 呢？
    ```cpp
    struct Base {};
    struct Derived : Base {};
    void f(Base&);       // #1
    void f(Derived&&);   // #2
    Derived x;
    // f(x);
    ```

<details markdown="1">
<summary>答案</summary>

`x` 是左值，#2 的右值引用不能绑定到左值，#2 不可行。#1 可行（派生类左值绑定到基类引用），选中 #1。

换成 `void f(Base) = delete;` 之后，两个候选都可行。#1 是派生类到基类引用的绑定，按值的那个要用 `x` 拷贝初始化一个 `Base`，两者的转换序列都是派生到基类转换，等级相同（[[over.best.ics#6]]、[[over.ics.ref#1]]）。[[over.ics.rank]] 没有规则能区分这两种情况，调用有歧义。`= delete` 在这里没有机会起作用。本机 Clang 23 报告歧义。
</details>

!!! question "思考题 2"
    三条要求的先后顺序（个数、约束、转换序列）有什么实际意义？

<details markdown="1">
<summary>答案</summary>

就结论而言，三条都要满足，顺序无关紧要。但顺序决定了编译器要做哪些工作。计算转换序列可能需要实例化类模板（例如查找转换构造函数、判断派生关系），实例化又可能产生硬错误或在概念检查中造成循环依赖。先检查约束，不满足约束的候选在触发这些实例化之前就被排除了。函数模板的约束检查也出于同样的理由，放在了把推导结果代入函数形参类型之前（[[temp.deduct]]）。
</details>
