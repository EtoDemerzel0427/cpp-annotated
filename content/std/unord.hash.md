---
title: 类模板 hash
summary: std::hash 的每个特化要么“启用”要么“禁用”；禁用的特化存在但不可构造、不是函数对象，以便被 SFINAE 探测；启用的特化满足 Cpp17Hash，相等的键必须有相等的哈希且调用不抛异常；哈希值只在一次程序执行内稳定
status: done
covers: hash.requirements
papers: P0513R0, P0919R3
related: function.objects, unord.req, func.search, namespace.std, temp.expl.spec, basic.string.hash, meta.unary.prop
tags: 标准库, functional, hash, 无序容器, Cpp17Hash
updated: 2026-10-18
---

`std::hash<Key>` 是无序关联容器（`unordered_map`、`unordered_set` 等，[[unord.req]]）的默认哈希函数，也是 Boyer–Moore 搜索器（[[func.search]]）的默认 `Hash`。[unord.hash] 只有五段，却包含一个很有特点的设计：**“禁用的特化”**——它让“`T` 能不能被哈希”成为一个可以在编译期安全探测的问题。

本页同时讲解 [hash.requirements] 中的 *Cpp17Hash* 要求，因为 [unord.hash] 的核心规定都是以它表述的。

## *Cpp17Hash* 要求（[hash.requirements]）

!!! std
    A type H meets the *Cpp17Hash* requirements if it is a function object type, it meets the *Cpp17CopyConstructible* and *Cpp17Destructible* requirements, and the expressions shown in Table 37 are valid and have the indicated semantics.

¶1：类型 `H` 满足 *Cpp17Hash*，当且仅当它是**函数对象类型**（[[function.objects]]）、可复制构造、可析构，并且下表的表达式合法且语义正确。¶2 给出记号：`h` 是（可能 const 的）`H` 值，`u` 是 `Key` 左值，`k` 是可转换为（可能 const 的）`Key` 的值。

| 表达式 | 返回类型 | 要求 |
|---|---|---|
| `h(k)` | `size_t` | 返回值**只依赖于实参 `k`**，且只在**程序的本次执行期间**如此；不同值 `t1`、`t2` 的哈希相等的概率**应当**很小，趋近 `1.0 / numeric_limits<size_t>::max()` |
| `h(u)` | `size_t` | 不得修改 `u` |

三个细节：

1. **“for the duration of the program”**——注 1 说得更直白：同一次执行中，对同一个值 `k` 求 `h(k)` 结果相同。反过来，**不同次执行之间没有任何保证**：实现可以在启动时随机化哈希种子（抵御哈希洪泛攻击），也可以在不同版本间更换算法。把 `std::hash` 的结果写进文件、通过网络发送、或者作为持久化存储的键，都是在依赖标准不保证的东西。
2. **碰撞概率用的是 *should***，是建议而非可检验的要求。libc++ 对不超过 `size_t` 宽度的整数直接返回 `static_cast<size_t>(v)`（恒等哈希），完全符合要求——不同的整数根本不会碰撞——但对“低位相同的键”很不友好，这是质量问题而不是合规问题。
3. 要求的是 `h` **可能是 const**：`operator()` 必须能在 const 对象上调用。

## 启用与禁用（¶2–¶4）

!!! std
    Each specialization of hash is either enabled or disabled, as described below.

¶2 先列出**一定启用**的特化：每个声明了 `hash` 模板的头文件，都为 `nullptr_t` 以及所有 **cv 不限定**的算术类型、枚举类型、指针类型提供启用的特化。然后是兜底规则：对于库和用户都没有提供显式或部分特化的 `Key`，`hash<Key>` 是**禁用的**（[[g:disabled-hash-specialization]]）。

¶3：库提供的特化，除非另有说明都是启用的，且成员函数除非另有说明都是 `noexcept`。“另有说明”的典型是**条件启用**：`hash<optional<T>>` 当且仅当 `hash<remove_const_t<T>>` 启用时才启用，`hash<variant<Ts...>>`、`hash<unique_ptr<T, D>>` 等类似。

¶4 规定禁用的特化长什么样：

!!! std
    If H is a disabled specialization of hash, these values are false: is_default_constructible_v&lt;H&gt;, is_copy_constructible_v&lt;H&gt;, is_move_constructible_v&lt;H&gt;, is_copy_assignable_v&lt;H&gt;, and is_move_assignable_v&lt;H&gt;.

并且禁用的特化**不是函数对象类型**。注 2 总结：**这个特化存在，但任何把它当作 *Cpp17Hash* 使用的尝试都是非良构的。**

### 为什么不直接“不定义”主模板？

C++11 中主模板 `hash<T>` 只声明不定义，对不支持的类型，`hash<T>` 是**不完整类型**。这带来两个问题：

- 不完整类型不能安全地用 type trait 探测——对不完整类型使用 `is_default_constructible` 等是 {{ub}}（[[meta.unary.prop]] 的前置条件），而且结果会被第一次实例化“冻结”。
- 库自身需要条件启用：`hash<optional<T>>` 应当在 `hash<T>` 不可用时也“不可用”。若“不可用”意味着不完整类型，`hash<optional<T>>` 就得做成部分特化与否的复杂组合。

