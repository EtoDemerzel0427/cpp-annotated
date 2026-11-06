---
title: Matching engine
summary: A problem common in trading-firm final rounds: implement a matching engine with limit orders, cancels, amends by total quantity, and multiple symbols. This page follows a mock interview in order. It starts with how an order trades, writes an STL baseline, then replaces it step by step with an object pool, an open-addressing hash table and sorted arrays, stating each step's precondition and how to confirm the behavior did not change. The appendices give complete C++20 code, three-way differential tests, 22 protocol test cases, the timing program with measured data, and the structure of a multithreaded system.
status: draft
order: 10
related: perf/measuring, perf/memory-hierarchy, perf/choosing-containers, perf/allocation, perf/false-sharing, toolchain/testing, topics/concurrency-in-practice, list.ops, unord.req.general, associative.reqmts.general
tags: matching engine, order book, interview, hash table, latency, practice
updated: 2026-11-05
---

!!! tldr
    - Price priority, then time priority; a trade happens at the resting order's price. A new order matches first; a GTC remainder rests, an IOC remainder is canceled.
    - An amend carries the target total quantity, and the new remaining quantity is the target total minus the cumulative fill. A same-price decrease keeps its queue position, an increase goes to the back, and a price change matches again. An aggressor that fills partly and then rests keeps its cumulative fill.
    - Write the STL version with `map + list + unordered_map` first, then replace the order nodes, the id index and the price-level table in turn. Multiple symbols are handled by an outer layer that routes to each symbol's book; the single-book matching logic does not change.
    - Measured on an Apple M2 Pro with 10 million messages, the cost per message drops from 150 ns for the STL version to 67 ns with a shallow book, and from 371 ns to 109 ns with a deep one. The requirement that no id repeat within the session costs about 14–25 ns on its own, and requiring increasing ids removes that cost. Without reserved capacity, one rehash stalls a single message for 70–98 ms.
    - The three implementations in the appendices pass the same deterministic cases, 100,000 steps of three-way random differential testing and 22 protocol cases, all under ASan/UBSan.

When an interviewer asks you to write a matching engine, the hard part is usually not comparing bid and ask prices. It is keeping the orders, price levels and index consistent after every trade, cancel and amend. Writing `map + list + unordered_map` is only the start; you also need to explain why you chose them, where they may be slow, and how you confirm that replacing them did not change the business rules.

This page first looks at how a single order trades, then proceeds in four versions: an STL baseline, amends by total quantity, routing across symbols, and data-structure optimization. The main text keeps the interview's questions and answers; the complete implementation and tests are in the appendices, so you can rewrite it on your own and compare.

## What this problem tests

This is a common problem in trading-firm C++ final rounds. A typical format is two hours: the first hour discussing requirements and design with the interviewer, the second writing code in a provided project so that its existing tests pass; some places give 30 minutes to read the problem alone first. You work in an ordinary IDE, not on a whiteboard. Passing every test does not guarantee an offer; how you do in the discussion counts too.

Over those two hours the interviewer looks at four areas:

| Area | What they look for |
|---|---|
| Communication and requirements | Whether you ask about the semantics before coding, and write the answers down |
| Data structures and hardware | Whether you give a correct structure and its complexity, then explain its cost in caches and memory allocation |
| Writing code | Clear structure, no duplicated buy and sell code, talking while you write, passing simple tests before adding features |
| Testing and edge cases | Whether you can say how to show it is correct, and think of the edge cases that are easy to miss |

The "Grading" section near the end of the page describes strong, average and weak answers in each of these four areas.

## How an order book works

### Bids, asks and the top of the book

Orders that have not traded and wait in the system make up the **order book** (limit order book). Each instrument (a stock, a futures contract) has its own book with two sides: buyers' prices form the **bids**, sorted from high to low, and sellers' prices form the **asks**, sorted from low to high.

- The highest bid is the best bid, and the lowest ask is the best ask.
- Their difference is the spread. After continuous matching finishes a message, whenever both sides are non-empty, `best_bid < best_ask` holds; otherwise some order could still trade immediately. A book that satisfies this condition is called an uncrossed book.

All prices below are integer multiples of the minimum price increment, the tick. Suppose three sell orders have arrived in turn on the ask side:

| Ask price | Queue at that price (left arrived first) | Level total |
|---|---|---:|
| 102 | #1: 3 lots → #2: 4 lots | 7 |
| 103 | #3: 10 lots | 10 |

A new buy order #4 arrives, willing to buy 5 lots at no more than 105. It first looks at the lowest ask, 102: it takes the 3 lots of #1 at the front of the queue, then 2 lots from #2, and is completely filled. #2 has 2 lots left and stays at the front of the queue at 102.

### Aggressor and resting order

A new order entering the engine has one of two outcomes:

1. It does not cross: the lowest ask is 102 and the new buy order bids 101, so nothing trades and the order waits on the book. An order waiting on the book is a **resting order**.
2. It crosses: the lowest ask is 102 and the new buy order is willing to pay 105, which triggers matching at once. The incoming order that triggers the trades is the **aggressor**. An aggressor may also fill only partly: if #4 above wanted 20 lots, it would take the 7 lots at 102 and the 10 lots at 103, and the remaining 3 lots would rest on the bid side at its own limit of 105, becoming a new resting order.

In this problem a trade happens at the resting order's price, not the aggressor's limit. The seller put 102 on the book first and the buyer accepts that price, so both trades are at 102. When one buy order sweeps the 102 and 103 levels in a row, each trade records the price of the level it consumed.

### How order types differ

Common order types differ in three ways: whether there is a price limit, what happens to the unfilled part, and whether enough quantity is required before trading.

| Order type | Price limit | Remainder | Implementation notes |
|---|---|---|---|
| Limit order, GTC (good till canceled) | Yes | Rests on its own side until filled or canceled | The basic path; the exercise does not handle trading-day boundaries |
| IOC (immediate or cancel) | Yes | Discarded at once, never rests | One extra branch after matching; trading nothing is still a normal acceptance, not a reject |
| Market order | No | Usually canceled; some markets convert it to a limit order | Needs a separate flag for whether there is a limit; 0 or an extreme value cannot serve both as a price and as a market marker. Not implemented on this page |
| FOK (fill or kill) | Yes | No remainder allowed | Before matching, check whether the total within the limit is enough, and match only if it is; it cannot trade first and then roll back |

### Price priority, time priority, and queue rules for amends

Matching trades first with the best-priced opposite orders: a buy takes the lowest ask first, a sell takes the highest bid first. At the same price, the earlier order trades first, so each price level is a first-in, first-out (FIFO) queue.

When an order still on the book is modified, the convention is:

- Same price, smaller quantity: modified in place, keeping its queue position. The order itself trades less, and orders behind it lose nothing.
- Same price, larger quantity: loses time priority and moves to the back of the queue at that price. Otherwise someone could rest 1 lot to hold the front of the queue, then amend it to 10,000 lots and jump ahead of everyone behind.
- Price change: removed from the old level and re-entered at the new price; if the new price crosses the opposite side, it trades immediately as an aggressor.

## Opening: confirm the rules that change the code

What follows is a mock interview for practicing the reasoning; it does not represent any company's fixed problem or schedule. Suppose the IDE contains a single comment:

> `// Implement an in-memory matching engine supporting add, cancel, and modify.`

**Interviewer:** "Let's write a matching engine. The input is new-order, cancel and amend messages, and downstream is notified of trades. Define the interface yourself. Don't start coding yet; tell me what you're thinking."

Candidates who start writing `struct Order` as soon as they hear the problem often find halfway through that they misunderstood the trade price or the amend semantics, and have to rewrite. Ask first about the rules that change the code's structure.

**Candidate:** "Before designing the data structures, I'd like to confirm a few rules:

1. Priority and trade price: price priority, then time priority, and a crossing order trades at the resting order's price, right?
2. Order types and operations: the first version supports new order, cancel and amend, with GTC and IOC time in force, and leaves FOK and iceberg orders as extensions. Is that fine?
3. Amend quantity: is it the target total quantity or the new remaining quantity? I'd suggest the total including what has already filled, so a client that has not yet received a partial-fill report can still state exactly how much it wants in total.
4. Price and quantity: prices parsed into integer ticks, as signed `int64_t`, allowing 0 and negative values (calendar spreads have them); a single order's quantity as `uint32_t`, and a level's total as `uint64_t` so that several large orders added together cannot overflow.
5. Symbols and ids: first write a correct single-symbol book, then wrap it in a multi-symbol router; ids of orders currently resting in the same symbol must be unique. If every id used in the session must be rejected, add a separate history table for duplicates.
6. Return values and callbacks: a `Result` enum distinguishes success from each failure reason; trades are reported by a synchronous callback through a template parameter `Listener`. The callback may run queries, but may not add, cancel or amend orders, and may not throw. Does that work?"

Once you agree, write the conclusions down as a table and check each one while coding:

| Rule | Convention on this page | Where it affects the code |
|---|---|---|
| Matching and pricing | Price then time priority, at the resting price | Sort direction of each side, FIFO queue per price, `Trade::price` |
| Time in force | GTC remainder rests; IOC remainder is discarded | One branch after matching |
| Amend quantity | Target total, including what has filled | Each order records its cumulative fill `cum` |
| Amend queueing | Same-price decrease keeps position; same-price increase goes to the back; a price change re-enters | `std::list::splice`, or unlink and relink; a price change reuses the new-order path |
| Id uniqueness | The main text checks against active orders within a symbol; appendix D implements a session-wide history check | One active index is enough, or add a history set |
| Numeric types | `Price = int64_t`, `Quantity = uint32_t`, `Volume = uint64_t` | No floating-point error, no overflow of level totals |
| Failure conditions | New order with quantity 0, duplicate active id, cancel or amend of an unknown id, pool full, unknown symbol | Return `Result`, so the caller can tell the reasons apart |
| Callback | Template parameter `Listener&`, called synchronously; read-only queries allowed, no modifying the engine, no exceptions | Callbacks in the matching loop can be inlined, with no reentrancy guard or exception rollback |

### Why each question is asked

The interviewer will often ask "why do you need to know that?" For each question you should be able to say which part of the code it changes:

- Matching rule: with time priority, one queue per price level is enough, and matching looks only at the front of the queue. The alternative is pro-rata allocation, used in some futures markets: at one price level, the traded quantity is split in proportion to each resting order's size. For example, buy orders of 300 lots and then 100 lots rest at 100, and a sell order for 200 lots arrives: under time priority all 200 lots go to the first order; under pro-rata the two get 150 and 50 lots. Matching then has to walk the whole level, compute shares and handle the rounding remainder, so both the data structure and the matching loop differ.
- Price type: prices cannot be `double`. Binary floating point cannot represent most decimal fractions exactly, so `0.1 + 0.2 != 0.3`; prices are keys of an ordered container and decide whether two orders are at the same level, and rounding error can split one price across two levels. So the input is parsed directly from the string into integer ticks, without going through `double`. In a trading-firm interview, storing prices as `double` usually draws a follow-up question.
- The scope in which ids are unique: if ids only need to differ among orders resting at the same time, a lookup in the order index is enough. If they must be unique for the whole run, the engine has to remember every id ever used, even for orders long since filled or canceled; this table grows with the number of messages, and the measurements later show how expensive it is. If the protocol requires increasing ids, the duplicate check is a single comparison with the previous id. Real systems mostly make ids unique per client per trading day, require them to increase, or have the engine assign separate internal numbers.
- What is reported, and how it reaches downstream: only trades, or a report for every message (accepted, partially filled, filled, cancel confirmed, rejected)? The kinds of event decide how many functions the callback interface has. The delivery mechanism affects both performance and correctness: a virtual function or `std::function` is an indirect call each time; with the downstream as a template parameter, the compiler can inline the callback; the engine can also write events into a preallocated buffer that the caller reads after each message.
- The order of reject checks: which error is reported when a message has several, and whether a rejected new order counts as having used its id. The latter decides whether the duplicate table is updated only after every check passes, or as soon as the message arrives. The protocol in appendix D specifies: check fields first, then duplicates, then unknown ids; a rejected new order does not use up its id.

