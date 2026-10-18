---
title: const_cast
summary: const_cast 只改变 cv 限定：相似的对象指针/数据成员指针之间、以及对应的左值/亡值引用之间的转换；类与数组 prvalue 的实质化；"去掉常量性"（casts away constness）的精确定义及其对其他转换的约束；修改 const 对象为何是 UB
status: draft
related: expr.static.cast, expr.reinterpret.cast, expr.dynamic.cast, expr.cast, conv.qual, dcl.type.cv, basic.type.qualifier, topics/casts
tags: 类型转换, const, cv 限定, UB
updated: 2026-10-17
---

`const_cast` 是职责最单一的具名转换：**只改 cv 限定（`const`、`volatile`），别的一概不改**。它能去掉 `const`，也能加上 `const`；能作用于多级指针的任意层；但不能改变类型本身（`int*` 不能变 `long*`），也不能用于函数指针和成员函数指针。

本节同时承担另一个职责：定义**[[g:casts-away-constness|"去掉常量性"]]**（casts away constness）这个术语（¶6–¶7）。`static_cast`、`reinterpret_cast`、`dynamic_cast` 都"不能去掉常量性"，它们的这条限制正是引用这里的定义。

最重要的一点：`const_cast` 本身**永远不是 UB**；UB 来自之后**通过结果修改一个 const 对象**（[[dcl.type.cv]]）。

## 结果与值类别（¶1–2）

¶1：`const_cast<T>(v)` 的结果类型是 `T`。

- `T` 是**对象**的左值引用 ⇒ lvalue；
- `T` 是**对象**的右值引用 ⇒ xvalue；
- 否则 ⇒ prvalue，并对 `v` 施行左值到右值、数组到指针、函数到指针转换。

除了 ¶4.3 规定的情形，**不**对 `v` 施行临时量实质化。可以用 `const_cast` 显式完成的转换列于下文，**不得**用它进行其他转换。

注意 ¶1 只提到"对象的"引用：`const_cast` 根本不适用于函数引用。

¶2（注 1）：在本节的限制下，表达式可以用 `const_cast` 转换为其自身的类型。

## 指针与数据成员指针（¶3）

¶3：对两个**相似的**（[[conv.qual]]）对象指针类型或数据成员指针类型 `T1`、`T2`，若在二者的**限定分解**（qualification-decomposition）中，每一层的 `P1i` 与 `P2i` 都**相同**（即只有各层的 cv 不同），则 `T1` 类型的 prvalue 可以用 `const_cast` 显式转换为 `T2`。

- 空指针 / 空成员指针 ⇒ 空指针 / 空成员指针；
- 否则结果指向与 `v` **相同的对象**（或其末尾之后），或指向相同的成员。

"限定分解"把类型拆成 cv0 P0 cv1 P1 … cvn U 的形式（P 是"指针"、"`C` 的成员指针"、"数组"等）。"每层 P 相同"就是说：指针的**层数和种类**不能变，只能改各层的 cv。

```cpp title="const-cast-ptr.cpp" error
struct S { const int cm = 0; };
void fn();

void t(int** pp, const int* const* cpcp, int* ip, volatile int* vp) {
    int** a = const_cast<int**>(cpcp);                 // OK：两层 const 都去掉
    const int** b = const_cast<const int**>(pp);       // OK：const_cast 也可以"加" const，任意层
    int* c = const_cast<int*>(vp);                     // OK：去掉 volatile
    int S::* m = const_cast<int S::*>(&S::cm);         // OK：数据成员指针
    long* d = const_cast<long*>(ip);                   // error: 类型不相似
    void (*f)() = const_cast<void (*)()>(&fn);         // error: 函数指针不在 const_cast 的范围内
    int x = const_cast<int>(*ip);                      // error: 非指针、非引用
    (void)a; (void)b; (void)c; (void)m; (void)d; (void)f; (void)x;
}
```

## 引用（¶4）

¶4：对两个对象类型 `T1`、`T2`，若"指向 `T1` 的指针"能用 `const_cast` 转换为"指向 `T2` 的指针"，那么还可以：

