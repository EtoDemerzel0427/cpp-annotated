---
title: 容器适配器
summary: stack、queue、priority_queue 把一个底层容器包起来、只暴露一部分接口，复杂度、异常和前置条件都来自底层容器；pop() 为什么返回 void，priority_queue 的严格弱序前提，以及所有适配器共用的推导与失效规则。
status: done
covers: container.adaptors.general, queue.syn, queue, queue.defn, queue.cons, queue.cons.alloc, queue.mod, queue.ops, queue.special, priority.queue, priqueue.overview, priqueue.cons, priqueue.cons.alloc, priqueue.members, priqueue.special, stack.syn, stack, stack.general, stack.defn, stack.cons, stack.cons.alloc, stack.mod, stack.ops, stack.special, container.adaptors.format
related: containers, container.requirements, sequence.reqmts, flat.map, flat.set, deque, vector, list, alg.heap.operations, alg.sorting, allocator.uses
tags: 标准库, 容器, 容器适配器, 堆
papers: P1425R4, P1206R7, P2286R8, P0429R9, P1222R4
updated: 2026-10-19
---

!!! tldr
    - 适配器持有一个底层容器，成员函数大多是一行转发，比如 `stack::top()` 就是 `c.back()`。复杂度、异常保证、引用失效、前置条件都取决于底层容器。
    - `pop()` 返回 `void`，是为了让"取出元素"和"删除元素"分开，从而在拷贝抛出异常时不丢数据。
    - `priority_queue` 是按比较器排序的最大堆，比较器必须是严格弱序；用含 NaN 的 `double` 会让出队顺序错乱，而且通常检测不到。
    - `protected` 成员 `c` 和 `comp` 是标准规定的接口，派生类可以依赖它们，比如给 `priority_queue` 加 `reserve`。
    - 经典适配器没有迭代器，不是 range；格式化输出的是底层容器的存储顺序；`priority_queue` 没有 `==`。

**容器适配器**（[[g:container-adaptor]]，container adaptor）自己不管理内存，也不实现数据结构。它持有一个普通容器，把接口收窄成某种抽象：栈只能操作顶部，队列只能尾进头出，优先队列只能看到最大的元素。

[container.adaptors] 一共有七个类模板：

| 适配器 | 头文件 | 默认底层容器 | 底层容器要支持 | 迭代器 |
|---|---|---|---|---|
| `stack` | `<stack>` | `deque<T>` | `back`、`push_back`、`pop_back` | 无 |
| `queue` | `<queue>` | `deque<T>` | `front`、`back`、`push_back`、`pop_front` | 无 |
| `priority_queue` | `<queue>` | `vector<T>` | 随机访问迭代器，`front`、`push_back`、`pop_back` | 无 |
| `flat_map`、`flat_multimap` | `<flat_map>` | 两个 `vector` | 随机访问的序列容器 | 随机访问 |
| `flat_set`、`flat_multiset` | `<flat_set>` | `vector<Key>` | 随机访问的序列容器 | 随机访问（常量） |

前三个从 C++98 就有，下文称为经典适配器。后四个是 C++23 加入的扁平关联容器（[[P0429R9]]、[[P1222R4]]），规模和语义复杂得多，分别见 [[flat.map]] 和 [[flat.set]]。所有适配器共用的规则（[container.adaptors.general]）放在后面统一讲。

## 一切行为来自底层容器

经典适配器的成员几乎都直接定义在类概要里：`queue::front()` 就是 `{ return c.front(); }`，`stack::pop()` 就是 `{ c.pop_back(); }`。所以下面几条结论在条文里没有字面写出，但完全确定：

