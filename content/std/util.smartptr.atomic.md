---
title: 原子智能指针
summary: atomic<shared_ptr<T>> 与 atomic<weak_ptr<T>>——哪些部分是原子的（指针与 use_count 递增）、哪些不是（递减、析构与释放）、"等价"的定义与 CAS、wait 的比较方式，以及 C++26 删除旧的 atomic_load(shared_ptr*) 系列；libc++ 尚未实现
status: draft
covers: *
papers: P0718R2
related: util.sharedptr, util.smartptr.shared, util.smartptr.weak, atomics.types.generic, atomics.wait, saferecl, diff.cpp23.depr
tags: 标准库, 原子操作, shared_ptr
updated: 2026-10-18
---

`shared_ptr` 的控制块引用计数是原子的，这常被误解为"`shared_ptr` 是线程安全的"。实际上，**同一个** `shared_ptr` 对象被一个线程赋值、另一个线程读取，是数据竞争（[[res.on.data.races]]）：赋值要同时改指针和控制块指针两个字，还要调整两个控制块的计数，这些合起来不是原子的。

`atomic<shared_ptr<T>>` 与 `atomic<weak_ptr<T>>`（C++20，[[P0718R2]]）提供真正原子的"共享指针变量"。它们是 `atomic` 主模板的偏特化，但 `shared_ptr` 不可平凡复制，所以主模板的 [[atomics.types.generic]] ¶1 不适用——这里单独规定。注 1：它们声明在 `<memory>` 里，不是 `<atomic>`。

## 总述（[util.smartptr.atomic.general]）

¶1 库为共享所有权的智能指针（[[util.sharedptr]]）提供 `atomic` 的偏特化。除非另有规定，所有操作的行为按 [[atomics.types.generic]]。**模板形参 `T` 可以是不完整类型**——这对链表节点 `struct node { atomic<shared_ptr<node>> next; };` 是必需的。

¶2 精确规定了"原子"的边界：

| 操作的组成部分 | 是否属于原子操作 |
|---|---|
| 对原子智能指针本身的修改 | **是** |
| 相关的 `use_count` **递增** | **是** |
| 相关的 `use_count` **递减** | 否，sequenced after 原子操作 |
| 由此导致的对象析构与内存释放 | 否，sequenced after 原子更新步骤 |

注 2：若原子操作用锁实现，那么实现获取的锁在调整 `use_count` 时**持有**，在执行析构或释放时**不持有**。

为什么递增必须在内、递减可以在外？考虑 `load()`：它要返回一个新的 `shared_ptr`，必须在**读到指针的同时**增加引用计数——否则在"读到指针"与"增加计数"之间，另一个线程可能 `store` 了新值、把旧对象的计数减到零并删除了它，`load` 就会返回一个悬空指针。而递减发生在旧值已经被替换之后，此时没有人能再通过原子指针看到它，所以可以在原子操作之外慢慢做，析构函数（可能很慢、甚至可能再去访问这个原子指针）也不应在锁内执行。

¶3 例 1：一个无锁风格的单链表，`find` 遍历时用 `head.load()` 获得节点的共享所有权，`push_front` 用 CAS 插入：

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

`find` 拿到的每个节点都被自己持有的 `shared_ptr` 保活，所以即使另一个线程把节点从链表上摘掉，遍历也不会访问已释放的内存——这正是普通原始指针无锁链表需要 hazard pointer（[[saferecl]]）才能解决的问题。代价是每一步都要原子地修改引用计数。

## shared_ptr 偏特化（[util.smartptr.atomic.shared]）

类定义的要点：仅说明用成员 `shared_ptr<T> p`；构造函数 `constexpr` 且 `noexcept`；可以从 `nullptr` 构造和赋值；`operator=` 返回 `void`（不像主模板返回值——返回值需要再复制一次 `shared_ptr`，徒增引用计数操作）。**没有** `volatile` 重载。

- ¶1 默认构造：值初始化 `p`。¶2 `atomic(shared_ptr<T> desired)`：初始化不是原子操作；注 1 与主模板相同的"与构造竞争"陷阱。
- ¶3–¶4 `store(desired, order)`：如同 `p.swap(desired)` 原子地替换。注意：旧值随后在 `desired`（函数形参）析构时被释放——在原子操作之外，符合 ¶2。
- ¶5–¶6 `operator=(shared_ptr<T>)`、`operator=(nullptr_t)`：等价于 `store`。
- ¶7–¶9 `load(order)`：原子地返回 `p` 的副本。¶10 `operator shared_ptr<T>()`。
- ¶11–¶12 `exchange`：如同 `p.swap(desired)`，原子 RMW；返回旧值。

### compare_exchange 与"等价"（¶13–¶19）

¶14 若 `p` 与 `expected` **等价**，就把 `desired` 赋给 `p`，具有对应 `success` 的同步语义；否则把 `p` 赋给 `expected`，具有对应 `failure` 的同步语义。

¶16 *Remarks*：两个 `shared_ptr` **等价**，当且仅当它们**存储相同的指针值**，并且**共享所有权或都为空**。weak 形式可以虚假失败。

