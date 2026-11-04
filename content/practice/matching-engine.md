---
title: 撮合引擎
summary: 一道交易公司现场编程面试里常见的题：实现一个支持多品种、限价单、撤单和改单的撮合引擎。本页给出完整题面和 17 个测试用例，一份参考实现和一份优化实现，两者的差分测试与实测对比，以及设计讨论和口头追问里常被问到的三十个问题和回答要点。
status: draft
order: 10
related: perf/measuring, perf/memory-hierarchy, perf/choosing-containers, perf/allocation, perf/false-sharing, toolchain/testing, topics/concurrency-in-practice, unord.req.general, associative.reqmts.general
tags: 撮合引擎, 订单簿, 面试, 哈希表, 延迟, 实战
updated: 2026-11-03
---

!!! tldr
    - 撮合引擎按价格优先、时间优先把买单和卖单配对，成交价取挂单的价格；没成交完的部分挂在订单簿上。题目的难点不在撮合循环，而在撤单、改单、拒单这些边界规则，以及让每种操作都不必遍历整本簿。
    - 标准答案的结构是：每一侧按价格排序的价位表，每个价位一个先进先出的队列，再加一张从订单 id 到订单位置的哈希表，撤单因此是 O(1)。
    - 本机实测，把 `std::map` 加 `std::list` 换成有序 `vector` 加对象池加开放寻址哈希表，簿浅时每条消息从 94 ns 降到 71 ns，簿深时从 178 ns 降到 94 ns。题目要求拒绝任何用过的 id，记住全部 id 的那张表本身又占了 20 多纳秒。
    - 最大延迟的差别比平均值大得多：不预留容量时，一次哈希表扩容让单条消息耗时 70 到 100 ms。
    - 这类面试一般先花一小时讨论设计，再花一小时写代码过测试。设计阶段要先把语义问清楚，写代码时要能讲出每个数据结构为什么这样选，以及换一种需求时要改哪里。

## 面试形式

公开的面经里，这道题通常出现在做市商或交易公司的最后一轮，形式大致相同：两个小时左右，前一半时间和面试官一起讨论需求和设计，后一半时间在给定的工程里写代码，让尽量多的现成测试通过。语言一般是 C++ 或 Java。有人测试全部通过仍然没有拿到 offer，可见评分不只看测试，代码结构、设计取舍和讨论时的表达都算在内。

各家的具体题面不公开，下面这道题是按这类题目的常见要求自拟的。它比一般的题面写得更完整，把面试时需要当场问清楚的语义都定了下来；每条规则在后面的追问部分都有对应的讨论。

## 题目

### 背景

**限价单**（limit order）是带价格上限或下限的委托：限价买单表示愿意以不高于这个价格买入，限价卖单表示愿意以不低于这个价格卖出。所有还没成交的限价单组成**订单簿**（order book），分成买盘和卖盘两侧。买盘的最高价和卖盘的最低价合称**盘口**，也叫最优价。

一笔新订单到达时，如果它和对手方的最优价交叉（买价不低于最低卖价，或卖价不高于最高买价），就立即成交。这笔新订单叫**主动方**（aggressor），被它成交掉的、原本挂在簿上的订单叫**被动方**（resting order）。没有成交完的数量留在簿上，成为新的挂单。

请实现一个这样的撮合引擎：从标准输入逐行读取消息，按顺序处理，向标准输出写出成交和拒单事件；输入结束后，再写出每个品种剩下的订单簿。

### 输入

每行一条消息，字段用空格分隔：

| 消息 | 格式 | 含义 |
|---|---|---|
| 下单 | `INSERT <id> <symbol> <BUY\|SELL> <price> <qty>` | 提交一笔限价单 |
| 改单 | `AMEND <id> <price> <qty>` | 修改一笔挂单的价格和剩余数量 |
| 撤单 | `CANCEL <id>` | 撤销一笔挂单 |

- `id` 是正整数，可以放进 64 位无符号整数。`symbol` 是由大写字母组成的非空字符串，`BUY`、`SELL` 总是拼写正确。
- `price` 和 `qty` 两个字段可能是任意记号。合法的 `price` 是正的十进制数，整数部分 1 到 12 位，小数部分最多 2 位（`100`、`100.5`、`100.25` 合法，`100.123`、`1e2`、`.5`、`0` 不合法）。合法的 `qty` 是 1 到 10⁹ 之间的整数。
- 空行忽略。不必处理其他格式错误。

### 撮合规则

1. 新订单先和对手方撮合。买单从最低的卖价开始，依次和价格不高于自己限价的卖单成交；卖单从最高的买价开始，依次和价格不低于自己限价的买单成交。
2. 同一价位上，先到达的挂单先成交（时间优先）。
3. 每次成交的数量是双方剩余数量的较小值，**成交价是挂单的价格**。
4. 一笔挂单的剩余数量变成 0 时，它离开订单簿。
5. 撮合结束后主动方还有剩余数量，就以自己的限价挂到本方的簿上，排在这个价位所有已有订单的后面。
6. 不同品种的订单互不撮合。

### 改单规则

`AMEND` 里的 `qty` 是改单后的**剩余**数量，不是订单的原始总数量。

- 价格不变、新数量不大于当前剩余数量：原地修改数量，保留时间优先。新数量等于当前剩余数量时什么也不改变。
- 改了价格，或者数量增加了：效果等同于撤掉原订单，再以同一个 id、同一方向、新价格和新数量重新下单。它会失去原来的排队位置；如果新价格和对手方交叉，它作为主动方立即成交。

### 拒单规则

按下面的顺序检查，命中第一条就输出拒单，这条消息不产生其他效果：

1. `price` 或 `qty` 不合法：`INVALID`。
2. `INSERT` 的 `id` 在本次运行中已经被一笔**成功受理**的 `INSERT` 用过，即使那笔订单已经成交或撤销：`DUPLICATE_ID`。被拒绝的 `INSERT` 不占用 id。
3. `AMEND` 或 `CANCEL` 的 `id` 当前不在簿上（从未出现、已经全部成交或已经撤销）：`UNKNOWN_ID`。

### 输出

处理每条消息时，按发生顺序输出事件：

```text
TRADE <symbol> <price> <qty> <aggressor id> <resting id>
REJECT <id> <INVALID|DUPLICATE_ID|UNKNOWN_ID>
```

价格一律输出两位小数。输入结束后，按品种名的字典序，对每个还有挂单的品种输出：

```text
BOOK <symbol>
BID <price> <total qty> <order count>     买盘的每个价位，从最高价到最低价
ASK <price> <total qty> <order count>     卖盘的每个价位，从最低价到最高价
```

`total qty` 是这个价位所有挂单剩余数量之和，`order count` 是挂单笔数。簿上没有订单的品种不输出。

### 示例

```text
INSERT 1 AAPL SELL 101 5
INSERT 2 AAPL SELL 100 5
INSERT 3 AAPL SELL 100 5
INSERT 4 AAPL SELL 102 5
INSERT 5 AAPL BUY 101 12
```

订单 5 是买单，限价 101。它先吃最低价 100 上的两笔卖单，按到达顺序先 2 后 3，各成交 5；再吃 101 上的订单 1，成交剩下的 2。102 高于它的限价，不再成交。订单 5 恰好成交完，不挂单；订单 1 剩下 3。输出：

```text
TRADE AAPL 100.00 5 5 2
TRADE AAPL 100.00 5 5 3
TRADE AAPL 101.00 2 5 1
BOOK AAPL
ASK 101.00 3 1
ASK 102.00 5 1
```

### 分阶段要求

现场的题目往往分阶段给出，后一阶段在前一阶段的代码上扩展。建议按下面的顺序实现，每一阶段都让对应的测试通过再往下走：

| 阶段 | 内容 | 用例 |
|---|---|---|
| 一 | `INSERT`、撮合、订单簿快照 | 01–06 |
| 二 | `CANCEL`、三种拒单 | 07–09、17 |
| 三 | `AMEND` | 10–16 |
| 四 | 性能：十万量级的挂单、每秒千万量级的消息，说明你的结构在哪里会成为瓶颈 | 见「实测」 |

### 测试用例

每个用例以 `=== 编号 说明` 开头，`---` 之前是输入，之后是期望的完整输出。用例文件和运行脚本可以直接复制使用。

<details markdown="1">
<summary>tests.txt（17 个用例）</summary>