- ¶4.1 `T1` 的**左值** → `T2` 的左值：`const_cast<T2&>`；
- ¶4.2 `T1` 的 **glvalue** → `T2` 的亡值：`const_cast<T2&&>`；
- ¶4.3 若 `T1` 是**类或数组**类型，`T1` 的 **prvalue** → `T2` 的亡值：`const_cast<T2&&>`，此时对 `v` 施行**临时量实质化**。

结果指代与（可能经转换的）操作数**相同的对象**。标准例 1：

```cpp run title="const-cast-ref.cpp" ok
int main() {
    const int ci = 1;
    const int& cr = ci;
    int& r = const_cast<int&>(cr);       // OK：¶4.1（转换本身合法；写入 r 才是 UB）
    struct S { int v; };
    S&& s = const_cast<S&&>(S{1});       // OK：¶4.3，类 prvalue 被实质化
    (void)r;
    return s.v == 1 ? 0 : 1;
}
```

数组 prvalue 的情形是标准例 1：

```cpp title="const-cast-array.cpp"
typedef int* A[3];                  // 3 个 int* 的数组
typedef const int* const CA[3];     // 3 个 const int* const 的数组

auto&& r2 = const_cast<A&&>(CA{});  // OK（按标准）：¶4.3，数组 prvalue 被实质化
```

本机 Clang 拒绝这一行（"const_cast from rvalue to reference type 'A &&'"），即尚未实现 ¶4.3 中数组 prvalue 的情形；按标准它是良构的。

为什么 ¶4.3 只允许类和数组 prvalue？因为标量 prvalue 根本没有 cv（[[expr.prop]]：非类非数组的 prvalue 的 cv 会被丢弃），`const_cast<int&&>(5)` 没有要去掉的东西，标准也就不为它开实质化的口子——它是非良构的。

## 修改的后果（¶5）

¶5（注 2）：取决于对象的类型，通过去掉 `const` 的 `const_cast` 结果所得的指针、左值或数据成员指针进行**写操作**，可能产生未定义行为（[[dcl.type.cv]]）。脚注 50 补充：`const_cast` 并不限于去掉 `const` 的转换。

准确地说，[[dcl.type.cv]] 规定：**修改 const 对象**（除 `mutable` 成员外）是 UB。关键在于对象**本身**是否是 const 的，而不是你手里的路径是否带 const：

```cpp run title="const-cast-ok-modify.cpp" ok
void legacy_api(char* s) { (void)s; }   // 老接口：其实不修改，但没写 const

int main() {
    int x = 1;                          // x 本身不是 const
    const int& cr = x;
    const_cast<int&>(cr) = 2;           // OK：被修改的对象 x 不是 const 对象
    const char* msg = "hello";
    legacy_api(const_cast<char*>(msg)); // OK：只要 legacy_api 真的不写入
    return x == 2 ? 0 : 1;
}
```

```cpp run title="const-cast-ub.cpp" ub
int main() {
    const int x = 1;                    // x 是 const 对象
    const_cast<int&>(x) = 2;            // UB: 修改 const 对象
    return x;                           // 编译器常常直接返回 1（常量折叠）
}
```

为什么修改 const 对象要定为 UB？因为它给了实现两种重要的自由：

1. **把 const 对象放进只读内存**：带静态存储期、常量初始化的 `const` 对象（以及字符串字面量）可能放在 `.rodata` 段，写入会触发段错误；
2. **常量传播**：编译器可以假定 `const int x = 1;` 的值永远是 1，把所有读取替换为常量。

常量求值器必须诊断 UB，所以它对这个规则的判断很清楚：

```cpp title="const-cast-constexpr.cpp" error
constexpr int f() {
    const int x = 1;
    const_cast<int&>(x) = 2;    // 修改 const 对象
    return x;
}
static_assert(f() == 1);        // error: 常量求值中检测到修改 const 对象

constexpr int g() {
    int x = 1;
    const int& r = x;
    const_cast<int&>(r) = 2;    // OK：x 不是 const 对象
    return x;
}
static_assert(g() == 2);        // OK
```

Clang 的说明是"modification of object of const-qualified type 'const int' is not allowed in a constant expression"。

