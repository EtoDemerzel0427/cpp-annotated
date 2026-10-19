---
title: 范围生成器 std::generator
summary: C++23 的 std::generator 把一个协程变成只能单趟遍历的视图：元素类型怎样由模板实参推出，co_yield 左值时为什么要复制，elements_of 怎样实现递归生成，以及引用形参悬垂、begin 只能调用一次这些陷阱。
status: draft
covers: coro.generator, coroutine.generator.overview, generator.syn, coro.generator.class, coro.generator.members, coro.generator.promise, coro.generator.iterator, range.elementsof
since: c++23
papers: P2502R2, P2718R0
related: dcl.fct.def.coroutine, expr.yield, expr.await, support.coroutine, range.view, range.req, range.utility, allocator.requirements, topics/coroutines
tags: 标准库, 范围, 协程, generator
updated: 2026-10-19
---

!!! tldr
    - `std::generator<T>` 是一个协程返回类型，同时是一个视图：函数体里每执行一次 `co_yield`，遍历它的循环就拿到一个元素。
    - 它只建模 `input_range`：只能移动、只能遍历一趟，同一个对象上调用两次 `begin()` 是未定义行为。
    - 默认的 `generator<T>` 以 `T&&` 交出元素。`co_yield` 一个左值时，标准库先复制一份，所以消费者移动元素不会掏空协程里的局部变量。
    - `co_yield ranges::elements_of(g)` 把另一个生成器的元素逐个转交出去，递归生成器每一步的开销与递归深度无关。
    - 协程只保存引用形参本身，不保存被引用的对象。生成器的形参尽量按值传递。

C++20 只提供了协程的语言机制（[[dcl.fct.def.coroutine]]），没有提供任何现成的协程类型。想写一个能 `co_yield` 的函数，得自己实现 promise 类型和迭代器。C++23 的 [[P2502R2]] 补上了最常用的一种：`std::generator`（[[g:range-generator]]），声明在 `<generator>` 里。

!!! impl "本页例子没有判定标记"
    本机 Clang 23 + libc++ 还没有 `<generator>` 头文件，下面的例子按标准写成，没有经过本地编译。libstdc++（GCC 14 起）已经提供了它，可以点 godbolt 按钮在 GCC 上运行。

## 一个最简单的生成器 [coroutine.generator.overview]

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

¶1 `generator` 呈现的是一个协程产出的元素组成的视图。¶2 它反复恢复返回它的那个协程，协程每执行一次 `co_yield` 语句就产出一个元素。

`ints` 是一个无限循环，程序却能正常结束。原因是生成器是惰性的：协程创建后立即挂起，只有遍历它的循环要下一个元素时，才运行到下一个 `co_yield`。`take(3)` 拿够三个元素后不再要，协程也就不再运行，最后随着生成器对象一起销毁。

¶3 `generator` 的每个特化都建模 `view` 和 `input_range`，所以它能直接接上 `views::take` 这样的范围适配器（[[range.view]]）。它拥有协程帧，复制构造函数被删除，只能移动。

## 元素类型从哪里来 [coro.generator.class]

```cpp
template<class Ref, class Val = void, class Allocator = void>
class generator;
```

`Ref` 和 `Val` 决定了三个类型。*value* 是元素的值类型，*reference* 是解引用迭代器得到的类型，这两个是仅用于说明的名字；公开的成员类型 `yielded` 是 `co_yield` 接受的类型：

```cpp
using value     = conditional_t<is_void_v<Val>, remove_cvref_t<Ref>, Val>;
using reference = conditional_t<is_void_v<Val>, Ref&&, Ref>;
using yielded   = conditional_t<is_reference_v<reference>, reference, const reference&>;
```

| 写法 | *value* | *reference* | `yielded` |
|---|---|---|---|
| `generator<int>` | `int` | `int&&` | `int&&` |
| `generator<const int&>` | `int` | `const int&` | `const int&` |
| `generator<std::string&>` | `std::string` | `std::string&` | `std::string&` |
| `generator<int, int>` | `int` | `int`（纯右值） | `const int&` |

最常用的是第一行。只写一个实参 `generator<T>` 时，元素以右值引用 `T&&` 交给消费者，消费者可以把它移走。想让消费者只读，写 `generator<const T&>`。想按值交出元素，同时显式写出 `Val`。

¶1 用 *Mandates* 检查这几个类型是否合理：*value* 必须是无 cv 限定的对象类型，*reference* 必须是引用类型或者可复制构造的对象类型，它们之间还要有公共引用类型。注 1 说明，这些条件保证了迭代器满足 `input_iterator`。

## `co_yield` 做了什么 [coro.generator.promise]

协程里的 `co_yield e` 会调用 promise 对象的 `yield_value(e)`（[[expr.yield]]）。`generator` 的 promise 类型对单个值有两个重载：

