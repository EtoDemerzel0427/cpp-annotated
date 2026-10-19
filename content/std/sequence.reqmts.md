---
title: 序列容器要求
summary: vector、deque、list 等序列容器共同的契约：构造、insert、emplace、erase、assign 的前置条件与返回值，哪些自引用的实参合法，整数为什么不会被当作迭代器，以及 front、back、operator[] 在 C++26 中成为加固前置条件。
status: done
related: container.requirements, container.requirements.general, vector, deque, list, forward.list, array, inplace.vector, hive, res.on.arguments
tags: 标准库, 容器, 序列容器, 加固, 前置条件
updated: 2026-10-19
---

!!! tldr
    - 在 `vector`、`deque`、`inplace_vector` 中间插入或擦除要挪动已有元素，所以它们比 `list` 多要求元素可移动赋值。
    - `v.push_back(v[0])`、`v.insert(p, v.back())` 这类单元素操作引用容器自身的元素是合法的；但 `v.insert(p, v.begin(), v.end())` 用自身的区间作源是 UB。
    - 区间构造和插入时，每个源迭代器恰好解引用一次。
    - 只有能在摊还常数时间内完成的容器才提供 `push_front`、`operator[]` 等可选操作，所以 `vector` 没有 `push_front`，`list` 没有 `operator[]`。
    - C++26 起，`front`、`back`、`pop_*`、`operator[]` 的前置条件是加固前置条件，加固实现会在违反时终止程序；`at` 越界则抛出 `out_of_range`。

## 序列容器是什么（¶1）

¶1 **序列容器**（sequence container）把有限个同类型对象排成严格的线性序列，元素的位置由插入方式决定，而不是由值决定。标准库提供五种基本的序列容器：`vector`、`inplace_vector`、`forward_list`、`list`、`deque`。

`array` 和 `hive` 也是序列容器，但只提供有限的序列操作：`array` 的元素个数固定，不能插入和擦除；`hive` 由容器决定插入位置，所以没有"在 p 之前插入"这种操作。

容器适配器 `stack`、`queue`、`flat_map`、`flat_multimap`、`flat_set`、`flat_multiset` 由基本序列容器组装而成，¶1 说也可以由程序自定义的序列容器组装。所以自己写的容器只要满足这一节的要求，就能放进这些适配器（[[container.adaptors]]、[[flat.map]]）。

具体容器的条款只补充这一节没写的部分。例如 `vector::insert` 的完整语义，是这一节的条目加上 [[vector]] 中 [vector.modifiers] 的规定。

## 记号（¶2–¶4）

¶2 规定的记号里有几条容易忽略：

- `A` 是 `X::allocator_type`（如果这个名字有效且表示类型），否则是 `allocator<T>`。这样，`inplace_vector` 这类不是分配器感知的容器也能使用 *Cpp17CopyInsertable* 等术语（[[container.requirements.general]]）。
- `p` 是 `a` 的有效常量迭代器，可以是 `end()`；`q` 是可解引用的常量迭代器，不能是 `end()`。所以 `erase(end())` 违反前置条件。
- `[q1, q2)` 是 `a` 中常量迭代器构成的有效区间。
- `t` 是 `value_type` 的左值或 `const` 右值，`rv` 是非 `const` 右值。

¶3 各表达式的复杂度依具体容器而定，这一节的条目几乎不写复杂度，复杂度在各容器的条款里给出。¶4 类型 `X` 满足序列容器要求，如果它满足容器要求，并且下列语句和表达式良构、具有规定的语义。

## 构造与赋值（¶5–¶19）

| 表达式 | 前置条件 | 要点 |
|---|---|---|
| `X u(n, t);` | 可拷贝插入 | ¶5–¶7 n 个 `t` 的副本 |
| `X u(i, j);` | 可从 `*i` 就地构造；对 `vector`，迭代器不满足前向迭代器要求时还要可移动插入 | ¶9 每个迭代器恰好解引用一次 |
| `X(from_range, rg)` | 同上；对 `vector`，`rg` 只能预估长度（`approximately_sized_range` 而非 `sized_range`）或者是单趟区间时，还要可移动插入 | ¶13 推荐实践：预估长度 `reserve_hint` 不小于实际长度时，最多重新分配一次 |
| `X(il)` | | ¶15 等价于 `X(il.begin(), il.end())` |
| `a = il` | 可拷贝插入且可拷贝赋值 | ¶18 现有元素被赋值或销毁 |

