---
title: cv 限定符
summary: const 和 volatile 怎样作用于类型：每个对象类型都有四个 cv 版本；什么是 const 对象；数组的 cv 属于元素；更多 cv 限定的偏序；顶层 cv 在哪些地方被丢弃。
status: done
papers: P1152R4, P2327R1, CWG2654
related: dcl.type.cv, basic.types, conv.qual, dcl.fct, expr.type, intro.abstract, depr.volatile.type, expr.assign
tags: 类型系统, const, volatile
updated: 2026-10-19
---

!!! tldr
    - 函数和引用以外的每个类型都有四个版本：`T`、`const T`、`volatile T`、`const volatile T`，它们表示和对齐相同。函数类型和引用类型永远不带 cv。
    - 一个对象是不是 [[g:const-object|const 对象]]，在它创建时由它的类型决定。修改 const 对象是 UB；通过 const 指针看到的非 const 对象，去掉 const 后修改是合法的。
    - `const int*` 本身不是 const 类型，cv 不会从成分传到复合类型上。唯一的例外是数组：数组的 cv 就是元素的 cv。
    - [[g:top-level-cv-qualifiers|顶层 cv]] 是直接加在整个类型上的那层 cv。形参类型、按值的模板推导、`auto`、prvalue 的类型都会丢掉它。
    - volatile 访问属于可观察行为，但不是原子的，也不做线程同步。C++20 弃用了 volatile 的几种容易误解的用法。

## 四个 cv 版本（¶1）

`const` 和 `volatile` 合称 **cv 限定符**（cv-qualifiers）。它们写在哪里、怎样组合，语法规则在 [[dcl.type.cv]]；本节讲它们加到类型上之后的含义。

¶1 函数类型和引用类型以外，每个类型都属于一个四类型组：

| 版本 | 以 `int` 为例 |
|---|---|
| cv 无限定（cv-unqualified） | `int` |
| const 限定（const-qualified） | `const int` |
| volatile 限定（volatile-qualified） | `volatile int` |
| const volatile 限定 | `const volatile int` |

这四个类型互不相同，但必须有相同的表示和对齐要求（[[basic.align]]）。脚注 28 说明了目的：让它们作为函数实参、函数返回值、联合的非静态数据成员时可以互换。例如一个 `const int` 的值传给 `int` 形参，内存里的样子不需要任何改变。

函数类型和引用类型永远是 cv 无限定的。通过 typedef 或模板参数给它们加 cv 时，cv 被忽略（[[dcl.ref]]、[[dcl.fct]]）：

```cpp run ok
#include <type_traits>

using Ref = int&;
using Fn  = void(int);

static_assert(std::is_same_v<const Ref, int&>);   // const 被忽略
static_assert(std::is_same_v<const Fn, Fn>);      // const 被忽略
int main() {}
```

程序是良构的，Clang 23 只提示限定符没有效果（`-Wignored-reference-qualifiers`、`-Wignored-qualifiers`）。

## const 对象（¶1.1–¶1.3）

```cpp run ub
int main() {
  int i = 2;
  const int* cip = &i;               // 通过 const 指针看 i，但 i 不是 const 对象
  *const_cast<int*>(cip) = 4;        // OK

  const int* ciq = new const int(3); // 新对象的类型是 const int
  *const_cast<int*>(ciq) = 4;        // UB：修改 const 对象

  struct X { mutable int m; int n; };
  const X x{1, 2};
  x.m = 10;                          // OK：mutable 成员不是 const 对象
  const_cast<X&>(x).n = 20;          // UB：x.n 是 const 对象
  delete ciq;
  return i;
}
```

两次 `const_cast` 写法一样，结果不同。区别在于被修改的对象本身是不是 const 对象。¶1 定义了三种对象：

- ¶1.1 **const 对象**：类型为 `const T` 的对象，或 const 对象的非 mutable 子对象。
- ¶1.2 **volatile 对象**：类型为 `volatile T` 的对象，或 volatile 对象的任何子对象。
- ¶1.3 **const volatile 对象**：类型为 `const volatile T` 的对象、const volatile 对象的非 mutable 子对象、volatile 对象的 const 子对象，或 const 对象的非 mutable volatile 子对象。

注 1 补充，对象的类型包含创建对象时声明或 *new-type-id* 里写出的 cv。所以 const 是对象一出生就带着的性质，与之后通过什么样的指针或引用访问它无关。

