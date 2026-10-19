---
title: 模板与友元
summary: 类模板里的友元声明指什么：一个普通函数、模板的一个特化，还是整个模板；友元模板覆盖哪些特化；几条禁令；带约束的友元；为什么模板里的 operator<< 常常链接失败。
status: done
covers: temp.friend
since: c++98
related: class.friend, temp.class, temp.mem, basic.lookup.argdep, dcl.meaning, temp.expl.spec, temp.deduct.type, temp.inst
tags: 模板, 友元, hidden friend, operator<<
updated: 2026-10-19
---

!!! tldr
    - 类模板中的 `friend void f(X<T>)` 没有 `<...>`，它为每个特化声明一个普通函数，不是函数模板的特化。这是模板中 `operator<<` 链接失败的根源。
    - 写成 `f<T>` 或 `f<>` 指函数模板的一个特化，写成 `template<class U> friend ...` 指整个模板的所有特化。
    - 把一个模板声明为友元，它的部分特化和显式特化也都是友元。
    - 友元不能是部分特化，局部类里不能声明友元模板，指向特化的友元声明不能带默认实参和 `inline`、`constexpr`、`consteval`。
    - 带 *requires-clause* 的非模板友元必须是定义；给类模板写运算符，首选类内定义的 hidden friend。

## 一个链接错误

```cpp ifndr
#include <iostream>
template<class T> class Box {
    T v;
public:
    Box(T t) : v(t) { }
    friend std::ostream& operator<<(std::ostream&, const Box&);   // 问题在这里
};
template<class T>
std::ostream& operator<<(std::ostream& os, const Box<T>& b) { return os << b.v; }

int main() { std::cout << Box<int>(1); }   // 编译通过，链接失败：undefined reference
```

这段代码看上去声明了一个友元，又在下面定义了它，可是链接时找不到 `operator<<`。要解释这个现象，需要先弄清类模板里的友元声明到底声明了什么。友元的一般规则在 [[class.friend]]，本节处理模板和友元相遇时的情形。

## 友元的种类（¶1）

¶1 类或类模板的友元可以是函数模板或类模板，可以是函数模板或类模板的特化，也可以是非模板的函数或类。标准把各种组合放进一个例子：

```cpp run ok
template<class T> class task;
template<class T> task<T>* preempt(task<T>*);

template<class T> class task {
    friend void next_time();                  // (a)
    friend void process(task<T>*);            // (b)
    friend task<T>* preempt<T>(task<T>*);     // (c)
    template<class C> friend int func(C);     // (d)

    friend class task<int>;                   // (e)
    template<class P> friend class frd;       // (f)
};
int main() { }
```

| | 每个特化 `task<T>` 的友元是 |
|---|---|
| (a) | 同一个普通函数 `::next_time()` |
| (b) | 一个类型随 `T` 而变的普通函数：`task<int>` 的友元是 `void process(task<int>*)`，它不是函数模板的特化 |
| (c) | 函数模板 `preempt` 的特化 `preempt<T>`，一个特化对一个特化 |
| (d) | 函数模板 `func` 的所有特化 |
| (e) | 类模板特化 `task<int>` |
| (f) | 类模板 `frd` 的所有特化 |

关键在 (b) 和 (c) 的区别：友元函数声明如果没有显式模板实参 `<...>`，声明的就是普通函数，哪怕它的参数类型依赖于 `T`。

回到开头的例子。`friend ... operator<<(std::ostream&, const Box&)` 属于 (b)，它为 `Box<int>` 声明了一个普通函数 `operator<<(std::ostream&, const Box<int>&)`，下面那个函数模板是另一个实体。重载决议时，这个普通函数与模板特化 `operator<< <int>` 的转换序列相同，非模板优先，于是选中了只有声明、没有定义的普通函数。odr-use 了一个没有定义的非 inline 函数，按 [[basic.def.odr]] 程序是 IFNDR，实践中表现为链接错误。GCC 对这种写法有专门的警告 `-Wnon-template-friend`，Clang 不警告。

## 修好 operator<<

```cpp run ok
#include <iostream>
#include <sstream>

// 写法 1：hidden friend，在类内定义
template<class T> class Box1 {
    T v;
public:
    Box1(T t) : v(t) { }
    friend std::ostream& operator<<(std::ostream& os, const Box1& b) { return os << b.v; }
};

// 写法 2：友元指向函数模板的一个特化，需要前置声明
template<class T> class Box2;
template<class T> std::ostream& operator<<(std::ostream&, const Box2<T>&);
template<class T> class Box2 {
    T v;
public:
    Box2(T t) : v(t) { }
    friend std::ostream& operator<< <T>(std::ostream&, const Box2&);   // 注意 <T>，也可写 <>
};
template<class T> std::ostream& operator<<(std::ostream& os, const Box2<T>& b) { return os << b.v; }

// 写法 3：整个函数模板作友元
template<class T> class Box3 {
    T v;
public:
    Box3(T t) : v(t) { }
    template<class U> friend std::ostream& operator<<(std::ostream&, const Box3<U>&);
};
template<class U> std::ostream& operator<<(std::ostream& os, const Box3<U>& b) { return os << b.v; }

int main() {
    std::ostringstream s;
    s << Box1<int>(1) << Box2<int>(2) << Box3<int>(3);
    return s.str() == "123" ? 0 : 1;
}
```

