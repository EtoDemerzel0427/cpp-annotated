---
title: 抽象类
summary: 纯虚函数与抽象类；纯虚函数何时需要定义（限定调用与析构函数）；抽象类型能出现在哪里（C++20 起只在定义与调用处检查）；抽象性随最终覆盖者继承；构造/析构中虚调用纯虚函数是 UB
status: draft
papers: P0929R2
related: class.virtual, class.dtor, class.mem, class.cdtor, dcl.fct, expr.call, expr.new, basic.def, dcl.type.decltype
tags: 类, 虚函数, 抽象类, UB
updated: 2026-10-17
---

**抽象类**（abstract class）是"只能作为基类使用"的类：它表达一个概念（"形状"、"流"），把部分行为留给派生类实现。在 C++ 中，抽象性不是用关键字声明的，而是由**纯虚函数**推出来的：至少有一个（最终覆盖者仍是）纯虚函数的类就是抽象类。本节规定纯虚函数的写法与定义要求、抽象类型的使用限制，以及在构造/析构中调用纯虚函数的 UB。

前置阅读：[[class.virtual]]（覆盖与最终覆盖者）。

## 动机（¶1）

¶1（注 1）：抽象类机制支持"一般概念"（如 `shape`），只有其具体变体（`circle`、`square`）才能实际使用；抽象类也可以用来定义**接口**，由派生类提供不同实现。

C++ 没有单独的 `interface` 关键字；"所有成员函数都是纯虚、无数据成员"的抽象类就是接口。

## 纯虚函数与抽象类（¶2）

¶2：在类定义中的函数声明里使用 ***pure-specifier***（`= 0`，[[class.mem]]）把一个虚函数指定为**纯虚函数**（pure virtual function）。**至少有一个**纯虚函数的类是**抽象类**。

`= 0` 的语法细节（[class.mem.general]）：

- 记号序列必须**恰好是** `= 0`：`= 0L`、`= false`、`= nullptr` 都不行；
- 只能用于**虚函数**的声明，且不能是友元声明；
- 顺序是：声明符、*virt-specifier-seq*（`override`/`final`）、C++26 的合约说明符（`pre`/`post`），最后才是 *pure-specifier*：`void f() override = 0;`。

```cpp title="pure-specifier.cpp" error
struct A {
    virtual void f() = 0;            // OK
    virtual void g() = 0L;           // error: 不是 pure-specifier
    void h() = 0;                    // error: 非虚函数不能是纯虚
    virtual void k() override = 0;   // error: override 了但没有覆盖任何函数
};
struct B : A {
    void f() override = 0;           // OK: 纯虚函数也可以覆盖（重新声明为纯虚）
};
```

注 3：抽象类只能作为其他类的基类使用；除了作为派生类的子对象，不能创建抽象类的对象（[[basic.def]]、[[class.mem]]）。

### 纯虚函数也可以有定义

一个常见误解是"纯虚函数没有函数体"。¶2 说的是：纯虚函数**只有在**用限定名语法调用（或"如同"用限定名调用，[[class.dtor]]）时**才需要定义**。换句话说，纯虚函数**可以**有定义，只是通过虚调用永远不会到达它；只能通过 `Base::f()` 显式调用。

注 4：一个函数声明**不能同时**提供 *pure-specifier* 和定义，所以定义必须写在类外：

```cpp title="pure-with-body.cpp" error
struct C {
    virtual void f() = 0 { }     // error: 不能在同一声明中既是纯虚又给出定义
};
```

```cpp run title="pure-default-impl.cpp" ok
#include <cstdio>

struct Shape {
    virtual void draw() const = 0;   // 纯虚：派生类必须覆盖……
    virtual ~Shape() = default;
};
void Shape::draw() const {           // ……但可以提供一个"默认实现"供派生类显式调用
    std::puts("Shape: default outline");
}

struct Circle : Shape {
    void draw() const override {
        Shape::draw();               // 限定调用：需要 Shape::draw 的定义
        std::puts("Circle: fill");
    }
};

int main() {
    Circle c;
    const Shape& s = c;
    s.draw();
}
```

这种写法表达"派生类**必须**显式决定行为，但可以选择复用默认实现"——比普通虚函数（可以静默继承默认行为）更强的约束。

### 纯虚析构函数必须有定义