```text title="tests.txt"
=== 01 不交叉的两笔订单都挂在簿上
INSERT 1 AAPL BUY 100.00 10
INSERT 2 AAPL SELL 101.00 5
---
BOOK AAPL
BID 100.00 10 1
ASK 101.00 5 1
=== 02 完全成交，成交价取挂单价，空簿不输出
INSERT 1 AAPL SELL 100.50 10
INSERT 2 AAPL BUY 101 10
---
TRADE AAPL 100.50 10 2 1
=== 03 部分成交，剩余部分挂单
INSERT 1 AAPL SELL 100 4
INSERT 2 AAPL BUY 100 10
---
TRADE AAPL 100.00 4 2 1
BOOK AAPL
BID 100.00 6 1
=== 04 价格优先、时间优先，一笔买单扫过两个价位
INSERT 1 AAPL SELL 101 5
INSERT 2 AAPL SELL 100 5
INSERT 3 AAPL SELL 100 5
INSERT 4 AAPL SELL 102 5
INSERT 5 AAPL BUY 101 12
---
TRADE AAPL 100.00 5 5 2
TRADE AAPL 100.00 5 5 3
TRADE AAPL 101.00 2 5 1
BOOK AAPL
ASK 101.00 3 1
ASK 102.00 5 1
=== 05 卖单主动成交，先吃最高买价，剩余不再交叉就挂单
INSERT 1 AAPL BUY 99 5
INSERT 2 AAPL BUY 100 5
INSERT 3 AAPL SELL 99.5 7
---
TRADE AAPL 100.00 5 3 2
BOOK AAPL
BID 99.00 5 1
ASK 99.50 2 1
=== 06 不同品种互不撮合，快照按品种名排序
INSERT 1 MSFT BUY 50 10
INSERT 2 AAPL SELL 50 10
INSERT 3 AAPL BUY 50 3
---
TRADE AAPL 50.00 3 3 2
BOOK AAPL
ASK 50.00 7 1
BOOK MSFT
BID 50.00 10 1
=== 07 撤单；重复撤单和未知 id 被拒绝
INSERT 1 AAPL BUY 100 10
INSERT 2 AAPL BUY 100 20
CANCEL 1
CANCEL 1
CANCEL 99
INSERT 3 AAPL SELL 100 5
---
REJECT 1 UNKNOWN_ID
REJECT 99 UNKNOWN_ID
TRADE AAPL 100.00 5 3 2
BOOK AAPL
BID 100.00 15 1
=== 08 已成交的订单不能撤；用过的 id 不能再用
INSERT 1 AAPL SELL 100 5
INSERT 2 AAPL BUY 100 5
CANCEL 1
CANCEL 2
INSERT 1 AAPL BUY 90 1
---
TRADE AAPL 100.00 5 2 1
REJECT 1 UNKNOWN_ID
REJECT 2 UNKNOWN_ID
REJECT 1 DUPLICATE_ID
=== 09 非法字段；被拒绝的 INSERT 不占用 id
INSERT 1 AAPL BUY 0 10
INSERT 2 AAPL BUY 100.123 10
INSERT 3 AAPL BUY 100 0
INSERT 4 AAPL BUY 100 -5
INSERT 5 AAPL BUY 1e2 5
INSERT 1 AAPL BUY 100 1
AMEND 1 100 0
---
REJECT 1 INVALID
REJECT 2 INVALID
REJECT 3 INVALID
REJECT 4 INVALID
REJECT 5 INVALID
REJECT 1 INVALID
BOOK AAPL
BID 100.00 1 1
=== 10 同价减量保留时间优先
INSERT 1 AAPL BUY 100 10
INSERT 2 AAPL BUY 100 10
AMEND 1 100 4
INSERT 3 AAPL SELL 100 6
---
TRADE AAPL 100.00 4 3 1
TRADE AAPL 100.00 2 3 2
BOOK AAPL
BID 100.00 8 1
=== 11 加量失去时间优先，排到队尾
INSERT 1 AAPL BUY 100 10
INSERT 2 AAPL BUY 100 10
AMEND 1 100 11
INSERT 3 AAPL SELL 100 12
---
TRADE AAPL 100.00 10 3 2
TRADE AAPL 100.00 2 3 1
BOOK AAPL
BID 100.00 9 1
=== 12 改价后交叉，改单的订单作为主动方立即成交
INSERT 1 AAPL SELL 101 5
INSERT 2 AAPL BUY 100 8
AMEND 2 101 8
---
TRADE AAPL 101.00 5 2 1
BOOK AAPL
BID 101.00 3 1
=== 13 AMEND 的数量是新的剩余数量：等于剩余数量时什么也不变
INSERT 1 AAPL SELL 100 10
INSERT 2 AAPL BUY 100 4
INSERT 3 AAPL SELL 100 5
AMEND 1 100 6
INSERT 4 AAPL BUY 100 7
---
TRADE AAPL 100.00 4 2 1
TRADE AAPL 100.00 6 4 1
TRADE AAPL 100.00 1 4 3
BOOK AAPL
ASK 100.00 4 1
=== 14 改未知的或已经成交的订单
AMEND 7 100 1
INSERT 1 AAPL BUY 100 5
INSERT 2 AAPL SELL 100 5
AMEND 1 100 5
AMEND 2 100 5
---
REJECT 7 UNKNOWN_ID
TRADE AAPL 100.00 5 2 1
REJECT 1 UNKNOWN_ID
REJECT 2 UNKNOWN_ID
=== 15 改价后扫过多个价位，剩余部分在新价位挂单
INSERT 1 AAPL BUY 100 3
INSERT 2 AAPL BUY 99 3
INSERT 3 AAPL BUY 98 3
INSERT 4 AAPL SELL 105 10
AMEND 4 99 10
---
TRADE AAPL 100.00 3 4 1
TRADE AAPL 99.00 3 4 2
BOOK AAPL
BID 98.00 3 1
ASK 99.00 4 1
=== 16 改单后完全成交，之后不能再撤
INSERT 1 AAPL BUY 100 5
INSERT 2 AAPL SELL 101 5
AMEND 2 100 5
CANCEL 2
---
TRADE AAPL 100.00 5 2 1
REJECT 2 UNKNOWN_ID
=== 17 撤掉队列中间的订单；价位清空后从簿中删除
INSERT 1 AAPL BUY 100 1
INSERT 2 AAPL BUY 100 2
INSERT 3 AAPL BUY 100 3
CANCEL 2
INSERT 4 AAPL BUY 99 1
CANCEL 1
CANCEL 3
---
BOOK AAPL
BID 99.00 1 1
```
</details>

<details markdown="1">
<summary>run_tests.py</summary>

```python title="run_tests.py"
# run_tests.py <可执行文件> [参数...]：逐个运行 tests.txt 里的用例，比较输出
import subprocess, sys, pathlib

text = (pathlib.Path(__file__).parent / "tests.txt").read_text()
failed = 0
for case in text.split("=== ")[1:]:
    head, body = case.split("\n", 1)
    inp, exp = body.split("---\n")
    out = subprocess.run(sys.argv[1:], input=inp, capture_output=True, text=True).stdout
    if out != exp:
        failed += 1
        print(f"FAIL {head}\n--- expected\n{exp}--- got\n{out}")
total = text.count("=== ")
print(f"{total - failed}/{total} passed")
sys.exit(1 if failed else 0)
```
</details>

```bash
clang++ -std=c++2c -O2 main.cpp -o me
python3 run_tests.py ./me          # 优化实现
python3 run_tests.py ./me --ref    # 参考实现
```

## 设计讨论

### 动手之前先问清楚的事

上面的题面已经把这些语义定了下来，现场的题面通常没有。面试官往往有意不说，看你会不会问。每一条都会改变代码：

| 问题 | 本题的规定 | 另一种常见规定 |
|---|---|---|
| 成交价取谁的价格 | 挂单的价格 | 极少有别的做法，但要说出来 |
| 改单的数量是剩余数量还是总数量 | 剩余数量 | 总数量（FIX 协议的改单就是这样） |
| 改单什么时候失去时间优先 | 改价或加量 | 有的系统任何改单都重新排队 |
| 价格的精度 | 两位小数，按整数存 | 每个品种有自己的最小变动单位（tick） |
| 订单 id 在什么范围内唯一 | 整个运行期间 | 每个客户各自唯一，或者由引擎分配 |
| 撤单消息带不带品种 | 不带 | 真实协议一般要求带 |
| 要不要输出确认、撤单回报 | 只输出成交和拒单 | 每条消息都有回报 |
| 有没有市价单、IOC 之类的订单类型 | 没有 | 见追问 25 |

问完以后把结论写成代码顶部的注释。写代码时遇到没问到的情况，先说出你的假设，再继续。

### 数据结构

一本簿需要支持的操作，以及标准答案在每个操作上的代价：

| 操作 | 怎么做 | 代价 |
|---|---|---|
| 找对手方最优价 | 有序容器的第一个元素 | O(1) |
| 成交一笔挂单 | 最优价位队列的队首 | O(1) |
| 新挂单 | 找到或新建价位，追加到队尾 | 找价位 O(log P)，P 是价位数；追加 O(1) |
| 撤单 | 哈希表按 id 找到订单，从所在价位的队列中摘掉 | O(1)，价位变空时再加 O(log P) |
| 改单（同价减量） | 哈希表找到订单，改数量 | O(1) |
| 快照 | 按价格顺序遍历价位 | O(P) |

价位的有序容器可以是红黑树（`std::map`），也可以是有序数组；同一价位内的队列要能在 O(1) 时间删除中间的元素，所以是双向链表。哈希表保存的是订单在链表里的位置，这要求这个位置在其他订单插入、删除时保持有效。下面的参考实现正好利用了标准对节点式容器的保证。

### 不变量

讨论设计时把不变量说出来，测试和调试时就有了检查的依据。这道题有五条：

