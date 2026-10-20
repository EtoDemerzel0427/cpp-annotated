---
title: 容器的选择：复杂度之外
summary: 复杂度相同或更好的容器为什么常常更慢：在本机用 10 到 100 万个元素实测 vector、deque、list，map、unordered_map、flat_map 与有序 vector，reserve 和坏哈希，小集合，字符串键的异构查找，每个元素的内存开销，最后说明节点容器真正的用处是迭代器和引用的稳定性。
status: draft
order: 85
group: 代码
since: c++98
papers: N3657, P0919R3, P1690R1, P0429R9, P1222R4
related: vector, deque, list, map, unord.map, flat.map, flat.set, bitset, vector.modifiers, deque.modifiers, list.modifiers, associative.reqmts.general, unord.req.general, flat.map.overview, topics/dangling-references, topics/allocators-and-pmr, perf/measuring, perf/memory-hierarchy, perf/allocation, perf/vectorization
tags: 性能, 容器, vector, list, map, unordered_map, flat_map, 哈希, 异构查找, 内存开销
updated: 2026-10-19
---

!!! tldr
    - 复杂度只描述规模变大时的增长趋势，不包含常数。实际的常数主要来自内存访问：连续存储能被缓存和预取器利用，节点容器每走一步都可能是一次缓存未命中。
    - 在本机测得的数据里，维护一个有序序列（线性查找位置再插入），`vector<int>` 在 10 到 100 万个元素的每个规模上都比 `list<int>` 快，100 万个元素时快约 3.7 倍。元素有 256 字节时，`list` 在几十到几千个元素之间领先，规模再大又落后。
    - 查找为主时，`unordered_map` 最快；`flat_map` 和有序 `vector` 的查找比 `map` 快几倍，遍历快两三个数量级，但逐个插入是线性的，应当先收集再排序。哈希表要提前 `reserve`，哈希函数要能把键分散开，否则查找会退化成遍历链表。
    - `std::string` 作键时，用 `is_transparent` 打开异构查找，`find` 就能直接接受 `string_view`，长键查找省掉一次分配，本机快 2.3 倍。
    - 节点容器每个元素多占 16 到 40 字节，真正的理由是插入、rehash 不使引用失效。需要长期持有元素的指针或引用时选它们，否则先选 `vector`。

## 一个复杂度说不清的结果

