---
title: C++ 与 ISO C++ 2017 的差异
summary: 从 C++17 升级到 C++20 时，哪些原来合法的代码会报错或改变行为：module/import 开头的行、新关键字、<=> 记号、u8 字面量变成 char8_t、聚合的新定义、反向 == 候选、f < a 被当作模板名、throw() 删除，以及 iostream、filesystem、容器和一批弃用库设施的改动。
status: done
covers: *
related: diff, diff.cpp20, diff.cpp14, lex.key, dcl.init.aggr, over.match.oper, class.copy.elision, module.unit, lex.string
tags: 附录, 兼容性, 迁移, C++20
updated: 2026-10-19
---

!!! tldr
    - C++20 新增了 `concept`、`requires`、`char8_t`、`consteval`、`constinit` 和三个 `co_` 关键字，`module`、`import` 开头的行会被当作模块指令，`<=` 后紧跟 `>` 会合成 `<=>`。
    - `u8"..."` 的类型从 `const char` 数组变成 `const char8_t` 数组，把它当 `const char*`、`std::string` 用或者输出到 `std::cout` 的代码都要改。
    - 声明了任何构造函数（包括 `= default`、`= delete`）的类不再是聚合，`struct P { P() = default; int x, y; }; P p{1, 2};` 编译失败。
    - `a == b` 还会尝试参数对调的 `operator==`，`a != b` 还会尝试改写成 `!(a == b)`。不对称或缺少 `const` 的 `operator==` 可能变成歧义，或者悄悄调用另一个函数。
    - 库方面：`throw()` 删除，iostream 拒绝 `u8`、`char16_t` 等字符的输出和对 `char*` 的无界读取，`uncaught_exception`、`not1`、`result_of`、`std::allocator` 的冗余成员等弃用设施被删除。

[diff.cpp17] 列出 C++20 相对 C++17 的不兼容：原来良构的代码，在 C++20 中变成非良构，或者含义改变。每一条在标准里都写成同样的格式：受影响的条款、改了什么、为什么改、对旧代码有什么影响。C++20 加入了模块、概念、协程、三路比较和 `char8_t`，它们各自在旧语法上占了一块地方，所以这一节的条目比其他版本多。

¶1 这一节列的是在前面各节之外的差异：从 C++17 升级到当前草案，还要再看 [[diff.cpp20]]、[[diff.cpp23]] 和 [[diff.cpp26]]。条目按正文的章节顺序排列。文中的实测都用本机 Clang 23.1.3 + libc++，对比 `-std=c++17` 与 `-std=c++20`。在 `-std=c++17` 下加 `-Wc++20-compat`，Clang 会对其中几条提前给出警告。

## 词法约定 [diff.cpp17.lex] {#diff.cpp17.lex}

### `module`、`import` 开头的行

```cpp
class module {};
module m1;     // C++20：模块声明，不再是变量声明
module *m2;    // 仍是变量声明

class import {};
import j1;     // C++20：模块导入声明
::import j2;   // 仍是变量声明
```

¶1 C++20 中，以 `module` 或 `import` 开头的逻辑行会被预处理器识别为模块指令（[[lex.pptoken]]、[[module.unit]]、[[module.import]]、[[cpp.module]]、[[cpp.import]]）。`module` 和 `import` 不是关键字，而是**有特殊含义的标识符**：只在这些位置有特殊含义，在别处仍可作名字。

所以 `module m1;` 不再声明一个变量，而成了一条（位置不对的）模块声明。后面跟 `*`、`::` 这类不能出现在模块指令里的记号时不受影响。修正方法是在类型名前加 `::`，或者改名。Clang 23 对 `module m1;` 报 module declaration must occur at the start of the translation unit。

### `import` 后面的 `<...>`

```cpp
template<typename> class import {};
import<int> f();     // error: 被当作导入头文件 <int>
::import<int> g();   // OK
```

