---
title: 有序关联容器要求
summary: set/map/multiset/multimap 的共同契约——比较器必须诱导严格弱序且对同一对键结果不变、"等价"不是"相等"、带提示插入的摊还常数、透明比较器与异构查找的精确条件（kl/ku/ke/kx）、merge/extract 的失效规则、迭代顺序不变式与异常安全
status: done
covers: *
related: container.requirements, container.requirements.general, associative, container.node, unord.req, alg.sorting, flat.map, flat.set
tags: 标准库, 容器, 关联容器, 严格弱序, 异构查找, 透明比较器
updated: 2026-10-18
---

有序关联容器按**键**组织元素，用一个比较器维持排序，提供对数时间的查找、插入、擦除。标准库的四个——`set`、`multiset`、`map`、`multimap`——都满足本节的*关联容器*要求；`flat_map` 等容器适配器也借用了本节的大部分术语（[[flat.map]]、[[flat.set]]）。

本节的分量在于它对**比较器**的要求：一个"看起来合理"的比较器（比如 `<=`）就能让整个容器进入未定义行为。

## 比较器与等价（[associative.reqmts.general] ¶1–¶3）

¶2：每个关联容器以 `Key` 和一个排序关系 `Compare` 为参数，`Compare` 必须在 `Key` 的元素上诱导**严格弱序**（[[g:strict-weak-ordering]]，[[alg.sorting]]）。`map`/`multimap` 还把任意的**映射类型** `T` 关联到 `Key`。`Compare` 类型的对象称为容器的**比较对象**。

严格弱序 `comp` 的要求（[[alg.sorting]]）：非自反（`comp(a, a)` 为假）、传递，并且由它导出的"不可比较"关系 `!comp(a, b) && !comp(b, a)` 也是传递的——即它是一个等价关系，把键划分成等价类，等价类之间全序排列。

¶3：

!!! std
    two keys k1 and k2 are considered to be equivalent if for the comparison object comp, comp(k1, k2) == false && comp(k2, k1) == false.

    若 comp(k1, k2) 与 comp(k2, k1) 都为 false，则两个键被视为等价。

注 1：这**不一定**等同于 `k1 == k2` 的结果。容器从不调用 `operator==` 判断键是否"相同"，只用比较器导出的**等价**。¶3 还要求：对同一容器中的任意两个键，调用 `comp(k1, k2)` 必须**总是返回相同的值**——比较器不能有随时间变化的状态，键也不能在容器中被修改到改变相对顺序的程度。

用 `<=` 当比较器违反的是"非自反"：`comp(k, k)` 为真，于是任何键都不和自己等价。

```cpp title="less-equal.cpp" run ub
#include <map>
#include <functional>
#include <cstdio>

int main() {
  std::map<int, int, std::less_equal<int>> m;   // UB: less_equal 不是严格弱序
  m[1] = 10;
  m[1] = 20;                                    // 两个"等价"判断都为 true
  std::printf("size=%zu find=%d\n", m.size(), m.find(1) != m.end());
}
```

本机 libc++ 输出 `size=2 find=0`：一个"唯一键"的 `map` 里出现了两个键 1，而 `find(1)` 一个也找不到。这是违反前置条件的典型症状，但标准不保证任何具体症状。

## 唯一键与等价键、值类型、迭代器（¶4–¶6）

- ¶4：支持**唯一键**（unique keys）的容器对每个键最多含一个元素（`set`、`map`）；否则支持**等价键**（equivalent keys，`multiset`、`multimap`）。对 `multi*`，`insert`、`emplace`、`erase` **保持等价元素的相对顺序**。
- ¶5：`set`/`multiset` 的值类型就是键类型；`map`/`multimap` 的值类型是 `pair<const Key, T>`——键的 `const` 是对"不得改变键的顺序"的类型层面保护。
- ¶6：`iterator` 是双向迭代器。值类型与键类型相同时（`set` 系），`iterator` 和 `const_iterator` **都是常量迭代器**，并且两者是否为同一类型**未指明**。注 2：为避免违反 ODR，在函数形参列表中应始终使用 `const_iterator`——否则 `void f(set<int>::iterator); void f(set<int>::const_iterator);` 在一个实现上是重载、在另一个实现上是重定义。

```cpp title="multimap-order.cpp" run ok
#include <map>
#include <string>
#include <cassert>

int main() {
  std::multimap<int, std::string> m;
  m.emplace(1, "a");
  m.emplace(2, "x");
  m.emplace(1, "b");                // 插在等价键区间的末尾
  m.emplace_hint(m.begin(), 1, "c"); // 带提示：尽可能靠近提示位置之前
  auto [lo, hi] = m.equal_range(1);
  std::string seq;
  for (auto i = lo; i != hi; ++i) seq += i->second;
  assert(seq == "cab");
}
```

