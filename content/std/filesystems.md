---
title: 文件系统库
summary: std::filesystem 的总则：文件、目录和链接的定义，以 POSIX 为参照的一致性规则，文件系统竞争为什么是未定义行为，抛异常和设置 error_code 两套错误报告方式，以及 file_type、copy_options、perms 等枚举。
status: done
covers: fs.general, fs.conformance, fs.conformance.general, fs.conform.9945, fs.conform.os, fs.race.behavior, fs.req, fs.filesystem.syn, fs.err.report, fs.class.filesystem.error, fs.class.filesystem.error.general, fs.filesystem.error.members, fs.enum, fs.enum.path.format, fs.enum.file.type, fs.enum.copy.opts, fs.enum.perms, fs.enum.perm.opts, fs.enum.dir.opts
since: c++17
related: fs.class.path, fs.class.directory.iterator, fs.op.funcs, file.streams, syserr, time.clock.file, input.output
tags: 标准库, filesystem, 文件系统, TOCTOU, error_code
updated: 2026-10-19
---

!!! tldr
    - 文件系统是进程之外的共享状态。`<filesystem>` 的函数调用引入文件系统竞争时行为未定义，所以不要先检查再操作，直接操作并检查结果。
    - 大多数函数成对提供：一个出错时抛 `filesystem_error`，一个把错误写进 `error_code&` 参数，成功时把它清零。
    - `error_code&` 版本不一定是 `noexcept`，内存不足时照样抛 `bad_alloc`。
    - 行为以 POSIX 为参照；实现做不到时必须报告错误，不能静默给出错误结果。
    - `file_type` 中 `none` 表示出错，`not_found` 表示文件不存在（不算错误），`unknown` 表示文件存在但类型不明。

```cpp title="no-toctou.cpp" run ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  const fs::path dir = "work", lock = "work/app.lock";

  // 不必先 exists()：目录已存在时 create_directory 返回 false，不算错误
  std::error_code ec;
  bool created = fs::create_directory(dir, ec);
  std::cout << "created=" << created << " ec=" << ec.value() << '\n';  // created=1 ec=0

  // 独占创建：检查和创建是同一个原子操作（C++23 noreplace，即 fopen 的 "x"）
  std::ofstream first(lock, std::ios_base::out | std::ios_base::noreplace);
  std::ofstream second(lock, std::ios_base::out | std::ios_base::noreplace);
  std::cout << "first=" << first.is_open() << " second=" << second.is_open() << '\n';  // 1 0

  first.close();
  // 文件不存在时 remove 返回 false，也不必先检查
  std::cout << "removed=" << fs::remove(lock) << " again=" << fs::remove(lock) << '\n';  // 1 0
  fs::remove(dir);
}
```

`<filesystem>`（C++17，源自 Boost.Filesystem 和 Filesystem TS）处理两类事情：路径 `std::filesystem::path`，一个只关心字符串语法的值类型（[[fs.class.path]]）；以及文件系统中的对象，包括目录遍历（[[fs.class.directory.iterator]]）、状态查询、复制、改名、删除、权限等操作（[[fs.op.funcs]]）。读写文件内容不归它管，那是文件流（[[file.streams]]）的事。

本页讲贯穿整个库的规则：术语、一致性、竞争、错误报告和枚举类型。

## 文件、目录和链接 [fs.general]

¶1–¶3 **文件系统**（file system）是文件及其属性的集合。**文件**（file）是文件系统中保存用户或系统数据的对象，可读、可写或两者兼有，具有类型等属性。文件类型包括普通文件和目录，实现还可以支持其他类型，例如符号链接。

¶4 **目录**（directory）是一种文件，它是目录项的容器，每个目录项记录另一个文件的信息。一个目录的父目录既包含它的目录项，又在它里面以 `..` 表示；其他文件的父目录就是包含其目录项的目录。

¶5 **链接**（link）把一个文件名关联到一个文件，多个链接可以关联同一个文件。