1. 每条消息处理完以后，簿不交叉：最高买价严格低于最低卖价。
2. 每个价位的 `total` 等于其中所有订单剩余数量之和，`count` 等于订单笔数。
3. 簿上没有空价位，也没有剩余数量为 0 的订单。
4. 哈希表里的 id 恰好是簿上所有挂单的 id。
5. 同一价位的队列按到达顺序排列，改单失去优先级时按重新到达处理。

## 参考实现

先写一个正确、容易讲清楚的版本。面试现场这一版能过全部测试，就已经完成了大半。

```cpp title="common.hpp"
// common.hpp：两个引擎共用的类型、事件接口，以及价格和数量的解析
#pragma once
#include <charconv>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

using OrderId = std::uint64_t;
using Price = std::int64_t;  // 以 0.01 为单位：101.25 存成 10125
using Qty = std::int64_t;

enum class Side : std::uint8_t { Buy, Sell };
enum class Reject : std::uint8_t { Invalid, DuplicateId, UnknownId };

inline constexpr Qty kMaxQty = 1'000'000'000;

// 引擎通过它报告事件。回调里不能再调用引擎。
struct Sink {
    virtual void on_trade(std::string_view symbol, Price px, Qty qty, OrderId aggressor, OrderId resting) = 0;
    virtual void on_reject(OrderId id, Reject why) = 0;

protected:
    ~Sink() = default;
};

// 整数部分 1–12 位，可选小数点和 1–2 位小数，结果必须为正。不经过 double。
inline std::optional<Price> parse_price(std::string_view s) {
    Price v = 0;
    int int_digits = 0, frac_digits = -1;  // -1 表示还没遇到小数点
    for (char c : s) {
        if (c == '.') {
            if (frac_digits >= 0) return std::nullopt;
            frac_digits = 0;
            continue;
        }
        if (c < '0' || c > '9') return std::nullopt;
        v = v * 10 + (c - '0');
        if (frac_digits >= 0) {
            if (++frac_digits > 2) return std::nullopt;
        } else if (++int_digits > 12) {
            return std::nullopt;
        }
    }
    if (int_digits == 0 || frac_digits == 0) return std::nullopt;
    for (int i = frac_digits < 0 ? 0 : frac_digits; i < 2; ++i) v *= 10;
    if (v <= 0) return std::nullopt;
    return v;
}

inline std::optional<Qty> parse_qty(std::string_view s) {
    Qty v = 0;
    auto [end, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
    if (ec != std::errc{} || end != s.data() + s.size() || v <= 0 || v > kMaxQty) return std::nullopt;
    return v;
}

inline std::string format_price(Price p) {
    char frac[] = {'.', char('0' + p % 100 / 10), char('0' + p % 10), '\0'};
    return std::to_string(p / 100) + frac;
}
```

```cpp title="engine_ref.hpp"
// engine_ref.hpp：参考实现。std::map 按价格排序，每个价位一个 std::list，哈希表从 id 找到订单
#pragma once
#include "common.hpp"
#include <algorithm>
#include <functional>
#include <list>
#include <map>
#include <ostream>
#include <unordered_map>
#include <unordered_set>

class RefEngine {
public:
    explicit RefEngine(Sink& sink) : sink_(sink) {}

    void insert(OrderId id, std::string_view symbol, Side side, Price px, Qty qty) {
        if (px <= 0 || qty <= 0 || qty > kMaxQty) return sink_.on_reject(id, Reject::Invalid);
        if (!used_.insert(id).second) return sink_.on_reject(id, Reject::DuplicateId);
        auto it = books_.find(symbol);
        if (it == books_.end()) it = books_.emplace(std::string(symbol), Book{}).first;
        execute(it->first, it->second, Order{id, side, px, qty});
    }

    void cancel(OrderId id) {
        auto it = live_.find(id);
        if (it == live_.end()) return sink_.on_reject(id, Reject::UnknownId);
        remove(it);
    }

    void amend(OrderId id, Price px, Qty qty) {
        if (px <= 0 || qty <= 0 || qty > kMaxQty) return sink_.on_reject(id, Reject::Invalid);
        auto it = live_.find(id);
        if (it == live_.end()) return sink_.on_reject(id, Reject::UnknownId);
        Locator loc = it->second;
        Order& o = *loc.pos;
        if (px == o.px && qty <= o.qty) {  // 同价减量：保留时间优先
            loc.level->total -= o.qty - qty;
            o.qty = qty;
            return;
        }
        Order moved{id, o.side, px, qty};
        remove(it);
        execute(loc.symbol, *loc.book, moved);  // 改价或加量：相当于撤单后重新下单，可能立即成交
    }

    void dump(std::ostream& os) const {
        for (const auto& [sym, b] : books_) {
            if (b.bids.empty() && b.asks.empty()) continue;
            os << "BOOK " << sym << '\n';
            for (const auto& [px, l] : b.bids) os << "BID " << format_price(px) << ' ' << l.total << ' ' << l.orders.size() << '\n';
            for (const auto& [px, l] : b.asks) os << "ASK " << format_price(px) << ' ' << l.total << ' ' << l.orders.size() << '\n';
        }
    }

private:
    struct Order {
        OrderId id;
        Side side;
        Price px;
        Qty qty;  // 剩余数量
    };
    using Queue = std::list<Order>;
    struct Level {
        Queue orders;  // 先到的在前
        Qty total = 0;
    };
    struct Book {
        std::map<Price, Level, std::greater<>> bids;  // begin() 是最高买价
        std::map<Price, Level> asks;                  // begin() 是最低卖价
    };
    // std::map 和 std::list 的节点地址不随插入删除改变，可以长期保存
    struct Locator {
        std::string_view symbol;
        Book* book;
        Level* level;
        Queue::iterator pos;
    };

    // 先和对手方撮合，剩余数量挂到本方
    void execute(std::string_view sym, Book& b, Order o) {
        if (o.side == Side::Buy) {
            match(sym, b.asks, o);
            if (o.qty > 0) rest(sym, b, b.bids, o);
        } else {
            match(sym, b.bids, o);
            if (o.qty > 0) rest(sym, b, b.asks, o);
        }
    }

    template <class Levels>
    void match(std::string_view sym, Levels& opp, Order& in) {
        while (in.qty > 0 && !opp.empty()) {
            auto lvl = opp.begin();
            if (in.side == Side::Buy ? lvl->first > in.px : lvl->first < in.px) break;
            Level& l = lvl->second;
            while (in.qty > 0 && !l.orders.empty()) {
                Order& r = l.orders.front();
                Qty q = std::min(in.qty, r.qty);
                in.qty -= q;
                r.qty -= q;
                l.total -= q;
                sink_.on_trade(sym, r.px, q, in.id, r.id);  // 成交价取挂单的价格
                if (r.qty == 0) {
                    live_.erase(r.id);
                    l.orders.pop_front();
                }
            }
            if (l.orders.empty()) opp.erase(lvl);
        }
    }

    template <class Levels>
    void rest(std::string_view sym, Book& b, Levels& own, const Order& o) {
        Level& l = own[o.px];
        l.total += o.qty;
        auto pos = l.orders.insert(l.orders.end(), o);
        live_.emplace(o.id, Locator{sym, &b, &l, pos});
    }

    void remove(std::unordered_map<OrderId, Locator>::iterator it) {
        auto [sym, b, l, pos] = it->second;
        Side side = pos->side;
        Price px = pos->px;
        l->total -= pos->qty;
        l->orders.erase(pos);
        if (l->orders.empty()) {
            if (side == Side::Buy) b->bids.erase(px);
            else b->asks.erase(px);
        }
        live_.erase(it);
    }

    Sink& sink_;
    std::map<std::string, Book, std::less<>> books_;
    std::unordered_map<OrderId, Locator> live_;  // 还挂在簿上的订单
    std::unordered_set<OrderId> used_;           // 出现过的全部 id，用来拒绝重复
};
```

```cpp title="main.cpp"
// main.cpp：从标准输入读消息，把事件和最后的订单簿写到标准输出。--ref 选参考实现
#include "engine_fast.hpp"
#include "engine_ref.hpp"
#include <iostream>
#include <sstream>

struct PrintSink final : Sink {
    void on_trade(std::string_view sym, Price px, Qty qty, OrderId aggressor, OrderId resting) override {
        std::cout << "TRADE " << sym << ' ' << format_price(px) << ' ' << qty << ' ' << aggressor << ' ' << resting << '\n';
    }
    void on_reject(OrderId id, Reject why) override {
        static constexpr const char* name[] = {"INVALID", "DUPLICATE_ID", "UNKNOWN_ID"};
        std::cout << "REJECT " << id << ' ' << name[std::to_underlying(why)] << '\n';
    }
};

template <class Engine>
int run() {
    PrintSink sink;
    Engine engine(sink);
    std::string line, cmd, sym, side, px, qty;
    OrderId id;
    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        if (!(in >> cmd)) continue;  // 空行
        if (cmd == "INSERT") {
            in >> id >> sym >> side >> px >> qty;
            auto p = parse_price(px);
            auto q = parse_qty(qty);
            if (!p || !q) sink.on_reject(id, Reject::Invalid);
            else engine.insert(id, sym, side == "BUY" ? Side::Buy : Side::Sell, *p, *q);
        } else if (cmd == "AMEND") {
            in >> id >> px >> qty;
            auto p = parse_price(px);
            auto q = parse_qty(qty);
            if (!p || !q) sink.on_reject(id, Reject::Invalid);
            else engine.amend(id, *p, *q);
        } else if (cmd == "CANCEL") {
            in >> id;
            engine.cancel(id);
        }
    }
    engine.dump(std::cout);
    return 0;
}

int main(int argc, char** argv) {
    return argc > 1 && std::string_view(argv[1]) == "--ref" ? run<RefEngine>() : run<FastEngine>();
}
```

