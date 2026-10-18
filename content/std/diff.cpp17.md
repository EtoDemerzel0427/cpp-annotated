---
title: C++ 与 ISO C++ 2017 的差异
summary: Annex C.4：从 C++17 升级到 C++20 会遇到的 35 条不兼容——module/import 开头的行、新关键字、<=> token、u8 字面量变成 char8_t、伪析构结束生命周期、有用户声明构造函数的类不再是聚合、反向 == 候选、f < a 被当作模板名、throw() 删除，以及 iostream、filesystem、分配器、函数对象适配器等库改动。逐条给出前后对比与 Clang 23 / libc++ 实测。
status: draft
covers: *
related: diff, diff.cpp20, diff.cpp14, lex.key, dcl.init.aggr, over.match.oper, class.copy.elision, module.unit, lex.string
tags: 附录, 兼容性, 迁移, C++20
updated: 2026-10-18
---

[diff.cpp17] 列出 C++17 → C++20 这一步引入的不兼容。C++20 是一次大版本：模块、概念、协程、三路比较、`char8_t` 各自都在旧语法上占了一块地方。所以这一节条目最多，而且有几条会在真实项目里大面积出现：

- **新关键字**：`concept`、`requires`、`char8_t` 这几个词在老代码里作标识符并不罕见。
- **`u8` 字面量的类型**：所有把 `u8"…"` 当 `const char*` 用的代码都要改。
- **聚合的定义**：`struct S { S() = default; int x; }; S s{1};` 这种写法在 C++20 中失效。
- **`==` 的反向候选**：一些不对称的 `operator==` 在 C++20 中变成歧义或调用了另一个函数。

实测环境：Clang 23.1.3 + libc++，对比 `-std=c++17` 与 `-std=c++20`。需要提前发现问题时，在 C++17 模式下加 `-Wc++20-compat`，见 [[diff]]。

¶1 [diff.cpp17.general]：本小节列出与 ISO C++ 2017 的差异，是在前面各小节所列差异**之外**的部分。

## Clause [lex]：词法约定 {#diff.cpp17.lex}

### ¶1 新的有特殊含义的标识符 `module`、`import`

**受影响小节**：[[lex.pptoken]]、[[module.unit]]、[[module.import]]、[[cpp.pre]]、[[cpp.module]]、[[cpp.import]]

**改动**：以 `module` 或 `import` 开头的逻辑行（后面跟的不是 `::` 或 `(` 等）会被预处理器识别为模块指令。

**理由**：模块需要。

```cpp
class module {};
module m1;          // C++17：变量声明；现在：module-declaration
module *m2;         // 仍是变量声明

class import {};
import j1;          // C++17：变量声明；现在：module-import-declaration
::import j2;        // 仍是变量声明
```

**Clang 23 实测**：C++20 模式下第 2 行报 `module declaration must occur at the start of the translation unit`，随后 `fatal error: module 'm1' not found`。

**改写难度**：容易。在类型名前加 `::`，或改名。

### ¶2 更多场合会形成 *header-name*

**受影响小节**：[[lex.header]]

**改动**：标识符 `import` 后面跟 `<` 时，`<…>` 可能被分成一个 *header-name* token。

```cpp error
template<typename> class import {};
import<int> f();      // error: 现在被当作导入头文件单元 <int>
::import<int> g();    // OK
```

**Clang 23 实测**：C++20 下 `fatal error: 'int' file not found`，即 `import<int>` 被当成了 `import <int>;`。

**改写难度**：容易，同上。

### ¶3 新关键字

**受影响小节**：[[lex.key]]

**改动**：新增关键字 `char8_t`、`concept`、`consteval`、`constinit`、`co_await`、`co_yield`、`co_return`、`requires`。

**影响**：用这些词作标识符的代码失效。

**Clang 23 实测**：C++17 模式加 `-Wc++20-compat` 可以提前发现：

```text
warning: 'concept' is a keyword in C++20 [-Wc++20-compat]
warning: 'requires' is a keyword in C++20 [-Wc++20-compat]
warning: 'char8_t' is a keyword in C++20 [-Wc++20-compat]
```

**改写难度**：容易，但可能量大。`requires`（如 `bool requires;`）和 `concept`（概念验证代码里的变量名）最常见。

### ¶4 新运算符 `<=>`

**受影响小节**：[[lex.operators]]

