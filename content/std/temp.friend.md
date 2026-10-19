---
title: 模板与友元
summary: 友元可以是非模板函数/类、模板特化、整个模板；类模板中的四种友元声明及其含义；友元模板授予所有特化（含部分/显式特化）友元关系；依赖类型的成员作友元；局部类不能声明友元模板；友元不能声明部分特化；友元特化不能带默认实参和 inline/constexpr；带约束的友元必须是定义；经典的模板中 operator<< 问题
status: done
covers: temp.friend
since: c++98
related: class.friend, temp.class, temp.mem, basic.lookup.argdep, dcl.meaning, temp.expl.spec, temp.deduct.type, temp.inst
tags: 模板, 友元, hidden friend, operator<<
updated: 2026-10-18
---

友元的一般规则在 [[class.friend]]；本节处理模板与友元交汇时的问题，两个方向都有：

- 授予者是类模板。`template<class T> class task` 中的友元声明，对每个特化 `task<int>`、`task<char>` 意味着什么？友元声明里提到 `T` 时，指的是一个函数、一族函数，还是一个模板？
- 被授予者是模板。把整个函数模板或类模板声明为友元时，它的哪些特化被覆盖？

本节的规则看起来零碎，但都源自同一个事实：友元声明本身也是一个声明，它可能引入新的函数或模板，也可能指向已存在的特化。语法上的细微差别（有没有 `<>`、有没有 `template<...>`）决定了它是哪一种。

---

## 友元的种类（¶1）

¶1 类或类模板的友元可以是：函数模板或类模板、函数模板或类模板的特化，或者非模板函数或类。标准例子把各种组合放在一起：

```cpp run ok
template<class T> class task;
template<class T> task<T>* preempt(task<T>*);

template<class T> class task {
    friend void next_time();                  // (a) 非模板函数，所有特化共享同一个友元
    friend void process(task<T>*);            // (b) 非模板函数，每个特化一个不同的函数
    friend task<T>* preempt<T>(task<T>*);     // (c) 函数模板的特化：preempt<T>
    template<class C> friend int func(C);     // (d) 函数模板：它的所有特化

    friend class task<int>;                   // (e) 类模板的特化
    template<class P> friend class frd;       // (f) 类模板：它的所有特化
};
int main() { }
```

逐一解读：

| | 声明 | 每个 `task<T>` 的友元是 |
|---|---|---|
| (a) | `friend void next_time();` | 同一个普通函数 `::next_time()` |
| (b) | `friend void process(task<T>*);` | 一个普通函数，类型依 `T` 而定：`task<int>` 的友元是 `void process(task<int>*)`，不是函数模板特化 |
| (c) | `friend task<T>* preempt<T>(task<T>*);` | 函数模板 `preempt` 的特化 `preempt<T>`（一对一） |
| (d) | `template<class C> friend int func(C);` | 函数模板 `func` 的所有特化（多对多） |
| (e) | `friend class task<int>;` | 类模板特化 `task<int>` |
| (f) | `template<class P> friend class frd;` | 类模板 `frd` 的所有特化 |

(b) 与 (c) 的区别是本节最重要的一点，也是下面 `operator<<` 问题的根源：**没有显式模板实参（没有 `<...>`）的非模板友元函数声明，声明的是一个普通函数**，即使它的参数类型依赖于 `T` 也是如此。

## 实例化时友元的可见性（¶2）

¶2 类模板中可以声明友元类、类模板、函数、函数模板。类模板实例化时，它的友元声明参与名字查找的方式，如同它们在该特化的实例化点显式声明过一样。注释补充说，友元声明可以引入属于外围命名空间的实体（[[dcl.meaning]]），这时这些实体附属于（attached to）与类模板相同的模块（[[module.unit]]）。

这里的参与名字查找要与 [[class.friend]] / [[basic.scope.scope]] 的规则结合理解：首次在友元声明中出现的函数名，普通的（非 ADL）查找找不到，只有 ADL 能找到它。这就是 **hidden friend** 的由来。

## 友元模板（¶3–4）

¶3 友元模板可以在类或类模板中声明。友元函数模板可以在类中定义，友元类模板则不能。无论哪种情况，友元类模板或友元函数模板的所有特化都是授予类的友元。

```cpp error
class A {
    template<class T> friend class B;                    // OK: 声明
    template<class T> friend void f(T) { }               // OK: 友元函数模板可以在类内定义
    template<class T> friend class C { };                // error: 友元类模板不能在类内定义
};
```

¶4 模板友元声明规定，该模板的所有特化，无论是隐式实例化的、部分特化的还是显式特化的，都是包含该声明的类的友元。

