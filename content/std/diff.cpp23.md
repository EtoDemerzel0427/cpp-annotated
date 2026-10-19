---
title: C++ 与 ISO C++ 2023 的差异
summary: 从 C++23 升级到 C++26 时，哪些原来合法的代码会报错或改变行为：新记号与关键字、枚举混合运算和数组比较变成错误、delete 不完整类型、包索引、宏名限制、to_string 的输出，以及一批被删除的库设施。
status: done
covers: *
related: diff, diff.cpp26, diff.cpp20, depr, expr.arith.conv, expr.rel, expr.delete, dcl.init.list, temp.constr, cpp.replace
tags: 附录, 兼容性, 迁移, C++26
updated: 2026-10-19
---

!!! tldr
    - C++20 弃用的两类写法在 C++26 中成为错误：不同枚举之间、枚举与浮点之间的算术和比较，以及两个数组直接比较。`delete` 一个指向不完整类类型的指针也成为错误。
    - 静态反射、契约和包索引占用了原来合法的语法：记号 `^^` 和 `:]`、关键字 `contract_assert`、无名的 `T...[n]`；`pre`、`post` 和所有关键字都不能再定义成宏。
    - 浮点版 `std::to_string` 改为输出最短往返表示，`to_string(3.14)` 从 `"3.140000"` 变成 `"3.14"`。代码照常编译，输出静默改变。
    - 库删除了 `<codecvt>`、`<strstream>`、`wstring_convert`、`shared_ptr` 的原子自由函数、无参 `string::reserve()` 和 `allocator::is_always_equal`。
    - 在 `-std=c++23` 下编译，Clang 会对大部分即将失效的写法给出弃用或兼容性警告，升级前先把它们清理掉。

[diff.cpp23] 列出 C++26 相对 C++23 的不兼容：原来良构的代码，在 C++26 中变成非良构，或者含义改变。每一条在标准里都写成同样的格式：受影响的条款、改了什么、为什么改、对旧代码有什么影响，通常还附一个例子。C++26 之后的改动另见 [[diff.cpp26]]，更早的版本见 [[diff.cpp20]] 等。

¶1 本节按正文的章节顺序排列，下文也照此分组。文中的实测都用本机 Clang 23.1.3 + libc++，对比 `-std=c++23` 与 `-std=c++2c`。

## 词法约定 [diff.cpp23.lex] {#diff.cpp23.lex}

### 新记号 `^^`

```cpp error
struct C { int operator^(int); };
int operator^(int (C::*p)(int), C);
int i = &C::operator^^C{};   // error: C++23 中良构
```

¶1 C++26 新增了反射运算符 `^^`（[[g:reflection-operator]]，见 [[expr.reflect]]），它是一个新的记号（[[lex.operators]]）。分词时总是取能组成记号的最长字符序列（[[lex.pptoken]]），所以两个紧挨着的 `^` 现在被读成一个 `^^`。

C++23 把上面的第三行分成 `&C::operator^`、`^`、`C{}`：先取成员函数指针，再调用第二个 `operator^`。C++26 中 `operator` 后面跟着的是 `^^`，不构成任何运算符函数名，程序非良构。两个 `^` 之间加一个空格就能恢复原意。

Clang 23 还没有实现静态反射，两种模式都接受这段代码。

### 新关键字 `contract_assert`

```cpp error
int contract_assert = 0;   // error: contract_assert 是关键字
```

¶2 C++26 的契约断言语句写作 `contract_assert(条件);`（[[stmt.contract.assert]]），所以 `contract_assert` 成为关键字（[[lex.key]]），不能再用作名字。函数契约用的 `pre` 和 `post` 不是关键字，而是有特殊含义的标识符（[[g:identifier-with-special-meaning]]），仍然可以作变量名，但不能定义成宏（见下文 [cpp] 一节）。

Clang 23 还没有实现契约，两种模式都接受这段代码。

## 表达式 [diff.cpp23.expr] {#diff.cpp23.expr}

### 枚举与另一种枚举或浮点类型混合运算

<div class="compare" markdown="1">

```cpp error
enum E1 { e };
enum E2 { f };
bool b = e <= 3.7;      // error
int  k = f - e;         // error
auto x = true ? e : f;  // error
```

```cpp ok
enum E1 { e };
enum E2 { f };
bool b = +e <= 3.7;     // OK
int  k = +f - e;        // OK
int  y = e + 1;         // OK：同一枚举与整数
```

</div>

