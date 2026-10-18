---
title: 初始化列表
summary: std::initializer_list<E>——列表初始化背后那个指向 const E 数组的轻量视图：复制不复制元素、不可特化、元素只读不可移动、底层数组的生命期由核心语言决定；以及 begin/end/size/data/empty 的精确契约
status: done
covers: *
papers: N2672, P2752R3
related: dcl.init.list, over.ics.list, dcl.spec.auto, class.temporary, stmt.ranged, support.signal, iterator.range
tags: 标准库, initializer_list, 列表初始化
updated: 2026-10-18
---

`std::initializer_list<E>` 是标准库中与核心语言耦合最紧的类模板之一。你写 `std::vector<int> v{1, 2, 3};` 时，编译器做了两件事（[[dcl.init.list]]）：

1. 创建一个**底层数组**（[[g:backing-array]]）`const int[3]`，用 `1, 2, 3` 复制初始化其元素；
2. 构造一个 `std::initializer_list<int>` 对象，**指向**这个数组，然后传给 `vector` 的**初始化器列表构造函数**（[[g:initializer-list-constructor]]）。

`initializer_list` 本身没有任何能装进元素的构造函数——它只能由编译器在列表初始化时创建。本节只规定它的**库接口**，而它的创建方式、底层数组的生命期、在重载决议中的优先级，都由核心语言规定。

¶1（[support.initlist.general]）：`<initializer_list>` 定义了一个与列表初始化（[[dcl.init.list]]）相关的类模板及若干支持函数。**本节规定的所有函数都是信号安全的**（[[support.signal]]）。

## 类模板（[initializer.list.syn]）

```cpp
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
```

注意 `reference` 和 `iterator` **都是 const 的**——通过 `initializer_list` 只能**读取**元素。

### 它是一个视图（¶1）

!!! std
    An object of type `initializer_list<E>` provides access to an array of objects of type `const E`.

    `initializer_list<E>` 类型的对象提供对一个 `const E` 对象数组的访问。

注 1：一对指针或者"指针加长度"是显而易见的表示方式；**复制一个 `initializer_list` 不会复制底层元素**。它在语义上相当于 `std::span<const E>`——非拥有的视图。

由此引出两个后果：

**元素不可移动。** 底层数组的元素是 `const E`，`*il.begin()` 是 `const E&`，`std::move` 之后是 `const E&&`，只能绑定到复制构造函数。所以 `std::vector<std::unique_ptr<int>> v{std::make_unique<int>(1)};` **无法编译**——`vector` 的初始化器列表构造函数只能复制元素，而 `unique_ptr` 不可复制。即使元素可复制，用 `{...}` 初始化容器也总是**复制**每个元素一次（先从初始化器复制到底层数组，再从底层数组复制到容器）。

**生命期不归它管。** 底层数组的生命期由 [[dcl.init.list]] 规定：它像一个**绑定到引用的临时对象**一样被延长（[[class.temporary]]），即延长到**直接从该列表初始化**的那个 `initializer_list` 对象的生命期。复制出去的 `initializer_list` **不会**延长它：

```cpp run title="initlist-dangling.cpp" ub
#include <initializer_list>

std::initializer_list<int> make() {
    return {1, 2, 3};          // 底层数组是 make 内的临时对象，return 语句不延长它的生命期
}                              // 函数返回时数组已销毁

int main() {
    auto il = make();
    return *il.begin();        // UB：底层数组已经不存在（Clang：-Wreturn-stack-address 警告）
}
```

```cpp run title="initlist-ok.cpp" ok
#include <initializer_list>

int sum(std::initializer_list<int> il) {     // 参数由调用者的列表初始化而来
    int s = 0;
    for (int x : il) s += x;                 // 范围 for 使用成员 begin()/end()
    return s;
}

int main() {
    std::initializer_list<int> il = {1, 2, 3};   // 底层数组的生命期延长到 il 的生命期
    auto copy = il;                              // 浅复制：copy.begin() == il.begin()
    return (sum({4, 5, 6}) == 15 && copy.begin() == il.begin()) ? 0 : 1;
}
```

### 不得特化（¶2）

如果声明了 `initializer_list` 的**显式特化**或**偏特化**，程序**非良构**。

这比一般的 [[namespace.std]] 规则更严格（一般规则允许对程序定义类型特化标准库模板）。原因是 `initializer_list` 的布局是编译器与库之间的约定：编译器直接构造它的对象（填入数组指针和长度），如果用户特化了 `initializer_list<MyType>`，编译器就不知道该怎么构造了。

