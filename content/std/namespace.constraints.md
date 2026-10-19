---
title: 命名空间的使用：std 里能放什么
summary: 往 namespace std 里添加声明是 UB，例外是依赖程序定义类型的类模板特化（hash、tuple_size、formatter…）和少数明确允许的变量模板特化；函数模板、成员函数不能特化，也不能写推导指引；除可寻址函数外，取标准库函数的地址是未指明的；posix 和 std 加数字的命名空间也被保留。
status: done
covers: *
papers: P0551R3, P2996R13
related: constraints, reserved.names, conforming, utility.requirements, global.functions, member.functions, temp.expl.spec, temp.explicit, namespace.def
tags: 库, namespace std, 特化, UB, 可寻址函数
updated: 2026-10-19
---

!!! tldr
    - 往 `std` 或它的任何嵌套命名空间里添加声明或定义是未定义行为，除非标准另有说明。
    - 主要的例外：可以为标准类模板（`std::hash`、`std::formatter`、`std::tuple_size`…）写特化，前提是特化依赖你自己定义的类型，并且满足原模板的要求。
    - 不能特化标准库的函数模板（C++20 起，包括 `std::swap`）、成员函数和大多数变量模板，也不能为标准类模板写推导指引。定制 `swap` 要在自己的命名空间里写重载。
    - 除了少数可寻址函数（`std::endl`、`std::hex` 等），对标准库函数取地址的行为是未指明的，可能编译不过。需要函数对象时用 lambda 包一层。
    - `posix`、`std2`、`std26` 这类命名空间也保留给标准使用。

## 总原则：不要往 std 里加东西（[namespace.std] ¶1）

```cpp ub
#include <ostream>
#include <vector>
namespace std {
  // UB：在 std 里给 std::vector 添加 operator<<
  template<class T>
  ostream& operator<<(ostream& os, const vector<T>& v) {
    for (const auto& x : v) os << x << ' ';
    return os;
  }
}
int main() {}
```

!!! std
    Unless otherwise specified, the behavior of a C++ program is undefined if it adds declarations or definitions to namespace `std` or to a namespace within namespace `std`.

¶1 除非另有说明，程序向命名空间 `std` 或 `std` 内的命名空间添加声明或定义，行为未定义。`std::ranges`、`std::chrono`、`std::pmr`、`std::meta` 这些嵌套命名空间同样适用。

规则这么严，是为了让标准库的实现可以自由演化。实现可以给函数加重载（[[global.functions]]、[[member.functions]]），把函数换成函数对象，把整个库放进内联命名空间 `std::__1`。用户一旦往 `std` 里加声明，就和这些实现细节绑在了一起：可能与内部的同名实体冲突，可能在升级后悄悄改变重载决议的结果，两个库各加一份还会违反 ODR。

这里定为 UB 而不是非良构，是因为编译器分不清哪些声明来自标准库头文件，哪些是用户写的，两者都是普通的 C++ 代码。

上例的动机通常是让 ADL 找到运算符。`std::vector<int>` 的关联命名空间只有 `std`，所以定义在全局的 `operator<<` 在 `std::ostream_iterator` 这类模板内部找不到。正确的做法是写一个具名函数、包一层自己的类型，或者用 C++23 的 `std::print` / `std::format`，它们直接支持范围。

## 允许：为自己的类型特化类模板（¶2）

¶2 除非明确禁止，程序可以为任何标准库类模板向 `std` 添加特化，条件是：

- ¶2.1 这个声明依赖至少一个程序定义的类型；
- ¶2.2 这个特化满足原模板的标准库要求。

脚注 140 说明了这对实现的意义：库里实例化其他库模板的代码，必须能与任何满足最低要求的用户特化正常配合。

### 什么是程序定义的类型

**程序定义的类型**（[[g:program-defined-type]]）是不属于标准库、也不由实现定义的类类型或枚举类型，此外还包括程序中 lambda 的闭包类型，以及程序定义的特化的实例化。依赖并不要求最外层是用户类型，模板实参里出现就够了：

