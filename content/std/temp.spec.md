---
title: 模板实例化与特化
summary: 第 13.9 节的总纲：什么叫"实例化"、什么叫"特化"，隐式实例化/显式实例化/显式特化三种途径如何产生同一个特化，它们之间的"至多一次"与可达性约束，显式实例化与显式特化豁免访问检查，以及每个特化各有一份静态成员。
status: done
covers: temp.spec.general
papers: P0692R1
related: temp.inst, temp.explicit, temp.expl.spec, temp.spec.partial, temp.fct.spec, temp.point, basic.def.odr
tags: 模板, 实例化, 特化, 访问控制
updated: 2026-10-17
---

模板本身不是类、不是函数、也不是变量——它是**生成**这些实体的配方。把模板实参代入、得到一个具体实体的过程，标准称为[[g:template-instantiation|**模板实例化**]]（template instantiation）；得到的具体实体（或者程序员手写的替代品）叫[[g:specialization|**特化**]]（specialization）。

第 13.9 节 [[temp.spec]] 讲的就是"一个特化从哪里来"。答案有三种：

| 途径 | 语法 | 谁写定义 | 详见 |
|---|---|---|---|
| **隐式实例化**（implicit instantiation） | 无，使用即触发 | 编译器按模板生成 | [[temp.inst]] |
| **显式实例化**（explicit instantiation） | `template class X<int>;` / `extern template ...;` | 编译器按模板生成，但由程序员指定**何时何地** | [[temp.explicit]] |
| **显式特化**（explicit specialization） | `template<> class X<int> { ... };` | 程序员手写，**完全替换**模板 | [[temp.expl.spec]] |

前两种都是"实例化"——定义来自模板；第三种不是实例化，定义来自程序员。三者都产生"特化"。另外还有**部分特化**（partial specialization，[[temp.spec.partial]]），它本身仍是模板，只是为一族实参提供替代的模板定义，最终还要经过实例化才得到特化。

本页是 13.9 的总述（[[temp.spec.general]]），定义术语并给出几条贯穿三种途径的约束。

## 术语：实例化与"被实例化的 X"（¶1–¶2）

¶1 实例化一个函数、变量、类、类模板的成员或成员模板的行为，叫做**模板实例化**。

注意列表里有"类模板的成员"：类模板 `X<T>` 的成员函数 `X<T>::f` 本身**不是**模板（它没有自己的模板形参列表），但它是**模板化实体**（templated entity，[[temp.pre]]），同样要经过实例化才能得到 `X<int>::f` 的定义。这就是为什么后面的规则总在说"函数模板、成员函数、静态数据成员……"。

¶2 给出一组命名，后文会反复用到：

| 从什么实例化 | 得到 |
|---|---|
| 函数模板 | instantiated function（被实例化的函数） |
| 类模板 | instantiated class |
| 类模板的成员函数 / 成员类 / 成员枚举 / 静态数据成员的**成员定义** | instantiated member function / member class / member enumeration / static data member |
| 成员函数模板 | instantiated member function |
| 成员类模板 | instantiated member class |
| 变量模板 | instantiated variable |
| 静态数据成员模板 | instantiated static data member |

这些名字没有额外的语义，只是让后文能精确地说"被实例化的成员函数"而不是笼统的"特化"。

## 显式特化的声明形式（¶3）

¶3 可以为函数模板、变量模板、类模板、类模板的成员、成员模板声明显式特化；显式特化声明以 `template<>` 开头。对变量模板、类模板、类模板的成员、类成员模板，被特化的变量或类必须用 *simple-template-id*（`A<double>` 这样带尖括号的形式）写出；对函数模板，**可以**用 *template-id*，也可以只写函数名，让实参从函数类型推导出来（[[temp.deduct.decl]]）。

