---
title: polymorphic
summary: C++26 的 polymorphic<T>：持有 T 或其派生类的对象，复制时按动态类型复制，取代 unique_ptr<Base> 加虚 clone()；构造时为何要求派生类可复制，移动后为何不一定无值，以及为何没有比较运算。
status: draft
covers: *
since: c++26
related: mem.composite.types, indirect, allocator.traits, unique.ptr, class.virtual, class.copy.ctor
tags: 标准库, polymorphic, 值语义, 类型擦除, C++26
papers: P3019R14
updated: 2026-10-19
---

!!! tldr
    - `polymorphic<T>` 持有 `T` 或其公有派生类的对象。复制时调用实际类型的复制构造函数，不会切片，也不需要基类提供虚 `clone()`。
    - 销毁时按实际类型销毁，`T` 的析构函数不必是虚的。
    - 放进 `polymorphic` 的类型必须可复制，这一点在构造时就以 *Constraints* 检查。
    - 移动构造允许实现不接管指针而是移动构造一个新对象，为小对象优化留出空间，所以被移动的对象不一定无值。
    - 复制赋值总是先构造后销毁，给出强异常保证；没有从值赋值，也没有比较和散列。

## 一个老问题

类里有一个多态成员，又希望外层类可以复制，传统写法是这样的：

```cpp
struct Shape {
    virtual ~Shape() = default;
    virtual double area() const = 0;
    virtual std::unique_ptr<Shape> clone() const = 0;   // 每个派生类都要实现
};
struct Scene {
    std::vector<std::unique_ptr<Shape>> shapes;
    Scene(const Scene& o) {                             // 手写深复制
        for (auto& s : o.shapes) shapes.push_back(s->clone());
    }
    // 还要手写复制赋值
};
```

用 `polymorphic<Shape>` 改写：

```cpp
#include <memory>
#include <vector>

struct Shape {                       // 不需要 clone()，析构函数也可以不是虚的
    virtual double area() const = 0;
protected:
    ~Shape() = default;
};
struct Circle : Shape {
    double r;
    explicit Circle(double r) : r(r) {}
    double area() const override { return 3 * r * r; }
};
struct Square : Shape {
    double a;
    explicit Square(double a) : a(a) {}
    double area() const override { return a * a; }
};

struct Scene {
    std::vector<std::polymorphic<Shape>> shapes;   // 隐式复制即为深复制
};

int main() {
    Scene s;
    s.shapes.emplace_back(std::in_place_type<Circle>, 1.0);
    s.shapes.emplace_back(Square(2.0));
    Scene t = s;                                   // 每个元素按动态类型复制
    static_cast<Square&>(*t.shapes[1]).a = 3.0;
    // s.shapes[1]->area() == 4.0，t.shapes[1]->area() == 9.0
}
```

`polymorphic<Shape>` 在构造时记住了实际类型，复制时调用那个类型的复制构造函数。截至写作时本机 libc++ 尚未实现 `std::polymorphic`，这段代码没有经过编译验证。设计动机及与 [[indirect]] 的共同点见 [[mem.composite.types]]。

## 概述 [polymorphic.general]

¶1 `polymorphic` 对象管理一个被拥有对象的生命周期，在生命周期的不同时刻可以拥有不同类型的对象，例如赋值可以把 `Circle` 换成 `Square`。没有被拥有对象时是无值的，只有被移动之后才可能无值，这与 [[indirect]] 相同。

¶2 `allocator_traits<Allocator>::value_type` 必须是 `T`。¶3 以分配器 `a` 构造类型为 `U` 的被拥有对象，指调用 `allocator_traits<Allocator>::construct(a, p, args...)`，其中 `p` 指向适合 `U` 的存储。分配器的 `value_type` 是 `T`，构造的却是 `U`，所以实现要把分配器重绑定到包含 `U` 的内部类型上。

