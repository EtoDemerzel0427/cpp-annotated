---
title: Choosing an error-handling strategy
summary: "How a project reports and handles errors: first tell program bugs, recoverable environmental failures and exceptional situations apart, then choose between exceptions, error_code, std::expected and return codes, and deal with module boundaries, -fno-exceptions, error context, nodiscard, assertions, standard library hardening and contracts."
group: Engineering practice
tags: error handling, exceptions, expected, error_code, contracts, hardening, engineering practice
updated: 2026-10-19
---

!!! tldr
    - Classify errors first: program bugs (precondition violations) should terminate as early as possible, recoverable environmental failures (missing file, malformed input) should be reported to the caller, and exceptional situations such as running out of memory can, in most programs, only be allowed to propagate to the top.
    - The happy-path costs of the four styles (exceptions, `std::error_code`, `std::expected`, return code plus out-parameters) were indistinguishable in our measurements; on the error path, throwing an exception once costs several microseconds, while the other three cost a few nanoseconds.
    - Styles can be mixed, but convert at module boundaries: a function that throws inside and returns `expected` outside is sealed with `noexcept`; a callback handed to C code must never let an exception cross C stack frames.
    - Standard library errors still happen under `-fno-exceptions`: `at()` and `value()` in headers terminate directly instead, and a failed `operator new` still throws, terminating when nobody catches it.
    - Functions that return errors should be marked `[[nodiscard]]`; libc++'s `std::expected` itself isn't. Hand program bugs to `assert`, standard library hardening or C++26 contracts, rather than propagating them as recoverable errors.

## Classify errors first

Reading a configuration file `app.conf`, at least four things can go wrong:

1. The file doesn't exist, or isn't readable;
2. The file says `port=80a`;
3. Somewhere the code accesses the configuration with `ports[i]`, and `i` is out of range;
4. Memory runs out while reading the file.

The first two are the world outside the program not cooperating. The program itself is fine, and the caller may be able to do something: try another path, use a default configuration, ask the user to fix the file. Errors of this kind are called **recoverable errors**; they are part of the function's contract and should be reported to the caller.

The third is different. An out-of-range access means the program's own logic is wrong, the program state can no longer be trusted, and the caller can't recover from a bug whose cause it doesn't know. Errors of this kind are **program bugs**, also called precondition violations. The sensible response is to detect them as early as possible and stop as early as possible, rather than returning them layer by layer as values.

The fourth lies between the two. It isn't a bug, but almost no caller can handle it on the spot; usually it can only propagate to the top, or terminate the program directly.

The standard library's own specifications make the same distinction ([[structure.specifications#3]]):

| Specification element | Meaning | On violation or failure |
|---|---|---|
| *Preconditions* | Conditions the caller must guarantee | UB (¶3.4) |
| *Hardened preconditions* | Same, but checked by a hardened implementation | A contract violation in a hardened implementation, otherwise UB (¶3.5) |
| *Throws* | Exceptions the function may throw | Throws (¶3.11) |
| *Error conditions* | Errors reported through `error_code` | Sets the `error_code` (¶3.14) |

