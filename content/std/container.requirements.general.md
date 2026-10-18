---
title: 通用容器要求：容器、可逆容器、可选操作与分配器感知容器
summary: 逐条拆解 [container.requirements.general] 的四组具名要求——X u(rv) 为何常数、== 的复杂度、swap 何时是 UB、分配器在拷贝/移动/赋值/交换时如何传播、Cpp17*Insertable 家族的精确定义、什么算"连续容器"，以及"整数不算输入迭代器"这条重载规则
status: done
covers: *
related: container.requirements, sequence.reqmts, allocator.traits, allocator.requirements, mem, res.on.data.races, swappable.requirements, alg.three.way
tags: 标准库, 容器, 分配器, 具名要求, POCMA, 异常安全
updated: 2026-10-18
---

这一节定义了四组**具名要求**（named requirements），其他所有容器条款都靠"满足……要求"来引用它们：

| 子条款 | 要求名 | 谁满足 |
|---|---|---|
| [container.reqmts] | *container* | 本章全部容器（`forward_list`、`hive`、无序容器有局部例外） |
| [container.rev.reqmts] | *reversible container* | 迭代器为双向或随机访问的容器 |
| [container.opt.reqmts] | 可选操作 `<=>` | 序列容器与有序关联容器 |
| [container.alloc.reqmts] | *allocator-aware container* | 除 `array`、`inplace_vector` 外的全部容器，外加 `basic_string`、`basic_stacktrace`、`match_results` |

读这一节需要先熟悉**分配器**协议（[[allocator.requirements]]）与 `allocator_traits`（[[allocator.traits]]）——本站在 [[mem]] 里讲过分配器只负责"拿存储"、元素的生命周期要靠 `construct` 一个个建起来。本节则规定**容器如何使用分配器**。

## 记号与 container-compatible-range（[container.intro.reqmts]）

¶1 固定了全节的记号：`X` 是容器类、`T` 是元素类型；`a` 是 `X` 的值，`b`、`c` 可能是 `const X`；`i`、`j` 是（可能 const 的）`X::iterator`；`v` 是 `X` 的左值或 `const X` 的右值（也就是"会被拷贝的东西"）；`s`、`t` 是非 const 左值；`rv` 是非 const 右值（"会被移动的东西"）。读后面的表时，**记号本身就编码了值类别**：`X u(v)` 是拷贝、`X u(rv)` 是移动。

¶2 定义了仅用于阐述的 concept `container-compatible-range<R, T>`：`R` 是 `input_range`，且其引用类型可转换为 `T`。所有 C++23 引入的 `from_range_t` 构造函数、`insert_range`、`append_range` 等都用它约束——这是本章少有的**真正的** concept 约束，不满足时重载直接不可行（[[over.match]]）。

## 容器要求（[container.reqmts]）

¶1：类型 `X` 满足*容器*要求，当且仅当下列类型、语句和表达式良构且具有指定语义。

### 成员类型（¶2–¶9）

| 表达式 | 结果 | 要点 |
|---|---|---|
| `X::value_type` | `T` | ¶3 前置条件：`T` 是从 `X` *Cpp17Erasable* 的——没有这个，容器连析构都做不到 |
| `X::reference` / `const_reference` | `T&` / `const T&` | `vector<bool>` 不满足，见 [[vector.bool]] |
| `X::iterator` | 值类型为 `T` 的前向迭代器，可转换为 `const_iterator` | ¶6 |
| `X::const_iterator` | 常量前向迭代器 | ¶7 |
| `X::difference_type` | 有符号整数，**等于**两种迭代器的差类型 | ¶8 |
| `X::size_type` | 无符号整数，能表示 `difference_type` 的任何非负值 | ¶9 |

### 构造、赋值、析构（¶10–¶26）

