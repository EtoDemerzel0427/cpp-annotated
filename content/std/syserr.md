---
title: 系统错误支持
summary: <system_error> 的完整设计：error_category（错误"来源"的身份与解释者）、error_code（精确的、平台相关的错误值）、error_condition（可移植的抽象错误状况）、system_error 异常；code 与 condition 的比较如何经由 category 的虚函数双向映射，generic_category 与 system_category 的分工，如何为自己的库定义错误类别，以及格式化、哈希与常见陷阱。
status: done
covers: *
since: c++11
related: diagnostics, errno, std.exceptions, class.compare, over.match.oper, basic.lookup.argdep, unord.hash, format.string
tags: 标准库, error_code, error_condition, error_category, system_error, 错误处理
updated: 2026-10-18
---

操作系统和底层库报告错误的方式五花八门：POSIX 用 `errno`，Windows 用 `GetLastError()` 和 `HRESULT`，`getaddrinfo` 有自己的 `EAI_*`，数据库驱动、压缩库、HTTP 客户端各有各的整数错误码。一个光秃秃的 `int` 是**有歧义的**：`2` 在 POSIX 上是 `ENOENT`，在 Windows 上是 `ERROR_FILE_NOT_FOUND`（恰好意思相近），在某个 HTTP 库里可能是"连接被重置"。

[syserr] 的解决方案可以用一句话概括：**错误 = （整数值，类别）**。类别是一个多态的单例对象，它的**身份**（地址）区分不同的错误来源，它的**虚函数**负责解释这个整数（消息文本）以及把它映射到可移植的错误状况。整个设计由四个类组成：

| 类 | 角色 | 比喻 |
|---|---|---|
| `error_category`（[[g:error-category]]） | 错误的来源/命名空间：身份 + 解释 + 映射 | "这是哪本字典" |
| `error_code`（[[g:error-code]]） | 某次操作实际得到的错误：**精确**、**平台相关** | "字典里的第 2 条" |
| `error_condition`（[[g:error-condition]]） | 调用者关心的错误**状况**：**抽象**、**可移植** | "所有表示'文件不存在'的条目" |
| `system_error` | 携带 `error_code` 的异常 | "装着上面那张纸条的信封" |

[syserr.general] ¶1：这些组件供标准库和 C++ 程序报告**源自操作系统或其他底层应用程序接口**的错误状况。

## 不碰别人的错误状态（[syserr.general] ¶2）

¶2：[syserr] 中描述的组件**不改变 `errno` 的值**（[[errno]]）。*Recommended practice*：实现应当保持其他库提供的错误状态不变。

这条看似琐碎，实则必要：典型用法是"系统调用失败 → 读 `errno` → 构造 `error_code`/`system_error`"，如果构造过程（例如 `message()` 里调用 `strerror`）改写了 `errno`，或者 Windows 上改写了 `GetLastError()`，就会破坏调用者可能还要做的检查。

## 头文件概要（[system.error.syn]）

概要的主要内容：

- 四个类的声明，以及 `generic_category()`、`system_category()`；
- 两个特征模板 `is_error_code_enum<T>`、`is_error_condition_enum<T>`（默认为 `false_type`）及其 `_v` 变量模板；
- `enum class errc`（**freestanding**）：为每个 POSIX 错误号起一个可读的名字，例如 `errc::no_such_file_or_directory // ENOENT`；并有 `is_error_condition_enum<errc> : true_type`；
- `make_error_code(errc)`、`make_error_condition(errc)`；
- `error_code` 的 `operator<<`；
- 比较运算符：`error_code == error_code`、`error_code == error_condition`、`error_condition == error_condition`，以及两个 `<=>`；
- `hash<error_code>`、`hash<error_condition>`；
- `formatter<error_code, charT>`。

¶1：`errc` 每个枚举项的值与概要中所示 `<cerrno>` 宏的值相同。`<system_error>` 是否暴露 `<cerrno>` 的宏是未指明的——要用 `ENOENT` 就自己包含 `<cerrno>`。