## 记号：异构查找的四种"键"（¶7）

¶7 的记号是本节最精密的部分。除了常规的 `a`、`b`、`k`（`key_type` 的值）、`c`（比较对象）外，它为异构查找定义了四种"不是 `key_type` 的键"：

| 记号 | 条件（`x` 遍历 `a` 中元素的键） | 用于 |
|---|---|---|
| `kl` | `a` 关于 `c(x, kl)` 被划分（[[alg.sorting]]） | `lower_bound(kl)` |
| `ku` | `a` 关于 `!c(ku, x)` 被划分 | `upper_bound(ku)` |
| `ke` | `a` 关于 `c(x, ke)` 和 `!c(ke, x)` 都被划分，且 `c(x, ke)` 蕴含 `!c(ke, x)` | `find`、`count`、`contains`、`equal_range` |
| `kx` | 同 `ke`，并且 `kx` **不能**转换为 `iterator` 或 `const_iterator` | `erase(kx)`、`extract(kx)` |

这些条件不要求 `kl` 等与容器的键"严格弱序兼容"，只要求容器关于它们**被划分**——即二分查找能工作所需的最弱条件。`kx` 的附加条件防止 `erase(it)` 的迭代器实参被误当成异构键。另外，`a_tran` 表示"`X::key_compare::is_transparent` 有效且表示类型"时的容器（¶7.8）。

## 要求表（¶8–¶174）

¶8：`X` 满足关联容器要求，当且仅当它满足分配器感知容器的全部要求，并且下列表达式良构且有指定语义；对 `map`/`multimap`，[container.reqmts] 中对 `value_type` 的要求改为施加于 `key_type` 和 `mapped_type`（注 3：`pair<const K, T>` 本身不可拷贝赋值，但 `K`、`T` 有时需要可拷贝赋值）。

### 类型（¶9–¶17）

`key_type`（`Key`）、`mapped_type`（`T`，仅 `map` 系）、`value_type`、`key_compare`（`Compare`，前置条件 *Cpp17CopyConstructible*）、`value_compare`（`set` 系同 `key_compare`；`map` 系是按 `first` 比较 `pair` 的关系）、`node_type`（[[container.node]] 的特化）。

### 构造（¶18–¶40）

| 表达式 | 复杂度 |
|---|---|
| `X(c)`、`X u;` | 常数 |
| `X(i, j, c)`、`X(i, j)` | 一般 N log N；**若 `[i, j)` 已按 `value_comp()` 排序则线性**（¶25、¶28） |
| `X(from_range, rg, c)`、`X(from_range, rg)` | 同上（¶31、¶34） |
| `a = il` | N log N，N 为 `il.size() + a.size()`；已排序则线性（¶40） |

"已排序则线性"禁止了"逐个以 O(log n) 插入"的朴素实现——实现必须利用"新元素总是在最右端"这一事实，带着提示插入。

### 插入（¶46–¶99）

| 表达式 | 唯一键返回 | 等价键语义 | 复杂度 |
|---|---|---|---|
| `emplace(args)` | `pair<iterator, bool>` | 插在等价区间**末尾**（¶54） | 对数 |
| `emplace_hint(p, args)` | 同 `emplace` 返回的迭代器 | 尽可能插在紧靠 `p` **之前**的位置（¶58） | 对数；**若恰好插在 `p` 之前则摊还常数**（¶60） |
| `insert(t)` | `pair<iterator, bool>` | 插在等价区间末尾（¶68） | 对数 |
| `insert(p, t)` | `iterator` | 同 `emplace_hint` | 同 `emplace_hint`（¶74） |
| `insert(i, j)`、`insert_range(rg)` | `void` | — | N log(a.size() + N)（¶78、¶82）；源不得指向/重叠 `a` |
| `insert(nh)` | `insert_return_type` | 等价键版返回 `iterator` | 对数（¶88、¶93） |
| `insert(p, nh)` | `iterator` | — | 对数；恰在 `p` 之前时摊还常数（¶99） |

注意 `emplace` 有一个常被忽视的代价：对唯一键容器，它必须**先构造**出 `value_type` 对象才能拿到键去比较，键已存在时再把它销毁。`map::try_emplace`（[[associative]]）正是为避免这一点而生。

