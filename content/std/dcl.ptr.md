---
title: 指针与成员指针声明符
summary: 声明符 `* cv D1` 和 `C::* cv D1` 的含义：cv 修饰的是指针本身，为什么 `T**` 不能转换为 `const T**`，哪些东西不能有指针，以及成员指针的声明、限制和在 ABI 中的表示。
status: draft
covers: dcl.ptr, dcl.mptr
related: dcl.decl, dcl.ref, basic.compound, conv.qual, expr.unary.op, expr.mptr.oper, conv.mem, basic.type.qualifier
tags: 指针, 成员指针, const, 声明符
updated: 2026-10-19
---

!!! tldr
    - `*` 后面的 cv 修饰指针本身。要让被指向的对象是 const，`const` 要写在说明符里：`const int *p` 或 `int const *p`。
    - `int*` 可以隐式转换为 `const int*`，但 `int**` 不能转换为 `const int**`，否则可以借它修改 const 对象。需要时要写 `const int* const*`。
    - 不能有指向引用的指针、指向位域的指针，也不能有指向带 cv 或引用限定的函数类型的普通指针。
    - 成员指针 `T C::*` 和指针是不同的类型。声明它不要求 `C` 完整，也不要求 `C` 真有这种类型的成员；它不能指向静态成员、引用成员或 `void`。

这一页讲 [[dcl.decl]] 中声明符的两种前缀运算符：普通指针 `*` 和成员指针 `C::*`。引用 `&`、`&&` 见 [[dcl.ref]]。

## 指针声明符 [dcl.ptr]

### cv 修饰指针本身（¶1）

```cpp run ok
#include <type_traits>

const int ci = 10, *pc = &ci, *const cpc = pc, **ppc;
int i, *p, *const cp = &i;

static_assert(std::is_same_v<decltype(pc),  const int *>);       // 指向 const int
static_assert(std::is_same_v<decltype(cpc), const int *const>);  // const 指针，指向 const int
static_assert(std::is_same_v<decltype(ppc), const int **>);      // 指向 const int* 的指针
static_assert(std::is_same_v<decltype(cp),  int *const>);        // const 指针，指向 int

int main() { }
```

¶1 如果声明 `T D` 中的 `D` 形如 `* cv D1`，名字的类型就是"cv 指向 `T` 的指针"，前面再加上内层声明符 `D1` 积累的修饰（求类型的递归过程见 [[dcl.decl]]）。

!!! std
    The *cv-qualifier*s apply to the pointer and not to the object pointed to.

`*` 后面的 cv 修饰指针本身，不修饰被指向的对象。被指向的类型是说明符给出的 `T`，所以想让对象是 const，`const` 要写进说明符。同理，`*` 后面的属性也属于指针类型。

按这个规则读上面的 `*const cpc`：最外层运算符是 `* const`，它紧贴说明符给出的 `const int`，所以 `cpc` 是指向 `const int` 的 const 指针。

### const 正确性（¶2）

¶2 是一个例子，用同一组变量说明哪些操作可以做：

<div class="compare" markdown="1">

```cpp
// 正确的操作
i = ci;     // 读 const 对象
*cp = ci;   // cp 是 const，*cp 不是
pc++;       // pc 本身不是 const
pc = cpc;   // 复制指针值
pc = p;     // int* → const int*
ppc = &pc;  // 类型相同
```

```cpp
// 非良构的操作
ci = 1;     // error: 修改 const 对象
ci++;       // error
*pc = 2;    // error: 经由指向 const 的指针
cp = &ci;   // error: cp 是 const
cpc++;      // error: cpc 是 const
p = pc;     // error: 丢弃 const
ppc = &p;   // error: int** → const int**
```

</div>

最后一行值得细想。既然 `int*` 转换为 `const int*` 是安全的，为什么 `int**` 转换为 `const int**` 不安全？假如允许 `ppc = &p`，接下来就可以写：

