---
title: 文件系统操作函数与 file_status
summary: <filesystem> 中访问文件系统的非成员函数：status 与 symlink_status、exists 和 is_* 的错误报告差异、absolute/canonical/weakly_canonical/relative 的区别、创建、复制、删除、重命名、权限，以及 current_path 这个进程级的全局状态。
status: done
covers: *, fs.class.file.status, fs.class.file.status.general, fs.file.status.cons, fs.file.status.obs, fs.file.status.mods
since: c++17
related: filesystems, fs.class.path, fs.class.directory.iterator, file.streams, time.clock.file, syserr
tags: 标准库, filesystem, 文件操作, status, TOCTOU
updated: 2026-10-19
---

!!! tldr
    - 任何文件系统操作都可能失败，连 `exists(p)` 也会抛异常；每个函数都有一个抛 `filesystem_error` 的版本和一个接受 `error_code&` 的版本。
    - `status` 跟随符号链接，`symlink_status` 不跟随；对悬空链接，`exists(p)` 为假，但这个名字确实被占用了。
    - 文件不存在时，`exists(p, ec)` 清除 `ec`，`is_regular_file(p, ec)` 却把 `ec` 设为错误。
    - 只有 `canonical` 要求路径存在；`weakly_canonical` 解析存在的前缀，其余部分只做字面规范化；`absolute` 只是拼上当前目录。
    - `create_directory` 遇到已有目录返回 `false` 而不报错；`remove` 遇到不存在的文件也不报错；`copy` 不加 `recursive` 只复制一层。

## 任何操作都可能失败 [fs.op.funcs.general]

¶1 本节的函数查询或修改外部存储中的文件，包括目录。第 2 段的注提醒，硬件故障、网络故障、文件系统竞争（[[fs.race.behavior]]）等错误在文件系统操作中经常发生，所以任何一个操作函数，无论看起来多么无害，都可能遇到错误。比如对一个所在目录没有搜索权限的路径，`exists(p)` 也会抛异常。

几乎每个函数都成对出现。按 [[filesystems]] 的 [fs.err.report]，不带 `error_code&` 的版本出错时抛 `filesystem_error`；带 `error_code& ec` 的版本出错时设置 `ec`，并返回一个约定的值（通常是空路径、`false` 或 `static_cast<uintmax_t>(-1)`），成功时清除 `ec`。

## 文件状态

### `file_status` [fs.class.file.status]

```cpp
class file_status {
public:
  file_status() noexcept : file_status(file_type::none) {}
  explicit file_status(file_type ft, perms prms = perms::unknown) noexcept;
  file_type type() const noexcept;        void type(file_type) noexcept;
  perms permissions() const noexcept;     void permissions(perms) noexcept;
  friend bool operator==(const file_status&, const file_status&) noexcept;
};
```

[fs.class.file.status.general] ¶1 `file_status` 保存一个文件的类型和权限，是一个简单的值类型（[fs.file.status.cons]、[fs.file.status.obs]、[fs.file.status.mods]）。把两者放在一起，是因为一次 `stat` 就能同时得到它们；之后 `is_directory(s)`、`exists(s)` 等接受 `file_status` 的重载直接读这个值，不再访问文件系统。

### `status` 与 `symlink_status`

```cpp run title="status-vs-symlink.cpp" ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

const char* name(fs::file_type t) {
  switch (t) {
    case fs::file_type::not_found: return "not_found";
    case fs::file_type::regular:   return "regular";
    case fs::file_type::symlink:   return "symlink";
    default:                       return "other";
  }
}

int main() {
  fs::path d = "st_demo";
  fs::remove_all(d);
  fs::create_directory(d);
  std::ofstream(d / "real.txt") << "x";
  fs::create_symlink("real.txt", d / "good_link");
  fs::create_symlink("gone.txt", d / "dangling");

  for (auto n : {"real.txt", "good_link", "dangling", "nope"}) {
    fs::path p = d / n;
    std::cout << n << ": " << name(fs::status(p).type()) << ' '
              << name(fs::symlink_status(p).type()) << ' '
              << fs::exists(p) << '\n';
  }
  // real.txt:  regular   regular   1
  // good_link: regular   symlink   1
  // dangling:  not_found symlink   0
  // nope:      not_found not_found 0
  fs::remove_all(d);
}
```

