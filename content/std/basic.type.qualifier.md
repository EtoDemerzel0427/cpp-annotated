---
title: cv 限定符
summary: 每个对象类型都有 const/volatile 四个版本；const 对象与 volatile 对象的精确定义；数组的 cv 归属元素；更多 cv 限定的偏序；顶层 cv
status: draft
papers: P1152R4, P2327R1
related: dcl.type.cv, basic.types, conv.qual, dcl.fct, expr.type, intro.abstract, depr.volatile.type, expr.assign
tags: 类型系统, const, volatile
updated: 2026-10-17
---

`const` 与 `volatile` 是 C++ 类型系统中仅有的两个**类型限定符**（cv-qualifiers）。语法层面的规则（`cv-qualifier` 能写在哪里、重复限定被忽略、修改 const 对象是 UB）在 [[dcl.type.cv]]；本节（[[basic.type.qualifier]]，6.9.6）则从类型的角度回答这些问题：cv 限定后的类型和原类型是什么关系？什么叫 const 对象？数组、指针、函数上的 cv 归属于谁？更多 cv 限定如何比较？什么是顶层 cv？

这些定义被大量其他规则引用：限定转换（[[conv.qual]]）、引用绑定（[[dcl.init.ref]]）、重载决议中的隐式转换序列排序（[[over.ics.rank]]）、模板实参推导（[[temp.deduct.call]]）、形参类型调整（[[dcl.fct]]）、prvalue 的 cv 剥离（[[expr.type#2]]）。

## cv 的四个版本（¶1）

¶1 规定，除函数类型和引用类型之外，每个类型都属于一个由四个不同但相关的类型组成的组：

| 版本 | 例（以 `int` 为例） |
|---|---|
| cv 无限定（cv-unqualified） | `int` |
| const 限定（const-qualified） | `const int` |
| volatile 限定（volatile-qualified） | `volatile int` |
| const volatile 限定 | `const volatile int` |

同一组中的类型必须具有**相同的表示和对齐要求**。脚注 28 说明了这条要求的意图：使它们作为函数实参、函数返回值、联合的非静态数据成员时可以互换。例如通过 `int` 形参传入 `const int` 的值，或在联合中以 `const int` 成员写入、以 `int` 成员读出时，表示不会有差异。

**函数类型和引用类型总是 cv 无限定的**。通过 typedef 或模板参数给它们加上 cv 时，cv 被忽略（[[dcl.ref]]、[[dcl.fct]]）：

```cpp run ok
#include <type_traits>

using Ref = int&;
using Fn  = void(int);

static_assert(std::is_same_v<const Ref, int&>);   // const 作用于引用类型：被忽略
static_assert(std::is_same_v<const Fn, Fn>);      // const 作用于函数类型：被忽略
static_assert(!std::is_const_v<const Ref>);
int main() {}
```

（这是良构的；Clang 会提示限定符无效：对引用是 `-Wignored-reference-qualifiers`，对函数类型是 `-Wignored-qualifiers`。）

### const 对象与 volatile 对象（¶1.1–¶1.3）

¶1 接着定义了三种对象。注意这里定义的是对象的性质，不是表达式或类型的性质：

- ¶1.1 **const 对象**：类型为 `const T` 的对象，或 const 对象的非 mutable 子对象。
- ¶1.2 **volatile 对象**：类型为 `volatile T` 的对象，或 volatile 对象的子对象（任何子对象都算，`mutable` 不影响 volatile）。
- ¶1.3 **const volatile 对象**：类型为 `const volatile T` 的对象；const volatile 对象的非 mutable 子对象；volatile 对象的 const 子对象；const 对象的非 mutable volatile 子对象。

Note 1 指出，对象的类型包括**创建对象时**在 *decl-specifier-seq*、*declarator*、*type-id* 或 *new-type-id* 中给出的 cv 限定符。也就是说，一个对象是不是 const 对象，在它创建时就确定了，与之后通过什么样的指针或引用访问它无关。

[[dcl.type.cv#4]] 中最常被误解的 UB 就建立在这一区分上：**修改 const 对象是 UB；而一个非 const 对象，即使是通过 const 访问路径看到的，去掉 const 后修改也完全合法**。

```cpp run ub
int main() {
  int i = 2;
  const int* cip = &i;               // const 访问路径，但对象 i 不是 const 对象
  *const_cast<int*>(cip) = 4;        // OK：i 是非 const 对象

  const int* ciq = new const int(3); // 对象类型是 const int → const 对象
  *const_cast<int*>(ciq) = 4;        // UB：修改 const 对象

  struct X { mutable int m; int n; };
  const X x{1, 2};
  x.m = 10;                          // OK：mutable 子对象不是 const 对象
  const_cast<X&>(x).n = 20;          // UB：x.n 是 const 对象的非 mutable 子对象
  delete ciq;
  return i;
}
```

为什么标准把修改 const 对象规定为 UB，而不仅仅是编译错误？因为编译器想利用 const 对象的值不会改变这一点来优化：把它放进只读段（`.rodata`），对它的读取做常量折叠，跨函数调用缓存它的值。而通过 `const_cast` 进行的修改，一般无法在编译期检测出来。

!!! note "mutable 与 volatile 的不对称"
    `mutable` 只能豁免 const，不能豁免 volatile：volatile 对象的所有子对象都是 volatile 对象（¶1.2 没有非 mutable 的限定）。原因是 volatile 描述的是这块存储可能被程序之外的因素改变，这对整个对象的存储都成立；而 `mutable` 的设计意图（逻辑常量性，如缓存）与此无关。

!!! lawyer "构造与析构期间的 const"
    const 对象在构造函数和析构函数执行期间不被当作 const：[[class.ctor]] 与 [[class.dtor]] 规定，const 语义从最派生对象的构造函数结束时开始，到析构函数开始时结束。所以 `const Widget w;` 的构造函数可以给成员赋值。[[dcl.type.cv#4]] 中"在其生存期内"一语也与此呼应，因为生存期在构造完成后才开始（[[basic.life]]）。

## 复合类型不继承成分的 cv（¶2）

¶2 规定，除数组类型外，复合类型（[[basic.compound]]）不会因为构成它的类型带有 cv 限定而成为 cv 限定的类型。

| 类型 | 自身是否 const 限定 | 说明 |
|---|---|---|
| `const int*` | 否 | 指向 const int 的（非 const）指针 |
| `int* const` | 是 | const 指针 |
| `const int&` | 否 | 引用永远 cv 无限定 |
| `const int()`（返回 `const int` 的函数） | 否 | 函数类型永远 cv 无限定 |
| `struct S { const int x; }` 中的 `S` | 否 | 类类型不因成员 const 而 const |
| `const int[3]` | **是** | 数组：见 ¶3 |

所以 `std::is_const_v<const int*>` 为 `false`，这个结果常让初学者意外。

## 数组的 cv 属于元素（¶3–¶4）

¶3 规定，元素被 cv 限定的数组类型，也被认为具有与元素**相同的 cv 限定**。Note 2 指出，作用于数组类型的 cv 限定符会附着到元素类型上，所以记号 cv `T`（`T` 为数组类型）指的是元素被如此限定的数组（[[dcl.array]]）。

改编自标准 Example 1：

```cpp run ok
#include <type_traits>

typedef char CA[5];
typedef const char CC;
CC       arr1[5] = { 0 };     // 5 个 const char 的数组
const CA arr2    = { 0 };     // const 加在数组 typedef 上 → 也落到元素上

static_assert(std::is_same_v<decltype(arr1), decltype(arr2)>);
static_assert(std::is_same_v<decltype(arr1), const char[5]>);
static_assert(std::is_const_v<const char[5]>);   // 数组类型"被认为是 const 限定的"
int main() {}
```

这条规则的动机是：C++ 中不存在数组本身是 const 而元素不是的情况，因为数组没有独立于元素、可以修改的值（数组不能被赋值）。把 cv 统一归到元素上，既避免了出现两种不同却无法区分的类型，又让 `const T`（`T` 是数组类型）在模板中表现为整个对象只读。例如 `template<class T> void f(const T&)` 用 `int[3]` 实例化时，形参类型是 `const int(&)[3]`。

!!! history "演进与 C 的差异"
    C++98 只说作用于数组类型的 cv 限定符附着到元素类型上，并没有说数组类型本身也算 cv 限定；元素被 cv 限定的数组类型也被认为具有相同的 cv 限定，这一句是后来通过核心问题决议补上的（C++14 前后）。C 在 C17 及之前认为数组类型本身从不被限定；C23 修改了规则，使数组类型与元素类型具有相同的限定，与 C++ 一致。

¶4 是一个注：带 *cv-qualifier* 的函数类型（如非静态成员函数 `void f() const` 的类型 `void() const`）见 [[dcl.fct]] 与 [[over.match.funcs]]。这里的 `const` 修饰的是隐式对象形参，函数类型本身仍然是 cv 无限定的。这类类型俗称 abominable function types，只能出现在少数位置（如成员指针 `void (C::*)() const`）。

## 更多 cv 限定的偏序（¶5）

¶5 规定，cv 限定符之间有一个偏序，据此可以说一个类型比另一个**更多 cv 限定**（more cv-qualified）。表 16 列出了构成这个偏序的关系：

| 较少 | | 较多 |
|---|---|---|
| 无 cv | < | `const` |
| 无 cv | < | `volatile` |
| 无 cv | < | `const volatile` |
| `const` | < | `const volatile` |
| `volatile` | < | `const volatile` |

注意 `const` 与 `volatile` 不可比较，所以这是偏序而不是全序。可以把它看作集合 {const, volatile} 的子集之间的包含关系。

使用这个偏序的规则举例如下：

- 限定转换只能增加 cv（[[conv.qual]]）：`int*` → `const int*` 可以，反之不行。
- 引用绑定：`cv1 T1` 的引用能绑定到 `cv2 T2`，前提之一是 cv1 不少于 cv2（引用相容，[[dcl.init.ref]]）。
- 重载决议：两个引用绑定只在 cv 上不同时，cv 更少的那个更好（[[over.ics.rank]]）：

```cpp run ok
#include <cstdio>

void f(const int&)          { std::puts("const int&"); }
void f(const volatile int&) { std::puts("const volatile int&"); }

int main() {
  int i = 0;
  f(i);          // 两者都可行；const int& 的 cv 更少 → 更好
  volatile int v = 0;
  f(v);          // const int& 不可行（不能丢掉 volatile）→ const volatile int&
}
```

## cv 记号与顶层 cv（¶6）

¶6 规定，本标准在描述类型时，记号 cv（或 *cv1*、*cv2* 等）表示任意一个 cv 限定符集合：{const}、{volatile}、{const, volatile} 或空集。对类型 cv `T`，其**顶层 cv 限定符**（top-level cv-qualifiers）就是 cv 所表示的那些限定符。

标准 Example 2 给出了三个例子：

| *type-id* | 顶层 cv | 解释 |
|---|---|---|
| `const int&` | 无 | 引用类型没有 cv；`const` 属于被引用类型 |
| `volatile int * const` | `const` | 指针本身是 const；`volatile` 属于被指向类型 |
| `void (C::* volatile)(int) const` | `volatile` | 成员指针本身是 volatile；末尾的 `const` 属于成员函数类型 |

顶层 cv 之所以重要，是因为**许多规则只丢弃顶层 cv**：

1. 函数形参类型调整（[[dcl.fct]]）：形参类型的顶层 cv 被删除，所以 `void f(int)` 与 `void f(const int)` 声明的是同一个函数；但 `void g(int*)` 与 `void g(const int*)` 是两个重载。
2. 模板实参推导（[[temp.deduct.call]]）：按值传参时忽略 `P` 与 `A` 的顶层 cv。`template<class T> void h(T); const int ci = 0; h(ci);` 推导出 `T = int`。
3. prvalue 的类型调整（[[expr.type#2]]）：如果非类、非数组类型的 prvalue 具有 cv `T` 类型，其类型调整为 `T`。所以返回 `const int` 的函数，其调用表达式的类型是 `int`。
4. `auto` 推导按模板实参推导进行，因此同样丢弃顶层 cv。

```cpp run ok
#include <type_traits>

void f(int);
void f(const int);           // 同一个函数的重复声明：顶层 const 被丢弃
void f(int) {}

void g(int*);
void g(const int*);          // 不同的重载：const 不在顶层

const int k();
static_assert(std::is_same_v<decltype(k()), int>);   // prvalue：cv 被剥离

int main() {
  const int ci = 0;
  auto a = ci;                                     // auto 丢弃顶层 const
  static_assert(std::is_same_v<decltype(a), int>);
  int* const p = nullptr;
  auto q = p;                                      // q 是 int*
  static_assert(std::is_same_v<decltype(q), int*>);
}
```

## volatile 的语义与弃用 {{deprecated}}

本节只定义了 volatile 对象，volatile 的语义散落在别处：

- [[dcl.type.cv#5]]：通过 volatile glvalue 访问的语义由实现定义；通过非 volatile glvalue 访问一个以 volatile 类型定义的对象是 UB。
- [[intro.abstract]]：通过 volatile glvalue 的访问严格按照抽象机的规则求值，属于程序的**可观察行为**，编译器不能省略、合并它们，也不能（相对于其他 volatile 访问）重排它们。
- volatile 不提供原子性，也不建立线程间的 happens-before 关系；多线程同步应使用 `std::atomic`（[[atomics]]）。

C++20 通过 [[P1152R4]] 弃用了 volatile 的许多语义可疑的用法，因为这些用法暗示了 volatile 并不提供的原子性或单次访问。当前草案中仍然弃用的有（[[depr.volatile.type]]）：

| 用法 | 当前状态 |
|---|---|
| volatile 算术/指针类型的前后缀 `++`、`--` | 弃用：`++v` 实际上是读、改、写两次访问，常被误以为是原子的 |
| 以 volatile 非类类型为左操作数的赋值，且使用了其结果（如 `x = v = 1`） | 弃用（[[expr.assign#5]]：赋值是弃值表达式或不求值操作数时除外） |
| 复合赋值 `v += 1`、`v |= mask` | **不再弃用**（见下） |
| 带 volatile 限定形参或 volatile 限定返回类型的函数类型 | 弃用：按值传递的 volatile 没有意义 |
| volatile 限定的结构化绑定 | 弃用 |

复合赋值经历了一次反复。C++20 把它们一并弃用，但嵌入式社区指出，`REG |= BIT` 这样的寄存器操作在大量厂商头文件中随处可见。C++23 通过 [[P2327R1]] 撤销了按位复合赋值（`&=`、`|=`、`^=`）的弃用；此后又通过一个核心问题决议撤销了全部复合赋值的弃用，当前草案 [[depr.volatile.type]] 的例子中 `brachiosaur += neck;` 标注为 OK。

```cpp run ok
volatile int reg;
int x;

void f() {
  reg |= 0x4;      // OK：不弃用
  reg += 1;        // OK：当前草案中不弃用
  reg = 3;         // OK：赋值作为弃值表达式
  ++reg;           // 弃用（Clang: -Wdeprecated-volatile 警告）
  x = reg = 2;     // 弃用：使用了 volatile 赋值的结果
}
void g(volatile int);   // 弃用：volatile 形参

int main() { f(); }
```

Clang 23 在 `-std=c++2c` 下对 `++reg`、`x = reg = 2`、`g` 的声明给出 `-Wdeprecated-volatile` 警告，对 `reg |= 0x4` 和 `reg += 1` 不警告，与当前草案一致。

## 实现视角

!!! impl
    - **const 对象的存放**：静态存储期且以常量初始化的 const 对象通常放在只读段（ELF 的 `.rodata`、Mach-O 的 `__TEXT,__const`）。对它们 `const_cast` 后写入会触发段错误，这是修改 const 对象属于 UB 最直观的表现。但有动态初始化或 `mutable` 成员的 const 对象必须放在可写段。
    - **cv 与名字修饰**：Itanium ABI 中 cv 限定以 `K`（const）、`V`（volatile）编码；函数形参的顶层 cv 不进入修饰名（这与它们不影响函数类型一致），所以 `f(int)` 与 `f(const int)` 的修饰名相同。MSVC 的修饰方案同样不编码形参的顶层 cv，但会把返回类型的 cv 编码进修饰名。
    - **volatile 的代码生成**：GCC/Clang 保证每次 volatile 访问都生成一条对应宽度的加载或存储，且不与其他 volatile 访问重排，但不插入内存屏障。MSVC 在 x86/x64 上有 `/volatile:ms` 模式，赋予 volatile 获取/释放语义（ARM 上默认 `/volatile:iso`）。

## 历史与演进

!!! history
    - **C++98**：cv 的四个版本、const/volatile 对象、数组上的 cv 附着到元素、偏序表，这些规则在 C++98 中就已存在，后续版本主要是措辞上的澄清（例如数组类型本身被认为是 cv 限定的）。
    - **C++11**：引入右值引用，引用永远 cv 无限定的规则同样适用。
    - **C++20**：[[P1152R4]] 弃用 volatile 的大部分复合用法。
    - **C++23**：[[P2327R1]] 撤销按位复合赋值的弃用；随后全部复合赋值的弃用都被撤销。

## 陷阱

!!! pitfall "`const` 指针 ≠ 指向 `const` 的指针"
    `const int* p` 可以改 `p`，不能改 `*p`；`int* const p` 正好相反。`std::is_const_v<const int*>` 为 `false`。读声明时从右往左读：`int* const` 是指向 int 的 const 指针。

!!! pitfall "以为 `void f(const int)` 是另一个重载"
    顶层 const 在函数类型中被丢弃，它只影响定义中的形参在函数体内能否修改。在头文件的声明里给形参写 `const int` 没有任何意义（也不影响 ABI）。

!!! pitfall "`const_cast` 本身不是 UB"
    用 `const_cast` 去掉 const 总是合法的，UB 只发生在随后修改了一个 const 对象时。反之，即使不用 `const_cast`，通过 `memcpy` 或 placement new 修改 const 对象同样是 UB（或者至少不能再通过原来的名字访问新对象，见 [[basic.life]]）。

!!! pitfall "volatile 不是线程同步工具"
    与 Java 不同，C++ 的 volatile 不提供原子性，也不建立 happens-before。两个线程无同步地读写同一个 volatile `int` 仍然是数据竞争（[[intro.races]]），行为未定义。

## 思考题

!!! question "1. `using A = int[3]; const A* p;` 中 `p` 的类型是什么？`std::is_const_v<std::remove_pointer_t<decltype(p)>>` 的值？"

<details markdown="1">
<summary>答案</summary>

`const A` 中的 const 附着到元素上，所以 `const A` 就是 `const int[3]`，`p` 的类型是 `const int (*)[3]`。按 ¶3，被指向的类型 `const int[3]` 被认为是 const 限定的，所以 `is_const_v<const int[3]>` 为 `true`。
</details>

!!! question "2. 下面哪些是 const 对象？`struct S { mutable int m; const int c; int n; }; const S cs{1,2,3}; S s{1,2,3};`"

<details markdown="1">
<summary>答案</summary>

- `cs`：类型为 `const S`，是 const 对象。
- `cs.m`：const 对象的 mutable 子对象 → **不是** const 对象。
- `cs.c`：既是 const 对象的非 mutable 子对象，自身类型也是 `const int` → const 对象。
- `cs.n`：const 对象的非 mutable 子对象 → const 对象。
- `s`：不是。`s.c`：类型为 `const int` → const 对象（即使外围对象不是 const）。`s.m`、`s.n`：不是。

所以 `const_cast<int&>(s.c) = 0;` 也是 UB。
</details>

!!! question "3. 为什么 `void f(volatile int)` 被弃用，而 `void g(volatile int*)` 没有？"

<details markdown="1">
<summary>答案</summary>

`volatile int` 形参是按值传递的局部副本，它的 volatile 是顶层 cv，不影响函数类型，调用者看不到。它只让函数体内对这个局部变量的访问不被优化，这几乎从来不是作者的本意，作者往往误以为它对调用方的实参有意义。`volatile int*` 中的 volatile 不在顶层，它说明被指向的对象（通常是硬件寄存器）需要 volatile 访问，是函数接口的一部分，有明确的意义。[[depr.volatile.type]] 的 Example 3 正是这一对比。
</details>

## 小结

!!! summary
    - 每个对象类型（及 `void`）都有 cv 的四个版本，表示与对齐相同；函数类型、引用类型永远 cv 无限定。
    - [[g:const-object|const 对象]]由对象创建时的类型决定：`const T` 对象，或 const 对象的非 mutable 子对象。修改 const 对象是 UB，修改通过 const 路径看到的非 const 对象则不是。volatile 对象的所有子对象都是 volatile 对象。
    - 复合类型不继承成分的 cv，**数组例外**：数组的 cv 就是元素的 cv。
    - [[g:more-cv-qualified|更多 cv 限定]]是 {const, volatile} 的子集上的偏序；`const` 与 `volatile` 不可比较。
    - [[g:top-level-cv-qualifiers|顶层 cv]] 在形参类型、模板推导、prvalue 类型中被丢弃。
    - volatile 访问是可观察行为，但不是原子的，也不同步。C++20 弃用了 `++`/`--`、链式赋值、volatile 形参/返回值、volatile 结构化绑定；复合赋值的弃用已被撤销。
