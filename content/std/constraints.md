---
title: 对程序的约束
summary: 用标准库的程序要守的规矩：实参必须有效，右值引用实参被当作唯一引用；跨线程访问库对象不能有数据竞争；替换函数、处理函数和用作模板实参的类型必须满足库的要求；概念被满足但没有被建模时程序 IFNDR。
status: done
covers: constraints.overview, alt.headers, derived.classes, replacement.functions, handler.functions, res.on.functions, res.on.arguments, res.on.objects, res.on.requirements
related: namespace.constraints, reserved.names, conforming, utility.requirements, dcl.fct.def.replace, lib.types.movedfrom, res.on.data.races, temp.constr.decl, new.delete
tags: 库, UB, IFNDR, 替换函数, 数据竞争, 移动语义
updated: 2026-10-19
---

!!! tldr
    - 传给库函数的实参必须有效。传入悬垂指针、越界迭代器之类的值是未定义行为，哪怕函数说明里没写前置条件。
    - 用 `std::move(x)` 把对象传给库函数，等于允许库假定没有别的引用指向它，所以 `v.push_back(std::move(v[0]))` 不受保证，`v.push_back(v[0])` 受保证。
    - 多个线程同时调用一个库对象的 `const` 成员是安全的；一边修改一边读取是数据竞争。对象的构造必须先于一切访问，一切访问必须先于析构，`std::mutex` 也不例外。
    - 用户提供给库的东西（替换的 `operator new`、`terminate_handler`、放进容器的类型、比较器）不满足库的要求就是未定义行为；用不完整类型实例化 `std::map` 这类没有明确允许的模板也是。
    - 概念只检查语法。类型满足了概念却不符合它的语义要求时，程序非良构、不要求诊断。

这一节列出程序在使用标准库时必须遵守的约束。库的实现以这些约束为前提，编译器通常检查不了，所以违反的后果几乎都是**未定义行为**（UB，标准对程序的行为不作任何要求）或 **IFNDR**（ill-formed, no diagnostic required：程序非良构，但编译器不必报告，见 [[intro.compliance]]）。

其中命名空间的使用（[[namespace.constraints]]）和保留名字（[[reserved.names]]）内容较多，各自单独成页。

## 传给库函数的实参 [res.on.arguments]

### 无效的值一律是 UB（¶1.1、¶1.2）

```cpp ub
#include <cstring>
int main() {
  const char* p = nullptr;
  return std::strlen(p);   // UB：空指针不是有效的字符串
}
```

¶1 下面三条适用于标准库中所有函数的所有实参，除非某个函数另有说明。

¶1.1 实参的值无效时行为未定义。无效的值包括函数定义域以外的值，以及对预期用途无效的指针。这是一条兜底规则：即使某个函数的说明里没有列出前置条件（*Preconditions*），给它传悬垂指针、越界迭代器或空的 `const char*` 也都是 UB。

¶1.2 实参被描述为数组时，传入的指针必须真的指向足够大的数组，函数按数组访问时做的地址计算和对象访问都必须有效。

### 右值引用实参被当作唯一引用（¶1.3）

<div class="compare" markdown="1">

```cpp run ok
#include <string>
#include <vector>
int main() {
  std::vector<std::string> v{"a", "b"};
  v.push_back(v[0]);
  // 库必须处理实参就是
  // 自己元素的情形
}
```

```cpp run
#include <string>
#include <vector>
int main() {
  std::vector<std::string> v{"a", "b"};
  v.push_back(std::move(v[0]));
  // 不受保证：库可以假定实参
  // 不与容器里的元素重叠
}
```

</div>

`push_back` 可能需要扩容。扩容时库把旧元素搬到新存储里，如果实参恰好引用其中一个旧元素，就得小心先后顺序。对左值实参，标准没有给库任何豁免，库必须处理好这种别名情形。

¶1.3 实参绑定到右值引用形参时，实现可以假定这个形参是指向该实参的唯一引用。注 2 解释了它的意思：程序用 `std::move(x)` 把一个左值传给库函数，等于告诉库可以把 `x` 当作临时对象，库因此可以省掉别名检查。所以右边的代码违反了库的前提。`v.insert(pos, std::move(v.back()))`、`s.append(std::move(s))` 也是同样的情形。

这条规则有两处限定：

