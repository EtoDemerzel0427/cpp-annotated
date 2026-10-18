---
title: 文件系统操作函数与 file_status
summary: [fs.op.funcs] 的四十个操作函数分组精读——status 如何区分 none/not_found/unknown（以及 exists(p, ec) 与 is_regular_file(p, ec) 对"不存在"报告方式的差异）、symlink_status 与悬空链接、absolute/canonical/weakly_canonical/relative/proximate 的解析差异、create_directory 返回 false 而不报错、copy 与 copy_file 的选项组与完整算法、remove/remove_all/rename 的 POSIX 语义、file_size/equivalent/last_write_time/space/permissions、current_path 是危险的全局状态；以及 file_status 类
status: done
covers: *, fs.class.file.status, fs.class.file.status.general, fs.file.status.cons, fs.file.status.obs, fs.file.status.mods
since: c++17
related: filesystems, fs.class.path, fs.class.directory.iterator, file.streams, time.clock.file, syserr
tags: 标准库, filesystem, 文件操作, status, TOCTOU
updated: 2026-10-18
---

[fs.op.funcs] 是 `<filesystem>` 中真正"动手"的部分：查询文件状态、解析路径、创建、复制、移动、删除。几乎每个函数都成对出现——一个按 [[filesystems]] 的 [fs.err.report] 抛 `filesystem_error`，一个接受 `error_code&`。本页按用途分组讲解，并先介绍它们共用的 `file_status`。

## 总则（[fs.op.funcs.general]）

¶1：文件系统操作函数查询或修改外部存储中的文件（包括目录）。¶2（注）：硬件故障、网络故障、文件系统竞争（[[fs.race.behavior]]）以及许多其他类型的错误在文件系统操作中**频繁发生**，所以**任何**文件系统操作函数，无论看起来多么无害，都可能遇到错误。

这句注释是阅读本节的基调：不存在"不会失败"的文件系统操作。`exists(p)` 也会抛异常（例如对一个没有搜索权限的目录下的路径）。

## `file_status`（[fs.class.file.status]）

```cpp
class file_status {
public:
  file_status() noexcept : file_status(file_type::none) {}
  explicit file_status(file_type ft, perms prms = perms::unknown) noexcept;
  // 复制、移动均为 noexcept = default
  void type(file_type ft) noexcept;        void permissions(perms prms) noexcept;
  file_type type() const noexcept;         perms permissions() const noexcept;
  friend bool operator==(const file_status& lhs, const file_status& rhs) noexcept
    { return lhs.type() == rhs.type() && lhs.permissions() == rhs.permissions(); }
};
```

[fs.class.file.status.general] ¶1：保存文件的类型和权限信息。构造函数（[fs.file.status.cons] ¶1）后条件为 `type() == ft && permissions() == prms`；观察器返回最近一次构造、赋值或修改器设置的值（[fs.file.status.obs]、[fs.file.status.mods]）。它只是一个简单的值类型；把 `file_type` 与 `perms` 打包在一起的意义在于：一次 `stat` 就能得到两者，之后的 `is_directory(s)`、`exists(s)` 等重载都直接作用于这个值，不再访问文件系统。

## 状态查询

### `status`（[fs.op.status]）

`status(p, ec) noexcept` 是所有状态查询的基础：