¶2 C++20 可以用 `import <vector>;` 导入头文件单元，所以标识符 `import` 后面跟 `<` 时，`<...>` 会被分成一个头文件名记号（[[lex.header]]）。上例第二行因此成了导入名为 `int` 的头文件，Clang 23 报 'int' file not found。加 `::` 即可。

### 新关键字

```cpp
bool requires = true;   // error: C++20 中 requires 是关键字
int concept = 0;        // error
char char8_t = 0;       // error
```

¶3 C++20 新增关键字 `char8_t`、`concept`、`consteval`、`constinit`、`co_await`、`co_yield`、`co_return` 和 `requires`（[[lex.key]]），用它们作标识符的代码失效。`requires` 和 `concept` 在老代码里作变量名并不罕见。改名即可，量可能较大。在 `-std=c++17` 下加 `-Wc++20-compat`，Clang 会对每一处给出 is a keyword in C++20 的警告。

### 新记号 `<=>`

<div class="compare" markdown="1">

```cpp error
namespace N {
  struct X {};
  bool operator<=(X, X);
  template<bool(X, X)> struct Y {};
  Y<operator<=> y;    // error
}
```

```cpp ok
namespace N {
  struct X {};
  bool operator<=(X, X);
  template<bool(X, X)> struct Y {};
  Y<operator<= > y;   // OK
}
```

</div>

¶4 三路比较运算符 `<=>` 是 C++20 的新记号（[[lex.operators]]）。分词时取最长的记号，所以 C++17 中紧挨着的 `<=` 和 `>` 现在合成一个 `<=>`。左边本意是把函数 `operator<=` 作为模板实参，C++20 中却成了 `operator<=>`。加一个空格即可。

Clang 23 在 `-std=c++17` 下给出 `-Wc++20-compat` 警告，提示加空格；`-std=c++20` 下报错。

### UTF-8 字面量的类型变成 `char8_t`

```cpp
const auto* u8s = u8"text";   // 推导为 const char8_t*（C++17：const char*）
const char* ps = u8s;         // error

auto u8c = u8'c';             // 推导为 char8_t（C++17：char）
char* pc = &u8c;              // error

std::string s = u8"text";     // error

void f(const char* s);
f(u8"text");                  // error

template<typename> struct ct;
template<> struct ct<char> { using type = char; };
ct<decltype(u8'c')>::type x;  // error: ct<char8_t> 没有定义
```

¶5 C++20 新增了字符类型 `char8_t`，`u8"..."` 的类型从 `const char` 的数组改为 `const char8_t` 的数组，`u8'c'` 的类型从 `char` 改为 `char8_t`（[[lex.string]]、[[lex.ccon]]）。这样重载、模板特化和类型推导就能区分普通字面量和 UTF-8 字面量。代价是所有把 `u8` 字面量当 `char` 字符串用的代码都失效了。

可选的修正方法有几种。执行字符集本来就是 UTF-8 时，去掉 `u8` 前缀；接口可以改的，改用 `std::u8string_view`；临时过渡可以用 `reinterpret_cast<const char*>(u8"...")`。Clang 和 GCC 还提供非标准选项 `-fno-char8_t`，恢复 C++17 的语义。C++23 又允许用 `u8` 字面量初始化 `char` 数组，见 [[diff.cpp20]] 的 [dcl] 一节。

## 基础 [diff.cpp17.basic] {#diff.cpp17.basic}

### 伪析构函数调用结束对象的生命周期

```cpp ub
int f() {
  int a = 123;
  using T = int;
  a.~T();
  return a;   // UB：a 的生命周期已经结束；C++17 返回 123
}
```

¶1 对 `int` 这样的标量类型调用析构函数，叫**伪析构函数调用**（[[g:pseudo-destructor]]）。C++17 中它什么也不做，C++20 规定它结束对象的生命周期（[[basic.life]]）。这样，泛型代码对任意 `T` 写 `p->~T()`，无论 `T` 是类还是标量，含义都是对象到此为止。之后再读 `a` 就是读取生命周期之外的对象，行为未定义。

