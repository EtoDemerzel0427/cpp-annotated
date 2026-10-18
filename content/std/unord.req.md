---
title: 无序关联容器要求
summary: unordered_* 的共同契约——Hash 与 Pred 的一致性要求、等价键组、桶与负载因子、rehash 使迭代器失效但从不使引用失效、(N+n) ≤ z·B 的不 rehash 保证、平均/最坏复杂度、透明哈希的双重选择加入、operator== 的置换语义与 UB 条件、异常安全
status: done
covers: *
related: container.requirements, container.requirements.general, unord, associative.reqmts, container.node, hash.requirements, unord.hash
tags: 标准库, 容器, 无序容器, 哈希, rehash, 迭代器失效
updated: 2026-10-18
---

无序关联容器（`unordered_set`、`unordered_map`、`unordered_multiset`、`unordered_multimap`，C++11）用哈希表组织元素：**平均**常数时间查找，**最坏**线性。本节规定它们的共同契约。与有序关联容器（[[associative.reqmts]]）相比，最需要警惕的是两件事：**Hash 与 Pred 必须一致**，以及 **rehash 会使所有迭代器失效**。

## 基本概念（[unord.req.general] ¶1–¶9）

¶1：大多数操作的最坏复杂度是线性的，但平均情况快得多。¶2：满足容器要求，但 `a == b` 与 `a != b` 的语义不同于其他容器（见下文 ¶240）。

¶3：每个无序容器以 `Key`、一个满足 *Cpp17Hash* 要求（[[hash.requirements]]）的哈希函数对象类型 `Hash`、以及一个在 `Key` 上诱导**等价关系**的二元谓词 `Pred` 为参数；`unordered_map` 系还关联映射类型 `T`。

¶4：`Hash` 对象称为容器的**哈希函数**，`Pred` 对象称为**键相等谓词**（key equality predicate）。

### Hash 与 Pred 的一致性（¶5）

!!! std
    If k1 and k2 are equivalent, the container's hash function shall return the same value for both.

    若 k1 与 k2 等价，容器的哈希函数必须对二者返回相同的值。

两个值若 `pred(k1, k2)` 有效且为真，则被视为**等价**。注 1 点明后果：用了非默认的 `Pred`，通常也需要非默认的 `Hash`。¶5 还要求：对同一容器中任意两个键，`pred(k1, k2)` 总返回相同的值；对容器中任意键 `k`，`hash(k)` 总返回相同的值。

```cpp title="hash-pred-mismatch.cpp" run ub
#include <unordered_set>
#include <string>
#include <cctype>
#include <cstdio>

struct CaseInsensitiveEq {
  bool operator()(const std::string& a, const std::string& b) const {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i)
      if (std::tolower((unsigned char)a[i]) != std::tolower((unsigned char)b[i])) return false;
    return true;
  }
};

int main() {
  // UB: "ABC" 与 "abc" 按 Pred 等价，但 std::hash<std::string> 给出不同的值（违反 ¶5）
  std::unordered_set<std::string, std::hash<std::string>, CaseInsensitiveEq> s{"abc"};
  std::printf("%d\n", s.contains("ABC"));
}
```

本机输出 `0`：查找 `"ABC"` 去了另一个桶，根本没机会调用 `Pred`。换一组字符串或换一个桶数，结果可能变成 `1`——这正是"未定义"的含义。

### 唯一键、等价键与等价键组（¶6–¶8）

¶6：`unordered_set`/`unordered_map` 支持唯一键，`multi` 版本支持等价键。在等价键容器中，等价键的元素在迭代顺序中**彼此相邻**——元素被分成若干**等价键组**（[[g:equivalent-key-group]]），组内所有元素键等价。修改操作必须保持每个组内元素的相对顺序，除非另有规定。

¶7–¶8：值类型（`Key` 或 `pair<const Key, T>`），以及"值类型即键类型时 `iterator` 与 `const_iterator` 都是常量迭代器、是否同一类型未指明"——与 [[associative.reqmts]] ¶6 相同，包括"函数形参里总用 `const_iterator` 以免违反 ODR"的注。

### 桶与 rehash（¶9）

!!! std
    Rehashing invalidates iterators, changes ordering between elements, and changes which buckets elements appear in, but does not invalidate pointers or references to elements.

    rehash 使迭代器失效、改变元素间的顺序、改变元素所在的桶，但不使指向元素的指针或引用失效。