- ¶4：若可能，如同用 POSIX `stat` 获取 `p` 所解析到的文件的属性。若底层 API 报告错误，把 `ec` 设为该错误；否则 `ec.clear()`。注：这让用户即使在返回值不是 `file_status(file_type::none)` 时，也能检查底层 API 的具体错误。
- ¶5：令 `prms` 为 `st_mode & perms::mask`。
- ¶6 返回值：
    - 若 `ec` 非零：错误表明 `p` 因为路径中某个元素**不存在**而无法解析，返回 `file_status(file_type::not_found)`；错误表明 `p` 可以解析但**属性无法确定**，返回 `file_status(file_type::unknown)`；否则返回 `file_status(file_type::none)`。注：这三种结果区分了"确知 `p` 不存在"、"`p` 存在但无法确定其属性"、"有错误使得连 `p` 是否存在都无法知道"。
    - 若 `ec` 为零：按 `S_ISREG`、`S_ISDIR`、`S_ISBLK`、`S_ISCHR`、`S_ISFIFO`、`S_ISSOCK` 依次返回 `regular`、`directory`、`block`、`character`、`fifo`、`socket`（都带 `prms`），实现定义的类型返回相应常量，否则返回 `unknown`。注 4：`regular` 意味着在没有硬件、权限、访问或文件系统竞争错误的前提下 `<fstream>` 操作会成功；注 5：`directory` 意味着 `directory_iterator(p)` 会成功。
- ¶7：路径名解析中遇到符号链接时，**继续用链接的内容解析**——`status` 跟随链接。

抛异常的 `status(p)`（¶1–¶3）**如同**：

```cpp
error_code ec;
file_status result = status(p, ec);
if (result.type() == file_type::none)
  throw filesystem_error(implementation-supplied-message, p, ec);
return result;
```

注：`not_found` 和 `unknown` **不被视为失败**，不抛异常。所以 `status("no-such-file")` 正常返回 `file_status(file_type::not_found)`。

### `symlink_status`、`status_known`（[fs.op.symlink.status]、[fs.op.status.known]）

`symlink_status`：¶1 同 `status`，但如同用 POSIX `lstat`；¶3 属性表明是符号链接（`S_ISLNK`）时返回 `file_status(file_type::symlink, prms)`；¶5 `p` 是符号链接时路径名解析终止——**不跟随**。

`status_known(s)`：¶1 `s.type() != file_type::none`。

```cpp title="status-vs-symlink.cpp" ok
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
  fs::create_symlink("gone.txt", d / "dangling");      // 悬空的符号链接

  for (auto n : {"real.txt", "good_link", "dangling", "nope"}) {
    fs::path p = d / n;
    std::cout << n << ": status=" << name(fs::status(p).type())
              << " symlink_status=" << name(fs::symlink_status(p).type())
              << " exists=" << fs::exists(p) << '\n';
  }
  // real.txt:  status=regular   symlink_status=regular   exists=1
  // good_link: status=regular   symlink_status=symlink   exists=1
  // dangling:  status=not_found symlink_status=symlink   exists=0   ← 链接本身在，exists 却为假
  // nope:      status=not_found symlink_status=not_found exists=0
  fs::remove_all(d);
}
```

悬空链接是 `exists()` 的经典陷阱：`exists` 用的是 `status`（跟随链接），链接目标不存在时返回 `false`，但目录里确实有这个名字，`create_symlink` 同名会失败。判断"这个名字是否被占用"要用 `exists(fs::symlink_status(p))`。

### `exists` 与 `is_*`（[fs.op.exists] 至 [fs.op.is.symlink]）

| 函数 | 规定 |
|---|---|
| `exists(file_status s) noexcept` | `status_known(s) && s.type() != file_type::not_found` |
| `exists(p)` / `exists(p, ec) noexcept` | 令 `s` 为 `status(p)` / `status(p, ec)`；带 `ec` 的版本在 `status_known(s)` 时调用 `ec.clear()`；返回 `exists(s)` |
| `is_regular_file(s)` 等 | `s.type() == file_type::regular`（`directory`、`symlink`、`block`、`character`、`fifo`、`socket` 同理） |
| `is_regular_file(p, ec) noexcept` | ¶4 如同 `status(p, ec)` 设置 `ec`；注：`none`、`not_found`、`unknown` 都会把 `ec` 设为错误值；返回 `false` |
| `is_other(s)` | `exists(s) && !is_regular_file(s) && !is_directory(s) && !is_symlink(s)` |
| `is_symlink(p)` | `is_symlink(symlink_status(p))`——唯一用 `symlink_status` 的 `is_*` |
| `is_empty(p)` | 目录：`directory_iterator(p) == directory_iterator()`；否则 `file_size(p) == 0` |

