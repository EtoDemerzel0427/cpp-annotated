---
title: C++ 与 ISO C++ 2014 的差异
summary: 从 C++14 升级到 C++17 时，哪些原来合法的代码会报错或改变行为：三字符组、pp-number 吸收 p±、bool 自增与 register 删除、auto x{1} 的推导、noexcept 进入函数类型、带基类的聚合、继承构造函数的新语义、动态异常说明删除，以及 auto_ptr、bind1st、random_shuffle 等库设施的删除。
status: done
covers: *
related: diff, diff.cpp17, diff.cpp11, lex.phases, dcl.spec.auto, except.spec, dcl.init.aggr, class.inhctor.init
tags: 附录, 兼容性, 迁移, C++17
updated: 2026-10-19
---

!!! tldr
    - C++17 删除了一批过时的语言特性：三字符组、`register`、对 `bool` 的 `++`、`throw(int)` 这样的动态异常说明。
    - `noexcept` 成为函数类型的一部分，`void() noexcept` 和 `void()` 是两个类型。模板推导、类型特征的特化和名字修饰都受影响。
    - `auto x{1};` 推导为 `int` 而不是 `std::initializer_list<int>`；带公有基类的类也可以是聚合，`T{}` 可能从调用默认构造函数变成聚合初始化。
    - `new` 一个过度对齐的类型时，改为调用带 `std::align_val_t` 的分配函数，只替换了 `operator new(size_t)` 的内存统计代码会漏掉这部分分配。
    - 库删除了 `auto_ptr`、`random_shuffle`、`bind1st`、`bind2nd`、`ptr_fun`、`mem_fun` 等，各有直接的替代品。

[diff.cpp14] 列出 C++17 相对 C++14 的不兼容：原来良构的代码，在 C++17 中变成非良构，或者含义改变。每一条在标准里都写成同样的格式：受影响的条款、改了什么、为什么改、对旧代码有什么影响。

¶1 这一节列的是在前面各节之外的差异：从 C++14 升级到当前草案，还要再看 [[diff.cpp17]] 及之后各节。条目按正文的章节顺序排列。文中的实测都用本机 Clang 23.1.3 + libc++，对比 `-std=c++14` 与 `-std=c++17`。有几条被编译器当作缺陷修正，在 `-std=c++14` 下也已是新行为，下文逐条注明。

## 词法约定 [diff.cpp14.lex] {#diff.cpp14.lex}

### 不再要求支持三字符组

```cpp
const char* s = "??=";   // C++17："??="；C++14："#"
```

¶1 **三字符组**（[[g:trigraph]]）是 `??` 开头的三个字符，在翻译的最早阶段被替换成一个字符，例如 `??=` 换成 `#`，`??/` 换成 `\`。它是为了在缺少某些字符的老式键盘和字符集上书写 C 程序而设计的。C++17 不再要求支持它（[[lex.phases]]）。

删除的理由是它经常在字符串和注释里意外生效。经典的例子是注释 `// 这是什么??/`：`??/` 变成 `\`，把下一行代码也并进了注释。实现仍然可以在把源文件字符映射到翻译字符集时（这一步由实现定义）继续替换原始字符串字面量之外的三字符组，所以确实需要三字符组的平台（如 EBCDIC）可以用编译器选项打开，Clang 和 GCC 用 `-trigraphs`。

本机 Clang 23 在 `-std=c++14` 下把上例替换成 `#` 并给出警告，`-std=c++17` 下保留 `??=` 并提示 trigraph ignored。

### 预处理数可以包含 `p+`、`p-`

```cpp error
#define F(a) b ## a
int b0p = F(0p+0);   // error: C++14 中等价于 int b0p = b0p + 0;
```

¶2 预处理阶段的数字记号叫**预处理数**（[[g:pp-number]]），它的文法很宽松，比真正的数字字面量能吃进更多字符。为了支持十六进制浮点字面量 `0x1p+3`，C++17 让预处理数可以包含 `p+`、`p-`、`P+`、`P-`（[[lex.ppnumber]]）。于是 `0p+0`、`0e1_p+0` 这样的字符序列在 C++14 中是三个记号，在 C++17 中是一个。

