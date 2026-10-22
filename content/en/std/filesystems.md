---
title: File systems library
summary: "The general rules of std::filesystem: what files, directories and links are, the POSIX-based conformance rules, why file system races are undefined behavior, the two ways of reporting errors (throwing and setting an error_code), and the enumerations file_type, copy_options, perms and others."
updated: 2026-10-19
---

!!! tldr
    - The file system is shared state outside the process. Behavior is undefined if calls to `<filesystem>` functions introduce a file system race, so do not check first and then act; act directly and check the result.
    - Most functions come in pairs: one throws `filesystem_error` on error, the other writes the error into an `error_code&` parameter and clears it on success.
    - The `error_code&` versions are not necessarily `noexcept`; they still throw `bad_alloc` when memory runs out.
    - Behavior is specified with reference to POSIX; when an implementation cannot provide it, it must report an error rather than silently give a wrong result.
    - In `file_type`, `none` means an error occurred, `not_found` means the file does not exist (not an error), and `unknown` means the file exists but its type is unknown.

```cpp title="no-toctou.cpp" run ok
#include <filesystem>
#include <fstream>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  const fs::path dir = "work", lock = "work/app.lock";

  // no need to exists() first: create_directory returns false if the directory exists, not an error
  std::error_code ec;
  bool created = fs::create_directory(dir, ec);
  std::cout << "created=" << created << " ec=" << ec.value() << '\n';  // created=1 ec=0

  // exclusive creation: check and create are one atomic operation (C++23 noreplace, i.e. fopen's "x")
  std::ofstream first(lock, std::ios_base::out | std::ios_base::noreplace);
  std::ofstream second(lock, std::ios_base::out | std::ios_base::noreplace);
  std::cout << "first=" << first.is_open() << " second=" << second.is_open() << '\n';  // 1 0

  first.close();
  // remove returns false if the file does not exist; no need to check first either
  std::cout << "removed=" << fs::remove(lock) << " again=" << fs::remove(lock) << '\n';  // 1 0
  fs::remove(dir);
}
```

`<filesystem>` (C++17, derived from Boost.Filesystem and the Filesystem TS) handles two kinds of things: paths, `std::filesystem::path`, a value type concerned only with string syntax ([[fs.class.path]]); and objects in the file system, including directory iteration ([[fs.class.directory.iterator]]) and operations such as status queries, copying, renaming, removal and permissions ([[fs.op.funcs]]). Reading and writing file contents is not its business; that belongs to file streams ([[file.streams]]).

This page covers the rules that run through the whole library: terminology, conformance, races, error reporting and the enumeration types.

## Files, directories and links [fs.general]

¶1–¶3 A **file system** is a collection of files and their attributes. A **file** is an object within a file system that holds user or system data; it can be read, written, or both, and has attributes such as its type. File types include regular files and directories, and implementations may support other types, such as symbolic links.

¶4 A **directory** is a file that acts as a container of directory entries, each of which records information about another file. A directory's parent directory both contains the directory's entry and is represented within it as `..`; the parent directory of any other file is the directory containing its entry.

¶5 A **link** associates a filename with a file; several links can associate names with the same file.

- A **hard link** refers to an existing file. Only when the last hard link is removed is the file itself removed. The standard's note likens a hard link to a shared-ownership smart pointer to a file.
- A **symbolic link** is a type of file whose content is a string; when path resolution encounters it, resolution continues with that string instead. The note likens it to a raw pointer to a file: if the file it refers to does not exist, it is called a dangling symbolic link.

These two analogies match actual behavior: removing a hard link is like decrementing a reference count; after the target of a symbolic link is removed, the link itself still exists but dangles. This is also why `status` follows symbolic links and `symlink_status` does not ([[fs.op.funcs]]).

## POSIX as the reference [fs.conformance]

[fs.conformance.general] ¶1 Conformance is specified in terms of behavior. Ideal behavior is not always implementable, and the following wording takes that into account.

[fs.conform.9945] ¶1 Many behaviors are specified by reference to POSIX; how they are actually implemented is unspecified. The note explains that this is an as-if rule: an implementation may call the operating system's native API as long as the effect is the same. That is why phrases like "as if by POSIX `stat`" appear throughout the wording, and implementations on Windows achieve the same with Win32 APIs.

