---
title: 迭代器要求：值与范围
summary: 迭代器库的基础词汇：值类型和差值类型、六个类别、可解引用值、过尾值和奇异值、范围与计数范围、有效范围，以及对无效范围调用库函数为什么是未定义行为。
status: done
covers: iterator.requirements.general
since: c++98
related: iterators, iterator.concepts, iterator.cpp17, iterator.assoc.types, expr.add, basic.compound, basic.indet, res.on.functions, iterator.concept.forward, iterator.concept.contiguous
tags: 标准库, 迭代器, 奇异值, 范围, UB
updated: 2026-10-19
---

!!! tldr
    - 迭代器的值分三种：可解引用的、过尾的、奇异的。奇异值不属于任何序列，除了销毁、被赋值和（值初始化时）被复制，对它做什么都是未定义行为。
    - 范围有两种写法：起点加哨位 `[i, s)`，起点加个数 `i+[0, n)`。从 `i` 有限次 `++` 能到达 `s` 时，`[i, s)` 才是有效范围。
    - 对无效范围调用库函数，结果未定义。传反首尾、首尾来自不同容器都属于这种情况，编译器查不出来。
    - 对连续迭代器，库可以直接改用裸指针，所以不要依赖解引用或递增的副作用。
    - 不是前向迭代器的迭代器可以把当前元素存在自己体内，迭代器一销毁，先前取得的引用就悬垂了。

[iterator.requirements] 下有七个子条款：总则 [iterator.requirements.general]、关联类型（[[iterator.assoc.types]]）、两个定制点（[[iterator.cust]]）、C++20 概念（[[iterator.concepts]]）、C++17 命名要求（[[iterator.cpp17]]）、间接可调用概念（[[indirectcallable]]）和算法的通用要求（[[alg.req]]）。总则定义了其余各处都在用的两个基本概念：迭代器的值和范围。

## 迭代器有哪些属性（¶1–¶6）

### 值类型与差值类型（¶1）

¶1 迭代器是指针的推广。为了让模板算法在各种数据结构上都正确而高效，库不只规定迭代器的接口，还规定它的语义和复杂度。

- 输入迭代器 `i` 支持 `*i`，结果是某个对象类型 `T` 的值，`T` 叫做迭代器的**值类型**（[[g:iterator-value-type]]）。
- 输出迭代器有一组可写入的类型：对其中每个 `T` 的值 `o`，`*i = o` 都合法。
- 每个迭代器类型都有一个**差值类型**（[[g:iterator-difference-type]]），它是一个有符号的类整数类型（[[iterator.concept.winc]]）。

类整数（integer-like）的意思是差值类型不一定是内建整数，也可以是实现提供的**整数类类型**（[[g:integer-class-type]]）。`iota_view<long long>` 中两个迭代器的距离可能超出 `long long`，就需要这种更宽的类型。

### 六个类别（¶2–¶4）

¶2 迭代器的语义是指针语义的推广，这保证了接受迭代器的函数模板对普通指针同样适用。标准按支持的操作把迭代器分成六类：输入、输出、前向、双向、随机访问、连续。

¶3 这六类分别对应六个概念：`input_iterator`、`output_iterator`、`forward_iterator`、`bidirectional_iterator`、`random_access_iterator`、`contiguous_iterator`。泛称的**迭代器**指任何建模 `input_or_output_iterator` 的类型。

¶4 类别之间可以替换：前向迭代器满足输入迭代器的全部要求，凡要求输入迭代器的地方都能用；双向之于前向、随机访问之于双向、连续之于随机访问也是如此。输出迭代器不在这条链上。

### 可变迭代器与常量迭代器（¶5）

¶5 同时满足输出迭代器要求的迭代器叫**可变迭代器**（[[g:mutable-iterator]]），其余的叫**常量迭代器**（[[g:constant-iterator]]）。`vector<int>::iterator` 是可变的，`vector<int>::const_iterator` 是常量的。C++23 的 `basic_const_iterator`（[[const.iterators]]）能把任意输入迭代器包装成常量迭代器。

