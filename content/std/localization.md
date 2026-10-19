---
title: 本地化库：locale 与 facet
summary: std::locale 是一组按类型索引、引用计数、不可变的 facet；本页讲 facet 的身份与生命周期、locale 的构造与名字、locale::global 与 C locale 的联动，以及 isspace(c, loc) 等便利函数。
status: done
covers: localization.general, locale.syn, locales, locale, locale.general, locale.types, locale.category, locale.facet, locale.id, locale.cons, locale.members, locale.operators, locale.statics, locale.global.templates, locale.convenience, classification, conversions.character
related: text, locale.categories, c.locales, text.encoding, format.string.std, iostreams.base, res.on.data.races, bitmask.types
tags: 标准库, locale, facet, 本地化, iostream
updated: 2026-10-19
---

!!! tldr
    - 一个 `std::locale` 是一组 facet 的集合，每个 facet 负责一类本地化规则（小数点、字符分类、排序……），用 facet 的类型作键来查找。
    - locale 内部引用计数，拷贝很便宜；装进 locale 的 facet 不再改变，从 `use_facet` 得到的引用在持有它的 locale 存在期间一直有效。
    - 定制标准 facet 的做法是派生一个类，覆盖受保护的虚函数，再用 `locale(old, new my_facet)` 装进新 locale。
    - 由名字构造的 locale 有名字，装入自定义 facet 后的 locale 没有名字；`locale::global` 只在实参有名字时才同步调用 `setlocale`，反方向永远不同步。
    - 全局 locale 是否每线程一个由实现定义，libstdc++ 和 libc++ 都是整个进程一个。

## 一个 locale 是一组 facet [locale.general]

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

