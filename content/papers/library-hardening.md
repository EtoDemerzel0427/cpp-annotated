---
title: 标准库加固（P3471）
summary: C++26 怎样把 vector 越界、空 optional 解引用这类库 UB 变成有保证的终止：把一部分已有前置条件标成加固前置条件，由实现定义是否提供加固实现；为什么只挑便宜的边界检查、为什么借用契约的违约机制，以及 observe 语义为什么后来被排除。
status: draft
order: 58
group: 标准库
since: c++26
papers: P3471R4, P2900R14, P3878R0, P3878R1, P3697R1, P4349R0
related: intro.compliance, structure.specifications, basic.contract.eval, res.contract.assertions, sequence.reqmts, span.elem, optional.observe, version.syn, topics/undefined-behavior, toolchain/error-handling-strategy, perf/reading-assembly, history/contracts, papers/contracts, papers/erroneous-behaviour
tags: 加固, 安全性, 前置条件, 契约, UB, libc++, 提案
updated: 2026-10-19
---

!!! tldr
    - C++26 把 `vector::operator[]`、`optional::operator*`、`span::front()` 等一批函数的前置条件改标为**加固前置条件**：在加固实现中违反它们是契约违反并以终止型语义处理，在其他实现中仍是 UB（[[structure.specifications#3.5]]）。
    - 是否为加固实现由实现定义（[[intro.compliance#8]]），和独立实现一样是一种实现形态，标准不规定怎么开启，也不要求默认开启。
    - 入选的条件只有一类：违反会造成越界或读取不存在的元素，调用点有足够信息检查，并且是常数时间。检查所有前置条件被明确列为非目标。
    - P3471R4 原本允许用 observe 语义检查，违约处理函数返回后仍是 UB；[[P3878R1]] 把它改成只能用 enforce 或 quick-enforce。
    - 本机 libc++ 的 `_LIBCPP_HARDENING_MODE` 是这套规则的前身：FAST 模式检查一次只多一次比较和一个 `brk`，但它还没有覆盖 C++26 列出的全部加固前置条件，也不定义 `__cpp_lib_hardened_*` 宏。

## 同一行越界读，三种结局

```cpp title="oob.cpp" run ub
#include <cstdio>
#include <optional>
#include <string_view>
#include <vector>

int main(int argc, char** argv) {
  std::vector<int> v{1, 2, 3};
  std::optional<int> o;
  std::string_view s;
  switch (argv[1][0]) {
    case 'v': std::printf("%d\n", v[argc + 2]); break;  // 越界
    case 'o': std::printf("%d\n", *o); break;           // 空 optional
    case 's': std::printf("%c\n", s.front()); break;    // 空 string_view
  }
}
```

C++23 中这三处都违反了函数的 *Preconditions*，结果是未定义行为（[[structure.specifications#3.4]]）。标准库不必检查，编译器也不报错。本机 Clang 23 + libc++ 用 `-O2` 编译，分别以 `v`、`o`、`s` 为参数运行，三种配置的结果如下：

| 配置 | `./oob v` | `./oob o` | `./oob s` |
|---|---|---|---|
| 默认（不加固） | 打印 `5`，退出码 0 | 打印 `0`，退出码 0 | 什么也不打印，退出码 0 |
| `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` | SIGTRAP，退出码 133 | 同左 | 同左 |
| `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_DEBUG` | 打印断言信息后 SIGABRT，退出码 134 | 同左 | 同左 |

不加固时，程序读到了 `v` 缓冲区之后的某个值，照常退出。`s` 那一行什么也没打印：空 `string_view` 的 `data()` 是空指针，读它是 UB，汇编显示优化器把这个分支整个删掉了。越界读能泄露数据，越界写能改写相邻对象，这正是内存安全漏洞最常见的来源。DEBUG 模式打印的信息指出了具体的条件，例如：

```text
vector.h:414: libc++ Hardening assertion __n < size() failed: vector[] index out of bounds
optional:513: libc++ Hardening assertion this->has_value() failed: optional operator* called on a disengaged value
string_view:425: libc++ Hardening assertion !empty() failed: string_view::front(): string is empty
```

这些开关在 C++26 之前就存在。三大标准库实现各有一套：libc++ 的 `_LIBCPP_HARDENING_MODE`，libstdc++ 的 `_GLIBCXX_ASSERTIONS`，MSVC STL 的 `_MSVC_STL_HARDENING`。MSVC STL 的文档说明它检查的正是越界元素访问、空容器上的 `pop_back()` 以及空 `optional`/`expected` 的访问，失败时最终调用 `__fastfail`。本机只有 Clang 和 libc++，另外两个没有验证。

[[P3471R4]] 的出发点是：既然每家都有，为什么还要标准化？论文给了三个理由。第一，最有价值的是让现有代码更安全，而不是要求重写；把 `v[i]` 改成 `v.at(i)` 对上亿行代码不现实。第二，各家的覆盖范围、性能承诺和开启方式都不同，用户得不到可移植的保证。第三，安全编码规范需要能引用的条文，厂商扩展做不到这一点。

## 部署经验

论文的论据主要来自部署。它引用了 Google 公开的报告：在数亿行代码上开启这项加固，性能影响低至 0.3%，发现了一千多个 bug，其中包括安全相关的。论文还提到 Apple 平台上若干代码库的部署，以及 libc++ 维护者收到的大量非正式反馈。

这些经验直接决定了设计的方向。论文认为只在调试构建里开启的检查对安全没有实质帮助，必须轻到能在生产环境里常开。由此得出一个取舍：一小组被广泛开启的检查，比一大组只有少数人敢开的检查更有价值。幸运的是，最有价值的检查（容器越界）恰好也最便宜。

## 设计空间

### 检查全部前置条件

最彻底的方案是让加固实现检查库里的每一条前置条件。P3471 把这一点明确列为非目标，理由有两个。

一是做不到。很多前置条件是语义要求，比如给 `std::sort` 的比较器必须是严格弱序（[[alg.sorting]]），库无法在合理的代价下验证。二是太贵。目标是生产环境常开，每条检查的代价都要乘以调用次数。

最后选的是一个很窄的集合。论文第一版只覆盖会导致越界访问的条件，后续的 [[P3697R1]] 把入选标准写得更明确：违反会造成内存安全问题（越界访问或读取未初始化内存）；调用点拥有检查所需的全部数据；检查是常数时间、开销较小。

### 违反之后怎么办

确定了检查哪些条件，还要规定检查失败后的行为。论文的几个修订版走过三条路：

| 方案 | 出处 | 结局 |
|---|---|---|
| 以实现定义的方式终止程序 | P3471R0 | 被 R1 取代 |
| 错误行为（erroneous behavior） | 论文中讨论 | 被否决 |
| 契约违反 | P3471R1 起 | 采纳 |

**错误行为**是 C++26 新增的一类行为：程序有错，但行为是明确的，实现可以诊断（见 [[papers/erroneous-behaviour|错误行为]]）。论文否决它的理由很具体：错误行为只说明代码有错，不规定发生错误时做什么。按错误行为，`vector::operator[]` 越界时返回最后一个元素也是合规的，行为明确，但没有用，用户要的是程序停下来。

**契约违反**来自同期的契约提案（[[P2900R14]]，见 [[papers/contracts|契约]]）。一条契约断言被检查而谓词为假时发生契约违反，后续动作由**求值语义**（[[g:evaluation-semantic|evaluation semantic]]）决定：ignore 不检查；observe 调用违约处理函数，处理函数返回后继续执行；enforce 调用处理函数后终止；quick-enforce 直接终止（[[basic.contract.eval#1]]）。后两种称为**终止型语义**（terminating semantic）。

论文选择契约有两个理由：语言和库在出错时有统一的处理框架，这是已有用户反复要求的；违约处理函数可以替换，用户能按自己的需要记录日志。论文同时说明，实现不必真的用契约断言写这些检查，用宏也可以，只要违反时走契约违约的处理机制。

论文还讨论了 Profiles。如果将来 Profiles 进入标准，加固可以表述为其中一个 profile，但论文认为不应等待一个仍在实验中的更大特性。

### ignore 和 observe

既然借用了契约，就要回答四种语义里哪些可以用。

ignore 从一开始就被排除。P3471 的理由是：标准规定违反加固前置条件本身就是契约违反，到这一步已经越过了 ignore 能跳过检查的位置。换句话说，一个用 ignore 的实现不算加固实现。

observe 在 P3471R4 中是允许的。论文认为部署经验表明 observe 对大规模推广很有用：先只记录、不终止，等修完日志里的问题再切换到终止。R4 的措辞因此写成：以 checking semantic 求值；如果用的是非终止型语义并且违约处理函数返回，则行为未定义。

[[P3878R0]] 反对这一点，而且反对得更彻底，标题就是 C++26 契约不适合标准库加固。它的技术论点有两个：

1. observe 下处理函数返回后，函数继续执行，越界访问照样发生。一个允许这种结果的加固实现不是内存安全机制。
2. C++26 契约没有办法为单条断言指定语义。标准库要支持多种编译器，无法保证加固前置条件一定以终止型语义求值；而用户可能让自己的契约用 ignore 或 observe，加固必须与此无关。

修订版 [[P3878R1]] 收窄了目标，只提出把 checking semantic 改成 terminating semantic，删除处理函数返回后 UB 的那一句。论文说明 P3471 的作者也认为这是一个缺陷修正。它同时指出，这一修改并不保证程序一定终止：如果实现支持替换违约处理函数，处理函数可以抛出异常，但这样也不会执行库函数的剩余部分，不会产生 UB。仍想要只记录不终止的厂商可以提供一个检查但不称为加固的模式。

本机 libc++ 还保留着 observe 选项（实验性，需要 `-fexperimental-library`）。用 FAST 模式加 `-D_LIBCPP_ASSERTION_SEMANTIC=_LIBCPP_ASSERTION_SEMANTIC_OBSERVE` 运行 `./oob v`，程序先打印断言信息，然后照常打印了一个越界读到的值，退出码 0。这正是 P3878 所说的情形：检查发生了，UB 也发生了。

### 一种实现形态，而不是默认行为

P3471 没有把检查变成所有实现的义务，而是仿照独立实现（freestanding）新增一种实现形态。是否加固由实现定义，怎么开启也由实现决定。论文预期工具链会提供类似 `-fhardened` 的编译选项，但用 `-D_LIBCPP_HARDENING_MODE=...` 这样的宏开启也是合规的。

论文还写明了两个约束。加固不应要求改变 ABI，实现可以允许加固代码和未加固代码混在同一个程序里；但混用是否允许，标准有意不作规定，以免过度约束实现。

这一选择带来一个直接后果：对没有违反前置条件的程序，加固实现和非加固实现的行为完全相同。加固只是给原本就是 UB 的执行规定了结果。所以 P3471 没有在 Annex C 里留下任何不兼容条目。

## 最终的规则

### 新的规范要素（[[structure.specifications#3.5]]）

库函数的规范由一串带标签的要素组成，各自规定违反时的后果（见 [[description]]）。C++26 在 *Preconditions*（¶3.4）之后加了一个要素：

!!! std
    *Hardened preconditions*: … When invoking the function in a hardened implementation, prior to any other observable side effects of the function, contract assertions whose predicates are as described in the hardened precondition are evaluated with a terminating semantic.

    在加固实现中，调用函数时，先于函数的任何其他可观察副作用，以终止型语义求值谓词为该条件的契约断言（¶3.5.1）；在非加固实现中，违反它是 UB（¶3.5.2）。

和 P3471R4 相比，有两处变化。一是 checking semantic 改成了 terminating semantic，处理函数返回后 UB 的那句话被删除，这是 P3878R1 的修改。二是 R4 中的 one or more contract assertions 在当前草案里写作 contract assertions。

[[intro.compliance#8]] 给出另一半：

!!! std
    It is implementation-defined whether the implementation is a *hardened implementation*. If it is a hardened implementation, violating a hardened precondition results in a contract violation.

    是否为加固实现由实现定义；在加固实现中，违反加固前置条件导致契约违反。

[[structure.specifications#4]] 也同步修改：当 *Effects* 写成 *Equivalent to* 一段代码时，这段代码里各个函数调用的 *Hardened preconditions* 一并适用。所以 `basic_string::front()` 规定为等价于 `return operator[](0);`，`operator[]` 的加固前置条件也会被带进来。

普通的 *Preconditions* 并没有因此失去检查的可能。[[res.contract.assertions#1]] 允许实现用契约断言检查任何前置条件和后置条件，只是不要求。区别在于：*Hardened preconditions* 在加固实现中是必须检查的，*Preconditions* 在任何实现中都可以不检查。

### 哪些函数入选

P3471R4 的修改集中在两类：可能访问不存在元素的访问函数，以及假定容器非空的修改函数。

| 类 | `operator[]` | `front()` | `back()` | `pop_front()` | `pop_back()` |
|---|---|---|---|---|---|
| `array` | ✓ | ✓ | ✓ | | |
| `basic_string` | ✓ | ✓ | ✓ | | ✓ |
| `deque` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `forward_list` | | ✓ | | ✓ | |
| `inplace_vector` | ✓ | ✓ | ✓ | | ✓ |
| `list` | | ✓ | ✓ | ✓ | ✓ |
| `vector` | ✓ | ✓ | ✓ | | ✓ |
| `span` | ✓ | ✓ | ✓ | | |
| `basic_string_view` | ✓ | ✓ | ✓ | | |
| `mdspan` | ✓ | | | | |
| `bitset` | ✓ | | | | |
| `valarray` | ✓ | | | | |

此外还有：`optional` 和 `expected` 的 `operator->`、`operator*`，`expected::error()`（要求 `has_value()` 为假）；`span` 的 `first`、`last`、`subspan`，以及固定 extent 的 `span` 从运行期长度构造时要求长度等于 extent；`string_view` 的 `remove_prefix`、`remove_suffix`；从另一个 `mdspan` 转换的构造函数。

顺序容器的条件写在 [[sequence.reqmts]] 的通用要求里，例如 `a[n]` 要求 `n < a.size()`（[[sequence.reqmts#122]]），`a.front()` 要求 `a.empty()` 为假（[[sequence.reqmts#72]]）。论文顺手把一些原本隐含的前置条件写成了明文：此前 `vector::operator[]` 的前置条件只能从迭代器有效性推出来。

注意两个相近的条件不一样。`basic_string::operator[]` 要求 `pos <= size()`（[[string.access#1]]），可以读到结尾的空字符；`basic_string_view::operator[]` 要求 `pos < size()`。

C++26 定稿前，[[P3697R1]] 又补了几处，论文称之为原提案的遗漏：`basic_stacktrace` 的 `operator[]` 和 `current(skip, max_depth)`，`shared_ptr<T[N]>::operator[]`（[[util.smartptr.shared.obs#9]]），`view_interface` 的 `front`/`back`（[[view.interface.members#1]]），以及 `counted_iterator`、`common_iterator` 的若干成员。`counted_iterator` 记录了到末尾的剩余长度，所以能检查越过末尾，却不能检查退到开头之前，论文认为只检查一半也比不检查好。当前草案的 [[version.syn#3]] 列出了对应的特性测试宏，P3471 的一组值为 `202502L`，P3697 新增的一组为 `202506L`；[[version.syn#7]] 建议非加固实现不要定义它们。

### 没有入选的

P3471 用一节说明了几处明显的遗漏：

- **`erase(iterator)`**：要求迭代器指向本容器的元素。连续容器可以把迭代器降为指针，比较它是否落在缓冲区内；非连续容器没有不改 ABI、不带显著开销的检查办法。
- **关联容器**：它们的前置条件大多与空间安全没有直接关系，实现经验也不够。
- **算法**：几乎所有算法都要求输入是有效范围，但只有连续迭代器能部分检查；两个迭代器是否属于同一个容器、输入输出范围是否重叠，一般无法检查（输入迭代器不能回退）。
- **`mdspan` 的 extents 和布局映射**、**`valarray` 除 `operator[]` 以外的部分**：类之间的交互复杂，需要单独研究，避免漏检或重复检查。

C++26 的新类型也不一定加固了。`std::indirect` 被移动后处于 valueless 状态，此时解引用在当前草案里仍是普通的 *Preconditions*（[[indirect.obs#1]]）。[[P4349R0]] 提议把 `indirect` 和 `polymorphic` 的这类前置条件也改为加固前置条件，写作时尚未并入草案。

## 在 libc++ 里验证

### 检查编译成什么

用 `-O2` 编译 `int get(const std::optional<int>& o) { return *o; }`，本机 AArch64 汇编如下：

<div class="compare" markdown="1">

```asm title="不加固"
ldr  w0, [x0]
ret
```

```asm title="FAST（quick-enforce）"
ldrb w8, [x0, #4]   ; 读 engaged 标志
tbz  w8, #0, LBB0_2
ldr  w0, [x0]
ret
LBB0_2:
brk  #0x1           ; 陷入
```

</div>

FAST 多出一次字节加载和一个几乎从不跳转的分支。DEBUG 模式的快路径与 FAST 相同，区别只在失败分支：它装入一条消息字符串，调用 `std::__libcpp_verbose_abort` 打印后中止，而不是一条 `brk` 指令。这对应契约的两种终止型语义：quick-enforce 直接终止，enforce 先调用处理函数再终止。libc++ 的头文件注释说明 FAST 和 EXTENSIVE 默认用 quick-enforce，DEBUG 默认用 enforce。

`vector::operator[]` 的汇编、检查怎样被提到循环外，见 [[perf/reading-assembly|读汇编]]，这里不重复。

### FAST 模式还不是 C++26 加固实现

本机 libc++ 23 是 C++26 加固的前身，不等于标准意义上的加固实现。用一个程序逐个触发上文列出的加固前置条件，分别在四种模式下运行：

| 违反的加固前置条件 | NONE | FAST | EXTENSIVE | DEBUG |
|---|---|---|---|---|
| `span::subspan` 越界、`bitset`/`valarray`/`deque`/`string` 的 `[]` 越界 | 不检查 | 133 | 133 | 134 |
| `expected::error()` 而对象持有值、`mdspan` 下标越界 | 不检查 | 133 | 133 | 134 |
| 空 `string::pop_back()`、`ref_view` 的 `front()`（来自 `view_interface`） | 不检查 | 133 | 133 | 134 |
| `counted_iterator(p, -5)` | 不检查 | 不检查 | 133 | 134 |
| `shared_ptr<int[3]>` 的 `p[5]` | 不检查 | 不检查 | 不检查 | 不检查 |

133 是 SIGTRAP，134 是 SIGABRT。`counted_iterator` 构造函数的检查在 libc++ 里归类为 uncategorized，FAST 模式不启用；`shared_ptr::operator[]` 在本机版本中完全没有检查，P3697 的这一条还没有实现。另外，libc++ 的 `<version>` 不定义任何 `__cpp_lib_hardened_*` 宏，Clang 23 也不定义 `__cpp_contracts`，检查失败时不经过可替换的契约违约处理函数。

所以今天可移植地依赖加固，最多只能依赖各实现文档承诺的范围。标准的作用是给出一个所有实现都会收敛到的目标。

### 开销取决于检查能否被消掉

检查能不能被证明多余，决定了开销的大小。下面的直方图统计里，`hist_vec` 的下标来自数据，编译器无法提前判断；`hist_arr` 的下标是 `uint8_t`，而数组正好有 256 个元素，检查恒为真。

```cpp title="hist.cpp" run ok flags="-std=c++2c -O2 -D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST"
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>

[[gnu::noinline]] void hist_vec(const std::vector<std::uint32_t>& keys,
                                std::vector<std::uint32_t>& h) {
  for (std::size_t i = 0; i < keys.size(); ++i) ++h[keys[i]];
}

[[gnu::noinline]] void hist_arr(const std::vector<std::uint8_t>& keys,
                                std::array<std::uint32_t, 256>& h) {
  for (std::size_t i = 0; i < keys.size(); ++i) ++h[keys[i]];
}

template <class F> double best_ms(F f) {
  double best = 1e30;
  for (int r = 0; r < 15; ++r) {
    auto t0 = std::chrono::steady_clock::now();
    f();
    auto t1 = std::chrono::steady_clock::now();
    double ms = std::chrono::duration<double, std::milli>(t1 - t0).count();
    if (ms < best) best = ms;
  }
  return best;
}

int main() {
  const std::size_t N = 1 << 24, B = 1 << 12;
  std::mt19937 g(42);
  std::vector<std::uint32_t> k32(N);
  std::vector<std::uint8_t> k8(N);
  for (std::size_t i = 0; i < N; ++i) { k32[i] = g() % B; k8[i] = g(); }
  std::vector<std::uint32_t> h(B);
  std::array<std::uint32_t, 256> a{};
  double t1 = best_ms([&] { hist_vec(k32, h); });
  double t2 = best_ms([&] { hist_arr(k8, a); });
  std::printf("vec %.2f arr %.2f (%u %u)\n", t1, t2, h[0], a[0]);
}
```

本机 M2 Pro 上，分别用 NONE 和 FAST 编译，交替运行 9 次取中位数（机器负载较高，只看比值）：

| 函数 | FAST / NONE | 汇编里的 `brk` |
|---|---|---|
| `hist_vec` | 约 1.32 | 1 个，热循环里每次迭代一次 `cmp` 加 `b.ls` |
| `hist_arr` | 约 1.00 | 0 个，检查被完全消除 |

`hist_vec` 慢了约三成，一部分来自每次迭代的比较和分支，一部分来自循环不再 2 路展开。这是一个只做下标访问的微基准，代表的是最坏情形之一；它和 Google 报告的全程序 0.3% 并不矛盾，真实程序的大部分时间不花在这种循环上。需要在热点里去掉检查时，可以让编译器看出条件恒真（如上面的 `uint8_t` 下标），顺序遍历时则可以改用范围 `for`，它不经过 `operator[]`。

## 后续与现状

- **C++26**：[[P3471R4]] 与契约（[[P2900R14]]）同时并入；[[P3697R1]] 补充了 `stacktrace`、`shared_ptr<T[N]>`、`view_interface`、`counted_iterator`、`common_iterator`；[[P3878R1]] 去掉了 observe。契约本身的来龙去脉见 [[history/contracts|契约沿革]]。
- **C++26 之后**：还有继续扩大范围的提案，如 [[P4349R0]]。
- **实现**：libc++ 的 FAST/EXTENSIVE/DEBUG 模式、libstdc++ 的 `_GLIBCXX_ASSERTIONS`、MSVC STL 的 `_MSVC_STL_HARDENING` 都早于标准，覆盖范围各不相同。各模式的语义列表见 [[topics/undefined-behavior|未定义行为]]；在项目里怎样和断言、契约一起使用，见 [[toolchain/error-handling-strategy|错误处理策略]]。

开启加固最常暴露出来的，是那些一直侥幸运行的代码：

```cpp title="end.cpp" run ub
#include <cstdio>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  int* e = &v[v.size()];   // 违反 n < a.size()
  std::printf("%td\n", e - v.data());
}
```

这种取尾后指针的写法从来都是 UB，只是在不检查的实现上看起来没问题。本机不加固时打印 `3`；FAST 模式下在 `v[v.size()]` 处 SIGTRAP。[[P3878R0]] 提到这种写法在实际代码中确实存在。正确的写法是 `v.data() + v.size()`。

## 思考题

!!! question "1. 加固实现里能用 ignore 吗"
    某实现提供一个开关：加固前置条件照常编译进库，但以 ignore 语义求值。它能自称加固实现吗？

<details markdown="1">
<summary>答案</summary>

不能。[[structure.specifications#3.5]] 要求在加固实现中以终止型语义求值这些断言，ignore 不是终止型语义（[[basic.contract.eval#1]]）。P3471 从第一版起就排除了 ignore，P3878R1 又排除了 observe。libc++ 的头文件注释也写明，选择 ignore 语义得到的不是合规的加固实现。

</details>

!!! question "2. 抛异常的违约处理函数"
    在一个用 enforce 语义、支持替换违约处理函数的加固实现中，用户的处理函数抛出异常。`v[10]` 越界时，库会不会继续执行越界读？

<details markdown="1">
<summary>答案</summary>

不会。按 [[basic.contract.eval#11]]，enforce 下发生契约违反时调用违约处理函数；处理函数以异常退出，异常从调用点向外传播，`operator[]` 的函数体不再执行。[[structure.specifications#3.5.1]] 还要求检查先于函数的任何其他可观察副作用。P3878R1 专门讨论了这一情形：程序不一定终止，但不会进入库函数的剩余部分，因此没有 UB。

</details>

!!! question "3. 为什么没有 Annex C 条目"
    C++26 让一些程序在加固实现中从照常运行变成终止。为什么附录 C 没有把它列为不兼容？

<details markdown="1">
<summary>答案</summary>

受影响的只有违反了前置条件的执行，而这些执行在 C++23 中就是 UB，标准对它们没有任何要求，终止也是 UB 允许的结果之一。P3471 只把已有的前置条件改标为加固前置条件，没有新增条件（论文明确说明只是把隐含的条件写成明文）。对所有在 C++23 中行为明确的程序，加固实现与非加固实现的行为相同，所以不存在需要记录的不兼容。

</details>
