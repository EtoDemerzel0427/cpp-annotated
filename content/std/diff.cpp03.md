---
title: C++ 与 ISO C++ 2003 的差异
summary: 合法的 C++03（以及 C++98）代码升级到 C++11 及以后会在哪里编译失败、哪里悄悄改变行为，逐条给出前后对比与 Clang 23 的实际表现。
status: done
covers: *
related: diff, diff.cpp11, diff.iso, lex.key, conv.ptr, dcl.init.list, dcl.link, temp.arg, class.dtor, except.spec
tags: 附录, 兼容性, 迁移, C++11
updated: 2026-10-19
---

!!! tldr
    - 这一节列出合法的 C++03 代码在 C++11 及以后版本中编译失败或行为改变的地方。C++98 与 C++03 只差一些勘误，所以对 C++98 代码同样适用。
    - 多数改动编译器会报错：新关键字、`>>` 闭合两层模板、花括号初始化中的收窄、隐式删除的特殊成员、流不再能隐式转换成 `bool`。
    - 最需要人工检查的是不报错的改动：析构函数隐式 `noexcept`，抛出异常就调用 `std::terminate`；紧贴字符串字面量的宏不再展开；xvalue 的引入改变了 `typeid` 和 `?:` 的行为。
    - 库方面，`basic_string` 不再允许写时复制，所有容器的 `size()` 必须是常数时间。libstdc++ 为此在 GCC 5 中更换了 ABI。
    - Clang 把其中几条语言改动也用于 `-std=c++03` 模式，所以用旧模式编译并不总能复现旧行为。

Annex C 是资料性（informative）附录：它不创造规则，只指出正文哪里改了（见 [[diff]]）。每个条目都有固定的几项：受影响的正文条款、改了什么、为什么改、对原有代码的影响。下文用叙述的方式转述这些内容，并在 Clang 23.1.3 + libc++ 上分别用 `-std=c++03` 和 `-std=c++11` 编译附录的例子。

## 词法 {#diff.cpp03.lex}

### 新的字符串字面量前缀会吞掉宏

```cpp run std=c++17 title="u8macro.cpp" ok
#include <cstdio>
#define u8 "abc"
const char* s = u8"def";
int main() { std::puts(s); }
```

¶1 C++11 新增了编码前缀和原始字符串：`u8"…"`、`u"…"`、`U"…"`、`R"(…)"`，以及组合 `u8R`、`uR`、`UR`、`LR`。名字是这些前缀之一的宏，紧挨着字符串字面量时不再展开，而是成为字面量的一部分。上面的程序在 C++03 下输出 `abcdef`（宏展开后两个字面量拼接），在 C++11 到 C++17 下输出 `def`，而且没有任何诊断。

C++20 起 `u8"def"` 的类型变成 `const char8_t[4]`，这段代码会因为类型不匹配而报错（见 [[diff.cpp17]]）。

### 用户定义字面量会吞掉宏

¶2 C++11 起，字符串字面量后面紧跟一个标识符，整体构成一个记号：用户定义字面量（[[g:user-defined-literal]]）。原来这是两个记号，标识符若是宏就会展开。

```cpp run error
#include <cstdio>
#define _x "there"
int main() { std::puts("hello"_x); }   // error: 需要 operator""_x
```

C++03 下输出 `hellothere`。实际代码中最常见的情形是格式串写成 `"%"PRId64`，中间没有空格。Clang 在 C++11 下对它报错 `invalid suffix on literal; C++11 requires a space between literal and identifier`。改法是在字面量和宏之间加一个空格。

### 新关键字

¶3 C++11 新增的关键字有 `alignas`、`alignof`、`char16_t`、`char32_t`、`constexpr`、`decltype`、`noexcept`、`nullptr`、`static_assert`、`thread_local`。用它们作标识符的 C++03 代码不再合法。Clang 的 `-Wc++11-compat` 可以在 `-std=c++03` 下提前找出它们。

### 整数字面量的类型

¶4 C++11 沿用 C99 的规则：无后缀的十进制整数字面量依次尝试 `int`、`long`、`long long`，不会变成无符号类型。C++03 的规则只列出 `int` 和 `long`，放不下时行为未定义，实现普遍沿用 C90 的做法，取 `unsigned long`。附录说的就是这种从无符号类型变成 `long long` 的情形。

