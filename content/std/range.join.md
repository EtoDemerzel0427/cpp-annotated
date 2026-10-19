---
title: join 与 join_with 视图
summary: views::join 把范围的范围展平成一个范围，views::join_with 在相邻的内层范围之间插入分隔符；内层范围是引用还是临时对象，决定了结果能否前向遍历、能否以 const 方式遍历。
status: done
covers: range.join, range.join.overview, range.join.view, range.join.iterator, range.join.sentinel, range.join.with, range.join.with.overview, range.join.with.view, range.join.with.iterator, range.join.with.sentinel
since: c++20
papers: P0896R4, P2441R2, P2770R0
related: range.adaptors, range.nonprop.cache, range.split, range.concat, range.transform, range.utility.conv, range.utility
tags: 标准库, 范围, join, join_with, 展平
updated: 2026-10-19
---

!!! tldr
    - `views::join` 把 `vector<vector<int>>` 展平成一串 `int`，空的内层范围被跳过。
    - 内层范围是外层元素的引用时，结果最高可以是双向范围，也能以 const 方式遍历。
    - 内层范围是临时对象（例如 `transform` 返回 `std::string`）时，它被暂存在视图里，结果只是输入范围，也不能以 const 方式遍历。
    - `views::join_with(sep)` 只在相邻内层范围之间插入分隔符，首尾不加；分隔符可以是单个元素，也可以是一个范围。
    - 字符串字面量不能直接当分隔符，要写成 `string_view` 或单个字符。

```cpp run ok
#include <iostream>
#include <ranges>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> ss{"hello", " ", "world", "!"};
  for (char ch : ss | std::views::join) std::cout << ch;     // hello world!

  std::vector<std::string> vs{"the", "quick", "brown", "fox"};
  for (char c : vs | std::views::join_with('-')) std::cout << c;
  std::cout << '\n';                                          // the-quick-brown-fox
}
```

这两段分别是 [range.join.overview] ¶3 和 [range.join.with.overview] ¶3 的标准例子。`join` 是 [[range.split]] 的逆运算，把切开的片段重新连起来；`transform` 加 `join` 也就是其他语言里的 `flat_map`（一个元素变成若干元素）。

## `views::join` [range.join.overview]

¶1 `join_view` 把一个由范围组成的视图展平成一个视图。¶2 `views::join(E)` 等价于 `join_view<views::all_t<decltype((E))>>{E}`，没有任何特例。

一个 `join_view` 的迭代器要同时记住两个位置：外层走到了第几个内层范围，内层走到了第几个元素。规则里的复杂之处几乎都来自一个问题：内层范围这个对象存放在哪里。

## 内层是引用：迭代器自己记住一切 [range.join.iterator]

`vector<vector<int>>` 的元素类型是 `vector<int>&`，内层范围就在外层容器里，一直存在。迭代器保存一个外层迭代器和一个内层迭代器就够了，随时可以回到外层。标准用说明用常量 *ref-is-glvalue*（`range_reference_t<Base>` 是不是引用类型）区分这种情况。

¶1 内层是引用时，迭代器的类别是：

- 外层双向，内层双向且是[[g:common-range|公共范围]]（`begin()` 和 `end()` 类型相同）时，是双向迭代器；
- 外层和内层都是前向范围时，是前向迭代器；
- 其他情况是输入迭代器（¶1.3）。

双向还要求内层是公共范围，是因为 `--` 从下一个内层范围倒退到上一个时，要从上一个内层的 `end()` 往回走（¶15），而 `end()` 必须是一个能 `--` 的迭代器。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <vector>

int main() {
  std::vector<std::vector<int>> vv{{1, 2}, {}, {3}};
  auto flat = vv | std::views::join;
  static_assert(std::ranges::bidirectional_range<decltype(flat)>);
  static_assert(std::ranges::range<const decltype(flat)>);
  static_assert(!std::ranges::sized_range<decltype(flat)>);
  for (int x : flat) std::printf("%d", x);                         // 123
  for (int x : flat | std::views::reverse) std::printf(" %d", x);  // 3 2 1
  std::puts("");
}
```

`join_view` 永远不是 sized range：总长度要把每个内层范围都看一遍才知道。它也不是借用范围。

### 跳过空的内层范围（¶4–¶6）

¶4 迭代器用说明用函数 *satisfy* 跳过空的内层范围。¶6 定义的 *satisfy* 不断推进外层，直到找到一个非空的内层范围或者外层结束；构造迭代器时（¶7–8）和每次 `++` 走完一个内层范围时（¶13）都会调用它。所以 `{{1, 2}, {}, {3}}` 展平后是 `1 2 3`，空的 `{}` 不产生任何元素。

因此 `++` 不是严格的 O(1)：连续有很多空内层范围时，一次 `++` 会跳过它们全部。

## 内层是临时对象：暂存在视图里 [range.join.view]

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string>
#include <vector>

int main() {
  std::vector<int> v{1, 2, 3};
  auto j = v | std::views::transform([](int i) { return std::string(i, 'x'); })
             | std::views::join;
  static_assert(std::ranges::input_range<decltype(j)>);
  static_assert(!std::ranges::forward_range<decltype(j)>);
  static_assert(!std::ranges::range<const decltype(j)>);
  for (char c : j) std::putchar(c);   // xxxxxx
  std::puts("");
}
```

这里解引用外层迭代器每次都返回一个新的 `std::string` 临时对象。内层迭代器指向它，所以它必须存放在某个地方，否则表达式一结束就销毁了，内层迭代器随之悬垂。

