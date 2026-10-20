---
title: 从 Boost、TR1 到 C++26：标准库的现代演进
summary: C++98 之后标准库怎样长大：组件从哪里来，哪些设计是在修补旧设计，ABI 兼容为什么让已有组件很难再改，以及标准库该不该继续扩大的争论。
status: draft
order: 70
since: c++11
papers: N1836, N1856, N2661, N3916, N4542, P0088R3, P0323R12, N4128, P0896R4, P0645R10, P2216R3, P1863R1, P2000R4, P3001R0, P3471R4
related: utilities, smartptr, unique.ptr, util.sharedptr, func.wrap, time, time.zone, filesystems, optional, variant, any, string.view, expected, mem.res, ranges, format, views.multidim, linalg, simd, inplace.vector, hive, exec, toolchain/name-mangling, toolchain/object-layout-and-vtables
tags: 沿革, 标准库, Boost, TR1, ABI, Ranges, format
updated: 2026-10-19
---

!!! tldr
    - C++98 之后进入标准库的组件，几乎都先在 Boost、公司代码库或作者的开源库里用了多年，再经 TR1、TS 或直接提案进入标准。
    - 不少今天的组件是在修补旧设计：`unique_ptr` 取代 `auto_ptr`，`move_only_function`/`function_ref` 弥补 `std::function`，`expected` 避开了 `variant` 的 valueless 状态。
    - 组件一旦被编译进大量二进制文件，它的内存布局和函数签名就很难再改（ABI 约束），所以改进常以新增类型的形式出现。
    - 标准库该覆盖多大范围没有共识：网络和 2D 图形没有进入，`hive`、`simd`、`linalg` 进入了 C++26。
    - C++26 的标准库加固把一部分前置条件违反从未定义行为变成了契约违反。

## 先有实践，后有标准

C++98 的标准库只有容器、迭代器、算法（来自 STL）、iostream、string、locale 和从 C 继承来的部分。哈希表、正则表达式、智能指针、线程、文件系统都不在里面。

Stroustrup 回忆，1998 年标准收尾时委员会普遍觉得库做得不够，而且已批准的部分缺少试验和性能测量（HOPL III §4.2）。哈希表就是一例：1995 年有人提交过哈希表提案，但委员会已经没有时间做细致的设计。此后各家实现各自提供了互不兼容的 `hash_map`，标准化时只好换个名字，这就是 `unordered_map` 这个名字的由来。

为了避免重蹈覆辙，委员会成员在 1998 年发起了 **Boost**：一个经过同行评审的开源库集合，明确目的是为将来的标准化积累既有实践（HOPL IV §2.3）。一个库先在 Boost 里接受公开评审和真实项目的检验，几年后作者再带着实现经验去写标准提案。regex、thread、`shared_ptr`、variant、filesystem 都走了这条路。

Boost 不是唯一的来源，但这个先实践后标准化的模式被后来的提案者普遍沿用：string_view 的先例在 Google、LLVM 和 Bloomberg 的代码库里，PMR 来自 Bloomberg，{fmt}、range-v3 和 date 都是作者个人维护的开源库。

### TR1 与 TS：标准之外的中间站

**技术报告**（technical report）不是标准，没有强制力，作用是先把一组设计写下来，让实现者实现、用户试用。第一份库技术报告 TR1 在 2007 年发布，包含 `shared_ptr`/`weak_ptr`、`function`/`bind`、`tuple`、`<type_traits>`、`<random>`、`array`、无序容器和 `<regex>`。

TR1 的组件声明在 `std::tr1` 命名空间里，当时的代码要写 `std::tr1::shared_ptr`。C++11 把它们几乎全部搬进 `std`，并借助右值引用、可变参数模板重写了接口：`tuple` 不必再模拟可变参数，`function` 和 `bind` 支持完美转发。

C++11 之后的扩展改用按主题划分的**技术规范**（Technical Specification，TS），例如 Filesystem TS、Library Fundamentals TS、Ranges TS、Networking TS。实现者在 `std::experimental` 下提供它们，委员会收集经验后再决定是否并入。近年的提案更常直接以国际标准为目标，`format` 和 `expected` 都中途放弃了 TS 路线。

