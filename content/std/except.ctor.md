---
title: 栈回溯
summary: 异常从抛出点传到 handler 的途中，按构造完成的逆序销毁自动对象；return 语句中途抛出时连返回对象也要销毁；初始化或析构半途抛出时，哪些子对象已知已初始化、要被析构；委托构造函数的特殊规则；new 表达式归还内存
status: done
related: except.throw, except.handle, except.pre, class.base.init, class.dtor, dcl.init.aggr, dcl.init.general, expr.new, stmt.return, class.inhctor.init, expr.prim.lambda.capture
tags: 异常, 栈回溯, 析构, 构造函数
updated: 2026-10-17
---

本节回答一个问题：异常传播的途中，哪些对象会被析构？RAII 的规范依据就在这里。C++ 能用析构函数管理资源而不需要 `finally`，正是因为本节保证：**无论控制以正常方式还是以异常方式离开作用域，已经构造好的对象都会被析构，并且只有它们会被析构**。

本节的稳定名 `[except.ctor]` 来自早年版本的标题 Constructors and destructors，现在的正式标题是 Stack unwinding。

## 栈回溯的定义（¶1）

¶1 控制从抛出点传到 handler 的过程中，按本节规定的过程销毁对象，这一过程称为**栈回溯**（[[g:stack-unwinding]]，stack unwinding）。

