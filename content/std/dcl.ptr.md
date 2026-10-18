---
title: 指针与成员指针声明符
summary: 声明符 `* cv D1` 与 `C::* cv D1`：cv 修饰的是指针本身、const 正确性为何禁止 `T**` → `const T**`、哪些东西不能有指针；成员指针的声明、限制与 ABI 表示
status: draft
covers: dcl.ptr, dcl.mptr
related: dcl.decl, dcl.ref, basic.compound, conv.qual, expr.unary.op, expr.mptr.oper, conv.mem, basic.type.qualifier
tags: 指针, 成员指针, const, 声明符
updated: 2026-10-17
---

[[dcl.decl]] 给出了从 `T D` 递归求类型的总框架，本页覆盖其中两种前缀运算符：普通指针 `*`（[dcl.ptr]）和成员指针 `C::*`（[dcl.mptr]）。引用 `&`/`&&` 单独成页，见 [[dcl.ref]]。

这两节本身很短，但 `const` 正确性、指针不等于成员指针这些类型系统的基本事实都出自这里。阅读之前最好先了解复合类型的分类（[[basic.compound]]）与 cv 限定（[[basic.type.qualifier]]）。

## 指针声明符（[dcl.ptr] ¶1）

¶1 在声明 `T D` 中，如果 `D` 形如

```
* attribute-specifier-seq(opt) cv-qualifier-seq(opt) D1
```

且 `T D1` 中 *declarator-id* 的类型是"*derived-declarator-type-list* `T`"，那么 `D` 中 *declarator-id* 的类型是"*derived-declarator-type-list* *cv-qualifier-seq* 指向 `T` 的指针"。

!!! std
    The *cv-qualifier*s apply to the pointer and not to the object pointed to.

    `*` 后面的 cv 限定符修饰**指针本身**，而不是被指向的对象。

同理，`*` 后面的属性属于指针类型。要让被指对象是 const，cv 必须出现在说明符里（`const int *p` 或 `int const *p`），因为说明符给出的 `T` 才是被指向的类型。

```cpp title="ptr-cv.cpp" ok
#include <type_traits>

const int ci = 10, *pc = &ci, *const cpc = pc, **ppc;
int i, *p, *const cp = &i;

static_assert(std::is_same_v<decltype(pc),  const int *>);        // 指向 const int 的指针
static_assert(std::is_same_v<decltype(cpc), const int *const>);   // const 指针，指向 const int
static_assert(std::is_same_v<decltype(ppc), const int **>);       // 指向〔指向 const int 的指针〕的指针
static_assert(std::is_same_v<decltype(cp),  int *const>);         // const 指针，指向 int

int main() { }
```

读法与 [[dcl.decl]] 一致。`*const cpc` 中最外层运算符是 `* const`，它紧贴说明符给出的 `const int`，所以 `cpc` 是指向 `const int` 的 const 指针。

## const 正确性（¶2）

¶2（例）标准用一组赋值说明 cv 的作用。正确的操作：

```cpp title="ptr-ops-ok.cpp" ok
const int ci = 10, *pc = &ci, *const cpc = pc, **ppc;
int i, *p, *const cp = &i;

void ok() {
    i = ci;       // 读 const 对象，OK
    *cp = ci;     // cp 本身是 const，但它指向的 int 可以改
    pc++;         // pc 本身不是 const
    pc = cpc;     // 复制指针值
    pc = p;       // int* → const int*：限定转换，OK
    ppc = &pc;    // const int** ← const int**，类型相同
}
int main() { ok(); }
```

非良构的操作：

```cpp title="ptr-ops-bad.cpp" error
const int ci = 10, *pc = &ci, *const cpc = pc, **ppc;
int i, *p, *const cp = &i;

void bad() {
    ci = 1;       // error: 修改 const 对象
    ci++;         // error
    *pc = 2;      // error: 通过指向 const 的指针修改
    cp = &ci;     // error: cp 是 const 指针；且 &ci 是 const int*
    cpc++;        // error: cpc 是 const 指针
    p = pc;       // error: const int* → int* 会丢弃 const
    ppc = &p;     // error: int** → const int** 不是合法的限定转换
}
```

最后一行最值得深究。既然 `int*` → `const int*` 是安全的，为什么 `int**` → `const int**` 不安全？标准给出了反例。假如允许 `ppc = &p`：

```cpp
*ppc = &ci;   // OK：*ppc 的类型是 const int*，&ci 也是
*p = 5;       // 而 p 和 *ppc 是同一个对象——p 现在指向 ci，这里修改了 const 对象！
```

一个存放指向 const 的指针的位置，被当成存放指向非 const 的指针的位置来用，const 就在不知不觉中丢掉了。所以 [[conv.qual]] 规定，在多级指针中，如果某一级加了 `const`，它外面的每一级也都必须是 `const`。`int**` → `const int* const*` 是合法的，因为外层也加了 const，`*ppc = &ci` 就写不了了。

