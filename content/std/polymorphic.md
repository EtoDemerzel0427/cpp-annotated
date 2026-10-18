---
title: polymorphic
summary: C++26 的 polymorphic<T>：持有 T 或其派生类对象、复制时保留动态类型的值语义包装——取代 unique_ptr<Base> + 虚 clone()；构造约束为何要求派生类可复制，移动为何允许不"偷指针"，以及为何没有比较运算
status: done
covers: *
since: c++26
related: mem.composite.types, indirect, allocator.traits, unique.ptr, class.virtual, class.copy.ctor
tags: 标准库, polymorphic, 值语义, 类型擦除, C++26
papers: P3019R14
updated: 2026-10-18
---

`polymorphic<T, Allocator = allocator<T>>` 解决的是一个老问题：类里有一个多态成员，希望外层类可复制。

```cpp
struct Shape { virtual ~Shape() = default; virtual double area() const = 0;
               virtual std::unique_ptr<Shape> clone() const = 0; };   // 每个派生类都要实现
struct Scene {
    std::vector<std::unique_ptr<Shape>> shapes;
    Scene(const Scene& o) { for (auto& s : o.shapes) shapes.push_back(s->clone()); }  // 手写深拷贝
    // 还要手写复制赋值……
};
```

`polymorphic<Shape>` 在构造时记住了实际类型 `U`，复制时调用 `U` 的复制构造函数——**不需要**基类提供虚 `clone()`，也不需要外层类手写复制操作。设计动机与 `indirect` 的共性见 [[mem.composite.types]]。

## 概述（[polymorphic.general]）

- ¶1：`polymorphic` 对象管理一个被拥有对象的生命周期，**在其生命周期的不同时刻可以拥有不同类型的对象**（赋值可改变动态类型）。无值、只有被移动后才可能无值——与 [[indirect]] 相同。
- ¶2：`allocator_traits<Allocator>::value_type` 必须是 `T`。
- ¶3：以分配器 `a` 构造 `U` 类型的被拥有对象，指调用 `allocator_traits<Allocator>::construct(a, p, args...)`，其中 `p` 指向适合 `U` 的存储。注意 `Allocator` 的 `value_type` 是 `T`，而构造的是 `U`——实现需要把分配器重绑定到包含 `U` 的控制块类型。
- ¶4：分配器只能通过赋值或 `swap` 替换，规则同容器。
- ¶5–¶8：与 `indirect` 相同的类型限制；`T` 可以不完整；禁止特化。

说明用的数据成员只有 `Allocator alloc`——标准刻意不规定内部表示。实现通常存一个指向"控制块"的指针，控制块里放被拥有对象以及一组类型擦除的操作（复制、销毁），概念上与 `shared_ptr` 的控制块类似，但没有引用计数。

## 构造（[polymorphic.ctor]）

¶2：除非 `allocate` 或 `construct` 抛出，否则不抛出。

### 默认构造（¶3–¶7）

*Mandates*：`T` 可默认构造**且可复制构造**。构造一个 `T`。所以 `polymorphic<AbstractBase>` 的默认构造函数不可用（抽象类不可默认构造）——必须从具体派生类构造。

### 从值或就地构造（¶12–¶23）

```cpp
template<class U = T> explicit polymorphic(U&& u);
template<class U, class... Ts> explicit polymorphic(in_place_type_t<U>, Ts&&... ts);
```

令 `UU = remove_cvref_t<U>`，*Constraints* 包括：

- `derived_from<UU, T>`：必须是 `T` 本身或其派生类（[[concept.derived]]，要求公有且无歧义的派生）；
- `is_copy_constructible_v<UU>`：**派生类必须可复制**——因为 `polymorphic` 的复制要调用 `UU` 的复制构造函数，而这个调用是在构造时就被"记录"进类型擦除的操作表里的；
- `UU` 不是 `polymorphic` 本身、不是 `in_place_type_t` 的特化；
- `in_place_type_t<U>` 版本还要求 `U` 是 cv 无限定的非引用类型（`is_same_v<remove_cvref_t<U>, U>`）——被拥有对象必须是 cv 无限定对象类型。

