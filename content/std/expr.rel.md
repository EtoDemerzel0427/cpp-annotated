---
title: 关系运算符与相等性运算符
summary: < > <= >= 和 == != 接受哪些操作数；指针的 < 只对同一数组的元素、同一对象的成员有保证，其余结果未指定；== 按地址判断，尾后指针与相邻对象例外；成员指针只能比较相等；C++26 起两个数组不能直接比较。
status: done
covers: expr.rel, expr.eq
papers: P1120R0, P2865, P1847R4, P2996R13
related: expr.spaceship, expr.arith.conv, expr.type, conv.ptr, conv.qual, conv.mem, basic.compound, expr.add, comparisons.general, defns.order.ptr, expr.const.core, intro.object
tags: 比较, 指针, 成员指针, 未指定行为
updated: 2026-10-19
---

!!! tldr
    - `a < b < c` 是 `(a < b) < c`，`a == b == c` 同理；算术操作数先做常用算术转换，所以 `-1 < 1u` 为假。
    - 指针的 `<` 只保证同一数组内按下标排序、同一对象内按成员声明顺序排序；无关指针的 `<` 结果未指定（不是 UB），需要全序时用 `std::less<T*>`。
    - 指针的 `==` 按地址判断，几乎总有确定结果。唯一的例外是一个对象的尾后指针与另一个完整对象的地址比较，结果未指定。
    - 成员指针只能用 `==`、`!=` 比较；涉及虚成员函数，或者来自两个互不为基类的类时，结果未指定。
    - C++26 起两个数组不能直接比较，`"abc" == "abc"` 也非良构；要比较地址就先用一元 `+` 让数组退化。

[[expr.rel]] 规定 `<`、`>`、`<=`、`>=`，[[expr.eq]] 规定 `==`、`!=`。对算术类型两者都很简单，需要细读的是指针和成员指针的比较。

## 关系运算符 [expr.rel]

### 从左往右结合（¶1）

```cpp run title="rel-chain.cpp" ok flags="-std=c++2c -Wno-error=parentheses"
int main() {
    int a = 5, b = 3, c = 2;
    bool x = a < b < c;    // (5 < 3) < 2，即 false < 2，即 0 < 2
    return x ? 0 : 1;      // x 为 true，尽管 5 < 3 < 2 在数学上为假
}
```

¶1 关系运算符从左往右结合。标准的例 1 专门提醒：`a<b<c` 的意思是 `(a<b)<c`，不是 `(a<b)&&(b<c)`。

按标准这段程序是良构的。但本机 Clang 23 默认把它当作错误："chained comparison 'X < Y < Z' does not behave the same as a mathematical expression [-Wparentheses]"，要加 `-Wno-error=parentheses` 才降为警告，上面的 godbolt 按钮已经带上了这个选项。这是编译器出于实用考虑拒绝良构代码的一个例子；确实需要这种写法时，写成 `(a < b) < c` 即可。

### 允许哪些操作数（¶1–¶3）

```cpp title="rel-operands-bad.cpp" error
struct S { int m; };
enum E1 { e1 };
enum E2 { e2 };

void f(int* p, long* q, int S::* pm) {
    bool a = p < q;              // error: int* 与 long* 没有复合指针类型
    bool b = p < 0;              // error: 指针不能与整数比较大小，0 也不行
    bool c = nullptr < nullptr;  // error: nullptr_t 不是指针类型
    bool d = pm < pm;            // error: 成员指针不能比较大小
    bool e = e1 < e2;            // error: 两个不同的枚举类型（C++26 起）
    bool g = e1 < 1.5;           // error: 枚举与浮点（C++26 起）
}
```

¶1 操作数先做左值到右值转换和函数到指针转换。数组到指针转换只在另一个操作数是指针时才做，所以两个数组无法比较，见下文。

¶2 转换后的操作数必须是算术、枚举或指针类型，结果类型是 `bool`。`std::nullptr_t`、成员指针、没有重载比较的类类型都不能用关系运算符比较。