```cpp run ok
class X {
    template<class T> friend struct A;
    class Y { };                                         // private
};
template<class T> struct A      { X::Y ab; };            // OK: 主模板是友元
template<class T> struct A<T*>  { X::Y ab; };            // OK: 部分特化也是友元
template<>        struct A<int> { X::Y ab; };            // OK: 显式特化也是友元
int main() { A<char> a; A<int*> b; A<int> c; (void)a; (void)b; (void)c; }
```

为什么部分特化和显式特化也算？因为友元关系授予的是模板这个实体，而部分特化、显式特化只是这个模板的不同定义方式。否则，库作者给某个模板写一个部分特化，就会意外失去友元访问权。

## 依赖类型的成员作友元（¶5）

¶5 模板友元声明可以把依赖类型的成员声明为友元，条件是：

- 声明的是函数，或用 *elaborated-type-specifier* 指定的类型；
- 带有以 *simple-template-id* `C`（其模板名指称类模板）结尾的 *nested-name-specifier*；
- 友元声明的模板形参必须能从 `C` 推导（[[temp.deduct.type]]）。

此时，类模板某个特化 `S` 的成员是友元，当且仅当从 `S` 推导 `C` 的模板形参成功，并且把推导出的实参代入友元声明后，得到的声明对应于该特化的那个成员。

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
    template<class T> friend struct A<T>::B;      // A<int>::B 也是友元——即使它不是 A<T>::B 的特化
    template<class T> friend void A<T>::f();      // A<int>::f() 不是友元：返回类型 int 对不上 void
    template<class T> friend void A<T>::D::g();   // error: A<T>::D 不以 simple-template-id 结尾
    template<class T> friend int* A<T*>::h();     // A<int*>::h() 与 A<float*>::h() 都是友元
    template<class T> template<T U>
        friend T A<T>::i();                       // A<T>::i 的所有实例化，以及 A<int>::i 的所有特化
};
```

逐条来看：

- 匹配只看声明的形状，不关心成员来自哪个定义。`A<int>` 是显式特化，它的 `B` 与主模板的 `A<T>::B` 毫无关系，但代入 `T = int` 后 `struct A<int>::B` 与之对应，所以是友元。
- `A<int>::f()` 返回 `int`，代入后的友元声明是 `void A<int>::f()`，不对应，所以不是友元。
- `A<T>::D::g()` 的 *nested-name-specifier* 以 `D`（不是 *simple-template-id*）结尾，所以非良构。要求以 *simple-template-id* 结尾，是为了让从 `S` 推导 `C` 这一步有意义。
- `A<T*>::h()`：推导要求 `S` 形如 `A<X*>`，所以 `A<int*>` 与 `A<float*>` 都匹配（只要 `h` 的声明对应）。

!!! warning "编译器现状"
    截至写作时，Clang 23 不支持 ¶5 这种依赖嵌套名的友元。它对上面每一条（合法的）友元声明给出警告，大意是不支持以依赖的嵌套名说明符声明友元，因此关闭对类 `C` 的访问控制。结果是过度授予：所有人都能访问 `C` 的私有成员。对 `A<T>::D::g()` 这一行也只给出同样的警告，而不是标准要求的错误。依赖这一特性的可移植代码很少，实践中通常改为把整个类模板 `A` 声明为友元。

## 禁令（¶6–8）

¶6 局部类中不能声明友元模板（这与 [[temp.mem#2]] 中局部类不能有成员模板同理）。

¶7 友元声明不能声明部分特化：

```cpp error
template<class T> class A { };
class X {
    template<class T> friend class A<T*>;         // error: 友元不能是部分特化
};
void loc() {
    struct L {
        template<class T> friend void zz(T);      // error: 局部类中的友元模板（¶6）
    };
}
```

想让某个部分特化成为友元，只能把整个模板声明为友元（¶4 保证部分特化也包括在内）。

¶8 当友元声明指向函数模板的特化时，函数参数声明不能带默认实参，也不能使用 `inline`、`constexpr`、`consteval` 说明符。

```cpp error
template<class T> void ff(T);
struct Z { friend void ff<int>(int = 0); };       // error: 指向特化的友元声明不能有默认实参
```

这样规定的理由是，友元特化声明并不定义或声明一个新函数，它只是指向由模板生成（或显式特化）的那个特化。默认实参、`inline`、`constexpr` 都是函数声明的属性，应该在模板本身或显式特化上声明，不能借友元声明追加。

!!! note "编译器现状"
    截至写作时，Clang 23 对 `friend void ff<int>(int = 0);` 报错（给出的理由是带默认实参的友元声明必须是唯一的声明，这也是一条有效的规则），但对 `friend inline void ff<long>(long);` 不报错。按 ¶8 后者也非良构。

## 带约束的友元（¶9）

¶9 共三句：

1. 带 *requires-clause* 的非模板友元声明必须是定义；
2. 如果友元函数模板的约束依赖于外围模板的模板形参，它必须是定义；
3. 这样的受约束友元（函数或函数模板）声明，不与任何其他作用域中的声明声明同一函数（或函数模板）。

```cpp error
template<class T> struct Q {
    friend void k() requires (sizeof(T) > 1);     // error: 带 requires-clause 的非模板友元必须是定义
};
```

为什么必须是定义？非模板友元 `friend void h() requires C<T>` 在每个特化 `R<int>`、`R<char>` 中各实例化一次，约束依赖于 `T`，所以每个特化中的 `h` 都是不同的函数（第 3 句）。如果它只是声明，定义就只能在别处给出，但在别处无法写出与 `R<int>` 中那个 `h` 对应的声明，因为它不与其他作用域中的任何声明对应。所以必须当场定义。

第 3 句还有一个后果：不带约束的 hidden friend 如果不依赖于 `T`，多次实例化会导致重定义；受约束的版本则是每个特化各有各的函数，不会冲突：

```cpp error
template<class T> struct S { friend void g() { } };
S<int> a;
S<char> b;                     // error: g() 被重定义（S<int> 和 S<char> 都定义了同一个 ::g）
```

```cpp run ok
template<class T> struct R {
    friend void h(R) requires (sizeof(T) > 1) { }   // 受约束的友元：每个特化一个独立函数
};
R<int> r1;
R<short> r2;                   // OK: 与 R<int> 中的 h 不是同一个函数
int main() { h(r1); h(r2); }
```

---

## 经典问题：类模板中的 operator<<

现在可以完整解释这个很多人都遇到过的问题：

```cpp
#include <iostream>
template<class T> class Box {
    T v;
public:
    Box(T t) : v(t) { }
    friend std::ostream& operator<<(std::ostream&, const Box&);   // ← 问题所在
};
template<class T>
std::ostream& operator<<(std::ostream& os, const Box<T>& b) { return os << b.v; }

