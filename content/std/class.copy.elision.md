---
title: 复制/移动消除
summary: 允许的复制消除（NRVO、throw、协程形参、catch）——唯一可以改变可观察行为的"优化"；它与 C++17 起由 prvalue 语义保证的"不产生复制"是两回事；隐式移动何时发生；常量求值中禁止复制消除
status: done
papers: P0135R1, P1825R0, P2266R3
related: class.temporary, basic.lval, dcl.init, stmt.return, expr.prim.id.unqual, expr.throw, except.handle, dcl.fct.def.coroutine, class.copy.ctor, expr.const.const, topics/special-members-and-elision, topics/value-categories
tags: 复制消除, NRVO, RVO, 移动语义, 值类别
updated: 2026-10-17
---

几乎所有 C++ 程序员都听说过 RVO 和 NRVO，但"复制消除"这个词在 C++17 之后其实指**两种完全不同的东西**：

| | "保证的复制消除" | 允许的复制消除（本节） |
|---|---|---|
| 典型代码 | `return T(...);`、`T x = T(...);`、`T x = f();` | `T t; ...; return t;`（NRVO） |
| 本质 | **根本没有复制**：prvalue 直接初始化其结果对象 | **有一次复制/移动**，但实现可以省略它 |
| 是否强制 | 是（语言语义） | 否（实现自由） |
| 复制/移动构造函数 | 不需要存在 | 必须可用（可访问、未删除） |
| 规则所在 | [[basic.lval#5]]、[[dcl.init#15.6.1]]、[[class.temporary]] | 本节 [[class.copy.elision]] |
| 常量求值中 | 照常 | **禁止**消除 |

本节（[class.copy.elision]）只管右栏。C++17 的提案 [[P0135R1]] 把左栏从"复制消除"中剥离出去，变成了值类别语义的一部分；从那以后，"guaranteed copy elision"这个流行说法在标准里其实**并不存在**——标准中没有被消除的复制，只有从未发生的复制。

读本页前请先理解 prvalue 与**结果对象**（result object）的概念，见 [[basic.lval]] 与专题 [[topics/value-categories]]。

## 先说左栏：prvalue 不产生复制

C++17 起，prvalue 不是对象，而是"如何初始化一个对象"的描述；这个被初始化的对象叫它的**结果对象**（[[basic.lval#5]]）。当用同类型的 prvalue 初始化一个对象时，[[dcl.init#15.6.1]] 规定"直接用初始化器表达式初始化目标对象"——目标对象**就是**结果对象。

```cpp run title="no-copy-at-all.cpp" ok
struct NM {
    NM() {}
    NM(const NM&) = delete;   // 不可复制
    NM(NM&&) = delete;        // 也不可移动
};

NM make()  { return NM(); }   // OK（C++17 起）：返回值的结果对象由调用方提供
NM make2() { return {}; }     // OK

int main() {
    NM a = make();            // OK：a 就是 make() 中 NM() 的结果对象
    NM b = NM(NM(NM()));      // OK：一层层 prvalue，最终只构造一次（[dcl.init] 例 2 的同类）
    auto c = make2();         // OK
    (void)a; (void)b; (void)c;
}
```

用 `-std=c++14` 编译这段代码，除了 `make2` 中的 `return {};`（复制列表初始化直接初始化返回值，C++14 中也没有临时对象）之外，`make()`、`a`、`b`、`c` 每一处都会报"调用被删除的构造函数"：C++14 中这些地方语义上有临时对象和复制/移动，只是**允许**消除，因此构造函数必须可用。C++17 把它们变成"没有复制"之后，不可移动的类型（`std::mutex`、`std::atomic`、带 `const` 成员的类型、作用域守卫）终于可以从工厂函数中按值返回了。

左栏也有它的"例外"——此时实现**仍会**创建临时对象：

- **临时量实质化**：prvalue 被绑定到引用、被访问成员、作为弃值表达式等时，会实质化一个临时对象（[[class.temporary#2]]）。
- **平凡可复制类型的寄存器传递**：对于有可用的平凡复制/移动构造函数、且析构函数平凡或被删除的类型，实现**可以**为传参和返回创建额外的临时对象（[[class.temporary#3]]）。这就是小结构体能通过寄存器返回的法律依据——代价是对象的地址可能"变了"（见下文常量求值一节的例子）。

## 允许的复制消除（¶1）

### 什么是复制消除

¶1 在满足特定条件时，实现**被允许**省略"从同类型（忽略 cv 限定）的源对象创建一个类对象"——**即使**被选中的构造函数和/或析构函数有副作用。这时实现把被省略的初始化的源和目标视为**同一个对象的两种称呼**。

!!! std
    In such cases, the implementation treats the source and target of the omitted initialization as simply two different ways of referring to the same object.

    此时实现把被省略的初始化的源与目标，仅仅视为指代同一个对象的两种方式。

这是 C++ 中**极少数允许改变可观察行为的优化**之一。一般优化都受 as-if 规则约束（[[intro.abstract]]）：只要可观察行为不变，实现可以做任何事。复制消除则明确允许"复制构造函数里的 `printf` 不执行"。另一个类似的特例是 *new-expression* 可以省略对可替换分配函数的调用（[[expr.new]]）。

### 析构发生在什么时候

既然两个对象合二为一，就只剩一次析构。¶1 规定：

- 若被选中的构造函数的第一个形参是对该对象类型的**右值引用**（即本来是一次**移动**），合并后的对象在**目标**本应被销毁时销毁；
- 否则，在两个对象本应被销毁的时刻中**较晚**的那一个销毁。

注 1：因为只销毁一个对象、也只少构造一个对象，"每构造一个对象就销毁一个"的配平依然成立。

为什么移动时取"目标的时刻"？被移动的源对象之后通常处于"已被掏空"的状态，它的析构时刻没有意义；而目标对象才是程序继续使用的那个。

### 四种允许消除的场合

¶1 列出了四种场合（可以组合使用，以消除多次复制）：

**¶1.1 return 语句（NRVO）**：在返回类类型的函数中，`return` 的操作数是一个**非 volatile**、**自动存储期**对象 *o* 的**名字**（不能是函数形参，也不能是 *handler* 的 *exception-declaration* 引入的变量）时，可以把 *o* 直接构造在函数调用的结果对象中，省略对结果对象的复制初始化。

这就是俗称的 **NRVO**（named return value optimization）。注意限制条件：

- 必须是**名字**（*id-expression*，可以加括号），`return c ? x : y;`、`return std::move(x);`、`return p.a;` 都不是；
- 必须是**自动存储期**的**对象**——`static` 局部变量、引用、结构化绑定（它不是变量）都不行；
- **函数形参不行**：形参由调用方构造在调用方的栈帧中（Itanium ABI），被调用方无法把它"放到"返回值槽里；
- 被省略的是"从 *o* 到结果对象的复制初始化"，所以 *o* 的类型须与返回类型相同（忽略 cv）。

**¶1.2 throw-expression**：*throw-expression* 的操作数是非 volatile 自动存储期对象 *o* 的名字（同样排除形参和 handler 变量），且 *o* 所属的作用域**不包含**（若存在的话）最内层外围 *try-block* 的复合语句时，可以把 *o* 直接构造到异常对象中。

"不包含 try 块"这个条件的道理：如果 `throw x;` 发生在 `x` 的作用域内部的 `try` 块里，异常可能被这个 `try` 的 handler 捕获，之后代码还可能继续使用 `x`——此时 `x` 和异常对象必须是两个不同的对象。

**¶1.3 协程**：协程中对**协程形参的复制**（[[dcl.fct.def.coroutine]] 要求把形参复制到协程帧中）可以省略，对副本的引用替换为对原形参的引用——前提是除了副本的构造与析构之外，程序的含义不变。

**¶1.4 catch 子句**：*handler* 的 *exception-declaration* 声明了一个对象 *o* 时，若除了 *o* 的构造/析构之外程序的含义不变，可以把 *exception-declaration* 视为异常对象的别名，省略 *o* 的复制初始化。注 2：不可能从异常对象**移动**，因为它总是左值。

### 常量求值中禁止复制消除

¶1 最后：在要求常量表达式的语境中求值的表达式（[[expr.const.const]]）以及常量初始化（[[basic.start.static]]）中，**不允许**复制消除。注 3：同一个表达式在其他语境中求值时，可能进行复制消除。

为什么要禁止？因为常量求值的结果必须是**确定**的，而复制消除是**可选**的——如果允许，`constexpr` 变量的值就可能取决于编译器是否选择了消除。标准例 1 的后半部分恰好构造了这样一个"能观察到消除"的类型：

```cpp title="constexpr-elision.cpp" error
struct A {
    void* p;
    constexpr A() : p(this) {}   // 记录自己的地址
};

constexpr A g() {
    A loc;
    return loc;                  // 此处的复制可以被消除（NRVO）——但常量求值中不允许
}

constexpr A a;          // OK：a.p 指向 a
constexpr A b = g();    // error: 常量求值中没有消除，b 是 loc 的复制，b.p 指向已销毁的 loc（悬垂）

void h() {
    A c = g();          // OK：c.p 可能指向 c（消除了），也可能悬垂（没消除）
}
```

`b` 非良构的原因是 [[expr.const.const]] 不允许常量表达式的结果中含有指向已结束生命周期对象的指针。本机 Clang 给出的附注是"指向 `loc` 的指针不是常量表达式"。

`c` 那一行在运行时是什么结果？本机 Clang 上（无论 `-O0` 还是 `-O2`）`c.p == &c` 为假——`A` 是平凡可复制的 8 字节类型，按 [[class.temporary#3]] 经寄存器返回，`loc` 与 `c` 必然是不同的对象。但这是**实现的选择**，标准允许两种结果。

```cpp run title="constexpr-ok.cpp" ok
struct A {
    void* p;
    constexpr A() : p(this) {}
};

constexpr A mk() { return A(); }   // prvalue：没有复制，不涉及"消除"
constexpr A c = mk();
static_assert(c.p == &c);          // OK：c 就是 A() 的结果对象

int main() {}
```

对比之下，`return A();` 走的是左栏：根本没有复制，所以常量求值中 `c.p` 确定地指向 `c`。

## 例子：NRVO 与隐式移动（¶2–¶3）

### 标准例 1：NRVO 的效果（¶2）

```cpp run title="thing.cpp" ok
#include <cstdio>

class Thing {
public:
    Thing()             { std::puts("Thing()"); }
    ~Thing()            { std::puts("~Thing()"); }
    Thing(const Thing&) { std::puts("Thing(const Thing&)"); }
};

Thing f() {
    Thing t;
    return t;     // 允许消除：t 可以直接构造为 t2
}

Thing t2 = f();   // 结果对象是非局部对象 t2

int main() { std::puts("main"); }
// 消除时输出：Thing() / main / ~Thing()（t2 在程序退出时销毁）
```

标准的解说：消除使 `t` 的构造可以被看作直接初始化 `t2`，该对象的销毁发生在程序退出时。给 `Thing` 加上移动构造函数效果相同，只是被消除的变成了从 `t` 到 `t2` 的**移动**构造。

### 标准例 2：隐式移动（¶3）

如果实现**没有**消除 `return t;` 的复制，会用什么构造函数？答案是：**先当作右值**。C++23 起，规则是 [[expr.prim.id.unqual#15]] 的 **move-eligible** 表达式：

- **可隐式移动的实体**（implicitly movable entity）：自动存储期的变量，且是非 volatile 对象，或者是对非 volatile 对象类型的右值引用；
- *id-expression* 是**move-eligible** 的，如果它指代可隐式移动的实体，是 `return`/`co_return`/*throw-expression* 的（可加括号的）操作数，且实体声明与表达式之间只隔着块作用域（对 *throw-expression* 还要求不是 *try-block* 的块作用域）；
- move-eligible 的表达式是 **xvalue**（[[expr.prim.id.unqual#12]]）。

于是重载决议自然会优先选择移动构造函数。标准例 2：

```cpp title="implicit-move.cpp" error
class Thing {
public:
    Thing();
    ~Thing();
    Thing(Thing&&);
private:
    Thing(const Thing&);
};

Thing f(bool b) {
    Thing t;
    if (b)
        throw t;          // OK：使用（或消除）Thing(Thing&&) 来抛出 t
    return t;             // OK：使用（或消除）Thing(Thing&&) 来返回 t
}

Thing t2 = f(false);      // OK：没有额外的复制/移动，t2 由 f 的调用构造

struct Weird {
    Weird();
    Weird(Weird&);
};

Weird g(bool b) {
    static Weird w1;
    Weird w2;
    if (b)
        return w1;        // OK：w1 是静态的，不是可隐式移动实体；左值，用 Weird(Weird&)
    else
        return w2;        // error: w2 在这里是 xvalue，Weird(Weird&) 绑定不了
}

int& h(bool b, int i) {
    static int s;
    if (b)
        return s;         // OK
    else
        return i;         // error: i 是 xvalue，int& 不能绑定
}

decltype(auto) h2(Thing t) {
    return t;             // OK：t 是 xvalue，但 decltype(t) 是 Thing，返回类型 Thing
}

decltype(auto) h3(Thing t) {
    return (t);           // OK：(t) 是 xvalue，decltype((t)) 是 Thing&&，返回类型 Thing&&
}
```

几个值得逐条体会的点：

- `throw t;`：`t` 的作用域不包含 *try-block*，满足 move-eligible，所以使用移动构造函数——即使复制构造函数是 `private` 的也没关系。
- `Weird` 的 `return w2;` 是 C++23 [[P2266R3]] 带来的**破坏性变化**：C++20 的规则是"先当作右值做一次重载决议，失败则当作左值再来一次"，`Weird(Weird&)` 在第二轮能匹配；C++23 起表达式直接就是 xvalue，没有第二轮。本机 Clang 在 `-std=c++20` 下接受、在 `-std=c++23` 及以上拒绝。
- `int& h(..., int i) { return i; }` 返回对形参的引用——必然悬垂。C++23 起它直接非良构，这正是 P2266 想要的副作用；C++20 下只是警告。
- `h2`/`h3`：`decltype(auto)` 对 `t` 与 `(t)` 的推导不同（[[dcl.type.decltype]]）。`h3` 返回的 `Thing&&` 指向形参 `t`，同样会悬垂——良构，但别这么写。

注意隐式移动与复制消除是**两层**机制：隐式移动决定"如果要复制，用哪个构造函数"；复制消除决定"这次复制/移动能否省略"。NRVO 失败时，你得到的是一次**移动**而不是复制——前提是表达式是 move-eligible 的。

### 标准例 3：throw 与 try 块（¶4）

```cpp title="throw-scope.cpp" error
template<class T> void g(const T&);

template<class T> void f() {
    T x;
    try {
        T y;
        try { g(x); }
        catch (...) {
            if (/*...*/ true)
                throw x;   // 不移动：x 的作用域包含外层 try 块的复合语句
            throw y;       // 移动：y 的作用域（外层 try 的复合语句）不包含内层 try 块……
        }
        g(y);
    } catch (...) {
        g(x);
        g(y);              // error: y 不在作用域内
    }
}
```

对 `throw x;`：从 `x` 的声明到 `throw` 之间经过了外层 `try` 块的块作用域，按 [[expr.prim.id.unqual#15.3]] 不是 move-eligible，所以复制。这符合直觉：异常被外层 handler 捕获后，`g(x)` 还要用 `x`。对 `throw y;`：`y` 声明在外层 `try` 块内，中间只隔着 handler 的块作用域（不是 *try-block* 的块作用域），所以移动——`y` 在异常离开外层 `try` 块后就销毁了，偷走它的资源无妨。

## 观察：编译器实际做了什么

用一个打印所有特殊成员函数的类型，就能清楚地看到两栏的区别：

```cpp run title="observe.cpp" ok
#include <cstdio>

struct T {
    T()              { std::puts("  T()"); }
    T(const T&)      { std::puts("  T(const T&)"); }
    T(T&&) noexcept  { std::puts("  T(T&&)"); }
    ~T()             { std::puts("  ~T()"); }
};

T make()        { return T(); }                         // prvalue：没有复制
T nrvo()        { T t; return t; }                      // NRVO：允许消除
T two(bool b)   { T x, y; if (b) return x; return y; }  // 两个候选：通常无法 NRVO
T param(T p)    { return p; }                           // 形参：不能消除，只能隐式移动

int main() {
    std::puts("make:");  { T a = make(); }
    std::puts("nrvo:");  { T b = nrvo(); }
    std::puts("two:");   { T c = two(true); }
    std::puts("param:"); { T d = param(T()); }
}
```

本机 Clang 23（`-O0`）在三种设置下的特殊成员调用次数（不含析构）：

| 函数 | C++26，默认 | C++26，`-fno-elide-constructors` | C++14，`-fno-elide-constructors` |
|---|---|---|---|
| `make()` | `T()` | `T()` | `T()` + 2 次 `T(T&&)` |
| `nrvo()` | `T()` | `T()` + 1 次 `T(T&&)` | `T()` + 2 次 `T(T&&)` |
| `two(true)` | 2 次 `T()` + 1 次 `T(T&&)` | 同左 | 2 次 `T()` + 2 次 `T(T&&)` |
| `param(T())` | `T()` + 1 次 `T(T&&)` | 同左 | `T()` + 3 次 `T(T&&)` |

读这张表：

- **`-fno-elide-constructors`**（GCC 与 Clang 都支持）关闭的是**允许的**消除。在 C++17 及以后的模式下，`make()` 一行不受影响——那里本来就没有可以"关闭"的复制；只有 `nrvo()` 多出一次移动。在 C++14 模式下，所有临时对象都"现形"了：`make()` 中有"`T()` 临时量 → 返回值"、"返回值 → `a`"两次移动。
- **`two`**：两个不同的局部变量都可能被返回，编译器无法事先决定把哪一个构造在返回值槽里，NRVO 失败，退化为隐式移动。
- **`param`**：形参永远不能被 NRVO（¶1.1 明文排除），但会隐式移动。
- 即使在默认设置下 Clang 也在 `-O0` 时做 NRVO：GCC 与 Clang 都把 NRVO 视为前端的语义选择，而不是后端优化。MSVC 的 NRVO 策略历来较为保守，与优化选项相关。

### throw 与 catch：允许但通常不做

```cpp run title="throw-catch.cpp" ok
#include <cstdio>

struct T {
    T()              { std::puts("  T()"); }
    T(const T&)      { std::puts("  T(const T&)"); }
    T(T&&) noexcept  { std::puts("  T(T&&)"); }
    ~T()             { std::puts("  ~T()"); }
};

void f1() { T t; throw t; }

int main() {
    try { f1(); } catch (T e) { std::puts("  in handler"); }
    // 本机 Clang：T() / T(T&&) / ~T() / T(const T&) / in handler / ~T() / ~T()
}
```

¶1.2 与 ¶1.4 都**允许**消除，但本机 Clang 两者都没有做：`throw t;` 把 `t` 隐式**移动**到异常对象中（异常对象由 `__cxa_allocate_exception` 在堆上另行分配，和栈上的 `t` 不可能是同一块存储）；`catch (T e)` 从异常对象**复制**出 `e`（异常对象是左值，注 2）。实践建议仍然是"按值抛出、按 `const&` 捕获"。

## 实现视角

!!! impl "返回值槽（return slot）"
    在 Itanium ABI（以及 MSVC ABI）中，返回**非平凡**类类型的函数会接收一个隐藏参数：调用方准备好的**结果对象的地址**（AArch64 上通过 `x8` 传递，x86-64 SysV 上通过 `rdi` 并在 `rax` 中返回）。于是：

    - `return T(...);`：被调用方直接在这个地址上构造——这就是"prvalue 的结果对象由上下文提供"在机器层面的样子；
    - NRVO：编译器把局部变量 `t` **分配在**这个地址上，而不是自己的栈帧里，`return t;` 就什么都不用做；
    - `two(bool)`：`x` 和 `y` 不能同时住在同一个地址上，所以失败。

    对于平凡可复制、足够小的类型，ABI 规定通过寄存器返回，此时根本没有"结果对象的地址"可传，结果对象必然是调用方另一个对象——这是 [[class.temporary#3]] 允许额外临时对象的原因。

!!! impl "诊断"
    - `-Wpessimizing-move`（Clang，GCC 也有同名警告）：`return std::move(local);` 阻止了 NRVO；
    - `-Wredundant-move`（Clang 与 GCC）：在已经会隐式移动的地方多写了 `std::move`，如 `T d(T p) { return std::move(p); }`。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：已允许 RVO 与 NRVO 式的复制省略（"即使有副作用"），以及 throw/catch 中的省略。被省略的复制所需的复制构造函数仍须可访问。
    - **C++11**：引入移动语义。可以消除复制的 `return`/`throw` 场合，同时规定先把操作数当作右值做重载决议（隐式移动的雏形）。
    - **C++14**：[[CWG1579]] 放宽隐式移动：返回表达式的类型与函数返回类型不同（例如返回 `unique_ptr<Derived>` 局部变量、返回类型是 `unique_ptr<Base>`）时也会尝试移动。
    - **C++17**：[[P0135R1]] 引入 prvalue 新语义，"保证的复制消除"从本节剥离；本节只剩"允许的"复制消除。协程（C++20）后来又加入了形参复制的消除。
    - **C++20**：[[P1825R0]] 进一步扩大隐式移动：右值引用类型的局部变量也会隐式移动，并取消"所选构造函数的第一个形参必须是右值引用"的限制。
    - **C++23**：[[P2266R3]]（"更简单的隐式移动"）把 move-eligible 的 *id-expression* 直接定为 xvalue，取消"两轮重载决议"；返回对局部变量/形参的左值引用因此变为非良构。
    - 常量求值中禁止复制消除的规定（¶1 末）为了让常量求值的结果确定而加入，与 `constexpr` 能力的扩大同步。

## 陷阱

!!! pitfall "`return std::move(local);`"
    `std::move(local)` 不是名字，¶1.1 不适用，NRVO 被阻止；结果是一次本可以避免的移动。直接写 `return local;`——隐式移动会兜底。

!!! pitfall "`return cond ? a : b;`"
    条件表达式不是 *id-expression*：既不能 NRVO，也**不会隐式移动**（它是左值），结果是一次**复制**。改写为 `if (cond) return a; return b;`，至少能保证移动。

!!! pitfall "返回成员、结构化绑定、*this"
    `return p.a;`、`auto [a, b] = ...; return a;`、`return *this;` 都不满足 move-eligible：成员访问不是对变量的命名；结构化绑定不是变量。都会复制。需要移动时显式 `std::move`。

!!! pitfall "依赖复制构造函数的副作用"
    复制构造函数里计数、打日志、注册对象——NRVO 发生与否取决于编译器和代码结构，这些副作用不可靠。复制构造函数应该只做"复制"。

!!! pitfall "以为 NRVO 发生时就不需要移动/复制构造函数"
    NRVO 是允许的而不是保证的，`NM bad() { NM n; return n; }` 对不可移动类型依然非良构，哪怕实际上一定会被消除。只有返回 prvalue 才能摆脱对构造函数的要求。

## 思考题

!!! question "思考题 1"
    下面三个函数中，哪些可能发生 NRVO？如果都不发生，各会调用什么构造函数？（`T` 同 `observe.cpp`）

    ```cpp
    T a()            { T t; return (t); }
    T b()            { static T t; return t; }
    T c(T&& r)       { return r; }
    ```

<details markdown="1">
<summary>答案</summary>

- `a`：`(t)` 是加了括号的名字；¶1.1 说"*expression* 是对象的名字"，而括号表达式被普遍理解为满足这一条件（[[expr.prim.paren]] 规定其与内部表达式完全相同），Clang 与 GCC 都会做 NRVO；即使不做，`(t)` 也是 move-eligible 的（[[expr.prim.id.unqual#15.2]] 明说"possibly parenthesized"），会移动。
- `b`：静态存储期，不能 NRVO，不是可隐式移动实体——**复制**。
- `c`：`r` 是右值引用类型的自动变量，是可隐式移动实体（C++20 起），`r` 是 xvalue，**移动**；它不是"对象"而是引用，不能 NRVO。
</details>

!!! question "思考题 2"
    `T x = T(T(T()));` 在 C++14 和 C++17 中分别至多/至少调用几次构造函数？为什么 C++17 中 `T` 的复制和移动构造函数都可以被删除？

<details markdown="1">
<summary>答案</summary>

C++14：语义上有 1 次默认构造 + 3 次移动，后者都可以被消除，所以实际可能是 1 到 4 次；移动构造函数必须可用。C++17：只有 1 次默认构造——`T()` 是 prvalue，`T(prvalue)` 按 [[dcl.init#15.6.1]] 仍然是同一个 prvalue，最终 `x` 就是最内层 `T()` 的结果对象。没有任何复制/移动"发生过"，所以也不需要它们存在。上文 `observe.cpp` 系列实验中，Clang 在 `-std=c++14 -fno-elide-constructors` 下确实打印出 3 次 `T(T&&)`。
</details>

!!! question "思考题 3"
    为什么 ¶1 要求 NRVO 的源对象"不能是函数形参"，而 C++20 起形参却可以被隐式移动？

<details markdown="1">
<summary>答案</summary>

NRVO 的实现是让局部变量直接住在结果对象的存储里。形参的存储由**调用方**在调用之前就分配并初始化好了（Itanium ABI 中非平凡形参是调用方栈帧里的临时对象），被调用方无法让它与调用方提供的返回值槽重合。隐式移动则只是改变重载决议的结果，对存储位置没有要求；而形参在函数返回后马上销毁，移走它的资源是安全的。
</details>

## 小结

- 本节只规定**允许的**复制消除：`return` 局部对象（NRVO）、`throw` 局部对象、协程形参复制、`catch` 按值捕获。实现可以做也可以不做，相应的构造函数必须可用。
- 消除时源与目标是同一个对象；移动时在目标的时刻销毁，否则取较晚的时刻。
- 常量求值与常量初始化中**禁止**消除，保证结果确定。
- "保证的复制消除"不在本节：它是 prvalue 语义（[[basic.lval]]、[[dcl.init]]），根本没有复制，因此不受 `-fno-elide-constructors` 影响，也不需要复制/移动构造函数。
- 隐式移动（[[expr.prim.id.unqual#15]]）是 NRVO 失败时的兜底：move-eligible 的名字是 xvalue。不要写 `return std::move(local);`。
