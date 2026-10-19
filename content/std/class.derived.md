---
title: 派生类
summary: 基类说明符的语法与语义、直接/间接基类、基类子对象与子对象格、布局未指定；多重继承、虚基类与菱形继承、final 类
status: draft
covers: class.derived.general, class.mi
related: class.virtual, class.abstract, class.access.base, class.member.lookup, class.base.init, intro.object, conv.ptr, class.pre
tags: 类, 继承, 多重继承, 虚基类
updated: 2026-10-17
---

**派生**（derivation）是 C++ 类之间最重要的关系。本节（[class.derived.general] 与 [class.mi]）只回答结构上的问题：怎样声明基类，派生类对象里有哪些基类子对象，虚基类与非虚基类的子对象如何对应。基类成员在派生类里如何查找（[[class.member.lookup]]）、能否访问（[[class.access.base]]）、如何初始化（[[class.base.init]]），虚函数如何覆盖（[[class.virtual]]），都由其他条款规定。

贯穿本节的核心观念是：**派生类对象中包含基类子对象**（base class subobject）。在 C++ 对象模型中，说 `D` 是一个 `B`，意思是每个 `D` 对象里嵌着一个 `B` 对象；派生类到基类的指针转换，就是找到那个子对象。

## 基类说明符的语法（[class.derived.general] ¶1）

```
base-clause:
    : base-specifier-list
base-specifier:
    attribute-specifier-seq(opt) class-or-decltype
    attribute-specifier-seq(opt) virtual access-specifier(opt) class-or-decltype
    attribute-specifier-seq(opt) access-specifier virtual(opt) class-or-decltype
class-or-decltype:
    nested-name-specifier(opt) type-name
    nested-name-specifier template simple-template-id
    computed-type-specifier
```

几点说明：

- `virtual` 和访问说明符（`public`/`protected`/`private`）可以按任意顺序书写，`virtual public B` 与 `public virtual B` 等价。
- *computed-type-specifier* 包括 `decltype(...)`、包索引说明符和 splice 类型说明符，所以 `struct L : decltype(lambda) {}` 是合法的，从 lambda 派生以组成重载集的惯用法就建立在这一点上。
- 可选的属性说明符序列属于这个 *base-specifier* 本身。

## 基类必须是完整的类类型（¶2）

¶2 规定了以下几点：

- *class-or-decltype* 必须表示一个（可能带 cv 限定的）类类型，并且不能是**不完整定义的类**（incompletely defined class，[[class.mem]]），也就是说基类在此处必须已经完整。cv 限定会被忽略。
- 查找 *type-name* 或 *simple-template-id* 中的名字时，采用**仅类型查找**（type-only lookup，[[basic.lookup]]），同名的变量和函数会被忽略。
- 由 *base-specifier* 直接写出的类称为**直接基类**（direct base class）。每个 *base-specifier* 对应一个直接基类关系（direct base class relationship），即有序对 (D, B)。C++26 中，直接基类关系可以被反射（`std::meta::bases_of` 返回的就是它们的反射），并可在 `obj.[: base :]` 中用来指名基类子对象。
- 直接基类，以及基类的直接基类（递归地），都是基类。是基类但不是直接基类的，称为间接基类。

```cpp title="base-requirements.cpp" error
struct Inc;
struct A : Inc {};              // error: 基类不完整
struct Self : Self {};          // error: Self 在此处尚未完整
struct X {};
using CX = const X;
struct W : CX {};               // OK: cv 限定被忽略
int B;
struct B {};
struct D : B {};                // OK: 仅类型查找，忽略变量 B
```

为什么基类必须完整？派生类的布局要容纳整个基类子对象，编译器需要知道基类的大小、成员和虚函数，不完整的基类无法参与布局。

¶2 后半句规定，**基类的成员也是派生类的成员**。注 2 汇总了几条相关规则：

- 基类的构造函数可以用 using 声明显式继承（[[namespace.udecl]]）；
- 除非被隐藏或有二义（[[class.member.lookup]]），基类成员可以像派生类自己的成员一样在表达式中使用；
- 作用域解析运算符 `::` 可以显式指名被隐藏的基类成员；
- 指向派生类的指针可以隐式转换为指向可访问且无二义的基类的指针（[[conv.ptr]]），派生类左值可以绑定到这种基类的引用（[[dcl.init.ref]]）。

## 基类子对象（¶3–¶4）

