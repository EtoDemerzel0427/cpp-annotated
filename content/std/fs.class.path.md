---
title: 路径 path
summary: std::filesystem::path 的完整规则——它只做字面运算、不访问文件系统；通用格式的文法（root-name / root-directory / filename、连续分隔符、dot 与 dot-dot）与 8 步规范化；原生格式与通用格式的双重表示、检测格式、编码转换；operator/= 遇到绝对路径或不同 root-name 时整体替换、+= 是纯字符串拼接；分解函数（filename 对 "foo/" 为空、stem/extension 对点文件的处理）、逐元素比较、lexically_normal/relative/proximate；迭代器的"暂存"特性；<< 加引号；C++26 的 formatter 与 display_string，以及 string() 的弃用
status: done
covers: *
since: c++17
related: filesystems, fs.op.funcs, fs.class.directory.iterator, file.streams, quoted.manip, format, depr.fs.path.obs, depr.fs.path.factory
tags: 标准库, filesystem, path, 路径
updated: 2026-10-18
---

`std::filesystem::path` 是一个**值类型**：它保存一个路径名字符串，并提供按照路径语法拆分、拼接、比较、规范化的操作。它最重要的性质写在 [fs.class.path.general] ¶1：

!!! std
    An object of class path represents a path and contains a pathname. Such an object is concerned only with the lexical and syntactic aspects of a path.

    `path` 只关心路径的**字面与语法**。它表示的路径不必在外部存储中存在，路径名也不必对当前操作系统或某个文件系统有效。

所以 `path` 的所有成员函数都**不访问文件系统**：`lexically_normal()` 不解析符号链接，`==` 不判断是不是同一个文件，`is_absolute()` 只看字符。凡是需要访问文件系统的（`canonical`、`equivalent`、`exists`……）都是 [[fs.op.funcs]] 中的非成员函数。

## 概述（[fs.class.path.general]）

- ¶2（注）：`path` 用于处理不同操作系统表示路径名的字符串类型之间的差异，并在需要时进行编码转换。
- ¶3：**路径**（path）是标识文件在文件系统中位置的元素序列：可选的 *root-name*、可选的 *root-directory*，以及可选的 *filename* 序列。元素个数的上限依赖操作系统。
- ¶4：**绝对路径**无需额外的起点就能无歧义地确定文件位置；**相对路径**不是绝对路径，只有相对于某个隐含的起点解析时才能确定位置。哪些元素决定绝对/相对依赖操作系统。注：路径名 `.` 和 `..` 是相对路径。
- ¶5：**路径名**（pathname）是表示路径的字符串，按通用路径名格式文法（[[g:generic-pathname-format]]）或按依赖操作系统的**原生路径名格式**（[[g:native-pathname-format]]）书写。
- ¶6：**路径名解析**（pathname resolution）是把路径名解析到文件层次结构中某个文件的、依赖操作系统的机制；可能有多个路径名解析到同一个文件。例：POSIX 系统上这一机制由 POSIX 4.12 节"Pathname resolution"规定。

¶7–¶9：`value_type` 是依赖操作系统的、表示路径名的编码字符类型；`preferred_separator` 是依赖操作系统的首选分隔符。例：POSIX 上 `value_type` 是 `char`、`preferred_separator` 是 `'/'`；Windows 上分别是 `wchar_t` 和 `L'\\'`。`string_type` 是 `basic_string<value_type>`。

于是 `path::native()`、`c_str()` 的类型**随平台变化**：在 Windows 上 `p.c_str()` 是 `const wchar_t*`，不能直接传给接受 `const char*` 的函数。

## 通用路径名格式（[fs.path.generic]）

```text
pathname:            root-name(opt) root-directory(opt) relative-path
root-name:           依赖操作系统的字符序列 / 实现定义的字符序列
root-directory:      directory-separator
relative-path:       filename
                     filename directory-separator relative-path
                     空路径
filename:            不含 directory-separator 字符的非空字符序列
directory-separator: preferred-separator directory-separator(opt)
                     fallback-separator directory-separator(opt)
preferred-separator: 依赖操作系统的目录分隔符
fallback-separator:  '/'（当 preferred-separator 不是 '/' 时）
```

`/` 在所有平台上都是合法的分隔符：要么它就是首选分隔符，要么它是后备分隔符。所以用 `/` 写的路径是可移植的。

