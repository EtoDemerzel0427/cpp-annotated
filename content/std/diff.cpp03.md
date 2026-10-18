---
title: C++ 与 ISO C++ 2003 的差异
summary: Annex C.7：从 C++03 升级到 C++11 及以后会遇到的 39 条不兼容——新字符串字面量前缀和用户定义字面量吞掉宏、新关键字、整数字面量类型、只有字面量才是空指针常量、&& 进入类型名、auto 不再是存储类、收窄转换、无名命名空间改为内部链接、隐式特殊成员被删除、析构函数隐式 noexcept、>> 闭合模板、export 改作他用，以及大量库签名变化。逐条给出前后对比与 Clang 23 / libc++ 实测。
status: draft
covers: *
related: diff, diff.cpp11, diff.iso, lex.key, conv.ptr, dcl.init.list, dcl.link, temp.arg, class.dtor, except.spec
tags: 附录, 兼容性, 迁移, C++11
updated: 2026-10-18
---

[diff.cpp03] 列出 C++03 → C++11 这一步引入的不兼容，是附录里最长的一节之一。C++11 几乎重写了这门语言：右值引用、`constexpr`、`auto`、`decltype`、lambda、`noexcept`、新的字面量种类、线程。新东西多，占用旧语法的地方也多。好在大部分改动编译器都会报错；需要人工审查的主要是三处：析构函数隐式 `noexcept`、条件运算符和 `typeid` 的值类别变化、库容器的若干行为变化。

由于 C++03 与 C++98 只有少量技术勘误的差别，这一节同样适用于 C++98 代码。

实测环境：Clang 23.1.3 + libc++，对比 `-std=c++03` 与 `-std=c++11`。

¶1 [diff.cpp03.general]：本小节列出与 ISO C++ 2003 的差异，是在前面各小节所列差异**之外**的部分。

## Clause [lex]：词法约定 {#diff.cpp03.lex}

### ¶1 新的字符串字面量种类

**受影响小节**：[[lex.pptoken]]

**改动**：新增编码前缀和原始字符串：`u8"…"`、`u"…"`、`U"…"`、`R"(…)"` 以及组合 `u8R`、`uR`、`UR`、`LR`。

**影响**：名叫 `R`、`u8`、`u8R`、`u`、`uR`、`U`、`UR`、`LR` 的宏，紧挨着字符串字面量时不再展开，而是成为字面量的一部分：

```cpp run std=c++11 title="u8macro.cpp" ok
#include <cstdio>
#define u8 "abc"
const char* s = u8"def";   // C++03："abc" "def" 拼接成 "abcdef"；现在："def"
int main() { std::puts(s); }
```

**Clang 23 实测**：`-std=c++03` 输出 `abcdef`，`-std=c++11` 输出 `def`。（C++20 起 `u8"def"` 的类型是 `const char8_t[4]`，上面这段在 C++20 下还会因为类型不匹配报错，见 [[diff.cpp17]]。）

**改写难度**：容易，但不会有诊断（C++11 到 C++17 之间）。搜索名为这些前缀的宏。

### ¶2 用户定义字面量

**受影响小节**：[[lex.pptoken]]

**改动**：字符串字面量后紧跟标识符构成一个 *user-defined-string-literal* 记号。

```cpp
#define _x "there"
"hello"_x   // C++03：两个记号，_x 展开，结果 "hellothere"
            // 现在：一个记号，_x 不展开，需要 operator""_x
```

**Clang 23 实测**：C++03 输出 `hellothere`；C++11 报 `no matching literal operator for call to 'operator""_x'`。最常见的受害者是 `"%" PRId64` 写成了 `"%"PRId64`（中间没有空格）：C++11 起 `PRId64` 被当作字面量后缀。

**改写难度**：容易，在字面量和宏之间加空格。

### ¶3 新关键字

**受影响小节**：[[lex.key]]

**改动**：新增 `alignas`、`alignof`、`char16_t`、`char32_t`、`constexpr`、`decltype`、`noexcept`、`nullptr`、`static_assert`、`thread_local`。

**改写难度**：容易。`-std=c++03 -Wc++11-compat` 可以提前找出来。

### ¶4 整数字面量的类型

**受影响小节**：[[lex.icon]]

**改动**：无后缀的十进制整数字面量，`long` 放不下时，C++03 中可以变成 `unsigned long`；C++11 跟随 C99，改为依次尝试 `int`、`long`、`long long`，不再选无符号类型。