这里有一处容易忽略的不对称：**`exists(p, ec)` 把"不存在"当作正常结果**（`status_known` 为真，于是清除 `ec`），而 **`is_regular_file(p, ec)` 等不清除**，`ec` 保留 `status` 设置的"No such file or directory"：

```cpp title="exists-vs-is-ec.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  std::error_code ec;
  bool e = fs::exists("nope", ec);
  std::cout << "exists: " << e << " error=" << bool(ec) << '\n';           // exists: 0 error=0
  bool r = fs::is_regular_file("nope", ec);
  std::cout << "is_regular_file: " << r << " error=" << bool(ec) << '\n';  // is_regular_file: 0 error=1
}
```

用 `error_code` 版本时，判断"出错了"与"答案是否"要分开处理；需要细分情况时，直接调用 `status(p, ec)` 并检查 `type()`。

### 其他属性（[fs.op.equivalent] 至 [fs.op.space]）

| 函数 | 规定 | 出错时（`ec` 版本） |
|---|---|---|
| `equivalent(p1, p2)` | ¶1 位于同一设备的同一位置即解析到同一实体（POSIX：`st_dev` 与 `st_ino` 都相等）；¶4 `!exists(p1) \|\| !exists(p2)` 是错误 | `false` |
| `file_size(p)` | ¶1 `p` 不存在是错误；¶2 普通文件返回 `st_size`，**其他类型的结果由实现定义** {{impl}} | `uintmax_t(-1)` |
| `hard_link_count(p)` | 硬链接数 | `uintmax_t(-1)` |
| `last_write_time(p)` | 最后数据修改时间（`st_mtime`），类型 `file_time_type` | `file_time_type::min()` |
| `last_write_time(p, t)` | 如同 `futimens` 设置；注：**不保证**之后 `last_write_time(p) == t`，因为文件系统的时间粒度可能较粗 | — |
| `space(p)` | 如同 `statvfs`，`f_blocks`/`f_bfree`/`f_bavail` 乘以 `f_frsize` 得到 `capacity`/`free`/`available`；无法确定的成员为 `uintmax_t(-1)`；注：`available` 可能小于 `free`（保留给特权用户的空间） | 全部 `uintmax_t(-1)` |

`file_time_type` 是 `chrono::time_point<chrono::file_clock>`（[[time.clock.file]]）；`file_clock` 的纪元未指定，要转成系统时间用 `clock_cast<system_clock>` 或 `file_clock::to_sys`。

## 路径解析

| 函数 | 访问文件系统？ | 要求存在？ | 解析符号链接？ | 结果 |
|---|---|---|---|---|
| `absolute(p)` | 应当不（¶6 注） | 否 | 否 | 绝对路径，不一定规范 |
| `canonical(p)` | 是 | **是**（¶4 `!exists(p)` 是错误） | 是 | 绝对、无符号链接、无 `.`/`..` |
| `weakly_canonical(p)` | 是 | 否 | 对存在的前缀是 | 规范形式（¶2） |
| `relative(p, base)` | 是 | 否 | 是 | `weakly_canonical(p).lexically_relative(weakly_canonical(base))` |
| `proximate(p, base)` | 是 | 否 | 是 | 同上，用 `lexically_proximate` |
| `p.lexically_normal()` 等 | 否 | 否 | 否 | 见 [[fs.class.path]] |

