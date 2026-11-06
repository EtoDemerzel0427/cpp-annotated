---
title: 撮合引擎
summary: 交易公司终面常见的一道题：实现支持限价单、撤单、按总数量改单和多品种的撮合引擎。本页按模拟面试的顺序，从一笔订单怎样成交讲起，先写 STL 基线，再逐步换成对象池、开放寻址哈希表和有序数组，并说明每一步的前提和怎样确认行为没变。附录给出完整 C++20 代码、三方差分测试、22 个协议用例、计时程序与实测数据，以及多线程系统的结构。
status: draft
order: 10
related: perf/measuring, perf/memory-hierarchy, perf/choosing-containers, perf/allocation, perf/false-sharing, toolchain/testing, topics/concurrency-in-practice, list.ops, unord.req.general, associative.reqmts.general
tags: 撮合引擎, 订单簿, 面试, 哈希表, 延迟, 实战
updated: 2026-11-05
---

!!! tldr
    - 价格优先、时间优先，成交价取被动挂单的价格；新单先撮合，GTC 余量挂单，IOC 余量取消。
    - 改单传目标总量，新剩余量等于目标总量减累计成交量；同价减量保留位置，加量去队尾，改价重新撮合。主动方成交一部分后再挂单，也要带着累计成交量。
    - 先写 `map + list + unordered_map` 的 STL 版，再依次换掉订单节点、id 索引和价位表；多品种由外层路由到各自的订单簿，单簿的撮合逻辑不变。
    - 本机实测（Apple M2 Pro，1000 万条消息）：每条消息从 STL 版的 150 ns 降到 67 ns（簿浅）、371 ns 降到 109 ns（簿深）；「整个会话里 id 不能重复」这条需求本身约占 14–25 ns，改成要求 id 递增就省掉了；不预留容量时，一次扩容让单条消息卡住 70–98 ms。
    - 附录的三种实现通过同一组确定性用例、10 万条三方随机差分和 22 个协议用例，全部在 ASan/UBSan 下运行。

面试官让你写撮合引擎，难点往往不在比较买价和卖价，而在每次成交、撤单、改单之后，能否把订单、价位和索引一起维护正确。写出 `map + list + unordered_map` 只是开始，还要解释为什么选它们，哪里可能慢，换掉之后怎样确认没有改变业务规则。

本页先看一笔订单怎样成交，再按四个版本推进：STL 基线、按总数量改单、多品种路由、数据结构优化。正文保留面试中的问答，完整实现与测试放在附录，方便独立重写后对照。

## 这道题考什么

这是交易公司 C++ 终面里很常见的一道题。常见的形式是两小时：前一个小时和面试官讨论需求和设计，后一个小时在给定的工程里写代码，让现成的测试通过；有的地方会先给 30 分钟独自读题。用的是普通的 IDE，不是白板。测试全部通过也不一定能拿到 offer，讨论时的表现同样计分。

面试官在这两个小时里看四个方面：

| 方面 | 看什么 |
|---|---|
| 沟通与需求对齐 | 动手前会不会主动问清楚语义，并把结论写下来 |
| 数据结构与硬件 | 能不能给出正确的结构、说出复杂度，再讲出它在缓存和内存分配上的代价 |
| 写代码 | 结构清楚，买卖两侧不复制代码，边写边说，先过简单测试再加功能 |
| 测试与边界 | 说得出怎样证明它是对的，想得到容易漏的边界情况 |

页尾的「评分」一节按这四个方面，列出强、一般、弱三档回答各是什么样子。

## 订单簿怎样工作

### 买盘、卖盘与盘口

尚未成交、留在系统里等待的订单组成**订单簿**（limit order book）。每个品种（一只股票、一个期货合约）有自己的一本簿，分成两侧：买方的出价组成**买盘**（bids），从高到低排；卖方的要价组成**卖盘**（asks），从低到高排。

- 买盘里最高的出价叫最优买价或买一（best bid），卖盘里最低的要价叫最优卖价或卖一（best ask）。
- 两者之差叫买卖价差（spread）。连续撮合处理完一条消息后，只要两侧都不为空，就有 `best_bid < best_ask`；否则还存在能够立即成交的订单。满足这个条件的簿叫未交叉的簿（uncrossed book）。

下面的价格都是最小变动单位 tick 的整数倍。假设卖盘上先后挂着三笔卖单：

| 卖价 | 同价位队列（左边先到） | 价位总量 |
|---|---|---:|
| 102 | #1：3 手 → #2：4 手 | 7 |
| 103 | #3：10 手 | 10 |

新来一笔买单 #4，愿意以不高于 105 的价格买 5 手。它先看最低卖价 102：吃掉队首 #1 的 3 手，再吃 #2 的 2 手，自己全部成交。#2 还剩 2 手，继续留在 102 的队首。

### 主动方与被动方

一笔新订单进入引擎时有两种结果：

1. 不跨价：最低卖价是 102，新买单出价 101，无法成交，订单留在簿上等待。留在簿上的订单叫**被动方**（resting order）。
2. 跨价：最低卖价是 102，新买单愿意出 105，立即触发撮合。进来触发成交的订单叫**主动方**（aggressor）。主动方也可能只成交一部分：如果上面的 #4 要买 20 手，它会吃完 102 的 7 手和 103 的 10 手，剩下 3 手以自己的限价 105 挂入买盘，成为新的被动方。

本题的成交价取被动方的价格，而不是主动方的限价。卖方先把 102 报在簿上，买方接受这个价格成交，所以两笔成交都按 102 计。一笔买单连续扫过 102、103 两档时，每笔成交各自记录被吃掉的那一档的价格。

### 订单类型的差别

常见的订单类型在三处有区别：有没有价格限制，没成交完的部分怎样处理，成交前是否要求数量足够。

| 订单类型 | 价格限制 | 余量 | 实现要点 |
|---|---|---|---|
| 限价单，GTC（good till canceled） | 有 | 挂入本方队列，直到成交或撤销 | 最基本的路径；练习中不处理跨交易日 |
| IOC（immediate or cancel） | 有 | 立即丢弃，不挂单 | 撮合完后多一个分支；一手都没成交也是正常受理，不是拒单 |
| 市价单 | 无 | 通常撤销，有的市场转为限价 | 要单独表示有没有限价，不能让 0 或极值同时充当价格和市价标记；本页不实现 |
| FOK（fill or kill） | 有 | 不允许有余量 | 撮合前先检查限价以内的总量够不够，够了才撮合，不能先成交再撤回 |

### 价格优先、时间优先与改单的排队规则

撮合时先和价格最好的对手方成交：买单先吃最低的卖价，卖单先吃最高的买价。同一价位上先到的先成交，所以每个价位是一个先进先出（FIFO）的队列。

修改一笔还挂在簿上的订单时，惯例是：

- 价格不变，数量减少：原地修改，保留排队位置。只是自己少成交一些，排在后面的订单不受损。
- 价格不变，数量增加：失去时间优先，移到同价位的队尾。否则有人可以先挂 1 手占住队首，再改成 1 万手，绕过后面所有人。
- 改价：从旧价位撤出，按新价格重新进入；新价格如果和对手盘交叉，会作为主动方立即成交。

## 开场：先确认会改变代码的规则

下面是一段模拟面试，用来练习思路，不代表某家公司固定的题面或时长。假设 IDE 里只有一行注释：

> `// Implement an in-memory matching engine supporting add, cancel, and modify.`

**面试官：**「我们来写一个撮合引擎，输入是下单、撤单、改单消息，成交时通知下游。接口你自己定，先别急着写代码，说说你的想法。」

听到题目就开始写 `struct Order` 的候选人，常常写到一半才发现成交价或改单语义理解错了，只能回头重写。应该先把会改变代码结构的规则问清楚。

**候选人：**「设计数据结构之前，我想先确认几条规则：

1. 优先级与成交价：价格优先、时间优先，跨价时按被动方的价格成交，对吗？
2. 订单类型与操作：第一版支持下单、撤单、改单，有效期支持 GTC 和 IOC，FOK 和冰山单留作扩展，可以吗？
3. 改单数量：传的是目标总量，还是新的剩余量？我建议用包含已成交部分的总量，客户还没收到部分成交回报时，也能准确表达总共想买多少。
4. 价格与数量：价格解析成整数 tick，用有符号 `int64_t`，允许 0 和负数（跨期价差会出现）；单笔数量用 `uint32_t`，价位总量用 `uint64_t`，防止多笔大单相加溢出。
5. 品种与 id：先写好单品种的簿，再包一层多品种路由；同一品种里当前挂着的订单 id 不能重复。如果要求整个会话里用过的 id 都不能再用，再加一张历史判重表。
6. 返回值与回调：用 `Result` 枚举区分成功和各种失败原因；成交通过模板参数 `Listener` 同步回调，回调里可以查询，但不能下单、撤单、改单，也不能抛异常。这样可以吗？」

对齐以后，把结论写成一张表，写代码时逐条对照：

| 规则 | 本页约定 | 影响代码的哪里 |
|---|---|---|
| 撮合与定价 | 价格优先、时间优先，取被动方价格 | 两侧的排序方向、同价 FIFO 队列、`Trade::price` |
| 有效期 | GTC 余量挂单；IOC 余量丢弃 | 撮合结束后的一个分支 |
| 改单数量 | 目标总量，包括已成交部分 | 每笔订单要记录累计成交量 `cum` |
| 改单排队 | 同价减量保留；同价加量去队尾；改价重新进入 | `std::list::splice`，或摘链后重挂；改价复用下单入口 |
| id 唯一性 | 正文按品种内的活跃订单判重；附录 D 实现整个会话的历史判重 | 一张活跃索引就够，或者再加一张历史集合 |
| 数值类型 | `Price = int64_t`，`Quantity = uint32_t`，`Volume = uint64_t` | 没有浮点误差，价位总量不溢出 |
| 失败条件 | 新单数量为 0、活跃 id 重复、撤改未知 id、池满、未知品种 | 返回 `Result`，调用方能区分原因 |
| 回调 | 模板参数 `Listener&`，同步调用；只读查询可以，不能修改引擎，不能抛异常 | 撮合循环里的回调可以内联，不需要重入保护和异常回滚 |

### 每个问题为什么要问

面试官往往会追问「为什么要问这个」。每个问题都应该说得出它会改变代码里的哪一处：

- 撮合规则：时间优先时，一个价位只需要一个队列，撮合只看队首。另一种规则是按比例分配（pro-rata），有些期货市场在用：同一价位上，成交量按各笔挂单的数量比例分。比如 100 这个价位上先后挂着 300 手和 100 手的买单，进来一笔 200 手的卖单：按时间优先，200 手全部给第一笔；按比例分配，两笔分别得到 150 手和 50 手。这时撮合要遍历整个价位，计算份额并处理取整剩下的零头，数据结构和撮合循环都不一样。
- 价格的类型：价格不能用 `double`。二进制浮点数不能精确表示大多数十进制小数，`0.1 + 0.2 != 0.3`；而价格要作为有序容器的键，要判断两笔订单是不是同一个价位，误差会让同一个价格分到两个价位上。所以输入时直接从字符串解析成整数 tick，不经过 `double`。在交易公司的面试里，用 `double` 存价格通常会被追问。
- id 在什么范围内唯一：如果只要求同时挂着的订单之间不重复，查一下订单索引就够了；如果要求整个运行期间都不重复，引擎就必须记住所有用过的 id，即使订单早已成交或撤销，这张表会随消息数一直增长，后面的实测会看到它有多贵；如果协议要求 id 递增，判重只需和上一个 id 比较一次。真实系统多半是每个客户在一个交易日内唯一，或者要求递增，或者由引擎另外分配内部编号。
- 输出什么，怎样交给下游：只报成交，还是每条消息都要回报（受理、部分成交、全部成交、撤单确认、拒单）？事件种类决定回调接口有几个函数。交付方式影响性能和正确性：虚函数或 `std::function` 每次调用是一次间接调用；把下游作为模板参数，编译器可以内联回调；也可以让引擎把事件写进预先分配的缓冲区，调用者处理完一条消息后再读取。
- 拒单的检查顺序：一条消息同时有几种错误时报哪一种，被拒绝的下单算不算用过这个 id。后者决定了判重表是在所有检查通过以后才更新，还是一收到消息就更新。附录 D 的题面规定：先查字段，再查重复，最后查未知 id；被拒的下单不占用 id。

还有一个入口边界：引擎接收的 `Quantity` 是无符号数。如果外部协议是文本（附录 D），负数、过大的整数、小数位过多都要在解析层拦下；不能把 `"-5"` 先转成 `uint32_t`，再指望订单簿发现它原来是负数。

## 从操作推导数据结构

**面试官：**「规则清楚了。你打算用什么数据结构？」

先用 STL 给出满足需求的结构，把操作和复杂度讲清楚，再讨论内存分配和缓存，这样后面每一次替换都有明确的目标。

面试官不想听你背出「`map` 加 `list` 加哈希表」，而是想看你从要支持的操作出发，推出每个结构为什么是这样。先把操作列出来，并估计各自出现得多频繁：

| 操作 | 输入 | 要做的事 | 频率 |
|---|---|---|---|
| 撮合 | 一笔新订单 | 反复取对手方的最优价位，按到达顺序和那里的挂单成交，价位吃空后取下一个 | 每笔下单都要检查，只有交叉时才真正成交 |
| 挂单 | 剩余数量、价格 | 找到这个价格的价位，没有就新建，排到队尾 | 大多数下单 |
| 撤单 | 只有 id | 找到这笔订单，从队列中间拿掉；价位空了就删掉价位 | 很高，真实市场里撤单远多于成交 |
| 改单 | id、价格、数量 | 同价减量原地改；否则撤单再挂单 | 中等 |
| 快照 | 无 | 按价格顺序输出每个价位的总量和笔数 | 很少 |

还有一个关于分布的事实：绝大多数操作发生在盘口附近，离最优价几档以内。后面的优化会用到这一点。

### STL 基线

从订单簿的三个高频操作推出容器：

1. 撮合要反复取对手方的最优价，所以价位要有序。买盘用降序的 `std::map<Price, Level, std::greater<Price>>`，卖盘用升序的 `std::map<Price, Level, std::less<Price>>`，两侧的 `begin()` 都是最优价。
2. 同价位按到达顺序成交，撤单又要删掉中间的任意一笔。`std::queue` 只能操作两端，所以用双向链表 `std::list<Order>`：队尾挂单，队首成交；插入、删除其他节点时，已有的迭代器仍然有效。
3. 撤单和改单只给 id，不能扫描整本簿。加一张哈希索引 `std::unordered_map<OrderId, std::list<Order>::iterator>`，拿到链表迭代器后，从订单里读出方向和价格，找到价位，再摘掉节点。

```text
OrderId ──哈希索引──→ 链表节点迭代器
                         │
                         ├─ side（买 / 卖）
                         └─ price ──→ 对应价位 Level 的 FIFO 双向链表

买盘（高价在前）               卖盘（低价在前）
std::map<Price, Level, >       std::map<Price, Level, <>
```

| 操作 | STL 基线的代价（P 为本侧价位数） | 说明 |
|---|---|---|
| 取最优买卖价 | O(1) | 有序容器的 `begin()` 是常数时间 |
| 按价格挂单 | O(log P)，再加链表尾插 O(1) | 在红黑树里找到或新建价位 |
| 按 id 撤单、同价改单 | 哈希平均 O(1)，找价位 O(log P)，摘链 O(1) | 索引只存了订单的迭代器，还要 `map.find(price)` 才能扣价位总量、删空价位 |
| 主动单连续吃掉 K 笔挂单 | 均摊 O(K + E) | E 是被吃空的价位数；按迭代器删除价位，均摊 O(1) |

撤单不能笼统地说成 O(1)。如果面试官问怎样省掉撤单里的 O(log P)，可以让索引同时存 `Level*` 或 `map` 的迭代器。`std::map` 的节点不随其他元素插入删除而移动，这样扣总量是 O(1)，价位变空时按迭代器删除也是均摊 O(1)；代价是要多维护一份定位信息。

### 基线的常数成本

面试官继续问延迟时，再分析常数：

**候选人：**「这套结构的复杂度够用，慢在常数上，主要有三处：

| 成本 | STL 基线 | 替换方案 |
|---|---|---|
| 热路径上的堆分配 | 每挂一笔单，链表节点和哈希节点各分配一次（一次小块分配加释放约 20 ns，见 [[perf/allocation\|内存分配]]）；新价位还要分配红黑树节点 | 预分配的对象池和容量预留：节点池去掉逐笔的订单节点分配；索引、价位和回调要分别检查 |
| 同价队列与索引的间接访问 | 链表节点和哈希节点散落在堆上，簿深时，沿指针访问更可能落到不在缓存里的数据 | 32 位下标的侵入式链表、开放寻址哈希表：订单节点 32 字节，哈希槽位 16 字节连续存放 |
| 价位查找与删除 | 红黑树每次在父子节点之间跳指针 | 最优价放在末尾的有序数组（或有界的价格偏移数组加位图）：最优档被吃空只是一次 `pop_back()` |

我会先写 STL 版，跑通撮合、撤单和改单，再一步步换成对象池、开放寻址哈希表和有序数组，每一步都用差分测试确认外部行为不变。」

### 两个容易出错的细节

真正写代码时，有两处细节最容易卡住或埋下错误。

第一，`std::map::operator[]` 的语义是找不到就插入：`bids_[price]` 找不到 `price` 时，会插入一个默认构造的 `Level`（总量为 0、队列为空），再返回它的引用。挂单时这正好需要：有价位就追加，没有就新建。但在 `bid_volume_at(price)` 这样的只读查询或撤单里写 `bids_[price]`，查询一个不存在的价格就会在簿上留下一个空价位，`best_bid()` 也会跟着变成这个价格。只读查询和已知存在的修改，应该用 `find()`，或者确认存在时用 `at()`。

第二，在 100 和 98 之间插入 99，不需要修改其他价位。容易混淆的是行情里的买一、买二、买三，那是排名；引擎内部每个价位的键是价格本身，里面只有订单队列和总量。插入 99 以后，100 还是 100，98 还是 98，容器按价格有序，从最优价往外遍历时，顺序自然变成 100、99、98。

### 追问

**面试官：**「为什么不用 `std::priority_queue`？」

堆能快速取出最优价，但不能删除中间的元素，撤单做不到。惰性删除（只做标记，浮到堆顶时再丢弃）会让被撤的订单一直占着内存，而真实市场里撤单远多于成交。另外，同价位的时间优先还要把到达序号编进比较键。

**面试官：**「哈希表里存的位置，在别的订单插入、删除以后还有效吗？」

