---
title: 智能指针
summary: [smartptr] 导读——unique_ptr、shared_ptr/weak_ptr、out_ptr/inout_ptr 各自解决什么问题、如何选择；智能指针的散列支持
status: done
covers: util.smartptr.hash
related: unique.ptr, util.sharedptr, util.smartptr.shared, util.smartptr.weak, util.smartptr.enab, smartptr.adapt, util.smartptr.atomic, indirect, polymorphic
tags: 标准库, 智能指针, 导读
updated: 2026-10-18
---

[smartptr] 收录三组组件：

| 子条款 | 组件 | 所有权模型 | 本站笔记 |
|---|---|---|---|
| [unique.ptr] | `unique_ptr`、`default_delete`、`make_unique` | 独占，可转移 | [[unique.ptr]] |
| [util.sharedptr] | `shared_ptr`、`weak_ptr`、`bad_weak_ptr`、`owner_less`/`owner_hash`/`owner_equal`、`enable_shared_from_this` | 共享，引用计数 | [[util.sharedptr]]、[[util.smartptr.shared]]、[[util.smartptr.weak]]、[[util.smartptr.ownerless]]、[[util.smartptr.enab]] |
| [util.smartptr.hash] | `hash<unique_ptr>`、`hash<shared_ptr>` | — | 本页 |
| [smartptr.adapt] | `out_ptr`、`inout_ptr` | 与 C 风格"输出指针形参"互操作 | [[smartptr.adapt]] |

`atomic<shared_ptr<T>>` 与 `atomic<weak_ptr<T>>` 声明在 `<memory>`，但规范在原子操作章 [[util.smartptr.atomic]]。

## 怎么选

1. **默认用 `unique_ptr`。** 零开销（空删除器时与裸指针同大小），所有权转移显式（`std::move`），可以随时升级为 `shared_ptr`（`shared_ptr` 有从 `unique_ptr&&` 的构造函数），反之不行。
2. **只有当所有权真的被多个独立的生命周期共享、且无法确定谁最后释放时，才用 `shared_ptr`。** 它的代价是：额外的控制块（一次分配，或用 `make_shared` 合并）、每次复制/析构的**原子**引用计数操作、两倍于裸指针的大小。
3. **`weak_ptr` 用于"观察但不延长生命周期"**：缓存、观察者列表、打破 `shared_ptr` 环。
4. **需要值语义的"堆上对象"时，C++26 起考虑 [[indirect]] / [[polymorphic]]**：它们像 `unique_ptr` 一样独占，但**可复制**（深拷贝）、`const` 正确传播、比较按值进行。它们不在 [smartptr] 下，而在 [[mem.composite.types]]。
5. **非拥有的观察用裸指针或引用。** 标准没有 `observer_ptr`（它只存在于 Library Fundamentals TS v2 中）。

一个常被忽略的事实：标准智能指针都**不是线程安全的容器**。`shared_ptr` 只保证"不同的 `shared_ptr` 对象之间"操作引用计数不构成数据竞争；对**同一个** `shared_ptr` 对象的并发读写仍是数据竞争（见 [[util.sharedptr]]）。

## 散列支持（[util.smartptr.hash]）

- ¶1：令 `UP` 为 `unique_ptr<T, D>`。`hash<UP>` **当且仅当** `hash<typename UP::pointer>` 启用时启用（[[unord.hash]]）；启用时 `hash<UP>()(p)` 与 `hash<typename UP::pointer>()(p.get())` 的值相同。成员函数**不保证** `noexcept`——花式 `pointer` 的散列可能抛异常。
- ¶2：`hash<shared_ptr<T>>()(p)` 等于 `hash<typename shared_ptr<T>::element_type*>()(p.get())`。

两者都是**按存储指针**（`get()`）散列，与 `operator==` 一致（`==` 也比较 `get()`）。这意味着：

- 别名构造得到的 `shared_ptr`（[[util.smartptr.shared]]）与原 `shared_ptr` 散列值**不同**，尽管它们共享所有权；
- 要按**所有权**分组（例如用 `weak_ptr` 作为无序容器的键），应改用 C++26 的 `owner_hash` 与 `owner_equal`（[[util.smartptr.ownerless]]）。`weak_ptr` 根本没有 `hash` 特化——它的 `get()` 不存在，存储的指针随时可能悬空。

```cpp title="smartptr-hash.cpp" ok
#include <memory>
#include <unordered_set>
#include <cassert>

struct P { int a, b; };

int main() {
    auto sp = std::make_shared<P>();
    std::shared_ptr<int> alias(sp, &sp->b);         // 共享所有权，但 get() 不同
    std::unordered_set<std::shared_ptr<void>> s;
    s.insert(sp);
    s.insert(alias);
    assert(s.size() == 2);                           // 按 get() 区分
    assert(std::hash<std::shared_ptr<P>>()(sp) == std::hash<P*>()(sp.get()));
}
```

## 小结

- `unique_ptr` 是默认选择；`shared_ptr` 用于真正的共享所有权；`weak_ptr` 用于观察。
- 智能指针的 `hash` 与 `==` 都基于存储指针 `get()`；按所有权比较/散列要用 owner 系列工具。
- `hash<unique_ptr>` 是否启用取决于 `hash<pointer>`，且不保证 `noexcept`。
