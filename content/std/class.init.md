---
title: 初始化（类对象）
summary: 类对象与类对象数组的初始化入口：无初始化器或 () 交给 [dcl.init]；圆括号实参列表、= 形式、花括号列表三种显式初始化；数组元素按下标顺序构造、逆序析构
status: done
covers: class.init.general, class.expl.init
related: dcl.init, dcl.init.list, dcl.init.aggr, class.base.init, class.ctor, class.default.ctor, class.copy.elision, except.ctor
tags: 初始化, 构造函数, 数组
updated: 2026-10-17
---

[[class.init]] 是第 11 章里"初始化"一组条款的总入口：它本身规定的东西很少，主要作用是**分流**——

- 没写初始化器、或者写的是 `()`：去看 [[dcl.init]]（默认初始化 / 值初始化）；
- 写了圆括号实参列表、`= 表达式`、花括号列表：本页 [[class.expl.init]] 给出直觉，精确语义仍在 [[dcl.init]]、[[dcl.init.list]]；
- 在构造函数里初始化基类与成员：[[class.base.init]]；
- 通过继承的构造函数初始化：[[class.inhctor.init]]；
- 构造/析构期间对象处于什么状态：[[class.cdtor]]；
- 什么时候可以省掉复制：[[class.copy.elision]]。

读本页前最好已经知道 [[dcl.init]] 的整体结构：**直接初始化**（direct-initialization）与**复制初始化**（copy-initialization）的区别、默认初始化与值初始化。本页的价值在于把这些规则落到"类对象"这个具体场景上，并补上数组元素的构造顺序。

## 无初始化器与 `()`（[class.init.general] ¶1–¶2）

¶1 当一个（可能 cv 限定的）类类型对象或其数组**没有指定初始化器**，或初始化器的形式是 `()` 时，按 [[dcl.init]] 初始化。具体来说：

| 写法 | [[dcl.init]] 中的归类 | 对类类型 `T` 的效果 |
|---|---|---|
| `T x;` | 默认初始化 | 对 `T` 的默认构造函数做重载决议并调用；平凡默认构造时成员保持不确定/错误值 |
| `new T` | 默认初始化 | 同上 |
| `new T()`、`T()`、成员 `m()` | 值初始化 | 若默认构造函数不是用户提供的，先零初始化再（必要时）默认初始化；否则直接调用默认构造 |
| `T x{};` | 列表初始化 → 对非聚合且有默认构造的类是值初始化 | 见 [[dcl.init.list]] |

注意 `()` 这种形式**不能**用在变量声明里：`T x();` 声明的是一个函数（所谓 most vexing parse，见 [[dcl.ambig.res]]）。所以 ¶1 说的 `()` 只出现在 `T()`、`new T()`、*mem-initializer* `m()` 等语境中。

```cpp run title="init-empty.cpp" ok
#include <cstdio>

struct Agg { int a; int b; };                      // 平凡默认构造
struct User { int a; User() {} };                  // 用户提供的默认构造，不初始化 a
struct Defaulted { int a; Defaulted() = default; };// 不是"用户提供"的

int main() {
    Agg* p1 = new Agg();        // 值初始化：零初始化，a == b == 0
    User* p2 = new User();      // 值初始化：调用 User()，a 不被零初始化
    Defaulted* p3 = new Defaulted();  // 值初始化：先零初始化，a == 0
    std::printf("%d %d %d\n", p1->a, p1->b, p3->a);   // 0 0 0
    // 读 p2->a 将得到错误值（erroneous value，[basic.indet]）——这里不读
    delete p1; delete p2; delete p3;
}
```

这张"用户提供 vs 非用户提供"的区分是 [[dcl.init]] 里值初始化的核心：`Defaulted() = default;` 在类内第一次声明时就被预置，**不是**用户提供的（[[dcl.fct.def.default]]），因此值初始化会先清零。

¶2 只是一个指路牌：类对象（或其数组）可以被显式初始化，见 [[class.expl.init]] 与 [[class.base.init]]。

