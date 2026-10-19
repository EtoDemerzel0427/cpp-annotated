---
title: 原子智能指针
summary: atomic<shared_ptr<T>> 与 atomic<weak_ptr<T>>：哪些步骤在原子操作之内，CAS 和 wait 怎样比较两个智能指针，以及为什么旧的 atomic_load(shared_ptr*) 系列在 C++26 被删除。
status: draft
covers: *
papers: P0718R2
related: util.sharedptr, util.smartptr.shared, util.smartptr.weak, atomics.types.generic, atomics.wait, saferecl, diff.cpp23.depr
tags: 标准库, 原子操作, shared_ptr
updated: 2026-10-19
---

!!! tldr
    - `shared_ptr` 的引用计数是原子的，但同一个 `shared_ptr` 变量被一个线程赋值、另一个线程读取，仍然是数据竞争。`atomic<shared_ptr<T>>` 才让这个变量本身可以并发读写。
    - 原子操作包括指针的修改和 `use_count` 的递增；递减、析构和释放发生在原子操作之后，不在其中。
    - CAS 和 `wait` 比较的是等价：存储的指针相同，并且共享所有权或都为空。这比 `==` 更严格。
    - 原子智能指针只保护指针变量，不保护它指向的对象。
    - 旧的非成员 `atomic_load(const shared_ptr<T>*)` 系列在 C++20 弃用，C++26 删除。截至写作时 libc++ 还没有提供这两个偏特化。

## shared_ptr 本身不是线程安全的变量

`shared_ptr` 控制块里的引用计数是原子更新的，这常被误解为 `shared_ptr` 是线程安全的。实际上，同一个 `shared_ptr` 对象被一个线程赋值、另一个线程复制，是数据竞争（[[res.on.data.races]]）。赋值要同时改存储的指针和控制块指针两个字，还要调整新旧两个控制块的计数，这些步骤合起来不是原子的。

`atomic<shared_ptr<T>>` 和 `atomic<weak_ptr<T>>`（C++20，[[P0718R2]]）提供可以并发读写的共享指针变量。它们是 `atomic` 主模板的偏特化。`shared_ptr` 不可平凡复制，主模板对 `T` 的要求（[[atomics.types.generic]]）不适用于它们，这里单独规定。

## 原子的边界 [util.smartptr.atomic.general]

¶1 库为共享所有权的智能指针（[[util.sharedptr]]）提供 `atomic` 的偏特化。注 1：它们声明在 `<memory>` 中，不在 `<atomic>` 中。除非另有规定，所有操作的行为按 [[atomics.types.generic]]。模板形参 `T` 可以是不完整类型，这对 `struct node { atomic<shared_ptr<node>> next; };` 这样的链表节点是必需的。

¶2 规定了哪些步骤属于原子操作：

| 步骤 | 是否在原子操作之内 |
|---|---|
| 对原子智能指针本身的修改 | 是 |
| 相关的 `use_count` 递增 | 是 |
| 相关的 `use_count` 递减 | 不要求，sequenced after 原子操作 |
| 由此导致的对象析构和内存释放 | 否，sequenced after 原子更新步骤 |

注 2 补充：如果原子操作用锁实现，调整 `use_count` 时持有锁，执行析构或释放时不持有锁。

递增必须在原子操作之内。`load()` 要返回一个新的 `shared_ptr`，必须在读到指针的同时增加引用计数；否则在读到指针和增加计数之间，另一个线程可能 `store` 了新值、把旧对象的计数减到零并删除它，`load` 就返回了悬空指针。

递减可以放在外面。递减发生时旧值已经被替换，没有人能再经由这个原子指针看到它。析构函数可能很慢，甚至可能再次访问这个原子指针，也不应在锁内执行。

## 例子：一个链表（¶3）

¶3 的例 1 是一个单链表。`find` 遍历时用 `head.load()` 取得节点的共享所有权，`push_front` 用 CAS 插入：

```cpp
template<typename T> class atomic_list {
  struct node {
    T t;
    shared_ptr<node> next;
  };
  atomic<shared_ptr<node>> head;
public:
  shared_ptr<node> find(T t) const {
    auto p = head.load();
    while (p && p->t != t)
      p = p->next;
    return p;
  }
  void push_front(T t) {
    auto p = make_shared<node>();
    p->t = t;
    p->next = head;
    while (!head.compare_exchange_weak(p->next, p)) {}
  }
};
```

`find` 拿到的每个节点都由自己持有的 `shared_ptr` 保活，即使另一个线程把节点从链表上摘掉，遍历也不会访问已释放的内存。用原始指针写的无锁链表要靠 hazard pointer（[[saferecl]]）才能做到这一点。代价是每走一步都要原子地修改引用计数。

截至写作时，本机 Clang 23 的 libc++ 还没有实现 `atomic<shared_ptr<T>>`，这段代码没有经过编译验证。

## shared_ptr 偏特化 [util.smartptr.atomic.shared]

类的形状有几处与主模板不同：仅说明用的成员是 `shared_ptr<T> p`；可以从 `nullptr` 构造和赋值；`operator=` 返回 `void`，因为返回值需要再复制一次 `shared_ptr`，多一对引用计数操作；没有 `volatile` 重载。

