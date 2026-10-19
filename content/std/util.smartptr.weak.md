---
title: weak_ptr
summary: weak_ptr 观察一个由 shared_ptr 管理的对象而不拥有它：只能经由 lock() 原子地取得 shared_ptr，只能按所有权比较，常用于缓存、观察者和打破引用环。
status: done
covers: *
related: util.sharedptr, util.smartptr.shared, util.smartptr.ownerless, util.smartptr.enab, util.smartptr.atomic
tags: 标准库, 智能指针, weak_ptr
updated: 2026-10-19
---

!!! tldr
    - `weak_ptr` 让控制块继续存在，但不让对象继续存在；对象被销毁后，`weak_ptr` 仍能可靠地报告这一点。
    - 它没有 `operator*`、`operator->` 和 `get()`，访问对象的唯一途径是 `lock()`，它原子地检查对象是否存活并取得一个 `shared_ptr`。
    - 先 `expired()` 再 `lock()` 有竞态，正确的写法是 `if (auto sp = w.lock())`。
    - `weak_ptr` 只能按所有权比较和散列，这种比较在对象销毁后依然稳定，所以 `weak_ptr` 可以做容器的键。
    - 两个对象互相用 `shared_ptr` 指向对方时永远不会被释放，把回指的一方改成 `weak_ptr` 就能打破这个环。

## 打破引用环

```cpp run title="break-cycle.cpp" ok
#include <memory>
#include <cstdio>
struct Node {
    std::shared_ptr<Node> next;     // 拥有下一个节点
    std::weak_ptr<Node>   prev;     // 只观察上一个节点
    ~Node() { std::puts("~Node"); }
};
int main() {
    auto a = std::make_shared<Node>();
    auto b = std::make_shared<Node>();
    a->next = b;
    b->prev = a;
    std::weak_ptr<Node> w = b;
    if (auto sp = w.lock())
        std::printf("alive, use_count=%ld\n", sp.use_count());   // 3
}
```

本机输出 `alive, use_count=3`（`b`、`a->next` 和 `sp`），然后打印两次 `~Node`。如果 `prev` 也是 `shared_ptr`，`a` 和 `b` 的计数在 `main` 结束时都还是 1，两个节点都不会析构，内存就泄漏了。`shared_ptr` 只是引用计数，没有环检测。

选哪一边用 `weak_ptr` 取决于所有权的方向：拥有者持有 `shared_ptr`（父节点拥有子节点、容器拥有元素），被拥有者回指拥有者时用 `weak_ptr`。

## weak_ptr 是什么 [util.smartptr.weak.general]

¶1 `weak_ptr` 存储对一个已经由 `shared_ptr` 管理的对象的弱引用。要访问对象，用成员函数 `lock()` 把它转换为 `shared_ptr`。¶2 它可复制构造、可复制赋值，`T` 可以是不完整类型。

按 [[util.sharedptr]] 的物理模型，`weak_ptr` 也是两个指针：存储指针和控制块指针。它增加的是控制块里的弱计数。强计数归零时对象被销毁，控制块要等弱计数也归零才释放，所以 `weak_ptr` 总能安全地查询对象是否还在。

接口中刻意没有 `operator*`、`operator->` 和 `get()`。被观察的对象随时可能被另一个线程销毁，任何直接访问都存在从检查到使用之间的竞态。`lock()` 返回的 `shared_ptr` 则保证对象在它的作用域内存活。

## 构造、赋值与析构 [util.smartptr.weak.const]

¶1–¶2 默认构造得到空的 `weak_ptr`，存储空指针，`use_count() == 0`。

