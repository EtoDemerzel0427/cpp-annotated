---
title: 目录项与目录遍历
summary: directory_entry 是路径加上可能已缓存的文件属性；directory_iterator 单层遍历一个目录，recursive_directory_iterator 递归遍历；遍历顺序未指定、出错即变成尾迭代器、递归在 ++ 时决定。
status: done
covers: *, fs.class.directory.entry, fs.class.directory.entry.general, fs.dir.entry.cons, fs.dir.entry.mods, fs.dir.entry.obs, fs.dir.entry.io, fs.class.rec.dir.itr, fs.class.rec.dir.itr.general, fs.rec.dir.itr.members, fs.rec.dir.itr.nonmembers
since: c++17
related: filesystems, fs.class.path, fs.op.funcs, input.iterators, range.view, range.range
tags: 标准库, filesystem, 目录遍历, 迭代器
updated: 2026-10-19
---

!!! tldr
    - 遍历得到的条目顺序未指定，不含 `.` 和 `..`；需要确定的顺序就先收集再排序。
    - `directory_entry` 可以缓存遍历时顺便得到的文件属性，省掉一次 `stat`，代价是缓存可能过期，需要时调用 `refresh()`。
    - 范围 `for` 只能用会抛异常的 `++`；不想处理异常就手写循环，用 `increment(ec)`。
    - `recursive_directory_iterator` 在 `++` 时才决定是否进入当前目录，所以 `disable_recursion_pending()` 要在 `++` 之前调用；默认不进入指向目录的符号链接。
    - 在尾迭代器上调用 `depth()`、`pop()` 等成员是 UB。

## 列出一个目录 [fs.class.directory.iterator]

```cpp run title="dir-iterate.cpp" ok
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <ranges>
#include <vector>
namespace fs = std::filesystem;

int main() {
  fs::create_directories("proj/src");
  std::ofstream("proj/a.cpp");
  std::ofstream("proj/b.h");
  std::ofstream("proj/c.cpp");

  auto names = fs::directory_iterator("proj")
    | std::views::filter([](const fs::directory_entry& e) {
        return e.is_regular_file() && e.path().extension() == ".cpp"; })
    | std::views::transform([](const fs::directory_entry& e) {
        return e.path().filename(); })
    | std::ranges::to<std::vector>();
  std::ranges::sort(names);              // 顺序未指定：先排序
  for (auto& n : names) std::cout << n << ' ';
  std::cout << '\n';                     // "a.cpp" "c.cpp"

  std::error_code ec;
  int count = 0;
  for (fs::directory_iterator it("proj", ec), end;
       !ec && it != end; it.increment(ec))
    ++count;
  std::cout << count << ' ' << bool(ec) << '\n';  // 4 0

  fs::directory_iterator bad("no-such-dir", ec);
  std::cout << (bad == fs::directory_iterator()) << ' '
            << ec.message() << '\n';
  // 1 No such file or directory
  fs::remove_all("proj");
}
```

`directory_iterator` 本身就是一个范围：[fs.dir.itr.nonmembers] 的 `begin(it)` 返回 `it`，`end(it)` 返回默认构造的**尾迭代器**（end iterator）。[[filesystems]] 的概要还把它声明为 view 和 borrowed range，所以可以直接接范围适配器。

### 迭代器的规则（[fs.class.directory.iterator.general]）

- ¶1 它遍历一个目录中每个文件对应的 `directory_entry`。¶2 它是输入迭代器，只能单遍遍历。
- ¶3 迭代器报告错误，或者越过最后一个条目时，都会变得等于尾迭代器。默认构造的迭代器就是尾迭代器。¶4–¶5 尾迭代器不可解引用，两个尾迭代器总是相等。
- ¶6 条目的 `path()` 是构造时传入的目录路径 `/` 条目的文件名，不做规范化。从 `"proj"` 开始得到 `"proj/a.cpp"`，从 `"./proj/"` 开始得到 `"./proj/a.cpp"`。需要绝对路径，就从绝对路径开始遍历。
- ¶7 不产生 `.` 和 `..`。
- ¶8 条目的顺序未指定。不同文件系统、不同平台，甚至同一目录的两次遍历都可能不同。
- 第 10 段的注提醒，得到的路径不一定存在：它可能是一个悬空的符号链接。
- 第 11 段的注说明，构造之后在目录中添加或删除文件，后续递增能否遇到这些条目是未指定的（与 POSIX `readdir` 一致）。删除当前条目本身是安全的；新建的文件可能被遍历到，也可能不会。

### 构造与递增（[fs.dir.itr.members]）

¶2 `directory_iterator(p)` 指向 `p` 这个目录的第一个条目，目录为空时得到尾迭代器。¶3 出错时按 [fs.err.report] 报告：不带 `error_code` 的版本抛 `filesystem_error`，带 `ec` 的版本设置 `ec` 并得到尾迭代器，上例的 `bad` 就是这样。

如果选项含 `directory_options::skip_permission_denied`，构造时遇到权限被拒绝，得到尾迭代器而不报告错误。第 4 段的注提醒，遍历当前目录要写 `directory_iterator(".")`，而不是 `directory_iterator("")`。