维护一个有序序列：每来一个新值，从头线性查找第一个不小于它的元素，在那里插入。`std::list` 的插入是常数时间（[[list.modifiers#1]]），`std::vector` 的插入要把后面的元素逐个后移，是线性时间（[[vector.modifiers#1]]）。只看复杂度，`list` 应该赢。

下面每个操作先线性查找，再插入，再把刚插入的元素删掉，使容器大小保持为 N；元素是随机值，所以平均要走过一半元素。

```cpp
// 每次操作：找到位置、插入、再删除
int v = int(rng() % (2 * n));
auto it = std::find_if(c.begin(), c.end(),
                       [&](int x) { return x >= v; });
it = c.insert(it, v);
c.erase(it);
```

| N | `vector<int>` | `deque<int>` | `list<int>` |
|---:|---:|---:|---:|
| 10 | 32 ns | 33 ns | 38 ns |
| 100 | 35 ns | 60 ns | 80 ns |
| 1 000 | 120 ns | 293 ns | 516 ns |
| 10 000 | 1.05 µs | 2.52 µs | 5.93 µs |
| 100 000 | 11.6 µs | 24.0 µs | 63.0 µs |
| 1 000 000 | 107 µs | 159 µs | 391 µs |

`vector` 在每个规模上都最快。两者的总复杂度其实相同：查找已经是线性的，`list` 省下的只是插入那一步。问题在于两个线性过程的常数相差很大。`vector` 的查找和移动都是在一段连续内存上顺序读写，`memmove` 一次能搬几十字节；`list` 的查找每走一步都要先从节点里读出下一个节点的地址，才能发出下一次读取。

这一页的其余部分按同样的方式，把常见的选择逐一放到本机上测量。

## 怎样测的

所有数字都来自同一台机器：Apple M2 Pro，macOS，Homebrew Clang 23.1 加 libc++，arm64，编译命令是

```bash
clang++ -std=c++2c -O2 -Wall -Wextra -pedantic seq.cpp -o seq && ./seq
```

计时框架和 [[perf/measuring#harness|bench.hpp]] 的做法相同：被测代码放进 lambda，连续调用固定次数作为一个样本，先跑一轮预热，再取若干个样本；结果用 `do_not_optimize`（一条不生成指令的内联汇编，让编译器认为这个值被读取了，从而不能删掉算出它的代码）保留下来。和那一页不同的是，这里报告样本中的最小值而不是中位数。测量时机器上同时运行着大量其他进程，干扰只会让一个样本变慢，不会让它变快，最小值最接近不受干扰的时间。

```cpp
template <class F>
double bench(F&& f, long inner, int reps = 9) {
  using clk = std::chrono::steady_clock;
  for (long i = 0; i < inner; ++i) f();   // 预热
  std::vector<double> s;
  for (int r = 0; r < reps; ++r) {
    auto t0 = clk::now();
    for (long i = 0; i < inner; ++i) f();
    auto t1 = clk::now();
    s.push_back(std::chrono::duration<double, std::nano>(t1 - t0).count() / inner);
  }
  return *std::min_element(s.begin(), s.end());
}
```

即便如此，同一个程序在不同时刻运行，大规模那几行的绝对值仍会相差到 2 倍左右（例如 100 万个元素的 `map` 查找，两次运行分别是 545 ns 和 1.3 µs）。各列之间的相对关系在多次运行中保持不变，下文的结论只依赖这种相对关系。换一台机器、换一个标准库，具体数字和交叉点都会移动，读者应该用自己的数据重测。

## 序列容器

### 在末尾追加

| N | `vector` | `vector` + `reserve` | `deque` | `list` |
|---:|---:|---:|---:|---:|
| 10 | 22 ns | 3.2 ns | 6.7 ns | 38 ns |
| 100 | 5.0 ns | 1.0 ns | 1.4 ns | 47 ns |
| 1 000 | 0.96 ns | 0.79 ns | 0.94 ns | 35 ns |
| 100 000 | 0.64 ns | 0.77 ns | 0.95 ns | 49 ns |
| 1 000 000 | 0.62 ns | 0.77 ns | 0.94 ns | 47 ns |

表中是每个元素的平均时间，包括建好 N 个元素的容器再把它销毁。`list` 每个元素都要一次 `operator new` 和一次 `operator delete`，所以不管规模多大都是几十纳秒；一次分配本身的代价见 [[perf/allocation|堆分配的代价]]。

`vector` 不预留容量时，小规模下的代价集中在扩容：libc++ 每次把容量翻倍，10 个元素要经历 5 次分配。`reserve` 把它们合并成一次，10 个元素时快 7 倍。规模大了以后，扩容的次数是对数级的，被摊薄到每个元素不到 1 ns，两者的差别落在测量噪声的量级里（这几次运行中不预留的版本反而稍快，原因本页没有追究）。`deque` 按固定大小的块分配，介于两者之间。

### 遍历

| N | `vector` | `deque` | `list`，按顺序建立 | `list`，链接顺序打乱 |
|---:|---:|---:|---:|---:|
| 100 | 0.057 ns | 0.59 ns | 1.08 ns | 0.81 ns |
| 10 000 | 0.039 ns | 0.61 ns | 1.68 ns | 9.2 ns |
| 1 000 000 | 0.046 ns | 0.46 ns | 1.36 ns | 92 ns |

每个元素 0.04 ns，意味着一个时钟周期处理十个以上的 `int`。只有向量化才能做到这一点：

```cpp
long sum_vec(const std::vector<int>& c) {
  long s = 0;
  for (int x : c) s += x;
  return s;
}
```

`-O2` 下，Clang 23 为它生成的主循环每次迭代读 64 字节，用 `saddw`/`saddw2` 把 4 字节的 `int` 扩展成 8 字节累加到 8 个向量寄存器里；同样的循环换成 `std::list<int>`，循环体只剩追指针：

```text
LBB1_2:                       ; sum_list 的循环
    ldrsw   x10, [x9, #16]    ; 读出节点里的值
    add     x8, x8, x10
    ldr     x9, [x9, #8]      ; 读出 next，下一轮才能开始
    cmp     x9, x0
    b.ne    LBB1_2
```

下一次读取的地址取决于这一次读取的结果，CPU 无法提前发出请求。节点按顺序分配时，它们在内存里大体相邻，读取多半命中缓存，每个元素 1 ns 左右；`sort` 之后链接顺序与地址顺序无关，100 万个元素时每一步都要等一次内存，92 ns。真实程序里反复插入删除的链表接近后一种情况。这里的机制、缓存延迟的测法见 [[perf/memory-hierarchy|缓存、局部性与数据布局]]，向量化见 [[perf/vectorization]]。

`deque` 的迭代器每一步都要检查是否走到了当前块的末尾，循环没有被向量化，所以比 `vector` 慢一个数量级，但它的块是连续的，不受打乱的影响。

### 中间插入：交叉点在哪里

开头的表用的是 4 字节的 `int`，移动元素很便宜。把元素换成 256 字节的结构体（键加填充），移动的代价增加 64 倍，而 `list` 的插入完全不移动元素：

| N | `vector<Big>` | `deque<Big>` | `list<Big>` |
|---:|---:|---:|---:|
| 10 | 47 ns | 62 ns | 39 ns |
| 100 | 345 ns | 239 ns | 83 ns |
| 1 000 | 3.91 µs | 2.22 µs | 2.50 µs |
| 10 000 | 44.4 µs | 26.6 µs | 27.4 µs |
| 100 000 | 542 µs | 348 µs | 2 206 µs |

现在出现了交叉点。`list` 在 10 到 1 000 个元素之间领先或接近领先；到了 10 万个元素，27 MB 的节点装不进缓存，追指针的代价又超过了 `vector` 的批量移动。

`deque` 在大元素时一直比 `vector` 快，原因写在它的复杂度要求里：在中间插入的代价与到两端距离中较小的那一个成正比（[[deque.modifiers#2]]），实现会移动较短的那一侧，平均移动 N/4 个元素；`vector` 总是移动插入点之后的所有元素，平均 N/2 个（[[vector.modifiers#1]]）。

还要注意这个测试对 `list` 很有利：它是按顺序建立的，每次删掉的节点又被下一次插入复用，节点始终大体连续。`list` 真正有优势的场合，是插入位置已经以迭代器的形式拿在手里，不需要查找。

## 查找表：`map`、`unordered_map`、`flat_map`、有序 `vector`

`std::map` 是一棵红黑树，每个元素一个节点。`std::unordered_map` 是带链表的哈希表，同样每个元素一个节点。`std::flat_map`（{{c++23}}，[[P0429R9]]）是一个容器适配器，它把键和值分别放在两个有序的序列容器里，默认是两个 `vector`（[[flat.map.overview#5]]）。有序 `vector<pair<K, V>>` 加 `std::lower_bound` 是它的手写版本，区别是键和值交错存放。

本机 libc++ 提供 `<flat_map>` 和 `<flat_set>`（`flat_set` 是同样思路的集合版本，[[P1222R4]]），`__cpp_lib_flat_map` 的值是 `202511`。

下面三张表的键和值都是随机的 64 位整数。

### 查找

每次查找一个已经存在的键，按随机顺序：

| N | `map` | `unordered_map` | `flat_map` | 有序 `vector` |
|---:|---:|---:|---:|---:|
| 10 | 2.9 ns | 2.5 ns | 4.0 ns | 3.1 ns |
| 100 | 4.8 ns | 2.3 ns | 7.7 ns | 6.7 ns |
| 1 000 | 7.1 ns | 3.6 ns | 12.9 ns | 11.7 ns |
| 10 000 | 59 ns | 7.6 ns | 27 ns | 28 ns |
| 100 000 | 103 ns | 10.7 ns | 44 ns | 44 ns |
| 1 000 000 | 545 ns | 28 ns | 95 ns | 70 ns |

三种有序结构都要比较约 log₂N 次，差别在于每次比较之前要读的那块内存在哪里。`map` 的每一层都是一个单独分配的节点，规模一大，几乎每层都是一次缓存未命中。二分查找在一个连续数组上跳，最初几步跳得远，也会未命中，但最后几步落在同一个缓存行里，而且数组比同样内容的树小得多。几千个元素以内，三者都在缓存里，`map` 甚至略快，因为二分查找的分支难以预测。

`unordered_map` 平均只看一个桶，读一个节点，在所有规模上都最快。代价是它不维持顺序，也不支持按范围查找。

### 插入

从空容器开始，逐个插入 N 个随机键，表中是每个元素的平均时间。最后一列不逐个插入，而是先全部 `push_back` 到 `vector` 里，再 `std::sort` 一次：

| N | `map` | `unordered_map` | `unordered_map` + `reserve` | `flat_map` | 有序 `vector` | 收集后排序 |
|---:|---:|---:|---:|---:|---:|---:|
| 10 | 57 ns | 81 ns | 48 ns | 91 ns | 20 ns | 14 ns |
| 100 | 92 ns | 82 ns | 47 ns | 44 ns | 33 ns | 7.0 ns |
| 1 000 | 117 ns | 69 ns | 71 ns | 109 ns | 186 ns | 14 ns |
| 10 000 | 179 ns | 90 ns | 68 ns | 1.50 µs | 2.32 µs | 80 ns |
| 100 000 | 378 ns | 146 ns | 85 ns | 28.3 µs | 27.5 µs | 54 ns |
| 1 000 000 | 1.03 µs | 438 ns | 260 ns | 未测 | 未测 | 117 ns |

`flat_map` 的单个插入是线性的，这一点标准明说了（[[flat.map.overview#2.3]]）：100 个元素以内它比 `map` 快，1 000 个时持平，10 万个时慢 75 倍。100 万个元素逐个插入，平均每次要移动 50 万个键和 50 万个值，总共约 4×10¹² 字节，没有测。

所以 `flat_map` 和有序 `vector` 适合读多写少、可以成批建立的数据。成批建立时，收集后排序在每个规模上都比任何逐个插入快。`flat_map` 有接受已排序数据的构造函数（以 `std::sorted_unique` 为标签），可以跳过排序。

### 遍历

| N | `map` | `unordered_map` | `flat_map` | 有序 `vector` |
|---:|---:|---:|---:|---:|
| 100 | 2.4 ns | 0.80 ns | 0.069 ns | 0.12 ns |
| 10 000 | 15 ns | 5.1 ns | 0.078 ns | 0.19 ns |
| 1 000 000 | 167 ns | 36 ns | 0.094 ns | 0.20 ns |

`map` 的节点是按插入顺序分配的，插入的键是随机的，按键的顺序遍历就是在内存里随机跳，100 万个元素时每一步都是一次内存延迟，和打乱的 `list` 一样。`flat_map` 只读值所在的那个 `vector`，循环被向量化；有序 `vector` 要跨过交错存放的键，读的内存多一倍。

## 哈希表：`reserve` 与坏哈希

### 预留桶

`unordered_map` 默认的最大负载因子（平均每个桶的元素数上限）是 1.0（[[unord.map.cnstr#1]]）。元素数超过桶数时，容器分配一个更大的桶数组，把所有节点重新挂到新的桶上，这叫 [[g:rehash]]。`reserve(n)` 一开始就把桶数设得足够容纳 n 个元素（[[unord.req.general#239]]）。上一节的插入表里，100 万个元素时它把每个元素的插入时间从 438 ns 降到 260 ns。

`reserve` 还有一个和速度无关的作用：只要插入后的元素数不超过桶数乘以最大负载因子，插入就不使迭代器失效（[[unord.req.general#243]]）。

### 哈希函数决定一切

`unordered_map` 的平均常数时间建立在哈希值分散的前提上。标准给出的最坏情况是线性的（[[unord.req.general#174]]），当所有键落进同一个桶时就会发生。下面用三个哈希函数比较：

```cpp
struct Low8 {    // 只有 256 种不同的哈希值
  std::size_t operator()(std::uint64_t k) const { return k & 0xFF; }
};
struct Const {   // 所有键都冲突
  std::size_t operator()(std::uint64_t) const { return 0; }
};
```

| 哈希 | N | 插入（每元素） | 查找 | 最长的桶 |
|---|---:|---:|---:|---:|
| `std::hash`，随机键 | 100 000 | 61 ns | 12 ns | 7 |
| `std::hash`，键为 `i << 12` | 100 000 | 33 ns | 3.2 ns | 1 |
| `Low8` | 100 000 | 1.45 µs | 1.26 µs | 443 |
| `Const` | 1 000 | 2.13 µs | 990 ns | 1 000 |
| `Const` | 10 000 | 9.85 µs | 9.88 µs | 10 000 |

`Low8` 把 10 万个键挤进 256 个桶，查找慢了 100 倍；`Const` 让哈希表退化成一个链表，每次查找和插入都要遍历全部元素，建一个 1 万个元素的表就要 0.1 秒。插入同样变慢，因为插入一个唯一键之前要先在桶里确认它不存在。

第二行看起来应该很糟：本机 libc++ 的 `std::hash<std::uint64_t>` 直接返回键本身（`std::hash<std::uint64_t>{}(12345)` 输出 12345），而 `i << 12` 的低 12 位全是 0。它没有出问题，是因为 libc++ 的桶数是素数（表中为 102 877），取模会用到哈希值的所有位。如果一个哈希表实现用 2 的幂作桶数、直接取哈希值的低位，同样的键会集中到极少数桶里。哈希值的质量要求是实现与使用者之间的约定，标准只要求相等的键哈希值相等，并且对不相等的键，哈希值相同的概率应当很小（[[hash.requirements]]），没有规定 `std::hash` 怎样实现。

!!! pitfall "攻击者可以选择键"
    如果键来自外部输入（HTTP 头、JSON 字段名），而哈希函数是公开且固定的，攻击者可以专门构造落进同一个桶的键，让服务器退化成上表的 `Const` 行。对外的服务应当使用带随机种子的哈希函数。

## 小集合

元素很少时，常数就是一切。下面的集合里有 N 个互不相同的 `uint8_t` 键，每次查询一个随机的 `uint8_t`，命中率约为 N/256：

| N | 无序 `vector` + `find` | 有序 `vector` + `binary_search` | `set` | `unordered_set` | `flat_set` | `bitset<256>` |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 1.7 ns | 2.2 ns | 2.6 ns | 1.8 ns | 2.1 ns | 0.37 ns |
| 16 | 2.2 ns | 3.8 ns | 6.6 ns | 1.8 ns | 3.8 ns | 0.37 ns |
| 64 | 4.4 ns | 5.3 ns | 12.8 ns | 2.5 ns | 5.4 ns | 0.37 ns |
| 128 | 6.1 ns | 6.5 ns | 15.8 ns | 2.2 ns | 6.5 ns | 0.37 ns |

键的取值范围小到可以逐一列举时，`std::bitset`（或一个 `bool` 数组）把查找变成一次移位和一次按位与，与 N 无关（[[bitset]]）。不满足这个条件时，几十个元素以内，线性扫描一个连续数组不输给二分查找，`std::set` 在所有规模上都最慢。

这里的 `unordered_set` 处在理想状况：`std::hash` 是恒等函数，256 个可能的键彼此不冲突。键是字符串时，计算哈希本身就要读完整个键，小集合上它未必还能赢。

## 字符串键与异构查找

用 `std::string` 作键很常见，而查询用的键往往是从缓冲区里切出来的 `std::string_view`。`std::string` 从 `string_view` 构造是 `explicit` 的，默认的 `unordered_map<std::string, int>::find` 只接受 `const std::string&`：

```cpp title="het-error.cpp" error
#include <string>
#include <string_view>
#include <unordered_map>
int main() {
  std::unordered_map<std::string, int> prices;
  std::string_view sym = "AAPL";
  prices.find(sym);   // error: string_view 不能隐式转换为 string
}
```

调用方只好写 `prices.find(std::string(sym))`，每次查找都构造一个临时字符串。键超过 SSO（短字符串优化：短字符串直接存在 `std::string` 对象内部，本机 libc++ 最多 22 个字符）的长度时，这意味着一次堆分配。

**异构查找**（heterogeneous lookup）让 `find` 直接接受与键类型不同、但可以和键比较的参数。它是按容器打开的：有序容器要求比较器有一个名为 `is_transparent` 的成员类型（[[associative.reqmts.general#180]]，C++14，[[N3657]]），无序容器要求哈希函数和相等比较器都有（[[unord.req.general#245]]，C++20，[[P0919R3]]、[[P1690R1]]）。这样的比较器叫 [[g:transparent-comparator|透明比较器]]，`std::less<>` 和 `std::equal_to<>` 就是现成的例子。

```cpp title="het.cpp" run ok
#include <cstdio>
#include <functional>
#include <string>
#include <string_view>
#include <unordered_map>

struct SvHash {
  using is_transparent = void;
  std::size_t operator()(std::string_view s) const {
    return std::hash<std::string_view>{}(s);
  }
};

int main() {
  std::unordered_map<std::string, int,
                     SvHash, std::equal_to<>> prices;
  prices["AAPL240119C00190000"] = 7;
  std::string_view line = "AAPL240119C00190000,buy";
  std::string_view sym = line.substr(0, line.find(','));
  if (auto it = prices.find(sym); it != prices.end())  // 不构造 std::string
    std::printf("%d\n", it->second);
}
```

`SvHash` 对 `std::string` 和 `std::string_view` 用同一个函数，所以相等的两者得到相同的哈希值，这是透明哈希必须满足的条件。有序容器只需要把比较器换成 `std::less<>`：`std::map<std::string, int, std::less<>>`。

本机对 1 万个键各查找一次，`allocs` 是用替换的全局 `operator new` 数出的每次查找的分配次数：

| 键长 | 容器 | `find(std::string(sv))` | `find(sv)`，透明 |
|---:|---|---:|---:|
| 16 | `unordered_map` | 18.8 ns，0 allocs | 15.1 ns，0 allocs |
| 40 | `unordered_map` | 47.4 ns，1 alloc | 20.4 ns，0 allocs |
| 16 | `map` | 118 ns，0 allocs | 116 ns，0 allocs |
| 40 | `map` | 166 ns，1 alloc | 133 ns，0 allocs |

16 个字符在 SSO 范围内，临时字符串不分配，透明查找只省下一次复制。40 个字符时临时字符串要分配和释放，透明查找让 `unordered_map` 快 2.3 倍。`map` 的收益比例小一些，因为它的时间主要花在十几次字符串比较和沿途的缓存未命中上。

## 每个元素占多少内存

用一个计数分配器（[[allocator.requirements.general|分配器要求]]的最小实现）把所有容器的分配都记下来，就能知道每个元素实际花了多少字节：

```cpp
template <class T>
struct Counting {
  using value_type = T;
  Counting() = default;
  template <class U> Counting(const Counting<U>&) {}
  T* allocate(std::size_t n) {
    g.bytes += n * sizeof(T);
    g.rounded += malloc_good_size(n * sizeof(T));  // macOS：malloc 实际给的大小
    ++g.blocks;
    return static_cast<T*>(std::malloc(n * sizeof(T)));
  }
  void deallocate(T* p, std::size_t n) { /* 对称地减去 */ std::free(p); }
  friend bool operator==(Counting, Counting) { return true; }
};
```

元素是 8 字节的 `long`（`map` 和 `unordered_map` 的键和值都是 `long`，有效数据 16 字节），N = 100 万：

| 容器 | 请求的字节/元素 | malloc 实际/元素 | 分配次数/元素 |
|---|---:|---:|---:|
| `vector`，`push_back` | 8.4 | 8.4 | ≈0 |
| `vector`，`reserve` | 8.0 | 8.0 | ≈0 |
| `deque` | 8.0 | 8.0 | ≈0 |
| `list` | 24 | 32 | 1 |
| `set` | 40 | 48 | 1 |
| `unordered_set` | 37 | 45 | 1 |
| `map<long, long>` | 48 | 48 | 1 |
| `unordered_map<long, long>` | 45 | 45 | 1 |
| `unordered_map`，`reserve` | 40 | 40 | 1 |
| `flat_map<long, long>` | 16.8 | 16.8 | ≈0 |

这些数字可以按 libc++ 的节点结构拆开（具体布局是实现的选择，标准不规定）：

- `list` 的节点是两个指针加元素，24 字节。macOS 的 malloc 以 16 字节为粒度，实际占 32 字节，有效数据只有四分之一。
- `set` 和 `map` 的节点是左、右、父三个指针，加一个颜色标记（对齐后占 8 字节），再加元素：`set<long>` 40 字节，被取整到 48；`map<long, long>` 恰好 48。
- `unordered_map` 的节点是 `next` 指针、缓存的哈希值和元素，共 32 字节；另外每个桶一个 8 字节的指针。不预留时桶数大约是元素数的 1.6 倍，每个元素再分摊 13 字节；`reserve` 后桶数接近元素数，分摊 8 字节。
- `vector` 的额外开销来自未使用的容量：100 万不是 2 的幂，翻倍增长留下了 5% 的空位。`flat_map` 的两个 `vector` 也一样。

节点容器每个元素大约多占 16 到 40 字节，以 16 字节有效数据计，是 2 到 3 倍。更重要的是节点分散在堆上：同样 64 字节的缓存行，`flat_map` 装 8 个键，`map` 只装一个节点。分配本身的代价和减少分配的办法（对象池、`std::pmr`）见 [[perf/allocation|堆分配的代价]] 和 [[topics/allocators-and-pmr]]。

## 选节点容器的真正理由：引用稳定性

前面的数据几乎都在说连续存储更快。节点容器仍然有不可替代的用处：元素一旦放进去，就不会被搬走。

```cpp title="dangle.cpp" run ub
#include <cstdio>
#include <string>
#include <vector>

struct Order { int id; std::string owner; };

int main() {
  std::vector<Order> book;
  book.push_back({1, "alice"});
  Order& first = book.front();   // 引用指向 vector 的缓冲区
  for (int i = 2; i <= 100; ++i)
    book.push_back({i, "bob"});  // 扩容：元素搬到新缓冲区
  std::printf("%d\n", first.id); // UB: first 指向已释放的旧缓冲区
}
```

扩容使指向 `vector` 元素的所有引用、指针和迭代器失效（[[vector.modifiers#2]]）。本机用 `-fsanitize=address` 运行，报告 `heap-use-after-free`，释放发生在扩容时的 `deallocate` 里。这类错误的更多形态见 [[topics/dangling-references]]。

```cpp title="stable.cpp" run ok
#include <cstdio>
#include <deque>
#include <string>
#include <unordered_map>

struct Order { int id; std::string owner; };

int main() {
  std::deque<Order> book;
  book.push_back({1, "alice"});
  Order& first = book.front();
  for (int i = 2; i <= 100; ++i)
    book.push_back({i, "bob"});  // 两端插入不使引用失效
  std::printf("%d\n", first.id); // 1

  std::unordered_map<int, Order> by_id;
  Order& o = by_id[1] = {1, "alice"};
  for (int i = 2; i <= 1000; ++i)
    by_id[i] = {i, "bob"};       // 多次 rehash
  std::printf("%s\n", o.owner.c_str()); // alice：引用仍然有效
}
```

`deque` 在两端插入时使所有迭代器失效，但不影响元素的引用（[[deque.modifiers#1]]），因为它只是在块的索引表里加一个新块，旧块不动。`unordered_map` 的 rehash 只是把节点重新挂到新的桶上，节点本身不动，所以迭代器失效，指针和引用不失效（[[unord.req.general#9]]）。

各个容器的规则汇总如下。[[g:iterator-invalidation|迭代器失效]]的精确条件见各自的条款页。

| 容器 | 插入后，指向其他元素的引用 | 插入后，迭代器 | 出处 |
|---|---|---|---|
| `vector` | 扩容时全部失效；否则插入点之后的失效 | 同左 | [[vector.modifiers#2]] |
| `deque` | 两端插入：保持有效；中间插入：全部失效 | 全部失效 | [[deque.modifiers#1]] |
| `list` / `forward_list` | 保持有效 | 保持有效 | [[list.modifiers#2]] |
| `map` / `set` | 保持有效 | 保持有效 | [[associative.reqmts.general#175]] |
| `unordered_map` / `unordered_set` | 保持有效 | rehash 时全部失效 | [[unord.req.general#242]] |
| `flat_map` / `flat_set` | 不作保证 | 不作保证 | [[flat.map.overview#2.2]] |

`flat_map` 明确声明不满足关联容器关于迭代器失效的要求。它的元素存放在 `vector` 里，插入会移动其后的所有元素，可能还会重新分配。

所以选节点容器的理由通常是下面几种之一：别的数据结构持有指向元素的指针（索引、侵入式链表、观察者）；元素不可移动；需要 `splice`、`merge` 或节点句柄 `extract`，在容器之间转移元素而不复制（[[list.ops]]、[[container.node]]）。如果只是因为插入删除多，先测一测 `vector`。

!!! tip "只需要稳定地址时"
    元素需要稳定地址、又想要连续存储的遍历速度，常见的折中是 `vector<std::unique_ptr<T>>`（元素地址稳定，指针数组连续），或者用下标代替指针，把元素放在不缩短的 `vector` 或 `deque` 里。前者每个元素仍要一次分配，遍历时多一次间接访问。

## 怎样选

下表的每一行都对应上文的一组测量。

| 需求 | 首选 | 依据 |
|---|---|---|
| 一般的序列，主要在尾部增删、遍历 | `vector`，能预估大小就 `reserve` | 追加约 0.6–1 ns/元素，`list` 约 40 ns；遍历快 20 倍以上 |
| 在两端增删，或需要尾部追加时元素引用保持有效 | `deque` | 两端插入不使引用失效；遍历比 `vector` 慢约 10 倍 |
| 按值找位置再插入的有序序列 | 小元素用 `vector`；大元素且规模在几千以内可以考虑 `list` 或 `deque` | `int`：`vector` 在所有规模领先；256 字节：交叉点在 100 到 1 000 之间，10 万时 `list` 又最慢 |
| 键到值的映射，只按键查找 | `unordered_map`，提前 `reserve` | 100 万元素时查找 28 ns，`map` 545 ns |
| 需要有序遍历或范围查询，读多写少 | `flat_map` 或有序 `vector`，成批建立 | 1 万元素以上查找比 `map` 快 2–8 倍，遍历快两三个数量级；逐个插入 10 万时慢 75 倍 |
| 需要有序，同时频繁增删，或要持有元素引用 | `map` / `set` | 插入不使任何引用、迭代器失效 |
| 键域很小（如 0–255） | `bitset` 或 `bool` 数组 | 0.37 ns，与元素个数无关 |
| 几十个元素以内的集合 | 无序 `vector` 线性扫描 | 64 个元素时 4.4 ns，`set` 12.8 ns |
| `std::string` 作键，用 `string_view` 查 | 透明哈希 + `equal_to<>`，或 `less<>` | 40 字符的键：每次少一次分配，快 2.3 倍 |
| 外部长期持有元素的指针或引用 | 节点容器，或 `vector<unique_ptr<T>>` | 见上一节的失效规则 |

这张表只是起点。容器的选择取决于实际的元素大小、规模、操作比例和访问模式，最可靠的办法是把真实的数据放进上面这种小基准里测一次。

## 思考题

!!! question "1"
    一个 `unordered_map` 先调用了 `reserve(1000)`，然后从空表开始插入 1000 个元素。插入之前取得的迭代器在插入之后还有效吗？

<details markdown="1">
<summary>答案</summary>

有效。`a.reserve(n)` 等价于 `a.rehash(ceil(n / a.max_load_factor()))`（[[unord.req.general#239]]），之后桶数 B 满足 B ≥ n / z，其中 z 是最大负载因子。插入的元素数满足 N + n ≤ 1000 ≤ z × B，按 [[unord.req.general#243]]，这样的插入不影响迭代器的有效性。

前提是插入期间没人改过 `max_load_factor`。这条规则只保证迭代器，引用和指针无论是否 rehash 都保持有效（[[unord.req.general#242]]）。
</details>

!!! question "2"
    256 字节的元素做中间插入时，`deque` 比 `vector` 快。如果插入位置总是在最后 10% 的范围内，两者的差距会怎样变化？

<details markdown="1">
<summary>答案</summary>

差距基本消失。`deque` 移动的是到两端距离中较短的一侧（[[deque.modifiers#2]]），`vector` 移动的是插入点之后的部分（[[vector.modifiers#1]]）；插入点靠近尾部时，两者都只移动尾部那一小段。`deque` 的优势只在插入位置均匀分布、或者靠近头部时出现，靠近头部时 `vector` 要移动几乎全部元素。这一点由复杂度要求保证，不依赖具体实现。
</details>

!!! question "3"
    把开头那个测试里的 `list` 改成每次插入一个新节点、从不删除，让它从空表增长到 10 万个元素。可以预期它和 `vector` 的差距比表中更大还是更小？

<details markdown="1">
<summary>答案</summary>

更大。表中的 `list` 一直复用同一个被删除的节点，其余节点按地址顺序排列，遍历时缓存和预取器都有效。随机位置插入的新节点按分配的先后顺序分布在堆上，与它们在链表中的顺序无关，链表长大后遍历就接近打乱的情形：本机 100 万个元素时每步 92 ns，而按顺序建立的链表是 1.4 ns。`vector` 不受影响，它每次插入后的内存布局都是连续的。
</details>
