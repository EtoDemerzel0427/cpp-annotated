---
title: 文件系统库
summary: std::filesystem 导读——文件、目录、硬链接与符号链接的定义；以 POSIX 为参照的一致性规则（"as if"、必须记录偏差、无法合理实现时报告错误）；文件系统竞争是未定义行为及其对 TOCTOU 的含义；编码字符类型的要求；<filesystem> 概要（目录迭代器是 view 和 borrowed_range）；抛 filesystem_error 与设置 error_code 两套错误报告；filesystem_error；file_type/copy_options/perms/perm_options/directory_options 等枚举
status: done
covers: fs.general, fs.conformance, fs.conformance.general, fs.conform.9945, fs.conform.os, fs.race.behavior, fs.req, fs.filesystem.syn, fs.err.report, fs.class.filesystem.error, fs.class.filesystem.error.general, fs.filesystem.error.members, fs.enum, fs.enum.path.format, fs.enum.file.type, fs.enum.copy.opts, fs.enum.perms, fs.enum.perm.opts, fs.enum.dir.opts
since: c++17
related: fs.class.path, fs.class.directory.iterator, fs.op.funcs, file.streams, syserr, time.clock.file, input.output
tags: 标准库, filesystem, 文件系统, TOCTOU, error_code
updated: 2026-10-18
---

`<filesystem>`（C++17，源自 Boost.Filesystem 和 Filesystem TS）处理两类事情：

1. **路径**——`std::filesystem::path`，一个只关心"字面与语法"的值类型（[[fs.class.path]]）；
2. **文件系统中的对象**——目录遍历（[[fs.class.directory.iterator]]）、状态查询、复制、移动、删除、权限等操作函数（[[fs.op.funcs]]）。

它不读写文件**内容**，那是文件流（[[file.streams]]）的事。本页覆盖 [filesystems] 中贯穿所有组件的"总则"：术语、一致性、竞争、错误报告和枚举类型。

## 术语（[fs.general]）

- ¶1：本节描述对文件系统及其组成部分（路径、普通文件、目录）的操作。
- ¶2：**文件系统**（file system）是文件及其属性的集合。
- ¶3：**文件**（file）是文件系统中保存用户或系统数据的对象，可以读、写或两者兼有，具有包括类型在内的属性。文件类型包括普通文件和目录；实现可以支持其他类型，如符号链接。
- ¶4：**目录**（directory）是文件系统中作为目录项容器的文件，目录项包含其他文件（可能包括其他目录）的信息。目录的**父目录**既包含该目录的目录项，又在该目录中以 dot-dot 文件名（`..`）表示；其他类型文件的父目录是包含其目录项的目录。
- ¶5：**链接**（link）把一个文件名与一个文件关联，多个链接可以关联同一个文件。**硬链接**（hard link）是指向已有文件的链接；最后一个硬链接被删除时文件本身被删除。注：硬链接可以看作文件的**共享所有权智能指针**。**符号链接**（symbolic link）是一种文件类型：在路径名解析中遇到它时，用它保存的字符串修改解析过程。注：符号链接可以看作文件的**裸指针**；它指向的文件不存在时称为"悬空"（dangling）符号链接。

这两个比喻非常贴切：删除一个硬链接只是"引用计数减一"；删除符号链接指向的目标后，符号链接本身还在，只是悬空了——这正是 `status` 与 `symlink_status` 区别的来源（[[fs.op.funcs]]）。

## 一致性（[fs.conformance]）

### 以 POSIX 为参照（[fs.conform.9945]）

[fs.conformance.general] ¶1：一致性以行为来规定；理想的行为并不总能实现，各子条款考虑了这一点。

[fs.conform.9945]：

- ¶1：有些行为通过引用 POSIX 来规定，实际如何实现是未指定的。注：这构成一条"as if"规则，允许实现调用原生操作系统 API 或其他 API。——于是条文中大量出现"as if by POSIX `stat`"、"as if by POSIX `rename`"。
- ¶2：实现**应当**提供 POSIX 定义的行为；与 POSIX 不同的行为**必须写入文档**；不能精确支持 POSIX 行为的，应在实际操作系统和文件系统的限制下尽量接近；**无法提供任何合理行为时，必须按 [fs.err.report] 报告错误**。注：所以用户可以依赖"要么抛异常、要么设置错误码"，而不是得到静默的错误结果。
- ¶3：不要求实现提供特定文件系统不支持的行为。例：FAT 文件系统不支持硬链接、符号链接等功能，实现不必在 FAT 上支持它们，但必须报告错误。

