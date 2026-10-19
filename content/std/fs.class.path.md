---
title: 路径 path
summary: std::filesystem::path 是只做字面运算、从不访问文件系统的值类型：路径的语法结构、分解与末尾分隔符、/= 与 += 的区别、逐元素比较、lexically_normal/relative/proximate、暂存迭代器、编码转换与输出格式。
status: done
covers: *
since: c++17
related: filesystems, fs.op.funcs, fs.class.directory.iterator, file.streams, quoted.manip, format, depr.fs.path.obs, depr.fs.path.factory
tags: 标准库, filesystem, path, 路径
updated: 2026-10-19
---

!!! tldr
    - `path` 只处理路径字符串的语法，它的成员函数从不访问文件系统；`lexically_normal()` 不解析符号链接，`==` 也不判断是不是同一个文件。
    - 末尾的分隔符会产生一个空元素：`path("/usr/lib/").filename()` 是空的，`path("a/b/") != path("a/b")`。
    - `p / q` 在 `q` 是绝对路径时整体替换成 `q`，`..` 原样保留，所以它不能防止路径逃逸；`p += q` 是纯字符串拼接。
    - `path::iterator` 在自身内部保存当前元素，不能用于 `std::reverse_iterator`。
    - `std::cout << p` 会给路径加引号；C++26 的 `std::format("{}", p)` 不加引号。

## 一个只管字面的值类型 [fs.class.path.general]

```cpp run title="path-lexical.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::path p = "/no/such/dir/../file.txt";   // 不必存在
  std::cout << p.lexically_normal() << '\n'; // "/no/such/file.txt"
  std::cout << p.is_absolute() << '\n';      // 1：只看字符
  std::cout << (fs::path("a//b") == fs::path("a/b")) << '\n';  // 1
}
```

`/no/such/dir` 并不存在，这些操作照样得出结果，因为它们只看字符串。

!!! std
    An object of class path represents a path and contains a pathname. Such an object is concerned only with the lexical and syntactic aspects of a path.

¶1 `path` 对象保存一个**路径名**（pathname），也就是表示路径的字符串，只关心它的字面和语法。它表示的路径不必存在，甚至不必对当前操作系统有效。凡是需要访问文件系统的操作，比如 `canonical`、`equivalent`、`exists`，都是 [[fs.op.funcs]] 里的非成员函数。

¶3 一条**路径**（path）由三部分依次组成，每部分都可以省略：一个 *root-name*（Windows 的 `C:`、网络路径的 `//host`）、一个 *root-directory*（开头的分隔符）、若干 *filename*。

¶4 **绝对路径**（absolute path）不需要额外的起点就能确定文件位置；其余都是**相对路径**，要相对于某个隐含的起点（通常是当前目录）解析。哪些部分让路径成为绝对路径由操作系统决定。`.` 和 `..` 都是相对路径。

¶6 **路径名解析**（pathname resolution）是操作系统把路径名对应到某个文件的机制，POSIX 上由 POSIX 标准 4.12 节规定。多个路径名可以解析到同一个文件。

¶7–¶9 `value_type` 是操作系统用来表示路径名的字符类型，`string_type` 是 `basic_string<value_type>`，`preferred_separator` 是首选的目录分隔符。POSIX 上分别是 `char` 和 `'/'`；Windows 上是 `wchar_t` 和 `L'\\'`。所以 `native()`、`c_str()` 的类型随平台变化：在 Windows 上 `p.c_str()` 是 `const wchar_t*`，不能直接传给接受 `const char*` 的函数。

## 路径的语法 [fs.path.generic]

`path` 按下面的**通用路径名格式**（[[g:generic-pathname-format]]）理解路径名：

```text
pathname:            root-name(opt) root-directory(opt) relative-path
root-name:           由操作系统决定 / 实现定义的字符序列
root-directory:      directory-separator
relative-path:       filename
                     filename directory-separator relative-path
                     空
filename:            不含分隔符的非空字符序列
directory-separator: preferred-separator directory-separator(opt)
                     fallback-separator directory-separator(opt)
fallback-separator:  '/'（当 preferred-separator 不是 '/' 时）
```

`/` 在所有平台上都是合法的分隔符：它要么就是首选分隔符，要么是后备分隔符。所以用 `/` 写的路径是可移植的。