本机运行时两种模式都返回 123，这是 UB 的一种表现。把 `f` 改成 `constexpr` 并在常量表达式中调用，`-std=c++20` 下 Clang 报 read of object outside its lifetime，确认了新规则。

### 释放序列只由读-改-写操作组成

```cpp
std::atomic<int> flag{0};
int data = 0;

// 线程 1
data = 42;
flag.store(1, std::memory_order_release);
flag.store(2, std::memory_order_relaxed);

// 线程 2
if (flag.load(std::memory_order_acquire) == 2)
  use(data);   // C++20：与 data = 42 构成数据竞争；C++17：已同步
```

¶2 一次 release 写之后，对同一原子变量的某些后续修改仍然算作这次写的延续，读到它们的 acquire 读同样能与那次 release 写同步。这串修改叫**释放序列**（[[g:release-sequence]]，[[intro.races]]）。C++17 中，同一线程随后对该变量的普通写也算在内；C++20 规定，除了开头的 release 操作，释放序列只包含原子读-改-写操作（如 `fetch_add`、`exchange`）。

所以上例中线程 2 读到 2 时，不再与线程 1 的 release 写同步，读 `data` 构成数据竞争，即使中间没有别的线程写过 `flag`。这个特性很少被用到，又容易让人困惑，因此被删除。编译器不会诊断，修正方法是把第二次写也改成 `memory_order_release`。

## 表达式 [diff.cpp17.expr] {#diff.cpp17.expr}

### 隐式 lambda 捕获可能捕获更多实体

```cpp
template<bool B>
void f(int n) {
  [=](auto a) {
    if constexpr (B && sizeof(a) > 4) {
      (void)n;   // 无论 B 和 sizeof(int) 是多少，都捕获 n
    }
  }(0);
}
```

¶1 带默认捕获（`[=]` 或 `[&]`）的 lambda 会自动捕获函数体里用到的局部实体。C++17 只在实体被 odr-use（大致是需要它的地址或运行时的值）时才捕获；C++20 改为按语法判断：只要在潜在求值的表达式里命名了它，就捕获，即使这个表达式在 `if constexpr` 被丢弃的分支里（[[expr.prim.lambda.capture]]）。

按 odr-use 判断时，泛型 lambda 捕获哪些变量要等到实例化后才知道，闭包类型的布局因此依赖于实例化，和 `if constexpr` 的交互也说不清楚。改成按语法判断后规则简单了，代价是闭包可能比以前大，多复制一些对象。没有被 odr-use 的捕获，实现可以优化掉。

本机 Clang 23 在两种模式下都捕获了 `n`（闭包大小为 4），即把这条修正也用于 C++17 模式。这条改动通常不需要修改代码。

## 声明 [diff.cpp17.dcl.dcl] {#diff.cpp17.dcl.dcl}

### 用 typedef 命名的无名类只能包含 C 兼容的成员

```cpp error
typedef struct {
  void f() {}   // error: C++17 中良构
} S;
```

¶1 `typedef struct { ... } S;` 这种写法中，无名类借 typedef 名 `S` 取得链接时用的名字，这叫**用于链接的 typedef 名**（[[g:typedef-name-for-linkage]]，[[dcl.typedef]]）。C++20 规定这样的类只能有非静态数据成员、成员枚举和成员类，不能有成员函数、基类、默认成员初始化器或 lambda 表达式，也就是只能包含 C 里也有的东西。

原因是可实现性。类的链接名要等读到末尾的 `S` 才确定，而类体内的成员函数等实体在那之前就需要确定的名字，比如用于名字修饰。修正方法是给类起名：`struct S { ... };`。Clang 23 在两种模式下都只给出 `-Wnon-c-typedef-for-linkage` 警告；对非良构的程序给出警告也算诊断，所以这符合标准。

