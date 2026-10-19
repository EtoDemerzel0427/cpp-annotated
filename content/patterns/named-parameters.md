---
title: 命名参数与 builder
summary: C++ 没有命名实参，怎样让 open("f", true, false, 4096) 这样的调用读得懂：布尔形参换成枚举，选项聚合配合指派初始化器，按引用返回 *this 的方法链，用引用限定符和显式对象形参处理临时 builder，以及默认实参的几个陷阱。
status: draft
order: 95
since: c++20
papers: P0329R4, P2287R5, P1008R1, P0847R7
related: dcl.init.aggr, dcl.init.list, over.ics.list, dcl.fct.default, class.temporary, over.match.funcs, dcl.fct, expected, patterns/strong-types, topics/dangling-references, topics/initialization, topics/type-deduction
tags: 惯用法, 指派初始化器, 聚合, builder, 方法链, deducing this, 默认实参
updated: 2026-10-19
---

!!! tldr
    - 位置实参只靠顺序区分，同类型的实参写反了编译器不会发现。`bool` 形参尤其危险：指针、整数、浮点数都能隐式转换成 `bool`。
    - C++20 的指派初始化器配合一个选项聚合，可以写出 `open_file("f", {.create = true, .buffer = 4096})`：没写的成员用默认成员初始化器，顺序错了、窄化、重复都是编译错误。代价是选项类型必须是聚合，不能有构造函数。
    - builder 的方法链按引用返回 `*this`。在临时 builder 上链式调用到分号为止都安全，把链的结果绑到引用上就悬垂。
    - 用 `&` / `&&` 引用限定符重载，临时 builder 的链可以按值返回，从根本上避免悬垂；C++23 的显式对象形参（deducing this）把这两个重载合成一个模板，还能让派生 builder 的链保持派生类型。
    - 默认实参在调用方展开，按静态类型选取，不属于函数类型。虚函数的默认实参和头文件里改默认值是两个常见的坑。

## 读不懂的调用

```cpp title="positional.cpp" run ok
#include <string_view>

void open_file(std::string_view /*path*/, bool /*create*/,
               bool /*truncate*/, bool /*append*/, int /*buffer*/) {}

int main() {
  open_file("a.log", true, false, true, 4096);  // 哪个 true 是什么？
  open_file("a.log", "create", 4096, true, 0);  // 也能编译
}
```

