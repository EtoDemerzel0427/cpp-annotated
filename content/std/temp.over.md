---
title: 重载决议（函数模板）
summary: 函数模板怎样参加重载决议：每次调用对每个模板做推导，成功就合成一个特化的声明放进候选集，失败就不放，这是 SFINAE 不报错的来源；之后先比较转换序列，同等好时非模板优先，再看哪个模板更特殊。
status: done
covers: temp.over
related: temp.deduct, temp.deduct.call, temp.arg.explicit, temp.func.order, over.match, over.match.best, over.match.funcs, topics/overload-resolution-walkthrough
tags: 模板, 重载决议, SFINAE
updated: 2026-10-19
---

!!! tldr
    - 每次调用时，对每个函数模板做模板实参推导；成功就合成一个具体特化的声明，当作普通函数放进候选集。
    - 推导失败或合成的声明非良构时，这个模板不贡献候选，也不报错。SFINAE 不算错误，出处就在这里。
    - 参与推导的实参只允许少数几种转换；不参与推导的形参照常允许任何隐式转换。
    - 比较候选时先比转换序列；只有转换序列不分高下时，才轮到非模板优先、更特殊的模板优先。
    - 只合成声明，不实例化函数体，所以只有模板声明没有定义也能完成重载决议。

## 推导失败的模板不参加（¶1–¶2）

```cpp error
template<class T> T max(T a, T b) { return a > b ? a : b; }

void f(int a, int b, char c, char d) {
    int m1 = max(a, b);     // max<int>
    char m2 = max(c, d);    // max<char>
    int m3 = max(a, c);     // error: 无法生成 max(int, char)
}
```

`max(a, c)` 从第一个实参推出 `T = int`，从第二个推出 `T = char`，两者冲突，推导失败。模板不贡献候选，候选集是空的，于是报错。加一个非模板函数就能接住这次调用：

```cpp ok
template<class T> T max(T a, T b) { return a > b ? a : b; }
int max(int, int);

void f(int a, int b, char c, char d) {
    int m1 = max(a, b);     // max<int> 与 max(int,int) 同等好，非模板优先
    char m2 = max(c, d);    // max<char> 精确匹配，胜过要提升的 max(int,int)
    int m3 = max(a, c);     // 只有 max(int,int)：c 提升为 int
    (void)m1; (void)m2; (void)m3;
}
```

¶1 写出一个函数调用（包括用运算符写法隐式调用）时，对每个函数模板执行模板实参推导（[[temp.deduct]]）并检查显式给出的模板实参（[[temp.arg]]），目标是找到一组模板实参，使实例化出的特化能用这些实参调用。对转换函数模板，目标是能转换到所需的类型。然后：

- ¶1.1 推导和检查成功，就用得到的模板实参合成一个特化的声明，加入候选集；
- ¶1.2 推导失败，或合成的特化会是非良构的，这个模板不向候选集加入任何函数。

候选集由所有合成的声明和名字查找找到的所有非模板函数组成。此后合成的声明和其他函数一样参与重载决议，只在 [[over.match.best]] 明确说明的地方有区别。

!!! std
    If the argument deduction fails or the synthesized function template specialization would be ill-formed, no such function is added to the set of candidate functions for that template.