```cpp run ok title="spec_forms.cpp"
template<class T = int> struct A {
    static int x;
};
template<class U> void g(U) { }

template<> struct A<double> { };   // T == double
template<> struct A<> { };         // T == int：默认模板实参照样生效
template<> void g(char) { }        // U == char：从形参类型推导
template<> void g<int>(int) { }    // U == int：显式写出
template<> int A<char>::x = 0;     // 类模板成员的显式特化：A<char>::x

template<class T = int> struct B {
    static int x;
};
template<> int B<>::x = 1;         // B<int>::x
```

`A<>` 这行值得停一下：空尖括号仍然是 *simple-template-id*，默认实参 `int` 补上后它就是 `A<int>`。类模板特化**必须**有尖括号，`template<> struct A { };` 不合法——那会被当作重新定义 `A`。

函数模板可以省略 `<...>`，是因为函数有类型可以拿来推导；类没有"类型签名"可推，所以不行。

## 特化 = 实例化出来的 + 显式特化的（¶4）

¶4 一个被实例化的模板特化，可以是对给定实参列表的隐式实例化（[[temp.inst]]），也可以是显式实例化（[[temp.explicit]]）。**特化**（specialization）是从模板化实体实例化出来的、或作为其显式特化（[[temp.expl.spec]]）的类、变量、函数或类成员。

换句话说，"`X<int>` 是 `X` 的一个特化"这句话不关心它是怎么来的。程序里每个 `X<int>` 都指同一个实体——只是它的**定义**可能来自主模板、某个部分特化、或程序员手写的显式特化。哪一个，由 [[temp.spec.partial.match]] 和本节的可达性规则决定。

!!! note "\"特化\"一词的两种用法"
    日常说"写一个特化"通常指**显式特化**（`template<>`）。标准里的"特化"则是一个更宽的概念：`std::vector<int>` 就是 `std::vector` 的一个特化，哪怕没有人为它写过 `template<>`。读标准时看到 "specialization" 要按宽义理解；看到 "explicit specialization" 才是狭义。

## 每组实参：至多一个定义（¶5）

¶5 对给定的模板和给定的一组模板实参：

- ¶5.1 **显式实例化定义**在整个程序中至多出现一次；
- ¶5.2 **显式特化**在整个程序中至多定义一次（按 [[basic.def.odr]]）；
- ¶5.3 显式实例化与显式特化的声明不能同时出现，**除非**显式特化从显式实例化处可达。若两者互不可达，不要求诊断。

