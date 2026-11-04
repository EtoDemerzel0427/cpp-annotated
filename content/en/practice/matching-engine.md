---
title: Matching engine
summary: A problem common in trading-firm onsite coding interviews: implement a matching engine with multiple symbols, limit orders, cancels and amends. This page gives a complete problem statement with 17 test cases, a reference implementation and an optimized one, a differential test and measurements comparing the two, and thirty questions that come up in the design discussion and verbal follow-ups, with what a good answer covers.
status: draft
tags: matching engine, order book, interview, hash table, latency, practice
updated: 2026-11-03
---

!!! tldr
    - A matching engine pairs buy and sell orders by price priority, then time priority, and trades at the resting order's price; whatever is left unfilled rests on the order book. The hard part of the problem is not the matching loop but the edge rules for cancels, amends and rejects, and keeping every operation from walking the whole book.
    - The standard structure is a price-sorted table of levels per side, a FIFO queue per level, and a hash table from order id to the order's position, which makes a cancel O(1).
    - On our test machine, replacing `std::map` plus `std::list` with a sorted `vector`, an object pool and an open-addressing hash table took the cost per message from 94 ns to 71 ns with a shallow book and from 178 ns to 94 ns with a deep one. The problem requires rejecting any id ever used, and the table that remembers all of them costs another 20-odd nanoseconds on its own.
    - The difference in maximum latency is far larger than in the average: without reserved capacity, one hash-table rehash makes a single message take 70 to 100 ms.
    - These interviews usually spend an hour discussing the design and an hour writing code against tests. In the design phase, pin down the semantics first; while coding, be able to say why each data structure was chosen and what would change if a requirement changed.

## Interview format

In published interview reports, this problem usually shows up in the final round at market makers and trading firms, in roughly the same form: about two hours, the first half discussing requirements and design with the interviewer, the second half writing code in a provided project to make as many of the existing tests pass as possible. The language is usually C++ or Java. Some candidates passed every test and still did not get an offer, so grading is not just the tests: code structure, design trade-offs and how you communicate in the discussion all count.

Firms do not publish their exact problem statements. The problem below is our own, written from the requirements these problems usually have. It is more complete than a typical statement and fixes the semantics you would otherwise have to ask about on the spot; every rule has a matching discussion in the follow-up section.

## The problem

### Background

A **limit order** is an order with a price bound: a limit buy is willing to buy at no more than its price, a limit sell is willing to sell at no less than its price. All limit orders not yet filled form the **order book**, which has a bid side and an ask side. The highest bid and the lowest ask are together called the **top of book**, or the best prices.

When a new order arrives and crosses the best price on the other side (its buy price is at least the lowest ask, or its sell price is at most the highest bid), it trades immediately. The new order is the **aggressor**; the orders it trades against, which were already on the book, are **resting orders**. Any quantity left unfilled stays on the book as a new resting order.

Implement such a matching engine: read messages line by line from standard input, process them in order, and write trade and reject events to standard output; when the input ends, write what is left of each symbol's book.

### Input

One message per line, fields separated by spaces:

| Message | Format | Meaning |
|---|---|---|
| Insert | `INSERT <id> <symbol> <BUY\|SELL> <price> <qty>` | submit a limit order |
| Amend | `AMEND <id> <price> <qty>` | change a resting order's price and remaining quantity |
| Cancel | `CANCEL <id>` | cancel a resting order |

- `id` is a positive integer that fits in a 64-bit unsigned integer. `symbol` is a non-empty string of uppercase letters; `BUY` and `SELL` are always spelled correctly.
- The `price` and `qty` fields may be arbitrary tokens. A valid `price` is a positive decimal number with 1 to 12 integer digits and at most 2 decimals (`100`, `100.5` and `100.25` are valid; `100.123`, `1e2`, `.5` and `0` are not). A valid `qty` is an integer from 1 to 10⁹.
- Ignore blank lines. No other malformed input needs handling.

### Matching rules

1. A new order first matches against the other side. A buy starts at the lowest ask and trades in turn with sells priced no higher than its limit; a sell starts at the highest bid and trades in turn with buys priced no lower than its limit.
2. Within one price level, the resting order that arrived first trades first (time priority).
3. Each trade is for the smaller of the two remaining quantities, **at the resting order's price**.
4. A resting order leaves the book when its remaining quantity reaches 0.
5. If the aggressor has quantity left after matching, it rests on its own side at its limit price, behind every order already at that level.
6. Orders in different symbols never match each other.

### Amend rules

The `qty` in `AMEND` is the new **remaining** quantity, not the order's original total.

- Same price and a new quantity no greater than the current remaining quantity: change the quantity in place and keep time priority. A new quantity equal to the current remaining quantity changes nothing.
- Price changed, or quantity increased: the same as cancelling the original order and inserting again with the same id, the same side, the new price and the new quantity. The order loses its place in the queue; if the new price crosses the other side, it trades immediately as the aggressor.

### Reject rules

Check in this order. On the first match, print a reject; the message has no other effect:

1. `price` or `qty` is invalid: `INVALID`.
2. The `id` of an `INSERT` was already used in this run by an `INSERT` that was **accepted**, even if that order has since filled or been cancelled: `DUPLICATE_ID`. A rejected `INSERT` does not consume its id.
3. The `id` of an `AMEND` or `CANCEL` is not currently on the book (never seen, fully filled, or cancelled): `UNKNOWN_ID`.

### Output

While processing each message, print events in the order they happen:

```text
TRADE <symbol> <price> <qty> <aggressor id> <resting id>
REJECT <id> <INVALID|DUPLICATE_ID|UNKNOWN_ID>
```