### 同一函数在不同翻译单元中不能有不同的默认实参

```cpp title="tu1.cpp"
int f(int a = 42);
int g() { return f(); }
```

```cpp title="tu2.cpp" ifndr
int f(int a = 76) { return a; }   // 与 tu1.cpp 的默认实参不同
int g();
int main() { return g(); }        // C++17 中返回 42
```

¶2 C++20 规定，同一个函数在不同翻译单元的声明给同一个形参提供默认实参时，这些默认实参必须相同（[[dcl.fct.default]]）。模块需要这条规则：一个默认实参可能经由模块接口进入许多翻译单元，它的含义必须唯一。

违反这条规则的程序是**非良构、不要求诊断**的（IFNDR）：编译器一次只看一个翻译单元，看不到冲突，链接器也不报错，标准却不再保证任何结果。修正方法是把默认实参只写在头文件里那一个声明上。

### 有用户声明的构造函数的类不再是聚合

```cpp
struct A { A() = delete; };                 // C++17 是聚合，C++20 不是
struct B { B() = default; int i = 0; };     // 同上
struct C { C(C&&) = default; int a, b; };   // 同上

A a{};                  // error: C++17 中良构
B b = {1};              // error
auto* c = new C{2, 3};  // error

struct Y;
struct X { operator Y(); };
struct Y {              // C++17 是聚合，C++20 不是
  Y(const Y&) = default;
  X x;
};
Y y{X{}};   // C++20：经 X::operator Y 调用复制构造函数
            // C++17：聚合初始化，用 X{} 初始化 y.x
```

¶3 **聚合**是可以用花括号逐个初始化成员的类，比如 `struct P { int x, y; }; P p{1, 2};`（[[dcl.init.aggr]]）。C++17 要求聚合没有用户提供的构造函数，C++20 改为没有用户声明的构造函数，于是写了 `= default` 或 `= delete` 的构造函数也会使类不再是聚合。

旧规则下，声明了 `A() = delete;` 的类仍然可以写 `A a{};`，聚合初始化完全绕过了作者禁止默认构造的意图。新规则堵上了这个漏洞。

实际代码中最常见的受害者是 `struct P { P() = default; int x, y; }; P p{1, 2};`。那行 `= default` 本来就是多余的，删掉它，类就重新成为聚合。如果构造函数另有用途，就补一个真正接受这些实参的构造函数。Clang 23 已经实现，`-std=c++20` 下 `A`、`B`、`C` 三行都报错。

### 指针到 `bool` 的转换是窄化转换

```cpp error
bool y[] = { "bc" };   // error: C++17 中良构
```

¶4 花括号初始化不允许可能丢失信息的隐式转换，这类转换叫**窄化转换**（[[g:narrowing-conversion]]，[[dcl.init.list]]）。C++20 把指针或成员指针到 `bool` 的转换也算作窄化，以便捕获上例这样的错误：本意大概是字符串，结果得到一个 `true`。需要真假值时写 `p != nullptr`。Clang 23 把这条当作缺陷修正，`-std=c++17` 下也报错。

## 类 [diff.cpp17.class] {#diff.cpp17.class}

### `explicit` 后面不能紧跟带括号的构造函数名

```cpp
struct S {
  explicit (S)(const S&);      // error: C++17 中良构
  explicit (operator int)();   // error
  explicit(true) (S)(int);     // OK
};
```

¶1 C++20 引入了条件式的 `explicit(条件)`，所以 `explicit` 后面紧跟的括号会被当作条件来解析（[[class.ctor]]、[[class.conv.fct]]）。C++17 中构造函数名或转换函数名可以加括号，`explicit (S)(const S&)` 是合法的写法；C++20 中 `(S)` 被当成条件，程序非良构。去掉多余的括号即可。

### 构造函数名不能写成 `A<T>`

