---
title: 通用容器要求：容器、可逆容器、可选操作与分配器感知容器
summary: 所有标准容器共用的四组要求：成员类型与基本操作的复杂度，==、<=> 和 swap 的语义，分配器在拷贝、移动、赋值、交换时怎样传递，Cpp17CopyInsertable 等术语的定义，以及什么是连续容器。
status: done
covers: *
related: container.requirements, sequence.reqmts, allocator.traits, allocator.requirements, mem, res.on.data.races, swappable.requirements, alg.three.way
tags: 标准库, 容器, 分配器, 具名要求, POCMA, 异常安全
updated: 2026-10-19
---

!!! tldr
    - 除 `array` 和 `inplace_vector` 外，容器的移动构造和 `swap` 都是常数复杂度，所以只能交接内部缓冲区，不能逐个移动元素。
    - 拷贝构造的容器用 `select_on_container_copy_construction` 得到分配器，移动构造的容器移动源的分配器；之后分配器只在赋值或 `swap` 时、且对应的 propagate 特征为真时才会被替换。所以 `pmr` 容器的副本默认不在原来的内存池里。
    - 分配器不随 `swap` 传播而两个分配器又不相等时，`a.swap(b)` 是 UB。
    - *Cpp17CopyInsertable* 等术语的意思是经由分配器的 `construct` 能否构造，和 `is_copy_constructible` 不是一回事。它们写在 *Preconditions* 里，所以 `vector<unique_ptr<int>>` 的拷贝构造函数仍然被声明，调用时才报错。
    - `vector<int> v(5, 3)` 得到五个 3，因为整数类型不能被当作输入迭代器。

## 四组要求（[container.intro.reqmts]）

这一节定义了四组具名要求，其他容器条款都用"满足某某要求"来引用它们：

| 子条款 | 要求 | 哪些容器满足 |
|---|---|---|
| [container.reqmts] | 容器（container） | 本章全部容器，`forward_list`、`hive`、无序容器有局部例外 |
| [container.rev.reqmts] | 可逆容器（reversible container） | 迭代器为双向或随机访问的容器 |
| [container.opt.reqmts] | 可选操作 `<=>` | 序列容器与有序关联容器 |
| [container.alloc.reqmts] | 分配器感知容器（allocator-aware container） | 除 `array`、`inplace_vector` 外的全部容器，以及 `basic_string`、`basic_stacktrace`、`match_results` |

分配器只负责提供存储，元素要用 `construct` 逐个创建（[[allocator.requirements]]、[[allocator.traits]]）。这一节规定的是容器怎样使用分配器。

¶1 [container.intro.reqmts] 规定了全节的记号：`X` 是容器类，`T` 是元素类型；`a` 是 `X` 的值，`b`、`c` 可能是 `const X`；`i`、`j` 是 `X::iterator`；`v` 是 `X` 的左值或 `const X` 的右值，也就是会被拷贝的东西；`s`、`t` 是非 `const` 左值；`rv` 是非 `const` 右值，也就是会被移动的东西。所以表达式 `X u(v)` 表示拷贝构造，`X u(rv)` 表示移动构造。

¶2 定义了仅用于说明的 concept `container-compatible-range<R, T>`：`R` 是 `input_range`，而且它的引用类型可以转换为 `T`。C++23 引入的 `from_range_t` 构造函数、`insert_range`、`append_range` 等都用它约束。这是本章少有的真正的 concept 约束，不满足时重载不可行（[[over.match]]）。

## 容器要求 [container.reqmts]

¶1 类型 `X` 满足容器要求，当且仅当下列类型、语句和表达式良构并且具有规定的语义。

### 成员类型（¶2–¶9）

