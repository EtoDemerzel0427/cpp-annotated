---
title: 对程序的约束
summary: 标准库对用户程序的义务清单：不得在标准位置放置同名头文件；可以覆盖标准基类的虚函数；替换函数（operator new/delete、契约违反处理函数……）与处理函数（new_handler、terminate_handler）必须满足必需行为；用户提供的组件不满足要求即 UB；库函数的实参必须有效，右值引用实参被假定为唯一引用；跨线程访问库对象不得构成数据竞争；概念被满足但未被建模时 IFNDR。
status: done
covers: constraints.overview, alt.headers, derived.classes, replacement.functions, handler.functions, res.on.functions, res.on.arguments, res.on.objects, res.on.requirements
related: namespace.constraints, reserved.names, conforming, description, utility.requirements, dcl.fct.def.replace, basic.contract, intro.races, lib.types.movedfrom, temp.constr.decl, new.delete
tags: 库, UB, IFNDR, 替换函数, 数据竞争, 移动语义
updated: 2026-10-18
---

[[constraints]]（16.4.5）列出 C++ 程序在使用标准库时必须遵守的约束。其中命名空间的使用（[[namespace.constraints]]）与保留名字（[[reserved.names]]）两部分篇幅较大，单独成页；本页覆盖其余各节。

¶1（[constraints.overview]）概述了内容：以下子条款规定对程序在命名空间使用、各种保留名字使用、头文件使用、把标准库类作为基类使用（[derived.classes]）、替换函数定义，以及执行期间安装处理函数方面的约束。

这些约束有一个共同点：违反的后果几乎都是 UB 或 IFNDR。它们规定的是程序与库之间的约定，编译器通常无从检查。

## 不要冒名顶替标准头文件（[alt.headers]）

¶1 若某个与 C++ 标准库头文件的派生文件名等价的文件不是作为实现的一部分提供的，而有一个这样名字的文件放在了任何标准的源文件包含位置中，行为未定义。

这条针对的是 polyfill 头文件。假设你的编译器还没有 `<expected>`，于是你自己写了一个名为 `expected` 的文件，放进系统包含目录（或通过 `-isystem`）。此后 `#include <expected>` 找到的就是你的文件，但标准库中其他头文件可能对 `<expected>` 的内容有假设，将来编译器升级后又会出现两个 `<expected>`。标准把这种做法定为 UB。

正确的 polyfill 做法是放在自己的命名空间和自己的头文件名中（例如 `<tl/expected.hpp>`），通过 `__has_include(<expected>)` 与特性测试宏 `__cpp_lib_expected` 选择。

## 可以覆盖标准基类的虚函数（[derived.classes]）

¶1 C++ 标准库中为基类定义的虚成员函数签名，可以在程序定义的派生类中覆盖（[[class.virtual]]）。

这是库明确允许用户扩展的少数方式之一。典型的可派生基类如下：

| 基类 | 常被覆盖的虚函数 |
|---|---|
| `std::exception` 及其派生类 | `what()` |
| `std::basic_streambuf` | `overflow`、`underflow`、`sync`、`xsputn`…… |
| `std::pmr::memory_resource` | `do_allocate`、`do_deallocate`、`do_is_equal` |
| `std::error_category` | `name`、`message`、`default_error_condition`…… |
| `std::locale::facet` 系列（`std::ctype`、`std::numpunct`……） | `do_*` 系列 |
| `std::execution::parallel_scheduler_backend` {{c++26}} | 调度接口 |

