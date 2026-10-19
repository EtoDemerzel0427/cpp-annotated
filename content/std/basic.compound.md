---
title: 复合类型
summary: 由其他类型构造出来的八种类型；指针值除了地址还记录它指向哪个对象，以及存储释放后指针还能做什么；哪些对象指针可互转，std::launder 最多能触及哪些字节。
status: draft
related: basic.types, basic.types.trivial, dcl.ptr, dcl.ref, dcl.mptr, expr.add, expr.reinterpret.cast, ptr.launder, basic.life, intro.object
tags: 类型系统, 指针, 指针来源, UB
updated: 2026-10-19
---

!!! tldr
    - 复合类型有八种：数组、函数、指针、引用、类、联合、枚举、成员指针。构造一个大小超过 `SIZE_MAX` 字节的类型是非良构的。
    - 指针值不只是一个地址：尾后指针不指向恰好位于那个地址的另一个对象，即使两者比较相等。
    - 存储释放之后，指向它的指针仍然可以复制和传递；解引用是 UB，比较和布尔转换是实现定义的。
    - 同一对象、联合与其成员、标准布局类与其首个成员或基类子对象，这几种对象指针可互转，可以用 `reinterpret_cast` 互相得到。数组和它的首元素不是。
    - `std::launder` 可以把指针换成指向同一地址的另一个对象，但不能扩大经由指针可以到达的字节范围。

**复合类型**（compound type）是用其他类型构造出来的类型。[[basic.compound]]（6.9.5）的前两段只是一个目录，各种复合类型的细节分布在声明符 [[dcl.decl]]、类 [[class]]、枚举 [[dcl.enum]] 等章节。本节的主体是指针（¶3–¶9）：一个指针值到底是什么，什么时候还能用，哪些对象可以通过 `reinterpret_cast` 互相转换。[[basic.life]]、[[expr.add]]、[[expr.reinterpret.cast]]、`std::launder`（[[ptr.launder]]）里与指针相关的 UB，都要从这里的定义出发。

## 八种复合类型（¶1–¶2）

| ¶ | 复合类型 | 详细规则 | 主类别 trait |
|---|---|---|---|
| 1.1 | 某种类型对象的数组 | [[dcl.array]] | `is_array` |
| 1.2 | 函数：有给定类型的形参，返回 `void` 或给定类型的结果 | [[dcl.fct]] | `is_function` |
| 1.3 | 指向 cv `void`、对象或函数（包括类的静态成员）的指针 | [[dcl.ptr]] | `is_pointer` |
| 1.4 | 指代对象或函数的引用，分左值引用和右值引用 | [[dcl.ref]] | `is_lvalue_reference`、`is_rvalue_reference` |
| 1.5 | 类：包含一系列成员，并限制对它们的访问 | [[class]]、[[class.access]] | `is_class` |
| 1.6 | 联合：能在不同时刻容纳不同类型对象的类 | [[class.union]] | `is_union` |
| 1.7 | 枚举：由一组具名常量值组成 | [[dcl.enum]] | `is_enum` |
| 1.8 | 指向非静态类成员的指针 | [[dcl.mptr]] | `is_member_object_pointer`、`is_member_function_pointer` |

类、联合和枚举直观上并不由其他类型构造而来，但标准把它们也归为复合类型：不是基础类型的都是复合类型，`is_compound_v<T>` 就等于 `!is_fundamental_v<T>`。

指向静态成员的指针就是普通指针（脚注 26）：`&S::static_member` 的类型是 `int*`，不是 `int S::*`。数据成员指针和成员函数指针合称**成员指针类型**（pointer-to-member type）。

¶2 这些构造方式可以递归使用，限制见 [[dcl.meaning]]：没有引用的数组，没有指向引用的指针，函数不能返回数组或函数，等等。另外，构造一个对象表示超过 `std::size_t` 最大值字节的类型，程序非良构：

