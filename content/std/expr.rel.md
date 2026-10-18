---
title: 关系运算符与相等性运算符
summary: "< > <= >= == != 的操作数转换与类型要求；指针的偏序（同一数组、同一对象的成员）与“无关指针比较结果未指定”；尾后指针与相邻对象相等性未指定；函数指针、成员指针（虚函数、无关类、联合体）的相等性；C++26 起两个数组不能直接比较；std::meta::info 的相等性"
status: done
covers: expr.rel, expr.eq
papers: P1120R0, P2865, P1847R4, P2996R13
related: expr.spaceship, expr.arith.conv, expr.type, conv.ptr, conv.qual, conv.mem, basic.compound, expr.add, comparisons.general, defns.order.ptr, expr.const.core, intro.object
tags: 比较, 指针, 成员指针, 未指定行为
updated: 2026-10-17
---

本页合并讲解 [[expr.rel]]（`<` `>` `<=` `>=`）与 [[expr.eq]]（`==` `!=`）。两者结构平行：先做哪些转换、操作数允许什么类型、算术比较怎么做、指针比较怎么做。对算术类型，它们几乎没有什么可说的；真正需要细读条文的，是**指针**和**成员指针**的比较：

- `==` 对几乎所有指针组合都有定义：地址相同即相等，只有尾后指针与相邻对象比较这一种情形是未指定的；
- `<` 只对同一数组内或同一对象的成员之间的指针给出保证，其余情况**结果未指定**（不是 UB）；
- 成员指针只能比较相等，并且在虚函数、无关类上有一些未指定的情形。

这些规则背后是贯穿 C++ 内存模型的一对矛盾：标准不想假设平坦的线性地址空间（以兼容分段架构和基于来源的优化），却又要让 `std::less<T*>` 能给出全序、让 `std::set<T*>` 可用。

## 关系运算符 [expr.rel]

### 转换与操作数类型（¶1–¶3）

¶1 关系运算符从左往右结合。标准自带的例子提醒，`a<b<c` 的意思是 `(a<b)<c`，而不是 `(a<b)&&(b<c)`，即拿一个 `bool` 与 `c` 比较。

```cpp run title="rel-chain.cpp" ok flags="-std=c++2c -Wno-error=parentheses"
int main() {
    int a = 5, b = 3, c = 2;
    bool x = a < b < c;    // (5 < 3) < 2  →  false < 2  →  0 < 2  →  true
    return x ? 0 : 1;      // 返回 0：x 为 true，尽管 5 < 3 < 2 在数学上为假
}
```

按标准这是良构的程序。但 Clang 23 对它给出的诊断默认就是错误："chained comparison 'X < Y < Z' does not behave the same as a mathematical expression [-Wparentheses]"。它属于 `-Wparentheses` 警告组，可以用 `-Wno-error=parentheses` 降回警告（上例的 godbolt 按钮已加上该选项）。这是编译器出于实用考虑拒绝良构代码的一个例子：严格来说不符合标准，但几乎不会误伤有意这样写的代码，真有需要时写成 `(a < b) < c` 即可。

操作数先经左值到右值（[[conv.lval]]）和函数到指针（[[conv.func]]）转换。**数组到指针转换只在另一个操作数是指针时进行**，这是 C++26 的关键修改：两个数组不再退化，于是无法比较（见下文“数组比较”一节）。

¶2 转换后的操作数必须是算术、枚举或指针类型。结果类型是 `bool`。因此 `nullptr_t`、成员指针、类类型（无重载时）都不能用关系运算符比较。

¶3 算术或枚举类型的操作数做常用算术转换（[[expr.arith.conv]]）；如果两个都是指针，则做指针转换（[[conv.ptr]]）、函数指针转换（[[conv.fctptr]]）和限定转换（[[conv.qual]]），使之成为复合指针类型（[[expr.type]]）。转换后两个操作数类型必须相同。

```cpp title="rel-operands-bad.cpp" error
struct S { int m; };
enum E1 { e1 };
enum E2 { e2 };

void f(int* p, long* q, int S::* pm) {
    bool a = p < q;              // error: int* 与 long* 没有复合指针类型
    bool b = p < 0;              // error: 指针与整数（即使是 0）不能做关系比较
    bool c = nullptr < nullptr;  // error: nullptr_t 不是指针
    bool d = pm < pm;            // error: 成员指针不能做关系比较
    bool e = e1 < e2;            // error: 不同枚举类型（C++26 起）
    bool g = e1 < 1.5;           // error: 枚举与浮点（C++26 起）
}
```

