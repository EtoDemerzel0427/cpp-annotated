---
title: 两阶段查找与待决名
summary: 把散落在 [temp.res]、[temp.dep]、[temp.point]、[basic.lookup.argdep]、[module.context] 中的规则拼成一张完整的图：模板中每个名字在何时、何处、以何种方式被查找；配一组"猜输出"式的谜题，以及模块如何改变实例化语境。
status: done
order: 50
papers: P0634R3, P1787R6, P2593R1
related: temp.res, temp.local, temp.dep, temp.dep.res, temp.point, temp.dep.candidate, basic.lookup.argdep, module.context, module.reach
tags: 模板, 两阶段查找, 待决名, ADL, 模块
updated: 2026-10-17
---

[[g:two-phase-lookup|"两阶段查找"]]（two-phase name lookup）不是标准里的术语，而是一组规则的俗称：

- **第一阶段——定义时**：模板定义被完整解析。不依赖模板形参的名字（**非依赖名**）在此查找并永久绑定；非依赖的结构在此检查（可以报错）。
- **第二阶段——实例化时**：模板实参确定后，**依赖名**（依赖于模板形参的名字）被查找；但依赖的无限定函数调用在这一阶段**只追加 ADL**。

这页专题不逐段解读条款（那是 [[temp.res]]、[[temp.dep]]、[[temp.dep.res]] 的事），而是：先给出一个完整的判定流程，然后用一组谜题检验，最后讲模块。

## 一张决策表

面对模板定义中的一个名字 `n`，依次问：