上例中，C++14 把实参分成 `0p`、`+`、`0`，`b ## 0p` 拼成 `b0p`，得到 `int b0p = b0p + 0;`。C++17 中实参是一个记号 `0p+0`，拼成的 `b0p+0` 不是合法的记号，程序非良构。实际代码中几乎不会碰到。

Clang 23 没有完全实现这条：`-std=c++17` 下仍然只对 `0x` 开头的数吸收 `p+`，把上例展开成 `int b0p = b0p+0;`。

## 表达式 [diff.cpp14.expr] {#diff.cpp14.expr}

### 删除对 `bool` 的自增

```cpp error
bool b = false;
void f() { ++b; b++; }   // error: C++14 中良构
```

¶1 C++17 不再允许对 `bool` 使用 `++`（[[expr.post.incr]]、[[expr.pre.incr]]），`--` 本来就不允许。`b++` 的效果总是把 `b` 设成 `true`，这个语义令人意外，又早已过时。`++b` 改成 `b = true`，用到返回值的 `b++` 改成 `std::exchange(b, true)`。

Clang 23 在 `-std=c++14` 下给出 `-Wdeprecated-increment-bool` 警告，`-std=c++17` 下报错。

### 过度对齐类型的动态分配

```cpp run title="overaligned.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>
void* operator new(std::size_t n) {
  std::puts("operator new(size_t)");
  return std::malloc(n);
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct alignas(64) V { char c; };
int main() {
  V* v = new V;
  std::printf("%lu\n", reinterpret_cast<unsigned long>(v) % 64);
  delete v;
}
```

¶2 对齐要求超过 `__STDCPP_DEFAULT_NEW_ALIGNMENT__`（常见平台上是 16）的类型叫**过度对齐**类型。C++14 中 `new` 一个这样的对象，调用的是普通的 `::operator new(std::size_t)`，不保证得到对齐的内存。C++17 改为调用 `::operator new(std::size_t, std::align_val_t)`（[[expr.new]]、[[expr.delete]]），前提是类没有自己的分配函数。

本机运行上例，`-std=c++14` 下调用了自定义的 `operator new`，得到的地址模 64 余 32，没有对齐；`-std=c++17` 下自定义函数没有被调用，地址模 64 为 0。

所以只替换了 `operator new(size_t)` 的程序，在 C++17 下会漏掉过度对齐类型的分配，内存统计、内存池之类的代码会受影响。替换全局分配函数时，要把带 `std::align_val_t` 的各个版本（单对象和数组、`nothrow`、带大小的 `delete`）一起替换，见 [[new.delete]]。

## 声明 [diff.cpp14.dcl.dcl] {#diff.cpp14.dcl.dcl}

### 删除 `register`

```cpp error
void f() { register int x = 0; }   // error: C++14 中良构
```

¶1 `register` 不再是存储类说明符（[[dcl.stc]]），但仍是保留的关键字，以便将来改作他用。直接删掉它，含义不变。要留意被 C++ 代码包含的 C 头文件，那里的 `register` 同样会报错。Clang 23 在 `-std=c++14` 下给出 `-Wdeprecated-register` 警告，`-std=c++17` 下报错。

### 从花括号推导 `auto`

```cpp
auto x1{1};      // C++17：int；C++14：std::initializer_list<int>
auto x2{1, 2};   // error: C++14 中是 std::initializer_list<int>
auto x3 = {1};   // 两者都是 std::initializer_list<int>
```

¶2 直接列表初始化 `auto x{...}` 时，C++17 要求花括号里只有一个元素，`auto` 推导为这个元素的类型；C++14 推导为 `std::initializer_list`（[[dcl.spec.auto]]）。复制列表初始化 `auto x = {...}` 不变，仍然推导为 `initializer_list`。新规则更符合直觉：`auto x{1};` 和 `int x{1};` 得到同样的类型。

