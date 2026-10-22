---
title: Directory entries and directory iteration
summary: "A directory_entry is a path plus possibly cached file attributes; directory_iterator walks one directory level, recursive_directory_iterator walks recursively; the order is unspecified, an error turns the iterator into the end iterator, and recursion is decided at ++."
updated: 2026-10-19
---

!!! tldr
    - The order of the entries produced is unspecified, and `.` and `..` are not included; if you need a definite order, collect and then sort.
    - A `directory_entry` can cache file attributes obtained incidentally during iteration, saving a `stat`; the price is that the cache may go stale, and you call `refresh()` when needed.
    - A range-based `for` can only use the throwing `++`; if you do not want to deal with exceptions, write the loop by hand with `increment(ec)`.
    - `recursive_directory_iterator` decides whether to descend into the current directory only at `++`, so `disable_recursion_pending()` must be called before `++`; by default it does not descend into symbolic links to directories.
    - Calling members such as `depth()` and `pop()` on the end iterator is UB.

## Listing a directory [fs.class.directory.iterator]

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
  std::ranges::sort(names);              // order is unspecified: sort first
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

A `directory_iterator` is itself a range: `begin(it)` in [fs.dir.itr.nonmembers] returns `it`, and `end(it)` returns a default-constructed **end iterator**. The synopsis in [[filesystems]] also declares it a view and a borrowed range, so range adaptors can be applied to it directly.

### The rules of the iterator ([fs.class.directory.iterator.general])

- ¶1 It iterates over the `directory_entry` for each file in a directory. ¶2 It is an input iterator and supports only a single pass.
- ¶3 When the iterator reports an error or advances past the last entry, it becomes equal to the end iterator. A default-constructed iterator is the end iterator. ¶4–¶5 The end iterator is not dereferenceable, and two end iterators are always equal.
- ¶6 An entry's `path()` is the directory path passed at construction `/` the entry's filename, without normalization. Starting from `"proj"` gives `"proj/a.cpp"`; starting from `"./proj/"` gives `"./proj/a.cpp"`. If you need absolute paths, start iterating from an absolute path.
- ¶7 `.` and `..` are not produced.
- ¶8 The order of the entries is unspecified. It may differ between file systems, between platforms, and even between two iterations of the same directory.
- The note in paragraph 10 reminds us that the path obtained need not exist: it may be a dangling symbolic link.
- The note in paragraph 11 says that if files are added to or removed from the directory after construction, whether subsequent increments encounter those entries is unspecified (consistent with POSIX `readdir`). Removing the current entry itself is safe; newly created files may or may not be visited.

### Construction and increment ([fs.dir.itr.members])

¶2 `directory_iterator(p)` refers to the first entry of the directory `p`, or is the end iterator if the directory is empty. ¶3 Errors are reported per [fs.err.report]: the version without `error_code` throws `filesystem_error`, while the version with `ec` sets `ec` and yields the end iterator, as with `bad` in the example above.

If the options contain `directory_options::skip_permission_denied` and permission is denied at construction, the result is the end iterator with no error reported. The note in paragraph 4 reminds us that to iterate over the current directory you write `directory_iterator(".")`, not `directory_iterator("")`.

¶9–¶11 `operator++()` and `increment(ec)` move to the next entry, likewise reporting errors per [fs.err.report].

!!! pitfall "A range-based `for` cannot use an `error_code`"
    The `++` in `for (auto& e : fs::directory_iterator(p))` calls the throwing `operator++()`. If the directory becomes unreadable midway (deleted, permissions changed, network gone), `filesystem_error` is thrown. For non-throwing iteration, write the loop by hand as in the example above, using `increment(ec)` and checking `ec` at each step.

    Also, the iterator after `transform` does not meet the old *Cpp17InputIterator* requirements and cannot be passed to `vector(first, last)`; use `std::ranges::to`.

## Directory entries [fs.class.directory.entry]

### Cached attributes ([fs.class.directory.entry.general])

