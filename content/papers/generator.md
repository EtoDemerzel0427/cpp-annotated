---
title: std::generator（P2502）
summary: C++20 有了协程却没有任何协程类型，人人手写生成器；C++23 的 std::generator 怎样决定第一个模板实参是引用类型、默认交出 T&&、co_yield 左值时复制，为什么递归生成只用一个类型和一个活动栈，分配器为什么从形参传入，以及它为什么只是单趟、只能移动的视图。
status: draft
order: 56
group: 标准库
since: c++23
papers: P2502R2, P2168R3, P2529R0, P0913R1, P1681R0, P2415R2, P2787R1, LWG3894, LWG3899
related: coro.generator, coro.generator.class, coro.generator.promise, coro.generator.iterator, range.elementsof, dcl.fct.def.coroutine, expr.await, expr.yield, range.view, lib.types.movedfrom, diff.cpp20.library, topics/coroutines, topics/ranges-design, topics/allocators-and-pmr, history/coroutines, papers/ranges-to
tags: generator, 协程, 范围, 视图, 分配器, 提案, C++23
updated: 2026-10-19
---

!!! tldr
    - C++20 只有协程的语言机制，没有协程类型。一个能用的生成器要自己写 promise、迭代器和所有权，写错一处就是悬垂或重复销毁；递归时逐层转发元素，每取一个元素要恢复的协程数与深度成正比。
    - [[P2502R2]]（建立在 [[P2168R3]] 之上）给出 `std::generator<Ref, V = void, Allocator = void>`。第一个实参决定引用类型，`generator<T>` 交出 `T&&`；这是比较了"按值"、`const T&`、`T&&` 三种默认之后的选择。
    - `co_yield` 只把操作数的地址存进 promise，不复制；唯一的例外是向 `T&&` 生成器 `co_yield` 左值，此时复制一份，让消费者的移动不会掏空协程里的变量。
    - 递归生成只用一个类型：`co_yield ranges::elements_of(g)` 把子生成器压进一个活动栈，用对称转移直接切换，取一个元素只恢复一个协程。异常沿这个栈逐层重新抛出。
    - 协程帧的分配器经由开头的 `allocator_arg, alloc` 两个实参传入，默认在类型里擦除。生成器是只能移动、单趟的视图，`begin()` 只能调用一次。

## C++20：有协程，没有生成器

C++20 加入了**协程**（[[g:coroutine|coroutine]]）：函数体里出现 `co_yield`、`co_await` 或 `co_return` 的函数可以在中途挂起，以后再从挂起处继续（[[dcl.fct.def.coroutine]]）。但标准只规定了一套改写协议，没有提供任何可以直接写在返回类型位置上的类型。机制本身见 [[topics/coroutines]]，这里只看写一个生成器要做什么。

**生成器**是最简单的协程类型：协程每执行一次 `co_yield`，遍历它的循环就拿到一个元素。下面是一个可以接上范围适配器的最小实现：

```cpp title="gen.cpp" run ok
#include <coroutine>
#include <cstddef>
#include <cstdio>
#include <exception>
#include <iterator>
#include <memory>
#include <ranges>
#include <utility>

template<class T>
class gen : public std::ranges::view_interface<gen<T>> {
public:
  struct promise_type {
    const T* cur = nullptr;            // 指向 co_yield 的操作数
    gen get_return_object() {
      return gen{handle::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    std::suspend_always yield_value(const T& v) noexcept {
      cur = std::addressof(v);
      return {};
    }
    void return_void() noexcept {}
    void unhandled_exception() { throw; }
  };
  using handle = std::coroutine_handle<promise_type>;

  struct iterator {
    using value_type = T;
    using difference_type = std::ptrdiff_t;
    handle h;
    const T& operator*() const { return *h.promise().cur; }
    iterator& operator++() { h.resume(); return *this; }
    void operator++(int) { ++*this; }
    bool operator==(std::default_sentinel_t) const { return h.done(); }
  };

  gen(gen&& o) noexcept : h_(std::exchange(o.h_, {})) {}
  gen& operator=(gen o) noexcept { std::swap(h_, o.h_); return *this; }
  ~gen() { if (h_) h_.destroy(); }

  iterator begin() { h_.resume(); return {h_}; }
  std::default_sentinel_t end() const noexcept { return {}; }

private:
  explicit gen(handle h) : h_(h) {}
  handle h_;
};

gen<int> fib() {
  int a = 0, b = 1;
  while (true) {
    co_yield a;
    a = std::exchange(b, a + b);
  }
}

static_assert(std::ranges::input_range<gen<int>>);
static_assert(std::ranges::view<gen<int>>);

int main() {
  for (int x : fib() | std::views::take(8))
    std::printf("%d ", x);             // 0 1 1 2 3 5 8 13
  std::printf("\n");
}
```

