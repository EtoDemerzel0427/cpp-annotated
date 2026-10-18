---
title: owner_less、owner_hash 与 owner_equal
summary: 按所有权（控制块）而非存储指针比较与散列 shared_ptr/weak_ptr——让 weak_ptr 能做 std::map 键（owner_less）和 C++26 起做无序容器键（owner_hash + owner_equal）
status: done
covers: util.smartptr.owner.hash, util.smartptr.owner.equal
related: util.smartptr.shared, util.smartptr.weak, util.sharedptr, smartptr, alg.sorting, unord.req
tags: 标准库, 智能指针, weak_ptr, 关联容器
papers: P1901R2
updated: 2026-10-18
---

`shared_ptr` 有两种"相等"：

- **值相等**：`a == b` 比较存储指针 `get()`；
- **所有权等价**：`a` 与 `b` 属于同一个所有权组（共享同一个控制块），或都为空。

二者可以不一致：别名构造的 `shared_ptr<int>(sp, &sp->b)` 与 `sp` 所有权等价但值不等；两个都持有 `nullptr` 的 `shared_ptr`（一个空的、一个拥有空指针加删除器的）值相等但所有权不等价。`weak_ptr` 则**只有**所有权意义上的比较——它的存储指针可能悬空，没有 `get()`、没有 `==`。

本页三个函数对象把成员函数 `owner_before`、`owner_hash`、`owner_equal`（见 [[util.smartptr.shared]]）包装成可用于容器的比较器与散列器。

## `owner_less`（[util.smartptr.ownerless]）

```cpp
template<class T = void> struct owner_less;
template<class T> struct owner_less<shared_ptr<T>>;   // 三个 operator()，混合 shared/weak
template<class T> struct owner_less<weak_ptr<T>>;
template<> struct owner_less<void>;                    // C++17，透明，任意 T、U
```

- ¶1：允许对共享指针与弱指针做**基于所有权的混合比较**。
- ¶2：`operator()(x, y)` 返回 `x.owner_before(y)`。注 1：它构成严格弱序（[[alg.sorting]]），且 `!op(a, b) && !op(b, a)` 当且仅当 `a.owner_equal(b)`。

`owner_less<void>` 的 `is_transparent` 使得 `std::map<std::weak_ptr<X>, V, std::owner_less<>>` 可以直接用 `shared_ptr<X>` 查找而无需构造临时 `weak_ptr`（[[associative.reqmts]] 的异构查找）。

```cpp title="owner-less-map.cpp" ok
#include <memory>
#include <map>
#include <cassert>
struct P { int a, b; };
int main() {
    auto sp = std::make_shared<P>();
    std::shared_ptr<int> alias(sp, &sp->b);
    std::weak_ptr<P> w = sp;
    std::map<std::weak_ptr<void>, int, std::owner_less<>> m;   // weak_ptr 作键：按所有权排序
    m[w] = 1;
    m[alias] = 2;                       // 与 w 共享所有权 → 同一个键
    assert(m.size() == 1 && m.begin()->second == 2);
    assert(!(sp.owner_before(alias) || alias.owner_before(sp)));
    sp.reset(); alias.reset();
    assert(w.expired() && m.size() == 1);   // 过期的 weak_ptr 键仍然有效、仍可比较
}
```

最后一行是关键：键过期后，控制块仍然存在（弱计数非零，`map` 里的 `weak_ptr` 本身就是一个弱引用），`owner_before` 比较的控制块地址不变，`map` 的有序性不被破坏。若改用"按 `lock().get()` 比较"，过期键会突然变成"空指针"，与其他过期键相等，红黑树的不变式就被悄悄破坏了。

## `owner_hash`（[util.smartptr.owner.hash]）{{c++26}}

```cpp
struct owner_hash {
  template<class T> size_t operator()(const shared_ptr<T>&) const noexcept;
  template<class T> size_t operator()(const weak_ptr<T>&) const noexcept;
  using is_transparent = unspecified;
};
```

¶2：返回 `x.owner_hash()`。¶3 注：对任何 `x.owner_equal(y)` 的 `y`，`x.owner_hash() == y.owner_hash()`——满足无序容器对散列与相等一致的要求（[[unord.req]]）。

## `owner_equal`（[util.smartptr.owner.equal]）{{c++26}}

```cpp
struct owner_equal {
  template<class T, class U> constexpr bool operator()(const shared_ptr<T>&, const shared_ptr<U>&) const noexcept;
  // 以及 shared/weak、weak/shared、weak/weak 三种组合
  using is_transparent = unspecified;
};
```

¶2：返回 `x.owner_equal(y)`；¶3 注：当且仅当 `x`、`y` 共享所有权或都为空时为真。它是 `constexpr` 的——判断两者是否指向同一个控制块，常量求值中可以做到；而 `owner_hash` 与 `owner_before` 需要控制块地址的**数值**，不是 `constexpr`。

二者配合，`std::unordered_map<std::weak_ptr<X>, V, std::owner_hash, std::owner_equal>` 成为可能。在 C++26 之前（[[P1901R2]] 之前），`weak_ptr` 只能放进有序容器——标准没有任何可移植的方式拿到"控制块的身份"来散列。

截至写作时，本机 libc++ 尚未实现 `owner_hash`/`owner_equal`（`__cpp_lib_smart_ptr_owner_equality` 被注释掉），相应示例无法在本地验证。

## 思考题

<details markdown="1">
<summary>1. 两个默认构造的 `shared_ptr<int>` 与 `shared_ptr<int>(nullptr, [](int*){})` 之间，`owner_equal` 与 `==` 分别给出什么？</summary>

两个默认构造的：都为空，`owner_equal` 为真；`get()` 都为空，`==` 为真。默认构造的与带删除器的空指针版本：后者**拥有**（一个空指针和一个删除器），不是空的，它们不共享所有权，`owner_equal` 为假；但 `get()` 都是空指针，`==` 为真。
</details>

## 小结

| 工具 | 依据 | 用途 |
|---|---|---|
| `==`、`<=>`、`hash<shared_ptr>` | 存储指针 `get()` | 按"指向哪里"区分 |
| `owner_less` | 控制块的严格弱序 | `weak_ptr`/`shared_ptr` 作有序容器键 |
| `owner_hash` + `owner_equal` {{c++26}} | 控制块身份 | 作无序容器键 |

所有权比较在 `weak_ptr` 过期后依然稳定，这是它能作为容器键的根本原因。
