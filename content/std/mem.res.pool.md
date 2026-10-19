---
title: 池资源
summary: synchronized_pool_resource 与 unsynchronized_pool_resource：按块大小分成若干池，池耗尽时从上游取一块越来越大的内存来补充，超大请求直接交给上游；pool_options 的两个参数只是提示；析构时归还全部内存。
status: done
covers: *
related: mem.res, mem.res.class, mem.res.monotonic.buffer, mem.poly.allocator.class
tags: 标准库, pmr, 内存池
updated: 2026-10-19
---

!!! tldr
    - 池资源会复用释放的块，适合反复分配和释放大小相近的对象，例如节点式容器。
    - 每个池服务一种块大小，请求交给能容纳它的最小的池；池耗尽时从上游取一块内存，每次取得的块按几何级数变大；超过最大块大小的请求直接交给上游。
    - `pool_options` 的两个参数只是提示，`options()` 返回实际生效的值。
    - 析构或 `release()` 时，所有内存都还给上游，不管是否 `deallocate` 过。
    - `synchronized_pool_resource` 可以被多个线程同时使用，`unsynchronized_pool_resource` 没有同步开销。

## 池资源怎样工作 [mem.res.pool.overview]

¶1 `synchronized_pool_resource` 和 `unsynchronized_pool_resource` 合称**池资源类**（pool resource classes，[[g:pool-resource-classes]]），它们是通用的内存资源，具有以下性质：

- ¶1.2 一个池资源由若干**池**（pool）组成，每个池服务一种块大小。每个池管理一组 **chunk**，chunk 再切分成大小一致的**块**（block），`do_allocate` 返回的就是块。`do_allocate(size, alignment)` 交给块大小至少为 `size` 的池中最小的那一个。
- ¶1.3 某个池耗尽时，从构造时提供的**上游分配器**（upstream allocator）再分配一个 chunk 补充它。每次补充，chunk 的大小按几何级数增长。注 1 指出，成块地分配让连续的分配更可能在内存中彼此靠近。
- ¶1.4 超过所有池的最大块大小的请求，直接由上游满足。
- ¶1.5 可以给构造函数传入 `pool_options`，调节最大块大小和 chunk 的最大大小。
- ¶1.1 资源析构时释放它分配的全部内存，即使有些块从未被 `deallocate`。

```text
请求 24 字节 → 32 字节的池 → 空闲链表里有块？ → 有：返回
                                   ↓ 没有
                    向上游要一个更大的 chunk，切成 32 字节的块
请求 2 MiB  → 超过最大块大小 → 直接 upstream->allocate
```

¶2 `synchronized_pool_resource` 可以被多个线程无需外部同步地访问，并且可以使用线程专属的池来降低同步开销。`unsynchronized_pool_resource` 不能被多个线程同时访问，因此单线程程序完全不用付出同步的代价。

!!! impl "libc++"
    libc++ 的 `synchronized_pool_resource` 是在 `unsynchronized_pool_resource` 外面加一把 `std::mutex`，每次分配和释放都加锁，没有使用标准允许的线程专属池。高并发时它可能成为争用热点，可以考虑每个线程使用一个 `unsynchronized_pool_resource`。

## pool_options [mem.res.pool.options]

```cpp
struct pool_options {
  size_t max_blocks_per_chunk = 0;
  size_t largest_required_pool_block = 0;
};
```

¶2 `max_blocks_per_chunk` 是补充一个池时一次从上游分配的最大块数。为零或超过由实现定义的上限时，使用这个上限。实现可以使用更小的值，也可以对不同的池使用不同的值。

¶3 `largest_required_pool_block` 是要求用池机制满足的最大分配大小，单块大于这个阈值的请求直接交给上游。为零或超过由实现定义的上限时，使用这个上限。实现可以选择更大的直通阈值。

两个值都只是提示。[mem.res.pool.mem] ¶3 规定，`options()` 返回实际控制池行为的值：零会被替换为由实现定义的默认值，大小可能按未指定的粒度取整。

