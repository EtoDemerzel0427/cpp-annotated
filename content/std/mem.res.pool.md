---
title: 池资源
summary: synchronized_pool_resource 与 unsynchronized_pool_resource——按块大小分档的池，每个池由几何增长的 chunk 补充；超大请求直通上游；pool_options 的两个调节旋钮；析构时无论是否 deallocate 都全部归还
status: done
covers: *
related: mem.res, mem.res.class, mem.res.monotonic.buffer, mem.poly.allocator.class
tags: 标准库, pmr, 内存池
updated: 2026-10-18
---

池资源是 `pmr` 中的"通用"资源：与单调资源不同，它**会**复用被释放的块，适合频繁分配与释放大小相近对象的场景（节点式容器、对象池）。

## 概述（[mem.res.pool.overview]）

¶1 把 `synchronized_pool_resource` 与 `unsynchronized_pool_resource` 统称为**池资源类**（[[g:pool-resource-classes]]），并描述其特性：

- (1.1) 析构时释放其分配的**全部**内存，即使某些块从未被 `deallocate`。
- (1.2) 池资源由若干**池**（pool）组成，每个池服务一种块大小。每个池管理一组**chunk**，chunk 被切分成大小一致的**块**（block），`do_allocate` 返回的就是块。`do_allocate(size, alignment)` 被分派到"块大小不小于 `size` 的最小的池"。
- (1.3) 某个池耗尽时，从**上游分配器**（构造时提供）再要一个 chunk 来补充；每次补充的 chunk 大小**几何增长**。注 1：成块分配使连续的分配在内存中更可能彼此靠近。
- (1.4) 超过所有池最大块大小的请求**直接**由上游满足。
- (1.5) 可以向构造函数传入 `pool_options` 来调节最大块大小与最大 chunk 大小。

¶2：`synchronized_pool_resource` 可以被多个线程无外部同步地访问，并且**可以**使用线程专属的池来降低同步开销；`unsynchronized_pool_resource` 不得被多个线程同时访问，因此在单线程程序中完全没有同步开销。

```
请求 24 字节 ──▶ 32 字节池 ──▶ 空闲链表有块？──是──▶ 返回
                                │否
                                ▼
                     向上游要一个 chunk（每次更大），切成 32 字节的块
请求 2 MiB ──▶ 超过最大块大小 ──▶ 直接 upstream->allocate
```

!!! impl "libc++"
    libc++ 的 `synchronized_pool_resource` 只是 `unsynchronized_pool_resource` 外面加一把 `std::mutex`——没有使用标准允许的线程专属池。高并发场景下它会成为争用热点。池的块大小从 8 字节起按 2 的幂分档；默认最大块大小为 1 MiB，`max_blocks_per_chunk` 的上限是 2^20。

## `pool_options`（[mem.res.pool.options]）

```cpp
struct pool_options {
  size_t max_blocks_per_chunk = 0;
  size_t largest_required_pool_block = 0;
};
```

- ¶2 `max_blocks_per_chunk`：补充某个池时一次从上游分配的最大块数。为零或超过由实现定义的上限时，使用该上限。实现可以使用更小的值，并且可以对不同的池使用不同的值。
- ¶3 `largest_required_pool_block`：**要求**用池机制满足的最大分配大小；更大的单块请求直通上游。为零或超过由实现定义的上限时使用该上限。实现可以选择**更大**的直通阈值。

两个值都只是"提示"：`options()`（[mem.res.pool.mem] ¶3）返回实际生效的值，零被替换为由实现定义的默认值，大小可能按未指明的粒度取整：

```cpp title="pool-options.cpp" impl
#include <memory_resource>
#include <cstdio>
int main() {
    std::pmr::pool_options o{.max_blocks_per_chunk = 0, .largest_required_pool_block = 100};
    std::pmr::unsynchronized_pool_resource pool(o);
    auto got = pool.options();
    std::printf("max_blocks_per_chunk=%zu largest_required_pool_block=%zu\n",
                got.max_blocks_per_chunk, got.largest_required_pool_block);
    // 本机 libc++：max_blocks_per_chunk=1048576 largest_required_pool_block=128
}
```

## 构造与析构（[mem.res.pool.ctor]）

- `(const pool_options& opts, memory_resource* upstream)`（¶1–¶3）：*Preconditions* `upstream` 是有效资源的地址。资源保存 `upstream` 的副本，但**不拥有**它所指的资源（上游必须比池活得长）。注 1：意图是在大多数情况下，对 `upstream->allocate()` 的调用远少于对 `this->allocate()` 的调用。不抛出，除非 `upstream->allocate()` 抛出；构造函数是否、何时调用 `upstream->allocate()` 未指明（实现可以预分配，也可以延迟）。
- 其余构造函数委托给它，缺省的上游是 `get_default_resource()`，缺省的选项是 `pool_options()`。
- 析构函数（¶4）：调用 `release()`。复制被弃置。

## 成员（[mem.res.pool.mem]）

- `release()`（¶1）：根据需要调用 `upstream_resource()->deallocate()` 释放全部已分配内存。注 1：即使某些块尚未被 `deallocate`，内存也会还给上游——与单调资源一样，池资源可以充当"整体释放"的 arena；但与单调资源不同，`release()` 之后不能保证复用到同一批地址。
- `upstream_resource()`、`options()`（¶2–¶3）。
- `do_allocate(bytes, alignment)`（¶4–¶6）：选中的池无法从内部数据结构满足请求时调用 `upstream_resource()->allocate()`；`bytes` 超过最大池的能力时直接从上游分配。返回至少 `bytes` 大小、满足 [[mem.res.class]] 对齐要求的存储。不抛出，除非上游抛出。
- `do_deallocate`（¶7–¶8）：把内存还给池。**是否、何时**因此调用 `upstream_resource()->deallocate()` 未指明——实现通常把块挂回空闲链表而不还给上游，只有超大块（直通上游的那些）会立即归还。不抛出。
- `do_is_equal`（¶9）：`this == &other`。

由于 `do_deallocate` 需要知道块属于哪个池，池资源**依赖**调用者传回正确的 `bytes`（与对齐）——这正是 [[mem.res.class]] 中 `do_deallocate` 前置条件要求大小匹配的意义。

## 选择指南

| 场景 | 选择 |
|---|---|
| 一批对象、一起死、很少单独释放 | [[mem.res.monotonic.buffer]] |
| 大量同尺寸对象反复分配释放，单线程 | `unsynchronized_pool_resource` |
| 同上但多线程共享 | `synchronized_pool_resource`（或每线程一个 `unsynchronized` 池） |
| 既要复用、又要上游分配极快 | `unsynchronized_pool_resource` 叠在 `monotonic_buffer_resource` 之上 |

## 小结

- 池按块大小分档，每档由几何增长的 chunk 补充；超大请求直通上游。
- `pool_options` 的两个值只是提示，`options()` 报告实际生效值。
- 析构与 `release()` 归还全部内存；`deallocate` 一般只把块放回空闲链表。
- `synchronized` 版本线程安全（libc++ 实现为单把互斥锁），`unsynchronized` 版本零同步开销。