[fs.op.status] ¶4 `status(p, ec)` 如同用 POSIX `stat` 获取 `p` 解析到的文件的属性。¶7 解析途中遇到符号链接时，继续按链接的内容解析，也就是跟随链接。¶6 返回值分两种情况：

- 底层调用成功时，按 `S_ISREG`、`S_ISDIR` 等宏得到 `regular`、`directory`、`block`、`character`、`fifo`、`socket`，实现定义的类型返回相应常量，其余返回 `unknown`，权限取 `st_mode & perms::mask`（¶5）。
- 底层调用出错时，`ec` 设为该错误。如果错误表明路径中某个元素不存在，返回 `not_found`；如果路径能解析但属性无法确定，返回 `unknown`；否则返回 `none`。注 3 解释了这三者的区别：确知不存在、存在但属性不明、连是否存在都无法知道。

¶1–¶3 不带 `ec` 的 `status(p)` 只在结果是 `none` 时抛异常。第 3 段的注强调，`not_found` 和 `unknown` 不算失败，所以 `status("no-such-file")` 正常返回 `file_type::not_found`。[fs.op.status.known] ¶1 `status_known(s)` 就是 `s.type() != file_type::none`。

[fs.op.symlink.status] ¶1 `symlink_status` 与 `status` 相同，只是如同用 POSIX `lstat`。¶3 `p` 本身是符号链接时返回 `file_type::symlink`，¶5 解析到这里就停止，不跟随。

!!! pitfall "悬空链接与 `exists`"
    上例中 `dangling` 指向一个不存在的文件。`exists` 用的是 `status`，跟随链接后找不到目标，于是返回 `false`。但目录里确实有这个名字，再用它 `create_symlink` 会失败。要判断一个名字是否被占用，用 `exists(fs::symlink_status(p))`。

### `exists` 与 `is_*`

| 函数 | 规定 |
|---|---|
| `exists(s)` | [fs.op.exists] ¶1 `status_known(s) && s.type() != file_type::not_found` |
| `exists(p)`、`exists(p, ec)` | ¶2–¶4 取 `s = status(p)`（或 `status(p, ec)`）；带 `ec` 的版本在 `status_known(s)` 时清除 `ec`；返回 `exists(s)` |
| `is_regular_file(s)` 等 | `s.type() == file_type::regular`；`directory`、`symlink`、`block`、`character`、`fifo`、`socket` 同理 |
| `is_regular_file(p, ec)` | [fs.op.is.regular.file] ¶4–¶5 如同 `status(p, ec)` 设置 `ec`；出错时返回 `false` |
| `is_other(s)` | [fs.op.is.other] ¶1 存在，但不是普通文件、目录或符号链接 |
| `is_symlink(p)` | [fs.op.is.symlink] ¶2 `is_symlink(symlink_status(p))`，唯一用 `symlink_status` 的 `is_*` |
| `is_empty(p)` | [fs.op.is.empty] ¶1 目录看 `directory_iterator(p) == directory_iterator()`，其他看 `file_size(p) == 0` |

`exists` 和 `is_*` 对待不存在的文件并不一样：

```cpp run title="exists-vs-is-ec.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  std::error_code ec;
  bool e = fs::exists("nope", ec);
  std::cout << e << ' ' << bool(ec) << '\n';  // 0 0
  bool r = fs::is_regular_file("nope", ec);
  std::cout << r << ' ' << bool(ec) << '\n';  // 0 1
}
```

`exists(p, ec)` 把不存在当作一个正常的答案：`not_found` 时 `status_known` 为真，于是 `ec` 被清除。`is_regular_file(p, ec)` 照搬 `status(p, ec)` 设置的 `ec`，[fs.op.is.regular.file] 第 4 段的注明确说 `none`、`not_found`、`unknown` 都会让 `ec` 成为错误值，所以 `ec` 留着 "No such file or directory"。用 `error_code` 版本时，要把出错和答案是否分开处理；需要细分时，直接调用 `status(p, ec)` 并检查 `type()`。

