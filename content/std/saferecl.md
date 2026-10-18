---
title: 安全回收：RCU 与 hazard pointer
summary: C++26 的两种安全内存回收机制——RCU（读侧临界区、rcu_retire、rcu_synchronize 与 rcu_barrier 的 strongly happens before 规则）与 hazard pointer（保护纪元、retire、"可能可回收"的形式定义、protect/try_protect 的步骤）；二者解决的"访问-删除竞争"问题；libc++ 尚未提供
status: draft
covers: *
papers: P2545R4, P2530R3
related: atomics.types.generic, util.smartptr.atomic, intro.races, thread.req, thread.lock
tags: 标准库, 并发, RCU, hazard pointer, 无锁, 内存回收
updated: 2026-10-18
---

无锁数据结构里有一个绕不过去的问题：线程 A 通过一个原子指针读到节点 `p`，正准备访问 `*p`；线程 B 同时把 `p` 从结构中摘下并 `delete p`。A 接下来的访问就是释放后使用。这叫**访问-删除竞争**（access-deletion race）。用互斥量可以避免它，但那样读者就要加锁，失去了无锁的意义；用 `atomic<shared_ptr>`（[[util.smartptr.atomic]]）也可以，但每次读取都要原子地修改引用计数，读多的场景代价很高。

[saferecl.general] ¶1：本子条款包含**安全回收**技术，它们最常用于直截了当地解决访问-删除竞争。C++26 标准化了两种 {{c++26}}：

| | RCU（[[P2545R4]]） | hazard pointer（[[P2530R3]]） |
|---|---|---|
| 读者的开销 | 极低：进入/退出读侧临界区 | 低：每个受保护的指针一次发布 + 校验 |
| 保护粒度 | 临界区内读到的**所有**对象 | 每个 hazard pointer 保护**一个**对象 |
| 回收延迟 | 等所有已存在的读侧临界区结束 | 等不再有 hazard pointer 指向它 |
| 未回收对象数量 | 无界（读者长时间不退出临界区时） | 有界（¶7） |
| 头文件 | `<rcu>` | `<hazard_pointer>` |

!!! impl "libc++ 尚未实现"
    Clang 23 自带的 libc++ 没有 `<rcu>` 和 `<hazard_pointer>` 头文件，`__cpp_lib_rcu` 与 `__cpp_lib_hazard_pointer` 均未定义。本页的代码**未经编译验证**，只根据草案条文写成。两者的参考实现源自 Facebook 的 Folly 库。

## RCU（[saferecl.rcu]）

### 概念（[saferecl.rcu.general]）

¶1 RCU（read-copy update，读-复制-更新）是一种同步机制，用于**频繁读取、很少更新**的链式数据结构。RCU **不提供互斥**，而是允许用户把指定的动作（如删除）**安排**在之后的某个时间执行。

典型用法：读者在**读侧临界区**中读取共享指针并使用它指向的对象；写者用新对象替换旧指针（"复制-更新"），然后把旧对象交给 RCU "退休"（retire），RCU 保证等到所有**可能**看到旧对象的读者都离开临界区后，才真正删除它。

¶2 一个类类型 `T` 是 **rcu-protectable** 的，当且仅当它恰有一个类型为 `rcu_obj_base<T, D>`（对某个 `D`）的基类，该基类是公有、非虚的，且没有任何其他组合 `X, Y` 的 `rcu_obj_base<X, Y>` 基类。rcu-protectable 类型的对象是 rcu-protectable 对象。

¶3 定义 `unlock` 与 `lock` 的配对：对 `rcu_domain dom` 的一次 `unlock` U **对应**一次 `lock` L，若 L sequenced before U，且要么 ¶3.1 L 与 U 之间没有其他对 `dom` 的 `lock`，要么 ¶3.2 L 与 U 之间的每个 `unlock` U2 都对应 L 与 U2 之间的某个 `lock` L2。注 1：这把每个线程中对给定域的嵌套 lock/unlock 配对。

¶4 域 `dom` 上的一个 **RCU 保护区域**（region of RCU protection，[[g:region-of-rcu-protection]]）从 `dom` 上的 lock L 开始，到它对应的 unlock U 结束。

¶5 是 RCU 的核心保证：

!!! std
    Given a region of RCU protection R on a domain dom and given an evaluation E that scheduled another evaluation F in dom, if E does not strongly happen before the start of R, the end of R strongly happens before evaluating F.

    给定域 dom 上的 RCU 保护区域 R，以及在 dom 中安排了另一个求值 F 的求值 E：若 E 不 strongly happens before R 的开始，则 R 的结束 strongly happens before F 的求值。