- ¶1：*filename* 是文件的名字。**dot** 和 **dot-dot** 文件名（恰好一个、两个句点）有特殊含义。以下特性依赖操作系统：允许的字符（注：限制在 POSIX 可移植文件名字符集 `A–Z a–z 0–9 . _ -` 内可获得更好的可移植性）、最大长度、不允许的文件名、有特殊含义的文件名、路径解析时的大小写敏感性、对普通文件以外类型的特殊规则。
- ¶2：除了在 *root-name* 中，**连续多个分隔符等同于一个**。
- ¶3：dot 指当前目录，dot-dot 指父目录；**dot-dot 相对于 *root-directory* 指什么由实现定义**（POSIX 上 `/..` 就是 `/`）。特定文件名对特定操作系统可能有特殊含义。
- ¶4：*root-name* 标识路径名解析的起点。若操作系统没有 *root-name*，至少要有一个实现定义的 *root-name*。注：许多操作系统把以两个分隔符开头的名字（如 `//host`）定义为标识网络资源的 *root-name*；有些把"单个字母加冒号"（如 `C:`）定义为驱动器说明符。
- ¶5：*root-name* 有歧义时取最长的可能。注：在类 POSIX 系统上，不可能出现"有 *root-name* 和 *relative-path* 却没有中间的 *root-directory*"的情况——这种组合只在 Windows 上存在，如 `C:foo`（驱动器 C 的**当前目录**下的 `foo`），它既不是绝对路径，也不是普通的相对路径。

### 规范化（¶6）

通用格式路径名的**规范化**（normalization）步骤：

1. 路径为空则停止。
2. 把 *root-name* 中的每个 `/` 替换为 *preferred-separator*。
3. 把每个 *directory-separator*（一个或多个分隔符）替换为一个 *preferred-separator*。
4. 删除每个 dot 文件名及紧跟其后的分隔符。
5. 只要存在，就删除"非 dot-dot 文件名 + 分隔符 + dot-dot 文件名"及紧跟其后的分隔符。
6. 若有 *root-directory*，删除紧跟在它后面的所有 dot-dot 文件名及其后的分隔符（注：这些 dot-dot 试图引用不存在的父目录）。
7. 若最后一个文件名是 dot-dot，删除末尾的分隔符。
8. 路径为空则加一个 dot。

结果称为**规范形式**（normal form，[[g:normal-form-path]]）。`lexically_normal()` 返回它。第 5 步是纯字面的：它假设 `a/..` 等于"没有"，而这在 `a` 是指向别处的符号链接时**不成立**——见下文"生成"一节的例子。

## 转换（[fs.path.cvt]）

### 格式转换（[fs.path.fmt.cvt]）

- ¶1（注）：POSIX 系统上不应用这些转换，因为通用格式就是可接受的原生路径，函数实参不需要区分两种格式，普通文件和目录的路径语法相同。
- ¶2：有些函数接受**检测格式**（detected-format，[[g:detected-format]]）的实参：它表示通用格式或原生格式的路径名，**当且仅当**它符合通用格式且**不被**操作系统接受为原生路径时，才视为通用格式。
- ¶3（注）：有些操作系统无法无歧义地区分两种格式，这是有意的设计。
- ¶4：路径名按需在通用与原生格式间转换，方式依赖操作系统。记实现的转换函数为 *G*(*n*)（原生到通用）和 *N*(*g*)（通用到原生）：若 *g* = *G*(*n*)，则 *G*(*N*(*g*)) = *g*；若 *n* = *N*(*g*)，则 *N*(*G*(*n*)) = *n*。注：两者都不必可逆。
- ¶5：若原生格式要求普通文件与目录的路径写法不同，则最后一个元素是分隔符时视为目录路径，否则视为普通文件路径。（这是为 OpenVMS 一类系统准备的。）
- ¶6（注）：`path` 保存原生格式路径名，**并表现得如同**也保存了通用格式路径名；实现可以在需要时从原生格式（及其他信息）生成通用格式。
- ¶7–¶8：从单一表示构造或赋值时，用 *G* 或 *N* 选出另一种表示；从某个路径的表示导出新值时，另一种表示选一个能转换回去的值（否则未指定）。

这就是为什么 `path` 的成员规定里反复出现"pathname in the generic format"和"pathname in the native format"：分解函数（`filename`、`parent_path`……）按**通用格式**工作，`native()`、`+=` 按**原生格式**工作。

### 类型与编码转换（[fs.path.type.cvt]）

¶1：普通字符串的**原生编码**是依赖操作系统的当前路径名编码；宽字符串的原生编码是实现定义的执行宽字符集编码。¶2：成员函数的参数或返回值的值类型与 `path::value_type` 不同时，进行值类型和编码转换，方式由值类型决定：