### 其他属性

| 函数 | 规定 | `ec` 版本出错时返回 |
|---|---|---|
| `equivalent(p1, p2)` | [fs.op.equivalent] ¶1 两者位于同一设备的同一位置即为同一实体（POSIX 上 `st_dev`、`st_ino` 都相等）；¶4 任一方不存在是错误 | `false` |
| `file_size(p)` | [fs.op.file.size] ¶1 不存在是错误；¶2 普通文件返回字节数，其他类型的结果由实现定义 {{impl}} | `uintmax_t(-1)` |
| `hard_link_count(p)` | [fs.op.hard.lk.ct] ¶1 硬链接数 | `uintmax_t(-1)` |
| `last_write_time(p)` | [fs.op.last.write.time] ¶1 最后修改时间，类型 `file_time_type` | `file_time_type::min()` |
| `last_write_time(p, t)` | ¶3 设置修改时间；第 5 段的注说明之后不保证 `last_write_time(p) == t`，文件系统的时间精度可能更粗 | — |
| `space(p)` | [fs.op.space] ¶1 如同 POSIX `statvfs`，得到 `capacity`、`free`、`available`，无法确定的成员为 `uintmax_t(-1)`；¶3 `available` 可能小于 `free`（有空间保留给特权用户） | 全部 `uintmax_t(-1)` |

`file_time_type` 是 `chrono::time_point<chrono::file_clock>`（[[time.clock.file]]）。`file_clock` 的纪元未指定，要转换成系统时间，用 `clock_cast<system_clock>` 或 `file_clock::to_sys`。

## 把路径变成绝对路径

```cpp run title="resolve.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::create_directories("cz/real/sub");
  fs::create_directory_symlink("real", "cz/link");
  fs::path p = "cz/link/sub/../sub/./not-yet/file.txt";
  auto here = fs::current_path();
  std::cout << fs::absolute(p).lexically_relative(here) << '\n';
  // "cz/link/sub/../sub/./not-yet/file.txt"
  std::cout << fs::weakly_canonical(p).lexically_relative(here) << '\n';
  // "cz/real/sub/not-yet/file.txt"
  std::error_code ec;
  (void)fs::canonical(p, ec);
  std::cout << ec.message() << '\n';  // No such file or directory
  fs::remove_all("cz");
}
```

`absolute` 原样保留了 `..`、`.` 和符号链接；`weakly_canonical` 解析了存在的前缀 `cz/link/sub`（`link` 换成了 `real`），然后接上不存在的 `not-yet/file.txt`；`canonical` 因为路径不存在而报错。

| 函数 | 访问文件系统 | 要求存在 | 解析符号链接 | 结果 |
|---|---|---|---|---|
| `absolute(p)` | 应当不 | 否 | 否 | 绝对路径，不一定规范 |
| `canonical(p)` | 是 | 是 | 是 | 绝对路径，没有符号链接、`.`、`..` |
| `weakly_canonical(p)` | 是 | 否 | 只对存在的前缀 | 规范形式 |
| `relative(p, base)` | 是 | 否 | 是 | `weakly_canonical(p).lexically_relative(weakly_canonical(base))` |
| `proximate(p, base)` | 是 | 否 | 是 | 同上，改用 `lexically_proximate` |
| `p.lexically_normal()` 等 | 否 | 否 | 否 | 见 [[fs.class.path]] |

- [fs.op.absolute] ¶1 按操作系统的规则组合出指向同一位置的绝对路径。第 6 段的注强烈建议实现不查询外部存储，也不把路径不存在当作错误。第 7 段的例子：POSIX 上 `absolute(p)` 就是 `current_path() / p`，Windows 上可能等同于 `GetFullPathNameW`。第 5 段的注建议，需要解析符号链接时考虑 `canonical`。
- [fs.op.canonical] ¶1–¶2 转换为不含符号链接、dot、dot-dot 的绝对路径，与 `absolute(p)` 指向同一个对象。¶4 `p` 不存在是错误。
- [fs.op.weakly.canonical] ¶1 用 `status` 找出 `p` 中存在的最长前缀，对它调用 `canonical`，再用 `/=` 接上其余元素。¶2 结果是规范形式。
- [fs.op.relative]、[fs.op.proximate] ¶3 的定义如上表；`base` 默认是 `current_path()`。