翻译成具体场景：E 是"写者调用 `retire` 安排删除旧对象"，F 是"删除旧对象"，R 是某个读者的临界区。

- 若 retire **strongly happens before** 读者进入临界区：读者进入时，指针早已被替换（替换 sequenced before retire），读者不可能读到旧对象——不需要等它。
- 否则（读者的临界区可能与 retire 重叠，或在其之前）：读者**可能**读到了旧对象，于是**删除必须等到这个临界区结束之后**。

¶6 一个被安排的求值的执行，与任何其他被安排的求值**潜在并发**。每个被安排的求值**至多**被求值一次。所以删除器（deleter）可能在任意线程上并发执行，它们之间若共享状态需要自己同步。

### 头文件 &lt;rcu&gt; 概要（[rcu.syn]）

```cpp
namespace std {
  template<class T, class D = default_delete<T>> class rcu_obj_base;
  class rcu_domain;
  rcu_domain& rcu_default_domain() noexcept;
  void rcu_synchronize(rcu_domain& dom = rcu_default_domain()) noexcept;
  void rcu_barrier(rcu_domain& dom = rcu_default_domain()) noexcept;
  template<class T, class D = default_delete<T>>
    void rcu_retire(T* p, D d = D(), rcu_domain& dom = rcu_default_domain());
}
```

### rcu_obj_base（[saferecl.rcu.base]）

¶1 要受 RCU 保护的 `T` 类型对象继承自某个 `rcu_obj_base<T, D>` 特化（CRTP）。它只有一个公有成员 `retire(D d = D(), rcu_domain& dom = rcu_default_domain()) noexcept`；构造、复制、析构都是 `protected` 的默认函数；仅说明用成员 `D deleter`。

- ¶2 为 `rcu_obj_base` 添加特化的程序行为未定义。
- ¶3 `T` 可以是不完整类型，但在引用特化的任何成员之前必须完整。
- ¶4–¶5 `D` 须为函数对象类型，对 `D` 类型的值 `d` 与 `T*` 类型的值 `ptr`，`d(ptr)` 有效；`D` 须满足 *Cpp17DefaultConstructible* 与 *Cpp17MoveAssignable*。
- ¶6 若 `D` 可平凡复制，`rcu_obj_base<T, D>` 的所有特化都可平凡复制。

`retire(d, dom)`：

- ¶7 *Mandates*：`T` 是 rcu-protectable 类型。
- ¶8 *Preconditions*：`*this` 是某个 `T` 类型对象 `x` 的基类子对象；`x` 上没有调用过 `retire`；对 `deleter` 的赋值不会以异常退出。
- ¶9 *Effects*：求值 `deleter = std::move(d)`，并在域 `dom` 中**安排**对表达式 `deleter(addressof(x))` 的求值；若该求值以异常退出，行为未定义。**可能**调用 `dom` 中已安排的求值。注 1：若这些求值获取了在调用 `retire` 期间持有的资源，可能死锁。

最后一句是实际编程中的要点：`retire` 可能**就在调用它的线程上**顺便执行一些早先安排好的删除器。如果你持有锁 `m` 调用 `retire`，而某个删除器也要锁 `m`，就会自锁。

### rcu_domain（[saferecl.rcu.domain]）

[saferecl.rcu.domain.general]：`rcu_domain` 不可复制，只有 `lock()`、`try_lock()`、`unlock()` 三个成员（都是 `noexcept`）。

- ¶1 满足 *Cpp17Lockable*（[[thread.req]]），提供 RCU 保护区域。例 1：`std::scoped_lock<rcu_domain> rlock(rcu_default_domain());`
- ¶2 `lock` 与 `unlock` 建立（可能嵌套的）RCU 保护区域。

所以读侧临界区可以直接用标准的 RAII 锁（[[thread.lock]]）管理。注意这把"锁"并不互斥：任意多个读者可以同时"持有"它。

[saferecl.rcu.domain.members]：

- ¶1–¶2 `lock()`：打开一个 RCU 保护区域；对 `lock` 的调用不引入涉及 `*this` 的数据竞争。
- ¶3–¶4 `try_lock()`：等价于 `lock()`，返回 `true`——永远成功（读者从不需要等待）。
- ¶5–¶8 `unlock()`：*Preconditions*：一个打开了尚未关闭的 RCU 保护区域的 `lock` 调用 sequenced before 本调用。关闭**最近打开的**未关闭区域。**可能**调用 `*this` 中已安排的求值（注 1：同样的死锁风险）。不引入涉及 `*this` 的数据竞争；注 2：被安排的求值的执行仍可能导致数据竞争。

