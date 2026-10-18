---
title: 目录项与目录遍历
summary: directory_entry（路径＋可选的缓存属性，refresh 与缓存过期，is_symlink 用 symlink_status）、directory_iterator（输入迭代器，出错或遍历完都变成尾迭代器，不产生 . 和 ..，顺序未指定，遍历中增删文件的可见性未指定，是 view 与 borrowed_range）、recursive_directory_iterator（depth、recursion_pending、disable_recursion_pending、pop，默认不跟随目录符号链接，skip_permission_denied，在尾迭代器上调用观察器是 UB，环可能使遍历不终止）；以及用 error_code 安全遍历的写法
status: done
covers: *, fs.class.directory.entry, fs.class.directory.entry.general, fs.dir.entry.cons, fs.dir.entry.mods, fs.dir.entry.obs, fs.dir.entry.io, fs.class.rec.dir.itr, fs.class.rec.dir.itr.general, fs.rec.dir.itr.members, fs.rec.dir.itr.nonmembers
since: c++17
related: filesystems, fs.class.path, fs.op.funcs, input.iterators, range.view, range.range
tags: 标准库, filesystem, 目录遍历, 迭代器
updated: 2026-10-18
---

本页覆盖 [filesystems] 中与"列出目录内容"有关的三个类：表示一个目录项的 `directory_entry`，单层遍历的 `directory_iterator`，以及递归遍历的 `recursive_directory_iterator`。

## `directory_entry`（[fs.class.directory.entry]）

### 概述与缓存（[fs.class.directory.entry.general]）

```cpp
class directory_entry {
public:
  directory_entry() noexcept = default;
  explicit directory_entry(const filesystem::path& p);
  directory_entry(const filesystem::path& p, error_code& ec);

  void assign(const filesystem::path& p);               // 及 error_code 版本
  void replace_filename(const filesystem::path& p);     // 及 error_code 版本
  void refresh();   void refresh(error_code& ec) noexcept;

  const filesystem::path& path() const noexcept;
  operator const filesystem::path&() const noexcept;
  bool exists() const;  bool is_directory() const;  bool is_regular_file() const;  bool is_symlink() const;
  // is_block_file / is_character_file / is_fifo / is_other / is_socket
  uintmax_t file_size() const;  uintmax_t hard_link_count() const;
  file_time_type last_write_time() const;
  file_status status() const;  file_status symlink_status() const;
  // 以上每个观察器都有 (error_code&) const noexcept 版本
  bool operator==(const directory_entry& rhs) const noexcept;
  strong_ordering operator<=>(const directory_entry& rhs) const noexcept;
private:
  filesystem::path path-object;   // 说明专用
};
```

- ¶1：`directory_entry` 保存一个 `path`，**并且可能**保存文件属性的附加对象，如硬链接数、状态、符号链接状态、文件大小、最后写入时间。
- ¶2：实现**应当**在目录遍历期间、属性值可得且保存它们能省去观察器的文件系统访问时，保存这些属性。这样保存的值称为**已缓存的**（cached）。
- ¶3（注）：`directory_iterator` 可以把已有的属性值直接缓存进 `directory_entry`，而不必付出调用 `refresh()` 的代价。

这样设计的原因是性能：在 POSIX 上，`readdir` 返回的 `d_type` 字段已经告诉你条目是不是目录；在 Windows 上，`FindNextFileW` 一次就返回了大小、时间和属性。把这些信息缓存起来，`entry.is_directory()` 就不必再做一次 `stat` 系统调用。

¶4 的例子说明了缓存的代价——**它可能过期**：

```cpp
for (auto&& x : directory_iterator(".")) {
  lengthy_function(x.path());   // 期间文件可能被修改：缓存变旧
  x.refresh();                  // 需要最新值时显式刷新
  std::cout << x.path() << " " << x.last_write_time() << std::endl;
}
```

在不缓存的实现上，每次 `last_write_time()` 都会访问文件系统；在缓存的实现上，用的是迭代时的快照。代码在两种实现上都可移植，但读到的值的新旧程度不同。

