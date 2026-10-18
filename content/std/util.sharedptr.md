---
title: 共享所有权指针总览
summary: shared_ptr/weak_ptr 的物理模型——两字指针 + 控制块（强计数、弱计数、删除器、分配器），make_shared 的单次分配及其代价；线程安全保证到底覆盖什么；bad_weak_ptr
status: done
covers: util.smartptr.weak.bad
related: smartptr, util.smartptr.shared, util.smartptr.weak, util.smartptr.enab, util.smartptr.ownerless, util.smartptr.atomic, intro.races, unique.ptr
tags: 标准库, 智能指针, shared_ptr, 控制块, 线程安全, ABI
papers: P0718R2
updated: 2026-10-18
---

[util.sharedptr] 下有七个子条款：`bad_weak_ptr`、`shared_ptr`、`weak_ptr`、`owner_less`、`owner_hash`、`owner_equal`、`enable_shared_from_this`。标准正文以"所有权""共享所有权"等抽象概念描述它们，从不提"引用计数"或"控制块"——但不理解这个物理模型，几乎无法读懂这些条款的设计。本页先建立模型，再讲本节唯一的独立小节 [util.smartptr.weak.bad]；各类模板的逐段解读见：

- [[util.smartptr.shared]]：`shared_ptr` 的构造、别名构造、`make_shared`、类型转换；
- [[util.smartptr.weak]]：`weak_ptr` 与 `lock`；
- [[util.smartptr.ownerless]]：`owner_less`、`owner_hash`、`owner_equal`；
- [[util.smartptr.enab]]：`enable_shared_from_this`。

## 物理模型：两个指针 + 一个控制块

标准里的"所有权组"（ownership group）——一组彼此"共享所有权"的 `shared_ptr` 与 `weak_ptr`——在所有实现中都对应**一个控制块**（control block）。一个 `shared_ptr` 对象是两个指针：

```
shared_ptr<T>           控制块（堆上）
┌─────────────┐         ┌──────────────────────────────┐
│ T* ptr      │──┐      │ vptr                          │
│ ctrl*       │──┼────▶ │ 强计数 (use_count)            │
└─────────────┘  │      │ 弱计数                        │
                 │      │ 删除器 D、分配器 A（类型擦除）│
                 │      │ [make_shared 时：T 对象本身]  │
                 └────▶ └──────────────────────────────┘
```

- **存储指针** `ptr`：`get()` 返回的值，解引用用的就是它。它**不一定**指向被拥有的对象（别名构造、指向基类子对象的转换）。
- **控制块**：记录强计数（有几个 `shared_ptr` 拥有）、弱计数（有几个 `weak_ptr`，通常再加 1 代表"强计数非零"）、**被拥有的指针**、删除器、分配器。
- 强计数归零时：调用删除器销毁被拥有的对象。弱计数归零时：释放控制块本身。

这个模型解释了标准里许多看似奇怪的规定：

| 标准条款 | 物理解释 |
|---|---|
| `shared_ptr<T>` 的 `T` 可以不完整，甚至是 `void` 或函数类型（[[util.smartptr.shared]] ¶3） | 删除器在**构造时**按实际类型捕获进控制块，析构 `shared_ptr` 时不需要知道 `T` |
| 存在"空但存储指针非空"的 `shared_ptr`（别名构造，¶17 注） | 控制块指针为空，存储指针非空 |
| `get_deleter` 返回的指针可能在最后一个 `shared_ptr` 销毁后仍有效（[[util.smartptr.getdeleter]] 注） | 删除器放在控制块里，实现可以等到弱计数归零再销毁它 |
| `owner_before` 与 `operator<` 不同 | 前者比较控制块地址，后者比较存储指针 |
| 构造 `shared_ptr(p)` 可能抛 `bad_alloc`，并且抛出时会 `delete p`（¶6、¶8） | 需要分配控制块；分配失败必须清理已接管的 `p` |

### libc++ 的实现

libc++ 的控制块基类是 `__shared_weak_count`（派生自 `__shared_count`）：

- 一个虚表指针，虚函数 `__on_zero_shared()`（强计数归零：销毁对象）、`__on_zero_shared_weak()`（弱计数归零：释放控制块）、`__get_deleter(const type_info&)`（实现 `get_deleter`，依赖 RTTI）；
- `long __shared_owners_` 与 `long __shared_weak_owners_`，两者都存"计数减一"——所以 `use_count()` 返回 `__shared_owners_ + 1`，新建的控制块计数字段为 0。

