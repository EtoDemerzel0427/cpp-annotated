---
title: 派生类
summary: 怎样声明基类，派生类对象里有哪些基类子对象；多重继承下同一个基类出现多次时会怎样，虚基类如何让它们合而为一。
status: done
covers: class.derived.general, class.mi
related: class.virtual, class.abstract, class.access.base, class.member.lookup, class.base.init, intro.object, conv.ptr, class.pre
tags: 类, 继承, 多重继承, 虚基类
updated: 2026-10-19
---

!!! tldr
    - 派生类对象里嵌着每个基类的一个子对象；派生类到基类的指针转换，就是找到那个子对象。
    - 基类在 *base-clause* 中出现时必须已经是完整类型。子对象在内存中的排列顺序未指定，由 ABI 决定。
    - 同一个类不能两次作为直接基类，但可以多次作为间接基类，这时就有多个同类型子对象，访问它们的成员需要限定路径。
    - 每个非虚基类的每次出现对应一个独立的子对象；同一个虚基类无论出现几次，最派生对象中只有一个。
    - 声明为 `final` 的类不能作为基类。

本页只讲结构：基类怎么声明、对象里有哪些子对象。基类成员如何查找见 [[class.member.lookup]]，能否访问见 [[class.access.base]]，如何初始化见 [[class.base.init]]，虚函数见 [[class.virtual]]。

## 派生类对象里有什么 [class.derived.general]

```cpp
struct Base     { int a, b, c; };
struct Derived  : Base    { int b; };
struct Derived2 : Derived { int c; };
```

¶3 *base-specifier-list*（冒号后面的基类列表）指定了派生类对象所含的**基类子对象**（base class subobject）的类型。上面这个标准例子里，`Derived2` 对象含一个 `Derived` 子对象，后者又含一个 `Base` 子对象。说 `Derived` 是一个 `Base`，在对象模型里的意思就是每个 `Derived` 对象里都有一个完整的 `Base` 对象。

¶2 直接写在 *base-clause* 里的类叫**直接基类**（direct base class）。直接基类，以及基类的直接基类（递归地），都是**基类**；是基类但不是直接基类的叫**间接基类**。上例中 `Base` 是 `Derived2` 的间接基类。

¶2 后半还规定，基类的成员也是派生类的成员。注 2 汇总了由此而来的几条规则：基类成员可以像派生类自己的成员一样在表达式中使用，除非被隐藏或有二义（[[class.member.lookup]]）；`::` 可以显式指名被隐藏的基类成员；派生类指针可以隐式转换为可访问且无二义的基类指针（[[conv.ptr]]），派生类左值可以绑定到这种基类的引用（[[dcl.init.ref]]）；基类的构造函数可以用 using 声明继承（[[namespace.udecl]]）。

### 基类说明符的写法（¶1）

```text
base-specifier:
    attribute-specifier-seq(opt) class-or-decltype
    attribute-specifier-seq(opt) virtual access-specifier(opt) class-or-decltype
    attribute-specifier-seq(opt) access-specifier virtual(opt) class-or-decltype
class-or-decltype:
    nested-name-specifier(opt) type-name
    nested-name-specifier template simple-template-id
    computed-type-specifier
```

`virtual` 和访问说明符（`public`、`protected`、`private`）的顺序任意，`virtual public B` 与 `public virtual B` 相同。*computed-type-specifier* 包括 `decltype(...)`、包索引和 splice 类型说明符，所以可以从 `decltype(某个 lambda)` 派生。开头的属性属于这个 *base-specifier*。

### 基类必须完整（¶2）

¶2 *class-or-decltype* 必须表示一个类类型，而且这个类此时不能还在定义当中或只有声明，也就是必须是完整类型。派生类的布局要容纳整个基类子对象，编译器必须知道基类的大小和成员。基类上的 cv 限定被忽略。

查找基类名字时只看类型（**仅类型查找**，[[basic.lookup]]），同名的变量和函数被忽略。