**理由**：与 C99 兼容。

```cpp
// 在 long 为 32 位的平台上（ILP32、Windows）：
2147483648     // C++03：unsigned long；现在：long long
-2147483648    // C++03：unsigned long 的 2147483648（正数！）；现在：long long 的 −2147483648
```

**Clang 23 实测**：用 `--target=i386-linux-gnu` 检查 `__typeof__(2147483648)`：`-std=c++03` 下是 `unsigned long`，`-std=c++11` 下是 `long long`。

**改写难度**：需人工审查。受影响的是跨越 `long` 上限的常量，常见于 `INT_MIN` 的手写版本。

## Clause [expr]：表达式 {#diff.cpp03.expr}

### ¶1 只有字面量才是整数空指针常量

**受影响小节**：[[conv.ptr]]

**改动**：整数**空指针常量**（[[g:null-pointer-constant]]）只能是值为 0 的整数**字面量**。C++03 中任何值为 0 的整数常量表达式都是空指针常量。

**理由**：消除与模板、常量表达式之间令人意外的交互。

```cpp
void f(void*);   // #1
void f(...);     // #2
template<int N> void g() {
  f(0*N);        // 现在调用 #2；C++03 调用 #1
}
```

C++03 中 `g<0>` 实例化后 `0*N` 是值为 0 的常量表达式，可以转换为空指针，于是选 #1。这让函数的行为依赖于模板实参的**值**。

**Clang 23 实测**：两种模式下 `g<0>()` 都调用 #2，Clang 把这条回溯到了 C++03。

**改写难度**：容易。需要空指针就写 `nullptr`（C++11 起）或 `0`。

### ¶2 `typeid` 操作数的求值

**受影响小节**：[[expr.typeid]]

**改动**：C++11 引入 xvalue 之后，`C().b` 这种"右值的成员"成为 xvalue，是 glvalue。`typeid` 对多态类类型的 glvalue 操作数**要求值**，以取得动态类型。

```cpp
void f() {
  struct B {
    B() {}
    virtual ~B() { }
  };
  struct C { B b; };
  typeid(C().b);   // C++03：不求值；现在：求值（构造并销毁一个 C）
}
```

**Clang 23 实测**：给 `B()` 加打印，`-std=c++03` 不打印，`-std=c++11` 打印。Clang 还会在 C++11 下给出 `expression with side effects will be evaluated despite being used as an operand to 'typeid' [-Wpotentially-evaluated-expression]`。

**改写难度**：几乎不会碰到。

### ¶3 整数 `/` 和 `%` 的舍入方向

**受影响小节**：[[expr.mul]]

**改动**：整数除法的商向零舍入。C++03 中操作数有负数时，舍入方向（向零或向负无穷）由实现定义。

**理由**：提高可移植性，与 C99 兼容。

**影响**：在 C++03 中选择了"向负无穷舍入"的实现上，`-7 / 2` 从 −4 变成 −3，`-7 % 2` 从 1 变成 −1。主流实现一直是向零舍入，所以实际影响很小。

**改写难度**：需要向下取整时用 `std::div` 之外的显式写法。

### ¶4 `&&` 可以出现在类型名中

**受影响小节**：[[expr.log.and]]

**改动**：`&&` 在类型名中表示右值引用。

```cpp error
bool b1 = new int && false;              // C++03：(new int) && false，即 false；现在：new (int&&) 非良构
struct S { operator int(); };
bool b2 = &S::operator int && false;     // C++03：false；现在：非良构（operator int&&）
```

**Clang 23 实测**：C++11 下 `cannot allocate reference type 'int &&' with new`。

**改写难度**：容易，加括号。

### ¶5 条件运算符中更少的复制

**受影响小节**：[[expr.cond]]

**改动**：条件运算符的操作数是 xvalue 时，不再强制复制。

```cpp
void f() {
  struct B {
    B() {}
    B(const B&) { }
  };
  struct D : B {};
  struct BB { B b; };
  struct DD { D d; };
  true ? BB().b : DD().d;   // C++03：额外复制一次；现在：不复制也不移动
}
```

**Clang 23 实测**：给 `B(const B&)` 加打印，`-std=c++03` 打印一次，`-std=c++11` 不打印。

**改写难度**：只有依赖复制构造函数副作用的代码受影响。