```cpp
// long 为 32 位的平台（ILP32、64 位 Windows）
2147483648    // C++03 实现：unsigned long；C++11：long long
-2147483648   // C++03 实现：unsigned long 的 2147483648
              // C++11：long long 的 -2147483648
```

用 `--target=i386-linux-gnu -std=c++03` 编译时，Clang 警告这个字面量在 C++98 中是未定义行为，它按 `unsigned long` 解释，C++11 起类型为 `long long`。受影响的主要是手写的 `INT_MIN` 一类常量。

## 表达式 {#diff.cpp03.expr}

### 只有字面量才是整数空指针常量

```cpp run ok
#include <cstdio>
void f(void*) { std::puts("#1"); }
void f(...)   { std::puts("#2"); }
template<int N> void g() {
  f(0*N);   // 现在调用 #2；C++03 调用 #1
}
int main() { g<0>(); }
```

¶1 C++03 中，任何值为 0 的整数常量表达式都是空指针常量，所以 `g<0>` 里的 `0*N` 可以转换为 `void*`，调用 #1。函数的行为因此取决于模板实参的值。C++11 规定整数空指针常量（[[g:null-pointer-constant]]）只能是值为 0 的整数字面量，`0*N` 不再算，于是调用 #2。

Clang 在 `-std=c++03` 下也输出 `#2`，它把这条改动用于所有语言模式。需要空指针时写 `nullptr`。

### xvalue 改变了 `typeid` 和条件运算符

C++11 引入了一种新的值类别 xvalue（[[g:xvalue]]）。右值类对象的成员，例如 `C().b`，现在是 xvalue，属于 glvalue。附录登记了这件事带来的两处行为变化。

```cpp run ok
#include <cstdio>
#include <typeinfo>
void f() {
  struct B {
    B() { std::puts("B()"); }
    virtual ~B() {}
  };
  struct C { B b; };
  (void)typeid(C().b);   // C++11 起求值操作数
}
int main() { f(); }
```

¶2 `typeid` 的操作数是多态类类型的 glvalue 时，要求值它以取得动态类型（[[expr.typeid]]）。`C().b` 在 C++03 中是右值，不求值；在 C++11 中是 xvalue，要求值，于是构造并销毁了一个 `C`。上面的程序在 C++03 下什么也不输出，在 C++11 下输出 `B()`，Clang 还会给出 `-Wpotentially-evaluated-expression` 警告。

¶5 条件运算符的第二、三个操作数是 xvalue 时，结果也可以是 xvalue，不再强制复制出一个临时对象（[[expr.cond]]）。附录的例子 `true ? BB().b : DD().d` 在 C++03 中会额外调用一次 `B` 的复制构造函数，在 C++11 中既不复制也不移动。给复制构造函数加上打印后，Clang 的 C++03 模式打印一次，C++11 模式不打印。只有依赖复制构造函数副作用的代码会受影响。

### 整数除法向零舍入

¶3 C++11 规定整数 `/` 的商向零舍入，`%` 的结果随之确定，这也是 C99 的规则。C++03 中，操作数有负数时向零还是向负无穷舍入由实现定义。在选择向负无穷舍入的实现上，`-7 / 2` 从 −4 变成 −3，`-7 % 2` 从 1 变成 −1。主流实现一直向零舍入，实际影响很小。

### `&&` 可以出现在类型名中

```cpp error
bool b1 = new int && false;           // error: new (int&&)
struct S { operator int(); };
bool b2 = &S::operator int && false;  // error: operator int&&
```

¶4 `&&` 在类型名中表示右值引用。C++03 把 `new int && false` 解析为 `(new int) && false`，结果为 `false`；现在 `int &&` 被当作 *new-type-id* 的一部分，分配引用类型，非良构。Clang 报 `cannot allocate reference type 'int &&' with new`。加括号即可。

## 声明 {#diff.cpp03.dcl.dcl}

### `auto` 不再是存储类说明符

¶1 `auto` 改为占位类型说明符，从初始化器推导变量类型（[[dcl.spec.auto]]）。C++03 的 `auto int x;` 不再合法。Clang 在 C++11 及以后的模式下只给警告 `-Wauto-storage-class`，加 `-pedantic-errors` 才报错。删掉 `auto` 即可。

