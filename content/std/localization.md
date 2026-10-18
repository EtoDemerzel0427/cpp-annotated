---
title: 本地化库：locale 与 facet
summary: std::locale 的对象模型——一组按“facet 类型”（实为 Facet::id）索引的、引用计数的不可变 facet；category 位掩码、有名字与无名字的 locale、locale::global 与 C locale 的联动、use_facet 返回引用的生命周期、facet 的 refs 参数与 delete 语义，以及 isspace(c, loc) 等便利函数
status: draft
covers: localization.general, locale.syn, locales, locale, locale.general, locale.types, locale.category, locale.facet, locale.id, locale.cons, locale.members, locale.operators, locale.statics, locale.global.templates, locale.convenience, classification, conversions.character
related: text, locale.categories, c.locales, text.encoding, format.string.std, iostreams.base, res.on.data.races, bitmask.types
tags: 标准库, locale, facet, 本地化, iostream
updated: 2026-10-18
---

[localization] 是 C++98 留下的本地化框架。它要解决的问题是：同一个程序，在德国应把 `1234.5` 输出成 `1.234,5`，在美国是 `1,234.5`；日期、货币、字符分类、字符串排序也各有规矩。C 库用一个**进程全局**的 `setlocale` 解决这个问题；C++ 的做法是把这些规则封装成对象——`std::locale`——并允许每个流各自 imbue 一个。

¶1（[localization.general]）列出它覆盖的领域：字符分类与字符串排序、数值/货币/日期时间的格式化与解析、消息检索。¶2 与表 90 把本节分成三块：

| 子条款 | 头文件 | 本站笔记 |
|---|---|---|
| [locales] | `<locale>` | 本页 |
| [locale.categories] | `<locale>` | [[locale.categories]] |
| [c.locales] | `<clocale>` | [[c.locales]] |

[locale.syn] 的概要声明了 `locale`、`use_facet`/`has_facet`、14 个便利函数（`isspace(c, loc)` … `tolower(c, loc)`），以及六个类别的全部 facet 模板（`ctype`、`codecvt`、`num_get`、`num_put`、`numpunct`、`collate`、`time_get`、`time_put`、`money_get`、`money_put`、`moneypunct`、`messages` 及其 `_byname` 版本）。脚注说明在本节中 `tm` 是不完整类型，定义在 `<ctime>`。

## locale 的对象模型（[locale.general]）

### facet 既是接口也是索引（¶1–¶4）

!!! std
    Class `locale` implements a type-safe polymorphic set of facets, indexed by facet *type*.

`locale` 是一组**按 facet 类型索引**的多态 facet 集合。“facet 具有双重角色”：一方面它就是一个类接口（比如 `numpunct<char>` 有 `decimal_point()`），另一方面它的类型本身就是在 locale 里查找它的键。

访问 facet 只有两个入口：`use_facet<Facet>(loc)` 返回引用（不存在则抛 `bad_cast`），`has_facet<Facet>(loc)` 询问是否存在（¶2、¶4）。用户自定义的 facet 可以装进 locale，使用方式和标准 facet 完全一样。

注 1（¶5）列出两个例外的“便捷通道”：`locale` 本身有一个 `operator()` 可以当字符串比较谓词（用 `collate` facet），以及全局的 `isspace(c, loc)` 一类函数。

物理图景：一个 `locale` 对象只是一个指针，指向一个**引用计数**的、内部按 `locale::id` 编号排列的 facet 指针数组。拷贝 `locale` 很便宜（增加引用计数）；facet 本身一旦装入就不再改变。

### 引用的有效期与结果的稳定性（¶6–¶7）

¶6：通过 `use_facet` 取得的 facet 引用，**只要还有某个 locale 对象引用该 facet**，就一直可用，其成员函数的结果可以缓存复用。[locale.global.templates]/4 给出了更直接的保证：返回的引用至少在 `loc` 的任一副本存在期间有效。

¶7：在同一 locale 中的同一 facet 对象上，连续调用同一成员函数，结果必须相同——facet 是不可变的。这是“可以缓存”的理论基础：iostream 实现通常在 imbue 时把 `ctype`/`numpunct` 指针缓存在流里。

!!! ub "临时 locale 返回的 facet 引用"
    ```cpp
    const auto& np = std::use_facet<std::numpunct<char>>(std::locale("de_DE.UTF-8"));
    char c = np.decimal_point();   // UB: 临时 locale 已销毁，可能已经没有 locale 引用该 facet
    ```
    `use_facet` 的引用由 locale 的引用计数“托管”。对命名 locale，实现往往内部还有缓存，使这段代码“碰巧能跑”，但标准不保证。正确做法是先把 locale 存进具名变量。

### 名字与相等（¶8）

