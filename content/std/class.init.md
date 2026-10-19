---
title: 初始化（类对象）
summary: 类对象有哪几种初始化写法，各自交给哪条规则处理；类对象数组的元素按下标顺序构造、逆序析构。
status: done
covers: class.init.general, class.expl.init
related: dcl.init, dcl.init.list, dcl.init.aggr, class.base.init, class.ctor, class.default.ctor, class.copy.elision, except.ctor
tags: 初始化, 构造函数, 数组
updated: 2026-10-19
---

!!! tldr
    - 类对象没有初始化器时默认初始化，初始化器是 `()` 时值初始化，细节都在 [[dcl.init]]。`T x();` 声明的是函数，不是值初始化。
    - `T x(args)` 是直接初始化，`T x = e` 是复制初始化，`T x{...}` 和 `T x = {...}` 是列表初始化。复制初始化不考虑 `explicit` 构造函数；复制列表初始化若选中 `explicit` 构造函数则非良构。
    - 声明里的 `=` 不是赋值，`operator=` 与初始化无关。
    - 类对象数组的元素按下标顺序构造、按相反顺序析构；某个元素构造时抛出异常，已构造的元素逆序析构。
    - 花括号里的初始化器比数组元素少时，剩余元素从空列表初始化，因此需要默认构造函数。

[[class.init]] 下有六个子条款。本页讲其中最基础的两个：[[class.init.general]] 和 [[class.expl.init]]。构造函数里怎样初始化基类和成员见 [[class.base.init]]，继承的构造函数见 [[class.inhctor.init]]，构造和析构期间对象处于什么状态见 [[class.cdtor]]，复制消除见 [[class.copy.elision]]。

## 没有初始化器，或者写 `()`（[class.init.general] ¶1–¶2）

```cpp run title="init-empty.cpp" ok
#include <cstdio>

struct Agg { int a; int b; };
struct User { int a; User() {} };
struct Defaulted { int a; Defaulted() = default; };

int main() {
    Agg* p1 = new Agg();              // 值初始化：清零
    User* p2 = new User();            // 值初始化：只调用 User()
    Defaulted* p3 = new Defaulted();  // 值初始化：清零
    std::printf("%d %d %d\n", p1->a, p1->b, p3->a);  // 0 0 0
    // p2->a 没有被初始化，这里不读它
    delete p1; delete p2; delete p3;
}
```

¶1 类类型对象（或其数组）没有初始化器，或者初始化器是 `()` 时，按 [[dcl.init]] 初始化。前者是**默认初始化**（[[g:default-initialization]]）：对类类型就是选出并调用默认构造函数。后者是**值初始化**（[[g:value-initialization]]）：如果默认构造函数不是用户提供的，先把整个对象清零，再默认初始化；否则直接调用默认构造函数。

所以上例中 `User` 的默认构造函数是用户提供的，`a` 不会被清零。`Defaulted() = default;` 在类内首次声明时就被预置，不算用户提供（[[dcl.fct.def.default]]），值初始化照样先清零。

| 写法 | 初始化方式 |
|---|---|
| `T x;`、`new T` | 默认初始化 |
| `T()`、`new T()`、*mem-initializer* `m()` | 值初始化 |
| `T x{};`、`T{}` | 列表初始化；对有默认构造函数的非聚合类就是值初始化（[[dcl.init.list]]） |

`()` 这种形式不能用在变量声明里：`T x();` 声明了一个返回 `T` 的函数（[[dcl.ambig.res]]）。要值初始化一个局部变量，写 `T x{};` 或 `T x = T();`。

¶2 只是指引：类对象可以显式初始化，见 [[class.expl.init]] 和 [[class.base.init]]。

## 圆括号与 `=`（[class.expl.init] ¶1）

```cpp run title="complex.cpp" ok
struct complex {
    complex() {}
    complex(double) {}
    complex(double, double) {}
};
complex sqrt(complex, complex) { return {}; }

int main() {
    complex a(1);              // complex(double)
    complex b = a;             // 复制构造函数
    complex c = complex(1, 2); // c 就是这个 prvalue 的结果对象
    complex d = sqrt(b, c);    // d 是函数调用的结果对象
    complex e;                 // complex()
    complex f = 3;             // complex(double)
    complex g = {1, 2};        // complex(double, double)
    (void)d; (void)e; (void)f; (void)g;
}
```

