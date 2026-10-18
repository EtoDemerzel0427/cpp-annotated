---
title: C++ 与 ISO C++ 2014 的差异
summary: Annex C.5：从 C++14 升级到 C++17 会遇到的 19 条不兼容——三字符组删除、pp-number 吸收 p±、bool 自增与 register 删除、auto x{1} 推导改变、noexcept 进入类型系统、带基类的聚合、继承构造函数语义改变、从常量模板实参的类型推导、动态异常说明删除，以及 auto_ptr、bind1st、random_shuffle 等库删除。逐条给出前后对比与 Clang 23 / libc++ 实测。
status: draft
covers: *
related: diff, diff.cpp17, diff.cpp11, lex.phases, dcl.spec.auto, except.spec, dcl.init.aggr, class.inhctor.init
tags: 附录, 兼容性, 迁移, C++17
updated: 2026-10-18
---

[diff.cpp14] 列出 C++14 → C++17 这一步引入的不兼容。C++17 的主题之一是**清理**：三字符组、`register`、`bool` 的 `++`、动态异常说明、`auto_ptr` 这些弃用多年的东西在这一版被删除。另一个主题是**类型系统更精确**：`noexcept` 成为函数类型的一部分，这一条对模板代码影响最大。

不少条目（`auto x{1}`、继承构造函数）是以 DR 形式被编译器回溯到旧模式的，实测中切换 `-std=` 看不到差别，下文逐条注明。

实测环境：Clang 23.1.3 + libc++，对比 `-std=c++14` 与 `-std=c++17`。

¶1 [diff.cpp14.general]：本小节列出与 ISO C++ 2014 的差异，是在前面各小节所列差异**之外**的部分。

## Clause [lex]：词法约定 {#diff.cpp14.lex}

### ¶1 不再要求支持三字符组

**受影响小节**：[[lex.phases]]

**改动**：删除**三字符组**（[[g:trigraph]]，如 `??=` 表示 `#`、`??/` 表示 `\`）作为必须支持的特性。

**理由**：防止在非原始字符串字面量和注释中意外触发三字符组替换。经典的坑是 `// 这是什么??/` 这样的注释：`??/` 变成 `\`，把下一行也并进了注释。

**影响**：使用三字符组的 C++14 代码可能无效或含义改变。实现可以在把源文件字符映射到翻译字符集的那一步（实现定义）继续翻译原始字符串字面量之外的三字符组。

```cpp
const char* s = "??=";   // C++14："#"；现在："??="
```

**Clang 23 实测**：

```text
$ clang++ -std=c++14 ...
warning: trigraph converted to '#' character [-Wtrigraphs]
$ clang++ -std=c++17 ...
warning: trigraph ignored [-Wtrigraphs]
```

**改写难度**：容易。需要三字符组的平台（EBCDIC）用编译器选项（Clang/GCC 的 `-trigraphs`）。

### ¶2 *pp-number* 可以包含 `p` *sign* 和 `P` *sign*

**受影响小节**：[[lex.ppnumber]]

**改动**：预处理数（[[g:pp-number]]）的文法增加 `p+`、`p-`、`P+`、`P-`，以支持十六进制浮点字面量 `0x1p+3`。

**影响**：`0p+0`、`0e1_p+0` 这样的字符序列在 C++14 中是三个预处理记号，现在是一个。和 `##` 一起用时结果不同：

```cpp error
#define F(a) b ## a
int b0p = F(0p+0);   // 现在：b ## 0p+0 → 非法记号，非良构；C++14："int b0p = b0p + 0;"
```

**Clang 23 实测**：`-std=c++17` 下仍然按 C++14 的方式处理（只有以 `0x` 开头的数才吸收 `p±`），展开为 `int b0p = b0p+0;` 并给出"变量在自身初始化中使用"的警告。即 Clang 在这一点上没有完全实现标准的 *pp-number* 文法。

**改写难度**：容易。实际中几乎不会碰到。

## Clause [expr]：表达式 {#diff.cpp14.expr}

### ¶1 删除对 `bool` 操作数的自增