| 问题 | 是 | 否 |
|---|---|---|
| 1. `n` 是依赖的吗？（[[temp.dep]]） | 进入 2 | **定义处**查一次，绑定，完事（[[temp.res.general#1]]） |
| 2. `n` 是限定名（`X::n`、`x.n`、`p->n`）吗？ | 进入 3 | 进入 4 |
| 3. 查找上下文是当前实例化吗？ | 定义处先查；若有依赖基类且查无此名则推迟；实例化时再查，结果不同则二义（[[temp.dep.type#5]]、[[temp.dep.type#6]]） | 替换后在确定的类/命名空间中做限定名查找 |
| 4. `n` 是依赖调用 `n(args)` 的被调名吗？ | 普通无限定查找：**定义处**；ADL：定义处 + **实例化语境**中每一点（[[basic.lookup.argdep#4]]） | （其他依赖的无限定名，如依赖的 `operator T`、`operator=`）实例化时查找 |

什么让名字"依赖"？最常见的来源：

| 形式 | 依赖的原因 |
|---|---|
| `T::x`、`Base<T>::x` | 查找上下文是依赖类型（[[temp.dep.type#5]] ¶5.2） |
| `t.x`、`this->x`（`t`、`this` 类型依赖） | 成员限定名，查找上下文依赖（或当前实例化 + 依赖基类 + 查无此名） |
| `f(t)`，`t` 类型依赖 | 依赖调用（[[temp.dep.general#2]]） |
| `f(ts...)` | 包展开使其成为依赖调用 |
| `get<I>(x)`，`I` 是模板形参 | *template-id* 有依赖实参（¶2.3） |
| `operator T()`、类模板中的 `operator=` | ¶2.4、¶2.5 |

什么**不**让名字依赖？

- `f()`、`f(1)`、`f(sizeof(T))`——实参不是类型依赖的（`sizeof(T)` 的类型是 `size_t`）。
- 依赖基类里的名字——它们根本不会在定义时被找到，除非你用上表的某种方式让它依赖。

## 谜题

每道谜题先给代码，猜一猜，再看答案。所有例子都用 Clang 23 验证过。

### 谜题 1：更好的匹配为什么没被选中？

```cpp run ok
#include <cstdio>
void f(int) { std::puts("f(int)"); }
template<class T> void g(T t) { f(t); }
void f(double) { std::puts("f(double)"); }
int main() { g(1.0); }
```

<details markdown="1">
<summary>答案：f(int)</summary>

`f(t)` 是依赖调用。普通无限定查找在**定义处**进行，只看见 `f(int)`。实例化时追加 ADL，但 `double` 没有关联命名空间，ADL 什么也找不到。`f(double)` 虽然在实例化时已经声明、而且是精确匹配，却从未进入候选集。
</details>

### 谜题 2：同样晚声明，这次却找到了

```cpp run ok
#include <cstdio>
template<class T> struct Box { T v; };
template<class T> void show(const Box<T>& b) { describe(b); }
struct Tag { };
void describe(const Box<Tag>&) { std::puts("Box<Tag>"); }
int main() { show(Box<Tag>{}); }
```

<details markdown="1">
<summary>答案：Box&lt;Tag&gt;</summary>

`Box<Tag>` 的关联实体包括 `Box<Tag>` 本身和其**类型模板实参** `Tag`（[[basic.lookup.argdep#3]]），关联命名空间是全局命名空间。实例化语境中的 ADL 在全局命名空间里找到了后声明的 `describe`。和谜题 1 的区别仅在于：实参类型有没有关联命名空间。
</details>

### 谜题 3：hidden 的运算符

```cpp error
#include <iostream>
#include <vector>
std::ostream& operator<<(std::ostream& os, const std::vector<int>& v) { return os << v.size(); }

namespace app {
    struct Widget { };
    std::ostream& operator<<(std::ostream& os, Widget) { return os << "W"; }
    template<class T> void log(const T& t) { std::cout << t << '\n'; }
}
int main() { app::log(std::vector<int>{1, 2}); }
```

<details markdown="1">
<summary>答案：编译失败</summary>

全局的 `operator<<(ostream&, const vector<int>&)` 在模板**之前**声明，但从 `app::log` 内部做无限定查找时，先在 `app` 命名空间中找到了 `app::operator<<(ostream&, Widget)`，查找就此停止，全局的那个被**隐藏**。ADL 的关联命名空间只有 `std`（`ostream` 和 `vector<int>` 都在 `std`），`std` 里没有接受 `vector<int>` 的 `operator<<`。所以候选集里没有可行函数。

删掉 `Widget` 的 `operator<<`，程序就能编译并输出 `2`——无限定查找一路找到全局命名空间。这就是为什么"给标准库类型在全局命名空间定义运算符"是个坏主意：它的可用性取决于调用点所在命名空间里有没有同名声明。正确做法是包装类型，或把运算符定义在类型的关联命名空间中（对 `std` 类型而言这是不允许的）。
</details>

### 谜题 4：静默改道

```cpp run ok
#include <cstdio>
void g() { std::puts("::g"); }
template<class T> struct Base { void g() { std::puts("Base<T>::g"); } };
template<class T> struct D : Base<T> {
    void f() { g(); }
};
int main() { D<double>{}.f(); }
```

<details markdown="1">
<summary>答案：::g</summary>

`g()` 没有实参，不是依赖调用，在定义处查找。依赖基类 `Base<T>` 在定义时不被搜索（[[temp.dep.type#3]]），于是找到全局的 `::g` 并永久绑定。旧版 MSVC（不实现两阶段查找）会输出 `Base<T>::g`。改成 `this->g()` 即可。
</details>

### 谜题 5：两个实例化点

```cpp ifndr
#include <cstdio>
namespace N { struct S { }; }
template<class T> int g(T t) { return h(t); }
int a = g(N::S{});
namespace N { int h(S) { return 42; } }
int main() { std::printf("%d\n", a); }
```

<details markdown="1">
<summary>答案：IFNDR（Clang 输出 42）</summary>

`g<N::S>` 有两个实例化点（[[temp.point#7]]）：紧随 `int a = ...;` 之后（此时 `N::h` 未声明，调用非良构），和 TU 末尾（此时 ADL 找到 `N::h`）。两者含义不同，程序 IFNDR。Clang 把函数模板实例化推迟到 TU 末尾，所以接受并输出 42。如果把 `g` 改成 `constexpr`，Clang 会立即实例化并报错——同一段 IFNDR 代码，不同的结果。
</details>

### 谜题 6：类模板没有第二次机会

```cpp error
namespace N { struct A { }; }
template<class T> struct H { char buf[probe(T{})]; };
int x = sizeof(H<N::A>);
namespace N { constexpr int probe(A) { return 4; } }
```

<details markdown="1">
<summary>答案：编译失败（真正的非良构）</summary>

类模板特化的 POI 紧挨在引用它的声明**之前**，且一个 TU 中至多一个（[[temp.point#4]]、¶7）。`H<N::A>` 在 `int x` 之前实例化，此时 `probe` 未声明，ADL 也找不到。没有"TU 末尾"可以补救。和谜题 5 对比：函数模板可以"等"，类模板不行。
</details>

### 谜题 7：this-> 也会报错

```cpp error
struct A { int m; };
struct B { int m; };
template<class T> struct C : A, T {
    int f() { return this->m; }
};
template int C<B>::f();
```

<details markdown="1">
<summary>答案：编译失败（二义）</summary>

`this->m` 的查找上下文是当前实例化 `C<T>`。定义时，非依赖基类 `A` 中找到 `A::m`。实例化 `C<B>` 时按 [[temp.dep.type#6]] 在实例化语境中**再查一次**，此时依赖基类 `B` 也参与，找到 `A::m` 和 `B::m`，与定义时的结果不同 → 二义。

有趣的是，把 `this->m` 换成无限定的 `m` 反而没问题：无限定的 `m` 在定义处绑定为 `A::m`，向 `(*this).m` 的变换"不在模板定义语境中发生"（[[expr.prim.id.general#2]]），不会二次查找。
</details>

### 谜题 8：没有模板形参的"依赖"

```cpp run ok
#include <cstdio>
struct C { };
void g(...) { std::puts("g(...)"); }
template<class T> void f() {
    C arr[1];
    auto [...e] = arr;
    g(e...);
}
void g(C) { std::puts("g(C)"); }
int main() { f<int>(); }
```

<details markdown="1">
<summary>答案：g(C)</summary>

`f` 中没有任何东西依赖 `T`，但 C++26 的**结构化绑定包** `e` 被规定为类型依赖（[[temp.dep.expr#3]] ¶3.6），`g(e...)` 又是包展开——依赖调用。于是 `g` 的 ADL 推迟到实例化，`C` 的关联命名空间（全局）中找到后声明的 `g(C)`，它比 `g(...)` 好。若写成 `auto [x] = arr; g(x);`，就是非依赖调用，定义处只看得见 `g(...)`。
</details>

### 谜题 9：static_assert(false)

```cpp run ok
template<class T> void never() { static_assert(false, "boom"); }
template<class T> int pick(T) {
    if constexpr (sizeof(T) <= 8) return 1;
    else static_assert(false, "too big");
}
int main() { return pick(0) - 1; }
```

<details markdown="1">
<summary>答案：C++23 起良构</summary>

`never` 从未实例化；`pick<int>` 中 `else` 分支被丢弃、不被实例化。C++23 的 [[P2593R1]] 规定判断"能否生成合法特化"时忽略失败的 `static_assert`（[[temp.res.general#6]] ¶6.1），且在模板定义语境中求值的静态断言没有效果（[[dcl.pre#13]]）。在 C++23 之前这是 IFNDR，GCC/Clang 会在定义处报错，人们只能写 `static_assert(dependent_false<T>)`。
</details>

## 规则背后的设计

为什么 C++ 要搞得这么复杂？因为它同时想要三样东西：

1. **早期诊断**：模板作者写错了，应该在写模板时就知道，而不是等用户实例化时看到一屏错误。→ 需要定义时解析与检查 → 需要 `typename`/`template` 消歧义。
2. **模板含义稳定**：模板的行为由作者在定义处看到的声明决定，不会被用户在实例化前声明的某个同名函数劫持（谜题 1、谜题 4）。→ 非依赖名定义处绑定；依赖基类不搜索。
3. **定制点**：泛型代码必须能调用用户类型的 `swap`、`begin`、`operator<<`，而这些函数在模板定义时还不存在。→ 实例化时追加 ADL——但**只**追加 ADL，因为 ADL 只会找到"与实参类型相关"的函数，这是用户有意提供的接口，而不是偶然同名的东西。

剩下的复杂性大多来自"实例化时"这个时间点不唯一：一个特化可能在多处被使用、在多个 TU 中实例化、编译器想推迟到 TU 末尾……标准的回答是：允许所有这些实现策略，凡是会产生不同结果的程序一律 IFNDR（[[temp.point#7]]、[[temp.dep.candidate#1]]、[[temp.res.general#6]] ¶6.8）。

## 模块如何改变"实例化时"

在没有模块的世界里，"实例化时看得见什么"很简单：POI 之前该 TU 中的声明。模块打破了"一个 TU 包含一切"的假设：模板定义在模块 A 中，实例化发生在导入了 A 的 TU 中，而实参类型可能来自第三个模块。C++20 引入**实例化语境**（instantiation context，[[module.context]]）来回答"此时看得见什么"。

### 实例化语境是一组点

¶1 实例化语境是程序中的一组点，它决定 ADL 找到哪些声明（[[basic.lookup.argdep]]），以及在某个声明或模板实例化的语境中哪些声明**可达**（[[module.reach]]）。

各段规定了这组点包含什么：

| 情形 | 实例化语境包含 | 段落 |
|---|---|---|
| 默认函数的隐式定义（如 `= default` 的 `operator==`） | 类定义处的实例化语境 ∪ 引发隐式定义的那个结构的实例化语境 | ¶2 |
| 模板 POI 继承自外围特化 | 外围特化的实例化语境；若模板在模块 M 的接口单元中定义、POI 不在 M 的接口单元中，再加上 **M 的主模块接口单元末尾** | ¶3 |
| 因默认函数的隐式定义而引发的模板实例化 | 该默认函数的实例化语境 | ¶4 |
| 其他模板特化的实例化 | 该模板的 POI | ¶5 |
| 常量求值引发的隐式实例化 {{c++26}} | 求值语境（[[expr.const.reflect]]）中的每一点 | ¶6 |
| 其他情况 | 那个点本身 | ¶7 |

¶8：实例化语境只包含上面列出的点。

¶3 是关键：它把"链条"上每个模块的**接口末尾**都纳入了实例化语境。于是，当 `M1` 中的模板 `f` 调用 `stuff` 中的模板 `foo`，然后在 TU #4 中被实例化时，`foo` 的实例化语境包括：`stuff` 的接口末尾、`M1` 的接口末尾、TU #4 中的调用点。

### 例：可达性取决于链条上的模块

[[module.context#9]] 的例子：

```cpp title="TU #1"
export module stuff;
export template<typename T, typename U> void foo(T, U u) { auto v = u; }
export template<typename T, typename U> void bar(T, U u) { auto v = *u; }
```

```cpp title="TU #2"
export module M1;
import "defn.h";        // 提供 struct X {};
import stuff;
export template<typename T> void f(T t) {
    X x;
    foo(t, x);
}
```

```cpp title="TU #3"
export module M2;
import "decl.h";        // 提供 struct X;（只有声明）
import stuff;
export template<typename T> void g(T t) {
    X *x;
    bar(t, x);
}
```

```cpp title="TU #4"
import M1;
import M2;
void test() {
    f(0);
    g(0);
}
```

- `f(0)` 合法：`foo<int, X>` 的实例化语境 = {TU #1 末尾, TU #2 末尾, `f(0)` 调用点}。TU #2 末尾处 `X` 的定义（来自导入的 `defn.h` 头文件单元）是可达的，`auto v = u;` 需要完整类型，满足。
- `g(0)` 是否合法**未指明**：`bar<int, X>` 的实例化语境 = {TU #1 末尾, TU #3 末尾, `g(0)` 调用点}。`*u` 需要 `X` 的定义，但 TU #3 只导入了声明；TU #4 间接导入了 `M1`，`defn.h` 是否因此可达，按 [[module.reach]] 是未指明的（实现可以让间接导入的接口依赖可达，也可以不让）。

### 例：被丢弃的声明不参与

[[basic.lookup.argdep#4]] 规定，对依赖名从实例化语境中的点做 ADL 时，**额外忽略**同时满足以下条件的声明：出现在另一个 TU、附属于全局模块、且被丢弃（[[module.global.frag]]）或具有内部链接。

实际含义：如果你在模块单元的全局模块片段里 `#include` 了一个头文件，而模块自己没有用到其中的某个函数，这个函数就被丢弃了——下游 TU 中实例化你的模板时，ADL 找不到它（[[temp.dep.candidate#5]] 的 `dog` 例子）。修正方法：在模块单元中确实"用到"它（例如模板定义中以非依赖方式引用它），或者导入头文件单元而不是 `#include`。

### 一个可运行的模块例子

[[temp.dep.candidate#3]] 的例子（定制点 `swap` 跨模块工作）可以用 Clang 编译运行：

```cpp title="Std.cppm"
export module Std;
export template<typename Iter>
void indirect_swap(Iter lhs, Iter rhs) { swap(*lhs, *rhs); }
```

```cpp title="M.cppm"
export module M;
import Std;
struct S { int v; };
void swap(S& a, S& b) { int t = a.v; a.v = b.v; b.v = t; }   // 未导出
export int f() { S a{1}, b{2}; indirect_swap(&a, &b); return a.v; }
```

```cpp ok title="main.cpp"
import M;
#include <cstdio>
int main() { std::printf("%d\n", f()); }   // 输出 2
```

构建命令（Clang）：

```text
clang++ -std=c++2c --precompile Std.cppm -o Std.pcm
clang++ -std=c++2c --precompile -fmodule-file=Std=Std.pcm M.cppm -o M.pcm
clang++ -std=c++2c -fmodule-file=Std=Std.pcm -fmodule-file=M=M.pcm main.cpp M.pcm Std.pcm -o main
```

`swap(S&, S&)` 没有导出，模块 `Std` 也不可能看见它；但 `indirect_swap<S*>` 的 POI 在模块 `M` 中，ADL 从那里找到了它。

## 写出稳健模板代码的清单

1. 依赖基类的成员一律用 `this->`（不是 `Base<T>::`，后者会关闭虚派发）。
2. 依赖类型名前写 `typename`——C++20 起在仅类型语境（[[temp.res.general#4]]）中可省略，但块作用域、模板实参中仍然需要。
3. 依赖的成员模板加 `template`：`t.template get<0>()`、`T::template rebind<U>`。
4. 自定义点（`swap`、`begin`、`operator<<`……）与类型定义在**同一个命名空间**中、在同一头文件里声明，让 ADL 总能在任何 POI 找到它们，避免谜题 5 一类的 IFNDR。
5. 不要在全局命名空间为别人的类型重载运算符（谜题 3）。
6. 显式特化在第一次使用之前声明（[[temp.expl.spec#7]]）。
7. 想调用"晚于模板定义"的函数？只有 ADL 能帮你——确保实参类型的关联命名空间里有它。
8. 模块：被模板以依赖方式使用的辅助函数，不要只放在全局模块片段的 `#include` 里；导出它、或在模块中引用它、或用头文件单元。

## 相关条款

- [[temp.res]]：查找从哪里出发、`typename`、仅类型语境、IFNDR 清单
- [[temp.local]]：注入类名、模板形参的查找顺序
- [[temp.dep]]：依赖类型、类型依赖/值依赖、当前实例化
- [[temp.dep.res]]：实例化点、候选函数、依赖基类与 MSVC 的历史
- [[basic.lookup.argdep]]：ADL 本身
- [[module.context]]、[[module.reach]]：模块中的实例化语境与可达性
