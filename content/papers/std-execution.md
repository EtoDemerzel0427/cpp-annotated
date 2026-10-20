---
title: std::execution（P2300）
summary: C++26 的发送器/接收器模型为什么取代 future、协程和执行器成为标准异步的基础：惰性、三个完成通道、不分配内存的 connect/start、停止令牌、结构化并发和成员函数定制各自解决了什么问题，又付出了什么代价。
status: draft
order: 34
group: C++26
since: c++26
papers: P2300R10, P0443R14, P1525R1, P2006R1, P1677R2, P2175R0, P1895R0, P2855R1, P2999R3, P3303R1, P3826R5, P3187R1, P3149R11, P3682R0, P2079R10, P3552R3, P3557R3, P3941R4, P3940R0
related: exec, exec.async.ops, exec.recv, exec.opstate, exec.snd, exec.connect, exec.adapt, exec.when.all, exec.scope, exec.spawn, exec.task, exec.par.scheduler, exec.snd.transform, futures, thread.stoptoken, history/executors-to-execution, history/threads-and-memory-model, topics/coroutines, topics/name-lookup-and-customization, papers/constexpr-exceptions
tags: std::execution, 发送器, 接收器, 异步, 并发, 结构化并发, 提案
updated: 2026-10-19
---

!!! tldr
    - C++11 的 `std::async`/`std::future` 每次都要在堆上分配共享状态，组合只能靠阻塞一个线程，没有取消，也不能选择在哪里运行。P2300 认为这些代价来自 future 本身：它是一项已经开始运行的工作的句柄。
    - P2300 的基础是带三个通道的回调（接收器）加上惰性的工作描述（发送器）：`connect` 把两者装进一个不可移动的操作状态，放在调用者的栈上，`start` 才开始运行，所以组合本身不需要分配内存。
    - 几个关键取舍都有被否决的对手：急切执行（析构时只能在 UB、脱离、阻塞之间选）、把取消当作错误、`start_detached` 式的无人等待的工作、`tag_invoke` 式的 ADL 定制。
    - 代价是接口复杂、元编程重、错误信息难读，生存期规则交给了调用者。截至写作时本机 Clang 23 的 libc++ 还没有发送器，使用标准接口的例子都不标判定。

## C++11 的异步接口缺什么

C++11 给异步工作准备的接口是 `std::async` 和 `std::future`。只要想把两步工作串起来，问题就出现了：

```cpp title="chain.cpp" run ok
#include <future>
#include <cstdio>

int main() {
  std::future<int> a = std::async(std::launch::async,
                                  [] { return 6 * 7; });
  // 想在 a 完成后再加 1：只能再占一个线程去等
  std::future<int> b = std::async(std::launch::async,
      [a = std::move(a)]() mutable { return a.get() + 1; });
  std::printf("%d\n", b.get());
}
```

标准的 `future` 没有 `then`。第二步要么在调用者的线程里 `get()`，要么像上面这样另开一个线程专门阻塞着等第一步。本机 Clang 23 加 TSan 运行输出 `43`，没有报告数据竞争，但为了一次加法用掉了两个线程。

