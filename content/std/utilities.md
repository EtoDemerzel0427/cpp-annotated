---
title: 通用工具库
summary: 第 22 章导读：<utility>、pair、tuple、optional、variant、any、expected、bitset、<functional> 和 <bit> 各自解决什么问题，以及读这一章的条文前要先认识的 Constraints、Mandates、Preconditions 和 Hardened preconditions。
status: done
covers: utilities.general
related: library, structure.specifications, utility, pairs, tuple, optional, variant, any, expected, bitset, function.objects, bit, class.union, class.prop
tags: 导读, 标准库, 词汇类型
updated: 2026-10-19
---

!!! tldr
    - 第 22 章收录几乎每个程序都会用到、又不属于容器、算法或 I/O 的小组件，其中不少还是标准库其他部分的积木，例如 `std::move`、`std::pair`、`std::invoke`。
    - `optional`、`variant`、`any`、`expected` 都是在一个对象里存放可能不同的值；前两者和 `expected` 不分配内存，特殊成员函数随元素类型有条件地平凡。
    - 库函数的说明分成固定的几个元素：违反 *Constraints* 时该函数退出重载决议，违反 *Mandates* 时编译报错，违反 *Preconditions* 是未定义行为。
    - C++26 把 `optional::operator*` 等不检查的访问改成了 *Hardened preconditions*：在加固实现中违反时程序终止，在其他实现中仍是未定义行为。

## 本章地图 [utilities.general]

¶1 本章描述在 C++ 程序中普遍有用的工具，其中一些也被标准库的其他部分使用。

| 节 | 条款 | 头文件 | 内容 |
|---|---|---|---|
| 22.2 | [[utility]] | `<utility>` | `swap`、`exchange`、`move`、`forward`、`declval`、整数安全比较 `cmp_less` 等、`to_underlying`、`unreachable`；{{c++26}} `constant_wrapper`（[[const.wrap.class]]） |
| 22.3 | [[pairs]] | `<utility>` | `pair` |
| 22.4 | [[tuple]] | `<tuple>` | `tuple`、`apply`、`make_from_tuple` |
| 22.5 | [[optional]] | `<optional>` | 可能为空的值 `optional<T>`；{{c++26}} `optional<T&>` |
| 22.6 | [[variant]] | `<variant>` | 类型安全的联合体 `variant`、`visit` |
| 22.7 | [[any]] | `<any>` | 可以存放任意可复制类型的 `any` |
| 22.8 | [[expected]] | `<expected>` | {{c++23}} 值或错误 `expected<T, E>` |
| 22.9 | [[bitset]] | `<bitset>` | 定长位集 |
| 22.10 | [[function.objects]] | `<functional>` | *INVOKE*、`reference_wrapper`、`bind_front`、`function`、`move_only_function`、`function_ref`、`hash` 等 |
| 22.11 | [[bit]] | `<bit>` | `bit_cast`、`byteswap`、2 的幂、循环移位、位计数 |
| 22.12 | [[stdbit.h.syn]] | `<stdbit.h>` | {{c++26}} C23 的位操作头文件 |

!!! note "已经搬走的内容"
    C++17 和 C++20 的 [utilities] 还包括智能指针和内存工具、`<type_traits>`、`<ratio>`、`<charconv>`、`<format>`、执行策略、`type_index` 等（C++17 还有 `<chrono>`）。现在它们分散在别处：内存在 [[mem]]，类型特征和 `<ratio>` 在 [[meta]]，`<charconv>` 和 `<format>` 在 [[text]]，执行策略在 [[execpol]]，`type_index` 在 [[type.index]]，时间库在 [[time]]。引用旧版标准的条款号时要注意这一点。

## 四种词汇类型

`optional`、`variant`、`any`、`expected` 常被称为**词汇类型**（vocabulary types）：不同的库用同一种类型表达同一件事，接口就能互相配合。它们的设计取舍可以放在一张表里比较：

| | `optional<T>` | `variant<Ts...>` | `any` | `expected<T, E>` |
|---|---|---|---|---|
| 存什么 | 一个 `T`，或者没有值 | `Ts` 中恰好一个 | 任意可复制的类型 | 一个 `T`，或者一个错误 `E` |
| 存储 | 对象内部 | 对象内部 | 可能在堆上（标准鼓励对小对象避免分配） | 对象内部 |
| 空状态 | `nullopt`，正常状态 | `valueless_by_exception()`，只会因异常出现 | 空的 `any`，正常状态 | 没有：总是有值或有错误 |
| 访问错的东西 | `operator*` 违反加固前置条件；`value()` 抛 `bad_optional_access` | `get` 抛 `bad_variant_access`；`get_if` 返回空指针 | `any_cast` 抛 `bad_any_cast` 或返回空指针 | `operator*` 违反加固前置条件；`value()` 抛 `bad_expected_access<E>` |
| 平凡性 | 特殊成员随 `T` 有条件地平凡 | 随全部 `Ts` | 不平凡 | 随 `T` 和 `E` |

