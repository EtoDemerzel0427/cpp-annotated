---
title: monotonic_buffer_resource
summary: 标准库的区域分配器：分配只是在缓冲区里移动指针，释放什么也不做，内存在 release() 或析构时一次性还给上游资源。
status: done
covers: *
related: mem.res, mem.res.class, mem.res.pool, ptr.align, mem.poly.allocator.class
tags: 标准库, pmr, arena, monotonic_buffer_resource
updated: 2026-10-19
---

!!! tldr
    - `monotonic_buffer_resource` 的分配是在当前缓冲区里把指针往前移，`deallocate` 什么也不做。
    - 缓冲区用完时，它向上游资源要一块更大的新缓冲区，大小按实现定义的倍数增长。
    - 内存只在 `release()` 或析构时整体还给上游；`release()` 之后又从构造时的初始缓冲区开始。
    - 它适合处理一个请求、一帧画面这类先建一批对象、再整体丢弃的场景，不适合反复增删的长寿容器。

## 用法：一帧一清的分配器

```cpp title="monotonic-loop.cpp" run ok
#include <memory_resource>
#include <vector>
#include <string>
#include <cstdio>

int main() {
    std::byte buf[4096];
    std::pmr::monotonic_buffer_resource arena(
        buf, sizeof buf, std::pmr::null_memory_resource());
    for (int frame = 0; frame < 3; ++frame) {
        {
            std::pmr::vector<std::pmr::string> names(&arena);
            for (int i = 0; i < 5; ++i)
                names.emplace_back("some name that is not short at all");
        }                       // names 先析构（deallocate 都是空操作）
        arena.release();        // 再整体复位：下一帧重新从 buf 开头分配
        std::printf("frame %d ok\n", frame);
    }
}
```

每一帧里，`vector` 和各个 `string` 都从栈上的 `buf` 切出内存，整个循环不碰堆。上游是 `null_memory_resource()`（任何分配都抛 `bad_alloc` 的资源），所以一旦某一帧超过 4096 字节，程序会抛异常，而不是悄悄落到堆上。

顺序很重要：必须先让所有使用者析构，再调用 `release()`。否则使用者手里的指针会指向已经被收回、随后又分给别人的内存。

这类分配器通常叫**区域分配器**（arena allocator）或 bump allocator。[mem.res.monotonic.buffer.general] ¶1 说明了它的定位：一种为极快分配设计的特殊用途资源，用在先用内存建起少量对象、资源对象销毁时再一次性全部释放的场合。

## 内部模型

标准用三个说明用的数据成员描述它的状态：

```cpp
memory_resource* upstream_rsrc;    // 上游：缓冲区用完时向它要新块
void*            current_buffer;   // 当前正在切分的缓冲区
size_t           next_buffer_size; // 下次向上游要多大
```

分配就是在 `current_buffer` 的剩余空间里按对齐要求找一块，再把指针前移（对齐调整的做法见 [[ptr.align]] 的 `std::align`）。放不下时向上游要一块新缓冲区。释放什么也不做。

## 构造与析构 [mem.res.monotonic.buffer.ctor]

除了三个主构造函数，类里还有三个省略 `upstream` 的版本，它们以 `get_default_resource()` 作为上游。复制构造和复制赋值都是弃置的，资源对象有身份，不能复制。

¶1 第一组构造函数是 `(upstream)` 和 `(initial_size, upstream)`。前置条件是 `upstream` 指向一个有效的资源，给出的 `initial_size` 大于零。

¶2 它们把 `current_buffer` 设为空，把 `next_buffer_size` 设为至少 `initial_size`；没有给出时用一个实现定义的大小。构造时不分配内存，第一次 `allocate` 才向上游要。

¶3 第二组是 `(buffer, buffer_size, upstream)`，用调用者提供的内存起步。前置条件要求 `buffer_size` 不超过 `buffer` 实际的字节数。

¶4 它把 `current_buffer` 设为 `buffer`，把 `next_buffer_size` 设为 `buffer_size`（至少为 1），然后乘以一个实现定义的**增长因子**，这个因子不必是整数。所以第一次向上游要的块已经比初始缓冲区大。

¶5 析构函数调用 `release()`。

## 成员 [mem.res.monotonic.buffer.mem]

### 分配（¶4–¶6）

¶4 如果 `current_buffer` 的剩余空间放得下所需的大小和对齐，就从中分配。否则令 `current_buffer = upstream_rsrc->allocate(n, m)`，其中 `n` 不小于 `max(bytes, next_buffer_size)`，`m` 不小于 `alignment`；再把 `next_buffer_size` 乘以增长因子，然后从新缓冲区分配。

旧缓冲区里剩下的空间就此作废，不会回头再用。

¶5 返回的存储满足 [[mem.res.class]] 对所有派生资源的大小和对齐要求。¶6 只有上游的 `allocate` 抛出时，它才抛出。

### 释放（¶7–¶9）

¶7–¶8 `do_deallocate` 没有效果，也不抛出。¶9 因此这个资源占用的内存只增不减，直到它被销毁，这就是名字里 monotonic 的含义。

### `release()`（¶1–¶2）

¶1 `release()` 按需调用 `upstream_rsrc->deallocate()`，把向上游要来的所有内存还回去，并把 `current_buffer` 和 `next_buffer_size` 重置为构造时的初值。

如果构造时给了用户缓冲区，`current_buffer` 又指回它。开头的例子正是靠这一点做到每帧零堆分配。

¶2 注 1 强调，即使从 `*this` 分配出去的块还没有被归还，`release()` 也照样把内存还给上游。资源不跟踪哪些块还在用，这是调用者的责任。

### 其他（¶3、¶10）

¶3 `upstream_resource()` 返回 `upstream_rsrc`。¶10 `do_is_equal` 只在两者是同一个对象时返回真，所以从一个单调资源分配的内存不能交给另一个单调资源释放。

## 什么时候不该用它

`deallocate` 什么也不做，对不断增删的数据结构是个问题：

- `vector` 扩容时旧缓冲区不会被回收。按 2 倍增长，`push_back` N 次累计占用约 2N 个元素的空间。
- 长期存在、频繁插入删除的 `map` 或 `list` 会无限增长。

这类场景应当用池资源（[[mem.res.pool]]），或者在单调资源之上叠一个池资源，例如 `unsynchronized_pool_resource pool(&arena);`。池负责复用释放掉的块，单调资源负责快速地成批获取内存。

!!! impl "libc++ 的做法"
    本机 Clang 23 + libc++ 中，增长因子是 2。每块向上游要来的内存末尾放一个 32 字节的簿记结构，记录链表指针等信息，`release()` 沿链表逐块归还。

    用一个打印请求的上游资源观察到：以 256 字节的用户缓冲区起步，前两次向上游请求 544 和 1056 字节（512、1024 加上簿记结构）；默认构造的资源把初始大小当作 1024，第一次请求 2080 字节。`release()` 之后的下一次小分配又回到了用户缓冲区，没有向上游请求。

## 小结

| 操作 | 行为 |
|---|---|
| 分配 | 在当前缓冲区里前移指针；放不下就向上游要更大的一块 |
| 释放 | 什么也不做 |
| `release()` / 析构 | 把上游给的内存全部还回去，状态回到构造时 |
| 初始缓冲区 | 可以由调用者提供（如栈数组），`release()` 后再次使用 |