## auto_ptr → unique_ptr：没有移动语义时的移动

C++98 唯一的智能指针 `auto_ptr` 表示独占所有权。语言当时没有移动语义，它只能借用复制的语法来转移所有权：

<div class="compare" markdown="1">

```cpp title="C++98：复制即转移"
std::auto_ptr<int> a(new int(1));
std::auto_ptr<int> b = a;
// a 悄悄变成了空指针
```

```cpp title="C++11：转移要写出来"
std::unique_ptr<int> a(new int(1));
std::unique_ptr<int> b = std::move(a);
// std::unique_ptr<int> c = b;  // error
```

</div>

Howard Hinnant 在 [[N1856]]（2005）中说明了左边为什么不可接受：泛型代码假设复制之后源和目标等价。把 `auto_ptr` 放进容器再排序，某个 `sort` 实现可能把一个元素复制到局部变量当作枢轴，容器里的那个元素就被置空了，结果取决于实现，甚至会崩溃。

N1856 的办法是新增只可移动、不可复制的 `unique_ptr`，把转移所有权交给 C++11 的右值引用。本来会悄悄转移所有权的代码，现在变成编译错误：

```cpp run error
#include <memory>
#include <vector>
int main() {
    std::vector<std::unique_ptr<int>> v;
    v.push_back(std::make_unique<int>(1));
    auto q = v[0];   // error: unique_ptr 的复制构造函数被删除
}
```

由于 `unique_ptr` 能直接替代 `auto_ptr`，委员会得到了一个少有的机会，把一个有缺陷的设施真正移除（HOPL IV §4.2.4）。`auto_ptr` 在 C++11 中弃用，C++17 中移除（[[N4190]]，见 [[diff.cpp14.depr]]）。`make_unique` 则晚到 C++14 才补上。

```cpp run error
#include <memory>
int main() {
    std::auto_ptr<int> p(new int(1));   // error: C++17 起 std::auto_ptr 已被移除
}
```

!!! impl "unique_ptr 的调用约定代价"
    `unique_ptr` 在源代码层面是零开销抽象，但在主流的 Itanium C++ ABI 下，有非平凡析构函数的类类型按值传参时必须经由内存传递，不能放在寄存器里。[[P1863R1]] 把这列为一个因 ABI 约束而无法消除的性能问题，下文 ABI 一节会回到这个话题。参见 [[toolchain/object-layout-and-vtables]]。

## std::function 与三个新包装器

`std::function` 来自 Boost.Function，经 TR1 进入 C++11。它是一种[[g:type-erasure|类型擦除]]包装：签名匹配的任何可调用对象都能存进同一个类型 `function<R(Args...)>`，代价是可能的堆分配和一次间接调用。它有两个后来被反复讨论的问题。

第一，`function` 自身可复制，所以它要求被包装的对象可复制。捕获了 `unique_ptr` 的 lambda 放不进去：

```cpp run error
#include <functional>
#include <memory>
int main() {
    auto p = std::make_unique<int>(10);
    std::function<int(int)> g = [p = std::move(p)](int x) { return x + *p; };
    // error: std::function 要求可复制，而这个 lambda 只能移动
}
```

第二，它的 `operator()` 是 `const` 成员函数，却会调用被包装对象的非 `const` 调用运算符，这是常量正确性上的漏洞。

修改 `std::function` 会改变已有代码的行为，也会破坏 ABI，委员会于是增加了新类型：

| 类型 | 拥有对象 | 可复制 | 版本 |
|---|---|---|---|
| `function` | 是 | 是 | C++11 |
| `move_only_function` | 是 | 否 | C++23 |
| `copyable_function` | 是 | 是 | C++26 |
| `function_ref` | 否 | 是（浅复制） | C++26 |

后三者的签名里可以写 `const`、`noexcept` 和引用限定符，例如 `copyable_function<int(int) const>`，从而修正了常量正确性问题。

```cpp run
#include <functional>
#include <memory>
#include <print>
int call_twice(std::function_ref<int(int)> f, int x) { return f(f(x)); }   // 不拥有，不分配
int main() {
    auto p = std::make_unique<int>(10);
    std::move_only_function<int(int)> add = [p = std::move(p)](int x) { return x + *p; };
    std::println("{}", call_twice(add, 1));   // 21
}
```