- 注 1：形参是转发引用（`T&&`，`T` 由推导得出）且推导成左值引用时，实参并没有绑定到右值引用。所以 `v.emplace_back(v[0])` 不受影响，库仍要处理别名。
- 传给移动赋值运算符的实参可以就是 `*this`。因此对标准库类型做自移动赋值 `x = std::move(x)` 不是 UB，[[lib.types.movedfrom#2]] 规定之后对象处于有效但未指明的状态。

## 跨线程访问库对象 [res.on.objects]

¶1 如果从不同线程调用标准库函数可能引入**数据竞争**（[[g:data-race]]：两个线程访问同一内存位置，至少一个是写，且没有同步），程序的行为未定义。什么时候会发生数据竞争，由 [[res.on.data.races]] 规定。

两条合起来就是标准库的线程安全模型，常被概括为和 `int` 一样：

| 操作 | 结果 |
|---|---|
| 多个线程同时调用同一对象的 `const` 成员函数 | 安全：库不会在 `const` 调用中修改共享状态 |
| 一个线程修改对象，另一个线程同时读取它 | 数据竞争，UB |
| 多个线程各自操作不同的对象 | 安全：库不会访问实参以外的共享对象 |
| 明确规定可共享的对象（`std::atomic`、`std::mutex`、`std::cout`…） | 按各自的规定 |

```cpp ub
#include <mutex>
#include <thread>
int main() {
  auto* m = new std::mutex;
  std::thread t([m] { std::lock_guard g(*m); });
  delete m;   // UB：线程里对 *m 的访问不一定先于析构
  t.join();
}
```

¶2 访问标准库类型的对象时，对象生命周期的开始必须**发生先于**（[[g:happens-before]]）这次访问，这次访问又必须发生先于生命周期的结束，否则行为未定义。注 2 特意指出，这对 `std::mutex` 这种本身用来做同步的对象也成立。

mutex 能保护别的数据，保护不了它自己的创建和销毁。上例中构造 `*m` 发生在启动线程之前，没有问题；但 `delete m` 与线程中的加锁之间没有任何先后关系。正确的写法是先 `t.join()` 再 `delete m`。

## 用户提供的组件必须满足要求 [res.on.functions]

¶1 库在几种场合依赖程序提供的组件：替换函数、处理函数，以及用来实例化库模板的类型上的操作。这些组件不满足要求时，标准对实现不作任何要求。

¶2 具体来说，以下情形行为未定义：

| ¶ | 情形 | 例子 |
|---|---|---|
| 2.1 | 替换函数没有实现其 *Required behavior* 段落的语义 | 替换的 `operator new` 失败时返回空指针 |
| 2.2 | 处理函数没有实现其 *Required behavior* 段落的语义 | `terminate_handler` 返回了 |
| 2.3 | 用作模板实参的类型，其操作不符合相应要求条款的语义 | 比较器不是严格弱序；`==` 不是等价关系 |
| 2.4 | 替换函数、处理函数或析构操作以异常退出，除非明确允许 | 容器元素的析构函数抛出异常 |
| 2.5 | 用不完整类型实例化库模板或求值概念，除非该组件明确允许 | 见下例 |

***Required behavior*** 是库函数说明中的一种段落，规定替换版本或用户安装的版本必须做到什么（[[structure.specifications#5]]）。

¶2.3 是所有 Cpp17 命名要求（[[utility.requirements]]）的法律后果：类型不满足 *Cpp17LessThanComparable*、*Cpp17Hash* 这些要求，编译器多半不报错，但程序有 UB。¶2.3 的后半句同样重要：除非另有说明，这些操作可以通过抛异常报告失败，库必须能正确处理。容器的各种异常安全保证就建立在这一点上。

```cpp ub
#include <map>
#include <vector>
struct Node {
  std::vector<Node> children;   // OK：vector 明确允许不完整类型
  std::map<int, Node> index;    // UB：map 没有这样的许可（¶2.5）
};
int main() {}
```

在 `Node` 的定义内部，`Node` 还是不完整类型。明确允许不完整元素类型的组件有 `vector`、`list`、`forward_list`（在分配器满足[[allocator.requirements.completeness|完整性要求]]时，并且要在使用某些成员之前让元素类型完整），以及 `unique_ptr`、`shared_ptr` 等。`map`、`deque`、`unordered_map` 不在其列，上例在实践中能编译，但标准不保证。

类型萃取另有规则（[[meta.rqmts]]）：大多数萃取允许不完整类型，但如果结果可能因为类型以后变完整而不同，行为就是未定义的，例如对不完整类型问 `is_trivially_copyable`。

## 替换函数 [replacement.functions]

```cpp run ok
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <vector>

static std::size_t count = 0;

void* operator new(std::size_t n) {   // 替换全局 operator new
  ++count;
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc{};             // 失败时必须抛异常
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  std::vector<int> v(100);
  std::printf("allocations: %zu\n", count);   // 本机输出 1
}
```

有些库函数是**可替换的**（replaceable）：程序可以给出一个签名相同的定义，叫做**替换函数**（[[g:replacement-function]]），程序启动前它就取代了实现提供的默认版本（[[dcl.fct.def.replace]]）。

¶1 对可替换函数，库条款里的语义描述同时约束默认版本和程序的替换版本。替换函数必须满足 *Required behavior* 段落，否则就是上一节 ¶2.1 的 UB。

当前草案中的可替换函数如下：

| 函数 | 所在条款 |
|---|---|
| 全局 `operator new`、`operator new[]`、`operator delete`、`operator delete[]` 的各种形式（含 `nothrow`、对齐、带大小的版本，不含布置形式） | [[new.delete]] |
| `std::is_debugger_present()` {{c++26}} | [[debugging]] |
| 契约违反处理函数 `::handle_contract_violation`，是否可替换由实现定义 | [[basic.contract.handler]] |
| `std::execution::parallel_scheduler_replacement::query_parallel_scheduler_backend()` {{c++26}} | [[exec.parschedrepl]] |

替换 `operator new` 时常见的错误有：

- 失败时返回空指针而不抛 `bad_alloc`。`new` 表达式会在空指针上构造对象，这是 ¶2.1 的 UB。
- 只替换了 `operator new`，没有替换配套的 `operator delete`。如果自己的 `new` 不是用 `malloc` 实现的，释放时就会配错。
- 把替换函数声明为 `inline`，这是 IFNDR（[[dcl.fct.def.replace#1]]）。声明为 `static` 则直接非良构，因为全局分配函数不能有内部链接（[[basic.stc.dynamic.allocation]]），本机 Clang 会报错。
- 在替换函数里调用本身会分配内存的函数，例如 `std::cout`，导致无限递归。

## 处理函数 [handler.functions]

```cpp run ok
#include <cstdio>
#include <new>

void my_new_handler() {
  std::fputs("out of memory\n", stderr);
  throw std::bad_alloc{};   // 必须腾出内存后返回、抛 bad_alloc 或终止，三选一
}

int main() {
  std::set_new_handler(my_new_handler);
  return std::get_new_handler() == my_new_handler ? 0 : 1;
}
```

**处理函数**（handler function）是程序在运行时安装、由库在特定事件发生时调用的函数。标准库有两种：

- [[g:new-handler|`new_handler`]]：`operator new` 分配失败时调用，用 `set_new_handler` 安装（¶2.1），用 `get_new_handler` 读取（¶3.1）；
- [[g:terminate-handler|`terminate_handler`]]：`std::terminate` 调用它，用 `set_terminate` 安装（¶2.2），用 `get_terminate` 读取（¶3.2）。

¶1 库只为 `terminate_handler` 提供默认版本。`new_handler` 默认为空，这时 `get_new_handler()` 返回空指针，`operator new` 分配失败就直接抛出 `bad_alloc`。

处理函数必须做什么，写在 [[new.handler]] 和 [[terminate.handler]] 的 *Required behavior* 里。例如 `terminate_handler` 必须结束程序，不能返回调用者；返回了就是 [res.on.functions] ¶2.2 的 UB。

¶4 调用 `set_*` 和 `get_*` 函数不会引起数据竞争。对某个 `set_*` 的调用**同步于**（[[g:synchronizes-with]]）之后对同一个 `set_*` 以及对应 `get_*` 的调用。换句话说，一个线程 `set_terminate(h)` 之后，另一个线程随后的 `get_terminate()` 能看到 `h`。实现一般用原子变量做到这一点。

## 从标准库类派生 [derived.classes]

¶1 标准库基类的虚成员函数，可以在程序定义的派生类中覆盖（[[class.virtual]]）。这是库明确留给用户的扩展方式之一：

| 基类 | 常被覆盖的虚函数 |
|---|---|
| `std::exception` 及其派生类 | `what()` |
| `std::basic_streambuf` | `overflow`、`underflow`、`sync`… |
| `std::pmr::memory_resource` | `do_allocate`、`do_deallocate`、`do_is_equal` |
| `std::error_category` | `name`、`message`… |
| `std::locale::facet` 的各个派生类 | 各个 `do_*` 函数 |

```cpp run ok
#include <ostream>
#include <sstream>
#include <streambuf>

// 把字母转成大写再转发的 streambuf
class upper_buf : public std::streambuf {
  std::streambuf* dest_;
protected:
  int_type overflow(int_type ch) override {
    if (traits_type::eq_int_type(ch, traits_type::eof()))
      return traits_type::not_eof(ch);
    char c = traits_type::to_char_type(ch);
    if (c >= 'a' && c <= 'z') c = static_cast<char>(c - 'a' + 'A');
    return dest_->sputc(c);
  }
public:
  explicit upper_buf(std::streambuf* d) : dest_(d) {}
};

int main() {
  std::stringbuf sink;
  upper_buf ub(&sink);
  std::ostream os(&ub);
  os << "hello";
  return sink.str() == "HELLO" ? 0 : 1;
}
```

覆盖的函数仍要满足基类虚函数规定的语义。例如 `memory_resource::do_allocate` 必须返回对齐合适的存储或抛出异常。

这条只说虚函数。从 `std::vector` 这类没有虚析构函数的类公有派生并没有被禁止，但通过基类指针 `delete` 派生类对象是 UB（[[expr.delete]]）。

## 满足与建模 [res.on.requirements]

```cpp ifndr
#include <algorithm>
#include <vector>
struct Weird {
  int v;
  bool operator==(const Weird&) const { return false; }   // a == a 为假
};
int main() {
  std::vector<Weird> w{{1}, {2}};
  auto it = std::ranges::find(w, Weird{1});   // 要求 Weird 建模 equality_comparable
  return it == w.end();
}
```

编译器检查概念时只看语法：表达式是否有效、类型是否对得上，这叫**满足**（satisfy，[[temp.constr.decl]]）。但概念的说明里还有用文字写的**语义要求**，例如 `equality_comparable` 要求 `==` 表示相等，因而必须自反。上例的 `Weird` 满足 `equality_comparable`，语义上却不符合。

¶1 一组模板实参满足概念 `C`，并且符合 `C` 的所有语义要求时，就说它**建模**（model，[[g:models-concept]]）了 `C`。

¶2 如果程序的有效性或含义取决于某组模板实参是否建模某个概念，而这个概念被满足却没有被建模，程序非良构，不要求诊断。

¶3 声明的约束带有语义要求（[[structure.requirements]]），而在使用点这些要求没有被建模时，程序同样非良构、不要求诊断。上例调用 `ranges::find` 正属于这种情形。

为什么这里是 IFNDR，而上一节 Cpp17 要求不满足是 UB？概念参与重载决议和 `requires` 的判断，建模与否可能改变程序选中哪个函数、哪段代码有效，影响的是程序的含义，而不只是某一次运行的行为。核心语言对同类问题也用 IFNDR，例如原子约束在不同位置的满足结果不同（[[temp.constr.atomic]]）。

## 不要冒充标准头文件 [alt.headers]

¶1 如果一个文件不是实现提供的，文件名却与某个标准库头文件等价，又被放在了标准的包含位置（系统包含目录、`-isystem` 指定的目录等），行为未定义。

典型的场景是 polyfill：编译器还没有 `<expected>`，于是自己写一个名为 `expected` 的文件放进系统包含路径。标准库的其他头文件可能对 `<expected>` 的内容有自己的假设，编译器升级后还会出现两个 `<expected>`。

正确的做法是用自己的头文件名和命名空间（例如 `<tl/expected.hpp>`），再用 `__has_include(<expected>)` 或特性测试宏 `__cpp_lib_expected` 选择用哪一个。

<details class="fine" markdown="1"><summary>其余条文</summary>

[constraints.overview] ¶1 只是列出本节各子条款的内容：命名空间的使用、保留名字、头文件、把库类作为基类、替换函数、运行时安装处理函数。

</details>

## 思考题

!!! question "思考题 1"
    在自己替换的 `operator delete(void*)` 里调用 `std::printf` 打日志，违反标准吗？换成 `std::cout << "freed\n"` 呢？

<details markdown="1">
<summary>答案</summary>

标准层面，`operator delete` 的 *Required behavior* 只要求正确释放内存（对空指针什么也不做），并且不抛异常。调用 `printf` 本身不违反它。

实践层面这很危险。`std::cout` 的输出可能分配内存，分配和释放又会进入你替换的 `operator new` / `operator delete`，造成递归或重入；有些 C 库的 `printf` 在第一次调用时也会分配缓冲区。`operator delete` 还可能在静态对象析构阶段被调用，那时别的全局状态可能已经销毁。所以替换函数里一般只用不分配内存的原语记录日志，例如 POSIX 的 `write`。
</details>

!!! question "思考题 2"
    `std::string s = "abc"; s = std::move(s);` 是 UB 吗？之后还能调用 `s.size()` 吗？

<details markdown="1">
<summary>答案</summary>

不是 UB。[res.on.arguments] ¶1.3 明确允许传给移动赋值运算符的实参就是 `*this`，[[lib.types.movedfrom#2]] 规定标准库类型自移动赋值后处于有效但未指明的状态。所以 `s.size()` 可以调用，只是返回值不确定；`s.clear()`、`s = "x"` 这类没有前置条件的操作也都可以用。

如果换成用户类型，自移动赋值的结果取决于类型自己的实现。但库算法可能在内部对同一个元素做自移动赋值，所以放进容器、交给算法的类型要能承受：*Cpp17MoveAssignable* 的注 2 要求，即使 `t` 和 `rv` 是同一个对象，`rv` 也仍须满足组件的要求（[[utility.arg.requirements]]）。
</details>