### 聚合初始化中的收窄

```cpp error
int x[] = { 2.0 };   // error: double → int 是收窄转换
```

¶2 C++11 起，花括号初始化不允许收窄转换（[[g:narrowing-conversion]]），C++03 就有的聚合初始化也一样。这条规则用来捕获错误。Clang 报 `type 'double' cannot be narrowed to 'int' in initializer list`，它是一个错误，但可以用 `-Wno-c++11-narrowing` 关掉。大量 C 风格表格初始化的代码里可能有很多处，改法是写显式转换。

### 无名命名空间中的名字改为内部链接

```cpp ifndr
namespace { extern "C" { extern int x; } }  // #1
namespace A { extern "C" int x = 42; }      // #2
int main(void) { return x; }
```

¶3 C++11 把无名命名空间中声明的名字从外部链接改为内部链接，并规定语言链接（`extern "C"`）只作用于有外部链接的名字。这符合用户的预期：无名命名空间本来就是为了让名字只在本文件可见。

在 C++03 中，#1 和 #2 都有外部链接和 C 语言链接，是同一个变量。现在 #1 有内部链接和 C++ 语言链接，#2 不是它的定义，而 `main` 使用的 `x` 是 #1，它从未被定义，程序违反 ODR，不要求诊断（[[basic.def.odr]]）。Clang 在三种模式下都编译链接通过，程序返回 42，也就是仍把两者当作同一个变量。这在 IFNDR 程序上是允许的，但说明编译器不会帮你发现这个问题。实际代码中这种写法极少见。

## 类 {#diff.cpp03.class}

### 隐式特殊成员函数可以被定义为删除

```cpp error
struct S { int& r; };   // 引用成员：无法复制赋值
S* p;
int n = sizeof(*p = *p);  // error: 复制赋值被删除
```

¶1 隐式声明的默认构造函数、析构函数、复制构造函数和复制赋值运算符，如果隐式定义会是非良构的，C++11 起直接定义为删除（[[class.default.ctor]]、[[class.dtor]]、[[class.copy.ctor]]、[[class.copy.assign]]）。删除的函数在重载决议时就能被发现，模板实参推导因此可以干净地失败。

代价是：C++03 允许在不需要函数定义的地方使用它，比如上面 `sizeof` 的不求值操作数。现在被调用的是删除的函数，程序非良构。Clang 的 C++03 模式接受这段代码，C++11 模式报 `copy assignment operator is implicitly deleted`。

### 析构函数隐式 `noexcept`

```cpp run ok title="dtor_throw.cpp"
#include <cstdio>
struct D { ~D() { throw 1; } };
int main() {
  try { D d; } catch (...) { std::puts("caught"); }
}
```

¶2 用户声明的析构函数如果没有写异常说明，C++11 起与隐式声明的析构函数有相同的异常说明，通常是不抛出（[[except.spec]]）。从这样的析构函数抛出异常，会直接调用 `std::terminate`，`catch` 来不及处理。

上面的程序在 C++03 下输出 `caught`；在 C++11 下输出 `libc++abi: terminating due to uncaught exception of type int`，退出码 134。Clang 会给出警告 `'~D' has a non-throwing exception specification but can still throw`。这是升级时最需要检查的一条：确实要从析构函数抛出的，写 `~D() noexcept(false)`；否则改成不抛出。

## 模板 {#diff.cpp03.temp}

### `export` 改作模块之用

¶1 C++03 的导出模板（`export template<…>`）被删除，`export` 关键字在 C++20 中重新用于模块（[[module]]、[[cpp.module]]、[[cpp.import]]）。原来的 `export` 没有实现上的共识，只有 EDG 前端实现过。Clang 在 `-std=c++03` 和 `-std=c++11` 下对 `export template<class T> void f(T);` 只给警告 `exported templates are unsupported`，`-std=c++20` 下报错。删掉 `export` 即可。

### `>>` 可以闭合两层模板

<div class="compare" markdown="1">

```cpp error
template <class T> struct X { };
template <int N> struct Y { };
X< Y< 1 >> 2 > > x;
// error: >> 闭合了 Y 和 X
```