**改动**：`<=>` 成为一个 token。C++17 中紧挨着的 `<=` 与 `>` 会被合并。

```cpp error
namespace N {
  struct X {};
  bool operator<=(X, X);
  template<bool(X, X)> struct Y {};
  Y<operator<=> y;     // error: 现在非良构；C++17 中是 Y< operator<= > y
}
```

**Clang 23 实测**：

```text
$ clang++ -std=c++17 ...
warning: '<=>' is a single token in C++20; add a space to avoid a change in behavior [-Wc++20-compat]
$ clang++ -std=c++20 ...
error: use of undeclared 'operator<=>'
```

**改写难度**：容易，加空格。

### ¶5 UTF-8 字符串和字符字面量的类型改为 `char8_t`

**受影响小节**：[[lex.literal]]（本站见 [[lex.string]]、[[lex.ccon]]）

**改动**：`u8"…"` 的类型从"`const char` 的数组"改为"`const char8_t` 的数组"，`u8'c'` 的类型从 `char` 改为 `char8_t`。

**理由**：让重载、模板特化和类型推导能区分普通字面量与 UTF-8 字面量。

```cpp
const auto *u8s = u8"text";     // 推导结果从 const char* 变成 const char8_t*
const char *ps = u8s;           // error: 现在非良构

auto u8c = u8'c';               // 从 char 变成 char8_t
char *pc = &u8c;                // error: 现在非良构

std::string s = u8"text";       // error: 现在非良构

void f(const char *s);
f(u8"text");                    // error: 现在非良构

template<typename> struct ct;
template<> struct ct<char> { using type = char; };
ct<decltype(u8'c')>::type x;    // error: ct<char8_t> 没有定义
```

**Clang 23 实测**：

```text
error: cannot initialize a variable of type 'const char *' with an lvalue of type 'const char8_t *'
error: cannot initialize a variable of type 'char *' with an rvalue of type 'char8_t *'
error: no viable conversion from 'const char8_t[5]' to 'std::string' (aka 'basic_string<char>')
```

**改写难度**：中等，可能量大。临时方案是 Clang/GCC 的 `-fno-char8_t`（恢复 C++17 语义，非标准）。长期方案：需要 `char` 的地方去掉 `u8` 前缀（前提是执行字符集就是 UTF-8），或用 `reinterpret_cast<const char*>(u8"…")`，或把接口改为 `std::u8string_view`。C++23 恢复了 `char s[] = u8"…"` 这种数组初始化，见 [[diff.cpp20]] [dcl] ¶1。

## Clause [basic]：基础 {#diff.cpp17.basic}

### ¶1 伪析构函数调用结束对象的生命周期

**受影响小节**：[[basic.life]]

**改动**：对标量类型调用**伪析构函数**（[[g:pseudo-destructor]]，如 `a.~T()`，`T` 为 `int`）现在结束该对象的生命周期。C++17 中它是无操作。

**理由**：提高语言模型的一致性。泛型代码对任意 `T` 调用 `p->~T()` 时，无论 `T` 是类还是标量，语义都应当是"对象结束生命周期"。

```cpp ub
int f() {
  int a = 123;
  using T = int;
  a.~T();
  return a;   // UB：现在读取生命周期已结束的对象；C++17 返回 123
}
```

**Clang 23 实测**：运行时两种模式都返回 123（UB 的一种表现）。把 `f` 改成 `constexpr` 并在常量表达式中调用，C++20 模式下 Clang 报 `read of object outside its lifetime is not allowed in a constant expression`，确认了新规则。

**改写难度**：需人工审查。真正受影响的只有"销毁之后接着读"的代码，这类代码在泛型上下文里本来就是错的。

### ¶2 释放序列只由读-改-写操作组成

**受影响小节**：[[intro.races]]

**改动**：除最初的释放操作外，**释放序列**（[[g:release-sequence]]）只包含原子读-改-写操作。C++17 中同一线程随后对同一原子变量的普通写也算在内。

**理由**：删除一个很少使用且令人困惑的特性。

**影响**：如果一个线程先 `store(…, memory_order_release)`，再 `store(…, memory_order_relaxed)` 同一个变量，另一个线程用 `memory_order_acquire` 读到后一个值时，不再与第一次 release store 同步，即使中间没有其他线程写入。

