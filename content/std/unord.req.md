---
title: 无序关联容器要求
summary: unordered_set、unordered_map 等哈希容器共同遵守的契约：哈希函数与相等谓词必须一致，桶与负载因子，rehash 使迭代器失效但不使引用失效，平均与最坏复杂度，以及 operator== 的含义。
status: done
covers: *
related: container.requirements, container.requirements.general, unord, associative.reqmts, container.node, hash.requirements, unord.hash
tags: 标准库, 容器, 无序容器, 哈希, rehash, 迭代器失效
updated: 2026-10-19
---

!!! tldr
    - 两个键按相等谓词等价时，哈希函数必须给出相同的值。换了相等谓词而不换哈希函数，通常就违反了这一点，行为未定义。
    - 插入从不使元素的指针和引用失效，但可能触发 rehash，使所有迭代器失效。只要插入后的元素数不超过 `max_load_factor() * bucket_count()`，就保证不 rehash，所以先 `reserve` 可以保住迭代器。
    - 查找、插入、擦除平均是常数时间，最坏是线性时间；插入时给的位置提示可以被实现忽略。
    - `==` 把两个容器当作多重集合比较，与迭代顺序和桶数无关。
    - 异构查找要求哈希函数和相等谓词都声明 `is_transparent`。

C++11 加入了四个**无序关联容器**：`unordered_set`、`unordered_map`、`unordered_multiset`、`unordered_multimap`。它们用哈希表组织元素，查找平均是常数时间，最坏是线性时间（¶1）。本节规定它们共同的要求，各容器自己的条款见 [[unord]]。和有序关联容器（[[associative.reqmts]]）相比，最需要注意的是两件事：哈希函数与相等谓词必须一致，以及 rehash 会使所有迭代器失效。

## 哈希函数与相等谓词必须一致 [unord.req.general]

```cpp title="hash-pred-mismatch.cpp" run ub
#include <cctype>
#include <cstdio>
#include <string>
#include <unordered_set>

struct CaseInsensitiveEq {
  bool operator()(const std::string& a,
                  const std::string& b) const {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i)
      if (std::tolower((unsigned char)a[i]) !=
          std::tolower((unsigned char)b[i]))
        return false;
    return true;
  }
};

int main() {
  // UB: "ABC" 与 "abc" 按 Pred 等价，哈希值却不同
  std::unordered_set<std::string, std::hash<std::string>,
                     CaseInsensitiveEq> s{"abc"};
  std::printf("%d\n", s.contains("ABC"));
}
```

本机打印 `0`：`"ABC"` 的哈希值把查找带到了另一个桶，`CaseInsensitiveEq` 根本没有机会被调用。换一组字符串或换一个桶数，结果可能变成 `1`。标准对这个程序没有任何要求。

¶3 每个无序容器有三个类型参数：键类型 `Key`；满足 *Cpp17Hash* 要求（[[hash.requirements]]）的哈希函数类型 `Hash`；在 `Key` 上诱导等价关系的二元谓词 `Pred`。`unordered_map` 系还把一个映射类型 `T` 关联到键上。¶4 容器中的 `Hash` 对象叫**哈希函数**，`Pred` 对象叫**键相等谓词**（key equality predicate）。

¶5 如果 `pred(k1, k2)` 有效且为真，两个键就是**等价**的。

!!! std
    If k1 and k2 are equivalent, the container's hash function shall return the same value for both.

注 1 指出了后果：用了非默认的 `Pred`，通常也需要非默认的 `Hash`。上例的修正办法是给 `CaseInsensitiveEq` 配一个先把字符串转成小写再求哈希的哈希函数。

同一段还要求，对容器中任意两个键，`pred(k1, k2)` 总是返回同样的值；对容器中任意键 `k`，`hash(k)` 总是返回同样的值。

## 桶、负载因子与 rehash（¶9）

¶9 元素被组织在若干**桶**（[[g:bucket]]）里，哈希值相同的键在同一个桶中。平均每个桶的元素个数叫**负载因子**（[[g:load-factor]]）。随着元素增加，容器自动增加桶的个数，使负载因子保持在 `max_load_factor()` 之下。把元素重新分配到新的桶数组中，叫作 **rehash**。

