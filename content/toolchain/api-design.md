---
title: API 设计与演进
summary: 怎样设计难以误用、能够演进的 C++ 接口：用形参和返回类型表达所有权与可空性，const 与引用限定符，让非法状态无法表示，nodiscard、deprecated 和 noexcept 作为契约的一部分，库作者面对的重载集合与 ADL 风险，以及在不破坏用户的前提下修改接口、给用户提供特性检测宏、记录前置条件。
group: 工程实践
status: draft
order: 130
since: c++98
papers: P0012R1, P2573R2, P1301R4, P1771R1, P0061R1, P0941R2, P2988, N3279, P2900R14
related: dcl.fct, except.spec, conv.fctptr, dcl.attr.nodiscard, dcl.attr.deprecated, dcl.fct.def.delete, dcl.fct.default, over.match.funcs.general, basic.scope.scope, basic.lookup.argdep, namespace.def, cpp.cond, cpp.predefined, version.syn, structure.specifications, topics/ownership-and-smart-pointers, topics/dangling-references, topics/name-lookup-and-customization, topics/exception-safety, patterns/strong-types, patterns/named-parameters, toolchain/library-boundaries, toolchain/error-handling-strategy
tags: API, 接口设计, 兼容性, noexcept, nodiscard, deprecated, 特性检测, 工程实践
updated: 2026-10-19
---

!!! tldr
    - 形参类型就是文档：`const T&` 是不能为空的只读借用，`T*` 是可以为空的借用，按值的 `unique_ptr<T>` 是接管所有权，`span` 和 `string_view` 借用一段数据。选对类型，误用就变成编译错误。
    - 返回值、`optional` 和 `expected` 分别表达一定有结果、可能没有结果、可能失败。不要返回拥有所有权的裸指针；返回内部数据的引用时，用引用限定符拒绝在临时对象上调用。
    - `[[nodiscard]]`、`[[deprecated("...")]]`、`= delete("...")` 把使用规则交给编译器检查。`noexcept` 从 C++17 起是函数类型的一部分，加上容易，去掉会破坏用户。
    - 库作者往用户类型所在的命名空间加一个泛型函数模板，就可能通过 ADL 悄悄改变用户代码调用的函数。泛型操作用函数对象，运算符用隐藏友元。
    - 源码兼容和二进制兼容是两回事。加默认实参与加重载破坏的东西不同；删除要先经过一个带说明的 `[[deprecated]]` 版本；新功能要给用户一个可以 `#if` 的宏。

## 一个容易用错的接口

```cpp
void open(const char* path, bool write, bool create);
Widget* make_widget();
const std::string& Person::name() const;
```

这三个声明都能编译，也都能写出看起来正常的调用：`open("f", true, false)` 读不出哪个 `bool` 是哪个，换了顺序也照样编译；`make_widget()` 返回的指针由谁 `delete` 只能看文档；`load().name()` 返回一个指向临时对象成员的引用，表达式结束后就悬垂了。

**API 设计**要做的，是让正确的用法容易写，让错误的用法写不出来或者至少收到警告。C++ 的类型系统、属性和重载规则提供了大部分工具。本页按调用的组成部分逐个讨论：形参、返回值、成员函数的限定、属性，最后讨论接口发布之后怎样修改它。

二进制层面的约定（布局、vtable、符号可见性）见 [[toolchain/library-boundaries|库边界]]，错误报告机制的选择见 [[toolchain/error-handling-strategy|错误处理策略]]。

## 形参类型表达所有权和可空性

一个形参要回答三个问题：函数是否取得对象的所有权，函数是否修改对象，调用方能否传入“没有对象”。下表给出常用写法的约定含义。

| 形参 | 含义 | 能否为空 | 典型调用 |
|---|---|---|---|
| `T`（按值） | 函数得到自己的一份；对可移动的类型也用于“接收并保存” | 不适用 | `f(x)`、`f(std::move(x))` |
| `const T&` | 只读借用，函数返回后不再使用 | 不能 | `f(x)` |
| `T&` | 可写借用，函数会修改调用方的对象 | 不能 | `f(x)` |
| `const T*`、`T*` | 借用，`nullptr` 表示没有对象 | 能 | `f(&x)`、`f(nullptr)` |
| `T&&`（非模板） | 只接受右值，函数可能从中移走资源 | 不能 | `f(std::move(x))` |
| `std::unique_ptr<T>`（按值） | 接管所有权 | 能 | `f(std::move(p))` |
| `std::shared_ptr<T>`（按值） | 保存一份共享所有权 | 能 | `f(p)` |
| `std::span<const T>`、`std::span<T>` | 借用一段连续元素，只读或可写 | 可以为空范围 | `f(vec)`、`f(arr)` |
| `std::string_view` | 借用一段字符，不保证以空字符结尾 | 可以为空串 | `f("lit")`、`f(str)` |
| `std::optional<T>`（按值） | 可选的输入，函数得到一份副本 | 能（`std::nullopt`） | `f(5)`、`f(std::nullopt)` |
| `std::optional<const T&>` {{c++26}} | 可选的只读借用 | 能 | `f(x)`、`f(std::nullopt)` |

智能指针各种传法的细节和理由见 [[topics/ownership-and-smart-pointers]]，这里只强调一点：只想使用对象的函数应该接受 `T&` 或 `T*`，不要接受智能指针，否则栈上的对象和别的所有者持有的对象都传不进来。