这个例子按标准是良构的，但本机 Clang 23 附带的 libc++ 还没有提供 `move_only_function` 和 `function_ref`，所以没有标判定，可以点 godbolt 按钮用 GCC trunk 验证。

一个类型变成四个，也招来了批评：David Sankel 在 [[P3023R1]] 中认为这无助于降低复杂度。支持者的理由是它们的语义确实不同，一个类型无法同时满足。条款见 [[func.wrap]]。

## chrono：用类型区分单位

C++11 的线程库需要表达睡眠时长和等待截止时间，[[N2661]]（2008）为此提出了 `duration`、`time_point` 和时钟。它的几个设计选择决定了今天 `<chrono>` 的用法。

**精度中立。** `duration<Rep, Period>` 用编译期有理数 `ratio` 表示单位，`hours`、`nanoseconds` 只是同一个类模板的不同实例。

**只允许无损的隐式转换。** 粗单位可以隐式变成细单位，反过来必须写 `duration_cast`：

<div class="compare" markdown="1">

```cpp ok
#include <chrono>
using namespace std::chrono;
seconds s = hours(1);    // 无损
minutes m = duration_cast<minutes>(
    seconds(90));        // 显式截断
int main() {}
```

```cpp error
#include <chrono>
using namespace std::chrono;
hours h = seconds(3600);
// error: 有损转换必须
// 写 duration_cast
int main() {}
```

</div>

**不做日历。** N2661 有一节标题就是 *Sold Separately*：不提供日历，不规定纪元，不处理闰秒，只承诺做将来日期库的基础。这个日历库后来由 Hinnant 本人以开源的 date/tz 库完成，经 [[P0355R7]] 进入 C++20。

日历部分延续了用类型防错的思路：`year`、`month`、`day`、`weekday` 是各自独立的类型，`ymd + 10` 这种分不清加的是日、月还是年的写法会被拒绝；日期换算是 `constexpr` 的（HOPL IV §9.3.6）。

```cpp run ok
#include <chrono>
#include <print>
using namespace std::chrono;
static_assert(year_month_day{2016y / May / 29d}.ok());
static_assert(weekday{sys_days{2016y / May / 29}} == Sunday);   // 编译期算出星期
int main() {
    constexpr auto d = 2026y / October / 18d;
    std::println("{} is a {}", d, weekday{sys_days{d}});   // 2026-10-18 is a Sun
}
```

条款见 [[time]]、[[time.cal]]、[[time.zone]]。

## 文件系统：两套错误报告

`std::filesystem` 来自 Boost.Filesystem，经 Filesystem TS 并入 C++17，是 TS 机制按设计运作的例子。

它的一个特点是大多数操作都有两个版本：一个出错时抛出 `filesystem_error`，另一个接受 `error_code&` 参数、不抛异常。Stroustrup 的解释是，文件操作的错误有时是罕见的异常情况，有时是预期之中的结果（比如文件不存在），两种情况都要照顾（HOPL IV §8.6）。条款见 [[filesystems]]。

## 词汇类型：optional、variant、any、string_view

C++17 新增了一批在接口之间传递数据用的**词汇类型**（vocabulary type）。它们大多经由 Library Fundamentals TS 进入标准。

`string_view` 的先例是 Google 的 `StringPiece`、LLVM 的 `StringRef` 等字符串引用类型，用来避免为了传参而构造 `std::string`（[[N3921]]）。它不拥有所指的字符，因此也是悬垂引用的常见来源（见 [[topics/dangling-references]]、[[string.view]]）。

### variant 的空状态

`variant` 设计中争论最久的是赋值时的异常安全。设 `v` 持有 `S`，要改为持有 `T`：`v` 必须先销毁 `S`，再在同一块存储上构造 `T`。如果 `T` 的构造抛出异常，`v` 里就既没有 `S` 也没有 `T`。[[N4542]] 逐一讨论了几种出路：

