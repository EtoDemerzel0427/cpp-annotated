---
title: 有序关联容器要求
summary: set、map、multiset、multimap 共同遵守的契约：比较器必须是严格弱序，键的等价由比较器决定，以及各操作的复杂度、失效规则、异构查找和异常安全。
status: done
covers: *
related: container.requirements, container.requirements.general, associative, container.node, unord.req, alg.sorting, flat.map, flat.set
tags: 标准库, 容器, 关联容器, 严格弱序, 异构查找, 透明比较器
updated: 2026-10-19
---

!!! tldr
    - 比较器必须在键上构成严格弱序，并且对同一对键永远给出同样的结果。用 `<=` 当比较器就违反了这一点，行为未定义。
    - 两个键等价，指 `comp(a, b)` 和 `comp(b, a)` 都为假。容器从不调用 `operator==`。
    - 插入不使任何迭代器或引用失效，擦除只使被擦除元素失效；`extract` 后指针仍有效，但元素在节点句柄里时不能经由它访问。
    - 带提示的插入，元素恰好插在提示之前时是摊还常数时间；已排序的区间构造是线性的。
    - 用 `std::less<>` 这类声明了 `is_transparent` 的比较器，`find` 等查找函数才接受与键类型不同的实参，不必先构造临时的键对象。

`set`、`multiset`、`map`、`multimap` 是标准库的四个**有序关联容器**：它们按键排序存放元素，查找、插入、擦除都是对数时间。本节规定它们共同的要求，各容器自己的条款（[[associative]]）只补充差异。`flat_map`、`flat_set` 等容器适配器也沿用本节的大部分术语（[[flat.map]]、[[flat.set]]）。

## 比较器写错，map 就坏了 [associative.reqmts.general]

```cpp title="less-equal.cpp" run ub
#include <cstdio>
#include <functional>
#include <map>

int main() {
  // UB: less_equal 不是严格弱序
  std::map<int, int, std::less_equal<int>> m;
  m[1] = 10;
  m[1] = 20;
  std::printf("size=%zu find=%d\n",
              m.size(), m.find(1) != m.end());
}
```

本机 libc++ 打印 `size=2 find=0`：唯一键的 `map` 里出现了两个键 1，`find(1)` 却一个也找不到。这是违反前置条件的一种表现，标准不保证任何具体症状。

### 严格弱序（¶2）

¶2 每个关联容器以键类型 `Key` 和排序关系 `Compare` 为参数，`Compare` 必须在 `Key` 上诱导**严格弱序**（[[g:strict-weak-ordering]]，定义见 [[alg.sorting]]）。`Compare` 类型的那个对象叫作容器的**比较对象**。`map` 和 `multimap` 还把一个映射类型 `T` 关联到键上。

一个关系 `comp` 是严格弱序，要满足三点：

1. 非自反：`comp(a, a)` 为假；
2. 传递：`comp(a, b)` 且 `comp(b, c)` 蕴含 `comp(a, c)`；
3. 不可比较关系也传递：如果 `a` 与 `b` 不可比较，`b` 与 `c` 不可比较，那么 `a` 与 `c` 也不可比较。这里不可比较指 `!comp(a, b) && !comp(b, a)`。

第 3 点使不可比较成为一个等价关系，把键分成若干等价类，各等价类之间是全序。`<=` 违反的是第 1 点：`comp(k, k)` 为真，任何键都不和自己等价，所以上例里 `m[1]` 每次都找不到已有的 1。

### 等价不是相等（¶3）

!!! std
    two keys k1 and k2 are considered to be equivalent if for the comparison object comp, comp(k1, k2) == false && comp(k2, k1) == false.

¶3 两个键的**等价**完全由比较对象决定。注 1 提醒，这不一定等于 `k1 == k2` 的结果：容器从不调用 `operator==` 来判断两个键是否相同。

同一段还要求，对容器中的任意两个键，`comp(k1, k2)` 必须总是返回同样的值。比较器不能有随时间变化的状态，键也不能在容器里被改到改变相对顺序的程度。

## 唯一键与等价键（¶4–¶6）

¶4 `set` 和 `map` 支持**唯一键**：每个键最多一个元素。`multiset` 和 `multimap` 支持**等价键**：可以有多个等价的键。对后两者，`insert`、`emplace` 和 `erase` 保持等价元素之间的相对顺序。