- **硬链接**（hard link）指向一个已有的文件。最后一个硬链接被删除时，文件本身才被删除。标准的注把硬链接比作文件的共享所有权智能指针。
- **符号链接**（symbolic link）是一种文件类型，内容是一个字符串；路径解析遇到它时，改用这个字符串继续解析。注里把它比作文件的裸指针：它指向的文件不存在时，称为悬空（dangling）的符号链接。

这两个比喻对应着实际的行为：删除一个硬链接相当于引用计数减一；删除符号链接的目标之后，链接本身还在，只是悬空了。这也是 `status` 跟随符号链接、`symlink_status` 不跟随的原因（[[fs.op.funcs]]）。

## 以 POSIX 为参照 [fs.conformance]

[fs.conformance.general] ¶1 一致性以行为来规定。理想的行为并不总能实现，后面的条文考虑了这一点。

[fs.conform.9945] ¶1 很多行为通过引用 POSIX 来规定，实际怎样实现是未指定的。注里说明这是一条 as-if 规则：实现可以调用操作系统原生的 API，只要效果相同。所以条文里随处可见 "as if by POSIX `stat`" 这样的写法，Windows 上的实现用 Win32 API 完成同样的事。

¶2 实现应当提供 POSIX 定义的行为。与 POSIX 不同的行为必须写进文档；不能精确支持时，应在操作系统和文件系统的限制下尽量接近；连合理的行为都给不出时，必须按 [[fs.err.report]] 报告错误。所以使用者总能得到一个结果：要么操作成功，要么收到异常或错误码，不会是静默的错误结果。

¶3 实现不必提供某个文件系统本身不支持的行为。标准举的例子是 FAT：它不支持硬链接和符号链接，在 FAT 上创建它们时实现只需报告错误。

[fs.conform.os] ¶1 有些行为被规定为**依赖操作系统**（operating system dependent），取决于实际的操作系统；实现依赖哪个操作系统由实现定义。¶2 实现可以依赖一个操作系统模拟层（例如 Windows 上的 Cygwin 一类环境），而不是底层真正的操作系统。路径的原生字符类型、首选分隔符、什么算绝对路径，都属于这一类。

## 文件系统竞争 [fs.race.behavior]

!!! std
    Behavior is undefined if calls to functions provided by subclause [filesystems] introduce a file system race.

¶1 **文件系统竞争**（[[g:file-system-race|file system race]]）指多个线程、进程或计算机交错地访问和修改文件系统中的同一个对象。`<filesystem>` 的函数调用引入了文件系统竞争时，行为未定义 {{ub}}。

¶2 如果文件系统竞争的可能性使程序无法在调用前可靠地检查某个函数的前置条件，就不为这个函数规定前置条件。注里说明这是一条设计惯例：程序没办法事先检查的条件，不写成前置条件。

这条规则承认的是一个事实：文件系统是进程之外的共享状态，你检查到的状态在下一刻可能已经变了。由此有三点推论。

**先检查再操作不可靠。** `if (!exists(p)) create(p);`、`if (is_regular_file(p)) open(p);` 在检查和操作之间，别的进程可能已经修改了文件，这类缺陷称为 TOCTOU（time of check to time of use）。正确的做法是直接执行操作，再检查它的结果，就像开头的例子那样。

**很多函数没有前置条件。** `file_size(p)` 不要求 `p` 存在，不存在时报告错误；`remove(p)` 不要求 `p` 存在，不存在时返回 `false`。这都是 ¶2 的直接体现。

**按路径操作的接口防不住恶意竞争。** 条文说的是函数调用引入了竞争，但在多用户系统上，别的进程完全可能在你调用 `remove_all` 时往目录里放东西或换掉符号链接。标准对此不作保证，实现通常会报告错误或给出某个合理结果。以高权限处理别人可写的目录时，需要使用平台提供的、基于文件描述符的 API（如 POSIX 的 `openat`、`unlinkat`）。