Prices are always printed with two decimals. When the input ends, for each symbol that still has resting orders, in lexicographic order of symbol name, print:

```text
BOOK <symbol>
BID <price> <total qty> <order count>     each bid level, highest price to lowest
ASK <price> <total qty> <order count>     each ask level, lowest price to highest
```

`total qty` is the sum of the remaining quantities of all orders at that level, and `order count` is the number of orders. Symbols with no resting orders are not printed.

### Example

```text
INSERT 1 AAPL SELL 101 5
INSERT 2 AAPL SELL 100 5
INSERT 3 AAPL SELL 100 5
INSERT 4 AAPL SELL 102 5
INSERT 5 AAPL BUY 101 12
```

Order 5 is a buy with limit 101. It first takes the two sells at the lowest price 100, in arrival order, 2 then 3, 5 each; then order 1 at 101 for the remaining 2. 102 is above its limit, so matching stops. Order 5 is exactly filled and does not rest; order 1 has 3 left. Output:

```text
TRADE AAPL 100.00 5 5 2
TRADE AAPL 100.00 5 5 3
TRADE AAPL 101.00 2 5 1
BOOK AAPL
ASK 101.00 3 1
ASK 102.00 5 1
```

### Stages

Onsite problems are often handed out in stages, each extending the code of the one before. We suggest implementing in this order and making each stage's tests pass before moving on:

| Stage | Content | Cases |
|---|---|---|
| 1 | `INSERT`, matching, book snapshot | 01–06 |
| 2 | `CANCEL`, the three rejects | 07–09, 17 |
| 3 | `AMEND` | 10–16 |
| 4 | Performance: hundreds of thousands of resting orders, tens of millions of messages per second; explain where your structure becomes the bottleneck | see "Measurements" |

### Test cases

Each case starts with `=== number description`; the input comes before `---` and the complete expected output after it. The case file and the runner script can be copied as they are.

<details markdown="1">
<summary>tests.txt (17 cases)</summary>

```text title="tests.txt"
=== 01 two non-crossing orders both rest
INSERT 1 AAPL BUY 100.00 10
INSERT 2 AAPL SELL 101.00 5
---
BOOK AAPL
BID 100.00 10 1
ASK 101.00 5 1
=== 02 full fill at the resting price; an empty book prints nothing
INSERT 1 AAPL SELL 100.50 10
INSERT 2 AAPL BUY 101 10
---
TRADE AAPL 100.50 10 2 1
=== 03 partial fill, the remainder rests
INSERT 1 AAPL SELL 100 4
INSERT 2 AAPL BUY 100 10
---
TRADE AAPL 100.00 4 2 1
BOOK AAPL
BID 100.00 6 1
=== 04 price then time priority, one buy sweeps two levels
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
=== 05 aggressive sell hits the highest bid first; the non-crossing remainder rests
INSERT 1 AAPL BUY 99 5
INSERT 2 AAPL BUY 100 5
INSERT 3 AAPL SELL 99.5 7
---
TRADE AAPL 100.00 5 3 2
BOOK AAPL
BID 99.00 5 1
ASK 99.50 2 1
=== 06 symbols never match each other; snapshot sorted by symbol
INSERT 1 MSFT BUY 50 10
INSERT 2 AAPL SELL 50 10
INSERT 3 AAPL BUY 50 3
---
TRADE AAPL 50.00 3 3 2
BOOK AAPL
ASK 50.00 7 1
BOOK MSFT
BID 50.00 10 1
=== 07 cancel; a second cancel and an unknown id are rejected
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
=== 08 a filled order cannot be cancelled; a used id cannot be reused
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
=== 09 invalid fields; a rejected INSERT does not consume its id
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
=== 10 same-price decrease keeps time priority
INSERT 1 AAPL BUY 100 10
INSERT 2 AAPL BUY 100 10
AMEND 1 100 4
INSERT 3 AAPL SELL 100 6
---
TRADE AAPL 100.00 4 3 1
TRADE AAPL 100.00 2 3 2
BOOK AAPL
BID 100.00 8 1
=== 11 increase loses time priority and goes to the back
INSERT 1 AAPL BUY 100 10
INSERT 2 AAPL BUY 100 10
AMEND 1 100 11
INSERT 3 AAPL SELL 100 12
---
TRADE AAPL 100.00 10 3 2
TRADE AAPL 100.00 2 3 1
BOOK AAPL
BID 100.00 9 1
=== 12 amend crosses; the amended order trades at once as aggressor
INSERT 1 AAPL SELL 101 5
INSERT 2 AAPL BUY 100 8
AMEND 2 101 8
---
TRADE AAPL 101.00 5 2 1
BOOK AAPL
BID 101.00 3 1
=== 13 AMEND qty is the new remaining qty: equal to remaining changes nothing
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
=== 14 amend an unknown or filled order
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
=== 15 amend sweeps several levels, the remainder rests at the new price
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
=== 16 fully filled after an amend, cannot be cancelled afterwards
INSERT 1 AAPL BUY 100 5
INSERT 2 AAPL SELL 101 5
AMEND 2 100 5
CANCEL 2
---
TRADE AAPL 100.00 5 2 1
REJECT 2 UNKNOWN_ID
=== 17 cancel from the middle of a queue; an emptied level leaves the book
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
# run_tests.py <executable> [args...]: runs each case in tests.txt and compares the output
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
python3 run_tests.py ./me          # optimized implementation
python3 run_tests.py ./me --ref    # reference implementation
```

## Design discussion

### What to ask before writing code

