---
title: flat_map 与 flat_multimap
summary: 用两个并行的有序序列容器实现的关联容器——键与值分开存放、迭代器解引用得到的是 pair 代理而非 pair&、单点插入线性、任何插入都可能使全部迭代器失效、抛异常后只保证"不变式恢复"（可能被清空）；sorted_unique 标签与 extract/replace 的前置条件
status: done
covers: flat.map.syn, flat.map.overview, flat.map.defn, flat.map.cons, flat.map.cons.alloc, flat.map.capacity, flat.map.access, flat.map.modifiers, flat.map.erasure, flat.multimap, flat.multimap.overview, flat.multimap.defn, flat.multimap.cons, flat.multimap.cons.alloc, flat.multimap.erasure
related: container.adaptors, flat.set, associative.reqmts, associative, container.requirements, container.node, sequence.reqmts, vector, deque, allocator.uses, alg.sorting
tags: 标准库, 容器, 容器适配器, 关联容器, 异常安全
papers: P0429R9
since: c++23
updated: 2026-10-18
---

`std::map` 是一棵红黑树：每个元素一个堆上节点，查找时沿着指针在内存里跳来跳去。`std::flat_map`（{{c++23}}，[[P0429R9]]）把同样的接口建在**两个有序数组**上：

```
keys:   [ 1 | 3 | 7 | 9 | 12 ]      ← KeyContainer，默认 vector<Key>
values: [ a | b | c | d | e  ]      ← MappedContainer，默认 vector<T>
           第 i 个值属于第 i 个键
```

查找是一次 `lower_bound`（对连续内存做二分，缓存友好），遍历就是线性扫描两个数组；代价是插入、删除一个元素要把后面的元素整体挪动——线性时间。它是一个**容器适配器**（[[g:container-adaptor]]），标准管它叫 *flat container*（[[g:flat-container]]）：你可以把底层容器换成 `deque`、`pmr::vector`、`static_vector` 风格的自定义类型，也可以用 `extract()` 把两个数组整体"借"出来操作再还回去。

这一设计带来了一连串与 `std::map` 截然不同的法律后果，本页逐一拆解：