由名字字符串构造的 locale（如 `"POSIX"`），或由两个有名字的 locale 的部分组合而成的 locale，**有名字**；其他都没有。有名字的 locale 可以按名字比较相等；无名 locale 只与它自己（及其副本）相等。无名 locale 的 `name()` 返回 `"*"`。

这一规则直接决定了 `locale::global` 能否同步 C locale（见下文），因为只有有名字的 locale 才能交给 `setlocale`。

### 全局 locale：一个还是每线程一个（¶9）

!!! std
    Whether there is one global locale object for the entire program or one global locale object per thread is implementation-defined.

是否每个线程一个全局 locale 由实现定义（{{impl}}），标准建议每线程一个；若只有一个，实现**不必**避免其上的数据竞争（[[res.on.data.races]]）。主流实现（libstdc++、libc++、MSVC STL）都是进程级的单一全局 locale，所以在多线程程序里调用 `locale::global` 需要自行同步。

## 类型（[locale.types]）

### `locale::category`（[locale.category]）

¶1：`category` 就是 `int`，取值是位掩码元素 `collate`、`ctype`、`monetary`、`numeric`、`time`、`messages`，外加 `none == 0` 和 `all`（所有类别的并集）。概要里的具体数值“仅供说明”。

¶2 与表 91 规定每个类别**至少**包含哪些 facet：

| 类别 | facet（各有 `char` 与 `wchar_t` 版本） |
|---|---|
| `collate` | `collate` |
| `ctype` | `ctype`，`codecvt<char, char, mbstate_t>`，`codecvt<wchar_t, char, mbstate_t>` |
| `monetary` | `moneypunct`（含 `Intl = true`）、`money_get`、`money_put` |
| `numeric` | `numpunct`、`num_get`、`num_put` |
| `time` | `time_get`、`time_put` |
| `messages` | `messages` |

`char16_t`/`char32_t` 的 `codecvt` 特化已被移到附录 [[depr.locale.category]]（已弃用）。¶3：任何构造出来的 locale（以及 `classic()`）上，表 91 中所有 facet 的 `has_facet` 都为真——标准 facet 永远齐全。¶4 与表 92 要求实现提供的额外特化（各 `_byname` 版本，以及对任意迭代器类型的 `num_get`/`num_put`/`money_get`/…）。

¶5 是一条容易忽略的规定：标准提供的 `num_get`/`num_put` 实现**只会**对 `numpunct<charT>` 和 `ctype<charT>` 调用 `use_facet`，且所用的 locale 是 `ios_base&` 实参的 `getloc()`。也就是说，你替换了流上的 `numpunct`，`num_put` 就一定会用到它。

### `locale::facet`（[locale.facet]）

!!! std
    A class is a *facet* if it is publicly derived from another facet, or if it is a class derived from `locale::facet` and contains a publicly accessible declaration as follows: `static ::std::locale::id id;`

¶1 给出 [[g:facet]] 的定义：要么公开派生自另一个 facet，要么派生自 `locale::facet` 且有一个公开的 `static locale::id id;`。脚注强调这是**完整的**要求——facet 不需要公开的拷贝构造、赋值、默认构造或析构。事实上 `locale::facet` 删除了拷贝，析构函数是 `protected` 的，因此 facet 只能 `new` 出来交给 locale 管理。

¶2：要求 facet 的模板参数（名为 `Facet`）若传入非 facet 类型，或 `volatile` 限定的 facet，程序{{ill-formed}}；`const` 限定的 facet 是合法实参。

!!! lawyer "派生 facet 不声明自己的 id 会怎样"
    “公开派生自另一个 facet”的类也是 facet，而它继承来的 `id` 就是基类的 `id`。所以 `struct my_punct : std::numpunct<char> {...}` **和 `numpunct<char>` 占用同一个槽位**：`locale(loc, new my_punct)` 替换的正是 `numpunct<char>`，这也是定制标准 facet 的标准做法。副作用是 `has_facet<my_punct>(std::locale::classic())` 同样为真——它查的只是那个槽位里有没有东西。此时若调用 `use_facet<my_punct>(classic())`，得到的“`my_punct&`”实际指向一个 `numpunct<char>` 对象；libc++ 的实现是一个 `static_cast`，后续访问 `my_punct` 特有的成员就是 {{ub}}。想要一个独立的新 facet，就必须在派生类里重新声明 `static std::locale::id id;`。

¶3：构造函数的 `refs` 参数管理生命周期：`refs == 0` 时，**最后一个包含该 facet 的 locale 销毁时**，实现执行 `delete static_cast<locale::facet*>(f)`；`refs == 1` 时实现永不销毁它（适合静态存储期或自己管理的 facet）。¶4：所有标准 facet 的构造函数都接受并转发这个参数，且所有单参数构造函数都是 `explicit` 的。

