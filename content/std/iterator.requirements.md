---
title: 迭代器要求：值与范围
summary: [iterator.requirements.general] 逐段精读——值类型与差值类型、六个类别、可变/常量迭代器；迭代器的三种值（可解引用、过尾、奇异）及对奇异值几乎一切操作都是 UB；范围 [i, s)、可达性、有效范围与计数范围 i+[0, n)；对连续迭代器库可以改用 to_address 指针；非前向迭代器析构可使引用失效；无效迭代器与 constexpr 迭代器。
status: done
covers: iterator.requirements.general
since: c++98
related: iterators, iterator.concepts, iterator.cpp17, iterator.assoc.types, expr.add, basic.compound, basic.indet, res.on.functions, iterator.concept.forward, iterator.concept.contiguous
tags: 标准库, 迭代器, 奇异值, 范围, UB
updated: 2026-10-18
---

[iterator.requirements] 是整个迭代器库的"法律总则"。它的子条款依次给出关联类型（[[iterator.assoc.types]]）、两个定制点（[[iterator.cust]]）、C++20 概念（[[iterator.concepts]]）、C++17 命名要求（[[iterator.cpp17]]）、间接可调用概念（[[indirectcallable]]）与算法通用要求（[[alg.req]]）。本页只讲开篇的 [iterator.requirements.general]——它定义了后面所有条款都在用的基础词汇：**迭代器的值**和**范围**。

这一节的分量在于：标准库几乎所有"传错迭代器"的错误，最终都落到这里的定义上——"这不是有效范围"、"这是奇异值"、"这个迭代器已经无效"——然后由 ¶12 或 [[res.on.functions]] 判为未定义行为。

## 迭代器是什么（¶1–¶6）

### 值类型、可写类型、差值类型（¶1）

¶1 开宗明义：迭代器是**指针的推广**，库不只形式化接口，还形式化**语义与复杂度假设**。随后定义三个关联概念：

- 输入迭代器 `i` 支持 `*i`，其结果是某个对象类型 `T` 的值，`T` 称为迭代器的**值类型**（[[g:iterator-value-type]]）；
- 输出迭代器有一个非空的**可写**类型集合：对其中每个 `T`，`*i = o` 合法；
- 每个迭代器类型 `X` 都有一个对应的**有符号类整数类型**（*signed integer-like type*，[[iterator.concept.winc]]）作为**差值类型**（[[g:iterator-difference-type]]）。

注意"类整数"（*integer-like*）这个措辞：差值类型不必是内建整数，也可以是实现提供的**整数类类型**（[[g:integer-class-type]]）。这是 C++20 为 `iota_view<long long>` 这类"距离可能超出 `long long`"的范围准备的。

### 六个类别与"可替换性"（¶2–¶4）

¶2 说明为什么用指针做模型：迭代器语义是指针语义的推广，这保证接受迭代器的函数模板对普通指针同样适用。然后列出六个类别（input、output、forward、bidirectional、random access、contiguous），¶3 把它们一一对应到六个概念，并规定泛称"迭代器"指建模 `input_or_output_iterator` 的类型。

¶4 规定类别之间的**可替换性**：前向迭代器满足输入迭代器的全部要求，可以用在任何要求输入迭代器的地方；双向之于前向、随机访问之于双向、连续之于随机访问，同理。输出迭代器不在这条链上——它是独立的一支。

### 可变迭代器与常量迭代器（¶5）

¶5：同时满足输出迭代器要求的迭代器称为**可变迭代器**（[[g:mutable-iterator]]），否则是**常量迭代器**（[[g:constant-iterator]]）。`vector<int>::iterator` 是可变的，`vector<int>::const_iterator` 是常量的。C++23 的 `basic_const_iterator`（[[const.iterators]]）就是把任意输入迭代器包装成常量迭代器的工具。

### 关联类型必须可查（¶6）

¶6 要求迭代器类型提供 [[iterator.traits]] 中规定的嵌套类型名；注 1 说明两条路：类型自己声明（`iterator_traits` 会自动取用），或特化 `iterator_traits`。C++20 之后第三条路更常见：什么都不写，由 `iterator_traits` 主模板根据表达式自动推导（[[iterator.assoc.types]]）。

## 迭代器的三种值（¶7）

这是本节最重要的一段。类比"指向数组的指针"，迭代器的值可以分为：