```cpp run ok
#include <ostream>
#include <sstream>
#include <streambuf>

// 把每个字符转为大写再输出的 streambuf
class upper_buf : public std::streambuf {
  std::streambuf* dest_;
protected:
  int_type overflow(int_type ch) override {            // 覆盖标准基类的虚函数
    if (traits_type::eq_int_type(ch, traits_type::eof())) return traits_type::not_eof(ch);
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

覆盖时仍要满足基类虚函数规定的语义，例如 `memory_resource::do_allocate` 必须返回适当对齐的存储或抛异常，否则就落入 [res.on.functions] 的 UB。注意本条只针对虚函数：从 `std::vector` 等非多态类公有派生并不被禁止，但它们的析构函数不是虚的，通过基类指针 `delete` 派生对象是 UB（[[expr.delete]]）。

## 替换函数（[replacement.functions]）

¶1 若第 17–33 章及附录 D 中定义的某个函数规定为可替换的（replaceable，[[dcl.fct.def.replace]]），则其函数语义的描述同时适用于标准库定义的默认版本和程序定义的替换函数。

当前草案中的可替换函数如下：

| 函数 | 位置 |
|---|---|
| 全局 `operator new` / `operator new[]` / `operator delete` / `operator delete[]` 的各种形式（含 `nothrow`、对齐、带大小的版本；不含布置形式） | [new.delete] |
| `std::is_debugger_present()` {{c++26}} | [debugging] |
| 契约违反处理函数 `::handle_contract_violation`（是否可替换由实现定义，见 `__cpp_lib_replaceable_contract_violation_handler`） | [[basic.contract]] |
| `std::execution::parallel_scheduler_replacement::query_parallel_scheduler_backend()` {{c++26}} | [exec.parschedrepl] |

[[dcl.fct.def.replace]] 规定了替换函数在语言层面的形式要求（非 `inline`、附属于全局模块、C++ 语言链接、返回类型相同……违反为 IFNDR）。本条补上了语义要求：替换函数必须实现 *Required behavior*（[[structure.specifications#5]]），否则 UB（[res.on.functions] ¶2.1）。

```cpp run ok
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <vector>

static std::size_t count = 0;

void* operator new(std::size_t n) {          // 替换函数：必需行为——返回适当对齐的非空指针，
  ++count;                                    //           或抛出 bad_alloc
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
  std::vector<int> v(100);
  std::printf("allocations: %zu\n", count);   // 本机输出：allocations: 1
}
```

常见的错误有以下几种：

- `operator new` 失败时返回 `nullptr` 而不是抛异常。这违反必需行为，是 UB（`new` 表达式会把空指针当成合法存储去构造对象）；
- 只替换 `operator new` 而不替换 `operator delete`，后者仍调用默认版本，若你的 `new` 不是用 `malloc` 实现的，就会配对错误；
- 替换函数声明为 `inline` 或 `static`，这是 IFNDR（[[dcl.fct.def.replace#1]]）；
- 在替换的 `operator new` 里调用会分配内存的函数（例如 `std::printf` 有时会、`std::cout` 一定会），导致无限递归。

## 处理函数（[handler.functions]）

¶1 C++ 标准库提供以下处理函数（第 17 章）的默认版本：

- **¶1.1** `terminate_handler`。

¶2 程序可以在执行期间安装不同的处理函数：把指向程序或库中定义的函数的指针作为实参，分别传给：

- **¶2.1** `set_new_handler`；
- **¶2.2** `set_terminate`。

另见 [alloc.errors]（存储分配错误）与 [support.exception]（异常处理）。

¶3 程序可以调用以下函数获取当前处理函数的指针：**¶3.1** `get_new_handler`；**¶3.2** `get_terminate`。

¶4 调用 `set_*` 和 `get_*` 函数不得引起数据竞争（[[intro.races]]）。对任何 `set_*` 函数的调用，同步于（synchronizes with）后续对同一 `set_*` 函数和相应 `get_*` 函数的调用。

¶4 对实现提出了线程安全要求：多个线程同时 `set_new_handler` 不是数据竞争；一个线程 `set_terminate(h)` 后，另一个线程随后的 `get_terminate()` 能看到 `h`。这通常用原子变量实现。

注意 `new_handler` 没有默认版本：默认情况下 `get_new_handler()` 返回空指针，于是 `operator new` 在分配失败时直接抛出 `bad_alloc`（[new.delete.single] 的默认行为）。

```cpp run ok
#include <cstdio>
#include <exception>
#include <new>

void my_new_handler() {
  // 必需行为（[new.handler]）：腾出更多内存后返回；或抛出 bad_alloc（或其派生类）；或终止
  std::fputs("out of memory\n", stderr);
  throw std::bad_alloc{};          // 这里选择第二种
}

