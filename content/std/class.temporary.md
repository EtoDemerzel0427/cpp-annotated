---
title: 临时对象
summary: 临时对象只在 prvalue 被物化（或为在寄存器中传参/返回）时才创建；通常在完整表达式末尾销毁，但引用绑定、范围 for、展开语句、结构化绑定等七种语境例外；悬垂引用的规则全在这里
status: done
papers: P0135R1, P2718R0, P2748R5
related: conv.rval, basic.lval, dcl.init.ref, class.copy.elision, stmt.ranged, stmt.return, class.base.init, intro.object
tags: 临时对象, 生命周期延长, 悬垂引用, 复制消除
updated: 2026-10-17
---

临时对象是 C++ 中**悬垂引用**（dangling reference）的主要来源，也是 C++17 "保证复制消除"改写最深的地方。本节回答三个问题：

1. **什么时候创建临时对象？**（¶1–¶3）C++17 起，答案是"尽可能晚"：prvalue 本身不是对象，只有在需要一个对象时才**物化**（materialize）。
2. **什么时候销毁？**（¶4）默认在完整表达式（full-expression）求值的最后一步。
3. **有哪些例外？**（¶5–¶10）七种语境下临时对象活得更长（或在不同的时点销毁），其中最重要的是**引用绑定导致的生命周期延长**——以及它的诸多"不延长"的例外。

阅读前需要了解值类别（[[basic.lval]]）：prvalue 是"初始化一个对象的配方"，glvalue 是"一个对象的身份"。

## 临时对象的定义（¶1）

临时对象是在以下情形创建的对象：

- ¶1.1 prvalue 被转换为 xvalue 时——即**临时物化转换**（temporary materialization conversion，[[conv.rval]]）；
- ¶1.2 实现为了**传递或返回**某些合适类型的对象而需要时（见 ¶3）。

**就这两种**。C++17 之前，"创建临时对象"的场合多得多（每个类类型的 prvalue 都是一个临时对象，然后再"复制"到目标），复制消除只是一个**允许的**优化。C++17 起（[[P0135R1]]），prvalue 不再是对象：

```cpp run title="guaranteed-elision.cpp" ok
struct NonMovable {
    NonMovable(int) {}
    NonMovable(const NonMovable&) = delete;
    NonMovable(NonMovable&&) = delete;
};

NonMovable make() { return NonMovable(42); }   // C++17: OK —— prvalue 直接初始化返回对象

int main() {
    NonMovable a = make();                       // OK: 没有临时对象，make() 的 prvalue 直接初始化 a
    NonMovable b = NonMovable(NonMovable(1));    // OK: 嵌套的 prvalue 最终只初始化 b 一个对象
    (void)a; (void)b;
}   // C++14 中三处都是 error：需要可访问的复制/移动构造函数
```

¶1 第二句：即使临时对象的创建是**不求值的**（unevaluated，如 `sizeof` 的操作数），所有语义限制都必须如同创建并销毁了该对象一样被遵守——包括构造函数和析构函数的可访问性、是否被删除（注 1）。唯一例外：`decltype` 的操作数中的 prvalue 不引入临时对象（[[dcl.type.decltype]]）。

```cpp run title="unevaluated-temp.cpp" error
struct P { private: ~P(); };
P make();

using A = decltype(make());   // OK: decltype 的操作数不引入临时对象，不检查析构函数
auto n = sizeof(P{});         // error: 物化临时对象需要可访问的析构函数，即使不求值
```

## 物化尽可能推迟（¶2）

!!! std
    The materialization of a temporary object is generally delayed as long as possible in order to avoid creating unnecessary temporary objects.

    临时对象的物化通常被尽可能推迟，以避免创建不必要的临时对象。

注 2 列出了物化发生的场合（这是一份方便查阅的汇总，规范依据散布在各条款中）：

| 列表项 | 场合 | 例子 |
|---|---|---|
| ¶2.1 | 引用绑定到 prvalue | `const T& r = T{};`、`static_cast<T&&>(T{})` |
| ¶2.2 | 对类 prvalue 做某些成员访问 | `T{}.member`、`T{}.*pm` |
| ¶2.3 | 对类 prvalue 调用隐式对象成员函数 | `T{}.f()` |
| ¶2.4 | 对数组 prvalue 做数组到指针转换或下标 | `id<int[3]>{1,2,3}[i]` |
| ¶2.5 | 从花括号列表初始化 `std::initializer_list<T>` | `std::initializer_list<int> il = {1,2,3};`（后备数组） |
| ¶2.6 | 某些不求值操作数 | `sizeof(T{})`、`typeid(T{})` |
| ¶2.7 | 非 `void` prvalue 作为弃值表达式 | `T{};` 作为表达式语句 |