```cpp title="multimap-order.cpp" run ok
#include <cassert>
#include <map>
#include <string>

int main() {
  std::multimap<int, std::string> m;
  m.emplace(1, "a");
  m.emplace(2, "x");
  m.emplace(1, "b");                  // 插在等价区间的末尾
  m.emplace_hint(m.begin(), 1, "c");  // 尽量插在提示位置之前
  auto [lo, hi] = m.equal_range(1);
  std::string seq;
  for (auto i = lo; i != hi; ++i) seq += i->second;
  assert(seq == "cab");
}
```

¶5 `set` 系的值类型就是键类型；`map` 系的值类型是 `pair<const Key, T>`。键上的 `const` 防止用户通过迭代器修改键、打乱顺序。

¶6 迭代器是双向迭代器。值类型就是键类型时（`set` 系），`iterator` 和 `const_iterator` 都是常量迭代器，两者是否为同一类型未指明。注 2 因此建议函数形参一律写 `const_iterator`：否则 `void f(set<int>::iterator); void f(set<int>::const_iterator);` 在一个实现上是两个重载，在另一个实现上是重复定义。

## 各操作的复杂度

要求表（¶8–¶174）逐条列出了每个表达式的返回类型、前置条件、效果和复杂度。下表是其中的要点：

| 操作 | 复杂度 | 说明 |
|---|---|---|
| `X(i, j)`、`X(from_range, rg)` | N log N；区间已排序时线性 | ¶25、¶28、¶31 |
| `emplace`、`insert(t)` | 对数 | 唯一键返回 `pair<iterator, bool>`；等价键插在等价区间末尾（¶54、¶68） |
| `emplace_hint(p, …)`、`insert(p, t)` | 对数；恰好插在 `p` 之前时摊还常数 | ¶60、¶74 |
| `insert(i, j)`、`insert_range(rg)` | N log(size + N) | 源区间不得指向 `a` 本身 |
| `insert(nh)`、`insert(p, nh)` | 同单元素插入 | 见 [[container.node]] |
| `extract(k)` / `extract(q)` | 对数 / 摊还常数 | ¶103、¶111 |
| `erase(k)` | log(size) + count(k) | ¶121 |
| `erase(q)` | 摊还常数 | ¶129 |
| `erase(q1, q2)` | log(size) + N | ¶137 |
| `find`、`count`、`contains`、`lower_bound`、`upper_bound`、`equal_range` | 对数（`count` 另加结果个数） | ¶141–¶174 |

几处值得一看：

- 已排序区间的构造要求线性，排除了逐个以对数时间插入的朴素实现。实现需要利用新元素总在最右端这一点，每次以 `end()` 为提示插入。
- `erase(q)` 是摊还常数：单次擦除可能要 O(log n) 时间去重新平衡或寻找后继，但均摊下来是常数。
- `lower_bound(k)` 返回第一个不小于 `k` 的元素，`upper_bound(k)` 返回第一个大于 `k` 的元素，`equal_range(k)` 就是这两者组成的区间。
- 对唯一键容器，`emplace` 要先构造出 `value_type` 对象才拿得到键去比较；键已存在时，这个对象再被销毁。`map::try_emplace`（[[associative]]）就是为避免这种浪费而设计的。

## 失效规则（¶175–¶176）

!!! std
    The insert, insert_range, and emplace members shall not affect the validity of iterators and references to the container, and the erase members shall invalidate only iterators and references to the erased elements.

¶175 插入从不使任何迭代器或引用失效；擦除只使指向被擦除元素的迭代器和引用失效。这是基于节点的实现带来的结果：每个元素在自己的节点里，地址从不改变。

¶176 `extract` 只使指向被取出元素的迭代器失效，指向它的指针和引用仍然有效。但元素归节点句柄所有期间，经由这些指针和引用访问它是 {{ub}}；元素被成功插入某个容器后，在句柄持有期间得到的指针和引用失效。这条规则让"取出、改键、插回"的流程不必搬动元素（[[container.node]]）。

### merge（¶112–¶117）

