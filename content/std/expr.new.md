---
title: new 表达式
summary: new-expression 创建动态存储期对象的全过程：被分配类型与 auto/CTAD 推导、数组边界与 bad_array_new_length、分配函数的查找与实参（大小、对齐、placement 实参）、数组开销（cookie）、分配省略与合并、初始化（默认初始化 vs 值初始化）与求值顺序、初始化抛异常时匹配的释放函数
status: draft
papers: N3664, P0035R4, P0145R3, P0784R7, P1009R2, P2747R2
related: expr.delete, basic.stc.dynamic, basic.life, intro.object, class.free, new.delete, dcl.init, expr.const.core, basic.align
tags: new, operator new, 动态内存, placement new, 对齐, 分配省略
updated: 2026-10-17
---

`new T(args)` 看起来像一次函数调用，实际上是**两件事**的组合：

1. 调用一个**分配函数**（allocation function，名为 `operator new` 或 `operator new[]`）取得原始存储；
2. 在这块存储上**初始化**一个对象。

两件事之间还夹着一大堆规则：分配函数怎么选、传什么实参、数组要不要额外开销、初始化抛异常时谁来释放内存、编译器能不能干脆不分配……[expr.new] 是标准中段落最多的表达式条款之一（32 段），本页逐段讲解。

与本节配合阅读：分配/释放函数本身的约束在 [[basic.stc.dynamic]]，标准库提供的版本在 [[new.delete]]，类专属版本在 [[class.free]]，配对的 [[expr.delete]]；对象何时开始存在见 [[intro.object]]、[[basic.life]]；初始化语义见 [[dcl.init]]。

## 被分配类型（¶1）

¶1 *new-expression* 试图创建一个由 *new-type-id* 或 *nofun-type-id* 指定类型的对象，这个类型称为**被分配类型**（[[g:allocated-type]]）。它必须是**完整对象类型**，但**不能是抽象类**或抽象类的数组。

- 注 1：引用不是对象，所以不能 `new` 一个引用。
- 注 2：类型可以带 cv 限定，此时创建的对象就是 cv 限定的：`new const int(5)` 创建一个 `const int` 对象，结果类型是 `const int*`。

文法有两种写法：

```text
::opt new placement-opt  new-type-id        new-initializer-opt     // new int[n]{...}
::opt new placement-opt  ( nofun-type-id )  new-initializer-opt     // new (int(*[10])())
```

开头的 `::` 强制只在全局作用域查找分配/释放函数（¶13、¶28）。*new-type-id* 是一种受限的 *type-id*：它不能有括号形式的声明符，但其第一维数组边界可以是任意表达式（见 ¶6）。

```cpp title="allocated-type.cpp" ok
#include <type_traits>
auto p1 = new const int(5);
static_assert(std::is_same_v<decltype(p1), const int*>);   // cv 限定被保留（注 2）
auto p2 = new int*[3];          // 3 个 int* 的数组，结果 int**
auto p3 = new (int (*[10])());  // 10 个函数指针（必须用括号形式，见 ¶4）
```

```cpp title="allocated-type-error.cpp" error
struct Abs { virtual void f() = 0; };
struct Inc;
void g(int n) {
    auto a = new int&(n);   // error: 引用不是对象
    auto b = new Abs;       // error: 抽象类
    auto c = new Abs[2];    // error: 抽象类的数组
    auto d = new Inc;       // error: 不完整类型
    auto e = new void;      // error: void 不是对象类型（不完整）
}
```

## 占位符类型的推导（¶2）

¶2 如果 *new-type-id*（或 *nofun-type-id*）的类型说明符里有占位符（`auto`、`decltype(auto)`）或类模板名（CTAD 的占位符），被分配类型按**虚构声明** `T x init;` 推导，其中 `init` 是 *new-initializer*。

```cpp title="new-auto.cpp" ok
#include <type_traits>
#include <vector>
template<class T> struct A { A(T, T) {} };

auto x = new auto('a');          // char*
static_assert(std::is_same_v<decltype(x), char*>);
auto y = new A{1, 2};            // CTAD：A<int>*
static_assert(std::is_same_v<decltype(y), A<int>*>);
auto z = new std::vector{1, 2, 3};   // std::vector<int>*
auto w = new auto{42};           // int*：按 auto x{42}; 推导，单元素花括号推导为 int
static_assert(std::is_same_v<decltype(w), int*>);
```

```cpp title="new-auto-error.cpp" error
auto a = new auto;          // error: 没有初始化器，无法推导
auto b = new auto(1, 2);    // error: auto x(1, 2); 无法推导
auto c = new auto{1, 2};    // error: auto x{1, 2}; 非良构（直接列表初始化只能有一个元素）
```

## 文法歧义（¶3–¶5）

¶3 *new-type-id* 取**尽可能长**的 *new-declarator* 序列。于是 `new int * i` 被解析为 `(new int*) i`——语法错误，而不是 `(new int) * i`。

¶4（注）括号在 *new-type-id* 中可能有出人意料的效果：`new int(*[10])()` 会被解析为 `(new int)(*[10])()`——把 `(*[10])` 当成 `int` 的初始化器，非良构。要分配复合类型（如函数指针数组），使用带括号的 `new ( nofun-type-id )` 形式。

¶5 *noptr-new-declarator* 中的属性说明符属于相应的数组类型。

```cpp title="new-parse.cpp" error
void f(int i) {
    auto a = new int * i;       // error: 解析为 (new int*) i
    auto b = new int(*[10])();  // error: 解析为 (new int)(*[10])()
}
```

## 数组边界（¶6–¶9）

### 第一维可以是运行期值，其余维必须是正常量（¶6）

