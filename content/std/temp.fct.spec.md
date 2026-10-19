---
title: 函数模板特化
summary: 调用或引用函数模板时，模板实参有三个来源：显式写出、从实参推导、取默认值；显式模板实参能写在哪里、哪些可以省略、空的 f<>() 有什么用，以及显式指定为什么能让实参做隐式转换。
status: done
covers: temp.fct.spec.general, temp.arg.explicit
related: temp.deduct, temp.deduct.call, temp.over, temp.names, temp.arg, temp.variadic, over.match.best, temp.expl.spec
tags: 模板, 函数模板, 显式模板实参
updated: 2026-10-19
---

!!! tldr
    - 函数模板的每个模板实参都要有值，来源有三个：显式写出（`f<int>(x)`）、从调用实参推导、取默认模板实参。三者可以混用。
    - 显式实参按模板形参的声明顺序填入，只有末尾那些能推导或有默认值的才能省略。所以需要显式指定的形参应该排在前面。
    - 显式指定的模板形参不再参与推导，对应的函数实参可以做普通的隐式转换：`max_(1, 2.5)` 推导冲突，`max_<double>(1, 2.5)` 可以编译。
    - 空的 `f<>(x)` 表示只考虑模板，把同名的非模板函数排除在外。
    - 构造函数模板没法写显式模板实参，它的模板实参只能推导或取默认值。

## 模板实参从哪里来（[temp.fct.spec.general]）

```cpp
template<class U, class V> U convert(V v);

int i = convert<int>(3.14);   // U 显式写出，V 从实参推导为 double
```

¶1 从函数模板实例化出来的函数叫[[g:function-template-specialization|**函数模板特化**]]（function template specialization），函数模板的显式特化（[[temp.expl.spec]]）也叫函数模板特化。确定一个特化需要知道它的全部模板实参，它们可以：

1. 在指名特化时显式写出，如上面的 `<int>`；
2. 从语境中推导，最常见的是从调用实参推导（[[temp.deduct]]）；
3. 取默认模板实参，如 `template<class T, class A = std::allocator<T>>` 里的 `A`。

