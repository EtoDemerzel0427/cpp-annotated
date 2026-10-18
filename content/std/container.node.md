---
title: 节点句柄与 insert_return_type
summary: C++17 节点句柄（node handle）——只能移动的元素所有者、兼容节点表、空句柄不含分配器、移动赋值与 swap 的分配器前置条件、key() 返回非 const 引用为何合法、用户特化 pair 时的 UB，以及唯一键容器 insert(nh) 返回的 insert_return_type
status: done
covers: *, container.insert.return
related: associative.reqmts, unord.req, associative, unord, container.requirements.general, basic.life, allocator.traits
tags: 标准库, 容器, 节点句柄, extract, merge, C++17
since: c++17
papers: P0083R3
updated: 2026-10-18
---

C++17 的"拼接 map 与 set"（[[P0083R3]]）给节点式关联容器加上了 `extract`、`insert(node_type&&)` 和 `merge`。它们的核心是**节点句柄**（[[g:node-handle]]）：一个只能移动的对象，拥有一个从容器中摘下来的节点（以及其中的元素），可以把它原封不动地插进另一个容器。这实现了三件以前做不到的事：

1. **修改 `map` 的键而不拷贝/移动元素**：`extract` → 改 `key()` → 插回；
2. **在容器间转移只能移动、甚至不能移动的元素**，不重新分配内存；
3. **把元素"暂存"在容器之外**，之后再放回（或放进别的容器）。

## 概览（[container.node.overview]）

¶1：节点句柄接受关联容器（[[associative.reqmts]]）或无序关联容器（[[unord.req]]）中**单个元素**的所有权，可用于把所有权转移到另一个具有**兼容节点**的容器。兼容节点的容器具有**相同的**节点句柄类型。表 75 列出可以双向转移的容器对：

| 容器 | 可与之交换节点的容器 |
|---|---|
| `map<K, T, C1, A>` | `map<K, T, C2, A>`、`multimap<K, T, C2, A>` |
| `set<K, C1, A>` | `set<K, C2, A>`、`multiset<K, C2, A>` |
| `unordered_map<K, T, H1, E1, A>` | `unordered_map<K, T, H2, E2, A>`、`unordered_multimap<K, T, H2, E2, A>` |
| `unordered_set<K, H1, E1, A>` | `unordered_set<K, H2, E2, A>`、`unordered_multiset<K, H2, E2, A>` |

要点：键类型、映射类型、**分配器类型**必须相同；比较器、哈希、谓词可以不同；唯一键与等价键之间可以转移；**有序与无序之间不行**（节点结构不同：红黑树节点 vs 哈希链表节点）。

```cpp title="node-type-identity.cpp" run ok
#include <set>
#include <functional>
#include <type_traits>
static_assert(std::is_same_v<std::set<int>::node_type, std::multiset<int, std::greater<>>::node_type>);
int main(){}
```

¶2：非空的节点句柄含有一个分配器，等于元素被取出时容器的分配器；**空**节点句柄不含分配器。¶3：类 `node-handle` 仅用于阐述——每个容器的 `node_type` 是它的一个特化，名字未指明。

!!! std
    If a user-defined specialization of pair exists for pair<const Key, T> or pair<Key, T>, ... the behavior of operations involving node handles is undefined.

    若存在用户为 pair<const Key, T> 或 pair<Key, T> 定义的特化，涉及节点句柄的操作行为未定义。

¶4 的这条 UB 揭示了实现方式：为了让 `key()` 返回**可修改**的 `Key&`，实现需要在 `pair<const Key, T>` 与 `pair<Key, T>` 之间"换着看"同一个对象（两者布局相同）。用户特化 `pair` 会破坏这一布局假设，于是标准干脆宣布它是 UB。

## 仅用于阐述的定义

`node-handle` 持有两个成员：

- `ptr_`：指向容器节点的指针，类型为 `allocator_traits<allocator_type>::rebind_traits<container-node-type>::pointer`——即分配器的花式指针；
- `alloc_`：`optional<allocator_type>`，空句柄时为 `nullopt`。

