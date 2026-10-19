---
title: 类模板 hash
summary: std::hash 的每个特化要么启用、要么禁用：禁用的特化存在但不能构造和调用，因此可以在编译期探测；启用的特化要与 == 一致、不抛异常，哈希值只在一次程序执行内稳定。
status: done
covers: hash.requirements
papers: P0513R0, P0919R3
related: function.objects, unord.req, func.search, namespace.std, temp.expl.spec, basic.string.hash, meta.unary.prop
tags: 标准库, functional, hash, 无序容器, Cpp17Hash
updated: 2026-10-19
---

!!! tldr
    - `std::hash<Key>` 是无序容器的默认哈希函数。标准保证 `nullptr_t` 以及所有 cv 不限定的算术、枚举、指针类型都有可用的特化。
    - 没有特化的类型（包括 `pair`、`tuple` 和你自己的类）对应的是禁用的特化：它存在，但不能构造、不能调用，所以 `is_default_constructible_v<hash<T>>` 可以用来判断 `T` 能否哈希。
    - 启用的特化必须满足：`k1 == k2` 时 `h(k1) == h(k2)`，并且标准库提供的特化不抛异常。
    - 哈希值只在本次程序执行中稳定，不能写进文件或在进程之间传递。
    - `hash<const int>` 是禁用的，`hash<const char*>` 哈希的是指针而不是字符串内容。

## 从一个编译错误说起

```cpp run title="disabled_use.cpp" error
#include <unordered_set>
struct Point { int x, y; bool operator==(const Point&) const = default; };
std::unordered_set<Point> s;   // error: hash<Point> 是禁用的特化，不能默认构造
int main() {}
```

[unord.hash] 第 1 段规定，无序关联容器（`unordered_map`、`unordered_set` 等，[[unord.req]]）默认用 `std::hash<Key>` 作哈希函数。标准库没有为 `Point` 提供特化，所以上面的容器无法使用默认的哈希。本机 libc++ 报告 "call to implicitly-deleted default constructor of 'hasher'"。

要弄清这条错误从何而来，先看标准对哈希函数的一般要求，再看 `std::hash` 的启用与禁用。

## Cpp17Hash 要求（[hash.requirements]）

[hash.requirements] 第 1 段规定，类型 `H` 满足 *Cpp17Hash* 要求，当且仅当它是函数对象类型（[[function.objects]]），满足可复制构造和可析构的要求，并且下表的表达式合法、语义正确。第 2 段约定了记号：`h` 是（可能为 const 的）`H` 值，`u` 是 `Key` 类型的左值，`k` 是可以转换为（可能为 const 的）`Key` 的值。

| 表达式 | 返回类型 | 要求 |
|---|---|---|
| `h(k)` | `size_t` | 在程序运行期间，返回值只依赖于实参 `k`；两个不同值的哈希相等的概率应当很小，接近 `1.0 / numeric_limits<size_t>::max()` |
| `h(u)` | `size_t` | 不得修改 `u` |

这张表有三处值得注意：

1. 稳定性只限于程序运行期间。注 1 说得更直白：同一次执行中，对同一个值求 `h(k)` 结果相同。不同次执行之间没有任何保证，实现可以在启动时随机化种子以抵御哈希洪泛攻击，也可以在版本之间更换算法。把 `std::hash` 的结果写进文件、通过网络发送或者用作持久化的键，都是在依赖标准不保证的东西。
2. 碰撞概率用的是 should，只是建议。libc++ 对不超过 `size_t` 宽度的整数直接返回原值，这完全合规，不同整数根本不会碰撞，但对低位相同的一组键分布很差。这是质量问题，不是符合性问题。
3. `h` 可能是 const，所以 `operator()` 必须能在 const 对象上调用。

## 启用的特化与禁用的特化（¶2–¶4）

¶2 每个 `hash` 特化要么是**启用的**（enabled），要么是**禁用的**（disabled）。注 1 说明，启用的特化满足 *Cpp17Hash*，禁用的不满足。

每个声明了 `hash` 模板的头文件，都为 `nullptr_t` 以及所有 cv 不限定的算术类型、枚举类型和指针类型提供启用的特化。对其余的类型 `Key`，如果标准库和用户都没有提供显式特化或部分特化，`hash<Key>` 就是禁用的（[[g:disabled-hash-specialization]]）。

¶3 标准库提供的特化，除非另有说明都是启用的，成员函数除非另有说明都是 `noexcept`。另有说明的典型是有条件启用：`hash<optional<T>>` 当且仅当 `hash<remove_const_t<T>>` 启用时才启用，`hash<variant<Ts...>>`、`hash<unique_ptr<T, D>>` 与此类似。