`async` 返回的 `future` 还有一个意外的行为。共享状态由 `async` 启动的线程和 `future` 共同持有，最后一个释放它的 `future` 要等那个线程结束（[[futures.async#4]]，[[futures.async#5]] 的注 2）：

```cpp title="dtor.cpp" run ok
#include <chrono>
#include <cstdio>
#include <future>
#include <thread>
using namespace std::chrono;

int main() {
  auto t0 = steady_clock::now();
  (void)std::async(std::launch::async, [] {
    std::this_thread::sleep_for(500ms);
  });  // 临时 future 在这里析构，并阻塞
  auto ms = duration_cast<milliseconds>(steady_clock::now() - t0);
  std::printf("%lld ms\n", (long long)ms.count());
}
```

本机运行输出约 `506 ms`：看起来是发出去就不管的调用，其实是同步的。不写 `(void)` 时 Clang 会因为 `async` 的 `[[nodiscard]]` 给出警告。`async` 的析构行为为什么这样定，见 [[history/threads-and-memory-model]]。

最后是分配。用一个计数的全局 `operator new` 包住一次 `async` 加 `get`：

```cpp title="alloc.cpp" run ok
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <future>
#include <new>

std::atomic<int> n{0};
void* operator new(std::size_t sz) {
  ++n;
  if (void* p = std::malloc(sz)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  int before = n;
  std::future<int> f = std::async(std::launch::async,
                                  [] { return 42; });
  int v = f.get();
  std::printf("%d, %d allocations\n", v, n - before);
}
```

本机 libc++ 在 `-O0` 和 `-O2` 下都输出 `42, 4 allocations`。具体次数是实现细节，但共享状态的分配躲不掉：它同时被两个线程引用，生存期不由任何一方单独决定。

[[P2300R10]] 的动机一节（§1.1）把这些概括为 `async`/`future`/`promise` 低效、难以正确使用、缺乏泛型性。规则本身见 [[futures]]。

## 设计空间：拿什么做异步的基础

P2300 §1.9 逐一讨论了几种候选的基础抽象，并说明它们为什么不够。

**future。** 即使给 `future` 加上 `then`（并发 TS 就这样做过），代价也还在。§1.9.1 的论证是：future 是一项已经被调度执行的工作的句柄，结果可能在挂上延续之前或之后到达，所以必须有共享状态、同步，通常还要对工作和延续做类型擦除。这些代价是这个抽象固有的。

**协程。** C++20 协程（[[topics/coroutines]]）写起来最自然，而且通常以挂起状态开始，不需要同步。但协程帧通常要动态分配，调用要经过间接跳转，因为帧的布局对类型系统隐藏。§1.9.2 承认 HALO（协程堆分配消除）能去掉这些开销，但指出它需要很多条件同时满足，作者的经验是在实际代码里往往不生效。对一套要能在热路径上调用的泛型算法来说，这不可接受。

**回调。** 回调最古老、最高效，但没有标准的形状：值和错误怎么传、传几个参数，各个库各不相同，泛型代码无从下手；大多数形状也没有为取消留位置（§1.9.3）。

**执行器。** 执行器是把一个 `void()` 函数对象交给某处运行的接口，以 [[P0443R14]] 为代表的一系列提案为它争论了多年。它的问题是交出去之后，结果、错误和取消都没有标准的通道送回来，而且急切提交使得每个任务的状态都要放在堆上（[[P1525R1]]）。这段历史见 [[history/executors-to-execution]]。

P2300 的回答是从回调出发，修掉回调的两个缺点：

- 给回调一个标准形状。**接收器**（[[g:receiver]]）是有三个入口的回调：`set_value`、`set_error`、`set_stopped`，分别对应成功、失败和取消。
- 不让回调在工作开始之后才挂上。**发送器**（[[g:sender]]）是一段尚未开始的工作的描述，先和接收器组合，再启动。

剩下的设计，大多是这两点的推论。

## 用一个玩具模型看清 connect 和 start

下面是一个只有值通道的极简模型，不是 `std::execution` 的接口，但骨架相同：`just` 产生一个值，`then` 对它调用一个函数，`connect` 把发送器和接收器组合成**操作状态**（[[g:operation-state]]），`start` 才开始运行。

```cpp title="toy.cpp" run ok
#include <cstdio>
#include <utility>

// 极简模型：只有值通道，不是 std::execution 的接口
template<class T>
struct just_sender {
  T v;
  template<class R> struct op {
    T v; R r;
    void start() { std::move(r).set_value(v); }
  };
  template<class R> op<R> connect(R r) && {
    return {std::move(v), std::move(r)};
  }
};

template<class S, class F>
struct then_sender {
  S s; F f;
  template<class R> struct rcvr {
    F f; R r;
    template<class... A> void set_value(A&&... a) && {
      std::move(r).set_value(f(std::forward<A>(a)...));
    }
  };
  template<class R> auto connect(R r) && {
    return std::move(s).connect(
        rcvr<R>{std::move(f), std::move(r)});
  }
};

struct print_rcvr {
  void set_value(int v) && { std::printf("value %d\n", v); }
};

int main() {
  auto snd = then_sender{just_sender{6}, [](int x) {
    std::puts("then runs");
    return x * 7;
  }};
  std::puts("built");
  auto op = std::move(snd).connect(print_rcvr{});
  std::puts("connected");
  op.start();
}
```

本机 Clang 23（ASan + UBSan）输出 `built`、`connected`、`then runs`、`value 42`。三点值得注意：

1. 构造发送器、`connect` 都不运行用户代码，`then` 的函数体在 `start` 之后才执行。
2. `then_sender::connect` 把下游接收器包进自己的接收器，再交给上游的 `connect`。最后得到的 `op` 是一个嵌套的普通对象，里面装着整条链需要的全部状态，大小在编译期已知，就放在 `main` 的栈上。
3. 整条链都是可内联的直接调用。本机 `-O2` 下 `main` 的汇编里只剩三次 `puts` 和一次以常量 `42` 为实参的 `printf`，没有任何分配。

对比前面 `async` 的 4 次分配，这就是 [[P2006R1]] 把唯一的基本操作 `submit(sndr, rcvr)` 拆成 `connect` 和 `start` 两步的原因：由调用者决定操作状态放在哪里。代价也在第 2 点里：操作状态必须活到操作完成。标准还规定，复制或移动库提供的发送器产生的操作状态是非良构的（[[exec.opstate.general#3]]），所以它只能就地构造、就地使用。

## 标准接口长什么样

同样的结构放到标准接口里，用户通常只接触发送器算法和**调度器**（[[g:scheduler]]，执行资源的轻量句柄）：

```cpp title="依据当前草案；本机 libc++ 尚未提供发送器，不标判定"
#include <execution>
#include <cstdio>
namespace ex = std::execution;

int main() {
  ex::scheduler auto sch = ex::get_parallel_scheduler();
  auto a = ex::schedule(sch) | ex::then([] { return 6; });
  auto b = ex::schedule(sch) | ex::then([] { return 7; });
  auto work = ex::when_all(std::move(a), std::move(b))
            | ex::then([](int x, int y) { return x * y; });
  auto [v] = std::this_thread::sync_wait(std::move(work)).value();
  std::printf("%d\n", v);
}
```

`schedule(sch)` 产生一个在 `sch` 上完成的发送器，`then` 和 `when_all` 是**发送器适配器**（[[g:sender-adaptor]]），`sync_wait` 在当前线程上 `connect`、`start` 并阻塞等待结果。接收器和操作状态都由算法在内部生成，P2300 §5.1、§5.2 明确说它们只面向写发送器算法的人。四个概念的完整关系见 [[exec]]。

`sync_wait` 返回 `optional<tuple<...>>`：值完成时有值，停止完成时为空，错误完成时抛出异常（[[exec.sync.wait#11]]）。这三种结果直接对应接收器的三个入口。

## 取舍一：惰性还是急切

P2300 的早期修订里有些算法可以急切执行。§4.10 记录了删除它们的理由，核心问题是：一个已经在别的线程上运行的发送器，如果没有被 `connect` 和 `start` 就被销毁，析构函数该做什么？

| 策略 | 后果 | 标准库里的先例 |
|---|---|---|
| 定为未定义行为 | 出现异常时极难保证每个急切操作都被等待 | `std::thread` 的变体：析构时 `terminate` |
| 让它在后台继续运行 | 无法确定它用到的资源何时可以安全销毁，只能靠 `shared_ptr` 一类的手段 | `thread::detach` |
| 在析构函数里阻塞等待 | 保持结构化，但线程池里可能死锁 | `async` 的 `future`；`jthread` 先请求停止再等待 |

§4.10.1 的结论是三种都不令人满意。另外几条理由更偏向实现：

- 如果发送器一定是惰性的，算法可以假定 `start` 发生在工作开始之前，把几个操作按顺序串起来时不需要同步；要兼容急切发送器，就得按最坏情况防御，或者让每个发送器报告自己是否急切（§4.10.2）。
- 急切操作在启动时还不知道将来连接的接收器是否会请求停止，只能为类型擦除的停止回调预留空间，承担取消的运行时开销（§4.10.3）。
- 停止令牌、分配器、当前调度器等上下文信息是通过接收器在 `connect` 时向下传的，已经开始运行的操作拿不到它们（§4.10.4）。

这条决定落在 [[exec.adapt.general#3]] 的 ¶3.1：除非另有规定，发送器适配器在返回的发送器被 `connect` 且 `start` 之前，除了移动和复制实参之外不得产生可观察效果。

需要急切启动的工作并没有消失，而是改由 async scope 管理，见下文的结构化并发一节。

## 取舍二：取消为什么单独一个通道

既然有错误通道，取消为什么不当作一种错误？[[P1677R2]] 专门讨论了这个问题（它的标题从 R2 起改为把取消称作 *serendipitous-success*，大意是没有结果、但也不算失败）。主要理由有两条。

第一，算法对错误和取消的反应不同。一个泛型的 `retry` 应该在出错时重试，在被取消时停止；如果取消也走错误通道，`retry` 就得检查每个错误是不是取消，而不同的库用不同的类型表示取消。分开之后，`retry` 只需处理 `set_error`，`set_stopped` 原样向下传。

第二，取消在异步代码里很常见，把它报告成异常会给日志、调试和其他分析工具带来大量噪声。P1677R2 还回顾了更早用异常表示中断的尝试（`jthread` 早期修订里的 `std::interrupted`）在委员会里被删掉的经过。

这个三分法写进了异步操作的定义：一个已启动的异步操作最终恰好以成功、失败、取消三种**处置**（disposition）之一完成一次，其中取消完成不带任何结果数据（[[exec.async.ops#2]] ¶2.3）。

!!! std
    "After its start operation has begun executing, exactly one completion operation shall execute."
    `start` 开始执行之后，恰好执行一次完成操作。（[[exec.async.ops#8]]）

## 取舍三：取消请求怎样传到需要它的地方

`set_stopped` 是被取消的操作向下游报告结果的方式。另一个方向，即上游怎样请求一个已经开始的操作停下来，来自 [[P2175R0]]：接收器的环境提供一个停止令牌，操作在需要时查询它。这复用了 C++20 的 `std::stop_token` 一族（[[thread.stoptoken]]），P2300 又加入了 `stoppable_token` 概念、不分配内存的 `inplace_stop_token` 和永远不会请求停止的 `never_stop_token`。

几个细节说明了这个设计的取向：

- **取消是可选的。** 接收器的环境不提供停止令牌时，`get_stop_token` 返回 `never_stop_token`（[[exec.get.stop.token#2]] ¶2.2）。它的 `stop_possible()` 在编译期就是 `false`，处理取消的代码可以整个被优化掉（P2300 §4.9.2）。
- **用户一般不碰令牌。** `when_all` 为子操作提供一个自己的 `inplace_stop_source`，任何一个子操作以错误或停止完成时就请求停止（[[exec.when.all#17]]）。查询了令牌的兄弟操作可以提前结束；没查询的照常运行完，`when_all` 等所有子操作都完成后才向下游报告。
- **取消天生有竞争。** 停止请求可能从另一个线程在任意时刻到来，`start` 的实现要小心安排注册停止回调和启动操作的先后（§4.9.3）。[[exec.recv.concepts#3]] 因此规定停止令牌只需在操作的生存期内有效，停止回调必须在完成操作之前销毁。

P2300R10 自己也记录了一个未决的担忧：SG1 初审时对单线程场景下这套机制的运行时开销有疑问（§4.9.4）。

## 取舍四：结构化并发

[[P2300R10]] 在并入工作草案之前删掉了 `ensure_started`、`start_detached` 和 `execute`。理由来自 [[P3187R1]]：它们都会急切启动一项工作，又不保证有人等待它结束，于是重新面对上面那张表里的同一个问题。P3187R1 特别指出，`ensure_started` 返回的发送器看起来可以和其他算法正常组合，大多数时候也确实能工作，数据竞争只在失败路径上出现。

替代品是 async scope（[[P3149R11]]）：急切启动的工作必须先和一个**异步作用域**（[[g:async-scope]]）关联，作用域负责在结束前等待所有关联的工作完成。

```cpp title="依据当前草案；本机 libc++ 尚未提供，不标判定"
#include <execution>
namespace ex = std::execution;

void serve(ex::scheduler auto sch, int requests) {
  ex::counting_scope scope;
  for (int i = 0; i < requests; ++i)
    ex::spawn(ex::schedule(sch) | ex::then([i] { /* 处理请求 i */ }),
              scope.get_token());
  // 等所有 spawn 出去的工作结束，scope 才能销毁
  std::this_thread::sync_wait(scope.join());
}
```

`spawn` 尝试把发送器关联到作用域，成功后急切启动它（[[exec.spawn#1]]）。忘记 `join` 不会悄悄留下悬垂的工作：计数作用域析构时，除非它已经 join 完毕或者从未被使用过，否则调用 `std::terminate`（`simple_counting_scope` 的规定见 [[exec.simple.counting.ctor#2]]）。这和 `std::thread` 的选择相同，只是现在有了一个明确的等待点。

同样的理由后来还删掉了 `split`。[[P3682R0]] 指出，`split` 产生的发送器共享一个状态，这个状态在创建发送器时就要动态分配，无法使用接收器环境里的分配器；对第二个及以后的使用者来说，操作已经被第一个使用者启动，又成了急切的。当前草案的 [[exec.adapt]] 里没有 `split`。

## 取舍五：怎样定制

标准算法需要能被执行资源替换（GPU 调度器要自己的 `bulk`），用户也要能写自己的接收器和发送器。P2300 的定制机制改过两次。

### 从 tag_invoke 到成员函数

P2300 早期修订用 `tag_invoke`（[[P1895R0]]）：所有定制都是名为 `tag_invoke` 的[[g:hidden-friend|隐藏友元]]，靠[[g:argument-dependent-lookup|实参依赖查找]]（ADL）找到，第一个参数的类型区分定制的是哪个操作。R9 按 [[P2855R1]] 改成了具名成员函数。P2300 §5.9 给出了同一个接收器的两种写法：

<div class="compare" markdown="1">

```cpp title="R8 及以前（tag_invoke）"
struct my_receiver {
  friend void tag_invoke(
      execution::set_value_t,
      my_receiver&& self,
      int value) noexcept {
    std::cout << value;
  }
};
```

```cpp title="R9 起（成员函数）"
struct my_receiver {
  using receiver_concept =
      execution::receiver_tag;

  void set_value(int value)
      && noexcept {
    std::cout << value;
  }
};
```

</div>

右边的 `receiver_tag` 是当前草案的名字，P2300R10 里叫 `receiver_t`。[[P3940R0]] 提议把 `<execution>` 的四个概念标签从 `_t` 改为 `_tag`，与标准库里其他概念标签的命名一致，当前草案采用了新名字。

P2855R1 把目标概括为不在任何地方使用 ADL。它的理由主要来自实现：ADL 会搜索模板实参的关联命名空间，为了控制重载集的大小，实现者要把每个算法的内部类型放进嵌套的细节命名空间，再在泛型代码里把模板参数包装起来，防止它们的命名空间被 ADL 搜到。换成成员函数，这些手段都不需要了。ADL 和定制点的一般问题见 [[topics/name-lookup-and-customization]]。

查询是唯一保留标签参数的地方：环境的 `query(get_stop_token_t)` 这类成员以查询对象为第一个参数，这样一个包装类型可以用一个成员模板转发它不认识的所有查询。

这条决定在条文里的痕迹很直接：`set_value(rcvr, vs...)` 表达式等价于 `rcvr.set_value(vs...)`，并且要求它是 `noexcept` 的（[[exec.set.value#1]]）；`connect(sndr, rcvr)` 首先尝试 `new_sndr.connect(rcvr)`（[[exec.connect#6]] ¶6.1）。由于没有了 `receiver_adaptor`，接收器适配器改用继承来写，所以 [[exec.recv.concepts#2]] 规定 `final` 类不满足 `receiver`。

### 算法定制与 domain

成员函数解决了基本操作的定制，算法（`then`、`bulk`）的定制是另一个问题。P2300R7 的做法是向前驱发送器询问它的完成调度器，按调度器分派。[[P2999R3]] 指出这不够：`just(42)` 在被启动之前不知道自己会在哪里完成；`when_all(s1, s2)` 在哪个调度器上完成取决于运行时谁最后完成；`on(sch, then(just(), f))` 里的 `then` 在指定调度器之前就已经构造好了。

P2999R3 的办法是让发送器报告一个**domain**（执行域的标签类型），并且除了在构造发送器时分派，还在 `connect` 时借助接收器的环境再分派一次。P2999 的措辞漏掉了后一半，[[P3303R1]] 补上：`connect` 和 `get_completion_signatures` 先用 `transform_sender` 变换发送器。C++26 定稿前 [[P3826R5]] 又修改了完成 domain 的查询方式，细节见 [[exec.snd.transform]] 和 [[history/executors-to-execution]]。

## 协程：不是基础，但是一等公民

P2300 不把协程作为基础，但让两者可以互相使用（§4.15–4.17）：

- 任何不依赖特定 promise 类型的可等待类型都自动满足 `sender`，`sync_wait` 可以直接接受一个协程任务。
- 协程的 promise 类型借助 `with_awaitable_senders` 后，可以 `co_await` 一个只以单个值完成的发送器（[[exec.as.awaitable]]）。
- 被等待的发送器以 `set_stopped` 完成时，协程的行为类似抛出了一个无法被 `catch(...)` 捕获的异常，沿着协程调用链一直展开，直到某一层用 `stopped_as_optional` 之类的适配器把停止转换成值或错误。

P2300 本身没有协程任务类型，`std::execution::task` 由 [[P3552R3]] 加入 C++26，任务怎样回到启动它的调度器由 [[P3941R4]] 规定（[[exec.task]]）。

## 措辞：[exec] 一章

P2300R10 新增了 [[exec]] 一章（当前草案的第 33 章），并在 [[thread.stoptoken]] 里加入了新的停止令牌类型。下表把上面的设计对应到条款：

| 设计 | 条款 |
|---|---|
| 异步操作恰好以三种处置之一完成一次 | [[exec.async.ops#2]]、[[exec.async.ops#8]] |
| 操作状态在异步操作结束前被销毁是 UB | [[exec.async.ops#7]]、[[exec.opstate.general#2]] |
| 复制或移动库提供的发送器产生的操作状态是非良构的 | [[exec.opstate.general#3]] |
| 完成函数只接受接收器右值，且必须是 `noexcept` | [[exec.set.value#1]] |
| `connect` 先变换发送器，再调用成员 `connect` | [[exec.connect#2]]、[[exec.connect#6]] |
| 适配器在 `start` 之前没有可观察效果 | [[exec.adapt.general#3]] |
| 停止令牌从接收器的环境查询，默认为 `never_stop_token` | [[exec.get.stop.token#2]] |
| `final` 类不是接收器 | [[exec.recv.concepts#2]] |
| 急切工作必须关联到 async scope | [[exec.scope]]、[[exec.spawn]] |

C++17 已经有头文件 `<execution>`（执行策略，见 [[execpol]]），P2300 只是往里加内容，所以 Annex C 的 [[diff.cpp23]] 没有相关的不兼容条目。特性测试宏 `__cpp_lib_senders` 在当前草案里是 `202506L`。

## 代价与批评

**接口复杂。** 写一个新的发送器算法要处理操作状态、接收器包装、环境转发和完成签名。P2300 的回应是用户大多只用现成的算法；它也引用了用户的反馈，大意是发送器/接收器本身不简单，但不是复杂性的主要来源（§1.10.3）。

**元编程重，错误信息难读。** 每个发送器都要在编译期计算自己的[[g:completion-signature|完成签名]]。[[P3557R3]] 的引言直说，这是写发送器算法最难的部分，用错算法会得到深埋在元程序里的大段错误。它的解决办法是在常量求值中抛出异常来报告类型错误，这依赖 C++26 的 [[papers/constexpr-exceptions|constexpr 异常]]，于是 `get_completion_signatures` 改成了无实参的 `consteval` 函数模板。

**编译时间。** 整条发送器链在编译期展开成一个嵌套类型，这是玩具模型里能内联成一个常量的原因，也意味着模板实例化的数量随链长增长。本机没有可用的实现，无法给出测量数据。

**生存期交给了调用者。** 不分配内存的代价是操作状态必须活到操作完成，否则是未定义行为（[[exec.opstate.general#2]]）。`sync_wait`、`spawn` 这类消费者替用户管理了这件事，手写 `connect`/`start` 的代码则要自己保证。

**没接住的需求。** 并行算法仍然只接受执行策略，不能指定调度器；标准网络库没有进入 C++26。这两件事和执行器之争的关系见 [[history/executors-to-execution]]。

## 后续提案与实现现状

| 提案 | 内容 | 当前草案 |
|---|---|---|
| [[P3187R1]] | 删除 `ensure_started`、`start_detached`、`execute` | 已在 P2300R10 中删除 |
| [[P3149R11]] | async scope：`counting_scope`、`spawn`、`spawn_future` | 已并入，[[exec.scope]] |
| [[P2079R10]] | `parallel_scheduler`，后端可替换 | 已并入，[[exec.par.scheduler]] |
| [[P3552R3]] | 协程任务类型 `task` | 已并入，[[exec.task]] |
| [[P3682R0]] | 删除 `split` | 当前草案没有 `split` |
| [[P3557R3]] | 用 constexpr 异常报告完成签名的错误 | 已并入，[[exec.getcomplsigs]] |
| [[P3826R5]] | 修改算法定制的 domain 查询 | 已并入，[[exec.snd.transform]] |

**实现。** P2300 §1.10 列出的实践经验主要来自两个库：Meta 的 libunifex，以及 NVIDIA 的参考实现 stdexec。后者按规范编写，用来发现规范中的错误，后来也提供了 CUDA 等调度器。

本机 Homebrew Clang 23.1.3 的 libc++ 在 `-std=c++2c` 下（加不加 `-fexperimental-library` 都一样）没有 `std::execution::just`，没有 `std::inplace_stop_source`，也不定义 `__cpp_lib_senders`。所以使用标准接口的代码都没有判定标记。GCC 和 MSVC 本机未验证。

## 思考题

!!! question "1. 手写 connect/start"
    下面的函数有什么问题？
    
    ```cpp
    void fire(ex::scheduler auto sch, auto rcvr) {
      auto op = ex::connect(ex::schedule(sch), std::move(rcvr));
      ex::start(op);
    }
    ```

<details markdown="1">
<summary>答案</summary>

`start` 之后工作可能还在 `sch` 上排队，`fire` 返回时 `op` 就被销毁了。在异步操作的生存期内销毁操作状态是未定义行为（[[exec.opstate.general#2]]、[[exec.async.ops#7]]）。这正是 `start_detached` 想解决、又因为没人等待而被删掉的问题。应该用 `spawn` 把工作关联到一个 async scope，并在作用域结束前 `join`。

</details>

!!! question "2. `just(42)` 在哪里完成"
    为什么不能只靠前驱发送器的完成调度器来选择 `then` 的实现？

<details markdown="1">
<summary>答案</summary>

`just(42)` 在启动它的执行资源上同步完成，构造时不知道会被谁启动，所以它没有完成调度器。`then(just(42), f)` 被 `starts_on(gpu, ...)` 包住之后才在 GPU 上运行，而 `then` 在那之前就已经构造好了。所以 [[P2999R3]] 加入了 `connect` 时的第二次分派，此时接收器的环境已经说明了操作从哪里启动（[[exec.connect#2]]）。

</details>

!!! question "3. 把取消当作错误"
    设想一个只有 `set_value` 和 `set_error` 两个通道的设计，取消用一个特殊的异常类型表示。一个泛型的 `retry` 算法要多做什么？

<details markdown="1">
<summary>答案</summary>

`retry` 必须检查每个错误是不是表示取消的那种，否则会在用户已经要求停止时继续重试。而它是泛型算法，不知道上游用的是哪个库的取消类型。三个通道把这个判断变成了类型层面的分派：`retry` 只定制错误通道，停止通道原样转发（[[P1677R2]]）。

</details>
