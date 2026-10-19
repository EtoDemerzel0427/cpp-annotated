---
title: pimpl 与编译防火墙
summary: 把类的数据成员藏到一个指向不完整类型的指针后面：它解决的重编译级联和共享库 ABI 问题，unique_ptr 实现中特殊成员必须定义在哪里，const 传播、复制与移动后的空状态，C++26 的 std::indirect，fast pimpl，以及它的运行时代价和替代方案。
status: draft
order: 20
since: c++98
papers: P3144R2, P3019R14, N4388, P1413R3
related: unique.ptr, unique.ptr.dltr, expr.delete, class.dtor, class.base.init, dcl.fct.def.default, basic.def.odr, indirect, module.reach, topics/ownership-and-smart-pointers, topics/exception-safety, topics/special-members-and-elision, toolchain/linking-and-symbols, toolchain/modules-in-practice, patterns/factory-and-registration, patterns/type-erasure
tags: pimpl, 编译防火墙, ABI, 不完整类型, 惯用法
updated: 2026-10-19
---

!!! tldr
    - 类的私有数据成员写在头文件里，它们的类型、大小和偏移就编进了每一个包含这个头文件的翻译单元。改一个私有成员，所有使用者都要重新编译；如果使用者在另一个共享库里，不重编译就会读写错位的内存。
    - pimpl 把数据成员移进一个只在 `.cpp` 里定义的 `Impl`，头文件只留一个指针。外层类的 `sizeof` 从此固定，`Impl` 怎么改都不影响使用者。
    - 用 `unique_ptr<Impl>` 实现时，析构函数、所有构造函数和移动赋值都会实例化 `delete`，必须在 `Impl` 完整之后的 `.cpp` 里定义，哪怕只是 `= default`。
    - 指针不传播 `const`，也不会自动深复制，移动之后还会留下空指针。这三点要手工处理；C++26 的 `std::indirect<Impl>` 一次解决了前两点。
    - 代价是每个对象一次堆分配、每次访问多一次间接，以及跨翻译单元无法内联。fast pimpl 用对象内的定长缓冲区省掉分配，代价是把大小常量写进了 ABI。

## 改一个私有成员，整个项目重编译

一个按常规写法定义的类：

```cpp title="widget.h"
#pragma once
#include <map>
#include <regex>
#include <string>
#include <vector>

class Widget {
public:
  explicit Widget(std::string pattern);
  bool match(const std::string& s) const;
  int hits() const { return hits_; }
private:
  std::regex re_;
  std::map<std::string, std::vector<double>> cache_;
  mutable int hits_ = 0;
};
```

使用者只调用 `match` 和 `hits`，从不碰 `re_` 和 `cache_`。可是包含 `widget.h` 的每个 `.cpp` 都要解析 `<regex>` 和 `<map>`，而且它们的目标代码依赖 `Widget` 的布局：在栈上放一个 `Widget` 要知道 `sizeof(Widget)`，内联的 `hits()` 要知道 `hits_` 的偏移。

