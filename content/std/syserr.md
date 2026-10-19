---
title: 系统错误支持
summary: <system_error> 把整数错误码和它的来源（错误类别）放在一起：error_code 保存精确的平台错误，error_condition 表示可移植的错误状况，两者经由类别的虚函数比较；以及如何定义自己的错误类别和 system_error 异常。
status: done
covers: *
since: c++11
related: diagnostics, errno, std.exceptions, class.compare, over.match.oper, basic.lookup.argdep, unord.hash, format.string
tags: 标准库, error_code, error_condition, error_category, system_error, 错误处理
updated: 2026-10-19
---

!!! tldr
    - 一个错误由一个整数值和一个错误类别组成。类别是不可复制的单例对象，两个类别相同当且仅当它们是同一个对象。
    - `error_code` 保存某次操作实际得到的错误，精确但与平台相关；`error_condition` 表示调用者关心的一类错误，是可移植的抽象。
    - 两个 `error_code` 只在类别和值都相同时相等；`error_code` 与 `error_condition` 比较时，由双方类别的 `equivalent` 虚函数判断，任一方认可即相等。
    - 用 `error_code` 存储和传递错误，用 `errc` 这样的 condition 判断是哪种错误。
    - 自定义错误码：特化 `is_error_code_enum`，在枚举所在命名空间提供 `make_error_code`，再从 `error_category` 派生一个类别。

操作系统和底层库都用整数报告错误：POSIX 用 `errno`，Windows 用 `GetLastError()`，`getaddrinfo` 有自己的 `EAI_*`，各种第三方库又各有一套。单独一个 `int` 是有歧义的：`2` 在 POSIX 上是 `ENOENT`，在 Windows 上是 `ERROR_FILE_NOT_FOUND`，在某个 HTTP 库里可能是别的意思。

`<system_error>` 的做法是给整数配上它的来源，也就是错误类别。¶1 说这些组件供标准库和 C++ 程序报告来自操作系统或其他底层接口的错误（[syserr.general]）。

## 先看一个例子

```cpp run title="code-vs-condition.cpp" ok
#include <cerrno>
#include <cstdio>
#include <iostream>
#include <system_error>

int main() {
    std::error_code ec(ENOENT, std::system_category());   // 操作系统报告的错误
    std::error_code gc = std::make_error_code(std::errc::no_such_file_or_directory);

    std::printf("%d\n", ec == std::errc::no_such_file_or_directory);   // 1：code 与 condition
    std::printf("%d\n", std::errc::no_such_file_or_directory == ec);   // 1：C++20 反向重写
    std::printf("%d\n", ec == gc);                                     // 0：code 与 code
    std::cout << ec << " | " << ec.message() << " | " << gc << '\n';
    // system:2 | No such file or directory | generic:2

    auto cond = ec.default_error_condition();
    std::printf("%s:%d\n", cond.category().name(), cond.value());      // generic:2
    std::error_code big(100000, std::system_category());               // 不对应任何 errno 值
    auto c2 = big.default_error_condition();
    std::printf("%s:%d\n", c2.category().name(), c2.value());          // system:100000
}
```

`ec` 和 `gc` 的值都是 2，却不相等，因为它们属于不同的类别。`ec` 与 `errc::no_such_file_or_directory` 相等，是因为 `system_category` 认为自己的 2 对应 POSIX 的 `ENOENT`。本页其余部分解释这些结果从何而来。

整个设计由四个类组成：

| 类 | 角色 |
|---|---|
| `error_category`（[[g:error-category]]） | 错误的来源：用对象身份区分来源，用虚函数解释值、映射到可移植的状况 |
| `error_code`（[[g:error-code]]） | 某次操作实际得到的错误，精确、与平台相关 |
| `error_condition`（[[g:error-condition]]） | 调用者关心的错误状况，抽象、可移植 |
| `system_error` | 携带一个 `error_code` 的异常 |

## 错误类别 [syserr.errcat]

### 类别是单例，身份就是地址

