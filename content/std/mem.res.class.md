---
title: memory_resource
summary: 抽象类 memory_resource 的契约——公有非虚接口 + 私有虚函数（NVI）；allocate 隐式创建对象；do_deallocate 必须收到与分配时相同的大小与对齐；is_equal 的含义是"能否互相释放"
status: done
covers: *
related: mem.res, mem.poly.allocator.class, mem.res.pool, mem.res.monotonic.buffer, intro.object, basic.stc.dynamic.allocation, class.virtual
tags: 标准库, pmr, memory_resource, NVI
updated: 2026-10-18
---

`memory_resource` 是 `std::pmr` 的根：所有内存资源都派生自它，`polymorphic_allocator` 只认识它。

## 概述（[mem.res.class.general]）

¶1：`memory_resource` 是一个面向"无界的、封装内存资源的类集合"的抽象接口。

```cpp
class memory_resource {
  static constexpr size_t max_align = alignof(max_align_t);   // exposition only
public:
  memory_resource() = default;
  memory_resource(const memory_resource&) = default;
  virtual ~memory_resource();
  memory_resource& operator=(const memory_resource&) = default;

  void* allocate(size_t bytes, size_t alignment = max_align);
  void deallocate(void* p, size_t bytes, size_t alignment = max_align);
  bool is_equal(const memory_resource& other) const noexcept;

private:
  virtual void* do_allocate(size_t bytes, size_t alignment) = 0;
  virtual void do_deallocate(void* p, size_t bytes, size_t alignment) = 0;
  virtual bool do_is_equal(const memory_resource& other) const noexcept = 0;
};
```

这是教科书式的**非虚接口**（NVI）模式：公有的 `allocate` 等是非虚函数，转调私有的纯虚 `do_*`。派生类覆盖私有虚函数——C++ 允许覆盖基类的私有虚函数（访问控制与覆盖无关，[[class.virtual]]），只是不能直接调用它。好处是基类可以在公有函数里统一附加语义，而派生类无法绕过——下面会看到，`allocate` 正是在这里附加了"隐式创建对象"。

注意它可复制（默认的复制构造与复制赋值），但具体的资源类（池、单调缓冲）都把复制弃置了。

## 公有成员函数（[mem.res.public]）

### `allocate`（¶2–¶4）

!!! std "[mem.res.public]/2"
    Effects: Allocates storage by calling `do_allocate(bytes, alignment)` and implicitly creates objects within the allocated region of storage.

    通过调用 `do_allocate(bytes, alignment)` 分配存储，并在所分配的区域内**隐式创建对象**。

¶3：返回指向该区域中一个合适的已创建对象的指针（[[intro.object]]）。¶4：抛出 `do_allocate` 抛出的异常。

"隐式创建对象"这条附加语义（C++20 起）就是 NVI 的价值：任何派生类的 `do_allocate` 只需返回一块原始内存，基类保证调用者拿到的指针可以像 `malloc` 的结果一样直接使用——无论派生类内部是从栈缓冲区切出来的、还是从池里取的。没有这条，`pmr` 容器对隐式生存期类型做的指针算术在严格意义上就没有依据（[[g:implicitly-create-objects]]）。

### `deallocate`、`is_equal`（¶5–¶6）

等价于对应的 `do_*` 调用。

## 私有虚函数（[mem.res.private]）

### `do_allocate`（¶1–¶3）

- ¶1 *Preconditions*：`alignment` 是 2 的幂。
- ¶2：派生类须返回指向**已分配存储**（[[basic.stc.dynamic.allocation]]）的指针，大小至少 `bytes`，按 `alignment` 对齐。
- ¶3：无法满足时须抛出适当的异常。**不能返回空指针**表示失败。

### `do_deallocate`（¶4–¶6）

!!! std "[mem.res.private]/4"
    Preconditions: p was returned from a prior call to `allocate(bytes, alignment)` on a memory resource equal to `*this`, and the storage at p has not yet been deallocated.

    `p` 必须来自之前在一个**与 `*this` 相等**的资源上、以**相同的** `bytes` 与 `alignment` 调用的 `allocate`，且尚未被释放。

与 `std::allocator::deallocate` 一样，大小必须匹配；此外对齐也必须匹配。违反是 {{ub}}。这使得资源可以不存任何元数据：池资源用 `bytes` 直接定位到对应的池（[[mem.res.pool]]），从不需要在块头记录大小。¶6：不抛出。

### `do_is_equal`（¶7）

派生类须在"**从 `*this` 分配的内存可以由 `other` 释放、反之亦然**"时返回 `true`。注 1：`other` 的最派生类型可能与 `*this` 不同；派生类 `D` 的实现可以在 `dynamic_cast<const D*>(&other) == nullptr` 时立即返回 `false`。

对大多数有状态的资源，"可以互相释放"就等于"是同一个对象"——标准的池资源与单调资源都返回 `this == &other`。

## 相等（[mem.res.eq]）

`operator==(a, b)` 返回 `&a == &b || a.is_equal(b)`——先比较地址作为快速路径。`polymorphic_allocator` 的相等最终归结到这里，因此容器的移动赋值与 `swap` 是否需要逐元素操作，取决于两个资源是否相等（[[allocator.traits]]）。

## 自定义资源示例

```cpp title="tracing-resource.cpp" ok
#include <memory_resource>
#include <vector>
#include <string>
#include <cstdio>
#include <cstddef>

// 一个记录调用的资源：转发给上游
class tracing_resource : public std::pmr::memory_resource {
    std::pmr::memory_resource* up_;
    void* do_allocate(std::size_t n, std::size_t a) override {
        std::printf("  allocate(%zu, %zu)\n", n, a);
        return up_->allocate(n, a);
    }
    void do_deallocate(void* p, std::size_t n, std::size_t a) override {
        std::printf("  deallocate(%zu, %zu)\n", n, a);
        up_->deallocate(p, n, a);
    }
    bool do_is_equal(const memory_resource& o) const noexcept override { return this == &o; }
public:
    explicit tracing_resource(std::pmr::memory_resource* up = std::pmr::get_default_resource()) : up_(up) {}
};

int main() {
    std::byte buf[256];
    tracing_resource tr;                                   // 上游：打印每次向堆要内存
    std::pmr::monotonic_buffer_resource mono(buf, sizeof buf, &tr);
    std::pmr::vector<std::pmr::string> v(&mono);
    std::puts("push_back x3:");
    for (int i = 0; i < 3; ++i) v.emplace_back("a string long enough to need the heap");
    std::puts("scope end:");
}   // vector 析构时对 mono 的 deallocate 是空操作；mono 析构时把向 tr 要的块一次性还回去
```

本机输出：三次 `push_back`（加上三个字符串各自的缓冲区——`pmr::string` 也从 `mono` 分配，见 [[allocator.uses]]）只触发了**一次** `allocate(544, 8)`——栈上 256 字节用尽后向上游要了一块；作用域结束时一次 `deallocate(544, 8)`。`544` 是 libc++ 单调资源下一块的大小（按增长因子放大后再加上块尾的簿记结构），具体数值由实现定义。

## 小结

- NVI：公有非虚 `allocate`/`deallocate`/`is_equal` 转调私有纯虚 `do_*`。
- `allocate` 隐式创建对象（C++20），结果像 `malloc` 一样可直接使用。
- `do_allocate` 失败须抛异常、不得返回空；`do_deallocate` 要求大小与对齐都与分配时相同，且资源相等。
- `is_equal` 的含义是"可以互相释放"；`operator==` 先比较地址。
