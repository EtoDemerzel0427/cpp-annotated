---
title: owner_less、owner_hash 与 owner_equal
summary: 三个按所有权（控制块）而不是存储指针比较和散列 shared_ptr、weak_ptr 的函数对象：owner_less 让 weak_ptr 做有序容器的键，C++26 的 owner_hash 与 owner_equal 让它做无序容器的键。
status: done
covers: util.smartptr.owner.hash, util.smartptr.owner.equal
related: util.smartptr.shared, util.smartptr.weak, util.sharedptr, smartptr, alg.sorting, unord.req
tags: 标准库, 智能指针, weak_ptr, 关联容器
papers: P1901R2
updated: 2026-10-19
---

!!! tldr
    - `shared_ptr` 有两种相等：`==` 比较存储指针，所有权等价比较是否属于同一个所有权组。两者可以不一致。
    - `weak_ptr` 只有所有权意义上的比较，因为它的存储指针可能悬空。
    - `owner_less` 给出按所有权的严格弱序，`std::map<std::weak_ptr<X>, V, std::owner_less<>>` 是常见用法。
    - 对象销毁后，`weak_ptr` 键的比较结果不变，容器的不变式不会被破坏。
    - C++26 的 `owner_hash` 和 `owner_equal` 让 `weak_ptr` 可以做无序容器的键；本机 libc++ 尚未实现它们。

## 两种相等

```cpp run title="two-equalities.cpp" ok
#include <memory>
#include <cstdio>
int main() {
    std::shared_ptr<int> a, b;
    std::shared_ptr<int> c(nullptr, [](int*) {});
    std::printf("a,b: == %d  owner %d\n", a == b,
                !a.owner_before(b) && !b.owner_before(a));
    std::printf("a,c: == %d  owner %d\n", a == c,
                !a.owner_before(c) && !c.owner_before(a));
}
```

本机输出 `a,b: == 1  owner 1` 和 `a,c: == 1  owner 0`。`a` 和 `b` 都是空的，按两种标准都相等。`c` 拥有一个空指针和一个删除器，不是空的，它与 `a` 的存储指针都为空，所以 `==` 为真，但它们不属于同一个所有权组。反过来，别名构造的 `shared_ptr<int>(sp, &sp->b)` 与 `sp` 所有权等价，`==` 却为假（[[util.smartptr.shared]]）。

所有权等价的精确定义在成员函数 `owner_equal` 里：两者共享所有权，或者都为空。`owner_before` 给出与之一致的严格弱序，`owner_hash` 给出与之一致的散列值。`owner_less`、`owner_hash`、`owner_equal` 这三个函数对象只是把这三个成员函数包装成容器能用的比较器和散列器。

## owner_less [util.smartptr.ownerless]

```cpp run title="owner-less-map.cpp" ok
#include <memory>
#include <map>
#include <cassert>
struct P { int a, b; };
int main() {
    auto sp = std::make_shared<P>();
    std::shared_ptr<int> alias(sp, &sp->b);
    std::weak_ptr<P> w = sp;
    std::map<std::weak_ptr<void>, int, std::owner_less<>> m;
    m[w] = 1;
    m[alias] = 2;                     // 与 w 同组：同一个键
    assert(m.size() == 1 && m.begin()->second == 2);
    sp.reset();
    alias.reset();
    assert(w.expired() && m.find(w) != m.end());   // 过期的键仍可查找
}
```

¶1 `owner_less` 允许对共享指针和弱指针做基于所有权的混合比较。它有三种形式：`owner_less<shared_ptr<T>>` 和 `owner_less<weak_ptr<T>>` 各有三个 `operator()`，接受 `shared_ptr` 与 `weak_ptr` 的各种组合；C++17 起的 `owner_less<void>`（主模板的默认实参就是 `void`）接受任意 `T`、`U`，并带有 `is_transparent`，可以用 `shared_ptr` 直接在以 `weak_ptr` 为键的容器里查找，不必先构造一个临时的 `weak_ptr`。

¶2 `operator()(x, y)` 返回 `x.owner_before(y)`。注 1 指出，它是一个严格弱序（[[alg.sorting]]），而且 `!op(a, b) && !op(b, a)` 当且仅当 `a.owner_equal(b)`。

上例最后一行说明了按所有权比较的价值。键过期后，控制块仍然存在（map 里的 `weak_ptr` 本身就让弱计数非零），它的地址不变，比较结果也就不变。如果改成按 `lock().get()` 比较，过期的键会突然变成空指针，与其他过期的键相等，红黑树的有序性就悄悄被破坏了。

## owner_hash 与 owner_equal {{c++26}}

### owner_hash [util.smartptr.owner.hash]

¶1 `owner_hash` 提供基于所有权的散列。它对 `shared_ptr<T>` 和 `weak_ptr<T>` 各有一个 `operator()`，并带有 `is_transparent`。¶2 `operator()(x)` 返回 `x.owner_hash()`。¶3 注 1：对任何满足 `x.owner_equal(y)` 的 `y`，`x.owner_hash() == y.owner_hash()`，满足无序容器对散列和相等一致的要求（[[unord.req]]）。

### owner_equal [util.smartptr.owner.equal]

¶1 `owner_equal` 提供基于所有权的混合相等比较，有 `shared_ptr` 与 `weak_ptr` 两两组合的四个 `operator()`，也带有 `is_transparent`。¶2 `operator()(x, y)` 返回 `x.owner_equal(y)`，¶3 注 1 说明它当且仅当 `x` 和 `y` 共享所有权或都为空时为真。

`owner_equal` 是 `constexpr` 的：判断两者是否指向同一个控制块，常量求值中可以做到。`owner_hash` 和 `owner_before` 需要控制块地址的数值，所以不是 `constexpr`。

二者配合，就可以写 `std::unordered_map<std::weak_ptr<X>, V, std::owner_hash, std::owner_equal>`。在 [[P1901R2]] 之前，标准没有任何可移植的方式拿到控制块的身份来做散列，`weak_ptr` 只能放进有序容器。截至写作时，本机 libc++ 没有定义 `__cpp_lib_smart_ptr_owner_equality`，也不提供这两个类，所以本节没有可编译的例子。

## 思考题

!!! question "思考题"
    能不能用 `std::set<std::shared_ptr<X>>` 代替 `std::set<std::shared_ptr<X>, std::owner_less<>>`？两者什么时候行为不同？

<details markdown="1">
<summary>答案</summary>

默认的 `std::less<std::shared_ptr<X>>` 用 `<=>` 比较存储指针（[[util.smartptr.shared]] 的比较部分）。只要集合里没有别名构造的 `shared_ptr`，也没有拥有空指针的 `shared_ptr`，两者的分组结果相同。差异出现在两种情况：两个指向同一对象不同成员的别名 `shared_ptr` 在 `owner_less<>` 下等价、在默认比较下不等价；一个空的 `shared_ptr` 和一个拥有空指针的 `shared_ptr` 在默认比较下等价、在 `owner_less<>` 下不等价。对 `shared_ptr` 两种都可以用，对 `weak_ptr` 只能用 `owner_less`。
</details>

## 小结

| 工具 | 依据 | 用途 |
|---|---|---|
| `==`、`<=>`、`hash<shared_ptr>` | 存储指针 `get()` | 区分指向哪里 |
| `owner_less` | 控制块的严格弱序 | `weak_ptr`、`shared_ptr` 做有序容器的键 |
| `owner_hash` + `owner_equal` {{c++26}} | 控制块的身份 | 做无序容器的键 |
