---
title: Observers and callback lifetimes
summary: "A subject notifies a set of observers; the hard part is not the notification but which side dies first: what raw pointer lists, unsubscribing in the destructor, weak_ptr and RAII connection objects each protect against, how reentrancy during notification and callbacks invoked under a lock go wrong, and dangling captured this in callbacks."
tags: design patterns, observer, callbacks, lifetime, weak_ptr, concurrency, topic
updated: 2026-10-19
---

!!! tldr
    - The observer pointers a subject stores do not own the objects. If an observer is destroyed without unsubscribing, the next notification calls a member function through a dangling pointer, which is UB; ASan reports heap-use-after-free.
    - Unsubscribing in the observer's destructor is reliable only in a single thread. With multiple threads, the derived part is already destroyed before the base destructor runs, and a notification from another thread can reach a half-destroyed object.
    - Storing observers as `weak_ptr` and calling `lock()` when notifying, or having subscription return a connection object that unsubscribes in its destructor, hands the question of who dies first to the type system. `std::stop_callback` is the standard library's version of such a connection object.
    - Subscribing or unsubscribing from inside a callback modifies the container during iteration and invalidates iterators. The fixes are iterating over a snapshot, or marking removals and deferring cleanup until the outermost notification ends. Calling callbacks while holding a lock deadlocks; copy under the lock and call outside it.
    - When a callback captures `this`, the object's lifetime must cover every possible call. Across threads, capture `weak_from_this()` and `lock()` it first when the callback runs.

## An observer list that crashes

In the **observer pattern**, a subject keeps a set of observers and notifies each of them when its state changes. The most direct C++ version stores raw pointers:

```cpp run title="naive.cpp" ub
#include <algorithm>
#include <cstdio>
#include <vector>

struct Observer {
  virtual void on_event(int) = 0;
  virtual ~Observer() = default;
};

class Subject {
  std::vector<Observer*> obs_;   // doesn't own them, doesn't know when they die
public:
  void attach(Observer* o) { obs_.push_back(o); }
  void detach(Observer* o) { std::erase(obs_, o); }
  void notify(int v) { for (Observer* o : obs_) o->on_event(v); }
};

struct Printer : Observer {
  int id;
  explicit Printer(int i) : id(i) {}
  void on_event(int v) override { std::printf("%d got %d\n", id, v); }
};

int main() {
  Subject s;
  Printer a(1);
  s.attach(&a);
  auto b = new Printer(2);
  s.attach(b);
  s.notify(10);
  delete b;          // forgot to detach
  s.notify(20);      // UB: virtual call through a dangling pointer
}
```

