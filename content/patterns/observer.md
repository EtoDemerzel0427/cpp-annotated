---
title: 观察者与回调的生命周期
summary: 主题对象通知一组观察者，难点不在通知本身，而在双方谁先销毁：裸指针列表、析构时退订、weak_ptr、RAII 连接对象各自能防住什么，通知过程中的重入和持锁回调怎样出错，以及回调里捕获 this 的悬垂。
status: draft
order: 65
since: c++11
papers: P0792R14, P2300R10, P3149R11
related: util.smartptr.weak, util.smartptr.enab, func.wrap.func, func.wrap.ref, thread.stoptoken, exec.scope, intro.races, topics/ownership-and-smart-pointers, topics/lambdas, topics/memory-model, topics/dangling-references, patterns/raii, patterns/type-erasure
tags: 设计模式, 观察者, 回调, 生命周期, weak_ptr, 并发, 专题
updated: 2026-10-19
---

!!! tldr
    - 主题对象保存的观察者指针不拥有对象。观察者先销毁、又没有退订，下一次通知就是通过悬垂指针调用成员函数，属于 UB，ASan 报告 heap-use-after-free。
    - 在观察者析构函数里退订只在单线程下可靠。多线程时，基类析构函数运行之前派生部分已经销毁，另一个线程的通知会调用到半毁的对象。
    - 用 `weak_ptr` 保存观察者、通知时 `lock()`，或者让订阅返回一个析构时自动退订的连接对象，把谁先死的问题交给类型系统；`std::stop_callback` 就是标准库里的这种连接对象。
    - 回调里订阅或退订会在遍历中修改容器，使迭代器失效。办法是遍历一份快照，或者标记删除、延迟到最外层通知结束再整理。持锁调用回调会死锁，应该在锁内复制、锁外调用。
    - 回调里捕获 `this` 时，对象的寿命必须覆盖所有可能的调用；跨线程时用 `weak_from_this()` 捕获，回调执行时先 `lock()`。

## 一个会崩溃的观察者列表

**观察者模式**（observer）里，一个主题对象（subject）保存一组观察者，状态变化时逐个通知它们。最直接的 C++ 写法是保存裸指针：

```cpp run title="naive.cpp" ub
#include <algorithm>
#include <cstdio>
#include <vector>

struct Observer {
  virtual void on_event(int) = 0;
  virtual ~Observer() = default;
};

class Subject {
  std::vector<Observer*> obs_;   // 不拥有，也不知道它们何时销毁
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
  delete b;          // 忘了 detach
  s.notify(20);      // UB：通过悬垂指针做虚调用
}
```