!!! note "什么是“const 对象”"
    [[basic.type.qualifier]]：类型为 `const T` 的对象、或这种对象的非 `mutable` 子对象，是 **const 对象**。经 `new const T` 创建的对象也是 const 对象。相反，`const T&` 绑定到非 const 对象，或者 `const T*` 指向非 const 对象，都不会使对象变成 const 的。

## "去掉常量性"（¶6–7）

¶6 用限定分解定义：从类型 `T1` 到 `T2` 的转换**去掉常量性**，若 `T1` 与 `T2` 不同，存在 `T1` 的一个 *n* 层限定分解，使得 `T2` 有形如 cv20 P20 cv21 P21 ⋯ cv2n U2 的限定分解，并且**不存在**从 `T1` 到 cv20 P10 cv21 P11 ⋯ cv2n U1 的**限定转换**。

翻译成直觉：把 `T2` 的各层 cv "套到" `T1` 的骨架上，如果得到的类型不是 `T1` 经**隐式限定转换**（[[conv.qual]]）能到达的，就说这个转换"去掉了常量性"。由于限定转换的规则是"只能加 cv，且加 const 时外层也要都是 const"，"去掉常量性"就包括了两种情况：

1. 真正**去掉**某层的 cv：`const int*` → `int*`；
2. 在**不安全的位置加** const：`int**` → `const int**`。

第 2 种情况乍看是"加 const"，但它和第 1 种一样危险：

```cpp run title="unsafe-add-const.cpp" ub
const int ci = 0;

int main() {
    int* p = nullptr;
    int** pp = &p;
    const int** cpp = const_cast<const int**>(pp);   // 必须用 const_cast：这"去掉了常量性"
    *cpp = &ci;          // 合法：把 const int* 存入 *cpp（也就是 p）
    *p = 1;              // UB: 经 p 修改了 const 对象 ci —— 我们没写任何"去 const"的操作
}
```

正因如此，`int**` → `const int**` 不是限定转换（不能隐式进行），`static_cast` 也不行（Clang："static_cast from 'int \*\*' to 'const int \*\*' is not allowed"），只能用 `const_cast`。安全的做法是同时给中间层加 const：`int**` → `const int* const*` 是合法的隐式限定转换。

¶7：引用的情形归结为指针：用左值引用转换从 `T1` 左值到 `T2` 左值、或用右值引用转换从 `T1` 表达式到 `T2` 亡值，若"指向 `T1` 的指针"到"指向 `T2` 的指针"去掉常量性，则这次引用转换也去掉常量性。

### 其他转换的限制

