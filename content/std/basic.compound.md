---
title: 复合类型
summary: 八种复合类型的构造方式；指针值的四种状态与在某求值上下文中有效；指针可互转与可经由指针到达的字节
status: draft
related: basic.types, basic.types.trivial, dcl.ptr, dcl.ref, dcl.mptr, expr.add, expr.reinterpret.cast, ptr.launder, basic.life, intro.object
tags: 类型系统, 指针, 指针来源, UB
updated: 2026-10-17
---

**复合类型**（compound types）是由别的类型组合出来的类型：数组、函数、指针、引用、类、联合、枚举、成员指针。本节（[[basic.compound]]，6.9.5）的前两段只是一个目录，各种复合类型的细节分散在声明符（[[dcl.decl]]）、类（[[class]]）、枚举（[[dcl.enum]]）等章节。

本节真正的分量在指针上（¶3–¶9）：一个指针值到底是什么，何时有效，指向哪个对象，哪些对象共享地址并能互相 `reinterpret_cast`。这些规则是理解 [[basic.life]]、[[expr.add]]、[[expr.reinterpret.cast]]、`std::launder`（[[ptr.launder]]）以及大部分与指针相关的 UB 的前提。当前草案 {{c++26}} 在这里做了一次重要的重写：旧模型说指针值在存储期结束时变为无效，新模型改为看指针值**在某个求值的上下文中**是否有效。

## 八种复合类型（¶1）

| ¶ | 复合类型 | 详细规则 | 主类别 trait |
|---|---|---|---|
| 1.1 | 给定类型对象的**数组** | [[dcl.array]] | `is_array` |
| 1.2 | **函数**：有给定类型的形参，返回 `void` 或给定类型的结果 | [[dcl.fct]] | `is_function` |
| 1.3 | 指向 cv `void`、对象或函数（包括类的静态成员）的**指针** | [[dcl.ptr]] | `is_pointer` |
| 1.4 | 指代对象或函数的**引用**：左值引用、右值引用 | [[dcl.ref]] | `is_lvalue_reference` / `is_rvalue_reference` |
| 1.5 | 包含一系列类成员、并对其访问加以限制的**类** | [[class]]、[[class.mem]]、[[class.access]] | `is_class` |
| 1.6 | **联合**：能在不同时刻容纳不同类型对象的类 | [[class.union]] | `is_union` |
| 1.7 | **枚举**：由一组具名常量值组成 | [[dcl.enum]] | `is_enum` |
| 1.8 | **指向非静态类成员的指针**：在给定类的对象中标识给定类型的成员 | [[dcl.mptr]] | `is_member_object_pointer` / `is_member_function_pointer` |

几点说明：

- 类、联合、枚举也是复合类型。直观上它们并不由别的类型构造，但标准就是这样分类的：凡不是基础类型的都是复合类型（`is_compound_v<T> == !is_fundamental_v<T>`）。
- 指向静态成员的指针就是普通指针（脚注 26）：`&S::static_member` 的类型是 `int*`，不是 `int S::*`。¶1.8 的成员指针专指非静态成员。数据成员指针和成员函数指针合称**成员指针类型**（pointer-to-member types）。
- 引用不是对象，所以有引用类型，但没有引用对象；不过引用可能占用存储（作为类成员时），见 [[dcl.ref]]。

## 递归构造与大小上限（¶2）

¶2 规定，上述构造方法可以递归使用，限制见 [[dcl.meaning]]（例如没有引用的数组，没有指向引用的指针，函数不能返回数组或函数，没有 `void` 的数组）。此外：

!!! std
    "Constructing a type such that the number of bytes in its object representation exceeds the maximum value representable in the type std::size_t is ill-formed."
    —— 构造一个对象表示字节数超出 `size_t` 最大值的类型，程序非良构。

注意，非良构的是构造这个类型本身，而不只是定义该类型的对象：

```cpp run error
#include <cstdint>
using Huge = char[SIZE_MAX][2];   // error: 类型大小超过 SIZE_MAX
```

为什么要这样规定？`sizeof` 的结果类型是 `size_t`（[[expr.sizeof]]），如果一个类型的大小装不进 `size_t`，`sizeof` 就无值可返，指针算术也会失去意义。

## 指针类型与指针值（¶3）

### 术语

¶3 先定义了几个名称：

