---
title: 构造函数
summary: 构造函数的声明形式（没有名字、只能用注入类名声明）、允许的说明符、构造期间 cv 语义不生效、不能取地址/不能是协程/不能有显式对象形参；默认构造函数的定义、隐式声明、何时被删除、何时平凡、隐式定义的内容与 constexpr
status: draft
covers: class.ctor.general, class.default.ctor
related: special, class.copy.ctor, class.base.init, class.init, dcl.init, class.cdtor, class.prop, class.conv.ctor
tags: 构造函数, 默认构造, 平凡, 值初始化
updated: 2026-10-17
---

构造函数的作用是把一块原始存储变成一个类对象。它在语言中的地位很特殊：没有名字，没有返回类型，不能取地址，也不能用普通的函数调用语法调用，总是**作为初始化的一部分隐式调用**。本页覆盖 11.4.5 的前两个子条款：

- [[class.ctor.general]]：构造函数的一般规则（下文 ¶ 编号默认指此条款）；
- [[class.default.ctor]]：默认构造函数（以 [class.default.ctor] ¶N 的形式标注）。

复制/移动构造函数见 [[class.copy.ctor]]；构造函数如何初始化基类和成员（成员初始化列表、委托构造、初始化顺序）见 [[class.base.init]]；构造期间调用虚函数等规则见 [[class.cdtor]]；`explicit` 与隐式转换见 [[class.conv.ctor]]。

## 构造函数的声明形式（¶1）

¶1：一个*声明符*如果是形如

```text
ptr-declarator ( parameter-declaration-clause ) noexcept-specifier(可选) 属性(可选)
```

的函数声明符，其中 *ptr-declarator* 只由一个 *id-expression*（可带属性、可加括号）组成，并且这个 *id-expression* 是以下形式之一，那么它声明的是构造函数：

