---
title: 待决名决议
summary: 依赖名在哪里被查找：实例化点（POI）如何确定——函数模板紧随引用它的声明之后、类模板紧挨其前、翻译单元末尾也是 POI；多个 POI 含义不同即 IFNDR；依赖调用的候选函数 = 定义处的无限定查找 ∪ 定义语境与实例化语境中的 ADL。附两阶段查找的精确表述、依赖基类与 this->、MSVC 的历史差异。
status: done
covers: temp.dep.res, temp.point, temp.dep.candidate
papers: P1787R6
related: temp.res, temp.dep, temp.inst, basic.lookup.argdep, module.context, module.reach, temp.expl.spec, basic.def.odr, topics/two-phase-lookup
tags: 模板, 两阶段查找, 实例化点, ADL, 模块, IFNDR
updated: 2026-10-17
---

[[temp.dep]] 决定了**哪些名字**是依赖的；本节 [[temp.dep.res]]（dependent name resolution）决定依赖名**在哪里**被查找。它只有两个子条款：

- [[temp.point]]：[[g:point-of-instantiation|**实例化点**]]（point of instantiation，POI）——一个特化"在源代码的哪个位置被实例化"；
- [[temp.dep.candidate]]：依赖调用的**候选函数**——ADL 在实例化语境中找到的函数也参与重载决议，但若"看全所有 TU"会改变结果，则 IFNDR。

本页先把散落在几个条款中的"两阶段查找"规则拼成一张完整的图，再逐段读这两个子条款。

## 两阶段查找的精确表述

"两阶段查找"不是标准术语，它是以下规则的合称：

