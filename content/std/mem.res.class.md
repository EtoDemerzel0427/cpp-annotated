---
title: memory_resource
summary: 所有 pmr 内存资源的抽象基类：公有的非虚接口转调私有虚函数；allocate 会隐式创建对象；释放时必须传回与分配时相同的大小和对齐；is_equal 表示两个资源能否互相释放对方分配的内存。
status: done
covers: *
related: mem.res, mem.poly.allocator.class, mem.res.pool, mem.res.monotonic.buffer, intro.object, basic.stc.dynamic.allocation, class.virtual
tags: 标准库, pmr, memory_resource, NVI
papers: P0593R6
updated: 2026-10-19
---

!!! tldr
    - 自定义资源只需派生 `memory_resource`，覆盖三个私有虚函数 `do_allocate`、`do_deallocate`、`do_is_equal`。
    - 公有的 `allocate` 除了转调 `do_allocate`，还在分配到的区域里隐式创建对象，所以结果可以像 `malloc` 的返回值一样直接使用。
    - `deallocate` 必须收到与分配时相同的大小和对齐，资源可以据此不保存任何元数据。
    - `do_allocate` 失败时必须抛出异常，不能返回空指针。
    - 两个资源相等，意思是一方分配的内存可以由另一方释放。

## 一个自定义资源

```cpp run title="tracing-resource.cpp" ok
#include <memory_resource>
#include <vector>
#include <string>
#include <cstdio>
#include <cstddef>

class tracing_resource : public std::pmr::memory_resource {
  std::pmr::memory_resource* up_;
  void* do_allocate(std::size_t n, std::size_t a) override {
    std::printf("  allocate(%zu, %zu)\n", n, a);
    return up_->allocate(n, a);
  }
  void do_deallocate(void* p, std::size_t n,
                     std::size_t a) override {
    std::printf("  deallocate(%zu, %zu)\n", n, a);
    up_->deallocate(p, n, a);
  }
  bool do_is_equal(const memory_resource& o)
      const noexcept override {
    return this == &o;
  }
public:
  explicit tracing_resource(std::pmr::memory_resource* up =
                                std::pmr::get_default_resource())
      : up_(up) {}
};

int main() {
  std::byte buf[256];
  tracing_resource tr;                       // 打印每次向上游要的内存
  std::pmr::monotonic_buffer_resource mono(buf, sizeof buf, &tr);
  std::pmr::vector<std::pmr::string> v(&mono);
  std::puts("push_back x3:");
  for (int i = 0; i < 3; ++i)
    v.emplace_back("a string long enough to need the heap");
  std::puts("scope end:");
}
```

本机输出：

```text
push_back x3:
  allocate(544, 8)
scope end:
  deallocate(544, 8)
```

三次插入加上三个字符串各自的缓冲区，只向 `tr` 要了一次内存。`pmr::string` 也从 `mono` 分配，这是 `polymorphic_allocator::construct` 做 uses-allocator 构造的结果（[[allocator.uses]]）。栈上的 256 字节用完之后，单调资源向上游要了一块 544 字节的内存，作用域结束时 `mono` 析构，一次性还回去。544 这个数值取决于 libc++ 单调资源的增长策略和簿记开销，由实现决定。

`tracing_resource` 只覆盖了三个私有虚函数，`vector` 和 `string` 调用的却是公有的 `allocate` 和 `deallocate`。下面解释这个结构。

## 公有接口与私有虚函数 [mem.res.class.general]

¶1 `memory_resource` 是一个抽象接口，对应一个无界的类集合，每个类封装一种内存资源。

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

这是**非虚接口**（non-virtual interface，NVI）模式：公有函数不是虚函数，它们转调私有的纯虚函数。派生类可以覆盖基类的私有虚函数，因为覆盖与访问控制无关（[[class.virtual]]），只是不能直接调用它。这样基类可以在公有函数里统一附加语义，派生类无法绕过，`allocate` 附加的隐式创建对象就是例子。

基类本身可以复制，但标准提供的具体资源类（池资源、单调资源）都把复制弃置了。

## 公有成员函数 [mem.res.public]