¶9–¶11 `operator++()` 和 `increment(ec)` 移到下一个条目，出错时同样按 [fs.err.report] 报告。

!!! pitfall "范围 `for` 不能用 `error_code`"
    `for (auto& e : fs::directory_iterator(p))` 里的 `++` 调用的是会抛异常的 `operator++()`。目录在遍历中途变得不可读（被删除、权限改变、网络断开）时，就会抛 `filesystem_error`。需要不抛异常的遍历，就像上例那样手写循环，用 `increment(ec)` 并每一步检查 `ec`。

    另外，`transform` 之后的迭代器不满足老式的 *Cpp17InputIterator* 要求，不能传给 `vector(first, last)`，要用 `std::ranges::to`。

## 目录项 [fs.class.directory.entry]

### 缓存的属性（[fs.class.directory.entry.general]）

¶1 `directory_entry` 保存一个 `path`，还可能保存这个文件的若干属性：硬链接数、状态、符号链接状态、大小、最后写入时间。¶2 如果目录遍历时这些属性已经可得，而保存下来可以让观察器免去一次文件系统访问，实现应当保存它们。这样保存的值叫做**已缓存的**（cached）属性。

这样设计是为了性能。POSIX 的 `readdir` 返回的 `d_type` 已经说明条目是不是目录，Windows 的 `FindNextFileW` 一次就返回了大小、时间和属性。缓存下来，`entry.is_directory()` 就不必再调用一次 `stat`。

代价是缓存可能过期。第 4 段的例子：

```cpp
for (auto&& x : directory_iterator(".")) {
  lengthy_function(x.path());  // 期间文件可能被修改
  x.refresh();                 // 需要最新值时显式刷新
  std::cout << x.path() << " " << x.last_write_time() << std::endl;
}
```

不缓存的实现每次调用 `last_write_time()` 都访问文件系统；缓存的实现返回遍历时的快照。这段代码在两种实现上都能用，读到的值新旧不同。

### 观察器（[fs.dir.entry.obs]）

| 观察器 | 返回 |
|---|---|
| `path()`、`operator const path&()` | ¶2 保存的路径 |
| `exists()`、`is_directory()`、`is_regular_file()` 等 | ¶3–¶18 对应的非成员函数作用于 `status()` |
| `is_symlink()` | ¶19 `is_symlink(symlink_status())`，不跟随链接 |
| `file_size()`、`hard_link_count()`、`last_write_time()` | ¶21–¶26 已缓存则返回缓存值，否则调用对应的非成员函数 |
| `status()`、`symlink_status()` | ¶27–¶30 已缓存则返回缓存值，否则调用 `status(path())`、`symlink_status(path())` |
| `==`、`<=>` | ¶31–¶32 比较路径 |

`status()` 跟随符号链接，`symlink_status()` 不跟随，详见 [[fs.op.funcs]]。所以对一个指向目录的符号链接，`is_directory()` 和 `is_symlink()` 都为真。

每个观察器都有一个接受 `error_code&` 的 `noexcept` 版本。[fs.dir.entry.io] ¶1 `os << d` 等价于 `os << d.path()`，所以同样会加引号。

### 构造与修改（[fs.dir.entry.cons]、[fs.dir.entry.mods]）

¶1 `directory_entry(p)` 和 `directory_entry(p, ec)` 会调用 `refresh()`，也就是会访问文件系统。¶2 无错误时 `path() == p`，出错时 `path()` 为空。所以 `directory_entry("no-such-file")` 会抛异常；对可能不存在的路径，要用带 `ec` 的版本。

[fs.dir.entry.mods] ¶1 `assign(p)` 等价于先替换路径再 `refresh()`；¶3 `replace_filename(p)` 等价于先对路径调用 `replace_filename(p)` 再 `refresh()`。¶5 `refresh()` 重新读取并保存当前的属性值，出错时报告错误，缓存的值未指定。

[fs.class.directory.iterator.general] ¶9 规定，`directory_iterator` 把已缓存的属性存进它返回的 `directory_entry`，但不得直接或间接调用 `refresh`。[fs.dir.entry.mods] 第 7 段的注重复了这一点。遍历本身因此不会为每个条目多做一次 `stat`，没缓存的属性由观察器在被调用时再去获取。

## 递归遍历 [fs.class.rec.dir.itr]

```cpp run title="recursive-walk.cpp" ok
#include <filesystem>
#include <fstream>
#include <iostream>
#include <set>
#include <string>
namespace fs = std::filesystem;

int main() {
  const fs::path root = "sandbox";
  fs::remove_all(root);
  fs::create_directories(root / "src/detail");
  fs::create_directories(root / "build/obj");
  std::ofstream(root / "src/main.cpp") << "int main(){}";
  std::ofstream(root / "src/detail/util.hpp") << "#pragma once";
  std::ofstream(root / "build/obj/main.o") << "obj";

  std::set<std::string> seen;  // 顺序未指定：放进 set
  for (auto it = fs::recursive_directory_iterator(root);
       it != fs::recursive_directory_iterator(); ++it) {
    if (it->is_directory() && it->path().filename() == "build")
      it.disable_recursion_pending();  // 在 ++ 之前调用
    seen.insert(std::to_string(it.depth()) + " " +
                it->path().generic_string());
  }
  for (auto& s : seen) std::cout << s << '\n';
  // 0 sandbox/build
  // 0 sandbox/src
  // 1 sandbox/src/detail
  // 1 sandbox/src/main.cpp
  // 2 sandbox/src/detail/util.hpp
  std::cout << fs::remove_all(root) << '\n';  // 8
}
```