| 转换 | 限制 | 条款 |
|---|---|---|
| `static_cast` | 除 ¶5 的初始化情形外，各项都要求"cv2 不少于 cv1"，且 `void*` → `T*` 不能去 cv | [[expr.static.cast]] |
| `reinterpret_cast` | 不能去掉常量性 | [[expr.reinterpret.cast#2]] |
| `dynamic_cast` | 不能去掉常量性 | [[expr.dynamic.cast#1]] |
| C 风格转换 | 可以：它会尝试 `static_cast`/`reinterpret_cast` 后接 `const_cast` | [[expr.cast#4]] |

这就是为什么只有 `const_cast` 和 C 风格转换能去 const：把"去 const"这件危险的事集中到一个显眼的关键字上，便于审查和搜索。

## 不能用 `const_cast` 的转换（¶8）

¶8（注 3）：有些只涉及 cv 变化的转换不能用 `const_cast` 完成：

- **函数指针**之间（函数类型本身没有 cv，所谓"cv 变化"只能来自别处，其使用会导致 UB）；
- **成员函数指针**之间，特别是从指向 `const` 成员函数的指针转换为指向非 `const` 成员函数的指针——`void (S::*)() const` 和 `void (S::*)()` 是**不同的函数类型**，不是 cv 不同的相似类型。

```cpp title="const-cast-pmf.cpp" error
struct S { void f() const; };

void t() {
    void (S::*p)() const = &S::f;
    auto q = const_cast<void (S::*)()>(p);   // error: 成员函数指针不在 const_cast 的范围内
}
```

## 正当用途

1. **调用不够 const 正确的旧接口**：C 库或老代码的参数应当是 `const T*` 却写成了 `T*`，而你确认它不会写入。
2. **以 const 版本实现非 const 版本**，避免重复代码：

```cpp run title="const-overload.cpp" ok
#include <cstddef>

class Buffer {
    char data_[16]{};
public:
    const char& at(std::size_t i) const {
        // ……复杂的边界检查……
        return data_[i];
    }
    char& at(std::size_t i) {
        // *this 不是 const 对象（否则不会调用到这个重载），所以去掉 const 是安全的
        return const_cast<char&>(static_cast<const Buffer&>(*this).at(i));
    }
};

int main() {
    Buffer b;
    b.at(3) = 'x';
    return b.at(3) == 'x' ? 0 : 1;
}
```

C++23 的显式对象形参（`this auto& self`）提供了另一种去重方式，不再需要 `const_cast`。

3. **`volatile` 的去除**：读写硬件寄存器副本、或者把 `volatile` 缓冲区交给不接受 `volatile` 的函数（同样，若对象本身是 volatile 对象，经非 volatile glvalue 访问它是 UB，[[dcl.type.cv]]）。

## 陷阱

!!! pitfall "“我只是去掉 const，又没写”"
    `const_cast` 本身无害；只要不写入 const 对象就不是 UB。但"不写"往往依赖调用的函数——一旦那个函数的实现改为写入，UB 就悄悄出现了。

!!! pitfall "字符串字面量"
    `char* p = const_cast<char*>("abc"); p[0] = 'x';` 是 UB：字符串字面量是 const 对象，通常位于只读段，运行时直接崩溃。

!!! pitfall "以为 `int**` → `const int**` 是安全的“加 const”"
    见 ¶6 的例子：它能让你在不写任何"去 const"代码的情况下修改 const 对象，因此语言把它归为"去掉常量性"。

## 思考题

!!! question "思考题 1"
    `const int* const* p;` 下，`const_cast<int* const*>(p)`、`static_cast<const int* const* const>(p)` 是否合法？前者是否"去掉常量性"？

<details markdown="1">
<summary>答案</summary>

`const_cast<int* const*>(p)` 合法：二者相似，每层 P 相同，只改第二层（被指的指针所指对象）的 const；它去掉常量性（把 `int* const*` 的 cv 套到 `p` 的类型上，`const int* const*` → `int* const*` 不是限定转换）。`static_cast<const int* const* const>(p)` 合法：目标类型的顶层 const 对 prvalue 没有意义（被丢弃），实际是到 `const int* const*` 的同类型转换（¶5 隐式转换序列存在）。
</details>

!!! question "思考题 2"
    `struct S { mutable int m; int n; }; const S s{};` 下，`const_cast<S&>(s).m = 1;` 与 `const_cast<S&>(s).n = 1;` 各如何？

<details markdown="1">
<summary>答案</summary>

`s` 是 const 对象，`s.n` 是它的非 mutable 子对象，因而也是 const 对象，修改它是 UB。`s.m` 是 `mutable` 成员，**不是** const 对象（[[basic.type.qualifier]]），修改它是合法的——而且根本不需要 `const_cast`，`s.m = 1;` 直接就能编译（[[expr.ref#8]] 中 `mutable` 成员不继承对象表达式的 const）。
</details>

## 小结

!!! summary
    - `const_cast` 只改 cv：相似的对象指针 / 数据成员指针（¶3），对应的左值 / 亡值引用（¶4），类与数组 prvalue 可实质化后转为亡值（¶4.3）。
    - 不适用：类型不相似、函数指针、成员函数指针、非指针非引用类型。
    - 转换本身从不 UB；**修改 const 对象**才是 UB（[[dcl.type.cv]]），判断依据是对象本身是否 const。
    - "去掉常量性"（¶6–7）= 目标 cv 套在源骨架上不是合法的限定转换；包括去掉 cv 与在不安全位置加 const（`int**` → `const int**`）。
    - 只有 `const_cast` 与 C 风格转换能去掉常量性。