- ¶1 恰好由一个点和两个点组成的文件名叫 **dot** 和 **dot-dot**，有特殊含义。允许哪些字符、最长多少、是否区分大小写，都由操作系统决定；只用 `A–Z a–z 0–9 . _ -` 可移植性最好。
- ¶2 除了在 *root-name* 中，连续多个分隔符等同于一个。
- ¶3 dot 指当前目录，dot-dot 指父目录。根目录的 dot-dot 指什么由实现定义，POSIX 上 `/..` 就是 `/`。
- ¶4 *root-name* 标识路径解析的起点。许多系统把以两个分隔符开头的名字（如 `//host`）当作网络资源的 *root-name*，Windows 把 `C:` 这样的驱动器号当作 *root-name*。
- ¶5 *root-name* 有歧义时取最长的那种解释。有 *root-name*、没有 *root-directory* 的路径，如 Windows 的 `C:foo`（驱动器 C 当前目录下的 `foo`），在 POSIX 上不会出现。

### 路径的元素 [fs.path.itr]

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

¶4 遍历 `path` 得到它的**元素**，依次是：*root-name*（如有）、*root-directory*（如有）、每个 *filename*，以及路径以非根的分隔符结尾时，最后一个空元素。¶5 反向遍历是正向的逆序。

上例中 `//` 被当作一个分隔符，末尾的 `/` 产生了空元素 `[]`。这个空元素是下面许多结果的根源。

## 分解 [fs.path.decompose]

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

| 成员 | 规定 |
|---|---|
| `root_name()`、`root_directory()` | ¶1–¶2 对应部分，没有则为空 |
| `root_path()` | ¶3 `root_name() / root_directory()` |
| `relative_path()` | ¶4 根之后的部分 |
| `parent_path()` | ¶5 没有相对部分时返回 `*this`；否则去掉最后一个元素 |
| `filename()` | ¶6 `relative_path().empty() ? path() : *--end()`，即最后一个元素 |
| `stem()` | ¶8 设 `f = filename()`：`f` 除开头的点外不含点，或者 `f` 只由一两个点组成时，返回 `f`；否则返回 `f` 最后一个点之前的部分 |
| `extension()` | ¶10 `filename()` 中不属于 `stem()` 的后缀 |

`"/usr/lib/"` 的最后一个元素是那个空元素，所以 `filename()` 为空，`parent_path()` 去掉的也是它，得到 `"/usr/lib"`。目录路径末尾有没有 `/` 会改变分解结果，这是使用 `path` 时最常见的意外。

开头的点不算扩展名的分隔符，所以 `.bashrc` 没有扩展名。第 12 段的注说明，`extension()` 包含那个点，这样能区分没有扩展名（`"foo"` 得到 `""`）和空扩展名（`"foo."` 得到 `"."`）。要剥掉多重扩展名，可以循环 `p = p.stem()`，第 9 段的例子对 `"foo.bar.baz.tar"` 依次得到 `.tar`、`.baz`、`.bar`。

[fs.path.query] 的 `has_xxx()` 都等价于对应的分解结果非空；`empty()` 看路径名是否为空。¶10 `is_absolute()` 看原生格式的路径名是否是绝对路径，第 11 段的例子指出 `path("/").is_absolute()` 在 POSIX 上为真，在 Windows 上为假（没有驱动器号）。

## 拼接：`/=` 与 `+=`

```cpp run title="path-append.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::path base = "/srv/www";
  std::cout << base / "img/logo.png" << '\n';
  // "/srv/www/img/logo.png"
  std::cout << base / "/etc/passwd" << '\n';
  // "/etc/passwd"：右边是绝对路径
  std::cout << base / "../../etc/passwd" << '\n';
  // "/srv/www/../../etc/passwd"
  std::cout << fs::path("foo") / "" << '\n';
  // "foo/"
  fs::path p = "a/b";
  p += ".txt";                    // 纯字符串拼接
  std::cout << p << '\n';         // "a/b.txt"
}
```

### `operator/=` [fs.path.append]

¶1 `/=` 的意思是在需要时加一个分隔符，再追加。`p1 /= p2` 的规则是：

