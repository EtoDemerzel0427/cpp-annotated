---
title: 构造与析构
summary: 对象正在构造或析构时能对它做什么；这段时间里虚函数调用、typeid 和 dynamic_cast 都把它当作当前构造函数或析构函数所属类的对象。
status: done
related: class.base.init, basic.life, class.virtual, class.abstract, expr.typeid, expr.dynamic.cast, class.dtor, except.ctor, dcl.contract.func
tags: 构造函数, 析构函数, 虚函数, 多态, UB
updated: 2026-10-19
---

!!! tldr
    - 在基类构造函数里调用虚函数，调用的是基类自己的版本，不是派生类的覆盖函数。析构时同理。这段时间里 `typeid` 和 `dynamic_cast` 也把对象当作当前构造或析构函数所属类的对象。
    - 如果按这条规则分派到的是纯虚函数，行为未定义；Itanium ABI 下程序打印 Pure virtual function called 后终止。
    - 对象有非平凡构造函数时，构造开始前访问它的成员或基类是 UB；有非平凡析构函数时，析构结束后同样是 UB。
    - 初始化期间不经由构造函数的 `this` 读取正在初始化的对象，读到的值是未指定的。
    - 构造期间转换到基类，要求转换路径上的各个类都已开始构造；经由其他子对象发起的虚调用可能是 UB。

## 基类构造函数里的虚调用

```cpp run title="virtual-in-ctor.cpp" ok
#include <cstdio>

struct Base {
    Base() { call(); }
    virtual ~Base() { call(); }
    virtual const char* name() const { return "Base"; }
    void call() const { std::printf("%s\n", name()); }
};

struct Derived : Base {
    Derived() { call(); }
    ~Derived() override { call(); }
    const char* name() const override { return "Derived"; }
};

int main() {
    Derived d;   // Base / Derived
}                // Derived / Base
```

`Base()` 执行时，`Derived` 的成员一个都还没有初始化。如果这时调用 `Derived::name()`，它很可能读到未初始化的成员。析构反过来：`~Base()` 执行时，`Derived` 的成员已经全部析构了。

所以 C++ 让对象的动态类型在构造和析构期间逐步变化：构造 `Base` 部分时它表现为 `Base`，构造 `Derived` 部分时表现为 `Derived`，析构时按相反顺序退回。Java 和 C# 的选择相反，基类构造函数里会调用到派生类的覆盖函数，此时派生类的字段还是默认的零值。

### 规则（¶4）

¶4 成员函数（包括虚函数）可以在构造或析构期间调用。如果虚函数是从构造函数或析构函数中直接或间接调用的，并且调用作用的对象就是正在构造或析构的那个对象（记作 *x*），那么被调用的是构造函数或析构函数所属的类中的[[g:final-overrider|最终覆盖函数]]，而不是更派生类中覆盖它的函数。

这里的构造或析构期间，包括初始化或析构非静态数据成员的过程，以及 {{c++26}} 构造函数的后置条件断言和析构函数的前置条件断言的求值（[[dcl.contract.func]]）。上例中 `call()` 是非虚函数，它对 `name()` 的调用是间接的，同样受这条规则约束。

!!! impl "实现：构造过程中改写虚表指针"
    在 Itanium ABI 和 MSVC ABI 中，每个构造函数在初始化完基类之后、初始化成员之前，把对象的虚表指针（vptr）设为本类的虚表；析构函数在执行函数体之前把它设回本类的虚表，之后基类的析构函数再把它改成基类的。`typeid` 读的是虚表里的类型信息，`dynamic_cast` 也依赖它，所以三者看到的都是当前的类。

    这条规则也给了优化器一个保证：构造函数里对 `this` 的虚调用一定落到本类的最终覆盖函数，可以去虚化。本机 Clang 23 在 `-O1` 下对 `Base::Base() { sink(name()); }` 生成的就是对 `Base::name` 的直接调用。

### 分派到纯虚函数

```cpp run title="pure-virtual.cpp" ub
struct B {
    B() { init(); }
    void init() { f(); }     // 间接调用，编译器不警告
    virtual void f() = 0;
    virtual ~B() = default;
};
struct D : B { void f() override {} };

int main() { D d; }   // UB：B 构造期间 f() 是纯虚的 B::f
```

