---
title: 抽象类
summary: 纯虚函数怎么写、什么时候需要定义；哪些类是抽象类，抽象类型能在哪里出现；在构造或析构期间虚调用纯虚函数为什么是未定义行为。
status: done
papers: P0929R2
related: class.virtual, class.dtor, class.mem, class.cdtor, dcl.fct.def.general, expr.call, expr.new, basic.def, dcl.type.decltype
tags: 类, 虚函数, 抽象类, UB
updated: 2026-10-19
---

!!! tldr
    - 用 `= 0` 声明的虚函数是纯虚函数；只要一个纯虚函数的最终覆盖者仍是纯虚的，这个类就是抽象类，不能单独创建对象。
    - 纯虚函数可以有定义（写在类外），只有用限定名 `Base::f()` 调用时才需要它；纯虚析构函数则一定要定义。
    - 派生类漏掉一个纯虚函数没有覆盖，自己也会成为抽象类；纯虚函数也可以覆盖一个已有实现的虚函数，让类重新变成抽象的。
    - C++20 起，只有函数定义和函数调用处才检查形参、返回类型是不是抽象类，单纯的声明不受限制。
    - 在抽象类的构造函数或析构函数里，直接或间接地虚调用一个纯虚函数是未定义行为，常见表现是 pure virtual function called 后程序终止。

```cpp error
struct Shape {
    virtual double area() const = 0;   // 纯虚函数
    virtual ~Shape() = default;
};
struct Square : Shape {
    double side = 1;
    double area() const override { return side * side; }
};
Square sq;          // OK
Shape* p = &sq;     // OK: 指向抽象类的指针
Shape s;            // error: Shape 是抽象类
```

`Shape` 只表示一个一般概念，有意义的是它的具体变体。¶1 的注说的就是这种用法：抽象类表示一般概念，或者定义一个接口，由派生类提供不同的实现。C++ 没有 `interface` 关键字，全部成员函数都是纯虚、又没有数据成员的抽象类就相当于接口。

C++ 也不用关键字声明抽象性，而是从纯虚函数推出来。阅读本页需要知道覆盖和最终覆盖者的含义，见 [[class.virtual]]。

## 纯虚函数（¶2）

¶2 在类定义中的函数声明里写上 ***pure-specifier***（`= 0`），就把这个虚函数指定为**纯虚函数**（pure virtual function）。至少有一个纯虚函数的类是**抽象类**（abstract class），¶4 会把这个定义说得更精确。

`= 0` 的语法细节在 [[class.mem.general]]：