¶6 *noptr-new-declarator* 中的 *constant-expression*（第二维及以后）必须是 `std::size_t` 类型的**转换后的常量表达式**（[[expr.const.const]]），且值**大于零**。第一维是普通的 *expression*，可以是运行期值，也可以是 0。

| 写法（`int n = 42;`） | 结果 |
|---|---|
| `new float[n][5]` | OK：第一维是表达式；结果类型 `float(*)[5]` |
| `new float[5][n]` | 非良构：第二维不是常量 |
| `new float[0]` | OK：分配一个**零元素数组** |
| `new float[n][0]` | 非良构：第二维必须 > 0 |

为什么只有第一维能是运行期值？因为 *new-expression* 的结果是指向**首元素**的指针（¶11），而首元素的类型 `float[5]` 必须是编译期已知的完整类型，指针运算才有意义。C++ 没有 C99 的 VLA 类型。

```cpp title="array-bounds.cpp" ok
#include <type_traits>
void f(int n) {
    auto a = new float[n][5];
    static_assert(std::is_same_v<decltype(a), float(*)[5]>);
    auto z = new float[0];      // OK：返回非空、唯一的指针，但不能解引用
    delete[] a;
    delete[] z;
}
```

```cpp title="array-bounds-error.cpp" error
void f(int n) {
    auto a = new float[5][n];   // error: 第二维不是常量表达式
}
```

（`new float[n][0]` 按 ¶6 非良构；Clang 23 只在 `-pedantic` 下给出"zero size arrays are an extension"的警告——警告也算诊断，满足"必须诊断"的要求，但默认配置下它会被接受为扩展。）

### 未知边界数组（¶7）{{c++20}}

¶7 如果类型是**未知边界数组**，*new-initializer* 不能省略；元素个数 *n* 由初始化器提供的初始元素个数确定（[[dcl.init.aggr]]、[[dcl.init.string]]）。

```cpp title="unknown-bound.cpp" ok
auto a = new int[]{1, 2, 3};      // n = 3
auto b = new char[]("hello");     // n = 6，包括 '\0'；C++20 起括号形式也可用于数组
auto c = new int[](1, 2);         // n = 2（C++20 的括号聚合初始化）
```

```cpp title="unknown-bound-error.cpp" error
auto a = new int[];               // error: 未知边界必须有初始化器
```

在 C++20 之前，`new int[]{1, 2, 3}` 是非良构的（只允许显式边界），由 [[P1009R2]] 修正，作为对 C++11 的缺陷报告。

### 无效的数组大小（¶8）

¶8 第一维表达式隐式转换为 `std::size_t`。以下情况其值**无效**：

- ¶8.1 非类类型，转换**之前**的值小于 0；
- ¶8.2 类类型，在应用第二次标准转换**之前**的值小于 0（脚注 53：若转换函数返回有符号整数，第二次标准转换会把它转成 `size_t`，负数就"消失"了——所以必须在那之前检查）；
- ¶8.3 分配对象的大小会超过实现定义的上限（例如 `n * sizeof(T)` 溢出）；
- ¶8.4 *new-initializer* 是花括号列表或括号表达式列表，而提供的初始化器个数（字符串字面量含 `'\0'`）**多于**元素个数。

值无效时：

- ¶8.5 若该表达式是潜在求值的**核心常量表达式**，程序**非良构**；
- ¶8.6 否则**不调用**分配函数，而是：
    - ¶8.6.1 若本应调用的分配函数有**不抛出**的异常规约（如 `std::nothrow` 版本），*new-expression* 的值是**空指针**；
    - ¶8.6.2 否则抛出一个能被 `std::bad_array_new_length` 类型的 handler 捕获的异常。

值为 0 时照常调用分配函数，分配一个零元素数组。

```cpp title="bad-array-new-length.cpp" run ok
#include <new>
#include <cstdio>
int main(int argc, char**) {
    int n = -argc;                             // 运行期的 -1
    try {
        int* p = new int[n];                   // ¶8.1 + ¶8.6.2
        delete[] p;
    } catch (const std::bad_array_new_length&) {
        std::puts("bad_array_new_length");
    } catch (const std::bad_alloc&) {
        std::puts("bad_alloc");                // Clang 23 实际走到这里，见下
    }
    int* q = new (std::nothrow) int[n];        // ¶8.6.1：不抛出，结果为空
    std::puts(q ? "non-null" : "null");
}
```

```cpp title="bad-array-const.cpp" error
auto a = new int[-1];          // error: ¶8.5，常量表达式且值无效
auto b = new int[2]{1, 2, 3};  // error: ¶8.4 + ¶8.5，初始化器多于元素
```

!!! warning "Clang 的偏差"
    按 ¶8.6.2，运行期负数边界应抛出 `std::bad_array_new_length`（它派生自 `std::bad_alloc`）。本地验证 Clang 23 的做法是把大小**饱和**为 `SIZE_MAX` 再照常调用 `operator new[]`，于是抛出的是普通的 `std::bad_alloc`——只捕获 `bad_array_new_length` 的代码会漏掉它。（在 AddressSanitizer 下还会直接报告"requested allocation size exceeds maximum"。）这还违反了"不调用分配函数"的要求：用户替换的 `operator new[]` 会看到一个 `SIZE_MAX` 的请求。初始化器过多的情形（¶8.4）同样如此。Itanium C++ ABI 为此提供了运行时函数 `__cxa_throw_bad_array_new_length`，GCC 使用它来实现 ¶8.6.2。

### 部分初始化的数组：假想元素检查（¶9）

¶9 若被分配类型是数组，初始化器是花括号或括号列表，而边界表达式**不是**核心常量表达式，编译器不知道列表会不会填满整个数组，于是要**检查一个假想元素**的初始化是否合法：