- ¶1.1 在友元声明中：指名一个构造函数的 *qualified-id*（`friend X::X();`，[[class.qual]]）；
- ¶1.2 否则，在类或类模板的 *member-specification* 中的成员声明里：直接外围实体的注入类名（[[class.pre#2]]）；
- ¶1.3 否则：一个 *qualified-id*，其 *unqualified-id* 是其查找上下文的注入类名（类外定义 `X::X() { }`）。

换句话说，**构造函数是按语法形状识别的**：在类内，前面没有类型、由注入类名加形参列表构成的声明，就是构造函数声明。

构造函数没有名字，这一点有实际后果：

- 无限定名字查找永远找不到构造函数（¶2 注 1）。`X(1)` 这种写法是一个显式类型转换（函数式记法，[[expr.type.conv]]），它创建一个临时对象，只是看起来像在调用构造函数；
- [[class.mem.general#25]] 中成员不能与类同名的限制不适用于构造函数（注 9）；
- 不能写 `&X::X` 取构造函数的地址（¶5）。

在构造函数声明中，*decl-specifier-seq* 里只能出现：`friend`、`inline`、`constexpr`、`consteval`、*explicit-specifier*（`explicit` 或 `explicit(bool)`）。没有返回类型，也不能写 `void`，不能是 `static`、`virtual`。

```cpp title="ctor-decl.cpp" error
struct S {
    S();                     // 声明构造函数
    explicit S(int);         // OK
    constexpr S(double) { }  // OK
    void S(char);            // error: 构造函数不能有返回类型
    static S(long);          // error: 构造函数不能是 static
    virtual S(short);        // error: 构造函数不能是 virtual
};
S::S() { }                   // 类外定义：qualified-id，unqualified-id 是 S 的注入类名
```

!!! lawyer "类模板中的 `X<T>()`"
    ¶1.2 要求在类内声明构造函数时使用注入类名本身。在类模板 `template<class T> struct X` 中，`X<T>` 是一个 *simple-template-id*，不是注入类名，所以从 C++20 起，`X<T>();` 作为构造函数声明是非良构的（C++17 及以前普遍接受这种写法）。正确写法是 `X();`。截至写作时，Clang 23 对 `X<T>();` 仍静默接受。析构函数同理，应写 `~X();` 而不是 `~X<T>();`（[[class.dtor#1]]）。

## 构造函数用于初始化（¶2–¶3）

¶2：构造函数用于初始化其类类型的对象。注 1–4：

- 函数式记法 `complex(1, 2.3)` 会调用构造函数来初始化一个对象，语法上像是显式调用构造函数；
- 类对象的初始化见 [[class.init]]；临时对象的生命周期见 [[class.temporary]]；
- 所谓显式构造函数调用（即 `T(args)` 形式）不产生左值（[[basic.lval]]），它是一个 prvalue。

C++17 引入保证复制消除（[[class.temporary]]、[[dcl.init]]）之后，`T x = T(args);` 中只调用一次构造函数：prvalue `T(args)` 直接初始化结果对象 `x`，没有临时量，也不需要可用的复制/移动构造函数。

¶3 注 5：某些语言构造在构造期间有特殊语义（如在构造函数中调用虚函数），见 [[class.base.init]] 和 [[class.cdtor]]。

## 构造期间 cv 语义不生效（¶4）

¶4：构造函数可以为 `const`、`volatile`、`const volatile` 对象调用。**正在构造的对象不受 `const` 和 `volatile` 语义约束**，这些语义在最派生对象（[[intro.object]]）的构造函数结束时才生效。

这条规则显然是必需的，`const` 对象的成员总得有机会被赋值。没有它，下面的代码就是在修改 `const` 对象（UB）：

```cpp run title="const-during-ctor.cpp" ok
struct K {
    int v;
    constexpr K() : v(0) {
        v = 5;          // OK: 构造期间，即使对象最终是 const，也可以修改成员
    }
};

const K k;              // const 对象：构造函数结束后才变成 const
constexpr K ck;         // 常量求值中同样允许
static_assert(ck.v == 5);

int main() { return k.v - 5; }
```

措辞是最派生对象的构造函数结束时，这意味着派生类构造函数体执行时，基类子对象的构造函数虽已结束，`const` 语义仍未生效。整个对象要等最外层的构造完成，才作为一个整体变为 const。`volatile` 也一样：构造期间对成员的访问不是 volatile 访问，编译器可以优化它们。

## 不能取地址、不能是协程、不能有显式对象形参（¶5–¶7）

- ¶5：不能取构造函数的地址。注 6：构造函数体中的 `return` 语句不能带返回值（[[stmt.return]]）。为什么不能取地址？构造函数不是普通函数：它需要接收未初始化的存储，可能还需要额外的隐藏参数（如 Itanium ABI 中构造虚基类时的 VTT 指针），并且有多个 ABI 变体（完整对象构造函数 C1 与基类子对象构造函数 C2），没有一个统一的函数指针能代表它。需要把构造当作可调用对象使用时，可以用 lambda 或 `std::construct_at`。
- ¶6：构造函数不能是协程。协程的返回值由 promise 对象产生，而构造函数根本没有返回值；而且协程挂起时对象只构造了一半，生命周期语义无法定义。
- ¶7：构造函数不能有显式对象形参（[[dcl.fct]]）。构造函数开始执行时对象还不存在，没有东西可以作为对象实参传入。

```cpp title="ctor-restrictions.cpp" error
struct S {
    S() { }
    S(int) { return; }            // OK: 不带值的 return
    S(long) { return 1; }         // error: 构造函数不能返回值
    S(this S self, char);         // error: 构造函数不能有显式对象形参
};
auto p = &S::S;                   // error: 不能取构造函数的地址
```

---

# 默认构造函数（[class.default.ctor]）

## 定义与隐式声明（[class.default.ctor] ¶1）

[[class.default.ctor#1]]：如果一个构造函数的每个形参（函数形参包除外）都有默认实参，它就是类 `X` 的**默认构造函数**，没有形参的情形也包括在内。所以 `X()`、`X(int = 0)`、`X(int = 0, double = 1.0)` 都是默认构造函数。

一个类可以有多个默认构造函数，但用它们默认初始化时会产生二义性：

```cpp title="ambiguous-default.cpp" error
struct Amb {
    Amb();
    Amb(int = 0);     // 也是默认构造函数
};
Amb a;                // error: 调用二义
Amb b(1);             // OK: 只有 Amb(int) 可行
```

**隐式声明**：如果类没有用户声明的构造函数或构造函数模板，并且不是匿名联合体，就隐式声明一个无形参的非 explicit 构造函数，它是预置的（[[dcl.fct.def]]）。隐式声明的默认构造函数是类的 inline public 成员。

任何用户声明的构造函数都会抑制默认构造函数，包括复制构造函数、移动构造函数、构造函数模板、`= delete` 的构造函数。继承构造函数（`using Base::Base;`）则不算本类用户声明的构造函数，不会抑制。

```cpp run title="suppressed.cpp" ok
#include <type_traits>

struct A { };                          // 隐式默认构造
struct B { B(int); };                  // 用户声明了构造函数 ⇒ 无默认构造
struct C { C(const C&) = default; };   // 复制构造也是构造函数 ⇒ 无默认构造
struct D { template<class T> D(T); };  // 构造函数模板 ⇒ 无默认构造
struct E { E(int); E() = default; };   // 想要的话就显式预置

static_assert( std::is_default_constructible_v<A>);
static_assert(!std::is_default_constructible_v<B>);
static_assert(!std::is_default_constructible_v<C>);
static_assert(!std::is_default_constructible_v<D>);
static_assert( std::is_default_constructible_v<E>);
int main() { }
```

## 预置的默认构造函数何时被删除（[class.default.ctor] ¶2）

[[class.default.ctor#2]]：在下列情形中，类 `X` 的预置默认构造函数**定义为弃置**：

- ¶2.1 某个非静态数据成员是引用类型，且没有默认成员初始化器，因为引用必须绑定；
- ¶2.2 `X` 是非联合体类，某个非变体非静态数据成员是 `const` 限定类型（或其多维数组），没有 *brace-or-equal-initializer*，而且不是 const-default-constructible 的（[[dcl.init.general#7]]），因为 `const` 对象必须有确定的值；
- ¶2.3 某个非变体的潜在构造子对象（有 *brace-or-equal-initializer* 的数据成员除外）是类类型 `M`（或其多维数组），而为找到 `M` 的对应构造函数所做的重载决议没有得到可用的候选（[[over.match.general#4]]：失败、二义、选中弃置函数或不可访问函数）；
- ¶2.4 某个潜在构造子对象 S 是类类型 `M`（或其多维数组），`M` 的析构函数被删除或从该预置默认构造函数中不可访问，并且 S 是非变体的或有默认成员初始化器。构造函数中途抛异常时需要析构已构造的子对象，所以析构函数必须可用。

**const-default-constructible** 大致是说，对这个类型做默认初始化能得到有意义的值：要么会调用用户提供的构造函数（如 `std::string`），要么每个成员都有默认成员初始化器（或递归地是 const-default-constructible），等等。

```cpp title="default-deleted.cpp" error
#include <string>

struct R  { int& r; };                 // ¶2.1
struct C1 { const int c; };            // ¶2.2: const int 不是 const-default-constructible
struct C2 { const std::string s; };    // OK: std::string 有用户提供的默认构造函数
struct C3 { const int c = 1; };        // OK: 有默认成员初始化器
struct P  { private: P(); };
struct Q  { P p; };                    // ¶2.3: P() 不可访问 ⇒ 不可用候选

R  r;                                  // error: 默认构造函数被删除
C1 c1;                                 // error: 同上
C2 c2;                                 // OK
C3 c3;                                 // OK
Q  q;                                  // error: 默认构造函数被删除
```

### 联合体：C++26 的平凡联合体 {{c++26}}

¶2.3 只看非变体的子对象。也就是说，联合体的变体成员即使有非平凡的默认构造函数，也不会导致联合体的默认构造函数被删除；¶2.4 也只在变体成员有默认成员初始化器时才检查其析构函数。

这是 C++26 的变化。C++23 及以前，¶2 还有一条：如果联合体的某个变体成员带非平凡默认构造函数，并且没有任何变体成员有默认成员初始化器，联合体的默认构造函数就被删除。这迫使 `union { std::string s; }` 的使用者必须手写 `U() {}`，否则连对象都定义不了。C++26 删除了这一条（联合体的析构函数规则也相应调整，见 [[class.dtor#7]]），现在：

```cpp title="trivial-union.cpp"
#include <string>

union U { std::string s; };   // C++26：默认构造函数平凡、未被删除；不开始 s 的生命周期
U u;                          // C++26 OK；C++23 error: 默认构造函数被删除
// 截至写作时，Clang 23 尚未实现这一变化，仍报"implicitly-deleted default constructor"
int main() { }
```

这样，需要手动管理生命周期的存储（如 `std::optional`、`std::inplace_vector` 的元素存储）可以直接写成 `union { T storage[N]; };`，在常量求值中也能使用。

## 平凡默认构造函数（[class.default.ctor] ¶3）

[[class.default.ctor#3]]：如果类 `X` 的默认构造函数不是用户提供的，并且满足下列条件，它就是**平凡的**：

- ¶3.1 `X` 没有虚函数和虚基类（否则需要设置 vptr）；
- ¶3.2 `X` 的非静态数据成员都没有默认成员初始化器（否则需要执行初始化器）；
- ¶3.3 `X` 的所有直接基类都有平凡默认构造函数；
- ¶3.4 `X` 是联合体，或者 `X` 的所有类类型（或其数组）的非变体非静态数据成员都有平凡默认构造函数 {{c++26}}（C++23 中联合体的变体成员也要求平凡）。

否则默认构造函数是非平凡的。**平凡的默认构造函数什么也不做**，对象的成员处于不确定状态（C++26 起为错误值，[[basic.indet]]）。

```cpp run title="trivial-default.cpp" ok
#include <type_traits>

struct T1 { int x; };                         // 平凡
struct T2 { int x = 0; };                     // ¶3.2：有默认成员初始化器 ⇒ 非平凡
struct T3 { virtual void f(); };              // ¶3.1 ⇒ 非平凡
struct T4 : T2 { };                           // ¶3.3 ⇒ 非平凡
struct T5 { T5() = default; int x; };         // 首次声明即预置：非用户提供 ⇒ 平凡
struct T6 { T6(); int x; };
T6::T6() = default;                           // 类外预置：用户提供 ⇒ 非平凡

static_assert( std::is_trivially_default_constructible_v<T1>);
static_assert(!std::is_trivially_default_constructible_v<T2>);
static_assert(!std::is_trivially_default_constructible_v<T3>);
static_assert(!std::is_trivially_default_constructible_v<T4>);
static_assert( std::is_trivially_default_constructible_v<T5>);
static_assert(!std::is_trivially_default_constructible_v<T6>);
int main() { }
```

### 用户提供与值初始化的微妙联系

默认构造函数是否用户提供，不仅影响平凡性，还影响值初始化（[[dcl.init.general#8]]）。值初始化 `T{}`/`T()` 时，如果选中的默认构造函数不是用户提供的，对象先零初始化，然后再默认初始化；如果是用户提供的，就只调用它。于是：

```cpp run title="value-init.cpp" ok
struct A { int x; };                 // 隐式默认构造：非用户提供
struct B { B() = default; int x; };  // 首次声明预置：非用户提供
struct C { C(); int x; };
C::C() = default;                    // 类外预置：用户提供！

int main() {
    A a{};      // 聚合初始化：x = 0
    B b{};      // C++20 起 B 不是聚合：值初始化，B() 非用户提供 ⇒ 先零初始化，x = 0
    C c{};      // 值初始化：C() 是用户提供的 ⇒ 不先零初始化 ⇒ c.x 是错误值
    (void)b; (void)c;
    return a.x;
}
```

- `A a{}`：`A` 是聚合，聚合初始化把 `x` 值初始化为 0。
- `B b{}`：C++20 起，有用户声明的构造函数的类不再是聚合（[[dcl.init.aggr]]），所以 `B{}` 是值初始化；`B()` 不是用户提供的，因此先零初始化，`b.x == 0`。
- `C c{}`：值初始化，但 `C()` 是用户提供的（类外 `= default`），因此不会零初始化，读 `c.x` 得到错误值（C++26 起为错误行为，[[basic.indet]]；之前为 UB）。

**把 `= default` 从类内挪到类外，`T{}` 的结果就从全零变成未初始化**，这是 C++ 中最反直觉的规则之一。

## 隐式定义（[class.default.ctor] ¶4）

[[class.default.ctor#4]]：隐式定义（[[dcl.fct.def.default]]）的默认构造函数所执行的初始化，与一个没有成员初始化列表、函数体为空的用户编写的默认构造函数完全相同。也就是说：

- 有默认成员初始化器的成员用它初始化；
- 其他成员和基类默认初始化（类类型调用默认构造函数，标量不初始化）。

如果那个用户编写的默认构造函数会是非良构的，程序就非良构。**隐式定义的默认构造函数是 `constexpr` 的。** 在预置默认构造函数被隐式定义之前，其基类和非静态数据成员的所有非用户提供的默认构造函数先被隐式定义（自底向上）。

注 1：隐式声明的默认构造函数有一个异常说明（[[except.spec]]）：如果它会调用的所有函数都不抛出，它就是 `noexcept` 的。显式预置的定义可能有隐式的异常说明。

### 隐式定义是 constexpr

在 C++20 及以前，隐式定义的默认构造函数只有在满足 constexpr 构造函数的要求时才是 `constexpr` 的。C++23 放宽了对 `constexpr` 函数的限制，一个函数能否用于常量求值，改由调用时实际做了什么来决定，于是现在直接规定它是 `constexpr` 的。但这不意味着它总能在常量表达式中使用：

```cpp title="constexpr-default.cpp" error
#include <string>

struct S { int x; };
constexpr S s1{};        // OK: 值初始化，x == 0
constexpr S s2;          // error: const 对象的默认初始化要求类型 const-default-constructible（[dcl.init]）

struct N { int* p = new int(1); constexpr ~N() { delete p; } };
constexpr bool ok() { N n; return *n.p == 1; }   // OK: N 的隐式默认构造函数是 constexpr 的，
                                                  //     常量求值中允许 new/delete 配对的瞬态分配
static_assert(ok());
```

## 注：默认构造函数何时被调用（[class.default.ctor] ¶5–¶6）

[[class.default.ctor#5]] 注 2：没有指定初始化器时（默认初始化，[[dcl.init.general]]），会隐式调用默认构造函数来初始化类对象，它必须是可访问的。[[class.default.ctor#6]] 注 3：基类和成员的构造顺序以及如何为它们指定实参，见 [[class.base.init]]。

## 实现视角

!!! impl "C1/C2/C3：一个构造函数，多个符号"
    Itanium ABI 为每个构造函数发出多个变体：C1（complete object constructor，构造完整对象，包括虚基类）和 C2（base object constructor，作为基类子对象构造，跳过虚基类）；C3（allocating constructor）在规范中保留，但实践中不使用。没有虚基类时 C1 与 C2 行为相同，GCC/Clang 常把其中一个作为另一个的别名。这是 ¶5 不允许取构造函数地址在 ABI 层面的原因之一。

!!! impl "平凡默认构造不生成代码"
    对 `T1 t;`（平凡默认构造），编译器不生成任何指令；对 `std::vector<T1> v(n);` 这种值初始化，库会用 `memset` 零初始化。对非平凡但隐式定义的默认构造函数（如含 `std::string` 成员），编译器生成一个依次调用成员构造函数的函数，通常会被内联。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：没有用户声明的构造函数时隐式声明默认构造函数；平凡的定义已经存在（用于 POD）。
    - **C++11**：`= default`/`= delete`；默认成员初始化器（使默认构造非平凡）；用定义为弃置的规则取代隐式定义非良构；引用/`const` 成员使默认构造函数被删除；继承构造函数。
    - **C++20**：有用户声明构造函数的类不再是聚合；禁止在类模板中用 `X<T>()` 声明构造函数；隐式定义的特殊成员函数在常量求值中更容易使用。
    - **C++23**：随着 `constexpr` 限制的放宽，隐式定义的默认构造函数无条件 `constexpr`。
    - **C++26 草案**：联合体的变体成员不再导致默认构造函数被删除，联合体的默认构造函数可以平凡（平凡联合体）；默认初始化的标量成员具有错误值（erroneous value），而不是不确定值。

## 陷阱

!!! pitfall "类外 `= default` 改变了值初始化的结果"
    见 `value-init.cpp`。如果希望 `T{}` 零初始化，要么在类内 `= default`，要么给成员加默认成员初始化器。

!!! pitfall "给成员加了默认成员初始化器，默认构造不再平凡"
    `struct P { int x = 0; };` 的默认构造函数非平凡，`std::is_trivially_default_constructible_v<P>` 为 `false`。这会影响一些要求平凡默认构造的优化（例如某些容器在 `resize` 时跳过初始化），但它仍然是平凡可复制的。

!!! pitfall "以为构造函数模板能替代默认构造函数"
    `template<class... Ts> X(Ts&&...);` 能匹配零个实参，于是 `X x;` 会使用它（模板特化可以作为默认构造函数调用）。但它抑制了隐式默认构造函数，而且它不是预置的，所以 `X` 不会有平凡默认构造函数。

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

- `A`：引用成员有默认成员初始化器，¶2.1 不适用，所以可用（虽然这段代码会泄漏内存）。
- `B`：在首次声明处预置。按 ¶2.2，`const int` 没有初始化器，且不是 const-default-constructible，所以预置的默认构造函数定义为弃置，不可用（Clang 会提示 "explicitly defaulted default constructor is implicitly deleted"）。
- `C`：联合体。¶2.2 只针对非联合体类，`c` 是变体成员，所以默认构造函数未被删除。可以写 `C x;`（`x` 没有活跃成员），但 `const C x;` 不行，因为 `C` 不是 const-default-constructible：联合体需要恰好一个变体成员有默认成员初始化器。
- `D`：成员 `s` 的类型（无名类）的默认构造函数因 `const int` 而被删除，于是对 `D` 而言 ¶2.3 成立，不可用。
</details>

!!! question "思考题 2"
    为什么 ¶2.4 要求子对象的析构函数可用，才能保留默认构造函数？

<details markdown="1">
<summary>答案</summary>

构造函数可能在构造到一半时因异常退出（例如第三个成员的构造函数抛出），这时语言规定要析构已经构造完成的子对象（[[except.ctor]]）。所以默认构造函数中隐含着对每个子对象析构函数的潜在调用（[[class.dtor#14]] 中的 potentially invoked）。如果某个子对象的析构函数被删除或不可访问，这个隐含调用就无法进行，默认构造函数也就只能删除。这与用户编写的空构造函数在同样情况下会非良构是一致的。
</details>

## 小结

| 主题 | 规则 |
|---|---|
| 声明形式 | 类内用注入类名；类外用 `X::X`；构造函数没有名字 |
| 允许的说明符 | `friend`、`inline`、`constexpr`、`consteval`、`explicit` |
| 构造期间 | `const`/`volatile` 语义在最派生对象构造完成后才生效 |
| 禁止 | 取地址、返回值、协程、显式对象形参 |
| 默认构造函数 | 所有（非包）形参都有默认实参的构造函数 |
| 隐式声明 | 没有任何用户声明的构造函数（模板）时；inline public、非 explicit |
| 定义为弃置 | 无初始化器的引用成员；非 const-default-constructible 的 `const` 成员；非变体子对象无法默认构造；子对象析构不可用 |
| 平凡 | 非用户提供 + 无虚 + 无默认成员初始化器 + 基类与（非联合体的）类类型成员平凡 |
| 隐式定义 | 等同于空函数体、无初始化列表的用户版本；`constexpr` |
| C++26 | 联合体的变体成员不再阻止默认构造（平凡联合体） |
