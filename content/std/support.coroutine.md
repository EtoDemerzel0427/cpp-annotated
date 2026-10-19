---
title: 协程支持
summary: 头文件 <coroutine> 是协程的语言规则依赖的库部分：编译器用 coroutine_traits 找到 promise 类型，用 coroutine_handle 恢复、销毁协程；另有对称转移用的 noop 协程，以及 suspend_always、suspend_never。
status: done
covers: *
papers: P0912R5, P0913R1
related: dcl.fct.def.coroutine, expr.await, expr.yield, stmt.return.coroutine, namespace.std, unord.hash, cmp
tags: 标准库, 协程, coroutine_handle, 对称转移
updated: 2026-10-19
---

!!! tldr
    - 编译器通过 `std::coroutine_traits<R, 形参类型...>::promise_type` 找到协程的 promise 类型，默认取返回类型里嵌套的 `R::promise_type`。
    - `std::coroutine_handle` 是一个不拥有协程的指针：复制它不复制协程，销毁它也不销毁协程，协程帧只能由 `destroy()` 或协程自己结束时释放。
    - `resume()` 要求协程已挂起且不在最终挂起点，`destroy()` 和 `done()` 要求协程已挂起；违反就是未定义行为。
    - 在 `std::thread`、`std::jthread` 和主线程之间换线程恢复协程是有保证的，其他执行代理上由实现定义。
    - `noop_coroutine()` 返回一个恢复了也什么都不做的句柄，用于对称转移中没有下一个协程可恢复的情形。

## 语言依赖这个头文件

C++20 协程的语言规则（[[dcl.fct.def.coroutine]]、[[expr.await]]、[[expr.yield]]）规定了一种变换：函数体里出现 `co_await`、`co_yield` 或 `co_return`，这个函数就是**协程**，编译器把它的函数体改写成对一个 **promise 对象**的一系列调用。promise 对象存放在**协程帧**里，协程帧是编译器为协程分配的、保存局部变量和挂起位置的存储。

有两件事核心语言交给了 `<coroutine>`：

- promise 是什么类型。编译器从协程的返回类型和形参类型出发，通过 `std::coroutine_traits` 找到它。
- 怎样从外面恢复一个挂起的协程。编译器把协程帧的句柄以 `std::coroutine_handle` 的形式交给等待者的 `await_suspend`，用户通过它恢复、销毁协程，访问 promise。

所以定义协程之前必须包含 `<coroutine>`，否则这些名字找不到，程序非良构：

```cpp error
struct R { struct promise_type; };
R f() { co_return; }   // error: 没有包含 <coroutine>
```

本机 Clang 23 的诊断是 `std::coroutine_traits type was not found; include <coroutine> before defining a coroutine`。核心语言依赖库的场合不多，另外几处是 `<initializer_list>`、`<compare>` 和 `<typeinfo>`。

¶1 [support.coroutine.general] `<coroutine>` 定义为协程提供编译期和运行期支持的若干类型。整个头文件是 freestanding 的，并且包含 `<compare>`，因为 `coroutine_handle` 的 `<=>` 返回 `strong_ordering`。

## 找到 promise 类型 [coroutine.traits]