¶5.3 的直觉：显式实例化说"按主模板生成定义"，显式特化说"不要用主模板，用我这份"——两者矛盾。唯一的协调方式是让显式实例化"看见"显式特化，此时按 [[temp.explicit#7]]，显式实例化**无效果**。反过来（先显式实例化、后显式特化）就是实打实的冲突：

```cpp error
template<class T> struct S { void f() {} };
template struct S<int>;          // 显式实例化定义：按主模板生成 S<int>
template<> struct S<int> { };    // error: 显式特化出现在实例化之后
```

```cpp ok
template<class T> struct S { void f() {} };
template<> struct S<int> { };    // 显式特化
template struct S<int>;          // OK：特化可达，此显式实例化无效果（Clang 会给出警告）
```

两者分处不同翻译单元、互相不可达时，编译器看不到冲突，¶5.3 只能是 {{ifndr}}。

!!! lawyer "¶5.1 是\"必须诊断\"吗？"
    ¶5.1 本身没有写 "no diagnostic required"，所以同一 TU 里重复的显式实例化定义编译器会报错（Clang："duplicate explicit instantiation"）。但跨 TU 的重复，主流实现把显式实例化出来的定义按"可合并"的弱符号输出（与内联函数、隐式实例化相同），链接器不会报重复定义。实践中跨 TU 违反 ¶5.1 通常不会被发现——不要依赖这一点。

¶5.2 只是重申 ODR：显式特化是普通的（非模板）实体定义，例如函数模板的显式特化是一个普通函数，**不是** inline 的（除非声明为 inline，见 [[temp.expl.spec#12]]），放在头文件里被多个 TU 包含就会违反 ODR。这是一个极常见的链接错误来源，见 [[temp.expl.spec]] 的陷阱。

## 访问检查豁免（¶6）

¶6 显式实例化或显式特化的**声明**中的名字不受通常的访问检查约束——但出现在**函数体、默认实参、*base-clause*、*member-specification*、*enumerator-list*、静态数据成员或变量模板的初始化器**中的名字除外。

注 1 说得更直白：模板实参、函数声明符里的名字（形参类型、返回类型、异常说明）可以是平时无法访问的私有类型或对象。

为什么？因为特化经常需要"点名"一个私有类型。比如类 `Widget` 想让 `std::hash` 支持它的私有嵌套类型，或者测试代码要为私有类型特化一个 trait。如果特化声明本身就要受访问控制，就只能把类型改成 public，或者到处写 friend。

```cpp run ok title="access_exempt.cpp"
class Widget {
    struct Impl { int v = 42; };   // 私有
};

template<class T> struct Probe { static int get() { return 0; } };
template<> struct Probe<Widget::Impl> {        // OK：模板实参中的私有名不受检查
    static int get() { return 1; }
};

template<class T> int peek() { return 0; }
template<> int peek<Widget::Impl>() { return 1; } // OK：声明符中的私有名不受检查

int main() { return Probe<int>::get() + peek<int>(); }
```

但函数体照常检查：

```cpp error
class Widget { struct Impl { int v = 42; }; };
template<class T> int peek() { return 0; }
template<> int peek<Widget::Impl>() {
    Widget::Impl i;     // error: 'Impl' is a private member of 'Widget'
    return i.v;
}
```

!!! history "历史与演进"
    显式**实例化**的访问豁免在 C++98 就已存在。显式**特化**（以及部分特化）的豁免是 C++20 由 [[P0692R1]]（Access Checking on Specializations）加入的：此前为私有类型写特化在技术上是非良构的，尽管多数编译器早已放行。

### 著名的"合法偷窃"

显式实例化的访问豁免可以被用来——完全合法地——取得私有成员的指针：

```cpp run ok title="steal.cpp"
#include <cstdio>
class Bank { int balance = 100; };

template<int Bank::* M> struct Thief {
    friend int Bank::* steal() { return M; }   // 每次实例化定义一个友元函数
};
int Bank::* steal();                           // 让 steal 可被普通查找找到

template struct Thief<&Bank::balance>;         // OK：显式实例化中 &Bank::balance 不检查访问

int main() {
    Bank b;
    std::printf("%d\n", b.*steal());           // 100
}
```

模板实参 `&Bank::balance` 出现在显式实例化的声明里，¶6 豁免了它；友元函数 `steal` 把这个成员指针"带出"了模板。这一技巧被用在测试框架和序列化库里，但请理解它绕过的是**封装**，而不是类型系统——行为完全有定义。注意若把 `template struct` 换成隐式实例化（例如 `Thief<&Bank::balance> t;`），`&Bank::balance` 就要受访问检查，程序非良构。

## 每个特化各自一份静态成员（¶7）

¶7 从模板实例化出来的每个类模板特化，都有它**自己的**静态成员副本。

```cpp run ok
template<class T> struct Counter { static int n; };
template<class T> int Counter<T>::n = 0;

int main() {
    Counter<int>::n += 1;
    Counter<long>::n += 5;
    return Counter<int>::n == 1 && Counter<long>::n == 5 ? 0 : 1;
}
```

`Counter<int>` 和 `Counter<long>` 是两个毫无关系的类，`n` 自然也是两个变量。这条规则看似废话，但它堵住了一种误读："静态成员属于模板"。模板不是类，没有成员；只有特化有。函数模板的局部静态变量同理，每个特化一份（[[temp.fct.spec.general#2]]）。

!!! pitfall "\"全局计数器\"写在模板里就不全局了"
    想统计"所有 `Handle<T>` 一共创建了多少个"，把 `static int count` 放进 `Handle<T>` 是错的——每个 `T` 各数各的。把计数器移到一个非模板基类里，或者放在命名空间作用域。

## 通过依赖类型得到函数类型（¶8）

¶8 如果一个函数声明**不是**用函数声明符的语法形式、而是通过依赖类型"获得"了函数类型，程序非良构。

```cpp error
template<class T> struct A {
    static T t;          // T 若是函数类型，这就"变成"了静态成员函数声明
};
typedef int function();
A<function> a;           // error: 会把 A<function>::t 声明为静态成员函数
```

普通代码里 `typedef int F(); F f;` 是合法的函数声明（[[dcl.fct]]），但在模板里允许这样做会让 `static T t;` 这一行的**种类**（数据成员还是成员函数）取决于模板实参——这会破坏类模板的整体结构（成员函数要不要定义？`t` 能不能取地址得到数据成员指针？）。标准干脆禁止。Clang 的诊断是"static data member instantiated with function type"。

## 思考题

!!! question "思考题 1"
    下面的程序良构吗？
    ```cpp
    template<class T> struct S { static const int v = 1; };
    template<> struct S<int>;          // (a)
    S<int>* p;                         // (b)
    int n = S<int>::v;                 // (c)
    ```

<details markdown="1">
<summary>答案</summary>

(a) 声明了显式特化 `S<int>` 但没有定义。(b) 只需要指针，不要求类完整，OK。(c) 需要 `S<int>` 完整；`S<int>` 是一个已声明但未定义的显式特化，按 [[temp.expl.spec#7]]"已声明未定义的显式特化永不隐式实例化"，所以它就是不完整类型，`S<int>::v` 非良构（必须诊断：对不完整类的成员访问）。主模板里那个 `v` 与 `S<int>` 毫无关系。
</details>

!!! question "思考题 2"
    `std::hash` 的特化可以写成 `template<> struct std::hash<Widget::Impl> { ... };`，其中 `Impl` 是 `Widget` 的私有成员。特化里的 `operator()` 的**形参类型**写 `const Widget::Impl&`，函数体里访问 `impl.v`（私有数据成员）。哪些地方会报访问错误？

<details markdown="1">
<summary>答案</summary>

模板实参 `std::hash<Widget::Impl>` 中的 `Widget::Impl`：豁免（C++20 起）。
但 `operator()` 是在显式特化的**类定义**（*member-specification*）里声明的，¶6 把 *member-specification* 排除在豁免之外，所以形参类型里的 `Widget::Impl` 照常检查——报错；函数体里的 `impl.v` 也报错。实际写法是让 `Widget` 把 `std::hash<Widget::Impl>` 声明为友元，或者把 `Impl` 暴露出来。豁免只覆盖"声明特化这一句"本身，而不是特化的整个内容。
</details>

## 小结

| 规则 | 段落 | 后果 |
|---|---|---|
| 实例化 = 从模板生成定义；特化 = 实例化所得或显式特化 | ¶1, ¶4 | 术语 |
| 显式特化以 `template<>` 引入；类/变量须写 *simple-template-id*，函数可推导 | ¶3 | — |
| 显式实例化定义至多一次；显式特化至多定义一次 | ¶5.1–¶5.2 | 非良构 / ODR |
| 显式实例化与显式特化共存，须特化可达 | ¶5.3 | 互不可达时 {{ifndr}} |
| 显式实例化/特化声明中的名字豁免访问检查（函数体、成员规格等除外） | ¶6 | C++20 起含特化 |
| 每个类模板特化各有一份静态成员 | ¶7 | — |
| 依赖类型使声明"变成"函数声明 | ¶8 | {{ill-formed}} |