**不**物化的场合：用 prvalue 初始化同类型的对象（`T x = T{};`、`return T{};`、函数实参 `f(T{})` 初始化**值**形参）——prvalue 直接以目标对象为其**结果对象**（result object）。

标准例 1（加注）：

```cpp run title="materialize.cpp" ok
class X {
public:
    X(int) {}
    X(const X&) {}
    X& operator=(const X&) { return *this; }
    ~X() {}
};
class Y {
public:
    Y(int) {}
    Y(Y&&) {}
    ~Y() {}
};

X f(X x) { return x; }
Y g(Y y) { return y; }

int main() {
    X a(1);
    X b = f(X(2));   // X(2) 直接在 f 的形参中构造；f 的结果直接构造在 b 中
    Y c = g(Y(3));   // 同上
    a = f(a);        // f(a) 的结果需要物化成临时对象，才能绑定到 operator= 的 const X& 形参
}
```

## 为在寄存器中传参/返回而创建的临时对象（¶3）

当类型 `X` 的对象被传给或从一个潜在求值的函数调用中返回时，若 `X` 是

- ¶3.1 标量类型，或
- ¶3.2 类类型，至少有一个合格的（eligible）复制或移动构造函数、每个这样的构造函数都是**平凡的**，且析构函数是平凡的或被删除的，

那么实现**允许**创建临时对象来保存函数形参或返回对象：第一个临时对象从实参/返回值构造（¶3.3），后续每个从前一个初始化（¶3.4），最后形参或返回对象从最终的临时对象初始化（¶3.5）——对类类型均使用合格的平凡构造函数（即使它不可访问，或重载决议不会选它）。

注 3 道出动机：**允许在寄存器中传递和返回对象**。寄存器不是内存，没有地址；对象被放进寄存器、再写回被调用者的栈帧，就产生了"另一个对象"。对平凡可复制的类型，这种"复制"不可观察（没有用户代码运行），标准干脆把它合法化。

可观察的后果：**对象的地址在调用前后可能不同**。

```cpp run title="register-pass.cpp" unspecified
#include <cstdio>

struct Small { int a, b; };              // 平凡复制、平凡析构：可以放在寄存器中传递

const void* seen;

Small make() {
    Small s{1, 2};
    seen = &s;
    return s;                            // 返回对象可能经由寄存器"复制"
}

int main() {
    Small r = make();
    std::printf("%d\n", seen == &r);     // 未指定：常见实现（x86-64 SysV、AArch64）上为 0
}
```

!!! impl "ABI：\"对调用而言非平凡\""
    Itanium C++ ABI 把满足 ¶3.2 条件之外的类称为"对调用而言非平凡"（non-trivial for the purposes of calls）：这类对象**不能**放在寄存器里，而是由调用者在内存中创建，再传递其地址（"隐形引用"）。著名的例子是 `std::unique_ptr<T>`：它只有一个指针大小，却因为有非平凡析构函数，必须通过栈内存传递，比裸指针多一次内存往返。Clang 提供 `[[clang::trivial_abi]]` 属性让类在 ABI 意义上被当作平凡的。MSVC x64 的规则不同：它主要按大小（1、2、4、8 字节）以及是否为聚合等条件决定能否在寄存器中传递。

## 默认销毁时机（¶4）

!!! std
    Temporary objects are destroyed as the last step in evaluating the full-expression that (lexically) contains the point where they were created.

    临时对象在（词法上）包含其创建点的完整表达式求值的最后一步被销毁。

即使该求值以抛出异常结束也是如此。销毁的值计算和副作用只与完整表达式关联，而不与任何子表达式关联。

完整表达式（[[intro.execution]]）大致是"不是其他表达式一部分的表达式"——一条表达式语句、一个变量的初始化器、`if` 的条件等。所以"临时对象活到分号"是一个很好的近似：