`build` 本身出现在结果里，但它下面的 `obj` 没有出现，因为在 `++` 之前关掉了对它的递归。

### 额外的成员（[fs.class.rec.dir.itr.general]、[fs.rec.dir.itr.members]）

¶1 `recursive_directory_iterator` 遍历一个目录及其所有子目录。¶3 除另有规定外，它的行为与 `directory_iterator` 相同，所以顺序未指定、不产生 `.` 和 `..`、路径是拼出来的，这些规则都适用。它多出这几个成员：

| 成员 | 作用 |
|---|---|
| `options()` | ¶15 构造时传入的选项，没有传入则为 `none` |
| `depth()` | ¶17 当前深度：起始目录中的条目为 0，其子目录中的为 1，依此类推 |
| `recursion_pending()` | ¶19 自上次构造或递增以来没有调用过 `disable_recursion_pending()` 时为真 |
| `disable_recursion_pending()` | ¶27–¶28 让下一次 `++` 不进入当前目录 |
| `pop()`、`pop(ec)` | ¶24 `depth() == 0` 时变为尾迭代器；否则放弃当前目录剩下的条目，回到父目录继续 |

¶7–¶14 复制和移动保留 `options()`、`depth()`、`recursion_pending()`。¶26 `pop()` 之后，此前的副本不再保证可以解引用或比较。

### `++` 何时进入子目录（¶21）

¶21 递增按输入迭代器的规定进行，另有两条：

- ¶21.1 当前目录没有更多条目时，如果 `depth() != 0`，回到父目录继续；否则变为尾迭代器。
- ¶21.2 否则，满足下面的条件时进入目录 `(*this)->path()`：

```cpp
recursion_pending() && is_directory((*this)->status()) &&
(!is_symlink((*this)->symlink_status()) ||
 (options() & directory_options::follow_directory_symlink)
   != directory_options::none)
```

从这个条件可以读出三点：

1. 递归发生在 `++` 时。迭代器先停在目录条目本身上，下一次 `++` 才进入其中。要跳过某个目录，必须在它是当前条目时、`++` 之前调用 `disable_recursion_pending()`。每次递增后，这个标志自动恢复。
2. 是不是目录用 `status()` 判断（跟随链接），是不是链接用 `symlink_status()` 判断。所以默认情况下，指向目录的符号链接会作为条目出现，但不会被进入（第 6 段的注）。
3. 打开 `follow_directory_symlink` 后，指向祖先目录的链接会形成环。[fs.class.rec.dir.itr.general] 第 4 段的注说明，这时可能永远到不了尾迭代器。

进入子目录时遇到权限被拒绝，如果选项含 `skip_permission_denied`，就把这个目录当作空目录，不报告错误。

!!! pitfall "在尾迭代器上调用 `depth()` 是 UB"
    [[fs.class.rec.dir.itr.general#2]] 规定，在不可解引用的迭代器（包括尾迭代器）上调用 `options`、`depth`、`recursion_pending`、`pop` 或 `disable_recursion_pending`，行为未定义 {{ub}}。循环里要先判断是否到尾，再使用这些成员。

## 思考题

!!! question "思考题 1"
    用 `recursive_directory_iterator` 遍历时，对当前条目调用 `fs::remove_all(it->path())` 删除一个子目录，然后 `++it`，安全吗？

<details markdown="1">
<summary>答案</summary>

对目录条目不安全。`recursion_pending()` 仍为真，缓存的状态表明它是目录，于是 `++` 会尝试进入它（[[fs.rec.dir.itr.members#21]]），而目录已经不存在。本机 libc++ 抛出 `filesystem_error`，消息是 `attempting recursion into "t/a": No such file or directory`；用 `increment(ec)` 则设置 `ec`。删除之前先调用 `it.disable_recursion_pending()`。

删除普通文件没有这个问题。删除对之后遍历的影响，按 [[fs.class.directory.iterator.general#11]] 是未指定的。
</details>

!!! question "思考题 2"
    `directory_entry("a/b")` 和 `directory_iterator` 产生的指向 `a/b` 的条目，调用 `is_directory()` 时访问文件系统的次数一定相同吗？

<details markdown="1">
<summary>答案</summary>

不一定。构造函数调用了 `refresh()`，实现选择缓存的属性在构造时就读取并保存了（[[fs.dir.entry.cons#1]]）。遍历得到的条目只含实现顺便拿到的属性，`directory_iterator` 不得为它调用 `refresh`（[[fs.class.directory.iterator.general#9]]）。如果实现缓存了状态，`is_directory()` 不访问文件系统；没有缓存，就会调用一次 `status(path())`。
</details>