¶3 规定，*base-specifier-list* 指定了派生类对象所含基类子对象的类型。在 `struct Derived2 : Derived` 和 `struct Derived : Base` 的例子中，`Derived2` 对象含一个 `Derived` 子对象，后者又含一个 `Base` 子对象。

¶4 规定，*base-specifier* 后跟 `...` 构成包展开（[[temp.variadic]]），变参基类由此成为可能：

```cpp run title="overloaded.cpp" ok
#include <string>
#include <variant>

template<class... Fs>
struct overloaded : Fs... {        // ¶4：包展开为多个直接基类
    using Fs::operator()...;       // 把每个基类的 operator() 引入同一作用域参与重载
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

（`overloaded{...}` 能直接聚合初始化，是因为 C++17 起有基类的类也可以是聚合；C++20 起也不再需要显式的推导指引。）

## 布局未指定；子对象格（¶5–¶7）

¶5 规定，基类子对象在**最派生对象**（most derived object）中的分配顺序是未指定的。注 3 指出，派生类与其基类子对象可以用一个有向无环图（DAG）表示，箭头的意思是"直接派生自"；这个 DAG 常称为**子对象格**（subobject lattice）。这些箭头不必在内存中有物理表示。

!!! note "为什么不规定布局"
    标准只在语义上作出承诺：每个基类子对象都存在，并且可以通过转换找到。它位于哪个偏移、是否排在派生类成员之前，都留给 ABI 决定。这样实现就可以做空基类优化、把虚基类放到对象末尾、重排子对象以减少填充。需要稳定的布局时，应当看标准布局类（[[class.prop]]）的规则，而不是这里。

¶6（注）说明，基类子对象的初始化可以在构造函数中指定，见 [[class.base.init]]。

¶7（注）指出，基类子对象与同类型的完整对象可能有以下不同：

- 布局可能不同。例如在 Itanium ABI 中，含虚基类的类作为基类子对象时，它的虚基类并不在它自己的连续区域里（见下文的实现视角）；派生类的成员还可能放进基类子对象的尾部填充中。
- 多态行为可能不同。在构造和析构期间，基类子对象的动态类型表现为正在构造或析构的那个类（[[class.cdtor]]）。
- 大小可以为零。空基类子对象可以不占空间（空基类优化，EBO）；但在同一个最派生对象中，**同类型的两个子对象不能分配在同一地址**（[[intro.object]]）。

```cpp run title="ebo.cpp" ok
struct Empty {};
struct A : Empty { int x; };
struct B : Empty { Empty e; int x; };   // 基类 Empty 与成员 e 同类型，不能同址

static_assert(sizeof(A) == sizeof(int));  // 实践中：空基类优化
int main() {
    B b;
    return (void*)static_cast<Empty*>(&b) != (void*)&b.e ? 0 : 1;   // 两个 Empty 子对象地址不同
}
```

（所有主流 ABI 都满足 `sizeof(A) == sizeof(int)`，但标准并不强制，它只说空基类子对象可以是零大小。）

---

## 多重继承（[class.mi] ¶1–¶3）

¶1 规定，一个类可以有任意多个基类。使用多于一个直接基类，通常称为**多重继承**（multiple inheritance）。

¶2（注）指出，派生的顺序通常无关紧要，只在三个场合起作用：构造顺序（[[class.base.init]]，按 *base-specifier* 的声明顺序）、析构顺序（与构造相反），以及存储布局（[[class.mem]]）。

¶3 规定，**同一个类不能作为直接基类出现多次**，否则就无法用名字区分这两个子对象（`X::m` 指的是哪一个？）。但一个类可以多次作为间接基类，也可以同时是直接基类和间接基类。注 3 指出，这种情况下能做的事很有限：在派生类作用域中查找它的非静态数据成员和成员函数会产生二义；不过它的静态成员、枚举和类型不属于某个特定子对象，可以无二义地引用。

```cpp title="mi-basics.cpp" error
class X {};
class Y : public X, public X {};                   // error: X 两次作为直接基类

