---
title: 成员名字查找
summary: 在类作用域中找名字时，先看类自己，找不到再把各个基类里的结果逐个合并；这一个算法解释了名字隐藏、虚基类的支配、多继承下的二义，以及静态成员为什么不会二义。
status: done
papers: P1787R6
related: basic.lookup, basic.lookup.unqual, basic.lookup.qual, namespace.udecl, expr.ref, class.access.base, class.mi, temp.dep.type
tags: 名字查找, 多继承, 虚基类
updated: 2026-10-19
---

!!! tldr
    - 在类里找名字时先看类自己。只要类里有同名声明，基类的同名成员就一律不看，不论参数是否相同；要用 `using Base::f;` 把基类的重载引回来。
    - 类自己没有，就分别在每个直接基类里找，再合并结果：一边找到的子对象是另一边的基类子对象时，它被支配而丢弃；否则两边找到的声明不同就是二义。
    - 虚继承让一个基类子对象被多条路径共享，所以虚基类里的声明可以被另一条路径上的声明支配；非虚继承做不到。
    - 查找没有二义，使用仍可能二义：静态成员、类型、枚举项经多条路径找到都没问题，非静态成员还要求对象能无二义地转换到那个基类。
    - 类模板中，依赖于模板形参的基类不参与查找，所以要写 `this->f()`。