`delete b` 结束了 `*b` 的生命周期，`obs_` 里那个指针却还在。第二次 `notify` 通过它调用非静态成员函数，[[basic.life#7]] 第 7.2 项规定这是 UB。本机 Clang 23 用 `-fsanitize=address` 运行，报告 `heap-use-after-free`，位置在 `Subject::notify`，读取的 8 字节就是对象开头的 vptr（虚函数表指针，见 [[toolchain/object-layout-and-vtables]]）。

问题的根源是所有权没有表达出来。`Subject` 借用观察者，借用者却活得比被借用的对象长。本页其余部分都在回答同一个问题：怎样让 `Subject` 在调用之前知道观察者还活着，并且在调用期间一直活着。所有权的一般讨论见 [[topics/ownership-and-smart-pointers]]。

## 在析构函数里退订

第一个想法是让观察者在析构时自动把自己摘掉。把 `attach`、`detach` 放进基类的构造函数和析构函数，派生类就不会忘记：

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
  virtual ~Observer();            // 在析构函数里退订
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
  std::vector<int> seen;          // 派生类的成员
  using Observer::Observer;
  void on_event(int v) override { seen.push_back(v); }
};

int main() {
  Subject s;
  std::atomic<bool> stop{false};
  std::thread t([&] { for (int i = 0; !stop; ++i) s.notify(i); });
  for (int i = 0; i < 1000; ++i) {
    Counter c(s);                 // 构造时订阅，析构时退订
  }
  stop = true;
  t.join();
}
```

单线程程序里这个设计是可靠的：`~Counter` 运行期间没有别人会调用 `notify`。多线程时，即使 `Subject` 的每个操作都加了锁，它仍然出错，因为退订发生得太晚。

销毁一个 `Counter` 的顺序是：先执行 `~Counter` 的函数体，再销毁成员 `seen`，最后调用基类的 `~Observer`（[[class.dtor#13]]）。对象的生命周期在 `~Counter` 开始时就已经结束（[[basic.life#2]] 第 2.4 项），而它从列表里消失要等到 `~Observer` 拿到锁。在这段时间里，另一个线程的 `notify` 仍然能通过列表里的指针调用 `on_event`。

本机 Clang 23 用 `-fsanitize=thread` 运行，TSan 先报告 `data race on vptr (ctor/dtor vs virtual call)`，随后程序以 `libc++abi: Pure virtual function called!` 中止。原因是析构过程中实现把 vptr 依次改成各个基类的虚表，进入 `~Observer` 时虚表已经是 `Observer` 的，`on_event` 在那里是纯虚函数。构造函数里 `attach(this)` 有对称的问题：基类构造完、派生类还没构造时，对象已经能被别的线程看到。

!!! pitfall "析构函数里退订不等于线程安全"
    析构函数里退订解决的是忘记退订，没有解决并发。跨线程时，观察者必须在自己开始销毁之前就保证不会再被调用，这要么靠所有权（下一节的 `weak_ptr`），要么靠退订操作阻塞到正在进行的回调结束（后文的 `stop_callback`）。

## `weak_ptr`：通知时先确认对象活着

如果观察者由 `shared_ptr` 拥有，主题对象就可以保存 `weak_ptr`。`weak_ptr` 不让对象活着，但它的 `lock()` 原子地检查对象是否存活并取得一个 `shared_ptr`（[[util.smartptr.weak.obs#3]]）。拿到的 `shared_ptr` 在回调期间保证对象不会被销毁：

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
        auto p = w.lock();             // 原子地检查并取得所有权
        if (!p) return true;           // 已销毁：顺手清理
        alive.push_back(std::move(p));
        return false;
      });
    }
    for (auto& p : alive) p->on_event(v);   // 不持锁调用；p 保证对象活着
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
  }                                    // 最后一个所有者可能是通知线程里的 p
  stop = true;
  t.join();
  std::puts("done");
}
```

本机 TSan 连续运行 5 次、ASan 加 UBSan 运行 1 次都没有报告。和上一节相比，观察者不再需要主动退订：它被销毁之后，`lock()` 返回空指针，`notify` 顺手把它清理掉。

这个设计有三个后果需要知道：

- 观察者必须由 `shared_ptr` 拥有。栈上的对象、`unique_ptr` 拥有的对象都不能这样注册。
- `notify` 里的 `p` 可能是最后一个所有者。`main` 中的 `c` 先离开作用域时，`Counter` 会在通知线程上、在 `notify` 返回之前被析构。析构函数里如果要拿锁或者访问线程局部状态，要考虑到这一点。
- 过期的 `weak_ptr` 不释放控制块。用 `make_shared` 创建的观察者，对象和控制块在同一块内存里，在 `weak_ptr` 被清理之前整块内存都不会释放。

用 `std::set` 加 `std::owner_less` 保存 `weak_ptr` 的写法，以及先 `expired()` 再 `lock()` 为什么是竞态，见 [[topics/ownership-and-smart-pointers]] 中的 `weak_ptr` 一节。

## 连接对象：析构时退订

`weak_ptr` 方案要求观察者是一个由 `shared_ptr` 拥有的对象。很多时候观察者只是一个回调函数，订阅方想要的是：只要我持有某个东西，回调就有效；这个东西一销毁，回调就不再被调用。这个东西叫做**连接对象**（connection），它是一个 RAII 句柄：由对象的析构函数负责释放它获得的资源，这里的资源就是那份订阅（见 [[patterns/raii|RAII 与作用域守卫]]）。

连接对象本身也要处理生命周期：它可能比主题对象活得长。下面的 `Signal` 把订阅列表放在一个由 `shared_ptr` 拥有的 `State` 里，连接对象只持有 `weak_ptr`，主题对象先销毁时退订就什么也不做：

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
    ~Connection() { disconnect(); }   // 离开作用域就退订

    void disconnect() {
      auto s = slot_.lock();
      if (!s) return;
      s->connected = false;           // 本轮通知中还没调用的，跳过
      if (auto st = st_.lock()) {     // Signal 可能已经先销毁了
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
      snapshot = st_->slots;          // 持锁只做复制
    }
    for (auto& s : snapshot)          // 不持锁调用
      if (s->connected) s->fn(args...);
  }
};
```

`Connection` 只能移动，不能复制：两个句柄退订同一个回调没有意义。它的移动构造函数是预置的，被移走的 `weak_ptr` 变成空的，移后对象析构时 `disconnect()` 直接返回。`connect` 标了 `[[nodiscard]]`，因为丢弃返回值会让临时的 `Connection` 在分号处析构，回调刚订阅就被退订；本机 Clang 23 对 `s.connect(f);` 给出 `-Wunused-result` 警告。

`emit` 的写法是后面两节的结论，这里先记住它的形状：持锁复制一份 `shared_ptr<Slot>` 快照，解锁之后逐个调用，调用前检查 `connected`。

!!! note "标准库里的连接对象"
    `std::stop_callback`（[[thread.stoptoken]]）就是这样一个句柄：构造时把回调登记到停止状态上，析构时注销（[[stopcallback.cons#3]]）。标准对注销还多要求了一条：如果回调正在另一个线程上执行，注销要阻塞到它返回；如果正在当前线程上执行（回调里销毁了自己的 `stop_callback`），则不阻塞（[[stoptoken.concepts#3]] 第 3.3.3、3.3.4 项）。上面的 `Signal` 没有提供这一保证，后文会讲到它的后果。

## 重入：通知过程中订阅和退订

回调里做的事情常常会反过来修改主题对象：收到一次事件就退订自己，或者在事件里订阅新的回调。这叫**重入**（reentrancy）。如果 `notify` 直接遍历容器，重入就是在遍历过程中修改容器：

```cpp run title="reentrant.cpp" ub
#include <cstdio>
#include <functional>
#include <vector>