int main() {
  std::set_new_handler(my_new_handler);
  return std::get_new_handler() == my_new_handler ? 0 : 1;
}
```

处理函数的必需行为写在 [[new.handler]] 与 [[terminate.handler]]：例如 `terminate_handler` 必须终止程序执行而不返回调用者。若一个 `terminate_handler` 返回了，就属于 [res.on.functions] ¶2.2 的 UB。

## 其他函数：用户组件不满足要求即 UB（[res.on.functions]）

¶1 在某些情况下（替换函数、处理函数、用于实例化标准库模板组件的类型上的操作），C++ 标准库依赖于 C++ 程序提供的组件。若这些组件不满足其要求，本文档对实现不作任何要求。

¶2 特别地，以下情形的行为未定义：

- **¶2.1** 对替换函数：安装的替换函数没有实现适用的 *Required behavior* 段落的语义。
- **¶2.2** 对处理函数（[[new.handler]]、[[terminate.handler]]）：安装的处理函数没有实现适用的 *Required behavior* 段落的语义。
- **¶2.3** 对实例化模板组件时用作模板实参的类型：该类型上的操作没有实现适用的 Requirements 子条款（[[allocator.requirements]]、[[container.requirements]]、[[iterator.requirements]]、[[algorithms.requirements]]、[[numeric.requirements]]）的语义。除非另有说明，这些类型上的操作可以通过抛出异常报告失败。
- **¶2.4** 任何替换函数、处理函数或析构操作以异常退出，除非适用的 *Required behavior* 段落明确允许。
- **¶2.5** 在实例化模板组件或求值概念时，以不完整类型（[[basic.types.general]]）作模板实参，除非该组件明确允许。

不满足 Cpp17 要求就是 UB，总的依据就是 ¶2.3（[[utility.requirements]] 中比较器、哈希、分配器的例子都归到这里）。它的后半句也很重要：用户类型的操作（拷贝构造、比较……）可以抛异常，库必须正确处理。容器的强异常保证、基本异常保证等规定正是由此而来。

¶2.4 把析构函数抛异常明确列为 UB，因为容器在销毁元素时若遇到异常，无法既保持自身一致又传播异常。

许多在实践中能够编译的代码，问题就出在 ¶2.5：

```cpp ub
#include <map>
#include <vector>
struct Node {
  std::vector<Node> children;   // OK：vector 明确允许不完整类型（[vector.overview]）
  std::map<int, Node> index;    // UB：map 没有允许不完整类型（¶2.5）
};
int main() { }
```

明确允许不完整类型的组件包括：`vector`、`list`、`forward_list`（在分配器满足[[allocator.requirements.completeness|完整性要求]]时，且须在引用其任何成员之前使 `T` 完整）、`unique_ptr<T>`（`T` 在需要完整类型的成员如析构函数被使用之前完整即可）、`shared_ptr<T>` 等。类型萃取另有一套规则（[[meta.rqmts]] ¶5）：默认允许用不完整类型实例化 [type.traits] 中的模板，但如果实例化依赖于某个不完整定义的对象类型 `T`，而 `T` 补全后结果可能不同，则行为未定义，例如对不完整类型问 `is_trivially_copyable`。

## 函数实参（[res.on.arguments]）

¶1 除非另有明确说明，以下各项适用于标准库中定义的函数的所有实参：

- **¶1.1** 若函数的实参具有无效值（例如函数定义域之外的值，或对其预期用途无效的指针），行为未定义。
- **¶1.2** 若函数实参描述为数组，实际传入的指针必须具有这样的值：所有（若指针确实指向这样一个数组的首元素就会有效的）地址计算和对象访问都确实是有效的。
- **¶1.3** 若函数实参绑定到右值引用形参，实现可以假定该形参是对该实参的唯一引用。例外是传给移动赋值运算符的实参可以是对 `*this` 的引用（[[lib.types.movedfrom]]）。

¶1.1 是兜底规则，无效实参一律是 UB：即使某个函数的规范里没有写 *Preconditions*，给它传一个悬垂指针、一个越界迭代器、一个空的 `const char*` 也是 UB。

### 右值引用实参的唯一性假定（¶1.3）

¶1.3 是 C++11 移动语义带来的一条很微妙的规则。Note 2 解释了它的含义：若程序在把左值传给库函数时把它转换为 xvalue（例如用 `std::move(x)` 调用函数），程序实际上是在请求该函数把这个左值当作临时对象对待。实现因此可以省略本来在实参是左值时可能需要的别名检查。

下面是一个经典例子：

```cpp
std::vector<std::string> v{"a", "b", "c"};
v.push_back(v[0]);              // OK：左值实参。实现必须正确处理"实参是容器自身元素"的情形
                                //     ——扩容时先构造新元素，再搬移旧元素