### 关联类型必须能查到（¶6）

¶6 迭代器类型必须提供 [[iterator.traits]] 规定的那几个嵌套类型名。注 1 给出两种办法：类型自己声明，`iterator_traits` 会自动取用；或者特化 `iterator_traits`。C++20 起还可以都不写，由 `iterator_traits` 主模板根据表达式推导（[[iterator.assoc.types]]）。

## 迭代器的三种值（¶7）

¶7 和指向数组的指针类比，迭代器的值分三种：

| 值 | 含义 | 可以做什么 |
|---|---|---|
| **可解引用**（[[g:dereferenceable-iterator]]） | `*i` 有定义 | 解引用，按类别递增、递减 |
| **过尾值**（[[g:past-the-end-value]]） | 指向序列最后一个元素之后 | 比较，按类别递减；库从不假定它可解引用 |
| **奇异值**（[[g:singular-value]]） | 不与任何序列关联 | 几乎什么都不能做 |

!!! std
    Results of most expressions are undefined for singular values;

    对奇异值求值，绝大多数表达式的结果都是未定义的。

对持有奇异值的迭代器，只有三种操作是允许的：

1. 销毁它；
2. 给它赋一个非奇异的值，这时奇异值像普通值一样被覆盖；
3. 如果迭代器类型满足 *Cpp17DefaultConstructible*，可以把一个**值初始化**的迭代器用作复制或移动的源。

其他操作，比如复制一个默认初始化的迭代器、对它 `++`、比较两个奇异迭代器，都是 {{ub}}。可解引用的值一定不是奇异值。

```cpp run title="singular.cpp" ok
#include <vector>

int main() {
  std::vector<int>::iterator a;     // 默认初始化：奇异值
  std::vector<int>::iterator b{};   // 值初始化：奇异值，但可以复制
  auto c = b;                       // OK：第 3 条例外
  // auto d = a;                    // UB：复制默认初始化的奇异迭代器
  bool e = (b == c);                // OK，结果为 true，依据见下文
  a = c;                            // OK：给奇异迭代器赋值
  (void)a; (void)e;
}
```

第 3 条只对值初始化（`It it{};`、`It()`）成立。注 2 指出，默认初始化和值初始化的区别只对有平凡默认构造函数的类型有实际意义，例如指针和内含指针的聚合体：`int* p;` 不初始化，`int* p{};` 得到空指针。