### 构造与修改（[fs.dir.entry.cons]、[fs.dir.entry.mods]）

- `directory_entry(p)` / `(p, ec)`：¶1 分别调用 `refresh()` / `refresh(ec)`；¶2 无错误时 `path() == p`，否则 `path() == filesystem::path()`；¶3 按 [fs.err.report] 抛异常。
- `assign(p)`：¶1 等价于 `path-object = p;` 再 `refresh()`。`replace_filename(p)`：¶3 等价于 `path-object.replace_filename(p);` 再 `refresh()`。出错时缓存属性的值未指定。
- `refresh()`：¶5 保存 `p` 所解析到的文件的当前属性值（按实现缓存的那些）。出错时报告错误，缓存值未指定。¶7（注）：`directory_iterator` 的实现**被禁止**直接或间接调用 `refresh`（见下文 ¶9）。

注意构造函数会调用 `refresh()`，所以 `directory_entry("no-such-file")` 会**抛异常**（或设置 `ec`）——不存在的路径不能用抛异常的构造函数构造目录项。

### 观察器（[fs.dir.entry.obs]）

¶1：*Returns* 中的非限定函数名指 `std::filesystem` 命名空间的成员。

| 观察器 | 返回 |
|---|---|
| `path()`、`operator const path&()` | ¶2 `path-object` |
| `exists()`、`is_block_file()`、`is_character_file()`、`is_directory()`、`is_fifo()`、`is_other()`、`is_regular_file()`、`is_socket()` | ¶3–¶18 对应的非成员函数作用于 `this->status()` |
| `is_symlink()` | ¶19 `is_symlink(this->symlink_status())`——用的是**不跟随**链接的状态 |
| `file_size()`、`hard_link_count()`、`last_write_time()` | ¶21–¶26 若已缓存，返回缓存值；否则调用对应的非成员函数 |
| `status()`、`symlink_status()` | ¶27–¶30 若已缓存，返回缓存值；否则调用 `status(path())` / `symlink_status(path())` |
| `==`、`<=>` | ¶31–¶32 比较 `path-object` |

对一个指向目录的符号链接，`is_directory()` 为真（`status` 跟随链接），`is_symlink()` 也为真。

[fs.dir.entry.io] ¶1：`operator<<(os, d)` 等价于 `os << d.path()`（所以也会加引号）。

## `directory_iterator`（[fs.class.directory.iterator]）

### 概述（[fs.class.directory.iterator.general]）

```cpp
class directory_iterator {
public:
  using iterator_category = input_iterator_tag;
  using value_type        = directory_entry;
  using difference_type   = ptrdiff_t;
  using pointer           = const directory_entry*;
  using reference         = const directory_entry&;

  directory_iterator() noexcept;
  explicit directory_iterator(const path& p);
  directory_iterator(const path& p, directory_options options);
  directory_iterator(const path& p, error_code& ec);
  directory_iterator(const path& p, directory_options options, error_code& ec);
  // 复制、移动、析构、赋值
  const directory_entry& operator*() const;
  const directory_entry* operator->() const;
  directory_iterator& operator++();
  directory_iterator& increment(error_code& ec);
  bool operator==(default_sentinel_t) const noexcept { return *this == directory_iterator(); }
  // 其他输入迭代器要求的成员
};
```

¶1：遍历一个目录（或实现定义的类目录文件）中每个文件对应的 `directory_entry` 序列，每个元素表示路径及已缓存的属性。注：递归进入子目录见 `recursive_directory_iterator`。