节点句柄插入（¶84–¶99）的前置条件是 `nh` 为空或与容器分配器相等；插入失败时 `insert_return_type::node` 保有原节点（不丢失元素）。详见 [[container.node]]。

### 取出、合并、擦除（¶100–¶140）

- `extract(k)`/`extract(kx)`：取出第一个键等价于 `k` 的元素，返回拥有它的节点句柄，找不到则返回空句柄；log(size) 复杂度。`extract(q)`：**摊还常数**（¶111）。
- `merge(a2)`（¶112–¶117）：前置条件分配器相等。尝试把 `a2` 的每个元素提取并插入 `a`（使用 `a` 的比较对象）；唯一键容器中若 `a` 已有等价键，该元素**留在 `a2`**。后置条件：被转移元素的指针和引用指向同一元素，现在是 `a` 的成员；若 `a.begin()` 与 `a2.begin()` 类型相同，迭代器继续指向原元素，但表现为 `a` 的迭代器。除比较对象外不抛异常。N log(a.size() + N)。
- `erase(k)`：擦除所有等价于 `k` 的元素，返回个数，log(size) + count(k)（¶121）。`erase(q)`/`erase(r)`：**摊还常数**（¶129、¶133）——这里的"摊还"是因为红黑树删除后的再平衡是摊还 O(1) 次旋转，而找后继在最坏情况下是 O(log n)，摊还到整次遍历才是常数。`erase(q1, q2)`：log(size) + N。
- `clear()`：等价于 `erase(begin(), end())`，线性。

```cpp title="merge.cpp" run ok
#include <set>
#include <cassert>

int main() {
  std::set<int> a{1, 2, 3}, b{3, 4, 5};
  auto it = b.find(4);
  const int* p = &*it;
  a.merge(b);                       // 搬节点，不拷贝元素
  assert((a == std::set<int>{1, 2, 3, 4, 5}));
  assert((b == std::set<int>{3}));  // 3 在 a 中已有等价键：留在 b
  assert(p == &*a.find(4));         // 指针仍指向同一元素，现属于 a
  assert(it == a.find(4));          // 迭代器类型相同：it 现在表现为 a 的迭代器
}
```

### 查找（¶141–¶174）

`find`、`count`（log + count）、`contains`、`lower_bound`（第一个**不小于** k 的元素）、`upper_bound`（第一个**大于** k 的元素）、`equal_range`（等价于 `make_pair(lower_bound, upper_bound)`），各有一个 `a_tran` 的异构版本，条件见上文 `kl`/`ku`/`ke`。全部对数复杂度（`count` 为 log + 结果数）。

## 失效规则（¶175–¶176）

!!! std
    The insert, insert_range, and emplace members shall not affect the validity of iterators and references to the container, and the erase members shall invalidate only iterators and references to the erased elements.

    插入成员不得影响迭代器和引用的有效性；擦除成员只使指向被擦除元素的迭代器和引用失效。

¶176：`extract` 只使指向被取出元素的**迭代器**失效；指向它的指针和引用**仍然有效**——但元素归节点句柄所有期间，经由它们访问元素是 {{ub}}；元素被成功插入（到任何容器）后，在句柄持有期间获得的引用和指针失效。这条看似奇怪的规则，是为了允许"`extract` → 修改键 → 插回"的流程在实现上不搬动元素，同时给实现留下"句柄持有期间元素处于特殊状态"的余地（[[container.node]]）。

## 迭代顺序不变式（¶177–¶178）

¶177：关联容器迭代器的**基本性质**是按键的**非降序**遍历，"非降序"由构造时使用的比较定义：对任意距离为正的可解引用迭代器 `i`、`j`，`value_comp(*j, *i) == false`。¶178：唯一键容器满足更强的条件 `value_comp(*i, *j) != false`。

这是容器对外的承诺，也是对**用户**的约束：如果你通过 `const_cast` 或可变成员改动了键，使这一不变式被破坏，后续操作的前提就不成立了。

## 比较对象的存储（¶179）

构造时传入比较对象，容器**不得**存储指向它的指针或引用，即使是按引用传入的；拷贝容器时，目标容器使用源容器的比较对象，如同在构造时传入。所以有状态的比较器（如携带区域设置的字符串比较器）会被**按值**复制进容器。

## 透明比较器与重载决议（¶180）

!!! std
    The member function templates find, count, contains, lower_bound, upper_bound, equal_range, erase, and extract shall not participate in overload resolution unless the qualified-id Compare::is_transparent is valid and denotes a type.

    find、count、contains、lower_bound、upper_bound、equal_range、erase、extract 的成员函数模板，除非 Compare::is_transparent 有效且表示类型，否则不参与重载决议。