```cpp
std::atomic<int> flag{0};
int data = 0;

// 线程 1
data = 42;
flag.store(1, std::memory_order_release);
flag.store(2, std::memory_order_relaxed);   // C++17：仍在释放序列中；现在：不在

// 线程 2
if (flag.load(std::memory_order_acquire) == 2)
  use(data);   // 现在：与线程 1 的 data = 42 构成数据竞争（UB）；C++17：已同步
```

**改写难度**：需人工审查，编译器不诊断。把第二次 store 也改成 `release`。

## Clause [expr]：表达式 {#diff.cpp17.expr}

### ¶1 隐式 lambda 捕获可能捕获更多实体

**受影响小节**：[[expr.prim.lambda.capture]]

**改动**：带 *capture-default* 的 lambda 现在按**语法**判定隐式捕获：只要在可能求值的表达式中命名了某个局部实体（即使在 `if constexpr` 的弃用分支里，或者该命名并不构成 odr-use），就捕获它。C++17 只在实体被 odr-use 时才捕获。

**理由**：简化规则，并解决与 `constexpr if` 的交互：按 odr-use 判定时，泛型 lambda 是否捕获某个变量要等到实例化后才知道，闭包类型的布局因此依赖于实例化。

```cpp
template<bool B>
void f(int n) {
  [=](auto a) {
    if constexpr (B && sizeof(a) > 4) {
      (void)n;   // 无论 B 和 sizeof(int) 的值如何都捕获 n
    }
  }(0);
}
```

**影响**：闭包对象可能变大，复制的开销增加；捕获可能触发更多的复制构造。

**Clang 23 实测**：`sizeof` 一个只在弃用分支中命名 `n` 的闭包，C++17 和 C++20 模式下都是 4，Clang 把这条回溯到了 C++17。对于命名了常量但未 odr-use 的 `[=] { return x; }`（`const int x = 17`），两种模式下闭包大小都是 1，附录例子说的"实现可以把这个捕获优化掉"正是这种情况。

**改写难度**：通常无需改动。

## Clause [dcl]：声明 {#diff.cpp17.dcl.dcl}

### ¶1 用 typedef 命名以用于链接的无名类只能包含 C 兼容的构造

**受影响小节**：[[dcl.typedef]]

**改动**：`typedef struct { … } S;` 这种"无名类 + typedef 名"（[[g:typedef-name-for-linkage]]）的类里，不能有成员函数、基类、默认成员初始化器、lambda 等 C 中没有的东西。

**理由**：为了可实现性。类的链接名要等读到 typedef 时才确定，而类体内的成员函数等实体在读到 typedef 之前就需要一个确定的名字（例如用于名字修饰）。

```cpp error
typedef struct {
  void f() {}   // error: 现在非良构；C++17 良构
} S;
```

**Clang 23 实测**：两种模式都只给警告：

```text
warning: anonymous non-C-compatible type given name for linkage purposes by typedef declaration; add a tag name here [-Wnon-c-typedef-for-linkage]
```

即 Clang 没有把它当作错误。

**改写难度**：容易，给类加一个名字：`typedef struct S { … } S;` 或直接 `struct S { … };`。

### ¶2 同一函数在不同 TU 中不能有不同的默认实参

**受影响小节**：[[dcl.fct.default]]

**改动**：一个函数在不同翻译单元中的声明，若给同一形参提供默认实参，这些默认实参必须相同。

**理由**：模块需要：一个默认实参可能经由模块接口被导入多个 TU，必须有唯一的含义。

```cpp ifndr
// 翻译单元 1
int f(int a = 42);
int g() { return f(); }

// 翻译单元 2
int f(int a = 76) { return a; }   // IFNDR：现在非良构，不要求诊断；C++17 良构
int g();
int main() { return g(); }        // C++17 中返回 42
```

**影响**：变成 **IFNDR**，编译器和链接器都不会报错。

**改写难度**：需人工审查。把默认实参放到唯一的头文件声明中。

### ¶3 有用户声明构造函数的类不再是聚合

**受影响小节**：[[dcl.init.aggr]]

**改动**：聚合的定义从"没有**用户提供**的构造函数"改为"没有**用户声明**的构造函数"。`= default` 和 `= delete` 也算用户声明。

**理由**：消除容易出错的聚合初始化：C++17 中声明了 `A() = delete;` 的类仍然可以 `A a{};` 初始化，完全绕过了作者的意图。