| 值类型 | 编码 | 转换方式 |
|---|---|---|
| `char` | 原生普通编码 | 依赖操作系统。注：POSIX 上不转换；Windows 上由当前 locale 编码与 `AreFileApisANSI` 决定 |
| `wchar_t` | 原生宽编码 | 未指定。注：Windows 上不转换 |
| `char8_t` | UTF-8 | 未指定 |
| `char16_t` | UTF-16 | 未指定 |
| `char32_t` | UTF-32 | 未指定 |

¶2 的注 2 解释为什么 `char` 用"原生普通编码"而不是 UTF-8：这样与其他用普通字符串表示路径的 C/C++ 库函数行为一致，改变它会出人意料。¶3：目标编码无法表示源字符时，结果未指定；实参已经是 `value_type` 时实现不应修改它。

**实践含义**：要在 Windows 上可靠地表示 UTF-8 路径，用 `char8_t` 字符串（`u8"..."`、`std::u8string`）构造 `path`，而不是 `std::string`——后者按系统代码页解释。

## 对 `Source` 的要求（[fs.path.req]）

¶1：名为 `Source` 的模板参数必须是以下之一：`basic_string<EcharT, ...>`、`basic_string_view<EcharT, ...>`（有效范围是 `[begin, end)`）；迭代一个 NTCTS 的 *Cpp17InputIterator*（有效范围到第一个值为 `value_type()` 的元素为止）；退化后指向 NTCTS 开头的字符数组。

¶2：接受 `Source` 的函数只在 `Source` 不是 `path`，且（是 `basic_string`/`basic_string_view` 的特化，或 `iterator_traits<decay_t<Source>>::value_type` 有效并表示可能 const 的编码字符类型）时参与重载决议。¶4：`Source` 类型的实参不得是空指针。

## 构造与赋值（[fs.path.construct]、[fs.path.assign]）

| 构造函数 | 效果 |
|---|---|
| `path() noexcept` | ¶1 `empty()` 为真 |
| 复制、移动 | ¶2 原生与通用格式路径名都与原值相同；移动后源处于有效但未指定的状态 |
| `path(string_type&& source, format fmt = auto_format)` | ¶3 检测格式下的路径名为 `source` 的原值，必要时转换格式 |
| `path(const Source&, fmt)`、`path(first, last, fmt)` | ¶4 取有效范围、按需转换编码，按检测格式构造 |
| `path(const Source&, const locale& loc, fmt)`、`path(first, last, loc, fmt)` | ¶5 *Mandates*：值类型为 `char`；¶6 先用 `loc` 的 `codecvt<wchar_t, char, mbstate_t>` 转成宽字符，若 `value_type` 不是 `wchar_t` 再转到当前普通编码 |

¶7 的例子说明了 locale 版本的用途：从数据库读出 ISO 8859-1 编码的字符串，用一个 8859-1 的 `codecvt` facet 构造 locale，再构造 `path`。

赋值（[fs.path.assign] ¶1–¶8）与构造对应：`operator=(const path&)`、`operator=(path&&)`（注：`swap(p)` 是有效实现）、`operator=(string_type&&)`/`assign(string_type&&)`、`operator=(const Source&)`/`assign(...)`。

## 追加 `/=` 与拼接 `+=`

### `operator/=`（[fs.path.append]）

¶1：追加操作用 `operator/=` 表示"在需要时加上 *preferred-separator*"。

`path& operator/=(const path& p)`：

- ¶2：若 `p.is_absolute() || (p.has_root_name() && p.root_name() != root_name())`，则 **`operator=(p)`**——整体替换。
- ¶3 否则：
    - ¶3.1：若 `p.has_root_directory()`，从通用格式路径名中删除根目录和相对路径；否则，若 `!has_root_directory() && is_absolute()` 或 `has_filename()` 为真，追加 `preferred_separator`。
    - ¶3.2：然后把 `p` 的原生格式路径名（去掉其通用格式中的 *root-name*）追加到原生格式路径名。

标准给出的例子（¶4）：

```cpp
// POSIX：
path("foo") /= path("");        // "foo/"
path("foo") /= path("/bar");    // "/bar"

// Windows：
path("foo") /= path("");        // "foo\\"
path("foo") /= path("/bar");    // "/bar"
path("foo") /= path("c:/bar");  // "c:/bar"
path("foo") /= path("c:");      // "c:"
path("c:") /= path("");         // "c:"
path("c:foo") /= path("/bar");  // "c:/bar"
path("c:foo") /= path("c:bar"); // "c:foo\\bar"
```