¶2：`is_error_code_enum` 与 `is_error_condition_enum` 可以为**程序定义的类型**特化，表示这些类型可以隐式转换为 `error_code` / `error_condition`。

!!! pitfall "`errc` 是 condition 枚举，不是 code 枚举"
    标准只特化了 `is_error_condition_enum<errc>`。所以 `std::error_condition c = std::errc::invalid_argument;` 可以，而 `std::error_code ec = std::errc::invalid_argument;` **非良构**（Clang："no viable conversion from 'std::errc' to 'std::error_code'"）——必须写 `std::make_error_code(std::errc::invalid_argument)`。这是设计意图的直接体现：`errc` 表示的是**可移植的状况**，是用来**比较**的（`ec == std::errc::invalid_argument`），而不是用来充当具体错误值的。

## `error_category`（[syserr.errcat]）

### 概述（[syserr.errcat.overview]）

¶1：`error_category` 是一个**基类**，用于标识某一类错误码的**来源和编码**。可以派生它来支持标准之外的错误类别，派生类必须按 [syserr.errcat] 的规定行为。

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

设计要点：

- **不可复制**：类别是单例，按引用传递，`error_code` 里存的是指向它的指针。
- **身份即地址**：注 1 指出，类别对象按引用传递，两个类别对象相等**当且仅当地址相同**；如果某个自定义类别类型有多个对象，即使它们"值相同"，比较也可能为假。
- **`constexpr` 默认构造函数**：使派生类的类别对象可以被常量初始化，从而避免静态初始化顺序问题。
- 两个纯虚函数：`name()`（类别名）和 `message(int)`（把值翻译成文本）；其余三个虚函数有默认实现，负责与 `error_condition` 的映射。

### 虚成员的默认行为（[syserr.errcat.virtuals]）

| 函数 | 默认返回 | 段落 |
|---|---|---|
| `name()` | 纯虚；应返回普通字面量编码的类别名字符串 | ¶1 |
| `default_error_condition(ev)` | `error_condition(ev, *this)`——同值、同类别 | ¶2 |
| `equivalent(int code, const error_condition& cond)` | `default_error_condition(code) == cond` | ¶3 |
| `equivalent(const error_code& code, int cond)` | `*this == code.category() && code.value() == cond` | ¶4 |
| `message(ev)` | 纯虚；返回描述 `ev` 的多字节字符串 | ¶5 |

两个 `equivalent` 的方向要看清：

- `equivalent(int code, const error_condition&)` 由 **code 所属的类别**调用：问"我这个类别里的 `code`，是否属于那个状况？"
- `equivalent(const error_code&, int condition)` 由 **condition 所属的类别**调用：问"那个 error_code，是否属于我这个类别里的状况 `condition`？"

这就是整个设计的关键：**code 与 condition 的等价关系可以由任意一方的类别来认定**——下面的比较运算符会两边都问一遍。

### 非虚成员（[syserr.errcat.nonvirtuals]）

¶1：`operator==` 返回 `this == &rhs`。¶2：`operator<=>` 返回 `compare_three_way()(this, &rhs)`；注 1：`compare_three_way` 对指针提供**全序**（即便指针指向无关对象，[[comparisons.three.way]]），所以类别可以排序——但顺序取决于对象的地址，**每次运行可能不同**。

### 程序定义的派生类（[syserr.errcat.derived]）

当你派生自己的类别时，¶1–¶4 规定了重写版本的契约（比基类的默认实现宽松，允许自定义映射）：

- ¶1 `name()`：返回命名该类别的字符串；
- ¶2 `default_error_condition(ev)`：返回与 `ev` **对应**的 `error_condition`；
- ¶3 `equivalent(int code, const error_condition& cond)`：若在本类别中 `code` 被认为与 `cond` 等价则返回 `true`；
- ¶4 `equivalent(const error_code& code, int cond)`：若在本类别中 `code` 被认为与 `cond` 等价则返回 `true`。

### 两个标准类别（[syserr.errcat.objects]）

