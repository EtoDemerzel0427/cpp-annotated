---
title: enable_shared_from_this
summary: 让一个由 shared_ptr 管理的对象安全地取得指向自身、与已有所有者共享所有权的 shared_ptr：内部的 weak-this 由谁、在何时设置，未被拥有时为何抛出 bad_weak_ptr，以及私有继承、多重继承和复制带来的陷阱。
status: done
related: util.smartptr.shared, util.sharedptr, util.smartptr.weak, class.access.base
tags: 标准库, 智能指针, shared_from_this
papers: P0033R1
updated: 2026-10-19
---

!!! tldr
    - 在成员函数里写 `shared_ptr<X>(this)` 会新建第二个所有权组，导致双重删除；`shared_from_this()` 返回与已有所有者共享所有权的 `shared_ptr`。
    - 实现方式是基类里藏一个 `weak_ptr`（说明用名 *weak-this*），由创建第一个所有权组的 `shared_ptr` 构造函数或 `make_shared` 填写。
    - 对象没有被任何 `shared_ptr` 拥有时（包括它自己的构造函数运行期间），`shared_from_this()` 抛出 `bad_weak_ptr`，`weak_from_this()` 返回空。
    - 基类必须可访问：`class X : enable_shared_from_this<X>` 是私有继承，不会有任何诊断，`shared_from_this()` 永远抛异常。
    - 复制对象不复制 *weak-this*，副本属于它自己的所有者。

## 从对象内部再要一个 shared_ptr

```cpp run title="shared-from-this.cpp" ok
#include <memory>
#include <cstdio>

struct Session : std::enable_shared_from_this<Session> {
    Session() {
        try { auto self = shared_from_this(); }          // 构造期间
        catch (const std::bad_weak_ptr&) { std::puts("in ctor: bad_weak_ptr"); }
    }
};
class Hidden : std::enable_shared_from_this<Hidden> {   // class 默认私有继承
public:
    bool ok() { return !weak_from_this().expired(); }
};
struct Copyable : std::enable_shared_from_this<Copyable> {};

int main() {
    auto s = std::make_shared<Session>();
    std::printf("use_count = %ld\n", s->shared_from_this().use_count());   // 2

    Session local;                                        // 不被 shared_ptr 拥有
    try { (void)local.shared_from_this(); }
    catch (const std::bad_weak_ptr&) { std::puts("stack object: bad_weak_ptr"); }

    auto h = std::make_shared<Hidden>();
    std::printf("private base: %d\n", h->ok());           // 0

    auto c1 = std::make_shared<Copyable>();
    auto c2 = std::make_shared<Copyable>(*c1);
    std::printf("c2 owns itself: %d\n", c2->shared_from_this() == c2);   // 1
}
```

本机输出依次是：`in ctor: bad_weak_ptr`、`use_count = 2`、`in ctor: bad_weak_ptr`（`local` 的构造）、`stack object: bad_weak_ptr`、`private base: 0`、`c2 owns itself: 1`。下面逐一解释。

典型的使用场景是异步 I/O：会话对象把指向自己的 `shared_ptr` 捕获进回调，保证回调执行时会话还活着。直接写 `shared_ptr<Session>(this)` 会新建一个所有权组，与外面已有的那一组各自删除一次对象（[[util.smartptr.shared]]）。需要的是与已有所有者共享同一个控制块的 `shared_ptr`。

## 接口 [util.smartptr.enab]

¶1 类 `T` 可以继承 `enable_shared_from_this<T>`，从而继承成员函数 `shared_from_this`，用它取得指向 `*this` 的 `shared_ptr`。这是 CRTP 写法：基类以派生类作模板实参。¶2 例 1 中，`p->shared_from_this()` 返回的 `q` 与 `p` 相等，并且 `p.owner_equal(q)`。

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
  constexpr weak_ptr<T>       weak_from_this() noexcept;
  constexpr weak_ptr<T const> weak_from_this() const noexcept;
