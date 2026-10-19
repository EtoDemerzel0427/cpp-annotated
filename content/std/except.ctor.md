---
title: 栈回溯
summary: 异常传向 handler 的途中销毁哪些对象：已构造完成的自动对象按逆序析构；构造到一半失败时只析构已经初始化好的子对象，对象自己的析构函数不运行；委托构造函数体抛出时运行析构函数；new 表达式归还内存。
status: done
related: except.throw, except.handle, except.pre, class.base.init, class.dtor, dcl.init.aggr, dcl.init.general, expr.new, stmt.return, class.inhctor.init, expr.prim.lambda.capture
tags: 异常, 栈回溯, 析构, 构造函数, RAII
updated: 2026-10-19
---

!!! tldr
    - 异常传向 handler 的途中，自进入那个 try 块以来构造完成、尚未销毁的自动对象，按构造完成的逆序析构。这叫栈回溯，是 RAII 的规范依据。
    - 构造函数抛出时，对象自己的析构函数不会运行；已经初始化好的基类和成员会被析构。所以每份资源都应由一个子对象管理。
    - 析构函数体抛出时，成员和基类照常析构，不会泄漏。
    - 委托构造函数的函数体抛出时，对象已经完整构造，标准调用整个对象的析构函数。
    - `new` 表达式里构造函数抛出时，调用匹配的 `operator delete` 归还内存。

## 回溯销毁哪些对象（¶1–¶2）

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
    T c("c");          // 从未构造，也不会析构
}

int main() {
    T outer("outer");  // 在 try 块之外，不参与回溯
    try {
        T t("t");
        f();
    } catch (int) {
        std::printf("| handler ");
    }
    std::printf("| after\n");
}
```

输出 `+outer +t +a +b -b -a -t | handler | after`，最后是 `-outer`。

¶1 控制从抛出点传到 handler 的途中按本节规定销毁对象，这一过程叫**栈回溯**（[[g:stack-unwinding]]，stack unwinding）。

¶2 自进入（接住异常的那个）try 块以来，每个已经构造完成、尚未销毁的自动存储期对象都会被销毁，顺序是构造完成顺序的逆序。try 块之外更早构造的对象不受影响。正在构造中的对象不算构造完成，它的子对象由 ¶3 处理。

无论控制正常离开作用域，还是因异常离开，已构造的对象都会析构，而且只有它们会析构。C++ 不需要 `finally`，靠的就是这一条。

找不到匹配的 handler 时是否回溯栈，由实现定义；查找穿出 `noexcept` 函数时，栈可以只回溯一部分（[[except.terminate#2]]）。

### return 之后抛出：返回对象也要销毁

¶2 第二句处理一种少见的情形：`return` 语句已经构造好返回对象，之后析构局部变量时抛出了异常，这时返回对象也要析构。

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
        return A(3);    // #1：返回对象 A3 构造完成，然后析构 b
    } catch (...) {     //     析构 y 时抛出，开始回溯
    }
    return A(4);        // #2：再次构造返回对象
}

int main() { A r = f(); std::printf("| got A%d\n", r.id); }
```

返回对象在 `return` 的操作数求值时就构造好了，早于局部变量的析构（[[stmt.return]]）。它是 try 块里最后构造完成的对象，所以回溯时最先销毁。按标准输出应为 `A1() A2() A3() ~A2 ~A3 ~A1 A4() | got A4`。

!!! impl "编译器现状"
    本机 Clang 23 的输出是 `A1() A2() A3() ~A2 ~A1 A4() | got A4`，少了 `~A3`，返回对象泄漏了。这是 Clang 长期存在的不符合之处（对应 CWG2176）。因为实现与标准不符，这段代码不标判定。

## 构造到一半失败（¶3）

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
    ~X() { std::printf("~X "); }        // 不会被调用
};

int main() {
    try { X x; } catch (int) { std::printf("| caught\n"); }
}
```

输出 `+Base::m +a -a ~Base -Base::m | caught`。`Base` 和 `a` 已构造完成，被析构；`b` 的构造函数没有完成，`c` 没有开始，都不析构。`X` 的构造函数没有完成，`X` 对象的生存期从未开始（[[basic.life]]），`~X` 不会运行。

¶3 一个对象的初始化（委托构造函数除外，见 ¶4）因异常终止时，对它的每个子对象，只要这个子对象是**已知已初始化**的，并且初始化已经完成，就调用它的析构函数。析构顺序是构造完成的逆序，并且发生在进入构造函数的 function-try-block 的 handler（如果有）之前。

由此可见，在构造函数里 `new` 两个裸指针会泄漏：

```cpp title="ctor-leak.cpp" ok
#include <memory>