¶1 二元运算符在计算之前要把两个操作数转换成同一类型，这一步叫**常用算术转换**（usual arithmetic conversions，[[expr.arith.conv]]）。C++26 规定，如果一个操作数是枚举类型，另一个是另一种枚举类型或浮点类型，程序就非良构。条件运算符的两个分支属于不同枚举时同样如此。

两种无关的枚举相减、枚举与 `double` 比较，几乎总是写错了，所以 C++20 先把这些用法列为弃用，C++26 改为错误。枚举与整数的运算不受影响。确实需要混合运算时，用一元 `+` 或 `static_cast<int>` 先把枚举转换成整数。C 代码移植到 C++ 时也常碰到这一条，见 [[diff.iso]]。

Clang 23 已经实现：`-std=c++23` 下给出 `-Wdeprecated-enum-float-conversion`、`-Wdeprecated-enum-enum-conversion` 等弃用警告，`-std=c++2c` 下三行都报错。

### 两个数组直接比较

<div class="compare" markdown="1">

```cpp error
int arr1[5];
int arr2[5];
bool same = arr1 == arr2;  // error
```

```cpp ok
int arr1[5];
int arr2[5];
bool idem = arr1 == +arr2; // 比较地址
bool less = arr1 < +arr2;  // 结果未指定
```

</div>

¶2 相等运算符和关系运算符的两个操作数都是数组时，程序非良构（[[expr.rel]]、[[expr.eq]]）。`arr1 == arr2` 看起来是比较内容，实际上两边先经过数组到指针的转换，比较的是地址，所以几乎总是写错了。C++20 把它列为弃用，C++26 改为错误。

只要有一边不是数组类型，例如 `+arr2`、`&arr2[0]` 或一个指针变量，就不受影响。右边第二行比较两个无关对象的地址，`<` 的结果未指定。本意是比较内容时，改用 `std::ranges::equal` 或 `std::array`。

Clang 23 已经实现：`-std=c++23` 下是 `-Wdeprecated-array-compare` 警告，`-std=c++2c` 下报错，并提示用一元 `+` 让操作数退化成指针。

### `delete` 指向不完整类类型的指针

```cpp error
struct S;

void f(S* p) {
  delete p;   // error: C++23 中良构
}

struct S {};
```

¶3 一个类只有声明、还没有定义时，它是**不完整类型**。C++26 规定 *delete-expression* 的操作数指向不完整类类型时，程序非良构（[[expr.delete]]）。

在 `delete p` 处，编译器看不到 `S` 的析构函数和类专属的 `operator delete`，只能跳过析构直接释放内存。C++23 允许这样写，但如果 `S` 最终有非平凡的析构函数或自己的释放函数，行为未定义。新规则把这类错误提前到编译期，而且只看 `delete` 出现处 `S` 是否完整：上例中 `S` 后来定义成一个平凡的类，同样被拒绝。

典型的受影响场景是 pimpl 惯用法。修正方法是把执行 `delete` 的函数（通常是外层类的析构函数）定义在 `.cpp` 文件里、`S` 的定义之后。`std::unique_ptr<S>` 的默认删除器一直用 `static_assert` 拒绝不完整类型，用它的代码不受影响。

Clang 23 已经实现：`-std=c++23` 下给出 `-Wdelete-incomplete` 警告，`-std=c++2c` 下报错。

## 声明 [diff.cpp23.dcl.dcl] {#diff.cpp23.dcl.dcl}

### `initializer_list` 的底层数组可以共享存储

```cpp unspecified
#include <initializer_list>

bool ne(std::initializer_list<int> a,
        std::initializer_list<int> b) {
  return a.begin() != b.begin() + 1;
}
bool b = ne({2, 3}, {1, 2, 3});   // 结果未指定
```

¶1 `std::initializer_list` 本身不存元素，元素放在编译器生成的一个数组里，这个数组叫**底层数组**（[[g:backing-array]]）。C++23 中每个底层数组都是一个独立的临时数组，所以上例中 `a.begin()` 和 `b.begin() + 1` 指向不同的对象，`ne` 一定返回 `true`。

C++26 允许实现把内容是常量的底层数组放进静态只读存储，并且让内容相同、或者一个是另一个后缀的列表共用存储（[[dcl.init.list]]）。于是 `{2, 3}` 可以就是 `{1, 2, 3}` 的后两个元素，`ne` 的结果变成未指定。这样每次调用不必在栈上重新构造数组。标准例子的注释写着 previously false，按 C++23 的规则推算应为 true，这里的实质是一个确定的结果变成了未指定。