| 段落 | 规定 |
|---|---|
| ¶2 | 满足 *Cpp17InputIterator* |
| ¶3 | 迭代器**报告错误**或**越过最后一个元素**时，变得等于尾迭代器；默认构造函数构造尾迭代器，这是唯一合法的"结束"迭代器值 |
| ¶4 | 尾迭代器不可解引用 |
| ¶5 | 两个尾迭代器总是相等；尾迭代器不等于非尾迭代器 |
| ¶6 | 解引用得到的 `directory_entry` 的 `path()` 是"构造时给的目录实参" `/=` "目录项的文件名" |
| ¶7 | 不产生当前目录（dot）和父目录（dot-dot）的目录项 |
| ¶8 | 目录项的顺序**未指定** |
| ¶9 | 构造函数和非 const 成员把已缓存属性存进 `operator*()` 返回的 `directory_entry`；**不得直接或间接调用 `directory_entry` 的任何 `refresh` 函数**。注：存储缓存值的具体机制不对用户公开 |
| ¶10（注） | 解引用得到的路径可能并不存在——它可能是指向不存在文件的符号链接；为删除或重命名而递归遍历目录树，可能使正在跟随的符号链接失效 |
| ¶11（注） | 构造之后向目录**添加或删除**文件，后续递增是否会遇到这些目录项是**未指定**的（参见 POSIX `readdir`） |

几点推论：

- **¶6：路径是拼出来的，不是规范化的。** 用 `directory_iterator("proj")` 得到的是 `"proj/a.cpp"`；用 `directory_iterator("./proj/")` 得到的是 `"./proj/a.cpp"`。需要绝对路径就从绝对路径开始遍历。
- **¶8：顺序未指定。** 不同文件系统、不同平台、甚至同一目录的两次遍历都可能不同。需要确定性输出（测试、生成文件列表）就先收集再排序。
- **¶11：边遍历边修改是允许的，只是可见性未指定。** 删除当前条目本身是常见且安全的做法；但新建的文件可能被遍历到，也可能不会。

### 成员（[fs.dir.itr.members]）

- 默认构造：¶1 尾迭代器。
- `directory_iterator(p [, options] [, ec])`：¶2 对 `p` 所解析到的目录，构造指向第一个元素的迭代器，目录为空则构造尾迭代器。但若 `options` 含 `skip_permission_denied` 且构造时遇到"权限被拒绝"的错误，构造尾迭代器并**不报告错误**。¶3 按 [fs.err.report] 报告错误——带 `ec` 的版本出错时得到尾迭代器。¶4（注）：遍历当前目录用 `directory_iterator(".")`，而不是 `directory_iterator("")`。
- 复制/移动构造与赋值：¶5–¶8 `*this` 具有 `rhs` 原来的值；自赋值无效果。
- `operator++()` / `increment(ec)`：¶9 按输入迭代器前置递增的规定；¶11 按 [fs.err.report] 报告错误。

[fs.dir.itr.nonmembers] ¶1–¶3：`begin(iter)` 返回 `iter`，`end(iter)` 返回 `directory_iterator()`——迭代器本身就是一个范围，可以直接用于范围 `for`。

### 作为 range 与 view

[[filesystems]] 的概要把 `directory_iterator` 声明为 `enable_view` 和 `enable_borrowed_range`。于是它可以直接接范围适配器：

```cpp title="dir-iterate.cpp" ok
#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <ranges>
#include <vector>
namespace fs = std::filesystem;

int main() {
  fs::create_directories("proj/src");
  std::ofstream("proj/a.cpp"); std::ofstream("proj/b.h"); std::ofstream("proj/c.cpp");

  auto cpp = fs::directory_iterator("proj")
           | std::views::filter([](const fs::directory_entry& e) {
               return e.is_regular_file() && e.path().extension() == ".cpp"; })
           | std::views::transform([](const fs::directory_entry& e) { return e.path().filename(); });
  auto names = cpp | std::ranges::to<std::vector>();
  std::ranges::sort(names);                         // 顺序未指定：先排序再用
  for (auto& n : names) std::cout << n << ' ';      // "a.cpp" "c.cpp"
  std::cout << '\n';

  // 不抛异常的遍历：构造与 increment 都用 error_code
  std::error_code ec;
  int count = 0;
  for (fs::directory_iterator it("proj", ec), end; !ec && it != end; it.increment(ec)) ++count;
  std::cout << "entries=" << count << " error=" << bool(ec) << '\n';   // entries=4 error=0

  fs::directory_iterator bad("no-such-dir", ec);
  std::cout << (bad == fs::directory_iterator()) << ' ' << ec.message() << '\n';
  // 1 No such file or directory
  fs::remove_all("proj");
}
```