| 写法 | 友元是什么 | 优点 | 缺点 |
|---|---|---|---|
| hidden friend | 每个特化一个普通函数 | 简洁；只能经 ADL 找到；允许隐式转换 | 函数体写在类内 |
| `operator<< <T>` | 函数模板的一个特化 | 一对一授权，最精确 | 要前置声明类模板和函数模板 |
| `template<class U> friend` | 函数模板的所有特化 | 不需要前置声明 | 授权过宽：`operator<< <char>` 也能访问 `Box3<int>` 的私有成员 |

!!! tip "hidden friend"
    第一次在友元声明里出现的函数，普通名字查找找不到，只有实参依赖查找（ADL，按实参类型去关联的类和命名空间里找函数，[[basic.lookup.argdep]]）能找到。类内定义的这种友元叫做 **hidden friend**。它只在实参的类型关联到 `Box1<T>` 时才参与重载决议，重载集更小，错误信息更短。它不是模板，不做推导，所以另一侧的实参可以经过隐式转换。

## 实例化后友元怎样被找到（¶2）

¶2 类模板里可以声明友元类、友元类模板、友元函数和友元函数模板。模板实例化时，名字查找对待它的友元声明，就像这些声明是在该特化的实例化点显式写出的一样。

注 1 补充：友元声明可以引入属于外围命名空间的实体（[[dcl.meaning]]），这时这些实体与类模板附属于同一个模块（[[module.unit]]）。

## 友元模板（¶3–4）

¶3 友元模板可以在类或类模板中声明。友元函数模板可以在类内定义，友元类模板不行。两种情况下，友元模板的所有特化都是授予方的友元。

```cpp error
class A {
    template<class T> friend class B;                    // OK
    template<class T> friend void f(T) { }               // OK：友元函数模板可以类内定义
    template<class T> friend class C { };                // error: 友元类模板不能类内定义
};
```

¶4 模板友元声明使该模板的所有特化都成为友元，无论是隐式实例化的、部分特化的还是显式特化的：

```cpp run ok
class X {
    template<class T> friend struct A;
    class Y { };                                         // private
};
template<class T> struct A      { X::Y ab; };            // OK：主模板
template<class T> struct A<T*>  { X::Y ab; };            // OK：部分特化
template<>        struct A<int> { X::Y ab; };            // OK：显式特化
int main() { A<char> a; A<int*> b; A<int> c; (void)a; (void)b; (void)c; }
```

友元关系授予的是模板这个实体，部分特化和显式特化只是它的另外几种定义。否则，库作者给模板加一个部分特化，就会意外失去访问权。

## 依赖类型的成员作友元（¶5）

¶5 模板友元声明可以把依赖类型的某个成员声明为友元。要求是：声明的是函数，或者用 *elaborated-type-specifier*（如 `struct A<T>::B`）指定的类型；它的限定部分以一个指名类模板的 *simple-template-id*（记作 `C`，如 `A<T>`）结尾；友元声明的模板形参都能从 `C` 推导（[[temp.deduct.type]]）。

对类模板的一个特化 `S`，判断它的成员是不是友元分两步：先从 `S` 推导 `C` 的模板形参；推导成功后，把结果代入友元声明，看得到的声明是否与 `S` 的那个成员对应。

```cpp
template<class T> struct A {
    struct B { };
    void f();
    struct D { void g(); };
    T h();
    template<T U> T i();
};
template<> struct A<int> {
    struct B { };
    int f();
    struct D { void g(); };
    template<int U> int i();
};
template<> struct A<float*> { int* h(); };

class C {
    template<class T> friend struct A<T>::B;      // A<int>::B 也是友元
    template<class T> friend void A<T>::f();      // A<int>::f() 不是友元
    template<class T> friend void A<T>::D::g();   // error: A<T>::D 不以 simple-template-id 结尾
    template<class T> friend int* A<T*>::h();     // A<int*>::h() 和 A<float*>::h() 都是友元
    template<class T> template<T U>
        friend T A<T>::i();                       // A<T>::i 和 A<int>::i 的所有特化
};
```