这是语言规则的直接结果。凡是要求类型完整的地方（定义该类型的对象、`sizeof`、访问成员），类的定义必须可达（[[basic.def.odr#14]]）。定义里包括私有成员，`private` 只限制名字能否被访问，不影响布局对使用者可见。

本机做了一个小实验：`widget.cpp` 加 20 个各自包含 `widget.h` 的使用者，用带 `-MMD` 依赖跟踪的 Makefile、`-O2`、单线程构建。给 `Widget` 加一个私有成员 `std::vector<int> extra_;` 之后：

| | 重新编译的翻译单元 | 增量构建耗时 | 一个使用者预处理后的行数 | 一个使用者的编译耗时 |
|---|---|---|---|---|
| 成员写在 `widget.h` | 21 | 7.4 s | 56070 | 0.32 s |
| pimpl，成员在 `widget.cpp` | 1 | 1.0 s | 27691 | 0.16 s |

pimpl 版本的头文件只包含 `<memory>` 和 `<string>`，所以每个使用者自己也编译得更快。实现细节的改动被挡在 `widget.cpp` 一个文件里，**编译防火墙**（compilation firewall）这个别名由此而来。

## 共享库：`sizeof` 被编进了调用方

第二个问题更严重。设想 `Widget` 由一个共享库提供，应用程序按 v1 的头文件编译。库升级到 v2 时，给 `Widget` 加了一个私有数组：

<div class="compare" markdown="1">

```cpp title="v1.h"
class Widget {
public:
  Widget();
  int get() const;
  static unsigned lib_size();
private:
  int a_;
};
```

```cpp title="v2.h"
class Widget {
public:
  Widget();
  int get() const;
  static unsigned lib_size();
private:
  long log_[4];   // v2 新增
  int a_;
};
```

</div>

```cpp title="app.cpp"
#include <cstdio>
#include "v1.h"
int main() {
  int guard = 7;
  Widget w;                       // 按 v1 在栈上留 4 字节
  std::printf("app sizeof=%zu lib sizeof=%u get=%d guard=%d\n",
              sizeof(Widget), Widget::lib_size(), w.get(), guard);
}
```

公有接口一个字都没改，函数的修饰名也没变，所以 v2 的 `.dylib` 可以直接替换 v1，动态链接成功。但 `app` 只在栈上留了 4 字节，库里的构造函数按 v2 的布局写入 40 字节。本机加 `-fsanitize=address` 运行，ASan 报告 `stack-buffer-overflow`，`WRITE of size 32` 发生在库里的 `Widget::Widget()`；不加 ASan 时进程直接段错误。

标准不知道共享库的存在。在它看来，这是同一个程序里 `Widget` 有两个不同的定义，违反了 [[basic.def.odr#16]]，属于**非良构但不要求诊断**（IFNDR：程序不合法，但编译器和链接器都不必报告）。实践中的说法是这个改动破坏了 **ABI**（application binary interface，二进制层面的接口约定，包括类型的大小、成员偏移、调用约定和符号名），见 [[toolchain/linking-and-symbols]]。

把同一个类改成 pimpl，头文件里只有一个指针：

```cpp title="p.h"
#include <memory>
class Widget {
public:
  Widget();
  ~Widget();
  int get() const;
  static unsigned lib_size();
private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
```

库在 `.cpp` 里定义 `Impl`，v2 往 `Impl` 里加同样的数组。本机重复上面的实验，应用程序不重新编译，两个版本的库都正常运行：`sizeof(Widget)` 始终是 8，`sizeof(Widget::Impl)` 从 4 变成 40，只有库自己知道。

pimpl 固定的是外层类的大小和布局。公有成员函数的签名、虚函数表仍然属于 ABI，改它们一样会破坏兼容性，布局问题见 [[toolchain/object-layout-and-vtables]]。

## 经典实现

```cpp title="widget.h"
#pragma once
#include <memory>
#include <string>

class Widget {
public:
  explicit Widget(std::string name);
  ~Widget();
  Widget(const Widget&);
  Widget& operator=(const Widget&);
  Widget(Widget&&) noexcept;
  Widget& operator=(Widget&&) noexcept;

  void add(int x);
  int total() const;
  const std::string& name() const;

private:
  struct Impl;                    // 只声明，不定义
  std::unique_ptr<Impl> impl_;
};
```

```cpp title="widget.cpp" ok
#include "widget.h"
#include <numeric>
#include <vector>

struct Widget::Impl {             // 私有成员都搬到这里
  std::string name;
  std::vector<int> items;
};

Widget::Widget(std::string name)
    : impl_(std::make_unique<Impl>(std::move(name))) {}
Widget::~Widget() = default;      // 从这里起 Impl 是完整类型

Widget::Widget(const Widget& o)   // 深复制
    : impl_(o.impl_ ? std::make_unique<Impl>(*o.impl_) : nullptr) {}
Widget& Widget::operator=(const Widget& o) {
  if (this != &o) *this = Widget(o);   // 先复制，再用移动提交
  return *this;
}
Widget::Widget(Widget&&) noexcept = default;
Widget& Widget::operator=(Widget&&) noexcept = default;

void Widget::add(int x) { impl_->items.push_back(x); }
int Widget::total() const {
  return std::accumulate(impl_->items.begin(), impl_->items.end(), 0);
}
const std::string& Widget::name() const { return impl_->name; }
```

```cpp title="main.cpp" ok
#include "widget.h"
#include <cstdio>

int main() {
  Widget a("a");
  a.add(1); a.add(2);
  Widget b = a;                   // 复制出独立的 Impl
  b.add(10);
  Widget c = std::move(b);        // 只移交指针
  std::printf("%s %d %d %zu\n", a.name().c_str(), a.total(), c.total(),
              sizeof(Widget));
}
```

本机加 ASan 和 UBSan 运行，输出 `a 3 13 8`，没有报告。`Impl` 是 `Widget` 的嵌套类，所以能访问 `Widget` 的私有成员；反过来 `Widget` 的成员函数通过 `impl_->` 访问实现。

头文件里六个特殊成员一个都不能省，也一个都不能在类内写 `= default`。下一节解释原因。

## 特殊成员必须定义在哪里

`struct Impl;` 只声明了 `Impl`，在头文件里它是**不完整类型**（[[g:incomplete-type]]）：知道它是一个类，不知道它的大小和成员。指向不完整类型的指针可以存储和传递，`unique_ptr` 也允许 `T` 不完整（[[unique.ptr.general#4]]）。问题出在销毁上。

### `delete` 要求完整类型

`unique_ptr<Impl>` 的默认删除器是 `default_delete<Impl>`，它的 `operator()` 要求 `T` 是完整类型（[[unique.ptr.dltr.dflt#3]]），然后执行 `delete ptr`。直接写 `delete` 也一样：

```cpp run title="delete-incomplete.cpp" error
struct Impl;
void f(Impl* p) { delete p; }   // error: Impl 不完整
```

!!! std
    If the object being deleted has incomplete class type at the point of deletion, the program is ill-formed. ([[expr.delete#4]])

    删除时对象的类型不完整，程序非良构。

这是 C++26 的规则（[[P3144R2]]）。以前只有当完整类型具有非平凡析构函数或类专属的 `operator delete` 时才是 UB，编译器一般只给警告，程序会静默地跳过析构函数。本机 Clang 23 在 `-std=c++23` 下对上例给出 `-Wdelete-incomplete` 警告，在 `-std=c++2c` 下报错 `cannot delete pointer to incomplete type 'Impl'`。`default_delete` 的完整性要求更早就有，本机 libc++ 在 `operator()` 里用 `static_assert(sizeof(_Tp) >= 0, ...)` 落实它，所以 `unique_ptr` 版本一直是编译错误。

### 哪些成员会实例化 `~unique_ptr<Impl>`

`~unique_ptr<Impl>` 是类模板的成员函数，只有在需要它的定义时才实例化（[[temp.inst]]）。下面几条规则决定了 `Widget` 的哪些成员需要它：

1. `Widget` 的析构函数执行完函数体之后，会调用每个数据成员的析构函数（[[class.dtor#13]]）。所以 `~Widget` 的定义处要实例化 `~unique_ptr<Impl>`。
2. 非委托构造函数会**潜在调用**（[[g:potentially-invoked]]）每个子对象的析构函数（[[class.base.init#14]]），因为构造到一半抛出异常时，要销毁已经构造好的成员。所以每个构造函数的定义处，包括带参数的、复制和移动构造函数，也要实例化它。
3. 被潜在调用的析构函数算作 odr-use（[[basic.def.odr#9]]）。移动赋值会销毁 `*this` 原来的 `Impl`，复制赋值和复制构造要用 `Impl` 的复制构造函数，它们同样要求完整类型。
4. 在类内隐式声明或写 `= default` 的特殊成员，不是在类定义处定义的，而是在第一次被 odr-use 的地方才隐式定义（[[dcl.fct.def.default#5]]）。那个地方通常在使用者的 `.cpp` 里，`Impl` 不完整。

第 4 条是大多数错误的来源。不写析构函数，隐式的 `~Widget` 就在使用者的代码里定义：

```cpp run title="implicit-dtor.cpp" error
#include <memory>
class Widget {
public:
  Widget();
  int value() const;
private:
  struct Impl;
  std::unique_ptr<Impl> impl;
};
void user() { Widget w; }   // error: 在这里隐式定义 ~Widget
```

本机 libc++ 的诊断是对不完整类型 `Widget::Impl` 使用了 `sizeof`，实例化链的最后一条指向 `user()`：`in implicit destructor for 'Widget' first required here`。

解决办法是在头文件里只声明，在 `.cpp` 里 `Impl` 的定义之后再写 `= default`。在首次声明之后才写 `= default` 的函数属于用户提供的函数，就在写 `= default` 的那一点定义（[[dcl.fct.def.default#5]]）。

| 成员 | 类内 `= default` 或不声明 | 原因 |
|---|---|---|
| 析构函数 | 在使用处定义，报错 | [[class.dtor#13]] |
| 任意构造函数（类内定义函数体） | 报错 | [[class.base.init#14]] |
| 默认构造函数 `= default` | 在使用处定义，报错 | 同上 |
| 移动构造函数 `= default` | 在使用处定义，报错 | 同上 |
| 移动赋值 `= default` | 在使用处定义，报错 | 销毁旧的 `Impl` |
| 复制构造、复制赋值 | 隐式声明为弃置，因为 `unique_ptr` 不可复制 | 要手写深复制 |

表中的报错都在本机 Clang 23 上逐一验证过，例如类内 `Widget(Widget&&) = default;` 在 `Widget b(std::move(a));` 处报错，提示 `in defaulted move constructor for 'Widget' first required here`。只声明不使用的成员不会被定义，也就不会报错，但头文件不能假设使用者不用它。

完整的推导过程和 `make_unique` 的细节见 [[topics/ownership-and-smart-pointers]] 中关于不完整类型的一节。

!!! tip "为什么 `shared_ptr<Impl>` 不需要这些"
    `shared_ptr` 在构造时就要求类型完整（[[util.smartptr.shared.const#4]]），并把怎样删除记在控制块里；之后的析构不再需要 `T` 完整。所以 `shared_ptr<Impl>` 成员可以让隐式析构函数留在头文件里。但它让复制出的两个 `Widget` 共享同一个 `Impl`，这一点在后文讨论。

## `const` 不会穿过指针

```cpp run title="const-leak.cpp" ok
#include <memory>
#include <vector>

class Widget {
public:
  Widget();
  ~Widget();
  int total() const;
private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

struct Widget::Impl { std::vector<int> items; };
Widget::Widget() : impl_(std::make_unique<Impl>()) {}
Widget::~Widget() = default;

int Widget::total() const {
  impl_->items.clear();           // 编译通过：const 没有传到 *impl_
  return 0;
}
int main() { Widget w; return w.total(); }
```

程序良构，但 `total()` 是 `const` 成员函数，却清空了对象的内容。在 `const` 成员函数里，`impl_` 的类型是 `const unique_ptr<Impl>`，而 `unique_ptr` 的 `operator->` 是 `const` 成员函数，返回的是 `Impl*`（[[unique.ptr.single.observers#6]]）。指针本身是 `const` 的，它指向的对象不是。

数据成员直接写在类里时，编译器会拒绝这种代码。pimpl 把成员移到指针后面，这层保护就丢了。修复方法是给指针包一层，让 `const` 的包装只交出 `const Impl*`：

```cpp run title="deep-const.cpp" error
#include <memory>
#include <utility>
#include <vector>

template <class T>
class deep_const_ptr {            // 手写的 const 传播包装
  std::unique_ptr<T> p_;
public:
  deep_const_ptr() = default;
  explicit deep_const_ptr(std::unique_ptr<T> p) noexcept : p_(std::move(p)) {}
  T* operator->() noexcept { return p_.get(); }
  const T* operator->() const noexcept { return p_.get(); }
  T& operator*() noexcept { return *p_; }
  const T& operator*() const noexcept { return *p_; }
  explicit operator bool() const noexcept { return static_cast<bool>(p_); }
};

class Widget {
public:
  Widget();
  ~Widget();
  int total() const;
private:
  struct Impl;
  deep_const_ptr<Impl> impl_;
};

struct Widget::Impl { std::vector<int> items; };
Widget::Widget() : impl_(std::make_unique<Impl>()) {}
Widget::~Widget() = default;

int Widget::total() const {
  impl_->items.clear();           // error: impl_-> 返回 const Impl*
  return 0;
}
int main() { Widget w; return w.total(); }
```

`deep_const_ptr` 的隐式析构函数会实例化 `~unique_ptr<Impl>`，但它只在 `~Widget` 的定义处被用到，那里 `Impl` 已经完整，上一节的规则不变。

Library Fundamentals TS 第 2 版提供了同样用途的 `std::experimental::propagate_const<std::unique_ptr<Impl>>`（[[N4388]]），本机 libc++ 有 `<experimental/propagate_const>`，换上它后上例在同一行报同样的错误。它从未进入标准，可移植的代码通常手写上面这样的包装。另一种常见做法是不加包装，只通过一对私有访问函数 `Impl& impl()` 和 `const Impl& impl() const` 访问实现，并约定不直接用 `impl_`，靠代码审查维持。

## 复制、移动与空状态

### 深复制

`unique_ptr` 不可复制，所以 `Widget` 隐式的复制构造函数被定义为弃置。要让 `Widget` 像普通值一样复制，复制构造函数要复制 `*impl_`，而不是指针：

```cpp
Widget::Widget(const Widget& o)
    : impl_(o.impl_ ? std::make_unique<Impl>(*o.impl_) : nullptr) {}
Widget& Widget::operator=(const Widget& o) {
  if (this != &o) *this = Widget(o);
  return *this;
}
```

复制赋值先构造一个完整的副本，再用不抛出的移动赋值提交。副本构造失败时 `*this` 没有任何改动，这就是强异常安全保证，见 [[topics/exception-safety]]。代价是每次赋值都新分配一个 `Impl`；如果 `Impl` 的复制赋值能复用已有的内存，并且基本保证就够了，可以改写成 `*impl_ = *o.impl_`（前提是两边都不为空）。

### 只声明析构函数的后果

只写了析构函数、没有声明移动操作的 pimpl 类，既不能复制也不能移动。用户声明的析构函数会阻止隐式声明移动构造函数（[[class.copy.ctor#8]]），于是 `std::move(a)` 退而选择复制构造函数，而它因为 `unique_ptr` 被弃置了。所以上面的头文件把五个成员全部声明出来。

### 移动之后的空指针

移动构造只是把指针交出去，被移动的对象留下一个空的 `impl_`。之后再调用它的成员函数就是解引用空指针：

```cpp title="moved.cpp" ub
#include "widget.h"
#include <cstdio>
int main() {
  Widget b("b");
  Widget c = std::move(b);
  std::printf("%d\n", b.total());   // b.impl_ 为空
}
```

本机 UBSan 报告 `member access within null pointer of type 'Widget::Impl'`，随后 ASan 报告 SEGV。

有三种处理方式。第一种是约定被移动的对象只能赋值或销毁，这和标准库对大多数类型的约定一致。第二种是每个成员函数检查 `impl_`，增加分支。第三种是让移动构造函数也分配一个新的 `Impl`，于是永远不为空，但移动不再是 `noexcept`，`std::vector` 扩容时会因此改用复制。第一种最常见，复制构造函数里的 `o.impl_ ? … : nullptr` 就是为了让被移动的对象仍然可以被复制和赋值。

### 共享的不可变实现

如果 `Impl` 构造之后从不修改，可以用 `std::shared_ptr<const Impl>`：复制 `Widget` 只增加引用计数，两个对象共享同一个 `Impl` 也观察不到区别。只要 `Impl` 可变，共享就破坏了值语义，修改一个对象会改到另一个。

标准库的实现里也能看到这种结构。本机 libc++ 的 `std::locale` 只有一个 `__imp*` 成员，`sizeof(std::locale)` 是 8；`std::filesystem::directory_iterator` 只有一个指向内部状态的 `shared_ptr`，大小是 16。

## C++26 的 `std::indirect`

`std::indirect<T>` 在堆上持有一个 `T`，但表现得像一个 `T` 类型的值（[[P3019R14]]）。用它做 pimpl 的持有者：

```cpp title="widget.h"
#include <memory>
#include <string>
class Widget {
public:
  explicit Widget(std::string name);
  ~Widget();
  Widget(const Widget&);
  Widget& operator=(const Widget&);
  Widget(Widget&&) noexcept;
  Widget& operator=(Widget&&) noexcept;
  int total() const;
private:
  struct Impl;
  std::indirect<Impl> impl_;
};
```

```cpp title="widget.cpp"
#include "widget.h"
#include <numeric>
#include <vector>
struct Widget::Impl { std::string name; std::vector<int> items; };

Widget::Widget(std::string name) : impl_(std::in_place, std::move(name)) {}
Widget::~Widget() = default;
Widget::Widget(const Widget&) = default;            // indirect 负责深复制
Widget& Widget::operator=(const Widget&) = default;
Widget::Widget(Widget&&) noexcept = default;
Widget& Widget::operator=(Widget&&) noexcept = default;

int Widget::total() const {
  // impl_->items.clear();                          // error: *impl_ 是 const Impl
  return std::accumulate(impl_->items.begin(), impl_->items.end(), 0);
}
```

本机 libc++ 还没有实现 `std::indirect`（`no template named 'indirect' in namespace 'std'`），上面的代码没有经过编译，所以不加判定。按草案，它和 `unique_ptr<Impl>` 的区别是：

- 复制构造函数用 `*other` 构造一个新的 `T`（[[indirect.ctor#9]]），复制赋值同理（[[indirect.assign#2]]），于是 `Widget` 的复制成员可以直接 `= default`。
- `const indirect<T>` 的 `operator->` 返回 `const_pointer`（[[indirect.obs]]），`const` 自动传播，不需要手写包装。
- 默认构造函数也会分配并构造一个 `T`（[[indirect.ctor#5]]），没有空状态。被移动之后会变成**无值**（[[g:valueless]]，[[indirect.general#1]]），这时解引用违反前置条件（[[indirect.obs#1]]）。和 `unique_ptr` 的空指针相比，只是多了 `valueless_after_move()` 可以查询。
- `T` 可以不完整（[[indirect.general#6]]），但析构函数要求 `T` 完整（[[indirect.dtor#1]]），复制构造要求 `is_copy_constructible_v<T>`（[[indirect.ctor#8]]），而这个 trait 本身要求完整类型。所以上一节关于特殊成员位置的规则照样适用，头文件里仍然要声明全部五个成员，在 `.cpp` 里 `= default`。

| | `unique_ptr<Impl>` | `deep_const_ptr<Impl>`（手写） | `indirect<Impl>` |
|---|---|---|---|
| `const` 传播 | 否 | 是 | 是 |
| 复制 | 手写深复制 | 手写深复制 | `= default` 即深复制 |
| 移动后 | 空指针 | 空指针 | 无值，可查询 |
| 默认构造 | 可为空 | 可为空 | 总是分配 |
| 特殊成员定义在 `.cpp` | 需要 | 需要 | 需要 |
| 可用性 | C++11 | 任意 | C++26，本机 libc++ 未实现 |

## fast pimpl：不分配的版本

如果每个对象一次堆分配不可接受，可以在对象内部预留一块定长、对齐的字节数组，把 `Impl` 就地构造在里面：

```cpp title="widget.h"
#pragma once
#include <cstddef>
#include <string>

class Widget {
public:
  explicit Widget(std::string name);
  ~Widget();
  Widget(const Widget&);
  Widget& operator=(const Widget&);
  void add(int x);
  int total() const;
private:
  struct Impl;
  static constexpr std::size_t impl_size = 48, impl_align = 8;
  alignas(impl_align) std::byte buf_[impl_size];   // Impl 就地构造在这里
  Impl& impl() noexcept;
  const Impl& impl() const noexcept;
};
```

```cpp title="widget.cpp" ok
#include "widget.h"
#include <new>
#include <numeric>
#include <vector>

struct Widget::Impl {
  std::string name;
  std::vector<int> items;
};

Widget::Impl& Widget::impl() noexcept {
  return *std::launder(reinterpret_cast<Impl*>(buf_));
}
const Widget::Impl& Widget::impl() const noexcept {
  return *std::launder(reinterpret_cast<const Impl*>(buf_));
}

Widget::Widget(std::string name) { ::new (buf_) Impl{std::move(name), {}}; }
Widget::~Widget() {
  static_assert(sizeof(Impl) <= impl_size, "enlarge impl_size");
  static_assert(alignof(Impl) <= impl_align, "enlarge impl_align");
  impl().~Impl();
}
Widget::Widget(const Widget& o) { ::new (buf_) Impl(o.impl()); }
Widget& Widget::operator=(const Widget& o) {
  impl() = o.impl();
  return *this;
}
void Widget::add(int x) { impl().items.push_back(x); }
int Widget::total() const {
  return std::accumulate(impl().items.begin(), impl().items.end(), 0);
}
```

本机配一个复制、赋值并打印结果的 `main.cpp`，加 ASan 和 UBSan 运行无报告，`sizeof(Widget)` 是 48。几处细节：

- `std::byte` 数组可以为在其中创建的对象**提供存储**（[[intro.object#3]]）。但数组和其中新建的 `Impl` 不是指针可互换的（[[basic.compound#7]]），`reinterpret_cast` 得到的指针仍然指向数组的字节，要经过 `std::launder` 才能得到指向 `Impl` 的指针（[[ptr.launder]]）。另一种写法是把 placement new 返回的指针存成成员，多占 8 字节。
- `static_assert` 只能写在 `Impl` 完整的地方，头文件里对 `Impl` 用 `sizeof` 是非良构的（[[expr.sizeof#1]]）。`Impl` 和两个常量都是私有的，所以检查放在成员函数里；析构函数一定会被定义，放在这里最稳妥。把 `impl_size` 改成 40，本机报错 `static assertion failed due to requirement 'sizeof(Widget::Impl) <= impl_size': enlarge impl_size`。
- C++23 起 `std::aligned_storage` 已弃用（[[P1413R3]]，[[depr.meta.types]]），用 `alignas` 修饰的 `std::byte` 数组代替它。

这种写法保住了第一个好处：头文件不再包含 `<vector>`，`Impl` 的改动只要不超过 48 字节，使用者就不必重新编译。第二个好处打了折扣：48 和 8 这两个数写进了头文件，成为 ABI 的一部分。`Impl` 超出预留的大小时，只能改常量，也就破坏了 ABI。这两个常量还依赖标准库实现：48 是本机 libc++ 中 `std::string`（24 字节）加 `std::vector<int>`（24 字节）的大小，libstdc++ 的 `std::string` 是 32 字节，同一个头文件要按平台给出不同的值。

此外，它失去了指针版本廉价的移动：移动 `Widget` 就是移动 `Impl` 的每个成员。上例只声明了复制操作，没有隐式的移动操作（[[class.copy.ctor#8]]），`std::move(w)` 会复制。复制赋值的异常安全保证也只是 `Impl` 自己的复制赋值所提供的那一级。

## 代价

### 一次分配，一次间接

本机用 `-O2` 比较两个只含一个 `int` 的类，成员函数都定义在另一个翻译单元里，一个直接存储，一个用 `unique_ptr<Impl>`。每种测 1000 万个对象：

| | 构造加析构 | 顺序遍历调用 `get()` | 打乱 `vector` 顺序后遍历 |
|---|---|---|---|
| 直接存储 | 1.5 ns | 0.9 ns/个 | 1.0 ns/个 |
| pimpl | 24 ns | 1.2 ns/个 | 7.8 ns/个 |

构造的差距来自 `operator new` 和 `operator delete`。顺序遍历时差距不大，因为按顺序分配的 `Impl` 在堆上恰好也是相邻的；把 `vector<Widget>` 打乱之后，每次访问都跳到不相关的地址，缓存未命中让遍历慢了约 7 倍。直接存储的对象本身就在 `vector` 的连续内存里，打乱顺序没有影响。

### 内联失效

<div class="compare" markdown="1">

```cpp godbolt flags="-std=c++2c -O2" ok
class Counter {
public:
  int get() const { return n_; }
private:
  int n_ = 0;
};
int sum(const Counter& c, int k) {
  int s = 0;
  for (int i = 0; i < k; ++i)
    s += c.get();
  return s;
}
```

```cpp godbolt flags="-std=c++2c -O2" ok
#include <memory>
class Counter {
public:
  Counter(); ~Counter();
  int get() const;  // 在 counter.cpp
private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
int sum(const Counter& c, int k) {
  int s = 0;
  for (int i = 0; i < k; ++i)
    s += c.get();
  return s;
}
```

</div>

本机 arm64 上，左边的循环整个被折叠掉了，`sum` 只剩一次加载、一次乘法和一次条件选择：

```text
ldr  w8, [x0]
mul  w8, w8, w1
cmp  w1, #0
csel w0, w8, wzr, gt
ret
```

右边的 `get()` 定义在别的翻译单元，编译器看不到它，也就不知道它没有副作用，只能在循环里调用 `k` 次 `bl __ZNK7Counter3getEv`。`get()` 本身是两次相互依赖的加载，先取 `impl_` 再取 `n`：

```text
ldr  x8, [x0]
ldr  w0, [x8]
ret
```

链接时优化（`-flto`）能把同一个可执行文件里的翻译单元合起来优化。本机把 `sum`、`get` 和一个构造 `Counter` 再调用 `sum` 的 `main` 分三个文件、加 `-flto` 编译，`main` 被优化成三条指令，连 `Impl` 的分配也被消除了。跨共享库的调用做不到这一点，而 ABI 稳定恰恰是用 pimpl 的主要理由之一，所以这时内联的损失是实打实的。

## 替代方案

### 抽象接口加工厂

```cpp run title="interface.cpp" ok
#include <memory>
#include <string>

class Widget {                     // widget.h：只有接口
public:
  virtual ~Widget() = default;
  virtual void add(int x) = 0;
  virtual int total() const = 0;
  static std::unique_ptr<Widget> create(std::string name);
};

#include <numeric>                 // widget.cpp
#include <vector>
namespace {
class WidgetImpl final : public Widget {
  std::string name_;
  std::vector<int> items_;
public:
  explicit WidgetImpl(std::string n) : name_(std::move(n)) {}
  void add(int x) override { items_.push_back(x); }
  int total() const override {
    return std::accumulate(items_.begin(), items_.end(), 0);
  }
};
}
std::unique_ptr<Widget> Widget::create(std::string name) {
  return std::make_unique<WidgetImpl>(std::move(name));
}

int main() {
  auto w = Widget::create("w");
  w->add(1); w->add(2);
  return w->total() == 3 ? 0 : 1;
}
```

接口类同样把数据成员挡在头文件之外，并且不需要转发函数：实现类直接实现虚函数。代价是使用者拿到的是 `unique_ptr<Widget>`，不能在栈上直接创建 `Widget`，也不能按值复制，每次调用经过虚函数表。它适合本来就需要多个实现或需要在测试中替换实现的场合，注册多个实现的写法见 [[patterns/factory-and-registration|工厂与自注册]]。

| | pimpl | 抽象接口 + 工厂 |
|---|---|---|
| 使用者看到的类型 | 值类型 `Widget` | `unique_ptr<Widget>` 或引用 |
| 调用开销 | 直接调用加一次间接 | 虚调用 |
| 复制 | 可手写深复制 | 需要虚 `clone()` |
| 多种实现 | 不支持 | 支持 |
| ABI 变化点 | 公有函数签名 | 虚函数的顺序和签名 |
| 样板代码 | 每个公有函数一个转发 | 无转发 |

如果想要可复制的值类型，又要在运行时换实现，那是 [[patterns/type-erasure|类型擦除]] 要解决的问题。

### 模块不隐藏布局

C++20 模块让导入方读取编译好的模块接口，不再反复解析头文件，第一个问题中预处理和解析的开销因此大大减少。但它不隐藏布局：

```cpp title="widget.cppm"
export module widget;
import std;
export class Widget {
public:
  int total() const { return n_; }
private:
  std::vector<int> items_;
  int n_ = 0;
};
```

```cpp title="use.cpp" ok
import widget;
static_assert(sizeof(Widget) == 32);   // 导入方知道布局
int f() { Widget w; return w.total(); }
```

本机用 Clang 23 和 libc++ 的 `std` 模块编译通过。导入方要创建 `Widget` 的对象，就需要完整类型，于是类的定义连同私有成员必须对它可达（[[basic.def.odr#14]]）。一个声明是否导出与它是否可达无关（[[module.reach#4]]），可达的声明决定了类型是否完整（[[module.reach#5]]）。改动私有成员就是改动模块接口，导入方要跟着重新编译；共享库的 ABI 问题也一样存在。模块的构建方式见 [[toolchain/modules-in-practice]]。

## 常见错误

| 错误 | 后果 | 修复 |
|---|---|---|
| 头文件里不声明析构函数，或在类内 `= default` | 使用者的 `.cpp` 编译失败 | 析构函数在 `.cpp` 里 `= default` |
| 构造函数或移动操作在类内定义 | 同上 | 一律在 `.cpp` 里定义 |
| 只声明了析构函数 | `Widget` 不能复制，也不能移动 | 声明全部五个特殊成员 |
| `const` 成员函数通过 `impl_` 修改实现 | 编译通过，违反 `const` 语义 | `deep_const_ptr` 或访问函数 |
| 复制构造函数复制指针（用 `shared_ptr` 换可复制性） | 两个对象共享可变状态 | 深复制，或 `indirect` |
| 使用被移动的对象 | 解引用空指针，UB | 约定只赋值或销毁 |
| 头文件里的内联函数访问 `impl_->` | 不能编译，`Impl` 不完整 | 函数定义移到 `.cpp` |
| fast pimpl 的常量只在一个平台上验证 | 另一个平台 `static_assert` 失败 | 按平台给出常量 |

## 什么时候用

| 情况 | 建议 |
|---|---|
| 共享库的公有类，需要跨版本保持 ABI | pimpl（或 C 接口、抽象接口） |
| 头文件依赖很重的类型（平台头文件、正则、第三方库），被大量文件包含 | pimpl |
| 对象数量大、创建频繁，或成员函数在热点循环里被调用 | 不用；直接存储，必要时把重依赖换成前向声明 |
| 需要多种实现或在测试中替换实现 | 抽象接口加工厂 |
| 不能接受堆分配，但想隐藏依赖 | fast pimpl，接受常量写进 ABI |
| 项目已经全面使用模块，只关心编译速度 | 模块可能已经够用；它不提供 ABI 隔离 |
| 编译器和标准库支持 C++26 `indirect` | 用 `indirect<Impl>` 代替 `unique_ptr<Impl>` 加手写复制 |

## 思考题

!!! question "1"
    `Widget` 只声明了 `explicit Widget(std::string)` 和 `~Widget()`，都在 `.cpp` 里定义，成员是 `unique_ptr<Impl>`。`void f(Widget a) { Widget b = std::move(a); }` 能编译吗？

<details markdown="1">
<summary>答案</summary>

不能。用户声明的析构函数使移动构造函数不被隐式声明（[[class.copy.ctor#8]]），`std::move(a)` 只能匹配复制构造函数。隐式的复制构造函数要复制 `unique_ptr`，而 `unique_ptr` 的复制构造函数是弃置的，所以 `Widget` 的复制构造函数也被定义为弃置。本机 Clang 23 报告 `call to implicitly-deleted copy constructor of 'Widget'`。在头文件里声明 `Widget(Widget&&) noexcept;` 并在 `.cpp` 里 `= default` 即可。
</details>

!!! question "2"
    把成员换成 `std::shared_ptr<Impl>`，构造函数在 `.cpp` 里用 `make_shared<Impl>()` 初始化，头文件里不声明析构函数。使用者 `{ Widget w; Widget c = w; }` 能编译吗？这个 `Widget` 有什么问题？

<details markdown="1">
<summary>答案</summary>

能编译，本机加 ASan 运行也没有报告。`shared_ptr` 允许 `T` 不完整（[[util.smartptr.shared.general#3]]），删除方式在构造时就记录下来（[[util.smartptr.shared.const#6]]），析构时只调用记录下来的删除器（[[util.smartptr.shared.dest#1]]），不需要 `T` 完整。需要 `Impl` 完整的只有创建它的那个构造函数。

问题在语义上：隐式的复制构造函数复制的是 `shared_ptr`，`c` 和 `w` 共享同一个 `Impl`，修改一个会影响另一个，`const` 也照样不传播。除非 `Impl` 构造后不可变（此时应写成 `shared_ptr<const Impl>`），这都不是值语义。
</details>

!!! question "3"
    fast pimpl 里，为什么不能把 `static_assert(sizeof(Impl) <= impl_size)` 写在头文件的类定义里？如果把它写进一个只在某些配置下才会被调用的成员函数，会发生什么？

<details markdown="1">
<summary>答案</summary>

头文件里 `Impl` 是不完整类型，`sizeof` 不能用于不完整类型（[[expr.sizeof#1]]），这正是 pimpl 想要的效果：使用者看不到 `Impl`。`static_assert` 只能放在 `Impl` 完整之后。

`static_assert` 声明在模板之外，只要它所在的函数定义被编译就会检查，与这个函数会不会被调用无关。所以写在任何一个被编译的成员函数定义里都会检查；选析构函数只是因为每个 fast pimpl 类都必须定义它，不会因为重构被删掉。如果把检查放进一个被 `#ifdef` 排除在某些配置之外的函数，那些配置就失去了这道检查。
</details>
