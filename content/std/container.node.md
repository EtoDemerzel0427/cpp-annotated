---
title: 节点句柄与 insert_return_type
summary: 节点句柄是一个只能移动的对象，拥有从 map、set 或无序容器中取出的单个元素，可以把它原样插进另一个兼容的容器。
status: done
covers: *, container.insert.return
related: associative.reqmts, unord.req, associative, unord, container.requirements.general, basic.life, allocator.traits
tags: 标准库, 容器, 节点句柄, extract, merge, C++17
since: c++17
papers: P0083R3
updated: 2026-10-19
---

!!! tldr
    - `extract` 把一个元素连同它所在的节点从关联容器里摘下来，交给节点句柄；`insert(std::move(nh))` 再把节点接进容器。元素本身从不复制或移动。
    - 只有键类型、映射类型和分配器类型都相同，并且同为有序或同为无序的容器之间才能交换节点；比较器、哈希可以不同，`map` 与 `multimap` 之间也可以。
    - 节点句柄的 `key()` 返回非 const 引用，标准明确允许通过它修改 `map` 的键。这是不重新分配就能改键的唯一办法。
    - 唯一键容器的 `insert(nh)` 返回 `{position, inserted, node}`；键冲突时元素回到 `node` 里，不会丢失。
    - 被移动后的句柄一定为空；空句柄不含分配器；丢弃一个非空句柄会正常销毁元素并释放节点。

## 不复制元素也能改 map 的键

`std::map` 的元素类型是 `pair<const Key, T>`，键是 const 的，因为直接改键会破坏树的顺序。C++17 之前，想改一个元素的键，只能先 `erase` 再 `insert`，元素要被复制或移动一次，节点也要释放再分配。C++17 加入的 `extract` 解决了这个问题（[[P0083R3]]）：

```cpp title="node-handle.cpp" run ok
#include <map>
#include <string>
#include <cassert>

int main() {
  std::map<int, std::string> m{{1, "one"}, {2, "two"}, {3, "three"}};
  const std::string* p = &m.at(2);

  auto nh = m.extract(2);          // 节点离开 m，元素留在原地
  assert(nh && nh.key() == 2);
  nh.key() = 20;                   // 允许：key() 返回非 const 引用
  auto [pos, inserted, node] = m.insert(std::move(nh));
  assert(inserted && !node && pos->first == 20);
  assert(&pos->second == p);       // 同一个 std::string 对象

  std::multimap<int, std::string> mm;
  mm.insert(m.extract(1));         // map 与 multimap 的节点兼容
  assert(mm.count(1) == 1 && !m.contains(1));

  auto again = m.extract(3);
  m.emplace(3, "THREE");
  auto r = m.insert(std::move(again));   // 键冲突：插入失败
  assert(!r.inserted && r.node.mapped() == "three");
  assert(r.position->second == "THREE");
}
```

`&pos->second == p` 说明整个过程中 `std::string` 对象没有动过：`extract` 只是把节点从树上摘下，`insert` 再把它挂回去。

**节点句柄**（[[g:node-handle]]）就是 `extract` 返回的那个对象。它只能移动，拥有一个节点和其中的元素。除了改键，它还能做两件以前做不到的事：在容器之间转移不可复制、甚至不可移动的元素，以及把元素暂时放在容器之外，之后再放回去。