- 要求所有备选类型的构造不抛异常。这个限制太强，而且哪些类型满足它取决于实现。
- 双缓冲：Boost.Variant 先在另一块存储上构造新值，成功后再销毁旧值。代价是额外内存，以及内部存储的地址会变化。
- 引入一个可见的空状态，类似被移动后的对象：有效，但内容未指定。

最终选了第三种。处于这种状态时，`get` 和 `visit` 抛出 `bad_variant_access`（[[P0088R3]]），查询函数取名 `valueless_by_exception()`，名字本身就在提醒这个状态只来自异常。

```cpp run ok
#include <variant>
#include <stdexcept>
#include <cstdio>
struct Bomb {
    Bomb() = default;
    Bomb(Bomb&&) { throw std::runtime_error("boom"); }
};
int main() {
    std::variant<int, Bomb> v = 42;
    try {
        v.emplace<Bomb>(Bomb{});   // 先销毁 int，再用会抛异常的移动构造函数初始化 Bomb
    } catch (const std::runtime_error&) {}
    std::printf("%d %d\n", v.valueless_by_exception(), v.index() == std::variant_npos);   // 1 1
}
```

### 三个类型，三种接口

`optional`、`variant`、`any` 是分开设计的，接口差别很大：取值分别写 `*opt`、`get<int>(var)`、`any_cast<int>(a)`。Stroustrup 称之为委员会设计的经典例子，认为模式匹配才是更根本的解决办法（HOPL IV §8.3）；方向组的 [[P2000R4]] 也把它列为标准库缺乏一致性的例证。条款见 [[optional]]、[[variant]]、[[any]]。

## PMR：分配器不再改变容器的类型

C++98 的分配器是容器的模板参数，换一个分配器就换了一个类型：`vector<int, A1>` 和 `vector<int, A2>` 不能互相赋值，接受 `vector<int>` 的函数也不接受它们。

[[N3916]]（Halpern）把分配策略放进一个虚基类 `memory_resource`，再用固定的分配器类型 `polymorphic_allocator` 在运行期指向某个资源。这样所有使用 PMR 的容器都是同一个类型，比如 `std::pmr::vector<int>`。这套设施来自 Bloomberg 内部使用了十多年的 BSL 库，提案说它显著提高了可测试性（可以注入测试用的资源）。

```cpp run ok
#include <memory_resource>
#include <vector>
#include <cstddef>
#include <print>
int main() {
    std::byte buffer[1024];
    std::pmr::monotonic_buffer_resource arena(buffer, sizeof buffer);
    std::pmr::vector<int> v(&arena);   // 先从栈上的 buffer 取内存，用完再向上游资源要
    for (int i = 0; i < 10; ++i) v.push_back(i);
    std::println("{}", v.size());      // 10
}
```

这是用一次虚函数调用换取类型统一的取舍，与前文 `std::function` 用类型擦除换取统一类型是同一种思路。条款见 [[mem.res]]。

## expected：错误作为返回值

`expected<T, E>` 把一个值或一个错误做成返回类型。它从 2014 年的 [[N4015]] 到 2022 年并入 C++23 用了约八年。被反复审阅的主要是它在错误处理方案中的定位：它与异常、`error_code`、Boost.Outcome，以及当时提出的确定性异常（[[P0709R4]]）是什么关系，还有 `E` 要不要默认为 `std::error_code`（最后决定不设默认值）。

它在设计上明确避开了 `variant` 的空状态：[[P0323R12]] 保证 `expected` 总是持有 `T` 或 `E` 之一，用户不必处理 valueless 状态。C++23 还给 `optional` 和 `expected` 加上了 `and_then`、`transform`、`or_else` 这些一元式操作（[[P0798R8]]、[[P2505R5]]）。

```cpp run ok
#include <expected>
#include <charconv>
#include <string_view>
#include <print>
enum class parse_error { not_a_number, out_of_range };
std::expected<int, parse_error> parse_int(std::string_view s) {
    int value{};
    auto [ptr, ec] = std::from_chars(s.data(), s.data() + s.size(), value);
    if (ec == std::errc::invalid_argument) return std::unexpected(parse_error::not_a_number);
    if (ec == std::errc::result_out_of_range) return std::unexpected(parse_error::out_of_range);
    return value;
}
int main() {
    auto doubled = parse_int("21").transform([](int x) { return x * 2; });
    std::println("{}", doubled.value_or(-1));          // 42
    std::println("{}", parse_int("abc").has_value());  // false
}
```

