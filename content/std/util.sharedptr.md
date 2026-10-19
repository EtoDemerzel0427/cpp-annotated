---
title: 共享所有权指针总览
summary: shared_ptr 和 weak_ptr 背后的模型：两个指针加一个控制块；make_shared 的单次分配及其代价；标准的线程安全保证覆盖什么；以及 bad_weak_ptr。
status: done
covers: util.smartptr.weak.bad
related: smartptr, util.smartptr.shared, util.smartptr.weak, util.smartptr.enab, util.smartptr.ownerless, util.smartptr.atomic, intro.races, unique.ptr
tags: 标准库, 智能指针, shared_ptr, 控制块, 线程安全, ABI
papers: P0718R2, P3037R6
updated: 2026-10-19
---

!!! tldr
    - 共享同一个对象的所有 `shared_ptr` 和 `weak_ptr` 都指向同一个控制块，里面有强计数、弱计数和删除器；每个 `shared_ptr` 本身是两个指针。
    - 删除器在构造时按实际类型存进控制块，所以 `shared_ptr<Base>` 和 `shared_ptr<void>` 也能正确销毁派生类对象，`T` 可以不完整。
    - `make_shared` 把对象和控制块放在一次分配里；代价是只要还有 `weak_ptr`，这块内存就不能释放。
    - 不同的 `shared_ptr` 对象可以在不同线程里随意复制和销毁；并发读写同一个 `shared_ptr` 对象是数据竞争，要用 `atomic<shared_ptr<T>>`。
    - 从已过期的 `weak_ptr` 构造 `shared_ptr` 会抛出 `bad_weak_ptr`；`weak_ptr::lock()` 不抛异常，过期时返回空指针。

[util.sharedptr] 包含 `bad_weak_ptr`、`shared_ptr`、`weak_ptr`、`owner_less`、`owner_hash`、`owner_equal`、`enable_shared_from_this`。标准用所有权、共享所有权这些抽象概念描述它们，从不提引用计数或控制块，但不了解下面这个实现模型，很难理解这些条款为什么这样规定。各个类模板的逐段解读见：

- [[util.smartptr.shared]]：`shared_ptr` 的构造、别名构造、`make_shared`、类型转换；
- [[util.smartptr.weak]]：`weak_ptr` 和 `lock`；
- [[util.smartptr.ownerless]]：`owner_less`、`owner_hash`、`owner_equal`；
- [[util.smartptr.enab]]：`enable_shared_from_this`。

## 两个指针和一个控制块

```text
shared_ptr<T>           控制块（在堆上）
┌─────────────┐         ┌──────────────────────────────┐
│ T* ptr      │──┐      │ vptr                         │
│ ctrl*       │──┼────▶ │ 强计数 (use_count)           │
└─────────────┘  │      │ 弱计数                       │
                 │      │ 删除器 D、分配器 A（类型擦除）│
                 │      │ [make_shared 时：T 对象本身] │
                 └────▶ └──────────────────────────────┘
```

彼此共享所有权的一组 `shared_ptr` 和 `weak_ptr`，在所有实现中都对应一个**控制块**（control block）。一个 `shared_ptr` 对象存两个指针：

- **存储的指针** `ptr`：`get()` 返回它，解引用用的也是它。它不一定指向被拥有的对象，别名构造和转换到基类都会让它指向别处。
- **控制块指针**：控制块里有强计数（几个 `shared_ptr` 拥有这个对象）、弱计数（几个 `weak_ptr`，实现通常再加 1 表示强计数不为 0）、被拥有的指针、删除器和分配器。

强计数归零时，调用删除器销毁被拥有的对象；弱计数也归零时，释放控制块本身。

这个模型能解释标准里许多看起来奇怪的规定：