类型选对之后，几种常见的误用直接变成编译错误：

```cpp title="params.cpp"
#include <memory>
#include <span>
#include <string>
#include <string_view>

struct Widget { int id; };

void inspect(const Widget& w);               // 只读借用，不能为空
void adopt(std::unique_ptr<Widget> w);       // 接管所有权
void sum(std::span<const int> xs);           // 借用一段连续元素
void greet(std::string_view name);           // 借用字符序列

void use() {
  auto p = std::make_unique<Widget>();
  inspect(nullptr);    // error: 引用不能为空
  adopt(p);            // error: 必须显式交出所有权
  adopt(std::move(p)); // OK
  int a[] = {1, 2, 3};
  sum(a);              // OK
  std::string_view sv = std::string("temp");   // 悬垂
  greet(sv);
}
```

本机 Clang 23 加 `-Wall -Wextra -pedantic` 的诊断（省略了源码行）：

```text
params.cpp:15:3: error: no matching function for call to 'inspect'
params.cpp:8:6: note: candidate function not viable: no known conversion from 'std::nullptr_t' to 'const Widget' for 1st argument
params.cpp:16:9: error: call to implicitly-deleted copy constructor of 'std::unique_ptr<Widget>'
params.cpp:20:25: warning: object backing the pointer will be destroyed at the end of the full-expression [-Wdangling-gsl]
```

`adopt(p)` 的错误说明了为什么接管所有权要按值接受 `unique_ptr`：调用处必须写出 `std::move`，读代码的人一眼就知道 `p` 此后为空。

借用类型（引用、指针、`span`、`string_view`）的共同风险是悬垂：函数把借来的东西存起来，而调用方的对象先死了。所以有一条配套的约定：接受借用的函数不在返回后继续使用它；需要保存时，接受按值的拥有型类型（`std::string`、`std::vector<T>`）。各种悬垂途径和编译器能诊断到什么程度见 [[topics/dangling-references]]。

!!! pitfall "`string_view` 不是 C 字符串"
    `std::string_view` 指向的字符序列不一定以 `'\0'` 结尾。把 `sv.data()` 传给 `fopen`、`strlen` 这类需要空字符结尾的 C 函数，可能读到范围之外。底层要调 C 接口的函数，形参用 `const std::string&` 或 `const char*`。

!!! note "`T&&` 与按值"
    非模板的 `T&&` 形参强迫调用方写 `std::move` 或传临时对象，对只想复制一份的调用方不友好。对 `std::string`、`std::vector` 这类移动很便宜的类型，推荐“按值接受，再移动进成员”：调用方传左值时复制一次，传右值时只移动，函数只写一个。模板中的 `T&&` 是转发引用，含义完全不同（[[g:forwarding-reference]]）。

## 返回类型

| 返回类型 | 含义 |
|---|---|
| `T` | 一定产生一个结果，调用方拥有它 |
| `std::optional<T>` | 可能没有结果，没有结果不是错误（例如查找） |
| `std::expected<T, E>` | 可能失败，失败时带回原因 |
| `std::unique_ptr<T>` | 返回一个新对象的所有权，需要多态或稳定地址时使用 |
| `const T&`、`std::string_view`、`std::span` | 借出内部数据，有效期受对象生命周期约束 |
| `std::optional<const T&>` {{c++26}} | 可能借出，也可能没有 |

`optional` 与 `expected` 的取舍、`expected` 在模块边界上的用法见 [[toolchain/error-handling-strategy]]。

本机 libc++ 已经实现了 `std::optional<T&>`（`__cpp_lib_optional` 为 `202506`，[[P2988]]）。`sizeof(std::optional<const Config&>)` 在本机是 8，和一个指针一样大：它实际上就是一个带着明确语义的可空指针。

### 不返回拥有所有权的裸指针

```cpp run title="owning.cpp" ok
#include <cstdio>
#include <memory>

struct Conn { int fd = 3; };

Conn* open_raw() { return new Conn; }              // 谁来 delete？
std::unique_ptr<Conn> open() { return std::make_unique<Conn>(); }

int main() {
  int fd1 = open_raw()->fd;     // 泄漏：没有人拥有这个对象
  int fd2 = open()->fd;         // 临时 unique_ptr 在完整表达式结束时释放
  std::printf("%d %d\n", fd1, fd2);
}
```

内存泄漏不是 UB，程序良构，但第一个调用泄漏了。本机用 `-fsanitize=address` 构建并以 `ASAN_OPTIONS=detect_leaks=1` 运行，LeakSanitizer 报告 `Direct leak of 4 byte(s) in 1 object(s)`，分配点是 `open_raw()`。返回 `unique_ptr` 时同样的写法不会泄漏，因为所有权落在一个临时对象上，由它负责释放。

库在 C 接口上不得不返回裸指针时，要提供配对的销毁函数，见 [[toolchain/library-boundaries]]。

## const 与引用限定符

### const 成员函数