Clang 23 把这条当作缺陷修正，`-std=c++14` 下 `x1` 也是 `int`，`x2` 也报错。

### 异常说明成为函数类型的一部分

```cpp error
void g1() noexcept;
void g2();
template<class T> int f(T*, T*);
int x = f(g1, g2);   // error: T 推导冲突；C++14 中良构
```

¶3 C++17 中 `noexcept` 是函数类型的一部分：`void() noexcept` 与 `void()` 是不同的类型（[[dcl.fct]]）。指向 `noexcept` 函数的指针可以隐式转换为指向普通函数的指针，反过来不行，这样类型系统就能防止把可能抛出的函数交给只接受不抛出函数的地方。

上例中两个实参分别推出 `T = void() noexcept` 和 `T = void()`，推导冲突。显式指定模板实参（`f<void()>(g1, g2)`）即可。

受影响的还有两处。以函数类型为键的特化，比如自己写的函数类型特征、成员函数指针的特征类，需要为 `R(Args...) noexcept` 额外提供特化。名字修饰也变了：形参类型中含 `noexcept` 函数指针的函数，在 C++14 和 C++17 下的符号名不同。

### 聚合可以有基类

```cpp
struct derived;
struct base {
  friend struct derived;
private:
  base();
};
struct derived : base {};

derived d1{};   // error: C++14 中良构
derived d2;     // OK
```

¶4 C++17 起，有公有非虚基类的类也可以是**聚合**（[[dcl.init.aggr]]），用花括号初始化时基类子对象排在成员前面，例如 `struct D : B { int x; }; D d{{}, 1};`。

对这样的类，空花括号 `derived{}` 从调用默认构造函数变成了聚合初始化。聚合初始化在初始化处逐个初始化基类，访问检查也在初始化处进行：`base()` 是私有的，`derived` 是它的友元，但 `d1` 的初始化发生在全局作用域，不可访问。`d2` 仍然调用 `derived` 隐式定义的默认构造函数，它作为友元可以访问 `base()`。

把 `d1{}` 改成 `d1` 就能编译。给 `derived` 声明构造函数也行，但那样它就不再是聚合了，参见 [[diff.cpp17]] 的 [dcl] 一节。

## 类 [diff.cpp14.class] {#diff.cpp14.class}

### 继承构造函数不再向派生类注入构造函数

```cpp
struct A {
  template<typename T> A(T, typename T::type = 0);
  A(int);
};
struct B : A {
  using A::A;
  B(int);
};
B b(42L);   // C++17：调用 B(int)
            // C++14：调用注入的 B<long>(long)，它再调用 A(int)
```

¶1 C++14 中，`using A::A;` 在 `B` 里声明一组新的构造函数，每个对应 `A` 的一个构造函数。C++17 改为：这条声明只是让 `A` 的构造函数在初始化 `B` 时可见，由它们直接参与重载决议（[[class.inhctor.init]]）。旧模型下，默认实参、模板、访问控制、`explicit` 都有各种怪异的表现，新模型与其他语言特性配合得更好。

上例中，C++14 为 `A` 的构造函数模板注入了 `template<class T> B(T)`，默认实参不随之注入，所以 `B<long>(long)` 对 `42L` 是精确匹配，胜过需要转换的 `B(int)`。它再去调用 `A<long>(long)`，后者因 `long::type` 替换失败被排除，最后落到 `A(int)`。C++17 中继承来的模板以原样参与决议，同样被替换失败排除，剩下的 `B(int)` 胜出。

Clang 23 把新语义用于所有模式：给构造函数加上打印，`-std=c++14` 和 `-std=c++17` 都输出 `A(int)` 然后 `B(int)`。实际受影响的代码很少。

## 模板 [diff.cpp14.temp] {#diff.cpp14.temp}

### 从常量模板实参的类型推导