### 依赖操作系统的行为（[fs.conform.os]）

¶1：规定为"**依赖操作系统**"（operating system dependent）的行为取决于操作系统的行为与特性；实现依赖的是哪个操作系统，由实现定义。¶2：允许实现依赖操作系统模拟层（如 Windows 上的 Cygwin 一类环境），而不是实际的底层操作系统。

"依赖操作系统"是 [filesystems] 独有的一类行为：`path::value_type`、`preferred_separator`、何为绝对路径、文件名允许哪些字符等都属此类。

### 文件系统竞争（[fs.race.behavior]）

!!! std
    A file system race is the condition that occurs when multiple threads, processes, or computers interleave access and modification of the same object within a file system. Behavior is undefined if calls to functions provided by subclause [filesystems] introduce a file system race.

¶1：**文件系统竞争**（[[g:file-system-race]]）是多个线程、进程或计算机交错地访问和修改文件系统中同一对象的情形。若调用 [filesystems] 中的函数**引入**了文件系统竞争，行为未定义 {{ub}}。

¶2：若文件系统竞争的可能性使程序在调用某函数之前检查其前置条件变得不可靠，就不为该函数规定 *Preconditions*。注：作为设计惯例，当程序无法合理地在调用前检测前置条件时，就不规定前置条件。

这条规定的分量很重。它不是说"并发访问文件会出错"，而是在标准层面承认：文件系统是进程外的共享状态，库**无法**保证你看到的状态在下一刻仍然成立。实际后果：

1. **检查后使用（TOCTOU）是不可靠的。** `if (!exists(p)) create(p);`、`if (is_regular_file(p)) open(p);` 中间可能被别的进程插入修改。正确的做法是**直接执行操作并检查它的结果**：

```cpp title="no-toctou.cpp" ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  const fs::path dir = "work", lock = "work/app.lock";

  // 不要先 exists() 再 create_directory()：create_directory 自己会报告"已存在"（返回 false，不报错）
  std::error_code ec;
  bool created = fs::create_directory(dir, ec);
  std::cout << "created=" << created << " ec=" << ec.value() << '\n';      // created=1 ec=0

  // 独占创建：检查与创建是同一个原子操作（C++23 noreplace，即 fopen 的 "x"）
  std::ofstream first(lock, std::ios_base::out | std::ios_base::noreplace);
  std::ofstream second(lock, std::ios_base::out | std::ios_base::noreplace);
  std::cout << "first=" << first.is_open() << " second=" << second.is_open() << '\n';  // 1 0

  first.close();
  // remove 对不存在的文件返回 false 而不是报错：同样不需要先检查
  std::cout << "removed=" << fs::remove(lock) << " again=" << fs::remove(lock) << '\n'; // 1 0
  fs::remove(dir);
}
```

2. **"引入"竞争的是你的程序还是别人？** 条文说的是"函数调用引入了文件系统竞争"。在多用户系统上，别的进程在你调用 `remove_all` 期间往目录里放文件，从字面上看你的调用就处于竞争之中。所以实践中这条规则的意思是：标准对此类情形**不作任何保证**；实现通常会返回错误或给出某个合理结果，但不能依赖。安全敏感的代码（如以高权限删除用户可写目录）需要使用平台提供的、基于文件描述符的 API（如 `openat`/`unlinkat`），`<filesystem>` 的按路径接口无法防御符号链接替换攻击。

3. **没有前置条件的函数很多**：`file_size(p)` 不要求 `p` 存在，而是在不存在时**报告错误**；`remove(p)` 不要求 `p` 存在，而是返回 `false`。这都是 ¶2 的直接体现。

## 要求（[fs.req]）

- ¶1：`char`、`wchar_t`、`char8_t`、`char16_t`、`char32_t` 统称**编码字符类型**（encoded character types）。
- ¶2：名为 `EcharT` 的模板参数，只有在它是编码字符类型之一时才参与重载决议。
- ¶3：名为 `InputIterator` 的模板参数须满足 *Cpp17InputIterator*，值类型须是编码字符类型。
- ¶4（注）：使用编码字符类型意味着关联了字符集和编码；`signed char` 和 `unsigned char` 没有隐含的字符集和编码，所以**不在**允许之列。
- ¶5：名为 `Allocator` 的模板参数须满足 *Cpp17Allocator*。