int main() { std::cout << Box<int>(1); }   // 编译通过，链接失败：undefined reference
```

友元声明 `operator<<(std::ostream&, const Box&)` 没有 `<...>`，按 ¶1 的 (b)，它为每个特化声明一个普通函数 `std::ostream& operator<<(std::ostream&, const Box<int>&)`，下面那个函数模板是另一个实体。重载决议时，普通函数与模板特化 `operator<< <int>` 的转换序列相同，非模板优先，于是选中了那个只有声明、没有定义的普通函数，导致链接错误。GCC 对此有专门的警告（`-Wnon-template-friend`），Clang 不警告。

正确的写法有四种，含义各不相同：

```cpp run ok
#include <iostream>
#include <sstream>

// 解法 1：hidden friend——在类内定义非模板友元（最推荐）
template<class T> class Box1 {
    T v;
public:
    Box1(T t) : v(t) { }
    friend std::ostream& operator<<(std::ostream& os, const Box1& b) { return os << b.v; }
};

// 解法 2：友元指向函数模板的特化（一对一）——需要前置声明
template<class T> class Box2;
template<class T> std::ostream& operator<<(std::ostream&, const Box2<T>&);
template<class T> class Box2 {
    T v;
public:
    Box2(T t) : v(t) { }
    friend std::ostream& operator<< <T>(std::ostream&, const Box2&);   // 注意 <T>（或 <>）
};
template<class T> std::ostream& operator<<(std::ostream& os, const Box2<T>& b) { return os << b.v; }

// 解法 3：整个函数模板作友元（多对多：operator<< <char> 也能访问 Box3<int> 的私有成员）
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

（第四种是保留非模板友元，再为每个用到的 `T` 手写非模板定义，几乎没有实用价值。）

| 写法 | 友元是什么 | 优点 | 缺点 |
|---|---|---|---|
| hidden friend（类内定义） | 每个特化一个普通函数 | 简洁；只能经 ADL 找到，不污染重载集；不做模板推导，允许隐式转换 | 函数体在类内 |
| `operator<< <T>` | 函数模板的一个特化 | 一对一授权，最精确 | 需要前置声明类模板与函数模板 |
| `template<class U> friend` | 函数模板的所有特化 | 不需要前置声明 | 授权过宽 |

