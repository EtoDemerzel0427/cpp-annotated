---
title: 加性运算符
summary: "+ 与 - 的操作数要求；指针算术只在同一个数组（含尾后位置与“单元素数组”）内有定义；空指针加 0；指针相减得到 ptrdiff_t；元素类型不相似时的 UB；为什么“只是算出越界指针、不解引用”也是 UB"
status: done
papers: P1839
related: basic.compound, expr.mul, expr.sub, expr.unary.op, expr.rel, expr.eq, conv.qual, conv.prom, expr.arith.conv, dcl.array, expr.const.core
tags: 指针算术, 数组, UB
updated: 2026-10-17
---

对算术类型而言，加法和减法没有什么特别之处：经过常用算术转换后相加相减，溢出规则与 [[expr.mul]] 相同。本节的重点在**指针算术**：一个指针加上一个整数何时得到有意义的指针？两个指针相减何时有定义？

C++ 的回答非常严格：**指针算术只在一个数组对象内部有定义**，可以到达尾后位置，但不能更远；不是数组元素的对象被看作只有一个元素的数组。越出这个范围，哪怕只是算出那个指针、从不解引用，也是未定义行为。`a[i]`（[[expr.sub]] 把它定义为 `*((a)+(i))`）、迭代器模型，以及指针越界检查被优化掉等现象，都以本节为依据。