| 表达式 | 结果 | 要点 |
|---|---|---|
| `X::value_type` | `T` | ¶3 前置条件：`T` 可以从 `X` 中擦除（*Cpp17Erasable*，见下文），否则容器连析构都做不到 |
| `X::reference`、`X::const_reference` | `T&`、`const T&` | `vector<bool>` 不满足，见 [[vector.bool]] |
| `X::iterator` | 值类型为 `T` 的前向迭代器，可以转换为 `const_iterator` | ¶6 |
| `X::const_iterator` | 常量前向迭代器 | ¶7 |
| `X::difference_type` | 有符号整数类型，与两种迭代器的差类型相同 | ¶8 |
| `X::size_type` | 无符号整数类型，能表示 `difference_type` 的任何非负值 | ¶9 |

### 构造、赋值与析构（¶10–¶26）

- ¶10–¶11 `X u;`：后置条件 `u.empty()`，常数复杂度。
- ¶12–¶14 `X u(v);`：前置条件是 `T` 可拷贝插入（*Cpp17CopyInsertable*），后置条件 `u == v`，线性复杂度。
- ¶15–¶16 `X u(rv);`：`u` 等于 `rv` 在构造前的值。复杂度对 `array` 和 `inplace_vector` 是线性的，对其他标准容器是常数。常数复杂度意味着实现只能接管 `rv` 的内部缓冲区，不能逐个移动元素。
- ¶20–¶22 `t = rv`：`t` 现有的元素要么被移动赋值，要么被销毁。后置条件只在 `t` 和 `rv` 不是同一个对象时成立，所以 `v = std::move(v)` 不保证保留原值。按库的一般规则 [[lib.types.movedfrom#2]]，标准库类型自移动赋值后处于有效但未指定的状态。
- ¶24–¶26 `a.~X()`：销毁每个元素，释放获得的全部内存，线性复杂度。

### 迭代器与比较（¶27–¶47，¶63）

- ¶27–¶38 `begin()`、`end()` 对 `const X` 返回 `const_iterator`；`cbegin()` 定义为 `const_cast<X const&>(b).begin()`。全部是常数复杂度。
- ¶39–¶41 `i <=> j` 的约束是 `X::iterator` 满足随机访问迭代器要求，结果类型是 `strong_ordering`。
- ¶63 在 `i == j`、`i < j`、`i - j`、`i <=> j` 等表达式中，任一侧都可以换成指向同一元素的 `const_iterator`，语义不变。

!!! std
    c == b — Preconditions: T meets the Cpp17EqualityComparable requirements. ... Complexity: Constant if c.size() != b.size(), linear otherwise.

¶42–¶46 `c == b` 返回 `equal(c.begin(), c.end(), b.begin(), b.end())`。大小不同时必须在常数时间内返回 `false`。¶47 `c != b` 等价于 `!(c == b)`，C++20 起由重写候选自动提供。

¶46 还有一句 *Remarks*：`==` 是等价关系。这对元素类型有隐含要求：*Cpp17EqualityComparable*（[[utility.arg.requirements]]）要求 `==` 自反、对称、传递。`double` 的 NaN 不等于自己，所以在含 NaN 的取值上 ¶42 的前置条件不成立，标准也没有为浮点数开特例。实践中所有实现都只是逐个元素调用 `==`，含 NaN 的 `vector<double>` 不等于它自己，这在意料之中。写泛型代码时，不要假定容器的 `==` 对任意元素类型都是等价关系。

### `swap`、`size`、`empty`（¶48–¶62）

- ¶48–¶51 `t.swap(s)` 和 `swap(t, s)` 对 `array`、`inplace_vector` 是线性的，对其他容器是常数。非成员 `swap(t, s)` 等价于 `t.swap(s)`。
- ¶52–¶55 `c.size()` 返回 `distance(c.begin(), c.end())`，常数复杂度。`forward_list` 是唯一不提供它的容器。
- ¶56–¶58 `c.max_size()` 返回最大可能的容器的元素个数。
- ¶59–¶62 `c.empty()` 返回 `c.begin() == c.end()`，常数复杂度。

### 分配器从哪里来（¶64）

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

拷贝出来的 `b` 不在 `arena` 里，这由 ¶64 决定。¶64 按顺序规定了容器的分配器从哪里来、什么时候被替换：

1. 除非另有规定，本章的容器都通过分配器获取内存。注 2 补充，容器和迭代器只通过分配器的指针类型（`allocator_traits<A>::pointer` 或它的 rebind）引用分配到的元素。这使得花式指针（fancy pointer，例如共享内存里用偏移量表示的指针）可以用于标准容器。
2. 拷贝构造函数对源容器的分配器调用 `allocator_traits<A>::select_on_container_copy_construction`，得到新容器的分配器。
3. 移动构造函数从源容器的分配器移动构造出新的分配器，这次移动不得抛出异常。
4. 其他构造函数都接受一个 `const allocator_type&` 实参。注 3 提醒，使用这个实参的默认值时，分配器类型必须支持值初始化。
5. 在容器的整个生存期内，所有内存分配和元素构造都使用这个分配器的副本，直到它被替换。替换只能通过赋值或 `swap` 发生，而且只在对应的特征为 `true` 时：拷贝赋值看 `propagate_on_container_copy_assignment`（POCCA），移动赋值看 `propagate_on_container_move_assignment`（POCMA），交换看 `propagate_on_container_swap`（POCS）。
6. `get_allocator()` 返回构造时所用的分配器的副本，替换过的话返回最近一次替换后的副本。

`std::pmr::polymorphic_allocator` 的三个 propagate 特征都是 `false`，它的 `select_on_container_copy_construction` 返回一个默认构造的分配器，即使用默认内存资源。所以上例中 `b` 的分配器是默认资源，`d` 的仍是 `arena`。

!!! pitfall "pmr 容器的副本不在原来的内存池里"
    `std::pmr::vector<T> copy = pooled;` 得到的副本使用默认内存资源，而不是 `pooled` 的资源。这是有意的设计，防止生存期更长的副本还指向一个短命的内存池。但它常常让人以为整个子系统都在内存池里分配，实际上并没有。

### `swap` 的精确语义（¶65）

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

!!! std
    Otherwise, the allocators shall not be swapped, and the behavior is undefined unless a.get_allocator() == b.get_allocator().

¶65 如果 POCS 为 `false`，分配器不交换，这时两个分配器必须相等，否则行为未定义。原因是交换后 `a` 拿着 `r2` 分配的缓冲区，却只能用 `r1` 的分配器去释放它。

本机用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` 编译，libc++ 报告 *vector::swap: Either propagate_on_container_swap must be true or the allocators must compare equal* 并终止程序。不开加固时它照常交换缓冲区，问题留到释放内存时才出现。

¶65 的其余规定：

- 除 `array`、`inplace_vector` 外，`a.swap(b)` 交换两个容器的值，不对任何元素调用移动、拷贝或 `swap`。
- `Compare`、`Pred`、`Hash` 对象必须可交换（*Cpp17Swappable*），并按 [[swappable.requirements]] 的方式（即经由 ADL 找到的 `swap`）交换。
- POCS 为 `true` 时，分配器也按同样的方式交换。
- 交换前指向一个容器中元素的迭代器，交换后指向另一个容器中的同一个元素。交换前的 `a.end()` 交换后是否等于 `b.end()` 是未指定的。

### 默认的异常保证与失效规则（¶66–¶67）

¶66 列出六条默认保证：单元素插入和 `push_*`、`emplace_*` 抛异常时没有效果；`erase`、`clear`、`pop_*` 不抛异常；返回的迭代器的拷贝不抛异常；`swap` 不抛异常；`swap` 不使元素的迭代器失效。[[associative.reqmts]]、[[unord.req]]、[[deque]]、[[inplace.vector]]、[[vector]] 各自规定了例外。

¶67 是失效规则的总开关：除非另有规定，调用容器的成员函数或把容器传给库函数，不使迭代器失效，也不改变元素的值。

把这两段和各容器的细则合起来的对照表，见 [[container.requirements]]。

### 连续容器（¶68）

!!! std
    A contiguous container is a container whose member types iterator and const_iterator meet the Cpp17RandomAccessIterator requirements and model contiguous_iterator.

¶68 **连续容器**（contiguous container）是 `iterator` 和 `const_iterator` 满足 *Cpp17RandomAccessIterator* 要求、并且建模 `contiguous_iterator` 的容器。定义是按迭代器给出的，而不是按内存布局。标准中的连续容器有 `array`、`vector`（元素不是 `bool` 时）、`inplace_vector`，以及第 27 章的 `basic_string`。它们都能直接转换为 `span`（[[views.contiguous]]）。

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

### 整数不能当作迭代器（¶69）

上例最后的 `vector<int> v(5, 3)` 有两个同类型的实参。模板构造函数 `vector(InputIterator, InputIterator)` 可以推导出 `InputIterator = int`，而且比 `vector(size_type, const T&)` 匹配得更好，因为后者需要把 `int` 转换为 `size_type`。

¶69 规定，容器的某些成员函数和推导指引的行为，取决于一个类型是否有资格作为输入迭代器或分配器。实现在多大程度上判断一个类型不能作为输入迭代器是未指定的，但至少整数类型没有资格。同样，一个类型 `A` 至少要满足两个条件才有资格作为分配器：`A::value_type` 有效且是一个类型；`declval<A&>().allocate(size_t{})` 作为不求值操作数是良构的。

[[sequence.reqmts]] 的第 69 段再规定，没有资格的类型使相应的构造函数和成员函数不参与重载决议。于是 `vector<int> v(5, 3)` 选中的是 `(n, value)` 版本。C++98 用另一种办法处理这个问题：`InputIterator` 是整数类型时，模板版本表现得像调用 `(n, value)` 版本。

## 可逆容器 [container.rev.reqmts]

¶1 类型 `X` 满足可逆容器要求，如果它满足容器要求，迭代器属于双向或随机访问类别，并且提供：

- ¶2–¶3 `reverse_iterator` 即 `std::reverse_iterator<iterator>`，`const_reverse_iterator` 同理；
- ¶4–¶15 `rbegin()` 返回 `reverse_iterator(end())`，`rend()` 返回 `reverse_iterator(begin())`，`crbegin()` 和 `crend()` 用 `const_cast` 定义，全部是常数复杂度。

`forward_list` 和无序容器不是可逆容器，`hive` 是。

## 可选操作 `<=>` [container.opt.reqmts]

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

¶1 下面的操作只有部分容器提供。传给 `lexicographical_compare_three_way` 的迭代器满足 constexpr 迭代器要求时，这些操作是 `constexpr` 函数。

- ¶2 `a <=> b` 的结果类型是 `synth-three-way-result<value_type>`。
- ¶3 前置条件：要么 `T` 建模 `three_way_comparable`，要么 `<` 对（可能带 `const` 的）`T` 有定义，并且是全序关系。
- ¶4–¶5 返回 `lexicographical_compare_three_way(a.begin(), a.end(), b.begin(), b.end(), synth-three-way)`（[[alg.three.way]]），线性复杂度。

所以 `vector<double>` 的 `<=>` 结果类型是 `partial_ordering`，遇到 NaN 得到 `unordered`，这是有定义的，因为 `double` 建模 `three_way_comparable`。而一个只提供非全序 `operator<` 的类型放进容器再比较，就违反了前置条件。

无序容器和 `hive` 不提供 `<=>`，`hive` 连 `==` 和 `!=` 都不提供（[[hive]]）。

## 分配器感知容器 [container.alloc.reqmts]

¶1 除 `array` 和 `inplace_vector` 外，第 23 章的全部容器，以及 `basic_stacktrace`、`basic_string`（[[basic.string]]）、`match_results`，满足分配器感知容器的附加要求。

### *Cpp17CopyInsertable* 等术语（¶2）

这些术语出现在第 23 章几乎所有的 *Preconditions* 里。设 `A` 是分配器类型，`X` 的 `allocator_type` 是 `allocator_traits<A>::rebind_alloc<T>`，`m` 是 `A` 类型的左值，`p` 是 `T*`：

| 术语 | 定义：下列表达式良构，并且…… |
|---|---|
| `T` 可默认插入 `X`（*Cpp17DefaultInsertable*） | `allocator_traits<A>::construct(m, p)` |
| 元素被默认插入（default-inserted） | 用上面的表达式初始化。对 `std::allocator`，这就是值初始化 `::new(p) T()`；自定义分配器可以改成默认初始化，省去清零 |
| 可移动插入（*Cpp17MoveInsertable*） | `construct(m, p, rv)`，之后 `*p` 等价于 `rv` 原来的值。注 1：`rv` 仍是有效对象，状态未指定 |
| 可拷贝插入（*Cpp17CopyInsertable*） | 首先可移动插入，再加上 `construct(m, p, v)`，`v` 不变且等价于 `*p` |
| 可就地构造（*Cpp17EmplaceConstructible*）自 `args` | `construct(m, p, args)` |
| 可擦除（*Cpp17Erasable*）自 `X` | `allocator_traits<A>::destroy(m, p)` |

这些术语都是经由分配器定义的，所以和 `is_copy_constructible` 这类类型特征不是一回事。一个 `T` 本身不能拷贝构造，但只要分配器的 `construct` 能从 `const T&` 造出 `T`，它就可拷贝插入，反过来也一样。

如果 `X` 不是分配器感知的（`array`、`inplace_vector`），或者是 `basic_string` 的特化，这些术语就按 `A` 是 `allocator<T>` 来定义。这时不需要创建任何分配器对象，也不会实例化用户为 `allocator<T>` 写的特化。

注 2 说明，容器以 `m == get_allocator()` 调用 `construct(m, p, args)`。`std::allocator` 的默认做法是 `::new((void*)p) T(args)`（C++20 起实际经由 `construct_at`），但特制的分配器可以另行定义。`scoped_allocator_adaptor` 正是借此把自己传给嵌套的容器（[[allocator.uses]]）。

### 附加的表达式（¶3–¶32）

| 表达式 | 前置条件 | 后置条件或效果 | 复杂度 |
|---|---|---|---|
| `X::allocator_type` | ¶5 *Mandates*：`allocator_type::value_type` 与 `X::value_type` 相同 | | |
| `c.get_allocator()` | | | 常数 |
| `X u;` | `A` 可默认构造 | `u.empty()`，`u.get_allocator() == A()` | 常数 |
| `X u(m);` | | `u.empty()`，`u.get_allocator() == m` | 常数 |
| `X u(t, m);` | 可拷贝插入 | `u == t`，`u.get_allocator() == m` | 线性 |
| `X u(rv);` | | 元素和分配器都来自 `rv` | 常数 |
| `X u(rv, m);` | 可移动插入 | `u` 拥有 `rv` 原来的元素或它们的副本，`u.get_allocator() == m` | `m == rv.get_allocator()` 时常数，否则线性 |
| `a = t` | 可拷贝插入且可拷贝赋值 | `a == t` | 线性 |
| `a = rv` | POCMA 为 `false` 时：可移动插入且可移动赋值（¶26） | 现有元素被移动赋值或销毁 | 线性 |
| `a.swap(b)` | | 交换内容 | 常数 |

¶5 的 *Mandates* 是 C++20 加上的。以前 `vector<int, allocator<long>>` 在某些实现上能用（内部做 rebind），现在必须诊断：

```cpp title="alloc-mandates.cpp" error
#include <vector>
#include <memory>
std::vector<int, std::allocator<long>> v;   // error: allocator_type::value_type 必须与 value_type 相同
```

¶26 的前置条件带有条件：POCMA 为 `false` 时，两个分配器可能不相等，`a` 不能接管 `rv` 的缓冲区，因为它无法用自己的分配器释放那块内存，只能逐个移动元素。所以只在这种情况下要求 `T` 可移动插入和可移动赋值。这就是 `pmr` 容器在内存资源不同时，移动赋值退化为线性的原因：

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

本机 libc++ 输出 `element-wise move` 和 `b keeps r2`。容器的 `noexcept` 规格也由此而来：`vector` 的移动赋值声明为 `noexcept(POCMA || is_always_equal)`（[[vector]]）。

## 历史与演进

| 版本 | 变化 |
|---|---|
| C++98 | 容器要求以表格形式给出；允许实现假定同一类型的分配器实例总是相等 |
| C++11 | `allocator_traits`、POCCA、POCMA、POCS 和 `select_on_container_copy_construction`；*Cpp17CopyInsertable* 等术语；移动构造为常数；`size()` 为常数 |
| C++17 | 节点句柄；`is_always_equal` 进入容器的 `noexcept` 规格 |
| C++20 | `<=>` 取代 `<` 等比较运算符，可选操作改用 `synth-three-way`；分配器 `value_type` 不匹配改为 *Mandates* |
| C++23 | `container-compatible-range` 与 `from_range` 系列 |
| C++26 | 加入 `inplace_vector` 和 `hive`；除 `array` 外又多了一个移动构造和 `swap` 为线性的容器 |

## 思考题

!!! question "思考题 1"
    `std::list<std::unique_ptr<int>>` 的元素可拷贝插入吗？`list` 的拷贝构造函数还会被声明吗？

<details markdown="1">
<summary>答案</summary>

不可拷贝插入，`allocator_traits<allocator<...>>::construct(m, p, v)` 对 `const unique_ptr&` 不良构。但 `list` 的拷贝构造函数仍然被声明，`std::is_copy_constructible_v<std::list<std::unique_ptr<int>>>` 是 `true`。原因是 [container.reqmts] 第 12 段把可拷贝插入写成了 *Preconditions*，而不是 *Constraints*。真正调用拷贝构造函数时，会在实例化过程中报错，这是硬错误，不能用 SFINAE 检测。所以在泛型代码里，`std::vector<只能移动的类型>` 看起来可以拷贝。`std::optional` 等类型则用 *Constraints* 精确地传递可拷贝性，可以作对照。
</details>

!!! question "思考题 2"
    两个 `std::vector<int, MyAlloc>`，`MyAlloc` 有状态、POCS 为 `false`、两个实例不相等。`std::swap(a, b)`（不是成员 `swap`）也是 UB 吗？

<details markdown="1">
<summary>答案</summary>

是。`vector` 的非成员 `swap` 等价于 `x.swap(y)`（[container.reqmts] 第 51 段）。`std::swap(a, b)` 这种限定调用在命名空间 `std` 里同样能找到这个重载，它比通用的 `std::swap` 模板更特化（[[temp.func.order]]），会被选中。于是和成员 `swap` 一样，落入 ¶65 的分配器不相等则 UB。如果分配器不相等也要交换，只能自己写一次移动构造加两次移动赋值。这条路径对不相等的分配器是有定义的，代价是线性时间，还可能分配内存。
</details>

## 小结

- 容器要求：成员类型；移动构造为常数（`array`、`inplace_vector` 除外）；大小不同时 `==` 为常数；`size()` 为常数；`swap` 不碰元素。
- 分配器：拷贝构造用 `select_on_container_copy_construction`，移动构造移动分配器且不得抛异常，其他构造函数显式接受；之后只在 POCCA、POCMA、POCS 为真时随赋值或交换被替换。
- POCS 为假且分配器不相等时，`swap` 是 UB。
- *Cpp17CopyInsertable* 等术语看的是经由 `allocator_traits::construct` 能否构造，写在 *Preconditions* 里，不满足时是实例化错误或 UB，而不是重载不可行。
- 连续容器按迭代器定义：`array`、`vector`（非 `bool`）、`inplace_vector`、`basic_string`。
