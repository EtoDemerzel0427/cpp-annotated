---
title: 异常类
summary: <stdexcept> 的九个异常类：logic_error 与 runtime_error 两支各报告什么错误，统一的构造函数和 what() 要求，复制为什么不能抛异常，标准库在哪些地方抛哪一个。
status: done
covers: *
related: diagnostics, support.exception, except, res.on.exception.handling, syserr, exception
tags: 标准库, 异常, logic_error, runtime_error
updated: 2026-10-19
---

!!! tldr
    - `<stdexcept>` 的九个类分两支：`logic_error`（程序逻辑错误，理论上可以预防）和 `runtime_error`（超出程序控制的事件）。分类有历史成分，不总是严格。
    - 九个类的接口相同：两个 `explicit` 构造函数，分别接受 `const string&` 和 `const char*`；没有默认构造函数；`what()` 返回与实参内容相同的字符串。
    - 标准库的异常类复制时不得抛异常，所以实现用引用计数的不可变字符串保存消息，而不是 `std::string` 成员。
    - `bad_alloc`、`bad_cast` 等直接派生自 `exception`，`catch (const std::runtime_error&)` 抓不到它们。

## 谁抛哪个

```cpp run title="who-throws-what.cpp" ok
#include <bitset>
#include <cstdio>
#include <future>
#include <stdexcept>
#include <string>
#include <vector>

template<class F> void probe(const char* name, F f) {
  try { f(); }
  catch (const std::logic_error& e) {
    std::printf("%-16s logic_error:   %s\n", name, e.what());
  }
  catch (const std::runtime_error& e) {
    std::printf("%-16s runtime_error: %s\n", name, e.what());
  }
}

int main() {
  probe("vector::at", [] {        // out_of_range
    std::vector<int> v; (void)v.at(1); });
  probe("stoi(\"x\")", [] {        // invalid_argument
    (void)std::stoi("x"); });
  probe("stoi(huge)", [] {        // out_of_range
    (void)std::stoi("99999999999"); });
  probe("vector::reserve", [] {   // length_error
    std::vector<int> v; v.reserve(v.max_size() + 1); });
  probe("bitset::to_ulong", [] {  // overflow_error
    std::bitset<128> b; b.set(100); (void)b.to_ulong(); });
  probe("get_future x2", [] {     // future_error
    std::promise<int> p;
    (void)p.get_future(); (void)p.get_future(); });
}
```

`what()` 的文本由实现决定，所以上面能保证的只是每次落进哪个 `catch`。下表列出标准库里的典型抛出点：

| 异常 | 标准库中的典型抛出点 |
|---|---|
| `out_of_range` | 各容器和 `string` 的 `at()`；`string::substr`、`insert` 的位置越界；`stoi` 一族结果超出范围；`bitset::set(pos)` 等 |
| `invalid_argument` | `stoi` 一族无法转换；`bitset` 从含非法字符的字符串构造 |
| `length_error` | 容器的 `reserve` 或构造请求超过 `max_size()`；`string` 增长超过 `max_size()` |
| `overflow_error` | `bitset::to_ulong`、`to_ullong` 放不下结果 |
| `domain_error`、`range_error`、`underflow_error` | 标准库自身基本不抛，留给用户代码（`range_error` 以前由 `wstring_convert` 抛出，该设施已在 C++26 删除） |

`length_error` 和 `bad_alloc` 要分清：请求超过 `max_size()` 是逻辑上不可能，抛 `length_error`；没超过但内存不够，是运行期资源耗尽，抛 `bad_alloc`。

## 两类错误（[std.exceptions.general]）

¶1 标准库提供这些类，用来报告 C++ 程序中的某些错误（[[res.on.exception.handling]]）。它们反映的错误模型把错误分为两大类：**逻辑错误**（logic error）和**运行期错误**（runtime error）。

!!! std
    The distinguishing characteristic of logic errors is that they are due to errors in the internal logic of the program. In theory, they are preventable.

¶2 逻辑错误源于程序内部的逻辑错误，理论上可以预防。¶3 运行期错误则源于程序范围之外的事件，无法轻易预先预测。

实际的判断标准是调用者能否在调用之前查出问题。`v.at(i)` 抛 `out_of_range`，调用者本可以先检查 `i < v.size()`，所以是逻辑错误。打开文件失败抛 `filesystem_error`（经 `system_error` 派生自 `runtime_error`），文件是否存在不由程序控制，所以是运行期错误。`bitset::to_ulong` 的溢出调用者其实也能预先检查，却被归为运行期错误，因为算术溢出传统上被看作计算过程中发生的事件。

!!! note "逻辑错误为什么还要抛异常"
    逻辑错误理论上可以预防，也就是 bug。调用者通常不知道怎样从自己的 bug 里恢复，所以现在一般认为 bug 应该用断言或契约（[[assertions]]、[[basic.contract]]）报告并尽早终止。`logic_error` 一支体现的是 C++98 用异常报告一切错误的设计。新的标准库接口更倾向于把这类情形写成前置条件，只在 `at()` 这类明确提供带检查版本的接口上保留 `logic_error`。

## 类层次（[stdexcept.syn]）

```text
exception                    <exception>，见 [support.exception]
├── logic_error              程序执行前大概就能检测到的错误
│   ├── domain_error         定义域错误
│   ├── invalid_argument     无效实参
│   ├── length_error         长度超过允许的最大值
│   ├── out_of_range         实参不在期望范围内
│   └── future_error         <future>
└── runtime_error            大概只有执行时才能检测到的错误
    ├── range_error          内部计算中的值域错误
    ├── overflow_error       算术上溢
    ├── underflow_error      算术下溢
    ├── system_error         <system_error>，见 [syserr]
    │   ├── ios_base::failure     <ios>
    │   └── filesystem_error      <filesystem>
    ├── format_error         <format>
    └── regex_error          <regex>
```