第一个调用要对照声明才能读懂。第二个调用把字符串和整数放在了 `bool` 的位置，却能编译：字符串字面量退化成指针，指针转换成 `bool`；`4096` 也转换成 `bool`；`true` 转换成 `int`。按 [[conv.bool#1]]，算术类型、无作用域枚举、指针都能转换成 `bool`。本机 Clang 23 加 `-Wall -Wextra -pedantic` 对这两行都没有警告。

C++ 没有命名实参，名字只能放进类型里。有几种做法，从轻到重：

1. 把 `bool` 换成枚举，把同类型的数值换成不同的强类型，让写错位置变成类型错误；
2. 把一组可选参数收进一个选项聚合，用指派初始化器按名字填写；
3. 用 builder：一个专门收集参数的对象，每个参数一个成员函数，最后一步构造结果并检查参数之间的约束。

## 让类型替你检查位置

```cpp title="enum-flags.cpp" error
#include <string_view>

enum class Create : bool { no, yes };
enum class Truncate : bool { no, yes };

void open_file(std::string_view path, Create, Truncate);

void t() {
  open_file("a.log", Create::yes, Truncate::no);  // OK
  open_file("a.log", Truncate::no, Create::yes);  // error: 类型不匹配
  open_file("a.log", true, false);                // error: bool 不能隐式转换成枚举
}
```

有作用域枚举（`enum class`）与整数之间没有隐式转换：[[dcl.enum#11]] 的整型提升只适用于无作用域枚举，[[conv.bool#1]] 的布尔转换也不包括它。调用处必须写出 `Create::yes`，读的人不用再查声明。底层类型写 `bool`，它的大小和传参方式都与 `bool` 相同。

同样的办法适用于数值：`resize(Width{800}, Height{600})` 里两个实参类型不同，写反就编译失败。怎样定义这类包装类型、怎样避免为每个类型重写运算符，见 [[patterns/strong-types|强类型与幻影类型]]。

这一步只解决位置写错的问题。参数一多，调用方仍要按顺序写出每一个，哪怕大多数都取默认值。

## 选项聚合与指派初始化器 {{c++20}}

### 写法

```cpp title="options.cpp" run ok
#include <cstdio>
#include <string_view>

struct OpenOptions {
  bool create = false;
  bool truncate = false;
  bool append = false;
  int buffer = 8192;
};

void open_file(std::string_view path, OpenOptions o = {}) {
  std::printf("%.*s create=%d truncate=%d append=%d buffer=%d\n",
              int(path.size()), path.data(),
              o.create, o.truncate, o.append, o.buffer);
}

int main() {
  open_file("a.log");
  open_file("b.log", {.create = true, .buffer = 4096});
  open_file("c.log", {.append = true});
}
```

输出三行，`b.log` 一行是 `create=1 truncate=0 append=0 buffer=4096`。调用处只写需要改的选项，其余的取默认值，读起来接近其他语言的关键字实参。

### 为什么能这样写

`{.create = true, .buffer = 4096}` 是一个**指派初始化器列表**（designated-initializer-list，[[P0329R4]]），每一项 `.名字 = 值` 叫一个指派子句。它作为实参时，形参 `o` 从它拷贝列表初始化。几条规则串起来：

- [[dcl.init.list#3]] 第 1 项：列表里有指派子句时，被初始化的类型必须是聚合类，执行聚合初始化。
- [[dcl.init.aggr#4]]：被指派的成员是显式初始化的元素，¶5.2.1 用对应子句里的初始化器初始化它。
- [[dcl.init.aggr#6]]：没有显式初始化的元素，有默认成员初始化器就用它（¶6.1），否则从 `{}` 拷贝初始化（¶6.2）。`truncate`、`append` 因此取 `false`。
- [[dcl.init.aggr#8]]：所有元素按声明顺序初始化，前一个元素的副作用在后一个之前完成。

**聚合**（[[g:aggregate]]）指数组，或者没有用户声明的构造函数、没有私有或受保护的直接非静态数据成员、没有虚函数和虚基类的类（[[dcl.init.aggr#1]]）。默认成员初始化器不影响聚合身份，所以选项类型可以同时有默认值和指派初始化。

### 规则一览

C++ 只取了 C99 指派初始化器的一个子集。各项限制都出于同一个模型：成员按声明顺序初始化，每个成员恰好初始化一次。完整的条文分析见 [[dcl.init.aggr]]。

| 写法 | 结果 | 出处 |
|---|---|---|
| `{.buffer = 1, .create = true}` 顺序与声明不同 | 非良构 | [[dcl.init.list#3]] 第 1 项 |
| `{true, .buffer = 1}` 普通子句与指派子句混用 | C++20/23 非良构；当前草案只允许普通子句初始化基类 | [[dcl.init.aggr#4]]、[[P2287R5]] |
| `{.o.buffer = 1}` 嵌套指派符 | 非良构，文法只有 `. identifier` | [[dcl.init.general#1]] |
| `{.o = {.buffer = 1}}` 嵌套的列表 | OK | [[dcl.init.aggr#5]] |
| `{.create = true, .create = false}` 重复 | 非良构 | [[dcl.init.general#20]] |
| `{.buffer = 4096.5}` 或 `{.buffer = n}`，`n` 是 `long` | 非良构：窄化 | [[dcl.init.aggr#5]] 第 2.1 项 |
| 选项类型有构造函数，哪怕是 `= default` | 非良构：不是聚合 | [[dcl.init.aggr#1]]、[[P1008R1]] |
| 选项类型有私有数据成员 | 非良构：不是聚合 | [[dcl.init.aggr#1]] |

本机 Clang 23 对窄化、重复和非聚合报错，但把乱序、嵌套指派符、混用都当作 C99 扩展接受，只给出 `-Wreorder-init-list`、`-Wc99-designator` 警告，加 `-pedantic-errors` 才报错。可移植的代码应当把这两个警告当成错误。

窄化的检查值得单独说一句。普通的拷贝初始化 `int x = 4096.5;` 允许窄化，指派子句的 `= 值` 形式却不允许，这是 ¶5.2.1 专门加的一句。选项里的数值因此不会悄悄截断。

### 基类里的公共选项

几组选项共享一部分字段时，自然的想法是把公共部分放进基类：

```cpp
struct Common { int timeout = 30; int retries = 3; };
struct HttpOptions : Common { bool keep_alive = true; };

HttpOptions a{.timeout = 5, .keep_alive = false};          // C++20/23 非良构，草案 OK
HttpOptions b{Common{.timeout = 5}, .keep_alive = false};  // C++20/23 非良构，草案 OK
HttpOptions c{{.timeout = 5}, false};                      // OK：基类按位置初始化
```

C++20/23 中指派符只能命名类自己的直接成员，基类只能按位置初始化，写成 `c` 那样。当前草案按 [[P2287R5]] 放宽了：指派符可以命名基类的成员（`a`），也可以先用普通子句初始化基类，再用指派子句初始化自己的成员（`b`）。截至写作时，本机 Clang 23 对 `a` 报错（field designator 'timeout' does not refer to any field），对 `b` 只给出 C99 扩展警告，所以这段代码不标判定。需要可移植时，用组合代替继承：`struct HttpOptions { Common common; bool keep_alive = true; };`，调用处写 `{.common = {.timeout = 5}}`。

### 必填字段

选项聚合的每个成员都有默认值，调用方漏写也能编译。如果某个字段必须由调用方提供，可以让它的类型不能从 `{}` 初始化：

```cpp title="required.cpp" run ok
#include <concepts>
#include <string>
#include <utility>

template<class T> struct Required {
  T value;
  template<class U> requires std::constructible_from<T, U>
  Required(U&& u) : value(std::forward<U>(u)) {}   // 没有默认构造函数
};

struct ConnectOptions {
  Required<std::string> host;
  int port = 443;
  bool tls = true;
};

void connect(ConnectOptions) {}

int main() {
  connect({.host = "example.org", .port = 8443});  // OK
  // connect({.port = 8443});  // error: host 无法从 {} 初始化
}
```

漏写 `.host` 时，按 [[dcl.init.aggr#6]] 第 2 项，`host` 要从 `{}` 拷贝初始化。`Required` 不是聚合，也没有默认构造函数，模板构造函数又无法从空列表推导出 `U`，于是初始化失败，`ConnectOptions` 不能从这个列表初始化。`ConnectOptions` 本身仍然是聚合：聚合的条件只看它自己有没有构造函数，不看成员。

构造函数写成模板，是因为 `"example.org"` 到 `Required<std::string>` 要经过两次用户定义转换（先到 `std::string`，再到 `Required`），隐式转换序列只允许一次。

!!! impl "漏写字段的警告"
    Clang 的 `-Wmissing-designated-field-initializers`（`-Wextra` 包含它）对指派列表里漏写的、没有默认成员初始化器的字段发出警告。字段有默认成员初始化器时不警告。所以给选项的每个字段都写上默认值，既表达了意图，也让这个警告只在真正遗漏时出现。

### 与重载决议的相互作用

指派列表作为实参时，[[over.ics.list#2]] 规定：只有形参是能用这个列表做聚合初始化的聚合类型，才存在转换。指派符的名字因此参与了重载决议：

```cpp title="overload.cpp" error
struct A { int x, y; };
struct C { int x; int z; };
void h(A);
void h(C);

void t() {
  h({.y = 2});   // OK：只有 A 有成员 y
  h({.z = 2});   // OK：只有 C 有成员 z
  h({.x = 1});   // error: 有歧义
}
```

顺序不参与这一步。[[over.ics.list#2]] 的注 1 说明，先按名字选出重载，选中之后才检查顺序，顺序不对就是初始化失败，而不会转去另一个重载。

### 代价

选项聚合是普通的值类型，按值传递时遵循平台 ABI 对小结构体的规则。`OpenOptions` 是 8 字节（三个 `bool`、一个填充字节、一个 `int`），本机 arm64 和交叉编译的 x86-64 Linux 都把它装进一个寄存器传递：

<div class="compare" markdown="1">

```cpp
open_opts("f", {.create = true,
                .buffer = 4096});
// arm64 -O2：
//   mov  x1, #1
//   movk x1, #4096, lsl #32
//   b    open_opts
```

```cpp
open_pos("f", true, false,
         false, 4096);
// arm64 -O2：
//   mov w1, #1
//   mov w2, #0
//   mov w3, #0
//   mov w4, #4096
//   b   open_pos
```

</div>

两者都是把常量放进寄存器后尾调用，没有额外的内存访问。结构体超过 16 字节时，两个平台都改为经由内存传递（arm64 传一个指向副本的指针，x86-64 SysV 放在栈上），这时多一次写内存和读内存。和函数本身的工作相比，这通常可以忽略。

另一项代价在演进上。给选项聚合在末尾或中间加成员，用指派初始化器的调用方不受影响；调整已有成员的顺序，凡是指派了两个以上被调整成员的调用都会报错。这是编译期就能发现的破坏，比位置实参悄悄错位要好，但也意味着成员顺序成了接口的一部分。

## builder 与方法链

选项聚合只是一包数据，不能检查字段之间的约束（`append` 和 `truncate` 不能同时为真），也不能在填写过程中做计算。**builder** 是一个专门收集参数的类：每个参数对应一个成员函数，最后由 `build()` 检查约束并构造结果。成员函数返回 builder 自身的引用，调用就能串起来，这种写法叫**方法链**（method chaining）。标准库里 `std::ostream` 的 `operator<<` 返回 `ostream&`，是同一个手法。

### 按引用返回 `*this`，以及悬垂

```cpp title="dangling-builder.cpp" run ub
#include <cstdio>
#include <string>

class RequestBuilder {
  std::string url_;
  int timeout_ = 30;
public:
  RequestBuilder& url(std::string u) { url_ = std::move(u); return *this; }
  RequestBuilder& timeout(int s) { timeout_ = s; return *this; }
  void send() const { std::printf("GET %s (%ds)\n", url_.c_str(), timeout_); }
};

int main() {
  RequestBuilder{}.url("https://example.org/long/path").timeout(5).send();  // OK
  auto& b = RequestBuilder{}.url("https://example.org/long/path");
  b.timeout(5);   // UB: 临时对象已在上一行末尾销毁
  b.send();
}
```

第一行是 builder 的典型用法，完全正确。`RequestBuilder{}` 是一个纯右值，在它上面调用成员函数时实质化成临时对象（[[class.temporary#2]]），临时对象在整个**完整表达式**（[[g:full-expression]]，这里是到分号为止的那条语句）求值的最后一步才销毁（[[class.temporary#4]]）。链上的每个调用都在这之前完成。

第二行把链的结果绑到引用上。`url` 没有引用限定符，按 [[over.match.funcs.general#5]]，这种成员函数的隐式对象形参虽然是非 const 左值引用，仍然允许绑定右值，所以在临时对象上调用它合法。它返回的 `RequestBuilder&` 指向那个临时对象，但引用 `b` 绑定的是函数调用的结果，不是 [[class.temporary#6]] 列出的那几种表达式之一，临时对象的生命期不会延长，在这一行末尾就销毁了。`const auto&` 也一样。

本机 Clang 23 编译时没有任何警告。加 `-fsanitize=address` 运行，第三行报 `stack-use-after-scope`，写入发生在 `RequestBuilder::timeout(int)` 内，地址落在第二行创建的那个临时对象里。在 `url` 的声明符后面加 `[[clang::lifetimebound]]`（作用于 `*this`），Clang 就会对第二行给出 `-Wdangling`。更多悬垂情形与工具见 [[topics/dangling-references]]。

### 用引用限定符区分左值和临时对象

成员函数可以按调用它的对象是左值还是右值重载，办法是在形参列表后面写**引用限定符**（ref-qualifier）`&` 或 `&&`。按 [[over.match.funcs.general#4]]，`&` 版本的隐式对象形参是左值引用，`&&` 版本是右值引用；两者都可行时，[[over.ics.rank#3.2.3]] 让右值优先选 `&&` 版本。

```cpp title="ref-qualified.cpp" run ok
#include <cstdio>
#include <string>
#include <utility>

struct Request { std::string url; int timeout; };

class RequestBuilder {
  std::string url_;
  int timeout_ = 30;
public:
  RequestBuilder() = default;
  RequestBuilder(RequestBuilder&& o) noexcept
      : url_(std::move(o.url_)), timeout_(o.timeout_) { std::puts("  move"); }

  RequestBuilder& url(std::string u) & { url_ = std::move(u); return *this; }
  RequestBuilder  url(std::string u) && { url_ = std::move(u); return std::move(*this); }
  RequestBuilder& timeout(int s) & { timeout_ = s; return *this; }
  RequestBuilder  timeout(int s) && { timeout_ = s; return std::move(*this); }

  Request build() && { return {std::move(url_), timeout_}; }
};

int main() {
  std::puts("temporary chain:");
  Request r = RequestBuilder{}.url("https://example.org").timeout(5).build();
  std::puts("named builder:");
  RequestBuilder b;
  b.url("https://example.org").timeout(5);
  Request r2 = std::move(b).build();
  std::puts("bound to auto&&:");
  auto&& c = RequestBuilder{}.url("https://example.org");
  c.timeout(1);   // OK：c 绑定的是延长了生命期的临时对象
  std::printf("%s %d / %s %d\n", r.url.c_str(), r.timeout, r2.url.c_str(), r2.timeout);
}
```

具名 builder 走 `&` 版本，返回引用，没有移动。临时 builder 走 `&&` 版本，按值返回，每一环把内容移动到一个新的纯右值里：输出显示临时链上的两次调用各移动一次，具名 builder 一次也不移动。`auto&& c` 绑定的是按值返回的纯右值，按 [[class.temporary#6]] 第 1 项实质化的临时对象活得和 `c` 一样久，悬垂消失了。

`build() &&` 只接受右值，具名 builder 要写成 `std::move(b).build()`。这样 `build` 可以把成员移动出去，调用处的 `std::move` 也提醒读者 `b` 之后不该再用。

`&&` 版本也可以返回 `RequestBuilder&&`，省掉每一环的移动。代价是 `auto&& c = RequestBuilder{}.url(...)` 又悬垂了：本机 ASan 同样报告 `stack-use-after-scope`。返回值还是返回右值引用，是安全和移动次数之间的取舍。

移动次数在优化后通常不是问题。本机 Clang 23 `-O2` 下，在临时 builder 上连续调用三个 setter 再 `build()`，返回 `RequestBuilder` 和返回 `RequestBuilder&&` 两个版本生成的指令完全相同，都是 10 条，与直接写 `Request{std::move(u), 5, 1}` 的 9 条只差一次寄存器搬运。所有调用内联后，中间的 `std::string` 移动都被消掉了。

!!! pitfall "不能一半有限定符、一半没有"
    同名、同形参列表的成员函数，要么都带引用限定符，要么都不带。`B x(int);` 和 `B x(int) &&;` 放在一起是重复声明（[[basic.scope.scope#4]] 的例 2），本机 Clang 报错。所以给某个 setter 加 `&&` 重载时，原来那个必须改成 `&`。

### deducing this：一个模板代替两个重载 {{c++23}}

每个 setter 写两遍，函数体几乎相同。C++23 的**显式对象形参**（explicit object parameter，[[g:explicit-object-parameter]]，[[P0847R7]]）把对象写成第一个形参，前面加 `this`（[[dcl.fct#8]]）。形参写成 `Self&&` 时它是转发引用，`Self` 从调用对象推导：在左值上调用推导为 `RequestBuilder&`，在右值上推导为 `RequestBuilder`（[[temp.deduct.call#3]]）。

```cpp title="deducing-this.cpp" run ok
#include <cstdio>
#include <string>
#include <utility>

class RequestBuilder {
  std::string url_;
  int timeout_ = 30;
public:
  RequestBuilder() = default;
  RequestBuilder(RequestBuilder&& o) noexcept
      : url_(std::move(o.url_)), timeout_(o.timeout_) { std::puts("  move"); }

  template<class Self>
  Self url(this Self&& self, std::string u) {
    self.url_ = std::move(u);
    return std::forward<Self>(self);
  }
  template<class Self>
  Self timeout(this Self&& self, int s) {
    self.timeout_ = s;
    return std::forward<Self>(self);
  }
  void show() const { std::printf("%s %d\n", url_.c_str(), timeout_); }
};

class HttpRequestBuilder : public RequestBuilder {
  std::string header_;
public:
  template<class Self>
  Self header(this Self&& self, std::string h) {
    self.header_ = std::move(h);
    return std::forward<Self>(self);
  }
};

int main() {
  RequestBuilder b;
  b.url("https://example.org").timeout(5);        // Self = RequestBuilder&
  b.show();
  std::puts("temporary:");
  auto&& t = RequestBuilder{}.url("x").timeout(1);   // Self = RequestBuilder
  t.show();
  std::puts("derived:");
  HttpRequestBuilder{}.url("y").header("Accept: */*").timeout(2).show();
}
```

返回类型直接写 `Self`。左值调用时它是 `RequestBuilder&`，与 `&` 版本相同；右值调用时它是 `RequestBuilder`，按值返回，与上一节的 `&&` 版本相同。一个模板同时得到了两种行为，输出中具名 builder 不移动，临时链每环移动一次。

最后一行是这种写法额外的收获。`url` 定义在基类里，但在 `HttpRequestBuilder` 上调用时 `Self` 推导为 `HttpRequestBuilder`，返回的仍是派生类型，后面可以接 `header`。用上一节的写法，`url` 返回 `RequestBuilder`，接 `header` 会报 no member named 'header'。C++23 之前要做到这一点，得让基类成为模板、把派生类作为模板实参传进去，见 [[patterns/crtp|CRTP 与静态多态]]。

<details class="fine" markdown="1"><summary>显式对象形参的几处细节</summary>

- 函数体里没有隐式的 `this`，访问成员必须写 `self.url_`。名字按 `Self` 的类型查找，如果派生类声明了同名成员，找到的是派生类的那个。
- `self.url_` 是基类的私有成员，经由派生类对象访问。在公有继承下这是允许的，因为访问发生在基类的成员函数里，`url_` 作为基类成员可访问（[[class.access.base#5]]）。私有继承时这条路径不通，编译失败。
- 在 `const` 对象上调用时 `Self` 推导为 `const RequestBuilder&`，赋值 `self.url_ = ...` 在实例化时失败。这正是期望的结果，只是诊断出现在函数体里，而不是在重载决议时。
- setter 变成了模板，定义必须对调用方可见，通常放在头文件里。

</details>

### 带校验的 builder

builder 比选项聚合多出来的能力，是在构造结果之前检查参数。检查可能失败，`build()` 可以返回 `std::expected`（[[expected]]，{{c++23}}）：要么是构造好的对象，要么是错误。

```cpp title="validating-builder.cpp" run ok
#include <cstdio>
#include <expected>
#include <string>
#include <utility>

class Request {
  std::string url_;
  int timeout_;
  Request(std::string u, int t) : url_(std::move(u)), timeout_(t) {}
  friend class RequestBuilder;
public:
  const std::string& url() const { return url_; }
  int timeout() const { return timeout_; }
};

class RequestBuilder {
  std::string url_;
  int timeout_ = 30;
public:
  RequestBuilder& url(std::string u) { url_ = std::move(u); return *this; }
  RequestBuilder& timeout(int s) { timeout_ = s; return *this; }

  std::expected<Request, std::string> build() const {
    if (url_.empty())
      return std::unexpected("url is required");
    if (timeout_ <= 0)
      return std::unexpected("timeout must be positive");
    return Request(url_, timeout_);
  }
};

int main() {
  auto r = RequestBuilder{}.url("https://example.org").timeout(5).build();
  if (r) std::printf("%s %d\n", r->url().c_str(), r->timeout());
  auto e = RequestBuilder{}.timeout(0).build();
  if (!e) std::printf("error: %s\n", e.error().c_str());
}
```

`Request` 的构造函数是私有的，只有 builder 能创建它，所以每个 `Request` 对象都经过了校验。这里的 setter 没有引用限定符，但所有链都在一个完整表达式里结束，`build()` 返回的是值，没有悬垂。输出的第二行是 `error: url is required`，第一个检查先失败。

校验失败时抛异常还是返回 `expected`，取决于调用方是否经常需要处理失败，见 [[topics/exception-safety]] 末尾的讨论。

### builder 和选项聚合怎么选

<div class="compare" markdown="1">

```cpp
// 选项聚合
connect({.host = "example.org",
         .port = 8443});
```

```cpp
// builder
auto c = ConnBuilder{}
    .host("example.org")
    .port(8443)
    .build();
```

</div>

选项聚合写起来短，零运行时开销，但只能表达一组彼此独立、各有默认值的字段，校验只能推迟到使用它的函数里。builder 要为每个字段写一个成员函数，换来的是字段之间的约束检查、分步填写（可以在循环或条件里调用 setter）、以及 `build()` 处的单一出口。

## 默认实参的陷阱

最简单的可选参数是默认实参：`void open_file(std::string_view path, int buffer = 8192);`。它不解决命名问题，只能省略尾部的实参，而且有几条规则容易出错。逐条分析见 [[dcl.fct.default]]，这里列出与接口设计有关的几条。

**默认实参在调用方展开。** 调用 `f()` 时，编译器在调用处把默认实参的表达式补上，每次调用求值一次（[[dcl.fct.default#9]]、[[expr.call#7]]）。后果是默认值编译进了调用方：

```cpp title="lib.h"
void set_level(int level = 1);
```

本机用这个头文件分别编译 `main.cpp`（调用 `set_level()`）和 `lib.cpp`，运行输出 `level 1`。把头文件改成 `= 2`、只重新编译 `lib.cpp` 再链接，输出仍是 `level 1`。对共享库来说，默认值实际上是调用方的一部分，修改它需要重新编译所有调用方。

**虚函数的默认实参按静态类型取。** [[dcl.fct.default#10]] 规定，虚函数调用使用的默认实参由表示对象的指针或引用的静态类型决定，而被调用的函数按动态类型选：

```cpp title="virtual-default.cpp" run ok
#include <cstdio>

struct Logger {
  virtual void log(const char* msg, int level = 1) { std::printf("base %s %d\n", msg, level); }
  virtual ~Logger() = default;
};
struct FileLogger : Logger {
  void log(const char* msg, int level = 3) override { std::printf("file %s %d\n", msg, level); }
};

int main() {
  FileLogger f;
  Logger& r = f;
  r.log("a");   // file a 1：函数按动态类型选，默认实参按静态类型取
  f.log("b");   // file b 3
}
```

`r.log("a")` 运行的是 `FileLogger::log`，拿到的却是 `Logger` 声明里的 `1`。行为是明确的，只是很少有人想要。常见的做法是只在非虚的公有函数上写默认实参，由它转调虚函数，见 [[patterns/nvi|非虚接口与模板方法]]。

**默认实参不属于函数类型**（[[dcl.fct.default#9]]）。`&open_file` 的类型里没有默认值，经由函数指针或 `std::function` 调用时必须写全实参。

**重声明可以补充，但不能重复。** 同一作用域里的后续声明可以给更多形参加默认实参，但同一个形参的默认实参不能再给一次，值相同也不行；块作用域里的声明各有一套（[[dcl.fct.default#4]]）。在头文件声明里写默认值、在 `.cpp` 定义里不写，是最不容易出错的习惯。

**与重载组合时容易产生歧义。** `void f(int, int = 0);` 和 `void f(int);` 可以同时声明，但 `f(1)` 有歧义，本机 Clang 报 call to 'f' is ambiguous。

## 怎么选

| 情况 | 做法 |
|---|---|
| 一两个开关参数 | 有作用域枚举，`enum class X : bool` |
| 同类型的数值参数容易写反 | [[patterns/strong-types\|强类型]] |
| 一组彼此独立、都有默认值的选项 | 选项聚合 + 指派初始化器 |
| 选项之间有约束，或需要分步填写 | builder，`build()` 校验，失败返回 `expected` 或抛出 |
| builder 会在临时对象上链式调用，结果可能被绑到引用上 | `&` / `&&` 重载，`&&` 按值返回；C++23 用 deducing this |
| 派生 builder 要沿用基类的 setter | deducing this，返回 `Self` |
| 只是省略尾部一两个参数，且不是虚函数、不是稳定的库接口 | 默认实参 |

## 思考题

!!! question "1"
    `open_file("f", {.buffer = 4096, .create = true})` 在本机 Clang 23 上加 `-Wall -Wextra` 只有一条警告，程序能运行。它是良构的吗？如果 `open_file` 还有一个重载接受 `struct Other { int buffer; bool create; }`，结果会怎样？

<details markdown="1">
<summary>答案</summary>

不良构。[[dcl.init.list#3]] 第 1 项要求被指派成员按元素顺序不降，`buffer` 声明在 `create` 之后，违反了这条可诊断规则。Clang 把它当作 C99 扩展接受并给出 `-Wreorder-init-list`，加 `-pedantic-errors` 才报错。

加上 `Other` 的重载后，按 [[over.ics.list#2]]，两个形参类型都有 `buffer` 和 `create` 成员，都能由这个列表做聚合初始化，顺序在重载决议阶段不考虑，于是调用有歧义。顺序与 `Other` 的声明一致这件事并不能帮它胜出。
</details>

!!! question "2"
    把 `dangling-builder.cpp` 第二行改成 `const auto& b = RequestBuilder{}.url("...");`，并删去对 `b.timeout` 的调用，只保留 `b.send()`。const 引用能延长临时对象的生命期，这样还悬垂吗？

<details markdown="1">
<summary>答案</summary>

仍然悬垂。生命期延长只发生在引用绑定到的泛左值是经由 [[class.temporary#6]] 列出的表达式得到的时候：临时量实质化、括号、数据成员访问、几种转型等。`url(...)` 是函数调用，返回的引用指向哪里，在调用处看不出来，所以不在名单里。`const` 与否无关。本机 ASan 对 `b.send()` 同样报 `stack-use-after-scope`。要让绑定安全，`&&` 版本必须按值返回。
</details>

!!! question "3"
    有人在 `OpenOptions` 里加了一行 `OpenOptions() = default;`，希望让默认构造的意图更明确。所有使用指派初始化器的调用会怎样？

<details markdown="1">
<summary>答案</summary>

全部编译失败。C++20 起聚合不能有任何用户声明的构造函数，包括预置的（[[dcl.init.aggr#1]] 第 1 项，[[P1008R1]]）。`OpenOptions` 不再是聚合，按 [[over.ics.list#2]]，指派列表到它没有隐式转换，本机 Clang 报 no matching function for call to 'open_file'。直接写 `OpenOptions o{.create = true};` 时，[[dcl.init.list#3]] 第 1 项同样不满足，Clang 报 initialization of non-aggregate type 'OpenOptions' with a designated initializer list。去掉这一行即可，默认成员初始化器已经表达了默认值。
</details>