private:
  mutable weak_ptr<T> weak-this;  // exposition only
};
```

特殊成员函数都是 `protected` 的，所以它只能作为基类使用。¶3 `T` 可以是不完整类型，在 `struct X : enable_shared_from_this<X>` 中，基类实例化时 `X` 确实还不完整。

¶7 `shared_from_this()` 返回 `shared_ptr<T>(weak-this)`，¶8 `weak_from_this()` 返回 *weak-this*。

## weak-this 由谁设置

`enable_shared_from_this` 自己从不写 *weak-this*。写它的是 `shared_ptr` 的构造函数，规则是 [[util.smartptr.shared]] 中的“启用 shared_from_this”（[util.smartptr.shared.const] ¶1）：如果 `Y` 有一个无歧义且可访问的基类是 `enable_shared_from_this` 的特化，并且 `p->weak-this` 已过期，就令 `p->weak-this` 与这个新的 `shared_ptr` 共享所有权。会这样做的只有创建新所有权组的途径：

- `shared_ptr(Y* p)`、`shared_ptr(Y* p, D d)`、`shared_ptr(Y* p, D d, A a)`，且 `T` 不是数组；
- `shared_ptr(unique_ptr<Y, D>&&)`，它等价于前两者之一；
- `make_shared`、`allocate_shared`（[util.smartptr.shared.create] ¶10）。

别名构造、复制以及从 `weak_ptr` 构造都不会设置 *weak-this*，它们没有创建新的所有权组。

### 未被拥有时：抛出 bad_weak_ptr

¶7 的写法决定了失败时的行为：从过期的 `weak_ptr` 构造 `shared_ptr` 会抛出 `bad_weak_ptr`（[util.smartptr.shared.const] ¶27）。所以对一个不被任何 `shared_ptr` 拥有的对象调用 `shared_from_this()`，结果是抛出 `bad_weak_ptr`。`weak_from_this()` 则返回一个空的 `weak_ptr`，不抛异常。

C++17 的 [[P0033R1]] 确立了这一行为，并加入了 `weak_from_this()`。在 C++11 和 C++14 中，`shared_from_this()` 有一个前置条件：必须存在一个拥有 `*this` 的 `shared_ptr`，违反它是 UB。

构造函数里调用 `shared_from_this()` 一定失败：对象还没构造完，`make_shared` 或 `shared_ptr` 的构造函数还没走到设置 *weak-this* 那一步。需要在创建时把自己注册到别处的类，可以用私有构造函数加静态工厂函数：工厂先 `make_shared`，再调用一个 `init()` 完成注册。析构函数里也一样，那时强计数已经归零，*weak-this* 已经过期。

### 复制不传递 weak-this（¶4–¶6）

¶4 默认构造和复制构造都值初始化 *weak-this*，也就是让它为空。¶5–¶6 复制赋值返回 `*this`，注 1 指出 *weak-this* 不变。

这是必要的。对象的副本是一个新对象，它的所有者（如果有）与原对象无关。如果 *weak-this* 被复制，副本的 `shared_from_this()` 会返回指向原对象的 `shared_ptr`，类型对了，地址却错了。上例中 `c2` 从 `*c1` 复制构造，`c2->shared_from_this()` 正确地等于 `c2`。

## 陷阱

### 私有继承

“启用”的条件要求基类可访问（[[class.access.base]]）。`class X : enable_shared_from_this<X>` 是私有继承，`shared_ptr` 的构造函数看不到这个基类，于是静默地不设置 *weak-this*，没有任何诊断，`shared_from_this()` 永远抛异常。上例中的 `Hidden` 就是这样。基类要写成 `public`，或者用 `struct`。

### 两个 enable_shared_from_this 基类

```cpp run title="two-bases.cpp" impl
#include <memory>
#include <cstdio>
struct A : std::enable_shared_from_this<A> {};
struct B : std::enable_shared_from_this<B> {};
struct C : A, B {};
int main() {
    auto c = std::make_shared<C>();
    std::printf("A: %d B: %d\n", !c->A::weak_from_this().expired(),
                                 !c->B::weak_from_this().expired());
}
```

`C` 有两个不同的 `enable_shared_from_this` 特化基类，每一个单独看都无歧义且可访问。标准的措辞是“有一个这样的基类”，没有说明存在两个时怎么办。本机 libc++ 输出 `A: 0 B: 0`，两个都不设置。应当避免这种设计：通常只让最顶层的公共基类继承 `enable_shared_from_this`，派生类用 `std::static_pointer_cast<Derived>(shared_from_this())` 取得派生类型的指针。

C++23 的显式对象形参（[[dcl.fct]]）可以把这个转换写成一个通用的辅助函数，`Self` 会推导为调用者的实际类型：

```cpp run title="shared-from-self.cpp" ok
#include <memory>
#include <cstdio>
struct Base : std::enable_shared_from_this<Base> {
    template<class Self>
    auto shared_from(this Self& self) {
        return std::static_pointer_cast<Self>(self.shared_from_this());
    }
    virtual ~Base() = default;
};
struct Derived : Base { int v = 7; };
int main() {
    auto d = std::make_shared<Derived>();
    std::shared_ptr<Derived> p = d->shared_from();
    std::printf("%d %ld\n", p->v, d.use_count());   // 7 2
}
```

### 并发

设置 *weak-this* 的那次赋值不是原子的，与对同一对象的任何潜在并发访问冲突（[util.smartptr.shared.const] ¶1 最后一句）。如果对象的地址在交给 `shared_ptr` 之前就被另一个线程看到，那个线程调用 `weak_from_this()` 与构造 `shared_ptr` 构成数据竞争。

## 思考题

!!! question "思考题 1"
    `X` 继承了 `enable_shared_from_this<X>`。`auto p = std::shared_ptr<X>(new X); auto q = std::shared_ptr<X>(p.get());` 会发生什么？

<details markdown="1">
<summary>答案</summary>

仍然是双重删除的 UB。构造 `q` 时，`p->weak-this` 没有过期，所以不会被覆盖，但 `q` 照样新建了第二个控制块并拥有同一个对象。`enable_shared_from_this` 只提供了正确地再取一个 `shared_ptr` 的途径，不能阻止错误的途径。
</details>

!!! question "思考题 2"
    对 `const X` 对象调用 `shared_from_this()` 返回什么类型？*weak-this* 为什么是 `mutable` 的？

<details markdown="1">
<summary>答案</summary>

返回 `shared_ptr<const X>`。`shared_ptr<const X>(new const X)` 中 `Y` 是 `const X`，启用 shared_from_this 的语句通过 `const X*` 类型的 `p` 给 `p->weak-this` 赋值，只有 `mutable` 成员才能这样修改。同一条语句里的 `const_cast<remove_cv_t<Y>*>(p)` 则让新建的 `shared_ptr<X>` 能指向这个对象。
</details>

## 小结

- *weak-this* 由创建新所有权组的 `shared_ptr` 构造函数或 `make_shared` 设置，前提是基类无歧义且可访问。
- 未被拥有时，`shared_from_this()` 抛出 `bad_weak_ptr`（C++17 起），`weak_from_this()` 返回空。
- 构造函数和析构函数里都不能用 `shared_from_this()`。
- 复制构造和复制赋值都不传递 *weak-this*。
