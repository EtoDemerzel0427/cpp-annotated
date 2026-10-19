---
title: reinterpret_cast
summary: reinterpret_cast 能做的转换（指针与整数、函数指针之间、对象指针之间、函数指针与对象指针、成员指针之间、引用）以及每一种真正保证的东西：转换几乎总是合法的，通常只保证往返，而经结果访问对象往往违反严格别名规则。
status: done
papers: P2186R2, P0137R1, P0593R6, P0476R2, P2590R2
related: expr.static.cast, expr.const.cast, expr.cast, expr.call, basic.lval, basic.compound, basic.align, conv.ptr, intro.object, bit.cast, obj.lifetime, topics/casts, topics/type-punning
tags: 类型转换, 指针, 严格别名, 类型双关, UB
updated: 2026-10-19
---

!!! tldr
    - `reinterpret_cast` 改变类型而不改变值：把指针重新看成另一种指针、整数或引用，几乎不生成任何指令。
    - 转换本身通常合法，保证却很少，主要只有一条：转过去再转回来，得到原值。
    - 对象指针之间的 `reinterpret_cast<T*>(p)` 就是 `static_cast<T*>(static_cast<void*>(p))`。地址上没有可以互转的 `T` 对象时，结果仍指向原对象，通过它读写通常违反严格别名规则。
    - 要重新解释一个值的位模式，用 `std::bit_cast` 或 `std::memcpy`，不要用 `reinterpret_cast` 加解引用。
    - `reinterpret_cast` 不能去掉 `const`，不能在算术类型之间转换，也不能出现在常量表达式中。

## 转换合法，使用未必合法

```cpp run title="strict-aliasing-opt.cpp" flags="-std=c++2c -O2" ub
int f(int* i, float* p) {
  *i = 1;
  *p = 2.0f;
  return *i;   // 编译器假设 *p 与 *i 不是同一个对象
}

int main() {
  int x = 0;
  return f(&x, reinterpret_cast<float*>(&x));  // UB: 用 float 左值写 int 对象
}
```

本机 Clang 以 `-O2` 编译，`f` 被优化成存 1、存 2.0f、直接返回常量 1，程序退出码是 1。加上 `-fno-strict-aliasing` 之后，`f` 重新从内存读 `*i`，退出码变成 0，也就是 2.0f 的位模式 `0x40000000` 的低 8 位。

`reinterpret_cast<float*>(&x)` 这次转换本身完全合法。出问题的是之后通过 `float` 左值去写一个 `int` 对象。所以讨论 `reinterpret_cast` 时要分清两件事：

