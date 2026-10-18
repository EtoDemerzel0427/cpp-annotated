---
title: 表达式的类型
summary: 表达式的类型永远不是引用类型；非类纯右值的 cv 限定被丢弃；两个指针操作数的复合指针类型如何计算
status: draft
related: basic.lval, conv.qual, expr.cond, expr.eq, expr.rel, dcl.init.ref
tags: 类型, 指针, 限定转换
updated: 2026-10-17
---

[expr.type] 讲的是对表达式类型的两次调整和一次合成：

1. ¶1：表达式的类型不可能是引用。引用一出现就被剥掉，只留下值类别。
2. ¶2：非类、非数组的 prvalue 不带 cv 限定。
3. ¶3：当两个指针（或成员指针、`nullptr`）需要统一为同一类型时（`==`、`<`、`?:` 等），如何计算它们的**复合指针类型**（composite pointer type）。

"表达式没有引用类型""标量 prvalue 没有 const"这两条常识，就出自前两条；第三条则是一个精巧的小算法，直接建立在 [[conv.qual]] 的限定分解之上。

## 引用类型被立即剥去（¶1）

¶1 如果表达式最初具有"`T` 的引用"类型（[[dcl.ref]]、[[dcl.init.ref]]），那么在任何进一步分析之前，其类型调整为 `T`，值类别不变。

这条规则解释了一个常让初学者困惑的事实：在 C++ 中，**没有引用类型的表达式**。

```cpp ok
#include <type_traits>
int i = 0;
int& r = i;
int&& rr = 0;

static_assert(std::is_same_v<decltype(r), int&>);    // decltype(名字)：看声明的类型
static_assert(std::is_same_v<decltype((r)), int&>);  // decltype(表达式)：类型 int + 左值 → int&
static_assert(std::is_same_v<decltype((rr)), int&>); // rr 作为表达式：类型 int，左值
```

`r` 这个表达式的类型是 `int`，值类别是左值。`decltype((r))` 之所以得出 `int&`，是因为 [[dcl.type.decltype]] 把左值编码成了 `&`，而不是因为表达式的类型是引用。函数调用 `f()`（`int& f();`）和强制转换 `static_cast<int&&>(x)` 也是如此：类型都是 `int`，前者是左值，后者是 xvalue（[[expr.call]]、[[expr.static.cast]]）。

### 引用失效时的 UB

¶1 后半段（当前草案的措辞）还规定了结果指代什么。设 `X` 是引用所指代的对象或函数。如果指向 `X` 的指针在该求值的语境中是有效的（[[basic.compound]] 中的 valid in the context of），结果就指代 `X`；否则行为未定义。注释 1：在引用的生命周期开始之前或结束之后使用它，行为未定义（[[basic.life]]）。

换言之，对悬垂引用的任何求值都是 UB，而不只是读取它的值：

```cpp ub
int main() {
    int* p = new int(1);
    int& r = *p;
    delete p;
    int* q = &r;   // UB：r 所指对象的存储期已结束，对 r 的求值本身就是 UB
    (void)q;
}
```