```cpp error
template<class T>
struct A {
  A<T>();    // error: C++17 中良构
  A(int);    // OK：用注入类名
  ~A<T>();   // error
};
```

¶2 在类模板内部声明构造函数或析构函数时，C++20 不再允许写成 `A<T>` 这样带模板实参的形式，只能用注入类名 `A`（[[class.ctor]]、[[class.dtor]]）。这种冗余写法容易出错，因此被删除，删掉 `<T>` 即可。

Clang 23 还没有实现这条限制，`-std=c++20` 下即使加 `-pedantic` 也没有任何诊断。

### 隐式移动的适用范围扩大

```cpp
struct base {
  base();
  base(base const&);
private:
  base(base&&);
};
struct derived : base {};

base f(base b) {
  throw b;     // error: base(base&&) 是私有的
  derived d;
  return d;    // error: base(base&&) 是私有的
}
```

¶3 C++20 在两处扩大了隐式移动（[[class.copy.elision]]）。一是返回一个可移动的局部对象时，可以调用接受另一种类型右值引用的构造函数，比如返回 `derived` 局部变量时用 `base` 的移动构造函数。二是函数形参和 catch 子句的形参在 `throw` 时也可以被移动。

原来选复制构造函数的地方现在选移动构造函数，移动构造函数不可访问时编译失败，如上例。移动与复制的效果不同时，行为也会改变：

```cpp
struct S {
  S(const char* s) : m(s) { }
  S(const S&) = default;
  S(S&& other) : m(other.m) { other.m = nullptr; }
  const char* m;
};

S consume(S&& s) { return s; }   // C++20：移动 s，也就是调用者的对象

void g() {
  S s("text");
  consume(static_cast<S&&>(s));
  char c = *s.m;   // UB：s.m 已被置空；C++17 中 s 被复制，没有问题
}
```

`consume` 的形参 `s` 是右值引用，C++20 中 `return s;` 会移动它所引用的对象，也就是 `g` 里的 `s`。Clang 23 把这条改动也用于 C++17 模式：`f` 在两种模式下都报错，`g` 中 `s.m` 在两种模式下都是空指针。

## 重载 [diff.cpp17.over] {#diff.cpp17.over}

### `==` 和 `!=` 会使用对调参数的候选

```cpp
struct A {
  operator int() const;
};

bool operator==(A, int);   // #1
// 内置候选 #2：bool operator==(int, int);
// 内置候选 #3：bool operator!=(int, int);

int check(A x, A y) {
  return (x == y) +   // C++20：歧义；C++17：调用 #1
    (10 == x) +       // C++20：调用 #1（参数对调）；C++17：#2
    (10 != x);        // C++20：调用 #1（改写为 !(x == 10)）；C++17：#3
}
```

¶1 C++20 中，`x == y` 除了找 `operator==(x, y)`，还会考虑参数对调的 `operator==(y, x)`；`x != y` 还会考虑由 `operator==` 改写而来的 `!(x == y)` 及其对调形式。这些叫**改写候选**（[[g:rewritten-candidate]]，[[over.match.oper]]）。这样只写一个 `operator==` 就能支持全部四种相等比较，与三路比较 `<=>` 的设计一致。

于是一个类型能隐式转换成另一个类型时，`==`、`!=` 可能调用另一个函数。上例中 `10 == x` 原来用内置的整数比较，现在用 #1。`x == y` 则变成歧义：正向的 #1 要把 `y` 转换成 `int`，对调的 #1 要把 `x` 转换成 `int`，两者一样好。

¶2 同一类型的两个对象比较也可能变成歧义：

```cpp
struct B {
  bool operator==(const B&);   // 漏了 const
};
B b1;
bool eq = (b1 == b1);          // C++20：歧义；C++17 良构
```

正向候选 `b1.operator==(b1)` 的隐式对象形参是非 const 的 `B&`，第二个形参是 `const B&`；对调的候选正好相反。两个候选各在一个实参上匹配得更好，于是歧义。给成员 `operator==` 加上 `const` 就好了，这本来就该有。