C++17 的 [[P0513R0]]（“Poisoning the hash”）改为：**主模板是完整的类型，但被“毒化”**——不能构造、不能复制、不能调用。于是 `is_default_constructible_v<hash<T>>` 就成了一个可靠的“能否哈希”检测，容器可以据此给出清晰的诊断。

!!! impl "libc++ 的毒化实现"
    `__functional/hash.h` 中，`template <class _Tp> struct hash : public __hash_impl<_Tp> {};`。`__hash_impl` 的主模板把默认构造、复制构造、复制赋值全部 `= delete`（移动操作因此不会被隐式声明），且没有 `operator()`；针对 cv 不限定的枚举、整型、浮点类型的部分特化才提供真正的实现。注意条件里用的是 `__is_unqualified_v<_Tp>`——这正是 ¶2 中“cv-unqualified”的直接体现。

```cpp run title="enabled_disabled.cpp" ok
#include <functional>
#include <string>
#include <type_traits>
#include <unordered_set>
#include <utility>
#include <cstdio>
struct Opaque { int v; };
enum class Color { red, green };
// 禁用的特化：类型存在，但不能构造、不能调用
static_assert(!std::is_default_constructible_v<std::hash<Opaque>>);
static_assert(!std::is_copy_constructible_v<std::hash<Opaque>>);
static_assert(!std::is_invocable_v<std::hash<Opaque>, Opaque>);
static_assert(!std::is_default_constructible_v<std::hash<std::pair<int, int>>>);  // 标准没给 pair 提供
static_assert(!std::is_default_constructible_v<std::hash<const int>>);           // 只给 cv 不限定的类型
// 启用的特化
static_assert(std::is_default_constructible_v<std::hash<Color>>);
static_assert(std::is_nothrow_invocable_v<std::hash<int*>, int*>);
static_assert(std::is_default_constructible_v<std::hash<std::nullptr_t>>);

struct Point { int x, y; bool operator==(const Point&) const = default; };
template<> struct std::hash<Point> {          // 为程序定义类型特化（须在首次使用之前）
  std::size_t operator()(const Point& p) const noexcept {
    std::size_t h = std::hash<int>{}(p.x);
    return h ^ (std::hash<int>{}(p.y) + 0x9e3779b97f4a7c15 + (h << 6) + (h >> 2));
  }
};
int main() {
  std::unordered_set<Point> s{{1, 2}, {3, 4}, {1, 2}};
  std::printf("%zu\n", s.size());                                              // 2
  std::printf("%d\n", std::hash<double>{}(0.0) == std::hash<double>{}(-0.0)); // 1：0.0 == -0.0
}
```

```cpp run title="disabled_use.cpp" error
#include <unordered_set>
struct Point { int x, y; bool operator==(const Point&) const = default; };
std::unordered_set<Point> s;   // error：hash<Point> 是禁用的特化，不可默认构造、不可调用
int main() {}
```

!!! lawyer "`hash<const int>` 是禁用的"
    ¶2 只承诺 **cv 不限定**的算术、枚举、指针类型。`std::hash<const int>` 没有任何库特化，按兜底规则是**禁用**的。平时不会撞上它，因为容器用的是 `hash<Key>` 而 `Key` 通常不带 const；但在泛型代码里写 `std::hash<T>` 而 `T` 可能推导为 `const U` 时，就需要先 `remove_const_t`——标准库自己的 `hash<optional<T>>` 正是这样写的（依赖 `hash<remove_const_t<T>>`）。

## 启用的特化必须做到什么（¶5）

一个启用的特化 `hash<Key>`：

- ¶5.1 满足 *Cpp17Hash*（以 `Key` 为实参类型），并且满足 *Cpp17DefaultConstructible*、*Cpp17CopyAssignable*、*Cpp17Swappable*——比 *Cpp17Hash* 本身要求得多，因为容器需要默认构造并交换哈希器；
- ¶5.2 **若 `k1 == k2` 为 true，则 `h(k1) == h(k2)` 也为 true**——哈希与 `operator==` 一致；
- ¶5.3 `h(k)` 不抛异常，**除非** `hash<Key>` 是程序定义的特化。

¶5.2 的一个推论：`0.0 == -0.0`，所以 `hash<double>` 必须对二者给出相同的值——尽管它们的位模式不同。libc++ 为此专门写了 `if (__v == 0.0f) return 0;`。而 NaN 与任何值都不相等，¶5.2 对它没有约束（但把 NaN 作为键放进无序容器本身就是在找麻烦：它永远找不回来）。

¶5.3 意味着：用户特化可以抛异常，但标准库的启用特化（包括 `hash<std::string>`）都不抛。

## 为自己的类型提供哈希

两种方式：