¶3 算术和枚举操作数做常用算术转换（[[expr.arith.conv]]）。两个都是指针时，做指针转换（[[conv.ptr]]）、函数指针转换（[[conv.fctptr]]）和限定转换（[[conv.qual]]），把它们变成**复合指针类型**（composite pointer type，[[expr.type]]），也就是两个指针都能转换到的公共指针类型。转换后两边类型必须相同。

`int*` 和 `long*` 之间没有这样的公共类型，所以不能比较。早期标准允许指针与空指针常量比较大小，C++14 起去掉了这一点，因为问一个指针是否小于空指针没有意义。不同枚举之间、枚举与浮点之间的比较在 C++20 被 [[P1120R0]] 弃用，C++26 改为非良构（[[diff.cpp23.expr]]）。

常用算术转换带来的老问题依然存在：

```cpp run title="rel-signed-unsigned.cpp" ok
int main() {
    int i = -1;
    unsigned u = 1;
    bool r = i < u;    // false：i 被转换为 unsigned，值为 UINT_MAX
    return r ? 1 : 0;  // 返回 0
}
```

`-Wextra` 包含的 `-Wsign-compare` 会警告这一行。`<=>` 对这种比较直接非良构（[[expr.spaceship#4]]）；C++20 的 `std::cmp_less` 等函数（[[utility.intcmp]]）给出数学上正确的结果。

### 指针的偏序（¶4）

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
    return &arr[1] < &arr[3]          // ¶4.1：同一数组，下标大者更大
        && &arr[3] < arr + 4          // 尾后指针当作假想元素 4
        && &s.a < &s.b                // ¶4.2：后声明的成员更大
        && &s.a < &s.in.y             // ¶4.2：对成员的子对象递归适用
        && &s.in.x < &s.in.y;
}
static_assert(test());

int main() {}
```

¶4 不等的对象指针之间的比较结果，由一个满足以下规则的**偏序**决定：

- ¶4.1 指向同一数组的不同元素（或元素的子对象），下标较大者必须比较为更大。
- ¶4.2 指向同一对象的不同非静态数据成员（或它们的子对象，递归地），后声明的成员必须比较为更大。前提是两个成员都不是大小为零的子对象，而且这个类不是联合体。
- ¶4.3 其他情况，不要求任何一方更大。

脚注 59 沿用 [[expr.add]] 的约定：不是数组元素的对象当作 1 元素数组，尾后指针当作假想的第 *n* 号元素。所以 `p < a + n` 对数组 `a` 内的 `p` 总有意义，`for (p = a; p < a + n; ++p)` 才是合法的。

¶4.2 的两个例外都有原因。大小为零的子对象，例如标了 `[[no_unique_address]]` 的空成员（[[intro.object]]），可能与其他成员共享地址。联合体的所有成员地址相同（[[class.union]]），谈不上先后。

!!! history "成员顺序与访问控制"
    C++11 到 C++20 中，第 4.2 项还要求两个成员的访问控制相同，因为当时允许实现重新排列不同访问区段（`public:`、`private:`）的成员。C++23 的 [[P1847R4]] 删除了这项许可，实际上也没有实现利用过它，这里的条件随之去掉。

### 其余情况结果未指定（¶5–¶6）

¶5 把偏序翻译成四个运算符的结果。如果 `p` 和 `q` 相等（按 [[expr.eq]]），`<=` 和 `>=` 为真，`<` 和 `>` 为假。否则，如果偏序规定 `p` 大于 `q`，四个运算符给出相应的结果。**再否则，每个运算符的结果都是未指定的。**

注 1 补充两点：不等的函数指针做关系比较，结果未指定，因为函数既不是数组元素也不是成员；`void*` 可以指向对象，所以通过 `void*` 比较同一数组的元素同样适用第 4 段。

未指定不等于 UB。比较两个无关对象的地址，程序仍然有意义，只是得不到可移植的答案。但在常量求值中，结果未指定的比较会使表达式不再是常量表达式（[[expr.const.core]] ¶2.28）：

```cpp title="rel-unrelated-const.cpp" error
int x, y;
bool rt = &x < &y;                     // OK: 运行期，结果未指定
constexpr bool ct = &x < &y;           // error: 结果未指定，不是常量表达式
```

¶6 算术和枚举操作数，关系成立就是 `true`，否则是 `false`。任何涉及 NaN 的关系都不成立，所以 `NaN < 1` 和 `NaN >= 1` 都是 `false`。

### `std::less` 的全序

既然 `<` 对无关指针的结果未指定，`std::set<T*>` 怎么工作？答案在库里：`std::less<T*>` 等函数对象对指针使用一个实现定义的**严格全序**（[[comparisons.general#2]]、[[defns.order.ptr]]），它与内置运算符的偏序一致。在平坦地址空间上，实现就是直接比较地址。

```cpp run title="rel-std-less.cpp" ok
#include <functional>
#include <set>

int main() {
    int x = 0, y = 0;
    std::less<int*> lt;
    bool a = lt(&x, &y), b = lt(&y, &x);
    std::set<int*> s{&x, &y};       // 依赖 std::less<int*> 的全序
    return (a != b && s.size() == 2) ? 0 : 1;   // a、b 恰好一个为真
}
```

所以泛型代码比较指针大小时，应当用 `std::less` 或 `std::ranges::less`，而不是 `<`。

### 两个数组不能比较 {{removed:C++26}}

```cpp title="rel-array-compare.cpp" error
int a1[3], a2[3];

bool e1 = a1 == a2;          // error: C++26 起非良构
bool e2 = a1 < a2;           // error: 同上
bool e3 = "abc" == "abc";    // error: 两个字符串字面量也是两个数组
```

C++23 及以前，两个数组比较时都会退化为指针，比较的是地址而不是内容，这几乎从来不是写代码的人想要的。C++20 由 [[P1120R0]] 弃用了这种比较，C++26 由 [[P2865]] 移除：只有另一个操作数是指针（对 `==`、`!=` 还包括空指针常量）时才做数组到指针转换。

确实要比较地址时，用一元 `+` 让数组先退化：

```cpp run title="rel-array-compare-ok.cpp" ok
int a1[3], a2[3];

bool p1 = a1 == +a2;         // OK: 比较地址，结果为 false
bool p2 = +a1 < +a2;         // OK: 比较地址，结果未指定
int* p = a1;
bool p3 = p == a1;           // OK: 一边是指针，数组退化
bool p4 = a1 == nullptr;     // OK: 对 == 而言空指针常量也会触发退化，恒为 false

int main() { return (p3 && !p1) ? 0 : 1; }
```

`"abc" == "abc"` 在 C++26 中非良构是件好事：它从来不比较内容，而两个相同的字面量是否是同一个对象本身就是未指定的（见下文）。比较字符串内容用 `std::string_view` 或 `std::strcmp`。

## 相等性运算符 [expr.eq]

### 允许哪些操作数（¶1–¶3）

¶1 `==` 和 `!=` 也从左往右结合，所以 `a == b == c` 同样是陷阱。操作数先做左值到右值和函数到指针转换；一个操作数是指针或空指针常量时，另一个做数组到指针转换。比关系运算符多了空指针常量这一项，所以 `arr == nullptr` 合法，只是恒为 `false`，Clang 会警告。

¶2 转换后的操作数必须是标量类型（[[basic.types.general]]）：算术、枚举、指针、成员指针、`std::nullptr_t`，以及 C++26 的 `std::meta::info`。结果是 `bool`。下面每种情形都要求转换后两边类型相同。

¶3 任意两个指针值或两个成员指针值，要么相等，要么不等，不存在无法比较的情况。注 1 补充，只要两者都不是无效指针值，重复比较的结果一致。**无效指针值**（invalid pointer value）是指所指存储已经释放的指针，例如 `delete` 之后的指针；比较它的行为由实现定义（[[basic.compound#6]]）。

### 指针相等（¶4）

```cpp run title="eq-same-address.cpp" ok
struct Empty {};
struct S { int a; double b; };
struct D : Empty { int x; };

constexpr bool test() {
    S s{};
    D d{};
    return static_cast<void*>(&s) == static_cast<void*>(&s.a)   // 对象与首成员同址
        && static_cast<void*>(&d) == static_cast<void*>(static_cast<Empty*>(&d));  // 空基类子对象
}
static_assert(test());

int main() {}
```

¶4 至少一个操作数是指针时，两边先转换到复合指针类型，然后：

- ¶4.1 一个指针表示某个完整对象的地址，另一个表示另一个完整对象的尾后地址，结果未指定。
- ¶4.2 否则，两个都是空指针、指向同一个函数，或者表示同一个地址，就相等。
- ¶4.3 否则不等。

¶4.2 的判据是表示同一个地址，而不是指向同一个对象。所以上例中指向不同对象、但地址相同的指针比较相等。

### 尾后指针与相邻对象（¶4.1）

```cpp title="eq-past-end.cpp" unspecified
#include <cstdio>

int main() {
    int a = 0, b = 0;
    int* p = &a + 1;     // a 的尾后指针
    int* q = &b;
    // 如果 b 恰好紧跟在 a 之后，p 和 q 表示同一个地址
    std::printf("%d\n", p == q);   // 未指定：可能是 0，也可能是 1
}
```

为什么偏偏这种比较是未指定的？编译器做别名分析时依赖指针的**来源**（provenance）：`p` 由 `&a` 算出，所以它不可能指向 `b`。GCC 等编译器确实会据此把这类比较在编译期折叠为 `false`，而运行时两者的地址又可能确实相同。如果标准要求地址相同就相等，这种优化就成了编译器的 bug。规定为未指定，等于承认地址和来源是两回事。

与此配套，[[basic.compound#3]] 注 2 规定尾后指针不算指向恰好位于该地址的无关对象。即使 `p == q` 为真，也不能通过 `p` 访问 `b`。

常量求值中，这种比较同样不是常量：

```cpp title="eq-past-end-const.cpp" error
int a, b;
constexpr bool r = &a + 1 == &b;   // error: 结果未指定
```

Clang 的说明是 "comparison against pointer '&a + 1' that points past the end of a complete object has unspecified value"。

### 函数指针与字符串字面量

¶4.2 规定指向同一个函数的指针相等，反过来，指向不同函数的指针必须不等。链接器的相同代码折叠（identical code folding，ICF）会与此冲突：MSVC 的 `/OPT:ICF`、lld 和 gold 的 `--icf=all` 会把机器码相同的不同函数合并为一个，使 `&f == &g` 为真，这不符合标准。`--icf=safe` 只合并从未被取地址的函数，不会破坏这条规则。

字符串字面量则是**潜在非唯一对象**（potentially non-unique object，[[intro.object]]）：两个相同的字面量，或者一个是另一个的后缀，是否共享存储是未指定的。所以 `+"foo" == +"foo"` 的结果未指定；在常量求值中，两个指针可能指向同一合并对象的同一偏移时，比较不是常量（[[expr.const.core]] ¶2.29）。C++26 起 `std::initializer_list` 的底层数组也是潜在非唯一对象（[[diff.cpp23.dcl.dcl]]）。

```cpp run title="eq-string-literal.cpp" ok
constexpr const char* p = "foo";
static_assert(p == p);                 // OK: 同一个指针值
static_assert(!("foo" == +"bar"));     // OK: 内容不同，不可能合并到同一处
// static_assert(+"foo" == "foo");     // error: 是否合并未指定，不是常量

int main() {}
```

### 成员指针相等（¶5）

¶5 至少一个操作数是成员指针时，两边先做成员指针转换（[[conv.mem]]）、函数指针转换和限定转换，得到复合指针类型。然后：

- ¶5.1 两个都是空成员指针，相等。
- ¶5.2 只有一个是空成员指针，不等。
- ¶5.3 任一个指向虚成员函数，结果未指定。
- ¶5.4 一个指向类 `C1` 的成员，另一个指向另一个类 `C2` 的成员，而两者互不为基类，结果未指定。
- ¶5.5 两个都指向同一个联合体的成员（可以是不同成员），相等。
- ¶5.6 否则，设想用一个关联类类型的对象做间接访问：如果两者会访问同一个最终派生对象的同一个成员或同一个子对象，就相等，否则不等。

¶5.3 的原因在实现。Itanium ABI 中，虚成员函数指针存的是虚表偏移加 1，同一个虚函数在不同类的虚表里偏移可能不同。要求精确的相等语义，会让每次比较都很昂贵。

```cpp title="eq-mptr-virtual-const.cpp" error
struct B { virtual int v(); };
constexpr bool r = &B::v == &B::v;   // error: 结果未指定，不是常量
```

¶5.4 对应标准的例 1：`B::x` 和 `C::x` 被强制转换成 `int A::*` 之后比较，`B`、`C` 互不为基类，结果未指定。

¶5.6 用设想的对象做判据，是为了处理菱形继承。标准的例 2：

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

bool x = (pdl == pdr);   // false
bool y = (pb == pl);     // true

int B::f() { return 0; }
int main() { return (!x && y) ? 0 : 1; }
```

`pdl` 和 `pdr` 都指向 `B::f`，但在一个 `D` 对象上调用时，`this` 会分别调整到 `D` 里两个不同的 `B` 子对象，所以它们不等。成员指针不仅记录是哪个成员，还记录经由哪条继承路径到达。

成员指针与 `nullptr` 比较总是合法的，空指针常量可以转换为空成员指针。

### `nullptr_t`（¶6）

¶6 两个 `std::nullptr_t` 操作数，或者一个 `std::nullptr_t` 和一个空指针常量，比较相等。它们不能做关系比较。

### `std::meta::info` {{c++26}}（¶7）

C++26 的静态反射（[[P2996R13]]）引入了标量类型 `std::meta::info`（[[basic.fundamental]]），它的值叫反射，表示一个类型、变量、函数等程序实体。

¶7 两个反射相等，当且仅当它们都是空反射（¶7.1），或者表示模板实参等价（[[temp.type]]）的值（¶7.2）、同一个对象（¶7.3）、同一个实体（¶7.4）、同一个注解（¶7.5，[[dcl.attr.annotation]]）、同一个直接基类关系（¶7.6），或者相等的数据成员描述（¶7.7，[[class.mem.general]]）。

```cpp title="eq-meta-info.cpp"
#include <meta>

struct S { int m; };
using Alias = S;

static_assert(^^S != ^^Alias);                       // ^^Alias 反射的是别名本身
static_assert(std::meta::dealias(^^Alias) == ^^S);   // 去掉别名后是同一个类型
static_assert(std::meta::info{} == std::meta::info{});   // 两个空反射（¶7.1）
```

类型别名是一个独立的实体（[[expr.reflect]] ¶5.6），反射它得到的值与反射目标类型得到的值不同；要判断是不是同一个类型，先 `dealias`。本机 Clang 23 还没有提供 `<meta>`，这个例子没有经过编译验证。

### 结果（¶8–¶9）

¶8 相等时 `==` 为 `true`、`!=` 为 `false`，不等时相反。

¶9 算术和枚举操作数先做常用算术转换，再按数学关系给出结果。浮点有两个特例：`NaN == NaN` 为 `false`，`-0.0 == 0.0` 为 `true`。

## 实现视角

!!! impl
    - 在主流平台上，指针比较编译为整数比较，运行期结果未指定的比较实际上都给出地址顺序。但优化器可以利用这种未指定：基于来源的分析可能在编译期把 `&a + 1 == &b` 折叠为 `false`，而另一处没有被优化的同一比较得到 `true`。
    - Itanium ABI 中，数据成员指针比较偏移量；成员函数指针比较 `{ptr, adj}` 两个字，`ptr` 为 0（空）时忽略 `adj`。MSVC 的成员函数指针表示随继承模型而变，比较也相应复杂。
    - Clang 的 `-Wtautological-compare` 系列会警告数组与空指针比较恒为假、字符串字面量比较结果未指定等情况；`-std=c++2c` 下两个数组的比较报错（`-Warray-compare-cxx26`）。

## 常见误解

!!! pitfall "用 `<` 给任意指针排序"
    无关指针的 `<` 结果未指定，用 `std::less<T*>`。

!!! pitfall "无关指针的比较是 UB"
    关系比较的结果未指定，相等比较有定义（尾后指针与相邻对象除外）。真正是 UB 的是无关指针相减（[[expr.add#5]]）。

!!! pitfall "用 `==` 比较 C 字符串"
    两个字面量直接比较在 C++26 中非良构；`const char*` 之间的 `==` 比较的是地址。

## 思考题

!!! question "思考题 1"
    下面的 `r1`、`r2` 是什么？

    ```cpp
    struct S { int a; int b[2]; int c; };
    S s;
    bool r1 = &s.b[1] < &s.c;
    bool r2 = &s.b[2] == &s.c;
    ```

<details markdown="1">
<summary>答案</summary>

`r1`：`s.b[1]` 是成员 `b` 的子对象，`s.c` 是后声明的成员。[[expr.rel#4]] 的第 4.2 项对成员的子对象递归适用，所以 `r1` 必须为 `true`。

`r2`：`&s.b[2]` 是数组 `b` 的尾后指针。[[expr.eq#4]] 的第 4.1 项只管另一个完整对象，而 `s.c` 是子对象，所以不适用。按第 4.2 项，两者表示同一个地址就相等。典型布局中 `b` 和 `c` 之间没有填充，结果为 `true`；但是否有填充由实现决定，所以结果依赖布局。
</details>

!!! question "思考题 2"
    为什么标准对 `<` 只给出偏序，却对 `==` 给出几乎完全确定的答案？

<details markdown="1">
<summary>答案</summary>

`==` 只需判断是不是同一个地址，在任何内存模型下都能高效实现，分段架构也可以把段和偏移规范化后比较。`<` 则需要一个全序，而在分段架构上不同段之间谁大没有自然的答案，强制全序会让所有指针比较都付出规范化的代价。

所以标准把全序交给 `std::less`，需要时才付代价；内置 `<` 只保证同一对象内部的偏序，这足以支持数组遍历和迭代器比较。`==` 唯一保留的未指定情形，即尾后指针与相邻对象，是为了基于来源的优化，而不是为了硬件。
</details>

## 小结

| 比较 | 结果 | 依据 |
|---|---|---|
| 算术、枚举 | 常用算术转换后按数学关系；NaN 与任何值都不相等 | [[expr.rel#6]]、[[expr.eq#9]] |
| 同一数组内、同一对象的成员之间的指针 `<` | 按下标、按声明顺序 | [[expr.rel#4]] |
| 无关指针的 `<`、不等函数指针的 `<` | {{unspec}} | [[expr.rel#5]] |
| 指针 `==` | 地址相同即相等 | [[expr.eq#4]] |
| 尾后指针 `==` 另一个完整对象 | {{unspec}} | [[expr.eq#4]] ¶4.1 |
| 虚成员函数指针、无关类的成员指针 `==` | {{unspec}} | [[expr.eq#5]] |
| 同一联合体的成员指针 `==` | 相等 | [[expr.eq#5]] ¶5.5 |
| 两个数组比较 | {{ill-formed}}（C++26；C++20 起弃用） | [[expr.rel#1]]、[[expr.eq#1]] |
| 指针 `<` `0`、`nullptr_t` 或成员指针的 `<` | {{ill-formed}} | [[expr.rel#2]]、[[expr.rel#3]] |