## Clause [dcl]：声明 {#diff.cpp03.dcl.dcl}

### ¶1 `auto` 不再是存储类说明符

**受影响小节**：[[dcl.spec]]

**改动**：`auto` 改为占位类型说明符，表示从初始化器推导变量类型（[[dcl.spec.auto]]）。

**影响**：`auto int x;` 这种写法失效。

**Clang 23 实测**：C++11（直到 C++2c）下只给警告：`'auto' storage class specifier is not permitted in C++11, and will not be supported in future releases [-Wauto-storage-class]`，并没有拒绝。

**改写难度**：容易，删掉 `auto`。

### ¶2 聚合初始化中的收窄限制

**受影响小节**：[[dcl.init.list]]

**改动**：花括号初始化（包括 C++03 就有的聚合初始化 `T x[] = {…}`）中不允许**收窄转换**（[[g:narrowing-conversion]]）。

```cpp error
int x[] = { 2.0 };   // error: double → int 是收窄转换；C++03 良构
```

**Clang 23 实测**：C++11 下 `type 'double' cannot be narrowed to 'int' in initializer list [-Wc++11-narrowing]`。这是错误，但可以用 `-Wno-c++11-narrowing` 降级。

**改写难度**：容易，显式转换。在大量 C 风格表格初始化的代码里可能很多。

### ¶3 无名命名空间中的名字改为内部链接

**受影响小节**：[[dcl.link]]

**改动**：无名命名空间中声明的名字从外部链接改为内部链接；语言链接（`extern "C"`）只作用于有外部链接的名字。

**理由**：与用户的预期一致：无名命名空间本来就是为了"文件私有"。

```cpp
namespace { extern "C" { extern int x; } }   // #1：C++03 外部链接 + C 语言链接；现在：内部链接 + C++ 语言链接
namespace A { extern "C" int x = 42; }       // #2：外部链接 + C 语言链接
int main(void) { return x; }
```

C++03 中 #1 和 #2 是同一个 C 链接的变量 `x`。现在 #1 是内部链接的另一个实体，#2 不是它的定义，违反 ODR。

**Clang 23 实测**：两种模式都编译、链接通过，程序返回 42，即 Clang 仍把两者当作同一个实体。

**改写难度**：需人工审查，实际代码中极少见。

## Clause [class]：类 {#diff.cpp03.class}

### ¶1 隐式特殊成员函数在定义会非良构时被定义为删除

**受影响小节**：[[class.default.ctor]]、[[class.dtor]]、[[class.copy.ctor]]、[[class.copy.assign]]

**改动**：隐式声明的默认构造函数、析构函数、复制构造函数、复制赋值运算符，如果隐式定义会是非良构的，现在直接被定义为**删除**。

**理由**：改善模板实参推导失败（SFINAE）的表现：删除的函数可以在重载决议阶段被检测到，而"定义时才报错"的函数不行。

**影响**：C++03 中在不需要定义的场合（例如不求值的操作数里）使用这类函数是合法的，现在非良构：

```cpp error
struct S { int& r; };   // 引用成员：复制赋值的隐式定义非良构
S* p;
int n = sizeof(*p = *p);   // C++03：不求值，不需要定义 → 良构；现在：使用了被删除的函数 → 非良构
```

**Clang 23 实测**：C++03 下通过；C++11 下 `object of type 'S' cannot be assigned because its copy assignment operator is implicitly deleted`。

**改写难度**：容易。

### ¶2 用户声明的析构函数有隐式异常说明

**受影响小节**：[[class.dtor]]

**改动**：析构函数（包括用户声明的）在没有显式异常说明时，隐式具有与隐式声明时相同的异常说明，通常是 `noexcept(true)`（[[except.spec]]）。

**理由**：澄清对析构函数的要求。

**影响**：从析构函数抛出异常的 C++03 代码，现在会调用 `std::terminate`：

```cpp run title="dtor_throw.cpp"
#include <cstdio>
struct D { ~D() { throw 1; } };
int main() {
  try { D d; } catch (...) { std::puts("caught"); }
}
```

**Clang 23 实测**：

```text
-std=c++03:  caught
-std=c++11:  libc++abi: terminating due to uncaught exception of type int   (退出码 134)
```

Clang 在 C++11 下还会警告 `'~D' has a non-throwing exception specification but can still throw [-Wexceptions]`。