```cpp
*ppc = &ci;   // OK：*ppc 的类型是 const int*，&ci 也是
*p = 5;       // 但 *ppc 就是 p，p 现在指向 ci：修改了 const 对象
```

`ppc` 把一个存放 `int*` 的位置当成存放 `const int*` 的位置来用，`const` 就在不知不觉中丢掉了。所以 [[conv.qual]] 规定，多级指针中某一级加了 `const`，它外面的每一级也都必须加 `const`。`int**` 可以转换为 `const int* const*`，因为外层也是 const，`*ppc = &ci` 就写不了了。

```cpp run ok
int *p;
const int *const *ok = &p;   // OK：外层同时加了 const
int main() { (void)ok; }
```

!!! pitfall "`char**` 传给 `const char**`"
    把 `argv` 这样的 `char**` 传给形参为 `const char**` 的函数时会报错。这不是编译器过于严格，而是在堵上面这个漏洞。应把形参改为 `const char* const*`。

### 不能形成的指针（¶3）

¶3 是一条注，规范性的规定分别在别处：

- 不能有指向引用的指针，因为引用不是对象（[[dcl.ref#5]]）。`int&* p;` 非良构。
- 带 cv 或引用限定符的函数类型，比如 `void() const`，只用来描述非静态成员函数的类型，不能形成普通的函数指针（[[dcl.fct#11]]）；但可以形成成员指针 `void (S::*)() const`。
- 位域不能取地址（[[class.bit]]），所以指针永远不会指向位域。

除此之外，指针可以指向任何对象类型、函数类型、`void`，以及数组，包括未知边界的数组 `int (*)[]`。

## 成员指针 [dcl.mptr]

### 声明成员指针（¶2–3）

```cpp run ok
struct X {
  void f(int) { }
  int a;
};
struct Y;               // 不完整类型

int X::* pmi = &X::a;
void (X::* pmf)(int) = &X::f;
double X::* pmd;        // OK：X 没有 double 成员也可以
char Y::* pmc;          // OK：Y 不完整也可以

int main() {
  X obj;
  obj.*pmi = 7;         // 给 obj.a 赋值
  (obj.*pmf)(7);        // 调用 obj.f(7)
  return obj.a == 7 ? 0 : 1;
}
```

¶2 如果 `D` 形如 `C::* cv D1`，并且 `C::` 指代一个类，名字的类型就是"cv 指向类 `C` 的 `T` 类型成员的指针"。第 3 段的例子就是上面这段代码。

`pmd` 和 `pmc` 都合法，说明成员指针类型只是类和成员类型的组合。声明它既不要求类完整，也不要求类真的有这种成员。要求出现在形成值的时候：`&X::a` 必须找到一个非静态成员（[[expr.unary.op]]）。

调用时 `(obj.*pmf)(7)` 的括号不能省：`.*` 的优先级低于函数调用，`obj.*pmf(7)` 会解析为 `obj.*(pmf(7))`。也可以写 `std::invoke(pmf, obj, 7)`。`.*` 和 `->*` 的规则见 [[expr.mptr.oper]]。

¶2 的最后一句规定，`C::` 不能指代匿名联合体。平常写不出指代匿名联合体的名字，但 C++26 的 [[g:splice-specifier|splice-specifier]] 可以拼出这样的限定符，这一句就是为它准备的。

¶1 *ptr-operator* 的组成名字（component names，[[expr.prim.id.unqual#2]]）就是其中 `C::` 部分的组成名字。名字查找用到这个定义，例如 [[basic.lookup.unqual#5]] 规定转换函数名 `operator T C::*` 里的这些名字怎样查找。

### 不能指向什么（¶4）

¶4 成员指针不能指向静态成员、引用类型的成员，也不能是"指向 cv `void` 的成员指针"。

```cpp run error
struct X { static int s; int& r; };
int X::* p1 = &X::s;   // error: &X::s 的类型是普通指针 int*
int& X::* p2;          // error: 指向引用成员
void X::* p3;          // error: 指向 void
```

静态成员不属于任何对象，`&X::s` 得到的是普通指针。引用不是对象，没有可以记录的位置。

### 成员指针不是指针（¶5）

¶5 是一条注：成员指针和指针是不同的类型。成员指针只能用 `C::*` 语法声明，普通的指针声明符永远不会产生成员指针。C++ 也没有指向成员的引用类型。

所以成员指针不能转换为 `void*`，不能和普通指针比较；`std::is_pointer_v<int X::*>` 是 `false`，`std::is_member_pointer_v<int X::*>` 是 `true`（[[basic.compound]]）。成员指针之间的转换见 [[conv.mem]]：指向基类成员的指针可以转换为指向派生类成员的指针，方向与普通指针相反。

## 实现视角

!!! impl
    - 普通指针在主流平台上就是一个地址。`T* const` 和 `T*` 的表示相同，cv 只在编译期起作用。
    - Itanium C++ ABI（GCC、Clang 在 Linux 和 macOS 上使用）中，数据成员指针是一个 `ptrdiff_t`，存放成员相对对象起点的字节偏移。偏移 0 是合法值，所以空成员指针用 -1 表示。本机（arm64，Clang 23）上，对一个带虚函数、成员为 `int a, b` 的类，`&X::a`、`&X::b` 分别是 8 和 12（前 8 字节是虚表指针），`nullptr` 是 -1。
    - 成员函数指针由两个字 `{ptr, adj}` 组成，`adj` 是调用前对 `this` 的调整量。非虚函数时 `ptr` 是函数地址；虚函数时 `ptr` 编码虚表中的位置。x86-64 用 `ptr` 的最低位标记虚函数；ARM 的变体改用 `adj` 的最低位，因为 Thumb 代码地址的最低位另有用途。本机对第一个虚函数测得 `{0, 1}`。
    - MSVC 的成员指针大小取决于类的继承方式（单继承、多继承、虚继承）。类还不完整时形成的成员指针，只能使用最通用、也最大的表示。这是允许不完整类的成员指针在 ABI 上的代价。

## 历史与演进

!!! history
    - 普通指针的规则继承自 C；成员指针是 C++ 早期就有的特性。
    - C++11 允许在 `*` 和 `C::*` 后面写属性；`nullptr` 可以转换为任何成员指针类型。
    - C++20 统一并放宽了限定转换（[[conv.qual]]），例如允许指向已知边界数组的指针转换为指向未知边界数组的指针。

## 思考题

!!! question "思考题 1"
    `int *const *volatile *p;` 中 `p` 的类型是什么？`p`、`*p`、`**p`、`***p` 中哪些可以赋值？

<details markdown="1">
<summary>答案</summary>

说明符是 `int`，声明符是 `*const *volatile *p`。三个前缀运算符中最左边的 `*const` 最靠外，它紧贴 `int`，得到"指向 `int` 的 const 指针"；下一层 `*volatile` 得到"指向〔前者〕的 volatile 指针"；最内层的 `*` 得到"指向〔前者〕的指针"。

`p` 没有 cv，可以赋值；`*p` 是 volatile 指针，可以赋值，volatile 不阻止写入；`**p` 是 const 指针，不能赋值；`***p` 是 `int`，可以赋值。
</details>

!!! question "思考题 2"
    为什么可以声明指向不完整类成员的指针 `char Y::* pmc;`，却不能写 `sizeof(Y)`？

<details markdown="1">
<summary>答案</summary>

声明 `char Y::*` 只是组合出一个类型，不需要知道 `Y` 的布局，正如声明 `Y*` 不需要 `Y` 完整。只有形成值（`&Y::m` 要查找成员）或者使用它（`obj.*pmc` 要有对象）时，才需要完整的类。`sizeof(Y)` 则必须知道布局。代价体现在 ABI 上：Itanium ABI 的成员指针表示与类无关；MSVC 的表示依赖继承方式，对不完整类只能保守地使用最通用的表示。
</details>