派生类按创建方式区分：`__shared_ptr_pointer<P, D, A>` 存放指针、删除器、分配器（由 `shared_ptr(p, d, a)` 等创建），`__shared_ptr_emplace<T, A>` 把 `T` 对象**直接内嵌**在控制块里（由 `make_shared`/`allocate_shared` 创建），数组版本另有专门的控制块。删除器和分配器用 `[[no_unique_address]]` 存放，空类型不占空间。

引用计数增加使用 `memory_order_relaxed`，减少使用 `memory_order_acq_rel`：增加时调用方已经持有一个引用，对象不可能被销毁，不需要同步；减少时，最后一次减少（归零者）必须"看到"其他线程通过它们的副本对对象所做的全部修改，才能安全地析构对象。

## `make_shared` 的单次分配

[[util.smartptr.shared]] 的 [util.smartptr.shared.create] ¶7.1 写道："实现**应当**最多执行一次内存分配"（注 1：这提供了与侵入式智能指针相当的效率）。`shared_ptr<T>(new T)` 需要两次分配——`new T` 一次，控制块一次；`make_shared<T>()` 把 `T` 嵌入控制块，只需一次：

```cpp title="make-shared-allocs.cpp" impl
#include <memory>
#include <cstdio>
#include <cstdlib>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) { ++allocs; if (void* p = std::malloc(n)) return p; throw std::bad_alloc(); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Big { char data[64]; };

int main() {
    allocs = 0; std::shared_ptr<Big> a(new Big);  std::printf("shared_ptr(new T): %d allocations\n", allocs);  // 2
    allocs = 0; auto b = std::make_shared<Big>(); std::printf("make_shared:       %d allocation\n", allocs);   // 1
    std::printf("sizeof(shared_ptr) = %zu, sizeof(weak_ptr) = %zu\n", sizeof a, sizeof(std::weak_ptr<Big>)); // 16, 16
}
```

单次分配的好处是少一次 `malloc`、对象与计数在同一缓存行附近。代价有两个：

1. **内存释放推迟。** `T` 与控制块在同一块内存里。强计数归零时 `T` 被**析构**，但只要还有 `weak_ptr` 存在，弱计数不为零，整块内存（包括 `T` 所占的字节）都不能释放。对大对象 + 长寿 `weak_ptr` 的缓存，这可能造成可观的内存滞留。
2. **无法自定义删除器**，也不能使用类的 `operator new`/`operator delete`（[util.smartptr.shared.create] ¶7.4 规定 `make_shared` 用 `::new(pv) U(...)` 构造）。需要定制分配时用 `allocate_shared`。

## 线程安全：标准保证了什么

[[util.smartptr.shared]] ¶5 是全部线程安全保证的来源：

!!! std "[util.smartptr.shared.general]/5"
    For purposes of determining the presence of a data race, member functions shall access and modify only the shared_ptr and weak_ptr objects themselves and not objects they refer to. Changes in use_count() do not reflect modifications that can introduce data races.

    在判断是否存在数据竞争时，成员函数应只访问和修改 `shared_ptr` 与 `weak_ptr` 对象本身，而不访问它们所指的对象。`use_count()` 的变化不被视为可能引入数据竞争的修改。

翻译成工程语言：

| 场景 | 是否数据竞争 |
|---|---|
| 两个线程各自复制、析构**不同的** `shared_ptr` 对象，哪怕它们共享同一个控制块 | **否**——引用计数的修改"不算"，实现必须用原子操作 |
| 两个线程同时**读**（复制、`get()`）**同一个** `shared_ptr` 对象 | 否（都是 const 操作，[[res.on.data.races]]） |
| 一个线程**写**（赋值、`reset`）同一个 `shared_ptr` 对象，另一个线程读或写它 | **是**——{{ub}} |
| 多个线程通过 `shared_ptr` 访问**被指对象** | 与 `shared_ptr` 无关，由被指对象自身决定 |

```cpp title="shared-ptr-race.cpp" ub
#include <memory>
#include <thread>
int main() {
    auto p = std::make_shared<int>(1);
    std::thread t([&] { for (int i = 0; i < 100000; ++i) { auto copy = p; } });   // 读 p
    for (int i = 0; i < 100000; ++i) p = std::make_shared<int>(i);                  // 写 p：数据竞争
    t.join();
}
```

