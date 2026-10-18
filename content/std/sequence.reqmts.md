---
title: 序列容器要求
summary: 序列容器的统一契约——构造、insert/emplace/erase/assign 的前置条件为何对 vector/deque 额外要求可移动赋值、"每个迭代器恰好解引用一次"、自引用实参何时合法、整数不算迭代器的重载规则，以及 front/back/operator[]/pop_* 在 C++26 中成为加固前置条件
status: done
related: container.requirements, container.requirements.general, vector, deque, list, forward.list, array, inplace.vector, hive, res.on.arguments
tags: 标准库, 容器, 序列容器, 加固, 前置条件
updated: 2026-10-18
---

序列容器（sequence container）把一组同类型对象排成**严格线性**的序列，元素的位置由插入方式决定，而不是由值决定。本节是 `vector`、`deque`、`list`、`forward_list`、`inplace_vector`（以及部分地，`array`、`hive`）的共同契约。每个具体容器的条款只补充本节没写或需要加强的部分，所以要知道 `vector::insert` 的完整语义，必须把本节的表达式条目与 [[vector]] 的 [vector.modifiers] 叠加起来读。

前置知识：[[container.requirements.general]] 中的容器要求与 *Cpp17*Insertable* 家族。

## 谁是序列容器（¶1）

¶1 列出五种**基本**序列容器：`vector`、`inplace_vector`、`forward_list`、`list`、`deque`。另外两种只提供**有限**的序列操作：

- `array`——元素个数固定，不能插入或擦除；
- `hive`——插入位置由容器决定（"insertion order is unspecified"），所以没有 `insert(p, t)` 这种"在 p 之前插入"的操作。

库还提供容器适配器：`stack`、`queue`、`flat_map`、`flat_multimap`、`flat_set`、`flat_multiset`，它们由基本序列容器（**或程序自定义的序列容器**）组装而来——这就是"满足序列容器要求"对用户的实际意义：你写的容器只要满足本节要求，就能插进这些适配器（[[container.adaptors]]、[[flat.map]]）。

## 记号（¶2–¶3）

¶2 的记号里有几条容易被忽略的精确约定：

- `A` 是 `X::allocator_type`（若该限定名有效且表示类型），**否则是 `allocator<T>`**——这让 `inplace_vector` 这类非分配器感知容器也能复用 *Cpp17*Insertable* 术语；
- `p` 是**有效的常量迭代器**（可以是 `end()`），`q` 是**可解引用的**常量迭代器——所以 `erase(end())` 违反前置条件；
- `[q1, q2)` 是 `a` 中常量迭代器构成的有效区间；
- `t` 是 `value_type` 的左值或 const 右值，`rv` 是非 const 右值。

¶3：复杂度"依序列而定"——本节的条目本身几乎不写复杂度，复杂度在各容器条款里给出。

## 构造与赋值（¶4–¶19）

| 表达式 | 前置条件 | 要点 |
|---|---|---|
| `X u(n, t);` | *Cpp17CopyInsertable* | n 个 `t` 的副本（¶5–¶7） |
| `X u(i, j);` | *Cpp17EmplaceConstructible* 自 `*i`；对 `vector`，若迭代器不满足前向迭代器要求，还要 *Cpp17MoveInsertable* | **每个迭代器恰好解引用一次**（¶9） |
| `X(from_range, rg)` | 同上，`vector` 在 `rg` 只是 `approximately_sized_range` 而非 `sized_range`、或只是 `input_range` 时还要 *Cpp17MoveInsertable* | ¶13 推荐实践：若 `ranges::distance(rg) <= ranges::reserve_hint(rg)`，最多一次重新分配 |
| `X(il)` | — | 等价于 `X(il.begin(), il.end())` |
| `a = il` | *Cpp17CopyInsertable* 且 *Cpp17CopyAssignable* | 现有元素被赋值或销毁（¶18） |

为什么 `vector` 在输入迭代器时额外需要 *Cpp17MoveInsertable*？因为单趟输入区间无法预知长度，`vector` 只能边读边 `push_back`，中途扩容要把已有元素**搬**到新缓冲区；而对前向迭代器，它可以先 `distance` 一遍、一次分配到位，再逐个构造，根本不需要搬迁。