`convert<int>(3.14)` 同时用了前两种。三者如何组合，见下文 ¶4 和 [[temp.deduct.general#5]]。

¶2 每个实例化出来的特化都有自己的一份静态变量：

```cpp run ok
template<class T> int counter(T*) {
    static int n = 0;
    return ++n;
}

int main() {
    int a; char* b;
    counter(&a); counter(&a);   // counter<int>：n == 2
    counter(&b);                // counter<char*>：n == 1
    return counter(&a) == 3 && counter(&b) == 2 ? 0 : 1;   // 返回 0
}
```

`counter<int>` 和 `counter<char*>` 是两个不同的函数，类模板的静态成员也是每个特化一份（[[temp.spec#7]]）。`f<int>` 和 `f<const int>` 的函数类型相同（形参的顶层 `const` 会被去掉），但它们仍是两个特化，各有一份静态变量（[[temp.deduct.general#4]]）。

## 显式写出模板实参（[temp.arg.explicit]）

### 什么时候必须写（¶1）

¶1 指名函数模板特化时，可以像类模板那样在名字后面写模板实参列表：

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

`sort` 的实参其实都能推导，写不写都行。`convert` 的 `U` 只出现在返回类型里，调用实参推不出来（[[temp.deduct.call#5]] 注 1），必须写。`std::make_unique<T>(args...)`、`std::get<I>(t)` 都属于这种情况。

### 能写在哪里（¶3）

¶3 函数模板特化的模板实参列表可以出现在这些地方：

- ¶3.1 调用函数时：`f<int>(x)`；
- ¶3.2 取函数地址、用函数初始化函数引用、形成成员函数指针时：`&f<int>`、`void (&r)(int) = f<int>;`、`&X::mf<int>`；
- ¶3.3 显式特化中：`template<> void f<int>(int);`；
- ¶3.4 显式实例化中：`template void f<int>(int);`；
- ¶3.5 友元声明中：`friend void f<int>(int);`。

!!! note "依赖语境中的 `template`"
    在模板里，如果 `.`、`->` 左边的对象或 `::` 左边的限定符依赖于模板形参，要加 `template` 关键字说明后面的 `<` 开始一个模板实参列表：`t.template get<0>()`、`T::template make<int>()`（[[temp.names]]）。

### 按顺序填，末尾的可以省（¶4、¶6）

¶6 写出的模板实参按对应模板形参的声明顺序排列。个数不能超过模板形参的个数，除非其中有模板形参包（[[temp.variadic]]）。

¶4 末尾那些能推导或有默认值的模板实参可以省略。注 1 补充，末尾的模板形参包如果没有从别处推导出来，就推导为空。全部模板实参都能这样得到时，可以一个都不写，此时连空的 `<>` 也可以省略。

```cpp ok
template<class X, class Y, class Z> X f(Y, Z);
template<class... Args> void f2();

void g() {
    f<int, const char*, double>("aa", 3.0);
    f<int, const char*>("aa", 3.0);    // Z 推导为 double
    f<int>("aa", 3.0);                 // Y、Z 都推导出来
    f2<char, short, int, long>();      // 四个都归入包 Args
}
```

```cpp error
template<class X, class Y, class Z> X f(Y, Z);
void g() { f("aa", 3.0); }             // error: X 无法推导
```

因此设计函数模板时，需要显式指定的形参放前面，能推导的放后面。`std::make_unique<T, Args...>` 就是这个顺序。反过来写成 `template<class Y, class X> X f(Y)`，用户就得写 `f<double, int>(5.6)`，连能推导的 `Y` 也要写出来。

标准例 2 里有一个更细的情形，实参本身是另一个函数模板的名字：

```cpp
template<class X, class Y> X f(Y);
template<class X, class Y, class... Z> X g(Y);

void h() {
    f<void>(f<int, bool>);     // OK：外层 f 的 Y 推导为 int(*)(bool)
    f<void>(f<int>);           // error: f<int> 不是唯一的特化
    f<void>(g<int, bool>);     // OK：g 的包 Z 推导为空
}
```

- `f<int>` 只确定了 `X`，`Y` 仍然未知，它代表无数个可能的特化，是一个重载集。从包含函数模板的重载集推导属于非推导语境（[[temp.deduct.call#6]]），外层的 `Y` 推不出来。
- `g<int, bool>` 中，末尾的包 `Z` 按注 1 推导为空，所以它指称唯一的特化 `int g<int, bool>(bool)`，外层能够推导。

### `f<>(x)`：只考虑模板（¶5）

```cpp run ok
#include <cstdio>
template <class T> int f(T) { return 1; }   // #1
int f(int) { return 2; }                    // #2

int main() {
    std::printf("%d %d\n", f(1), f<>(1));   // 输出 2 1
}
```

¶5 注 2 指出，空的模板实参列表可以用来表示这里要的是函数模板的特化，即使有一个本来会被选中的非模板函数可见。`f(1)` 的两个候选同样好，[[over.match.best]] ¶2.4 让非模板函数胜出；`f<>(1)` 写了模板实参列表，非模板函数根本不是候选。

### 显式指定的形参允许隐式转换（¶7）

<div class="compare" markdown="1">

```cpp error
template<class T>
T max_(T a, T b) { return a < b ? b : a; }

// T 推导为 int 和 double，冲突
double m = max_(1, 2.5);    // error
```

```cpp ok
template<class T>
T max_(T a, T b) { return a < b ? b : a; }

// T 不再推导，1 转换为 double
double m = max_<double>(1, 2.5);
```

</div>

推导时，实参类型和形参类型之间只允许极少几种差异（[[temp.deduct.call#4]]），`int` 到 `double` 这样的转换不在其中。

¶7 规定，如果一个函数形参的类型里没有参与推导的模板形参，那么对应的实参会做普通的隐式转换（[[conv]]）。注 3 说明，显式指定的模板形参不参与推导。所以写了 `max_<double>` 之后，它就是一个普通的 `double max_(double, double)`，实参照常转换。转换也可以是用户定义的：

```cpp ok
template<class T> void f(T);
class Complex { public: Complex(double); };

void g() {
    f<Complex>(1);    // OK：相当于 f<Complex>(Complex(1))
}
```

C++20 起也可以用 `std::type_identity_t<T>` 把某个形参放进非推导语境，只从其余形参推导 `T`，让这个形参允许转换（见 [[temp.deduct.type]]）。

### 推导可以接着填充包（¶9）

```cpp ok
#include <type_traits>
template<class... Types> void f(Types... values) {
    static_assert(std::is_same_v<void(Types...), void(int*, float*, int)>);
    (void)sizeof...(values);
}

void g() {
    f<int*, float*>(0, 0, 0);   // Types 为 int*, float*, int
}
```

¶9 即使模板形参包已经有了显式指定的实参，推导仍然可以在后面继续添加。上例中前两个 `0` 对应显式写出的 `int*`、`float*`，作为空指针常量转换过去；第三个 `0` 超出了显式部分，由推导补上 `int`。显式写出包的几个元素，只是固定了它的前缀。

如果包不在末尾，显式实参会依次全部归入这个包，后面的形参只能靠推导：

```cpp ok
#include <type_traits>
template<class... Ts, class U> void f(U) {
    static_assert(sizeof...(Ts) == 2);
    static_assert(std::is_same_v<U, double>);
}
void g() { f<int, char>(1.0); }   // Ts = {int, char}，U 从实参推导
```

### 构造函数模板不能显式指定（¶2、¶8）

¶2 指名构造函数模板的特化时不能写模板实参。¶8 注 4 解释了原因：显式模板实参列表要跟在函数模板的名字后面，而构造函数没有可以这样写的名字（`X::X` 指名的是类，[[class.qual]]）。

```cpp
struct S { template<class T> S(T); };
S s = S<int>(1);    // error: S 不是模板，这里不是在给构造函数指定 T
```

所以构造函数模板的模板实参只能推导或取默认值。需要由调用者指定类型时，惯用做法是加一个标签形参，例如 `std::in_place_type_t<T>`：

```cpp ok
#include <utility>
struct Any {
    template<class T, class... Args>
    explicit Any(std::in_place_type_t<T>, Args&&...) { }
};
Any a(std::in_place_type<int>, 42);   // T 由标签的类型推导为 int
```

## 常见误解

!!! pitfall "对转发引用写 `g<int>(i)`"
    转发引用的特殊规则（左值实参让 `T` 推导为左值引用）只在推导时生效。对 `template<class T> void g(T&&)` 写 `g<int>(i)`，`T` 被固定为 `int`，形参是 `int&&`，不能绑定左值 `i`，调用失败。`std::forward<T>(x)` 反过来利用了这一点：它的形参是非推导语境，强制调用者写出 `T`。

!!! pitfall "显式实参不合法时会报硬错误"
    不会。显式实参先代入函数类型（[[temp.deduct.general#2]]），得到无效类型时只是推导失败，这个模板被安静地剔除。对 `template<class T> void f(typename T::type)` 写 `f<int>(0)`，如果没有别的候选，报的是没有匹配的函数，而不是 `int` 没有成员 `type`。

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

只有 (b) 良构。(a)：`T` 从第一个实参推导为 `int`，从第二个推导为 `long`，冲突。(b)：`T` 显式指定为 `long`，不参与推导，`1` 隐式转换为 `long`（¶7）。(c)：`<>` 没有指定任何实参，`T` 仍需推导，与 (a) 相同。本机 Clang 23 的结果与此一致。
</details>

!!! question "思考题 2"
    为什么 `std::make_shared<int>(42)` 能编译，`std::make_shared(42)` 不能？如果把它声明成 `template<class... Args, class T> shared_ptr<T> make_shared(Args&&...)` 会怎样？

<details markdown="1">
<summary>答案</summary>

`make_shared` 声明为 `template<class T, class... Args> shared_ptr<T> make_shared(Args&&... args);`。`T` 只出现在返回类型里，推导不出来，所以 `make_shared(42)` 失败；`make_shared<int>(42)` 中 `T = int`，`Args` 推导为 `int`。

如果把包放在前面，显式写出的 `int` 会归入 `Args`（¶6、¶9），`T` 既推不出来也没有办法写出来，这个函数模板就无法调用，除非 `T` 有默认值。这就是需要显式指定的形参应该放前面的原因。
</details>