"等价"比 `==` 严格：`shared_ptr` 的 `==` 只比较存储的指针（`get()`）。两个 `shared_ptr` 可能存相同的指针却属于不同的控制块（别名构造，或者对同一个裸指针错误地建了两个 `shared_ptr`），它们 `==` 但不等价，CAS 会失败。这样定义是因为 CAS 必须同时检查"指针"和"控制块"两个字，否则成功的 CAS 可能把一个属于不同控制块的值错当成当前值，导致引用计数错乱。

¶17 返回 `true` 时，`expected` **在原子更新之后不再被访问**，操作是原子 RMW；否则是原子 load，`expected` 被更新为读到的值。与 `expected` 写入对应的 `use_count` 更新**是**原子操作的一部分，但对 `expected` 本身的写入**不必是**。

¶18–¶19 单内存序重载：`fail_order` 由 `order` 推导，`acq_rel` → `acquire`，`release` → `relaxed`。

### wait 与 notify（¶20–¶26）

`wait(old, order)`：反复 `load(order)` 并与 `old` 比较，**不等价**则返回（¶21–¶22，用的仍是上面的"等价"定义，不是按字节比较）；是原子等待操作。`notify_one`、`notify_all` 照常（[[atomics.wait]]）。

## weak_ptr 偏特化（[util.smartptr.atomic.weak]）

与 `shared_ptr` 版本逐条平行：成员 `weak_ptr<T> p`；`load`/`store`/`exchange`/`compare_exchange_*`/`wait`/`notify_*`。等价的定义：存储相同的指针值，并且共享所有权或**都为空**。它的典型用途是缓存与观察者列表：多个线程原子地读写一个"可能已过期"的引用，需要时再 `lock()`。

## 被删除的旧接口

C++11 的做法是对普通 `shared_ptr` 对象使用一组非成员函数：`atomic_load(const shared_ptr<T>*)`、`atomic_store`、`atomic_exchange`、`atomic_compare_exchange_*` 及其 `_explicit` 版本。C++20 弃用了它们 {{deprecated}}，C++26 将其**删除** {{removed:C++26}}。[[diff.cpp23.depr]] ¶2 给出的理由：旧行为很脆弱——使用旧 API 的 `shared_ptr` 对象不受类型系统保护，与不使用该 API 的代码交互时，在某些情况下会悄无声息地产生未定义行为。`atomic<shared_ptr<T>>` 是完整的、类型安全的替代。

"不受类型系统保护"指的是：只要有**一处**代码忘了用 `atomic_load`、直接复制了那个 `shared_ptr` 变量，就是数据竞争，编译器毫无提示。`atomic<shared_ptr<T>>` 根本不提供非原子的访问方式。

## 实现视角

!!! impl "libc++ 尚未实现 atomic<shared_ptr<T>>"
    Clang 23 自带的 libc++ 中 `__cpp_lib_atomic_shared_ptr` 未定义。写 `std::atomic<std::shared_ptr<int>>` 会落到主模板，被 `static_assert` 拒绝：`std::atomic<T> requires that 'T' be a trivially copyable type`。本页的例子未经本地编译验证。

    与此同时，已在 C++26 中删除的 `std::atomic_load(const shared_ptr<T>*)` 等非成员函数，在 libc++ 的 `-std=c++2c` 模式下**仍然可用**，且没有弃用警告。

!!! impl "常见实现策略"
    `shared_ptr` 由两个指针组成，原子地操作它需要 16 字节 CAS 或者一把锁。libstdc++ 的实现把一个自旋锁位"藏"在控制块指针的最低位里（控制块至少按指针对齐，最低位空闲）：`load` 先锁住这一位，复制指针并增加引用计数，再解锁。所以它通常**不是**无锁的（`is_always_lock_free` 为 `false`），但临界区极短。

## 陷阱

!!! pitfall "`atomic<shared_ptr<T>>` 只保护指针变量，不保护指向的对象"
    `ap.load()->value = 42;` 两个线程同时这样做，对 `value` 仍然是数据竞争。原子智能指针保证的是"读写这个指针变量"安全，以及"拿到的对象不会在你使用时被释放"；对象本身的并发访问需要另外同步，或者把对象当作不可变的（写时复制：每次修改都 `make_shared` 一个新对象再 `store`）。

!!! pitfall "析构可能发生在意想不到的线程"
    `store` 或 `exchange` 替换掉旧值后，旧对象在最后一个持有者释放时析构——可能是执行 `store` 的线程，也可能是某个刚 `load` 过、稍后才释放的读者线程。析构函数里不要依赖"我在哪个线程上"。

## 小结

- 原子的部分：指针本身的读写、`use_count` 递增；不在原子操作内：递减、析构、释放。
- CAS 与 `wait` 比较的是"等价"（同指针 + 同所有权），不是 `==` 或逐字节。
- `T` 可以不完整；`operator=` 返回 `void`；没有 `volatile` 重载。
- 旧的 `atomic_load(shared_ptr*)` 系列 C++20 弃用、C++26 删除。
- libc++ 尚未提供这两个偏特化。