```cpp
class error_category {
public:
  constexpr error_category() noexcept;
  virtual ~error_category();
  error_category(const error_category&) = delete;
  error_category& operator=(const error_category&) = delete;
  virtual const char* name() const noexcept = 0;
  virtual error_condition default_error_condition(int ev) const noexcept;
  virtual bool equivalent(int code, const error_condition& condition) const noexcept;
  virtual bool equivalent(const error_code& code, int condition) const noexcept;
  virtual string message(int ev) const = 0;

  bool operator==(const error_category& rhs) const noexcept;
  strong_ordering operator<=>(const error_category& rhs) const noexcept;
};
```

¶1（[syserr.errcat.overview]）`error_category` 是一个基类，用来标识某类错误码的来源和编码。程序可以派生自己的类别，派生类必须按本条款的规定行为。

类别不可复制，总是按引用传递，`error_code` 里存的是指向它的指针。注 1 指出，两个类别对象相等当且仅当地址相同；如果某个自定义类别类型有多个对象，它们之间的比较可能为假。

默认构造函数是 `constexpr` 的，派生类的类别对象因此可以常量初始化，不受静态初始化顺序的影响。

### 虚函数的默认行为 [syserr.errcat.virtuals]

`name()` 和 `message(int)` 是纯虚函数，派生类必须提供：前者返回类别名，后者把值翻译成说明文字。另外三个虚函数有默认实现：

| 函数 | 默认返回 |
|---|---|
| ¶2 `default_error_condition(ev)` | `error_condition(ev, *this)`，同值、同类别 |
| ¶3 `equivalent(int code, const error_condition& cond)` | `default_error_condition(code) == cond` |
| ¶4 `equivalent(const error_code& code, int cond)` | `*this == code.category() && code.value() == cond` |

两个 `equivalent` 的方向不同：

- `equivalent(int code, const error_condition&)` 在 code 所属的类别上调用，问的是：我这个类别里的 `code` 属于那个状况吗？
- `equivalent(const error_code&, int condition)` 在 condition 所属的类别上调用，问的是：那个 `error_code` 属于我这个类别里的状况 `condition` 吗？

code 与 condition 是否等价，可以由任意一方的类别来认定。后面的比较运算符两边都会问。

[syserr.errcat.derived] 的 ¶1–¶4 对派生类重写这些函数的要求比默认实现宽松：`default_error_condition(ev)` 返回与 `ev` 对应的状况，两个 `equivalent` 在本类别认为两者等价时返回 `true`。对应和等价的具体含义由派生类自己决定。

### 类别之间的比较 [syserr.errcat.nonvirtuals]

¶1 `operator==` 返回 `this == &rhs`。¶2 `operator<=>` 返回 `compare_three_way()(this, &rhs)`，`compare_three_way` 对任意指针都给出全序（[[comparisons.three.way]]），所以类别可以排序，但顺序取决于对象的地址，每次运行可能不同。

### 两个标准类别 [syserr.errcat.objects]

¶1–¶2 `generic_category()` 每次调用都返回同一个对象，`name()` 返回 `"generic"`，其余虚函数按基类的默认行为。它解释的是 POSIX `errno` 值，`errc` 的值就在这个类别里解释。

¶3–¶4 `system_category()` 也是单例，`name()` 返回 `"system"`，代表操作系统原生的错误码。它的 `default_error_condition(ev)` 有专门的规定：

- `ev` 为 0 时，返回 `error_condition(0, generic_category())`；
- `ev` 对应某个 POSIX `errno` 值 `pxv` 时，返回 `error_condition(pxv, generic_category())`；
- 否则返回 `error_condition(ev, system_category())`。

在给定操作系统上什么算对应是未指定的。注 1 解释说，系统错误码数量庞大，有些不对应任何 POSIX 值，所以留给实现决定。

这就是 `system_category` 的用处。POSIX 系统上，系统错误码就是 `errno` 值，映射是恒等的；Windows 上，它的值是 `GetLastError()` 返回的 Win32 错误码，`default_error_condition` 把 `ERROR_FILE_NOT_FOUND` 之类映射到 `errc::no_such_file_or_directory`。于是 `ec == std::errc::no_such_file_or_directory` 在两个平台上都成立。上面例子里的 100000 对应不上任何 POSIX 值，所以留在 `system_category` 中。