¶2 Implementations should provide the behavior defined by POSIX. Behavior that differs from POSIX must be documented; when it cannot be supported exactly, it should be as close as the operating system and file system allow; when not even reasonable behavior can be provided, an error must be reported as specified in [[fs.err.report]]. So the user always gets an outcome: either the operation succeeds, or an exception or error code is received, never a silently wrong result.

¶3 Implementations need not provide behavior that a file system itself does not support. The standard's example is FAT: it supports neither hard links nor symbolic links, and an implementation on FAT only needs to report an error when asked to create them.

[fs.conform.os] ¶1 Some behaviors are specified as **operating system dependent**, depending on the actual operating system; which operating system the implementation depends on is implementation-defined. ¶2 An implementation may depend on an operating system emulator (such as a Cygwin-like environment on Windows) rather than the actual underlying operating system. The native character type of paths, the preferred separator, and what counts as an absolute path all fall into this category.

## File system races [fs.race.behavior]

!!! std
    Behavior is undefined if calls to functions provided by subclause [filesystems] introduce a file system race.

¶1 A **file system race** ([[g:file-system-race|file system race]]) is the condition where multiple threads, processes or computers interleave access and modification of the same object within a file system. Behavior is undefined if calls to `<filesystem>` functions introduce a file system race {{ub}}.

¶2 If the possibility of a file system race would make it unreliable for a program to test for a precondition before calling a function, the precondition is not specified for that function. The note explains this as a design convention: a condition the program has no way to check in advance is not written as a precondition.

This rule acknowledges a fact: the file system is shared state outside the process, and the state you checked may have changed a moment later. Three consequences follow.

**Check-then-act is unreliable.** With `if (!exists(p)) create(p);` or `if (is_regular_file(p)) open(p);`, another process may modify the file between the check and the action; this kind of defect is called TOCTOU (time of check to time of use). The correct approach is to perform the operation directly and then check its result, as in the opening example.

**Many functions have no preconditions.** `file_size(p)` does not require `p` to exist and reports an error if it does not; `remove(p)` does not require `p` to exist and returns `false` if it does not. Both are direct expressions of ¶2.

**Path-based interfaces cannot defend against malicious races.** The wording speaks of function calls introducing a race, but on a multi-user system another process may well put things in a directory or swap a symbolic link while you call `remove_all`. The standard makes no guarantees about this; implementations usually report an error or give some reasonable result. When processing directories writable by others with elevated privileges, use the platform's file-descriptor-based APIs (such as POSIX `openat` and `unlinkat`).

## Character types [fs.req]

¶1 `char`, `wchar_t`, `char8_t`, `char16_t` and `char32_t` are collectively called **encoded character types**. ¶2 Template parameters named `EcharT` participate in overload resolution only if they are encoded character types. ¶3 Template parameters named `InputIterator` shall meet *Cpp17InputIterator*, with a value type that is an encoded character type.

¶4 is a note: the encoded character types all imply a character set and encoding, while `signed char` and `unsigned char` do not, so they are not allowed. This means a `path` cannot be constructed directly from a sequence of `unsigned char` bytes; you must first say what encoding it is, for example by converting to `char8_t`.

¶5 Template parameters named `Allocator` shall meet *Cpp17Allocator*.

## Error reporting [fs.err.report]

```cpp title="error-reporting.cpp" run ok
#include <cstdint>
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  std::error_code ec;
  auto sz = fs::file_size("no-such-file", ec);           // error_code version
  std::cout << (sz == static_cast<std::uintmax_t>(-1)) << ' ' << ec.message() << '\n';
  // 1 No such file or directory

  try {
    (void)fs::file_size("no-such-file");                 // throwing version
  } catch (const fs::filesystem_error& e) {
    std::cout << "path1=" << e.path1() << " code=" << e.code().value() << '\n';
    // path1="no-such-file" code=2 (POSIX ENOENT)
  }
}
```

¶1 Library functions usually provide two overloads, one that throws and one that sets an `error_code`. The note explains where each fits: when errors are truly exceptional and indicate a serious failure, use exceptions; when errors are routine and do not necessarily mean failure (the file may simply not exist, say), use error codes and let the program decide how to handle them, or even ignore them.

