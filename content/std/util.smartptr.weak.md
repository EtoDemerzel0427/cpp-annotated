---
title: weak_ptr
summary: weak_ptr 是"共享所有权组中不拥有对象的成员"——它延长控制块而非对象的寿命；lock() 原子地检查并获取，expired() 之后再 lock 是 TOCTOU；用 weak_ptr 打破 shared_ptr 环
status: done
covers: *
related: util.sharedptr, util.smartptr.shared, util.smartptr.ownerless, util.smartptr.enab, util.smartptr.atomic
tags: 标准库, 智能指针, weak_ptr
updated: 2026-10-18
---

`weak_ptr` 解决两类问题：

1. **观察而不拥有**：缓存、观察者、回调注册表需要指向某个对象，但不应该让对象因此活得更久；对象死了要能**检测到**，而不是留一个悬空裸指针。
2. **打破引用环**：`shared_ptr` 是纯引用计数，没有环检测。父节点强引用子节点、子节点强引用父节点，两者的计数永远不会归零。

## 概述（[util.smartptr.weak.general]）

¶1：`weak_ptr` 存储对**已被 `shared_ptr` 管理**的对象的弱引用；要访问对象，用 `lock()` 把它转换成 `shared_ptr`。¶2：可复制构造、可复制赋值，`T` 可以不完整。

接口中**没有** `operator*`、`operator->`、`get()`——这是刻意的：被观察的对象随时可能被另一个线程销毁，任何"直接访问"都是 TOCTOU（检查到使用之间的竞态）。唯一的访问路径是 `lock()`，它返回的 `shared_ptr` 在作用域内**保证**对象存活。

用 [[util.sharedptr]] 的物理模型来说：`weak_ptr` 也是"存储指针 + 控制块指针"两个字，它增加的是**弱计数**。强计数归零时对象被销毁，但控制块要等弱计数也归零才释放——所以 `weak_ptr` 总能安全地查询"对象还在不在"。

## 构造、析构、赋值（[util.smartptr.weak.const] 到 [util.smartptr.weak.mod]）

- 默认构造（¶1–¶2）：空，存储空指针，`use_count() == 0`。
- 从 `weak_ptr` 或 `shared_ptr` 复制（¶3–¶5）：*Constraints* 为 `Y*` 与 `T*` 兼容（[[util.smartptr.shared]] ¶6）；`r` 为空时得到空 `weak_ptr`，否则与 `r` 共享所有权并复制其存储指针；`use_count() == r.use_count()`。
- 移动（¶6–¶8）：`r` 变空、存储空指针、`use_count() == 0`。
- 析构（[util.smartptr.weak.dest]）：销毁自身，**对存储指针所指对象没有影响**。
- 赋值（[util.smartptr.weak.assign]）：等价于 `weak_ptr(r).swap(*this)`；¶3 允许实现不真的创建临时对象。
- `swap`、`reset()`（[util.smartptr.weak.mod]）。

!!! lawyer "从 `weak_ptr<Derived>` 转换为 `weak_ptr<Base>` 并不平凡"
    `shared_ptr<Derived>` → `shared_ptr<Base>` 只是对存储指针做一次派生到基的转换。但对 `weak_ptr`，存储指针可能**已经悬空**（对象已被销毁），而经由虚基类的派生到基转换需要读取对象的虚表——对已销毁对象做这件事是 UB。标准只说"共享所有权并存储 `r` 中指针的副本"，把如何安全得到"副本"留给了实现。

libc++ 的做法是**一律先 `lock()`**，再从得到的 `shared_ptr` 构造。副作用是：若 `r` 已过期，`lock()` 返回空，结果是一个**空** `weak_ptr`——它不再与 `r` 共享所有权。按 ¶4，`r` 非空（过期不等于空）时结果应与 `r` 共享所有权，`owner_before` 意义下与 `r` 等价。这是 libc++ 与标准措辞的一处可观察偏离：

```cpp title="weak-convert-expired.cpp" impl
#include <memory>
#include <cstdio>
struct B { int x; }; struct D : B {};
int main() {
    std::weak_ptr<D> w;
    { auto sp = std::make_shared<D>(); w = sp; }      // w 已过期，但仍属于原所有权组
    std::weak_ptr<B> wb = w;                          // 标准：与 w 共享所有权
    std::weak_ptr<B> empty;
    bool same = !w.owner_before(wb) && !wb.owner_before(w);
    bool is_empty = !wb.owner_before(empty) && !empty.owner_before(wb);
    std::printf("same group as w: %d, equivalent to empty: %d\n", same, is_empty);
    // 本机 libc++：same group as w: 0, equivalent to empty: 1
}
```