注意 `transform` 之后的迭代器不是 *Cpp17InputIterator*（`iterator_traits` 没有 `reference`），不能用 `vector(first, last)` 构造，要用 `std::ranges::to`。

!!! pitfall "范围 `for` 不能用 `error_code`"
    `for (auto& e : fs::directory_iterator(p))` 中的 `++` 调用的是会抛异常的 `operator++()`。目录在遍历中途变得不可读（被删除、权限改变、网络断开）时会抛 `filesystem_error`。需要不抛异常的遍历，就像上例那样手写循环，用 `increment(ec)`，并在每一步检查 `ec`。

## `recursive_directory_iterator`（[fs.class.rec.dir.itr]）

### 概述（[fs.class.rec.dir.itr.general]）

¶1：遍历一个目录及其子目录中的文件对应的 `directory_entry` 序列。成员与 `directory_iterator` 相同，另外有：

```cpp
directory_options options() const;
int  depth() const;
bool recursion_pending() const;
void pop();   void pop(error_code& ec);
void disable_recursion_pending();
```

- ¶2：在**不可解引用**的迭代器（包括尾迭代器）上调用 `options`、`depth`、`recursion_pending`、`pop` 或 `disable_recursion_pending`，行为未定义 {{ub}}。
- ¶3：除非另有说明，行为与 `directory_iterator` 相同（于是 ¶6–¶11 的规则——顺序未指定、不产生 `.` 和 `..`、路径是拼出来的——全部适用）。
- ¶4（注）：若被遍历的目录结构中有**环**，尾迭代器可能永远到达不了。

### 成员（[fs.rec.dir.itr.members]）

- 构造：¶2 同 `directory_iterator`，包括 `skip_permission_denied` 的处理；¶3 `options()` 等于传入的选项，未传入则为 `none`；¶5（注）同样用 `"."` 而不是 `""`；¶6（注）**默认不跟随目录符号链接**，要跟随需指定 `follow_directory_symlink`。
- 复制/移动：¶7–¶14 `options()`、`depth()`、`recursion_pending()` 与源相同。
- `options()`：¶15 构造时传入的选项；`depth()`：¶17 当前遍历的深度——初始目录为 0，其直接子目录为 1，依此类推；`recursion_pending()`：¶19 自上次构造或递增以来**没有**调用过 `disable_recursion_pending()` 时为真。三者都不抛异常。
- `operator++()` / `increment(ec)`：¶21 按输入迭代器前置递增，但：
    - ¶21.1：当前深度没有更多条目时，若 `depth() != 0` 则回到父目录继续；否则 `*this` 变为尾迭代器。
    - ¶21.2：否则，若

      ```cpp
      recursion_pending() && is_directory((*this)->status()) &&
      (!is_symlink((*this)->symlink_status()) ||
       (options() & directory_options::follow_directory_symlink) != directory_options::none)
      ```

      则**递归进入**目录 `(*this)->path()`；若选项含 `skip_permission_denied` 且进入时发生权限被拒绝的错误，把该目录当作空目录、不报告错误。
- `pop()` / `pop(ec)`：¶24 若 `depth() == 0`，`*this` 变为尾迭代器；否则停止遍历当前目录，回到父目录继续。¶26：之前 `*this` 的副本不再保证可解引用，也不再保证在 `==` 的定义域内。
- `disable_recursion_pending()`：¶27 后条件 `recursion_pending() == false`；¶28（注）用于阻止进入不想要的目录。

¶21.2 的条件值得逐项读：