[saferecl.rcu.domain.func]：

- ¶1 `rcu_default_domain()`：返回对一个静态存储期 `rcu_domain` 对象的引用，每次调用返回同一个对象。
- ¶2–¶3 `rcu_synchronize(dom)`：若本调用不 strongly happens before 打开某个 RCU 保护区域 R 的 lock，则**阻塞直到关闭 R 的 unlock 发生**。*Synchronization*：关闭 R 的 unlock strongly happens before `rcu_synchronize` 的返回。——即"等待所有**已经开始**的读侧临界区结束"，这是经典 RCU 的 `synchronize_rcu()`。
- ¶4–¶5 `rcu_barrier(dom)`：**可能**求值 `dom` 中已安排的任何求值。对任何 happens before 本调用、且在 `dom` 中安排了求值 E 的求值，**阻塞直到 E 已被求值**。*Synchronization*：每个这样的 E 的求值 strongly happens before `rcu_barrier` 的返回。注 1：调用 `rcu_barrier` 不意味着调用 `rcu_synchronize`，反之亦然。——"等待所有已安排的删除完成"，典型用途是在卸载模块或程序退出前清空待删除队列。
- ¶6–¶10 `rcu_retire(p, d, dom)`：*Mandates* `is_move_constructible_v<D>` 且 `d(p)` 良构；*Preconditions* `D` 满足 *Cpp17MoveConstructible* 与 *Cpp17Destructible*。*Effects*：**可能分配内存**（是否通过 `operator new` 未指定）；从 `std::move(d)` 初始化 `D` 类型的对象 `d1`；在 `dom` 中安排 `d1(p)` 的求值（以异常退出则 UB）；可能调用已安排的求值。注 2：若 `rcu_retire` 以异常退出，则没有安排任何求值。*Throws*：`bad_alloc` 或初始化 `d1` 时的异常。

`rcu_retire` 与 `rcu_obj_base::retire` 的区别：前者用于**不继承** `rcu_obj_base` 的任意类型，代价是需要额外分配一个节点来记录"待删除的指针 + 删除器"（因此可能抛 `bad_alloc`）；后者把删除器存在对象自己的基类子对象里，不需要分配，所以是 `noexcept`。

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
  return c->timeout_ms;                              // 临界区内 *c 不会被删除（¶5）
}                                                    // 离开临界区

