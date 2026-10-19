---
title: 操作状态
summary: operation_state 概念只要求能被 start；异步操作进行期间销毁操作状态是 UB；复制或移动标准库发送器的操作状态非良构；start(op) 只接受左值，不能抛异常，并且必须真的启动操作。
status: draft
covers: *
papers: P2300R10
related: exec.async.ops, exec.recv, exec.connect, exec.snd, class.copy.elision
tags: 标准库, std::execution, 生存期, UB
updated: 2026-10-19
---

!!! tldr
    - 操作状态是 `connect(sndr, rcvr)` 的结果，装着一次异步操作需要的全部数据；`start(op)` 才让它开始运行。
    - 操作开始后、完成之前销毁操作状态是未定义行为。
    - 标准库发送器产生的操作状态不能复制也不能移动。要把它放到某处，靠的是 C++17 的保证复制消除。
    - `start(op)` 拒绝右值，必须是 noexcept 的；启动时出的错要通过接收器的 `set_error` 报告。

本页的 `std::execution` 例子没有经过编译验证：本机 Clang 23 附带的 libc++ 还没有实现发送器库，所以这些例子不加判定标记。演示语言规则的例子用一个不可移动的类型模拟操作状态，经过了本机 Clang 编译。

## 操作状态是什么

[[g:sender|发送器]]（sender）只是一段异步工作的描述，[[g:receiver|接收器]]（receiver）是工作完成后的去处。`connect(sndr, rcvr)` 把两者绑在一起，得到一个[[g:operation-state|操作状态]]（operation state）对象（[[exec.connect]]）：

```cpp title="opstate.cpp"
namespace ex = std::execution;

auto op = ex::connect(ex::just(42), rcvr);   // 什么也没发生
ex::start(op);                               // 现在才开始；just 会立即调用 rcvr 的 set_value
```

接收器、发送器复制进来的数据、所有子操作的状态、排队用的链表指针，都存在操作状态里面。它由调用者拥有，可以放在栈上、协程帧里，或者嵌在父操作的操作状态里。`std::future` 的共享状态必须分配在堆上，因为生产者和消费者各持有一份；操作状态只有一个所有者，所以整个发送器链可以不做任何动态分配。

代价是它必须待在原地。操作一旦开始，别处就可能持有指向它内部的指针：`run_loop` 的队列里挂着它（[[exec.run.loop]]），线程池的工作项指向它，子操作的接收器里存着指向父操作状态的指针（[[exec.snd]] 中的 *basic-receiver*）。移动它会让这些指针全部悬空。下面的规则都是从这一点出发的。

## operation_state 概念 [exec.opstate.general]

¶1 概念本身只有两个要求：类型声明 `operation_state_concept` 标签，并且 `start` 能用左值调用。

```cpp
template<class O>
  concept operation_state =
    derived_from<typename O::operation_state_concept, operation_state_tag> &&
    requires (O& o) {
      start(o);
    };
```

它不要求可复制、可移动，也不要求可析构。另外它检查的是 `O::operation_state_concept`，而不像 `sender`、`receiver` 那样先去掉引用和 cv 限定：操作状态总是以对象类型本身被检查。

