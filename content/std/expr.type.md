---
title: 表达式的类型
summary: 表达式的类型永远不是引用类型，求值悬垂引用是 UB；非类、非数组的 prvalue 不带 cv；两个指针操作数需要共同类型时按什么算法求出复合指针类型。
status: done
papers: P0012R1, P0388R4
related: basic.lval, conv.qual, expr.cond, expr.eq, expr.rel, dcl.init.ref, dcl.type.decltype
tags: 类型, 指针, 限定转换
updated: 2026-10-19
---

!!! tldr
    - 表达式的类型永远不是引用：引用在分析之前就被去掉，只留下值类别。`decltype((r))` 里的 `&` 来自值类别，不来自类型。
    - 引用所指的对象的存储已经结束时，对这个引用的任何求值都是 UB，不只是读它的值。
    - 非类、非数组的 prvalue 不带 cv，所以 `const int f();` 的 `const` 没有作用；类和数组的 prvalue 保留 cv。
    - `p == q`、`c ? p : q` 等把两个指针统一成复合指针类型：空指针常量让位给另一方，`void*` 吸收对象指针，基类指针吸收派生类指针，相似类型逐层合并 cv。
    - 合并 cv 时，某一层加了限定，它外面各层（最外层除外）都要加 `const`，所以 `int**` 和 `const int**` 合成 `const int* const*`。

## 表达式没有引用类型（¶1）

```cpp ok
#include <type_traits>
int i = 0;
int& r = i;
int&& rr = 0;

static_assert(std::is_same_v<decltype(r), int&>);    // decltype(名字)：看声明的类型
static_assert(std::is_same_v<decltype((r)), int&>);  // decltype(表达式)：类型 int，lvalue → int&
static_assert(std::is_same_v<decltype((rr)), int&>); // 表达式 rr：类型 int，lvalue
static_assert(std::is_same_v<decltype((i)), int&>);  // 表达式 i：同样是 int、lvalue
```

¶1 如果一个表达式最初的类型是 `T` 的引用（[[dcl.ref]]、[[dcl.init.ref]]），在做任何进一步分析之前就把类型调整为 `T`，值类别不变。

所以表达式 `r` 和 `i` 的类型都是 `int`，值类别都是 lvalue，两者在表达式层面没有区别。`decltype((r))` 得到 `int&`，是因为 [[dcl.type.decltype]] 把 lvalue 编码为 `&`。函数调用和强制转换也是这样：`int& f();` 的 `f()` 是 `int` 类型的 lvalue，`static_cast<int&&>(x)` 是 `int` 类型的 xvalue（[[expr.call]]、[[expr.static.cast]]）。

### 悬垂引用的求值是 UB

