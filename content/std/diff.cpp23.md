---
title: C++ 与 ISO C++ 2023 的差异
summary: Annex C.2：从 C++23 升级到 C++26 会遇到的 21 条不兼容——新 token ^^ 和 :]、新关键字 contract_assert、枚举混合运算与数组比较非良构、delete 不完整类型非良构、T...[n] 成为包索引、宏名限制、to_string 输出变化，以及 <codecvt>、<strstream>、wstring_convert 等的删除。逐条给出前后对比与 Clang 23 / libc++ 实测。
status: draft
covers: *
related: diff, diff.cpp26, diff.cpp20, depr, expr.arith.conv, expr.rel, expr.delete, dcl.init.list, temp.constr, cpp.replace
tags: 附录, 兼容性, 迁移, C++26
updated: 2026-10-18
---

[diff.cpp23] 列出 C++23 → C++26 这一步引入的不兼容（C++26 之后的改动另见 [[diff.cpp26]]）。核心语言部分的主线是**类型安全**：C++20 已经弃用的几种隐式转换和比较，在 C++26 里正式变成错误；另外静态反射、契约、包索引三个大特性各自占用了一点原来合法的语法。库部分则是一批弃用多年的设施被删除。

实测环境：Clang 23.1.3 + libc++，对比 `-std=c++23` 与 `-std=c++2c`，均加 `-Wall -Wextra`。

¶1 [diff.cpp23.general]：本小节按正文章节列出与 ISO C++ 2023 的差异。

## Clause [lex]：词法约定 {#diff.cpp23.lex}

### ¶1 新运算符 `^^`

**受影响小节**：[[lex.operators]]

**改动**：`^^` 成为一个新的 *operator-or-punctuator*，即反射运算符（[[g:reflection-operator]]，见 [[expr.reflect]]）。

**理由**：静态反射需要。

**影响**：按"最长匹配"分词（[[lex.pptoken]]），两个紧挨着的 `^` 现在被读成一个 `^^` token。原来写成 `a^^b` 的位运算表达式就会被拆错：

```cpp error
struct C { int operator^(int); };
int operator^(int (C::*p)(int), C);
int i = &C::operator^^C{};      // error: 现在非良构；C++23 中是 (&C::operator^) ^ C{}
```

C++23 把 `&C::operator^^C{}` 分成 `&C::operator^`、`^`、`C{}`：取成员函数指针，再用第二个 `operator^` 与 `C{}` 异或。现在 `operator^^` 是一个 token，`operator` 后面跟着它不构成任何合法的 *operator-function-id*。

**Clang 23 实测**：两种模式都接受。Clang 23 尚未实现静态反射，`^^` 还不是 token。

**改写难度**：容易。在两个 `^` 之间加空格。真实代码中几乎不会出现。

### ¶2 新关键字 `contract_assert`

**受影响小节**：[[lex.key]]

**改动**：`contract_assert` 成为关键字，用于 *assertion-statement*（[[stmt.contract.assert]]）。注意 `pre` 和 `post` 是**有特殊含义的标识符**（[[g:identifier-with-special-meaning]]）而不是关键字，作为普通名字仍然可以用（但不能作宏名，见下文 [cpp] 一节）。

**影响**：用 `contract_assert` 作标识符的 C++23 代码失效。

```cpp error
int contract_assert = 0;        // error: 现在 contract_assert 是关键字
```

**Clang 23 实测**：两种模式都接受。Clang 23 尚未实现契约（`-fcontracts` 不是可识别的选项）。

**改写难度**：容易，改名即可。

## Clause [expr]：表达式 {#diff.cpp23.expr}

### ¶1 枚举与另一种枚举或浮点类型混合运算非良构

**受影响小节**：[[expr.arith.conv]]

**改动**：当**常用算术转换**（usual arithmetic conversions）的一个操作数是枚举类型、另一个是**另一种**枚举类型或浮点类型时，程序非良构。C++20 已经弃用这些用法（当时登记在 Annex D），C++26 把弃用升级为错误。