`const` 成员函数承诺不修改对象的可观察状态，它可以在 `const` 对象和 `const T&` 上调用。从重载决议的角度看，成员函数有一个隐含的对象形参：没有 cv 限定的成员函数，这个形参是 `X&`；`const` 成员函数是 `const X&`（[[over.match.funcs.general#4]]）。所以按 `const` 重载就是按对象形参的类型重载，`std::vector::operator[]` 就是这样提供只读和可写两个版本的。

推荐的做法是先把所有成员函数写成 `const`，确实需要修改时再去掉。一个本应是 `const` 却没有标的函数，会让所有只拿到 `const T&` 的调用方都无法使用它，而事后补上 `const` 不会破坏任何调用方。

### 返回内部引用的访问器

```cpp run title="refq.cpp" ub
#include <cstdio>
#include <string>
#include <utility>

class Person {
  std::string name_;
public:
  explicit Person(std::string n) : name_(std::move(n)) {}
  const std::string& name() const { return name_; }
};

Person load() { return Person("a fairly long name, no SSO"); }

int main() {
  const std::string& n = load().name();   // 临时 Person 已销毁
  std::printf("%zu\n", n.size());
}
```

`load()` 返回的临时对象在完整表达式结束时销毁，`n` 引用的是它已经销毁的成员。本机 Clang 23 加 `-Wall -Wextra` 对这段代码没有任何警告；`-fsanitize=address` 运行时报告 `stack-use-after-scope`。

引用限定符（ref-qualifier）可以按对象是左值还是右值区分成员函数：带 `&` 的版本只能在左值上调用，带 `&&` 的版本只能在右值上调用（[[over.match.funcs.general#4]]）。右值版本可以把成员移出去，返回值而不是引用：

```cpp run title="refq2.cpp" ok
#include <cstdio>
#include <string>
#include <utility>

class Person {
  std::string name_;
public:
  explicit Person(std::string n) : name_(std::move(n)) {}
  const std::string& name() const& { return name_; }
  std::string name() && { return std::move(name_); }
};

Person load() { return Person("a fairly long name, no SSO"); }

int main() {
  Person p = load();
  const std::string& a = p.name();        // 左值：返回引用
  const std::string& b = load().name();   // 右值：返回值，生命周期延长
  std::printf("%zu %zu\n", a.size(), b.size());
}
```

本机输出 `26 26`，ASan 无报告。`b` 绑定到 `name() &&` 返回的临时 `std::string` 上，这个临时对象的生命周期延长到 `b` 的作用域结束。

返回 `string_view` 或 `span` 这类视图时，没有可以延长的东西，可以直接删除右值版本：

```cpp title="view.cpp" error
#include <string>
#include <string_view>

class Person {
  std::string name_;
public:
  std::string_view view() const& { return name_; }
  std::string_view view() const&& = delete("would dangle");
};
Person load();

void use(const Person& p) {
  std::string_view a = p.view();        // OK
  std::string_view b = load().view();   // error: 调用已删除的函数
}
```

```text
view.cpp:14:31: error: call to deleted member function 'view': would dangle
```

`= delete("理由")` 是 C++26 的写法（[[dcl.fct.def.delete#2]]，[[P2573R2]]），本机 Clang 23 已支持，诊断里带上了理由。删除右值版本的代价是 `print(load().view())` 这种完全安全的用法也被拒绝了，所以它适合视图很可能被保存的接口。另一个办法是 Clang 的 `[[clang::lifetimebound]]`：本机给 `refq.cpp` 中的 `name()` 加上它之后，`const std::string& n = load().name();` 得到 `-Wdangling` 警告，而在完整表达式内部使用结果不受影响，详见 [[topics/dangling-references]]。

!!! pitfall "带引用限定符和不带的不能混用"
    同一个名字、同样形参的成员函数，不能一个带引用限定符、另一个不带：`int f() const;` 和 `int f() const&&;` 被视为同一个函数的重复声明（[[basic.scope.scope#3.1]]），本机报 `class member cannot be redeclared`。要用引用限定符区分，两个版本都要写上，例如 `const&` 和 `const&&`。

builder 的方法链如何利用引用限定符（以及 C++23 的显式对象形参），见 [[patterns/named-parameters]]。

## 让非法状态无法表示

### 用类型代替 bool 和裸整数

```cpp title="states.cpp" error
#include <chrono>

enum class Mode { read, write };
enum class Create : bool { no, yes };

void open(const char* path, Mode m, Create c);

void use() {
  open("f", Mode::write, Create::yes);   // OK
  open("f", Create::yes, Mode::write);   // error: 顺序错了
  open("f", 1, true);                    // error: 没有隐式转换
}
```

```text
states.cpp:10:3: error: no matching function for call to 'open'
states.cpp:6:6: note: candidate function not viable: no known conversion from 'Create' to 'Mode' for 2nd argument
states.cpp:11:3: error: no matching function for call to 'open'
states.cpp:6:6: note: candidate function not viable: no known conversion from 'int' to 'Mode' for 2nd argument
```

限定作用域枚举（`enum class`，[[g:scoped-enumeration]]）不会隐式转换为整数，也不能从整数隐式转换过来，两个不同的枚举之间更不能互换。同样的思路推广到数值：把米和秒、用户 ID 和订单 ID 包成不同的类型，参数顺序写错就是编译错误，做法与零开销的条件见 [[patterns/strong-types]]。参数很多时，选项聚合配合指派初始化器让调用处写出参数名，见 [[patterns/named-parameters]]。

`std::chrono::duration` 是标准库里的例子：接受 `std::chrono::milliseconds` 的函数不接受 `50`，因为从整数构造 `duration` 的构造函数是 `explicit` 的；传 `2s` 可以，因为秒到毫秒是无损转换。

### 删除不想要的转换

有时形参必须是基本类型，但不想接受隐式转换来的实参：

```cpp title="del.cpp" error
void set_percent(int p);
template <class T>
void set_percent(T) = delete("set_percent takes exactly int");

void use(double ratio, short s) {
  set_percent(ratio * 100);   // error: 否则 double -> int 静默截断
  set_percent(s);             // error: short -> int 无损，也被拒绝
  set_percent(42);            // OK
}
```

去掉删除的模板，本机 `-Wall -Wextra -pedantic` 对前两个调用都没有警告。加上之后，模板对 `double` 和 `short` 推导出精确匹配，比需要转换的 `set_percent(int)` 更好，被选中而又是已删除的函数，于是非良构（[[dcl.fct.def.delete#2]]）。对 `int` 实参两者一样好，非模板优先。诊断附带了理由：

```text
del.cpp:6:3: error: call to deleted function 'set_percent': set_percent takes exactly int
del.cpp:3:6: note: candidate function [with T = double] has been explicitly deleted
```

### 构造时建立不变式

一个值的合法范围比它的类型窄时（端口号是 1 到 65535 的 `int`），可以把检查放进一个类的构造中：构造函数 `explicit`，失败时抛出异常，或者把构造函数设为私有，只提供返回 `std::expected<Port, Error>` 的工厂函数。此后所有接受 `Port` 的函数都不必再检查。这个例子的完整写法见 [[toolchain/error-handling-strategy]]。

## nodiscard 与 deprecated

### `[[nodiscard]]`

`[[nodiscard]]` 可以标在函数、构造函数和类型上；丢弃 nodiscard 调用的结果时，标准建议实现给出警告，并在警告中使用属性里的字符串（[[dcl.attr.nodiscard#4]]）。标在类型上的效果、以及 libc++ 的 `std::expected` 不是 nodiscard 类型这件事，见 [[toolchain/error-handling-strategy]]。这里讨论哪些函数值得标。

```cpp title="attrs.cpp"
#include <memory>
#include <mutex>
#include <vector>

class Lock {
public:
  [[nodiscard("the lock is released immediately")]]
  explicit Lock(std::mutex& m);
  ~Lock();
};

[[nodiscard]] int compute(int x);

void use(std::mutex& m, std::vector<int>& v, std::unique_ptr<int>& p) {
  Lock{m};         // 构造后立即析构
  compute(1);
  v.empty();       // 想清空，实际只是查询
  p.release();     // 泄漏
}
```

```text
attrs.cpp:15:3: warning: ignoring temporary created by a constructor declared with 'nodiscard' attribute: the lock is released immediately [-Wunused-value]
attrs.cpp:16:3: warning: ignoring return value of function declared with 'nodiscard' attribute [-Wunused-result]
attrs.cpp:17:3: warning: ignoring return value of function declared with 'nodiscard' attribute [-Wunused-result]
```

`v.empty()` 的警告来自 libc++，它给 `vector::empty` 标了 `[[nodiscard]]`。`p.release()` 本机没有警告：这个版本的 libc++ 没有给 `unique_ptr::release` 加这个属性，尽管丢弃它的结果一定泄漏。

推荐标 `[[nodiscard]]` 的情形，理由都是丢弃结果几乎一定是 bug：

- 除了返回值没有别的效果的函数，例如 `empty()`、`size()`、纯计算；
- 返回资源或所有权的函数，例如 `release()`、工厂函数；
- 用返回值报告失败的函数；
- 获取资源的构造函数，例如锁和 scope guard（[[P1771R1]]）。

带字符串的形式是 C++20 加入的（[[P1301R4]]）。字符串写调用方该怎么做，比单纯的警告更有用。

### `[[deprecated]]`

`[[deprecated]]` 标记仍然可以使用、但不鼓励使用的名字或实体。它可以标在类、类型别名、变量、非静态数据成员、函数、命名空间、枚举、枚举项、概念和模板特化上（[[dcl.attr.deprecated#2]]），实现应当在程序引用它时给出诊断，并包含属性里的字符串（[[dcl.attr.deprecated#4]]）。

```cpp title="dep.cpp"
namespace geo {
struct Vector2 { double x, y; };
using Vec [[deprecated("renamed to geo::Vector2")]] = Vector2;

enum class Unit { meter, metre [[deprecated("use Unit::meter")]] = meter };

double length(const Vector2& v);
[[deprecated("use length(); removed in 3.0")]]
inline double norm(const Vector2& v) { return length(v); }
}

double user(geo::Vec v, geo::Unit u) {
  if (u == geo::Unit::metre) return geo::norm(v);
  return 0;
}
```

```text
dep.cpp:12:18: warning: 'Vec' is deprecated: renamed to geo::Vector2 [-Wdeprecated-declarations]
dep.cpp:13:23: warning: 'metre' is deprecated: use Unit::meter [-Wdeprecated-declarations]
dep.cpp:13:42: warning: 'norm' is deprecated: use length(); removed in 3.0 [-Wdeprecated-declarations]
```

这三种写法覆盖了最常见的演进动作：重命名类型时留一个弃用的别名，重命名枚举项时留一个弃用的同值枚举项，替换函数时让旧函数转发到新函数。消息里写清替代品和计划删除的版本。

`[[deprecated]]` 可以在之后的重新声明中加上（[[dcl.attr.deprecated#3]]），所以库也可以在一个单独的头文件里集中弃用旧接口。

!!! pitfall "用户的 `-Werror`"
    用 `-Werror` 构建的用户，升级到一个新弃用了某些接口的版本时，构建会直接失败：本机上例加 `-Wall -Werror` 得到 3 个错误。这不是库的错误，但会让用户推迟升级。在发布说明里提醒用户可以用 `-Wno-error=deprecated-declarations` 把这类诊断保持为警告；本机加上它之后，三条诊断恢复为警告，编译成功。

## noexcept 是契约的一部分

### 承诺，以及谁依赖这个承诺

`noexcept` 声明函数不会以异常退出。它不是检查：异常真的离开 `noexcept` 函数时调用 `std::terminate`（[[topics/exception-safety]]）。调用方可以用 `noexcept(expr)` 在编译期查询这个承诺，并据此选择算法：`std::vector` 扩容时只有元素的移动构造函数不抛出才移动元素，否则复制。

所以 `noexcept` 是接口的一部分，和返回类型一样会被调用方的代码依赖。

### 从 C++17 起是函数类型的一部分

函数类型由返回类型、形参类型列表、引用限定符、cv 限定符和异常规范组成，但不包括默认实参（[[dcl.fct#13]]）。异常规范进入类型系统是 C++17 的改动（[[P0012R1]]）。

```cpp title="nx.cpp" error
void may_throw();
void wont_throw() noexcept;

void (*p1)() = wont_throw;            // OK：可以丢掉 noexcept
void (*p2)() noexcept = may_throw;    // error: 不能凭空加上 noexcept
static_assert(!__is_same(decltype(may_throw), decltype(wont_throw)));

void h();
void h() noexcept;                    // error: 不能按 noexcept 重载

struct Base { virtual void run() noexcept; };
struct Derived : Base { void run() override; };   // error
```

```text
nx.cpp:5:8: error: cannot initialize a variable of type 'void (*)() noexcept' with an lvalue of type 'void ()': different exception specifications
nx.cpp:9:6: error: exception specification in declaration does not match previous declaration
nx.cpp:12:30: error: exception specification of overriding function is more lax than base version
```

逐条对照规则：

- 指向 `noexcept` 函数的指针可以转换为普通函数指针，反过来不行（[[conv.fctptr#1]]）。
- 判断两个声明是不是重载时只比较形参类型列表等，不比较异常规范（[[basic.scope.scope#4]]），所以 `h()` 和 `h() noexcept` 是同一个函数的两个声明，异常规范不一致是错误（[[except.spec#4]]）。
- 基类的虚函数是 `noexcept` 的，覆盖它的函数也必须是（[[except.spec#5]]）。

用 `-std=c++14` 编译同一个文件，`static_assert` 失败：C++14 中两个函数的类型相同。本机 Clang 23 的 `__cpp_noexcept_function_type` 为 `201510`。

### 加上和去掉

函数自身的修饰名不含异常规范。本机 `void f() noexcept {}` 的符号是 `__Z1fv`，和不带 `noexcept` 时一样，所以给一个非模板函数加上 `noexcept` 不改变它的导出符号。但以函数指针类型为形参时，`noexcept` 出现在形参类型中，修饰名不同：`take(void (*)() noexcept)` 是 `__Z4takePDoFvvE`，`take(void (*)())` 是 `__Z4takePFvvE`，两者可以同时存在。修饰规则见 [[toolchain/name-mangling]]。

源码层面，两个方向的风险不对称：

- **加上** `noexcept` 几乎总是兼容的。用户原来的 `void (*)()` 指针仍然可以指向它。受影响的只有依赖确切类型的代码，例如 `decltype(&f)` 现在带着 `noexcept`。
- **去掉** `noexcept` 会破坏用户：`void (*)() noexcept` 类型的指针无法再指向它，`static_assert(noexcept(f()))` 失败，覆盖它的派生类不受影响但基类的约束没有了。更隐蔽的是性能：一个类型的移动构造函数失去 `noexcept` 之后，`std::vector<T>` 扩容时改为复制，没有任何诊断。

因此 `noexcept` 只应该加在确定以后也不会抛出的函数上。标准库遵循一条保守的惯例：有前置条件的函数（窄契约）通常不声明为 `noexcept`，即使正常使用时它不会抛出，好让调试型实现在前置条件被违反时抛出异常、便于测试（[[N3279]]，常称 Lakos 规则，见 [[description]]）。

!!! tip "建议"
    移动构造、移动赋值、`swap` 和析构函数应当是 `noexcept` 的，它们影响标准容器的行为，而且几乎总能写成不抛出。其他函数只在不抛出是接口承诺、而不是当前实现碰巧如此时才标。

## 重载集合与 ADL：库作者的风险

### 新增一个模板，劫持了用户的调用

实参依赖查找（ADL）会在实参类型所在的命名空间里查找函数名（[[basic.lookup.argdep]]，详见 [[topics/name-lookup-and-customization]]）。对库作者来说，这意味着库命名空间里的每一个函数名，都会参与用户对库类型的每一次无限定调用。

```cpp run title="adl.cpp" ok
#include <cstdio>

namespace geo {
struct Point { int x, y; };
#ifdef V2
template <class T>            // v2 新增的泛型工具
void dump(T&) { std::puts("geo::dump"); }
#endif
}

// 用户代码，v1 时代写的
void dump(const geo::Point& p) { std::printf("user dump %d,%d\n", p.x, p.y); }

int main() {
  geo::Point p{1, 2};
  dump(p);
}
```

本机按 v1 编译输出 `user dump 1,2`；加 `-DV2` 重新编译，输出 `geo::dump`，没有任何诊断。v2 的模板通过 ADL 进入了候选集，`T` 推导为 `geo::Point`，形参 `geo::Point&` 与非 `const` 左值实参的绑定比用户的 `const geo::Point&` 更好（引用绑定时 cv 限定较少者优先），于是模板胜出。库只是新增了一个函数，用户的程序就换了行为。

### 函数对象不参与 ADL

ADL 只找函数和函数模板的声明（[[basic.lookup.argdep#4]]）；无限定查找如果找到的是一个变量，就根本不做 ADL（[[basic.lookup.argdep#1]]）。所以把泛型操作写成函数对象，它就不会被别人的无限定调用意外找到：

```cpp run title="adl2.cpp" ok
#include <cstdio>

namespace geo {
struct Point { int x, y; };
struct dump_fn {
  template <class T>
  void operator()(T&) const { std::puts("geo::dump"); }
};
inline constexpr dump_fn dump{};   // 对象，不是函数：ADL 找不到它
}

void dump(const geo::Point& p) { std::printf("user dump %d,%d\n", p.x, p.y); }

int main() {
  geo::Point p{1, 2};
  dump(p);         // 用户的函数
  geo::dump(p);    // 显式使用库的版本
}
```

本机输出 `user dump 1,2` 和 `geo::dump`。C++20 的 `std::ranges` 算法就是这样实现的（[[g:algorithm-function-object]]）。

库作者可以遵守的几条规则：

1. 不要在自己类型所在的命名空间里放无约束、名字常见的函数模板。确实需要时用概念约束它，或者写成函数对象。
2. 运算符和 `swap` 这类只对本类有意义的函数写成隐藏友元（[[g:hidden-friend]]）：只在类内定义的友元函数只能经 ADL 找到，只在实参是这个类时才进入候选集，不会出现在其他类型的重载集合和错误信息里。
3. 库内部调用自己的辅助函数时用限定名（`detail::helper(x)`），否则用户类型的命名空间里同名的函数会被 ADL 找到。
4. 需要让用户定制行为时，明确规定定制的方式：一个由 ADL 查找、名字不易冲突的函数，一个可以特化的 trait，或者一个定制点对象。几种设计的取舍见 [[topics/name-lookup-and-customization]]。

## 演进：不破坏用户地修改接口

### 两种兼容

**源码兼容**指用户的代码不修改，用新版本的头文件重新编译后仍然良构，而且意思不变。**二进制兼容**（ABI 兼容）指用户的程序不重新编译，换上新版本的库仍然正确运行。两者互不包含：给 `struct` 加一个数据成员通常源码兼容但破坏 ABI；把一个形参从 `const std::string&` 改成 `std::string_view` 对多数调用者源码兼容，但修饰名变了，也破坏 ABI。ABI 的各种破坏方式和检查办法见 [[toolchain/library-boundaries]]，这里讨论源码层面。

### 加默认实参还是加重载

假设 v2 要给 `connect` 加一个超时参数：

```cpp title="evo.cpp"
namespace net {
#if VER == 1
void connect(const char* host);
#elif VER == 2   // 方案 A：加一个带默认实参的形参
void connect(const char* host, int timeout_ms = 1000);
#else            // 方案 B：加一个重载
void connect(const char* host);
void connect(const char* host, int timeout_ms);
#endif
}

void user() {
  net::connect("example.org");                   // 三个版本都能编译
  void (*fp)(const char*) = &net::connect;       // A 中出错
  auto ap = &net::connect;                       // B 中出错
  (void)fp; (void)ap;
}
```

```text
VER=2: error: cannot initialize a variable of type 'void (*)(const char *)' with an rvalue of type 'void (*)(const char *, int)': different number of parameters (1 vs 2)
VER=3: error: variable 'ap' with type 'auto' has incompatible initializer of type '<overloaded function type>'
```

两种方案对直接调用都兼容，破坏的东西不同：

| | 方案 A：默认实参 | 方案 B：重载 |
|---|---|---|
| 直接调用 | 兼容 | 兼容 |
| 取地址到 `void (*)(const char*)` | 出错，函数类型变了 | 兼容，按目标类型选出重载 |
| `auto p = &net::connect` | 兼容 | 出错，重载集合没有唯一的类型 |
| 旧的导出符号 | 消失：本机 `__ZN3net7connectEPKc` 变成 `__ZN3net7connectEPKci` | 保留 |
| 默认值以后能否修改 | 修改只对重新编译的调用方生效（默认实参在调用处求值，[[dcl.fct.default#9]]） | 默认值在库内部，可以修改 |

对以二进制形式发布的库，方案 B 更好：旧符号仍在，默认值留在库里。方案 A 的优点是声明少，适合只以源码形式使用的头文件库。

取函数地址这条风险，标准库用规则化解了：除非标准把一个函数指定为可取址函数，程序对标准库函数取地址的行为是未指明的，可能非良构（[[namespace.std#6]]）。这样标准库就可以自由地加重载、加默认实参。库也可以在文档里声明同样的规则。

### 其他常见改动

| 改动 | 源码兼容吗 |
|---|---|
| 给枚举加一个枚举项 | 编译通过，但用户对它的 `switch` 得到 `-Wswitch` 警告：本机 `enumeration value 'fatal' not handled in switch`；用 `-Werror` 的用户构建失败 |
| 形参 `const std::string&` 改为 `std::string_view` | 多数调用兼容；只能隐式转换为 `std::string` 的类型不再能传入，本机报 `no known conversion from 'Name' to 'std::string_view'` |
| 给函数加 `noexcept` | 兼容（见上节） |
| 去掉 `noexcept` | 不兼容 |
| 在聚合末尾加数据成员 | 按位置或按指派初始化的代码仍能编译，但本机 `-Wextra` 对没有初始化新成员的地方给出 `-Wmissing-field-initializers` 或 `-Wmissing-designated-field-initializers` 警告；结构化绑定的个数变了，不兼容 |
| 给成员函数补上 `const` | 兼容 |
| 在库命名空间新增函数或函数模板 | 可能通过 ADL 改变用户调用的函数，见上节 |

### 先弃用，再删除

删除或重命名一个公开名字，推荐分三步，每一步至少间隔一个发布版本：

1. 加入新接口，旧接口转发到新接口，二者并存。
2. 给旧接口加上 `[[deprecated("use X; removed in N")]]`，写清替代品和删除版本。
3. 在说明的版本中删除旧接口。

第 2 步让用户在编译时、在使用旧接口的那一行得到提示，而不是在升级之后面对一个 `no member named` 错误去查发布说明。

### 内联命名空间作为版本号

把公开接口放进一个内联命名空间 `namespace geo { inline namespace v2 { ... } }`，用户照常写 `geo::f`，修饰名里却带着 `v2`（[[namespace.def#6]]）。不兼容的改动换一个内联命名空间，旧二进制就会在链接或加载时失败，而不是静默地读错内存。本机的完整实验、实现文件里必须用限定名定义的陷阱，以及 libc++ 的 `std::__1`，见 [[toolchain/library-boundaries]]。

在源码层面它还有一个用处：老版本的命名空间不再内联，但继续保留，需要旧行为的用户可以显式写 `geo::v1::f`。

## 特性检测宏

### 用户怎样检测标准库

```cpp run title="ftm.cpp" ok
#include <cstdio>
#include <version>

#if __has_include(<expected>)
#  include <expected>
#endif

int main() {
#ifdef __cpp_lib_expected
  std::printf("__cpp_lib_expected      %ld\n", (long)__cpp_lib_expected);
#endif
#ifdef __cpp_lib_function_ref
  std::puts("function_ref available");
#else
  std::puts("__cpp_lib_function_ref  undefined");
#endif
#ifdef __cpp_contracts
  std::puts("contracts available");
#else
  std::puts("__cpp_contracts         undefined");
#endif
}
```

本机 `-std=c++2c` 输出 `__cpp_lib_expected 202211`，`__cpp_lib_function_ref` 和 `__cpp_contracts` 都未定义；`<version>` 本机定义了 188 个 `__cpp_lib_` 宏。

两种检测回答不同的问题。`__has_include(<expected>)` 只说明能找到这个头文件（[[cpp.cond#3]]）。本机用 `-std=c++20` 编译时 `__has_include(<expected>)` 为真，包含之后使用 `std::expected` 却报 `use of undeclared identifier 'std'`，因为 libc++ 只在 C++23 及以后的模式下声明它。`__cpp_lib_expected` 定义在 `<version>` 和对应的头文件中（[[version.syn#2]]），它的值是该特性被采纳的年月，才说明这个特性在当前模式下可用。语言特性的宏（`__cpp_deleted_function` 等）由编译器预定义（[[cpp.predefined#1.2]]），不需要包含头文件。

所以推荐的写法是：先 `#include <version>`，再检查 `__cpp_lib_*`；`__has_include` 用来检测非标准的、或者可能没有安装的头文件。`__has_include` 只能出现在 `#if` 一类的条件里（[[cpp.cond#7]]），本机把它写进普通表达式得到 `'__has_include' must be used within a preprocessing directive`。

`__has_include` 来自 C++17（[[P0061R1]]），特性检测宏在 C++20 才写进标准正文（[[P0941R2]]）。

### 给自己的库定义宏

库也应该给用户同样的工具。一个 `version.h` 通常包含：

```cpp title="geo/version.h"
#pragma once
#define GEO_VERSION_MAJOR 2
#define GEO_VERSION_MINOR 4
#define GEO_VERSION_PATCH 0
#define GEO_VERSION \
  (GEO_VERSION_MAJOR * 10000 + GEO_VERSION_MINOR * 100 + GEO_VERSION_PATCH)

#define GEO_HAS_SIMPLIFY 202609L   // 加入 simplify() 的年月
```

用户写 `#if defined(GEO_HAS_SIMPLIFY)` 或 `#if GEO_VERSION >= 20400`，就能同时支持新旧两个版本的库。按功能定义的宏比版本号比较更稳妥：功能可能被移植回旧的维护分支，版本号却不会。这个头文件可以由构建系统根据项目版本号生成，见 [[toolchain/cmake]]。

宏名要带库自己的前缀。不要模仿标准写成 `__cpp_geo_simplify`：含双下划线的标识符保留给实现，使用它们是 IFNDR（[[lex.name#4.1]]）。

## 记录前置条件

**前置条件**是函数假定调用时成立、由调用方负责保证的条件。违反前置条件是调用方的 bug，函数不必、通常也无法报告它。

标准库的规格说明把函数的要求分成几类元素（[[structure.specifications#3]]）：*Constraints* 不满足时函数不参与重载决议，*Mandates* 不满足时程序非良构，*Preconditions* 不满足时是 UB，*Hardened preconditions* 在加固实现中保证被检查。这几个词的精确含义见 [[description]]。库的文档可以借用同样的分类，让用户知道哪些要求由编译器保证、哪些要自己保证。

能用类型表达的条件，就不要写成前置条件。`const T&` 比“`p` 不得为空”好，`Port` 类型比“`port` 必须在 1 到 65535 之间”好，`span` 比“`n` 不得超过 `p` 指向的数组长度”好。剩下的条件写在文档里，并在调试构建中用 `assert` 检查。

C++26 允许把前置条件和后置条件写在声明上（[[P2900R14]]）：

```cpp title="contracts.cpp（C++26，本机 Clang 23 不支持，未编译）"
double sqrt_checked(double x)
  pre(x >= 0)
  post(r: r >= 0);
```

这样前置条件成为声明的一部分，调用方和工具都看得见，检查与否由构建时选择的求值语义决定。本机 Clang 23 没有定义 `__cpp_contracts`，也没有 `<contracts>` 头文件，上例没有验证。契约的语义、与 `assert` 和标准库加固的关系见 [[toolchain/error-handling-strategy]]，设计取舍与仍在讨论的问题见 [[history/contracts]]。

## 检查清单

| 问题 | 推荐做法 |
|---|---|
| 形参是否表达了所有权和可空性 | 借用用 `T&`、`T*`、`span`、`string_view`；接管用按值的拥有型类型 |
| 返回值 | 值、`optional`、`expected`、`unique_ptr`；不返回拥有所有权的裸指针 |
| 返回内部数据的引用或视图 | 用引用限定符区分左值和右值，或者 `[[clang::lifetimebound]]` |
| 布尔和整数形参 | 换成 `enum class` 或强类型；用 `= delete` 拒绝不想要的转换 |
| 丢弃结果是不是 bug | 是就标 `[[nodiscard("...")]]` |
| 移动操作、`swap` | `noexcept` |
| 库命名空间里的泛型函数 | 约束它，或改为函数对象；运算符用隐藏友元 |
| 新增参数 | 以二进制形式发布时用重载，不用默认实参 |
| 删除或重命名 | 新旧并存，`[[deprecated("...")]]` 至少一个版本，再删除 |
| 用户怎样检测新功能 | 提供带前缀的版本宏和功能宏 |

## 思考题

!!! question "1"
    库的 v1 中有 `struct Buffer { Buffer(Buffer&&); };`，移动构造函数没有 `noexcept`。v2 给它加上了 `noexcept`，函数体不变。用户的程序不重新编译、直接换上 v2 的动态库，`std::vector<Buffer>` 扩容的行为会变吗？重新编译之后呢？

<details markdown="1">
<summary>答案</summary>

不重新编译时不变。`vector` 是模板，选择移动还是复制的决定（`std::move_if_noexcept`）在用户的翻译单元实例化时就做完了，编进了用户的二进制。移动构造函数自身的修饰名不含异常规范，v2 的库仍然导出同一个符号，加载成功，用户的代码继续复制元素。

重新编译之后，`noexcept(Buffer(std::declval<Buffer>()))` 为真，扩容改为移动。这是一个源码兼容、二进制兼容、但性能特征随重新编译而改变的例子。反方向的改动（去掉 `noexcept`）会让重新编译的用户从移动退回复制，而且没有任何诊断。
</details>

!!! question "2"
    `adl2.cpp` 中把 `geo::dump` 改成了函数对象。如果用户写的是 `using namespace geo;` 之后再调用 `dump(p)`，会发生什么？

<details markdown="1">
<summary>答案</summary>

无限定查找此时在全局命名空间中找到用户的函数 `::dump`，同时经 using 指令在 `geo` 中找到变量 `geo::dump`。一个是函数、一个是变量，查找结果有歧义，程序非良构。函数对象只能防止 ADL 意外地找到库的名字，防不住用户主动用 using 指令把两个命名空间合在一起。这也是不在头文件里写 `using namespace` 的理由之一。
</details>

!!! question "3"
    为什么给 `set_percent(int)` 配上 `template <class T> void set_percent(T) = delete;` 之后，`set_percent(42)` 仍然调用 `int` 版本，而 `set_percent(42L)` 被拒绝？

<details markdown="1">
<summary>答案</summary>

对 `42`（`int`），模板推导出 `T = int`，两个候选都是精确匹配，转换序列无法区分；此时非模板函数优于模板特化（[[over.match.best]]），选中 `set_percent(int)`。对 `42L`，模板推导出 `T = long`，是精确匹配；`set_percent(int)` 需要一次整数转换，排名更低。最佳候选是已删除的模板特化，引用已删除的函数使程序非良构（[[dcl.fct.def.delete#2]]）。
</details>