1. **递归发生在 `++` 时，而不是解引用时。** 迭代器先停在目录条目本身上（你能看到它），下一次 `++` 才进入其中。所以要跳过某个目录，必须在它作为当前条目时、调用 `++` **之前**调用 `disable_recursion_pending()`。每次递增后标志自动恢复为"待递归"。
2. 判断是否为目录用的是 `status()`（跟随链接），判断是否为链接用的是 `symlink_status()`。所以默认情况下，指向目录的符号链接会**作为条目出现**，但不会被进入。
3. 打开 `follow_directory_symlink` 后，指向祖先目录的链接会造成环，¶4 说遍历可能不终止。

```cpp title="recursive-walk.cpp" ok
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

  std::set<std::string> seen;                        // 顺序未指定：放进 set 再打印
  for (auto it = fs::recursive_directory_iterator(root); it != fs::recursive_directory_iterator(); ++it) {
    if (it->is_directory() && it->path().filename() == "build")
      it.disable_recursion_pending();                // 在 ++ 之前调用：不进入 build
    seen.insert(std::to_string(it.depth()) + " " + it->path().generic_string());
  }
  for (auto& s : seen) std::cout << s << '\n';
  // 0 sandbox/build
  // 0 sandbox/src
  // 1 sandbox/src/detail
  // 1 sandbox/src/main.cpp
  // 2 sandbox/src/detail/util.hpp

  std::cout << "removed " << fs::remove_all(root) << " files\n";   // removed 8 files
}
```

[fs.rec.dir.itr.nonmembers] ¶1–¶3：与 `directory_iterator` 相同的 `begin`/`end`，同样被声明为 view 和 borrowed range。

!!! pitfall "在尾迭代器上调用 `depth()` 是 UB"
    写成 `for (auto it = ...; ; ++it) { if (it.depth() > 3) ...; if (it == end) break; }` 之类的循环时，若在判断是否到尾之前调用了 `depth()`、`pop()` 或 `disable_recursion_pending()`，到达尾部时就是 {{ub}}（[[fs.class.rec.dir.itr.general#2]]）。先判断是否到尾，再使用这些成员。

## 思考题

<details markdown="1">
<summary>1. 用 <code>recursive_directory_iterator</code> 遍历时，对当前条目调用 <code>fs::remove_all(it-&gt;path())</code> 删除一个子目录，然后 <code>++it</code>，安全吗？</summary>

对**目录**条目来说不安全。`++` 会因为 `recursion_pending()` 为真且（缓存的）状态表明它是目录而尝试进入它（[[fs.rec.dir.itr.members#21]]），而目录已经不存在，于是抛 `filesystem_error`（或在 `increment(ec)` 中设置错误、迭代器变为尾迭代器）。删除前先调用 `it.disable_recursion_pending()`。删除普通文件则没有这个问题；至于删除对后续遍历的影响，按 [[fs.class.directory.iterator.general#11]] 是未指定的。
</details>

<details markdown="1">
<summary>2. 为什么 <code>directory_iterator</code> 被禁止调用 <code>refresh()</code>？</summary>

`refresh()` 会重新访问文件系统获取属性（典型地是一次 `stat`）。目录遍历本来就能从 `readdir`/`FindNextFileW` 免费得到一部分属性，规定 [[fs.class.directory.iterator.general#9]] 禁止迭代器调用 `refresh`，保证遍历本身不会为每个条目引入额外的系统调用；需要的属性由观察器在被调用时按需获取（未缓存时）。
</details>

## 小结

| 类 | 要点 |
|---|---|
| `directory_entry` | 路径＋可选缓存属性；构造/`assign`/`refresh` 会访问文件系统；缓存可能过期；`is_symlink` 不跟随链接 |
| `directory_iterator` | 输入迭代器；出错或结束都变成尾迭代器；无 `.`/`..`；顺序未指定；遍历中增删的可见性未指定；是 view |
| `recursive_directory_iterator` | 在 `++` 时决定是否递归；`disable_recursion_pending` 必须在 `++` 前调用；默认不跟随目录符号链接；在尾迭代器上调用 `depth` 等是 UB |
| 错误处理 | 范围 `for` 只能用抛异常的 `++`；不抛异常的遍历要手写循环并使用 `increment(ec)` |