```cpp
suspend_always yield_value(yielded val) noexcept;
auto yield_value(const remove_reference_t<yielded>& lval)
  requires is_rvalue_reference_v<yielded> && /* 可以从 lval 复制构造 */;
```

¶4 第一个重载只记下实参的地址，`value_ = addressof(val)`，不复制任何东西。这样做是安全的：`co_yield` 的操作数如果是临时量，它要到 `co_yield` 所在的完整表达式结束时才销毁，而协程在这个表达式中间挂起，消费者解引用迭代器时临时量还活着。

第二个重载只在 `yielded` 是右值引用时存在，也就是默认的 `generator<T>`。`co_yield` 一个左值时，右值引用 `T&&` 绑定不了左值，于是选中它。¶7 它返回的可等待对象里存着一份从左值复制来的副本，`value_` 指向这份副本。

```cpp run
#include <generator>
#include <string>
#include <vector>
std::generator<std::string> names() {
  std::string s = "alice";
  co_yield s;                    // 左值：交出去的是副本
  co_yield std::string("bob");   // 纯右值：绑定到 string&&，不复制
  // s 仍然是 "alice"
}
int main() {
  std::vector<std::string> out;
  for (auto&& n : names())
    out.push_back(std::move(n)); // 移走的是副本或临时量
}
```

如果没有这份副本，消费者对 `T&&` 做的移动会直接掏空协程里的 `s`，而协程恢复后可能还要用它。

## 惰性、`begin()` 与迭代器 [coro.generator.members]

promise 的 `initial_suspend()` 返回 `suspend_always`，所以调用 `ints()` 时函数体一行都没有执行。¶9 第一次调用 `begin()` 才恢复协程，运行到第一个 `co_yield` 或者函数结束。

¶8 `begin()` 的前置条件是协程停在初始挂起点。注 4 据此指出，对同一个生成器调用两次 `begin()` 是{{ub}}：第二次调用时协程早已离开了初始挂起点。

迭代器（[[coro.generator.iterator]]）很简单：

- `*it` 返回 `static_cast<reference>(*p.value_)`，`p` 是当前正在产出元素的协程的 promise；
- `++it` 恢复这个协程，让它运行到下一个 `co_yield`；
- `it == default_sentinel` 在协程运行结束时为真，`end()` 返回的就是 `default_sentinel`。

迭代器只保存协程句柄，不保存生成器对象的地址。所以注 1 说，移动一个生成器之后，原来取得的迭代器仍然有效，成为新对象的迭代器。

## 递归生成：`elements_of`

中序遍历一棵树，最自然的写法是递归。`co_yield ranges::elements_of(r)` 把范围 `r` 的每个元素依次作为本生成器的元素产出：

```cpp run
#include <generator>
#include <memory>
#include <ranges>
#include <cstdio>
struct Node { int v; std::unique_ptr<Node> l, r; };
std::generator<int> inorder(const Node* n) {
  if (!n) co_return;
  co_yield std::ranges::elements_of(inorder(n->l.get()));
  co_yield n->v;                 // const int 左值：复制一份交出
  co_yield std::ranges::elements_of(inorder(n->r.get()));
}
int main() {
  Node root{2, std::make_unique<Node>(1, nullptr, nullptr),
               std::make_unique<Node>(3, nullptr, nullptr)};
  for (int x : inorder(&root)) std::printf("%d ", x);   // 1 2 3
}
```

### `elements_of` 是一个标签 [range.elementsof]

`ranges::elements_of` 是一个只有两个成员的聚合，声明在 `<ranges>` 里：

```cpp
template<range R, class Allocator = allocator<byte>>
struct elements_of {
  [[no_unique_address]] R range;
  [[no_unique_address]] Allocator allocator = Allocator();
};
```

它的作用是在重载决议中区分两种意思。对一个 `generator<std::any>`，`co_yield r` 把范围 `r` 本身当作一个元素产出，`co_yield ranges::elements_of(r)` 则逐个产出 `r` 的元素。

### 活动栈

promise 对 `elements_of` 有两类重载。

