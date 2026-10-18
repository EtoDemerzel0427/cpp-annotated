---
title: monotonic_buffer_resource
summary: 只增不减的 bump 分配器——deallocate 是空操作，内存只在 release() 或析构时一次性还给上游；可以从用户提供的初始缓冲区（如栈数组）开始，按几何级数向上游要新块
status: done
covers: *
related: mem.res, mem.res.class, mem.res.pool, ptr.align, mem.poly.allocator.class
tags: 标准库, pmr, arena, monotonic_buffer_resource
updated: 2026-10-18
---

`monotonic_buffer_resource` 是"区域分配器"（arena / bump allocator）的标准版本。¶1（[mem.res.monotonic.buffer.general]）：它是为**极快的分配**设计的特殊用途资源，适用于"用内存构建少量对象、然后在资源对象销毁时一次性全部释放"的场景。典型用途：处理一个请求、解析一份文档、一帧渲染——期间产生大量小对象，结束时整体丢弃。

## 模型

说明用的数据成员揭示了全部机制：

```cpp
memory_resource* upstream_rsrc;   // 上游：缓冲区用完时向它要新块
void*            current_buffer;  // 当前正在切分的缓冲区
size_t           next_buffer_size;// 下次向上游要多大
```

分配就是在 `current_buffer` 里**移动指针**（加上对齐调整，参见 [[ptr.align]] 的 `std::align`）；放不下时向上游要一块更大的新缓冲区。释放什么都不做。

## 构造与析构（[mem.res.monotonic.buffer.ctor]）

三个"主"构造函数（其余委托给它们，以 `get_default_resource()` 作为上游）：

- `explicit monotonic_buffer_resource(memory_resource* upstream)` 与 `(size_t initial_size, memory_resource* upstream)`（¶1–¶2）：*Preconditions* `upstream` 是有效资源的地址，`initial_size`（若给出）大于零。效果：`current_buffer = nullptr`；`next_buffer_size` 至少为 `initial_size`，未给出时为**由实现定义**的大小。注意构造时**不分配**——第一次 `allocate` 才向上游要内存。
- `(void* buffer, size_t buffer_size, memory_resource* upstream)`（¶3–¶4）：*Preconditions* `buffer_size` 不大于 `buffer` 中的字节数。效果：`current_buffer = buffer`，`next_buffer_size = buffer_size`（但不小于 1），然后乘以一个**由实现定义的增长因子**（不必是整数）。这是"从栈数组开始"的用法。
- 析构（¶5）：调用 `release()`。

复制构造与复制赋值都被弃置——资源有身份，不可复制。

## 成员（[mem.res.monotonic.buffer.mem]）

- `release()`（¶1–¶2）：根据需要调用 `upstream_rsrc->deallocate()` 释放所有已分配内存；把 `current_buffer` 与 `next_buffer_size` **重置为构造时的初值**。注 1：即使从 `*this` 分配的某些块尚未被释放，内存也会还给上游。
- `upstream_resource()`（¶3）。
- `do_allocate(bytes, alignment)`（¶4–¶6）：若 `current_buffer` 中未用空间能放下一个满足大小与对齐的块，就从中分配；否则令 `current_buffer = upstream_rsrc->allocate(n, m)`，其中 `n` 不小于 `max(bytes, next_buffer_size)`、`m` 不小于 `alignment`，并把 `next_buffer_size` 乘以增长因子，再从新缓冲区分配。不抛出，除非上游抛出。
- `do_deallocate`（¶7–¶9）：**无效果**；不抛出。¶9：此资源使用的内存单调增长，直到销毁。
- `do_is_equal`（¶10）：`this == &other`。

### `release()` 之后初始缓冲区可以复用

`release()` 把状态重置为"构造时的初值"——如果构造时给了用户缓冲区，`current_buffer` 又指回它。所以在循环里反复 `release()` 一个以栈数组起步的资源，可以做到稳态零堆分配：

```cpp title="monotonic-loop.cpp" ok
#include <memory_resource>
#include <vector>
#include <string>
#include <cstdio>

int main() {
    std::byte buf[4096];
    std::pmr::monotonic_buffer_resource arena(buf, sizeof buf, std::pmr::null_memory_resource());
    for (int frame = 0; frame < 3; ++frame) {
        {
            std::pmr::vector<std::pmr::string> names(&arena);
            for (int i = 0; i < 5; ++i) names.emplace_back("some name that is not short at all");
        }                       // names 先析构（deallocate 都是空操作）
        arena.release();        // 再整体复位：下一帧重新从 buf 开头分配
        std::printf("frame %d ok\n", frame);
    }
}
```

上游是 `null_memory_resource()`：若某一帧超过 4096 字节就会抛 `bad_alloc`，而不是悄悄落到堆上。注意顺序：必须先让所有使用者析构，再 `release()`——否则使用者持有的指针会指向被"回收"后再次分配出去的内存。

## 何时**不**该用它

单调资源的 `deallocate` 什么都不做，这对"不断增删"的数据结构是灾难：

- `vector` 扩容时旧缓冲区不会被回收，`push_back` N 次累计占用约 2N 个元素的空间（按 2 倍增长）；
- 长生命周期、频繁插入删除的 `map` 或 `list` 会无限增长。

这类场景应当用池资源（[[mem.res.pool]]），或者在单调资源之上叠一个池资源：`unsynchronized_pool_resource pool(&monotonic);`——池负责复用，单调资源负责快速批量获取上游内存。

!!! impl "libc++"
    libc++ 的默认初始大小是 1024 字节；每次向上游要的块末尾放一个 `__chunk_footer`（记录链表指针、起始地址、当前位置、对齐），`release()` 沿链表逐块归还；块内分配是**从高地址向低地址**切分的。以 256 字节的用户缓冲区起步时，本机观察到第一次向上游请求 544 字节（512 字节的下一块加上块尾簿记结构，见 [[mem.res.class]] 中的跟踪示例），即增长因子为 2。

## 小结

- 分配 = 指针前移；释放 = 空操作；内存只在 `release()`/析构时整体归还。
- 可以从用户缓冲区（栈数组）起步；`release()` 后回到初始缓冲区，可循环复用。
- 下一块大小按由实现定义的增长因子几何增长。
- 不适合频繁增删的长寿数据结构；需要复用时在其上叠池资源。