1. **特化 `std::hash`**：[[namespace.std]] 允许对 `std` 中的类模板为**程序定义类型**添加特化，前提是特化满足原模板的要求——即上面 ¶5 的全部。特化的声明必须在每一个会引起隐式实例化的使用之前可达，否则是 IFNDR（[[temp.expl.spec#7]]）——实际上 Clang 会直接报“explicit specialization of 'std::hash&lt;Point&gt;' after instantiation”。
2. **写一个独立的哈希函数对象**，作为容器的模板实参传入：`std::unordered_set<Point, PointHash>`。这种方式不碰 `std`，也不受“首次使用前声明”的约束。

不论哪种，都要保证与容器所用的相等谓词一致（¶5.2 的精神），否则容器会出现“插得进、找不到”的现象。

## 异构查找与透明哈希

C++20 起，无序容器支持用与 `Key` 不同的类型查找（[[P0919R3]] 等），条件是哈希与相等谓词**都**有 `is_transparent` 成员（[[function.objects]]）。`std::hash<std::string>` **不是**透明的，需要自己包一层。由于 [[basic.string.hash]] 保证 `hash<string>()(s) == hash<string_view>()(string_view(s))`，用 `hash<string_view>` 实现透明哈希是安全的：

```cpp run title="transparent_hash.cpp" ok
#include <functional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <cstdio>
struct sv_hash {
  using is_transparent = void;          // 哈希与相等谓词都要透明
  std::size_t operator()(std::string_view s) const noexcept { return std::hash<std::string_view>{}(s); }
};
int main() {
  std::unordered_map<std::string, int, sv_hash, std::equal_to<>> m{{"one", 1}};
  std::string_view k = "one";
  std::printf("%d\n", m.find(k)->second);    // 不构造临时 std::string
  std::printf("%d\n", std::hash<std::string>{}("abc") == std::hash<std::string_view>{}("abc"));  // 1
}
```

!!! pitfall "`hash<const char*>` 哈希的是地址"
    `const char*` 是指针类型，`std::hash<const char*>` 是 ¶2 中的指针特化：它哈希**指针值本身**，与所指字符串的内容无关。`std::unordered_set<const char*>` 里两个内容相同、地址不同的字符串会被当成不同的键。

## 哪些类型有启用的特化

除了 ¶2 的基础类型，标准库在各自的头文件里为许多类型提供了特化，常见的有：`basic_string`（各字符类型、默认 traits 与任意分配器）、`basic_string_view`、`unique_ptr`、`shared_ptr`、`optional`（条件启用）、`variant`（条件启用）、`monostate`、`bitset`、`vector<bool>`、`error_code`、`error_condition`、`type_index`、`thread::id`、`coroutine_handle`、`filesystem::path`、`chrono` 的多种时间类型（C++26）等。**没有**特化的常见类型包括 `pair`、`tuple`、`array`、`vector<T>`（`bool` 以外）以及各种容器——标准没有规定组合哈希的方式，需要自己写。

## 思考题

!!! question "思考题 1"
    下面的写法能否用来“探测 `T` 是否可哈希”？`template<class T> concept hashable = requires(T t) { std::hash<T>{}(t); };`

<details markdown="1">
<summary>展开查看答案与解析</summary>

可以。对禁用的特化，`std::hash<T>{}` 本身就非良构（默认构造函数被弃置），`requires` 表达式为 false；对启用的特化为 true。这正是 [[P0513R0]] 之后才变得安全的写法：在 C++11 的“不完整主模板”方案下，`std::hash<T>{}` 对不完整类型同样非良构，但像 `is_default_constructible_v<std::hash<T>>` 这类 trait 对不完整类型有前置条件，“毒化”方案才让二者都可靠。另外注意 `T` 可能是 `const U`——`hashable<const int>` 为 false。
</details>

!!! question "思考题 2"
    某程序把 `std::hash<std::string>{}(username)` 的结果作为分片号写入数据库，升级标准库后数据“错位”了。这是标准库的 bug 吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

不是。[hash.requirements] 只要求返回值在“程序的本次执行期间”只依赖于实参，不同次执行、不同版本、不同实现之间都可以不同。需要稳定哈希的场合必须使用明确规定算法的哈希函数（如 FNV、xxHash 的固定版本），而不是 `std::hash`。
</details>

## 小结

!!! summary
    | 要点 | 内容 |
    |---|---|
    | *Cpp17Hash* | 函数对象类型、可复制、可析构；`h(k)` 返回 `size_t`，只依赖 `k`，仅在本次执行内稳定；碰撞率“应当”很低 |
    | 一定启用 | `nullptr_t`、cv 不限定的算术/枚举/指针类型 |
    | 禁用的特化 | 无库/用户特化时；不可默认构造/复制/移动/赋值，不是函数对象类型；可被 SFINAE 探测 |
    | 启用的特化 | 还须可默认构造、可复制赋值、可交换；`k1 == k2` ⇒ `h(k1) == h(k2)`；库特化不抛异常 |
    | 用户特化 | 仅限程序定义类型；须在首次使用前可达 |
    | 陷阱 | `hash<const T>` 禁用；`hash<const char*>` 哈希地址；跨执行不稳定 |