元素被组织在**桶**（[[g:bucket]]）中，哈希值相同的键在同一个桶里。随着元素增加，桶数自动增加，使每桶平均元素数保持在一个上界之下。对 `multi` 版本，rehash 保持等价元素的相对顺序。

"不使指针和引用失效"这一句决定了实现：每个元素必须有独立且稳定的地址，开放寻址（把元素直接放进槽位数组）被排除了（见 [[container.requirements]] 的思考题）。

## 记号（¶10）

与 [[associative.reqmts]] 类似，除常规记号外，`a_tran` 表示 `X::key_equal::is_transparent` **和** `X::hasher::is_transparent` 都有效并表示类型时的容器（¶10.7）。异构键 `ke`、`kx` 的条件（¶10.20–¶10.21）是：

- `eq(r1, ke) == eq(ke, r1)`（对称）；
- `eq(r1, ke)` 为真时 `hf(r1) == hf(ke)`（哈希一致）；
- `eq(r1, ke)`、`eq(r2, ke)`、`eq(r1, r2)` 中任意两个为真则三个都为真（传递）；
- `kx` 还要求不能转换为 `iterator`/`const_iterator`。

其中 `r1`、`r2` 是容器中元素的键。也就是说，异构键必须"像一个真正的键那样"融入 `Pred` 的等价划分，并哈希到同一个值。

## 要求表（¶11–¶239）

¶11：满足分配器感知容器的全部要求，加上下列条目；对 `unordered_map` 系，对 `value_type` 的要求改施加于 `key_type` 与 `mapped_type`。

### 类型（¶12–¶23）

| 类型 | 结果 | 前置条件 |
|---|---|---|
| `hasher` | `Hash` | `hf(k)` 的类型为 `size_t`（¶18） |
| `key_equal` | `Pred` | *Cpp17CopyConstructible*，是接受两个 `Key` 的二元谓词，**是等价关系**（¶20） |
| `local_iterator` / `const_local_iterator` | 类别、值类型、差类型、指针与引用类型与 `iterator`/`const_iterator` 相同 | 只能遍历**单个桶**，不能跨桶（注 4、注 5） |
| `node_type` | [[container.node]] 的特化 | — |

### 构造（¶24–¶67）

- `X(n, hf, eq)` 等：构造至少有 `n` 个桶的空容器，**O(n)**（要初始化桶数组）。
- `X a;`：桶数未指明，常数。具体容器（[[unord]]）补充：默认构造的桶数由实现定义，`max_load_factor()` 返回 1.0。
- 区间构造：平均 O(N)，最坏 O(N²)。
- 拷贝构造/拷贝赋值：除容器要求外，还复制哈希函数、谓词**和最大负载因子**（¶63、¶66）；平均线性，最坏平方。

### 插入（¶77–¶130）

| 表达式 | 复杂度 |
|---|---|
| `emplace(args)`、`insert(t)` | 平均 O(1)，最坏 O(size) |
| `emplace_hint(p, args)`、`insert(p, t)` | 同上；`p` 是"从哪里开始搜索"的提示，**实现可以忽略**（¶89、¶103） |
| `insert(i, j)`、`insert_range(rg)` | 平均 O(N)，最坏 O(N·(size + 1)) |
| `insert(nh)`、`insert(q, nh)` | 平均 O(1)，最坏 O(size) |

与有序容器不同，`multi` 版本的 `emplace`/`insert` 只说"插入 t"，没有规定插在等价组的哪个位置（但 ¶6 要求等价元素相邻）。

### 取出、合并、擦除（¶130–¶171）

- `extract(k)`/`extract(kx)`/`extract(q)`：平均 O(1)，最坏 O(size)。
- `merge(a2)`（¶143–¶147）：分配器相等；用 `a` 的哈希与谓词插入；唯一键冲突时元素留在 `a2`。后置条件：被转移元素的指针和引用指向同一元素、现属于 `a`；**被转移元素的迭代器以及 `a` 的所有迭代器都失效**（因为可能 rehash），`a2` 中剩余元素的迭代器保持有效。平均 O(N)，最坏 O(N·size + N)。
- `erase(k)`：平均 O(count(k))，最坏 O(size)。`erase(q)`：平均 O(1)，最坏 O(size)。`erase(q1, q2)`：平均线性于距离，最坏 O(size)。`clear()`：线性。

### 查找（¶171–¶191）

`find`、`count`、`contains`、`equal_range` 及其 `a_tran` 版本：平均 O(1)（`count`/`equal_range` 为 O(count)），最坏 O(size)。没有 `lower_bound`/`upper_bound`——无序容器没有顺序。