**改写难度**：需人工审查。确实需要从析构函数抛出的（极少），显式写 `~D() noexcept(false)`；否则改成不抛出。

## Clause [temp]：模板 {#diff.cpp03.temp}

### ¶1 `export` 改作模块之用

**受影响小节**：[[temp.param]]

**改动**：C++03 的"导出模板"（`export template<…>`）被删除；`export` 关键字在 C++20 中重新用于模块（[[module]]、[[cpp.module]]、[[cpp.import]]）。

**理由**：C++03 的 `export` 没有实现共识，事实上只有 EDG 前端实现过。

**Clang 23 实测**：`export template<class T> void f(T);` 在 `-std=c++03` 和 `-std=c++11` 下只给 `warning: exported templates are unsupported`；`-std=c++20` 下报 `export declaration can only be used within a module interface`。

**改写难度**：容易，删掉 `export`（反正没有编译器真的支持过它）。

### ¶2 嵌套的模板右尖括号不再需要空格

**受影响小节**：[[temp.arg]]

**改动**：模板实参列表中的 `>>` 被当作两个 `>`，闭合两层模板。

**理由**：一个长期存在的小麻烦；别名模板出现后，表示非类类型的模板嵌套会更多，问题会更突出。

```cpp error
template <class T> struct X { };
template <int N> struct Y { };
X< Y< 1 >> 2 > > x;   // C++03：Y< (1 >> 2) >；现在：Y<1> 闭合后多出 "2 > >"，非良构
```

**Clang 23 实测**：

```text
$ clang++ -std=c++03 ...
warning: use of right-shift operator ('>>') in template argument will require parentheses in C++11 [-Wc++11-compat]
$ clang++ -std=c++11 ...
error: expected unqualified-id
```

**改写难度**：容易，加括号：`Y< (1 >> 2) >`。

### ¶3 允许依赖调用找到内部链接的函数

**受影响小节**：[[temp.dep.candidate]]

**改动**：C++03 中，模板实例化点的依赖调用经 ADL 只能找到有外部链接的函数；C++11 去掉了这个限制。

**理由**：限制过严，简化重载决议规则。

```cpp
template<class T> void call(T t) { g(t, 0); }
namespace N {
  struct S {};
  void g(S, long);           // 外部链接
  static void g(S, int);     // 内部链接
}
// call(N::S())：C++03 只能找到 g(S, long)；现在 g(S, int) 也参与，并且是更好的匹配
```

**Clang 23 实测**：两种模式下都调用 `g(S, int)`，Clang 在 C++03 下也使用新规则。

**改写难度**：需人工审查，实际影响很小。

## Clause [library]：库引言 {#diff.cpp03.library}

### ¶1 新的保留标识符

**受影响**：[library] 到 [exec] 各章

**改动**：后续版本加入标准库的所有标识符。

**影响**：使用了这些名字的 C++03 代码可能编译失败或得到不同结果。最典型的是 `using namespace std;` 之后自己定义的 `bind`、`function`、`array`、`move`、`begin`、`size`，与 `std::` 中新增的同名设施发生冲突或被 ADL 选中。标准的"Index of Library Names"列出了所有库名字。

**改写难度**：中等。去掉 `using namespace std;` 是最彻底的办法。

### ¶2 新头文件

**受影响小节**：[[headers]]

C++ 头文件：`<array>`、`<atomic>`、`<chrono>`、`<condition_variable>`、`<forward_list>`、`<future>`、`<initializer_list>`、`<mutex>`、`<random>`、`<ratio>`、`<regex>`、`<scoped_allocator>`、`<system_error>`、`<thread>`、`<tuple>`、`<typeindex>`、`<type_traits>`、`<unordered_map>`、`<unordered_set>`。C 兼容头文件：`<cfenv>`、`<cinttypes>`、`<cstdint>`、`<cuchar>`。

### ¶3 `swap` 移到了 `<utility>`

**受影响小节**：[[swappable.requirements]]

**改动**：`std::swap` 的声明从 `<algorithm>` 移到 `<utility>`。

**影响**：只包含 `<utility>` 而依赖 `<algorithm>` 中 `swap` 的代码不受影响；只包含 `<algorithm>` 用 `swap` 的代码在不同实现上可能需要改为包含 `<utility>`。

### ¶4 新的保留命名空间 `posix`