¶5：对于有 `_byname` 版本的 facet，`xxx_byname(name)` 实现的语义等价于 `locale(name)` 中的对应 facet；没有 `_byname` 版本的 facet（如 `num_get`），基类通过查询其他 facet 来实现命名 locale 的语义。

### `locale::id`（[locale.id]）

¶1：`id` 用作查找 facet 的索引，并封装初始化。它不可拷贝、不可赋值。注 1 解释了一个工程细节：iostream 可能在静态初始化期间就被使用，因此 `id` 的初始化不能依赖动态初始化。一种策略是在 facet 第一次装入 locale 时才给 `id` 分配编号——这只依赖静态存储在构造函数运行前被零初始化（[[basic.start.static]]）。

## 构造、成员与运算符（[locale.cons]、[locale.members]、[locale.operators]）

| 构造 | 语义 | 是否有名字 |
|---|---|---|
| `locale()`（¶1） | 当前全局 locale 的副本；从未调用过 `global` 则同 `classic()` | 同全局 locale |
| `locale(const char* name)`（¶2–¶4） | 按 C locale 名字构造；名字无效或为空指针抛 `runtime_error` | 有 |
| `locale(other, name, cats)`（¶6–¶9） | `other` 的副本，但 `cats` 指定的类别取自 `locale(name)` | 当且仅当 `other` 有 |
| `locale(other, Facet* f)`（¶11–¶12） | `other` 的副本，用 `f` 替换 `Facet` 槽位；`f` 为空则就是 `other` | `f` 非空则**无名** |
| `locale(other, one, cats)`（¶13–¶15） | `cats` 类别的 facet 取自 `one` | `cats == none` 时同 `other`；否则两者都有名字才有 |

¶4：合法的名字只有 `"C"`、`""`（用户环境的偏好，即环境变量所指）和由实现定义的其他值。¶6、¶13：`cats` 必须是合法的 category 值（Preconditions）。

[locale.members]：

- `combine<Facet>(other)`（¶1–¶4）：`*this` 的副本，但 `Facet` 取自 `other`；`other` 没有该 facet 抛 `runtime_error`；结果无名。
- `name()`（¶5）：有名字返回名字，否则 `"*"`。
- `encoding()`（¶6–¶7，{{c++26}}）：*Mandates* `CHAR_BIT == 8`；返回代表该 locale 关联编码方案的 `text_encoding`（由实现定义，见 [[text.encoding]]）。libc++ 用 `name()` 查询，因此无名 locale 得不到有意义的结果。

[locale.operators]：

- `operator==`（¶1）：同一个 locale、互为副本、或都有名字且名字相同时为真。注意：两个无名 locale 即使 facet 完全相同也不相等。
- `operator()(s1, s2)`（¶2–¶5）：用 `collate<charT>` 比较两个 `basic_string`，返回 `compare(...) < 0`。于是 locale 本身就满足比较谓词要求，可以写 `std::sort(v.begin(), v.end(), loc)`（例 1）。

## 全局 locale 与 classic（[locale.statics]）

!!! std
    If the argument has a name, does `setlocale(LC_ALL, loc.name().c_str());` otherwise, the effect on the C locale, if any, is implementation-defined.

`locale::global(loc)`（¶1–¶3）：设置全局 locale，使以后的 `locale()` 返回它的副本；**如果 `loc` 有名字，还会调用 `setlocale(LC_ALL, ...)`**，否则对 C locale 的影响由实现定义。返回旧的全局 locale。¶3：除了 `global` 之外，没有任何库函数会改变 `locale()` 的返回值——特别是，直接调用 C 的 `setlocale` **不会**影响 C++ 全局 locale。

这一不对称是许多诡异 bug 的根源：

- `std::locale::global(std::locale(""))` 会同时改变 C 库（`printf`、`strtod`…）的行为；
- `std::locale::global(std::locale(std::locale::classic(), new my_punct))`（无名）在 libc++/libstdc++ 上**不**改变 C locale；
- `setlocale(LC_ALL, "")` 只改 C locale，之后新建的 `std::locale()` 仍是旧的全局 locale。

注意已经存在的流不受 `global` 影响：`std::cout` 在构造时 imbue 了当时的全局 locale，之后要改需显式 `std::cout.imbue(...)`。

`classic()`（¶4–¶6）返回 `"C"` locale，等价于 `locale("C")`；它、它的 facet 及其成员函数“不随时间改变”。

## 便利接口（[locale.convenience]）