只有依赖底层数组地址彼此不同的代码受影响，实际中极少。本机 Clang 23 在 `-O0` 和 `-O2` 下都输出 `1`，没有观察到共享。

### `T...[n]` 现在是包索引

```cpp
template <typename... T> void f(T... [1]);
template <typename... T> void g(T... ptr[1]);

int main() {
  f<int, double>(nullptr, nullptr);   // error: C++23 中良构
  g<int, double>(nullptr, nullptr);   // OK
}
```

¶2 C++23 中，模板里的 `T... [1]` 声明一个无名的函数形参包，每个形参的类型是 `T` 的数组，随即调整为指针，所以 `f<int, double>` 的形参是 `int*` 和 `double*`。C++26 引入了**包索引**（[[g:pack-index]]）：`T...[n]` 表示包 `T` 的第 n 个元素，于是 `f` 变成只有一个形参、类型为 `double`，原来的调用非良构（[[dcl.array]]）。

区分两者的是有没有形参名。`T... ptr[1]` 有名字，`...` 只能是包展开，含义不变；没有名字的 `T... [1]` 现在解析成包索引。给形参起个名字就能保留原意。

Clang 23 在 `-std=c++23` 下也按新规则解析，并给出 `-Wpre-c++26-compat` 警告，提示 `T...[1]` 已不再是包展开。

### 新记号 `:]`

```cpp
struct [[using CC:]] C;    // error: C++23 中良构
struct [[using DD: ]] D;   // OK
```

¶3 反射的拼接语法 `[: r :]`（[[basic.splice]]）需要新记号 `:]`。属性说明符可以用 `using 命名空间:` 前缀省去重复的属性命名空间（[[dcl.attr.grammar]]）。如果这个前缀后面一个属性也没有，冒号又紧贴着 `]`，`:]` 就会被读成一个记号，属性的语法被打断。冒号后加空格即可。这种空属性说明符在实际代码中几乎不存在。

Clang 23 还没有实现这条，两种模式都接受第一行。

## 模板 [diff.cpp23.temp] {#diff.cpp23.temp}

### 折叠表达式约束要求每个元素都是 `bool`

```cpp error
template <typename... V> struct A;
struct S {
  static constexpr int compare(const S&) { return 1; }
};

template <typename... T, typename... U>
void f(A<T...>*, A<U...>*)
  requires (T::compare(U{}) && ...);   // 每一项是 int

void g(A<S, S>* ap) {
  f(ap, ap);   // error: C++23 中良构
}
```

¶1 约束（*requires-clause* 里的条件）在比较之前要拆成**原子约束**：不能再分解的子表达式，每个原子约束的类型必须恰好是 `bool`（[[temp.constr]]）。C++23 把 `(E && ...)` 这样的折叠表达式整个当作一个原子约束，它的类型是 `bool`，所以每个 `E` 是 `int` 也没关系。

C++26 把这类折叠规范化为**折叠展开约束**（[[g:fold-expanded-constraint]]），每个 `E` 各自成为原子约束，于是要求 `E` 本身是 `bool`。这样改是为了让两个含相同折叠的约束能比较强弱，参与包含（subsumption）判断（[[temp.constr.order]]）。修正方法是显式转换：`requires (bool(T::compare(U{})) && ...)`。

Clang 23 在 `-std=c++23` 下也按新规则处理，两种模式都报 atomic constraint must be of type 'bool'。

### 从重载集推导模板实参

```cpp error
template <typename T>
void f(T&&, void (*)(T&&));

void g(int&);                             // #1
inline namespace A { void g(short&&); }   // #2
inline namespace B { void g(short&&); }   // #3

void q() {
  int x;
  f(x, g);   // error: C++23 中良构，T 推导为 int&
}
```

¶2 实参是一个函数名、对应多个重载时，模板实参推导会逐个尝试这些候选（[[temp.deduct.call]]）。单个候选的规则没有变：#1 的类型 `void(int&)` 无法与 `void(T&&)` 匹配，推导失败；#2 和 #3 都推出 `T = short`。

C++23 中，只要有不止一个候选推导成功，第二个形参就不参与推导，`T` 只由第一个实参定为 `int&`，然后 `g` 解析到 #1。C++26 为了能用约束排除重载集里的候选，改写了这条规则（[[temp.deduct.call#6]]）：只尝试约束得到满足的候选，如果所有成功的推导得出同一个结果，就采用它。#2 和 #3 都推出 `short`，于是 `T = short` 被采纳，与第一个实参推出的 `int&` 冲突，推导失败。