**`generic_category()`**（¶1–¶2）：返回一个派生自 `error_category` 的对象的引用，所有调用返回**同一个对象**；它的 `default_error_condition` 与 `equivalent` 按基类的规定行为，`name()` 返回 `"generic"`。它对应的是 **POSIX `errno` 值**——`errc` 的值就在这个类别里解释。

**`system_category()`**（¶3–¶4）：同样是单例，`name()` 返回 `"system"`，`equivalent` 按基类行为。它代表**操作系统原生**的错误码。它的 `default_error_condition` 有特殊规定：

- `ev == 0`：返回 `error_condition(0, generic_category())`；
- 若 `ev` 对应某个 POSIX `errno` 值 `pxv`：返回 `error_condition(pxv, generic_category())`；
- 否则：返回 `error_condition(ev, system_category())`。

"对应"在给定操作系统上意味着什么是**未指明的**。注 1：可能的系统错误码数量庞大且无界，有些可能不对应任何 POSIX `errno` 值，因此实现在决定对应关系时有很大余地。

这就是 `system_category` 存在的意义：在 POSIX 系统上，系统错误码**就是** `errno` 值，映射是恒等的；在 Windows 上，`system_category` 的值是 `GetLastError()` 返回的 Win32 错误码，`default_error_condition` 把 `ERROR_FILE_NOT_FOUND` 等映射到 `errc::no_such_file_or_directory`，从而让 `ec == std::errc::no_such_file_or_directory` 在两个平台上都成立。

## `error_code`（[syserr.errcode]）

### 概述（[syserr.errcode.overview]）

¶1：`error_code` 描述一个用来保存错误码值的对象，例如源自操作系统或其他底层 API 的错误码。注 1：`error_code` 是**对异常错误报告的补充**——它不是要取代异常，而是给"不想/不能抛异常"的接口一个报告渠道。

它的数据就是两个说明专用成员：`int val_;` 和 `const error_category* cat_;`——一个整数加一个指针，可以廉价地按值传递、复制、存储。

### 构造与修改（[syserr.errcode.constructors]、[syserr.errcode.modifiers]）

| 操作 | 效果 | 段落 |
|---|---|---|
| `error_code()` | `val_ = 0`，`cat_ = &system_category()` | 构造 ¶1 |
| `error_code(int val, const error_category& cat)` | 直接保存 | 构造 ¶2 |
| `template<class E> error_code(E e)` | *Constraints*：`is_error_code_enum_v<E>`；效果：`error_code ec = make_error_code(e); assign(ec.value(), ec.category());` | 构造 ¶3–¶4 |
| `assign(val, cat)` | 后置条件 `val_ == val && cat_ == &cat` | 修改 ¶1 |
| `operator=(E e)` | 同上的枚举转换，*Constraints* 相同 | 修改 ¶2–¶4 |
| `clear()` | 后置条件 `value() == 0 && category() == system_category()` | 修改 ¶5 |

枚举构造函数里的 `make_error_code(e)` 是**无限定**调用，通过**实参依赖查找**（[[basic.lookup.argdep]]）在枚举 `E` 的命名空间里找到用户提供的 `make_error_code`。这就是扩展点：为自己的枚举特化 `is_error_code_enum`，并在枚举所在命名空间提供 `make_error_code`，`error_code ec = my_errc::timeout;` 就能工作。

*Constraints* 意味着不满足时该构造函数**不参与重载决议**（[[structure.specifications]]），所以 `error_code ec = 42;` 不会意外地匹配模板构造函数。

### 观察者（[syserr.errcode.observers]）

- ¶1 `value()`、¶2 `category()`：返回两个成员；
- ¶3 `default_error_condition()`：`category().default_error_condition(value())`；
- ¶4 `message()`：`category().message(value())`——注意它**不是** `noexcept`，可能分配内存并抛 `bad_alloc`；
- ¶5 `explicit operator bool()`：`value() != 0`。

