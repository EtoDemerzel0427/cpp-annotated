---
title: flat_map 与 flat_multimap
summary: 把键和值分别存进两个有序数组的关联容器：查找和遍历快，单点插入是线性的；迭代器解引用得到代理对象，插入可能使所有迭代器失效，抛异常后容器可能被清空。
status: done
covers: flat.map.syn, flat.map.overview, flat.map.defn, flat.map.cons, flat.map.cons.alloc, flat.map.capacity, flat.map.access, flat.map.modifiers, flat.map.erasure, flat.multimap, flat.multimap.overview, flat.multimap.defn, flat.multimap.cons, flat.multimap.cons.alloc, flat.multimap.erasure
related: container.adaptors, flat.set, associative.reqmts, associative, container.requirements, container.node, sequence.reqmts, vector, deque, allocator.uses, alg.sorting
tags: 标准库, 容器, 容器适配器, 关联容器, 异常安全
papers: P0429R9
since: c++23
updated: 2026-10-19
---

!!! tldr
    - `flat_map` 把键和值分别存在两个有序的序列容器里（默认是两个 `vector`）。查找是二分，遍历是线性扫描，单点插入和删除是线性时间。
    - 内存里没有 `pair<Key, T>` 对象，解引用迭代器得到的是代理 `pair<const Key&, T&>`。所以 `for (auto [k, v] : fm) v += "!";` 会修改容器，对 `std::map` 则不会。
    - 迭代器失效规则沿用底层容器：用 `vector` 时，任何插入都可能使所有迭代器、引用和指针失效。
    - 成员函数抛出异常后，标准只保证不变式恢复，容器可能被清空。
    - 传 `sorted_unique` 是向库保证数据已有序、无重复；数据不满足时是 UB。两个容器长度不同也是 UB。

## 两个数组上的 map

`std::map` 是一棵红黑树，每个元素占一个堆上节点，查找时沿着指针在内存里跳转。`std::flat_map`（{{c++23}}，[[P0429R9]]）提供几乎相同的接口，数据却放在两个有序数组里：

```
keys:   [ 1 | 3 | 7 | 9 | 12 ]      KeyContainer，默认 vector<Key>
values: [ a | b | c | d | e  ]      MappedContainer，默认 vector<T>
          第 i 个值属于第 i 个键
```

查找是对连续内存做一次二分，对缓存友好；遍历就是顺序扫描两个数组。代价是插入或删除一个元素时，后面的元素都要挪动一位。

`flat_map` 是一个**容器适配器**（[[g:container-adaptor]]）：它不自己管理存储，而是包装两个序列容器。标准把这一类叫做 flat container（[[g:flat-container]]）。底层容器可以换成 `deque`、`pmr::vector`、`inplace_vector`，也可以用 `extract()` 把两个数组整个取出来，处理完再放回去。

这种存储方式带来了一系列与 `std::map` 不同的规则：

| | `std::map` | `std::flat_map` |
|---|---|---|
| 解引用迭代器 | `pair<const Key, T>&` | `pair<const Key&, T&>`，一个代理 prvalue |
| 单点插入、删除 | O(log N) | O(N) |
| 插入后的迭代器 | 全部有效 | 按底层容器规则失效，`vector` 下可能全部失效 |
| 节点句柄 | `extract(key)`、`insert(node)` | 没有；`extract()` 取出的是两个整个的容器 |
| 分配器 | allocator-aware 容器 | 不是，没有 `allocator_type` |
| 单元素插入抛异常 | 没有效果（强保证） | 只保证不变式恢复，可能被清空 |

## 解引用得到的是代理（[flat.map.defn]）

键和值存在两个数组里，内存中根本没有一个 `pair<Key, T>` 对象可供引用。解引用迭代器时，实现只能当场构造一个由两个引用组成的 pair，作为 prvalue 返回。成员类型因此是：

```cpp
using value_type      = pair<key_type, mapped_type>;
using reference       = pair<const key_type&, mapped_type&>;
using const_reference = pair<const key_type&, const mapped_type&>;
```

第一个后果是不能用 `pair&` 去绑定 `*it`：

```cpp run title="flat-map-no-pair-ref.cpp" error
#include <flat_map>
#include <string>

int main() {
  std::flat_map<int, std::string> m{{1, "a"}};
  std::pair<const int, std::string>& r = *m.begin();  // error: 不能绑定到 pair<const int&, string&> 临时对象
  (void)r;
}
```