第一类接受另一个 `generator`，要求它的 `yielded` 类型相同。返回的可等待对象把子生成器移进来，把子生成器的句柄压入一个栈，然后直接恢复子生成器。这个栈就是 `generator` 的私有成员 `active_`，它记录了当前嵌套着的所有协程，栈顶是正在产出元素的那一个（[[coro.generator.promise#11]]）。

迭代器的 `++` 总是恢复栈顶的协程，`*` 总是读栈顶协程的值。子生成器运行结束时，它的 `final_suspend` 把自己弹出栈，再恢复新的栈顶，也就是父协程（[[coro.generator.promise#3]]）。所以无论递归多深，取下一个元素都只恢复一个协程。如果每一层都用 `for (auto x : child) co_yield x;` 转发，取一个元素就要逐层恢复，开销与深度成正比。

第二类接受任意 `input_range`。按 [[coro.generator.promise#13]]，它用一个内部的生成器 lambda 把范围包装成 `generator<yielded, void, Alloc>`，再交给第一类重载处理。

[[coro.generator.members#4]] 的注 2 补充，子生成器归父协程帧里的可等待对象所有，所以销毁最外层的生成器会连带销毁整个栈。

## 异常与 `co_await`

协程体里抛出的异常没有被捕获时，会调用 promise 的 `unhandled_exception()`（[[coro.generator.promise#16]]）：

- 如果这个协程是栈中唯一的协程，也就是最外层的生成器，它等价于 `throw;`，异常从 `begin()` 或 `++` 直接抛给消费者；
- 否则它是被 `elements_of` 嵌套的子生成器，异常先存进 promise，父协程恢复时由可等待对象的 `await_resume` 重新抛出。异常就这样沿着栈一层层向外传播。

promise 还声明了一个被删除的、没有形参的 `await_transform`。按 [[expr.await]]，promise 类型只要有名为 `await_transform` 的成员，`co_await e` 就会改写成 `co_await p.await_transform(e)`。这个成员被删除，也不接受实参，所以在生成器协程里写 `co_await` 是非良构的。生成器是同步的拉取模型，不能在里面等待异步操作。

## 分配协程帧

协程帧默认用 `std::allocator` 分配。按 [[coro.generator.promise#17]]，要换分配器有两种写法：

- 写在类型里：`generator<T, V, Alloc>` 的 `Allocator` 不是 `void` 时，用它分配协程帧。`std::pmr::generator<T, V>` 就是 `Allocator` 固定为 `polymorphic_allocator<>` 的别名。
- 写在形参里：协程的前两个形参是 `allocator_arg_t, const Alloc&`（成员函数则跟在对象形参后面）时，promise 的 `operator new` 会收到这两个实参，用它们分配协程帧。这是协程分配器的通用约定。

## 常见陷阱

!!! pitfall "引用形参悬垂"
    ```cpp
    std::generator<char> chars(const std::string& s) {
      for (char c : s) co_yield c;
    }
    auto g = chars("temporary");   // 临时 string 在这一行结束时销毁
    for (char c : g) { }           // UB：s 引用的对象已经不在了
    ```
    协程把形参复制进协程帧，但引用形参复制的只是引用本身（[[dcl.fct.def.coroutine]]）。函数体在 `chars(...)` 返回时一行都没有执行，等到遍历时临时量已经销毁。生成器的形参尽量按值传递。

    直接写 `for (char c : chars("temporary"))` 从 C++23 起是安全的：范围 `for` 的初始化器中创建的临时量会活到循环结束（[[P2718R0]]，[[stmt.ranged]]）。C++20 中这样写同样会悬垂。

!!! pitfall "当作前向范围用"
    `generator` 只是 `input_range`：不能遍历两次，不能用 `views::reverse`，`ranges::distance(g)` 会把它消费掉。需要多趟访问时，先用 `std::ranges::to<std::vector>()` 存下来。

<details class="fine" markdown="1"><summary>其余条文</summary>

[coro.generator.class] ¶1.1 和 ¶2：`Allocator` 不是 `void` 时，它的 `pointer` 必须是指针类型，而且它要满足 *Cpp17Allocator* 要求。¶4：程序为 `generator` 添加特化是{{ub}}。

[coro.generator.members] ¶5–¶7：移动赋值运算符按值接收另一个生成器，与 `*this` 交换协程句柄和活动栈。注 3 同样说明，原来取得的迭代器变成 `*this` 的迭代器。

[coro.generator.promise] ¶1：`get_return_object()` 返回的生成器持有本协程的句柄和一个空的活动栈。¶9、¶12、注 1：调用这些 `yield_value` 重载的 `co_yield` 表达式类型是 `void`。

[coro.generator.iterator] ¶1–¶3：迭代器只能移动，移动时接管协程句柄。

</details>

## 小结

| 问题 | 结论 |
|---|---|
| `generator<T>` 交出什么 | `T&&`；`generator<const T&>` 交出只读引用 |
| `co_yield` 是否复制 | 一般只存地址；默认的右值引用生成器遇到左值时复制一份 |
| 能遍历几次 | 一次；`begin()` 只能调用一次 |
| 递归 | `co_yield ranges::elements_of(child)`，每步只恢复一个协程 |
| 异常 | 沿活动栈向外传播，最终从 `begin()` 或 `++` 抛出 |
| `co_await` | 非良构 |
