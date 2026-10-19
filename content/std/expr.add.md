---
title: 加性运算符
summary: 二元 + 和 - 接受哪些操作数；指针加减整数只在同一个数组内（含尾后位置）有定义，算出越界指针本身就是未定义行为；两个指针相减得到 ptrdiff_t。
status: done
papers: P1839
related: basic.compound, expr.mul, expr.sub, expr.unary.op, expr.rel, expr.eq, conv.qual, conv.prom, expr.arith.conv, dcl.array, expr.const.core
tags: 指针算术, 数组, UB
updated: 2026-10-19
---

!!! tldr
    - 算术操作数的 `+`、`-` 先做常用算术转换，溢出规则与乘除相同：有符号溢出是未定义行为，无符号按模回绕。
    - 指针加减整数，结果必须落在同一个数组的元素 0 到尾后位置之间。只要算出范围外的指针就是未定义行为，不需要解引用。
    - 不是数组元素的对象当作只有一个元素的数组，所以 `&x + 1` 合法，`&x + 2` 是 UB；相邻成员、二维数组的相邻行都不能靠指针算术走过去。
    - 两个指针相减得到 `std::ptrdiff_t`，只有指向同一个数组时才有定义；空指针加 0、两个空指针相减都有定义。
    - 指针的类型必须与数组元素类型相似：`int` 数组不能用 `unsigned*` 做算术，即使别名规则允许用它读取。

## 算术操作数（¶1、¶3）

¶1 `+` 和 `-` 从左往右结合，操作数必须是 prvalue，左值会先经过左值到右值转换，数组先退化为指针。两个操作数都是算术类型或无作用域枚举类型时，先做常用算术转换（[[expr.arith.conv]]），把两边变成同一个类型。