The statement above already fixes these semantics; onsite statements usually do not. Interviewers often leave them out on purpose to see whether you ask. Each one changes the code:

| Question | This problem | Another common answer |
|---|---|---|
| Whose price does a trade use | the resting order's | almost never anything else, but say it |
| Is the amend quantity remaining or total | remaining | total (this is how a FIX amend works) |
| When does an amend lose time priority | price change or quantity increase | some systems requeue on any amend |
| Price precision | two decimals, stored as an integer | each symbol has its own tick size |
| Scope of order id uniqueness | the whole run | unique per client, or assigned by the engine |
| Does a cancel carry the symbol | no | real protocols usually require it |
| Are acks and cancel confirmations printed | only trades and rejects | every message gets a response |
| Market orders, IOC and other order types | none | see follow-up 25 |

Once you have the answers, write them as a comment at the top of the code. When you hit a case you did not ask about while coding, state your assumption out loud, then carry on.

### Data structures

The operations a book must support, and what the standard answer costs for each:

| Operation | How | Cost |
|---|---|---|
| Find the best price on the other side | first element of a sorted container | O(1) |
| Fill a resting order | front of the best level's queue | O(1) |
| Rest a new order | find or create the level, append to the queue | finding the level O(log P), P the number of levels; appending O(1) |
| Cancel | find the order by id in the hash table, unlink it from its level's queue | O(1), plus O(log P) when the level empties |
| Amend (same price, smaller qty) | find the order in the hash table, change the quantity | O(1) |
| Snapshot | walk the levels in price order | O(P) |

The sorted container of levels can be a red-black tree (`std::map`) or a sorted array; the queue within a level must support removing an element from the middle in O(1), so it is a doubly linked list. The hash table stores the order's position in that list, which requires the position to stay valid while other orders are inserted and removed. The reference implementation below relies on exactly the guarantees the standard gives node-based containers.

### Invariants

Stating the invariants during the design discussion gives you something concrete to check while testing and debugging. This problem has five:

1. After each message, the book is not crossed: the highest bid is strictly below the lowest ask.
2. Each level's `total` equals the sum of the remaining quantities of its orders, and `count` equals the number of orders.
3. The book has no empty levels and no orders with remaining quantity 0.
4. The ids in the hash table are exactly the ids of the resting orders.
5. The queue at each level is in arrival order; an amend that loses priority counts as a new arrival.

## Reference implementation

Start with a version that is correct and easy to explain. If this version passes every test in the interview, most of the job is done.

```cpp title="common.hpp"
// common.hpp: types and the event interface shared by both engines, plus price and quantity parsing
#pragma once
#include <charconv>
#include <cstdint>
#include <optional>
#include <string>
#include <string_view>

using OrderId = std::uint64_t;
using Price = std::int64_t;  // in units of 0.01: 101.25 is stored as 10125
using Qty = std::int64_t;

enum class Side : std::uint8_t { Buy, Sell };
enum class Reject : std::uint8_t { Invalid, DuplicateId, UnknownId };

inline constexpr Qty kMaxQty = 1'000'000'000;

// The engine reports events through this. Callbacks must not call back into the engine.
struct Sink {
    virtual void on_trade(std::string_view symbol, Price px, Qty qty, OrderId aggressor, OrderId resting) = 0;
    virtual void on_reject(OrderId id, Reject why) = 0;

protected:
    ~Sink() = default;
};

// 1–12 integer digits, an optional point with 1–2 decimals, result must be positive. No double involved.
inline std::optional<Price> parse_price(std::string_view s) {
    Price v = 0;
    int int_digits = 0, frac_digits = -1;  // -1: no decimal point seen yet
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
// engine_ref.hpp: reference implementation. std::map sorted by price, one std::list per level, a hash table from id to order
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
        if (px == o.px && qty <= o.qty) {  // same price, smaller qty: keeps time priority
            loc.level->total -= o.qty - qty;
            o.qty = qty;
            return;
        }
        Order moved{id, o.side, px, qty};
        remove(it);
        execute(loc.symbol, *loc.book, moved);  // price change or qty increase: cancel and re-insert, may trade at once
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
        Qty qty;  // remaining quantity
    };
    using Queue = std::list<Order>;
    struct Level {
        Queue orders;  // earliest first
        Qty total = 0;
    };
    struct Book {
        std::map<Price, Level, std::greater<>> bids;  // begin() is the highest bid
        std::map<Price, Level> asks;                  // begin() is the lowest ask
    };
    // nodes of std::map and std::list do not move on insert or erase, so these stay valid
    struct Locator {
        std::string_view symbol;
        Book* book;
        Level* level;
        Queue::iterator pos;
    };

    // match against the other side first, rest the remainder on our own side
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
                sink_.on_trade(sym, r.px, q, in.id, r.id);  // trade at the resting order's price
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
    std::unordered_map<OrderId, Locator> live_;  // orders resting on the book
    std::unordered_set<OrderId> used_;           // every id ever accepted, to reject duplicates
};
```

