---
title: 模板实例化与特化
summary: 特化从哪里来：隐式实例化、显式实例化、显式特化三种途径；同一组实参至多一个定义，显式特化与显式实例化并存的条件；特化声明中的名字豁免访问检查；每个类模板特化各有一份静态成员。
status: done
covers: temp.spec.general
papers: P0692R1
related: temp.inst, temp.explicit, temp.expl.spec, temp.spec.partial, temp.fct.spec, temp.point, basic.def.odr
tags: 模板, 实例化, 特化, 访问控制
updated: 2026-10-19
---

!!! tldr
    - 把模板实参代入模板、生成具体的类、函数或变量，叫实例化；得到的实体，以及程序员用 `template<>` 手写的替代品，都叫特化。
    - 特化有三个来源：使用时的隐式实例化、`template class X<int>;` 这样的显式实例化、`template<> class X<int> {…};` 这样的显式特化。
    - 同一组实参的显式特化必须在显式实例化之前可见，反过来是错误；分在两个翻译单元时不要求诊断。
    - 显式实例化和显式特化的声明里可以指名私有类型和私有成员，但函数体、类体等部分照常检查访问。
    - 静态成员属于特化而不属于模板：`X<int>::n` 和 `X<long>::n` 是两个变量。

## 三种途径，同一个特化

```cpp run ok
template<class T> struct Box { T v; };

Box<int> a;                         // 隐式实例化：用到时按模板生成
template struct Box<long>;          // 显式实例化：指定在这里生成
template<> struct Box<char> {       // 显式特化：不用模板，用这份定义
  char v[4];
};

int main() { Box<char> c; (void)a; (void)c; }
```

模板本身不是类、函数或变量，而是生成它们的配方。¶1 把代入模板实参、得到一个具体实体的过程叫做**模板实例化**（template instantiation，[[g:template-instantiation]]）。实例化的对象可以是函数、变量、类，也可以是类模板的成员或成员模板。类模板的成员函数 `Box<T>::f` 没有自己的模板形参列表，不是模板，但同样要实例化才能得到 `Box<int>::f` 的定义。

¶4 实例化得到的实体，以及程序员为某组实参写的显式特化，都叫**特化**（specialization，[[g:specialization]]）。上例的 `Box<int>`、`Box<long>`、`Box<char>` 都是 `Box` 的特化，区别只在定义的来源：

| 途径 | 语法 | 定义来自 | 详见 |
|---|---|---|---|
| 隐式实例化 | 无，用到即触发 | 编译器按模板生成 | [[temp.inst]] |
| 显式实例化 | `template struct Box<long>;`<br>`extern template struct Box<long>;` | 编译器按模板生成，位置由程序员指定 | [[temp.explicit]] |
| 显式特化 | `template<> struct Box<char> {…};` | 程序员手写，完全替换模板 | [[temp.expl.spec]] |

部分特化（[[temp.spec.partial]]）不在表中：它本身仍是模板，为一族实参提供另一份模板定义，最终还要实例化。

!!! note "日常用语里的特化"
    日常说写一个特化，通常指 `template<>` 的显式特化。标准里的特化范围更宽，`std::vector<int>` 就是 `std::vector` 的特化，哪怕没有人为它写过 `template<>`。

## 显式特化的写法（¶3）

¶3 显式特化以 `template<>` 开头，可以针对函数模板、变量模板、类模板、类模板的成员和成员模板。类、变量以及类的成员必须用带尖括号的 *simple-template-id* 指出特化的是哪个；函数模板可以省略尖括号，让编译器从函数类型推导实参（[[temp.deduct.decl]]）。

```cpp run ok title="spec_forms.cpp"
template<class T = int> struct A {
  static int x;
};
template<class U> void g(U) { }

template<> struct A<double> { };   // T == double
template<> struct A<> { };         // T == int，默认实参照样生效
template<> void g(char) { }        // U == char，从形参类型推导
template<> void g<int>(int) { }    // U == int，显式写出
template<> int A<char>::x = 0;     // 类模板成员的显式特化

int main() {}
```