For example, an out-of-range index for `vector::operator[]` is a hardened precondition ([[sequence.reqmts#122]]), while an out-of-range index for `vector::at` is listed under *Throws* and throws `out_of_range` ([[sequence.reqmts#127]]). The same check: the former treats it as the caller's bug, the latter as a situation the caller wants to handle.

<div class="compare" markdown="1">

```cpp
// external input: a failed validation is a recoverable error
std::expected<Port, ConfigError>
parse_port(std::string_view text);
```

```cpp
// internal: the caller guarantees v has been validated
// if not, it is a bug
Port::Port(int v);  // precondition:
                    // 0 < v && v <= 65535
```

</div>

The classification decides the mechanism. Program bugs are handled with assertions, hardening or contracts, covered in the last section. The sections in between are all about how to report recoverable errors.

## One task, four styles

The task is fixed: read a file and parse it line by line as `key=value`, where `host` is a string and `port` an integer. Three errors must be reported: failure to open the file (with `errno`), a line without `=`, and a `port` that isn't an integer; the last two carry a line number.

### Exceptions

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

Output:

```text
example.org:8080
line 2: not an integer: 80a
missing.conf: No such file or directory
```

The function signatures contain only the normal result; the intermediate layer `parse_config` doesn't have to deal with `to_int`'s failure at all, and the error automatically propagates to the nearest `catch`. The error information lives in the exception object: `ParseError` carries the line number and `system_error` carries `errno`. `read_file` manages the `FILE*` with `unique_ptr`, so stack unwinding closes the file when something is thrown. How these guarantees hold is covered in [[topics/exception-safety]].

The cost is that failure doesn't appear in the signature. Reading the declaration of `load_config` doesn't tell you what it throws; only the documentation can.

### `std::expected`

A `std::expected<T, E>` holds either a `T` or an `E` ([[expected]], {{c++23}}, [[P0323R12]]). The error becomes part of the return value:

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
  std::error_code code;   // which kind of error
  int line = 0;           // 0 means not tied to a line
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
  // transform: transforms the value only when there is one
  auto port = parse_config("host=example.org\nport=8080\n")
                  .transform([](const Config& c) { return c.port; });
  std::printf("port %d\n", *port);

  // or_else: fall back to a default configuration if the file is missing, pass other errors through
  auto cfg = load_config("missing.conf").or_else(
      [](const ConfigError& e) -> Result<Config> {
        if (e.code == std::errc::no_such_file_or_directory)
          return Config{"localhost", 80};
        return std::unexpected(e);
      });
  std::printf("%s:%d\n", cfg->host.c_str(), cfg->port);

  // transform_error: turn the error into a message at the boundary
  auto msg = parse_config("port=80a\n").transform_error(
      [](const ConfigError& e) {
        return "line " + std::to_string(e.line) + ": " + e.detail;
      });
  if (!msg) std::printf("%s\n", msg.error().c_str());
}
```

Output:

```text
port 8080
localhost:80
line 1: not an integer: 80a
```

`main` uses C++23's four monadic operations ([[P2505R5]], [[expected.object.monadic]]):

| Operation | With a value | With an error |
|---|---|---|
| `and_then(f)` | Returns `f(value)`, where `f` itself returns an `expected` | Passes the error through |
| `transform(f)` | Returns an `expected` holding `f(value)` | Passes the error through |
| `or_else(f)` | Passes the value through | Returns `f(error)`, where `f` itself returns an `expected` |
| `transform_error(f)` | Passes the value through | Returns an `expected` holding `f(error)` |

`load_config` chains the two steps with `and_then`, short-circuiting if either fails. But inside `parse_config`'s loop, monadic operations don't help, and the check has to be written by hand:

```cpp
auto v = to_int(val, no);
if (!v) return std::unexpected(std::move(v.error()));
c.port = *v;
```

C++ has no equivalent of Rust's `?` operator, so every call that may fail takes these three lines. The error type `ConfigError` can be designed freely; here it holds an `error_code`, a line number and a description, far more than an integer can carry.

`*v` requires `v` to hold a value; that is a hardened precondition of `operator*` ([[expected.object.obs#3]]). `v.value()` throws `bad_expected_access` when there is no value ([[expected.object.obs#11]]). After a hand-written check, `*v` is fine.

### `std::error_code`

A `std::error_code` holds just two things: an `int` and a pointer to an error category ([[syserr.errcode.overview]]). It was originally meant to wrap operating system error codes, and the standard positions it as a complement to exception reporting (the note in [[syserr.errcode.overview#1]]). Most functions in `<filesystem>` have two overloads, one that throws `filesystem_error` and one with an extra `error_code&` parameter ([[fs.err.report#1]]); the code below imitates that:

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

// 1. this module's own error enumeration (0 is reserved for "no error")
enum class config_errc { syntax = 1, not_an_integer };

// 2. an error category: name and messages
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

// 3. make config_errc implicitly convertible to error_code
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

// there is nowhere to put the line number, so add another out-parameter
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

// throwing version: wraps the error_code version, as <filesystem> does
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
  if (ec == std::errc::no_such_file_or_directory)   // portable comparison
    std::printf("%s: %s\n", ec.category().name(), ec.message().c_str());

  try { parse_config("host\n"); }
  catch (const std::system_error& e) { std::printf("%s\n", e.what()); }
}
```

Output:

```text
example.org:8080
config:2 at line 1: not an integer
generic: No such file or directory
line 1: expected key=value
```

A custom error code takes three steps: an enumeration, a category derived from `std::error_category`, and a `make_error_code` plus a specialization of `is_error_code_enum`. Only with the last two does `ec = config_errc::syntax` compile ([[syserr.errcode.constructors#3]]).

`ec == std::errc::no_such_file_or_directory` compares an `error_code` with an `error_condition`, and the result is decided by the category's `equivalent` ([[syserr.compare#2]]). So system error codes whose numeric values differ between platforms can be compared with the same portable condition.

The problem with `error_code` is that it can't carry context. There is nowhere to put the line number, so `parse_config` needs an extra `int& line` parameter; to also return the offending text, it would need yet another.

!!! pitfall "Categories compare by address"
    Two `error_category` objects are equal if and only if they have the same address (the note in [[syserr.errcat.overview#1]]). If the static object in `config_category()` exists twice in a process because of symbol visibility settings in shared libraries, the same error code coming from two libraries compares unequal. This is one of the things to watch for at [[toolchain/library-boundaries|library boundaries]].

### Return code plus out-parameters

The C style: return a status code, and bring back the result and extra information through pointers.

```cpp run title="config-return-code.cpp" ok
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>

struct Config { char host[64]; int port; };

enum cfg_status { CFG_OK = 0, CFG_EOPEN, CFG_ESYNTAX, CFG_EINT };

// returns a status code; the result, the failing line number and errno come back through out-parameters
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
  char buf[4096];                 // illustration only: anything past 4 KiB is truncated
  std::size_t n = std::fread(buf, 1, sizeof buf - 1, f);
  std::fclose(f);                 // must remember to close on every return path
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
  load_config("missing.conf", &c, &line, &err);   // warning: return value ignored
}
```

Output:

```text
example.org:8080
line 1: not an integer
open: No such file or directory
```

Compiling also gives a warning, because the last line ignores the return value of a `[[nodiscard]]` function:

```text
config-return-code.cpp:58:3: warning: ignoring return value of function declared with 'nodiscard' attribute [-Wunused-result]
```

This style depends on no C++ runtime facilities and can be exported directly to C and other languages. The cost is that every return path must release resources by hand (`fclose` can only be written after `fread`), the correspondence between status codes and out-parameters rests entirely on convention, and a caller who forgets to check still compiles.

### Side by side

| | Exceptions | `expected` | `error_code` | Return code |
|---|---|---|---|---|
| Failure appears in the signature | No | Yes | Yes (parameter) | Yes |
| Propagation code in intermediate layers | None | About three lines per call | One `if` per call | One `if` per call |
| Context an error can carry | Anything (the exception object) | Anything (`E`) | An integer plus a category | Only through extra out-parameters |
| Can the caller silently ignore it? | No; terminates if nobody catches | Yes, unless `[[nodiscard]]` | Yes | Yes, unless `[[nodiscard]]` |
| Usable under `-fno-exceptions` | No | Yes | Yes | Yes |
| Across C interfaces | No | No | Partly (only the integer) | Yes |

## Cost: measurements

### Happy path and error path

To compare only the reporting mechanisms, the benchmark below has the four styles do the same work: parse an integer with `from_chars`, pass errors back through three levels of non-inlined calls, and add the line number at the outermost level. The exception version has an extra variant that doesn't add the line number and propagates straight to `main`.

<details class="fine" markdown="1"><summary>Benchmark program micro.cpp</summary>

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

// the same work: parse an integer, pass errors back through three call levels, add the line number at the top
namespace exc {
NOINLINE int to_int(std::string_view s) {
  int v;
  if (bad_int(s, v)) throw Err{1, 0};
  return v;
}
NOINLINE int field(std::string_view s) { return to_int(s) + 1; }
NOINLINE int line(std::string_view s, int no) {
  try { return field(s) * 2; }
  catch (Err& e) { e.line = no; throw; }      // add the line number, then rethrow
}
NOINLINE int line_plain(std::string_view s, int) {
  return field(s) * 2;                         // no line number added
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
  for (int rep = 0; rep < 15; ++rep) {      // take the fastest of 15 rounds
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

Compiled with `clang++ -std=c++2c -O2` and run on our test machine (Apple M2 Pro, libc++abi), each item taking the fastest of 15 rounds. The machine was heavily loaded during measurement (load average about 80); the table gives the range over two runs and should only be read for orders of magnitude:

| Style | Happy path | Error path |
|---|---|---|
| Exception, caught midway to add the line number and rethrown | 8.3 ns | 8.5–11 µs |
| Exception, propagated straight to the top | 8.3 ns | 4.2–5.9 µs |
| `expected` | 8.3–9.5 ns | 6.7–9 ns |
| `error_code` | 8.9 ns | 8.0 ns |
| Return code | 8.6–8.9 ns | 7.4 ns |

On the happy path the four styles show no measurable difference; the time goes into parsing and function calls. On the error path, the three value-based styles are as fast as the happy path; exceptions are about three orders of magnitude slower, and a `catch` midway followed by `throw;` amounts to throwing again, doubling the time. Where the time goes is covered in the two-phase unwinding section of [[toolchain/exception-implementation]].

These numbers say only one thing: how often errors happen decides whether the cost of exceptions matters. A configuration file read once in a program's lifetime can afford a few extra microseconds for a throw; a network service that rejects tens of thousands of malformed requests per second shouldn't report that failure with exceptions.

### Binary size

Removing `main` from each of the four versions and compiling only the library functions with `clang++ -std=c++2c -O2 -c`, `llvm-size -m` gives the byte count of each section of the object file:

| Version | `__text` | `__gcc_except_tab` | `__compact_unwind` |
|---|---|---|---|
| Exceptions | 3032 | 148 | 512 |
| `expected` | 2972 | 148 | 384 |
| `expected`, `-fno-exceptions` | 2564 | 0 | 0 |
| `error_code` (including the throwing wrapper) | 3324 | 108 | 576 |
| Return code | 600 | 0 | 64 |
| Return code, `-fno-exceptions` | 600 | 0 | 0 |

The `expected` version has not a single `throw`, yet it has exception tables just like the exception version. The reason is that `std::string` allocations can throw `bad_alloc`, and `unique_ptr` needs landing pads to close the file during unwinding. Only with `-fno-exceptions` do these landing pads and tables disappear, and `__text` shrinks by about 14%.

The return-code version is five times smaller, mainly not because of how it handles errors but because it doesn't use `std::string` at all. Size depends first on which library facilities are used; the error mechanism is a secondary factor.

## Converting styles at module boundaries

A project rarely uses only one style: the standard library throws, operating system interfaces return `errno`, and third-party libraries each have their own conventions. A workable approach is for each module to pick one style internally and convert uniformly at its boundaries.

### Throwing inside, returning `expected` outside

Suppose the configuration module is written internally with exceptions (the first version above), but must be offered to a caller that disables exceptions or doesn't want to deal with them. The code below follows the library functions of `config-exceptions.cpp` (with the original `main` removed and `<expected>` and `<new>` added):

```cpp title="boundary.cpp (follows the library functions of config-exceptions.cpp)"
// the module's external interface: doesn't throw, returns expected
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
  // any other exception: leaves a noexcept function, std::terminate
}

int main() {
  auto r = try_load_config("missing.conf");
  if (!r) std::printf("%s (%s)\n", r.error().message.c_str(),
                      r.error().code.message().c_str());
}
```

Output:

```text
missing.conf: No such file or directory (No such file or directory)
```

`try_load_config` is the boundary: it catches every kind of exception this module throws and translates it into a `LoadError`. With `noexcept`, an exception type that was missed doesn't silently cross the boundary; instead `std::terminate` is called as it leaves the function ([[except.handle#7]]). That is easier to notice than a caller unexpectedly receiving an exception.

The other side of the boundary works the same way: when a module written with `expected` has to hand an error to code that throws, write `if (!r) throw ...;` at the boundary, or call `r.value()`, which throws `bad_expected_access`.

### C interfaces and callbacks

When a C library calls a callback written in C++, an exception must never leave the callback. `walk_lines` below is a C function that calls the callback for each line and frees the memory it allocated before returning:

```c title="walk.c"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef int (*line_cb)(const char* line, size_t len, void* user);
int walk_lines(const char* text, line_cb cb, void* user) {
  char* copy = strdup(text);          /* the C code's own resource */
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

If the callback throws directly, the exception has to cross `walk_lines`'s stack frame. C compilers don't generate landing pads for C code, so `free(copy)` doesn't run. We compiled the C part with `clang -c -O2 walk.c` and had the callback throw a `runtime_error`: the outer `catch` caught the exception (on macOS, C code has unwind information by default too), but the `walk_lines: freed` line was never printed, and the memory leaked. On platforms or with compile options without unwind information, the result may be immediate termination. The standard has no say over C translation units, and there is no guarantee whatsoever about this behavior.

The correct approach is to catch everything in the callback, store the exception in a `std::exception_ptr`, let the C code return normally, and rethrow once back in C++:

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

// the callback boundary: exceptions don't cross C frames; store them first
extern "C" int on_line(const char* p, std::size_t n, void* user) noexcept {
  auto* self = static_cast<Collector*>(user);
  try {
    self->feed({p, n});
    return 0;
  } catch (...) {
    self->error = std::current_exception();
    return -1;                      // let the C code return normally and free its resources
  }
}

int count_entries(const char* text) {
  Collector c;
  walk_lines(text, on_line, &c);
  if (c.error) std::rethrow_exception(c.error);   // rethrow once back in C++
  return c.count;
}

int main() {
  std::printf("%d\n", count_entries("a=1\nb=2\n"));
  try { count_entries("a=1\noops\n"); }
  catch (const std::exception& e) { std::printf("%s\n", e.what()); }
}
```

Compiled together with `walk.c` and run in a terminal, the output is (the two `freed` lines come from standard error):

```text
walk_lines: freed
2
walk_lines: freed
bad line: oops
```

In both calls the C code freed its memory. `std::current_exception` gets the exception currently being handled ([[propagation#9]]), and `std::rethrow_exception` throws it again ([[propagation#11]]), preserving its type and content.

The callback itself is marked `noexcept`, so even if code inside `catch (...)` throws again, the program terminates at the callback's boundary instead of entering C stack frames. If the callback type is defined on the C++ side, `noexcept` can also be written into the function pointer type. `noexcept` is part of the function type, and a potentially-throwing function can't be converted to a pointer to a `noexcept` function ([[conv.fctptr#1]] only allows the opposite direction):

```cpp run title="noexcept-callback.cpp" error
#include <cstddef>
using line_cb = int (*)(const char*, std::size_t, void*) noexcept;
void subscribe(line_cb cb);

int may_throw(const char*, std::size_t, void*);
int wont_throw(const char*, std::size_t, void*) noexcept;

void setup() {
  subscribe(wont_throw);    // OK
  subscribe(may_throw);     // error: can't convert to a noexcept function pointer
  subscribe([](const char*, std::size_t, void*) noexcept {
    return 0;
  });                       // OK
}
```

Clang 23 reports `no known conversion from 'int (const char *, std::size_t, void *)' ... to 'line_cb'`. A callback that forgot to handle exceptions is stopped at compile time.

The same reasoning applies to thread entry functions, destructors and functions registered with `atexit`: an exception escaping from any of these calls `std::terminate` (the note in [[except.terminate#1]] lists all the cases).

## Codebases using `-fno-exceptions`

Many codebases compile with `-fno-exceptions`, a non-conforming dialect offered by GCC and Clang: `throw` and `try` don't compile, and the compiler generates no landing pads. The effects at the code generation level are covered in [[toolchain/exception-implementation]]. The concern here is the other side: what becomes of the standard library's error reporting in this mode.

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

Compiled with `clang++ -std=c++2c -O2 -fno-exceptions` and run case by case with libc++ 23:

| Argument | Operation | Result |
|---|---|---|
| 1 | `v.at(10)` | Prints `out_of_range was thrown in -fno-exceptions mode with message "vector"`, `abort` |
| 2 | `reserve` beyond `max_size()` | Prints `length_error was thrown in -fno-exceptions mode ...`, `abort` |
| 3 | `e.value()` with no value | Prints `bad_expected_access was thrown in -fno-exceptions mode`, `abort` |
| 4 | `new` allocating 100 TB | `libc++abi: terminating due to uncaught exception of type std::bad_alloc` |
| 5 | `std::stoi("abc")` | `libc++abi: terminating due to uncaught exception of type std::invalid_argument` |
| 6 | `new (std::nothrow)` allocating 100 TB | Returns a null pointer, `p = 0x0` |

The throws in the first three cases are written in headers and compiled with `-fno-exceptions` along with user code, and libc++ replaces them with printing a message and calling `abort`. The last two are implemented in the precompiled libc++ shared library, which was compiled with exception support, so an exception really is thrown. Crossing user code's stack frames, it finds no landing pads, so local objects aren't destroyed, and finally, with no handler found, `std::terminate` is called ([[except.handle#8]]).

This gives some practical rules for `-fno-exceptions` codebases:

- The standard library's only way to report failure becomes termination. Functions such as `at()`, `value()` and `stoi` effectively can't be used to report recoverable errors; switch to check-then-access and non-throwing interfaces such as `std::from_chars`.
- Allocation failure terminates by default. The specification of `operator new` requires it to throw `bad_alloc` on failure ([[new.delete.single#2]]), and `-fno-exceptions` can't change the behavior of the precompiled library. To really handle allocation failure, the only options are `new (std::nothrow)` with a null check, or your own allocator; standard containers have no way to report allocation failure to the caller.
- Whether a third-party library throws must be confirmed when integrating it. A library that throws, linked into a `-fno-exceptions` program, sends its exceptions through frames without landing pads.

## Error context

An error that only says `not an integer` is nearly impossible to track down. A useful error report answers: which file, which line, what value, and what was being done at the time.

Context should be added where it is known. `to_int` knows the value, `parse_config` the line number, `load_config` the file name. In the four versions above, exceptions and `expected` can put all of this into the error object; `error_code` can only use extra out-parameters.

Exceptions can also be wrapped layer by layer. `std::throw_with_nested` throws a new exception with the current one nested inside it, and `std::rethrow_if_nested` gets it back out ([[except.nested]]):

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
    return to_int("80a");               // pretend "80a" was read from path
  } catch (...) {
    std::throw_with_nested(             // add a layer of context, with the original nested inside
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
    print(e);                           // logged only once, here
  }
}
```

Output:

```text
loading app.conf
  not an integer: 80a
```

The `expected` counterpart is to add information to `E` with `transform_error` at each layer; the benchmark above uses it to add the line number.

### Stack traces

Another kind of context is the call stack. C++23's `std::stacktrace::current()` records the call stack at the current point ([[stacktrace.basic.cons#1]], [[P0881R7]]). It is `noexcept` and returns an empty stack if recording fails. For an exception to carry the call stack of its throw point, the stack must be recorded before throwing, because by the time a `catch` clause runs, the stack has already been unwound.

libc++ 23 on our test machine has no `<stacktrace>`: `#include` reports file not found, and `__cpp_lib_stacktrace` isn't defined. libstdc++ and MSVC STL already provide it; usage and platform status are in [[stacktrace]]. On libc++, when you need a call stack, the only options are platform interfaces (such as the `backtrace` provided by glibc and macOS), a third-party library, or letting the program crash and getting it from the debugger and crash report; see [[toolchain/debugging]].

Recording a call stack on every throw makes the error path slower. It suits errors that shouldn't happen and need investigating afterwards, not input validation failures that occur thousands of times a second.

## Log or propagate

An error should either be handled at the current layer or passed up, not both. The style below logs a line at every layer and rethrows, so one error appears in the log three times, each time with incomplete context:

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

The recommended division of labor:

- Lower layers only add context to the error (wrap the exception, or add fields to `E`) and propagate it;
- The layer that decides how to respond logs it, once, with the full context;
- For failures that need no response and that you only want to know happened (for example, substituting a default for a missing optional setting), log a low-level message where the substitution happens, and don't propagate further.

Program bugs are the exception: once a bug is found, the program state can't be trusted, and you should log whatever you can on the spot and terminate. That is exactly what terminate handlers and contract-violation handlers are for.

## Preventing ignored errors with `[[nodiscard]]`

The biggest risk with errors returned as values is that the caller never looks at them. `[[nodiscard]]` can be applied to functions, and also to classes and enumerations ([[dcl.attr.nodiscard#1]]). A call to a function marked `nodiscard`, or to a function whose return type is a nodiscard type, is a nodiscard call ([[dcl.attr.nodiscard#3]]); when its result is discarded, the standard recommends that implementations issue a warning ([[dcl.attr.nodiscard#4]]).

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
  f();         // no warning with Clang 23
  g();         // no warning with Clang 23
  h();         // warning, with "check the status"
  k();         // no warning with Clang 23
  (void)h();   // explicitly discarded, no warning
}
```

Clang 23 with `-Wall -Wextra` warns only for `h()`:

```text
nodiscard.cpp:15:3: warning: ignoring return value of type 'Status' declared with 'nodiscard' attribute: check the status [-Wunused-value]
```

libc++ doesn't mark `std::expected` or `std::error_code` as nodiscard types. Although `Result<int>`'s error type `Error` is marked, `expected<int, Error>` itself still isn't a nodiscard type.

Recommendation: mark functions that return errors with `[[nodiscard]]` one by one, or define a project-specific result type marked `[[nodiscard]]`. As a supplement, clang-tidy's `bugprone-unused-return-value` with its default configuration warned about `f()`, `g()` and `k()` in the example above in our tests; see [[toolchain/static-analysis]]. Which functions to mark is a question of [[toolchain/api-design]].

## Program bugs: assertions, hardening and contracts

### `assert`

`assert(cond)` prints a diagnostic and calls `abort` when the condition is false. When `NDEBUG` is defined it expands to `((void)0)` and does nothing ([[assertions.assert#1]]). CMake 3.29's `Release` and `RelWithDebInfo` configurations add `-DNDEBUG` to the compile options by default, so `assert` is usually absent from release builds: it is a development-time check, not a production safeguard.

### Standard library hardening

As mentioned earlier, an out-of-range index for `vector::operator[]` is a hardened precondition. Whether an implementation is a **hardened implementation** is implementation-defined ([[intro.compliance.general#8]]). In a hardened implementation, hardened preconditions are checked with a terminating semantic before the function has any other side effects; in a non-hardened implementation, violating one is still UB ([[structure.specifications#3.5]], [[P3471R4]]).

```cpp title="hardening.cpp"
#include <cstdio>
#include <vector>
int main(int argc, char**) {
  std::vector<int> v(3);
  std::printf("%d\n", v[argc + 2]);   // out of range: index 3
}
```

libc++ selects the mode with the macro `_LIBCPP_HARDENING_MODE`. Homebrew's libc++ on our test machine isn't hardened by default. Compiled with `-O2` and run without arguments:

| `-D_LIBCPP_HARDENING_MODE=` | Result |
|---|---|
| Not defined (the default, i.e. `_LIBCPP_HARDENING_MODE_NONE`) | Prints `0`, having read memory outside the array: UB |
| `_LIBCPP_HARDENING_MODE_FAST` | `SIGTRAP`, exit code 133, no message |
| `_LIBCPP_HARDENING_MODE_EXTENSIVE` | Same as above |
| `_LIBCPP_HARDENING_MODE_DEBUG` | Prints `libc++ Hardening assertion __n < size() failed: vector[] index out of bounds`, `abort`, exit code 134 |

In FAST mode the check is just a comparison plus a trap instruction: in the `-O2` assembly on our test machine, `main` begins with `cmp w8, #3`, `b.hs`, and the out-of-range branch is `brk #0x1`. The libc++ configuration on our test machine makes the check semantic depend on the mode: FAST and EXTENSIVE use quick-enforce (trap immediately), DEBUG uses enforce (print, then terminate), names that correspond to the evaluation semantics of C++26 contracts. libstdc++'s corresponding switch is `-D_GLIBCXX_ASSERTIONS`.

Hardening checks only cover the standard library's own preconditions, and a failed check terminates; it can't be caught or recovered from. This is exactly the principle for handling program bugs.

### C++26 contracts

C++26 allows preconditions and postconditions to be written on function declarations, and assertions with `contract_assert` in function bodies ([[basic.contract]], [[dcl.contract.func]], [[stmt.contract.assert]], [[P2900R14]]). Back to the `Port` from the classification section:

```cpp title="port.cpp (C++26, not supported by Clang 23, not compiled)"
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

Each check uses one of four evaluation semantics, ignore, observe, enforce and quick-enforce, and which one is implementation-defined ([[basic.contract.eval#1]], [[basic.contract.eval#2]]). The standard recommends that implementations offer a build mode that ignores everything and one that enforces everything, with enforce as the default ([[basic.contract.eval#3]]). Compared with `assert`, contracts are written on declarations, visible to callers and tools; a violation calls a replaceable handler, which allows uniform logging.

Clang 23 recognizes neither `pre` nor `contract_assert`, has no option like `-fcontracts`, and doesn't define `__cpp_contracts`, so the example above has not been verified. The design trade-offs of contracts and the disputes still open (for example, the same inline function compiled with different semantics in different translation units) are covered in [[history/contracts]]; this page makes no recommendation on whether to adopt contracts.

!!! pitfall "Don't write input validation as preconditions"
    `parse_port` receiving `80a` isn't a bug; handling such input is its job, and failure must be reported to the caller. Only once the caller has taken responsibility for validation does a downstream function write the valid range as a precondition. Validation of external input written as `pre` or `assert` amounts to no validation under the ignore semantic or `NDEBUG`.

## How to choose

Below is a set of recommendations, each with its reason. When a project already has an established style, consistency usually matters more than a local optimum.

1. **Don't use error-reporting mechanisms for program bugs.** Use `assert`, standard library hardening or C++26 contracts to terminate when a bug is detected. Return a bug as an error code, and the caller can only continue running in a wrong state.
2. **Put failures the caller often needs to handle on the spot into the return value.** Parsing user input, looking up a key that may not exist, a failed network request: these failures are ordinary outcomes. Use `std::expected<T, E>`, where `E` is a struct carrying context, and mark it `[[nodiscard]]`. The error path is as cheap as the happy path.
3. **Use exceptions for failures that are rare and handled only many layers up.** A corrupt configuration causing startup to fail, a deep I/O error that must fall back to the request level. Intermediate layers need no propagation code, and stack unwinding does the cleanup. The preconditions are that the codebase allows exceptions and that errors are rare enough for a few microseconds not to matter.
4. **Use `std::error_code` when interfacing with operating system or C library error codes.** It wraps `errno` and platform error codes losslessly and compares them portably through `error_condition`. When more context is needed, put it inside the `E` of an `expected` rather than using it alone.
5. **Use return codes for interfaces exported to C or other languages.** The implementation behind the interface can use any style; at the boundary, a `noexcept` function catches everything and converts.
6. **Usually don't handle running out of memory.** Let `bad_alloc` propagate to the top and terminate, or terminate directly under `-fno-exceptions`. Where you really must respond (large buffers, caches that can degrade), handle it separately at that one place with `new (std::nothrow)` or a dedicated allocator.
7. **One style per module, converted at the boundaries.** Mark functions that throw inside and return `expected` outside `noexcept`; callbacks don't let exceptions into C stack frames.

## Questions

!!! question "1"
    `try_load_config` in `boundary.cpp` catches `ParseError`, `system_error` and `bad_alloc`. Under what circumstances does it still call `std::terminate`?

<details markdown="1">
<summary>Answer</summary>

There are two cases. One is that `load_config` throws an exception other than these three, say some third-party library's exception type; it has no matching handler, the search leaves the body of a `noexcept` function, and `std::terminate` is called ([[except.handle#7]]). The other is that a handler itself throws: constructing the `LoadError` in `catch (const ParseError& e)` copies `e.what()` into a `std::string`, and that allocation can also throw `bad_alloc`, which likewise leaves the `noexcept` function.

This is by design: a boundary function would rather terminate than let an untranslated exception into a caller that doesn't handle exceptions. To be more lenient, add a `catch (...)` that returns a `LoadError` meaning "unknown error" and doesn't allocate memory.
</details>

!!! question "2"
    In a program compiled with `-fno-exceptions`, a `new` allocation fails. Do the destructors of local objects constructed before the allocation run?

<details markdown="1">
<summary>Answer</summary>

Not necessarily, and in most cases no. libc++'s `operator new` lives in the precompiled library, compiled with exception support, and throws `bad_alloc` on failure. User code's frames are compiled with `-fno-exceptions` and have no landing pads, so even if unwinding passes through them, their objects aren't destroyed. When the whole program has no matching handler, whether the stack is unwound before `std::terminate` is called is itself implementation-defined ([[except.handle#8]]); libc++abi on our test machine terminates as soon as the search phase finds no handler, printing `terminating due to uncaught exception of type std::bad_alloc`. So in such a codebase, allocation failure is equivalent to immediate termination, and you can't count on RAII to clean anything up.
</details>

!!! question "3"
    A function returns `std::expected<Config, ConfigError>`, and `ConfigError` is marked `[[nodiscard]]`. A caller writes `load(path);` and discards the result. Should there be a warning according to the standard?

<details markdown="1">
<summary>Answer</summary>

The standard doesn't encourage one. A nodiscard call requires that the called function be marked `nodiscard`, or that the return type itself be a nodiscard type ([[dcl.attr.nodiscard#3]]). The return type is `expected<Config, ConfigError>`; that class template specialization isn't marked `nodiscard` itself, and its template argument being marked doesn't count. Clang 23 indeed gives no warning for `k()` in `nodiscard.cpp`. To get a warning, mark the function `[[nodiscard]]`, or use a result type that is itself marked `[[nodiscard]]`.
</details>

## Summary

| Question | Conclusion | Source |
|---|---|---|
| How does the standard library separate bugs from recoverable errors? | *Preconditions* / *Hardened preconditions* versus *Throws* / *Error conditions* | [[structure.specifications#3]] |
| The cost of exceptions | Not measurable on the happy path in our tests; one throw about 4–6 µs, doubled when rethrown | [[toolchain/exception-implementation]] |
| `expected`'s monadic operations | `and_then`, `transform`, `or_else`, `transform_error`, short-circuiting on failure | [[expected.object.monadic]] |
| Comparing `error_code`s | Comparison with an `error_condition` is decided by the category's `equivalent`; categories are distinguished by address | [[syserr.compare#2]], [[syserr.errcat.overview]] |
| An exception leaving a `noexcept` boundary | `std::terminate` | [[except.handle#7]] |
| Passing exceptions across C code | Store it in an `exception_ptr` in the callback, rethrow once back in C++ | [[propagation#9]], [[propagation#11]] |
| The standard library under `-fno-exceptions` | Throws in headers become termination; throws in the precompiled library still happen and end in termination | [[except.handle#8]] |
| Discarding an error return value | Warnings are encouraged only for nodiscard calls; libc++'s `expected` isn't a nodiscard type | [[dcl.attr.nodiscard#3]] |
| Program bugs | `assert` (controlled by `NDEBUG`), standard library hardening, C++26 contracts | [[assertions.assert#1]], [[structure.specifications#3.5]], [[basic.contract.eval]] |