## `error_code` [syserr.errcode]

¶1（[syserr.errcode.overview]）`error_code` 保存错误码的值，比如来自操作系统的错误码。注 1 说它是对异常报告错误的补充，给不想或不能抛异常的接口一个报告渠道。

它的数据只有两个说明专用的成员 `int val_;` 和 `const error_category* cat_;`，一个整数加一个指针，可以廉价地按值传递和存储。

### 构造与修改

| 操作 | 效果 |
|---|---|
| `error_code()` | 值 0，类别 `system_category()`（构造 ¶1） |
| `error_code(int val, const error_category& cat)` | 直接保存（构造 ¶2） |
| `template<class E> error_code(E e)` | 约束：`is_error_code_enum_v<E>`；效果：`error_code ec = make_error_code(e); assign(ec.value(), ec.category());`（构造 ¶3–¶4） |
| `assign(val, cat)`、`operator=(E e)` | 同上（修改 ¶1–¶4） |
| `clear()` | 值 0，类别 `system_category()`（修改 ¶5） |

枚举构造函数里的 `make_error_code(e)` 是不带限定的调用，会经实参依赖查找（[[basic.lookup.argdep]]）在枚举 `E` 所在的命名空间里找到用户提供的 `make_error_code`。这就是扩展点：为自己的枚举特化 `is_error_code_enum`，在同一命名空间提供 `make_error_code`，`error_code ec = my_errc::timeout;` 就能编译。

*Constraints* 不满足时，这个构造函数不参与重载决议（[[structure.specifications]]），所以 `error_code ec = 42;` 不会匹配到模板构造函数。