读本节前需要了解指针值的四种情况（指向对象、尾后、空、无效）以及假想数组元素的约定，它们定义在 [[basic.compound#3]]。

## 操作数与转换（¶1）

¶1 `+` 和 `-` 从左往右结合，每个操作数都必须是 prvalue（所以左值先经过左值到右值转换，数组先退化为指针，[[expr.prop]] / [[conv]]）。然后：

- 两个操作数都是算术或无作用域枚举类型：进行常用算术转换（[[expr.arith.conv]]）；
- 只有一个是算术或无作用域枚举类型（另一个是指针）：对它做整数提升（[[conv.prom]]）。

对于加法，要么两边都是算术类型，要么一边是指向完整定义的对象类型的指针、另一边是整型。这直接排除了以下情形：

- `void*` 的算术（`void` 不是对象类型），GCC/Clang 作为 GNU 扩展接受，`-pedantic` 下警告；
- 函数指针的算术；
- 指向不完整类型的指针的算术（编译器不知道要跨多少字节）；
- `nullptr + 0`（`std::nullptr_t` 不是指针类型）；
- 两个指针相加（没有意义）。

```cpp title="add-operands.cpp" error
struct Incomplete;
void fn();

void f(void* pv, Incomplete* pi, int* p, int* q) {
    auto a = pv + 1;        // error: void* 不能做算术（GNU 扩展除外）
    auto b = pi + 1;        // error: 指向不完整类型
    auto c = &fn + 1;       // error: 函数指针
    auto d = p + q;         // error: 两个指针不能相加
    auto e = nullptr + 0;   // error: nullptr_t 不是指针
}
```

```cpp title="add-operands-ok.cpp" ok
enum E { two = 2 };

int f(int* p) {
    int* a = p + two;       // OK: 无作用域枚举先整数提升
    int* b = true + p;      // OK: bool 是整型（提升为 int），加法可交换
    return int(a - b);
}
```

## 减法（¶2）与结果（¶3）

¶2 减法的三种合法形式：

- ¶2.1 两边都是算术类型；
- ¶2.2 两边都是指向相似（similar，[[conv.qual]]）的完整对象类型的指针，所以 `const int*` 减 `int*` 合法，`int*` 减 `long*` 不合法；
- ¶2.3 左边是指向完整定义对象类型的指针，右边是整型（`p - 3`；而 `3 - p` 不合法）。

¶3 `+` 的结果是和，`-` 的结果是差。对算术类型就这么简单，溢出由 [[expr.pre#4]] 处理（有符号溢出 UB，无符号模 2<sup>N</sup>）。下面两段精确规定了和与差对指针意味着什么。

## 指针加减整数（¶4）

¶4 设 `P` 是指针类型的表达式，`J` 是整型表达式（值为 *j*），结果类型与 `P` 相同：

- ¶4.1 若 `P` 是空指针值且 *j* 为 0，结果是空指针值；
- ¶4.2 否则，若 `P` 指向数组对象 *x*（有 *n* 个元素）的（可能是假想的）第 *i* 个元素：`P + J` 与 `J + P` 指向第 *i + j* 个元素，前提是 0 ≤ *i + j* ≤ *n*；`P - J` 指向第 *i − j* 个元素，前提是 0 ≤ *i − j* ≤ *n*；
- ¶4.3 否则，行为未定义 {{ub}}。

两条约定（[[basic.compound#3]]，本节脚注重述）让这个规则覆盖到所有对象：

1. **尾后指针**（指向最后一个元素之后）被视为指向假想的第 *n* 号元素，所以 *i + j* 可以等于 *n*；
2. 不是数组元素的对象被视为属于一个**只有一个元素的数组**，所以 `&x + 1` 是 `x` 的尾后指针，合法；`&x + 2` 是 UB。

```cpp run title="add-bounds.cpp" ok
constexpr bool test() {
    int a[3]{};
    int* end = a + 3;      // OK: 尾后（假想元素 3）
    int* p = end - 3;      // OK: 回到元素 0
    int v = 0;
    int* q = &v + 1;       // OK: 单个对象视为 1 元素数组，q 是尾后指针
    int* n = nullptr;
    n = n + 0;             // OK: 空指针加 0 仍是空指针（¶4.1）
    return p == a && q - 1 == &v && n == nullptr && end - a == 3;
}
static_assert(test());

int main() {}
```

越界一步就进入 ¶4.3。常量求值中编译器必须诊断 UB，所以最适合在这里观察这条规则：

```cpp title="add-oob-const.cpp" error
constexpr bool f() {
    int a[3]{};
    int* p = a + 4;        // UB: 越过尾后位置
    return p != nullptr;
}
static_assert(f());        // error: 不是常量表达式（Clang："cannot refer to element 4 of array of 3 elements"）

constexpr bool g() {
    int a[3]{};
    int* p = a - 1;        // UB: 在首元素之前
    return p != nullptr;
}
static_assert(g());        // error: 不是常量表达式
```

### 为什么只是算出来也是 UB？

`p + 4` 不解引用，为什么也不行？原因有三：

1. **历史上的分段地址**：在分段内存模型中，指针由段和偏移组成，越过段末尾的算术可能回绕或触发硬件陷阱，甚至把指针载入段寄存器这一动作本身就可能出错。标准为这类实现保留了自由。
2. **地址空间边界**：数组可能紧贴地址空间末尾。标准特别保证尾后一个位置可以表示（实现必须确保数组后至少有一个可寻址的位置不回绕），再往后则不保证。
3. **优化**：编译器可以假设所有指针算术都留在对象内，从而把 `p + n < p` 这样的溢出检查判定为恒假并删除，也可以把 `p + i < p + j` 化简为 `i < j`。这类推理在循环优化（向量化、强度削减）中非常普遍。

```cpp title="add-overflow-check.cpp" ub
#include <cstddef>

bool will_overflow(const char* p, std::size_t len) {
    return p + len < p;    // UB: 若 p + len 越界则已是 UB；编译器可把整个比较折叠为 false
}
```

Clang 对上面的函数直接给出 `-Wtautological-compare` 警告（"pointer comparison always evaluates to false"），说明编译器已经按 UB 前提把它推理成了常量。正确的做法是在整数域里比较长度：`len > static_cast<std::size_t>(end - p)`。

### 注 1：子对象与相邻成员的手动寻址

¶4 的注 1 把规则说得更直白：对指向基类子对象、成员子对象或完整对象的指针加上 0 或 1 以外的值，都是 UB。经典的反例是通过一个成员的地址走到下一个成员：

```cpp run title="add-member-walk.cpp" ub
struct P { int x, y, z; };

int main() {
    P s{1, 2, 3};
    int* px = &s.x;
    int* end = px + 1;     // OK: s.x 的尾后指针（可能恰好等于 &s.y，但不"指向" s.y）
    int bad = *(px + 2);   // UB: s.x 不是数组元素，只能 +0 或 +1
    (void)end;
    return bad;
}
```

即使 `px + 1` 的地址与 `&s.y` 相同，它仍然是 `s.x` 的尾后指针，而不是指向 `s.y` 的指针。[[basic.compound#3]] 注 2 明确说明，尾后指针不被视为指向恰好位于该地址的无关对象。解引用它同样是 UB。

### 多维数组不能拉平

`int a[2][3]` 是一个有 2 个元素的数组，每个元素是 `int[3]`。`a[0][j]` 的指针算术发生在 `a[0]` 这个 3 元素数组里，所以 `a[0][3]` 是尾后，`a[0][4]` 越界，即使内存是连续的、`a[1][1]` 就在那个位置：

```cpp title="add-2d.cpp" error
constexpr int f() {
    int a[2][3]{{1, 2, 3}, {4, 5, 6}};
    int* p = &a[0][0];
    return p[4];           // UB: p 在 a[0]（3 个元素）内，p + 4 越界
}
constexpr int v = f();     // error: 不是常量表达式
```

把二维数组当成一维遍历（`for (int* p = &a[0][0]; p != &a[0][0] + 6; ++p)`）在实践中很常见，在主流编译器上通常也能得到预期结果，但按标准它是 UB。合法的写法是逐行遍历，或者把存储声明为一维数组再自己算下标。

## 指针相减（¶5）

¶5 两个指针相减得到 `std::ptrdiff_t` 类型的 prvalue（[[support.types.layout]]）：

- ¶5.1 两个都是空指针值：结果为 0；
- ¶5.2 分别指向同一个数组对象的第 *i*、*j* 个元素（含尾后/假想元素）：结果是 *i − j*；
- ¶5.3 否则 {{ub}}。

注 2 补充：即使在同一数组内，若 *i − j* 超出 `ptrdiff_t` 的可表示范围，同样是 UB（[[expr.pre]]）。这在 32 位平台上确实会发生：一个超过 2 GiB 的 `char` 数组，首尾指针相减就会溢出。这也是 `std::vector` 等容器的 `max_size()` 通常不超过 `PTRDIFF_MAX` 的原因。

```cpp title="add-sub-unrelated.cpp" error
constexpr long f() {
    int a[3]{}, b[3]{};
    return b - a;          // UB: 指向不同数组
}
constexpr long v = f();    // error: 不是常量表达式
```

!!! lawyer "三种指针运算，三种不同的严重程度"
    对指向不同完整对象的两个指针 `p`、`q`：

    - `p == q`：有定义（结果为 `false`，除尾后与相邻对象的特殊情形外，[[expr.eq#4]]）；
    - `p < q`：结果未指定（unspecified），不是 UB（[[expr.rel#5]]）；
    - `p - q`：未定义行为（¶5.3）。

    所以比较两个无关指针的大小只是得不到可移植的答案，而相减则让整个程序失去意义。需要全序时使用 `std::less<T*>`（[[comparisons.general]]）。

## 元素类型必须相似（¶6）

¶6 进行加减时，若 `P` 或 `Q` 的类型是指向 cv `T` 的指针，而 `T` 与数组元素类型不相似，行为未定义。也就是说，指针算术不仅要看指向哪个数组，还要看以什么类型移动：

```cpp run title="add-similar.cpp" ub
int main() {
    int arr[5] = {1, 2, 3, 4, 5};
    unsigned int* p = reinterpret_cast<unsigned int*>(arr + 1);
    unsigned int k = *p;    // OK: 通过对应的无符号类型读 int 是允许的（[basic.lval]），k == 2
    unsigned int* q = p + 1;// UB: p 指向的是 int 数组元素，unsigned int 与 int 不相似
    return int(k + *q);
}
```

第一处读取是合法的，因为 [[basic.lval]] 的类型访问规则允许通过有符号/无符号对应类型访问对象。但指针算术的规则更严：`unsigned int` 与 `int` 不是相似类型（相似只忽略各层 cv），于是 `p + 1` 是 UB。**别名规则允许读取，并不意味着允许做指针算术。**

!!! warning "已知的缺陷：用 `unsigned char*` 遍历对象表示"
    严格按 ¶4 和 ¶6，`reinterpret_cast<unsigned char*>(&obj) + k`（*k* > 1）是 UB：这个指针并不指向一个 `unsigned char` 数组的元素，它指向的是 `obj` 本身，而 `unsigned char` 与 `obj` 的类型不相似。但 `memcpy` 式的逐字节访问是大量代码（包括标准库实现）的基础，所有编译器都支持它。这是公认的标准措辞缺陷，[[P1839]]（Accessing object representations）试图为对象表示提供真正的 `unsigned char` 数组语义。在它被采纳之前，这类代码按标准是 UB，但在实践中得到普遍支持。

## 实现视角

!!! impl
    - **代码生成**：`p + j` 编译为 `p + j * sizeof(T)`，一条 `lea` 或 `add`；`p - q` 编译为字节差再除以 `sizeof(T)`。由于 ¶5 保证差值一定是 `sizeof(T)` 的整数倍，编译器用精确除法（乘以 `sizeof(T)` 的模逆元）代替真正的除法，这又是一处利用 UB 前提的优化。
    - **UBSan** 的 `-fsanitize=pointer-overflow` 只检查指针算术在地址空间中回绕的情形，不检查越出数组；ASan 检查越界访问，而不检查越界指针的形成。也就是说，`a + 4` 这种 UB 两个 sanitizer 都发现不了，常量求值反而是最严格的检查器。
    - **`-Warray-bounds`**（GCC/Clang）能在编译期发现部分常量下标越界。
    - **GNU 扩展**：`void*` 与函数指针的算术被当作 `char*` 处理（`sizeof(void) == 1`），`-Wpointer-arith` / `-pedantic` 会警告。

## 历史与演进

!!! history
    - 尾后一个位置的保证从 C89/C++98 起就有，它让 `for (p = a; p != a + n; ++p)` 这一惯用法合法，也是 STL 半开区间迭代器模型的基础。
    - 空指针加/减 0 得到空指针、两个空指针相减得 0，在 C++ 中是明确规定的；C 语言直到 C23 都把 `NULL + 0` 留作 UB，这是 C 与 C++ 在指针算术上少见的分歧。
    - “（可能是假想的）数组元素”的说法以及 ¶6 的相似类型要求，是后来对措辞的精确化。早期标准只说“指向数组元素”，对尾后指针和非数组对象的处理散落在注释里。今天的版本把它们统一到 [[basic.compound#3]] 的约定中。
    - C++17 起 `std::launder`（[[ptr.launder]]）与 C++20 的隐式对象创建（[[intro.object]]）让 `malloc` 出来的存储可以合法地进行指针算术：分配函数会隐式创建一个适当的数组对象。

## 陷阱

!!! pitfall "以为只有解引用越界才是 UB"
    算出越界指针本身就是 UB（¶4.3）。`p + n < p` 的溢出检查会被编译器删掉。

!!! pitfall "以为相邻成员可以用指针算术访问"
    `&s.x + 1` 是 `s.x` 的尾后指针，不是指向 `s.y` 的指针；`&s.x + 2` 是 UB。

!!! pitfall "把多维数组当一维数组遍历"
    `&a[0][0] + 5`（对 `int a[2][3]`）越出了 `a[0]` 的边界，是 UB。

!!! pitfall "以为别名规则允许的类型就能做指针算术"
    读取可以通过 `unsigned`/`signed` 对应类型或 `char` 系类型进行，但指针算术要求类型与数组元素相似（¶6）。

!!! pitfall "以为不同数组的指针相减只是结果不确定"
    关系比较是 unspecified，相减是 UB。

## 思考题

!!! question "思考题 1"
    下面的循环是否有 UB？

    ```cpp
    void f(int* a, int n) {
        for (int* p = a + n - 1; p >= a; --p) { /* ... */ }
    }
    ```

<details markdown="1">
<summary>答案</summary>

有。最后一次迭代后执行 `--p`，`p` 从 `a`（元素 0）变成 `a - 1`，越出了数组的下界（不存在首前位置），这一步本身就是 UB（¶4.3），随后的 `p >= a` 比较也就无从谈起。标准只保证尾后位置，不保证首前位置。正确写法是 `for (int* p = a + n; p != a; ) { --p; /* ... */ }`，或者使用反向迭代器：`std::reverse_iterator` 内部存放的是后一个位置，解引用时先减一，正好绕开了这个问题。另外，若 `n == 0`，`a + n - 1` 就已经越界。
</details>

!!! question "思考题 2"
    `int x; int* p = &x + 1; int* q = p - 1;` 中 `q` 指向什么？`p - &x` 的值是多少？

<details markdown="1">
<summary>答案</summary>

`x` 被视为 1 元素数组的元素 0；`p` 是假想元素 1（尾后）；`q = p - 1` 指向元素 0，即 `x`，可以解引用。`p - &x` 依 ¶5.2 等于 1 − 0 = 1，类型为 `std::ptrdiff_t`。
</details>

## 小结

| 运算 | 合法范围 | 越界后果 | 段落 |
|---|---|---|---|
| `p + j` / `p - j` | 结果下标在 [0, *n*] 内（*n* = 尾后） | {{ub}}（即使不解引用） | ¶4 |
| 空指针 ± 0 | 结果为空指针 | — | ¶4.1 |
| 非数组对象 | 视为 1 元素数组：只能 +0 / +1 | {{ub}} | ¶4 注 1 |
| `p - q` | 同一数组内（含尾后），结果 `ptrdiff_t` | {{ub}} | ¶5 |
| 两个空指针相减 | 0 | — | ¶5.1 |
| 指针类型与元素类型不相似 | — | {{ub}} | ¶6 |
| `void*`、函数指针、不完整类型 | — | {{ill-formed}} | ¶1、¶2 |