**理由**：加强类型安全。两种无关枚举相减、枚举和 `double` 比较，几乎总是写错了。

```cpp error
enum E1 { e };
enum E2 { f };
bool b = e <= 3.7;      // error: 枚举 vs 浮点
int  k = f - e;         // error: 两种不同的枚举
auto x = true ? e : f;  // error: 条件运算符两支是不同的枚举
```

同一种枚举之间的运算、枚举与整数的运算都不受影响（`e + 1` 仍然合法，结果是 `int`）。

**Clang 23 实测**：

```text
$ clang++ -std=c++23 -fsyntax-only -Wall c23_enum.cpp
c23_enum.cpp:3:12: warning: comparison of enumeration type 'E1' with floating-point type 'double' is deprecated [-Wdeprecated-enum-float-conversion]
c23_enum.cpp:4:12: warning: arithmetic between different enumeration types ('E2' and 'E1') is deprecated [-Wdeprecated-enum-enum-conversion]
c23_enum.cpp:5:17: warning: conditional expression between different enumeration types ('E1' and 'E2') is deprecated [-Wdeprecated-enum-compare-conditional]

$ clang++ -std=c++2c -fsyntax-only -Wall c23_enum.cpp
c23_enum.cpp:3:12: error: invalid comparison of enumeration type 'E1' with floating-point type 'double'
c23_enum.cpp:4:12: error: invalid arithmetic between different enumeration types ('E2' and 'E1') [-Wenum-enum-conversion]
c23_enum.cpp:5:17: error: invalid conditional expression between different enumeration types ('E1' and 'E2') [-Wenum-enum-conversion]
```

已实现：C++23 模式下是弃用警告，C++26 模式下是错误。

**改写难度**：容易。用一元 `+` 或 `static_cast<int>` 先把枚举提升为整数：`+f - e`、`static_cast<int>(e) <= 3.7`。C 代码移植到 C++ 时也会碰到同样的问题，见 [[diff.iso]]。

### ¶2 两个数组对象之间的比较非良构

**受影响小节**：[[expr.rel]] 与 [[expr.eq]]

**改动**：关系运算符和相等运算符的两个操作数都是数组类型时，程序非良构。C++20 弃用，C++26 删除。

**理由**：旧行为令人困惑。`arr1 == arr2` 看起来是比较内容，实际上两边先经过数组到指针转换，比较的是地址。

```cpp
int arr1[5];
int arr2[5];
bool same = arr1 == arr2;       // error: 现在非良构
bool idem = arr1 == +arr2;      // OK: 一元 + 强制退化，比较地址
bool less = arr1 < +arr2;       // OK，但两个不相关对象的地址比较结果未指定
```

只要**有一边**不是数组（例如 `+arr2`、`&arr2[0]`、指针变量），就不受影响。

**Clang 23 实测**：

```text
$ clang++ -std=c++23 ...
c23_arr.cpp:3:18: warning: comparison between two arrays is deprecated; to compare array addresses, use unary '+' to decay operands to pointers [-Wdeprecated-array-compare]
$ clang++ -std=c++2c ...
c23_arr.cpp:3:18: error: comparison between two arrays is ill-formed in C++26; to compare array addresses, use unary '+' to decay operands to pointers [-Warray-compare-cxx26]
```

已实现。

**改写难度**：容易。如果本意是比较地址，加 `+`；如果本意是比较内容（更常见），改用 `std::ranges::equal` 或 `std::array`。

### ¶3 `delete` 指向不完整类类型的指针非良构

**受影响小节**：[[expr.delete]]

**改动**：*delete-expression* 的操作数指向不完整的类类型时，程序非良构。C++23 中这是合法的，但如果该类最终有非平凡析构函数或类专属的释放函数，行为未定义。

**理由**：减少未定义行为。编译器在 `delete p` 处看不到析构函数，只能跳过析构直接释放内存；一旦类后来定义了非平凡析构函数，资源就泄漏了，而这在编译期本可以发现。

