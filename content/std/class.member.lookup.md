---
title: 成员名字查找
summary: 在类作用域中"搜索"一个名字时，怎样用"声明集 + 子对象集"的查找集沿基类格逐个合并，从而统一解释名字隐藏、虚基类支配、静态成员的无二义性与多继承下的二义。
status: done
related: basic.lookup, basic.lookup.unqual, basic.lookup.qual, namespace.udecl, expr.ref, class.access.base, class.mi, temp.dep.type
tags: 名字查找, 多继承, 虚基类
updated: 2026-10-17
---

在命名空间作用域里，"在作用域 S 中找名字"就是看 S 里绑定了什么（[[basic.lookup#3|单次搜索]]）。类作用域不行：类除了自己的成员，还"继承"了基类的成员，而基类可能有多个、可能重复出现（非虚继承的菱形）、可能共享（虚继承）。于是标准在本节定义了**搜索**（search）：对类作用域，搜索要沿着基类子对象格（subobject lattice）计算一个[[g:lookup-set|查找集]]（lookup set）。

本节是以下所有规则的共同基础：

- 成员访问 `obj.m`、`p->m` 中 `m` 的查找（[[basic.lookup.qual]] 的成员限定名）；
- 限定名 `C::m`（[[class.qual]]）；
- 成员函数体、默认实参等处的无限定名（无限定搜索到达类作用域时，[[basic.lookup.unqual#2]] 的注 1）；
- 运算符重载的成员候选（[[over.match.oper#3]] "在 T1 的作用域中搜索 `operator@`"）。

读本页前请熟悉 [[class.derived]]、[[class.mi]] 中基类子对象的概念：**非虚**基类每出现一次就是一个独立子对象，**虚**基类在整个对象中只有一个共享子对象。

## 搜索的定义（¶1）

¶1 在作用域 X 中从程序点 P 对名字 M 的**搜索**：

- 若 X 不是类（或类模板）的作用域，就是一次单次搜索；
- 若 X 是类或类模板 T 的作用域，则由下面 ¶2–¶7 的步骤定义。

注 1 一语道破：只有两种情况结果会与单次搜索不同——M 是**转换函数名**（*conversion-function-id*，¶7），或者单次搜索**什么也没找到**（于是去基类找，¶4）。换句话说："派生类里只要有一个同名声明，基类的就统统不看"——这就是**按名隐藏**。

## 查找集 S(N,C)（¶2–¶3）

¶2 类 C 中名字 N 的查找集记为 **S(N,C)**，由两部分组成：

- **声明集**（declaration set）：名为 N 的成员声明；
- **子对象集**（subobject set）：这些声明是在哪些（基类）子对象中找到的（可能经由 using 声明）。

声明集中，**类型声明（包括注入类名）被替换为它们指代的类型**。为什么？因为同一个类型经由不同基类路径找到时（例如两个基类各自继承同一个 `A`，于是都带有注入类名 `A`），声明虽然"是同一个"，子对象却不同；把它们看作同一个"类型"，合并时声明集相同，就不会被判为二义。

```cpp run ok
struct A {};
struct B : A {};
struct C : A {};
struct D : B, C {
    A* p;    // OK：A 经 B 与 C 两条路径找到（注入类名），但都指类型 A，声明集相同
};
```

¶3 **第一步：先看 C 自己。** 声明集是在 C 的作用域中对 N 的一次单次搜索的结果，搜索的出发点是：

- 若 P 位于 C 的**完整类上下文**（complete-class context，[[class.mem#10]]：函数体、默认实参、默认模板实参、noexcept 说明符、契约说明符、默认成员初始化器）中，则从 C 的 *class-specifier* **之后**搜索——也就是说，能看到整个类的所有成员；
- 否则从 P 搜索——只能看到 P 之前声明的成员。

若声明集非空，子对象集就是 `{C}`，计算结束。**派生类的同名声明隐藏一切基类的同名成员**，不论种类、签名如何。

```cpp run error
struct Base {
    void f(int);
    void f(double);
};
struct Der : Base {
    void f(const char*);     // 隐藏 Base::f 的全部重载
};
void t(Der& d) {
    d.Base::f(1);            // OK：限定名直接在 Base 中查找
    d.f(1);                  // error: 只找到 Der::f(const char*)，int 不能转换为 const char*
}
```

解决办法是把基类的重载"拉"进派生类：`using Base::f;`。using 声明本身绑定在 Der 的作用域里，单次搜索找到它后把它替换为 `Base::f` 的两个声明（[[basic.lookup#3]]）；并且 [[namespace.udecl#11]] 规定，若基类成员函数与派生类中声明的函数**对应**（同参数列表等），它不进入集合——派生类的版本"胜出"。

```cpp run ok
struct Base {
    void f(int);
    void f(double);
    void g(int);
};
struct Der : Base {
    using Base::f;           // 引入 Base::f(int)、Base::f(double)
    using Base::g;           // Base::g(int) 与下面的 Der::g(int) 对应 → 不引入
    void f(const char*);
    void g(int);
};
void t(Der& d) {
    d.f(1);                  // Base::f(int)
    d.f("x");                // Der::f(const char*)
    d.g(1);                  // Der::g(int)
}
```

!!! note "隐藏 vs 覆盖"
    名字隐藏是**查找**层面的事，虚函数覆盖（override）是**调用分派**层面的事，二者正交。`Der::f(const char*)` 隐藏了 `Base::f(int)`，但若 `Base::h` 是虚函数而 `Der::h` 签名相同，它既隐藏又覆盖：通过 `Base&` 调用 `h` 会分派到 `Der::h`，通过 `Der&` 查找 `h` 只找到 `Der::h`。

## 第二步：合并各直接基类（¶4–¶5）

¶4 若 C 自己的声明集为空，S(N,C) 初始为空；然后对**每个直接的、非依赖的**基类子对象 Bᵢ 递归计算 S(N,Bᵢ)，依次**合并**进 S(N,C)。

注 2 补充两点：

- C 不完整时（P 在类定义内部、但不在完整类上下文中），只考虑 *base-specifier* 出现在 P 之前的基类。
- **依赖基类不参与**：类模板 `template<class T> struct W : T` 中，基类 `T` 是依赖的，在模板定义中查找名字时根本不进入。实例化之后的类没有依赖基类。这就是模板中必须写 `this->m` 或 `W::m` 的根源——它们使名字成为依赖的，查找推迟到实例化（[[temp.dep.type]]）。

```cpp run error
template<class T> struct Base { void f(); };
template<class T> struct Der : Base<T> {
    void g() {
        this->f();           // OK：依赖的成员访问，推迟到实例化时查找
        Der::f();            // OK：限定名的查找上下文是当前实例化，依赖
        f();                 // error: 无限定查找不进入依赖基类 Base<T>
    }
};
```

¶5 **合并算法**。把 S(N,Bᵢ) 合并进当前的 S(N,C)：

| 情形 | 结果 |
|---|---|
| ¶5.1 S(N,Bᵢ) 为空，或其每个子对象都是 S(N,C) 中某个子对象的**基类子对象** | S(N,C) 不变（Bᵢ 这边找到的东西被"支配"了） |
| ¶5.1 反之，S(N,C) 为空，或其每个子对象都是 S(N,Bᵢ) 中某个子对象的基类子对象 | S(N,C) := S(N,Bᵢ)（新来的支配旧的） |
| ¶5.2 否则，若两边的**声明集不同** | **二义**：声明集记为"无效"，子对象集取并集。无效声明集在后续合并中与任何声明集都"不同" |
| ¶5.3 否则（声明集相同） | 声明集不变，子对象集取并集 |

"X 是 Y 的基类子对象"说的是**子对象**而非**类型**：在非虚菱形中，B 里的 A 与 C 里的 A 是两个不同的子对象，互不为基；而虚基类 V 只有一个子对象，是所有虚继承它的类的子对象的基。这就是虚继承下"支配"（dominance）规则的来源。

## 查找结果与"改变含义"（¶6）

¶6 搜索的结果是 S(M,T) 的声明集。

- 若是**无效集**——程序非良构（这就是"成员二义"）。
- 若它**不同于**在 T 的完整类上下文中搜索 M 的结果——程序非良构，**不要求诊断**（{{ifndr}}）。

第二条处理的是"类内名字含义被后来的声明改变"的情形：

```cpp ifndr
typedef int I;
struct S {
    I x;                 // 此处搜索 S 找不到 I（还未声明）→ 往外找到 ::I（int）
    typedef double I;    // 在完整类上下文中，搜索 S 会找到 S::I（double）
};                       // 两次结果不同 → IFNDR
```

这条规则的目的是：类成员声明的含义不依赖于成员声明的**顺序**——编译器可以单遍处理类定义，而程序员不能写出"重排成员就改变含义"的类。旧标准把它放在 [basic.scope.class] 里作为"重新求值规则"，C++23 移到这里并用"搜索结果不同"重新表述。GCC 会对此类代码给出"改变了 `I` 的含义"（changes meaning）的诊断；Clang 23 在本机测试中默认不诊断——两者都符合"不要求诊断"。

### 标准例 1 推演

```cpp run ok
struct A { int x; };                    // S(x,A) = { {A::x}, {A} }
struct B { float x; };                  // S(x,B) = { {B::x}, {B} }
struct C: public A, public B { };       // S(x,C) = { 无效, {A in C, B in C} }
struct D: public virtual C { };         // S(x,D) = S(x,C)
struct E: public virtual C { char x; }; // S(x,E) = { {E::x}, {E} }
struct F: public D, public E { };       // S(x,F) = S(x,E)
int main() {
    F f;
    f.x = 0;                            // OK：找到 E::x
}
```

逐步计算 S(x,F)：

1. F 自己没有 `x`，开始合并直接基类 D、E。
2. 合并 S(x,D) = {无效, {C 中的 A, C 中的 B}} 到空集：¶5.1 第二款，直接复制。
3. 合并 S(x,E) = {{E::x}, {E}}：现有子对象 "C 中的 A"、"C 中的 B" 是否都是 E 的基类子对象？C 是 **虚**基类，F 中只有一个 C 子对象，它同时是 D 和 E 的基类子对象；所以 C 中的 A 与 B 都是 E 的基类子对象——¶5.1 第二款成立，S(x,F) := S(x,E)。

可见"无效"状态在合并中**可以被消除**：只要后来有一个支配它的声明。把 `virtual` 去掉，D 和 E 各有自己的 C，第 3 步不成立，结果就是二义。

## 转换函数模板（¶7）

¶7 若 M 是非依赖的 *conversion-function-id*（如 `operator int*`），T 的成员**转换函数模板**也被考虑：对每个这样的模板 F，用"对应于 F 的声明"这一标准构造查找集 S(t,T)，其声明集（不得为无效集）并入结果。之后由重载决议/模板实参推导淘汰不能转换到目标类型的那些（[[temp.over]]）。

为什么需要特别规定？因为名字的"相同"对转换函数是按**类型**判断的（[[basic.pre#4]]）：`operator int*` 与模板 `template<class T> operator T*` 的名字并不"相同"，单次搜索找不到后者。¶7 确保 `p.operator int*()` 这样的显式调用、以及隐式转换的查找能考虑模板。

```cpp run ok
struct A {
    operator int();
    template<class T> operator T*();
};
struct B : A {
    operator double();      // 名字 operator double 与基类的转换函数都不"相同"，不隐藏它们
};
void t(B b) {
    int i = b;              // A::operator int
    int* p = b;             // A::operator T*，T = int
    double d = b;           // B::operator double
    (void)i; (void)p; (void)d;
}
```

## 静态成员、类型与枚举符：不怕多个子对象（¶8）

¶8 注 4：静态成员、嵌套类型、枚举符即使所在基类 T 在对象中有多个子对象，也能被无二义地找到；两个基类子对象共享它们共同的虚基类的非静态成员子对象。

用合并算法解释：经两条路径找到的 `A::s` 声明集相同（都是 `{A::s}`），¶5.3 只是合并子对象集——**查找本身不二义**。那 `pd->a` 为什么错？因为非静态成员的使用还要求把对象表达式转换到 `A`，而 D 中有两个 `A`——这是 [[expr.ref#9]] 与 [[class.access.base]] 的错误，不是查找的错误（¶11 的注也这样说）。

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
    pd->s++;          // OK：静态成员，只有一个 s
    int i = pd->e;    // OK：枚举符
    D::T k = i;       // OK：嵌套类型
    D::sf();          // OK：静态成员函数
    (void)k;
    pd->a++;          // error: 查找得到 {A::a}，但 D 到 A 的转换二义（两个 A 子对象）
}
```

!!! lawyer "查找无二义 ≠ 使用无二义"
    Clang 对 `pd->a` 的诊断是"非静态成员 `a` 在类型 `A` 的多个基类子对象中找到"，GCC 的诊断也把它表述为成员请求有歧义。两者都把它说成查找问题，但按标准它是查找成功后的**对象表达式转换**问题。区分这一点的实际意义：同样的名字换成静态成员就合法。

## 虚基类与支配（¶9）

¶9 注 5：使用虚基类时，被隐藏的声明可能沿一条**不经过**隐藏者的路径被到达——这**不是**二义。同样的结构若换成非虚基类，就是二义，因为没有一个唯一的声明能隐藏所有其他声明。

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

对象布局示意（标准图 1 的文字版）：

```text
        V (虚，唯一)
       / \
 W₁   B   C   W₂          W₁ 是 B 的非虚基类，W₂ 是 C 的非虚基类
   \ /     \ /
    B       C
     \     /
        D
```

逐步计算 S(x,D)：S(x,B) = {{B::x},{B}}（B 自己声明了 x）；S(x,C) = S(x,V) = {{V::x},{V}}（C 自己没有，W 没有 x，合并 V）。合并时：S(x,C) 的子对象 V 是 B 的基类子对象吗？是——因为 V 是虚基类，D 中唯一的 V 同时是 B 和 C 的基。于是 ¶5.1 第一款：S(x,D) 保持 {{B::x},{B}}。

S(y,D)：S(y,B) = {{B::y},{B}}；S(y,C) = {{W::y},{C 中的 W₂}}。W₂ 不是 B 的基类子对象（B 有自己的 W₁），B 也不是 W₂ 的基，声明集不同 → 无效 → 二义。

!!! tip "支配规则的直觉"
    "离得最近的声明胜出"并不准确。准确的说法是：**若一个声明所在的子对象是另一个声明所在子对象的派生（含该子对象作为基类子对象），前者支配后者**。虚继承让"同一个子对象"可被多条路径共享，于是支配关系能跨路径成立；非虚继承下各路径的子对象互相独立，无法支配。

## 派生到基类的转换必须无二义（¶10）

¶10 从派生类的指针或指代对象的表达式，显式或隐式地转换到其某个基类的指针或引用时，必须**无二义地**指向唯一一个表示该基类的对象。

```cpp run error
struct V { };
struct A { };
struct B : A, virtual V { };
struct C : A, virtual V { };
struct D : B, C { };

void g() {
    D d;
    B* pb = &d;       // OK
    A* pa = &d;       // error: 二义：C 里的 A 还是 B 里的 A？
    A* pa2 = pb;      // OK：先到 B，再到唯一的 A
    V* pv = &d;       // OK：只有一个 V 子对象
    (void)pa2; (void)pv;
}
```

这条放在"成员名字查找"里，是因为它与 ¶8/¶11 是一回事：查找只决定"哪个声明"，到哪个**子对象**取成员则由这种转换决定。

## 查找无二义但使用仍可能二义（¶11）

¶11 注 6 与例 5 集中展示了上面的区分：

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
        f();                        // 二义：this 转换到 B1* 二义（D 中有两个 B1）
        f(0);                       // 无二义：选中静态的 B1::f(int)，不需要对象
        f(0.0);                     // 无二义：B2 只有一个
        int B1::* mpB1 = &D::i;     // 无二义：&D::i 的类型是 int B1::*，无需转换
        int D::* mpD = &D::i;       // 二义：int B1::* → int D::* 的转换二义
    }
};
```

要点：

- 两个 using 声明都绑定在 D 中，单次搜索 D 找到它们并替换为 `{B1::f(), B1::f(int), B2::f(double)}`——D 自己的声明集非空，查找就此结束，**不会**再去基类合并，所以没有子对象层面的二义。
- `f()` 选中非静态的 `B1::f()`，需要把隐式的 `*this` 转换到 `B1`——D 中有两个 B1，转换二义。
- `f(0)` 选中静态成员，不需要对象，合法。
- `&D::i`：按 [[expr.unary.op]]，限定名指名类 C 的成员时结果是 `int C::*`，这里 C 是声明 `i` 的 B1，所以第一行无需任何转换；第二行需要把 `int B1::*` 转换为 `int D::*`（[[conv.mem]]），这要求 B1 是 D 的无二义基类，失败。

!!! impl "编译器的偏差"
    在本机（Clang 23）测试，`int B1::* mpB1 = &D::i;` 被 Clang 拒绝，诊断为"非静态成员 `i` 在类型 `B1` 的多个基类子对象中找到"。按标准这一行是良构的（标准例 5 明确标注 Unambiguous）——Clang 在形成成员指针时过早地检查了子对象唯一性。其余各行 Clang 的判断与标准一致。

## 更多例子：菱形继承全家福

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
    d.B::x = 1;               // OK：限定名先在 B 中查找，B 中只有一个 A
    vd.x = 1;                 // OK：VC::x 支配 A::x（经 VB 到达的是同一个虚基类 A）
    vd.f();                   // OK：只有一个 A 子对象
    d.x = 1;                  // error: 两个 A 子对象，对象表达式转换二义
}
```

注意 `d.B::x`：限定名 `B::x` 在 B 中查找，得到 `A::x`；然后 [[expr.ref#9]] 检查 "`x` 的直接所属类 A 是否是**指定类**（designating class）B 的无二义基类"——是的。再从 `d` 转换到 B 也无二义。

### 不同种类的同名成员

二义不要求"同种"：一个基类的数据成员与另一个基类的成员函数同名，同样是 ¶5.2 的"声明集不同"。用 using 声明在派生类中选定一个即可消解：

```cpp run error
struct B1 { int x; };
struct B2 { void x(); };
struct D : B1, B2 { };
struct E : B1, B2 { using B1::x; };   // 在 E 中声明，查找在 E 就结束

void t(D d, E e) {
    e.x = 1;          // OK：E::x（即 B1::x）
    d.x;              // error: 声明集 {B1::x} 与 {B2::x} 不同 → 二义
}
```

### 私有继承与注入类名

¶2 说注入类名也参与成员查找。一个著名的意外：

```cpp run error
struct P { };
struct Q : private P { };
struct R : Q {
    ::P* good;        // OK：限定名直接在全局命名空间查找
    P* bad;           // error: 无限定查找在 R 中搜索 → 合并基类 Q → 找到 P 的注入类名，
                      //        而 P 是 Q 的私有基类，经由 Q 不可访问
};
```

查找本身找到的是 `P` 的注入类名（指代类型 P），完全正确；但访问检查（在查找之后，[[basic.lookup#1]]）发现这个名字是通过私有基类继承来的。修法就是写 `::P`。

!!! impl "实现视角"
    - Clang 用 `CXXRecordDecl::lookupInBases` 与 `CXXBasePaths` 记录"在哪些路径上找到了什么"，正对应查找集的子对象集。它的诊断区分两种情形：不同类型的基类中找到同名成员（¶5.2 的二义）、同一类型的多个基类子对象中找到非静态成员（¶11 的使用二义）。
    - Itanium ABI 层面：查找完全是编译期行为，不影响布局；但它决定了取哪个子对象的偏移——非虚基类的偏移是静态常量，虚基类的偏移要经 vtable 中的 vbase offset 在运行时取得。

!!! history "历史与演进"
    - **C++98**：本节用"支配"等文字描述多继承下的查找，与静态成员、类型、using 声明的交互有不少含糊之处。
    - **C++11**：已采用"查找集 S(f,C) = 声明集 + 子对象集"的合并算法（即今天 ¶2–¶5 的骨架），修正了旧文字。
    - **C++23**：P1787R6 把它重新定位为"类作用域中的**搜索**"，作为所有查找的组件；把旧 [basic.scope.class] 的"重排成员不得改变含义"规则改写为 ¶6 的 IFNDR；明确"从 *class-specifier* 之后搜索"与完整类上下文的关系。

## 陷阱

!!! pitfall "以为重载会跨作用域"
    派生类声明了一个 `f`，基类的所有 `f` 都看不见了——即便参数完全不同。这是 C++ 最常见的意外之一，也是 Clang 的 `-Woverloaded-virtual` 警告存在的原因（派生类的虚函数隐藏了基类同名的其他虚重载）。

!!! pitfall "以为 using 声明会让基类版本覆盖派生类版本"
    `using Base::f;` 引入的函数若与派生类中声明的函数参数列表相同，被**排除**（[[namespace.udecl#11]]），不会冲突也不会二义。

!!! pitfall "模板里忘了 this->"
    依赖基类的成员不在无限定查找的范围内。某些旧编译器（以及 MSVC 的非 `/permissive-` 模式）会"帮你"找到，代码换编译器就挂。

## 思考题

!!! question "思考题 1"
    ```cpp
    struct A { void f(); };
    struct B : virtual A { void f(); };
    struct C : virtual A { };
    struct D : B, C { };
    struct E : D, A { };   // 再加一个非虚的 A
    ```
    `D{}.f()` 与 `E{}.f()` 的查找结果各是什么？

<details markdown="1">
<summary>答案</summary>

S(f,D)：S(f,B) = {{B::f},{B}}，S(f,C) = {{A::f},{虚 A}}；虚 A 是 B 的基类子对象，被支配 → {{B::f},{B}}，`D{}.f()` 调用 `B::f`。

S(f,E)：先合并 S(f,D) = {{B::f},{B}}；再合并非虚基类 A 的 S(f,A) = {{A::f},{非虚 A}}。这个非虚 A 是 E 的直接基类，与 D 里的虚 A 是**不同**的子对象，它不是 B 的基类子对象，B 也不是它的基 → 声明集不同 → 二义，`E{}.f()` 非良构。（编译器还会警告直接基类 A 因二义而不可访问。）
</details>

!!! question "思考题 2"
    为什么 ¶2 要求把类型声明"替换为它们所指的类型"？举一个若不替换就会误判为二义的例子。

<details markdown="1">
<summary>答案</summary>

例如在 B 中 `using T = int;`，在 C 中 `typedef int T;`，D 继承 B 和 C：两条路径找到的是**不同的声明**（两个别名声明），若按声明比较则 ¶5.2 判为二义；替换为类型后两边都是 `{int}`，¶5.3 合并，`D::T` 无二义。注入类名经多条路径找到时同理（本页第一个例子）。
</details>

## 小结

| 规则 | 要点 |
|---|---|
| 搜索 vs 单次搜索 | 类作用域的搜索 = 自己找不到就递归合并直接非依赖基类 |
| 按名隐藏 | 派生类有任何同名声明，基类同名成员全部不考虑（用 using 声明引回） |
| 完整类上下文 | 函数体等处从类末尾搜索，其他位置从 P 搜索；两者不同 → IFNDR |
| 合并 | 支配者胜出；声明集不同 → 无效（二义）；相同 → 合并子对象 |
| 虚基类 | 共享子对象使跨路径支配成立 |
| 静态成员/类型/枚举符 | 声明集相同即无二义 |
| 非静态成员 | 查找无二义后，对象到所属基类的转换仍须无二义（[[expr.ref#9]]） |
| 依赖基类 | 不参与模板定义中的查找，需 `this->` |