**受影响小节**：[[expr.post.incr]] 与 [[expr.pre.incr]]

**改动**：`++b`、`b++` 对 `bool` 左值非良构（`--` 本来就不允许）。

**理由**：过时的特性，语义时常令人意外（`b++` 总是把 `b` 设成 `true`）。

```cpp error
bool b = false;
void f() { ++b; b++; }   // error: 现在非良构
```

**Clang 23 实测**：

```text
$ clang++ -std=c++14 ...
warning: incrementing expression of type bool is deprecated and incompatible with C++17 [-Wdeprecated-increment-bool]
$ clang++ -std=c++17 ...
error: ISO C++17 does not allow incrementing expression of type bool [-Wincrement-bool]
```

**改写难度**：容易。`++b` → `b = true`；`b++` 作为表达式 → `std::exchange(b, true)`。

### ¶2 过度对齐类型的动态分配

**受影响小节**：[[expr.new]] 与 [[expr.delete]]

**改动**：用 *new-expression* 分配**过度对齐**（alignment 大于 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`）的类类型对象时，如果该类没有自己的分配函数，C++14 调用 `::operator new(std::size_t)`，现在调用 `::operator new(std::size_t, std::align_val_t)`。

**理由**：简化过度对齐类型的使用。C++14 中 `new` 一个 `alignas(64)` 的类型不保证得到 64 字节对齐的内存。

**影响**：替换了全局 `operator new(size_t)` 的程序，在 C++17 下对过度对齐类型不再走自己的分配函数，而是走标准库的对齐版本（除非一并替换对齐版本）。内存统计、内存池之类的代码会漏掉这部分分配。

**改写难度**：中等。替换全局分配函数时，同时替换带 `std::align_val_t` 的各个版本（单对象/数组、`nothrow`、带大小的 `delete`，见 [[new.delete]]）。

## Clause [dcl]：声明 {#diff.cpp14.dcl.dcl}

### ¶1 删除 `register` 存储类说明符

**受影响小节**：[[dcl.stc]]

**改动**：`register` 不再是存储类说明符（它仍然是保留的关键字）。

**理由**：为将来改作他用而腾出这个已弃用的关键字。

**Clang 23 实测**：

```text
$ clang++ -std=c++14 ...
warning: 'register' storage class specifier is deprecated and incompatible with C++17 [-Wdeprecated-register]
$ clang++ -std=c++17 ...
error: ISO C++17 does not allow 'register' storage class specifier [-Wregister]
```

**改写难度**：容易，删掉 `register`，含义不变。注意 C 头文件里的 `register`：被 C++ 代码包含时同样报错。

### ¶2 从花括号初始化列表推导 `auto`

**受影响小节**：[[dcl.spec.auto]]

**改动**：直接列表初始化 `auto x{…}` 时，花括号里只能有一个元素，`auto` 推导为该元素的类型；C++14 推导为 `std::initializer_list`。复制列表初始化 `auto x = {…}` 不变，仍然推导为 `initializer_list`。

**理由**：更直观的推导结果。

```cpp
auto x1{1};      // C++14：std::initializer_list<int>；现在：int
auto x2{1, 2};   // C++14：std::initializer_list<int>；现在：非良构
auto x3 = {1};   // 两者都是 std::initializer_list<int>
```

**Clang 23 实测**：`-std=c++14` 下 `decltype(x1)` 就已经是 `int`，`x2` 也报 `initializer for variable 'x2' with type 'auto' contains multiple expressions`。这条改动是以 DR 形式回溯的，Clang 在 C++11/14 模式下也用新规则。

**改写难度**：容易。

### ¶3 异常说明成为类型系统的一部分

**受影响小节**：[[dcl.fct]]

**改动**：`noexcept` 成为函数类型的一部分：`void() noexcept` 与 `void()` 是不同的类型。指向 `noexcept` 函数的指针可以隐式转换为指向普通函数的指针，反之不行。

**理由**：提高类型安全。

**影响**：模板推导中，两个实参分别是 `noexcept` 和非 `noexcept` 的函数时，推出的类型不再相同：

```cpp error
void g1() noexcept;
void g2();
template<class T> int f(T*, T*);
int x = f(g1, g2);   // error: 现在 T 推导冲突；C++14 良构
```

此外，以函数类型为键的特化（`std::function` 之外的手写类型擦除、成员函数指针的 traits）需要为 `noexcept` 版本额外提供特化；名字修饰也变了，`noexcept` 函数指针作为形参的函数在 C++14 和 C++17 中有不同的符号名。

**Clang 23 实测**：C++14 下通过，C++17 下 `no matching function for call to 'f'`。

**改写难度**：中等。traits 类要加 `noexcept` 特化（`R(Args...) noexcept`）；推导冲突处显式指定模板实参。

### ¶4 聚合可以有基类

**受影响小节**：[[dcl.init.aggr]]

**改动**：聚合的定义扩展到有（公有、非虚）基类的类。

**理由**：增加聚合初始化的便利性。

**影响**：对这类类型，空的花括号初始化 `T{}` 从"调用默认构造函数"变成"聚合初始化"，而聚合初始化要逐个初始化基类，此时访问检查在**初始化处**进行：

```cpp
struct derived;
struct base {
  friend struct derived;
private:
  base();
};
struct derived : base {};