更隐蔽的是 range-for 里 `auto` 的含义变了。复制一个代理，复制的仍是两个引用：

```cpp run title="flat-map-auto-binding.cpp" ok
#include <flat_map>
#include <map>
#include <string>
#include <cassert>

int main() {
  std::flat_map<int, std::string> fm{{1, "a"}, {2, "b"}};
  for (auto [k, v] : fm) v += "!";        // 复制的是代理 pair<const int&, string&>，v 仍引用容器里的值
  assert(fm[1] == "a!");                  // 容器被修改了

  auto&& ref = *fm.begin();               // OK：延长临时代理的生命周期
  ref.second = "z";
  assert(fm[1] == "z");

  std::map<int, std::string> m{{1, "a"}};
  for (auto [k, v] : m) v += "!";         // 对 map，auto 复制出一个 pair，v 是副本
  assert(m[1] == "a");
}
```

同一行 `for (auto [k, v] : c) v += "!";`，对 `map` 不修改容器，对 `flat_map` 修改容器。从 `map` 迁移到 `flat_map` 时，这是最容易漏掉的差别。`it->second` 也需要特别处理：实现让 `operator->` 返回一个持有代理的小对象。

代理还解释了 [flat.map.overview] ¶1 里的一句措辞：

!!! std
    `flat_map` supports iterators that meet the *Cpp17InputIterator* requirements and model the `random_access_iterator` concept.

按 C++20 的迭代器概念，它是随机访问迭代器；按 C++17 风格的命名要求（*Cpp17ForwardIterator* 及以上），它只是输入迭代器，因为那些要求规定 `reference` 必须是真正的引用类型。所以 `std::ranges` 的算法把它当作随机访问迭代器，只看 Cpp17 要求的老算法严格来说只能把它当作输入迭代器。

类定义里的其他细节：

- `value_compare` 只比较 `.first`。它的构造函数是私有的，只能通过 `value_comp()` 获得。
- `struct containers { key_container_type keys; mapped_container_type values; };` 是 `extract()` 的返回类型。¶1 规定它只有这两个数据成员，没有基类，所以可以写 `auto [ks, vs] = std::move(m).extract();`。
- `keys()` 和 `values()` 返回底层容器的 `const&`，都是 `noexcept`。要把值数组交给只接受连续内存的接口，用 `m.values().data()` 即可。
- `size_type` 固定是 `size_t`；`flat_set` 的 `size_type` 却是 `KeyContainer::size_type`（[[flat.set]]）。
- 成员 *c*、*compare* 只用于说明（exposition only）。它们不像 `stack` 的 `protected: Container c;` 那样可以被派生类访问。

## 满足哪些要求（[flat.map.overview] ¶1–¶4）

¶1 `flat_map` 是唯一键的关联容器：每个键最多出现一次，根据键快速找到另一个类型 `T` 的值。

¶2 它满足容器（[[container.reqmts]]）、可逆容器（[[container.rev.reqmts]]）和可选容器要求（[[container.opt.reqmts]]，即 `<=>` 比较），也满足关联容器要求（[[associative.reqmts]]），但有三个例外：

- ¶2.1 不满足节点句柄（[[container.node]]）的要求；
- ¶2.2 不满足迭代器失效的要求；
- ¶2.3 插入或删除单个元素的操作是线性时间，带位置提示（hint）的版本也一样。

注 1 补充，`flat_map` 不满足分配器感知容器（[[g:allocator-aware-container]]）的附加要求。它没有 `allocator_type` 和 `get_allocator()`，复制和赋值时也不按 `propagate_on_container_*` 处理分配器，这些都交给两个底层容器各自处理。不过它仍然参与 uses-allocator 构造，见下文的分配器构造函数。

¶3 它支持关联容器要求中针对唯一键的 *a_uniq* 操作，不支持针对等价键的 *a_eq* 操作。`key_type` 是 `Key`，`value_type` 是 `pair<Key, T>`，不是 `std::map` 的 `pair<const Key, T>`。

¶4 本节只描述要求表里没有、或者需要补充语义的操作。`find`、`lower_bound`、`count` 等没有在这里出现的成员，语义以 [[associative.reqmts]] 为准。

