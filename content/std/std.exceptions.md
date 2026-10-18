---
title: 异常类
summary: <stdexcept> 的九个异常类：logic_error（本可预防的程序逻辑错误）与 runtime_error（超出程序控制的事件）两大分支；统一的构造函数与 what() 后置条件、复制不抛异常的要求与 libc++ 的引用计数字符串实现、标准库中谁抛哪个异常，以及 C++26 起的 constexpr 构造函数。
status: done
covers: *
related: diagnostics, support.exception, except, res.on.exception.handling, syserr, exception
tags: 标准库, 异常, logic_error, runtime_error
updated: 2026-10-18
---

`<stdexcept>` 是标准库最古老的错误报告设施之一（C++98 就有），内容极其简单：九个从 `std::exception`（[[support.exception]]）派生的类，每个类只有两个构造函数。值得花时间的不是它们的接口，而是它们背后的**错误分类模型**，以及标准库到底在什么情况下抛哪一个。

## 错误分类模型（[std.exceptions.general]）

¶1：标准库提供一组类，用于报告 C++ 程序中的某些错误（[[res.on.exception.handling]]）。在这些类所反映的错误模型中，错误分为两大类：**逻辑错误**（*logic errors*）与**运行期错误**（*runtime errors*）。

!!! std
    The distinguishing characteristic of logic errors is that they are due to errors in the internal logic of the program. In theory, they are preventable.

    逻辑错误的区分特征是：它们源于程序内部的逻辑错误。**理论上，它们是可以预防的。**

¶3：与之相对，运行期错误源于**超出程序范围**的事件，无法轻易预先预测。`<stdexcept>` 定义的这些异常类型通过继承相互关联。

这条分界线的含义是"**调用者是否本可以在调用前检查出问题**"：

- `v.at(i)` 抛 `out_of_range`——调用者本可以先检查 `i < v.size()`。逻辑错误。
- `bitset<128>::to_ulong()` 抛 `overflow_error`——调用者理论上也能先检查，但被归入运行期错误，因为"算术溢出"在传统上被视为计算过程中的事件。分类并不总是严格遵循 ¶2/¶3 的定义，而更多是历史延续。
- 打开文件失败（`filesystem_error`，经由 `system_error` 派生自 `runtime_error`）——文件是否存在不由程序控制。运行期错误。

!!! note "逻辑错误为什么还要抛异常？"
    既然逻辑错误"理论上可预防"，它就是 bug。按现代观点，bug 最好用断言或契约（[[assertions]]、[[basic.contract]]）报告并尽早终止，而不是抛异常让调用者"处理"——调用者通常并不知道如何从自己的 bug 中恢复。`logic_error` 族的存在反映的是 C++98 时代"用异常报告一切错误"的设计哲学。今天的标准库在新接口中更倾向于把这类情形写成**前置条件**（违反即 UB，或在强化实现中成为契约违反），只在 `at()` 这类明确提供"带检查版本"的接口上保留 `logic_error`。

## 类层次（[stdexcept.syn]）

```text
exception                       （<exception>，见 [support.exception]）
├── logic_error                 本可预防的逻辑错误
│   ├── domain_error            定义域错误
│   ├── invalid_argument        无效实参
│   ├── length_error            长度超过最大允许值
│   ├── out_of_range            实参不在期望范围内
│   └── future_error            （<future>）
└── runtime_error               只能在运行时检测的错误
    ├── range_error             内部计算的值域错误
    ├── overflow_error          算术上溢
    ├── underflow_error         算术下溢
    ├── system_error            （<system_error>，见 [syserr]）
    │   ├── ios_base::failure   （<ios>）
    │   └── filesystem_error    （<filesystem>）
    ├── format_error            （<format>）
    └── regex_error             （<regex>）
```

概要（[stdexcept.syn]）只声明了前九个类，缩进本身就是注释——标准用排版暗示继承关系。其他标准库异常（`bad_alloc`、`bad_cast`、`bad_optional_access`、`bad_expected_access` 等）直接派生自 `exception`，不属于这两个分支。

## 统一的接口（[logic.error] … [underflow.error]）

九个类的规格几乎完全相同，以 `logic_error` 为例：

```cpp
namespace std {
  class logic_error : public exception {
  public:
    constexpr explicit logic_error(const string& what_arg);
    constexpr explicit logic_error(const char* what_arg);
  };
}
```

每个类的 ¶2、¶3 都是同样的后置条件：

- 从 `const string&` 构造：`strcmp(what(), what_arg.c_str()) == 0`；
- 从 `const char*` 构造：`strcmp(what(), what_arg) == 0`。