| 名字的种类 | 在哪里查找 | 出处 |
|---|---|---|
| 非依赖名（无论限定与否） | 只在**定义处**查一次；结果固定 | [[temp.res.general#1]] |
| 依赖调用 `f(args)` 中的 `f`：普通无限定查找 | 从**定义处**出发（对每个特化各做一次，但起点相同，结果相同） | [[temp.res.general#1]]、[[basic.lookup.unqual]] |
| 依赖调用 `f(args)` 中的 `f`：ADL | 从定义处，**以及实例化语境中的每一点**出发 | [[basic.lookup.argdep#4]]、[[module.context]] |
| 依赖的限定名 `T::x`、`Base<T>::x`、`t.x` | 替换后在确定的查找上下文中做限定名查找 | [[temp.res.general#1]]、[[temp.dep.type#5]] |
| 以限定名引用的当前实例化成员 | 定义处查一次；实例化时在实例化语境中再查，结果不同则二义 | [[temp.dep.type#6]] |

关键在第 2、3 行：**依赖调用并不是"在实例化处做完整的查找"**。实例化处只追加 ADL；普通的无限定查找仍然只看得到定义处之前的声明。

!!! std
    If N is a dependent name, the above lookup is also performed from each point in the instantiation context of the lookup, ...

    （[[basic.lookup.argdep#4]]）对依赖名，ADL 还要从实例化语境中的每一点出发再做一次。

对于不使用模块的程序，实例化语境就是实例化点本身（[[module.context#5]]）。模块带来的扩展见下文和 [[topics/two-phase-lookup]]。

```cpp run ok title="where_lookup_happens.cpp"
#include <cstdio>
void f(int) { std::puts("f(int)"); }

template<class T> void g(T t) { f(t); }    // 依赖调用

void f(double) { std::puts("f(double)"); } // 定义之后才声明
namespace N {
    struct S { operator int() const { return 0; } };
    void f(S) { std::puts("N::f(S)"); }    // 定义之后才声明
}

int main() {
    g(1.0);      // f(int)：f(double) 不可见——无限定查找只在定义处，double 无关联命名空间
    g(N::S{});   // N::f(S)：实例化语境中的 ADL 找到它
}
```

`g(1.0)` 调用 `f(int)`（`double` 隐式转换为 `int`），尽管 `f(double)` 在实例化时早已声明且是精确匹配。这是两阶段查找最常被误解的地方。

## 依赖基类与 this->

两阶段查找最常见的"受害者"是依赖基类中的成员：

```cpp error
template<class T> struct Base { void g() { } };
template<class T> struct D : Base<T> {
    void f() { g(); }    // error: g 没有实参 → 不是依赖调用 → 定义处查找，依赖基类不被搜索
};
```

`g()` 没有实参，也就不可能有类型依赖的实参，按 [[temp.dep.general#2]] 它**不是**依赖调用，`g` 是非依赖名。定义处查找：`D` 中没有 `g`，依赖基类 `Base<T>` 不被搜索（[[class.member.lookup#4]]、[[temp.dep.type#3]]），全局也没有 → 找不到。

为什么依赖基类不被搜索？因为 `Base<T>` 可以被**显式特化**成任何样子：

```cpp run ok title="silent_rebinding.cpp"
#include <cstdio>
void g() { std::puts("::g"); }

template<class T> struct Base { void g() { std::puts("Base<T>::g"); } };
template<class T> struct D : Base<T> {
    void f() {
        g();          // ::g——定义处绑定，永远不会是 Base<T>::g
        this->g();    // Base<T>::g——依赖名，实例化时查找
    }
};
template<> struct Base<int> { };   // 显式特化：没有 g

int main() { D<double>{}.f(); }    // 输出 ::g，然后 Base<T>::g
```

这个例子说明了两件事：（1）如果全局恰好有个 `g`，无限定的 `g()` 会**静默**地绑定到它——不报错，行为却不是你想要的；（2）如果规则允许在定义处"偷看"主模板 `Base<T>` 的成员，那么 `D<int>` 将无法正确处理 `Base<int>` 这个没有 `g` 的特化。标准选择了一致且可预测的规则：依赖基类在定义时**不存在**。

让名字变成依赖的三种写法：

```cpp run ok
template<class T> struct Base { void g() { } int x = 0; };
template<class T> struct D : Base<T> {
    void f() {
        this->g();      // ① this 类型依赖 → 成员访问依赖
        D::g();         // ② 查找上下文是当前实例化、有依赖基类、查无此名 → 依赖（¶5.4）
        Base<T>::g();   // ③ 查找上下文依赖 → 依赖（¶5.2）
    }
};
template<class T> struct D2 : Base<T> {
    using Base<T>::g;   // ④ using 声明把名字引入当前作用域
    void f() { g(); }
};
int main() { D<int>{}.f(); D2<int>{}.f(); }
```

!!! pitfall "Base<T>::f() 会关掉虚调用"
    写法 ③ 是**限定**调用，限定名调用虚函数不做动态派发（[[class.virtual]]）。若 `g` 是虚函数而派生类覆盖了它，`Base<T>::g()` 调用的是基类版本，`this->g()` 才是虚调用：

    ```cpp run ok
    #include <cstdio>
    template<class T> struct Base { virtual void hook() { std::puts("Base::hook"); } };
    template<class T> struct D : Base<T> {
        void hook() override { std::puts("D::hook"); }
        void call() { this->hook(); Base<T>::hook(); }
    };
    int main() { D<int> d; d.call(); }   // D::hook，然后 Base::hook
    ```
    所以通用的建议是 `this->`，而不是 `Base<T>::`。

### 为什么 MSVC 历史上不一样

MSVC 在很长时间里不实现两阶段查找：它把模板体保存为**记号流**，到实例化时才解析与查找。这意味着：

- 依赖基类的成员可以直接无限定使用（实例化时基类已知，自然能找到）；
- 缺少 `typename`、`template` 的代码照样能编译（实例化时已知 `T::x` 是什么）；
- 定义之后才声明的函数，即使不是通过 ADL，也会被找到（实例化时它们已经声明）；
- 模板里的语法错误、非依赖错误，只要模板从未被实例化就不报。

这种模型对用户很"宽容"，但它给出的含义与标准不同（`silent_rebinding.cpp` 中它会调用 `Base<T>::g`），而且同一份代码在 GCC/Clang 上无法编译。微软从 VS 2017 开始在 `/permissive-` 一致性模式下实现两阶段查找，`/Zc:twoPhase-` 可以关掉它以兼容旧代码。

Clang 为兼容 MSVC 提供了 `-fdelayed-template-parsing`：函数模板体推迟到翻译单元末尾才解析。用它编译上面那个"`g()` 找不到"的例子，Clang 不再报错——这正是旧 MSVC 的行为，也是不符合标准的行为（Clang 会提示该选项在 C++20 之后已弃用）。

## 实例化点（[temp.point]）

实例化点是一个**程序点**：特化中依赖名的 ADL 从这里出发，可达性（[[module.reach]]）也从这里判断。规则按实体种类分为函数类与类类，二者的位置恰好相反。

### 函数类特化：紧随其后（¶1）

¶1 对函数模板特化、成员函数模板特化、类模板的成员函数或静态数据成员的特化：

- 如果 ¶1.1 它是因为在**另一个模板特化中被引用**而隐式实例化的，并且 ¶1.2 引用它的语境依赖于模板形参，那么它的 POI 就是**外围特化的 POI**；
- 否则，它的 POI **紧随**引用它的那个命名空间作用域声明或定义**之后**。

"命名空间作用域声明"很重要：在函数体里调用 `f(x)`，POI 不在调用处，而在包含这个调用的**整个**命名空间作用域函数定义之后：

```cpp
namespace N { struct S { }; }
template<class T> void call(T t) { touch(t); }

void use() {
    call(N::S{});       // call<N::S> 的 POI：紧随 use 的定义之后（见下）
}
// ← call<N::S> 的 POI 在这里
namespace N { void touch(S) { } }
// ← 翻译单元末尾：也是 POI（¶7）
```

为什么是"之后"？函数模板特化可能递归地引用自己，或被包含它的函数间接引用；把 POI 放在整个声明之后，可以保证该声明本身（例如 `use`）在实例化语境中已经可见。

嵌套情形：`call<N::S>` 内部若又调用了 `helper(t)`（依赖语境），`helper<N::S>` 的 POI 就是 `call<N::S>` 的 POI，而不是 `call` 定义内的某个位置——模板定义内部不存在有意义的"命名空间作用域声明"可以作为参照。

### 默认实参与 noexcept 说明符（¶2–¶3）

¶2 函数模板或类模板成员函数的调用用到默认实参的定义时，默认实参的 POI 就是该函数特化的 POI。

¶3 函数模板特化或类模板成员函数特化的 *noexcept-specifier*：若因另一个模板特化需要而隐式实例化（¶3.1），且需要它的语境依赖于模板形参（¶3.2），POI 是需要它的那个特化的 POI；否则紧随需要它的命名空间作用域声明之后。

这与 [[temp.res.general#7]] 呼应：默认实参与 noexcept 说明符被视为"定义"，按需单独实例化，因此需要自己的 POI。

### 类类特化：紧挨其前（¶4）

¶4 对类模板特化、类成员模板特化、类模板的类成员的特化：

- 如果 ¶4.1 它是因为在另一个模板特化中被引用而隐式实例化的，¶4.2 引用语境依赖于模板形参，并且 ¶4.3 它在外围模板实例化之前尚未被实例化，那么 POI **紧挨在**外围模板 POI **之前**；
- 否则，POI **紧挨在**引用它的命名空间作用域声明或定义**之前**。

为什么类在"之前"？因为引用它的声明需要一个**完整的类型**：`int x = sizeof(H<A>);` 在解析这个声明时就得知道 `H<A>` 的布局，类模板特化必须在这个声明开始之前就"已经存在"。函数则不同，声明中引用一个函数只需要它的声明，定义可以稍后再给。

```cpp error
namespace N { struct A { }; }
template<class T> struct H { char buf[probe(T{})]; };   // probe 依赖：ADL

int x = sizeof(H<N::A>);    // H<N::A> 的 POI 紧挨在这个声明之前：probe 尚未声明

namespace N { constexpr int probe(A) { return 4; } }
```

类模板特化在一个 TU 中**至多一个** POI（¶7），所以这里没有"翻译单元末尾"可以补救：实例化在 `x` 之前进行，`probe` 不可见，程序非良构。若把 `N::probe` 的声明移到 `x` 之前，就正常了。

### 虚函数与显式实例化（¶5–¶6）

¶5 隐式实例化的虚函数，POI 紧随其外围类模板特化的 POI 之后。原因：虚函数要放进虚表，而虚表在类被实例化时就需要（实现上常常在类实例化时就实例化所有虚函数，[[temp.inst]] 允许这样做）。

¶6 显式实例化定义是它所指定的特化的一个实例化点。

### 多个实例化点与 IFNDR（¶7）

¶7 是本节最重要的一段。函数模板、成员函数模板、类模板的成员函数或静态数据成员的特化，在一个 TU 内可以有**多个** POI。除了上面描述的那些之外：

- ¶7.1 若特化在翻译单元 *declaration-seq* 中（私有模块片段之前）有 POI，则**翻译单元的 *declaration-seq* 之后**那一点也是它的 POI；
- ¶7.2 若特化在私有模块片段中有 POI，则**翻译单元末尾**也是它的 POI。

类模板特化在一个 TU 内至多一个 POI。任何模板的特化都可以在**多个 TU** 中有 POI。

!!! std
    If two different points of instantiation give a template specialization different meanings according to the one-definition rule, the program is ill-formed, no diagnostic required.

    两个不同的 POI 按 ODR 给出不同的含义 → {{ifndr}}。

为什么要把翻译单元末尾也算作 POI？这是为了让编译器可以**把函数模板的实例化推迟到 TU 末尾**统一处理——Clang 和 GCC 实际上就是这么做的（实例化是昂贵的，集中处理有利于去重与性能）。为了让这种实现与"紧随声明之后"的规则不冲突，标准干脆规定两个点都是 POI，并要求它们含义相同；不同则 IFNDR。

于是，下面这段程序：

```cpp ifndr title="two_pois.cpp"
#include <cstdio>
namespace N { struct S { }; }
template<class T> int g(T t) { return h(t); }

int a = g(N::S{});          // POI ①：紧随此声明之后，此时 N::h 未声明 → 非良构
                            // POI ②：TU 末尾，此时 N::h 已声明 → 调用 N::h

namespace N { int h(S) { return 42; } }
int main() { std::printf("%d\n", a); }
```

在 POI ① 处 ADL 找不到 `h`（程序非良构），在 POI ② 处找到 `N::h`。两个 POI 给出不同含义，IFNDR。实测 Clang 接受这个程序并输出 `42`——它在 TU 末尾才实例化 `g<N::S>`。

同样的机制可以让"加一个重载"在不同实现上得到完全不同的结果：

```cpp ifndr
namespace N { struct S { }; }
template<class T> void call(T t) { touch(t); }
namespace N { void touch(S) { } }
void use() { call(N::S{}); }                 // POI ①：只有 touch(S)，调用它
namespace N { void touch(const S&) { } }     // POI ②（TU 末尾）：两个 touch，二义
```

按 POI ① 程序良构；按 POI ② 调用二义。IFNDR。Clang 在 TU 末尾实例化，于是报"调用 touch 有二义"。

!!! impl "Clang 并不总是推迟"
    Clang 对普通函数模板推迟到 TU 末尾实例化，但对 **constexpr 函数模板**会在用到时立即实例化（常量求值可能需要它的定义）。于是把上面 `two_pois.cpp` 中的 `g` 改成 `constexpr`，Clang 就会在 `int a = g(...)` 处报 `h` 未声明。两种行为都是符合标准的——程序本来就是 IFNDR。

"多个 TU 中的 POI"同样适用：同一个特化 `g<N::S>` 在 TU 1 和 TU 2 中实例化，若两处看到的 `h` 不同，就违反了 ODR 的"处处一致"要求（[[basic.def.odr#16]] 一族条款），同样 IFNDR，链接器一般随便保留一份。

!!! lawyer "显式特化的声明晚于使用"
    另一条相关但不同的规则在 [[temp.expl.spec#7]]：显式特化的声明必须在每个会引起隐式实例化的使用之前可达，否则 IFNDR。
    ```cpp error
    template<class T> void show(T) { }
    void use() { show(1); }                 // 隐式实例化 show<int>
    template<> void show<int>(int) { }      // 太晚了
    ```
    这个特定情形 Clang 能诊断（"在实例化之后显式特化"）；跨 TU 的版本则基本无法诊断。

### 展开语句（¶8）{{c++26}}

¶8 *expansion-statement*（[[stmt.expand]]）的复合语句的 POI 是其外围模板化实体的 POI（若有）；否则紧随包含该展开语句的命名空间作用域声明或定义之后。展开语句在非模板函数中也会"实例化"它的循环体，所以需要自己的 POI 规则；规则与函数类特化一致。

## 候选函数（[temp.dep.candidate]）

### 看全所有 TU 的假想查找（¶1）

¶1 对一个依赖调用，假如它的依赖名查找考虑**所有翻译单元**中、在关联命名空间里引入的所有**外部链接**函数声明，而不仅仅是模板定义语境和实例化语境中找到的那些（[[basic.lookup.argdep]]）——如果这样会使调用**非良构**，或找到**更好的匹配**，则程序 {{ifndr}}。

这条规则把 ADL 的"语境依赖性"约束住了：依赖调用的结果，不应该取决于某个 TU 碰巧包含了哪些头文件。

```cpp title="h.h"
namespace N { struct S { }; void g(S, long); }
template<class T> void call(T t) { g(t, 0); }   // 依赖调用
```

```cpp title="a.cpp"
#include "h.h"
void use() { call(N::S{}); }    // 这里只看得到 g(S, long)
```

```cpp ifndr title="b.cpp"
#include "h.h"
namespace N { void g(S, int) { } }   // 外部链接、在关联命名空间 N 中、对 g(t, 0) 是更好的匹配
```

`a.cpp` 中 `call<N::S>` 选中 `g(S, long)`；但如果看全所有 TU，`b.cpp` 中的 `g(S, int)` 对实参 `0` 是精确匹配，更好。按 ¶1 程序 IFNDR。这类错误编译器和链接器都不可能可靠地发现，只能靠约定避免：**一个类型的所有重载应该和类型本身一起声明**（同一头文件、同一模块接口）。

### 模块中的例子（¶2–¶5）

后四段都是例子，展示模块如何影响依赖调用的查找。读懂它们需要 [[module.context]] 中实例化语境的定义：对于在模块 M 的接口单元中定义、在别处被实例化的模板，实例化语境除了 POI 之外，还包括 **M 的主模块接口单元末尾**那一点（[[module.context#3]]）；ADL 在实例化语境中查找时，忽略来自其他 TU、附属于全局模块、且被丢弃或具有内部链接的声明（[[basic.lookup.argdep#4]]）。

**例 1（¶2）：定义语境的 ADL**

```cpp title="M1 的模块接口单元"
module;
#include "X.h"        // namespace Q { struct X { }; }
#include "G.h"        // namespace Q { void g_impl(X, X); }
export module M1;
export template<typename T>
void g(T t) {
    g_impl(t, Q::X{ });   // 定义语境中的 ADL 找到 Q::g_impl，于是 g_impl 不被丢弃
}
```

```cpp ok title="M2 的模块接口单元"
module;
#include "X.h"
export module M2;
import M1;
void h(Q::X x) {
    g(x);                 // OK
}
```

全局模块片段（`module;` 之后）里的声明，如果没有被模块单元"用到"，会被**丢弃**（[[module.global.frag]]），对导入者不可见。`g_impl` 在 `g` 的定义中被 ADL 找到（实参 `Q::X{}` 不依赖，关联命名空间 `Q` 在定义处就确定），这算"用到"了，所以它被保留下来，`M2` 中实例化 `g<Q::X>` 时可以调用它。

**例 2（¶3）：只能经由实例化语境的 ADL 找到**

```cpp title="Std 的模块接口单元"
export module Std;
export template<typename Iter>
void indirect_swap(Iter lhs, Iter rhs) {
    swap(*lhs, *rhs);     // 无限定查找找不到 swap，只能靠 ADL
}
```

```cpp ok title="M 的模块接口单元"
export module M;
import Std;

struct S { /* ... */ };
void swap(S&, S&);        // #1

void f(S* p, S* q) {
    indirect_swap(p, q);  // 经由实例化语境中的 ADL 找到 #1
}
```

`#1` 没有导出，`Std` 也看不见 `M`，但 `indirect_swap<S*>` 的 POI 在 `M` 中，ADL 从 POI 出发找到了 `swap(S&, S&)`。这正是"定制点"在模块世界里继续工作的方式。本机 Clang 23 编译并运行了这个例子的可执行版本，行为符合预期。

**例 3（¶4）：运算符**

```cpp title="X.h"
struct X { /* ... */ };
X operator+(X, X);
```

```cpp title="F 的模块接口单元"
export module F;
export template<typename T>
void f(T t) {
    t + t;
}
```

```cpp ok title="M 的模块接口单元"
module;
#include "X.h"
export module M;
import F;
void g(X x) {
    f(x);       // OK：实例化 F 中的 f，operator+ 在实例化语境中可见
}
```

运算符表达式 `t + t` 的非成员候选也按依赖调用处理（[[temp.dep.general#2]] 首句"可能作为运算符的非成员候选形成"），所以同样适用实例化语境中的 ADL。`operator+` 在 `M` 的全局模块片段里，被 `g` 中的 `f(x)` 间接用到。

**例 4（¶5）：被丢弃的声明与头文件单元**

这个例子最复杂，它对比了 `#include` 普通头文件与导入头文件单元：

- 模块 `A` 的模板 `f` 调用 `cat(t, t)`（#1）和 `dog(t, t)`（#2）；`B` 的 `g` 调用 `f`；`C1` 的全局模块片段 `#include "foo.h"`（`struct foo { friend int cat(foo, foo); }; int dog(foo, foo);`），`C1` 的 `h` 调用 `g(foo{}, t)`。
- 在另一个 TU 中 `import C1; h(0);`：**错误**，`#2` 处找不到 `dog`。因为 `dog` 在 `C1` 中没有被用到，被丢弃了；ADL 在实例化语境中查找时忽略"来自其他 TU、附属全局模块、被丢弃"的声明。`cat` 则没问题——它是 `foo` 的隐藏友元，按 [[basic.lookup.argdep#4]] ¶4.2，"关联类定义可达时其友元"的规则找到。
- 把 `foo.h` 换成**可导入头文件** `bar.h`（`#include` 被替换为导入头文件单元），`dog` 不会被丢弃，它在 `C2` 的模块接口单元末尾可见，而那一点属于实例化语境（[[module.context#3]]）——于是 `j(0)` OK。

!!! impl "Clang 对\"丢弃\"的实现"
    截至写作时，本机 Clang 23 对例 4 的错误情形（`h(0)` 找不到 `dog`）并不报错——它没有完整实现全局模块片段中声明的丢弃规则。标准规定这里非良构，依赖这种宽松行为的代码不可移植。

## 实现视角

!!! impl "实例化的时机与 POI"
    - **Clang**：遇到函数模板特化的使用时，把它加入"待实例化"队列，在 TU 末尾统一实例化（constexpr 函数、需要推导返回类型的函数等例外，会立即实例化）。所以 Clang 实际上使用的是 ¶7.1 的"TU 末尾"POI。类模板特化在需要完整类型时立即实例化。
    - **GCC** 的策略类似：函数模板体的实例化通常推迟到 TU 末尾。
    - 对于 ADL 在实例化语境中的查找，两者都把 POI 处"可见"的声明纳入；由于函数模板实际在 TU 末尾实例化，它们看到的是整个 TU 的声明——这正是 ¶7 让 TU 末尾成为合法 POI 的意义。
    - **跨 TU**：每个 TU 各自实例化，生成弱符号（COMDAT/linkonce_odr），链接器任选其一。不同 TU 的实例化若不一致，链接器不会发现。

## 历史与演进

!!! history "历史与演进"
    | 版本 | 变化 |
    |---|---|
    | C++98 | 已有 POI 规则（函数类紧随其后、类类紧挨其前）、依赖调用在 POI 处做 ADL、¶1 式的"看全所有 TU"条款（早期标准把它规定为未定义行为，后来改为 IFNDR）；`export` 模板曾让"实例化语境"跨 TU 变得极其复杂（后于 C++11 移除） |
    | C++11 前后 | 通过核心语言缺陷报告承认"TU 末尾也是 POI"，使实现推迟实例化的做法合规；随 noexcept 的引入，后续缺陷报告为 noexcept 说明符规定了单独的 POI |
    | C++20 | 模块：引入**实例化语境**（[[module.context]]），POI 之外加入模块接口单元末尾等点；私有模块片段（¶7.2） |
    | C++23 | [[P1787R6]] 把"实例化语境中的 ADL"移到 [[basic.lookup.argdep]] 统一表述 |
    | C++26 | 展开语句的 POI（¶8）；常量求值中的隐式实例化使用求值语境（[[module.context#6]]，与反射的 `define_aggregate` 相关） |

## 陷阱

!!! pitfall "\"晚声明的重载也会被找到\"——只有经由 ADL"
    模板定义之后才声明的函数，只有当实参类型的关联命名空间包含它时才可能被找到。基本类型（`int`、`double`、指针到基本类型）没有关联命名空间，晚声明的重载对它们永远不可见。

!!! pitfall "头文件顺序改变程序含义"
    依赖 POI 处可见性的代码（自定义点在模板实例化之后才声明），在 Clang/GCC 上因为 TU 末尾实例化而"碰巧"能工作，换一种实例化策略（或者把函数改成 `constexpr`）就失败。正确做法：在第一次使用之前声明所有重载与特化。

!!! pitfall "依赖基类成员的静默误绑定"
    依赖基类中的成员被无限定使用时，若外层恰有同名实体，代码能编译但调用的是外层实体（`silent_rebinding.cpp`）。习惯性地写 `this->` 可以避免。

## 思考题

!!! question "思考题 1"
    ```cpp
    #include <vector>
    template<class T> void print_all(const std::vector<T>& v) { for (auto& x : v) print(x); }
    struct Point { int x, y; };
    void print(const Point&);
    int main() { print_all(std::vector<Point>{}); }
    ```
    `print(x)` 能找到 `::print(const Point&)` 吗？如果把 `Point` 换成 `int`、`print` 换成 `void print(int);` 呢？

<details markdown="1">
<summary>答案</summary>

`Point` 的关联命名空间是全局命名空间。`print(x)` 是依赖调用，实例化语境中的 ADL 在全局命名空间中找到 `print(const Point&)`（它在 POI 之前声明），所以 OK。

换成 `int` 后，`int` 没有关联命名空间，ADL 什么也不找；普通无限定查找只在模板定义处进行，而 `print(int)` 在定义之后才声明，找不到——非良构。（`std::vector<int>` 的关联命名空间 `std` 与此无关：`print` 的实参是 `int`，不是 vector。）
</details>

!!! question "思考题 2"
    为什么类模板特化在一个 TU 中"至多一个 POI"，而函数模板特化可以有多个？

<details markdown="1">
<summary>答案</summary>

类模板特化一旦实例化，它就成为一个完整类型，后续代码依赖它的布局、成员集合（`sizeof`、成员访问、继承……）。如果允许它在 TU 末尾"重新实例化"，之前基于第一次实例化做出的所有判断都可能失效，这在实现上不可行，在语义上也无意义。函数模板特化的定义只影响生成的代码，不影响之前声明的类型检查，所以可以推迟到 TU 末尾再实例化——标准为此把 TU 末尾也算作 POI，并要求与"紧随声明之后"的 POI 含义一致。
</details>

!!! question "思考题 3"
    `template<class T> struct D : Base<T> { void f() { g(*this); } };` 中，`g` 是依赖名吗？如果 `Base<T>` 有成员函数 `g`，实例化时会调用它吗？

<details markdown="1">
<summary>答案</summary>

`*this` 的类型是 `D<T>`，类型依赖，所以 `g(*this)` 是依赖调用，`g` 是依赖名。但依赖调用的查找 = 定义处的无限定查找 ∪ ADL。定义处的无限定查找不搜索依赖基类，找不到 `Base<T>::g`；实例化时也只追加 ADL，而 ADL 只找命名空间作用域函数（和关联类的友元），永远不会找到类成员函数。所以不会调用 `Base<T>::g`——要么找到某个命名空间中的 `g`，要么非良构。要调用成员，写 `this->g(*this)`。
</details>

## 小结

| 规则 | 出处 | 要点 |
|---|---|---|
| 依赖调用的普通查找 | [[temp.res.general#1]] | 只在定义处 |
| 依赖调用的 ADL | [[basic.lookup.argdep#4]] | 定义处 + 实例化语境中的每一点 |
| 函数类特化的 POI | ¶1、¶2、¶3、¶5 | 紧随引用它的命名空间作用域声明之后；嵌套时继承外围 POI |
| 类类特化的 POI | ¶4 | 紧挨在引用它的声明之前；一个 TU 至多一个 |
| TU 末尾 | ¶7 | 函数类特化的额外 POI，允许推迟实例化 |
| 多个 POI 含义不同 | ¶7 | {{ifndr}}（含跨 TU） |
| 看全所有 TU 会更好/会出错 | [temp.dep.candidate] ¶1 | {{ifndr}} |
| 模块 | [[module.context]] | 实例化语境包含模块接口单元末尾；被丢弃的 GMF 声明不参与 |