`A<>` 也是 *simple-template-id*，补上默认实参后就是 `A<int>`。写成 `template<> struct A { };` 则不合法。函数能省略尖括号，是因为它有类型可以拿来推导，类没有。

## 每组实参至多一个定义（¶5）

¶5 对给定的模板和一组模板实参：

- ¶5.1 显式实例化定义在整个程序中至多出现一次；
- ¶5.2 显式特化至多定义一次，这是 ODR 的要求（[[basic.def.odr]]）；
- ¶5.3 显式实例化与显式特化的声明不能同时出现，除非显式特化从显式实例化处可达（reachable，大致是能看到它的声明，见 [[module.reach]]）。两者互不可达时，不要求诊断。

显式实例化要求按模板生成定义，显式特化要求不用模板，两者矛盾。唯一的协调方式是特化在前：这时显式实例化没有效果（[[temp.explicit#7]]）。

<div class="compare" markdown="1">

```cpp error
template<class T>
struct S { void f() {} };
template struct S<int>;
template<> struct S<int> { };
// error: 实例化之后才特化
```

```cpp ok
template<class T>
struct S { void f() {} };
template<> struct S<int> { };
template struct S<int>;
// OK：实例化没有效果
```

</div>

本机 Clang 23 对右边给出 `-Winstantiation-after-specialization` 警告。两者分在不同翻译单元、互相看不到时，编译器无法发现冲突，所以 ¶5.3 是 {{ifndr}}（非良构、不要求诊断：标准对这样的程序没有任何要求）。

¶5.1 没有写不要求诊断，同一翻译单元里重复的显式实例化定义会被报错。但主流实现把显式实例化的定义输出为可合并的弱符号，跨翻译单元的重复链接器不会报告。

¶5.2 提醒的是一个常见的链接错误：函数模板的显式特化是普通函数，默认不是 inline 的（[[temp.expl.spec]]）。把它的定义写在头文件里、被多个翻译单元包含，就违反 ODR。

## 特化声明豁免访问检查（¶6）

```cpp run ok title="access_exempt.cpp"
class Widget {
  struct Impl { int v = 42; };   // 私有
};

template<class T> struct Probe { static int get() { return 0; } };
template<> struct Probe<Widget::Impl> {   // OK
  static int get() { return 1; }
};

template<class T> int peek() { return 0; }
template<> int peek<Widget::Impl>() {     // OK
  return 1;
}

int main() { return Probe<int>::get() + peek<int>(); }
```

¶6 显式实例化和显式特化的声明中，名字不做通常的访问检查。注 1 指出，模板实参和函数声明符中的名字（形参类型、返回类型、异常说明）都可以是平时无法访问的私有类型或对象。这样，为私有类型特化一个 trait 时，就不必把类型改成 public 或到处写友元。

豁免不包括以下部分：函数体、默认实参、基类列表、类的成员列表（*member-specification*）、枚举项列表，以及静态数据成员和变量模板的初始化器。

```cpp error
class Widget { struct Impl { int v = 42; }; };
template<class T> int peek() { return 0; }
template<> int peek<Widget::Impl>() {
  Widget::Impl i;   // error: 'Impl' is a private member of 'Widget'
  return i.v;
}
```

C++20 之前只有显式实例化有这项豁免；为私有类型写显式特化或部分特化在技术上是非良构的，尽管多数编译器早已放行。[[P0692R1]] 把豁免扩展到了特化。

!!! lawyer "合法地取得私有成员的指针"
    利用显式实例化的豁免，可以取得私有成员的指针，行为完全有定义：

    ```cpp run ok title="steal.cpp"
    #include <cstdio>
    class Bank { int balance = 100; };

    template<int Bank::* M> struct Thief {
      friend int Bank::* steal() { return M; }
    };
    int Bank::* steal();   // 让普通查找能找到 steal

    template struct Thief<&Bank::balance>;   // OK：豁免访问检查

    int main() {
      Bank b;
      std::printf("%d\n", b.*steal());       // 100
    }
    ```

    模板实参 `&Bank::balance` 写在显式实例化里，不检查访问；友元函数 `steal` 把这个成员指针带出模板。改成隐式实例化（`Thief<&Bank::balance> t;`）就要检查访问，本机 Clang 23 报 `'balance' is a private member of 'Bank'`。测试框架和序列化库会用到这个技巧。

## 每个特化各有一份静态成员（¶7）

```cpp run ok
template<class T> struct Counter { static int n; };
template<class T> int Counter<T>::n = 0;

int main() {
  Counter<int>::n += 1;
  Counter<long>::n += 5;
  return Counter<int>::n == 1 && Counter<long>::n == 5 ? 0 : 1;
}
```

¶7 每个从模板实例化出来的类模板特化，都有自己的一份静态成员。`Counter<int>` 和 `Counter<long>` 是两个无关的类，`n` 也是两个变量。模板不是类，没有成员，只有特化有。函数模板里的局部静态变量同理，每个特化一份（[[temp.fct.spec.general#2]]）。

!!! pitfall "模板里的计数器不是全局的"
    想统计所有 `Handle<T>` 一共创建了多少个，把 `static int count` 放进 `Handle<T>` 是错的，每个 `T` 各自计数。计数器应当放在非模板基类或命名空间作用域里。

## 依赖类型不能把声明变成函数声明（¶8）

```cpp error
template<class T> struct A {
  static T t;
};
typedef int function();
A<function> a;   // error: A<function>::t 会成为静态成员函数
```

¶8 函数声明如果不是通过函数声明符的语法，而是通过依赖类型获得了函数类型，程序非良构。普通代码里 `typedef int F(); F f;` 是合法的函数声明（[[dcl.fct]]）。在模板里允许这样做，`static T t;` 声明的是数据成员还是成员函数就取决于模板实参，类模板的结构就无从确定。本机 Clang 23 的诊断是 static data member instantiated with function type。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶2 给实例化出的实体起了一组名字：从函数模板实例化出的函数叫 instantiated function，从类模板实例化出的类叫 instantiated class；类模板的成员函数、成员类、成员枚举、静态数据成员从成员定义实例化后，分别叫 instantiated member function、member class、member enumeration、static data member；成员函数模板、成员类模板、变量模板、静态数据成员模板也各有对应的名称。这些名字没有额外的语义，只是让后文能精确地指称。

</details>

## 思考题

!!! question "思考题 1"
    下面的程序良构吗？
    ```cpp
    template<class T> struct S { static const int v = 1; };
    template<> struct S<int>;   // (a)
    S<int>* p;                  // (b)
    int n = S<int>::v;          // (c)
    ```

<details markdown="1">
<summary>答案</summary>

不良构，错在 (c)。(a) 声明了显式特化 `S<int>`，没有定义。(b) 只需要指针，不要求完整类型。(c) 需要 `S<int>` 完整；按 [[temp.expl.spec#7]]，已声明的显式特化不会被隐式实例化，没有定义它就是不完整类型。主模板里的 `v` 与 `S<int>` 无关。本机 Clang 23 报 incomplete type 'S<int>' named in nested name specifier。
</details>

!!! question "思考题 2"
    `Impl` 是 `Widget` 的私有成员。下面哪些地方会报访问错误？
    ```cpp
    template<> struct std::hash<Widget::Impl> {
      std::size_t operator()(const Widget::Impl& i) const { return i.v; }
    };
    ```

<details markdown="1">
<summary>答案</summary>

模板实参 `std::hash<Widget::Impl>` 中的 `Widget::Impl` 豁免检查。但 `operator()` 在特化的类定义里，属于 *member-specification*，¶6 把它排除在豁免之外，所以形参类型里的 `Widget::Impl` 和函数体里的 `i.v` 都要检查，会报错。豁免只覆盖特化声明本身，不覆盖特化的内容。实际做法是让 `Widget` 把 `std::hash<Widget::Impl>` 声明为友元。
</details>
