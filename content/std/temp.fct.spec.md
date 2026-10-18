---
title: 函数模板特化
summary: 函数模板特化的模板实参从三处来：显式指定、推导、默认模板实参。本页讲第 13.10 节的总述与显式指定模板实参：哪些地方可以写 f<...>、尾随实参可省略、空的 f<>() 强制选模板、显式指定的形参不参与推导因而允许隐式转换、包可以被推导"续长"，以及构造函数模板为什么无法显式指定实参。
status: done
covers: temp.fct.spec.general, temp.arg.explicit
related: temp.deduct, temp.over, temp.names, temp.arg, temp.variadic, over.match.best, temp.expl.spec
tags: 模板, 函数模板, 显式模板实参
updated: 2026-10-18
---

第 13.10 节 [[temp.fct.spec]] 是函数模板的"使用说明书"：给定一个函数模板 `f` 和一次对它的引用（调用、取地址、显式实例化……），如何确定**所有**模板实参，从而确定是哪个特化。它包含四个子条款：

| 子条款 | 内容 | 本站页面 |
|---|---|---|
| [[temp.fct.spec.general]] | 总述 | 本页 |
| [[temp.arg.explicit]] | 显式指定模板实参 | 本页 |
| [[temp.deduct]] | 模板实参推导（SFINAE、从调用/类型/声明推导……） | [[temp.deduct]]、[[temp.deduct.call]]、[[temp.deduct.type]] |
| [[temp.over]] | 函数模板与重载决议 | [[temp.over]] |

## 总述（[temp.fct.spec.general]）

### 函数模板特化与它的三种实参来源（¶1）

¶1 从函数模板实例化出来的函数叫[[g:function-template-specialization|**函数模板特化**]]（function template specialization）；函数模板的显式特化也叫函数模板特化。模板实参可以：

1. 在指名特化时**显式指定**（`f<int>(x)`）；
2. 从语境中**推导**（例如从函数调用的实参推导，[[temp.deduct]]）；
3. 从**默认模板实参**取得（`template<class T, class A = std::allocator<T>>`）。