!!! pitfall "“0 表示成功”是硬编码的"
    `if (ec)` 判断的是 `value() != 0`，**与类别无关**。如果你为某个"0 表示错误"的底层库定义类别（例如 HTTP 状态码里没有 0，但某些库用 0 表示"未知错误"），就必须在映射时避开 0。整个 `<system_error>` 的约定是：值 0 在任何类别中都表示"没有错误"。

### 非成员函数（[syserr.errcode.nonmembers]）

- ¶1 `make_error_code(errc e)`：返回 `error_code(static_cast<int>(e), generic_category())`；
- ¶2 `operator<<`：等价于 `os << ec.category().name() << ':' << ec.value()`——输出 `system:2` 这样的形式，**不是**消息文本。

### 格式化（[syserr.fmt]）

```cpp
template<class charT>
struct formatter<error_code, charT> {
  constexpr void set_debug_format();
  constexpr typename basic_format_parse_context<charT>::iterator
    parse(basic_format_parse_context<charT>& ctx);
  template<class Out>
    typename basic_format_context<Out, charT>::iterator
      format(const error_code& ec, basic_format_context<Out, charT>& ctx) const;
};
```

格式说明的文法是 *error-code-format-spec*：*fill-and-align*ₒₚₜ *width*ₒₚₜ `?`ₒₚₜ `s`ₒₚₜ（¶3）。`format`（¶5）的语义：

- **用了 `s` 选项**：输出 `ec.message()`。¶5.1：若 `charT` 是 `char` 且普通字面量编码为 UTF-8，消息被转码为 UTF-8，非法子序列用 U+FFFD 替换；¶5.2：否则转码为**由实现定义**的编码。
- **未用 `s`**：输出 `format("{}:{}", ec.category().name(), ec.value())`，与 `operator<<` 一致。
- **用了 `?`**：把结果按**转义字符串**格式化（[[format.string.escaped]]）。¶2：`set_debug_format()` 使 formatter 如同解析到了 `?`——这是让 `error_code` 作为容器元素时（`format("{}", vector<error_code>{...})`）能以调试形式输出的钩子。

所以 `std::format("{}", ec)` 得到 `"system:2"`，`std::format("{:s}", ec)` 得到 `"No such file or directory"`。

!!! warning "实现状况"
    这个 formatter 是 C++23 之后加入草案的。截至本文编写时，Clang 23 + libc++ 尚未提供它：`std::format("{}", std::error_code())` 报错，指出 `formatter<std::error_code, char>` 的默认构造函数被隐式删除（即没有可用的特化）。

## `error_condition`（[syserr.errcondition]）

¶1：`error_condition` 描述一个用来保存**标识错误状况**的值的对象。注 1：

!!! std
    error_condition values are portable abstractions, while error_code values are implementation specific.

    `error_condition` 的值是**可移植的抽象**，而 `error_code` 的值是**实现特定的**。

它的接口与 `error_code` 几乎平行（同样是 `val_` + `cat_`），区别只在：

- 默认构造（[syserr.errcondition.constructors] ¶1）与 `clear()`（modifiers ¶5）使用 **`generic_category()`**，而不是 `system_category()`；
- 枚举构造函数的约束是 `is_error_condition_enum_v`，经 ADL 调用 `make_error_condition`（constructors ¶3–¶4，modifiers ¶2–¶4）；
- **没有** `default_error_condition()`——它本身就是 condition；
- observers ¶1–¶4：`value()`、`category()`、`message()`、`explicit operator bool`（`value() != 0`）；
- nonmembers ¶1：`make_error_condition(errc e)` 返回 `error_condition(static_cast<int>(e), generic_category())`；
- **没有** `operator<<` 和 formatter。

## 比较（[syserr.compare]）

这是整个设计的心脏：