另外，`extract` 和 `erase` 的模板在 `is_convertible_v<K&&, iterator> || is_convertible_v<K&&, const_iterator>` 为真时也不参与重载决议——防止 `erase(it)` 被模板劫持。

"透明"（[[g:transparent-comparator]]）是一种**选择加入**：`std::less<>`（即 `less<void>`）声明了 `is_transparent`，`std::less<std::string>` 没有。没有这一层选择加入，C++14 之前的代码里"用可隐式转换为 `Key` 的类型调用 `find`"的语义（先转换、再比较）就会被悄悄改变。

```cpp title="heterogeneous-lookup.cpp" run ok
#include <set>
#include <map>
#include <string>
#include <string_view>
#include <cassert>

int main() {
  std::set<std::string, std::less<>> s{"apple", "banana"};
  std::string_view key = "apple";
  assert(s.contains(key));          // 异构查找：不构造 std::string 临时对象
  s.erase(s.find(key));             // 异构 erase(key) 是 C++23 的，本机 libc++ 未实现
  assert(s.count("banana") == 1);   // const char* 也直接与 std::string 比较

  std::set<std::string> plain{"apple"};
  // plain.find(key);               // error: std::less<std::string> 不透明，string_view 不能隐式转换为 string
  assert(plain.find(std::string(key)) != plain.end());
}
```

{{impl}} 本机 libc++ 的 `<version>` 中 `__cpp_lib_associative_heterogeneous_erasure`（C++23 的异构 `erase`/`extract`）与 `__cpp_lib_associative_heterogeneous_insertion`（C++26 的异构 `insert`/`try_emplace`/`operator[]` 等，见 [[associative]]）都仍被注释掉，即尚未实现。

## 推导指引（¶181）

关联容器的推导指引在以下情况不参与重载决议：`InputIterator` 推导出不具备输入迭代器资格的类型；`Allocator` 推导出不具备分配器资格的类型；**`Compare` 推导出一个具备分配器资格的类型**。最后一条消除了 `std::map m(first, last, alloc)` 中把分配器误当作比较器的歧义。

## 异常安全（[associative.reqmts.except]）

- ¶1：`clear()` 不抛；`erase(k)` 只可能因 `Compare` 对象抛出而抛出。
- ¶2：单元素 `insert`/`emplace` 内部的**任何**操作抛出异常，插入都无效果（强保证）。
- ¶3：`swap` 只可能因 `Compare` 对象的 `swap` 抛出而抛出。

## 思考题

!!! question "1. `std::set<double>` 中插入 NaN 会怎样？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

`std::less<double>` 在含 NaN 的值域上**不是**严格弱序：NaN 与任何值都"不可比较"（`a < NaN` 和 `NaN < a` 都为假），于是 NaN 等价于 1.0、也等价于 2.0，但 1.0 与 2.0 不等价——"不可比较"关系不传递。¶2 要求 `Compare` 在容器的键上诱导严格弱序，一旦插入 NaN 就违反了它，行为未定义。实践中常见的症状是：NaN 被当作"与它比较的第一个元素等价"而插入失败，或者插进去后再也找不到。需要容纳 NaN 时，用 `std::strong_order` 包装一个全序比较器。
</details>

!!! question "2. 为什么 `map::insert(p, t)` 规定的是“恰好插在 `p` **之前**时摊还常数”，而不是“之后”？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

C++98 的措辞曾是"插在 `p` 之后"，C++11 经库工作组讨论改为"之前"。"之前"与 `end()` 配合得最好：用 `insert(m.end(), x)` 依次插入一个**升序**序列，每次新元素都恰好在 `end()` 之前，于是总复杂度线性——这正是 ¶25"已排序区间构造为线性"的实现方式；而"之后"无法用 `end()` 表达"末尾"。此外，"之前"与序列容器 `insert(p, t)` 的"在 p 之前插入"语义一致，泛型代码（如 `std::inserter`）因而对两类容器都正确。
</details>

## 小结

- 比较器必须诱导严格弱序，且对同一对键的结果永不改变；等价 ≠ 相等。
- 插入从不使任何东西失效；擦除只使被擦除者失效；`extract` 的引用/指针仍有效但不可经由它们访问。
- 带提示插入在恰好位于提示之前时摊还常数；已排序区间构造线性。
- 异构查找需要 `Compare::is_transparent`；`erase`/`extract` 的异构版本排除了可转换为迭代器的实参。
- 单元素插入强保证；`clear` 不抛；`erase(k)`/`swap` 只可能因比较器抛出。