```cpp run title="pool-options.cpp" impl
#include <memory_resource>
#include <cstdio>
int main() {
  std::pmr::pool_options o{.max_blocks_per_chunk = 0,
                           .largest_required_pool_block = 100};
  std::pmr::unsynchronized_pool_resource pool(o);
  auto got = pool.options();
  std::printf("max_blocks_per_chunk=%zu largest_required_pool_block=%zu\n",
              got.max_blocks_per_chunk, got.largest_required_pool_block);
}
```

本机 libc++ 输出 `max_blocks_per_chunk=1048576 largest_required_pool_block=128`：零被替换为上限 2^20，100 被向上取整到 128。不传选项时，libc++ 的 `largest_required_pool_block` 是 1048576，即 1 MiB。

## 构造与析构 [mem.res.pool.ctor]

¶1 构造函数 `(const pool_options& opts, memory_resource* upstream)` 的前置条件是 `upstream` 指向一个有效的内存资源。¶2 池资源在自己的数据结构无法满足请求时向 `upstream` 要内存。它保存 `upstream` 的副本，但不拥有它所指的资源，所以上游必须比池资源活得长。注 1 说明设计意图：在大多数情况下，对 `upstream->allocate()` 的调用应当远少于对 `this->allocate()` 的调用。

¶3 构造函数除非 `upstream->allocate()` 抛出，否则不抛出；它是否、在什么条件下调用 `upstream->allocate()` 是未指定的，实现可以预先分配，也可以推迟到第一次分配时。

其余三个构造函数都委托给这一个，缺省的上游是 `get_default_resource()`，缺省的选项是 `pool_options()`。复制构造和复制赋值被弃置。¶4 析构函数调用 `release()`。

## 成员函数 [mem.res.pool.mem]

¶1 `release()` 根据需要调用 `upstream_resource()->deallocate()`，释放全部已分配的内存。注 1 强调，即使有些块还没有 `deallocate`，内存也会还给上游。所以池资源也可以当作整体释放的 arena 使用。

¶2 `upstream_resource()` 返回构造时传入的上游，¶3 `options()` 见上文。

¶4–¶6 `do_allocate(bytes, alignment)`：选中的池无法用自己的数据结构满足请求时，调用 `upstream_resource()->allocate()` 取得更多内存；`bytes` 超过最大的池能处理的大小时，直接从上游分配。返回的存储至少有 `bytes` 字节，大小和对齐满足 [[mem.res.class]] 对派生类的要求。除非上游抛出，否则不抛出。

¶7–¶8 `do_deallocate` 把内存还给池。它是否、在什么情况下导致调用 `upstream_resource()->deallocate()` 是未指定的。实现通常只把块挂回空闲链表，只有直接从上游分配的大块才立即归还。不抛出。

`do_deallocate` 靠调用者传回的 `bytes` 找到块所属的池，所以池资源依赖 [[mem.res.class]] 中大小必须与分配时一致的前置条件。传错大小是 UB，典型的后果是块被挂到错误的池里，之后的分配返回大小不对的内存。

¶9 `do_is_equal` 返回 `this == &other`。

## 选择哪种资源

| 场景 | 选择 |
|---|---|
| 一批对象一起创建、一起销毁，很少单独释放 | [[mem.res.monotonic.buffer]] |
| 大量大小相近的对象反复分配释放，单线程 | `unsynchronized_pool_resource` |
| 同上，但多个线程共享 | `synchronized_pool_resource`，或者每个线程一个 `unsynchronized_pool_resource` |
| 既要复用块，又要上游分配极快 | `unsynchronized_pool_resource` 以 `monotonic_buffer_resource` 为上游 |

## 小结

- 池按块大小分档，每档由按几何级数变大的 chunk 补充；超大请求直接交给上游。
- `pool_options` 的两个值只是提示，`options()` 报告实际生效的值。
- 析构和 `release()` 归还全部内存；`deallocate` 一般只把块放回空闲链表。
- `synchronized_pool_resource` 线程安全（libc++ 用一把互斥锁实现），`unsynchronized_pool_resource` 没有同步开销。