class Subject {
  std::vector<std::function<void(int)>> slots_;
public:
  void subscribe(std::function<void(int)> f) { slots_.push_back(std::move(f)); }
  void notify(int v) {
    for (auto& f : slots_) f(v);    // 迭代期间 slots_ 不能变
  }
};

int main() {
  Subject s;
  s.subscribe([&](int v) {
    std::printf("first %d\n", v);
    s.subscribe([](int) {});        // 在通知中订阅：push_back 可能重新分配
  });
  s.subscribe([](int v) { std::printf("second %d\n", v); });
  s.notify(1);                      // UB
}
```

`push_back` 使 `size()` 超过 `capacity()` 时会重新分配，所有指向元素的引用和迭代器都失效（[[vector.modifiers#2]]，[[g:iterator-invalidation|迭代器失效]]）。范围 `for` 手里的迭代器和正在执行的 `f` 都指向旧的缓冲区。本机 ASan 报告 `heap-use-after-free`，位置在 `std::function::operator()` 里，被访问的是已经释放的 64 字节区域，正好是两个 32 字节的 `std::function`。

退订也一样。`erase` 使被删位置及其后的迭代器失效（[[vector.modifiers#4]]），删掉的如果是正在执行的那个 `std::function`，它保存的闭包对象在自己的 `operator()` 还没返回时就被销毁了，之后再访问捕获的变量就是访问已经结束生命周期的对象。

有两种常见的修法。

### 遍历快照

`Signal::emit` 在锁内复制 `slots` 得到快照，然后遍历快照。回调里 `connect` 修改的是 `State::slots`，不影响正在遍历的快照；新订阅的回调从下一次 `emit` 开始生效。

快照里存的是 `shared_ptr<Slot>`，不是 `std::function` 的副本。这样做有两个好处：复制的代价是每个槽一次原子加减，不会复制闭包捕获的状态；回调退订自己时，`Slot` 被快照拥有，正在执行的 `fn` 不会被销毁。`connected` 标志让本轮中已经被退订、但还在快照里的回调被跳过：

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
    self.reset();                     // 在自己的回调里退订
    added = sig.connect([](int v) { std::printf("added %d\n", v); });
  });
  sig.emit(1);                        // keep 1, once 1；added 下一轮才生效
  sig.emit(2);                        // keep 2, added 2

  Signal<int>::Connection late;
  {
    Signal<int> tmp;
    late = tmp.connect([](int) {});
  }                                   // Signal 先销毁
}                                     // late 析构：weak_ptr 已过期，什么也不做
```

