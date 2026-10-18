---
title: 对象生命周期
summary: 生命周期何时开始、何时结束；生命周期之外的指针与 glvalue 只能有限使用；透明可替换与 std::launder；作用域退出时类型不符、const 对象被替换的 UB
status: done
papers: P0137R1, P0593R6
related: intro.object, basic.stc, class.cdtor, class.union, expr.new, ptr.launder, basic.indet
tags: 对象模型, 生命周期, UB, launder
updated: 2026-10-17
---

[[intro.object]] 回答了"对象从哪里来"，本节回答"对象**什么时候能用**"。**生命周期**（lifetime）是对象的一个运行期属性：一个对象只有在生命周期之内，才能以它的类型被正常地读、写、调用成员函数。生命周期之外——存储已经有了但构造还没完成，或者析构已经开始但存储还没释放——指向它的指针和引用仍然"存在"，却只能做极其有限的事。

本节是 placement new、`std::optional`/`std::variant`/`std::vector` 这类"手动管理对象"代码的法律依据，也是 `std::launder` 存在的理由。它要解决的核心矛盾是：

- 程序员希望**复用存储**（在同一块内存上先后放不同的对象），
- 优化器希望**假设对象不变**（`const` 成员不会变、vptr 不会变、指针指向的对象身份不会变），

两者之间的边界必须精确划定。

## "之前"与"之后"（¶1）

本节中的"before"和"after"指 **happens-before** 关系（[[intro.races]]），而不是单线程里的"先后"。这意味着本节的规则在多线程下也成立：一个线程正在构造的对象，另一个线程在没有同步的情况下去访问它，就是在"生命周期开始之前"访问——UB（¶8 注 5）。

## 生命周期何时开始（¶2 前半）

### 空初始化

先定义一个术语。变量具有**空初始化**（vacuous initialization），如果它被默认初始化、没有进行其他初始化，并且（若是类类型或其数组）默认初始化选中的是**平凡**构造函数。直觉：`int x;`、`struct POD { int a; } p;` 这种"什么都没做"的初始化。

### 开始的条件

类型为 `T` 的对象的生命周期在以下两件事都完成时开始：

- ¶2.1 获得了**大小和对齐都合适**的存储；
- ¶2.2 它的初始化（如果有）**完成**——包括空初始化。

```cpp title="lifetime-begin.cpp" ok
#include <string>

void f() {
    int x;                 // 空初始化：生命周期在此开始，值是错误值（[basic.indet]）
    std::string s("abc");  // 构造函数返回时生命周期开始
    struct P { int a, b; } p;   // 平凡默认构造 ⇒ 空初始化，生命周期开始
    (void)x; (void)p;
}

int main() { f(); }
```

对类类型而言，"初始化完成"就是**构造函数执行完毕**。在构造函数体执行期间，对象处于"构造期间"（period of construction），既不是"生命周期之前"的完全不可用状态，也不是正常的生命周期之内——[[class.cdtor]] 给出了这期间的专门规则（例如虚函数调用按当前正在构造的类分派）。¶7 和 ¶8 都说"对正在构造或析构的对象，见 [[class.cdtor]]"。

### 联合体成员的例外

如果对象是联合体成员或其子对象，只有当该成员是联合体中**被初始化的成员**时，它的生命周期才开始（[[dcl.init.aggr]]、[[class.base.init]]）；或者按照 [[class.union]]（赋值隐式切换活跃成员）、[[class.copy.ctor]] / [[class.copy.assign]]（平凡复制/移动联合体时复制活跃成员）、[[obj.lifetime]]（`std::start_lifetime`）所述的方式开始。另有 [[allocator.members]] 的例外：`std::allocator<T>::allocate` 创建数组对象但不开始其元素的生命周期。

```cpp run title="union-lifetime.cpp" ok
union U { int i; float f; };

int main() {
    U u{.i = 1};     // u.i 是被初始化的成员，其生命周期开始；u.f 不在生命周期内
    u.f = 2.0f;      // [class.union]：赋值隐式创建 float 对象，结束 u.i 的生命周期
    return u.f == 2.0f ? 0 : 1;   // OK
    // 若此时读 u.i：UB——u.i 不在生命周期内（¶8.1）
}
```

## 生命周期何时结束（¶2 后半）