这里用的是 *Constraints*（参与重载决议），而不是像默认构造那样的 *Mandates*：派生类型 `U` 在构造点必然是完整的。

### 复制构造（¶8–¶9）

*alloc* 取 `select_on_container_copy_construction(other.alloc)`；`other` 无值则 `*this` 无值；否则**构造一个类型为 `U` 的被拥有对象，`U` 是 `other` 中被拥有对象的类型**，以该对象为实参。复制构造函数**没有** *Mandates*——可复制性已经在 `other` 被构造时由 *Constraints* 保证了。

!!! note "不会切片"
    复制时用的是**动态类型** `U` 的复制构造函数，不是 `T` 的。若 `T` 的复制构造函数是公有的，`polymorphic<T>` 也不会退化为"只复制基类部分"。[[LWG4532]] 修正了此处旧措辞中容易被误读为切片的写法。

### 移动构造（¶10–¶11）

¶10：`polymorphic(polymorphic&& other) noexcept`：

!!! std "[polymorphic.ctor]/10"
    … either `*this` takes ownership of the owned object of `other` or, owns an object of the same type constructed from the owned object of `other` considering that owned object as an rvalue, using the allocator *alloc*.

    要么 `*this` 接管 `other` 的被拥有对象，要么拥有一个以 `other` 的被拥有对象（视为右值）构造的、同类型的新对象。

这个"要么……要么"是给**小对象优化**（small buffer optimization）留的空间：实现可以把小的、移动不抛异常的对象直接存在 `polymorphic` 对象内部，移动时就只能移动构造而不能偷指针。注意 `indirect` 的移动构造没有这个选项（它总是偷指针、`other` 总是变为无值）；而 `polymorphic` 移动构造的规范**没有**"`other` 变为无值"的后置条件——走小对象路径时 `other` 仍有值（只是处于被移动后的状态）。移动构造无条件 `noexcept`，所以实现只能把移动构造不抛异常的类型放进小缓冲区。

带分配器的移动（¶11）：分配器相等时同样"接管或移动构造"；不等时用 *alloc* 以右值构造一个 `U`。`noexcept(is_always_equal)`。

## 析构（[polymorphic.dtor]）

¶1 *Mandates*：`T` 完整。¶2：若非无值，调用 `allocator_traits<Allocator>::destroy(p)`，其中 `p` 是 `U*`——**按动态类型销毁**，所以 `T` 的析构函数**不需要是虚的**。这与 `shared_ptr` 一样（构造时捕获类型），与 `unique_ptr<Base>` 不同。

## 赋值（[polymorphic.assign]）

### 复制赋值（¶1–¶4）

*Mandates*：`T` 完整。与 `indirect` 不同，它**总是**"先构造后销毁"：

- (2.2) `other` 非无值时，用 `allocator_traits::construct` 构造一个 `U`（`other` 的动态类型）的新对象（使用 `*this` 或在需要更新时 `other` 的分配器）；
- (2.3) 销毁并释放旧对象；(2.4) 必要时替换分配器。
- ¶4：抛出异常时 `*this` 无效果——**强异常保证**。

为什么不像 `indirect` 那样在可能时直接对被拥有对象赋值？因为两个对象的**动态类型可能不同**，`*this` 里是 `Circle`、`other` 里是 `Square`，没有可调用的赋值运算符。统一采用"构造新的、销毁旧的"既简单又给出强保证。

### 移动赋值（¶5–¶8）

`noexcept(POCMA || is_always_equal)`；*Mandates*：POCMA 与 `is_always_equal` 都为假时 `T` 完整。分配器需要更新或相等时接管 `other` 的对象；否则以右值构造一个新的 `U`。¶8：抛异常时 `*this` 与 `other` 都无效果。