```cpp title="base-requirements.cpp" error
struct Inc;
struct A : Inc {};              // error: Inc 不完整
struct Self : Self {};          // error: Self 此时尚未定义完
struct X {};
using CX = const X;
struct W : CX {};               // OK: cv 限定被忽略
int B;
struct B {};
struct D : B {};                // OK: 只查找类型，忽略变量 B
```

每个 *base-specifier* 对应一个**直接基类关系**（direct base class relationship），即有序对 (D, B)。C++26 的静态反射里，`std::meta::bases_of` 返回的就是这些关系的反射，它们还可以在 `obj.[: base :]` 中用来指名基类子对象。

### 变参基类（¶4）

¶4 *base-specifier* 后面跟 `...` 是一个包展开（[[temp.variadic]]），于是一个类可以从一组类型逐一派生。常见的用法是把几个 lambda 合成一个重载集：

```cpp run title="overloaded.cpp" ok
#include <string>
#include <variant>

template<class... Fs>
struct overloaded : Fs... {        // 每个 Fs 都是直接基类
    using Fs::operator()...;       // 把各基类的 operator() 引入同一作用域
};

int main() {
    std::variant<int, std::string> v = 42;
    int r = std::visit(overloaded{
        [](int i) { return i; },
        [](const std::string& s) { return (int)s.size(); },
    }, v);
    return r == 42 ? 0 : 1;
}
```

`overloaded{...}` 能用花括号初始化，是因为 C++17 起有基类的类也可以是聚合；C++20 起它也不再需要手写推导指引。

## 子对象的布局（¶5–¶7）

¶5 基类子对象在[[g:most-derived-object|最派生对象]]（不是任何对象的子对象的那个完整对象）中的排列顺序是未指定的。标准只保证每个基类子对象都存在，并且能通过转换找到；它在哪个偏移、是否排在派生类自己的成员前面，都由 ABI 决定。这样实现才能做空基类优化、把虚基类放到对象末尾。需要可预测的布局时，要看标准布局类的规则（[[class.prop]]）。

注 3 指出，派生类和它的基类子对象可以画成一个有向无环图，箭头表示直接派生自，这张图常称为**子对象格**（subobject lattice）。箭头不一定在内存中有对应物。

¶7 注 5 提醒，基类子对象与同类型的完整对象可能有三点不同：

- 布局可能不同。例如有虚基类的类作为子对象时，它的虚基类不一定紧挨着它（见下文实现视角）；派生类的成员也可能放进基类子对象的尾部填充里。
- 多态行为可能不同。构造和析构期间，基类子对象表现得像正在构造或析构的那个类（[[class.cdtor]]）。
- 大小可以为零。空的基类子对象可以不占空间，这就是空基类优化（EBO）。但同一个最派生对象中，两个同类型的子对象不能在同一地址（[[intro.object]]）。

```cpp run title="ebo.cpp" ok
struct Empty {};
struct A : Empty { int x; };
struct B : Empty { Empty e; int x; };   // 基类和成员 e 同为 Empty

static_assert(sizeof(A) == sizeof(int));  // 主流 ABI 都做空基类优化
int main() {
    B b;
    // 两个 Empty 子对象不能同址
    return (void*)static_cast<Empty*>(&b) != (void*)&b.e ? 0 : 1;
}
```

标准并不强制 `sizeof(A) == sizeof(int)`，它只允许空基类子对象大小为零；但所有主流 ABI 都这样做。

¶6 注 4 提示，基类子对象怎样初始化由构造函数指定，见 [[class.base.init]]。

## 多重继承 [class.mi]

¶1 一个类可以有任意多个基类。有多个直接基类时通常称为**多重继承**（multiple inheritance）。

¶2 注 2 指出，基类的书写顺序一般无关紧要，只影响三件事：构造顺序（按 *base-specifier* 的顺序，[[class.base.init]]）、析构顺序（与构造相反），以及存储布局。

### 同一个基类出现多次（¶3）

¶3 同一个类不能两次作为直接基类，否则无法用名字区分这两个子对象。但它可以多次作为间接基类，也可以既是直接基类又是间接基类。注 3 说，这时能做的事不多：在派生类中查找它的非静态成员会有二义，只有静态成员、枚举和类型可以无二义地引用，因为它们不属于某个特定子对象。