[classification]：`isspace(c, loc)` … `isblank(c, loc)` 共 12 个函数模板，各返回 `use_facet<ctype<charT>>(loc).is(ctype_base::F, c)`。与 `<cctype>` 的 `std::isspace(int)` 不同，这些模板接受 `charT`，**没有** “实参必须可表示为 `unsigned char`” 的 UB 陷阱（见 [[text.c.strings]]）。脚注提示：在循环中应缓存 `ctype` facet 或使用其向量版本 `is(low, high, vec)`，因为每次调用都要做一次 `use_facet`。

[conversions.character]：`toupper(c, loc)`/`tolower(c, loc)` 转发给 `ctype<charT>` 的同名成员。注意这是**逐字符**映射，无法处理 `ß` → `SS` 这类一对多的大小写转换。

## 示例：定制 numpunct

```cpp run title="custom-numpunct.cpp" ok
#include <cassert>
#include <format>
#include <locale>
#include <sstream>
#include <string>

struct swiss_punct : std::numpunct<char> {
protected:
    char do_thousands_sep() const override { return '\''; }
    std::string do_grouping() const override { return "\3"; }    // 每 3 位一组
    std::string do_truename() const override { return "ja"; }
};

struct bad_punct : std::numpunct<char> {
protected:
    std::string do_grouping() const override { return "3"; }     // '3' == 51：每 51 位一组！
};

int main() {
    // refs == 0：最后一个持有它的 locale 销毁时由库 delete
    std::locale loc(std::locale::classic(), new swiss_punct);
    assert(loc.name() == "*");                        // 装入自定义 facet 后 locale 没有名字
    // swiss_punct 没有声明自己的 id，swiss_punct::id 就是 numpunct<char>::id：
    // 二者共用同一个“槽位”，所以连 classic() 也“有” swiss_punct
    assert(std::has_facet<swiss_punct>(std::locale::classic()));

    std::ostringstream os;
    os.imbue(loc);
    os << 1234567 << ' ' << std::boolalpha << true;
    assert(os.str() == "1'234'567 ja");

    assert(std::format(loc, "{:L}", 1234567) == "1'234'567");   // format 的 L 选项也走 numpunct
    assert(std::format(loc, "{}", 1234567) == "1234567");       // 没有 L 就与 locale 无关

    std::ostringstream os2;
    os2.imbue(std::locale(std::locale::classic(), new bad_punct));
    os2 << 1234567;
    assert(os2.str() == "1234567");                    // 不到 51 位，根本不分组
}
```

`grouping()` 返回的 `string` 被当作**整数向量**使用（[[locale.categories]] 中 [facet.numpunct.virtuals]/3），`"3"` 是字符 `'3'`，值为 51——标准的脚注也专门用“(!)”提醒了这一点。

## 常见误区

!!! pitfall "以为 `std::locale(“”)` 一定可用"
    `locale("")` 取决于运行环境的 `LANG`/`LC_*` 变量；若环境变量指向系统未安装的 locale，构造函数抛 `runtime_error`（¶3）。容器镜像里常见这个问题。

!!! pitfall "以为 `imbue` 能改变已解析的格式"
    `basic_ios::imbue` 只影响之后的 I/O。同一流在格式化过程中切换 locale，前后片段会用不同规则。

## 思考题

<details markdown="1">
<summary>1. `std::locale a("C"), b = std::locale::classic();` 两者相等吗？`std::locale(a, new std::numpunct<char>)` 与 `a` 相等吗？</summary>

`a == b` 为真：两者都有名字 `"C"`，[locale.operators]/1 规定名字相同即相等。第二个为假：装入 facet 指针（非空）后得到的 locale 无名（[locale.cons]/12），无名 locale 只与自身及其副本相等（[locale.general]/8）——即便装入的 `numpunct<char>` 与原来的行为完全一样。
</details>

<details markdown="1">
<summary>2. 一个 `refs == 1` 构造、具有静态存储期的 facet，装进 locale 后再被 locale 销毁，会发生什么？</summary>

什么也不发生。[locale.facet]/3 规定 `refs == 1` 时实现永不销毁该 facet。反之，若对静态存储期的 facet 用默认的 `refs == 0`，最后一个 locale 销毁时会对它执行 `delete`，这是对非 `new` 得到的指针调用 `delete`，属于 {{ub}}（[[expr.delete]]）。
</details>

## 小结

- locale = 引用计数的、按 `Facet::id` 索引的不可变 facet 集合；拷贝便宜。
- `use_facet` 引用的有效期绑定于持有该 facet 的 locale；结果可缓存。
- 有名字的 locale 才能与 C locale 同步：`locale::global` 仅在实参有名字时调用 `setlocale`；反向（`setlocale` → C++ 全局 locale）永远不会发生。
- 自定义 facet：派生自标准 facet 以**替换**它；重新声明 `static locale::id id` 以**新增**一个 facet。
- 全局 locale 是否每线程一个由实现定义；主流实现都是进程级。