## 数组元素的构造与析构顺序（[class.init.general] ¶3）

¶3 当类对象数组被初始化（无论显式还是隐式）、且元素由构造函数初始化时，**按下标顺序**逐个调用构造函数（参见 [[dcl.array]]）。注 1 补充：元素的析构按构造的**逆序**进行。

```cpp run title="array-order.cpp" ok
#include <cstdio>

struct E {
    int id;
    E(int i) : id(i) { std::printf("E(%d) ", id); }
    ~E() { std::printf("~E(%d) ", id); }
};

int main() {
    E arr[3] = {1, 2, 3};   // 输出 E(1) E(2) E(3)
    std::puts("");
}                           // 输出 ~E(3) ~E(2) ~E(1)
```

为什么要规定顺序？两个原因：

1. **可观察性**：构造函数可能有副作用（打印、分配资源、注册到全局表），顺序必须确定，程序才可移植。
2. **异常安全**：若第 *k* 个元素的构造抛出异常，已经构造好的前 *k* − 1 个元素必须被析构（[[except.ctor#3]] 第 3.6 项与 [[dcl.init.aggr]]），而"逆序析构"只有在构造顺序确定时才有意义。

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
        std::puts("caught");    // 先输出 E(1) E(2) ~E(2) ~E(1)，再 caught
    }
}
```

`new E[n]{...}` 的情形完全相同：已构造的元素逆序析构后，再调用匹配的释放函数（[[expr.new]]）。

## 显式初始化：圆括号与 `=`（[class.expl.init] ¶1）

¶1 类对象可以用两种"非花括号"形式显式初始化：

- **圆括号实参列表** `T x(a, b, c);`：*expression-list* 被当作构造函数的**实参列表**，通过重载决议（[[over.match.ctor]]）选出构造函数。这是直接初始化。
- **`=` 形式** `T x = e;`：单个 *assignment-expression*。这是复制初始化。

至于两者的精确差别，标准只说"直接初始化或复制初始化语义适用，见 [[dcl.init]]"。按 [[dcl.init#15.6]]，对类类型目标：

- 若初始化器是**同类型的 prvalue**，直接用它初始化目标对象——不调用任何复制/移动构造函数（[[dcl.init#15.6.1]]，C++17 的"保证复制消除"，详见 [[class.copy.elision]]）；
- 若是直接初始化，或复制初始化但源类型是同类或派生类，**考虑构造函数**（包括 `explicit` 的仅限直接初始化）；
- 否则（复制初始化且源类型不同），考虑能把源类型转换为目标类型的**用户定义转换序列**（转换构造函数与转换函数，[[over.match.copy]]），`explicit` 构造函数不参与。

标准的例子改编如下（每行注释说明调用了什么）：

```cpp run title="complex.cpp" ok
struct complex {
    complex() {}
    complex(double) {}
    complex(double, double) {}
};

complex sqrt(complex, complex) { return {}; }

int main() {
    complex a(1);              // 直接初始化：调用 complex(double)，实参 1 转换为 double
    complex b = a;             // 复制初始化：调用（隐式的）复制构造函数
    complex c = complex(1, 2); // 初始化器是同类型 prvalue：c 就是 complex(1,2) 的结果对象，没有复制
    complex d = sqrt(b, c);    // d 是 sqrt 调用的结果对象
    complex e;                 // 默认初始化：调用 complex()
    complex f = 3;             // 复制初始化：用转换构造函数 complex(double)
    complex g = {1, 2};        // 复制列表初始化：调用 complex(double, double)
    (void)d; (void)e; (void)f; (void)g;
}
```

注意 `c` 和 `d` 两行：C++17 之前，标准说它们"先构造一个临时对象再复制到 `c`/`d`"，复制可以被省略但复制构造函数必须可访问；C++17 起，prvalue 不再是临时对象，而是"初始化某个结果对象的配方"，`c`、`d` 本身就是结果对象，**根本没有**复制这一步（[[basic.lval#5]]）。

### `explicit` 构造函数：直接 vs 复制初始化的分水岭

```cpp title="explicit.cpp" error
struct S {
    explicit S(int) {}
};