!!! std
    Rehashing invalidates iterators, changes ordering between elements, and changes which buckets elements appear in, but does not invalidate pointers or references to elements.

rehash 不使指针和引用失效，这一句决定了实现方式：每个元素必须有自己稳定的地址，通常每个元素一个节点，同一个桶里的节点连成链表。把元素直接存放在槽位数组里的开放寻址实现，rehash 时要搬动元素，不符合这个要求。

对 `unordered_multiset` 和 `unordered_multimap`，rehash 保持等价元素的相对顺序。

### 桶接口（¶192–¶239）

| 表达式 | 含义 |
|---|---|
| `bucket_count()` | 桶的个数 |
| `bucket(k)` | 键 `k` 所在（或将在）的桶号；前置条件 `bucket_count() > 0` |
| `bucket_size(n)`、`begin(n)`、`end(n)` | 第 `n` 个桶的元素个数和局部迭代器 |
| `load_factor()` | 平均每桶的元素个数 |
| `max_load_factor()` / `max_load_factor(z)` | 容器试图保持的负载因子上界；设置时 `z` 只是提示 |
| `rehash(n)` | 之后 `bucket_count() >= n` 且 `bucket_count() >= size() / max_load_factor()` |
| `reserve(n)` | 等价于 `rehash(ceil(n / max_load_factor()))` |

局部迭代器（`local_iterator`）只能在一个桶里遍历，不能跨桶（¶21–¶22）。

默认构造的容器桶数未指明（¶33），可以是 0。本机 libc++ 默认构造的 `unordered_set<int>` 的 `bucket_count()` 正是 0，对它调用 `bucket(k)` 违反前置条件，是 {{ub}}。[[unord]] 中的各容器进一步规定，默认构造时的桶数由实现定义，`max_load_factor()` 的初始值是 1.0。

## 失效规则（¶242–¶244）

!!! std
    The insert, insert_range, and emplace members shall not affect the validity of references to container elements, but may invalidate all iterators to the container.

¶242 插入从不使元素的引用失效，但可能使容器的所有迭代器失效，因为插入可能触发 rehash。擦除只使被擦除元素的迭代器和引用失效，并保持其余元素的相对顺序。

¶243 给出了不 rehash 的充分条件：

!!! std
    The insert, insert_range, and emplace members shall not affect the validity of iterators if (N + n) <= z * B

其中 N 是插入前的元素个数，n 是插入的元素个数，B 是桶数，z 是最大负载因子。这是在插入后继续使用旧迭代器的唯一依据：先 `reserve(N + n)`，在这个容量之内插入就不会 rehash。

```cpp title="rehash-invalidation.cpp" run ok
#include <cassert>
#include <unordered_map>

int main() {
  std::unordered_map<int, int> u;
  u.reserve(1000);          // 保证 (N + n) <= z * B
  int& ref = u[0];
  auto it = u.find(0);
  for (int i = 1; i < 1000; ++i)
    u[i] = i;               // 不 rehash：迭代器和引用都有效
  assert(&ref == &it->second);

  u.rehash(100000);         // rehash：迭代器全部失效
  ref = 42;                 // 引用仍然有效
  assert(u.at(0) == 42);
}
```