- `absolute`（[fs.op.absolute]）：¶1 按操作系统组合出引用同一位置的绝对路径；¶3（注）无错误时结果 `is_absolute()` 为真；¶5（注）要解析符号链接或做其他需要查询外部存储的清理，考虑 `canonical`；¶6（注）**强烈鼓励**实现不查询外部存储，并且不把 `!exists(p)` 当作错误；¶7 例：POSIX 上 `absolute(p)` 就是 `current_path()/p`，Windows 上可能与 `GetFullPathNameW` 语义相同。
- `canonical`（[fs.op.canonical]）：¶1 转换为没有符号链接、dot、dot-dot 元素的绝对路径；¶2 返回与 `absolute(p)` 指向同一文件系统对象的路径。
- `weakly_canonical`（[fs.op.weakly.canonical]）：¶1 用 `status` 判断存在性，对 `p` 的**存在的前导元素**组成的路径调用 `canonical`，再用 `/=` 拼上**不存在的后续元素**；¶2 结果是规范形式；¶3 即"解析了符号链接并规范化的 `p`"。
- `relative`/`proximate`（[fs.op.relative]、[fs.op.proximate]）：¶1 单参数 `ec` 版本以 `current_path()` 为 `base`；¶3 如上表。

```cpp title="resolve.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::create_directories("cz/real/sub");
  fs::create_directory_symlink("real", "cz/link");
  fs::path p = "cz/link/sub/../sub/./not-yet/file.txt";
  std::cout << fs::absolute(p).lexically_relative(fs::current_path()) << '\n';
  // "cz/link/sub/../sub/./not-yet/file.txt"：absolute 只是拼上当前目录
  std::cout << fs::weakly_canonical(p).lexically_relative(fs::canonical(".")) << '\n';
  // "cz/real/sub/not-yet/file.txt"：存在的前缀被解析，其余部分被规范化
  std::error_code ec;
  (void)fs::canonical(p, ec);
  std::cout << ec.message() << '\n';      // No such file or directory：canonical 要求路径存在
  fs::remove_all("cz");
}
```

### `current_path` 与 `temp_directory_path`（[fs.op.current.path]、[fs.op.temp.dir.path]）

- `current_path()`：¶1 当前工作目录的绝对路径，如同 POSIX `getcwd`；`ec` 版本出错返回 `path()`。¶3：当前工作目录是与**进程**关联的、作为相对路径解析起点的目录。¶4（注）：许多操作系统返回的当前路径是一个**危险的全局变量**，可能被第三方库、系统库函数或**另一个线程**意外改变。
- `current_path(p)`：¶5 如同 POSIX `chdir`；¶6 后条件 `equivalent(p, current_path())`；¶8（注）同样警告它是危险的全局状态。
- `temp_directory_path()`：¶1 令 `p` 为一个适合存放临时文件的、未指定的目录路径；¶2 `p` 不存在或不是目录时报告错误；¶5 例：POSIX 上实现可能依次查看环境变量 `TMPDIR`、`TMP`、`TEMP`、`TEMPDIR`，都没有则用 `"/tmp"`；Windows 上可能用 `GetTempPath`。

!!! pitfall "多线程程序中不要调用 `current_path(p)`"
    工作目录是整个进程共享的。一个线程调用 `current_path(p)` 之后，其他线程所有以**相对路径**进行的文件操作（包括 `ifstream("x.txt")`）都会解析到新目录下。这与 [[fs.race.behavior]] 一样，是标准库无法替你同步的外部状态。库代码应接受绝对路径或显式的基准目录，而不是依赖工作目录。

## 创建

| 函数 | 规定 |
|---|---|
| `create_directory(p)` | ¶1 如同 POSIX `mkdir(p, perms::all)`；**若因 `p` 已解析到一个已有目录而失败，不报告错误**；¶2 新建了目录返回 `true`，否则 `false` |
| `create_directory(p, existing_p)` | ¶4 创建目录并从 `existing_p` 复制属性（哪些属性依赖操作系统；POSIX 上是 `stat(existing_p)` 后以其 `st_mode` 调用 `mkdir`） |
| `create_directories(p)` | ¶1 对 `p` 中每个不存在的元素调用 `create_directory`；¶2 为 `p` 新建了目录时返回 `true`；¶4 复杂度 O(n)，n 为 `p` 的元素个数 |
| `create_symlink(to, new_symlink)` | 如同 POSIX `symlink`；后条件：`new_symlink` 解析到一个包含 `to` 的某种表示的符号链接文件 |
| `create_directory_symlink(to, new_symlink)` | 同上；¶4 注：有些操作系统要求创建时就标明链接指向目录（Windows），所以不能可靠地用 `create_symlink` 创建目录链接 |
| `create_hard_link(to, new_hard_link)` | 如同 POSIX `link`；后条件 `exists(to) && exists(new_hard_link) && equivalent(to, new_hard_link)`，`to` 的内容不变；注：有的系统或文件系统（如 FAT）不支持硬链接，或限制每个文件的链接数 |

