---
title: enable_shared_from_this
summary: 让对象安全地"再要一个"共享自身所有权的 shared_ptr——内部的 weak-this 何时由 shared_ptr 构造函数设置；构造函数中、栈对象上调用 shared_from_this 抛 bad_weak_ptr（C++17 起不再是 UB）；私有继承、复制、多重继承的坑
status: done
related: util.smartptr.shared, util.sharedptr, util.smartptr.weak, class.access.base
tags: 标准库, 智能指针, shared_from_this
papers: P0033R1
updated: 2026-10-18
---

场景：一个由 `shared_ptr` 管理的对象，要在成员函数里把"指向自己的 `shared_ptr`"交给别人——典型例子是异步 I/O 中把 `shared_ptr<Session>` 捕获进回调，保证回调执行时会话仍然存活。`shared_ptr<Session>(this)` 是错的：它新建第二个控制块，导致双重删除（[[util.smartptr.shared]]）。我们需要的是**与已有所有者共享同一个控制块**的 `shared_ptr`。

`enable_shared_from_this<T>` 的方案：在对象里藏一个 `weak_ptr<T>`（说明用成员 *weak-this*），由**创建第一个 `shared_ptr` 的那个构造函数**负责填写；之后对象随时可以从这个 `weak_ptr` 得到 `shared_ptr`。

## 接口（[util.smartptr.enab] ¶1–¶3）

```cpp
template<class T> class enable_shared_from_this {
protected:
  constexpr enable_shared_from_this() noexcept;
  constexpr enable_shared_from_this(const enable_shared_from_this&) noexcept;
  constexpr enable_shared_from_this& operator=(const enable_shared_from_this&) noexcept;
  constexpr ~enable_shared_from_this();
public:
  constexpr shared_ptr<T>       shared_from_this();
  constexpr shared_ptr<T const> shared_from_this() const;
  constexpr weak_ptr<T>       weak_from_this() noexcept;        // C++17
  constexpr weak_ptr<T const> weak_from_this() const noexcept;  // C++17
private:
  mutable weak_ptr<T> weak-this;  // exposition only
};
```

¶1：类 `T` 可以继承 `enable_shared_from_this<T>`（CRTP）以获得 `shared_from_this`。¶3：`T` 可以是不完整类型。特殊成员都是 `protected`：它只能作为基类使用。

## *weak-this* 由谁设置

不是 `enable_shared_from_this` 自己，而是 `shared_ptr` 的构造函数——[util.smartptr.shared.const] ¶1 定义的"**以 `p` 启用 shared_from_this**"：若 `Y` 有一个**无歧义且可访问**的 `enable_shared_from_this` 特化基类，且 `p->weak-this` 已过期，就令 `p->weak-this = shared_ptr<remove_cv_t<Y>>(*this, p)`。以下构造途径会启用：

- `shared_ptr(Y* p)`、`shared_ptr(Y* p, D d)`、`shared_ptr(Y* p, D d, A a)`（非数组 `T`）；
- `shared_ptr(unique_ptr<Y, D>&&)`（它等价于前两者之一）；
- `make_shared`、`allocate_shared`（[util.smartptr.shared.create] ¶10）。

别名构造、复制、从 `weak_ptr` 构造**不**启用——它们不创建新的所有权组。

## 成员函数（¶4–¶8）

- ¶4：默认构造与**复制构造**都**值初始化** *weak-this*。
- ¶5–¶6：复制赋值返回 `*this`，注 1：*weak-this* **不变**。
- ¶7：`shared_from_this()` 返回 `shared_ptr<T>(weak-this)`。
- ¶8：`weak_from_this()` 返回 *weak-this*。

¶7 的写法决定了失败行为：从过期的 `weak_ptr` 构造 `shared_ptr` 抛 `bad_weak_ptr`（[util.smartptr.shared.const] ¶27）。所以**对不被任何 `shared_ptr` 拥有的对象调用 `shared_from_this()` 会抛 `bad_weak_ptr`**。这是 C++17 由 [[P0033R1]] 确立的；在 C++11/14 中，`shared_from_this()` 有前置条件"必须存在拥有 `*this` 的 `shared_ptr`"，违反即 UB。`weak_from_this()` 也是同一提案加入的，失败时返回空 `weak_ptr`，不抛异常。

¶4–¶6 中"复制不复制 *weak-this*"同样必要：对象被复制后，副本是一个**新**对象，它的所有者（如果有）与原件无关。若 *weak-this* 被复制，副本的 `shared_from_this()` 会返回指向**原件**的 `shared_ptr`——类型正确、地址错误。