最后一行值得多看一眼：

```cpp run title="optional-trivial.cpp" ok
#include <optional>
#include <string>
#include <type_traits>

static_assert( std::is_trivially_copyable_v<std::optional<int>>);
static_assert(!std::is_trivially_copyable_v<std::optional<std::string>>);

int main() {}
```

`optional<int>` 可以像 `int` 一样用 `memcpy` 复制、在寄存器里传递，`optional<string>` 不行。一个类模板要做到这一点，需要两方面的语言支持：联合体的特殊成员只有在所有变体成员的对应函数都平凡时才不被弃置（[[class.union]]）；C++20 起一个类可以声明多个带不同约束的预期析构函数等特殊成员，由约束选出其中一个（[[class.dtor]]、[[special]]）。细节见 [[optional.optional]] 和 [[variant.variant]]，平凡性为什么重要见 [[class.prop]]。

## 读库条文要先认识的元素

库条文中每个函数都按 [[structure.specifications#3]] 规定的元素书写。不同元素被违反时，后果完全不同：

| 元素 | 不满足时 |
|---|---|
| *Constraints* | 该函数不参与重载决议，不报错，可以被 `requires` 表达式探测到 |
| *Mandates* | 程序非良构，编译器必须诊断 |
| *Constant When* | 这次调用不是常量子表达式 |
| *Preconditions* | 未定义行为 |
| *Hardened preconditions* | 加固实现在函数产生其他可观察副作用之前检查条件，失败时终止；其他实现中是未定义行为 |

```cpp run title="mandates.cpp" error
#include <variant>
int main() {
  std::variant<int, int> v{std::in_place_index<0>, 1};
  return std::get<int>(v);   // error: int 在 Ts 中出现了两次，违反 Mandates
}
```

`std::get<T>(variant)` 要求 `T` 在 `Ts...` 中恰好出现一次，这是 *Mandates*，违反时直接编译失败，不会退而选择别的重载。按下标取值的 `std::get<0>(v)` 没有这个问题。反过来，`optional<T>` 的转换构造函数用的是 *Constraints*：条件不满足时这个构造函数只是退出重载决议，`is_constructible_v<optional<int>, std::string>` 平静地得到 `false`。判断一个库接口能否用于概念检测，看的就是这个区别。

### 加固前置条件 {{c++26}}

```cpp title="hardened.cpp"
#include <optional>
int main() {
  std::optional<int> o;
  return *o;   // 违反 hardened precondition：has_value() 为 false
}
```

`optional::operator*`、`expected::operator->`、`bitset::operator[]` 等不检查的访问函数，过去是普通前置条件，违反就是未定义行为。C++26 把它们改成了加固前置条件：同一份代码，在加固的标准库下运行到这里会确定地终止。本机 libc++ 用 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 编译上面的程序，运行时以 `SIGTRAP` 终止；不加这个宏则没有任何检查。哪些实现算加固实现见 [[intro.compliance]]。

另一个常见措辞是 Equivalent to：*Effects* 写成等价于某段代码时，那段代码的语义（调用哪些函数、抛出什么异常、能否用于常量求值）就是这个函数的语义（[[structure.specifications#4]]）。`std::apply`、`optional::value_or`、`expected` 的 `and_then` 等都这样定义。

## 推荐阅读顺序

1. [[utility]]：`move`、`forward`、`declval` 是阅读其余条文的基础词汇。
2. [[func.require]]：*INVOKE* 的定义，`apply`、`visit`、`function`、`optional::and_then` 都以它为基础。
3. [[pairs]] 和 [[tuple]]：类元组协议，以及它和结构化绑定（[[dcl.struct.bind]]）的关系。
4. [[optional.optional]]、[[variant.variant]]、[[expected.expected]]：同一套有条件平凡的技巧用了三次；[[any]] 是类型擦除的对照。
5. [[func.wrap]]：四种多态函数包装器的取舍。
6. [[bit]]：`bit_cast` 是合法地重新解释对象表示的标准做法，可与 [[basic.lval]] 的别名规则对照阅读。

## 思考题

!!! question "思考题"
    `std::optional<int>` 是平凡可复制的吗？标准在哪里保证了这一点？

<details markdown="1">
<summary>答案</summary>

是。[optional.ctor] 规定，若 `is_trivially_copy_constructible_v<T>` 为真，复制构造函数是平凡的；移动构造、复制赋值、移动赋值和析构函数（[optional.dtor]）都有类似的条款。`int` 满足全部条件，于是 `optional<int>` 满足 [[class.prop]] 对平凡可复制类的定义。`std::string` 的复制构造和析构都不平凡，所以 `optional<std::string>` 不是平凡可复制的。
</details>