struct Leaky {
    int* p;
    int* q;
    Leaky() : p(new int[100]), q(new int[100]) {}   // 第二个 new 抛出时：
    ~Leaky() { delete[] p; delete[] q; }            // ~Leaky 不运行，p 泄漏
};

struct Safe {
    std::unique_ptr<int[]> p;
    std::unique_ptr<int[]> q;
    Safe() : p(new int[100]), q(new int[100]) {}    // q 失败时 p 已构造完成，会被析构
};
```

`Leaky` 是良构的，只是会泄漏。把每份资源交给一个子对象管理，¶3 就会自动完成清理。

### 已知已初始化

**已知已初始化**（[[g:known-to-be-initialized]]，known to be initialized）的子对象，指不是匿名联合体成员、并且初始化由下列条款规定的子对象：

- ¶3.1 构造函数初始化基类和成员（[[class.base.init]]）；
- ¶3.2 预置的拷贝或移动构造函数（[[class.copy.ctor]]）；
- ¶3.3 继承构造函数（[[class.inhctor.init]]）；
- ¶3.4 聚合初始化（[[dcl.init.aggr]]）；
- ¶3.5 求值 lambda 表达式时初始化闭包对象（[[expr.prim.lambda.capture]]）；
- ¶3.6 数组的默认初始化、值初始化或直接初始化（[[dcl.init.general]]）。

加上已知这个限定，是因为有些子对象是否已构造，语言无从知道。典型的是**变体成员**（variant member），也就是联合体的成员：哪个成员是活动的，通常只有程序员清楚。注 2 说明，变体成员只有在被 *mem-initializer* 或指派初始化器显式指名、或者有默认成员初始化器时才算已知已初始化。对完整对象，虚基类子对象也包括在内。

聚合和数组没有构造函数，同样适用这条规则：

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

输出 `+1 +2 -2 -1 | agg` 和 `+1 +2 -2 -1 | array`。

为了让 ¶3 能执行，构造函数必须能调用每个子对象的析构函数。所以 [[class.base.init]] 规定，非委托构造函数会潜在调用每个类类型子对象的析构函数。析构函数被删除或不可访问时，即使构造函数体不可能抛出，程序也非良构：

```cpp title="dtor-needed-by-ctor.cpp" error
struct NoDtor {
    NoDtor() = default;
    ~NoDtor() = delete;
};

struct Holder {
    NoDtor d;
    Holder() {}         // error: 构造函数需要 NoDtor 的析构函数
};
```

注 1 指出一个推论：如果对象有一个引用成员，它延长了某个临时对象的生存期，那么对象初始化失败时，这个引用成员的生存期结束，临时对象也随之销毁：

```cpp run title="ref-member-temp.cpp" ok
#include <cstdio>

struct Tmp { ~Tmp() { std::puts("~Tmp"); } };
struct Thrower { Thrower() { throw 0; } };

struct Agg {
    const Tmp& r;      // 聚合初始化时绑定到临时对象，延长其生存期
    Thrower t;
};

int main() {
    try { Agg a{Tmp{}, {}}; (void)a; } catch (int) { std::puts("caught"); }
}
```

输出 `~Tmp`，然后是 `caught`。

## 析构到一半失败（¶3）

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

输出 `~D-body -m2 -m1 ~B | caught`。

¶3 后半段规定，析构函数因异常终止时，函数体之后本应执行的析构调用（成员、直接基类，对完整对象还有虚基类，见 [[class.dtor]]）中还没开始的，照常执行。所以析构函数体抛出不会让成员和基类泄漏。这只可能发生在 `noexcept(false)` 的析构函数上。

## 委托构造函数（¶4）

```cpp run title="delegating.cpp" ok
#include <cstdio>

