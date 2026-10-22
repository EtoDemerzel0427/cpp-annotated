---
title: Class path
summary: "std::filesystem::path is a value type that does purely lexical operations and never touches the file system: the syntax of paths, decomposition and trailing separators, /= versus +=, element-wise comparison, lexically_normal/relative/proximate, the stashing iterator, encoding conversion and output format."
updated: 2026-10-19
---

!!! tldr
    - `path` deals only with the syntax of path strings; its member functions never access the file system. `lexically_normal()` does not resolve symbolic links, and `==` does not tell whether two paths name the same file.
    - A trailing separator produces an empty element: `path("/usr/lib/").filename()` is empty, and `path("a/b/") != path("a/b")`.
    - `p / q` replaces the whole thing with `q` when `q` is absolute, and keeps `..` as is, so it cannot prevent path escape; `p += q` is plain string concatenation.
    - `path::iterator` stores the current element inside itself and cannot be used with `std::reverse_iterator`.
    - `std::cout << p` puts quotes around the path; C++26's `std::format("{}", p)` does not.

## A value type that cares only about the letters [fs.class.path.general]

```cpp run title="path-lexical.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::path p = "/no/such/dir/../file.txt";   // need not exist
  std::cout << p.lexically_normal() << '\n'; // "/no/such/file.txt"
  std::cout << p.is_absolute() << '\n';      // 1: only looks at the characters
  std::cout << (fs::path("a//b") == fs::path("a/b")) << '\n';  // 1
}
```

`/no/such/dir` does not exist, yet these operations produce results anyway, because they look only at the string.

!!! std
    An object of class path represents a path and contains a pathname. Such an object is concerned only with the lexical and syntactic aspects of a path.

¶1 A `path` object holds a **pathname**, the string representing a path, and is concerned only with its lexical and syntactic aspects. The path it represents need not exist, nor even be valid for the current operating system. Every operation that needs to access the file system, such as `canonical`, `equivalent` or `exists`, is a non-member function in [[fs.op.funcs]].

¶3 A **path** consists of three parts in order, each of which may be omitted: a *root-name* (Windows `C:`, `//host` for network paths), a *root-directory* (a leading separator), and a sequence of *filename*s.

¶4 An **absolute path** unambiguously identifies the location of a file without reference to an additional starting location; all others are **relative paths**, resolved relative to some implied starting location (usually the current directory). Which elements make a path absolute is operating system dependent. `.` and `..` are both relative paths.

¶6 **Pathname resolution** is the operating system's mechanism for mapping a pathname to a file; on POSIX it is specified in section 4.12 of the POSIX standard. Multiple pathnames may resolve to the same file.

¶7–¶9 `value_type` is the character type the operating system uses for pathnames, `string_type` is `basic_string<value_type>`, and `preferred_separator` is the preferred directory separator. On POSIX these are `char` and `'/'`; on Windows, `wchar_t` and `L'\\'`. So the types of `native()` and `c_str()` vary by platform: on Windows `p.c_str()` is `const wchar_t*` and cannot be passed directly to a function taking `const char*`.

## The syntax of paths [fs.path.generic]

`path` understands a pathname according to the following **generic pathname format** ([[g:generic-pathname-format]]):

```text
pathname:            root-name(opt) root-directory(opt) relative-path
root-name:           OS-dependent / implementation-defined character sequence
root-directory:      directory-separator
relative-path:       filename
                     filename directory-separator relative-path
                     empty
filename:            non-empty sequence of characters other than separators
directory-separator: preferred-separator directory-separator(opt)
                     fallback-separator directory-separator(opt)
fallback-separator:  '/' (if preferred-separator is not '/')
```

`/` is a valid separator on every platform: it is either the preferred separator or the fallback separator. So paths written with `/` are portable.

- ¶1 Filenames consisting of exactly one dot or two dots are called **dot** and **dot-dot** and have special meaning. Which characters are permitted, the maximum length, and case sensitivity are all operating system dependent; using only `A–Z a–z 0–9 . _ -` is the most portable.
- ¶2 Except within a *root-name*, multiple successive separators are treated as one.
- ¶3 Dot refers to the current directory, dot-dot to the parent directory. What dot-dot of the root directory refers to is implementation-defined; on POSIX `/..` is `/`.
- ¶4 A *root-name* identifies the starting location for pathname resolution. Many systems treat names beginning with two separators (such as `//host`) as the *root-name* of a network resource, and Windows treats drive letters like `C:` as *root-name*s.
- ¶5 If a *root-name* is ambiguous, the longest interpretation is taken. A path with a *root-name* but no *root-directory*, such as Windows `C:foo` (`foo` in the current directory of drive C), does not occur on POSIX.