```cpp error
struct S;

void f(S* p) {
  delete p;             // error: 现在非良构；C++23 中良构（可能 UB）
}

struct S {};
```

注意即使 `S` 后来定义成平凡类、旧代码"碰巧没事"，新规则也一律拒绝：判定只看 `delete` 出现处 `S` 是否完整。

**Clang 23 实测**：

```text
$ clang++ -std=c++23 ...
c23_del.cpp:2:16: warning: deleting pointer to incomplete type 'S' is incompatible with C++2c and may cause undefined behavior [-Wdelete-incomplete]
$ clang++ -std=c++2c ...
c23_del.cpp:2:16: error: cannot delete pointer to incomplete type 'S'
```

已实现。

**改写难度**：容易。把 `delete` 移到类定义可见的地方（典型场景是 pimpl：把持有者的析构函数定义放进 `.cpp` 文件）。`std::unique_ptr<S>` 的默认删除器早就用 `static_assert` 拒绝不完整类型，用它的代码不受影响。

## Clause [dcl]：声明 {#diff.cpp23.dcl.dcl}

### ¶1 `initializer_list` 底层数组之间的指针比较结果未指定

**受影响小节**：[[dcl.init.list]]

**改动**：`std::initializer_list` 的**底层数组**（[[g:backing-array]]）不再保证是彼此独立的对象：实现可以把常量内容放进静态只读存储，内容相同（或一个是另一个的后缀）的两个列表可以共享存储。

**理由**：允许实现把底层数组放进静态只读内存，避免每次调用都在栈上重新构造一个数组。

```cpp unspecified
#include <initializer_list>

bool ne(std::initializer_list<int> a, std::initializer_list<int> b) {
  return a.begin() != b.begin() + 1;
}
bool b = ne({2, 3}, {1, 2, 3});   // 现在：结果未指定
```

在 C++23 中，两个底层数组是两个不同的临时数组对象，`a.begin()` 与 `b.begin() + 1` 指向不同对象，`!=` 的结果确定为真。现在 `{2, 3}` 可以与 `{1, 2, 3}` 的后两个元素共用存储，两个指针可能相等。（附录例子的注释写作 *previously false*；按 C++23 的规则推，`ne` 原来应返回 `true`，这里的"false"大概指"两者相等"这一判断为假。不影响条目的实质：旧代码依赖的是一个确定结果，现在它变成未指定。）

**Clang 23 实测**：两种模式下，`-O0` 和 `-O2` 都输出 `1`，即没有共享存储。

**改写难度**：只有依赖底层数组地址唯一性的代码才受影响，实际中极少。需人工审查。

### ¶2 `T...[n]` 现在是包索引

**受影响小节**：[[dcl.array]]

**改动**：C++23 中，模板里的 `T...[1]` 声明一个无名的函数形参包，每个形参类型是"`T` 的数组"（随即调整为指针）。现在 `T...[n]` 是 *pack-index-specifier*（[[g:pack-index]]），表示包 `T` 的第 n 个元素。

**理由**：改进对包的处理，引入包索引。

```cpp
template <typename... T> void f(T... [1]);       // 现在：一个形参，类型是 T...[1]（第二个类型）
template <typename... T> void g(T... ptr[1]);    // 仍然是形参包：有 declarator-id

int main() {
  f<int, double>(nullptr, nullptr);   // error: 现在非良构；C++23 中声明的是 f(int[1], double[1])
  g<int, double>(nullptr, nullptr);   // OK
}
```

区分的关键是**有没有名字**：`T... ptr[1]` 有 *declarator-id*，`...` 只能是包展开；`T... [1]` 没有名字，现在优先解析成包索引。

**Clang 23 实测**：两种模式都拒绝 `f` 的调用，Clang 在 C++23 模式下也按新规则解析，并给出提示：