这段程序要和上面的 `signal.hpp` 放在一起编译。本机 ASan 加 UBSan 运行，输出 `keep 1`、`once 1`、`keep 2`、`added 2`，没有报告。

### 标记删除，延迟整理

快照的代价是每次通知都要分配一块内存。单线程、通知频繁的场合，可以改为让容器在通知期间保持不变：退订只打标记，订阅先放进待加入列表，等最外层的 `notify` 结束时再统一整理。

```cpp run title="deferred.cpp" ok
#include <cstdio>
#include <functional>
#include <vector>

class Subject {
  struct Slot { int id; std::function<void(int)> fn; bool alive = true; };
  std::vector<Slot> slots_, pending_;
  int depth_ = 0, next_id_ = 0;

  void flush() {                       // 只在最外层通知结束时整理
    std::erase_if(slots_, [](const Slot& s) { return !s.alive; });
    for (auto& s : pending_) slots_.push_back(std::move(s));
    pending_.clear();
  }
public:
  int subscribe(std::function<void(int)> f) {
    auto& v = depth_ ? pending_ : slots_;   // 通知中：先放进待加入列表
    v.push_back({next_id_, std::move(f)});
    return next_id_++;
  }
  void unsubscribe(int id) {
    for (auto* v : {&slots_, &pending_})
      for (auto& s : *v)
        if (s.id == id) s.alive = false;   // 只做标记，不销毁 fn
    if (!depth_) flush();
  }
  void notify(int v) {
    ++depth_;
    struct Guard {                     // 回调抛异常也要恢复 depth_
      Subject& s;
      ~Guard() { if (--s.depth_ == 0) s.flush(); }
    } g{*this};
    for (std::size_t i = 0; i < slots_.size(); ++i)   // 通知中 slots_ 不会增删
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

本机输出和快照版本相同，ASan 加 UBSan 没有报告。`depth_` 计数让嵌套的 `notify`（回调里又触发通知）不会提前整理。`Guard` 保证回调抛出异常时计数照样恢复，否则之后所有的订阅都会永远留在 `pending_` 里。

| | 遍历快照 | 标记删除、延迟整理 |
|---|---|---|
| 每次通知的额外开销 | 一次分配，每个槽一次原子加减 | 无 |
| 通知中订阅 | 下一轮生效 | 下一轮生效 |
| 通知中退订 | 本轮后续跳过（靠 `connected` 标志） | 本轮后续跳过 |
| 多线程 | 可以，锁只保护复制 | 不行，`depth_` 和两个容器都没有同步 |
| 正在执行的回调退订自己 | 安全，快照拥有 `Slot` | 安全，`fn` 在整理之前不销毁 |

## 持锁回调与死锁

多线程的主题对象需要一把锁保护订阅列表。最省事的写法是 `notify` 整个持锁，这样做有两种死法。

第一种是同一线程重入。回调里调用 `subscribe`，同一个线程第二次锁同一个 `std::mutex`：

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
    std::lock_guard g(m_);          // 持锁回调
    for (auto& f : slots_) f(v);
  }
};

int main() {
  Subject s;
  s.subscribe([&](int) { s.subscribe([](int) {}); });   // 回调里再订阅
  s.notify(1);                      // UB：同一线程再次锁 std::mutex
}
```

`std::mutex::lock()` 的前提条件是调用线程没有持有这把锁（[[thread.mutex.requirements.mutex.general#6]]），违反库函数的前提条件是 UB（[[structure.specifications#3]] 第 3.4 项）。本机不论是否开 TSan，程序都直接挂起。换成 `std::recursive_mutex` 能让它不挂起，但锁不住的问题就变成了上一节的迭代器失效。

第二种是两个线程以相反的顺序拿两把锁。通知线程持有 `Subject` 的锁，回调里去拿 `Model` 的锁；另一个线程持有 `Model` 的锁，去 `Subject` 上订阅：

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
    std::lock_guard g(m_);               // 先锁 Subject
    for (auto& f : slots_) f(v);         // 回调里再锁 Model
  }
};

