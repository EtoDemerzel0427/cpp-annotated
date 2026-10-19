---
title: RAII 与作用域守卫
summary: 把资源的生存期绑在一个对象的生存期上：哪些语言规则保证析构函数一定运行，怎样写一个只能移动的资源句柄，unique_ptr 删除器和 scope guard 的用法与代价，标准库里的锁和线程，协程挂起时的生存期，以及 RAII 管不到的情形和常见陷阱。
status: draft
order: 10
since: c++98
papers: P0052R10, P1771R1, P2169R4, P2718R0
related: stmt.dcl, except.ctor, class.temporary, class.dtor, unique.ptr, thread.lock, uncaught.exceptions, dcl.fct.def.coroutine, topics/exception-safety, topics/ownership-and-smart-pointers, topics/special-members-and-elision, topics/dangling-references
tags: RAII, scope guard, 析构函数, 生存期, 惯用法
updated: 2026-10-19
---

!!! tldr
    - RAII 把释放资源的代码放进一个对象的析构函数。离开作用域的方式不论是正常执行、`return`、`break` 还是异常，自动对象都按构造的逆序析构，所以清理只写一次。
    - 一个资源句柄类通常只能移动：复制被删除，移动后源对象进入不拥有资源的空状态，析构函数必须能处理这个状态。接管原始句柄的构造函数要写成 `explicit`。
    - 大多数时候不必手写这个类：`unique_ptr` 加一个空类删除器就是零额外空间的句柄；一次性的清理用 scope guard，它在 `-O2` 下生成的代码与手写的 `try`/`catch` 一样。
    - 协程挂起不算离开作用域，局部对象一直活到协程帧被销毁。`exit`、`quick_exit`、`abort` 和未捕获的异常都可能根本不析构局部对象。
    - 最常见的错误是守卫没有名字（`std::lock_guard<std::mutex>{m};` 立即解锁），以及成员的声明顺序让线程在它所用的数据析构之后才 join。

## 四个出口，一份清理代码

一个函数打开文件、分配缓冲区、解析内容，途中有好几个出口：

<div class="compare" markdown="1">

```cpp
bool load(const char* path) {
  std::FILE* f = std::fopen(path, "rb");
  if (!f) return false;
  char* buf = new char[4096];
  if (std::fread(buf, 1, 4096, f) == 0) {
    delete[] buf;
    std::fclose(f);
    return false;
  }
  parse(buf);   // 抛出：两份资源都泄漏
  delete[] buf;
  std::fclose(f);
  return true;
}
```

```cpp
bool load(const char* path) {
  file_ptr f(std::fopen(path, "rb"));
  if (!f) return false;
  auto buf = std::make_unique<char[]>(4096);
  if (std::fread(buf.get(), 1, 4096,
                 f.get()) == 0)
    return false;
  parse(buf.get());  // 抛出：两份都释放
  return true;
}
```

</div>

左边每个出口都要把已经拿到的资源逐个释放，异常出口根本没有地方写释放代码。右边的 `file_ptr` 是 `std::unique_ptr<std::FILE, fclose_deleter>`（定义见后文），`buf` 是 `unique_ptr<char[]>`。它们的析构函数负责释放，任何出口都会调用到。

这种写法叫 **RAII**（resource acquisition is initialization）：获得资源的同时初始化一个对象，由这个对象拥有资源，对象析构时释放资源。名字强调的是获取，真正起作用的是另一半：析构函数在什么时候一定运行。

## 让它成立的规则

### 离开作用域就析构