### 当前目录与临时目录

[fs.op.current.path] ¶1 `current_path()` 返回当前工作目录的绝对路径，如同 POSIX `getcwd`。¶3 当前工作目录与进程关联，是解析相对路径的起点。¶5–¶6 `current_path(p)` 如同 POSIX `chdir`，之后 `equivalent(p, current_path())`。

第 4 段和第 8 段的注都警告：在许多操作系统上，当前路径是一个危险的全局变量，可能被第三方库、系统库函数或另一个线程意外改变。

!!! pitfall "多线程程序中不要调用 `current_path(p)`"
    工作目录由整个进程共享。一个线程调用 `current_path(p)` 之后，其他线程所有以相对路径进行的文件操作，包括 `std::ifstream("x.txt")`，都会解析到新目录下。标准库无法替你同步这个外部状态。库代码应当接受绝对路径或显式的基准目录，而不是依赖工作目录。

[fs.op.temp.dir.path] ¶1–¶2 `temp_directory_path()` 返回一个适合存放临时文件的目录，它不存在或不是目录时报告错误。第 5 段的例子：POSIX 上实现可能依次查看环境变量 `TMPDIR`、`TMP`、`TEMP`、`TEMPDIR`，都没有则用 `/tmp`。

## 创建

| 函数 | 规定 |
|---|---|
| `create_directory(p)` | [fs.op.create.directory] ¶1 如同 POSIX `mkdir(p, perms::all)`；因 `p` 已经是一个目录而失败时不报告错误；¶2 新建了目录返回 `true`，否则 `false` |
| `create_directory(p, existing_p)` | ¶4 创建目录，并从 `existing_p` 复制属性，复制哪些由操作系统决定 |
| `create_directories(p)` | [fs.op.create.directories] ¶1 对 `p` 中每个不存在的元素调用 `create_directory`；¶2 新建了目录时返回 `true` |
| `create_symlink(to, link)` | [fs.op.create.symlink] ¶1–¶2 如同 POSIX `symlink`，`link` 成为一个内容为 `to` 的符号链接 |
| `create_directory_symlink(to, link)` | [fs.op.create.dir.symlk] 同上；第 4 段的注说明有些系统（如 Windows）要求创建时就标明链接指向目录 |
| `create_hard_link(to, link)` | [fs.op.create.hard.lk] ¶1–¶2 如同 POSIX `link`，之后 `equivalent(to, link)`；第 4 段的注说明有的系统或文件系统（如 FAT）不支持硬链接 |

- `mkdir` 的权限参数是 `perms::all`（0777），实际权限还要经过进程的 umask，通常得到 0755。
- `create_directory` 的返回值说明了目录是不是这次调用创建的。两个进程并发创建同一个目录，只有一个得到 `true`，可以用来实现"谁先创建谁负责"。`p` 已存在但不是目录时，仍然报告错误。
- 符号链接的内容 `to` 原样保存，以后相对于链接所在的目录解析，而不是相对于当前工作目录。`create_symlink("real.txt", "d/link")` 创建的链接指向 `d/real.txt`。

## 复制

```cpp run title="copy-ops.cpp" ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::remove_all("ops");
  fs::create_directories("ops/d1/sub");
  std::ofstream("ops/d1/a.txt") << "aaa";
  std::ofstream("ops/d1/sub/b.txt") << "bb";
  fs::copy("ops/d1", "ops/d2");  // 只复制一层
  fs::copy("ops/d1", "ops/d3", fs::copy_options::recursive);
  std::cout << fs::exists("ops/d2/a.txt") << fs::exists("ops/d2/sub")
            << fs::exists("ops/d3/sub/b.txt") << '\n';  // 101

  try {
    fs::copy_file("ops/d1/a.txt", "ops/d2/a.txt");  // 目标已存在
  } catch (const fs::filesystem_error& e) {
    std::cout << e.code().message() << '\n';        // File exists
  }
  std::cout << fs::copy_file("ops/d1/a.txt", "ops/d2/a.txt",
                             fs::copy_options::skip_existing)
            << '\n';                                // 0
  std::cout << fs::remove_all("ops") << '\n';       // 11
}
```