对这两种歧义，Clang 23 只给出 `-Wambiguous-reversed-operator` 警告，然后照常选一个函数。警告也是诊断，所以这符合标准。给 #1 加上打印实测，`10 == x` 和 `10 != x` 在 `-std=c++17` 下用的是内置比较，在 `-std=c++20` 下都调用 #1。这类改变调用目标的情况编译器不会提示，需要人工检查。

## 模板 [diff.cpp17.temp] {#diff.cpp17.temp}

### 后面跟 `<` 的函数名被当作模板名

```cpp
struct A {};
bool operator<(void (*fp)(), A);
void f() {}
int main() {
  A a;
  f < a;     // error: C++17 中良构
  (f) < a;   // OK
}
```

¶1 C++20 规定，一个不带限定的名字后面跟着 `<`，如果名字查找什么也没找到，或者找到的是函数，就把它当作模板名（[[temp.names]]）。

这是为了能用实参依赖查找（ADL）调用带显式模板实参的函数模板，比如 `get<0>(t)`。C++17 中，如果普通查找看不到任何名叫 `get` 的模板，`get < 0` 会被当成小于号，只能先 `using` 一个同名模板才行。代价是上例中 `f < a` 被当成模板实参列表的开头，程序非良构。加括号即可。

## 异常处理 [diff.cpp17.except] {#diff.cpp17.except}

### 删除 `throw()`

```cpp error
void f() throw();   // error: 改成 void f() noexcept;
```

¶1 C++20 删除了异常说明 `throw()`（[[except.spec]]）。它从 C++17 起就与 `noexcept` 含义相同，直接替换即可。带类型的动态异常说明 `throw(int)` 在 C++17 中已经删除，见 [[diff.cpp14]]。

标准还提到，没有一种写法能同时在当前标准和 C++03 中都表示不抛出，需要兼容两者的头文件只能用预处理器按 `__cplusplus` 生成不同的代码。

Clang 23 还没有实现这条：`void f() throw();` 在 `-std=c++20` 乃至 `-std=c++2c` 下都被接受，加 `-Wdeprecated` 才有一条弃用警告。

## 库引言 [diff.cpp17.library] {#diff.cpp17.library}

¶1 C++20 新增头文件 `<barrier>`、`<bit>`、`<charconv>`、`<compare>`、`<concepts>`、`<coroutine>`、`<format>`、`<latch>`、`<numbers>`、`<ranges>`、`<semaphore>`、`<source_location>`、`<span>`、`<stop_token>`、`<syncstream>` 和 `<version>`（[[headers]]）。要留意 `<version>`：有些项目在包含路径里放了一个名叫 `version`（或在大小写不敏感的文件系统上叫 `VERSION`）的文件，而标准库的其他头文件会包含 `<version>`，拿到错误的文件就会出现莫名其妙的错误。

¶2 C++20 删除了 `<ccomplex>`、`<ciso646>`、`<cstdalign>`、`<cstdbool>`、`<ctgmath>` 这五个空洞的头文件。它们的存在暗示 C++ 头文件需要和 C 兼容，而这个要求并不存在。`<ccomplex>` 换成 `<complex>`，`<ctgmath>` 换成 `<cmath>` 加 `<complex>`，其余三个直接删掉。本机 libc++ 在 C++20 模式下仍然提供这五个头文件，没有警告。

## 容器库 [diff.cpp17.containers] {#diff.cpp17.containers}

¶1 `list` 和 `forward_list` 的 `remove`、`remove_if`、`unique` 的返回类型从 `void` 改为 `size_type`，返回删除的元素个数（[[forward.list]]、[[list]]）。依赖返回类型的代码，比如取成员函数指针或者用 `decltype`，可能改变含义。用 C++17 和 C++20 分别编译的翻译单元混在一起时，可能链接失败，也可能有未定义行为。本机 libc++ 已经实现：`decltype(std::list<int>{}.remove(1))` 在 C++17 下是 `void`，C++20 下是 `unsigned long`。