控制从一点转移到另一点时，凡是在起点处已经生效、在终点处不再生效的块作用域自动变量，都按构造的逆序销毁（[[stmt.dcl#2]]）。这条规则不区分转移的方式：顺序执行到块末尾、`return`、`break`、`continue`、`goto` 都一样，[[stmt.jump.general#2]] 的注把它总结为不论以何种方式离开作用域。

`return` 的顺序也有规定：先用操作数初始化返回值，再销毁操作数里的临时对象，最后销毁局部变量（[[stmt.return#5]]）。所以析构函数运行时，返回值已经算好了，局部的 RAII 对象可以放心地守护计算返回值的那段代码。

异常走的是另一条路，结果相同。异常从 `throw` 传到 handler 的途中，自进入 `try` 块以来已经构造完成、还没销毁的自动对象，按构造完成的逆序销毁（[[except.ctor#2]]），这叫[[g:stack-unwinding|栈回溯]]。构造函数中途抛出时，已经构造好的成员和基类也会析构（[[except.ctor#3]]）。这两条的细节和例子见 [[topics/exception-safety]]。

### 逆序

局部变量按声明的逆序析构，类的成员也一样：析构函数体执行完之后，按成员构造完成的逆序调用成员的析构函数，然后是基类（[[class.dtor#13]]）。成员总是按声明顺序初始化，与初始化列表的书写顺序无关（[[class.base.init#15]]），所以析构顺序就是声明顺序的逆序。

逆序的道理是依赖关系：后构造的对象可能引用先构造的对象，先构造的对象不会引用后构造的。逆序析构保证每个对象析构时，它依赖的对象都还活着。这条保证只在声明顺序与依赖顺序一致时成立，后文的陷阱一节有一个反例。

### 临时对象

临时对象在包含它的完整表达式（[[g:full-expression]]）求值的最后一步销毁，即使求值以异常结束也一样（[[class.temporary#4]]）。临时对象直接绑定到引用时，生存期延长到引用的生存期（[[class.temporary#6]]）。

```cpp run title="order.cpp" ok
#include <cstdio>

struct Trace {
  const char* name;
  explicit Trace(const char* n) : name(n) { std::printf("+%s ", name); }
  ~Trace() { std::printf("-%s ", name); }
};

Trace make(const char* n) { return Trace(n); }

struct Pair {
  Trace first{"m1"};
  Trace second{"m2"};
};

int main() {
  {
    Trace a("a");
    Pair p;
    make("tmp"), std::printf("[expr] ");   // 临时对象活到完整表达式结束
    const Trace& r = make("ext");          // 绑定到引用：延长到 r 的作用域结束
    Trace b("b");
    std::printf("[end] ");
  }
  std::printf("\n");
  try {
    Trace c("c");
    throw 0;
  } catch (int) { std::printf("[handler]\n"); }
}
```

本机输出：

```text
+a +m1 +m2 +tmp [expr] -tmp +ext +b [end] -b -ext -m2 -m1 -a
+c -c [handler]
```

`tmp` 在逗号表达式求值完之后立即销毁；`ext` 被延长，和局部变量一起按逆序销毁；`p` 的两个成员按声明的逆序销毁；`c` 在进入 handler 之前销毁。

## 写一个 RAII 类

POSIX 文件描述符是一个 `int`，没有现成的标准库类型管理它。一个合格的句柄类大致如下：

```cpp run title="unique-fd.cpp" ok
#include <cstdio>
#include <fcntl.h>
#include <unistd.h>
#include <utility>

class UniqueFd {
  int fd_ = -1;                              // -1：不拥有任何描述符
public:
  UniqueFd() = default;
  explicit UniqueFd(int fd) noexcept : fd_(fd) {}
  UniqueFd(const UniqueFd&) = delete;
  UniqueFd& operator=(const UniqueFd&) = delete;
  UniqueFd(UniqueFd&& o) noexcept : fd_(std::exchange(o.fd_, -1)) {}
  UniqueFd& operator=(UniqueFd&& o) noexcept {
    reset(std::exchange(o.fd_, -1));         // 自移动赋值时 o.fd_ 先变成 -1
    return *this;
  }
  ~UniqueFd() { reset(); }

  int get() const noexcept { return fd_; }
  explicit operator bool() const noexcept { return fd_ >= 0; }
  [[nodiscard]] int release() noexcept { return std::exchange(fd_, -1); }
  void reset(int fd = -1) noexcept {
    if (int old = std::exchange(fd_, fd); old >= 0) ::close(old);
  }
};

UniqueFd open_read(const char* path) {
  return UniqueFd(::open(path, O_RDONLY));   // 失败时 open 返回 -1，即空句柄
}

int main() {
  UniqueFd a = open_read("/etc/hosts");
  UniqueFd b = std::move(a);                 // a 变为空，b 拥有描述符
  std::printf("a=%d b=%s\n", a.get(), b ? "open" : "empty");
  int raw = b.release();                     // 交出所有权，b 不再关闭它
  std::printf("b=%d close(raw)=%d\n", b.get(), ::close(raw));
  UniqueFd c = open_read("/no/such/file");
  std::printf("c=%s\n", c ? "open" : "empty");
}
```

本机输出 `a=-1 b=open`、`b=-1 close(raw)=0`、`c=empty`，ASan 和 UBSan 没有报告。下面逐条说明这些成员为什么这样写。

### 空状态与移动

句柄类首先要有一个不拥有资源的状态，这里是 `-1`。移动构造把资源转给新对象，源对象进入空状态；析构函数和 `reset` 在空状态下什么也不做。被移动后的对象仍然会析构，所以空状态不是可有可无的，它是移动语义能成立的前提。

标准库对自己的类型一般只承诺移动后处于有效但未指定的状态（[[lib.types.movedfrom#1]]）。句柄类可以承诺得更多，`unique_ptr` 就保证移动后 `get() == nullptr`（[[unique.ptr.single.ctor#18]]）。自己写的句柄类也应当把移动后的状态写成明确的保证，调用方就可以在移动之后继续给它赋值、检查它或者让它析构。

移动赋值写成 `reset(std::exchange(o.fd_, -1))`，先把源对象清空，再关闭自己的旧描述符、换成新的。自移动赋值时，`exchange` 已经把 `fd_` 变成 `-1`，`reset` 再把原来的值写回，对象仍然拥有描述符，本机验证了这一点（Clang 对显式的 `b = std::move(b)` 给出 `-Wself-move` 警告）。

### 复制、`noexcept` 与 `explicit`

两个对象拥有同一个描述符会导致关闭两次，所以复制必须禁止。其实只要声明了移动构造函数，隐式的复制构造函数就定义为删除的（[[class.copy.ctor#6]]），显式写出 `= delete` 是为了让读者一眼看出意图。

移动操作和析构函数都标 `noexcept`。移动只是交换整数，不会失败；`std::vector` 扩容时据此决定移动还是复制，原因见 [[topics/exception-safety]]。析构函数默认就是 `noexcept` 的，`close` 的错误也不该从析构函数里抛出，见后文。

接管原始句柄的构造函数必须是 `explicit`，否则一个 `int` 会悄悄变成一个拥有它的对象：

<div class="compare" markdown="1">

```cpp
// UniqueFd(int) 没有 explicit
void send_all(UniqueFd sock);

void f(int fd) {
  send_all(fd);   // 编译通过：形参析构时
}                 // 关闭了调用方的 fd
```

```cpp
// explicit UniqueFd(int)
void send_all(UniqueFd sock);

void f(int fd) {
  send_all(fd);   // error: 不能隐式转换
  send_all(UniqueFd(fd));  // 所有权转移写在明处
}
```

</div>

`release()` 是反方向的出口：交出原始句柄，自己变空，调用方从此负责释放。它的返回值一旦丢弃就是泄漏，所以标了 `[[nodiscard]]`。这与 `unique_ptr::release` 的语义相同（[[unique.ptr.single.modifiers#1]]）。

### 获取失败怎么办

构造函数没有返回值。获取失败时有两种做法：抛出异常，让对象根本不存在；或者像 `UniqueFd` 这样进入空状态，由调用方检查。后一种做法的对象总是需要空状态，反正移动也需要它，所以句柄类通常两者兼容。需要错误信息时，可以把获取写成一个返回 `std::expected<UniqueFd, std::error_code>` 的工厂函数。

### Rule of zero

句柄类写好之后，使用它的类就不必再写任何特殊成员函数：

```cpp
struct Connection {
  UniqueFd sock;
  std::string peer;
};
static_assert(!std::is_copy_constructible_v<Connection>);
static_assert(std::is_nothrow_move_constructible_v<Connection>);
```

两条断言在本机都成立。编译器生成的移动构造逐成员移动，`noexcept` 也由成员推导出来；复制因为 `UniqueFd` 不可复制而被删除。这就是 Rule of zero：管理资源的代码集中在一个只做这件事的类里，其他类只组合它。Rule of 3/5/0 的完整规则见 [[topics/special-members-and-elision]]。

## `unique_ptr` 加删除器

资源本身是指针时，比如 `FILE*`、C 库返回的结构体指针、`malloc` 的结果，不必手写句柄类，`unique_ptr` 的第二个模板参数就是释放函数：

```cpp run title="deleters.cpp" ok
#include <cstdio>
#include <memory>

struct fclose_deleter {
  void operator()(std::FILE* f) const noexcept { std::fclose(f); }
};
using file_ptr = std::unique_ptr<std::FILE, fclose_deleter>;

using file_lambda = std::unique_ptr<std::FILE,
    decltype([](std::FILE* f) noexcept { std::fclose(f); })>;   // C++20

void close_file(std::FILE* f) noexcept { std::fclose(f); }      // 自己的函数
using file_fnptr = std::unique_ptr<std::FILE, void (*)(std::FILE*) noexcept>;

int main() {
  file_ptr a(std::fopen("/etc/hosts", "r"));
  file_lambda b(std::fopen("/etc/hosts", "r"));
  file_fnptr c(std::fopen("/etc/hosts", "r"), &close_file);   // 每个对象都带着指针
  std::printf("%zu %zu %zu\n", sizeof a, sizeof b, sizeof c);
}
```

本机输出 `8 8 16`。空类删除器不占空间，`unique_ptr` 和一个裸指针一样大；函数指针删除器要存在每个对象里，大小翻倍，调用也要经过一次间接跳转，除非优化器能证明指针的值。所以推荐写一个空的函数对象类，或者 C++20 起直接用无捕获 lambda 的类型。

不要写 `decltype(&std::fclose)` 或 `&std::fclose`。除了标准明确标为可取地址的少数函数，取标准库函数的地址，行为未指定，甚至可能非良构（[[namespace.std#6]]），C 库函数也在此列。在删除器的函数体里调用它就没有这个问题。

删除器类型如果定义了嵌套类型 `pointer`，`unique_ptr` 就存储这个类型而不是 `T*`（[[unique.ptr.single.general#4]]），理论上可以用它管理 `int` 描述符这类非指针句柄。但这个 `pointer` 类型要满足 *Cpp17NullablePointer*，必须能和 `nullptr` 比较、能从 `nullptr` 构造，包装起来并不比上一节的 `UniqueFd` 简单。`unique_ptr` 的其余细节，包括交给 C 接口的 `out_ptr`，见 [[topics/ownership-and-smart-pointers]]。

## scope guard

有些清理只在一个函数里出现一次，比如恢复一个全局设置、撤销一步已经完成的操作。为它专门写一个类不值得，这时用 **scope guard**：构造时保存一个函数对象，析构时调用它。

```cpp run title="scope-exit.cpp" ok
#include <cstdio>
#include <utility>

template<class F>
class [[nodiscard]] scope_exit {
  F f_;
  bool active_ = true;
public:
  explicit scope_exit(F f) noexcept(noexcept(F(std::move(f))))
      : f_(std::move(f)) {}
  scope_exit(const scope_exit&) = delete;
  scope_exit& operator=(const scope_exit&) = delete;
  ~scope_exit() { if (active_) f_(); }
  void release() noexcept { active_ = false; }   // 取消清理
};

int depth = 0;

void visit(int n) {
  ++depth;
  auto _ = scope_exit([] { --depth; });         // C++26：_ 不需要起名字
  if (n == 0) return;
  visit(n - 1);
}

int main() {
  visit(3);
  std::printf("depth=%d\n", depth);             // 0
}
```

几处细节。类模板实参推导让 `scope_exit(lambda)` 不必写出 lambda 的类型。复制和移动都被删除，但 C++17 起 prvalue 直接初始化变量，不经过移动，所以 `auto _ = scope_exit(...)` 可以编译（[[dcl.init.general#15.6.1]]），按值返回一个 `scope_exit` 的工厂函数也可以；反过来 `scope_exit g(...); return g;` 需要移动构造函数，是非良构的。C++26 允许同一作用域里有多个名为 `_` 的变量（[[P2169R4]]），一串守卫都可以叫 `_`。

只在失败时运行的 `scope_fail`、只在成功时运行的 `scope_success`，与上面只差析构函数里的条件：构造时记下 `std::uncaught_exceptions()`，析构时如果计数变大，说明正处于栈回溯中（[[uncaught.exceptions#1]]）。为什么要比较计数而不是检查它是否大于 0，以及一个用 `scope_fail` 实现强保证的完整例子，见 [[topics/exception-safety]]。

| 守卫 | 析构时运行函数的条件 |
|---|---|
| `scope_exit` | 总是（除非调用过 `release()`） |
| `scope_fail` | `uncaught_exceptions()` 大于构造时的值 |
| `scope_success` | `uncaught_exceptions()` 不大于构造时的值 |

这三个名字来自 Library Fundamentals TS 第 3 版的 `std::experimental::scope_exit` 等（[[P0052R10]]），同一提案还有一个通用的资源句柄 `unique_resource`。它们没有进入标准，本机 libc++ 也没有实现 TS 中的这一部分，实际项目里要自己写或者用第三方库。

### 代价

把一个可能抛出的函数夹在获取和释放之间，分别用 `try`/`catch` 和 `scope_exit` 写：

<div class="compare" markdown="1">

```cpp
void by_hand() {
  void* r = acquire();
  try { use(r); }
  catch (...) { release_res(r); throw; }
  release_res(r);
}
```

```cpp
void by_guard() {
  void* r = acquire();
  scope_exit g([r] { release_res(r); });
  use(r);
}
```

</div>

本机 Clang 23 `-O2`（arm64）下，两者正常路径的指令完全相同：调用 `acquire`、调用 `use`，然后尾调用 `release_res`，`active_` 标志被优化掉了。异常路径上，守卫版本更短：着陆点只调用 `release_res` 再 `_Unwind_Resume`，手写版本要经过 `__cxa_begin_catch`、`__cxa_rethrow`、`__cxa_end_catch`。

`scope_fail` 不是免费的。`uncaught_exceptions()` 是运行时库里的一个函数，编译器不知道它的结果，于是正常路径上也有两次调用（构造时一次，析构时一次）和一次比较。对象大小方面，捕获一个指针的 lambda 加上一个 `bool` 或 `int`，本机 `sizeof` 是 16。

## 标准库里的 RAII

标准库的很多类型本身就是 RAII 类，析构函数的效果都写在规范里：

| 类型 | 析构时 | 能否移动 | 出处 |
|---|---|---|---|
| `unique_ptr<T, D>` | 非空时调用删除器 | 能，源变空 | [[unique.ptr.single.dtor]] |
| `lock_guard<M>` | `unlock()` | 不能 | [[thread.lock.guard#6]] |
| `scoped_lock<Ms...>` | 逐个 `unlock()` | 不能 | [[thread.lock.scoped#6]] |
| `unique_lock<M>` | 持有锁时 `unlock()` | 能，源不再关联互斥量 | [[thread.lock.unique.cons#20]] |
| `jthread` | 可 join 时 `request_stop()` 再 `join()` | 能 | [[thread.jthread.cons#12]] |
| `thread` | 可 join 时调用 `std::terminate` | 能 | [[thread.thread.destr#1]] |
| `fstream` 等文件流 | 关闭文件，吞掉其中的异常 | 能 | [[filebuf.cons#5]] |

`lock_guard` 最简单，构造时加锁、析构时解锁，不能移动也不能提前解锁。`scoped_lock` 可以同时锁多个互斥量，内部用 `std::lock` 的避免死锁算法（[[thread.lock.scoped#2]]）。`unique_lock` 多了状态：可以延迟加锁、提前解锁、移交给别人，`condition_variable::wait` 需要的就是它。

```cpp run title="locks.cpp" ok
#include <condition_variable>
#include <cstdio>
#include <mutex>
#include <queue>
#include <thread>

struct Account { std::mutex m; long balance = 100; };

void transfer(Account& from, Account& to, long n) {
  std::scoped_lock lk(from.m, to.m);       // 同时锁两个，不会因加锁顺序死锁
  from.balance -= n;
  to.balance += n;
}

std::mutex qm;
std::condition_variable cv;
std::queue<int> q;

int pop() {
  std::unique_lock lk(qm);                 // wait 需要能解锁再加锁的 unique_lock
  cv.wait(lk, [] { return !q.empty(); });
  int v = q.front();
  q.pop();
  lk.unlock();                             // 提前释放；析构时不再持有，什么也不做
  return v * 2;                            // 不需要锁的工作
}

int main() {
  Account a, b;
  {
    std::jthread t1([&] { for (int i = 0; i < 1000; ++i) transfer(a, b, 1); });
    std::jthread t2([&] { for (int i = 0; i < 1000; ++i) transfer(b, a, 1); });
  }                                        // jthread 析构时 join
  std::printf("%ld %ld\n", a.balance, b.balance);

  std::jthread consumer([] { std::printf("%d\n", pop()); });
  { std::lock_guard lk(qm); q.push(21); }
  cv.notify_one();
}
```

本机输出 `100 100` 和 `42`，TSan 没有报告。`t1` 和 `t2` 以相反的顺序请求两把锁，如果分别用两个 `lock_guard` 依次加锁，就可能死锁。

`std::thread` 不是完整的 RAII 类：它的析构函数在线程仍可 join 时直接终止程序（[[thread.thread.destr#1]]）。标准的注里给出的理由是，析构时自动 join 或 detach 都会在异常路径上引入难以调试的问题。C++20 的 `jthread` 选择了 join，并在 join 之前通过 `stop_token` 请求线程停止，这样析构函数既不会终止程序，也不会在线程不肯结束时永远等下去，前提是线程函数检查了停止请求。

## 协程：挂起不算离开作用域

协程在 `co_await` 处挂起时，控制回到调用方，但协程里的局部变量并没有离开作用域，[[stmt.jump.general#2]] 的第二个注明确说挂起不是离开作用域。局部变量存放在[[g:coroutine-state|协程状态]]（通常在堆上）里，一直活到协程运行结束，或者协程句柄的 `destroy()` 被调用（[[dcl.fct.def.coroutine#11]]）。

```cpp run title="coro.cpp" ok
#include <coroutine>
#include <cstdio>
#include <utility>

struct Trace {
  const char* name;
  explicit Trace(const char* n) : name(n) { std::printf("+%s\n", name); }
  ~Trace() { std::printf("-%s\n", name); }
};

struct Task {                              // 最小的协程类型：拥有协程帧
  struct promise_type {
    Task get_return_object() {
      return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
    }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_void() {}
    void unhandled_exception() { throw; }
  };
  std::coroutine_handle<promise_type> h;
  explicit Task(std::coroutine_handle<promise_type> h) : h(h) {}
  Task(Task&& o) noexcept : h(std::exchange(o.h, {})) {}
  ~Task() { if (h) h.destroy(); }          // Task 自己也是 RAII 类
  void resume() { h.resume(); }
};

Task job() {
  Trace t("local");
  std::puts("before suspend");
  co_await std::suspend_always{};          // 挂起：t 还活着
  std::puts("after resume");               // 本例不会执行到这里
}

int main() {
  Task task = job();
  task.resume();                           // 运行到 co_await 处挂起
  std::puts("main: dropping task");
}                                          // ~Task 调用 destroy()，t 在此析构
```

本机输出 `+local`、`before suspend`、`main: dropping task`、`-local`。协程从未恢复，但 `destroy()` 被视为控制转移出函数（[[dcl.fct.def.coroutine#11]]），挂起点上活着的局部变量照常按逆序析构。所以协程里的 RAII 依然成立，前提是协程帧本身有一个 RAII 的拥有者，这里是 `Task`。忘记 `destroy()` 的协程帧会连同里面的所有局部对象一起泄漏。

生存期跨越挂起点也带来两个问题。

第一，锁跨越 `co_await`。持有 `std::lock_guard` 时挂起，锁在整个挂起期间都不释放；如果协程在另一个线程上恢复，析构时由另一个线程调用 `unlock()`，违反了调用线程必须持有互斥量的前提（[[thread.mutex.requirements.mutex.general#21]]），而违反前提条件是 UB（[[structure.specifications#3.4]]）。需要在异步代码里互斥时，应当用调度器提供的异步互斥量，或者在 `co_await` 之前结束锁的作用域。

第二，协程的引用形参只复制引用本身（[[dcl.fct.def.coroutine#13]]）。调用方的实参如果是临时对象，第一次挂起之后它就已经析构了，恢复后使用就是悬垂引用。更多例子见 [[topics/dangling-references]]。

## RAII 管不到的地方

### 析构函数无法报告错误

`close`、`fclose` 可能失败，比如刷新缓冲区时磁盘已满。析构函数不能把这个错误传给调用方：它默认是 `noexcept` 的，即使改成可以抛出，在栈回溯中抛出也会终止程序。常见的做法是另外提供一个显式的 `close()`，让关心错误的调用方先调用它并检查结果，析构函数只做不会失败的兜底。理由和实测见 [[topics/exception-safety]]。

### 程序没有正常结束

析构函数只在控制按语言规则离开作用域时运行。有几种结束程序的方式根本不离开作用域：

```cpp run title="exits.cpp" impl
#include <cstdio>
#include <cstdlib>
#include <stdexcept>

struct Flush {
  const char* name;
  ~Flush() { std::printf("~%s ", name); std::fflush(stdout); }
};

Flush global{"static"};

int main(int argc, char**) {
  Flush local{"local"};
  switch (argc) {
    case 1: return 0;                               // 正常返回
    case 2: std::exit(0);                           // 不析构自动对象
    case 3: std::quick_exit(0);                     // 什么对象都不析构
    case 4: throw std::runtime_error("unhandled");  // 没有 handler：是否回溯由实现定义
  }
}
```

| 结束方式 | 本机析构了 | 规则 |
|---|---|---|
| 从 `main` 返回 | `local`、`static` | 先销毁 `main` 的局部变量，再按 `exit` 处理静态对象 |
| `std::exit` | 只有 `static` | 不销毁自动对象（[[support.start.term#9]]） |
| `std::quick_exit` | 都没有 | 只调用 `at_quick_exit` 注册的函数（[[support.start.term#13]]） |
| 未捕获的异常 | 都没有，退出码 134 | 栈是否回溯由实现定义（[[except.terminate#2]]） |

`std::abort` 和 `std::_Exit` 同样不运行任何析构函数（[[support.start.term#5]]）。由此可知，进程崩溃或被信号杀死时，RAII 不能保证外部状态一致：锁文件、临时文件、共享内存这类在进程之外仍然存在的资源，需要另外的恢复机制，比如启动时检查并清理。

### 脱离作用域的工作

RAII 依赖的是作用域，一个任务一旦脱离了创建它的作用域，就没有对象替它收尾。`std::thread::detach()` 之后，`thread` 对象不再代表那个线程（[[thread.thread.member#8]]），线程里按引用捕获的局部变量可能早已析构；回调注册到全局的事件循环里，注册它的对象析构后回调仍可能被调用。这类问题需要让任务自己拥有它用到的数据（按值捕获、`shared_ptr`），或者用一个能等待所有任务结束的作用域对象。回调与生存期的问题见 [[patterns/observer|观察者与回调的生命周期]]。

## 陷阱

### 没有名字的守卫

守卫对象只有活到作用域结束才有意义，忘了给它起名字，它就成了临时对象，或者成了别的东西：

```cpp
std::mutex m;
int counter;

void f1() {
  std::lock_guard<std::mutex>{m};     // 临时对象：加锁后立即解锁
  ++counter;                          // 没有加锁
}
void f2() {
  std::unique_lock<std::mutex>(m);    // 声明了一个名为 m 的 unique_lock
  ++counter;                          // 没有加锁
}
void f3() {
  std::lock_guard<std::mutex>(m);     // error: 同样是声明，lock_guard 不能默认构造
}
```

`f1` 是一条表达式语句，临时对象在分号处析构（[[class.temporary#4]]）。`f2` 和 `f3` 的圆括号版本更隐蔽：一条语句既能解释为表达式又能解释为声明时，按声明处理（[[stmt.ambig#1]]），于是 `(m)` 成了被括起来的变量名，声明了一个遮住外层互斥量的新变量 `m`。`unique_lock` 有默认构造函数，`f2` 能编译，得到一个不关联任何互斥量的锁；`lock_guard` 没有，`f3` 碰巧编译失败。详细的消歧规则见 [[dcl.ambig.res]]。

本机 Clang 23 加 libc++ 对 `f1` 给出 `-Wunused-value` 警告（ignoring temporary created by a constructor declared with 'nodiscard' attribute），对 `f2`、`f3` 给出 `-Wvexing-parse` 警告。`f1` 的警告来自 libc++ 给这些构造函数加的 `[[nodiscard]]`：C++20 起，以显式类型转换的形式调用 nodiscard 构造函数或构造 nodiscard 类型的对象，也算 nodiscard 调用，丢弃它时建议警告（[[dcl.attr.nodiscard#3]]、[[P1771R1]]）。这是实现的选择，标准没有要求 `lock_guard` 这样标注。一个没有 `[[nodiscard]]` 的普通类，`G{1};` 在本机不产生任何警告。所以自己写的守卫类应当像上文的 `scope_exit` 那样标上 `[[nodiscard]]`。

### 代理对象的临时生存期

一种常见的设计把数据和保护它的锁放在一起，只能通过一个持有锁的代理对象访问数据。代理是临时对象时，锁的范围就是完整表达式的范围：

```cpp run title="synchronized.cpp" ok
#include <cstdio>
#include <mutex>
#include <vector>

template<class T>
class Synchronized {                       // 数据和保护它的锁放在一起
  T data_;
  std::mutex mu_;
public:
  class Locked {                           // 持有锁的代理对象
    std::unique_lock<std::mutex> lk_;
    T* p_;
  public:
    Locked(std::mutex& m, T* p) : lk_(m), p_(p) { std::puts("  lock"); }
    ~Locked() { std::puts("  unlock"); }
    T* operator->() const { return p_; }
    T& operator*() const { return *p_; }
  };
  Locked lock() { return {mu_, &data_}; }
};

int main() {
  Synchronized<std::vector<int>> s;
  std::puts("A");
  s.lock()->push_back(1);                  // 锁覆盖整个完整表达式
  std::puts("B");
  auto& v = *s.lock();                     // 这条声明结束时代理对象析构
  v.push_back(2);                          // 没有加锁
  std::puts("C");
  for (int x : *s.lock())                  // C++23 起临时对象活到循环结束
    std::printf("  %d\n", x);
  std::puts("D");
}
```

本机 `-std=c++2c` 下，`A` 和 `B` 之后都是 `lock`、`unlock` 紧挨着，`C` 之后是 `lock`、`1`、`2`、`unlock`。`v` 绑定到的是 `operator*` 返回的引用，不是临时对象本身，所以不延长代理的生存期，`v.push_back(2)` 在锁外执行。

范围 `for` 的情况取决于语言版本。C++23 起，范围 `for` 初始化器里的临时对象活到循环结束（[[class.temporary#7]]、[[P2718R0]]）；本机用 `-std=c++20` 编译同一个程序，`C` 之后先 `lock`、`unlock`，再打印 `1`、`2`，整个循环都在锁外。升级语言版本也可能让原本在循环前释放的锁一直持有到循环结束，[[diff.cpp20]] 里有一个因此死锁的例子。

### 成员的析构顺序

成员按声明的逆序析构。一个类拥有一个线程，线程又使用这个类的其他成员时，线程必须最后声明：

```cpp run title="member-order.cpp" ub
#include <chrono>
#include <cstdio>
#include <mutex>
#include <thread>
#include <vector>

class Sampler {
  std::jthread worker_;                    // 先声明，所以最后析构
  std::mutex mu_;
  std::vector<int> samples_;
public:
  Sampler()
      : worker_([this](std::stop_token st) {
          while (!st.stop_requested()) {
            std::lock_guard lk(mu_);
            samples_.push_back(42);
          }
        }) {}
  // ~Sampler 依次析构 samples_、mu_，最后才是 worker_：
  // 在它请求停止并 join 之前，线程还在使用已经析构的成员
};

int main() {
  {
    Sampler s;
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  std::puts("done");
}
```

`~Sampler` 的函数体是空的，之后先析构 `samples_`，再析构 `mu_`，最后 `worker_` 的析构函数才请求停止并 join（[[class.dtor#13]]）。在这段时间里，线程还在对已经析构的互斥量加锁、往已经析构的 vector 里写。本机不加 sanitizer 运行 5 次，有 1 次以 `mutex lock failed: Invalid argument` 终止；TSan 报告 vector 内部的 data race。把 `worker_` 移到最后声明之后，TSan 不再报告。

`jthread` 的析构函数会自动 join，看起来已经是 RAII 了，但它只能保证线程在 `worker_` 自己析构时结束，不能替类决定其他成员的析构时机。一般规则是：成员 A 在生存期内要用到成员 B，A 就声明在 B 之后。

## 什么时候用

| 情形 | 建议 |
|---|---|
| 资源是指针，有专门的释放函数 | `unique_ptr` 加空类删除器 |
| 资源是整数句柄或其他非指针值，到处都要用 | 写一个只能移动的句柄类，其余类 Rule of zero |
| 一个函数里一次性的清理或撤销 | scope guard |
| 只在失败时撤销 | `scope_fail` 式的守卫，或者重排步骤使撤销不必要 |
| 互斥 | `lock_guard`；多把锁用 `scoped_lock`；要配合条件变量或提前解锁用 `unique_lock` |
| 线程 | `jthread`，并在线程函数里检查 `stop_token` |
| 释放操作可能失败且调用方需要知道 | 提供显式的 `close()`，析构函数只兜底 |
| 资源在进程外，崩溃后仍然存在 | RAII 之外还需要恢复机制 |
| 释放需要异步等待 | 析构函数不能 `co_await`，要用异步作用域或显式的关闭协程 |

## 思考题

!!! question "1"
    `UniqueFd::reset` 先把新值写进 `fd_`，再关闭旧值。`unique_ptr::reset` 的规范也要求这个顺序。如果反过来，先关闭旧值再赋值，会有什么问题？

<details markdown="1">
<summary>答案</summary>

释放操作可能间接地再次访问这个句柄对象。`unique_ptr` 的情况最典型：删除器删除的对象可能正好拥有这个 `unique_ptr`，比如链表节点里指向下一个节点的指针，删除器运行时 `*this` 本身可能被销毁。[[unique.ptr.single.modifiers#3]] 的注说明了这一点：先赋值再调用删除器，删除器运行时 `*this` 已经处于一致的状态，之后也不再访问 `*this`。反过来的顺序，删除器运行期间别人会看到一个指向已释放资源的对象，删除器返回后还要写一个可能已经不存在的对象。
</details>

!!! question "2"
    下面两个函数哪个能编译？能编译的那个，守卫在什么时候运行？

    ```cpp
    auto make_guard() { return scope_exit([] { std::puts("cleanup"); }); }
    auto bad() { scope_exit g([] {}); return g; }
    ```

<details markdown="1">
<summary>答案</summary>

`make_guard` 能编译，`bad` 不能。`make_guard` 的返回语句的操作数是 prvalue，C++17 起它直接初始化调用方的结果对象，不需要复制或移动构造函数（[[dcl.init.general#15.6.1]]）。调用方写 `auto _ = make_guard();` 时，守卫在调用方的作用域结束时运行，本机输出先是调用方的工作，然后是 `cleanup`。`bad` 返回一个具名局部变量，返回语句用它复制初始化结果对象（[[stmt.return#2]]）。`g` 可以隐式移动，所以这里是一个 xvalue（[[expr.prim.id.unqual#12]]），需要移动构造函数，而它被删除了。编译器可以省略这次构造（NRVO，[[class.copy.elision#1]]），但省略不是强制的，被选中的构造函数仍然必须可用。本机 Clang 报告调用了被删除的构造函数。
</details>

!!! question "3"
    `member-order.cpp` 的 `Sampler` 除了析构顺序，在构造时还有一个问题。是什么？

<details markdown="1">
<summary>答案</summary>

成员按声明顺序初始化（[[class.base.init#15.3]]）。`worker_` 最先声明，所以它的构造函数最先运行，线程启动时 `mu_` 和 `samples_` 还没有构造，线程立即对它们加锁和写入就是在使用生存期尚未开始的对象。把 `worker_` 移到最后声明，同时修正了构造和析构两个问题：线程在它用到的成员全部构造之后才启动，在它们析构之前就已经 join。
</details>