`p < 0` 有一段历史：早期标准允许指针与空指针常量做关系比较（空指针常量经转换成为同类型指针），后来的修订把它去掉了，因为问一个指针是否小于空指针没有任何意义。不同枚举之间、枚举与浮点之间的比较在 C++20 被 [[P1120R0]] 弃用，C++26 改为非良构（[[diff.cpp23.expr]]）。

常用算术转换的老问题在这里依然存在：

```cpp run title="rel-signed-unsigned.cpp" ok
int main() {
    int i = -1;
    unsigned u = 1;
    bool r = i < u;    // false！i 被转换为 unsigned，值为 UINT_MAX
    return r ? 1 : 0;  // 返回 0
}
```

`-Wsign-compare`（Clang/GCC 的 `-Wextra` 中包含）会警告这一行。`<=>` 对此直接非良构（[[expr.spaceship#4]]）；C++20 的 `std::cmp_less` 等函数（[[utility.intcmp]]）给出数学上正确的结果。

### 指针的偏序（¶4）

¶4 对指向对象的不等指针，比较结果由满足以下规则的一个**偏序**决定：

- ¶4.1 指向同一数组的不同元素（或其子对象）的两个指针：下标较大者必须比较为更大；
- ¶4.2 指向同一对象的不同非静态数据成员（或其子对象，递归地）的两个指针：后声明的成员必须比较为更大，前提是两个成员都不是零大小子对象，且该类不是联合体；
- ¶4.3 其他情况：不要求任何一方更大。

脚注沿用了 [[expr.add]] 的约定：非数组元素的对象视为 1 元素数组，尾后指针视为假想的第 *n* 号元素。所以 `p < a + n`（`p` 在数组 `a` 内）总是有意义的，这正是 `for (p = a; p < a + n; ++p)` 合法的原因。

```cpp run title="rel-partial-order.cpp" ok
struct Inner { int x, y; };
struct S {
    int a;
    Inner in;
    int b;
};

constexpr bool test() {
    int arr[4]{};
    S s{};
    return &arr[1] < &arr[3]          // ¶4.1
        && &arr[3] < arr + 4          // 尾后指针视为假想元素 4
        && &s.a < &s.b                // ¶4.2：b 声明在 a 之后
        && &s.a < &s.in.y             // ¶4.2：子对象递归适用
        && &s.in.x < &s.in.y;
}
static_assert(test());

int main() {}
```

¶4.2 的两个例外各有道理：

- 零大小子对象（如 `[[no_unique_address]]` 的空成员，[[intro.object]]）可能与其他成员共享地址，无法保证顺序；
- 联合体的所有成员地址相同（[[class.union]]），谈不上先后。

!!! history "成员地址顺序与访问控制"
    C++11–C++20 中，¶4.2 还要求两个成员具有相同的访问控制，因为当时允许实现重新排列不同访问区段（`public:`/`private:`）的成员。C++23 的 [[P1847R4]] 删除了这项重排许可（实际上没有任何实现利用过它），这里的条件也随之去掉。

### 结果与未指定（¶5–¶6）

¶5 把偏序转化为四个运算符的结果：若 `p` 与 `q` 相等（按 [[expr.eq]]），`<=`、`>=` 为真，`<`、`>` 为假；否则若 `p` 比较为大于 `q`，四个运算符给出相应一致的结果；**否则每个运算符的结果都是未指定的**。

注 1 补充了两点：

- 对不等的函数指针做关系比较，结果未指定（函数不属于任何数组，也不是成员，¶4 的偏序不涉及它们）；
- `void*` 可以指向对象（[[basic.compound]]），所以经 `void*` 比较同一数组的元素同样适用 ¶4。

**未指定（unspecified）不等于未定义（UB）**。比较两个无关对象的地址，程序不会因此失去意义，只是得不到可移植的答案，甚至同一表达式两次求值可以得到不同结果（[[intro.execution]] 注 5 允许未指定的求值在不同次执行中不一致）。但在常量求值中，结果未指定的比较会使表达式不是核心常量表达式（[[expr.const.core]] ¶2.28）：

```cpp title="rel-unrelated-const.cpp" error
int x, y;
bool rt = &x < &y;                     // OK: 运行期，结果未指定
constexpr bool ct = &x < &y;           // error: 不是常量表达式（结果未指定）
```

¶6 算术或枚举类型的操作数（转换后）：关系成立则 `true`，否则 `false`。对浮点而言，任何涉及 NaN 的关系都不成立，所以 `NaN < 1`、`NaN >= 1` 都是 `false`。

### `std::less` 的全序

既然 `<` 对无关指针未指定，`std::set<T*>`、`std::map<T*, V>` 怎么工作？答案在库里：`std::less<T*>` 等函数对象对指针使用实现定义的**严格全序**（[[comparisons.general#2]]、[[defns.order.ptr]]），这个全序与内置运算符给出的偏序一致。在平坦地址空间上，实现就是直接比较地址；在分段架构上，实现可以把段号也编码进比较。

```cpp run title="rel-std-less.cpp" ok
#include <functional>
#include <set>

int main() {
    int x = 0, y = 0;
    std::less<int*> lt;
    bool a = lt(&x, &y), b = lt(&y, &x);
    std::set<int*> s{&x, &y};       // 依赖 std::less<int*> 的全序
    return (a != b && s.size() == 2) ? 0 : 1;   // 恰好一个为真
}
```

所以**泛型代码比较指针时，应当用 `std::less` / `std::ranges::less`，而不是 `<`**。

### 数组比较 {{removed:C++26}}

C++23 及以前，`arr1 == arr2`、`arr1 < arr2` 会把两个数组都退化为指针，比较的是地址而不是内容，而这几乎从来不是程序员想要的。C++20 由 [[P1120R0]] 弃用了这种比较，C++26 由 [[P2865]] 移除：现在只有当另一个操作数是指针（对 `==`、`!=` 还包括空指针常量）时才进行数组到指针转换，于是两个数组相比是非良构的。

```cpp title="rel-array-compare.cpp" error
int a1[3], a2[3];

bool e1 = a1 == a2;          // error: C++26 起非良构（此前比较地址）
bool e2 = a1 < a2;           // error: 同上
bool e3 = "abc" == "abc";    // error: 两个字符串字面量也是两个数组！
```

```cpp run title="rel-array-compare-ok.cpp" ok
int a1[3], a2[3];

bool p1 = a1 == +a2;         // OK: 一元 + 强制退化，比较地址（结果 false）
bool p2 = +a1 < +a2;         // OK: 比较地址，结果未指定
int* p = a1;
bool p3 = p == a1;           // OK: 一边是指针，数组退化
bool p4 = a1 == nullptr;     // OK: 对 == 而言空指针常量也会触发退化（恒为 false）

int main() { return (p3 && !p1) ? 0 : 1; }
```

第三行 `"abc" == "abc"` 尤其需要注意：C 程序员常写的字符串字面量比较在 C++26 中直接非良构。这是好事，因为它从来不比较内容，而且两个相同字面量是否是同一对象本身就是未指定的（见下文）。

## 相等性运算符 [expr.eq]

### 转换与操作数类型（¶1–¶3）

¶1 `==` 和 `!=` 从左往右结合（所以 `a == b == c` 也是陷阱）；先做左值到右值与函数到指针转换；若一个操作数是指针或空指针常量，对另一个操作数做数组到指针转换。与 [[expr.rel]] 相比多出了空指针常量这一项，因此 `arr == nullptr`、`arr == 0` 是合法的（虽然恒为 `false`，Clang 会警告）。

¶2 转换后的操作数必须是标量类型（[[basic.types.general]]：算术、枚举、指针、成员指针、`std::nullptr_t`，以及 C++26 的 `std::meta::info`）。结果是 `bool`；在下面每种情形中，转换后两操作数类型必须相同。

¶3 任意两个指针值或两个成员指针值，要么相等，要么不等，不存在无法比较的情况。注 1 补充：只要两者都不是无效指针值（invalid pointer value，[[basic.compound]]），重复比较的结果就是一致的。对无效指针值（如已 `delete` 的指针）的比较，按 [[basic.compound]] 是实现定义的行为。

### 指针相等（¶4）

¶4 至少一个操作数是指针时，对两者做指针转换、函数指针转换、限定转换，得到复合指针类型。然后：

- ¶4.1 一个指针表示某个完整对象的地址，另一个表示另一个完整对象的尾后地址：结果**未指定**；
- ¶4.2 否则，若两者都为空、或指向同一个函数、或表示同一地址：相等；
- ¶4.3 否则：不等。

¶4.2 的判据是**表示同一地址**（represent the same address），而不是指向同一对象。所以指向不同对象但地址相同的指针相等：

```cpp run title="eq-same-address.cpp" ok
struct Empty {};
struct S { int a; double b; };
struct D : Empty { int x; };

constexpr bool test() {
    S s{};
    D d{};
    return static_cast<void*>(&s) == static_cast<void*>(&s.a)   // 标准布局类与首成员同址
        && static_cast<void*>(&d) == static_cast<void*>(static_cast<Empty*>(&d));  // 空基类子对象
}
static_assert(test());

int main() {}
```

### 尾后指针与相邻对象（¶4.1）

为什么偏偏尾后指针与相邻对象的比较是未指定的？考虑下面的例子：

```cpp title="eq-past-end.cpp" unspecified
#include <cstdio>

int main() {
    int a = 0, b = 0;
    int* p = &a + 1;     // a 的尾后指针
    int* q = &b;
    // 若 b 恰好紧接在 a 之后，p 与 q 表示同一地址。
    std::printf("%d\n", p == q);   // 未指定：可能是 0 也可能是 1
}
```

如果标准规定地址相同即相等，编译器就不能利用来源（provenance）做别名分析，即推断 `p` 由 `&a` 算出、因此不可能指向 `b`。实际上，GCC 等编译器确实会基于来源把这类比较折叠为 `false`，而两者在内存中的地址又确实相同；如果标准要求结果为 `true`，这就成了编译器的 bug。把它定为未指定，等于承认在优化器看来，地址和指向哪个对象是两回事。

与此配套，[[basic.compound#3]] 注 2 规定尾后指针不被视为指向恰好位于该地址的无关对象，即使比较相等，也不能通过它访问 `b`。

在常量求值中，这类比较同样不是常量：

```cpp title="eq-past-end-const.cpp" error
int a, b;
constexpr bool r = &a + 1 == &b;   // error: 尾后指针与另一完整对象比较，结果未指定
```

Clang 的诊断说明是 "comparison against pointer '&a + 1' that points past the end of a complete object has unspecified value"。

### 函数指针与字符串字面量

¶4.2 规定指向同一函数的指针相等；反过来，指向不同函数的指针必须不等。这条规则与链接器的相同代码折叠（identical code folding，ICF）有冲突：MSVC 的 `/OPT:ICF`、lld/gold 的 `--icf=all` 会把机器码相同的不同函数合并为一个，导致 `&f == &g` 为真，这是不符合标准的激进优化。lld/gold 的 `--icf=safe` 只合并地址从未被取过的函数，从而保持一致性。

字符串字面量则相反：它们是潜在非唯一对象（potentially non-unique object，[[intro.object]]），两个相同（或一个是另一个后缀）的字面量是否共享存储是未指定的，因此 `+"foo" == +"foo"` 的结果未指定；在常量求值中，当两个指针可能指向同一合并对象的同一偏移处时，比较不是常量（[[expr.const.core]] ¶2.29）。C++26 起 `std::initializer_list` 的底层数组也是潜在非唯一对象，比较不同列表的 `begin()` 结果同样未指定（[[diff.cpp23.dcl.dcl]]）。

```cpp run title="eq-string-literal.cpp" ok
constexpr const char* f() { return "foo"; }

constexpr const char* p = f();
static_assert(p == p);                             // OK: 同一个指针值
static_assert(!("foo" == "bar" + 0));              // OK: 内容不同，不可能合并到同一偏移
// static_assert(+"foo" == "foo");                 // error: 非常量（是否合并未指定）

int main() {}
```

### 成员指针相等（¶5）

¶5 至少一个操作数是成员指针时，先做成员指针转换（[[conv.mem]]）、函数指针转换、限定转换，得到复合指针类型。然后：

- ¶5.1 两者都是空成员指针值：相等；
- ¶5.2 只有一个是空成员指针值：不等；
- ¶5.3 任一指向虚成员函数：结果未指定；
- ¶5.4 一个指向类 `C1` 的成员、另一个指向不同类 `C2` 的成员，且二者都不是对方的基类：结果未指定；
- ¶5.5 都指向同一联合体的（可能不同的）成员：相等；
- ¶5.6 否则：若用一个假想的关联类类型对象做间接访问时，两者会访问同一最终派生对象的同一成员或同一子对象，则相等；否则不等。

¶5.3 的理由来自实现。Itanium ABI 中虚成员函数指针存的是虚表偏移加 1，而同一虚函数在不同类中的虚表偏移可能不同，所以两个语义上相同的虚函数指针，表示可能不同，反之亦然。要求精确的相等语义会让每次比较都很昂贵。

¶5.4 对应标准的例 1：`B::x` 与 `C::x` 被强制转换成 `int A::*` 后比较，二者来自互不为基类的 `B`、`C`，结果未指定。

¶5.6 用假想对象作为判据，处理的是菱形继承中的歧义。标准的例 2 改编如下：

```cpp run title="eq-mptr-diamond.cpp" ok
struct B { int f(); };
struct L : B {};
struct R : B {};
struct D : L, R {};

int (B::*pb)() = &B::f;
int (L::*pl)() = pb;
int (R::*pr)() = pb;
int (D::*pdl)() = pl;    // 经由 L 到达 B
int (D::*pdr)() = pr;    // 经由 R 到达 B

bool x = (pdl == pdr);   // false：在 D 对象上调用时，this 分别调整到不同的 B 子对象
bool y = (pb == pl);     // true：指向同一成员，经 pb 转换而来

int B::f() { return 0; }
int main() { return (!x && y) ? 0 : 1; }
```

`pdl` 与 `pdr` 都指向 `B::f`，但在一个假想的 `D` 对象上用它们调用时，`this` 会分别指向 `D` 中两个不同的 `B` 子对象，所以它们不等。**成员指针不仅记录是哪个成员，还记录通过哪条继承路径到达。**

```cpp title="eq-mptr-virtual-const.cpp" error
struct B { virtual int v(); };
constexpr bool r = &B::v == &B::v;   // error: 虚成员函数指针的比较结果未指定，非常量
```

成员指针与 `nullptr` 的比较总是合法的（空指针常量可以转换为空成员指针值，¶5.1/5.2）。

### `nullptr_t`（¶6）

¶6 两个 `std::nullptr_t` 类型的操作数，或一个 `nullptr_t` 与一个空指针常量，比较相等。但它们不能做关系比较（[[expr.rel#2]] 不接受 `nullptr_t`）。

### `std::meta::info` {{c++26}}（¶7）

¶7 C++26 的静态反射（[[P2996R13]]）引入了标量类型 `std::meta::info`（[[basic.fundamental]]），它的值是反射。两个反射值相等，当且仅当它们：

- ¶7.1 都是空反射值；
- ¶7.2 表示模板实参等价（[[temp.type]]）的值；
- ¶7.3 表示同一个对象；
- ¶7.4 表示同一个实体；
- ¶7.5 表示同一个注解（[[dcl.attr.annotation]]）；
- ¶7.6 表示同一个直接基类关系；
- ¶7.7 表示相等的数据成员描述（[[class.mem.general]]）。

```cpp title="eq-meta-info.cpp"
#include <meta>

struct S { int m; };
using Alias = S;

static_assert(^^S != ^^Alias);                       // ^^Alias 反射的是类型别名本身（[expr.reflect] ¶5.6）
static_assert(std::meta::dealias(^^Alias) == ^^S);   // 去掉别名后表示同一个类型
static_assert(^^S::m != ^^S);
static_assert(std::meta::info{} == std::meta::info{});   // 两个空反射值（¶7.1）
```

第一行说明 `info` 的相等并不只是值相等或类型等价那么简单：类型别名是一个独立的实体（[[expr.reflect]] ¶5.6），反射它得到的值与反射其目标类型得到的值不同，要判断是不是同一个类型，得先 `dealias`。（截至写作时，本站使用的 Clang 23 尚未提供 `<meta>`，此例未经本地编译验证。）

### 结果与算术比较（¶8–¶9）

¶8 两操作数相等则 `==` 为 `true`、`!=` 为 `false`；不等则相反。

¶9 算术或枚举类型的操作数做常用算术转换，然后按数学关系给出结果。浮点的两个经典特例：`NaN == NaN` 为 `false`，`-0.0 == 0.0` 为 `true`。

## 实现视角

!!! impl
    - **指针比较**在主流平台上编译为整数比较（平坦地址空间），所以运行期结果未指定的比较实际上都给出地址顺序。但优化器可以利用这种未指定：基于来源的分析可能在编译期把 `&a + 1 == &b` 折叠为 `false`，而另一处未经优化的同一比较得到 `true`，标准允许同一程序中的结果不一致。
    - **成员指针比较**（Itanium ABI）：数据成员指针比较偏移量；成员函数指针比较 `{ptr, adj}` 两个字，但当 `ptr` 为 0（空）时忽略 `adj`。MSVC 的成员函数指针表示随继承模型而变，比较也相应复杂。
    - **诊断**：Clang 的 `-Wtautological-compare` 系列会警告数组与空指针比较恒为假、字符串字面量比较结果未指定等情况；C++26 模式下两个数组的比较是错误（`-Warray-compare-cxx26` 作为错误）。

## 陷阱

!!! pitfall "`a < b < c` 当作链式比较"
    它是 `(a < b) < c`。`==` 同理。

!!! pitfall "用 `<` 给任意指针排序"
    无关指针的 `<` 结果未指定；用 `std::less<T*>`。

!!! pitfall "以为无关指针比较是 UB"
    关系比较未指定，相等比较有定义（尾后指针与相邻对象除外）。真正是 UB 的是无关指针相减（[[expr.add#5]]）。

!!! pitfall "用 `==` 比较 C 字符串"
    C++26 中两个字面量的比较非良构；`const char*` 之间的 `==` 比较的是地址。用 `std::string_view` 或 `std::strcmp`。

!!! pitfall "以为指向同一函数的虚成员函数指针一定相等"
    ¶5.3：任一是虚成员函数指针时结果未指定。

## 思考题

!!! question "思考题 1"
    下面的断言是否成立？为什么？

    ```cpp
    struct S { int a; int b[2]; int c; };
    S s;
    bool r1 = &s.b[1] < &s.c;
    bool r2 = &s.b[2] == &s.c;
    ```

<details markdown="1">
<summary>答案</summary>

- `r1`：`s.b[1]` 是成员 `b` 的子对象，`s.c` 是后声明的成员；¶4.2 适用于指向不同非静态数据成员或其子对象的指针，所以 `&s.b[1] < &s.c` 必须为 `true`。
- `r2`：`&s.b[2]` 是数组 `b` 的尾后指针。¶4.1（[[expr.eq]]）的未指定只适用于另一个完整对象，而 `s.c` 是子对象、不是完整对象，所以不适用 ¶4.1；按 ¶4.2，若两者表示同一地址则相等。在没有填充的典型布局中二者地址相同，结果为 `true`；但布局中是否存在填充是实现相关的，所以结果依赖于布局。
</details>

!!! question "思考题 2"
    为什么标准对 `<` 只给出偏序，却敢于对 `==` 给出几乎完全确定的答案？

<details markdown="1">
<summary>答案</summary>

`==` 只需要判断是不是同一地址，在任何内存模型下都能高效实现（分段架构也能把段和偏移规范化后比较）；而 `<` 要求一个全序，在分段架构上，不同段之间谁大没有自然的答案，强制全序会让所有指针比较都付出规范化的代价。因此标准把全序的需求交给 `std::less`（需要时才付出代价），内置 `<` 只保证同一对象内部的偏序，这足以支持数组遍历和迭代器比较。`==` 唯一保留的未指定情形（尾后指针与相邻对象）则是为了基于来源的优化，而不是为了硬件。
</details>

## 小结

| 比较 | 结果 | 依据 |
|---|---|---|
| 算术/枚举 | 常用算术转换后按数学关系（NaN 不等于任何值） | [[expr.rel#6]]、[[expr.eq#9]] |
| 同一数组内、同一对象的成员间指针的 `<` | 按下标/声明顺序 | [[expr.rel#4]] |
| 无关指针的 `<` | {{unspec}} | [[expr.rel#5]] |
| 函数指针的 `<` | {{unspec}}（不等时） | [[expr.rel#5]] 注 1 |
| 指针 `==` | 地址相同即相等 | [[expr.eq#4]] |
| 尾后指针 `==` 相邻完整对象 | {{unspec}} | [[expr.eq#4]] ¶4.1 |
| 虚成员函数指针 `==`、无关类成员指针 `==` | {{unspec}} | [[expr.eq#5]] |
| 同一联合体的成员指针 | 相等 | [[expr.eq#5]] ¶5.5 |
| 两个数组比较 | {{ill-formed}}（C++26；C++20 起弃用） | [[expr.rel#1]]、[[expr.eq#1]] |
| 指针 `<` `0`、`nullptr_t` 的 `<`、成员指针的 `<` | {{ill-formed}} | [[expr.rel#2]]、[[expr.rel#3]] |