[[temp.deduct.general#8]] 规定代入失败导致推导失败，¶1.2 规定推导失败的模板不加入候选，两者合起来就是 SFINAE（substitution failure is not an error，代入失败不是错误）：失败的模板悄悄消失。只有当所有候选都消失或都不可行时，才报告没有匹配的函数。

¶1 只合成声明。函数体要等这个特化被选中并被使用时才实例化（[[temp.inst#11]]），所以函数体里的错误不属于 SFINAE：

<div class="compare" markdown="1">

```cpp error
template<class T>
auto size_of(const T& c) {
  return c.size();
}
int size_of(...);
int n = size_of(42);
// error: 选中模板后实例化函数体，
// int 没有 size()
```

```cpp ok
template<class T>
auto size_of(const T& c)
    -> decltype(c.size()) {
  return c.size();
}
int size_of(...);
int n = size_of(42);
// OK: 推导失败，选 size_of(...)
```

</div>

左边的模板签名没有问题，推导成功，而且它比省略号版本更好，于是被选中；随后实例化函数体，`c.size()` 出错，这是硬错误。右边把 `c.size()` 写进了签名，代入时就失败，模板退出候选集。

## 推导中允许的转换（¶3–¶4）

参与推导的实参只允许 [[temp.deduct.call#4]] 列出的几种转换，例如派生类到基类：

```cpp ok
template<class T> struct B { };
template<class T> struct D : public B<T> { };
template<class T> void f(B<T>&) { }

void g(B<int>& bi, D<int>& di) {
    f(bi);    // T = int
    f(di);    // T = int，D<int>& 转换为 B<int>&
}
```

形参里不含模板形参的部分不参与推导，实参可以做任何隐式转换：

```cpp run ok title="nondeduced_conv.cpp"
#include <cstdio>
template<class T> void f(T*, int)  { std::puts("#1"); }
template<class T> void f(T, char)  { std::puts("#2"); }

int main() {
    int* pi = nullptr; int i = 0; char c = 0;
    f(pi, i);   // #1: f<int>(pi, i)
    f(pi, c);   // #2: f<int*>(pi, c)
    f(i, c);    // #2: f<int>(i, c)
    f(i, i);    // #2: f<int>(i, char(i))
}
```

- `f(pi, i)`：#1 两个实参都精确匹配；#2 是 `f<int*>(int*, char)`，第二个实参要从 `int` 转换到 `char`。#1 胜。
- `f(pi, c)`：#1 的第二个实参要提升；#2 都是精确匹配。#2 胜。
- `f(i, c)` 和 `f(i, i)`：#1 推导失败（`T*` 匹配不了 `int`），只剩 #2。`f(i, i)` 中第二个形参 `char` 不参与推导，`int` 到 `char` 的转换照样允许。

¶1 的脚注解释了这种设计：推导产生的特化，形参要么和实参精确匹配，要么只差那几种有限的转换；非推导的形参则允许全部转换。

## 同等好时怎样决胜

合成的候选进入 [[over.match.best]] 后，先和其他候选一样比较隐式转换序列。转换序列分不出高下时，才依次使用：

1. ¶2.4：非模板函数优于函数模板特化；
2. ¶2.5：两个都是模板特化时，按偏序（[[temp.func.order]]）更特殊的模板胜出；
3. 之后还有按约束比较等规则。

顺序是关键：一个精确匹配的模板特化，胜过需要转换的非模板函数。

```cpp run ok title="template_vs_nontemplate.cpp"
#include <cstdio>
template<class T> void g(T) { std::puts("template"); }
void g(int)                 { std::puts("non-template int"); }
void g(long)                { std::puts("non-template long"); }

int main() {
    g(1);      // non-template int：与 g<int> 同等好，非模板优先
    g('a');    // template：g<char> 精确匹配，胜过要提升的 g(int)
    g(1L);     // non-template long
    g(1u);     // template：g<unsigned> 精确匹配，两个非模板都要转换
}
```

一个常见的意外是给字符串写了重载，调用时却进了模板：

```cpp run ok title="string_overload.cpp"
#include <cstdio>
#include <string>
void show(const std::string&) { std::puts("string"); }
template<class T> void show(const T&) { std::puts("template"); }

int main() {
    show("hi");               // template：T = char[3]，精确匹配；string 版本要用户定义转换
    show(std::string("hi"));  // string：同等好，非模板优先
}
```

字符串字面量不是 `std::string`。修正办法是加一个 `show(const char*)` 重载，或者约束模板。

## 只需要声明（¶5）

```cpp
template<class T> void f(T);    // 只有声明

void g() {
    f("Annemarie");             // 调用 f<const char*>
}
```

¶5 把特化放进候选集只需要它的签名，所以调用点只需看到模板的声明。这次调用是良构的；但程序还要求某个翻译单元显式实例化 `f<const char*>`（[[temp.explicit]]），否则非良构（[[temp.pre]]）。把模板定义放在 `.cpp` 里、再显式实例化需要的特化，依据就在这里。

Clang 和 GCC 在 no matching function 错误下，会把被 ¶1.2 剔除的每个模板列成附注并说明原因，例如 candidate template ignored: deduced conflicting types for parameter 'T'。调试 SFINAE 时这是最有用的信息。

## 常见误解

!!! pitfall "完美转发构造函数抢走了拷贝"
    ```cpp
    struct Person {
        template<class S> Person(S&& name);   // 转发构造
        Person(const Person&);                // 拷贝构造
    };
    Person p("x");
    Person q(p);    // 调用的是模板
    ```
    `p` 是非 const 左值，模板推出 `Person(Person&)`，精确匹配；拷贝构造函数要加 `const`。转换序列已经分出高下，非模板优先的规则用不上。需要用约束排除 `Person` 本身：`requires (!std::is_same_v<std::remove_cvref_t<S>, Person>)`。

!!! pitfall "以为有非模板函数就一定选它"
    非模板优先只是转换序列不分高下时的决胜规则，见上面的 `g('a')`。

## 思考题

!!! question "思考题 1"
    ```cpp
    template<class T> void f(T, T);
    void f(double, double);
    f(1, 2.0);
    f(1, 2);
    ```
    两次调用分别选哪个？

<details markdown="1">
<summary>答案</summary>

`f(1, 2.0)`：模板推导时 `T` 冲突（`int` 与 `double`），不贡献候选；非模板 `f(double, double)` 可行。调用非模板。

`f(1, 2)`：模板合成 `f<int>(int, int)`，精确匹配；非模板要两次 `int` 到 `double` 的转换。调用 `f<int>`。
</details>

!!! question "思考题 2"
    ¶1.2 为什么在推导失败之外，还要写合成的特化会是非良构的？

<details markdown="1">
<summary>答案</summary>

推导（[[temp.deduct]]）本身已经把代入后类型无效算作推导失败。第二个条件覆盖推导之外的检查，例如显式模板实参与模板形参的种类不符或个数过多（[[temp.arg]]）。这句话保证，凡是在形成候选声明这一步出问题的模板，都只是被丢弃，不会让整个调用非良构。
</details>