!!! impl
    libc++ 在类模板上标注了 `_LIBCPP_NO_SPECIALIZATIONS`（展开为 Clang 的 `[[clang::no_specializations]]` 属性），于是特化尝试会被诊断：`'initializer_list' cannot be specialized: Users are not allowed to specialize this standard library entity`。libc++ 的表示是 `const E* __begin_; size_t __size_;`，以及一个**私有**的 `(const E*, size_t)` 构造函数——编译器直接调用它，用户调用不到。

## 构造与访问（[support.initlist.cons]、[support.initlist.access]）

| 成员 | 规格 |
|---|---|
| `initializer_list()` | ¶1 *Postconditions*：`size() == 0` |
| `begin()` | ¶1：指向数组开头的指针；若 `size() == 0`，`begin()` 和 `end()` 的值是**未指明的**，但**必须相同** |
| `end()` | ¶2：`begin() + size()` |
| `data()` | ¶3：`begin()` |
| `size()` | ¶4：数组中元素的个数；¶5 *Complexity*：常数 |
| `empty()` | ¶6：`size() == 0` |

¶1 中"值未指明但必须相同"：空的 `initializer_list` 的 `begin()` 不保证是空指针（libc++ 默认构造时是 `nullptr`，但从 `{}` 列表初始化创建的空列表不一定）。不要对 `begin()` 做空指针判断，应该用 `empty()` 或 `size()`。

!!! note "`data()` 与 `empty()`"
    `data()` 和 `empty()` 是较新的工作草案中加入的成员（特性测试宏 `__cpp_lib_initializer_list` 为 `202511L`，见 [[version.syn]]）。同时，旧版 `<initializer_list>` 里的非成员 `std::begin(initializer_list<E>)` 和 `std::end(initializer_list<E>)` 重载已从概要中删除——`<iterator>` 中通用的 `std::begin(c)`/`std::end(c)` 会调用成员函数，同样适用（[[iterator.range]]）。截至本文编写时，libc++ 尚未提供 `data()` 和 `empty()`，仍保留着非成员 `begin`/`end`。

## 与核心语言的交互

`initializer_list` 的大部分"魔法"都在核心语言里：

- **重载决议的偏好**（[[over.match.list]]）：类有初始化器列表构造函数时，非空的 `{...}` 列表初始化**优先**考虑它们。这就是 `std::vector<int> v{10, 1};`（两个元素）与 `std::vector<int> v(10, 1);`（十个 1）的区别。
- **`auto` 推导**（[[dcl.spec.auto]]）：`auto x = {1, 2};` 推导为 `std::initializer_list<int>`；而 `auto x{1};` 自 C++17 起推导为 `int`，`auto x{1, 2};` 非良构。模板参数推导**不会**从 `{...}` 推导出 `initializer_list<T>`，除非形参本身就写成 `std::initializer_list<T>`（[[temp.deduct.call]]）。
- **范围 for**（[[stmt.ranged]]）：`for (int x : {1, 2, 3})` 合法，范围初始化器被推导为 `initializer_list<int>`，其生命期延长到整个循环。
- **必须包含头文件**：[[dcl.init.list]] 规定，若在使用 `std::initializer_list`（包括隐式使用，例如 `auto x = {1, 2};`）之前没有声明它，程序非良构。

!!! history "历史"
    `initializer_list` 随统一初始化在 C++11 引入（[[N2672]]）。C++14 把它的成员变为 `constexpr`。此后核心语言多次修订了底层数组的规则：它的生命期与绑定到引用的临时对象相同；C++26 起，底层数组被明确为**潜在非唯一对象**（[[dcl.init.list]] 注 6，[[intro.object]]），于是常量内容的底层数组可以放进静态只读存储、多次求值可以共享同一份存储（[[P2752R3]]）。

## 小结

!!! summary
    - `initializer_list<E>` 是对 `const E` 数组的**非拥有视图**：复制不复制元素，元素只读，不能从中移动。
    - 只能由编译器在列表初始化中创建；用户不得特化它（非良构）。
    - 底层数组的生命期由核心语言决定；从函数返回 `initializer_list` 会悬垂。
    - 空列表的 `begin() == end()`，但值未指明；用 `empty()`/`size()` 判断。
    - 所有函数都是信号安全、`constexpr`、`noexcept` 的。