¶2 如果在异步操作的生存期内销毁操作状态对象，行为未定义 {{ub}}。这和 [[exec.async.ops#7]] 是同一条规则，只是换成了针对对象的说法。注 1 补充，概念对析构和 `start` 以外的操作（包括复制、移动）没有任何要求，对这样的对象调用它们可能导致 UB。

¶3 如果程序对标准库发送器 connect 得到的操作状态执行复制或移动（构造或赋值），程序非良构 {{ill-formed}}。实践中这些类型直接删除了复制和移动构造函数。

| 操作状态来自 | 复制、移动 |
|---|---|
| 标准库发送器 | 非良构，必须诊断 |
| 用户自己写的发送器 | 概念不管；即使类型允许移动，启动后再移动也很可能是 UB |

## 怎样持有一个不可移动的对象

`connect` 返回纯右值（prvalue）。C++17 起，用纯右值初始化同类型的对象时不会创建临时对象，而是直接在目标位置构造，这叫保证复制消除（[[class.copy.elision]]）。所以直接初始化变量、从函数返回 `connect(...)` 都不需要移动构造函数。下面用一个删除了移动构造函数的类型模拟操作状态：

<div class="compare" markdown="1">

```cpp run ok
struct op_t {
  explicit op_t(int) {}
  op_t(op_t&&) = delete;
};
op_t connect(int x) { return op_t(x); }

op_t make() {
  return connect(1);   // OK：纯右值
}
int main() { [[maybe_unused]] op_t op = make(); }
```

```cpp run error
struct op_t {
  explicit op_t(int) {}
  op_t(op_t&&) = delete;
};
op_t connect(int x) { return op_t(x); }

op_t make() {
  op_t op = connect(1);
  return op;   // error: 移动构造函数被删除
}
```

</div>

右边依赖的是具名返回值优化（NRVO）。NRVO 只是允许编译器省略的复制，语言仍然要求移动构造函数可用，所以它非良构。

放进 `std::optional` 也有同样的问题。`opt.emplace(connect(...))` 不行：`emplace` 的形参是引用，实参会先物化成一个临时对象，再用它移动构造元素。标准阐述代码里的 *emplace-from*（[[exec.snd]]）绕过了这一点：传进去的不是操作状态，而是一个能转换成操作状态的对象。`optional` 内部用它构造元素时调用转换函数，转换函数返回纯右值，又回到了保证复制消除。

```cpp run ok
#include <optional>
struct op_t {
  explicit op_t(int) {}
  op_t(op_t&&) = delete;
};
op_t connect(int x) { return op_t(x); }

template<class F>
struct emplace_from {
  F fun;
  operator decltype(fun())() && { return static_cast<F&&>(fun)(); }
};
template<class F> emplace_from(F) -> emplace_from<F>;

int main() {
  std::optional<op_t> opt;
  // opt.emplace(connect(1));                       // error: 需要移动构造
  opt.emplace(emplace_from{[] { return connect(1); }});   // OK
}
```

`let_value` 要在运行时才 connect 第二个发送器，它就是这样把第二个操作状态放进成员里的（[[exec.let]]）。

同理，`std::vector<op_t>` 不能用：扩容时要移动已有元素，`push_back`、`emplace_back` 都编译不过。需要一组操作状态时，可以用定长数组、`std::list` 或 `std::deque`（它们的 `emplace_back` 不移动已有元素），或者像 `when_all` 那样把所有子操作状态放进一个聚合体里一次构造好（[[exec.snd]] 的 *connect-all*）。

## start [exec.opstate.start]

¶1 `start` 是一个定制点对象（CPO），它启动操作状态对应的异步操作。`start(op)` 的规则有三条：

- `op` 是右值时，`start(op)` 非良构 {{ill-formed}}；
- 否则它等价于 `op.start()`，并且要求这个调用不抛异常（*MANDATE-NOTHROW*，不满足时非良构）；
- `op.start()` 的类型必须是 `void`。

禁止右值，是因为 `start(connect(s, r))` 里的临时操作状态在完整表达式结束时就被销毁，而操作多半还没有完成，正好违反 ¶2 的生存期规则。在编译期拦下来，比留到运行期出现 UB 好。

要求 noexcept，是因为 [[exec.async.ops#8]] 要求操作启动后恰好完成一次。如果 `start` 能抛异常，就会出现启动了却没有完成的状态。启动过程中的错误（线程池队列已满、分配失败）必须通过对接收器调用 `set_error` 报告。

¶2 如果 `op.start()` 并没有真的启动对应的异步操作，调用 `start(op)` 的行为未定义 {{ub}}。所以 `start` 成员不能是空函数，也不能先记下来、等别人再调用一次。按 [[exec.async.ops#7]]，异步生存期从启动操作开始执行时开始，此后操作必须最终完成。

调用 `start(op)` 之后，调用者对 `op` 只剩一件事可做：等完成操作开始执行之后销毁它。不能再次 `start`（[[exec.async.ops#2]] 规定至多启动一次），不能移动，完成之后也不能再访问它的内部。

## 思考题

!!! question "1. start 两次"
    `auto op = connect(just(1), rcvr); start(op); start(op);` 违反了哪条规则？是非良构还是 UB？

<details markdown="1">
<summary>答案</summary>

违反 [[exec.async.ops#2]]：一个操作至多启动一次。第一次 `start` 时 `just` 已经同步完成，操作状态随之失效；第二次 `start` 访问失效的操作状态，按 [[exec.async.ops#7]] 是 UB。编译期无法发现：两次都是对左值的合法 `start` 表达式。
</details>

!!! question "2. 为什么概念不要求可析构？"
    `operation_state` 没有像 `scheduler` 那样要求 `destructible`。这是疏漏吗？

<details markdown="1">
<summary>答案</summary>

不是。概念只表达能被启动这一接口。什么时候可以析构是生存期问题，由 ¶2 和 [[exec.async.ops#7]] 约束，概念无法表达只能在某个时刻之后析构。操作状态几乎总是作为局部变量或成员被隐式析构，`destructible` 对它并不提供有用的信息。实践中操作状态都有 noexcept 的析构函数。
</details>