¶2 Functions without an `error_code&` parameter, unless otherwise specified:

- ¶2.1 throw `filesystem_error` when a call by the implementation to an operating system API results in an error that prevents the function from meeting its specification. A function with a single `path` parameter passes it as the exception's `path1`; one with two passes the first as `path1` and the second as `path2`. The `error_code` in the exception is the specific, operating-system-dependent error.
- ¶2.2 report failure to allocate storage by throwing an exception per the general rules, i.e. `bad_alloc` ([[res.on.exception.handling]]).
- ¶2.3 Destructors throw nothing.

¶3 Functions with an `error_code&` parameter, unless otherwise specified: when an operating system call results in an error, write that error into the parameter; otherwise call its `clear()`.

Two details follow:

- The `error_code&` versions write `ec` every time and clear it on success, so the same `ec` can be reused repeatedly without clearing it manually before each call.
- The `error_code&` versions are not necessarily `noexcept`. `exists(p, ec)` and `file_size(p, ec)` are `noexcept`, but `absolute(p, ec)`, `canonical(p, ec)`, `create_directories(p, ec)`, `copy(from, to, ec)`, `remove_all(p, ec)` and others are not: they construct new `path`s or traverse directories and may need to allocate memory. ¶3 only specifies how errors from operating system calls are handled, and allocation failure is not among them; these functions are not declared `noexcept`, so under the general rules of [[res.on.exception.handling]] they throw `bad_alloc` when allocation fails.

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

[fs.class.filesystem.error.general] ¶1 This is the exception type thrown by `<filesystem>` functions to report file system errors.

[fs.filesystem.error.members] ¶1–¶4 The three constructors store zero, one and two paths respectively. Afterwards `code() == ec`, and the result of `what()` contains `what_arg`. ¶5–¶6 `path1()` and `path2()` return the stored paths, or an empty path if none was stored. ¶7 The exact format of `what()` is unspecified; implementations should include the `system_error::what()` string and the native format of both paths.

It derives from `system_error`, so `catch (const std::system_error&)` catches it, and `e.code()` can be compared directly with `std::errc::no_such_file_or_directory` ([[syserr]]).

## The `<filesystem>` synopsis [fs.filesystem.syn]

`namespace std::filesystem` contains: the classes `path`, `filesystem_error`, `directory_entry`, `directory_iterator`, `recursive_directory_iterator` and `file_status`; the struct `space_info` (three `uintmax_t`s: `capacity`, `free`, `available`); the enumeration types below; `file_time_type`, which is `chrono::time_point<chrono::file_clock>` ([[time.clock.file]]); and all the operational functions ([[fs.op.funcs]]). `namespace std` contains `hash<filesystem::path>` and C++26's `formatter<filesystem::path, charT>`.

A directory iterator is itself a range: it has non-member `begin` and `end`, and the synopsis declares it a `view` and a `borrowed_range`:

```cpp
template<> inline constexpr bool ranges::enable_borrowed_range<filesystem::directory_iterator> = true;
template<> inline constexpr bool ranges::enable_view<filesystem::directory_iterator> = true;
// likewise for recursive_directory_iterator
```

Copying a directory iterator is cheap, as the copies share the underlying directory handle, and iterators obtained from a temporary iterator do not dangle. So you can write `fs::directory_iterator(".") | std::views::filter(...)` directly ([[fs.class.directory.iterator]]).

¶1 Implementations should make the resolution and range of `file_time_type` reflect the operating system's resolution and range for file times.

## Enumeration types [fs.enum]

### `file_type` [fs.enum.file.type]

| Constant | Meaning |
|---|---|
| `none` | the type has not been determined yet, or an error occurred while determining it |
| `not_found` | the file does not exist. When determining the type, a nonexistent file is not an error |
| `regular`, `directory`, `symlink` | regular file, directory, symbolic link |
| `block`, `character`, `fifo`, `socket` | block device, character device, FIFO (pipe), socket |
| implementation-defined constants | required of implementations supporting other file types |
| `unknown` | the file exists, but its type cannot be determined |

¶1 The constants have distinct values. The distinction between `none`, `not_found` and `unknown` is central to the design of `status()`: respectively, an error occurred and we do not even know whether it exists; it definitely does not exist; it definitely exists but we do not know what it is ([[fs.op.funcs]]).