```cpp title="main.cpp"
// main.cpp: reads messages from stdin, writes events and the final book to stdout. --ref selects the reference engine
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
        if (!(in >> cmd)) continue;  // blank line
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

Points worth saying out loud:

- `Locator` stores both a `Level*` and a `std::list` iterator. Inserting into a `std::map` does not affect existing iterators and references, and erasing only invalidates those to the erased element ([[associative.reqmts.general#175]]); the same holds for `std::list` insertion and erasure ([[list.modifiers#2]], [[list.modifiers#3]]). So both can be kept until the order leaves the book. With `std::vector` this would not work: an insertion may reallocate, invalidating every iterator and reference ([[vector.modifiers#2]]).
- The symbol table is `std::map<std::string, Book, std::less<>>`. The transparent comparator `std::less<>` lets `find` take a `std::string_view` directly, without first building a `std::string`. The `symbol` in `Locator` and in trade events points at this map's key, whose address is just as stable.
- Both amend paths share `execute`. A price change or quantity increase is a `remove` followed by running `execute` with the new parameters, so trading as aggressor, resting and updating the index need no separate code.
- Prices are parsed straight from the string into integers, never through `double`, and formatted back on output.
- `Sink` callbacks run in the middle of the matching loop, while the iterator `lvl` and the reference `r` are still in use. A callback that calls back into the engine could destroy them (follow-up 13).

## Optimized implementation

For every resting order, the reference implementation allocates once for a `std::list` node and once for a `std::unordered_map` node; red-black tree level nodes and list nodes are scattered over the heap, and every step of matching follows a pointer. The optimized version keeps the rules and the interface and changes only the data structures:

| Part | Reference | Optimized |
|---|---|---|
| Levels | `std::map<Price, Level>` | sorted `std::vector<Level>`, best price at the back |
| Queue within a level | `std::list<Order>` | nodes in an object pool, linked into a doubly linked list by 32-bit indices |
| Order index | `std::unordered_map` | open addressing with linear probing, shifting elements back on erase |
| Used ids | `std::unordered_set` | the same kind of open-addressing table |
| Allocation | twice per resting order | with capacity reserved, only occasional growth on the hot path when a new level appears |

The best price sits at the back of the `vector` because nearly all activity is near the top of book: taking out the best level is a `pop_back`, and adding or removing a level near the top only moves the few elements after it. Levels are found by binary search. Nodes refer to each other by index rather than pointer, so references survive growth of the pool's `vector`, and a node is only 40 bytes.

<details markdown="1">
<summary>engine_fast.hpp</summary>

```cpp title="engine_fast.hpp"
// engine_fast.hpp: same rules as RefEngine, with cache-friendly data structures that do not allocate on the hot path
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

// Open-addressing hash table from order id to a 32-bit value. Linear probing; erase shifts later
// affected elements back instead of leaving tombstones.
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

    // does nothing and returns false if id is already present
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
        while (slots_[i].id != id) i = next(i);  // the caller guarantees id is present
        // with i now empty, move back any later element in the same run that sits there only because i was taken
        for (std::size_t j = next(i); slots_[j].id != 0; j = next(j)) {
            std::size_t h = home(slots_[j].id);
            if (((j - h) & mask()) >= ((j - i) & mask())) {  // h is not in (i, j]
                slots_[i] = slots_[j];
                i = j;
            }
        }
        slots_[i].id = 0;
        --size_;
    }

private:
    struct Slot {
        OrderId id = 0;  // 0 marks an empty slot: order ids are positive
        std::uint32_t val = 0;
    };
    std::size_t mask() const { return slots_.size() - 1; }
    std::size_t next(std::size_t i) const { return (i + 1) & mask(); }
    std::size_t home(OrderId id) const { return (id * 0x9E3779B97F4A7C15ull) >> shift_; }  // Fibonacci hashing
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
    // expected_live: estimate of orders resting at once; expected_ids: estimate of orders over the whole session
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
        if (px == o.px && qty <= o.qty) {  // same price, smaller qty: keeps time priority
            level_of(o).total -= o.qty - qty;
            o.qty = qty;
            return;
        }
        std::uint32_t b = o.book;
        Side side = o.side;
        remove(*n);
        execute(b, id, side, px, qty);  // price change or qty increase: cancel and re-insert, may trade at once
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
    struct Node {  // 40 bytes
        OrderId id;
        Price px;
        Qty qty;
        std::uint32_t prev, next;  // doubly linked list within a level; when free, next links the free list
        std::uint32_t book;
        Side side;
    };
    struct Level {  // 32 bytes
        Price px;
        Qty total;
        std::uint32_t head, tail, count;
    };
    struct Book {
        std::string name;
        std::vector<Level> levels[2];  // [buy, sell], each ordered worst to best, best price at the back
    };

    static int idx(Side s) { return std::to_underlying(s); }
    static bool better(Side s, Price a, Price b) { return s == Side::Buy ? a > b : a < b; }

    // returns i such that every v[i..] is better than px and v[i-1], if any, is not. Binary search
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

    // takes a resting order off the book
    void remove(std::uint32_t n) {
        const Node& o = nodes_[n];
        auto& v = books_[o.book].levels[idx(o.side)];
        std::size_t i = lower(v, o.side, o.px) - 1;  // a resting order's level always exists
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
    IdMap live_;  // resting order -> node index
    IdMap used_;  // every id ever accepted (value unused), to reject duplicates
    std::vector<Node> nodes_;
    std::uint32_t free_ = kNil;
    std::vector<Book> books_;
    std::unordered_map<std::string, std::uint32_t, StrHash, std::equal_to<>> symbols_;
};
```
</details>

`IdMap::erase` uses backward-shift deletion for linear probing: after removing the element at position `i`, scan forward through the same run of occupied slots; if an element's home position `h` is not in `(i, j]` (computed cyclically), it was pushed past its home only because `i` was taken, so move it back to `i` and continue the scan with its old position as the new hole. The table then needs no tombstones, and a lookup can stop at the first empty slot.

### How to know the optimized version is right

The optimized version has more code, and indices and list links are easier to get wrong. Besides the 17 cases, run a **differential test** against the reference implementation: generate many random message sequences, feed each to both engines, and require identical event sequences (hashed) and identical final books. The generator deliberately keeps prices within 3 ticks of mid so that trades, multi-level sweeps and amends happen often, and mixes in duplicate ids and zero quantities.

<details markdown="1">
<summary>bench.cpp (differential test and timing)</summary>

```cpp title="bench.cpp"
// bench.cpp: generates random message streams, runs the differential test first (both engines must
// produce the same events and final book), then times each engine
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