**受影响小节**：[[namespace.posix]]

全局命名空间 `posix` 保留给标准化。

### ¶5 宏名的额外限制

**受影响小节**：[[macro.names]]

**改动**：属性标识符不能用作宏名。定义 `override`、`final`、`noreturn` 宏的 C++03 代码失效。当前草案把这条规则从库对程序的约束（[[constraints]]）移到了预处理一章（[[cpp.replace.general]]），使它成为核心语言规则，并随契约加入了 `pre`、`post`，见 [[diff.cpp23]] [cpp] ¶1。

**改写难度**：容易。

## Clause [support]：语言支持库 {#diff.cpp03.language.support}

这一小节在草案中编号为 C.7.8，本站的目录数据中没有收录它的 stable name，内容一并写在这里。

### ¶1 `operator new` 可能抛出 `std::bad_alloc` 以外的异常

**受影响小节**：[[new.delete.single]]

**改动**：全局 `operator new` 的声明中去掉了 `throw(std::bad_alloc)` 动态异常说明。

**理由**：统一地应用 `noexcept`。

**影响**：假设全局 `operator new` 只会抛出 `std::bad_alloc` 的 C++03 代码可能执行得不同（替换后的分配函数可以抛别的异常）。用 `throw(std::bad_alloc)` 声明替换版本的 C++03 代码，按附录的说法在当前标准下非良构——当然，自 C++17 起任何带类型的动态异常说明都是非良构的。

**Clang 23 实测**：`void* operator new(std::size_t) throw(std::bad_alloc)` 在 C++03、C++11 下都接受，C++17 起报 `ISO C++17 does not allow dynamic exception specifications`。

**改写难度**：容易，删掉异常说明。

## Clause [diagnostics]：诊断库 {#diff.cpp03.diagnostics}

### ¶1 线程局部的 `errno`

**受影响小节**：[[errno]]

**改动**：`errno` 是线程局部的。

**理由**：支持新的线程设施。

**影响**：依赖"各线程共享同一个 `errno`"的（本来就是实现特定的）C++03 代码，行为可能改变。

## Clause [utilities]：通用工具库 {#diff.cpp03.utilities}

### ¶1 标准函数对象不再派生自 `unary_function` / `binary_function`

**受影响小节**：[[refwrap]]、[[arithmetic.operations]]、[[comparisons]]、[[logical.operations]]、[[bitwise.operations]]

**理由**：已被新特性取代；`unary_function` 和 `binary_function` 在 C++17 中被删除（见 [[diff.cpp14]]）。

**影响**：依赖 `std::plus<int>` 等派生自 `binary_function` 的代码（例如把它们转成基类指针、或用基类做特化）编译失败。

## Clause [strings]：字符串库 {#diff.cpp03.strings}

### ¶1 `basic_string` 不再允许引用计数实现

**受影响小节**：[[string.classes]]

**改动**：对 `basic_string` 的要求不再允许写时复制（COW）的引用计数实现。

**理由**：引用计数字符串的失效规则与其他实现有微妙差别；这个改动使行为一致。另一个重要原因是 C++11 的并发模型：COW 字符串的 `operator[]` 等非 const 操作需要"去共享"，与多线程下的数据竞争规则冲突。

**影响**：C++03 代码可能执行得不同。最著名的实例是 GCC 的 libstdc++：为了遵守这条，它在 GCC 5 中引入了新的 `std::__cxx11::basic_string` ABI，与旧 ABI 不兼容（`_GLIBCXX_USE_CXX11_ABI` 宏）。

### ¶2 放宽 `basic_string` 的失效规则

**受影响小节**：[[string.require]]

**改动**：一些 const 成员函数（如 `data`、`c_str`）不再使迭代器失效。

**理由**：允许短字符串优化（SSO）。

## Clause [containers]：容器库 {#diff.cpp03.containers}

### ¶1 `size()` 的复杂度改为常数

**受影响小节**：[[container.requirements]]

**改动**：所有提供 `size()` 的容器，`size()` 都是常数时间。

**理由**：C++03 没有规定 `size()` 的复杂度，各实现分道扬镳，性能特征不一致。

**影响**：一些符合 C++03 的实现不再符合要求。`std::list` 为了常数 `size()` 必须维护一个计数器，这改变了它的布局，`splice` 某一段的复杂度也从常数变成线性。libstdc++ 的 `std::list` 因此同样随 C++11 ABI 改变。

