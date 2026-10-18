---
title: 显式类型转换（强制转换写法）
summary: C 风格转换 (T)e 的语义：依次尝试 const_cast、static_cast、static_cast+const_cast、reinterpret_cast、reinterpret_cast+const_cast，先匹配者胜（即使它非良构）；可以无视基类访问控制的三种情形；不完整类之间的转换未指定按 static_cast 还是 reinterpret_cast 解释；为什么 C 风格转换危险
status: draft
related: expr.type.conv, expr.static.cast, expr.reinterpret.cast, expr.const.cast, expr.dynamic.cast, class.access.base, dcl.name, topics/casts
tags: 类型转换, C 兼容, 访问控制
updated: 2026-10-17
---

`(T)e` 是从 C 继承来的强制转换写法。在 C 里它只有一种含义；在 C++ 里，同一个写法可能是 `const_cast`、`static_cast`、`reinterpret_cast` 或它们的组合，具体是哪一种**由编译器替你挑选**，而且代码改动时，挑选的结果可能悄悄改变。本节规定这个挑选算法。

函数式转换 `T(e)`（单个实参时）与 `(T)e` 完全等价（[[expr.type.conv#1]]），所以本节的一切也适用于它。

## 结果（¶1）

¶1：`(T)` *cast-expression* 的结果类型是 `T`。`T` 是左值引用或函数右值引用 ⇒ lvalue；对象右值引用 ⇒ xvalue；否则 prvalue。注 1：若 `T` 是 cv 限定的非类类型，确定结果 prvalue 的类型时会丢弃 cv（[[expr.prop]]），所以 `(const int)3` 的类型是 `int`。

## 语法（¶2）

¶2：显式类型转换可以用函数式写法（[[expr.type.conv]]）、类型转换运算符（`dynamic_cast`、`static_cast`、`reinterpret_cast`、`const_cast`）或强制转换写法表达：

```text
cast-expression:
    unary-expression
    ( nofun-type-id ) cast-expression
```

*cast-expression* 右递归，优先级介于一元表达式与成员指针运算 `.*` 之间：`(T)a.b` 是 `(T)(a.b)`；`(T)*p` 是 `(T)(*p)`；`(T)a + b` 是 `((T)a) + b`。

括号中是 *nofun-type-id*（[[dcl.name]]），即不能写成函数类型的 *type-id*。函数类型的值本来就不存在，转换到函数类型没有意义。

## 只允许列出的转换（¶3）

¶3：下文未提及、也不是用户定义的（[[class.conv]]：构造函数、转换函数）任何类型转换都非良构。

## 尝试顺序（¶4）

¶4 是本节的核心。以下转换可以用强制转换写法完成：

| 顺序 | 解释 |
|---|---|
| ¶4.1 | `const_cast` |
| ¶4.2 | `static_cast` |
| ¶4.3 | `static_cast` 后接 `const_cast` |
| ¶4.4 | `reinterpret_cast` |
| ¶4.5 | `reinterpret_cast` 后接 `const_cast` |

每种解释都适用与对应具名转换相同的语义限制和行为。**若一个转换能以多种方式解释，就使用列表中最靠前的那种，即使由此得到的转换非良构**。若使用的是 `static_cast` 后接 `const_cast`，而它又能以多种方式解释，则转换非良构。

关键在于“即使非良构”这一句。编译器并不是挨个尝试、哪个能编译就用哪个，而是哪个在形式上能匹配就用哪个。如果匹配上的解释违反了语义限制（例如二义基类），就报错，不会回退到后面的 `reinterpret_cast`。这条规则防止了更糟的结果：若允许回退，当 `A` 是二义基类时，`(A*)p` 会默默变成 `reinterpret_cast`，得到一个错误的指针。

标准例 1：

```cpp title="c-cast-order.cpp" error
struct A { };
struct I1 : A { };
struct I2 : A { };
struct D : I1, I2 { };
A* foo(D* p) {
    return (A*)(p);             // error: 选中 static_cast 解释，而 A 是二义基类
}

int*** ptr = 0;
auto t = (int const* const* const*)ptr;   // OK：const_cast 解释（只加 cv）

struct S {
    operator const int*();
    operator volatile int*();
};
int* p = (int*)S();             // error: static_cast + const_cast 有两种可能解释
```

第一处，`D*` → `A*` 能解释为 `static_cast`（派生类到基类），所以就用它，而二义性导致非良构，不会退到 `reinterpret_cast`。第二处，`int***` → `int const* const* const*` 只涉及 cv，是 `const_cast`。它也可以是 `static_cast`，因为这恰好也是合法的限定转换，但 `const_cast` 排在前面。第三处，`S` 可以经两个转换函数之一 `static_cast` 到 `const int*` 或 `volatile int*`，再 `const_cast` 到 `int*`，存在两种解释，所以非良构。

### 最常见的映射

| `(T)e` | 实际解释 |
|---|---|
| `(int)3.7`、`(double)n`、`(Enum)i` | `static_cast` |
| `(Derived*)base_ptr` | `static_cast`（不检查！） |
| `(int*)const_int_ptr` | `const_cast` |
| `(char*)"literal"` | `const_cast` |
| `(long*)int_ptr`、`(std::uintptr_t)ptr` | `reinterpret_cast` |
| `(char*)const_int_ptr` | `reinterpret_cast` + `const_cast` |
| `(void)expr` | `static_cast`（¶4 的 [[expr.static.cast#4]]） |

`dynamic_cast` 不在清单中，所以 C 风格转换永远不会做运行期检查。

## 访问控制的漏洞（¶4.6–¶4.8）

¶4 还规定，在以下情形中执行 `static_cast` 时，即使基类不可访问，转换也有效：

- ¶4.6 派生类对象指针 / 左值 / 右值 → 无二义基类的指针 / 引用；
- ¶4.7 派生类的成员指针 → 无二义、非虚基类的成员指针；
- ¶4.8 无二义、非虚基类的对象指针 / glvalue / 成员指针 → 派生类的指针 / 引用 / 成员指针。

也就是说，C 风格转换可以**无视 `private`/`protected` 继承**，而且由于它仍然是 `static_cast` 的语义，指针调整是正确的。这是具名转换做不到的：`static_cast` 会因不可访问而报错，`reinterpret_cast` 不做偏移调整。

```cpp run title="c-cast-private-base.cpp" ok
struct X { int x = 2; };
struct B { int b = 1; };
struct D : X, private B { int d = 3; };   // B 是私有基类，且不是首个基类

int main() {
    D d;
    B* pb = (B*)&d;                  // OK：¶4.6，无视私有继承，正确调整到 B 子对象
    D* back = (D*)pb;                // OK：¶4.8，向下转换，同样无视访问
    int D::* pm = (int D::*)&B::b;   // OK：¶4.8，基类成员指针 → 派生类成员指针，无视访问
    // static_cast<B*>(&d);          // error: B 是不可访问的基类
    return (pb->b == 1 && back == &d && d.*pm == 1) ? 0 : 1;
}
```

为什么要保留这个漏洞？原因是兼容性：C++ 早期的代码（以及 [[expr.dynamic.cast]] 的标准例 2 本身）需要在不修改类定义的情况下取得私有基类的指针。它也是语言中唯一一种合法突破私有继承的手段，这正是它危险的地方：访问控制体现了类作者的设计意图，而 C 风格转换可以不留痕迹地绕开它。

## 不完整类（¶5）

¶5：强制转换写法的操作数可以是指向不完整类类型的指针 prvalue，目标类型也可以是指向不完整类类型的指针。若指针所指的操作数类型和目标类型都是类类型，且其中之一或二者不完整，则**未指定**使用 `static_cast` 解释还是 `reinterpret_cast` 解释，即使二者之间实际存在继承关系。

注 2 给出了原因：如果这些类在翻译单元中稍后才定义，多遍编译器可以合法地按类完整时的方式解释这个转换。

```cpp run title="c-cast-incomplete.cpp" unspecified
struct P;
struct Q;
Q* f(P* p) { return (Q*)p; }   // 此处 P、Q 不完整：未指定按 static_cast 还是 reinterpret_cast 解释

struct X { int x; };
struct P { int a; };
struct Q : X, P {};            // P 是 Q 的非首个基类：两种解释的结果不同！

int main() {
    Q q;
    P* pp = &q;
    return f(pp) == &q ? 0 : 1;   // static_cast 解释 ⇒ 0；reinterpret_cast 解释（不调整地址）⇒ 1
}
```

单遍编译器（GCC、Clang、MSVC 都是）在 `f` 处看不到继承关系，实际按 `reinterpret_cast` 处理，`f` 返回的指针没有做偏移调整，本机 Clang 上程序退出码为 1。具名转换不存在这个问题：`static_cast<Q*>(p)` 在 `P`、`Q` 不完整时直接非良构，`reinterpret_cast` 则明确不调整。

## 为什么 C 风格转换危险

综合以上规则，`(T)e` 有这些问题：

1. **意图不可见**：读代码的人无法从 `(Foo*)p` 看出它是向下转换、去 const 还是重新解释。具名转换各自表达一种意图，也便于 `grep`。
2. **语义随上下文变化**：`(Derived*)base` 在 `Derived` 完整且公有派生时是 `static_cast`；把继承改为私有，它仍然编译（¶4.6 漏洞）；去掉头文件包含使类不完整，它悄悄变成 `reinterpret_cast`（¶5）；把基类改成无关类，它还是能编译（`reinterpret_cast`）。每一次变化都不产生诊断。
3. **能力过大**：一次转换可以同时去掉 const 并重新解释类型（¶4.5），而这两个都是危险操作。
4. **函数式转换 `T(e)` 有同样的问题**（[[expr.type.conv]]），却看起来像无害的构造函数调用。

!!! tip "工具"
    GCC 和 Clang 的 `-Wold-style-cast` 会对每个 C 风格转换发出警告（不针对函数式写法）；Clang-Tidy 的 `cppcoreguidelines-pro-type-cstyle-cast` 和 `google-readability-casting` 检查器可以建议对应的具名转换。C++ Core Guidelines 的 ES.48/ES.49 建议避免强制转换，必须转换时使用具名转换。

## 历史与演进

!!! history
    - **C**：`(T)e` 是唯一的显式转换。
    - **C++98**：引入四个具名转换，并把 C 风格转换定义为它们的组合；访问控制漏洞和不完整类的未指定行为都在 C++98 中就已存在。
    - **C++11**：右值引用目标类型（结果为亡值）。
    - **当前草案**：括号中的类型写为 *nofun-type-id*。

## 陷阱

!!! pitfall "`(Derived*)p` 不做检查"
    它是 `static_cast`，不是 `dynamic_cast`。错误的向下转换是静默 UB。

!!! pitfall "`(T*)p` 在看不到继承关系时变成 reinterpret_cast"
    类不完整（¶5）或者根本无关时，C 风格转换不报错，只是不再调整地址。

!!! pitfall "以为 `(int)x` 和 `int(x)` 不同"
    二者完全相同。要禁止窄化，用 `int{x}`；要明确意图，用 `static_cast<int>(x)`。

## 思考题

!!! question "思考题 1"
    `const char* s = "abc"; auto p = (unsigned char*)s;` 被解释为什么？

<details markdown="1">
<summary>答案</summary>

¶4.1 `const_cast`：`const char*` → `unsigned char*` 类型不相似，不行。¶4.2 `static_cast`：无关对象指针之间不行。¶4.3 `static_cast` + `const_cast`：`static_cast` 到 `const unsigned char*` 也不行。¶4.4 `reinterpret_cast`：会去掉常量性，不行。¶4.5 `reinterpret_cast` 到 `const unsigned char*` 再 `const_cast` 到 `unsigned char*`：可以。所以是 `reinterpret_cast` + `const_cast`，同时做了两件危险的事。经 `p` 读取是合法的（`unsigned char` 可以访问任何对象），写入则修改了字符串字面量，UB。
</details>

!!! question "思考题 2"
    `struct X { int x; }; struct B { int b; }; struct D : X, private B {}; D d;` 在 `D` 的成员与友元之外，`((B&)d).b` 与 `reinterpret_cast<B&>(d).b` 各如何？

<details markdown="1">
<summary>答案</summary>

`(B&)d` 按 ¶4.6 解释为无视访问的 `static_cast`，结果指代 `d` 的 `B` 基类子对象，`.b` 读取它，行为良好。`reinterpret_cast<B&>(d)` 不调整地址；`d` 与它的 `B` 子对象不是指针可互转的（`B` 不是首个基类），结果仍指代 `d`，其类型 `D` 与 `B` 不相似，访问 `.b` 按 [[expr.ref#10]] 是 UB。
</details>

## 小结

!!! summary
    - `(T)e` 与单实参 `T(e)` 等价；结果值类别由 `T` 决定。
    - 依次尝试 `const_cast` → `static_cast` → `static_cast`+`const_cast` → `reinterpret_cast` → `reinterpret_cast`+`const_cast`；**先匹配者胜，即使它非良构**。
    - 作为 `static_cast` 时可以无视基类的访问控制（¶4.6–¶4.8），并正确调整指针。
    - 指向不完整类的指针之间转换时，未指定按 `static_cast` 还是 `reinterpret_cast` 解释（¶5）。
    - 永远不做 `dynamic_cast`；由于意图不可见、语义随上下文变化，在 C++ 代码中应优先使用具名转换。