即使 `//host` 被解释为 *root-name*，`path("//host")/"foo"` 和 `path("//host/")/"foo"` 都等于 `"//host/foo"`。

`operator/=(const Source&)`、`append(...)`：¶6–¶7 等价于 `operator/=(path(source))`。非成员 `operator/(lhs, rhs)`（[fs.path.nonmember] ¶6）：`return path(lhs) /= rhs;`。

### `operator+=`（[fs.path.concat]）

¶1：把 `path(x).native()` 追加到**原生格式**路径名——纯字符串拼接，不加分隔符、不做任何语法处理。注：这直接操作 `native()`，不一定在操作系统之间可移植。¶3：单个字符版本等价于 `*this += basic_string_view(&x, 1)`。

```cpp title="path-append.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  std::cout << fs::path("/srv/www") / "img/logo.png" << '\n';   // "/srv/www/img/logo.png"
  std::cout << fs::path("/srv/www") / "/etc/passwd" << '\n';    // "/etc/passwd"：右边是绝对路径，整体替换
  std::cout << fs::path("foo") / "" << '\n';                    // "foo/"：追加空路径只加分隔符
  fs::path p = "a/b";
  p += ".txt";                                                  // 纯字符串拼接
  std::cout << p << '\n';                                       // "a/b.txt"
}
```

!!! pitfall "`base / user_input` 不能防止路径逃逸"
    `operator/` 遇到绝对路径会整体替换（¶2），遇到 `..` 则原样保留。所以 `fs::path("/srv/www") / request_path` 在 `request_path` 为 `/etc/passwd` 或 `../../etc/passwd` 时都会指向 `/srv/www` 之外。校验应在解析之后进行：例如先 `weakly_canonical`，再检查结果是否仍以 `canonical(base)` 为前缀（逐元素比较，而不是字符串前缀）。即便如此，检查与使用之间仍有文件系统竞争（[[filesystems]]）。

## 修改器（[fs.path.modifiers]）

| 成员 | 效果 |
|---|---|
| `clear() noexcept` | ¶1 `empty()` 为真 |
| `make_preferred()` | ¶2 把通用格式中的每个分隔符换成首选分隔符（POSIX 上无变化） |
| `remove_filename()` | ¶5–¶6 从通用格式中删除 `filename()`；后条件 `!has_filename()` |
| `replace_filename(r)` | ¶9 等价于 `remove_filename(); operator/=(r);` |
| `replace_extension(r = path())` | ¶12 删除现有 `extension()`；若 `r` 非空且不以点开头，先追加一个点；再 `operator+=(r)` |
| `swap(rhs) noexcept` | ¶14–¶15 交换所有格式的内容，常数时间 |

```cpp
path("foo/bar").remove_filename();   // "foo/"
path("foo/").remove_filename();      // "foo/"
path("/foo").remove_filename();      // "/"
path("/").remove_filename();         // "/"
path("/foo").replace_filename("bar");// POSIX 上 "/bar"
```

注意 `remove_filename()` 保留末尾的分隔符：`"foo/bar"` 变成 `"foo/"` 而不是 `"foo"`——要得到父目录用 `parent_path()`。

## 观察器

### 原生格式（[fs.path.native.obs]）

¶1：所有原生格式观察器返回的字符串都是原生路径名格式。

| 成员 | 返回 |
|---|---|
| `const string_type& native() const noexcept` | ¶2 原生格式路径名 |
| `const value_type* c_str() const noexcept` | ¶3 `native().c_str()` |
| `operator string_type() const` | ¶4 `native()`（隐式转换！） |
| `template<class EcharT, ...> basic_string<EcharT, ...> string(const Allocator& a = Allocator()) const` | ¶5–¶6 `native()`，按需转换编码，内存由 `a` 分配 |
| `native_encoded_string()`、`wstring()`、`u8string()`、`u16string()`、`u32string()` | ¶7–¶8 `native()`，按 [fs.path.cvt] 转换 |
| `std::string display_string() const` | ¶9 `std::format("{}", *this)`；注：返回的字符串适合用于格式化与 `print` 函数 |

`u8string()` 自 C++20 起返回 `std::u8string`（之前返回 `std::string`），把结果赋给 `std::string` 的旧代码不再能编译（[[diff.cpp17.input.output]]）。