```cpp error
template <int N> struct A;
template <typename T, T N> int foo(A<N>*) = delete;
void foo(void*);
void bar(A<0>* p) {
  foo(p);   // error: 调用了被删除的模板；C++14 中调用 foo(void*)
}
```

¶1 C++17 允许 `auto` 作常量模板形参的类型（`template<auto N>`），偏特化需要能从中拆出 `N` 的类型。因此 C++17 规定，在 `template<typename T, T N>` 这样的声明中，从 `A<N>` 推导时，`T` 也可以由 `N` 的类型推出（[[temp.deduct.type]]）。

C++14 中 `T` 无法推导，模板被排除，调用 `foo(void*)`。C++17 中推出 `T = int`，模板对 `A<0>*` 是精确匹配，胜过需要转换的 `foo(void*)`，结果选中了被删除的函数。Clang 23 在 `-std=c++17` 下报 call to deleted function。

## 异常处理 [diff.cpp14.except] {#diff.cpp14.except}

### 删除动态异常说明

```cpp error
void g() throw(int);   // error: C++14 中良构
```

¶1 函数声明后的 `throw(T1, T2, ...)` 叫**动态异常说明**（[[g:dynamic-exception-specification]]），C++17 删除了其中可能抛出的形式（[[except.spec]]）。它用起来复杂而脆弱，与类型系统配合不好；`noexcept` 进入函数类型之后，这个问题更严重了。`throw(...)` 直接删掉即可。

`throw()` 暂时保留为 `noexcept` 的同义词，C++20 也把它删除了，见 [[diff.cpp17]]。违反 `throw()` 时，C++17 调用 `std::terminate` 而不再调用 `std::unexpected`，调用之前是否展开栈是未指定的。

Clang 23 在 `-std=c++14` 下接受（加 `-Wdeprecated` 才警告），`-std=c++17` 下报错。

## 库引言 [diff.cpp14.library] {#diff.cpp14.library}

¶1 C++17 新增头文件 `<any>`、`<charconv>`、`<execution>`、`<filesystem>`、`<memory_resource>`、`<optional>`、`<string_view>` 和 `<variant>`（[[headers]]）。项目里有同名头文件并用 `#include <...>` 包含时，可能拿到标准库的版本。

¶2 全局命名空间中 `std` 后跟数字的名字（`std1`、`std2` 等）保留给将来的标准库使用（[[namespace.future]]），使用这类顶层命名空间的代码需要改名。

## 通用工具库 [diff.cpp14.utilities] {#diff.cpp14.utilities}

¶1 `std::function` 接受分配器的构造函数被删除（[[func.wrap]]），因为各实现对它的支持很不一致。用分配器构造 `std::function` 的代码非良构，uses-allocator 构造也不再向 `std::function` 传递分配器。

### 从 `unique_ptr` 转换到 `shared_ptr`

```cpp error
#include <memory>
std::unique_ptr<int[]> arr(new int[1]);
std::shared_ptr<int> ptr(std::move(arr));   // error: int(*)[] 与 int* 不兼容
```

¶2 C++17 让 `shared_ptr` 支持数组，可以写 `shared_ptr<T[]>`、`shared_ptr<T[N]>`。为此，从 `unique_ptr<Y, D>` 构造 `shared_ptr<T>` 的约束改为要求 `Y*` 与 `T*` 兼容，并且 `unique_ptr` 的指针类型能转换成 `shared_ptr` 的元素指针类型（[[util.smartptr.shared]]）。上例中 `Y` 是 `int[]`，`int(*)[]` 与 `int*` 不兼容，程序非良构。改用 `std::shared_ptr<int[]>` 即可。

本机 libc++ 在 `-std=c++14` 下也拒绝上例。

## 字符串库 [diff.cpp14.string] {#diff.cpp14.string}

### 非 const 的 `data()`

```cpp error
int f(char*) = delete;
int f(const char*);
std::string s;
int x = f(s.data());   // error: 选中了被删除的 f(char*)；C++14 中良构
```