类型为 `T` 的对象 *o* 的生命周期在以下任一情况发生时结束：

- ¶2.3 `T` 是**非类类型**：对象被**销毁**（如伪析构函数调用 `p->~int()`、`std::destroy_at`，或者存储期结束时）；
- ¶2.4 `T` 是**类类型**：**析构函数调用开始**；
- ¶2.5 对象占据的存储被**释放**，或者被一个**不嵌套于** *o* 的对象**复用**（[[intro.object#4]]）。

注意 ¶2.4 说的是"析构函数调用**开始**"，而不是结束：析构函数体执行期间，对象已经不在生命周期内（处于"析构期间"，由 [[class.cdtor]] 管辖）。

¶2.5 中的"不嵌套于 *o*"是 [[intro.object#3]] "提供存储"的配套规则：在 `unsigned char` 数组里 placement new 一个对象，新对象嵌套于数组，所以**不会**结束数组的生命周期。

### new-expression 中"复用"发生在初始化之前

¶2 最后一句是一个精确的时序规定：

!!! std
    When evaluating a *new-expression*, storage is considered reused after it is returned from the allocation function, but before the evaluation of the *new-initializer*.

    求值 *new-expression* 时，存储在分配函数返回之后、*new-initializer* 求值之前即被视为已复用。

这意味着 placement new 的**初始化器里不能再读旧对象**：

```cpp run title="reuse-before-init.cpp" ub
#include <new>

struct S { int m; };

int main() {
    S x{1};
    ::new (&x) S(x.m);   // UB: 求值 x.m 时，x 的存储已被视为复用，旧 x 的生命周期已经结束
    return x.m;
}
```

```cpp run title="reuse-before-init-fixed.cpp" ok
#include <new>

struct S { int m; };

int main() {
    S x{1};
    int v = x.m;         // 先读出来
    ::new (&x) S(v);     // OK
    return x.m;          // OK: x 透明可替换（¶9），名字 x 指向新对象
}
```

这条规则也解释了为什么"自赋值安全"的 `this->~T(); new (this) T(other);` 惯用法在 `other` 就是 `*this` 时是错误的：析构之后 `other` 已经不在生命周期内。

## 引用的生命周期（¶3）与生命周期内才有的属性（¶5）

¶3：引用的生命周期在其初始化完成时开始；结束的方式**如同它是一个需要存储的标量对象**。也就是说，引用在其存储期结束时（或其所在的对象的存储被复用时）结束——引用本身没有析构函数可言。

¶4 是注，指向 [[class.base.init]] 对基类和成员子对象生命周期的描述。

¶5：标准中归属于对象或引用的**所有属性，只在其生命周期内成立**。这句话是一个"总闸"：标准其他地方说"对象的值是……""成员函数调用会……"时，都默认前提是对象在生命周期内。生命周期之外能做的事，必须由 ¶7、¶8 和 [[class.cdtor]] 另行明确允许。

## 不调用析构函数而结束生命周期（¶6）

程序**可以**不调用析构函数就结束类对象的生命周期——通过复用或释放其存储。此时析构函数**不会**被隐式调用。注 4 提醒：程序的正确性通常依赖于每个类对象的析构函数被调用（例如释放资源）；但跳过它**本身不是 UB**，只是可能泄漏资源。

```cpp run title="skip-dtor.cpp" ok
#include <new>
#include <string>

int main() {
    alignas(std::string) unsigned char buf[sizeof(std::string)];
    auto* s = ::new (buf) std::string(100, 'x');   // 堆上分配了 100 字节
    ::new (buf) int(0);   // 复用存储：*s 的生命周期结束，析构函数没有被调用 —— 内存泄漏，但不是 UB
    (void)s;
}
```

!!! history "曾经的那句“依赖析构副作用即 UB”"
    较早的标准在此处还有一句：若不显式调用析构函数，"依赖于析构函数所产生副作用的程序具有未定义行为"。这句话的含义一直说不清楚（什么叫"依赖"？），在后来的修订中被删除，改为现在不具规范效力的注 4。

## 生命周期之外的指针（¶7）

¶7 规定：在对象生命周期开始之前（存储已分配）或结束之后（存储未被复用或释放），任何**表示该存储位置地址的指针**可以被使用，但只能有限使用：

- 对正在构造或析构的对象，见 [[class.cdtor]]；
- 否则，这样的指针指向的是**已分配的存储**（allocated storage），**把它当作 `void*` 使用**是良定义的；
- **可以**对其解引用（`*p`），但得到的左值只能按 ¶8 的方式有限使用。

以下四种用法是 **UB**：

| 列表项 | 禁止的操作 | 为什么 |
|---|---|---|
| ¶7.1 | 作为 *delete-expression* 的操作数 | `delete` 要调用析构函数、读取动态类型来确定释放大小 |
| ¶7.2 | 访问非静态数据成员，或调用非静态成员函数 | 成员访问需要对象存在 |
| ¶7.3 | 转换为指向**虚基类**（或其基类）的指针 | 虚基类偏移要从 vptr 指向的表里读 |
| ¶7.4 | 作为 `dynamic_cast` 的操作数 | 需要读取 vptr 获取动态类型 |

注意哪些**不在**清单里：转换为非虚基类的指针（静态偏移，编译期可知）、`static_cast` 到 `void*`、比较、拷贝指针值——这些都允许。（较早的标准还对 `static_cast` 有一条额外限制，现行草案已经没有。）

改编标准例 2（补齐定义使之可以编译）：

```cpp run title="mutate.cpp" ub
#include <cstdlib>
#include <new>

struct B {
    virtual void f() {}
    void mutate();
    virtual ~B() {}
};
struct D1 : B { void f() override {} };
struct D2 : B { void f() override {} };

void B::mutate() {
    ::new (this) D2;   // 复用存储 —— 结束 *this 的生命周期
    f();               // UB: 通过生命周期已结束的对象调用成员函数（¶7.2；this->f()）
    void* p = this;    // OK: this 指向有效的存储，当作 void* 使用
    (void)p;
}

int main() {
    void* p = std::malloc(sizeof(D1) + sizeof(D2));
    B* pb = ::new (p) D1;
    pb->mutate();
    void* q = pb;      // OK: pb 指向有效存储
    (void)q;
    pb->f();           // UB: *pb 的生命周期已结束（新对象 D2 与 D1 类型不同，不透明替换）
    std::free(p);
}
```

为什么 `pb->f()` 是 UB 而不能"自动"调用 `D2::f`？因为编译器有权假设 `*pb` 的动态类型在其生命周期内不变：在 `pb = new D1` 之后，它可以把 `pb->f()` 去虚化为直接调用 `D1::f`，而中间的 `mutate()` 是一个它看不透的调用也不影响这个推断——它不能把 `D1` 变成 `D2`，因为那会结束对象的生命周期，之后再通过 `pb` 访问就是 UB。正确的写法是**使用 placement new 返回的指针**：`B* pb2 = ::new (p) D2; pb2->f();`。

## 生命周期之外的 glvalue（¶8）

¶8 是 ¶7 的 glvalue 版本：在同样的时间窗内，引用原对象的 glvalue 可以被使用，但只能使用**不依赖其值的属性**（如取地址、绑定到同类型引用）。以下是 **UB**：

| 列表项 | 禁止的操作 |
|---|---|
| ¶8.1 | 用该 glvalue **访问**对象（[[defns.access]]：读或写） |
| ¶8.2 | 调用非静态成员函数 |
| ¶8.3 | 绑定到**虚基类**的引用 |
| ¶8.4 | 作为 `dynamic_cast` 或 `typeid` 的操作数 |

```cpp run title="glvalue-outside.cpp" ub
#include <new>
#include <memory>

int main() {
    int x = 1;
    std::destroy_at(&x);   // 结束 x 的生命周期（C++20：标量也"被销毁"）
    int* p = &x;           // OK: 取地址不依赖值
    int& r = x;            // OK: 绑定到同类型的引用
    (void)p;
    return r;              // UB: 访问生命周期之外的对象（¶8.1）
}
```

注 5 特别指出多线程含义：一个线程正在构造的对象，被另一个线程在没有适当同步的情况下引用，就是 UB——因为"之前/之后"是 happens-before 关系，没有同步就谈不上"在构造完成之后"。这是双检锁（double-checked locking）错误写法的标准层面解释。

## 透明可替换（¶9–¶10）

最实用也最微妙的两段。场景：旧对象的生命周期结束后、存储被释放之前，在**同一位置**创建了一个新对象。问：原来指向旧对象的**指针、引用、名字**，能不能直接拿来用新对象？

¶10 的回答：如果旧对象 *o1* **透明可替换**（transparently replaceable）为新对象 *o2*，那么指向 *o1* 的指针、引用 *o1* 的引用、*o1* 的名字**自动指向** *o2*，并且在 *o2* 生命周期开始后可以用来操作 *o2*。

¶9 的定义：*o1* 透明可替换为 *o2*，当且仅当以下两种情形之一：

**情形一（¶9.1）：两者都是完整对象**，且

- ¶9.1.1 *o1* 不是 `const` 的；
- ¶9.1.2 *o2* 占据的存储**恰好覆盖** *o1* 曾占据的存储；
- ¶9.1.3 *o1* 与 *o2* 类型相同（忽略顶层 cv）。

**情形二（¶9.2）：两者是对应的直接子对象**（[[intro.object#2]]），且

- ¶9.2.1 *o1* 的完整对象不是 `const` 的，或
- ¶9.2.2 *o1* 是 `mutable` 成员子对象或其子对象。

情形二借助 [[intro.object#2]] 的"对应的直接子对象"概念，自然排除了**基类子对象**和 `[[no_unique_address]]` 成员（它们是潜在重叠子对象，见该段第 2.3 项），也要求类型相同（第 2.4 项）。

### 为什么有这些条件

每一条都对应一种优化器想做的假设：

| 条件 | 保护的优化 |
|---|---|
| 不是 `const` 完整对象 | 编译器可以假设 `const` 对象的值永不改变，把它的值常量传播、缓存在寄存器里 |
| 恰好覆盖 | 指针算术、子对象偏移在新旧对象间保持一致 |
| 类型相同 | 动态类型（vptr）不变，允许去虚化 |
| 不是基类子对象 | 基类子对象的动态类型是派生类，替换成基类类型会改变"最派生对象"；且潜在重叠子对象的存储可能与其他成员共享 |

```cpp run title="transparent-replace.cpp" ok
#include <new>

struct C {
    int i;
    void f() {}
    const C& operator=(const C& other);
};

const C& C::operator=(const C& other) {
    if (this != &other) {
        this->~C();              // *this 的生命周期结束
        ::new (this) C(other);   // 在同一位置创建同类型的新对象
        f();                     // OK: this 透明地指向新对象
    }
    return *this;
}

int main() {
    C c1{1}, c2{2};
    c1 = c2;                     // OK
    c1.f();                      // OK: 名字 c1 指向新的 C 对象
    return c1.i == 2 ? 0 : 1;
}
```

### C++20 的放宽：`const` 成员和引用成员不再阻止替换

在 C++17 中，¶9 还有一条：若是类类型，**不能含有 `const` 限定的或引用类型的非静态数据成员**。这让下面这种非常自然的代码变成 UB，必须到处用 `std::launder`：

```cpp run title="const-member.cpp" ok
#include <new>

struct X { const int n; int& r; };

int main() {
    int a = 1, b = 2;
    X x{1, a};
    x.~X();
    ::new (&x) X{2, b};   // C++17: x 这个名字不能再用来访问新对象，须 std::launder(&x)
    return x.n + x.r;     // C++20 起 OK: X 不是 const 完整对象，类型相同，恰好覆盖
}
```

这一限制在 C++20 周期中被删除。动机之一：`std::optional<X>`、`std::vector<X>` 中元素含有 `const` 成员时，标准库实现若严格遵守 C++17 就得在每次访问时 `launder`，这既笨拙又有性能顾虑（`launder` 会抑制优化）。现在只剩下"完整对象本身是 `const`"这一条：

```cpp run title="const-complete.cpp" ok
#include <new>

struct X { int n; };

int main() {
    const X* p = new const X{3};
    const int a = p->n;
    ::new (const_cast<X*>(p)) const X{5};   // 新对象：p 不指向它，因为原对象是 const 完整对象
    // const int b = p->n;                  // UB: p 仍"指向"已结束生命周期的旧对象
    const int c = std::launder(p)->n;       // OK: launder 得到指向新对象的指针
    delete std::launder(p);
    return a + c == 8 ? 0 : 1;
}
```

（这是 [[ptr.launder]] 中的标准例子。注意它是**动态**存储期的 `const` 对象，因此不受 ¶12 的约束；若是静态/自动存储期的 `const` 完整对象，连创建新对象本身都是 UB。）

### 不透明替换时：`std::launder`

¶10 注 6：条件不满足时，可以对"表示该存储地址的指针"调用 `std::launder`（[[ptr.launder]]）得到指向新对象的指针。`launder` 的前置条件：地址处有一个与目标类型**相似**的对象处于生命周期内（或是生命周期内数组的元素），且结果可达的字节都能经由原指针到达。

典型的不透明替换情形：

1. 原对象是 `const` 完整对象（上例）；
2. 新旧对象类型不同（例如 `unsigned char` 缓冲区里放的 `T`，你手里的是 `unsigned char*` 转出来的 `T*`）；
3. 基类子对象被替换。

```cpp run title="optional-like.cpp" ok
#include <new>
#include <utility>
#include <string>

template<class T>
class Opt {
    alignas(T) unsigned char buf_[sizeof(T)];   // buf_ 为 T 提供存储
    bool has_ = false;

    T* ptr() { return std::launder(reinterpret_cast<T*>(buf_)); }
    // 没有 launder：reinterpret_cast 的结果指向 buf_[0]（unsigned char），不指向 T —— 访问是 UB

public:
    Opt() = default;
    ~Opt() { reset(); }
    template<class... A>
    T& emplace(A&&... a) {
        reset();
        T* p = ::new (buf_) T(std::forward<A>(a)...);
        has_ = true;
        return *p;           // placement new 的返回值本身就指向新对象，无需 launder
    }
    void reset() { if (has_) { ptr()->~T(); has_ = false; } }
    T& operator*() { return *ptr(); }
};

int main() {
    Opt<std::string> o;
    o.emplace("hello");
    o.emplace("world");      // 先析构旧 string，再在同一 buf_ 中构造新 string
    return (*o).size() == 5 ? 0 : 1;
}
```

!!! tip "避免 launder 的另一种写法"
    把 placement new 返回的指针存成成员 `T* p_;`，之后一律通过 `p_` 访问——它就是指向新对象的指针，无需 `launder`。代价是多存一个指针。标准库实现通常选择用联合体成员（`union { T val_; };`）作为存储，借助 C++20 的透明替换规则同样避免 `launder`。

### `std::vector` 风格的存储

```cpp run title="vector-like.cpp" ok
#include <memory>
#include <string>

int main() {
    std::allocator<std::string> a;
    std::string* p = a.allocate(3);          // 创建 std::string[3] 数组对象，但元素生命周期未开始
    for (int i = 0; i < 3; ++i)
        std::construct_at(p + i, 3, char('a' + i));   // p + i 合法：p 指向数组元素（[allocator.members]）
    std::string s = p[0] + p[2];             // OK: 元素在生命周期内
    std::destroy(p, p + 3);
    a.deallocate(p, 3);
    return s == "aaaccc" ? 0 : 1;
}
```

在 P0593 之前，`allocate` 返回的存储里没有数组对象，`p + i` 严格说是 UB——这是著名的"`std::vector` 无法用标准 C++ 实现"问题。现在 [[allocator.members]] 规定 `allocate` 创建一个 `T[n]` 数组对象（但不开始元素的生命周期），指针算术因此合法；元素在 `construct_at` 后才开始生命周期。

## 作用域退出时的"原类型"要求（¶11）

如果程序结束了一个**静态、线程或自动存储期**的、具有**非平凡析构函数**的 `T` 类型对象的生命周期，并且在**隐式析构调用发生时**，该存储位置上**没有**一个原类型的对象，则行为未定义。即使是因异常退出块也是如此。

道理很直接：编译器会在作用域结束时**无条件地**插入 `T::~T()` 调用（脚注 17：自动对象在离开块时、线程对象在线程退出时、静态对象在程序退出时），它不可能知道你中途换了对象。

```cpp run title="scope-exit.cpp" ub
#include <new>

class T {};
struct B { ~B() {} };   // 非平凡析构

void h() {
    B b;
    ::new (&b) T;       // 复用存储：b 的生命周期结束，原位置上是一个 T
}                       // UB: 隐式调用 B::~B() 时，该位置没有 B 对象

int main() { h(); }
```

修复：在离开作用域之前，再在原位置构造回一个 `B`。这正是"异常安全"的难点——如果 `::new (&b) B` 抛出异常，退出作用域时那里没有 `B`，同样是 UB。所以这种技巧只适合构造不会抛出的类型。

```cpp run title="scope-exit-fixed.cpp" ok
#include <new>

struct B { ~B() {} };
struct T {};

void h() {
    B b;
    b.~B();
    T* t = ::new (&b) T;   // 暂时用这块存储放 T
    t->~T();
    ::new (&b) B;          // 退出前放回一个 B（B 的构造不抛出）
}                          // OK: 隐式析构时该位置有一个 B

int main() { h(); }
```

## 不能在 const 对象的存储上创建新对象（¶12）

在**静态、线程或自动存储期**的 `const` **完整**对象占据的存储中——或者它在生命周期结束前曾占据的存储中——创建新对象，是 UB。

```cpp run title="const-static.cpp" ub
#include <new>

struct B { B() {} ~B() {} };

const B b;

void h() {
    b.~B();
    ::new (const_cast<B*>(&b)) const B;   // UB: 在 const 完整对象（静态存储期）的存储中创建对象
}

int main() { h(); }
```

为什么？因为这类对象可能被放在**只读内存**（`.rodata` 段）里——写入会触发硬件异常；即使没有，编译器也已经把它的值常量传播到所有使用处了。动态存储期的 `const` 对象（`new const X`）不受此条约束，因为它们来自可写的堆。

## 实现视角

!!! impl "编译器如何利用生命周期规则"
    - **去虚化**：`B* p = new D; p->f();` 编译器知道 `*p` 的动态类型是 `D`，可直接调用 `D::f`。如果允许 `p` 在不 `launder` 的情况下"看到"一个替换进来的 `D2`，这项优化就不成立。Clang 的 `-fstrict-vtable-pointers` 就是基于这些规则更激进地假设 vptr 不变，并把 `std::launder` 实现为 vptr 值的"屏障"。
    - **const 传播**：`const` 完整对象的值在其生命周期内被假定不变，可以被提前读入寄存器或折叠成常量。¶9.1.1 和 ¶12 保护这一点。
    - **`std::launder` 的成本**：在 GCC/Clang 上它是 `__builtin_launder`，生成零条指令，只是对优化器说"别对这个指针指向的东西做旧假设"。它不是运行时操作。
    - **析构顺序**：编译器在作用域退出处直接生成析构调用（或在异常路径的 landing pad 里生成），这就是 ¶11 的根源。

## 历史与演进

!!! history "历史与演进"
    - **C++98/03**：已有生命周期的概念和 ¶7/¶8 那样的清单，以及透明替换的雏形（"若满足……则指针自动指向新对象"），条件中包括"不含 const 或引用成员"。
    - **C++17**：[[P0137R1]] 随对象模型重写引入 `std::launder`（[[ptr.launder]]），把"不满足透明替换条件时如何获取新对象指针"变得有据可依。
    - **C++20**：
        - 删除"类类型不得含 const/引用成员"的限制；
        - 生命周期结束条件从"类类型**且有非平凡析构函数**时析构调用开始"改为"类类型时析构调用开始"；非类类型对象也有了"被销毁"的概念（伪析构函数调用结束其生命周期）——这些都与 [[P0593R6]] 的隐式对象创建一同落地；
        - `std::allocator::allocate` 创建数组对象的规定。
    - **C++26 草案**：透明替换的子对象情形改用 [[intro.object#2]] 新增的"对应的直接子对象"表述，并明确排除潜在重叠子对象；¶2 明确 *new-expression* 中存储在 *new-initializer* 求值前即被视为复用（标准例 1）。

## 陷阱

!!! pitfall "以为 placement new 后旧指针一定能用"
    只有透明可替换时才能用。最常见的反例：原对象是基类子对象（多态替换）、原对象类型与新对象不同、原对象是 `const` 完整对象。不确定时，用 placement new 的**返回值**。

!!! pitfall "以为 `std::launder` 能“修好”一切"
    `launder` 只是给你一个指向**已存在的**、**生命周期内的**对象的指针。如果那个地址上根本没有该类型的对象（例如 `std::string` 被放在 `malloc` 来的内存而没有 placement new），`launder` 的前置条件不满足，调用本身就是 UB。

!!! pitfall "析构后再读成员做“调试”"
    `obj.~T(); log(obj.x);` 是 UB（¶8.1），即使 `T` 的析构函数什么都没做。对平凡析构的类类型，C++20 起显式调用析构函数同样结束生命周期。

!!! pitfall "在 placement new 的参数里引用旧对象"
    `new (&x) S(x.m)` 是 UB（¶2 最后一句）。先把需要的值读到局部变量里。

## 思考题

!!! question "思考题 1"
    下面的程序有 UB 吗？

    ```cpp
    struct Base { virtual int id() { return 1; } virtual ~Base() = default; };
    struct Der : Base { int id() override { return 2; } };
    int main() {
        Der d;
        Base* pb = &d;
        pb->~Base();
        ::new (pb) Base;
        int r = pb->id();
        ::new (&d) Der;
        return r;
    }
    ```

<details markdown="1">
<summary>答案</summary>

有 UB。`pb->~Base()` 是虚析构调用，实际调用 `Der::~Der()`，结束了 `d` 的生命周期。`::new (pb) Base` 在 `d` 的存储上创建了一个完整对象 `Base`（`pb` 此时是指向生命周期已结束的 `Der` 的基类子对象的指针，但用于 placement new 只是当作 `void*`，没问题）。然而旧对象是 `Der` 的**基类子对象**，与新的 `Base` 完整对象不是"对应的直接子对象"（基类子对象是潜在重叠子对象，[[intro.object#2]] 第 2.3 项），也不满足 ¶9.1（旧的 `Base` 不是完整对象）——不透明替换，所以 `pb->id()` 是 ¶7.2 的 UB。正确做法是使用 placement new 的返回值，或 `std::launder(pb)->id()`。最后又放回了 `Der`，¶11 在作用域退出时满足。
</details>

!!! question "思考题 2"
    `struct S { const int c; }; S s{1}; s.~S(); new (&s) S{2}; int v = s.c;` 在 C++17 和 C++20 中分别如何？如果改为 `const S s{1};` 呢（假设 `s` 是自动存储期）？

<details markdown="1">
<summary>答案</summary>

C++17：`S` 含 `const` 成员，不透明可替换，`s.c` 通过旧名字访问新对象是 UB（需要 `std::launder(&s)->c`）。C++20 起：`s` 不是 `const` 完整对象，类型相同、恰好覆盖，透明可替换，OK。

改为 `const S s{1};`：在自动存储期的 `const` 完整对象的存储上创建新对象，按 ¶12 直接是 UB，`launder` 也救不了。
</details>

!!! question "思考题 3"
    为什么 ¶7 允许把生命周期之外的 `D*` 转换为**非虚**基类指针，却禁止转换为**虚**基类指针？

<details markdown="1">
<summary>答案</summary>

非虚基类子对象相对派生类对象的偏移是编译期常量，转换只是给地址加一个固定偏移，不需要读取对象内容。虚基类子对象的偏移取决于最派生类型，通常要通过对象的 vptr 在虚表里查（Itanium ABI 中的 vbase offset），也就是要**读取对象**——而对象不在生命周期内（vptr 可能尚未设置或已被析构过程改写）。
</details>

## 小结

| 时刻 / 情形 | 规则 |
|---|---|
| 生命周期开始 | 存储就绪 **且** 初始化完成（含空初始化）；联合体成员需成为活跃成员 |
| 生命周期结束 | 非类：被销毁；类：析构**开始**；或存储被释放 / 被非嵌套对象复用 |
| new-expression | 分配函数返回后、初始化器求值前即视为复用存储 |
| 生命周期外的指针 | 当 `void*` 用 OK；`delete`、成员访问、转虚基类、`dynamic_cast` 为 UB |
| 生命周期外的 glvalue | 不依赖值的属性 OK；访问、调成员、绑虚基类引用、`dynamic_cast`/`typeid` 为 UB |
| 透明替换 | 完整对象：非 const + 恰好覆盖 + 同类型；子对象：对应的直接子对象 + 完整对象非 const（或 mutable） |
| 不透明时 | 用 placement new 返回值，或 `std::launder` |
| 作用域退出 | 非平凡析构的静态/线程/自动对象，退出时原位置必须有原类型对象 |
| const 对象 | 静态/线程/自动存储期的 const 完整对象，其存储上不得创建新对象 |