### ¶2 要求放宽

**受影响小节**：[[container.requirements]]

**改动**：要求的放宽：

- 并非所有容器都提供 `size()`（`forward_list` 没有），判空用 `empty()` 而不是 `size() == 0`；
- 并非所有容器构造后都是空的（`array`）；
- 并非所有容器的 `swap()` 都是常数复杂度（`array`）。

**影响**：想要在各种容器上通用的 C++03 代码可能需要按上面几条调整。

### ¶3 默认可构造的要求

**受影响小节**：[[container.requirements]]

**改动**：容器的各成员函数对元素类型的要求被逐一细化（例如只有 `resize(n)` 要求默认可构造）。

**影响**：显式实例化一个元素类型没有默认构造函数的容器（`template class std::vector<NoDefault>;`）可能编译失败，因为显式实例化会实例化所有成员，包括要求默认构造的那些。

### ¶4 签名变化：原来返回 `void` 的函数

**受影响小节**：[[sequence.reqmts]] 与 [[associative.reqmts]]

**改动**：以下成员函数不再返回 `void`（改为返回迭代器）：

- `set`、`multiset`、`map`、`multimap` 的 `erase(iter)` 和 `erase(begin, end)`；
- `vector`、`deque`、`list`、`forward_list` 的 `insert(pos, num, val)` 和 `insert(pos, beg, end)`。

**理由**：旧签名丢掉了重新计算代价可能很高的有用信息。

**影响**：依赖返回 `void` 的代码（例如取这些函数的成员函数指针）编译失败。

### ¶5 签名变化：`iterator` 形参改为 `const_iterator`

**受影响小节**：[[sequence.reqmts]] 与 [[associative.reqmts]]

**改动**：以下成员函数的形参从 `iterator` 改为 `const_iterator`：

- `vector`、`deque`、`list`、`set`、`multiset`、`map`、`multimap` 的 `insert(iter, val)`；
- `vector`、`deque`、`list`、`forward_list` 的 `insert(pos, beg, end)`；
- `set`、`multiset`、`map`、`multimap` 的 `erase(begin, end)`；
- `list::splice` 和 `list::merge` 的所有形式。

**理由**：过度规定。插入位置只用来定位，不需要可变迭代器。

**影响**：直接调用不受影响（`iterator` 可以转换为 `const_iterator`）；取成员函数指针、或传入只能转换为 `iterator` 的自定义类型时编译失败。

### ¶6 签名变化：`resize`

**受影响小节**：[[sequence.reqmts]] 与 [[associative.reqmts]]

**改动**：`vector`、`deque`、`list` 的 `resize` 的填充值从按值传递改为按引用传递，并增加了单参数重载 `resize(n)`。

**理由**：性能，与移动语义兼容。

**影响**：取 `resize` 的成员函数指针的代码可能编译失败（现在有两个重载）。

## Clause [algorithms]：算法库 {#diff.cpp03.algorithms}

### ¶1 某些算法之后输入的结果状态

**受影响小节**：[[algorithms.general]]

**改动**：算法改用移动而不是复制。

**理由**：新特性（移动语义）需要。

**影响**：C++03 程序可能观察到一个"有效但未指定"状态的对象，现在处于另一个"有效但未指定"的状态。例如 `std::remove` 和 `std::remove_if` 之后，序列尾部（`[new_end, end)`）的值可能与以前不同：元素被移走后，尾部可能是空字符串，而不再是原值的副本。

**改写难度**：需人工审查。读取 `remove` 之后尾部元素的代码本来就依赖了未指定的行为。

## Clause [numerics]：数值库 {#diff.cpp03.numerics}

### ¶1 规定了复数的表示

**受影响小节**：[[complex.numbers]]

**改动**：`std::complex<float>`、`complex<double>`、`complex<long double>` 的表示被规定为两个元素的数组（实部、虚部），可以 `reinterpret_cast` 成 `T[2]`。

**理由**：与 C99 的 `_Complex` 兼容。

**影响**：依赖某个实现的特定二进制表示的 C++03 代码可能不兼容（实际上所有主流实现本来就是这种布局）。

## [localization]：本地化库 {#diff.cpp03.locale}

### ¶1 `num_get` 识别十六进制浮点值

**受影响小节**：[[facet.num.get.virtuals]]