- **对象指针类型**（object pointer type）：指向 cv `void` 或指向对象类型的指针的类型。Note 1 指出，`void*` 是对象指针类型，但不是指向对象类型的指针（pointer-to-object type），因为 `void` 不是对象类型。
- **函数指针类型**（function pointer type）：能指代函数的指针的类型。
- 指向 `T` 类型对象的指针称为指向 `T` 的指针（pointer to `T`）。
- 除指向静态成员的指针外，标准中说指针时不包括成员指针。
- 允许指向不完整类型的指针，但能对它们做的事有限（[[basic.types.general]]）。

### 指针值的四种状态

!!! std
    "Every value of pointer type is one of the following: a *pointer to* an object or function …, a *pointer past the end of* an object …, the *null pointer value* for that type, or an *invalid pointer value*."

| 类别 | 例子 | 能做什么 |
|---|---|---|
| **指向**对象或函数的指针（¶3.1） | `&x`、`new int`、`&f` | 解引用（若对象在生存期内或满足 [[basic.life]] 的条件）、算术、比较 |
| 对象的**尾后**指针（¶3.2） | `arr + N`、`&x + 1` | 算术、比较；**不能解引用** |
| 该类型的**空指针值**（¶3.3） | `nullptr`、`int* p{}` | 比较、布尔转换；不能解引用或做非零算术 |
| **无效指针值**（¶3.4） | 某些转换的结果（见 [[expr.reinterpret.cast#5]] 的注） | 几乎什么都不能做 |

理解本节的关键在于：**同一个地址可以对应不同的指针值**。指向对象或越过对象末尾的指针值表示一个地址，分别是对象占据的第一个字节的地址，或对象存储之后的第一个字节的地址（脚注 27：对不在生存期内的对象，是它将要或曾经占据的第一个字节）。Note 2 强调：

> 对象的尾后指针**不被认为指向**恰好位于该地址的另一个无关同类型对象。

所以在下面的代码中，即使比较成立，也不能通过 `p` 修改 `b`：

```cpp run ub
#include <cstdio>

int main() {
  int a = 1, b = 2;
  int* p = &a + 1;           // a 的尾后指针（a 被视为单元素数组，见下）
  if (p == &b) {             // 结果未指定 [expr.eq]：可能为 true
    *p = 10;                 // 若执行到这里：UB——p 不指向 b，是尾后指针，不能解引用
  }
  std::printf("%d\n", b);
}
```

这就是常说的**指针来源**（pointer provenance）：指针值不仅是一个地址，还记录了它来自哪个对象。编译器的别名分析依赖这一点，它可以假定通过 `&a + 1` 的写入不会改变 `b`。

### 单元素数组与假想元素

¶3 接着为指针算术（[[expr.add]]）和比较（[[expr.rel]]、[[expr.eq]]）规定了两条视同规则：

1. `n` 个元素的数组 `x` 的尾后指针，视为指向假想的第 `n` 个元素 `x[n]`；
2. 不是数组元素的 `T` 类型对象，视为属于一个单元素的 `T` 数组。

第二条使 `&x + 1` 合法（得到 `x` 的尾后指针），于是 `std::copy(&x, &x + 1, out)` 这种把单个对象当作长度为 1 的区间的写法得以成立。

### 表示

¶3 最后规定，指针类型的值表示由实现定义。指向布局兼容类型（[[basic.types.general#9]]）的指针必须具有相同的值表示和对齐要求。Note 3 指出，指向超对齐类型（[[basic.align]]）的指针没有特殊表示，只是有效值的范围受超对齐要求限制（低若干位为 0）。

!!! impl
    主流平台上，所有对象指针和函数指针都是一个机器字长的地址，但标准有意不作此要求。历史上有段式内存、字寻址机器（`char*` 比 `int*` 宽）；今天的 CHERI 架构上，指针是 128 位的能力（capability），携带边界和权限，这正是指针值不等于地址在硬件上的体现。AArch64 的指针认证（PAC）和内存标签（MTE）也会在指针高位放置非地址信息。

## 与潜在非唯一对象关联的指针值（¶4）

¶4 规定，指向**潜在非唯一对象**（potentially non-unique object，[[intro.object#9]]）`O` 的指针值，**关联于**（associated with）以下求值之一：

- ¶4.1 产生该字符串字面量对象的那个 *string-literal* 的求值；
- ¶4.2 产生该后备数组的那个初始化列表的求值；
- ¶4.3 作为 `O` 或包含 `O` 的模板形参对象的初始化（[[temp.arg.nontype]]、[[meta.define.static]]）。

Note 4：由关联于求值 `E` 的指针值经指针算术得到的指针值，也关联于 `E`。

为什么需要这个概念？潜在非唯一对象（字符串字面量、`initializer_list` 的后备数组等）允许实现合并或重叠存储，`"foo"` 与 `"xfoo"` 的后缀可能共用同一段内存。在运行期，这只会让比较结果未指定，但常量求值必须给出确定的答案。因此 [[expr.const.core]] 规定：比较两个关联于不同求值、且可能指向同一潜在非唯一对象中同一偏移的指针，**不是核心常量表达式**。

```cpp run error
constexpr const char* f() { return "foo"; }

constexpr bool b1 = +"foo" == "foo";   // error: 非常量——两个字面量可能合并，也可能不合并
constexpr bool b2 = f() == f();        // error: 非常量——每次求值字面量可能产生不同对象
constexpr const char* p = f();
constexpr bool b3 = p == p;            // OK: 同一个指针值，true
constexpr bool b5 = "foo" == "bar" + 0;// OK: false，内容不同不可能重叠
```

## 存储期开始之前的指针（¶5）

¶5 规定：如果一个求值产生、或使某个对象具有（[[basic.types.trivial]]）一个指向或越过对象 `O` 末尾的指针值，而该求值发生在 `O` 的存储区存续期开始之前（happens before），则行为未定义。

Note 5：宽松（relaxed）原子操作可能产生这样的值；从整数转换而来则不会（[[expr.reinterpret.cast#5]] 会选一个能让程序有定义行为的值）。

这条规则针对的是内存模型中凭空出现的值（out-of-thin-air）问题。在 relaxed 原子的形式模型下，理论上可能出现一个线程读到指向尚未分配的对象的指针这种因果倒置的执行。¶5 直接规定这种执行是 UB，从而把它排除在需要考虑的合法执行之外。

## 指针值在某求值上下文中有效 {{c++26}}（¶6）

¶6 是本节最重要的新规则。

!!! std
    "A pointer value P is *valid in the context of* an evaluation E if P is a pointer to function or a null pointer value, or if it is a pointer to or past the end of an object O and E happens after the beginning and happens before the end of the duration of the region of storage for O."

也就是说，函数指针和空指针总是有效的；指向或越过对象 `O` 的指针，在 `O` 的存储区存续期之内发生的求值中有效。如果在求值 `E` 中使用了在 `E` 的上下文中无效的指针值 `P`：

- ¶6.1 若 `E` 是间接（`*P`，[[expr.unary.op]]），则是**未定义行为**；
- ¶6.2 若 `E` 是布尔转换（[[conv.bool]]），或由一元 `+`、加减、三路比较、关系、相等运算符执行，则是**实现定义行为**。

其他用途，如复制该指针值、作为实参传递、存入变量，则不受限制。

Note 6 指出，即使 `P` 指向的类型与 `O` 无关，或者 `O` 不在生存期内，`P` 也可以在 `E` 的上下文中有效，只是还有其他限制（[[basic.life]]、[[basic.lval]]、[[expr.add]]）。换言之，有效性只关心存储是否存在，不关心对象是否存活、类型是否匹配。

```cpp run impl
#include <cstdlib>

int main() {
  int* p = static_cast<int*>(std::malloc(sizeof(int)));
  std::free(p);              // p 所指存储的存续期结束
  int* q = p;                // OK（C++26）：复制无效上下文中的指针值不受限制
  if (q) { }                 // 实现定义：布尔转换使用了无效指针值
  bool same = (p == q);      // 实现定义：相等比较
  // *p = 1;                 // UB：间接
  return same ? 0 : 1;
}
```

### 与 C++23 的区别

C++23 的 [basic.stc.general]/4 规定：存储区存续期结束时，所有表示该区域任何部分地址的指针的值都变为无效指针值；通过无效指针值间接，或将其传给释放函数，是 UB；其他任何使用，包括单纯地复制它（左值到右值转换），都是实现定义的。这种在 `free` 时集体改写指针的模型（lifetime-end pointer zap）有两个问题：

1. 大量现实代码（并发数据结构中比较一个可能已释放的指针，例如 ABA 检测、无锁栈）因此在理论上依赖实现定义行为，连复制都不安全；
2. 它与指针值是不可变的值这一直觉冲突：一个变量的值怎么会因为别的线程调用了 `free` 而改变？

在新模型中，指针值本身不变，有效性成为**指针值与求值之间的关系**。相应地，[[basic.stc.general]] 的 Note 1 只说"存储期结束后，指向该存储的指针的使用受到限制（见 [[basic.compound]]）"。配套的 [[expr.assign#2.2]] 还规定：向 volatile 指针 glvalue 赋一个在当前上下文中无效的指针值时，按先转成 `uintptr_t` 再转回来处理。

## 指针可互转（¶7）

¶7 规定，两个对象 *a* 和 *b* 在下列情况下**指针可互转**（pointer-interconvertible）：

- ¶7.1 它们是同一个对象；或
- ¶7.2 一个是联合对象，另一个是该对象的非静态数据成员（[[class.union]]）；或
- ¶7.3 一个是标准布局类对象，另一个是该对象的第一个非静态数据成员或其任一基类子对象（[[class.mem]]）；或
- ¶7.4 存在对象 *c*，使 *a* 与 *c*、*c* 与 *b* 分别指针可互转（传递性）。

如果两个对象指针可互转，它们的**地址相同**，并且可以通过 `reinterpret_cast`（[[expr.reinterpret.cast]]）从指向其一的指针得到指向另一个的指针。更精确地说，`static_cast` 从 `void*` 转到 `T*` 时（[[expr.static.cast#12]]），如果原指针指向对象 *a*，且存在与 *a* 指针可互转、类型与 `T` 相似的对象 *b*，结果就指向 *b*；否则指针值不变，**仍然指向 *a***，此时通过它访问往往违反别名规则。

!!! std
    "An array object and its first element are not pointer-interconvertible, even though they have the same address."
    —— Note 7：数组对象与它的第一个元素地址相同，但**不**指针可互转。

```cpp run ok
#include <cstdio>

struct S { int a; double b; };    // 标准布局
union U { int i; float f; };
struct Base { int x; };
struct Der : Base { };            // 标准布局：所有数据成员在 Base 中

int main() {
  S s{1, 2.0};
  int* pa = reinterpret_cast<int*>(&s);    // OK: s 与 s.a 指针可互转，pa 指向 s.a
  S*   ps = reinterpret_cast<S*>(pa);      // OK: 反向也行
  U u{.i = 3};
  int* pi = reinterpret_cast<int*>(&u);    // OK: 联合对象与其成员
  Der d{};
  Base* pb = reinterpret_cast<Base*>(&d);  // OK: 标准布局类与其基类子对象（当然 static_cast 更好）
  std::printf("%d %g %d %d\n", *pa, ps->b, *pi, pb->x);
}
```

反过来，下面这些转换得到的指针仍指向原对象，通过它们访问是 UB：

```cpp run ub
struct NS { int a; private: int b = 0; public: int get() const { return b; } };  // 非标准布局

int main() {
  NS ns{};
  int* p = reinterpret_cast<int*>(&ns);  // 结果仍指向 ns（不是 ns.a）：二者不指针可互转
  int r = *p;                            // UB：通过 int glvalue 访问 NS 对象 [basic.lval]

  int arr[2] = {1, 2};
  int (*pa)[2] = reinterpret_cast<int(*)[2]>(&arr[0]);  // 仍指向 arr[0]
  int s = (*pa)[1];                      // UB：*pa 指代的是 int 对象 arr[0]，那里没有 int[2] 对象可供下标
  return r + s + ns.get();
}
```

实践中这两段代码都能工作，因为地址确实相同。但编译器有权基于 `p` 指向的是 `NS` 而不是 `int` 来做别名分析。正确的做法是直接写 `&ns.a`、`arr`（数组到指针转换），对数组的情形也可以使用 `std::launder`（见下节）。

!!! note "相关 trait"
    C++20 提供 `std::is_pointer_interconvertible_base_of<B, D>` 与 `std::is_pointer_interconvertible_with_class(&C::m)`（[[meta.rel]]、[[meta.member]]）。本机 libc++ 尚未提供它们；Clang 有内建的 `__is_pointer_interconvertible_base_of(B, D)`。

为什么数组与首元素不可互转？如果可以，`reinterpret_cast<int(*)[2]>(&arr[0])` 就会指向数组，再由此访问 `arr[1]`，编译器就无法再依据一个 `int*` 只能访问它所在的数组来限定访问范围。¶8 和 `std::launder` 正是围绕这个可到达范围设计的。

## 可经由指针到达的字节（¶8）

¶8 规定：如果存在一个与 *x* 指针可互转的对象 *y*，使得存储的字节 *b* 位于 *y* 占据的存储之内，或者在 *y* 是数组元素时位于直接外围数组对象的存储之内，那么 *b* **可经由**（reachable through）一个指向对象 *x* 的指针值**到达**。

这个定义只有 `std::launder` 使用（[[ptr.launder#2]]）："结果可到达的所有字节，都必须能经由实参指针到达"。意图是：`launder` 可以把指针转成指向同地址的另一个对象，但不能扩大可访问的内存范围。否则编译器的逃逸分析就会失效，一个只暴露了 `&s.a[0]` 的函数，可能被调用方用 `launder` 扩大到整个 `s`。

```cpp run ok
#include <new>

int main() {
  int arr[2] = {1, 2};
  // 指向 arr[0] 的指针：可到达整个 arr（arr[0] 是数组元素，外围数组是 arr）
  int (*pa)[2] = std::launder(reinterpret_cast<int(*)[2]>(&arr[0]));   // OK
  return (*pa)[1] == 2 ? 0 : 1;
}
```

```cpp run ub
#include <new>

struct S2 { int a[2]; int b; };

int main() {
  S2 s{{1, 2}, 3};
  // &s.a[0] 只能到达 s.a 的字节；S2 对象还包括 s.b，后者不可到达
  S2* p = std::launder(reinterpret_cast<S2*>(&s.a[0]));   // UB：违反 launder 的前置条件
  return p->b;
}
```

## `void*`（¶9）

¶9 规定，指向 cv `void` 的指针可以用来指向类型未知的对象，它必须能容纳任何对象指针。指向 cv `void` 的指针类型的对象，与指向 cv `char` 的指针具有相同的表示和对齐要求。

后一句是从 C 继承下来的：在 C 引入 `void*` 之前，`char*` 承担通用指针的角色，`malloc` 返回 `char*`。注意 `void*` 只保证能容纳对象指针，不保证能容纳函数指针。函数指针与 `void*` 之间的转换是**条件性支持**的（[[expr.reinterpret.cast]]），POSIX 的 `dlsym` 额外要求它可行。

## 其他复合类型速览

| 类型 | 要点 | 详见 |
|---|---|---|
| 数组 `T[N]` / `T[]` | `T` 必须是完整对象类型（未知边界时可不完整的情形见 [[dcl.array]]）；`N` 是 `size_t` 范围内的正整数；cv 作用于元素（[[basic.type.qualifier#3]]） | [[dcl.array]] |
| 函数 `R(Args...)` | 形参类型列表中顶层 cv 被丢弃，数组/函数形参调整为指针；`noexcept` 是函数类型的一部分（C++17） | [[dcl.fct]] |
| 引用 `T&` / `T&&` | 不是对象，没有 cv；引用折叠；不能有引用的引用/数组/指针 | [[dcl.ref]] |
| 类、联合 | 完整性由定义决定；标准布局、平凡可复制等性质见 [[class.prop]] | [[class]] |
| 枚举 | 有作用域 / 无作用域；底层类型决定表示（[[basic.fundamental#6]]） | [[dcl.enum]] |
| 成员指针 `T C::*` | 不属于指针；不能指向静态成员或引用成员；有空成员指针值 | [[dcl.mptr]]、[[expr.mptr.oper]] |

!!! impl "成员指针的表示"
    - **Itanium ABI**：数据成员指针是成员在类中的字节偏移（`ptrdiff_t`），空值用 `-1` 表示（因为偏移 0 是合法的首成员）；成员函数指针占两个字，一个是函数指针（虚函数时为虚表偏移 + 1，ARM 变体改用调整量的最低位做标记），另一个是 `this` 调整量。
    - **MSVC**：成员函数指针的大小取决于类的继承模型（单继承/多继承/虚继承/未知）。单继承时与普通指针一样大，模型越复杂，需要的调整字段越多；对不完整类型默认按最保守的模型处理，可以通过 `/vmg`、`/vmb` 编译选项或 `__single_inheritance` 等关键字控制。

## 陷阱

!!! pitfall "`p == q` 为真 ≠ `p` 与 `q` 可以互换使用"
    相等比较只比较地址（[[expr.eq]]），而指针值还带有指向谁的信息。尾后指针与下一个对象的指针、旧对象的指针与同址新对象的指针（[[basic.life]]），都可能相等，却不能互换。

!!! pitfall "`reinterpret_cast` 不改变指针指向"
    对非指针可互转的对象，`reinterpret_cast<T*>(p)` 得到的指针仍指向原对象，只是类型变了。随后的访问由 [[basic.lval#11]] 判定，通常是 UB。

!!! pitfall "在旧规则下，free 后读取指针变量是实现定义的"
    在 C++23 及之前，`free(p); auto q = p;` 中的复制本身就是使用无效指针值，属于实现定义行为（一些实现可能在此陷入）。C++26 起复制不受限制，只有间接是 UB，布尔转换与比较是实现定义的。

## 思考题

!!! question "1. `struct A { int x; }; struct B : A { }; struct C : B { };` 中，`C` 对象与其 `x` 成员是否指针可互转？"

<details markdown="1">
<summary>答案</summary>

是。`C` 是标准布局类（所有数据成员都首次声明于 `A` 这一个类中）。按 ¶7.3，`C` 对象与其基类子对象 `B`、`A` 都指针可互转；`A` 子对象是标准布局类对象，与其首个非静态数据成员 `x` 指针可互转；再由 ¶7.4 的传递性，`C` 对象与 `x` 指针可互转。所以 `reinterpret_cast<int*>(&c)` 指向 `c.x`。
</details>

!!! question "2. 为什么 ¶6 把 `if (p)` 规定为实现定义，而不是像 `*p` 一样规定为 UB，或者干脆规定为良定义？"

<details markdown="1">
<summary>答案</summary>

不规定为良定义，是因为某些（历史上的或特殊的）架构在把无效地址装入地址寄存器时就可能陷入，存储释放后其地址空间也可能被重映射，标准不能要求所有实现都给出有意义的结果。不规定为 UB，是因为大量现实代码（无锁算法中的比较、调试断言、日志打印）在存储释放后仍会比较或检查指针，如果统统归为 UB，编译器就有权删除这些代码。实现定义是折中：在主流实现上它就是按地址比较，而且实现必须在文档中说明。
</details>

!!! question "3. `int a[2][2]{}; int* p = &a[0][0]; p[3] = 1;` 合法吗？"

<details markdown="1">
<summary>答案</summary>

不合法（UB）。`p` 指向 `a[0]`（一个 `int[2]`）的元素 `a[0][0]`。按 [[expr.add]]，`p + 2` 是 `a[0]` 的尾后指针，`p + 3` 已超出该数组范围，指针算术本身就是 UB。尽管 `a[1][1]` 恰好位于那个地址，¶3 中尾后指针不指向无关对象的规定，与 [[expr.add]] 的数组边界一起，禁止了这种把多维数组当一维数组用的写法。`std::launder` 也无法补救这种情形，因为 `a[0][0]` 能到达的字节只有 `a[0]`。
</details>

## 小结

!!! summary
    - 复合类型包括数组、函数、指针、引用、类、联合、枚举、成员指针；构造一个大小超过 `SIZE_MAX` 的类型是非良构的。
    - 指针值有四种：指向对象或函数、尾后、空、无效。**指针值 ≠ 地址**：尾后指针不指向同地址的无关对象；非数组对象视为单元素数组。
    - 指向潜在非唯一对象（字符串字面量、`initializer_list` 后备数组、模板形参对象）的指针关联于产生它的求值，用于判定常量求值中的比较。
    - C++26：指针值[[g:valid-in-the-context-of|在某求值上下文中有效]]当且仅当它所指的存储正处于存续期；无效时，间接是 UB，布尔转换、算术、比较是实现定义的，复制不受限制。
    - [[g:pointer-interconvertible|指针可互转]]的情形：同一对象；联合与其成员；标准布局类与首个成员、基类子对象；并且可以传递。数组与首元素**不**可互转。
    - [[g:reachable-through|可到达]]的字节界定了 `std::launder` 能扩大到的范围。`void*` 与 `char*` 表示相同。