## 迭代器库 [diff.cpp17.iterators] {#diff.cpp17.iterators}

¶1 `iterator_traits` 对 `void*` 和函数指针类型的特化不再有任何嵌套类型（[[iterator.traits]]），以免把不能递增的指针误认作迭代器。依赖这些嵌套类型的代码可能编译失败或者行为改变。本机 libc++ 在 C++17 下访问 `iterator_traits<void*>::value_type` 会在库内部报硬错误，C++20 下则是普通的成员不存在，可以用 SFINAE 检测。

## 算法库 [diff.cpp17.alg.reqs] {#diff.cpp17.alg.reqs}

¶1 算法声明中可推导模板形参的个数和顺序，从与声明一致改为未指定（[[algorithms.requirements]]）。这让实现可以把一些算法写成带模板调用运算符的函数对象，`std::ranges` 中的算法就是这样实现的。给算法显式写模板实参的代码（如 `std::find<It, int>(...)`）可能编译失败或有未定义行为，除非该算法明确允许这样做。让模板实参自动推导即可。

## 输入/输出库 [diff.cpp17.input.output] {#diff.cpp17.input.output}

### 读取字符数组只接受数组

```cpp
auto p = new char[100];
char q[100];
std::cin >> std::setw(20) >> p;   // error: C++17 中良构
std::cin >> std::setw(20) >> q;   // OK
```

¶1 `operator>>(basic_istream&, charT*)` 改为 `operator>>(basic_istream&, charT(&)[N])`（[[istream.extractors]]）。库由此知道目标数组的大小，即使忘了 `setw` 也不会写出界。读入指针所指的缓冲区不再允许，改读进 `std::string`，或者改用数组。

### 向 `ostream` 输出 `u8` 和其他字符类型

```cpp
std::cout << u8"text";   // error: C++17 中打印字符串
std::cout << u8'X';      // error: C++17 中打印字符
std::cout << u"text";    // error: C++17 中打印指针的值
std::cout << u'X';       // error: C++17 中打印整数 88
```

¶2 `u8` 字面量的类型变成 `char8_t` 之后，如果什么都不做，`cout << u8"text"` 会选中 `const void*` 重载打印地址，`cout << u8'X'` 会打印整数。所以 C++20 把 `basic_ostream<char>` 和 `basic_ostream<wchar_t>` 对 `char8_t` 字符和字符串的插入运算符定义为删除的（[[ostream.inserters.character]]）。

¶3 出于同样的原因，`basic_ostream<char>` 对 `wchar_t`、`char16_t`、`char32_t` 的插入运算符，以及 `basic_ostream<wchar_t>` 对 `char16_t`、`char32_t` 的插入运算符也被删除。C++17 中 `cout << u"text"` 打印指针值、`cout << u'X'` 打印 88，都不是任何人想要的结果。本机 libc++ 已经实现，这些写法在 C++20 下都报 selected deleted operator。

### `path::u8string()` 返回 `std::u8string`

```cpp
std::filesystem::path p;
std::string s1 = p.u8string();           // error: C++17 中良构
std::string s2 = p.generic_u8string();   // error
```

¶4 `std::filesystem::path` 的 `u8string()` 和 `generic_u8string()` 改为返回 `std::u8string`（[[fs.class.path]]）。需要 `std::string` 时改用 `p.string()`（本机编码），或者显式转换。

## 删除的弃用特性 [diff.cpp17.depr] {#diff.cpp17.depr}

C++20 删除了一批在 C++17 中弃用的库设施。libc++ 在 `-std=c++17` 下对它们给出 `-Wdeprecated-declarations` 警告，在 `-std=c++20` 下报名字不存在。