**改动**：`num_get` 刻面在解析浮点数时识别十六进制浮点格式（`0x1p3`）。

**理由**：新特性需要。

**影响**：C++03 中从 `"0x1p3"` 读 `double` 得到 0（读到 `x` 停止），现在可能得到 8。

**libc++ 实测**：两种模式下 `std::istringstream("0x1p3") >> d` 都得到 8。

## Clause [input.output]：输入/输出库 {#diff.cpp03.input.output}

### ¶1 已有的布尔转换函数改为 `explicit`

**受影响小节**：[[istream.sentry]]、[[ostream.sentry]]、[[iostate.flags]]

**改动**：流和 sentry 的布尔转换从 C++03 的 `operator void*()` 改为 `explicit operator bool()`。

**理由**：表明意图，避免各种变通写法。

**影响**：依赖隐式布尔转换的代码编译失败。这些转换出现在：

1. 把流传给接受 `bool` 的函数；
2. 用 `==` 与 `false` 或 `true` 比较；
3. 从返回类型为 `bool` 的函数中返回流；
4. 通过聚合初始化来初始化 `bool` 成员；
5. 初始化一个会绑定到临时对象的 `const bool&`。

```cpp error
#include <iostream>
bool ok() { return std::cin; }       // error: 现在非良构
bool e = std::cin == false;          // error: 现在非良构
```

`if (std::cin)`、`while (in >> x)`、`!std::cin` 这些**上下文转换**不受影响。

**libc++ 实测**：C++03 下通过；C++11 下 `no viable conversion from returned value of type 'istream' ... to function return type 'bool'` 等。

**改写难度**：容易。`return !std::cin.fail();` 或 `return static_cast<bool>(std::cin);`。

### ¶2 `ios_base::failure` 的基类改变

**受影响小节**：[[ios.failure]]

**改动**：`std::ios_base::failure` 不再直接派生自 `std::exception`，而是派生自 `std::system_error`（后者派生自 `std::runtime_error`）。

**理由**：提供更详细的错误信息（`error_code`）。

**影响**：假设它直接派生自 `std::exception` 的代码可能执行得不同，例如 `catch (std::runtime_error&)` 现在能捕获它。

### ¶3 `ios_base` 中的标志类型改为位掩码

**受影响小节**：[[ios.base]]

**改动**：`std::ios_base` 的标志类型（`fmtflags`、`iostate`、`openmode`、`seekdir`）是位掩码类型，各个值定义为 `constexpr static` 成员。

**影响**：依赖这些类型是 `std::bitset` 或整数类型的 C++03 代码可能编译失败：

```cpp
#include <iostream>
int main() {
  int flag = std::ios_base::hex;
  std::cout.setf(flag);   // 可能非良构：setf 不接受 int 类型的实参
}
```

**libc++ 实测**：两种模式都能编译：libc++ 的 `fmtflags` 是 `unsigned int`，`int` 可以隐式转换。用枚举实现 `fmtflags` 的库（如 libstdc++）上会报错。

**改写难度**：容易，变量改用 `std::ios_base::fmtflags` 类型。

## 小结

| 条目 | 类型 | Clang 23 / libc++ |
|---|---|---|
| `u8` 等宏名 | 静默改变 | 已实现 |
| `"hello"_x` | 非良构 | 已实现 |
| 新关键字 | 非良构 | 已实现 |
| 整数字面量类型 | 改变类型 | 已实现 |
| 只有字面量是空指针常量 | 调用不同重载 | 已实现并回溯 |
| `typeid` / `?:` 值类别 | 静默改变 | 已实现 |
| `/` `%` 舍入 | 实现定义 → 确定 | — |
| `new int && false` | 非良构 | 已实现 |
| `auto` 存储类 | 非良构 | **只警告** |
| 收窄 | 非良构 | 已实现 |
| 无名命名空间链接 | ODR 违规 | 行为未变 |
| 隐式删除的特殊成员 | 非良构 | 已实现 |
| 析构函数隐式 `noexcept` | 静默改变（terminate） | 已实现 |
| `export` | 非良构 | C++20 前只警告 |
| `>>` | 非良构 | 已实现 |
| 内部链接的依赖调用 | 调用不同重载 | 已实现并回溯 |
| 流的 `explicit operator bool` | 非良构 | 已实现 |
| `fmtflags` 类型 | 可能非良构 | libc++ 不受影响 |