- `A<int>` 是显式特化，它的 `B` 与主模板的 `A<T>::B` 无关。但代入 `T = int` 后得到 `struct A<int>::B`，与之对应，所以是友元。匹配只看声明的形状。
- `A<int>::f()` 返回 `int`，代入后的声明是 `void A<int>::f()`，对不上，所以不是友元。
- `A<T>::D::g()` 的限定部分以 `D` 结尾，无法从特化 `S` 推导，所以非良构。
- `A<T*>::h()` 要求 `S` 形如 `A<X*>`，`A<int*>` 和 `A<float*>` 都符合。

!!! warning "Clang 不支持 ¶5"
    本机 Clang 23 对上面五条友元声明都只给出 `-Wunsupported-friend` 警告：不支持依赖的嵌套名说明符，因此关闭类 `C` 的访问控制。结果是授权过宽，任何代码都能访问 `C` 的私有成员；`A<T>::D::g()` 那一行也没有报错。所以上面这段代码没有标判定。需要可移植时，改为把整个类模板 `A` 声明为友元。

## 禁令（¶6–8）

¶6 局部类中不能声明友元模板，这与局部类不能有成员模板（[[temp.mem#2]]）一致。¶7 友元声明不能声明部分特化。

```cpp error
template<class T> class A { };
class X {
    template<class T> friend class A<T*>;         // error: 友元不能是部分特化（¶7）
};
void loc() {
    struct L {
        template<class T> friend void zz(T);      // error: 局部类中的友元模板（¶6）
    };
}
```

想让某个部分特化成为友元，只能把整个模板声明为友元，¶4 保证部分特化也包括在内。

¶8 友元声明指向函数模板的特化时，形参不能带默认实参，声明也不能用 `inline`、`constexpr` 或 `consteval`。这样的声明不引入新函数，只是指向由模板生成或显式特化的那个特化；默认实参和这些说明符应该写在模板本身或显式特化上。

```cpp error
template<class T> void ff(T);
struct Z { friend void ff<int>(int = 0); };       // error: 默认实参
```

!!! note "Clang 的情况"
    Clang 23 拒绝上面的代码，但给出的理由是另一条规则：带默认实参的友元声明必须是唯一的声明。它接受 `friend inline void ff<long>(long);`，按 ¶8 这也是非良构的。

## 带约束的友元（¶9）

¶9 有三句：

1. 带 *requires-clause* 的非模板友元声明必须是定义。
2. 友元函数模板的约束如果依赖于外围模板的模板形参，它也必须是定义。
3. 这样的受约束友元，与任何其他作用域中的声明都不是同一个函数或函数模板。

```cpp error
template<class T> struct Q {
    friend void k() requires (sizeof(T) > 1);     // error: 必须是定义
};
```

第 3 句是第 1、2 句的原因。`friend void h(R) requires C<T>` 在 `R<int>`、`R<short>` 中各有一份，约束随 `T` 而变，所以它们是不同的函数。在类外写不出一个与 `R<int>` 中那个 `h` 对应的声明，定义只能当场给出。

第 3 句还意味着受约束的 hidden friend 不会在多次实例化时互相冲突。不带约束、也不依赖 `T` 的类内友元定义则会：

<div class="compare" markdown="1">

```cpp error
template<class T> struct S {
  friend void g() { }
};
S<int> a;
S<char> b;  // error: ::g 重定义
```

```cpp run ok
template<class T> struct R {
  friend void h(R)
    requires (sizeof(T) > 1) { }
};
R<int> r1;
R<short> r2;  // OK：两个不同的 h
int main() { h(r1); h(r2); }
```

</div>

## 思考题

!!! question "思考题 1"
    下面两种写法中，`operator<< <char>` 能访问 `Box<int>` 的私有成员吗？

    (a) `friend std::ostream& operator<< <T>(std::ostream&, const Box&);`
    (b) `template<class U> friend std::ostream& operator<<(std::ostream&, const Box<U>&);`

<details markdown="1">
<summary>答案</summary>

(a) 不能。`Box<int>` 的友元只有 `operator<< <int>`，一个特化对一个特化（¶1 (c)）。

(b) 能。`Box<int>` 把整个函数模板声明为友元（¶3），它的所有特化，包括 `operator<< <char>`，都是 `Box<int>` 的友元。
</details>

!!! question "思考题 2"
    `print(b)` 和 `print(1)` 各能否编译？

    ```cpp
    template<class T> struct Box1 {
        T v;
        Box1(T t) : v(t) {}
        friend void print(const Box1&) {}
    };
    Box1<int> b(0);
    void test() { print(b); print(1); }
    ```

<details markdown="1">
<summary>答案</summary>

`print(b)` 可以，`print(1)` 不行。hidden friend 只能经 ADL 找到。`b` 的关联类就是 `Box1<int>`，ADL 能找到 `print`；实参 `1` 的类型 `int` 没有关联类，名字查找根本找不到 `print`，Clang 报告它是未声明的标识符。即使存在从 `int` 到 `Box1<int>` 的隐式转换，hidden friend 也不会被意外选中。
</details>