class L { public: int next; static int count; using T = int; };
class A : public L {};
class B : public L {};
class C : public A, public B {                     // OK: L 作为间接基类出现两次
    void f() {
        next = 0;                                  // error: 二义（哪个 L 子对象？）
        A::next = B::next;                         // OK: 用限定指明路径
        count = 1;                                 // OK: 静态成员不属于子对象
        T t = 0; (void)t;                          // OK: 类型
    }
};
class D : public A, public L {};                   // OK（Clang 会警告：直接基类 L 因二义而不可访问）
```

`class D : public A, public L` 是合法的，但这个直接基类 `L` 几乎无法使用。从 `D*` 到 `L*` 的转换是二义的（`A::L` 和直接的 `L` 共有两个），`L` 的非静态成员也无法无二义地指名：写 `L::next` 时，限定名 `L` 查到的是注入类名，它仍然对应两个子对象。

## 非虚基类与虚基类（¶4）

¶4 是本节的核心规范：

- 不含 `virtual` 的基类说明符指定**非虚基类**，含 `virtual` 的指定**虚基类**（virtual base class）。
- 非虚基类在最派生类的类格中每出现一次，最派生对象中就有一个与之对应的、各不相同的该类型基类子对象。
- 对每个指定为 `virtual` 的不同基类，最派生对象只含一个该类型的基类子对象。

!!! std
    For each distinct base class that is specified virtual, the most derived object shall contain a single base class subobject of that type.

    对每个被指定为 virtual 的不同基类，最派生对象应恰好含一个该类型的基类子对象。

注意，这条规则是相对最派生对象说的：虚基类子对象由谁共享，要到最终的完整对象里才确定。`A : virtual V` 作为独立对象时含一个 `V`；作为 `C : A, B` 的子对象时，它的 `V` 与 `B` 的 `V` 是同一个。正因为如此，**虚基类必须由最派生类初始化**（[[class.base.init]]），虚基类的位置也必须在运行期查表得到。

### 菱形：非虚 vs 虚（¶5–¶6）

¶5（注 4）说明非虚继承的情形：`C : A, B` 且 `A : L`、`B : L` 时，`C` 对象有两个 `L` 子对象，必须用 `A::next` 和 `B::next` 区分。

¶6（注 5）说明虚继承的情形：`A : virtual V`、`B : virtual V`、`C : A, B` 时，`C` 对象只有一个 `V` 子对象，由 `A` 和 `B` 两个子对象共享。

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
    assert(c1.A1::next != c1.B1::next);            // 两个独立的子对象
    // L* pl = &c1;                                // error: 二义
    L* pl = static_cast<A1*>(&c1);                 // OK: 先选路径
    (void)pl;

    C2 c2;
    c2.v = 5;                                      // OK: 只有一个 V，无二义
    V* pv = &c2;                                   // OK
    assert(static_cast<A2&>(c2).v == static_cast<B2&>(c2).v);
    assert(pv == static_cast<V*>(static_cast<B2*>(&c2)));
}
```

### 虚与非虚混合（¶7）

¶7（注 6）指出，一个类可以同时以虚和非虚两种方式拥有同一类型的基类。所有虚出现对应同一个子对象，每个非虚出现各自对应一个子对象。标准的例子中， `AA : X, Y, Z`，`X : virtual B`、`Y : virtual B`、`Z : B`，于是 `AA` 有两个 `B` 子对象：`X` 和 `Y` 共享的虚 `B`，以及 `Z` 自己的 `B`。

```cpp run title="virt-nonvirt.cpp" ok
struct B { int id = 0; };
struct X : virtual B {};
struct Y : virtual B {};
struct Z : B {};
struct AA : X, Y, Z {};

int main() {
    AA aa;
    B& shared = static_cast<X&>(aa);
    B& own    = static_cast<Z&>(aa);
    return &shared != &own ? 0 : 1;                // 两个不同的 B 子对象
}
```

## `final` 类