!!! warning "元素在句柄里时，不要经由旧指针访问它"
    上例中 `p` 在 `extract` 之后、`insert` 之前不能解引用。[[associative.reqmts#176]] 规定，元素归节点句柄所有期间，经由先前得到的指针和引用访问它是 {{ub}}；元素被成功插入后，这些指针和引用重新指向容器中的这个元素。上例只在插入之后才比较 `p` 的值。

## 哪些容器之间能交换节点 [container.node.overview]

¶1 节点句柄接受关联容器（[[associative.reqmts]]）或无序关联容器（[[unord.req]]）中单个元素的所有权，可以把它转给另一个具有兼容节点的容器。节点兼容的容器，`node_type` 是同一个类型。表 75 列出了可以双向转移的组合：

| 容器 | 可以与之交换节点的容器 |
|---|---|
| `map<K, T, C1, A>` | `map<K, T, C2, A>`、`multimap<K, T, C2, A>` |
| `set<K, C1, A>` | `set<K, C2, A>`、`multiset<K, C2, A>` |
| `unordered_map<K, T, H1, E1, A>` | `unordered_map<K, T, H2, E2, A>`、`unordered_multimap<K, T, H2, E2, A>` |
| `unordered_set<K, H1, E1, A>` | `unordered_set<K, H2, E2, A>`、`unordered_multiset<K, H2, E2, A>` |

键类型、映射类型和分配器类型必须相同；比较器、哈希函数和相等谓词可以不同；唯一键与等价键之间可以转移。有序容器和无序容器之间不行，因为两者的节点结构不同，一个是树节点，一个是哈希链表节点。

```cpp title="node-type-identity.cpp" run ok
#include <functional>
#include <set>
#include <type_traits>
using A = std::set<int>;
using B = std::multiset<int, std::greater<>>;
static_assert(std::is_same_v<A::node_type, B::node_type>);
int main() {}
```

插入时按目标容器自己的比较器或哈希重新定位节点。类型兼容之外，运行时还要求两个容器的分配器相等，这是 `insert(nh)` 的前置条件（[[associative.reqmts#85]]）。

## 节点句柄的结构

¶3 标准用一个仅用于阐述的类模板 *node-handle* 描述节点句柄，每个容器的 `node_type` 是它的一个特化，具体名字未指明。它有两个数据成员：

- `ptr_`：指向容器节点的指针，类型是分配器 rebind 到节点类型之后的 `pointer`，可以是花式指针；
- `alloc_`：`optional<allocator_type>`。

¶2 非空的句柄含有一个分配器，等于取出元素时容器的分配器。空句柄不含分配器，`alloc_` 为 `nullopt`。

公开接口很小：默认构造（得到空句柄）、移动构造、移动赋值、析构，观察器 `value()`、`key()`、`mapped()`、`get_allocator()`、`explicit operator bool`、`empty()`，以及 `swap`。没有复制构造和复制赋值。`set` 系的句柄有 `value()` 没有 `key()`/`mapped()`，`map` 系的正好相反。除 `key()` 外，所有成员都是 `constexpr`。

## 移动与析构 [container.node.cons]

¶1 移动构造接管 `nh.ptr_`，移动构造 `alloc_`，然后把 `nh.ptr_` 置空、`nh.alloc_` 置为 `nullopt`。所以被移动的句柄一定是空的，不是有效但未指明的状态。

¶2–¶5 移动赋值先处理自己原有的节点：如果非空，用分配器的 `destroy` 销毁其中的元素，再释放节点。然后接管 `nh.ptr_`；如果自己原本为空，或者分配器的 `propagate_on_container_move_assignment`（POCMA）为真，就移动赋值 `alloc_`；最后把 `nh` 置空。它不抛异常。

前置条件是：自己为空，或 POCMA 为真，或两个分配器相等。理由在于，如果自己非空又不接管对方的分配器，将来就要用自己的分配器释放 `nh` 那个分配器分配的节点，两者必须相等。

### 析构 [container.node.dtor]

¶1 析构函数同样先销毁元素再释放节点。丢掉一个非空的句柄不会泄漏，元素会被正常销毁。

## 观察器与 key() [container.node.observers]

| 成员 | 前置条件 | 返回 |
|---|---|---|
| `value()` | 非空 | 节点中 `value_type` 对象的引用（¶1–¶3） |
| `key()` | 非空 | `value_type` 中键成员的非 const 引用（¶4–¶7） |
| `mapped()` | 非空 | `value_type` 中映射值成员的引用（¶8–¶10） |
| `get_allocator()` | 非空 | `*alloc_`（¶11–¶13） |
| `operator bool` / `empty()` | 无 | `ptr_ != nullptr` / `ptr_ == nullptr`（¶14–¶15） |

这些函数都不抛异常，但在空句柄上调用前四个违反前置条件，是 {{ub}}。

¶7 `key()` 的说明里有一句特别的话：

!!! std
    *Remarks*: Modifying the key through the returned reference is permitted.

按核心语言的规则，`pair<const Key, T>` 的 `first` 是 const 对象，修改它是 UB（[[dcl.type.cv]]）。这句 *Remarks* 是库给出的保证：通过节点句柄的 `key()` 修改键是合法的，实现要负责用编译器认可的方式兑现它。

概览部分的第 4 段（[[container.node.overview#4]]）透露了常见的实现方式：

!!! std
    If a user-defined specialization of pair exists for pair<const Key, T> or pair<Key, T>, ... the behavior of operations involving node handles is undefined.

实现需要把同一个对象一会儿当作 `pair<const Key, T>`，一会儿当作 `pair<Key, T>` 来访问，这要求两者布局相同。用户特化 `pair` 会破坏这个前提，所以标准把这种情况定为 UB。`key()` 是唯一没有标 `constexpr` 的观察器，一个合理的推测是，这种手法无法在常量求值中实现。

## swap [container.node.modifiers]

¶1 前置条件：任一方为空，或分配器的 `propagate_on_container_swap`（POCS）为真，或两个分配器相等。¶2 效果是交换 `ptr_`；任一方为空或 POCS 为真时，还交换 `alloc_`。异常规格是 `noexcept(POCS || is_always_equal)`。

空句柄不含分配器，在这里就有了用处：和空句柄交换总是合法的，分配器跟着节点走。

## insert_return_type [container.insert.return]

¶1 唯一键的关联容器和无序容器各有一个 `insert(node_type&&)`，返回嵌套类型 `insert_return_type`。它是下面这个仅用于阐述的模板的特化：

```cpp
template<class Iterator, class NodeType>
struct insert-return-type {
  Iterator position;
  bool     inserted;
  NodeType node;
};
```

¶2 它恰好有这三个数据成员，没有基类，也没有其他成员。所以它是聚合，可以像开头的例子那样用结构化绑定按 `position`、`inserted`、`node` 的顺序解包。

三个字段的取值由 [[associative.reqmts#87]] 和 [[unord.req#118]] 规定：

| 情形 | `inserted` | `position` | `node` |
|---|---|---|---|
| `nh` 为空 | `false` | `end()` | 空 |
| 插入成功 | `true` | 指向新元素 | 空 |
| 已有等价的键 | `false` | 指向已有的那个元素 | 原来的 `nh` |

等价键容器（`multimap` 等）的 `insert(nh)` 总能成功，直接返回 `iterator`。带位置提示的 `insert(p, nh)` 对所有容器都返回 `iterator`；插入失败时 `nh` 保持不变（[[associative.reqmts#97]]）。

## 思考题

!!! question "思考题"
    能否把 `std::map<int, std::string, std::less<>, A>` 的节点插进 `std::map<int, std::string, std::less<int>, A>`？插进 `std::unordered_map<int, std::string>` 呢？

<details markdown="1">
<summary>答案</summary>

第一种可以。键类型、映射类型、分配器类型都相同，只有比较器不同，按表 75 属于兼容节点，`node_type` 是同一个类型。插入时用目标容器的比较器定位，可能因为键冲突而失败，这时节点通过 `insert_return_type::node` 返还。运行时还要求两个容器的分配器相等，否则违反前置条件。

第二种不行。有序容器和无序容器的 `node_type` 是不同的类型，`unordered_map::insert` 没有接受它的重载，编译报错。
</details>