对以过期 `weak_ptr` 为键、且键类型发生过转换的容器，这会改变查找结果。

## 观察器（[util.smartptr.weak.obs]）

- `use_count()`（¶1）：空时 0，否则与之共享所有权的 `shared_ptr` 个数。
- `expired()`（¶2）：`use_count() == 0`。
- `lock()`（¶3）：

!!! std "[util.smartptr.weak.obs]/3"
    Returns: `expired() ? shared_ptr<T>() : shared_ptr<T>(*this)`, executed atomically.

    返回 `expired() ? shared_ptr<T>() : shared_ptr<T>(*this)`，**原子地**执行。

"原子地"是整个 `weak_ptr` 设计的核心：检查强计数非零与递增强计数必须是不可分割的一步，否则另一个线程可能在两步之间把计数减到 0、销毁对象。

!!! pitfall "`expired()` 然后 `lock()`"
    ```cpp
    if (!w.expired()) {
        auto sp = w.lock();   // sp 仍可能为空：expired() 返回后对象可能已被另一线程销毁
        sp->f();              // 可能解引用空指针
    }
    ```
    `expired()` 的结果一返回就可能过时，只有"为真"（已过期）是稳定的——对象死了不会复活。正确写法永远是 `if (auto sp = w.lock()) { ... }`。

- `owner_before`、`owner_hash`、`owner_equal`（¶4–¶7）：与 `shared_ptr` 的同名成员相同，见 [[util.smartptr.ownerless]]。它们**在 `weak_ptr` 过期后依然有意义**：控制块还在，地址不变。这正是 `weak_ptr` 能作为有序/无序容器键的原因——过期的键仍然可以比较，不会破坏容器不变式。

`weak_ptr` 没有 `operator==`、`operator<` 与 `hash` 特化：存储指针可能悬空，按值比较没有意义，只能按所有权比较。

## 打破环

```cpp title="weak-break-cycle.cpp" ok
#include <memory>
#include <cstdio>
struct Node {
    std::shared_ptr<Node> next;     // 强引用
    std::weak_ptr<Node>   prev;     // 弱引用：打破环
    ~Node() { std::puts("~Node"); }
};
int main() {
    auto a = std::make_shared<Node>();
    auto b = std::make_shared<Node>();
    a->next = b;
    b->prev = a;                     // 若 prev 也是 shared_ptr，a 和 b 永远不会析构
    std::weak_ptr<Node> w = b;
    if (auto sp = w.lock())          // 正确：一次原子的"检查并获取"
        std::printf("alive, use_count=%ld\n", sp.use_count());   // 3：b、a->next、sp
}                                    // 打印两次 ~Node，LSan 无报告
```

选择哪一边用弱引用，取决于所有权的方向：**拥有者**持强引用（父拥有子、容器拥有元素），**被拥有者**回指拥有者时用弱引用。

## 特化算法（[util.smartptr.weak.spec]）

`swap(a, b)` 等价于 `a.swap(b)`。另有推导指引 `weak_ptr(shared_ptr<T>) -> weak_ptr<T>`。

## 思考题

<details markdown="1">
<summary>1. 用 `weak_ptr` 做缓存：`std::map<Key, std::weak_ptr<Value>>`。它会无限增长吗？</summary>

会。对象销毁后，过期的 `weak_ptr` 仍留在 map 里，并且（若对象由 `make_shared` 创建）还**钉住了整块内存**——控制块与对象在同一次分配中，弱计数不归零就不释放（[[util.sharedptr]]）。需要定期清理过期条目，或者在 `lock()` 失败时顺手 `erase`。
</details>

<details markdown="1">
<summary>2. `weak_ptr::use_count()` 与 `lock()` 的返回值的 `use_count()` 有什么关系？</summary>

`lock()` 成功后多了一个 `shared_ptr`（返回值本身），所以 `w.lock().use_count()` 比紧邻之前的 `w.use_count()` 大 1（单线程下）。[[util.smartptr.shared]] 的 `use_count` 注 2 正是提醒：`weak_ptr::lock()` 会影响 `use_count()` 的返回值。
</details>

## 小结

- `weak_ptr` 延长控制块的寿命，不延长对象的寿命。
- 没有解引用接口；唯一的访问方式是 `lock()`，它原子地检查并获取。
- `expired()` 只有"为真"可信；`if (auto sp = w.lock())` 是唯一正确的模式。
- 只能按所有权比较与散列，过期后依然有效——因此可作为容器键。
- 拥有者持强引用、回指者持弱引用，以打破环。