```text
$ clang++ -std=c++23 ...
c23_packidx.cpp:1:33: warning: pack indexing is a C++2c extension [-Wc++26-extensions]
c23_packidx.cpp:1:33: warning: 'T...[1]' is no longer a pack expansion but a pack indexing type; add a name to specify a pack expansion [-Wpre-c++26-compat]
c23_packidx.cpp:4:3: error: no matching function for call to 'f'
```

**改写难度**：容易。给形参起名：`T... args[1]`。

### ¶3 新 token `:]`

**受影响小节**：[[dcl.attr.grammar]]

**改动**：`:]` 成为一个新 token（用于反射相关的语法，例如 splice 说明符 `[: … :]`，见 [[basic.splice]]）。

**影响**：属性说明符里带 *attribute-using-prefix* 但没有任何属性、并且冒号后面紧跟 `]` 时，`:]` 被读成一个 token，属性语法就断了：

```cpp
struct [[using CC:]] C;      // error: 现在非良构；C++23 中良构
struct [[using DD: ]] D;     // OK：冒号后有空格
```

**Clang 23 实测**：两种模式都接受第一行，尚未实现。

**改写难度**：容易，加空格或删掉空的属性说明符。实际代码中几乎不存在。

## Clause [temp]：模板 {#diff.cpp23.temp}

### ¶1 部分原子约束变成折叠展开约束

**受影响小节**：[[temp.constr]]

**改动**：*requires-clause* 中的 `(E && ...)` / `(E || ...)` 形式的折叠表达式，现在规范化为**折叠展开约束**（[[g:fold-expanded-constraint]]），而不是一个整体的原子约束。

**理由**：让含折叠表达式的约束可以参与**包含**（subsumption）判断（[[temp.constr.order]]）。原来整个折叠是一个原子约束，两个看起来一样的折叠无法互相包含。

**影响**：拆开之后，每个元素 `E` 自己成为原子约束，就要求 `E` 的类型**恰好是 `bool`**。原来只要整个折叠表达式是 `bool`（`&&` 会把 `int` 转换成 `bool`）就行：

```cpp error
template <typename... V> struct A;
struct S {
  static constexpr int compare(const S&) { return 1; }
};

template <typename... T, typename... U>
void f(A<T...>*, A<U...>*)
  requires (T::compare(U{}) && ...);   // 现在：每个 T::compare(U{}) 是 int 类型的原子约束 → 非良构
                                      // C++23：整个折叠是 bool 类型的原子约束 → 良构

void g(A<S, S>* ap) {
  f(ap, ap);
}
```

**Clang 23 实测**：两种模式都报 `atomic constraint must be of type 'bool' (found 'int')`，Clang 在 C++23 模式下也按新规则处理。

**改写难度**：容易。显式转换：`requires (bool(T::compare(U{})) && ...)`。

### ¶2 从重载集推导模板实参，成功的情况更多

**受影响小节**：[[temp.deduct.call]]

**改动**：实参是重载集（函数名）时，推导会考虑约束来排除候选，并在多个候选都推导成功时有了新的处理方式。

**理由**：允许用约束消除重载集作为实参时的歧义。

**影响**：原来"推导失败于是退化为非推导上下文、由其他实参决定 `T`"的代码，现在可能从重载集里推出一个与其他实参冲突的类型：

```cpp error
template <typename T>
void f(T&&, void (*)(T&&));

void g(int&);                         // #1
inline namespace A { void g(short&&); }   // #2
inline namespace B { void g(short&&); }   // #3

void q() {
  int x;
  f(x, g);   // error: 现在非良构；C++23 中良构，T 推导为 int&
}
```

单个候选的推导规则没有变：#1 的类型 `void(int&)` 无法与 `void(T&&)` 匹配（形参是右值引用，而 #1 的形参是左值引用），推导失败；#2 和 #3 都成功推出 `T = short`。C++23 中"多于一个候选成功"使第二个形参成为非推导上下文，`T` 只由第一个实参定为 `int&`，随后 `g` 解析到 #1。新规则下 #2/#3 的推导结果被采纳，与 `int&` 冲突。

