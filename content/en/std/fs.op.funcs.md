---
title: Filesystem operation functions and file_status
summary: "The non-member functions in <filesystem> that access the file system: status versus symlink_status, how exists and is_* differ in error reporting, the differences among absolute/canonical/weakly_canonical/relative, creating, copying, removing, renaming and permissions, and current_path as process-wide global state."
updated: 2026-10-19
---

!!! tldr
    - Any file system operation can fail; even `exists(p)` can throw. Every function has a version that throws `filesystem_error` and a version taking an `error_code&`.
    - `status` follows symbolic links and `symlink_status` does not; for a dangling link, `exists(p)` is false, yet the name really is taken.
    - When the file does not exist, `exists(p, ec)` clears `ec`, while `is_regular_file(p, ec)` sets `ec` to an error.
    - Only `canonical` requires the path to exist; `weakly_canonical` resolves the existing prefix and only lexically normalizes the rest; `absolute` just prepends the current directory.
    - `create_directory` returns `false` rather than an error for an existing directory; `remove` does not report an error for a nonexistent file; `copy` without `recursive` copies only one level.

## Any operation can fail [fs.op.funcs.general]

¶1 The functions in this subclause query or modify files, including directories, in external storage. The note in paragraph 2 points out that errors such as hardware failures, network failures and file system races ([[fs.race.behavior]]) are common in file system operations, so any operational function, no matter how innocuous it looks, may encounter an error. For example, `exists(p)` throws for a path whose directory has no search permission.

Almost every function comes in a pair. Per [fs.err.report] in [[filesystems]], the version without `error_code&` throws `filesystem_error` on error; the version with `error_code& ec` sets `ec` on error and returns an agreed value (usually an empty path, `false`, or `static_cast<uintmax_t>(-1)`), and clears `ec` on success.

## File status

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

[fs.class.file.status.general] ¶1 A `file_status` stores a file's type and permissions; it is a simple value type ([fs.file.status.cons], [fs.file.status.obs], [fs.file.status.mods]). The two are kept together because a single `stat` yields both; afterwards, overloads that take a `file_status`, such as `is_directory(s)` and `exists(s)`, read this value without accessing the file system again.

### `status` and `symlink_status`

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

[fs.op.status] ¶4 `status(p, ec)` determines the attributes of the file `p` resolves to as if by POSIX `stat`. ¶7 If a symbolic link is encountered during resolution, resolution continues using the link's contents, i.e. it follows the link. ¶6 The return value covers two cases:

- If the underlying call succeeds, the `S_ISREG`, `S_ISDIR` and similar macros give `regular`, `directory`, `block`, `character`, `fifo` or `socket`; implementation-defined types return the corresponding constant, and anything else returns `unknown`; the permissions are `st_mode & perms::mask` (¶5).
- If the underlying call reports an error, `ec` is set to that error. If the error indicates that some element of the path does not exist, it returns `not_found`; if the path can be resolved but the attributes cannot be determined, `unknown`; otherwise `none`. Note 3 explains the difference among the three: known not to exist, exists but attributes unknown, and cannot even tell whether it exists.

¶1–¶3 `status(p)` without `ec` throws only when the result would be `none`. The note in paragraph 3 stresses that `not_found` and `unknown` are not failures, so `status("no-such-file")` returns `file_type::not_found` normally. [fs.op.status.known] ¶1 `status_known(s)` is just `s.type() != file_type::none`.

[fs.op.symlink.status] ¶1 `symlink_status` is the same as `status`, except as if by POSIX `lstat`. ¶3 If `p` itself is a symbolic link, it returns `file_type::symlink`; ¶5 resolution stops there and does not follow it.

!!! pitfall "Dangling links and `exists`"
    In the example above, `dangling` points to a nonexistent file. `exists` uses `status`, which follows the link, finds no target, and so returns `false`. But the name really is in the directory, and `create_symlink` with that name would fail. To check whether a name is taken, use `exists(fs::symlink_status(p))`.

### `exists` and `is_*`