### `copy_file` [fs.op.copy.file]

¶3 `copy_options` 分成几组（[fs.enum.copy.opts]），每组至多指定一个，否则违反前置条件。¶4 的规则：

1. ¶4.1 报告错误，如果：`from` 不是普通文件；`to` 存在但不是普通文件；`to` 存在且与 `from` 是同一个文件；`to` 存在而选项里没有 `skip_existing`、`overwrite_existing`、`update_existing` 中的任何一个。
2. ¶4.2 否则，下列情况把 `from` 的内容和属性复制到 `to`：`to` 不存在；指定了 `overwrite_existing`；指定了 `update_existing` 且 `from` 比 `to` 新。
3. ¶4.3 否则什么也不做。

¶5 复制了返回 `true`，否则 `false`。上例第二次 `copy_file` 指定了 `skip_existing`，所以返回 `false` 而不报错。

### `copy` [fs.op.copy]

`copy(from, to, options)` 能复制文件、目录和符号链接。¶4 的算法：

1. ¶4.1–¶4.3 先取得状态 `f`（源）和 `t`（目标）。指定了 `create_symlinks` 或 `skip_symlinks` 时用 `symlink_status`；指定了 `copy_symlinks` 时源用 `symlink_status`、目标用 `status`；否则都用 `status`。
2. ¶4.4 任一方是实现定义的文件类型时，效果由实现定义。
3. ¶4.5 报告错误，如果：源不存在；两者是同一个文件；任一方是 `is_other` 的类型；源是目录而目标是普通文件。
4. ¶4.6 源是符号链接：指定了 `skip_symlinks` 就返回；目标不存在且指定了 `copy_symlinks` 就复制链接本身；否则报错。
5. ¶4.7 源是普通文件：指定了 `directories_only` 就返回；指定了 `create_symlinks` 或 `create_hard_links` 就创建相应的链接；目标是目录就 `copy_file(from, to / from.filename(), options)`；否则 `copy_file(from, to, options)`。
6. ¶4.8 源是目录且指定了 `create_symlinks`：报告 `errc::is_a_directory` 错误。
7. ¶4.9 源是目录，并且指定了 `recursive` 或者 `options == copy_options::none`：目标不存在时用 `create_directory(to, from)` 创建，然后如同执行

   ```cpp
   for (const directory_entry& x : directory_iterator(from))
     copy(x.path(), to / x.path().filename(),
          options | copy_options::in-recursive-copy);
   ```

   *in-recursive-copy* 是一个不对外公开的选项位。
8. ¶4.10–¶4.11 否则带 `ec` 的版本清除 `ec`，不带的什么也不做。

第 7 步解释了上例中 `d2` 为什么没有 `sub`。`options == none` 时会进入源目录，逐个复制它的直接条目。递归调用传下去的选项多了 *in-recursive-copy* 这一位，不再等于 `none`；子目录 `sub` 在下一层既没有 `recursive`，选项也不是 `none`，于是落到第 8 步，什么也不做。第 7 段的例子说的就是这件事：不加 `recursive` 只复制一层文件。

¶6 带 `ec` 的版本内部调用的库函数，凡是有 `error_code` 版本的都必须用那个版本，所以整个复制过程不会抛 `filesystem_error`。不过这个函数没有标 `noexcept`，仍可能抛 `bad_alloc`。

[fs.op.copy.symlink] `copy_symlink(existing, new)` 等价于用 `read_symlink(existing)` 的结果创建一个新的符号链接。[fs.op.read.symlink] `read_symlink(p)` 返回链接的内容，`p` 不是符号链接是错误。

## 删除、重命名、大小与权限