几个要点：

- `mkdir` 的第二个实参是 `perms::all`（0777），实际权限还要经过进程的 umask，通常得到 0755。
- `create_directory` 的返回值是 TOCTOU 安全的"是否由我创建"：并发的两个进程中只有一个会得到 `true`（[[filesystems]] 的例子）。`p` 已存在但**不是目录**时仍然报错。
- `create_symlink(to, ...)` 的 `to` 原样存入链接，**相对于链接所在的目录**解析，而不是相对于当前工作目录——`create_symlink("real.txt", "d/link")` 创建的链接指向 `d/real.txt`。

## 复制

### `copy_file`（[fs.op.copy.file]）

¶3：前置条件：`options` 中每个选项组至多设置一个元素。¶4 效果：

1. 以下情况报告错误：`is_regular_file(from)` 为假；`exists(to)` 为真且 `is_regular_file(to)` 为假；`exists(to)` 且 `equivalent(from, to)`；`exists(to)` 且没有设置 `skip_existing`、`overwrite_existing`、`update_existing` 中的任何一个。
2. 否则，在以下情况下把 `from` 的**内容和属性**复制到 `to`：`exists(to)` 为假；或设置了 `overwrite_existing`；或设置了 `update_existing` 且 `from` 比 `to` 新（如同用 `last_write_time` 判断）。
3. 否则无效果。

¶5：复制了文件返回 `true`，否则 `false`（`ec` 版本出错时返回 `false`）。¶7 复杂度：至多直接或间接调用一次 `status(to)`。

### `copy`（[fs.op.copy]）

`copy(from, to, options)` 是一个可以复制文件、目录（可递归）、符号链接的通用函数。¶3 前置条件同上。¶4 的算法：

1. 先确定 `f` 和 `t`：设置了 `create_symlinks` 或 `skip_symlinks` 时，`f = symlink_status(from)`、需要时 `t = symlink_status(to)`；否则设置了 `copy_symlinks` 时，`f = symlink_status(from)`、`t = status(to)`；否则 `f = status(from)`、`t = status(to)`。
2. ¶4.4：`f` 或 `t` 是实现定义的文件类型时，效果由实现定义。
3. ¶4.5：以下情况报告错误：`!exists(f)`；`equivalent(from, to)`；`is_other(f) || is_other(t)`；`is_directory(f) && is_regular_file(t)`。
4. ¶4.6：`f` 是符号链接：设置了 `skip_symlinks` 则返回；否则 `!exists(t)` 且设置了 `copy_symlinks` 则 `copy_symlink(from, to)`；否则报错。
5. ¶4.7：`f` 是普通文件：设置了 `directories_only` 则返回；设置了 `create_symlinks` 则创建指向源文件的符号链接；设置了 `create_hard_links` 则创建硬链接；`to` 是目录则 `copy_file(from, to / from.filename(), options)`；否则 `copy_file(from, to, options)`。
6. ¶4.8：`f` 是目录且设置了 `create_symlinks`：以 `errc::is_a_directory` 报错。
7. ¶4.9：`f` 是目录，且设置了 `recursive` **或 `options == copy_options::none`**：若 `to` 不存在，`create_directory(to, from)`；然后如同

   ```cpp
   for (const directory_entry& x : directory_iterator(from))
     copy(x.path(), to / x.path().filename(), options | copy_options::in-recursive-copy);
   ```

   其中 *in-recursive-copy* 是一个不属于公开枚举值的位。
