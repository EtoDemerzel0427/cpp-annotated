---
title: 范围生成器 std::generator
summary: C++23 的 std::generator<Ref, Val, Allocator> 把协程变成一个 input_range 视图——reference/value/yielded 三个类型如何由 Ref、Val 推出；co_yield 左值时复制、yield_value 存指针；elements_of 与递归生成器的"活动栈"；begin() 只能调用一次；异常传播、分配器参数的位置约定；引用形参悬垂与 await_transform 被删除。
status: draft
covers: coro.generator, coroutine.generator.overview, generator.syn, coro.generator.class, coro.generator.members, coro.generator.promise, coro.generator.iterator, range.elementsof
since: c++23
papers: P2502R2
related: dcl.fct.def.coroutine, expr.yield, expr.await, support.coroutine, range.view, range.req, range.utility, allocator.requirements, topics/coroutines
tags: 标准库, 范围, 协程, generator
updated: 2026-10-18
---

C++20 给了协程的语言机制（[[dcl.fct.def.coroutine]]）却没给任何现成的协程类型，写一个"能 `co_yield` 的函数"需要自己实现 promise 和迭代器。C++23 的 [[P2502R2]] 提供了 `std::generator`（[[g:range-generator]]）：一个协程返回类型，同时是一个**视图**，于是生成器可以直接接上范围适配器。

!!! impl "实现现状"
    截至编写时，本站验证环境（Clang 23 + libc++）**没有** `<generator>` 头文件，本页示例按标准编写，未经本地运行验证。

## 概览（[coroutine.generator.overview]）

¶1 类模板 `generator` 呈现由协程求值产出的元素的视图。¶2 生成器通过**反复恢复**返回它的那个协程来生成元素序列；每次求值 `co_yield` 语句就产出一个元素。若形如 `co_yield elements_of(r)`，则 `r` 的每个元素依次作为序列元素产出。

```cpp run
#include <generator>
#include <ranges>
#include <cstdio>
std::generator<int> ints(int start = 0) {
  while (true)
    co_yield start++;
}
int main() {
  for (int i : ints() | std::views::take(3))
    std::printf("%d ", i);       // 0 1 2
}
```

无限序列配合 `take`——协程只在被请求时才运行到下一个 `co_yield`，是彻底的惰性。

## 头文件与类模板（[generator.syn]、[coro.generator.class]）

```cpp
template<class Ref, class Val = void, class Allocator = void>
class generator : public ranges::view_interface<generator<Ref, Val, Allocator>> {
  using value = conditional_t<is_void_v<Val>, remove_cvref_t<Ref>, Val>;
  using reference = conditional_t<is_void_v<Val>, Ref&&, Ref>;
public:
  using yielded = conditional_t<is_reference_v<reference>, reference, const reference&>;
  class promise_type;
  generator(const generator&) = delete;
  generator(generator&& other) noexcept;
  ~generator();
  generator& operator=(generator other) noexcept;
  iterator begin();
  default_sentinel_t end() const noexcept;
private:
  coroutine_handle<promise_type> coroutine_ = nullptr;
  unique_ptr<stack<coroutine_handle<>>> active_;
};
namespace pmr {
  template<class Ref, class Val = void>
    using generator = std::generator<Ref, Val, polymorphic_allocator<>>;
}
```

### 三个类型

| 写法 | *value* | *reference* | `yielded` |
|---|---|---|---|
| `generator<int>` | `int` | `int&&` | `int&&` |
| `generator<const int&>` | `int` | `const int&` | `const int&` |
| `generator<std::string&>` | `std::string` | `std::string&` | `std::string&` |
| `generator<int, int>`（显式 `Val`） | `int` | `int`（prvalue） | `const int&` |

默认情况下（`Val` 为 `void`），`generator<T>` 的引用类型是 `T&&`：元素以**右值引用**交给消费者，消费者可以从中移动。`yielded` 是 `promise_type::yield_value` 接受的类型。

¶1 *Mandates*：*value* 是 cv 非限定对象类型；*reference* 是引用或可复制构造的 cv 非限定对象类型；三条 `common_reference_with` 关系成立（注 1：保证迭代器能建模 `indirectly_readable` 从而是 `input_iterator`）。¶3 `generator` 的特化建模 `view` 与 `input_range`。¶4 为 `generator` 添加特化是{{ub}}。

`generator` **只能移动**（复制被删除），是一个拥有协程帧的视图——这正是 [[range.view]] 在 C++20 DR 后允许"只移动、拥有资源"的视图的典型受益者。不是借用范围。