为什么只有 `vector` 在单趟的输入迭代器时额外要求可移动插入？单趟区间无法预先知道长度，`vector` 只能边读边追加，中途扩容要把已有元素移动到新缓冲区。对前向迭代器，它可以先算出 `distance`，一次分配到位，再逐个构造，不需要搬迁。

每个迭代器恰好解引用一次，这是对实现的限制。实现不能为了求长度先走一遍输入区间（单趟迭代器也不支持走两遍），也不能对同一位置多次解引用。对 `istream_iterator` 这种解引用有副作用的迭代器，多一次解引用就会多读入数据。

C++23 的 range 接口把这些构造推广到任意 `container-compatible-range`：

```cpp title="ranges-api.cpp" run ok
#include <vector>
#include <list>
#include <deque>
#include <ranges>
#include <cassert>

int main() {
  // C++23 range 接口：from_range 构造、append_range、prepend_range、insert_range
  auto squares = std::views::iota(1, 5) | std::views::transform([](int x) { return x * x; });
  std::vector<int> v(std::from_range, squares);           // {1, 4, 9, 16}
  std::deque<int> d;
  d.append_range(v);
  d.prepend_range(std::views::iota(-2, 0));               // 不反转顺序：{-2, -1, 1, 4, 9, 16}
  std::list<int> l = d | std::ranges::to<std::list>();
  l.insert_range(std::next(l.begin()), std::views::single(0));
  assert((l == std::list<int>{-2, 0, -1, 1, 4, 9, 16}));
}
```

## 插入与擦除（¶20–¶52）

### 数组式容器为什么要求可移动赋值

| 表达式 | 所有序列容器的前置条件 | `vector`、`inplace_vector`、`deque` 的额外要求 |
|---|---|---|
| `a.emplace(p, args)` | 可从 `args` 就地构造 | 可移动插入、可移动赋值（¶21） |
| `a.insert(p, t)` | 可拷贝插入 | 可拷贝赋值（¶25） |
| `a.insert(p, rv)` | 可移动插入 | 可移动赋值（¶29） |
| `a.insert(p, n, t)` | 可拷贝插入、可拷贝赋值（¶33，所有容器都要求） | 无 |
| `a.insert(p, i, j)`、`a.insert_range(p, rg)` | 可从 `*i` 就地构造 | 可移动插入，且 `T` 可移动构造、可移动赋值、可交换（¶37、¶41） |
| `a.erase(q)`、`a.erase(q1, q2)` | 无 | 可移动赋值（¶46、¶50） |

在数组式容器的中间插入，要把插入点之后的元素往后挪。尾部新增的位置上原来没有对象，用移动构造；其余位置上已有对象，用移动赋值。擦除则相反：把后面的元素往前赋值，再销毁尾部多出来的对象。`list` 只修改指针，所以没有这些要求。

区间插入还要求可交换，是因为实现常用先追加到尾部、再用 `rotate` 转到位的策略，而 `rotate` 依赖 `swap`。

### 返回值

- ¶23、¶27、¶31 `emplace`、`insert(p, t)`、`insert(p, rv)` 返回指向新元素的迭代器。
- ¶35、¶39、¶43 `insert(p, n, t)`、`insert(p, i, j)`、`insert_range` 返回指向第一个新元素的迭代器，什么都没插入时返回 `p`。
- ¶48 `erase(q)` 返回擦除前紧跟在 `q` 之后的元素的迭代器，没有则返回 `end()`。¶52 `erase(q1, q2)` 返回擦除前 `q2` 所指元素的迭代器。

所以边遍历边擦除的写法是 `it = c.erase(it);`。

### 引用容器自身元素的实参

```cpp title="self-reference.cpp" run ok
#include <vector>
#include <string>
#include <cassert>

int main() {
  std::vector<std::string> v{"hello"};
  v.shrink_to_fit();                    // 让下一次 push_back 必然扩容
  v.push_back(v[0]);                    // OK：实现必须先构造新元素再释放旧缓冲区
  v.emplace_back(v[1]);                 // OK：同理（¶22 注 1）
  v.insert(v.begin(), v.back());        // OK：insert(p, t) 的 t 可以引用容器自身的元素
  assert(v.size() == 4 && v[0] == "hello" && v[3] == "hello");
}
```