[[dcl.type.cv#4]] 规定，在 const 对象的生命期内修改它是 UB。这样规定是为了优化：编译器可以把 const 对象放进只读段，对它做常量折叠，跨函数调用缓存它的值。通过 `const_cast` 的修改一般无法在编译期发现，所以标准没有把它定为编译错误。

!!! note "mutable 只豁免 const"
    ¶1.2 没有非 mutable 的限定：volatile 对象的所有子对象都是 volatile 的。volatile 说的是这块存储可能被程序以外的因素改变，这对整个对象都成立；`mutable` 用于逻辑上的常量性（例如缓存），与此无关。

!!! lawyer "构造和析构期间不算 const"
    const 对象在构造函数和析构函数执行期间不按 const 对待（[[class.ctor]]、[[class.dtor]]），所以 `const Widget w;` 的构造函数可以给成员赋值。[[dcl.type.cv#4]] 说的是在生命期内，而生命期在构造完成后才开始（[[basic.life]]）。

## 复合类型不继承 cv，数组除外（¶2–¶4）

¶2 除数组类型外，复合类型（[[basic.compound]]）不会因为它的成分带有 cv 而成为 cv 限定的类型。

| 类型 | 自身是否 const 限定 | 说明 |
|---|---|---|
| `const int*` | 否 | 指向 const int 的普通指针 |
| `int* const` | 是 | const 指针 |
| `const int&` | 否 | 引用永远不带 cv |
| `struct S { const int x; }` 中的 `S` | 否 | 类不因成员是 const 而成为 const |
| `const int[3]` | 是 | 数组，见 ¶3 |

所以 `std::is_const_v<const int*>` 是 `false`。

¶3 元素带 cv 的数组类型，也被认为带有和元素相同的 cv。注 2 从反方向说明：加在数组类型上的 cv 会落到元素类型上，所以 cv `T`（`T` 是数组类型）指的是元素被这样限定的数组（[[dcl.array]]）。改编自例 1：

```cpp run ok
#include <type_traits>

typedef char CA[5];
typedef const char CC;
CC       arr1[5] = { 0 };     // 5 个 const char 的数组
const CA arr2    = { 0 };     // const 加在数组 typedef 上，落到元素上

static_assert(std::is_same_v<decltype(arr1), decltype(arr2)>);
static_assert(std::is_same_v<decltype(arr1), const char[5]>);
static_assert(std::is_const_v<const char[5]>);   // 数组类型算 const 限定
int main() {}
```

数组不能被整体赋值，没有独立于元素的值，所以不存在数组本身是 const 而元素不是的情况。把 cv 统一归到元素上，避免了两种无法区分的类型。模板里也因此自然：`template<class T> void f(const T&)` 用 `int[3]` 实例化，形参类型是 `const int(&)[3]`。

数组本身也算 cv 限定这句话，是 [[CWG1059]] 的决议补上的。C 在 C17 及以前认为数组类型本身从不带限定，C23 改成了与 C++ 相同的规则。

¶4 是一个注，指向带 cv 的函数类型。成员函数 `void f() const` 的类型写作 `void() const`，这里的 `const` 修饰隐式对象形参（[[dcl.fct]]、[[over.match.funcs]]），函数类型本身仍然是 cv 无限定的。

## 更多 cv 限定（¶5）

```cpp run ok
#include <cstdio>

void f(const int&)          { std::puts("const int&"); }
void f(const volatile int&) { std::puts("const volatile int&"); }

int main() {
  int i = 0;
  f(i);          // 两个都可行，const int& 的 cv 更少，更好
  volatile int v = 0;
  f(v);          // const int& 不可行（不能丢掉 volatile）
}
```

程序依次打印 `const int&` 和 `const volatile int&`。重载决议要比较两个类型谁的 cv 多，用的就是 ¶5 定义的偏序。

¶5 cv 限定符之间有一个偏序，据此可以说一个类型比另一个**更多 cv 限定**（more cv-qualified）。表 16 列出了全部关系：

| 较少 | | 较多 |
|---|---|---|
| 无 cv | < | `const` |
| 无 cv | < | `volatile` |
| 无 cv | < | `const volatile` |
| `const` | < | `const volatile` |
| `volatile` | < | `const volatile` |

可以把它看作集合 {const, volatile} 的子集之间的包含关系。`const` 和 `volatile` 互不包含，无法比较，所以这是偏序。

用到[[g:more-cv-qualified|更多 cv 限定]]这个偏序的规则主要有三处：

- 限定转换只能增加 cv（[[conv.qual]]）：`int*` 可以转换为 `const int*`，反过来不行。
- 引用绑定：`cv1 T` 的引用要绑定到 `cv2 T` 的对象，cv1 不能比 cv2 少（[[dcl.init.ref]]）。
- 重载决议：两个引用绑定只在 cv 上不同时，cv 少的那个更好（[[over.ics.rank]]），即上面的例子。

## 顶层 cv（¶6）

¶6 标准描述类型时，记号 cv（或 cv1、cv2）表示任意一个 cv 集合：{const}、{volatile}、{const, volatile} 或空集。对类型 cv `T`，cv 所表示的那些限定符就是它的**顶层 cv 限定符**（top-level cv-qualifiers）。直观地说，顶层 cv 是直接加在整个类型上的那一层。例 2 给了三个例子：

| *type-id* | 顶层 cv | 原因 |
|---|---|---|
| `const int&` | 无 | 引用不带 cv，`const` 属于被引用的类型 |
| `volatile int * const` | `const` | 指针本身是 const，`volatile` 属于被指向的类型 |
| `void (C::* volatile)(int) const` | `volatile` | 成员指针本身是 volatile，末尾的 `const` 属于成员函数类型 |

许多规则只丢弃顶层 cv：

```cpp run ok
#include <type_traits>

void f(int);
void f(const int);           // 同一个函数的重复声明
void f(int) {}

void g(int*);
void g(const int*);          // 两个不同的重载：const 不在顶层

const int k();
static_assert(std::is_same_v<decltype(k()), int>);   // prvalue 的 cv 被去掉

int main() {
  const int ci = 0;
  auto a = ci;                                     // auto 丢弃顶层 const
  static_assert(std::is_same_v<decltype(a), int>);
  int* const p = nullptr;
  auto q = p;                                      // q 是 int*
  static_assert(std::is_same_v<decltype(q), int*>);
}
```

1. 形参类型调整（[[dcl.fct]]）删除形参的顶层 cv，所以 `void f(int)` 和 `void f(const int)` 是同一个函数。形参上的 `const` 只影响函数体内能否修改这个局部变量。
2. 按值传参的模板实参推导（[[temp.deduct.call]]）忽略顶层 cv：`template<class T> void h(T);` 用 `const int` 实参调用，推导出 `T = int`。`auto` 按同样的规则推导。
3. 非类、非数组类型的 prvalue 如果类型是 cv `T`，类型调整为 `T`（[[expr.type#2]]）。所以返回 `const int` 的函数，调用表达式的类型是 `int`，Clang 会提示返回类型上的 const 没有效果。

在 Itanium C++ ABI（GCC、Clang 在 Linux、macOS 上使用）中，函数形参的顶层 cv 也不进入修饰名，`f(int)` 和 `f(const int)` 的符号相同。

## volatile 的语义与弃用

本节只定义了什么是 volatile 对象。volatile 的语义在别处：

- [[dcl.type.cv#5]]：通过 volatile glvalue 访问的语义由实现定义；通过非 volatile glvalue 访问一个以 volatile 类型定义的对象是 UB。
- [[intro.abstract]]：通过 volatile glvalue 的访问属于可观察行为，编译器不能省略或合并它们，也不能改变它们之间的顺序。
- volatile 不提供原子性，也不建立线程间的 happens before 关系。多线程同步要用 `std::atomic`（[[atomics]]）。

C++20 的 [[P1152R4]] 弃用了 volatile 的几种用法，它们暗示了 volatile 并不提供的原子性或单次访问。当前草案中仍然弃用的有（[[depr.volatile.type]]）：

| 用法 | 状态 |
|---|---|
| volatile 算术或指针类型的 `++`、`--` | 弃用：`++v` 是一次读加一次写，常被误以为是原子的 |
| 左操作数是 volatile 非类类型的赋值，且结果被使用（如 `x = v = 1`） | 弃用（[[expr.assign#5]]） |
| 作为单独语句的赋值和复合赋值，如 `v = 1`、`v += 1`、<code>v &#124;= mask</code> | 不弃用 |
| 函数类型带 volatile 形参或 volatile 返回类型 | 弃用：按值传递的 volatile 没有意义 |
| volatile 限定的结构化绑定 | 弃用 |

复合赋值有过一次反复。C++20 把它们一并弃用，但嵌入式代码里 `REG |= BIT` 这类寄存器操作随处可见。[[P2327R1]] 先撤销了按位复合赋值的弃用，[[CWG2654]] 又撤销了其余复合赋值的弃用。

```cpp run ok
volatile int reg;
int x;

void f() {
  reg |= 0x4;      // OK
  reg += 1;        // OK
  reg = 3;         // OK：赋值是弃值表达式
  ++reg;           // 弃用
  x = reg = 2;     // 弃用：使用了 volatile 赋值的结果
}
void g(volatile int);   // 弃用：volatile 形参

int main() { f(); }
```

Clang 23 在 `-std=c++2c` 下对 `++reg`、`x = reg = 2` 和 `g` 的声明给出 `-Wdeprecated-volatile` 警告，对 `reg |= 0x4` 和 `reg += 1` 不警告，与当前草案一致。

!!! impl "实现视角"
    - 静态存储期、常量初始化的 const 对象通常放在只读段（ELF 的 `.rodata`，Mach-O 的 `__TEXT,__const`），`const_cast` 之后写入会触发段错误。有动态初始化或 mutable 成员的 const 对象只能放在可写段。
    - GCC 和 Clang 让每次 volatile 访问对应一条同宽度的加载或存储指令，不与其他 volatile 访问重排，但不插入内存屏障。MSVC 的 `/volatile:ms` 模式给 volatile 附加了 acquire/release 语义，这是扩展，ARM 目标上默认是 `/volatile:iso`。

## 常见误解

!!! pitfall "`const` 指针和指向 `const` 的指针"
    `const int* p` 可以改 `p`，不能改 `*p`；`int* const p` 正相反。从右往左读声明：`int* const` 是指向 int 的 const 指针。

!!! pitfall "`const_cast` 本身是 UB"
    去掉 const 总是合法的，UB 只发生在随后修改了一个 const 对象时。反过来，不用 `const_cast`，通过 `memcpy` 等手段修改 const 对象同样是 UB。

!!! pitfall "volatile 可以用来做线程同步"
    C++ 的 volatile 与 Java 不同，不提供原子性，也不建立 happens before。两个线程不加同步地读写同一个 `volatile int`，仍然是数据竞争（[[intro.races]]）。

## 思考题

!!! question "1. `using A = int[3]; const A* p;` 中 `p` 的类型是什么？`std::is_const_v<std::remove_pointer_t<decltype(p)>>` 的值是多少？"

<details markdown="1">
<summary>答案</summary>

`const A` 中的 const 落到元素上，`const A` 就是 `const int[3]`，所以 `p` 的类型是 `const int (*)[3]`。按 ¶3，`const int[3]` 算 const 限定的类型，结果为 `true`。
</details>

!!! question "2. `struct S { mutable int m; const int c; int n; }; const S cs{1,2,3}; S s{1,2,3};` 中哪些是 const 对象？"

<details markdown="1">
<summary>答案</summary>

- `cs` 的类型是 `const S`，是 const 对象。
- `cs.m` 是 const 对象的 mutable 子对象，不是 const 对象。
- `cs.c` 和 `cs.n` 是 const 对象的非 mutable 子对象，都是 const 对象。
- `s` 不是 const 对象，但 `s.c` 的类型是 `const int`，它是 const 对象。`s.m`、`s.n` 不是。

所以 `const_cast<int&>(s.c) = 0;` 也是 UB（¶1.1、[[dcl.type.cv#4]]）。
</details>

!!! question "3. 为什么 `void f(volatile int)` 被弃用，`void g(volatile int*)` 却没有？"

<details markdown="1">
<summary>答案</summary>

`volatile int` 形参是按值传入的局部副本，这个 volatile 是顶层 cv，不进入函数类型，调用者看不到。它只让函数体内对副本的访问不被优化，几乎从来不是作者的本意。`volatile int*` 里的 volatile 不在顶层，说明被指向的对象（通常是硬件寄存器）需要 volatile 访问，是接口的一部分。[[depr.volatile.type]] 的例 3 对比的正是这两种写法。
</details>