条款见 [[expected]]。

## Ranges：哨兵与第二套算法

STL 用一对迭代器表示序列。[[N4128]]（Niebler、Parent、Sutton，2014）提出以范围作为算法的参数，同时有意保留迭代器作为基础，理由是迭代器作为算法基础已有可靠的记录。它引入的关键改变是**哨兵**（sentinel）：范围的终点可以是与迭代器不同的类型。这样，到某个谓词为止、或者从某处数 n 个元素的序列，不必伪造一个结束迭代器。

Ranges 依赖概念，而概念直到 C++20 才进入语言，所以它先以 Ranges TS 的形式发布，C++20 再通过 [[P0896R4]] 并入。为了不改变旧代码的行为，原有的 `std::sort` 等算法保持不动，另在 `std::ranges` 里提供一套受约束的新算法。今天标准库里两套算法并存，就是这样来的。

```cpp run ok
#include <ranges>
#include <vector>
#include <print>
int main() {
    std::vector<int> v{1, 2, 3, 4, 5, 6, 7, 8, 9, 10};
    auto r = v | std::views::filter([](int i) { return i % 2 == 0; })
               | std::views::transform([](int i) { return i * i; })
               | std::views::take(3);
    std::println("{}", r);                          // [4, 16, 36]
    auto w = std::views::zip(v, v | std::views::drop(1))
           | std::ranges::to<std::vector>();        // C++23
    std::println("{}", w.size());                   // 9
}
```

C++20 的 Ranges 缺少不少 range-v3 里已有的组件。C++23 按 [[P2214R2]] 的优先级补上了 `views::zip`、`ranges::to`、`views::chunk_by`、`ranges::fold_left` 等，C++26 又加了 `views::concat` 等。条款见 [[ranges]]。

## format：类型安全的格式串

iostream 类型安全、可扩展，但格式化能力弱；`printf` 写起来方便，却不检查类型。`std::format` 想两者兼得：用格式串，同时保持类型安全和可扩展（HOPL IV §9.3.7）。它的原型是 Victor Zverovich 的开源库 {fmt}，C++20 通过 [[P0645R10]] 并入。

审阅中定下的几个设计决定在今天的条文里都能看到：采用 Python 风格的 `{}` 而不是 `%`；用户通过特化 `std::formatter<T>` 扩展格式；默认不依赖 locale；浮点数默认输出能精确往返的最短表示（Zverovich，*std::format in C++20*，2019）。

```cpp run ok
#include <format>
#include <string>
#include <print>
struct Point { int x, y; };
template <>
struct std::formatter<Point> : std::formatter<std::string> {
    auto format(Point p, auto& ctx) const {   // 泛型上下文：放进容器里也能格式化
        return std::formatter<std::string>::format(std::format("({}, {})", p.x, p.y), ctx);
    }
};
int main() {
    std::println("{}", std::format("{:>8}|{:<6.2f}|{:#x}", "abc", 3.14159, 255));   //      abc|3.14  |0xff
    std::println("{}", Point{1, 2});                                                // (1, 2)
}
```

C++20 刚发布时，格式串的错误要到运行期才以异常报告。[[P2216R3]] 把格式串参数改为 `consteval` 构造的 `basic_format_string`，在编译期检查，并作为缺陷报告追溯适用于 C++20：

```cpp run error
#include <format>
int main() {
    auto s = std::format("{:d}", "text");   // error: 字符串不能按 d 格式化，编译期即被拒绝
}
```

C++23 加入了 `std::print`/`std::println` 和范围的格式化。条款见 [[format]]、[[print.fun]]。

## C++23 之后：数值与容器

C++23 之后，标准库的增长转向了高性能计算和底层容器。这些组件都有较长的提案史。