| 标准的规定 | 用模型解释 |
|---|---|
| `shared_ptr<T>` 的 `T` 可以不完整，甚至可以是函数类型（[[util.smartptr.shared#3]]） | 删除器在构造时按实际类型存进控制块，析构 `shared_ptr` 时不需要知道 `T` |
| 可以有空的、但存储的指针非空的 `shared_ptr`（别名构造，[util.smartptr.shared.const] ¶17） | 控制块指针为空，存储的指针不为空 |
| `get_deleter` 返回的指针在最后一个 `shared_ptr` 销毁后可能仍然有效（[[util.smartptr.getdeleter]] 的注） | 删除器在控制块里，实现可以等弱计数归零再销毁它 |
| `owner_before` 和 `operator<` 的结果不同 | 前者比较控制块，后者比较存储的指针 |
| `shared_ptr(p)` 可能抛出 `bad_alloc`，抛出时会 `delete p`（[util.smartptr.shared.const] ¶6、¶8） | 要分配控制块；分配失败时必须清理已经接管的 `p` |

!!! impl "libc++ 的控制块"
    libc++ 的控制块基类是 `__shared_weak_count`，它派生自 `__shared_count`。它有一个虚表指针，虚函数 `__on_zero_shared()` 在强计数归零时销毁对象，`__on_zero_shared_weak()` 在弱计数归零时释放控制块，`__get_deleter(const type_info&)` 用来实现 `get_deleter`。两个计数字段 `__shared_owners_`、`__shared_weak_owners_` 存的都是计数减一，所以 `use_count()` 返回 `__shared_owners_ + 1`。

    派生类按创建方式区分：`__shared_ptr_pointer<P, D, A>` 保存指针、删除器和分配器，由 `shared_ptr(p, d, a)` 这类构造函数创建；`__shared_ptr_emplace<T, A>` 把 `T` 对象直接放在控制块里，由 `make_shared` 和 `allocate_shared` 创建。

    增加计数用 `__ATOMIC_RELAXED`，减少计数用 `__ATOMIC_ACQ_REL`。增加时调用方已经持有一个引用，对象不可能在此期间被销毁，不需要同步；减少时，把计数减到 0 的线程要析构对象，它必须看到其他线程通过各自的副本对对象做过的全部修改。

## `make_shared` 只分配一次

```cpp run impl
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Big { char data[64]; };

int main() {
  allocs = 0;
  std::shared_ptr<Big> a(new Big);
  std::printf("shared_ptr(new T): %d\n", allocs);   // 2
  allocs = 0;
  auto b = std::make_shared<Big>();
  std::printf("make_shared:       %d\n", allocs);   // 1
  std::printf("%zu %zu\n", sizeof a,
              sizeof(std::weak_ptr<Big>));          // 16 16
}
```

注释里是本机 libc++ 的输出。`shared_ptr<T>(new T)` 分配两次，`new T` 一次，控制块一次。`make_shared<T>()` 把 `T` 放进控制块，只分配一次。[util.smartptr.shared.create] ¶7.1 建议实现最多分配一次，这是建议而不是要求，所以判定是 {{impl}}。

一次分配少调用一次 `malloc`，对象和计数也挨在一起。代价有两个：

1. 内存释放被推迟。`T` 和控制块在同一块内存里，强计数归零时 `T` 被析构，但只要还有 `weak_ptr`，弱计数不为 0，整块内存就不能释放，包括 `T` 占的那部分。大对象配上长期存在的 `weak_ptr`（比如缓存），会占住可观的内存。
2. 不能自定义删除器，也不会使用类自己的 `operator new` 和 `operator delete`：¶7.4 规定 `make_shared` 用 `::new(pv) U(...)` 构造对象。需要定制分配时用 `allocate_shared`。

## 线程安全

`shared_ptr` 的全部线程安全保证都来自 [[util.smartptr.shared#5]]：

!!! std "[util.smartptr.shared.general]/5"
    For purposes of determining the presence of a data race, member functions shall access and modify only the shared_ptr and weak_ptr objects themselves and not objects they refer to. Changes in use_count() do not reflect modifications that can introduce data races.

判断有没有数据竞争时，成员函数只算访问和修改了 `shared_ptr`、`weak_ptr` 对象本身，不算访问它们所指的对象；`use_count()` 的变化也不算可能引起数据竞争的修改。换成具体场景：

| 场景 | 是否数据竞争 |
|---|---|
| 两个线程各自复制、销毁不同的 `shared_ptr` 对象，即使它们共享同一个控制块 | 否，计数的修改不算，实现必须用原子操作 |
| 两个线程同时读（复制、`get()`）同一个 `shared_ptr` 对象 | 否，都是 const 操作（[[res.on.data.races]]） |
| 一个线程写（赋值、`reset`）某个 `shared_ptr` 对象，另一个线程同时读或写它 | 是，{{ub}} |
| 多个线程通过 `shared_ptr` 访问所指的对象 | 与 `shared_ptr` 无关，取决于那个对象本身 |

```cpp run ub
#include <memory>
#include <thread>
int main() {
  auto p = std::make_shared<int>(1);
  std::thread t([&] {
    for (int i = 0; i < 100000; ++i) { auto copy = p; }   // 读 p
  });
  for (int i = 0; i < 100000; ++i)
    p = std::make_shared<int>(i);   // 写 p：数据竞争
  t.join();
}
```

本机用 `-fsanitize=thread` 运行，ThreadSanitizer 报告数据竞争；用 `-fsanitize=address` 运行，AddressSanitizer 报告 heap-use-after-free。读线程复制 `p` 时，可能读到新的存储指针和旧的控制块指针；也可能在它增加旧控制块的计数之前，写线程已经释放了那个控制块。

多个线程要读写同一个 `shared_ptr` 变量时，C++20 起用 `std::atomic<std::shared_ptr<T>>`（[[util.smartptr.atomic]]，[[P0718R2]]）。它取代了 C++11 的自由函数 `atomic_load(&sp)`、`atomic_store(&sp, ...)`，这些函数 C++20 弃用，C++26 移除。截至写作时，本机 libc++ 还没有实现 `atomic<shared_ptr>`，`<version>` 里的 `__cpp_lib_atomic_shared_ptr` 是注释掉的。

另外两点容易被忽略：

- 多线程下 `use_count()` 只是近似值（[util.smartptr.shared.obs] ¶17）。实现用 relaxed 读取，`use_count() == 1` 并不意味着其他线程通过已经销毁的 `shared_ptr` 所做的访问都已完成。用它判断自己是唯一的拥有者、可以不加锁修改对象，是错误的。C++20 移除 `unique()` 的原因之一就在这里。
- 最后一个 `shared_ptr` 在哪个线程销毁，对象就在哪个线程析构。持有锁、依赖线程局部状态或者必须在 GUI 线程析构的对象要特别注意。

## `bad_weak_ptr` [util.smartptr.weak.bad]

```cpp
class bad_weak_ptr : public exception {
public:
  constexpr const char* what() const noexcept override;
};
```

¶1 接受 `weak_ptr` 的 `shared_ptr` 构造函数会抛出 `bad_weak_ptr`，条件是这个 `weak_ptr` 已经过期（[util.smartptr.shared.const] ¶27）。`shared_from_this()` 就是用这个构造函数实现的，所以对一个不被任何 `shared_ptr` 拥有的对象调用 `shared_from_this()`，同样会抛出它。这是 C++17 的规定，之前是未定义行为（[[util.smartptr.enab]]）。

¶2 `what()` 返回一个由实现定义的 NTBS（以空字符结尾的字节串）。

`what()` 是 `constexpr` 的。C++26 让 `shared_ptr` 可以在常量求值中使用（[[P3037R6]]），同时允许常量求值中抛出和捕获异常，从过期的 `weak_ptr` 构造 `shared_ptr` 在编译期也会抛出这个异常。

`weak_ptr::lock()` 不抛异常，过期时返回空的 `shared_ptr`。两种取得 `shared_ptr` 的方式区别就在这里：失败时一个抛异常，一个返回空。

## 思考题

!!! question "思考题 1"
    在 64 位平台上，一个 `shared_ptr<T>` 为什么是 16 字节，而不像侵入式智能指针那样只有 8 字节？

<details markdown="1">
<summary>答案</summary>

存储的指针可以和被拥有的指针不同，别名构造和转换到基类都会改变地址。只存一个控制块指针就得不到 `get()`，除非每次解引用都多一次间接访问。标准的接口要求别名构造，并且 `get()` 是 `noexcept` 的常数时间操作，实际上迫使实现存两个指针。
</details>

!!! question "思考题 2"
    用 `make_shared` 创建的对象被一个 `weak_ptr` 观察着。最后一个 `shared_ptr` 销毁之后，对象的析构函数会运行吗？内存会释放吗？

<details markdown="1">
<summary>答案</summary>

析构函数会运行，强计数归零时对象被销毁。内存不会释放：对象放在控制块里，控制块要等弱计数归零，也就是那个 `weak_ptr` 也销毁之后才释放。
</details>