```cpp
struct A { A() = delete; };                    // C++17 是聚合，现在不是
struct B { B() = default; int i = 0; };        // 同上
struct C { C(C&&) = default; int a, b; };      // 同上

A a{};                  // error: 现在非良构
B b = {1};              // error: 现在非良构
auto* c = new C{2, 3};  // error: 现在非良构

struct Y;
struct X { operator Y(); };
struct Y {              // C++17 是聚合，现在不是
  Y(const Y&) = default;
  X x;
};
Y y{X{}};               // 现在：调用复制构造函数（经 X::operator Y）；C++17：聚合初始化 y.x
```

**Clang 23 实测**：

```text
$ clang++ -std=c++20 ...
error: call to deleted constructor of 'A'
error: no matching constructor for initialization of 'B'
error: no matching constructor for initialization of 'C'
```

C++17 模式下全部通过。

**改写难度**：容易到中等。最常见的写法是 `struct P { P() = default; int x, y; }; P p{1, 2};`：删掉那行 `= default`（它本来就是多余的），类重新成为聚合。如果构造函数是为了别的目的声明的，就补一个真正的构造函数。

### ¶4 指针/成员指针到 `bool` 的转换是收窄转换

**受影响小节**：[[dcl.init.list]]

**改动**：在列表初始化中，从指针或成员指针类型到 `bool` 的转换算作**收窄转换**（[[g:narrowing-conversion]]）。

**理由**：捕获 bug。

```cpp error
bool y[] = { "bc" };   // error: 现在非良构；C++17 良构
```

**Clang 23 实测**：两种模式都报 `type 'const char[3]' cannot be narrowed to 'bool' in initializer list`，Clang 把这条作为 DR 回溯了。

**改写难度**：容易，显式写 `p != nullptr`。

## Clause [class]：类 {#diff.cpp17.class}

### ¶1 `explicit` 后面不能紧跟带括号的构造函数名

**受影响小节**：[[class.ctor]]、[[class.conv.fct]]

**改动**：构造函数声明中，`explicit` 后面不能紧跟带括号的类名；转换函数同理。

**理由**：为 `explicit(bool)` 让路：`explicit (S)(…)` 现在会被解析为 `explicit(` 条件 `)`。

```cpp
struct S {
  explicit (S)(const S&);       // error: 现在非良构；C++17 良构
  explicit (operator int)();    // error: 现在非良构；C++17 良构
  explicit(true) (S)(int);      // OK
};
```

**Clang 23 实测**：C++20 下 `'S' does not refer to a value` 等错误。

**改写难度**：容易，去掉括号。

### ¶2 构造函数和析构函数的 *declarator-id* 不能是 *simple-template-id*

**受影响小节**：[[class.ctor]]、[[class.dtor]]

**改动**：类模板内声明构造函数或析构函数时，不能写成 `A<T>()`、`~A<T>()`，只能用注入类名 `A`。

**理由**：删除一种容易出错的冗余写法。

```cpp error
template<class T>
struct A {
  A<T>();       // error: 现在非良构
  A(int);       // OK
  ~A<T>();      // error: 现在非良构
};
```

**Clang 23 实测**：C++20 模式下（加 `-pedantic` 也一样）**没有任何诊断**，Clang 尚未实现这条限制。GCC 会报错，所以跨编译器的代码要尽早改掉。

**改写难度**：容易，删掉 `<T>`。

### ¶3 隐式移动的适用范围扩大

**受影响小节**：[[class.copy.elision]]

**改动**：两处扩大：(1) 返回一个可隐式移动的实体时，可以调用接受**不同类型**右值引用的构造函数（例如返回派生类局部变量，用基类的移动构造函数）；(2) 函数形参和 catch 子句形参也可以在 `throw` 中被移动。

**理由**：让写出高效代码更容易。

**影响**：原来选复制构造函数的地方现在选移动构造函数。如果移动构造函数不可访问，就编译失败；如果移动的语义与复制不同，行为改变：

```cpp
struct base {
  base();
  base(base const&);
private:
  base(base&&);
};
struct derived : base {};

base f(base b) {
  throw b;          // error: base(base&&) 是私有的
  derived d;
  return d;         // error: base(base&&) 是私有的
}

struct S {
  S(const char* s) : m(s) { }
  S(const S&) = default;
  S(S&& other) : m(other.m) { other.m = nullptr; }
  const char* m;
};

S consume(S&& s) { return s; }   // 现在移动 s（即调用者的对象）

void g() {
  S s("text");
  consume(static_cast<S&&>(s));
  char c = *s.m;   // UB：s.m 已被置空；C++17 中 s 被复制，没问题
}
```