"如同用限定名调用"指的是析构函数：[[class.dtor]] 规定派生类的析构函数在执行完自己的函数体后，调用各基类的析构函数，**如同**用限定名引用它们（忽略虚覆盖）。因此纯虚析构函数**一定**会被调用，必须定义；[[class.dtor#11]] 也明确：若析构函数是虚的，且程序中创建了该类或其派生类的任何对象，析构函数必须被定义。

```cpp run title="pure-virtual-dtor.cpp" ok
#include <cstdio>

struct Interface {
    virtual ~Interface() = 0;     // 纯虚析构：在没有其他纯虚函数时让类成为抽象类
};
Interface::~Interface() { std::puts("~Interface"); }   // 必须定义

struct Impl : Interface {};       // Impl::~Impl 隐式覆盖，Impl 不是抽象类

int main() { Impl i; }            // 输出 ~Interface
```

纯虚析构函数是"我想让这个类抽象，但没有合适的成员函数可以设为纯虚"时的标准手法。忘记给它定义，在 Itanium ABI 下表现为链接错误（找不到 `Interface::~Interface()`）。

## 抽象类型能出现在哪里（¶3）

¶3（注 5）总结了限制（规范性规则分散在各处）：

| 场合 | 是否允许 | 依据 |
|---|---|---|
| 函数**定义**中的形参类型或返回类型 | 不允许（deleted 函数除外） | [[dcl.fct.def.general#2]] |
| 函数**调用**时形参是抽象类型 | 不允许 | [[expr.call#7]] |
| 函数**声明**（非定义）的形参/返回类型 | **允许**（C++20 起） | — |
| 显式类型转换 `A()`、`A{}`、`static_cast<A>(x)` 的结果类型 | 不允许（结果是抽象类型的 prvalue） | [[basic.lval#9]] |
| 变量定义、`new A`、非静态数据成员 | 不允许 | [[basic.def]]、[[expr.new]]、[[class.mem#20]] |
| 数组元素类型 | 作为**类型**允许（[[dcl.array]] 不再禁止），但不能定义这样的数组对象 | |
| `decltype(f())` 中返回抽象类型的调用 | 允许 | [[dcl.type.decltype#2]]：不实质化临时量 |
| 指针、引用、`sizeof`、`typeid`、`std::is_abstract` | 允许 | |

核心思想：**限制的是"创建对象"，而不是"提到类型"**。只要不会真的产生一个抽象类型的对象（或 prvalue 结果对象），提到这个类型就没问题。

```cpp title="abstract-uses.cpp" error
struct A { virtual void f() = 0; };

A make();                    // OK（C++20 起）：只是声明
void take(A);                // OK（C++20 起）：只是声明
struct S { A g(); };         // OK：成员函数声明
using F = A(A);              // OK：函数类型
using T = decltype(make());  // OK：decltype 不实质化临时量
A* p;                        // OK: 指针
void ref(A& r);              // OK: 引用

A make2() { }                // error: 函数定义的返回类型是抽象类
void use(A& a) { take(a); }  // error: 调用时形参是抽象类型
A arr[2];                    // error: 定义抽象类型的数组对象
void h() { A{}; }            // error: 显式类型转换的结果是抽象类型
```

!!! impl "Clang 的偏差"
    按当前 [[dcl.array]]，`using X = A[2];`（只是一个类型，不创建对象）应当合法；截至写作时 Clang 23 仍然以"抽象类类型的数组"为由拒绝它。另外，Clang 在 `-std=c++17` 下同样接受上面那些"只是声明"的用法，不区分语言版本。

### 为什么 C++20 要放宽（P0929）

C++17 及之前，抽象类型**根本不能**作为函数形参或返回类型出现，哪怕只是声明。这带来两个问题：

1. **完整性时序问题**：类在闭花括号处才完整，此前无法知道它是否抽象。`struct A { A f(); virtual void g() = 0; };` 中 `A f();` 出现时 `A` 是否抽象尚不可知——编译器要么回头重新检查，要么行为不一致。
2. **模板中的意外错误**：仅仅实例化一个声明（例如 `std::function<A()>` 的签名，或某个 trait 中的 `T f();`）就可能因为 `T` 是抽象类而硬错误，而这个函数根本不会被定义或调用。

[[P0929R2]]（C++20）把检查推迟到真正需要对象的地方：**函数定义**与**函数调用**。这与"不完整类型可以出现在函数声明中、只在定义/调用时必须完整"的规则完全一致——抽象性被当作另一种"不能创建对象"的属性对待。

## 抽象性的继承（¶4–¶5）

¶4 给出更精确的定义：一个类是抽象类，当且仅当它有至少一个纯虚函数，其**最终覆盖者是纯虚的**。

这意味着抽象性会**沿继承传递**，直到所有纯虚函数都被覆盖：

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
    // 未覆盖 draw：shape::draw 仍是最终覆盖者，仍是纯虚
};

class circle : public shape {
public:
    void rotate(int) override {}
    void draw() override {}          // 全部覆盖：不再抽象
};

static_assert(std::is_abstract_v<shape>);
static_assert(std::is_abstract_v<ab_circle>);
static_assert(!std::is_abstract_v<circle>);

int main() { circle c; (void)c; }
```

¶5（注 6）指出两个反方向的可能：

- 抽象类可以派生自**非抽象类**；
- 纯虚函数可以**覆盖非纯虚函数**——把一个已有实现的虚函数"重新变为纯虚"，强制更下层的派生类重新实现它。

```cpp run title="re-abstract.cpp" ok
#include <type_traits>

struct Concrete { virtual int f() { return 1; } virtual ~Concrete() = default; };
struct Abs : Concrete { int f() override = 0; };   // 纯虚函数覆盖了非纯虚函数
struct Again : Abs { int f() override { return 3; } };

static_assert(!std::is_abstract_v<Concrete>);
static_assert(std::is_abstract_v<Abs>);
static_assert(!std::is_abstract_v<Again>);

int main() { Again a; return a.f() == 3 ? 0 : 1; }
```

!!! lawyer "最终覆盖者是相对于哪个类？"
    ¶4 中"最终覆盖者"是以该类本身作为最派生类来计算的。在虚继承中，一个纯虚函数可能在**某条分支**上被覆盖了：`struct A { virtual void f() = 0; }; struct B : virtual A { void f() override; }; struct C : virtual A {}; struct D : B, C {};` 中 `C` 是抽象的（在 `C` 中，`A::f` 的最终覆盖者是纯虚的 `A::f`），但 `D` **不是**抽象的——在 `D` 中，共享的 `A` 子对象的 `f` 的最终覆盖者是 `B::f`。

## 构造/析构中调用纯虚函数（¶6）

¶6：可以在抽象类的构造函数（或析构函数）中调用成员函数；但从这样的构造函数（或析构函数）中，对正在创建（或销毁）的对象**直接或间接地**进行纯虚函数的**虚调用**，行为**未定义**（{{ub}}）。

为什么？根据 [[class.cdtor#4]]，构造/析构期间的虚调用落到**当前类**的最终覆盖者；对于抽象类，那可能正是纯虚函数本身——没有可执行的函数体（即使纯虚函数有定义，虚调用也不会选中它）。

"直接"的情形编译器常能发现并警告；"间接"——构造函数调用一个非虚成员函数，后者再调用纯虚函数——编译器通常发现不了：

```cpp run title="pure-call.cpp" ub
#include <cstdio>

struct Base {
    Base() { init(); }               // 间接：经过一个普通成员函数
    void init() { hook(); }          // 虚调用：当前类 Base 中的最终覆盖者是纯虚的 hook
    virtual void hook() = 0;
    virtual ~Base() = default;
};
struct Der : Base {
    void hook() override { std::puts("Der::hook"); }
};

int main() { Der d; }                // UB
```

注意 UB 的范围：只有**虚调用**是 UB。在构造函数中用限定名 `Base::hook()` 调用（且 `Base::hook` 有定义）是合法的普通调用。

!!! impl "实践中的表现"
    Itanium ABI 把纯虚函数在 vtable 中的槽位填为运行时库函数 `__cxa_pure_virtual`；构造 `Base` 子对象期间 vptr 指向 `Base` 的 vtable，于是上例调用到它，打印一条消息后终止程序。本机（libc++abi）的输出是：

    ```text
    libc++abi: Pure virtual function called!
    ```

    MSVC 的对应函数是 `_purecall`。这是"良性"的表现；由于是 UB，优化器也可能做出其他假设（例如认为这条路径不可达）。

## 实现视角

!!! impl
    - 抽象类**仍然有 vtable**（构造/析构期间 vptr 要指向它），纯虚槽位填 `__cxa_pure_virtual`。若一个类的所有虚函数要么纯虚、要么内联，Itanium ABI 中它没有"关键函数"，vtable 在每个用到它的 TU 中作为 COMDAT 生成。
    - MSVC 提供 `__declspec(novtable)`：告诉编译器该类永远不会被直接实例化，构造函数中可以不设置 vptr，省掉一次写入和 vtable 本身（如果没有其他引用）。代价是：在其构造函数中进行虚调用会访问无效的 vptr。
    - 编译器会诊断"在构造函数中直接调用纯虚函数"的明显情况（Clang 有对应警告），但无法覆盖间接调用。

## 历史与演进

!!! history
    - **C++98**：纯虚函数、抽象类；抽象类型不能作为形参/返回类型/数组元素类型出现，即使只是声明。
    - **C++11**：`override` 可与 `= 0` 组合（`void f() override = 0;`）。
    - **C++20**：[[P0929R2]] "Checking for abstract class types"——抽象性检查推迟到函数定义和调用处，与不完整类型的处理一致；数组元素类型不再禁止抽象类。
    - **C++26** {{c++26}}：合约说明符位于 *virt-specifier-seq* 与 *pure-specifier* 之间。

## 陷阱

!!! pitfall
    1. **以为纯虚函数不能有定义**：可以有，只是只能通过限定名调用。纯虚**析构函数**则**必须**有定义。
    2. **构造函数里间接调用纯虚函数**：UB，通常以"pure virtual function called"崩溃告终，而且编译器往往不警告。
    3. **派生类漏覆盖一个纯虚函数**：派生类悄悄变成抽象类，直到有人试图创建对象时才报错——在派生类上加 `final` 或写 `static_assert(!std::is_abstract_v<D>)` 能更早发现。
    4. **签名写错导致没覆盖**：结果同上；用 `override`。

## 思考题

!!! question "思考题 1"
    `struct A { virtual ~A() = 0; };` 没有为 `~A` 提供定义。下面哪些程序是良构的？(a) 只声明 `A* p = nullptr;`；(b) `struct B : A {}; int main() { B b; }`；(c) `struct B : A {}; int main() { B* p = nullptr; }`。

<details markdown="1">
<summary>答案</summary>

(a) 与 (c) 良构：没有创建 `A` 或其派生类的任何对象，[[class.dtor#11]] 不要求定义，也没有对 `~A` 的 odr-use（纯虚函数不会仅因声明而被 odr-use，[[basic.def.odr#8]]）。(c) 中 `B` 的隐式析构函数虽然声明了，但只有在被 odr-use 时才隐式定义。(b) 创建了 `B` 对象，`B::~B` 被定义并"如同用限定名"调用 `A::~A`，后者被 odr-use 却没有定义——违反 ODR，不要求诊断，实践中是链接错误。
</details>

!!! question "思考题 2"
    为什么 [[expr.call]] 只在**调用**时检查形参不是抽象类型，而不在函数声明时检查？举一个这种放宽有实际价值的例子。

<details markdown="1">
<summary>答案</summary>

因为只有调用时才需要为按值形参创建对象。实际价值：`std::declval<A>()` 风格的元编程，或 `template<class T> T make();` 这样的"只声明不定义"的辅助函数，在 `decltype(make<A>())` 中使用；以及类成员函数中提前声明返回自身类型（`A clone() const;`），而类是否抽象要到闭花括号处才知道。C++17 中前者在 `T` 为抽象类时可能产生硬错误，后者会出现检查时机不一致的问题。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 纯虚函数 | `= 0`（恰好这个记号序列），只用于虚函数；可以有类外定义 |
    | 抽象类 | 至少一个纯虚函数的最终覆盖者仍是纯虚 |
    | 定义要求 | 纯虚函数仅在限定调用时需定义；纯虚析构函数必须定义 |
    | 使用限制 | 不能创建对象（变量、`new`、成员、显式转换）；函数定义/调用处不能按值使用；C++20 起声明中可以 |
    | 继承 | 抽象性沿继承传递；纯虚可以覆盖非纯虚 |
    | 构造/析构 | 对正在构造/析构的对象虚调用纯虚函数是 UB |