¶1 类对象可以用圆括号里的 *expression-list* 初始化，这些表达式就是构造函数的实参，这是**直接初始化**（[[g:direct-initialization]]）。也可以用 `= 表达式` 的形式，这是**复制初始化**（[[g:copy-initialization]]）。两者的精确语义在 [[dcl.init#15.6]]。对类类型的目标：

- 初始化器是同一类型的 prvalue 时，直接用它初始化目标，不经过复制或移动构造函数（[[dcl.init#15.6.1]]）；
- 直接初始化，或者源类型是同类或派生类的复制初始化，在构造函数中做重载决议；
- 其余的复制初始化，找一个把源类型转换成目标类型的用户定义转换（[[over.match.copy]]），`explicit` 构造函数不参与。

`c`、`d` 两行在 C++17 之前的说法是：先构造一个临时对象，再复制到 `c`、`d`，复制可以省略，但复制构造函数必须可访问。C++17 起 prvalue 不再先变成临时对象，它只是初始化某个结果对象的方式，`c`、`d` 本身就是结果对象，没有复制这一步（[[basic.lval#5]]）。

### `explicit` 构造函数

```cpp title="explicit.cpp" error
struct S {
    explicit S(int) {}
};

S a(1);       // OK：直接初始化
S b{1};       // OK：直接列表初始化
S c = 1;      // error: 不考虑 explicit 构造函数
S d = {1};    // error: 选中了 explicit 构造函数
S e = S(1);   // OK：同类型 prvalue
```

`c` 和 `d` 失败的方式不同。`c` 的复制初始化根本不把 `explicit` 构造函数放进候选集。`d` 的复制列表初始化会把它放进候选集，但如果重载决议选中它，程序非良构（[[over.match.list]]）。当还有其他非 `explicit` 的候选时，这个区别就会改变结果，见文末思考题。

### 声明里的 `=` 不是赋值

```cpp run title="not-assignment.cpp" ok
struct S {
    S(int) {}
    S& operator=(int) = delete;
};

int main() {
    S s = 42;     // OK：复制初始化，调用 S(int)
    // s = 43;    // 这才是赋值：error
    (void)s;
}
```

注 1：重载的赋值运算符（[[over.assign]]）对初始化没有任何影响。`T x = e;` 中的 `=` 是声明语法的一部分。

## 花括号（[class.expl.init] ¶2）

¶2 类对象也可以用花括号初始化列表初始化，这时按列表初始化处理（[[dcl.init.list]]）。对类类型，它大致分三种情况：聚合类做聚合初始化（[[dcl.init.aggr]]），逐个成员复制初始化；有 `std::initializer_list` 构造函数的类优先考虑它；其余情况把花括号里的元素当作构造函数实参做重载决议。三种情况都禁止窄化转换。

标准例 2 里的数组，加上输出：

```cpp run title="array-braced.cpp" ok
#include <cstdio>

struct complex {
    complex()               { std::printf("() "); }
    complex(double)         { std::printf("(d) "); }
    complex(double, double) { std::printf("(d,d) "); }
};

int main() {
    complex v[6] = {1, complex(1, 2), complex(), 2};
    std::puts("");   // (d) (d,d) () (d) () ()
    (void)v;
}
```

`v[0]` 和 `v[3]` 由 `complex(double)` 复制初始化。`v[1]`、`v[2]` 的初始化器是同类型 prvalue，直接初始化元素本身。`v[4]`、`v[5]` 没有对应的初始化器，按 [[dcl.init.aggr]] 从空列表初始化，也就是调用 `complex()`。

```cpp run title="aggr-class-member.cpp" ok
struct complex { complex(double) {} };

struct X {
    int i;
    float f;
    complex c;
} x = {99, 88.8, 77.7};   // c 由 complex(double) 初始化

int main() { (void)x; }
```

`88.8` 是 `double`，转换成 `float` 在这里不算窄化：源是常量表达式，转换后的值在 `float` 的范围内（[[dcl.init.list]]）。注 2 提醒，聚合的初始化列表里可以省略内层花括号，即使成员是带用户定义转换的类类型（[[dcl.init.aggr]]）。

## 没有默认构造函数的类（[class.expl.init] ¶3–¶4）

```cpp title="no-default-ctor.cpp" error
struct NoDef { NoDef(int) {} };

NoDef a(1);              // OK
NoDef b;                 // error: 没有默认构造函数
NoDef arr1[2] = {1};     // error: arr1[1] 需要默认构造
NoDef arr2[2] = {1, 2};  // OK
```

¶3 是一条注：如果 `T` 没有默认构造函数，不写初始化器的 `T` 对象（或数组）声明非良构。这是默认初始化规则的直接推论。

`arr1` 是常见的陷阱。初始化器比元素少时，剩下的元素不是不初始化，而是从空列表初始化，对 `NoDef` 来说这需要默认构造函数。只有完全不写初始化器的 `E arr[3];` 才是逐个元素默认初始化。

¶4 也是一条注，指向静态和线程存储期对象之间的初始化顺序：见 [[basic.start.dynamic]] 和 [[stmt.dcl]]。

## 数组元素的构造顺序（[class.init.general] ¶3）

```cpp run title="array-order.cpp" ok
#include <cstdio>

struct E {
    int id;
    E(int i) : id(i) { std::printf("E(%d) ", id); }
    ~E() { std::printf("~E(%d) ", id); }
};

int main() {
    E arr[3] = {1, 2, 3};   // E(1) E(2) E(3)
    std::puts("");
}                           // ~E(3) ~E(2) ~E(1)
```

¶3 初始化类对象数组时，如果元素由构造函数初始化，就按下标顺序逐个调用构造函数（参见 [[dcl.array]]）。注 1 补充，元素按构造的相反顺序析构。

顺序确定之后，构造函数的副作用（打印、分配资源、注册到全局表）在各实现上就一致了。它也让异常处理有了明确的结果：第 *k* 个元素的构造抛出异常时，前 *k* − 1 个元素已经构造完成，按相反顺序析构（[[except.ctor#3]]）。

```cpp run title="array-throw.cpp" ok
#include <cstdio>
#include <stdexcept>

struct E {
    int id;
    E(int i) : id(i) {
        if (i == 3) throw std::runtime_error("boom");
        std::printf("E(%d) ", id);
    }
    ~E() { std::printf("~E(%d) ", id); }
};

int main() {
    try {
        E arr[4] = {1, 2, 3, 4};
    } catch (const std::exception&) {
        std::puts("caught");   // 之前输出 E(1) E(2) ~E(2) ~E(1)
    }
}
```

`new E[4]{1, 2, 3, 4}` 的结果相同：已构造的元素逆序析构，然后调用对应的释放函数释放存储（[[expr.new]]）。

## 思考题

!!! question "思考题"
    下面三行分别调用 `S` 的哪个构造函数？哪些行非良构？

    ```cpp
    struct S {
        S(int);
        explicit S(long);
        S(const S&);
    };
    S a = 1L;
    S b(1L);
    S c = {1L};
    ```

<details markdown="1">
<summary>答案</summary>

`S a = 1L;` 是复制初始化，源类型 `long` 与 `S` 不同，只考虑非 `explicit` 的转换构造函数，于是用 `S(int)`（`long` 到 `int` 的整型转换）。合法。

`S b(1L);` 是直接初始化，`S(long)` 精确匹配，胜过 `S(int)`。合法。

`S c = {1L};` 是复制列表初始化，`explicit S(long)` 在候选集中且精确匹配，被选中，于是程序非良构（[[over.match.list]]）。`S(int)` 本来可用（`1L` 是常量，转换成 `int` 不算窄化），但改变不了结果。本机 Clang 23 报告 `chosen constructor is explicit in copy-initialization`。
</details>