## 不变式与异常（¶5–¶6）

¶5 `flat_map` 维护三条**不变式**：

- ¶5.1 键和值的个数相同；
- ¶5.2 键按比较对象有序；
- ¶5.3 值容器中偏移 `off` 处的值，属于键容器中偏移 `off` 处的键。

对唯一键的 `flat_map`，键还不能重复。这一点由构造函数去重，以及 `sorted_unique` 和 `replace` 的前提保证。

¶6 是 flat 容器家族特有的异常规定：

!!! std
    If any member function in [flat.map.defn] exits via an exception the invariants of the object argument are restored.

如果 [flat.map.defn] 中的成员函数以异常退出，`*this` 的不变式会被恢复；对移动构造和移动赋值，两个对象的不变式都会被恢复。注 2 说明，这可能导致 `flat_map` 被清空。

为什么不提供 `std::map` 那样的强保证？插入一个元素要在两个容器里各插入一次。如果键插入成功、值插入抛出，键容器就多了一个元素。要回到原状只能再把那个键删掉，而对 `vector` 来说，删除要移动后面的元素，移动本身也可能抛出。所以标准只承诺不变式成立，代价最低的恢复办法就是把两个容器都清空。

这条规定有两处措辞值得注意：

- object argument 指隐式对象实参，也就是 `*this`（[[over.match.funcs]]）。非成员函数 `erase_if` 不在其中，它有自己的规定（[flat.map.erasure] ¶5）。
- restored 只要求结果满足不变式，没有说保留了哪些元素。实现可以回滚，也可以清空，还可以只留下一部分。异常之后的内容对用户来说是未指明的。

libc++ 的单元素插入能回滚时就回滚，否则清空。下面两个程序只差在值类型能否复制：

<div class="compare" markdown="1">

```cpp run title="rollback.cpp" ok
#include <flat_map>
#include <cstdio>
#include <stdexcept>

struct Bomb {    // 复制可能抛出
  static inline bool armed = false;
  int v;
  Bomb(int x) : v(x) {}
  Bomb(const Bomb& o) : v(o.v) {
    if (armed)
      throw std::runtime_error("copy");
  }
  Bomb& operator=(const Bomb&)
    = default;
};

int main() {
  std::flat_map<int, Bomb> m;
  for (int i = 0; i < 4; ++i)
    m.try_emplace(i * 10, i);
  Bomb::armed = true;
  try {
    m.try_emplace(15, 99);
  } catch (const std::exception&) {
    // libc++: size = 4
    std::printf("size = %zu\n",
                m.size());
  }
}
```

```cpp run title="clear.cpp" ok
#include <flat_map>
#include <cstdio>
#include <stdexcept>

struct MoveOnly {  // 只能移动，移动可能抛出
  static inline bool armed = false;
  int v;
  MoveOnly(int x) : v(x) {}
  MoveOnly(MoveOnly&& o) : v(o.v) {
    if (armed)
      throw std::runtime_error("move");
  }
  MoveOnly& operator=(MoveOnly&&)
    = default;
};

int main() {
  std::flat_map<int, MoveOnly> m;
  for (int i = 0; i < 4; ++i)
    m.try_emplace(i * 10, i);
  MoveOnly::armed = true;
  try {
    m.try_emplace(15, 99);
  } catch (const std::exception&) {
    // libc++: size = 0
    std::printf("size = %zu\n",
                m.size());
  }
}
```

</div>

在中间插入要挪动已有的值，所以两段代码都会抛出。左边的值类型可以复制，`vector` 的单元素插入有强保证，libc++ 删掉刚插入的键，`m` 保持 4 个元素。右边的值类型只能移动且移动可能抛出，`vector` 给不出强保证，libc++ 只好清空。两种结果都符合 ¶6，换一个标准库实现，异常之后剩下几个元素可能不同。

移动也受 ¶6 约束：移动构造和移动赋值之后，被移走的对象也要满足不变式。`vector` 被移动后通常是空的，但标准只说它处于有效但未指明的状态。如果键容器被移空而值容器没有，被移走的 `flat_map` 就违反了 ¶5.1。libc++ 因此在移动构造函数里显式清空源对象。

## 底层容器（¶7–¶8）