| 比较 | 返回 | 段落 |
|---|---|---|
| `error_code == error_code` | `lhs.category() == rhs.category() && lhs.value() == rhs.value()` | ¶1 |
| `error_code == error_condition` | `lhs.category().equivalent(lhs.value(), rhs) \|\| rhs.category().equivalent(lhs, rhs.value())` | ¶2 |
| `error_condition == error_condition` | 类别与值都相同 | ¶3 |
| `error_code <=> error_code` | 先比类别（地址序），再比值 | ¶4 |
| `error_condition <=> error_condition` | 同上 | ¶5 |

**同类比较是精确的**：两个 `error_code` 只有在类别和值都相同时才相等。`error_code(ENOENT, system_category())` 与 `error_code(ENOENT, generic_category())` **不相等**——尽管在 POSIX 上它们表示同一件事。

**跨类比较是语义的**：`error_code == error_condition` 依次询问 code 的类别"你认为这个 code 属于那个 condition 吗"，再询问 condition 的类别"你认为那个 code 属于你的这个 condition 吗"，任一方认可即相等。

默认实现下，第一问是 `code类别.default_error_condition(code) == condition`。对于 `system_category`，`default_error_condition` 把能对应上的值映射到 `generic_category`，于是：

```cpp run title="code-vs-condition.cpp" ok
#include <cerrno>
#include <cstdio>
#include <iostream>
#include <system_error>

int main() {
    std::error_code ec(ENOENT, std::system_category());                       // 操作系统报告的
    std::error_code gc = std::make_error_code(std::errc::no_such_file_or_directory);

    std::printf("%d\n", ec == std::errc::no_such_file_or_directory);   // 1：code vs condition，语义比较
    std::printf("%d\n", std::errc::no_such_file_or_directory == ec);   // 1：C++20 重写候选
    std::printf("%d\n", ec == gc);                                     // 0：code vs code，精确比较
    std::cout << ec << " | " << ec.message() << " | " << gc << '\n';   // system:2 | No such file or directory | generic:2

    auto cond = ec.default_error_condition();
    std::printf("%s:%d\n", cond.category().name(), cond.value());      // generic:2
    std::error_code big(100000, std::system_category());               // 对应不上任何 errno
    auto c2 = big.default_error_condition();
    std::printf("%s:%d\n", c2.category().name(), c2.value());          // system:100000
}
```

（`ec == std::errc::...` 中，`errc` 经 `error_condition` 的枚举构造函数隐式转换，选中 `error_code == error_condition`。）

!!! note "C++20 之后只剩三个 `==`"
    C++17 及以前，概要中还有 `error_condition == error_code` 以及全部 `!=`、`<`。C++20 起，`!=` 与反向的 `==` 都由重写候选（[[over.match.oper]]）自动提供，`<` 等由 `<=>` 提供，所以概要只保留了三个 `==` 和两个 `<=>`。注意 `error_code` 与 `error_condition` 之间**没有** `<=>`——跨类的"等价"不是同一个值域里的比较，没有序可言。libc++ 在 `-std=c++17` 及以下仍保留旧的运算符。

### 最佳实践：用 code 存储，用 condition 比较

把以上规则合起来就是 `<system_error>` 的使用纪律：

- **传递和存储**用 `error_code`：它保留了最精确的信息（原始值和来源），日志里能打印出 `system:10054` 这样可供排查的东西；
- **判断"是不是某种错误"**时，与 `error_condition`（通常是 `errc` 枚举项）比较：`if (ec == std::errc::timed_out)`。这在 POSIX 和 Windows 上都能工作；
- **不要**与 `make_error_code(errc::...)` 比较——那是 code 与 code 的精确比较，只有当对方恰好也在 `generic_category` 中时才相等。

## 定义自己的错误类别

一个完整的例子：某 HTTP 客户端库有自己的错误码（code），应用层关心"能否重试"（condition）。