| 特化 | 依赖的程序定义类型 | 允许吗 |
|---|---|---|
| `std::hash<app::Id>` | `app::Id` | 允许 |
| `std::hash<app::Box<T>>`（偏特化） | `app::Box<T>` | 允许 |
| `std::hash<std::vector<app::Id>>` | `app::Id` | 允许 |
| `std::hash<std::pair<int, int>>` | 无 | UB |

¶2.2 同样有约束力。比如 `std::hash` 的特化必须满足 *Cpp17Hash*（[[hash.requirements]]）和 [[unord.hash]] 的要求：可默认构造、可拷贝、`operator()` 返回 `size_t` 等。

### 常见的定制点

```cpp run ok
#include <cstddef>
#include <format>
#include <functional>
#include <tuple>
#include <unordered_set>
#include <utility>

namespace app {
  struct Id {
    int v;
    bool operator==(const Id&) const = default;
  };
  struct Pair {
    int a; double b;
    template<std::size_t I> auto get() const {
      if constexpr (I == 0) return a; else return b;
    }
  };
}

template<> struct std::hash<app::Id> {
  std::size_t operator()(app::Id i) const noexcept {
    return std::hash<int>{}(i.v);
  }
};
// 结构化绑定的元组协议
template<> struct std::tuple_size<app::Pair>
  : std::integral_constant<std::size_t, 2> {};
template<> struct std::tuple_element<0, app::Pair> { using type = int; };
template<> struct std::tuple_element<1, app::Pair> { using type = double; };
// std::format 的定制
template<> struct std::formatter<app::Id> : std::formatter<int> {
  auto format(app::Id i, std::format_context& ctx) const {
    return std::formatter<int>::format(i.v, ctx);
  }
};

int main() {
  std::unordered_set<app::Id> s{{1}, {2}};
  auto [a, b] = app::Pair{1, 2.5};
  return s.size() == 2 && a == 1 && b == 2.5
      && std::format("{}", app::Id{42}) == "42" ? 0 : 1;
}
```

`template<> struct std::hash<app::Id>` 这种写法用限定名直接声明特化（[[temp.expl.spec]]），不必打开 `namespace std { }`，也就不会顺手在里面加入别的东西。

设计上就供用户特化的类模板还有 `std::coroutine_traits`、`std::common_type`、`std::basic_common_reference`、`std::iterator_traits`、`std::numeric_limits`、`std::uses_allocator`、`std::is_error_code_enum`、`std::is_error_condition_enum`、`std::pointer_traits` 等。

### 明确禁止特化的类模板

¶2 开头的"除非明确禁止"并不是空话，不少类模板的条款明确禁止用户特化：