void update(std::string ep, int t) {                 // 写者：假定写者之间另有互斥
  Config* fresh = new Config(std::move(ep), t);
  Config* old = current.exchange(fresh, std::memory_order::acq_rel);
  old->retire();                                     // 安排 delete old，在所有可能看到 old 的读者离开后执行
}
```

## hazard pointer（[saferecl.hp]）

### 概念（[saferecl.hp.general]）

¶1 **hazard pointer** 是一个单写者、多读者的指针，任一时刻至多被一个线程拥有。只有拥有者能设置它的值，任意数量的线程可以读取它。拥有者把 hazard pointer 设为指向某个对象，以此告诉并发的线程（它们**可能**删除该对象）：这个对象**还不能安全删除**。

¶2 **hazard-protectable** 类型的定义与 rcu-protectable 平行：恰有一个公有、非虚的 `hazard_pointer_obj_base<T, D>` 基类，没有其他组合的同类基类。

¶3 hazard pointer `h` 从创建到销毁的时间被划分为一系列**保护纪元**（protection epoch，[[g:protection-epoch]]）；在每个纪元中，`h` 要么**关联**一个 hazard-protectable 对象，要么**未关联**。创建时未关联。改变关联（即使改为同一个对象）开始一个新纪元并结束前一个。

¶4 hazard-protectable 类型 `T` 的对象 `x` 在调用 `hazard_pointer_obj_base<T, D>::retire` 时以 `D` 类型的删除器**退休**。任何对象至多退休一次。

¶5 退休的对象 `x` 通过以指向 `x` 的指针调用其删除器而被**回收**；该调用以异常退出则 UB。

¶6 是精确的回收条件。hazard-protectable 对象 `x` 相对于求值 A 是**可能可回收的**（possibly-reclaimable），若：

- ¶6.1 `x` 尚未被回收；
- ¶6.2 `x` 在求值 R 中退休，且 A 不 happens before R；
- ¶6.3 对所有 hazard pointer `h`，以及 `h` 与 `x` 关联的每个保护纪元 E：
    - ¶6.3.1 若 E 的开始 happens before R，则 E 的结束 strongly happens before A；
    - ¶6.3.2 若 E 由以 `src` 为实参的 `try_protect` 求值开始，记其原子 load 操作为 L。若存在 `src` 上的原子修改 B，使得 L 观察到的修改在修改顺序中先于 B，且 B happens before `x` 退休，则 E 的结束 strongly happens before A。

注 1：典型用法中，退休 `x` 之前 sequenced 的对 `src` 的 store 就是这样的 B。注 2：后两个条件表达的直觉是：一个在退休 `x` **之前**开始的保护纪元——无论是由 happens before 关系还是由某个源的一致性顺序所蕴含——都会推迟 `x` 的回收。

¶6.3.2 处理的是这样的竞争：读者 load 了 `src` 得到 `x`（L），写者随后把 `src` 改为别的值（B）并退休 `x`。读者的 hazard pointer 纪元的开始与退休之间也许没有 happens before 关系，但 L 读到的是 B **之前**的值，说明读者"抢在替换之前"看到了 `x`——这种纪元同样必须保护 `x`。

¶7 可能可回收对象的数量有一个**未指定的上界**。注 3：上界可以是 hazard pointer 数量、退休对象的线程数、使用 hazard pointer 的线程数的函数。这是 hazard pointer 相对 RCU 的一个优势：内存占用有界。

例 1（标准自带，改为注释说明）：

```cpp
// 未经编译验证：libc++ 尚无 <hazard_pointer>
struct Name : public hazard_pointer_obj_base<Name> { /* details */ };
atomic<Name*> name;
// 调用频繁，且会并行调用！
void print_name() {
  hazard_pointer h = make_hazard_pointer();
  Name* ptr = h.protect(name);          // 保护纪元开始
  // ... 可以安全访问 *ptr
}                                       // 保护纪元结束
// 很少调用，但可能与 print_name 并发
void update_name(Name* new_name) {
  Name* ptr = name.exchange(new_name);
  ptr->retire();
}
```

### 头文件 &lt;hazard_pointer&gt; 概要（[hazard.pointer.syn]）

声明 `hazard_pointer_obj_base`、`hazard_pointer`、`make_hazard_pointer()`、`swap`，以及 `make_hazard_pointer_batch(span<hazard_pointer>)` 与 `clear_hazard_pointer_batch(span<hazard_pointer>)`——后两个批量操作是较晚加入草案的新措辞。

### hazard_pointer_obj_base（[saferecl.hp.base]）

与 `rcu_obj_base` 平行：¶1、¶3 `D` 的要求；¶2 添加特化是 UB；¶4 `T` 可以不完整。

`retire(D d = D()) noexcept`：¶5 *Mandates* `T` 是 hazard-protectable 的；¶6 *Preconditions*：`*this` 是 `T` 对象 `x` 的基类子对象，`x` 未退休，移动赋值 `d` 不抛异常；¶7 *Effects*：把 `d` 移动赋值给 `deleter`，然后退休 `x`；**可能回收**可能可回收的对象。

注意 hazard pointer 的 `retire` 没有"域"参数：与 RCU 不同，标准接口里没有 hazard pointer 域的概念。

### hazard_pointer（[saferecl.hp.holder]）

[saferecl.hp.holder.general] ¶1：`hazard_pointer` 对象要么为**空**，要么**拥有**一个 hazard pointer。每个 hazard pointer 恰被一个 `hazard_pointer` 对象拥有。注 1：空的 `hazard_pointer` 对象与拥有一个**未关联** hazard pointer 的对象不同——前者根本不拥有 hazard pointer。

`hazard_pointer` 只可移动。

[saferecl.hp.holder.ctor]：

- ¶1 默认构造：空。要获得一个真正的 hazard pointer，必须调用 `make_hazard_pointer()`。
- ¶2 移动构造：接管 `other` 的 hazard pointer，`other` 变空。
- ¶3 析构：若非空，销毁拥有的 hazard pointer，从而结束其当前保护纪元。
- ¶4–¶6 移动赋值：同理。

[saferecl.hp.holder.mem]：

- ¶1 `empty()`。
- ¶2 `protect(const atomic<T*>& src)`：等价于

  ```cpp
  T* ptr = src.load(memory_order::relaxed);
  while (!try_protect(ptr, src)) {}
  return ptr;
  ```

- ¶3–¶6 `try_protect(T*& ptr, const atomic<T*>& src)`：*Mandates* `T` 是 hazard-protectable 的；*Preconditions* `*this` 非空。按顺序执行：
    1. 用 `ptr` 初始化 `T*` 类型的变量 `old`；
    2. 求值 `reset_protection(old)`——先把 hazard pointer 指向 `old`（发布"我要用它"）；
    3. 把 `src.load(memory_order::acquire)` 赋给 `ptr`——**再读一次**源；
    4. 若 `old == ptr` 为 `false`，求值 `reset_protection()`（取消保护）。

  返回 `old == ptr`。

  这正是 hazard pointer 算法的核心："先发布、再校验"。只有在发布 hazard pointer **之后**再次读到同一个指针，才能确定对象在发布时还没有被替换（因而还没有退休，或者退休者一定能看到这个 hazard pointer）。`protect` 就是不断重试直到校验成功。
- ¶7–¶10 `reset_protection(const T* ptr)`：`ptr` 为空时调用 `reset_protection()`；否则把 hazard pointer 与 `*ptr` 关联，结束当前保护纪元。常数复杂度。
- ¶11–¶13 `reset_protection(nullptr_t = nullptr)`：之后 hazard pointer 未关联。
- ¶14–¶15 `swap`：交换所有权；注 1：拥有的 hazard pointer 本身不变，继续与原来保护的对象关联，**不结束也不开始任何保护纪元**。

[saferecl.hp.holder.nonmem]：

- ¶1–¶3 `make_hazard_pointer()`：构造一个 hazard pointer，返回拥有它的 `hazard_pointer` 对象；内存不足时**可能**抛 `bad_alloc`。
- ¶4 `swap(a, b)`。
- ¶5–¶6 `make_hazard_pointer_batch(span<hazard_pointer>)`：对每个空元素构造一个 hazard pointer；抛异常则无效果；可能抛 `bad_alloc`。
- ¶7 `clear_hazard_pointer_batch(span<hazard_pointer>) noexcept`：销毁每个非空元素拥有的 hazard pointer，使其为空。

## 两者如何选择

- 读侧非常频繁、临界区很短、可以容忍未回收内存暂时增长：**RCU**。读者几乎零开销（进入/退出临界区通常只是线程局部计数器的增减）。
- 读者可能长时间持有某个对象，或需要严格限制未回收内存：**hazard pointer**。每个被保护对象需要一个 hazard pointer，读者每次保护都要一次"发布 + 校验"（含一个 store 与一个 acquire load，以及实现所需的栅栏）。
- 二者都比 `atomic<shared_ptr>` 在读多写少的场景下快得多：它们的读者不修改任何共享的计数器。

## 陷阱

!!! pitfall "在删除器可能需要的锁下调用 retire/unlock"
    `rcu_obj_base::retire`、`rcu_retire`、`rcu_domain::unlock` 与 `hazard_pointer_obj_base::retire` 都**可能**顺便执行（回收）早先安排的删除。持有删除器需要的锁时调用它们可能死锁（[saferecl.rcu.base] ¶9 注 1 等）。

!!! pitfall "退休两次"
    `retire` 的前置条件要求对象从未退休过；退休两次是 UB，后果通常是重复释放。

!!! pitfall "RCU 读侧临界区中阻塞"
    RCU 读者长时间不离开临界区，会阻止所有在此之后退休的对象被回收，内存持续增长。`rcu_synchronize` 也会一直阻塞。临界区内不要做 I/O 或等待其他线程。

## 小结

| | RCU | hazard pointer |
|---|---|---|
| 读者保护 | `rcu_domain::lock/unlock`（可用 `scoped_lock`） | `make_hazard_pointer()` + `protect(src)` |
| 写者交出旧对象 | `obj->retire()` / `rcu_retire(p)` | `obj->retire()` |
| 核心保证 | 与 retire 重叠的临界区结束 strongly happens before 删除（[saferecl.rcu.general] ¶5） | 退休前开始的保护纪元结束 strongly happens before 回收（[saferecl.hp.general] ¶6） |
| 等待 | `rcu_synchronize`（等已有临界区）、`rcu_barrier`（等已安排的删除） | 无显式等待；回收在 `retire` 中顺便发生 |
| 未回收对象 | 无界 | 有界（¶7） |
| libc++ | 未实现 | 未实现 |