```cpp run title="end-of-full-expr.cpp" ok
#include <string>
#include <cstdio>

std::string name() { return "temporary"; }

int main() {
    std::printf("%s\n", name().c_str());   // OK: 临时 string 活到整条语句结束

    const char* p = name().c_str();         // p 悬垂：临时 string 在这个分号处销毁
    (void)p;                                // 只要不解引用 p 就没有 UB
}
```

## 七种例外语境（¶5–¶10）

### 第一、二种：数组元素的默认实参（¶5）

1. 默认构造函数被调用来初始化**没有对应初始化器的数组元素**时；
2. 整个数组被复制时（lambda 按值捕获数组、隐式复制构造函数复制数组成员），复制构造函数被调用来复制一个元素时。

两种情形下，若构造函数有默认实参，每个默认实参中创建的临时对象在**构造下一个元素之前**销毁。否则一个 1000 元素的数组会在一个完整表达式里累积 1000 个临时对象。

```cpp run title="array-default-arg.cpp" ok
#include <cstdio>

struct Tmp { Tmp() { std::puts("Tmp()"); } ~Tmp() { std::puts("~Tmp()"); } };
struct E { E(const Tmp& = Tmp()) { std::puts("E()"); } };

int main() {
    E arr[2];   // 输出：Tmp() E() ~Tmp() Tmp() E() ~Tmp() —— 每个元素的临时对象在下一个元素构造前销毁
}
```

### 第三种：引用绑定（¶6）

这是最重要的一条。当引用绑定到临时对象时，**临时对象**（或者引用所绑定的**子对象**的完整临时对象）**持续到引用的生命周期结束**——前提是引用所绑定的 glvalue 是通过以下途径之一得到的：

| 列表项 | 途径 | 例子（均延长） |
|---|---|---|
| ¶6.1 | 临时物化转换 | `const T& r = T{};` |
| ¶6.2 | 括号 `( e )` | `const T& r = (T{});` |
| ¶6.3 | 对数组操作数下标 | `int&& r = id<int[3]>{1,2,3}[i];` |
| ¶6.4 | 用 `.` 做类成员访问，右侧是非引用类型的非静态数据成员或直接基类关系 | `int&& r = S{}.m;` |
| ¶6.5 | 用 `.*` 的成员指针操作，右侧是非引用类型的数据成员指针 | `int&& r = S{}.*pm;` |
| ¶6.6 | `const_cast`/`static_cast`/`dynamic_cast`/`reinterpret_cast`，不经用户定义转换，结果指向操作数所指对象、其完整对象或子对象 | `const int& r = static_cast<const int&>(0);` |
| ¶6.7 | 到引用类型、初始化器为花括号列表的函数式显式类型转换 | `using R = const T&; R{T{}}` |
| ¶6.8 | glvalue 条件表达式，第二或第三操作数是上述表达式之一 | `const T& r = c ? T{1} : T{2};` |
| ¶6.9 | glvalue 逗号表达式，右操作数是上述表达式之一 | `const T& r = (f(), T{});` |

这份清单是**递归**定义的（"其中 *expression* 是这些表达式之一"），它刻画的是一类"能**静态地**看出结果就是某个临时对象（或其子对象）"的表达式。在 [[stmt.return]] 和 [[class.base.init]] 中，这类表达式被称为**临时表达式**（temporary expression）。

```cpp run title="extension-yes.cpp" ok
#include <string>
#include <utility>

template<class T> using id = T;
struct S { int m; std::string s; };

int main(int argc, char**) {
    int i = 1;
    const std::string& a = std::string("abc");             // ¶6.1
    int&& b = id<int[3]>{1, 2, 3}[i];                      // ¶6.3：整个临时数组被延长
    std::string&& c = S{1, "x"}.s;                         // ¶6.4：整个 S 临时对象被延长
    const int& d = static_cast<const int&>(0);             // ¶6.6
    int&& e = argc > 1 ? id<int[3]>{1, 2, 3}[i] : static_cast<int&&>(0);
                                                           // ¶6.8：恰好一个临时对象被延长
    const int& f = (const int&)1;                          // 注 4：C 风格强转被解释为 static_cast 序列
    return a.size() + b + c.size() + d + e + f > 0 ? 0 : 1;   // 全部 OK
}
```

注 5：若临时对象有一个引用成员被另一个临时对象初始化，延长**递归地**作用于该成员的初始化器：