¶4 意味着 `path(std::vector<unsigned char>{...}.begin(), ...)` 不能编译——这是有意的：字节序列应先明确它是什么编码。

## `<filesystem>` 概要（[fs.filesystem.syn]）

`namespace std::filesystem` 中：

- 类：`path`、`filesystem_error`、`directory_entry`、`directory_iterator`、`recursive_directory_iterator`、`file_status`；
- 非成员：`swap(path&, path&)`、`hash_value(const path&)`、两种目录迭代器的 `begin`/`end`；
- `struct space_info { uintmax_t capacity, free, available; }`，带默认的 `operator==`；
- 枚举：`file_type`、`perms`、`perm_options`、`copy_options`、`directory_options`；
- `using file_time_type = chrono::time_point<chrono::file_clock>;`（[[time.clock.file]]）；
- 全部操作函数（[[fs.op.funcs]]），绝大多数成对出现：一个抛异常、一个接受 `error_code&`。

`namespace std` 中：`formatter<filesystem::path, charT>` {{c++26}} 与 `hash<filesystem::path>`。

`namespace std::ranges` 中：

```cpp
template<> inline constexpr bool enable_borrowed_range<filesystem::directory_iterator> = true;
template<> inline constexpr bool enable_borrowed_range<filesystem::recursive_directory_iterator> = true;
template<> inline constexpr bool enable_view<filesystem::directory_iterator> = true;
template<> inline constexpr bool enable_view<filesystem::recursive_directory_iterator> = true;
```

目录迭代器**本身就是一个范围**（有非成员 `begin`/`end`），而且被声明为 `view` 和 `borrowed_range`：复制一个目录迭代器很便宜（共享底层的目录句柄），从临时迭代器得到的迭代器也不会悬垂。于是可以直接写 `for (auto& e : fs::directory_iterator(".") | std::views::filter(...))`（[[fs.class.directory.iterator]]）。

¶1：实现应当保证 `file_time_type` 的分辨率和范围反映操作系统相关的文件时间值的分辨率和范围。

## 错误报告（[fs.err.report]）

¶1：文件系统库函数通常提供两个重载：一个抛异常报告文件系统错误，另一个设置 `error_code`。注：这支持两种常见用法——错误确实是异常情况、意味着严重故障时，抛异常合适；错误是常规情况、不一定代表失败时（例如"文件可能不存在"），返回错误码最合适，可以由应用自行处理甚至忽略。

¶2：**没有** `error_code&` 参数的函数，除非另有规定：

- ¶2.1：实现对操作系统或其他底层 API 的调用产生了使函数无法满足其规格的错误时，抛出 `filesystem_error`。单个 `path` 参数的函数把该参数传给 `filesystem_error` 的单 `path` 构造函数；两个 `path` 参数的，第一个作为 `path1`、第二个作为 `path2`。`error_code` 实参按具体的、依赖操作系统的错误设置。
- ¶2.2：分配存储失败按 [[res.on.exception.handling]] 抛异常（即 `bad_alloc`）。
- ¶2.3：析构函数不抛异常。

¶3：**有** `error_code&` 参数的函数，除非另有规定：底层 API 调用产生错误时，按具体错误设置该 `error_code&`；**否则调用它的 `clear()`**。

两个细节：

- `error_code&` 重载**每次都会写** `ec`：成功时清零。所以可以复用同一个 `ec` 变量，不必在调用前手动清零。
- `error_code&` 重载**不一定是 `noexcept`**。查看概要：`exists(p, ec)`、`file_size(p, ec)` 等是 `noexcept` 的，但 `absolute(p, ec)`、`canonical(p, ec)`、`create_directories(p, ec)`、`copy(from, to, ec)`、`remove_all(p, ec)` 等不是——它们要构造 `path` 或遍历目录，可能抛 `bad_alloc`（¶2.2 仍然适用）。