8. ¶4.10–¶4.11：否则（`ec` 版本）`ec.clear()`，或者无效果。

第 7 步的设计很巧妙：`options == none` 时也会进入目录，复制其中的**直接**条目；但递归调用传入的选项多了 *in-recursive-copy* 位，于是不再等于 `none`，子目录在下一层不满足条件、被跳过。结果就是 ¶7 例子所说的：`copy("/dir1", "/dir3")` 只复制 `dir1` 的文件、不复制子目录 `dir2`；加上 `copy_options::recursive` 才完整复制。

¶6 *Remarks*：`ec` 版本中，实现调用的库函数在适用时都必须使用 `error_code` 版本——保证整个递归复制过程不抛 `filesystem_error`（但仍可能抛 `bad_alloc`，它也不是 `noexcept`）。

`copy_symlink(existing, new)`（[fs.op.copy.symlink]）：等价于 `create_symlink(read_symlink(existing), new)` 或 `create_directory_symlink(...)`，视链接类型而定。`read_symlink(p)`（[fs.op.read.symlink]）：返回符号链接的内容；`p` 不是符号链接是错误。

```cpp title="copy-ops.cpp" ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::create_directories("ops/d1/sub");
  std::ofstream("ops/d1/a.txt") << "aaa";
  std::ofstream("ops/d1/sub/b.txt") << "bb";
  fs::copy("ops/d1", "ops/d2");                                // 默认：只复制直接条目中的文件
  fs::copy("ops/d1", "ops/d3", fs::copy_options::recursive);
  std::cout << fs::exists("ops/d2/sub") << fs::exists("ops/d3/sub/b.txt") << '\n';   // 01

  try {
    fs::copy_file("ops/d1/a.txt", "ops/d2/a.txt");             // 目标已存在且没有指定选项：错误
  } catch (const fs::filesystem_error& e) {
    std::cout << e.code().message() << '\n';                   // File exists
  }
  std::cout << fs::copy_file("ops/d1/a.txt", "ops/d2/a.txt",
                             fs::copy_options::skip_existing) << '\n';   // 0：跳过，不报错
  std::cout << "removed " << fs::remove_all("ops") << '\n';    // removed 11
}
```

## 删除、重命名、改变大小与权限

| 函数 | 规定 |
|---|---|
| `remove(p)` | ¶1 若 `exists(symlink_status(p, ec))`，如同 POSIX `remove` 删除 `p`；注：删除的是**符号链接本身**而不是其目标；¶2 后条件 `!exists(symlink_status(p))`；¶3 删除了返回 `true`，否则 `false`；注：**`p` 不存在不是错误** |
| `remove_all(p)` | ¶1 若存在，递归删除其内容，再删除 `p` 本身（符号链接只删除链接）；¶3 返回删除的文件数，`ec` 版本出错返回 `uintmax_t(-1)` |
| `rename(old_p, new_p)` | ¶1 如同 POSIX `rename`。注：二者解析到同一个已有文件时无动作；否则 `new_p` 若是已有的非目录文件，**它被删除**；若是已有目录，在 POSIX 系统上为空时被删除，其他系统上可能是错误；符号链接被重命名的是链接本身 |
| `resize_file(p, n)` | ¶1 如同 POSIX `truncate`，使 `file_size(p) == n` |
| `permissions(p, prms, opts = replace)` | ¶1 前置条件：`replace`、`add`、`remove` 中**恰好**一个出现在 `opts` 中；¶2 对 `p` 解析到的文件（设置 `nofollow` 且 `p` 是符号链接时，对链接本身）如同用 POSIX `fchmodat` 应用该动作；¶5 不带 `opts` 的 `ec` 版本如同 `opts = replace` |