class Model {
  std::mutex m_;
  int value_ = 0;
public:
  void on_event(int v) { std::lock_guard g(m_); value_ = v; }
  void add_listener(Subject& s) {
    std::lock_guard g(m_);               // 先锁 Model
    s.subscribe([](int) {});             // 再锁 Subject
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

这个程序没有数据竞争，也不是 UB，它只是可能永远等下去。本机 `-O2` 构建运行 6 次，6 次都挂起。TSan 构建运行两次，一次跑完、一次挂起，都没有给出锁顺序反转的诊断（第二次设置了 `TSAN_OPTIONS=detect_deadlocks=1`）。这类问题要靠设计避免，不能指望本机的工具发现。

两种死锁的共同原因是：回调是外部代码，`Subject` 不知道它会拿哪些锁、会不会回到自己身上。所以规则是不要在持有自己的锁时调用外部代码。`Signal::emit` 在锁内只复制快照，调用回调时不持锁，两个例子都不再死锁。

!!! warning "锁外调用的代价：退订返回后回调仍可能在运行"
    `emit` 复制快照之后、调用某个回调之前，另一个线程可以 `disconnect` 并返回。`connected` 标志能拦住还没开始的调用，拦不住已经通过检查、正在执行的调用。所以 `disconnect()` 返回之后，回调仍可能在别的线程上运行一小段时间，它捕获的对象此时不能销毁。`std::stop_callback` 用阻塞的注销来保证这一点，代价是注销可能要等；另一个办法是让回调本身持有它需要的对象，见下一节。

## 捕获 `this` 的回调

成员函数里订阅时，回调几乎总是要访问成员，于是写成 `[this]`。闭包里存的只是一个指针（[[topics/lambdas]] 中 `this` 与 `*this` 一节），对象销毁后它就悬垂了。把连接对象作为成员，让它随对象一起析构，在单线程里足够：

```cpp title="this-race.cpp" ub
#include "signal.hpp"
#include <cstdio>
#include <thread>
#include <vector>

struct Widget {
  std::vector<int> seen;
  Signal<int>::Connection conn;       // 最后声明，最先析构
  explicit Widget(Signal<int>& s)
    : conn(s.connect([this](int v) { seen.push_back(v); })) {}
};

int main() {
  Signal<int> sig;
  std::atomic<bool> stop{false};
  std::thread t([&] { for (int i = 0; !stop; ++i) sig.emit(i); });
  for (int i = 0; i < 10000; ++i) {
    Widget w(sig);
  }                                   // 析构与另一线程中的回调并发
  stop = true;
  t.join();
}
```

成员按声明的逆序销毁（[[class.dtor#13]]），`conn` 声明在 `seen` 之后，所以先退订、再销毁 `seen`。单线程里这个顺序就够了；如果 `conn` 声明在前面，`seen` 先被销毁，中间那段时间里的通知会访问已经销毁的 `vector`。

跨线程时，成员顺序也不够。正如上一节所说，`conn` 析构返回时，通知线程可能已经通过了 `connected` 检查，正在执行 `seen.push_back(v)`，而主线程接着销毁 `seen`。这是对同一个对象的两个冲突访问，彼此之间没有 happens-before 关系，按 [[intro.races#17]] 构成[[g:data-race|数据竞争]]，是 UB（细节见 [[topics/memory-model]]）。本机 TSan 报告了 3 处 `data race`，涉及的位置是通知线程里的 `vector::emplace_back` 和主线程的 `main`。

修法是让回调不借用对象，而是在调用时临时共享对象的所有权：

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
    // 构造完成、已被 shared_ptr 拥有之后再订阅
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
  }                                   // 最后一个所有者可能是通知线程里的 self
  stop = true;
  t.join();
  std::puts("done");
}
```

本机 TSan 连续运行 5 次、ASan 加 UBSan 运行 1 次都没有报告。回调里的 `self` 存在期间，`Widget` 不会开始析构；`lock()` 失败说明对象已经在销毁或者已经销毁，回调什么也不做。

这里有几个细节：

- 订阅放在静态工厂函数里，而不是构造函数里。构造函数运行时对象还没被 `shared_ptr` 拥有，`weak_from_this()` 返回空的 `weak_ptr`，`shared_from_this()` 抛出 `bad_weak_ptr`（[[util.smartptr.enab#7]]、[[util.smartptr.enab#8]]）。
- 捕获 `weak_from_this()` 而不是 `shared_from_this()`。捕获 `shared_ptr` 会让 `Widget` 拥有自己的连接、连接里的闭包又拥有 `Widget`，形成环，对象永远不会销毁。
- 连接 `conn_` 仍然需要。没有它，过期的回调会一直留在 `Signal` 里，每次通知都做一次失败的 `lock()`。

`enable_shared_from_this` 的其余陷阱见 [[topics/ownership-and-smart-pointers]]。

## 回调存成什么类型

观察者是一个虚基类时，主题对象存 `Observer*` 或 `weak_ptr<Observer>`。观察者是任意可调用对象时，就需要一个能装下任意可调用对象的类型，也就是[[patterns/type-erasure|类型擦除]]的包装器：

| 类型 | 拥有目标 | 目标须可复制 | 本机 `sizeof` | 适合 |
|---|---|---|---|---|
| `std::function<R(A...)>` | 是 | 是（[[func.wrap.func.con#10]]） | 32 | 存储回调，需要复制订阅表时 |
| `std::move_only_function<R(A...)>` {{c++23}} | 是 | 否 | 本机 libc++ 未实现 | 存储捕获了 `unique_ptr` 等只能移动的状态的回调 |
| `std::copyable_function<R(A...)>` {{c++26}} | 是 | 是 | 本机 libc++ 未实现 | 同 `function`，但调用遵守签名里的 `const`、`noexcept` |
| `std::function_ref<R(A...)>` {{c++26}} | 否 | 不要求 | 本机 libc++ 未实现 | 函数参数，调用期间同步使用 |

订阅表要保存回调，必须用拥有目标的包装器。`std::function` 对小对象有内联缓冲区（标准只作为建议，[[func.wrap.func.con#15]]）。本机 libc++ 上，捕获 16 字节以内的闭包不分配内存，17 字节起每次构造分配一次；`Signal::connect` 本来就要分配 `Slot`，这一点影响不大。

`function_ref` 只保存目标的地址和一个调用函数指针（[[func.wrap.ref.class#1]]，[[P0792R14]]），用它保存订阅一定会悬垂：订阅时传入的 lambda 是临时对象，分号处就销毁了。它的位置在另一个方向，比如让调用方同步地遍历所有观察者，而不暴露容器：

```cpp title="for-each.cpp"
class Registry {
  std::vector<std::shared_ptr<Observer>> obs_;
public:
  // 只在调用期间使用 f，不保存：参数用 function_ref，不分配
  void for_each(std::function_ref<void(Observer&)> f) {
    for (auto& o : obs_) f(*o);
  }
};
```

本机 libc++ 还没有 `function_ref`，这段代码没有编译过，不标判定。`function_ref` 的完整规则和悬垂的例子见 [[func.wrap.ref]]。

## 代价

本机（Apple Silicon，Clang 23，`-O2`，单线程，无竞争）测量每次通知分摊到每个观察者上的时间，16 个观察者，每种写法 200 万次通知，取两轮中较稳定的数字：

| 写法 | 每个观察者 | 额外的工作 |
|---|---|---|
| `vector<Observer*>`，虚调用 | 约 1.0 ns | 无 |
| `vector<std::function>` | 约 1.3 ns | 多一次间接调用 |
| `vector<weak_ptr>`，逐个 `lock()` | 约 4.8 ns | 每个观察者一次原子加、一次原子减 |
| `Signal::emit`（快照） | 约 4.8 ns | 每次通知一次加锁、一次分配，每个槽一次原子加减 |

这些是本机的观察值，回调体只是一次加法，所以通知机制本身的开销占了大头。真实的回调通常比这重得多；多线程竞争同一个主题对象时，原子计数所在的缓存行会在核之间来回传递，`lock()` 和快照的代价会明显上升。安全的写法慢了几纳秒，换来的是不再依赖调用方记得退订。

## `std::execution`：让结构管理生命周期

前面所有的办法都在回答同一个问题：回调可能在任何时候被调用，怎样保证它用到的对象那时还活着。C++26 的 `std::execution`（[[P2300R10]]）换了一个方向：异步工作表示为发送器（sender），被启动的子操作必须在父操作完成之前完成（[[exec.async.ops#2]] 第 2.5 项）。生命周期由调用结构决定，像函数调用一样嵌套，而不是靠引用计数或退订来维持。

运行时才知道数量的工作（比如每来一个事件就启动一个处理任务）可以交给异步作用域（[[exec.scope]]，[[P3149R11]]）。作用域给关联到它的工作计数，`join()` 等它们全部结束；作用域的所有者在 `join` 完成之前不能销毁它。这相当于把 `stop_callback` 那种阻塞的注销推广成了作用域级别的等待。

这个方向和观察者模式的关系还在探索之中：事件源一对多地广播、订阅者来去不定，这些需求在标准里还没有对应的设施。本机 libc++ 也还没有实现发送器部分，这里不给代码，细节见 [[exec.scope]] 和 [[exec.spawn]]。

## 选哪一种

| 情形 | 做法 |
|---|---|
| 单线程，观察者的寿命明确长于主题对象 | `vector<Observer*>` 或回调列表即可，在文档里写清楚约定 |
| 单线程，观察者可能先销毁 | 订阅返回连接对象，析构时退订 |
| 回调里会订阅、退订 | 遍历快照，或标记删除、延迟整理 |
| 多线程 | 锁内复制、锁外调用；回调访问的对象用 `weak_ptr` 或 `weak_from_this()` 保活 |
| 退订后必须保证回调不再运行（例如马上要释放资源） | 阻塞到正在进行的回调结束，参考 `std::stop_callback` 的语义 |
| 回调只在一次调用期间同步使用 | 不需要观察者，参数用 `function_ref` 或模板参数 |

不需要观察者模式的情形也很常见：只有一个订阅者时，一个 `std::function` 成员就够了；事件源和订阅者在同一个作用域里创建和销毁时，裸指针加清楚的约定比 `shared_ptr` 更简单。

## 思考题

!!! question "1"
    `deferred.cpp` 里，`unsubscribe` 为什么只把 `alive` 设为 `false`，而不直接写 `s.fn = nullptr` 释放闭包？

<details markdown="1">
<summary>答案</summary>

`unsubscribe` 可能在回调内部被调用，被退订的也可能正是这个回调自己。`s.fn = nullptr` 会销毁 `std::function` 保存的闭包对象，而这个闭包的 `operator()` 此刻还在栈上执行。之后它只要再访问一次捕获的变量（例子里接着调用了 `s.subscribe`，用到捕获的引用 `s`），就是通过已经结束生命周期的对象访问成员，按 [[basic.life#7]] 第 7.2 项是 UB。只打标记，闭包就一直活到最外层 `notify` 结束后的 `flush()`，那时已经没有回调在执行。`Signal` 里 `Slot` 由快照拥有，起的是同样的作用。
</details>

!!! question "2"
    下面这行代码有什么问题？为什么 `connect` 要标 `[[nodiscard]]`？
    ```cpp
    sig.connect([this](int v) { handle(v); });
    ```

<details markdown="1">
<summary>答案</summary>

`connect` 返回的 `Connection` 是一个临时对象，在完整表达式结束时析构，析构函数立即退订。回调刚订阅就被移除，一次也不会被调用。这和悬垂正好相反，是一个不报错的逻辑错误。`[[nodiscard]]` 让编译器在返回值被丢弃时警告，本机 Clang 23 给出 `-Wunused-result`。正确的写法是把返回值保存为成员，让它和 `this` 指向的对象一起销毁。
</details>

!!! question "3"
    `weak.cpp` 里，`main` 中的 `c` 离开作用域，`Counter` 却可能在通知线程上被析构。为什么？如果 `~Counter` 里调用 `s.attach(...)`，会发生什么？

<details markdown="1">
<summary>答案</summary>

`notify` 在锁内 `lock()` 得到的 `shared_ptr` 也是所有者。如果主线程的 `c` 先销毁，`alive` 里的那个 `shared_ptr` 就成了最后一个所有者，它在 `notify` 末尾销毁时把强计数减到零，`Counter` 的析构函数就在通知线程上运行。

此时 `notify` 已经释放了锁（`alive` 在锁的作用域之外销毁），所以 `~Counter` 里调用 `attach` 能拿到锁，不会死锁。如果把 `alive` 的作用域写进锁里，析构函数就会在持锁状态下运行，`attach` 会同一线程再次锁 `std::mutex`，回到 `self-lock.cpp` 的 UB。这也是锁内只复制、锁外调用的另一个理由：最后一个 `shared_ptr` 在哪里销毁，析构函数就在哪里运行。
</details>