```cpp title="error-reporting.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  std::error_code ec;
  auto sz = fs::file_size("no-such-file", ec);           // 不抛异常的重载
  std::cout << (sz == static_cast<std::uintmax_t>(-1)) << ' ' << ec.message() << '\n';
  // 1 No such file or directory

  try {
    (void)fs::file_size("no-such-file");                 // 抛 filesystem_error
  } catch (const fs::filesystem_error& e) {
    std::cout << "path1=" << e.path1() << " code=" << e.code().value() << '\n';
    // path1="no-such-file" code=2（POSIX ENOENT）
  }
}
```

## `filesystem_error`（[fs.class.filesystem.error]）

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

- [fs.class.filesystem.error.general] ¶1：定义 [filesystems] 中函数报告文件系统错误时抛出的异常类型。
- [fs.filesystem.error.members] ¶1–¶4：构造函数保存零、一或两个路径；后条件包括 `code() == ec`、`path1()`/`path2()` 引用保存的副本（没有则为空路径），以及 `what()` 的结果**包含** `what_arg`。
- ¶5–¶6：`path1()`/`path2()` 返回保存的路径副本，没有则返回空路径。
- ¶7：`what()` 返回一个包含 `what_arg` 的 NTBS，确切格式未指定；实现应当把 `system_error::what()` 的字符串以及 `path1`、`path2` 的原生格式路径名包含进去。

因为派生自 `system_error`，`catch (const std::system_error&)` 能捕获它，`e.code()` 可以与 `std::errc::no_such_file_or_directory` 比较（[[syserr]]）。

## 枚举类型（[fs.enum]）

### `path::format`（[fs.enum.path.format]）

| 名字 | 含义 |
|---|---|
| `native_format` | 原生路径名格式 |
| `generic_format` | 通用路径名格式 |
| `auto_format` | 字符序列格式的解释方式由实现定义，实现可以检查内容来决定 |

*Recommended practice*：在 POSIX 系统上原生格式与通用格式等价，字符序列应始终以同一种方式解释。详见 [[fs.class.path]]。

### `file_type`（[fs.enum.file.type]）

| 常量 | 含义 |
|---|---|
| `none` | 文件类型尚未确定，或确定类型时**发生了错误** |
| `not_found` | 伪类型，表示**文件不存在**。注：文件不存在在确定文件类型时**不被视为错误** |
| `regular`、`directory`、`symlink`、`block`、`character`、`fifo`、`socket` | 普通文件、目录、符号链接、块设备、字符设备、FIFO/管道、套接字 |
| 实现定义的常量 | 支持其他文件类型的实现须提供 |
| `unknown` | 文件存在，但类型无法确定 |

¶1：各常量的值互不相同。`none`、`not_found`、`unknown` 三者的区分是 `status()` 设计的核心：分别对应"出错了，连是否存在都不知道"、"确定不存在"、"确定存在但不知道是什么"（[[fs.op.funcs]]）。

### `copy_options`（[fs.enum.copy.opts]）

¶1：位掩码类型，常量分为若干**选项组**；`none` 表示空位掩码，在每组中列出只是为了说明，实现只提供一个定义；其他常量各代表一个不同的位。

| 选项组 | 常量 |
|---|---|
| `copy_file` 遇到已存在的目标 | `none`（默认，报错）、`skip_existing`（不覆盖、不报错）、`overwrite_existing`（覆盖）、`update_existing`（目标较旧时覆盖） |
| `copy` 对子目录 | `none`（默认，不复制子目录）、`recursive`（递归复制） |
| `copy` 对符号链接 | `none`（默认，跟随）、`copy_symlinks`（复制链接本身）、`skip_symlinks`（忽略） |
| `copy` 的复制形式 | `none`（默认，复制内容）、`directories_only`（只复制目录结构）、`create_symlinks`（创建符号链接；源路径须为绝对路径，除非目标在当前目录）、`create_hard_links`（创建硬链接） |

`copy` 与 `copy_file` 都要求**每组至多设置一个**选项（[[fs.op.funcs]]）。

### `perms`（[fs.enum.perms]）

位掩码类型，值与 POSIX 的权限位一一对应：