### 桶接口（¶191–¶239）

| 表达式 | 语义 |
|---|---|
| `bucket_count()`、`max_bucket_count()` | 桶数 / 桶数上界，常数 |
| `bucket(k)` | 前置条件 `bucket_count() > 0`；返回键 `k` **会在**的桶号，∈ `[0, bucket_count())`，常数 |
| `bucket_size(n)` | 第 n 个桶的元素数，O(bucket_size(n)) |
| `begin(n)`/`end(n)`/`cbegin(n)`/`cend(n)` | 第 n 个桶的局部迭代器，常数 |
| `load_factor()` | 平均每桶元素数（[[g:load-factor]]），常数 |
| `max_load_factor()` | 容器**试图**保持的负载因子上界，正数 |
| `max_load_factor(z)` | 前置条件 `z` 为正；**可能**以 `z` 为提示改变最大负载因子 |
| `rehash(n)` | 后置条件：`bucket_count() >= size() / max_load_factor()` 且 `bucket_count() >= n`；平均线性，最坏平方 |
| `reserve(n)` | 等价于 `rehash(ceil(n / max_load_factor()))` |

注意 `bucket(k)` 的前置条件 `bucket_count() > 0`：默认构造的容器桶数未指明，可以是 0（本机 libc++ 正是 0），对它调用 `bucket(k)` 是 {{ub}}。

## operator== 的语义（¶240）

两个无序容器相等，当且仅当 `size()` 相等，并且对 `a` 的每个等价键组 `[Ea1, Ea2)`，`b.equal_range(Ea1)` 得到的组 `[Eb1, Eb2)` 使 `is_permutation(Ea1, Ea2, Eb1, Eb2)` 为真。也就是说，**比较的是多重集合，与迭代顺序和桶数无关**。

```cpp title="unordered-equality.cpp" run ok
#include <unordered_set>
#include <cassert>

int main() {
  std::unordered_multiset<int> a{1, 1, 2, 3}, b{3, 2, 1, 1};
  assert(a == b);                                 // 按等价键组做 is_permutation，而不是按迭代顺序
  std::unordered_set<int> c, d;
  for (int i = 0; i < 100; ++i) c.insert(i);
  for (int i = 99; i >= 0; --i) d.insert(i);
  d.rehash(1024);
  assert(c == d);                                 // 桶数与迭代顺序不同，仍相等
}
```

复杂度：唯一键版本平均 O(N)、最坏 O(N²)；等价键版本平均 O(ΣEᵢ²)（Eᵢ 为第 i 个等价键组的大小）、最坏 O(N²)，但若对应组内元素排列顺序相同（例如两者是同一容器的未修改副本），平均降为 O(N)。

!!! std
    The behavior of a program that uses operator== or operator!= on unordered containers is undefined unless the Pred function object has the same behavior for both containers and the equality comparison function for Key is a refinement of the partition into equivalent-key groups produced by Pred.

    除非两个容器的 Pred 行为相同，且 Key 的相等比较是 Pred 所产生的等价键组划分的"细化"，否则对无序容器使用 == 或 != 的行为未定义。

脚注 173 定义"细化"：相等比较为真的任意两个对象不会落入不同的划分。直觉上，`==` 可以比 `Pred` 更严格（`Pred` 认为等价的元素 `==` 可以认为不等），但不能更宽松。前面的大小写不敏感例子若换一个一致的哈希，`"abc"` 与 `"ABC"` 的 `==` 为假，而 `Pred` 认为它们等价——这是允许的；反过来，若 `Pred` 比 `==` 更严格，`operator==` 就是 {{ub}}。

## 迭代器类别与失效（¶241–¶244）

¶241：迭代器至少是前向迭代器；键类型即值类型时两种迭代器都是常量迭代器。

!!! std
    The insert, insert_range, and emplace members shall not affect the validity of references to container elements, but may invalidate all iterators to the container.

    插入成员不得影响元素引用的有效性，但可能使容器的全部迭代器失效。

¶242 还规定：擦除只使被擦除元素的迭代器和引用失效，并保持未被擦除元素的相对顺序。¶243 给出**不 rehash 的充分条件**：

!!! std
    The insert, insert_range, and emplace members shall not affect the validity of iterators if (N + n) <= z * B

    若 (N + n) <= z * B，则插入成员不得影响迭代器的有效性。

其中 N 是插入前元素数，n 是插入的元素数，B 是桶数，z 是最大负载因子。这是"边遍历边插入"或"保存迭代器跨插入"的唯一规范依据：先 `reserve`，就能保证在容量内插入不 rehash。