!!! history "`string()` 被弃用"
    当前草案把非模板的 `std::string string() const` 和 `std::string generic_string() const` 移到了附录 D（[[depr.fs.path.obs]]），它们分别返回 `native_encoded_string()` 和 `generic_native_encoded_string()`；同时新增了 `display_string()`/`generic_display_string()`。这是 C++23 之后的新措辞。动机是区分两种用途：把路径交给需要"原生编码"字符串的 API（`native_encoded_string`），与把路径**显示**给人看（`display_string`，经 `formatter` 在 UTF-8 字面量编码下转码并替换无效码元）。在 Windows 上，`string()` 按系统代码页转换，遇到无法表示的字符时结果未指定，用于显示时常产生乱码。本机 libc++ 尚未提供 `display_string`/`native_encoded_string`，`string()` 也没有弃用警告。

另外，`u8path()` 工厂函数自 C++20 起已弃用（[[depr.fs.path.factory]]）：用 `std::u8string` 或 `u8""` 字面量直接构造 `path` 即可表达"这是 UTF-8"。

### 通用格式（[fs.path.generic.obs]）

¶1：通用格式观察器返回按通用路径名格式书写的字符串，用单个 `'/'` 作分隔符。¶2 例：在首选分隔符为反斜杠的系统上，`path("foo\\bar").generic_string()` 返回 `"foo/bar"`。成员与原生版本一一对应：`generic_string<EcharT>()`、`generic_native_encoded_string()`、`generic_wstring()`、`generic_u8string()`、`generic_u16string()`、`generic_u32string()`、`generic_display_string()`（`std::format("{:g}", *this)`）。

需要跨平台一致的文本表示（写配置文件、日志、比较测试输出）时，用 `generic_*` 版本。

## 比较（[fs.path.compare]、[fs.path.nonmember]）

`int compare(const path& p) const noexcept`（¶1）：

1. 比较 `root_name().native()`，不同则返回该结果；
2. 否则，`*this` 无根目录而 `p` 有，返回负值；反之返回正值；
3. 否则，**逐元素**按字典序比较 `relative_path()` 各元素的 `native()`；
4. 都相同返回 0。

¶2：与字符串比较的重载等价于 `compare(path(s))`。`operator==` 是 `compare(rhs) == 0`，`operator<=>` 是 `compare(rhs) <=> 0`（返回 `strong_ordering`）。

逐元素比较意味着：多余的分隔符不影响相等（`"a//b" == "a/b"`），但**末尾分隔符**会产生一个空元素，于是 `"a/b/" != "a/b"`；`.` 和 `..` 不被化简，`"a/./b" != "a/b"`。

[fs.path.nonmember] ¶4 的注强调：**相等**（`==`，只看字面表示）与**等价**（`equivalent()`，判断是否解析到同一个文件系统实体，[[fs.op.funcs]]）是两回事。`path("foo") == "bar"` 永远不为真，而 `equivalent("foo", "bar")` 在两者解析到同一文件时为真。

`hash_value(p)`（¶2）：`p1 == p2` 时 `hash_value(p1) == hash_value(p2)`。`hash<filesystem::path>`（[fs.path.hash]）的结果与 `hash_value` 相同，所以 `path` 可以直接作为 `unordered_map` 的键。

## 分解（[fs.path.decompose]）与查询（[fs.path.query]）

| 成员 | 规定 |
|---|---|
| `root_name()` | ¶1 通用格式中的 *root-name*，没有则空 |
| `root_directory()` | ¶2 *root-directory*，没有则空 |
| `root_path()` | ¶3 `root_name() / root_directory()` |
| `relative_path()` | ¶4 从 `root_path()` 之后第一个 *filename* 开始的部分 |
| `parent_path()` | ¶5 `has_relative_path()` 为假时返回 `*this`；否则返回通用格式路径名的最长前缀，使其迭代时**少一个元素** |
| `filename()` | ¶6 `relative_path().empty() ? path() : *--end()` |
| `stem()` | ¶8 设 `f` 为 `filename()`：若 `f` 除开头的点外不含点，或只由一两个点组成，返回 `f`；否则返回 `f` 中最后一个点之前的部分 |
| `extension()` | ¶10 `filename()` 中不属于 `stem()` 的后缀 |

查询函数 `has_root_name()`、`has_root_directory()`、`has_root_path()`、`has_relative_path()`、`has_parent_path()`、`has_filename()`、`has_stem()`、`has_extension()` 都是"对应分解结果非空"；`empty()` 看通用格式是否为空；`is_absolute()`（¶10）看原生格式是否包含绝对路径——¶11 例：`path("/").is_absolute()` 在 POSIX 上为真、在 Windows 上为**假**（没有驱动器名）。