¶7 任何满足序列容器要求（[[sequence.reqmts]]）的类型 `C` 都可以用作 `KeyContainer` 或 `MappedContainer`，只要 `C::iterator` 满足 *Cpp17RandomAccessIterator*，并且 `C::size` 和 `C::max_size` 不抛异常。标准点名了 [[vector]] 和 [[deque]]；注 3 提醒 [[vector.bool]] 不是序列容器，不能用。[[inplace.vector]] 满足要求，用它可以得到完全不分配堆内存的 `flat_map`。

`size` 不抛异常这一条大概是为 ¶6 服务的：恢复不变式时要比较两个容器的长度，这一步不能再抛出。

¶8 如果 `Key` 与 `KeyContainer::value_type` 不是同一类型，或者 `T` 与 `MappedContainer::value_type` 不是同一类型，程序{{ill-formed}}。

## sorted_unique 与两条 UB（¶9–¶11）

```cpp run title="sorted-unique-lie.cpp" ub
#include <flat_map>
#include <vector>
#include <cstdio>

int main() {
  std::vector<int> keys{3, 1, 2};               // 没有排序
  std::vector<int> vals{30, 10, 20};
  std::flat_map<int, int> m(std::sorted_unique, std::move(keys), std::move(vals));  // UB
  std::printf("contains(1) = %d\n", m.contains(1));
}
```

`std::sorted_unique` 是一个标签对象，类型是 `sorted_unique_t`（[[g:sorted-unique]]），在 `<flat_map>` 和 `<flat_set>` 里都有定义（[flat.map.syn]）。它的默认构造函数是 `explicit` 的，所以 `{}` 不会被隐式转换成这个标签。传入它就是告诉库：数据已经有序、没有重复，不必再排序和去重。作为回报，构造的复杂度降到常数或线性。

¶10 如果数据并不有序或者含有相等的元素，行为未定义：

!!! std
    The effect of calling a member function that takes a `sorted_unique_t` argument with a container, containers, or range that is not sorted with respect to `key_comp()`, or that contains equal elements, is undefined.

¶9 另一条 UB：用长度不同的键容器和值容器调用构造函数。

上面的程序在本机默认配置下输出 `contains(1) = 0`：二分查找在乱序数组上找不到确实存在的键。这两条都是普通的 {{ub}}，不是加固前置条件，但 libc++ 仍然会检查，只是档位不同：

| 违例 | 在哪些加固档位检查 |
|---|---|
| 键、值容器长度不同（¶9、`replace`） | fast、extensive、debug |
| `sorted_unique` 数据无序或有重复（¶10、`replace`） | 只有 debug，因为检查本身是 O(N) |

用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` 编译上面的程序，构造时就会终止，报告 key container 未排序或含重复。

¶11 `iterator` 和 `const_iterator` 满足 constexpr 迭代器的要求。整个 `flat_map` 在当前草案中都可以在常量求值中使用。

## 构造（[flat.map.cons]、[flat.map.cons.alloc]）

### 从两个容器构造

| 段落 | 构造函数 | 效果 | 复杂度 |
|---|---|---|---|
| ¶1–¶2 | `flat_map(key_cont, mapped_cont, comp = {})` | 移入两个容器，按 `value_comp()` 排序，再去掉重复的键 | 已有序时线性，否则 N log N |
| ¶3–¶4 | `flat_map(sorted_unique, key_cont, mapped_cont, comp = {})` | 只移入，不排序也不去重 | 常数 |

¶1 两个容器形参按值接收，再移入成员。所以 `flat_map(std::move(ks), std::move(vs))` 不复制任何元素。

¶1 的去重用 `ranges::unique` 作用于 `views::zip(keys, values)`，每组等价键保留排序后的第一个。排序没有要求稳定，所以输入中有重复键时，留下的是哪一个值是未指明的，不要依赖前面覆盖后面或者后面覆盖前面。

¶2 要求输入已经有序时必须是线性时间。实现要么先检查一遍是否有序，要么用对有序输入自适应的排序算法。

类定义中直接给出的其余构造函数都归结到插入操作：迭代器对构造调用 `insert(first, last)`，`sorted_unique` 迭代器对构造调用 `insert(sorted_unique, first, last)`，`from_range` 构造调用 `insert_range(rg)`，`initializer_list` 构造转给迭代器对版本。

### 带分配器的构造

[flat.map.cons.alloc] ¶1 只有 `uses_allocator_v<key_container_type, Alloc>` 和 `uses_allocator_v<mapped_container_type, Alloc>` 都为真时，这些构造函数才参与重载决议。¶2–¶6 它们的效果等同于对应的无分配器版本，只是两个底层容器都以 uses-allocator 构造（[[allocator.uses.construction]]）方式创建，同一个分配器分别交给两个容器。

¶5 `sorted_unique` 加分配器的版本复杂度是线性而不是常数，因为这里的容器形参是 `const&`，必须复制。

标准还为 `flat_map` 特化了 `uses_allocator`，两个底层容器都使用该分配器时为真。所以 `flat_map` 虽然不是分配器感知容器，放进 `pmr::vector` 时仍然能拿到外层的内存资源：

```cpp run title="flat-map-pmr.cpp" ok
#include <flat_map>
#include <memory_resource>
#include <vector>
#include <cassert>