There is also a boundary at the entry point: the `Quantity` the engine accepts is unsigned. If the external protocol is text (appendix D), negative numbers, integers that are too large and too many decimal places must be stopped in the parsing layer; you cannot convert `"-5"` to `uint32_t` and expect the order book to discover it was negative.

## Deriving the data structures from the operations

**Interviewer:** "The rules are clear. What data structures will you use?"

Give a structure that meets the requirements using the STL first, explaining the operations and their complexity, and then discuss memory allocation and caches. That way each later replacement has a clear target.

The interviewer does not want to hear you recite "`map` plus `list` plus a hash table". They want to see you start from the operations to be supported and derive why each structure is the way it is. List the operations first, with an estimate of how often each occurs:

| Operation | Input | What it does | Frequency |
|---|---|---|---|
| Match | A new order | Repeatedly take the best opposite level, trade with its resting orders in arrival order, move to the next level when one is emptied | Checked for every new order; trades only when it crosses |
| Rest | Remaining quantity, price | Find the level for this price, create it if absent, append to the back of the queue | Most new orders |
| Cancel | Only the id | Find the order, remove it from the middle of the queue; erase the level if it becomes empty | Very high; in real markets cancels far outnumber trades |
| Amend | Id, price, quantity | Same-price decrease in place; otherwise cancel and rest again | Moderate |
| Snapshot | None | Print each level's total and order count in price order | Rare |

There is also a fact about distribution: the vast majority of operations happen near the top of the book, within a few ticks of the best price. The later optimizations rely on this.

### STL baseline

The containers follow from the order book's three most frequent operations:

1. Matching repeatedly needs the best opposite price, so price levels must be sorted. The bid side uses a descending `std::map<Price, Level, std::greater<Price>>` and the ask side an ascending `std::map<Price, Level, std::less<Price>>`; on both sides `begin()` is the best price.
2. Orders at the same price trade in arrival order, and a cancel has to remove an arbitrary order from the middle. `std::queue` only works at its ends, so use the doubly linked list `std::list<Order>`: rest at the back, trade at the front; inserting or erasing other nodes leaves existing iterators valid.
3. Cancels and amends give only an id, and cannot scan the whole book. Add a hash index `std::unordered_map<OrderId, std::list<Order>::iterator>`; from the list iterator, read the side and price from the order, find the level, then unlink the node.

```text
OrderId ──hash index──→ list node iterator
                         │
                         ├─ side (buy / sell)
                         └─ price ──→ FIFO doubly linked list of that price's Level

bids (highest first)           asks (lowest first)
std::map<Price, Level, >       std::map<Price, Level, <>
```

| Operation | Cost in the STL baseline (P = number of levels on that side) | Notes |
|---|---|---|
| Get best bid and ask | O(1) | `begin()` of an ordered container is constant time |
| Rest an order at a price | O(log P), plus O(1) list append | Find or create the level in the red-black tree |
| Cancel by id, same-price amend | Hash O(1) average, find level O(log P), unlink O(1) | The index stores only the order's iterator, so `map.find(price)` is still needed to adjust the level total and erase an empty level |
| An aggressor consumes K resting orders | Amortized O(K + E) | E is the number of levels emptied; erasing a level by iterator is amortized O(1) |

A cancel cannot simply be called O(1). If the interviewer asks how to remove the O(log P) from cancels, the index can also store a `Level*` or the `map` iterator. Nodes of `std::map` do not move when other elements are inserted or erased, so adjusting the total becomes O(1), and erasing an empty level by iterator is amortized O(1); the cost is one more piece of location data to maintain.

### Constant costs of the baseline

When the interviewer goes on to ask about latency, analyze the constants:

**Candidate:** "The complexity of this structure is good enough; it is slow in the constants, in three main places:

| Cost | STL baseline | Replacement |
|---|---|---|
| Heap allocation on the hot path | Every resting order allocates a list node and a hash node (a small allocation plus free is about 20 ns, see [[perf/allocation\|memory allocation]]); a new price level also allocates a red-black tree node | Preallocated object pool and reserved capacity: the node pool removes the per-order node allocation; the index, levels and callback each need checking separately |
| Indirection in queues and the index | List nodes and hash nodes are scattered across the heap; with a deep book, following pointers is more likely to reach data not in cache | An intrusive list with 32-bit indices and an open-addressing hash table: order nodes are 32 bytes and hash slots 16 bytes, stored contiguously |
| Finding and erasing levels | The red-black tree follows a pointer between parent and child at each step | A sorted array with the best price at the end (or a bounded price-offset array plus a bitmap): emptying the best level is a single `pop_back()` |

I'd write the STL version first and get matching, cancels and amends working, then replace it step by step with an object pool, an open-addressing hash table and sorted arrays, using differential tests at each step to confirm the external behavior is unchanged."

### Two details that are easy to get wrong

When you actually write the code, two details are where people most often get stuck or plant bugs.

First, `std::map::operator[]` inserts when the key is missing: if `price` is not found, `bids_[price]` inserts a default-constructed `Level` (total 0, empty queue) and returns a reference to it. When resting an order, that is exactly what is needed: append if the level exists, create it if not. But writing `bids_[price]` in a read-only query such as `bid_volume_at(price)`, or in a cancel, means that querying a nonexistent price leaves an empty level on the book, and `best_bid()` then becomes that price. Read-only queries and modifications of elements known to exist should use `find()`, or `at()` when existence is certain.

Second, inserting 99 between 100 and 98 does not require changing other levels. What gets confused here is the first, second and third bid shown in market data, which are ranks; inside the engine each level's key is the price itself, holding only an order queue and a total. After 99 is inserted, 100 is still 100 and 98 is still 98; the container is sorted by price, so iterating outward from the best price naturally yields 100, 99, 98.

### Follow-ups

**Interviewer:** "Why not `std::priority_queue`?"

A heap gets the best price quickly but cannot remove an element from the middle, so it cannot cancel. Lazy deletion (only marking an order, and discarding it when it rises to the top) keeps canceled orders in memory, and in real markets cancels far outnumber trades. Time priority within a level would also require encoding the arrival sequence number into the comparison key.

**Interviewer:** "Are the positions stored in the hash table still valid after other orders are inserted and erased?"