```cpp title="path-decompose.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

void show(const fs::path& p) {
  std::cout << p << ": parent=" << p.parent_path() << " filename=" << p.filename()
            << " stem=" << p.stem() << " ext=" << p.extension() << '\n';
}

int main() {
  show("/usr/lib/libc.so.6");  // parent="/usr/lib" filename="libc.so.6" stem="libc.so" ext=".6"
  show("/usr/lib/");           // parent="/usr/lib" filename="" stem="" ext=""
  show("archive.tar.gz");      // parent="" filename="archive.tar.gz" stem="archive.tar" ext=".gz"
  show(".bashrc");             // parent="" filename=".bashrc" stem=".bashrc" ext=""
  show("..");                  // parent="" filename=".." stem=".." ext=""
  show("/");                   // parent="/" filename="" stem="" ext=""
}
```

几个值得注意的结果：

- **`"/usr/lib/"` 的 `filename()` 为空**，`parent_path()` 是 `"/usr/lib"`：末尾分隔符在迭代中产生一个空元素（见下文），`filename()` 取的就是这个空元素，`parent_path()` 去掉的也是它。所以对目录路径，结尾有没有 `/` 会影响分解结果——这是最常见的 `path` 陷阱。
- `".bashrc"` 的扩展名为空、主干是整个名字：开头的点不算扩展名分隔符（¶8.1）。¶11 例：`"..bar"` 的扩展名是 `".bar"`、主干是 `"."`。
- ¶12（注）：句点包含在 `extension()` 的结果里，这样可以区分"没有扩展名"（`"foo"` → `""`）和"空扩展名"（`"foo."` → `"."`）。
- ¶13（注）：在非 POSIX 系统上，`p.stem() + p.extension() == p.filename()` 可能为假，尽管它们的通用格式路径名相同。
- 剥掉多重扩展名：¶9 的例子 `for (; !p.extension().empty(); p = p.stem())` 依次输出 `.tar`、`.baz`、`.bar`（对 `"foo.bar.baz.tar"`）。

## 生成（[fs.path.gen]）

### `lexically_normal()`（¶1–¶2）

返回通用格式路径名的规范形式（见上文 8 个步骤）。例：

```cpp
assert(path("foo/./bar/..").lexically_normal() == "foo/");
assert(path("foo/.///bar/../").lexically_normal() == "foo/");
```

Windows 上结果的分隔符是反斜杠，但不影响路径相等性。

### `lexically_relative(base)`（¶3–¶7）

¶3：若下列任一成立，返回空路径 `path()`：`root_name() != base.root_name()`；`is_absolute() != base.is_absolute()`；`!has_root_directory() && base.has_root_directory()`；`relative_path()` 或 `base.relative_path()` 中有某个 *filename* 可以被解释为 *root-name*（注：POSIX 上不会发生）。

否则，如同 `auto [a, b] = mismatch(begin(), end(), base.begin(), base.end());` 找到第一个不匹配的元素：

- 若 `a == end()` 且 `b == base.end()`，返回 `path(".")`；
- 否则设 `n` 为 `[b, base.end())` 中**不是 dot、dot-dot 或空**的 filename 个数**减去** dot-dot 的个数；`n < 0` 时返回 `path()`；
- `n == 0` 且（`a == end()` 或 `a->empty()`）时返回 `path(".")`；
- 否则返回一个默认构造的 `path`，依次 `/= path("..")` `n` 次，再对 `[a, end())` 的每个元素 `/=`。

¶4：返回 `*this` 相对于 `base` 的路径；**不解析符号链接，也不先规范化** `*this` 或 `base`。¶6–¶7（注）：需要符号链接语义时用操作函数 `relative()`；需要规范化时先对两者调用 `lexically_normal()`。

```cpp
assert(path("/a/d").lexically_relative("/a/b/c") == "../../d");
assert(path("/a/b/c").lexically_relative("/a/d") == "../b/c");
assert(path("a/b/c").lexically_relative("a") == "b/c");
assert(path("a/b/c").lexically_relative("a/b/c/x/y") == "../..");
assert(path("a/b/c").lexically_relative("a/b/c") == ".");
assert(path("a/b").lexically_relative("c/d") == "../../a/b");
```

### `lexically_proximate(base)`（¶8–¶10）

若 `lexically_relative(base)` 不是空路径就返回它，否则返回 `*this`。也就是"能算出相对路径就用相对路径，否则保持原样"。

