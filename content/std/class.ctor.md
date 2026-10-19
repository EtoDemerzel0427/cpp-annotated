---
title: 构造函数
summary: 构造函数怎样声明、为什么没有名字也不能取地址；默认构造函数何时隐式声明、何时被删除、何时平凡，以及类外 = default 怎样改变 T{} 的结果。
status: done
covers: class.ctor.general, class.default.ctor
related: special, class.copy.ctor, class.base.init, class.init, dcl.init, class.cdtor, class.prop, class.conv.ctor
tags: 构造函数, 默认构造, 平凡, 值初始化
updated: 2026-10-19
---

!!! tldr
    - 构造函数靠声明的形状识别：类内写注入类名加形参列表，前面没有类型。它没有名字，不能取地址，不能是协程，也不能有显式对象形参。
    - 对象在构造期间还不是 const 的，所以 `const` 对象的构造函数可以给成员赋值。
    - 只要类里声明了任何构造函数（包括复制构造函数和构造函数模板），编译器就不再隐式声明默认构造函数。
    - 引用成员、没有初始化器的 `const` 成员、无法默认构造或无法析构的子对象，会让预置的默认构造函数被删除。C++26 起联合体的变体成员不再触发这条规则。
    - 默认构造函数在类内 `= default` 时不是用户提供的，`T{}` 会先把对象清零；挪到类外 `= default` 就成了用户提供的，`T{}` 不再清零。

## 构造函数的声明 [class.ctor.general]

```cpp title="ctor-decl.cpp" error
struct S {
    S();                     // 构造函数
    explicit S(int);         // OK
    constexpr S(double) { }  // OK
    void S(char);            // error: 不能有返回类型
    static S(long);          // error: 不能是 static
    virtual S(short);        // error: 不能是 virtual
};
S::S() { }                   // 类外定义
```

构造函数用来初始化它所属类类型的对象。它是一种特殊的成员函数：没有返回类型，也没有名字。

### 按形状识别（¶1）

¶1 一个函数声明符，如果去掉形参列表、异常说明和属性之后只剩一个 *id-expression*，并且这个 *id-expression* 是下面三种形式之一，它声明的就是构造函数：