```cpp title="shared-from-this.cpp" ok
#include <memory>
#include <cstdio>

struct Session : std::enable_shared_from_this<Session> {
    Session() {
        try { auto self = shared_from_this(); }            // 构造期间：weak-this 尚未设置
        catch (const std::bad_weak_ptr&) { std::puts("in ctor: bad_weak_ptr"); }
    }
};
class Hidden : std::enable_shared_from_this<Hidden> {     // class 默认 private 继承！
public:
    bool ok() { return !weak_from_this().expired(); }
};
struct Copyable : std::enable_shared_from_this<Copyable> {};

int main() {
    auto s = std::make_shared<Session>();
    std::printf("use_count via sft = %ld\n", s->shared_from_this().use_count());   // 2

    Session local;                                          // 不被 shared_ptr 拥有
    try { (void)local.shared_from_this(); }
    catch (const std::bad_weak_ptr&) { std::puts("stack object: bad_weak_ptr"); }

    auto h = std::make_shared<Hidden>();
    std::printf("private base detected: %d\n", h->ok());   // 0：基类不可访问，未启用

    auto c1 = std::make_shared<Copyable>();
    auto c2 = std::make_shared<Copyable>(*c1);              // 复制不复制 weak-this
    std::printf("c2 owns itself: %d\n", c2->shared_from_this() == c2);   // 1
}
```

## 常见陷阱

1. **在构造函数中调用 `shared_from_this()`。** 构造函数运行时，`shared_ptr` 的构造函数（或 `make_shared`）还没轮到"启用 shared_from_this"那一步——它必须等对象构造完成。于是抛 `bad_weak_ptr`。需要在创建时注册自己的类，应使用"私有构造函数 + 静态工厂函数"：工厂先 `make_shared`，再调用 `init()` 注册。析构函数中同理：此时强计数已归零，*weak-this* 已过期。
2. **私有继承。** `class X : enable_shared_from_this<X>` 是私有继承，"可访问"条件不满足，`shared_ptr` 的构造函数静默地不启用——没有任何诊断，`shared_from_this()` 永远抛异常。务必写 `public`（或用 `struct`）。
3. **多重继承出两个 `enable_shared_from_this`。** `struct A : enable_shared_from_this<A> {}; struct B : enable_shared_from_this<B> {}; struct C : A, B {};`——`C` 有两个不同的 `enable_shared_from_this` 特化基类。标准措辞是"若 `Y` 有一个无歧义且可访问的基类是 `enable_shared_from_this` 的特化"，没有说明存在两个这样的基类时该怎么办。本机 libc++ 的选择是**两个都不启用**：`make_shared<C>()` 之后 `c->A::weak_from_this()` 与 `c->B::weak_from_this()` 都是过期的。应避免这种设计；通常的解法是只让最顶层的公共基类继承 `enable_shared_from_this`，派生类用 `std::static_pointer_cast<Derived>(shared_from_this())`。
4. **并发。** 设置 *weak-this* 的赋值不是原子的（[util.smartptr.shared.const] ¶1 末句）。若对象指针在交给 `shared_ptr` 之前就已被其他线程看到，那个线程调用 `weak_from_this()` 与构造 `shared_ptr` 构成数据竞争。

!!! tip "C++23 显式对象形参"
    派生类想得到 `shared_ptr<Derived>` 而不是 `shared_ptr<Base>`，C++23 起可以写一个辅助函数 `template<class Self> auto shared_from(this Self& self) { return std::static_pointer_cast<Self>(self.shared_from_this()); }`，利用显式对象形参（[[dcl.fct]]）推导出实际类型。

## 思考题

<details markdown="1">
<summary>1. `auto p = std::shared_ptr<X>(new X); auto q = std::shared_ptr<X>(p.get());` 若 `X` 继承 `enable_shared_from_this<X>`，会发生什么？</summary>

仍然是双重删除的 UB。`q` 的构造函数检查 `p->weak-this.expired()`——未过期，所以**不**覆盖 *weak-this*，但它照样新建了第二个控制块并拥有同一对象。`enable_shared_from_this` 只提供"正确地再要一个"的途径，不能阻止错误的途径。
</details>

<details markdown="1">
<summary>2. 对 `const X` 对象，`shared_from_this()` 返回什么类型？为什么 *weak-this* 是 `mutable`？</summary>

返回 `shared_ptr<const X>`。*weak-this* 是 `mutable` 是因为 `shared_ptr` 构造函数需要对 `const X*`（`Y` 为 `const X`）也能写入它——¶1 中的 `const_cast<remove_cv_t<Y>*>(p)` 与 `mutable` 一起保证了 `shared_ptr<const X>(new const X)` 也能启用。
</details>

## 小结

- *weak-this* 由"创建所有权组"的 `shared_ptr` 构造函数或 `make_shared` 设置，前提是基类无歧义且**可访问**。
- 未被拥有时：`shared_from_this()` 抛 `bad_weak_ptr`（C++17 起），`weak_from_this()` 返回空。
- 构造函数和析构函数中都不能用 `shared_from_this()`。
- 复制构造与复制赋值都不传递 *weak-this*。