## 成员（[coro.generator.members]）

- ¶1–¶2 移动构造：接管协程句柄与活动栈；注 1：从 `other` 取得的迭代器**不会失效**，而是变成指向 `*this` 的迭代器（迭代器只持有协程句柄，不持有 `generator` 的地址）；
- ¶3–¶4 析构：若持有协程则 `destroy()`。注 2：递归 yield 的子生成器由父协程帧中的可等待体持有，所以销毁根生成器会连带销毁整条生成器栈；
- ¶8–¶11 **`begin()`**：前置条件是协程挂起在初始挂起点；效果是把协程压入活动栈并 `resume()`，运行到第一个 `co_yield`（或结束）。注 4：**对同一个 generator 调用两次 `begin()` 是{{ub}}**——它违反了前置条件。这也是 [[range.req]] 只对 forward 范围要求 `begin()` 保持相等性的现实例子；
- ¶12 `end()` 返回 `default_sentinel`。

## promise_type（[coro.generator.promise]）

```cpp
class promise_type {
public:
  generator get_return_object() noexcept;
  suspend_always initial_suspend() const noexcept { return {}; }   // 惰性：创建时不运行
  auto final_suspend() noexcept;
  suspend_always yield_value(yielded val) noexcept;
  auto yield_value(const remove_reference_t<yielded>& lval)
    requires is_rvalue_reference_v<yielded> &&
             constructible_from<remove_cvref_t<yielded>, const remove_reference_t<yielded>&>;
  template<class R2, class V2, class Alloc2, class Unused>
    requires same_as<typename generator<R2, V2, Alloc2>::yielded, yielded>
    auto yield_value(ranges::elements_of<generator<R2, V2, Alloc2>&&, Unused> g) noexcept;
  // ... elements_of<generator&> 与任意 input_range 的重载
  void await_transform() = delete;
  void return_void() const noexcept {}
  void unhandled_exception();
  // operator new / delete：分配器支持
private:
  add_pointer_t<yielded> value_ = nullptr;
  exception_ptr except_;
};
```

### `co_yield` 一个值（¶4–¶9）

- ¶4 `yield_value(yielded val)`：`value_ = addressof(val)`——**只存地址**，不复制。`co_yield expr;` 中的临时量活到协程恢复为止（它在 *yield-expression* 所在的完整表达式中，[[expr.yield]]），所以迭代器解引用时它还活着；
- ¶6–¶9 当 `yielded` 是右值引用（默认的 `generator<T>`）而你 `co_yield` 了一个**左值**时：右值引用绑不上左值，于是选第二个重载——它返回一个可等待体，里面**复制**一份该左值，`value_` 指向这份副本。这保证消费者从 `T&&` 移动时不会偷走协程里的局部变量。

```cpp run
#include <generator>
#include <string>
#include <vector>
std::generator<std::string> names() {
  std::string s = "alice";
  co_yield s;                  // 左值：复制一份交出去，s 本身不会被消费者移走
  co_yield std::string("bob"); // prvalue：绑定到 string&&，不复制
}
int main() {
  std::vector<std::string> out;
  for (auto&& n : names()) out.push_back(std::move(n));   // 移动的是副本 / 临时量
}
```

### `await_transform() = delete`

promise 声明了一个被删除的、无参的 `await_transform`。按 [[expr.await]]，promise 类型中只要有名为 `await_transform` 的成员，`co_await expr` 就会被改写为 `co_await p.await_transform(expr)`——而它被删除且不接受实参，于是**在 generator 协程里写 `co_await` 是非良构的**。生成器是同步的拉取模型，不允许在其中等待异步操作。

### 异常（¶15–¶16）

`unhandled_exception()`：若当前协程是活动栈中**唯一**的一个（顶层生成器），等价于 `throw;`——异常直接从 `begin()`/`++` 抛给消费者；否则（它是被 `elements_of` 嵌套的子生成器）把异常存进 `except_`，由父生成器在恢复时的 `await_resume` 中 `rethrow_exception`，从而沿着生成器栈逐层传播。

### 分配器（¶17–¶22）

- `generator<T, V, Alloc>` 中 `Allocator` 非 `void` 时，用它（重新绑定后）分配协程帧；
- 也可以不在类型里写分配器，而是让协程的**形参**以 `allocator_arg_t, const Alloc&` 开头（或者是成员函数时在隐式对象形参之后），promise 的 `operator new` 会拦截这两个实参来分配协程帧——这是协程分配器的通用约定；
- `pmr::generator` 固定使用 `polymorphic_allocator<>`。