¶1 C++17 给 `basic_string` 增加了非 const 的 `data()`，返回 `charT*`（[[basic.string]]），与 `std::vector::data()` 保持一致。对非 const 字符串调用 `data()`，结果从 `const char*` 变成 `char*`，对 `char*` 和 `const char*` 分别重载的函数会走另一个分支。需要 `const char*` 时用 `s.c_str()` 或 `std::as_const(s).data()`。

## 容器库 [diff.cpp14.containers] {#diff.cpp14.containers}

### 比较器的调用运算符必须是 const 的

```cpp error
#include <set>
struct compare {
  bool operator()(int a, int b) { return a < b; }   // 缺 const
};
int main() {
  const std::set<int, compare> s;
  s.find(0);   // C++17 中可能编译失败
}
```

¶1 C++17 澄清了关联容器的要求：比较对象的函数调用运算符必须能在 const 的比较对象上调用（[[associative.reqmts]]）。给 `operator()` 加上 `const` 即可。本机 libc++ 在两种模式下都拒绝上例，并给出一条库自定义的警告，指出比较器没有可用的 const 调用运算符。

## 删除的弃用特性 [diff.cpp14.depr] {#diff.cpp14.depr}

¶1 C++17 删除了 `auto_ptr`、`unary_function`、`binary_function`、`random_shuffle`、`ptr_fun`、`mem_fun`、`mem_fun_ref`、`bind1st`、`bind2nd`，它们都已被新特性取代：

| 删除项 | 替代 |
|---|---|
| `auto_ptr` | `unique_ptr` |
| `unary_function`、`binary_function` | 不需要基类；需要结果类型时用 `invoke_result_t` |
| `random_shuffle` | `std::shuffle(first, last, urbg)` |
| `ptr_fun` | 直接传函数指针或 lambda |
| `mem_fun`、`mem_fun_ref` | `std::mem_fn` |
| `bind1st`、`bind2nd` | lambda 或 `std::bind` |

`auto_ptr` 换成 `unique_ptr` 通常是机械替换，但要注意 `auto_ptr` 复制即转移所有权的语义：原来 `a = b` 悄悄转移所有权的地方，要改成 `a = std::move(b)`。`unique_ptr` 不能复制，编译器会把这些地方都指出来。libc++ 在 `-std=c++14` 下对这些名字给出弃用警告，`-std=c++17` 下报名字不存在。

¶2 [depr.ios.members] 中为兼容标准化之前的代码而保留的 iostream 成员被删除，例如 `ios_base::io_state`、`open_mode`、`seek_dir` 这几个类型。改用 `iostate`、`openmode`、`seekdir`。

## 小结

| 条目 | 旧代码的结局 | Clang 23 / libc++ |
|---|---|---|
| 三字符组 | 含义改变 | 已实现 |
| 预处理数吸收 `p±` | 非良构或含义改变 | 未完全实现 |
| `bool` 自增 | 非良构 | 已实现，C++14 下警告 |
| 过度对齐类型的 `new` | 调用另一个分配函数 | 已实现 |
| `register` | 非良构 | 已实现，C++14 下警告 |
| `auto x{1}` | 类型改变 | 已实现，C++14 模式同样处理 |
| `noexcept` 进入函数类型 | 非良构，修饰名改变 | 已实现 |
| 聚合可以有基类 | 非良构或含义改变 | 已实现 |
| 继承构造函数 | 调用另一个构造函数 | 已实现，C++14 模式同样处理 |
| 从常量实参的类型推导 | 非良构 | 已实现 |
| 动态异常说明 | 非良构 | 已实现 |
| `std::function` 的分配器 | 非良构 | 已删除 |
| `unique_ptr<T[]>` 到 `shared_ptr<T>` | 非良构 | 两种模式都拒绝 |
| 非 const 的 `data()` | 调用另一个重载 | 已实现 |
| 非 const 的比较器 | 非良构 | 两种模式都拒绝 |
| 删除的弃用特性 | 非良构 | 已删除 |