!!! std "[mem.res.public]/2"
    *Effects*: Allocates storage by calling `do_allocate(bytes, alignment)` and implicitly creates objects within the allocated region of storage.

¶2 `allocate` 调用 `do_allocate` 分配存储，并在分配到的区域里**隐式创建对象**（implicitly create objects，[[g:implicitly-create-objects]]）：如果某些隐式生存期类型的对象能让程序的行为有定义，这些对象就在此刻开始存在（[[intro.object]]）。¶3 它返回指向其中一个合适的已创建对象的指针。¶4 它抛出 `do_allocate` 抛出的异常。

这条语义来自 C++20 的 [[P0593R6]]。派生类的 `do_allocate` 只需返回一块原始内存，可以来自栈上的缓冲区，也可以来自池；基类保证调用者拿到的指针可以像 `malloc` 的结果一样直接用来存放 `int` 数组之类的隐式生存期类型。

¶5 `deallocate` 等价于 `do_deallocate(p, bytes, alignment)`，¶6 `is_equal` 等价于 `return do_is_equal(other);`。

## 派生类的义务 [mem.res.private]

### do_allocate（¶1–¶3）

¶1 前置条件是 `alignment` 为 2 的幂。¶2 派生类必须返回一块已分配的存储（[[basic.stc.dynamic.allocation]]），大小至少 `bytes`，按 `alignment` 对齐。¶3 无法满足时必须抛出适当的异常。返回空指针不是表示失败的合法方式。

### do_deallocate（¶4–¶6）

!!! std "[mem.res.private]/4"
    *Preconditions*: `p` was returned from a prior call to `allocate(bytes, alignment)` on a memory resource equal to `*this`, and the storage at `p` has not yet been deallocated.

¶4 `p` 必须来自之前在一个与 `*this` 相等的资源上、以相同的 `bytes` 和 `alignment` 调用的 `allocate`，而且还没有被释放。违反这一点是 UB。

大小和对齐都必须与分配时一致，所以资源不必在每个块前面记录大小：池资源直接用 `bytes` 找到对应的池（[[mem.res.pool]]）。`std::allocator::deallocate` 也要求大小一致，`memory_resource` 还要求对齐一致。¶5 派生类负责处置这块存储，¶6 不得抛出异常。

### do_is_equal（¶7）

¶7 派生类必须在从 `*this` 分配的内存可以由 `other` 释放、反之亦然时返回 `true`，否则返回 `false`。注 1 提醒，`other` 的最派生类型可能与 `*this` 不同；派生类 `D` 的实现可以在 `dynamic_cast<const D*>(&other) == nullptr` 时立即返回 `false`。

对大多数有状态的资源，能互相释放就意味着是同一个对象，标准的池资源和单调资源都返回 `this == &other`。

## 相等 [mem.res.eq]

¶1 `operator==(a, b)` 返回 `&a == &b || a.is_equal(b)`，先比较地址，省去一次虚函数调用。`polymorphic_allocator` 的相等最终归结到这里（[[mem.poly.allocator.class]]）。容器移动赋值和交换时能否直接交出内部缓冲区，取决于两个资源是否相等（[[allocator.traits]]）。

## 思考题

!!! question "思考题"
    一个资源的 `do_allocate` 按 16 字节对齐分配所有请求，忽略 `alignment` 参数。`allocate(64, 64)` 会出什么问题？

<details markdown="1">
<summary>答案</summary>

¶2 要求返回的存储按 `alignment` 对齐，这个 `do_allocate` 违反了派生类的义务。调用者会在只有 16 字节对齐的地址上放置要求 64 字节对齐的对象，结果是未定义行为，在使用对齐 SIMD 指令的代码里可能直接崩溃。正确的做法是满足任意 2 的幂的对齐，或者对无法满足的对齐抛出异常（¶3）。
</details>

## 小结

- 公有非虚的 `allocate`、`deallocate`、`is_equal` 转调私有纯虚的 `do_*`。
- `allocate` 隐式创建对象（C++20），结果可以像 `malloc` 的返回值一样直接使用。
- `do_allocate` 失败时必须抛出异常；`do_deallocate` 要求大小、对齐与分配时相同，且来自相等的资源。
- `is_equal` 的含义是能否互相释放；`operator==` 先比较地址。