¶22 的注 1 说，`emplace` 的实参可以直接或间接引用 `a` 中的值。`insert(p, t)` 也没有"`t` 不得引用 `a`"的前置条件。因此这三个调用都必须正确工作：实现要先在新位置构造好元素，再挪动或释放旧元素。

区间形式的操作则不同，它们的前置条件明确排除了自引用：

| 写法 | 结论 | 依据 |
|---|---|---|
| `a.insert(p, i, j)`，`i`、`j` 是 `a` 的迭代器 | {{ub}} | ¶37：`i` 和 `j` 都不是指向 `a` 的迭代器 |
| `a.assign(i, j)`，同上 | {{ub}} | ¶58 |
| `a.insert_range(p, rg)`、`a.assign_range(rg)`，`rg` 与 `a` 重叠 | {{ub}} | ¶41、¶62：`rg` 与 `a` 不重叠 |
| `a.assign(n, t)`，`t` 引用 `a` 的元素 | {{ub}} | ¶67：`t` 不是指向 `a` 的引用 |
| `a.push_back(std::move(a[0]))` | 实现可以假定没有别名 | [[res.on.arguments#1]] 第 3 项：绑定到右值引用形参的实参，实现可以假定它是唯一的引用 |

```cpp title="self-range.cpp" ub
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  v.insert(v.begin(), v.begin(), v.end());   // UB: i、j 不能是指向 v 的迭代器
}
```

本机 libc++ 在 ASan 下运行这段代码没有报错，结果看起来也对。这不改变它违反前置条件的事实，换一个实现或换一种元素类型，就可能读到已经被挪动过的元素。

### `clear` 与 `assign`（¶53–¶68）

- ¶54–¶56 `a.clear()` 销毁所有元素，使指向元素的引用、指针、迭代器失效，还可能使尾后迭代器失效。线性复杂度。
- ¶59、¶63、¶68 `assign(i, j)`、`assign_range(rg)`、`assign(n, t)` 用新内容替换原有元素，使所有指向元素的引用、指针、迭代器失效；对 `vector` 和 `deque` 还使尾后迭代器失效。
- ¶61 `assign_range` 有 *Mandates*：`assignable_from<T&, range_reference_t<R>>` 被建模。对 `inplace_vector`，如果 `ranges::size(rg)` 是常量表达式，它不得超过 `max_size()`，放不下的情况在编译期就能发现。

## 整数不是迭代器（¶69）

`std::vector<int> v(5, 3)` 的两个实参类型相同，模板构造函数 `X(InputIterator, InputIterator)` 可以推导出 `InputIterator = int`。¶69 对第 23 章和第 27 章（字符串）的每个序列容器规定：

- ¶69.1 构造函数 `X(InputIterator first, InputIterator last, const allocator_type& = ...)` 在 `InputIterator` 没有资格作为输入迭代器时，不参与重载决议。
- ¶69.2 `F(p, first, last)`（如 `insert`）、`F(first, last)`（如 `append`、`assign`）、`F(i1, i2, first, last)`（如 `replace`）这几种形式的成员函数模板同理。
- ¶69.3 推导指引推导出的 `InputIterator` 没有资格作为输入迭代器，或推导出的 `Allocator` 没有资格作为分配器时，也不参与重载决议。

[[container.requirements.general]] 的第 69 段规定了最低标准：整数类型没有资格作为输入迭代器。于是 `std::vector<int> v(5, 3)` 是五个 3，`v.assign(5, 3)` 同理。

## 可选操作（¶70–¶128）

¶70 下面的操作只有部分序列容器提供。除 `prepend_range` 和 `append_range` 外，它们都要在摊还常数时间内完成。这也决定了谁提供它们：做不到摊还常数的容器就不提供。所以 `vector` 没有 `push_front`，`list` 没有 `operator[]`，`forward_list` 没有 `push_back` 和 `back`。

| 操作 | 前置条件 | `vector` | `inplace_vector` | `deque` | `list` | `forward_list` | `array` | `basic_string` |
|---|---|---|---|---|---|---|---|---|
| `front()` | 加固：`!empty()` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `back()` | 加固：`!empty()` | ✓ | ✓ | ✓ | ✓ | | ✓ | ✓ |
| `emplace_front`、`push_front`、`prepend_range` | | | | ✓ | ✓ | ✓ | | |
| `emplace_back`、`append_range` | | ✓ | ✓ | ✓ | ✓ | | | |
| `push_back` | | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| `pop_front()` | 加固：`!empty()` | | | ✓ | ✓ | ✓ | | |
| `pop_back()` | 加固：`!empty()` | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| `operator[](n)` | 加固：`n < size()` | ✓ | ✓ | ✓ | | | ✓ | ✓ |
| `at(n)` | 越界抛 `out_of_range` | ✓ | ✓ | ✓ | | | ✓ | ✓ |

`basic_string` 不要求提供 `emplace_back` 和 `append_range`，它有自己的 `append`。

C++17 起，`emplace_front` 和 `emplace_back` 返回新元素的引用，分别等价于返回 `a.front()` 和 `a.back()`（¶82、¶87）。`inplace_vector::push_back` 也返回引用，这是它自己的规定（[[inplace.vector]]）。

¶85 `emplace_back` 对 `vector` 要求可移动插入，因为扩容时要把旧元素移动构造到新缓冲区。¶80 `emplace_front` 只要求可就地构造：`deque` 在头部插入时只在空位上构造新元素，不触碰已有元素。

### 加固前置条件

```cpp title="hardened-front.cpp" run ub
#include <vector>
int main() {
  std::vector<int> e;
  return e.front();   // 违反加固前置条件：a.empty() 为 true
}
```

C++26 的标准库加固（[[P3471R4]]）把 `front`、`back`、`pop_front`、`pop_back`、`operator[]` 的前置条件改为 *Hardened preconditions*（¶72、¶76、¶114、¶118、¶122）。在**加固实现**（[[g:hardened-implementation]]）中，违反它们会以终止型语义作为契约违反来检查；在非加固实现中仍然是 {{ub}}（[[intro.compliance]]、[[structure.specifications]]）。

libc++ 用宏 `_LIBCPP_HARDENING_MODE` 选择模式，取值为 `_LIBCPP_HARDENING_MODE_NONE`、`_FAST`、`_EXTENSIVE`、`_DEBUG`。本机测试：`_EXTENSIVE` 下程序执行陷阱指令终止，没有消息；`_DEBUG` 下先打印 *libc++ Hardening assertion !empty() failed: front() called on an empty vector* 再终止。

`at(n)` 没有前置条件：越界时抛出 `out_of_range`（¶127），行为是有定义的。两者代表两种错误模型：`operator[]` 越界说明程序有缺陷，加固实现会终止程序；`at` 越界是调用者预料到、打算捕获的错误。

## 常见误解

!!! pitfall "把容器自身的区间追加到末尾没问题"
    `v.insert(v.end(), v.begin(), v.end())` 违反 ¶37，是 {{ub}}。一旦触发扩容，`[i, j)` 就指向已经释放的缓冲区。可以先复制到一个临时容器，再 `append_range`。

!!! pitfall "`erase(end())` 什么都不做"
    `erase(q)` 要求 `q` 可解引用（¶2 的记号），`end()` 不可解引用，所以这是 {{ub}}。`erase(q1, q2)` 中 `q1 == q2 == end()` 是合法的空区间。

## 思考题

!!! question "思考题"
    为什么 `deque::emplace(p, args)` 要求元素可移动赋值，而 `deque::emplace_front` 不要求？

<details markdown="1">
<summary>答案</summary>

`emplace(p, args)` 在中间插入，`deque` 要把插入点某一侧（较短的那一侧）的元素整体挪动一格，挪到原本已有对象的位置上用的是移动赋值，所以 ¶21 对 `vector`、`inplace_vector`、`deque` 都要求可移动赋值。`emplace_front` 只在头部的空位上构造新元素，不触碰已有元素（[deque.modifiers] 第 2 段：只调用一次 `T` 的构造函数），所以 ¶80 只要求可就地构造。
</details>

## 小结

- 前置条件反映物理实现：数组式容器（`vector`、`inplace_vector`、`deque`）在中间插入、擦除需要移动赋值，节点式容器不需要。
- 区间构造和插入：每个迭代器恰好解引用一次；源区间不能指向容器自身；`assign(n, t)` 的 `t` 不能引用自身。单元素的 `insert`、`push_back`、`emplace` 引用自身元素是合法的。
- 可选操作只由能在摊还常数时间内完成它们的容器提供。
- C++26：`front`、`back`、`pop_*`、`operator[]` 是加固前置条件；`at` 越界仍是抛异常。
