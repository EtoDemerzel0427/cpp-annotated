---
title: 两阶段查找与待决名
summary: 模板里的每个名字在什么时候、从哪里、用哪种方式查找：非依赖名在定义处绑定，依赖调用在实例化时追加 ADL，以及模块怎样决定实例化时看得见哪些声明。
status: done
order: 50
papers: P0634R3, P1787R6, P2593R1
related: temp.res, temp.local, temp.dep, temp.dep.res, temp.point, temp.dep.candidate, basic.lookup.argdep, module.context, module.reach
tags: 模板, 两阶段查找, 待决名, ADL, 模块
updated: 2026-10-19
---

!!! tldr
    - 模板里不依赖模板形参的名字在定义处查找并永久绑定；之后再声明的更好的重载，模板看不见。
    - 依赖调用 `f(t)` 的普通无限定查找也只在定义处做；实例化时只追加 ADL，所以只有实参类型关联命名空间里的函数能晚于模板声明。
    - 依赖基类的成员在定义时不会被搜索，要写 `this->x` 才能找到它们，否则可能悄悄绑定到外层作用域的同名实体。
    - 同一个特化在不同实例化点上含义不同时，程序是 IFNDR；不同编译器可能给出不同结果。
    - 有了模块，实例化时看得见什么由实例化语境决定，它包括模板所在模块接口的末尾。

## 更好的匹配为什么没被选中

```cpp run ok
#include <cstdio>
void f(int) { std::puts("f(int)"); }
template<class T> void g(T t) { f(t); }
void f(double) { std::puts("f(double)"); }
int main() { g(1.0); }
```

程序输出 `f(int)`。调用 `g<double>` 时 `f(double)` 已经声明，而且是精确匹配，却没有被选中。

**两阶段查找**（[[g:two-phase-lookup|two-phase name lookup]]）不是标准里的正式术语，而是一组规则的通称。它要同时照顾两件事：模板写错了能在定义时就发现，实例化时又能用上调用方提供的函数。

- 第一阶段在定义处。编译器完整解析模板定义。不依赖模板形参的名字叫**非依赖名**（non-dependent name），在这里查找并永久绑定；不依赖模板形参的结构在这里检查，有错可以当场报告。
- 第二阶段在实例化时。模板实参确定之后，查找依赖于模板形参的名字，即**依赖名**（dependent name）。但对依赖的无限定函数调用，这一阶段只追加 ADL（实参依赖查找，在实参类型的关联命名空间里找函数，见 [[basic.lookup.argdep]]），不会重做普通的无限定查找。

回到上面的例子。`f(t)` 的实参类型依赖于 `T`，所以是依赖调用。普通无限定查找在定义处进行，那时只看得见 `f(int)`。实例化时追加 ADL，但 `double` 是基本类型，没有关联命名空间，ADL 什么也找不到。`f(double)` 从未进入候选集，`1.0` 被转换成 `int`。

## 一个名字在什么时候查找

面对模板定义里的一个名字 `n`，依次问下面几个问题：