- ¶2 如果 `p2.is_absolute()`，或者 `p2` 有 *root-name* 且与 `p1` 的不同，结果就是 `p2`，左边被整体替换；
- ¶3.1 否则，如果 `p2` 有 *root-directory*，先删掉 `p1` 的根目录和相对部分；否则，`p1` 有 filename，或者 `p1` 是没有根目录的绝对路径时，加一个首选分隔符；
- ¶3.2 然后把 `p2` 去掉 *root-name* 后的原生格式路径名追加上去。

`path("/a/b/") / "c"` 不会加出两个分隔符：`"/a/b/"` 的 filename 为空，所以直接拼上 `c`。`path("foo") / ""` 得到 `"foo/"`，因为 `foo` 有 filename，于是加了一个分隔符，再追加空串。

¶4 的例子展示了 Windows 上 *root-name* 的影响：

```cpp
// Windows
path("foo") /= path("c:/bar");  // "c:/bar"：根名不同，替换
path("foo") /= path("c:");      // "c:"
path("c:foo") /= path("/bar");  // "c:/bar"：保留根名，换掉其余部分
path("c:foo") /= path("c:bar"); // "c:foo\\bar"：根名相同，追加
```

`operator/=(const Source&)` 和 `append` 等价于先构造 `path` 再 `/=`；非成员的 `lhs / rhs` 等价于 `path(lhs) /= rhs`（[[fs.path.nonmember#6]]）。

!!! pitfall "`base / user_input` 不能防止路径逃逸"
    右边是绝对路径时整体替换，`..` 又原样保留，所以 `request` 为 `/etc/passwd` 或 `../../etc/passwd` 时，`fs::path("/srv/www") / request` 都会指向 `/srv/www` 之外。应当在解析之后检查：例如先对结果调用 `weakly_canonical`，再逐元素比较它是否以 `canonical(base)` 开头，而不是比较字符串前缀。即便如此，检查和使用之间仍可能被其他进程修改文件系统（[[filesystems]]）。

### `operator+=` [fs.path.concat]

¶1 `+=` 把 `path(x).native()` 直接接到原生格式路径名后面，不加分隔符，也不做任何语法处理。¶3 单个字符的版本等价于追加长度为 1 的字符串。

## 修改器 [fs.path.modifiers]

| 成员 | 效果 |
|---|---|
| `clear()` | ¶1 变为空路径 |
| `make_preferred()` | ¶2 把每个分隔符换成首选分隔符（POSIX 上不变） |
| `remove_filename()` | ¶5–¶6 删掉 `filename()`，之后 `has_filename()` 为假 |
| `replace_filename(r)` | ¶9 等价于 `remove_filename(); operator/=(r);` |
| `replace_extension(r = path())` | ¶12 删掉现有扩展名；`r` 非空且不以点开头时先加一个点；再 `+= r` |
| `swap(rhs)` | ¶14–¶15 常数时间交换 |

```cpp
path("foo/bar").remove_filename();     // "foo/"
path("/foo").remove_filename();        // "/"
path("/foo").replace_filename("bar");  // "/bar"
path("x.txt").replace_extension("md"); // "x.md"
path("x.txt").replace_extension();     // "x"
```

`remove_filename()` 保留末尾的分隔符，`"foo/bar"` 变成 `"foo/"` 而不是 `"foo"`。要得到父目录，用 `parent_path()`。

## 比较：相等不等于同一个文件 [fs.path.compare]

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

¶1 `p1.compare(p2)` 依次比较：

1. *root-name* 的 `native()` 字符串，不同则返回该结果（¶1.1）；
2. 只有一方有 *root-directory* 时，没有的一方较小（¶1.2–¶1.3）；
3. 否则逐元素按字典序比较 `relative_path()` 各元素的 `native()`（¶1.4–¶1.5）；
4. 都相同返回 0（¶1.6）。

逐元素比较意味着多余的分隔符不影响结果，但末尾分隔符产生的空元素会，`.` 和 `..` 也不会被化简。`==` 和 `<=>` 都由 `compare` 定义（[[fs.path.nonmember#3]]、[[fs.path.nonmember#5]]）。

[[fs.path.nonmember#4]] 的注强调了**相等**和**等价**的区别。`==` 只比较字面表示；`equivalent(p1, p2)`（[[fs.op.funcs]]）访问文件系统，判断两者是否解析到同一个文件。`path("foo") == "bar"` 永远为假，而 `equivalent("foo", "bar")` 在 `foo` 是指向 `bar` 的链接时为真。

[[fs.path.nonmember#2]] 规定 `p1 == p2` 时 `hash_value(p1) == hash_value(p2)`，`std::hash<path>` 与之一致（[fs.path.hash]），所以 `path` 可以直接作为 `unordered_map` 的键。

## 字面运算 [fs.path.gen]

### `lexically_normal()`（¶1）

[[fs.path.generic#6]] 定义了**规范化**（normalization），结果叫**规范形式**（[[g:normal-form-path]]）：

1. 路径为空则停止；
2. 把 *root-name* 中的 `/` 换成首选分隔符；
3. 把每组连续分隔符换成一个首选分隔符；
4. 删除每个 dot 文件名和紧跟的分隔符；
5. 反复删除"非 dot-dot 的文件名、分隔符、dot-dot"及紧跟的分隔符；
6. 有根目录时，删除紧跟在根目录后的 dot-dot 和分隔符；
7. 最后一个文件名是 dot-dot 时，删除末尾分隔符；
8. 路径为空则变为 `.`。

¶1 `lexically_normal()` 返回规范形式：

```cpp
path("foo/./bar/..").lexically_normal();     // "foo/"
path("foo/.///bar/../").lexically_normal();  // "foo/"
```

第 5 步假设 `a/..` 等于什么都没有。在 `a` 是指向别处的符号链接时，这并不成立：

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

字面上 `shortcut/..` 消掉了，得到 `dd`；在文件系统里，它是 `real/sub` 的父目录 `real`。POSIX 按物理目录结构解析 `..`，所以需要真实结果时要用访问文件系统的 `canonical`、`weakly_canonical`（[[fs.op.funcs]]）。

### `lexically_relative(base)`（¶3–¶7）

```cpp
path("/a/d").lexically_relative("/a/b/c");      // "../../d"
path("/a/b/c").lexically_relative("/a/d");      // "../b/c"
path("a/b/c").lexically_relative("a");          // "b/c"
path("a/b/c").lexically_relative("a/b/c/x/y");  // "../.."
path("a/b/c").lexically_relative("a/b/c");      // "."
path("a/b").lexically_relative("/a");           // ""：一个绝对一个相对
```

¶3 如果两者的 *root-name* 不同、一个是绝对路径而另一个不是、`*this` 没有根目录而 `base` 有，或者某个文件名可能被解释为 *root-name*，返回空路径。否则，找出两者第一个不同的元素，从 `base` 剩下的部分数出要退几层（普通文件名加一、dot-dot 减一），生成相应个数的 `..`，再接上 `*this` 剩下的部分。层数为负时返回空路径，两者相同时返回 `.`。

¶4 它不解析符号链接，也不先做规范化。注指出，需要符号链接语义时用 [[fs.op.funcs]] 的 `relative()`，需要规范化时先对两边调用 `lexically_normal()`。

### `lexically_proximate(base)`（¶8）

¶8 `lexically_relative(base)` 不为空就返回它，否则返回 `*this`。也就是能算出相对路径就用相对路径，否则保持原样。

## 迭代器的特殊之处 [fs.path.itr]

¶2 `path::iterator` 是常量迭代器，满足双向迭代器的全部要求，只有一条例外：两个相等的可解引用迭代器 `a == b`，不要求 `*a` 和 `*b` 是同一个对象。¶3 调用 `path` 的任何非 const 成员函数，都会使指向它的迭代器失效。

!!! lawyer "暂存迭代器"
    被放宽的那条，正是前向迭代器的要求"`a == b` 则 `*a` 与 `*b` 绑定到同一个对象"（[[forward.iterators#6]]）。路径的元素并不以 `path` 对象的形式存在于字符串里，迭代器只能在自身内部构造一个 `path` 保存当前元素（libc++ 的成员名就叫 `__stashed_elem_`），`operator*` 返回对它的引用。所以：

    - 复制迭代器后，两者解引用得到不同的对象；迭代器销毁后，先前得到的引用悬垂。
    - `std::reverse_iterator::operator*` 规定为 `Iterator tmp = current; return *--tmp;`（[[reverse.iter.elem]]），返回的是局部副本 `tmp` 内部对象的引用，函数返回时就悬垂了。`path::iterator` 在语义上不满足 [[reverse.iter.requirements]] 的要求，`std::reverse_iterator<path::iterator>` 不能用。
    - libc++ 把它的 `iterator_category` 声明为 `input_iterator_tag`，但 `std::bidirectional_iterator<path::iterator>` 为真，因为概念只检查语法。

    需要反向遍历时，直接对 `path::iterator` 用 `--`，并在迭代器存活期间使用或复制元素。

## 字符串、编码与输出

### 原生格式与通用格式 [fs.path.fmt.cvt]

同一个路径名有两种写法：**原生格式**（[[g:native-pathname-format]]）是操作系统使用的写法，**通用格式**是上面文法描述的写法。第 6 段的注说明，`path` 保存原生格式，同时表现得如同也保存了通用格式。分解、迭代、比较按通用格式工作；`native()`、`+=` 按原生格式工作。

¶1 的注说明，POSIX 上两者相同，不发生转换。区别只在 Windows 这样的系统上出现：

| 观察器 | 返回 | Windows 上 `path("foo\\bar")` |
|---|---|---|
| `native()`、`c_str()`、`wstring()`、`u8string()` 等 | 原生格式（[fs.path.native.obs]） | `foo\bar` |
| `generic_string()`、`generic_u8string()` 等 | 通用格式，分隔符统一为 `/`（[fs.path.generic.obs]） | `foo/bar` |

需要跨平台一致的文本（写配置文件、日志、测试比对）时，用 `generic_*` 版本。`operator string_type()` 是到 `native()` 的隐式转换（[[fs.path.native.obs#4]]）。

### 编码转换 [fs.path.type.cvt]

¶2 参数或返回值的字符类型与 `value_type` 不同时，`path` 会转换编码：

| 字符类型 | 编码 | 转换方式 |
|---|---|---|
| `char` | 原生普通编码，即操作系统当前的路径名编码 | 由操作系统决定；POSIX 上不转换，Windows 上取决于当前代码页 |
| `wchar_t` | 原生宽编码 | 未指定；Windows 上不转换 |
| `char8_t`、`char16_t`、`char32_t` | UTF-8、UTF-16、UTF-32 | 未指定 |

¶2 的注解释了为什么 `char` 不规定为 UTF-8：要和其他用普通字符串表示路径的 C/C++ 函数保持一致。¶3 目标编码表示不了某个字符时，结果未指定。

所以在 Windows 上要可靠地表示 UTF-8 路径，应当用 `char8_t` 字符串（`u8"..."`、`std::u8string`）构造 `path`，而不是 `std::string`，后者会按系统代码页解释。`u8path()` 工厂函数在 C++20 弃用（[[depr.fs.path.factory]]），原因也在这里：直接用 `char8_t` 字符串构造就能表达这是 UTF-8。同样从 C++20 起，`u8string()` 返回 `std::u8string` 而不是 `std::string`（[[diff.cpp17.input.output]]）。

### `string()` 的弃用与 `display_string()`

当前草案把非模板的 `string()` 和 `generic_string()` 移进了附录 D（[[depr.fs.path.obs]]），它们分别等价于新增的 `native_encoded_string()` 和 `generic_native_encoded_string()`。另外新增了 `display_string()`（[[fs.path.native.obs#9]]），返回 `std::format("{}", *this)`，以及对应的 `generic_display_string()`。这是 C++23 之后的新措辞。

动机是区分两种用途：把路径交给需要原生编码字符串的 API，和把路径显示给人看。在 Windows 上，`string()` 按代码页转换，遇到表示不了的字符时结果未指定，用于显示常出现乱码。本机 libc++ 还没有 `display_string` 和 `native_encoded_string`，`string()` 也没有弃用警告。

### 流输出加引号 [fs.path.io]

¶1 `os << p` 等价于 `os << quoted(p.string<charT, traits>())`（[[quoted.manip]]），会加双引号并转义。本页的例子输出里带引号，就是这个原因。要打印不带引号的路径，用 `p.native()` 或 `p.generic_string()`。¶3 `is >> p` 对应地用 `quoted` 读入，可以读回带引号、含空格的路径。

### `formatter<path>` [fs.path.fmtr] {{c++26}}

[[fs.path.fmtr.funcs#1]] 格式说明的形式是：可选的填充与对齐、可选的宽度、可选的 `?`、可选的 `g`。`?` 表示按转义字符串输出（[[format.string.escaped]]），`g` 表示使用通用格式。

与 `<<` 不同，`std::format("{}", p)` 默认不加引号，`{:?}` 才加引号并转义。¶5 规定，`charT` 是 `char`、`value_type` 是 `wchar_t`、字面量编码是 UTF-8 时，把路径从原生宽编码转为 UTF-8，无效的部分替换为 U+FFFD；两者字符类型相同时不转码；其余情形由实现定义。

本机 libc++（Clang 23）还没有提供 `formatter<path>`，`std::format("{}", path)` 编译失败，报 `formatter<std::filesystem::path, char>` 的默认构造函数被隐式删除。

<details class="fine" markdown="1"><summary>其余条文</summary>

[fs.class.path.general] ¶2 是注：`path` 用来处理不同系统表示路径名的字符串类型之间的差异。¶5 定义路径名可以按通用格式或原生格式书写。

[fs.path.fmt.cvt] ¶2 定义**检测格式**（[[g:detected-format]]）：一个实参当且仅当符合通用格式、又不被操作系统接受为原生路径时，才视为通用格式。第 3 段的注说明有些系统无法区分两种格式。¶4 要求格式转换函数 *G*（原生到通用）和 *N*（通用到原生）满足 *G*(*N*(*g*)) = *g*、*N*(*G*(*n*)) = *n*，但两者都不必可逆。¶5 为普通文件和目录写法不同的系统（如 OpenVMS）规定：最后一个元素是分隔符时视为目录。¶7–¶8 规定从一种表示构造或导出新值时，另一种表示如何选取。

[fs.path.req] ¶1 名为 `Source` 的模板参数可以是 `basic_string`、`basic_string_view`、遍历以空字符结尾的字符串（NTCTS）的输入迭代器，或者退化后指向 NTCTS 的字符数组。¶2 接受 `Source` 的函数只在 `Source` 不是 `path`、并且是字符串类型或其 `iterator_traits<decay_t<Source>>::value_type` 是字符类型时参与重载决议。¶4 `Source` 实参不能是空指针。

[fs.path.construct] ¶1–¶4 默认构造得到空路径；从字符串构造时取有效范围、按需转换编码和格式。¶5–¶6 带 `locale` 的版本要求字符类型为 `char`，先用 `loc` 的 `codecvt<wchar_t, char, mbstate_t>` 转成宽字符，`value_type` 不是 `wchar_t` 时再转到原生普通编码。第 7 段的例子是从数据库读出 ISO 8859-1 编码的字符串再构造 `path`。[fs.path.assign] 的赋值函数与构造函数一一对应，`operator=(path&&)` 可以用 `swap` 实现。

</details>

## 思考题

!!! question "思考题 1"
    在 POSIX 上，`path("/a/b") / path("")`、`path("/a/b/") / "c"`、`path("/a/b") / "c/"` 分别是什么？

<details markdown="1">
<summary>答案</summary>

`"/a/b/"`、`"/a/b/c"`、`"/a/b/c/"`。第一个：右边为空，不是绝对路径；左边有 filename `b`，所以加一个分隔符，再追加空串（[[fs.path.append#3]]）。第二个：`"/a/b/"` 的 filename 为空，不加分隔符，直接拼上 `c`。第三个：普通追加，`c/` 保留末尾分隔符。
</details>

!!! question "思考题 2"
    为什么 `path("C:foo").is_absolute()` 在 Windows 上为假，`has_root_name()` 却为真？

<details markdown="1">
<summary>答案</summary>

`C:` 是 *root-name*（[[fs.path.generic#4]]），但后面没有 *root-directory*，路径表示驱动器 C 的当前目录下的 `foo`。确定它的位置还需要一个额外的起点，也就是该驱动器的当前目录，所以按 [[fs.class.path.general#4]] 它不是绝对路径。
</details>

!!! question "思考题 3"
    `std::set<fs::path>` 里能同时放 `"a/b"` 和 `"a//b"` 吗？`"a/b"` 和 `"a/b/"` 呢？

<details markdown="1">
<summary>答案</summary>

前一对不能：两者的元素都是 `a`、`b`，`compare` 结果为 0。后一对能：`"a/b/"` 多一个末尾的空元素（[[fs.path.itr#4]]），比较结果不为 0。
</details>