`a.merge(a2)` 尝试把 `a2` 的每个元素取出并用 `a` 的比较对象插入 `a`。前置条件是两个容器的分配器相等。对唯一键容器，如果 `a` 里已有等价的键，这个元素就留在 `a2` 里。

```cpp title="merge.cpp" run ok
#include <cassert>
#include <set>

int main() {
  std::set<int> a{1, 2, 3}, b{3, 4, 5};
  auto it = b.find(4);
  const int* p = &*it;
  a.merge(b);                       // 搬节点，不复制元素
  assert((a == std::set<int>{1, 2, 3, 4, 5}));
  assert((b == std::set<int>{3}));  // a 中已有 3：留在 b
  assert(p == &*a.find(4));         // 指针指向同一元素
  assert(it == a.find(4));          // it 现在是 a 的迭代器
}
```

¶115 被转移元素的指针和引用继续指向原元素，只是它们现在属于 `a`。如果 `a.begin()` 和 `a2.begin()` 类型相同，迭代器也继续指向原元素，并且表现为 `a` 的迭代器。¶116 除了比较对象抛出的异常，`merge` 不抛异常；¶117 复杂度是 N log(a.size() + N)。

## 异构查找（¶7、¶180）

```cpp title="heterogeneous-lookup.cpp" run ok
#include <cassert>
#include <set>
#include <string>
#include <string_view>

int main() {
  std::set<std::string, std::less<>> s{"apple", "banana"};
  std::string_view key = "apple";
  assert(s.contains(key));         // 不构造 std::string 临时对象
  s.erase(s.find(key));
  assert(s.count("banana") == 1);  // const char* 直接与 string 比较

  std::set<std::string> plain{"apple"};
  // plain.find(key);  // error: less<string> 不透明，
  //                   // string_view 也不能隐式转换为 string
  assert(plain.find(std::string(key)) != plain.end());
}
```

¶180 `find`、`count`、`contains`、`lower_bound`、`upper_bound`、`equal_range`、`erase`、`extract` 各有一个成员函数模板版本，接受任意类型的实参。这些模板只在 `Compare::is_transparent` 有效并表示一个类型时才参与重载决议。

!!! std
    The member function templates find, count, contains, lower_bound, upper_bound, equal_range, erase, and extract shall not participate in overload resolution unless the qualified-id Compare::is_transparent is valid and denotes a type.

声明了 `is_transparent` 的比较器叫**透明比较器**（[[g:transparent-comparator]]）。`std::less<>`（即 `less<void>`）是透明的，`std::less<std::string>` 不是。之所以要用户显式选择，是为了保护旧代码：以前用一个可以隐式转换为 `Key` 的值调用 `find`，语义是先转换再比较；如果模板版本无条件参与重载决议，这些调用的含义就会悄悄改变。

同一段还规定，`erase` 和 `extract` 的模板版本在实参可以转换为 `iterator` 或 `const_iterator` 时不参与重载决议，防止 `erase(it)` 被模板版本抢走。

¶7 规定了异构实参必须满足的条件。设 `x` 遍历容器中元素的键，`c` 是比较对象：

| 记号 | 条件 | 用于 |
|---|---|---|
| `kl` | 容器关于 `c(x, kl)` 已划分 | `lower_bound` |
| `ku` | 容器关于 `!c(ku, x)` 已划分 | `upper_bound` |
| `ke` | 关于 `c(x, ke)` 和 `!c(ke, x)` 都已划分，且前者蕴含后者 | `find`、`count`、`contains`、`equal_range` |
| `kx` | 同 `ke`，并且不能转换为 `iterator` 或 `const_iterator` | `erase`、`extract` |

已划分（partitioned，[[alg.sorting]]）指满足条件的元素全部排在不满足的元素前面。这正是二分查找能工作的最弱条件：异构的键不必和容器里的键构成严格弱序，只要能把有序序列切成前后两段。

!!! impl
    异构的 `erase` 和 `extract` 是 C++23 加入的。本机 libc++ 没有定义 `__cpp_lib_associative_heterogeneous_erasure`，`s.erase(key)` 无法编译，所以上例用了 `s.erase(s.find(key))`。

## 其他保证

### 迭代顺序（¶177–¶178）

