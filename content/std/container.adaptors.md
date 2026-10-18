---
title: 容器适配器
summary: queue / priority_queue / stack 与四个 flat 容器的共同法则——"包一个容器、只暴露一部分接口"，复杂度、异常与前置条件全部委托给底层容器；pop() 为何返回 void，priority_queue 的堆不变式与严格弱序前提，C++23 的范围构造与格式化
status: done
covers: container.adaptors.general, queue.syn, queue, queue.defn, queue.cons, queue.cons.alloc, queue.mod, queue.ops, queue.special, priority.queue, priqueue.overview, priqueue.cons, priqueue.cons.alloc, priqueue.members, priqueue.special, stack.syn, stack, stack.general, stack.defn, stack.cons, stack.cons.alloc, stack.mod, stack.ops, stack.special, container.adaptors.format
related: containers, container.requirements, sequence.reqmts, flat.map, flat.set, deque, vector, list, alg.heap.operations, alg.sorting, allocator.uses
tags: 标准库, 容器, 容器适配器, 堆
updated: 2026-10-18
---

**容器适配器**（[[g:container-adaptor]] / *container adaptor*）不自己管理内存，也不自己实现数据结构：它持有一个"真正的"容器对象，把它的接口**收窄**成某种抽象——栈只能动顶部、队列只能尾进头出、优先队列只能看最大值。标准对它们的规定因此特别"薄"：绝大多数成员函数的效果一行就写完了，`{ return c.back(); }`，剩下的一切（复杂度、异常、失效、前置条件）都要到底层容器的条款里去找。

[container.adaptors] 一共托管了七个类模板：

| 适配器 | 头文件 | 默认底层容器 | 对底层容器的要求 | 有迭代器吗 | 本站笔记 |
|---|---|---|---|---|---|
| `stack` | `<stack>` | `deque<T>` | `back`、`push_back`、`pop_back` | 无 | 本页 |
| `queue` | `<queue>` | `deque<T>` | `front`、`back`、`push_back`、`pop_front` | 无 | 本页 |
| `priority_queue` | `<queue>` | `vector<T>` | 随机访问迭代器 + `front`、`push_back`、`pop_back` | 无 | 本页 |
| `flat_map` / `flat_multimap` | `<flat_map>` | 两个 `vector` | 随机访问的序列容器 | 随机访问 | [[flat.map]] |
| `flat_set` / `flat_multiset` | `<flat_set>` | `vector<Key>` | 随机访问的序列容器 | 随机访问（常量） | [[flat.set]] |

前三个是 C++98 就有的"经典适配器"，后四个是 C++23 加入的**扁平关联容器**（[[P0429R9]]、[[P1222R4]]）。后者虽然也叫 adaptor，但接口规模与语义复杂度完全是另一个量级，本站单独成页。本页讲适配器的通用规则（[container.adaptors.general]）和三个经典适配器，以及只适用于它们的格式化支持（[container.adaptors.format]）。

阅读前置：[[container.requirements]]（容器要求总表，包括迭代器失效表）、[[sequence.reqmts]]（`front`/`pop_back` 等操作的精确语义与加固前置条件）、[[alg.heap.operations]]（`priority_queue` 的全部算法内核）。

## 通用法则（[container.adaptors.general]）

### ¶1–¶2：构造即拷贝，`T` 必须等于 `Container::value_type`

¶1 只是头文件清单。¶2 定下适配器的基本形态：

- 每个适配器有一个或多个名为 `Container`、`KeyContainer` 或 `MappedContainer` 的模板参数，表示被适配的容器类型；
- 至少有一个构造函数以引用接收这样的容器，并把它**拷贝**（或移动）进适配器；
- 若容器接受分配器，则可以给适配器的构造函数额外传一个"兼容的分配器"；否则就用普通的拷贝/移动构造。

!!! std
    For the container adaptors that take a single container template parameter `Container`, the first template parameter `T` of the container adaptor shall denote the same type as `Container::value_type`.
    对只有一个 `Container` 参数的适配器，第一个模板参数 `T` 必须与 `Container::value_type` 是同一类型。