**Clang 23 实测**：`f` 在 C++17 和 C++20 模式下都报 `calling a private constructor of class 'base'`；`g` 之后打印 `s.m`，两种模式下都是 `0x0`。Clang 把这一改动回溯到了 C++17。

**改写难度**：需人工审查。特别注意 `S&&` 形参被 `return` 时会移动走调用者的对象。

## Clause [over]：重载 {#diff.cpp17.over}

### ¶1 相等/不等表达式会找到反向和改写候选

**受影响小节**：[[over.match.oper]]

**改动**：`x == y` 除了查找 `operator==(x, y)`，还会考虑**反向候选** `operator==(y, x)`；`x != y` 还会考虑由 `operator==` **改写**而来的候选（[[g:rewritten-candidate]]）。

**理由**：与三路比较保持一致，只写一个 `operator==` 就能得到完整的四种相等比较。

**影响**：某些类型对之间，`==`、`!=` 会调用不同的运算符；某些类型自身之间的比较变成歧义：

```cpp
struct A {
  operator int() const;
};

bool operator==(A, int);        // #1
// #2 内置候选：bool operator==(int, int);
// #3 内置候选：bool operator!=(int, int);

int check(A x, A y) {
  return (x == y) +             // 现在：歧义（非良构）；C++17 良构
    (10 == x) +                 // 现在调用 #1（反向）；C++17 选 #2
    (10 != x);                  // 现在调用 #1（改写为 !(x == 10)）；C++17 选 #3
}
```

`x == y`：#1 正向（`y` 转换成 `int`）和 #1 反向（`x` 转换成 `int`）同样好，于是歧义。

**Clang 23 实测**：给 `#1` 加上打印，`10 == A()` 和 `10 != A()` 在 C++17 下什么都不打印（用了内置比较），在 C++20 下都打印 `#1`。而 `x == y` 这种标准说非良构的情况，Clang 只给警告并照常选一个：

```text
warning: ISO C++20 considers use of overloaded operator '==' (with operand types 'A' and 'A') to be ambiguous despite there being a unique best viable function [-Wambiguous-reversed-operator]
```

**改写难度**：中等，需人工审查（静默改变调用的函数）。

### ¶2 相等运算符的重载决议可能改变

**受影响小节**：[[over.match.oper]]

**改动与理由**：同上，从"支持以相反顺序调用 `operator==`"的角度登记。

```cpp
struct B {
  bool operator==(const B&);    // 没有 const 限定的成员函数
};
B b1;
bool eq = (b1 == b1);           // 现在：歧义；C++17 良构
```

正向候选 `b1.operator==(b1)` 的隐式对象形参是非 const 的 `B&`，实参是 `const B&`；反向候选正好反过来。两个候选各有一个实参匹配得更好，于是歧义。

**Clang 23 实测**：同样只给 `-Wambiguous-reversed-operator` 警告。

**改写难度**：容易。给成员 `operator==` 加 `const`，这本来就该有。

## Clause [temp]：模板 {#diff.cpp17.temp}

### ¶1 后跟 `<` 且查找无结果或找到函数的名字被当作模板名

**受影响小节**：[[temp.names]]

**改动**：一个 *unqualified-id* 后面跟着 `<`，如果名字查找什么也没找到，或者找到的是函数，就把它当作 *template-name*，以便进行 ADL。

**理由**：C++17 中要用显式模板实参调用一个只能经 ADL 找到的函数模板（`get<0>(t)`），必须先让普通查找能看见某个同名模板，否则 `get < 0` 会被当成小于号。

```cpp
struct A {};
bool operator<(void (*fp)(), A);
void f() {}
int main() {
  A a;
  f < a;    // error: 现在非良构（f 被当作模板名）；C++17 良构
  (f) < a;  // 仍然良构
}
```

**Clang 23 实测**：C++20 下 `expected '>'`。

**改写难度**：容易，加括号。

## Clause [except]：异常处理 {#diff.cpp17.except}

### ¶1 删除 `throw()` 异常说明

**受影响小节**：[[except.spec]]