| Function | Specification |
|---|---|
| `exists(s)` | [fs.op.exists] ¶1 `status_known(s) && s.type() != file_type::not_found` |
| `exists(p)`, `exists(p, ec)` | ¶2–¶4 let `s = status(p)` (or `status(p, ec)`); the version with `ec` clears `ec` if `status_known(s)`; returns `exists(s)` |
| `is_regular_file(s)` and so on | `s.type() == file_type::regular`; likewise for `directory`, `symlink`, `block`, `character`, `fifo`, `socket` |
| `is_regular_file(p, ec)` | [fs.op.is.regular.file] ¶4–¶5 sets `ec` as `status(p, ec)` does; returns `false` on error |
| `is_other(s)` | [fs.op.is.other] ¶1 exists, but is not a regular file, directory or symbolic link |
| `is_symlink(p)` | [fs.op.is.symlink] ¶2 `is_symlink(symlink_status(p))`, the only `is_*` that uses `symlink_status` |
| `is_empty(p)` | [fs.op.is.empty] ¶1 for a directory, `directory_iterator(p) == directory_iterator()`; otherwise `file_size(p) == 0` |

`exists` and `is_*` do not treat a nonexistent file the same way:

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

`exists(p, ec)` treats nonexistence as a normal answer: for `not_found`, `status_known` is true, so `ec` is cleared. `is_regular_file(p, ec)` passes on the `ec` set by `status(p, ec)`; the note in paragraph 4 of [fs.op.is.regular.file] says explicitly that `none`, `not_found` and `unknown` all leave `ec` holding an error, so `ec` keeps "No such file or directory". When using the `error_code` versions, handle "an error occurred" separately from "the answer is no"; when finer distinctions are needed, call `status(p, ec)` directly and check `type()`.

### Other attributes

| Function | Specification | `ec` version returns on error |
|---|---|---|
| `equivalent(p1, p2)` | [fs.op.equivalent] ¶1 the same entity if both reside on the same device at the same location (on POSIX, both `st_dev` and `st_ino` equal); ¶4 either not existing is an error | `false` |
| `file_size(p)` | [fs.op.file.size] ¶1 nonexistence is an error; ¶2 for a regular file, returns the size in bytes; for other types, the result is implementation-defined {{impl}} | `uintmax_t(-1)` |
| `hard_link_count(p)` | [fs.op.hard.lk.ct] ¶1 the number of hard links | `uintmax_t(-1)` |
| `last_write_time(p)` | [fs.op.last.write.time] ¶1 the time of last modification, of type `file_time_type` | `file_time_type::min()` |
| `last_write_time(p, t)` | ¶3 sets the modification time; the note in paragraph 5 says `last_write_time(p) == t` is not guaranteed afterwards, as the file system's time resolution may be coarser | — |
| `space(p)` | [fs.op.space] ¶1 as if by POSIX `statvfs`, obtaining `capacity`, `free` and `available`, with any member that cannot be determined set to `uintmax_t(-1)`; ¶3 `available` may be less than `free` (space reserved for privileged users) | all `uintmax_t(-1)` |

`file_time_type` is `chrono::time_point<chrono::file_clock>` ([[time.clock.file]]). The epoch of `file_clock` is unspecified; to convert to system time, use `clock_cast<system_clock>` or `file_clock::to_sys`.

## Turning a path into an absolute path

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

`absolute` keeps the `..`, `.` and symbolic link as is; `weakly_canonical` resolves the existing prefix `cz/link/sub` (`link` replaced by `real`), then appends the nonexistent `not-yet/file.txt`; `canonical` reports an error because the path does not exist.

| Function | Accesses the file system | Requires existence | Resolves symbolic links | Result |
|---|---|---|---|---|
| `absolute(p)` | should not | no | no | absolute path, not necessarily normalized |
| `canonical(p)` | yes | yes | yes | absolute path with no symbolic links, `.` or `..` |
| `weakly_canonical(p)` | yes | no | only for the existing prefix | normal form |
| `relative(p, base)` | yes | no | yes | `weakly_canonical(p).lexically_relative(weakly_canonical(base))` |
| `proximate(p, base)` | yes | no | yes | same, using `lexically_proximate` instead |
| `p.lexically_normal()` and the like | no | no | no | see [[fs.class.path]] |