`delete b` ends the lifetime of `*b`, but the pointer in `obs_` is still there. The second `notify` calls a non-static member function through it, which [[basic.life#7]] bullet 7.2 makes UB. Run with Clang 23 and `-fsanitize=address`, it reports `heap-use-after-free` in `Subject::notify`; the 8 bytes read are the vptr at the start of the object (the virtual table pointer; see [[toolchain/object-layout-and-vtables]]).

The root of the problem is that ownership is not expressed. `Subject` borrows the observers, yet the borrower outlives what it borrowed. The rest of this page answers one question: how does `Subject` know, before calling, that an observer is still alive, and keep it alive for the duration of the call? The general discussion of ownership is in [[topics/ownership-and-smart-pointers]].

## Unsubscribing in the destructor

The first idea is to have the observer remove itself automatically on destruction. Put `attach` and `detach` in the base constructor and destructor, and derived classes can't forget:

```cpp run title="dtor-detach.cpp" ub
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <mutex>
#include <thread>
#include <vector>

class Subject;

class Observer {
  Subject& s_;
public:
  explicit Observer(Subject& s);
  virtual void on_event(int) = 0;
  virtual ~Observer();            // unsubscribes in the destructor
};

class Subject {
  std::mutex m_;
  std::vector<Observer*> obs_;
public:
  void attach(Observer* o) { std::lock_guard g(m_); obs_.push_back(o); }
  void detach(Observer* o) { std::lock_guard g(m_); std::erase(obs_, o); }
  void notify(int v) {
    std::lock_guard g(m_);
    for (Observer* o : obs_) o->on_event(v);
  }
};

Observer::Observer(Subject& s) : s_(s) { s_.attach(this); }
Observer::~Observer() { s_.detach(this); }

struct Counter : Observer {
  std::vector<int> seen;          // a member of the derived class
  using Observer::Observer;
  void on_event(int v) override { seen.push_back(v); }
};

int main() {
  Subject s;
  std::atomic<bool> stop{false};
  std::thread t([&] { for (int i = 0; !stop; ++i) s.notify(i); });
  for (int i = 0; i < 1000; ++i) {
    Counter c(s);                 // subscribes on construction, unsubscribes on destruction
  }
  stop = true;
  t.join();
}
```

In a single-threaded program this design is reliable: nobody else can call `notify` while `~Counter` runs. With multiple threads it still goes wrong, even though every operation of `Subject` is locked, because unsubscription happens too late.

Destroying a `Counter` goes like this: first the body of `~Counter` runs, then the member `seen` is destroyed, and finally the base `~Observer` is called ([[class.dtor#13]]). The object's lifetime has already ended when `~Counter` starts ([[basic.life#2]] bullet 2.4), but it disappears from the list only when `~Observer` gets the lock. In between, a `notify` on another thread can still call `on_event` through the pointer in the list.

Run with Clang 23 and `-fsanitize=thread`, TSan first reports `data race on vptr (ctor/dtor vs virtual call)`, and then the program aborts with `libc++abi: Pure virtual function called!`. The reason is that during destruction the implementation changes the vptr to each base class's vtable in turn; on entering `~Observer` the vtable is already `Observer`'s, where `on_event` is pure virtual. The `attach(this)` in the constructor has the symmetric problem: after the base is constructed but before the derived class is, the object is already visible to other threads.

!!! pitfall "Unsubscribing in the destructor is not thread safety"
    Unsubscribing in the destructor solves forgetting to unsubscribe, not concurrency. Across threads, an observer must guarantee it will not be called again before it starts being destroyed, either through ownership (`weak_ptr`, next section) or by having unsubscription block until any in-progress callback finishes (`stop_callback`, later).

## `weak_ptr`: confirm the object is alive when notifying

If observers are owned by `shared_ptr`, the subject can store `weak_ptr`s. A `weak_ptr` does not keep the object alive, but its `lock()` atomically checks whether the object is alive and obtains a `shared_ptr` ([[util.smartptr.weak.obs#3]]). The `shared_ptr` obtained guarantees the object is not destroyed during the callback:

```cpp run title="weak.cpp" ok
#include <atomic>
#include <cstdio>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

struct Observer {
  virtual void on_event(int) = 0;
  virtual ~Observer() = default;
};

class Subject {
  std::mutex m_;
  std::vector<std::weak_ptr<Observer>> obs_;
public:
  void attach(std::weak_ptr<Observer> o) {
    std::lock_guard g(m_);
    obs_.push_back(std::move(o));
  }
  void notify(int v) {
    std::vector<std::shared_ptr<Observer>> alive;
    {
      std::lock_guard g(m_);
      std::erase_if(obs_, [&](const std::weak_ptr<Observer>& w) {
        auto p = w.lock();             // atomically check and take ownership
        if (!p) return true;           // already destroyed: clean it up on the way
        alive.push_back(std::move(p));
        return false;
      });
    }
    for (auto& p : alive) p->on_event(v);   // called without the lock; p keeps the object alive
  }
};

struct Counter : Observer {
  std::vector<int> seen;
  void on_event(int v) override { seen.push_back(v); }
};

int main() {
  Subject s;
  std::atomic<bool> stop{false};
  std::thread t([&] { for (int i = 0; !stop; ++i) s.notify(i); });
  for (int i = 0; i < 1000; ++i) {
    auto c = std::make_shared<Counter>();
    s.attach(c);
  }                                    // the last owner may be p in the notifying thread
  stop = true;
  t.join();
  std::puts("done");
}
```

Five consecutive runs under TSan and one under ASan plus UBSan reported nothing in our tests. Compared with the previous section, observers no longer need to unsubscribe actively: once destroyed, `lock()` returns null and `notify` cleans them up along the way.

This design has three consequences worth knowing:

- Observers must be owned by `shared_ptr`. Objects on the stack, or owned by `unique_ptr`, cannot be registered this way.
- The `p` in `notify` may be the last owner. If `c` in `main` goes out of scope first, the `Counter` is destroyed on the notifying thread, before `notify` returns. If the destructor takes locks or touches thread-local state, account for this.
- An expired `weak_ptr` does not release the control block. For an observer created with `make_shared`, the object and the control block share one allocation, and the whole block is not freed until the `weak_ptr` is cleaned up.

Storing `weak_ptr`s in a `std::set` with `std::owner_less`, and why calling `expired()` before `lock()` is a race, are covered in the `weak_ptr` section of [[topics/ownership-and-smart-pointers]].

## Connection objects: unsubscribing on destruction

The `weak_ptr` approach requires the observer to be an object owned by `shared_ptr`. Often the observer is just a callback function, and the subscriber wants this: as long as I hold a certain thing, the callback is valid; once that thing is destroyed, the callback is no longer called. That thing is called a **connection** object. It is an RAII handle, whose destructor releases the resource it acquired, here the subscription (see [[patterns/raii]]).

The connection object has its own lifetime problem: it may outlive the subject. The `Signal` below keeps the subscription list in a `State` owned by a `shared_ptr`, and connection objects hold only a `weak_ptr` to it, so if the subject is destroyed first, unsubscribing does nothing:

```cpp title="signal.hpp"
#include <atomic>
#include <functional>
#include <memory>
#include <mutex>
#include <utility>
#include <vector>

template <class... Args>
class Signal {
  struct Slot {
    std::function<void(Args...)> fn;
    std::atomic<bool> connected{true};
  };
  struct State {
    std::mutex m;
    std::vector<std::shared_ptr<Slot>> slots;
  };
  std::shared_ptr<State> st_ = std::make_shared<State>();

public:
  class Connection {
    std::weak_ptr<State> st_;
    std::weak_ptr<Slot> slot_;
  public:
    Connection() = default;
    Connection(std::weak_ptr<State> st, std::weak_ptr<Slot> s)
      : st_(std::move(st)), slot_(std::move(s)) {}
    Connection(Connection&&) noexcept = default;
    Connection& operator=(Connection&& o) noexcept {
      disconnect();
      st_ = std::move(o.st_);
      slot_ = std::move(o.slot_);
      return *this;
    }
    ~Connection() { disconnect(); }   // unsubscribes on leaving scope

    void disconnect() {
      auto s = slot_.lock();
      if (!s) return;
      s->connected = false;           // skip it if not yet called in this round
      if (auto st = st_.lock()) {     // the Signal may already be gone
        std::lock_guard g(st->m);
        std::erase(st->slots, s);
      }
      slot_.reset();
    }
  };

  [[nodiscard]] Connection connect(std::function<void(Args...)> f) {
    auto s = std::make_shared<Slot>();
    s->fn = std::move(f);
    std::lock_guard g(st_->m);
    st_->slots.push_back(s);
    return Connection(st_, s);
  }

  void emit(Args... args) {
    std::vector<std::shared_ptr<Slot>> snapshot;
    {
      std::lock_guard g(st_->m);
      snapshot = st_->slots;          // the lock is held only for copying
    }
    for (auto& s : snapshot)          // called without the lock
      if (s->connected) s->fn(args...);
  }
};
```

`Connection` is move-only: two handles unsubscribing the same callback makes no sense. Its move constructor is defaulted; the moved-from `weak_ptr`s become empty, so `disconnect()` returns immediately when the moved-from object is destroyed. `connect` is marked `[[nodiscard]]`, because discarding the return value destroys the temporary `Connection` at the semicolon, unsubscribing the callback right after subscribing it; Clang 23 warns with `-Wunused-result` for `s.connect(f);`.

The shape of `emit` is the conclusion of the next two sections; for now just note it: copy a snapshot of `shared_ptr<Slot>` under the lock, unlock, then call each one, checking `connected` before each call.

!!! note "Connection objects in the standard library"
    `std::stop_callback` ([[thread.stoptoken]]) is such a handle: construction registers the callback with the stop state, and destruction deregisters it ([[stopcallback.cons#3]]). The standard adds one more requirement on deregistration: if the callback is executing on another thread, deregistration blocks until it returns; if it is executing on the current thread (the callback destroys its own `stop_callback`), it does not block ([[stoptoken.concepts#3]] bullets 3.3.3 and 3.3.4). The `Signal` above provides no such guarantee; its consequences come up later.

## Reentrancy: subscribing and unsubscribing during notification

What a callback does often modifies the subject in turn: unsubscribing itself after one event, or subscribing a new callback in response to an event. This is called **reentrancy**. If `notify` iterates the container directly, reentrancy modifies the container during iteration:

```cpp run title="reentrant.cpp" ub
#include <cstdio>
#include <functional>
#include <vector>

class Subject {
  std::vector<std::function<void(int)>> slots_;
public:
  void subscribe(std::function<void(int)> f) { slots_.push_back(std::move(f)); }
  void notify(int v) {
    for (auto& f : slots_) f(v);    // slots_ must not change during iteration
  }
};

int main() {
  Subject s;
  s.subscribe([&](int v) {
    std::printf("first %d\n", v);
    s.subscribe([](int) {});        // subscribing during notification: push_back may reallocate
  });
  s.subscribe([](int v) { std::printf("second %d\n", v); });
  s.notify(1);                      // UB
}
```

When `push_back` makes `size()` exceed `capacity()`, it reallocates and invalidates every reference and iterator to the elements ([[vector.modifiers#2]], [[g:iterator-invalidation|iterator invalidation]]). The range-`for`'s iterator and the executing `f` both point into the old buffer. ASan in our tests reports `heap-use-after-free` inside `std::function::operator()`, accessing a freed 64-byte region, exactly two 32-byte `std::function`s.

Unsubscribing is the same. `erase` invalidates iterators at and after the erased position ([[vector.modifiers#4]]), and if what is erased is the `std::function` currently executing, the closure object it holds is destroyed before its own `operator()` has returned; any later access to a captured variable accesses an object whose lifetime has ended.

There are two common fixes.

### Iterating a snapshot

`Signal::emit` copies `slots` under the lock to get a snapshot, then iterates the snapshot. A `connect` inside a callback modifies `State::slots`, not the snapshot being iterated; a newly subscribed callback takes effect from the next `emit`.

The snapshot stores `shared_ptr<Slot>`, not copies of `std::function`. This has two benefits: the copy costs one atomic increment and decrement per slot, without copying the state captured by closures; and when a callback unsubscribes itself, the `Slot` is owned by the snapshot, so the executing `fn` is not destroyed. The `connected` flag makes callbacks that were unsubscribed during this round, but are still in the snapshot, get skipped:

```cpp title="signal-test.cpp" ok
#include "signal.hpp"
#include <cstdio>
#include <optional>

int main() {
  Signal<int> sig;
  std::optional<Signal<int>::Connection> self, added;
  auto keep = sig.connect([](int v) { std::printf("keep %d\n", v); });
  self = sig.connect([&](int v) {
    std::printf("once %d\n", v);
    self.reset();                     // unsubscribe from within its own callback
    added = sig.connect([](int v) { std::printf("added %d\n", v); });
  });
  sig.emit(1);                        // keep 1, once 1; added takes effect next round
  sig.emit(2);                        // keep 2, added 2

  Signal<int>::Connection late;
  {
    Signal<int> tmp;
    late = tmp.connect([](int) {});
  }                                   // the Signal is destroyed first
}                                     // late is destroyed: weak_ptr expired, does nothing
```

This program must be compiled together with `signal.hpp` above. Run under ASan plus UBSan in our tests, it prints `keep 1`, `once 1`, `keep 2`, `added 2`, with no reports.

### Marking removals, deferring cleanup

The cost of a snapshot is an allocation on every notification. For single-threaded code with frequent notifications, you can instead keep the container unchanged during notification: unsubscribing only sets a mark, subscribing goes into a pending list first, and everything is cleaned up when the outermost `notify` finishes.

```cpp run title="deferred.cpp" ok
#include <cstdio>
#include <functional>
#include <vector>

class Subject {
  struct Slot { int id; std::function<void(int)> fn; bool alive = true; };
  std::vector<Slot> slots_, pending_;
  int depth_ = 0, next_id_ = 0;

  void flush() {                       // cleans up only when the outermost notification ends
    std::erase_if(slots_, [](const Slot& s) { return !s.alive; });
    for (auto& s : pending_) slots_.push_back(std::move(s));
    pending_.clear();
  }
public:
  int subscribe(std::function<void(int)> f) {
    auto& v = depth_ ? pending_ : slots_;   // during notification: into the pending list
    v.push_back({next_id_, std::move(f)});
    return next_id_++;
  }
  void unsubscribe(int id) {
    for (auto* v : {&slots_, &pending_})
      for (auto& s : *v)
        if (s.id == id) s.alive = false;   // only marks it; fn is not destroyed
    if (!depth_) flush();
  }
  void notify(int v) {
    ++depth_;
    struct Guard {                     // restores depth_ even if a callback throws
      Subject& s;
      ~Guard() { if (--s.depth_ == 0) s.flush(); }
    } g{*this};
    for (std::size_t i = 0; i < slots_.size(); ++i)   // slots_ is not changed during notification
      if (slots_[i].alive) slots_[i].fn(v);
  }
};

int main() {
  Subject s;
  int self = -1;
  s.subscribe([](int v) { std::printf("keep %d\n", v); });
  self = s.subscribe([&](int v) {
    std::printf("once %d\n", v);
    s.unsubscribe(self);
    s.subscribe([](int v) { std::printf("added %d\n", v); });
  });
  s.notify(1);                         // keep 1, once 1
  s.notify(2);                         // keep 2, added 2
}
```

The output is the same as the snapshot version, and ASan plus UBSan report nothing in our tests. The `depth_` counter keeps a nested `notify` (a callback triggering another notification) from cleaning up early. `Guard` ensures the counter is restored even if a callback throws; otherwise every later subscription would stay in `pending_` forever.

| | Iterating a snapshot | Marking removals, deferring cleanup |
|---|---|---|
| Extra cost per notification | one allocation, one atomic increment/decrement per slot | none |
| Subscribing during notification | takes effect next round | takes effect next round |
| Unsubscribing during notification | skipped for the rest of this round (via the `connected` flag) | skipped for the rest of this round |
| Multiple threads | yes, the lock protects only the copy | no; `depth_` and both containers are unsynchronized |
| The executing callback unsubscribes itself | safe; the snapshot owns the `Slot` | safe; `fn` is not destroyed before cleanup |

## Callbacks under a lock, and deadlock

A multithreaded subject needs a lock to protect the subscription list. The easiest approach holds the lock for the whole of `notify`, which can deadlock in two ways.

The first is reentrancy on the same thread. A callback calls `subscribe`, and the same thread locks the same `std::mutex` a second time:

```cpp run title="self-lock.cpp" ub
#include <functional>
#include <mutex>
#include <vector>

class Subject {
  std::mutex m_;
  std::vector<std::function<void(int)>> slots_;
public:
  void subscribe(std::function<void(int)> f) {
    std::lock_guard g(m_);
    slots_.push_back(std::move(f));
  }
  void notify(int v) {
    std::lock_guard g(m_);          // calls callbacks while holding the lock
    for (auto& f : slots_) f(v);
  }
};

int main() {
  Subject s;
  s.subscribe([&](int) { s.subscribe([](int) {}); });   // subscribes again inside a callback
  s.notify(1);                      // UB: the same thread locks std::mutex again
}
```

The precondition of `std::mutex::lock()` is that the calling thread does not own the mutex ([[thread.mutex.requirements.mutex.general#6]]), and violating a library function's precondition is UB ([[structure.specifications#3]] bullet 3.4). In our tests the program simply hangs, with or without TSan. Switching to `std::recursive_mutex` keeps it from hanging, but then the lock no longer protects anything and the problem becomes the iterator invalidation of the previous section.

The second is two threads taking two locks in opposite orders. The notifying thread holds `Subject`'s lock and takes `Model`'s lock in a callback; another thread holds `Model`'s lock and subscribes on `Subject`:

```cpp run title="lock-order.cpp"
#include <cstdio>
#include <functional>
#include <mutex>
#include <thread>
#include <vector>

class Subject {
  std::mutex m_;
  std::vector<std::function<void(int)>> slots_;
public:
  void subscribe(std::function<void(int)> f) {
    std::lock_guard g(m_);
    slots_.push_back(std::move(f));
  }
  void notify(int v) {
    std::lock_guard g(m_);               // locks Subject first
    for (auto& f : slots_) f(v);         // then Model, inside the callback
  }
};

class Model {
  std::mutex m_;
  int value_ = 0;
public:
  void on_event(int v) { std::lock_guard g(m_); value_ = v; }
  void add_listener(Subject& s) {
    std::lock_guard g(m_);               // locks Model first
    s.subscribe([](int) {});             // then Subject
  }
};

int main() {
  Subject s;
  Model model;
  s.subscribe([&](int v) { model.on_event(v); });
  std::thread a([&] { for (int i = 0; i < 1000; ++i) s.notify(i); });
  std::thread b([&] { for (int i = 0; i < 1000; ++i) model.add_listener(s); });
  a.join();
  b.join();
  std::puts("done");
}
```

This program has no data race and is not UB; it can just wait forever. Six runs of an `-O2` build all hung in our tests. Two runs of a TSan build finished once and hung once, and neither produced a lock-order inversion diagnostic (the second run set `TSAN_OPTIONS=detect_deadlocks=1`). Problems of this kind have to be avoided by design; you cannot rely on the tools we tried to find them.

Both deadlocks have the same cause: the callback is foreign code, and `Subject` doesn't know which locks it will take or whether it will come back into `Subject`. So the rule is: never call foreign code while holding your own lock. `Signal::emit` only copies the snapshot under the lock and calls callbacks without it, and neither example deadlocks any more.

!!! warning "The cost of calling outside the lock: callbacks may still run after unsubscribing returns"
    After `emit` copies the snapshot and before it calls a given callback, another thread can `disconnect` and return. The `connected` flag stops calls that haven't started, but not a call that has already passed the check and is executing. So after `disconnect()` returns, the callback may still run on another thread for a short while, and the objects it captured must not be destroyed yet. `std::stop_callback` guarantees this with blocking deregistration, at the price that deregistration may have to wait; the alternative is to have the callback itself own the objects it needs, as in the next section.

## Callbacks capturing `this`

When subscribing from a member function, the callback almost always needs to access members, so it is written `[this]`. The closure stores only a pointer (see the section on `this` and `*this` in [[topics/lambdas]]), which dangles once the object is destroyed. Making the connection object a member, so that it is destroyed with the object, is enough in a single thread:

```cpp title="this-race.cpp" ub
#include "signal.hpp"
#include <cstdio>
#include <thread>
#include <vector>

struct Widget {
  std::vector<int> seen;
  Signal<int>::Connection conn;       // declared last, destroyed first
  explicit Widget(Signal<int>& s)
    : conn(s.connect([this](int v) { seen.push_back(v); })) {}
};

int main() {
  Signal<int> sig;
  std::atomic<bool> stop{false};
  std::thread t([&] { for (int i = 0; !stop; ++i) sig.emit(i); });
  for (int i = 0; i < 10000; ++i) {
    Widget w(sig);
  }                                   // destruction concurrent with the callback on another thread
  stop = true;
  t.join();
}
```

Members are destroyed in reverse order of declaration ([[class.dtor#13]]), and `conn` is declared after `seen`, so it unsubscribes first and then `seen` is destroyed. In a single thread this order is enough; if `conn` were declared first, `seen` would be destroyed first, and a notification in between would access a destroyed `vector`.

Across threads, member order is not enough either. As the previous section said, when `conn`'s destructor returns, the notifying thread may have passed the `connected` check and be executing `seen.push_back(v)` while the main thread goes on to destroy `seen`. These are two conflicting accesses to the same object with no happens-before relation between them, which by [[intro.races#17]] is a [[g:data-race|data race]] and UB (details in [[topics/memory-model]]). TSan in our tests reported 3 `data race`s, involving `vector::emplace_back` on the notifying thread and `main` on the main thread.

The fix is to have the callback not borrow the object but temporarily share ownership of it when called:

```cpp title="weak-this.cpp" ok
#include "signal.hpp"
#include <cstdio>
#include <memory>
#include <thread>
#include <vector>

class Widget : public std::enable_shared_from_this<Widget> {
  std::vector<int> seen_;
  Signal<int>::Connection conn_;
  Widget() = default;
public:
  static std::shared_ptr<Widget> create(Signal<int>& s) {
    std::shared_ptr<Widget> w(new Widget);
    // subscribe only after construction completes and a shared_ptr owns it
    w->conn_ = s.connect([wk = w->weak_from_this()](int v) {
      if (auto self = wk.lock()) self->seen_.push_back(v);
    });
    return w;
  }
};

int main() {
  Signal<int> sig;
  std::atomic<bool> stop{false};
  std::thread t([&] { for (int i = 0; !stop; ++i) sig.emit(i); });
  for (int i = 0; i < 10000; ++i) {
    auto w = Widget::create(sig);
  }                                   // the last owner may be self in the notifying thread
  stop = true;
  t.join();
  std::puts("done");
}
```

Five consecutive runs under TSan and one under ASan plus UBSan reported nothing in our tests. While the callback's `self` exists, the `Widget` cannot start being destroyed; if `lock()` fails, the object is being or has been destroyed, and the callback does nothing.

A few details:

- Subscription happens in a static factory function, not in the constructor. While the constructor runs, no `shared_ptr` owns the object yet, so `weak_from_this()` returns an empty `weak_ptr` and `shared_from_this()` throws `bad_weak_ptr` ([[util.smartptr.enab#7]], [[util.smartptr.enab#8]]).
- Capture `weak_from_this()`, not `shared_from_this()`. Capturing a `shared_ptr` would make the `Widget` own its connection while the closure in the connection owns the `Widget`, forming a cycle; the object would never be destroyed.
- The connection `conn_` is still needed. Without it, expired callbacks stay in the `Signal` forever, each notification doing a failed `lock()`.

The other traps of `enable_shared_from_this` are in [[topics/ownership-and-smart-pointers]].

## What type to store callbacks as

When observers are a virtual base class, the subject stores `Observer*` or `weak_ptr<Observer>`. When observers are arbitrary callables, you need a type that can hold any callable, i.e. a [[patterns/type-erasure|type-erasing]] wrapper:

| Type | Owns the target | Target must be copyable | `sizeof` in our tests | Suited for |
|---|---|---|---|---|
| `std::function<R(A...)>` | yes | yes ([[func.wrap.func.con#10]]) | 32 | storing callbacks, when the subscription table must be copyable |
| `std::move_only_function<R(A...)>` {{c++23}} | yes | no | not implemented in libc++ in our tests | storing callbacks that capture move-only state such as `unique_ptr` |
| `std::copyable_function<R(A...)>` {{c++26}} | yes | yes | not implemented in libc++ in our tests | like `function`, but calls respect `const` and `noexcept` in the signature |
| `std::function_ref<R(A...)>` {{c++26}} | no | not required | not implemented in libc++ in our tests | function parameters, used synchronously during the call |

A subscription table that stores callbacks must use an owning wrapper. `std::function` has an inline buffer for small objects (the standard only recommends this, [[func.wrap.func.con#15]]). With libc++ in our tests, closures capturing up to 16 bytes don't allocate, and from 17 bytes each construction allocates once; `Signal::connect` allocates a `Slot` anyway, so this matters little.

`function_ref` stores only the target's address and an invoker function pointer ([[func.wrap.ref.class#1]], [[P0792R14]]), so storing subscriptions in it always dangles: the lambda passed at subscription is a temporary destroyed at the semicolon. Its place is the other direction, for example letting the caller synchronously visit every observer without exposing the container:

```cpp title="for-each.cpp"
class Registry {
  std::vector<std::shared_ptr<Observer>> obs_;
public:
  // f is used only during the call, never stored: take function_ref, no allocation
  void for_each(std::function_ref<void(Observer&)> f) {
    for (auto& o : obs_) f(*o);
  }
};
```

libc++ in our tests has no `function_ref` yet, so this code has not been compiled and carries no verdict. The full rules of `function_ref` and examples of dangling are in [[func.wrap.ref]].

## Costs

In our tests (Apple Silicon, Clang 23, `-O2`, single thread, no contention), we measured the time per notification per observer, with 16 observers and 2 million notifications per approach, taking the more stable figure of two rounds:

| Approach | Per observer | Extra work |
|---|---|---|
| `vector<Observer*>`, virtual call | about 1.0 ns | none |
| `vector<std::function>` | about 1.3 ns | one more indirect call |
| `vector<weak_ptr>`, `lock()` each | about 4.8 ns | one atomic increment and one decrement per observer |
| `Signal::emit` (snapshot) | about 4.8 ns | one lock and one allocation per notification, one atomic increment/decrement per slot |

These are observations from our test machine. The callback body is a single addition, so the notification mechanism itself dominates. Real callbacks are usually much heavier; when multiple threads contend for the same subject, the cache line holding the atomic counts bounces between cores, and the cost of `lock()` and snapshots rises noticeably. The safe approaches are a few nanoseconds slower, in exchange for no longer depending on callers remembering to unsubscribe.

## `std::execution`: letting structure manage lifetimes

All the approaches so far answer the same question: a callback can be invoked at any time, so how do you guarantee the objects it uses are still alive then? C++26's `std::execution` ([[P2300R10]]) takes a different direction: asynchronous work is expressed as senders, and a started child operation must complete before its parent operation completes ([[exec.async.ops#2]] bullet 2.5). Lifetimes are determined by the call structure, nested like function calls, instead of being maintained by reference counting or unsubscription.

Work whose amount is known only at run time (for example, starting a handler task for each incoming event) can be handed to an async scope ([[exec.scope]], [[P3149R11]]). The scope counts the work associated with it, and `join()` waits for all of it to finish; the scope's owner must not destroy it before `join` completes. This generalizes the blocking deregistration of `stop_callback` into a wait at scope level.

How this direction relates to the observer pattern is still being explored: one-to-many broadcasting from an event source, with subscribers coming and going, has no corresponding facility in the standard yet. libc++ in our tests has not implemented the sender part yet, so no code is given here; see [[exec.scope]] and [[exec.spawn]] for details.

## Which to choose

| Situation | Approach |
|---|---|
| Single thread, observers clearly outlive the subject | a `vector<Observer*>` or callback list is enough; document the convention |
| Single thread, observers may be destroyed first | subscription returns a connection object that unsubscribes on destruction |
| Callbacks subscribe or unsubscribe | iterate a snapshot, or mark removals and defer cleanup |
| Multiple threads | copy under the lock, call outside it; keep the objects callbacks use alive with `weak_ptr` or `weak_from_this()` |
| After unsubscribing, the callback must be guaranteed not to run (e.g. resources are about to be released) | block until in-progress callbacks finish, following the semantics of `std::stop_callback` |
| The callback is used only synchronously during one call | no observer needed; take a `function_ref` or a template parameter |

Situations that don't need the observer pattern are common too: with only one subscriber, a `std::function` member is enough; when the event source and subscribers are created and destroyed in the same scope, raw pointers plus a clear convention are simpler than `shared_ptr`.

## Questions

!!! question "1"
    In `deferred.cpp`, why does `unsubscribe` only set `alive` to `false` instead of writing `s.fn = nullptr` to free the closure directly?

<details markdown="1">
<summary>Answer</summary>

`unsubscribe` may be called from inside a callback, and the callback being unsubscribed may be that very callback. `s.fn = nullptr` would destroy the closure object held by the `std::function` while that closure's `operator()` is still executing on the stack. If it then accesses a captured variable even once (the example goes on to call `s.subscribe`, using the captured reference `s`), it accesses a member through an object whose lifetime has ended, which [[basic.life#7]] bullet 7.2 makes UB. With only a mark, the closure stays alive until `flush()` after the outermost `notify` ends, when no callback is executing any more. In `Signal`, the snapshot owning the `Slot` serves the same purpose.
</details>

!!! question "2"
    What is wrong with the line below? Why is `connect` marked `[[nodiscard]]`?
    ```cpp
    sig.connect([this](int v) { handle(v); });
    ```

<details markdown="1">
<summary>Answer</summary>

The `Connection` returned by `connect` is a temporary, destroyed at the end of the full-expression, and its destructor unsubscribes immediately. The callback is removed right after being subscribed and is never called once. This is the opposite of dangling: a logic error that reports nothing. `[[nodiscard]]` makes the compiler warn when the return value is discarded; Clang 23 gives `-Wunused-result`. The correct approach is to store the return value as a member, so that it is destroyed together with the object `this` points to.
</details>

!!! question "3"
    In `weak.cpp`, `c` in `main` goes out of scope, yet the `Counter` may be destroyed on the notifying thread. Why? What happens if `~Counter` calls `s.attach(...)`?

<details markdown="1">
<summary>Answer</summary>

The `shared_ptr` that `notify` obtains with `lock()` under the lock is also an owner. If the main thread's `c` is destroyed first, the `shared_ptr` in `alive` becomes the last owner; when it is destroyed at the end of `notify`, the strong count drops to zero, and `Counter`'s destructor runs on the notifying thread.

By then `notify` has released the lock (`alive` is destroyed outside the lock's scope), so the `attach` in `~Counter` can take the lock without deadlocking. If `alive`'s scope were inside the lock, the destructor would run with the lock held, and `attach` would lock the `std::mutex` again on the same thread, back to the UB of `self-lock.cpp`. This is one more reason to copy under the lock and call outside it: the destructor runs wherever the last `shared_ptr` is destroyed.
</details>