¶3–¶5 从 `weak_ptr` 或 `shared_ptr` 复制：模板版本要求 `Y*` 与 `T*` 兼容（[[util.smartptr.shared#6]]）。`r` 为空时结果为空；否则结果与 `r` 共享所有权，并存储 `r` 中指针的一个副本。

¶6–¶8 移动构造之后 `r` 为空，存储空指针。

析构（[util.smartptr.weak.dest] ¶1）只销毁 `weak_ptr` 本身，对它的存储指针所指的对象没有影响。赋值（[util.smartptr.weak.assign]）与 `shared_ptr` 一样定义为构造临时对象再 `swap`，¶3 允许实现不真的创建临时对象。`reset()` 等价于 `weak_ptr().swap(*this)`。推导指引 `weak_ptr(shared_ptr<T>) -> weak_ptr<T>` 让 `std::weak_ptr w = sp;` 可以直接写。

### 转换一个已过期的 weak_ptr

从 `shared_ptr<Derived>` 转换到 `shared_ptr<Base>`，只需对存储指针做一次派生类到基类的转换。对 `weak_ptr` 就麻烦了：对象可能已经销毁，存储指针已经悬空。如果 `Base` 是虚基类，这次转换要读取对象中的信息才能算出基类子对象的地址，对已销毁的对象这样做是 UB。¶4 只说存储 `r` 中指针的一个副本，怎样安全地得到这个副本留给了实现。

libc++ 的做法是一律先 `lock()`，再从得到的 `shared_ptr` 构造：

```cpp run title="convert-expired.cpp" impl
#include <memory>
#include <cstdio>
struct B { int x; };
struct D : B {};
int main() {
    std::weak_ptr<D> w;
    { auto sp = std::make_shared<D>(); w = sp; }   // w 已过期，但不是空的
    std::weak_ptr<B> wb = w;                        // 按 ¶4：与 w 共享所有权
    std::weak_ptr<B> empty;
    bool same = !w.owner_before(wb) && !wb.owner_before(w);
    bool is_empty = !wb.owner_before(empty) && !empty.owner_before(wb);
    std::printf("same group: %d, empty: %d\n", same, is_empty);
}
```

本机 libc++ 输出 `same group: 0, empty: 1`。`w` 已经过期，`lock()` 返回空的 `shared_ptr`，于是 `wb` 成了一个空的 `weak_ptr`，不再与 `w` 属于同一个所有权组。按 ¶4，`w` 不是空的（过期不等于空），结果应当与 `w` 共享所有权。这是 libc++ 与标准措辞的一处可观察差异：如果容器以过期的 `weak_ptr` 为键，转换前后的键在按所有权比较时就不再等价。

## 观察器 [util.smartptr.weak.obs]

¶1 `use_count()` 在为空时返回 0，否则返回与它共享所有权的 `shared_ptr` 的个数。¶2 `expired()` 返回 `use_count() == 0`。

!!! std "[util.smartptr.weak.obs]/3"
    *Returns*: `expired() ? shared_ptr<T>() : shared_ptr<T>(*this)`, executed atomically.

¶3 关键在 executed atomically。检查强计数非零和把它加一必须是不可分割的一步，否则另一个线程可能在两步之间把计数减到 0 并销毁对象。实现通常用一个比较交换循环：只在计数非零时把它加一。

!!! pitfall "先 `expired()` 再 `lock()`"
    ```cpp
    if (!w.expired()) {
        auto sp = w.lock();   // sp 仍可能为空
        sp->f();              // 可能解引用空指针
    }
    ```
    `expired()` 的结果一返回就可能过时，只有返回 `true` 是稳定的，因为对象被销毁后不会复活。正确的写法是 `if (auto sp = w.lock()) { ... }`。

¶4–¶7 `owner_before`、`owner_hash`、`owner_equal` 与 `shared_ptr` 的同名成员相同，见 [[util.smartptr.ownerless]]。`weak_ptr` 过期之后，控制块仍然存在、地址不变，所以这些比较的结果不变。这正是 `weak_ptr` 能做有序或无序容器的键的原因。

`weak_ptr` 没有 `operator==`、`operator<`，也没有 `std::hash` 特化。它的存储指针可能悬空，按存储指针比较没有意义。

<details class="fine" markdown="1"><summary>其余条文</summary>

[util.smartptr.weak.mod] ¶1：成员 `swap` 交换两个对象的内容。[util.smartptr.weak.spec] ¶1：非成员 `swap(a, b)` 等价于 `a.swap(b)`。

</details>

## 思考题

!!! question "思考题 1"
    用 `std::map<Key, std::weak_ptr<Value>>` 做缓存，它会无限增长吗？

<details markdown="1">
<summary>答案</summary>

会。对象销毁后，过期的 `weak_ptr` 仍留在 map 里。如果对象是 `make_shared` 创建的，对象和控制块在同一次分配里，弱计数不归零，整块内存都不会释放（[[util.sharedptr]]）。需要定期清理过期条目，或者在 `lock()` 失败时顺手 `erase`。
</details>

!!! question "思考题 2"
    单线程下，`w.lock().use_count()` 与紧挨着它之前的 `w.use_count()` 有什么关系？

<details markdown="1">
<summary>答案</summary>

如果对象还活着，前者比后者大 1，因为 `lock()` 返回的 `shared_ptr` 本身也算一个所有者。[[util.smartptr.shared]] 中 `use_count` 的注 2 提醒的正是这一点：`weak_ptr::lock()` 会影响 `use_count()` 的返回值。
</details>

## 小结

- `weak_ptr` 延长控制块的寿命，不延长对象的寿命。
- 访问对象只能用 `lock()`，它原子地检查并取得 `shared_ptr`；`expired()` 只有返回 `true` 时可信。
- 只能按所有权比较和散列，过期后结果不变，因此可以做容器的键。
- 拥有者持有 `shared_ptr`，回指者持有 `weak_ptr`，以此打破环。
