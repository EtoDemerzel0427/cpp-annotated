---
title: 错误处理策略
summary: 一个项目怎样报告和处理错误：先区分程序缺陷、可恢复的环境失败和例外情况，再在异常、error_code、std::expected、返回码之间选择，并处理模块边界、-fno-exceptions、错误上下文、nodiscard、断言、标准库加固与契约。
status: draft
order: 125
group: 工程实践
since: c++23
papers: P0323R12, P2505R5, P0881R7, P2900R14, P3471R4
related: except.handle, syserr, expected, fs.err.report, dcl.attr.nodiscard, structure.specifications, basic.contract, stacktrace, topics/exception-safety, toolchain/exception-implementation, history/contracts, topics/undefined-behavior, toolchain/library-boundaries, toolchain/api-design, toolchain/static-analysis
tags: 错误处理, 异常, expected, error_code, 契约, 加固, 工程实践
updated: 2026-10-19
---

!!! tldr
    - 先给错误分类：程序缺陷（违反前置条件）应当尽早终止，可恢复的环境失败（文件不存在、输入格式错）应当报告给调用方，内存耗尽这类例外情况多数程序只能让它传到顶层。
    - 异常、`std::error_code`、`std::expected`、返回码加输出参数四种写法的正常路径代价在本机测不出差别；出错路径上抛出一次异常要几微秒，其余三种只要几纳秒。
    - 风格可以混用，但要在模块边界上转换：内部抛出、对外返回 `expected` 的函数用 `noexcept` 封口；交给 C 代码的回调绝不能让异常穿过 C 的栈帧。
    - `-fno-exceptions` 下标准库的错误照样会发生：头文件里的 `at()`、`value()` 改为直接终止，`operator new` 失败仍然抛出，没人接住就终止。
    - 返回错误的函数要标 `[[nodiscard]]`，libc++ 的 `std::expected` 本身没有标；程序缺陷交给 `assert`、标准库加固或 C++26 契约，不要当作可恢复错误传播。

## 先给错误分类

读一个配置文件 `app.conf`，至少有四种事会出错：

1. 文件不存在，或者没有读权限；
2. 文件里写着 `port=80a`；
3. 代码里某处用 `ports[i]` 访问配置，而 `i` 越界了；
4. 读文件时内存耗尽。

前两种是程序之外的世界不合作。程序本身没有问题，调用方也许能做点什么：换一个路径、用默认配置、提示用户改文件。这类错误叫**可恢复错误**（recoverable error），它们是函数约定的一部分，应当报告给调用方。

第三种不一样。越界说明程序自己的逻辑错了，此时程序状态已经不可信，调用方没法恢复一个它不知道成因的 bug。这类错误叫**程序缺陷**（bug），也叫违反前置条件。合理的反应是尽早发现、尽早停下，而不是把它当成一个值层层返回。

第四种介于两者之间。它不是 bug，但几乎没有调用方能就地处理，通常只能传到顶层，或者直接终止。

