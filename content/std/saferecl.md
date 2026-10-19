---
title: 安全回收：RCU 与 hazard pointer
summary: C++26 提供的两种安全回收机制 RCU 和 hazard pointer，用来解决无锁数据结构中读者还在用、写者已经删除的问题。
status: draft
covers: *
papers: P2545R4, P2530R3
related: atomics.types.generic, util.smartptr.atomic, intro.races, thread.req, thread.lock
tags: 标准库, 并发, RCU, hazard pointer, 无锁, 内存回收
updated: 2026-10-19
---

!!! tldr
    - 无锁结构里，读者拿到指针后，写者可能已经把对象删掉；安全回收机制把删除推迟到没有读者还在用它的时候。
    - RCU：读者用 `rcu_domain` 的 `lock`/`unlock` 圈出一段读侧临界区，写者 `retire` 旧对象；删除要等所有可能看到旧对象的临界区结束。
    - hazard pointer：读者用 `protect` 把一个 hazard pointer 指向要用的对象；只要还有 hazard pointer 指着它，它就不会被回收。
    - RCU 的读者开销最低，但未回收对象没有上界；hazard pointer 每个对象要单独保护，但未回收对象数量有界。
    - `retire`、`unlock` 都可能顺便执行早先安排的删除器，持有删除器需要的锁时调用它们会死锁。Clang 23 的 libc++ 还没有实现这两个头文件。

## 访问-删除竞争

```cpp
#include <atomic>
struct Node { int value; };
std::atomic<Node*> head{new Node{1}};

int reader() {
  Node* p = head.load(std::memory_order::acquire);
  return p->value;            // 此时 *p 可能已被删除
}

void writer() {
  Node* old = head.exchange(new Node{2});
  delete old;                 // reader 可能还在用 old
}
```

`reader` 读到指针 `p` 之后、访问 `*p` 之前，`writer` 可能已经把它摘下并删除。两个线程一旦这样交错，`reader` 的访问就是释放后使用，属于未定义行为。这种问题叫**访问-删除竞争**（access-deletion race）。

用互斥量能解决它，但读者每次都要加锁，失去了无锁结构的意义。用 `atomic<shared_ptr>`（[[util.smartptr.atomic]]）也能解决，但每次读取都要原子地修改引用计数，读多写少时代价很高。

¶1 第 32.11 节提供的**安全回收**（safe reclamation）技术就是为这个问题准备的 {{c++26}}。两种机制的共同思路是：写者不直接删除旧对象，而是把它交给库**退休**（retire），由库在确认没有读者还在使用之后再调用删除器。

| | RCU（[[P2545R4]]） | hazard pointer（[[P2530R3]]） |
|---|---|---|
| 读者做什么 | 进入、退出读侧临界区 | 每个要用的指针发布一次再校验一次 |
| 保护范围 | 临界区内读到的所有对象 | 一个 hazard pointer 保护一个对象 |
| 何时删除 | 所有可能看到它的临界区结束后 | 没有 hazard pointer 再指向它时 |
| 未回收对象数量 | 无上界 | 有上界 |
| 头文件 | `<rcu>` | `<hazard_pointer>` |

!!! impl "libc++ 尚未实现"
    Clang 23 自带的 libc++ 没有 `<rcu>` 和 `<hazard_pointer>`，`__cpp_lib_rcu` 与 `__cpp_lib_hazard_pointer` 均未定义。本页使用这两个头文件的代码没有经过编译验证，只依据草案条文写成。两者的参考实现来自 Folly 库。

## RCU

### 用法

