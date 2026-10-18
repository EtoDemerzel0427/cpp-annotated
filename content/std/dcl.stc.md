---
title: 存储类说明符
summary: static、thread_local、extern、mutable 四个存储类说明符的组合限制与适用对象；同一实体的所有声明必须给出相同链接；auto 与 register 的退役
status: done
papers: P0001R1
related: basic.stc, basic.link, basic.def, class.static, class.union.anon, dcl.inline
tags: 声明, 存储期, 链接
updated: 2026-10-17
---

**存储类说明符**（*storage-class-specifier*）这个名字是从 C 继承来的，但在今天的 C++ 中有点名不副实：四个说明符里，`static` 和 `thread_local` 确实决定**存储期**（[[basic.stc]]），`extern` 主要影响**链接**与"是否为定义"（[[basic.link]]、[[basic.def]]），`mutable` 则与存储毫无关系——它只是允许在 const 对象中修改某个成员。

本节规定这些说明符**能用在哪里、能怎样组合**；它们的语义效果大多由其他条款给出：存储期在 [[basic.stc]]，链接在 [[basic.link]]，静态成员在 [[class.static]]，局部静态变量的初始化在 [[stmt.dcl]]。

## 组合与作用范围（¶1）

¶1 存储类说明符只有四个：`static`、`thread_local`、`extern`、`mutable`。规则：

1. **至多一个**，唯一的例外是 `thread_local` 可以和 `static` 或 `extern` 同时出现。
2. **`thread_local` 必须一致**：变量的任一声明有 `thread_local`，则所有声明都必须有。
3. **不能与 `typedef` 并存**：`typedef static int X;` 非良构——类型别名没有存储期。
4. **声明符列表不能为空**（命名空间作用域的匿名联合体除外）：存储类说明符修饰的是被声明的变量/函数，没有声明符就没有修饰对象。
5. **只作用于声明符声明的名字**，不作用于其他说明符顺带声明的名字。

```cpp run ok
extern thread_local int counter;           // OK: thread_local + extern
thread_local int counter = 0;              // OK: 所有声明都有 thread_local
static struct Point { int x, y; } origin;  // static 作用于 origin，不作用于 Point（类没有存储期）
static union { int u_i; float u_f; };      // 例外：匿名联合体可以没有声明符
int main() { return counter + origin.x + u_i; }
```

```cpp error
thread_local int x;
extern int x;                  // error: x 的声明必须都带 thread_local
typedef static int SI;         // error: typedef 不能和存储类说明符组合
static struct T { };           // error: 没有声明符（Clang 只给警告）
```