**Clang 23 实测**：两种模式都报错：

```text
c23_ded.cpp:5:19: error: no matching function for call to 'f'
c23_ded.cpp:1:28: note: candidate template ignored: deduced conflicting types for parameter 'T' ('int &' vs. 'short')
```

即 Clang 在 C++23 模式下的行为已经与新规则一致。

**改写难度**：容易。显式写出目标：`f(x, static_cast<void(*)(int&)>(g))`。

## Clause [cpp]：预处理指令 {#diff.cpp23.cpp}

### ¶1 宏名的额外限制

**受影响小节**：[[cpp.replace.general]]

**改动**：关键字、有特殊含义的标识符（`final`、`override`、`import`、`module`、`pre`、`post`，见 [[lex.name#2]]）以及（除非另有规定）[[dcl.attr]] 中规定的 *attribute-token* 都不能用作宏名。

**理由**：避免难以诊断或不可移植的写法。`#define override` 之类的宏会悄悄改变后续代码的含义。

```cpp
#define pre  1     // 现在非良构
#define post 2     // 现在非良构
#define final      // 现在非良构（C++11 起就不允许，见 [diff.cpp03.library]）
#define int long   // 现在非良构：int 是关键字
```

**Clang 23 实测**：`pre` / `post` 没有任何诊断；对关键字只给 `-Wkeyword-macro` 警告（`keyword is hidden by macro definition`）；只有替代表示 `and`、`or` 等作宏名会报错（它们一直就是运算符，不是标识符）。新规则基本没有实现。

**改写难度**：通常容易。常见的冲突来自老代码里的 `#define pre ...`、`#define post ...`（例如 HTTP 库里的方法名）。改名即可。

## Clause [library]：库引言 {#diff.cpp23.library}

### ¶1 新头文件

**受影响小节**：[[headers]]

**改动**：新增 C++ 头文件 `<contracts>`、`<debugging>`、`<hazard_pointer>`、`<hive>`、`<inplace_vector>`、`<linalg>`、`<meta>`、`<rcu>`、`<simd>`、`<stdbit.h>`、`<stdckdint.h>`、`<text_encoding>`。

**影响**：自己有同名头文件、并且通过 `#include <…>` 包含它的代码可能拿到标准库的版本。

**改写难度**：容易，改名或改用引号包含并调整搜索路径。

## Clause [mem]：内存管理库 {#diff.cpp23.mem}

### ¶1 `realloc(p, 0)` 是错误行为

**受影响小节**：[[c.malloc]]

**改动**：用非空指针和 0 大小调用 `realloc`，现在是**错误行为**（[[g:erroneous-behavior]]）。

**理由**：C 标准库（C23）不再定义这种调用的行为。C++ 没有跟着把它变成 UB，而是选择 EB：[[c.malloc#6]] 规定此时"行为是错误的，效果由实现定义"。也就是说程序不会因此失去一切保证，但这次调用被明确标为错误，实现可以诊断。

**影响**：旧代码把 `realloc(p, 0)` 当作"释放并返回空指针或一个最小块"来用，现在这是一个错误。各实现在这里本来就不一致（glibc 释放并返回空指针，其他实现可能返回一个可释放的非空指针），所以依赖它的代码本就不可移植。

**改写难度**：容易。需要释放就调用 `free(p)`；需要零大小块就显式处理。需人工审查（编译器不报错）。

## Clause [strings]：字符串库 {#diff.cpp23.strings}

### ¶1 浮点版 `to_string` / `to_wstring` 的输出改变

**受影响小节**：[[string.conversions]]

**改动**：`std::to_string(double)` 等浮点重载不再等价于 `sprintf("%f")`，而是等价于 `std::format("{}")`，即最短往返表示。

**理由**：`%f` 会丢失信息（小数点后固定 6 位，`1e-7` 变成 `"0.000000"`），而且小数点字符受全局 C locale 影响。新行为与 `std::format`、`std::to_chars` 一致。

```cpp
auto s = std::to_string(1e-7);   // 现在："1e-07"；C++23："0.000000"（'.' 可能随全局 C locale 变化）
auto t = std::to_string(3.14);   // 现在："3.14"；C++23："3.140000"
```

这是一条**静默改变**：代码照常编译，输出字符串不同。拿 `to_string` 的结果去比对、写文件或做序列化的代码会受影响。

**libc++ 实测**：两种模式下都输出 `[0.000000] [3.140000]`，新行为尚未实现。

**改写难度**：需人工审查。若需要旧格式，改用 `std::format("{:f}", x)`。

## Clause [input.output]：输入/输出库 {#diff.cpp23.io}

### ¶1 新增 `basic_istream<char>::ignore(streamsize, char)` 重载

**受影响小节**：[[istream.unformatted]]

**改动**：`std::basic_istream<char, traits>::ignore` 增加一个第二形参为 `char` 的重载。

**理由**：允许直接用 `char` 值作分隔符。原来只有 `ignore(streamsize, int_type delim)`：传入 `'\xA1'` 这样的负值 `char` 时，它被转换成 `int` 的 −95，而流内部比较的是 `traits::to_int_type(c)`（非负的 161），永远不相等，于是一路忽略到 EOF。

```cpp
std::istringstream in("\xF0\x9F\xA4\xA1 Clown Face");
in.ignore(100, '\xA1');     // 现在：忽略到 '\xA1' 为止；C++23：可能一直忽略到 EOF
in.ignore(100, -1L);        // 现在：重载歧义（long 到 int 与到 char 都是转换）；C++23：等价于 (int)-1L
```

**libc++ 实测**：两种模式下第一句都停在第 4 个字节之后（`tellg()` 为 4），第二句都能编译。即 libc++ 没有加新重载，但它的实现在 C++23 模式下已经能正确匹配 `'\xA1'`。

**改写难度**：容易。第二个实参既不是 `int` 也不是 `char` 时，显式转换。

## Annex [depr]：兼容性特性 {#diff.cpp23.depr}

这一节没有"受影响小节"字段：被删除的东西原来都在 Annex D 里，现在已经不在正文中了。删除的头文件和名字按 [[zombie.names]] 成为"僵尸名"（[[g:zombie-name]]）：程序不得使用，实现可以继续提供。

### ¶1 删除 `allocator<T>::is_always_equal`

**理由**：从 `std::allocator` 派生的**有状态**分配器会继承基类的 `is_always_equal = true_type`，`allocator_traits` 于是错误地认为它的所有实例都相等。派生类必须记得显式重新定义 `is_always_equal`，很容易漏掉。删掉之后，`allocator_traits` 回到默认的推断：`is_empty<Alloc>`。

**影响**：用 `allocator` 作基类定义分配器变得更不容易出错。

```cpp
#include <memory>
template <class T>
struct MyAlloc : std::allocator<T> {
  int tag;
};
static_assert(!std::allocator_traits<MyAlloc<int>>::is_always_equal::value);   // C++23：失败；现在：通过
```

**libc++ 实测**：`-std=c++23` 下静态断言失败，`-std=c++2c` 下通过。已实现。

### ¶2 删除 `shared_ptr` 的原子访问函数

**改动**：删除 `std::atomic_load(const shared_ptr<T>*)`、`atomic_store`、`atomic_exchange`、`atomic_compare_exchange_*` 等针对 `shared_ptr` 的自由函数（C++20 起弃用）。

**理由**：旧 API 很脆弱：被它保护的 `shared_ptr` 在类型上与普通 `shared_ptr` 没有区别，只要有一处代码不经过这组函数直接访问，就悄悄变成数据竞争（UB）。类型安全的替代品是 `std::atomic<std::shared_ptr<T>>`（见 [[util.smartptr.atomic]]）。

**libc++ 实测**：`std::atomic_load(&p)` 在两种模式下都能编译，且没有弃用警告。尚未删除。

**改写难度**：中等。要把对应的 `shared_ptr` 变量改成 `std::atomic<std::shared_ptr<T>>`，所有访问点都要跟着改。

### ¶3 删除无参的 `basic_string::reserve()`

**理由**：冗余。无参 `reserve()` 是一个非约束性的"收缩请求"，与 `shrink_to_fit()` 重复。

**libc++ 实测**：C++23 下警告 `'reserve' is deprecated [-Wdeprecated-declarations]`；C++26 下报 `too few arguments to function call`。已删除。

**改写难度**：容易。改成 `shrink_to_fit()`，或者直接删掉这次调用（它没有可观察的效果）。

### ¶4 删除 `<codecvt>` 头文件

**改动**：删除 `<codecvt>` 及其全部内容：`codecvt_mode`、`codecvt_utf8`、`codecvt_utf16`、`codecvt_utf8_utf16`、`consume_header`、`generate_header`、`little_endian`。

**理由**：这个头文件已经弃用了三个版本（C++17 起），而且不符合现行 Unicode 标准，只支持已经过时的 UCS-2 编码。

**libc++ 实测**：C++23 下 `std::codecvt_utf8<wchar_t>` 给出弃用警告；C++26 下 `no member named 'codecvt_utf8' in namespace 'std'`。

**改写难度**：中等到困难。标准库目前没有完整的直接替代品；常用方案是第三方库（ICU 等）或自写 UTF-8/16/32 转换。

### ¶5 删除 `<strstream>` 头文件

**改动**：删除 `<strstream>` 及 `istrstream`、`ostrstream`、`strstream`、`strstreambuf`。

**理由**：自第一版 C++ 标准起就已弃用。`<spanstream>`（C++23）提供了更新、更安全的"在固定缓冲区上做流操作"的设施。

**libc++ 实测**：C++23 下 `'istrstream' is deprecated`；C++26 下 `no type named 'istrstream' in namespace 'std'`。

**改写难度**：中等。固定缓冲区用 `std::ispanstream` / `std::ospanstream`，动态缓冲区用 `std::stringstream`；注意 `ostrstream::str()` 返回的 `char*` 不以零结尾、需要 `freeze(false)` 等旧语义要一并清理。

### ¶6 删除 `wstring_convert` 与 `wbuffer_convert`

**理由**：规定不充分，没有清晰的错误报告机制，而且已经弃用三个版本。

**libc++ 实测**：C++23 下弃用警告，C++26 下 `no template named 'wstring_convert'`。

**改写难度**：同 ¶4。

## 小结

| 条目 | 类型 | Clang 23 / libc++ |
|---|---|---|
| `^^` token | 非良构 | 未实现（无反射） |
| `contract_assert` 关键字 | 非良构 | 未实现（无契约） |
| 枚举 × 枚举 / 浮点 | 非良构 | 已实现（C++23 警告，C++26 错误） |
| 数组 == 数组 | 非良构 | 已实现 |
| `delete` 不完整类型 | 非良构 | 已实现 |
| `initializer_list` 底层数组地址 | 未指定 | 未观察到共享 |
| `T...[n]` | 非良构 / 改变含义 | 已实现，且回溯到 C++23 模式 |
| `[[using CC:]]` | 非良构 | 未实现 |
| 折叠展开约束 | 非良构 | 已实现，且回溯到 C++23 模式 |
| 重载集推导 | 非良构 | C++23 模式下也拒绝 |
| 宏名限制 | 非良构 | 基本未实现 |
| `realloc(p, 0)` | EB | — |
| `to_string(double)` | 静默改变 | 未实现 |
| `istream::ignore(n, char)` | 改变 / 歧义 | 未加新重载 |
| Annex D 删除项 | 非良构 | `reserve()`、`<codecvt>`、`<strstream>`、`wstring_convert`、`is_always_equal` 已删；`shared_ptr` 原子函数仍在 |