对一个返回类型为 `R`、形参类型为 `P1, ..., Pn` 的协程，promise 类型是 `std::coroutine_traits<R, P1, ..., Pn>::promise_type`（[[dcl.fct.def.coroutine#3]]）。如果协程是非静态成员函数，形参类型列表前面还要加上对象形参的类型，例如隐式对象成员函数的 `C&`。

[coroutine.traits.primary] ¶1 主模板的规定是：如果 `R::promise_type` 是一个有效的类型名，`coroutine_traits<R, ArgTypes...>` 就有一个公开成员

```cpp
using promise_type = R::promise_type;
```

否则它没有任何成员，协程的定义也就非良构。这里的有效按模板实参推导（[[temp.deduct]]）的意义判断，所以 `R` 没有 `promise_type` 时不会引起硬错误。这就是通常把 `promise_type` 嵌套在返回类型（`Task`、`Generator`）里的原因。

¶2 程序也可以特化 `coroutine_traits`，特化必须有一个公开的嵌套类型 `promise_type`。返回类型不是自己能修改的类，例如 `void`，就要用这种办法。按 [[namespace.std]]，特化标准库模板必须依赖于至少一个程序定义的类型，这可以借形参类型满足：

```cpp run title="coroutine-traits.cpp" ok
#include <coroutine>
#include <cstdio>
#include <exception>

struct Detached {};   // 程序定义的类型，用作标签形参

template<class... Args>
struct std::coroutine_traits<void, Detached, Args...> {
  struct promise_type {
    void get_return_object() {}
    std::suspend_never initial_suspend() noexcept { return {}; }
    std::suspend_never final_suspend() noexcept { return {}; }
    void return_void() {}
    void unhandled_exception() { std::terminate(); }
  };
};

void task(Detached, int x) {   // 返回 void 的协程
  std::printf("running %d\n", x);
  co_return;
}

int main() { task(Detached{}, 42); }
```

`final_suspend` 返回 `suspend_never`，协程结束时帧自动销毁，所以没有任何句柄需要管理。

## 协程句柄 [coroutine.handle]

### 一个生成器

```cpp run title="generator.cpp" ok
#include <coroutine>
#include <exception>
#include <utility>

template<class T>
class Generator {
public:
  struct promise_type {
    T current;
    Generator get_return_object() {
      return Generator{
        std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    // 创建后先挂起：惰性
    std::suspend_always initial_suspend() noexcept { return {}; }
    // 结束时挂起：帧由 Generator 销毁
    std::suspend_always final_suspend() noexcept { return {}; }
    std::suspend_always yield_value(T v) {
      current = std::move(v);
      return {};
    }
    void return_void() {}
    void unhandled_exception() { std::terminate(); }
  };

  explicit Generator(std::coroutine_handle<promise_type> h) : h_(h) {}
  Generator(Generator&& o) noexcept : h_(std::exchange(o.h_, {})) {}
  ~Generator() { if (h_) h_.destroy(); }  // 要求：已挂起

  bool next() {
    h_.resume();         // 要求：已挂起，且不在最终挂起点
    return !h_.done();   // 是否停在了最终挂起点
  }
  const T& value() const { return h_.promise().current; }

private:
  std::coroutine_handle<promise_type> h_;
};

Generator<int> iota(int n) {
  for (int i = 0; i < n; ++i) co_yield i;
}

int main() {
  auto g = iota(4);
  int sum = 0;
  while (g.next()) sum += g.value();   // 0 + 1 + 2 + 3
  return sum == 6 ? 0 : 1;
}
```

`get_return_object` 用 `from_promise` 从 promise 得到句柄，交给返回对象 `Generator` 保存。之后 `Generator` 用这个句柄恢复协程（`resume`）、判断协程是否结束（`done`）、读出 promise 里的值（`promise`），最后在析构函数里销毁协程（`destroy`）。下面逐个看这些操作的规定。

C++23 的 `std::generator`（`<generator>`）是生产级的实现，支持递归 `co_yield` 和分配器。

### 两种句柄

```cpp
template<class Promise = void> struct coroutine_handle;   // 知道 promise 类型
template<> struct coroutine_handle<void>;                 // 类型擦除：coroutine_handle<>
```

`coroutine_handle<>`（即 `coroutine_handle<void>`）能指代任何协程，但不能访问 promise。`coroutine_handle<Promise>` 多了 `from_promise` 和 `promise()`，可以隐式转换为 `coroutine_handle<>`（[coroutine.handle.conv]）。反方向没有转换，需要时写 `coroutine_handle<P>::from_address(h.address())`，由程序自己保证 promise 类型正确。

两者都只有一个仅用于说明的成员 `void* ptr`，也就是协程帧的地址。

[coroutine.handle.general] ¶1 `coroutine_handle<T>` 的对象叫做**协程句柄**（[[g:coroutine-handle]]），指代一个挂起的或正在执行的协程。`address()` 返回空指针的句柄不指代任何协程。两个句柄指代同一个协程，当且仅当它们的 `address()` 返回相同的非空值。

句柄不拥有协程：复制句柄不复制协程，句柄销毁也不影响协程。协程帧只在两种情况下释放：有人调用 `destroy()`，或者协程执行结束而 `final_suspend` 不挂起。所以协程的返回类型几乎都像 `unique_ptr` 一样管理句柄，上面的 `Generator` 就是这样。

¶2 程序声明 `coroutine_handle` 的显式特化或偏特化，行为未定义。注意这里是 UB，而 `initializer_list`（[[support.initlist]]）和 `type_order`（[[cmp]]）的同类规定是非良构。

### 构造 [coroutine.handle.con]

| 成员 | 规定 |
|---|---|
| 默认构造、`coroutine_handle(nullptr_t)` | ¶1 `address() == nullptr` |
| `static from_promise(Promise& p)` | ¶2 要求 `p` 是某个协程的 promise 对象；¶3–¶4 返回指代该协程的句柄 `h`，`addressof(h.promise()) == addressof(p)` |
| `operator=(nullptr_t)` | ¶5 `address() == nullptr` |

`from_promise` 是从 promise 回到句柄的唯一途径。它能实现，是因为 promise 对象在协程帧里的位置是固定的，实现从 promise 的地址减去一个偏移就得到帧的地址。传入一个不是协程 promise 的对象，违反前置条件，行为未定义。

### 导出和导入地址 [coroutine.handle.export.import]

- ¶1 `address()` 返回 `ptr`。
- ¶2 `coroutine_handle<>::from_address(addr)` 要求 `addr` 来自先前对某个 `coroutine_handle` 特化的对象调用的 `address()`。
- ¶4 `coroutine_handle<Promise>::from_address(addr)` 要求更严格：`addr` 必须来自同一个 `Promise` 的 `coroutine_handle<Promise>`。

这对函数让句柄可以穿过只接受 `void*` 的 C 接口，例如 `epoll_event.data.ptr` 或操作系统回调的 `void* context`。

### 观察 [coroutine.handle.observers]

¶1 `explicit operator bool()` 返回 `address() != nullptr`。

¶2–¶3 `done()` 要求句柄指代一个挂起的协程；协程挂起在**最终挂起点**（执行 `co_await promise.final_suspend()` 时的挂起点）就返回 `true`，否则返回 `false`。

所以 `done()` 不能用来查询协程是否还存在。对空句柄、已经销毁的协程或正在执行的协程调用 `done()`，都违反前置条件。

### 恢复和销毁 [coroutine.handle.resumption]

| 操作 | 前置条件 | 效果 |
|---|---|---|
| `resume()`、`operator()()` | ¶2 指代一个挂起的协程，且不在最终挂起点 | ¶3 恢复协程的执行 |
| `destroy()` | ¶4 指代一个挂起的协程，可以在最终挂起点 | ¶5 销毁协程：析构作用域内的对象、promise 和形参副本，释放协程帧（[[dcl.fct.def.coroutine]]） |

¶1 规定了换线程恢复：

!!! std
    Resuming a coroutine via `resume`, `operator()`, or `destroy` on an execution agent other than the one on which it was suspended has implementation-defined behavior unless each execution agent either is an instance of `std::thread` or `std::jthread`, or is the thread that executes `main`.

**执行代理**（execution agent）是执行一个控制流的实体，线程是最常见的一种（[[thread.req.lockable.general]]）。协程在一个执行代理上挂起，在另一个上恢复，只有两者都是 `std::thread`、`std::jthread` 或主线程时才有保证；其他执行代理之间，例如并行算法的工作单元、某些平台的纤程，由实现定义。

注 1 提醒，在另一个执行代理上恢复的协程不应依赖线程身份不变，例如跨挂起点持有互斥锁，因为 `std::mutex` 必须由加锁的线程解锁。同样的道理也适用于 `thread_local` 变量。注 2 提醒，并发地恢复同一个协程可能造成数据竞争。

### 访问 promise [coroutine.handle.promise]

¶1–¶2 `promise()` 要求句柄指代一个协程，返回它的 promise 的引用。这里不要求协程已挂起，协程执行期间也可以通过句柄访问 promise。

### 比较和哈希 [coroutine.handle.compare] [coroutine.handle.hash]

¶1 `==` 比较 `address()`。¶2 `<=>` 返回 `compare_three_way()(x.address(), y.address())`。用 `compare_three_way` 而不用内建的 `<`，是因为它对不相关的指针也给出一个全序（[[comparisons.three.way]]）。两个运算符的形参都是 `coroutine_handle<>`，任何 `coroutine_handle<P>` 都能经隐式转换使用。

`hash<coroutine_handle<P>>` 是启用的（[[unord.hash]]），所以句柄可以直接放进 `unordered_set`。

!!! impl "Clang 和 libc++ 的实现"
    libc++ 的 `coroutine_handle` 是对 Clang 内建函数的薄包装：`resume()` 调用 `__builtin_coro_resume`，`destroy()` 调用 `__builtin_coro_destroy`，`done()` 调用 `__builtin_coro_done`，`promise()` 和 `from_promise()` 调用 `__builtin_coro_promise`，用 promise 的对齐值在帧地址和 promise 地址之间换算。在 Clang 的实现中，协程帧开头是 resume 和 destroy 两个函数指针，`resume()` 就是一次通过帧内函数指针的间接调用。所以 `coroutine_handle<>` 不知道 promise 类型，也能恢复任何协程。

## noop 协程与对称转移 [coroutine.noop]

### 对称转移需要一个空目标

`await_suspend` 可以返回一个 `coroutine_handle<>`，意思是挂起当前协程，然后立即恢复返回的那个协程（[[expr.await]]）。这叫**对称转移**（symmetric transfer）。编译器把它实现成尾调用，所以一长串 `co_await` 互相恢复时，栈不会一层层加深。

可是有时没有下一个要恢复的协程，例如一个任务结束了，却没有人在等它。这时 `await_suspend` 需要返回一个什么也不做的句柄，这就是 `noop_coroutine()`：

```cpp run title="symmetric-transfer.cpp" ok
#include <coroutine>
#include <exception>
#include <utility>

struct Task {
  struct promise_type {
    int value = 0;
    std::coroutine_handle<> continuation;   // 等待这个任务的协程
    Task get_return_object() {
      return Task{
        std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    struct FinalAwaiter {
      bool await_ready() noexcept { return false; }
      std::coroutine_handle<>
      await_suspend(std::coroutine_handle<promise_type> h) noexcept {
        auto c = h.promise().continuation;
        // 有等待者就恢复它；没有就转移到 noop 协程，
        // 控制回到 resume() 的调用者
        return c ? c : std::noop_coroutine();
      }
      void await_resume() noexcept {}
    };
    FinalAwaiter final_suspend() noexcept { return {}; }
    void return_value(int v) { value = v; }
    void unhandled_exception() { std::terminate(); }
  };

  bool await_ready() { return false; }
  std::coroutine_handle<> await_suspend(std::coroutine_handle<> awaiting) {
    h_.promise().continuation = awaiting;
    return h_;   // 对称转移：直接恢复被等待的任务
  }
  int await_resume() { return h_.promise().value; }

  explicit Task(std::coroutine_handle<promise_type> h) : h_(h) {}
  Task(Task&& o) noexcept : h_(std::exchange(o.h_, {})) {}
  ~Task() { if (h_) h_.destroy(); }
  std::coroutine_handle<promise_type> h_;
};

Task leaf() { co_return 20; }
Task root() {
  int a = co_await leaf();
  int b = co_await leaf();
  co_return a + b + 2;
}

int main() {
  Task t = root();
  t.h_.resume();   // 启动 root；全部完成后经 noop 协程回到这里
  return (t.h_.done() && t.h_.promise().value == 42) ? 0 : 1;
}
```

`root` 等待 `leaf` 时，`Task::await_suspend` 记下等待者，然后返回 `leaf` 的句柄，直接转入 `leaf`。`leaf` 结束时，`FinalAwaiter` 返回等待者 `root` 的句柄，转回 `root`。`root` 自己结束时没有等待者，返回 `noop_coroutine()`，控制回到 `main` 中 `resume()` 的调用处。

### noop 协程的规定

[coroutine.promise.noop] ¶1 `noop_coroutine_promise` 是一个空结构体，作为 noop 协程的 promise 类型。`coroutine_handle<noop_coroutine_promise>`（别名 `noop_coroutine_handle`）是一个显式特化，它的成员与通用版本有几处不同：

| 成员 | noop 版本的规定 |
|---|---|
| `explicit operator bool()` | 总是 `true` |
| `done()` | 总是 `false`，`constexpr noexcept`，没有前置条件 |
| `resume()`、`operator()()`、`destroy()` | 没有效果，`constexpr noexcept`；转换为 `coroutine_handle<>` 后调用它们，同样没有可观察的效果 |
| `promise()` | 返回与这个句柄关联的 promise 对象 |
| `address()` | 返回 `ptr`，而 `ptr` 总是非空 |
| 构造函数 | 私有，只能通过 `noop_coroutine()` 得到 |

[coroutine.noop.coroutine] ¶1 `noop_coroutine()` 返回一个句柄，它指代的协程在恢复或销毁时没有可观察的效果。¶2 两次调用得到的句柄可能相等，也可能不相等。

!!! impl
    Clang 提供内建函数 `__builtin_coro_noop()`，返回一个静态的协程帧，它的 resume 和 destroy 函数都是空函数，libc++ 用它构造 `noop_coroutine_handle`。GCC 没有这个内建函数，libc++ 在 GCC 下自己构造一个静态的假帧。帧是静态的，所以 `address()` 永远非空。

## 平凡 awaitable [coroutine.trivial.awaitables]

```cpp
struct suspend_never {
  constexpr bool await_ready() const noexcept { return true; }
  constexpr void await_suspend(coroutine_handle<>) const noexcept {}
  constexpr void await_resume() const noexcept {}
};
struct suspend_always {
  constexpr bool await_ready() const noexcept { return false; }
  constexpr void await_suspend(coroutine_handle<>) const noexcept {}
  constexpr void await_resume() const noexcept {}
};
```

¶1 的注说明，它们分别让 `co_await` 从不挂起和总是挂起，两种情况都不产生值。最常见的用法是作为 `initial_suspend()` 和 `final_suspend()` 的返回值：

| | 返回 `suspend_always` | 返回 `suspend_never` |
|---|---|---|
| `initial_suspend()` | 惰性：创建后先挂起，第一次 `resume()` 才开始执行 | 急切：创建后立即执行 |
| `final_suspend()` | 结束后停在最终挂起点，句柄的持有者负责 `destroy()` | 结束时自动销毁帧，之后所有句柄都悬垂 |

[[dcl.fct.def.coroutine#15]] 要求 `co_await promise.final_suspend()` 不是潜在抛出的。这就是这两个类型的成员都是 `noexcept` 的原因，自定义的 final awaiter 也必须全部是 `noexcept`。

!!! history
    协程先以技术规范（Coroutines TS）的形式发布，[[P0912R5]] 把它合并进 C++20。对称转移和 `noop_coroutine` 由 [[P0913R1]] 加入，解决了早期设计中每次 `co_await` 恢复另一个协程都要多占一层栈的问题。

## 常见错误

!!! pitfall "对已经结束的协程调用 `resume()`"
    协程停在最终挂起点后，`resume()` 的前置条件不再满足，调用它是 UB。生成器在恢复之前要先用 `done()` 检查，或者像上面的 `Generator::next` 那样在恢复之后检查。

!!! pitfall "`final_suspend` 不挂起，之后又调用 `destroy()`"
    `final_suspend` 返回 `suspend_never` 时，协程结束就自动释放了帧，句柄随之悬垂。返回对象的析构函数如果再调用 `destroy()`，就是对同一个帧释放两次。

!!! pitfall "`await_suspend` 交出句柄后继续使用 awaiter"
    调用 `await_suspend` 之前，协程已经被视为挂起（[[expr.await#5.1]]），所以 `await_suspend` 把句柄交给另一个线程后，那个线程立即 `resume()` 是允许的。但协程一旦在别处恢复，awaiter 对象和协程帧里的局部变量就可能被修改或销毁；`await_suspend` 在交出句柄之后再访问它们，就会与另一个线程发生数据竞争，甚至访问已销毁的对象。交出句柄应当是 `await_suspend` 做的最后一件事。