| 名字 | 八进制 | POSIX 宏 |
|---|---|---|
| `none` | 0 | |
| `owner_read` / `owner_write` / `owner_exec` / `owner_all` | 0400 / 0200 / 0100 / 0700 | `S_IRUSR` / `S_IWUSR` / `S_IXUSR` / `S_IRWXU` |
| `group_read` / `group_write` / `group_exec` / `group_all` | 040 / 020 / 010 / 070 | `S_IRGRP` … `S_IRWXG` |
| `others_read` / `others_write` / `others_exec` / `others_all` | 04 / 02 / 01 / 07 | `S_IROTH` … `S_IRWXO` |
| `all` | 0777 | |
| `set_uid` / `set_gid` / `sticky_bit` | 04000 / 02000 / 01000 | `S_ISUID` / `S_ISGID` / `S_ISVTX`（sticky 依赖操作系统） |
| `mask` | 07777 | |
| `unknown` | 0xFFFF | 权限未知（如构造 `file_status` 时未指定权限） |

### `perm_options`（[fs.enum.perm.opts]）

`permissions(p, prms, opts)` 的动作：`replace`（用 `prms` 替换）、`add`（按位或）、`remove`（按位与 `~prms`）、`nofollow`（作用于符号链接本身而不是其目标）。前三者必须**恰好**出现一个（[[fs.op.funcs]]）。

```cpp title="perms.cpp" ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  std::ofstream("p.txt") << "x";
  auto show = [] {
    std::cout << std::oct << static_cast<unsigned>(fs::status("p.txt").permissions()) << std::dec << '\n';
  };
  fs::permissions("p.txt", fs::perms::owner_read | fs::perms::owner_write | fs::perms::group_read,
                  fs::perm_options::replace);
  show();                                                                        // 640
  fs::permissions("p.txt", fs::perms::others_read, fs::perm_options::add);
  show();                                                                        // 644
  fs::permissions("p.txt", fs::perms::group_read | fs::perms::others_read, fs::perm_options::remove);
  show();                                                                        // 600
  fs::remove("p.txt");
}
```

### `directory_options`（[fs.enum.dir.opts]）

| 名字 | 含义 |
|---|---|
| `none` | 默认：跳过目录符号链接（递归时不进入），权限被拒绝是错误 |
| `follow_directory_symlink` | 递归时跟随目录符号链接 |
| `skip_permission_denied` | 跳过因权限被拒绝而无法访问的目录，不报错 |

## 思考题

<details markdown="1">
<summary>1. <code>if (fs::exists(p)) fs::remove(p);</code> 有什么问题？怎么写更好？</summary>

两个问题。其一是 TOCTOU：`exists` 返回 `true` 之后、`remove` 之前，文件可能已被别的进程删除；按 [[fs.race.behavior]]，函数调用引入文件系统竞争时行为未定义（实践中 `remove` 会报告错误或返回 `false`）。其二是多余：`remove(p)` 对不存在的文件返回 `false`，"不存在不是错误"（[[fs.op.remove]]）。直接写 `fs::remove(p);`，需要时再用返回值区分"删了"与"本来就没有"。
</details>

<details markdown="1">
<summary>2. 调用 <code>fs::canonical(p, ec)</code> 时，内存耗尽会怎样？</summary>

抛出 `bad_alloc`。`canonical(const path&, error_code&)` 没有被声明为 `noexcept`（[[fs.filesystem.syn]]），[[fs.err.report]] ¶2.2 规定分配失败按一般规则抛异常；`error_code&` 只用于报告**操作系统 API** 产生的错误。
</details>

## 小结

| 规则 | 要点 |
|---|---|
| 术语 | 硬链接≈共享所有权指针，符号链接≈裸指针（可以悬空） |
| 一致性 | 以 POSIX 为参照的 as-if 规则；偏差须写入文档；无法合理实现时必须报错 |
| 竞争 | 函数调用引入文件系统竞争是 UB；可能被竞争破坏的条件不写成前置条件 → 不要先检查再操作 |
| 字符类型 | 只接受 `char`/`wchar_t`/`char8_t`/`char16_t`/`char32_t`，不接受 `signed`/`unsigned char` |
| 错误 | 抛 `filesystem_error`（带 `path1`/`path2`）或设置 `error_code&`（成功时 `clear()`）；`ec` 重载不一定 `noexcept` |
| `file_type` | `none`＝出错、`not_found`＝不存在（不算错误）、`unknown`＝存在但类型不明 |