"每个迭代器恰好解引用一次"是对实现的**禁令**：实现不能为了求长度先走一遍输入区间再走第二遍（单趟迭代器根本不支持），也不能对同一位置多次解引用（对于有副作用的迭代器，例如 `istream_iterator`，这会读入多余数据）。

C++23 的 range 接口把上述构造推广到任意 `container-compatible-range`（[[container.requirements.general]]）：

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

## 插入与擦除（¶19–¶55）

### 为什么 `vector`/`deque`/`inplace_vector` 需要"可移动赋值"

| 表达式 | 所有序列容器的前置条件 | `vector`、`inplace_vector`、`deque` 额外要求 |
|---|---|---|
| `a.emplace(p, args)` | *Cpp17EmplaceConstructible* 自 `args` | *Cpp17MoveInsertable* + *Cpp17MoveAssignable*（¶21） |
| `a.insert(p, t)` | *Cpp17CopyInsertable* | *Cpp17CopyAssignable*（¶25） |
| `a.insert(p, rv)` | *Cpp17MoveInsertable* | *Cpp17MoveAssignable*（¶29） |
| `a.insert(p, n, t)` | *Cpp17CopyInsertable* + *Cpp17CopyAssignable*（所有容器） | — |
| `a.insert(p, i, j)` / `insert_range(p, rg)` | *Cpp17EmplaceConstructible* | *Cpp17MoveInsertable*，且 `T` 满足 *Cpp17MoveConstructible*、*Cpp17MoveAssignable*、*Cpp17Swappable*（¶37、¶41） |
| `a.erase(q)` / `erase(q1, q2)` | — | *Cpp17MoveAssignable*（¶46、¶50） |

物理图景：在数组式容器的中间插入，要把插入点之后的元素**往后挪**——尾部新增的槽位用移动**构造**（那里原来没有对象），其余的用移动**赋值**（那里已有对象）。擦除则反过来，把后面的元素**往前赋值**，再销毁尾部多出来的对象。`list` 只改指针，所以没有这些要求。区间插入额外要求 *Cpp17Swappable*，是因为实现常用"先在尾部追加、再 `rotate` 到位"的策略，而 `rotate` 依赖 `swap`。

### 返回值约定（¶23–¶52）

- `emplace`/`insert(p, t)`/`insert(p, rv)` 返回指向新元素的迭代器；
- `insert(p, n, t)`、`insert(p, i, j)`、`insert_range` 返回指向**第一个**新元素的迭代器，若没插入任何东西则返回 `p`；
- `erase(q)` 返回 `q` 之后元素（擦除前意义上）的迭代器，无则 `end()`；`erase(q1, q2)` 返回擦除前 `q2` 所指元素的迭代器。

这套约定使"边遍历边擦除"的标准写法成立：`it = c.erase(it);`。

### 自引用实参：哪些合法，哪些不合法

¶22 的注 1 写道：*args can directly or indirectly refer to a value in a*——`emplace` 的实参可以引用容器自身的元素。对 `insert(p, t)` 本节没有任何"`t` 不得引用 `a`"的前置条件，因此 `v.insert(v.begin(), v.back())`、`v.push_back(v[0])` 都必须正确工作：实现必须先在新位置构造好元素，再挪动或释放旧元素。

```cpp title="self-reference.cpp" run ok
#include <vector>
#include <string>
#include <cassert>

int main() {
  std::vector<std::string> v{"hello"};
  v.shrink_to_fit();                    // 让下一次 push_back 必然扩容
  v.push_back(v[0]);                    // OK：实现必须先构造新元素再释放旧缓冲区
  v.emplace_back(v[1]);                 // OK：同理（¶22 的注）
  v.insert(v.begin(), v.back());        // OK：insert(p, t) 的 t 可以引用容器自身元素
  assert(v.size() == 4 && v[0] == "hello" && v[3] == "hello");
}
```

但另外三种情形**明确**不合法或不受保护：

