---
title: 智能指针
summary: unique_ptr、shared_ptr、weak_ptr、out_ptr 各自解决什么问题、怎样选择，以及智能指针的散列为什么按存储的指针计算。
status: done
covers: util.smartptr.hash
related: unique.ptr, util.sharedptr, util.smartptr.shared, util.smartptr.weak, util.smartptr.enab, smartptr.adapt, util.smartptr.atomic, indirect, polymorphic
tags: 标准库, 智能指针, 导读
updated: 2026-10-19
---

!!! tldr
    - 默认用 `unique_ptr`：独占所有权，用空删除器时和普通指针一样大，需要时可以转换成 `shared_ptr`。
    - 只有所有权确实由多方共享、无法确定谁最后释放时，才用 `shared_ptr`；它要多一个控制块，复制和销毁时做原子的计数操作。
    - `weak_ptr` 观察一个 `shared_ptr` 管理的对象而不延长它的生命周期，用于缓存、观察者列表和打破循环引用。
    - 智能指针的 `hash` 和 `==` 都按存储的指针 `get()` 计算；想按所有权分组，用 `owner_hash` 和 `owner_equal`。

## 组成

| 子条款 | 组件 | 所有权 |
|---|---|---|
| [[unique.ptr]] | `unique_ptr`、`default_delete`、`make_unique` | 独占，可以转移 |
| [[util.sharedptr]] | `shared_ptr`、`weak_ptr`、`bad_weak_ptr`、`owner_less`/`owner_hash`/`owner_equal`、`enable_shared_from_this` | 共享，引用计数 |
| [util.smartptr.hash] | `hash<unique_ptr>`、`hash<shared_ptr>` | 见下文 |
| [[smartptr.adapt]] | `out_ptr`、`inout_ptr` | 与通过指针形参输出指针的 C 接口配合 |

`shared_ptr` 的细节分在 [[util.smartptr.shared]]、[[util.smartptr.weak]]、[[util.smartptr.ownerless]]、[[util.smartptr.enab]] 几页。`atomic<shared_ptr<T>>` 和 `atomic<weak_ptr<T>>` 声明在 `<memory>` 里，规则写在原子操作一章的 [[util.smartptr.atomic]]。

## 怎样选择

1. 默认用 `unique_ptr`。用空删除器时它和普通指针一样大，没有额外开销；所有权转移要显式写 `std::move`。`shared_ptr` 有一个接受 `unique_ptr&&` 的构造函数，所以以后随时可以改成共享，反过来则不行。
2. 只有当所有权真的被几个独立的生命周期共享、无法确定谁最后释放时，才用 `shared_ptr`。代价是一个额外的控制块（多一次分配，用 `make_shared` 可以合并成一次），每次复制和销毁都有原子的引用计数操作，对象本身也通常是普通指针的两倍大。
3. `weak_ptr` 用于观察但不延长生命周期：缓存、观察者列表、打破 `shared_ptr` 之间的循环引用。
4. 需要一个放在堆上、但有值语义的对象时，C++26 起可以考虑 [[indirect]] 和 [[polymorphic]]。它们像 `unique_ptr` 一样独占所有权，但可以复制（深拷贝），`const` 会传递到所指对象，比较时比较的是值。它们不在 [smartptr] 下，而在 [[mem.composite.types]]。
5. 不拥有对象的观察用普通指针或引用。标准里没有 `observer_ptr`，它只在 Library Fundamentals TS v2 里。

智能指针不会让所指对象变得线程安全，也不会让智能指针对象本身线程安全。`shared_ptr` 只保证不同的 `shared_ptr` 对象并发操作同一个引用计数时不构成数据竞争；并发读写同一个 `shared_ptr` 对象仍然是数据竞争（[[util.sharedptr]]）。

## 散列 [util.smartptr.hash]

```cpp run ok
#include <cassert>
#include <memory>
#include <unordered_set>

struct P { int a, b; };

int main() {
  auto sp = std::make_shared<P>();
  std::shared_ptr<int> alias(sp, &sp->b);   // 共享所有权，get() 不同
  std::unordered_set<std::shared_ptr<void>> s;
  s.insert(sp);
  s.insert(alias);
  assert(s.size() == 2);                     // 按 get() 区分
  assert(std::hash<std::shared_ptr<P>>()(sp) ==
         std::hash<P*>()(sp.get()));
}
```

`alias` 用别名构造函数（[[util.smartptr.shared]]）创建，它和 `sp` 共享同一个控制块，但存储的指针指向成员 `b`。集合把它们当作两个不同的元素。

¶1 设 `UP` 为 `unique_ptr<T, D>`。当且仅当 `hash<typename UP::pointer>` 启用时，`hash<UP>` 才启用（[[unord.hash]]）。启用时，`hash<UP>()(p)` 的值等于 `hash<typename UP::pointer>()(p.get())`。这些成员函数不保证 `noexcept`，因为自定义的 `pointer` 类型，散列可能抛异常。

¶2 对 `shared_ptr<T>` 对象 `p`，`hash<shared_ptr<T>>()(p)` 的值等于 `hash<typename shared_ptr<T>::element_type*>()(p.get())`。

两者都按存储的指针 `get()` 计算，和 `operator==` 一致，`==` 比较的也是 `get()`。所以别名 `shared_ptr` 和原来的 `shared_ptr` 散列值一般不同，尽管它们共享所有权。

要按所有权分组，比如用 `weak_ptr` 作为无序容器的键，应该用 C++26 的 `owner_hash` 和 `owner_equal`（[[util.smartptr.ownerless]]）。`weak_ptr` 没有 `hash` 特化：它没有 `get()`，存储的指针随时可能悬空。