### The elements of a path [fs.path.itr]

```cpp run title="path-iterate.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  for (const auto& e : fs::path("/a//b/"))
    std::cout << '[' << e.native() << ']';
  std::cout << '\n';                       // [/][a][b][]
}
```

¶4 Iterating over a `path` yields its **elements**, in order: the *root-name* (if any), the *root-directory* (if any), each *filename*, and, if the path ends with a non-root separator, a final empty element. ¶5 Backward iteration is the reverse of forward iteration.

In the example above, `//` is treated as one separator, and the trailing `/` produces the empty element `[]`. This empty element is the source of many of the results below.

## Decomposition [fs.path.decompose]

```cpp run title="path-decompose.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

void show(const fs::path& p) {
  std::cout << p << ": parent=" << p.parent_path()
            << " filename=" << p.filename()
            << " stem=" << p.stem()
            << " ext=" << p.extension() << '\n';
}

int main() {
  show("/usr/lib/libc.so.6");
  // parent="/usr/lib" filename="libc.so.6" stem="libc.so" ext=".6"
  show("/usr/lib/");
  // parent="/usr/lib" filename="" stem="" ext=""
  show(".bashrc");
  // parent="" filename=".bashrc" stem=".bashrc" ext=""
  show("..bar");
  // parent="" filename="..bar" stem="." ext=".bar"
  show("/");
  // parent="/" filename="" stem="" ext=""
}
```

| Member | Specification |
|---|---|
| `root_name()`, `root_directory()` | ¶1–¶2 the corresponding part, or empty |
| `root_path()` | ¶3 `root_name() / root_directory()` |
| `relative_path()` | ¶4 the part after the root |
| `parent_path()` | ¶5 `*this` if there is no relative part; otherwise with the last element removed |
| `filename()` | ¶6 `relative_path().empty() ? path() : *--end()`, i.e. the last element |
| `stem()` | ¶8 let `f = filename()`: if `f` contains no dot other than a leading one, or `f` consists solely of one or two dots, returns `f`; otherwise returns the part of `f` before its last dot |
| `extension()` | ¶10 the suffix of `filename()` not included in `stem()` |

The last element of `"/usr/lib/"` is that empty element, so `filename()` is empty, and `parent_path()` removes it too, giving `"/usr/lib"`. Whether a directory path has a trailing `/` changes the decomposition, which is the most common surprise when using `path`.

A leading dot is not treated as an extension separator, so `.bashrc` has no extension. The note in paragraph 12 explains that `extension()` includes the dot, so that "no extension" (`"foo"` gives `""`) can be told apart from "empty extension" (`"foo."` gives `"."`). To strip multiple extensions, loop `p = p.stem()`; the example in paragraph 9 yields `.tar`, `.baz`, `.bar` in turn for `"foo.bar.baz.tar"`.

Each `has_xxx()` in [fs.path.query] is equivalent to the corresponding decomposition result being non-empty; `empty()` checks whether the pathname is empty. ¶10 `is_absolute()` checks whether the pathname in native format is an absolute path; the example in paragraph 11 points out that `path("/").is_absolute()` is true on POSIX and false on Windows (no drive letter).

## Appending: `/=` versus `+=`

```cpp run title="path-append.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::path base = "/srv/www";
  std::cout << base / "img/logo.png" << '\n';
  // "/srv/www/img/logo.png"
  std::cout << base / "/etc/passwd" << '\n';
  // "/etc/passwd": the right-hand side is absolute
  std::cout << base / "../../etc/passwd" << '\n';
  // "/srv/www/../../etc/passwd"
  std::cout << fs::path("foo") / "" << '\n';
  // "foo/"
  fs::path p = "a/b";
  p += ".txt";                    // plain string concatenation
  std::cout << p << '\n';         // "a/b.txt"
}
```

### `operator/=` [fs.path.append]

¶1 `/=` means "add a separator if needed, then append". The rule for `p1 /= p2` is:

- ¶2 if `p2.is_absolute()`, or `p2` has a *root-name* different from `p1`'s, the result is `p2`: the left side is replaced entirely;
- ¶3.1 otherwise, if `p2` has a *root-directory*, first remove `p1`'s root directory and relative part; otherwise, if `p1` has a filename, or `p1` is an absolute path without a root directory, add a preferred separator;
- ¶3.2 then append the native-format pathname of `p2` with its *root-name* removed.

`path("/a/b/") / "c"` does not produce two separators: the filename of `"/a/b/"` is empty, so `c` is appended directly. `path("foo") / ""` gives `"foo/"`, because `foo` has a filename, so a separator is added, and then the empty string is appended.

The example in ¶4 shows the effect of a *root-name* on Windows:

```cpp
// Windows
path("foo") /= path("c:/bar");  // "c:/bar": different root-name, replaced
path("foo") /= path("c:");      // "c:"
path("c:foo") /= path("/bar");  // "c:/bar": root-name kept, the rest replaced
path("c:foo") /= path("c:bar"); // "c:foo\\bar": same root-name, appended
```

`operator/=(const Source&)` and `append` are equivalent to constructing a `path` first and then `/=`; the non-member `lhs / rhs` is equivalent to `path(lhs) /= rhs` ([[fs.path.nonmember#6]]).

!!! pitfall "`base / user_input` does not prevent path escape"
    An absolute right-hand side replaces everything, and `..` is kept as is, so with `request` being `/etc/passwd` or `../../etc/passwd`, `fs::path("/srv/www") / request` points outside `/srv/www` either way. Check after resolution instead: for example, call `weakly_canonical` on the result first, then compare element by element whether it begins with `canonical(base)`, rather than comparing string prefixes. Even then, another process may modify the file system between the check and the use ([[filesystems]]).

### `operator+=` [fs.path.concat]

¶1 `+=` appends `path(x).native()` directly to the native-format pathname, without adding a separator or doing any syntactic processing. ¶3 The single-character version is equivalent to appending a string of length 1.

## Modifiers [fs.path.modifiers]

| Member | Effect |
|---|---|
| `clear()` | ¶1 becomes an empty path |
| `make_preferred()` | ¶2 replaces each separator with the preferred separator (no change on POSIX) |
| `remove_filename()` | ¶5–¶6 removes `filename()`; afterwards `has_filename()` is false |
| `replace_filename(r)` | ¶9 equivalent to `remove_filename(); operator/=(r);` |
| `replace_extension(r = path())` | ¶12 removes the existing extension; if `r` is non-empty and does not begin with a dot, adds a dot first; then `+= r` |
| `swap(rhs)` | ¶14–¶15 constant-time swap |

```cpp
path("foo/bar").remove_filename();     // "foo/"
path("/foo").remove_filename();        // "/"
path("/foo").replace_filename("bar");  // "/bar"
path("x.txt").replace_extension("md"); // "x.md"
path("x.txt").replace_extension();     // "x"
```

`remove_filename()` keeps the trailing separator: `"foo/bar"` becomes `"foo/"`, not `"foo"`. To get the parent directory, use `parent_path()`.

## Comparison: equal is not the same file [fs.path.compare]

```cpp run title="path-compare.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  std::cout << std::boolalpha
    << (fs::path("a//b") == fs::path("a/b")) << ' '   // true
    << (fs::path("a/b/") == fs::path("a/b")) << ' '   // false
    << (fs::path("a/./b") == fs::path("a/b")) << '\n';// false
}
```

¶1 `p1.compare(p2)` compares in order:

1. the `native()` strings of the *root-name*s, returning that result if they differ (¶1.1);
2. if only one side has a *root-directory*, the side without it is smaller (¶1.2–¶1.3);
3. otherwise, the `native()` of each element of `relative_path()`, element by element, lexicographically (¶1.4–¶1.5);
4. 0 if all are the same (¶1.6).

Element-wise comparison means redundant separators do not affect the result, but the empty element produced by a trailing separator does, and `.` and `..` are not simplified. Both `==` and `<=>` are defined in terms of `compare` ([[fs.path.nonmember#3]], [[fs.path.nonmember#5]]).

The note in [[fs.path.nonmember#4]] stresses the difference between **equality** and **equivalence**. `==` compares only the lexical representation; `equivalent(p1, p2)` ([[fs.op.funcs]]) accesses the file system to determine whether both resolve to the same file. `path("foo") == "bar"` is always false, while `equivalent("foo", "bar")` is true if `foo` is a link to `bar`.

[[fs.path.nonmember#2]] specifies that if `p1 == p2` then `hash_value(p1) == hash_value(p2)`, and `std::hash<path>` is consistent with it ([fs.path.hash]), so `path` can be used directly as an `unordered_map` key.

## Lexical operations [fs.path.gen]

### `lexically_normal()` (¶1)

[[fs.path.generic#6]] defines **normalization**, whose result is called the **normal form** ([[g:normal-form-path]]):

1. if the path is empty, stop;
2. replace each `/` in the *root-name* with the preferred separator;
3. replace each sequence of separators with a single preferred separator;
4. remove each dot filename and any immediately following separator;
5. repeatedly remove each "non-dot-dot filename, separator, dot-dot" sequence and any immediately following separator;
6. if there is a root directory, remove any dot-dot and separator immediately following it;
7. if the last filename is dot-dot, remove any trailing separator;
8. if the path is empty, make it `.`.

¶1 `lexically_normal()` returns the normal form:

```cpp
path("foo/./bar/..").lexically_normal();     // "foo/"
path("foo/.///bar/../").lexically_normal();  // "foo/"
```

Step 5 assumes `a/..` is the same as nothing. That does not hold when `a` is a symbolic link pointing elsewhere:

```cpp run title="lexical-vs-real.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::create_directories("dd/real/sub");
  // dd/shortcut -> dd/real/sub
  fs::create_directory_symlink("real/sub", "dd/shortcut");
  fs::path p = "dd/shortcut/..";
  std::cout << p.lexically_normal() << '\n';    // "dd/"
  std::cout << fs::canonical(p).lexically_relative(
                 fs::canonical(".")) << '\n';   // "dd/real"
  fs::remove_all("dd");
}
```

Lexically, `shortcut/..` cancels out, giving `dd`; in the file system it is `real`, the parent directory of `real/sub`. POSIX resolves `..` according to the physical directory structure, so when the real result is needed, use `canonical` or `weakly_canonical`, which access the file system ([[fs.op.funcs]]).

### `lexically_relative(base)` (¶3–¶7)

```cpp
path("/a/d").lexically_relative("/a/b/c");      // "../../d"
path("/a/b/c").lexically_relative("/a/d");      // "../b/c"
path("a/b/c").lexically_relative("a");          // "b/c"
path("a/b/c").lexically_relative("a/b/c/x/y");  // "../.."
path("a/b/c").lexically_relative("a/b/c");      // "."
path("a/b").lexically_relative("/a");           // "": one absolute, one relative
```

¶3 If the two have different *root-name*s, one is absolute and the other is not, `*this` has no root directory while `base` has one, or some filename could be interpreted as a *root-name*, it returns an empty path. Otherwise, it finds the first element where the two differ, counts from the rest of `base` how many levels to go up (plus one for an ordinary filename, minus one for dot-dot), generates that many `..`, and appends the rest of `*this`. If the count is negative it returns an empty path; if the two are the same, it returns `.`.

¶4 It does not resolve symbolic links and does not normalize first. The note points out: for symbolic link semantics use `relative()` from [[fs.op.funcs]]; for normalization, call `lexically_normal()` on both sides first.

### `lexically_proximate(base)` (¶8)

¶8 Returns `lexically_relative(base)` if that is not empty, otherwise `*this`. That is, use the relative path if one can be computed, and leave it as is otherwise.

## What is special about the iterator [fs.path.itr]

¶2 `path::iterator` is a constant iterator that meets all the requirements of a bidirectional iterator except one: for two equal dereferenceable iterators `a == b`, `*a` and `*b` are not required to be the same object. ¶3 Calling any non-const member function of a `path` invalidates iterators referring to it.

!!! lawyer "A stashing iterator"
    The relaxed requirement is exactly the forward iterator requirement "if `a == b` then `*a` and `*b` are bound to the same object" ([[forward.iterators#6]]). The elements of a path do not exist as `path` objects within the string, so the iterator has no choice but to construct a `path` inside itself holding the current element (libc++ even names the member `__stashed_elem_`), and `operator*` returns a reference to it. So:

    - After copying an iterator, the two dereference to different objects; after an iterator is destroyed, references obtained from it dangle.
    - `std::reverse_iterator::operator*` is specified as `Iterator tmp = current; return *--tmp;` ([[reverse.iter.elem]]), which returns a reference to an object inside the local copy `tmp`, dangling as soon as the function returns. `path::iterator` semantically does not meet the requirements of [[reverse.iter.requirements]], and `std::reverse_iterator<path::iterator>` cannot be used.
    - libc++ declares its `iterator_category` as `input_iterator_tag`, yet `std::bidirectional_iterator<path::iterator>` is true, because concepts check only syntax.

    When reverse traversal is needed, use `--` on `path::iterator` directly, and use or copy the element while the iterator is alive.

## Strings, encodings and output

### Native and generic formats [fs.path.fmt.cvt]

The same pathname can be written two ways: the **native pathname format** ([[g:native-pathname-format]]) is what the operating system uses, and the **generic format** is what the grammar above describes. The note in paragraph 6 explains that `path` stores the native format and behaves as if it also stored the generic format. Decomposition, iteration and comparison work on the generic format; `native()` and `+=` work on the native format.

The note in ¶1 explains that on POSIX the two are the same and no conversion takes place. The difference shows up only on systems like Windows:

| Observer | Returns | `path("foo\\bar")` on Windows |
|---|---|---|
| `native()`, `c_str()`, `wstring()`, `u8string()` and so on | native format ([fs.path.native.obs]) | `foo\bar` |
| `generic_string()`, `generic_u8string()` and so on | generic format, with separators normalized to `/` ([fs.path.generic.obs]) | `foo/bar` |

When text must be consistent across platforms (writing config files, logs, test comparisons), use the `generic_*` versions. `operator string_type()` is an implicit conversion to `native()` ([[fs.path.native.obs#4]]).

### Encoding conversion [fs.path.type.cvt]

¶2 When the character type of an argument or return value differs from `value_type`, `path` converts encodings:

| Character type | Encoding | Conversion |
|---|---|---|
| `char` | the native ordinary encoding, i.e. the operating system's current pathname encoding | operating system dependent; no conversion on POSIX, depends on the current code page on Windows |
| `wchar_t` | the native wide encoding | unspecified; no conversion on Windows |
| `char8_t`, `char16_t`, `char32_t` | UTF-8, UTF-16, UTF-32 | unspecified |

The note in ¶2 explains why `char` is not specified as UTF-8: for consistency with other C and C++ functions that represent paths as ordinary strings. ¶3 If a character cannot be represented in the target encoding, the result is unspecified.

So to represent UTF-8 paths reliably on Windows, construct the `path` from `char8_t` strings (`u8"..."`, `std::u8string`), not from `std::string`, which would be interpreted according to the system code page. This is also why the `u8path()` factory function was deprecated in C++20 ([[depr.fs.path.factory]]): constructing directly from a `char8_t` string expresses that it is UTF-8. Likewise since C++20, `u8string()` returns `std::u8string` rather than `std::string` ([[diff.cpp17.input.output]]).

### The deprecation of `string()` and `display_string()`

The current draft moves the non-template `string()` and `generic_string()` into Annex D ([[depr.fs.path.obs]]); they are equivalent to the newly added `native_encoded_string()` and `generic_native_encoded_string()` respectively. It also adds `display_string()` ([[fs.path.native.obs#9]]), which returns `std::format("{}", *this)`, and the corresponding `generic_display_string()`. This is post-C++23 wording.

The motivation is to separate two uses: handing a path to an API that needs a string in the native encoding, and displaying a path to people. On Windows, `string()` converts according to the code page, and the result is unspecified for characters it cannot represent, so using it for display often produces garbage. libc++ in our tests has neither `display_string` nor `native_encoded_string` yet, and `string()` gives no deprecation warning.

### Stream output adds quotes [fs.path.io]

¶1 `os << p` is equivalent to `os << quoted(p.string<charT, traits>())` ([[quoted.manip]]), which adds double quotes and escapes. That is why the example output on this page has quotes. To print a path without quotes, use `p.native()` or `p.generic_string()`. ¶3 `is >> p` correspondingly reads with `quoted`, so a quoted path containing spaces can be read back.

### `formatter<path>` [fs.path.fmtr] {{c++26}}

[[fs.path.fmtr.funcs#1]] The format specification has the form: optional fill and align, optional width, optional `?`, optional `g`. `?` means output as an escaped string ([[format.string.escaped]]), and `g` means use the generic format.

Unlike `<<`, `std::format("{}", p)` adds no quotes by default; only `{:?}` adds quotes and escapes. ¶5 specifies that when `charT` is `char`, `value_type` is `wchar_t`, and the literal encoding is UTF-8, the path is converted from the native wide encoding to UTF-8, with invalid parts replaced by U+FFFD; when the two character types are the same, no transcoding happens; other cases are implementation-defined.

libc++ (Clang 23) does not yet provide `formatter<path>`: `std::format("{}", path)` fails to compile, reporting that the default constructor of `formatter<std::filesystem::path, char>` is implicitly deleted.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[fs.class.path.general] ¶2 is a note: `path` is used to deal with differences between the string types different systems use to represent pathnames. ¶5 defines that a pathname can be written in either the generic format or the native format.

[fs.path.fmt.cvt] ¶2 defines the **detected-format** ([[g:detected-format]]): an argument is treated as being in generic format if and only if it matches the generic format and is not acceptable to the operating system as a native path. The note in paragraph 3 explains that some systems cannot distinguish the two formats. ¶4 requires the format conversion functions *G* (native to generic) and *N* (generic to native) to satisfy *G*(*N*(*g*)) = *g* and *N*(*G*(*n*)) = *n*, though neither need be invertible. ¶5 specifies, for systems that write regular files and directories differently (such as OpenVMS), that a path whose last element is a separator is treated as a directory. ¶7–¶8 specify how the other representation is chosen when constructing or producing a new value from one representation.

[fs.path.req] ¶1 A template parameter named `Source` can be a `basic_string`, a `basic_string_view`, an input iterator over a null-terminated character string (NTCTS), or a character array that decays to a pointer to an NTCTS. ¶2 Functions taking a `Source` participate in overload resolution only if `Source` is not `path` and is either a string type or its `iterator_traits<decay_t<Source>>::value_type` is a character type. ¶4 A `Source` argument shall not be a null pointer.

[fs.path.construct] ¶1–¶4 Default construction gives an empty path; construction from a string takes the effective range and converts encoding and format as needed. ¶5–¶6 The versions taking a `locale` require the character type to be `char`; they first convert to wide characters with `loc`'s `codecvt<wchar_t, char, mbstate_t>`, then, if `value_type` is not `wchar_t`, to the native ordinary encoding. The example in paragraph 7 reads an ISO 8859-1 encoded string from a database and then constructs a `path`. The assignment functions in [fs.path.assign] correspond one-to-one to the constructors; `operator=(path&&)` may be implemented with `swap`.

</details>

## Questions

!!! question "Question 1"
    On POSIX, what are `path("/a/b") / path("")`, `path("/a/b/") / "c"` and `path("/a/b") / "c/"`?

<details markdown="1">
<summary>Answer</summary>

`"/a/b/"`, `"/a/b/c"` and `"/a/b/c/"`. The first: the right side is empty and not absolute; the left side has the filename `b`, so a separator is added and then the empty string appended ([[fs.path.append#3]]). The second: the filename of `"/a/b/"` is empty, so no separator is added and `c` is appended directly. The third: an ordinary append, and `c/` keeps its trailing separator.
</details>

!!! question "Question 2"
    Why is `path("C:foo").is_absolute()` false on Windows while `has_root_name()` is true?

<details markdown="1">
<summary>Answer</summary>

`C:` is a *root-name* ([[fs.path.generic#4]]), but no *root-directory* follows, so the path means `foo` in the current directory of drive C. Locating it requires an additional starting location, the current directory of that drive, so by [[fs.class.path.general#4]] it is not an absolute path.
</details>

!!! question "Question 3"
    Can a `std::set<fs::path>` hold both `"a/b"` and `"a//b"`? What about `"a/b"` and `"a/b/"`?

<details markdown="1">
<summary>Answer</summary>

Not the first pair: both have the elements `a` and `b`, and `compare` gives 0. The second pair, yes: `"a/b/"` has an extra trailing empty element ([[fs.path.itr#4]]), so the comparison is not 0.
</details>