S a(1);       // OK：直接初始化考虑 explicit 构造函数
S b{1};       // OK：直接列表初始化
S c = 1;      // error: 复制初始化不考虑 explicit 构造函数
S d = {1};    // error: 复制列表初始化选中了 explicit 构造函数
S e = S(1);   // OK：初始化器是同类型 prvalue
```

`d` 这一行值得细看：复制列表初始化**会**把 `explicit` 构造函数放进候选集，但如果重载决议**选中**了它，程序非良构（[[over.match.list]]）。这与 `c` 的"根本不考虑"是两种不同的机制——区别会在另有非 explicit 候选时显现出来。

### 赋值运算符与初始化无关

¶1 注 1：重载赋值运算符（[[over.assign]]）**对初始化没有任何影响**。`T x = e;` 中的 `=` 是声明语法的一部分，不是赋值表达式。

```cpp run title="not-assignment.cpp" ok
struct S {
    S(int) {}
    S& operator=(int) = delete;   // 禁止赋值
};

int main() {
    S s = 42;     // OK：这是复制初始化，调用 S(int)，与 operator= 无关
    // s = 43;    // 这才是赋值：error，使用了被删除的函数
    (void)s;
}
```

## 花括号初始化（[class.expl.init] ¶2）

¶2 类对象也可以用 *braced-init-list* 初始化，此时适用**列表初始化**语义（[[dcl.init.list]]）。对类类型，列表初始化的走向取决于类是不是聚合：

- 聚合类：聚合初始化（[[dcl.init.aggr]]），逐个成员复制初始化；
- 有 `std::initializer_list` 构造函数：优先考虑它；
- 否则：把花括号里的元素当作构造函数实参做重载决议，但禁止窄化转换。

标准例 2 的数组：

```cpp run title="array-braced.cpp" ok
#include <cstdio>

struct complex {
    complex()               { std::printf("() "); }
    complex(double)         { std::printf("(d) "); }
    complex(double, double) { std::printf("(d,d) "); }
};

int main() {
    complex v[6] = {1, complex(1, 2), complex(), 2};
    // 输出：(d) (d,d) () (d) () ()
    std::puts(""); (void)v;
}
```

逐元素来看：`v[0]` 和 `v[3]` 用 `complex(double)` 复制初始化；`v[1]`、`v[2]` 的初始化器是同类型 prvalue，直接初始化元素本身；`v[4]`、`v[5]` 没有对应的初始化子句，按 [[dcl.init.aggr]] 从空初始化列表复制初始化——对有默认构造函数的类即值初始化，调用 `complex()`。

标准还给了一个聚合里嵌类成员的例子：

```cpp run title="aggr-class-member.cpp" ok
struct complex { complex(double) {} };

struct X {
    int i;
    float f;
    complex c;
} x = {99, 88.8, 77.7};   // x.i = 99, x.f = 88.8f, x.c 由 complex(double) 初始化

int main() { (void)x; }
```

`88.8` 是 `double` 常量，转换为 `float` 在这里**不是**窄化——因为源是常量表达式且转换后的值在 `float` 的表示范围内（[[dcl.init.list]] 对浮点窄化的例外）。

注 2：对任何聚合，*initializer-list* 中都可以省略内层花括号（brace elision），即使聚合的成员是带用户定义转换的类类型，见 [[dcl.init.aggr]]。

## 没有默认构造函数的类（[class.expl.init] ¶3–¶4）

¶3（注）如果 `T` 是没有默认构造函数的类类型，那么任何不显式提供初始化器的 `T`（或其数组）对象声明都是非良构的。这其实是 [[dcl.init]] 默认初始化规则的直接推论：默认初始化要对默认构造函数做重载决议，找不到就非良构。

```cpp title="no-default-ctor.cpp" error
struct NoDef { NoDef(int) {} };