¶4 规定了禁用的特化是什么样子：

!!! std
    If H is a disabled specialization of hash, these values are false: is_default_constructible_v&lt;H&gt;, is_copy_constructible_v&lt;H&gt;, is_move_constructible_v&lt;H&gt;, is_copy_assignable_v&lt;H&gt;, and is_move_assignable_v&lt;H&gt;.

此外，禁用的特化不是函数对象类型。注 2 总结说：这个特化存在，但任何把它当作 *Cpp17Hash* 使用的尝试都是非良构的。

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
static_assert(!std::is_default_constructible_v<std::hash<std::pair<int, int>>>);  // 标准没给 pair
static_assert(!std::is_default_constructible_v<std::hash<const int>>);           // 只给 cv 不限定的类型
// 启用的特化
static_assert(std::is_default_constructible_v<std::hash<Color>>);
static_assert(std::is_nothrow_invocable_v<std::hash<int*>, int*>);
static_assert(std::is_default_constructible_v<std::hash<std::nullptr_t>>);

struct Point { int x, y; bool operator==(const Point&) const = default; };
template<> struct std::hash<Point> {          // 为程序定义的类型特化，须在首次使用之前
  std::size_t operator()(const Point& p) const noexcept {
    std::size_t h = std::hash<int>{}(p.x);
    return h ^ (std::hash<int>{}(p.y) + 0x9e3779b97f4a7c15 + (h << 6) + (h >> 2));
  }
};

int main() {
  std::unordered_set<Point> s{{1, 2}, {3, 4}, {1, 2}};
  std::printf("%zu\n", s.size());                                               // 2
  std::printf("%d\n", std::hash<double>{}(0.0) == std::hash<double>{}(-0.0));  // 1
}
```

### 为什么要有禁用的特化

C++11 中主模板 `hash<T>` 只声明、不定义，不支持的类型对应的是不完整类型。这有两个问题：

- 对不完整类型使用 `is_default_constructible` 之类的 trait 是 {{ub}}（[[meta.unary.prop]] 的前条件），而且结果会在第一次实例化时固定下来，无法可靠地探测。
- 标准库自己需要有条件地启用特化：`hash<T>` 不可用时，`hash<optional<T>>` 也应该不可用。如果不可用意味着不完整类型，`hash<optional<T>>` 就只能写成一组复杂的部分特化。

C++17 的 [[P0513R0]] 改用禁用的特化：类型是完整的，但不能构造、复制和调用。这样 `is_default_constructible_v<hash<T>>` 就成了判断能否哈希的可靠手段，容器也能据此给出清楚的诊断。

!!! impl "libc++ 的做法"
    libc++ 的 `hash<T>` 继承自 `__hash_impl<T>`。`__hash_impl` 的主模板把默认构造、复制构造和复制赋值都声明为 `= delete`，因此不会隐式声明移动操作，也没有 `operator()`。只有针对 cv 不限定的枚举、整型和浮点类型的部分特化才提供真正的实现，条件里写的 `__is_unqualified_v<_Tp>` 对应的正是 ¶2 中的 cv 不限定。

!!! lawyer "`hash<const int>` 是禁用的"
    ¶2 只保证 cv 不限定的类型。`std::hash<const int>` 没有任何库特化，按兜底规则是禁用的。容器用的是 `hash<Key>`，而 `Key` 通常不带 const，所以平时碰不到。泛型代码里写 `std::hash<T>` 而 `T` 可能推导为 `const U` 时，要先 `remove_const_t`。标准库的 `hash<optional<T>>` 就依赖 `hash<remove_const_t<T>>`。

## 启用的特化必须做到什么（¶5）

一个启用的特化 `hash<Key>`：

- ¶5.1 以 `Key` 为实参类型满足 *Cpp17Hash*，还要满足 *Cpp17DefaultConstructible*、*Cpp17CopyAssignable* 和 *Cpp17Swappable*。这比 *Cpp17Hash* 本身要求得多，因为容器需要默认构造和交换哈希函数对象。
- ¶5.2 如果 `k1 == k2` 为 true，那么 `h(k1) == h(k2)` 也为 true，即哈希与 `operator==` 一致。
- ¶5.3 `h(k)` 不抛异常，除非 `hash<Key>` 是程序定义的特化。所以标准库的启用特化，包括 `hash<std::string>`，都不抛异常；用户自己的特化可以抛。

¶5.2 的一个推论：`0.0 == -0.0`，所以 `hash<double>` 必须给这两个值相同的结果，尽管它们的位模式不同。libc++ 为此专门写了 `if (__v == 0.0f) return 0;`。NaN 与任何值都不相等，¶5.2 对它没有约束；把 NaN 作为键放进无序容器，之后也找不回来。

## 为自己的类型提供哈希

有两种方式：

1. 特化 `std::hash`。[[namespace.std]] 允许为程序定义的类型添加 `std` 中类模板的特化，前提是特化满足原模板的要求，也就是上面 ¶5 的全部。特化必须在每一个会引起隐式实例化的使用之前声明，否则程序是非良构的，不要求诊断（[[temp.expl.spec#7]]）。实际上 Clang 会直接报 "explicit specialization of 'std::hash&lt;Point&gt;' after instantiation"。
2. 写一个独立的哈希函数对象，作为容器的模板实参：`std::unordered_set<Point, PointHash>`。这种方式不碰 `std`，也没有必须先声明的限制。

无论哪种，都要与容器使用的相等谓词一致，否则容器会出现插得进、找不到的现象。

## 异构查找与透明哈希

C++20 起，无序容器可以用与 `Key` 不同的类型查找（[[P0919R3]] 等），条件是哈希和相等谓词都声明了 `is_transparent` 成员类型（[[function.objects]]）。`std::hash<std::string>` 不是透明的，需要自己包一层。[[basic.string.hash]] 保证 `hash<string>` 和 `hash<string_view>` 对相同内容给出相同的值，所以用 `hash<string_view>` 实现透明哈希是安全的：

```cpp run title="transparent_hash.cpp" ok
#include <functional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <cstdio>