## 字符类型 [fs.req]

¶1 `char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t` 统称**编码字符类型**（encoded character types）。¶2 名为 `EcharT` 的模板参数只在它是编码字符类型时参与重载决议。¶3 名为 `InputIterator` 的模板参数须满足 *Cpp17InputIterator*，值类型须是编码字符类型。

¶4 是一条注：编码字符类型都隐含了字符集和编码，`signed char` 和 `unsigned char` 没有，所以不在允许之列。这意味着不能直接用一段 `unsigned char` 字节构造 `path`，必须先说明它是什么编码，例如转换成 `char8_t`。

¶5 名为 `Allocator` 的模板参数须满足 *Cpp17Allocator*。

## 错误报告 [fs.err.report]

```cpp title="error-reporting.cpp" run ok
#include <cstdint>
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  std::error_code ec;
  auto sz = fs::file_size("no-such-file", ec);           // error_code 版本
  std::cout << (sz == static_cast<std::uintmax_t>(-1)) << ' ' << ec.message() << '\n';
  // 1 No such file or directory

  try {
    (void)fs::file_size("no-such-file");                 // 抛异常的版本
  } catch (const fs::filesystem_error& e) {
    std::cout << "path1=" << e.path1() << " code=" << e.code().value() << '\n';
    // path1="no-such-file" code=2（POSIX 的 ENOENT）
  }
}
```

¶1 库函数通常提供两个重载，一个抛异常，一个设置 `error_code`。注里说明了各自的适用场合：错误确实罕见、意味着严重故障时，用异常；错误是常态、不一定代表失败时（比如文件可能本来就不存在），用错误码，由程序自己决定怎样处理，甚至忽略。

¶2 没有 `error_code&` 参数的函数，除非另有规定：

- ¶2.1 底层操作系统调用出错、使函数无法完成其规定时，抛出 `filesystem_error`。只有一个 `path` 参数的函数把它作为异常的 `path1`；有两个的，第一个作为 `path1`，第二个作为 `path2`。异常中的 `error_code` 是具体的、依赖操作系统的错误。
- ¶2.2 分配存储失败按一般规则抛异常，即 `bad_alloc`（[[res.on.exception.handling]]）。
- ¶2.3 析构函数不抛异常。

¶3 有 `error_code&` 参数的函数，除非另有规定：底层调用出错时把错误写进这个参数，否则调用它的 `clear()`。

由此有两个细节：

- `error_code&` 版本每次都会写 `ec`，成功时清零，所以同一个 `ec` 可以反复使用，调用前不必手动清零。
- `error_code&` 版本不一定是 `noexcept`。`exists(p, ec)`、`file_size(p, ec)` 是 `noexcept` 的，但 `absolute(p, ec)`、`canonical(p, ec)`、`create_directories(p, ec)`、`copy(from, to, ec)`、`remove_all(p, ec)` 等不是：它们要构造新的 `path` 或遍历目录，可能需要分配内存。¶3 只规定了操作系统调用出错时怎样处理，分配失败不在其列；这些函数没有声明 `noexcept`，按 [[res.on.exception.handling]] 的一般规则，分配失败时抛出 `bad_alloc`。

## `filesystem_error` [fs.class.filesystem.error]

```cpp
class filesystem_error : public system_error {
public:
  filesystem_error(const string& what_arg, error_code ec);
  filesystem_error(const string& what_arg, const path& p1, error_code ec);
  filesystem_error(const string& what_arg, const path& p1, const path& p2, error_code ec);
  const path& path1() const noexcept;
  const path& path2() const noexcept;
  const char* what() const noexcept override;
};
```

[fs.class.filesystem.error.general] ¶1 这是 `<filesystem>` 的函数报告文件系统错误时抛出的异常类型。