1. 转换是否合法。规则在本节，通常是合法的。
2. 使用结果是否合法。规则在别处：通过结果指针访问对象受[[basic.lval#11|严格别名规则]]约束，通过结果函数指针调用受 [[expr.call#6]] 约束，成员访问受 [[expr.ref#10]] 约束。

## 能做哪些转换（¶1–¶3）

¶1 结果的值类别与 [[expr.static.cast]] 相同：`T` 是左值引用或函数的右值引用时是左值，是对象的右值引用时是亡值，否则是 prvalue，这时先对操作数做左值到右值、数组到指针、函数到指针转换。能用 `reinterpret_cast` 做的转换都在下文列出，其余一概不行。

¶2 `reinterpret_cast` 不能去掉 `const` 或 `volatile`（[[expr.const.cast#6]]）。整数、枚举、指针、成员指针类型的表达式可以转换为自身的类型，结果就是操作数的值。这样泛型代码遇到可能已经是目标类型的值时，也能无条件地写 `reinterpret_cast`。

¶3 是一条注：`reinterpret_cast` 做的映射，可能产生与原值不同的表示，也可能不产生。

```cpp title="rc-basic.cpp" error
void t(int* ip, const int* cip) {
  int a = reinterpret_cast<int>(5);         // OK：转换为自身类型
  int* q = reinterpret_cast<int*>(ip);      // OK：转换为自身类型
  int* w = reinterpret_cast<int*>(cip);     // error: 去掉了 const
  double d = reinterpret_cast<double>(1L);  // error: 算术类型之间不行
  char c = reinterpret_cast<char>(ip);      // error: char 装不下指针
  (void)a; (void)q; (void)w; (void)d; (void)c;
}
```

`reinterpret_cast<double>(1L)` 是非良构的，`reinterpret_cast` 不能重新解释算术值的位模式。很多人以为可以，于是写成 `*reinterpret_cast<double*>(&l)`，这其实是一次合法的指针转换加一次未定义的访问，见下文类型双关一节。

## 指针与整数（¶4、¶5）

¶4 指针可以转换为任何一个大到足以区分指针所有取值的整数类型，映射方式由实现定义。注 2 说，这个映射的本意是让了解底层机器寻址方式的人不感到意外，在常见平台上它就是地址值。

`std::nullptr_t` 的值也可以转换为整数，效果与把 `(void*)0` 转换为该整数相同。注 3 提醒，反过来不行：没有任何值能经 `reinterpret_cast` 转换为 `std::nullptr_t`。

```cpp run title="ptr-to-int.cpp" ok
#include <cstdint>

int main() {
  int x = 0;
  auto u = reinterpret_cast<std::uintptr_t>(&x);
  auto z = reinterpret_cast<std::uintptr_t>(nullptr);
  int* back = reinterpret_cast<int*>(u);   // 由指针得来的整数，转回指针
  *back = 1;                               // OK：back 指向 x
  return x == 1 && z == 0 ? 0 : 1;   // z == 0 在常见平台成立，标准不保证
}
```

`std::uintptr_t` 和 `std::intptr_t` 是可选的（[[cstdint.syn]]）：只有存在一个能让 `void*` 往返的整数类型时，实现才提供它们。

¶5 整数或枚举值可以转换为指针，分两种情况：

1. 这个整数值能由一个或多个指针值转换得到：结果是这些指针中能让程序行为有定义的某一个，选哪一个未指定。如果一个都没有，行为未定义。
2. 否则，比如整数是一个硬件寄存器的地址 `0x40001000`，结果由实现定义。注 5 说，它可能是一个无效指针值。

第 1 种情况涉及指针的**来源**（provenance）：一个指针不只是地址，还记着它指向哪个对象。一个整数可能对应多个指针，例如一个对象尾后的地址恰好等于下一个对象的起始地址，两者转换成的整数相同。这时实现必须选一个不会导致未定义行为的：如果随后用它访问第二个对象，它就是指向第二个对象的指针。注 4 提醒，即使这样，结果仍可能无效，例如它指向的存储期已经结束。这是 C++23 之后的新措辞。

!!! history "安全派生指针"
    C++11 为了支持可选的垃圾回收，引入了安全派生指针（safely-derived pointer）：只有从 `new` 得到、再经过可追踪运算的指针才算安全派生。指针转换成整数、运算之后再转回来，在采用严格指针安全的实现上可能无效。没有任何主流实现采用严格指针安全，C++23 通过 [[P2186R2]] 删除了整个垃圾回收支持，这个概念也一并删除。

## 对象指针之间（¶7）

!!! std
    When a prvalue v of object pointer type is converted to the object pointer type "pointer to cv T", the result is `static_cast<cv T*>(static_cast<cv void*>(v))`.

¶7 对象指针可以转换为另一种对象指针，结果就是先转换到 `void*`，再用 `static_cast` 转换到目标类型。所以结果完全由 [[expr.static.cast#12]] 决定：

- 地址不满足 `T` 的对齐要求时，结果的值未指定；
- 地址上有一个类型与 `T` 相似、并且与原对象**指针可互转**（pointer-interconvertible，可以用同一个地址互相到达，[[basic.compound]]）的对象时，结果指向那个对象；
- 否则指针值不变，结果仍指向原来的对象，只是类型变了。

```cpp run title="obj-ptr-cast.cpp" ok
struct S { int first; double second; };   // 标准布局

int main() {
  S s{1, 2.0};
  int* pi = reinterpret_cast<int*>(&s);  // 与 s.first 可互转：指向 s.first
  *pi = 10;                              // OK
  S* back = reinterpret_cast<S*>(pi);    // 指回 s
  return back == &s && s.first == 10 ? 0 : 1;
}
```

标准布局类对象与它的第一个非静态数据成员是指针可互转的，所以 `pi` 真的指向 `s.first`，通过它写入没有问题。

注 7 给出由此推出的往返保证：`T1*` 指向一个 `T1` 对象，转换为 `T2*`（`T2` 的对齐要求不比 `T1` 严格），再转回 `T1*`，得到原来的指针值。

## 为什么类型双关是未定义行为

**类型双关**（type punning）指把一个对象的存储当作另一个类型来读写。用 `reinterpret_cast` 的典型写法是这样：

```cpp run title="punning-ub.cpp" ub
#include <cstdint>

float fast_abs(float f) {
  auto bits = *reinterpret_cast<std::uint32_t*>(&f);  // UB: 读 float 对象
  bits &= 0x7fffffffu;
  return *reinterpret_cast<float*>(&bits);            // UB: 读 uint32_t 对象
}

int main() { return fast_abs(-1.0f) == 1.0f ? 0 : 1; }
```

按第 7 段，`reinterpret_cast<std::uint32_t*>(&f)` 本身合法：地址上没有可以互转的 `uint32_t` 对象，于是指针值不变，结果仍指向 `float` 对象 `f`。问题出在解引用后的读取。

[[basic.lval#11]] 规定，通过类型为 `Tref` 的 glvalue 访问动态类型为 `Tobj` 的对象，只有在 `Tref` 与下面之一相似时才允许：`Tobj` 本身、`Tobj` 对应的有符号或无符号类型、`char`、`unsigned char`、`std::byte`。其余情况都是未定义行为。这就是**严格别名规则**（strict aliasing rule）。

这条规则让编译器可以做基于类型的别名分析：它假设不同类型的左值不指向同一个对象，于是可以重排和缓存读写，开头的 `f` 就是这样被优化的。

!!! impl "编译器与严格别名"
    GCC 和 Clang 在 `-O2` 及以上默认启用 `-fstrict-aliasing`，Linux 内核等项目用 `-fno-strict-aliasing` 编译。MSVC 历来不做基于类型的别名优化，所以在 MSVC 上能正常运行的双关代码，移植到 GCC、Clang 后可能出错。

合法的替代写法有四种（详见 [[topics/type-punning]]）：

- `std::bit_cast<To>(from)`（C++20，[[P0476R2]]，[[bit.cast]]）：按位复制出一个新对象，可以在常量求值中使用；
- `std::memcpy`：把字节复制到目标类型的对象里，C++20 起它还会隐式创建对象（[[P0593R6]]）；
- 用 `char`、`unsigned char` 或 `std::byte` 左值逐字节访问，这是严格别名规则明确允许的；
- `std::start_lifetime_as<T>(p)`（C++23，[[P2590R2]]，[[obj.lifetime]]）：在已有的字节上开始一个 `T` 对象的生命期并保留字节内容，适合把网络缓冲区当作某个结构体来读。

```cpp run title="punning-ok.cpp" ok
#include <bit>
#include <cstdint>
#include <cstring>

constexpr float abs_bitcast(float f) {
  auto bits = std::bit_cast<std::uint32_t>(f) & 0x7fffffffu;
  return std::bit_cast<float>(bits);
}

float abs_memcpy(float f) {
  std::uint32_t bits;
  std::memcpy(&bits, &f, sizeof bits);
  bits &= 0x7fffffffu;
  std::memcpy(&f, &bits, sizeof f);
  return f;
}

static_assert(abs_bitcast(-2.5f) == 2.5f);   // 编译期也能用

int main() {
  return abs_bitcast(-1.0f) == 1.0f && abs_memcpy(-1.0f) == 1.0f ? 0 : 1;
}
```

## 函数指针（¶6、¶8）

¶6 函数指针可以转换为另一种函数指针类型，指针值不变。注 6 提醒，用一个与函数定义的类型不**调用兼容**（call-compatible，类型相同，或者只差 `noexcept`）的函数指针去调用函数，是未定义行为（[[expr.call#6]]）。

```cpp run title="fnptr-cast.cpp" ok
int add(int a, int b) { return a + b; }

int main() {
  using Generic = void (*)();
  auto g = reinterpret_cast<Generic>(&add);         // 存成通用函数指针
  auto f = reinterpret_cast<int (*)(int, int)>(g);  // 转回原类型
  return f(1, 2) == 3 ? 0 : 1;                      // OK：用原类型调用
}
```

如果改成 `reinterpret_cast<int (*)(long, long)>(g)(1, 2)`，类型不调用兼容，就是未定义行为。C 风格的回调表、动态加载的代码常用这种做法存放不同类型的函数指针：先存成 `void (*)()`，用时再转回原类型。

¶8 函数指针与对象指针之间的转换是**有条件支持**的（conditionally-supported，实现可以不支持，但不支持时必须诊断），含义由实现定义。如果实现两个方向都支持，往返必须得到原值。

```cpp run title="fn-obj-ptr.cpp" impl
void fn() {}

int main() {
  void* vp = reinterpret_cast<void*>(&fn);       // 有条件支持
  auto back = reinterpret_cast<void (*)()>(vp);  // 往返得到原值
  back();
  return back == &fn ? 0 : 1;
}
```

之所以是有条件支持，是因为有些体系结构的代码和数据在不同的地址空间里，指针宽度都可能不同。POSIX 要求支持这种转换，因为 `dlsym` 返回 `void*`，却经常用来取函数。GCC、Clang、MSVC 都支持；本机 Clang 在 `-pedantic` 下也不对它发出警告。

## 空指针（¶9）

¶9 空指针值转换为目标类型的空指针值。注 8 补充了两点：

- `std::nullptr_t` 类型的空指针常量不能经 `reinterpret_cast` 转换为指针，应当用 `static_cast` 或隐式转换；
- 整数类型的空指针常量 `0` 不一定得到空指针值。`reinterpret_cast<int*>(0)` 走的是第 5 段的整数到指针映射，而不是 [[conv.ptr]] 的空指针转换。在空指针的表示不是全零的平台上，两者结果不同。

```cpp title="rc-null.cpp" error
void t() {
  int* a = reinterpret_cast<int*>(nullptr);  // error: nullptr_t 到指针
  int* b = reinterpret_cast<int*>(0);  // OK：¶5 的映射，不保证是空指针
  int* c = static_cast<int*>(0);       // OK：保证是空指针
  (void)a; (void)b; (void)c;
}
```

## 成员指针（¶10）

¶10 只要 `T1` 和 `T2` 同为函数类型或同为对象类型，`X` 的成员指针（类型为 `T1`）就可以转换为 `Y` 的成员指针（类型为 `T2`），`X` 和 `Y` 可以毫无关系。空成员指针转换为空成员指针。除下面两种往返以外，结果都是未指定的：

- ¶10.1 成员函数指针转换为另一种成员函数指针类型，再转回来，得到原值；
- ¶10.2 数据成员指针转换为另一种数据成员指针类型（`T2` 的对齐要求不比 `T1` 严格），再转回来，得到原值。

## 引用（¶11）

¶11 设 glvalue `v` 的类型是 `T1`，指代对象或函数 *x*。只要 `T1*` 能经 `reinterpret_cast` 转换为 `T2*`，`v` 就能转换为 `T2&`，结果就是 `*reinterpret_cast<T2*>(p)`，其中 `p` 是指向 *x* 的 `T1*`。注 9 强调，这个转换不创建临时量，不复制，也不调用构造函数或转换函数。

```cpp title="rc-ref.cpp" error
void t() {
  int i = 0;
  float& fr = reinterpret_cast<float&>(i);  // OK：转换合法，通过 fr 读写是 UB
  long&& lr = reinterpret_cast<long&&>(i);  // OK：结果是亡值
  int&& rr = reinterpret_cast<int&&>(5);    // error: 操作数必须是 glvalue
  (void)fr; (void)lr; (void)rr;
}
```

这正是它与 `static_cast` 的区别：`static_cast<float>(i)` 创建一个新的 `float` 值，3 变成 3.0f；`reinterpret_cast<float&>(i)` 只是换一个类型看同一块内存。脚注 49 说，结果引用的是与源 glvalue 相同的对象时，这种做法有时称为类型双关。

## 不能用于常量表达式

`reinterpret_cast` 表达式不是核心常量表达式（[[expr.const.core]]）。常量求值器无法给重新解释过的指针赋予有意义的语义，编译期计算也因此不会涉及实现定义的映射。需要在编译期重新解释位模式时，用 `std::bit_cast`。

```cpp title="rc-constexpr.cpp" error
constexpr int g() {
  int x = 1;
  return *reinterpret_cast<unsigned*>(&x);  // 访问本身是允许的
}
static_assert(g() == 1);   // error: reinterpret_cast 不能出现在常量求值中
```

## 历史与演进

!!! history
    - C++98：引入 `reinterpret_cast`。对象指针之间转换的结果未指定，只保证往返。
    - C++11：第 7 段的结果改为经 `void*` 用 `static_cast` 定义，但当时只适用于两边都是标准布局类型的情形，后来的修订推广到所有对象指针。函数指针与对象指针之间的转换从不允许改为有条件支持。引入安全派生指针。
    - C++17：采用 [[P0137R1]] 的对象模型（指针可互转、`std::launder`），第 7 段的结果改为用指针指向哪个对象来描述。
    - C++20：`std::bit_cast`（[[P0476R2]]）提供合法的位模式重新解释；引入对象的隐式创建（[[P0593R6]]）。
    - C++23：删除垃圾回收支持和安全派生指针（[[P2186R2]]）；新增 `std::start_lifetime_as`（[[P2590R2]]）。
    - C++23 之后：第 5 段改为基于来源的措辞。

## 常见误解

!!! pitfall "能编译、-O0 下能跑，双关就没问题"
    除了 `char`、`unsigned char`、`std::byte` 和有无符号对应类型，通过 `reinterpret_cast` 得到的指针读写原对象都违反严格别名规则。开头的例子在 `-O0` 下结果正常，到 `-O2` 就变了。

!!! pitfall "把字节缓冲区 reinterpret_cast 成结构体"
    `auto* hdr = reinterpret_cast<Header*>(buf);` 在 C++20 之前几乎总是未定义行为，因为那里没有 `Header` 对象。C++20 起，如果 `buf` 来自 `std::malloc`、`new unsigned char[]` 这类会隐式创建对象的操作，而 `Header` 是隐式生命期类型，对象可能已经被隐式创建；但缓冲区如果已经被其他类型的对象占用，情况就复杂得多。最清楚的写法是 `std::start_lifetime_as<Header>(buf)`（C++23），或者 `memcpy` 到一个局部的 `Header`。还要注意对齐：按第 7 段，未对齐的地址得到的是未指定的值。

!!! pitfall "reinterpret_cast 到基类指针"
    多重继承中，第二个及以后的基类子对象与派生对象不在同一地址。`reinterpret_cast` 不知道继承关系，不做偏移调整，结果仍指向派生对象；之后访问基类成员是未定义行为（[[expr.ref#10]] 的例 2 正是这种情况）。本机 Clang 用 `-Wreinterpret-base-class` 警告这种写法。

## 思考题

!!! question "思考题 1"
    ```cpp
    int a[2] = {1, 2};
    auto n = reinterpret_cast<std::uintptr_t>(&a[0]) + sizeof(int);
    int* p = reinterpret_cast<int*>(n);
    ```
    `*p` 有定义吗？

<details markdown="1">
<summary>答案</summary>

在映射就是地址值的实现上，`n` 恰好等于 `&a[1]` 转换得到的整数，所以它是能由指针值转换得到的值。按第 5 段，候选中指向 `a[1]` 的指针能让 `*p` 有定义，于是结果指向 `a[1]`，`*p == 2`。

不过这依赖于实现定义的映射（¶4）恰好是线性的，标准本身不保证整数加法对应指针算术。可移植的写法是 `&a[0] + 1`。
</details>

!!! question "思考题 2"
    `unsigned u = 1; int& r = reinterpret_cast<int&>(u); r = -1;` 是未定义行为吗？`u` 的值是多少？

<details markdown="1">
<summary>答案</summary>

不是。转换本身合法（¶11）；`int` 是 `unsigned int` 对应的有符号类型，按 [[basic.lval#11.2]]，`u` 可以通过 `int` glvalue 访问。

写入 `-1` 后，`u` 的值是 `UINT_MAX`，因为 `-1` 的二进制补码表示是全 1。这是少数合法的 `reinterpret_cast` 双关之一。
</details>

!!! question "思考题 3"
    `x` 是 `long` 时，为什么 `reinterpret_cast<double>(x)` 非良构，而 `reinterpret_cast<long>(x)` 良构？

<details markdown="1">
<summary>答案</summary>

¶1 规定只能做下文列出的转换。¶2 允许整数类型转换为自身类型，所以 `long` 到 `long` 可以；列表里没有任何算术类型到另一个算术类型的转换，所以 `long` 到 `double` 非良构。重新解释算术值的位模式是 `std::bit_cast` 的事。
</details>

## 小结

!!! summary
    | 条文 | 转换 | 保证 |
    |---|---|---|
    | ¶2 | 整数、枚举、指针、成员指针到自身类型 | 值不变 |
    | ¶4 | 指针到足够宽的整数；`nullptr_t` 到整数 | 映射由实现定义 |
    | ¶5 | 整数、枚举到指针 | 来自指针：选一个让行为有定义的候选，没有则 UB；否则实现定义 |
    | ¶6 | 函数指针到函数指针 | 值不变；以不兼容的类型调用是 UB |
    | ¶7 | 对象指针到对象指针 | 等于经 `void*` 的两次 `static_cast`；对齐允许时往返不变 |
    | ¶8 | 函数指针与对象指针互转 | 有条件支持；两个方向都支持时往返不变 |
    | ¶9 | 空指针值 | 得到空指针值；`nullptr_t` 不能转为指针；整数 `0` 不保证得到空指针 |
    | ¶10 | 成员指针到成员指针 | 只保证往返 |
    | ¶11 | glvalue 到引用 | 等于 `*reinterpret_cast<T2*>(&x)`；不创建临时量 |