!!! pitfall "`errc` 是 condition 枚举，不是 code 枚举"
    标准只特化了 `is_error_condition_enum<errc>`（[[system.error.syn#2]] 允许程序为自己的类型特化这两个模板）。所以 `std::error_condition c = std::errc::invalid_argument;` 可以编译，`std::error_code ec = std::errc::invalid_argument;` 不行，Clang 报 no viable conversion from 'std::errc' to 'std::error_code'。要得到 `error_code`，写 `std::make_error_code(std::errc::invalid_argument)`。`errc` 表示可移植的状况，用来做比较（`ec == std::errc::invalid_argument`），不是用来充当具体错误值的。

### 观察者与非成员函数

- 观察者 ¶1–¶2 `value()`、`category()` 返回两个成员；¶3 `default_error_condition()` 等于 `category().default_error_condition(value())`。
- ¶4 `message()` 等于 `category().message(value())`。它不是 `noexcept` 的，可能分配内存并抛出 `bad_alloc`。
- ¶5 `explicit operator bool()` 返回 `value() != 0`。
- 非成员 ¶1 `make_error_code(errc e)` 返回 `error_code(static_cast<int>(e), generic_category())`。
- 非成员 ¶2 `operator<<` 输出 `类别名:值`，例如 `system:2`，不是说明文字。

`if (ec)` 只看值是否为 0，与类别无关。整个 `<system_error>` 约定：值 0 在任何类别里都表示没有错误。为一个用 0 表示某种错误的底层库定义类别时，映射必须避开 0。

## `error_condition` [syserr.errcondition]

!!! std
    error_condition values are portable abstractions, while error_code values are implementation specific.

¶1 的注 1 说，`error_condition` 的值是可移植的抽象，`error_code` 的值则与实现相关。

它的接口与 `error_code` 几乎一样，同样是一个值加一个类别指针。区别在于：

- 默认构造和 `clear()` 使用 `generic_category()`（构造 ¶1、修改 ¶5），不是 `system_category()`；
- 枚举构造函数的约束是 `is_error_condition_enum_v`，经实参依赖查找调用 `make_error_condition`（构造 ¶3–¶4）；
- 没有 `default_error_condition()`，它本身就是 condition；
- 非成员 ¶1 `make_error_condition(errc e)` 返回 `error_condition(static_cast<int>(e), generic_category())`；
- 没有 `operator<<`，也没有 formatter。

## 比较 [syserr.compare]

| 比较 | 返回 |
|---|---|
| ¶1 `error_code == error_code` | `lhs.category() == rhs.category() && lhs.value() == rhs.value()` |
| ¶2 `error_code == error_condition` | `lhs.category().equivalent(lhs.value(), rhs) \|\| rhs.category().equivalent(lhs, rhs.value())` |
| ¶3 `error_condition == error_condition` | 类别和值都相同 |
| ¶4、¶5 两个 `<=>` | 先比类别（按地址），再比值 |

同类比较是精确的。`error_code(ENOENT, system_category())` 与 `error_code(ENOENT, generic_category())` 不相等，尽管在 POSIX 上它们说的是同一件事。

`error_code` 与 `error_condition` 的比较是语义上的：先问 code 的类别是否认为这个值属于那个状况，再问 condition 的类别是否认领这个 code，任一方回答是即相等。默认实现下第一问就是 `default_error_condition(code) == condition`，而 `system_category` 把能对应上的值映射到 `generic_category`，这就是开头例子中第一行输出 1 的原因。

!!! note "C++20 起概要里只剩三个 `==`"
    C++17 及以前，概要里还有 `error_condition == error_code` 和全部 `!=`、`<`。C++20 起，`!=` 和反向的 `==` 由重写候选自动提供（[[over.match.oper]]），`<` 等由 `<=>` 提供。`error_code` 与 `error_condition` 之间没有 `<=>`：两者之间是属于关系，不在同一个值域里排序。

由此得到 `<system_error>` 的用法：

- 传递和存储用 `error_code`。它保留了原始值和来源，日志里能打印出 `system:10054` 这样可供排查的信息。
- 判断是哪种错误时，与 `error_condition` 比较，通常就是 `errc` 的枚举项：`if (ec == std::errc::timed_out)`。这在 POSIX 和 Windows 上都能工作。
- 不要与 `make_error_code(errc::...)` 比较。那是两个 `error_code` 的精确比较，只有对方恰好也在 `generic_category` 里时才相等。

## 定义自己的错误类别

某个 HTTP 客户端库有自己的错误码，应用层关心的是能不能重试：

```cpp run title="custom-category.cpp" ok
#include <cstdio>
#include <string>
#include <system_error>

// 库自己的错误码：具体、与实现相关
enum class http_errc { ok = 0, not_found = 404, timeout = 408, server_down = 503 };
// 应用关心的错误状况：抽象、可移植
enum class app_cond { ok = 0, retryable = 1, permanent = 2 };

template<> struct std::is_error_code_enum<http_errc> : std::true_type {};
template<> struct std::is_error_condition_enum<app_cond> : std::true_type {};

struct app_category_t final : std::error_category {
  const char* name() const noexcept override { return "app"; }
  std::string message(int c) const override {
    return c == 1 ? "retryable" : c == 2 ? "permanent" : "unknown";
  }
};
const std::error_category& app_category() { static const app_category_t c; return c; }
std::error_condition make_error_condition(app_cond c) { return {static_cast<int>(c), app_category()}; }

struct http_category_t final : std::error_category {
  const char* name() const noexcept override { return "http"; }
  std::string message(int c) const override { return "HTTP " + std::to_string(c); }
  // code 到 condition 的映射写在 code 一侧
  bool equivalent(int code, const std::error_condition& cond) const noexcept override {
    if (cond == app_cond::retryable)  return code == 408 || code == 503;
    if (cond == app_cond::permanent)  return code == 404;
    if (cond == std::errc::timed_out) return code == 408;   // 也能对上 generic 状况
    return default_error_condition(code) == cond;
  }
};
const std::error_category& http_category() { static const http_category_t c; return c; }
std::error_code make_error_code(http_errc e) { return {static_cast<int>(e), http_category()}; }

int main() {
  std::error_code ec = http_errc::timeout;          // 经实参依赖查找找到 make_error_code
  std::printf("%s\n", ec.message().c_str());                      // HTTP 408
  std::printf("retryable? %d\n", ec == app_cond::retryable);      // 1
  std::printf("permanent? %d\n", ec == app_cond::permanent);      // 0
  std::printf("timed_out? %d\n", ec == std::errc::timed_out);     // 1
  std::printf("same code? %d\n", ec == std::error_code(408, std::generic_category()));  // 0
}
```

几点说明：

- 类别对象用函数内的静态变量实现单例，C++11 起它的初始化是线程安全的。也可以用常量初始化的全局对象。
- `make_error_code` 和 `make_error_condition` 要放在枚举所在的命名空间，实参依赖查找才能找到。
- 映射可以写在 code 的类别里（重写 `equivalent(int, const error_condition&)` 或 `default_error_condition`），也可以写在 condition 的类别里（重写 `equivalent(const error_code&, int)`）。前者适合库知道自己的错误属于哪些通用状况；后者适合应用定义一个状况去认领几个库的错误码，不必修改那些库。

## `system_error` [syserr.syserr]

¶1 `system_error` 是携带一个错误码的异常，通常用来报告来自操作系统的错误。¶2 的注 1 建议，表示内存不足的错误应当抛 `bad_alloc` 而不是 `system_error`。

```cpp
class system_error : public runtime_error {
public:
  system_error(error_code ec, const string& what_arg);
  system_error(error_code ec, const char* what_arg);
  system_error(error_code ec);
  system_error(int ev, const error_category& ecat, const string& what_arg);
  system_error(int ev, const error_category& ecat, const char* what_arg);
  system_error(int ev, const error_category& ecat);
  const error_code& code() const noexcept;
  const char* what() const noexcept override;
};
```

[syserr.syserr.members] ¶1–¶6 规定六个构造函数的后置条件：`code()` 等于给定的错误码；带 `what_arg` 的版本还要求 `what()` 包含 `what_arg`，但不必等于它。¶8 说 `what()` 返回一个融合了构造实参的字符串，注 1 举例说它可以是 `what_arg + ": " + code.message()`。

[[std.exceptions]] 里的 `runtime_error` 等类要求 `what()` 与 `what_arg` 相等，`system_error` 只要求包含，以便实现把错误码的说明文字附加上去。

```cpp run title="system-error.cpp" ok
#include <cerrno>
#include <cstdio>
#include <stdexcept>
#include <system_error>

int main() {
    try {
        throw std::system_error(ENOENT, std::system_category(), "open config");
    } catch (const std::runtime_error& e) {      // system_error 派生自 runtime_error
        std::printf("what(): %s\n", e.what());   // libc++：open config: No such file or directory
        if (auto* se = dynamic_cast<const std::system_error*>(&e))
            std::printf("is ENOENT: %d\n", se->code() == std::errc::no_such_file_or_directory);
    }
}
```

`ios_base::failure` 和 `filesystem::filesystem_error` 都派生自 `system_error`；`std::thread`、`std::mutex` 等在系统资源不可用时也抛 `system_error`。

## 格式化与哈希

### formatter [syserr.fmt]

C++23 之后的草案为 `error_code` 加了 `formatter<error_code, charT>`。格式说明是 *fill-and-align*ₒₚₜ *width*ₒₚₜ `?`ₒₚₜ `s`ₒₚₜ（¶3）。按 ¶5：

- 不带 `s` 时输出 `类别名:值`，与 `operator<<` 一致，所以 `std::format("{}", ec)` 得到 `system:2`；
- 带 `s` 时输出 `ec.message()`，`std::format("{:s}", ec)` 得到 `No such file or directory`。如果 `charT` 是 `char` 且普通字面量编码是 UTF-8，消息会转码为 UTF-8，非法的字节序列替换为 U+FFFD；否则转码为由实现定义的编码；
- 带 `?` 时按转义字符串输出（[[format.string.escaped]]）。¶2 的 `set_debug_format()` 起同样的作用，`error_code` 作为容器元素格式化时会用到它。

截至写作时，本机 Clang 23 + libc++ 还没有这个特化：`std::format("{}", std::error_code())` 报错，说 `formatter<std::error_code, char>` 的默认构造函数被隐式删除。

### 哈希 [syserr.hash]

¶1 `hash<error_code>` 与 `hash<error_condition>` 是启用的（[[unord.hash]]），可以作为无序容器的键。

!!! impl "libc++ 的哈希只看值"
    libc++ 中这两个特化只返回 `static_cast<size_t>(value())`，不混入类别。于是 `error_code(2, system_category())` 与 `error_code(2, generic_category())` 哈希值相同而不相等。这是允许的，哈希只要求相等的对象哈希值相同，但值相同、类别不同的大量错误码会落进同一个桶。

## 常见误解

!!! pitfall "每个共享库各有一份类别对象"
    类别的身份是地址。如果类别对象定义在头文件的 inline 函数里，Windows DLL 之间、或者用 `-fvisibility=hidden` 编译的共享库之间可能各有一份。来自两个模块、类别和值都相同的 `error_code` 会比较为不等，`equivalent` 映射也会失效。类别单例应当在一个共享库中定义并导出。

!!! pitfall "把 errno 值放进 system_category"
    `errno` 的值属于 `generic_category`，操作系统 API 直接返回的原生错误码属于 `system_category`。POSIX 上两者数值相同，混用通常碰巧能用；Windows 上 `errno` 值和 Win32 错误码是两套不同的编号。

!!! pitfall "以为 `message()` 不会抛异常"
    `message()` 返回 `std::string`，可能抛出 `bad_alloc`。在 `noexcept` 的析构函数或错误恢复路径里调用它要小心。

<details class="fine" markdown="1"><summary>其余条文</summary>

[syserr.general] ¶2：本条款的组件不改变 `errno` 的值；*Recommended practice* 建议实现也不改动其他库的错误状态（例如 Windows 的 `GetLastError()`）。典型用法是系统调用失败后读 `errno` 再构造 `error_code`，如果构造过程改写了 `errno`，就会破坏调用者随后的检查。

[system.error.syn] ¶1：`errc` 每个枚举项的值与对应的 `<cerrno>` 宏相同；`<system_error>` 是否同时提供这些宏是未指定的，要用 `ENOENT` 就自己包含 `<cerrno>`。`errc` 本身是 freestanding 的。

[syserr.errcat.virtuals] ¶1 要求 `name()` 返回普通字面量编码的字符串；¶5 要求 `message(ev)` 返回执行字符集中的多字节字符串。

</details>

## 思考题

!!! question "思考题 1"
    `std::errc::timed_out` 和上例的 `app_cond::retryable` 是两个不同的 `error_condition`。一个 `error_code` 能同时等于两者吗？这与 `==` 应当是等价关系矛盾吗？

<details markdown="1">
<summary>答案</summary>

能，上例的 `http_errc::timeout` 就同时等于两者。这不矛盾：`error_code == error_condition` 是两个不同类型之间的属于关系，类似元素与集合，不是同一类型上的等价关系。`error_code` 与 `error_condition` 没有公共类型，不满足 `equality_comparable_with`（[[concepts.compare]]），标准也没有声称它满足。
</details>

!!! question "思考题 2"
    为什么 `error_code` 的默认类别是 `system_category()`，而 `error_condition` 的默认类别是 `generic_category()`？

<details markdown="1">
<summary>答案</summary>

默认构造的对象值为 0，表示没有错误。`error_code` 存放实际发生的错误，最常见的来源是操作系统，所以默认用 `system_category`。`error_condition` 表示可移植的状况，可移植状况的标准词汇是 `errc`，它在 `generic_category` 中解释，所以默认用 `generic_category`。值为 0 时两者都不是错误，类别的差别基本只在打印时看得到。
</details>

!!! question "思考题 3"
    如果 code 的类别认为 `ec` 属于 `cond`，而 `cond` 的类别不认为如此，`ec == cond` 的结果是什么？

<details markdown="1">
<summary>答案</summary>

`true`。[[syserr.compare#2]] 的比较是两次询问的逻辑或，任一方认可即相等。
</details>
