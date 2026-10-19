---
title: 重载决议（函数模板）
summary: 函数模板如何进入重载决议：对每个模板做推导与显式实参检查，成功则合成一个特化声明加入候选集，失败则静默不加入（SFINAE 之所以不报错，正源于此）；合成的候选只容忍推导允许的那点差异，非推导形参可做全部转换；同等好时非模板优先、再比谁更特殊；只需模板声明即可决议。
status: done
covers: temp.over
related: temp.deduct, temp.deduct.call, temp.arg.explicit, temp.func.order, over.match, over.match.best, over.match.funcs, topics/overload-resolution-walkthrough
tags: 模板, 重载决议, SFINAE
updated: 2026-10-18
---

普通函数的重载决议（[[over.match]]）面对的是一组签名已知的候选。函数模板没有固定签名，`template<class T> T max(T, T)` 可以是 `int max(int, int)`，也可以是 `std::string max(std::string, std::string)`。第 13.10.4 节 [[temp.over]] 规定了把模板转化为普通候选的方法：**每次调用时，为每个模板推导出一个具体特化的声明，把它当作普通函数放进候选集**。

这一节很短，但 SFINAE 之所以不算错误，真正的出处就在这里；它也解释了为什么模板与非模板混合重载时常常出人意料。完整的重载决议流程见 [[topics/overload-resolution-walkthrough]]。

## 候选集如何构成（¶1）

¶1 写出对函数或函数模板的调用（显式地，或通过运算符记法隐式地）时，对每个函数模板执行模板实参推导（[[temp.deduct]]）和显式模板实参的检查（[[temp.arg]]），以找到合适的模板实参值，使实例化出的函数模板特化能用这些调用实参调用（对转换函数模板，则是能转换到所需类型）。对每个函数模板：

- ¶1.1 若推导和检查成功，用得到的模板实参（推导的和/或显式的）合成一个函数模板特化的声明，加入候选函数集，参与重载决议。
- ¶1.2 若推导失败，或合成的特化会是非良构的，就不为这个模板向候选集加入任何函数。

完整的候选集由所有合成的声明和名字查找找到的所有非模板函数组成。此后，合成的声明与其他函数一样参与重载决议，只有 [[over.match.best]] 中明确提到的地方例外。

!!! std
    If the argument deduction fails or the synthesized function template specialization would be ill-formed, no such function is added to the set of candidate functions for that template.

    推导失败或合成的特化非良构时，该模板不向候选集添加函数。

