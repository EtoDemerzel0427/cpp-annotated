---
title: 命名空间的使用：std 里能放什么
summary: 往 namespace std 里添加声明或定义是 UB——例外是依赖程序定义类型的类模板特化（hash、tuple_size、formatter……）与少数被明确允许的变量模板特化；禁止特化函数模板（C++20 起）、成员函数、成员模板，禁止为标准类模板写推导指引；显式实例化同样要依赖程序定义类型；除"可寻址函数"外，取标准库函数的地址或引用是未指明的（可能非良构）；反射标准库函数与私有成员也未指明；std 不能是内联命名空间；posix 与 std+数字 命名空间被保留。
status: done
covers: *
papers: P0551R3, P2996R13
related: constraints, reserved.names, requirements, utility.requirements, conforming, global.functions, member.functions, temp.expl.spec, temp.explicit, namespace.def, expr.unary.op
tags: 库, namespace std, 特化, UB, 可寻址函数, language lawyer
updated: 2026-10-18
---

"我能不能往 `namespace std` 里加点东西？"——这大概是标准库条款中被问得最多的问题。答案的总原则是**不能**（¶1），然后有一张精确的例外清单。本页逐条讲清楚这张清单，以及与之相关的"能不能取标准库函数的地址"问题。

为什么要这么严格？标准库的实现需要**演化的自由**：今天 `std::swap` 是一个函数模板，明天它可能多出一个重载、变成一个 CPO、搬进一个内联命名空间（[[contents#2]]）；今天 `std::vector::push_back` 有两个重载，实现可以有三个（[[member.functions]]）。用户代码一旦往 `std` 里加声明、特化函数、取地址，就和这些实现细节绑死了。[namespace.constraints] 划定的，就是用户与实现之间的"公共接口边界"。

## 总原则：添加即 UB（[namespace.std] ¶1）

!!! std
    Unless otherwise specified, the behavior of a C++ program is undefined if it adds declarations or definitions to namespace `std` or to a namespace within namespace `std`.

    除非另有说明，若 C++ 程序向命名空间 `std` 或 `std` 内的命名空间添加声明或定义，其行为未定义。

注意范围：`std::ranges`、`std::chrono`、`std::pmr`、`std::execution`、`std::meta` 等嵌套命名空间同样适用。常见的违规：

```cpp ub
#include <ostream>
#include <string>
#include <vector>
namespace std {
  // UB：为 std 中的类型在 std 中添加运算符重载（"为了让 ADL 找到它"）
  template<class T>
  ostream& operator<<(ostream& os, const vector<T>& v) { /* ... */ return os; }

  // UB：添加 std::to_string 的新重载
  string to_string(const vector<int>& v);

  // UB：自己前向声明标准类型（libc++ 中甚至会因内联命名空间 std::__1 而直接报错）
  template<class T> class optional;
}
int main() { }
```

第一种情况尤其诱人：`std::vector<int>` 的关联命名空间只有 `std`，所以用户定义在全局的 `operator<<` 在模板内部（例如 `std::ostream_iterator`）通过 ADL 找不到，于是有人把它塞进 `std`。正确做法是：写一个具名函数、包一层自己的类型，或在 C++23 起直接用 `std::print` / `std::format`，它们原生支持范围。

"UB"意味着什么？绝大多数时候这些代码都能编译运行——但它可能与实现内部的同名实体冲突、可能在实现升级后静默改变重载决议结果、可能违反 ODR。标准选择 UB 而不是"非良构"，是因为编译器无法区分"标准库头文件里的声明"和"用户写的声明"（两者都是普通的 C++ 代码）。不过，现代实现正在尝试诊断一部分情形，见下文 ¶3 的 libc++ 例子。

## 允许：依赖程序定义类型的类模板特化（¶2）

¶2 除非被明确禁止，程序可以为**任何标准库类模板**向 `std` 添加模板特化，前提是：

- **¶2.1** 所添加的声明**依赖至少一个程序定义的类型**；并且
- **¶2.2** 该特化满足原模板的标准库要求。

脚注 140 说明这对实现意味着什么：任何实例化其他库模板的库代码，都必须准备好与满足本文档最低要求的任何用户提供的特化正常配合。

### "程序定义的类型"是什么

**程序定义的类型**（program-defined type，[intro.defs]）是：不属于 C++ 标准库、也不由实现定义的非闭包类类型或枚举类型；或非实现提供的 lambda 表达式的闭包类型；或**程序定义的特化**（[intro.defs]：不属于标准库、不由实现定义的显式特化或偏特化）的实例化。

于是以下都"依赖程序定义的类型"：

| 特化 | 依赖的程序定义类型 | 允许？ |
|---|---|---|
| `std::hash<app::Id>` | `app::Id` | 是 |
| `template<class T> struct std::hash<app::Box<T>>` | `app::Box<T>` | 是（偏特化也可以） |
| `std::hash<std::vector<app::Id>>` | `app::Id`（作为模板实参） | 是——"依赖"不要求最外层是用户类型 |
| `std::hash<std::pair<int, int>>` | 无 | **否**，UB |
| `std::hash<int*>` | 无 | **否**（且标准已有指针的特化） |
| `std::hash<decltype([]{})>` 的类型 | 闭包类型 | 是 |

最后一条 ¶2.2 也很重要：特化必须满足原模板的**要求**。例如 `std::hash<K>` 的特化必须满足 *Cpp17Hash*（[[hash.requirements]]）与 [[unord.hash]] 的要求——可默认构造、可拷贝、`operator()` 返回 `size_t`……一个不满足要求的特化同样导致 UB。

### 常见的、被设计成可以特化的类模板

```cpp run ok
#include <cstddef>
#include <format>
#include <functional>
#include <string>
#include <tuple>
#include <unordered_set>
#include <utility>
#include <vector>

namespace app {
  struct Id { int v; bool operator==(const Id&) const = default; };
  template<class T> struct Box { T value; bool operator==(const Box&) const = default; };
  struct Pair {
    int a; double b;
    template<std::size_t I> auto get() const { if constexpr (I == 0) return a; else return b; }
  };
}

template<> struct std::hash<app::Id> {                     // ¶2：OK
  std::size_t operator()(app::Id i) const noexcept { return std::hash<int>{}(i.v); }
};
template<class T> struct std::hash<app::Box<T>> {          // ¶2：偏特化，OK
  std::size_t operator()(const app::Box<T>& b) const { return std::hash<T>{}(b.value); }
};
template<> struct std::hash<std::vector<app::Id>> {        // ¶2：依赖 app::Id，OK
  std::size_t operator()(const std::vector<app::Id>& v) const noexcept { return v.size(); }
};
// 结构化绑定的"元组协议"（[dcl.struct.bind]）
template<> struct std::tuple_size<app::Pair> : std::integral_constant<std::size_t, 2> {};
template<> struct std::tuple_element<0, app::Pair> { using type = int; };
template<> struct std::tuple_element<1, app::Pair> { using type = double; };
// std::format 的定制（[format.formatter]）
template<> struct std::formatter<app::Id> : std::formatter<int> {
  auto format(app::Id i, std::format_context& ctx) const {
    return std::formatter<int>::format(i.v, ctx);
  }
};

int main() {
  std::unordered_set<app::Id> s{{1}, {2}};
  std::unordered_set<app::Box<std::string>> t{{"x"}};
  auto [a, b] = app::Pair{1, 2.5};
  std::string str = std::format("{}", app::Id{42});
  return s.size() == 2 && t.size() == 1 && a == 1 && b == 2.5 && str == "42" ? 0 : 1;
}
```

`template<> struct std::hash<app::Id>` 这种**限定名**写法（显式特化可以在主模板可被定义的任何作用域中、用限定名声明，[[temp.expl.spec]]）比 `namespace std { template<> struct hash<app::Id> {...}; }` 更好：它不会"打开"`std`，也就不可能顺手在里面加入别的东西。

其他常被特化的：`std::coroutine_traits`（让协程返回非类类型或第三方类型）、`std::common_type` 与 `std::basic_common_reference`（被 [meta.trans.other] 明确允许）、`std::iterator_traits`（为迭代器提供 traits）、`std::numeric_limits`（为数值类型）、`std::uses_allocator`、`std::is_error_code_enum` / `std::is_error_condition_enum`（由 [syserr] 明确允许，配合 ADL 找到的 `make_error_code`）、`std::pointer_traits`。

### "除非被明确禁止"

许多标准类模板明确禁止用户特化：

| 模板 | 规定 | 违反的后果 |
|---|---|---|
| [[type.traits]] 中的所有模板（`is_integral`、`remove_cv`……） | [meta.rqmts] ¶4：除非另有说明，添加特化是 UB | UB |
| `std::initializer_list` | [support.initlist] ¶2 | **非良构** |
| `std::allocator_traits` | [[allocator.requirements#3]] Note：不存在程序定义的特化 | — |
| `std::ranges::range_adaptor_closure`、`std::generator`、`std::is_execution_policy`、`std::basic_format_arg`、`std::chrono::is_clock` | 各自条款：添加特化是 UB | UB |

类型萃取被禁止特化的原因显而易见：`is_integral<MyInt>` 若可以被特化为 `true`，编译器内建的那些假设（例如对整数类型才合法的操作）会被打破；而且像 `is_trivially_copyable` 这样的萃取直接对应于语言规则，不可能由用户"声明"。

本机 Clang + libc++ 已经开始**诊断**这类 UB：libc++ 把类型萃取标上了 `[[clang::no_specializations]]` 属性。

```cpp error
#include <type_traits>
struct S {};
template<> struct std::is_integral<S> : std::true_type {};
// error: 'is_integral' cannot be specialized: Users are not allowed to specialize
//        this standard library entity [-Winvalid-specialization]
int main() { }
```

标准说这是 UB，libc++ 选择报错——UB 允许实现做任何事，包括拒绝编译。

## 变量模板：默认禁止（¶3）

¶3 若程序声明了任何标准库**变量模板**的显式特化或偏特化，行为未定义——除非该变量模板的规范明确允许。Note 1：允许的变量模板各自规定了对特化的要求。

被明确允许的变量模板都是**定制开关**：

| 变量模板 | 用途 |
|---|---|
| `std::ranges::enable_borrowed_range<R>` | 声明 `R` 的迭代器不依赖 `R` 对象的生命周期（可安全返回） |
| `std::ranges::enable_view<V>` | 声明 `V` 是视图 |
| `std::ranges::disable_sized_range<R>` | 关闭 `ranges::size` 对 `R` 的 `size()` 的使用 |
| `std::disable_sized_sentinel_for<S, I>` | 声明 `S - I` 不是常数时间的 |
| `std::format_kind<R>` | 指定范围的格式化方式（序列、集合、映射……） |
| `std::enable_nonlocking_formatter_optimization<T>` | 允许 `std::print` 对 `T` 使用无锁优化 |

而 `std::is_integral_v`、`std::tuple_size_v` 这类"萃取的 `_v` 版本"**不能**特化——它们定义为 `= is_integral<T>::value`，特化 `_v` 会让两者不一致。

```cpp run ok
#include <ranges>
struct MyView : std::ranges::view_base {
  int* begin() const;
  int* end() const;
};
template<> inline constexpr bool std::ranges::enable_borrowed_range<MyView> = true;  // ¶3：明确允许
int main() { }
```

## 禁止：成员函数、成员模板、推导指引（¶4）

¶4 若程序声明了下列任何一项，行为未定义：

- **¶4.1** 标准库**类模板的任何成员函数**的显式特化；
- **¶4.2** 标准库类或类模板的任何**成员函数模板**的显式特化；
- **¶4.3** 标准库类或类模板的任何**成员类模板**的显式或偏特化；
- **¶4.4** 任何标准库类模板的**推导指引**。

```cpp ub
#include <vector>
struct S {};
// ¶4.1：UB——即使依赖程序定义的类型 S
template<> constexpr void std::vector<S>::push_back(const S&) { }
int main() { }
```

¶4.1 与 ¶2 的对比值得注意：可以特化整个 `std::vector<S>`（理论上，只要满足 vector 的全部要求——实践中没人这么做），但不能只特化它的一个成员函数。原因是成员函数的签名、数量、是否内联都是实现的自由（[[member.functions]]）：标准里的 `push_back(const T&)` 在实现中可能根本不是一个独立的函数。

¶4.4 禁止推导指引。在 libc++ 中这条 UB 甚至直接变成编译错误：`namespace std { vector(const char*) -> vector<string>; }` 报 "deduction guide must be declared in the same scope as template 'std::vector'"——因为真正的 `vector` 在 `std::__1` 中，推导指引必须与模板在同一作用域（[[temp.deduct.guide]]）。

## 显式实例化（¶5）

¶5 程序可以**显式实例化**标准库中定义的类模板，仅当该声明：

- **¶5.1** 依赖至少一个程序定义类型的**名字**；并且
- **¶5.2** 该实例化满足原模板的标准库要求。

```cpp
#include <vector>
struct S {};
template class std::vector<S>;     // OK：依赖程序定义的类型 S
template class std::vector<int>;   // UB：不依赖任何程序定义的类型
```

为什么 `std::vector<int>` 不行？因为实现可能已经在库的二进制中提供了 `vector<int>` 的显式实例化（libstdc++ 对 `basic_string<char>` 等就是这么做的，在头文件中用 `extern template` 声明），用户再显式实例化一次就可能违反 [[temp.explicit]] 的"至多一个显式实例化定义"。

显式实例化**整个类模板**还意味着实例化**所有**成员函数——包括那些对 `S` 来说本来不可用的成员。所以 ¶5.2 要求 `S` 满足让所有成员都能实例化的要求。

## 不能取标准库函数的地址（¶6）

¶6 是 C++20 引入的重大限制（[[P0551R3]]）。设 *F* 表示一个标准库函数（[[global.functions]]）、标准库静态成员函数，或标准库函数模板的特化。除非 *F* 被指定为[[g:addressable-function|**可寻址函数**]]（*addressable function*），若程序**显式或隐式地试图形成指向 F 的指针**，其行为是**未指明的（可能非良构）**。Note 2：形成这种指针的可能手段包括一元 `&`（[[expr.unary.op]]）、`addressof`、函数到指针的标准转换（[[conv.func]]）。

此外，试图形成**对 F 的引用**，或试图形成指向标准库**非静态成员函数**或标准库成员函数模板特化的**成员指针**，行为同样未指明（可能非良构）。

### 为什么

因为实现有权：

- 给非成员函数加重载（只要不改变合法调用的结果，[[global.functions#2]]），给成员函数加重载和默认实参（[[member.functions#2]]）——于是 `&std::f` 可能变得有歧义；
- 把函数实现为函数对象（CPO）或宏以外的任何东西；
- 改变函数的 `noexcept`（[[res.on.exception.handling#5]]）——这会改变函数指针的类型。

### 经典例子：`std::toupper`

```cpp error
#include <algorithm>
#include <cctype>
#include <locale>
#include <string>
int main() {
  std::string s = "abc";
  std::transform(s.begin(), s.end(), s.begin(), std::toupper);
  // error: no matching function for call to 'transform'
  //   <cctype> 的 int toupper(int) 与 <locale> 的 template<class charT> charT toupper(charT, const locale&)
  //   构成重载集，模板实参无法推导
}
```

即使只包含 `<cctype>`、碰巧能编译，按 ¶6 这也是未指明行为。可移植的写法是用 lambda 包一层（顺便修正 `char` 可能为负的问题）：

```cpp run ok
#include <algorithm>
#include <cctype>
#include <string>
int main() {
  std::string s = "abc";
  std::ranges::transform(s, s.begin(),
      [](unsigned char c) { return static_cast<char>(std::toupper(c)); });
  return s == "ABC" ? 0 : 1;
}
```

同理不可移植的还有：`std::function<double(double)> f = std::sqrt;`、`auto p = &std::vector<int>::push_back;`、`std::thread t(std::sleep_for<...>, ...)`、`std::bind(&std::string::size, _1)`。统一的解法：**lambda 包装**。

### 可寻址函数

被明确**指定为可寻址**（designated addressable function）的函数可以安全取地址。当前草案中包括：

- iostream 的操纵符：`boolalpha`、`hex`、`left`、`fixed` 等 `ios_base` 操纵符（[std.ios.manip]），以及 `endl`、`ends`、`flush`、`ws` 等（[istream.manip]、[ostream.manip]）——它们本来就是以函数指针的形式传给 `operator<<` 的；
- C++26 反射头文件 `<meta>` 中的函数（除非另有说明）——它们以 `consteval` 函数的形式提供，经常需要作为高阶函数的实参。

```cpp run ok
#include <iostream>
#include <ostream>
int main() {
  std::ostream& (*pe)(std::ostream&) = std::endl;   // OK：endl 的特化是可寻址函数
  std::ios_base& (*ph)(std::ios_base&) = &std::hex; // OK：hex 是可寻址函数
  std::cout << ph << 255 << pe;                     // 输出 ff
}
```

!!! note "未指明（可能非良构）"
    "unspecified (possibly ill-formed)" 是一种不常见的组合措辞：行为是未指明的——实现可能接受（得到一个可用的函数指针）、可能拒绝（编译错误），但**不是** UB。与 ¶1 的"添加声明是 UB"相比，它对程序的伤害更小：最坏是编译不过，不会悄悄出错。

## 反射与标准库（¶7–¶8）{{c++26}}

C++26 静态反射（[[P2996R13]]）带来了一个新的"取地址"问题：通过反射值可以枚举、命名、拼接标准库实体，这比取地址暴露更多的实现细节。

¶7 设 *F* 是标准库函数或函数模板。除非 *F* 被指定为可寻址函数，是否以及如何能够形成指称其关联实体的**反射值**是**未指明**的。对于表示 *F* 的某个形参反射的任何 `meta::info` 值 *p*，`has_identifier(p)` 返回 `true` 还是 `false` 是未指明的；若为 `true`，`meta::identifier_of(p)` 和 `meta::u8identifier_of(p)` 产生的 ntmbs 是未指明的。Note 3：例如，`std::meta::members_of` 可能不会返回实现通过语言外机制处理的标准库函数的反射。

形参名未指明，因为实现的形参名是 `__x`、`_Tp` 之类的保留标识符，而且随版本变化。

¶8 设 *C* 是标准库类或类模板特化。是否以及如何能形成对 *C* 任何**私有成员**的反射值，以及这些成员的名字，都是未指明的。——[[objects.within.classes]] 说类的表示未指明，¶8 把这一点延伸到反射：你可以用 `nonstatic_data_members_of` 去看 `std::vector` 的私有成员（若实现允许），但看到什么、叫什么名字，没有任何保证。

## std 不能是内联命名空间（¶9）

¶9 翻译单元不得把命名空间 `std` 声明为内联命名空间（[[namespace.def]]）。

这是一条可诊断规则（无"不要求诊断"），违反即非良构：

```cpp error
inline namespace std { }   // error: cannot declare the namespace 'std' to be inline
int main() { }
```

若允许 `std` 是全局的内联命名空间，`std` 中的所有名字都会变成全局可见，与 C 库的全局名字、用户名字大面积冲突。

## 命名空间 posix（[namespace.posix]）

¶1 若 C++ 程序向命名空间 `posix` 或 `posix` 内的命名空间添加声明或定义，其行为未定义，除非另有说明。命名空间 `posix` 保留给 ISO/IEC/IEEE 9945 及其他 POSIX 标准使用。

这是为将来的 POSIX C++ 绑定预留的。所以不要把自己的 POSIX 封装放在 `namespace posix` 里——起名 `my_posix`、`sys` 都可以。

## 为将来标准化保留的命名空间（[namespace.future]）

¶1 名字由 `std` 后跟**一个或多个数字**（[[lex.name]]）构成的**顶层**命名空间，保留给将来的标准化。若程序向这样的命名空间添加声明或定义，行为未定义。Example 1：顶层命名空间 `std2` 保留给本标准的将来修订使用。

| 命名空间 | 保留？ |
|---|---|
| `std2`、`std26`、`std0` | 是 |
| `stdx`、`std_2`、`stdlib` | 否（不是"std + 数字"） |
| `app::std2` | 否（不是顶层） |

这条规则在 C++17 时期加入，背景是当时关于"不兼容的新一代标准库 std2"的讨论；该设想后来没有实现，但保留规则留了下来。

## 历史与演进

- **C++98–C++17**：允许为标准库**函数模板**添加显式特化（只要依赖用户定义类型）。最常见的就是特化 `std::swap`：

  ```cpp
  namespace std { template<> void swap(MyType& a, MyType& b) noexcept { a.swap(b); } }
  ```

  但这种做法问题重重：函数模板特化不参与重载决议（只在主模板被选中后才考虑），对类模板（`MyTmpl<T>`）无法偏特化，只能改为**重载**——而重载又是 ¶1 禁止的。
- **C++20**：[[P0551R3]]（"Thou Shalt Not Specialize std Function Templates!"）彻底禁止特化标准库函数模板，同时引入"可寻址函数"的概念与 ¶6 的取址限制。正确的定制方式改为：在类型自己的命名空间中提供 ADL 可找到的函数（`swap`、`begin`……），由两步式或 CPO 调用。
- **C++26**：¶7、¶8 针对反射加入；更多的标准库实体获得了显式的"禁止特化"条款。

```cpp ub
#include <utility>
namespace app { struct S { }; }
template<> void std::swap(app::S&, app::S&) noexcept { }   // C++20 起：UB（¶1，函数模板特化不再被 ¶2 允许）
int main() { }
```

（这段代码本机 Clang + libc++ 编译无任何诊断。）正确写法：

```cpp run ok
#include <utility>
namespace app {
  struct S { int v; };
  void swap(S& a, S& b) noexcept { std::swap(a.v, b.v); }   // ADL 可找到的重载
}
int main() {
  app::S a{1}, b{2};
  using std::swap;
  swap(a, b);                  // 两步式：调用 app::swap
  return a.v == 2 ? 0 : 1;
}
```

## 常见误区

!!! pitfall "\"我只是加一个 operator<<\""
    在 `std` 中为 `std::vector`、`std::pair` 等加运算符是最普遍的违规。它在一个 TU 中"能用"，但如果两个库各加了一个，就是 ODR 违规；若标准库将来自己提供了（C++23 的 `std::formatter` 对范围的支持就是一例），则会产生歧义。

!!! pitfall "特化 std::hash<std::pair<int,int>>"
    不依赖程序定义类型，UB。改为自定义哈希函数对象作为 `unordered_map` 的第三个模板实参：`std::unordered_map<std::pair<int,int>, V, PairHash>`。

!!! pitfall "std::function<R(Args...)> f = std::some_function;"
    取标准库函数地址是未指明的（¶6）。今天能编译，明天实现加个重载就不能了。用 lambda。

!!! lawyer "特化 std::hash 时用了 namespace std { }"
    `namespace std { template<> struct hash<app::Id> { ... }; }` 是合法的（¶2 允许"向 std 添加模板特化"），只是不推荐。但如果在同一个 `namespace std { }` 块中顺手写了一个辅助函数 `inline size_t hash_combine(...)`，那个辅助函数就是 ¶1 的 UB。

## 思考题

!!! question "思考题 1"
    以下特化合法吗？

    ```cpp
    namespace app { enum class Color { red, green }; }
    template<> struct std::hash<std::optional<app::Color>> { /* 满足 Cpp17Hash */ };
    ```

<details markdown="1">
<summary>展开查看答案与解析</summary>

¶2.1 满足：声明依赖程序定义的类型 `app::Color`（枚举也是程序定义的类型）。标准**已经**为 `std::optional<T>` 提供了 `hash` 的偏特化（[[optional.hash]]），用户的显式特化 `hash<optional<app::Color>>` 比它更特殊，会被选中——语言上没有问题。只要满足 ¶2.2（*Cpp17Hash* 与 [[unord.hash]] 的要求），它就是合法的。

还有一个语言层面的陷阱：显式特化必须在**第一次会导致隐式实例化的使用之前**声明，否则程序非良构、不要求诊断（[[temp.expl.spec]]）。若某个 TU 先用了 `std::hash<std::optional<app::Color>>`（实例化了标准偏特化），后面才看到你的显式特化，就踩中了这条。所以这种特化应当紧挨着 `app::Color` 的定义放在同一个头文件里。
</details>

!!! question "思考题 2"
    `auto f = &std::move<int&>;` 的行为是什么？`auto g = &std::meta::is_class_type;` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`std::move<int&>` 是标准库函数模板的特化，不是可寻址函数——形成指向它的指针是未指明的（可能非良构）。实践中它通常能编译，但标准不保证；况且 Clang、GCC 都会把 `std::move`、`std::forward` 等识别为内建操作做特殊处理，取地址时它们只能退回到库里的普通定义。

`std::meta::is_class_type` 是 `<meta>` 中的函数，[meta.reflection] 规定除非另有说明，该头文件中的每个函数都是可寻址函数——所以取地址的行为是规定好的。不过它是 `consteval` 函数（立即函数），取它的地址本身只能出现在立即函数上下文或常量求值中（[[expr.const]] 对立即函数的限制），这是语言层面的另一道约束。
</details>

## 小结

!!! summary "能做与不能做"
    | 行为 | 规定 | 后果 |
    |---|---|---|
    | 向 `std`（及其嵌套命名空间）添加声明、重载、新名字 | ¶1 | UB |
    | 特化标准**类模板**，依赖程序定义的类型并满足要求 | ¶2 | **允许**（除非明确禁止） |
    | 特化类型萃取 | [meta.rqmts] ¶4 | UB（libc++ 报错） |
    | 特化 `std::initializer_list` | [support.initlist] | 非良构 |
    | 特化标准**变量模板** | ¶3 | UB，除非明确允许（`enable_borrowed_range` 等） |
    | 特化标准**函数模板**（如 `std::swap`） | ¶1（C++20 起） | UB |
    | 特化成员函数 / 成员函数模板 / 成员类模板 | ¶4.1–¶4.3 | UB |
    | 为标准类模板写推导指引 | ¶4.4 | UB |
    | 显式实例化标准类模板 | ¶5 | 仅当依赖程序定义类型 |
    | 取标准库函数的地址 / 引用 / 成员指针 | ¶6 | 未指明（可能非良构），可寻址函数除外 |
    | 反射标准库函数 / 私有成员 | ¶7–¶8 | 未指明 |
    | `inline namespace std` | ¶9 | 非良构 |
    | 向 `posix` 或 `std2` 等添加声明 | [namespace.posix]、[namespace.future] | UB |