- ¶1.1 友元声明中，指名某个构造函数的限定名，如 `friend X::X();`；
- ¶1.2 类定义内的成员声明中，直接外围类的**注入类名**（[[g:injected-class-name]]，类在自己的作用域里以自身名字的形式出现的那个名字，[[class.pre#2]]）；
- ¶1.3 其他情况下，最后一部分是注入类名的限定名，如类外定义 `S::S() { }`。

声明的其余部分只能有 `friend`、`inline`、`constexpr`、`consteval` 和 `explicit`（含 `explicit(bool)`）这几种说明符。所以上例中的 `void`、`static`、`virtual` 都是错误。

!!! lawyer "类模板里的 `X<T>()`"
    在 `template<class T> struct X` 中，`X<T>` 是一个模板标识，不是注入类名，所以 `X<T>();` 不符合 ¶1.2，C++20 起不再是合法的构造函数声明，应写 `X();`。析构函数同理，应写 `~X();`（[[class.dtor#1]]）。本机 Clang 23 加上 `-pedantic` 仍然静默接受 `X<T>()` 和 `~X<T>()`；GCC 会给出 `-Wtemplate-id-cdtor` 警告。

### 构造函数没有名字（¶1–¶2）

¶1 最后明确说，构造函数没有名字。由此有几个直接后果：

- 无限定名字查找永远找不到构造函数（¶2 注 1）。
- `S(1)` 不是在调用构造函数，而是函数式记法的显式类型转换（[[expr.type.conv]]）。它产生一个 prvalue，初始化这个 prvalue 的结果对象时才调用构造函数。
- 成员不能与类同名的限制（[[class.mem.general#25]]）不适用于构造函数。

C++17 起，`S x = S(1);` 只调用一次构造函数。prvalue `S(1)` 直接初始化结果对象 `x`，中间没有临时对象，也不需要可用的复制或移动构造函数（[[class.temporary]]、[[dcl.init]]）。

¶3 注 5 提醒，在构造期间调用虚函数等操作有特殊语义，见 [[class.base.init]] 和 [[class.cdtor]]。

## 构造期间对象还不是 const（¶4）

```cpp run title="const-during-ctor.cpp" ok
struct K {
    int v;
    constexpr K() : v(0) {
        v = 5;   // OK: 构造期间可以修改成员
    }
};

const K k;           // 构造结束后才成为 const
constexpr K ck;
static_assert(ck.v == 5);

int main() { return k.v - 5; }
```

¶4 构造函数可以为 `const`、`volatile` 或 `const volatile` 对象调用。正在构造的对象不受 `const` 和 `volatile` 语义约束。这些语义在**最派生对象**（[[g:most-derived-object]]，不是任何其他对象子对象的那个完整对象）的构造函数结束时才生效。

如果没有这条规则，上面构造函数体里的 `v = 5` 就是在修改 const 对象，属于未定义行为。

生效的时间点是最派生对象的构造结束，而不是各个子对象的构造结束。派生类构造函数体执行时，基类部分虽然已经构造完毕，仍然可以修改。`volatile` 也一样，构造期间对成员的访问不算 volatile 访问。

## 三条禁令（¶5–¶7）

```cpp title="ctor-restrictions.cpp" error
struct S {
    S() { }
    S(int) { return; }         // OK: 不带值的 return
    S(long) { return 1; }      // error: 不能返回值
    S(this S self, char);      // error: 不能有显式对象形参
};
auto p = &S::S;                // error: 不能取构造函数的地址
```

¶5 不能取构造函数的地址。构造函数体中的 `return` 也不能带值（注 6，[[stmt.return]]）。

构造函数接收的是还没有初始化的存储，在 ABI 层面往往有多个版本（见下文实现视角），所以没有一个统一的函数指针能代表它。需要把构造当作可调用对象时，用 lambda 或 `std::construct_at`。

¶6 构造函数不能是协程。协程挂起时对象只构造了一半，它的生命周期无法定义。

¶7 构造函数不能有显式对象形参（[[dcl.fct]]）。构造函数开始执行时对象还不存在，没有东西可以作为对象实参传进去。

## 默认构造函数 [class.default.ctor]

### 什么是默认构造函数（¶1）

```cpp title="ambiguous-default.cpp" error
struct Amb {
    Amb();
    Amb(int = 0);   // 也是默认构造函数
};
Amb a;              // error: 二义
Amb b(1);           // OK: 只有 Amb(int) 可行
```

¶1 如果一个构造函数的每个形参（函数形参包除外）都有默认实参，它就是**默认构造函数**（default constructor）。没有形参的构造函数当然也算。所以 `X()`、`X(int = 0)`、`X(int = 0, double = 1.0)` 都是默认构造函数。一个类可以有好几个，但默认初始化时会二义。

### 隐式声明与抑制（¶1）

¶1 如果类没有**用户声明**（[[g:user-declared]]，在类里写出了声明，包括 `= default` 和 `= delete`）的构造函数或构造函数模板，并且不是匿名联合体，编译器就隐式声明一个无形参、非 explicit 的默认构造函数。它是**预置**的（defaulted，由编译器按规则生成定义，[[dcl.fct.def]]），也是类的 inline public 成员。

```cpp run title="suppressed.cpp" ok
#include <type_traits>

struct A { };
struct B { B(int); };
struct C { C(const C&) = default; };
struct D { template<class T> D(T); };
struct E { E(int); E() = default; };

static_assert( std::is_default_constructible_v<A>);
static_assert(!std::is_default_constructible_v<B>);
static_assert(!std::is_default_constructible_v<C>);
static_assert(!std::is_default_constructible_v<D>);
static_assert( std::is_default_constructible_v<E>);
int main() { }
```

任何用户声明的构造函数都会抑制隐式默认构造函数：普通构造函数（`B`）、复制构造函数（`C`）、构造函数模板（`D`），以及 `= delete` 的构造函数。还想要默认构造函数，就像 `E` 那样显式写 `= default`。

继承构造函数（`using Base::Base;`）不算本类用户声明的构造函数，不会抑制隐式默认构造函数。

### 何时被删除（¶2）

```cpp title="default-deleted.cpp" error
#include <string>

struct R  { int& r; };
struct C1 { const int c; };
struct C2 { const std::string s; };
struct C3 { const int c = 1; };
struct P  { private: P(); };
struct Q  { P p; };

R  r;      // error: ¶2.1
C1 c1;     // error: ¶2.2
C2 c2;     // OK
C3 c3;     // OK
Q  q;      // error: ¶2.3
```

¶2 预置的默认构造函数在下面四种情况下**定义为弃置**（defined as deleted），即视同写了 `= delete`，调用它就是错误：

- ¶2.1 有引用类型的非静态数据成员，并且它没有默认成员初始化器。引用必须绑定到某个对象。
- ¶2.2 类不是联合体，有一个 `const` 类型的非变体成员没有初始化器，而且它的类型不是 **const-default-constructible**（[[g:const-default-constructible]]）的。
- ¶2.3 某个非变体的**潜在构造子对象**（[[g:potentially-constructed-subobjects]]，直接基类、非静态数据成员，最派生时还包括虚基类）没有初始化器，而为它选默认构造函数的重载决议找不到可用的候选：失败、二义、选中了弃置的函数，或者选中的函数不可访问。
- ¶2.4 某个潜在构造子对象的析构函数被删除或不可访问，并且这个子对象不是变体成员，或者带有默认成员初始化器。

**变体成员**（[[g:variant-member]]）指联合体的成员，以及匿名联合体里的成员。

const-default-constructible 大致是说，对这个类型做默认初始化能得到确定的值：要么会调用用户提供的构造函数（如 `std::string`），要么每个成员都有默认成员初始化器（详见 [[dcl.init.general#7]]）。所以 `C2` 合法，`C1` 不合法。

¶2.4 检查析构函数，是因为构造函数可能在中途因异常退出。这时要析构已经构造好的子对象（[[except.ctor]]），所以析构函数必须可用。

### 联合体：C++26 的平凡联合体 {{c++26}}

¶2.3 和 ¶2.2 都只看非变体成员；¶2.4 只在变体成员有默认成员初始化器时才检查它的析构函数。所以联合体的成员即使有非平凡的默认构造函数，也不会让联合体的默认构造函数被删除。

```cpp title="trivial-union.cpp"
#include <string>

union U { std::string s; };   // C++26: 默认构造平凡，未被删除
U u;                          // C++26 OK；C++23 error
int main() { }
```

这是 C++26 的变化（[[P3074R7]]）。C++23 中，变体成员带非平凡默认构造函数、又没有任何变体成员有默认成员初始化器时，联合体的默认构造函数被删除，使用者必须手写 `U() {}`。C++26 删掉了这条，析构函数的规则也相应调整（[[class.dtor#7]]）。

于是 `std::optional`、`std::inplace_vector` 这类需要手动管理元素生命周期的存储，可以直接写成 `union { T storage[N]; };`，在常量求值中也能用。本机 Clang 23 还没有实现这一变化，对上例报告默认构造函数被隐式删除，所以这个例子不标判定。

### 平凡的默认构造函数（¶3）

```cpp run title="trivial-default.cpp" ok
#include <type_traits>

struct T1 { int x; };
struct T2 { int x = 0; };
struct T3 { virtual void f(); };
struct T4 : T2 { };
struct T5 { T5() = default; int x; };
struct T6 { T6(); int x; };
T6::T6() = default;

using std::is_trivially_default_constructible_v;
static_assert( is_trivially_default_constructible_v<T1>);
static_assert(!is_trivially_default_constructible_v<T2>);
static_assert(!is_trivially_default_constructible_v<T3>);
static_assert(!is_trivially_default_constructible_v<T4>);
static_assert( is_trivially_default_constructible_v<T5>);
static_assert(!is_trivially_default_constructible_v<T6>);
int main() { }
```

¶3 默认构造函数**平凡**（trivial）的前提是它不是**用户提供**（[[g:user-provided]]）的。用户提供指用户声明了它，并且没有在第一次声明处 `= default` 或 `= delete`。所以 `T5` 不是用户提供的，`T6` 在类外 `= default`，是用户提供的。此外还要满足四条：

- ¶3.1 类没有虚函数和虚基类（否则要设置虚表指针，`T3`）；
- ¶3.2 没有非静态数据成员带默认成员初始化器（否则要执行初始化器，`T2`）；
- ¶3.3 所有直接基类的默认构造函数都平凡（`T4`）；
- ¶3.4 类是联合体，或者它所有类类型（或其数组）的非变体非静态数据成员，其默认构造函数都平凡。

平凡的默认构造函数什么也不做，标量成员不被初始化。对自动存储期的对象，C++26 起这些成员持有错误值，读取它们是错误行为（[[basic.indet]]）。

¶3.4 中联合体一律满足条件，是 C++26 平凡联合体的另一半。C++23 要求联合体的变体成员也有平凡默认构造函数。

### 类外 `= default` 会改变 `T{}` 的结果

默认构造函数是不是用户提供的，还决定了**值初始化**（[[g:value-initialization]]，`T()` 或 `T{}` 在没有更合适的初始化方式时所做的初始化）的行为：选中的默认构造函数不是用户提供的，就先把整个对象零初始化，再调用它；是用户提供的，就只调用它（[[dcl.init.general#8]]）。

```cpp run title="value-init.cpp" ok
struct A { int x; };
struct B { B() = default; int x; };
struct C { C(); int x; };
C::C() = default;   // 类外预置：用户提供

int main() {
    A a{};   // 聚合初始化：x == 0
    B b{};   // 值初始化，先清零：x == 0
    C c{};   // 值初始化，只调用 C()：x 未初始化
    (void)b; (void)c;
    return a.x;
}
```

- `A` 是聚合（[[dcl.init.aggr]]），`A{}` 是聚合初始化，`x` 被值初始化为 0。
- `B` 有用户声明的构造函数，C++20 起不再是聚合，`B{}` 是值初始化。`B()` 不是用户提供的，所以先清零，`b.x == 0`。
- `C{}` 也是值初始化，但 `C()` 是用户提供的，不清零。读 `c.x` 在 C++26 中是错误行为，此前是未定义行为。

只是把 `= default` 从类内挪到类外，`T{}` 的结果就从全零变成了未初始化。

### 隐式定义（¶4）

¶4 隐式定义的默认构造函数，所做的初始化与一个没有成员初始化列表、函数体为空的手写默认构造函数完全相同：有默认成员初始化器的成员用它初始化，其余的基类和成员默认初始化。如果那个手写版本是非良构的，程序就是非良构的。

¶4 还规定隐式定义的默认构造函数是 `constexpr` 的。这不意味着它总能用在常量表达式里，能否常量求值仍取决于它实际做了什么：

```cpp title="constexpr-default.cpp" error
struct S { int x; };
constexpr S s1{};   // OK: 值初始化，x == 0
constexpr S s2;     // error: 默认初始化 const 对象，
                    // 但 S 不是 const-default-constructible

struct N {
    int* p = new int(1);
    constexpr ~N() { delete p; }
};
constexpr bool ok() { N n; return *n.p == 1; }
static_assert(ok());   // OK: 编译期分配并在同一次求值中释放
```

预置的默认构造函数被隐式定义之前，它的基类和成员的所有非用户提供的默认构造函数先被隐式定义。隐式声明的默认构造函数带有隐含的异常说明：它要调用的函数都不抛出时，它就是 `noexcept` 的（注 1，[[except.spec]]）。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶5 注 2：没有给出初始化器时（默认初始化，[[dcl.init.general]]），会隐式调用默认构造函数来初始化类对象，它必须可访问。

¶6 注 3：基类和成员的构造顺序，以及如何为它们指定实参，见 [[class.base.init]]。

</details>

## 实现视角

!!! impl "一个构造函数，多个符号"
    Itanium C++ ABI 为每个构造函数生成两个变体：C1（complete object constructor）构造完整对象，包括虚基类；C2（base object constructor）作为基类子对象构造，跳过虚基类。规范还有 C3（allocating constructor），实践中不用。没有虚基类时 C1 和 C2 行为相同，GCC 和 Clang 常把其中一个作为另一个的别名。

    平凡的默认构造函数不生成任何代码。隐式定义的非平凡默认构造函数（例如有 `std::string` 成员）依次调用成员的构造函数，通常会被内联。

## 历史与演进

!!! history
    - C++98 已有隐式声明的默认构造函数和平凡性的概念（用于 POD）。
    - C++11 引入 `= default`、`= delete` 和默认成员初始化器，并用定义为弃置取代了隐式定义非良构，引用成员和 `const` 成员从此使默认构造函数被删除。
    - C++20 起有用户声明构造函数的类不再是聚合，类模板中不能再用 `X<T>()` 声明构造函数。
    - C++23 放宽了 `constexpr` 函数的限制，隐式定义的默认构造函数改为无条件 `constexpr`。
    - C++26 的平凡联合体（[[P3074R7]]）让联合体的变体成员不再导致默认构造函数被删除或非平凡；默认初始化的标量成员持有错误值。

## 常见误解

!!! pitfall "以为构造函数模板能代替默认构造函数"
    `template<class... Ts> X(Ts&&...);` 能匹配零个实参，所以 `X x;` 会用它。但它会抑制隐式默认构造函数，自己又不是预置的，于是 `X` 不再有平凡的默认构造函数。

!!! pitfall "给成员加了默认成员初始化器，平凡性随之改变"
    `struct P { int x = 0; };` 的默认构造函数不是平凡的，`std::is_trivially_default_constructible_v<P>` 为 `false`。某些依赖平凡默认构造的优化（例如容器扩容时跳过初始化）因此失效，但 `P` 仍然是平凡可复制的。

## 思考题

!!! question "思考题 1"
    下面哪些类有可用的默认构造函数？

    ```cpp
    struct A { int& r = *new int; };
    struct B { const int c; B() = default; };
    union  C { const int c; int i; };
    struct D { struct { const int c; } s; };
    ```

<details markdown="1">
<summary>答案</summary>

- `A` 可用。引用成员有默认成员初始化器，¶2.1 不适用（这段代码会泄漏内存，但合法）。
- `B` 不可用。`c` 没有初始化器，`const int` 也不是 const-default-constructible，按 ¶2.2 预置的默认构造函数被删除。Clang 对这个声明给出 `-Wdefaulted-function-deleted` 警告。
- `C` 可用。¶2.2 只针对非联合体类，`c` 是变体成员。`C x;` 合法，`x` 没有活跃成员。但 `const C x;` 不合法：联合体要成为 const-default-constructible，需要恰好一个变体成员带默认成员初始化器。
- `D` 不可用。成员 `s` 的无名类型因 ¶2.2 没有可用的默认构造函数，于是对 `D` 而言 ¶2.3 成立。

</details>

!!! question "思考题 2"
    `struct E { E(); int x; }; E::E() = default;` 中，`E e{};` 之后 `e.x` 的值是什么？把 `= default` 移进类内呢？

<details markdown="1">
<summary>答案</summary>

类外 `= default` 使 `E()` 成为用户提供的。`E{}` 是值初始化（`E` 有用户声明的构造函数，不是聚合），只调用 `E()`，`x` 没有被初始化，读取它在 C++26 中是错误行为。移进类内后 `E()` 不再是用户提供的，值初始化先零初始化，`e.x == 0`（[[dcl.init.general#8]]）。

</details>