SFINAE 中不算错误的那一半就来自这句话：[[temp.deduct.general#8]] 说代入失败导致推导失败，本节说推导失败的模板不添加候选，两者合起来，**失败的模板就悄无声息地消失了**。只有当所有候选都消失（或剩下的都不可行）时，才报告没有匹配的函数。

注意 ¶1 只合成声明。函数体只在该特化被选中且被 odr-use 时才实例化（[[temp.inst#11]]），所以函数体里的错误永远不属于 SFINAE。

### 脚注：为什么推导出的形参只允许有限的转换

¶1 的脚注说明了设计意图：函数模板特化的形参中不含模板形参类型；推导所允许的转换集是受限的，因为推导过程产生的函数模板，其形参要么与调用实参精确匹配，要么只差那几种可以用受限转换弥补的差异（[[temp.deduct.call#4]]）。非推导的实参则允许全部的转换。此外，[[over.match.best]] 规定：若非模板函数与模板特化在其他方面同等好，优先选非模板函数。

## 例子：推导失败时由非模板函数接手（¶2）

```cpp
template<class T> T max(T a, T b) { return a > b ? a : b; }

void f(int a, int b, char c, char d) {
    int m1 = max(a, b);     // max(int a, int b)
    char m2 = max(c, d);    // max(char a, char b)
    int m3 = max(a, c);     // error: 无法生成 max(int, char)
}
```

`max(a, c)`：`T` 从第一个实参推导为 `int`，从第二个推导为 `char`，两者冲突，推导失败。模板不贡献候选，候选集为空。

加上一个非模板函数之后：

```cpp ok
template<class T> T max(T a, T b) { return a > b ? a : b; }
int max(int, int);

void f(int a, int b, char c, char d) {
    int m1 = max(a, b);     // 两个候选：max<int>(int,int) 与 max(int,int)；同等好，非模板优先
    char m2 = max(c, d);    // max<char>：精确匹配，优于需要提升的 max(int,int)
    int m3 = max(a, c);     // 只有 max(int,int)：c 做整型提升 char → int
    (void)m1; (void)m2; (void)m3;
}
```

非模板函数的形参类型固定，实参可以做任何隐式转换，于是模板推导失败的那次调用由它来接手。

## 推导中的转换（¶3）

例 2 表明，参与推导的实参也可以有转换，但仅限 [[temp.deduct.call#4]] 允许的那几种。派生类到基类就是其中之一：

```cpp ok
template<class T> struct B { };
template<class T> struct D : public B<T> { };
template<class T> void f(B<T>&) { }

void g(B<int>& bi, D<int>& di) {
    f(bi);    // f(bi)
    f(di);    // f((B<int>&)di)：T = int，派生到基类
}
```

## 不参与推导的实参：完整的转换（¶4）

例 3 表明，对形参中不参与推导的部分，实参可以做任意隐式转换：

```cpp run ok title="nondeduced_conv.cpp"
#include <cstdio>
template<class T> void f(T*, int)  { std::puts("#1"); }
template<class T> void f(T, char)  { std::puts("#2"); }

int main() {
    int* pi = nullptr; int i = 0; char c = 0;
    f(pi, i);   // #1: f<int>(pi, i)            —— 精确匹配
    f(pi, c);   // #2: f<int*>(pi, c)           —— #2 精确；#1 第二参需提升
    f(i, c);    // #2: f<int>(i, c)             —— #1 推导失败（int 不是指针）
    f(i, i);    // #2: f<int>(i, char(i))       —— #1 推导失败；#2 第二参 int → char 转换
}
```

- `f(pi, i)`：#1 = `f<int>(int*, int)`，两参都精确；#2 = `f<int*>(int*, char)`，第二参需要 `int` → `char` 转换。#1 胜。
- `f(pi, c)`：#1 第二参需要 `char` → `int` 提升；#2 两参都精确。#2 胜。
- `f(i, i)`：#1 推导失败（`T*` 不能匹配 `int`），只剩 #2 = `f<int>(int, char)`；第二个形参 `char` 不含模板形参、不参与推导，所以 `int` → `char` 这种窄化转换也照样允许。

## 只需要声明（¶5）

¶5 把函数模板特化放进候选集只需要它的签名。因此，解析一个以模板特化为候选的调用，只需要函数模板的声明：

```cpp
template<class T> void f(T);    // 只有声明

void g() {
    f("Annemarie");             // 调用 f<const char*>
}
```

即使在调用点模板 `f` 只有声明没有定义，对 `f` 的调用也是良构的。但除非在某个 TU 中显式实例化了 `f<const char*>`（[[temp.explicit]]），程序是非良构的（[[temp.pre]] 要求被使用的模板特化的定义在某处可得）。把模板定义放在 `.cpp` 中再显式实例化，这一手法的规范依据就在这里。

## 决胜：非模板优先、更特殊者优先

合成的候选进入 [[over.match.best]] 后，与其他候选一样，先比较隐式转换序列。只有当转换序列分不出高下时，才用模板相关的决胜规则：

1. [[over.match.best]] ¶2.4：`F1` 不是函数模板特化而 `F2` 是，则 `F1` 更好（非模板优先）；
2. ¶2.5：两者都是函数模板特化，`F1` 的模板按偏序（[[temp.func.order]]、[[temp.deduct.partial]]）比 `F2` 的模板更特殊，则 `F1` 更好；
3. 此后还有基于约束的比较等。

关键在于顺序：**转换序列的比较先于是否为模板的比较**。一个精确匹配的模板特化，胜过一个需要转换的非模板函数：

```cpp run ok title="template_vs_nontemplate.cpp"
#include <cstdio>
template<class T> void g(T) { std::puts("template"); }
void g(int)                 { std::puts("non-template int"); }
void g(long)                { std::puts("non-template long"); }

int main() {
    g(1);      // non-template int：与 g<int> 同等好，非模板优先
    g('a');    // template：g<char> 精确匹配，胜过需要提升的 g(int)
    g(1L);     // non-template long
    g(1u);     // template：g<unsigned> 精确，g(int)/g(long) 都需要转换
}
```

```cpp run ok title="string_overload.cpp"
#include <cstdio>
#include <string>
void show(const std::string&) { std::puts("string"); }
template<class T> void show(const T&) { std::puts("template"); }

int main() {
    show("hi");               // template：T = char[3]，精确匹配；string 版本需要用户定义转换
    show(std::string("hi"));  // string：同等好，非模板优先
}
```

`show("hi")` 调用模板是一个常见的意外：程序员想为字符串提供重载，却忘了字符串字面量不是 `std::string`。修正方法是加一个 `show(const char*)` 重载，或者约束模板（`requires (!std::is_convertible_v<const T&, std::string>)`）。

## SFINAE 与硬错误的边界

结合 [[temp.deduct.general#8]] 来看，能让候选静默消失的，只有声明（推导代入位置）中直接语境里的失败。函数体中的错误在选中之后才会出现，不能影响候选集：

```cpp error
template<class T> auto size_of(const T& c) { return c.size(); }   // 返回类型需由函数体推导
int size_of(...);
int n = size_of(42);   // error: 为确定返回类型实例化函数体，int 没有 size()
```

```cpp ok
template<class T> auto size_of(const T& c) -> decltype(c.size()) { return c.size(); }
int size_of(...);
int n = size_of(42);   // OK：decltype(c.size()) 在签名中，推导失败，选 size_of(...)
```

第一个版本的模板在推导时，为了得到合成声明的返回类型，必须实例化函数体（[[temp.inst#9]]），而函数体不在直接语境中，`c.size()` 的错误是硬错误。

## 实现视角

!!! impl "诊断中的被拒候选"
    Clang 与 GCC 在 "no matching function" 错误下，会把每个被 ¶1.2 剔除的模板列为附注，并给出原因，例如 "candidate template ignored: deduced conflicting types for parameter 'T' ('int' vs. 'char')" 或 "candidate template ignored: substitution failure [with T = int]: ..."。调试 SFINAE 时这是最有用的信息。

## 陷阱

!!! pitfall "完美转发构造函数劫持拷贝"
    ```cpp
    struct Person {
        template<class S> Person(S&& name);   // 转发构造
        Person(const Person&);                // 拷贝构造
    };
    Person p("x");
    Person q(p);    // 调用的是模板！
    ```
    `p` 是非 const 左值：模板推导出 `Person(Person&)`，精确匹配；拷贝构造函数需要添加 `const`。两者的转换序列不同（模板的更好），非模板优先的规则根本用不上。需要用约束排除 `Person` 自身：`requires (!std::is_same_v<std::remove_cvref_t<S>, Person>)`。

!!! pitfall "非模板优先只是最后的决胜规则"
    很多人以为只要有非模板函数就一定选它。实际上这条规则只在转换序列完全不分高下时才生效（见上面的 `g('a')`）。

## 思考题

!!! question "思考题 1"
    ```cpp
    template<class T> void f(T, T);
    void f(double, double);
    f(1, 2.0);
    f(1, 2);
    ```
    分别调用哪个？

<details markdown="1">
<summary>答案</summary>

`f(1, 2.0)`：模板推导 `T` 冲突（`int` vs `double`），失败，不贡献候选；非模板 `f(double, double)` 可行（`1` → `double`）。调用非模板。

`f(1, 2)`：模板推导 `T = int`，合成 `f<int>(int, int)`，精确匹配；非模板需要两次 `int` → `double` 转换。模板的转换序列更好，调用 `f<int>`。
</details>

!!! question "思考题 2"
    为什么 ¶1.2 要同时写推导失败和合成的特化会是非良构的这两个条件？什么情况下推导成功但合成的特化非良构？

<details markdown="1">
<summary>答案</summary>

推导（[[temp.deduct]]）的定义已经把代入后的函数类型无效算作推导失败。第二个条件覆盖的是推导之外的检查，例如显式模板实参的检查（[[temp.arg]]），即显式给出的实参与模板形参种类不符或个数过多；又如合成的声明违反了某些不属于无效类型的规则。标准用这句话保证：任何在形成候选声明这一步就出问题的模板，都只是被丢弃，而不会让整个调用非良构。
</details>

## 小结

| 要点 | 出处 |
|---|---|
| 每个模板：推导 + 检查 → 成功则合成一个特化声明加入候选 | ¶1.1 |
| 推导失败或合成特化非良构 → 不加候选（SFINAE 不报错的来源） | ¶1.2 |
| 候选集 = 合成声明 + 非模板函数；此后同等对待（[over.match.best] 的例外除外） | ¶1 |
| 推导的形参只容忍有限差异；非推导的形参允许完整转换 | 脚注、¶3–¶4 |
| 只需要模板声明即可决议；定义须在某处（如显式实例化）提供 | ¶5 |
| 决胜：先比转换序列；再非模板优先；再更特殊的模板优先 | [[over.match.best]] ¶2.4–¶2.5 |