```cpp run title="rename-links.cpp" ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::create_directory("rn");
  std::ofstream("rn/x.txt") << "x";
  std::ofstream("rn/y.txt") << "yyyy";
  fs::rename("rn/x.txt", "rn/y.txt");  // y.txt 被替换
  std::cout << fs::file_size("rn/y.txt") << ' '
            << fs::exists("rn/x.txt") << '\n';           // 1 0

  fs::create_hard_link("rn/y.txt", "rn/y2.txt");
  std::cout << fs::equivalent("rn/y.txt", "rn/y2.txt") << ' '
            << fs::hard_link_count("rn/y.txt") << '\n';  // 1 2
  bool r1 = fs::remove("rn/y.txt");
  bool r2 = fs::remove("rn/y.txt");   // 已不存在：不是错误
  std::cout << r1 << ' ' << r2 << ' '
            << fs::exists("rn/y2.txt") << '\n';          // 1 0 1
  fs::remove_all("rn");
}
```

删掉一个硬链接后，文件仍然可以通过另一个名字 `y2.txt` 访问。

| 函数 | 规定 |
|---|---|
| `remove(p)` | [fs.op.remove] ¶1 如果 `exists(symlink_status(p))`，如同 POSIX `remove` 删除 `p`；注 1：删除的是符号链接本身，而不是它的目标；¶3 删除了返回 `true`，否则 `false`；注 2：`p` 不存在不是错误 |
| `remove_all(p)` | [fs.op.remove.all] ¶1 递归删除 `p` 的内容，再删除 `p` 本身，符号链接只删链接；¶3 返回删除的文件数，`ec` 版本出错时返回 `uintmax_t(-1)` |
| `rename(old_p, new_p)` | [fs.op.rename] ¶1 如同 POSIX `rename`；两者是同一个文件时什么也不做；`new_p` 是已有的非目录文件时，它被删除；是已有目录时，POSIX 上空目录会被删除，其他系统上可能是错误 |
| `resize_file(p, n)` | [fs.op.resize.file] ¶1 如同 POSIX `truncate`，之后 `file_size(p) == n` |
| `permissions(p, prms, opts)` | [fs.op.permissions] ¶1 `opts` 中 `replace`、`add`、`remove` 必须恰好有一个；¶2 对 `p` 解析到的文件（指定 `nofollow` 且 `p` 是符号链接时，对链接本身）应用该操作，如同 POSIX `fchmodat`；¶5 不带 `opts` 的 `ec` 版本如同 `opts` 为 `replace` |

`rename` 会覆盖已有文件，所以可以用来原子地替换文件内容：先写到同一目录下的临时文件，再 `rename` 成目标名。其他进程要么看到旧文件，要么看到新文件。标准本身只说如同 POSIX `rename`，原子性是 POSIX 给的保证。

## 思考题

!!! question "思考题 1"
    `fs::file_size(dir)` 对一个目录返回什么？

<details markdown="1">
<summary>答案</summary>

由实现定义（[[fs.op.file.size#2]]），标准只规定普通文件返回字节数。实现可以返回目录的 `st_size`，也可以报告错误。本机 libc++ 报告错误 "Is a directory"，`ec` 版本返回 `uintmax_t(-1)`。需要可移植的行为，先检查 `is_regular_file`。
</details>

!!! question "思考题 2"
    为什么 `status(p)` 对不存在的文件不抛异常，`file_size(p)` 却抛？

<details markdown="1">
<summary>答案</summary>

`status` 的职责是报告文件的状态，不存在是一个合法的答案（`file_type::not_found`），只有连存在与否都无法确定（`none`）时才抛异常（[[fs.op.status#1]]、[[fs.op.status#3]]）。`file_size` 要返回大小，不存在的文件没有大小，所以 [[fs.op.file.size#1]] 规定 `exists(p)` 为假时报告错误。
</details>

!!! question "思考题 3"
    `dir` 是已有的目录。`fs::copy("a.txt", "dir")` 的结果是什么？`fs::copy_file("a.txt", "dir")` 呢？

<details markdown="1">
<summary>答案</summary>

`copy` 按 [[fs.op.copy#4.7.4]]：源是普通文件、目标是目录，于是调用 `copy_file("a.txt", "dir/a.txt", options)`，把文件复制进目录。`copy_file` 没有这种处理，[[fs.op.copy.file#4.1.2]] 规定目标存在但不是普通文件时报告错误。
</details>
