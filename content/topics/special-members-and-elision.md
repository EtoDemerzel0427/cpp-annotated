---
title: 对象的诞生与消亡
summary: 一个类对象从构造到析构的完整故事：特殊成员函数何时被隐式声明（总表）、何时发生复制/移动、何时根本不发生；Rule of 0/3/5；noexcept 移动与 std::vector 扩容；平凡可复制与 memcpy；最后逐行追踪一段打印所有特殊成员的程序
status: draft
order: 60
since: c++11
papers: P0135R1, P2266R3
related: special, class.ctor, class.copy.ctor, class.copy.assign, class.dtor, class.base.init, class.copy.elision, class.temporary, class.prop, basic.types.trivial, depr.impldec, expr.call, topics/value-categories
tags: 特殊成员函数, 复制消除, 移动语义, Rule of five, 平凡可复制
updated: 2026-10-17
---

C++ 的值语义建立在六个**特殊成员函数**之上：默认构造函数、复制构造函数、移动构造函数、复制赋值运算符、移动赋值运算符、析构函数（[[special]]）。它们的规则散落在第 11 章的十几个条款里：什么时候由编译器声明（[[class.default.ctor]]、[[class.copy.ctor]]、[[class.copy.assign]]、[[class.dtor]]），什么时候被调用、按什么顺序初始化子对象（[[class.base.init]]），什么时候**不**被调用（[[class.copy.elision]]、[[dcl.init]]、[[class.temporary]]）。本专题把这些串成一条完整的时间线，并给出可以直接用于日常编码的结论。

## 一、编译器替你声明什么：总表

规则的出处：