```cpp title="mi-basics.cpp" error
class X {};
class Y : public X, public X {};    // error: X 两次作为直接基类

class L { public: int next; static int count; using T = int; };
class A : public L {};
class B : public L {};
class C : public A, public B {      // OK: L 作为间接基类出现两次
    void f() {
        next = 0;                   // error: 二义，哪个 L？
        A::next = B::next;          // OK: 用限定指明路径
        count = 1;                  // OK: 静态成员
        T t = 0; (void)t;           // OK: 类型
    }
};
class D : public A, public L {};    // OK，但这个直接基类 L 几乎没法用
```

最后一行是合法的，Clang 只给出一条警告，说直接基类 `L` 因二义而不可访问。`D*` 到 `L*` 的转换有两个目标（`A` 里的 `L` 和直接的 `L`），所以是二义的；写 `L::next` 也不行，因为限定名 `L` 查到的是注入类名，仍然对应两个子对象。

### 虚基类（¶4–¶7）

¶4 不带 `virtual` 的基类说明符指定**非虚基类**，带 `virtual` 的指定**虚基类**（virtual base class）。两者的区别在于子对象的数量：

!!! std
    For each distinct base class that is specified virtual, the most derived object shall contain a single base class subobject of that type.

非虚基类在类格中每出现一次，最派生对象里就有一个对应的独立子对象；同一个虚基类不论出现多少次，最派生对象里只有一个，被所有以它为虚基类的子对象共享。¶5、¶6 的注用经典的菱形对比了这两种情况：

```cpp run title="diamond.cpp" ok
#include <cassert>

struct L { int next = 0; };
struct A1 : L {};
struct B1 : L {};
struct C1 : A1, B1 {};               // 两个 L

struct V { int v = 0; };
struct A2 : virtual V {};
struct B2 : virtual V {};
struct C2 : A2, B2 {};               // 一个 V

int main() {
    C1 c1;
    c1.A1::next = 1;
    c1.B1::next = 2;
    assert(c1.A1::next != c1.B1::next);   // 两个独立的子对象
    // L* pl = &c1;                       // error: 二义
    L* pl = static_cast<A1*>(&c1);        // OK: 先选定路径
    (void)pl;

    C2 c2;
    c2.v = 5;                             // OK: 只有一个 V
    V* pv = &c2;                          // OK
    assert(&static_cast<A2&>(c2).v == &static_cast<B2&>(c2).v);
    assert(pv == static_cast<V*>(static_cast<B2*>(&c2)));
}
```

这条规则是相对最派生对象说的：虚基类子对象由谁共享，要到最终的完整对象里才能确定。单独一个 `A2` 对象里有自己的 `V`；作为 `C2` 的一部分时，它的 `V` 和 `B2` 的 `V` 是同一个。由此有两个后果：虚基类由最派生类负责初始化（[[class.base.init]]），虚基类子对象的位置要在运行时查表得到。

¶7 注 6 指出，同一个类可以同时以虚和非虚两种方式作为基类。所有虚的出现合为一个子对象，每个非虚的出现各有一个：

```cpp run title="virt-nonvirt.cpp" ok
struct B { int id = 0; };
struct X : virtual B {};
struct Y : virtual B {};
struct Z : B {};
struct AA : X, Y, Z {};     // 两个 B：X 和 Y 共享的虚 B，Z 自己的 B

int main() {
    AA aa;
    B& shared = static_cast<X&>(aa);
    B& own    = static_cast<Z&>(aa);
    return &shared != &own ? 0 : 1;
}
```

## final 类