!!! tip "hidden friend 的额外好处"
    普通查找找不到 hidden friend（[[class.friend]]、[[basic.lookup.argdep]]），只有在实参类型关联到 `Box1<T>` 时才能经 ADL 找到。因此重载集更小，编译更快，错误信息更短；而且它是非模板函数，`std::cout << 1` 这样无关的调用不会去尝试推导它。另外，因为它不是模板，一侧实参可以经过隐式转换（例如从 `T` 隐式构造 `Box1<T>`），函数模板做不到这一点，因为推导不考虑用户定义转换。

---

## 实现视角

!!! impl "实现视角"
    - **hidden friend 的实例化**：类内定义的友元函数是模板化实体，随类模板特化的实例化而声明，其定义要到 odr-use 时才实例化（[[temp.inst]]）。每个特化的 hidden friend 是一个独立的普通函数，按内联函数（类内定义的友元隐式 `inline`）输出为 COMDAT 符号。
    - **¶5 的支持度**：依赖嵌套名的友元（`template<class T> friend void A<T>::f();`）实现复杂，Clang 23 不支持（降级为关闭访问控制并警告）。

## 陷阱

!!! pitfall "常见误解"
    - 误以为 `friend void f(X<T>)` 声明的是函数模板。它为每个特化声明一个普通函数；要指向模板特化必须写 `f<>` 或 `f<T>`，要指向整个模板必须写 `template<...>`。
    - 误以为 hidden friend 不依赖 `T` 也没关系。不依赖 `T` 的类内友元定义（如 `friend void g() {}`）在第二次实例化时就是重定义。
    - 误以为把类模板声明为友元不包括它的部分特化。实际上包括在内（¶4）。
    - 误以为友元特化声明可以加 `inline` 或默认实参。这是不允许的（¶8）。

## 思考题

!!! question "思考题 1"
    下面每种情况下，`Box<int>` 的私有成员能被 `operator<< <char>`（作用于 `Box<char>` 的那个特化）访问吗？

    (a) `friend std::ostream& operator<< <T>(std::ostream&, const Box&);`
    (b) `template<class U> friend std::ostream& operator<<(std::ostream&, const Box<U>&);`

<details markdown="1">
<summary>答案</summary>

(a) 不能。`Box<int>` 的友元只有 `operator<< <int>`（¶1 (c)：特化，一对一）。

(b) 能。`Box<int>` 把整个函数模板声明为友元（¶3），它的所有特化（包括 `operator<< <char>`）都是 `Box<int>` 的友元。如果 `operator<< <char>` 的函数体访问了某个 `Box<int>` 对象的私有成员，这是允许的。
</details>

!!! question "思考题 2"
    `Box1<int>` 有非 explicit 的转换构造函数 `Box1(int)`。下面的 `print(b)` 与 `print(1)` 各能否编译？如果把 `print` 改成在命名空间作用域也有声明的函数模板友元 `template<class U> void print(const Box1<U>&)` 呢？

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

`print(b)` 可以，`print(1)` 不能。hidden friend 只能经 ADL 找到，而实参 `1` 的类型 `int` 没有关联类 `Box1<int>`，所以名字查找根本找不到 `print`（Clang 报告 `print` 是未声明的标识符）；`print(b)` 中 `b` 的关联类就是 `Box1<int>`，ADL 能找到它。这正是 hidden friend 的设计目的：只有实参本身已经是 `Box1` 时它才可见，即使存在从 `int` 的隐式转换，它也不会被意外选中。如果改成函数模板友元并在命名空间作用域另有声明，普通查找能为 `print(1)` 找到它，但模板推导无法从 `int` 推出 `Box1<U>`（推导不考虑转换），调用仍然失败。
</details>

!!! summary "小结"
    - 类模板中的友元声明：不带 `<>` 的函数为每个特化声明一个普通函数；带 `<T>`/`<>` 的指向函数模板的特化；带 `template<...>` 的指向整个模板。
    - 友元模板授予它所有的特化（含部分特化和显式特化）友元关系；友元函数模板可以类内定义，友元类模板不行。
    - 依赖类型的成员可作友元，判定方法是先推导，再看代入后的声明是否对应（Clang 尚不支持）。
    - 几条禁令：局部类中不能有友元模板；友元不能是部分特化；指向特化的友元声明不能有默认实参和 `inline`/`constexpr`/`consteval`。
    - 带约束的友元必须是定义，且每个作用域中各是不同的函数。
    - 模板的 `operator<<`：首选 hidden friend。