`<stdexcept>` 的概要只声明前九个类，用缩进暗示继承关系。注释里的说明出自各类定义的第 1 段，比如 [[logic.error]] 说它报告违反逻辑前置条件或类不变式这类错误。其他标准库异常，如 `bad_alloc`、`bad_cast`、`bad_optional_access`、`bad_expected_access`，直接派生自 `exception`，不属于这两支。

## 统一的接口（[logic.error] 至 [underflow.error]）

九个类的规格几乎一样。以 `logic_error` 为例：

```cpp
namespace std {
  class logic_error : public exception {
  public:
    constexpr explicit logic_error(const string& what_arg);
    constexpr explicit logic_error(const char* what_arg);
  };
}
```

每个类的 ¶2、¶3 是同样的后置条件：从 `const string&` 构造后 `strcmp(what(), what_arg.c_str()) == 0`，从 `const char*` 构造后 `strcmp(what(), what_arg) == 0`。由此可以得出几点：

1. 没有默认构造函数，必须给出消息。[[exception#2]] 规定从 `exception` 派生的标准库类有默认构造函数，但除外了类概要列出其他构造函数的情形，这里正是这种情形。
2. 构造函数是 `explicit` 的。`throw std::runtime_error("x")` 可以，`std::runtime_error e = "x";` 不行。
3. `what()` 返回的是消息的副本，生命期由异常对象管理。构造之后修改或销毁原来的 `string`，不影响 `what()`。

### 复制不得抛异常

异常对象在抛出和捕获的过程中可能被复制（[[except.throw]]、[[except.handle]]）。如果复制需要分配内存，就可能在处理一个异常的途中再抛出 `bad_alloc`。所以 [[exception#2]] 要求：每个从 `exception` 派生的标准库类，其复制构造函数和复制赋值运算符都有不抛出的异常说明，并且复制后两边 `what()` 的内容相同。

这意味着实现不能简单地用一个 `std::string` 成员保存消息。

!!! impl "libc++ 的引用计数字符串"
    libc++ 的 `logic_error` 和 `runtime_error` 各有一个 `__libcpp_refstring` 成员，它只是一个指针，指向一块引用计数加字符串的堆内存。构造时分配一次，这时可能抛 `bad_alloc`，但那发生在 `throw` 之前。之后的复制只把引用计数原子地加一，不会抛异常。其余七个类都继承这两个基类的存储。libstdc++ 采用类似的写时复制字符串。

## C++26：`constexpr` 构造函数

当前草案中九个类的构造函数都是 `constexpr`，`exception` 的成员也是（[[exception]]）。这是为了配合 C++26 允许在常量求值中抛出并捕获异常（[[P3068R6]]）：`constexpr` 函数抛出的 `std::out_of_range` 如果在常量求值中被捕获，就不再使求值失败。

```cpp
#include <stdexcept>
constexpr bool f() {
  try { throw std::logic_error("x"); }
  catch (const std::exception&) { return true; }
}
static_assert(f());   // 按当前草案：OK
```

截至写作时，本机 Clang 23 还不支持在常量求值中抛出异常，连 `throw 1` 也不行，这段代码报 `static_assert` 的表达式不是常量表达式。所以上面的代码没有标判定。

## 常见误解

!!! pitfall "按值捕获"
    `catch (std::exception e)` 会把 `out_of_range` 切成一个 `exception` 对象，`what()` 变成基类版本，返回由实现定义的字符串。应当按 `const&` 捕获。

!!! pitfall "`catch (const std::runtime_error&)` 能接住所有运行期错误"
    `bad_alloc`、`bad_cast`、`bad_optional_access` 都不在 `runtime_error` 一支，`future_error` 甚至在 `logic_error` 一支。需要兜底时捕获 `const std::exception&`。

!!! pitfall "拼接消息本身也可能抛异常"
    `throw std::runtime_error("open " + path + " failed")` 在抛出前要构造两个临时 `string`，异常对象里再保存一份。内存耗尽时，构造消息就可能抛出 `bad_alloc`，掩盖原本的错误。

## 思考题

!!! question "思考题"
    1. `std::system_error` 为什么派生自 `runtime_error`，而不是直接派生自 `exception`？
    2. 自定义异常类 `struct my_error : std::runtime_error { std::string detail; };` 违反标准的要求吗？
    3. `std::logic_error e("x"); std::logic_error f = e;` 之后，`e.what() == f.what()`（比较指针）一定成立吗？

<details markdown="1">
<summary>答案</summary>

1. 系统调用失败是典型的程序范围之外的事件（[[std.exceptions.general]] ¶3），归入 `runtime_error` 一支符合分类模型。这也让原有的 `catch (const std::runtime_error&)` 能接住它，包括 C++11 起改为派生自 `system_error` 的 `ios_base::failure`。
2. 不违反。[[exception#2]] 约束的是标准库的类，不是用户的类。但它违背了这条约束背后的道理：复制 `std::string` 成员可能抛 `bad_alloc`。按值捕获时要用异常对象初始化 handler 的形参（[[except.handle]]），`std::current_exception` 也可能复制它；异常对象初始化完成后、handler 激活前，异常处理机制调用的函数如果以异常退出，就会调用 `std::terminate`（[[except.terminate]]）。用户的异常类最好也只持有复制时不抛异常的数据，例如 `shared_ptr<const string>`，或者把信息放进基类的 `what_arg`。
3. 不一定。标准只要求 `strcmp(e.what(), f.what()) == 0`。在 libc++ 上两个指针恰好相等，因为它们共享同一块存储，但这是实现细节。
</details>