¶4 分配器只能通过赋值或 `swap` 替换，规则同容器（[[allocator.traits]]）。¶5–¶8 与 `indirect` 相同：`T` 不能是非对象类型、数组、`in_place_t`、`in_place_type_t` 的特化或 cv 限定类型；`T` 可以不完整；声明特化是 UB。

说明用的数据成员只有 `Allocator alloc`，标准刻意不规定内部表示。实现通常存一个指向控制块的指针，控制块里放被拥有对象和一组类型擦除的操作（复制、销毁），概念上与 `shared_ptr` 的控制块相似，但没有引用计数。

## 构造 [polymorphic.ctor]

¶2 所有构造函数除非 `allocate` 或 `construct` 抛出，否则不抛出。

### 默认构造（¶3–¶7）

*Mandates*：`T` 可默认构造，并且可复制构造。效果是构造一个 `T`。抽象类不能默认构造，所以 `polymorphic<Shape>` 的默认构造函数不能用，必须从一个具体的派生类构造。

### 从值或就地构造（¶12–¶23）

```cpp
template<class U = T> explicit polymorphic(U&& u);
template<class U, class... Ts> explicit polymorphic(in_place_type_t<U>, Ts&&... ts);
```

令 `UU = remove_cvref_t<U>`，*Constraints* 包括：

- `derived_from<UU, T>`：必须是 `T` 本身或其派生类，[[concept.derived]] 要求公有且无歧义的派生；
- `is_copy_constructible_v<UU>`：派生类必须可复制；
- `UU` 不是 `polymorphic` 本身，也不是 `in_place_type_t` 的特化；
- `in_place_type_t<U>` 版本还要求 `U` 不带 cv 限定、不是引用，即 `is_same_v<remove_cvref_t<U>, U>`。

为什么构造时就要求可复制？`polymorphic` 无条件地提供复制构造函数，而复制构造函数（¶8）没有任何 *Mandates*。要保证任何有值的 `polymorphic` 都能被复制，就必须在对象进入 `polymorphic` 时确认它的动态类型可复制：默认构造时动态类型是 `T`，所以 ¶4 要求 `T` 可复制；从 `U` 构造时动态类型是 `U`，所以这里要求 `U` 可复制。

这里用 *Constraints* 而不是 *Mandates*，是因为在构造点上派生类型 `U` 必然是完整的，不需要为不完整类型让步。

### 复制构造（¶8–¶9）

¶8 分配器取 `select_on_container_copy_construction(other.alloc)`；`other` 无值则结果无值；否则构造一个类型为 `U` 的被拥有对象，`U` 是 `other` 中被拥有对象的类型，以那个对象为实参。用的是动态类型 `U` 的复制构造函数，而不是 `T` 的，所以即使 `T` 有公有的复制构造函数也不会切片。

### 移动构造（¶10–¶11）

!!! std "[polymorphic.ctor]/10"
    … either `*this` takes ownership of the owned object of `other` or, owns an object of the same type constructed from the owned object of `other` considering that owned object as an rvalue, using the allocator *alloc*.

¶10 移动构造有两种允许的结果：接管 `other` 的被拥有对象，或者以它为右值移动构造一个同类型的新对象。后一种是给小对象优化（small buffer optimization）留的余地：实现可以把小的对象直接存在 `polymorphic` 内部，这样的对象移动时就只能移动构造，不能接管指针。

所以 `polymorphic` 的移动构造没有 `other` 变为无值的后置条件，这一点与 `indirect` 不同。走小对象路径时，`other` 仍然有值，只是对象处于被移动后的状态。移动构造无条件 `noexcept`，因此实现只能把移动构造不抛异常的类型放进内部缓冲区。

¶11 带分配器的移动构造：分配器相等时同样是接管或移动构造二选一；不等时用 *alloc* 以右值构造一个新的 `U`。它的 `noexcept` 取决于 `is_always_equal`。

## 析构 [polymorphic.dtor]