| 写法 | 判定 | 依据 |
|---|---|---|
| `a.insert(p, i, j)`，`i`/`j` 是 `a` 的迭代器 | {{ub}} | ¶37："Neither i nor j are iterators into a" |
| `a.insert_range(p, rg)` / `a.assign_range(rg)`，`rg` 与 `a` 重叠 | {{ub}} | ¶41、¶62："rg and a do not overlap" |
| `a.assign(n, t)`，`t` 引用 `a` 的元素 | {{ub}} | ¶67："t is not a reference into a" |
| `a.push_back(std::move(a[0]))` | 实现可假定无别名 | [[res.on.arguments#1]]（1.3）：绑定到右值引用形参时，实现可假定该形参是实参的唯一引用 |

```cpp title="self-range.cpp" ub
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  v.insert(v.begin(), v.begin(), v.end());   // UB: 前置条件要求 i、j 不是指向 a 的迭代器
}
```

本机 libc++ 在 ASan 下运行这段代码没有报告错误，结果也"看起来对"——这不改变它违反前置条件的事实，换一个实现或换一个元素类型就可能读到已被挪动的元素。

### `clear` 与 `assign`（¶53–¶68）

- `a.clear()`：销毁所有元素，使所有元素的引用、指针、迭代器失效，**可能**使尾后迭代器失效；线性（¶54–¶56）。
- `a.assign(i, j)` / `assign_range(rg)` / `assign(n, t)`：用新内容替换，使所有元素的引用、指针、迭代器失效；对 `vector` 和 `deque` 还使尾后迭代器失效（¶59、¶63、¶68）。
- `assign_range` 有一条 *Mandates*：`assignable_from<T&, range_reference_t<R>>` 被建模；对 `inplace_vector`，若 `ranges::size(rg)` 是常量表达式，则它不得超过 `max_size()`（¶61）——编译期就能抓住"塞不下"。

## 整数不是迭代器：模板成员的重载规则（¶69）

¶69 对本章和第 27 章（字符串）的**每个**序列容器规定：

- (69.1) 构造函数 `X(InputIterator, InputIterator, const allocator_type& = …)`，若 `InputIterator` 不具备输入迭代器资格，则**不参与重载决议**；
- (69.2) `F(p, first, last)`（如 `insert`）、`F(first, last)`（如 `append`、`assign`）、`F(i1, i2, first, last)`（如 `replace`）同理；
- (69.3) 推导指引若推导出的 `InputIterator` 不具备资格、或 `Allocator` 不具备分配器资格，则不参与重载决议。

"具备资格"的最低标准在 [[container.requirements.general]] ¶69：整数类型绝不是输入迭代器。于是 `std::vector<int> v(5, 3)` 是五个 3，`v.assign(5, 3)` 同理。

## 可选序列操作（¶70–¶128）

¶70：这些操作只有部分序列容器提供；除 `prepend_range` 和 `append_range` 外，都要实现为**摊还常数时间**。这句话是一条隐含的"提供与否"的标准：**做不到摊还常数的容器就不提供**。所以 `vector` 没有 `push_front`，`list` 没有 `operator[]`（脚注说明它们只由迭代器为随机访问的容器提供），`forward_list` 没有 `push_back`/`back`。

| 操作 | 前置条件类别 | `vector` | `inplace_vector` | `deque` | `list` | `forward_list` | `array` | `basic_string` |
|---|---|---|---|---|---|---|---|---|
| `front()` | 加固：`!empty()` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `back()` | 加固：`!empty()` | ✓ | ✓ | ✓ | ✓ | | ✓ | ✓ |
| `emplace_front`/`push_front`/`prepend_range` | — | | | ✓ | ✓ | ✓ | | |
| `emplace_back` | — | ✓ | ✓ | ✓ | ✓ | | | |
| `push_back` | — | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| `append_range` | — | ✓ | ✓ | ✓ | ✓ | | | |
| `pop_front()` | 加固：`!empty()` | | | ✓ | ✓ | ✓ | | |
| `pop_back()` | 加固：`!empty()` | ✓ | ✓ | ✓ | ✓ | | | ✓ |
| `operator[](n)` | 加固：`n < size()` | ✓ | ✓ | ✓ | | | ✓ | ✓ |
| `at(n)` | 越界抛 `out_of_range` | ✓ | ✓ | ✓ | | | ✓ | ✓ |

（`emplace_back` 与 `append_range` 不要求 `basic_string` 提供；`basic_string` 有自己的 `append`。）

`emplace_front`/`emplace_back` 返回新元素的**引用**（C++17 起），分别等价于返回 `a.front()`/`a.back()`（¶82、¶87）。注意 `inplace_vector` 的 `push_back` 也返回引用，这是它自己的扩展（[[inplace.vector]]）。

### 加固前置条件（Hardened preconditions）

C++26 的标准库加固（[[P3471R4]]）把 `front`、`back`、`pop_front`、`pop_back`、`operator[]` 的前置条件改写为 *Hardened preconditions*（¶72、¶76、¶114、¶118、¶122）。法律后果见 [[structure.specifications]] 与本站 [[mem]] 的说明：在**加固实现**（[[g:hardened-implementation]]）中，违反它们会以契约违例的终止语义被检查；在非加固实现中仍然是 {{ub}}。

```cpp title="hardened-front.cpp" run ub
#include <vector>
int main() {
  std::vector<int> e;
  return e.front();   // 违反 hardened precondition：a.empty() 为 true
}
```

libc++ 用宏 `_LIBCPP_HARDENING_MODE` 选择模式（取值 `_LIBCPP_HARDENING_MODE_NONE`/`_FAST`/`_EXTENSIVE`/`_DEBUG`）。本机实测：`_EXTENSIVE` 下程序直接以陷阱指令终止（退出码 133，无消息）；`_DEBUG` 下打印 `libc++ Hardening assertion !empty() failed: front() called on an empty vector` 后终止。

`at(n)` 则从来不是前置条件：越界时**抛出** `out_of_range`（¶127），是定义良好的行为。

!!! note "`at` 与 `operator[]` 的分工在 C++26 后更清楚了"
    `operator[]` 的越界是"契约违例"——程序有 bug，加固实现会终止它；`at` 的越界是"可恢复的错误"——调用者预期它可能发生并打算捕获。两者不是"安全版与快速版"的关系，而是两种不同的错误模型。

## 常见误区

!!! pitfall "\"insert(p, i, j) 用自己的区间做源很常见，应该没事\""
    比如"把 vector 自身复制一遍追加到末尾"：`v.insert(v.end(), v.begin(), v.end())`。这违反 ¶37，是 {{ub}}——一旦触发扩容，`[i, j)` 就指向已释放的缓冲区。正确写法是先 `reserve(2 * v.size())` 再用下标/指针复制，或者复制到临时容器再 `append_range`。

!!! pitfall "\"erase(end()) 什么都不做\""
    `erase(q)` 要求 `q` **可解引用**（¶2 的记号 `q`），`end()` 不可解引用。这是 {{ub}}。`erase(q1, q2)` 中 `q1 == q2 == end()` 则是合法的空区间。

## 思考题

!!! question "为什么 `deque::emplace(p, args)` 也要求 *Cpp17MoveAssignable*，而 `deque::emplace_front` 不要求？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

`emplace(p, args)` 在中间插入，`deque` 要把插入点一侧（较短的那一侧）的元素整体挪动一格——挪动到原本已有对象的位置上用的是**移动赋值**，所以 ¶21 对 `vector`、`inplace_vector`、`deque` 一并要求 *Cpp17MoveAssignable*。`emplace_front` 只在头部的空槽位上构造新元素，不触碰已有元素（[deque.modifiers] ¶2："causes a single call to a constructor of T"），所以 ¶80 只要求 *Cpp17EmplaceConstructible*。`vector::emplace_back` 则要求 *Cpp17MoveInsertable*（¶85），因为扩容时要把旧元素移动**构造**到新缓冲区。
</details>

## 小结

- 序列容器的前置条件反映物理实现：数组式容器（`vector`、`inplace_vector`、`deque`）中间插入/擦除需要移动赋值，节点式容器不需要。
- 区间构造/插入："每个迭代器恰好解引用一次"；源区间不得指向自身；`assign(n, t)` 的 `t` 不得引用自身；但单元素 `insert`/`push_back`/`emplace` 引用自身元素是合法的。
- 可选操作只由能摊还常数实现它们的容器提供。
- C++26：`front`/`back`/`pop_*`/`operator[]` 成为加固前置条件；`at` 仍是抛异常。