标准库自己的规格就按这个思路区分（[[structure.specifications#3]]）：

| 规格元素 | 含义 | 违反或出错时 |
|---|---|---|
| *Preconditions* | 调用方必须保证的条件 | UB（¶3.4） |
| *Hardened preconditions* | 同上，但加固实现会检查 | 加固实现中是契约违反，否则 UB（¶3.5） |
| *Throws* | 函数可能抛出的异常 | 抛出（¶3.11） |
| *Error conditions* | 经 `error_code` 报告的错误 | 设置 `error_code`（¶3.14） |

例如 `vector::operator[]` 的下标越界属于加固前置条件（[[sequence.reqmts#122]]），`vector::at` 的越界则写在 *Throws* 里，抛出 `out_of_range`（[[sequence.reqmts#127]]）。同一个检查，前者把它当作调用方的 bug，后者把它当作调用方想要处理的情况。

<div class="compare" markdown="1">

```cpp
// 外部输入：校验失败是可恢复错误
std::expected<Port, ConfigError>
parse_port(std::string_view text);
```

```cpp
// 内部：调用方保证 v 已经校验过
// 不满足就是 bug
Port::Port(int v);  // 前置条件：
                    // 0 < v && v <= 65535
```

</div>

分类决定了机制。程序缺陷用断言、加固或契约处理，见后文最后一节。下面几节讨论的都是可恢复错误怎样报告。

## 同一个任务，四种写法

任务固定为：读一个文件，按行解析 `key=value`，`host` 是字符串，`port` 是整数。要报告三种错误：打不开文件（带 `errno`），某行没有 `=`，`port` 不是整数，后两种要带行号。

### 异常

```cpp run title="config-exceptions.cpp" ok
#include <algorithm>
#include <cerrno>
#include <charconv>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <system_error>

struct Config { std::string host; int port = 0; };

struct Closer { void operator()(std::FILE* f) const { std::fclose(f); } };
using File = std::unique_ptr<std::FILE, Closer>;

struct ParseError : std::runtime_error {
  int line;
  ParseError(int l, const std::string& msg)
    : std::runtime_error(msg), line(l) {}
};

std::string read_file(const char* path) {
  File f(std::fopen(path, "r"));
  if (!f)
    throw std::system_error(errno, std::generic_category(), path);
  std::string s;
  char buf[4096];
  while (auto n = std::fread(buf, 1, sizeof buf, f.get()))
    s.append(buf, n);
  return s;
}

int to_int(std::string_view s, int line) {
  int v = 0;
  auto [p, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
  if (ec != std::errc{} || p != s.data() + s.size())
    throw ParseError(line, "not an integer: " + std::string(s));
  return v;
}

Config parse_config(std::string_view text) {
  Config c;
  for (int no = 1; !text.empty(); ++no) {
    std::string_view ln = text.substr(0, text.find('\n'));
    text.remove_prefix(std::min(ln.size() + 1, text.size()));
    auto eq = ln.find('=');
    if (eq == ln.npos) throw ParseError(no, "expected key=value");
    auto key = ln.substr(0, eq), val = ln.substr(eq + 1);
    if (key == "host") c.host = val;
    else if (key == "port") c.port = to_int(val, no);
  }
  return c;
}

Config load_config(const char* path) {
  return parse_config(read_file(path));
}

int main() {
  Config c = parse_config("host=example.org\nport=8080\n");
  std::printf("%s:%d\n", c.host.c_str(), c.port);
  try {
    parse_config("host=x\nport=80a\n");
  } catch (const ParseError& e) {
    std::printf("line %d: %s\n", e.line, e.what());
  }
  try {
    load_config("missing.conf");
  } catch (const std::system_error& e) {
    std::printf("%s\n", e.what());
  }
}
```

本机输出：

```text
example.org:8080
line 2: not an integer: 80a
missing.conf: No such file or directory
```

函数签名里只有正常结果，`parse_config` 中间层完全不用管 `to_int` 的失败，错误自动传到最近的 `catch`。错误信息放在异常对象里，`ParseError` 带了行号，`system_error` 带了 `errno`。`read_file` 用 `unique_ptr` 管理 `FILE*`，抛出时栈回溯会关闭文件。这些保证怎样成立见 [[topics/exception-safety]]。

代价是失败不出现在签名里。读 `load_config` 的声明看不出它会抛出什么，只能靠文档。

### `std::expected`

`std::expected<T, E>` 要么持有一个 `T`，要么持有一个 `E`（[[expected]]，{{c++23}}，[[P0323R12]]）。错误成了返回值的一部分：

```cpp run title="config-expected.cpp" ok
#include <algorithm>
#include <cerrno>
#include <charconv>
#include <cstdio>
#include <expected>
#include <memory>
#include <string>
#include <string_view>
#include <system_error>

struct Config { std::string host; int port = 0; };

struct Closer { void operator()(std::FILE* f) const { std::fclose(f); } };
using File = std::unique_ptr<std::FILE, Closer>;

struct ConfigError {
  std::error_code code;   // 哪一类错误
  int line = 0;           // 0 表示与行无关
  std::string detail;
};
template <class T> using Result = std::expected<T, ConfigError>;

Result<std::string> read_file(const char* path) {
  File f(std::fopen(path, "r"));
  if (!f)
    return std::unexpected(ConfigError{
        std::error_code(errno, std::generic_category()), 0, path});
  std::string s;
  char buf[4096];
  while (auto n = std::fread(buf, 1, sizeof buf, f.get()))
    s.append(buf, n);
  return s;
}

Result<int> to_int(std::string_view s, int line) {
  int v = 0;
  auto [p, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
  if (ec != std::errc{} || p != s.data() + s.size())
    return std::unexpected(ConfigError{
        std::make_error_code(std::errc::invalid_argument), line,
        "not an integer: " + std::string(s)});
  return v;
}

Result<Config> parse_config(std::string_view text) {
  Config c;
  for (int no = 1; !text.empty(); ++no) {
    std::string_view ln = text.substr(0, text.find('\n'));
    text.remove_prefix(std::min(ln.size() + 1, text.size()));
    auto eq = ln.find('=');
    if (eq == ln.npos)
      return std::unexpected(ConfigError{
          std::make_error_code(std::errc::invalid_argument), no,
          "expected key=value"});
    auto key = ln.substr(0, eq), val = ln.substr(eq + 1);
    if (key == "host") c.host = val;
    else if (key == "port") {
      auto v = to_int(val, no);
      if (!v) return std::unexpected(std::move(v.error()));
      c.port = *v;
    }
  }
  return c;
}

Result<Config> load_config(const char* path) {
  return read_file(path).and_then(
      [](const std::string& text) { return parse_config(text); });
}

int main() {
  // transform：只在有值时变换值
  auto port = parse_config("host=example.org\nport=8080\n")
                  .transform([](const Config& c) { return c.port; });
  std::printf("port %d\n", *port);

  // or_else：文件不存在时退回默认配置，其他错误原样传出
  auto cfg = load_config("missing.conf").or_else(
      [](const ConfigError& e) -> Result<Config> {
        if (e.code == std::errc::no_such_file_or_directory)
          return Config{"localhost", 80};
        return std::unexpected(e);
      });
  std::printf("%s:%d\n", cfg->host.c_str(), cfg->port);

  // transform_error：在边界上把错误变成一条消息
  auto msg = parse_config("port=80a\n").transform_error(
      [](const ConfigError& e) {
        return "line " + std::to_string(e.line) + ": " + e.detail;
      });
  if (!msg) std::printf("%s\n", msg.error().c_str());
}
```

本机输出：

```text
port 8080
localhost:80
line 1: not an integer: 80a
```

`main` 用到了 C++23 的四个单子操作（[[P2505R5]]，[[expected.object.monadic]]）：

| 操作 | 有值时 | 有错误时 |
|---|---|---|
| `and_then(f)` | 返回 `f(值)`，`f` 本身返回 `expected` | 原样传出错误 |
| `transform(f)` | 返回装着 `f(值)` 的 `expected` | 原样传出错误 |
| `or_else(f)` | 原样传出值 | 返回 `f(错误)`，`f` 本身返回 `expected` |
| `transform_error(f)` | 原样传出值 | 返回装着 `f(错误)` 的 `expected` |

`load_config` 用 `and_then` 把两步串起来，任何一步失败都会短路。可是在 `parse_config` 的循环里，单子操作用不上，只能手写：

```cpp
auto v = to_int(val, no);
if (!v) return std::unexpected(std::move(v.error()));
c.port = *v;
```

C++ 没有 Rust 的 `?` 运算符，每个可能失败的调用都要这样三行。错误类型 `ConfigError` 可以随意设计，这里放了 `error_code`、行号和描述，比一个整数能带的信息多得多。

`*v` 要求 `v` 有值，这是 `operator*` 的加固前置条件（[[expected.object.obs#3]]）；`v.value()` 在没有值时抛出 `bad_expected_access`（[[expected.object.obs#11]]）。手写的检查之后用 `*v` 即可。

### `std::error_code`

`std::error_code` 只装两样东西：一个 `int` 和一个指向错误类别的指针（[[syserr.errcode.overview]]）。它原本是为了包装操作系统的错误码，标准把它定位为异常报告的补充（[[syserr.errcode.overview#1]] 的注）。`<filesystem>` 的大多数函数都有两个重载，一个抛出 `filesystem_error`，一个多一个 `error_code&` 参数（[[fs.err.report#1]]），下面仿照这种做法：

```cpp run title="config-error-code.cpp" ok
#include <algorithm>
#include <cerrno>
#include <charconv>
#include <cstdio>
#include <memory>
#include <string>
#include <string_view>
#include <system_error>

struct Config { std::string host; int port = 0; };

struct Closer { void operator()(std::FILE* f) const { std::fclose(f); } };
using File = std::unique_ptr<std::FILE, Closer>;

// 1. 本模块自己的错误枚举（0 留给“没有错误”）
enum class config_errc { syntax = 1, not_an_integer };

// 2. 一个错误类别：名字和消息
struct config_category_t : std::error_category {
  const char* name() const noexcept override { return "config"; }
  std::string message(int ev) const override {
    switch (static_cast<config_errc>(ev)) {
      case config_errc::syntax: return "expected key=value";
      case config_errc::not_an_integer: return "not an integer";
    }
    return "unknown config error";
  }
};
const std::error_category& config_category() {
  static const config_category_t cat;
  return cat;
}

// 3. 让 config_errc 能隐式转换成 error_code
std::error_code make_error_code(config_errc e) {
  return {static_cast<int>(e), config_category()};
}
template <>
struct std::is_error_code_enum<config_errc> : std::true_type {};

std::string read_file(const char* path, std::error_code& ec) {
  File f(std::fopen(path, "r"));
  if (!f) { ec.assign(errno, std::generic_category()); return {}; }
  std::string s;
  char buf[4096];
  while (auto n = std::fread(buf, 1, sizeof buf, f.get()))
    s.append(buf, n);
  ec.clear();
  return s;
}

int to_int(std::string_view s, std::error_code& ec) {
  int v = 0;
  auto [p, e] = std::from_chars(s.data(), s.data() + s.size(), v);
  if (e != std::errc{} || p != s.data() + s.size())
    ec = config_errc::not_an_integer;
  return v;
}

// 行号没有地方放，只好再加一个输出参数
Config parse_config(std::string_view text, std::error_code& ec,
                    int& line) {
  Config c;
  ec.clear();
  for (line = 1; !text.empty(); ++line) {
    std::string_view ln = text.substr(0, text.find('\n'));
    text.remove_prefix(std::min(ln.size() + 1, text.size()));
    auto eq = ln.find('=');
    if (eq == ln.npos) { ec = config_errc::syntax; return {}; }
    auto key = ln.substr(0, eq), val = ln.substr(eq + 1);
    if (key == "host") c.host = val;
    else if (key == "port") {
      c.port = to_int(val, ec);
      if (ec) return {};
    }
  }
  line = 0;
  return c;
}

// 抛出版本：包装 error_code 版本，和 <filesystem> 的做法一样
Config parse_config(std::string_view text) {
  std::error_code ec;
  int line;
  Config c = parse_config(text, ec, line);
  if (ec) throw std::system_error(ec, "line " + std::to_string(line));
  return c;
}

int main() {
  std::error_code ec;
  int line;
  Config c = parse_config("host=example.org\nport=8080\n", ec, line);
  std::printf("%s:%d\n", c.host.c_str(), c.port);

  parse_config("port=80a\n", ec, line);
  std::printf("%s:%d at line %d: %s\n", ec.category().name(),
              ec.value(), line, ec.message().c_str());

  read_file("missing.conf", ec);
  if (ec == std::errc::no_such_file_or_directory)   // 可移植的比较
    std::printf("%s: %s\n", ec.category().name(), ec.message().c_str());

  try { parse_config("host\n"); }
  catch (const std::system_error& e) { std::printf("%s\n", e.what()); }
}
```

本机输出：

```text
example.org:8080
config:2 at line 1: not an integer
generic: No such file or directory
line 1: expected key=value
```

自定义错误码要三步：一个枚举，一个从 `std::error_category` 派生的类别，一个 `make_error_code` 加上 `is_error_code_enum` 的特化。有了后两者，`ec = config_errc::syntax` 才能编译（[[syserr.errcode.constructors#3]]）。

`ec == std::errc::no_such_file_or_directory` 比较的是一个 `error_code` 和一个 `error_condition`，结果由类别的 `equivalent` 决定（[[syserr.compare#2]]）。所以不同平台上数值不同的系统错误码，可以和同一个可移植的条件比较。

`error_code` 的问题是带不了上下文。行号没处放，`parse_config` 只好再加一个 `int& line` 参数；如果还想带出错的那段文本，就要再加一个。

!!! pitfall "类别按地址比较"
    两个 `error_category` 对象相等当且仅当地址相同（[[syserr.errcat.overview#1]] 的注）。`config_category()` 里的静态对象如果因为共享库的符号可见性设置而在进程中存在两份，来自两个库的同一个错误码会比较为不相等。这是 [[toolchain/library-boundaries|库边界]] 上要注意的问题之一。

### 返回码加输出参数

C 风格的写法：返回一个状态码，结果和附加信息经指针带回。

```cpp run title="config-return-code.cpp" ok
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>

struct Config { char host[64]; int port; };

enum cfg_status { CFG_OK = 0, CFG_EOPEN, CFG_ESYNTAX, CFG_EINT };

// 返回状态码；结果、出错行号、errno 都经输出参数带回
[[nodiscard]] cfg_status parse_config(const char* text, Config* out,
                                      int* err_line) {
  std::memset(out, 0, sizeof *out);
  for (int no = 1; *text; ++no) {
    const char* end = std::strchr(text, '\n');
    if (!end) end = text + std::strlen(text);
    const char* eq = static_cast<const char*>(
        std::memchr(text, '=', end - text));
    if (!eq) { *err_line = no; return CFG_ESYNTAX; }
    int klen = eq - text, vlen = end - eq - 1;
    if (klen == 4 && std::memcmp(text, "host", 4) == 0) {
      std::snprintf(out->host, sizeof out->host, "%.*s", vlen, eq + 1);
    } else if (klen == 4 && std::memcmp(text, "port", 4) == 0) {
      char* p;
      errno = 0;
      long v = std::strtol(eq + 1, &p, 10);
      if (p != end || p == eq + 1 || errno) {
        *err_line = no;
        return CFG_EINT;
      }
      out->port = static_cast<int>(v);
    }
    text = *end ? end + 1 : end;
  }
  return CFG_OK;
}

[[nodiscard]] cfg_status load_config(const char* path, Config* out,
                                     int* err_line, int* err_no) {
  std::FILE* f = std::fopen(path, "r");
  if (!f) { *err_no = errno; return CFG_EOPEN; }
  char buf[4096];                 // 示意：超过 4 KiB 的部分被截断
  std::size_t n = std::fread(buf, 1, sizeof buf - 1, f);
  std::fclose(f);                 // 每条返回路径都要记得关闭
  buf[n] = '\0';
  return parse_config(buf, out, err_line);
}

int main() {
  Config c;
  int line = 0, err = 0;
  if (parse_config("host=example.org\nport=8080\n", &c, &line) == CFG_OK)
    std::printf("%s:%d\n", c.host, c.port);
  if (parse_config("port=80a\n", &c, &line) == CFG_EINT)
    std::printf("line %d: not an integer\n", line);
  if (load_config("missing.conf", &c, &line, &err) == CFG_EOPEN)
    std::printf("open: %s\n", std::strerror(err));
  load_config("missing.conf", &c, &line, &err);   // warning: 忽略了返回值
}
```

本机输出：

```text
example.org:8080
line 1: not an integer
open: No such file or directory
```

编译时还有一条警告，因为最后一行忽略了 `[[nodiscard]]` 函数的返回值：

```text
config-return-code.cpp:58:3: warning: ignoring return value of function declared with 'nodiscard' attribute [-Wunused-result]
```

这种写法不依赖任何 C++ 运行时设施，能直接导出给 C 和其他语言调用。代价是每条返回路径都要手动释放资源（`fclose` 只能写在 `fread` 之后），状态码和输出参数之间的对应关系全靠约定，调用方忘了检查也能编译通过。

### 并排比较

| | 异常 | `expected` | `error_code` | 返回码 |
|---|---|---|---|---|
| 失败出现在签名里 | 否 | 是 | 是（参数） | 是 |
| 中间层的传播代码 | 无 | 每次调用约三行 | 每次调用一行 `if` | 每次调用一行 `if` |
| 错误能带的上下文 | 任意（异常对象） | 任意（`E`） | 一个整数加类别 | 靠额外输出参数 |
| 调用方能否默默忽略 | 不能，没人接就终止 | 能，除非 `[[nodiscard]]` | 能 | 能，除非 `[[nodiscard]]` |
| `-fno-exceptions` 下可用 | 否 | 是 | 是 | 是 |
| 跨 C 接口 | 否 | 否 | 部分（只传整数） | 是 |

## 代价：本机测量

### 正常路径与出错路径

为了只比较报告机制，下面的基准让四种写法做同样的工作：用 `from_chars` 解析一个整数，错误经过三层非内联调用传回，最外层补上行号。异常版本另有一个不补行号、直接传到 `main` 的变体。

<details class="fine" markdown="1"><summary>基准程序 micro.cpp</summary>

```cpp title="micro.cpp" ok
#include <algorithm>
#include <charconv>
#include <chrono>
#include <cstdio>
#include <expected>
#include <string_view>
#include <system_error>

#define NOINLINE [[gnu::noinline]]
struct Err { int code; int line; };

bool bad_int(std::string_view s, int& v) {
  auto [p, ec] = std::from_chars(s.data(), s.data() + s.size(), v);
  return ec != std::errc{} || p != s.data() + s.size();
}

// 同样的工作：解析一个整数，错误经过三层调用传回，最外层补上行号
namespace exc {
NOINLINE int to_int(std::string_view s) {
  int v;
  if (bad_int(s, v)) throw Err{1, 0};
  return v;
}
NOINLINE int field(std::string_view s) { return to_int(s) + 1; }
NOINLINE int line(std::string_view s, int no) {
  try { return field(s) * 2; }
  catch (Err& e) { e.line = no; throw; }      // 补上行号再抛出
}
NOINLINE int line_plain(std::string_view s, int) {
  return field(s) * 2;                         // 不补行号
}
}  // namespace exc

namespace exp {
using R = std::expected<int, Err>;
NOINLINE R to_int(std::string_view s) {
  int v;
  if (bad_int(s, v)) return std::unexpected(Err{1, 0});
  return v;
}
NOINLINE R field(std::string_view s) {
  return to_int(s).transform([](int v) { return v + 1; });
}
NOINLINE R line(std::string_view s, int no) {
  return field(s)
      .transform([](int v) { return v * 2; })
      .transform_error([no](Err e) { e.line = no; return e; });
}
}  // namespace exp

namespace ec {
NOINLINE int to_int(std::string_view s, std::error_code& ec) {
  int v = 0;
  if (bad_int(s, v)) ec = std::make_error_code(std::errc::invalid_argument);
  return v;
}
NOINLINE int field(std::string_view s, std::error_code& ec) {
  int v = to_int(s, ec);
  return ec ? 0 : v + 1;
}
NOINLINE int line(std::string_view s, int no, std::error_code& ec,
                  int& err_line) {
  int v = field(s, ec);
  if (ec) { err_line = no; return 0; }
  return v * 2;
}
}  // namespace ec

namespace rc {
NOINLINE int to_int(std::string_view s, int* out) {
  return bad_int(s, *out) ? 1 : 0;
}
NOINLINE int field(std::string_view s, int* out) {
  int v;
  if (int r = to_int(s, &v)) return r;
  *out = v + 1;
  return 0;
}
NOINLINE int line(std::string_view s, int no, int* out, int* err_line) {
  int v;
  if (int r = field(s, &v)) { *err_line = no; return r; }
  *out = v * 2;
  return 0;
}
}  // namespace rc

template <class T> void keep(const T& v) { asm volatile("" : : "r"(&v) : "memory"); }

template <class F> double ns_per_call(F f, int n) {
  double best = 1e18;
  for (int rep = 0; rep < 15; ++rep) {      // 取 15 轮中最快的一轮
    auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < n; ++i) f();
    auto t1 = std::chrono::steady_clock::now();
    best = std::min(best,
        std::chrono::duration<double, std::nano>(t1 - t0).count() / n);
  }
  return best;
}

int main() {
  const char* volatile g = "8080";
  const char* volatile b = "80a";
  std::string_view good = g, bad = b;
  constexpr int N = 2'000'000;
  std::printf("%-18s ok %5.1f ns  err %7.1f ns\n", "exception+rethrow",
    ns_per_call([&] { keep(exc::line(good, 2)); }, N),
    ns_per_call([&] {
      try { keep(exc::line(bad, 2)); } catch (const Err& e) { keep(e); }
    }, N / 100));
  std::printf("%-18s ok %5.1f ns  err %7.1f ns\n", "exception",
    ns_per_call([&] { keep(exc::line_plain(good, 2)); }, N),
    ns_per_call([&] {
      try { keep(exc::line_plain(bad, 2)); } catch (const Err& e) { keep(e); }
    }, N / 100));
  std::printf("%-18s ok %5.1f ns  err %7.1f ns\n", "expected",
    ns_per_call([&] { keep(exp::line(good, 2)); }, N),
    ns_per_call([&] { keep(exp::line(bad, 2)); }, N));
  std::printf("%-18s ok %5.1f ns  err %7.1f ns\n", "error_code",
    ns_per_call([&] { std::error_code e; int l = 0;
                      keep(ec::line(good, 2, e, l)); keep(e); }, N),
    ns_per_call([&] { std::error_code e; int l = 0;
                      keep(ec::line(bad, 2, e, l)); keep(e); }, N));
  std::printf("%-18s ok %5.1f ns  err %7.1f ns\n", "return code",
    ns_per_call([&] { int v, l; keep(rc::line(good, 2, &v, &l)); keep(v); }, N),
    ns_per_call([&] { int v, l; keep(rc::line(bad, 2, &v, &l)); keep(l); }, N));
}
```

</details>

用 `clang++ -std=c++2c -O2` 编译，在本机（Apple M2 Pro，libc++abi）运行，每项取 15 轮中最快的一轮。测量时机器负载很高（load average 约 80），下表是两次运行的范围，只应看数量级：

| 写法 | 正常路径 | 出错路径 |
|---|---|---|
| 异常，中途 catch 补行号后重新抛出 | 8.3 ns | 8.5–11 µs |
| 异常，直接传到最外层 | 8.3 ns | 4.2–5.9 µs |
| `expected` | 8.3–9.5 ns | 6.7–9 ns |
| `error_code` | 8.9 ns | 8.0 ns |
| 返回码 | 8.6–8.9 ns | 7.4 ns |

正常路径上四种写法没有可测的差别，时间都花在解析和函数调用上。出错路径上，值传递的三种写法和正常路径一样快；异常慢了大约三个数量级，中途 `catch` 再 `throw;` 相当于又抛出一次，时间翻倍。慢在哪里，见 [[toolchain/exception-implementation]] 的两阶段回溯一节。

这组数字只说明一件事：错误发生的频率决定了异常的代价是否要紧。配置文件一辈子读一次，抛出一次多花几微秒无关紧要；网络服务每秒要拒绝上万个格式错误的请求，就不该用异常报告这种失败。

### 二进制体积

把四个版本的 `main` 去掉，只编译库函数，`clang++ -std=c++2c -O2 -c`，用 `llvm-size -m` 看目标文件各节的字节数：

| 版本 | `__text` | `__gcc_except_tab` | `__compact_unwind` |
|---|---|---|---|
| 异常 | 3032 | 148 | 512 |
| `expected` | 2972 | 148 | 384 |
| `expected`，`-fno-exceptions` | 2564 | 0 | 0 |
| `error_code`（含抛出版本的包装） | 3324 | 108 | 576 |
| 返回码 | 600 | 0 | 64 |
| 返回码，`-fno-exceptions` | 600 | 0 | 0 |

`expected` 版本没有一个 `throw`，却和异常版本一样有异常表。原因是 `std::string` 的分配可能抛出 `bad_alloc`，`unique_ptr` 需要着陆点在回溯时关闭文件。只有加上 `-fno-exceptions`，这些着陆点和表才消失，`__text` 少了约 14%。

返回码版本小了五倍，主要不是因为错误处理方式，而是它根本没用 `std::string`。体积首先取决于用了哪些库设施，错误机制是次要因素。

## 在模块边界上转换风格

一个项目很少只用一种风格：标准库会抛出，操作系统接口返回 `errno`，第三方库各有各的约定。可行的做法是每个模块内部选一种，在边界上统一转换。

### 内部抛出，对外返回 `expected`

假设配置模块内部用异常写成（上面的第一个版本），但它要提供给一个禁用了异常、或者不愿处理异常的调用方。下面的代码接在 `config-exceptions.cpp` 的库函数之后（去掉原来的 `main`，另加 `<expected>` 和 `<new>`）：

```cpp title="boundary.cpp（接在 config-exceptions.cpp 的库函数之后）"
// 模块对外的接口：不抛出，返回 expected
struct LoadError {
  std::error_code code;
  int line = 0;
  std::string message;
};

std::expected<Config, LoadError>
try_load_config(const char* path) noexcept {
  try {
    return load_config(path);
  } catch (const ParseError& e) {
    return std::unexpected(LoadError{
        std::make_error_code(std::errc::invalid_argument), e.line,
        e.what()});
  } catch (const std::system_error& e) {
    return std::unexpected(LoadError{e.code(), 0, e.what()});
  } catch (const std::bad_alloc&) {
    return std::unexpected(LoadError{
        std::make_error_code(std::errc::not_enough_memory), 0, {}});
  }
  // 其他异常：离开 noexcept 函数，std::terminate
}

int main() {
  auto r = try_load_config("missing.conf");
  if (!r) std::printf("%s (%s)\n", r.error().message.c_str(),
                      r.error().code.message().c_str());
}
```

本机输出：

```text
missing.conf: No such file or directory (No such file or directory)
```

`try_load_config` 是边界：它接住本模块会抛出的每一种异常，翻译成 `LoadError`。标了 `noexcept` 之后，漏掉的异常类型不会悄悄穿过边界，而是在离开函数时调用 `std::terminate`（[[except.handle#7]]）。这比让调用方意外收到一个异常更容易发现。

边界的另一侧也一样：用 `expected` 写成的模块要把错误交给抛出异常的代码时，在边界上 `if (!r) throw ...;`，或者调用会抛出 `bad_expected_access` 的 `r.value()`。

### C 接口与回调

C 库调用 C++ 写的回调时，异常绝不能离开回调。下面的 `walk_lines` 是一个 C 函数，逐行调用回调，并在返回前释放自己分配的内存：

```c title="walk.c"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef int (*line_cb)(const char* line, size_t len, void* user);
int walk_lines(const char* text, line_cb cb, void* user) {
  char* copy = strdup(text);          /* C 代码自己的资源 */
  int rc = 0;
  for (char* p = copy; *p && rc == 0;) {
    char* nl = strchr(p, '\n');
    size_t len = nl ? (size_t)(nl - p) : strlen(p);
    rc = cb(p, len, user);
    p += len + (nl != NULL);
  }
  free(copy);
  fprintf(stderr, "walk_lines: freed\n");
  return rc;
}
```

如果回调直接抛出，异常要穿过 `walk_lines` 的栈帧。C 编译器不为 C 代码生成着陆点，`free(copy)` 不会执行。本机用 `clang -c -O2 walk.c` 编译 C 部分、让回调抛出 `runtime_error` 做实验：外面的 `catch` 接住了异常（macOS 上 C 代码默认也有回溯信息），但 `walk_lines: freed` 一行没有打印，内存泄漏了。在没有回溯信息的平台或编译选项下，结果可能是直接终止。标准管不到 C 翻译单元，这种行为没有任何保证。

正确的做法是在回调里接住一切，把异常存进 `std::exception_ptr`，让 C 代码正常返回，回到 C++ 之后再抛出：

```cpp title="callback.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <string>
#include <string_view>

extern "C" {
typedef int (*line_cb)(const char* line, std::size_t len, void* user);
int walk_lines(const char* text, line_cb cb, void* user);
}

struct Collector {
  int count = 0;
  std::exception_ptr error;
  void feed(std::string_view ln) {
    if (ln.find('=') == ln.npos)
      throw std::runtime_error("bad line: " + std::string(ln));
    ++count;
  }
};

// 回调的边界：异常不越过 C 帧，先存起来
extern "C" int on_line(const char* p, std::size_t n, void* user) noexcept {
  auto* self = static_cast<Collector*>(user);
  try {
    self->feed({p, n});
    return 0;
  } catch (...) {
    self->error = std::current_exception();
    return -1;                      // 让 C 代码正常返回、释放资源
  }
}

int count_entries(const char* text) {
  Collector c;
  walk_lines(text, on_line, &c);
  if (c.error) std::rethrow_exception(c.error);   // 回到 C++ 再抛出
  return c.count;
}

int main() {
  std::printf("%d\n", count_entries("a=1\nb=2\n"));
  try { count_entries("a=1\noops\n"); }
  catch (const std::exception& e) { std::printf("%s\n", e.what()); }
}
```

与 `walk.c` 一起编译，在终端中运行，本机输出（`freed` 两行来自标准错误）：

```text
walk_lines: freed
2
walk_lines: freed
bad line: oops
```

两次调用里 C 代码都释放了内存。`std::current_exception` 拿到当前处理的异常（[[propagation#9]]），`std::rethrow_exception` 再把它抛出（[[propagation#11]]），类型和内容都保留下来。

回调本身标了 `noexcept`，这样即使 `catch (...)` 里的代码再抛出，也会在回调的边界上终止，不会进入 C 的栈帧。如果回调类型由 C++ 一侧定义，还可以把 `noexcept` 写进函数指针类型。`noexcept` 是函数类型的一部分，潜在抛出的函数不能转换成指向 `noexcept` 函数的指针（[[conv.fctptr#1]] 只允许反方向的转换）：

```cpp run title="noexcept-callback.cpp" error
#include <cstddef>
using line_cb = int (*)(const char*, std::size_t, void*) noexcept;
void subscribe(line_cb cb);

int may_throw(const char*, std::size_t, void*);
int wont_throw(const char*, std::size_t, void*) noexcept;

void setup() {
  subscribe(wont_throw);    // OK
  subscribe(may_throw);     // error: 不能转换成 noexcept 函数指针
  subscribe([](const char*, std::size_t, void*) noexcept {
    return 0;
  });                       // OK
}
```

本机 Clang 23 报告 `no known conversion from 'int (const char *, std::size_t, void *)' ... to 'line_cb'`。忘了处理异常的回调在编译期就被拦下。

同样的道理适用于线程入口函数、析构函数、`atexit` 注册的函数：异常从这些地方逃出都会调用 `std::terminate`（[[except.terminate#1]] 的注列出了全部情形）。

## `-fno-exceptions` 的代码库

许多代码库用 `-fno-exceptions` 编译，这是 GCC 和 Clang 提供的一种不符合标准的方言：`throw` 和 `try` 不能编译，编译器不生成着陆点。代码生成层面的影响见 [[toolchain/exception-implementation]]。这里关心的是另一面：标准库的错误报告在这种模式下变成了什么。

```cpp title="noexc.cpp"
#include <cstdio>
#include <cstdlib>
#include <expected>
#include <new>
#include <string>
#include <vector>

int main(int argc, char** argv) {
  std::vector<int> v(3);
  std::size_t huge = std::strtoull("100000000000000", nullptr, 10);
  void* p = nullptr;
  switch (argc > 1 ? std::atoi(argv[1]) : 0) {
    case 1: std::printf("%d\n", v.at(10)); break;
    case 2: v.reserve(v.max_size() + 1); break;
    case 3: {
      std::expected<int, int> e = std::unexpected(7);
      std::printf("%d\n", e.value());
      break;
    }
    case 4: p = new char[huge]; break;
    case 5: std::printf("%d\n", std::stoi("abc")); break;
    case 6: p = new (std::nothrow) char[huge]; break;
  }
  std::printf("p = %p\n", p);
}
```

用 `clang++ -std=c++2c -O2 -fno-exceptions` 编译，本机 libc++ 23 上逐项运行：

| 参数 | 操作 | 结果 |
|---|---|---|
| 1 | `v.at(10)` | 打印 `out_of_range was thrown in -fno-exceptions mode with message "vector"`，`abort` |
| 2 | `reserve` 超过 `max_size()` | 打印 `length_error was thrown in -fno-exceptions mode ...`，`abort` |
| 3 | 没有值时 `e.value()` | 打印 `bad_expected_access was thrown in -fno-exceptions mode`，`abort` |
| 4 | `new` 分配 100 TB | `libc++abi: terminating due to uncaught exception of type std::bad_alloc` |
| 5 | `std::stoi("abc")` | `libc++abi: terminating due to uncaught exception of type std::invalid_argument` |
| 6 | `new (std::nothrow)` 分配 100 TB | 返回空指针，`p = 0x0` |

前三项的抛出写在头文件里，随用户代码一起以 `-fno-exceptions` 编译，libc++ 把它们替换成打印一条消息再 `abort`。后两项的实现在预编译的 libc++ 动态库里，那里是以支持异常的方式编译的，于是真的抛出了异常。异常穿过用户代码的栈帧时没有着陆点，局部对象不会析构，最后找不到 handler，调用 `std::terminate`（[[except.handle#8]]）。

由此得到 `-fno-exceptions` 代码库的几条实际规则：

- 标准库报告失败的唯一方式变成了终止。`at()`、`value()`、`stoi` 这类函数实际上不能用来报告可恢复错误，要换成先检查再访问、`std::from_chars` 这类不抛出的接口。
- 分配失败默认终止。`operator new` 的规格要求失败时抛出 `bad_alloc`（[[new.delete.single#2]]），`-fno-exceptions` 改变不了预编译库的行为。真的要处理分配失败，只能用 `new (std::nothrow)` 并检查空指针，或者使用自己的分配器；标准容器没有办法把分配失败报告给调用方。
- 第三方库是否抛出，要在接入时确认。一个会抛出的库链接进 `-fno-exceptions` 的程序，它的异常会穿过没有着陆点的帧。

## 错误的上下文

只说 `not an integer` 的错误几乎没法排查。有用的错误报告要回答：哪个文件、哪一行、什么值、在做什么的时候。

上下文要在知道它的地方加上。`to_int` 知道值，`parse_config` 知道行号，`load_config` 知道文件名。前面四个版本里，异常和 `expected` 可以把这些都放进错误对象；`error_code` 只能靠额外的输出参数。

异常还可以逐层包装。`std::throw_with_nested` 抛出一个新异常，同时把当前异常嵌在里面；`std::rethrow_if_nested` 把它取出来（[[except.nested]]）：

```cpp run title="nested.cpp" ok
#include <cstdio>
#include <exception>
#include <stdexcept>
#include <string>

int to_int(const std::string& s) {
  if (s.empty() || s.find_first_not_of("0123456789") != s.npos)
    throw std::invalid_argument("not an integer: " + s);
  return std::stoi(s);
}

int load_port(const std::string& path) {
  try {
    return to_int("80a");               // 假装从 path 读到了 "80a"
  } catch (...) {
    std::throw_with_nested(             // 加一层上下文，原异常嵌在里面
        std::runtime_error("loading " + path));
  }
}

void print(const std::exception& e, int depth = 0) {
  std::printf("%*s%s\n", depth * 2, "", e.what());
  try {
    std::rethrow_if_nested(e);
  } catch (const std::exception& inner) {
    print(inner, depth + 1);
  }
}

int main() {
  try {
    load_port("app.conf");
  } catch (const std::exception& e) {
    print(e);                           // 只在这里记录一次
  }
}
```

本机输出：

```text
loading app.conf
  not an integer: 80a
```

`expected` 的对应做法是在每一层用 `transform_error` 往 `E` 里添加信息，上面的基准程序就用它补上行号。

### 栈回溯信息

另一种上下文是调用栈。C++23 的 `std::stacktrace::current()` 在当前位置记录调用栈（[[stacktrace.basic.cons#1]]，[[P0881R7]]）。它是 `noexcept` 的，记录失败时返回一个空的栈。要让异常带上抛出点的调用栈，必须在抛出前记录，因为 `catch` 子句运行时栈已经回溯掉了。

本机 libc++ 23 没有 `<stacktrace>`，`#include` 报 file not found，`__cpp_lib_stacktrace` 也没有定义。libstdc++ 和 MSVC STL 已经提供，用法和平台状况见 [[stacktrace]]。在 libc++ 上需要调用栈时，只能用平台接口（如 glibc 和 macOS 提供的 `backtrace`）或第三方库，或者让程序崩溃后由调试器和崩溃报告来提供，见 [[toolchain/debugging|调试]]。

每次抛出都记录调用栈会让出错路径更慢。适合记录的是不应发生、需要事后排查的错误，而不是每秒发生上千次的输入校验失败。

## 记录还是传播

一个错误要么在当前层处理掉，要么传给上层，不要两样都做。下面这种写法在每一层都打一行日志再重新抛出，一个错误在日志里出现三次，每次的上下文都不完整：

```cpp
Config load_config(const char* path) {
  try {
    return parse_config(read_file(path));
  } catch (const std::exception& e) {
    log_error("load_config failed: {}", e.what());
    throw;
  }
}
```

建议的分工是：

- 下层只负责往错误里加上下文（包装异常，或者往 `E` 里加字段），然后传播；
- 决定怎样应对的那一层负责记录，记录一次，带上完整的上下文；
- 不需要应对、只想知道发生过的失败（比如用默认值替代缺失的可选配置），在替代的地方记录一条低级别日志，然后不再传播。

程序缺陷是例外：发现 bug 时程序状态已经不可信，应当就地记录能记录的信息并终止。这正是 terminate 处理函数和契约违约处理函数的用途。

## 用 `[[nodiscard]]` 防止忽略错误

返回值形式的错误最大的风险是调用方根本不看。`[[nodiscard]]` 可以标在函数上，也可以标在类或枚举上（[[dcl.attr.nodiscard#1]]）。调用一个标了 `nodiscard` 的函数，或者返回类型是 nodiscard 类型的函数，叫做 nodiscard 调用（[[dcl.attr.nodiscard#3]]）；丢弃它的结果时，标准建议实现给出警告（[[dcl.attr.nodiscard#4]]）。

```cpp run title="nodiscard.cpp" ok
#include <expected>
#include <system_error>

std::expected<int, int> f();
std::error_code g();
enum class [[nodiscard("check the status")]] Status { ok, failed };
Status h();
struct [[nodiscard]] Error { int code; };
template <class T> using Result = std::expected<T, Error>;
Result<int> k();

void use() {
  f();         // 本机无警告
  g();         // 本机无警告
  h();         // 警告，附带 "check the status"
  k();         // 本机无警告
  (void)h();   // 显式丢弃，无警告
}
```

本机 Clang 23 加 `-Wall -Wextra` 只对 `h()` 给出警告：

```text
nodiscard.cpp:15:3: warning: ignoring return value of type 'Status' declared with 'nodiscard' attribute: check the status [-Wunused-value]
```

libc++ 没有把 `std::expected` 和 `std::error_code` 标成 nodiscard 类型。`Result<int>` 的错误类型 `Error` 虽然标了，`expected<int, Error>` 本身仍不是 nodiscard 类型。

建议：返回错误的函数逐个标上 `[[nodiscard]]`，或者为项目定义自己的、标了 `[[nodiscard]]` 的结果类型。作为补充，clang-tidy 的 `bugprone-unused-return-value` 在本机默认配置下对上例的 `f()`、`g()`、`k()` 都给出了警告，见 [[toolchain/static-analysis|静态分析]]。哪些函数该标，属于 [[toolchain/api-design|API 设计]] 的问题。

## 程序缺陷：断言、加固与契约

### `assert`

`assert(cond)` 在条件不成立时打印诊断并调用 `abort`。定义了 `NDEBUG` 时它展开成 `((void)0)`，什么也不做（[[assertions.assert#1]]）。本机 CMake 3.29 的 `Release` 和 `RelWithDebInfo` 配置默认在编译选项里加 `-DNDEBUG`，所以 `assert` 在发布版本里通常不存在：它是开发期的检查，不是生产环境的防线。

### 标准库加固

前面说过，`vector::operator[]` 的越界是加固前置条件。实现是否为**加固实现**（hardened implementation）由实现定义（[[intro.compliance.general#8]]）。在加固实现中，加固前置条件会在函数产生其他副作用之前以终止型语义检查；在非加固实现中，违反它仍然是 UB（[[structure.specifications#3.5]]，[[P3471R4]]）。

```cpp title="hardening.cpp"
#include <cstdio>
#include <vector>
int main(int argc, char**) {
  std::vector<int> v(3);
  std::printf("%d\n", v[argc + 2]);   // 越界：下标为 3
}
```

libc++ 用宏 `_LIBCPP_HARDENING_MODE` 选择模式。本机 Homebrew libc++ 默认不加固。以 `-O2` 编译、不带参数运行：

| `-D_LIBCPP_HARDENING_MODE=` | 结果 |
|---|---|
| 不定义（默认，即 `_LIBCPP_HARDENING_MODE_NONE`） | 打印 `0`，读了数组之外的内存，UB |
| `_LIBCPP_HARDENING_MODE_FAST` | `SIGTRAP`，退出码 133，没有消息 |
| `_LIBCPP_HARDENING_MODE_EXTENSIVE` | 同上 |
| `_LIBCPP_HARDENING_MODE_DEBUG` | 打印 `libc++ Hardening assertion __n < size() failed: vector[] index out of bounds`，`abort`，退出码 134 |

FAST 模式下的检查只是一次比较加一条陷阱指令，本机 `-O2` 汇编中 `main` 的开头是 `cmp w8, #3`、`b.hs`，越界分支是 `brk #0x1`。本机 libc++ 的配置让检查语义随模式而定：FAST 和 EXTENSIVE 用 quick-enforce（直接陷入），DEBUG 用 enforce（先打印再终止），名称与 C++26 契约的求值语义对应。libstdc++ 的对应开关是 `-D_GLIBCXX_ASSERTIONS`。

加固检查只覆盖标准库自己的前置条件，而且检查失败就终止，不能接住、不能恢复。这正符合程序缺陷的处理原则。

### C++26 契约

C++26 允许把前置条件和后置条件写在函数声明上，在函数体内用 `contract_assert` 断言（[[basic.contract]]，[[dcl.contract.func]]，[[stmt.contract.assert]]，[[P2900R14]]）。回到分类一节的 `Port`：

```cpp title="port.cpp（C++26，本机 Clang 23 不支持，未编译）"
class Port {
  int v_;
public:
  explicit Port(int v)
    pre(0 < v && v <= 65535)
    : v_(v) {}
  int value() const
    post(r: 0 < r && r <= 65535)
  { return v_; }
};
```

每次检查使用 ignore、observe、enforce、quick-enforce 四种求值语义之一，选哪一种由实现定义（[[basic.contract.eval#1]]，[[basic.contract.eval#2]]）。标准建议实现提供全部忽略和全部 enforce 两种构建方式，默认 enforce（[[basic.contract.eval#3]]）。和 `assert` 相比，契约写在声明上，调用方和工具都看得见；违约时调用一个可替换的处理函数，可以统一记录。

本机 Clang 23 不认识 `pre` 和 `contract_assert`，也没有 `-fcontracts` 之类的选项，`__cpp_contracts` 没有定义，上例没有在本机验证。契约的设计取舍和尚未解决的争议（例如同一个内联函数在不同翻译单元以不同语义编译）见 [[history/contracts]]，本页不对是否采用契约给出建议。

!!! pitfall "不要把输入校验写成前置条件"
    `parse_port` 收到 `80a` 不是 bug，它就是用来处理这种输入的，失败要报告给调用方。只有在调用方已经负责校验之后，下游函数才把有效范围写成前置条件。把外部输入的校验写成 `pre` 或 `assert`，在忽略语义或 `NDEBUG` 下就等于没有校验。

## 怎样选择

下面是一组建议，每条都附上理由。项目已有既定风格时，一致性通常比局部最优更重要。

1. **程序缺陷不用错误报告机制。** 用 `assert`、标准库加固、C++26 契约在发现时终止。把 bug 当成错误码返回，调用方只能继续在错误的状态上运行。
2. **调用方经常需要就地处理的失败，放进返回值。** 解析用户输入、查找可能不存在的键、网络请求失败，这些失败是常规结果。用 `std::expected<T, E>`，`E` 是带上下文的结构体，并标 `[[nodiscard]]`。出错路径和正常路径一样便宜。
3. **少见、要跨很多层才有人处理的失败，用异常。** 配置损坏导致启动失败、深层的 I/O 错误要退回到请求级别。中间层不必写传播代码，栈回溯负责清理。前提是代码库允许异常，且出错频率低到几微秒的代价无关紧要。
4. **与操作系统或 C 库的错误码对接时用 `std::error_code`。** 它能无损地包装 `errno` 和平台错误码，并通过 `error_condition` 可移植地比较。需要更多上下文时，把它放进 `expected` 的 `E` 里，而不是单独使用。
5. **导出给 C 或其他语言的接口用返回码。** 接口实现内部可以用任何风格，在边界上用 `noexcept` 函数接住一切并转换。
6. **内存耗尽通常不处理。** 让 `bad_alloc` 传到顶层终止，或在 `-fno-exceptions` 下直接终止。确实要应对的场合（大块缓冲区、可以降级的缓存），在那一处用 `new (std::nothrow)` 或专门的分配器单独处理。
7. **每个模块一种风格，边界上转换。** 内部抛出、对外返回 `expected` 的函数标 `noexcept`；回调不让异常进入 C 的栈帧。

## 思考题

!!! question "1"
    `boundary.cpp` 中的 `try_load_config` 接住了 `ParseError`、`system_error` 和 `bad_alloc`。它在什么情况下仍然会调用 `std::terminate`？

<details markdown="1">
<summary>答案</summary>

有两种情况。一是 `load_config` 抛出了这三种之外的异常，比如某个第三方库的异常类型，它没有匹配的 handler，搜索离开 `noexcept` 函数的函数体，调用 `std::terminate`（[[except.handle#7]]）。二是 handler 本身抛出：`catch (const ParseError& e)` 里构造 `LoadError` 要把 `e.what()` 复制进一个 `std::string`，这次分配也可能抛出 `bad_alloc`，它同样会离开 `noexcept` 函数。

这是有意的设计：边界函数宁可终止，也不让未经翻译的异常进入不处理异常的调用方。需要更宽容时，可以再加一个 `catch (...)`，返回一个表示未知错误的 `LoadError`，并且不在里面分配内存。
</details>

!!! question "2"
    在 `-fno-exceptions` 编译的程序中，`new` 分配失败。分配之前构造的局部对象，它们的析构函数会运行吗？

<details markdown="1">
<summary>答案</summary>

不一定，多数情况下不会。libc++ 的 `operator new` 在预编译库中，以支持异常的方式编译，失败时抛出 `bad_alloc`。用户代码的帧以 `-fno-exceptions` 编译，没有着陆点，即使回溯经过这些帧也不会析构其中的对象。整个程序里没有匹配的 handler 时，调用 `std::terminate` 之前是否回溯栈本身就由实现定义（[[except.handle#8]]）；本机 libc++abi 在搜索阶段找不到 handler 就直接终止，输出 `terminating due to uncaught exception of type std::bad_alloc`。所以在这种代码库里，分配失败等同于立即终止，不能指望 RAII 做任何清理。
</details>

!!! question "3"
    一个函数返回 `std::expected<Config, ConfigError>`，`ConfigError` 标了 `[[nodiscard]]`。调用方写 `load(path);` 并丢弃结果，按标准应当得到警告吗？

<details markdown="1">
<summary>答案</summary>

标准不鼓励警告。nodiscard 调用要求被调用的函数标了 `nodiscard`，或者返回类型本身是 nodiscard 类型（[[dcl.attr.nodiscard#3]]）。返回类型是 `expected<Config, ConfigError>`，这个类模板特化本身没有标 `nodiscard`，它的模板实参标了不算。本机 Clang 23 对 `nodiscard.cpp` 中的 `k()` 确实没有警告。要得到警告，就在函数上标 `[[nodiscard]]`，或者使用一个自己标了 `[[nodiscard]]` 的结果类型。
</details>

## 小结

| 问题 | 结论 | 出处 |
|---|---|---|
| 标准库怎样区分 bug 与可恢复错误 | *Preconditions* / *Hardened preconditions* 对 *Throws* / *Error conditions* | [[structure.specifications#3]] |
| 异常的代价 | 正常路径本机测不出；抛出一次约 4–6 µs，重新抛出再翻倍 | [[toolchain/exception-implementation]] |
| `expected` 的单子操作 | `and_then`、`transform`、`or_else`、`transform_error`，失败时短路 | [[expected.object.monadic]] |
| `error_code` 的比较 | 与 `error_condition` 比较由类别的 `equivalent` 决定；类别按地址区分 | [[syserr.compare#2]]、[[syserr.errcat.overview]] |
| 异常离开 `noexcept` 边界 | `std::terminate` | [[except.handle#7]] |
| 跨 C 代码传递异常 | 在回调里存进 `exception_ptr`，回到 C++ 后重新抛出 | [[propagation#9]]、[[propagation#11]] |
| `-fno-exceptions` 下的标准库 | 头文件中的抛出改为终止；预编译库中的抛出照常发生，最终终止 | [[except.handle#8]] |
| 丢弃错误返回值 | 只有 nodiscard 调用才鼓励警告；libc++ 的 `expected` 不是 nodiscard 类型 | [[dcl.attr.nodiscard#3]] |
| 程序缺陷 | `assert`（受 `NDEBUG` 控制）、标准库加固、C++26 契约 | [[assertions.assert#1]]、[[structure.specifications#3.5]]、[[basic.contract.eval]] |