[fs.filesystem.error.members] ¶1–¶4 三个构造函数分别保存零个、一个、两个路径。之后 `code() == ec`，`what()` 的结果包含 `what_arg`。¶5–¶6 `path1()`、`path2()` 返回保存的路径，没有保存时返回空路径。¶7 `what()` 的确切格式未指定，实现应当在其中包含 `system_error::what()` 的字符串和两个路径的原生格式。

它派生自 `system_error`，所以 `catch (const std::system_error&)` 能捕获它，`e.code()` 可以直接与 `std::errc::no_such_file_or_directory` 比较（[[syserr]]）。

## `<filesystem>` 概要 [fs.filesystem.syn]

`namespace std::filesystem` 中有：类 `path`、`filesystem_error`、`directory_entry`、`directory_iterator`、`recursive_directory_iterator`、`file_status`；结构 `space_info`（`capacity`、`free`、`available` 三个 `uintmax_t`）；下文的枚举类型；`file_time_type`，即 `chrono::time_point<chrono::file_clock>`（[[time.clock.file]]）；以及全部操作函数（[[fs.op.funcs]]）。`namespace std` 中有 `hash<filesystem::path>` 和 C++26 的 `formatter<filesystem::path, charT>`。

目录迭代器本身就是一个范围：它有非成员的 `begin` 和 `end`，并且概要把它声明为 `view` 和 `borrowed_range`：

```cpp
template<> inline constexpr bool ranges::enable_borrowed_range<filesystem::directory_iterator> = true;
template<> inline constexpr bool ranges::enable_view<filesystem::directory_iterator> = true;
// recursive_directory_iterator 同样
```

复制一个目录迭代器很便宜，副本共享底层的目录句柄；从临时迭代器得到的迭代器也不会悬垂。所以可以直接写 `fs::directory_iterator(".") | std::views::filter(...)`（[[fs.class.directory.iterator]]）。

¶1 实现应当让 `file_time_type` 的分辨率和范围反映操作系统中文件时间的分辨率和范围。

## 枚举类型 [fs.enum]

### `file_type` [fs.enum.file.type]

| 常量 | 含义 |
|---|---|
| `none` | 类型尚未确定，或者确定类型时出了错 |
| `not_found` | 文件不存在。确定类型时，文件不存在不算错误 |
| `regular`、`directory`、`symlink` | 普通文件、目录、符号链接 |
| `block`、`character`、`fifo`、`socket` | 块设备、字符设备、FIFO（管道）、套接字 |
| 实现定义的常量 | 支持其他文件类型的实现须提供 |
| `unknown` | 文件存在，但类型无法确定 |

¶1 各常量的值互不相同。`none`、`not_found`、`unknown` 的区分是 `status()` 设计的核心：分别表示出了错、连存在与否都不知道，确定不存在，确定存在但不知道是什么（[[fs.op.funcs]]）。

### `copy_options` [fs.enum.copy.opts]

¶1 `copy_options` 是位掩码类型，常量按选项组划分。`none` 表示空位掩码，为了说明在每组都列出，实际只有一个定义；其他常量各占一位。

| 选项组 | 常量 |
|---|---|
| `copy_file` 遇到已存在的目标 | `none`（默认，报错）、`skip_existing`（不覆盖也不报错）、`overwrite_existing`（覆盖）、`update_existing`（目标比源旧时覆盖） |
| `copy` 对子目录 | `none`（默认，不复制子目录）、`recursive`（递归复制） |
| `copy` 对符号链接 | `none`（默认，跟随）、`copy_symlinks`（复制链接本身）、`skip_symlinks`（忽略） |
| `copy` 的复制形式 | `none`（默认，复制内容）、`directories_only`（只复制目录结构）、`create_symlinks`（创建符号链接；除非目标在当前目录，源路径必须是绝对路径）、`create_hard_links`（创建硬链接） |

`copy` 和 `copy_file` 要求每组至多设置一个选项（[[fs.op.funcs]]）。

### `perms` 与 `perm_options` [fs.enum.perms]、[fs.enum.perm.opts]