| 话题 | `std::map` | `std::flat_map` |
|---|---|---|
| 解引用迭代器 | `pair<const Key, T>&` | `pair<const Key&, T&>`（**代理**，prvalue） |
| 单点插入/删除 | O(log N) | O(N)（[[flat.map#2]] ¶2.3） |
| 插入后迭代器 | 全部有效 | 按底层容器规则失效，`vector` 下可能**全部**失效 |
| 节点句柄 | `extract(key)`/`insert(node)` | 无（¶2.1）；`extract()` 是整体取出两个容器 |
| 分配器 | allocator-aware | **不是** allocator-aware，没有 `allocator_type`（¶2 注） |
| 异常 | 单元素插入强保证 | 只保证"不变式恢复"，**可能被清空**（¶6） |

阅读前置：[[associative.reqmts]]（`flat_map` 继承了它的绝大部分语义）、[[container.adaptors]]（适配器的通用规则，尤其是失效规则的委托）、[[alg.sorting]]（"关于比较器有序"的精确定义）。

## 它满足哪些要求、不满足哪些（[flat.map.overview] ¶1–¶4）

¶1：`flat_map` 提供唯一键的关联容器接口，"根据键快速检索另一类型 `T` 的值"。关于迭代器有一个精确到字的措辞：

!!! std
    `flat_map` supports iterators that meet the *Cpp17InputIterator* requirements and model the `random_access_iterator` concept.
    `flat_map` 的迭代器满足 *Cpp17InputIterator* 要求，并建模 `random_access_iterator` 概念。

注意这里的落差：C++20 概念层面它是随机访问迭代器，但"老式"（Cpp17）要求层面它只是**输入迭代器**。原因是 *Cpp17ForwardIterator* 要求 `reference` 是真正的引用类型（`T&` 或 `const T&`），而 `flat_map` 的 `reference` 是 `pair<const Key&, T&>`——一个按值返回的代理对象。C++20 迭代器概念放宽了这一限制，所以 `std::ranges::sort` 等算法可以接受它，而只认 Cpp17 要求的旧算法严格来说只能把它当输入迭代器。

¶2 列出它满足的要求：容器（[[container.reqmts]]）、可逆容器（[[container.rev.reqmts]]）、可选容器要求（[[container.opt.reqmts]]，即 `<`/`<=>` 比较），以及关联容器（[[associative.reqmts]]）——但有三个例外：

!!! std
    (2.1) it does not meet the requirements related to node handles, (2.2) it does not meet the requirements related to iterator invalidation, and (2.3) the time complexity of the operations that insert or erase a single element from the map is linear
    不满足节点句柄相关要求、不满足迭代器失效相关要求、单元素插入/删除（包括带位置提示的版本）的复杂度是线性的。

外加一个注：*A flat_map does not meet the additional requirements of an allocator-aware container*（[[g:allocator-aware-container]]）。它没有 `allocator_type`，没有 `get_allocator()`，构造函数不是"分配器感知容器"那一套语义（拷贝构造不调用 `select_on_container_copy_construction`，赋值不看 `propagate_on_container_*`）——这些全部由两个底层容器各自处理。但它仍然**参与 uses-allocator 构造**：标准为它特化了 `uses_allocator`，当且仅当两个底层容器都 `uses_allocator` 时为真（见下文 [flat.map.cons.alloc]）。

¶3：支持 [[associative.reqmts]] 中针对唯一键的 *a_uniq* 操作、不支持 *a_eq* 操作；`key_type` 是 `Key`，`value_type` 是 `pair<Key, T>`——注意**不是** `pair<const Key, T>`。¶4：本节只描述那些在要求表里没写、或者需要补充语义的操作；没在这里出现的成员（`find`、`lower_bound`、`count`……），语义一律以 [[associative.reqmts]] 为准。

## 不变式与异常安全（¶5–¶6）

¶5 列出三条**不变式**：

1. 键与值的数量相同；
2. 键关于比较对象有序；
3. 值容器中偏移 `off` 处的值，就是键容器中偏移 `off` 处的键所关联的值。

对唯一键的 `flat_map`，"有序"还隐含"无重复"（¶10 和 `replace` 的 *Preconditions* 都会单独提到"不含相等元素"）。

¶6 是整个 flat 家族最独特的一条规定：

!!! std
    If any member function in [flat.map.defn] exits via an exception the invariants of the object argument are restored. For the move constructor and move assignment operator, the invariants of both arguments are restored.
    若 [flat.map.defn] 中任何成员函数以异常退出，对象实参的不变式被恢复；对移动构造与移动赋值，两个实参的不变式都被恢复。

紧跟着一条注：*This can result in the flat_map being emptied.*

这是一个刻意的**弱化**。`std::map::insert` 对单元素插入提供强保证（失败则无效果），而 `flat_map` 做不到：插入一个元素要分别在两个容器中各插入一次，若键插入成功、值插入抛出，键容器就多了一个元素。要恢复原状只能再把那个键删掉——而删除本身（对 `vector` 来说是移动后续元素）也可能抛出。标准于是只承诺"不变式恢复"，最廉价的恢复手段就是把两个容器都清空。注意几个用词的分量：

- "**object argument**"指隐式对象实参，即 `*this`（[[over.match.funcs]]）。所以这条保证覆盖成员函数，**不覆盖**非成员的 `erase_if`——后者另有规定（[flat.map.erasure] ¶5，见下文）。
- "restored"只说结果满足不变式，没说保留了哪些元素。实现可以回滚、可以清空，也可以只删掉一部分——对用户来说，异常之后的内容是**未指明**的，唯一能依赖的是它仍是一个合法的 `flat_map`。

libc++ 的实现在可能时会尽力回滚，否则清空。以 `try_emplace` 为例（`__flat_map/utils.h` 中的 `__emplace_exact_pos`）：先在键容器中插入；若值容器的插入抛出，而值容器的单元素插入具有强保证（libc++ 内部 trait：元素类型不抛移动、或可拷贝插入），就把刚插入的键删掉；否则调用 `clear()`。下面两个程序只差在值类型能否拷贝：

```cpp run title="flat-map-exception-rollback.cpp" ok
#include <flat_map>
#include <cstdio>
#include <stdexcept>

struct Bomb {                        // 可拷贝；拷贝可能抛出
  static inline bool armed = false;
  int v;
  Bomb(int x) : v(x) {}
  Bomb(const Bomb& o) : v(o.v) { if (armed) throw std::runtime_error("copy"); }
  Bomb& operator=(const Bomb&) = default;
};

int main() {
  std::flat_map<int, Bomb> m;
  for (int i = 0; i < 4; ++i) m.try_emplace(i * 10, i);
  Bomb::armed = true;
  try {
    m.try_emplace(15, 99);           // 在 values 中段插入需要挪动既有元素 → 抛出
  } catch (const std::exception& e) {
    std::printf("caught: %s, size = %zu\n", e.what(), m.size());   // libc++: size = 4
  }
}
```

```cpp run title="flat-map-exception-clear.cpp" ok
#include <flat_map>
#include <cstdio>
#include <stdexcept>

struct MoveOnly {                    // 只能移动，且移动可能抛出
  static inline bool armed = false;
  int v;
  MoveOnly(int x) : v(x) {}
  MoveOnly(MoveOnly&& o) : v(o.v) { if (armed) throw std::runtime_error("move"); }
  MoveOnly& operator=(MoveOnly&&) = default;
};

int main() {
  std::flat_map<int, MoveOnly> m;
  for (int i = 0; i < 4; ++i) m.try_emplace(i * 10, i);
  MoveOnly::armed = true;
  try {
    m.try_emplace(15, 99);
  } catch (const std::exception& e) {
    std::printf("caught: %s, size = %zu\n", e.what(), m.size());   // libc++: size = 0
  }
}
```

两种结果**都**符合 ¶6。同一份代码换一个标准库实现，异常之后剩下几个元素完全可能不同——依赖异常后的内容就是依赖实现细节。

!!! warning "移动之后源对象是空的——这是 libc++ 的选择，也是 ¶6 的推论"
    ¶6 要求移动构造/移动赋值之后**两个**实参的不变式都成立。`vector` 被移动后通常为空，但标准只说它处于"有效但未指明"状态；若键容器被掏空而值容器没有（比如二者类型不同），源 `flat_map` 的不变式 1 就被破坏了。libc++ 因此在移动构造函数体里显式调用 `__other.clear()`，异常路径上也清空源对象。

## 底层容器的要求（¶7–¶8）

¶7：任何满足**序列容器要求**（[[sequence.reqmts]]）的类型 `C` 都可以用作 `KeyContainer`/`MappedContainer`，只要：

- `C::iterator` 满足 *Cpp17RandomAccessIterator*；
- `C::size` 与 `C::max_size` 不以异常退出。

特别点名 [[vector]] 与 [[deque]]；注 3 提醒 [[vector.bool]] **不是**序列容器，不能用。[[inplace.vector]] 满足要求，可以得到一个完全不用堆内存的 `flat_map`。

第二条是为 ¶6 服务的：恢复不变式时实现需要比较两个容器的大小，这一步不能再抛异常。

¶8 是硬性规定：`Key` 与 `KeyContainer::value_type`、`T` 与 `MappedContainer::value_type` 不同则程序 {{ill-formed}}。对比经典适配器只用了一句 "shall"（[[container.adaptors]]），这里直接写明了需要诊断。

## 两条 UB 前提与加固（¶9–¶10）

!!! std
    The effect of calling a member function that takes a `sorted_unique_t` argument with a container, containers, or range that is not sorted with respect to `key_comp()`, or that contains equal elements, is undefined.
    以未按 `key_comp()` 排序、或含有相等元素的容器/范围调用接收 `sorted_unique_t` 的成员函数，行为未定义。

`sorted_unique_t` 是一个**标签类型**（[[g:sorted-unique]]），定义在 `<flat_map>` 与 `<flat_set>` 两个头文件中（[flat.map.syn]），其默认构造函数是 `explicit` 的——防止 `{}` 被隐式转换成标签。传入 `std::sorted_unique` 就是向库**保证**"我给的数据已经有序且无重复，别再排序/去重了"，换来常数或线性的复杂度。

¶9 是另一条：以**大小不同**的键容器和值容器调用构造函数，行为未定义。

两条都是普通的 {{ub}}，不是 C++26 意义上的加固前置条件。但 libc++ 仍然选择检查它们，只是档位不同：

| 违例 | libc++ 宏 | 生效的加固档位 |
|---|---|---|
| 键/值容器大小不一致（¶9、`replace`） | `_LIBCPP_ASSERT_VALID_INPUT_RANGE` | `fast`、`extensive`、`debug` |
| `sorted_unique` 数据未排序或有重复（¶10、`replace`） | `_LIBCPP_ASSERT_SEMANTIC_REQUIREMENT` | 仅 `debug`（检查本身是 O(N)） |

```cpp run title="sorted-unique-lie.cpp" ub
#include <flat_map>
#include <vector>
#include <cstdio>

int main() {
  std::vector<int> keys{3, 1, 2};               // 没排序！
  std::vector<int> vals{30, 10, 20};
  std::flat_map<int, int> m(std::sorted_unique, std::move(keys), std::move(vals));  // UB
  std::printf("contains(1) = %d\n", m.contains(1));
}
```

本机实测：不开加固或开 `_LIBCPP_HARDENING_MODE_FAST`/`EXTENSIVE` 时，程序输出 `contains(1) = 0`——二分查找在乱序数组上找不到明明存在的键；以 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` 编译则在构造时终止，并报告 "Either the key container is not sorted or it contains duplicates"。

¶11：`iterator` 与 `const_iterator` 满足 constexpr 迭代器要求——整个 `flat_map` 在当前草案中是 `constexpr` 的（C++26 起）。

## 类型定义：代理引用（[flat.map.defn]）

成员类型里最值得细看的几行：

```cpp
using value_type      = pair<key_type, mapped_type>;
using reference       = pair<const key_type&, mapped_type&>;
using const_reference = pair<const key_type&, const mapped_type&>;
using size_type       = size_t;
using iterator        = implementation-defined;
```

由于键和值存在两个不同的数组里，内存中**根本没有**一个 `pair<Key, T>` 对象可供引用。解引用迭代器只能现场造一个"两个引用组成的 pair"作为 prvalue 返回。由此产生的后果：

```cpp run title="flat-map-no-pair-ref.cpp" error
#include <flat_map>
#include <string>

int main() {
  std::flat_map<int, std::string> m{{1, "a"}};
  std::pair<const int, std::string>& r = *m.begin();  // error: 无法绑定到 pair<const int&, string&> 临时对象
  (void)r;
}
```

更隐蔽的是 range-for 中 `auto` 的含义变了：

```cpp run title="flat-map-auto-binding.cpp" ok
#include <flat_map>
#include <map>
#include <string>
#include <cassert>

int main() {
  std::flat_map<int, std::string> fm{{1, "a"}, {2, "b"}};
  for (auto [k, v] : fm) v += "!";        // auto 拷贝的是代理 pair<const int&, string&>，v 仍是 string&
  assert(fm[1] == "a!");                  // 容器里的元素被修改了！

  auto&& ref = *fm.begin();               // OK：绑定并延长临时代理的生命周期
  ref.second = "z";
  assert(fm[1] == "z");

  std::map<int, std::string> m{{1, "a"}};
  for (auto [k, v] : m) v += "!";         // 对 map，auto 拷贝出一个 pair，v 是副本
  assert(m[1] == "a");
}
```

同样的代码 `for (auto [k, v] : c) v += "!";`，对 `map` 不修改容器，对 `flat_map` 修改容器——这是从 `map` 迁移到 `flat_map` 时最容易漏掉的语义差别。`->` 运算符也需要特殊处理：实现返回一个持有代理对象的"箭头代理"，使 `it->second` 能工作（libc++ 的 `__key_value_iterator::__arrow_proxy`）。

其他定义细节：

- `value_compare` 只比较 `.first`，其构造函数是 exposition-only 的私有成员，用户只能通过 `value_comp()` 获得。
- `struct containers { key_container_type keys; mapped_container_type values; };` 是 `extract()` 的返回类型。¶1 规定它**只有**这两个数据成员和隐式声明的特殊成员，没有基类——所以它是聚合，可以用结构化绑定 `auto [ks, vs] = std::move(m).extract();`。
- `keys()` 与 `values()` 返回底层容器的 `const&`，`noexcept`——这是把 `flat_map` 当作只读数组视图交给其他 API 的正规途径（例如把 `values()` 直接交给 SIMD 代码）。
- `size_type` 固定是 `size_t`，而 `flat_set` 的 `size_type` 却是 `KeyContainer::size_type`（[[flat.set]]）——两者不对称。
- 私有的 *c*、*compare* 和 *key-equiv* 都是 exposition-only：与 `stack` 的 `protected: Container c;` 不同，派生类**不能**依赖它们。

## 构造函数（[flat.map.cons]、[flat.map.cons.alloc]）

### 从两个容器构造（[flat.map.cons] ¶1–¶4）

| 段落 | 签名 | 效果 | 复杂度 |
|---|---|---|---|
| ¶1–¶2 | `flat_map(key_container_type, mapped_container_type, const key_compare& = key_compare())` | 移入两个容器 → 按 `value_comp()` 排序 → 用 `ranges::unique` 在 `views::zip(keys, values)` 上去重，保留每组等价键的**第一个** | 已有序则 O(N)，否则 O(N log N) |
| ¶3–¶4 | `flat_map(sorted_unique_t, key_container_type, mapped_container_type, const key_compare& = ...)` | 只移入，不排序不去重 | 常数 |

几个值得推敲的点：

- 参数是**按值**接收的：传左值会拷贝，传右值会移动，之后在内部 `std::move` 进成员。所以 `flat_map(std::move(ks), std::move(vs))` 不产生任何元素拷贝。
- 排序没有说"稳定"，所以存在重复键时，¶1 去重后**留下哪一个值是未指明的**（排序可能打乱等价键的相对顺序，"第一个"指的是排序后的第一个）。不要依赖"前面的覆盖后面的"或反过来。
- ¶2 的 "linear if already sorted" 是一条对实现的硬约束：输入已有序时必须做到线性，实现要么先检查一遍，要么使用对有序输入自适应的排序算法。

类定义中内联给出的其余构造函数都归约到 `insert`：迭代器对构造是 `insert(first, last)`，`sorted_unique` 迭代器对构造是 `insert(sorted_unique, first, last)`，`from_range` 构造是 `insert_range(rg)`，`initializer_list` 构造转到迭代器对版本。

### 带分配器的构造（[flat.map.cons.alloc] ¶1–¶6）

¶1：只有 `uses_allocator_v<key_container_type, Alloc>` **与** `uses_allocator_v<mapped_container_type, Alloc>` 都为真时，这些构造函数才参与重载决议。¶2–¶6：效果等价于对应的无分配器版本，只是 *c*.keys 与 *c*.values 以 **uses-allocator 构造**（[[allocator.uses.construction]]）创建——同一个分配器被分别交给两个容器。¶5 有个细节：`sorted_unique` 加分配器版本的复杂度是"线性"而不是"常数"，因为参数是 `const&`，必须拷贝。

```cpp run title="flat-map-pmr.cpp" ok
#include <flat_map>
#include <memory_resource>
#include <vector>
#include <cassert>

template<class K, class V>
using pmr_flat_map = std::flat_map<K, V, std::less<K>, std::pmr::vector<K>, std::pmr::vector<V>>;

template<class T> concept has_allocator_type = requires { typename T::allocator_type; };
static_assert(!has_allocator_type<pmr_flat_map<int, int>>);          // 不是 allocator-aware 容器
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

### 推导指引

类定义后有十几条推导指引，规律是：两个容器 → 从各自的 `value_type` 推出 `Key`/`T`，并保留容器类型；迭代器对 / `initializer_list<pair<Key, T>>` → 默认用 `vector`；`from_range` 加分配器 → 用 *alloc-rebind* 把一个分配器分别 rebind 给 `vector<Key>` 与 `vector<T>`。它们都受 [[container.adaptors]] 中 [container.adaptors.general] ¶6 的过滤规则约束，例如 ¶6.7 要求 `Compare` 能比较两个 `KeyContainer::value_type`。

## 容量与访问（[flat.map.capacity]、[flat.map.access]）

[flat.map.capacity]：¶1 `size()` 返回 *c*.keys.size()；¶2 `max_size()` 返回两个容器 `max_size()` 的较小者。

[flat.map.access]：

| 段落 | 成员 | 规定 |
|---|---|---|
| ¶1–¶2 | `operator[](const key_type&)` / `(key_type&&)` | 等价于 `return try_emplace(x).first->second;` |
| ¶3–¶4 | `template<class K> operator[](K&&)` | *Constraints*：`Compare::is_transparent` 有效；等价于 `try_emplace(std::forward<K>(x))` |
| ¶5–¶7 | `at(const key_type&)` | 返回对应值的引用；不存在则抛 `out_of_range`；对数复杂度 |
| ¶8–¶12 | `template<class K> at(const K&)` | 同上，外加透明比较器约束与"`find(x)` 良构且行为良定义"的前置条件 |
| ¶13–¶16 | `lookup(x)` | 返回 `optional<mapped_type&>`：存在则为 `find(x)->second`，否则 `nullopt`；对数复杂度 |

`lookup` 是较新加入草案的成员（`std::map` 同步获得），利用了 C++26 的 `optional<T&>`，填补了"查一下、找不到就算了"这一最常见需求长期需要 `find` + 比较 `end()` 的空白。截至本文编写时（Homebrew clang 23.1.3 + libc++），libc++ 的 `flat_map` 尚未提供 `lookup`。

`operator[]` 通过 `try_emplace` 定义，意味着它要求 `mapped_type` 可默认构造，并且一次缺失键的 `m[k]` 就是一次 O(N) 的插入。

## 修改操作（[flat.map.modifiers]）

### 单元素：emplace、insert、try_emplace、insert_or_assign

¶1–¶3 `emplace(args...)`：*Constraints* 是 `is_constructible_v<pair<key_type, mapped_type>, Args...>`。**先**用实参构造一个 `pair` 对象 `t`；若已存在等价键，`*this` 不变；否则等价于：

```cpp
auto key_it = ranges::upper_bound(c.keys, t.first, compare);
auto value_it = c.values.begin() + distance(c.keys.begin(), key_it);
c.keys.insert(key_it, std::move(t.first));
c.values.insert(value_it, std::move(t.second));
```

这段"as if"代码把复杂度说得明明白白：一次对数时间的二分，加上两次线性时间的中段插入。也说明 `emplace` 即使键已存在也会**先构造 `t`**——想避免这次构造，就用 `try_emplace`。

¶4–¶5：`insert(P&&)` 与 `insert(hint, P&&)` 分别等价于 `emplace`/`emplace_hint`。注意带 hint 的版本复杂度依然是线性（[[flat.map#2]] ¶2.3 明确把"take an insertion position iterator"的操作也包括在内），hint 最多省掉一次二分。

¶16–¶19 `try_emplace(k, args...)`：*Constraints* `is_constructible_v<mapped_type, Args...>`；若已有等价键，`*this` **和 `args...` 都不变**（不会被移走）；否则在 `upper_bound` 位置分别插入键和 `emplace` 值。¶20–¶24 是异构版本 `try_emplace(K&& k, ...)`，四条 *Constraints*（透明比较器、`key_type` 可从 `K` 构造、`mapped_type` 可从 `Args` 构造、第一个重载中 `K` 不能转换为迭代器——防止 `try_emplace(hint, ...)` 的歧义），以及一条耐人寻味的 *Preconditions*（¶21）：

!!! std
    The conversion from `k` into `key_type` constructs an object `u`, for which `find(k) == find(u)` is true.
    从 `k` 转换得到的 `key_type` 对象 `u` 必须满足 `find(k) == find(u)`。

即：异构键与它转换成的真正键必须"在比较器眼中是同一个位置"。若 `string_view` 与 `string` 的透明比较器实现不一致（例如一个大小写敏感、一个不敏感），这里就是 {{ub}}。

¶25–¶33 `insert_or_assign(k, obj)`：若存在等价键的元素 `e`，把 `std::forward<M>(obj)` 赋给 `e.second`；否则归约为 `try_emplace`。异构版本（¶29–¶33）有同样的 *Constraints*/*Preconditions* 结构。

### 批量插入：排序 + 合并 + 去重

¶6–¶8 `insert(first, last)`：先把所有新元素**追加**到两个容器尾部，然后对新追加的部分按 `value_comp()` 排序，与原有的有序部分合并成一个有序序列，最后用与构造函数相同的 `zip` + `unique` 代码去重。

- ¶7 *Complexity*：N + M log M（N 为原大小，M 为新元素个数）。对比逐个 `insert` 的 M·N，批量插入要快得多——这是使用 `flat_map` 的第一条性能守则：**能批量就批量**。
- ¶8 *Remarks*：由于执行原地合并（`inplace_merge`），可能分配内存。

去重保留每组等价键的第一个，但条文没有规定合并时新旧元素谁排在前面，所以新键与已有键冲突时留下哪个值，严格按条文并不确定；libc++ 实测保留**旧元素**（与 `map::insert` 的"已存在则不插入"一致）。新元素之间的重复键保留哪一个，与构造函数一样取决于排序，未指明。

¶9–¶10 `insert(sorted_unique, first, last)`：*Effects* 竟然是"等价于 `insert(first, last)`"，只有 *Complexity* 改为"线性（N 为操作**之后**的大小）"。也就是说标签只是允许实现跳过对新元素的排序，结果语义完全相同。

¶11–¶15 `insert_range(rg)` 与 `insert_range(sorted_unique, rg)` 与上面一一对应，只是用 `ranges::for_each` 逐个追加。

### extract 与 replace：把底层容器借出去

¶35–¶36 `extract() &&`：

!!! std
    *Postconditions*: `*this` is emptied, even if the function exits via an exception.
    后置条件：`*this` 被清空，即使函数以异常退出。

返回 `std::move(c)`。注意它是 **`&&` 限定**的：必须写 `std::move(m).extract()`，语法上就提醒你"`m` 的内容被拿走了"。与 `map::extract(key)`（取出一个节点句柄）完全是两回事——`flat_map` 不满足节点句柄要求（¶2.1）。

¶37–¶38 `replace(key_cont&&, mapped_cont&&)`：*Preconditions* 三条——两容器等长、键关于 *compare* 有序、键无重复；效果是直接移动赋值。违反前置条件是 {{ub}}，libc++ 的检查档位同上表。

二者配合，构成 flat 容器最强大的使用模式：

```cpp run title="flat-map-extract-replace.cpp" ok
#include <flat_map>
#include <algorithm>
#include <ranges>
#include <vector>
#include <cassert>

// 批量更新：把两个数组借出来，在外面用任意算法处理，再一次性还回去
void scale_and_drop_small(std::flat_map<int, double>& m, double factor) {
  auto [keys, vals] = std::move(m).extract();     // m 现在为空（¶35 的后置条件）
  for (double& v : vals) v *= factor;
  auto z = std::views::zip(keys, vals);
  auto tail = std::ranges::remove_if(z, [](const auto& kv) { return std::get<1>(kv) < 1.0; });
  auto n = tail.begin() - z.begin();
  keys.erase(keys.begin() + n, keys.end());
  vals.erase(vals.begin() + n, vals.end());
  m.replace(std::move(keys), std::move(vals));     // remove_if 稳定，键仍有序无重复
}

int main() {
  std::flat_map<int, double> m{{1, 0.5}, {2, 3.0}, {3, 0.1}, {4, 2.0}};
  scale_and_drop_small(m, 2.0);
  assert(m.size() == 3 && m[2] == 6.0 && !m.contains(3));
  assert(std::erase_if(m, [](const auto& kv) { return kv.first == 4; }) == 1);
}
```

### swap 与 clear

¶34 `swap`：依次 `ranges::swap` 比较器、键容器、值容器；`noexcept` 当且仅当三者都不抛地可交换。若中途抛出（比如键容器换了、值容器没换），¶6 再次登场——libc++ 在异常路径上把**两个** `flat_map` 都清空。`clear()` 无条件 `noexcept`（序列容器的 `clear` 不抛）。

## 删除与 erase_if（[flat.map.erasure]）

| 段落 | 规定 |
|---|---|
| ¶1 | *Preconditions*：`Key` 和 `T` 满足 *Cpp17MoveAssignable* |
| ¶2 | 对每个元素 `e`，以 `pair<const Key&, const T&>(e)` 调用谓词，删除使其为真者 |
| ¶3 | 返回删除个数 |
| ¶4 | 恰好调用谓词 `c.size()` 次 |
| ¶5 | 稳定（[[algorithm.stable]]）；若以异常退出，`c` 处于"有效但未指明"状态——注：仍满足不变式，但可能为空 |

`erase_if` 是非成员函数，不受 ¶6 覆盖，所以 ¶5 单独补上了异常规定，措辞也换成了"valid but unspecified"。谓词拿到的是 `const` 引用组成的 pair，不能借机修改元素。

## 迭代器失效：一切以底层容器为准

[[g:iterator-invalidation|迭代器失效]]方面，[flat.map.overview] ¶2.2 宣布 `flat_map` 不满足关联容器的失效要求，替代规则是 [[container.adaptors]] 中的 [container.adaptors.general] ¶5：`insert`、`emplace`、`erase` 对迭代器/引用/指针的影响与底层容器的同名操作相同。对默认的 `vector`：

- 插入导致重新分配 → **所有**迭代器、引用、指针失效；
- 未重新分配 → 插入点及之后的失效（插入点之前的仍有效，且仍指向原来的元素）；
- 删除 → 删除点及之后的失效。

`flat_map` 的迭代器内部是一对底层迭代器（libc++ 中 `sizeof(flat_map<int,int>::iterator)` 为 16 字节），任意一个失效它就失效。最危险的是 `operator[]` 返回的引用：

```cpp run title="flat-map-dangling.cpp" ub
#include <flat_map>
#include <map>
#include <string>

int main() {
  std::map<int, std::string> m{{2, "two"}};
  std::string& a = m[2];
  m[1] = "one";              // OK：map 插入不使任何引用失效
  a += "!";

  std::flat_map<int, std::string> fm{{2, "two"}};
  std::string& b = fm[2];
  fm[1] = "one";             // values 在头部插入：b 指向被挪动或被释放的存储
  b += "!";                  // UB
}
```

AddressSanitizer 在本机报告 `heap-use-after-free`。即使没有重新分配（例如事先 `reserve` 过），`b` 也会指向**另一个元素**（原来的 `"two"` 被挪到了下一个槽位）——形式上仍是 UB（插入点及之后的引用已失效），实践中不崩溃，但静默地改错了数据。

## flat_multimap（[flat.multimap]）

`flat_multimap` 是允许等价键的版本，结构与 `flat_map` 完全平行。差异集中在概述里：

| 段落 | `flat_multimap` 的规定 | 与 `flat_map` 的差别 |
|---|---|---|
| ¶1 | 支持等价键；迭代器满足 *Cpp17InputIterator* 并建模 `random_access_iterator` | 唯一键 → 等价键 |
| ¶2 | 同样的三条例外与"非 allocator-aware"注 | 相同 |
| ¶3 | 支持 *a_eq* 操作、不支持 *a_uniq* | 相反 |
| ¶4 | 除另有说明外，操作等价于 `flat_map` 的对应操作，**只是不删除或替换具有相等键的元素** | 构造与批量插入不去重 |
| ¶5–¶6 | 同样的三条不变式与"异常后恢复不变式"规定 | 相同 |
| ¶7–¶9 | 同样的底层容器要求、类型一致性、容器等长前提 | 相同 |
| ¶10 | 以**未排序**的数据调用接收 `sorted_equivalent_t` 的成员是 UB | 只要求有序，允许相等元素 |
| ¶11 | constexpr 迭代器 | 相同 |

标签换成了 `sorted_equivalent_t`/`std::sorted_equivalent`，名字本身就说明了"有序、但可以有等价元素"。接口上 `flat_multimap` **没有** `operator[]`、`at`、`lookup`、`try_emplace`、`insert_or_assign`（这些都是唯一键语义），`emplace` 返回 `iterator` 而非 `pair<iterator, bool>`。按 ¶4 的"等价于 `flat_map`"推理，`emplace` 也是在 `upper_bound` 处插入，即新元素排在等价键组的**末尾**——与 `multimap` 的 [[associative.reqmts]] 规定一致。

[flat.multimap.cons] ¶1–¶2：两容器构造函数排序但**不去重**，复杂度同 `flat_map`；¶3–¶4：`sorted_equivalent` 版本常数复杂度。[flat.multimap.cons.alloc] ¶1–¶6 与 `flat_map` 逐段对应（¶5 同样是"线性"）。[flat.multimap.erasure] ¶1–¶5 与 `flat_map` 的 `erase_if` 一字不差。

## 与 std::map 的取舍

本机粗测（Apple Silicon，`-O2`，`int → int`，100 万个随机键，仅供量级参考）：

| 操作 | `std::map` | `std::flat_map` |
|---|---|---|
| 构建：`map` 逐个插入 vs `flat_map` 两容器构造（一次排序） | ~930 ms | ~100 ms |
| 100 万次随机 `find` | ~860 ms | ~220 ms |
| 完整遍历求和 | ~140 ms | <1 ms |
| 10 万次随机**单点**插入 | ~60 ms | ~1600 ms |

`sizeof(std::flat_map<int,int>)` 为 48 字节（两个 `vector`），`std::map<int,int>` 为 24 字节；但 `map` 每个元素还要额外承担约 32 字节的节点开销加上分配器元数据，`flat_map` 每个元素只多 `vector` 的冗余容量。

经验法则：**读多写少、可以批量构建、元素小**——选 `flat_map`；需要稳定的引用/迭代器、频繁单点插入删除、元素很大或不可移动——选 `map`。还有一个容易被忽略的约束：`flat_map` 的键和值类型必须**可移动**（插入要挪动元素），而 `map` 可以存放既不可拷贝也不可移动的类型（`emplace` 后原地不动）。

## libc++ 实现笔记

截至 Homebrew clang 23.1.3 附带的 libc++：

- `__cpp_lib_flat_map` 为 `202511L`，`__cpp_lib_constexpr_flat_map` 为 `202502L`：`flat_map` 可在常量表达式中使用。
- 迭代器类型 `__key_value_iterator`：`iterator_concept` 为 `random_access_iterator_tag`；`iterator_category` **也**设为 `random_access_iterator_tag`——源码注释承认它只满足 *Cpp17InputIterator*，但为避免 Cpp17 算法在运行期退化而如此标注。
- 移动构造后源对象被显式清空；`swap`、`erase`、批量插入的异常路径上调用 `clear()`；单元素插入尽量回滚（见上文）。
- 尚未实现 `lookup`。
- `sorted_unique` 前提只在 `debug` 加固档检查，容器等长在 `fast` 档即检查。

## 历史演进

- C++23：`flat_map`、`flat_multimap` 随 [[P0429R9]] 进入标准，同期 `flat_set` 家族随 [[P1222R4]] 进入。
- C++26：全部成员 `constexpr`（`__cpp_lib_constexpr_flat_map`，值 `202502L`）。
- 当前草案：新增 `lookup` 成员（与 `std::map` 同步）。

## 思考题

1. `flat_map<int, int>` 用 `std::ranges::sort(m)` 会发生什么？能编译吗？语义上有意义吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`ranges::sort` 要求 `sortable<iterator_t<R>>`，其中包括 `indirectly_swappable` 与 `indirectly_movable_storable`。`flat_map` 的 `reference` 是 `pair<const int&, int&>`，`.first` 是 const 引用，无法通过它赋值，所以约束不满足，编译失败。这恰好是期望的结果：键是不可修改的（排序会破坏不变式 2）。真正需要重排时，应当 `extract()` 出两个容器，用 `views::zip(keys, values)` 排序，再 `replace()` 回去。
</details>

2. 某函数接收 `const std::flat_map<K, V>&`，把 `m.values().data()` 交给 C 库。对 `m` 做什么操作之后，这个指针会失效？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`values()` 返回 *c*.values 的 const 引用，`data()` 的有效性就是 `vector` 的规则。任何 `insert`/`emplace`/`try_emplace`/`operator[]`（缺失键时）/`erase`/`clear`、`extract`（把容器移走）、`replace`、赋值、`swap` 都可能使它失效或指向不同内容（[container.adaptors.general] ¶5）。另外，任何以异常退出的成员函数都可能清空 `m`（[[flat.map#6]]），所以"上一个操作抛了异常但被捕获"之后，也不能假定指针仍然有效。
</details>

3. 为什么 `insert(sorted_unique, first, last)` 的效果被规定为"等价于 `insert(first, last)`"，而不是"直接追加然后合并"？

<details markdown="1">
<summary>展开查看答案与解析</summary>

两者的可观察结果在前置条件满足时完全相同：新元素已经有序无重复，"排序新元素"这一步不改变任何东西。把效果写成"等价于"可以复用 ¶6 对合并、去重的精确描述（包括与已有键冲突时保留旧元素），只需把复杂度从 N + M log M 收紧为线性，就迫使实现跳过排序。至于 ¶10 的 UB：若数据并非有序，实现跳过排序后合并出的序列就不是有序的，不变式被破坏，后续所有二分查找都可能出错。
</details>

## 小结

- `flat_map` = 两个并行有序序列容器 + 比较器。查找快、遍历极快、单点插入删除线性；能批量就批量，`extract`/`replace` 是批量修改的正规通道。
- 迭代器解引用得到代理 `pair<const Key&, T&>`：不能绑定 `pair&`；`for (auto [k, v] : fm)` 会**修改**容器。Cpp17 层面只是输入迭代器，C++20 概念层面是随机访问迭代器。
- 满足容器、可逆容器、关联容器要求，但**不**满足节点句柄、失效、单点复杂度三项；**不是** allocator-aware 容器，却通过 `uses_allocator` 特化参与 uses-allocator 构造。
- 异常后只保证不变式恢复，结果可能是空容器（¶6）；移动后源对象的不变式也必须成立。
- `sorted_unique`（`flat_multimap` 为 `sorted_equivalent`）是向库作出的承诺，撒谎是 UB；容器不等长也是 UB。libc++ 分别在 `debug` 与 `fast` 加固档检查。
- 迭代器失效规则完全继承底层容器：`vector` 下任何插入都可能使一切失效，持有 `operator[]` 返回的引用跨越插入是经典 UB。