- ¶1 默认构造值初始化 `p`。¶2 `atomic(shared_ptr<T> desired)` 的初始化不是原子操作，注 1 与主模板一样提醒了与构造竞争的陷阱。
- ¶3–¶4 `store(desired, order)` 如同 `p.swap(desired)` 原子地替换。旧值换进了形参 `desired`，在形参析构时释放，正好在原子操作之外，符合 ¶2。
- ¶5–¶6 `operator=(shared_ptr<T>)` 和 `operator=(nullptr_t)` 等价于 `store`。
- ¶7–¶10 `load(order)` 原子地返回 `p` 的副本；`operator shared_ptr<T>()` 等价于 `load()`。
- ¶11–¶12 `exchange` 如同 `p.swap(desired)`，是原子读-改-写操作，返回旧值。

### compare_exchange 与等价（¶13–¶19）

¶14 如果 `p` 与 `expected` 等价，就把 `desired` 赋给 `p`，具有 `success` 对应的同步语义；否则把 `p` 赋给 `expected`，具有 `failure` 对应的同步语义。

¶16 两个 `shared_ptr` **等价**，指它们存储相同的指针值，并且共享所有权或都为空。weak 形式可以虚假失败。

等价比 `==` 严格，`shared_ptr` 的 `==` 只比较 `get()`。两个 `shared_ptr` 可能存储相同的指针，却属于不同的控制块，例如别名构造得到的，或者错误地对同一个裸指针建了两个 `shared_ptr`。它们 `==` 但不等价，CAS 会失败。如果只比较指针，一次成功的 CAS 可能把属于另一个控制块的值当成当前值，引用计数就会错乱。

¶17 返回 `true` 时，原子更新之后不再访问 `expected`，操作是原子读-改-写；否则是原子 load，`expected` 被更新为读到的值。与写 `expected` 对应的 `use_count` 更新属于原子操作，对 `expected` 本身的写入不必属于。

¶18–¶19 只给一个内存序的重载，`failure` 由它推导：`acq_rel` 换成 `acquire`，`release` 换成 `relaxed`。

### wait 与 notify（¶20–¶26）

¶21 `wait(old, order)` 反复 `load(order)`，与 `old` 不等价时返回，否则阻塞。¶22 说明这里用的也是上面的等价定义，不按字节比较。`notify_one`、`notify_all` 照常，见 [[atomics.wait]]。

## weak_ptr 偏特化 [util.smartptr.atomic.weak]

与 `shared_ptr` 版本逐条平行：成员是 `weak_ptr<T> p`，提供 `load`、`store`、`exchange`、`compare_exchange_*`、`wait`、`notify_*`，等价的定义相同。典型用途是缓存和观察者列表：多个线程原子地读写一个可能已过期的引用，需要时再 `lock()`。

## 被删除的旧接口

C++11 的做法是对普通的 `shared_ptr` 变量调用一组非成员函数：`atomic_load(const shared_ptr<T>*)`、`atomic_store`、`atomic_exchange`、`atomic_compare_exchange_*` 及其 `_explicit` 版本。C++20 弃用了它们 {{deprecated}}，C++26 删除 {{removed:C++26}}。

[[diff.cpp23.depr]] 给出的理由是：旧做法不受类型系统保护，与不使用这套 API 的代码交互时，可能悄无声息地产生未定义行为。只要有一处代码忘了用 `atomic_load`、直接复制了那个变量，就是数据竞争，编译器不会提示。`atomic<shared_ptr<T>>` 根本不提供非原子的访问方式。

## 实现视角

!!! impl "libc++ 的现状（Clang 23）"
    `__cpp_lib_atomic_shared_ptr` 未定义。写 `std::atomic<std::shared_ptr<int>>` 会落到主模板，被 `static_assert` 拒绝：`std::atomic<T> requires that 'T' be a trivially copyable type`。

    另一方面，已在 C++26 删除的 `std::atomic_load(const shared_ptr<T>*)` 等函数在 `-std=c++2c` 下仍然可用，也没有弃用警告。

!!! impl "常见实现策略"
    `shared_ptr` 由两个指针组成，原子地操作它需要 16 字节 CAS 或一把锁。libstdc++ 把一个自旋锁位放在控制块指针的最低位里（控制块按指针对齐，最低位空闲）：`load` 先锁住这一位，复制指针并增加引用计数，再解锁。所以它通常不是无锁的，`is_always_lock_free` 为 `false`，但临界区很短。

## 常见误解

!!! pitfall "原子智能指针保护指向的对象"
    两个线程同时执行 `ap.load()->value = 42;`，对 `value` 仍然是数据竞争。原子智能指针保证的是读写这个指针变量是安全的，以及拿到的对象不会在使用中被释放。对象本身的并发访问需要另外同步，或者把对象当作不可变的：每次修改都 `make_shared` 一个新对象再 `store`。

!!! pitfall "旧对象在执行 store 的线程里析构"
    `store` 或 `exchange` 替换掉旧值后，旧对象在最后一个持有者释放时才析构。那可能是执行 `store` 的线程，也可能是某个刚 `load` 过、稍后才释放的读者线程。析构函数不要依赖自己在哪个线程上运行。