- [fs.op.absolute] ¶1 Composes, according to the operating system's rules, an absolute path referring to the same location. The note in paragraph 6 strongly encourages implementations not to query external storage and not to treat a nonexistent path as an error. The example in paragraph 7: on POSIX, `absolute(p)` is simply `current_path() / p`; on Windows it may be equivalent to `GetFullPathNameW`. The note in paragraph 5 suggests considering `canonical` when symbolic links need resolving.
- [fs.op.canonical] ¶1–¶2 Converts to an absolute path with no symbolic link, dot or dot-dot elements, referring to the same object as `absolute(p)`. ¶4 `p` not existing is an error.
- [fs.op.weakly.canonical] ¶1 Uses `status` to find the longest existing prefix of `p`, calls `canonical` on it, then appends the remaining elements with `/=`. ¶2 The result is in normal form.
- [fs.op.relative], [fs.op.proximate] ¶3 are defined as in the table above; `base` defaults to `current_path()`.

### The current directory and the temporary directory

[fs.op.current.path] ¶1 `current_path()` returns the absolute path of the current working directory, as if by POSIX `getcwd`. ¶3 The current working directory is associated with the process and is the starting location for resolving relative paths. ¶5–¶6 `current_path(p)` behaves as if by POSIX `chdir`, after which `equivalent(p, current_path())`.

The notes in paragraphs 4 and 8 both warn that on many operating systems the current path is a dangerous global variable that may be changed unexpectedly by third-party libraries, system library functions, or another thread.

!!! pitfall "Do not call `current_path(p)` in multithreaded programs"
    The working directory is shared by the whole process. After one thread calls `current_path(p)`, every file operation on a relative path in other threads, including `std::ifstream("x.txt")`, resolves against the new directory. The standard library cannot synchronize this external state for you. Library code should accept absolute paths or an explicit base directory rather than rely on the working directory.

[fs.op.temp.dir.path] ¶1–¶2 `temp_directory_path()` returns a directory suitable for temporary files, reporting an error if it does not exist or is not a directory. The example in paragraph 5: on POSIX, an implementation might check the environment variables `TMPDIR`, `TMP`, `TEMP` and `TEMPDIR` in turn, falling back to `/tmp`.

## Creating

| Function | Specification |
|---|---|
| `create_directory(p)` | [fs.op.create.directory] ¶1 as if by POSIX `mkdir(p, perms::all)`; a failure because `p` already is a directory is not reported as an error; ¶2 returns `true` if a directory was created, otherwise `false` |
| `create_directory(p, existing_p)` | ¶4 creates the directory and copies attributes from `existing_p`; which attributes are copied is operating system dependent |
| `create_directories(p)` | [fs.op.create.directories] ¶1 calls `create_directory` for each element of `p` that does not exist; ¶2 returns `true` if a directory was created |
| `create_symlink(to, link)` | [fs.op.create.symlink] ¶1–¶2 as if by POSIX `symlink`; `link` becomes a symbolic link with contents `to` |
| `create_directory_symlink(to, link)` | [fs.op.create.dir.symlk] same; the note in paragraph 4 explains that some systems (such as Windows) require the link to be identified as a link to a directory at creation |
| `create_hard_link(to, link)` | [fs.op.create.hard.lk] ¶1–¶2 as if by POSIX `link`, after which `equivalent(to, link)`; the note in paragraph 4 says some systems or file systems (such as FAT) do not support hard links |

- The permission argument of `mkdir` is `perms::all` (0777); the actual permissions still pass through the process umask, usually giving 0755.
- The return value of `create_directory` tells whether the directory was created by this call. If two processes create the same directory concurrently, only one gets `true`, which can be used to implement "whoever creates it owns it". If `p` exists but is not a directory, an error is still reported.
- The contents `to` of a symbolic link are stored as is and later resolved relative to the directory containing the link, not the current working directory. `create_symlink("real.txt", "d/link")` creates a link pointing to `d/real.txt`.