```cpp ok
template <class T> struct X { };
template <int N> struct Y { };
X< Y< (1 >> 2) > > x;
// OK：括号里的 >> 是右移
```

</div>

¶2 C++11 起，模板实参列表中的 `>>` 被当作两个 `>`，可以连续闭合两层模板，`vector<vector<int>>` 不再需要空格。这个空格要求长期被视为一个小麻烦，而别名模板出现后，非类类型的嵌套会更多。

代价是 C++03 中合法的右移表达式可能被误读。左边在 C++03 中是 `Y<(1 >> 2)>`，现在 `Y< 1 >>` 先闭合了两层，剩下的 `2 > > x` 无法解析。Clang 的 C++03 模式会用 `-Wc++11-compat` 提醒这里将来需要括号。

### 依赖调用可以找到内部链接的函数

```cpp run ok
#include <cstdio>
template<class T> void call(T t) { g(t, 0); }
namespace N {
  struct S {};
  void g(S, long) { std::puts("long"); }
  static void g(S, int) { std::puts("int"); }
}
int main() { call(N::S()); }   // 输出 int
```

¶3 C++03 中，模板实例化点上的依赖调用经实参依赖查找只能找到有外部链接的函数，上例只能调用 `g(S, long)`。C++11 去掉了这个限制，内部链接的 `g(S, int)` 也参与重载决议，而且是更好的匹配（[[temp.dep.candidate]]）。Clang 在 `-std=c++03` 下同样输出 `int`。

## 标准库

库条目大多是签名和要求的调整，旧代码要么编译失败，要么在极少数情况下行为不同。

### 名字、头文件与宏 {#diff.cpp03.library}

¶1 后来加入标准库的所有标识符都可能与 C++03 代码冲突。典型情形是 `using namespace std;` 之后自己定义了 `bind`、`function`、`array`、`move`、`begin`，与 `std` 中新增的同名设施发生歧义，或者被实参依赖查找选中。去掉 `using namespace std;` 是最彻底的改法。

¶2 新增的 C++ 头文件有 `<array>`、`<atomic>`、`<chrono>`、`<condition_variable>`、`<forward_list>`、`<future>`、`<initializer_list>`、`<mutex>`、`<random>`、`<ratio>`、`<regex>`、`<scoped_allocator>`、`<system_error>`、`<thread>`、`<tuple>`、`<typeindex>`、`<type_traits>`、`<unordered_map>`、`<unordered_set>`；新增的 C 兼容头文件有 `<cfenv>`、`<cinttypes>`、`<cstdint>`、`<cuchar>`。自己写了同名头文件的代码可能失效（[[headers]]）。

¶3 `std::swap` 从 `<algorithm>` 移到了 `<utility>`（[[swappable.requirements]]）。只包含 `<algorithm>` 就使用 `swap` 的代码，在某些实现上要改为包含 `<utility>`。

¶4 全局命名空间 `posix` 保留给将来的标准化（[[namespace.posix]]）。