¶177 关联容器迭代器的基本性质是按键的非降序遍历，非降序由构造时使用的比较对象定义：对任意两个可解引用的迭代器 `i`、`j`，如果从 `i` 到 `j` 的距离为正，则 `value_comp(*j, *i) == false`。¶178 唯一键容器满足更强的条件 `value_comp(*i, *j) != false`。

### 比较对象按值保存（¶179）

¶179 即使比较对象是按引用传给构造函数的，容器也不得保存指向它的指针或引用。复制容器时，目标容器使用源容器的比较对象，如同在构造时传入。所以有状态的比较器会被复制进容器。

### 推导指引（¶181）

¶181 类模板实参推导时，如果为 `Compare` 推导出一个具备分配器资格的类型，这条推导指引就不参与重载决议（另外两条排除了不像迭代器的 `InputIterator` 和不像分配器的 `Allocator`）。这样 `std::map m(first, last, alloc);` 里的 `alloc` 不会被误当作比较器。

### 异常安全 [associative.reqmts.except]

¶1 `clear()` 不抛异常；`erase(k)` 只可能因比较对象抛出而抛出。

¶2 插入单个元素的 `insert` 或 `emplace` 中，任何操作抛出异常，插入都没有效果，即强异常保证。

¶3 `swap` 只可能因比较对象的 `swap` 抛出而抛出。

## 思考题

!!! question "思考题 1"
    往 `std::set<double>` 里插入 NaN 会怎样？

<details markdown="1">
<summary>答案</summary>

`std::less<double>` 在含 NaN 的值上不是严格弱序。NaN 与任何值都不可比较，于是 NaN 与 1.0 不可比较，与 2.0 也不可比较，但 1.0 与 2.0 可比较，不可比较关系不再传递。第 2 段要求 `Compare` 在容器的键上诱导严格弱序，插入 NaN 后这个要求就被违反了，行为未定义。常见的表现是 NaN 被当作与某个已有元素等价而插入失败，或者插进去后再也找不到。需要容纳 NaN 时，可以改用基于 `std::strong_order` 的比较器，它对浮点数给出全序。
</details>

!!! question "思考题 2"
    为什么 `insert(p, t)` 规定的是恰好插在 `p` 之前时摊还常数，而不是之后？

<details markdown="1">
<summary>答案</summary>

C++03 的措辞确实是插在 `p` 之后，C++11 改成了之前。改成之前后，`end()` 可以当提示：用 `insert(m.end(), x)` 依次插入一个升序序列，每个新元素都恰好在 `end()` 之前，总复杂度是线性的，已排序区间的线性构造（¶25）就可以这样实现。插在之后则无法用一个迭代器表示末尾。此外，之前也与序列容器 `insert(p, t)` 在 `p` 之前插入的语义一致，`std::inserter` 这类泛型代码对两类容器都能高效工作。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

¶1 列出四种关联容器，并提到可以用序列容器构造 `flat_map` 等适配器。

¶7 还定义了要求表中用到的其他记号：`a`、`b` 是容器的值，`a_uniq`、`a_eq` 分别表示唯一键和等价键容器，`a_tran` 表示 `X::key_compare::is_transparent` 有效时的容器，`i`、`j` 是输入迭代器，`p`、`q`、`r` 是指向 `a` 的各种迭代器，`t` 是 `value_type` 的值，`k` 是 `key_type` 的值，`nh` 是节点句柄右值。

¶8 `X` 满足关联容器要求，当且仅当它满足分配器感知容器的全部要求，并且要求表中的表达式都良构且语义正确。对 `map` 和 `multimap`，[container.reqmts] 中对 `value_type` 的要求改为施加于 `key_type` 和 `mapped_type`，因为 `pair<const K, T>` 本身不可复制赋值。

¶9–¶17 规定嵌套类型：`key_type` 是 `Key`，`mapped_type` 是 `T`（只有 `map` 系有），`key_compare` 是 `Compare` 并要求可复制构造，`value_compare` 对 `set` 系等于 `key_compare`、对 `map` 系是按 `first` 比较 `pair` 的谓词，`node_type` 是 [[container.node]] 中节点句柄模板的特化。

¶18–¶45 规定构造函数、`a = il` 赋值（N log N，已排序时线性）、`key_comp()` 和 `value_comp()`（返回构造时的比较对象，常数时间）。

</details>