¶1 A `directory_entry` stores a `path` and may also store some attributes of the file: hard link count, status, symlink status, file size, and last write time. ¶2 Implementations should store these attributes if they are available during directory iteration and storing them would allow the observers to avoid a file system access. Values stored this way are called **cached** attributes.

This design is for performance. The `d_type` returned by POSIX `readdir` already says whether an entry is a directory, and Windows `FindNextFileW` returns the size, times and attributes all at once. With these cached, `entry.is_directory()` does not need another `stat`.

The price is that the cache may go stale. The example in paragraph 4:

```cpp
for (auto&& x : directory_iterator(".")) {
  lengthy_function(x.path());  // the file may be modified meanwhile
  x.refresh();                 // refresh explicitly when the latest value is needed
  std::cout << x.path() << " " << x.last_write_time() << std::endl;
}
```

An implementation that does not cache accesses the file system each time `last_write_time()` is called; one that caches returns a snapshot from the time of iteration. This code works on both, reading values of different freshness.

### Observers ([fs.dir.entry.obs])

| Observer | Returns |
|---|---|
| `path()`, `operator const path&()` | ¶2 the stored path |
| `exists()`, `is_directory()`, `is_regular_file()` and so on | ¶3–¶18 the corresponding non-member function applied to `status()` |
| `is_symlink()` | ¶19 `is_symlink(symlink_status())`, not following the link |
| `file_size()`, `hard_link_count()`, `last_write_time()` | ¶21–¶26 the cached value if cached, otherwise calls the corresponding non-member function |
| `status()`, `symlink_status()` | ¶27–¶30 the cached value if cached, otherwise calls `status(path())` or `symlink_status(path())` |
| `==`, `<=>` | ¶31–¶32 compare the paths |

`status()` follows symbolic links and `symlink_status()` does not; see [[fs.op.funcs]]. So for a symbolic link to a directory, both `is_directory()` and `is_symlink()` are true.

Each observer has a `noexcept` version taking an `error_code&`. [fs.dir.entry.io] ¶1 `os << d` is equivalent to `os << d.path()`, so it adds quotes too.

### Construction and modification ([fs.dir.entry.cons], [fs.dir.entry.mods])

¶1 `directory_entry(p)` and `directory_entry(p, ec)` call `refresh()`, which means they access the file system. ¶2 Without error, `path() == p`; on error, `path()` is empty. So `directory_entry("no-such-file")` throws; for a path that may not exist, use the version with `ec`.

[fs.dir.entry.mods] ¶1 `assign(p)` is equivalent to replacing the path and then `refresh()`; ¶3 `replace_filename(p)` is equivalent to calling `replace_filename(p)` on the path and then `refresh()`. ¶5 `refresh()` re-reads and stores the current attribute values; on error it reports the error, and the cached values are unspecified.

[fs.class.directory.iterator.general] ¶9 specifies that `directory_iterator` stores cached attributes in the `directory_entry` it returns, but shall not directly or indirectly call `refresh`. The note in paragraph 7 of [fs.dir.entry.mods] repeats this. So iteration itself does not do an extra `stat` per entry; attributes not cached are fetched by the observers when they are called.