- 默认构造函数：没有任何用户声明的构造函数（或构造函数模板）时隐式声明（[[class.default.ctor#1]]）；
- 复制构造函数：没有用户声明的复制构造函数时隐式声明；若类声明了移动构造或移动赋值，隐式的复制构造被定义为**删除**；有用户声明的复制赋值或析构函数时，隐式定义为预置是**弃用**的（[[class.copy.ctor#6]]、[[depr.impldec]]）；
- 移动构造函数：**仅当**没有用户声明的复制构造、复制赋值、移动赋值、析构函数时才隐式声明（[[class.copy.ctor#8]]）；
- 复制赋值、移动赋值：与上面两条对称（[[class.copy.assign#2]]、[[class.copy.assign#4]]）；
- 析构函数：没有用户声明的预期析构函数时隐式声明（[[class.dtor]]）。

于是有了这张表（"用户声明"包括 `= default` 和 `= delete`）：

| 用户声明了 ↓ / 编译器提供 → | 默认构造 | 析构 | 复制构造 | 复制赋值 | 移动构造 | 移动赋值 |
|---|---|---|---|---|---|---|
| 什么都没有 | 预置 | 预置 | 预置 | 预置 | 预置 | 预置 |
| 任意构造函数 | **不声明** | 预置 | 预置 | 预置 | 预置 | 预置 |
| 默认构造 | 用户 | 预置 | 预置 | 预置 | 预置 | 预置 |
| 析构函数 | 预置 | 用户 | 预置（弃用） | 预置（弃用） | **不声明** | **不声明** |
| 复制构造 | **不声明** | 预置 | 用户 | 预置（弃用） | **不声明** | **不声明** |
| 复制赋值 | 预置 | 预置 | 预置（弃用） | 用户 | **不声明** | **不声明** |
| 移动构造 | **不声明** | 预置 | **删除** | **删除** | 用户 | **不声明** |
| 移动赋值 | 预置 | 预置 | **删除** | **删除** | **不声明** | 用户 |

读这张表要注意两种"没有"的区别：

- **不声明**（not declared）：这个函数根本不存在，重载决议看不到它。例如声明了析构函数的类没有移动构造函数，于是 `T b(std::move(a));` 会**退而选择复制构造函数**（`const T&` 能绑定右值）——代码照常编译，只是悄悄变成了复制。
- **删除**（deleted）：函数存在，参与重载决议，但选中它就是错误。声明了移动操作的类，复制构造被定义为删除，`T b = a;` 直接编译失败。

另一个容易忽视的点：表中的"预置"只是**声明**为预置；它还可能被**定义为删除**——比如有一个不可复制的成员时，隐式复制构造函数是删除的（[[class.copy.ctor#10]]）。有一个例外值得记住：被定义为删除的**预置移动**操作会被排除出候选集（[[over.match.funcs#9]]），这样移动"失败"时会回退到复制，而不是报错。

```cpp run title="silent-copy.cpp" ok
#include <cstdio>
#include <utility>

struct Logged {
    Logged() = default;
    Logged(const Logged&) { std::puts("copy"); }
    Logged(Logged&&) noexcept { std::puts("move"); }
};

struct WithDtor {
    Logged l;
    ~WithDtor() {}            // 用户声明了析构函数：移动构造不再隐式声明
};

struct Plain {
    Logged l;                 // 什么都没声明：移动构造是预置的
};

int main() {
    WithDtor a;
    WithDtor b(std::move(a)); // copy —— 没有移动构造，选中了隐式的复制构造
    Plain c;
    Plain d(std::move(c));    // move
}
```

这就是为什么"只是加了一个空析构函数"会让一个类的性能悄悄变差。

## 二、Rule of 0 / 3 / 5

上表直接导出三条经验法则：

- **Rule of 0**：如果类只是组合了"自己管理好自己"的成员（`std::string`、`std::vector`、`std::unique_ptr`……），**一个特殊成员都不要写**。编译器生成的全部六个都做正确的事（逐成员操作），并且移动是 `noexcept` 的（只要成员的是）。
- **Rule of 3**（C++98）：如果你需要自定义析构函数、复制构造、复制赋值中的**任何一个**（通常因为手动管理资源），那么三个都需要自定义。
- **Rule of 5**（C++11）：在 3 的基础上加上移动构造与移动赋值。因为按上表，声明了前三者中的任何一个，移动操作就不再隐式声明；不显式提供，就只能复制。

一个常见的折中写法是在需要"析构函数是虚的"时：

```cpp run title="rule-of-5-defaults.cpp" ok
#include <type_traits>

struct Base {
    virtual ~Base() = default;               // 用户声明析构函数 → 移动不再隐式声明
    Base() = default;
    Base(const Base&) = default;             // 所以把五个都显式预置
    Base& operator=(const Base&) = default;
    Base(Base&&) = default;
    Base& operator=(Base&&) = default;
};

static_assert(std::is_nothrow_move_constructible_v<Base>);
int main() {}
```

（多态基类通常还应考虑禁止复制以避免切片，这是设计问题，不是语言规则。）

## 三、什么时候复制、什么时候移动、什么时候什么都不发生

给定"用表达式 `e` 初始化一个 `T` 类型的对象"，决定发生什么的是 `e` 的**值类别**（[[basic.lval]]）：

| `e` 是 | 例子 | 结果 | 依据 |
|---|---|---|---|
| `T` 类型的 **prvalue** | `T()`、`f()`（返回 `T`）、`T{1, 2}` | **什么都不发生**：目标就是 `e` 的结果对象 | [[dcl.init#15.6.1]]、[[basic.lval#5]] |
| `T` 类型的 **xvalue** | `std::move(a)`、`return local;`（move-eligible） | 移动构造（没有则复制） | 重载决议 |
| `T` 类型的 **lvalue** | `a`、`*p`、`arr[0]` | 复制构造 | 重载决议 |
| 其他类型 | `T x = 42;` | 转换构造函数 / 转换函数，结果是 prvalue，然后同第一行 | [[dcl.init]] |

在此之上，有四个场合**允许**实现省略一次复制/移动（[[class.copy.elision]]）：`return` 局部对象（NRVO）、`throw` 局部对象、协程形参的复制、`catch` 按值捕获。它们是可选的；实践中 GCC/Clang 可靠地做 NRVO（单一返回变量时），通常不做 `throw`/`catch` 的消除。

再加上两条"兜底"规则：

- `return local;`、`throw local;` 中的名字是 **move-eligible** 的 xvalue（C++23，[[P2266R3]]），NRVO 不发生时也是移动而非复制（[[expr.prim.id.unqual#15]]）；
- 按值传参时，实参是 prvalue 则形参就是它的结果对象，没有复制；实参是 lvalue 则复制。

| 场景 | 典型开销（C++17 起，GCC/Clang） |
|---|---|
| `T x = T(args);` / `T x = make();`（`make` 返回 prvalue） | 1 次构造 |
| `T make() { T t; ...; return t; }` | 1 次构造（NRVO）；NRVO 失败时 +1 次移动 |
| `T f(T p) { return p; }` | 形参不能 NRVO：+1 次移动 |
| `return cond ? a : b;` | +1 次**复制**（不是 move-eligible） |
| `return std::move(t);` | +1 次移动（阻止了 NRVO） |
| `f(T(args))`（按值形参） | 1 次构造，形参就是结果对象 |
| `f(a)`（按值形参，`a` 是左值） | +1 次复制 |
| `throw t;` / `catch (T e)` | 通常 +1 次移动 / +1 次复制 |

## 四、`noexcept` 移动与 `std::vector` 扩容

`std::vector::push_back` 在扩容时需要把旧元素搬到新内存。标准要求：在末尾插入单个元素时如果抛出异常，若 `T` 是 *Cpp17CopyInsertable* 或 `is_nothrow_move_constructible_v<T>` 为真，则**没有任何效果**（强异常保证，[[vector.modifiers#2]]）。

这给实现出了一道题：如果用移动构造函数搬运元素，而移动到一半抛出了异常，旧内存里的元素已经被"掏空"了，无法回滚。所以实现的策略是：**只有当移动构造函数是 `noexcept` 的（或者类型不可复制）时才移动，否则复制**（标准库用 `std::move_if_noexcept` 表达这个选择）。

```cpp run title="vector-growth.cpp" ok
#include <cstdio>
#include <vector>

template<bool NoExcept>
struct T {
    int id;
    T(int i) : id(i) {}
    T(const T& o) : id(o.id)                 { std::printf("copy%d ", id); }
    T(T&& o) noexcept(NoExcept) : id(o.id)   { std::printf("move%d ", id); }
};

int main() {
    {
        std::vector<T<false>> v;
        v.reserve(2); v.emplace_back(1); v.emplace_back(2);
        std::printf("扩容（移动可能抛出）: ");
        v.emplace_back(3);     // copy1 copy2
        std::puts("");
    }
    {
        std::vector<T<true>> v;
        v.reserve(2); v.emplace_back(1); v.emplace_back(2);
        std::printf("扩容（noexcept 移动）: ");
        v.emplace_back(3);     // move1 move2
        std::puts("");
    }
}
```

结论：**移动构造函数和移动赋值运算符几乎总应该是 `noexcept` 的**。隐式生成或 `= default` 的移动操作，其异常说明由成员推导（[[except.spec]]），只要成员的移动不抛出就自动是 `noexcept`——这又是 Rule of 0 的一个好处。

## 五、平凡可复制与 `memcpy`

有一类类型可以绕过特殊成员函数，直接按字节复制：**平凡可复制**（trivially copyable）类型。按 [[class.prop#1]]，一个类是平凡可复制的，当且仅当：

- 至少有一个**合格的**（eligible，即未删除且约束满足的，[[special]]）复制/移动构造函数或复制/移动赋值运算符；
- 每个合格的复制/移动构造函数与复制/移动赋值运算符都是**平凡**的；
- 有一个平凡的、未删除的析构函数。

"平凡"大致意味着"编译器生成的、而且不需要做任何额外的事"：不是用户提供的、类没有虚函数和虚基类、所有子对象对应的操作也平凡（[[class.copy.ctor#12]]）。注意 `= default` 在首次声明时**不是**用户提供的，因此**不破坏**平凡性；而写一个空的 `~T() {}` 会。

对平凡可复制类型 `T`，[[basic.types.trivial#3]] 与 [[basic.types.trivial#4]] 保证：把对象的底层字节复制到 `char`/`unsigned char`/`std::byte` 数组再复制回去，或者从一个对象复制到另一个（非潜在重叠的）对象，目标对象获得源对象的值。这就是 `std::memcpy` 复制结构体、`std::bit_cast`、二进制序列化的合法性来源。

```cpp run title="trivially-copyable.cpp" ok
#include <cstring>
#include <string>
#include <type_traits>

struct P  { int x; double y; };
struct P2 { int x; P2() = default; P2(const P2&) = default; ~P2() = default; };  // 仍平凡
struct P3 { int x; ~P3() {} };                     // 用户提供的析构：不再平凡可复制
struct P4 { std::string s; };                      // 成员不平凡：不再平凡可复制
struct P5 { int x; virtual void f() {} };          // 虚函数：不再平凡可复制

static_assert(std::is_trivially_copyable_v<P>);
static_assert(std::is_trivially_copyable_v<P2>);
static_assert(!std::is_trivially_copyable_v<P3>);
static_assert(!std::is_trivially_copyable_v<P4>);
static_assert(!std::is_trivially_copyable_v<P5>);

int main() {
    P a{1, 2.0}, b{};
    std::memcpy(&b, &a, sizeof(P));   // OK：b 获得 a 的值
    return b.x == 1 ? 0 : 1;
}
```

平凡可复制还有一个 ABI 层面的后果：这类小对象可以通过**寄存器**传参和返回（[[class.temporary#3]] 允许为此创建额外的临时对象）。所以一个"空的用户析构函数"不仅阻止了 `memcpy`，还可能让按值传递 `std::pair<int,int>` 大小的对象从寄存器传递变成经内存传递。

## 六、构造与析构的顺序

把 [[class.base.init#15]] 和 [[class.dtor]] 放在一起：

1. **构造**：虚基类（仅最派生类，深度优先、从左到右）→ 直接基类（声明顺序）→ 非静态数据成员（声明顺序）→ 构造函数体；
2. **析构**：析构函数体 → 非静态数据成员（声明逆序）→ 直接基类（声明逆序）→ 虚基类（仅最派生类，构造逆序）。

构造期间、析构期间，对象在多态意义上"是"当前构造函数/析构函数所属的类（[[class.cdtor]]）：虚调用、`typeid`、`dynamic_cast` 都不会"看到"更派生的部分。若构造中途抛出异常，已构造完毕的子对象按逆序析构，对象本身的析构函数**不**调用——除非是委托构造函数的函数体抛出（[[except.ctor]]）。

## 七、逐行追踪

最后，用一个打印所有特殊成员函数的类型，把前面的规则落到一段具体的程序上。每个对象在构造时得到一个新编号 `#n`。

```cpp run title="trace.cpp" ok
#include <cstdio>
#include <utility>
#include <vector>

struct Tr {
    static inline int next = 0;
    int id;
    Tr() : id(++next)                  { std::printf("  #%d Tr()\n", id); }
    Tr(const Tr& o) : id(++next)       { std::printf("  #%d Tr(const Tr&) <- #%d\n", id, o.id); }
    Tr(Tr&& o) noexcept : id(++next)   { std::printf("  #%d Tr(Tr&&) <- #%d\n", id, o.id); }
    Tr& operator=(const Tr& o)         { std::printf("  #%d = copy #%d\n", id, o.id); return *this; }
    Tr& operator=(Tr&& o) noexcept     { std::printf("  #%d = move #%d\n", id, o.id); return *this; }
    ~Tr()                              { std::printf("  #%d ~Tr()\n", id); }
};

Tr factory() { Tr t; return t; }       // NRVO 候选
Tr pass(Tr p) { return p; }            // 形参：只能隐式移动

struct Holder {
    Tr m;
    Holder(Tr x) : m(std::move(x)) {}
};

int main() {
    std::puts("[1] Tr a = factory();");
    Tr a = factory();
    std::puts("[2] Tr b = pass(a);");
    Tr b = pass(a);
    std::puts("[3] Holder h(Tr{});");
    Holder h(Tr{});
    std::puts("[4] a = pass(Tr{});");
    a = pass(Tr{});
    std::puts("[5] vector");
    std::vector<Tr> v;
    v.reserve(1);
    v.push_back(b);
    v.push_back(std::move(a));
    std::puts("[6] end of main");
}
```

本机 Clang 23 + libc++ 的输出与逐步解释：

**[1] `Tr a = factory();`**

```text
  #1 Tr()
```

`factory()` 是 prvalue，`a` 是它的结果对象（[[dcl.init#15.6.1]]）；`factory` 内部的 `return t;` 满足 NRVO 条件（[[class.copy.elision#1.1]]），Clang 把 `t` 直接构造在 `a` 的存储中。全程 1 次构造。用 `-fno-elide-constructors` 编译，这里会多出一次 `Tr(Tr&&)`（从 `t` 到 `a`）和一次析构。

**[2] `Tr b = pass(a);`**

```text
  #2 Tr(const Tr&) <- #1
  #3 Tr(Tr&&) <- #2
  #2 ~Tr()
```

- `a` 是左值，按值形参 `p` 由**复制**构造（#2）；
- `return p;`：形参不能 NRVO，但 `p` 是 move-eligible 的 xvalue，于是**移动**构造返回值；返回值的结果对象就是 `b`（#3）；
- 形参 #2 销毁。形参在函数返回时销毁、还是在调用所在的完整表达式结束时销毁，是**实现定义**的（[[expr.call#7]]）；Itanium ABI 下由调用方在完整表达式末尾销毁。

**[3] `Holder h(Tr{});`**

```text
  #4 Tr()
  #5 Tr(Tr&&) <- #4
  #4 ~Tr()
```

- 实参 `Tr{}` 是 prvalue，形参 `x` 就是它的结果对象（#4），没有复制；
- *mem-initializer* `m(std::move(x))` 直接初始化成员 `m`：`std::move(x)` 是 xvalue，**移动**构造（#5）；
- 形参 #4 销毁。成员 `m` 不能"窃取"形参的存储——它必须住在 `h` 里面，所以这里的一次移动无法避免。这就是"按值接收再 `std::move` 进成员"惯用法的代价：一次移动。

**[4] `a = pass(Tr{});`**

```text
  #6 Tr()
  #7 Tr(Tr&&) <- #6
  #1 = move #7
  #7 ~Tr()
  #6 ~Tr()
```

- `Tr{}` 直接成为形参 `p`（#6）；
- `return p;` 隐式移动到返回值（#7）；
- 这次返回值**不是**用来初始化一个对象，而是作为 `operator=(Tr&&)` 的实参——引用要绑定到 prvalue，于是**临时量实质化**（[[class.temporary#2]]），#7 就是这个临时对象；
- 移动赋值 `a = #7`（`a` 的编号仍是 #1：赋值不创建对象）；
- 完整表达式结束：临时对象 #7 销毁，然后形参 #6 销毁（同一完整表达式中按构造逆序）。

**[5] `std::vector`**

```text
  #8 Tr(const Tr&) <- #3
  #9 Tr(Tr&&) <- #1
  #10 Tr(Tr&&) <- #8
  #8 ~Tr()
```

- `v.push_back(b)`：`b` 是左值，复制进容量为 1 的缓冲区（#8）；
- `v.push_back(std::move(a))`：容量不足，需要扩容。libc++ 先在**新**缓冲区中构造新元素（#9，从 `a` 移动），再把旧元素搬过去（#10，从 #8 **移动**——因为 `Tr` 的移动构造是 `noexcept`），最后销毁旧元素 #8。如果把 `Tr(Tr&&)` 的 `noexcept` 去掉，#10 这一行会变成 `Tr(const Tr&)`。

**[6] `main` 结束**

```text
  #9 ~Tr()
  #10 ~Tr()
  #5 ~Tr()
  #3 ~Tr()
  #1 ~Tr()
```

局部变量按声明的逆序销毁（[[stmt.jump]]）：先 `v`（它按下标逆序销毁元素：`v[1]` 是 #9，`v[0]` 是 #10——元素的析构顺序是库的选择），再 `h`（其成员 `m` 是 #5），再 `b`（#3），最后 `a`（#1）。

计数一下：一共构造了 10 个对象，析构了 10 次——每次构造都恰好对应一次析构，即使发生了复制消除（[[class.copy.elision#1]] 注 1）。

## 八、速查清单

- 能用 Rule of 0 就用 Rule of 0。
- 需要虚析构函数时，用 `= default` 显式恢复其余四个（或明确 `= delete` 复制）。
- 移动操作写成 `noexcept`；用 `static_assert(std::is_nothrow_move_constructible_v<T>)` 守护。
- 工厂函数返回 prvalue（`return T(...);`）或单一的局部变量；不要 `return std::move(local);`。
- 不可复制、不可移动的类型（`std::mutex`、锁守卫）也能从工厂函数按值返回——前提是返回 prvalue。
- 想 `memcpy` 就保证类型平凡可复制：不要写空的析构函数，用 `= default`。
- 复制构造函数不要有业务副作用：它会不会被调用取决于消除。

延伸阅读：值类别与 prvalue 语义见 [[topics/value-categories]]；各条款细节见 [[special]]、[[class.copy.ctor]]、[[class.copy.assign]]、[[class.dtor]]、[[class.base.init]]、[[class.cdtor]]、[[class.copy.elision]]。