## Copying

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
  fs::copy("ops/d1", "ops/d2");  // copies only one level
  fs::copy("ops/d1", "ops/d3", fs::copy_options::recursive);
  std::cout << fs::exists("ops/d2/a.txt") << fs::exists("ops/d2/sub")
            << fs::exists("ops/d3/sub/b.txt") << '\n';  // 101

  try {
    fs::copy_file("ops/d1/a.txt", "ops/d2/a.txt");  // the target exists
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

¶3 `copy_options` is divided into groups ([fs.enum.copy.opts]), and at most one option from each group may be specified, otherwise a precondition is violated. The rules of ¶4:

1. ¶4.1 Report an error if: `from` is not a regular file; `to` exists but is not a regular file; `to` exists and is the same file as `from`; or `to` exists and none of `skip_existing`, `overwrite_existing` and `update_existing` is in the options.
2. ¶4.2 Otherwise, copy the contents and attributes of `from` to `to` if: `to` does not exist; `overwrite_existing` is specified; or `update_existing` is specified and `from` is newer than `to`.
3. ¶4.3 Otherwise do nothing.

¶5 Returns `true` if copied, otherwise `false`. The second `copy_file` in the example specifies `skip_existing`, so it returns `false` without reporting an error.

### `copy` [fs.op.copy]

`copy(from, to, options)` can copy files, directories and symbolic links. The algorithm of ¶4:

1. ¶4.1–¶4.3 First obtain the statuses `f` (source) and `t` (target). If `create_symlinks` or `skip_symlinks` is specified, use `symlink_status`; if `copy_symlinks` is specified, use `symlink_status` for the source and `status` for the target; otherwise use `status` for both.
2. ¶4.4 If either is an implementation-defined file type, the effects are implementation-defined.
3. ¶4.5 Report an error if: the source does not exist; the two are the same file; either is of an `is_other` type; or the source is a directory and the target is a regular file.
4. ¶4.6 If the source is a symbolic link: if `skip_symlinks` is specified, return; if the target does not exist and `copy_symlinks` is specified, copy the link itself; otherwise report an error.
5. ¶4.7 If the source is a regular file: if `directories_only` is specified, return; if `create_symlinks` or `create_hard_links` is specified, create the corresponding link; if the target is a directory, `copy_file(from, to / from.filename(), options)`; otherwise `copy_file(from, to, options)`.
6. ¶4.8 If the source is a directory and `create_symlinks` is specified: report an `errc::is_a_directory` error.
7. ¶4.9 If the source is a directory, and either `recursive` is specified or `options == copy_options::none`: if the target does not exist, create it with `create_directory(to, from)`, then behave as if executing

   ```cpp
   for (const directory_entry& x : directory_iterator(from))
     copy(x.path(), to / x.path().filename(),
          options | copy_options::in-recursive-copy);
   ```

   *in-recursive-copy* is an option bit not exposed publicly.
8. ¶4.10–¶4.11 Otherwise the version with `ec` clears `ec`, and the version without does nothing.

Step 7 explains why `d2` in the example has no `sub`. With `options == none`, it enters the source directory and copies its direct entries one by one. The options passed down to the recursive calls have the extra *in-recursive-copy* bit and are no longer equal to `none`; at the next level, the subdirectory `sub` has neither `recursive` nor options equal to `none`, so it falls through to step 8 and nothing happens. The example in paragraph 7 is about exactly this: without `recursive`, only one level of files is copied.

¶6 Within the version with `ec`, every library function called that has an `error_code` version must use that version, so the whole copy never throws `filesystem_error`. However, the function is not marked `noexcept` and may still throw `bad_alloc`.

[fs.op.copy.symlink] `copy_symlink(existing, new)` is equivalent to creating a new symbolic link with the result of `read_symlink(existing)`. [fs.op.read.symlink] `read_symlink(p)` returns the contents of the link; `p` not being a symbolic link is an error.

## Removing, renaming, size and permissions

```cpp run title="rename-links.cpp" ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::create_directory("rn");
  std::ofstream("rn/x.txt") << "x";
  std::ofstream("rn/y.txt") << "yyyy";
  fs::rename("rn/x.txt", "rn/y.txt");  // y.txt is replaced
  std::cout << fs::file_size("rn/y.txt") << ' '
            << fs::exists("rn/x.txt") << '\n';           // 1 0

  fs::create_hard_link("rn/y.txt", "rn/y2.txt");
  std::cout << fs::equivalent("rn/y.txt", "rn/y2.txt") << ' '
            << fs::hard_link_count("rn/y.txt") << '\n';  // 1 2
  bool r1 = fs::remove("rn/y.txt");
  bool r2 = fs::remove("rn/y.txt");   // already gone: not an error
  std::cout << r1 << ' ' << r2 << ' '
            << fs::exists("rn/y2.txt") << '\n';          // 1 0 1
  fs::remove_all("rn");
}
```

After one hard link is removed, the file can still be accessed through the other name, `y2.txt`.

| Function | Specification |
|---|---|
| `remove(p)` | [fs.op.remove] ¶1 if `exists(symlink_status(p))`, removes `p` as if by POSIX `remove`; Note 1: a symbolic link itself is removed, not its target; ¶3 returns `true` if removed, otherwise `false`; Note 2: `p` not existing is not an error |
| `remove_all(p)` | [fs.op.remove.all] ¶1 recursively removes the contents of `p`, then `p` itself, removing only the link for symbolic links; ¶3 returns the number of files removed, or `uintmax_t(-1)` from the `ec` version on error |
| `rename(old_p, new_p)` | [fs.op.rename] ¶1 as if by POSIX `rename`; does nothing if the two are the same file; if `new_p` is an existing non-directory file, it is removed; if it is an existing directory, an empty one is removed on POSIX, and it may be an error on other systems |
| `resize_file(p, n)` | [fs.op.resize.file] ¶1 as if by POSIX `truncate`, after which `file_size(p) == n` |
| `permissions(p, prms, opts)` | [fs.op.permissions] ¶1 exactly one of `replace`, `add` and `remove` must be present in `opts`; ¶2 applies the operation to the file `p` resolves to (or to the link itself if `nofollow` is specified and `p` is a symbolic link), as if by POSIX `fchmodat`; ¶5 the `ec` version without `opts` behaves as if `opts` were `replace` |

`rename` overwrites an existing file, so it can be used to replace a file's contents atomically: first write to a temporary file in the same directory, then `rename` it to the target name. Other processes see either the old file or the new one. The standard itself says only "as if by POSIX `rename`"; the atomicity is a guarantee given by POSIX.

## Questions

!!! question "Question 1"
    What does `fs::file_size(dir)` return for a directory?

<details markdown="1">
<summary>Answer</summary>

It is implementation-defined ([[fs.op.file.size#2]]); the standard specifies only that a regular file returns its size in bytes. An implementation may return the directory's `st_size`, or report an error. In our tests libc++ reports the error "Is a directory", and the `ec` version returns `uintmax_t(-1)`. For portable behavior, check `is_regular_file` first.
</details>

!!! question "Question 2"
    Why does `status(p)` not throw for a nonexistent file, while `file_size(p)` does?

<details markdown="1">
<summary>Answer</summary>

The job of `status` is to report the file's status, and "does not exist" is a legitimate answer (`file_type::not_found`); it throws only when it cannot even determine whether the file exists (`none`) ([[fs.op.status#1]], [[fs.op.status#3]]). `file_size` has to return a size, and a nonexistent file has none, so [[fs.op.file.size#1]] specifies that it reports an error when `exists(p)` is false.
</details>

!!! question "Question 3"
    `dir` is an existing directory. What is the result of `fs::copy("a.txt", "dir")`? And of `fs::copy_file("a.txt", "dir")`?

<details markdown="1">
<summary>Answer</summary>

`copy` follows [[fs.op.copy#4.7.4]]: the source is a regular file and the target is a directory, so it calls `copy_file("a.txt", "dir/a.txt", options)`, copying the file into the directory. `copy_file` has no such handling; [[fs.op.copy.file#4.1.2]] says an error is reported when the target exists but is not a regular file.
</details>