**改动**：`throw()` 不再是合法的异常说明。

**理由**：删除已经被 `noexcept` 取代的过时特性。

**影响**：使用 `throw()` 的函数声明、函数指针声明等非良构。替换成 `noexcept` 即可，含义自 C++17 起就完全一样。

```cpp error
void f() throw();   // error: 现在非良构；改成 void f() noexcept;
```

!!! note "跨 C++03 与 C++20 的头文件"
    附录特别注明：没有一种写法能同时在当前标准和 C++03 下都表示"不抛出"，只能用预处理器根据 `__cplusplus` 生成不同的 token。

**Clang 23 实测**：`void f() throw();` 在 `-std=c++20` 乃至 `-std=c++2c` 下都**被接受**，默认没有任何诊断；加 `-Wdeprecated` 才有 `warning: dynamic exception specifications are deprecated [-Wdeprecated-dynamic-exception-spec]`。带类型的 `throw(int)` 则从 C++17 起就报错（见 [[diff.cpp14]]）。

**改写难度**：容易，机械替换。

## Clause [library]：库引言 {#diff.cpp17.library}

### ¶1 新头文件

**受影响小节**：[[headers]]

`<barrier>`、`<bit>`、`<charconv>`、`<compare>`、`<concepts>`、`<coroutine>`、`<format>`、`<latch>`、`<numbers>`、`<ranges>`、`<semaphore>`、`<source_location>`、`<span>`、`<stop_token>`、`<syncstream>`、`<version>`。

注意 `<version>`：有些项目在 include 路径里放了一个名叫 `version` 的文件（例如记录版本号），在大小写不敏感的文件系统上 `VERSION` 也会撞上。libc++ 的其他头文件会 `#include <version>`，拿到错误的文件就会出现莫名其妙的错误。

### ¶2 删除空洞的 C++ 头文件

**改动**：删除 `<ccomplex>`、`<ciso646>`、`<cstdalign>`、`<cstdbool>`、`<ctgmath>`。

**理由**：这些头文件内容为空或只是转发，它们的存在暗示了一个并不存在的"与 C 兼容"的要求。

**替换**：`<ccomplex>` → `<complex>`；`<ctgmath>` → `<cmath>` + `<complex>`；`<ciso646>`、`<cstdalign>`、`<cstdbool>` 直接删掉。

**libc++ 实测**：五个头文件在 C++20 模式下仍能包含，且没有警告。

**改写难度**：容易。

## Clause [containers]：容器库 {#diff.cpp17.containers}

### ¶1 `remove`、`remove_if`、`unique` 的返回类型

**受影响小节**：[[forward.list]] 与 [[list]]

**改动**：`list` 和 `forward_list` 的这三个成员函数返回类型从 `void` 改为 `size_type`（被删除的元素个数）。

**影响**：依赖返回类型的代码（取成员函数指针、`decltype`）可能改变含义；用 C++17 和 C++20 编译的 TU 之间可能**链接失败或 UB**（返回类型是修饰名的一部分，或调用约定不同）。

**libc++ 实测**：`static_assert(is_same_v<decltype(list<int>{}.remove(1)), void>)` 在 C++17 下通过，C++20 下失败（实际为 `unsigned long`）。

**改写难度**：容易；混合标准链接的问题需人工审查。

## Clause [iterators]：迭代器库 {#diff.cpp17.iterators}

### ¶1 `iterator_traits<void*>` 与函数指针特化不再有嵌套类型

**受影响小节**：[[iterator.traits]]

**改动**：`iterator_traits` 对 `void*` 和函数指针类型的特化不再包含任何嵌套 typedef。

**理由**：纠正把不可递增的指针类型误认作迭代器类型的问题。

**libc++ 实测**：C++17 下访问 `iterator_traits<void*>::value_type` 是硬错误（`cannot form a reference to 'void'`，在库内部）；C++20 下是干净的 `no type named 'value_type'`，可以被 SFINAE 检测。

**改写难度**：容易。

## Clause [algorithms]：算法库 {#diff.cpp17.alg.reqs}

### ¶1 算法的可推导模板形参的个数和顺序未指定

**受影响小节**：[[algorithms.requirements]]

**改动**：算法声明中可推导模板形参的个数和顺序，从"与声明一致"改为**未指定**。

