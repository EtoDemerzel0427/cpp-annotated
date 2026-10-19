---
title: 初始化列表
summary: std::initializer_list<E> 是列表初始化时编译器创建的、指向一个 const E 数组的轻量视图；本节规定它的接口，它的创建和底层数组的生命期由核心语言规定。
status: done
covers: *
papers: N2672, P2752R3
related: dcl.init.list, over.ics.list, dcl.spec.auto, class.temporary, stmt.ranged, support.signal, iterator.range
tags: 标准库, initializer_list, 列表初始化
updated: 2026-10-19
---

!!! tldr
    - `std::initializer_list<E>` 是一个指向 `const E` 数组的视图，复制它不会复制元素。
    - 元素是只读的，不能从中移动，所以 `vector<unique_ptr<int>> v{...}` 无法编译。
    - 底层数组的生命期由核心语言决定，从函数返回一个 `initializer_list` 会留下悬垂指针。
    - 程序不得特化 `initializer_list`，否则非良构。
    - 空列表的 `begin()` 与 `end()` 相等，但值未指定，判断是否为空要用 `empty()` 或 `size()`。

## 编译器替你做了什么

写下 `std::vector<int> v{1, 2, 3};` 时，编译器做了两件事（[[dcl.init.list]]）：

1. 创建一个类型为 `const int[3]` 的**底层数组**（[[g:backing-array]]），用 `1, 2, 3` 逐个复制初始化它的元素；
2. 构造一个指向这个数组的 `std::initializer_list<int>` 对象，传给 `vector` 的**初始化器列表构造函数**（[[g:initializer-list-constructor]]），也就是第一个形参为 `std::initializer_list<E>` 的构造函数。

`initializer_list` 自己没有能装入元素的公开构造函数，只有编译器能在列表初始化时创建非空的列表。它在重载决议中的优先级、底层数组的生命期，都由核心语言规定；本节只规定它的库接口。

¶1 [support.initlist.general] `<initializer_list>` 定义了这个类模板。本节的所有函数都是信号安全的（[[support.signal]]），可以在信号处理函数里调用。

## 接口 [initializer.list.syn]

```cpp
// 全部 freestanding
namespace std {
  template<class E> class initializer_list {
  public:
    using value_type      = E;
    using reference       = const E&;
    using const_reference = const E&;
    using size_type       = size_t;
    using iterator        = const E*;
    using const_iterator  = const E*;

    constexpr initializer_list() noexcept;

    constexpr const E* data() const noexcept;
    constexpr size_t size() const noexcept;
    constexpr bool empty() const noexcept;
    constexpr const E* begin() const noexcept;
    constexpr const E* end() const noexcept;
  };
}
```

`reference` 和 `iterator` 都是 const 的：通过 `initializer_list` 只能读元素。

### 它是一个视图（¶1）

!!! std
    An object of type `initializer_list<E>` provides access to an array of objects of type `const E`.

¶1 `initializer_list<E>` 的对象提供对一个 `const E` 数组的访问。注 1 说明，一对指针或者指针加长度是显然的表示方式，复制一个 `initializer_list` 不会复制底层元素。它和 `std::span<const E>` 一样，不拥有元素。

```cpp run title="initlist-ok.cpp" ok
#include <initializer_list>

int sum(std::initializer_list<int> il) {
  int s = 0;
  for (int x : il) s += x;
  return s;
}

int main() {
  std::initializer_list<int> il = {1, 2, 3};  // 数组的生命期延长到与 il 相同
  auto copy = il;                             // 浅复制：两者指向同一个数组
  return (sum({4, 5, 6}) == 15 && copy.begin() == il.begin()) ? 0 : 1;
}
```

由此有两个后果。

第一，元素不能移动。底层数组的元素是 `const E`，`std::move(*il.begin())` 的类型是 `const E&&`，只能匹配复制构造函数。所以容器的初始化器列表构造函数只能复制元素，下面的代码无法编译，因为 `unique_ptr` 不可复制：

```cpp run error
#include <memory>
#include <vector>
std::vector<std::unique_ptr<int>> v{std::make_unique<int>(1)};  // error: 需要复制 unique_ptr
```

即使元素可以复制，`{...}` 初始化的容器里，每个元素也都是从底层数组复制来的，而不是从初始化器直接构造的。