¶3 `+` 的结果是和，`-` 的结果是差。结果超出范围时由 [[expr.pre#4]] 统一处理：有符号整数溢出是 {{ub}}，无符号整数按模 2<sup>N</sup> 运算，不会溢出。这些与乘法完全相同，详见 [[expr.mul]]。

本节真正需要细读的是指针算术：一个指针加上一个整数何时得到有意义的指针，两个指针相减何时有定义。`a[i]` 就是 `*((a)+(i))`（[[expr.sub]]），所以下标访问的合法性也由本节决定。

## 哪些指针可以做算术（¶1、¶2）

```cpp title="add-operands.cpp" error
struct Incomplete;
void fn();

void f(void* pv, Incomplete* pi, int* p, int* q) {
    auto a = pv + 1;        // error: void 不是对象类型
    auto b = pi + 1;        // error: 指向不完整类型
    auto c = &fn + 1;       // error: 函数指针
    auto d = p + q;         // error: 两个指针不能相加
    auto e = nullptr + 0;   // error: nullptr_t 不是指针类型
}
```

¶1 对加法，要么两边都是算术类型，要么一边是指向完整定义的对象类型的指针、另一边是整型。指针算术要按元素大小移动，所以 `void*`、函数指针、指向不完整类型的指针都不行。另一边如果是 `bool`、`char` 或无作用域枚举，先做整数提升（[[conv.prom]]）：

```cpp run title="add-operands-ok.cpp" ok
enum E { two = 2 };

int f(int* p) {
    int* a = p + two;       // OK: 枚举先提升为 int
    int* b = true + p;      // OK: bool 是整型，加法可以交换
    return int(a - b);
}

int main() {}
```

¶2 减法有三种合法形式：两边都是算术类型（¶2.1）；两边都是指针，指向相似的完整对象类型（¶2.2）；左边是指针、右边是整型（¶2.3）。**相似**（similar，[[conv.qual]]）是指去掉各层 cv 限定后类型相同，所以 `const int*` 减 `int*` 合法，`int*` 减 `long*` 不合法，`3 - p` 也不合法。

GCC 和 Clang 作为 GNU 扩展接受 `void*` 和函数指针的算术，把它们当作 `char*` 处理；加 `-pedantic` 会得到警告，加 `-pedantic-errors` 会被拒绝。

## 指针加减整数（¶4）

```cpp run title="add-bounds.cpp" ok
constexpr bool test() {
    int a[3]{};
    int* end = a + 3;      // OK: 尾后位置
    int* p = end - 3;      // OK: 回到元素 0
    int v = 0;
    int* q = &v + 1;       // OK: v 当作 1 元素数组，q 是尾后指针
    int* n = nullptr;
    n = n + 0;             // OK: 空指针加 0 仍是空指针
    return p == a && q - 1 == &v && n == nullptr;
}
static_assert(test());

int main() {}
```

¶4 设 `P` 是指针，`J` 是整型表达式，值为 *j*。结果的类型与 `P` 相同，值按以下规则确定：

- ¶4.1 `P` 是空指针且 *j* 为 0，结果是空指针。
- ¶4.2 否则，如果 `P` 指向某个有 *n* 个元素的数组 *x* 的第 *i* 个元素，那么 `P + J` 指向第 *i + j* 个元素，`P - J` 指向第 *i − j* 个元素，前提是结果下标在 0 到 *n* 之间。
- ¶4.3 其余情况都是 {{ub}}。

¶4.2 里的元素可以是假想的，这来自 [[basic.compound#3]] 的两条约定（脚注 58 重述了它们）：

1. **尾后指针**（past-the-end pointer），即指向最后一个元素之后的指针，当作指向第 *n* 号假想元素。所以结果下标可以等于 *n*，`for (p = a; p != a + n; ++p)` 才合法。
2. 不是数组元素的对象，当作属于一个只有一个元素的数组。所以 `&v + 1` 是 `v` 的尾后指针，合法；`&v + 2` 是 UB。

越界一步就落入第 4.3 项。常量求值中出现 UB 的表达式不是常量表达式，编译器必须报错，所以在这里最容易观察这条规则：

```cpp title="add-oob-const.cpp" error
constexpr bool f() {
    int a[3]{};
    int* p = a + 4;        // UB: 越过尾后位置
    return p != nullptr;
}
static_assert(f());        // error: 不是常量表达式

constexpr bool g() {
    int a[3]{};
    int* p = a - 1;        // UB: 不存在首前位置
    return p != nullptr;
}
static_assert(g());        // error: 不是常量表达式
```

Clang 对 `f` 的说明是 "cannot refer to element 4 of array of 3 elements in a constant expression"。

### 不解引用也是 UB

`a + 4` 从未被解引用，为什么也不允许？标准想照顾的有三类情况：

1. 分段内存模型中，指针由段和偏移组成。越过段末尾的算术可能回绕，把这样的值载入段寄存器本身就可能触发硬件异常。
2. 数组可能紧贴地址空间末尾。实现只需保证尾后一个位置可以表示，再往后可能回绕到地址 0 附近。
3. 编译器可以假设指针算术不越界。于是 `p + i < p + j` 可以化简为 `i < j`，循环变换也依赖这个前提。

第三点最常在实际代码中出现：

```cpp title="add-overflow-check.cpp" ub
#include <cstddef>

bool will_overflow(const char* p, std::size_t len) {
    return p + len < p;    // 若 p + len 越界，计算它就已经是 UB
}
```

既然 `p + len` 不可能越界，`p + len < p` 就恒为假。本机 Clang 23 直接给出警告 "pointer comparison always evaluates to false"，并把整个函数编译成 `return false`。正确的写法是在整数域里比较剩余长度：`len > static_cast<std::size_t>(end - p)`。

### 相邻成员不是同一个数组

¶4 的注 1 把规则说得更直接：对指向基类子对象、成员子对象或完整对象的指针，加上 0 或 1 以外的值都是 UB。

```cpp run title="add-member-walk.cpp" ub
struct P { int x, y, z; };

int main() {
    P s{1, 2, 3};
    int* px = &s.x;
    int* end = px + 1;     // OK: s.x 的尾后指针
    int bad = *(px + 2);   // UB: s.x 不是数组元素，只能 +0 或 +1
    (void)end;
    return bad;
}
```

`px + 1` 的地址可能恰好等于 `&s.y`，但它仍然是 `s.x` 的尾后指针。[[basic.compound#3]] 注 2 说明，尾后指针不算指向恰好位于该地址的无关对象，解引用它同样是 UB。

### 二维数组不能拉平

`int a[2][3]` 是一个有 2 个元素的数组，每个元素是 `int[3]`。`&a[0][0]` 指向 `a[0]` 这个 3 元素数组的元素 0，指针算术就只能在 `a[0]` 里进行：

```cpp title="add-2d.cpp" error
constexpr int f() {
    int a[2][3]{{1, 2, 3}, {4, 5, 6}};
    int* p = &a[0][0];
    return p[4];           // UB: p + 4 越出 a[0]
}
constexpr int v = f();     // error: 不是常量表达式
```

内存是连续的，`p + 4` 的地址就是 `a[1][1]`，主流编译器在运行期通常也会给出 5。但按标准它是 UB。需要按一维访问时，把存储声明为一维数组，自己计算下标。

## 指针相减（¶5）

¶5 两个指针相减，结果是 `std::ptrdiff_t` 类型的 prvalue（[[support.types.layout]]）：

- ¶5.1 两个都是空指针，结果为 0。
- ¶5.2 分别指向同一个数组的第 *i*、*j* 个元素（可以是尾后位置），结果是 *i − j*。
- ¶5.3 其余情况都是 {{ub}}。

```cpp title="add-sub-unrelated.cpp" error
constexpr long f() {
    int a[3]{}, b[3]{};
    return b - a;          // UB: 指向不同的数组
}
constexpr long v = f();    // error: 不是常量表达式
```

注 2 补充：即使在同一个数组里，*i − j* 超出 `ptrdiff_t` 的范围也是 UB。在 32 位平台上，一个超过 2 GiB 的 `char` 数组首尾相减就会这样。所以 `std::vector` 等容器的 `max_size()` 通常不超过 `PTRDIFF_MAX`。

!!! lawyer "无关指针：相等、大小、相减"
    对指向不同完整对象的两个指针 `p`、`q`：

    - `p == q` 有定义，结果为 `false`；唯一的例外是一个尾后指针和另一个对象的地址比较，结果未指定（[[expr.eq#4]]）。
    - `p < q` 的结果未指定，但不是 UB（[[expr.rel#5]]）。需要全序时用 `std::less<T*>`。
    - `p - q` 是 UB（¶5.3）。

## 元素类型必须相似（¶6）

```cpp run title="add-similar.cpp" ub
int main() {
    int arr[5] = {1, 2, 3, 4, 5};
    unsigned int* p = reinterpret_cast<unsigned int*>(arr + 1);
    unsigned int k = *p;    // OK: 可以通过对应的无符号类型读 int，k == 2
    unsigned int* q = p + 1;// UB: unsigned int 与 int 不相似
    return int(k + *q);
}
```

¶6 做加减时，如果指针的类型是“指向 cv `T` 的指针”，而 `T` 与数组元素类型不相似，行为未定义。上面是标准的例 1：[[basic.lval]] 的别名规则允许通过对应的无符号类型读取 `int`，所以第一次读取合法；但指针算术要求类型相似，`unsigned int` 和 `int` 不相似，`p + 1` 就是 UB。能读取不等于能做算术。

!!! warning "用 `unsigned char*` 遍历对象的字节"
    严格按第 4、6 段，`reinterpret_cast<unsigned char*>(&obj) + k` 对任何 *k* 都是 UB，*k* 为 1 也一样（除非 `obj` 本身就是 `unsigned char`）。这个指针指向的是 `obj` 本身，不是某个 `unsigned char` 数组的元素，而 `unsigned char` 与 `obj` 的类型不相似。

    然而逐字节访问对象表示是大量代码的基础，包括 `memcpy` 式的序列化和标准库实现，所有编译器都按程序员的意图处理它。这是公认的措辞缺陷。[[P1839]] 提议让对象表示真正成为一个 `unsigned char` 数组，截至写作时还没有并入草案。

## 实现视角

!!! impl
    - `p + j` 编译为 `p + j * sizeof(T)`，通常是一条 `lea` 或 `add`。`p - q` 编译为字节差除以 `sizeof(T)`；第 5 段保证差值是 `sizeof(T)` 的整数倍，所以编译器用乘以模逆元代替真正的除法。
    - UBSan 的 `-fsanitize=pointer-overflow` 只检查指针算术在地址空间中回绕、以及空指针加非零值；ASan 只检查越界访问。`a + 4` 这种只算出、不访问的越界，两者都发现不了，常量求值反而是最严格的检查器。
    - `-Warray-bounds` 能在编译期发现一部分常量下标越界。

## 历史与演进

!!! history
    - 尾后位置的保证从 C89 和 C++98 就有。它让半开区间 `[first, last)` 成为 STL 迭代器模型的基础。
    - C++ 一直规定空指针加减 0 得到空指针、两个空指针相减得 0。C 语言直到 C23 都把 `NULL + 0` 留作 UB，这是两者在指针算术上的一个分歧。
    - 早期标准只说指向数组元素，尾后指针和非数组对象的处理散落在注里。今天的措辞把它们统一成 [[basic.compound#3]] 的假想元素约定。
    - C++20 的隐式对象创建（[[intro.object]]）让 `malloc` 得到的存储也能合法地做指针算术：分配函数会隐式创建一个合适的数组对象。

## 常见误解

!!! pitfall "只有解引用越界指针才是 UB"
    算出越界指针本身就是 UB（¶4.3）。`p + n < p` 式的溢出检查会被编译器当作恒假删掉。

!!! pitfall "别名规则允许读取的类型，也能拿来做指针算术"
    别名规则允许通过有符号/无符号对应类型或字符类型读取，但指针算术要求类型与数组元素相似（¶6）。

!!! pitfall "不同数组的指针相减只是结果不确定"
    关系比较的结果未指定，相减是 UB。

## 思考题

!!! question "思考题 1"
    下面的循环有没有 UB？

    ```cpp
    void f(int* a, int n) {
        for (int* p = a + n - 1; p >= a; --p) { /* ... */ }
    }
    ```

<details markdown="1">
<summary>答案</summary>

有。最后一次迭代后执行 `--p`，`p` 从 `a` 变成 `a - 1`。标准只保证尾后位置，不存在首前位置，这一步本身就是 UB（¶4.3），之后的 `p >= a` 也就无从谈起。另外 `n == 0` 时 `a + n - 1` 已经越界。

正确写法是 `for (int* p = a + n; p != a; ) { --p; /* ... */ }`。`std::reverse_iterator` 也是这样做的：它内部存放后一个位置，解引用时先减一。
</details>

!!! question "思考题 2"
    `int x; int* p = &x + 1; int* q = p - 1;` 中 `q` 指向什么？`p - &x` 是多少？

<details markdown="1">
<summary>答案</summary>

`x` 当作 1 元素数组的元素 0，`p` 是假想元素 1，也就是尾后位置。`q = p - 1` 回到元素 0，指向 `x`，可以解引用。按第 5.2 项，`p - &x` 等于 1 − 0 = 1，类型是 `std::ptrdiff_t`。
</details>

## 小结

| 运算 | 有定义的范围 | 否则 | 段落 |
|---|---|---|---|
| `p + j`、`p - j` | 结果下标在 0 到 *n*（尾后）之间 | {{ub}}，不解引用也是 | ¶4 |
| 空指针 ± 0 | 结果为空指针 | | ¶4.1 |
| 非数组对象 | 当作 1 元素数组，只能 +0、+1 | {{ub}} | ¶4 注 1 |
| `p - q` | 同一数组内（含尾后），结果 `ptrdiff_t` | {{ub}} | ¶5 |
| 两个空指针相减 | 0 | | ¶5.1 |
| 指针类型与元素类型不相似 | | {{ub}} | ¶6 |
| `void*`、函数指针、不完整类型 | | {{ill-formed}} | ¶1、¶2 |