¶5 属性名不能再用作宏名，定义了 `override`、`final` 或 `noreturn` 宏的 C++03 代码不再合法（[[macro.names]]）。当前草案已把这条规则移到预处理一章（[[cpp.replace.general#9]]），并随契约加入了 `pre`、`post`（[[diff.cpp23]]）。Clang 23 对 `#define override` 只给警告，对 `#define noreturn` 没有诊断。

### `operator new` 的异常说明 {#diff.cpp03.language.support}

¶1 全局 `operator new` 的声明去掉了 `throw(std::bad_alloc)`，这是为了统一使用 `noexcept`（[[new.delete.single]]）。替换后的 `operator new` 可能抛出别的异常，假设它只会抛 `std::bad_alloc` 的代码可能行为不同。用 `throw(std::bad_alloc)` 声明替换版本的代码，按附录的说法现在非良构。C++17 起任何带类型的动态异常说明都非良构，Clang 在 C++03 和 C++11 下接受这样的声明，C++17 起报错。

### 线程局部的 `errno` {#diff.cpp03.diagnostics}

¶1 `errno` 是线程局部的，以支持新的线程设施（[[errno]]）。依赖各线程共享同一个 `errno` 的代码本来就是实现特定的，现在行为可能改变。

### 函数对象的基类 {#diff.cpp03.utilities}

¶1 `std::plus`、`std::less`、`std::reference_wrapper` 等标准函数对象不再派生自 `std::unary_function` 或 `std::binary_function`（[[refwrap]]、[[arithmetic.operations]]、[[comparisons]]、[[logical.operations]]、[[bitwise.operations]]）。这两个基类已被新特性取代，C++17 起不再定义（[[diff.cpp14]]）。依赖这种派生关系的代码会编译失败。

### `basic_string` 不再允许写时复制 {#diff.cpp03.strings}

¶1 对 `basic_string` 的要求不再允许引用计数（写时复制，COW）的实现（[[string.classes]]）。引用计数字符串的迭代器失效规则与其他实现有微妙差别，这一改动让行为统一。C++11 的数据竞争规则也与 COW 冲突：非 `const` 的 `operator[]` 需要先解除共享，这是一次隐藏的写操作。

GCC 的 libstdc++ 原本是 COW 实现。为了遵守这条，它在 GCC 5 中引入了新的 `std::__cxx11::basic_string`，与旧 ABI 不兼容，由 `_GLIBCXX_USE_CXX11_ABI` 宏选择。

¶2 `data`、`c_str` 等一些 `const` 成员函数不再使迭代器失效（[[string.require]]）。这一放宽是为了允许短字符串优化（SSO）。

### 容器 {#diff.cpp03.containers}

¶1 所有提供 `size()` 的容器，`size()` 都必须是常数时间（[[container.requirements]]）。C++03 没有规定它的复杂度，各实现的性能特征不一致。`std::list` 为此必须维护一个计数器，这改变了它的布局，`splice` 一段区间也从常数时间变成线性时间。libstdc++ 的 `std::list` 因此同样随 C++11 ABI 改变。

¶2 容器要求有几处放宽，想在各种容器上通用的 C++03 代码可能要调整：`forward_list` 没有 `size()`，判空要用 `empty()`；`array` 构造后不是空的；`array` 的 `swap()` 不是常数时间。

¶3 容器各成员函数对元素类型的要求被逐一细化，例如只有 `resize(n)` 这类函数要求元素可默认构造。显式实例化 `template class std::vector<NoDefault>;` 会实例化所有成员，元素类型没有默认构造函数时可能编译失败。

¶4 以下成员函数原来返回 `void`，现在返回迭代器（[[sequence.reqmts]]、[[associative.reqmts]]）：`set`、`multiset`、`map`、`multimap` 的 `erase(iter)` 和 `erase(begin, end)`；`vector`、`deque`、`list`、`forward_list` 的 `insert(pos, num, val)` 和 `insert(pos, beg, end)`。依赖返回类型的代码，例如取这些函数的成员函数指针，会编译失败。

¶5 以下成员函数的迭代器形参从 `iterator` 改为 `const_iterator`：各序列容器和关联容器的 `insert(iter, val)`、序列容器的 `insert(pos, beg, end)`、关联容器的 `erase(begin, end)`，以及 `list::splice` 和 `list::merge` 的所有形式。插入位置只用于定位，不需要可变迭代器。直接调用不受影响，取成员函数指针的代码可能编译失败。

¶6 `vector`、`deque`、`list` 的 `resize` 的填充值从按值传递改为按引用传递，并增加了单参数重载 `resize(n)`，以配合移动语义。取 `resize` 成员函数指针的代码可能编译失败。

### 算法改用移动 {#diff.cpp03.algorithms}

```cpp run ok
#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>
int main() {
  std::vector<std::string> v;
  v.push_back("a string too long for SSO, #1");
  v.push_back("x");
  v.push_back("a string too long for SSO, #2");
  (void)std::remove(v.begin(), v.end(),
                    std::string("x"));
  for (std::size_t i = 0; i != v.size(); ++i)
    std::printf("[%s]\n", v[i].c_str());
}
```

¶1 算法改用移动而不是复制（[[algorithms.general]]）。被移走或留在尾部的对象原本处于有效但未指定的状态，现在可能处于另一种有效但未指定的状态。上例中，libc++ 在 C++03 模式下尾部元素是 `#2` 的副本，C++11 模式下是被移走后的空字符串。读取 `remove` 之后尾部元素的代码，本来就依赖了未指定的值。

### 复数的表示 {#diff.cpp03.numerics}

¶1 `complex<float>`、`complex<double>`、`complex<long double>` 的表示被规定为两个元素的数组，依次是实部和虚部，与 C99 的 `_Complex` 兼容（[[complex.numbers]]）。依赖某个实现特有二进制表示的代码可能不再兼容。主流实现本来就是这种布局。

### `num_get` 识别十六进制浮点数 {#diff.cpp03.locale}

¶1 `num_get` 刻面解析浮点数时识别十六进制格式（[[facet.num.get.virtuals]]）。C++03 中从 `"0x1p3"` 读 `double` 会在 `x` 处停止，得到 0；现在可能得到 8。libc++ 在两种模式下都得到 8。

### iostream {#diff.cpp03.input.output}

```cpp error
#include <iostream>
bool ok() { return std::cin; }  // error
bool e = std::cin == false;     // error
```

¶1 流和 sentry 的布尔转换从 C++03 的 `operator void*()` 改为 `explicit operator bool()`（[[istream.sentry]]、[[ostream.sentry]]、[[iostate.flags]]）。依赖隐式转换的代码会编译失败，附录列了五种情形：把流传给接受 `bool` 的函数；用 `==` 与 `true` 或 `false` 比较；从返回 `bool` 的函数中返回流；用聚合初始化给 `bool` 成员赋流；用流初始化一个会绑定到临时对象的 `const bool&`。

`if (std::cin)`、`while (in >> x)`、`!std::cin` 是按语境转换为 `bool`，不受影响。上面的代码在 Clang 的 C++03 模式下通过，C++11 下两处都报错。改写为 `return !std::cin.fail();` 或 `static_cast<bool>(std::cin)`。

¶2 `std::ios_base::failure` 不再直接派生自 `std::exception`，而是派生自 `std::system_error`，后者派生自 `std::runtime_error`（[[ios.failure]]）。这样可以携带更详细的错误码。现在 `catch (std::runtime_error&)` 也能捕获它，依赖原有继承关系的代码可能行为不同。

```cpp
#include <iostream>
int main() {
  int flag = std::ios_base::hex;
  std::cout.setf(flag);   // 可能非良构
}
```

¶3 `ios_base` 的标志类型 `fmtflags`、`iostate`、`openmode`、`seekdir` 是位掩码类型，各个值定义为 `constexpr static` 成员（[[ios.base]]）。假设它们是整数或 `std::bitset` 的代码可能编译失败。上面的例子在 libc++ 上能编译，因为 libc++ 的 `fmtflags` 是 `unsigned int`；在用枚举实现 `fmtflags` 的库（如 libstdc++）上会报错。变量改用 `std::ios_base::fmtflags` 类型即可。

## 小结

| 条目 | 结果 | Clang 23 的表现 |
|---|---|---|
| 名为 `u8` 等前缀的宏 | 行为静默改变 | 按新规则 |
| `"hello"_x` | 非良构 | 按新规则 |
| 整数字面量类型 | 类型改变 | 按新规则 |
| `0*N` 不再是空指针常量 | 调用不同的重载 | 旧模式也按新规则 |
| `typeid`、`?:` 与 xvalue | 行为静默改变 | 按新规则 |
| `new int && false` | 非良构 | 按新规则 |
| `auto int x;` | 非良构 | 只警告 |
| 收窄 | 非良构 | 按新规则 |
| 无名命名空间的链接 | IFNDR | 行为与旧规则相同 |
| 隐式删除的特殊成员 | 非良构 | 按新规则 |
| 析构函数隐式 `noexcept` | 抛异常时 terminate | 按新规则，有警告 |
| `export template` | 非良构 | C++20 前只警告 |
| `>>` | 非良构 | 按新规则 |
| 依赖调用找到内部链接函数 | 调用不同的重载 | 旧模式也按新规则 |
| 流的 `explicit operator bool` | 非良构 | 按新规则 |
| `fmtflags` 的类型 | 可能非良构 | libc++ 不受影响 |

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 [diff.cpp03.general] 说明这一节按本文档的章节列出 C++ 与 ISO C++ 2003 的差异，并且是在前面各节（C.1 到 C.6）所列差异之外的部分。

</details>