`rename` 覆盖已有文件的语义使它可以用来**原子地替换**文件内容：先写入同目录下的临时文件，再 `rename` 到目标名。POSIX 保证 `rename` 是原子的——其他进程要么看到旧文件，要么看到新文件。（标准本身只说"as if by POSIX rename"，原子性来自 POSIX。）

```cpp title="rename-links.cpp" ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::create_directory("rn");
  std::ofstream("rn/x.txt") << "x";
  std::ofstream("rn/y.txt") << "yyyy";
  fs::rename("rn/x.txt", "rn/y.txt");                    // y.txt 已存在：被替换
  std::cout << fs::file_size("rn/y.txt") << ' ' << fs::exists("rn/x.txt") << '\n';  // 1 0

  fs::create_hard_link("rn/y.txt", "rn/y2.txt");
  std::cout << fs::equivalent("rn/y.txt", "rn/y2.txt") << ' '
            << fs::hard_link_count("rn/y.txt") << '\n';  // 1 2
  std::cout << fs::remove("rn/y.txt") << ' ' << fs::remove("rn/y.txt") << ' '
            << fs::exists("rn/y2.txt") << '\n';          // 1 0 1：删掉一个硬链接，文件还在
  fs::remove_all("rn");
}
```

## 思考题

<details markdown="1">
<summary>1. <code>fs::file_size(dir)</code> 对一个目录返回什么？</summary>

由实现定义（[[fs.op.file.size#2]] ¶2.2）——标准只规定普通文件返回 `st_size`。不同实现可能返回目录的 `st_size`、报告错误（`is_a_directory`），或其他值。需要可移植的行为就先检查 `is_regular_file`。
</details>

<details markdown="1">
<summary>2. 为什么 <code>status(p)</code> 对不存在的文件不抛异常，而 <code>file_size(p)</code> 抛？</summary>

`status` 的职责是**报告**文件的状态，"不存在"是一个合法答案（`file_type::not_found`，[[fs.enum.file.type]] 的注说文件不存在在确定类型时不被视为错误），只有连存在与否都无法确定（`none`）时才抛（[[fs.op.status#1]]）。`file_size` 的职责是返回大小，[[fs.op.file.size#1]] 明确规定 `exists(p)` 为假时报告错误——不存在的文件没有大小。
</details>

<details markdown="1">
<summary>3. <code>fs::copy("a.txt", "dir")</code>（<code>dir</code> 是已有目录）的结果是什么？<code>fs::copy_file("a.txt", "dir")</code> 呢？</summary>

`copy` 按 ¶4.7.4：`from` 是普通文件、`to` 是目录，于是调用 `copy_file("a.txt", "dir/a.txt", options)`，把文件复制到目录里。`copy_file` 没有这种便利：[[fs.op.copy.file#4]] ¶4.1.2 规定 `exists(to)` 且 `is_regular_file(to)` 为假时报告错误。
</details>

## 小结

| 分组 | 函数 | 关键语义 |
|---|---|---|
| 状态 | `status`/`symlink_status` | 跟随 / 不跟随链接；`not_found`、`unknown` 不抛，只有 `none` 抛 |
| 存在性 | `exists`、`is_*` | `exists(p, ec)` 视不存在为正常；`is_*(p, ec)` 视之为错误；悬空链接 `exists` 为假 |
| 解析 | `absolute`、`canonical`、`weakly_canonical`、`relative`、`proximate` | 只有 `canonical` 要求存在；`absolute` 不应访问文件系统 |
| 创建 | `create_directory(ies)`、`create_*symlink`、`create_hard_link` | 目录已存在不报错、返回 `false`；目录链接要用专门函数 |
| 复制 | `copy`、`copy_file`、`copy_symlink` | 每组至多一个选项；`copy` 默认只复制一层文件；`copy_file` 目标存在时默认报错 |
| 删除 | `remove`、`remove_all` | 不存在不是错误；符号链接只删链接本身 |
| 移动 | `rename` | POSIX 语义：覆盖已有文件，可用于原子替换 |
| 全局状态 | `current_path` | 进程级、线程间共享，危险 |