`join_view` 把它存在视图对象的成员 `inner_` 里。`inner_` 是一个 [[range.nonprop.cache|non-propagating-cache]]（复制视图时不随之复制的缓存），每进入一个新的外层元素，*satisfy* 就在里面重新构造一次内层范围（¶6 中的 *emplace-deref*）。

这样做的后果是：

- 迭代器的一部分状态在视图里，两个迭代器不可能各自停在不同的内层范围上，所以结果只能是输入范围（¶1.3）；
- 写 `inner_` 要修改视图，所以没有 const 版本的 `begin()`；
- `ranges::to<std::vector>` 不能事先知道大小，也不能对结果再套 `reverse`。

需要多趟遍历时，可以先物化成容器，或者让变换函数返回一个轻量的视图。

### 外层只是输入范围

外层 `V` 只是输入范围时，外层迭代器也存在视图的 `outer_` 缓存里：`begin()` 先执行 `outer_ = ranges::begin(base_)`，迭代器自身只保存指向视图的指针（[range.join.iterator] ¶5、¶8）。这一设计来自 C++23 期间以缺陷报告形式并入的 [[P2770R0]]。它修复的问题是：有些输入迭代器解引用时返回指向迭代器自身内部的引用，迭代器一旦被移动，之前取得的内层范围就悬垂了。

## `views::join_with`：带分隔符的展平 [range.join.with] {{c++23}}

¶1 `join_with_view` 接受一个视图和一个分隔符，展平视图，并在相邻的两个内层范围之间插入分隔符的全部元素。分隔符可以是单个元素，也可以是元素组成的视图。¶2 `views::join_with(E, F)` 等价于 `join_with_view(E, F)`（[[P2441R2]]）。

```cpp run ok
#include <cstdio>
#include <ranges>
#include <string>
#include <string_view>
#include <vector>

int main() {
  std::vector<std::string> words{"a", "bc", "d"};
  auto s = words | std::views::join_with(std::string_view(", "))
                 | std::ranges::to<std::string>();
  std::printf("[%s]\n", s.c_str());                  // [a, bc, d]

  std::vector<std::vector<int>> vv{{1, 2}, {}, {3}};
  for (int x : vv | std::views::join_with(0))
    std::printf("%d", x);                            // 12003
  std::puts("");
}
```

第二个例子说明空的内层范围仍然算一个元素：`{1, 2}` 与 `{}` 之间插入一次 0，`{}` 与 `{3}` 之间再插入一次，所以得到 `1 2 0 0 3`。首尾不加分隔符。

`join_with_view` 和 `join_view` 有同样的 *ref-is-glvalue* 区分：内层是临时对象时暂存在视图的 `inner_` 里，外层只是输入范围时外层迭代器存在 `outer_it_` 里，结论也相同。其余几点：

- 分隔符是单个元素时，推导指引和第二个构造函数（[range.join.with.view] ¶2）把它包进 `single_view`。
- 约束要求内层范围与分隔符满足 *concatable*（与 [[range.concat]] 共用）：两者的元素要有公共的引用类型和值类型。¶12 迭代器的 `operator*` 返回两者引用类型的 `common_reference_t`。
- 迭代器内部用一个 `variant` 保存当前位置，它要么指向分隔符，要么指向内层范围（¶8、¶13）。

## 常见误解

!!! pitfall "字符串字面量当分隔符"
    `w | views::join_with("--")` 编译失败。管道写法先把实参按值保存起来（[[range.adaptor.object#8]]），数组退化成 `const char*`，它既不是范围，也不是 `char`。

    函数调用写法 `views::join_with(w, "--")` 能编译，但结果不对：数组不退化，被包成 `ref_view<const char[3]>`，分隔符里包含结尾的 `'\0'`。

    ```cpp run ok
    #include <cstdio>
    #include <ranges>
    #include <string>
    #include <vector>

    int main() {
      std::vector<std::string> w{"a", "b"};
      auto s = std::views::join_with(w, "--") | std::ranges::to<std::string>();
      std::printf("%zu\n", s.size());   // 5：a - - \0 b
    }
    ```

    分隔符写成 `std::string_view("--")` 或单个字符即可。

## 小结

| 情形 | 迭代器类别 | 可以 const 遍历 | 状态存放在 |
|---|---|---|---|
| 内层是引用，外层与内层双向且内层是公共范围 | 双向 | 是 | 迭代器 |
| 内层是引用，外层与内层前向 | 前向 | 是 | 迭代器 |
| 内层是临时对象 | 输入 | 否 | 视图的 `inner_` |
| 外层只是输入范围 | 输入 | 否 | 视图的 `outer_` |

<details class="fine" markdown="1"><summary>其余条文</summary>

[range.join.view] ¶1：构造函数保存底层视图。`end()` 在外层和内层都是前向、公共范围且内层是引用时返回迭代器，结果是公共范围；否则返回哨位。

[range.join.iterator] ¶2–3：只有内层是引用、外层和内层都是前向范围时才定义 `iterator_category`，取外层和内层类别中较弱的一个；`difference_type` 是两者差值类型的公共类型。¶7–10 是构造函数，¶11 是 `operator->`，¶12–14 是 `++`，¶16 是相等比较，¶17 是 `iter_swap`。

[range.join.sentinel] ¶1–3：哨位保存外层的终点，迭代器的外层位置到达终点即为结束。

[range.join.with.iterator] 与 [range.join.with.sentinel] 的结构相同；它的 `value_type` 是内层与分隔符值类型的公共类型（¶3）。

</details>