| 模板 | 出处 | 后果 |
|---|---|---|
| [[type.traits]] 中的类型萃取（`is_integral`、`remove_cv`…） | [[meta.rqmts#4]] | UB，除非另有说明 |
| `std::initializer_list` | [[support.initlist#2]] | 非良构 |
| `std::allocator_traits` | [[allocator.requirements.general#3]] 注 1 | 不存在用户特化 |
| `range_adaptor_closure`、`generator`、`is_execution_policy`、`basic_format_arg`、`chrono::is_clock` | 各自的条款 | UB |

禁止特化类型萃取的理由很直接。`is_trivially_copyable` 这类萃取对应的是语言规则，用户不可能自行声明；如果 `is_integral<MyInt>` 能被特化成 `true`，库里依赖它的代码就会对 `MyInt` 做只对整数合法的操作。

libc++ 已经开始诊断这类 UB：它给类型萃取加上了 `[[clang::no_specializations]]` 属性。标准说的是 UB，实现拒绝编译也在允许范围内。

```cpp error
#include <type_traits>
struct S {};
template<> struct std::is_integral<S> : std::true_type {};
// 本机 Clang + libc++：error: 'is_integral' cannot be specialized:
//   Users are not allowed to specialize this standard library entity
int main() {}
```

## 变量模板：只有明确允许的才能特化（¶3）

¶3 程序声明任何标准库变量模板的显式特化或偏特化，行为未定义，除非这个变量模板的说明明确允许。注 1 说明，允许特化的变量模板会各自规定对特化的要求。

明确允许特化的变量模板都是开关式的定制点：

| 变量模板 | 用途 |
|---|---|
| `std::ranges::enable_borrowed_range<R>` | 声明 `R` 的迭代器不依赖 `R` 对象的生命周期 |
| `std::ranges::enable_view<V>` | 声明 `V` 是视图 |
| `std::ranges::disable_sized_range<R>` | 不让 `ranges::size` 使用 `R` 的 `size()` |
| `std::disable_sized_sentinel_for<S, I>` | 声明 `S - I` 不是常数时间的 |
| `std::format_kind<R>` | 指定范围的格式化方式（序列、集合、映射…） |
| `std::enable_nonlocking_formatter_optimization<T>` | 允许 `std::print` 对 `T` 采用不加锁的优化 |

```cpp run ok
#include <ranges>
struct MyView : std::ranges::view_base {
  int* begin() const;
  int* end() const;
};
template<>
inline constexpr bool std::ranges::enable_borrowed_range<MyView> = true;   // 明确允许
int main() {}
```

`std::is_integral_v`、`std::tuple_size_v` 这类萃取的 `_v` 版本不能特化。它们定义为对应类模板的 `::value`，特化 `_v` 会让两者不一致。

## 不能特化函数模板

<div class="compare" markdown="1">

```cpp ub
#include <utility>
namespace app { struct S {}; }
// C++20 起 UB：特化函数模板
template<>
void std::swap(app::S&, app::S&)
    noexcept {}
int main() {}
```

```cpp run ok
#include <utility>
namespace app {
  struct S { int v; };
  void swap(S& a, S& b) noexcept {
    std::swap(a.v, b.v);
  }
}
int main() {
  app::S a{1}, b{2};
  using std::swap;
  swap(a, b);   // ADL 找到 app::swap
  return a.v == 2 ? 0 : 1;
}
```

</div>

¶2 只允许特化**类模板**。特化函数模板（比如 `std::swap`）是向 `std` 添加声明，落在 ¶1 的 UB 里。左边的代码本机 Clang 编译时没有任何提示。

C++17 及以前的标准允许这样特化函数模板，C++20 通过 [[P0551R3]] 取消了这项许可。函数模板特化本来就不好用：它不参与重载决议，只在主模板被选中之后才被考虑；对类模板 `app::Box<T>` 又无法偏特化，只能改写重载，而重载在 `std` 里本来就不允许。

正确的定制方式是在类型自己的命名空间里提供重载，像右边那样，再由调用方用两步式（`using std::swap; swap(a, b);`）或 `std::ranges::swap` 调用，让 ADL 找到它（[[swappable.requirements]]）。

## 成员和推导指引（¶4）

```cpp ub
#include <vector>
struct S {};
// UB：即使依赖程序定义的类型 S
template<> constexpr void std::vector<S>::push_back(const S&) {}
int main() {}
```

¶4 程序声明下列任何一项，行为未定义：

- ¶4.1 标准库类模板的成员函数的显式特化；
- ¶4.2 标准库类或类模板的成员函数模板的显式特化；
- ¶4.3 标准库类或类模板的成员类模板的显式特化或偏特化；
- ¶4.4 标准库类模板的推导指引。

理论上可以按 ¶2 特化整个 `std::vector<S>`（要满足 `vector` 的全部要求），却不能只特化它的一个成员。成员函数有几个重载、签名是什么，都是实现的自由（[[member.functions]]），标准里写的 `push_back(const T&)` 在实现中未必是一个独立的函数。

违反 ¶4.4 时，libc++ 会直接报错。`namespace std { vector(const char*) -> vector<string>; }` 得到 "deduction guide must be declared in the same scope as template 'std::vector'"，因为真正的 `vector` 在 `std::__1` 里，推导指引必须和模板位于同一作用域（[[temp.deduct.guide]]）。

## 显式实例化（¶5）

```cpp
#include <vector>
struct S {};
template class std::vector<S>;     // OK：依赖程序定义的类型 S
template class std::vector<int>;   // UB：不依赖程序定义的类型
```

¶5 程序可以显式实例化标准库中的类模板，条件和特化一样：声明依赖至少一个程序定义类型的名字（¶5.1），实例化满足原模板的要求（¶5.2）。

`std::vector<int>` 不行，是因为实现可能已经在库的二进制文件里提供了这个实例化。libstdc++ 对 `basic_string<char>` 等就是这样做的，头文件里用 `extern template` 声明。用户再实例化一次，可能违反 [[temp.explicit]] 中一个特化至多有一个显式实例化定义的规定。

显式实例化整个类模板会实例化它的所有成员函数，包括本来对 `S` 用不上的那些。¶5.2 要求 `S` 满足让这些成员都能实例化的要求。

## 不要取标准库函数的地址（¶6）

```cpp error
#include <algorithm>
#include <cctype>
#include <locale>
#include <string>
int main() {
  std::string s = "abc";
  std::transform(s.begin(), s.end(), s.begin(), std::toupper);
  // error: no matching function for call to 'transform'
}
```

`<cctype>` 的 `int toupper(int)` 和 `<locale>` 的 `template<class charT> charT toupper(charT, const locale&)` 构成重载集，`transform` 的模板实参无法推导。只包含 `<cctype>` 时这段代码碰巧能编译，但标准同样不保证。

¶6 设 *F* 是标准库函数（[[global.functions]]）、标准库静态成员函数，或标准库函数模板的特化。除非 *F* 被指定为**可寻址函数**（[[g:addressable-function]]，addressable function），程序显式或隐式地形成指向 *F* 的指针，行为是**未指明的（可能非良构）**。注 2 列出了形成指针的手段：一元 `&`、`std::addressof`、函数到指针的转换（[[conv.func]]）。形成对 *F* 的引用，或者形成指向标准库非静态成员函数的成员指针，也一样。

未指明（可能非良构）是一种少见的组合：实现可能接受，得到一个可用的指针；也可能拒绝编译。它不是 UB，最坏的结果是编译不过，不会悄悄出错。这条规则从 C++20 起生效（[[P0551R3]]），理由和 ¶1 一样，为实现保留这些自由：

- 给函数加重载、给成员函数加默认实参（[[global.functions#2]]、[[member.functions#2]]），这会让 `&std::f` 产生歧义；
- 给函数加上 `noexcept`（[[res.on.exception.handling#5]]），这会改变函数指针的类型；
- 把函数实现成函数对象。

可移植的写法是用 lambda 包一层，顺便处理 `char` 可能为负的问题：

```cpp run ok
#include <algorithm>
#include <cctype>
#include <string>
int main() {
  std::string s = "abc";
  std::ranges::transform(s, s.begin(), [](unsigned char c) {
    return static_cast<char>(std::toupper(c));
  });
  return s == "ABC" ? 0 : 1;
}
```

同样不可移植的还有 `std::function<double(double)> f = std::sqrt;`、`&std::vector<int>::push_back`、`std::bind(&std::string::size, _1)`。办法都是换成 lambda。

### 可寻址函数

被指定为可寻址的函数可以放心取地址，当前草案中有两类：

- iostream 操纵符：`boolalpha`、`hex`、`fixed` 等 `ios_base` 操纵符（[[std.ios.manip]]），以及 `endl`、`ends`、`flush`、`ws` 等（[[ostream.manip]]、[[istream.manip]]）。它们本来就要以函数指针的形式传给 `operator<<`。
- {{c++26}} 反射头文件 `<meta>` 中的函数，除非另有说明（[[meta.reflection]]）。

```cpp run ok
#include <iostream>
#include <ostream>
int main() {
  std::ostream& (*pe)(std::ostream&) = std::endl;    // OK：可寻址函数
  std::ios_base& (*ph)(std::ios_base&) = &std::hex;  // OK：可寻址函数
  std::cout << ph << 255 << pe;                      // 输出 ff
}
```

## 反射标准库实体（¶7、¶8）{{c++26}}

C++26 的静态反射（[[P2996R13]]）可以枚举、命名标准库中的实体，暴露的实现细节比取地址还多。¶7、¶8 把取地址的思路推广到了反射。

¶7 设 *F* 是标准库函数或函数模板。除非 *F* 是可寻址函数，能不能、以及怎样形成指代它的反射值，是未指明的。*F* 的形参有没有名字（`has_identifier` 的结果）、叫什么名字，也都未指明。实现中的形参名通常是 `__x`、`_Tp` 这类保留标识符，而且随版本变化。注 3 补充，`std::meta::members_of` 可能根本不返回实现通过语言之外的机制处理的标准库函数。

¶8 对标准库类，能不能形成其私有成员的反射值、这些成员叫什么名字，都未指明。[[objects.within.classes]] 说库类的内部表示是未指明的，¶8 把这一点延伸到了反射。

## std 不能是内联命名空间（¶9）

```cpp error
inline namespace std {}   // error: cannot declare the namespace 'std' to be inline
int main() {}
```

¶9 翻译单元不得把 `std` 声明为内联命名空间（[[namespace.def]]）。这条没有标注不要求诊断，所以违反就是非良构，编译器必须报告。如果 `std` 可以是全局的内联命名空间，它的所有名字都会在全局可见，与 C 库的全局名字和用户的名字大面积冲突。

## 命名空间 posix [namespace.posix]

¶1 向命名空间 `posix` 或它的嵌套命名空间添加声明或定义，行为未定义，除非另有说明。`posix` 保留给 POSIX 标准（ISO/IEC/IEEE 9945）将来的 C++ 绑定。自己的 POSIX 封装应该另起名字。

## 为将来保留的命名空间 [namespace.future]

¶1 名字由 `std` 后接一个或多个数字组成的顶层命名空间，保留给将来的标准化，向其中添加声明或定义是 UB。例 1 提到 `std2` 保留给本标准将来的修订。

| 命名空间 | 是否保留 |
|---|---|
| `std2`、`std26`、`std0` | 保留 |
| `stdx`、`std_2`、`stdlib` | 不保留：不是 std 加数字 |
| `app::std2` | 不保留：不是顶层 |

## 常见误解

!!! pitfall "特化 `std::hash<std::pair<int, int>>`"
    这个特化不依赖程序定义的类型，是 UB。应该自己写一个哈希函数对象，作为无序容器的模板实参：`std::unordered_map<std::pair<int, int>, V, PairHash>`。

!!! pitfall "在 `namespace std { }` 里顺手加辅助函数"
    `namespace std { template<> struct hash<app::Id> { ... }; }` 是合法的，只是不推荐。但如果在同一个块里顺手定义了一个 `hash_combine` 辅助函数，那个函数就是 ¶1 的 UB。用 `template<> struct std::hash<app::Id>` 的写法可以避免这种情况。

## 思考题

!!! question "思考题 1"
    下面的特化合法吗？
    ```cpp
    namespace app { enum class Color { red, green }; }
    template<> struct std::hash<std::optional<app::Color>> { /* 满足 Cpp17Hash */ };
    ```

<details markdown="1">
<summary>答案</summary>

满足 ¶2.1：声明依赖程序定义的类型 `app::Color`，枚举也算。标准已经为 `std::optional<T>` 提供了 `hash` 的偏特化（[[optional.hash]]），用户的显式特化比它更特殊，会被选中，语言上没有问题。只要满足 ¶2.2 的要求，它就是合法的。

还有一个语言层面的陷阱：显式特化必须出现在第一次会引起隐式实例化的使用之前，否则程序非良构、不要求诊断（[[temp.expl.spec]]）。如果某个翻译单元先用了 `std::hash<std::optional<app::Color>>`，用的就是标准的偏特化。所以这种特化应当紧跟在 `app::Color` 的定义后面，放在同一个头文件里。
</details>

!!! question "思考题 2"
    `auto f = &std::move<int&>;` 的行为是什么？`auto g = &std::meta::is_class_type;` 呢？

<details markdown="1">
<summary>答案</summary>

`std::move<int&>` 是标准库函数模板的特化，不是可寻址函数，形成指向它的指针是未指明的（可能非良构）。实践中通常能编译，但标准不保证。

`std::meta::is_class_type` 是 `<meta>` 中的函数，按 [[meta.reflection]] ¶1 是可寻址函数，取地址是允许的。不过它是 `consteval` 函数，取它的地址只能出现在立即函数上下文中（[[expr.const]]），这是语言层面的另一条约束。
</details>