- ¶9.1 花括号列表：假想元素从**空初始化列表复制初始化**（`T x = {};`）；
- ¶9.2 括号列表：假想元素**值初始化**。

注 5：数组可能比初始化器多出若干元素，它们需要按此方式初始化。这条规则保证"剩余元素"的初始化在编译期就通过语义检查。

```cpp title="hypothetical-element.cpp" error
struct E { explicit E(); E(int); };
struct NoDef { NoDef(int); };
void f(int n) {
    auto a = new E[n]{1, 2};       // error: 剩余元素从 {} 复制初始化，explicit 默认构造函数不可用
    auto b = new NoDef[n](1, 2);   // error: 剩余元素需要值初始化，NoDef 没有默认构造函数
    auto c = new NoDef[2]{1, 2};   // OK：边界是常量，恰好填满，没有剩余元素
}
```

## 存储期与结果（¶10–¶11）

¶10 *new-expression* 创建的对象具有**动态存储期**（[[basic.stc.dynamic]]）。注 6：其生命周期不受创建它的作用域限制。

¶11 结果是 prvalue：

- 被分配类型是"N 个 `T` 的数组"（使用了 *noptr-new-declarator*，或 typedef 名指代数组类型）时，结果类型是 `T*`，指向**首元素**（若有）；
- 否则结果类型是"指向被分配类型的指针"，指向所创建的对象。

注 7：`new int` 和 `new int[10]` 的类型都是 `int*`；`new int[i][10]` 的类型是 `int (*)[10]`。