五十行里每一行都有讲究。`initial_suspend` 返回 `suspend_always`，生成器才是惰性的；`final_suspend` 也必须挂起，否则协程结束时帧自动销毁，`h.done()` 读的就是已释放的内存。`yield_value` 只存地址，靠的是 `co_yield` 的操作数要活到协程恢复。基类 `view_interface` 让 `enable_view` 为真，它才算一个视图（[[range.view]]）。

最容易出错的是所有权。协程帧只能销毁一次，生成器对象必须只能移动。少写了移动构造函数，编译器就会隐式生成复制构造函数：

```cpp title="copy.cpp" ub
#include <coroutine>
struct gen {
  struct promise_type {
    gen get_return_object() {
      return gen{std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    std::suspend_always yield_value(int) noexcept { return {}; }
    void return_void() noexcept {}
    void unhandled_exception() { throw; }
  };
  std::coroutine_handle<promise_type> h;
  ~gen() { if (h) h.destroy(); }
};

gen g() { co_yield 1; }

int main() {
  gen a = g();
  gen b = a;     // 隐式生成的复制构造函数：两个对象持有同一个句柄
}                // UB: b、a 先后析构，同一个协程帧被销毁两次
```

本机用 `-Wall -Wextra` 编译没有任何警告，AddressSanitizer 在第二次 `destroy()` 时报告 heap-use-after-free。

手写的版本还有两个设计问题。一是元素类型：上面的迭代器交出 `const T&`，消费者没法把元素移走，只能移动的类型根本用不了；改成交出 `T&`，消费者又能修改协程里的局部变量。二是递归，见下一节。cppcoro、folly、range-v3 各有一套生成器，在是否支持递归、怎样管理所有权上各不相同（[[P2502R2]] 的 Implementation and experience 一节）。

## 递归的代价

中序遍历一棵树，最自然的写法是递归：子树也是生成器，父生成器把子生成器的元素逐个转发出去。这样写的问题在于，消费者每要一个元素，`++` 恢复最外层的协程，它的 `for` 循环又恢复下一层，一直到真正产出元素的那一层。深度为 d 时，取一个元素要恢复 d 个协程。

[[P2168R3]] 的方案是让生成器直接把子生成器交出去，由消费者一侧记住当前最内层的协程：

<div class="compare" markdown="1">

```cpp
// 逐层转发
gen<int> slow(int n) {
  if (n == 0) co_return;
  co_yield n;
  for (int x : slow(n - 1))
    co_yield x;
}
```

```cpp
// 交给子协程
rgen<int> fast(int n) {
  if (n == 0) co_return;
  co_yield n;
  co_yield nested<int>{fast(n - 1)};
}
```

</div>

右边的 `rgen` 是按标准的规则手写的递归生成器。最外层的生成器拥有一个栈，记录当前嵌套的所有协程，栈顶是正在产出元素的那一个：

- `co_yield nested{child}` 把子协程压栈，然后直接切换过去；
- 迭代器的 `++` 总是恢复栈顶的协程，`*` 总是读栈顶协程的值；
- 子协程结束时在 `final_suspend` 里把自己弹出栈，直接切换回父协程。