**理由**：给实现者更多自由，允许把一些函数模板实现成带模板调用运算符的函数对象（`std::ranges::` 中的算法正是这样，它们是 niebloid）。

**影响**：给算法显式传模板实参（`std::find<It, int>(…)`）的代码，除非该算法被明确规定允许这样做，否则可能编译失败或有 UB。

**改写难度**：容易。不要给算法写显式模板实参，让推导完成。

## Clause [input.output]：输入/输出库 {#diff.cpp17.input.output}

### ¶1 字符数组提取只接受数组类型

**受影响小节**：[[istream.extractors]]

**改动**：`operator>>(basic_istream&, charT*)` 改为 `operator>>(basic_istream&, charT(&)[N])`。

**理由**：在编译期防止缓冲区溢出：库现在知道目标数组的大小。

```cpp
auto p = new char[100];
char q[100];
std::cin >> std::setw(20) >> p;   // error: 现在非良构
std::cin >> std::setw(20) >> q;   // OK
```

**libc++ 实测**：C++20 下 `invalid operands to binary expression ('basic_istream<char, std::char_traits<char>>' and 'char *')`。

**改写难度**：容易。读进 `std::string`，或改用数组。

### ¶2 `u8` 字面量传给 `ostream::operator<<`

**受影响小节**：[[ostream.inserters.character]]

**改动**：`basic_ostream<char>` 和 `basic_ostream<wchar_t>` 对 `char8_t`、`const char8_t*` 的插入运算符被**删除**（`= delete`）。

**理由**：`u8` 字面量的类型变成 `char8_t` 之后，如果不删除，`cout << u8"text"` 会选中 `const void*` 重载打印地址，`cout << u8'X'` 会打印整数。

```cpp
std::cout << u8"text";   // C++17：打印字符串；现在：非良构
std::cout << u8'X';      // C++17：打印字符；现在：非良构
```

**libc++ 实测**：`overload resolution selected deleted operator '<<'`。

**改写难度**：容易。

### ¶3 `wchar_t` / `char16_t` / `char32_t` 传给 `ostream<char>`

**受影响小节**：[[ostream.inserters.character]]

**改动**：`basic_ostream<char>` 对 `wchar_t`、`char16_t`、`char32_t` 字符和字符串的插入运算符被删除；`basic_ostream<wchar_t>` 对 `char16_t`、`char32_t` 的同样被删除。

**理由**：消除令人惊讶的行为：C++17 中 `cout << u"text"` 打印指针值，`cout << u'X'` 打印整数 88。

**libc++ 实测**：`std::cout << u"text"`、`u'X'`、`L'X'` 在 C++20 下都报 `overload resolution selected deleted operator '<<'`。

**改写难度**：容易。

### ¶4 `path::u8string()` 返回 `std::u8string`

**受影响小节**：[[fs.class.path]]

**改动**：`std::filesystem::path` 的 `u8string()` 和 `generic_u8string()` 返回 `std::u8string` 而不是 `std::string`。

```cpp error
std::filesystem::path p;
std::string s1 = p.u8string();          // error: 现在非良构
std::string s2 = p.generic_u8string();  // error: 现在非良构
```

**libc++ 实测**：`no viable conversion from 'basic_string<char8_t>' to 'basic_string<char>'`。

**改写难度**：容易。改用 `p.string()`（本机编码）或显式转换。

## Annex [depr]：兼容性特性 {#diff.cpp17.depr}

C++20 删除了一批在 C++17 中弃用的库设施。libc++ 在 C++17 下对它们都给出 `-Wdeprecated-declarations` 警告，在 C++20 下全部报"不存在"。

### ¶1 删除 `uncaught_exception`

**理由**：多个异常同时处于活动状态时它的含义不清，已被 `uncaught_exceptions()`（返回个数）取代。

**改写**：`std::uncaught_exception()` → `std::uncaught_exceptions() > 0`；用在析构函数里判断"是否因栈展开而析构"时，正确做法是在构造时记录 `uncaught_exceptions()`，析构时比较。

### ¶2 删除可适配函数 API

**改动**：标准库类中的 `result_type`、`argument_type`、`first_argument_type`、`second_argument_type` 嵌套类型，以及 `not1`、`not2`、`unary_negate`、`binary_negate` 被删除。

**理由**：这套约定只覆盖一元和二元函数，无法扩展到一般情况和新的语言特性；已被 `decltype`、`std::bind`、`std::not_fn` 取代。