第二，数组的生命期不归它管。[[dcl.init.list#6]] 规定，底层数组和其他临时对象（[[class.temporary]]）一样，只是用它初始化一个 `initializer_list` 对象时，生命期像引用绑定到临时对象那样被延长，延长到那个对象的生命期为止。之后复制出去的 `initializer_list` 不会再延长它：

```cpp run title="initlist-dangling.cpp" ub
#include <initializer_list>

std::initializer_list<int> make() {
  return {1, 2, 3};      // 数组在 make 返回时销毁
}

int main() {
  auto il = make();
  return *il.begin();    // UB：读已经销毁的数组
}
```

本机 Clang 23 对 `return {1, 2, 3};` 给出 `-Wreturn-stack-address` 警告。

### 不得特化（¶2）

¶2 程序声明 `initializer_list` 的显式特化或偏特化，就是非良构的。

一般的规则（[[namespace.std]]）允许程序为自己定义的类型特化某些标准库类模板，这里更严格。原因是编译器要直接构造 `initializer_list` 对象，填入数组的地址和长度。用户特化了 `initializer_list<MyType>`，编译器就不知道该怎样构造它了。

```cpp run error
#include <initializer_list>
struct S {};
template<> class std::initializer_list<S> {};   // error: 不得特化
```

!!! impl
    libc++ 给这个类模板加了 Clang 的 `[[clang::no_specializations]]` 属性，所以上面的特化会被拒绝，诊断是 `'initializer_list' cannot be specialized`。libc++ 的数据成员是 `const E* __begin_` 和 `size_t __size_`，另有一个私有的 `(const E*, size_t)` 构造函数，编译器调用它，用户调用不到。

## 构造与访问 [support.initlist.cons] [support.initlist.access]

| 成员 | 规定 |
|---|---|
| `initializer_list()` | 后置条件：`size() == 0`（cons ¶1） |
| `begin()` | 指向数组开头；`size() == 0` 时，`begin()` 和 `end()` 的值未指定，但两者必须相同（access ¶1） |
| `end()` | `begin() + size()`（¶2） |
| `data()` | `begin()`（¶3） |
| `size()` | 数组的元素个数（¶4），常数复杂度（¶5） |
| `empty()` | `size() == 0`（¶6） |

空列表的 `begin()` 不保证是空指针，只保证等于 `end()`。libc++ 的默认构造函数把它设为 `nullptr`，但代码不应依赖这一点，判断是否为空要用 `empty()` 或 `size()`。

!!! note "`data()` 和 `empty()`"
    这两个成员是 C++23 之后的工作草案新加入的，特性测试宏 `__cpp_lib_initializer_list` 为 `202511L`（[[version.syn]]）。同时，`<initializer_list>` 里非成员的 `std::begin(initializer_list<E>)` 和 `std::end(initializer_list<E>)` 从概要中删除了；`<iterator>` 中通用的 `std::begin(c)`、`std::end(c)` 调用成员函数，同样适用（[[iterator.range]]）。截至写作时，本机 libc++ 还没有 `data()` 和 `empty()`，也没有定义这个宏，仍保留着非成员 `begin`、`end`。

## 与核心语言的交互

- **重载决议**（[[over.match.list]]）：类有初始化器列表构造函数时，非空的 `{...}` 优先考虑它们。所以 `std::vector<int> v{10, 1};` 是两个元素，`std::vector<int> v(10, 1);` 是十个 1。
- **`auto` 推导**（[[dcl.spec.auto]]）：`auto x = {1, 2};` 推导为 `std::initializer_list<int>`；C++17 起 `auto x{1};` 推导为 `int`，`auto x{1, 2};` 非良构。模板实参推导不会从 `{...}` 推导出 `initializer_list<T>`，除非形参本身写成 `std::initializer_list<T>`（[[temp.deduct.call]]）。
- **范围 for**（[[stmt.ranged]]）：`for (int x : {1, 2, 3})` 合法，范围被推导为 `initializer_list<int>`，数组的生命期延长到整个循环。
- **必须先声明**：使用 `std::initializer_list` 时（包括 `auto x = {1, 2};` 这种不写出类型名的隐式使用），如果它的声明不可达，程序非良构（[[dcl.init.list#2]]）。实践中就是要先 `#include <initializer_list>` 或包含某个会包含它的头文件。

!!! history
    `initializer_list` 随列表初始化在 C++11 引入（[[N2672]]），C++14 把它的成员改为 `constexpr`。C++26 起，底层数组是潜在非唯一对象（[[dcl.init.list]] 注 6，[[intro.object]]），内容为常量的数组可以放进静态只读存储，多次求值可以共享同一份存储（[[P2752R3]]）。