`b == c` 合法，但许可不来自 ¶7。前向迭代器有一条额外保证：同类型的值初始化迭代器可以互相比较，并且相等，如同它们都指向同一个空序列的末尾（[[iterator.concept.forward#2]]）。

!!! impl "libc++ 的做法"
    libc++ 的 `vector<T>::iterator` 是 `__wrap_iter<T*>`，它的默认构造函数写成 `__wrap_iter() noexcept : __i_() {}`，默认初始化时内部指针也会置空。所以在 libc++ 上 `auto d = a;` 实际不会出错。但标准层面 `a` 仍是奇异值，换一个实现或者打开调试迭代器，就可能被诊断。

!!! lawyer "与 C++26 错误值的关系"
    `int* p; int* q = p;` 在 C++26 的核心语言里是**错误行为**（erroneous behavior），不是 UB：未初始化的自动变量持有一个错误值（[[basic.indet]]）。但 ¶7 是库的规则：把这样的 `p` 当迭代器交给库函数，库仍然可以说结果未定义。核心语言管读这个值本身，库管它被当作迭代器使用之后的事。

## 范围（¶8–¶13）

### 两种写法（¶8）

¶8 库的大多数算法以**范围**（range）为接口。范围有两种表示：

- 迭代器加**哨位**（sentinel），记作 `[i, s)`，标出计算的起点和终点；
- 迭代器加个数，记作 `i+[0, n)`，标出起点和元素个数。

脚注 177 说明哨位可以和迭代器同类型，也可以不同类型。

### `[i, s)` 包含哪些元素（¶9）

¶9 表示范围的迭代器和哨位必须能比较。`i == s` 时范围为空；否则 `[i, s)` 从 `i` 所指的元素开始，到第一个满足 `j == s` 的迭代器 `j` 所指元素为止，不含后者。

注意"第一个"。对 `[p, unreachable_sentinel)`，这样的 `j` 不存在，范围没有尽头。

### 可达性与有效范围（¶10）

!!! std
    A sentinel s is called *reachable from* an iterator i if and only if there is a finite sequence of applications of the expression ++i that makes i == s.

    如果对 `i` 有限次应用 `++i` 能使 `i == s`，就说 `s` 从 `i` **可达**（[[g:reachable-sentinel]]）。

¶10 `s` 从 `i` 可达时，`[i, s)` 是**有效范围**（[[g:valid-range]]）。有效性是运行时的性质，类型系统表达不了。`std::find(v.end(), v.begin(), x)` 能编译，但对非空的 `v`，从 `end()` 递增永远到不了 `begin()`，这不是有效范围。

### 计数范围（¶11）

¶11 **计数范围**（[[g:counted-range]]）`i+[0, n)` 的定义是递归的：`n == 0` 时为空且有效；否则它有效，当且仅当 `n` 为正、`i` 可解引用、并且 `++i+[0, --n)` 有效。`std::copy_n`、`counted_iterator`（[[iterators.counted]]）和 `views::counted` 都基于这个模型：不需要知道终点在哪里，只需要知道还剩几个元素。

### 无效范围是未定义行为（¶12）

!!! std
    The result of the application of library functions to invalid ranges is undefined.

    对无效范围调用库函数，结果未定义。

¶12 这条规则覆盖的情形很多：传反了首尾、首尾来自不同的容器、遍历途中修改容器使某个迭代器失效，都落在这里。

```cpp run title="invalid_range.cpp" ok
#include <algorithm>
#include <vector>

int main() {
  std::vector<int> a{1, 2, 3}, b{4, 5, 6};
  auto n1 = std::count(a.begin(), a.end(), 2);    // OK
  // auto n2 = std::count(a.begin(), b.end(), 2); // UB：b.end() 从 a.begin() 不可达
  // auto n3 = std::count(a.end(), a.begin(), 2); // UB：同上
  return static_cast<int>(n1) - 1;
}
```

### 连续迭代器可以换成指针（¶13）

¶13 对建模 `contiguous_iterator` 的 `i`，库函数可以把 `[i, s)` 换成 `[to_address(i), to_address(i + ranges::distance(i, s)))`，把 `i+[0, n)` 换成 `[to_address(i), to_address(i + n))`。

注 3 说明了后果：程序不能依赖对连续迭代器解引用或逐次递增的副作用。库可能根本不调用你的 `operator*` 和 `operator++`，而是拿到裸指针直接 `memmove`，或者一次 `i + n` 跳到终点。给连续迭代器的 `operator*` 加访问计数，得到的数字不可靠。

## 其他规定（¶14–¶17）

### 只要求常数时间能实现的操作（¶14）

¶14 每个类别只要求那些对该类别能在常数时间（可以是摊还常数时间）内实现的操作，所以要求表和概念定义都不写复杂度。`std::list` 的迭代器没有 `operator+`，原因就在这里：不是做不到，而是做不到常数时间。需要跨多步时用 `std::advance` 或 `ranges::next`（[[iterator.primitives]]）。

### 销毁迭代器可能使引用失效（¶15）

!!! std
    Destruction of an iterator may invalidate pointers and references previously obtained from that iterator if its type does not meet the *Cpp17ForwardIterator* requirements and does not model forward_iterator.

    如果迭代器类型既不满足 *Cpp17ForwardIterator*，也不建模 `forward_iterator`，销毁它可能使先前从它取得的指针和引用失效。

¶15 这条规定允许输入迭代器把当前元素存在自己体内。`istream_iterator<T>` 就是这样，`*it` 返回对其成员的引用（[[istream.iterator]]）。所以下面的写法会悬垂：

```cpp
const int& r = *std::istream_iterator<int>(std::cin);
// 临时迭代器在完整表达式结束时销毁，r 悬垂
```

前向迭代器不能这样做。[[iterator.concept.forward#3]] 要求，只要 `[i, s)` 仍是范围，从中取得的指针和引用就保持有效。一个把元素存在体内的类型，即使语法上满足 `forward_iterator`，也不建模它。`reverse_iterator` 的 `operator*` 先复制、再递减、再解引用，用在这种类型上就会返回悬垂引用（[[reverse.iterators]]）。

### 无效迭代器（¶16）

¶16 **无效迭代器**（[[g:invalid-iterator]]）是可能为奇异值的迭代器。脚注 178 补充两点：这个定义同样适用于指针；对已失效的迭代器解引用，行为未定义。容器条款里"使迭代器失效"的规定（如 `vector::push_back` 扩容后）说的就是这个状态：迭代器不一定真的变成奇异值，但程序不能再假设它不是。

### constexpr 迭代器（¶17）

¶17 如果为满足类别要求而提供的操作全都是 constexpr 函数，迭代器就满足 **constexpr 迭代器**要求（[[g:constexpr-iterator]]）。注 4 的例子是 `int*` 和 `reverse_iterator<int*>`。常量求值中调用 constexpr 算法，例如 `std::sort`，就需要这样的迭代器。

## 常见误解

!!! pitfall "能编译就是有效范围"
    类型系统只能检查迭代器和哨位能否比较（`sentinel_for`），检查不了哨位是否可达。可达性始终是调用者的前提条件。`ranges::` 算法把它写进了 [[iterator.concept.sentinel]] 的语义要求，编译器同样不检查。

!!! pitfall "值初始化的迭代器是空范围的 begin"
    `It{}` 只在前向迭代器上有如同指向同一空序列末尾的语义，而且只能和同类型的值初始化迭代器比较。拿它和某个容器的 `end()` 比较仍然是 UB，因为它们不属于同一序列。

## 思考题

!!! question "思考题 1"
    `std::vector<int> v; auto b = v.begin(), e = v.end();` 中的 `b`、`e` 是奇异值吗？`[b, e)` 是有效范围吗？

<details markdown="1">
<summary>答案</summary>

不是奇异值，它们与 `v` 这个空序列关联。`b == e` 为真，零次 `++` 即可到达，所以 `[b, e)` 是有效的空范围（¶9、¶10）。`b` 是过尾值，不可解引用。
</details>

!!! question "思考题 2"
    ¶7 为什么只允许把值初始化的迭代器用作复制源，而不干脆规定值初始化的迭代器不是奇异值？

<details markdown="1">
<summary>答案</summary>

值初始化的迭代器确实不与任何序列关联，按定义就是奇异的。允许复制它，是为了让 `It tmp{}; ... tmp = other;` 这类代码有定义。更强的可比较保证只给前向迭代器（[[iterator.concept.forward#2]]）。
</details>

!!! question "思考题 3"
    一个类型把当前元素缓存在自身，`operator*` 返回对这个成员的引用，其余操作都满足 `forward_iterator` 的语法。`std::forward_iterator<It>` 为真吗？把它交给 `std::ranges::reverse_view` 会怎样？

<details markdown="1">
<summary>答案</summary>

为真，因为概念只检查语法。但它违反了 [[iterator.concept.forward#3]] 的语义要求，只满足而不建模 `forward_iterator`。按 [[res.on.requirements#2]]，程序的含义依赖于一个满足但不建模的概念时，程序 {{ifndr}}。实际运行时，`reverse_iterator::operator*` 先复制、再递减、再解引用，返回的引用指向已销毁的临时副本。
</details>