struct sv_hash {
  using is_transparent = void;          // 哈希和相等谓词都要透明
  std::size_t operator()(std::string_view s) const noexcept {
    return std::hash<std::string_view>{}(s);
  }
};

int main() {
  std::unordered_map<std::string, int, sv_hash, std::equal_to<>> m{{"one", 1}};
  std::string_view k = "one";
  std::printf("%d\n", m.find(k)->second);    // 不构造临时 std::string
  std::printf("%d\n", std::hash<std::string>{}("abc") == std::hash<std::string_view>{}("abc"));  // 1
}
```

!!! pitfall "`hash<const char*>` 哈希的是地址"
    `const char*` 是指针类型，`std::hash<const char*>` 是 ¶2 中的指针特化，哈希的是指针值本身，与所指字符串的内容无关。在 `std::unordered_set<const char*>` 里，两个内容相同、地址不同的字符串是两个不同的键。

## 哪些类型有启用的特化

除了 ¶2 的基本类型，标准库在各自的头文件里为许多类型提供了特化，常见的有 `basic_string`、`basic_string_view`、`unique_ptr`、`shared_ptr`、`optional`（有条件启用）、`variant`（有条件启用）、`monostate`、`bitset`、`vector<bool>`、`error_code`、`error_condition`、`type_index`、`thread::id`、`coroutine_handle`、`filesystem::path`，以及 C++26 起的多种 `chrono` 时间类型。

`pair`、`tuple`、`array`、`vector<T>`（`bool` 以外）和其他容器都没有特化。标准没有规定组合多个哈希值的方式，需要自己写。

`hash` 类模板本身在 `<functional>` 中标为 freestanding。

## 思考题

!!! question "思考题 1"
    下面的概念能否用来判断 `T` 是否可哈希？
    `template<class T> concept hashable = requires(T t) { std::hash<T>{}(t); };`

<details markdown="1">
<summary>答案</summary>

可以。对禁用的特化，`std::hash<T>{}` 本身就非良构（默认构造函数被删除），`requires` 表达式为 false；对启用的特化为 true。注意 `T` 可能是 `const U`：`hashable<const int>` 为 false，因为 `hash<const int>` 是禁用的。
</details>

!!! question "思考题 2"
    某程序把 `std::hash<std::string>{}(username)` 的结果作为分片号写进数据库，升级标准库之后数据错位了。这是标准库的缺陷吗？

<details markdown="1">
<summary>答案</summary>

不是。[hash.requirements] 只要求返回值在程序运行期间只依赖于实参，不同次执行、不同版本、不同实现之间都可以不同。需要稳定哈希时，应该用算法有明确规定的哈希函数（例如固定版本的 FNV 或 xxHash），而不是 `std::hash`。
</details>