### `copy_options` [fs.enum.copy.opts]

¶1 `copy_options` is a bitmask type whose constants are divided into option groups. `none` represents the empty bitmask and is listed in every group for exposition, but has only one definition; every other constant occupies one bit.

| Option group | Constants |
|---|---|
| `copy_file` behavior when the target exists | `none` (default, error), `skip_existing` (neither overwrite nor error), `overwrite_existing` (overwrite), `update_existing` (overwrite if the target is older than the source) |
| `copy` for subdirectories | `none` (default, do not copy subdirectories), `recursive` (copy recursively) |
| `copy` for symbolic links | `none` (default, follow), `copy_symlinks` (copy the link itself), `skip_symlinks` (ignore) |
| `copy` form of copying | `none` (default, copy contents), `directories_only` (copy the directory structure only), `create_symlinks` (create symbolic links; the source path must be absolute unless the target is in the current directory), `create_hard_links` (create hard links) |

`copy` and `copy_file` require at most one option to be set from each group ([[fs.op.funcs]]).

### `perms` and `perm_options` [fs.enum.perms], [fs.enum.perm.opts]

`perms` is a bitmask type whose values correspond one-to-one to the POSIX permission bits:

| Name | Octal | POSIX macro |
|---|---|---|
| `owner_read`, `owner_write`, `owner_exec`, `owner_all` | 0400, 0200, 0100, 0700 | `S_IRUSR`, `S_IWUSR`, `S_IXUSR`, `S_IRWXU` |
| `group_read` … `group_all` | 040, 020, 010, 070 | `S_IRGRP` … `S_IRWXG` |
| `others_read` … `others_all` | 04, 02, 01, 07 | `S_IROTH` … `S_IRWXO` |
| `all` | 0777 | |
| `set_uid`, `set_gid`, `sticky_bit` | 04000, 02000, 01000 | `S_ISUID`, `S_ISGID`, `S_ISVTX` (sticky is operating system dependent) |
| `mask` | 07777 | |
| `none`, `unknown` | 0, 0xFFFF | `unknown` means the permissions are not known, for example when a `file_status` is constructed without specifying them |

`perm_options` determines how `permissions(p, prms, opts)` uses `prms`: `replace` replaces, `add` ORs in, `remove` clears those bits, and `nofollow` acts on the symbolic link itself rather than its target. Exactly one of the first three must be present ([[fs.op.funcs]]).

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

| Name | Meaning |
|---|---|
| `none` | default: when recursing, do not descend into symbolic links to directories; permission denied is an error |
| `follow_directory_symlink` | when recursing, descend into symbolic links to directories |
| `skip_permission_denied` | skip directories that cannot be opened because permission is denied, without error |

### `path::format` [fs.enum.path.format]

¶1 When constructing a `path`, the format of the character sequence can be stated: `native_format` is the native pathname format, `generic_format` the generic pathname format, and `auto_format` leaves the interpretation to the implementation, which may inspect the content to decide. *Recommended practice*: on POSIX systems, where the native format and the generic format are the same, character sequences should always be interpreted the same way. The difference between the two formats is in [[fs.class.path]].

## Questions

!!! question "Question 1"
    What is wrong with `if (fs::exists(p)) fs::remove(p);`? How should it be written?

<details markdown="1">
<summary>Answer</summary>

Two things. First, TOCTOU: after `exists` returns `true` and before `remove`, the file may have been removed by another process, which by [[fs.race.behavior]] is a file system race (in practice `remove` would return `false` or report an error). Second, it is redundant: `remove(p)` returns `false` for a nonexistent file, which is not an error ([[fs.op.remove]]). Just write `fs::remove(p);`, and use the return value if you need to distinguish "removed" from "was never there".
</details>

!!! question "Question 2"
    What happens if memory runs out during a call to `fs::canonical(p, ec)`?

<details markdown="1">
<summary>Answer</summary>

`bad_alloc` is thrown. `canonical(const path&, error_code&)` is not declared `noexcept` ([[fs.filesystem.syn]]), and [[fs.err.report#3]] writes only errors produced by operating system calls into the `error_code&`; allocation failure is still reported by exception under the general rules of [[res.on.exception.handling]].
</details>