```cpp run title="custom-category.cpp" ok
#include <cstdio>
#include <string>
#include <system_error>

// 1) 库自己的错误码：具体、实现相关
enum class http_errc { ok = 0, not_found = 404, timeout = 408, server_down = 503 };
// 2) 应用关心的错误状况：抽象、可移植
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
  // code → condition 的映射写在 code 一侧
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
  std::error_code ec = http_errc::timeout;          // 经 ADL 找到 make_error_code
  std::printf("%s\n", ec.message().c_str());                      // HTTP 408
  std::printf("retryable? %d\n", ec == app_cond::retryable);      // 1
  std::printf("permanent? %d\n", ec == app_cond::permanent);      // 0
  std::printf("timed_out? %d\n", ec == std::errc::timed_out);     // 1
  std::printf("same code? %d\n", ec == std::error_code(408, std::generic_category()));  // 0
}
```

要点：

- 类别对象用函数局部静态变量实现单例（C++11 起线程安全初始化）；也可以用 `constexpr` 构造的全局对象（`error_category` 的默认构造函数是 `constexpr`）。
- `make_error_code`/`make_error_condition` 放在**枚举所在的命名空间**，供 ADL 找到。
- 映射逻辑可以放在 code 的类别（重写 `equivalent(int, const error_condition&)` 或 `default_error_condition`），也可以放在 condition 的类别（重写 `equivalent(const error_code&, int)`）。前者适合"库知道自己的错误属于哪些通用状况"；后者适合"应用定义的状况想要认领来自若干个库的错误码"——无需修改那些库。

## 哈希（[syserr.hash]）

¶1：`hash<error_code>` 与 `hash<error_condition>` 是**启用的**（[[unord.hash]]），可以作为无序容器的键。

!!! impl "libc++ 的哈希只看值"
    libc++ 中两个特化的 `operator()` 都只是 `static_cast<size_t>(value())`，**不混入类别**。于是 `error_code(2, system_category())` 与 `error_code(2, generic_category())` 哈希值相同而不相等——这是允许的（哈希只需相等则同值），但大量来自不同类别、值相同的错误码会落进同一个桶。

## `system_error`（[syserr.syserr]）

¶1：`system_error` 描述一个**携带关联错误码**的异常对象，用来报告这样的错误状况——它们通常源自操作系统或其他底层 API。¶2 注 1：如果错误表示内存不足，鼓励实现抛 `bad_alloc` 而不是 `system_error`。

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

[syserr.syserr.members]：

- ¶1–¶6：六个构造函数的后置条件：`code() == ec`（或 `error_code(ev, ecat)`）；带 `what_arg` 的版本还要求 `string_view(what()).find(what_arg) != npos`——**`what()` 包含 `what_arg`，但不必等于它**；
- ¶7：`code()` 返回构造时给出的错误码；
- ¶8：`what()` 返回一个融合了构造实参的 NTBS。注 1：返回的字符串**可能**是 `what_arg + ": " + code.message()`。

注意与 [[std.exceptions]] 中九个类的区别：那些类要求 `what()` 与 `what_arg` **相等**，`system_error` 只要求**包含**，以便实现把错误码的消息追加进去。

```cpp run title="system-error.cpp" ok
#include <cerrno>
#include <cstdio>
#include <stdexcept>
#include <system_error>

int main() {
    try {
        throw std::system_error(ENOENT, std::system_category(), "open config");
    } catch (const std::runtime_error& e) {      // system_error 属于 runtime_error 分支
        std::printf("what(): %s\n", e.what());   // libc++：open config: No such file or directory
        if (auto* se = dynamic_cast<const std::system_error*>(&e))
            std::printf("is ENOENT: %d\n", se->code() == std::errc::no_such_file_or_directory);
    }
}
```

`system_error` 的派生类包括 `ios_base::failure` 和 `filesystem::filesystem_error`；`std::thread`、`std::mutex` 等在系统资源不可用时也抛 `system_error`。

## 实现细节（libc++）

!!! impl
    - `<__system_error/error_category.h>`：`error_category` 的默认构造函数是 `= default` 且 `constexpr`（C++14 起）；`operator==` 就是 `this == &rhs`；`operator<=>` 用 `compare_three_way()(this, std::addressof(rhs))`。
    - `generic_category()`/`system_category()` 在共享库 `libc++.dylib` 中定义，返回库内的单例，因此在同一进程内的所有模块中地址唯一。
    - 本机 macOS 上，`system_category().default_error_condition(ev)` 对 POSIX 范围内的值映射到 `generic_category`，超出范围（如 100000）则保留在 `system_category`——与标准 ¶4 的三分支一致。
    - `system_error::what()` 的格式是 `what_arg + ": " + message()`，与注 1 给出的示例一致。