## 递归：`elements_of`（[range.elementsof]）与活动栈

`ranges::elements_of<R, Allocator>` 是一个简单的聚合（hosted）：

```cpp
template<range R, class Allocator = allocator<byte>>
struct elements_of {
  [[no_unique_address]] R range;
  [[no_unique_address]] Allocator allocator = Allocator();
};
template<class R, class Allocator = allocator<byte>>
  elements_of(R&&, Allocator = Allocator()) -> elements_of<R&&, Allocator>;
```

它是一个**标签**，在重载集里区分"把范围作为一个值产出"与"逐个产出范围的元素"（[range.elementsof] 例 1）：

```cpp
co_yield ranges::elements_of(r);   // 产出 r 的每个元素
co_yield r;                         // 把 r 本身当作一个值产出
```

promise 对 `elements_of` 有两类重载：

- **另一个 `generator`**（`yielded` 类型相同）：¶10–¶12 返回的可等待体把子生成器的句柄**压入活动栈**并直接恢复它；子生成器 `co_yield` 的值直接被最外层的迭代器看到，子生成器结束时（`final_suspend`，¶2–¶3）从栈中弹出并恢复父协程。迭代器的 `++`（[coro.generator.iterator] ¶7）总是恢复**栈顶**协程。这使得递归生成器的每一步都是 O(1) 的，而不是每层转发一次（O(深度)）；
- **任意 `input_range`**：¶13 用一个嵌套的生成器 lambda 把它包装成 `generator<yielded, void, Alloc>` 再按上一条处理（使用 `elements_of` 中携带的分配器）。

```cpp run
#include <generator>
#include <memory>
#include <ranges>
#include <cstdio>
struct Node { int v; std::unique_ptr<Node> l, r; };
std::generator<int> inorder(const Node* n) {        // 递归中序遍历
  if (!n) co_return;
  co_yield std::ranges::elements_of(inorder(n->l.get()));
  co_yield n->v;
  co_yield std::ranges::elements_of(inorder(n->r.get()));
}
int main() {
  Node root{2, std::make_unique<Node>(Node{1, nullptr, nullptr}),
               std::make_unique<Node>(Node{3, nullptr, nullptr})};
  for (int x : inorder(&root)) std::printf("%d ", x);   // 1 2 3
}
```

## 迭代器（[coro.generator.iterator]）

- `value_type` = *value*，`difference_type` = `ptrdiff_t`，只可移动，建模 `input_iterator`；
- ¶4–¶5 `operator*`：返回 `static_cast<reference>(*p.value_)`，其中 `p` 是活动栈顶协程的 promise；
- ¶6–¶8 `++`：恢复栈顶协程；
- ¶10 与 `default_sentinel` 比较：`coroutine_.done()`。

## 坑点

!!! pitfall "引用形参悬垂"
    ```cpp
    std::generator<char> chars(const std::string& s) { for (char c : s) co_yield c; }
    auto g = chars("temporary");     // 临时 string 在这一行结束时销毁
    for (char c : g) { }             // UB：协程帧里保存的是指向已销毁临时量的引用
    ```
    协程只把**引用形参本身**（而非被引用的对象）复制进协程帧（[[dcl.fct.def.coroutine]]）。由于 `initial_suspend` 是 `suspend_always`，函数体在 `chars(...)` 返回时一行都没执行，等到遍历时临时量早已不在。对生成器尽量**按值**接收参数。（直接写 `for (char c : chars("temporary"))` 则安全：范围 `for` 的初始化器中的临时量会活到循环结束。）

!!! pitfall "当作前向范围用"
    `generator` 只是 `input_range`：不能多趟遍历、不能 `views::reverse`、不能对同一对象调用两次 `begin()`；`ranges::distance(g)` 会把它消费掉。需要多趟时，先 `ranges::to<std::vector>()`。

## 小结

- `generator<Ref, Val, Alloc>`：拥有协程帧的只移动视图，建模 `input_range`；默认引用类型是 `Ref&&`；
- `co_yield` 只存地址；对默认的右值引用生成器 `co_yield` 左值会复制；
- `elements_of` 实现 O(1) 每步的递归生成；异常沿生成器栈传播；
- `begin()` 只能调一次；`co_await` 被禁止；引用形参是最常见的悬垂来源。
