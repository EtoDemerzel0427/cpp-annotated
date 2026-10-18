---
title: reinterpret_cast
summary: reinterpret_cast 允许的全部转换（指针↔整数、函数指针之间、对象指针之间、函数指针↔对象指针、成员指针之间、引用双关）及每种转换真正保证的东西：往返不变，只有指针可互转时才指向新对象；为什么经 reinterpret_cast 的类型双关访问是 UB；整数到指针的实现定义，以及 C++23 删除的安全派生指针
status: draft
papers: P2186R2, P0137R1, P0593R6, P0476R2, P2590R2
related: expr.static.cast, expr.const.cast, expr.cast, expr.call, basic.lval, basic.compound, basic.align, conv.ptr, intro.object, bit.cast, obj.lifetime, topics/casts
tags: 类型转换, 指针, 严格别名, 类型双关, UB
updated: 2026-10-17
---

`reinterpret_cast` 名字最吓人，实际保证的东西却最少。它的设计思路是**改变类型，不改变值（或位置）**：把一个指针重新解释为另一种指针、整数或引用。它几乎从不生成机器指令。

理解它的关键是区分两件事：

1. 转换本身是否合法。通常合法，规则在本节。
2. 使用转换的结果是否合法。通常不合法，规则在别处：经结果指针访问对象，受 [[basic.lval#11]] 的严格别名规则约束；经结果函数指针调用，受 [[expr.call#6]] 的调用兼容规则约束；成员访问受 [[expr.ref#10]] 约束。

`reinterpret_cast` 能保证的几乎只有一件事，就是往返：转换过去再转换回来，得到原值。

## 总则（¶1–3）

¶1：`reinterpret_cast<T>(v)` 的结果是把 `v` 转换为 `T`。值类别与 [[expr.static.cast]] 相同：`T` 是左值引用或函数右值引用 ⇒ lvalue；对象右值引用 ⇒ xvalue；否则 prvalue，并对 `v` 施行左值到右值、数组到指针、函数到指针转换。能用 `reinterpret_cast` 显式完成的转换都列在下文，**其他任何转换都不能用它完成**。

¶2：`reinterpret_cast` 不能去掉常量性（[[expr.const.cast#6]]）。整型、枚举、指针、成员指针类型的表达式可以转换为它自身的类型，结果是操作数的值。有了这一条，泛型代码面对可能已经是目标类型的值，也可以无条件地写 `reinterpret_cast`。

¶3（注 1）：`reinterpret_cast` 所做的映射，可能产生与原值不同的表示，也可能不产生。

```cpp title="rc-basic.cpp" error
#include <cstdint>

void t(int* ip, const int* cip) {
    int a = reinterpret_cast<int>(5);            // OK：¶2 整型转换为自身类型
    int* q = reinterpret_cast<int*>(ip);         // OK：指针转换为自身类型
    int* w = reinterpret_cast<int*>(cip);        // error: 去掉了 const
    double d = reinterpret_cast<double>(1L);     // error: 不能在算术类型之间转换（用 static_cast 或 std::bit_cast）
    char c = reinterpret_cast<char>(ip);         // error: char 不足以容纳指针的所有值
    (void)a; (void)q; (void)w; (void)d; (void)c;
}
```

注意 `reinterpret_cast<double>(1L)` 是非良构的，`reinterpret_cast` 不能重新解释算术值的位模式。很多人以为它可以，于是写出 `*reinterpret_cast<double*>(&l)`。这其实是一次指针转换加一次 UB 的访问（见下文“为什么类型双关是 UB”）。

## 指针 → 整数（¶4）

¶4：指针可以显式转换为任何一个足以区分其类型所有值表示的整型。**映射函数由实现定义**。注 2 说明，这个映射的本意是让了解底层机器寻址结构的人不感到意外。

`std::nullptr_t` 类型的值可以转换为整型，含义与有效性都等同于把 `(void*)0` 转换为该整型。注 3：`reinterpret_cast` 不能把任何值转换为 `std::nullptr_t`。

```cpp run title="ptr-to-int.cpp" ok
#include <cstdint>

int main() {
    int x = 0;
    auto u = reinterpret_cast<std::uintptr_t>(&x);    // 实现定义的映射，通常就是地址值
    auto z = reinterpret_cast<std::uintptr_t>(nullptr);   // 等同于 (std::uintptr_t)(void*)0
    int* back = reinterpret_cast<int*>(u);            // ¶5：从指针得来的整数转换回指针
    *back = 1;                                        // OK：back 指向 x（见 ¶5）
    return (x == 1 && z == 0) ? 0 : 1;                // z == 0 在常见平台成立，但标准不保证
}
```

`std::uintptr_t` 和 `std::intptr_t` 是可选的类型（[[cstdint.syn]]）：只有存在一个能让 `void*` 往返的整型时，实现才提供它们。

## 整数 → 指针（¶5）

¶5：整型或枚举类型的值可以显式转换为指针。当前草案分两种情况：

1. 如果该整数值能由一个或多个指针值转换得到，结果是这些指针值中能使程序具有定义行为的某一个，具体是哪一个未指定。如果不存在这样的指针值，**行为未定义**。
2. 否则，即这个整数不是由任何指针转换来的（例如硬件寄存器地址 `0x40001000`），结果**由实现定义**。注 5：它可以是一个无效指针值。

第 1 条的措辞涉及**指针来源**（pointer provenance）。一个整数可能同时对应多个指针，例如一个对象末尾之后的地址恰好等于下一个对象的起始地址，二者转换成整数后相等。标准在这里采用“天使般的非确定性”：实现必须从这些候选中选出一个不会让程序出现 UB 的指针。如果随后用它访问第二个对象，它就是指向第二个对象的指针。注 4 提醒，结果仍可能是无效指针值，或者在转换的上下文中无效（指向存储期已结束或尚未开始的区域）。

!!! history "安全派生指针的删除"
    C++11 为支持（可选的）垃圾回收引入了**安全派生指针**（safely-derived pointer）的概念：只有从 `new` 得到、再经过一系列可追踪运算的指针才算安全派生的。把指针转换为整数、做运算后再转回来，所得的指针在严格指针安全的实现上可能无效。与之配套的还有 `std::declare_reachable` 等库函数。没有任何主流实现采用严格指针安全，C++23 通过 [[P2186R2]] 删除了整个垃圾回收支持，安全派生指针的概念也随之删除。此后整数到指针的往返只受上述来源规则约束。

## 函数指针之间（¶6）

¶6：函数指针可以显式转换为不同类型的函数指针，指针值不变。注 6：如果所用的函数指针类型与函数定义的类型不调用兼容，经它调用函数是 UB（[[expr.call#6]]）。

```cpp run title="fnptr-cast.cpp" ok
int add(int a, int b) { return a + b; }

int main() {
    using Generic = void (*)();
    Generic g = reinterpret_cast<Generic>(&add);    // OK：存成"通用"函数指针
    auto f = reinterpret_cast<int (*)(int, int)>(g);  // OK：转换回原类型
    return f(1, 2) == 3 ? 0 : 1;                    // OK：以原类型调用
    // reinterpret_cast<int (*)(long, long)>(g)(1, 2) 是 UB：不调用兼容
}
```

在 C 风格回调表和动态加载的代码中，存储异构函数指针的标准做法就是先存成 `void (*)()`，用时再转回来。

## 对象指针之间（¶7）

!!! std
    When a prvalue v of object pointer type is converted to the object pointer type "pointer to cv T", the result is `static_cast<cv T*>(static_cast<cv void*>(v))`.

    对象指针 `v` 转换为“指向 cv `T` 的指针”时，结果就是先转换到 `cv void*`，再 `static_cast` 到 `cv T*`。

这条规则把 `reinterpret_cast` 的对象指针转换**完全定义在 `static_cast` 之上**（C++11 起对标准布局类型如此，后来推广到所有对象指针类型），因此结果由 [[expr.static.cast#12]] 决定：

- 地址不满足 `T` 的对齐要求时，结果值未指定；
- 地址上有一个与原对象指针可互转、且类型与 `T` 相似的对象时，结果指向那个对象；
- 否则指针值不变，结果仍指向原对象，只是类型变了。

注 7 给出由此推出的往返保证：`T1*` 指向一个 `T1` 对象，先转换为 `T2*`（`T2` 的对齐要求不严于 `T1`），再转换回 `T1*`，得到原指针值。

```cpp run title="obj-ptr-cast.cpp" ok
struct S { int first; double second; };   // 标准布局

int main() {
    S s{1, 2.0};
    int* pi = reinterpret_cast<int*>(&s);      // s 与 s.first 指针可互转 ⇒ pi 指向 s.first
    *pi = 10;                                  // OK
    S* back = reinterpret_cast<S*>(pi);        // s.first 与 s 指针可互转 ⇒ 指向 s
    return (back == &s && s.first == 10) ? 0 : 1;
}
```

## 为什么类型双关是 UB

**类型双关**（type punning）指把一个对象的存储当作另一个类型来读写。用 `reinterpret_cast` 做双关的典型写法如下：

```cpp run title="punning-ub.cpp" ub
#include <cstdint>

float fast_abs(float f) {
    std::uint32_t bits = *reinterpret_cast<std::uint32_t*>(&f);   // UB: 经 uint32_t 左值读 float 对象
    bits &= 0x7fffffffu;
    return *reinterpret_cast<float*>(&bits);                      // UB: 经 float 左值读 uint32_t 对象
}

int main() { return fast_abs(-1.0f) == 1.0f ? 0 : 1; }
```

按 ¶7，`reinterpret_cast<std::uint32_t*>(&f)` 本身合法：那里没有可互转的 `uint32_t` 对象，于是指针值不变，结果仍指向 `float` 对象 `f`。UB 发生在解引用之后的读取。[[basic.lval#11]] 规定，经类型为 `Tref` 的 glvalue 访问动态类型为 `Tobj` 的对象时，只有 `Tref` 与 `Tobj`（或其有/无符号对应类型）相似，或与 `char`/`unsigned char`/`std::byte` 相似，该对象才是可经类型访问的（type-accessible），否则是 UB。这就是**严格别名规则**（strict aliasing rule）。

为什么要有这条规则？因为它让编译器可以做基于类型的别名分析：编译器假定不同类型的左值不指向同一对象，于是可以自由地重排、缓存读写。

```cpp run title="strict-aliasing-opt.cpp" flags="-std=c++2c -O2" ub
int f(int* i, float* p) {
    *i = 1;
    *p = 2.0f;
    return *i;      // 编译器可以假定 *p 的写入不影响 *i，直接返回 1
}

int main() {
    int x = 0;
    return f(&x, reinterpret_cast<float*>(&x));   // UB: 经 float 左值写 int 对象
}
// 本机 Clang -O2：f 被编译为"存 1、存 2.0f、返回常量 1"，程序退出码为 1；
// 加 -fno-strict-aliasing 后重新从内存读取 *i，退出码变为 0（0x40000000 的低 8 位）。
```

!!! impl "编译器与严格别名"
    GCC 和 Clang 在 `-O2` 及以上默认启用 `-fstrict-aliasing`；Linux 内核等项目用 `-fno-strict-aliasing` 编译。GCC 的 `-Wstrict-aliasing` 能发现一部分直接的双关写法。MSVC 历来不做基于类型的别名优化，所以在 MSVC 上能正常运行的双关代码，移植到 GCC/Clang 后可能出错。

合法的替代写法如下（详见 [[topics/casts]]）：

- `std::bit_cast<To>(from)`（C++20，[[P0476R2]]，[[bit.cast]]）：按位复制到一个新对象，可用于常量求值；
- `std::memcpy`：把字节复制到目标类型的对象中（C++20 起 `memcpy` 还会隐式创建对象，[[P0593R6]]）；
- 经 `char`、`unsigned char`、`std::byte` 左值逐字节访问，这是严格别名规则明确给出的豁免；
- `std::start_lifetime_as<T>(p)`（C++23，[[P2590R2]]，[[obj.lifetime]]）：在已有的字节上开始一个 `T` 对象的生命周期，并保留字节内容，适合把网络缓冲区当作某个结构体来读。

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

static_assert(abs_bitcast(-2.5f) == 2.5f);   // bit_cast 可在编译期使用

int main() { return (abs_bitcast(-1.0f) == 1.0f && abs_memcpy(-1.0f) == 1.0f) ? 0 : 1; }
```

## 函数指针 ↔ 对象指针（¶8）

¶8：函数指针与对象指针之间的转换是**有条件支持**的（conditionally-supported），含义由实现定义。但如果实现两个方向都支持，往返（cv 限定可以不同）必须得到原指针值。

为什么是有条件支持？因为在某些体系结构上，代码与数据位于不同的地址空间，连指针宽度都可能不同（哈佛结构、x86 实模式的 near/far 指针）。POSIX 要求支持这种转换，因为 `dlsym` 返回 `void*`，却常用来取得函数。GCC、Clang、MSVC 都支持这种转换；本机 Clang 即使在 `-pedantic` 下也不对它发出警告。

```cpp run title="fn-obj-ptr.cpp" impl
void fn() {}

int main() {
    void* vp = reinterpret_cast<void*>(&fn);           // 有条件支持
    auto back = reinterpret_cast<void (*)()>(vp);      // 若两个方向都支持，往返得到原值
    back();
    return back == &fn ? 0 : 1;
}
```

## 空指针值（¶9）

¶9：空指针值转换为目标类型的空指针值。注 8 有两个要点：

- `std::nullptr_t` 类型的空指针常量不能经 `reinterpret_cast` 转换为指针类型，`reinterpret_cast<int*>(nullptr)` 是非良构的，应直接写 `static_cast<int*>(nullptr)` 或使用隐式转换；
- 整数类型的空指针常量（`0`）不一定转换为空指针值：`reinterpret_cast<int*>(0)` 走的是 ¶5 的整数到指针映射，而不是 [[conv.ptr]] 的空指针转换。在空指针的位表示不是全零的平台上，二者的结果不同。

```cpp title="rc-null.cpp" error
void t() {
    int* a = reinterpret_cast<int*>(nullptr);   // error: 不能从 std::nullptr_t 转换到指针
    int* b = reinterpret_cast<int*>(0);         // OK：但结果是 ¶5 的实现定义值，不保证是空指针
    int* c = static_cast<int*>(0);              // OK：空指针转换，保证是空指针
    (void)a; (void)b; (void)c;
}
```

## 成员指针之间（¶10）

¶10：只要 `T1` 与 `T2` 都是函数类型或都是对象类型，“`X` 的成员指针，类型为 `T1`”就可以显式转换为“`Y` 的成员指针，类型为 `T2`”（`X`、`Y` 可以无关）。空成员指针转换为空成员指针。除以下情形外，结果未指定：

- ¶10.1 成员函数指针转换为另一种成员函数指针类型，再转换回来，得到原值；
- ¶10.2 数据成员指针转换为另一种数据成员指针类型（`T2` 的对齐要求不严于 `T1`），再转换回来，得到原值。

也就是说，成员指针同样只保证往返。

## 引用的双关（¶11）

¶11：设类型为 `T1` 的 glvalue `v` 指代对象或函数 *x*。只要“指向 `T1` 的指针”能经 `reinterpret_cast` 转换为“指向 `T2` 的指针”，`v` 就可以转换为“`T2` 的引用”，结果就是 `*reinterpret_cast<T2*>(p)`，其中 `p` 是指向 *x* 的 `T1*`。注 9：这一转换不会实质化或创建临时量，不做复制，也不调用构造函数或转换函数。脚注 49：当结果引用的是与源 glvalue 相同的对象时，这种做法有时称为类型双关。

```cpp title="rc-ref.cpp" error
void t() {
    int i = 0;
    float& fr = reinterpret_cast<float&>(i);       // OK：转换本身合法；经 fr 读写 i 是 UB
    long&& lr = reinterpret_cast<long&&>(i);       // OK：结果是亡值，同样只能"看不能碰"
    int&& rr = reinterpret_cast<int&&>(5);         // error: 操作数必须是 glvalue
    (void)fr; (void)lr; (void)rr;
}
```

它与 `static_cast` 的根本区别在于：`static_cast<float>(i)` 会创建一个新的 `float` 值（3 变成 3.0f），而 `reinterpret_cast<float&>(i)` 只是换一个类型看同一块内存，不做任何转换。

## 不能出现在常量表达式中

`reinterpret_cast` 表达式不是核心常量表达式（[[expr.const.core]]）。这条规则有两层用意：常量求值器无法给重新解释过的指针赋予有意义的语义；同时，编译期计算也因此不会涉及实现定义的映射。需要在编译期重新解释位模式时，用 `std::bit_cast`。

```cpp title="rc-constexpr.cpp" error
constexpr int g() {
    int x = 1;
    return *reinterpret_cast<unsigned*>(&x);   // 即使"访问"本身合法（有符号/无符号对应类型）
}
static_assert(g() == 1);                       // error: reinterpret_cast 不能出现在常量求值中
```

## 历史与演进

!!! history
    - **C++98**：引入 `reinterpret_cast`；对象指针之间转换的结果未指定，只保证往返。
    - **C++11**：对标准布局类型，¶7 的结果改为经 `void*` 以 `static_cast` 定义（后来推广到所有对象类型）；函数指针与对象指针之间的转换改为有条件支持（C++03 中不允许）；引入安全派生指针。
    - **C++17**：采用 [[P0137R1]] 的对象模型（指针可互转、`std::launder`），¶7 的结果改用“指向哪个对象”来描述。
    - **C++20**：`std::bit_cast`（[[P0476R2]]）提供合法的位模式重解释；引入对象的隐式创建（[[P0593R6]]）。
    - **C++23**：删除垃圾回收支持与安全派生指针（[[P2186R2]]）；新增 `std::start_lifetime_as`（[[P2590R2]]）。
    - **当前草案**：¶5 改为基于来源的措辞，整数若由指针转换而来，结果是能使程序具有定义行为的候选之一。

## 陷阱

!!! pitfall "`reinterpret_cast` 后解引用几乎总是 UB"
    除了 `char`/`unsigned char`/`std::byte` 以及有/无符号对应类型，经 `reinterpret_cast` 得到的指针去读写原对象都违反严格别名规则。能编译、在 `-O0` 下能运行，并不代表正确。

!!! pitfall "从字节缓冲区 `reinterpret_cast` 出结构体"
    `auto* hdr = reinterpret_cast<Header*>(buf);` 在 C++20 之前几乎总是 UB，因为那里没有 `Header` 对象。C++20 起，如果 `buf` 来自 `std::malloc`、`new unsigned char[]` 等会隐式创建对象的操作，且 `Header` 是隐式生存期类型，对象就可能已被隐式创建；但如果缓冲区已经被其他类型的对象占用，或者之后又被写入，情况会更复杂。最清晰的写法是 `std::start_lifetime_as<Header>(buf)`（C++23），或者 `memcpy` 到一个局部 `Header`。另外别忘了对齐：按 ¶7，未对齐的地址得到的是未指定值。

!!! pitfall "`reinterpret_cast<Base*>(derived_ptr)` 不做偏移调整"
    在多重继承中，非首个基类子对象与派生对象不在同一地址。`reinterpret_cast` 不了解继承关系，结果仍指向派生对象（[[expr.ref#10]] 的标准例正是这种情况）。Clang 有专门的 `-Wreinterpret-base-class` 警告。

## 思考题

!!! question "思考题 1"
    `int a[2] = {1, 2}; int* p = reinterpret_cast<int*>(reinterpret_cast<std::uintptr_t>(&a[0]) + sizeof(int));` 中 `*p` 是否有定义？

<details markdown="1">
<summary>答案</summary>

按 ¶5，在映射就是地址的实现上，整数值 `addr(a[0]) + sizeof(int)` 恰好等于 `&a[1]` 转换得到的整数，所以它是能由指针值转换得到的值。候选之中，指向 `a[1]` 的指针能使 `*p` 有定义，于是结果选为指向 `a[1]`，`*p == 2`。但这依赖于实现定义的映射（¶4）恰好是线性的，标准本身并不保证整数加法对应指针算术。可移植的写法是 `&a[0] + 1`。
</details>

!!! question "思考题 2"
    `unsigned u = 1; int& r = reinterpret_cast<int&>(u); r = -1;` 是否 UB？`u` 的值是多少？

<details markdown="1">
<summary>答案</summary>

不是 UB。转换本身合法（¶11）；`int` 是 `unsigned int` 对应的有符号类型，按 [[basic.lval#11]]（11.2），`u` 可以经 `int` glvalue 访问。写入 `-1` 后，`u` 的对象表示是 `-1` 的二进制补码，即 `UINT_MAX`。这是少数合法的 `reinterpret_cast` 双关之一。
</details>

!!! question "思考题 3"
    为什么 `reinterpret_cast<double>(x)` 非良构，而 `reinterpret_cast<long>(x)`（`x` 是 `long`）良构？

<details markdown="1">
<summary>答案</summary>

¶1 规定只有列出的转换才能用 `reinterpret_cast`。¶2 允许整型、枚举、指针、成员指针转换为自身类型，所以 `long` → `long` 合法；列表中没有任何算术类型到算术类型的转换，所以 `long` → `double` 非良构。重新解释算术值的位模式是 `std::bit_cast` 的职责。
</details>

## 小结

!!! summary
    | 条款 | 转换 | 保证 |
    |---|---|---|
    | ¶2 | 整数/枚举/指针/成员指针 → 自身类型 | 值不变 |
    | ¶4 | 指针 → 足够宽的整数；`nullptr_t` → 整数 | 映射由实现定义 |
    | ¶5 | 整数/枚举 → 指针 | 来自指针 ⇒ 未指定地选一个使行为有定义的候选（无则 UB）；否则实现定义 |
    | ¶6 | 函数指针 → 函数指针 | 值不变；以不兼容类型调用 ⇒ UB |
    | ¶7 | 对象指针 → 对象指针 | ≡ `static_cast` 经 `void*`；可互转才指向新对象；往返不变（对齐允许时） |
    | ¶8 | 函数指针 ↔ 对象指针 | 有条件支持；双向支持则往返不变 |
    | ¶9 | 空指针值 | → 空指针值；`nullptr_t` 不能转为指针；整数 `0` 不保证得空指针 |
    | ¶10 | 成员指针 → 成员指针 | 只保证往返 |
    | ¶11 | glvalue → 引用 | ≡ `*reinterpret_cast<T2*>(&x)`；不创建临时量 |

    转换本身几乎总是合法的，问题出在**使用结果**：访问受严格别名规则约束，调用受调用兼容规则约束。