## 陷阱

!!! pitfall "多个类别对象 = 比较失效"
    类别的身份是地址。把类别对象定义在头文件里的 `inline` 函数局部静态变量中，在 Windows DLL 或带 `-fvisibility=hidden` 的共享库之间，可能每个模块各有一份——于是来自两个模块的 `error_code` 即使"同类别同值"也比较为不等，`equivalent` 映射也会失效。类别单例应当在一个共享库中**定义且导出**。

!!! pitfall "`errno` 值应该放进哪个类别"
    `errno` 的值属于 `generic_category`（这是 `errc`/`make_error_code` 使用的类别）；操作系统 API 直接返回的原生错误码属于 `system_category`。在 POSIX 上二者数值相同，混用通常"碰巧能用"，但在 Windows 上 `errno` 值和 Win32 错误码是两套完全不同的编号。

!!! pitfall "`message()` 会抛异常"
    `message()` 返回 `std::string`，可能抛 `bad_alloc`；某些实现中还会调用 `strerror` 一类的函数。在 `noexcept` 析构函数或错误恢复路径中调用它要小心。

## 思考题

!!! question "思考题"
    1. 两个 `error_condition`：`std::errc::timed_out` 与 `app_cond::retryable`（上例）。一个 `error_code` 可能同时等于两者吗？这与"`==` 是等价关系"矛盾吗？
    2. 为什么 `error_code` 的默认类别是 `system_category()`，而 `error_condition` 的默认类别是 `generic_category()`？
    3. 若 `cat_a.equivalent(code, cond)` 返回 `true` 而 `cat_b.equivalent(ec, cond_value)` 返回 `false`，`ec == cond` 的结果是什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

1. 可能，上例中 `http_errc::timeout` 就同时等于二者。这并不矛盾：`error_code == error_condition` 是两个**不同类型**之间的"属于"关系（类似元素与集合），不是同一类型上的等价关系。`error_code` 与 `error_condition` 之间也没有公共类型，不满足 `equality_comparable_with`（[[concepts.compare]]），标准也从未声称它满足。
2. 默认构造的对象表示"无错误"（值为 0）。`error_code` 用来存放**实际**发生的错误，最常见的来源是操作系统，故默认为 `system_category`；`error_condition` 用来表示**可移植的状况**，可移植状况的标准词汇是 `errc`，它在 `generic_category` 中解释，故默认为 `generic_category`。两者值为 0 时都"不是错误"，类别差异基本只在打印时可见。
3. `true`。¶2 的比较是两次询问的**逻辑或**：任一方类别认可即视为等价。
</details>

## 小结

!!! summary
    - 错误 = （`int` 值，类别指针）；类别是不可复制的单例，**身份即地址**。
    - `error_code`：精确、平台相关，用于存储与传递；默认 `(0, system_category())`；`if (ec)` 即 `value() != 0`。
    - `error_condition`：抽象、可移植，用于判断"是哪种错误"；默认 `(0, generic_category())`；`errc` 是 condition 枚举。
    - 比较：code==code、cond==cond 精确；code==cond 经两方类别的 `equivalent` 语义判断。**用 code 存储，用 condition 比较。**
    - `generic_category` 解释 POSIX `errno` 值；`system_category` 解释操作系统原生码，并把能对应的映射到 generic。
    - 自定义：特化 `is_error_code_enum`/`is_error_condition_enum`，在枚举的命名空间提供 `make_error_code`/`make_error_condition`，派生 `error_category` 并按需重写 `equivalent`/`default_error_condition`。
    - `system_error` 派生自 `runtime_error`，`what()` **包含**（不必等于）`what_arg`。