```cpp title="qual-conv.cpp" ok
int *p;
const int *const *ok = &p;    // OK：外层同时加 const
int main() { (void)ok; }
```

## 不能有指针的东西（¶3）

¶3（注）下面三条限制在其他条款中都有规范性来源：

- 不能有指向引用的指针，因为引用不是对象（[[dcl.ref#5]]）。`int&* p;` 非良构。
- 不能有指向带 cv 或 ref 限定符的函数类型的指针。这种函数类型（俗称 abominable function type）只能作为非静态成员函数的类型存在，不能形成普通函数指针（[[dcl.fct#11]]），但可以形成成员指针：`int (S::*)() const`。
- 指针不能指向位域，因为位域不能取地址（[[class.bit]]）。

除此之外，指针可以指向任何对象类型、函数类型、`void`（`void*`），以及数组（`int (*)[3]`），包括未知边界的数组（`int (*)[]`）。

## 成员指针（[dcl.mptr]）

### 声明形式（¶1–3）

¶2 如果 `D` 形如

```
nested-name-specifier * attribute-specifier-seq(opt) cv-qualifier-seq(opt) D1
```

且 *nested-name-specifier* 指代一个类 `C`，`T D1` 中 *declarator-id* 的类型是"*list* `T`"，那么 `D` 中 *declarator-id* 的类型是"*list* *cv* 指向类 `C` 的 `T` 类型成员的指针"。*nested-name-specifier* 不得指代匿名联合体。匿名联合体没有可以写出来的名字，但在某些情况下（例如借助反射的 *splice-specifier*）可以构造出指代它的 *nested-name-specifier*，¶2 禁止了这种用法。

¶1 规定 *ptr-operator* 的**组成名字**（component names，[[expr.prim.id.unqual#2]]）就是其 *nested-name-specifier* 的组成名字。名字查找规则引用了这条定义，例如 [[basic.lookup.unqual#5]] 规定，转换函数名 `operator T C::*` 中 *ptr-operator* 的组成名字要按转换函数名的方式查找（先在类中找）。

```cpp title="mptr-decl.cpp" ok
struct X {
    void f(int) { }
    int a;
};
struct Y;              // 不完整类型

int X::* pmi = &X::a;
void (X::* pmf)(int) = &X::f;
double X::* pmd;       // OK：X 没有 double 成员也没关系，这只是一个类型
char Y::* pmc;         // OK：Y 不完整也可以

int main() {
    X obj;
    obj.*pmi = 7;      // 通过成员指针给 obj.a 赋值
    (obj.*pmf)(7);     // 通过成员指针调用 obj.f(7)——括号必需：.* 的优先级低于 ()
    return obj.a == 7 ? 0 : 1;
}
```

`pmd` 与 `pmc` 合法，说明成员指针类型只是类与成员类型的组合，声明它既不要求类完整，也不要求类真有这样的成员。真正的约束在形成值的时候：`&X::a` 必须找到一个可访问的非静态成员（[[expr.unary.op]]）。

### 不能指向什么（¶4）

¶4 成员指针不能指向：

- 静态成员：`&X::s` 的类型是普通指针 `int*`，静态成员不属于对象；
- 引用类型的成员：引用不是对象，没有偏移量可言；
- cv `void`：`void X::*` 没有意义。

```cpp title="mptr-bad.cpp" error
struct X { static int s; int& r; };
int X::* p1 = &X::s;     // error: &X::s 是 int*，不是 int X::*
int& X::* p2;            // error: 指向引用成员的成员指针
void X::* p3;            // error: 指向 void 的成员指针
```

### 成员指针不是指针（¶5）

¶5（注）指向成员的指针与指针是**不同的类型**。成员指针只能用 `C::*` 语法声明，普通指针声明符永远不会产生成员指针；也不存在成员引用类型（没有 `int X::&`）。

由此可知：

- 成员指针不能转换为 `void*`，不能与普通指针比较，不能用 `reinterpret_cast` 在成员指针与普通指针之间转换；
- `std::is_pointer_v<int X::*>` 为 `false`，`std::is_member_pointer_v` 为 `true`（[[basic.compound]] 把它们列为不同的复合类型）；
- 成员指针之间的转换规则（派生 → 基的逆变）见 [[conv.mem]]，运算符 `.*` / `->*` 见 [[expr.mptr.oper]]。

## 实现视角

!!! impl
    - 普通指针在所有主流平台上就是一个地址。`T* const` 与 `T*` 表示相同，cv 只在编译期起作用。
    - 数据成员指针（Itanium C++ ABI）是一个 `ptrdiff_t`，存放成员相对对象起始的字节偏移。空成员指针用 -1 表示，因为偏移 0 是合法值（第一个成员）。本机（arm64，Clang）上 `sizeof(int X::*) == 8`，`&X::a`、`&X::b` 分别为 8、12（前 8 字节是 vptr），`nullptr` 为 -1。
    - 成员函数指针（Itanium）由两个字 `{ptr, adj}` 组成。非虚函数时 `ptr` 是函数地址，`adj` 是 `this` 调整量；虚函数时 `ptr` 编码虚表中的偏移。x86-64 上用 `ptr` 的最低位标记虚函数（函数地址至少 2 字节对齐）；ARM（含 AArch64）的变体改用 `adj` 的最低位，因为 Thumb 函数地址的最低位已有他用。本机实测虚函数 `&X::g` 的表示为 `{0, 1}`。
    - MSVC：成员指针的大小取决于类的继承模型（单继承 / 多继承 / 虚继承 / 未知），在类定义完整之前形成的成员指针可能只能使用最通用（也最大）的表示；`/vmg`、`#pragma pointers_to_members` 以及 `__single_inheritance` 等关键字可以控制这一点。这是 ¶3 允许不完整类的成员指针在 ABI 层面付出的代价。

## 历史与演进

!!! history
    - C++98：普通指针规则继承自 C；成员指针是 C++ 早期就引入的特性。
    - C++11：属性说明符序列可以出现在 `*` 与 `C::*` 之后。`nullptr` 可以转换为任何成员指针类型。
    - C++20：[[conv.qual]] 的限定转换规则得到统一和放宽（例如允许涉及未知边界数组的转换）；`const&` 限定的成员函数指针可以通过右值对象调用（[[expr.mptr.oper]]）。
    - C++26：*nested-name-specifier* 可以包含 *splice-specifier*（反射），¶2 中禁止指代匿名联合体的限制在此背景下有实际意义。

## 陷阱

!!! pitfall "`const` 读法"
    `const char *p` 可以改 `p`、不能改 `*p`；`char *const p` 不能改 `p`、可以改 `*p`。一个记忆方法是：`const` 修饰它左边紧邻的成分；如果左边没有成分（`const` 在最前面），就修饰右边紧邻的成分。按文法理解更可靠：说明符中的 cv 属于 `T`，`*` 后面的 cv 属于指针本身。

!!! pitfall "typedef 不是宏"
    `typedef char *PC; const PC p;` 是 `char *const p`，不是 `const char *p`。`const` 修饰的是 `PC` 这个完整的类型（指针）。

!!! pitfall "`T**` 不能隐式转换为 `const T**`"
    把 `char**`（如 `argv`）传给接受 `const char**` 的函数时常会遇到这个问题。这不是编译器过于严格，而是为了堵住 ¶2 例子展示的真实漏洞。应把形参改为 `const char* const*`。

!!! pitfall "成员函数指针调用的括号"
    `obj.*pmf(7)` 解析为 `obj.*(pmf(7))`，这是错误的。必须写 `(obj.*pmf)(7)`，或者用 `std::invoke(pmf, obj, 7)`。

## 思考题

!!! question "思考题 1"
    `int *const *volatile *p;` 中 `p` 的类型是什么？`p`、`*p`、`**p`、`***p` 中哪些可以赋值？

<details markdown="1">
<summary>答案</summary>

说明符是 `int`，声明符是 `*const *volatile *p`。三个前缀运算符中，最左边的 `*const` 最靠外，所以它紧贴 `int`，得到"const 指针 → `int`"；剥掉它，下一层 `*volatile` 得到"volatile 指针 → 〔const 指针 → `int`〕"；最内层 `*p` 得到"指针 → 〔volatile 指针 → 〔const 指针 → `int`〕〕"。

即 `p` 的类型是 `int *const *volatile *`。`p` 可赋值（无 cv）；`*p` 是 volatile 指针，可赋值（volatile 不阻止写）；`**p` 是 const 指针，不可赋值；`***p` 是 `int`，可赋值。
</details>

!!! question "思考题 2"
    为什么成员指针可以指向不完整类的成员（`char Y::* pmc;`），而 `sizeof(Y)` 却不行？

<details markdown="1">
<summary>答案</summary>

声明 `char Y::*` 只是组合出一个类型，不需要知道 `Y` 的布局，就像 `Y*` 不需要 `Y` 完整一样。只有在形成值（`&Y::m`，需要查找成员）或使用（`obj.*pmc`，需要对象）时才需要完整类型。代价体现在 ABI 层面：Itanium ABI 的成员指针表示与类无关，没有问题；MSVC 的表示依赖继承模型，对不完整类只能保守地使用最通用的表示。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | `* cv D1` | cv 修饰指针本身；被指类型的 cv 写在说明符里 |
    | const 正确性 | `T*` → `const T*` 安全；`T**` → `const T**` 不安全，须 `const T* const*` |
    | 不能有指针 | 引用、带 cv/ref 限定的函数类型（但可有成员指针）、位域 |
    | `C::* cv D1` | 成员指针；类可以不完整、可以没有这种成员 |
    | 成员指针不能指向 | 静态成员、引用成员、`void` |
    | 类型系统 | 成员指针 ≠ 指针；没有成员引用 |
    | ABI | Itanium：数据成员指针 = 偏移（空 = -1），成员函数指针 = `{ptr, adj}` |