有效，因为用的是节点式容器。`std::map` 和 `std::list` 插入不影响已有的迭代器和引用，删除只影响被删的那个元素（[[associative.reqmts.general#175]]、[[list.modifiers#3]]）；`std::unordered_map` rehash 会让迭代器失效，但元素的指针和引用不变（[[unord.req.general#9]]）。换成 `std::vector` 就不行，一次重新分配会让所有引用失效（[[vector.modifiers#2]]）。后面的对象池存的是下标而不是指针，也是为了不受这条规则限制。

**面试官：**「你的结构有哪些不变量？」

七条：

1. 每条消息处理完以后，簿不交叉：最高买价严格低于最低卖价。
2. 每一侧的价位严格有序，没有两个价位价格相同。
3. 每个价位的总量等于其中所有订单剩余数量之和，笔数等于订单数。
4. 簿上没有空价位，也没有剩余数量为 0 的订单。
5. 订单索引里的 id 恰好是簿上所有挂单的 id，并且指向它们。
6. 换成对象池以后：池里的节点要么挂在簿上，要么在空闲栈里，不会两头都不在（泄漏），也不会两头都在。
7. 同一价位的队列按到达顺序排列，改单失去优先级时按重新到达处理。

前六条可以在代码里直接检查（「怎样验证」一节就这样做），第七条要靠测试用例。另外还有一条跨消息的守恒关系：每笔订单的原始数量等于成交量、剩余量和被撤销的数量之和，可以在测试里从事件流统计。

## 第一版：单簿的 STL 实现

先把所有版本共用的类型放在 `types.hpp` 里。后面的 STL 版、对象池版、优化版和多品种外层都用这一套类型，方便直接做差分对照：

```cpp title="types.hpp"
#pragma once
#include <cstddef>
#include <cstdint>

using OrderId = std::uint64_t;
using Price = std::int64_t;
using Quantity = std::uint32_t;
using Volume = std::uint64_t;

enum class Side : std::uint8_t { Buy, Sell };
enum class TimeInForce : std::uint8_t { GTC, IOC };
enum class Result : std::uint8_t {
    Ok, InvalidQuantity, DuplicateId, UnknownId,
    CapacityExceeded, UnknownSymbol
};

struct Trade {
    OrderId resting_id;
    OrderId incoming_id;
    Price price;
    Quantity quantity;
    bool operator==(const Trade&) const = default;
};
```

- 单笔数量 `Quantity` 用 32 位无符号整数，上限约 42.9 亿；价位总量 `Volume` 用 64 位。同一价位上只要挂两笔 `UINT32_MAX` 的订单，总量就超出 32 位。
- `Trade` 的四个字段里，两个 id 都是 `OrderId`，价格和数量都是整数。如果写成 `Trade{resting_id, id, price, qty}` 这样按位置构造，把两个 id 写反了编译器也不会报错，所以本页构造成交事件时一律用指定初始化器 `Trade{.resting_id = ..., .incoming_id = ...}`，字段顺序写错会编译失败。测试里比较成交序列时仍用按位置的写法，那里的顺序就是要检查的内容。
- 接口允许 id 为 0。后面自己写开放寻址哈希表时，不能随手拿 0 当空槽标记，否则合法的 0 号订单会被拒掉；`IdMap` 会处理这一点。

### 下单：先撮合，再处理余量

公开入口 `add_order` 只做校验和判重，然后交给私有函数 `submit`。`submit` 多接收一个累计成交量 `cum`，是为了改价时复用；外部调用者不能伪造一笔订单已经成交过多少。

```cpp
Result add_order(OrderId id, Side side, TimeInForce tif,
                 Price price, Quantity quantity) {
    if (quantity == 0) return Result::InvalidQuantity;
    if (lookup_.contains(id)) return Result::DuplicateId;
    return submit(id, side, tif, price, quantity, 0);
}

Result submit(OrderId id, Side side, TimeInForce tif, Price price,
              Quantity leaves, Quantity cum) {
    // 1. 和对手盘撮合：方向只在入口判断一次
    if (side == Side::Buy)
        match(id, price, leaves, cum, asks_, std::greater_equal<Price>{});
    else
        match(id, price, leaves, cum, bids_, std::less_equal<Price>{});

    // 2. 处理余量：GTC 挂入本方，IOC 丢弃
    if (leaves != 0 && tif == TimeInForce::GTC) {
        if (lookup_.size() == capacity_) return Result::CapacityExceeded;
        Level& level = side == Side::Buy ? bids_[price] : asks_[price];
        level.orders.push_back(Order{id, side, price, leaves, cum});
        level.total += leaves;
        lookup_.emplace(id, std::prev(level.orders.end()));
    }
    return Result::Ok;
}
```

买卖两侧只有排序方向和跨价条件不同，不需要写两份撮合循环。买单对卖盘传 `asks_` 和 `>=`，卖单对买盘传 `bids_` 和 `<=`，由同一个 `match` 处理：

```cpp
template<class Book, class Cross>
void match(OrderId id, Price price, Quantity& leaves, Quantity& cum,
           Book& opposite, Cross can_cross) {
    auto it = opposite.begin();
    while (leaves != 0 && it != opposite.end()) {
        if (!can_cross(price, it->first)) break; // 最优价都不跨价，后面的价位更不会
        Level& level = it->second;
        while (leaves != 0 && !level.orders.empty()) {
            Order& resting = level.orders.front();
            OrderId resting_id = resting.id;
            Price match_price = it->first;
            Quantity traded = std::min(leaves, resting.leaves);
            leaves -= traded;
            cum += traded;
            resting.leaves -= traded;
            resting.cum += traded;
            level.total -= traded;
            if (resting.leaves == 0) {
                lookup_.erase(resting_id);
                level.orders.pop_front();
            }
            listener_.on_trade(Trade{.resting_id = resting_id, .incoming_id = id,
                                     .price = match_price, .quantity = traded});
        }
        if (level.orders.empty()) it = opposite.erase(it);
        else ++it;
    }
}
```

外层循环走价位，内层循环走同一价位的订单。几处顺序要注意：

- 成交价用 `match_price`，也就是被动方所在价位 `it->first`，不是主动方的限价 `price`。
- 先把吃光的被动单从 `lookup_` 和队列里删掉，再调用 `on_trade`；为此先把 `resting_id` 和 `match_price` 复制到局部变量。这样外层在回调里调用 `contains(resting_id)`，就能知道被动单是否已经离簿，附录 D 的全局路由靠这一点维护。但回调发生时，价位可能还没删除，主动方也还没挂单，整条消息并没有处理完；所以回调里只能做这类查询，不能修改引擎，也不能遍历簿并假设所有不变量都已恢复。
- 价位被吃空后用 `it = opposite.erase(it)` 前进，不留下空价位，否则下一次 `begin()` 拿到的是一个总量为 0 的价位。

### 撤单与迭代器失效

```cpp
Result cancel_order(OrderId id) {
    auto it = lookup_.find(id);
    if (it == lookup_.end()) return Result::UnknownId;
    Position pos = it->second;
    if (pos->side == Side::Buy) remove(bids_, pos);
    else remove(asks_, pos);
    lookup_.erase(it);
    return Result::Ok;
}
```

`remove` 按价格找到价位，扣掉总量，删除链表节点；价位空了就把价位一起删掉。`lookup_` 里存的 `Position` 是 `std::list<Order>::iterator`，`lookup_` 自己 rehash 时，链表节点不动，这个迭代器仍然有效。反过来，`cancel_order` 里的 `it` 是哈希表自己的迭代器，在 `lookup_.erase(it)` 之前没有往 `lookup_` 插入元素，所以也是安全的。rehash 的失效规则见 [[unord.req.general]]。

### 写代码时的追问

**面试官：**「如果有人在成交回调里调用 `cancel_order`，会怎样？」

撮合循环正拿着当前价位的迭代器和对手盘的引用。回调里撤掉的如果是这个价位上剩下的订单，或者改价让价位表重新分配，循环回来时就在使用已经销毁的对象，这是未定义行为。可以明确规定回调不能修改引擎，并在调试版本里用一个标志检查；也可以让引擎只把事件写进缓冲区，整条消息处理完再派发。真实系统里所有外部请求都变成排队的消息，回调里只能发消息。

**面试官：**「数量和金额会溢出吗？」

单笔数量是 32 位，价位总量用 64 位：即使一个价位上有一百万笔最大数量的订单，总量也不到 2⁵³。成交金额是价格乘数量：`int64_t` 的价格乘以 32 位数量，价格的绝对值超过约 2³¹ 个 tick 时就可能超出 `int64_t`，有符号溢出是未定义行为，要限制价格范围，或用 128 位整数、`__builtin_mul_overflow` 检查。数量用无符号类型还有一个陷阱：`a - b` 在 `b > a` 时回绕成一个很大的数，比溢出更难发现，改单里的 `new_total <= cum` 就是为此先比较再相减。

**面试官：**「有哪些边界情况你还没测？」

一笔订单扫穿多个价位；恰好全部成交时既不挂单，也不在索引里留记录；价位被吃空或撤空后从簿里删除；改单改到和对手方交叉；改单后全部成交，再撤单应该返回未知 id；改单的新总量不超过已成交数量时订单要结束，而不是挂一笔数量回绕的单；改价重下时累计成交量要带过去，主动方成交一部分后挂上簿，也要记住它已经成交的数量；被拒绝的下单不占用 id；撤掉队列中间的订单。

## 第二版：按总数量改单

第一版跑通以后加上 `modify_order`。这里要先想清楚一个问题：客户发出改单时，看到的成交状态可能已经过时。

### 为什么用目标总量

用一条时间线看成交回报和改单怎样交错：

1. 客户挂出买单 #1，要买 100 手。引擎里：剩余 100，累计成交 0。
2. 一笔卖单吃掉 #1 的 80 手。引擎发出成交回报，但回报还在路上，客户没有收到。引擎里：剩余 20，累计成交 80。
3. 客户觉得 100 手太多，想把总买入量降到 60 手，发出 `modify_order(1, px, 60)`。
4. 这条改单到达引擎。

如果把 60 当作新的剩余量写进订单，之后再来卖单，客户最终会买到 80 + 60 = 140 手：本想少买，结果多买了。

本题让每笔订单记录累计成交量 `cum`，改单传目标总量 `new_total`，新的剩余量是：

```text
new_leaves = new_total - cum
```

在上面的场景里 `new_total`（60）不大于 `cum`（80），说明已经成交的数量达到了客户的新目标，引擎撤掉剩下的 20 手。已经成交的 80 手不能撤回，仍然有效。`Quantity` 是无符号数，不能先算 `60 - 80` 再判断，那样会回绕成四十多亿；要先判断 `if (new_total <= order.cum) return cancel_order(id);`，成立就撤单，否则再相减。

这里处理的是消息在网络中交错到达造成的状态差异：引擎始终在一个线程里按顺序处理消息，没有两个线程同时修改订单簿，和数据竞争无关。

FIX 协议的改单（OrderCancelReplaceRequest）用的就是总数量，多数基于 FIX 的接口也这样，原因正是客户发改单时看到的剩余数量可能已经过时。另一种设计是把减量和其他改单分成两种消息，例如纳斯达克的 OUCH 协议：减量用一条只能减少的「部分撤单」，写目标剩余数量，目标值不小于当前剩余时什么也不改，所以永远保留排队位置；加量和改价必须用「替换」消息，它生成一笔新订单，一律重新排队。这样引擎不需要猜客户想增还是减。总量语义不是唯一的做法，按题目给定的消息语义实现即可，不能只凭函数名猜数量的含义。

### 部分成交后的改单

假设买单原本 100 手，改单到达前已成交 40 手，簿上还剩 60 手，价格不变：

| `new_total` | 新剩余量 `new_total - 40` | 与当前剩余 60 比较 | 动作 |
|---|---|---|---|
| 150 | 110 | 变大 | 剩余改为 110，价位总量加 50；移到同价位队尾 |
| 80 | 40 | 变小 | 剩余原地改为 40，价位总量减 20；保留排队位置 |
| 40 | 0 | 归零 | 撤掉剩余的 60 手，订单离簿 |
| 20 | `new_total < cum` | 已成交量超过目标 | 撤掉剩余的 60 手，已成交的 40 手有效 |

### 改单的实现

```cpp
Result modify_order(OrderId id, Price new_price, Quantity new_total) {
    auto it = lookup_.find(id);
    if (it == lookup_.end()) return Result::UnknownId; // 已全部成交离簿或已撤单
    Order& order = *it->second;
    if (new_total <= order.cum) return cancel_order(id);
    Quantity new_leaves = new_total - order.cum;

    // 价格不变：减量原地修改，加量用 splice 移到队尾
    if (new_price == order.price) {
        Level& level = order.side == Side::Buy
            ? bids_.at(order.price) : asks_.at(order.price);
        bool increase = new_leaves > order.leaves;
        level.total -= order.leaves;
        order.leaves = new_leaves;
        level.total += order.leaves;
        if (increase)
            level.orders.splice(level.orders.end(), level.orders, it->second);
        return Result::Ok;
    }

    // 价格改变：先复制字段再撤单，带着累计成交量重新撮合或挂单
    Side side = order.side;
    Quantity cum = order.cum;
    cancel_order(id);
    return submit(id, side, TimeInForce::GTC, new_price, new_leaves, cum);
}
```

三处需要解释：

1. 同价加量用单节点的 `list::splice`。它只改链表的前后指针，把节点移到队尾，不分配内存；节点还是同一个节点，`lookup_` 里存的迭代器不用更新。标准规定这个重载是常数时间，迭代器保持有效，见 [[list.ops]]。同价加量也不需要重新撮合：这笔订单原来就挂在这个价格上，说明它和对手盘不交叉。
2. 改价时先复制再撤单。`cancel_order(id)` 会销毁链表节点，之后 `order` 引用就悬空了，所以要先把 `side` 和 `cum` 复制到局部变量，再撤单、调用 `submit`。
3. 主动方成交一部分后挂单，`cum` 也要带着。卖盘挂着 3 手，新买单 #2 买 10 手，先主动吃掉 3 手，剩下 7 手挂入买盘，这时 #2 的 `cum` 应该是 3，不是 0。否则客户之后把总量改成 5，引擎会留下 5 手，而正确答案是 5 − 3 = 2 手。`match` 同时累加主动方的 `cum`，再传给挂单节点，就是为了这条路径。

完整的 STL 版见附录 A。

## 第三版：多品种

`AAPL` 的买单不能和 `MSFT` 的卖单成交。单品种的簿写对以后，支持多品种不需要改动撮合算法，只要在外面包一层路由 `MultiEngine`：预先注册品种，给每本簿分配容量；请求到达时按品种分发；内部的监听适配器给成交补上品种名，再交给下游。

```cpp
Result add_order(const std::string& symbol, OrderId id, Side side,
                 TimeInForce tif, Price price, Quantity quantity) {
    auto it = books_.find(symbol);
    if (it == books_.end()) return Result::UnknownSymbol;
    return it->second->book.add_order(id, side, tif, price, quantity);
}
```

如果入口拿到的品种名是 `std::string_view`（例如直接指向网络缓冲区），`books_.find(symbol)` 要先构造一个 `std::string`。C++20 起，给 `std::unordered_map` 配上带 `is_transparent` 的哈希和比较函数，就可以直接用 `string_view` 查找。更常见的做法是在网关处把品种名换成整数编号，撮合时根本不查字符串表，附录 E 的计时程序就是这样。

每本簿和它的监听适配器由 `std::unique_ptr<Entry>` 持有。簿持有监听者的引用，STL 版还持有自己链表的迭代器，所以簿不可复制、不可移动；放在 `unique_ptr` 里，注册更多品种时已有的对象不会搬家。注意 rehash 使哈希表的迭代器失效，但不改变元素的地址，这两种保证要分开。完整代码见附录 B 的 `multi_engine.hpp`。

**面试官：**「如果撤单和改单不带品种，比如附录 D 的题面只有 `CANCEL id` 和 `AMEND id price qty`，怎么知道去哪本簿？」

分两步回答：

1. 先确认前提：撤单不带品种，协议就必须保证 id 在所有品种之间唯一。否则两本簿里都有 #1，只凭 id 无法确定撤哪一笔。
2. 再给结构：外层维护一张全局路由表 `route: OrderId → 簿的编号`。新单撮合后如果还挂在簿上（`book.contains(id)` 为真），就写入路由；挂单被吃光、撤单成功、改单后离簿时，就从路由删除。如果还要求整个会话里成功受理过的 id 都不能再用，再加一张只增不减的历史集合 `used`。附录 D 的 `cli.cpp` 实现了路由、历史判重和容量拒单的配合。

## 第四版：逐步替换数据结构

**面试官：**「单簿和多品种的逻辑都对了。如果要求吞吐和尾延迟再好一个数量级，你改哪里？」

下面分四步替换订单队列、id 索引和价位表，得到附录 B 的 `FastBook`。在相同的容量约定下，它必须和 STL 版产生相同的受理结果、成交事件和快照；速度有没有提升，要另外测量。

### 第一步：订单队列换成对象池

先去掉最频繁的链表节点分配。构造时一次性分配 `std::vector<Node>` 作为固定容量的对象池，用 32 位下标代替 64 位指针，把同价位的订单串成双向链表；空闲的下标放在栈 `free_` 里复用。这种把前后链接直接放进业务对象的链表叫**侵入式链表**（intrusive list）。

```cpp
using Index = std::uint32_t;
static constexpr Index nil = UINT32_MAX;

// 节点 32 字节；缓存行大小依目标平台而定
struct alignas(32) Node {
    OrderId id = 0;       // 8B
    Price price = 0;      // 8B
    Quantity leaves = 0;  // 4B
    Quantity cum = 0;     // 4B
    Index prev = nil;     // 4B
    Index next = nil;     // 4B
};
static_assert(sizeof(Node) == 32);

struct Level {
    Index head = nil;
    Index tail = nil;
    Volume total = 0;
};
struct Locator { Index index; Side side; };
```

空闲栈按逆序压入，从 `capacity - 1` 压到 0，这样最先弹出的是 0、1、2……，开始时挂单在数组里是连续的。经过大量撤单和复用以后，同价队列里相邻的订单不一定在相邻地址，但都在同一块预分配的内存里。节点池构造后不再扩容，所以节点地址稳定。

主干逻辑基本不变，只是把 `std::list` 的操作一对一换掉：

| 操作 | `StlBook` | `PoolBook` / `FastBook` | 区别 |
|---|---|---|---|
| 位置句柄 | `std::list<Order>::iterator`（常见 64 位实现为 8 字节） | `uint32_t` 下标（4 字节） | 句柄减半，地址稳定 |
| 挂到队尾 | `level.orders.push_back(Order{...})` | 弹出 `free_.back()`，填值，`append(level, index)` | 不再为订单节点分配内存 |
| 读队首 | `level.orders.front()` | `nodes_[level.head]` | 按下标寻址 |
| 摘除并回收 | `level.orders.erase(pos)` | `unlink(level, index)`，`free_.push_back(index)` | 不再释放内存，槽位立即复用 |
| 同价加量 | `level.orders.splice(end, orders, it)` | `unlink`，更新数量，`append` | 只改整数下标 |

写 `append` 和 `unlink` 时，要定好谁负责更新价位总量，否则容易加两次或漏扣。这里让 `append` 把 `node.leaves` 加进 `level.total`，`unlink` 只改链接，不碰数量：

```cpp
void append(Level& level, Index index) noexcept {
    Node& node = nodes_[index];
    node.prev = level.tail;
    node.next = nil;
    if (level.tail != nil) nodes_[level.tail].next = index;
    else level.head = index;
    level.tail = index;
    level.total += node.leaves;
}

void unlink(Level& level, Index index) noexcept {
    Node& node = nodes_[index];
    if (node.prev != nil) nodes_[node.prev].next = node.next;
    else level.head = node.next;
    if (node.next != nil) nodes_[node.next].prev = node.prev;
    else level.tail = node.prev;
    node.prev = node.next = nil;
}
```

调用处统一先扣旧量、再计新量：

```cpp
bool increase = new_leaves > node.leaves;
if (increase) unlink(level, index);
level.total -= node.leaves;
node.leaves = new_leaves;
if (increase) append(level, index);
else level.total += node.leaves;
```

例如价位总量 7，其中当前订单 3 手，改成 6 手，结果必须是 7 − 3 + 6 = 10。不要先给总量加差值，再让 `append` 加一遍新数量。

#### 池满时还能不能接新单

假设对象池容量只有 1，簿上已经挂着一笔「100 卖 10 手」，池已满。进来一笔新买单：

| 新买单 | 撮合与槽位 | 结果 |
|---|---|---|
| 100 买 5 手 | 新单全部成交，旧卖单剩 5 手，不需要新槽位 | `Ok` |
| 100 买 15 手 | 旧卖单被吃光，归还 1 个槽位；新单剩 5 手，用这个槽位挂单 | `Ok` |
| 99 买 15 手 | 不跨价，余量要挂单，但没有空槽位 | `CapacityExceeded` |

所以不能在撮合前一看池满就拒绝所有新单。本题允许池满时继续成交，等撮合结束、确认 GTC 还有余量要挂时，再检查有没有空槽位。如果业务规定池满后一律拒单，那是另一种接入政策。

面试官可能接着问：会不会先成交了一部分，最后挂单时才发现没有槽位，返回失败，留下半完成的状态？在当前单线程、不重入、没有冰山单补量的规则下，这条路径走不到：只要发生过成交而新单还有余量，就说明至少有一笔旧挂单被吃光并归还了槽位；撮合过程中只归还槽位，不占用槽位，所以挂余量时至少有刚释放的那一个。改价也一样，先撤单归还一个槽位，再重新挂单。这个论证依赖当前规则，以后加入冰山单补量、回调重入或其他在撮合中途分配节点的路径，要重新检查。

只换掉订单队列的过渡版本见附录 B 的 `pool_book.hpp`。

### 第二步：id 索引换成开放寻址哈希表

`PoolBook` 去掉了链表节点的分配，但 `std::unordered_map` 在常见实现里每个元素仍是一个单独分配的节点，查找要先读桶、再跳到节点。只调用 `reserve` 也不会预先创建这些节点。

第二步把索引换成开放寻址、线性探测的哈希表 `IdMap`：所有键值对直接放在一个长度为 2 的幂的连续数组 `slots_` 里，每个槽位 16 字节（8 字节 `OrderId`，8 字节 `Locator`），冲突时往后找下一个空槽。空槽用 `UINT64_MAX` 标记，而 id 恰好是 `UINT64_MAX` 的那一项单独存在一个 `optional` 里，所以 0 到 `UINT64_MAX` 都是合法的 id。

有两处算法细节要讲清楚：

1. 散列函数。订单号常常是 1、2、3 这样连续递增的整数，直接对容量取模，相邻 id 会落在相邻槽位，形成长串冲突。乘以 `0x9E3779B97F4A7C15`（2⁶⁴ 除以黄金分割比）再取高位，一次乘法就能把连续整数打散，这叫 Fibonacci 散列。
2. 删除。线性探测表删掉位置 `i` 时，不能简单地把它标成空槽：当初因为 `i` 被占而顺延到后面的元素，查找时会在 `i` 处遇到空槽而提前停止，结果找不到。一种做法是留一个删除标记（墓碑），但要控制标记积累并定期清理。这里用回移删除（backward-shift deletion）：清空 `i` 后，向后扫描同一段连续占用的槽位；如果槽位 `j` 上元素的理想位置 `h` 不在环形区间 `(i, j]` 内，说明它当初越过了 `i`，就把它移回 `i`，再把 `j` 当作新的空位继续扫描，直到遇到真正的空槽。判断条件写成无符号运算是 `((j - h) & mask) >= ((j - i) & mask)`。这样表里没有删除标记，查找遇到空槽就可以停。

```cpp
void erase(OrderId id) noexcept {
    if (id == empty_key) {
        if (last_id_) { last_id_.reset(); --size_; }
        return;
    }
    std::size_t i = home(id);
    while (slots_[i].id != id) {
        if (slots_[i].id == empty_key) return;
        i = next(i);
    }
    for (std::size_t j = next(i); slots_[j].id != empty_key; j = next(j)) {
        std::size_t h = home(slots_[j].id);
        if (((j - h) & mask()) >= ((j - i) & mask())) {
            slots_[i] = slots_[j];
            i = j;
        }
    }
    slots_[i].id = empty_key;
    --size_;
}
```

### 第三步：价位表换成有序数组

`std::map` 的每个价位是一个红黑树节点，新建价位要分配内存，找相邻价位要在树上跳指针。第三步把两侧的价位表都换成连续的 `std::vector<Level>`，并把最优价放在数组末尾：

- `bids_` 按价格升序排列，例如 `[98, 99, 100]`，最高买价在 `bids_.back()`；
- `asks_` 按价格降序排列，例如 `[104, 103, 102]`，最低卖价在 `asks_.back()`。

最优价放在末尾，是因为大部分操作发生在盘口附近：

- 主动单吃空对手方的最优价位，只需要 `pop_back()`，不移动其他元素；
- 在盘口附近新建或删除一个价位，只需要移动末尾的几个 `Level`（这份实现的 `Level` 是 32 字节）。如果最优价放在下标 0，盘口每变一次都要移动整个数组。

按价格找价位用 `std::ranges::partition_point` 二分：

```cpp
// 价位从差到好排列，最优价在 back()；返回第一个不差于 px 的位置
template<Side S, class Vec>
static auto lower(Vec& levels, Price px) noexcept {
    return std::ranges::partition_point(levels, [&](const Level& l) {
        return better<S>(px, l.price);
    });
}
```

如果返回的迭代器 `it != own.end() && it->price == px`，价位已经存在；否则在 `it` 处插入新价位，数组仍然有序。

这一步有前提，要主动说出来：有序数组比红黑树快，前提是活跃价位数不多，或者操作集中在盘口附近。如果一个品种挂着几万个价位，撤单又均匀地落在远离盘口的位置，每次从数组中间删除都要移动 O(P) 个元素，反而可能比 `std::map` 慢。更多对比见 [[perf/choosing-containers|容器选择]]。

如果面试官继续问能不能连二分查找也省掉：当一个品种当日合法的价格范围有界（例如涨跌停之间几千到几万个 tick），可以用 `price - base_price` 直接作为数组下标，O(1) 找到价位；最优价位被吃空后，为了不逐格扫描空价位，再加一层位图，每个非空价位占 1 位，用 `std::countr_zero` 或 `std::countl_zero` 跳到下一个非空价位；范围更大时用两层位图，64 × 64 = 4096 档只需两次位运算。折中的做法是只给盘口附近的一段价格开数组，远处的挂单放回有序容器。要说清范围外的价格怎么处理，以及稀疏范围是否浪费内存。

如果问到节点大小和冷热字段：这里的 `Node` 只有 32 字节，x86 上常见的 64 字节缓存行放得下两个（测试机 M2 Pro 的缓存行是 128 字节）。真实系统的订单还带着账户、客户订单号、时间戳、风控标记，常常上百字节，而撮合循环只用到 `leaves`、`cum`、`id` 和 `next`。可以把不常用的字段拆到另一个按同一下标索引的数组里，减少撮合时读进缓存的数据；是否有收益要测量，见 [[perf/memory-hierarchy|内存层次]]。

### 第四步：开盘前预留容量

节点池大小固定，用完时返回容量错误。价位数组和外层的 `IdMap` 仍然会增长；某条消息触发扩容时，分配和搬移的全部成本都落在这一条消息上。

构造时按预计的挂单数和价位数预留：

```cpp
explicit FastBook(Listener& listener, std::size_t capacity = 1024,
                  std::size_t expected_levels = 256)
    : listener_(listener),
      nodes_(checked_capacity(capacity)),
      lookup_(capacity) {
    free_.reserve(capacity);
    for (std::size_t i = capacity; i != 0; --i)
        free_.push_back(static_cast<Index>(i - 1));
    bids_.reserve(expected_levels);
    asks_.reserve(expected_levels);
}
```

`expected_levels` 只是预留值，不是上限，价位数超过它时 `vector` 仍会扩容。固定的节点池也不等于整个进程不再分配内存：外层的路由表、历史判重表和监听者要分别检查。如果要求交易时段完全不分配，还要规定每种资源的上限和超限后的处理，并在启动时预先触碰这些内存。

这些实现都不处理内存分配失败后的回滚。监听者不能抛异常；分配失败时，不能捕获异常后当作普通拒单继续使用这个引擎。如果要求故障后继续服务，就要在修改状态前取得全部资源，或者设计可回滚的状态更新和延后提交的事件缓冲。

### 测量结果

**面试官：**「你说连续存储更快，有测量吗？」

附录 E 的 `bench.cpp` 用和附录 D 的 `cli.cpp` 相同的外层规则（8 个品种、全局路由、整个会话的 id 判重）驱动两种实现，在内存里预先生成消息，不计解析和输出，成交交给一个只计算哈希的监听者。计时前先确认两种实现的成交和最终快照完全相同。

测试机是 Apple M2 Pro（16 GB 内存），macOS，Homebrew Clang 23 + libc++，`-std=c++20 -O2 -DNDEBUG`。消息流这样生成：

- 8 个品种，中间价各自随机游走；
- 下单时 85% 落在中间价外 1 到 20 档，15% 越过中间价 0 到 3 档，多半会立即成交；
- 生成时用 STL 版跟踪哪些订单还挂着，撤单和改单只针对挂着的订单，其中七成落在最近挂出的 32 笔上，模拟不断刷新的报价；簿上的订单数按目标值调节；
- 每种深度 1000 万条消息。浅簿约 8 千笔挂单，产生 158 万笔成交；深簿约 80 万笔挂单，产生 509 万笔成交。

每个品种的节点池按目标挂单数的两倍分配，两种实现的容量相同。吞吐取 5 次重复中最快的一次，整个程序跑 3 遍，表中是 3 遍的中位数：

| 每条消息的平均耗时 | 浅簿（约 8 千笔挂单） | 深簿（约 80 万笔挂单） |
|---|---:|---:|
| `StlBook`，外层用 `std::unordered_map` | 150 ns | 371 ns |
| `FastBook`，外层用 `IdMap`，预留容量 | 67 ns | 109 ns |
| `FastBook`，要求 id 递增（`id <= last` 即重复） | 42 ns | 95 ns |
| `FastBook`，不判重 | 42 ns | 95 ns |
| `FastBook`，外层不预留容量 | 74 ns | 113 ns |

有几点值得注意。

第一，簿深时差距更大：浅簿的耗时降到不到一半，深簿降到不到三分之一。8 千笔订单的节点放得进缓存，STL 版沿指针访问大多命中；80 万笔订单时，STL 版的链表节点和哈希节点散落在堆上，`FastBook` 的节点池只有约 51 MB 且连续，价位也在连续数组里。沿指针访问慢不慢，取决于数据量。

第二，剩下的时间里，最大的一块不在数据结构里，而在需求里。「拒绝整个会话里用过的 id」要求判重表容纳全部受理过的 id，1000 万条消息里有几百万个，远远超出缓存，每次下单几乎都要付一次缓存未命中。改成要求 id 递增，判重只是和上一个 id 比较一次，浅簿从 67 ns 降到 42 ns，深簿从 109 ns 降到 95 ns，和完全不判重一样快。这一步在代码里做不到：要么协议规定 id 递增，要么只在一个交易日内判重、每天清空。这值得向定需求的人提出来。

第三，平均值之外还要看尾部。下面逐条消息计时。本机 `steady_clock` 的步长约 41 ns，一次 `now()` 本身要十几纳秒，所以 p50 一栏只有 42、83、125 这几个值，只能看量级；p99.9 和最大值在三遍之间波动较大，给出的是范围。

| 浅簿 | p50 | p99 | p99.9 | 最大值 |
|---|---:|---:|---:|---:|
| `StlBook` | 125 ns | 333 ns | 1.0–1.3 µs | 0.2–1.1 ms |
| `FastBook`，预留容量 | 83 ns | 208–250 ns | 1.0–3.5 µs | 0.1–5.3 ms |
| `FastBook`，不预留容量 | 83 ns | 208 ns | 0.3–2.5 µs | 70–85 ms |
| `FastBook`，要求 id 递增 | 42 ns | 125 ns | 0.2–0.8 µs | 0.05–0.07 ms |

| 深簿 | p50 | p99 | p99.9 | 最大值 |
|---|---:|---:|---:|---:|
| `StlBook` | 167–250 ns | 1.6–2.5 µs | 2.9–25 µs | 1.9–9.0 ms |
| `FastBook`，预留容量 | 125 ns | 500–625 ns | 2.6–5.0 µs | 1.7–8.5 ms |
| `FastBook`，不预留容量 | 125 ns | 459–542 ns | 0.9–3.0 µs | 75–98 ms |
| `FastBook`，要求 id 递增 | 125 ns | 417–500 ns | 0.7–1.0 µs | 0.04–0.75 ms |

不预留容量时，判重表随着 id 增多不断翻倍，最后一次扩容要把几百万个元素重新散列到几百 MB 的新表里，这一条消息就要等几十毫秒，三遍里最长 98 ms。对撮合引擎来说，这种停顿比平均慢几纳秒严重得多，所以容量要在开盘前预留，交易时段不能扩容，还要监控离上限还有多远。

预留也有代价：判重表一开始就按 1000 万个 id 分配，大约 512 MB，每次查找都落在这一大片内存里，p99.9 反而常常比不预留时高。不预留的版本在前半段表还小，查找多半命中缓存，只是要承受几次扩容。要求 id 递增时这张表根本不存在，平均、p99.9 和最大值都是四种里最好的。所以判重的问题不只是预留与否，更好的办法是让这张表变小或消失。预留以后仍偶尔出现毫秒级的最大值，三遍之间差别很大，可能来自缺页、系统调度或其他进程，我们没有查明原因。

还要说清这个基准没测什么：文本解析、网络收发、真实行情的消息分布，以及多个品种的簿互相挤占缓存。品种名查表也不在里面：计时程序在入口就把品种换成了整数编号。本页早先一版按字符串查品种表，采样显示约 16% 的时间花在计算字符串哈希和比较字符串上，真实系统同样会在网关处把品种名换成整数。

计时用的 `bench.cpp` 见附录 E。早期版本曾把全局路由表也按 1000 万个 id 预留，路由表和判重表合计约 1 GB，结果预留后的 p99 比不预留差了好几倍；改成按节点池总容量预留路由表以后，才得到上表。预留多少，也要按每张表实际存放的东西来定。

测量方法见 [[perf/measuring|性能测量]]。换一台机器、换一种消息分布，数字都会变；要回答「快了多少」，应当拿目标环境的真实消息流重放。

## 怎样验证

**面试官：**「代码写完了，你怎么证明它是对的？尤其是换了对象池和回移删除以后。」

只测一两笔成交覆盖不了这些状态变化。验证分四层，分别检查业务规则、内部结构、实现之间的一致性和内存错误。

### 确定性用例

结构检查发现不了「同价位是不是先到先成交」这类问题，所以先为每条规则手工构造恰好触发和恰好不触发的场景。附录 C 的 `examples()` 和附录 D 的 22 个分阶段用例覆盖了：

- 同价多单排队、跨多个价位扫单、成交价取被动方价格；
- 撤队首、队中、价位的最后一笔，空价位被删除；
- 同价减量保留位置，同价加量移到队尾；
- 部分成交后传入 `new_total <= cum`，撤掉剩余量且不回绕；
- 主动方成交后挂单再改单、改价后立即成交再改单，`cum` 一直正确；
- IOC 部分成交后丢弃余量，零价格与负价格，同一价位两笔 `UINT32_MAX` 的总量，池满的四条路径（全部成交、吃光旧单后复用槽位、不跨价拒单、改价归还槽位后重挂），多品种使用相同 id 不串簿。

### 不变量检查

`PoolBook` 和 `FastBook` 都有一个 `check()`，测试时每处理一条消息就扫描一遍，检查四条不变量：

1. 两侧都不为空时 `*best_bid() < *best_ask()`；有序数组里相邻价位严格有序；没有空价位，也没有剩余量为 0 的节点。
2. 每个价位链表里各节点的 `leaves` 之和等于 `level.total`，节点个数等于 `level.count`。
3. 每个节点的 `prev`、`next` 前后一致，首尾正确；每个活跃节点都能在 `lookup_` 里查到，下标和方向一致。
4. 活跃节点和空闲槽位不重复、不重叠，合起来恰好覆盖整个池。只检查 `active + free == capacity` 不够：一个槽位被重复归还两次，同时另一个槽位丢失，总数仍然相等。附录的代码用布尔数组 `seen` 标记每个访问过的下标，遍历链表和空闲栈时遇到越界或重复就报错，环路也会被发现。

检查器本身也要验证。我们往 `FastBook` 里人为放进两个错误，用附录 C 的同一种随机消息流（种子 1）对照 `StlBook`，每条消息之后调用 `check()`：

| 放进的错误 | 差分测试 | `check()` |
|---|---|---|
| 同价减量时不更新价位总量 | 第 182 条消息时快照不一致 | 第 182 条消息时失败 |
| 订单离簿时，每 97 次里有一次既不从索引删除，也不放回空闲栈 | 到第 611 条消息仍未发现 | 第 611 条消息时失败 |

第一种错误不影响成交，只让快照里的总量出错；差分测试每一步都比较快照，所以同时发现了它。只打印最终快照的用例，要恰好在减量之后检查才能发现。第二种错误一开始对外完全没有影响，泄漏的节点只是悄悄占着池，直到它造成不一致之前，只有检查池划分的 `check()` 能看出来。`check()` 会分配临时数组、扫描整个池，只在测试中使用。

### 三方差分

把逻辑最简单的 `StlBook` 当作参照，用固定种子生成随机的下单、撤单、改单消息，包括正、负、零价格，零数量，重复的活跃 id，离簿后复用的 id，同时交给 `StlBook`、`PoolBook` 和 `FastBook`（附录 C 跑 100 × 1000 步）。每一步比较三者的返回值、成交序列和全部价位快照，并调用 `pool.check()` 和 `fast.check()`。

如果随机测试在第 2800 步发现不一致：先用同一个种子复现；再缩小输入，截掉出错之后的消息，然后逐段、逐条删除前面的消息，删掉以后仍然出错就保留删除，最后手工推演剩下的几条。附录没有实现自动缩减。

RapidCheck 这类基于性质的测试框架能自动完成这种缩减。三种实现可能共享同一个业务错误，所以差分通过不能代替写明预期结果的用例。`IdMap` 另外单独和 `std::unordered_map` 对照，检查碰撞、跨数组末尾的探测、回移删除、扩容和 id 的两个端点。

### sanitizer

用 `-fsanitize=address,undefined` 编译，跑全部确定性用例和随机差分，可以发现数组越界、撤单后继续使用悬空引用（例如改价时先撤单再读 `order.cum`）和有符号整数溢出。见 [[toolchain/testing|测试、sanitizer 与模糊测试]]。

## 继续追问：从规则扩展到系统设计

回答扩展题时，先确认业务语义，再说改哪里，最后说新增的边界。

- 加上 FOK 怎么改？不能边撮合边回滚。在 `submit` 撮合前加一步只读检查：从对手方最优价位开始，累加限价以内各价位的 `level.total`，够了才进入 `match`，不够就整笔取消。这是价位维护总量的另一个用处：只需扫价位，不需要扫单笔订单。如果同时有自成交保护或冰山单的隐藏量，检查要按实际可成交的数量算。
- 加上自成交保护（self-trade prevention）怎么改？订单多存一个账户号。`match` 取到队首的被动单时，先比较双方账户；相同时按交易所规则选择：撤主动单的余量、撤被动单后继续、两边都撤，或者互相抵减数量但不报成交。如果撤掉被动单，要先保存后继，或者从新的队首继续，不能访问已经失效的节点。
- 冰山单和止损单呢？冰山单分成显示量和隐藏量，行情快照只算显示量；显示部分成交完以后，从隐藏量补出一批新的显示量，用 `unlink` 加 `append` 排到同价位队尾（这是一种常见的补量政策，具体按题目规定）。止损单平时放在另一本按触发价排序的簿里，触发后转成普通订单送进主簿；要规定连锁触发时的处理顺序。
- 有的期货市场按比例分配（pro-rata），结构怎么变？同一价位按各笔挂单的数量比例分配成交量，撮合要遍历整个价位，按 `level.total` 算份额，再把取整剩下的零头按 FIFO 或按最大挂单分掉。所以仍然要能遍历同价位的订单并维护总量；具体的分配和零头规则要先确认。
- 开盘集合竞价怎么撮合？收集阶段只挂单不撮合，允许买价高于卖价，这时暂停「簿不交叉」的检查。开盘时在交叉区间内找一个统一成交价，使 `min(累计可买量, 累计可卖量)` 最大；相同时再比较未成交的不平衡量和离参考价的距离。按这个价格一次性配对，剩余的订单转入连续撮合。
- 崩溃后怎样恢复？时间优先的「时间」以谁为准？常见做法是由入口的定序器（sequencer）给请求排定顺序，而不是采用客户端的时间戳，再按恢复协议记录和复制输入。引擎写成确定性的状态机：不读系统时钟，不依赖无序容器的遍历顺序，不读未初始化的内存。崩溃后加载最近的快照，回放之后的定序日志，就能恢复相同的状态和事件。还要定义哪些回报已经发出、恢复后怎样去重；快照和回放本身不解决事件的重复发送。
- 回调用虚函数、`std::function` 还是模板？虚函数和 `std::function` 每次调用都是一次间接调用，目标固定时分支预测很容易猜中，代价一般在几纳秒以内。`std::function` 的额外代价在构造：捕获的东西放不进内部缓冲区就要分配内存，所以只在初始化时构造一次。要彻底去掉间接调用，就把监听者作为模板参数让编译器内联，代价是引擎的代码都放在头文件里。本页的实现都这样写：`template<class Listener>`，监听者只要有一个 `on_trade(const Trade&)`。
- 如果像 FIX 那样，每次改单都换一个新的订单 id 呢？引擎内部给订单一个不变的编号，索引从客户 id 映射到这个编号；改单成功后删掉旧 id 的映射，加上新 id 的映射。还要处理在途的消息：客户用旧 id 发出的撤单，到达时改单已经生效，旧 id 已不在索引里，要回复撤单失败并说明原因，客户才能用新 id 重试。
- 风控检查放在哪里？放在订单进入撮合之前，在网关或单独的风控模块：价格是否偏离参考价太远，数量是否超限（防止胖手指），持仓和资金够不够，消息频率是否超限，还有一键停止某个账户全部交易的开关。撮合引擎内部保留最后一道检查，例如成交价不能超出涨跌停范围。
- 怎样利用多核，给引擎加一把锁行不行？不加锁，一本簿只由一个线程撮合。撮合顺序本身就是规则：两个线程抢一把锁时谁先拿到是偶然的，同样的输入可能得到不同的成交；而且一条消息只要几十纳秒，锁和簿的数据在核之间来回传递的代价比撮合本身还大。多核用在簿的外面，见附录 F。
- 做市商不运营交易所，为什么也常考撮合引擎？做市策略里到处都是订单簿：一边接收逐笔行情，在本地重建交易所的订单簿（可以复用价位、队列和 id 索引，但要按协议处理新增、删除、成交和序号缺口）；一边在回测里推演自己的挂单排在第几、什么时候会成交。

## 怎样安排练习

如果给自己一小时练习，目标是写出能验证的基线，而不是把所有优化都写完：

| 时间 | 目标 | 检查自己 |
|---|---|---|
| 0–10 分钟 | 确认题面，手推一笔成交和一笔部分成交后的改单 | 价格、排队、数量语义和 id 范围是否明确 |
| 10–20 分钟 | 推导数据结构和接口 | 能否从操作需要解释 map、链表和哈希索引 |
| 20–45 分钟 | 写 STL 版的撮合、撤单和改单 | 买卖共用一个循环，数量和索引同步更新，累计成交量不丢 |
| 45–60 分钟 | 跑边界测试，讨论一个优化方向 | 能否用反例验证规则，并说出优化依赖的前提 |

第二次练习换上对象池，第三次加入开放寻址哈希表和价位数组，每一步都重跑同一组测试。如果面试已经给了题面、框架和测试，以面试官的要求为准，不要为了展示完整路线而放弃能运行的主逻辑。

## 评分：怎样算答得好

| 方面 | 强 | 一般 | 弱 |
|---|---|---|---|
| 需求对齐 | 主动问清成交价、改单语义、id 范围等，说出每条影响代码的哪里，并写成注释 | 问了一些，但说不出为什么要问 | 直接开始写类和成员，写到一半回头改 |
| 数据结构 | 给出基线和复杂度，再按部件讲低延迟做法、前提和代价，能用数据说明什么时候值得 | 知道对象池、开放寻址等名词，说不清前提 | 结构不完整，或撤单要遍历整本簿 |
| 写代码 | 测试按阶段逐步通过，两侧共用代码，边写边说 | 能过测试，但代码重复、结构混乱 | 测试过不了，或卡住时不说话 |
| 测试与正确性 | 说出不变量、差分测试、sanitizer，以及失败后怎样缩小输入 | 只说「多写几个用例」 | 不考虑边界情况 |
| 深度 | 追问能说出语义、改动和代价，提到尾部延迟、确定性、单线程撮合 | 能回答一部分 | 停留在 LeetCode 层面 |

## 附录 A：基础类型与完整 STL 基线

将前面的 `types.hpp`（见「第一版：单簿的 STL 实现」）与下面的 `stl_book.hpp` 放在同一目录即可编译。它完整包含 `GTC`/`IOC`、撤单与总数量改单，作为后续优化的对照。默认不限制活跃订单数；可传入 `capacity`，使 CLI 对照测试与固定池版本采用相同容量规则。正文节选与附录是同一实现，不要重复粘贴。

<details markdown="1">
<summary>stl_book.hpp</summary>

```cpp title="stl_book.hpp"
#pragma once
#include <cstddef>
#include "types.hpp"
#include <algorithm>
#include <functional>
#include <iterator>
#include <list>
#include <limits>
#include <map>
#include <optional>
#include <unordered_map>

template<class Listener>
class StlBook {
    struct Order {
        OrderId id;
        Side side;
        Price price;
        Quantity leaves;
        Quantity cum;
    };
    struct Level {
        std::list<Order> orders;
        Volume total = 0;
    };
    using Position = typename std::list<Order>::iterator;

public:
    explicit StlBook(Listener& listener,
                     std::size_t capacity = std::numeric_limits<std::size_t>::max())
        : listener_(listener), capacity_(capacity) {}
    StlBook(const StlBook&) = delete;
    StlBook& operator=(const StlBook&) = delete;
    StlBook(StlBook&&) = delete;
    StlBook& operator=(StlBook&&) = delete;

    Result add_order(OrderId id, Side side, TimeInForce tif,
                     Price price, Quantity quantity) {
        if (quantity == 0) return Result::InvalidQuantity;
        if (lookup_.contains(id)) return Result::DuplicateId;
        return submit(id, side, tif, price, quantity, 0);
    }

    Result cancel_order(OrderId id) {
        auto it = lookup_.find(id);
        if (it == lookup_.end()) return Result::UnknownId;
        Position pos = it->second;
        if (pos->side == Side::Buy) remove(bids_, pos);
        else remove(asks_, pos);
        lookup_.erase(it);
        return Result::Ok;
    }

    Result modify_order(OrderId id, Price new_price, Quantity new_total) {
        auto it = lookup_.find(id);
        if (it == lookup_.end()) return Result::UnknownId;
        Order& order = *it->second;
        if (new_total <= order.cum) return cancel_order(id);
        Quantity new_leaves = new_total - order.cum;

        if (new_price == order.price) {
            Level& level = order.side == Side::Buy
                ? bids_.at(order.price) : asks_.at(order.price);
            bool increase = new_leaves > order.leaves;
            level.total -= order.leaves;
            order.leaves = new_leaves;
            level.total += order.leaves;
            if (increase)
                level.orders.splice(level.orders.end(), level.orders, it->second);
            return Result::Ok;
        }

        Side side = order.side;
        Quantity cum = order.cum;
        cancel_order(id);
        return submit(id, side, TimeInForce::GTC, new_price, new_leaves, cum);
    }

    std::optional<Price> best_bid() const {
        if (bids_.empty()) return std::nullopt;
        return bids_.begin()->first;
    }
    std::optional<Price> best_ask() const {
        if (asks_.empty()) return std::nullopt;
        return asks_.begin()->first;
    }
    Volume bid_volume_at(Price price) const {
        auto it = bids_.find(price);
        return it == bids_.end() ? 0 : it->second.total;
    }
    Volume ask_volume_at(Price price) const {
        auto it = asks_.find(price);
        return it == asks_.end() ? 0 : it->second.total;
    }
    std::size_t active_order_count() const { return lookup_.size(); }
    bool contains(OrderId id) const { return lookup_.contains(id); }

    template<class F>
    void for_each_level(F&& f) const {
        for (const auto& [price, level] : bids_)
            f(Side::Buy, price, level.total, level.orders.size());
        for (const auto& [price, level] : asks_)
            f(Side::Sell, price, level.total, level.orders.size());
    }

private:
    Result submit(OrderId id, Side side, TimeInForce tif, Price price,
                  Quantity leaves, Quantity cum) {
        if (side == Side::Buy)
            match(id, price, leaves, cum, asks_, std::greater_equal<Price>{});
        else
            match(id, price, leaves, cum, bids_, std::less_equal<Price>{});

        if (leaves != 0 && tif == TimeInForce::GTC) {
            if (lookup_.size() == capacity_) return Result::CapacityExceeded;
            Level& level = side == Side::Buy ? bids_[price] : asks_[price];
            level.orders.push_back(Order{id, side, price, leaves, cum});
            level.total += leaves;
            lookup_.emplace(id, std::prev(level.orders.end()));
        }
        return Result::Ok;
    }

    template<class Book, class Cross>
    void match(OrderId id, Price price, Quantity& leaves, Quantity& cum,
               Book& opposite, Cross can_cross) {
        auto it = opposite.begin();
        while (leaves != 0 && it != opposite.end()) {
            if (!can_cross(price, it->first)) break;
            Level& level = it->second;
            while (leaves != 0 && !level.orders.empty()) {
                Order& resting = level.orders.front();
                OrderId resting_id = resting.id;
                Price match_price = it->first;
                Quantity traded = std::min(leaves, resting.leaves);
                leaves -= traded;
                cum += traded;
                resting.leaves -= traded;
                resting.cum += traded;
                level.total -= traded;
                if (resting.leaves == 0) {
                    lookup_.erase(resting_id);
                    level.orders.pop_front();
                }
                listener_.on_trade(Trade{.resting_id = resting_id, .incoming_id = id,
                                         .price = match_price, .quantity = traded});
            }
            if (level.orders.empty()) it = opposite.erase(it);
            else ++it;
        }
    }

    template<class Book>
    void remove(Book& book, Position pos) {
        auto it = book.find(pos->price);
        Level& level = it->second;
        level.total -= pos->leaves;
        level.orders.erase(pos);
        if (level.orders.empty()) book.erase(it);
    }

    Listener& listener_;
    std::size_t capacity_;
    std::map<Price, Level, std::greater<Price>> bids_;
    std::map<Price, Level, std::less<Price>> asks_;
    std::unordered_map<OrderId, Position> lookup_;
};
```

</details>

## 附录 B：对象池版、四步优化版与多品种外层

下面三个头文件分别对应：只替换侵入式对象池的过渡版 `pool_book.hpp`、完成全部四步优化（对象池 + 开放寻址 `IdMap` + 末尾存最优价的有序数组 + 容量预留）的 `fast_book.hpp`，以及可套用任意单簿模板的多品种路由 `multi_engine.hpp`。

<details markdown="1">
<summary>pool_book.hpp（第一步优化：对象池 + 下标侵入式链表）</summary>

```cpp title="pool_book.hpp"
#pragma once
#include <cstddef>
#include "types.hpp"
#include <algorithm>
#include <cassert>
#include <functional>
#include <map>
#include <optional>
#include <stdexcept>
#include <unordered_map>
#include <vector>

template<class Listener>
class PoolBook {
    using Index = std::uint32_t;
    static constexpr Index nil = UINT32_MAX;

    struct alignas(32) Node {
        OrderId id = 0;
        Price price = 0;
        Quantity leaves = 0;
        Quantity cum = 0;
        Index prev = nil;
        Index next = nil;
    };
    static_assert(sizeof(Node) == 32);

    struct Level {
        Index head = nil;
        Index tail = nil;
        Volume total = 0;
    };
    struct Locator { Index index; Side side; };

public:
    explicit PoolBook(Listener& listener, std::size_t capacity = 1024)
        : listener_(listener), nodes_(checked_capacity(capacity)) {
        free_.reserve(capacity);
        for (std::size_t i = capacity; i != 0; --i)
            free_.push_back(static_cast<Index>(i - 1));
        lookup_.reserve(capacity);
    }
    PoolBook(const PoolBook&) = delete;
    PoolBook& operator=(const PoolBook&) = delete;
    PoolBook(PoolBook&&) = delete;
    PoolBook& operator=(PoolBook&&) = delete;

    Result add_order(OrderId id, Side side, TimeInForce tif,
                     Price price, Quantity quantity) {
        if (quantity == 0) return Result::InvalidQuantity;
        if (lookup_.contains(id)) return Result::DuplicateId;
        return submit(id, side, tif, price, quantity, 0);
    }

    Result cancel_order(OrderId id) {
        auto it = lookup_.find(id);
        if (it == lookup_.end()) return Result::UnknownId;
        Index index = it->second.index;
        Side side = it->second.side;
        if (side == Side::Buy) remove(bids_, index);
        else remove(asks_, index);
        lookup_.erase(it);
        free_.push_back(index);
        return Result::Ok;
    }

    Result modify_order(OrderId id, Price new_price, Quantity new_total) {
        auto it = lookup_.find(id);
        if (it == lookup_.end()) return Result::UnknownId;
        Index index = it->second.index;
        Side side = it->second.side;
        Node& node = nodes_[index];
        if (new_total <= node.cum) return cancel_order(id);
        Quantity new_leaves = new_total - node.cum;

        if (new_price == node.price) {
            Level& level = side == Side::Buy
                ? bids_.at(node.price) : asks_.at(node.price);
            bool increase = new_leaves > node.leaves;
            if (increase) unlink(level, index);
            level.total -= node.leaves;
            node.leaves = new_leaves;
            if (increase) append(level, index);
            else level.total += node.leaves;
            return Result::Ok;
        }

        Quantity cum = node.cum;
        cancel_order(id); // 归还一个槽位，足够改价后的剩余量重新挂单
        return submit(id, side, TimeInForce::GTC, new_price, new_leaves, cum);
    }

    std::optional<Price> best_bid() const {
        if (bids_.empty()) return std::nullopt;
        return bids_.begin()->first;
    }
    std::optional<Price> best_ask() const {
        if (asks_.empty()) return std::nullopt;
        return asks_.begin()->first;
    }
    Volume bid_volume_at(Price price) const {
        auto it = bids_.find(price);
        return it == bids_.end() ? 0 : it->second.total;
    }
    Volume ask_volume_at(Price price) const {
        auto it = asks_.find(price);
        return it == asks_.end() ? 0 : it->second.total;
    }
    std::size_t active_order_count() const { return lookup_.size(); }
    std::size_t free_pool_slots() const { return free_.size(); }
    bool contains(OrderId id) const { return lookup_.contains(id); }

    template<class F>
    void for_each_level(F&& f) const {
        auto visit = [&](Side side, const auto& book) {
            for (const auto& [price, level] : book) {
                std::size_t count = 0;
                for (Index i = level.head; i != nil; i = nodes_[i].next) ++count;
                f(side, price, level.total, count);
            }
        };
        visit(Side::Buy, bids_);
        visit(Side::Sell, asks_);
    }

    bool check() const {
        if (!bids_.empty() && !asks_.empty()
            && bids_.begin()->first >= asks_.begin()->first) return false;
        std::vector<bool> seen(nodes_.size(), false);
        std::size_t active = 0;
        auto visit = [&](Side side, const auto& book) {
            for (const auto& [price, level] : book) {
                if (level.head == nil || level.tail == nil) return false;
                Volume total = 0;
                Index previous = nil;
                for (Index i = level.head; i != nil; i = nodes_[i].next) {
                    if (i >= nodes_.size() || seen[i]) return false;
                    seen[i] = true;
                    const Node& node = nodes_[i];
                    if (node.prev != previous || node.price != price || node.leaves == 0)
                        return false;
                    if (Volume(node.cum) + node.leaves > UINT32_MAX) return false;
                    auto it = lookup_.find(node.id);
                    if (it == lookup_.end() || it->second.index != i || it->second.side != side)
                        return false;
                    total += node.leaves;
                    previous = i;
                    ++active;
                }
                if (previous != level.tail || total != level.total) return false;
            }
            return true;
        };
        if (!visit(Side::Buy, bids_) || !visit(Side::Sell, asks_)) return false;
        if (active != lookup_.size()) return false;
        for (Index i : free_) {
            if (i >= nodes_.size() || seen[i]) return false;
            seen[i] = true;
        }
        return active + free_.size() == nodes_.size();
    }

private:
    static std::size_t checked_capacity(std::size_t capacity) {
        if (capacity > nil) throw std::length_error("pool exceeds index range");
        return capacity;
    }

    Result submit(OrderId id, Side side, TimeInForce tif, Price price,
                  Quantity leaves, Quantity cum) {
        if (side == Side::Buy)
            match(id, price, leaves, cum, asks_, std::greater_equal<Price>{});
        else
            match(id, price, leaves, cum, bids_, std::less_equal<Price>{});

        if (leaves == 0 || tif == TimeInForce::IOC) return Result::Ok;
        if (free_.empty()) return Result::CapacityExceeded;

        Index index = free_.back();
        free_.pop_back();
        nodes_[index] = Node{id, price, leaves, cum, nil, nil};
        Level& level = side == Side::Buy ? bids_[price] : asks_[price];
        append(level, index);
        lookup_.emplace(id, Locator{index, side});
        return Result::Ok;
    }

    template<class Book, class Cross>
    void match(OrderId id, Price price, Quantity& leaves, Quantity& cum,
               Book& opposite, Cross can_cross) {
        auto it = opposite.begin();
        while (leaves != 0 && it != opposite.end()) {
            if (!can_cross(price, it->first)) break;
            Level& level = it->second;
            while (leaves != 0 && level.head != nil) {
                Index index = level.head;
                Node& resting = nodes_[index];
                OrderId resting_id = resting.id;
                Price match_price = it->first;
                Quantity traded = std::min(leaves, resting.leaves);
                leaves -= traded;
                cum += traded;
                resting.leaves -= traded;
                resting.cum += traded;
                level.total -= traded;
                if (resting.leaves == 0) {
                    lookup_.erase(resting_id);
                    unlink(level, index);
                    free_.push_back(index);
                }
                listener_.on_trade(Trade{.resting_id = resting_id, .incoming_id = id,
                                         .price = match_price, .quantity = traded});
            }
            if (level.head == nil) it = opposite.erase(it);
            else ++it;
        }
    }

    void append(Level& level, Index index) {
        Node& node = nodes_[index];
        node.prev = level.tail;
        node.next = nil;
        if (level.tail != nil) nodes_[level.tail].next = index;
        else level.head = index;
        level.tail = index;
        level.total += node.leaves;
    }
    void unlink(Level& level, Index index) {
        Node& node = nodes_[index];
        if (node.prev != nil) nodes_[node.prev].next = node.next;
        else level.head = node.next;
        if (node.next != nil) nodes_[node.next].prev = node.prev;
        else level.tail = node.prev;
        node.prev = node.next = nil;
    }
    template<class Book>
    void remove(Book& book, Index index) {
        auto it = book.find(nodes_[index].price);
        Level& level = it->second;
        level.total -= nodes_[index].leaves;
        unlink(level, index);
        if (level.head == nil) book.erase(it);
    }

    Listener& listener_;
    std::vector<Node> nodes_;
    std::vector<Index> free_;
    std::map<Price, Level, std::greater<Price>> bids_;
    std::map<Price, Level, std::less<Price>> asks_;
    std::unordered_map<OrderId, Locator> lookup_;
};
```

</details>

<details markdown="1">
<summary>fast_book.hpp（四步优化合体版：对象池 + IdMap + 末尾最优价有序数组 + 预留容量）</summary>

```cpp title="fast_book.hpp"
#pragma once
#include <cstddef>
#include "types.hpp"
#include <algorithm>
#include <bit>
#include <cassert>
#include <limits>
#include <optional>
#include <ranges>
#include <stdexcept>
#include <vector>

// 开放寻址、线性探测哈希表：Fibonacci 散列 + 回移删除（不留墓碑）。
template<class Value>
class IdMap {
public:
    static constexpr OrderId empty_key = UINT64_MAX;

    explicit IdMap(std::size_t expected = 1024) {
        std::size_t cap = 16;
        while (cap / 2 < expected) {
            if (cap > std::numeric_limits<std::size_t>::max() / 2)
                throw std::length_error("hash capacity overflow");
            cap *= 2;
        }
        slots_.resize(cap);
        shift_ = 64 - std::countr_zero(cap);
    }

    const Value* find(OrderId id) const noexcept {
        if (id == empty_key) return last_id_ ? &*last_id_ : nullptr;
        for (std::size_t i = home(id);; i = next(i)) {
            if (slots_[i].id == id) return &slots_[i].val;
            if (slots_[i].id == empty_key) return nullptr;
        }
    }

    bool contains(OrderId id) const noexcept { return find(id) != nullptr; }

    bool insert(OrderId id, Value val) {
        // 空槽哨兵也是合法 id，单独存放，不占普通探测槽位。
        if (id == empty_key) {
            if (last_id_) return false;
            last_id_ = val;
            ++size_;
            return true;
        }
        if (contains(id)) return false;
        if (size_ >= slots_.size() / 2) grow();
        std::size_t i = home(id);
        for (; slots_[i].id != empty_key; i = next(i))
            if (slots_[i].id == id) return false;
        slots_[i] = Slot{id, val};
        ++size_;
        return true;
    }

    void erase(OrderId id) noexcept {
        if (id == empty_key) {
            if (last_id_) { last_id_.reset(); --size_; }
            return;
        }
        std::size_t i = home(id);
        while (slots_[i].id != id) {
            if (slots_[i].id == empty_key) return;
            i = next(i);
        }
        for (std::size_t j = next(i); slots_[j].id != empty_key; j = next(j)) {
            std::size_t h = home(slots_[j].id);
            if (((j - h) & mask()) >= ((j - i) & mask())) {
                slots_[i] = slots_[j];
                i = j;
            }
        }
        slots_[i].id = empty_key;
        --size_;
    }

    std::size_t size() const noexcept { return size_; }

private:
    struct Slot {
        OrderId id = empty_key;
        Value val{};
    };
    std::size_t mask() const noexcept { return slots_.size() - 1; }
    std::size_t next(std::size_t i) const noexcept { return (i + 1) & mask(); }
    std::size_t home(OrderId id) const noexcept {
        return ((id + 1) * 0x9E3779B97F4A7C15ull) >> shift_;
    }
    void grow() {
        if (slots_.size() > slots_.max_size() / 2)
            throw std::length_error("hash capacity overflow");
        std::vector<Slot> old(slots_.size() * 2);
        old.swap(slots_);
        --shift_;
        for (const Slot& s : old) {
            if (s.id == empty_key) continue;
            std::size_t i = home(s.id);
            while (slots_[i].id != empty_key) i = next(i);
            slots_[i] = s;
        }
    }

    std::vector<Slot> slots_;
    std::optional<Value> last_id_; // UINT64_MAX 对应的值
    std::size_t size_ = 0;
    int shift_ = 60;
};

template<class Listener>
class FastBook {
    using Index = std::uint32_t;
    static constexpr Index nil = UINT32_MAX;

    struct alignas(32) Node {
        OrderId id = 0;
        Price price = 0;
        Quantity leaves = 0;
        Quantity cum = 0;
        Index prev = nil;
        Index next = nil;
    };
    static_assert(sizeof(Node) == 32);

    struct Level {
        Price price = 0;
        Volume total = 0;
        Index head = nil;
        Index tail = nil;
        std::uint32_t count = 0;
    };
    struct Locator { Index index = nil; Side side = Side::Buy; };

public:
    explicit FastBook(Listener& listener, std::size_t capacity = 1024,
                      std::size_t expected_levels = 256)
        : listener_(listener),
          nodes_(checked_capacity(capacity)),
          lookup_(capacity) {
        free_.reserve(capacity);
        for (std::size_t i = capacity; i != 0; --i)
            free_.push_back(static_cast<Index>(i - 1));
        bids_.reserve(expected_levels);
        asks_.reserve(expected_levels);
    }
    FastBook(const FastBook&) = delete;
    FastBook& operator=(const FastBook&) = delete;
    FastBook(FastBook&&) = delete;
    FastBook& operator=(FastBook&&) = delete;

    Result add_order(OrderId id, Side side, TimeInForce tif,
                     Price price, Quantity quantity) {
        if (quantity == 0) return Result::InvalidQuantity;
        if (lookup_.contains(id)) return Result::DuplicateId;
        if (side == Side::Buy)
            return submit<Side::Buy>(id, tif, price, quantity, 0);
        return submit<Side::Sell>(id, tif, price, quantity, 0);
    }

    Result cancel_order(OrderId id) {
        const Locator* loc = lookup_.find(id);
        if (!loc) return Result::UnknownId;
        Index index = loc->index;
        Side side = loc->side;
        if (side == Side::Buy) remove<Side::Buy>(bids_, index);
        else remove<Side::Sell>(asks_, index);
        lookup_.erase(id);
        free_.push_back(index);
        return Result::Ok;
    }

    Result modify_order(OrderId id, Price new_price, Quantity new_total) {
        const Locator* loc = lookup_.find(id);
        if (!loc) return Result::UnknownId;
        Index index = loc->index;
        Side side = loc->side;
        Node& node = nodes_[index];
        if (new_total <= node.cum) return cancel_order(id);
        Quantity new_leaves = new_total - node.cum;

        if (new_price == node.price) {
            Level& level = side == Side::Buy
                ? *lower<Side::Buy>(bids_, node.price)
                : *lower<Side::Sell>(asks_, node.price);
            bool increase = new_leaves > node.leaves;
            if (increase) unlink(level, index);
            level.total -= node.leaves;
            node.leaves = new_leaves;
            if (increase) append(level, index);
            else level.total += node.leaves;
            return Result::Ok;
        }

        Quantity cum = node.cum;
        cancel_order(id);
        if (side == Side::Buy)
            return submit<Side::Buy>(id, TimeInForce::GTC, new_price, new_leaves, cum);
        return submit<Side::Sell>(id, TimeInForce::GTC, new_price, new_leaves, cum);
    }

    std::optional<Price> best_bid() const noexcept {
        if (bids_.empty()) return std::nullopt;
        return bids_.back().price;
    }
    std::optional<Price> best_ask() const noexcept {
        if (asks_.empty()) return std::nullopt;
        return asks_.back().price;
    }
    Volume bid_volume_at(Price price) const noexcept {
        auto it = lower<Side::Buy>(bids_, price);
        return (it != bids_.end() && it->price == price) ? it->total : 0;
    }
    Volume ask_volume_at(Price price) const noexcept {
        auto it = lower<Side::Sell>(asks_, price);
        return (it != asks_.end() && it->price == price) ? it->total : 0;
    }
    std::size_t active_order_count() const noexcept { return lookup_.size(); }
    std::size_t free_pool_slots() const noexcept { return free_.size(); }
    bool contains(OrderId id) const noexcept { return lookup_.contains(id); }

    template<class F>
    void for_each_level(F&& f) const {
        for (auto it = bids_.rbegin(); it != bids_.rend(); ++it)
            f(Side::Buy, it->price, it->total, std::size_t(it->count));
        for (auto it = asks_.rbegin(); it != asks_.rend(); ++it)
            f(Side::Sell, it->price, it->total, std::size_t(it->count));
    }

    bool check() const {
        if (!bids_.empty() && !asks_.empty()
            && bids_.back().price >= asks_.back().price) return false;
        std::vector<bool> seen(nodes_.size(), false);
        std::size_t active = 0;
        auto visit = [&]<Side S>(const std::vector<Level>& levels) {
            for (std::size_t k = 0; k < levels.size(); ++k) {
                const Level& level = levels[k];
                if (k > 0 && !better<S>(level.price, levels[k - 1].price)) return false;
                if (level.head == nil || level.tail == nil || level.count == 0) return false;
                Volume total = 0;
                std::uint32_t count = 0;
                Index previous = nil;
                for (Index i = level.head; i != nil; i = nodes_[i].next) {
                    if (i >= nodes_.size() || seen[i]) return false;
                    seen[i] = true;
                    const Node& node = nodes_[i];
                    if (node.prev != previous || node.price != level.price || node.leaves == 0)
                        return false;
                    if (Volume(node.cum) + node.leaves > UINT32_MAX) return false;
                    const Locator* loc = lookup_.find(node.id);
                    if (!loc || loc->index != i || loc->side != S) return false;
                    total += node.leaves;
                    previous = i;
                    ++count;
                    ++active;
                }
                if (previous != level.tail || total != level.total || count != level.count)
                    return false;
            }
            return true;
        };
        if (!visit.template operator()<Side::Buy>(bids_)) return false;
        if (!visit.template operator()<Side::Sell>(asks_)) return false;
        if (active != lookup_.size()) return false;
        for (Index i : free_) {
            if (i >= nodes_.size() || seen[i]) return false;
            seen[i] = true;
        }
        return active + free_.size() == nodes_.size();
    }

private:
    static std::size_t checked_capacity(std::size_t capacity) {
        if (capacity > nil) throw std::length_error("pool exceeds index range");
        return capacity;
    }

    template<Side S>
    static constexpr bool better(Price a, Price b) noexcept {
        if constexpr (S == Side::Buy) return a > b;
        else return a < b;
    }

    template<Side S>
    static constexpr bool crosses(Price incoming, Price resting) noexcept {
        if constexpr (S == Side::Buy) return incoming >= resting;
        else return incoming <= resting;
    }

    // 价位从差到好排列，最优价在 back()；返回第一个不差于 px 的位置
    template<Side S, class Vec>
    static auto lower(Vec& levels, Price px) noexcept {
        return std::ranges::partition_point(levels, [&](const Level& l) {
            return better<S>(px, l.price);
        });
    }

    template<Side S>
    Result submit(OrderId id, TimeInForce tif, Price price,
                  Quantity leaves, Quantity cum) {
        auto& opp = S == Side::Buy ? asks_ : bids_;
        while (leaves != 0 && !opp.empty()) {
            Level& best = opp.back();
            if (!crosses<S>(price, best.price)) break;
            while (leaves != 0 && best.head != nil) {
                Index index = best.head;
                Node& resting = nodes_[index];
                OrderId resting_id = resting.id;
                Price match_price = best.price;
                Quantity traded = std::min(leaves, resting.leaves);
                leaves -= traded;
                cum += traded;
                resting.leaves -= traded;
                resting.cum += traded;
                best.total -= traded;
                if (resting.leaves == 0) {
                    lookup_.erase(resting_id);
                    unlink(best, index);
                    free_.push_back(index);
                }
                listener_.on_trade(Trade{.resting_id = resting_id, .incoming_id = id,
                                         .price = match_price, .quantity = traded});
            }
            if (best.head == nil) opp.pop_back(); // 吃空最优档直接弹出末尾，零元素移动
        }

        if (leaves == 0 || tif == TimeInForce::IOC) return Result::Ok;
        if (free_.empty()) return Result::CapacityExceeded;

        Index index = free_.back();
        free_.pop_back();
        nodes_[index] = Node{id, price, leaves, cum, nil, nil};

        auto& own = S == Side::Buy ? bids_ : asks_;
        auto it = lower<S>(own, price);
        if (it == own.end() || it->price != price)
            it = own.insert(it, Level{price, 0, nil, nil, 0});
        append(*it, index);
        lookup_.insert(id, Locator{index, S});
        return Result::Ok;
    }

    void append(Level& level, Index index) noexcept {
        Node& node = nodes_[index];
        node.prev = level.tail;
        node.next = nil;
        if (level.tail != nil) nodes_[level.tail].next = index;
        else level.head = index;
        level.tail = index;
        level.total += node.leaves;
        ++level.count;
    }

    void unlink(Level& level, Index index) noexcept {
        Node& node = nodes_[index];
        if (node.prev != nil) nodes_[node.prev].next = node.next;
        else level.head = node.next;
        if (node.next != nil) nodes_[node.next].prev = node.prev;
        else level.tail = node.prev;
        node.prev = node.next = nil;
        --level.count;
    }

    template<Side S>
    void remove(std::vector<Level>& book, Index index) noexcept {
        auto it = lower<S>(book, nodes_[index].price);
        it->total -= nodes_[index].leaves;
        unlink(*it, index);
        if (it->head == nil) book.erase(it);
    }

    Listener& listener_;
    std::vector<Node> nodes_;
    std::vector<Index> free_;
    std::vector<Level> bids_; // 升序排列，最高买价在 back()
    std::vector<Level> asks_; // 降序排列，最低卖价在 back()
    IdMap<Locator> lookup_;
};
```

</details>

<details markdown="1">
<summary>multi_engine.hpp（多品种外层路由，默认使用 FastBook）</summary>

```cpp title="multi_engine.hpp"
#pragma once
#include <cstddef>
#include "fast_book.hpp"
#include "pool_book.hpp"
#include <memory>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>

template<class Listener, template<class> class Book = FastBook>
class MultiEngine {
    struct BookListener {
        std::string symbol;
        Listener& downstream;
        void on_trade(const Trade& trade) {
            downstream.on_trade(std::string_view(symbol), trade);
        }
    };
    struct Entry {
        BookListener listener;
        Book<BookListener> book;
        Entry(std::string symbol, Listener& downstream, std::size_t capacity)
            : listener{std::move(symbol), downstream}, book(listener, capacity) {}
    };

public:
    explicit MultiEngine(Listener& listener) : listener_(listener) {}
    MultiEngine(const MultiEngine&) = delete;
    MultiEngine& operator=(const MultiEngine&) = delete;
    MultiEngine(MultiEngine&&) = delete;
    MultiEngine& operator=(MultiEngine&&) = delete;

    bool register_symbol(std::string symbol, std::size_t capacity) {
        if (symbol.empty() || books_.contains(symbol)) return false;
        auto entry = std::make_unique<Entry>(symbol, listener_, capacity);
        books_.emplace(std::move(symbol), std::move(entry));
        return true;
    }
    Result add_order(const std::string& symbol, OrderId id, Side side,
                     TimeInForce tif, Price price, Quantity quantity) {
        auto it = books_.find(symbol);
        if (it == books_.end()) return Result::UnknownSymbol;
        return it->second->book.add_order(id, side, tif, price, quantity);
    }
    Result cancel_order(const std::string& symbol, OrderId id) {
        auto it = books_.find(symbol);
        if (it == books_.end()) return Result::UnknownSymbol;
        return it->second->book.cancel_order(id);
    }
    Result modify_order(const std::string& symbol, OrderId id,
                        Price price, Quantity total) {
        auto it = books_.find(symbol);
        if (it == books_.end()) return Result::UnknownSymbol;
        return it->second->book.modify_order(id, price, total);
    }

private:
    Listener& listener_;
    std::unordered_map<std::string, std::unique_ptr<Entry>> books_;
};
```

</details>

## 附录 C：三方差分与边界测试套件

将 `tests.cpp` 与上述头文件放在同一目录，保留断言（不要加 `-DNDEBUG`）并开启 ASan/UBSan 编译运行：

```bash
clang++ -std=c++20 -Wall -Wextra -Wconversion -pedantic \
  -O1 -fsanitize=address,undefined tests.cpp -o tests
./tests
```

预期输出：

```text
examples (StlBook, PoolBook, FastBook), capacity, multi-symbol: passed
3-way differential: 100 seeds x 1000 messages passed
hash collisions, wraparound, growth, full-range ids: passed
```

<details markdown="1">
<summary>tests.cpp</summary>

```cpp title="tests.cpp"
#include "stl_book.hpp"
#include "pool_book.hpp"
#include "fast_book.hpp"
#include "multi_engine.hpp"
#include <cassert>
#include <iostream>
#include <limits>
#include <random>
#include <string>
#include <tuple>
#include <unordered_map>
#include <vector>

constexpr auto Buy = Side::Buy;
constexpr auto Sell = Side::Sell;
constexpr auto GTC = TimeInForce::GTC;
constexpr auto IOC = TimeInForce::IOC;
constexpr auto Ok = Result::Ok;

struct Recorder {
    std::vector<Trade> trades;
    void on_trade(const Trade& trade) { trades.push_back(trade); }
};

template<template<class> class Book>
void examples() {
    // 1. 多价位、同价 FIFO、成交价取被动挂单价（Price Improvement）
    {
        Recorder r; Book<Recorder> b(r);
        assert(b.add_order(1, Sell, GTC, 100, 3) == Ok);
        b.add_order(2, Sell, GTC, 100, 4);
        b.add_order(3, Sell, GTC, 101, 10);
        b.add_order(4, Buy, GTC, 102, 8);
        assert((r.trades == std::vector<Trade>{{1,4,100,3},{2,4,100,4},{3,4,101,1}}));
        assert(b.best_ask() == 101 && b.ask_volume_at(101) == 9);
    }
    // 2. 撤掉中间、队首、最后一笔；空价位必须清除（绝不留下幽灵空价位）
    {
        Recorder r; Book<Recorder> b(r);
        for (OrderId id : {OrderId{1}, OrderId{2}, OrderId{3}})
            b.add_order(id, Sell, GTC, 100, 2);
        assert(b.cancel_order(2) == Ok);
        b.cancel_order(1);
        b.cancel_order(3);
        assert(!b.best_ask() && b.active_order_count() == 0);
        assert(b.cancel_order(3) == Result::UnknownId);
    }
    // 3. 同价减量保留队首优先级；同价加量失去时间优先排到队尾
    {
        Recorder r; Book<Recorder> b(r);
        b.add_order(1, Sell, GTC, 100, 3);
        b.add_order(2, Sell, GTC, 100, 4);
        b.modify_order(1, 100, 2);
        b.add_order(3, Buy, IOC, 100, 1);
        assert(r.trades.back().resting_id == 1);
        b.modify_order(1, 100, 6); // cum=1，新的剩余量为 5，挪到 #2 后面
        assert(b.ask_volume_at(100) == 9);
        b.add_order(4, Buy, IOC, 100, 4);
        assert(r.trades.back().resting_id == 2);
    }
    // 4. 在途成交竞态：迟到改单的新总量 <= 已成交量，自动撤掉剩余挂单防超买
    {
        Recorder r; Book<Recorder> b(r);
        b.add_order(1, Buy, GTC, 100, 100);
        b.add_order(2, Sell, IOC, 100, 80);
        assert(b.modify_order(1, 100, 60) == Ok);
        assert(!b.best_bid());
    }
    // 5. 主动方先成交一部分再挂单，必须保留累计成交量 cum
    {
        Recorder r; Book<Recorder> b(r);
        b.add_order(1, Sell, GTC, 100, 3);
        b.add_order(2, Buy, GTC, 100, 10);
        b.modify_order(2, 100, 5);
        assert(b.bid_volume_at(100) == 2);
    }
    // 6. 改价后立即主动成交，再次改单仍累加整笔订单的累计成交量
    {
        Recorder r; Book<Recorder> b(r);
        b.add_order(1, Buy, GTC, 99, 10);
        b.add_order(2, Sell, IOC, 99, 2);
        b.add_order(3, Sell, GTC, 101, 3);
        assert(b.modify_order(1, 101, 10) == Ok);
        assert(b.bid_volume_at(101) == 5);
        b.modify_order(1, 101, 6);
        assert(b.bid_volume_at(101) == 1);
    }
    // 7. IOC 余量自动销毁；id=0 合法；离簿后的 id 允许复用
    {
        Recorder r; Book<Recorder> b(r);
        b.add_order(0, Sell, GTC, 100, 2);
        assert(b.add_order(0, Buy, GTC, 100, 1) == Result::DuplicateId);
        assert(b.add_order(2, Buy, IOC, 100, 5) == Ok);
        assert(!b.best_bid() && !b.best_ask());
        assert(b.add_order(2, Buy, GTC, 99, 1) == Ok);
        assert(b.add_order(3, Buy, GTC, 99, 0) == Result::InvalidQuantity);
        assert(b.modify_order(2, 99, 0) == Ok);
    }
    // 8. 负价格与零价格可用；价位聚合总量超过 32 位不溢出
    {
        Recorder r; Book<Recorder> b(r);
        b.add_order(1, Sell, GTC, -10, UINT32_MAX);
        b.add_order(2, Sell, GTC, -10, UINT32_MAX);
        assert(b.ask_volume_at(-10) == Volume(UINT32_MAX) * 2);
        b.add_order(3, Buy, IOC, 0, 1);
        assert(r.trades.back().price == -10);
        assert(b.modify_order(2, 0, 1) == Ok);
    }
    // 9. id 的两个端点都合法，哈希表空槽标记不能改变业务语义。
    {
        Recorder r; Book<Recorder> b(r);
        assert(b.add_order(UINT64_MAX, Sell, GTC, 100, 5) == Ok);
        assert(b.add_order(0, Sell, GTC, 100, 3) == Ok);
        assert(b.add_order(UINT64_MAX, Buy, IOC, 100, 1) == Result::DuplicateId);
        assert(b.modify_order(UINT64_MAX, 100, 6) == Ok);
        assert(b.add_order(1, Buy, IOC, 100, 6) == Ok);
        assert((r.trades == std::vector<Trade>{{0,1,100,3},{UINT64_MAX,1,100,3}}));
        assert(b.cancel_order(UINT64_MAX) == Ok);
        assert(b.active_order_count() == 0);
        assert(b.add_order(UINT64_MAX, Buy, GTC, 99, 1) == Ok);
    }
}

template<template<class> class Book>
void capacity_examples() {
    for (Quantity qty : {5u, 15u}) {
        Recorder r; Book<Recorder> b(r, 1);
        b.add_order(1, Sell, GTC, 100, 10);
        assert(b.add_order(2, Buy, GTC, 100, qty) == Ok);
        assert(r.trades.size() == 1 && b.check());
    }
    Recorder r; Book<Recorder> b(r, 1);
    b.add_order(1, Sell, GTC, 100, 10);
    assert(b.add_order(2, Buy, GTC, 99, 15) == Result::CapacityExceeded);
    assert(r.trades.empty() && b.ask_volume_at(100) == 10);
    assert(b.modify_order(1, 101, 8) == Ok);
    assert(b.ask_volume_at(101) == 8 && b.check());
    Recorder z; Book<Recorder> empty(z, 0);
    assert(empty.add_order(1, Buy, IOC, 100, 1) == Ok);
    assert(empty.add_order(1, Buy, GTC, 100, 1) == Result::CapacityExceeded);
    assert(empty.check());
}

using LevelRow = std::tuple<Side, Price, Volume, std::size_t>;
auto snapshot(const auto& book) {
    std::vector<LevelRow> rows;
    book.for_each_level([&](Side side, Price px, Volume total, std::size_t count) {
        rows.emplace_back(side, px, total, count);
    });
    return rows;
}

void differential() {
    for (unsigned seed = 1; seed <= 100; ++seed) {
        std::mt19937 rng(seed);
        Recorder a, b, c;
        StlBook ref(a);
        PoolBook pool(b, 64);
        FastBook fast(c, 64, 16);
        for (int step = 0; step < 1000; ++step) {
            OrderId id = rng() % 40; // 含 id = 0
            Price px = Price(rng() % 11) - 5;
            Quantity qty = rng() % 21;
            Side side = rng() % 2 ? Buy : Sell;
            TimeInForce tif = rng() % 3 ? GTC : IOC;
            Result x, y, z;
            switch (rng() % 3) {
            case 0:
                x = ref.add_order(id, side, tif, px, qty);
                y = pool.add_order(id, side, tif, px, qty);
                z = fast.add_order(id, side, tif, px, qty);
                break;
            case 1:
                x = ref.cancel_order(id);
                y = pool.cancel_order(id);
                z = fast.cancel_order(id);
                break;
            default:
                x = ref.modify_order(id, px, qty);
                y = pool.modify_order(id, px, qty);
                z = fast.modify_order(id, px, qty);
                break;
            }
            assert(x == y && y == z);
            assert(a.trades == b.trades && b.trades == c.trades);
            auto snap = snapshot(ref);
            assert(snap == snapshot(pool) && snap == snapshot(fast));
            assert(ref.active_order_count() == pool.active_order_count());
            assert(ref.active_order_count() == fast.active_order_count());
            assert(pool.check() && fast.check());
            a.trades.clear(); b.trades.clear(); c.trades.clear();
        }
    }
}

void hash_examples() {
    IdMap<unsigned> map(1);
    // 初始 16 槽，故意把 7 个键放到末尾同一桶，跨数组边界探测。
    std::vector<OrderId> colliding;
    for (OrderId id = 0; colliding.size() < 7; ++id)
        if ((((id + 1) * 0x9E3779B97F4A7C15ull) >> 60) == 15)
            colliding.push_back(id);
    for (OrderId id : colliding) assert(map.insert(id, 7));
    map.erase(colliding[0]);
    map.erase(colliding[3]);
    for (OrderId id : colliding)
        assert(map.contains(id) == (id != colliding[0] && id != colliding[3]));
    map.erase(UINT64_MAX); // 删除未知 id 是空操作

    IdMap<unsigned> actual(1);
    std::unordered_map<OrderId, unsigned> expected;
    std::mt19937 rng(2026);
    for (int step = 0; step < 20000; ++step) {
        OrderId id = rng() % 256;
        if (rng() % 8 == 0) id = UINT64_MAX;
        unsigned value = static_cast<unsigned>(step);
        switch (rng() % 3) {
        case 0:
            assert(actual.insert(id, value) == expected.emplace(id, value).second);
            break;
        case 1: actual.erase(id); expected.erase(id); break;
        default: {
            const unsigned* at = actual.find(id);
            auto it = expected.find(id);
            assert((at != nullptr) == (it != expected.end()));
            if (at) assert(*at == it->second);
        }
        }
        assert(actual.size() == expected.size());
        for (const auto& [key, v] : expected)
            assert(actual.find(key) && *actual.find(key) == v);
    }
}

void multiple_symbols() {
    struct MultiRecorder {
        std::vector<std::pair<std::string, Trade>> trades;
        void on_trade(std::string_view symbol, const Trade& trade) {
            trades.emplace_back(std::string(symbol), trade);
        }
    } r;
    MultiEngine<MultiRecorder, FastBook> engine(r);
    assert(engine.register_symbol("AAPL", 8));
    assert(engine.register_symbol("MSFT", 8));
    assert(!engine.register_symbol("AAPL", 8));
    engine.add_order("AAPL", 1, Sell, GTC, 100, 3);
    engine.add_order("MSFT", 1, Buy, GTC, 200, 3);
    assert(r.trades.empty());
    engine.add_order("AAPL", 2, Buy, IOC, 100, 2);
    assert(r.trades.size() == 1 && r.trades[0].first == "AAPL");
    assert((r.trades[0].second == Trade{1,2,100,2}));
    assert(engine.modify_order("AAPL", 1, 101, 3) == Ok);
    assert(engine.cancel_order("MSFT", 1) == Ok);
    assert(engine.cancel_order("AAPL", 1) == Ok);
    assert(engine.cancel_order("GOOG", 1) == Result::UnknownSymbol);
}

int main() {
    examples<StlBook>();
    examples<PoolBook>();
    examples<FastBook>();
    capacity_examples<PoolBook>();
    capacity_examples<FastBook>();
    differential();
    hash_examples();
    multiple_symbols();
    // CLI 的 STL 对照实现也启用相同的活跃订单容量。
    Recorder r; StlBook limited(r, 1);
    assert(limited.add_order(1, Buy, GTC, 99, 1) == Ok);
    assert(limited.add_order(2, Buy, GTC, 99, 1) == Result::CapacityExceeded);
    std::cout << "examples (StlBook, PoolBook, FastBook), capacity, multi-symbol: passed\n"
              << "3-way differential: 100 seeds x 1000 messages passed\n"
              << "hash collisions, wraparound, growth, full-range ids: passed\n";
}
```

</details>

## 附录 D：完整文本协议题面、22 个分阶段测试用例与命令行解答

现场上机题常给出标准输入输出的完整文本协议和一组黑盒用例，要求候选人分阶段让用例逐批通过。下面给出完整自拟题面、22 个分阶段测试用例、自动判题脚本 `run_tests.py`，以及直接复用前面 `fast_book.hpp` / `stl_book.hpp` 的命令行入口 `cli.cpp`（展示了无 `symbol` 撤改单的全局路由表 `route` 与全会话历史判重表 `used`）。

### 题面规范

从标准输入逐行读取空格分隔的消息，按顺序处理，实时向标准输出写出成交与拒单事件；输入结束后，按品种名字典序输出所有仍有挂单的订单簿快照。

| 消息 | 格式 | 含义 |
|---|---|---|
| 下单 | `INSERT <id> <symbol> <BUY\|SELL> <price> <qty>` | 提交一笔 GTC 限价单 |
| 改单 | `AMEND <id> <price> <qty>` | 修改挂单的价格与新的总数量（含已成交部分） |
| 撤单 | `CANCEL <id>` | 撤销当前在簿上的挂单 |

- 字段范围：`id` 为 64 位无符号正整数（包含 `UINT64_MAX`）；`symbol` 为非空大写字母串；合法 `price` 为正十进制数，整数部分 1–12 位，小数部分最多 2 位（如 `100`、`100.5`、`100.25` 合法，`100.123`、`1e2`、`.5`、`0` 非法）；合法 `qty` 为 `1` 到 `10^9` 的整数。空行忽略。
- 拒单检查顺序（命中第一条即输出 `REJECT <id> <原因>` 并忽略该消息）：
  1. `price` 或 `qty` 不合法：`INVALID`（被拒的 `INSERT` 不占用 `id`）。
  2. `INSERT` 的 `id` 曾被本次运行中任意一笔成功受理的 `INSERT` 用过（哪怕已全部成交或撤销）：`DUPLICATE_ID`。
  3. `AMEND` 或 `CANCEL` 的 `id` 当前不在任何订单簿上：`UNKNOWN_ID`。
  4. 有效新单需要挂单，但本品种活跃订单容量已满：`CAPACITY_EXCEEDED`。此时没有成交，不占用历史 id；释放容量后可用相同 id 重试。
- 撮合与改单规则：价格优先、时间优先，成交价取被动挂单价（保留两位小数输出）；`AMEND` 的新剩余量等于 `qty - cum`，不大于 0 时订单完结离簿（不输出事件），同价且新剩余量不大于原剩余量时原地减量保序，加量或改价等同于撤掉原单后携带原 `cum` 重新按同 ID 下单。
- 输出格式：

```text
TRADE <symbol> <price> <qty> <aggressor id> <resting id>
REJECT <id> <INVALID|DUPLICATE_ID|UNKNOWN_ID|CAPACITY_EXCEEDED>
BOOK <symbol>
BID <price> <total qty> <order count>     # 从最高买价到最低买价
ASK <price> <total qty> <order count>     # 从最低卖价到最高卖价
```

CLI 默认每个品种最多挂 1024 笔订单，两个实现使用同样限制。可用 `--capacity N` 调整；这个参数只限制同时活跃的订单数，历史判重表仍会增长。题面保证其余格式正确，解析层负责价格、数量的合法性，不承担通用协议解析器的职责。

### 分阶段推进顺序与 22 个测试用例

| 阶段 | 实现目标 | 对应测试编号 |
|---|---|---|
| 一 | `INSERT`、跨价撮合、多品种隔离与字典序快照 | 01–06 |
| 二 | `CANCEL`、队列中间删除与三种拒单顺序 | 07–09、17 |
| 三 | `AMEND` 总量语义、减量保序、加量队尾、在途超买撤单与主动单 `cum` 继承 | 10–16、18–22 |
| 四 | 容量拒单、重试、全局路由与最大 id 回归 | `cli_regressions.py` |

<details markdown="1">
<summary>tests.txt（22 个分阶段用例）</summary>

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
=== 13 AMEND 的数量是新的总数量：已成交 4，改成 6 只剩 2，减量保留时间优先
INSERT 1 AAPL SELL 100 10
INSERT 2 AAPL BUY 100 4
INSERT 3 AAPL SELL 100 5
AMEND 1 100 6
INSERT 4 AAPL BUY 100 7
---
TRADE AAPL 100.00 4 2 1
TRADE AAPL 100.00 2 4 1
TRADE AAPL 100.00 5 4 3
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
=== 18 新总量等于已成交量：订单结束，之后撤单返回未知 id
INSERT 1 AAPL SELL 100 10
INSERT 2 AAPL BUY 100 4
AMEND 1 100 4
CANCEL 1
---
TRADE AAPL 100.00 4 2 1
REJECT 1 UNKNOWN_ID
=== 19 新总量小于已成交量：订单同样结束，不撤销已有的成交
INSERT 1 AAPL SELL 100 10
INSERT 2 AAPL BUY 100 4
AMEND 1 100 3
INSERT 3 AAPL BUY 100 5
---
TRADE AAPL 100.00 4 2 1
BOOK AAPL
BID 100.00 5 1
=== 20 新总量大于原总量：加量失去时间优先
INSERT 1 AAPL SELL 100 10
INSERT 2 AAPL BUY 100 4
INSERT 3 AAPL SELL 100 5
AMEND 1 100 12
INSERT 4 AAPL BUY 100 6
---
TRADE AAPL 100.00 4 2 1
TRADE AAPL 100.00 5 4 3
TRADE AAPL 100.00 1 4 1
BOOK AAPL
ASK 100.00 7 1
=== 21 改价时已成交数量保留：之后再改单，剩余数量仍按原来的已成交量计算
INSERT 1 AAPL SELL 101 10
INSERT 2 AAPL BUY 101 4
AMEND 1 102 6
AMEND 1 102 5
INSERT 3 AAPL BUY 102 5
---
TRADE AAPL 101.00 4 2 1
TRADE AAPL 102.00 1 3 1
BOOK AAPL
BID 102.00 4 1
=== 22 主动方成交后挂单，它的已成交数量也要计入
INSERT 1 AAPL SELL 100 3
INSERT 2 AAPL BUY 100 10
AMEND 2 100 5
INSERT 3 AAPL SELL 100 9
---
TRADE AAPL 100.00 3 2 1
TRADE AAPL 100.00 2 3 2
BOOK AAPL
ASK 100.00 7 1
```

</details>

<details markdown="1">
<summary>run_tests.py（自动判题脚本）</summary>

```python title="run_tests.py"
# run_tests.py <可执行文件> [参数...]：逐个运行 tests.txt 里的用例，比较输出
import subprocess, sys, pathlib

text = (pathlib.Path(__file__).parent / "tests.txt").read_text()
failed = 0
for case in text.split("=== ")[1:]:
    head, body = case.split("\n", 1)
    inp, exp = body.split("---\n")
    run = subprocess.run(sys.argv[1:], input=inp, capture_output=True, text=True)
    out = run.stdout
    if run.returncode != 0 or out != exp:
        failed += 1
        print(f"FAIL {head}\n--- expected\n{exp}--- got\n{out}")
        if run.returncode != 0:
            print(f"exit={run.returncode}\n{run.stderr}")
total = text.count("=== ")
print(f"{total - failed}/{total} passed")
sys.exit(1 if failed else 0)
```

</details>

<details markdown="1">
<summary>cli.cpp（显式处理受理结果、全局路由与历史判重）</summary>

```cpp title="cli.cpp"
#include "fast_book.hpp"
#include "stl_book.hpp"
#include <algorithm>
#include <charconv>
#include <iostream>
#include <limits>
#include <memory>
#include <optional>
#include <ranges>
#include <sstream>
#include <string>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

inline constexpr Quantity kMaxCliQty = 1'000'000'000;

std::optional<Price> parse_price(std::string_view s) {
    Price v = 0;
    int int_digits = 0, frac_digits = -1;
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
    return v > 0 ? std::optional<Price>(v) : std::nullopt;
}

std::optional<Quantity> parse_qty(std::string_view s) {
    std::uint64_t v = 0;
    auto [end, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
    if (ec != std::errc{} || end != s.data() + s.size() || v == 0 || v > kMaxCliQty)
        return std::nullopt;
    return static_cast<Quantity>(v);
}

std::string format_price(Price p) {
    char frac[] = {'.', char('0' + p % 100 / 10), char('0' + p % 10), '\0'};
    return std::to_string(p / 100) + frac;
}

void print_reject(OrderId id, Result result) {
    const char* name = "INVALID";
    switch (result) {
    case Result::Ok: return;
    case Result::DuplicateId: name = "DUPLICATE_ID"; break;
    case Result::UnknownId: name = "UNKNOWN_ID"; break;
    case Result::CapacityExceeded: name = "CAPACITY_EXCEEDED"; break;
    default: break;
    }
    std::cout << "REJECT " << id << ' ' << name << '\n';
}

template<template<class> class Book>
int run_cli(std::size_t capacity) {
    IdMap<std::uint8_t> used(1 << 16);   // 全会话历史已受理 ID 集合
    IdMap<std::uint32_t> route(1 << 16); // 当前活跃挂单 ID -> 所在品种下标

    struct Entry {
        struct Sink {
            Entry* self = nullptr;
            IdMap<std::uint32_t>* route = nullptr;
            void on_trade(const Trade& t) {
                std::cout << "TRADE " << self->symbol << ' ' << format_price(t.price) << ' '
                          << t.quantity << ' ' << t.incoming_id << ' ' << t.resting_id << '\n';
                if (!self->book.contains(t.resting_id)) route->erase(t.resting_id);
            }
        };
        std::string symbol;
        Sink sink;
        Book<Sink> book;
        Entry(std::string sym, IdMap<std::uint32_t>& r, std::size_t capacity)
            : symbol(std::move(sym)), sink{this, &r}, book(sink, capacity) {}
    };

    std::vector<std::unique_ptr<Entry>> books;
    std::unordered_map<std::string, std::uint32_t> symbols;
    auto get_book = [&](const std::string& sym) -> std::uint32_t {
        if (auto it = symbols.find(sym); it != symbols.end()) return it->second;
        auto idx = static_cast<std::uint32_t>(books.size());
        books.push_back(std::make_unique<Entry>(sym, route, capacity));
        symbols.emplace(sym, idx);
        return idx;
    };

    std::string line, cmd, sym, side_str, px_str, qty_str;
    OrderId id = 0;
    while (std::getline(std::cin, line)) {
        std::istringstream in(line);
        if (!(in >> cmd)) continue;
        if (cmd == "INSERT") {
            in >> id >> sym >> side_str >> px_str >> qty_str;
            auto px = parse_price(px_str);
            auto qty = parse_qty(qty_str);
            if (!px || !qty || id == 0) {
                std::cout << "REJECT " << id << " INVALID\n";
                continue;
            }
            if (used.contains(id)) {
                std::cout << "REJECT " << id << " DUPLICATE_ID\n";
                continue;
            }
            std::uint32_t b = get_book(sym);
            Side side = side_str == "BUY" ? Side::Buy : Side::Sell;
            Result result = books[b]->book.add_order(id, side, TimeInForce::GTC, *px, *qty);
            if (result != Result::Ok) {
                print_reject(id, result);
                continue;
            }
            used.insert(id, 1); // 受理成功才占用历史 id，容量拒单不占用
            if (books[b]->book.contains(id)) route.insert(id, b);
        } else if (cmd == "AMEND") {
            in >> id >> px_str >> qty_str;
            auto px = parse_price(px_str);
            auto qty = parse_qty(qty_str);
            if (!px || !qty) {
                std::cout << "REJECT " << id << " INVALID\n";
                continue;
            }
            const std::uint32_t* b = route.find(id);
            if (!b) {
                std::cout << "REJECT " << id << " UNKNOWN_ID\n";
                continue;
            }
            std::uint32_t idx = *b;
            Result result = books[idx]->book.modify_order(id, *px, *qty);
            if (result != Result::Ok) { print_reject(id, result); continue; }
            if (!books[idx]->book.contains(id)) route.erase(id);
        } else if (cmd == "CANCEL") {
            in >> id;
            const std::uint32_t* b = route.find(id);
            if (!b) {
                std::cout << "REJECT " << id << " UNKNOWN_ID\n";
                continue;
            }
            Result result = books[*b]->book.cancel_order(id);
            if (result != Result::Ok) { print_reject(id, result); continue; }
            route.erase(id);
        }
    }

    std::vector<std::uint32_t> order(books.size());
    for (std::uint32_t i = 0; i < order.size(); ++i) order[i] = i;
    std::ranges::sort(order, {}, [&](std::uint32_t i) -> const std::string& { return books[i]->symbol; });
    for (std::uint32_t i : order) {
        if (books[i]->book.active_order_count() == 0) continue;
        std::cout << "BOOK " << books[i]->symbol << '\n';
        books[i]->book.for_each_level([&](Side s, Price px, Volume total, std::size_t count) {
            std::cout << (s == Side::Buy ? "BID " : "ASK ")
                      << format_price(px) << ' ' << total << ' ' << count << '\n';
        });
    }
    return 0;
}

int main(int argc, char** argv) {
    bool stl = false;
    std::size_t capacity = 1024;
    for (int i = 1; i < argc; ++i) {
        std::string_view arg = argv[i];
        if (arg == "--stl") { stl = true; continue; }
        if (arg == "--capacity" && i + 1 < argc) {
            std::string_view value = argv[++i];
            std::uint64_t n = 0;
            auto [end, ec] = std::from_chars(value.data(), value.data() + value.size(), n);
            if (ec == std::errc{} && end == value.data() + value.size()
                && n <= UINT32_MAX && n <= std::numeric_limits<std::size_t>::max()) {
                capacity = static_cast<std::size_t>(n);
                continue;
            }
        }
        std::cerr << "usage: cli [--stl] [--capacity 0..4294967295]\n";
        return 2;
    }
    return stl ? run_cli<StlBook>(capacity) : run_cli<FastBook>(capacity);
}
```

</details>

```bash
clang++ -std=c++20 -Wall -Wextra -Wconversion -pedantic -O2 cli.cpp -o cli
python3 run_tests.py ./cli          # 验证四步优化实现：22/22 passed
python3 run_tests.py ./cli --stl    # 验证 STL 参考实现：22/22 passed
python3 cli_regressions.py ./cli    # 容量、重试、路由与最大 id
./cli --capacity 8192 < input.txt  # 按题目规模设置每品种容量
```

---

### 额外回归：容量拒单不能静默丢单

单独生成 1025 笔不跨价订单，确认默认容量下第 1025 笔得到拒单回报；随后释放一个槽位，用同一 id 重试。这个场景检查的不只是订单簿，还包括 CLI 是否处理返回值、是否错误占用了历史 id、路由是否同步删除。

<details markdown="1">
<summary>cli_regressions.py</summary>

```python title="cli_regressions.py"
"""python3 cli_regressions.py ./cli：同时检查 FastBook 和 --stl 路径。"""
import subprocess
import sys

exe = sys.argv[1]

def run(text, capacity, stl):
    args = [exe, "--capacity", str(capacity)] + (["--stl"] if stl else [])
    result = subprocess.run(args, input=text, text=True, capture_output=True, check=True)
    return result.stdout

for stl in (False, True):
    # 第 1025 笔必须明确拒绝；拒单不占用 id，释放后原 id 可以重试。
    text = "".join(f"INSERT {i} AAPL BUY 100 1\n" for i in range(1, 1026))
    text += "CANCEL 1025\nCANCEL 1\nINSERT 1025 AAPL BUY 100 2\n"
    expected = ("REJECT 1025 CAPACITY_EXCEEDED\nREJECT 1025 UNKNOWN_ID\n"
                "BOOK AAPL\nBID 100.00 1025 1024\n")
    assert run(text, 1024, stl) == expected

    # 池满仍能成交；清理被吃光订单的路由，改价保留累计成交量。
    text = """INSERT 1 AAPL SELL 100 10
INSERT 2 AAPL BUY 99 10
INSERT 3 AAPL BUY 100 5
INSERT 4 AAPL BUY 100 10
CANCEL 1
AMEND 4 101 7
CANCEL 4
INSERT 2 AAPL SELL 102 1
INSERT 2 AAPL SELL 102 1
"""
    expected = ("REJECT 2 CAPACITY_EXCEEDED\nTRADE AAPL 100.00 5 3 1\n"
                "TRADE AAPL 100.00 5 4 1\nREJECT 1 UNKNOWN_ID\n"
                "REJECT 2 DUPLICATE_ID\nBOOK AAPL\nASK 102.00 1 1\n")
    assert run(text, 1, stl) == expected

    # UINT64_MAX 不再被哈希表哨兵排除；全部成交后仍按历史规则判重。
    last = 2**64 - 1
    text = (f"INSERT {last} AAPL SELL 100 1\nINSERT 1 AAPL BUY 100 1\n"
            f"CANCEL {last}\nINSERT {last} MSFT BUY 90 1\n")
    expected = (f"TRADE AAPL 100.00 1 1 {last}\nREJECT {last} UNKNOWN_ID\n"
                f"REJECT {last} DUPLICATE_ID\n")
    assert run(text, 1, stl) == expected

    # 每个品种单独计容量；全局路由仍指向正确的簿。
    text = """INSERT 1 AAPL BUY 100 1
INSERT 2 MSFT SELL 90 1
AMEND 2 91 2
CANCEL 1
"""
    assert run(text, 1, stl) == "BOOK MSFT\nASK 91.00 2 1\n"

print("CLI capacity, retry, routing, full-range ids (FastBook / StlBook): passed")
```

</details>

---

## 附录 E：计时代码

`bench.cpp` 生成正文「测量结果」里描述的消息流，先确认 `StlBook` 和 `FastBook` 的成交与最终快照一致，再分别测吞吐和逐条延迟。外层的路由和判重规则与附录 D 的 `cli.cpp` 相同，只是品种已经换成 0 到 7 的编号，不再按字符串查表。

<details markdown="1">
<summary>bench.cpp</summary>

```cpp title="bench.cpp"
// bench.cpp：生成随机消息流，确认两种实现输出一致，再分别计时
#include "fast_book.hpp"
#include "stl_book.hpp"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <memory>
#include <random>
#include <unordered_map>
#include <vector>

#ifndef NBIG
#define NBIG 10000000
#endif

constexpr int kSymbols = 8;

// 下单时怎样判重：记住整个会话用过的 id；要求 id 递增；不判重
enum class IdPolicy { History, Increasing, None };

struct Msg {
    enum Kind : std::uint8_t { Insert, Amend, Cancel } kind;
    Side side;
    std::uint8_t sym;
    OrderId id;
    Price px;
    Quantity qty;
};

// 与 IdMap 接口相同的 std::unordered_map 包装，给 STL 版的外层用
template<class Value>
class StdIdMap {
public:
    explicit StdIdMap(std::size_t expected) { map_.reserve(expected); }
    const Value* find(OrderId id) const {
        auto it = map_.find(id);
        return it == map_.end() ? nullptr : &it->second;
    }
    bool contains(OrderId id) const { return map_.contains(id); }
    bool insert(OrderId id, Value v) { return map_.emplace(id, v).second; }
    void erase(OrderId id) { map_.erase(id); }
private:
    std::unordered_map<OrderId, Value> map_;
};

// 外层：品种已换成 0..7 的编号；全局路由 + 可选的历史判重，规则与附录 D 的 cli.cpp 相同。
// 路由只放挂着的订单，按节点池总容量预留；历史判重表按预计受理的 id 数预留
template<template<class> class Book, template<class> class Map, class Sink>
class Engine {
    struct Entry {
        struct Listener {
            Engine* engine;
            std::uint8_t sym;
            void on_trade(const Trade& t) {
                engine->sink_.on_trade(sym, t);
                if (!engine->books_[sym]->book.contains(t.resting_id))
                    engine->route_.erase(t.resting_id);
            }
        } listener;
        Book<Listener> book;
        Entry(Engine* e, std::uint8_t sym, std::size_t capacity)
            : listener{e, sym}, book(listener, capacity) {}
    };

public:
    Engine(Sink& sink, std::size_t capacity, std::size_t expected_ids,
           IdPolicy policy = IdPolicy::History)
        : sink_(sink), route_(std::min(expected_ids, capacity * kSymbols)),
          used_(policy == IdPolicy::History ? expected_ids : 16), policy_(policy) {
        for (int s = 0; s < kSymbols; ++s)
            books_.push_back(std::make_unique<Entry>(this, std::uint8_t(s), capacity));
    }
    Engine(const Engine&) = delete;
    Engine& operator=(const Engine&) = delete;

    Result apply(const Msg& m) {
        if (m.kind == Msg::Insert) {
            if (policy_ == IdPolicy::History && used_.contains(m.id)) return Result::DuplicateId;
            if (policy_ == IdPolicy::Increasing && m.id <= last_id_) return Result::DuplicateId;
            auto& book = books_[m.sym]->book;
            Result r = book.add_order(m.id, m.side, TimeInForce::GTC, m.px, m.qty);
            if (r != Result::Ok) return r;
            if (policy_ == IdPolicy::History) used_.insert(m.id, 1);
            last_id_ = m.id;
            if (book.contains(m.id)) route_.insert(m.id, m.sym);
            return r;
        }
        const std::uint8_t* s = route_.find(m.id);
        if (!s) return Result::UnknownId;
        auto& book = books_[*s]->book;
        if (m.kind == Msg::Cancel) {
            Result r = book.cancel_order(m.id);
            route_.erase(m.id);
            return r;
        }
        Result r = book.modify_order(m.id, m.px, m.qty);
        if (!book.contains(m.id)) route_.erase(m.id);
        return r;
    }

    template<class F>
    void for_each_level(F&& f) const {
        for (int s = 0; s < kSymbols; ++s)
            books_[std::size_t(s)]->book.for_each_level([&](Side side, Price px, Volume total, std::size_t count) {
                f(s, side, px, total, count);
            });
    }

private:
    Sink& sink_;
    std::vector<std::unique_ptr<Entry>> books_;
    Map<std::uint8_t> route_;
    Map<std::uint8_t> used_;
    IdPolicy policy_;
    OrderId last_id_ = 0;
};

// 把成交和拒单混成一个哈希，用来比较两种实现的事件序列
struct HashSink {
    std::uint64_t h = 1469598103934665603ull, trades = 0, rejects = 0;
    void mix(std::uint64_t v) { h = (h ^ v) * 1099511628211ull; }
    void on_trade(std::uint8_t sym, const Trade& t) {
        ++trades;
        mix(sym), mix(std::uint64_t(t.price)), mix(t.quantity), mix(t.incoming_id), mix(t.resting_id);
    }
    void on_result(OrderId id, Result r) {
        if (r == Result::Ok) return;
        ++rejects;
        mix(id), mix(std::uint64_t(r) + 7);
    }
};

// 生成消息时用 STL 版跟踪哪些订单还挂着：撤单和改单只针对挂着的订单，
// 七成落在最近挂出的 32 笔上（报价不断刷新）。簿上的订单数稳定在 target 附近。
struct LiveTracker {
    std::vector<std::int64_t> rem, traded;
    std::vector<OrderId> filled;  // 本条消息里被吃光的挂单
    void on_trade(std::uint8_t, const Trade& t) {
        traded[t.incoming_id] += t.quantity, traded[t.resting_id] += t.quantity;
        rem[t.incoming_id] -= t.quantity;
        if ((rem[t.resting_id] -= t.quantity) == 0) filled.push_back(t.resting_id);
    }
};

std::vector<Msg> market(std::size_t n, std::uint64_t seed, std::size_t target, std::size_t capacity) {
    std::mt19937_64 rng(seed);
    auto pick = [&](std::uint64_t k) { return rng() % k; };
    LiveTracker t;
    t.rem.assign(n + 1, 0);
    t.traded.assign(n + 1, 0);
    Engine<StlBook, StdIdMap, LiveTracker> ref(t, capacity, n);
    Price mid[kSymbols];
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
        auto s = std::uint8_t(pick(kSymbols));
        if (pick(100) < 5) mid[s] += pick(2) ? 1 : -1;
        bool remove = !live.empty() && double(pick(1000)) < 500.0 * double(live.size()) / double(target);
        Msg m;
        if (!remove) {
            Side side = pick(2) ? Side::Buy : Side::Sell;
            Price off = pick(100) < 85 ? Price(1 + pick(20)) : -Price(pick(4));  // 15% 越过中间价
            OrderId id = next++;
            m = {Msg::Insert, side, s, id, side == Side::Buy ? mid[s] - off : mid[s] + off,
                 Quantity(1 + pick(100))};
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
                m = {Msg::Amend, side, 0, id, side == Side::Buy ? mp - off : mp + off, Quantity(1 + pick(100))};
                t.rem[id] = std::int64_t(m.qty) - t.traded[id];  // 改单的数量是新的总数量
                drop(id);
            }
        }
        out.push_back(m);
        ref.apply(m);
        for (OrderId r : t.filled) drop(r);
        t.filled.clear();
        if (m.kind != Msg::Cancel && t.rem[m.id] > 0) add(m.id);
    }
    return out;
}

using Stl = Engine<StlBook, StdIdMap, HashSink>;
using Fast = Engine<FastBook, IdMap, HashSink>;
using Clock = std::chrono::steady_clock;

template<class E, class... A>
std::pair<std::uint64_t, std::uint64_t> replay(const std::vector<Msg>& msgs, A... args) {
    HashSink sink;
    E e(sink, args...);
    for (const Msg& m : msgs) sink.on_result(m.id, e.apply(m));
    e.for_each_level([&](int s, Side side, Price px, Volume total, std::size_t count) {
        sink.mix(std::uint64_t(s)), sink.mix(std::uint64_t(side)), sink.mix(std::uint64_t(px));
        sink.mix(total), sink.mix(count);
    });
    return {sink.h, sink.trades};
}

template<class E, class... A>
double throughput(const std::vector<Msg>& msgs, A... args) {
    double best = 1e30;
    for (int rep = 0; rep < 5; ++rep) {
        HashSink sink;
        E e(sink, args...);
        auto t0 = Clock::now();
        for (const Msg& m : msgs) e.apply(m);
        auto t1 = Clock::now();
        best = std::min(best, std::chrono::duration<double, std::nano>(t1 - t0).count() / double(msgs.size()));
    }
    return best;
}

template<class E, class... A>
void latency(const char* name, const std::vector<Msg>& msgs, A... args) {
    HashSink sink;
    E e(sink, args...);
    std::vector<std::int64_t> ns(msgs.size());
    for (std::size_t i = 0; i < msgs.size(); ++i) {
        auto t0 = Clock::now();
        e.apply(msgs[i]);
        auto t1 = Clock::now();
        ns[i] = std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count();
    }
    std::ranges::sort(ns);
    auto q = [&](double p) { return ns[std::size_t(p * double(ns.size() - 1))]; };
    std::printf("%-26s p50 %5lld  p99 %6lld  p99.9 %7lld  max %9lld ns\n", name, (long long)q(0.5),
                (long long)q(0.99), (long long)q(0.999), (long long)ns.back());
}

int main() {
    const std::size_t n = NBIG;
    for (std::size_t target : {std::size_t(8'000), std::size_t(800'000)}) {
        std::size_t cap = target / kSymbols * 2;  // 每个品种的节点池，留一倍余量
        auto msgs = market(n, 42, target, cap);
        auto a = replay<Stl>(msgs, cap, n);
        auto b = replay<Fast>(msgs, cap, n);
        if (a != replay<Fast>(msgs, cap, n, IdPolicy::Increasing)) return std::puts("mismatch"), 1;
        std::printf("\ntarget %zu: %zu msgs, %llu trades\n", target, n, (unsigned long long)a.second);
        if (a != b) return std::puts("mismatch"), 1;
        std::printf("%-26s %6.1f ns/msg\n", "StlBook", throughput<Stl>(msgs, cap, n));
        std::printf("%-26s %6.1f ns/msg\n", "FastBook", throughput<Fast>(msgs, cap, n));
        std::printf("%-26s %6.1f ns/msg\n", "FastBook, increasing ids",
                    throughput<Fast>(msgs, cap, n, IdPolicy::Increasing));
        std::printf("%-26s %6.1f ns/msg\n", "FastBook, no dedupe", throughput<Fast>(msgs, cap, n, IdPolicy::None));
        std::printf("%-26s %6.1f ns/msg\n", "FastBook, no reserve", throughput<Fast>(msgs, cap, std::size_t(16)));
        latency<Stl>("StlBook", msgs, cap, n);
        latency<Fast>("FastBook", msgs, cap, n);
        latency<Fast>("FastBook, no reserve", msgs, cap, std::size_t(16));
        latency<Fast>("FastBook, increasing ids", msgs, cap, n, IdPolicy::Increasing);
    }
}
```

</details>

先用小规模输入在 sanitizer 下跑一遍，再关掉断言计时：

```bash
clang++ -std=c++20 -O1 -fsanitize=address,undefined -DNBIG=100000 bench.cpp -o bench_asan && ./bench_asan
clang++ -std=c++20 -O2 -DNDEBUG bench.cpp -o bench && ./bench
```

整个程序需要 1 GB 以上内存，主要是 1000 万条消息、生成时的跟踪数组和预留的判重表。

## 附录 F：一本簿一个执行线程，簿外怎样并行

**面试官：**「现在要利用多核，你会直接给订单簿加锁吗？」

先区分两件事：多本簿可以并行，和多线程同时修改同一本簿。本文选择每本簿由一个线程独占执行，其余线程负责收发、解析、风控、日志与输出。这样簿内不用锁，输入次序也容易保持确定。

这是一种可解释的架构选择，不是所有撮合系统都必须采用的唯一实现。即使给订单簿加锁，也仍然要定义业务顺序；锁能保护数据结构，却不能代替时间优先的定序规则。

Martin Fowler 在 2011 年的 [The LMAX Architecture](https://martinfowler.com/articles/lmax.html) 中描述过一个具体实例：业务核心是单线程、纯内存、基于事件回放的处理器，外围通过 Disruptor 交接。文章报告了约每秒 600 万笔订单的基准结果。这个实例支持单线程核心可以配合外围并行工作的思路，不能用它替所有系统推断固定延迟。

### 整体流水线：把不可控的工作移到簿外

<figure class="diagram">
<svg viewBox="0 0 760 330" role="img" aria-label="网关线程、定序线程、按品种分片的撮合线程和输出线程之间用队列连接" style="width:100%;height:auto;font-family:var(--font-sans);font-size:13px">
<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--ink)" opacity=".55"/></marker></defs>
<g fill="var(--ink)" opacity=".6" text-anchor="middle" font-size="12"><text x="55" y="22">客户连接</text><text x="205" y="22">网关线程</text><text x="375" y="22">定序线程</text><text x="540" y="22">撮合线程</text><text x="695" y="22">输出线程</text></g>
<g fill="var(--surface)" stroke="var(--line)" stroke-width="1.2">
<rect x="15" y="45" width="80" height="30" rx="6"/><rect x="15" y="90" width="80" height="30" rx="6"/><rect x="15" y="160" width="80" height="30" rx="6"/><rect x="15" y="205" width="80" height="30" rx="6"/>
<rect x="140" y="55" width="130" height="56" rx="8"/><rect x="140" y="170" width="130" height="56" rx="8"/>
<rect x="320" y="70" width="110" height="140" rx="8" stroke="var(--accent)"/>
<rect x="320" y="255" width="110" height="44" rx="8"/>
<rect x="470" y="45" width="140" height="48" rx="8" stroke="var(--accent)"/><rect x="470" y="116" width="140" height="48" rx="8" stroke="var(--accent)"/><rect x="470" y="187" width="140" height="48" rx="8" stroke="var(--accent)"/>
<rect x="645" y="45" width="100" height="190" rx="8"/>
</g>
<g fill="var(--ink)" text-anchor="middle">
<text x="55" y="65">客户 A</text><text x="55" y="110">客户 B</text><text x="55" y="180">客户 C</text><text x="55" y="225">客户 D</text>
<text x="205" y="78">网关 1</text><text x="205" y="98" font-size="11.5" opacity=".7">解析 · 会话 · 风控</text>
<text x="205" y="193">网关 2</text><text x="205" y="213" font-size="11.5" opacity=".7">解析 · 会话 · 风控</text>
<text x="375" y="100">定序器</text><text x="375" y="128" font-size="11.5" opacity=".7">排成全序</text><text x="375" y="148" font-size="11.5" opacity=".7">编序号</text><text x="375" y="168" font-size="11.5" opacity=".7">按品种分发</text>
<text x="375" y="275">日志 · 备机</text><text x="375" y="291" font-size="11" opacity=".7">落盘、复制</text>
<text x="540" y="66">撮合 0</text><text x="540" y="83" font-size="11.5" opacity=".7">S0 S3 S6 的簿</text>
<text x="540" y="137">撮合 1</text><text x="540" y="154" font-size="11.5" opacity=".7">S1 S4 S7 的簿</text>
<text x="540" y="208">撮合 2</text><text x="540" y="225" font-size="11.5" opacity=".7">S2 S5 的簿</text>
<text x="695" y="110">发送</text><text x="695" y="135" font-size="11.5" opacity=".7">执行回报</text><text x="695" y="155" font-size="11.5" opacity=".7">逐笔行情</text><text x="695" y="175" font-size="11.5" opacity=".7">输出日志</text>
</g>
<g stroke="var(--ink)" stroke-opacity=".45" stroke-width="1.2" fill="none" marker-end="url(#ah)">
<path d="M95 60L138 76"/><path d="M95 105L138 92"/><path d="M95 175L138 191"/><path d="M95 220L138 207"/>
<path d="M270 83L318 115"/><path d="M270 198L318 165"/>
<path d="M375 210L375 253"/>
<path d="M430 110L468 72"/><path d="M430 140L468 140"/><path d="M430 170L468 208"/>
<path d="M610 69L643 100"/><path d="M610 140L643 140"/><path d="M610 211L643 180"/>
</g>
<text x="380" y="322" text-anchor="middle" fill="var(--ink)" opacity=".6" font-size="12">线程之间的每个箭头是一个单生产者单消费者队列；每本簿只被一个撮合线程访问</text>
</svg>
</figure>

图中是一种简化方案，每个线程可以拥有多条队列；实际日志、复制和回报时机还需要故障恢复协议来定义。

- **网关线程**负责收包、解析、会话与下单前风控，把品种名转换成内部编号。
- **定序线程**决定请求的执行次序并分发到对应分片。可以让日志、复制与撮合围绕同一输入序列协作，但何时允许撮合、何时确认客户，需要明确持久化和复制水位。
- **撮合线程**独占若干本簿，处理输入并生成事件。若目标是严格零分配、零系统调用，就要预留所有资源并限制回调；本页代码并没有自动保证整条流水线满足这些目标。
- **输出线程**编码成交、订单状态和行情事件，负责网络与日志输出，把慢速 I/O 与核心状态更新分开。

LMAX 的共享环形缓冲区及多消费者依赖关系，比图里的成对 SPSC 队列更丰富；它们不是同一种队列拓扑。

### 线程之间怎样交接

如果一条队列确实只有一个生产者、一个消费者，可以用 **SPSC 环形缓冲区**：固定数组中循环复用槽位，生产者推进尾游标，消费者推进头游标，通过恰当的 acquire/release 操作发布与回收数据。具体实现和内存序见 [[topics/concurrency-in-practice|并发实战]]。

落地时要继续回答几个问题：

- 头尾游标是否共用缓存行？分开布局可以减少伪共享，缓存行大小和对齐方式要按平台确认，见 [[perf/false-sharing|伪共享]]。
- 队列满了怎么办？阻塞、拒绝、背压或降级必须有明确政策，不能覆盖尚未消费的事件。
- 消息由谁拥有？定长值消息容易管理；若传指针，则要另行规定跨线程生命周期和回收责任。
- 多个网关怎样汇入？可以各用一条 SPSC，由定序器按既定策略读取；也可以选择 MPSC。两者的争用、轮询成本、公平性与定序政策需要比较，不能仅凭是否使用 CAS 判断好坏。

### 空转还是睡眠

撮合线程的输入队列空了时，有两种等法：

- 空转：不停地轮询队列。新消息几十纳秒内就能被看到，代价是不管有没有消息，这个核一直满载。对延迟敏感的系统通常这样做，并把撮合线程绑在固定的核上，让调度器既不把别的线程放上来，也不把它迁走。Linux 上用 `sched_setaffinity` 绑核，再用 `isolcpus` 之类的启动参数把这些核从普通调度里拿出来；macOS 没有绑核的接口，只能用 QoS 提示要求跑在性能核上（见 [[perf/measuring|测量]]）。
- 睡眠：在条件变量或 `std::atomic::wait` 上睡下，生产者放进消息后唤醒它。这样省 CPU，但从唤醒到重新运行要几微秒，比撮合一条消息慢两个数量级。

C++20 的 `std::atomic::wait` 不一定马上睡。测试机上的 libc++（`<__atomic/atomic_sync.h>`）先检查 64 次，再继续自旋，直到 4 µs 内值都没变，才调用操作系统的等待。消息间隔小于 4 µs 时它的表现接近空转，间隔更长时每条消息都要付一次唤醒的代价。这些常数是这一版库的实现细节，不是接口保证，换平台要重新确认。

### 为什么不给引擎加锁

被问到「怎样改成多线程」时，常见的错误回答是给下单、撤单、改单加一把锁。可以按顺序把几种做法摆出来：

1. 一把全局锁。简单、正确，但消息仍然一条一条地执行，还多了加锁和簿的数据在核之间搬运的代价，线程越多每条消息越慢。
2. 每个品种一把锁。不同品种可以并行了。但撤单和改单不带品种时，要先按 id 查出品种，这张 id 表变成所有线程共享的结构，需要自己的保护；附录 D 里的路由表和历史判重表也是跨品种共享的。
3. 按品种分片，线程之间用队列传消息。每本簿只被一个线程访问，不需要锁，确定性也保住了。上面的流水线就是这种做法。

### 分片后，哪些问题还没消失

按品种分片之后，每个线程可以独占一组簿，但还要处理五类边界：

1. **撤单路由。** 协议若携带品种，可以直接查分片；只有全局 id 时，需要维护路由，并同步订单离簿事件。真实协议通常要求撤单带品种，例如 FIX 的撤单请求里品种是必填字段，这个问题就不存在了。
2. **跨品种组合单。** 如果一次操作要求同时撮合多本簿，就不能独立地向各分片发请求后假设它们原子完成。把相关品种放在同一执行分区是一种简化方式，否则需要跨分区协调。所以分片通常按相关品种成组划分，例如同一标的的各月期货和它们之间的价差合约放在一起，而不是按品种名做哈希。
3. **负载倾斜。** 热门品种可能压满一个线程，分配分片时应看实际流量，并设计迁移时机和状态交接。
4. **回报顺序。** 单簿内可以保持执行顺序，跨分片回报可能交错。协议要说明保证哪种顺序，是否需要在输出端重新排序。
5. **跨品种风控。** 账户资金与持仓横跨多本簿。一种做法是在进入撮合前预占额度，再根据成交或撤单回报结算；怎样同步、回收和恢复额度，仍需要单独设计。

单本簿的状态机写对，是讨论这些问题的基础。面试中把单簿规则、线程间交接和故障恢复分别讲清楚，比把一个示例直接称作生产系统更有说服力。

## 附录 G：按价格从高到低打印价位

有的题面用一条打印命令输出当前的簿：先卖盘后买盘，两侧都按价格从高到低，同价合并，只输出价格和总量。

```text
SELL:
1010 10
1000 20
BUY:
999 10
800 20
```

这个功能不走 `Listener`。`Listener` 用来通知撮合过程中发生的事件，由引擎主动调用；打印是调用方发起的一次查询，引擎没有事件要报告。所以让订单簿提供只读遍历，输出放在订单簿外面，订单簿不需要知道输出格式。

现有的 `for_each_level` 是先买后卖、每一侧从最优价开始，顺序不符合这里的要求，所以再加两个遍历函数。它们放在订单簿的 `public` 部分：

```cpp
// StlBook、PoolBook：买盘的 map 本来就从高到低，卖盘反向遍历
template<class F>
void for_each_ask_descending(F&& f) const {
    for (auto it = asks_.rbegin(); it != asks_.rend(); ++it)
        f(it->first, it->second.total);
}
template<class F>
void for_each_bid_descending(F&& f) const {
    for (const auto& [price, level] : bids_)
        f(price, level.total);
}
```

```cpp
// FastBook：卖盘数组本来就从高到低，买盘数组反向遍历
template<class F>
void for_each_ask_descending(F&& f) const {
    for (const Level& level : asks_)
        f(level.price, level.total);
}
template<class F>
void for_each_bid_descending(F&& f) const {
    for (auto it = bids_.rbegin(); it != bids_.rend(); ++it)
        f(it->price, it->total);
}
```

打印函数对三种实现都适用：

```cpp title="print_book.hpp"
#pragma once
#include "types.hpp"
#include <ostream>

template<class Book>
void print_book(const Book& book, std::ostream& out) {
    auto print_level = [&out](Price price, Volume total) {
        out << price << ' ' << total << '\n';
    };
    out << "SELL:\n";
    book.for_each_ask_descending(print_level);
    out << "BUY:\n";
    book.for_each_bid_descending(print_level);
}
```

某一侧为空时，标题照常输出。遍历不修改订单簿，可以多次打印。这份代码和三种实现一起用确定性用例测过（空簿、同价合并、多个价位、成交后的余量、连续打印两次），在 ASan/UBSan 下通过。

## 附录 H：另一套约定下的完整程序

下面是一份完整的单文件程序，用的是和正文不同的一套约定，可以对照看同样的结构怎样适配另一份题面：

- 一本簿，没有品种；订单 id 是任意不含空格的字符串；命令是 `BUY`、`SELL`、`CANCEL`、`MODIFY`、`PRINT`。
- 有效期是 GFD 和 IOC。输入里没有日期或收盘命令，GFD 单一直留在簿上，直到成交或撤销。
- 任何改单都失去排队位置，方向也可以变，数量是新的剩余量，所以 `MODIFY` 一律撤单再下单，可能立即成交。
- 成交输出两边各自的限价，先到的一方在前。
- 不合法的输入一律静默忽略；节点池可以增长，没有容量错误。

程序分成四部分：`OrderBook` 负责撮合，`Writer` 负责输出格式，`dispatch` 负责解析，`LineReader` 负责读取，彼此只通过很小的接口联系。

<details markdown="1">
<summary>engine.cpp</summary>

```cpp title="engine.cpp"
// engine.cpp：单本订单簿的撮合程序。从标准输入读命令，向标准输出写成交和快照。
// 假设：MODIFY 的数量是新的剩余量；改过的订单算后到；单个价位的总量不超过 64 位。
#include <algorithm>
#include <array>
#include <charconv>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <optional>
#include <ranges>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

using Price = std::int64_t;
using Quantity = std::uint64_t;

enum class Side : std::uint8_t { Buy, Sell };
enum class OrderType : std::uint8_t { GFD, IOC };

// 先到的一方在前。id 只在回调期间有效，要保存就复制
struct Trade {
    std::string_view first_id;
    Price first_price;
    std::string_view second_id;
    Price second_price;
    Quantity quantity;
};

struct StringHash {
    using is_transparent = void;
    std::size_t operator()(std::string_view s) const noexcept {
        return std::hash<std::string_view>{}(s);
    }
};

// 只负责撮合和状态：不读输入，不知道输出格式，成交通过 Listener 报告。
// 回调里不能修改订单簿。
template<class Listener>
class OrderBook {
public:
    explicit OrderBook(Listener& listener, std::size_t expected_orders = 1 << 16,
                       std::size_t expected_levels = 1 << 10)
        : listener_(listener) {
        nodes_.reserve(expected_orders);
        free_.reserve(expected_orders);
        lookup_.reserve(expected_orders);
        bids_.reserve(expected_levels);
        asks_.reserve(expected_levels);
    }
    OrderBook(const OrderBook&) = delete;
    OrderBook& operator=(const OrderBook&) = delete;

    // 活跃 id 重复时忽略。price、quantity 由调用方保证为正
    void add(std::string_view id, Side side, OrderType type, Price price, Quantity quantity) {
        if (lookup_.find(id) != lookup_.end()) return;
        submit(id, side, type, price, quantity);
    }

    void cancel(std::string_view id) {
        auto it = lookup_.find(id);
        if (it != lookup_.end()) remove(it);
    }

    // 任何改单都失去排队位置，方向也可以变，所以一律撤单再下单。
    // id 指向调用方的缓冲区，不指向索引里即将删除的键。
    void modify(std::string_view id, Side side, Price price, Quantity quantity) {
        auto it = lookup_.find(id);
        if (it == lookup_.end()) return;
        remove(it);
        submit(id, side, OrderType::GFD, price, quantity);
    }

    template<class F>
    void for_each_ask_descending(F&& f) const {  // 卖盘数组本来就从高到低
        for (const Level& level : asks_) f(level.price, level.total);
    }
    template<class F>
    void for_each_bid_descending(F&& f) const {  // 买盘数组从低到高，反向遍历
        for (const Level& level : std::views::reverse(bids_)) f(level.price, level.total);
    }

private:
    using Index = std::uint32_t;
    static constexpr Index nil = UINT32_MAX;

    struct Node {
        const std::string* id;  // 指向索引里的键；rehash 不改变元素地址
        Price price;
        Quantity leaves;
        Index prev;
        Index next;
    };
    struct Level {
        Price price;
        Quantity total;
        Index head;
        Index tail;
    };
    struct Locator {
        Index index;
        Side side;
    };
    // 键是节点式容器里的 string，地址稳定；查找时不用构造临时字符串
    using Lookup = std::unordered_map<std::string, Locator, StringHash, std::equal_to<>>;

    template<Side S>
    static constexpr bool better(Price a, Price b) noexcept {
        if constexpr (S == Side::Buy) return a > b;
        else return a < b;
    }
    template<Side S>
    std::vector<Level>& levels() noexcept {
        if constexpr (S == Side::Buy) return bids_;
        else return asks_;
    }
    // 价位从差到好排列，最优价在 back()，吃空最优价只是一次 pop_back。
    // 前提是操作集中在盘口附近；在远离盘口处增删价位要移动 O(P) 个元素。
    template<Side S>
    auto lower(Price price) noexcept {
        return std::ranges::partition_point(levels<S>(), [price](const Level& level) {
            return better<S>(price, level.price);
        });
    }

    void submit(std::string_view id, Side side, OrderType type, Price price, Quantity quantity) {
        if (side == Side::Buy) submit<Side::Buy>(id, type, price, quantity);
        else submit<Side::Sell>(id, type, price, quantity);
    }

    template<Side S>
    void submit(std::string_view id, OrderType type, Price price, Quantity leaves) {
        static constexpr Side opposite = S == Side::Buy ? Side::Sell : Side::Buy;
        match<S, opposite>(id, price, leaves);
        if (leaves != 0 && type == OrderType::GFD) rest<S>(id, price, leaves);
    }

    template<Side S, Side Opposite>
    void match(std::string_view id, Price price, Quantity& leaves) {
        auto& book = levels<Opposite>();
        while (leaves != 0 && !book.empty()) {
            Level& level = book.back();
            if (better<S>(level.price, price)) break;  // 对手最优价已经比限价差
            while (leaves != 0 && level.head != nil) {
                Index index = level.head;
                Node& resting = nodes_[index];
                Quantity traded = std::min(leaves, resting.leaves);
                leaves -= traded;
                resting.leaves -= traded;
                level.total -= traded;
                // 要在删除索引之前报告：resting.id 指向索引里的键
                listener_.on_trade(Trade{.first_id = *resting.id, .first_price = resting.price,
                                         .second_id = id, .second_price = price,
                                         .quantity = traded});
                if (resting.leaves == 0) {
                    unlink(level, index);
                    lookup_.erase(lookup_.find(*resting.id));
                    free_.push_back(index);
                }
            }
            if (level.head == nil) book.pop_back();
        }
    }

    template<Side S>
    void rest(std::string_view id, Price price, Quantity leaves) {
        auto [entry, inserted] = lookup_.try_emplace(std::string(id), Locator{nil, S});
        Index index = allocate();
        entry->second.index = index;
        nodes_[index] = Node{&entry->first, price, leaves, nil, nil};

        auto it = lower<S>(price);
        if (it == levels<S>().end() || it->price != price)
            it = levels<S>().insert(it, Level{price, 0, nil, nil});
        append(*it, index);
    }

    void remove(typename Lookup::iterator entry) {
        Locator locator = entry->second;
        if (locator.side == Side::Buy) remove_from_level<Side::Buy>(locator.index);
        else remove_from_level<Side::Sell>(locator.index);
        lookup_.erase(entry);
        free_.push_back(locator.index);
    }

    template<Side S>
    void remove_from_level(Index index) {
        auto it = lower<S>(nodes_[index].price);
        it->total -= nodes_[index].leaves;
        unlink(*it, index);
        if (it->head == nil) levels<S>().erase(it);
    }

    // 节点池可以增长：位置存的是下标，扩容后仍然有效
    Index allocate() {
        if (!free_.empty()) {
            Index index = free_.back();
            free_.pop_back();
            return index;
        }
        nodes_.emplace_back();
        return static_cast<Index>(nodes_.size() - 1);
    }

    // append 把数量计入价位总量；unlink 只改链接，不碰数量
    void append(Level& level, Index index) noexcept {
        Node& node = nodes_[index];
        node.prev = level.tail;
        node.next = nil;
        if (level.tail != nil) nodes_[level.tail].next = index;
        else level.head = index;
        level.tail = index;
        level.total += node.leaves;
    }
    void unlink(Level& level, Index index) noexcept {
        const Node& node = nodes_[index];
        if (node.prev != nil) nodes_[node.prev].next = node.next;
        else level.head = node.next;
        if (node.next != nil) nodes_[node.next].prev = node.prev;
        else level.tail = node.prev;
    }

    Listener& listener_;
    std::vector<Node> nodes_;
    std::vector<Index> free_;
    std::vector<Level> bids_;  // 升序，最高买价在 back()
    std::vector<Level> asks_;  // 降序，最低卖价在 back()
    Lookup lookup_;
};

// 只负责输出格式：缓冲后一次写出，不为每行调用一次系统调用
class Writer {
public:
    ~Writer() { flush(); }

    void on_trade(const Trade& t) {
        text("TRADE ");
        text(t.first_id), text(" "), number(t.first_price), text(" "), number(t.quantity), text(" ");
        text(t.second_id), text(" "), number(t.second_price), text(" "), number(t.quantity), text("\n");
    }
    template<class Book>
    void print(const Book& book) {
        auto print_level = [this](Price price, Quantity total) {
            number(price), text(" "), number(total), text("\n");
        };
        text("SELL:\n");
        book.for_each_ask_descending(print_level);
        text("BUY:\n");
        book.for_each_bid_descending(print_level);
    }
    void flush() {
        std::fwrite(buffer_.data(), 1, buffer_.size(), stdout);
        std::fflush(stdout);
        buffer_.clear();
    }

private:
    static constexpr std::size_t kFlushAt = 1 << 16;

    void text(std::string_view s) {
        buffer_.append(s);
        if (buffer_.size() >= kFlushAt) flush();
    }
    template<class T>
    void number(T value) {
        std::array<char, 24> digits;
        auto [end, ec] = std::to_chars(digits.data(), digits.data() + digits.size(), value);
        text({digits.data(), static_cast<std::size_t>(end - digits.data())});
    }

    std::string buffer_;
};

// 下面只负责解析：把一行文本变成对订单簿的调用，任何不合法的内容都静默忽略
template<class T>
std::optional<T> parse_positive(std::string_view s) {
    T value{};
    auto [end, ec] = std::from_chars(s.data(), s.data() + s.size(), value);
    if (ec != std::errc{} || end != s.data() + s.size() || value <= 0) return std::nullopt;
    return value;
}

std::optional<Side> parse_side(std::string_view s) {
    if (s == "BUY") return Side::Buy;
    if (s == "SELL") return Side::Sell;
    return std::nullopt;
}

std::optional<OrderType> parse_type(std::string_view s) {
    if (s == "GFD") return OrderType::GFD;
    if (s == "IOC") return OrderType::IOC;
    return std::nullopt;
}

// 按单个空格切分，连续空格会得到空列，这样才能发现空 id。
// 超过 N 列时返回 N + 1，调用方按列数不符忽略。
template<std::size_t N>
std::size_t split(std::string_view line, std::array<std::string_view, N>& columns) {
    std::size_t count = 0;
    while (count < N) {
        std::size_t space = line.find(' ');
        columns[count++] = line.substr(0, space);
        if (space == std::string_view::npos) return count;
        line.remove_prefix(space + 1);
    }
    return N + 1;
}

template<class Book>
void dispatch(std::string_view line, Book& book, Writer& writer) {
    if (!line.empty() && line.back() == '\r') line.remove_suffix(1);

    std::array<std::string_view, 5> c;
    std::size_t count = split(line, c);

    if (c[0] == "PRINT") {
        if (count == 1) writer.print(book);
    } else if (c[0] == "CANCEL") {
        if (count == 2 && !c[1].empty()) book.cancel(c[1]);
    } else if (c[0] == "MODIFY") {
        if (count != 5 || c[1].empty()) return;
        auto side = parse_side(c[2]);
        auto price = parse_positive<Price>(c[3]);
        auto quantity = parse_positive<Quantity>(c[4]);
        if (side && price && quantity) book.modify(c[1], *side, *price, *quantity);
    } else if (auto side = parse_side(c[0])) {
        if (count != 5 || c[4].empty()) return;
        auto type = parse_type(c[1]);
        auto price = parse_positive<Price>(c[2]);
        auto quantity = parse_positive<Quantity>(c[3]);
        if (type && price && quantity) book.add(c[4], *side, *type, *price, *quantity);
    }
}

// 只负责读取：一次读一大块，再按行切分。返回的 string_view 在下一次调用前有效。
// 不用 std::getline：有的标准库实现读 std::cin 时每个字符都要加锁调用一次 C 库函数。
class LineReader {
public:
    explicit LineReader(std::FILE* file, std::size_t capacity = 1 << 16)
        : file_(file), buffer_(capacity) {}

    bool next(std::string_view& line) {
        for (;;) {
            const char* begin = buffer_.data() + start_;
            const void* newline = start_ == end_ ? nullptr : std::memchr(begin, '\n', end_ - start_);
            if (newline) {
                auto length = static_cast<std::size_t>(static_cast<const char*>(newline) - begin);
                line = {begin, length};
                start_ += length + 1;
                return true;
            }
            if (!fill()) {
                if (start_ == end_) return false;
                line = {buffer_.data() + start_, end_ - start_};  // 最后一行没有换行符
                start_ = end_;
                return true;
            }
        }
    }

private:
    bool fill() {
        std::copy(buffer_.begin() + static_cast<std::ptrdiff_t>(start_),
                  buffer_.begin() + static_cast<std::ptrdiff_t>(end_), buffer_.begin());
        end_ -= start_;
        start_ = 0;
        if (end_ == buffer_.size()) buffer_.resize(buffer_.size() * 2);  // 一行比缓冲区还长
        std::size_t count = std::fread(buffer_.data() + end_, 1, buffer_.size() - end_, file_);
        end_ += count;
        return count != 0;
    }

    std::FILE* file_;
    std::vector<char> buffer_;
    std::size_t start_ = 0;
    std::size_t end_ = 0;
};

int main() {
    Writer writer;
    OrderBook<Writer> book(writer);
    LineReader reader(stdin);
    std::string_view line;
    while (reader.next(line)) dispatch(line, book, writer);
}
```

</details>

```bash
clang++ -std=c++20 -O2 -DNDEBUG engine.cpp -o engine
./engine < input.txt
```

这份程序在 ASan/UBSan 下通过了 20 个确定性用例，以及和一个独立的 Python 线性扫描实现的随机对照（300 个种子，共 30 万行，混有非法输入）。Python 实现和它不共享结构，但两者都按上面的假设写，所以对照不能发现对约定本身的误解。

读写的写法对总耗时影响很大。下面是同一份 300 万行输入（产生约 145 万行输出）的耗时，都写到文件，取 5 次中最快的一次，机器和编译器同附录 E。前五行都用 `LineReader` 读输入，输出完全相同：

| 写法 | 耗时 |
|---|---:|
| 自己的缓冲区加 `std::to_chars`（上面的程序） | 1.4 s |
| 自己的缓冲区加 `std::format_to` | 1.8 s |
| `std::cout << std::format(...)`，关闭同步 | 2.0 s |
| `std::cout << ...`，关闭同步 | 2.8 s |
| `std::cout << ... << std::endl` | 7.6 s |
| 上面的程序，输入改用 `std::getline` | 4.8 s |

`std::format` 解决的是把值变成文本，缓冲解决的是什么时候把文本交给操作系统，这是两件事。`std::endl` 每行都刷新，慢在系统调用，换成 `std::format` 也救不了；反过来，`std::format_to` 写进自己的缓冲区，代码更短，只慢一点，如果判题环境支持（GCC 13 起），也是合理的选择。`fmt` 库速度也好，但它是第三方依赖，判题环境不一定有。这些数字只反映这台机器和这个标准库，`std::getline` 的代价尤其依赖实现。