!!! pitfall "typedef 掩盖的数组 new"
    ```cpp
    using Buf = char[64];
    char* p = new Buf;    // 实际上是数组 new！
    delete p;             // UB：必须用 delete[]
    ```
    ¶11 明确说"或 *new-type-id* 指代数组类型"时也算数组。被分配类型是数组，就调用 `operator new[]`，就必须配 `delete[]`——与写法无关（[[expr.delete#2]] 注 1）。

## 分配函数（¶12–¶23）

### 名字与查找（¶12–¶13）

¶12 *new-expression* **可能**通过调用分配函数获得存储（"可能"是因为 ¶14 允许省略）。若初始化抛异常，它可能调用**释放函数**归还存储。名字取决于被分配类型：

| 被分配类型 | 分配函数 | 释放函数 |
|---|---|---|
| 非数组 | `operator new` | `operator delete` |
| 数组 | `operator new[]` | `operator delete[]` |

注 8：实现提供全局默认版本；程序可以**替换**它们（[[replacement.functions]]），也可以提供**类专属**版本（[[class.free]]）。分配函数集合里也包括**不分配**的函数，如 placement 形式 `operator new(size_t, void*)`（[[new.delete.placement]]）。

¶13 查找规则：

- 没有以 `::` 开头，且被分配类型是类类型 `T`（或其数组）：先在 **`T` 的作用域**中查找（[[class.member.lookup]]，包括基类）；
- 否则，或者类作用域中没找到：在**全局作用域**查找。

注意这是"**查找**"，不是"重载决议后失败再回退"：一旦类作用域里找到任何 `operator new`，全局版本就**被隐藏**了。类只声明了 placement 版本 `operator new(size_t, Arena&)` 时，`new T` 就会因为找不到 `operator new(size_t)` 而非良构——这是 [[class.free]] 中"要么全写，要么用 `using ::operator new;` 引入"的原因。

### 分配省略（¶14–¶15）{{c++14}}

¶14 实现**可以省略**对**可替换的全局分配函数**的调用。省略时，存储由实现提供，或通过**扩展另一个 *new-expression* 的分配**提供。

¶15 在**常量表达式的求值中**，对可替换分配函数的调用**总是被省略**（[[expr.const.core]]）——这是 `constexpr` 中能用 `new` 的基础。

为什么需要 ¶14？在 C++14 之前，`new`/`delete` 调用的是可被用户替换的函数，而替换函数可能有可观察的副作用（打印日志、计数），所以编译器在 as-if 规则下**不能**删除一对多余的 `new`/`delete`。[[N3664]] 明确放宽：对**可替换全局**分配函数的调用本身不再被视为必须保留的行为，即使用户替换了它，也可能根本不被调用。这样下面的函数可以优化成 `return 42;`：

```cpp title="elision.cpp" ok
int f() {
    int* p = new int(42);   // 允许省略分配：Clang -O2 下整个函数被优化为 return 42
    int r = *p;
    delete p;
    return r;
}
```

注意范围：只适用于 *new-expression* 调用的**可替换全局**分配函数。**类专属**的 `operator new`、**直接调用** `::operator new(n)` 的函数调用表达式、placement 形式都不在其列。

### 分配合并（¶16）

¶16 实现可以把 *new-expression* `e1` 的分配**扩展**，同时为 `e2` 提供存储（即把两次分配合并为一次），条件是（假设不扩展时）以下全部成立：

- ¶16.1 `e1` 的求值**先序于** `e2`；
- ¶16.2 只要 `e1` 取得了存储，`e2` 就一定会被求值；
- ¶16.3 两者调用**同一个**可替换全局分配函数；
- ¶16.4 若该分配函数会抛出，则 `e1`、`e2` 中抛出的异常都会首先被**同一个 handler** 捕获；
- ¶16.5 两者产生的指针值都是**被求值的 *delete-expression*** 的操作数；
- ¶16.6 `e2` 的求值先序于以 `e1` 结果为操作数的 *delete-expression*。

直觉：`e2` 的存储被"嵌套"在 `e1` 的生命期之内，异常行为也不受影响，合并就不可观察。标准例 5 中 `can_merge` 的三次 `nothrow` 分配可以合并（`nothrow` 版本不抛出，¶16.4 自然满足）；`cannot_merge` 中第二次分配在 `try` 块里，合并会改变"分配失败由哪个 handler 捕获"，所以不行。

¶18 合并后的分配大小**不得超过**：各被省略调用的大小之和 + 扩展调用本身的大小 + 必要的对齐填充。

### 第一个实参：请求的大小（¶17）

¶17 未扩展的分配，第一个实参（`std::size_t`）是请求的字节数：

- **不得小于**所创建对象的大小；
- **只有**当对象是数组且分配函数不是 placement 的不分配形式时，才**可以大于**——多出的部分就是**数组分配开销**（array allocation overhead），见 ¶21 中的 *x*。

对 `char`、`unsigned char`、`std::byte` 数组还有一条：*new-expression* 的结果与分配函数返回地址之差，必须是"大小不超过该数组的任何对象类型的最严格基础对齐"的整数倍。注 9 解释：这保证了"`new char[sizeof(T)]` 然后在里面放 `T`"这个惯用法的对齐正确性——即使实现在字符数组前面放了开销，也不会破坏对齐。

### 实参列表的组装与重载决议（¶19–¶21）

¶19 带 *new-placement* 的 *new-expression* 叫做 **placement new-expression**（[[g:placement-new-expression]]）。注意：标准中"placement"指的是**额外实参**的语法，并不特指 `new (ptr) T`。`new (std::nothrow) T` 也是 placement new。

¶20 对一个组装出来的函数调用做重载决议：

1. 第一个实参：请求的大小，`std::size_t`；
2. 若对象类型有 **new-extended 对齐**（[[basic.align]]，超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`），下一个实参是对齐值，类型 `std::align_val_t`；
3. 若有 *new-placement*，其中的表达式依次作为后续实参。

若**没有找到匹配的函数**，再试一次：

- ¶20.1 对齐是 new-extended 的：**去掉**对齐实参再试；
- ¶20.2 否则：在第一个实参后**加上**对齐实参再试。

这个"两次尝试"让旧代码和新代码互相兼容：只提供了 `operator new(size_t)` 的类，仍然能 `new` 一个过对齐类型（只是对齐不再被保证）；只提供对齐版本的类，也能 `new` 普通类型。

¶21（例 6）把四种情形写成了调用形式：

| 表达式 | 先尝试 | 再尝试 |
|---|---|---|
| `new T` | `operator new(sizeof(T))` | `operator new(sizeof(T), std::align_val_t(alignof(T)))` |
| `new(2,f) T` | `operator new(sizeof(T), 2, f)` | `operator new(sizeof(T), std::align_val_t(alignof(T)), 2, f)` |
| `new T[5]` | `operator new[](sizeof(T) * 5 + x)` | `operator new[](sizeof(T) * 5 + x, std::align_val_t(alignof(T)))` |
| `new(2,f) T[5]` | `operator new[](sizeof(T) * 5 + x, 2, f)` | `operator new[](sizeof(T) * 5 + x, std::align_val_t(alignof(T)), 2, f)` |

（对 new-extended 对齐的 `T`，"先尝试"与"再尝试"两列互换。）

*x* 是一个**非负的未指明值**，表示数组分配开销；*new-expression* 的结果相对于 `operator new[]` 的返回值偏移这么多。这个开销可以出现在**所有**数组 *new-expression* 中，包括调用用户 placement 分配函数的——**唯一例外**是标准库的 `operator new[](std::size_t, void*)`。开销的大小可以每次不同。

```cpp title="aligned-new.cpp" run ok
#include <cstdio>
#include <cstdlib>
#include <new>

struct alignas(64) Line { char c[64]; };   // 64 > __STDCPP_DEFAULT_NEW_ALIGNMENT__

void* operator new(std::size_t n, std::align_val_t a) {
    std::printf("operator new(%zu, align_val_t{%zu})\n", n, static_cast<std::size_t>(a));
    if (void* p = std::aligned_alloc(static_cast<std::size_t>(a), n)) return p;
    throw std::bad_alloc{};
}
void operator delete(void* p, std::align_val_t) noexcept { std::free(p); }

int main() {
    std::printf("default new alignment = %zu\n", __STDCPP_DEFAULT_NEW_ALIGNMENT__);
    Line* l = new Line;     // ¶20：第二个实参是 std::align_val_t(alignof(Line))
    delete l;               // [expr.delete] ¶9.2：优先选带 align_val_t 的释放函数
}
```

在 macOS arm64 上输出 `default new alignment = 16` 和 `operator new(64, align_val_t{64})`。

!!! history "对齐 new 之前"
    C++17 之前（[[P0035R4]] 之前），`new` 完全不考虑 `alignas`：`new Line` 只调用 `operator new(64)`，返回的存储只保证基础对齐（通常 16 字节），过对齐类型的 `new` 实际上是 UB 的温床（SIMD 类型崩溃是常见症状）。C++17 加入了 `std::align_val_t` 重载、¶20 的规则和 `__STDCPP_DEFAULT_NEW_ALIGNMENT__` 宏。

### 数组 cookie：实现视角

!!! impl "Itanium ABI 与 ARM 的数组 cookie"
    "数组分配开销" *x* 在实践中几乎只用于一件事：**cookie**——在数组前面记录元素个数，让 `delete[] p` 知道要析构多少个元素。

    - **Itanium C++ ABI**（x86-64 Linux/macOS、AArch64 Linux）：只有当元素类型有**非平凡析构函数**，或者对应的普通 `operator delete[]` 带有 `size_t` 形参（需要知道大小）时，才加 cookie。cookie 大小为 `max(sizeof(size_t), alignof(T))`，元素个数存放在**紧挨数组首元素之前**的 `size_t` 中。对 `struct NT { int x; ~NT(); }`，`new NT[5]` 在 x86-64 上请求 `5 * 4 + 8 = 28` 字节，在返回地址处写入 5，结果指针偏移 8 字节。
    - **ARM C++ ABI**（32 位 ARM；以及 Apple arm64）：cookie 固定为两个 `size_t`，依次存放**元素大小**和**元素个数**。本地 macOS arm64 验证：`new NonTrivial[5]`（`sizeof == 4`）请求 36 字节，cookie 为 16 字节，内容是 `4, 5`。
    - **平凡析构**的元素类型通常**没有** cookie：`new int[4]` 请求恰好 16 字节，结果指针等于分配函数的返回值。
    - **MSVC**：同样是为有非平凡析构函数的元素类型在数组前存放元素个数（布局细节未公开文档化）。
    - 标准库的 `operator new[](size_t, void*)` 被 ¶21 明确排除，**不会**加 cookie。但**用户定义的** placement `operator new[]` 可以有 cookie——这就是 `new (buf) T[n]` 在用户版本下可能越界写 `buf` 的原因。

    `delete[]` 和 `new[]` 必须配对的根本原因就在这里：`delete` 不会去读 cookie，传给 `operator delete` 的指针会比真正的分配地址偏 8 或 16 字节；反之 `delete[]` 一个非数组 `new` 的对象会去读一个不存在的 cookie。

```cpp title="array-cookie.cpp" run impl
#include <cstdio>
#include <cstdlib>
#include <new>

struct Trivial { int x; };
struct NonTrivial { int x; ~NonTrivial() {} };

void* last;
void* operator new[](std::size_t n) {
    std::printf("operator new[](%zu)\n", n);
    return last = std::malloc(n);
}
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t n) noexcept {
    std::printf("operator delete[](p, %zu)\n", n);
    std::free(p);
}

int main() {
    auto* a = new Trivial[4];
    std::printf("  offset = %td\n", (char*)a - (char*)last);
    delete[] a;
    auto* b = new NonTrivial[5];
    std::printf("  offset = %td\n", (char*)b - (char*)last);
    delete[] b;
}
```

在 x86-64 Linux 上的预期输出是 `operator new[](16)`、`offset = 0`、`operator new[](28)`、`offset = 8`、`operator delete[](p, 28)`；在 macOS arm64 上第二次分配是 36 字节、偏移 16。注意第一个 `delete[] a` 调用了**不带大小**的版本（平凡析构的数组，[[expr.delete#9]] ¶9.6 未指明），第二个调用了带大小的版本（¶9.5 要求）。

### 失败的约定（¶22–¶23）

¶22 注 10：除非分配函数有**不抛出**的异常规约，它通过抛出 `std::bad_alloc` 表示失败，成功时返回非空指针；`noexcept` 的分配函数用**返回空指针**表示失败。

规范部分：

- 若分配函数是**不分配形式**（[[new.delete.placement]]，即 `operator new(size_t, void*)`）而返回空——也就是说你写了 `new (nullptr) T`——**行为未定义**；
- 否则若分配函数返回空：**不做初始化**，**不调用**释放函数，*new-expression* 的值为**空**。

这就是 `new (std::nothrow) T(args)` 失败时 `T` 的构造函数根本不会被调用的依据。

¶23 注 11：返回非空时，必须指向已预留空间的存储块，并假定**适当对齐**且大小足够。数组时对象地址不一定等于块地址（因为 cookie）。

```cpp title="placement-null.cpp" ub
#include <new>
int main() {
    void* p = nullptr;
    int* q = ::new (p) int(1);   // UB: 不分配形式的 placement new 返回了空（¶22）
    (void)q;
}
```

!!! history "placement new 对空指针的检查"
    `operator new(size_t, void*)` 是 `noexcept` 的。若只有 ¶22 的一般规则，*new-expression* 就必须先检查返回值是否为空，再决定是否初始化，这让每次 `new (p) T` 都多出一次无用的空检查。后来一项核心语言 issue 的修订把"不分配形式返回空"单独定为 UB，编译器便可以省掉这个检查。

## 初始化（¶24–¶26）

### new T 与 new T()（¶24）

¶24 *new-expression* 创建的类型为 `T` 的对象按如下方式初始化：

- ¶24.1 省略 *new-initializer*：**默认初始化**（[[dcl.init]]）。注 12：若不进行任何初始化，对象具有**不确定值**；
- ¶24.2 否则：按 [[dcl.init]] 中**直接初始化**的规则解释 *new-initializer*。

这条规则产生了 C++ 中最常见的一个微妙差别：

| 写法 | 初始化方式 | `struct Pt { int x, y; }` | `int` | 有用户提供默认构造函数的类 |
|---|---|---|---|---|
| `new T` | 默认初始化 | 成员不确定 | 不确定 | 调用默认构造函数 |
| `new T()` | 值初始化（`()` 空括号） | 零初始化 | 0 | 调用默认构造函数（不先清零） |
| `new T{}` | 列表初始化 → 聚合初始化或值初始化 | 成员为 0 | 0 | 调用默认构造函数 |

```cpp title="new-init.cpp" run ok
#include <cstdio>
struct Pt { int x, y; };
int main() {
    Pt* p1 = new Pt;      // 默认初始化：x、y 具有不确定值（动态存储期，读取是 UB，见 [basic.indet]）
    Pt* p2 = new Pt();    // 值初始化：x = y = 0
    Pt* p3 = new Pt{};    // 聚合初始化（空列表）：x = y = 0
    int* i1 = new int[4];      // 4 个不确定值
    int* i2 = new int[4]();    // 4 个 0
    std::printf("%d %d %d %d %d\n", p2->x, p2->y, p3->x, p3->y, i2[3]);
    delete p1; delete p2; delete p3; delete[] i1; delete[] i2;
}
```

!!! note "动态存储期没有“错误值”"
    C++26 把**自动**存储期变量的未初始化读取从 UB 改为错误行为（erroneous behavior，[[basic.indet]]），但 `new int` 这类**动态**存储期对象的默认初始化仍然得到**不确定值**，读取它仍然是 UB。

### 求值顺序（¶25）{{c++17}}

¶25 两条先序关系：

- **分配函数的调用**先序于 *new-initializer* 中表达式的求值；
- **对象的初始化**先序于 *new-expression* 的值计算。

第一条是 C++17 加入的（[[P0145R3]]）。在此之前，`new T(f())` 中先调用 `f()` 还是先分配是**未指明**的。这个旧规则曾造成一个经典的泄漏场景：

```cpp
g(std::shared_ptr<A>(new A), h());   // C++14：可能 new A → h() → shared_ptr 构造
                                     // 若 h() 抛异常，A 泄漏
```

C++17 的函数实参求值顺序规则（每个实参的求值整体上不交错，[[expr.call]]）解决了这个问题；¶25 则进一步确定了 *new-expression* 内部的顺序。注意它也意味着：即使初始化器的求值抛异常，分配也**已经发生了**——此时由 ¶27 负责释放。

```cpp title="new-order.cpp" run ok
#include <cstdio>
#include <cstdlib>
#include <new>

struct W {
    explicit W(int) { std::puts("  W ctor"); }
    static void* operator new(std::size_t n) { std::puts("  allocate"); return ::operator new(n); }
    static void operator delete(void* p) { std::puts("  deallocate"); ::operator delete(p); }
};
int arg() { std::puts("  evaluate initializer"); return 1; }

int main() {
    delete new W(arg());   // 输出顺序必须是：allocate → evaluate initializer → W ctor → deallocate
}
```

### 析构函数被潜在调用（¶26）

¶26 若 *new-expression* 创建**类类型对象的数组**，析构函数被**潜在调用**（potentially invoked，[[class.dtor]]）。原因：若第 k 个元素的构造抛异常，前 k−1 个已构造的元素必须按逆序析构。所以即使你从不 `delete[]`，`new T[n]` 也要求 `T` 的析构函数**可访问且未删除**。

```cpp title="array-dtor-required.cpp" error
struct P { private: ~P() = default; public: P() = default; };
P* a = new P;      // OK：单个对象的 new 不调用析构函数
P* b = new P[2];   // error: 数组 new 潜在调用析构函数，而它是私有的
```

## 初始化失败时的释放（¶27–¶32）

### 何时释放（¶27）

¶27 若初始化的**任何部分**（脚注 54：包括求值 *new-initializer*、调用构造函数）**以异常终止**，且能找到一个**合适的释放函数**，就调用它释放正在构造对象所在的内存，然后异常在 *new-expression* 的上下文中继续传播。若找不到**无歧义的匹配**释放函数，传播异常**不会**释放内存。注 13：对于不真正分配内存的分配函数（如 `new (buf) T`），这是合适的；否则很可能导致内存泄漏。

### 释放函数的查找（¶28–¶29）

¶28 与 ¶13 对称：类类型（或其数组）且未以 `::` 开头时，先在类作用域查找释放函数名，找不到再去全局。

¶29 匹配规则：

- **非 placement** 分配函数：使用普通的释放函数查找规则（与 [[expr.delete]] 相同）。
- **placement** 分配函数：按 ¶30 选择。

无论哪种，匹配的释放函数（如果有）必须**未被删除**并且在 *new-expression* 处**可访问**。

### placement 的匹配释放函数（¶30–¶31）

¶30 对 placement 分配函数，匹配的释放函数这样选：

- ¶30.1 候选中的函数**模板**替换为用模板实参推导得到的特化；
- ¶30.2 删去形参类型列表与分配函数**不完全相同**的候选（忽略各自的第一个形参：`size_t` vs `void*`）；
- ¶30.3 删去约束不满足的候选；
- ¶30.4 若恰好剩一个，选中它；
- ¶30.5 否则不选任何释放函数。

如果选中的是一个**普通释放函数**（usual deallocation function，[[basic.stc.dynamic.deallocation]]），程序**非良构**。

¶30 中处理模板和约束的细节（¶30.1、¶30.3 以及例 8–10）是 C++23 之后的新措辞，此前的标准对模板形式的 placement delete 如何匹配语焉不详。注 14：比分配函数**多一个**尾随形参的释放函数**永远不会**匹配，即使它有默认实参。

为什么"选中普通释放函数"要定为非良构？看例 7：

```cpp title="placement-usual-mismatch.cpp" error
#include <cstddef>
struct S {
    static void* operator new(std::size_t, std::size_t);   // placement 分配函数
    static void operator delete(void*, std::size_t);       // 普通（sized）释放函数
};
S* p = new (0) S;   // error: 普通释放函数"匹配"了 placement 分配函数
```

按 ¶30.2，`operator delete(void*, size_t)` 去掉第一个形参后是 `(size_t)`，与 `operator new(size_t, size_t)` 去掉第一个形参后的 `(size_t)` 相同，因此"匹配"。但它是一个**普通** sized delete，其第二个形参的含义是"对象的大小"，而 placement new 传给它的却是 placement 实参 `0`——含义完全不同。与其悄悄传错实参，不如直接报错。

例 8–10 展示模板与约束：

```cpp title="placement-delete-template.cpp" ok
#include <cstddef>
struct A {};
struct T { T(); };

void* operator new(std::size_t s, A& al);    // #1
template<int = 0>
void operator delete(void* p, A& al);        // #2：模板，推导出 operator delete<0>(void*, A&)

A al;
T* p = new (al) T;   // OK：使用 #1，构造抛异常时使用 #2
```

例 9 中有两个都能匹配的候选（一个模板、一个非模板），¶30.4 不满足，于是**不选任何释放函数**——程序仍然良构，只是构造抛异常时不会释放。例 10 用 `requires (I > 0)` 排除掉模板，剩下的非模板就被选中。

### 传给释放函数的实参（¶32）

¶32 释放函数的第一个实参是分配函数返回的值（`void*`）。若调用的是 placement 释放函数，传给它**与 placement 分配函数相同的额外实参**——即 *new-placement* 中的那些。若实现被允许为某个实参引入临时量或复制，是否在两次调用中使用同一个对象是**未指明**的。

### 综合例子

```cpp title="new-cleanup.cpp" run ok
#include <cstdio>
#include <new>

struct Arena { alignas(16) char buf[256]; std::size_t used = 0; };

struct Widget {
    int v;
    explicit Widget(int v) : v(v) { if (v < 0) throw v; }

    static void* operator new(std::size_t n) {
        std::printf("  Widget::operator new(%zu)\n", n);
        return ::operator new(n);
    }
    static void operator delete(void* p) noexcept {
        std::puts("  Widget::operator delete(void*)");
        ::operator delete(p);
    }
    static void* operator new(std::size_t n, Arena& a) {
        std::printf("  Widget::operator new(%zu, Arena&)\n", n);
        void* p = a.buf + a.used; a.used += n; return p;
    }
    static void operator delete(void*, Arena&) noexcept {   // 与 placement 版本匹配
        std::puts("  Widget::operator delete(void*, Arena&)");
    }
};

int main() {
    std::puts("new Widget(-1):");
    try { new Widget(-1); } catch (int) { std::puts("  caught"); }   // 普通释放函数被调用

    Arena a;
    std::puts("new (a) Widget(-2):");
    try { new (a) Widget(-2); } catch (int) { std::puts("  caught"); }   // placement 释放函数被调用

    std::puts("::new Widget(3):");
    Widget* g = ::new Widget(3);   // :: 跳过类作用域，使用全局 operator new
    ::delete g;                    // 对称地使用全局 operator delete
}
```

## constexpr new {{c++20}}

结合 ¶15 与 [[expr.const.core]]：C++20 起（[[P0784R7]]），常量求值中可以使用 *new-expression*，条件是：

- 调用的是**可替换的全局**分配函数（由于 ¶15，调用总被省略，存储由编译器提供）；
- 分配必须在**同一次**常量求值中被 `delete` 释放——这种分配称为**暂时分配**（transient allocation）。分配不能"泄漏"到常量表达式的结果中（不能用 `constexpr` 指针变量保存它）。

```cpp title="constexpr-new.cpp" ok
constexpr int sum(int n) {
    int* p = new int[n];            // 常量求值中：分配调用总被省略（¶15）
    for (int i = 0; i < n; ++i) p[i] = i;
    int s = 0;
    for (int i = 0; i < n; ++i) s += p[i];
    delete[] p;                     // 必须在同一次常量求值中释放
    return s;
}
static_assert(sum(10) == 45);
```

```cpp title="constexpr-new-leak.cpp" error
constexpr int* leak() { return new int(1); }
constexpr int* q = leak();   // error: 分配逃逸出常量求值
```

C++26 起（[[P2747R2]]）**placement new** 也可以在常量求值中使用（`operator new(size_t, void*)` 成为 `constexpr`），条件是指针指向合适类型的对象（详见 [[expr.const.core]]）。这让 `std::construct_at` 不再需要编译器"开后门"。{{c++26}}

```cpp title="constexpr-placement-new.cpp" ok
#include <memory>
#include <new>
constexpr int g() {
    std::allocator<int> al;
    int* p = al.allocate(1);
    ::new (static_cast<void*>(p)) int(7);   // C++26：常量求值中可用 placement new
    int r = *p;
    std::destroy_at(p);
    al.deallocate(p, 1);
    return r;
}
static_assert(g() == 7);
```

## placement new 与 const 对象

*new-expression* 本身不禁止在 `const` 对象的存储上创建对象（被分配类型可以是任何完整对象类型），但 [[basic.life#12]] 规定：在**静态、线程或自动存储期的 const 完整对象**所占（或曾经占用）的存储上创建新对象是 **UB**。原因是编译器可以假设这些对象的值永不改变（甚至把它们放进只读段）。动态存储期的 `const` 对象不受此限制，但替换后需要 `std::launder` 才能通过旧指针访问新对象（旧对象是 `const` 完整对象，不能透明替换，[[basic.life#9]]）。

```cpp title="const-placement.cpp" ub
#include <new>
struct S { int m; };
const S cs{1};
int main() {
    ::new (const_cast<S*>(&cs)) S{2};   // UB: 静态存储期 const 完整对象的存储被复用
}
```

```cpp title="const-dynamic-placement.cpp" run ok
#include <new>
struct S { int m; };
int main() {
    const S* p = new const S{1};       // 动态存储期的 const 对象
    ::new (const_cast<S*>(p)) S{2};    // OK：[basic.life] ¶12 只管静态/线程/自动存储期
    p = std::launder(p);               // 旧对象是 const 完整对象，不能透明替换
    int r = p->m;
    delete p;
    return r == 2 ? 0 : 1;
}
```

## 历史与演进

!!! history "C++98 → 当前草案"
    - **C++98**：`new` 的基本形式、placement 语法、`std::nothrow`、数组开销 *x* 已经存在；负的数组边界是 UB。
    - **C++11**：花括号 *new-initializer*；`new auto(x)`；负数或溢出的数组大小改为抛出 `std::bad_array_new_length`（新增该异常类）。
    - **C++14**：[[N3664]] 允许省略/合并可替换全局分配函数的调用（¶14、¶16、¶18）；sized deallocation（N3778）影响 ¶29 选中的释放函数。
    - **C++17**：[[P0035R4]] 对齐 new（¶20、`std::align_val_t`）；[[P0145R3]] 规定分配先序于初始化器求值（¶25）；CTAD 也可用于 `new A{1, 2}`。
    - **C++20**：[[P0784R7]] constexpr new（¶15）；[[P1009R2]] 未知边界数组的 new（¶7）；括号聚合初始化让 `new int[](1, 2)` 成立。
    - **C++26**：[[P2747R2]] constexpr placement new {{c++26}}。
    - **当前草案**：括号类型使用 *nofun-type-id*；placement 释放函数匹配对模板与约束的精确处理（¶30）。

## 陷阱

!!! pitfall "`new T[n]` 与 `delete` 不配对"
    数组 new 必须配 `delete[]`，单对象 new 必须配 `delete`，哪怕元素类型是 `int`。判断标准是**被分配类型**，不是语法（`using Buf = char[64]; new Buf` 也是数组 new）。

!!! pitfall "以为 `new T` 会清零"
    `new int`、`new Pt`（聚合）、`new int[n]` 都只做默认初始化，值不确定。需要零时写 `new T()`、`new T{}` 或 `new int[n]()`。

!!! pitfall "只声明了 placement operator new 的类"
    类作用域中**任何**名为 `operator new` 的声明都会隐藏全局版本（¶13）。只写了 `operator new(size_t, Arena&)` 的类，`new T` 会编译失败。

!!! pitfall "依赖替换的 operator new 一定被调用"
    ¶14 允许省略对可替换全局分配函数的调用。用替换 `operator new` 来"统计 new 次数"的测试，在优化后可能得到更少的计数。

!!! pitfall "以为 `new (buf) T[n]` 正好用 `n * sizeof(T)` 字节"
    标准库的 `operator new[](size_t, void*)` 不加开销（¶21），但**用户定义**的 placement `operator new[]` 可能被加上 cookie。不要假设数组 placement new 的结果等于 `buf`。

## 思考题

!!! question "思考题 1"
    `struct A { static void* operator new(std::size_t, int); };` 之后，`new A`、`new (1) A`、`::new A` 哪些良构？

<details markdown="1">
<summary>答案</summary>

`new A`：¶13 在 `A` 的作用域找到了 `operator new`，全局版本被隐藏；对实参列表 `(sizeof(A))` 做重载决议，唯一的候选需要两个实参，失败；¶20.2 加上对齐实参再试，仍然失败——**非良构**。`new (1) A`：匹配 `operator new(size_t, int)`，良构（它没有匹配的 placement delete，所以构造抛异常时内存泄漏，但这不影响良构性）。`::new A`：只查找全局，找到 `::operator new(size_t)`，良构。
</details>

!!! question "思考题 2"
    对 `int n = 0;`，`new int[n]` 返回什么？能对结果解引用吗？`delete[]` 它是必要的吗？

<details markdown="1">
<summary>答案</summary>

¶8 末尾：值为 0 时仍然调用分配函数，分配一个**零元素数组**。[[basic.stc.dynamic.allocation]] 要求即使请求大小为 0，成功的分配也返回一个**非空**且与其他存活分配不同的指针。结果指针不指向任何对象（零元素数组没有首元素，[[expr.delete]] 脚注 56），解引用是 UB；但它确实占有一次分配，必须 `delete[]`，否则泄漏。
</details>

!!! question "思考题 3"
    `new (std::nothrow) T(f())` 中，若分配失败返回空，`f()` 会被调用吗？若 `f()` 抛异常，会发生什么？

<details markdown="1">
<summary>答案</summary>

¶25：分配先序于初始化器的求值。分配失败返回空时，¶22 规定"不做初始化"，所以 `f()` **不会**被调用（它是初始化的一部分）。若分配成功而 `f()` 抛异常，这属于 ¶27 所说的"初始化的任何部分以异常终止"：`std::nothrow` 版本是 placement 分配函数，按 ¶30 查找匹配的 `operator delete(void*, const std::nothrow_t&)`（标准库提供），用它释放内存，然后异常继续传播。
</details>

## 小结

| 阶段 | 段落 | 规则 |
|---|---|---|
| 类型 | ¶1–¶2 | 完整对象类型，非抽象，可带 cv；`auto`/CTAD 按 `T x init;` 推导 |
| 数组边界 | ¶6–¶9 | 只有第一维可为运行期值；无效值：常量 → 非良构，运行期 → `bad_array_new_length` 或空指针 |
| 未知边界 | ¶7 | 必须有初始化器，由其推导元素个数（C++20） |
| 结果 | ¶11 | 数组 → 首元素指针 `T*`；否则 → 对象指针 |
| 查找 | ¶13、¶28 | 类类型先查类作用域（隐藏全局），`::new` 只查全局 |
| 省略/合并 | ¶14–¶18 | 只针对可替换全局分配函数；常量求值中总是省略 |
| 实参 | ¶17、¶20–¶21 | 大小（数组可含开销 *x*）、可能的 `align_val_t`、placement 实参；两次尝试 |
| 失败 | ¶22 | 抛 `bad_alloc` 或返回空；返回空则不初始化；不分配形式返回空是 UB |
| 初始化 | ¶24 | 无初始化器 → 默认初始化；否则直接初始化 |
| 顺序 | ¶25 | 分配 → 初始化器求值 → 初始化 → 值计算 |
| 清理 | ¶26–¶32 | 初始化抛异常 → 调用匹配的释放函数；placement 需形参列表完全一致，匹配到普通释放函数则非良构 |