### 字面运算与真实解析不一致的例子

```cpp title="lexical-vs-real.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  fs::create_directories("dd/real/sub");
  fs::create_directory_symlink("real/sub", "dd/shortcut");   // dd/shortcut → dd/real/sub
  fs::path p = "dd/shortcut/..";
  std::cout << p.lexically_normal() << '\n';                                    // "dd/"：字面上消掉了
  std::cout << fs::canonical(p).lexically_relative(fs::canonical(".")) << '\n'; // "dd/real"：真实的父目录
  fs::remove_all("dd");
}
```

`shortcut/..` 在字面上是 `dd`，在文件系统里却是 `real/sub` 的父目录 `real`。这就是 POSIX 规定 `..` 必须按**物理**目录结构解析的原因，也是 `canonical`/`weakly_canonical` 要访问文件系统的原因（[[fs.op.funcs]]）。

## 迭代器（[fs.path.itr]）

- ¶1：路径迭代器遍历通用格式路径名的**元素**。
- ¶2：`path::iterator` 是常量迭代器，满足双向迭代器的所有要求，**除了**：对可解引用的 `a == b`，不要求 `*a` 和 `*b` 绑定到同一个对象。`value_type` 是 `path`。
- ¶3：调用 `path` 的任何非 const 成员函数使所有指向其元素的迭代器失效。
- ¶4 正向遍历顺序：*root-name*（若有）；*root-directory*（若有；注：可能需要使用通用格式才能保证正确的字典序比较）；每个 *filename*（若有）；**若有末尾的非根分隔符，一个空元素**。¶5：反向遍历是正向的逆序。
- ¶6–¶7：`begin()` 指向第一个存在的元素，没有元素则等于 `end()`。

```cpp title="path-iterate.cpp" ok
#include <filesystem>
#include <iostream>
namespace fs = std::filesystem;

int main() {
  for (const auto& e : fs::path("/a//b/")) std::cout << '[' << e.native() << ']';
  std::cout << '\n';                      // [/][a][b][]：根目录、两个文件名、末尾的空元素
  std::cout << std::boolalpha
            << (fs::path("a//b") == fs::path("a/b")) << ' '     // true
            << (fs::path("a/b/") == fs::path("a/b")) << ' '     // false
            << (fs::path("a/./b") == fs::path("a/b")) << '\n';  // false
}
```