¶244 `extract` 只使被取出元素的迭代器失效，指针和引用仍然有效；但元素归节点句柄所有期间，经由它们访问元素是 {{ub}}，元素被成功插入后它们失效。这和有序容器的规则相同（[[associative.reqmts#176]]、[[container.node]]）。

## 唯一键、等价键与等价键组（¶6–¶8）

¶6 `unordered_set` 和 `unordered_map` 支持唯一键，`multi` 版本支持等价键。在等价键容器中，键等价的元素在迭代顺序中彼此相邻。元素的绝对顺序未指明，但它们被分成若干**等价键组**（[[g:equivalent-key-group]]），每组内的键都等价。除非另有规定，修改操作要保持每个组内元素的相对顺序。

¶7–¶8 值类型和迭代器的规定与有序容器相同：`set` 系的值类型是 `Key`，`map` 系是 `pair<const Key, T>`；值类型就是键类型时，`iterator` 和 `const_iterator` 都是常量迭代器，是否同一类型未指明，函数形参应当写 `const_iterator`。¶241 补充，迭代器至少是前向迭代器。

## 复杂度

要求表（¶11–¶239）中的复杂度大多是平均和最坏两档。最坏情况出现在大量键落进同一个桶的时候，例如哈希函数很差，或者有人刻意构造了冲突的键。

| 操作 | 平均 | 最坏 |
|---|---|---|
| `X(n, hf, eq)` 等指定桶数的构造 | O(n) | O(n) |
| 区间构造、复制构造、复制赋值 | O(N) | O(N²) |
| `emplace`、`insert(t)`、`insert(nh)` | O(1) | O(size) |
| `insert(i, j)`、`insert_range(rg)` | O(N) | O(N · (size + 1)) |
| `find`、`contains`、`extract`、`erase(q)` | O(1) | O(size) |
| `count(k)`、`equal_range(k)`、`erase(k)` | O(count(k)) | O(size) |
| `rehash(n)` | O(size) | O(size²) |

`emplace_hint(p, …)` 和 `insert(p, t)` 中的 `p` 只是开始搜索的位置，实现可以忽略它（¶89、¶103）。与有序容器不同，`multi` 版本的插入没有规定新元素在等价键组中的位置，只要求等价的元素相邻。

无序容器没有 `lower_bound` 和 `upper_bound`，因为元素没有顺序。

### merge（¶143–¶147）

`a.merge(a2)` 用 `a` 的哈希函数和相等谓词，把 `a2` 的元素逐个取出插入 `a`；唯一键容器中已有等价键的元素留在 `a2`。前置条件是两者的分配器相等。

¶146 被转移元素的指针和引用继续指向原元素，现在属于 `a`。但和有序容器不同，被转移元素的迭代器以及 `a` 的所有迭代器都会失效，因为合并可能触发 rehash；`a2` 中剩余元素的迭代器保持有效。

## operator== 比较的是多重集合（¶240）

```cpp title="unordered-equality.cpp" run ok
#include <cassert>
#include <unordered_set>

int main() {
  std::unordered_multiset<int> a{1, 1, 2, 3}, b{3, 2, 1, 1};
  assert(a == b);
  std::unordered_set<int> c, d;
  for (int i = 0; i < 100; ++i) c.insert(i);
  for (int i = 99; i >= 0; --i) d.insert(i);
  d.rehash(1024);
  assert(c == d);   // 桶数和迭代顺序不同，仍然相等
}
```

¶2 指出无序容器的 `==` 与其他容器语义不同。¶240 规定，两个无序容器相等，当且仅当 `size()` 相等，并且对 `a` 的每个等价键组，`b` 中对应的等价键组是它的一个排列（`is_permutation` 为真）。所以比较结果与迭代顺序和桶数无关。

复杂度：唯一键版本平均 O(N)，最坏 O(N²)。等价键版本平均是各等价键组大小的平方和，最坏 O(N²)；如果对应的组内元素排列顺序相同（例如两个容器是同一个容器未经修改的副本），平均降到 O(N)。

¶240 最后还有一个 UB 条件：

!!! std
    The behavior of a program that uses operator== or operator!= on unordered containers is undefined unless the Pred function object has the same behavior for both containers and the equality comparison function for Key is a refinement of the partition into equivalent-key groups produced by Pred.

脚注 173 解释了细化（refinement）：任何两个 `==` 为真的对象，都不会落在不同的等价键组里。换句话说，`Key` 的 `==` 可以比 `Pred` 更严格，不能更宽松。如果给前面的大小写不敏感容器配上一致的哈希函数，`"abc" == "ABC"` 为假而 `Pred` 认为它们等价，这是允许的；反过来，`Pred` 比 `==` 更严格时，对容器使用 `==` 就是 {{ub}}。

## 异构查找要求两者都透明（¶10、¶245）

```cpp title="transparent-hash.cpp" run ok
#include <cassert>
#include <string>
#include <string_view>
#include <unordered_map>

struct SvHash {
  using is_transparent = void;   // 哈希函数也必须透明
  std::size_t operator()(std::string_view s) const noexcept {
    return std::hash<std::string_view>{}(s);
  }
};

int main() {
  std::unordered_map<std::string, int, SvHash,
                     std::equal_to<>> m{{"one", 1}, {"two", 2}};
  std::string_view k = "two";
  assert(m.find(k)->second == 2);   // 不构造 std::string
  assert(m.contains("one"));
}
```

¶245 `find`、`count`、`equal_range`、`contains`、`extract`、`erase`、`bucket` 的成员函数模板版本，只有在 `Pred::is_transparent` 和 `Hash::is_transparent` 都有效时才参与重载决议；`extract` 和 `erase` 的模板版本还排除可以转换为迭代器的实参。

为什么两个都要透明？异构查找先用 `Hash` 对实参求哈希值，再用 `Pred` 比较。任何一方不接受异构实参，都只能先把实参转换成 `Key`，异构查找就失去了意义。`std::hash<std::string>` 不透明，所以需要像上例那样自己写一个。

¶10 规定了异构实参 `ke`、`kx` 的条件。设 `r1`、`r2` 是容器中元素的键：

- 对称：`eq(r1, ke) == eq(ke, r1)`；
- 哈希一致：`eq(r1, ke)` 为真时，`hf(r1) == hf(ke)`；
- 传递：`eq(r1, ke)`、`eq(r2, ke)`、`eq(r1, r2)` 中任意两个为真，则三个都为真。

`kx`（用于 `erase` 和 `extract`）还要求不能转换为迭代器。也就是说，异构的键要像一个真正的键那样融入 `Pred` 的等价划分，并哈希到同一个值。

## 异常安全 [unord.req.except]

¶1 `clear()` 不抛异常；`erase(k)` 只可能因 `Hash` 或 `Pred` 对象抛出而抛出。

¶2 插入单个元素时，除哈希函数以外的任何操作抛出异常，插入都没有效果。哈希函数抛出时没有这个保证。

¶3 `swap` 只可能因 `Hash` 或 `Pred` 的 `swap` 抛出而抛出。

¶4 `rehash()` 中，除哈希函数或比较函数以外的操作抛出异常时，`rehash()` 没有效果。

所以哈希函数最好是 `noexcept` 的。

## 思考题

!!! question "思考题"
    下面的循环在什么条件下没有 UB？即使没有 UB，它的行为确定吗？
    ```cpp
    for (auto it = m.begin(); it != m.end(); ++it)
      if (cond(*it)) m.emplace(f(*it));
    ```

<details markdown="1">
<summary>答案</summary>

插入是否 rehash 由第 243 段决定。如果循环前 `reserve` 了足够的容量，使 (N + n) ≤ z·B 始终成立，迭代器不会失效，循环本身没有 UB。

但行为仍不确定。新插入的元素可能落在 `it` 之前，也可能落在之后，迭代顺序未指明，所以新元素会不会在本次循环中再被访问也是未指明的。如果 `f` 产生的键又满足 `cond`，还可能连锁插入。稳妥的做法是先把要插入的元素收集到一个临时容器，循环结束后再 `insert_range`。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

¶10 还定义了要求表中的其他记号：`a_uniq`、`a_eq` 分别表示唯一键和等价键容器，`a_tran` 表示 `key_equal::is_transparent` 和 `hasher::is_transparent` 都有效时的容器，`hf`、`eq` 分别是哈希函数和相等谓词的值，`n` 是 `size_type` 的值，`z` 是 `float` 的值。

¶11 `X` 满足无序关联容器要求，当且仅当它满足分配器感知容器的全部要求，并且要求表中的表达式良构且语义正确。对 `unordered_map` 系，对 `value_type` 的要求改为施加于 `key_type` 和 `mapped_type`。

¶12–¶23 规定嵌套类型：`hasher` 是 `Hash`，要求 `hf(k)` 的类型是 `size_t`；`key_equal` 是 `Pred`，要求可复制构造，并且是 `Key` 上的等价关系；`local_iterator` 的类别、值类型、差类型、指针和引用类型都与 `iterator` 相同；`node_type` 是节点句柄模板的特化。

¶63、¶66 复制构造和复制赋值除了复制元素，还复制哈希函数、相等谓词和最大负载因子。

¶246 推导指引在为 `Hash` 推导出整数类型或分配器类型时不参与重载决议，因为整数实参通常是桶数；为 `Pred` 推导出分配器类型时同样不参与。

</details>