公开接口：`value_type`（`map` 系没有）、`key_type`/`mapped_type`（`set` 系没有）、`allocator_type`；默认构造 `noexcept`（空句柄）；移动构造 `noexcept`；移动赋值；析构；`value()`、`key()`、`mapped()`、`get_allocator()`、`explicit operator bool`、`empty()`；`swap` 成员与友元 `swap`。**没有**拷贝构造和拷贝赋值。除 `key()` 外全部是 `constexpr`。

## 构造与赋值（[container.node.cons]）

- 移动构造（¶1）：接管 `nh.ptr_`，移动构造 `alloc_`，然后把 `nh.ptr_` 置空、`nh.alloc_` 置为 `nullopt`——被移动的句柄**一定为空**（不是"有效但未指明"）。
- 移动赋值（¶2–¶5）：
    - 前置条件：`!alloc_`（自身为空），或 POCMA 为真，或 `alloc_ == nh.alloc_`；
    - 效果：若自身非空，先用 `ator-traits::destroy` 销毁节点中的 `value_type` 子对象，再用 rebind 后的分配器释放节点；然后接管 `nh.ptr_`；若自身原本为空或 POCMA 为真，移动赋值 `alloc_`；最后把 `nh` 置空；
    - *Throws*：Nothing。

前置条件的理由：自身非空且不传播分配器时，`*this` 将用**自己的**分配器释放**将来**接管的节点，而该节点是 `nh` 的分配器分配的——二者必须相等。

## 析构（[container.node.dtor]）

¶1：若 `ptr_` 非空，用 `ator-traits::destroy` 销毁 `value_type` 子对象，再释放节点。所以一个被丢弃的非空节点句柄会**正常销毁元素并归还内存**，不会泄漏。

## 观察器（[container.node.observers]）

| 成员 | 前置条件 | 返回 |
|---|---|---|
| `value()` | `empty() == false` | 节点中 `value_type` 子对象的引用（¶1–¶3） |
| `key()` | 同上 | 对 `value_type` 中 `key_type` 成员的**非 const** 引用（¶4–¶6） |
| `mapped()` | 同上 | `mapped_type` 成员的引用（¶8–¶10） |
| `get_allocator()` | 同上 | `*alloc_`（¶11–¶13） |
| `operator bool` / `empty()` | — | `ptr_ != nullptr` / `ptr_ == nullptr`（¶14–¶15） |

全部 `Throws: Nothing`（观察器的前置条件违反仍是 UB）。

### `key()`：给 `const` 键开的后门（¶7）

!!! std
    *Remarks*: Modifying the key through the returned reference is permitted.

    经由返回的引用修改键是允许的。

`map` 的元素类型是 `pair<const Key, T>`，`first` 是 `const` 成员。按核心语言规则，修改一个 `const` 对象是 {{ub}}（[[dcl.type.cv]]），而且 `const` 完整对象的子对象被替换后，旧名字也不能透明地指向新对象（[[basic.life]]）。¶7 这句 *Remarks* 是一条**库层面的特许**：对通过节点句柄 `key()` 进行的修改，标准保证它是合法的——实现需要用编译器能接受的方式（例如上文提到的 `pair<Key, T>` 视图）来兑现这个承诺。`key()` 也是唯一**没有**标 `constexpr` 的观察器——可以推测，原因正在于这种"把 const 成员当作非 const 修改"的手法无法在常量求值中实现。

```cpp title="node-handle.cpp" run ok
#include <map>
#include <string>
#include <cassert>

int main() {
  std::map<int, std::string> m{{1, "one"}, {2, "two"}, {3, "three"}};
  const std::string* p = &m.at(2);

  auto nh = m.extract(2);                 // 节点离开 m，元素不移动
  assert(nh && nh.key() == 2);
  nh.key() = 20;                          // 合法：key() 返回非 const 引用（¶7）
  auto [pos, inserted, node] = m.insert(std::move(nh));
  assert(inserted && !node && pos->first == 20);
  assert(&pos->second == p);              // 同一个对象：没有拷贝或移动 std::string

  std::multimap<int, std::string> mm;
  mm.insert(m.extract(1));                // map 与 multimap 的节点兼容（表 75）
  assert(mm.count(1) == 1 && !m.contains(1));

  auto again = m.extract(3);
  m.emplace(3, "THREE");
  auto r = m.insert(std::move(again));    // 键冲突：插入失败，节点原样返还
  assert(!r.inserted && r.node.mapped() == "three" && r.position->second == "THREE");
}
```