## Recursive iteration [fs.class.rec.dir.itr]

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

  std::set<std::string> seen;  // order is unspecified: put into a set
  for (auto it = fs::recursive_directory_iterator(root);
       it != fs::recursive_directory_iterator(); ++it) {
    if (it->is_directory() && it->path().filename() == "build")
      it.disable_recursion_pending();  // called before ++
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

`build` itself appears in the result, but `obj` beneath it does not, because recursion into it was turned off before `++`.

### Additional members ([fs.class.rec.dir.itr.general], [fs.rec.dir.itr.members])

¶1 `recursive_directory_iterator` iterates over a directory and all its subdirectories. ¶3 Unless otherwise specified, it behaves the same as `directory_iterator`, so the rules about unspecified order, no `.` and `..`, and composed paths all apply. It has these extra members:

| Member | Purpose |
|---|---|
| `options()` | ¶15 the options passed at construction, or `none` if none were passed |
| `depth()` | ¶17 the current depth: 0 for entries in the starting directory, 1 for those in its subdirectories, and so on |
| `recursion_pending()` | ¶19 true if `disable_recursion_pending()` has not been called since the last construction or increment |
| `disable_recursion_pending()` | ¶27–¶28 makes the next `++` not descend into the current directory |
| `pop()`, `pop(ec)` | ¶24 becomes the end iterator if `depth() == 0`; otherwise abandons the remaining entries of the current directory and continues in the parent |

¶7–¶14 Copying and moving preserve `options()`, `depth()` and `recursion_pending()`. ¶26 After `pop()`, earlier copies are no longer guaranteed to be dereferenceable or comparable.

### When `++` descends into a subdirectory (¶21)

¶21 Increment proceeds as specified for input iterators, with two additions:

- ¶21.1 If the current directory has no more entries, then if `depth() != 0`, it returns to the parent directory and continues; otherwise it becomes the end iterator.
- ¶21.2 Otherwise, it descends into the directory `(*this)->path()` if the following condition holds:

```cpp
recursion_pending() && is_directory((*this)->status()) &&
(!is_symlink((*this)->symlink_status()) ||
 (options() & directory_options::follow_directory_symlink)
   != directory_options::none)
```

Three things can be read from this condition:

1. Recursion happens at `++`. The iterator first stops on the directory entry itself, and only the next `++` descends into it. To skip a directory, you must call `disable_recursion_pending()` while it is the current entry, before `++`. The flag resets automatically after each increment.
2. Whether it is a directory is decided with `status()` (following links), and whether it is a link with `symlink_status()`. So by default, a symbolic link to a directory appears as an entry but is not descended into (the note in paragraph 6).
3. With `follow_directory_symlink` on, a link to an ancestor directory forms a cycle. The note in paragraph 4 of [fs.class.rec.dir.itr.general] says the end iterator may then never be reached.

If permission is denied when descending into a subdirectory and the options contain `skip_permission_denied`, the directory is treated as empty, with no error reported.

!!! pitfall "Calling `depth()` on the end iterator is UB"
    [[fs.class.rec.dir.itr.general#2]] specifies that calling `options`, `depth`, `recursion_pending`, `pop` or `disable_recursion_pending` on an iterator that is not dereferenceable (including the end iterator) is undefined behavior {{ub}}. In a loop, check for the end first, then use these members.

## Questions

!!! question "Question 1"
    While iterating with `recursive_directory_iterator`, you call `fs::remove_all(it->path())` on the current entry to remove a subdirectory, then `++it`. Is that safe?

<details markdown="1">
<summary>Answer</summary>

Not for a directory entry. `recursion_pending()` is still true and the cached status says it is a directory, so `++` tries to descend into it ([[fs.rec.dir.itr.members#21]]), but the directory no longer exists. In our tests libc++ throws `filesystem_error` with the message `attempting recursion into "t/a": No such file or directory`; with `increment(ec)`, `ec` is set instead. Call `it.disable_recursion_pending()` before removing.

Removing a regular file does not have this problem. How removal affects the rest of the iteration is unspecified per [[fs.class.directory.iterator.general#11]].
</details>

!!! question "Question 2"
    Do `directory_entry("a/b")` and an entry for `a/b` produced by `directory_iterator` necessarily access the file system the same number of times when `is_directory()` is called?

<details markdown="1">
<summary>Answer</summary>

Not necessarily. The constructor calls `refresh()`, so the attributes the implementation chooses to cache are read and stored at construction ([[fs.dir.entry.cons#1]]). An entry obtained by iteration contains only the attributes the implementation got incidentally, and `directory_iterator` may not call `refresh` for it ([[fs.class.directory.iterator.general#9]]). If the implementation cached the status, `is_directory()` does not access the file system; if not, it calls `status(path())` once.
</details>