| 组件 | 版本 | 说明 |
|---|---|---|
| `mdspan` | C++23 | 多维数组视图，不拥有内存（[[views.multidim]]） |
| `linalg` | C++26 | 以 BLAS 为基础、建立在 `mdspan` 之上的线性代数（[[linalg]]） |
| `simd` | C++26 | 数据并行类型，先在 Parallelism TS 2 中试验（[[simd]]） |
| `inplace_vector` | C++26 | 容量在编译期固定、元素就地存储的可变长数组（[[inplace.vector]]） |
| `hive` | C++26 | 插入、删除不使其他元素的迭代器失效的容器（[[hive]]） |

`mdspan` 的下标写法 `m[i, j]` 依赖 C++23 的语言改动：`operator[]` 可以接受多个参数（[[P2128R6]]）。这是库的需求推动语言修改的一个例子。

```cpp run ok
#include <mdspan>
#include <vector>
#include <print>
int main() {
    std::vector<double> buf(6);
    std::mdspan m(buf.data(), 2, 3);           // 2 行 3 列，默认行主序；不拥有内存
    for (std::size_t i = 0; i < m.extent(0); ++i)
        for (std::size_t j = 0; j < m.extent(1); ++j)
            m[i, j] = 10.0 * i + j;
    std::println("{}", buf);                   // [0, 1, 2, 10, 11, 12]
}
```

截至写作时，本机 libc++ 已提供 `mdspan`，还没有 `<linalg>`、`<simd>`、`<inplace_vector>` 和 `<hive>`。

## ABI：为什么已有的组件很难再改

**ABI**（application binary interface）指编译出的二进制之间的约定：类的内存布局、调用约定、名字修饰。标准正文里没有 ABI 这个词，但它实际上约束着标准库：改变一个类的数据成员，或者改变一个函数的签名，新旧代码在链接或运行时就会不一致（见 [[toolchain/name-mangling]]）。

### C++11 的那次断裂

C++11 禁止 `basic_string` 用引用计数实现（[[diff.cpp03.strings]]），并要求 `list::size()` 为常数时间（[[diff.cpp03.containers]]）。libstdc++ 为此在 GCC 5.1 引入了新的 `std::string` 和 `std::list`，为了不让旧二进制失效，从此同时提供新旧两套 ABI（libstdc++ 手册，*Dual ABI*）。实现者普遍认为这次断裂昂贵而痛苦，之后的标准版本都尽量避免破坏 ABI（[[P1863R1]]）。

### 被 ABI 挡住的改进

[[P1863R1]]（Winters，*ABI - Now or Never*，2020）列出了一些因此无法收回的性能：

- `unordered_map` 和 `std::hash` 的布局与哈希函数，改进需要所有代码重新编译；
- 按值传递 `unique_ptr` 的开销，由调用约定决定；
- `std::string` 的短字符串优化调优。

`std::regex` 是另一个例子：改进它的实现往往需要改变类的布局或内部模板的签名，而这些已经被编译进了用户的二进制。[[P3001R0]] 把 `vector<bool>`、`unordered_map` 和 `regex` 并列为不够好、又没坏到能移除、只能一直留下的设施。

P1863R1 认为委员会应当二选一：定一个版本做 ABI 断裂，或者明确承诺 ABI 稳定，并告诉需要极致性能的用户去用外部库。2020 年委员会就此做了一组意向投票，结果是两者都不选：不承诺永远稳定，也不在 C++23 做大规模断裂（会议记录 [[P2130R0]]）。后来的方向组文件 [[P2000R4]] 和 [[P3466R1]] 都采取逐案评估的立场：与旧版 C++ 的链接兼容是默认要求，个别提案可以破坏 ABI，但要明确讨论并记录理由。

实际效果是，已有组件的布局很难再改，改进常以新增类型的形式出现。`function` 之后的三个包装器就是例子。

## 没有进入标准的提案

**Networking TS。** 它基于 Asio，有十几年的生产使用，2018 年以 TS 发布。但它依赖执行器，而执行器的设计一直在变；2021 年委员会转向发送器/接收器模型后，网络库需要在新模型上重新设计，最终没有进入 C++26。经过见 [[history/executors-to-execution]]。