`perms` 是位掩码类型，值与 POSIX 的权限位一一对应：

| 名字 | 八进制 | POSIX 宏 |
|---|---|---|
| `owner_read`、`owner_write`、`owner_exec`、`owner_all` | 0400、0200、0100、0700 | `S_IRUSR`、`S_IWUSR`、`S_IXUSR`、`S_IRWXU` |
| `group_read` … `group_all` | 040、020、010、070 | `S_IRGRP` … `S_IRWXG` |
| `others_read` … `others_all` | 04、02、01、07 | `S_IROTH` … `S_IRWXO` |
| `all` | 0777 | |
| `set_uid`、`set_gid`、`sticky_bit` | 04000、02000、01000 | `S_ISUID`、`S_ISGID`、`S_ISVTX`（sticky 依赖操作系统） |
| `mask` | 07777 | |
| `none`、`unknown` | 0、0xFFFF | `unknown` 表示权限未知，例如构造 `file_status` 时没有指定权限 |

`perm_options` 决定 `permissions(p, prms, opts)` 怎样使用 `prms`：`replace` 替换，`add` 按位或，`remove` 清除这些位，`nofollow` 作用于符号链接本身而不是其目标。前三个必须恰好出现一个（[[fs.op.funcs]]）。

```cpp title="perms.cpp" run ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  std::ofstream("p.txt") << "x";
  auto show = [] {
    auto p = fs::status("p.txt").permissions();
    std::cout << std::oct << static_cast<unsigned>(p) << std::dec << '\n';
  };
  using enum fs::perms;
  fs::permissions("p.txt", owner_read | owner_write | group_read,
                  fs::perm_options::replace);
  show();                                                         // 640
  fs::permissions("p.txt", others_read, fs::perm_options::add);
  show();                                                         // 644
  fs::permissions("p.txt", group_read | others_read, fs::perm_options::remove);
  show();                                                         // 600
  fs::remove("p.txt");
}
```

### `directory_options` [fs.enum.dir.opts]

| 名字 | 含义 |
|---|---|
| `none` | 默认：递归时不进入指向目录的符号链接；权限被拒绝算错误 |
| `follow_directory_symlink` | 递归时进入指向目录的符号链接 |
| `skip_permission_denied` | 跳过因权限被拒绝而无法打开的目录，不报错 |

### `path::format` [fs.enum.path.format]

¶1 构造 `path` 时可以说明字符序列的格式：`native_format` 是原生路径格式，`generic_format` 是通用路径格式，`auto_format` 由实现决定怎样解释，实现可以检查内容来判断。*Recommended practice*：POSIX 系统上原生格式与通用格式相同，字符序列应当始终按同一种方式解释。两种格式的区别见 [[fs.class.path]]。

## 思考题

!!! question "思考题 1"
    `if (fs::exists(p)) fs::remove(p);` 有什么问题？怎样写更好？

<details markdown="1">
<summary>答案</summary>

有两个问题。其一是 TOCTOU：`exists` 返回 `true` 之后、`remove` 之前，文件可能已被别的进程删除，按 [[fs.race.behavior]] 这是文件系统竞争（实践中 `remove` 会返回 `false` 或报告错误）。其二是多余：`remove(p)` 对不存在的文件返回 `false`，不算错误（[[fs.op.remove]]）。直接写 `fs::remove(p);`，需要时再用返回值区分删除了和本来就没有。
</details>

!!! question "思考题 2"
    调用 `fs::canonical(p, ec)` 时内存耗尽，会怎样？

<details markdown="1">
<summary>答案</summary>

抛出 `bad_alloc`。`canonical(const path&, error_code&)` 没有声明为 `noexcept`（[[fs.filesystem.syn]]），而 [[fs.err.report#3]] 只把操作系统调用产生的错误写进 `error_code&`，分配失败仍按 [[res.on.exception.handling]] 的一般规则以异常报告。
</details>