修正方法是显式指定模板实参：`f<int&>(x, g)`。这时第二个形参的类型是 `void(*)(int&)`，`g` 解析到 #1。Clang 23 在 `-std=c++23` 下也按新规则报错。

## 预处理指令 [diff.cpp23.cpp] {#diff.cpp23.cpp}

### 宏名的限制

```cpp
#define pre  1      // error: pre 有特殊含义
#define post 2      // error
#define override    // error
#define int long    // error: int 是关键字
```

¶1 C++26 规定，关键字、有特殊含义的标识符（`final`、`override`、`import`、`module`、`pre`、`post` 等，见 [[lex.name]]）以及 [[dcl.attr]] 中的属性名都不能定义或取消定义为宏，`likely` 和 `unlikely` 可以定义成函数式宏（[[cpp.replace.general]]）。以前类似的限制只写在库条款里，只约束使用标准库的程序。

这类宏会悄悄改变后面代码的含义，而且在不同实现上效果不同。老代码里最常见的冲突是 `#define pre ...`、`#define post ...`，改名即可。

Clang 23 基本没有实现这条：`pre`、`post` 没有任何诊断，关键字和 `override` 只有 `-Wkeyword-macro` 警告。`and`、`or` 这类替代记号不是标识符，一直不能作宏名。

## 库引言 [diff.cpp23.library] {#diff.cpp23.library}

¶1 C++26 新增头文件 `<contracts>`、`<debugging>`、`<hazard_pointer>`、`<hive>`、`<inplace_vector>`、`<linalg>`、`<meta>`、`<rcu>`、`<simd>`、`<stdbit.h>`、`<stdckdint.h>` 和 `<text_encoding>`（[[headers]]）。项目里有同名头文件并用 `#include <...>` 包含时，可能拿到标准库的版本。

## 内存管理库 [diff.cpp23.mem] {#diff.cpp23.mem}