`&pos->second == p` 说明元素在整个过程中从未移动——这正是节点句柄相对于"`erase` + 修改 + `insert`"的价值。

!!! warning "取出期间不要经由旧指针访问元素"
    上例中 `p` 在 `extract` 之后、`insert` 之前是**不能解引用**的：[[associative.reqmts]] ¶176 规定，元素归节点句柄所有期间经由先前的指针和引用访问它是 {{ub}}；元素被成功插入后，这些指针和引用又指向容器中的同一元素（本例在插入之后才比较 `p` 的值，不解引用）。

## 修改器（[container.node.modifiers]）

`swap(nh)`：

- `noexcept(POCS || is_always_equal)`；
- 前置条件：任一方为空，或 POCS 为真，或两个分配器相等（¶1）；
- 效果：交换 `ptr_`；若任一方为空或 POCS 为真，还交换 `alloc_`（¶2）。

空句柄"不含分配器"在这里起作用：与空句柄交换总是合法的，分配器跟着节点走。

## insert_return_type（[container.insert.return]）

¶1：**唯一键**的关联容器和无序容器有一个返回嵌套类型 `insert_return_type` 的 `insert(node_type&&)`；它是下面这个仅用于阐述的模板的特化：

```cpp
template<class Iterator, class NodeType>
struct insert-return-type {
  Iterator position;
  bool     inserted;
  NodeType node;
};
```

¶2：它恰好有这三个数据成员（按此顺序）和上面指定的特殊成员，没有基类，没有其他成员。所以它是聚合，可以用结构化绑定按 `position`、`inserted`、`node` 的顺序解包（上例的 `auto [pos, inserted, node]`）。

结合 [[associative.reqmts]] ¶87 / [[unord.req]] ¶118，三个字段的取值：

| 情形 | `inserted` | `position` | `node` |
|---|---|---|---|
| `nh` 为空 | `false` | `end()` | 空 |
| 插入成功 | `true` | 指向新元素 | 空 |
| 键已存在，插入失败 | `false` | 指向已有的等价元素 | `nh` 原来的值（元素没有丢失） |

等价键容器的 `insert(nh)` 总能成功，直接返回 `iterator`；带提示的 `insert(p, nh)` 对所有容器都返回 `iterator`，失败时 `nh` **保持不变**（¶97）。

## 思考题

!!! question "能否把一个 `std::map<int, std::string, std::less<>, A>` 的节点插进 `std::map<int, std::string, std::less<int>, A>`？插进 `std::unordered_map<int, std::string>` 呢？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

第一种可以：键类型、映射类型、分配器类型都相同，只有比较器不同，按表 75 属于兼容节点，`node_type` 是同一类型。插入时使用**目标**容器的比较器重新定位（可能因键冲突失败，节点通过 `insert_return_type::node` 返还）。第二种不行：有序与无序容器的节点结构不同，`node_type` 是不同的类型，`insert` 根本没有接受它的重载——编译错误。另外，即使类型兼容，运行时还要求两个容器的分配器**相等**（`insert(nh)` 的前置条件），否则是 UB。
</details>

## 小结

- 节点句柄是只能移动的单元素所有者；被移动后一定为空；空句柄不含分配器；析构会正常销毁元素。
- 兼容节点 = 同键类型、同映射类型、同分配器类型、同为有序或同为无序；比较器/哈希可以不同，唯一键与等价键可以互转。
- `key()` 返回非 const 引用，经由它修改键是标准特许的；用户特化 `pair<const Key, T>` 会使节点句柄操作 UB。
- 唯一键容器的 `insert(nh)` 返回 `{position, inserted, node}`；失败时元素回到 `node` 中，不会丢失。