```cpp run title="extension-recursive.cpp" ok
struct S { const int& m; };

int main() {
    const S& s = S{1};   // S 临时对象和 int 临时对象都被延长到 s 的生命周期
    return s.m;          // OK: 1
}
```

#### 不在清单上 ⇒ 不延长

最常见的悬垂：经过**函数调用**（包括成员函数、运算符重载）返回的引用，不在 ¶6 的清单里。编译器不知道函数返回的引用指向哪里，因此不延长任何东西。

```cpp run title="dangling-call.cpp" ub
#include <algorithm>
#include <string>

struct Holder {
    std::string s{"hello"};
    const std::string& get() const { return s; }
};

int main() {
    const int& m = std::max(1, 2);            // 悬垂：临时 int 绑定到 max 的引用形参，¶6.10 → 活到分号
    const std::string& g = Holder{}.get();    // 悬垂：经由成员函数调用，不是 ¶6.4 的成员访问
    return m + static_cast<int>(g.size());    // UB: 两个引用都已悬垂
}
```

对比：`Holder{}.s` 是成员访问（¶6.4），**会**延长整个 `Holder`；`Holder{}.get()` 是函数调用，**不会**。这种"把 public 成员改成 getter 就悬垂了"的行为是 C++ 的著名陷阱。

#### 延长的三个例外（¶6.10–¶6.12）

即使引用绑定到临时对象，以下三种情形也**不**延长到引用的生命周期：

- ¶6.10 **函数调用中绑定到引用形参**的临时对象：持续到包含该调用的完整表达式结束。（形参的生命周期本来就比完整表达式短，延长到"形参的生命周期"没有意义，也无法实现。）
- ¶6.11 **用圆括号表达式列表初始化的类类型聚合体**中，绑定到引用元素的临时对象：持续到包含该表达式列表的完整表达式结束。{{c++20}}
- ¶6.12 **new-initializer** 中绑定到引用的临时对象：持续到包含该 new-initializer 的完整表达式结束。注 6：这可能导致悬垂引用。

```cpp run title="paren-aggregate.cpp" ub
struct A { const int& r; };

int main() {
    A b{42};     // 花括号：临时 int 被延长到 b 的生命周期（¶6.1 + 聚合初始化）
    A a(42);     // C++20 圆括号聚合初始化：¶6.11，临时 int 在分号处销毁，a.r 悬垂
    return a.r + b.r;   // UB: 读取 a.r
}
```

为什么圆括号与花括号不同？C++20 的圆括号聚合初始化（[[dcl.init]]）被设计为"像调用一个构造函数"——而构造函数的形参是 ¶6.10 的情形，临时对象不延长。保持这一类比，`A a(42)` 才能与"如果 `A` 有一个 `A(const int&)` 构造函数"行为一致。

```cpp run title="new-init.cpp" ub
#include <utility>

struct S { int mi; const std::pair<int, int>& mp; };

int main() {
    S a{1, {2, 3}};              // OK: 临时 pair 被延长到 a 的生命周期
    S* p = new S{1, {2, 3}};     // 临时 pair 在分号处销毁：p->mp 悬垂（¶6.12）
    int r = a.mp.first + p->mp.first;   // UB: 读取 p->mp
    delete p;
    return r;
}
```

#### 现已变成非良构的两种情形

过去 ¶6 的例外清单中还有两项，现在已改为**非良构**，由编译器强制诊断：