int main() {
    // refs 取默认值 0：最后一个持有它的 locale 销毁时由库 delete
    std::locale loc(std::locale::classic(), new swiss_punct);

    std::ostringstream os;
    os.imbue(loc);
    os << 1234567 << ' ' << std::boolalpha << true;
    assert(os.str() == "1'234'567 ja");

    assert(std::format(loc, "{:L}", 1234567) == "1'234'567");   // format 的 L 选项也用 numpunct
    assert(std::format(loc, "{}", 1234567) == "1234567");       // 不写 L 就与 locale 无关
    assert(loc.name() == "*");                                  // 装入自定义 facet 后没有名字
}
```

同一个数，在德国应写成 `1.234.567`，在瑞士写成 `1'234'567`；日期、货币、字符分类、字符串排序也各有规矩。C 库用一个进程全局的 `setlocale` 处理这些差异。C++ 把每一类规则封装成一个对象，叫做 **facet**，再把一组 facet 打包成一个 `std::locale`。每个流可以各自 imbue（装入）一个 locale，上面的 `os` 就用了自定义的千位分隔符。

¶1 `locale` 是一组按 facet 类型索引的多态 facet 集合。facet 因此有双重身份：它是一个类接口，比如 `numpunct<char>` 有成员 `decimal_point()`；它的类型又是在 locale 里查找它的键。

¶2 访问 facet 只有两个函数模板。¶4 `use_facet<Facet>(loc)` 返回 locale 中该 facet 的引用，不存在时抛 `bad_cast`；`has_facet<Facet>(loc)` 询问它是否存在。用户定义的 facet 也可以装进 locale，用法与标准 facet 相同。

¶5 注 1 列出两个不经过 `use_facet` 的便捷入口：locale 自身的 `operator()` 可以当作字符串比较谓词，以及 `isspace(c, loc)` 一类全局函数（见下文）。

在实现中，一个 `locale` 对象通常只是一个指针，指向一个引用计数的 facet 指针数组，数组按每个 facet 的 `id` 编号排列。拷贝 `locale` 只是增加引用计数。

## facet 的身份：`locale::facet` 与 `locale::id`

### 什么类是 facet [locale.facet]

!!! std
    A class is a *facet* if it is publicly derived from another facet, or if it is a class derived from `locale::facet` and contains a publicly accessible declaration as follows: `static ::std::locale::id id;`

¶1 [[g:facet]] 的定义有两种情形：公开派生自另一个 facet 的类；或者派生自 `locale::facet`、并且有一个公开的 `static locale::id id;` 的类。脚注强调这是完整的要求，facet 不需要公开的拷贝构造、赋值、默认构造或析构函数。实际上 `locale::facet` 禁止拷贝，标准 facet 的析构函数都是 `protected` 的，所以 facet 一般用 `new` 创建后交给 locale 管理。

¶2 locale 的函数模板中名为 `Facet` 的模板形参要求是 facet。传入不是 facet 的类型，或 `volatile` 限定的 facet，程序{{ill-formed}}；`const` 限定的 facet 可以。

### 派生 facet 与标准 facet 共用一个槽位

`id` 是在 locale 里查找 facet 的索引（[locale.id] ¶1）。上面的 `swiss_punct` 没有声明自己的 `id`，它继承来的 `id` 就是 `numpunct<char>::id`，因此两者占用同一个槽位。`locale(loc, new swiss_punct)` 替换的正是 `numpunct<char>`，`num_put` 和 `format` 通过 `use_facet<numpunct<char>>` 找到的就是它。这是定制标准 facet 的标准做法。

想增加一个全新的 facet，而不是替换已有的，就要在派生类里重新声明 `static std::locale::id id;`。

!!! lawyer "没有自己 id 的派生 facet 也能在 classic() 里找到"
    因为共用槽位，`has_facet<swiss_punct>(std::locale::classic())` 同样为真：它只查那个槽位里有没有东西。此时调用 `use_facet<swiss_punct>(classic())`，得到的 `swiss_punct&` 实际指向一个普通的 `numpunct<char>` 对象（libc++ 内部用的是 `static_cast`），再访问 `swiss_punct` 特有的成员就是 {{ub}}。另外，[locale.global.templates] ¶1 要求 `use_facet` 的 `Facet` 的定义里含有公开的静态成员 `id`，继承来的 `id` 是否算数，条文没有说清；Clang 23 + libc++ 接受这种用法。

¶2 [locale.id] 的注 1 解释了 `id` 的一个实现细节：iostream 可能在静态初始化期间就被使用，所以 `id` 的初始化不能依赖动态初始化。一种做法是在 facet 第一次装入 locale 时才给 `id` 分配编号，这只依赖静态存储在任何构造函数运行之前已被零初始化（[[basic.start.static]]）。

## facet 的生命周期

### `refs` 参数（[locale.facet] ¶3–¶4）

¶3 每个 facet 的构造函数都有一个 `refs` 参数，用来管理生命周期。`refs == 0` 时，最后一个包含这个 facet 的 locale 销毁时，实现执行 `delete static_cast<locale::facet*>(f)`；`refs == 1` 时，实现永远不销毁它，适合静态存储期或自己管理的 facet。

¶4 标准 facet 的构造函数都接受这个参数并转交给基类；所有单参数的构造函数都是 `explicit` 的。

### 引用何时有效（[locale.general] ¶6–¶7）

¶6 从 `use_facet` 得到的引用，只要还有某个 locale 对象引用该 facet，就一直可用，它的成员函数的结果也可以缓存。[locale.global.templates] ¶4 给出更直接的保证：返回的引用至少在 `loc` 的任何一个副本存在期间有效。

¶7 在同一个 locale 中的同一个 facet 上反复调用同一个成员函数，结果必须相同，也就是说 facet 是不可变的。这是可以缓存的依据，iostream 的实现通常在 imbue 时就把 `ctype` 和 `numpunct` 的指针存在流里。

!!! ub "从临时 locale 取得的 facet 引用"
    ```cpp
    const auto& np = std::use_facet<std::numpunct<char>>(std::locale("de_DE.UTF-8"));
    char c = np.decimal_point();   // 临时 locale 已销毁，可能已经没有 locale 引用这个 facet
    ```
    完整表达式结束时临时 locale 就销毁了。如果没有其他 locale 持有这个 facet，它已被删除，`np` 悬垂，调用它是 {{ub}}。实现对命名 locale 往往另有内部缓存，这段代码可能碰巧能运行，但标准不保证。先把 locale 存进一个具名变量。

## 类别 [locale.category]

`locale::category` 就是 `int`。¶1 它的合法取值是六个位掩码元素 `collate`、`ctype`、`monetary`、`numeric`、`time`、`messages`，每个代表一个类别；`none` 为 0，`all` 是所有类别的并集；两个类别按位或表示它们的并集。

¶2 接受 category 参数的成员函数据此选出一组 facet。每个类别至少包含表 91 列出的 facet（各有 `char` 和 `wchar_t` 版本）：

| 类别 | facet |
|---|---|
| `collate` | `collate` |
| `ctype` | `ctype`、`codecvt<char, char, mbstate_t>`、`codecvt<wchar_t, char, mbstate_t>` |
| `monetary` | `moneypunct`（含 `Intl = true` 版本）、`money_get`、`money_put` |
| `numeric` | `numpunct`、`num_get`、`num_put` |
| `time` | `time_get`、`time_put` |
| `messages` | `messages` |

`char16_t`、`char32_t` 的 `codecvt` 特化在附录 [[depr.locale.category]] 中，已弃用。

¶3 对任何构造出来的 locale 以及 `classic()`，表 91 中所有 facet 的 `has_facet` 都为真，标准 facet 总是齐全的。¶4 和表 92 还要求实现提供各个 `_byname` 版本，以及 `num_get`、`num_put`、`money_get` 等对任意迭代器类型的特化。

¶5 标准的 `num_get`、`num_put` 只对 `numpunct<charT>` 和 `ctype<charT>` 调用 `use_facet`，用的 locale 是 `ios_base&` 实参的 `getloc()`。所以替换了流上的 `numpunct`，`num_put` 就一定会用到它。各 facet 的具体规则见 [[locale.categories]]。

## 构造、名字与相等

### 有名字和没有名字的 locale（[locale.general] ¶8）

¶8 由名字字符串构造的 locale（如 `"POSIX"`），或者由两个有名字的 locale 的部分组合而成的 locale，有名字；其他 locale 都没有。有名字的 locale 按名字比较相等；没有名字的 locale 只与它自己及其副本相等，它的 `name()` 返回 `"*"`。

名字很重要，因为只有有名字的 locale 才能交给 C 的 `setlocale`，见下文的 `locale::global`。

### 构造函数 [locale.cons]

| 构造 | 结果 | 是否有名字 |
|---|---|---|
| `locale()`（¶1） | 当前全局 locale 的副本；从未调用过 `global` 时等同 `classic()` | 同全局 locale |
| `locale(const char* name)`（¶2–¶4） | 按 C locale 名字构造；名字无效或为空指针时抛 `runtime_error` | 有 |
| `locale(other, name, cats)`（¶6–¶9） | `other` 的副本，但 `cats` 指定的类别取自 `locale(name)` | 当且仅当 `other` 有 |
| `locale(other, Facet* f)`（¶11–¶12） | `other` 的副本，用 `f` 替换 `Facet` 的槽位；`f` 为空时就是 `other` | `f` 非空时没有 |
| `locale(other, one, cats)`（¶13–¶15） | `other` 的副本，但 `cats` 类别的 facet 取自 `one` | `cats == none` 时同 `other`；否则两者都有名字才有 |

¶4 合法的名字只有 `"C"`、`""` 和实现定义的其他值。`""` 表示用户环境的偏好，在 POSIX 上由 `LANG`、`LC_*` 环境变量决定。¶6、¶13 要求 `cats` 是合法的 category 值。

### 成员与运算符（[locale.members]、[locale.operators]）

- `combine<Facet>(other)`（¶1–¶4）：返回 `*this` 的副本，但 `Facet` 取自 `other`；`other` 没有这个 facet 时抛 `runtime_error`。结果没有名字。
- `name()`（¶5）：有名字时返回名字，否则返回 `"*"`。
- `encoding()`（¶6–¶7，{{c++26}}）：要求 `CHAR_BIT == 8`，返回表示该 locale 所关联编码的 [[text.encoding|`text_encoding`]]，具体由实现定义。libc++ 用 `name()` 查询，所以没有名字的 locale 得到的是空名字。
- `operator==`（[locale.operators] ¶1）：两者是同一个 locale、互为副本，或者都有名字且名字相同时为真。两个没有名字的 locale 即使 facet 完全相同也不相等。
- `operator()(s1, s2)`（¶2–¶5）：用 `collate<charT>` 比较两个 `basic_string`，返回 `compare(...) < 0`。因此 locale 本身就是一个比较谓词，可以写 `std::sort(v.begin(), v.end(), loc)`（例 1）。

## 全局 locale [locale.statics]

!!! std
    If the argument has a name, does `setlocale(LC_ALL, loc.name().c_str());` otherwise, the effect on the C locale, if any, is implementation-defined.

¶1 `locale::global(loc)` 设置全局 locale，之后 `locale()` 都返回它的副本。如果 `loc` 有名字，还会调用 `setlocale(LC_ALL, ...)`；没有名字时对 C locale 有什么影响由实现定义。¶2 它返回旧的全局 locale。

¶3 除了 `global` 之外，没有任何库函数会改变 `locale()` 的返回值。特别是，直接调用 C 的 `setlocale` 不会影响 C++ 的全局 locale。这种不对称常常造成难查的问题：

- `std::locale::global(std::locale(""))` 同时改变了 C 库（`printf`、`strtod` 等）的行为；
- `std::locale::global(std::locale(std::locale::classic(), new my_punct))` 传入的 locale 没有名字，本机 libc++ 不改变 C locale；
- `setlocale(LC_ALL, "C")` 只改 C locale，之后新建的 `std::locale()` 仍是原来的全局 locale。

已经存在的流不受 `global` 影响。`std::cout` 在构造时 imbue 了当时的全局 locale，之后要改需要显式调用 `std::cout.imbue(...)`。

¶4–¶6 `classic()` 返回 `"C"` locale，等价于 `locale("C")`；它、它的 facet 和这些 facet 的成员函数都不随时间改变。

### 每线程一个还是整个程序一个（[locale.general] ¶9）

!!! std
    Whether there is one global locale object for the entire program or one global locale object per thread is implementation-defined.

¶9 全局 locale 是整个程序一个还是每个线程一个，由实现定义（{{impl}}）。标准建议每线程一个；如果整个程序只有一个，实现不必避免它上面的数据竞争（[[res.on.data.races]]）。libstdc++ 和 libc++ 都是整个进程一个，所以多线程程序中调用 `locale::global` 需要自己同步，最好只在启动其他线程之前调用。

## 便利函数 [locale.convenience]

[classification] ¶1 `isspace(c, loc)` 到 `isblank(c, loc)` 共 12 个函数模板，每个返回 `use_facet<ctype<charT>>(loc).is(ctype_base::F, c)`。它们接受 `charT`，与 `<cctype>` 的 `std::isspace(int)` 不同，没有实参必须能用 `unsigned char` 表示的限制（见 [[text.c.strings]]）。脚注提示，在循环里应该先取出 `ctype` facet 直接使用，或用它的批量版本 `is(low, high, vec)`，因为每次调用便利函数都要做一次 `use_facet`。

[conversions.character] `toupper(c, loc)`、`tolower(c, loc)` 转发给 `ctype<charT>` 的同名成员。这是逐字符的映射，无法表达 `ß` 到 `SS` 这类一对多的大小写转换。

<details class="fine" markdown="1"><summary>其余条文</summary>

[localization.general] ¶1 列出本地化库覆盖的领域：字符分类与字符串排序，数值、货币、日期时间的格式化与解析，以及消息检索。¶2 和表 90 把它分成 [locales]（本页）、[[locale.categories]]、[[c.locales]] 三部分。

[locale.syn] 是 `<locale>` 的概要：`locale`、`use_facet`/`has_facet`、12 个分类函数和 2 个大小写转换函数，以及六个类别的全部 facet 模板及其 `_byname` 版本。

[locale.general] ¶3 的例 1 演示了如何借 `time_put` 实现一个日期类型的 `operator<<`。

[locale.category] ¶6 说明 facet 声明中名为 `InputIterator`、`OutputIterator`、`C`、`International` 的模板形参分别代表哪些类型的集合。

[locale.facet] ¶5 规定 `xxx_byname(name)` 的语义等价于 `locale(name)` 中的同名 facet，并接受 `const char*` 或 `string` 形式的名字；没有 `_byname` 版本的 facet（如 `num_get`）通过查询其他 facet 实现命名 locale 的语义。

[locale.cons] ¶5、¶10 是接受 `string` 的重载，等价于 `c_str()` 版本；¶16–¶17 是复制赋值。

[locale.global.templates] ¶1–¶3、¶5 是 `use_facet` 与 `has_facet` 的形式化规定，内容已在上文。

</details>

## 常见误解

!!! pitfall "以为用空字符串构造 locale 一定成功"
    `locale("")` 取决于运行环境的 `LANG`、`LC_*` 变量。如果它们指向系统没有安装的 locale，构造函数抛 `runtime_error`（[locale.cons] ¶3）。精简的容器镜像里常见这个问题。

!!! pitfall "以为 `imbue` 能影响已经输出的内容"
    `basic_ios::imbue` 只影响之后的输入输出。在一串输出中途切换 locale，前后两部分会用不同的规则。

## 思考题

!!! question "思考题 1"
    `std::locale a("C"), b = std::locale::classic();` 两者相等吗？`std::locale(a, new std::numpunct<char>)` 与 `a` 相等吗？

<details markdown="1">
<summary>答案</summary>

`a == b` 为真：两者都叫 `"C"`，[locale.operators] ¶1 规定名字相同即相等。

第二个为假：装入非空的 facet 指针后得到的 locale 没有名字（[locale.cons] ¶12），而没有名字的 locale 只与自身及其副本相等（[locale.general] ¶8），即使装入的 `numpunct<char>` 与原来的行为完全一样。
</details>

!!! question "思考题 2"
    一个以 `refs == 1` 构造、具有静态存储期的 facet，装进 locale 后 locale 被销毁，会发生什么？如果用默认的 `refs == 0` 呢？

<details markdown="1">
<summary>答案</summary>

`refs == 1` 时什么也不发生，[locale.facet] ¶3 规定实现永远不销毁它。

如果用默认的 `refs == 0`，最后一个 locale 销毁时实现会对它执行 `delete`。对不是 `new` 得到的指针调用 `delete` 是 {{ub}}（[[expr.delete]]）。
</details>

## 小结

- locale 是引用计数、按 `Facet::id` 索引的不可变 facet 集合，拷贝很便宜。
- `use_facet` 返回的引用在持有该 facet 的 locale 存在期间有效，结果可以缓存。
- 派生标准 facet 并沿用它的 `id`，就替换了它；重新声明 `static locale::id id`，才是新增一个 facet。
- 只有有名字的 locale 能与 C locale 同步：`locale::global` 仅在实参有名字时调用 `setlocale`，`setlocale` 永远不影响 `std::locale()`。
- 全局 locale 是否每线程一个由实现定义，主流实现都是整个进程一个。