template<class K, class V>
using pmr_flat_map = std::flat_map<K, V, std::less<K>, std::pmr::vector<K>, std::pmr::vector<V>>;

template<class T> concept has_allocator_type = requires { typename T::allocator_type; };
static_assert(!has_allocator_type<pmr_flat_map<int, int>>);          // 不是分配器感知容器
static_assert(std::uses_allocator_v<pmr_flat_map<int, int>,          // 但参与 uses-allocator 构造
                                    std::pmr::polymorphic_allocator<>>);

int main() {
  std::pmr::monotonic_buffer_resource arena;
  std::pmr::vector<pmr_flat_map<int, int>> outer(&arena);
  outer.emplace_back();                       // 外层 vector 把 arena 传给内层的两个容器
  outer[0][1] = 10;
  assert(outer[0].keys().get_allocator().resource() == &arena);
  assert(outer[0].values().get_allocator().resource() == &arena);
}
```

类定义后有十几条推导指引。从两个容器推导时，`Key` 和 `T` 取各自的 `value_type`，并保留容器类型；从迭代器对或 `initializer_list<pair<Key, T>>` 推导时，默认使用 `vector`。它们都受 [[container.adaptors]] 中推导指引通用规则的约束。

## 容量与访问（[flat.map.capacity]、[flat.map.access]）

[flat.map.capacity] ¶1 `size()` 返回键容器的 `size()`；¶2 `max_size()` 返回两个容器 `max_size()` 中较小的一个。

[flat.map.access]：

| 段落 | 成员 | 规定 |
|---|---|---|
| ¶1–¶2 | `operator[](const key_type&)`、`operator[](key_type&&)` | 等价于 `return try_emplace(x).first->second;` |
| ¶3–¶4 | `template<class K> operator[](K&&)` | 要求比较器透明（`Compare::is_transparent` 存在）；其余同上 |
| ¶5–¶7 | `at(const key_type&)` | 返回对应值的引用；不存在时抛 `out_of_range`；对数复杂度 |
| ¶8–¶12 | `template<class K> at(const K&)` | 同上，另要求比较器透明，且 `find(x)` 良构、行为有定义 |
| ¶13–¶16 | `lookup(x)` | 返回 `optional<mapped_type&>`：存在时引用 `find(x)->second`，否则为 `nullopt`；对数复杂度 |

`operator[]` 通过 `try_emplace` 定义，所以它要求 `mapped_type` 可以默认构造，而且键不存在时的一次 `m[k]` 就是一次 O(N) 的插入。

`lookup` 是较新加入草案的成员，`std::map` 同时获得了它。它利用 `optional<T&>`，省去了先 `find` 再和 `end()` 比较的写法。截至写作时，本机 libc++ 的 `flat_map` 还没有 `lookup`。

## 修改（[flat.map.modifiers]）

### 单元素插入

¶1–¶3 `emplace(args...)` 先用实参构造一个 `pair<key_type, mapped_type>` 对象 `t`。如果已经存在等价的键，`*this` 不变；否则等价于：

```cpp
auto key_it = ranges::upper_bound(c.keys, t.first, compare);
auto value_it = c.values.begin() + distance(c.keys.begin(), key_it);
c.keys.insert(key_it, std::move(t.first));
c.values.insert(value_it, std::move(t.second));
```

这段代码说清了复杂度：一次对数时间的二分，加上两次线性时间的中间插入。它也说明 `emplace` 即使键已存在也会先构造 `t`，想省掉这次构造就用 `try_emplace`。

¶4–¶5 `insert(P&&)` 和 `insert(hint, P&&)` 分别等价于 `emplace` 和 `emplace_hint`。按 ¶2.3，带 hint 的版本仍然是线性时间，hint 最多省掉一次二分。

¶16–¶19 `try_emplace(k, args...)`：如果已有等价的键，`*this` 和 `args...` 都不变，实参不会被移走；否则在 `upper_bound` 位置分别插入键和值。

¶20–¶24 是异构版本 `try_emplace(K&& k, args...)`，键可以是 `string_view` 这类与 `key_type` 不同的类型。约束有四条：比较器透明；`key_type` 能从 `K` 构造；`mapped_type` 能从 `args...` 构造；第一个重载中 `K` 不能转换成迭代器，以免和 `try_emplace(hint, ...)` 混淆。¶21 还有一条前置条件：

!!! std
    The conversion from `k` into `key_type` constructs an object `u`, for which `find(k) == find(u)` is true.

也就是说，异构键和它转换成的真正的键，在比较器看来必须是同一个位置。如果透明比较器对 `string_view` 和 `string` 的比较方式不一致，比如一个区分大小写、一个不区分，这里就是 {{ub}}。

¶25–¶33 `insert_or_assign(k, obj)`：如果存在键等价的元素 `e`，把 `std::forward<M>(obj)` 赋给 `e.second`；否则归结为 `try_emplace`。异构版本（¶29–¶33）的约束和前置条件与 `try_emplace` 相同。

### 批量插入

¶6–¶8 `insert(first, last)` 先把所有新元素追加到两个容器的末尾，然后对新加的部分按 `value_comp()` 排序，与原有部分合并成一个有序序列，最后用与构造函数相同的方式去重。

- ¶7 复杂度是 N + M log M，N 是原来的大小，M 是新元素的个数。逐个插入要 M·N，所以有一批元素时应该一次插入。
- ¶8 合并是原地进行的（in-place merge），可能分配内存。

新键与已有键重复时留下哪个值，条文没有明说，因为它没有规定合并时新旧元素谁在前。本机 libc++ 保留旧元素，与 `map::insert` 遇到已有键时不插入的行为一致。新元素之间的重复键保留哪一个，和构造函数一样取决于排序，是未指明的。

¶9–¶10 `insert(sorted_unique, first, last)` 的效果规定为等价于 `insert(first, last)`，只把复杂度改成线性（N 为操作之后的大小）。标签的作用只是允许实现跳过对新元素的排序，结果完全相同。

¶11–¶15 `insert_range(rg)` 和 `insert_range(sorted_unique, rg)` 与上面一一对应。

### extract 与 replace

¶35–¶36 `extract() &&` 返回 `std::move(c)`，也就是把两个底层容器整个移出去：

!!! std
    *Postconditions*: `*this` is emptied, even if the function exits via an exception.

它带 `&&` 限定，必须写 `std::move(m).extract()`，这样从字面上就能看出 `m` 的内容被拿走了。它和 `map::extract(key)` 取出一个节点句柄完全不同，`flat_map` 没有节点句柄。

¶37–¶38 `replace(key_cont&&, mapped_cont&&)` 把两个容器移动赋值进来。前置条件有三条：两个容器等长，键按 *compare* 有序，键没有重复。违反时是 {{ub}}，libc++ 的检查档位同上表。

两者配合，可以在 `flat_map` 外面用任意算法批量处理数据：

```cpp run title="flat-map-extract-replace.cpp" ok
#include <flat_map>
#include <algorithm>
#include <ranges>
#include <vector>
#include <cassert>