derived d1{};   // error: 现在聚合初始化 base 子对象，在此处 base() 不可访问；C++14 良构
derived d2;     // 仍然 OK：调用 derived 的隐式默认构造函数，它是 base 的友元
```

**Clang 23 实测**：C++17 下 `base class 'base' has private default constructor`。

**改写难度**：容易。用 `derived d1;` 或给 `derived` 声明一个构造函数（但那样它就不是聚合了，参见 [[diff.cpp17]] [dcl] ¶3）。

## Clause [class]：类 {#diff.cpp14.class}

### ¶1 继承构造函数不再向派生类注入构造函数

**受影响小节**：[[class.inhctor.init]]

**改动**：命名构造函数的 *using-declaration* 不再在派生类中**声明**一组新的构造函数，而是让基类的构造函数在派生类的初始化中**可见**。

**理由**：与其他语言特性更好地交互（默认实参、模板、访问控制、`explicit` 等在"注入的构造函数"模型下都有各种怪异表现）。

```cpp
struct A {
  template<typename T> A(T, typename T::type = 0);
  A(int);
};
struct B : A {
  using A::A;
  B(int);
};
B b(42L);   // 现在：调用 B(int)
            // C++14：调用注入的 B<long>(long)，它再调用 A(int)（因为 A<long>(long) 替换失败）