¶1 用非空指针和大小 0 调用 `realloc`，现在是**错误行为**（[[g:erroneous-behavior]]）：标准认定这是错误，但行为仍然有定义，效果由实现决定，实现可以诊断（[[c.malloc#6]]）。

起因是 C23 不再定义这种调用。各实现本来就不一致：glibc 释放内存并返回空指针，本机 macOS 返回一个新的非空指针。把 `realloc(p, 0)` 当作释放来用的代码本来就不可移植，需要释放就调用 `free(p)`。编译器不会报错，需要人工检查。

## 字符串库 [diff.cpp23.strings] {#diff.cpp23.strings}

```cpp
auto s = std::to_string(1e-7);   // C++26: "1e-07"   C++23: "0.000000"
auto t = std::to_string(3.14);   // C++26: "3.14"    C++23: "3.140000"
```

¶1 浮点版的 `to_string` 和 `to_wstring` 以前等价于 `sprintf("%f")`，现在等价于 `std::format("{}", val)`，输出能精确还原原值的最短表示（[[string.conversions]]）。`%f` 固定保留 6 位小数，`1e-7` 会变成 `"0.000000"`，而且小数点字符受全局 C locale 影响。

代码照常编译，只是输出的字符串变了。拿结果做比较、写文件或序列化的代码会受影响，需要旧格式时改用 `std::format("{:f}", x)`。本机 libc++ 还没有实现，两种模式都输出旧格式。

## 输入/输出库 [diff.cpp23.io] {#diff.cpp23.io}

```cpp
std::istringstream in("\xF0\x9F\xA4\xA1 Clown Face");
in.ignore(100, '\xA1');   // C++26：在 '\xA1' 处停下
in.ignore(100, -1L);      // C++26：重载歧义
```

¶1 `istream::ignore(n, delim)` 原来只有一个版本，`delim` 的类型是 `int_type`。在 `char` 为有符号类型的平台上，`'\xA1'` 转换成 `int` 后是 −95，而流内部比较的是 `traits::to_int_type(c)`，即非负的 161，两者永远不相等，于是一直忽略到文件结尾。

C++26 给 `basic_istream<char>` 增加了 `ignore(streamsize, char)` 重载（[[istream.unformatted]]），`char` 实参不再经过有问题的转换。副作用是第二个实参既不是 `int` 也不是 `char` 时（例如 `-1L`），两个重载一样好，调用变成歧义，需要显式转换。

本机 libc++ 没有加这个重载，但它的实现在两种模式下都能在 `'\xA1'` 处正确停下（`tellg()` 为 4），第二行也都能编译。

## 删除的弃用特性 [diff.cpp23.depr] {#diff.cpp23.depr}

这一节的设施原来都列在弃用特性附录 [[depr]] 里，C++26 把它们删除了。删除的名字按 [[zombie.names]] 成为**僵尸名**（[[g:zombie-name]]）：程序不能再使用它们，实现可以继续提供。

### `allocator<T>::is_always_equal`

```cpp
#include <memory>
template <class T>
struct MyAlloc : std::allocator<T> {
  int tag;   // 有状态
};
static_assert(!std::allocator_traits<MyAlloc<int>>
                  ::is_always_equal::value);
// C++23：失败   C++26：通过
```

¶1 `std::allocator` 的 `is_always_equal` 是 `true_type`。从它派生的有状态分配器会继承这个成员，`allocator_traits` 于是误以为它的所有实例都相等，派生类必须记得自己重新定义。删除之后，`allocator_traits` 回到默认的推断方式 `is_empty<Alloc>`，上例就对了。libc++ 已经实现。

### `shared_ptr` 的原子访问函数

¶2 `std::atomic_load(const shared_ptr<T>*)`、`atomic_store`、`atomic_exchange`、`atomic_compare_exchange_*` 这组自由函数被删除。它们保护的 `shared_ptr` 在类型上与普通 `shared_ptr` 没有区别，只要有一处代码绕过这组函数直接访问，就悄悄构成数据竞争。替代品是 `std::atomic<std::shared_ptr<T>>`（[[util.smartptr.atomic]]），改写时要把变量类型和所有访问点一起改掉。本机 libc++ 在 C++26 模式下仍然提供这组函数，也没有弃用警告。

### 无参的 `basic_string::reserve()`

¶3 无参的 `reserve()` 是一个不保证生效的收缩请求，与 `shrink_to_fit()` 重复，因此被删除。改成 `shrink_to_fit()`，或者直接删掉这次调用。libc++ 在 C++23 下给出弃用警告，C++26 下报参数不足。

### `<codecvt>`、`<strstream>`、`wstring_convert`

¶4 `<codecvt>` 头文件及其中的 `codecvt_utf8`、`codecvt_utf16`、`codecvt_utf8_utf16`、`codecvt_mode` 等被删除。它从 C++17 起就是弃用的，而且只支持已经过时的 UCS-2 编码。

¶5 `<strstream>` 头文件及 `istrstream`、`ostrstream`、`strstream`、`strstreambuf` 被删除，它们从第一版 C++ 标准起就是弃用的。固定缓冲区改用 C++23 的 `std::ispanstream`、`std::ospanstream`，动态缓冲区改用 `std::stringstream`。

¶6 `wstring_convert` 和 `wbuffer_convert` 被删除，因为它们规定得不充分，没有清晰的错误报告机制。标准库目前没有直接的替代品，常用的方案是 ICU 之类的第三方库或者自己写 UTF 转换。

这三项 libc++ 都已经实现：C++23 下给出 `-Wdeprecated-declarations` 警告，C++26 下报名字不存在。

## 小结

| 条目 | 旧代码的结局 | Clang 23 / libc++ |
|---|---|---|
| `^^`、`:]` 记号 | 非良构 | 未实现 |
| `contract_assert` 关键字 | 非良构 | 未实现 |
| 枚举与枚举、浮点混合运算 | 非良构 | 已实现，C++23 下警告 |
| 两个数组比较 | 非良构 | 已实现，C++23 下警告 |
| `delete` 不完整类型 | 非良构 | 已实现，C++23 下警告 |
| `initializer_list` 底层数组地址 | 结果未指定 | 未观察到共享 |
| 无名 `T...[n]` | 非良构或含义改变 | 已实现，C++23 模式同样处理 |
| 折叠展开约束 | 非良构 | 已实现，C++23 模式同样处理 |
| 从重载集推导 | 非良构 | 已实现，C++23 模式同样处理 |
| 宏名限制 | 非良构 | 基本未实现 |
| `realloc(p, 0)` | 错误行为 | 无诊断 |
| 浮点 `to_string` | 输出改变 | 未实现 |
| `istream::ignore(n, char)` | 行为改变或歧义 | 未加重载 |
| 删除的弃用特性 | 非良构 | 除 `shared_ptr` 原子函数外均已删除 |