要点：

1. **没有默认构造函数**。必须给出消息。（[[exception#2]] 规定从 `exception` 派生的标准库类有默认构造函数"除非类概要给出了其他构造函数"——这里给出了。）
2. **构造函数是 `explicit` 的**，所以 `throw std::runtime_error{"x"}` 可以，`std::runtime_error e = "x";` 不行。
3. **`what()` 返回的是消息的副本**，与 `what_arg` 内容相同，但生命期由异常对象管理——构造后修改或销毁原来的 `string` 不影响 `what()`。
4. 各类的 ¶1 只给出"用来报告什么"的一句话描述：`domain_error` 报告定义域错误；`invalid_argument` 报告无效实参；`length_error` 报告"试图产生长度超过最大允许大小的对象"；`out_of_range` 报告实参值不在期望范围内；`range_error` 报告内部计算中的值域错误；`overflow_error`/`underflow_error` 报告算术上溢/下溢。`logic_error` 本身（[[logic.error]] ¶1）用于"程序执行前大概就能检测到的错误，例如违反逻辑前置条件或类不变式"；`runtime_error`（[[runtime.error]] ¶1）用于"大概只有在程序执行时才能检测到的错误"。

### 复制不得抛异常

`what()` 的字符串由异常对象自己保存，这就带来一个问题：异常对象在抛出时会被复制（[[except.throw]]），如果复制需要分配内存，就可能在抛异常的过程中再抛 `bad_alloc`。[[exception#2]] 因此要求：每个从 `exception` 派生的标准库类，其复制构造函数与复制赋值运算符都具有**不抛出的异常说明**，并且复制后 `strcmp(lhs.what(), rhs.what()) == 0`。

所以这些类不能简单地用一个 `std::string` 成员来存消息。

!!! impl "libc++ 的引用计数字符串"
    libc++ 的 `<stdexcept>` 中，`logic_error` 与 `runtime_error` 各有一个 `__libcpp_refstring __imp_` 成员：一个只含 `const char*` 的句柄，指向一块"引用计数 + 字符串"的堆内存。构造时分配一次（可能抛 `bad_alloc`——那是在 `throw` 之前），之后复制只是原子地增加引用计数，`noexcept`。九个类都只是继承这两个基类的存储。libstdc++ 采用了类似的写时复制字符串方案。

```cpp run title="who-throws-what.cpp" ok
#include <bitset>
#include <cstdio>
#include <future>
#include <stdexcept>
#include <string>
#include <vector>

template<class F> void probe(const char* what, F f) {
  try { f(); }
  catch (const std::logic_error& e)   { std::printf("%-18s logic_error:   %s\n", what, e.what()); }
  catch (const std::runtime_error& e) { std::printf("%-18s runtime_error: %s\n", what, e.what()); }
}

int main() {
  probe("vector::at",       [] { std::vector<int> v; (void)v.at(1); });                      // out_of_range
  probe("stoi(\"x\")",      [] { (void)std::stoi("x"); });                                   // invalid_argument
  probe("stoi(huge)",       [] { (void)std::stoi("99999999999"); });                         // out_of_range
  probe("vector::reserve",  [] { std::vector<int> v; v.reserve(v.max_size() + 1); });        // length_error
  probe("bitset::to_ulong", [] { std::bitset<128> b; b.set(100); (void)b.to_ulong(); });     // overflow_error
  probe("get_future twice", [] { std::promise<int> p; (void)p.get_future(); (void)p.get_future(); }); // future_error
}
```

`what()` 的具体文本由实现定义，所以上面只能保证落入哪个分支。

## 标准库中谁抛哪个

| 异常 | 标准库中的典型抛出点 |
|---|---|
| `out_of_range` | `at()`（`vector`、`string`、`array`、`deque`、`map` 等）、`string::substr`/`insert` 的位置越界、`stoi` 族结果超出范围、`bitset::set(pos)` 等 |
| `invalid_argument` | `stoi` 族无法转换、`bitset` 从含非法字符的字符串构造 |
| `length_error` | 容器的 `reserve`/构造请求超过 `max_size()`、`string` 增长超过 `max_size()` |
| `domain_error` | 标准库自身几乎不抛；留给用户代码 |
| `overflow_error` | `bitset::to_ulong`/`to_ullong` 的值放不下 |
| `range_error` | 已弃用的宽窄字符转换设施（`wstring_convert`）在转换失败时 |
| `underflow_error` | 标准库自身不抛；留给用户代码 |

`length_error` 与 `bad_alloc` 的区别值得注意：请求超过 `max_size()` 是**逻辑上不可能**（抛 `length_error`）；不超过 `max_size()` 但内存不足是**运行期资源耗尽**（抛 `bad_alloc`）。`bad_alloc` 不属于 `runtime_error` 分支，`catch (const std::runtime_error&)` 抓不到它。

## C++26：constexpr 构造函数

当前草案中九个类的构造函数都是 `constexpr`，`exception` 的成员也是（[[exception]]）。这是为了配合 C++26 允许在常量求值中抛出并捕获异常（[[P3068R6]]）：在 `constexpr` 函数里抛 `std::out_of_range`，若在常量求值中被捕获，就不再导致"不是常量表达式"。

!!! warning "编译器支持"
    截至本文编写时，本机 Clang 23 + libc++ 尚不支持在常量求值中抛出异常，`<stdexcept>` 的构造函数也还不是 `constexpr`：

    ```cpp
    #include <stdexcept>
    constexpr bool f() {
      try { throw std::logic_error("x"); } catch (const std::exception&) { return true; }
    }
    static_assert(f());   // 草案：OK；Clang 23 + libc++：不是整型常量表达式
    ```

## 陷阱

!!! pitfall "按值捕获导致切片"
    `catch (std::exception e)` 会把 `out_of_range` 切成 `exception`，`what()` 退化为基类版本（返回由实现定义的字符串）。永远按 `const&` 捕获。

!!! pitfall "以为 `catch (const std::runtime_error&)` 能兜住\"运行期\"的所有错误"
    `bad_alloc`、`bad_cast`、`bad_optional_access` 都不在 `runtime_error` 分支里；`future_error` 甚至在 `logic_error` 分支里。需要兜底时捕获 `const std::exception&`。

!!! pitfall "从 `std::string` 构造临时消息的开销"
    `throw std::runtime_error("open " + path + " failed")` 在抛出前构造了两个临时 `string`，再在异常对象里复制一份。热路径上这通常不是问题（抛异常本身就很贵），但在内存耗尽的情形下，构造消息本身可能抛 `bad_alloc`，掩盖原本的错误。

## 思考题

!!! question "思考题"
    1. 为什么 `std::system_error` 派生自 `runtime_error` 而不是直接派生自 `exception`？
    2. 一个自定义异常类 `struct my_error : std::runtime_error { std::string detail; ... };` 违反了标准的什么要求吗？
    3. `std::logic_error e("x"); std::logic_error f = e;` 之后，`e.what() == f.what()`（指针相等）一定成立吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 系统调用失败是典型的"超出程序范围的事件"（[[std.exceptions.general]] ¶3），归入 `runtime_error` 分支符合分类模型；同时这让旧代码中 `catch (const std::runtime_error&)` 能捕获到它，包括 C++11 起改为派生自 `system_error` 的 `ios_base::failure`。
2. 不违反标准——[[exception#2]] 的"复制不抛异常"约束的是**标准库**中的类，不是用户类。但它违反了这条约束背后的工程原则：`std::string` 成员的复制可能抛 `bad_alloc`。异常处理机制会在若干时刻复制异常对象——例如按值捕获时用它初始化 handler 的形参（[[except.handle]]），`std::current_exception` 也可能复制它——而在异常对象初始化完成之后、handler 激活之前，若异常处理机制调用的函数以异常退出，就会调用 `std::terminate`（[[except.terminate]]）。用户的异常类最好也只持有不抛异常复制的数据（例如 `shared_ptr<const string>`，或者把信息放进基类的 `what_arg`）。
3. 不一定。标准只要求 `strcmp(e.what(), f.what()) == 0`。libc++ 的引用计数实现下两个指针恰好相等（共享同一块存储），但这是实现细节。
</details>

## 小结

!!! summary
    - 两大分支：`logic_error`（理论上可预防：前置条件、类不变式）与 `runtime_error`（超出程序控制）；分类有历史成分，并不总是严格。
    - 九个类接口相同：两个 `explicit` 构造函数（`const string&` / `const char*`），后置条件为 `what()` 与 `what_arg` 内容相同；无默认构造函数。
    - 复制与复制赋值不得抛异常（[[exception#2]]），实现因此使用引用计数的不可变字符串。
    - 其他库异常：`future_error` 属于 `logic_error`；`system_error`、`format_error`、`regex_error` 属于 `runtime_error`；`bad_alloc` 等直接派生自 `exception`。
    - 当前草案中构造函数是 `constexpr` 的（配合 C++26 常量求值中的异常），libc++ 尚未实现。