本机 `-fsanitize=thread` 报告 "WARNING: ThreadSanitizer: data race"；在 `-fsanitize=address` 构建下它甚至直接以 SEGV 崩溃。这个竞争不只是"理论上的"：读线程可能读到新的存储指针和旧的控制块指针，或在复制旧控制块计数之前旧控制块已被写线程释放——经典的 use-after-free。

需要多个线程读写**同一个** `shared_ptr` 变量时，C++20 的做法是 `std::atomic<std::shared_ptr<T>>`（[[util.smartptr.atomic]]，[[P0718R2]]），它取代了 C++11 的自由函数 `atomic_load(&sp)`/`atomic_store(&sp, ...)`（C++20 弃用，C++26 移除）。截至写作时，本机 libc++ 尚未实现 `atomic<shared_ptr>`（`<version>` 中 `__cpp_lib_atomic_shared_ptr` 被注释掉）。

还有两个容易被忽略的细节：

- **`use_count()` 在多线程下只是近似值**（[util.smartptr.shared.obs] ¶17 注 3）：它用 relaxed 读取，`use_count() == 1` 并不意味着其他线程通过已销毁的 `shared_ptr` 进行的访问都已完成。用 `use_count() == 1` 判断"我是唯一拥有者，可以无锁修改对象"是错误的（这也是 C++20 移除 `unique()` 的原因之一）。
- **析构可能在任意线程发生**：最后一个 `shared_ptr` 在哪个线程被销毁，被拥有对象就在哪个线程析构。持有锁、线程局部状态或 GUI 线程亲和性的对象要特别小心。

## `bad_weak_ptr`（[util.smartptr.weak.bad]）

```cpp
class bad_weak_ptr : public exception {
public:
  constexpr const char* what() const noexcept override;
};
```

- ¶1：从 `weak_ptr` 构造 `shared_ptr` 的构造函数在 `weak_ptr` 已过期时抛出它（[util.smartptr.shared.const] ¶27）。`shared_from_this()` 正是通过这个构造函数实现的，所以对不被任何 `shared_ptr` 拥有的对象调用 `shared_from_this()` 也会抛出它（C++17 起；此前是 UB，见 [[util.smartptr.enab]]）。
- ¶2：`what()` 返回由实现定义的 NTBS。

`what()` 是 `constexpr` 的——这是 C++26 让 `shared_ptr` 全面 `constexpr`（[[P3037R6]]）的一部分：常量求值中也可能构造 `shared_ptr(weak_ptr)` 而抛出 `bad_weak_ptr`，C++26 同时允许常量求值中抛出与捕获异常。

注意 `weak_ptr::lock()` **不**抛异常：过期时返回空 `shared_ptr`。"从 `weak_ptr` 构造"与 "`lock()`" 的差别就在于失败时抛异常还是返回空。

## 思考题

<details markdown="1">
<summary>1. 一个 `shared_ptr<T>` 对象在 64 位平台上为什么是 16 字节，而不是像侵入式指针那样 8 字节？</summary>

因为存储指针与被拥有的指针**可以不同**（别名构造、到基类的转换会调整地址），只存控制块指针无法得到 `get()`——除非每次解引用都多一次间接访问。标准的接口（别名构造、`get()` 为 `noexcept` 的常量时间操作）实际上迫使实现存两个指针。
</details>

<details markdown="1">
<summary>2. `make_shared` 创建的对象被一个 `weak_ptr` 观察，最后一个 `shared_ptr` 销毁后，对象的析构函数会运行吗？内存会释放吗？</summary>

析构函数会运行（强计数归零 → `__on_zero_shared`）。内存不会释放：对象嵌在控制块里，控制块要等弱计数归零（`weak_ptr` 销毁）才释放。
</details>

## 小结

- 一个所有权组 = 一个控制块；`shared_ptr` = 存储指针 + 控制块指针（两个字）。
- 删除器在构造时按实际类型捕获，所以 `shared_ptr<Base>`/`shared_ptr<void>` 能正确销毁派生对象。
- `make_shared` 单次分配，但对象内存要等所有 `weak_ptr` 消失才释放。
- 线程安全：不同 `shared_ptr` 对象并发操作安全；同一对象的并发读写是数据竞争——用 `atomic<shared_ptr>`。
- `bad_weak_ptr` 由"从过期 `weak_ptr` 构造 `shared_ptr`"抛出；`lock()` 不抛。