**2D 图形。** 以 Cairo 为基础的 2D 图形提案（[[P0267R10]] 等）在 2018 年失去了继续推进的共识。据作者的回顾（[[P0988R0]]），反对理由包括：措辞超过 140 页，审阅会占用大量委员会时间；有人认为国际标准里不该有图形 API，也有人认为这套 API 已经过时。委员会决定当时不再以任何形式继续图形方面的工作，参考实现 io2d 作为独立项目继续（Sutter，Rapperswil 会议报告，2018 年 6 月）。

## 标准库加固（C++26）

C++26 引入了[[g:hardened-implementation|加固实现]]：实现是否加固由实现定义（[[intro.compliance#8]]）。在加固实现中，违反[[g:hardened-precondition|加固前置条件]]（如 `vector::operator[]` 的下标范围、`optional::operator*` 要求有值）会以终止语义触发契约违反；在非加固实现中，它仍是未定义行为（[[structure.specifications#3.5]]）。

```cpp ub
#include <vector>
#include <cstdio>
int main() {
    std::vector<int> v{1, 2, 3};
    std::printf("%d\n", v[3]);   // UB: 非加固实现中越界访问；加固实现中是契约违反，程序终止
}
```

用 libc++ 时，可以用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 打开它的加固模式。本机 Clang 23 以 `-O2` 和该宏编译上例，程序在越界访问处以 trap 终止（退出码 133，即 SIGTRAP），不会读取越界内存。

这项设计来自 libc++ 的加固模式（[[P3471R4]]）。它只检查已有的前置条件，不新增前置条件；开销要低到可以在生产环境中开启，论文引用 Google 的报告，在数亿行代码上部署后性能影响低至 0.3%；设计上避免要求改变 ABI，使加固和非加固代码可以混在同一个程序里。

## 标准库应该多大

上面几节反复出现同一个问题：什么东西应当进入标准库。各方的立场都有文档可查。

- **克制。** [[P3001R0]] 认为标准库擅长的是需要编译器支持的设施、词汇类型、跨平台操作系统抽象和基础算法与数据结构。高性能容器的价值在于持续跟进硬件，标准化之后接口和 ABI 都被冻结，所以 `hive` 这类容器不适合标准库。
- **扩大。** [[P2000R4]] 建议提供网络、简单图形和对现代硬件的支持，理由之一是教学：学生应当能只用每个实现都提供的东西开始学习。
- **一致性。** P2000R4 同时指出，各组件被单独打磨，彼此风格不一，前文 optional/variant/any 的接口就是例子；它建议每个新特性都要有人明确考虑与其他特性的交互。

分歧主要在于具体组件属于哪一类，以及委员会的时间应当优先花在哪里。从结果看，C++26 接纳了 `hive`、`simd`、`linalg`，没有接纳网络库。

## 时间线

| 年份 | 事件 |
|---|---|
| 1998 | C++98；Boost 发起 |
| 2007 | TR1 发布：智能指针、`function`、`tuple`、`regex`、无序容器 |
| 2011 | C++11：TR1 并入 `std`；`unique_ptr`、`chrono`；弃用 `auto_ptr` |
| 2017 | C++17：filesystem、`optional`/`variant`/`any`、`string_view`、PMR；移除 `auto_ptr` |
| 2020 | C++20：Ranges、`format`、日历与时区；ABI 政策投票 |
| 2023 | C++23：`expected`、`mdspan`、`print`、`move_only_function` |
| 2026 | C++26：`std::execution`、`linalg`、`simd`、`inplace_vector`、`hive`、`function_ref`、标准库加固 |

<details class="fine" markdown="1"><summary>出处</summary>

- HOPL III：Bjarne Stroustrup，*Evolving a language in and for the real world: C++ 1991–2006*（2007），§4.2、§6.2。
- HOPL IV：Bjarne Stroustrup，*Thriving in a Crowded and Changing World: C++ 2006–2020*（2020），§2.3、§4.2.4、§8.3、§8.6、§9.3.6、§9.3.7。
- Victor Zverovich，*std::format in C++20*（2019）。
- Herb Sutter 的会议报告（herbsutter.com），用于各组件的并入时间。
- libstdc++ 手册，*Dual ABI* 一节。
- 其他 WG21 文档见正文链接。

</details>