```

C++14 的注入模型下，`using A::A` 为 `A` 的构造函数模板生成了一个 `B` 的构造函数模板 `template<class T> B(T)`（默认实参不随之注入），`B<long>(long)` 对 `42L` 是精确匹配，胜过需要转换的 `B(int)`。现在继承的构造函数模板以 `A` 的原样参与决议，`A<long>` 因 `long::type` 替换失败被排除，只剩 `A(int)` 和 `B(int)`，后者胜出（派生类自己的构造函数隐藏同签名的继承构造函数）。

**Clang 23 实测**：给两个构造函数加打印，`-std=c++14` 和 `-std=c++17` 都输出 `A(int) B(int)`，即调用 `B(int)`。新语义被回溯到了所有模式。

**改写难度**：需人工审查，但实际受影响的代码很少。

## Clause [temp]：模板 {#diff.cpp14.temp}

### ¶1 可以从常量模板实参的类型进行推导

**受影响小节**：[[temp.deduct.type]]

**改动**：在 `template<typename T, T N>` 中，从 `A<N>` 推导时，`T` 也可以由 `N` 的类型推出。

**理由**：配合 `auto` 常量模板形参，让偏特化能拆解出常量模板实参的类型。

```cpp error
template <int N> struct A;
template <typename T, T N> int foo(A<N>*) = delete;
void foo(void*);
void bar(A<0>* p) {
  foo(p);   // error: 现在推出 T = int、调用被删除的模板；C++14 中 T 不可推导，调用 foo(void*)
}
```

**Clang 23 实测**：C++14 下通过，C++17 下 `call to deleted function 'foo'`。

**改写难度**：容易。

## Clause [except]：异常处理 {#diff.cpp14.except}

### ¶1 删除动态异常说明

**受影响小节**：[[except.spec]]

**改动**：删除可能抛出的**动态异常说明**（[[g:dynamic-exception-specification]]）`throw(T1, T2, …)`。`throw()` 暂时保留为 `noexcept` 的同义词（C++20 也删除了，见 [[diff.cpp17]] [except] ¶1）。

**理由**：动态异常说明是复杂而脆弱的弃用特性，与类型系统交互不良；在 `noexcept` 成为函数类型一部分之后，这个问题更严重。

**影响**：带 `throw(T)` 的声明非良构。违反 `throw()` 时，改为调用 `std::terminate` 而不是 `std::unexpected`，并且调用之前是否进行栈展开是未指定的。

```cpp error
void g() throw(int);   // error: 现在非良构
```

**Clang 23 实测**：C++14 下通过（加 `-Wdeprecated` 才警告），C++17 下 `ISO C++17 does not allow dynamic exception specifications [-Wdynamic-exception-spec]`。

**改写难度**：容易。`throw(…)` 直接删掉；`throw()` 改为 `noexcept`。

## Clause [library]：库引言 {#diff.cpp14.library}

### ¶1 新头文件

**受影响小节**：[[headers]]

`<any>`、`<charconv>`、`<execution>`、`<filesystem>`、`<memory_resource>`、`<optional>`、`<string_view>`、`<variant>`。

### ¶2 新的保留命名空间

**受影响小节**：[[namespace.future]]

**改动**：全局命名空间中 `std` 后跟任意数字序列的名字（`std1`、`std2`、…）保留给将来的标准化。

**改写难度**：容易。

## Clause [utilities]：通用工具库 {#diff.cpp14.utilities}

### ¶1 删除 `std::function` 接受分配器的构造函数

**受影响小节**：[[func.wrap]]

**理由**：没有实现共识，各库的支持参差不齐。

**影响**：用分配器构造 `std::function` 非良构；*uses-allocator* 构造不再向 `std::function` 的构造函数传递分配器。

**改写难度**：容易。

### ¶2 从 `unique_ptr` 转换到 `shared_ptr` 的约束改变

**受影响小节**：[[util.smartptr.shared]]

**改动**：为支持 `shared_ptr<T[]>` 和 `shared_ptr<T[N]>`，`shared_ptr(unique_ptr<Y, D>&&)` 的约束改为要求 `unique_ptr<Y, D>::pointer` 可以转换为 `shared_ptr` 的 `element_type*`。

```cpp error
#include <memory>
std::unique_ptr<int[]> arr(new int[1]);
std::shared_ptr<int> ptr(std::move(arr));   // error: int(*)[] 与 int* 不兼容
```

**libc++ 实测**：C++14 和 C++17 下都报 `no matching constructor`。

**改写难度**：容易。改用 `std::shared_ptr<int[]>`。

## Clause [strings]：字符串库 {#diff.cpp14.string}

### ¶1 增加非 const 的 `data()`

**受影响小节**：[[basic.string]]

**改动**：`basic_string` 增加 `charT* data() noexcept` 非 const 重载。

**理由**：与 `std::vector::data()` 保持一致。

**影响**：对非 const 字符串调用 `data()`，返回 `char*` 而不是 `const char*`，传给分别重载了 `char*` / `const char*` 的函数时走不同的分支：

```cpp error
int f(char*) = delete;
int f(const char*);
std::string s;
int x = f(s.data());   // error: 现在选中被删除的 f(char*)；C++14 良构
```

**libc++ 实测**：C++17 下 `call to deleted function 'f'`。

**改写难度**：容易。需要 `const char*` 时用 `s.c_str()` 或 `std::as_const(s).data()`。

## Clause [containers]：容器库 {#diff.cpp14.containers}

### ¶1 关联容器的比较对象要求

**受影响小节**：[[associative.reqmts]]

**改动**：要求变更：比较对象的函数调用运算符必须能在 `const` 比较对象上调用。

**理由**：提高可移植性，澄清关联容器的要求。

```cpp error
#include <set>
struct compare {
  bool operator()(int a, int b) { return a < b; }   // 非 const
};
int main() {
  const std::set<int, compare> s;
  s.find(0);   // 现在可能编译失败
}
```

**libc++ 实测**：C++14 和 C++17 下都报 `no matching function for call to object of type 'const compare'`，并附有库自定义的警告 `the specified comparator type does not provide a viable const call operator`。

**改写难度**：容易，给 `operator()` 加 `const`。

## Annex [depr]：兼容性特性 {#diff.cpp14.depr}

### ¶1 删除 `auto_ptr`、`unary_function`、`binary_function`、`random_shuffle`、`ptr_fun`、`mem_fun`、`mem_fun_ref`、`bind1st`、`bind2nd`

**理由**：已被新特性取代。

| 删除项 | 替代 |
|---|---|
| `auto_ptr` | `unique_ptr` |
| `unary_function` / `binary_function` | 不需要基类；需要类型时用 `invoke_result_t` |
| `random_shuffle` | `std::shuffle(first, last, urbg)` |
| `ptr_fun` | 直接传函数指针或 lambda |
| `mem_fun` / `mem_fun_ref` | `std::mem_fn` |
| `bind1st` / `bind2nd` | lambda 或 `std::bind` / `std::bind_front` |

**libc++ 实测**：

```text
$ clang++ -std=c++14 ...
warning: 'auto_ptr<int>' is deprecated [-Wdeprecated-declarations]
warning: 'random_shuffle<std::__wrap_iter<int *>>' is deprecated [-Wdeprecated-declarations]
warning: 'bind1st<std::plus<int>, int>' is deprecated [-Wdeprecated-declarations]
$ clang++ -std=c++17 ...
error: no template named 'auto_ptr' in namespace 'std'
error: no member named 'random_shuffle' in namespace 'std'
error: no member named 'bind1st' in namespace 'std'
```

**改写难度**：`auto_ptr` → `unique_ptr` 通常是机械替换，但要注意 `auto_ptr` 的"复制即转移"语义：原来 `a = b` 悄悄转移所有权的地方要改成 `a = std::move(b)`，编译器会帮你找出这些地方。

### ¶2 删除旧的 iostreams 成员

**改动**：删除 [depr.ios.members] 中的成员：`ios_base::io_state`、`open_mode`、`seek_dir` 类型，以及 `streamoff`、`streampos` 成员类型别名等为兼容标准化之前的代码而保留的名字。

**理由**：为兼容标准化之前的代码而保留的冗余特性，已经完成了历史使命。

**改写难度**：容易。改用 `iostate`、`openmode`、`seekdir`。

## 小结

| 条目 | 类型 | Clang 23 / libc++ |
|---|---|---|
| 三字符组 | 改变含义 | 已实现 |
| *pp-number* 吸收 `p±` | 非良构 / 改变含义 | **未实现** |
| `bool` 自增 | 非良构 | 已实现 |
| 过度对齐 `new` | 调用不同分配函数 | 已实现 |
| `register` | 非良构 | 已实现 |
| `auto x{1}` | 改变类型 | 已实现并回溯到 C++11 |
| `noexcept` 进入类型 | 非良构 / 改变修饰名 | 已实现 |
| 聚合可有基类 | 非良构 / 改变含义 | 已实现 |
| 继承构造函数 | 改变调用 | 已实现并回溯 |
| 从常量实参类型推导 | 非良构 | 已实现 |
| 动态异常说明 | 非良构 | 已实现 |
| `std::function` 分配器 | 非良构 | — |
| `unique_ptr<T[]>` → `shared_ptr<T>` | 非良构 | 两种模式都拒绝 |
| 非 const `data()` | 调用不同重载 | 已实现 |
| 非 const 比较器 | 非良构 | 两种模式都拒绝 |
| Annex D 删除项 | 非良构 | 已删除 |