在命名空间里找名字，只要看那个作用域里绑定了什么（[[g:single-search]]，单次搜索，[[basic.lookup#3]]）。类不一样：类还继承了基类的成员，基类可能有多个，可能重复出现（非虚继承的菱形），也可能被共享（虚继承）。本节定义的**搜索**（search）就是在类作用域里沿着基类找名字的算法。

成员访问 `obj.m`、限定名 `C::m`、成员函数体里的无限定名字、运算符重载的成员候选，查找时都用这个算法。读之前需要知道基类子对象的概念（[[class.mi]]）：非虚基类每出现一次就是一个独立的子对象，虚基类在整个对象里只有一个共享的子对象。

## 派生类的名字隐藏基类的同名成员

```cpp run error
struct Base {
    void f(int);
    void f(double);
};
struct Der : Base {
    void f(const char*);     // 隐藏 Base 的两个 f
};
void t(Der& d) {
    d.Base::f(1);            // OK：限定名直接在 Base 中查找
    d.f(1);                  // error: 只找到 Der::f(const char*)
}
```

¶1 在作用域 X 中从程序点 P 对名字 M 的**搜索**：如果 X 不是类的作用域，就是一次单次搜索；如果 X 是类或类模板 T 的作用域，结果按下面的步骤计算。注 1 指出，只有两种情况下结果会和单次搜索不同：M 是转换函数名（第 7 段），或者单次搜索什么也没找到（这时去基类找）。

换句话说，派生类里只要有一个同名声明，查找就到此为止，基类的同名成员不会成为候选。`d.f(1)` 只看到 `Der::f(const char*)`，`int` 不能转换为 `const char*`，所以出错。

要让基类的重载也参与，用 using 声明把它们引进派生类。using 声明绑定在 `Der` 的作用域里，搜索找到它之后，把它替换成 `Base::f` 的各个声明（[[basic.lookup#3]]）。基类的函数如果与派生类里的某个函数形参相同，就不引入，留下派生类的版本（[[namespace.udecl#11]]）：

```cpp run ok
struct Base {
    void f(int);
    void f(double);
    void g(int);
};
struct Der : Base {
    using Base::f;           // 引入 Base::f(int)、Base::f(double)
    using Base::g;           // Base::g(int) 与 Der::g(int) 形参相同，不引入
    void f(const char*);
    void g(int);
};
void t(Der& d) {
    d.f(1);                  // Base::f(int)
    d.f("x");                // Der::f(const char*)
    d.g(1);                  // Der::g(int)
}
```

!!! note "隐藏与覆盖"
    隐藏是查找层面的事，虚函数覆盖（override）是调用分派层面的事，两者互不相干。如果 `Base::h` 是虚函数，`Der::h` 签名相同，那么 `Der::h` 既隐藏又覆盖 `Base::h`：通过 `Der&` 查找 `h` 只找到 `Der::h`，通过 `Base&` 调用 `h` 会分派到 `Der::h`。

## 查找集（¶2–¶3）

¶2 类 C 中名字 N 的**查找集**（[[g:lookup-set]]）记作 S(N,C)，由两部分组成：

- **声明集**（declaration set）：找到的名为 N 的成员声明；
- **子对象集**（subobject set）：这些声明是在哪些子对象里找到的（可能经由 using 声明）。

声明集中的类型声明，包括注入类名（类名在自己类中的那份绑定），都换成它们所指的类型。同一个类型可能经由不同路径找到，例如两个基类都继承自 `A`，于是都带着注入类名 `A`。换成类型之后两边的声明集相同，合并时不会判为二义：

```cpp run ok
struct A {};
struct B : A {};
struct C : A {};
struct D : B, C {
    A* p;    // OK：经 B、C 两条路径找到的都是类型 A
};
```

¶3 第一步只看 C 自己：在 C 的作用域里对 N 做一次单次搜索。如果 P 在 C 的[[g:complete-class-context]]中（成员函数体、默认实参、默认成员初始化器等，[[class.mem#10]]），就从类定义的末尾开始搜索，能看到所有成员；否则从 P 开始搜索，只能看到 P 之前声明的成员。

搜索结果非空，子对象集就是 `{C}`，计算结束。这就是上一节的名字隐藏。

## 合并各基类的结果（¶4–¶5）

¶4 如果 C 自己没有名为 N 的成员，S(N,C) 先置为空，然后对每个直接基类子对象 Bᵢ 递归计算 S(N,Bᵢ)，依次合并进 S(N,C)。只考虑非依赖的基类（[[temp.dep.type]]）。

注 2 补充两点。C 还不完整时（P 在类定义内部、不在完整类上下文中），只考虑基类说明符出现在 P 之前的基类。实例化出来的类没有依赖基类。

¶5 把 S(N,Bᵢ) 合并进当前的 S(N,C)：

| 情形 | 结果 |
|---|---|
| ¶5.1 S(N,Bᵢ) 为空，或者它的每个子对象都是 S(N,C) 中某个子对象的基类子对象 | S(N,C) 不变：Bᵢ 这边的结果被支配 |
| ¶5.1 反过来，S(N,C) 为空，或者它的每个子对象都是 S(N,Bᵢ) 中某个子对象的基类子对象 | S(N,C) 换成 S(N,Bᵢ)：原来的结果被支配 |
| ¶5.2 否则，两边的声明集不同 | 二义：声明集记为无效，子对象集取并集；之后再合并时，无效的声明集和任何声明集都算不同 |
| ¶5.3 否则（声明集相同） | 声明集不变，子对象集取并集 |

这里说的"是某个子对象的基类子对象"比较的是子对象，不是类型。非虚菱形中，B 里的 A 和 C 里的 A 是两个子对象，互不为基；虚基类 V 只有一个子对象，它是每一个虚继承 V 的子对象的基。虚继承下的支配规则就来自这一点。

## 查找的结果（¶6）

¶6 搜索的结果是 S(M,T) 的声明集。它如果无效，程序非良构，这就是成员二义。

它如果与在 T 的完整类上下文中搜索 M 的结果不同，程序非良构，不要求诊断（{{ifndr}}）：

```cpp ifndr
typedef int I;
struct S {
    I x;                 // 这里在 S 中找不到 I，往外找到 ::I（int）
    typedef double I;    // 在完整类上下文中搜索 S 会找到 S::I（double）
};
```

这条规则保证类成员的含义不随成员的排列顺序改变：编译器可以从上到下处理类定义，程序员也写不出调换成员顺序就改变含义的类。GCC 对上面的代码报告 `I` 改变了含义，本机 Clang 23 不给诊断，两者都符合标准。

### 标准例 1

```cpp run ok
struct A { int x; };                    // S(x,A) = { {A::x}, {A} }
struct B { float x; };                  // S(x,B) = { {B::x}, {B} }
struct C: public A, public B { };       // S(x,C) = { 无效, {C 中的 A, C 中的 B} }
struct D: public virtual C { };         // S(x,D) = S(x,C)
struct E: public virtual C { char x; }; // S(x,E) = { {E::x}, {E} }
struct F: public D, public E { };       // S(x,F) = S(x,E)
int main() {
    F f;
    f.x = 0;                            // OK：找到 E::x
}
```

计算 S(x,F) 的过程：

1. F 自己没有 `x`，开始合并直接基类 D 和 E。
2. 把 S(x,D) 合并进空集，按第 5.1 项第二种情形直接复制，得到 {无效, {C 中的 A, C 中的 B}}。
3. 合并 S(x,E) = {{E::x}, {E}}。C 是虚基类，F 中只有一个 C 子对象，它同时是 D 和 E 的基类子对象，所以 C 中的 A 和 B 都是 E 的基类子对象。按第 5.1 项第二种情形，S(x,F) 换成 S(x,E)。

可见无效状态在后续合并中可以消除，只要后来出现一个支配它的声明。把 `virtual` 去掉，D 和 E 各有自己的 C，第 3 步不成立，结果就是二义。

## 虚基类与支配（¶9）

¶9 注 5 说明，使用虚基类时，可能沿一条不经过隐藏者的路径到达被隐藏的声明，这不算二义。同样的结构换成非虚基类就是二义，因为没有一个声明能隐藏所有其他声明。标准的例 3：

```cpp run error
struct V { int f();  int x; };
struct W { int g();  int y; };
struct B : virtual V, W {
    int f();  int x;
    int g();  int y;
};
struct C : virtual V, W { };
struct D : B, C { void glorp(); };

void D::glorp() {
    x++;              // OK：B::x 隐藏 V::x
    f();              // OK：B::f() 隐藏 V::f()
    y++;              // error: B::y 与 C 中那个 W 的 W::y
    g();              // error: B::g() 与 C 中那个 W 的 W::g()
}
```

对象结构如下（标准图 1）。V 是虚基类，只有一个；W 是非虚基类，B 和 C 各有一个：

```text
   W₁   V   W₂
    \  / \  /
     B     C
      \   /
        D
```

S(x,D)：S(x,B) = {{B::x}, {B}}，因为 B 自己声明了 `x`；C 自己没有 `x`，W 里也没有，所以 S(x,C) = {{V::x}, {V}}。合并时，V 是不是 B 的基类子对象？是的，D 中唯一的 V 同时是 B 和 C 的基。按第 5.1 项第一种情形，S(x,D) 保持 {{B::x}, {B}}。

S(y,D)：S(y,B) = {{B::y}, {B}}，S(y,C) = {{W::y}, {W₂}}。W₂ 不是 B 的基类子对象（B 有自己的 W₁），B 也不是 W₂ 的基类子对象，声明集又不同，所以结果无效，即二义。

!!! tip "怎样理解支配"
    "离得最近的声明胜出"并不准确。准确的说法是：一个声明所在的子对象如果以另一个声明所在的子对象为基类子对象，前者就支配后者。虚继承让同一个子对象由多条路径共享，支配关系才能跨路径成立；非虚继承下各条路径的子对象互相独立，无法相互支配。

## 查找无二义，使用仍可能二义（¶8、¶10、¶11）

```cpp run error
struct V { int v; };
struct A {
    int a;
    static int s;
    enum { e };
    using T = int;
    static void sf();
};
struct B : A, virtual V { };
struct C : A, virtual V { };
struct D : B, C { };

void f(D* pd) {
    pd->v++;          // OK：只有一个 V 子对象
    pd->s++;          // OK：静态成员
    int i = pd->e;    // OK：枚举项
    D::T k = i;       // OK：嵌套类型
    D::sf();          // OK：静态成员函数
    (void)k;
    pd->a++;          // error: D 中有两个 A
}
```

¶8 注 4 说，即使对象中有多个类型为 T 的基类子对象，T 中定义的静态成员、嵌套类型和枚举项也能无二义地找到；两个基类子对象共享它们共同的虚基类的非静态成员子对象。

用合并算法解释：经两条路径找到的 `A::s`，声明集都是 {A::s}，按第 5.3 项只是合并子对象集，查找本身没有二义。`A::a` 也一样，查找同样得到 {A::a}。那么 `pd->a` 为什么出错？因为使用非静态成员还要把对象表达式转换到 `A`，而 D 中有两个 `A`，这是 [[expr.ref]] 规定的错误，不是查找的错误。

¶10 把派生类的指针或对象显式或隐式地转换为基类的指针或引用时，结果必须无二义地指向唯一一个表示该基类的对象：

```cpp run error
struct V { };
struct A { };
struct B : A, virtual V { };
struct C : A, virtual V { };
struct D : B, C { };

void g() {
    D d;
    B* pb = &d;       // OK
    A* pa = &d;       // error: B 里的 A 还是 C 里的 A？
    A* pa2 = pb;      // OK：先到 B，再到唯一的 A
    V* pv = &d;       // OK：只有一个 V
    (void)pa2; (void)pv;
}
```

这一条放在成员查找里，是因为它与第 8、11 段说的是同一件事：查找只决定找到哪个声明，从哪个子对象中取成员由这种转换决定。

¶11 注 6 和例 5 把这个区别集中展示出来：

```cpp
struct B1 {
    void f();
    static void f(int);
    int i;
};
struct B2 {
    void f(double);
};
struct I1: B1 { };
struct I2: B1 { };

struct D: I1, I2, B2 {
    using B1::f;
    using B2::f;
    void g() {
        f();                        // 二义：this 转换到 B1* 有二义
        f(0);                       // 无二义：静态的 B1::f(int) 不需要对象
        f(0.0);                     // 无二义：只有一个 B2
        int B1::* mpB1 = &D::i;     // 无二义：&D::i 的类型是 int B1::*
        int D::* mpD = &D::i;       // 二义：int B1::* 转换为 int D::* 有二义
    }
};
```

- 两个 using 声明都绑定在 D 中，搜索 D 时就找到它们，替换为 {B1::f(), B1::f(int), B2::f(double)}。D 自己的结果非空，不再合并基类，查找没有二义。
- `f()` 选中非静态的 `B1::f()`，需要把 `*this` 转换到 `B1`，D 中有两个 B1，转换有二义。
- `f(0)` 选中静态成员，不需要对象。
- `&D::i` 的类型是 `int B1::*`，因为 `i` 是 B1 的成员（[[expr.unary.op]]），所以第一行不需要转换。第二行要把 `int B1::*` 转换为 `int D::*`（[[conv.mem]]），这要求 B1 是 D 的无二义基类，因此失败。

!!! impl "Clang 与标准的偏差"
    本机 Clang 23 拒绝 `int B1::* mpB1 = &D::i;`，报告 non-static member 'i' found in multiple base-class subobjects of type 'B1'。标准例 5 把这一行标为无二义，Clang 在形成成员指针时过早地检查了子对象是否唯一。其余各行 Clang 的判定与标准一致，所以这个例子没有标判定。

!!! lawyer "诊断的措辞"
    Clang 对 `pd->a` 报告 non-static member 'a' found in multiple base-class subobjects of type 'A'，听起来像查找出了问题。按标准，查找是成功的，出错的是之后对象表达式到 `A` 的转换。区分这一点有实际意义：同样的名字换成静态成员就合法。

## 转换函数模板（¶7）

```cpp run ok
struct A {
    operator int();
    template<class T> operator T*();
};
struct B : A {
    operator double();      // 名字与基类的转换函数都不相同，不隐藏它们
};
void t(B b) {
    int i = b;              // A::operator int
    int* p = b;             // A::operator T*，T = int
    double d = b;           // B::operator double
    (void)i; (void)p; (void)d;
}
```

转换函数的名字按类型比较（[[basic.pre#4]]）：`operator double` 和 `operator int` 是不同的名字，所以 `B::operator double` 不隐藏 `A::operator int`。但这样一来，`operator int*` 和模板 `template<class T> operator T*` 的名字也不相同，单次搜索 `operator int*` 找不到这个模板。

¶7 所以，M 是非依赖的转换函数名时，T 的成员转换函数模板也要考虑：对每个这样的模板 F，把与 F 对应（[[basic.scope.scope#4]]）的函数模板声明都视为同名，构造查找集，其声明集（不能是无效的）并入结果。不能转换到目标类型的模板，之后由重载决议和模板实参推导淘汰（[[temp.over]]）。

## 更多例子

### 菱形继承

```cpp run error
struct A { int x; void f(); static int s; };
struct B : A { };
struct C : A { };
struct D : B, C { };          // 非虚菱形：两个 A
struct VB : virtual A { };
struct VC : virtual A { int x; };
struct VD : VB, VC { };       // 虚菱形：一个 A；VC::x 支配 A::x

void t(D& d, VD& vd) {
    d.s = 1;                  // OK：静态成员
    d.B::x = 1;               // OK：B 中只有一个 A
    vd.x = 1;                 // OK：VC::x 支配 A::x
    vd.f();                   // OK：只有一个 A
    d.x = 1;                  // error: 两个 A 子对象
}
```

`d.B::x`：限定名 `B::x` 在 B 中查找，得到 `A::x`。[[expr.ref]] 随后检查 `x` 所属的类 `A` 是否为 `B` 的无二义基类，再把 `d` 转换到 `B`，两步都没有二义。

### 不同种类的同名成员

一个基类的数据成员与另一个基类的成员函数同名，声明集同样不同，按第 5.2 项是二义。在派生类中用 using 声明选定一个，查找在派生类就结束了：

```cpp run error
struct B1 { int x; };
struct B2 { void x(); };
struct D : B1, B2 { };
struct E : B1, B2 { using B1::x; };

void t(D d, E e) {
    e.x = 1;          // OK：E 中的 using 声明，即 B1::x
    d.x;              // error: {B1::x} 与 {B2::x} 不同，二义
}
```

### 私有继承与注入类名

注入类名也参与成员查找，由此会有一个常见的意外：

```cpp run error
struct P { };
struct Q : private P { };
struct R : Q {
    ::P* good;        // OK：在全局命名空间中查找
    P* bad;           // error: 找到的是经私有基类继承来的注入类名
};
```

在 `R` 中查找 `P`：R 自己没有，合并基类 Q，在 Q 的基类 P 中找到注入类名 `P`。查找本身没有问题，但访问检查发现这个名字是经 Q 的私有基类继承来的，在 R 中不可访问。改成 `::P` 即可。

### 依赖基类

```cpp run error
template<class T> struct Base { void f(); };
template<class T> struct Der : Base<T> {
    void g() {
        this->f();           // OK：依赖的成员访问，推迟到实例化时查找
        Der::f();            // OK：限定名，查找推迟到实例化时
        f();                 // error: 无限定查找不进入依赖基类 Base<T>
    }
};
```

¶4 只合并非依赖的基类。`Base<T>` 依赖于 `T`，在模板定义中根本不知道它有哪些成员（`Base` 可能有特化），所以查找不进入它。`this->f()` 和 `Der::f()` 让名字变成依赖的，查找推迟到实例化之后。

## 实现视角

!!! impl "编译器怎么做"
    - Clang 用 `CXXRecordDecl::lookupInBases` 和 `CXXBasePaths` 记录在哪些路径上找到了什么，相当于查找集里的子对象集。它的诊断区分两种情况：在不同类型的基类中找到同名成员（第 5.2 项的二义，member found in multiple base classes of different types），以及在同一类型的多个基类子对象中找到非静态成员（第 11 段所说的使用二义）。
    - 查找完全在编译期进行，不影响对象布局，但它决定了从哪个子对象取成员。非虚基类的偏移是编译期常量，虚基类的偏移要在运行时从虚表中取得。

## 历史与演进

!!! history
    - C++98 用支配等文字描述多继承下的查找，与静态成员、类型、using 声明的交互有不少含糊之处。
    - C++11 改用查找集的合并算法，也就是今天第 2–5 段的骨架。
    - C++23 由 [[P1787R6]] 把它定义为类作用域中的搜索，作为所有查找的一部分；旧 [basic.scope.class] 中调换成员顺序不得改变含义的规则改写为第 6 段的不要求诊断。

## 常见误解

!!! pitfall "重载会跨越基类和派生类"
    派生类声明了一个 `f`，基类所有的 `f` 就都看不见了，即使参数完全不同。Clang 的 `-Woverloaded-virtual` 警告的就是一种典型情况：派生类的虚函数隐藏了基类中同名的其他虚函数重载。

!!! pitfall "using 声明会让基类版本压过派生类版本"
    `using Base::f;` 引入的函数如果与派生类中的函数形参相同，就不引入（[[namespace.udecl#11]]），既不冲突，也不二义，派生类的版本胜出。

!!! pitfall "模板里可以直接调用基类成员"
    依赖基类的成员不在无限定查找的范围内，要写 `this->f()`。MSVC 在非 `/permissive-` 模式下会找到它们，这样的代码换一个编译器就无法编译。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct A { void f(); };
    struct B : virtual A { void f(); };
    struct C : virtual A { };
    struct D : B, C { };
    struct E : D, A { };   // 再加一个非虚的 A
    ```
    `D{}.f()` 和 `E{}.f()` 的查找结果各是什么？

<details markdown="1">
<summary>答案</summary>

S(f,D)：S(f,B) = {{B::f}, {B}}，S(f,C) = {{A::f}, {虚基类 A}}。虚基类 A 是 B 的基类子对象，被支配，结果是 {{B::f}, {B}}，`D{}.f()` 调用 `B::f`。

S(f,E)：先合并 S(f,D) = {{B::f}, {B}}，再合并非虚基类 A 的 S(f,A) = {{A::f}, {非虚的 A}}。这个 A 是 E 的直接基类，与 D 里的虚基类 A 是不同的子对象；它不是 B 的基类子对象，B 也不是它的基类子对象，声明集又不同，所以二义，`E{}.f()` 非良构。Clang 23 报告 member 'f' found in multiple base classes of different types，并警告直接基类 A 因二义而不可访问。
</details>

!!! question "思考题 2"
    为什么第 2 段要求把类型声明换成它们所指的类型？举一个不换就会误判为二义的例子。

<details markdown="1">
<summary>答案</summary>

例如 B 中有 `using T = int;`，C 中有 `typedef int T;`，D 继承 B 和 C。两条路径找到的是两个不同的别名声明，如果按声明比较，按第 5.2 项会判为二义；换成类型后两边都是 {int}，按第 5.3 项合并，`D::T` 没有二义。经多条路径找到同一个注入类名也是同样的道理。
</details>