**改写**：`std::not1(f)` → `std::not_fn(f)`；`F::result_type` → `std::invoke_result_t<F, Args...>`。

### ¶3 删除 `std::allocator` 的冗余成员

**改动**：删除 `pointer`、`const_pointer`、`reference`、`const_reference`、`rebind`、`address`、`construct`、`destroy`、`max_size`，以及带提示参数的 `allocate`。

**理由**：`std::allocator` 规定过度，鼓励用户容器直接使用这些成员，而不是经由 `std::allocator_traits`。

**改写**：一律经过 `std::allocator_traits<A>`：`traits::pointer`、`traits::construct(a, p, args...)`、`traits::rebind_alloc<U>`。

### ¶4 删除 `raw_storage_iterator`

**理由**：它鼓励使用可能抛出的算法，却不返回成功构造的元素个数，出现异常时无法正确销毁已构造的部分。

**改写**：用 `std::uninitialized_copy` 等算法（它们在异常时会销毁已构造的元素）。

### ¶5 删除临时缓冲区 API

**改动**：删除 `get_temporary_buffer` 和 `return_temporary_buffer`。

**理由**：本意是为小块内存请求提供高效优化，但实际中没有证据表明它做到了，用户还得自己写异常安全的包装。

**改写**：`std::make_unique_for_overwrite<T[]>(n)` 或 `std::allocator<T>`。

### ¶6 删除 `shared_ptr::unique`

**理由**：在多线程和存在 `weak_ptr` 的情况下，这个结果不可靠。`use_count` 同样不可靠，但它的契约更清楚，并且在单线程中有明确的用途，所以保留。

**改写**：`p.unique()` → `p.use_count() == 1`，并意识到它在并发下没有意义。

### ¶7 删除弃用的类型特征

**受影响小节**：[[depr.meta.types]]

**改动**：删除 `is_literal_type`、`is_literal_type_v`、`result_of`、`result_of_t`。

**理由**：`is_literal_type` 无法告诉你类型的哪些成员函数是 `constexpr` 的，几乎没有用；`result_of<F(Args...)>` 的语法令人意外，而且不直接支持函数类型，已被 `invoke_result` 取代。

**libc++ 实测**（C++17 → C++20）：

```text
warning: 'uncaught_exception' is deprecated [-Wdeprecated-declarations]
warning: 'not1<std::function<bool (int)>>' is deprecated [-Wdeprecated-declarations]
warning: 'result_of<int (*())()>' is deprecated [-Wdeprecated-declarations]
→
error: no member named 'uncaught_exception' in namespace 'std'; did you mean 'uncaught_exceptions'?
error: no member named 'not1' in namespace 'std'
error: no template named 'result_of' in namespace 'std'
```

**改写**：`result_of_t<F(Args...)>` → `invoke_result_t<F, Args...>`。

## 小结

| 条目 | 类型 | Clang 23 / libc++ |
|---|---|---|
| `module` / `import` 行 | 改变含义 | 已实现 |
| 新关键字 | 非良构 | 已实现；`-Wc++20-compat` 可预警 |
| `<=>` token | 非良构 | 已实现；`-Wc++20-compat` 可预警 |
| `u8` → `char8_t` | 非良构 | 已实现 |
| 伪析构结束生命周期 | UB | 常量求值中可见 |
| 释放序列 | 数据竞争 | — |
| 隐式捕获 | 闭包变大 | 已实现并回溯 |
| typedef 无名类 | 非良构 | 只警告 |
| 跨 TU 默认实参 | IFNDR | — |
| 聚合定义 | 非良构 / 改变含义 | 已实现 |
| 指针 → `bool` 收窄 | 非良构 | 已实现并回溯 |
| `explicit (S)` | 非良构 | 已实现 |
| `A<T>()` 构造函数 | 非良构 | **未实现** |
| 隐式移动扩大 | 非良构 / 改变行为 | 已实现并回溯 |
| 反向 `==` | 歧义 / 调用不同函数 | 实现；歧义只警告 |
| `f < a` | 非良构 | 已实现 |
| `throw()` | 非良构 | **未实现**（默认静默接受） |
| iostream / filesystem 四条 | 非良构 | 已实现 |
| 删除空 C 头文件 | 非良构 | libc++ 仍提供 |
| Annex D 删除项 | 非良构 | 已删除 |