| 值 | 定义 | 能做什么 |
|---|---|---|
| **可解引用**（[[g:dereferenceable-iterator]]） | `*i` 有定义 | 解引用、递增（视类别） |
| **过尾值**（[[g:past-the-end-value]]） | 指向序列最后一个元素之后 | 比较、（双向迭代器）递减；**库永不假定它可解引用** |
| **奇异值**（[[g:singular-value]]） | 不与任何序列关联 | 几乎什么都不能做 |

!!! std
    Iterators can also have singular values that are not associated with any sequence. Results of most expressions are undefined for singular values.

    迭代器可以持有**不与任何序列关联**的奇异值；对奇异值求值的绝大多数表达式，结果都是未定义的。

对奇异值**只有三种**操作是允许的：

1. **销毁**持有奇异值的迭代器；
2. 把一个**非奇异**值**赋给**持有奇异值的迭代器（奇异值像普通值一样被覆盖）；
3. 对满足 *Cpp17DefaultConstructible* 的迭代器：用一个**值初始化**的迭代器作为复制或移动的**源**。

除此之外——比较两个奇异迭代器、复制一个**默认初始化**（而非值初始化）的迭代器、对它 `++`——统统是 {{ub}}。¶7 最后一句"可解引用的值总是非奇异的"排除了一个可能的误读。

!!! note "注 2：默认初始化 vs 值初始化"
    第 3 条只对**值初始化**（`It it{};`、`It()`）成立。注 2 指出，这一区别只对具有**平凡默认构造函数**的类型有实际意义，例如指针，或内含指针的聚合体：`int* p;` 不初始化任何东西，`int* p{};` 得到空指针。对于有用户提供默认构造函数的类类型迭代器，两种写法调用的是同一个构造函数，库的规则仍然把前者算作奇异值，但实现往往"碰巧"把它置零。

```cpp run title="singular.cpp"
#include <vector>

int main() {
    std::vector<int>::iterator a;      // 默认初始化：奇异值
    std::vector<int>::iterator b{};    // 值初始化：奇异值，但可作为复制源
    auto c = b;                        // OK：¶7 的第 3 条例外
    // auto d = a;                     // UB：复制默认初始化的奇异迭代器
    bool e = (b == c);                 // OK，且为 true：不是 ¶7 给的许可，见下文
    a = c;                             // OK：给奇异迭代器赋值
    (void)a; (void)e;
}
```