"直接切换"用的是**对称转移**（symmetric transfer，[[P0913R1]]）：`await_suspend` 返回一个协程句柄，实现就恢复它（[[expr.await#5.1.1]]）。实现会把这次恢复编译成尾调用，所以不管嵌套多深，原生调用栈都不会增长（[[topics/coroutines]] 有更详细的说明）。

<details class="fine" markdown="1"><summary>完整程序：手写的递归生成器与计数</summary>

```cpp title="rec.cpp" run ok
#include <coroutine>
#include <cstdio>
#include <exception>
#include <iterator>
#include <memory>
#include <utility>
#include <vector>

long resumes = 0;   // 统计协程被恢复的次数

template<class T>
class rgen;

template<class T>
struct nested { rgen<T> g; };          // 相当于 ranges::elements_of

template<class T>
class rgen {
public:
  struct promise_type;
  using handle = std::coroutine_handle<promise_type>;
  using stack_t = std::vector<handle>;

  struct promise_type {
    const T* cur = nullptr;
    stack_t* stack = nullptr;          // 指向最外层 rgen 拥有的栈
    std::exception_ptr ex;

    rgen get_return_object() { return rgen{handle::from_promise(*this)}; }
    std::suspend_always initial_suspend() noexcept { return {}; }

    // 结束时把自己弹出栈，直接转去父协程
    auto final_suspend() noexcept {
      struct pop {
        bool await_ready() noexcept { return false; }
        std::coroutine_handle<> await_suspend(handle h) noexcept {
          stack_t& s = *h.promise().stack;
          s.pop_back();
          if (s.empty()) return std::noop_coroutine();
          ++resumes;
          return s.back();             // 对称转移
        }
        void await_resume() noexcept {}
      };
      return pop{};
    }

    std::suspend_always yield_value(const T& v) noexcept {
      cur = std::addressof(v);
      return {};
    }

    // co_yield nested{child}：把子协程压栈，直接转去子协程
    auto yield_value(nested<T> n) noexcept {
      struct push {
        rgen<T> child;
        bool await_ready() noexcept { return false; }
        std::coroutine_handle<> await_suspend(handle h) noexcept {
          stack_t& s = *h.promise().stack;
          child.h_.promise().stack = &s;
          s.push_back(child.h_);
          ++resumes;
          return child.h_;             // 对称转移
        }
        void await_resume() {
          if (auto e = child.h_.promise().ex) std::rethrow_exception(e);
        }
      };
      return push{std::move(n.g)};
    }

    void return_void() noexcept {}
    void unhandled_exception() {
      if (stack->size() == 1) throw;   // 最外层：抛给消费者
      ex = std::current_exception();   // 嵌套：交给父协程的 co_yield 重新抛出
    }
  };

  struct iterator {
    using value_type = T;
    using difference_type = std::ptrdiff_t;
    handle root;
    stack_t* stack;
    const T& operator*() const { return *stack->back().promise().cur; }
    iterator& operator++() { ++resumes; stack->back().resume(); return *this; }
    void operator++(int) { ++*this; }
    bool operator==(std::default_sentinel_t) const { return root.done(); }
  };

  rgen(rgen&& o) noexcept
    : h_(std::exchange(o.h_, {})), stack_(std::move(o.stack_)) {}
  ~rgen() { if (h_) h_.destroy(); }

  iterator begin() {
    stack_ = std::make_unique<stack_t>();
    h_.promise().stack = stack_.get();
    stack_->push_back(h_);
    ++resumes;
    h_.resume();
    return {h_, stack_.get()};
  }
  std::default_sentinel_t end() const noexcept { return {}; }

private:
  explicit rgen(handle h) : h_(h) {}
  handle h_;
  std::unique_ptr<stack_t> stack_;
};

// 一个只能逐层转发的生成器，用于对比
template<class T>
class gen {
public:
  struct promise_type {
    const T* cur = nullptr;
    gen get_return_object() { return gen{handle::from_promise(*this)}; }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    std::suspend_always yield_value(const T& v) noexcept { cur = &v; return {}; }
    void return_void() noexcept {}
    void unhandled_exception() { throw; }
  };
  using handle = std::coroutine_handle<promise_type>;
  struct iterator {
    using value_type = T;
    using difference_type = std::ptrdiff_t;
    handle h;
    const T& operator*() const { return *h.promise().cur; }
    iterator& operator++() { ++resumes; h.resume(); return *this; }
    void operator++(int) { ++*this; }
    bool operator==(std::default_sentinel_t) const { return h.done(); }
  };
  gen(gen&& o) noexcept : h_(std::exchange(o.h_, {})) {}
  ~gen() { if (h_) h_.destroy(); }
  iterator begin() { ++resumes; h_.resume(); return {h_}; }
  std::default_sentinel_t end() const noexcept { return {}; }
private:
  explicit gen(handle h) : h_(h) {}
  handle h_;
};

gen<int> slow(int n) {
  if (n == 0) co_return;
  co_yield n;
  for (int x : slow(n - 1)) co_yield x;   // 逐层转发
}
rgen<int> fast(int n) {
  if (n == 0) co_return;
  co_yield n;
  co_yield nested<int>{fast(n - 1)};      // 交给子协程
}
struct oops {};
rgen<int> thrower() { co_yield 0; throw oops{}; }
rgen<int> catcher() {
  bool caught = false;
  try { co_yield nested<int>{thrower()}; } catch (oops) { caught = true; }
  if (caught) co_yield -1;            // 处理器里不能写 co_yield
  co_yield 1;
}

int main() {
  for (int n : {10, 100, 1000}) {
    resumes = 0;
    for (int x : slow(n)) (void)x;
    long r1 = std::exchange(resumes, 0);
    for (int x : fast(n)) (void)x;
    std::printf("n=%4d: %6ld vs %4ld\n", n, r1, resumes);
  }
  // n=  10:     66 vs   31
  // n= 100:   5151 vs  301
  // n=1000: 501501 vs 3001
  for (int x : catcher()) std::printf("%d ", x);   // 0 -1 1
}
```

</details>

`slow(n)` 和 `fast(n)` 都产出 n 个元素，嵌套深度都是 n。本机计数，逐层转发一共恢复协程 (n+1)(n+2)/2 次，n = 1000 时是 501501 次；用栈和对称转移是 3n+1 次，n = 1000 时是 3001 次。用 `-O2` 计时，n = 1000 时前者约 4.7 ms，后者约 0.05 ms；`fast(1000000)` 在 `-O0` 下也能正常跑完，没有栈溢出。

## 设计空间

### 一个类型还是两个

cppcoro 把这个能力放在单独的 `recursive_generator` 里，普通的 `generator` 不支持递归。[[P2168R3]] 列出三种做法，[[P2502R2]] 原样沿用：

| 方案 | 问题 |
|---|---|
| 一个 `generator`，支持递归 | 每个生成器多两个指针的开销 |
| 另设 `recursive_generator`，可以嵌套两种生成器 | 性能收益很小，内存一样 |
| 另设 `recursive_generator`，只能嵌套同类 | 写生成器时就得猜它将来会不会被嵌套 |

第三种的问题最实际。一个返回 `generator` 的函数后来要在 `recursive_generator` 里使用，只能逐个转发，或者用适配函数包一层，两者都让每个元素多恢复一次协程。论文报告的测量是：不嵌套时两种实现看不出差别，支持递归也不妨碍 HALO（编译器把协程帧的堆分配优化掉）；深度嵌套时，支持对称转移的版本快得多。提案选了第一种。

单一类型还带来一个可以放宽的地方。promise 类型里和生成器模板实参有关的接口只有 `yield_value`，所以只要 `co_yield` 接受的类型相同，值类型或分配器不同的生成器也可以互相嵌套。当前草案的约束正是 `same_as<typename generator<R2, V2, Alloc2>::yielded, yielded>`（[[coro.generator.promise#10]]）。

### `elements_of`：交出范围还是交出元素

如果 `co_yield g` 本身就表示"交出 g 的所有元素"，有些情形会产生歧义：

```cpp
std::generator<int> f() { co_yield 42; }
std::generator<std::any> g() {
  co_yield f();   // 交出 42，还是交出一个 generator<int> 对象？
}
```

`std::any` 能装下任何可复制的对象，`generator<int>` 本来就可以作为一个元素交出去。[[P2168R3]] 从 R1 起引入标签 `ranges::elements_of`：`co_yield e` 永远交出 e 本身，`co_yield ranges::elements_of(e)` 才交出 e 的元素。既然有了标签，它顺带被推广到任意 `input_range`：对一个 `vector` 写 `co_yield ranges::elements_of(v)`，标准把它规定成先用一个内部生成器包装这个范围，再走嵌套生成器的路径（[[coro.generator.promise#13]]）。

[[P2502R2]] 把 `elements_of` 简化成一个只有 `range` 和 `allocator` 两个成员的聚合（[[range.elementsof]]）。

### 第一个模板实参：引用类型

范围有两个关联类型：**值类型**（`range_value_t`，存一份副本时用的类型）和**引用类型**（`range_reference_t`，解引用迭代器得到的类型），见 [[topics/ranges-design]]。生成器的模板实参怎样决定这两个类型，是整个提案修改次数最多的地方，一共经历了三个答案。

[[P2168R3]] 的第一个实参就是引用类型，值类型默认是它去掉 cv 和引用。这样最简单，但 `generator<std::string>` 的迭代器每次解引用都返回一个新的 `string` 纯右值。[[P2502R2]] 保留的旧讨论称它为严重的性能陷阱：用户只是写了最自然的 `generator<string>`，每个 `co_yield` 就要多付两次复制。

于是 [[P2502R2]] 的早期修订改为：第一个实参不是引用时，引用类型取 `const T&`。这样不复制了，但消费者只能读。[[P2529R0]] 主张改成 `T&&`，理由有三：

- 性能和只能移动的类型。用 `const T&` 时，`ranges::copy`、`ranges::to<vector>()`、`for (auto s : g)` 都要复制，元素是 `unique_ptr` 这类只能移动的类型时干脆编译不过，加上 `views::move` 也没用。
- 与返回 `T` 的函数一致。`generator<T>` 可以看作一个反复返回 `T` 的函数，调用者拿到的是自己的对象，可以移走，也可以修改。
- 规则简单：解引用总是得到 `FirstArg&&`，引用折叠自动处理 `generator<T&>` 这类写法。

反对的理由是 `T&&` 容易让元素被意外移走。[[P2502R2]] 给出的例子是一个按值接收实参的谓词，`views::filter` 用解引用的结果调用它，元素就被移进了形参。本机 libc++ 没有 `<generator>`，但 `views::as_rvalue` 产生同样的 `std::string&&` 引用类型，可以重现这个效果：

```cpp title="footgun.cpp" run unspecified
#include <cstdio>
#include <ranges>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> v{"footgun"};
  // 解引用得到 std::string&&，和 generator<std::string> 一样
  auto r = v | std::views::as_rvalue
             | std::views::filter([](std::string s) {   // 按值接收
                 return !s.empty();
               });
  for (auto&& x : r)
    std::printf("[%s]\n", x.c_str());   // 本机输出 []
}
```

谓词的形参从 `std::string&&` 移动构造，原来的元素进入移出后的状态。标准库类型移出后处于有效但未指定的状态（[[lib.types.movedfrom#1]]），所以输出是未指定的；本机 libc++ 把它留成空串，于是打印出 `[]`。

[[P2529R0]] 的回应是，以右值引用为引用类型的范围本来就是合法的输入范围，`views::move` 这类适配器也会产生它们，通用代码迟早要正确处理；而最常见的用法是范围 `for`，循环里具名的 `x` 是左值，不会被隐式移动。委员会最终采纳了 `T&&`，并保留了"值类型与引用类型分开指定"的能力，结果就是当前草案里的三行（[[coro.generator.class]]）：

```cpp
using value     = conditional_t<is_void_v<Val>, remove_cvref_t<Ref>, Val>;
using reference = conditional_t<is_void_v<Val>, Ref&&, Ref>;
using yielded   = conditional_t<is_reference_v<reference>, reference, const reference&>;
```

只写一个实参时，引用类型是 `Ref&&`。`Ref` 本身是引用时按引用折叠，`generator<const T&>` 交出 `const T&`，`generator<T&>` 交出 `T&`。各种写法得到的类型表见 [[coro.generator]]。

提案还列出了几个被否决的默认：

| 候选 | 否决理由 |
|---|---|
| 不给默认，强制写 `generator<const int&>` | 明明有合理的默认，没必要为难用户 |
| `T&` | 允许修改协程帧里的对象，作为默认太危险；能 `co_yield` 的表达式也很受限 |
| 只能移动的类型取 `T&`，其余取 `const T&` | 给 `T` 加一个复制构造函数就会改变代码的含义 |
| `reference_wrapper<T>` 之类特殊处理 | 没有别的视图这样做，"像引用的类型"也没有清楚的定义 |

### `co_yield` 左值时复制

引用类型改成 `T&&` 之后，`yield_value(T&&)` 不接受左值，`co_yield local;` 就写不出来了。[[P2502R2]] 在 R1 加了第二个重载：`co_yield` 一个可复制的左值时，复制一份存进 `co_yield` 返回的可等待对象，消费者拿到的是指向这份副本的 xvalue（[[coro.generator.promise#7]]）。论文的说法是，这省得用户写 `co_yield auto(lvalue)`。

副本保证了消费者移走元素不会掏空协程里的变量，协程恢复后还能接着用它。[[coro.generator]] 有完整的例子。论文说这是为了更接近返回纯右值的函数：调用者拿到的总是一个属于自己的对象。

### 存地址而不是存值

promise 里怎样保存当前元素，论文也比较过。最早的修订总是存一份副本，每个元素多一次复制。最终的做法利用了一条语言规则：`co_yield` 的操作数如果是临时量，要到 `co_yield` 所在的完整表达式结束才销毁，而协程正是在这个表达式中间挂起的。所以 promise 只存一个指针（[[coro.generator.promise#4]]），`yield_value` 的形参总是引用类型 `yielded`，需要的转换都在协程内部完成。

代价是临时量活得比较久。论文举的例子是 `(co_yield x, co_yield y);`：如果 `x` 需要转换成一个临时量，它要等到 `y` 也交出之后才销毁。

### 第二个实参：单独指定值类型

`V` 留给少数需要代理引用的场合。论文的例子是用生成器写 `zip`，引用类型是由两个引用组成的 `tuple`，值类型是由两个值组成的 `tuple`。另一个例子说明值类型影响的是消费者存副本时的类型：

```cpp
std::generator<std::string_view, std::string> strings() {
  std::string s;
  for (auto sv : {"a", "b"}) {
    s = sv;
    s += '!';
    co_yield s;                      // 交出指向 s 的 string_view
  }
}
auto v = std::ranges::to<std::vector>(strings());   // vector<std::string>
```

元素以 `string_view` 交出，没有复制。但 `ranges::to` 按值类型建容器，得到的是 `vector<string>`。如果值类型也是 `string_view`，`v` 里存的就是指向协程变量 `s` 的视图，`s` 下一次赋值就让它们失效。

三个实参的顺序也改过两次。[[P2502R2]] R1 最后把 `Allocator` 放回末位，因为标准库里其他模板都是这样排的，例外的代价太大。

### 分配器从形参传入

协程帧由 promise 类型的 `operator new` 分配，编译器调用它时，会把协程的实参原样附在大小后面（[[dcl.fct.def.coroutine#9.1]]）。生成器的 promise 因此可以从实参里认出分配器。按照 [[P1681R0]] 第 2 节的模型，提案规定：协程的前两个形参是 `allocator_arg_t` 和分配器时，用这个分配器分配协程帧（[[coro.generator.promise#17]]）。

```cpp
template<class Alloc>
std::generator<int> ints(std::allocator_arg_t, const Alloc&, int n) {
  for (int i = 0; i < n; ++i) co_yield i;
}

std::pmr::monotonic_buffer_resource mr;
auto g = ints(std::allocator_arg,
              std::pmr::polymorphic_allocator<>(&mr), 10);
```

为什么必须放在最前面？协程的形参里可能有好几个分配器，有的是函数体里要用的。约定位置才能区分哪一个用来分配协程帧。论文承认这限制了形参顺序，但想不出必须占用第一个形参的场景。

`Allocator` 为 `void`（默认）时，分配器类型被擦除：`g` 的类型仍然是 `generator<int>`，分配器连同释放所需的信息一起存在协程帧里。只想用一种无状态分配器的代码可以写成 `generator<T, void, Alloc>`，这时不需要传实参，也不额外占空间。

用 `void` 表示"擦除任意分配器"曾受到批评。论文讨论过换成一个专用的标签类型，结论是单一用途的标签收益太低；`monostate` 已经有明确的用途，不宜再借用。`void` 不会被误认为分配器，也就保留了下来。

分配器支持为什么不等以后再加？因为分配器是模板实参，生成器发布以后再加模板实参会破坏 ABI。[[P2502R2]] 因此坚持一次到位。

### 单趟、只能移动的视图

协程帧是一份独占的资源，句柄可以复制，帧不能。所以生成器只能移动，它的迭代器也只能移动，范围只能是 `input_range`：遍历一遍，协程就运行到了底。[[coro.generator.members#8]] 规定 `begin()` 的前置条件是协程停在初始挂起点，所以第二次调用 `begin()` 是{{ub}}（注 4）。

它仍然是一个**视图**（[[g:range-view|view]]），可以直接接适配器。这一点在 [[P2168R3]] 时还有疑问：当时视图要求 O(1) 的析构，而一个按值接收 `vector` 的生成器，销毁协程帧时要销毁整个 `vector`。[[P2415R2]] 放宽了视图的语义要求，现在只要求 N 份副本加 M 个元素的析构是 O(N+M)（[[range.view#2.3]]），生成器也就没有疑问地满足了。

### 异常沿栈传播

子生成器里抛出的异常没有在子生成器内捕获时，不直接从最外层的 `++` 抛出，而是在父生成器的 `co_yield ranges::elements_of(...)` 处重新抛出。论文的理由是，`co_yield elements_of(g)` 应当和手写的 `for (auto&& x : g) co_yield x;` 语义相同，后者的异常就是从父协程的循环里冒出来的，父协程可以用 `try` 接住。上面的 `rec.cpp` 里，`catcher` 接住了 `thrower` 的异常，输出 `0 -1 1`。

标准的写法是 `unhandled_exception()` 分两种情况（[[coro.generator.promise#16]]）：栈里只有自己时等价于 `throw;`，否则把异常存进 promise，由父协程的 `await_resume` 重新抛出（[[coro.generator.promise#11]]）。

promise 还有一个被删除的 `await_transform()`，它让生成器协程里的 `co_await` 非良构。生成器是同步的：消费者的 `++` 返回时必须已经有下一个元素或者已经结束，协程不能停下来等别的事情。

## 措辞

!!! std
    Specializations of `generator` model `view` and `input_range`. ([[coro.generator.class#3]])

    `generator` 的每个特化都建模 `view` 和 `input_range`。

[[P2502R2]] 的措辞基于 N4910，全部是新增的库条文。按当前草案的位置整理如下，逐条的释义见 [[coro.generator]]：

| 条款 | 内容 |
|---|---|
| [[coroutine.generator.overview]] | 生成器呈现一个协程产出的元素组成的视图；`co_yield elements_of(r)` 依次产出 r 的元素 |
| [[generator.syn]] | 新头文件 `<generator>`；`pmr::generator` 别名（后来由 [[P2787R1]] 加入） |
| [[coro.generator.class]] | 三个模板实参推出 *value*、*reference*、`yielded`；*Mandates* 保证迭代器满足 `input_iterator` |
| [[coro.generator.members]] | 只能移动；移动后原来的迭代器仍有效；`begin()` 只能调用一次 |
| [[coro.generator.promise]] | 各个 `yield_value` 重载、活动栈、异常、`operator new` |
| [[coro.generator.iterator]] | `*` 读栈顶协程的值，`++` 恢复栈顶协程 |
| [[range.elementsof]] | 标签 `ranges::elements_of` |

特性测试宏 `__cpp_lib_generator` 当前值为 `202207L`（[[version.syn]]）。

## 后果

### 兼容性

纯库扩展，唯一相关的附录 C 条目是新头文件：项目里自己有一个名为 `generator` 的头文件，并用 `#include <generator>` 包含时，可能拿到标准库的版本（[[diff.cpp20.library#1]]）。

### 后续的库 issue

- [[LWG3894]]：接受任意范围的 `yield_value(elements_of<R, Alloc>)` 原先声明为 `noexcept`。它要调用 `ranges::begin`、分配一个新的协程帧、复制迭代器，这些都可能抛异常，于是去掉了 `noexcept`。
- [[LWG3899]]：`co_yield elements_of(g)` 对右值 `g` 走嵌套生成器的快速路径，对左值 `g` 却落到通用的范围重载，多创建一个协程帧，也没有对称转移。修正后增加了接受 `elements_of<generator&>` 的重载，就是当前草案里并列的两个声明。
- [[P2787R1]] 加入 `std::pmr::generator<R, V>`，即 `Allocator` 固定为 `polymorphic_allocator<>` 的别名，让"必须用 pmr 分配"写进类型。

### 实现状况

本机 Homebrew Clang 23 附带的 libc++ 还没有 `<generator>`，`#include <generator>` 报告文件不存在。所以本页凡是用到 `std::generator` 的例子都没有判定标记，只能借助上面手写的 `gen`、`rgen` 在本地验证机制。libstdc++（GCC 14 起）和 MSVC 的标准库已经提供了它，点 godbolt 按钮可以在 GCC 上运行。

生成器协程的引用形参、`string_view` 形参在协程恢复时可能已经悬垂，这类陷阱见 [[coro.generator]] 和 [[topics/coroutines]]。

## 思考题

!!! question "1"
    `std::generator<std::unique_ptr<int>>` 能不能用？如果默认的引用类型是 [[P2502R2]] 早期修订的 `const T&`，下面的循环能不能编译？

    ```cpp
    std::generator<std::unique_ptr<int>> make();
    std::vector<std::unique_ptr<int>> v;
    for (auto&& p : make()) v.push_back(std::move(p));
    ```

<details markdown="1">
<summary>答案</summary>

按当前规则能用：引用类型是 `unique_ptr<int>&&`，`std::move(p)` 得到右值，`push_back` 移动构造。协程体里 `co_yield std::make_unique<int>(1);` 交出纯右值，绑定到 `yielded` 即 `unique_ptr<int>&&`，不复制。

如果引用类型是 `const unique_ptr<int>&`，`std::move(p)` 得到 `const unique_ptr<int>&&`，只能匹配被删除的复制构造函数，编译失败。这正是 [[P2529R0]] 列出的理由之一。另一个变化是：在协程体里 `co_yield` 一个 `unique_ptr` 左值，现在非良构，因为复制的那个 `yield_value` 重载要求可以复制构造（[[coro.generator.promise]]），要写 `co_yield std::move(p);`。

</details>

!!! question "2"
    `rec.cpp` 里，`fast(n)` 恢复协程的次数是 3n+1。这些恢复各发生在哪里？换成 `std::generator` 和 `co_yield std::ranges::elements_of(fast(n - 1))`，量级会变吗？

<details markdown="1">
<summary>答案</summary>

每个非空的 `fast(k)` 贡献三次：父协程压栈时对称转移进来一次，消费者为它的 `co_yield k` 之后的 `++` 恢复一次，它结束时对称转移回父协程一次（最外层结束时转向 `noop_coroutine`，不计数）。最外层的进入就是 `begin()` 那一次，它的退出不计；`fast(0)` 也是一个协程，进出各一次。合计 3n − 1 + 2 = 3n+1。

换成 `std::generator` 量级不变。标准的 `elements_of` 重载把子生成器压进 *active_* 并恢复它（[[coro.generator.promise#11]]），`final_suspend` 弹栈后恢复新的栈顶（[[coro.generator.promise#3]]），迭代器的 `++` 只恢复栈顶（[[coro.generator.iterator#7]]）。标准没有规定一定用对称转移，但每取一个元素恢复的协程数与深度无关。

</details>

## 小结

| 设计问题 | 最终选择 | 被放弃的方案 |
|---|---|---|
| 默认的引用类型 | `generator<T>` 交出 `T&&` | 按值（每次解引用复制）、`const T&`、`T&`、强制写引用 |
| `co_yield` 左值 | 对 `T&&` 生成器复制一份 | 要求用户写 `co_yield auto(x)` |
| 保存当前元素 | 只存地址 | 总是存一份副本 |
| 递归 | 同一个类型，`elements_of` 标签，活动栈 | 单独的 `recursive_generator` |
| 嵌套的异常 | 在父协程的 `co_yield` 处重新抛出 | 直接从最外层的 `++` 抛出 |
| 分配器 | 开头的 `allocator_arg, alloc`；`Allocator = void` 时擦除 | 以后再加（会破坏 ABI）；用专用标签代替 `void` |
| 范围类别 | 只能移动的 `input_range` 视图 | 可复制、多趟 |