// Message stream for the differential test. spread: how many ticks from mid a passive order may be;
// fuzz: mix in invalid quantities and duplicate ids
std::vector<Msg> generate(std::size_t n, std::uint64_t seed, int spread, bool fuzz) {
    std::mt19937_64 rng(seed);
    auto pick = [&](std::uint64_t k) { return rng() % k; };
    Price mid[8];
    std::ranges::fill(mid, 10'000);
    std::vector<OrderId> cand;  // orders that may still rest (the generator does not know which ones traded)
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
            Price off = r < 45 ? Price(1 + pick(spread)) : -Price(pick(4));  // the last 10% cross mid and will likely trade
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

// Message stream for timing: a RefEngine tracks which orders still rest while generating, cancels and
// amends target only resting orders, 70% of them among the 32 most recent (quotes refreshing all the
// time). The number of resting orders stays near target.
struct LiveTracker final : Sink {
    std::vector<Qty> rem;          // remaining quantity per id
    std::vector<OrderId> filled;   // resting orders filled by this message
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
            Price off = pick(100) < 85 ? Price(1 + pick(20)) : -Price(pick(4));  // 15% cross mid and will likely trade
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
    // 1. Differential test: many short random sequences in a narrow price range, with frequent trades,
    //    amends, duplicate ids and invalid quantities
    for (std::uint64_t seed = 1; seed <= 2000; ++seed) {
        auto msgs = generate(3000, seed, 3, true);
        if (replay<RefEngine>(msgs) != replay<FastEngine>(msgs, std::size_t(16), std::size_t(16))) {
            std::printf("mismatch at seed %llu\n", (unsigned long long)seed);
            return 1;
        }
    }
    std::puts("differential: 2000 seeds x 3000 messages agree");

    // 2. Timing at two depths: about 8 thousand resting orders (1 thousand per symbol) and about 800 thousand
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

The two engines produce identical output on 2000 random seeds of 3000 messages each, with no reports from AddressSanitizer or UndefinedBehaviorSanitizer.

## Measurements

### Method

The machine is an Apple M2 Pro, macOS, Homebrew Clang 23 + libc++, `-std=c++2c -O2`. The timed message streams are generated in memory beforehand, so text parsing and output are excluded, and events go to a `Sink` that only computes a hash:

- 8 symbols, each mid price on its own random walk;
- 85% of inserts are 1 to 20 ticks outside mid (passive), 15% cross mid by 0 to 3 ticks and will likely trade at once;
- while generating, the reference implementation tracks which orders still rest; cancels and amends target only resting orders, 70% of them among the last 32 entries in the candidate list, mostly recent orders, to mimic constantly refreshing quotes; the number of resting orders is steered toward a target;
- 10 million messages per depth. The shallow book has about 7 thousand resting orders on 636 levels, and its messages are 5.58 million inserts, 3.97 million cancels and 0.44 million amends; the deep book has about 400 thousand resting orders on 2668 levels, with 7.64 million inserts, 2.13 million cancels and 0.24 million amends.

Throughput takes the fastest of 5 repetitions; the whole program ran 3 times, and the table gives the median of the 3.

### Throughput

| Average time per message | Shallow book (~7k resting orders) | Deep book (~400k resting orders) |
|---|---|---|
| Reference | 94 ns | 178 ns |
| Optimized | 71 ns | 94 ns |
| Optimized, no duplicate-id check | 49 ns | 72 ns |
| Optimized, ids required to increase (`id <= last` is a duplicate) | 50 ns | 72 ns |

Three things stand out.

First, with a shallow book, changing the data structures only made it about a quarter faster. All the data for 7 thousand orders fits in L2 cache (16 MiB on our test machine; see [[perf/memory-hierarchy|the memory hierarchy]]), so the pointer chasing in the red-black tree and the lists mostly hits cache and is not very expensive. With a deep book, the reference implementation's list and hash nodes for resting orders are scattered over tens of MB of heap, while the optimized node pool is about 16 MB and contiguous, and the gap widens to nearly two times.

Second, the requirement to reject any id ever used is expensive in itself. With a shallow book only a few thousand orders rest at once, but more than five million ids are used over the run; the duplicate-check table has to hold all of them, far more than fits in cache, and each insert pays a cache miss that is close to certain. Dropping the check takes the shallow case from 71 ns to 49 ns, about as much as changing the data structures gained. If the protocol requires ids to increase, the check is a single comparison with the previous id and costs the same as no check. This is the measurement behind follow-up 5.

Third, of the remaining 49 ns, profiling with `sample` shows about 16% going to looking up the symbol name in a hash table (hashing and comparing strings). Real systems turn symbol names into integer ids at the gateway (follow-up 19).

### Latency distribution

Throughput is an average; trading systems care more about tail latency. Here each message is timed separately. On our test machine `steady_clock` has a step of 41 ns and one call to `now()` costs a dozen-odd nanoseconds (see [[perf/measuring|measuring]]), so the median column only takes values like 42, 83 and 125 and shows the order of magnitude, nothing finer. The maximum varied a lot across the 3 runs, so ranges are given.

| Shallow book | p50 | p99 | Max |
|---|---|---|---|
| Reference | 83 ns | 209–250 ns | 12–21 ms |
| Optimized, capacity reserved | 84 ns | 208–250 ns | 0.14–2.9 ms |
| Optimized, no reserve | 83 ns | 167–209 ns | 72–98 ms |
| Optimized, ids required to increase, capacity reserved | 42 ns | 125 ns | 0.02–0.1 ms |

Without reserved capacity, the duplicate-check table keeps doubling as ids accumulate, and the last growth rehashes several million elements into a new table of several hundred MB; that one message waits close to 100 ms. In the reference implementation, rehashing of `std::unordered_set` and `std::unordered_map` causes the same kind of stall: 12–21 ms with the shallow book, 25–34 ms with the deep one. For a matching engine such a stall is far worse than being a few nanoseconds slower on average, so capacity has to be reserved once before the market opens, and no rehash may happen during trading hours.

With capacity reserved, the optimized version still has millisecond-scale maxima. We did not track down every cause; with the shallow book, removing the duplicate-check table (requiring ids to increase) brings the maximum under 0.1 ms, so it is related to that table of several hundred MB. One possible cause is page faults on the first touch of each of its pages.

## Verbal follow-ups

The questions below are grouped by theme. They can come up during the design discussion or after the code is written. When answering, give the conclusion first, then the reason and the cost.

### 1. Requirements and semantics

#### 1. Why does a trade use the resting order's price?

The resting order came first and publicly quoted that price; the later order accepts it. If trades used the aggressor's price, an aggressor would have an incentive to send an extreme price to sweep the book, and the resting side would get a better price than it quoted, which serves no purpose in price discovery. A consequence: when a buy sweeps several levels, its trades are at different prices, none above its limit.

#### 2. Why define the amend quantity as remaining? What if it were the total?

Remaining quantity has the most direct meaning, but it has a race: when a client sends an amend, the remaining quantity it saw may be stale, with more filled in between, and amending by remaining quantity can make the total it actually trades exceed what it intended. Defining it as the total (as a FIX amend does) avoids this: the new remaining quantity is the new total minus the filled quantity, and a result of 0 or less acts as a cancel. The cost is that the engine has to track each order's filled quantity. In the interview, naming this race matters more than which option you pick.

#### 3. Why does a price change or quantity increase lose time priority, but a decrease does not?

Time priority rewards whoever rested first and took on the risk first. If an increase did not requeue, someone could rest 1 lot to hold the front of the queue, then amend it to 1000 lots and jump everyone behind them. A decrease only reduces one's own chance of a fill and harms no one else, so the position can be kept. A price change moves the order to a new level, where it never had a place in the queue.

#### 4. Why not use `double` for prices?

Binary floating point cannot represent most decimal fractions exactly: `0.1 + 0.2 != 0.3`. Prices are keys in a sorted container, are compared for equality (are two orders at the same level?) and are added and subtracted trade by trade; rounding error would split one price across two levels. So prices are integers in units of the minimum price increment (the tick), parsed directly from the string. In real systems each symbol has its own tick size, sometimes varying by price band, and an insert has to check that the price is a whole number of ticks.

#### 5. Who decides the scope of order id uniqueness? What does it cost?

This problem requires uniqueness over the whole run, so the engine must remember every id it has used; memory grows linearly with the number of messages, and in the measurements this table adds 20-odd nanoseconds per message and causes long stalls when it grows. Real systems usually do one of three things: client ids only need to be unique within a connection or a trading day, cleared daily; the protocol requires ids to increase, so the check is a single comparison; or the engine assigns its own internal id to each order and uses the client's id only for reconciliation. In the interview you can implement the statement as written first, then point this out.

#### 6. How does a client learn that an insert was accepted, partly filled, fully filled, or cancelled?

This problem only prints trades and rejects; real systems respond to every message: an acknowledgement, an execution report for each fill (with the remaining quantity), and confirmations of cancels and amends. Adding these events only takes new callbacks at the exits of `insert`, `cancel` and `amend`; the data structures stay the same. Mind the order of events: for example, the acknowledgement of an aggressive order should come before the execution reports it causes.

### 2. Data structures

#### 7. Why not `std::priority_queue`?

A heap gives the best price quickly but cannot remove an element from the middle, so it cannot cancel. The usual workaround is lazy deletion: a cancel only marks the order, which is discarded when it rises to the top. Cancelled orders then keep occupying memory, the top of the heap can fill with cancelled orders, and finding the best price becomes amortized rather than strictly O(1); in real markets cancels far outnumber fills, so this cost is real. Time priority within a level also requires putting an arrival sequence number into the comparison key.

#### 8. How is a cancel O(1)? Which positions can be kept long term?

A hash table goes from the id straight to the order's position, which is then unlinked from the doubly linked list. The key is that the stored position stays valid after other operations. Insertion into `std::map` and `std::list` does not affect existing iterators and references, and erasure only affects the erased element; growth of `std::unordered_map` invalidates iterators but not pointers and references to elements ([[unord.req.general#9]]); once a `std::vector` reallocates, every reference is invalid. The optimized implementation uses indices instead, which stay valid when the `vector` grows.

#### 9. If the price range is bounded, can it be faster?

Replace the sorted container with an array indexed by tick, one element per level, and keep the indices of the best bid and best ask. Finding the level for a new order or a cancel becomes O(1). There are two costs: the array's size is proportional to the price range, and a large array for each of thousands of symbols takes a lot of memory; and once a level is emptied, you have to scan toward worse prices for the next non-empty one, which can be a long scan on a sparse book, though a bitmap can speed it up. A common compromise is an array only for a band of prices near the top of book, with levels far from it in a sorted container.

#### 10. Why does the optimized implementation put the best price at the back of the `vector`?

Inserting into or erasing from the middle of a sorted array moves every element after it. Nearly all activity is near the top of book; with the top at the back, only the few levels better than the one touched have to move, and taking out the best level is a `pop_back` that moves nothing. With the best price at the front, every new level at the top would move the whole array. This choice depends on activity concentrating near the top; if the book is deep and cancels are spread evenly over all levels, inserting and erasing levels in a sorted array becomes O(P).

#### 11. What makes `std::list` slow?

Each node is allocated separately, and on our test machine a small `malloc` plus `free` is about 20 ns (see [[perf/allocation|heap allocation]]); nodes are scattered over the heap, so every step through a level's queue may miss the cache; and each node carries two pointers and allocator overhead besides its data. An object pool keeps the nodes in one contiguous `vector` and links freed nodes into a free list, so allocating and freeing each just update an index.

#### 12. Why do nodes refer to each other by 32-bit index rather than pointer?

An index is half the size of a pointer, so nodes are smaller and more of them fit in a cache line. When the pool's `vector` grows it moves to a new address, which invalidates pointers but not indices. Indices can also be written directly into a snapshot file and need no relocation on recovery. A 32-bit index limits the number of simultaneously resting orders to about 4 billion, which is plenty for one group of symbols.

### 3. Correctness

#### 13. What happens if the trade callback calls `cancel`?

The matching loop is holding an iterator to the current level and a reference to the current resting order. If the callback cancels that very order, or the last order at that level, the loop resumes using a destroyed object, which is undefined behavior. There are three options: state that callbacks must not re-enter and check it with a flag in debug builds; queue events and dispatch them after the whole message is processed; or make every external request a message that is queued and processed in order, so a callback can only send messages. Real matching engines usually do the last.

#### 14. How do you test it?

Four layers. The first is cases written rule by rule, like the 17 above, with at least one case that just triggers each rule and one that just misses it. The second is invariant checks: in debug builds, check the five invariants listed earlier after every message. The third is differential testing: use an implementation too simple to get wrong (even one that scans every order linearly each time) as the reference and compare outputs on lots of random input. The fourth is sanitizers: ASan catches out-of-bounds access and use after free, UBSan catches overflow. See [[toolchain/testing|testing, sanitizers and fuzzing]].

#### 15. Which edge cases are easy to miss?

An order sweeping several levels; an exact fill must neither rest nor leave an entry in the index; a level emptied by fills or cancels must be removed from the book, or the snapshot prints a level with quantity 0 and the best price is wrong; an amend that crosses the other side; an order fully filled after an amend, which a later cancel must reject as unknown; a rejected insert must not consume its id; cancelling an order from the middle of a level's queue.

#### 16. Can quantities and notional overflow?

A single quantity is at most 10⁹; a level's total, even with a million orders, is at most 10¹⁵, which fits in `int64_t`. But computing notional, with a maximum price of 10¹⁴ (in cents) times a quantity of 10⁹, overflows `int64_t`, and signed overflow is undefined behavior. Either limit the price and quantity ranges, or use 128-bit integers or checked multiplication (`__builtin_mul_overflow`).

### 4. Performance

#### 17. Where does the hot path allocate? How do you get rid of it?

In the reference implementation, a new level allocates a `std::map` node, each resting order allocates a `std::list` node and a `std::unordered_map` node, each new id allocates a `std::unordered_set` node, and a rehash allocates a whole new table. The optimized implementation removes all of these with an object pool and open-addressing tables with reserved capacity, leaving only occasional growth of a level `vector`. The measurements show the average differs only moderately while the maximum latency differs by more than two orders of magnitude, so reserve capacity before the open and monitor how close you are to the limit.

#### 18. What did your benchmark measure, and what did it not?

It measured the throughput and per-message latency of the engine alone on pre-generated messages, excluding parsing, networking and output. What it did not measure may all matter more than the engine: the distribution of real market traffic (random messages are hard for the branch predictor, and real traffic tends to be more regular), end-to-end latency, and interference between symbols sharing cache. The credible approach is to record a real message stream and replay it. Per-message latency is limited by the timer's step; on our test machine you only see multiples of 41 ns.

#### 19. What do you do about symbol name strings?

In this problem's interface every call passes a string, and the engine hashes and compares it; profiling shows this takes about 16% of the time. Real systems map symbol names to integer ids when a client connects or subscribes, the engine uses only the ids internally, and books can be stored directly in an array indexed by id. Names are looked up again on output.

#### 20. How do you use multiple cores?

Books for different symbols are independent, so shard by symbol: each thread owns a group of symbols and their books, with no locks at all. A gateway thread dispatches messages by symbol into a single-producer single-consumer queue for each matching thread. The queue's read and write indices must sit on different cache lines, or false sharing results (see [[perf/false-sharing|false sharing]]). In this problem `CANCEL` and `AMEND` carry no symbol, so after sharding the gateway does not know which thread to send them to and needs a global table from id to symbol; this is one reason real protocols require cancels to carry the symbol. One book should never be matched by several threads at once: the matching order is itself part of the rules.

#### 21. Which thread does logging and execution reports?

Not the matching thread. The matching thread only writes events into a preallocated ring buffer, and another thread formats, logs and sends them. String formatting, system calls and network sends all take far longer than matching itself, and unpredictably so.

#### 22. What does a virtual `Sink` cost?

One indirect call per trade. The target is always the same, so the branch predictor guesses it easily, and the cost is usually within a few nanoseconds; we did not measure it separately. To remove it, make `Sink` a template parameter so the compiler can inline the callbacks. The cost is that the engine's code goes into headers and is instantiated once per `Sink` type.

### 5. The real world

#### 23. How do you recover after a crash?

Make the matching engine deterministic: the same input sequence always produces the same output. Then, before a message enters the engine, give it a sequence number and write it to a persistent log. After a crash, load the book from the latest snapshot and replay the log since that snapshot to get back to the state before the crash; failover can work the same way, with a standby replaying the same input stream live. Determinism requires that the engine never read the system clock (the gateway stamps times into messages), that output never depend on hash-table iteration order (which is why this problem's snapshot is sorted by symbol name), and that it never read uninitialized memory.

#### 24. Who decides the time in time priority?

The engine does: specifically, the order in which messages enter the engine and receive sequence numbers, not the timestamp the client writes in the message, nor the time the gateway received it. Client clocks cannot be trusted, and clocks across gateways never agree exactly. It also means fairness has to be guaranteed at the gateway layer, for example by feeding each connection's messages into one sequence in arrival order.

#### 25. What other order types are there? What does each change?

A market order has no price and matches until the other side is empty or its quantity is used up; the remainder is usually cancelled, and many exchanges give it a protection price so it cannot sweep to absurd levels. IOC (immediate or cancel) does not rest after matching. FOK (fill or kill) must first check that the other side has enough total quantity within its limit, which is where each level's `total` pays off; if not, the whole order is rejected rather than partly filled. Post-only only provides liquidity: if it would trade immediately it is rejected or repriced. An iceberg order shows only part of its quantity; once the visible part fills it is replenished from the hidden part, and the replenished part goes to the back of the queue. A stop order becomes an ordinary order only when the last trade price reaches its trigger, which needs another book sorted by trigger price.

#### 26. What if a trader's buy meets the same trader's sell?

This is a self-trade, which many markets prohibit or require firms to prevent, because it can be used to fake volume. The remedy is self-trade prevention: orders carry an account or trader identifier, and when matching finds that the counterparty is the same party, the rule says to cancel the new order, cancel the old one, cancel both, or decrement both quantities against each other. It takes one more comparison in the matching loop; which rule applies is a business requirement, and you should ask.

#### 27. How does an opening auction match?

During the auction orders rest but do not trade. When the auction ends, a single price is chosen that maximizes the quantity that can trade at it; ties are broken by rules such as smallest remaining imbalance, then closest to a reference price. The algorithm: over all price levels that appear, accumulate the total buy quantity at or above each price and the total sell quantity at or below it; the smaller of the two is the volume at that price, and one pass over the levels suffices. Then every order that can trade does so at that price, still allocated by price priority, then time priority.

#### 28. Market makers do not run exchanges. Why do they ask about matching engines?

Order books are everywhere in a market maker's systems: rebuilding the full book from an exchange's order-by-order market data (each order's add, modify and delete) uses nearly the same data structures as this problem, minus matching, plus handling dropped packets and filling gaps by sequence number; backtesting and simulated trading must model how one's own orders queue and fill on the exchange, which is a matching engine; and estimating one's own position in a queue directly drives quoting strategy. What the problem tests is the ability to explain data structures, edge rules and performance clearly, all at once.

#### 29. Where do risk checks go?

Before the order reaches the matching engine, usually in the gateway or a separate risk module: is the price too far from a reference price (price bands), is the quantity over a limit (catching fat-finger errors), are the account's position and funds sufficient, is the message rate over a limit, and a kill switch that stops all trading for an account at once. The matching engine also keeps a last check of its own, for example that a trade price stays within the day's price limits.

#### 30. Does every market allocate by time priority?

No. Some futures use pro-rata allocation: at one level, the traded quantity is split among all resting orders in proportion to their sizes, sometimes with a priority share for the first order to arrive. The queue within a level then needs more than its front: matching walks the whole level and handles the leftovers from rounding, and the `total` field becomes essential. If the statement says nothing about it, you can raise it yourself and explain where your structure would have to change.

## How to spend the two hours

| Time | What to do |
|---|---|
| 0–10 min | Restate the problem, ask about the semantics in the table above, write the answers down as comments |
| 10–30 min | Draw the data structures, give the complexity of each operation, state the invariants |
| 30–50 min | Walk through the edge cases, describe the test plan, agree on the interface |
| 50–60 min | Discuss performance targets: message rate, number of resting orders, latency requirements, what becomes the bottleneck first |
| 60–90 min | Write the reference implementation; get the stage 1 and 2 tests passing first |
| 90–110 min | Add amends, cover the edge cases, run all the tests |
| 110–120 min | Explain how you would optimize with more time, and the risks of those changes |

While coding, get it right before getting it fast. A clearly structured reference implementation that passes every test, plus a clear account of where you would optimize, is usually more convincing than a half-written optimized one. When you get stuck, say what you are checking; interviewers often give hints.

## Summary

| Aspect | Key points |
|---|---|
| Rules | price priority, then time priority; trade at the resting price; the remainder rests; a price change or quantity increase loses priority |
| Structure | sorted table of levels + one FIFO queue per level + hash table from id to position |
| Correctness | stored positions must stay valid across other operations; callbacks must not re-enter; five invariants; differential testing |
| Performance | with a shallow book, the cache hides pointer chasing; with a deep book, contiguous storage is nearly twice as fast; remembering every id is expensive in itself; reserve capacity to avoid rehash stalls |
| Discussion | ask about semantics first; state the cost of each choice; be able to say what changes when a requirement changes |