`polymorphic` **没有**从值赋值的 `operator=(U&&)`：要换一个新对象，写 `p = polymorphic<T>(std::in_place_type<Square>, ...)`。

## 观察器（[polymorphic.obs]）

`operator*` 返回 `T&` / `const T&`（只有 const 与非 const 两个重载，**没有**引用限定的右值重载——从 `polymorphic` "移出"一个 `T` 会切片）；`operator->` 返回 `pointer`/`const_pointer`；前置条件：非无值。`valueless_after_move()`、`get_allocator()` 同 `indirect`。const 传播同样成立。

## 交换（[polymorphic.swap]）

`noexcept(POCS || is_always_equal)`；分配器不等且不传播时是 {{ub}}；交换状态而不对被拥有对象调用 `swap`。（在小对象优化的实现中，"交换状态"可能需要移动构造对象。）

## 没有比较与散列

`indirect` 可以委托 `T` 的 `==` 与 `<=>`，`polymorphic` 不行：两个对象的动态类型可能不同，基类的 `operator==` 只能比较基类部分，结果多半是错的。标准选择不提供，而不是提供一个可能误导的版本。

## 示例

```cpp title="polymorphic-scene.cpp" ok
#include <memory>
#include <vector>
#include <cassert>

struct Shape {                                  // 不需要虚 clone()，析构函数也可以不是虚的
    virtual double area() const = 0;
protected:
    ~Shape() = default;
};
struct Circle : Shape { double r; explicit Circle(double r) : r(r) {} double area() const override { return 3 * r * r; } };
struct Square : Shape { double a; explicit Square(double a) : a(a) {} double area() const override { return a * a; } };

struct Scene {
    std::vector<std::polymorphic<Shape>> shapes;   // 隐式复制构造/赋值即为深拷贝
};

int main() {
    Scene s;
    s.shapes.emplace_back(std::in_place_type<Circle>, 1.0);
    s.shapes.emplace_back(Square(2.0));
    Scene t = s;                                     // 每个元素按其动态类型复制
    static_cast<Square&>(*t.shapes[1]).a = 3.0;
    assert(s.shapes[1]->area() == 4.0 && t.shapes[1]->area() == 9.0);
}
```

（本机 libc++ 尚未实现 `std::polymorphic`，此例未在本地编译验证。）

## 思考题

<details markdown="1">
<summary>1. `polymorphic<Shape> p(Circle{1});` 之后 `polymorphic<Shape> q = std::move(p);`，`p.valueless_after_move()` 一定为真吗？</summary>

不一定。移动构造（¶10）允许实现选择"以右值移动构造一个同类型的新对象"，此时 `p` 仍拥有一个（被移动过的）`Circle`。标准没有给移动构造写"`other` 无值"的后置条件。只有在实现选择接管指针（不使用小对象优化、或对象太大）时才无值。可移植代码不应依赖移动后 `p` 的有值/无值状态，只应假定它可以被赋值或析构。
</details>

<details markdown="1">
<summary>2. 为什么 `polymorphic` 的默认构造函数要求 `T` 可复制构造，而从派生类构造要求派生类可复制构造？</summary>

`polymorphic` 无条件提供复制构造函数，并且不在复制时检查可复制性（复制构造函数没有 *Mandates*）。为保证"任何有值的 `polymorphic` 都可以被复制"这一不变式，必须在**对象进入 `polymorphic` 的那一刻**确认其动态类型可复制——默认构造时动态类型是 `T`，从 `U` 构造时动态类型是 `U`。
</details>

## 小结

- `polymorphic<T>` 持有 `T` 或其公有派生类，复制按**动态类型**进行，不需要虚 `clone()`，析构不需要虚析构函数。
- 派生类必须可复制（构造时以 *Constraints* 检查）。
- 移动构造允许"接管或移动构造"，为小对象优化留出空间；移动后 `other` 未必无值。
- 复制赋值总是"先构造后销毁"，提供强异常保证；没有从值赋值、没有比较与散列。