`final` 由 [[class.pre#6]] 规定：如果一个带 *class-property-specifier* `final` 的类作为 *class-or-decltype* 出现在 *base-clause* 中，程序 ill-formed。

```cpp title="final-class.cpp" error
struct F final {};
struct G : F {};          // error: F 是 final
```

`final` 类有两个作用：一是表达设计意图，说明这个类不是为继承设计的；二是让编译器可以去虚化，通过 `F&` 调用虚函数时，动态类型必然就是 `F`，可以直接调用（见 [[class.virtual]] 的实现视角）。

## 实现视角

!!! impl "Itanium C++ ABI 的布局（GCC、Clang 在 Linux/macOS 上）"
    - 非虚基类按声明顺序放在对象开头。第一个动态的（即有 vptr 的）非虚基类成为**主基类**（primary base），与派生类共享 vptr 和地址 0。
    - 虚基类放在对象末尾，位于所有非虚部分（nvsize）之后。虚基类的偏移随最派生类型而变，所以访问它需要从 vtable 中读取 vbase offset。
    - 本机 Clang 用 `-Xclang -fdump-record-layouts` 打印出的布局（`struct V { int v; virtual void h(); }; struct A : virtual V { int a; }; struct B : virtual V { int b; }; struct D : A, B { int d; };`）：

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

    可以看到 `V` 位于偏移 32，在所有非虚部分之后；而在一个独立的 `A` 对象中，`V` 紧跟在 `A` 的非虚部分之后（偏移 16）。¶7 的注说基类子对象的布局可以与同类型的最派生对象不同，指的就是这种情况。
    - MSVC 采用另一种方案：每个含虚基类的子对象存一个 vbptr（指向虚基类偏移表），与 vfptr 分开。
    - 空基类优化在 Itanium ABI 中是强制的（ABI 层面）。MSVC 在多重继承下历来只对第一个空基类做 EBO，需要加 `__declspec(empty_bases)` 才对所有空基类生效。

## 历史与演进

!!! history
    - **C++98**：多重继承、虚基类、访问说明符等结构在 ARM 时代就已存在，此后变化很少。
    - **C++11**：包展开可以作为基类说明符（变参模板）；引入 `final`；*decltype-specifier* 可以作为基类；引入继承构造函数。
    - **C++17**：有基类的类也可以是聚合（因此 `overloaded{...}` 可以用花括号初始化）；继承构造函数的语义重新表述。
    - **C++26** {{c++26}}：*computed-type-specifier* 扩展到包索引与 splice 类型说明符；直接基类关系成为可以反射的实体（静态反射）；类的 `final` 归入 *class-property-specifier*。

## 陷阱

!!! pitfall
    1. 认为虚继承解决了菱形问题，所以总该使用。虚基类有运行期代价：访问要查表，构造要由最派生类负责初始化，对象也更大；而且最派生类必须能访问并初始化虚基类。只在确实需要共享时才使用。
    2. 认为基类一定排在派生类成员之前。标准不保证这一点，只有标准布局类的规则提供有限的保证。
    3. 以为 `D : A, L`（`A : L`）里的直接基类 `L` 可以正常使用。它合法，但几乎无法使用，转换与成员访问都有二义。
    4. 忽略了虚基类初始化器会被丢弃。中间类构造函数为虚基类写的 *mem-initializer*，在构造最派生对象时会被忽略（[[class.base.init]]），只有最派生类写的那个生效。

## 思考题

!!! question "思考题 1"
    `struct A {}; struct B : A {}; struct C : A, B {};` 合法吗？`C` 有几个 `A` 子对象？`C*` 能转换到 `A*` 吗？

<details markdown="1">
<summary>答案</summary>

合法。¶3 只禁止同一个类两次作为直接基类，`A` 一次是直接基类、一次是间接基类是允许的。`C` 有两个 `A` 子对象：直接基类 `A`，以及 `B` 中的 `A`。`C*` 到 `A*` 的转换是二义的，ill-formed；要转换到 `B` 中的那个 `A`，可以先转为 `B*`。要转换到作为直接基类的那个 `A`，则没有任何无二义的写法，所以 Clang 会警告这个直接基类因二义而不可访问。
</details>

!!! question "思考题 2"
    在 `struct V {}; struct A : virtual V {}; struct B : virtual V {}; struct C : A, B {}; struct D : C, virtual V {};` 中，`D` 对象有几个 `V` 子对象？

<details markdown="1">
<summary>答案</summary>

一个。按 ¶4，对每个指定为 virtual 的不同基类，最派生对象只含一个该类型的子对象，所以 `A`、`B`、`D` 中 `V` 的三次 `virtual` 出现都对应同一个 `V`。如果 `D` 写成 `struct D : C, V {}`（非虚），就会有两个：共享的虚 `V`，以及 `D` 直接拥有的非虚 `V`。
</details>

## 小结

!!! summary
    | 概念 | 要点 |
    |---|---|
    | 基类说明符 | 访问说明符与 `virtual` 顺序任意；可用 `decltype`、包展开；基类必须完整 |
    | 直接/间接基类 | 直接写出的 vs 经由其他基类得到的 |
    | 基类子对象 | 派生类对象包含基类子对象；布局顺序未指定 |
    | 同一直接基类两次 | ill-formed；间接多次合法 |
    | 非虚基类 | 类格中每次出现对应一个独立子对象 |
    | 虚基类 | 每个不同的虚基类在最派生对象中只有一个子对象，由最派生类初始化 |
    | `final` 类 | 不能作为基类（[class.pre]/6） |