NoDef a(1);           // OK
NoDef b;              // error: 没有默认构造函数
NoDef arr1[2] = {1};  // error: arr1[1] 需要从 {} 复制初始化，找不到合适的构造函数
NoDef arr2[2] = {1, 2};  // OK
```

`arr1` 是一个常见的坑：数组初始化器比元素少时，剩余元素不是"不初始化"，而是从空列表初始化——对 `NoDef` 而言就需要默认构造函数。

¶4（注）静态/线程存储期对象之间的初始化顺序，见 [[basic.start.dynamic]] 与 [[stmt.dcl]]。

## 陷阱

!!! pitfall "以为 `T x = e;` 会调用 `operator=`"
    声明中的 `=` 永远是复制初始化，不是赋值。复制初始化与直接初始化的唯一差别在于：考虑哪些构造函数/转换函数（`explicit` 的不考虑），以及源类型不同时多出一步用户定义转换。

!!! pitfall "以为数组初始化器不足时剩余元素\"不初始化\""
    聚合初始化中没有对应初始化子句的元素会从其默认成员初始化器或空初始化列表初始化（[[dcl.init.aggr]]）。对类类型，这需要可用的默认构造函数；对标量是零初始化。只有完全没有初始化器的 `E arr[3];` 才是逐元素默认初始化。

!!! pitfall "`T x();` 不是值初始化"
    这是函数声明。值初始化一个局部变量请写 `T x{};` 或 `T x = T();`。

## 思考题

!!! question "思考题 1"
    下面每一行分别调用了 `S` 的哪些构造函数？哪些行非良构？

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

- `S a = 1L;`：复制初始化，源类型 `long` 与 `S` 不同，只考虑非 explicit 的转换构造函数——`S(int)`（`long`→`int` 是整型转换）。合法，调用 `S(int)`。C++17 起没有额外的复制构造（转换构造函数的调用是一个 prvalue，直接初始化 `a`）。
- `S b(1L);`：直接初始化，候选包括 `S(long)`（精确匹配）与 `S(int)`（转换），选 `S(long)`。合法。
- `S c = {1L};`：复制列表初始化，`explicit S(long)` **在**候选集中，且它是精确匹配，被选中——因此非良构（[[over.match.list]]）。即使 `S(int)` 本可以用（`1L` 是常量且值可表示为 `int`，不是窄化），也救不了。
</details>

!!! question "思考题 2"
    `struct A { A(); ~A(); }; A arr[3];` 中，若第二个元素的构造函数抛出异常，会调用几次析构函数？如果 `arr` 是 `new A[3]` 呢？

<details markdown="1">
<summary>答案</summary>

都只调用 1 次（析构 `arr[0]`）。¶3 规定按下标顺序构造，[[except.ctor#3]] 规定已完成初始化的元素按逆序析构。`new A[3]` 的情形，析构 `arr[0]` 之后还会调用 `operator delete[]` 释放存储（[[expr.new]]）。
</details>

## 小结

| 初始化器 | 语义 | 主要规则所在 |
|---|---|---|
| 无 | 默认初始化 | [[dcl.init]] |
| `()`（仅 `T()`、`new T()`、`m()`） | 值初始化 | [[dcl.init]] |
| `(a, b, ...)` | 直接初始化：实参列表交给构造函数重载决议 | [[dcl.init]]、[[over.match.ctor]] |
| `= e` | 复制初始化：不考虑 `explicit`；同类型 prvalue 直接初始化目标 | [[dcl.init]]、[[over.match.copy]] |
| `{...}` / `= {...}` | 列表初始化：聚合 / `initializer_list` / 构造函数，禁止窄化 | [[dcl.init.list]]、[[dcl.init.aggr]] |
| 数组元素 | 按下标顺序构造，逆序析构 | [class.init.general] ¶3 |
