---
title: 默认实参
summary: 默认实参是在调用点补上的表达式：每次调用都求值、名字在声明处查找、不属于函数类型；同一宿主作用域内跨声明累积而不能重定义；不能使用形参、this、局部变量；类模板成员只能在首次声明给出；虚函数按静态类型取默认实参
status: draft
related: dcl.fct, expr.call, over.match.viable, temp.inst, class.virtual, basic.def.odr, expr.const.imm, support.srcloc
tags: 默认实参, 函数, 虚函数, source_location
updated: 2026-10-17
---

**默认实参**（default argument）看起来是函数的属性，但在标准里它更像是声明的属性：它不属于函数类型（[[dcl.fct#13]]），同一个函数在不同作用域里可以有不同的默认实参集合，通过函数指针调用时它根本不存在。可以这样理解：

> 默认实参是附着在某个声明上的一段表达式。如果一次调用通过这个声明（或同一作用域中累积的声明）找到函数，且末尾的实参缺失，编译器就在调用点把这段表达式补进实参列表。

围绕这个模型，本节（[dcl.fct.default]）规定：默认实参在哪里可以写、怎样跨声明累积、名字在哪里查找、能引用什么、何时求值，以及与虚函数、类模板、友元的交互。

## 什么是默认实参（¶1–2）

¶1 非模板形参的 *parameter-declaration* 中的 *initializer-clause* 就是默认实参。注 1 指出，调用中末尾的实参缺失时就使用它（[[expr.call]]）。模板形参的 `= …` 是默认模板实参，由 [[temp.param]] 规定，不属于本节。

¶2（例）`void point(int = 3, int = 4);` 可以用 0、1、2 个实参调用；`point(1)` 等价于 `point(1, 4)`，`point()` 等价于 `point(3, 4)`。

## 只能写在哪里（¶3）

¶3 默认实参只能出现在函数声明或 *lambda-declarator* 的形参声明子句中；不能用于函数形参包；不能出现在形参声明的声明符或抽象声明符内部。脚注 70 解释了最后一条：这意味着函数指针、函数引用、typedef 的声明中都不能有默认实参。

```cpp title="default-where.cpp" error
void (*pf)(int = 0);              // error: 函数指针声明中不能有默认实参
typedef void F(int = 0);          // error: typedef 中不能有
void g(void (*cb)(int = 0));      // error: 形参的声明符内部（形参本身是函数指针）
template<class... T> void h(T... = 0);   // error: 形参包不能有默认实参
auto l = [](int x = 1) { return x; };     // OK：lambda 声明符
```

为什么函数指针不能有默认实参？因为默认实参不是类型的一部分，函数指针的类型里没有地方存放它。如果允许 `void (*pf)(int = 0)`，执行 `pf = &other;` 之后，这个默认值属于谁就说不清了。

## 跨声明累积（¶4）

¶4 是本节最微妙的一段。

**累积**：对非模板函数，可以在同一宿主作用域（host scope，[[basic.scope.scope]]）的后续声明中添加默认实参。

**隔离**：宿主作用域不同的声明拥有完全独立的默认实参集合，内层作用域的声明不继承外层的默认实参，反之亦然。

**连续性**：在任一函数声明中，有默认实参的形参之后的每个形参，都必须在本声明或先前的声明中有默认实参，除非它是从形参包展开来的，或者它本身是函数形参包。

**不能重定义**：按注 2，后续声明不能再次给同一形参指定默认实参，即使值相同也不行（这是 [[basic.def.odr]] 的推论）。

标准例 2 把这些都展示了：

```cpp title="default-accumulate.cpp" error
void g(int = 0, ...);           // OK：省略号不是形参，可以跟在有默认实参的形参后面
void f(int, int);
void f(int, int = 7);           // 累积：现在 f 的第二个形参有默认实参
void h() {
    f(3);                       // OK：调用 f(3, 7)
    void f(int = 1, int);       // error: 块作用域是新的宿主作用域，不继承外层的 "= 7"，
                                //        于是第二个形参没有默认实参，违反连续性
}
void m() {
    void f(int, int);           // 块作用域声明：没有任何默认实参
    f(4);                       // error: 实参个数不对——外层的 "= 7" 在这里不可见
    void f(int, int = 5);       // OK：在本块中累积
    f(4);                       // OK：调用 f(4, 5)
    void f(int, int = 5);       // error: 不能重定义，即使值相同
}
void n() {
    f(6);                       // OK：调用 f(6, 7)——m 中的 "= 5" 只属于 m 的块作用域
}
template<class ... T> struct C {
    void f(int n = 0, T...);    // 后面的形参来自包展开，不要求有默认实参
};
C<int> c;                       // OK：实例化出 void C<int>::f(int n = 0, int)
```

为什么要按宿主作用域隔离？块作用域的函数声明本来就是在局部重新描述一个外部函数的机制。如果它会继承或改动外层的默认实参，同一个函数在不同函数体里的调用方式就会互相影响，而且依赖于声明的出现顺序。隔离之后，每个作用域看到的都是自洽的一组默认实参。

### 跨翻译单元与友元

¶4 末尾还有两条：

- 对于在多个翻译单元中定义的内联函数，各 TU 结束时累积的默认实参集合必须相同，违反时 {{ifndr}}。这是 ODR 的延伸：如果头文件中的内联函数在一个 TU 里多加了默认实参，另一个 TU 没有，它们就不再是同一个函数。
- 如果友元声明 D 指定了默认实参，D 必须是定义，并且不能有其他声明从 D 可达，D 也不能从其他声明可达。也就是说，带默认实参的友元函数只能像隐藏友元那样，是唯一的声明。

```cpp title="friend-default.cpp" error
struct F  { friend void fr(int = 0); };        // error: 带默认实参的友元声明必须是定义
struct F2 { friend void fr2(int = 0) { } };    // OK：定义，且是唯一声明
```

为什么这样规定？友元函数的目标作用域是外围命名空间（[[dcl.meaning.general]]），但它的声明位于类中。如果允许在类中给它默认实参，又在命名空间中再声明一次，同一函数就会在两个不同的宿主作用域中有不同的默认实参，而且这两个声明彼此可达，局面会很混乱。

## 语义约束与名字查找（¶5）

¶5 默认实参与以形参类型声明的变量的初始化器具有相同的语义约束，使用复制初始化（[[dcl.init]]）。所以 `explicit` 构造函数不能用于默认实参的隐式转换。

**名字在默认实参出现的地方查找，语义约束也在那里检查**，而不是在调用点。标准例 3 如下：

```cpp run title="default-lookup.cpp" ok
#include <cstdio>
int a = 1;
int f(int x) { return x * 10; }
int g(int x = f(a)) { return x; }   // 这里的 a 已绑定为 ::a

int main() {
    a = 2;
    {
        int a = 3;                   // 调用点的局部 a 不影响默认实参
        std::printf("%d\n", g());    // 调用 g(f(::a))，输出 20
    }
}
```

**例外：即时调用**。默认实参中潜在求值的即时调用（immediate invocation，[[expr.const.imm]]）在声明处既不求值，也不检查是否为常量表达式。这条规则正是为 `std::source_location::current()` 准备的：它是 `consteval` 函数，如果在声明处求值，得到的就是声明的位置，而我们想要的是调用点的位置。

```cpp run title="source-location.cpp" ok
#include <cstdio>
#include <source_location>

void log(const char* msg,
         std::source_location loc = std::source_location::current()) {
    std::printf("%s @ line %u\n", msg, static_cast<unsigned>(loc.line()));
}

int main() {
    log("hello");    // 打印 main 中这一行的行号，而不是 log 声明的行号
}
```

模板化函数的默认实参，其名字查找与约束检查按 [[temp.inst]] 进行，也就是在需要时才实例化。所以即使 `T` 没有默认构造函数，`template<class T> struct TT { void m(T t = T()); };` 这个类模板也能实例化，只要调用 `m()` 时不省略实参即可。

注 3 指出，默认实参是**完整类语境**（complete-class context，[[class.mem]]），成员函数的默认实参中可以使用在类中后面才声明的成员。访问检查照常进行（[[class.access]]）。

```cpp title="complete-class.cpp" ok
#include <type_traits>
struct S {
    void f(int x = later);          // OK：默认实参是完整类语境，later 在下面声明
    static constexpr int later = 5;
};
void S::f(int) { }

template<class T> struct TT { void m(T t = T()) { (void)t; } };
struct NoDef { NoDef(int) { } };
int main() {
    S{}.f();
    TT<NoDef> x;            // OK：默认实参 T() 尚未实例化
    x.m(NoDef(1));          // OK：没有使用默认实参
}
```

## 类外定义成员函数时添加默认实参（¶6）

¶6 除模板化类的成员函数外，类外的成员函数定义中给出的默认实参，会添加到类内声明提供的集合中。但如果这样添加使该函数成为默认构造函数、复制/移动构造函数或复制/移动赋值运算符，程序非良构。模板化类的成员函数的默认实参必须在类内的初始声明中给出。

```cpp title="member-default.cpp" error
class C {
    void f(int i = 3);
    void g(int i, int j = 99);
    C(int x);
};
void C::f(int i = 3) { }        // error: 类作用域中已指定，不能重定义
void C::g(int i = 88, int j) { }// OK：在本 TU 中此后 C::g 可以无实参调用
C::C(int x = 0) { }             // error: 添加默认实参使其成为默认构造函数

template<class T> struct T1 { void f(int); };
template<class T> void T1<T>::f(int = 1) { }   // error: 类模板成员只能在类内给默认实参
```

为什么特殊成员函数不能这样？类是否有默认构造函数、复制构造函数，会影响类的性质，如是否平凡、是否聚合、隐式声明哪些成员等。这些性质在类定义结束时就必须确定，并且在所有 TU 中一致。如果某个 TU 在类外添加默认实参，使某个构造函数变成默认构造函数，类的性质就会因 TU 而异。

为什么类模板成员不能？类模板的成员在每次实例化时从类内声明生成，类外定义本身也只是一个模板，没有一个确定的时间点可供后续声明在其后累积默认实参。

## 不能引用的东西（¶7–9）

### 局部变量（¶7）

¶7（注）默认实参中不能 odr-use 局部变量（[[basic.def.odr]]），只允许不构成 odr-use 的引用（如在 `sizeof` 中，或者读取常量的值）。

```cpp title="default-local.cpp" error
void f() {
    int i;
    extern void g(int x = i);           // error: odr-use 局部变量
    extern void h(int x = sizeof(i));   // OK：未求值操作数
    const int k = 3;
    extern void p(int x = k);           // OK：读取常量不是 odr-use
}
```

理由很直接：默认实参在调用点求值，而调用可能发生在 `f` 之外（`g` 是命名空间函数），那时局部变量 `i` 早已不存在了。

### this（¶8）

¶8（注）`this` 不能出现在成员函数的默认实参中（[[expr.prim.this]]），因为默认实参在调用者的上下文中求值，那里没有当前对象的概念。

```cpp title="default-this.cpp" error
class A {
    void f(A* p = this) { }     // error
};
```

### 形参（¶9 前半）

¶9 **每次调用时（只要没有提供对应实参）都会对默认实参求值**。形参不能作为潜在求值的表达式出现在默认实参中。注 6 指出，在默认实参之前声明的形参已经在作用域内，会隐藏同名的命名空间成员和类成员。

```cpp title="default-param.cpp" error
int a;
int f(int a, int b = a);            // error: 形参 a 被用作默认实参（隐藏了 ::a）
typedef int I;
int g(float I, int b = I(2));       // error: 找到的是形参 I（float），不是类型 I
int h(int a, int b = sizeof(a));    // OK：未求值操作数
```

为什么禁止使用前面的形参？因为函数实参的求值顺序未指定（[[expr.call]]）：如果写 `b = a`，计算 `b` 的默认值时无法保证 `a` 已经初始化。`g` 的例子展示了隐藏带来的陷阱：形参 `I` 隐藏了类型名 `I`，于是 `I(2)` 变成了对一个 float 的调用。

每次调用都求值这一点可以直接观察到：

```cpp run title="default-each-call.cpp" ok
#include <cstdio>
int counter = 0;
int next() { return ++counter; }
void f(int a = next()) { std::printf("%d ", a); }

int main() {
    f(); f(); f(10);    // 输出 1 2 10：每次省略实参时重新调用 next()
}
```

这与 Python 的默认参数（在 `def` 时求值一次）截然不同。

### 非静态成员（¶9 中段）

默认实参中不能指代非静态成员，除非：

- ¶9.1 它通过类成员访问表达式指代（`obj.m`）；
- ¶9.2 它用于形成成员指针（`&X::m`）；
- ¶9.3 它是 *reflect-expression* 的操作数（`^^m`）{{c++26}}。

```cpp title="default-member.cpp" error
int b;
class X {
    int a;
    int mem1(int i = a);        // error: 没有对象可以提供 a
    int mem2(int i = b);        // OK：使用 X::b（静态成员，见下一行）
    int mem3(int X::*p = &X::a);// OK：形成成员指针
    static int b;
};
```

`mem2` 中的 `b` 指的是 `X::b` 而不是 `::b`。默认实参是完整类语境，类作用域中后声明的 `b` 也能找到。

## 不属于函数类型（¶9 后半）

默认实参不是函数类型的一部分：

```cpp title="default-not-type.cpp" error
int f(int = 0);
void h() {
    int j = f(1);
    int k = f();               // OK：即 f(0)
}
int (*p1)(int) = &f;
int (*p2)() = &f;              // error: 类型不匹配，f 的类型是 int(int)
```

注 7 指出，如果重载集合中包含一个宿主作用域为 *S* 的函数声明，那么与 *S* 中任何可达声明相关联的默认实参都可用于该调用（[[over.match.viable]]）。注 8 指出，候选函数可能是经由 *using-declarator* 找到的，而提供默认实参的声明从那里不一定可达。

## 虚函数：按静态类型取默认实参（¶10）

!!! std
    A virtual function call uses the default arguments in the declaration of the virtual function determined by the static type of the pointer or reference denoting the object.

    虚函数调用使用的默认实参，取自由指针或引用的**静态类型**所确定的那个虚函数声明。

覆盖函数不从被覆盖的函数那里获得默认实参。

```cpp run title="virtual-default.cpp" ok
#include <cstdio>
struct A {
    virtual void v(int a = 7) { std::printf("A %d\n", a); }
    virtual ~A() = default;
};
struct B : A {
    void v(int a = 9) override { std::printf("B %d\n", a); }
};
int main() {
    B b;
    A& ra = b;
    ra.v();      // 输出 "B 7"：函数体按动态类型分派，默认实参按静态类型 A 选取
    b.v();       // 输出 "B 9"
}
```

为什么这样规定？默认实参是在编译期、在调用点补进去的，而编译器在调用点只知道静态类型。要按动态类型选默认实参，就必须把默认实参也放进虚表（或者在运行期分派默认值的计算），这既违背零开销原则，也与默认实参不属于函数类型的设计相冲突。

标准例 10 中的 `pb->f()` 非良构，因为 `B::f` 自己没有默认实参，也不继承 `A::f` 的默认实参。

!!! tip "惯用法"
    不要在覆盖函数中重新指定默认实参，尤其不要指定不同的值。常见做法是让公开的非虚函数带默认实参，再由它调用受保护的虚函数（NVI，non-virtual interface）。

## lambda 与默认实参

lambda 可以出现在默认实参中（它是一个普通表达式），也可以自己带默认实参（¶3 允许 *lambda-declarator*）。

```cpp run title="lambda-default.cpp" ok
#include <cstdio>
void g(int x = [] { return 42; }()) { std::printf("%d\n", x); }   // 默认实参中的 lambda
int main() {
    g();                                         // 42
    auto add = [](int a, int b = 10) { return a + b; };   // lambda 的默认实参
    std::printf("%d\n", add(1));                 // 11
}
```

默认实参中的 lambda 不能捕获局部变量（¶7），命名空间作用域的默认实参中也没有可以捕获的东西。另外注意，按 [[expr.await]]，`co_await` 不能出现在默认实参中。

## 实现视角

!!! impl
    - 调用点展开：编译器在每个调用点把默认实参表达式实例化一份。在生成的目标代码中，被调函数完全不知道实参是否来自默认值；默认实参不影响名字修饰，也不进入 ABI。
    - 修改默认值需要重新编译调用者：默认值已经编译进了各个调用点，所以在头文件中修改默认实参后，只重新编译定义所在的 TU 是不够的。这是库 ABI 演进中常见的问题。
    - 诊断：Clang 对 ¶4 的重定义报 "redefinition of default argument"；对 ¶6 中使构造函数成为默认构造函数的情形报 "addition of default argument on redeclaration makes this constructor a default constructor"；对类模板成员报 "default arguments cannot be added to an out-of-line definition of a member of a class template"。

## 历史与演进

!!! history
    - C++98：本节的绝大部分规则已经存在，包括按静态类型选取虚函数的默认实参。
    - C++11：引入 lambda；C++11 原文禁止 lambda 有默认实参，C++14 通过核心问题修订解除了这一限制。
    - 之后的核心问题修订：对从形参包展开而来的形参豁免连续性要求（标准例 2 中的 `C<int>`）。
    - C++20 之后：`consteval` 与 `std::source_location` 进入 C++20 后，又经核心问题修订明确了默认实参中的即时调用不在声明处求值，而是推迟到调用点。
    - C++26：默认实参中允许用 `^^member`（反射）指代非静态成员。

## 陷阱

!!! pitfall "虚函数的默认实参"
    `Base* p = new Derived; p->f();` 用的是 `Base::f` 声明中的默认实参，即使执行的是 `Derived::f`。避免在覆盖函数中写不同的默认实参。

!!! pitfall "默认实参与 std::function / 函数指针"
    如果 `f` 是 `void f(int = 0)`，`std::function<void()> fn = f;` 非良构。函数指针和 `std::function` 都只看类型。

!!! pitfall "头文件与源文件各写一次"
    在头文件中声明 `void f(int x = 1);`，又在源文件中定义 `void f(int x = 1) { }`，这是重定义，非良构。默认实参只写在声明（通常是头文件）里。

!!! pitfall "默认实参不是常量"
    默认实参每次调用都会求值，可以有副作用（`next()`），每次的结果也可以不同（`std::chrono::steady_clock::now()`）。

## 思考题

!!! question "思考题 1"
    下面程序的输出是什么？
    ```cpp
    #include <cstdio>
    void f(int a, int b = 2);
    void f(int a = 1, int b);
    int main() {
        f();
        { void f(int, int = 20); f(10); }
        f();
    }
    void f(int a, int b) { std::printf("%d%d ", a, b); }
    ```

<details markdown="1">
<summary>答案</summary>

输出 `12 1020 12 `。第二个声明 `void f(int a = 1, int b);` 合法，因为 `b` 在先前（同一宿主作用域）的声明中已有默认实参，满足连续性；累积后 `f()` 即 `f(1, 2)`。块作用域中的声明属于新的宿主作用域，只有 `b = 20`，所以 `f(10)` 即 `f(10, 20)`；离开块后又回到全局的默认实参集合。
</details>

!!! question "思考题 2"
    `struct S { void f(int x = sizeof(S)); };` 良构吗？`sizeof(S)` 在默认实参出现时 `S` 还是不完整类型。

<details markdown="1">
<summary>答案</summary>

良构。默认实参是完整类语境（¶5 注 3、[[class.mem]]），其中的表达式在类定义结束后才分析，那时 `S` 已经完整。
</details>

!!! question "思考题 3"
    为什么 `std::source_location::current()` 作为默认实参能得到调用点的位置，而普通的 `constexpr` 函数 `my_line()` 做不到？

<details markdown="1">
<summary>答案</summary>

两者都在调用点求值（默认实参每次调用都求值），所以区别不在于在哪里求值，而在于 `current()` 是由实现特殊处理的 `consteval` 函数：[[support.srcloc]] 规定，它出现在默认实参中时，返回的是调用点的位置。¶5 的配套规则保证这个即时调用不会在声明处提前求值和检查（否则 `consteval` 函数的调用必须在出现处立即成为常量表达式）。普通函数无法知道调用者的源位置，除非它自己也有一个 `source_location` 默认实参。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 位置 | 函数声明与 lambda 声明符的形参；不能用于形参包、函数指针、typedef |
    | 累积 | 同一宿主作用域的后续声明可以添加，不能重定义（即使值相同）；不同宿主作用域完全独立 |
    | 连续性 | 有默认实参的形参之后都要有（来自包展开的形参与形参包除外） |
    | 查找 | 名字在声明处查找；完整类语境；即时调用推迟到调用点 |
    | 禁止 | odr-use 局部变量、`this`、潜在求值地使用形参、无对象地使用非静态成员 |
    | 求值 | 每次调用都求值，在调用点 |
    | 类型 | 不属于函数类型；函数指针看不到 |
    | 成员 | 类外定义可添加（除非使之成为特殊成员）；类模板成员只能在类内首次声明给出 |
    | 虚函数 | 按静态类型的声明选取；覆盖函数不继承 |
    | 友元 | 带默认实参的友元声明必须是定义且是唯一声明 |