- `X u;` / `X u = X();`：后置条件 `u.empty()`，常数（¶10–¶11）。
- `X u(v);`：前置条件 `T` 是 *Cpp17CopyInsertable*，后置 `u == v`，线性（¶12–¶14）。
- `X u(rv);`：后置条件"`u` 等于 `rv` 在构造前的值"，复杂度**对 `array` 和 `inplace_vector` 为线性，对其他所有标准容器为常数**（¶16）。常数复杂度意味着实现**只能**窃取 `rv` 的内部缓冲区——这条复杂度要求把"移动 = 指针交接"写进了标准。
- `t = rv`：¶21 "现有元素要么被移动赋值、要么被销毁"，¶22 后置条件只在 `t` 与 `rv` **不是同一对象**时成立——`v = std::move(v)` 不要求保持原值；库的一般规则 [[lib.types.movedfrom#2]] 规定标准库类型的自移动赋值使对象处于"有效但未指明"的状态。
- `a.~X()`：销毁每个元素并释放所获得的全部内存，线性（¶25–¶26）。

### 迭代器与比较（¶27–¶47，¶63）

- `begin()`/`end()` 对 `const X` 返回 `const_iterator`；`cbegin()` 被定义为 `const_cast<X const&>(b).begin()`（¶34），全部常数。
- `i <=> j`：*Constraints* 为 `X::iterator` 满足随机访问迭代器要求，结果 `strong_ordering`（¶39–¶41）。
- ¶63：在 `i == j`、`i < j`、`i - j`、`i <=> j` 等表达式中，任一侧都可以换成指向**同一元素**的 `const_iterator`，语义不变。

!!! std
    c == b — *Preconditions*: T meets the Cpp17EqualityComparable requirements. ... *Complexity*: Constant if c.size() != b.size(), linear otherwise.

    `==` 要求元素满足 *Cpp17EqualityComparable*；大小不同时必须常数时间返回。

¶44 规定 `==` 返回 `equal(c.begin(), c.end(), b.begin(), b.end())`，¶46 附带一句 *Remarks*："`==` 是等价关系"。这是对**元素类型**的隐含要求：*Cpp17EqualityComparable*（[[utility.arg.requirements]]）要求 `==` 自反、对称、传递。按字面读，含 NaN 的 `double` 值并不满足自反性，于是 ¶42 的前置条件在这些取值上不成立，标准也没有为浮点数开特例。实践中所有实现都只是逐元素调用 `==`，"含 NaN 的 `vector<double>` 不等于它自己"是可预期的结果——但写泛型代码时，不要假定容器的 `==` 对任意元素类型都是等价关系。

`c != b` 等价于 `!(c == b)`（¶47），C++20 起由重写候选自动提供。

### `swap`、`size`、`max_size`、`empty`（¶48–¶62）

- `t.swap(s)` 与 `swap(t, s)`：对 `array`、`inplace_vector` 线性，其他常数（¶50）。
- `c.size()` 返回 `distance(c.begin(), c.end())`，**常数**（¶53–¶54）；`forward_list` 是唯一不提供它的容器。
- `c.empty()` 等价于 `c.begin() == c.end()`，常数（¶60–¶61）。

### 分配器从哪里来、到哪里去（¶64）

¶64 是本节最长、工程上最要紧的一段。逐句翻译成规则：

1. 除非另有规定，本章容器**都通过分配器获取内存**。注 2 补充：容器和迭代器只能通过分配器的指针类型（`allocator_traits<A>::pointer` 或其 rebind）引用分配到的元素——这是"花式指针"（fancy pointer，如共享内存里的偏移指针）能用于标准容器的法律基础。
2. **拷贝构造**：分配器取自 `allocator_traits<A>::select_on_container_copy_construction(源容器的分配器)`。
3. **移动构造**：分配器从源容器的分配器**移动构造**而来，且这次移动**不得**以异常退出。
4. **其他构造函数**：接受 `const allocator_type&` 实参。注 3：若使用了可选分配器实参的默认值，分配器类型必须支持值初始化。
5. 这个分配器的副本用于容器整个生命周期内的所有分配和元素构造，**直到被替换**；而替换**只能**经由赋值或 `swap` 发生，且仅当对应的 `propagate_on_container_copy_assignment`（POCCA）、`propagate_on_container_move_assignment`（POCMA）、`propagate_on_container_swap`（POCS）为 `true` 时。
6. `get_allocator()` 返回构造时的分配器的副本，或最近一次替换后的副本。

`std::pmr::polymorphic_allocator` 是检验这些规则的最好样本：它的三个 propagate 特征都是 `false`，`select_on_container_copy_construction` 返回**默认构造**的分配器（即默认内存资源）。

```cpp title="pmr-propagation.cpp" run ok
#include <memory_resource>
#include <vector>
#include <cassert>

int main() {
  std::pmr::monotonic_buffer_resource arena;
  std::pmr::vector<int> a({1, 2, 3}, &arena);

  std::pmr::vector<int> b = a;                 // 拷贝构造：select_on_container_copy_construction
  assert(b.get_allocator().resource() == std::pmr::get_default_resource());

  std::pmr::vector<int> c(a, &arena);          // 想留在 arena 里，必须显式传入
  assert(c.get_allocator().resource() == &arena);

  std::pmr::vector<int> d = std::move(a);      // 移动构造：分配器随之移动
  assert(d.get_allocator().resource() == &arena);
}
```

!!! pitfall "pmr 容器的拷贝会"逃离"你的内存池"
    `std::pmr::vector<T> copy = pooled;` 得到的副本使用**默认**内存资源，而不是 `pooled` 的资源。这是有意设计（防止生命周期更长的副本悬挂在一个短命的 arena 上），但常常让人以为"整个子系统都在 arena 里分配"而实际上没有。

### `swap` 的精确语义（¶65）

!!! std
    Otherwise, the allocators shall not be swapped, and the behavior is undefined unless a.get_allocator() == b.get_allocator().

    若 POCS 为 false，则不交换分配器；此时除非两个分配器相等，否则行为未定义。

¶65 的其余规则：

- 除 `array`、`inplace_vector` 外，`a.swap(b)` 交换两个容器的值**而不对任何元素调用移动、拷贝或 swap**；
- `Compare`、`Pred`、`Hash` 必须 *Cpp17Swappable*，并通过 [[swappable.requirements]] 描述的方式（即 ADL `swap`）交换；
- 每个在交换前指向一个容器中元素的迭代器，交换后指向**另一个容器中的同一元素**；`a.end()` 交换后是否等于 `b.end()` 未指明。

```cpp title="swap-unequal-alloc.cpp" run ub
#include <memory_resource>
#include <vector>

int main() {
  std::pmr::monotonic_buffer_resource r1, r2;
  std::pmr::vector<int> a({1, 2, 3}, &r1);
  std::pmr::vector<int> b({4, 5}, &r2);
  a.swap(b);   // UB: POCS 为 false 且 a.get_allocator() != b.get_allocator()
}
```

用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` 编译，libc++ 会以 `vector::swap: Either propagate_on_container_swap must be true or the allocators must compare equal` 终止程序。没有开启加固时它会"成功"交换缓冲区——随后 `a` 用 `r1` 的分配器去释放 `r2` 分配的内存。

### 缺省异常保证与"不说就不失效"（¶66–¶67）

¶66 列出六条缺省保证（单元素插入强保证、`push_*`/`emplace_*` 强保证、`erase`/`clear`/`pop_*` 不抛、返回的迭代器复制不抛、`swap` 不抛、`swap` 不使元素迭代器失效），并点名由 [[associative.reqmts]]、[[unord.req]]、[[deque]]、[[inplace.vector]]、[[vector]] 各自的条款覆盖。¶67 是失效规则的总开关：**除非另有规定**，调用容器成员函数或把容器传给库函数，不得使迭代器失效或改变元素的值。

这两段与各容器的细则合并后的完整表格，见 [[container.requirements]] 的"总表二""总表三"。

### 连续容器（¶68）

!!! std
    A *contiguous container* is a container whose member types iterator and const_iterator meet the Cpp17RandomAccessIterator requirements and model contiguous_iterator.

    连续容器：其 `iterator`、`const_iterator` 满足 *Cpp17RandomAccessIterator* 要求并且建模 `contiguous_iterator` 的容器。

注意定义是**按迭代器**而不是按"内存长什么样"给出的。标准中的连续容器有 `array`、`vector`（`T ≠ bool`）、`inplace_vector`，以及（在第 27 章）`basic_string`。它们正是能无损转换成 [[views.contiguous|span]] 的容器。

```cpp title="contiguous.cpp" run ok
#include <vector>
#include <deque>
#include <list>
#include <iterator>

static_assert( std::contiguous_iterator<std::vector<int>::iterator>);
static_assert(!std::contiguous_iterator<std::vector<bool>::iterator>);
static_assert(!std::contiguous_iterator<std::deque<int>::iterator>);
static_assert( std::random_access_iterator<std::deque<int>::iterator>);
static_assert( std::bidirectional_iterator<std::list<int>::iterator>);

int main() {
  std::vector<int> v(5, 3);     // 两个 int：选中 (size_type n, const T& value)，不是迭代器区间
  return v.size() == 5 ? 0 : 1;
}
```

### "什么不算迭代器、什么不算分配器"（¶69）

¶69 规定：容器的某些成员函数和推导指引的行为，取决于类型是否"有资格作为输入迭代器 / 分配器"。实现在多大程度上判断"某类型不能是输入迭代器"是**未指明**的，但**至少整数类型不得**被当作输入迭代器；同样，至少要满足两条才可能被当作分配器：`A::value_type` 有效且是类型，以及 `declval<A&>().allocate(size_t{})` 作为不求值操作数良构。

这条规则配合 [[sequence.reqmts]] ¶69 解决了 C++98 以来的经典歧义：`vector<int> v(5, 3)` 的两个实参类型相同，模板构造函数 `vector(InputIterator, InputIterator)` 推导出 `InputIterator = int` 会比 `vector(size_type, const T&)` 更匹配——C++98 用"如果 `InputIterator` 是整数类型则表现得像调用 `(n, value)` 版本"打补丁，C++11 起改为"不具备资格时不参与重载决议"。

## 可逆容器（[container.rev.reqmts]）

¶1：满足容器要求、迭代器为双向或随机访问类别、并提供：

- `reverse_iterator` = `std::reverse_iterator<iterator>`，`const_reverse_iterator` 同理（¶2–¶3）；
- `rbegin()` 返回 `reverse_iterator(end())`，`rend()` 返回 `reverse_iterator(begin())`，`crbegin()`/`crend()` 用 `const_cast` 定义，全部常数（¶4–¶15）。

`forward_list` 与无序容器不是可逆容器；`hive` 是（其迭代器双向）。

## 可选容器操作：`<=>`（[container.opt.reqmts]）

¶1：下列操作只有部分容器提供；若传给 `lexicographical_compare_three_way` 的迭代器满足 constexpr 迭代器要求，则这些操作是 constexpr 函数。

- `a <=> b` 的结果类型是 `synth-three-way-result<value_type>`（¶2），返回 `lexicographical_compare_three_way(…, synth-three-way)`（¶4，[[alg.three.way]]），线性（¶5）。
- ¶3 前置条件：要么 `T` 建模 `three_way_comparable`，要么 `<` 对（可能 const 的）`T` 有定义且是**全序**关系。

于是：`vector<double>` 的 `<=>` 结果是 `partial_ordering`（`double` 建模 `three_way_comparable`，NaN 产生 `unordered`），这是**有定义**的；而一个只提供"非全序 `operator<`"的类型放进容器再比较，则违反前置条件。

```cpp title="partial-ordering.cpp" run ok
#include <vector>
#include <compare>
#include <cassert>
#include <cmath>

int main() {
  std::vector<double> a{1.0, NAN}, b{1.0, 2.0};
  auto r = a <=> b;                         // synth-three-way-result<double> 即 partial_ordering
  static_assert(std::is_same_v<decltype(r), std::partial_ordering>);
  assert(r == std::partial_ordering::unordered);
  assert(!(a < b) && !(b < a) && a != b);   // 不可比较
}
```

无序容器与 `hive` **不**提供 `<=>`；`hive` 甚至连 `==`/`!=` 都不提供（[[hive]]）。

## 分配器感知容器（[container.alloc.reqmts]）

¶1：除 `array` 和 `inplace_vector` 外，本章全部容器，以及 [stacktrace.basic]、[[basic.string]]、[re.results] 中的容器，满足*分配器感知容器*的附加要求。

### Cpp17*Insertable 家族（¶2）

这些术语遍布整个第 23 章的 *Preconditions*。设 `A` 为分配器类型，`X` 的 `allocator_type` 是 `allocator_traits<A>::rebind_alloc<T>`，`m` 是 `A` 的左值，`p` 是 `T*`：

| 术语 | 定义：下列表达式良构，且…… |
|---|---|
| `T` 可 *Cpp17DefaultInsertable* 到 `X` | `allocator_traits<A>::construct(m, p)` |
| 元素被 *default-inserted* | 用上式初始化（**不是**值初始化的同义词：对 `std::allocator`，`construct(m, p)` 等于 `::new(p) T()`，是值初始化；但自定义分配器可以改成默认初始化以避免清零） |
| *Cpp17MoveInsertable* | `construct(m, p, rv)`，且之后 `*p` 等价于 `rv` 原来的值；注 1：`rv` 仍是有效对象，状态未指明 |
| *Cpp17CopyInsertable* | 先是 *Cpp17MoveInsertable*，再加 `construct(m, p, v)`，且 `v` 不变、等价于 `*p` |
| *Cpp17EmplaceConstructible* 自 `args` | `construct(m, p, args)` |
| *Cpp17Erasable* 自 `X` | `allocator_traits<A>::destroy(m, p)` |

两个要点：

- 这些术语都是**"经由分配器"**定义的，因此和 `is_copy_constructible` 等类型特征**不是一回事**：一个 `T` 本身不可拷贝构造，但若分配器的 `construct` 能从 `const T&` 造出 `T`，它依然是 *Cpp17CopyInsertable* 的。反之亦然。
- 若 `X` 不是分配器感知的（`array`、`inplace_vector`）或是 `basic_string` 的特化，这些术语就**当作 `A` 是 `allocator<T>`** 来定义——不需要创建任何分配器对象，也不会实例化用户对 `allocator<T>` 的特化。

注 2 说明：容器以 `m == get_allocator()` 调用 `construct(m, p, args)`；默认的 `std::allocator` 会调用 `::new((void*)p) T(args)`（C++20 起实际经由 `construct_at`），但专门的分配器可以选择别的定义——`scoped_allocator_adaptor` 正是借此把自己"注入"到嵌套容器里（[[allocator.uses]]）。

### 分配器感知容器的附加表达式（¶3–¶32）

| 表达式 | 前置条件 | 后置 / 效果 | 复杂度 |
|---|---|---|---|
| `X::allocator_type` | *Mandates*：`allocator_type::value_type` 与 `X::value_type` 相同（¶5） | — | — |
| `c.get_allocator()` | — | — | 常数 |
| `X u;` | `A` *Cpp17DefaultConstructible* | `u.empty()`，`u.get_allocator() == A()` | 常数 |
| `X u(m);` | — | `u.empty()`，`u.get_allocator() == m` | 常数 |
| `X u(t, m);` | *Cpp17CopyInsertable* | `u == t`，`u.get_allocator() == m` | 线性 |
| `X u(rv);` | — | 元素与分配器都来自 `rv` | **常数** |
| `X u(rv, m);` | *Cpp17MoveInsertable* | `u` 拥有 `rv` 原来的元素**或其副本**；`u.get_allocator() == m` | `m == rv.get_allocator()` 时常数，否则线性 |
| `a = t` | *Cpp17CopyInsertable* 且 *Cpp17CopyAssignable* | `a == t` | 线性 |
| `a = rv` | 若 POCMA 为 `false`：*Cpp17MoveInsertable* 且 *Cpp17MoveAssignable*（¶26） | 现有元素被移动赋值或销毁 | 线性 |
| `a.swap(b)` | — | 交换内容 | 常数 |

¶5 的 *Mandates* 是 C++20 收紧的：从前 `vector<int, allocator<long>>` 在一些实现上"能用"（内部 rebind），现在必须诊断。

```cpp title="alloc-mandates.cpp" error
#include <vector>
#include <memory>
std::vector<int, std::allocator<long>> v;   // error: allocator_type::value_type 必须与 value_type 相同
```

¶26 的条件前置条件值得细看：`a = rv` 在 POCMA 为 `false` 时可能需要**逐元素移动**（两个分配器不相等时，`a` 不能接管 `rv` 的缓冲区——它无法用自己的分配器释放那块内存），所以此时才要求 `T` 可移动插入/赋值。这就是为什么 `pmr` 容器的移动赋值在资源不同时退化为线性：

```cpp title="pmr-move-assign.cpp" run ok
#include <memory_resource>
#include <vector>
#include <cstdio>

int main() {
  std::pmr::monotonic_buffer_resource r1, r2;
  std::pmr::vector<int> a({1, 2, 3}, &r1);
  std::pmr::vector<int> b(&r2);

  const int* old = a.data();
  b = std::move(a);   // polymorphic_allocator 不随移动赋值传播，且 r1 != r2
  std::printf("%s\n", b.data() == old ? "stole buffer" : "element-wise move");
  std::printf("%s\n", b.get_allocator().resource() == &r2 ? "b keeps r2" : "?");
}
```

本机 libc++ 输出 `element-wise move` 与 `b keeps r2`。容器的 `noexcept` 规格也随之而来：`vector` 的移动赋值声明为 `noexcept(POCMA || is_always_equal)`（[[vector]]）。

## 历史脉络

| 版本 | 变化 |
|---|---|
| C++98 | 容器要求以"表 65/66"等形式出现；分配器被假定"同类型实例总相等" |
| C++11 | `allocator_traits` 与 POCCA/POCMA/POCS、`select_on_container_copy_construction`；*Cpp17*Insertable* 家族；移动构造常数；`size()` 常数 |
| C++17 | 节点句柄；`is_always_equal` 进入容器的 `noexcept` 规格 |
| C++20 | `<=>` 取代 `<` 等六个比较（可选操作改为 `synth-three-way`）；`allocator_type::value_type` 不匹配改为 *Mandates* |
| C++23 | 表格从"一张大表"改写为逐条的 *Result*/*Preconditions*/*Complexity* 格式；`container-compatible-range` 与 `from_range` 系列 |
| C++26 | `inplace_vector`、`hive` 加入，`array` 之外出现了第二个"移动和 `swap` 为线性"的容器 |

## 思考题

!!! question "1. `std::list<std::unique_ptr<int>>` 满足 *Cpp17CopyInsertable* 吗？`list` 的拷贝构造函数还能被声明吗？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

不满足——`allocator_traits<allocator<…>>::construct(m, p, v)` 对 `const unique_ptr&` 不良构。但 `list` 的拷贝构造函数**依然被声明**，`std::is_copy_constructible_v<std::list<std::unique_ptr<int>>>` 为 `true`。原因是容器把"*Cpp17CopyInsertable*"写成了 *Preconditions*（[container.reqmts] ¶12），而不是 *Constraints*。真正调用它时，在实例化过程中报错（硬错误，不是 SFINAE）。这正是 `std::vector<move-only>` 在泛型代码里"看起来可拷贝"的根源，也是 `std::optional` 等类型的复制构造函数要靠 *Constraints* 精确传播"可复制性"的对照。
</details>

!!! question "2. 两个 `std::vector<int, MyAlloc>`，`MyAlloc` 是有状态、POCS 为 `false`、两个实例不相等。`std::swap(a, b)`（不是成员 `swap`）是否同样是 UB？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

是。`vector` 的非成员 `swap` 被规定为 `x.swap(y)`（容器要求 ¶51："Equivalent to t.swap(s)"），而 `std::swap(a, b)` 这种限定调用在命名空间 `std` 里同样找得到这个重载，并且它比通用的 `std::swap` 主模板更特化（[[temp.func.order]]），会被选中。于是和成员 `swap` 一样落入 ¶65 的"分配器不等则 UB"。想要"分配器不等也能交换"，只能自己写三次移动（移动构造 + 两次移动赋值）：那条路径对不相等的分配器是良定义的，代价是线性时间、可能分配内存。
</details>

## 小结

- **容器要求**：成员类型、`X u(rv)` 常数（`array`/`inplace_vector` 除外）、`==` 先比大小、`size()` 常数、`swap` 不碰元素。
- **分配器的一生**：拷贝构造走 `select_on_container_copy_construction`，移动构造移动分配器（不得抛），其他构造显式传入；之后只在 POCCA/POCMA/POCS 为真时随赋值/交换替换。
- **`swap` 的 UB**：POCS 为假且分配器不等。
- ***Cpp17*Insertable***：都是"经由 `allocator_traits::construct` 能否构造"，和类型特征不是一回事；写在 *Preconditions* 里，违反时是实例化硬错误或 UB，而不是重载不可行。
- **连续容器**按迭代器定义：`array`、`vector`（非 bool）、`inplace_vector`、`basic_string`。