¶1 的后半段规定引用表达式的结果。设 `X` 是引用所指代的对象或函数。如果在这次求值的语境里，指向 `X` 的指针是有效的（[[basic.compound#6]]：大致是说 `X` 的存储还没有结束），结果就指代 `X`；否则行为未定义。注 1 补充，在引用的生命周期开始之前或结束之后使用它，行为未定义（[[basic.life]]）。

```cpp ub
int main() {
    int* p = new int(1);
    int& r = *p;
    delete p;
    int* q = &r;   // UB：r 所指对象的存储已经结束，求值 r 本身就是 UB
    (void)q;
}
```

和指针对比一下。`delete p` 之后 `p` 持有无效指针值，通过它间接访问是 UB，但复制它之类的其他用法只是实现定义的（[[basic.compound#6]]）。引用没有这种中间状态，只要求值就是 UB，哪怕只是取地址。C++23 的措辞只说表达式指代引用所指的对象或函数，没有讨论这种情形，当前草案把它明确为 UB。

## 非类 prvalue 不带 cv（¶2）

¶2 如果一个 prvalue 最初的类型是 cv `T`，而 `T` 是不带 cv 的非类、非数组类型，就把表达式的类型调整为 `T`。

```cpp ok
#include <type_traits>
const int  f();
const int* g();
struct S {};
const S    h();

static_assert(std::is_same_v<decltype(f()), int>);         // 顶层 const 被去掉
static_assert(std::is_same_v<decltype(g()), const int*>);  // 不在顶层的 const 保留
static_assert(std::is_same_v<decltype(h()), const S>);     // 类 prvalue 保留 cv
static_assert(std::is_same_v<decltype(static_cast<const int>(1)), int>);
```

非类 prvalue 没有身份，一个 `const int` 值和一个 `int` 值无法区分，既不能被修改，也不能调用成员函数，保留 cv 只会让类型推导和重载决议更复杂。类和数组的 prvalue 会被实质化成对象，可以调用成员函数，`const` 有可观察的影响（[[basic.lval#9]]）。Clang 在 `-Wextra` 下对 `const int f();` 给出 `-Wignored-qualifiers` 警告，因为这个 `const` 没有作用。

## 复合指针类型（¶3）

```cpp ok
struct Base {};
struct Derived : Base {};

bool same(Base* b, Derived* d) { return b == d; }   // d 先转换为 Base*
const void* pick(bool c, void* v, const int* p) {
    return c ? v : p;                               // 两边都转换为 const void*
}
```

`==`、`!=`（[[expr.eq]]）、`<` 等（[[expr.rel]]）、`<=>`（[[expr.spaceship]]）和条件运算符 `?:`（[[expr.cond]]）的两个操作数都是指针时，要先把它们转换成同一个类型。¶3 定义了这个类型，叫做**复合指针类型**（[[g:composite-pointer-type]]）。至少一个操作数是指针、成员指针或 `std::nullptr_t` 时才用到它。

### 算法

设两个操作数 `p1`、`p2` 的类型为 `T1`、`T2`。¶3 按顺序尝试下列各条，用第一条适用的：

| 条目 | 条件 | 复合指针类型 |
|---|---|---|
| ¶3.1 | 两者都是空指针常量 | `std::nullptr_t` |
| ¶3.2 | 其中一个是空指针常量 | 另一个的类型 |
| ¶3.3 | 一个指向 *cv1* `void`，另一个指向 *cv2* `T`（`T` 是对象类型或 `void`） | 指向 *cv12* `void`，*cv12* 是两者的并 |
| ¶3.4 | 一个指向 `noexcept` 函数，另一个指向函数，其余相同 | 指向函数（不带 `noexcept`） |
| ¶3.5 | 分别指向 `C1` 和 `C2`，两者之一与另一个引用相关 | 两者的限定合成类型，以基类一方为骨架 |
| ¶3.6 | 两个成员函数指针，一个 `noexcept`、一个不是，类之间引用相关 | 不带 `noexcept` 的成员函数指针，以派生类一方为类 |
| ¶3.7 | 分别是 `C1`、`C2` 的成员指针，成员类型为 *cv1* `U`、*cv2* `U`，类之间引用相关 | 两者的限定合成类型，以派生类一方为骨架 |
| ¶3.8 | `T1` 与 `T2` 相似 | `T1` 和 `T2` 的限定合成类型 |
| ¶3.9 | 其他 | 需要求复合指针类型的程序非良构 |

表中用到三个术语：

- **空指针常量**（[[g:null-pointer-constant]]）：值为零的整数字面量，或 `std::nullptr_t` 类型的 prvalue（[[conv.ptr]]）。
- **引用相关**（reference-related，[[dcl.init.ref]]）：`C1` 与 `C2` 相似，或者一个是另一个的基类。
- **相似**（[[g:similar-types|similar]]）和**限定合成类型**（qualification-combined type）都定义在 [[conv.qual]]。相似大致是说，把各层的 cv 都去掉、并忽略数组边界之后两个类型相同。限定合成类型逐层取两边 cv 的并集，如果某一层因此发生了变化，它外面各层（最外层除外）都加上 `const`。

指针（¶3.5）和成员指针（¶3.7）的方向相反。`Base*` 和 `Derived*` 合成 `Base*`，与派生类指针到基类指针的隐式转换方向一致；`int Base::*` 和 `int Derived::*` 合成 `int Derived::*`，与成员指针从基类到派生类的转换方向一致（[[conv.mem]]）。

### 例子

```cpp ok
#include <type_traits>
#include <utility>
#include <cstddef>
template<class A, class B>
using CPT = decltype(true ? std::declval<A>() : std::declval<B>());

struct Base {}; struct Derived : Base {};
void f(); void g() noexcept;

static_assert(std::is_same_v<CPT<std::nullptr_t, int*>, int*>);               // ¶3.2
static_assert(std::is_same_v<CPT<void*, const int*>, const void*>);           // ¶3.3
static_assert(std::is_same_v<CPT<decltype(&f), decltype(&g)>, void (*)()>);   // ¶3.4
static_assert(std::is_same_v<CPT<Base*, const Derived*>, const Base*>);       // ¶3.5
static_assert(std::is_same_v<CPT<int Base::*, int Derived::*>, int Derived::*>);  // ¶3.7
static_assert(std::is_same_v<CPT<int**, const int**>, const int* const*>);    // ¶3.8
static_assert(std::is_same_v<CPT<const int**, volatile int**>,
                             const volatile int* const*>);                    // ¶3.8
```

<div class="compare" markdown="1">

```cpp error
struct B {}; struct D : B {};
bool a(int* p, long* q) {
    return p == q;   // error: ¶3.9
}
bool b(B** p, D** q) {
    return p == q;   // error: ¶3.9
}
```

```cpp ok
struct B {}; struct D : B {};
bool a(int* p, const int* q) {
    return p == q;   // ¶3.8
}
bool b(B* const* p, B** q) {
    return p == q;   // ¶3.8
}
```

</div>

`int*` 和 `long*` 不相似，`int` 和 `long` 也不引用相关，所以落到 ¶3.9。`B**` 和 `D**` 也一样：¶3.5 只看一层，被指的 `B*` 和 `D*` 既不相似，也不是基类关系。这也是 `D**` 不能隐式转换为 `B**` 的原因，否则就能通过它往一个 `D*` 槽位里写进一个指向别的 `B` 对象的指针。

### 为什么 `int**` 和 `const int**` 合成 `const int* const*`

逐层比较。最内层是 `int` 对 `const int`，取并集得到 `const int`，这一层发生了变化。按规则，它外面的中间层（被指的那个指针本身）要加 `const`。最外层不参与。结果是 `const int* const*`。

如果中间层不加 `const`，结果就是 `const int**`。而 `int**` 到 `const int**` 的转换会破坏 const 正确性：通过它可以往一个 `int*` 槽位里写入一个 `const int*`，再通过原来的 `int**` 修改那个 `const` 对象（[[conv.qual]] 给出了完整的反例）。中间层是 `const` 时，谁也不能通过合成类型的指针往中间层写东西，两边都可以安全地转换过去。

!!! lawyer "数组边界与 Clang 的偏差"
    C++20 起限定合成类型也处理已知边界和未知边界的数组（[[P0388R4]]）：某一层一方是 `[N]`、另一方是 `[]` 时合成为 `[]`，外面各层同样加 `const`。按条文：

    - `int(*)[3]` 和 `int(*)[]` 的变化发生在第 1 层，外面没有需要加 `const` 的层，合成为 `int(*)[]`。
    - `int(**)[3]` 和 `int(**)[]` 的变化发生在第 2 层，第 1 层加 `const`，合成为 `int(* const*)[]`。

    截至写作时，Clang 23 对这两例分别给出 `const int(*)[]` 和 `const int(* const*)[]`，额外给数组元素加了 `const`。两种结果都能让双方安全地转换过去，但 Clang 的结果与条文不一致。

## 历史与演进

!!! history
    - C++98 的复合指针类型只处理对象指针、`void*` 和空指针常量，定义在关系运算符一节，后来移到表达式总则。
    - C++11 加入 `std::nullptr_t`（¶3.1、¶3.2）。
    - C++17 起 `noexcept` 是函数类型的一部分（[[P0012R1]]），于是加入 ¶3.4 和 ¶3.6。
    - C++20 的限定转换支持数组边界（[[P0388R4]]），复合指针类型随之能处理 `T[N]` 和 `T[]`。
    - C++23 之后的新措辞在 ¶1 加入了引用所指不再有效时为 UB 的规定。

## 常见误解

!!! pitfall "`decltype(x)` 与 `decltype((x))` 一样"
    `decltype(r)` 看名字的声明类型，`decltype((r))` 看表达式的类型和值类别。对引用变量两者恰好都是 `int&`，这掩盖了区别；对 `int i;`，前者是 `int`，后者是 `int&`。

!!! pitfall "`?:` 里的 0 都是空指针常量"
    `c ? p : 0` 中的 `0` 是整数字面量，是空指针常量，按 ¶3.2 复合类型是 `p` 的类型。`int zero = 0;` 之后的 `c ? p : zero` 中，`zero` 不是字面量，不是空指针常量，于是非良构。

## 思考题

!!! question "思考题 1"
    `Base* const*` 和 `Derived**` 能用 `==` 比较吗？

<details markdown="1">
<summary>答案</summary>

不能。¶3.5 要求被指类型 `C1`、`C2` 引用相关。这里 `C1` 是 `Base* const`，`C2` 是 `Derived*`，它们既不相似，也不是基类关系。两个类型本身也不相似，¶3.8 不适用。于是落到 ¶3.9，非良构。
</details>

!!! question "思考题 2"
    设 `const char* s; char* t; void* v;`。`s == t` 时 `t` 被转换成什么？`s == v` 呢？

<details markdown="1">
<summary>答案</summary>

`s == t`：`const char*` 和 `char*` 相似，按 ¶3.8 合成为 `const char*`。只有最内层变化，没有中间层要加 `const`。`t` 经限定转换变为 `const char*`。

`s == v`：按 ¶3.3 合成为 `const void*`。`s` 经指针转换变为 `const void*`，`v` 经限定转换变为 `const void*`。
</details>