```cpp run error
#include <cstdint>
using Huge = char[SIZE_MAX][2];   // error: 类型大小超过 SIZE_MAX
```

非良构的是构造这个类型本身，不必等到定义它的对象。`sizeof` 的结果类型是 `size_t`（[[expr.sizeof]]），大小装不进 `size_t` 的类型连 `sizeof` 都无法求值。

## 指针值不只是地址（¶3）

```cpp run ub
#include <cstdio>

int main() {
  int a = 1, b = 2;
  int* p = &a + 1;           // a 的尾后指针
  if (p == &b) {             // 结果未指定：可能为 true
    *p = 10;                 // UB：p 是尾后指针，不指向 b
  }
  std::printf("%d\n", b);
}
```

`b` 可能恰好紧跟在 `a` 后面，这时 `p == &b` 为真。即便如此，`*p = 10` 也不会合法地修改 `b`。

### 四种指针值

¶3 规定，指针类型的每个值都是下面四种之一：

| 种类 | 例子 | 能做什么 |
|---|---|---|
| ¶3.1 指向对象或函数的指针 | `&x`、`new int`、`&f` | 解引用、算术、比较 |
| ¶3.2 对象的尾后指针 | `arr + N`、`&x + 1` | 算术、比较，不能解引用 |
| ¶3.3 该类型的空指针值 | `nullptr`、`int* p{}` | 比较、布尔转换 |
| ¶3.4 无效指针值 | 某些转换的结果（[[expr.reinterpret.cast#5]]） | 几乎什么都不能做 |

指向对象的指针和尾后指针都**表示一个地址**（represents the address）：分别是对象占据的第一个字节的地址，和对象存储之后的第一个字节的地址。对不在生存期内的对象，是它将要占据或曾经占据的第一个字节（脚注 27）。

注 2 是本节的关键：对象的尾后指针不被认为指向恰好位于那个地址的另一个同类型对象。所以同一个地址可以对应不同的指针值。指针值除了地址，还记录了它来自哪个对象，这通常叫做**指针来源**（pointer provenance）。编译器的别名分析依赖这一点：它可以假定通过 `&a + 1` 的写入不会改变 `b`。

### 单个对象视为单元素数组

¶3 还为指针算术（[[expr.add]]）和比较（[[expr.rel]]、[[expr.eq]]）规定了两条视同规则：

1. 有 `n` 个元素的数组 `x` 的尾后指针，视为指向假想的元素 `x[n]`；
2. 不是数组元素的 `T` 类型对象，视为一个只有一个元素的 `T` 数组的元素。

第二条使 `&x + 1` 合法，它就是 `x` 的尾后指针。所以 `std::copy(&x, &x + 1, out)` 这种把单个对象当作长度为 1 的区间的写法是成立的。

### 术语与表示

¶3 开头定义了几个名称。指向 cv `void` 或对象类型的指针的类型叫**对象指针类型**（object pointer type）。注 1 指出，`void*` 是对象指针类型，但不是指向对象类型的指针，因为 `void` 不是对象类型。能指代函数的指针的类型叫**函数指针类型**（function pointer type）。除了指向静态成员的指针，标准里说的指针都不包括成员指针。指向不完整类型的指针是允许的，只是能做的事有限（[[basic.types.general]]）。

指针类型的值表示由实现定义。指向布局兼容类型（[[basic.types.general#9]]）的指针必须有相同的值表示和对齐要求。注 3 补充，指向超对齐类型（[[basic.align]]）的指针没有特殊的表示，只是有效值的范围受对齐要求限制，例如低几位必须是 0。

!!! impl
    主流平台上，对象指针和函数指针都是一个机器字长的地址，但标准有意不作此要求。历史上有分段内存和按字寻址的机器（`char*` 比 `int*` 宽）。今天的 CHERI 架构上，指针是携带边界和权限的 128 位能力（capability）；AArch64 的指针认证（PAC）和内存标签（MTE）也在指针的高位放置地址以外的信息。

## 存储释放后的指针（¶6）

```cpp run impl
#include <cstdlib>

int main() {
  int* p = static_cast<int*>(std::malloc(sizeof(int)));
  std::free(p);              // p 所指存储的存续期结束
  int* q = p;                // OK：复制指针值不受限制
  if (q) { }                 // 实现定义：布尔转换
  bool same = (p == q);      // 实现定义：相等比较
  // *p = 1;                 // UB：间接
  return same ? 0 : 1;
}
```

¶6 先定义：指针值 `P` 在求值 `E` 的上下文中[[g:valid-in-the-context-of|有效]]（valid in the context of an evaluation），条件是 `P` 是函数指针或空指针值，或者 `P` 指向对象 `O` 或是 `O` 的尾后指针，而 `E` 发生在 `O` 所在存储的存续期之内（开始之后、结束之前）。

如果在求值 `E` 中使用了一个在 `E` 的上下文中无效的指针值：

- ¶6.1 `E` 是间接（`*P`，[[expr.unary.op]]），行为未定义；
- ¶6.2 `E` 是布尔转换（[[conv.bool]]），或者由一元 `+`、加减、三路比较、关系或相等运算符执行，行为由实现定义。

复制这个指针值、作为实参传递、存进变量，都不受限制。

注 6 补充，即使 `P` 指向的类型与 `O` 无关，或者 `O` 不在生存期内，`P` 也可以是有效的；这样的指针另外受 [[basic.life]]、[[basic.lval]]、[[expr.add]] 的限制。换句话说，有效性只关心存储是否还在，不关心对象是否存活、类型是否匹配。

### 与 C++23 的区别

这是 C++23 之后的新措辞。C++23 的 [basic.stc.general] 第 4 段规定，存储的存续期结束时，所有表示其中任何地址的指针的值都变成无效指针值；通过无效指针值间接，或者把它传给释放函数，是 UB；其他任何使用，包括单纯复制，都是实现定义的。

这种在释放时集体改写指针值的模型有两个问题。一是大量实际代码在理论上依赖实现定义行为，例如无锁数据结构中比较一个可能已经被释放的指针，连复制它都不安全。二是它违反直觉：一个变量的值怎么会因为别的线程调用了 `free` 而改变？

新模型里指针值本身不变，有效性变成指针值与求值之间的关系。相应地，[[basic.stc.general]] 现在只说存储期结束后指向它的指针的使用受到限制。配套的 [[expr.assign#2.2]] 规定，把一个在当前上下文中无效的指针值赋给 volatile 指针 glvalue 时，按先转成 `std::uintptr_t` 再转回来处理。

## 存储期开始之前的指针（¶5）

¶5 如果某个求值产生了一个指向对象 `O`（或 `O` 的尾后）的指针值，或者使某个对象具有了这样的值（[[basic.types.trivial]]），而这个求值发生在 `O` 所在存储的存续期开始之前，行为未定义。

注 5 说明，宽松（relaxed）原子操作可能产生这样的值，从整数转换得到指针则不会（[[expr.reinterpret.cast#5]] 会选一个能让程序有定义行为的值）。这条规则针对的是内存模型中凭空出现的值：在 relaxed 原子的形式模型下，理论上可能出现一个线程读到指向尚未分配的存储的指针这种因果颠倒的执行。¶5 把这种执行规定为 UB，把它排除在需要考虑的合法执行之外。

## 字符串字面量的指针（¶4）

```cpp run error
constexpr const char* f() { return "foo"; }

constexpr bool b1 = +"foo" == "foo";  // error: 两个字面量可能共用存储，也可能不共用
constexpr bool b2 = f() == f();       // error: 每次求值可能产生不同的对象
constexpr const char* p = f();
constexpr bool b3 = p == p;           // OK: 同一个指针值，true
constexpr bool b4 = +"foo" == +"bar"; // OK: false，内容不同，不可能重叠
```

字符串字面量对象、`initializer_list` 的后备数组和模板形参对象都是**潜在非唯一对象**（potentially non-unique object，[[intro.object#9]]）：实现可以让它们合并或重叠存储，例如 `"foo"` 和 `"xfoo"` 可能共用后缀。运行时，这只让比较结果未指定；常量求值却必须给出确定的答案。

¶4 指向潜在非唯一对象 `O` 的指针值**关联于**（associated with）产生它的那次求值：

- ¶4.1 产生这个字符串字面量对象的 *string-literal* 的求值；
- ¶4.2 产生这个后备数组的初始化列表的求值；
- ¶4.3 作为 `O` 或包含 `O` 的模板形参对象的初始化（[[temp.arg.nontype]]、[[meta.define.static]]）。

注 4 补充，由关联于求值 `E` 的指针经指针算术得到的指针，也关联于 `E`。[[expr.const.core]] 据此规定：比较两个关联于不同求值、又可能指向同一个潜在非唯一对象中同一位置的指针，不是核心常量表达式。上例中 `b1` 和 `b2` 因此被拒绝。

## 指针可互转（¶7）

```cpp run ok
#include <cstdio>

struct S { int a; double b; };    // 标准布局
union U { int i; float f; };
struct Base { int x; };
struct Der : Base { };            // 标准布局：数据成员都在 Base 中

int main() {
  S s{1, 2.0};
  int* pa = reinterpret_cast<int*>(&s);    // OK: pa 指向 s.a
  S*   ps = reinterpret_cast<S*>(pa);      // OK: 反过来也行
  U u{.i = 3};
  int* pi = reinterpret_cast<int*>(&u);    // OK: 联合对象与其成员
  Der d{};
  Base* pb = reinterpret_cast<Base*>(&d);  // OK: 不过 static_cast 更合适
  std::printf("%d %g %d %d\n", *pa, ps->b, *pi, pb->x);
}
```

¶7 两个对象 *a* 和 *b* 在下列情况下[[g:pointer-interconvertible|指针可互转]]（pointer-interconvertible）：

- ¶7.1 它们是同一个对象；
- ¶7.2 一个是联合对象，另一个是它的非静态数据成员（[[class.union]]）；
- ¶7.3 一个是标准布局类的对象，另一个是它的第一个非静态数据成员，或它的任一基类子对象（[[class.mem]]）；
- ¶7.4 存在对象 *c*，*a* 与 *c*、*c* 与 *b* 分别指针可互转。

指针可互转的两个对象地址相同，而且可以通过 `reinterpret_cast` 从指向一个的指针得到指向另一个的指针。具体机制在 [[expr.static.cast#12]]：从 `void*` 转到 `T*` 时，如果原指针指向对象 *a*，且存在与 *a* 指针可互转、类型与 `T` 相似的对象 *b*，结果就指向 *b*；否则指针值不变，仍然指向 *a*。`reinterpret_cast` 在对象指针之间的转换就是这样定义的。

!!! std
    An array object and its first element are not pointer-interconvertible, even though they have the same address.

注 7：数组对象和它的首元素地址相同，但不是指针可互转的。

不满足条件时，转换得到的指针仍指向原来的对象，通过它访问通常是 UB：

```cpp run ub
struct NS {                     // 不是标准布局：访问控制不同
  int a;
private:
  int b = 0;
public:
  int get() const { return b; }
};

int main() {
  NS ns{};
  int* p = reinterpret_cast<int*>(&ns);  // 仍指向 ns，不指向 ns.a
  int r = *p;                            // UB：通过 int glvalue 访问 NS 对象

  int arr[2] = {1, 2};
  int (*pa)[2] = reinterpret_cast<int(*)[2]>(&arr[0]);  // 仍指向 arr[0]
  int s = (*pa)[1];                      // UB：arr[0] 处没有 int[2] 对象
  return r + s + ns.get();
}
```

这两段代码在实践中都能工作，因为地址确实相同。但编译器有权依据 `p` 指向的是 `NS` 而不是 `int` 来做别名分析。正确的写法是直接取 `&ns.a`，或者让 `arr` 经数组到指针转换得到首元素指针。

为什么数组与首元素不可互转？如果可以，从一个 `int*` 就能转出指向整个数组的指针，再访问 `arr[1]`。编译器就不能再假定一个 `int*` 只能访问它所在的那个数组。下一段和 `std::launder` 正是围绕这个可到达范围设计的。

!!! note "相关 trait"
    C++20 提供 `std::is_pointer_interconvertible_base_of<B, D>` 和 `std::is_pointer_interconvertible_with_class(&C::m)`（[[meta.rel]]、[[meta.member]]）。本机 Clang 23 自带的 libc++ 还没有提供它们，Clang 有内建的 `__is_pointer_interconvertible_base_of(B, D)`。

## 可经由指针到达的字节（¶8）

¶8 设指针值指向对象 *x*。存储中的字节 *b* 可经由这个指针值[[g:reachable-through|到达]]（reachable through），条件是存在一个与 *x* 指针可互转的对象 *y*，*b* 位于 *y* 占据的存储之内；如果 *y* 是数组元素，则位于直接包含它的数组对象的存储之内也可以。

这个定义只用于 `std::launder` 的前置条件（[[ptr.launder#2]]）：结果能到达的所有字节，都必须能经由实参指针到达。`launder` 可以把指针换成指向同一地址的另一个对象，但不能扩大能访问的内存范围。否则编译器的逃逸分析就会失效：一个只拿到了 `&s.a[0]` 的函数，可能用 `launder` 把访问范围扩大到整个 `s`。

```cpp run ok
#include <new>

int main() {
  int arr[2] = {1, 2};
  // &arr[0] 是数组元素，可到达直接包含它的整个 arr
  int (*pa)[2] = std::launder(reinterpret_cast<int(*)[2]>(&arr[0]));   // OK
  return (*pa)[1] == 2 ? 0 : 1;
}
```

```cpp run ub
#include <new>

struct S2 { int a[2]; int b; };

int main() {
  S2 s{{1, 2}, 3};
  // &s.a[0] 只能到达 s.a 的字节，s.b 不可到达
  S2* p = std::launder(reinterpret_cast<S2*>(&s.a[0]));   // UB：违反前置条件
  return p->b;
}
```

## `void*`（¶9）

¶9 指向 cv `void` 的指针可以指向类型未知的对象，它必须能容纳任何对象指针。`void*` 与 `char*` 具有相同的表示和对齐要求。

后一条是从 C 继承来的：C 引入 `void*` 之前，`char*` 充当通用指针，`malloc` 返回 `char*`。`void*` 只保证能容纳对象指针，不保证能容纳函数指针。函数指针与 `void*` 之间的转换是**有条件支持**的（conditionally-supported，实现可以不支持，但不支持时必须诊断，[[expr.reinterpret.cast]]），POSIX 的 `dlsym` 额外要求它可行。

## 其他复合类型速览

| 类型 | 要点 | 详见 |
|---|---|---|
| 数组 `T[N]`、`T[]` | 元素类型必须是对象类型；cv 限定作用于元素（[[basic.type.qualifier#3]]） | [[dcl.array]] |
| 函数 `R(Args...)` | 形参的顶层 cv 被丢弃，数组和函数形参调整为指针；C++17 起 `noexcept` 是函数类型的一部分 | [[dcl.fct]] |
| 引用 `T&`、`T&&` | 不是对象，没有 cv 限定；引用折叠；没有引用的引用、数组和指针 | [[dcl.ref]] |
| 类、联合 | 标准布局、平凡可复制等性质见 [[class.prop]] | [[class]] |
| 枚举 | 有作用域或无作用域；表示由底层类型决定（[[basic.fundamental#6]]） | [[dcl.enum]] |
| 成员指针 `T C::*` | 不属于指针；不能指向静态成员或引用成员；有空成员指针值 | [[dcl.mptr]]、[[expr.mptr.oper]] |

!!! impl "成员指针的表示"
    - Itanium ABI：数据成员指针是成员在类中的字节偏移，空值用 `-1` 表示，因为偏移 0 是合法的首成员。成员函数指针占两个字，一个是函数地址（虚函数时是虚表偏移加 1），另一个是 `this` 的调整量；ARM 变体改用调整量的最低位做虚函数标记。
    - MSVC：成员函数指针的大小取决于类的继承模型。单继承时与普通指针一样大，多继承、虚继承需要更多的调整字段。对不完整类型默认按最保守的模型处理，可以用 `/vmg`、`/vmb` 选项或 `__single_inheritance` 等关键字控制。

## 常见误解

!!! pitfall "`p == q` 为真，`p` 和 `q` 就可以互换"
    相等比较只比较地址（[[expr.eq]]），指针值还带有指向哪个对象的信息。尾后指针与下一个对象的指针、旧对象的指针与同一位置新对象的指针（[[basic.life]]），都可能比较相等，却不能互换。

!!! pitfall "`reinterpret_cast` 改变了指针指向的对象"
    对不是指针可互转的对象，`reinterpret_cast<T*>(p)` 得到的指针仍指向原来的对象，只是类型变了。之后的访问是否合法由 [[basic.lval#11]] 判断，通常是 UB。

## 思考题

!!! question "1. `struct A { int x; }; struct B : A { }; struct C : B { };` 中，`C` 对象与它的成员 `x` 是否指针可互转？"

<details markdown="1">
<summary>答案</summary>

是。`C` 是标准布局类，所有数据成员都首次声明在 `A` 这一个类里。按 ¶7.3，`C` 对象与它的基类子对象 `B`、`A` 都指针可互转；`A` 子对象是标准布局类的对象，与它的首个非静态数据成员 `x` 指针可互转；再由 ¶7.4 的传递性，`C` 对象与 `x` 指针可互转。所以 `reinterpret_cast<int*>(&c)` 指向 `c.x`。
</details>

!!! question "2. 为什么 ¶6 把 `if (p)` 规定为实现定义，而不是像 `*p` 一样规定为 UB，或者干脆规定为有定义的？"

<details markdown="1">
<summary>答案</summary>

不规定为有定义，是因为某些架构在把无效地址装入地址寄存器时就可能陷入，存储释放后它的地址空间也可能被重新映射，标准不能要求所有实现都给出有意义的结果。

不规定为 UB，是因为大量实际代码（无锁算法中的比较、调试断言、日志）在存储释放后仍会检查或比较指针。如果这些都是 UB，编译器就有权删除这些代码。实现定义是折中：主流实现上它就是按地址比较，而且实现必须在文档中说明。
</details>

!!! question "3. `int a[2][2]{}; int* p = &a[0][0]; p[3] = 1;` 合法吗？"

<details markdown="1">
<summary>答案</summary>

不合法，是 UB。`p` 指向 `a[0]`（一个 `int[2]`）的元素 `a[0][0]`。按 [[expr.add]]，`p + 2` 是 `a[0]` 的尾后指针，`p + 3` 已经超出这个数组，指针算术本身就是 UB。尽管 `a[1][1]` 恰好在那个地址，尾后指针不指向无关对象的规定（¶3 注 2）与 [[expr.add]] 的数组边界一起，禁止了把多维数组当一维数组用的写法。`std::launder` 也无法补救，因为经由 `&a[0][0]` 能到达的字节只有 `a[0]` 的。
</details>