[[class.pre#6]] 规定，带有 `final` 的类出现在 *base-clause* 中时，程序非良构。

```cpp title="final-class.cpp" error
struct F final {};
struct G : F {};          // error: F 是 final
```

`final` 一方面说明这个类不是为继承设计的，另一方面让编译器可以去虚化：通过 `F&` 调用虚函数时，动态类型只能是 `F`，可以直接调用（见 [[class.virtual]]）。

## 实现视角

!!! impl "Itanium C++ ABI 的布局（Linux、macOS 上的 GCC 和 Clang）"
    - 非虚基类按声明顺序放在对象开头。第一个有虚表指针的非虚基类是**主基类**（primary base），与派生类共用虚表指针和地址 0。
    - 虚基类放在对象末尾，在所有非虚部分之后。它的偏移随最派生类型而变，所以访问虚基类要从虚表里读出偏移量。
    - 本机 Clang 用 `-Xclang -fdump-record-layouts` 打印 `struct V { int v; virtual void h(); }; struct A : virtual V { int a; }; struct B : virtual V { int b; }; struct D : A, B { int d; };` 中 `D` 的布局：

    ```text
             0 | struct D
             0 |   struct A (primary base)
             0 |     (A vtable pointer)
             8 |     int a
            16 |   struct B (base)
            16 |     (B vtable pointer)
            24 |     int b
            28 |   int d
            32 |   struct V (virtual base)
            32 |     (V vtable pointer)
            40 |     int v
               | [sizeof=48, dsize=44, align=8,
               |  nvsize=32, nvalign=8]
    ```

    `V` 位于偏移 32；而在一个独立的 `A` 对象里，`V` 紧跟在 `A` 的非虚部分之后，位于偏移 16。¶7 说子对象的布局可以与完整对象不同，指的就是这种情况。

    - MSVC 用另一种方案：含虚基类的子对象另存一个指向虚基类偏移表的指针（vbptr），与虚表指针分开。
    - Itanium ABI 总是做空基类优化。MSVC 在多重继承下默认只对部分空基类做 EBO，加 `__declspec(empty_bases)` 才对所有空基类生效。

## 历史与演进

!!! history
    - 多重继承和虚基类在 C++ 标准化之前就已存在，C++98 以来这一节的结构变化很少。
    - C++11：基类说明符可以是包展开和 `decltype`；引入 `final` 和继承构造函数。
    - C++17：有基类的类也可以是聚合，`overloaded{...}` 这样的写法由此可行；继承构造函数的语义重新表述。
    - C++26：*computed-type-specifier* 扩展到包索引和 splice 类型说明符；直接基类关系可以被反射。

## 常见误解

!!! pitfall "虚继承解决了菱形问题，所以应该总是使用"
    虚基类有代价：访问它要查表，对象更大，最派生类必须能访问并负责初始化它。中间类为虚基类写的 *mem-initializer* 在构造最派生对象时会被忽略（[[class.base.init]]），只有最派生类写的那个生效。只在确实需要共享同一个子对象时才用。

!!! pitfall "基类子对象一定排在派生类成员前面"
    标准不保证这一点。主流 ABI 的确这样排列，但可移植的保证只有标准布局类的那几条。

!!! pitfall "`D : A, L`（`A : L`）中的直接基类 L 可以正常使用"
    它是合法的，但几乎无法使用：转换和成员访问都有二义。

## 思考题

!!! question "思考题 1"
    `struct A {}; struct B : A {}; struct C : A, B {};` 合法吗？`C` 有几个 `A` 子对象？`C*` 能转换为 `A*` 吗？

<details markdown="1">
<summary>答案</summary>

合法。¶3 只禁止同一个类两次作为直接基类，这里 `A` 一次是直接基类、一次是间接基类。`C` 有两个 `A` 子对象，所以 `C*` 到 `A*` 的转换是二义的。要得到 `B` 里的那个 `A`，可以先转换为 `B*`；作为直接基类的那个 `A` 则没有任何无二义的写法，Clang 因此会警告这个直接基类不可访问。
</details>

!!! question "思考题 2"
    在 `struct V {}; struct A : virtual V {}; struct B : virtual V {}; struct C : A, B {}; struct D : C, virtual V {};` 中，`D` 对象有几个 `V` 子对象？如果 `D` 写成 `struct D : C, V {}` 呢？

<details markdown="1">
<summary>答案</summary>

第一种情况是一个。按 ¶4，同一个虚基类在最派生对象中只有一个子对象，`A`、`B`、`D` 中三次 `virtual V` 都对应它。第二种情况是两个：共享的虚 `V`，加上 `D` 直接拥有的非虚 `V`。
</details>