注意栈回溯发生在找到 handler 之后：若根本找不到匹配的 handler，是否回溯由实现定义（[[except.handle#8]]）；若 handler 搜索遇到 `noexcept` 边界，可以只回溯一部分（[[except.terminate#2]]）。

## 自动对象的销毁（¶2）

### 基本规则

¶2 第一句规定：具有自动存储期的对象，如果自进入 try 块以来已经构造、尚未销毁，就会被销毁，销毁顺序是构造完成顺序的逆序。

这里有三个要点：

1. 范围：只涉及进入（接住异常的那个）try 块以来构造的对象。try 块之外更早构造的对象不受影响，它们在 handler 结束后照常存活。
2. 只销毁已构造完成的对象：抛出时正在构造的对象不在此列（它的构造未完成，由 ¶3 处理它的子对象），还没执行到的声明更不必说。
3. 逆序：按构造完成的逆序，而不是按声明的逆序。两者通常一致，但对于临时对象、条件中声明的变量等，构造完成的时刻才是准确的依据。

```cpp run title="unwind-order.cpp" ok
#include <cstdio>

struct T {
    const char* n;
    explicit T(const char* s) : n(s) { std::printf("+%s ", n); }
    ~T() { std::printf("-%s ", n); }
};

void f() {
    T a("a");
    T b("b");
    throw 0;
    T c("c");          // 从未构造，自然不会被析构
}

int main() {
    T outer("outer");  // 在 try 块之外：不参与回溯
    try {
        T t("t");
        f();
    } catch (int) {
        std::printf("| handler ");
    }
    std::printf("| after\n");
}
```

输出：`+outer +t +a +b -b -a -t | handler | after` 然后 `-outer`。

### `return` 中途抛出：返回对象也要销毁

¶2 第二句处理一个容易被忽略的情形：如果 `return` 语句已经构造好返回对象，之后在销毁临时对象或局部变量时抛出异常，那么返回对象的析构函数也要调用。

```cpp title="return-then-throw.cpp"
#include <cstdio>

struct A {
    int id;
    explicit A(int i) : id(i) { std::printf("A%d() ", id); }
    ~A() { std::printf("~A%d ", id); }
};
struct Y { ~Y() noexcept(false) { throw 0; } };

A f() {
    try {
        A a(1);
        Y y;
        A b(2);
        return A(3);    // #1：返回对象 A3 构造完成
    } catch (...) {     //     然后析构 b；析构 y 时抛出 ⇒ 栈回溯：
    }                   //     标准要求先销毁返回对象 A3，再销毁 a
    return A(4);        // #2：返回对象再次被构造
}

int main() { A r = f(); std::printf("| got A%d\n", r.id); }
```

按标准，输出应为 `A1() A2() A3() ~A2 ~A3 ~A1 A4() | got A4`（最后还有 `~A4`）。这样排序的原因是，返回对象在 #1 处最后完成构造（晚于 `a`），所以按逆序它最先被销毁（`b` 已经被正常析构，`y` 正在析构）。

!!! impl "编译器现状"
    本机 Clang 23 的实际输出是 `A1() A2() A3() ~A2 ~A1 A4() | got A4`，漏掉了 `~A3`，返回对象被泄漏。这是 Clang 长期存在的不符合之处（对应核心问题 CWG2176，即析构函数抛出时销毁返回对象的问题）。由于实现行为与标准不符，这里的代码块没有标判定。

    这个场景要求有一个 `noexcept(false)` 的析构函数在 `return` 之后抛出，实践中罕见，但它揭示了返回对象何时算构造完成的精确规则：返回对象在 `return` 语句的操作数求值时就已被构造，早于局部变量的析构（[[stmt.jump]]、[[stmt.return]]）。

## 初始化中途失败：析构已知已初始化的子对象（¶3 前半）

### 规则

¶3 若一个对象的初始化（委托构造函数的情形除外，见 ¶4）因异常而终止，则对该对象的每个子对象，只要它**已知已被初始化**（[[g:known-to-be-initialized]]）并且其初始化已经完成，就调用它的析构函数。

这句话里有两个条件：

- 已知已被初始化（known to be initialized）：该子对象不是匿名联合体成员（anonymous union member，指类中那个无名的匿名联合体对象本身，见下文），并且它的初始化由以下某处规定：
    - ¶3.1 [[class.base.init]]：构造函数初始化（基类、成员）；
    - ¶3.2 [[class.copy.ctor]]：预置的拷贝/移动构造函数；
    - ¶3.3 [[class.inhctor.init]]：继承构造函数；
    - ¶3.4 [[dcl.init.aggr]]：聚合初始化；
    - ¶3.5 [[expr.prim.lambda.capture]]：求值 lambda 表达式时初始化闭包对象；
    - ¶3.6 [[dcl.init.general]]：数组的默认初始化、值初始化或直接初始化。
- 初始化已完成：抛出时正在初始化的那个子对象不算，它自己的构造函数会负责清理它自己的子对象（递归地应用本条）。

为什么要加已知这个限定？因为有些子对象是否已构造，语言无从得知。最典型的是变体成员（variant member）：联合体的哪个成员是活动的，通常只有程序员知道。而匿名联合体对象本身没有可调用的有意义的析构函数（含非平凡成员时它的析构函数是被删除的），所以被明文排除。注 2 补充了两点：

- 对完整对象的初始化，已知已初始化的子对象包括虚基类子对象（虚基类只由最派生类构造，[[class.base.init#15]]）；
- 可能包括变体成员，但仅限被 *mem-initializer* 或指派初始化器（*designated-initializer-clause*）显式指名、或有默认成员初始化器的那个。

```cpp run title="partial-construction.cpp" ok
#include <cstdio>

struct M {
    const char* n;
    M(const char* s, bool fail = false) : n(s) {
        if (fail) throw 1;
        std::printf("+%s ", n);
    }
    ~M() { std::printf("-%s ", n); }
};

struct Base {
    M m{"Base::m"};
    ~Base() { std::printf("~Base "); }
};

struct X : Base {
    M a{"a"};
    M b{"b", true};    // 构造 b 时抛出
    M c{"c"};          // 从未开始构造
    X() { std::printf("X-body "); }
    ~X() { std::printf("~X "); }        // X 本身从未构造完成：~X 不会被调用
};

int main() {
    try { X x; } catch (int) { std::printf("| caught\n"); }
}
```

输出：`+Base::m +a -a ~Base -Base::m | caught`。

逐项解释：

- `Base` 子对象构造完成 ⇒ 被析构（调用 `~Base`，它再按 [[class.dtor#13]] 析构 `Base::m`）；
- `a` 构造完成 ⇒ 被析构；
- `b` 构造中抛出 ⇒ 不析构（`M` 的构造函数没有完成）；
- `c` 未开始 ⇒ 不析构；
- `X` 自身的析构函数不会被调用，因为 `X` 的构造函数没有完成，`X` 对象的生命周期从未开始（[[basic.life#2]]）。

所以在构造函数里 `new` 两个裸指针的写法会泄漏：

```cpp title="ctor-leak.cpp" ok
struct Leaky {
    int* p;
    int* q;
    Leaky() : p(new int[100]), q(new int[100]) {}   // 第二个 new 抛出 bad_alloc 时：
    ~Leaky() { delete[] p; delete[] q; }            // ~Leaky 不会运行，p 泄漏
};

#include <memory>
struct Safe {
    std::unique_ptr<int[]> p;
    std::unique_ptr<int[]> q;
    Safe() : p(new int[100]), q(new int[100]) {}    // q 失败时 p 是已构造的子对象，被析构
};
```

`Leaky` 是良构的，只是有资源泄漏。把资源交给子对象管理（`Safe`），¶3 就会自动完成清理。这是 RAII 在构造函数中的完整形式：每个子对象只管一份资源。

### 析构函数的子对象必须潜在调用

为了让 ¶3 能够工作，构造函数必须能够调用每个子对象的析构函数。因此 [[class.base.init#14]] 规定，在非委托构造函数中，每个类类型潜在构造子对象的析构函数都是潜在调用的。如果析构函数被删除或不可访问，即使构造函数体根本不可能抛出，程序也非良构：

```cpp title="dtor-needed-by-ctor.cpp" error
struct NoDtor {
    NoDtor() = default;
    ~NoDtor() = delete;
};

struct Holder {
    NoDtor d;
    Holder() {}         // error: 构造函数需要（潜在调用）NoDtor 的析构函数
};
```

### 聚合初始化与数组

¶3.4 与 ¶3.6 让同样的规则适用于没有构造函数的聚合与数组：

```cpp run title="aggregate-partial.cpp" ok
#include <cstdio>

struct M {
    int i;
    M(int x) : i(x) { if (x == 3) throw x; std::printf("+%d ", i); }
    ~M() { std::printf("-%d ", i); }
};

struct Agg { M a, b, c; };

int main() {
    try { Agg g{1, 2, 3}; } catch (int) { std::printf("| agg\n"); }
    try { M arr[4] = {1, 2, 3, 4}; } catch (int) { std::printf("| array\n"); }
}
```

输出：`+1 +2 -2 -1 | agg` 和 `+1 +2 -2 -1 | array`，已构造的元素按逆序析构。

### 注 1：引用成员与生命周期延长

注 1 指出一个推论：若这样的对象有一个延长了临时对象生命周期的引用成员，那么随着对象初始化失败，引用成员的生命周期结束，临时对象的生命周期实际上并没有延长，它会被销毁。

```cpp run title="ref-member-temp.cpp" ok
#include <cstdio>

struct Tmp { ~Tmp() { std::puts("~Tmp"); } };
struct Thrower { Thrower() { throw 0; } };

struct Agg {
    const Tmp& r;      // 聚合初始化时绑定到临时对象 ⇒ 生命周期延长（[class.temporary]）
    Thrower t;
};

int main() {
    try { Agg a{Tmp{}, {}}; (void)a; } catch (int) { std::puts("caught"); }
}
```

输出 `~Tmp` 然后 `caught`：临时对象在回溯中被销毁，没有活到 `a` 的作用域结束。

## 析构中途失败（¶3 后半）

¶3 的后半处理析构函数以异常终止的情形（只可能发生在 `noexcept(false)` 的析构函数上）：在析构函数体执行之后本应进行的每一个析构调用（[[class.dtor#13]]：成员、直接基类、对完整对象还有虚基类），只要还没开始，就照常执行。注 3 说明，若析构函数是为完整对象调用的，这包括虚基类子对象。

换句话说，析构函数体抛出异常不会让成员和基类泄漏。

```cpp run title="dtor-throws.cpp" ok
#include <cstdio>

struct M { const char* n; ~M() { std::printf("-%s ", n); } };
struct B { ~B() { std::printf("~B "); } };

struct D : B {
    M m1{"m1"}, m2{"m2"};
    ~D() noexcept(false) { std::printf("~D-body "); throw 0; }
};

int main() {
    try { D d; } catch (int) { std::printf("| caught\n"); }
}
```

输出：`~D-body -m2 -m1 ~B | caught`。

¶3 最后两句对两半都适用：

- 子对象按构造完成的逆序销毁；
- 这些销毁先于进入构造函数/析构函数的 function-try-block 的 handler（如果有）。[[except.handle#11]] 规定在 handler 里访问成员是 UB，原因正在于此：进入 handler 时它们已经被销毁了。

## 委托构造函数（¶4）

¶3 开头排除了委托构造函数的情形，由 ¶4 单独规定：若委托构造函数（[[class.base.init#6]]）的函数体的复合语句以异常退出，则调用该对象的析构函数。这一销毁先于进入该对象某个委托构造函数的 function-try-block 的 handler。

原因在于，目标构造函数（最终是某个非委托构造函数）一返回，所有基类和成员都已经初始化完毕（[[class.base.init#6]]：目标构造函数返回后才执行委托构造函数体）。此时对象在结构上已经完整，可以安全地运行它的析构函数；如果再按 ¶3 逐个析构子对象，反而会漏掉析构函数体里的清理逻辑。所以委托构造函数体里抛出时，标准选择调用整个对象的析构函数：

```cpp run title="delegating.cpp" ok
#include <cstdio>

struct S {
    int* p;
    explicit S(int n) : p(new int[n]) { std::puts("target ctor done"); }
    S() : S(4) {                    // 委托给 S(int)
        std::puts("delegating body");
        throw 42;                   // 对象已完整构造 ⇒ 调用 ~S()
    }
    ~S() { std::puts("~S frees p"); delete[] p; }
};

int main() {
    try { S s; } catch (int) { std::puts("caught"); }
}
```

输出：`target ctor done`、`delegating body`、`~S frees p`、`caught`。用 `-fsanitize=address` 运行没有泄漏报告。

由此得到一个有用的惯用法：先委托给一个不会失败的构造函数，让对象进入可析构状态，再在委托构造函数体里做可能失败的工作。失败时析构函数会负责清理，不必写 function-try-block。

若异常发生在目标构造函数内部，则对目标构造函数应用 ¶3（析构已构造的子对象），对象的析构函数不会被调用。

## `new` 表达式与内存归还（¶5）

¶5（注 4）提醒：若对象是由 *new-expression* 分配的，则调用匹配的释放函数（如果有）释放对象占用的存储。规范性规则在 [[expr.new#27]]：如果初始化因异常终止且能找到合适的释放函数，就调用它释放内存，然后异常在 *new-expression* 的上下文中继续传播；如果找不到无歧义的匹配释放函数，内存不会释放。

```cpp run title="new-dealloc.cpp" ok
#include <cstdio>
#include <new>

struct X {
    X() { throw 1; }
    static void* operator new(std::size_t n) {
        std::puts("X::operator new");
        return ::operator new(n);
    }
    static void operator delete(void* p) noexcept {
        std::puts("X::operator delete");
        ::operator delete(p);
    }
};

int main() {
    try { new X; } catch (int) { std::puts("caught"); }
}
```

输出：`X::operator new`、`X::operator delete`、`caught`。

对定位 new（placement new）而言，匹配的释放函数是参数列表对应的定位 `operator delete`（[[expr.new#30]]）。定位 `operator delete` 只在这一种场合被调用，即构造函数抛出异常时。对标准的 `::new (p) T`，对应的 `operator delete(void*, void*)` 什么也不做。

## 实现视角

!!! impl "编译器如何实现栈回溯"
    在 Itanium C++ ABI（GCC、Clang 在 Linux/macOS 上使用）下，编译器为每个可能抛出的调用点生成一个**着陆点**（landing pad），这是一小段代码，负责调用本帧中已构造对象的析构函数，然后调用 `_Unwind_Resume` 继续回溯。哪段代码对应哪个调用点，记录在只读的 LSDA 表（`.gcc_except_table`）里。已构造完成这一运行时状态由编译器静态地编码成调用点区间：调用点在 `a` 构造之后、`b` 构造之前，着陆点就只析构 `a`。详见 [[toolchain/exception-implementation]]。

    构造函数中的部分构造（¶3）以同样方式实现：构造函数自身为每个子对象的初始化调用点生成着陆点，析构此前已初始化的子对象。

## 陷阱

!!! pitfall "在构造函数失败时期待析构函数运行"
    非委托构造函数抛出时，析构函数不运行。所有在构造函数体里获取、只由析构函数释放的资源都会泄漏。解法是让每份资源成为一个子对象（`unique_ptr`、`vector` 等），或使用 ¶4 的委托构造技巧。

!!! pitfall "以为 `catch` 之外的对象会被析构"
    栈回溯只销毁自进入（接住异常的）try 块以来构造的自动对象。异常被某个内层 handler 接住时，外层作用域的对象不受影响。这本是理所当然的，但有人会误以为异常会把整个栈清空。

## 思考题

!!! question "思考题 1"
    下面 `U` 的构造函数抛出异常时，`s` 会被析构吗？`i` 呢？

    ```cpp
    struct U {
        union { std::string s; int i; };
        U() : s("hello") { throw 0; }
        ~U() {}
    };
    ```

<details markdown="1">
<summary>答案</summary>

`s` 会被析构。`s` 是匿名联合体的成员，因此是 `U` 的变体成员；它被 `U` 的 *mem-initializer* 显式指名，其初始化由 [[class.base.init]] 规定并且已经完成，所以属于已知已初始化的子对象（注 2 明确说可以包括这样的变体成员）。`i` 未被指名，也没有默认成员初始化器，不是已知已初始化的，自然谈不上析构。

¶3 排除的 anonymous union member 指的是 `U` 中那个无名的匿名联合体对象本身：它的隐式析构函数因为 `std::string` 成员而被删除，不可能也不应该被调用。

本机 Clang 23 的行为与此一致：把 `std::string` 换成一个析构时打印的类型，可以看到它的析构函数在异常传播中被调用。

如果没有这条规则，`U` 的构造函数在 `s` 初始化之后抛出时，`s` 持有的资源就会泄漏，而程序员没有任何办法在构造函数外部补救（析构函数 `~U()` 不会运行）。
</details>

!!! question "思考题 2"
    委托构造函数链 `A() : A(1) {}`、`A(int) : A(1, 2) { throw 0; }`、`A(int, int) { }`。异常在中间那个构造函数体中抛出，会调用 `~A()` 吗？

<details markdown="1">
<summary>答案</summary>

会。`A(int)` 本身是委托构造函数（委托给 `A(int, int)`），¶4 适用于委托构造函数的函数体以异常退出的情形：目标构造函数 `A(int, int)` 已经返回，对象已完整构造，所以调用 `~A()`。之后异常继续从 `A()` 的委托中传播出去（`A()` 若有 function-try-block，其 handler 在 `~A()` 之后进入）。
</details>

## 小结

| 情形 | 析构什么 | 出处 |
|---|---|---|
| 异常穿过一个块作用域 | 进入 try 块以来已构造的自动对象，逆序 | ¶2 |
| `return` 之后析构局部变量时抛出 | 还要析构已构造的返回对象 | ¶2 |
| 非委托初始化中途抛出 | 已知已初始化且已完成初始化的子对象（含被显式指名的变体成员，不含匿名联合体对象本身）；对象自身析构函数不调用 | ¶3 |
| 析构函数体抛出 | 照常析构尚未开始析构的成员与基类 | ¶3 |
| 委托构造函数体抛出 | 调用对象的析构函数 | ¶4 |
| 由 `new` 创建的对象构造失败 | 调用匹配的（定位）释放函数 | ¶5，[[expr.new#27]] |