第 5 条的意义在于：`static struct Point {...} origin;` 中 `static` 不会让类 `Point` 获得什么"内部链接"——类型的链接由别的规则决定（[[basic.link#4]]）。

Note 1 提醒：显式特化和显式实例化对存储类说明符另有限制（[[temp.expl.spec]]：显式特化不能写 `static` 之类；[[temp.explicit]]：显式实例化不能带存储类说明符）。

¶2（注）：块作用域中、或作为函数参数声明的变量，若没有存储类说明符，默认具有**自动存储期**。C++11 之前可以用 `auto` 显式写出这一点，`register` 则是对编译器的寄存器分配提示。

## thread_local（¶3）

¶3 `thread_local` 表示实体具有**线程存储期**（[[basic.stc.thread]]）：每个线程有自己的一份对象，在线程开始时（或首次使用前）初始化，线程结束时销毁。它只能用于：

- 命名空间作用域或块作用域的**变量**；
- **结构化绑定声明**（作用于其引入的隐藏变量）；
- **静态数据成员**。

不能用于非静态数据成员、函数、函数参数。

在块作用域中，若 `thread_local` 没有伴随其他存储类说明符，则**隐含 `static`**：`void f() { thread_local int n; }` 与 `static thread_local int n;` 等价。这条规则的意义在于：块作用域的 `thread_local` 变量不是"每次进入块时创建"的自动变量，而是"每个线程一个、跨调用持续存在"——这与 `static` 局部变量的生命周期模型一致，只是按线程复制。

```cpp run ok
#include <thread>
#include <cstdio>
struct S { static thread_local int per_thread; };
thread_local int S::per_thread = 0;          // 静态数据成员的定义也要带 thread_local

int next_id() {
    thread_local int id = 0;                 // 隐含 static：每线程一份，跨调用保留
    return ++id;
}

int main() {
    next_id(); next_id();
    std::thread t([] { std::printf("worker: %d\n", next_id()); });   // 新线程从 1 开始
    t.join();
    std::printf("main: %d\n", next_id());                             // 3
}
```

```cpp error
struct S { thread_local int m; };     // error: 非静态数据成员不能是 thread_local
thread_local void f();                // error: 函数不能是 thread_local
```

!!! impl "实现视角：TLS 与包装函数"
    主流平台用操作系统/动态链接器提供的 TLS 机制实现 `thread_local`（ELF 的 `.tbss`/`.tdata` 段，访问时可能经由 `__tls_get_addr`）。具有**动态初始化**或非平凡析构的 `thread_local` 变量更复杂：Itanium C++ ABI 为它生成一个**线程局部包装函数**（mangled 名以 `_ZTW` 开头）和一个**初始化函数**（`_ZTH`），跨 TU 访问这类变量时，调用方会先调用包装函数确保本线程的初始化已完成。因此访问外部的 `thread_local` 变量可能比访问普通全局变量贵得多；若能保证常量初始化，用 `constinit thread_local`（[[dcl.constinit]]）可以让编译器省掉这层包装。

## static（¶4）

¶4 `static` 只能用于：变量或函数的声明、结构化绑定声明、匿名联合体的声明。并且：

- **块作用域中不能有 `static` 函数声明**；
- **函数参数不能是 `static`**；
- 用于变量时，赋予它**静态存储期**（[[basic.stc.static]]），除非同时有 `thread_local`（此时是线程存储期）；
- 用于类成员时，效果见 [[class.static]]；
- 对链接的影响见 [[basic.link]]。

`static` 是 C++ 中含义最"多"的关键字之一，但从标准的角度看，它作为存储类说明符只做两件事——**赋予静态存储期**（对变量）和**参与链接的判定**（命名空间作用域）。各种"含义"其实是这两件事在不同作用域的组合：

| 位置 | `static` 的效果 | 依据 |
|---|---|---|
| 命名空间作用域的变量 | 内部链接（存储期本来就是静态的） | [[basic.link#3]] |
| 命名空间作用域的函数 | 内部链接 | [[basic.link#3]] |
| 块作用域的变量 | 静态存储期；首次经过声明时初始化 | [[basic.stc.static]]、[[stmt.dcl]] |
| 块作用域的函数声明 | **非良构** | ¶4 |
| 类的数据成员 | 静态数据成员：不属于任何对象；链接同类名 | [[class.static.data]] |
| 类的成员函数 | 静态成员函数：没有 `this` | [[class.static.mfct]] |
| 函数参数 | **非良构** | ¶4 |
| 匿名联合体（命名空间作用域） | 外部链接的命名空间中**必须**写 `static` | [[class.union.anon#2]] |

```cpp error
void f() {
    static void g();         // error: 块作用域不能声明 static 函数
}
void h(static int x);        // error: 参数不能是 static
union { int a; float b; };   // error: 全局命名空间（外部链接）中的匿名联合体必须是 static
```

为什么块作用域不能有 `static` 函数声明？块作用域的函数声明总是指向某个命名空间作用域的函数（[[basic.link]] 中关于块作用域 `extern` 声明的规则），它的链接从先前的声明继承；在块里写 `static` 想表达"内部链接"，却又无法在块内**定义**这个函数（函数定义不是块声明，[[dcl.pre#1]]），这种写法没有用处，C 和 C++ 都禁止。

## extern（¶5、¶7）

¶5 `extern` 只能用于变量或函数的声明，**不能**用于类成员或函数参数。链接效果见 [[basic.link]]。

Note 3 区分了 `extern` 关键字的另外两种用法——`extern template`（显式实例化声明，[[temp.explicit]]）和 `extern "C"`（链接规格，[[dcl.link]]）——在那里它**不是**存储类说明符。

`extern` 的效果可以归纳为三条（分布在不同条款中）：

1. **使声明不成为定义**——但前提是**没有初始化器**（[[basic.def#2]]，¶2.2）。`extern int x = 1;` 是定义。
2. **影响链接**：命名空间作用域的 const 变量默认内部链接，加 `extern` 后变为外部链接（[[basic.link#3]]）；若之前的声明是内部链接，`extern` 声明继承之（¶6 例子中的 `b`）。
3. **在块作用域中引用外部实体**：块作用域的 `extern int n;` 的**目标作用域**是最内层的外围命名空间，只是名字绑定在块作用域中（[[dcl.meaning.general#3.5]]）——它声明的是命名空间成员，而不是局部变量。这样的声明**不能带初始化器**：所有主流实现都拒绝（C++20 及更早的标准在 [dcl.init] 中有一句明文：具有链接的块作用域标识符的声明不得有初始化器）。

```cpp run ok
extern const int limit = 100;   // 定义：有初始化器；extern 使 const 变量获得外部链接
extern int later;               // 声明，不是定义
int later = 5;                  // 定义
int use() {
    extern int later;           // 块作用域 extern：指向全局的 later
    return later + limit;
}
int main() { return use() - 105; }
```

```cpp error
struct X { extern int a; };     // error: 不能用于类成员
void f() { extern int y = 1; }  // error: 块作用域 extern 声明不能有初始化器
```

!!! tip "`extern` + 初始化器的警告"
    `extern int x = 1;` 是合法的定义，但 Clang 会给出 `-Wextern-initializer` 警告，因为在**非 const** 变量上这么写通常是误会（`extern` 是多余的）。对 `extern const` 来说这是惯用法，不必理会。

¶7 尚未定义的类（不完整类型）可以用在 `extern` 声明中，但只能以不需要完整类型的方式使用：

```cpp error
struct S;
extern S a;           // OK: 声明一个不完整类型的变量（不是定义，所以无需完整类型）
extern S f();         // OK
extern void g(S);     // OK
void h() {
    g(a);             // error: 按值传递需要 S 完整（复制初始化参数）
    f();              // error: 调用返回不完整类型的函数
}
```

为什么允许 `extern S a;`？因为它不是定义，不需要知道大小（[[basic.def#5]] 只要求**定义**的对象类型完整）。但 `&a` 是可以的——取地址不需要完整类型。

## 所有声明的链接必须一致（¶6）

¶6 同一实体的所有声明必须给出**相同的链接**。Note 4 补充：某些声明的链接受**先前声明**影响；重载的函数是不同的实体，彼此独立。

标准的长例子总结了"链接继承"的方向性——**先 `static`，后无说明符/`extern`/`inline` 是可以的（继承内部链接）；先外部，后 `static` 是错的**：

| 先 | 后 | 结果 |
|---|---|---|
| `static char* f();` | `char* f() {…}` | OK，内部链接 |
| `char* g();` | `static char* g() {…}` | **error**：链接不一致 |
| `void h();` | `inline void h();` | OK，外部链接（`inline` 不影响链接） |
| `static void n();` | `inline void n();` | OK，内部链接 |
| `static int a;` | `int a;` | **error**：两个定义（`int a;` 是定义，[[basic.def.odr]]） |
| `static int b;` | `extern int b;` | OK，`b` 仍是内部链接 |
| `int c;` | `static int c;` | **error**：链接不一致 |
| `extern int d;` | `static int d;` | **error**：链接不一致 |

为什么"先内部、后 `extern`"可以，反过来不行？`extern` 的含义是"指向一个已知的实体，若之前有可见声明则沿用其链接"（[[basic.link]]）——它是"从属"的；而 `static` 是"主动声明内部链接"。允许后者覆盖前者会让同一个名字在 TU 前半部分和后半部分指向不同的实体。

```cpp run ok
static int counter;          // 内部链接
extern int counter;          // 仍是内部链接（继承）
static void helper();
void helper() { }            // 仍是内部链接
void f(int);                 // 外部链接
static void f(char);         // OK：重载是不同实体，各自的链接互不影响
static void f(char) { }
int main() { helper(); f('x'); return counter; }
```

`static int a; int a;` 一行特别值得注意：报错的理由不是"链接不一致"（`int a;` 会继承内部链接），而是 `int a;` 是第二个**定义**。Clang 的报错文本是"non-static declaration follows static declaration"，但标准中的规则是 ODR。

## mutable（¶8–9）

¶8 `mutable` 只能出现在**非静态数据成员**的声明中，且该成员的类型**既不是 const 限定的，也不是引用类型**。

```cpp error
class X {
    mutable const int* p;     // OK: p 本身不是 const（它指向 const int）
    mutable int* const q;     // error: q 本身是 const
    mutable int& r;           // error: 引用类型
    mutable static int s;     // error: 不能和 static 组合（至多一个存储类说明符）
};
```

¶9（注）：`mutable` 抵消了包含它的对象的 `const`，使得即使对象是 const，这个成员也能被修改（[[basic.type.qualifier]]、[[dcl.type.cv]]）。具体地说：通过 const 对象访问 mutable 成员，得到的左值**不是** const 的（[[expr.ref]]），而修改它也不是 UB——[[dcl.type.cv#4]] 的"修改 const 对象是 UB"不适用，因为 mutable 成员**不是 const 对象**。

为什么禁止 `mutable` 用于 const 成员和引用？`mutable const int` 自相矛盾；引用本身不可"修改"（重新绑定），`mutable` 对它没有意义。

```cpp run ok
#include <mutex>
class Cache {
    mutable std::mutex m;          // 典型用法：在 const 成员函数里加锁
    mutable int hits = 0;          // 统计信息、缓存
    int value = 42;
public:
    int get() const {
        std::lock_guard lk(m);     // m 不是 const，可以 lock()
        ++hits;                    // OK
        return value;
    }
};
int main() { const Cache c; return c.get() - 42; }
```

!!! note "lambda 的 `mutable` 不是存储类说明符"
    `[x]() mutable { ++x; }` 中的 `mutable` 是 *lambda-specifier*（[[expr.prim.lambda.general]]），它让闭包的函数调用运算符不是 const 成员函数。语法位置、语义都与本节无关，只是复用了关键字。

## auto 与 register 的退役

!!! history "历史与演进"
    - **C++98/03**：存储类说明符有 `auto`、`register`、`static`、`extern`、`mutable`。`auto` 显式表示自动存储期（与默认相同，几乎无人使用）；`register` 是寄存器分配提示。
    - **C++11**：`auto` 被重新用作占位类型说明符（[[dcl.spec.auto]]），不再是存储类说明符——这是标准里少有的"破坏兼容"的关键字复用，理由是旧用法几乎不存在。`thread_local` 加入。`register` 被弃用。
    - **C++17**：`register` 作为存储类说明符被移除（[[P0001R1]]），但关键字**保留**，以便将来复用。C 语言中 `register` 仍然有效（并禁止对 register 变量取地址）。

```cpp error
void f() {
    register int x = 0;    // error: C++17 起 register 不再是存储类说明符
    auto int y = 0;        // error: C++11 起 auto 不是存储类说明符
}
```

（Clang 对 `register` 的诊断可以用 `-Wno-register` 关闭——这是为了兼容 C 头文件；对块作用域的 `auto int` 只给出 `-Wauto-storage-class` 警告。标准层面两者都是非良构的。）

!!! pitfall "常见误解"
    - "`static` 全局变量和非 static 全局变量的存储期不同"——错。命名空间作用域的变量**本来**就是静态存储期，`static` 只改变链接。
    - "`extern` 声明不能有初始化器"——错。命名空间作用域可以，这样的声明是定义；只有块作用域的 `extern` 声明不能有初始化器。
    - "`const` 全局变量是外部链接"——在 C 里是，在 C++ 里默认是**内部**链接（[[basic.link#3]]），除非加 `extern` 或 `inline`，或位于模块接口中。

!!! summary "小结"
    | 说明符 | 适用 | 主要效果 | 组合 |
    |---|---|---|---|
    | `static` | 变量、函数、结构化绑定、匿名联合体；不能用于块作用域函数和参数 | 静态存储期 / 内部链接 / 静态成员 | 可加 `thread_local` |
    | `thread_local` | 命名空间/块作用域变量、结构化绑定、静态数据成员 | 线程存储期；块作用域隐含 `static` | 可加 `static` 或 `extern`；所有声明都要写 |
    | `extern` | 变量、函数；不能用于成员和参数 | 外部链接 / 非定义声明（无初始化器时） | 可加 `thread_local` |
    | `mutable` | 非 const、非引用的非静态数据成员 | 在 const 对象中可修改 | 不与其他存储类说明符组合 |

    同一实体所有声明的链接必须相同；`static` 后跟 `extern`/无说明符 → 继承内部链接；反之非良构。

!!! question "思考题 1"
    下面的程序是否良构？`x` 有什么链接？

    ```cpp
    namespace {
        int x;
    }
    extern int x;
    ```

<details markdown="1">
<summary>答案</summary>

第二个 `extern int x;` 位于全局命名空间，它声明的是 `::x`，和无名命名空间里的 `(anonymous)::x` 是**不同的实体**（目标作用域不同）。所以这里有两个实体：内部链接的 `(anon)::x`（无名命名空间中的名字有内部链接）和外部链接的 `::x`。程序良构；但此后在全局作用域写 `x` 会导致查找歧义（两个声明都被找到，[[namespace.udir]] 的 using 指令语义），使用时才报错。
</details>

!!! question "思考题 2"
    `struct A { mutable int n; }; const A a{1};` 之后，`const_cast<A&>(a).n = 2;` 和 `a.n = 2;` 分别是什么行为？若把 `mutable` 去掉呢？

<details markdown="1">
<summary>答案</summary>

有 `mutable` 时两者都良构且行为明确：`a.n` 本身就是非 const 左值（[[expr.ref]]），`n` 不是 const 对象，修改不是 UB。去掉 `mutable` 后，`a.n = 2;` 非良构（给 const 左值赋值）；`const_cast<A&>(a).n = 2;` 能编译，但 `a` 是 const 对象，`a.n` 是其 const 子对象，修改它是 UB（[[dcl.type.cv#4]]）。
</details>