这条 "shall" 约束的是**用户**，条文本身没有写 "ill-formed"。对比一下：flat 系列在 [[flat.map#8]] 里明确规定 `Key` 与 `KeyContainer::value_type` 不同则 *program is ill-formed*。实践中两者效果相同——libc++ 在 `stack`、`queue`、`priority_queue`、`flat_map` 的类体里都放了 `static_assert`：

```cpp run title="value-type-mismatch.cpp" error
#include <stack>
#include <vector>

int main() {
  std::stack<long, std::vector<int>> s;   // error: T 是 long，Container::value_type 是 int
  s.push(1);
}
```

适配器的 `value_type` 等成员类型全部取自 `Container`，`T` 在类定义里几乎没有被用到——它是冗余信息，而冗余信息必须一致，否则 `stack<long, vector<int>>::value_type` 是 `int` 这种结果只会让人困惑。

### ¶3：swap 不额外抛异常

适配器的 `swap` 除非底层 `Container`/`KeyContainer`/`MappedContainer` 或 `Compare` 对象的 swap 抛出，否则不抛。这一条落到每个适配器的成员 `swap` 上就是 `noexcept(is_nothrow_swappable_v<Container>)`（`priority_queue` 还要加上 `Compare`），非成员 `swap` 则是 `noexcept(noexcept(x.swap(y)))`，并以 `is_swappable_v<Container>` 作 *Constraints*（[queue.special] ¶1–¶2、[stack.special] ¶1–¶2、[priqueue.special] ¶1–¶2）。

### ¶4 与 ¶6：迭代器对构造函数与推导指引的"过滤"

¶4：带 `InputIterator` 模板参数的**构造函数模板**，若推导出的类型不够格作输入迭代器，则不参与重载决议。这防止了 `stack<int> s(alloc1, alloc2)` 这类调用误入迭代器对重载。

¶6 是更长的推导指引过滤清单——在以下情况下推导指引不参与重载决议：

| 小项 | 条件 | 防止的误推导 |
|---|---|---|
| ¶6.1 | `InputIterator` 推导出非输入迭代器 | 把两个整数当迭代器对 |
| ¶6.2 | `Compare` 推导出一个分配器 | `priority_queue(first, last, alloc)` 把分配器当比较器 |
| ¶6.3 | `Container`/`KeyContainer`/`MappedContainer` 推导出一个分配器 | 把分配器当容器 |
| ¶6.4 | 没有容器参数、有 `Allocator` 参数，但推导出的不是分配器 | 把比较器当分配器 |
| ¶6.5、¶6.6、¶6.8 | 同时有容器参数与 `Allocator`，但 `uses_allocator_v<容器, Allocator>` 为假 | 给不兼容的容器配分配器 |
| ¶6.7 | 有 `KeyContainer` 与 `Compare`，但 `Compare` 不能以 `const Compare&` 比较两个 `const KeyContainer::value_type&` | 把容器/分配器错当比较器 |

"qualifies as an input iterator / an allocator" 的含义由 [[container.reqmts#69]] 给出，而且是**有意留白**的：实现在多大程度上判定"某类型不是输入迭代器 / 不是分配器"是 {{unspec}}，标准只规定了下限——整数类型绝不能算输入迭代器；类型 `A` 至少要满足 `A::value_type` 有效且 `declval<A&>().allocate(size_t{})` 良构，才可能算分配器。这是纯语法级的判定，不检查语义。

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

  // 两个容器 → flat_map 的五个模板参数全部推导出来
  std::deque<std::string> ks{"b", "a"};
  std::deque<double> vs{2.0, 1.0};
  std::flat_map fm(std::move(ks), std::move(vs));
  static_assert(std::is_same_v<decltype(fm),
      std::flat_map<std::string, double, std::less<std::string>,
                    std::deque<std::string>, std::deque<double>>>);
  assert(fm.begin()->first == "a" && fm.begin()->second == 1.0);
}
```

¶6.5 的反面：普通 `std::vector<int>` 配上 `pmr::polymorphic_allocator` 时 `uses_allocator_v` 为假，`stack(Container, Allocator)` 这条推导指引就退出，没有别的候选可用：

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

¶7–¶8 只是声明推导指引里可以使用一些仅供说明的别名模板：*iter-value-type*（[[sequences.general]]）、*iter-key-type*、*iter-mapped-type*、*range-key-type*、*range-mapped-type*（[[associative.general]]）以及 ¶8 新定义的 *alloc-rebind*（`allocator_traits<A>::rebind_alloc<T>` 的简写，flat 系列的 `from_range` 推导指引要用它把一个分配器"拆"给键和值两个容器）。

### ¶5：失效规则委托给底层容器

!!! std
    the `insert`, `emplace`, and `erase` members affect the validity of iterators, references, and pointers to the adaptor's container(s) in the same way that the containers' respective `insert`, `emplace`, and `erase` members do.
    适配器的 `insert`、`emplace`、`erase` 对迭代器、引用、指针有效性的影响，与底层容器相应成员完全相同。

这条主要是为 flat 系列写的（经典适配器根本不暴露迭代器）。条文自带的例子说 `flat_map::insert` **可能使所有迭代器失效**——因为默认底层是 `vector`，重新分配会让一切失效。注意 flat 容器在 [[flat.map#2]] 里明确声明**不满足**关联容器关于失效的要求（`std::map` 插入不使任何迭代器失效），¶5 就是它的替代规则。详见 [[flat.map]]。

经典适配器没有迭代器，但有 `emplace`（它还返回新元素的引用），而 `top()`/`front()`/`back()` 也返回引用，所以 ¶5 对它们同样有分量：`stack<int, vector<int>>` 的 `top()` 引用会在下一次触发重新分配的 `push`/`emplace` 后悬垂；`stack<int>`（默认 `deque`）则不会——[[deque]] 在两端插入只使迭代器失效、不使引用失效。`push`、`pop` 不在 ¶5 的名单里，但它们就是 `c.push_back`、`c.pop_back` 的一行转发，结论相同。

## `protected: Container c;`——标准承诺的扩展点

三个经典适配器的类定义里都写着：

```cpp
protected:
  Container c;          // stack、queue
  Compare comp;         // 仅 priority_queue
```

这**不是** exposition-only 成员（对比 flat 系列里标注 `// exposition only` 的私有成员 *c*、*compare*）。它是规范性接口的一部分：成员名必须叫 `c`/`comp`，访问级别必须是 `protected`。所以派生类可以合法地依赖它——这是标准库里少有的"有意留给继承者"的设计，常见用途是给 `priority_queue` 加 `reserve`，或者在派生类里提供迭代/清空：

```cpp run title="reservable-pq.cpp" ok
#include <queue>
#include <cassert>

template<class T>
struct reservable_pq : std::priority_queue<T> {
  void reserve(std::size_t n) { this->c.reserve(n); }   // c 是标准规定的 protected 成员
  void clear() noexcept { this->c.clear(); }             // 空序列天然是合法的堆
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

!!! pitfall "派生类要自己维护不变式"
    `priority_queue` 的所有公有成员都假设 `c` 是关于 `comp` 的合法堆。派生类直接改写 `c` 的元素之后若不重新 `make_heap`，后续的 `push`/`pop` 就违反了 [[push.heap]]/[[pop.heap]] 的 *Preconditions*，是 {{ub}}。`clear()` 安全是因为空区间平凡地是堆。

## 委托模型：一切行为都来自底层容器

经典适配器的成员几乎都以内联定义的形式写在类定义里：`front()` 就是 `{ return c.front(); }`，`pop()` 就是 `{ c.pop_front(); }`。由此推出几条在条文里**找不到字面表述**、但完全确定的结论：

1. **复杂度**：等于底层操作的复杂度。`stack<T, vector<T>>::push` 是均摊常数，`stack<T, list<T>>::push` 是严格常数。
2. **异常**：`push` 是否提供强保证，取决于 `c.push_back` 是否提供（对 [[vector]] 来说，元素类型移动构造可能抛出且不可拷贝时就不保证）。
3. **前置条件**：`front()`、`back()`、`top()`、`pop()` 在空适配器上调用的后果，就是 `c.front()`、`c.back()`、`c.pop_front()`、`c.pop_back()` 在空容器上调用的后果。C++26 起，[[sequence.reqmts]] 把它们都写成了 *Hardened preconditions*（`front` 见 [[sequence.reqmts#72]]，`back` 见 ¶76，`pop_front` 见 ¶114，`pop_back` 见 ¶118）：加固实现中必须以契约违反终止，非加固实现中仍是 {{ub}}。

`priority_queue::pop()` 是个例外，它不是一句话的转发：

```cpp
pop_heap(c.begin(), c.end(), comp);
c.pop_back();
```

空队列上先执行的是 `pop_heap`，而 [[pop.heap#2]] 要求区间是"合法的**非空**堆"——这只是普通 *Preconditions*，没有被加固。所以严格地说，空 `priority_queue::pop()` 的 UB 发生在任何加固检查之前；实践中 libc++ 的 `pop_heap` 对空区间什么都不做（源码注释如此），随后 `c.pop_back()` 的加固检查才触发。本机实测（Homebrew clang 23.1.3 + libc++，`-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST`）：空 `stack::pop`、`queue::pop`、`priority_queue::pop`、`priority_queue::top` 都以 `SIGTRAP` 终止。

## queue 与 stack（[queue]、[stack]）

### 底层容器要求（[queue.defn] ¶1、[stack.general] ¶1）

两者的要求都是"列举操作"式的：

- `queue`：任何支持 `front()`、`back()`、`push_back()`、`pop_front()` 的**序列容器**，特别是 [[list]] 与 [[deque]]。[[vector]] 没有 `pop_front`，不能用。
- `stack`：任何支持 `back()`、`push_back()`、`pop_back()` 的序列容器，特别是 `vector`、`list`、`deque`。

这些要求不是 *Constraints*，而是对模板实参的要求：不满足时，只有在你**实际调用**到缺失的成员时才会出现编译错误（类模板成员函数按需实例化，[[temp.inst]]）。所以 `std::queue<int, std::vector<int>>` 可以声明、可以 `push`，直到第一次 `pop()` 才报错。

### 接口一览（[queue.defn]、[stack.defn]）

| 成员 | `queue` | `stack` |
|---|---|---|
| 访问 | `front()`→`c.front()`、`back()`→`c.back()` | `top()`→`c.back()` |
| 插入 | `push(x)`→`c.push_back(x)` | 同左 |
| 原位构造 | `emplace(args...)`→`return c.emplace_back(args...)` | 同左 |
| 范围插入 {{c++23}} | `push_range(rg)`（[queue.mod] ¶1） | `push_range(rg)`（[stack.mod] ¶1） |
| 删除 | `pop()`→`c.pop_front()` | `pop()`→`c.pop_back()` |
| 交换 | `swap(q)`，`noexcept(is_nothrow_swappable_v<Container>)` | 同左 |

两个容易被忽略的细节：

- `emplace` 的返回类型是 `decltype(auto)`——自 C++17 起序列容器的 `emplace_back` 返回新元素的引用，适配器原样透传。而 `priority_queue::emplace` 返回 `void`：新元素在 `push_heap` 之后已经不知道跑到哪个位置去了。
- 所有成员（包括构造函数）在当前草案里都是 `constexpr`。

### 构造函数（[queue.cons]、[stack.cons]）

| 段落 | 签名 | 效果 |
|---|---|---|
| ¶1 | `explicit queue(const Container& cont)` | 以 `cont` 初始化 `c` |
| ¶2 | `explicit queue(Container&& cont)` | 以 `std::move(cont)` 初始化 `c` |
| ¶3 | `queue(InputIterator first, InputIterator last)` {{c++23}} | 以 `(first, last)` 初始化 `c` |
| ¶4 | `queue(from_range_t, R&& rg)` {{c++23}} | 以 `ranges::to<Container>(std::forward<R>(rg))` 初始化 `c` |

`stack` 的 [stack.cons] ¶1–¶4 一字不差。注意默认构造函数是 `queue() : queue(Container()) {}`——C++20 之前它是 `explicit queue(const Container& = Container())`，默认构造于是成了 `explicit` 的，导致 `std::queue<int> q = {};` 这类复制列表初始化失败；C++20 时为此拆出了一个非 `explicit` 的默认构造函数。

迭代器对构造函数来自 [[P1425R4]]，`from_range` 构造与 `push_range` 来自 [[P1206R7]]。`push_range` 的效果（[queue.mod] ¶1、[stack.mod] ¶1）是：若 `c.append_range(std::forward<R>(rg))` 是合法表达式就用它，否则退化成 `ranges::copy(rg, back_inserter(c))`——这样用户自定义的、没有 `append_range` 的容器也能用。

### 带分配器的构造函数（[queue.cons.alloc]、[stack.cons.alloc]）

¶1 是整个小节的总开关：

!!! std
    If `uses_allocator_v<container_type, Alloc>` is `false` the constructors in this subclause shall not participate in overload resolution.
    若 `uses_allocator_v<container_type, Alloc>` 为假，本小节的构造函数不参与重载决议。

¶2–¶8 的效果都是"把分配器作为最后一个实参追加给 `c` 的构造"：`queue(a)` 以 `a` 初始化 `c`；`queue(cont, a)` 以 `(cont, a)` 初始化；`queue(q, a)` 以 `(q.c, a)` 初始化；`from_range` 版本则调用 `ranges::to<Container>(std::forward<R>(rg), a)`。

这组构造函数存在的唯一目的，是让适配器能参与 **uses-allocator 构造**（[[allocator.uses]]）：标准为每个适配器特化了 `uses_allocator<queue<T, Container>, Alloc>`，令它继承 `uses_allocator<Container, Alloc>`。于是 `std::pmr::vector<std::stack<int, std::pmr::vector<int>>>` 的外层分配器会自动传进每个内层 `stack` 的底层容器。

### 比较运算（[queue.ops]、[stack.ops]）

¶1–¶6 的六个关系运算符一律 *Returns* `x.c op y.c`；¶7 的 `operator<=>` 要求 `three_way_comparable<Container>`，返回 `x.c <=> y.c`。即：两个栈相等当且仅当底层序列逐元素相等——比较的是"整个历史留下的状态"，而不只是栈顶。

`==` 与 `<=>` 并存，且 `!=`、`<` 等仍被单独声明，这是 C++20 引入 `<=>` 时为保持与旧行为一致（例如 `Container` 自己只有 `<` 没有 `<=>`）而保留的。

## pop() 为什么返回 void

`stack::pop()`、`queue::pop()`、`priority_queue::pop()` 全部返回 `void`。想"取出并删除"必须写两句：

```cpp
auto x = s.top();   // 1. 拷贝出来
s.pop();            // 2. 再删除
```

```cpp run title="pop-returns-void.cpp" error
#include <stack>

int main() {
  std::stack<int> s;
  s.push(1);
  int x = s.pop();   // error: pop() 返回 void
}
```

这是 STL 有意为之的**异常安全**设计，问题最早由 Tom Cargill 1994 年在 *C++ Report* 上的文章"Exception Handling: A False Sense of Security"中提出，后来在 Herb Sutter 的 *Exceptional C++* 里被系统讨论。设想 `T pop()`：

```cpp
T pop() {
  T tmp = std::move(c.back());   // (a)
  c.pop_back();                  // (b) 元素已从容器中移除
  return tmp;                    // (c) 返回值的拷贝/移动构造——可能抛出
}
```

在没有保证复制消除的年代，第 (c) 步要把 `tmp` 拷贝到调用者的对象里；若这一步抛出异常，元素已经从栈里删掉了，却没有交到调用者手里——**数据永久丢失**，强异常保证无从谈起。把"观察"（`top`）和"修改"（`pop`）拆成两个操作后：`top()` 返回引用不会抛，拷贝在调用者那里发生，若它抛出，栈完好无损；`pop()` 只做销毁，可以做到不抛。

!!! history "C++17 之后这个理由还成立吗？"
    C++17 的保证复制消除让 `return tmp;` 这种具名返回值仍然**不在**保证之列（NRVO 依旧可选），只有 prvalue 才有保证。更关键的是，`auto x = s.pop();` 之外还有 `x = s.pop();` 这种**赋值**场景，赋值运算符照样可能抛出。所以 `void pop()` 的设计理由至今有效。现代库（例如并发队列）常提供 `bool try_pop(T& out)` 或 `optional<T>` 返回的变体，代价是要求 `T` 的移动不抛或者接受较弱的保证。

!!! lawyer "从 priority_queue::top() 里“偷走”元素"
    `priority_queue::top()` 只有 `const` 版本，返回 `const_reference`——因为修改堆顶可能破坏堆性质。常见的"性能技巧"是 `T x = std::move(const_cast<T&>(pq.top())); pq.pop();`。底层元素本身不是 const 对象，所以 `const_cast` 后修改它不违反 [[dcl.type.cv]]；但随后的 `pop()` 调用 `pop_heap`，其 *Preconditions*（[[pop.heap#2]]）要求整个区间是合法堆——被移走的堆顶（例如变成空字符串）可能已经小于它的子节点，严格按条文这是 {{ub}}。主流实现的 `pop_heap` 采用 Floyd 式下沉，不会再比较原堆顶，因此"碰巧能用"；但这是依赖实现细节，而非标准保证。

## priority_queue（[priority.queue]）

### 概述：堆 + 严格弱序（[priqueue.overview] ¶1）

!!! std
    Any sequence container with random access iterator and supporting operations `front()`, `push_back()` and `pop_back()` can be used to instantiate `priority_queue`.
    任何具有随机访问迭代器、支持 `front()`、`push_back()`、`pop_back()` 的序列容器都可用于实例化 `priority_queue`。

特别点名 `vector`（默认）与 `deque`。同段的后半句是本节最重要的法律前提：

> the library assumes that the function or function object defines a strict weak ordering.

"库**假设**比较器是严格弱序"（[[g:strict-weak-ordering]]，[[alg.sorting]] ¶3–¶4）——假设不成立时，后续所有 `make_heap`/`push_heap`/`pop_heap` 的前置条件都失去意义。构造函数的 *Preconditions* 也再次写明这一点（[priqueue.cons] ¶1、¶3、¶5、¶7："`x` defines a strict weak ordering"）。

`priority_queue` 的全部状态就是 `c`（一个关于 `comp` 的**最大堆**，[[alg.heap.operations]] ¶1）和 `comp`。`top()` 返回 `c.front()`——堆顶就是区间第一个元素，即"按 `comp` 最大"的元素。所以 `priority_queue<int, vector<int>, greater<int>>` 是最小堆：`comp` 反过来了，"最大"也就反过来了。

### 违反严格弱序：一个真实的 NaN 事故

`double` 的 `operator<` 遇到 NaN 时不是严格弱序：`NaN < x` 与 `x < NaN` 都为假，于是 NaN 与所有数"等价"，而等价关系不再传递（`1 ~ NaN ~ 5` 但 `1 < 5`）。

```cpp run title="pq-nan.cpp" ub
#include <queue>
#include <limits>
#include <cstdio>

int main() {
  constexpr double nan = std::numeric_limits<double>::quiet_NaN();
  std::priority_queue<double> pq;
  for (double d : {1.0, 2.0, nan, 3.0, 4.0, 5.0}) pq.push(d);  // UB：NaN 破坏严格弱序
  while (!pq.empty()) { std::printf("%g ", pq.top()); pq.pop(); }
  std::printf("\n");
}
```

本机 libc++ 输出 `4 5 3 2 1 nan`——4 排在了 5 前面，"优先队列"不再按优先级出队。换一个插入顺序，结果又会不同。即便打开 `_LIBCPP_HARDENING_MODE_DEBUG`，这个例子也没有被检出：库无法在 O(log N) 的 `push` 里验证全局的序关系。修复方法是让比较器显式处理 NaN（例如把 NaN 视为最小），或者在入队前过滤。

### 构造函数（[priqueue.cons]）

所有构造函数的效果都以 `make_heap(c.begin(), c.end(), comp)` 收尾，把任意序列整理成堆（[[make.heap]]：至多 3N 次比较，线性时间）：

| 段落 | 签名 | 效果 |
|---|---|---|
| ¶1–¶2 | `priority_queue(const Compare& x, const Container& y)` / `Container&&` | 以 `x` 初始化 `comp`、以 `y` 拷贝或移动构造 `c`，再 `make_heap` |
| ¶3–¶4 | `priority_queue(first, last, const Compare& x = Compare())` | 以 `(first, last)` 初始化 `c`、以 `x` 初始化 `comp`，再 `make_heap` |
| ¶5–¶6 | `priority_queue(first, last, x, const Container& y)` / `Container&&` | 先用 `y` 初始化 `c`，再 `c.insert(c.end(), first, last)`，最后 `make_heap` |
| ¶7–¶8 | `priority_queue(from_range_t, R&& rg, const Compare& x = Compare())` {{c++23}} | `c` 取 `ranges::to<Container>(std::forward<R>(rg))`，再 `make_heap` |

每一对的奇数段都是同一句 *Preconditions*：`x` 定义了严格弱序。

把一批数据一次性交给构造函数（O(N)）比逐个 `push`（O(N log N)）在渐近意义上更快——这是"先收集、后建堆"这一常见优化的标准依据。

### 带分配器的构造函数（[priqueue.cons.alloc]）

¶1 与 queue/stack 相同：`uses_allocator_v<container_type, Alloc>` 为假则全部退出重载决议。¶2–¶13 共 12 个构造函数，模式统一：分配器追加给 `c` 的构造；未给比较器的版本**值初始化** `comp`（¶2、¶8、¶13）；凡是接收了元素的版本都以 `make_heap` 收尾（¶4、¶5、¶8–¶13），只拷贝/移动另一个 `priority_queue` 的 ¶6–¶7 不需要（源对象已经是堆）。

### 成员（[priqueue.members]）

| 段落 | 成员 | 效果（"as if by"） |
|---|---|---|
| ¶1 | `push(const value_type& x)` | `c.push_back(x); push_heap(c.begin(), c.end(), comp);` |
| ¶2 | `push(value_type&& x)` | `c.push_back(std::move(x)); push_heap(...)` |
| ¶3–¶4 | `push_range(R&& rg)` {{c++23}} | 先 `append_range`（不可用则 `ranges::copy` 到 `back_inserter`），**再对整个区间 `make_heap`**；*Postconditions*：`is_heap(c.begin(), c.end(), comp)` |
| ¶5 | `emplace(args...)` | `c.emplace_back(...); push_heap(...)`，返回 `void` |
| ¶6 | `pop()` | `pop_heap(c.begin(), c.end(), comp); c.pop_back();` |

`push_range` 的写法值得玩味：它没有规定"逐个 `push_heap`"（M log(N+M)），而是"全部追加后重新 `make_heap`"（O(N+M)）。当 M 远小于 N 时后者反而更慢；条文用的是 "restores the heap property **as if by** `make_heap`"，¶4 的后置条件只要求结果是堆，所以实现可以根据 M 与 N 的大小择优——标准只锁定可观察结果，不锁定算法。

"no equality is provided"：类定义末尾的这句注释说明 `priority_queue` 没有 `==`/`<=>`。原因很直接——两个包含相同元素的堆，内部排列可以不同，逐元素比较 `c` 没有意义，而按多重集合比较又需要 O(N log N)。

```cpp run title="pq-no-equality.cpp" error
#include <queue>

int main() {
  std::priority_queue<int> a, b;
  return a == b;   // error: priority_queue 没有 operator==
}
```

### 特化算法（[priqueue.special]）

¶1 *Constraints*：`is_swappable_v<Container>` 与 `is_swappable_v<Compare>` 都为真；¶2 效果等同 `x.swap(y)`。成员 `swap` 依次交换 `c` 和 `comp`，`noexcept` 条件是两者都不抛地可交换。

## C++23 的范围支持：一个综合例子

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

  std::stack s(v.begin(), v.end());                       // 迭代器对 + 推导指引
  static_assert(std::is_same_v<decltype(s), std::stack<int>>);   // 底层默认 deque<int>

  std::queue q(std::from_range, v | std::views::take(3)); // from_range 构造
  q.push_range(std::vector{9, 2, 6});
  assert(q.size() == 6 && q.front() == 3 && q.back() == 6);

  std::priority_queue pq(std::from_range, v);
  pq.push_range(std::list{9, 2});                          // 任何元素可转换的输入范围
  assert(pq.top() == 9);

  std::stack<int, std::vector<int>> sv;
  int& top = sv.emplace(42);                               // emplace 透传 emplace_back 的返回值
  assert(&top == &sv.top());

  // 适配器本身不是范围：没有 begin()/end()
  static_assert(!std::ranges::range<std::stack<int>>);
  static_assert(!std::ranges::range<std::priority_queue<int>>);
}
```

最后两行点出了经典适配器的本质：**没有迭代器**。这不是遗漏，而是抽象本身——栈的契约是"只能看到顶部"，一旦提供遍历，就等于承认它只是一个 `deque`。确实需要遍历时，正确的做法是直接使用底层容器，或者如前文所示通过派生类访问 `c`。

## 格式化（[container.adaptors.format]）

¶1：对 `queue`、`priority_queue`、`stack`，标准库提供 `formatter<adaptor-type<T, Container, U...>, charT>` 特化（要求 `formattable<Container, charT>`），其中只有一个仅供说明的成员 *underlying_*，类型是 `formatter<ranges::ref_view<maybe-const-container>, charT>`。¶2：`parse` 转发给 *underlying_*；¶3：

!!! std
    *Effects*: Equivalent to: `return underlying_.format(r.c, ctx);`
    效果：等价于把底层容器 `r.c` 交给范围格式化器输出。

也就是说，打印出来的是**底层容器的存储顺序**，而不是"出栈顺序"或"优先级顺序"：

```cpp run title="adaptor-format.cpp" ok
#include <queue>
#include <stack>
#include <print>

int main() {
  std::stack<int> s;
  for (int i : {3, 1, 4}) s.push(i);
  std::priority_queue<int> pq;
  for (int i : {3, 1, 4, 1, 5}) pq.push(i);

  std::println("{}", s);    // [3, 1, 4]        —— 栈底在左，栈顶在右
  std::println("{}", pq);   // 底层堆数组的排列，例如 [5, 4, 3, 1, 1]
}
```

范围格式说明符照常可用（如 `"{::02}"` 作用于每个元素）。这个 formatter 是 C++23 的范围格式化提案 [[P2286R8]] 一并加入的；`formatter` 能访问 `protected` 的 `c`，是因为条文以"等价于"的方式规定了效果，实现可以用友元或其他手段做到。

三个头文件的概要里还都写了：

```cpp
template<class T, class Container>
  constexpr bool enable_nonlocking_formatter_optimization<queue<T, Container>> = false;
```

`std::print` 默认会在格式化期间锁住输出流；`enable_nonlocking_formatter_optimization` 为真的类型允许实现先格式化到缓冲区再一次性写出（[[format.formatter.spec]]）。适配器的格式化会调用任意用户类型（`Container`、元素类型）的 formatter，库无法确定这些代码与流锁的交互是否安全，因此保守地设为 `false`。

## 编译器与库实现现状

以本机 Homebrew clang 23.1.3 + libc++ 实测：

- `priority_queue` 已完整 `constexpr`（可在 `static_assert` 中建堆、出队）。
- `queue` 与 `stack` 的成员**尚未**标 `constexpr`：在常量表达式中构造 `std::queue<int>` 报 "non-constexpr constructor 'queue' cannot be used in a constant expression"。值得注意的是，libc++ 的 `<queue>` 已经把 `__cpp_lib_constexpr_queue` 定义为 `202502L`，而 `__cpp_lib_constexpr_stack` 与 `__cpp_lib_constexpr_deque` 尚未定义——前者与 `std::queue` 的实际状态并不一致，依赖特性测试宏写 `constexpr` 代码时要小心。
- C++23 的迭代器对构造（`__cpp_lib_adaptor_iterator_pair_constructor`）、`from_range`/`push_range`（`__cpp_lib_containers_ranges`）、格式化（`__cpp_lib_format_ranges`）均可用。
- 加固：libc++ 不在适配器层面做额外检查，空适配器上的 `top`/`front`/`pop` 依靠底层容器的 `_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS` 等断言，在 `_LIBCPP_HARDENING_MODE_FAST` 及以上即被捕获。

## 历史演进

| 版本 | 变化 |
|---|---|
| C++98 | `stack`、`queue`、`priority_queue`，`protected` 成员 `c`/`comp`，`pop()` 返回 `void` |
| C++11 | 移动构造、`emplace`、带分配器的构造函数与 `uses_allocator` 特化、成员 `swap` |
| C++17 | 推导指引；`emplace` 改为返回 `decltype(auto)`（随序列容器 `emplace_back` 返回引用） |
| C++20 | `operator<=>`；默认构造函数拆为非 `explicit` |
| C++23 | 迭代器对构造（[[P1425R4]]）、`from_range` 构造与 `push_range`（[[P1206R7]]）、格式化（[[P2286R8]]）、`flat_map`/`flat_set` 家族（[[P0429R9]]、[[P1222R4]]） |
| C++26 | 全部适配器 `constexpr` 化；底层序列容器的 `front`/`back`/`pop_*` 成为加固前置条件，经委托惠及适配器 |

## 思考题

1. `std::queue<int, std::vector<int>> q; q.push(1);` 能编译吗？加一句 `q.pop();` 呢？为什么标准不用 *Constraints* 在声明处就拒绝它？

<details markdown="1">
<summary>展开查看答案与解析</summary>

前两句能编译：类模板的成员函数只有被使用时才隐式实例化（[[temp.inst]]），`push` 只需要 `push_back`。加上 `q.pop()` 后实例化 `queue::pop()`，其函数体 `c.pop_front()` 在 `vector` 上不存在，于是报错。

[queue.defn] ¶1 只是说"支持这些操作的序列容器**可以**用来实例化"，这是对模板实参的说明，而非 *Constraints*（*Constraints* 只能附着在函数/函数模板上，决定其是否参与重载决议，[[structure.specifications]]）。为整个类模板加概念约束会让"只用 `push` 和 `back` 的 queue"这种部分合法的用法失效，也会破坏 C++98 以来的兼容性。
</details>

2. 为什么 `priority_queue` 的 `push_range` 规定了 *Postconditions* `is_heap(...)`，而 `push` 没有？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`push` 的效果是 "as if by" 一段确定的代码（`push_back` + `push_heap`），而 [[push.heap]] 本身就保证结果是堆，不需要再写一次。`push_range` 的效果用的是"restores the heap property as if by `make_heap`"——¶4 明确写出后置条件，是在告诉实现者：真正受约束的是"结果是堆"这一可观察性质，具体用 `make_heap` 整体重建还是逐个 `push_heap`，可以按 M 与 N 的比例自由选择。对用户而言区别在于：相等元素在堆中的排列、以及之后 `pop` 出等价元素的次序，不能依赖任何特定算法。
</details>

3. 两个 `std::stack<int>`，一个依次压入 1、2、3，另一个压入 1、2、3、4 后再 `pop()`。它们 `==` 吗？换成 `std::priority_queue<int>` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

两个 `stack` 的底层 `deque` 都是 `[1, 2, 3]`，[stack.ops] ¶1 规定 `==` 就是 `x.c == y.c`，所以相等——比较只看当前存储的序列，与历史操作无关。

`priority_queue` 根本没有 `==`（类定义末尾"no equality is provided"），这样写是编译错误。即便你通过派生类比较 `c`，两个包含相同多重集合的堆也可能有不同的数组排列，逐元素比较会给出"不相等"——这正是标准不提供它的原因。
</details>

## 小结

- 适配器 = 一个底层容器 + 一个收窄的接口。复杂度、异常保证、失效规则、前置条件（包括 C++26 的加固前置条件）全部**委托**给底层容器，[container.adaptors.general] ¶5 把这一点对失效规则写成了明文。
- `protected: Container c;` 是规范性接口，派生类可依赖；flat 系列的 *c* 则是 exposition-only 的私有成员，不可依赖。
- `pop()` 返回 `void` 是为了强异常保证：观察（`top`/`front`）与删除（`pop`）分离。
- `priority_queue` 是以 `comp` 为序的最大堆；比较器必须是严格弱序（[priqueue.overview] ¶1 与各构造函数的 *Preconditions*），否则出队顺序不可预期，且通常检测不到。
- 经典适配器没有迭代器、不是范围；格式化输出的是底层容器的存储顺序；`priority_queue` 没有相等比较。
- 推导指引通过 ¶6 的八条过滤规则区分"容器 / 比较器 / 分配器 / 迭代器"，`uses_allocator` 特化让适配器参与 uses-allocator 构造。