上例中的 `b == c` **合法**——但许可不是来自 ¶7，而是 [[iterator.cpp17]] 与 [[iterator.concepts]] 中前向迭代器的额外保证：值初始化的前向迭代器可以相互比较，且比较结果为相等，"如同它们都指向同一个空序列的末尾"（[[iterator.concept.forward#2]]）。¶7 本身并不给这个许可；它来自更强的类别要求。

!!! impl "libc++ 的做法"
    libc++ 的 `vector<T>::iterator` 是 `__wrap_iter<T*>`，它的默认构造函数写成 `__wrap_iter() noexcept : __i_() {}`——即使默认初始化，内部指针也被值初始化为空。所以在 libc++ 上 `auto d = a;` 不会出事。但这只是实现的善意：标准层面它仍是奇异值，换一个实现（或打开调试模式的迭代器检查）就可能被诊断或崩溃。

!!! lawyer "与 C++26 错误值的关系"
    `int* p; int* q = p;` 在 C++26 的核心语言中是**错误行为**（*erroneous behavior*，[[basic.indet]]），而不是 UB——自动变量未初始化时字节持有"错误值"。但 ¶7 是**库**的规则：把这样的 `p` 传给库函数作为迭代器使用，库仍可以说"结果未定义"。两条规则各管各的：核心语言管"读这个值本身"，库管"把它当迭代器交给我之后的事"。

## 范围（¶8–¶13）

### 两种范围（¶8）

¶8：标准库的算法大多以**范围**（*range*）为接口，范围有两种表示：

- 迭代器 + **哨位**（*sentinel*）：`[i, s)`，标记计算的起点与终点；
- 迭代器 + **计数**：`i+[0, n)`，标记起点与元素个数。

脚注 177 强调：哨位可以与迭代器**同类型，也可以不同类型**。

### `[i, s)` 的含义（¶9）

¶9：表示范围的迭代器与哨位必须可比较。若 `i == s`，范围为空；否则 `[i, s)` 指从 `i` 所指元素开始、到**第一个**满足 `j == s` 的迭代器 `j` 所指元素（若存在）为止、但不含后者的那些元素。

"第一个"二字很关键：对 `[p, unreachable_sentinel)`，不存在这样的 `j`，范围是"无限"的。

### 可达性与有效范围（¶10）

!!! std
    A sentinel s is called *reachable from* an iterator i if and only if there is a finite sequence of applications of the expression ++i that makes i == s. If s is reachable from i, [i, s) denotes a *valid range*.

    若对 `i` 有限次地应用 `++i` 能使 `i == s`，则称 `s` 从 `i` **可达**（[[g:reachable-sentinel]]）；此时 `[i, s)` 是**有效范围**（[[g:valid-range]]）。

有效性是一个**动态的、语义的**性质，不是类型层面的。`std::find(v.end(), v.begin(), x)` 能编译，但 `[v.end(), v.begin())` 不是有效范围（对非空 `v`，从 `end()` 递增永远到不了 `begin()`）。

### 计数范围（¶11）

¶11 递归地定义**计数范围**（[[g:counted-range]]）`i+[0, n)`：`n == 0` 时为空且有效；否则它有效当且仅当 `n` 为正、`i` 可解引用、且 `++i+[0, --n)` 有效。这就是 `std::copy_n`、`counted_iterator`（[[iterators.counted]]）、`views::counted` 所依赖的模型：不需要知道终点在哪，只要知道"还剩几个"。

### 无效范围 → UB（¶12）

!!! std
    The result of the application of library functions to invalid ranges is undefined.

    对无效范围调用库函数，结果是未定义的。

这是本节唯一一条直接的 UB 条款，但它覆盖面极大：传反了首尾、首尾来自不同容器、在遍历过程中修改容器导致中间某个迭代器失效……全部落在这里。

```cpp run title="invalid_range.cpp"
#include <algorithm>
#include <vector>

int main() {
    std::vector<int> a{1, 2, 3}, b{4, 5, 6};
    auto n1 = std::count(a.begin(), a.end(), 2);   // OK
    // auto n2 = std::count(a.begin(), b.end(), 2); // UB：b.end() 从 a.begin() 不可达（¶12）
    // auto n3 = std::count(a.end(), a.begin(), 2); // UB：同上
    return static_cast<int>(n1) - 1;
}
```

### 连续迭代器：库可以换成指针（¶13）

¶13 是 C++20 随 `contiguous_iterator` 引入的一项**授权**：对建模 `contiguous_iterator` 的 `i`，库函数可以把 `[i, s)` 替换为 `[to_address(i), to_address(i + ranges::distance(i, s)))`，把 `i+[0, n)` 替换为 `[to_address(i), to_address(i + n))`。

注 3 指出后果：程序**不能依赖**对连续迭代器解引用或单次递增的副作用——库可能根本不调用你的 `operator*`/`operator++`，而是拿到裸指针后直接 `memmove`，或者一次性 `i + n` 跳到终点。所以给连续迭代器的 `operator*` 加"访问计数"或日志，计数结果是不可靠的。这也是 `contiguous_iterator` 语义要求（[[iterator.concept.contiguous]]）中 `ranges::iter_move(a)` 必须与 `std::move(*a)` 效果相同的原因：库要能随时换成指针而不改变程序含义。

## 其他规定（¶14–¶17）

### 复杂度：只要求常数时间可实现的操作（¶14）

¶14：每个类别只要求那些对该类别**可在（摊还）常数时间内实现**的操作，所以要求表与概念定义都不写复杂度。这句话是 `operator+` 只属于随机访问迭代器、`std::list` 迭代器没有 `operator+` 的理由——不是做不到，而是做不到常数时间。它也是 `std::advance`/`ranges::next` 存在的理由（[[iterator.primitives]]）。

### 析构可能使引用失效（¶15）

!!! std
    Destruction of an iterator may invalidate pointers and references previously obtained from that iterator if its type does not meet the *Cpp17ForwardIterator* requirements and does not model forward_iterator.

    对既不满足 *Cpp17ForwardIterator*、又不建模 `forward_iterator` 的迭代器，销毁它可能使先前从它取得的指针和引用失效。

这允许输入迭代器把"当前元素"存在自己体内（*stashing*）：`istream_iterator<T>` 正是这样，`*it` 返回的是对其成员 `value` 的引用（[[istream.iterator]]）。所以下面这种写法对输入迭代器是危险的：

```cpp
const int& r = *std::istream_iterator<int>(std::cin);  // 临时迭代器在完整表达式末尾销毁，r 悬垂
```

反过来，前向迭代器**不允许**这样做：[[iterator.concept.forward#3]] 要求，只要 `[i, s)` 仍是范围，从中取得的指针和引用就保持有效。所以"把元素存在迭代器体内"的类型最多只能是输入迭代器——即使它语法上满足 `forward_iterator`，也不**建模**它。`reverse_iterator` 的 `operator*` 正是因此会在这种"伪前向"迭代器上悬垂（[[reverse.iterators]]）。

### 无效迭代器（¶16）

¶16：**无效迭代器**（[[g:invalid-iterator]]）是**可能**是奇异的迭代器。脚注 178 补充：这一定义同样适用于指针（指针本身就是迭代器），而对已失效迭代器解引用的效果是未定义的。容器条款里大量"使迭代器失效"的规定（如 `vector::push_back` 扩容后所有迭代器失效），说的就是这个状态——它不保证一定变成奇异值，但你不能再假设它不是。

### constexpr 迭代器（¶17）

¶17：若为满足类别要求而提供的所有操作都是 constexpr 函数，迭代器就满足 **constexpr 迭代器**要求（[[g:constexpr-iterator]]）。注 4 举例：`int*` 与 `reverse_iterator<int*>`。这是库在常量求值中使用迭代器的门槛——比如 constexpr 的 `std::sort` 要求传入的迭代器是 constexpr 迭代器。

## 常见误区

!!! pitfall "“能编译”不等于“是有效范围”"
    类型系统只能检查迭代器与哨位**能否比较**（`sentinel_for`），无法检查哨位**可达**。可达性永远是调用者的前提条件；`ranges::` 算法也只是把它写进了 [[iterator.concept.sentinel]] 的语义要求，编译器同样不检查。

!!! pitfall "值初始化的迭代器不是“空范围的 begin”"
    `It{}` 只在前向迭代器上有"如同指向同一空序列末尾"的语义，且只能与**同类型的值初始化迭代器**比较。拿它和某个容器的 `end()` 比较，仍然是 UB——它们不属于同一序列。

## 思考题

!!! question "思考题"
    1. `std::vector<int> v; auto b = v.begin(), e = v.end();` 这里的 `b`、`e` 是奇异值吗？`[b, e)` 是有效范围吗？
    2. 为什么 ¶7 允许"用值初始化的迭代器作为复制源"，却不干脆规定"值初始化的迭代器不是奇异值"？
    3. 一个类型把当前元素缓存在自身，`operator*` 返回对该成员的引用，其余操作都满足 `forward_iterator` 的语法。它的 `std::forward_iterator<It>` 为真吗？把它交给 `std::ranges::reverse_view` 会怎样？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 不是奇异值：它们与 `v` 这个（空）序列关联，`b == e` 为真，`[b, e)` 是有效的空范围（¶9、¶10，零次 `++` 即可达）。`b` 是过尾值，不可解引用。
2. 因为"不与任何序列关联"正是值初始化迭代器的本质——它确实是奇异的。规定它可被复制，只是为了让容器、算法里 `It tmp{}; ... tmp = other;` 这类代码有定义；更强的"可比较"保证只给前向迭代器（[[iterator.concept.forward#2]]）。
3. 语法上为真（`forward_iterator` 的语法部分都满足），但它违反了 [[iterator.concept.forward#3]] 的语义要求，所以只是**满足**而不**建模**。依据 [[res.on.requirements#2]]，若程序的含义依赖于它是否建模该概念，程序 {{ifndr}}；实际上 `reverse_view`/`reverse_iterator` 的 `operator*` 先复制再 `--tmp` 后解引用，返回的引用指向已销毁的临时副本，运行时悬垂。
</details>

## 小结

!!! summary
    - 关联量：值类型、可写类型、差值类型（有符号类整数类型，可以是整数类类型）。
    - 三种值：可解引用 ⊂ 非奇异；过尾值库永不解引用；奇异值只能销毁、被赋值、（值初始化时）被复制。
    - 范围：`[i, s)`（哨位可异类）与 `i+[0, n)`；有效 = 可达；对无效范围调用库函数是 UB（¶12）。
    - 连续迭代器：库可改用 `to_address` 指针，不要依赖解引用/递增的副作用。
    - 非前向迭代器可以"把元素存在体内"，析构即失效；前向迭代器不可以。
    - 无效迭代器 = 可能奇异；constexpr 迭代器 = 所需操作全为 constexpr。