```cpp title="rehash-invalidation.cpp" run ok
#include <unordered_map>
#include <string>
#include <string_view>
#include <cassert>

struct SvHash {
  using is_transparent = void;                    // Hash 与 Pred 都必须透明
  std::size_t operator()(std::string_view s) const noexcept { return std::hash<std::string_view>{}(s); }
};

int main() {
  std::unordered_map<std::string, int, SvHash, std::equal_to<>> m{{"one", 1}, {"two", 2}};
  std::string_view k = "two";
  assert(m.find(k)->second == 2);                 // 不构造 std::string
  assert(m.contains("one"));

  std::unordered_map<int, int> u;
  u.reserve(1000);                                // 建立 (N + n) <= z * B 的条件
  int& ref = u[0];
  auto it = u.find(0);
  for (int i = 1; i < 1000; ++i) u[i] = i;        // 保证不 rehash：迭代器与引用都有效
  assert(&ref == &it->second);

  u.rehash(100000);                               // rehash：迭代器全部失效……
  ref = 42;                                       // ……但引用仍然有效
  assert(u.at(0) == 42);
}
```

¶244：`extract` 只使被取出元素的迭代器失效，保持其他元素的相对顺序；指针和引用仍有效，但元素归节点句柄所有期间经由它们访问是 {{ub}}，成功插入后失效——与有序容器相同。

## 透明哈希：双重选择加入（¶245）

`find`、`count`、`equal_range`、`contains`、`extract`、`erase`、`bucket` 的成员函数模板，只有在 `Pred::is_transparent` **和** `Hash::is_transparent` 都有效时才参与重载决议；`extract`/`erase` 还排除可转换为迭代器的实参。

为什么要求**两个**都透明？因为异构查找要先用 `Hash` 对异构键求哈希值、再用 `Pred` 比较——任何一个不支持异构实参，都会退化为"先转换成 `Key`"，失去异构查找的意义，甚至悄悄改变语义。`std::hash<std::string>` 本身不透明，所以必须像上例那样自己写一个带 `is_transparent` 的哈希器。

## 推导指引（¶246）

在以下情况不参与重载决议：`InputIterator`/`Allocator` 资格不符；`Hash` 推导为**整数类型**或具备分配器资格的类型（整数会被误当作桶数 `n`）；`Pred` 推导为具备分配器资格的类型。

## 异常安全（[unord.req.except]）

- ¶1：`clear()` 不抛；`erase(k)` 只可能因 `Hash` 或 `Pred` 抛出而抛出。
- ¶2：单元素插入中，**除哈希函数外**任何操作抛出，插入都无效果。哈希函数抛出时没有保证——因为实现可能已在计算哈希之前或之间做了 rehash 等准备工作。
- ¶3：`swap` 只可能因 `Hash` 或 `Pred` 的 `swap` 抛出而抛出。
- ¶4：`rehash()` 中**除哈希函数或比较函数外**的异常，使 `rehash` 无效果。

工程含义：让哈希函数 `noexcept`。

## 思考题

!!! question "`for (auto it = m.begin(); it != m.end(); ++it) if (cond(*it)) m.emplace(f(*it));` 在什么条件下是合法的？"

<details markdown="1">
<summary>展开查看答案与解析</summary>

即使不 rehash 也有问题。插入是否 rehash 由 ¶243 的 (N + n) ≤ z·B 决定：若循环前 `reserve` 了足够的容量，迭代器不会失效，循环本身不是 UB。但新插入的元素可能落在 `it` **之前**或**之后**的位置——迭代顺序未指明，所以新元素是否会被本次循环再次访问也是未指明的。若 `f` 产生的键又满足 `cond`，可能导致不可预期的多次插入。稳妥的做法是先把要插入的元素收集到一个临时容器，循环结束后再 `insert_range`。
</details>

## 小结

- `Hash` 与 `Pred` 必须一致：等价的键哈希相同；两者对同一键的结果都不能随时间改变。
- 插入**从不**使引用失效；rehash 使所有迭代器失效；(N + n) ≤ z·B 时保证不 rehash（先 `reserve`）。
- 插入/查找/擦除平均 O(1)、最坏 O(n)；提示可以被忽略。
- `==` 按等价键组做置换比较，与顺序和桶数无关；`Pred` 与 `Key::operator==` 不协调时是 UB。
- 异构查找需要 `Hash` 和 `Pred` **都**透明；哈希函数抛异常时单元素插入不再有强保证。