v.push_back(std::move(v[0]));   // 不保证：实现可以假定右值引用实参不与容器内的任何对象别名
                                //     ——若扩容时先搬移了旧元素，v[0] 就已经被移走了
```

对左值版本，库必须处理别名（标准没有给它豁免）；对右值版本，¶1.3 给了库豁免。所以第二行违反了 ¶1.3 隐含的前提，结果不受标准保证。同理的还有 `v.insert(pos, std::move(v.back()))`、`s.append(std::move(s))` 等。

Note 1 澄清，若形参是转发引用（[[temp.deduct.call]]）且推导为左值引用类型，则实参并非绑定到右值引用。所以 `v.emplace_back(v[0])`（左值，转发引用推导为 `std::string&`）不受 ¶1.3 影响，库仍需处理别名。

¶1.3 的例外规定传给移动赋值运算符的实参可以是 `*this`，这意味着自移动赋值 `x = std::move(x)` 对标准库类型不是 UB：[[lib.types.movedfrom#2]] 规定它使对象处于有效但未指明的状态。

## 库对象的访问（[res.on.objects]）

¶1 若从不同线程对标准库函数的调用可能引入数据竞争，程序行为未定义。可能发生这种情况的条件规定于 [[res.on.data.races]]。Note 1 指出，修改在线程间共享的标准库类型对象有未定义行为的风险，除非该类型的对象明确规定为可无数据竞争地共享，或用户提供了锁机制。

¶2 若访问了标准库类型的对象，而对象生命周期的开始不发生先于（happens before）该访问，或该访问不发生先于对象生命周期的结束，则行为未定义（除非另有说明）。Note 2 指出，这甚至适用于像互斥量这样本身用于线程同步的对象。

把 [res.on.objects] 与 [[res.on.data.races]] 合起来，就得到标准库的线程安全模型，通常概括为与 `int` 一样的线程安全：

| 操作 | 是否安全 |
|---|---|
| 多个线程同时调用同一对象的 `const` 成员函数 | 安全（[res.on.data.races] ¶3 保证库不会在 const 调用中修改共享状态） |
| 一个线程修改、另一个线程读取同一对象 | 数据竞争，UB |
| 多个线程分别操作不同对象 | 安全（库不得访问未经实参可达的共享对象） |
| 明确规定为可共享的对象（`std::atomic`、`std::mutex`、`std::cout` 等标准流对象……） | 按其规定 |

¶2 中的 Note 2 指出了一个容易忽视的问题：

```cpp ub
#include <mutex>
#include <thread>
int main() {
  auto* m = new std::mutex;                       // 构造 happens-before 线程启动：没问题
  std::thread t([m] { std::lock_guard g(*m); });  // 线程中访问 *m
  delete m;     // UB：*m 生命周期的结束不 happens-after 线程中的访问（¶2）
  t.join();
}
```

即使是 `std::mutex`，它自己的构造也必须 happens-before 其他线程对它的使用（通过线程创建、另一个同步原语等建立），所有使用也必须 happens-before 它的销毁。用 mutex 来保护 mutex 自己的创建和销毁是行不通的，这里正确的做法是先 `t.join()` 再 `delete m`。

## 语义要求：满足但未建模即 IFNDR（[res.on.requirements]）

¶1 若模板实参序列 `Args` 满足（satisfies）概念 `C`（[[temp.constr.decl]]），并且满足 `C` 的规范中给出的所有语义要求（如果有），就说 `Args` **建模**（model）`C`。

¶2 若程序的有效性或含义取决于某模板实参序列是否建模某概念，而该概念被满足但未被建模，程序非良构，不要求诊断。

¶3 若声明的约束的语义要求（[[structure.requirements]]）在使用点未被建模，程序非良构，不要求诊断。

这三段规定了概念语义部分的法律后果。编译器只检查满足，即语法上表达式有效、类型对得上；建模还包括文字描述的语义：`equality_comparable` 要求 `==` 反映相等性，`regular` 要求拷贝后相等，`sentinel_for` 要求 `s == i` 的含义一致……这些编译器查不了。

```cpp ifndr
#include <algorithm>
#include <vector>
struct Weird {
  int v;
  bool operator==(const Weird&) const { return false; }   // 语法上满足 equality_comparable
};                                                         // 语义上不建模（== 不自反）
int main() {
  std::vector<Weird> w{{1}, {2}};
  auto it = std::ranges::find(w, Weird{1});   // ranges::find 的约束要求 ranges::equal_to 可用于 Weird，
  return it == w.end();                       // 而 ranges::equal_to 要求 equality_comparable_with……
}                                             // 满足但未建模 → IFNDR（¶2、¶3）
```

为什么是 IFNDR 而不是 UB？因为建模与否影响的是程序的含义（选哪个重载、某个 `requires` 是否成立……），而不只是某次运行的行为。核心语言中，概念满足与否的结果在不同点不同时是 IFNDR，这里的处理方式与之一致（[[temp.constr]]）。作为对比，C++17 风格的 *Cpp17* 要求不满足时是 UB（[res.on.functions] ¶2.3）。

## 思考题

!!! question "思考题 1"
    用户在自己的 `operator delete(void*)` 替换函数里调用了 `std::printf`。这有问题吗？如果改成调用 `std::cout << "freed\n"` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

从标准层面看，`operator delete` 的必需行为只要求正确释放（对空指针则什么都不做）、不抛异常。调用 `printf` 本身不违反必需行为。

从实践层面看，`std::cout << ...` 可能分配内存（例如格式化或缓冲时），分配释放又会进入你的 `operator new`/`operator delete`，形成递归或重入；`printf` 在某些 C 库实现中也会在首次调用时分配缓冲区。另外，`operator delete` 可能在静态对象析构阶段被调用，此时程序中别的全局状态可能已经销毁。安全做法是在替换函数中只用不分配内存的原语（如 POSIX `write`）记录日志。
</details>

!!! question "思考题 2"
    `std::string s = "abc"; s = std::move(s);` 是 UB 吗？`s.size()` 之后能用吗？若 `s` 换成用户类型 `T` 的对象，放进 `std::vector<T>`，再对 `v[0] = std::move(v[0]);`，又如何？

<details markdown="1">
<summary>展开查看答案与解析</summary>

对 `std::string`，这不是 UB。[res.on.arguments] ¶1.3 为移动赋值运算符留了例外，[[lib.types.movedfrom#2]] 规定标准库类型的自移动赋值使对象处于有效但未指明的状态。所以 `s.size()` 可以调用（返回某个值），`s.clear()`、`s = "x"` 等无前置条件的操作都可以用。

对用户类型 `T`，`v[0] = std::move(v[0])` 是用户代码直接调用 `T` 的移动赋值，与库无关，行为取决于 `T` 的实现。但如果某个库算法（例如 `std::remove`、`std::rotate`）在实现中对同一元素做了自移动赋值，那么 `T` 必须能承受。*Cpp17MoveAssignable*（[[utility.arg.requirements]] 表 33）的 Note 2 要求，即使 `t` 与 `rv` 指代同一对象，`rv` 也必须仍满足组件的要求。
</details>

## 小结

!!! summary "核心要点"
    - 不要把自制的同名文件放进标准包含路径冒充标准头文件（UB）。
    - 可以覆盖标准基类的虚函数，但必须满足其语义。
    - 替换函数（全局 `operator new`/`delete`、`is_debugger_present`、契约违反处理函数……）与处理函数（new/terminate handler）必须实现 *Required behavior*；`set_*`/`get_*` 线程安全且有同步关系。
    - 用户组件不满足库的要求、析构抛异常、用不完整类型实例化不允许的组件，都是 UB。
    - 实参必须有效；右值引用实参被假定为唯一引用：`v.push_back(std::move(v[0]))` 不受保证，`v.push_back(v[0])` 受保证；自移动赋值对标准库类型是安全的。
    - 跨线程访问库对象：const 并发读安全，读写并发是 UB；对象生命周期必须与所有访问建立 happens-before，mutex 也不例外。
    - 概念被满足但未被建模 → IFNDR；Cpp17 要求不满足 → UB。