按 ¶4 分派到的最终覆盖函数如果是纯虚函数，行为未定义（[[class.abstract#6]]）。Itanium ABI 下，抽象类虚表中纯虚函数的位置指向 `__cxa_pure_virtual`；本机运行上例，libc++abi 打印 Pure virtual function called! 后 abort。如果 `B()` 直接调用 `f()`，本机 Clang 23 会给出 `-Wcall-to-pure-virtual-from-ctor-dtor` 警告。

### 经由其他子对象发起的调用

¶4 最后一句：如果虚调用使用了显式的成员访问（`p->f()` 或 `obj.f()`），而对象表达式指向 *x* 的完整对象或它的某个基类子对象，但不是 *x* 本身或 *x* 的基类子对象，行为未定义。

标准例 4，加上输出：

```cpp run title="virtual-other-path.cpp" ub
#include <cstdio>

struct V {
    virtual void f() { std::puts("V::f"); }
    virtual void g() { std::puts("V::g"); }
    virtual ~V() = default;
};
struct A : virtual V {
    void f() override { std::puts("A::f"); }
};
struct B : virtual V {
    void g() override { std::puts("B::g"); }
    B(V*, A*);
};
struct D : A, B {
    void f() override { std::puts("D::f"); }
    void g() override { std::puts("D::g"); }
    D() : B((A*)this, this) {}
};

B::B(V* v, A* a) {
    f();      // V::f：B 的最终覆盖函数
    g();      // B::g，不是 D::g
    v->g();   // OK：V 是 B 的基类，B::g
    a->f();   // UB：A 不是 B 的基类
}

int main() { D d; }
```

构造 `B` 子对象时，*x* 是 `B` 子对象。`A` 子对象已经构造完毕，但它属于完整对象 `D`，不是 *x* 的一部分。此时它的 vptr 指向什么，取决于实现在何时、以什么顺序设置各个子对象的 vptr，标准不愿约束这些细节，于是定为 UB。

本机 Clang 23 运行上例，`a->f()` 打印 `V::f`，既不是 `A::f` 也不是 `D::f`。有虚基类时，中间类在构造期间使用的是特殊的构造虚表（construction vtable，经由 [[class.base.init]] 提到的 VTT 传入）。一种可能的解释是：`A` 与虚基类 `V` 共用 vptr 的位置，`B` 的构造函数为 `V` 安装构造虚表时，也就改写了 `A` 子对象看到的 vptr。

## `typeid` 和 `dynamic_cast`（¶5–¶6）

```cpp run title="typeid-dyncast.cpp" ok
#include <cstdio>
#include <typeinfo>

struct V { virtual void f() {} virtual ~V() = default; };
struct A : virtual V {};
struct B : virtual V { B(V*, A*); };
struct D : A, B { D() : B((A*)this, this) {} };

B::B(V* v, A*) {
    std::printf("%d\n", typeid(*this) == typeid(B));      // 1
    std::printf("%d\n", typeid(*v) == typeid(B));         // 1
    std::printf("%d\n", dynamic_cast<B*>(v) == this);     // 1
    std::printf("%d\n", dynamic_cast<D*>(v) == nullptr);  // 1
    // typeid(*a); dynamic_cast<B*>(a);  都是 UB：A 不是 B 的基类
}

int main() { D d; }
```

¶5 在构造函数（包括非静态数据成员的 *mem-initializer* 和默认成员初始化器）、析构函数，或从它们直接、间接调用的函数中，如果 `typeid` 的操作数指向正在构造或析构的对象，结果是表示构造函数或析构函数所属类的 `std::type_info`。如果操作数的静态类型既不是这个类，也不是它的基类，行为未定义。

¶6 `dynamic_cast` 在同样的语境中，把正在构造或析构的对象看作一个最派生对象，类型是构造函数或析构函数所属的类。所以上例中 `dynamic_cast<D*>(v)` 是空指针：此时对象被当作 `B`，其中没有 `D` 的部分。操作数的静态类型不是指向这个类或其基类的指针（或这些类的对象）时，行为未定义。

¶4–¶6 合起来就是一句话：构造和析构期间，对象的动态类型是当前构造函数或析构函数所属的类。

| 时刻 | 虚调用分派到 | `typeid(*this)` | `dynamic_cast<Derived*>(this)` |
|---|---|---|---|
| `Base` 构造函数中 | `Base` 的最终覆盖函数 | `Base` | 空指针 |
| `Derived` 构造函数中 | `Derived` 的最终覆盖函数 | `Derived` | 非空 |
| 生命周期内 | 最派生类的最终覆盖函数 | 最派生类 | 非空 |
| `Derived` 析构函数中 | `Derived` 的最终覆盖函数 | `Derived` | 非空 |
| `Base` 析构函数中 | `Base` 的最终覆盖函数 | `Base` | 空指针 |

## 构造开始之前、析构结束之后（¶1）

```cpp run title="before-ctor.cpp" ub
struct X { int i; };
struct Y : X { Y() {} };              // 非平凡构造函数
struct A { int a; };
struct B : public A { int j; Y y; };  // 因为 y，构造函数非平凡

extern B bobj;
B* pb = &bobj;                        // OK：完整对象的地址
int* p1 = &bobj.a;                    // UB：基类的成员
int* p2 = &bobj.y.i;                  // UB：成员的成员
A* pa = &bobj;                        // UB：转换到基类
B bobj;                               // 定义，在上面几行之后初始化

extern X xobj;
int* p3 = &xobj.i;                    // OK：X 的构造函数都是平凡的
X xobj;

int main() {}
```

¶1 对象有非平凡构造函数时，在构造函数开始执行之前引用它的任何非静态成员或基类，是未定义行为。对象有非平凡析构函数时，在析构函数执行完毕之后引用它的成员或基类，同样是未定义行为。这里的引用不只是读写值，取成员地址、转换到基类都算。

标准例 1 用一个先声明、后定义的全局对象演示：全局变量按定义顺序动态初始化（[[basic.start.dynamic]]），`p1` 等初始化时 `bobj` 还没有构造。

平凡构造函数什么也不做，所以只限非平凡的情形。非平凡构造函数开始之前，对象的内部结构（vptr、虚基类的位置）可能还没有建立，连成员在哪里都可能算不出来。`pa = &bobj` 对非虚基类只是加一个常量偏移，实践中碰巧能用；如果 `A` 是虚基类，偏移要从还没写入的 vptr 里读。标准对两种情况一视同仁。

例 1 的第二部分在构造函数里演示同一个问题：

```cpp run title="before-member-ctor.cpp" ub
struct W { int j; };
struct X : public virtual W {};
struct Y {
    int* p;
    X x;
    Y() : p(&x.j) {}   // UB：x 还没有开始构造
};

int main() { Y y; (void)y; }
```

`p` 先于 `x` 初始化，`&x.j` 要经由虚基类 `W` 定位 `j`，而 `x` 的构造还没开始。

## 不经 `this` 读取正在初始化的对象（¶2）

```cpp run title="self-ref-global.cpp" unspecified
#include <cstdio>

extern struct D d;
struct D {
    D(int a) : a(a), b(d.a) {}   // 经由全局名 d，不经由 this
    int a, b;
};
D d = D(1);                      // d.b 的值未指定

int main() { std::printf("%d\n", d.b); }
```

¶2 对象初始化期间，如果通过一个不是（直接或间接）从构造函数的 `this` 得到的 glvalue 访问它的子对象的值或对象表示，得到的值是未指定的。

C++17 起 `D(1)` 直接初始化 `d`（[[class.copy.elision]]），构造函数里的 `this` 就是 `&d`，`d.a` 确实指同一个对象。但这次访问没有经由 `this`，值仍是未指定的。本机 Clang 23 输出 `1`，标准不保证。要读成员，写 `b(this->a)`。

这条规则是为优化服务的。标准例 2 的另一部分：

```cpp
struct C;
void no_opt(C*);

struct C {
    int c;
    C() : c(0) { no_opt(this); }
};

const C cobj;

void no_opt(C* cptr) {
    int i = cobj.c * 100;   // 值未指定
    cptr->c = 1;            // 经由 this 修改：OK
    std::printf("%d\n", cobj.c * 100);   // 值未指定
}
```

`cobj` 是 `const` 对象，编译器希望假设 `cobj.c` 初始化后不会再变，以便对它做常量折叠或缓存在寄存器里。但 `const` 对象在构造期间可以被修改，`const` 语义在最派生对象的构造函数结束时才生效（[[class.ctor.general#4]]）。¶2 的折中是：经由 `this` 的访问可靠，绕开 `this` 的访问只得到未指定的值。这是未指定行为，不是 UB：程序仍受约束，只是不知道读到哪一个值。

## 转换到基类，形成成员指针（¶3）

```cpp run title="conversion-path.cpp" ub
struct A {};
struct B : virtual A {};
struct C : B {};
struct D : virtual A { D(A*) {} };
struct X { X(A*) {} };

struct E : C, D, X {
    E() : D(this),   // UB：E* → A* 可能经过 D，而 D 还没开始构造
          X(this) {} // OK：此时 C、B、D、A 都已构造完毕
};

int main() { E e; }
```

¶3 有两个前提条件：

- 把指向类 `X` 对象的指针（或 glvalue）转换为指向其基类 `B` 的指针（或引用）时，`X` 的构造，以及 `X` 的所有直接或间接派生自 `B` 的基类的构造，都必须已经开始，且析构都尚未完成，否则行为未定义。
- 形成指向对象 `obj` 的直接非静态成员的指针（或访问该成员的值）时，`obj` 的构造必须已经开始、析构尚未完成，否则行为未定义。

第一条要看转换路径。`D(this)` 把 `E*` 转换为 `A*`，编译器可以经由 `D` 去找虚基类 `A`，这要读取 `D` 子对象里的信息，而 `D` 正是还没开始构造的那个。标准例的注释指出，写成 `D((C*)this)` 就是良定义的：`E*` 到 `C*` 没问题（`E()` 已经开始），`C*` 到 `A*` 也没问题（`C` 已经构造完毕）。

第二条比较宽松，只要 `obj` 已经开始构造，不要求那个成员已经初始化。所以在 *mem-initializer* 里写 `r(a)`（引用绑定到尚未初始化的成员，[[class.base.init#17]]）或 `p(&member)` 都是良定义的，只要不像 ¶1 的第二个例子那样经过一个尚未构造的成员的虚基类。

## 常见误解

!!! pitfall "用基类构造函数里的虚调用实现模板方法"
    `Base() { init(); }` 想让派生类定制 `init()`，派生类的版本不会被调用。可以改用两段式初始化（构造后再调用 `init()`）、工厂函数，或者把定制点作为构造函数参数传入。析构函数里的 `cleanup()` 同理，派生类的清理应写在派生类自己的析构函数里。

!!! pitfall "在构造函数里发布 this"
    把 `this` 交给其他线程或全局注册表后，别的代码可能在对象还在构造时就访问它：虚调用分派到基类版本、成员还没初始化、不经 `this` 读到的值未指定（¶2），跨线程没有同步时还构成数据竞争。应当在构造完成之后再发布。

## 思考题

!!! question "思考题"
    下面的程序输出什么？

    ```cpp
    #include <cstdio>
    struct B;
    struct M { M(B* b); };
    struct B {
        M m;
        B() : m(this) {}
        virtual const char* who() const { return "B"; }
        virtual ~B() = default;
    };
    struct D : B {
        const char* who() const override { return "D"; }
    };
    M::M(B* b) { std::puts(b->who()); }
    int main() { D d; }
    ```

<details markdown="1">
<summary>答案</summary>

输出 `B`。`M` 的构造函数在初始化 `B` 的成员 `m` 时调用，¶4 明确包括非静态数据成员的构造期间。`b` 指向的正是正在构造的 `B` 对象（*x* 本身），所以分派到 `B::who`。实现上，`B` 的构造函数在初始化成员 `m` 之前，已经把 vptr 设为 `B` 的虚表。
</details>

<details class="fine" markdown="1"><summary>沿革</summary>

本节的主体规则（¶1、¶3–¶6）在 C++98 中已经存在，措辞基本不变。C++26 引入契约后，¶4 把构造函数的后置条件和析构函数的前置条件也纳入按当前类分派的范围；[[class.base.init#18]] 则把构造函数前置条件、析构函数后置条件中的成员函数调用定为 UB。

</details>