| 问题 | 是 | 否 |
|---|---|---|
| 1. `n` 是依赖的吗？（[[temp.dep]]） | 看第 2 问 | 在定义处查一次并绑定，以后不变（[[temp.res.general#1]]） |
| 2. `n` 是限定名（`X::n`、`x.n`、`p->n`）吗？ | 看第 3 问 | 看第 4 问 |
| 3. 查找上下文是当前实例化吗？ | 定义处先查；有依赖基类且查不到时推迟。实例化时再查一次，两次结果不同则为二义（[[temp.dep.type#5]]、[[temp.dep.type#6]]） | 替换模板实参后，在确定的类或命名空间里做限定名查找 |
| 4. `n` 是依赖调用 `n(args)` 里的函数名吗？ | 普通无限定查找只在定义处做；ADL 在定义处和实例化语境的每一点都做（[[basic.lookup.argdep#4]]） | 其他依赖的无限定名（如依赖的 `operator T`、`operator=`）在实例化时查找 |

**当前实例化**（current instantiation）指在类模板自己的定义里提到的这个类模板本身，比如 `C<T>` 的成员函数里的 `*this`。

名字在下列情况下是依赖的：

| 形式 | 原因 |
|---|---|
| `T::x`、`Base<T>::x` | 查找上下文是依赖类型（[[temp.dep.type#5]] ¶5.2） |
| `t.x`、`this->x`，`t` 或 `this` 的类型依赖于 `T` | 查找上下文依赖于 `T`；或者是有依赖基类的当前实例化，并且定义处查不到这个名字 |
| `f(t)`，`t` 的类型依赖于 `T` | 依赖调用（[[temp.dep.general#2]] ¶2.2） |
| `f(ts...)` | 包展开使它成为依赖调用（第 2.1 项） |
| `get<I>(x)`，`I` 是模板形参 | *template-id* 的模板实参依赖于模板形参（第 2.3 项） |
| 依赖的 `operator T()`，类模板里的 `operator=` | 第 2.4、2.5 项 |

下列情况不使名字依赖：

- `f()`、`f(1)`、`f(sizeof(T))`：实参都不是类型依赖的。最后一个容易看错，`sizeof(T)` 里出现了 `T`，但它的类型总是 `size_t`。
- 依赖基类里的名字。定义时根本不去依赖基类里找，除非用上表的某种写法让名字变成依赖的（见谜题 3）。

## 谜题

每道题先猜输出，再看答案。所有例子都用本机 Clang 23 验证过。

### 谜题 1：同样晚声明，这次却找到了

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

`Box<Tag>` 的关联实体包括 `Box<Tag>` 本身和它的类型模板实参 `Tag`（[[basic.lookup.argdep#3]]），对应的关联命名空间是全局命名空间。实例化时的 ADL 在全局命名空间里找到了后声明的 `describe`。和开头的例子相比，区别只在于实参类型有没有关联命名空间。
</details>

### 谜题 2：全局运算符被同名声明隐藏

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

全局的 `operator<<(ostream&, const vector<int>&)` 在模板之前就声明了。但从 `app::log` 内部做无限定查找时，先在命名空间 `app` 里找到了 `app::operator<<(ostream&, Widget)`。无限定查找在某一层作用域找到名字就停下，于是全局的那个被隐藏。ADL 的关联命名空间只有 `std`，而 `std` 里没有接受 `vector<int>` 的 `operator<<`。候选集里没有可行函数。

删掉 `Widget` 的 `operator<<`，程序就能编译并输出 `2`。所以不要在全局命名空间为别人的类型定义运算符：它能不能被找到，取决于调用处所在的命名空间里有没有同名声明。应当包装类型，或者把运算符定义在类型的关联命名空间里；对 `std` 中的类型，后者是不允许的。
</details>

### 谜题 3：悄悄绑定到别处

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

`g()` 没有实参，不是依赖调用，在定义处查找。**依赖基类**（dependent base class，类型依赖于模板形参的基类）`Base<T>` 在定义时不被搜索（[[temp.dep.type#3]]）。编译器此时还不知道 `Base<T>` 里有什么，比如 `Base<double>` 可能被显式特化成没有 `g` 的样子。于是查找继续向外，找到全局的 `::g` 并永久绑定。不实现两阶段查找的旧版 MSVC 会输出 `Base<T>::g`。要调用基类的版本，写成 `this->g()`，让它变成依赖名。
</details>

### 谜题 4：两个实例化点

```cpp ifndr
#include <cstdio>
namespace N { struct S { }; }
template<class T> int g(T t) { return h(t); }
int a = g(N::S{});
namespace N { int h(S) { return 42; } }
int main() { std::printf("%d\n", a); }
```

<details markdown="1">
<summary>答案：IFNDR，Clang 输出 42</summary>

`g<N::S>` 有两个**实例化点**（point of instantiation，[[temp.point#7]]）：一个紧跟在 `int a = ...;` 之后，此时 `N::h` 还没声明，调用非良构；另一个在翻译单元末尾，此时 ADL 能找到 `N::h`。两处给出不同的含义，程序 IFNDR（非良构，不要求诊断）。

Clang 把函数模板的实例化推迟到翻译单元末尾，所以接受并输出 42。如果把 `g` 改成 `constexpr`，Clang 会立即实例化并报告 `use of undeclared identifier 'h'`。同一段 IFNDR 代码，结果取决于编译器在哪个点实例化。
</details>

### 谜题 5：类模板没有第二次机会

```cpp error
namespace N { struct A { }; }
template<class T> struct H { char buf[probe(T{})]; };
int x = sizeof(H<N::A>);
namespace N { constexpr int probe(A) { return 4; } }
```

<details markdown="1">
<summary>答案：编译失败，这是真正的非良构</summary>

类模板特化的实例化点紧挨在引用它的声明之前，并且一个翻译单元里至多一个（[[temp.point#4]]、[[temp.point#7]]）。`H<N::A>` 在 `int x` 之前实例化，此时 `probe` 还没有声明，ADL 也找不到。没有翻译单元末尾这个点可以补救。和谜题 4 相比，函数模板可以等，类模板不行。
</details>

### 谜题 6：写了 `this->` 反而报错

```cpp error
struct A { int m; };
struct B { int m; };
template<class T> struct C : A, T {
    int f() { return this->m; }
};
template int C<B>::f();
```

<details markdown="1">
<summary>答案：编译失败，二义</summary>

`this->m` 的查找上下文是当前实例化 `C<T>`。定义时在非依赖基类 `A` 中找到 `A::m`。实例化 `C<B>` 时，按 [[temp.dep.type#6]] 在实例化语境中再查一次，这次依赖基类 `B` 也参与，找到 `A::m` 和 `B::m`，与定义时的结果不同，因此是二义。

把 `this->m` 换成无限定的 `m` 反而没有问题。无限定的 `m` 在定义处绑定为 `A::m`；把它变换为 `(*this).m` 这一步不在模板定义语境中发生（[[expr.prim.id.general#2]]），所以实例化时不会再查一次。
</details>

### 谜题 7：没有模板形参的依赖 {{c++26}}

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

`f` 里没有任何东西依赖 `T`。但 C++26 规定，**结构化绑定包** `e` 是类型依赖的（[[temp.dep.expr#3]] ¶3.6），`g(e...)` 又是包展开，于是成了依赖调用。普通无限定查找仍在定义处进行，只看得见 `g(...)`；ADL 推迟到实例化时，在 `C` 的关联命名空间（全局）里找到了后声明的 `g(C)`，它比 `g(...)` 匹配得更好。如果写成 `auto [x] = arr; g(x);`，就是非依赖调用，定义处只看得见 `g(...)`。
</details>

### 谜题 8：`static_assert(false)`

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

`never` 从未实例化；`pick<int>` 中的 `else` 分支被丢弃，不会实例化。C++23 的 [[P2593R1]] 规定，判断模板能否生成有效特化时忽略失败的 `static_assert`（[[temp.res.general#6]] ¶6.1），在模板定义语境中求值的静态断言也没有效果（[[dcl.pre#13]]）。

C++23 之前这是 IFNDR，GCC 和 Clang 会在定义处直接报错。当时只能写 `static_assert(dependent_false<T>)`，人为制造依赖。
</details>

## 规则为什么这样定

C++ 在这里同时想要三样东西：

1. **早期诊断**。模板作者写错了，应当在写模板时就发现，而不是等用户实例化时看到一屏错误。这要求在定义时解析和检查模板，所以需要 `typename` 和 `template` 消除歧义。
2. **含义稳定**。模板的行为由作者在定义处看到的声明决定，不会被用户在实例化之前声明的某个同名函数改变（开头的例子、谜题 3）。所以非依赖名在定义处绑定，依赖基类不被搜索。
3. **定制点**。泛型代码必须能调用用户类型的 `swap`、`begin`、`operator<<`，而这些函数在模板定义时还不存在。所以实例化时追加 ADL。只追加 ADL，是因为它只会找到与实参类型相关的函数，那是类型作者有意提供的接口，而不是碰巧同名的函数。

剩下的复杂性大多来自实例化时这个时间点不唯一：一个特化可能在多处使用、在多个翻译单元中实例化，编译器也可能推迟到翻译单元末尾。标准允许所有这些实现策略，凡是会因此得到不同结果的程序一律 IFNDR（[[temp.point#7]]、[[temp.dep.candidate#1]]、[[temp.res.general#6]] ¶6.8）。

## 模块里的实例化语境

没有模块时，实例化时看得见的就是同一翻译单元里实例化点之前的声明。有了模块，模板定义在模块 A 里，实例化发生在导入 A 的翻译单元里，实参类型又可能来自第三个模块。C++20 用**实例化语境**（instantiation context，[[module.context]]）回答此时看得见什么。

### 实例化语境是一组点

按 [[module.context#1]]，实例化语境是程序里的一组点。它决定 ADL 能找到哪些声明（[[basic.lookup.argdep]]），以及在某个声明或模板实例化的语境里哪些声明**可达**（reachable，[[module.reach]]）。

| 情形 | 实例化语境包含 | 段落 |
|---|---|---|
| 预置函数的隐式定义，如 `= default` 的 `operator==` | 类定义处的实例化语境，加上引发隐式定义的那个结构的实例化语境 | [[module.context#2]] |
| 模板的实例化点因外围特化而产生 | 外围特化的实例化语境；如果模板定义在模块 M 的接口单元里，而实例化点不在其中，再加上 M 的主模块接口单元的末尾 | [[module.context#3]] |
| 因预置函数的隐式定义而引发的模板实例化 | 该预置函数的实例化语境 | [[module.context#4]] |
| 其他模板特化的实例化 | 该模板的实例化点 | [[module.context#5]] |
| 常量求值引发的隐式实例化 {{c++26}} | 求值语境（[[expr.const.reflect]]）中的每一点 | [[module.context#6]] |
| 其他情况 | 那个点本身 | [[module.context#7]] |

第 8 段规定实例化语境只包含上表列出的点。第 3 段最关键：它把链条上每个模块的接口末尾都纳入了实例化语境。

### 可达性取决于链条上的模块

下面是 [[module.context#9]] 的例子：

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

`f(0)` 是合法的。`foo<int, X>` 的实例化语境是 TU #1 末尾、TU #2 末尾和 `f(0)` 的调用处。在 TU #2 末尾，来自头文件单元 `defn.h` 的 `X` 的定义可达，`auto v = u;` 需要的完整类型有了。

`g(0)` 是否合法是未指明的。`bar<int, X>` 的实例化语境是 TU #1 末尾、TU #3 末尾和 `g(0)` 的调用处。`*u` 需要 `X` 的定义，但 TU #3 只导入了声明。TU #4 经由 `M1` 间接导入了 `defn.h`，它是否因此可达，按 [[module.reach]] 是未指明的。

### 被丢弃的声明不参与

按 [[basic.lookup.argdep#4]]，对依赖名从实例化语境中的点做 ADL 时，还要忽略同时满足以下条件的声明：出现在另一个翻译单元里，附属于全局模块，并且被丢弃（[[module.global.frag]]）或具有内部链接。

实际的含义是：在模块单元的全局模块片段里 `#include` 了一个头文件，而模块自己没有用到其中某个函数，这个函数就被丢弃了。下游翻译单元实例化你的模板时，ADL 找不到它（[[temp.dep.candidate]] 中的 `dog` 例子）。解决办法是在模块单元里确实用到它，比如在模板定义中以非依赖的方式引用它，或者改为导入头文件单元。

### 可运行的例子

[[temp.dep.candidate]] 里定制点 `swap` 跨模块工作的例子，可以用 Clang 编译运行：

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

构建命令：

```text
clang++ -std=c++2c --precompile Std.cppm -o Std.pcm
clang++ -std=c++2c --precompile -fmodule-file=Std=Std.pcm M.cppm -o M.pcm
clang++ -std=c++2c -fmodule-file=Std=Std.pcm -fmodule-file=M=M.pcm main.cpp M.pcm Std.pcm -o main
```

`swap(S&, S&)` 没有导出，模块 `Std` 也不可能看见它。但 `indirect_swap<S*>` 的实例化点在模块 `M` 里，ADL 从那里找到了它。

## 写模板代码时的清单

1. 依赖基类的成员一律用 `this->` 访问。不要用 `Base<T>::`，对虚函数它会关闭虚派发。
2. 依赖的类型名前写 `typename`。C++20 起在仅类型语境（[[temp.res.general#4]]）中可以省略，但块作用域里的声明、模板实参里仍然需要。
3. 依赖的成员模板前加 `template`，如 `t.template get<0>()`、`T::template rebind<U>`，否则 `<` 会被当成小于号。
4. 定制点（`swap`、`begin`、`operator<<` 等）和类型定义在同一个命名空间、同一个头文件里，这样任何实例化点上 ADL 都能找到它们，避免谜题 4 那样的 IFNDR。
5. 不要在全局命名空间为别人的类型重载运算符（谜题 2）。
6. 显式特化要在第一次使用之前声明（[[temp.expl.spec#7]]）。
7. 想调用在模板定义之后才声明的函数，只能依靠 ADL，要确保它在实参类型的关联命名空间里。
8. 使用模块时，被模板以依赖方式调用的辅助函数，不要只放在全局模块片段的 `#include` 里。导出它、在模块里引用它，或者改用头文件单元。

## 相关条款

- [[temp.res]]：查找从哪里出发、`typename`、仅类型语境、IFNDR 清单
- [[temp.local]]：注入类名、模板形参的查找顺序
- [[temp.dep]]：依赖类型、类型依赖与值依赖、当前实例化
- [[temp.dep.res]]：实例化点、候选函数、依赖基类
- [[basic.lookup.argdep]]：ADL
- [[module.context]]、[[module.reach]]：模块中的实例化语境与可达性