// 把两个数组取出来，在外面处理，再一次放回去
void scale_and_drop_small(std::flat_map<int, double>& m, double factor) {
  auto [keys, vals] = std::move(m).extract();     // m 现在为空（¶35）
  for (double& v : vals) v *= factor;
  auto z = std::views::zip(keys, vals);
  auto tail = std::ranges::remove_if(z, [](const auto& kv) { return std::get<1>(kv) < 1.0; });
  auto n = tail.begin() - z.begin();
  keys.erase(keys.begin() + n, keys.end());
  vals.erase(vals.begin() + n, vals.end());
  m.replace(std::move(keys), std::move(vals));     // remove_if 保持相对顺序，键仍有序、无重复
}

int main() {
  std::flat_map<int, double> m{{1, 0.5}, {2, 3.0}, {3, 0.1}, {4, 2.0}};
  scale_and_drop_small(m, 2.0);
  assert(m.size() == 3 && m[2] == 6.0 && !m.contains(3));
  assert(std::erase_if(m, [](const auto& kv) { return kv.first == 4; }) == 1);
}
```

### swap

¶34 `swap` 依次交换比较器、键容器、值容器。三者都不抛异常地可交换时，它是 `noexcept` 的。如果中途抛出，比如键容器换了、值容器没换，概述 ¶6 同样适用，libc++ 在这种情况下把两个 `flat_map` 都清空。

## erase_if（[flat.map.erasure]）

¶1 前置条件：`Key` 和 `T` 满足 *Cpp17MoveAssignable*。

¶2–¶4 对每个元素 `e`，以 `pair<const Key&, const T&>(e)` 调用谓词，删除使谓词为真的元素，返回删除的个数。谓词恰好调用 `c.size()` 次，拿到的是 const 引用，不能借机修改元素。

¶5 删除是稳定的（[[algorithm.stable]]），留下的元素保持原来的相对顺序。`erase_if` 是非成员函数，不受概述 ¶6 覆盖，所以这里单独规定：如果抛出异常，`c` 处于有效但未指明的状态。注 1 补充，`c` 仍满足不变式，但可能为空。

## 迭代器失效

¶2.2 说 `flat_map` 不满足关联容器的[[g:iterator-invalidation|迭代器失效]]要求。替代的规则在 [[container.adaptors]] 的通则里：`insert`、`emplace`、`erase` 对迭代器、引用和指针的影响，与底层容器的同名操作相同。对默认的 `vector`：

- 插入导致重新分配时，所有迭代器、引用和指针都失效；
- 没有重新分配时，插入点及之后的失效；
- 删除时，删除点及之后的失效。

`flat_map` 的迭代器内部是两个底层迭代器（libc++ 中 `flat_map<int, int>::iterator` 占 16 字节），其中任何一个失效，它就失效。最容易出事的是 `operator[]` 返回的引用：

```cpp run title="flat-map-dangling.cpp" ub
#include <flat_map>
#include <map>
#include <string>