RCU 是 read-copy update（读-复制-更新）的缩写。[[saferecl.rcu.general#1]] 说它适用于频繁读取、很少更新的链式数据结构。它不提供互斥，而是让用户把删除之类的动作**安排**（schedule）到以后某个时间执行。

```cpp
// 未经编译验证：libc++ 尚无 <rcu>
#include <atomic>
#include <mutex>
#include <rcu>
#include <string>

struct Config : std::rcu_obj_base<Config> {
  Config(std::string ep, int t) : endpoint(std::move(ep)), timeout_ms(t) {}
  std::string endpoint;
  int timeout_ms;
};

std::atomic<Config*> current{new Config("localhost", 100)};

int read_timeout() {
  std::scoped_lock rl(std::rcu_default_domain());   // 进入读侧临界区
  Config* c = current.load(std::memory_order::acquire);
  return c->timeout_ms;                              // 临界区内 *c 不会被删除
}                                                    // 离开临界区

void update(std::string ep, int t) {                 // 假定写者之间另有互斥
  Config* fresh = new Config(std::move(ep), t);
  Config* old = current.exchange(fresh, std::memory_order::acq_rel);
  old->retire();                                     // 安排 delete old
}
```

读者用 `rcu_domain` 的 `lock`/`unlock` 圈出一段临界区，这里借助 `scoped_lock` 管理。写者先用新对象替换指针（复制-更新），再把旧对象退休。RCU 保证，所有可能读到旧对象的读者离开临界区之后，才执行 `delete old`。

`rcu_domain` 满足 *Cpp17Lockable*，所以能用标准的 RAII 锁（[[thread.lock]]），但它并不互斥：任意多个读者可以同时持有它，`try_lock()` 永远返回 `true`。

### 核心保证

¶4 一次 `lock` 到与它配对的 `unlock` 之间，叫作一个 **RCU 保护区域**（[[g:region-of-rcu-protection|region of RCU protection]]），也就是上面说的读侧临界区。¶3 规定了嵌套时怎样配对：同一线程里对同一个域的 `lock`/`unlock` 像括号一样匹配。

¶5 是整个 RCU 的保证：

!!! std
    Given a region of RCU protection R on a domain dom and given an evaluation E that scheduled another evaluation F in dom, if E does not strongly happen before the start of R, the end of R strongly happens before evaluating F.

放到上面的例子里：E 是写者调用 `retire`，F 是 `delete old`，R 是某个读者的临界区。分两种情况：

- 如果 `retire` strongly happens before 读者进入临界区，那么读者进入时指针早已替换，不可能读到 `old`，删除不必等它。
- 否则，读者可能读到了 `old`，删除必须等这个临界区结束之后才进行。

strongly happens before 是 [[intro.races]] 定义的线程间顺序关系，比 happens before 更强，区别只出现在混用 `seq_cst` 和较弱内存序的情形，日常理解时可以把它当作 happens before。

¶6 被安排的删除器可能在任何线程上执行，彼此潜在并发，每个至多执行一次。如果多个删除器共享状态，需要自己同步。

### 两种退休方式

`rcu_obj_base<T, D>` 是一个 CRTP 基类。¶2 规定，类型 `T` 恰有一个公有、非虚的 `rcu_obj_base<T, D>` 基类（且没有其他 `rcu_obj_base<X, Y>` 基类）时，`T` 是 **rcu-protectable** 的。这样的对象可以直接调用成员 `retire(d, dom)`（[[saferecl.rcu.base#9]]），删除器 `D` 默认是 `default_delete<T>`，存放在基类子对象里，所以这个调用不分配内存，是 `noexcept` 的。

不想改类定义时，可以用自由函数 `rcu_retire(p, d, dom)`（[[saferecl.rcu.domain.func#8]]）。它需要另外分配一个节点记录指针和删除器，因此可能抛出 `bad_alloc`；抛出异常时什么也没有安排。

同一个对象只能退休一次（[[saferecl.rcu.base#8]]），删除器以异常退出是未定义行为。

### 等待：rcu_synchronize 与 rcu_barrier

两个函数等的东西不同：

- `rcu_synchronize(dom)`（[[saferecl.rcu.domain.func#2]]）等待调用前已经开始的所有临界区结束。有了它，写者可以不用 `retire`，而是先替换指针、调用 `rcu_synchronize()`，再直接 `delete`。
- `rcu_barrier(dom)`（[[saferecl.rcu.domain.func#4]]）等待调用前已经安排的所有删除器执行完毕。典型用途是卸载模块或程序退出前清空待删除队列。

[[saferecl.rcu.domain.func#5]] 的注特意说明，两者互不蕴含。

### 删除器可能在你的线程上运行

成员 `retire`、`rcu_retire` 和 `unlock` 都可以顺便执行早先安排好的删除器（[[saferecl.rcu.base#9]]、[[saferecl.rcu.domain.members#6]]）。如果你持有互斥量 `m` 时调用它们，而某个删除器也要锁 `m`，同一线程就会死锁。标准在这几处都用注提醒了这一点。

## hazard pointer

### 用法

**hazard pointer** 是一个单写者、多读者的指针（[[saferecl.hp.general#1]]）。它同一时刻至多属于一个线程，只有拥有者能修改它，其他线程都可以读。拥有者把它指向某个对象，等于告诉可能删除该对象的线程：这个对象还不能删。

下面是标准的例 1（[[saferecl.hp.general#7]]）：

```cpp
// 未经编译验证：libc++ 尚无 <hazard_pointer>
struct Name : public hazard_pointer_obj_base<Name> { /* details */ };
atomic<Name*> name;
// 调用频繁，且会并行调用
void print_name() {
  hazard_pointer h = make_hazard_pointer();
  Name* ptr = h.protect(name);          // 保护开始
  // ... 可以安全访问 *ptr
}                                       // 保护结束
// 很少调用，但可能与 print_name 并发
void update_name(Name* new_name) {
  Name* ptr = name.exchange(new_name);
  ptr->retire();
}
```

`make_hazard_pointer()` 创建一个 hazard pointer，`protect` 读出 `name` 并让 hazard pointer 指向读到的对象。写者 `retire` 旧对象后，只要还有 hazard pointer 指着它，它就不会被回收。

与 RCU 一样，¶2 定义了 **hazard-protectable** 类型：恰有一个公有、非虚的 `hazard_pointer_obj_base<T, D>` 基类。它的 `retire(d)` 没有域参数，标准接口中没有 hazard pointer 域的概念。

### 先发布，再校验

`protect` 等价于反复调用 `try_protect` 直到成功（[[saferecl.hp.holder.mem#2]]）：

```cpp
T* ptr = src.load(memory_order::relaxed);
while (!try_protect(ptr, src)) {}
return ptr;
```

[[saferecl.hp.holder.mem#5]] 规定 `try_protect(ptr, src)` 按顺序做四件事：

1. 记下 `old = ptr`；
2. 把 hazard pointer 指向 `old`，相当于公开声明要用它；
3. 用 `src.load(memory_order::acquire)` 重新读一次源，结果存入 `ptr`；
4. 如果 `old != ptr`，撤销保护。

最后返回 `old == ptr`。这是 hazard pointer 算法的关键：只有发布之后再次读到同一个指针，才能确定发布时对象还没有被替换。之后退休它的线程一定能看到这个 hazard pointer。

### 什么时候可以回收

¶3 把一个 hazard pointer 从创建到销毁的时间分成若干**保护纪元**（[[g:protection-epoch|protection epoch]]）。每个纪元里，它要么与一个对象关联，要么未关联；每次改变关联（哪怕改成同一个对象）都结束旧纪元、开始新纪元。¶4、¶5 定义：对象 `x` 调用 `retire` 时被**退休**，删除器被调用时被**回收**。

¶6 定义 `x` 相对于求值 A 何时**可能可回收**（possibly-reclaimable），即 A 可以回收它的条件。粗略地说：`x` 已退休、还没回收，而且每个在退休之前开始并关联到 `x` 的保护纪元，都已经在 A 之前结束。

"在退休之前开始"有两种认定方式（¶6.3.1、¶6.3.2）：

- 纪元的开始 happens before 退休；
- 纪元由 `try_protect` 开始，它的 load 读到的是 `src` 上某次修改 B 之前的值，而 B happens before 退休。这对应例 1 中的情形：读者在 `exchange` 之前读到了旧指针，即使两者之间没有 happens before 关系，读者的纪元也要保护旧对象。

¶7 规定可能可回收对象的数量有一个未指定的上界，比如可以是 hazard pointer 数量和线程数的函数。这是 hazard pointer 相对 RCU 的优势：慢读者不会让内存无限增长。

### hazard_pointer 对象

`hazard_pointer` 是只可移动的句柄，要么为空，要么拥有一个 hazard pointer（[[saferecl.hp.holder.general#1]]）。空的句柄和拥有一个未关联 hazard pointer 的句柄不同：前者根本没有 hazard pointer，不能调用 `protect`。

- 默认构造得到空句柄，要用 `make_hazard_pointer()` 获取真正的 hazard pointer，内存不足时可能抛出 `bad_alloc`。
- 析构时销毁拥有的 hazard pointer，从而结束当前保护纪元。
- `reset_protection(p)` 改为保护 `p`，`reset_protection()` 取消保护。
- `swap` 只交换所有权，hazard pointer 本身继续保护原来的对象，不开始也不结束任何纪元。
- `make_hazard_pointer_batch` 和 `clear_hazard_pointer_batch` 一次为一个 `span<hazard_pointer>` 中的空元素创建、或为非空元素销毁 hazard pointer。

## 如何选择

如果读操作极其频繁、临界区很短、能容忍待删除对象暂时堆积，选 RCU。读者进入、退出临界区通常只是增减一个线程局部计数器。

如果读者可能长时间持有某个对象，或者必须限制未回收内存，选 hazard pointer。代价是每保护一个对象都要一次发布加一次校验，还需要实现所需的栅栏。

两者在读多写少的场景下都比 `atomic<shared_ptr>` 快，因为读者不修改任何共享计数器。

## 陷阱

!!! pitfall "在删除器需要的锁下调用 retire 或 unlock"
    RCU 的 `retire`、`rcu_retire`、`unlock` 和 hazard pointer 的 `retire` 都可能在当前线程上执行早先安排的删除器。持有删除器需要的锁时调用它们可能死锁。

!!! pitfall "退休两次"
    两种 `retire` 的前置条件都要求对象没有退休过。退休两次是未定义行为，通常表现为重复释放。

!!! pitfall "在 RCU 临界区内阻塞"
    读者长时间不离开临界区，之后退休的所有对象都无法回收，内存持续增长，`rcu_synchronize` 也会一直阻塞。临界区内不要做 I/O，也不要等待其他线程。

<details class="fine" markdown="1"><summary>其余条文</summary>

- [[saferecl.rcu.base]] ¶2–¶6：给 `rcu_obj_base` 添加特化是未定义行为；`T` 可以是不完整类型，但引用特化的成员前必须完整；`D` 须是可以 `d(ptr)` 调用的函数对象类型，满足 *Cpp17DefaultConstructible* 与 *Cpp17MoveAssignable*；`D` 可平凡复制时，`rcu_obj_base<T, D>` 也可平凡复制。
- [[saferecl.hp.base]] ¶1–¶4：`hazard_pointer_obj_base` 的同类要求。
- [[saferecl.rcu.domain.members]]：`lock`、`unlock` 的调用本身不引入涉及该域的数据竞争；`unlock` 的前置条件是之前有一个未关闭的 `lock`；它关闭最近打开的那一个区域。
- [[saferecl.rcu.domain.func#1]]：`rcu_default_domain()` 每次返回同一个静态存储期对象。
- [[saferecl.rcu.domain.func#6]]、¶7：`rcu_retire` 要求 `D` 可移动构造、`d(p)` 良构。

</details>