1. **构造函数的 mem-initializer 中把引用成员绑定到临时对象**：[[class.base.init#8]] 规定非良构（以前是"临时对象持续到构造函数退出"，必然悬垂）；默认成员初始化器中同样非良构（[[class.base.init#13]]），但仅当它被实际用于初始化时。
2. **return 语句把返回的引用绑定到临时对象**：[[stmt.return#6]] 规定非良构 {{c++26}}（[[P2748R5]]）。C++23 中这只是"临时对象不延长"，代码合法但必然返回悬垂引用。

```cpp run title="now-ill-formed.cpp" error
struct A {
    A() : v(42) {}            // error: mem-initializer 中引用成员绑定到临时对象
    const int& v;
};

const int& f() { return 42; }        // error（C++26）：返回的引用绑定到临时对象
auto&& g() { return 42; }            // error（C++26）
const double& h() {
    static int x = 42;
    return x;                        // error（C++26）：int → double 转换产生临时 double
}
```

本机 Clang 23 在 `-std=c++2c` 下对 `f`、`g`、`h` 报错（"returning reference to local temporary object"），在 `-std=c++23` 及更早模式下只给出 `-Wreturn-stack-address` 警告——与标准的版本变化一致。

!!! lawyer "P2748 只能抓住\"临时表达式\""
    [[stmt.return]] 的例子里还有：

    ```cpp
    auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
    auto&& f3() { return id(42); }   // OK，但几乎肯定是 bug
    ```

    `id(42)` 是函数调用，不是临时表达式，所以规则管不到——这与 ¶6 不延长函数调用结果的道理相同。编译器的 `-Wdangling` 类警告（基于 `[[clang::lifetimebound]]` 等注解）在这里比标准规则走得更远。

### 第四种：范围 for 的范围初始化器（¶7）{{c++23}}

若临时对象在范围 `for` 语句的 *for-range-initializer* 中创建，并且它原本会在 *for-range-initializer* 完整表达式结束时销毁，那么它持续到由 *for-range-initializer* 初始化的那个引用（即 [[stmt.ranged]] 中的 `__range`）的生命周期结束——也就是整个循环结束。

这条规则修复了一个困扰 C++ 十多年的陷阱。范围 `for` 被定义为 `auto&& __range = range-init;`，按 ¶6，只有当 `range-init` 本身就是临时表达式时临时对象才会被延长；只要中间经过一次函数调用，就悬垂：

```cpp run title="range-for.cpp" ok
#include <cstdio>
#include <vector>

struct T {
    std::vector<int> v{1, 2, 3};
    ~T() { std::puts("~T"); }
    const std::vector<int>& items() const { return v; }
};
T make() { return {}; }

int main() {
    for (int x : make().items())   // C++20：make() 的临时 T 在循环开始前销毁 → 悬垂 → UB
        std::printf("%d\n", x);    // C++23：临时 T 持续到循环结束 → OK
    std::puts("end");
}
```

本机 Clang 23 实测：`-std=c++20` 下先输出 `~T` 再进入循环（悬垂），`-std=c++23` 下先输出 1 2 3 再输出 `~T`。该修改来自 [[P2718R0]]。注意这是**语言版本相关**的行为：同一份代码在 C++20 模式下仍然是 UB。

### 第五、六种：展开语句（¶8–¶9）{{c++26}}

C++26 的**展开语句**（expansion statements，`template for`，[[stmt.expand]]）有类似的规则：

- ¶8 **枚举型**展开语句（`template for (auto x : {a, b, c})`）中，在 *expansion-init-list* 的某个元素 E 中创建的临时对象，若原本在 E 的完整表达式结束时销毁，则持续到由 E 初始化的 *for-range-declaration* 的生命周期结束。
- ¶9 **迭代型**或**解构型**展开语句中，在 *expansion-initializer* 中创建的临时对象，若原本在其结束时销毁，则持续到由它初始化的引用（如果有）的生命周期结束。

!!! warning "实现状态"
    本机 Clang 23 支持 `template for`，但在测试 `template for (int y : tup(T{5}))`（`tup` 以 `const T&` 接收参数并返回 `std::tuple`）时观察到 `T{5}` 在循环体执行**之前**就被销毁，与 ¶9 的字面要求不一致。这类代码在当前编译器上请勿依赖延长行为。

### 第七种：结构化绑定（¶10）{{c++26}}

在结构化绑定声明（[[dcl.struct.bind]]）中创建的临时对象：为**具有唯一名字的变量**（即元组式绑定中保存 `get<i>(e)` 结果的那些隐藏引用变量）的**初始化器**引入的临时对象，在**整个结构化绑定声明结束时**销毁，而不是在各自初始化器的完整表达式结束时。这让各个 `get<i>` 调用之间的临时对象可以安全共享，并给出了明确的销毁时点。

## 销毁顺序（¶11–¶12）

¶11 规定了三层顺序：

1. 设 x、y 各是一个**未被延长的临时对象或者函数形参**。若它们的生命周期在同一个完整表达式结束时终止，且 x 先于 y 初始化，则 **y 的销毁先于 x**——后构造者先销毁。
2. 多个被延长、且在同一时点结束的临时对象，按**构造完成的逆序**销毁。
3. 被延长的临时对象的销毁还要与同存储期的其他对象协调：比临时对象**先**创建的同存储期对象 obj1，要在临时对象**之后**销毁；**后**创建的 obj2，要在临时对象**之前**销毁。即：被延长的临时对象在销毁顺序上就像一个在其创建点定义的同存储期变量。

标准例 6（加注）：

```cpp run title="destruction-order.cpp" ok
#include <cstdio>

struct S {
    int id;
    S(int i = 0) : id(i) { std::printf("S(%d)\n", id); }
    friend S operator+(const S& a, const S& b) { return S(a.id + b.id); }
    ~S() { std::printf("~S(%d)\n", id); }
};

S obj1(1);
const S& cr = S(16) + S(23);   // T1=S(16)、T2=S(23) 绑定到 operator+ 的引用形参，分号处销毁（顺序与创建相反）
                               // T3=S(39) 绑定到 cr，延长到程序结束
S obj2(2);

int main() {}
// 程序结束时：~S(2)（obj2）→ ~S(39)（T3）→ ~S(1)（obj1）
```

T1 与 T2 谁先创建是**未指定**的（函数实参的求值顺序未指定，[[expr.call]]）；但无论哪个先创建，都后销毁。

## 实现视角

!!! impl "编译器如何实现生命周期延长"
    - 被延长的临时对象在实现上就是一个**隐藏的局部变量**（或对静态引用来说，一个隐藏的静态变量）：`const T& r = T{};` 大致等价于 `T __tmp{}; const T& r = __tmp;`。Itanium ABI 甚至为静态存储期引用所绑定的临时对象规定了修饰名（`_ZGR` 前缀，"reference temporary"）。
    - 正因为延长是在**编译期**按语法结构决定的，它不可能"穿过"函数调用：编译器在调用点看不到函数返回的引用指向哪个对象。这是 ¶6 清单只包含内置运算的根本原因。
    - Clang 的 `-Wdangling`、`-Wdangling-gsl`、`-Wreturn-stack-address` 以及 `[[clang::lifetimebound]]` 注解，GCC 的 `-Wdangling-reference`，都是在标准规则之外用启发式方法捕获悬垂引用的工具。本机 Clang 23 对上面 `A a(42);` 的例子就给出了 `-Wdangling` 警告。

## 历史与演进

!!! history "历史与演进"
    - **C++98/03**：临时对象由"创建类类型的右值"等多种场合产生；引用延长规则已存在，例外包括构造函数初始化列表中的引用成员（持续到构造函数退出）、函数调用的引用形参、return 语句（持续到函数退出）。new-initializer 的例外是后来补充的。
    - **C++11**：引入右值引用与 xvalue；延长规则同样适用于右值引用。
    - **C++17**：[[P0135R1]] "保证复制消除"——prvalue 不再是临时对象，引入**临时物化转换**；本节 ¶1 改写为现在的两种情形，新增 ¶2 的物化注释。
    - **C++17 前后（缺陷修复）**：mem-initializer 中把引用成员绑定到临时对象改为非良构（原来的"持续到构造函数退出"必然悬垂，毫无用处）。
    - **C++20**：圆括号聚合初始化引入 ¶6.11 的例外。
    - **C++23**：[[P2718R0]] 范围 `for` 初始化器中的临时对象延长到循环结束（¶7）。
    - **C++26**：[[P2748R5]] return 语句绑定引用到临时对象改为非良构；展开语句的两种新语境（¶8–¶9）；结构化绑定的临时对象销毁时点（¶10）。

## 陷阱

!!! pitfall "`std::string_view` / `std::span` 不是引用"
    `std::string_view sv = std::string("abc");` —— `sv` 是一个**对象**，不是引用，¶6 不适用。临时 `string` 在分号处销毁，`sv` 悬垂。生命周期延长**只对引用**有效。

!!! pitfall "`auto&&` 绑定成员函数的结果"
    `auto&& x = make().value();`（如 `std::optional<T>::value()` 返回 `T&&`）——经过成员函数调用，不延长，`x` 悬垂。改为 `auto x = make().value();`（按值接收）。

!!! pitfall "以为 `const T&` 形参能\"保存\"临时对象"
    `struct W { const std::string& s; W(const std::string& s) : s(s) {} };  W w(std::string("x"));` —— 临时 `string` 绑定到构造函数的引用形参（¶6.10），分号处销毁，`w.s` 悬垂。这不是 mem-initializer 绑定临时对象（`s(s)` 绑定的是形参，一个左值），所以编译器不报错。

!!! pitfall "范围 for 修复只在 C++23 模式下有效"
    依赖 ¶7 的代码在 `-std=c++20` 下编译仍然悬垂。库代码若需兼容旧标准，不应依赖它。

## 思考题

!!! question "思考题 1"
    以下哪些引用悬垂？

    ```cpp
    struct P { int x; int& rx() { return x; } };
    P make();
    const int& a = make().x;                  // (a)
    const int& b = make().rx();               // (b)
    const int& c = static_cast<P&&>(make()).x;   // (c)
    const int& d = true ? make().x : 0;       // (d)
    ```

<details markdown="1">
<summary>答案</summary>

(a) 不悬垂：¶6.4 成员访问，整个 `P` 临时对象被延长。

(b) 悬垂：成员函数调用的结果不在 ¶6 清单中。

(c) 不悬垂：`make()` 被物化（¶6.1），`static_cast<P&&>` 不经用户定义转换、结果指向同一对象（¶6.6），再做成员访问（¶6.4）。

(d) 要看条件表达式的值类别：第二操作数 `make().x` 是 xvalue `int`，第三操作数 `0` 是 prvalue `int`，二者值类别不同，结果是 **prvalue**（[[expr.cond]]）。于是 `make().x` 先被左值到右值转换读出值，`d` 绑定到对结果 prvalue 物化出来的**新**临时 `int`（¶6.1），这个新临时对象被延长；`make()` 的 `P` 临时对象在分号处销毁，但 `d` 并不引用它。不悬垂。（¶6.8 要求条件表达式是 glvalue，这里不适用，但也不需要它。）
</details>

!!! question "思考题 2"
    为什么 C++17 之后 `NonMovable x = NonMovable(1);` 合法，而 `NonMovable x = std::move(NonMovable(1));` 不合法？

<details markdown="1">
<summary>答案</summary>

前者：初始化器是同类型的 prvalue，直接以 `x` 为结果对象，不涉及任何构造函数之外的复制/移动。后者：`std::move` 接收 `T&&` 形参，实参 `NonMovable(1)` 必须**物化**成临时对象（¶2.1）才能绑定；`std::move` 返回 xvalue，用 xvalue 初始化 `x` 需要调用移动构造函数——而它被删除了。顺带一提，即使类型可移动，这样写也会使 RVO 失效、多一次移动。
</details>

!!! question "思考题 3"
    `for (auto& x : std::vector<std::string>{"a", "b"})` 在 C++20 中有悬垂吗？`for (char c : std::string("ab").substr(0))` 呢？

<details markdown="1">
<summary>答案</summary>

第一个：`__range` 直接绑定到 prvalue 物化的临时 `vector`（¶6.1），在任何标准下都被延长，没有悬垂。

第二个：`std::string("ab")` 是临时对象，`.substr(0)` 是成员函数调用，**按值**返回一个新的 `string` prvalue；`__range` 绑定到这个新的 prvalue，它被延长。原来的临时 `string("ab")` 在 C++20 中于初始化器末尾销毁——但循环只用到 `substr` 的结果，所以也没有悬垂。真正悬垂的是返回**引用**的情形，如 `for (char c : make().name())`（`name()` 返回 `const std::string&`），这在 C++20 中是 UB，C++23 中 OK。
</details>

## 小结

| 问题 | 规则 |
|---|---|
| 何时创建 | 物化（prvalue → xvalue）时；或为寄存器传参/返回（平凡可复制类型） |
| 何时不创建 | prvalue 初始化同类型对象（保证复制消除，C++17） |
| 默认何时销毁 | 完整表达式求值的最后一步，逆构造顺序 |
| 延长 | 引用直接（经 ¶6.1–¶6.9 的内置运算）绑定到临时对象或其子对象 |
| 不延长 | 经函数调用；绑定到函数引用形参（¶6.10）；圆括号聚合初始化（¶6.11）；new-initializer（¶6.12） |
| 非良构 | mem-initializer / 默认成员初始化器绑定临时对象；return 绑定临时对象（C++26） |
| 特殊语境 | 数组元素默认实参（¶5）；范围 for（C++23）；展开语句、结构化绑定（C++26） |