int main() {
  std::map<int, std::string> m{{2, "two"}};
  std::string& a = m[2];
  m[1] = "one";              // OK：map 的插入不使引用失效
  a += "!";

  std::flat_map<int, std::string> fm{{2, "two"}};
  std::string& b = fm[2];
  fm[1] = "one";             // 在 values 头部插入：b 指向的存储被挪动或释放
  b += "!";                  // UB
}
```

AddressSanitizer 在本机报告 heap-use-after-free。即使事先 `reserve` 过、没有重新分配，`b` 也会指向另一个元素，因为原来的 `"two"` 被挪到了下一个位置。这同样是 UB，实际表现是程序不崩溃，却改错了数据。

## flat_multimap（[flat.multimap]）

`flat_multimap` 允许等价的键，结构与 `flat_map` 平行。它的概述各段与 `flat_map` 一一对应，区别如下：

| 段落 | `flat_multimap` | 与 `flat_map` 相比 |
|---|---|---|
| ¶1 | 支持等价键 | 唯一键改为等价键 |
| ¶3 | 支持 *a_eq*，不支持 *a_uniq* | 相反 |
| ¶4 | 除另有说明外，操作等价于 `flat_map` 的对应操作，只是不删除或替换键相等的元素 | 构造和批量插入不去重 |
| ¶10 | 用未排序的数据调用接收 `sorted_equivalent_t` 的成员是 UB | 只要求有序，允许相等元素 |

¶2、¶5–¶9、¶11 与 `flat_map` 相同：同样的三个例外，同样的不变式和异常规定，同样的底层容器要求和两条 UB 前提。

标签换成了 `std::sorted_equivalent`，名字本身就说明数据有序但可以有等价元素。`flat_multimap` 没有 `operator[]`、`at`、`lookup`、`try_emplace`、`insert_or_assign`，这些都依赖唯一键。它的 `emplace` 返回 `iterator` 而不是 `pair<iterator, bool>`，并且在 `upper_bound` 处插入，新元素排在等价键的末尾，与 `multimap` 一致。

[flat.multimap.cons] ¶1–¶2 两容器构造函数只排序不去重，复杂度同 `flat_map`；¶3–¶4 `sorted_equivalent` 版本是常数复杂度。[flat.multimap.cons.alloc] ¶1–¶6 与 `flat_map` 逐段对应，¶5 同样是线性。[flat.multimap.erasure] ¶1–¶5 与 `flat_map` 的 `erase_if` 相同。

## 什么时候用 flat_map

本机的粗略测量（Apple Silicon，`-O2`，`int` 到 `int`，100 万个随机键，只看数量级）：

| 操作 | `std::map` | `std::flat_map` |
|---|---|---|
| 构建：`map` 逐个插入，`flat_map` 从两个容器构造（排序一次） | ~930 ms | ~100 ms |
| 100 万次随机 `find` | ~860 ms | ~220 ms |
| 完整遍历求和 | ~140 ms | <1 ms |
| 10 万次随机单点插入 | ~60 ms | ~1600 ms |

读多写少、能批量构建、元素小的场合适合 `flat_map`。需要稳定的引用和迭代器、频繁单点插入删除、元素很大的场合适合 `map`。另外，`flat_map` 的键和值必须可以移动，因为插入要挪动元素；`map` 可以存放既不能复制也不能移动的类型。

!!! impl "libc++ 的实现"
    本机 libc++ 中 `__cpp_lib_flat_map` 为 `202511L`，`__cpp_lib_constexpr_flat_map` 为 `202502L`。迭代器的 `iterator_concept` 和 `iterator_category` 都是 `random_access_iterator_tag`，后者高于标准承诺的输入迭代器，libc++ 这样标注是为了避免老算法在运行期退化。移动构造后源对象被显式清空；`swap`、`erase` 和批量插入在异常路径上调用 `clear()`；单元素插入尽量回滚。`lookup` 尚未实现。

## 历史

!!! history
    - C++23：`flat_map` 和 `flat_multimap` 由 [[P0429R9]] 加入，`flat_set` 家族由 [[P1222R4]] 同期加入。
    - C++26：所有成员都成为 `constexpr`。
    - C++26 之后的草案：新增 `lookup` 成员，与 `std::map` 同步。

## 思考题

!!! question "思考题 1"
    对 `flat_map<int, int> m` 调用 `std::ranges::sort(m)` 能编译吗？

<details markdown="1">
<summary>答案</summary>

不能。`ranges::sort` 要求迭代器满足 `sortable`，其中包括通过迭代器交换和移动元素。`flat_map` 的 `reference` 是 `pair<const int&, int&>`，`.first` 是 const 引用，不能赋值，约束不满足，本机 Clang 报 no matching function。这正是想要的结果：键不能修改，否则会破坏有序不变式。确实需要重排时，先 `extract()` 出两个容器，对 `views::zip(keys, values)` 排序，再 `replace()` 回去。
</details>

!!! question "思考题 2"
    一个函数拿到 `const std::flat_map<K, V>& m`，把 `m.values().data()` 交给 C 库保存。之后对 `m` 做哪些操作会使这个指针失效？

<details markdown="1">
<summary>答案</summary>

`values()` 返回值容器的 const 引用，`data()` 的有效性按 `vector` 的规则判断。插入（包括键不存在时的 `operator[]`）、`erase`、`clear`、`extract`、`replace`、赋值、`swap` 都可能使它失效，或者让它指向不同的内容。此外，按 [flat.map.overview] ¶6，任何以异常退出的成员函数都可能清空 `m`，所以一次被捕获的异常之后，也不能假定指针仍然有效。
</details>

!!! question "思考题 3"
    `insert(sorted_unique, first, last)` 的效果为什么规定为等价于 `insert(first, last)`，而不是单独描述一遍？

<details markdown="1">
<summary>答案</summary>

前提满足时，新元素已经有序、无重复，对它们排序不会改变任何东西，两者的结果相同。写成等价于，就可以直接复用 [flat.map.modifiers] ¶6 对追加、合并、去重的描述，只需把复杂度从 N + M log M 收紧到线性，迫使实现跳过排序。如果数据其实无序，实现跳过排序后合并出的序列就不是有序的，不变式被破坏，之后的二分查找都可能出错，所以 ¶10 规定这是 UB。
</details>