几个值得讲出来的地方：

- `Locator` 里同时保存了 `Level*` 和 `std::list` 的迭代器。`std::map` 插入元素不影响已有的迭代器和引用，删除只让被删元素的迭代器和引用失效（[[associative.reqmts.general#175]]）；`std::list` 的插入、删除也一样（[[list.modifiers#2]]、[[list.modifiers#3]]）。所以这两样东西可以一直保存到订单离开簿。换成 `std::vector` 就不行，插入可能重新分配，所有迭代器和引用都会失效（[[vector.modifiers#2]]）。
- 品种表用 `std::map<std::string, Book, std::less<>>`。透明比较器 `std::less<>` 让 `find` 可以直接接受 `std::string_view`，不必先构造一个 `std::string`。`Locator` 和成交事件里的 `symbol` 指向这个 map 的键，键的地址同样稳定。
- 改单的两条路径共用 `execute`。改价和加量就是先 `remove` 再按新参数执行一遍，主动成交、挂单、更新索引都不必另写。
- 价格从字符串直接解析成整数，不经过 `double`，输出时再格式化回去。
- `Sink` 的回调在撮合循环中间被调用，此时迭代器 `lvl` 和引用 `r` 都还在用。如果回调里再调用引擎，就可能把它们删掉（追问 13）。

## 优化实现

参考实现每挂一笔单就要为 `std::list` 节点和 `std::unordered_map` 节点各分配一次内存，红黑树的价位节点和链表节点散落在堆上，撮合时每一步都是一次指针跳转。优化版本保持规则和接口不变，只换数据结构：

| 部分 | 参考实现 | 优化实现 |
|---|---|---|
| 价位 | `std::map<Price, Level>` | 有序 `std::vector<Level>`，最优价在末尾 |
| 同价位队列 | `std::list<Order>` | 对象池里的节点，用 32 位下标串成双向链表 |
| 订单索引 | `std::unordered_map` | 开放寻址、线性探测的哈希表，删除时回移元素 |
| 用过的 id | `std::unordered_set` | 同一种开放寻址表 |
| 内存分配 | 每笔挂单两次 | 预留容量后，热路径上只在出现新价位时偶尔扩容 |

最优价放在 `vector` 末尾，是因为绝大多数操作发生在盘口附近：吃掉最优价位是 `pop_back`，在盘口附近新增或删除价位只需要移动它后面的少数几个元素。价位的查找用二分。节点用下标而不是指针互相引用，这样对象池的 `vector` 扩容时引用不会失效，节点也只有 40 字节。

<details markdown="1">
<summary>engine_fast.hpp</summary>

```cpp title="engine_fast.hpp"
// engine_fast.hpp：规则与 RefEngine 相同，数据结构换成对缓存友好、热路径上不分配内存的版本
#pragma once
#include "common.hpp"
#include <algorithm>
#include <bit>
#include <cstdint>
#include <functional>
#include <ostream>
#include <string>
#include <unordered_map>
#include <utility>
#include <vector>

// 订单 id → 32 位值的开放寻址哈希表。线性探测；删除时把后面受影响的元素往回挪，不留墓碑。
class IdMap {
public:
    explicit IdMap(std::size_t expected) {
        std::size_t cap = 16;
        while (cap < 2 * expected) cap *= 2;
        slots_.resize(cap);
        shift_ = 64 - std::countr_zero(cap);
    }

    std::uint32_t* find(OrderId id) {
        for (std::size_t i = home(id);; i = next(i)) {
            if (slots_[i].id == id) return &slots_[i].val;
            if (slots_[i].id == 0) return nullptr;
        }
    }

    // id 已经存在时什么也不做，返回 false
    bool insert(OrderId id, std::uint32_t val) {
        if (2 * (size_ + 1) > slots_.size()) grow();
        std::size_t i = home(id);
        for (; slots_[i].id != 0; i = next(i))
            if (slots_[i].id == id) return false;
        slots_[i] = {id, val};
        ++size_;
        return true;
    }

    void erase(OrderId id) {
        std::size_t i = home(id);
        while (slots_[i].id != id) i = next(i);  // 调用者保证 id 存在
        // i 空出来以后，后面同一段连续区间里的元素如果因为 i 被占才排到后面，就挪到 i
        for (std::size_t j = next(i); slots_[j].id != 0; j = next(j)) {
            std::size_t h = home(slots_[j].id);
            if (((j - h) & mask()) >= ((j - i) & mask())) {  // h 不在 (i, j] 之间
                slots_[i] = slots_[j];
                i = j;
            }
        }
        slots_[i].id = 0;
        --size_;
    }

private:
    struct Slot {
        OrderId id = 0;  // 0 表示空槽：订单 id 都是正数
        std::uint32_t val = 0;
    };
    std::size_t mask() const { return slots_.size() - 1; }
    std::size_t next(std::size_t i) const { return (i + 1) & mask(); }
    std::size_t home(OrderId id) const { return (id * 0x9E3779B97F4A7C15ull) >> shift_; }  // Fibonacci 哈希
    void grow() {
        std::vector<Slot> old(slots_.size() * 2);
        old.swap(slots_);
        --shift_;
        for (const Slot& s : old) {
            if (s.id == 0) continue;
            std::size_t i = home(s.id);
            while (slots_[i].id != 0) i = next(i);
            slots_[i] = s;
        }
    }

    std::vector<Slot> slots_;
    std::size_t size_ = 0;
    int shift_;
};

class FastEngine {
public:
    // expected_live：同时挂在簿上的订单数的估计；expected_ids：整个会话的订单数的估计
    FastEngine(Sink& sink, std::size_t expected_live = 1 << 16, std::size_t expected_ids = 1 << 20)
        : sink_(sink), live_(expected_live), used_(expected_ids) {
        nodes_.reserve(expected_live);
    }

    void insert(OrderId id, std::string_view symbol, Side side, Price px, Qty qty) {
        if (px <= 0 || qty <= 0 || qty > kMaxQty) return sink_.on_reject(id, Reject::Invalid);
        if (!used_.insert(id, 0)) return sink_.on_reject(id, Reject::DuplicateId);
        execute(book_index(symbol), id, side, px, qty);
    }

    void cancel(OrderId id) {
        std::uint32_t* n = live_.find(id);
        if (!n) return sink_.on_reject(id, Reject::UnknownId);
        remove(*n);
    }

    void amend(OrderId id, Price px, Qty qty) {
        if (px <= 0 || qty <= 0 || qty > kMaxQty) return sink_.on_reject(id, Reject::Invalid);
        std::uint32_t* n = live_.find(id);
        if (!n) return sink_.on_reject(id, Reject::UnknownId);
        Node& o = nodes_[*n];
        if (px == o.px && qty <= o.qty) {  // 同价减量：保留时间优先
            level_of(o).total -= o.qty - qty;
            o.qty = qty;
            return;
        }
        std::uint32_t b = o.book;
        Side side = o.side;
        remove(*n);
        execute(b, id, side, px, qty);  // 改价或加量：相当于撤单后重新下单，可能立即成交
    }

    void dump(std::ostream& os) const {
        std::vector<std::uint32_t> order(books_.size());
        for (std::uint32_t i = 0; i < order.size(); ++i) order[i] = i;
        std::ranges::sort(order, {}, [&](std::uint32_t i) -> const std::string& { return books_[i].name; });
        for (std::uint32_t i : order) {
            const Book& b = books_[i];
            if (b.levels[0].empty() && b.levels[1].empty()) continue;
            os << "BOOK " << b.name << '\n';
            for (const char* tag : {"BID", "ASK"}) {
                const auto& v = b.levels[tag[0] == 'A'];
                for (auto l = v.rbegin(); l != v.rend(); ++l)
                    os << tag << ' ' << format_price(l->px) << ' ' << l->total << ' ' << l->count << '\n';
            }
        }
    }

private:
    static constexpr std::uint32_t kNil = UINT32_MAX;
    struct Node {  // 40 字节
        OrderId id;
        Price px;
        Qty qty;
        std::uint32_t prev, next;  // 同一价位内的双向链表；空闲时 next 串起空闲链表
        std::uint32_t book;
        Side side;
    };
    struct Level {  // 32 字节
        Price px;
        Qty total;
        std::uint32_t head, tail, count;
    };
    struct Book {
        std::string name;
        std::vector<Level> levels[2];  // [买, 卖]，各自从差到好排列，最优价在末尾
    };

    static int idx(Side s) { return std::to_underlying(s); }
    static bool better(Side s, Price a, Price b) { return s == Side::Buy ? a > b : a < b; }

    // 返回 i，使 v[i..] 都优于 px，v[i-1]（如果存在）不优于 px。二分查找
    static std::size_t lower(const std::vector<Level>& v, Side s, Price px) {
        auto it = std::ranges::partition_point(v, [&](const Level& l) { return !better(s, l.px, px); });
        return std::size_t(it - v.begin());
    }

    Level& level_of(const Node& o) {
        auto& v = books_[o.book].levels[idx(o.side)];
        return v[lower(v, o.side, o.px) - 1];
    }

    void execute(std::uint32_t b, OrderId id, Side side, Price px, Qty qty) {
        Book& book = books_[b];
        auto& opp = book.levels[1 - idx(side)];
        while (qty > 0 && !opp.empty()) {
            Level& l = opp.back();
            if (side == Side::Buy ? l.px > px : l.px < px) break;
            while (qty > 0 && l.head != kNil) {
                std::uint32_t n = l.head;
                Node& r = nodes_[n];
                Qty q = std::min(qty, r.qty);
                qty -= q;
                r.qty -= q;
                l.total -= q;
                sink_.on_trade(book.name, l.px, q, id, r.id);
                if (r.qty == 0) {
                    live_.erase(r.id);
                    l.head = r.next;
                    if (l.head != kNil) nodes_[l.head].prev = kNil;
                    else l.tail = kNil;
                    --l.count;
                    free_node(n);
                }
            }
            if (l.head == kNil) opp.pop_back();
        }
        if (qty == 0) return;

        auto& own = book.levels[idx(side)];
        std::size_t i = lower(own, side, px);
        if (i == 0 || own[i - 1].px != px) own.insert(own.begin() + i++, Level{px, 0, kNil, kNil, 0});
        Level& l = own[i - 1];
        std::uint32_t n = alloc_node();
        nodes_[n] = Node{id, px, qty, l.tail, kNil, b, side};
        if (l.tail != kNil) nodes_[l.tail].next = n;
        else l.head = n;
        l.tail = n;
        l.total += qty;
        ++l.count;
        live_.insert(id, n);
    }

    // 把挂着的订单从簿上拿掉
    void remove(std::uint32_t n) {
        const Node& o = nodes_[n];
        auto& v = books_[o.book].levels[idx(o.side)];
        std::size_t i = lower(v, o.side, o.px) - 1;  // 挂着的订单，所在价位一定存在
        Level& l = v[i];
        (o.prev != kNil ? nodes_[o.prev].next : l.head) = o.next;
        (o.next != kNil ? nodes_[o.next].prev : l.tail) = o.prev;
        l.total -= o.qty;
        if (--l.count == 0) v.erase(v.begin() + i);
        live_.erase(o.id);
        free_node(n);
    }

    std::uint32_t alloc_node() {
        if (free_ != kNil) {
            std::uint32_t n = free_;
            free_ = nodes_[n].next;
            return n;
        }
        nodes_.emplace_back();
        return std::uint32_t(nodes_.size() - 1);
    }
    void free_node(std::uint32_t n) {
        nodes_[n].next = free_;
        free_ = n;
    }

    struct StrHash {
        using is_transparent = void;
        std::size_t operator()(std::string_view s) const noexcept { return std::hash<std::string_view>{}(s); }
    };
    std::uint32_t book_index(std::string_view sym) {
        auto it = symbols_.find(sym);
        if (it != symbols_.end()) return it->second;
        books_.push_back(Book{std::string(sym), {}});
        symbols_.emplace(std::string(sym), std::uint32_t(books_.size() - 1));
        return std::uint32_t(books_.size() - 1);
    }

    Sink& sink_;
    IdMap live_;  // 挂在簿上的订单 → 节点下标
    IdMap used_;  // 出现过的全部 id（值不用），用来拒绝重复
    std::vector<Node> nodes_;
    std::uint32_t free_ = kNil;
    std::vector<Book> books_;
    std::unordered_map<std::string, std::uint32_t, StrHash, std::equal_to<>> symbols_;
};
```
</details>

`IdMap::erase` 用的是线性探测表的回移删除：删掉位置 `i` 的元素后，向后扫描同一段连续占用的槽位，如果某个元素的理想位置 `h` 不在 `(i, j]` 之间（按环形计算），说明它是因为 `i` 被占才排到后面的，就把它挪回 `i`，再以它原来的位置作为新的空位继续扫描。这样表里不需要墓碑，查找时遇到空槽就可以停。

### 怎样确认优化版本是对的

优化版本的代码更长，下标和链表指针更容易写错。除了 17 个用例，还要和参考实现做**差分测试**：随机生成大量消息序列，分别交给两个引擎，要求事件序列（取哈希）和最终的订单簿完全一致。生成器故意把价格限制在中间价附近 3 档以内，让成交、扫多档和改单频繁发生，并混入重复 id 和数量为 0 的消息。

<details markdown="1">
<summary>bench.cpp（差分测试与计时）</summary>

```cpp title="bench.cpp"
// bench.cpp：生成随机消息流，先做差分测试（两个引擎的事件和最终订单簿必须一致），再分别计时
#include "engine_fast.hpp"
#include "engine_ref.hpp"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <random>
#include <sstream>
#include <vector>

#ifndef NBIG
#define NBIG 10000000
#endif

struct Msg {
    enum Kind : std::uint8_t { Insert, Amend, Cancel } kind;
    Side side;
    std::uint8_t sym;
    OrderId id;
    Price px;
    Qty qty;
};

const std::string kSymbols[] = {"S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7"};

// 差分测试用的消息流。spread：被动单离中间价最多几档；fuzz：混入非法数量和重复 id
std::vector<Msg> generate(std::size_t n, std::uint64_t seed, int spread, bool fuzz) {
    std::mt19937_64 rng(seed);
    auto pick = [&](std::uint64_t k) { return rng() % k; };
    Price mid[8];
    std::ranges::fill(mid, 10'000);
    std::vector<OrderId> cand;  // 可能还挂着的订单（生成器不知道哪些已经成交）
    std::vector<Side> side_of(1);
    std::vector<std::uint8_t> sym_of(1);
    std::vector<Msg> out;
    out.reserve(n);
    OrderId next = 1;
    for (std::size_t i = 0; i < n; ++i) {
        auto s = std::uint8_t(pick(8));
        if (pick(100) < 5) mid[s] += pick(2) ? 1 : -1;
        int r = int(pick(100));
        if (r < 55 || cand.empty()) {
            Side side = pick(2) ? Side::Buy : Side::Sell;
            Price off = r < 45 ? Price(1 + pick(spread)) : -Price(pick(4));  // 后 10% 越过中间价，多半会成交
            Price px = side == Side::Buy ? mid[s] - off : mid[s] + off;
            bool dup = fuzz && next > 1 && pick(50) == 0;
            OrderId id = dup ? 1 + pick(next - 1) : next++;
            Qty qty = Qty(1 + pick(100));
            if (fuzz && pick(50) == 0) qty = 0;
            out.push_back({Msg::Insert, side, s, id, px, qty});
            if (!dup) {
                cand.push_back(id);
                side_of.push_back(side);
                sym_of.push_back(s);
            }
        } else {
            std::size_t k = pick(cand.size());
            OrderId id = cand[k];
            if (r < 95) {
                out.push_back({Msg::Cancel, Side::Buy, 0, id, 0, 0});
                cand[k] = cand.back();
                cand.pop_back();
            } else {
                Side side = side_of[id];
                Price off = Price(pick(spread + 1)) - 1;
                Price px = side == Side::Buy ? mid[sym_of[id]] - off : mid[sym_of[id]] + off;
                out.push_back({Msg::Amend, side, 0, id, px, Qty(1 + pick(100))});
            }
        }
    }
    return out;
}

struct HashSink final : Sink {
    std::uint64_t h = 1469598103934665603ull, trades = 0, rejects = 0;
    void mix(std::uint64_t v) { h = (h ^ v) * 1099511628211ull; }
    void on_trade(std::string_view sym, Price px, Qty qty, OrderId a, OrderId r) override {
        ++trades;
        mix(std::hash<std::string_view>{}(sym)), mix(std::uint64_t(px)), mix(std::uint64_t(qty)), mix(a), mix(r);
    }
    void on_reject(OrderId id, Reject why) override {
        ++rejects;
        mix(id), mix(std::to_underlying(why) + 7);
    }
};

template <class Engine>
void apply(Engine& e, const Msg& m) {
    switch (m.kind) {
    case Msg::Insert: e.insert(m.id, kSymbols[m.sym], m.side, m.px, m.qty); break;
    case Msg::Amend: e.amend(m.id, m.px, m.qty); break;
    case Msg::Cancel: e.cancel(m.id); break;
    }
}

// 计时用的消息流：生成时用 RefEngine 跟踪哪些订单还挂着，撤单和改单只针对挂着的订单，
// 七成落在最近挂出的 32 笔上（报价不断刷新）。簿上的订单数稳定在 target 附近。
struct LiveTracker final : Sink {
    std::vector<Qty> rem;          // 每个 id 的剩余数量
    std::vector<OrderId> filled;   // 本条消息里被吃光的挂单
    void on_trade(std::string_view, Price, Qty q, OrderId a, OrderId r) override {
        rem[a] -= q;
        if ((rem[r] -= q) == 0) filled.push_back(r);
    }
    void on_reject(OrderId, Reject) override {}
};

std::vector<Msg> market(std::size_t n, std::uint64_t seed, std::size_t target) {
    std::mt19937_64 rng(seed);
    auto pick = [&](std::uint64_t k) { return rng() % k; };
    LiveTracker t;
    t.rem.assign(n + 1, 0);
    RefEngine ref(t);
    Price mid[8];
    std::ranges::fill(mid, 10'000);
    std::vector<OrderId> live;
    std::vector<std::uint32_t> pos(n + 1);
    std::vector<Side> side_of(n + 1);
    std::vector<std::uint8_t> sym_of(n + 1);
    auto add = [&](OrderId id) { pos[id] = std::uint32_t(live.size()); live.push_back(id); };
    auto drop = [&](OrderId id) {
        std::uint32_t k = pos[id];
        live[k] = live.back();
        pos[live[k]] = k;
        live.pop_back();
    };
    std::vector<Msg> out;
    out.reserve(n);
    OrderId next = 1;
    for (std::size_t i = 0; i < n; ++i) {
        auto s = std::uint8_t(pick(8));
        if (pick(100) < 5) mid[s] += pick(2) ? 1 : -1;
        bool remove = !live.empty() && double(pick(1000)) < 500.0 * double(live.size()) / double(target);
        Msg m;
        if (!remove) {
            Side side = pick(2) ? Side::Buy : Side::Sell;
            Price off = pick(100) < 85 ? Price(1 + pick(20)) : -Price(pick(4));  // 15% 越过中间价，多半会成交
            OrderId id = next++;
            m = {Msg::Insert, side, s, id, side == Side::Buy ? mid[s] - off : mid[s] + off, Qty(1 + pick(100))};
            side_of[id] = side;
            sym_of[id] = s;
            t.rem[id] = m.qty;
        } else {
            std::size_t k = pick(10) < 7 && live.size() > 32 ? live.size() - 1 - pick(32) : pick(live.size());
            OrderId id = live[k];
            if (pick(10) < 9) {
                m = {Msg::Cancel, Side::Buy, 0, id, 0, 0};
                drop(id);
            } else {
                Side side = side_of[id];
                Price off = Price(pick(22)) - 1;
                Price mp = mid[sym_of[id]];
                m = {Msg::Amend, side, 0, id, side == Side::Buy ? mp - off : mp + off, Qty(1 + pick(100))};
                t.rem[id] = m.qty;
                drop(id);
            }
        }
        out.push_back(m);
        apply(ref, m);
        for (OrderId r : t.filled) drop(r);
        t.filled.clear();
        if (m.kind != Msg::Cancel && t.rem[m.id] > 0) add(m.id);
    }
    return out;
}

template <class Engine, class... A>
std::pair<std::uint64_t, std::string> replay(const std::vector<Msg>& msgs, A... args) {
    HashSink sink;
    Engine e(sink, args...);
    for (const Msg& m : msgs) apply(e, m);
    std::ostringstream os;
    e.dump(os);
    return {sink.h, os.str()};
}

using Clock = std::chrono::steady_clock;

template <class Engine, class... A>
double throughput(const std::vector<Msg>& msgs, A... args) {
    double best = 1e30;
    for (int rep = 0; rep < 5; ++rep) {
        HashSink sink;
        Engine e(sink, args...);
        auto t0 = Clock::now();
        for (const Msg& m : msgs) apply(e, m);
        auto t1 = Clock::now();
        best = std::min(best, std::chrono::duration<double, std::nano>(t1 - t0).count() / double(msgs.size()));
    }
    return best;
}

template <class Engine, class... A>
void latency(const char* name, const std::vector<Msg>& msgs, A... args) {
    HashSink sink;
    Engine e(sink, args...);
    std::vector<std::int64_t> ns(msgs.size());
    for (std::size_t i = 0; i < msgs.size(); ++i) {
        auto t0 = Clock::now();
        apply(e, msgs[i]);
        auto t1 = Clock::now();
        ns[i] = std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count();
    }
    std::ranges::sort(ns);
    auto q = [&](double p) { return ns[std::size_t(p * double(ns.size() - 1))]; };
    std::printf("%-23s p50 %5lld  p99 %6lld  p99.9 %7lld  max %9lld ns\n", name, (long long)q(0.5), (long long)q(0.99),
                (long long)q(0.999), (long long)ns.back());
}

int main() {
    // 1. 差分测试：很多小的随机序列，价格范围窄，成交、改单、重复 id、非法数量都很频繁
    for (std::uint64_t seed = 1; seed <= 2000; ++seed) {
        auto msgs = generate(3000, seed, 3, true);
        if (replay<RefEngine>(msgs) != replay<FastEngine>(msgs, std::size_t(16), std::size_t(16))) {
            std::printf("mismatch at seed %llu\n", (unsigned long long)seed);
            return 1;
        }
    }
    std::puts("differential: 2000 seeds x 3000 messages agree");

    // 2. 计时：簿上约 8 千笔订单（每个品种 1 千笔）和约 80 万笔订单两种深度
    const std::size_t n = NBIG;
    for (std::size_t target : {std::size_t(8'000), std::size_t(800'000)}) {
        auto msgs = market(n, 42, target);
        HashSink sink;
        FastEngine e(sink);
        for (const Msg& m : msgs) apply(e, m);
        std::ostringstream os;
        e.dump(os);
        std::istringstream in(os.str());
        std::string tag, px;
        long long q, c, orders = 0, levels = 0;
        while (in >> tag >> px)
            if (tag != "BOOK") in >> q >> c, orders += c, ++levels;
        std::printf("\ntarget %zu: %zu msgs, %llu trades, %llu rejects; at end %lld orders on %lld levels\n", target, n,
                    (unsigned long long)sink.trades, (unsigned long long)sink.rejects, orders, levels);
        if (replay<RefEngine>(msgs) != replay<FastEngine>(msgs)) return std::puts("mismatch on big run"), 1;
        std::printf("RefEngine               %6.1f ns/msg\n", throughput<RefEngine>(msgs));
        std::printf("FastEngine              %6.1f ns/msg\n", throughput<FastEngine>(msgs, target, n));
        std::printf("FastEngine (no reserve) %6.1f ns/msg\n", throughput<FastEngine>(msgs, std::size_t(16), std::size_t(16)));
        latency<RefEngine>("RefEngine", msgs);
        latency<FastEngine>("FastEngine", msgs, target, n);
        latency<FastEngine>("FastEngine (no reserve)", msgs, std::size_t(16), std::size_t(16));
    }
}
```
</details>

```bash
clang++ -std=c++2c -O1 -fsanitize=address,undefined -DNBIG=200000 bench.cpp -o bench_asan && ./bench_asan
clang++ -std=c++2c -O2 -DNDEBUG bench.cpp -o bench && ./bench
```

两个引擎在 2000 个随机种子、每个 3000 条消息上的输出完全一致，在 AddressSanitizer 和 UndefinedBehaviorSanitizer 下也没有报告。

## 实测

### 测量方法

机器是 Apple M2 Pro，macOS，Homebrew Clang 23 + libc++，`-std=c++2c -O2`。计时用的消息流在内存里预先生成，不包括解析文本和输出，事件交给一个只计算哈希的 `Sink`：

- 8 个品种，中间价各自随机游走；
- 下单时 85% 落在中间价外 1 到 20 档（被动单），15% 越过中间价 0 到 3 档，多半会立即成交；
- 生成时用参考实现跟踪哪些订单还挂着，撤单和改单只针对挂着的订单，其中七成落在候选列表末尾的 32 笔上，它们多数是最近挂出的，模拟报价不断刷新；簿上的订单数按目标值调节；
- 每种深度 1000 万条消息。浅簿约有 7 千笔挂单、636 个价位，消息里 558 万笔下单、397 万笔撤单、44 万笔改单；深簿约有 40 万笔挂单、2668 个价位，消息里 764 万笔下单、213 万笔撤单、24 万笔改单。

吞吐取 5 次重复中最快的一次，整个程序跑 3 遍，表中是 3 遍的中位数。

### 吞吐

| 每条消息的平均耗时 | 浅簿（约 7 千笔挂单） | 深簿（约 40 万笔挂单） |
|---|---|---|
| 参考实现 | 94 ns | 178 ns |
| 优化实现 | 71 ns | 94 ns |
| 优化实现，不检查重复 id | 49 ns | 72 ns |
| 优化实现，要求 id 递增（`id <= last` 即重复） | 50 ns | 72 ns |

有三点值得注意。

第一，簿浅的时候，换数据结构只快了约四分之一。7 千笔订单的全部数据放得进 L2 缓存（本机 16 MiB，见 [[perf/memory-hierarchy|内存层次]]），红黑树和链表的指针跳转大多命中缓存，代价不算高。簿深的时候，参考实现里挂单相关的链表节点和哈希表节点散落在几十 MB 的堆上，优化实现的节点池约 16 MB 且连续，差距就拉大到接近两倍。

第二，「拒绝任何用过的 id」这条需求本身很贵。浅簿时挂单只有几千笔，但整个运行期间用过的 id 有五百多万个，判重的表要容纳全部这些 id，远远超出缓存，每次下单都要付一次几乎必然的缓存未命中。去掉这条检查，浅簿时从 71 ns 降到 49 ns，和换数据结构带来的收益相当。如果协议规定 id 递增，判重只需要和上一个 id 比较，效果与不检查相同。这是追问 5 的实测依据。

第三，剩下的 49 ns 里，用 `sample` 采样看，按品种名查哈希表（计算字符串哈希、比较字符串）约占 16%。真实系统在网关处就把品种名换成整数编号（追问 19）。

### 延迟分布

吞吐是平均值，交易系统更在意尾部延迟。下面逐条消息计时。本机 `steady_clock` 的步长是 41 ns，一次 `now()` 本身要十几纳秒（见 [[perf/measuring|测量]]），所以中位数一栏只有 42、83、125 这几个值，只能看量级。最大值在三遍之间波动很大，给出的是范围。

| 浅簿 | p50 | p99 | 最大值 |
|---|---|---|---|
| 参考实现 | 83 ns | 209–250 ns | 12–21 ms |
| 优化实现，预留容量 | 84 ns | 208–250 ns | 0.14–2.9 ms |
| 优化实现，不预留容量 | 83 ns | 167–209 ns | 72–98 ms |
| 优化实现，要求 id 递增，预留容量 | 42 ns | 125 ns | 0.02–0.1 ms |

不预留容量时，判重表随着 id 增多不断翻倍，最后一次扩容要把几百万个元素重新散列到几百 MB 的新表里，这一条消息就要等将近 100 ms。参考实现里 `std::unordered_set` 和 `std::unordered_map` 的扩容同样造成停顿，浅簿时 12–21 ms，深簿时 25–34 ms。对一个撮合引擎来说，这样的停顿比平均慢几纳秒严重得多，所以容量要在开盘前一次性预留，扩容不能发生在交易时段。

预留容量后，优化实现的最大值仍有毫秒级。我们没有逐一查明原因；浅簿时去掉判重表（要求 id 递增），最大值降到 0.1 ms 以内，可见和那张几百 MB 的大表有关，一个可能的原因是第一次访问它的各个内存页时产生的缺页。

## 口头追问

下面的问题按主题分组。设计讨论阶段和写完代码之后都可能被问到，回答时先给结论，再说理由和代价。

### 一、需求与语义

#### 1. 成交价为什么取挂单的价格？

挂单是先到的一方，它公开报出了这个价格，后来的订单接受这个价格成交。如果取主动方的价格，主动方就有动机报一个夸张的价格来扫单，挂单方也会拿到比自己报价更好的价格，这在价格发现上没有意义。顺带的结果是：一笔买单扫过多个价位时，各笔成交的价格不同，而且都不高于它的限价。

#### 2. 改单的数量为什么定义成剩余数量？定义成总数量会怎样？

剩余数量的语义最直接，但有一个竞态：客户发出改单时，看到的剩余数量可能已经过时，中间又成交了一部分，按剩余数量改单可能让他实际买卖的总量超过本意。按总数量定义（FIX 协议的改单就是这样）可以避免这个问题：新剩余数量等于新总数量减去已成交数量，结果小于等于 0 时相当于撤单。代价是引擎要记录每笔订单的已成交数量。面试时说出这个竞态，比选哪一种更重要。

#### 3. 为什么改价或加量要失去时间优先，减量却不用？

时间优先是对先挂单、先承担风险的奖励。如果加量不重新排队，一个人可以先挂 1 手占住队首，再改成 1000 手，绕过排在后面的所有人。减量只会减少自己的成交机会，不损害别人，所以可以保留位置。改价意味着到了一个新的价位，在那里本来就没有排队位置。

#### 4. 价格为什么不用 `double`？

二进制浮点数不能精确表示大多数十进制小数，`0.1 + 0.2 != 0.3`。价格要作为有序容器的键、要判断相等（两笔订单是否在同一价位）、要逐笔加减，误差会让同一个价格分到两个价位上。所以价格用整数表示，单位是最小价格变动单位（tick），解析时直接从字符串得到整数。真实系统里每个品种的 tick 不同，有时还随价格区间变化，下单时要检查价格是不是 tick 的整数倍。

#### 5. 订单 id 唯一性的范围由谁决定？代价是什么？

本题要求整个运行期间都唯一，引擎就必须记住所有用过的 id，内存随消息数线性增长，实测里这张表让每条消息多花 20 多纳秒，扩容时还会造成长时间停顿。真实系统一般有三种做法：客户的 id 只要求在同一个连接或同一个交易日内唯一，按日清空；协议要求 id 递增，判重只比较一次；或者由引擎给每笔订单分配自己的内部 id，客户的 id 只用来对账。面试时可以先按题面实现，再指出这一点。

#### 6. 下单成功、部分成交、全部成交、撤单成功，客户怎么知道？

本题只输出成交和拒单，真实系统对每条消息都有回报：受理确认、每次成交的回报（带剩余数量）、撤单和改单确认。追加这些事件只需要在 `insert`、`cancel`、`amend` 的各个出口调用新的回调，数据结构不变。要注意事件的顺序，例如主动单的受理确认应该在它引起的成交回报之前。

### 二、数据结构

#### 7. 为什么不用 `std::priority_queue`？

堆能快速取出最优价，但不能删除中间的元素，撤单就做不到。常见的变通是惰性删除：撤单时只做标记，等它浮到堆顶时再丢弃。这样被撤的订单会一直占着内存，堆顶附近可能堆满已撤的订单，取最优价变成摊还而不是严格的 O(1)；而真实市场里撤单数量远多于成交，这个代价很实际。另外同价位的时间优先需要把到达序号也编进比较键里。

#### 8. 撤单怎么做到 O(1)？哪些位置可以长期保存？

用哈希表从 id 直接找到订单所在的位置，再从双向链表中摘掉。关键是保存的位置在其他操作之后仍然有效。`std::map`、`std::list` 的插入不影响已有的迭代器和引用，删除只影响被删元素；`std::unordered_map` 扩容会让迭代器失效，但元素的指针和引用不变（[[unord.req.general#9]]）；`std::vector` 一旦重新分配，所有引用都失效。优化实现改用下标，下标在 `vector` 扩容后依然有效。

#### 9. 如果价格范围有界，还能更快吗？

可以用以 tick 为下标的数组代替有序容器，每个元素是一个价位，再维护最优买价和最优卖价的下标。新挂单、撤单定位价位都是 O(1)。代价有两个：数组大小正比于价格范围，几千个品种每个开一个大数组会占很多内存；一个价位被吃空以后，要向差的方向扫描找到下一个非空价位，簿很稀疏时扫描可能很长，可以用一个位图加速。常见的折中是只为盘口附近的一段价格开数组，远离盘口的价位放进有序容器。

#### 10. 优化实现为什么把最优价放在 `vector` 的末尾？

在有序数组中间插入或删除，要移动它后面的所有元素。绝大多数操作发生在盘口附近，把盘口放在末尾，需要移动的就只有比它更优的少数几个价位；吃掉最优价位是 `pop_back`，不移动任何元素。如果把最优价放在开头，每次在盘口插入价位都要移动整个数组。这个选择依赖于操作集中在盘口附近，如果簿很深而撤单均匀分布在各个价位，有序数组的插入删除就会变成 O(P)。

#### 11. `std::list` 慢在哪里？

每个节点单独分配内存，本机一次小块 `malloc` 加 `free` 约 20 ns（见 [[perf/allocation|内存分配]]）；节点散落在堆上，遍历一个价位的队列每一步都可能缓存未命中；每个节点除了数据还有两个指针和分配器的开销。对象池把节点放在一个连续的 `vector` 里，释放的节点串成空闲链表，分配和释放都只是改一个下标。

#### 12. 节点之间为什么用 32 位下标而不是指针？

下标只有指针的一半大，节点更小，一个缓存行放得下更多节点。对象池的 `vector` 扩容时会搬到新地址，指针会失效，下标不会。下标还可以直接写进快照文件，恢复时不需要重定位。32 位下标意味着同时挂着的订单不能超过约 40 亿笔，这对一个品种组来说足够。

### 三、正确性

#### 13. 如果在成交回调里调用 `cancel` 会怎样？

撮合循环正拿着当前价位的迭代器和当前挂单的引用。回调里如果撤掉的正是这笔挂单或这个价位的最后一笔订单，循环回来时就在使用已经销毁的对象，是未定义行为。可选的处理办法有三种：明确规定回调不能重入，并在调试版本里用一个标志检查；把事件先放进队列，整条消息处理完再统一派发；或者让外部的所有请求都变成消息，排队按顺序处理，回调里只能发消息。真实的撮合引擎一般是最后一种。

#### 14. 怎么测试？

四层。第一层是按规则逐条写的用例，像上面的 17 个，每条规则至少有一个刚好触发和刚好不触发的例子。第二层是不变量检查：调试版本里每条消息处理完都检查前面列出的五条不变量。第三层是差分测试：用一个简单得不会错的实现（甚至可以是每次线性扫描所有订单的版本）作为参照，在大量随机输入上比较输出。第四层是 sanitizer：ASan 抓越界和释放后使用，UBSan 抓溢出。见 [[toolchain/testing|测试、sanitizer 与模糊测试]]。

#### 15. 有哪些容易漏掉的边界情况？

一笔订单扫穿多个价位；恰好全部成交时既不能挂单，也不能在索引里留下记录；价位被吃空或撤空以后要从簿中删除，否则快照会输出数量为 0 的价位，最优价也会出错；改单改到和对手方交叉；改单后全部成交，之后再撤单应该返回未知 id；被拒绝的下单不能占用 id；同一个价位上撤掉队列中间的订单。

#### 16. 数量和金额会溢出吗？

单笔数量最多 10⁹，一个价位的总量即使有一百万笔订单也只有 10¹⁵，放得进 `int64_t`。但如果要计算成交金额，价格最大是 10¹⁴（以分为单位），乘以 10⁹ 的数量就超出了 `int64_t` 的范围，有符号整数溢出是未定义行为。要么限制价格和数量的范围，要么用 128 位整数或带溢出检查的乘法（`__builtin_mul_overflow`）。

### 四、性能

#### 17. 热路径上哪里会分配内存？怎么消掉？

参考实现里，新价位分配一个 `std::map` 节点，每笔挂单分配一个 `std::list` 节点和一个 `std::unordered_map` 节点，新 id 还要分配一个 `std::unordered_set` 节点，哈希表扩容时再分配整张新表。优化实现用对象池和预留容量的开放寻址表把这些都去掉了，只剩价位 `vector` 偶尔扩容。实测表明，平均耗时的差别不算大，最大延迟的差别在两个数量级以上，所以要在开盘前预留好容量，并监控是否接近上限。

#### 18. 你的基准测了什么，没测什么？

测的是引擎本身处理预先生成的消息的吞吐和单条延迟，不包括解析、网络和输出。没测的东西都可能比引擎更重要：真实行情的分布（随机生成的消息让分支预测器很难猜，真实流量往往更有规律）、端到端延迟、多个品种共享缓存时的互相干扰。可信的做法是录下真实的消息流回放。单条延迟受计时器步长限制，本机只能看到 41 ns 的整数倍。

#### 19. 品种名字符串怎么处理？

本题的接口每次都传字符串，引擎要计算哈希、比较字符串，采样显示这占了约 16% 的时间。真实系统在客户连接或订阅时就把品种名映射成整数编号，引擎内部只用编号，簿可以直接按编号放在数组里。输出时再查表换回名字。

#### 20. 怎么利用多核？

不同品种的簿互不影响，可以按品种分片：每个线程负责一组品种，独占这些簿，不需要任何锁。网关线程按品种把消息分发到各个撮合线程的单生产者单消费者队列。队列的读写下标要放在不同的缓存行上，否则会产生伪共享（见 [[perf/false-sharing|伪共享]]）。本题的 `CANCEL` 和 `AMEND` 不带品种，分片以后网关就不知道该发给哪个线程，需要一张全局的 id 到品种的表，这也是真实协议要求撤单带上品种的原因之一。同一个簿不应该由多个线程同时撮合，撮合顺序本身就是规则的一部分。

#### 21. 日志和成交回报放在哪个线程？

不放在撮合线程。撮合线程只把事件写进一个预先分配的环形缓冲区，由另一个线程负责格式化、写日志和发送。格式化字符串、系统调用和网络发送的耗时都远大于撮合本身，也不可预测。

#### 22. `Sink` 用虚函数有什么代价？

每次成交一次间接调用。调用目标总是同一个，分支预测器很容易猜中，代价一般是几纳秒以内，我们没有单独测量。如果要去掉，可以把 `Sink` 作为模板参数，编译器就能内联回调。代价是引擎的代码要放进头文件，每种 `Sink` 实例化一份。

### 五、真实世界

#### 23. 进程崩溃以后怎么恢复？

把撮合引擎写成确定性的：同样的输入序列一定产生同样的输出。然后在消息进入引擎之前，给它编上序号并写入持久化的日志。崩溃后从最近一次快照加载簿，再回放快照之后的日志，就能恢复到崩溃前的状态；主备切换也可以靠备机实时回放同一个输入流。确定性要求引擎不读系统时间（时间戳由网关写进消息），输出不依赖哈希表的遍历顺序（本题的快照按品种名排序就是为此），也不能读未初始化的内存。

#### 24. 时间优先的时间由谁决定？

由引擎决定，具体是消息进入引擎、被编上序号的先后顺序，不是客户端在消息里写的时间戳，也不是网关收到的时间。客户端的时钟不可信，多个网关之间的时钟也不完全一致。这也意味着公平性要在网关这一层保证，例如各个连接的消息按到达顺序进入同一个序列。

#### 25. 还有哪些订单类型？各自要改哪里？

市价单没有价格，撮合到对手方没有订单或者数量用完为止，剩余部分一般撤销，很多交易所会给它一个保护价，防止扫到离谱的价位。IOC（立即成交否则撤销）撮合完不挂单。FOK（全部成交否则撤销）要先检查对手方在限价以内的总量够不够，这时每个价位的 `total` 就派上了用场，不够就整笔拒绝，不能先成交一部分。Post-only 只做挂单方，如果会立即成交就拒绝或调价。冰山单只显示一部分数量，显示部分成交完后从隐藏部分补充，补充的部分重新排到队尾。止损单在最新成交价触及触发价时才变成普通订单，需要另一本按触发价排序的簿。

#### 26. 同一个交易者的买单和卖单碰上了怎么办？

这叫自成交，很多市场禁止或要求避免，因为它可能被用来制造虚假成交量。处理办法叫自成交保护：订单需要带上所属的账户或交易者标识，撮合时发现对手方属于同一方，就按规则撤掉新单、撤掉旧单、两者都撤，或者把两边的数量相互抵减。这需要在撮合循环里多一次比较，规则的选择属于业务需求，要问清楚。

#### 27. 开盘集合竞价怎么撮合？

集合竞价期间订单只挂不成交。竞价结束时选一个统一的成交价，让在这个价格上能成交的数量最大；有多个价格并列时，再按剩余不平衡量最小、离参考价最近之类的规则取舍。算法是：在所有出现过的价位上，累计出不低于每个价格的买单总量和不高于每个价格的卖单总量，两者较小值就是这个价格上的成交量，扫一遍价位即可。然后所有可成交的订单都以这个价格成交，仍然按价格优先、时间优先分配。

#### 28. 做市商自己不运营交易所，为什么要考撮合引擎？

做市商的系统里到处都是订单簿：从交易所的逐笔行情（每笔订单的新增、修改、删除）重建出完整的簿，数据结构和本题几乎一样，只是不需要撮合，而且要处理行情丢包和按序号补齐；回测和模拟交易要模拟自己的订单在交易所里怎样排队、怎样成交，这就是一个撮合引擎；估计自己的订单在队列中的位置，直接决定报价策略。这道题考的是同时把数据结构、边界规则和性能讲清楚的能力。

#### 29. 风控检查放在哪里？

放在订单进入撮合引擎之前，通常在网关或单独的风控模块：价格是否偏离参考价太远（价格带），数量是否超过上限（防止输错数量的胖手指），账户的持仓和资金是否足够，消息频率是否超限，以及一键停止某个账户全部交易的开关。撮合引擎内部也会有最后一道检查，例如成交价不能超出当日涨跌停范围。

#### 30. 所有市场都按时间优先分配吗？

不是。部分期货品种用按比例分配：同一价位上，成交数量按各笔挂单的数量比例分给所有挂单，有的再给最先到达的订单一个优先份额。这时同价位的队列不再只需要队首，撮合时要遍历整个价位并处理取整产生的零头，`total` 字段变成必需的。题目没说时可以主动提出这一点，说明你的结构在哪里要改。

## 两个小时怎么安排

| 时间 | 做什么 |
|---|---|
| 0–10 分钟 | 复述题目，问清上面那张表里的语义，把结论写成注释 |
| 10–30 分钟 | 画出数据结构，逐个操作说复杂度，说出不变量 |
| 30–50 分钟 | 走一遍边界情况，说出测试计划，约定接口 |
| 50–60 分钟 | 讨论性能目标：消息量、挂单量、延迟要求，哪里会先成为瓶颈 |
| 60–90 分钟 | 写参考实现，先让阶段一、二的测试通过 |
| 90–110 分钟 | 加改单，补边界情况，跑全部测试 |
| 110–120 分钟 | 讲如果还有时间会怎样优化，以及改动的风险 |

写代码阶段先求正确再求快。一个能过全部测试、结构清楚的参考实现，加上对优化方向的清楚说明，通常比一个写到一半的优化实现更有说服力。卡住时说出你在检查什么，面试官往往会给提示。

## 小结

| 方面 | 要点 |
|---|---|
| 规则 | 价格优先、时间优先；成交价取挂单价；剩余数量挂单；改价或加量失去优先级 |
| 结构 | 有序价位表 + 每价位一个 FIFO 队列 + id 到位置的哈希表 |
| 正确性 | 保存的位置必须在其他操作后仍有效；回调不能重入；五条不变量；差分测试 |
| 性能 | 簿浅时缓存能掩盖指针跳转，簿深时连续存储快近一倍；记住全部 id 的需求本身就很贵；预留容量，避免扩容停顿 |
| 讨论 | 先问语义；每个选择说出代价；能说清换一种需求时改哪里 |