可以与指针对比。`delete p` 之后，`p` 持有无效指针值，通过它间接访问是 UB，对它的其他使用（如复制）则是实现定义的（[[basic.compound#6]]）。引用没有这种中间地带。C++23 的文本只说"表达式指代引用所指的对象或函数"，没有讨论引用失效的情形；当前草案把它明确规定为 UB。

## 非类纯右值丢掉 cv（¶2）

¶2 如果 prvalue 最初具有类型"cv `T`"，其中 `T` 是 cv 无限定的非类、非数组类型，那么表达式的类型调整为 `T`。

```cpp ok
#include <type_traits>
const int  f();
const int* g();
struct S {};
const S    h();

static_assert(std::is_same_v<decltype(f()), int>);         // 顶层 const 被丢弃
static_assert(std::is_same_v<decltype(g()), const int*>);  // 不是顶层的 const 保留
static_assert(std::is_same_v<decltype(h()), const S>);     // 类 prvalue 保留 cv
static_assert(std::is_same_v<decltype(static_cast<const int>(1)), int>);
```

为什么非类 prvalue 不需要 cv？因为它们没有身份：一个 `const int` 值与一个 `int` 值无法区分，既不能被修改，也不能调用成员函数。保留 cv 只会让类型推导和重载决议更复杂。类和数组的 prvalue 则不同，它们会被实质化成对象，可以调用成员函数，`const` 对它们有可观察的影响（[[basic.lval#9]]）。

（在 `-Wextra` 下，Clang 会对 `const int f();` 给出 `-Wignored-qualifiers` 警告，原因正是这个 `const` 毫无作用。）

## 复合指针类型（¶3）

在 `==`、`!=`（[[expr.eq]]）、`<` 等（[[expr.rel]]）、`<=>`（[[expr.spaceship]]）和条件运算符 `?:`（[[expr.cond]]）中，如果两个操作数都是指针（或至少一个是指针、成员指针或 `std::nullptr_t`），而运算需要一个共同类型，两个操作数就都转换为它们的**复合指针类型**（[[g:composite-pointer-type]]）。

¶3 的算法按顺序尝试以下各条，采用第一条适用的。设操作数 `p1`、`p2` 的类型为 `T1`、`T2`：

| 条目 | 条件 | 复合指针类型 |
|---|---|---|
| ¶3.1 | 两者都是空指针常量 | `std::nullptr_t` |
| ¶3.2 | 其中一个是空指针常量 | 另一个的类型 |
| ¶3.3 | 一个是"指向 *cv1* `void`"，另一个是"指向 *cv2* `T`"（`T` 为对象类型或 void） | "指向 *cv12* `void`"，*cv12* 是两者之并 |
| ¶3.4 | 一个是"指向 noexcept 函数"，另一个是"指向函数"，其余相同 | "指向函数" |
| ¶3.5 | "指向 `C1`"与"指向 `C2`"，且 `C1`、`C2` 之一引用相关于另一个 | 限定合成类型（qualification-combined type），以基类一方为骨架 |
| ¶3.6 | 成员函数指针：一个 noexcept，一个非 noexcept，类之间引用相关 | 指向（更派生类的）成员函数，去掉 noexcept |
| ¶3.7 | "`C1` 的类型为 *cv1* `U` 的成员指针"与"`C2` 的……*cv2* `U`"，类之间引用相关 | 限定合成类型，以派生类一方为骨架 |
| ¶3.8 | `T1`、`T2` 相似（[[conv.qual]]） | `T1` 与 `T2` 的限定合成类型 |
| ¶3.9 | 其他 | 非良构 |

几点说明：

- ¶3.5 的引用相关（reference-related，[[dcl.init.ref#4]]）是指 `C1` 与 `C2` 相似，或一个是另一个的基类。所以 `Base*` 与 `Derived*` 的复合类型是 `Base*`（派生到基的指针转换方向）；成员指针（¶3.7）的方向则相反，`int Base::*` 与 `int Derived::*` 的复合类型是 `int Derived::*`，与 [[conv.mem]] 的逆变方向一致。
- 限定合成类型（[[conv.qual#3]]）的算法是逐层取 cv 的并集；如果某一层发生了变化，它外面的所有层（最外层除外）都要加 `const`。保证多级限定转换安全的正是这条规则（见 [[conv]] 中对 `T**` → `const T**` 的讨论）。
- ¶3.5 只看一层指针。对 `Base**` 与 `Derived**` 而言，`Base*` 与 `Derived*` 既不相似，也不是基类关系，于是落到 ¶3.9，非良构。这也是 `Derived**` 不能隐式转换为 `Base**` 的原因（否则就可以把一个 `Base*` 写进 `Derived*` 的槽位）。

下面改编并扩充了标准的例子：

```cpp ok
#include <type_traits>
#include <utility>
#include <cstddef>
template<class A, class B>
using CPT = decltype(true ? std::declval<A>() : std::declval<B>());

struct Base {}; struct Derived : Base {};
void f(); void g() noexcept;

static_assert(std::is_same_v<CPT<void*, const int*>, const void*>);          // ¶3.3
static_assert(std::is_same_v<CPT<int**, const int**>, const int* const*>);   // ¶3.8：中间层加 const
static_assert(std::is_same_v<CPT<const int**, volatile int**>,
                             const volatile int* const*>);                   // ¶3.8
static_assert(std::is_same_v<CPT<Base*, const Derived*>, const Base*>);      // ¶3.5
static_assert(std::is_same_v<CPT<int Base::*, int Derived::*>, int Derived::*>);  // ¶3.7
static_assert(std::is_same_v<CPT<decltype(&f), decltype(&g)>, void (*)()>);  // ¶3.4
static_assert(std::is_same_v<CPT<std::nullptr_t, int*>, int*>);              // ¶3.2
```

```cpp error
struct Base {}; struct Derived : Base {};
bool a(int* p, long* q)        { return p == q; }  // error: 不相似，¶3.9
bool b(Base** p, Derived** q)  { return p == q; }  // error: Base* 与 Derived* 不引用相关
```

### 为什么 `int**` 与 `const int**` 的复合类型是 `const int* const*`

逐层计算限定合成类型：

| 层 | `int**` | `const int**` | 合成 |
|---|---|---|---|
| cv<sub>0</sub>（最外层指针本身） | — | — | —（最外层不参与） |
| cv<sub>1</sub>（被指的指针） | — | — | 因内层变化，加 `const` |
| cv<sub>2</sub>（最内的 int） | — | `const` | `const`（取并，发生变化） |

结果是 `const int* const*`。如果中间层没有 `const`，合成类型就是 `const int**`，而 `int**` 到 `const int**` 的转换会破坏 const 正确性（[[conv.qual]] 的注释里有完整的反例）。加上中间层的 `const` 后，谁也不能通过合成类型的指针往中间那层写入一个 `const int*`，因此是安全的。

!!! lawyer "数组边界与复合类型：Clang 的偏差"
    限定合成类型还处理已知边界数组与未知边界数组的组合（C++20 起，[[P0388R4]]）：如果某层一方是 `[N]`、另一方是 `[]`，就合成为 `[]`，并且外层加 `const`。按条文计算：

    - `int(*)[3]` 与 `int(*)[]`：变化发生在第 1 层，`0 < k < 1` 没有层需要加 `const`，合成为 `int(*)[]`。
    - `int(**)[3]` 与 `int(**)[]`：变化发生在第 2 层，第 1 层加 `const`，合成为 `int(* const*)[]`。

    截至写作时，Clang 23 对这两例分别给出 `const int(*)[]` 与 `const int(* const*)[]`，也就是额外给数组元素加了 `const`。两种结果都能让双方安全地转换过去，但 Clang 的结果与条文不一致，应视为实现偏差。

## 历史与演进

!!! history
    - C++98/03：复合指针类型的定义位于关系运算符一节，供相等运算符与条件运算符引用，只处理对象指针、`void*` 与空指针常量。后来才移到表达式总则（今天的 [expr.type]）。
    - C++11：加入 `std::nullptr_t`（¶3.1、¶3.2）。
    - C++17：noexcept 成为函数类型的一部分（[[P0012R1]]），于是加入了 ¶3.4、¶3.6。
    - C++20：限定转换扩展到数组边界（[[P0388R4]]），复合指针类型随之能处理 `T[N]` 与 `T[]`。
    - 当前草案：¶1 增加了引用所指不再有效时为 UB 的规定。

## 陷阱

!!! pitfall "`decltype(x)` 与 `decltype((x))`"
    `decltype(r)`（不加括号的名字）得到声明的类型 `int&`；`decltype((r))`（表达式）得到由类型和值类别编码出的 `int&`。对非引用变量 `int i;`，前者是 `int`，后者是 `int&`。对引用变量，两者恰好一致，这掩盖了它们在概念上的区别：一个看声明，一个看表达式。

!!! pitfall "`?:` 混合指针与整数 0"
    `cond ? p : 0` 中的 `0` 是空指针常量，按 ¶3.2，复合类型是 `p` 的类型；但在 `cond ? p : zero`（`int zero = 0;`）中，`zero` 不是空指针常量（[[conv.ptr#1]] 要求整数字面量），所以非良构。

## 思考题

!!! question "1. `Base* const*` 与 `Derived**` 能用 `==` 比较吗？"

<details markdown="1">
<summary>答案</summary>

不能。¶3.5 要求"指向 `C1`"与"指向 `C2`"中的 `C1`、`C2` 引用相关。这里 `C1 = Base* const`、`C2 = Derived*`，去掉 cv 后是 `Base*` 与 `Derived*`，两者既不相似，也不是基类关系。¶3.8 也不适用（类型不相似）。于是落到 ¶3.9，非良构。
</details>

!!! question "2. 设 `const char* s;`，`char* t;`。`s == t` 时 `t` 被转换成什么？`void* v;` 时 `s == v` 呢？"

<details markdown="1">
<summary>答案</summary>

对 `s == t`，`const char*` 与 `char*` 相似，按 ¶3.8 合成为 `const char*`（只有最内层变化，没有中间层需要加 const）；`t` 经限定转换变为 `const char*`。

对 `s == v`，按 ¶3.3 合成为"指向 `const void`"；`s` 经指针转换变为 `const void*`，`v` 经限定转换变为 `const void*`。
</details>

## 小结

!!! summary
    - 表达式的类型永远不是引用：引用被剥去，留下值类别（¶1）；引用指代的对象已不在有效存储中时，求值即 UB。
    - 非类、非数组的 prvalue 没有 cv（¶2）；类/数组 prvalue 保留 cv。
    - 复合指针类型（¶3）依次考虑空指针常量、`void*`、noexcept、基/派生、相似类型的限定合成；限定合成在发生变化的层外侧补 `const`，保证双方都能安全地转换过去。