!!! lawyer "`path::iterator` 是\"暂存迭代器\""
    ¶2 放宽的那条要求，正是 *Cpp17ForwardIterator* 的"`a == b` 则 `*a` 与 `*b` 绑定到同一个对象"（[[forward.iterators#6]]）。原因是路径元素并不作为 `path` 对象存在于字符串里，迭代器只能在**自身内部**构造一个 `path` 来保存当前元素（本机 libc++ 的成员名就叫 `__stashed_elem_`），`operator*` 返回对它的引用。于是：

    - 复制迭代器后，原迭代器和副本解引用得到的是**不同**对象；迭代器销毁后，之前得到的引用悬垂。
    - `std::reverse_iterator` 的 `operator*` 被规定为 `Iterator tmp = current; return *--tmp;`（[[reverse.iter.elem]]）——返回的是对局部副本 `tmp` 内部对象的引用，函数返回后即悬垂。`reverse_iterator` 要求其模板参数满足 *Cpp17BidirectionalIterator* 或模拟 `bidirectional_iterator`（[[reverse.iter.requirements]]），`path::iterator` 在语义上两者都不满足，所以 `std::reverse_iterator<path::iterator>` 不能使用。
    - 本机 libc++ 把 `iterator_traits<path::iterator>::iterator_category` 声明为 `input_iterator_tag`，而 `std::bidirectional_iterator<path::iterator>` 在语法上为真（概念只能检查语法，语义要求无法检查）。

    需要反向遍历时，直接对 `path::iterator` 用 `--`，并在迭代器存活期间使用（或复制）元素。

## 插入与提取（[fs.path.io]）

- `operator<<(os, p)`：¶1 等价于 `os << quoted(p.string<charT, traits>())`——**加引号、转义**（[[quoted.manip]]）。所以 `std::cout << p` 打印 `"dir/file name.txt"`（带双引号）。要打印不带引号的路径，用 `p.native()`、`p.generic_string()` 或 `std::print("{}", p)`（C++26）。
- `operator>>(is, p)`：¶3 `basic_string<charT, traits> tmp; is >> quoted(tmp); p = tmp;`——支持读回带引号、含空格的路径。

## 格式化支持（[fs.path.fmtr]）{{c++26}}

```cpp
template<class charT> struct formatter<filesystem::path, charT> {
  constexpr void set_debug_format();
  constexpr typename basic_format_parse_context<charT>::iterator parse(basic_format_parse_context<charT>& ctx);
  template<class FormatContext>
    typename FormatContext::iterator format(const filesystem::path& path, FormatContext& ctx) const;
};
```

[fs.path.fmtr.funcs] ¶1：格式说明为 *path-format-spec*：`fill-and-align`(opt) `width`(opt) `?`(opt) `g`(opt)。`?` 表示按转义字符串格式化（[[format.string.escaped]]），`g` 表示用通用格式。¶2：`set_debug_format()` 如同解析到了 `?`。¶5 `format`：设 `s` 为 `g` 时的 `p.generic_string<path::value_type>()`、否则的 `p.native()`，按说明调整后写出。若 `charT` 是 `char`、`value_type` 是 `wchar_t`、且字面量编码是 UTF-8，则把路径从原生宽编码转码为 UTF-8，把非良构子序列的最大部分替换为 U+FFFD；`charT` 与 `value_type` 相同则不转码；其余情形的转码由实现定义。

与 `operator<<` 不同，默认的 `{}` **不加引号**；`{:?}` 才加引号并转义。

!!! impl "libc++ 尚未提供 `formatter<path>`"
    本机 libc++（Clang 23）中 `__cpp_lib_format_path` 的定义被注释掉；`std::format("{}", path)` 编译失败（`formatter<path, char>` 的默认构造函数被隐式删除）。

## 思考题

<details markdown="1">
<summary>1. 在 POSIX 上，<code>path("/a/b") / path("")</code>、<code>path("/a/b/") / "c"</code>、<code>path("/a/b") / "c/"</code> 分别是什么？</summary>

`"/a/b/"`、`"/a/b/c"`、`"/a/b/c/"`。第一个：`p` 为空，不是绝对路径、没有根目录；`*this` 有 filename（`b`），所以追加一个分隔符，再追加空串（[[fs.path.append#3]]）。第二个：`"/a/b/"` 的 filename 为空（末尾空元素），`has_filename()` 为假，且它有根目录，所以**不**追加分隔符，直接拼上 `c`。第三个：普通追加，`c/` 原样保留末尾分隔符。
</details>

<details markdown="1">
<summary>2. 为什么 <code>path("C:foo").is_absolute()</code> 在 Windows 上为假，<code>path("C:foo").has_root_name()</code> 却为真？</summary>

`C:` 是 *root-name*（[[fs.path.generic#4]]），但它后面没有 *root-directory*，所以路径表示"驱动器 C 的**当前目录**下的 foo"——需要一个额外的起点（该驱动器的当前目录）才能确定位置，按 [[fs.class.path.general#4]] 不是绝对路径。这种"有根名、无根目录"的组合在 POSIX 上不可能出现（¶5 的注）。
</details>

<details markdown="1">
<summary>3. <code>std::set&lt;fs::path&gt;</code> 里能同时放 <code>"a/b"</code> 和 <code>"a//b"</code> 吗？能同时放 <code>"a/b"</code> 和 <code>"a/b/"</code> 吗？</summary>

前者不能：`compare` 逐元素比较，`"a//b"` 与 `"a/b"` 的元素都是 `a`、`b`，`<=>` 为相等。后者能：`"a/b/"` 多一个末尾的空元素（[[fs.path.itr#4]]），比较结果不等。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 本质 | 纯字面的值类型；成员函数从不访问文件系统 |
| 两种格式 | 原生格式（`native()`、`+=`）与通用格式（分解、迭代、`generic_*`）；POSIX 上相同 |
| 编码 | `char` 用原生普通编码（Windows 上是代码页）；要表达 UTF-8 用 `char8_t` |
| `/=` | 右侧是绝对路径或根名不同则整体替换；否则必要时加分隔符 |
| 末尾分隔符 | 产生空元素：`filename()` 为空、比较时不等于无末尾分隔符的路径 |
| `stem`/`extension` | 开头的点不算扩展名；`extension()` 包含点 |
| 生成 | `lexically_normal/relative/proximate` 不解析符号链接；需要真实语义用 `canonical`/`relative` |
| 迭代器 | 暂存迭代器：不能用于 `reverse_iterator`，引用随迭代器失效 |
| 输出 | `<<` 加引号；C++26 `formatter<path>` 默认不加引号（libc++ 尚未实现） |