Yes, because the containers are node-based. Inserting into `std::map` and `std::list` does not affect existing iterators and references, and erasing affects only the erased element ([[associative.reqmts.general#175]], [[list.modifiers#3]]); a rehash of `std::unordered_map` invalidates iterators but leaves pointers and references to elements unchanged ([[unord.req.general#9]]). With `std::vector` this would not work, since one reallocation invalidates every reference ([[vector.modifiers#2]]). The object pool later stores indices rather than pointers for the same reason, so that this rule does not constrain it.

**Interviewer:** "What are the invariants of your structure?"

Seven:

1. After each message, the book is uncrossed: the highest bid is strictly below the lowest ask.
2. Levels on each side are strictly ordered, and no two levels have the same price.
3. Each level's total equals the sum of its orders' remaining quantities, and its count equals the number of orders.
4. The book has no empty levels and no orders with a remaining quantity of 0.
5. The ids in the order index are exactly the ids of all resting orders, and they point to those orders.
6. After switching to an object pool: every node in the pool is either on the book or on the free stack, never in neither (a leak) and never in both.
7. The queue at each level is in arrival order, and an amend that loses priority counts as a new arrival.

The first six can be checked directly in code (the "How to verify" section does exactly that); the seventh needs test cases. There is also a conservation relation across messages: each order's original quantity equals the sum of its filled, remaining and canceled quantities, which tests can tally from the event stream.

## Version 1: the single-book STL implementation

First put the types shared by every version in `types.hpp`. The STL version, the pool version, the optimized version and the multi-symbol layer all use this set of types, which makes direct differential comparison possible:

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

- A single order's `Quantity` is a 32-bit unsigned integer, with an upper limit of about 4.29 billion; a level's total `Volume` is 64 bits. Two orders of `UINT32_MAX` at the same price already exceed 32 bits.
- The interface allows an id of 0. When we later write our own open-addressing hash table, we cannot casually use 0 as the empty-slot marker, or a valid order 0 would be rejected; `IdMap` handles this.
- Of the four fields of `Trade`, both ids are `OrderId`, and the price and quantity are both integers. Constructing it positionally, as in `Trade{resting_id, id, price, qty}`, would compile even with the two ids swapped, so this page always constructs trade events with designated initializers, `Trade{.resting_id = ..., .incoming_id = ...}`, where a wrong field order fails to compile. Tests still compare trade sequences positionally, because there the order is exactly what is being checked.

### New order: match first, then handle the remainder

The public entry point `add_order` only validates and checks for duplicates, then hands off to the private function `submit`. `submit` takes an extra cumulative fill `cum` so that price amends can reuse it; an external caller cannot fabricate how much an order has already filled.

```cpp
Result add_order(OrderId id, Side side, TimeInForce tif,
                 Price price, Quantity quantity) {
    if (quantity == 0) return Result::InvalidQuantity;
    if (lookup_.contains(id)) return Result::DuplicateId;
    return submit(id, side, tif, price, quantity, 0);
}

Result submit(OrderId id, Side side, TimeInForce tif, Price price,
              Quantity leaves, Quantity cum) {
    // 1. Match against the opposite side: the side is checked once, on entry
    if (side == Side::Buy)
        match(id, price, leaves, cum, asks_, std::greater_equal<Price>{});
    else
        match(id, price, leaves, cum, bids_, std::less_equal<Price>{});

    // 2. Handle the remainder: GTC rests on its own side, IOC is discarded
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

The two sides differ only in sort direction and crossing condition, so there is no need for two matching loops. A buy order passes `asks_` and `>=`, a sell order passes `bids_` and `<=`, and the same `match` handles both:

```cpp
template<class Book, class Cross>
void match(OrderId id, Price price, Quantity& leaves, Quantity& cum,
           Book& opposite, Cross can_cross) {
    auto it = opposite.begin();
    while (leaves != 0 && it != opposite.end()) {
        if (!can_cross(price, it->first)) break; // if the best price does not cross, no later level will
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

The outer loop walks price levels and the inner loop walks orders at one level. A few points about order of operations:

- The trade price is `match_price`, the resting order's level `it->first`, not the aggressor's limit `price`.
- A fully filled resting order is removed from `lookup_` and from the queue before `on_trade` is called; for that, `resting_id` and `match_price` are first copied to locals. The outer layer can then call `contains(resting_id)` inside the callback to learn whether the resting order has left the book, which the global routing in appendix D relies on. But when the callback runs, the level may not have been erased yet and the aggressor has not yet rested, so the message is not fully processed. The callback may therefore only run queries of this kind; it may not modify the engine, nor traverse the book assuming every invariant has been restored.
- When a level is emptied, advance with `it = opposite.erase(it)` and leave no empty level behind; otherwise the next `begin()` returns a level with total 0.

### Cancels and iterator invalidation

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

`remove` finds the level by price, subtracts from the total, and erases the list node; if the level becomes empty it is erased too. The `Position` stored in `lookup_` is a `std::list<Order>::iterator`; when `lookup_` itself rehashes, list nodes do not move and this iterator stays valid. Conversely, the `it` in `cancel_order` is the hash table's own iterator, and nothing is inserted into `lookup_` before `lookup_.erase(it)`, so it is safe as well. The invalidation rules for rehashing are in [[unord.req.general]].

### Follow-ups while writing code

**Interviewer:** "What happens if someone calls `cancel_order` inside the trade callback?"

The matching loop is holding an iterator to the current level and a reference to the opposite side. If the callback cancels the remaining orders at this level, or a price amend makes the level table reallocate, the loop uses destroyed objects when it resumes, which is undefined behavior. You can state explicitly that the callback may not modify the engine and check it with a flag in debug builds, or have the engine only write events into a buffer and dispatch them after the whole message is processed. In real systems every external request becomes a queued message, and a callback can only send messages.

**Interviewer:** "Can quantities or amounts overflow?"

A single order's quantity is 32 bits and a level's total uses 64 bits: even a million orders of the maximum quantity at one level total less than 2⁵³. The traded amount is price times quantity: an `int64_t` price times a 32-bit quantity can exceed `int64_t` once the price's absolute value goes beyond about 2³¹ ticks, and signed overflow is undefined behavior, so either limit the price range or check with 128-bit integers or `__builtin_mul_overflow`. Unsigned quantities have another trap: `a - b` wraps around to a huge number when `b > a`, which is harder to notice than overflow; that is why the amend compares `new_total <= cum` before subtracting.

**Interviewer:** "Which edge cases haven't you tested yet?"

One order sweeping through several levels; an exact full fill, which neither rests nor leaves an entry in the index; a level erased once it is emptied by trades or cancels; an amend that crosses the opposite side; a cancel after an amend that filled completely, which should return unknown id; an amend whose new total does not exceed the filled quantity, which must end the order rather than rest one with a wrapped-around quantity; carrying the cumulative fill through a price amend, and remembering what an aggressor has already filled when it rests after a partial fill; a rejected new order not using up its id; canceling an order from the middle of a queue.

## Version 2: amends by total quantity

Once the first version works, add `modify_order`. One question needs thinking through first: when a client sends an amend, the fill state it sees may already be out of date.

### Why the target total

A timeline shows how fill reports and amends interleave:

1. The client rests buy order #1 for 100 lots. In the engine: remaining 100, cumulative fill 0.
2. A sell order takes 80 lots of #1. The engine sends a fill report, but the report is still in transit and the client has not received it. In the engine: remaining 20, cumulative fill 80.
3. The client decides 100 lots is too many and wants to lower the total purchase to 60 lots, sending `modify_order(1, px, 60)`.
4. This amend reaches the engine.

If 60 were written into the order as the new remaining quantity, then after more sell orders arrive the client would end up buying 80 + 60 = 140 lots: it meant to buy less and bought more.

In this problem each order records its cumulative fill `cum`, an amend carries the target total `new_total`, and the new remaining quantity is:

```text
new_leaves = new_total - cum
```

In the scenario above `new_total` (60) is not greater than `cum` (80), meaning the filled quantity has already reached the client's new target, so the engine cancels the remaining 20 lots. The 80 lots already filled cannot be undone and remain valid. `Quantity` is unsigned, so you cannot compute `60 - 80` first and then check, because that wraps around to over four billion; check `if (new_total <= order.cum) return cancel_order(id);` first, cancel if it holds, and subtract only otherwise.

What is handled here is a difference in state caused by messages crossing in the network. The engine always processes messages in order on one thread, and no two threads modify the order book at once, so this has nothing to do with data races.

The FIX protocol's amend (OrderCancelReplaceRequest) uses the total quantity, as do most FIX-based interfaces, precisely because the remaining quantity a client sees when it sends an amend may be out of date. Another design splits decreases from other amends into two messages, as in Nasdaq's OUCH protocol: a decrease uses a partial cancel that can only reduce quantity and states the target remaining quantity, and when the target is not below the current remaining quantity nothing changes, so it always keeps its queue position; increases and price changes must use a replace message, which creates a new order that always queues again. The engine then never has to guess whether the client wants more or less. Total-quantity semantics is not the only design; implement the message semantics the problem specifies, and do not guess the meaning of a quantity from a function name.

### Amends after a partial fill

Suppose a buy order was originally for 100 lots, 40 have filled before the amend arrives, 60 remain on the book, and the price does not change:

| `new_total` | New remaining `new_total - 40` | Compared with current remaining 60 | Action |
|---|---|---|---|
| 150 | 110 | Larger | Remaining becomes 110, level total grows by 50; moves to the back of the queue at that price |
| 80 | 40 | Smaller | Remaining becomes 40 in place, level total shrinks by 20; keeps its queue position |
| 40 | 0 | Zero | Cancel the remaining 60 lots; the order leaves the book |
| 20 | `new_total < cum` | Filled quantity exceeds the target | Cancel the remaining 60 lots; the 40 lots filled stand |

### Implementing amends

```cpp
Result modify_order(OrderId id, Price new_price, Quantity new_total) {
    auto it = lookup_.find(id);
    if (it == lookup_.end()) return Result::UnknownId; // fully filled and gone, or already canceled
    Order& order = *it->second;
    if (new_total <= order.cum) return cancel_order(id);
    Quantity new_leaves = new_total - order.cum;

    // Same price: a decrease is applied in place, an increase moves to the back with splice
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

    // Price changes: copy the fields, cancel, then match or rest again carrying the cumulative fill
    Side side = order.side;
    Quantity cum = order.cum;
    cancel_order(id);
    return submit(id, side, TimeInForce::GTC, new_price, new_leaves, cum);
}
```

Three points need explaining:

1. A same-price increase uses the single-node `list::splice`. It only changes the list's link pointers to move the node to the back, with no allocation; the node is still the same node, so the iterator stored in `lookup_` needs no update. The standard specifies this overload as constant time with iterators remaining valid, see [[list.ops]]. A same-price increase also needs no rematching: the order was already resting at this price, which means it does not cross the opposite side.
2. For a price change, copy before canceling. `cancel_order(id)` destroys the list node, after which the reference `order` dangles, so first copy `side` and `cum` to locals, then cancel and call `submit`.
3. An aggressor that fills partly and then rests must carry its `cum`. The ask side has 3 lots resting; a new buy order #2 for 10 lots first takes the 3 lots as aggressor, and the remaining 7 lots rest on the bid side. At that point #2's `cum` should be 3, not 0. Otherwise, if the client later amends the total to 5, the engine would leave 5 lots, while the correct answer is 5 − 3 = 2 lots. `match` accumulates the aggressor's `cum` as it goes and passes it to the resting node precisely for this path.

The complete STL version is in appendix A.

## Version 3: multiple symbols

A buy order for `AAPL` cannot trade with a sell order for `MSFT`. Once the single-symbol book is correct, supporting multiple symbols needs no change to the matching algorithm, only an outer routing layer `MultiEngine`: symbols are registered in advance and each book is given its capacity; requests are dispatched by symbol on arrival; an internal listener adapter adds the symbol name to each trade and passes it downstream.

```cpp
Result add_order(const std::string& symbol, OrderId id, Side side,
                 TimeInForce tif, Price price, Quantity quantity) {
    auto it = books_.find(symbol);
    if (it == books_.end()) return Result::UnknownSymbol;
    return it->second->book.add_order(id, side, tif, price, quantity);
}
```

Each book and its listener adapter are owned by a `std::unique_ptr<Entry>`. A book holds a reference to its listener, and the STL version also holds iterators into its own lists, so a book can be neither copied nor moved; inside a `unique_ptr`, existing objects do not relocate when more symbols are registered. Note that a rehash invalidates the hash table's iterators but does not change the addresses of its elements; these two guarantees need to be kept apart. The complete code is `multi_engine.hpp` in appendix B.

If the symbol name arrives at the entry point as a `std::string_view` (for example pointing straight into a network buffer), `books_.find(symbol)` first has to construct a `std::string`. Since C++20, giving `std::unordered_map` a hash and an equality function with `is_transparent` allows lookup directly with a `string_view`. The more common approach is to convert symbol names to integer numbers at the gateway, so matching never looks up a string table at all; the timing program in appendix E does this.

**Interviewer:** "If cancels and amends don't carry a symbol, as in appendix D's protocol, which has only `CANCEL id` and `AMEND id price qty`, how do you know which book to go to?"

Answer in two steps:

1. Confirm the precondition first: if a cancel does not carry a symbol, the protocol must guarantee that ids are unique across all symbols. Otherwise, with a #1 in two books, the id alone cannot determine which one to cancel.
2. Then give the structure: the outer layer maintains a global routing table `route: OrderId → book index`. If a new order is still resting after matching (`book.contains(id)` is true), it is added to the route; when a resting order is filled completely, canceled, or leaves the book after an amend, it is removed from the route. If every id accepted in the session must also never be reused, add an insert-only history set `used`. `cli.cpp` in appendix D implements how the route, the history check and capacity rejects work together.

## Version 4: replacing the data structures step by step

**Interviewer:** "The single-book and multi-symbol logic are both correct. If throughput and tail latency need to improve by an order of magnitude, what do you change?"

What follows replaces the order queues, the id index and the level table in four steps, ending with `FastBook` in appendix B. Under the same capacity conventions it must produce the same acceptance results, trade events and snapshots as the STL version; whether it is faster has to be measured separately.

### Step 1: replace the order queues with an object pool

First remove the most frequent allocation, the list node. At construction, allocate a `std::vector<Node>` once as a fixed-capacity object pool, and chain orders at the same price into a doubly linked list using 32-bit indices instead of 64-bit pointers; free indices are kept on a stack `free_` for reuse. A list whose links live directly in the business object like this is an **intrusive list**.

```cpp
using Index = std::uint32_t;
static constexpr Index nil = UINT32_MAX;

// node is 32 bytes; cache line size depends on the target platform
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

The free stack is pushed in reverse, from `capacity - 1` down to 0, so the first indices popped are 0, 1, 2, … and initially resting orders are contiguous in the array. After many cancels and reuses, adjacent orders in a queue are not necessarily at adjacent addresses, but they all live in the same preallocated block. The node pool never grows after construction, so node addresses are stable.

The main logic barely changes; the `std::list` operations are replaced one for one:

| Operation | `StlBook` | `PoolBook` / `FastBook` | Difference |
|---|---|---|---|
| Position handle | `std::list<Order>::iterator` (8 bytes in common 64-bit implementations) | `uint32_t` index (4 bytes) | Half-size handle, stable address |
| Append to the queue | `level.orders.push_back(Order{...})` | Pop `free_.back()`, fill in the fields, `append(level, index)` | No allocation for order nodes |
| Read the front | `level.orders.front()` | `nodes_[level.head]` | Addressing by index |
| Remove and recycle | `level.orders.erase(pos)` | `unlink(level, index)`, `free_.push_back(index)` | No deallocation; the slot is reused immediately |
| Same-price increase | `level.orders.splice(end, orders, it)` | `unlink`, update quantity, `append` | Only integer indices change |

When writing `append` and `unlink`, decide who updates the level total, or it is easy to add twice or forget to subtract. Here `append` adds `node.leaves` to `level.total`, and `unlink` only changes links and does not touch quantities:

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

Call sites always subtract the old quantity first, then add the new one:

```cpp
bool increase = new_leaves > node.leaves;
if (increase) unlink(level, index);
level.total -= node.leaves;
node.leaves = new_leaves;
if (increase) append(level, index);
else level.total += node.leaves;
```

For example, if the level total is 7, of which the current order has 3 lots, and it is amended to 6 lots, the result must be 7 − 3 + 6 = 10. Do not add the difference to the total first and then let `append` add the new quantity again.

#### Can a full pool accept new orders

Suppose the object pool has a capacity of only 1, the book already has "sell 10 lots at 100" resting, and the pool is full. A new buy order arrives:

| New buy order | Matching and slots | Result |
|---|---|---|
| Buy 5 lots at 100 | The new order fills completely; the old sell has 5 lots left; no new slot needed | `Ok` |
| Buy 15 lots at 100 | The old sell is filled completely, returning 1 slot; the new order has 5 lots left and rests in that slot | `Ok` |
| Buy 15 lots at 99 | Does not cross; the remainder needs to rest but there is no free slot | `CapacityExceeded` |

So you cannot reject every new order before matching just because the pool is full. In this problem a full pool may still trade; only after matching, once it is confirmed that a GTC remainder needs to rest, is a free slot checked for. If the business rule says to reject everything once the pool is full, that is a different admission policy.

The interviewer may follow up: could part of an order trade, then find no slot when resting the remainder, return failure and leave a half-finished state? Under the current rules (single thread, no reentrancy, no iceberg replenishment) this path cannot be reached. If any trade happened and the new order still has a remainder, at least one old resting order was filled completely and returned its slot; matching only returns slots and never takes them, so when the remainder rests there is at least the one just freed. A price amend is the same: canceling returns one slot before the order rests again. This argument depends on the current rules; adding iceberg replenishment, reentrant callbacks or any other path that allocates nodes in the middle of matching would require checking it again.

The intermediate version that replaces only the order queues is `pool_book.hpp` in appendix B.

### Step 2: replace the id index with an open-addressing hash table

`PoolBook` removed the list node allocations, but in common implementations each element of `std::unordered_map` is still a separately allocated node, and a lookup reads the bucket first and then jumps to the node. Calling `reserve` does not create these nodes in advance either.

Step 2 replaces the index with `IdMap`, an open-addressing hash table with linear probing: all key-value pairs live directly in one contiguous array `slots_` whose length is a power of two, each slot 16 bytes (an 8-byte `OrderId` and an 8-byte `Locator`), and a collision moves on to the next empty slot. Empty slots are marked with `UINT64_MAX`, and the entry whose id is exactly `UINT64_MAX` is kept separately in an `optional`, so every id from 0 to `UINT64_MAX` is valid.

Two algorithmic details need explaining:

1. The hash function. Order ids are often consecutive integers such as 1, 2, 3; taking them modulo the capacity directly puts adjacent ids in adjacent slots and forms long runs of collisions. Multiplying by `0x9E3779B97F4A7C15` (2⁶⁴ divided by the golden ratio) and taking the high bits scatters consecutive integers with a single multiplication. This is called Fibonacci hashing.
2. Deletion. When a linear-probing table deletes position `i`, it cannot simply mark it empty: elements that were pushed further along because `i` was occupied would make a lookup stop early at the empty slot `i` and not be found. One approach leaves a deletion marker (a tombstone), but then the markers must be kept from accumulating and cleaned up periodically. Here we use backward-shift deletion: after clearing `i`, scan forward through the same run of occupied slots; if the ideal position `h` of the element in slot `j` is not in the circular interval `(i, j]`, it skipped past `i` when inserted, so move it back to `i` and continue scanning with `j` as the new hole, until a truly empty slot is reached. In unsigned arithmetic the condition is `((j - h) & mask) >= ((j - i) & mask)`. The table then has no deletion markers, and a lookup can stop at the first empty slot.

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

### Step 3: replace the level table with sorted arrays

Each level in `std::map` is a red-black tree node: creating a level allocates memory, and finding an adjacent level follows pointers through the tree. Step 3 replaces the level table on both sides with a contiguous `std::vector<Level>` and puts the best price at the end of the array:

- `bids_` is sorted by price ascending, for example `[98, 99, 100]`, with the highest bid at `bids_.back()`;
- `asks_` is sorted by price descending, for example `[104, 103, 102]`, with the lowest ask at `asks_.back()`.

The best price goes at the end because most operations happen near the top of the book:

- An aggressor that empties the best opposite level only needs `pop_back()`, moving no other elements;
- Creating or erasing a level near the top of the book only moves the last few `Level`s (`Level` is 32 bytes in this implementation). With the best price at index 0, every change at the top would move the whole array.

Finding a level by price uses binary search with `std::ranges::partition_point`:

```cpp
// levels run from worst to best, best price at back(); returns the first position not worse than px
template<Side S, class Vec>
static auto lower(Vec& levels, Price px) noexcept {
    return std::ranges::partition_point(levels, [&](const Level& l) {
        return better<S>(px, l.price);
    });
}
```

If the returned iterator satisfies `it != own.end() && it->price == px`, the level already exists; otherwise inserting a new level at `it` keeps the array sorted.

This step has a precondition, and you should state it yourself: a sorted array beats a red-black tree when there are few active levels, or when operations concentrate near the top of the book. If a symbol has tens of thousands of levels and cancels land uniformly far from the top, each erase from the middle of the array moves O(P) elements and may be slower than `std::map`. More comparisons are in [[perf/choosing-containers|choosing containers]].

If the interviewer asks whether even the binary search can go: when a symbol's valid price range for the day is bounded (for example a few thousand to tens of thousands of ticks between the price limits), `price - base_price` can be used directly as an array index to find the level in O(1). So that emptying the best level does not require stepping through empty levels one at a time, add a bitmap with one bit per non-empty level, and use `std::countr_zero` or `std::countl_zero` to jump to the next non-empty level; for a larger range use a two-level bitmap, where 64 × 64 = 4096 levels take only two bit operations. A compromise is to use an array only for a band of prices near the top of the book and keep distant orders in an ordered container. You need to say how prices outside the range are handled, and whether a sparse range wastes memory.

If asked about node size and hot and cold fields: the `Node` here is only 32 bytes, so the 64-byte cache line common on x86 holds two (the test machine's M2 Pro has 128-byte cache lines). Orders in real systems also carry the account, client order id, timestamps and risk flags, often over a hundred bytes, while the matching loop uses only `leaves`, `cum`, `id` and `next`. The rarely used fields can be moved to another array indexed by the same index, reducing the data brought into cache during matching; whether it helps has to be measured, see [[perf/memory-hierarchy|the memory hierarchy]].

### Step 4: reserve capacity before the open

The node pool has a fixed size and returns a capacity error when it runs out. The level arrays and the outer `IdMap` still grow; when a message triggers growth, the whole cost of allocating and moving falls on that one message.

At construction, reserve based on the expected numbers of resting orders and levels:

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

`expected_levels` is only a reservation, not a limit; when the number of levels exceeds it the `vector` still grows. A fixed node pool also does not mean the whole process stops allocating: the outer routing table, the duplicate-id history table and the listener have to be checked separately. If no allocation at all is allowed during trading hours, you also need to define a limit for each resource and what happens when it is exceeded, and touch that memory in advance at startup.

None of these implementations roll back after an allocation failure. The listener may not throw; when allocation fails, you cannot catch the exception, treat it as an ordinary reject, and keep using the engine. If the service must continue after a failure, either acquire every resource before modifying state, or design rollback-capable state updates with an event buffer that commits later.

### Measurements

**Interviewer:** "You say contiguous storage is faster. Did you measure it?"

`bench.cpp` in appendix E drives the two implementations with the same outer rules as `cli.cpp` in appendix D (8 symbols, global routing, session-wide id duplicate check). Messages are generated in memory in advance, parsing and output are not timed, and trades go to a listener that only computes a hash. Before timing, it confirms that the two implementations produce exactly the same trades and final snapshots.

The test machine is an Apple M2 Pro (16 GB of memory), macOS, Homebrew Clang 23 with libc++, `-std=c++20 -O2 -DNDEBUG`. The message stream is generated as follows:

- 8 symbols, each with its own random-walk mid price;
- 85% of new orders are placed 1 to 20 ticks outside the mid price and 15% cross the mid by 0 to 3 ticks, so most of the latter trade immediately;
- during generation the STL version tracks which orders are resting, and cancels and amends target only resting orders, 70% of them among the 32 most recently placed, simulating constantly refreshed quotes; the number of orders on the book is steered toward a target;
- 10 million messages for each depth. The shallow book has about 8,000 resting orders and produces 1.58 million trades; the deep book has about 800,000 resting orders and produces 5.09 million trades.

Each symbol's node pool is sized at twice the target number of resting orders, and both implementations have the same capacity. Throughput is the fastest of 5 repetitions; the whole program was run 3 times, and the table shows the median of the 3 runs:

| Average time per message | Shallow book (about 8,000 resting orders) | Deep book (about 800,000 resting orders) |
|---|---:|---:|
| `StlBook`, outer layer with `std::unordered_map` | 150 ns | 371 ns |
| `FastBook`, outer layer with `IdMap`, capacity reserved | 67 ns | 109 ns |
| `FastBook`, increasing ids required (`id <= last` is a duplicate) | 42 ns | 95 ns |
| `FastBook`, no duplicate check | 42 ns | 95 ns |
| `FastBook`, outer layer without reserved capacity | 74 ns | 113 ns |

Several things are worth noting.

First, the gap is larger with a deep book: the time per message falls to less than half with a shallow book and to less than a third with a deep one. The nodes of 8,000 orders fit in cache, so the STL version's pointer chasing mostly hits; with 800,000 orders, the STL version's list nodes and hash nodes are scattered across the heap, while `FastBook`'s node pool is only about 51 MB and contiguous, and its levels are in contiguous arrays too. Whether following pointers is slow depends on how much data there is.

Second, the largest share of the remaining time is not in the data structures but in the requirements. "Reject any id used in the session" requires the duplicate table to hold every accepted id, several million of them over 10 million messages, far beyond the cache, so almost every new order pays one cache miss. Requiring increasing ids instead makes the duplicate check a single comparison with the previous id, taking the shallow book from 67 ns to 42 ns and the deep book from 109 ns to 95 ns, as fast as no check at all. This step cannot be made in code: either the protocol requires increasing ids, or duplicates are checked only within one trading day and the table is cleared daily. It is worth raising with whoever sets the requirements.

Third, beyond the average you need to look at the tail. The tables below time each message individually. On this machine `steady_clock` advances in steps of about 41 ns, and one `now()` call itself takes over ten nanoseconds, so the p50 column only takes the values 42, 83 and 125 and shows only the order of magnitude; p99.9 and the maximum vary a lot between the three runs and are given as ranges.

| Shallow book | p50 | p99 | p99.9 | Maximum |
|---|---:|---:|---:|---:|
| `StlBook` | 125 ns | 333 ns | 1.0–1.3 µs | 0.2–1.1 ms |
| `FastBook`, capacity reserved | 83 ns | 208–250 ns | 1.0–3.5 µs | 0.1–5.3 ms |
| `FastBook`, capacity not reserved | 83 ns | 208 ns | 0.3–2.5 µs | 70–85 ms |
| `FastBook`, increasing ids required | 42 ns | 125 ns | 0.2–0.8 µs | 0.05–0.07 ms |

| Deep book | p50 | p99 | p99.9 | Maximum |
|---|---:|---:|---:|---:|
| `StlBook` | 167–250 ns | 1.6–2.5 µs | 2.9–25 µs | 1.9–9.0 ms |
| `FastBook`, capacity reserved | 125 ns | 500–625 ns | 2.6–5.0 µs | 1.7–8.5 ms |
| `FastBook`, capacity not reserved | 125 ns | 459–542 ns | 0.9–3.0 µs | 75–98 ms |
| `FastBook`, increasing ids required | 125 ns | 417–500 ns | 0.7–1.0 µs | 0.04–0.75 ms |

Without reserved capacity, the duplicate table keeps doubling as ids accumulate, and the last growth has to rehash several million elements into a new table of several hundred MB, so that one message waits tens of milliseconds, up to 98 ms over the three runs. For a matching engine such a stall is far worse than being a few nanoseconds slower on average, so capacity should be reserved before the open, never grown during trading hours, and monitored for how far it is from the limit.

Reserving has a cost too: the duplicate table is allocated for 10 million ids from the start, about 512 MB, and every lookup lands somewhere in that large region, so p99.9 is often higher than without reservation. The unreserved version has a small table during the first half, where lookups mostly hit the cache, and only pays for a few growths. With increasing ids the table does not exist at all, and the average, p99.9 and maximum are the best of the four. So the question for duplicate checking is not only whether to reserve; the better fix is to make the table small or remove it. Even with reservation, millisecond-scale maximums still occur occasionally and vary widely between runs; they may come from page faults, scheduling or other processes, and we did not find the cause.

You should also say what this benchmark does not measure: text parsing, network I/O, the message distribution of real market data, and books of several symbols competing for cache. Symbol lookup is not in it either: the timing program converts symbols to integer numbers at the entry point. An earlier version of this page looked symbols up by string, and sampling showed about 16% of the time spent hashing and comparing strings; real systems likewise convert symbol names to integers at the gateway.

The timing program `bench.cpp` is in appendix E. An earlier version also reserved the global routing table for 10 million ids; the routing and duplicate tables together took about 1 GB, and the p99 with reservation was several times worse than without. Only after the routing table was reserved at the total node pool capacity did we get the tables above. How much to reserve also depends on what each table actually holds.

Measurement method is covered in [[perf/measuring|measuring performance]]. A different machine or a different message distribution changes all of these numbers; to answer "how much faster", replay real message streams in the target environment.

## How to verify

**Interviewer:** "The code is written. How do you show it's correct? Especially after switching to the object pool and backward-shift deletion."

Testing one or two trades does not cover these state changes. Verification has four layers, which check the business rules, the internal structure, consistency between implementations, and memory errors.

### Deterministic cases

Structural checks cannot find problems such as whether orders at the same price trade first come, first served, so first construct, by hand, scenarios that just trigger and just fail to trigger each rule. `examples()` in appendix C and the 22 staged cases in appendix D cover:

- several orders queued at the same price, sweeping several levels, trading at the resting price;
- canceling the front, the middle, and the last order of a level, with empty levels erased;
- same-price decreases keeping position, same-price increases moving to the back;
- `new_total <= cum` after a partial fill canceling the remainder without wraparound;
- an aggressor that rests after trading and is then amended, and a price amend that trades at once and is amended again, with `cum` correct throughout;
- IOC discarding its remainder after a partial fill, zero and negative prices, the total of two `UINT32_MAX` orders at one price, the four paths of a full pool (full fill, reusing the slot after filling an old order completely, rejecting a non-crossing order, and resting again after a price amend returns a slot), and multiple symbols using the same id without mixing books.

### Invariant checks

`PoolBook` and `FastBook` both have a `check()`, which tests scan after every message, checking four invariants:

1. When both sides are non-empty, `*best_bid() < *best_ask()`; adjacent levels in the sorted arrays are strictly ordered; there are no empty levels and no nodes with a remaining quantity of 0.
2. In each level's list, the sum of the nodes' `leaves` equals `level.total`, and the number of nodes equals `level.count`.
3. Each node's `prev` and `next` agree, and the head and tail are correct; every active node can be found in `lookup_`, with matching index and side.
4. Active nodes and free slots do not repeat or overlap, and together cover exactly the whole pool. Checking only `active + free == capacity` is not enough: if one slot is returned twice while another is lost, the counts still match. The code in the appendix marks every visited index in a boolean array `seen`, and reports an error on an out-of-range or repeated index while walking the lists and the free stack, which also catches cycles.

The checker itself needs verifying too. We planted two bugs in `FastBook`, compared it against `StlBook` on the same kind of random message stream as appendix C (seed 1), and called `check()` after every message:

| Planted bug | Differential test | `check()` |
|---|---|---|
| A same-price decrease does not update the level total | Snapshot mismatch at message 182 | Fails at message 182 |
| One time in 97, an order leaving the book is neither removed from the index nor returned to the free stack | Still not found at message 611 | Fails at message 611 |

The first bug does not affect trades, only the totals in snapshots; the differential test compares snapshots at every step, so it caught this one at the same time. A test case that prints only the final snapshot would have to check right after the decrease to catch it. The second bug has no external effect at first: the leaked nodes just sit in the pool, and until they cause an inconsistency only `check()`, which checks the partition of the pool, can see them. `check()` allocates temporary arrays and scans the whole pool, so it is used only in tests.

### Three-way differential testing

Take `StlBook`, whose logic is simplest, as the reference. With a fixed seed, generate random new-order, cancel and amend messages, including positive, negative and zero prices, zero quantities, duplicate active ids and ids reused after leaving the book, and feed them to `StlBook`, `PoolBook` and `FastBook` at once (appendix C runs 100 × 1000 steps). At each step compare the three return values, trade sequences and full level snapshots, and call `pool.check()` and `fast.check()`.

If random testing finds a mismatch at step 2800: first reproduce it with the same seed; then shrink the input, cutting off the messages after the failure, and deleting earlier messages one block and then one message at a time, keeping each deletion that still fails; finally work through the few remaining messages by hand. The appendix does not implement automatic shrinking.

Property-based testing frameworks such as RapidCheck do this shrinking automatically. The three implementations may share the same business bug, so passing the differential test does not replace cases with written-down expected results. `IdMap` is also compared separately against `std::unordered_map`, checking collisions, probing that wraps past the end of the array, backward-shift deletion, growth, and both ends of the id range.

### Sanitizers

Compiling with `-fsanitize=address,undefined` and running all deterministic cases and the random differential test finds out-of-bounds array accesses, use of a dangling reference after a cancel (for example canceling first and then reading `order.cum` in a price amend) and signed integer overflow. See [[toolchain/testing|testing, sanitizers and fuzzing]].

## Follow-ups: from rules to system design

When answering an extension question, confirm the business semantics first, then say what changes, and finally name the new edge cases.

- How do you add FOK? You cannot roll back while matching. Add a read-only check in `submit` before matching: starting from the best opposite level, sum `level.total` over the levels within the limit, enter `match` only if it is enough, and cancel the whole order otherwise. This is another use of keeping a total per level: only levels are scanned, not individual orders. If self-trade prevention or hidden iceberg quantity is also present, the check has to count the quantity that can actually trade.
- How do you add self-trade prevention? Each order stores an account number. When `match` takes the resting order at the front of the queue, it first compares the two accounts; if they match, it follows the exchange's rule: cancel the aggressor's remainder, cancel the resting order and continue, cancel both, or decrement both quantities without reporting a trade. If the resting order is canceled, save its successor first, or continue from the new front of the queue; do not access a node that is no longer valid.
- What about iceberg and stop orders? An iceberg order has a displayed and a hidden quantity, and market data snapshots count only the displayed quantity. When the displayed part is filled, a new displayed batch is taken from the hidden quantity and moved to the back of the queue at that price with `unlink` and `append` (a common replenishment policy; follow what the problem specifies). Stop orders wait in a separate book sorted by trigger price and, once triggered, are converted to ordinary orders and sent into the main book; the order of processing for chained triggers has to be defined.
- Some futures markets use pro-rata allocation. How does the structure change? At one price level, the traded quantity is allocated in proportion to each resting order's size: matching walks the whole level, computes shares from `level.total`, and distributes the rounding remainder by FIFO or to the largest order. So orders at one price still need to be traversable, with a maintained total; the specific allocation and remainder rules must be confirmed first.
- How is the opening auction matched? During the collection phase orders rest without matching, and bids may be above asks, so the uncrossed-book check is suspended. At the open, a single price is found in the crossing range that maximizes `min(cumulative buy quantity, cumulative sell quantity)`; ties are broken by the unfilled imbalance and the distance from a reference price. Orders are paired at that price in one pass, and the rest move to continuous matching.
- How do you recover after a crash? Whose time defines time priority? A common approach is a sequencer at the entry that fixes the order of requests, rather than using client timestamps, and then records and replicates input according to the recovery protocol. The engine is written as a deterministic state machine: it does not read the system clock, does not depend on the iteration order of unordered containers, and does not read uninitialized memory. After a crash, loading the latest snapshot and replaying the sequenced log after it restores the same state and events. You also need to define which reports were already sent and how duplicates are removed after recovery; snapshots and replay do not by themselves solve repeated sending of events.
- Market makers do not run exchanges, so why do they also ask about matching engines? Order books are everywhere in market-making strategies: on one side, the firm receives order-by-order market data and rebuilds the exchange's order book locally (reusing levels, queues and the id index, but handling adds, deletes, trades and sequence gaps according to the protocol); on the other, backtests work out where the firm's own orders stand in the queue and when they would fill.
- Should the callback be a virtual function, a `std::function` or a template? A virtual function or `std::function` is an indirect call each time; when the target is fixed the branch predictor guesses it easily, and the cost is generally within a few nanoseconds. The extra cost of `std::function` is in construction: if what it captures does not fit in its internal buffer it allocates, so construct it only once at initialization. To remove the indirect call entirely, make the listener a template parameter so the compiler can inline it, at the price of keeping all the engine's code in headers. Every implementation on this page is written that way: `template<class Listener>`, where the listener only needs an `on_trade(const Trade&)`.
- What if, as in FIX, every amend switches to a new order id? Inside the engine the order gets a fixed number, and the index maps client ids to that number; after a successful amend, remove the old id's mapping and add one for the new id. Messages in flight also need handling: a cancel the client sent with the old id may arrive after the amend has taken effect, when the old id is no longer in the index, and it must be answered with a cancel reject that states the reason, so the client can retry with the new id.
- Where do risk checks go? Before the order enters matching, in the gateway or a separate risk module: whether the price deviates too far from a reference price, whether the quantity exceeds a limit (to stop fat-finger errors), whether position and funds are sufficient, whether the message rate exceeds a limit, and a kill switch that stops all trading for an account. The matching engine keeps a last check inside, for example that a trade price cannot be outside the daily price limits.
- How do you use multiple cores; would a lock on the engine work? No lock: each book is matched by one thread only. The matching order is itself a rule: when two threads contend for a lock, which one gets it first is accidental, so the same input could produce different trades. And a message takes only tens of nanoseconds, so passing the lock and the book's data back and forth between cores costs more than the matching itself. Multiple cores are used outside the book; see appendix F.

## How to plan practice

If you give yourself one hour of practice, the goal is a baseline you can verify, not finishing every optimization:

| Time | Goal | Check yourself |
|---|---|---|
| 0–10 min | Confirm the problem; work through one trade and one amend after a partial fill by hand | Are prices, queueing, quantity semantics and the id range clear |
| 10–20 min | Derive the data structures and the interface | Can you explain the map, the list and the hash index from the operations they must support |
| 20–45 min | Write matching, cancels and amends in the STL version | Buy and sell share one loop, quantities and the index are updated together, the cumulative fill is never lost |
| 45–60 min | Run edge-case tests and discuss one optimization | Can you check the rules with counterexamples, and name the preconditions an optimization depends on |

In the second session switch to the object pool, and in the third add the open-addressing hash table and the level arrays, rerunning the same tests at each step. If the interview already provides a problem statement, a framework and tests, follow the interviewer's requirements; do not give up working core logic in order to show the complete path.

## Grading: what a good answer looks like

| Area | Strong | Average | Weak |
|---|---|---|---|
| Requirements | Asks unprompted about the trade price, amend semantics, id scope and so on, says which part of the code each one affects, and writes them down as comments | Asks some questions but cannot say why | Starts writing classes and members at once and goes back to change them halfway |
| Data structures | Gives the baseline and its complexity, then explains low-latency alternatives component by component, with preconditions and costs, and can use data to show when they pay off | Knows terms such as object pool and open addressing but cannot state the preconditions | Incomplete structure, or a cancel that scans the whole book |
| Writing code | Tests pass stage by stage, both sides share code, talks while writing | Passes the tests, but with duplicated or disorganized code | Tests do not pass, or goes silent when stuck |
| Testing and correctness | Names invariants, differential testing and sanitizers, and how to shrink the input after a failure | Only says "write more test cases" | Does not consider edge cases |
| Depth | Answers follow-ups with the semantics, the change and its cost; brings up tail latency, determinism and single-threaded matching | Can answer some of them | Stays at the level of LeetCode |

## Appendix A: base types and the complete STL baseline

Put the earlier `types.hpp` (see "Version 1: the single-book STL implementation") in the same directory as `stl_book.hpp` below and it compiles. It includes `GTC`/`IOC`, cancels and amends by total quantity, and serves as the reference for later optimizations. By default it does not limit the number of active orders; a `capacity` can be passed so that the CLI comparison tests and the fixed-pool versions follow the same capacity rules. The excerpts in the main text and the appendix are the same implementation; do not paste them twice.

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

## Appendix B: the pool version, the four-step optimized version, and the multi-symbol layer

The three headers below are: `pool_book.hpp`, the intermediate version that only switches to the intrusive object pool; `fast_book.hpp`, with all four optimizations (object pool + open-addressing `IdMap` + sorted arrays with the best price at the end + reserved capacity); and `multi_engine.hpp`, the multi-symbol router that works with any single-book template.

<details markdown="1">
<summary>pool_book.hpp (step 1: object pool + index-based intrusive list)</summary>

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
        cancel_order(id); // frees one slot, enough to rest the remainder at the new price
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
<summary>fast_book.hpp (all four steps: object pool + IdMap + sorted arrays with the best price at the end + reserved capacity)</summary>

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

// Open-addressing, linear-probing hash table: Fibonacci hashing + backward-shift deletion (no tombstones).
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
        // The empty-slot sentinel is also a valid id; it is stored separately, outside the probed slots.
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
    std::optional<Value> last_id_; // the value for UINT64_MAX
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

    // levels run from worst to best, best price at back(); returns the first position not worse than px
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
            if (best.head == nil) opp.pop_back(); // best level emptied: pop the back, no elements move
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
    std::vector<Level> bids_; // ascending, highest bid at back()
    std::vector<Level> asks_; // descending, lowest ask at back()
    IdMap<Locator> lookup_;
};
```

</details>

<details markdown="1">
<summary>multi_engine.hpp (multi-symbol routing layer, FastBook by default)</summary>

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

## Appendix C: three-way differential and edge-case test suite

Put `tests.cpp` in the same directory as the headers above, keep assertions enabled (do not add `-DNDEBUG`), and compile and run with ASan/UBSan:

```bash
clang++ -std=c++20 -Wall -Wextra -Wconversion -pedantic \
  -O1 -fsanitize=address,undefined tests.cpp -o tests
./tests
```

Expected output:

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
    // 1. Multiple levels, FIFO within a level, trade at the resting order's price (price improvement)
    {
        Recorder r; Book<Recorder> b(r);
        assert(b.add_order(1, Sell, GTC, 100, 3) == Ok);
        b.add_order(2, Sell, GTC, 100, 4);
        b.add_order(3, Sell, GTC, 101, 10);
        b.add_order(4, Buy, GTC, 102, 8);
        assert((r.trades == std::vector<Trade>{{1,4,100,3},{2,4,100,4},{3,4,101,1}}));
        assert(b.best_ask() == 101 && b.ask_volume_at(101) == 9);
    }
    // 2. Cancel from the middle, the front, and the last order; empty levels must be removed
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
    // 3. Same-price decrease keeps queue position; same-price increase loses time priority and goes to the back
    {
        Recorder r; Book<Recorder> b(r);
        b.add_order(1, Sell, GTC, 100, 3);
        b.add_order(2, Sell, GTC, 100, 4);
        b.modify_order(1, 100, 2);
        b.add_order(3, Buy, IOC, 100, 1);
        assert(r.trades.back().resting_id == 1);
        b.modify_order(1, 100, 6); // cum=1, new remaining quantity is 5, moves behind #2
        assert(b.ask_volume_at(100) == 9);
        b.add_order(4, Buy, IOC, 100, 4);
        assert(r.trades.back().resting_id == 2);
    }
    // 4. Fill in flight: a late amend with new total <= filled quantity cancels the remainder, preventing overfill
    {
        Recorder r; Book<Recorder> b(r);
        b.add_order(1, Buy, GTC, 100, 100);
        b.add_order(2, Sell, IOC, 100, 80);
        assert(b.modify_order(1, 100, 60) == Ok);
        assert(!b.best_bid());
    }
    // 5. An aggressor that fills partly and then rests must keep its cumulative fill cum
    {
        Recorder r; Book<Recorder> b(r);
        b.add_order(1, Sell, GTC, 100, 3);
        b.add_order(2, Buy, GTC, 100, 10);
        b.modify_order(2, 100, 5);
        assert(b.bid_volume_at(100) == 2);
    }
    // 6. A price amend that trades immediately, then another amend: cum still covers the whole order
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
    // 7. IOC remainder is discarded; id=0 is valid; an id may be reused after it leaves the book
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
    // 8. Negative and zero prices work; a level total above 32 bits does not overflow
    {
        Recorder r; Book<Recorder> b(r);
        b.add_order(1, Sell, GTC, -10, UINT32_MAX);
        b.add_order(2, Sell, GTC, -10, UINT32_MAX);
        assert(b.ask_volume_at(-10) == Volume(UINT32_MAX) * 2);
        b.add_order(3, Buy, IOC, 0, 1);
        assert(r.trades.back().price == -10);
        assert(b.modify_order(2, 0, 1) == Ok);
    }
    // 9. Both ends of the id range are valid; the hash table's empty-slot marker must not change behavior.
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
            OrderId id = rng() % 40; // includes id = 0
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
    // 16 slots initially; 7 keys deliberately hash to the last bucket so probing wraps past the end.
    std::vector<OrderId> colliding;
    for (OrderId id = 0; colliding.size() < 7; ++id)
        if ((((id + 1) * 0x9E3779B97F4A7C15ull) >> 60) == 15)
            colliding.push_back(id);
    for (OrderId id : colliding) assert(map.insert(id, 7));
    map.erase(colliding[0]);
    map.erase(colliding[3]);
    for (OrderId id : colliding)
        assert(map.contains(id) == (id != colliding[0] && id != colliding[3]));
    map.erase(UINT64_MAX); // erasing an unknown id is a no-op

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
    // The CLI's STL reference implementation uses the same active-order capacity.
    Recorder r; StlBook limited(r, 1);
    assert(limited.add_order(1, Buy, GTC, 99, 1) == Ok);
    assert(limited.add_order(2, Buy, GTC, 99, 1) == Result::CapacityExceeded);
    std::cout << "examples (StlBook, PoolBook, FastBook), capacity, multi-symbol: passed\n"
              << "3-way differential: 100 seeds x 1000 messages passed\n"
              << "hash collisions, wraparound, growth, full-range ids: passed\n";
}
```

</details>

## Appendix D: the complete text protocol, 22 staged test cases, and a command-line solution

On-site coding problems often give a complete text protocol over standard input and output plus a set of black-box cases, and ask the candidate to make the cases pass in stages. Below are a complete problem statement of our own, 22 staged test cases, the grading script `run_tests.py`, and the command-line entry point `cli.cpp`, which reuses `fast_book.hpp` / `stl_book.hpp` from above directly (it shows the global routing table `route` for cancels and amends without a `symbol`, and the session-wide history table `used` for duplicate ids).

### Problem statement

Read space-separated messages from standard input line by line, process them in order, and write trade and reject events to standard output as they happen; at end of input, print snapshots of every order book that still has resting orders, in lexicographic order of symbol.

| Message | Format | Meaning |
|---|---|---|
| New order | `INSERT <id> <symbol> <BUY\|SELL> <price> <qty>` | Submit a GTC limit order |
| Amend | `AMEND <id> <price> <qty>` | Change a resting order's price and new total quantity (including what has filled) |
| Cancel | `CANCEL <id>` | Cancel an order currently on the book |

- Field ranges: `id` is a 64-bit unsigned positive integer (including `UINT64_MAX`); `symbol` is a non-empty string of uppercase letters; a valid `price` is a positive decimal number with 1–12 digits in the integer part and at most 2 decimal places (`100`, `100.5` and `100.25` are valid; `100.123`, `1e2`, `.5` and `0` are not); a valid `qty` is an integer from `1` to `10^9`. Empty lines are ignored.
- Reject checks, in order (the first match prints `REJECT <id> <reason>` and the message is ignored):
  1. `price` or `qty` is invalid: `INVALID` (a rejected `INSERT` does not use up its `id`).
  2. The `id` of an `INSERT` was used by any successfully accepted `INSERT` in this run (even if it has since been filled completely or canceled): `DUPLICATE_ID`.
  3. The `id` of an `AMEND` or `CANCEL` is not currently on any order book: `UNKNOWN_ID`.
  4. A valid new order needs to rest but the symbol's active-order capacity is full: `CAPACITY_EXCEEDED`. No trades happen, and the id is not recorded as used; the same id can be retried once capacity frees up.
- Matching and amend rules: price then time priority, trades at the resting price (printed with two decimal places). The new remaining quantity of an `AMEND` is `qty - cum`; if it is not greater than 0, the order ends and leaves the book (no event is printed). At the same price, if the new remaining quantity is not greater than the old one, it is reduced in place and keeps its position; an increase or a price change is equivalent to canceling the original order and submitting again with the same ID, carrying the original `cum`.
- Output format:

```text
TRADE <symbol> <price> <qty> <aggressor id> <resting id>
REJECT <id> <INVALID|DUPLICATE_ID|UNKNOWN_ID|CAPACITY_EXCEEDED>
BOOK <symbol>
BID <price> <total qty> <order count>     # from highest bid to lowest bid
ASK <price> <total qty> <order count>     # from lowest ask to highest ask
```

By default the CLI allows at most 1024 resting orders per symbol, and both implementations use the same limit. `--capacity N` changes it; the parameter limits only the number of simultaneously active orders, and the duplicate-id history table still grows. The problem guarantees that everything else is well formed; the parsing layer is responsible for validating price and quantity, and is not meant to be a general protocol parser.

### Staged order of work and the 22 test cases

| Stage | Goal | Test numbers |
|---|---|---|
| 1 | `INSERT`, crossing and matching, isolation between symbols, snapshots in lexicographic order | 01–06 |
| 2 | `CANCEL`, removal from the middle of a queue, and the order of the three rejects | 07–09, 17 |
| 3 | `AMEND` with total-quantity semantics, decreases keeping position, increases going to the back, canceling to prevent overfill when a fill is in flight, and an aggressor keeping its `cum` | 10–16, 18–22 |
| 4 | Capacity rejects, retries, global routing, and a regression for the largest id | `cli_regressions.py` |

<details markdown="1">
<summary>tests.txt (22 staged cases)</summary>

```text title="tests.txt"
=== 01 Two non-crossing orders both rest on the book
INSERT 1 AAPL BUY 100.00 10
INSERT 2 AAPL SELL 101.00 5
---
BOOK AAPL
BID 100.00 10 1
ASK 101.00 5 1
=== 02 Full fill at the resting price; an empty book prints nothing
INSERT 1 AAPL SELL 100.50 10
INSERT 2 AAPL BUY 101 10
---
TRADE AAPL 100.50 10 2 1
=== 03 Partial fill, the remainder rests
INSERT 1 AAPL SELL 100 4
INSERT 2 AAPL BUY 100 10
---
TRADE AAPL 100.00 4 2 1
BOOK AAPL
BID 100.00 6 1
=== 04 Price-time priority; one buy sweeps two levels
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
=== 05 Aggressive sell hits the highest bid first; the non-crossing remainder rests
INSERT 1 AAPL BUY 99 5
INSERT 2 AAPL BUY 100 5
INSERT 3 AAPL SELL 99.5 7
---
TRADE AAPL 100.00 5 3 2
BOOK AAPL
BID 99.00 5 1
ASK 99.50 2 1
=== 06 Different symbols do not match; snapshot sorted by symbol
INSERT 1 MSFT BUY 50 10
INSERT 2 AAPL SELL 50 10
INSERT 3 AAPL BUY 50 3
---
TRADE AAPL 50.00 3 3 2
BOOK AAPL
ASK 50.00 7 1
BOOK MSFT
BID 50.00 10 1
=== 07 Cancel; a repeated cancel and an unknown id are rejected
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
=== 08 A filled order cannot be canceled; a used id cannot be reused
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
=== 09 Invalid fields; a rejected INSERT does not use up its id
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
=== 10 Same-price decrease keeps time priority
INSERT 1 AAPL BUY 100 10
INSERT 2 AAPL BUY 100 10
AMEND 1 100 4
INSERT 3 AAPL SELL 100 6
---
TRADE AAPL 100.00 4 3 1
TRADE AAPL 100.00 2 3 2
BOOK AAPL
BID 100.00 8 1
=== 11 Increase loses time priority and goes to the back
INSERT 1 AAPL BUY 100 10
INSERT 2 AAPL BUY 100 10
AMEND 1 100 11
INSERT 3 AAPL SELL 100 12
---
TRADE AAPL 100.00 10 3 2
TRADE AAPL 100.00 2 3 1
BOOK AAPL
BID 100.00 9 1
=== 12 Price amend crosses; the amended order trades immediately as aggressor
INSERT 1 AAPL SELL 101 5
INSERT 2 AAPL BUY 100 8
AMEND 2 101 8
---
TRADE AAPL 101.00 5 2 1
BOOK AAPL
BID 101.00 3 1
=== 13 AMEND quantity is the new total: 4 filled, amend to 6 leaves 2, decrease keeps time priority
INSERT 1 AAPL SELL 100 10
INSERT 2 AAPL BUY 100 4
INSERT 3 AAPL SELL 100 5
AMEND 1 100 6
INSERT 4 AAPL BUY 100 7
---
TRADE AAPL 100.00 4 2 1
TRADE AAPL 100.00 2 4 1
TRADE AAPL 100.00 5 4 3
=== 14 Amend an unknown or already filled order
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
=== 15 Price amend sweeps several levels; the remainder rests at the new price
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
=== 16 Fully filled after an amend; it cannot be canceled afterwards
INSERT 1 AAPL BUY 100 5
INSERT 2 AAPL SELL 101 5
AMEND 2 100 5
CANCEL 2
---
TRADE AAPL 100.00 5 2 1
REJECT 2 UNKNOWN_ID
=== 17 Cancel from the middle of a queue; an emptied level is removed from the book
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
=== 18 New total equals filled quantity: the order ends, a later cancel gets unknown id
INSERT 1 AAPL SELL 100 10
INSERT 2 AAPL BUY 100 4
AMEND 1 100 4
CANCEL 1
---
TRADE AAPL 100.00 4 2 1
REJECT 1 UNKNOWN_ID
=== 19 New total below filled quantity: the order also ends; existing trades stand
INSERT 1 AAPL SELL 100 10
INSERT 2 AAPL BUY 100 4
AMEND 1 100 3
INSERT 3 AAPL BUY 100 5
---
TRADE AAPL 100.00 4 2 1
BOOK AAPL
BID 100.00 5 1
=== 20 New total above the original total: the increase loses time priority
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
=== 21 A price amend keeps the filled quantity: a later amend still computes the remainder from it
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
=== 22 An aggressor that rests after trading keeps its filled quantity
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
<summary>run_tests.py (grading script)</summary>

```python title="run_tests.py"
# run_tests.py <executable> [args...]: runs each case in tests.txt and compares the output
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
<summary>cli.cpp (explicit handling of acceptance results, global routing and duplicate-id history)</summary>

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
    IdMap<std::uint8_t> used(1 << 16);   // every id accepted in this session
    IdMap<std::uint32_t> route(1 << 16); // active order id -> index of its symbol

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
            used.insert(id, 1); // only an accepted order uses up its id; a capacity reject does not
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
python3 run_tests.py ./cli          # optimized implementation: 22/22 passed
python3 run_tests.py ./cli --stl    # STL reference implementation: 22/22 passed
python3 cli_regressions.py ./cli    # capacity, retry, routing and the largest id
./cli --capacity 8192 < input.txt  # set per-symbol capacity to the problem's scale
```

---

### Additional regression: a capacity reject must not drop an order silently

Generate 1025 non-crossing orders separately and confirm that with the default capacity order 1025 gets a reject; then free one slot and retry with the same id. This scenario checks not only the order book but also whether the CLI handles the return value, whether it wrongly records the id as used, and whether the route is removed in step.

<details markdown="1">
<summary>cli_regressions.py</summary>

```python title="cli_regressions.py"
"""python3 cli_regressions.py ./cli: checks both the FastBook and the --stl paths."""
import subprocess
import sys

exe = sys.argv[1]

def run(text, capacity, stl):
    args = [exe, "--capacity", str(capacity)] + (["--stl"] if stl else [])
    result = subprocess.run(args, input=text, text=True, capture_output=True, check=True)
    return result.stdout

for stl in (False, True):
    # Order 1025 must be rejected explicitly; the reject does not use up the id, which can be retried after a slot frees.
    text = "".join(f"INSERT {i} AAPL BUY 100 1\n" for i in range(1, 1026))
    text += "CANCEL 1025\nCANCEL 1\nINSERT 1025 AAPL BUY 100 2\n"
    expected = ("REJECT 1025 CAPACITY_EXCEEDED\nREJECT 1025 UNKNOWN_ID\n"
                "BOOK AAPL\nBID 100.00 1025 1024\n")
    assert run(text, 1024, stl) == expected

    # A full pool can still trade; routes of filled orders are removed, and a price amend keeps the cumulative fill.
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

    # UINT64_MAX is not excluded by the hash table sentinel; after a full fill it is still a duplicate.
    last = 2**64 - 1
    text = (f"INSERT {last} AAPL SELL 100 1\nINSERT 1 AAPL BUY 100 1\n"
            f"CANCEL {last}\nINSERT {last} MSFT BUY 90 1\n")
    expected = (f"TRADE AAPL 100.00 1 1 {last}\nREJECT {last} UNKNOWN_ID\n"
                f"REJECT {last} DUPLICATE_ID\n")
    assert run(text, 1, stl) == expected

    # Capacity is counted per symbol; the global route still points to the right book.
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

## Appendix E: timing code

`bench.cpp` generates the message stream described in "Measurements" in the main text, first confirms that `StlBook` and `FastBook` produce the same trades and final snapshots, and then measures throughput and per-message latency separately. The outer routing and duplicate-id rules are the same as in `cli.cpp` from appendix D, except that symbols are now numbered 0 to 7 instead of looked up by string.

<details markdown="1">
<summary>bench.cpp</summary>

```cpp title="bench.cpp"
// bench.cpp: generates a random message stream, checks that both implementations agree, then times each
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

// How a new order is checked for duplicates: remember every id used in the session; require increasing ids; no check
enum class IdPolicy { History, Increasing, None };

struct Msg {
    enum Kind : std::uint8_t { Insert, Amend, Cancel } kind;
    Side side;
    std::uint8_t sym;
    OrderId id;
    Price px;
    Quantity qty;
};

// std::unordered_map wrapper with the IdMap interface, for the STL version's outer layer
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

// Outer layer: symbols are numbered 0..7; global route + optional session-wide duplicate check, same rules as cli.cpp in appendix D.
// the route holds only resting orders, reserved at total pool capacity; the duplicate set is reserved at the expected number of accepted ids
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

// mixes trades and rejects into one hash, to compare the two implementations' event sequences
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

// While generating, the STL version tracks which orders are resting: cancels and amends target only resting orders,
// 70% of them hit the 32 most recently placed orders (quotes being refreshed). Resting orders stay near target.
struct LiveTracker {
    std::vector<std::int64_t> rem, traded;
    std::vector<OrderId> filled;  // resting orders filled completely by this message
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
            Price off = pick(100) < 85 ? Price(1 + pick(20)) : -Price(pick(4));  // 15% cross the mid price
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
                t.rem[id] = std::int64_t(m.qty) - t.traded[id];  // an amend's quantity is the new total
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
        std::size_t cap = target / kSymbols * 2;  // node pool per symbol, with 2x headroom
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

First run it on a small input under sanitizers, then time it with assertions off:

```bash
clang++ -std=c++20 -O1 -fsanitize=address,undefined -DNBIG=100000 bench.cpp -o bench_asan && ./bench_asan
clang++ -std=c++20 -O2 -DNDEBUG bench.cpp -o bench && ./bench
```

The whole program needs more than 1 GB of memory, mainly for the 10 million messages, the tracking arrays used during generation, and the reserved duplicate-id table.

## Appendix F: one execution thread per book, and parallelism outside the book

**Interviewer:** "Now we want to use multiple cores. Would you just put a lock on the order book?"

First separate two things: running several books in parallel, and several threads modifying the same book at once. This page chooses to have each book executed exclusively by one thread, while other threads handle receiving and sending, parsing, risk checks, logging and output. The book then needs no locks, and the input order is easy to keep deterministic.

This is an architectural choice that can be explained, not the only implementation every matching system must use. Even with a lock on the order book, the business order still has to be defined; a lock protects the data structure but does not replace the sequencing rule behind time priority.

Martin Fowler's 2011 article [The LMAX Architecture](https://martinfowler.com/articles/lmax.html) describes a concrete example: the business core is a single-threaded, in-memory processor based on event replay, connected to the surrounding stages through the Disruptor. The article reports a benchmark of about 6 million orders per second. The example supports the idea that a single-threaded core can work with parallel surrounding stages; it cannot be used to infer a fixed latency for every system.

### The overall pipeline: move uncontrolled work out of the book

<figure class="diagram">
<svg viewBox="0 0 760 330" role="img" aria-label="Gateway threads, a sequencer thread, matching threads sharded by symbol and output threads, connected by queues" style="width:100%;height:auto;font-family:var(--font-sans);font-size:13px">
<defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="var(--ink)" opacity=".55"/></marker></defs>
<g fill="var(--ink)" opacity=".6" text-anchor="middle" font-size="12"><text x="55" y="22">Clients</text><text x="205" y="22">Gateway threads</text><text x="375" y="22">Sequencer</text><text x="540" y="22">Matching threads</text><text x="695" y="22">Output</text></g>
<g fill="var(--surface)" stroke="var(--line)" stroke-width="1.2">
<rect x="15" y="45" width="80" height="30" rx="6"/><rect x="15" y="90" width="80" height="30" rx="6"/><rect x="15" y="160" width="80" height="30" rx="6"/><rect x="15" y="205" width="80" height="30" rx="6"/>
<rect x="140" y="55" width="130" height="56" rx="8"/><rect x="140" y="170" width="130" height="56" rx="8"/>
<rect x="320" y="70" width="110" height="140" rx="8" stroke="var(--accent)"/>
<rect x="320" y="255" width="110" height="44" rx="8"/>
<rect x="470" y="45" width="140" height="48" rx="8" stroke="var(--accent)"/><rect x="470" y="116" width="140" height="48" rx="8" stroke="var(--accent)"/><rect x="470" y="187" width="140" height="48" rx="8" stroke="var(--accent)"/>
<rect x="645" y="45" width="100" height="190" rx="8"/>
</g>
<g fill="var(--ink)" text-anchor="middle">
<text x="55" y="65">Client A</text><text x="55" y="110">Client B</text><text x="55" y="180">Client C</text><text x="55" y="225">Client D</text>
<text x="205" y="78">Gateway 1</text><text x="205" y="98" font-size="11.5" opacity=".7">parse · session · risk</text>
<text x="205" y="193">Gateway 2</text><text x="205" y="213" font-size="11.5" opacity=".7">parse · session · risk</text>
<text x="375" y="100">Sequencer</text><text x="375" y="128" font-size="11.5" opacity=".7">total order</text><text x="375" y="148" font-size="11.5" opacity=".7">sequence numbers</text><text x="375" y="168" font-size="11.5" opacity=".7">route by symbol</text>
<text x="375" y="275">Log · standby</text><text x="375" y="291" font-size="11" opacity=".7">persist, replicate</text>
<text x="540" y="66">Matcher 0</text><text x="540" y="83" font-size="11.5" opacity=".7">books S0 S3 S6</text>
<text x="540" y="137">Matcher 1</text><text x="540" y="154" font-size="11.5" opacity=".7">books S1 S4 S7</text>
<text x="540" y="208">Matcher 2</text><text x="540" y="225" font-size="11.5" opacity=".7">books S2 S5</text>
<text x="695" y="110">Publish</text><text x="695" y="135" font-size="11.5" opacity=".7">exec reports</text><text x="695" y="155" font-size="11.5" opacity=".7">market data</text><text x="695" y="175" font-size="11.5" opacity=".7">output log</text>
</g>
<g stroke="var(--ink)" stroke-opacity=".45" stroke-width="1.2" fill="none" marker-end="url(#ah)">
<path d="M95 60L138 76"/><path d="M95 105L138 92"/><path d="M95 175L138 191"/><path d="M95 220L138 207"/>
<path d="M270 83L318 115"/><path d="M270 198L318 165"/>
<path d="M375 210L375 253"/>
<path d="M430 110L468 72"/><path d="M430 140L468 140"/><path d="M430 170L468 208"/>
<path d="M610 69L643 100"/><path d="M610 140L643 140"/><path d="M610 211L643 180"/>
</g>
<text x="380" y="322" text-anchor="middle" fill="var(--ink)" opacity=".6" font-size="12">Every arrow between threads is a single-producer single-consumer queue; each book is touched by one matching thread only</text>
</svg>
</figure>

The figure shows a simplified design; each thread may own several queues, and the actual timing of logging, replication and reports needs to be defined by a failure-recovery protocol.

- **Gateway threads** receive packets, parse, handle sessions and pre-trade risk checks, and convert symbol names into internal numbers.
- **The sequencer thread** decides the execution order of requests and dispatches them to the corresponding shard. Logging, replication and matching can then cooperate around the same input sequence, but when matching may proceed and when a client may be acknowledged require explicit persistence and replication watermarks.
- **Matching threads** each own several books exclusively, process input and generate events. If the goal is strictly zero allocations and zero system calls, every resource has to be reserved and callbacks restricted; the code on this page does not automatically guarantee that the whole pipeline meets these goals.
- **Output threads** encode trade, order-status and market-data events and handle network and log output, keeping slow I/O apart from updates to the core state.

LMAX's shared ring buffer and multi-consumer dependencies are richer than the paired SPSC queues in the figure; they are not the same queue topology.

### Handing off between threads

If a queue really has exactly one producer and one consumer, an **SPSC ring buffer** can be used: slots in a fixed array are reused in a cycle, the producer advances the tail cursor, the consumer advances the head cursor, and data is published and reclaimed through appropriate acquire/release operations. The implementation and memory orders are covered in [[topics/concurrency-in-practice|concurrency in practice]].

Putting it into practice raises further questions:

- Do the head and tail cursors share a cache line? Laying them out separately reduces false sharing; the cache line size and alignment have to be confirmed for the platform, see [[perf/false-sharing|false sharing]].
- What happens when the queue is full? Blocking, rejecting, backpressure or degradation needs an explicit policy; events not yet consumed cannot be overwritten.
- Who owns a message? Fixed-size value messages are easy to manage; passing pointers requires separately defining cross-thread lifetimes and who reclaims them.
- How do several gateways merge? Each can use its own SPSC queue, read by the sequencer under a fixed policy, or an MPSC queue can be chosen. Contention, polling cost, fairness and sequencing policy have to be compared for the two; whether CAS is used does not by itself decide which is better.

### Spinning or sleeping

When the matching thread's input queue is empty, there are two ways to wait:

- Spinning: poll the queue continuously. A new message is seen within tens of nanoseconds, at the cost of keeping the core fully busy whether or not messages arrive. Latency-sensitive systems usually do this, and pin the matching thread to a fixed core so the scheduler neither puts other threads on it nor migrates it away. On Linux, `sched_setaffinity` pins the thread, and a boot parameter such as `isolcpus` takes those cores out of normal scheduling; macOS has no interface for pinning, only a QoS hint asking to run on the performance cores (see [[perf/measuring|measuring performance]]).
- Sleeping: sleep on a condition variable or `std::atomic::wait`, and have the producer wake the thread after enqueuing a message. This saves CPU, but getting from the wake-up to running again takes several microseconds, two orders of magnitude slower than matching one message.

C++20's `std::atomic::wait` does not necessarily sleep at once. The libc++ on the test machine (`<__atomic/atomic_sync.h>`) checks 64 times, then keeps spinning until the value has not changed for 4 µs, and only then calls the operating system's wait. When messages arrive less than 4 µs apart it behaves almost like spinning; with longer gaps every message pays the cost of a wake-up. These constants are implementation details of this library version, not interface guarantees, and need rechecking on another platform.

### Why not put a lock on the engine

When asked "how would you make it multithreaded?", a common wrong answer is to put a lock around new order, cancel and amend. The options can be laid out in order:

1. One global lock. Simple and correct, but messages still execute one at a time, with the added cost of locking and of moving the book's data between cores; the more threads, the slower each message.
2. One lock per symbol. Different symbols can now run in parallel. But when cancels and amends carry no symbol, the symbol has to be looked up by id first, and that id table becomes a structure shared by all threads that needs its own protection; the routing table and the duplicate-id history table in appendix D are also shared across symbols.
3. Shard by symbol and pass messages between threads through queues. Each book is accessed by only one thread, no locks are needed, and determinism is preserved. The pipeline above takes this approach.

### What remains after sharding

After sharding by symbol, each thread can own a group of books exclusively, but five kinds of boundary remain:

1. **Cancel routing.** If the protocol carries the symbol, the shard can be looked up directly; with only a global id, a route has to be maintained and kept in step with events where orders leave the book. Real protocols usually require cancels to carry the symbol; in FIX, for example, the symbol is a required field of a cancel request, and the problem disappears.
2. **Cross-symbol combination orders.** If one operation requires matching in several books at once, you cannot send independent requests to each shard and assume they complete atomically. Putting related symbols in the same execution partition is one simplification; otherwise cross-partition coordination is needed. So shards are usually formed from groups of related symbols, for example the monthly futures on one underlying together with the spread contracts between them, rather than by hashing symbol names.
3. **Load skew.** A popular symbol may saturate one thread, so shards should be assigned by actual traffic, with a plan for when to migrate and how to hand over state.
4. **Report ordering.** Execution order can be kept within one book, but reports from different shards may interleave. The protocol has to say which ordering it guarantees and whether output needs reordering.
5. **Cross-symbol risk.** Account funds and positions span many books. One approach reserves limits before an order enters matching and settles them from trade or cancel reports; how limits are synchronized, reclaimed and recovered still needs its own design.

A correct state machine for a single book is the foundation for discussing these questions. In an interview, explaining the single-book rules, the handoff between threads and failure recovery separately is more convincing than calling an example a production system.

## Appendix G: printing price levels from high to low

Some problem statements have a print command that outputs the current book: sells first, then buys, with both sides from high price to low, one line per price, showing only the price and total quantity.

```text
SELL:
1010 10
1000 20
BUY:
999 10
800 20
```

This does not go through `Listener`. `Listener` reports events that happen during matching, and the engine calls it; printing is a query the caller starts, and the engine has no event to report. So the book offers read-only traversal, and the output stays outside the book, which does not need to know the output format.

The existing `for_each_level` goes buys first and starts each side at the best price, which is not the order needed here, so add two more traversal functions to the book's `public` section:

```cpp
// StlBook, PoolBook: the bid map already runs high to low; walk the asks in reverse
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
// FastBook: the ask array already runs high to low; walk the bids in reverse
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

The print function works with all three implementations:

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

The header is printed even when a side is empty. Traversal does not change the book, so it can be printed repeatedly. This code was tested with all three implementations using deterministic cases (empty book, merging at one price, several levels, the remainder after a trade, printing twice in a row), and passes under ASan/UBSan.

## Appendix H: a complete program under a different set of conventions

This is a complete single-file program using conventions different from the main text, for comparing how the same structure adapts to another problem statement:

- One book, with no symbols; order ids are arbitrary strings without spaces; the commands are `BUY`, `SELL`, `CANCEL`, `MODIFY` and `PRINT`.
- Times in force are GFD and IOC. The input has no dates or closing command, so a GFD order stays on the book until it trades or is cancelled.
- Every modify loses its queue position and may change side, and its quantity is the new remaining quantity, so `MODIFY` always cancels and resubmits, and may trade immediately.
- A trade reports each side's own limit price, with the earlier order first.
- Invalid input is silently ignored; the node pool can grow, and there is no capacity error.

The program has four parts: `OrderBook` handles matching, `Writer` the output format, `dispatch` the parsing and `LineReader` the reading, connected only by small interfaces.

<details markdown="1">
<summary>engine.cpp</summary>

```cpp title="engine.cpp"
// engine.cpp: a matching program for one order book. Reads commands from stdin, writes trades and snapshots to stdout.
// Assumptions: a MODIFY quantity is the new remaining quantity; a modified order counts as arriving later; a level's total fits in 64 bits.
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

// The earlier order comes first. The ids are valid only during the callback; copy them to keep them
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

// Handles only matching and state: reads no input, knows no output format, reports trades through Listener.
// The callback must not modify the book.
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

    // Ignored if the id is active. The caller guarantees price and quantity are positive
    void add(std::string_view id, Side side, OrderType type, Price price, Quantity quantity) {
        if (lookup_.find(id) != lookup_.end()) return;
        submit(id, side, type, price, quantity);
    }

    void cancel(std::string_view id) {
        auto it = lookup_.find(id);
        if (it != lookup_.end()) remove(it);
    }

    // Every modify loses its queue position and may change side, so always cancel and resubmit.
    // id points into the caller's buffer, not at the index key about to be erased.
    void modify(std::string_view id, Side side, Price price, Quantity quantity) {
        auto it = lookup_.find(id);
        if (it == lookup_.end()) return;
        remove(it);
        submit(id, side, OrderType::GFD, price, quantity);
    }

    template<class F>
    void for_each_ask_descending(F&& f) const {  // the ask array already runs high to low
        for (const Level& level : asks_) f(level.price, level.total);
    }
    template<class F>
    void for_each_bid_descending(F&& f) const {  // the bid array runs low to high; walk it in reverse
        for (const Level& level : std::views::reverse(bids_)) f(level.price, level.total);
    }

private:
    using Index = std::uint32_t;
    static constexpr Index nil = UINT32_MAX;

    struct Node {
        const std::string* id;  // points at the key in the index; a rehash does not move elements
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
    // Keys are strings in a node-based container, so their addresses are stable; lookup builds no temporary string
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
    // Levels run from worst to best with the best at back(), so emptying the best level is one pop_back.
    // This assumes activity near the top of book; adding or removing a level far from it moves O(P) elements.
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
            if (better<S>(level.price, price)) break;  // the best opposite price is already worse than the limit
            while (leaves != 0 && level.head != nil) {
                Index index = level.head;
                Node& resting = nodes_[index];
                Quantity traded = std::min(leaves, resting.leaves);
                leaves -= traded;
                resting.leaves -= traded;
                level.total -= traded;
                // Report before erasing from the index: resting.id points at the key there
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

    // The node pool can grow: positions are indices, which survive reallocation
    Index allocate() {
        if (!free_.empty()) {
            Index index = free_.back();
            free_.pop_back();
            return index;
        }
        nodes_.emplace_back();
        return static_cast<Index>(nodes_.size() - 1);
    }

    // append adds the quantity to the level total; unlink only changes links
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
    std::vector<Level> bids_;  // ascending, highest bid at back()
    std::vector<Level> asks_;  // descending, lowest ask at back()
    Lookup lookup_;
};

// Handles only the output format: buffers and writes in blocks, not one system call per line
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

// Parsing only: turns a line of text into a call on the book, silently ignoring anything invalid
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

// Splits on single spaces; consecutive spaces give empty columns, which is how an empty id is detected.
// Returns N + 1 for more than N columns, which the caller ignores as a wrong column count.
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

// Handles only reading: reads large blocks and splits them into lines. The string_view stays valid until the next call.
// Not std::getline: some standard library implementations take a lock and call the C library per character when reading std::cin.
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
                line = {buffer_.data() + start_, end_ - start_};  // the last line has no newline
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
        if (end_ == buffer_.size()) buffer_.resize(buffer_.size() * 2);  // a line longer than the buffer
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

Under ASan/UBSan this program passes 20 deterministic cases and a randomized comparison against an independent linear-scan implementation in Python (300 seeds, 300 thousand lines in total, mixed with invalid input). The Python version shares no structure with it, but both are written to the assumptions above, so the comparison cannot catch a misreading of the conventions themselves.

How input and output are written has a large effect on total time. Below is the time for one input of 3 million lines (producing about 1.45 million lines of output), written to a file, taking the fastest of 5 runs, on the machine and compiler of appendix E. The first five rows read input with `LineReader`, and all output is identical:

| Approach | Time |
|---|---:|
| Own buffer with `std::to_chars` (the program above) | 1.4 s |
| Own buffer with `std::format_to` | 1.8 s |
| `std::cout << std::format(...)`, sync off | 2.0 s |
| `std::cout << ...`, sync off | 2.8 s |
| `std::cout << ... << std::endl` | 7.6 s |
| The program above, reading with `std::getline` | 4.8 s |

`std::format` solves turning values into text; buffering solves when that text goes to the operating system. They are separate problems. `std::endl` flushes every line, and is slow because of the system calls, which `std::format` cannot fix. Conversely, `std::format_to` into your own buffer is shorter and only slightly slower, and is a reasonable choice if the judging environment supports it (GCC 13 onward). The `fmt` library is fast too, but it is a third-party dependency the judging environment may not have. These numbers reflect only this machine and this standard library; the cost of `std::getline` in particular depends on the implementation.