1. **复杂度**等于底层操作的复杂度。`stack<T, vector<T>>::push` 是摊还常数时间，`stack<T, list<T>>::push` 是严格常数时间。
2. **异常保证**取决于底层操作。`push` 是否有强保证，看 `c.push_back` 有没有；对 [[vector]] 来说，元素类型不可拷贝、移动构造又可能抛出时就没有。
3. **前置条件**也一样。在空的适配器上调用 `front()`、`back()`、`top()`、`pop()`，后果就是在空容器上调用 `c.front()`、`c.back()`、`c.pop_front()`、`c.pop_back()` 的后果。C++26 起这四个操作在 [[sequence.reqmts]] 中都是加固前置条件（[[sequence.reqmts#72]]、[[sequence.reqmts#76]]、[[sequence.reqmts#114]]、[[sequence.reqmts#118]]）：加固实现中违反它们会以契约违反终止，非加固实现中仍是 {{ub}}。
4. **引用失效**也一样。`stack<int, vector<int>>` 的 `top()` 返回的引用，会在下一次触发重新分配的 `push` 之后悬空；默认的 `stack<int>` 用 [[deque]]，在两端插入不让引用失效，所以不会。

本机 libc++ 用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 编译，对空的 `stack::pop`、`queue::pop`、`priority_queue::pop`、`priority_queue::top` 调用都以 `SIGTRAP` 终止。libc++ 不在适配器层面另做检查，触发的是底层容器的断言。

`priority_queue::pop()` 不是一行转发，而是 `pop_heap(c.begin(), c.end(), comp); c.pop_back();`。[[pop.heap#2]] 要求区间是有效的非空堆，这只是普通前置条件，没有加固。所以严格地说，空 `priority_queue` 上的 `pop()` 在加固检查之前就已经是 UB 了。libc++ 的 `pop_heap` 对空区间什么也不做，随后 `c.pop_back()` 的加固检查才终止程序。

## queue 与 stack

### 底层容器的要求（[queue.defn] ¶1、[stack.general] ¶1）

[queue.defn] ¶1 任何支持 `front()`、`back()`、`push_back()`、`pop_front()` 的序列容器都可以用来实例化 `queue`，特别是 [[list]] 和 [[deque]]。[[vector]] 没有 `pop_front`。

[stack.general] ¶1 `stack` 只需要 `back()`、`push_back()`、`pop_back()`，`vector`、`list`、`deque` 都可以。

这些要求不是 *Constraints*（不满足时让函数退出重载决议的那种约束），而是对模板实参的说明。类模板的成员函数只在被使用时才实例化（[[temp.inst]]），所以不满足要求的容器，只在调用到缺失的成员时才报错：

<div class="compare" markdown="1">

```cpp run ok
#include <queue>
#include <vector>
int main() {
  std::queue<int, std::vector<int>> q;
  q.push(1);         // 只需要 push_back
  return q.back();
}
```

```cpp run error
#include <queue>
#include <vector>
int main() {
  std::queue<int, std::vector<int>> q;
  q.push(1);
  q.pop();   // error: 没有 pop_front
}
```

</div>

### 接口（[queue.defn]、[stack.defn]）

| 成员 | `queue` | `stack` |
|---|---|---|
| 访问 | `front()` 即 `c.front()`，`back()` 即 `c.back()` | `top()` 即 `c.back()` |
| 插入 | `push(x)` 即 `c.push_back(x)` | 同左 |
| 原位构造 | `emplace(args...)` 即 `return c.emplace_back(args...)` | 同左 |
| 区间插入 {{c++23}} | `push_range(rg)`（[queue.mod] ¶1） | `push_range(rg)`（[stack.mod] ¶1） |
| 删除 | `pop()` 即 `c.pop_front()` | `pop()` 即 `c.pop_back()` |
| 交换 | `swap(q)`，`noexcept(is_nothrow_swappable_v<Container>)` | 同左 |

`emplace` 的返回类型是 `decltype(auto)`。C++17 起序列容器的 `emplace_back` 返回新元素的引用，适配器原样返回它。`priority_queue::emplace` 却返回 `void`，因为新元素经过 `push_heap` 之后已经不知道在哪个位置了。

当前草案中，所有成员（包括构造函数）都是 `constexpr`。

[queue.mod] ¶1 `push_range(rg)` 在 `c.append_range(std::forward<R>(rg))` 是合法表达式时就用它，否则退回 `ranges::copy(rg, back_inserter(c))`。所以没有 `append_range` 的自定义容器也能用。

### 构造函数（[queue.cons]、[stack.cons]）

| 段落 | 签名 | 效果 |
|---|---|---|
| ¶1 | `explicit queue(const Container& cont)` | 用 `cont` 初始化 `c` |
| ¶2 | `explicit queue(Container&& cont)` | 用 `std::move(cont)` 初始化 `c` |
| ¶3 | `queue(InputIterator first, InputIterator last)` {{c++23}} | 用 `first, last` 初始化 `c` |
| ¶4 | `queue(from_range_t, R&& rg)` {{c++23}} | 用 `ranges::to<Container>(std::forward<R>(rg))` 初始化 `c` |

[stack.cons] ¶1–¶4 与此相同。迭代器对构造来自 [[P1425R4]]，`from_range` 构造和 `push_range` 来自 [[P1206R7]]。

默认构造函数单独写成 `queue() : queue(Container()) {}`，不是 `explicit` 的。C++20 之前它是通过一个带默认实参的 `explicit` 构造函数提供的，结果默认构造也成了 `explicit`，`std::queue<int> q = {};` 这样的复制列表初始化会失败。C++20 把它拆了出来。

### 带分配器的构造函数（[queue.cons.alloc]、[stack.cons.alloc]）

¶1 是整个小节的开关：

!!! std
    If `uses_allocator_v<container_type, Alloc>` is `false` the constructors in this subclause shall not participate in overload resolution.

¶2–¶8 的效果都是把分配器作为最后一个实参交给 `c` 的构造：`queue(a)` 用 `a` 初始化 `c`，`queue(cont, a)` 用 `cont, a`，`queue(q, a)` 用 `q.c, a`，`from_range` 版本调用 `ranges::to<Container>(std::forward<R>(rg), a)`。

这组构造函数是为了让适配器参与 uses-allocator 构造（[[allocator.uses]]）。标准为每个适配器特化了 `uses_allocator`，让它继承 `uses_allocator<Container, Alloc>`。于是 `std::pmr::vector<std::stack<int, std::pmr::vector<int>>>` 的外层分配器会自动传给每个内层 `stack` 的底层容器。

### 比较（[queue.ops]、[stack.ops]）

¶1–¶6 六个关系运算符都返回 `x.c op y.c`；¶7 的 `operator<=>` 要求 `three_way_comparable<Container>`，返回 `x.c <=> y.c`。两个栈相等，当且仅当底层序列逐元素相等，不只是栈顶相同。

`==`、`<=>` 之外，`!=`、`<` 等仍然单独声明。这样底层容器只有 `<`、没有 `<=>` 时，适配器的 `<` 照样可用。

## pop() 为什么返回 void

```cpp run title="pop-returns-void.cpp" error
#include <stack>

int main() {
  std::stack<int> s;
  s.push(1);
  int x = s.pop();   // error: pop() 返回 void
}
```

三个经典适配器的 `pop()` 都返回 `void`，取出并删除要写两句：`auto x = s.top(); s.pop();`。这是为了异常安全。设想 `pop()` 返回元素：

```cpp
T pop() {
  T tmp = std::move(c.back());   // (a)
  c.pop_back();                  // (b) 元素已经从容器中删除
  return tmp;                    // (c) 构造返回值：可能抛出异常
}
```

如果第 (c) 步把 `tmp` 拷贝给调用者时抛出了异常，元素已经从栈里删除，却没有交到调用者手里，数据就丢了，强异常保证无从谈起。把观察（`top`）和修改（`pop`）分开之后，`top()` 返回引用不会抛出，拷贝发生在调用者那里，即使抛出，栈也完好无损；`pop()` 只做销毁，可以不抛出。这个问题最早由 Tom Cargill 在 1994 年的文章 *Exception Handling: A False Sense of Security* 中提出。

C++17 的保证复制消除并没有让这个理由过时。`return tmp;` 返回的是具名对象，具名返回值优化仍然是可选的；而且 `x = s.pop();` 这样的赋值同样可能抛出。现代并发队列常提供 `bool try_pop(T& out)` 或返回 `optional<T>` 的变体，代价是要求 `T` 的移动不抛出，或者接受较弱的保证。

!!! lawyer "从 priority_queue::top() 里偷走元素"
    `priority_queue::top()` 只有 const 版本，返回 `const_reference`，因为修改堆顶可能破坏堆的性质。有一种常见的写法是 `T x = std::move(const_cast<T&>(pq.top())); pq.pop();`。底层元素本身不是 const 对象，所以 `const_cast` 后修改它不违反 [[dcl.type.cv]]。

    但随后的 `pop()` 调用 `pop_heap`，它的前置条件要求整个区间是有效的堆（[[pop.heap#2]]）。被移走的堆顶（比如变成了空字符串）可能已经小于它的子节点，严格按条文这是 {{ub}}。libc++ 的 `pop_heap` 先把堆顶移出、再下沉空位，不会再比较原来的堆顶，所以这种写法碰巧能用，但依赖的是实现细节。

## priority_queue

### 堆与严格弱序（[priqueue.overview] ¶1）

¶1 任何具有随机访问迭代器、支持 `front()`、`push_back()`、`pop_back()` 的序列容器都可以用来实例化 `priority_queue`，特别是 `vector`（默认）和 `deque`。同一段还说明了一个前提：

> the library assumes that the function or function object defines a strict weak ordering.

库假设比较器是**严格弱序**（[[g:strict-weak-ordering]]，[[alg.sorting]]）。这个假设不成立时，之后所有 `make_heap`、`push_heap`、`pop_heap` 的前置条件都失去了意义。各构造函数的前置条件也都重复了这一点（[priqueue.cons] ¶1、¶3、¶5、¶7）。

`priority_queue` 的全部状态就是 `c` 和 `comp`，`c` 始终是关于 `comp` 的最大堆（[[alg.heap.operations]]）。`top()` 返回 `c.front()`，堆顶是区间的第一个元素，即按 `comp` 最大的元素。所以 `priority_queue<int, vector<int>, greater<int>>` 是最小堆：比较反过来了，最大也就反过来了。

### 违反严格弱序：NaN

`double` 的 `<` 遇到 NaN 时不是严格弱序：`NaN < x` 和 `x < NaN` 都为假，于是 NaN 与每个数都等价，而等价不再传递（1 与 NaN 等价，NaN 与 5 等价，但 1 < 5）。

```cpp run title="pq-nan.cpp" ub
#include <queue>
#include <limits>
#include <cstdio>

int main() {
  constexpr double nan = std::numeric_limits<double>::quiet_NaN();
  std::priority_queue<double> pq;
  for (double d : {1.0, 2.0, nan, 3.0, 4.0, 5.0})
    pq.push(d);   // UB：NaN 破坏了严格弱序
  while (!pq.empty()) { std::printf("%g ", pq.top()); pq.pop(); }
  std::printf("\n");
}
```

本机 libc++ 输出 `4 5 3 2 1 nan`，4 排在了 5 前面，换一个插入顺序结果又不同。打开 `_LIBCPP_HARDENING_MODE_DEBUG` 也没有检出：库无法在 O(log N) 的 `push` 里验证全局的顺序关系。修正的办法是让比较器显式处理 NaN（比如把 NaN 当作最小），或者在入队前过滤掉。

### 构造函数（[priqueue.cons]、[priqueue.cons.alloc]）

所有放入了元素的构造函数，最后都调用 `make_heap(c.begin(), c.end(), comp)`，把任意序列整理成堆。[[make.heap]] 最多做 3N 次比较，是线性时间。

| 段落 | 签名 | 效果 |
|---|---|---|
| ¶1–¶2 | `priority_queue(const Compare& x, const Container& y)`，以及 `Container&&` 版本 | 用 `x` 初始化 `comp`，用 `y` 构造 `c`，再 `make_heap` |
| ¶3–¶4 | `priority_queue(first, last, const Compare& x = Compare())` | 用 `first, last` 初始化 `c`，用 `x` 初始化 `comp`，再 `make_heap` |
| ¶5–¶6 | `priority_queue(first, last, x, const Container& y)`，以及 `Container&&` 版本 | 先用 `y` 初始化 `c`，再 `c.insert(c.end(), first, last)`，最后 `make_heap` |
| ¶7–¶8 | `priority_queue(from_range_t, R&& rg, const Compare& x = Compare())` {{c++23}} | `c` 取 `ranges::to<Container>(std::forward<R>(rg))`，再 `make_heap` |

一次把整批数据交给构造函数是 O(N)，逐个 `push` 是 O(N log N)。先收集、后建堆是常见的优化。

[priqueue.cons.alloc] ¶1 与 queue、stack 相同：`uses_allocator_v<container_type, Alloc>` 为假时，这些构造函数全部退出重载决议。¶2–¶13 的模式也一样：分配器交给 `c` 的构造；没有给出比较器的版本值初始化 `comp`；放入了元素的版本以 `make_heap` 收尾；只从另一个 `priority_queue` 拷贝或移动的 ¶6–¶7 不需要，因为源对象已经是堆。

### 成员（[priqueue.members]）

| 段落 | 成员 | 效果 |
|---|---|---|
| ¶1–¶2 | `push(x)` | `c.push_back(x); push_heap(c.begin(), c.end(), comp);` |
| ¶3–¶4 | `push_range(rg)` {{c++23}} | 先追加全部元素（`append_range` 或 `ranges::copy`），再如同 `make_heap` 那样恢复堆性质；后置条件是 `is_heap(c.begin(), c.end(), comp)` |
| ¶5 | `emplace(args...)` | `c.emplace_back(...); push_heap(...)`，返回 `void` |
| ¶6 | `pop()` | `pop_heap(c.begin(), c.end(), comp); c.pop_back();` |

`push_range` 没有规定逐个 `push_heap`（M 个元素是 M log(N+M)），而是说恢复堆性质 as if by `make_heap`（O(N+M)），¶4 只要求结果是堆。M 远小于 N 时逐个插入反而更快，所以实现可以按 M 和 N 的大小选择算法。由此也可知，等价元素在堆中的排列、之后 `pop` 出等价元素的次序，都不能依赖。

类概要末尾有一句注释 "no equality is provided"：`priority_queue` 没有 `==` 和 `<=>`。包含相同元素的两个堆，内部排列可以不同，逐元素比较 `c` 没有意义，按多重集合比较又需要 O(N log N)。

```cpp run title="pq-no-equality.cpp" error
#include <queue>

int main() {
  std::priority_queue<int> a, b;
  return a == b;   // error: priority_queue 没有 operator==
}
```

[priqueue.special] ¶1–¶2 非成员 `swap` 要求 `is_swappable_v<Container>` 和 `is_swappable_v<Compare>` 都为真，效果如同 `x.swap(y)`。成员 `swap` 依次交换 `c` 和 `comp`。

## protected 成员 c：留给派生类的接口

三个经典适配器的类定义里都写着：

```cpp
protected:
  Container c;          // stack、queue、priority_queue
  Compare comp;         // 仅 priority_queue
```

这不是仅用于阐述的成员（flat 系列里标着 `// exposition only` 的私有成员才是），而是规范性接口的一部分：成员名必须是 `c` 和 `comp`，访问级别必须是 `protected`。所以派生类可以合法地依赖它们，常见的用途是给 `priority_queue` 加上 `reserve` 或 `clear`：

```cpp run title="reservable-pq.cpp" ok
#include <queue>
#include <cassert>

template<class T>
struct reservable_pq : std::priority_queue<T> {
  void reserve(std::size_t n) { this->c.reserve(n); }
  void clear() noexcept { this->c.clear(); }   // 空序列一定是堆
  const auto& underlying() const { return this->c; }
};

int main() {
  reservable_pq<int> pq;
  pq.reserve(1024);
  for (int i : {3, 1, 4, 1, 5}) pq.push(i);
  assert(pq.top() == 5);
  assert(pq.underlying().capacity() >= 1024);
  pq.clear();
  assert(pq.empty());
}
```

!!! pitfall "派生类要自己维护堆不变式"
    `priority_queue` 的所有公有成员都假设 `c` 是关于 `comp` 的有效堆。派生类直接改写了 `c` 的元素之后如果不重新 `make_heap`，后续的 `push`、`pop` 就违反了 [[push.heap]] 和 [[pop.heap]] 的前置条件，是 {{ub}}。上例中 `clear()` 是安全的，因为空区间一定是堆。

## C++23 的区间支持与格式化

```cpp run title="adaptors-ranges.cpp" ok
#include <queue>
#include <stack>
#include <vector>
#include <list>
#include <ranges>
#include <cassert>
#include <type_traits>

int main() {
  std::vector<int> v{3, 1, 4, 1, 5};

  std::stack s(v.begin(), v.end());              // 迭代器对 + 推导指引
  static_assert(std::is_same_v<decltype(s), std::stack<int>>);   // 底层是 deque<int>

  std::queue q(std::from_range, v | std::views::take(3));
  q.push_range(std::vector{9, 2, 6});
  assert(q.size() == 6 && q.front() == 3 && q.back() == 6);

  std::priority_queue pq(std::from_range, v);
  pq.push_range(std::list{9, 2});                // 任何元素类型可转换的输入区间
  assert(pq.top() == 9);

  std::stack<int, std::vector<int>> sv;
  int& top = sv.emplace(42);                     // 返回 emplace_back 的结果
  assert(&top == &sv.top());

  // 适配器本身不是 range：没有 begin() 和 end()
  static_assert(!std::ranges::range<std::stack<int>>);
  static_assert(!std::ranges::range<std::priority_queue<int>>);
}
```

最后两行说明了经典适配器的本质：没有迭代器。栈的契约就是只能看到顶部，提供遍历就等于承认它只是一个 `deque`。确实需要遍历时，直接使用底层容器，或者像上一节那样通过派生类访问 `c`。

### 格式化（[container.adaptors.format]）

¶1 对 `queue`、`priority_queue`、`stack`，标准库提供 `formatter` 特化，要求底层容器本身可以格式化。它只有一个仅用于阐述的成员 `underlying_`，是底层容器的区间格式化器。¶2 `parse` 转发给 `underlying_`。¶3：

!!! std
    *Effects*: Equivalent to: `return underlying_.format(r.c, ctx);`

所以打印的是底层容器的存储顺序，不是出栈顺序，也不是优先级顺序：

```cpp run title="adaptor-format.cpp" ok
#include <queue>
#include <stack>
#include <print>

int main() {
  std::stack<int> s;
  for (int i : {3, 1, 4}) s.push(i);
  std::priority_queue<int> pq;
  for (int i : {3, 1, 4, 1, 5}) pq.push(i);

  std::println("{}", s);    // [3, 1, 4]：栈底在左，栈顶在右
  std::println("{}", pq);   // 堆数组的排列，本机是 [5, 4, 3, 1, 1]
}
```

区间格式说明符照常可用，例如 `"{::02}"` 作用于每个元素。这个特化随 C++23 的区间格式化提案 [[P2286R8]] 加入。

三个头文件的概要里还把 `enable_nonlocking_formatter_optimization` 对这三个适配器特化为 `false`。`std::print` 默认在格式化期间锁住输出流；这个变量为真的类型允许实现先格式化到缓冲区，再一次写出（[[format.formatter.spec]]）。适配器的格式化会调用底层容器和元素类型的 formatter，这些用户代码与流锁的交互是否安全，库无法确定，所以保守地设为 `false`。

## 所有适配器共用的规则（[container.adaptors.general]）

这一节的规则同时适用于 flat 系列，其中有几条主要是为 flat 系列写的。

### T 必须等于 Container::value_type（¶1–¶2）

¶1 列出各头文件定义了哪些适配器。¶2 规定了适配器的基本形态：每个适配器有一个或多个名为 `Container`、`KeyContainer` 或 `MappedContainer` 的模板参数；至少有一个构造函数以引用接收这样的容器，并把它拷贝或移动进来；容器接受分配器时，还可以给构造函数传一个兼容的分配器。

!!! std
    For the container adaptors that take a single container template parameter `Container`, the first template parameter `T` of the container adaptor shall denote the same type as `Container::value_type`.

这里只写了 shall，没有写违反的后果；flat 系列在 [[flat.map#8]] 中则把同类要求直接写成了非良构。实践中两者效果相同，libc++ 在 `stack`、`queue`、`priority_queue` 的类体里都放了 `static_assert`：

```cpp run title="value-type-mismatch.cpp" error
#include <stack>
#include <vector>

int main() {
  std::stack<long, std::vector<int>> s;   // error: T 是 long，Container::value_type 是 int
  s.push(1);
}
```

适配器的 `value_type` 等成员类型都取自 `Container`，`T` 在类定义里几乎用不到。它是冗余信息，冗余信息必须一致，否则就会出现 `stack<long, vector<int>>::value_type` 是 `int` 这种令人困惑的结果。

### swap 不额外抛异常（¶3）

¶3 适配器的 `swap` 只在底层容器或 `Compare` 的 `swap` 抛出时才抛出。落到各个适配器上，成员 `swap` 是 `noexcept(is_nothrow_swappable_v<Container>)`（`priority_queue` 还要加上 `Compare`）；非成员 `swap` 是 `noexcept(noexcept(x.swap(y)))`，并要求 `is_swappable_v<Container>`（[queue.special]、[stack.special]、[priqueue.special] 的 ¶1–¶2）。

### 引用失效与底层容器相同（¶5）

!!! std
    the `insert`, `emplace`, and `erase` members affect the validity of iterators, references, and pointers to the adaptor's container(s) in the same way that the containers' respective `insert`, `emplace`, and `erase` members do.

这一条主要是为 flat 系列写的。条文自带的例子说 `flat_map::insert` 可能让所有迭代器失效，因为默认底层容器是 `vector`。flat 容器在 [[flat.map#2]] 中声明不满足关联容器的失效要求（`std::map` 的插入不让任何迭代器失效），¶5 就是替代的规则。经典适配器没有 `insert` 和 `erase`，`emplace` 的情形见开头一节的第 4 条。

### 推导时排除不合格的类型（¶4、¶6–¶8）

¶4 带有 `InputIterator` 模板参数的构造函数模板，如果推导出的类型不够格作为输入迭代器，就不参与重载决议。

¶6 推导指引在下列情况下不参与重载决议：

| 小项 | 条件 | 防止的误推导 |
|---|---|---|
| ¶6.1 | `InputIterator` 推导出的不是输入迭代器 | 把两个整数当作迭代器对 |
| ¶6.2 | `Compare` 推导出的是分配器 | `priority_queue(first, last, alloc)` 把分配器当成比较器 |
| ¶6.3 | `Container`、`KeyContainer`、`MappedContainer` 推导出的是分配器 | 把分配器当成容器 |
| ¶6.4 | 没有容器参数、有 `Allocator` 参数，但推导出的不是分配器 | 把比较器当成分配器 |
| ¶6.5、¶6.6、¶6.8 | 容器参数和 `Allocator` 都有，但 `uses_allocator_v<容器, Allocator>` 为假 | 给不兼容的容器配分配器 |
| ¶6.7 | 有 `KeyContainer` 和 `Compare`，但 `Compare` 不能比较两个 `const KeyContainer::value_type&` | 把容器或分配器当成比较器 |

什么算够格的输入迭代器或分配器，由 [[container.reqmts#69]] 规定，而且有意留了余地：实现能在多大程度上判定某个类型不是输入迭代器、不是分配器，是未指定的。标准只规定了下限：整数类型一定不算输入迭代器；类型 `A` 至少要有 `A::value_type`，并且 `declval<A&>().allocate(size_t{})` 良构，才可能算分配器。这是纯语法的判断，不检查语义。

```cpp run title="adaptor-ctad.cpp" ok
#include <queue>
#include <flat_map>
#include <deque>
#include <vector>
#include <string>
#include <memory_resource>
#include <type_traits>
#include <cassert>

int main() {
  std::vector<int> v{5, 1, 4};
  std::pmr::polymorphic_allocator<int> pa;

  // ¶6.2：第三个实参是分配器，带 Compare 参数的推导指引被排除
  std::priority_queue pq(v.begin(), v.end(), pa);
  static_assert(std::is_same_v<decltype(pq),
      std::priority_queue<int, std::vector<int, std::pmr::polymorphic_allocator<int>>>>);

  // 两个容器：flat_map 的五个模板参数全部推导出来
  std::deque<std::string> ks{"b", "a"};
  std::deque<double> vs{2.0, 1.0};
  std::flat_map fm(std::move(ks), std::move(vs));
  static_assert(std::is_same_v<decltype(fm),
      std::flat_map<std::string, double, std::less<std::string>,
                    std::deque<std::string>, std::deque<double>>>);
  assert(fm.begin()->first == "a" && fm.begin()->second == 1.0);
}
```

¶6.5 的反面：普通的 `std::vector<int>` 配 `pmr::polymorphic_allocator` 时，`uses_allocator_v` 为假，`stack(Container, Allocator)` 这条推导指引退出，没有别的候选：

```cpp run title="ctad-uses-allocator.cpp" error
#include <stack>
#include <vector>
#include <memory_resource>

int main() {
  std::vector<int> v;
  std::pmr::polymorphic_allocator<int> a;
  std::stack s(v, a);   // error: 没有可行的推导指引（¶6.5）
}
```

¶7–¶8 说明推导指引里可以使用几个仅用于阐述的别名模板：`iter-value-type`（[[sequences.general]]），`iter-key-type`、`iter-mapped-type`、`range-key-type`、`range-mapped-type`（[[associative.general]]），以及 ¶8 新定义的 `alloc-rebind`，即 `allocator_traits<A>::rebind_alloc<T>`。flat 系列的 `from_range` 推导指引用它把一个分配器分别重绑定给键容器和值容器。

## 实现现状

{{impl}} 本机 Homebrew Clang 23 + libc++ 的实测结果：

- `priority_queue` 已经完整 `constexpr`，可以在 `static_assert` 中建堆和出队。
- `queue` 和 `stack` 的成员还没有标 `constexpr`，在常量求值中使用会失败。libc++ 的 `<queue>` 却已经把 `__cpp_lib_constexpr_queue` 定义为 `202502L`，与 `std::queue` 的实际状态不一致；`__cpp_lib_constexpr_stack` 没有定义。依据特性测试宏写 `constexpr` 代码时要注意这一点。
- C++23 的迭代器对构造、`from_range` 和 `push_range`、格式化都可用。

## 历史

| 版本 | 变化 |
|---|---|
| C++98 | `stack`、`queue`、`priority_queue`；`protected` 成员 `c`、`comp`；`pop()` 返回 `void` |
| C++11 | 移动构造、`emplace`、带分配器的构造函数和 `uses_allocator` 特化、成员 `swap` |
| C++17 | 推导指引；`emplace` 改为返回 `decltype(auto)` |
| C++20 | `operator<=>`；默认构造函数不再是 `explicit` |
| C++23 | 迭代器对构造、`from_range` 构造和 `push_range`、格式化、flat 系列 |
| C++26 | 全部成员 `constexpr`；底层序列容器的 `front`、`back`、`pop_front`、`pop_back` 成为加固前置条件，适配器经由委托同样受益 |

## 思考题

!!! question "思考题 1"
    为什么标准不用 *Constraints* 在声明 `std::queue<int, std::vector<int>>` 时就拒绝它？

<details markdown="1">
<summary>答案</summary>

[queue.defn] ¶1 只是说支持这些操作的序列容器可以用来实例化 `queue`，这是对模板实参的说明。*Constraints* 只能附着在函数或函数模板上，决定它是否参与重载决议（[[structure.specifications]]）。给整个类模板加概念约束，会让只用 `push` 和 `back` 的 queue 这种部分合法的用法失效，也会破坏 C++98 以来的兼容性。
</details>

!!! question "思考题 2"
    为什么 `priority_queue::push_range` 明确写了后置条件 `is_heap(...)`，而 `push` 没有？

<details markdown="1">
<summary>答案</summary>

`push` 的效果是 as if by 一段确定的代码，`push_back` 加 `push_heap`，[[push.heap]] 本身就保证结果是堆，不必再写。`push_range` 的效果是 restores the heap property as if by `make_heap`，¶4 明确写出后置条件，是在说明真正受约束的是结果是堆这一性质：用 `make_heap` 整体重建还是逐个 `push_heap`，实现可以自由选择。对使用者来说，这意味着等价元素在堆中的排列不能依赖任何特定算法。
</details>

!!! question "思考题 3"
    两个 `std::stack<int>`，一个依次压入 1、2、3，另一个压入 1、2、3、4 后再 `pop()`。它们 `==` 吗？换成 `std::priority_queue<int>` 呢？

<details markdown="1">
<summary>答案</summary>

两个 `stack` 的底层 `deque` 都是 `[1, 2, 3]`，[stack.ops] ¶1 规定 `==` 就是 `x.c == y.c`，所以相等。比较只看当前存储的序列，与操作历史无关。

`priority_queue` 没有 `==`，这样写是编译错误。即使通过派生类比较 `c`，包含相同元素的两个堆也可能有不同的数组排列，这正是标准不提供 `==` 的原因。
</details>

## 小结

| 方面 | 规则 |
|---|---|
| 行为 | 复杂度、异常保证、引用失效、前置条件（含加固）都由底层容器决定 |
| `pop()` | 返回 `void`，观察与删除分离，保证异常安全 |
| `priority_queue` | 关于 `comp` 的最大堆；比较器必须是严格弱序；没有相等比较 |
| `c`、`comp` | `protected` 的规范性接口，派生类可以使用，但要维护堆不变式 |
| 遍历与输出 | 没有迭代器，不是 range；格式化输出底层容器的存储顺序 |
| 推导 | ¶6 的规则区分容器、比较器、分配器和迭代器；`uses_allocator` 特化让适配器参与 uses-allocator 构造 |