¶1 *Mandates*：`T` 完整。¶2 如果不是无值，以指向被拥有对象的 `U*` 调用 `allocator_traits<Allocator>::destroy`，`U` 是被拥有对象的类型，然后释放存储。按动态类型销毁，所以 `T` 的析构函数不需要是虚的，上例中 `Shape` 的析构函数甚至是 `protected` 的。这与 `shared_ptr` 一样在构造时记住了类型，与 `unique_ptr<Base>` 不同。

## 赋值 [polymorphic.assign]

### 复制赋值（¶1–¶4）

¶1 *Mandates*：`T` 完整。与 `indirect` 不同，它总是先构造后销毁：

- ¶2.2 `other` 不是无值时，用 `allocator_traits::construct` 构造一个类型为 `U`（`other` 的动态类型）的新对象，使用 `*this` 的分配器，需要更新时用 `other` 的；
- ¶2.3 销毁并释放原来的对象；¶2.4 需要更新时替换分配器。
- ¶4 抛出异常时 `*this` 没有变化，这是强异常保证。

`indirect` 在分配器相等时会直接对被拥有对象赋值，`polymorphic` 不能这样做：`*this` 里可能是 `Circle`，`other` 里可能是 `Square`，没有可以调用的赋值运算符。

### 移动赋值（¶5–¶8）

`noexcept(POCMA || is_always_equal)`，其中 POCMA 指分配器的 `propagate_on_container_move_assignment`。¶5 两者都为假时 *Mandates* 要求 `T` 完整。¶6 分配器需要更新或两者相等时，接管 `other` 的对象；否则以右值构造一个新的 `U`。¶8 抛出异常时 `*this` 和 `other` 都没有变化。

`polymorphic` 没有从值赋值的 `operator=(U&&)`。要换成一个新对象，写 `p = std::polymorphic<Shape>(std::in_place_type<Square>, 2.0);`。

## 观察器与交换 [polymorphic.obs] [polymorphic.swap]

¶1–¶4 `operator*` 返回 `T&` 或 `const T&`，`operator->` 返回 `pointer` 或 `const_pointer`，前置条件是不处于无值状态，`const` 同样会传播。它没有 `indirect` 那样的右值重载，因为从 `polymorphic` 里移出一个 `T` 会切片。¶5 `valueless_after_move()` 和 ¶6 `get_allocator()` 与 `indirect` 相同。

交换（[polymorphic.swap]）的规则也与 `indirect` 相同：`noexcept(POCS || is_always_equal)`；分配器不相等又不传播时是 UB；交换状态，不对被拥有对象调用 `swap`。在使用小对象优化的实现中，交换状态可能需要移动构造对象。

## 没有比较和散列

`indirect` 可以把 `==` 和 `<=>` 委托给 `T`，`polymorphic` 不行。两个对象的动态类型可能不同，基类的 `operator==` 只能比较基类部分，结果多半是错的。标准选择不提供，而不是提供一个容易误导的版本。

## 思考题

!!! question "思考题"
    `std::polymorphic<Shape> p(std::in_place_type<Circle>, 1.0);` 之后执行 `std::polymorphic<Shape> q = std::move(p);`，`p.valueless_after_move()` 一定为真吗？

<details markdown="1">
<summary>答案</summary>

不一定。¶10 允许实现以右值移动构造一个同类型的新对象，此时 `p` 仍然拥有一个被移动过的 `Circle`，标准也没有给移动构造写 `other` 无值的后置条件。只有实现选择接管指针时 `p` 才是无值的。可移植的代码不应依赖移动后 `p` 是否有值，只应假定它可以被赋值或销毁。
</details>

## 小结

- `polymorphic<T>` 持有 `T` 或其公有派生类的对象，按动态类型复制和销毁，不需要虚 `clone()`，也不需要虚析构函数。
- 进入 `polymorphic` 的类型必须可复制，构造时以 *Constraints* 检查。
- 移动构造可以接管指针，也可以移动构造新对象，所以移动后不一定无值。
- 复制赋值总是先构造后销毁，给出强异常保证；没有从值赋值，也没有比较和散列。