三者可以混合：前面几个显式指定，中间一些推导，剩下的用默认值。具体的组合规则见下文 ¶4 和 [[temp.deduct.general#5]]。

### 每个特化一份静态变量（¶2）

¶2 每个从模板实例化出来的函数模板特化都有自己的一份静态变量：

```cpp run ok
template<class T> int counter(T*) {
    static int n = 0;
    return ++n;
}

int main() {
    int a; char* b;
    counter(&a); counter(&a);   // counter<int>：n == 2
    counter(&b);                // counter<char*>：n == 1（各自独立）
    return counter(&a) == 3 && counter(&b) == 2 ? 0 : 1;
}
```

这和 [[temp.spec#7]]（类模板的静态成员每特化一份）是同一原理：`counter<int>` 和 `counter<char*>` 是两个不同的函数。但要注意：`f<int>` 与 `f<const int>` 尽管函数类型相同（顶层 const 被调整掉），也是**不同的特化**，各有一份静态变量（[[temp.deduct.general#4]]）。

## 显式指定模板实参（[temp.arg.explicit]）

### 语法（¶1–¶2）

¶1 指名一个（不是构造函数模板特化的）函数模板特化时，可以像指名类模板特化那样，在函数模板名后加模板实参列表：

```cpp ok
template<class T> struct Array { };
template<class T> void sort(Array<T>& v);
template<class U, class V> U convert(V v);

void f(Array<double>& cv, Array<int>& ci, double d) {
    sort<double>(cv);                  // sort(Array<double>&)
    sort<int>(ci);                     // sort(Array<int>&)
    int  i = convert<int, double>(d);  // int convert(double)
    char c = convert<char, double>(d); // char convert(double)
    (void)i; (void)c;
}
```

`convert` 的返回类型 `U` 不出现在形参中，无法推导（[[temp.deduct.call]] ¶5 注 1），必须显式指定——这是显式模板实参最典型的用途，也是 `std::make_unique<T>(args...)`、`std::get<I>(t)`、`static_cast` 风格的工厂函数的写法。

¶2 指名**构造函数模板**的特化时**不能**指定模板实参。¶8（注 4）解释了原因：显式模板实参列表跟在函数模板**名**后面，而构造函数没有名字（`X::X` 指名的是类，[[class.qual]]），没有地方可以写 `<...>`。

```cpp
struct S { template<class T> S(T); };
S s = S<int>(1);    // error: S 不是模板；这不是在给构造函数模板指定实参
```

构造函数模板的所有模板实参都必须能**推导**出来（或有默认值）。需要"显式指定"时的惯用法是加一个标签形参，如 `std::in_place_type_t<T>`：

```cpp ok
#include <utility>
struct Any {
    template<class T, class... Args>
    explicit Any(std::in_place_type_t<T>, Args&&...) { }
};
Any a(std::in_place_type<int>, 42);   // T 通过标签"显式"给出
```

### 哪些地方可以写模板实参列表（¶3）

¶3 函数模板特化的模板实参列表可以在以下场合给出：

- ¶3.1 调用函数时：`f<int>(x)`；
- ¶3.2 取函数地址、用函数初始化函数引用、形成成员函数指针时：`&f<int>`、`void (&r)(int) = f<int>;`、`&X::mf<int>`；
- ¶3.3 显式特化中：`template<> void f<int>(int);`；
- ¶3.4 显式实例化中：`template void f<int>(int);`；
- ¶3.5 友元声明中：`friend void f<>(T);`、`friend void f<int>(int);`。

!!! note "依赖语境中别忘了 `template`"
    在模板中，如果对象表达式或限定符是依赖的，要用 `template` 关键字告诉解析器 `<` 是模板实参列表的开头：`t.template get<0>()`、`T::template make<int>()`（[[temp.names]]）。

### 尾随实参可省略；空列表 `<>`（¶4–¶5）

¶4 可以从推导或默认模板实参得到的**尾随**模板实参，可以从显式列表中省略。注 1：一个**尾随**的模板形参包若没有被别的方式推导，会被推导为**空序列**。如果所有模板实参都能推导或有默认值，它们可以全部省略；此时空的模板实参列表 `<>` 本身也可以省略。

```cpp
template<class X, class Y> X f(Y);
template<class X, class Y, class... Z> X g(Y);

void h() {
    int i = f<int>(5.6);       // Y 推导为 double
    int j = f(5.6);            // error: X 无法推导
    f<void>(f<int, bool>);     // 外层 f 的 Y 推导为 int(*)(bool)
    f<void>(f<int>);           // error: f<int> 不指称单一的函数模板特化
    int k = g<int>(5.6);       // Y 推导为 double；Z 推导为空序列
    f<void>(g<int, bool>);     // 外层 f 的 Y 推导为 int(*)(bool)，内层 g 的 Z 为空
}
```

逐个分析两个错误：

- `f(5.6)`：`X` 只出现在返回类型里，调用实参无法推导它；它也没有默认值。
- `f<void>(f<int>)`：实参 `f<int>` 只固定了 `X = int`，`Y` 仍然未知——它是一个**重载集**（理论上有无穷多个 `f<int, Y>`）。外层 `f<void>` 的形参类型是 `Y`（外层的），从一个含函数模板的重载集推导是**非推导语境**（[[temp.deduct.call#6]]），于是外层 `Y` 也推不出来。
- 对比 `f<void>(g<int, bool>)`：`g<int, bool>` 中 `Z` 是尾随包，按注 1 推导为空，于是 `g<int, bool>` 指称唯一的特化 `int g<int, bool>(bool)`，外层能推导。

¶5（注 2）：空模板实参列表可以用来表示"这里指的是函数模板的特化"，即使有一个本会被选中的**非模板**函数可见：

```cpp run ok title="empty_angle.cpp"
#include <cstdio>
template <class T> int f(T) { return 1; }   // #1
int f(int) { return 2; }                    // #2

int main() {
    std::printf("%d %d\n", f(1), f<>(1));   // 2 1
}
```

`f(1)` 两个候选同等好，[[over.match.best]] ¶2.4 让非模板函数胜出；`f<>(1)` 写了模板实参列表，只有模板能匹配一个 *template-id*，非模板函数直接被排除在候选之外。

### 顺序与个数（¶6）

¶6 给出的模板实参必须按其对应模板形参的**声明顺序**；模板实参的个数不能超过模板形参的个数，除非其中有模板形参包。

```cpp ok
template<class X, class Y, class Z> X f(Y, Z);
template<class... Args> void f2();

void g() {
    f<int, const char*, double>("aa", 3.0);
    f<int, const char*>("aa", 3.0);    // Z 推导为 double
    f<int>("aa", 3.0);                 // Y 推导为 const char*，Z 推导为 double
    f2<char, short, int, long>();      // OK：全部归入包
}
```

```cpp error
template<class X, class Y, class Z> X f(Y, Z);
void g() { f("aa", 3.0); }             // error: X 无法推导
```

所以设计函数模板时，**需要显式指定的形参放在前面**，可以推导的放后面。`std::make_unique<T, Args...>`、`std::get<I, Types...>` 都遵循这个顺序。反过来写（`template<class Y, class X> X f(Y)`）就迫使用户写 `f<double, int>(5.6)`，连可推导的也得写出来。

### 显式指定的形参不参与推导 → 允许隐式转换（¶7）

¶7 如果函数形参的类型**不含参与推导的模板形参**，那么函数实参会做隐式转换（[[conv]]）以转为形参类型。

注 3 把关键点说出来了：**显式指定的模板形参不参与模板实参推导**。所以：

```cpp ok
template<class T> void f(T);
class Complex { public: Complex(double); };

void g() {
    f<Complex>(1);    // OK：意为 f<Complex>(Complex(1))
}
```

如果让 `T` 被推导，`f(1)` 会推导出 `T = int`；显式指定后形参就是"固定类型 `Complex`"，实参走完整的隐式转换（这里是用户定义转换）。

这条规则的经典应用：

```cpp
template<class T> T max_(T a, T b) { return a < b ? b : a; }
int    m1 = max_(1, 2.5);           // error: T 被推导为 int 和 double，冲突
double m2 = max_<double>(1, 2.5);   // OK：T 不参与推导，1 转换为 double
```

推导时，实参与形参之间只允许极少数的调整（[[temp.deduct.call#4]]）——不允许 `int` → `double` 这样的转换。显式指定之后，推导这一步对 `T` 就不发生了，`max_<double>` 成了一个普通的 `double max_(double, double)`，重载决议照常进行。C++20 起也可以用 `std::type_identity_t<T>` 让某个形参成为非推导语境，达到"只从一个实参推导，另一个允许转换"的效果（见 [[temp.deduct.type]]）。

### 推导可以"续长"包（¶9）

¶9 模板实参推导可以**延长**模板形参包对应的实参序列，即使该序列已含显式指定的实参：

```cpp ok
#include <type_traits>
template<class... Types> void f(Types... values) {
    static_assert(std::is_same_v<void(Types...), void(int*, float*, int)>);
    (void)sizeof...(values);
}

void g() {
    f<int*, float*>(0, 0, 0);   // Types 推导为 int*, float*, int
}
```

前两个 `0` 对应显式指定的 `int*`、`float*`（空指针常量转换），第三个 `0` 超出了显式部分，推导补上 `int`。换句话说，显式指定一个包的若干元素，只是固定了**前缀**，包并没有因此"封口"。

如果包不是尾随的，显式实参会按顺序填满它，后面的形参只能靠推导：

```cpp ok
#include <type_traits>
template<class... Ts, class U> void f(U) {
    static_assert(sizeof...(Ts) == 2);
    static_assert(std::is_same_v<U, double>);
}
void g() { f<int, char>(1.0); }   // Ts = {int, char}（显式），U 从实参推导
```

这里显式实参全部被 `Ts` "吞掉"，`U` 只能推导。这种形参顺序在实践中很少见，但能编译。

## 陷阱

!!! pitfall "`f<T>(x)` 关掉了推导，也关掉了引用折叠的“自动”"
    `std::forward<T>(x)` 必须显式写 `T`，因为 `forward` 的形参是 `std::remove_reference_t<T>&`——非推导语境，故意不让推导。反过来，对一个 `template<class T> void g(T&&)` 写 `g<int>(i)`（`i` 是左值）会失败：`T` 被固定为 `int`，形参是 `int&&`，不能绑定左值。转发引用的特殊推导规则只在**推导**时生效。

!!! pitfall "显式实参也会被替换，失败照样是 SFINAE"
    显式指定的实参首先被代入函数类型（[[temp.deduct.general#2]]），若得到无效类型，推导失败，模板被静默剔除。`f<int>(0)` 对 `template<class T> void f(typename T::type)` 不是硬错误，而是"没有匹配的函数"——如果没有别的候选，报错信息会是"no matching function"，而不是"int 没有成员 type"。

## 思考题

!!! question "思考题 1"
    ```cpp
    template<class T> void f(T, T);
    void g(long l) {
        f(1, l);         // (a)
        f<long>(1, l);   // (b)
        f<>(1, l);       // (c)
    }
    ```
    哪些良构？

<details markdown="1">
<summary>答案</summary>

(a) 非良构：`T` 从第一个实参推导为 `int`，从第二个推导为 `long`，冲突。(b) 良构：`T` 显式指定为 `long`，不参与推导，`1` 隐式转换为 `long`。(c) 非良构：`<>` 不指定任何实参，`T` 仍需推导，与 (a) 相同。
</details>

!!! question "思考题 2"
    为什么 `std::make_shared<int>(42)` 能工作，而 `std::make_shared(42)` 不行？如果把 `make_shared` 声明为 `template<class... Args, class T> shared_ptr<T> make_shared(Args&&...)`，会怎样？

<details markdown="1">
<summary>答案</summary>

`make_shared` 的声明是 `template<class T, class... Args> shared_ptr<T> make_shared(Args&&... args);`。`T` 只出现在返回类型中，无法推导，必须显式指定，所以 `make_shared(42)` 失败；`make_shared<int>(42)` 中 `T = int`，`Args` 推导为 `int`。

如果把包放在前面，`make_shared<int>(42)` 的显式实参 `int` 会进入 `Args`（显式实参按顺序填形参，包会吞掉所有显式实参，¶6/¶9），`T` 无法推导也无法指定——这个函数模板就无法调用（除非 `T` 有默认值）。这就是"需显式指定的形参放前面"原则的反例。
</details>

## 小结

| 规则 | 出处 | 要点 |
|---|---|---|
| 模板实参三来源：显式、推导、默认 | general ¶1 | 可混合 |
| 每个特化一份静态变量 | general ¶2 | `f<int>` 与 `f<const int>` 也不同 |
| 构造函数模板不能显式指定实参 | ¶2, ¶8 | 用 `in_place_type_t` 之类的标签 |
| 可写 `f<...>` 的场合：调用、取址、特化、实例化、友元 | ¶3 | — |
| 尾随的可推导/有默认值的实参可省；尾随包默认为空 | ¶4 | `<>` 也可省 |
| `f<>(x)` 排除非模板函数 | ¶5 | — |
| 显式实参按形参声明顺序；不超过形参个数（除非有包） | ¶6 | 需指定的形参放前面 |
| 不参与推导的形参允许完整的隐式转换 | ¶7 | `max_<double>(1, 2.5)` |
| 推导可以延长已部分显式指定的包 | ¶9 | — |