¶1 `uncaught_exception()` 被删除。多个异常同时处于活动状态时它的含义不清楚，已被返回个数的 `uncaught_exceptions()` 取代。在析构函数里判断是否因栈展开而析构，正确的做法是构造时记下 `uncaught_exceptions()`，析构时比较。

¶2 可适配函数（adaptable function）的那套约定被删除：标准库类中的 `result_type`、`argument_type`、`first_argument_type`、`second_argument_type` 嵌套类型，以及 `not1`、`not2`、`unary_negate`、`binary_negate`。这套约定只能描述一元和二元函数，无法扩展到一般情况，已被 `decltype`、`std::bind` 和 `std::not_fn` 取代。

¶3 `std::allocator` 的冗余成员被删除：`pointer`、`const_pointer`、`reference`、`const_reference`、`rebind`、`address`、`construct`、`destroy`、`max_size`，以及带提示参数的 `allocate`。它们鼓励用户容器直接使用 `std::allocator` 的成员，而不是经由 `std::allocator_traits`。改写时一律通过 `std::allocator_traits<A>` 访问，例如 `traits::construct(a, p, args...)`、`traits::rebind_alloc<U>`。

¶4 `raw_storage_iterator` 被删除。它鼓励使用可能抛出异常的算法，却不返回成功构造的元素个数，出现异常时无法销毁已经构造的部分。改用 `std::uninitialized_copy` 等算法，它们在异常时会自己清理。

¶5 `get_temporary_buffer` 和 `return_temporary_buffer` 被删除。它们本意是为小块内存请求提供高效的分配，但没有证据表明实际做到了，而且用户往往要自己写异常安全的包装。

¶6 `shared_ptr::unique()` 被删除。在多线程和存在 `weak_ptr` 的情况下，它的结果不可靠。`use_count()` 同样不可靠，但契约更清楚，单线程中也有明确的用途，所以保留。

¶7 类型特征 `is_literal_type`、`is_literal_type_v`、`result_of`、`result_of_t` 被删除（[[depr.meta.types]]）。`is_literal_type` 无法告诉你类型的哪些成员函数是 `constexpr` 的，几乎没有用处；`result_of<F(Args...)>` 的语法令人意外，也不直接支持函数类型。`result_of_t<F(Args...)>` 改写成 `invoke_result_t<F, Args...>`。

## 小结

| 条目 | 旧代码的结局 | Clang 23 / libc++ |
|---|---|---|
| `module`、`import` 开头的行 | 含义改变 | 已实现 |
| 新关键字 | 非良构 | 已实现，`-Wc++20-compat` 可预警 |
| `<=>` 记号 | 非良构 | 已实现，`-Wc++20-compat` 可预警 |
| `u8` 字面量变成 `char8_t` | 非良构 | 已实现 |
| 伪析构结束生命周期 | 之后的读取是 UB | 常量求值中可见 |
| 释放序列 | 数据竞争 | 无诊断 |
| 隐式捕获 | 闭包可能变大 | 已实现，C++17 模式同样处理 |
| typedef 命名的无名类 | 非良构 | 只给警告 |
| 跨翻译单元的默认实参 | IFNDR | 无诊断 |
| 聚合的定义 | 非良构或含义改变 | 已实现 |
| 指针到 `bool` 窄化 | 非良构 | 已实现，C++17 模式同样处理 |
| `explicit (S)` | 非良构 | 已实现 |
| 构造函数名 `A<T>` | 非良构 | 未实现 |
| 隐式移动扩大 | 非良构或行为改变 | 已实现，C++17 模式同样处理 |
| 对调的 `==` 候选 | 歧义或调用另一函数 | 已实现，歧义只给警告 |
| `f < a` | 非良构 | 已实现 |
| `throw()` | 非良构 | 未实现 |
| iostream、filesystem 四条 | 非良构 | 已实现 |
| 删除空洞的 C 头文件 | 非良构 | libc++ 仍提供 |
| 删除的弃用特性 | 非良构 | 已删除 |