- 记号序列必须恰好是 `= 0`，写成 `= 0L`、`= false`、`= nullptr` 都不行。
- 只能用于虚函数的声明，不能用于友元声明（[[class.mem.general#17]]）。
- 它写在最后：声明符、*virt-specifier-seq*（`override`、`final`）、C++26 的契约说明符（`pre`、`post`），然后才是 `= 0`，例如 `void f() override = 0;`。

```cpp title="pure-specifier.cpp" error
struct A {
    virtual void f() = 0;            // OK
    virtual void g() = 0L;           // error: 不是 pure-specifier
    void h() = 0;                    // error: 非虚函数
    virtual void k() override = 0;   // error: 没有覆盖任何函数
};
struct B : A {
    void f() override = 0;           // OK: 覆盖后仍声明为纯虚
};
```

¶2 的注 3 指出，抽象类只能用作其他类的基类：除了作为派生类对象的基类子对象，不能创建抽象类的对象。

### 纯虚函数也可以有定义

```cpp run title="pure-default-impl.cpp" ok
#include <cstdio>
struct Shape {
    virtual void draw() const = 0;
    virtual ~Shape() = default;
};
void Shape::draw() const {      // 纯虚函数的定义
    std::puts("Shape: outline");
}
struct Circle : Shape {
    void draw() const override {
        Shape::draw();          // 限定调用，用到上面的定义
        std::puts("Circle: fill");
    }
};
int main() {
    Circle c;
    const Shape& s = c;
    s.draw();
}
```

¶2 最后一句规定：只有用 *qualified-id* 语法调用纯虚函数，或者如同这样调用（见下一小节）时，才需要它的定义。虚调用永远不会落到纯虚函数上，所以它的定义只能通过 `Shape::draw()` 这样的限定调用用到。

这种写法表达的意思是：派生类必须自己决定行为，但可以选择复用一份默认实现。普通虚函数允许派生类什么都不写就继承默认行为，纯虚函数加定义的约束更强。

¶2 的注 4 说明，同一个声明不能既有 `= 0` 又给出函数体，所以定义只能写在类外：

```cpp error
struct C {
    virtual void f() = 0 { }   // error
};
```

### 纯虚析构函数必须定义

```cpp run title="pure-virtual-dtor.cpp" ok
#include <cstdio>
struct Interface {
    virtual ~Interface() = 0;   // 让类成为抽象类
};
Interface::~Interface() { std::puts("~Interface"); }   // 必须定义

struct Impl : Interface {};     // Impl::~Impl 覆盖它，Impl 不是抽象类

int main() { Impl i; }          // 输出 ~Interface
```

一个类找不到合适的成员函数设为纯虚，又想让它成为抽象类时，常用的办法是把析构函数声明为纯虚。

上一小节说的如同用限定名调用，指的就是析构函数。派生类的析构函数执行完自己的函数体后，会调用各基类的析构函数，调用方式如同用限定名，不经过虚调用（[[class.dtor]]）。所以纯虚析构函数一定会被调用。[[class.dtor#11]] 也直接规定：析构函数是虚函数、而程序创建了这个类或其派生类的对象时，必须定义这个析构函数。忘了定义，在 Itanium ABI 下表现为找不到 `Interface::~Interface()` 的链接错误。

## 抽象性随继承传递（¶4–¶5）

¶4 给出精确的定义：一个类是抽象类，当且仅当它至少有一个纯虚函数，而这个函数的最终覆盖者是纯虚的。

所以派生类没有覆盖全部纯虚函数时，它本身仍是抽象类。这是标准例 3 的完整版本：

```cpp run title="abstract-inherit.cpp" ok
#include <type_traits>
class shape {
public:
    virtual void rotate(int) = 0;
    virtual void draw() = 0;
    virtual ~shape() = default;
};
class ab_circle : public shape {
public:
    void rotate(int) override {}
    // 没有覆盖 draw：最终覆盖者仍是纯虚的 shape::draw
};
class circle : public shape {
public:
    void rotate(int) override {}
    void draw() override {}
};
static_assert(std::is_abstract_v<shape>);
static_assert(std::is_abstract_v<ab_circle>);
static_assert(!std::is_abstract_v<circle>);
int main() { circle c; (void)c; }
```

¶5 的注指出了反方向的两种可能：抽象类可以派生自非抽象类；纯虚函数可以覆盖非纯虚函数。后者把一个已有实现的虚函数重新变成纯虚的，强制更下层的派生类重新实现它：

```cpp run title="re-abstract.cpp" ok
#include <type_traits>
struct Concrete {
    virtual int f() { return 1; }
    virtual ~Concrete() = default;
};
struct Abs : Concrete { int f() override = 0; };
struct Again : Abs { int f() override { return 3; } };
static_assert(!std::is_abstract_v<Concrete>);
static_assert(std::is_abstract_v<Abs>);
static_assert(!std::is_abstract_v<Again>);
int main() { Again a; return a.f() == 3 ? 0 : 1; }
```

!!! lawyer "最终覆盖者是相对哪个类计算的"
    判断类 X 是否抽象时，最终覆盖者以 X 本身为最派生类来计算。虚继承下，一个纯虚函数可能只在一条分支上被覆盖：

    ```cpp
    struct A { virtual void f() = 0; };
    struct B : virtual A { void f() override; };
    struct C : virtual A {};
    struct D : B, C {};
    ```

    在 `C` 中，`A::f` 的最终覆盖者是纯虚的 `A::f`，所以 `C` 是抽象类。在 `D` 中，共享的 `A` 子对象的 `f` 的最终覆盖者是 `B::f`，所以 `D` 不是抽象类。

## 抽象类型能出现在哪里（¶3）

规则的出发点是：受限制的是创建抽象类型的对象，而不是提到这个类型。¶3 的注把分散在各处的规范性规则汇总了一遍：

```cpp title="abstract-uses.cpp" error
struct A { virtual void f() = 0; };

A make();                    // OK: 只是声明
void take(A);                // OK: 只是声明
struct S { A g(); };         // OK: 成员函数声明
using F = A(A);              // OK: 函数类型
using T = decltype(make());  // OK: decltype 不创建临时对象
A* p;                        // OK
void ref(A& r);              // OK

A make2() { }                // error: 函数定义的返回类型
void use(A& a) { take(a); }  // error: 调用时形参是抽象类型
A arr[2];                    // error: 抽象类型的数组对象
void h() { A{}; }            // error: 显式类型转换的结果
```

| 场合 | 是否允许 | 依据 |
|---|---|---|
| 函数定义的形参类型或返回类型 | 不允许，deleted 函数除外 | [[dcl.fct.def.general#2]] |
| 函数调用时按值传递的形参 | 不允许 | [[expr.call#7]] |
| 只是声明（不是定义）的函数的形参、返回类型 | 允许（C++20 起） | |
| 显式类型转换 `A()`、`A{}`、`static_cast<A>(x)` | 不允许，结果会是抽象类型的 prvalue | [[basic.lval#9]] |
| 变量定义、`new A`、非静态数据成员 | 不允许，它们的数组也不允许 | [[basic.def#5]]、[[expr.new]]、[[class.mem.general#20]] |
| 只作为类型的数组 `A[2]` | 允许（[[dcl.array]] 没有禁止） | |
| `decltype` 的操作数是返回抽象类型的调用 | 允许 | [[dcl.type.decltype#2]] |
| 指针、引用、`sizeof`、`typeid`、`std::is_abstract` | 允许 | |

`decltype(make())` 能用，是因为当 `decltype` 的操作数是函数调用时，不会把 prvalue 实质化为临时对象，也就没有对象被创建（[[dcl.type.decltype#2]]）。¶3 注中 except as specified in [dcl.type.simple] 说的就是这个例外。

!!! impl "Clang 的偏差"
    按当前的 [[dcl.array]]，只作为类型使用的 `using X = A[2];` 不创建对象，应当合法。截至写作时，Clang 23 仍以 `array of abstract class type` 为由拒绝它。另外，Clang 在 `-std=c++17` 下也接受上面那些只是声明的用法，没有按语言版本区分。

### 为什么 C++20 要放宽

C++17 及以前，抽象类型根本不能作为函数的形参或返回类型，哪怕只是声明。这带来两个问题。

第一是时序。类要到右花括号处才完整，在那之前不知道它是不是抽象的。在 `struct A { A f(); virtual void g() = 0; };` 中，编译器看到 `A f();` 时还不知道 `A` 是抽象类，只能事后回头检查，不同编译器的处理也不一致。

第二是模板中的意外错误。实例化一个只是声明的函数，比如某个 trait 中的 `T f();`，就可能因为 `T` 是抽象类而产生硬错误，尽管这个函数根本不会被定义或调用。

[[P0929R2]] 把检查推迟到真正需要对象的地方，也就是函数定义和函数调用。不完整类型一直是这样处理的：它可以出现在函数声明里，只在定义或调用时必须完整。抽象性现在被当作另一种不能创建对象的情况，与不完整类型同等对待。

## 构造与析构期间调用纯虚函数（¶6）

```cpp run title="pure-call.cpp" ub
#include <cstdio>
struct Base {
    Base() { init(); }        // 间接调用
    void init() { hook(); }   // 虚调用，Base 中的最终覆盖者是纯虚的
    virtual void hook() = 0;
    virtual ~Base() = default;
};
struct Der : Base {
    void hook() override { std::puts("Der::hook"); }
};
int main() { Der d; }         // UB
```

¶6 在抽象类的构造函数或析构函数里可以调用成员函数；但从这样的构造函数或析构函数中，直接或间接地对正在创建或销毁的对象虚调用一个纯虚函数，行为未定义。

原因在于 [[class.cdtor#4]]：构造和析构期间的虚调用落在当前类的最终覆盖者上。构造 `Base` 子对象时，`hook` 在 `Base` 中的最终覆盖者正是纯虚的 `Base::hook`，没有可以执行的函数体。即使 `Base::hook` 有定义，虚调用也不会选中它。

UB 只针对虚调用。如果 `Base::hook` 有定义，在构造函数里写 `Base::hook()` 就是普通的限定调用，完全合法。

编译器能发现直接的调用：把上例改成 `Base() { hook(); }`，Clang 给出 `-Wcall-to-pure-virtual-from-ctor-dtor` 警告。像上例这样经过一个普通成员函数间接调用，编译器通常发现不了。

!!! impl "实践中的表现"
    Itanium ABI 把 vtable 中纯虚函数的槽位填成运行时库函数 `__cxa_pure_virtual`。构造 `Base` 子对象期间 vptr 指向 `Base` 的 vtable，于是上例调用到这个函数，它打印一条消息后终止程序。本机（libc++abi）的输出是：

    ```text
    libc++abi: Pure virtual function called!
    ```

    MSVC 中对应的函数是 `_purecall`。不过这是 UB，优化器也可能做出别的假设，例如认为这条路径不可达。

## 实现视角

!!! impl
    - 抽象类仍然有 vtable，因为构造和析构期间 vptr 要指向它，纯虚槽位填 `__cxa_pure_virtual`。如果一个类的虚函数要么是纯虚的、要么是内联的，它在 Itanium ABI 下就没有关键函数，vtable 会在每个用到它的翻译单元里作为 COMDAT 生成，由链接器合并。
    - MSVC 提供 `__declspec(novtable)`，告诉编译器这个类永远不会被直接实例化。构造函数中可以不设置 vptr，省一次写入，没有其他引用时还能省掉整张 vtable。代价是在它的构造函数里做虚调用会读到无效的 vptr。

## 历史与演进

!!! history
    - C++98 就有纯虚函数和抽象类。那时抽象类型不能作为函数形参、返回类型或数组元素类型出现，即使只是声明。
    - C++11 起 `override` 可以与 `= 0` 一起写：`void f() override = 0;`。
    - C++20 的 [[P0929R2]] 把抽象类型的检查推迟到函数定义和函数调用处，与不完整类型一致；数组元素类型也不再禁止是抽象类。
    - C++26 {{c++26}} 的契约说明符位于 *virt-specifier-seq* 和 `= 0` 之间。

## 常见误解

!!! pitfall "纯虚函数不能有函数体"
    可以有，只是虚调用不会用到它，只能通过限定名调用。纯虚析构函数则必须有定义。

!!! pitfall "漏覆盖一个纯虚函数会马上报错"
    不会。派生类只是悄悄成为抽象类，直到有人创建它的对象时才报错，错误信息还可能出现在离类定义很远的地方。给派生类写 `static_assert(!std::is_abstract_v<D>)` 能更早发现；覆盖函数都写上 `override`，能排除签名写错导致没有覆盖的情况。

!!! pitfall "构造函数里没直接调用纯虚函数就安全"
    经过一个普通成员函数间接调用同样是 UB，而且编译器通常不警告。

## 思考题

!!! question "思考题 1"
    `struct A { virtual ~A() = 0; };`，没有为 `~A` 提供定义。下面两个程序是否有问题？(a) `int main() { A* p = nullptr; }`；(b) `struct B : A {}; int main() { B b; }`。

<details markdown="1">
<summary>答案</summary>

(a) 没有问题。程序没有创建 `A` 或其派生类的对象，[[class.dtor#11]] 不要求定义；纯虚函数也不会仅因为是虚函数就被 odr-use（[[basic.def.odr#8]]）。

(b) 有问题。它创建了 `B` 对象，`B` 的析构函数被定义，并如同用限定名那样调用 `A::~A`。`A::~A` 被 odr-use 却没有定义，违反 ODR，不要求诊断。实践中是找不到 `A::~A()` 的链接错误。
</details>

!!! question "思考题 2"
    为什么 [[expr.call]] 只在调用时检查形参是不是抽象类型，而不在函数声明时检查？举一个这种放宽有实际用处的例子。

<details markdown="1">
<summary>答案</summary>

只有调用时才需要为按值传递的形参创建对象，声明本身不创建任何对象。

实际用处有两类。一是元编程中只声明不定义的辅助函数，比如 `template<class T> T make();`，只在 `decltype(make<A>())` 里使用，C++17 中 `T` 为抽象类时可能产生硬错误。二是在类体里声明返回自身类型的成员函数（`A clone() const;`），而类是不是抽象的要到右花括号处才知道，C++17 中这会出现检查时机不一致的问题。
</details>