struct S {
    int* p;
    explicit S(int n) : p(new int[n]) { std::puts("target ctor done"); }
    S() : S(4) {                    // 委托给 S(int)
        std::puts("delegating body");
        throw 42;                   // 对象已完整构造：调用 ~S()
    }
    ~S() { std::puts("~S frees p"); delete[] p; }
};

int main() {
    try { S s; } catch (int) { std::puts("caught"); }
}
```

输出 `target ctor done`、`delegating body`、`~S frees p`、`caught`，用 `-fsanitize=address` 运行没有泄漏报告。

¶4 委托构造函数（[[class.base.init]]）的函数体以异常退出时，调用对象的析构函数，并且这发生在进入委托构造函数的 function-try-block 的 handler 之前。目标构造函数返回时，所有基类和成员都已初始化，对象在结构上已经完整，运行析构函数是安全的；逐个析构子对象反而会漏掉析构函数体里的清理。

由此得到一个惯用法：先委托给一个不会失败的构造函数，让对象进入可以析构的状态，再在委托构造函数体里做可能失败的工作。失败时析构函数负责清理。如果异常发生在目标构造函数内部，对目标构造函数适用 ¶3，析构函数不运行。

## new 表达式归还内存（¶5）

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

输出 `X::operator new`、`X::operator delete`、`caught`。

¶5 是一条注：对象由 *new-expression* 分配时，调用匹配的释放函数归还存储。规范性的规则在 [[expr.new]]：找不到无歧义的匹配释放函数时，内存不归还。对定位 new，匹配的是参数对应的定位 `operator delete`，它只在这种场合被调用。

## 实现

!!! impl "编译器怎样实现栈回溯"
    在 Itanium C++ ABI 下，编译器为每个可能抛出的调用点生成一段**着陆点**（landing pad）代码，负责析构本帧中已构造的对象，再调用 `_Unwind_Resume` 继续回溯。调用点和着陆点的对应关系记在只读的异常表里。已构造完成这个运行时状态，被编译器静态编码成调用点区间：调用点在 `a` 构造之后、`b` 构造之前，着陆点就只析构 `a`。构造函数里的部分构造用同样的办法实现。详见 [[toolchain/exception-implementation]]。

## 思考题

!!! question "思考题 1"
    下面 `U` 的构造函数抛出时，`s` 会被析构吗？

    ```cpp
    struct U {
        union { std::string s; int i; };
        U() : s("hello") { throw 0; }
        ~U() {}
    };
    ```

<details markdown="1">
<summary>答案</summary>

会。`s` 是匿名联合体的成员，因此是 `U` 的变体成员。它被 *mem-initializer* 显式指名，初始化由 [[class.base.init]] 规定并且已经完成，所以是已知已初始化的（注 2）。`i` 没有被指名，不析构。

¶3 排除的匿名联合体成员，指 `U` 里那个无名的联合体对象本身。它的析构函数因为 `std::string` 成员而被删除，不能调用。本机 Clang 23 的行为与此一致。
</details>

!!! question "思考题 2"
    委托链 `A() : A(1) {}`、`A(int) : A(1, 2) { throw 0; }`、`A(int, int) {}`。中间那个构造函数体抛出时，会调用 `~A()` 吗？

<details markdown="1">
<summary>答案</summary>

会。`A(int)` 本身是委托构造函数，它的目标 `A(int, int)` 已经返回，对象已完整构造，按 ¶4 调用 `~A()`。之后异常继续从 `A()` 传出。
</details>

## 小结

| 情形 | 析构什么 | 出处 |
|---|---|---|
| 异常穿过块作用域 | 进入 try 块以来已构造的自动对象，逆序 | ¶2 |
| `return` 之后析构局部变量时抛出 | 还要析构已构造的返回对象 | ¶2 |
| 非委托初始化中途抛出 | 已知已初始化且初始化已完成的子对象；对象本身的析构函数不运行 | ¶3 |
| 析构函数体抛出 | 尚未开始析构的成员和基类照常析构 | ¶3 |
| 委托构造函数体抛出 | 对象的析构函数 | ¶4 |
| `new` 创建的对象构造失败 | 调用匹配的释放函数 | ¶5，[[expr.new]] |

<details class="fine" markdown="1"><summary>其余条文</summary>

本节的稳定名 `[except.ctor]` 来自早年的标题 Constructors and destructors，现在的标题是 Stack unwinding。

</details>
