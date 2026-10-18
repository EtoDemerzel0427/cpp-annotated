---
title: 可存放任意类型的 any
summary: std::any 的完整契约——存入类型必须是可复制构造的 decay_t<T>（Constraints + Preconditions）、"小对象应避免动态分配但仅限 nothrow 移动的类型"、any_cast 的引用/值/指针三类形式与各自的 Mandates 和失败方式、make_any 与 emplace、为什么 any 必须要求可复制，以及 libc++ 的 handler 函数指针实现
status: done
covers: *
papers: P0220R1
related: variant, optional, func.wrap.func, func.wrap.move, func.wrap.copy, expr.typeid, structure.specifications, utility.arg.requirements, utilities
tags: 标准库, any, 类型擦除, 小对象优化
updated: 2026-10-18
---

`std::any` 是一个能装**任何可复制类型**的值、并且**记得那个值是什么类型**的容器。它和 [[variant]] 同为"可以装不同类型的东西"，但取舍完全相反：

| | `variant<Ts...>` | `any` |
|---|---|---|
| 可存类型集合 | 编译期固定的 `Ts...` | 开放：任何可复制构造的对象类型 |
| 存储 | 嵌套在对象内，禁止堆分配 | 可能堆分配；小对象**应当**放在内部缓冲区 |
| 取值 | `get` / `visit`，可穷尽 | `any_cast`，必须**精确**说出类型 |
| 类型信息 | 编译期下标 | 运行期 `type_info` |

`any` 是一个典型的**类型擦除**（[[g:type-erasure]]）类：它的类型不携带所存值的类型，所有针对具体类型的操作（复制、销毁、按类型取回）都通过运行时间接调用完成——与 `std::function`（[[func.wrap.func]]）是同一种技术。

[any] 有 5 个子条款（加上 [any.class] 下的 5 个），本页全部覆盖：

| 子条款 | 内容 |
|---|---|
| [any.general] | 目的：不做转换的"可辨识类型" |
| [any.synop] | `<any>` 概要 |
| [any.bad.any.cast] | `bad_any_cast` |
| [any.class.general] | 状态、所含值、**小对象优化** |
| [any.cons] | 构造与析构 |
| [any.assign] | 赋值 |
| [any.modifiers] | `emplace`、`reset`、`swap` |
| [any.observers] | `has_value`、`type` |
| [any.nonmembers] | `swap`、`make_any`、`any_cast` |

## 设计意图（[any.general]）

¶1 说 [any] 描述的组件用于"对**可辨识类型**（[[g:discriminated-type]]，*discriminated type*）的对象执行操作"。注 1 把意图说得很清楚：可辨识类型可以装不同类型的值，但**不尝试在它们之间转换**——`5` 就严格地是 `int`，既不能隐式变成 `"5"` 也不能变成 `5.0`。这种"对解释漠不关心、对类型却明察秋毫"的特性，使它成为安全的、通用的单值容器，"不会因为有歧义的转换而带来意外"。

这句话是理解 `any_cast` 的钥匙：**存进去的是什么类型，取出来就必须写什么类型**（忽略顶层 cv 和引用），`any_cast<long>` 取不出 `int`。

## 概要与 bad_any_cast（[any.synop]、[any.bad.any.cast]）

`<any>` 包含 `<initializer_list>` 与 `<typeinfo>`，声明 `bad_any_cast`、`any`、非成员 `swap`、两个 `make_any`、三个按引用的 `any_cast` 与两个按指针的 `any_cast`。注意 `any` 的成员函数**都不是 `constexpr`**（只有默认构造函数是），因为它可能需要动态分配并通过函数指针间接调用。

`bad_any_cast` 公开继承 **`bad_cast`**（而不是直接继承 `exception`），与 `dynamic_cast` 引用失败时抛出的 `bad_cast` 同族——两者都是"运行时类型检查失败"。¶1：失败的 `any_cast` 抛出它；¶2：`what()` 返回实现定义的 NTBS。

## 状态与小对象优化（[any.class.general]）

¶1：`any` 对象要么存放一个"满足构造函数要求的任意类型"的实例，要么没有值；这称为它的**状态**。存放的实例叫**所含值**。两个状态**等价**，当且仅当都没有值，或者都有值且所含值等价——这个"等价"定义被 [any.assign]/5 的移动赋值后置条件使用。

¶2：非成员 `any_cast` 提供对所含值的类型安全访问。

¶3 是本节最有工程意味的一段：

!!! std
    Implementations should avoid the use of dynamically allocated memory for a small contained value. However, any such small-object optimization shall only be applied to types `T` for which `is_nothrow_move_constructible_v<T>` is `true`.

    实现**应当**避免为小的所含值使用动态分配的内存。但这种小对象优化**只能**用于 `is_nothrow_move_constructible_v<T>` 为 `true` 的类型 `T`。

两句话的法律分量不同：

- 第一句是 "*should*"——**鼓励**（*encouraged*）而非要求，标准没有定义"小"是多小，实现可以完全不做小对象优化（[[g:small-object-optimization]]）而依然符合标准。
- 第二句是 "*shall*"——**硬性禁止**：移动构造可能抛异常的类型**不得**放进内部缓冲区，不管它有多小。

为什么有第二句？因为 `any` 的移动构造、移动赋值和 `swap` 都是 **`noexcept`** 的（见下文）。如果 `T` 放在堆上，移动 `any` 只是把指针挪过去，永远不会抛；但如果 `T` 放在内部缓冲区，移动 `any` 就必须**真的移动构造一个 `T`**，若这一步能抛，`noexcept` 就无法兑现。于是：移动可能抛的类型只能放堆上。例 1：`int` 可以存放在内部缓冲区中。

在 libc++ 上可以直接观察到这三类情况：

```cpp run title="any-sbo.cpp" ok
#include <any>
#include <cstdio>
#include <cstdlib>
#include <new>

static int allocs = 0;
void* operator new(std::size_t n) {
    ++allocs;
    if (void* p = std::malloc(n)) return p;
    throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct Small    { void* p[3]; };                         // 24 字节，移动 noexcept
struct Big      { void* p[4]; };                         // 32 字节
struct Throwing { Throwing() = default;
                  Throwing(const Throwing&) {}
                  Throwing(Throwing&&) noexcept(false) {} }; // 1 字节，但移动可能抛

template<class T>
int count() {
    int before = allocs;
    std::any a = T{};
    return allocs - before;
}

int main() {
    std::printf("sizeof(any)=%zu\n", sizeof(std::any));
    std::printf("int:%d Small:%d Big:%d Throwing:%d\n",
                count<int>(), count<Small>(), count<Big>(), count<Throwing>());
}
```

在本机（arm64 macOS，libc++ 23）上输出 `sizeof(any)=32` 和 `int:0 Small:0 Big:1 Throwing:1`——`Throwing` 只有 1 字节，却因为移动构造不是 `noexcept` 而被迫堆分配。具体阈值是实现细节，libstdc++ 与 MSVC 的缓冲区大小各不相同，不要依赖。

## 构造与析构（[any.cons]）

### 默认、复制、移动（¶1–4）

- `constexpr any() noexcept`：¶1 后置条件 `has_value()` 为 `false`。这是 `any` 唯一的 `constexpr` 成员，使 `constinit std::any g;` 成为可能。
- `any(const any& other)`：¶2 若 `other` 无值则构造空对象，否则**等价于** `any(in_place_type<T>, any_cast<const T&>(other))`，`T` 为所含值类型；¶3 抛出所选构造函数抛出的任何异常（复制可能分配、可能调用 `T` 的复制构造）。
- `any(any&& other) noexcept`：¶4 若 `other` 无值则构造空对象；否则新对象"要么含有 `other` 的所含值，要么含有一个以该所含值为右值构造出的同类型对象"。

¶4 的"要么……要么……"正是为小对象优化留的口子：堆上的值可以**直接接管**（指针转移，"含有 `other` 的所含值"）；内部缓冲区的值则要**移动构造**一份（"由该值作为右值构造"）。注意标准**没有**规定移动之后 `other` 处于什么状态——它可能为空，也可能仍有一个被移动过的值。libc++ 的两种实现都会把 `other` 置空，但可移植代码不能依赖这一点。

### 从值构造 `template<class T> any(T&& value)`（¶5–9）

¶5：令 `VT` 为 `decay_t<T>`。

!!! std
    *Constraints*: `VT` is not the same type as `any`, `VT` is not a specialization of `in_place_type_t`, and `is_copy_constructible_v<VT>` is `true`.

    **约束**：`VT` 不是 `any`，不是 `in_place_type_t` 的特化，并且 `is_copy_constructible_v<VT>` 为 `true`。

¶7 **Preconditions**：`VT` 满足 *Cpp17CopyConstructible*（[[utility.arg.requirements]]）。¶8 **Effects**：构造一个含有 `VT` 类型对象的 `any`，以 `std::forward<T>(value)` 直接初始化。¶9：抛出 `VT` 所选构造函数抛出的异常。

这里有两层"可复制"要求，分属不同的法律层级（[[structure.specifications]]）：

| 层级 | 内容 | 违反的后果 |
|---|---|---|
| *Constraints* | `is_copy_constructible_v<VT>`——**语法上**能复制构造 | 构造函数不参与重载决议，`is_constructible_v<any, VT>` 为 `false`，SFINAE 友好 |
| *Preconditions* | *Cpp17CopyConstructible*——**语义上**复制得到等价的值，且不修改源对象 | 未定义行为 |

所以 `std::any a = std::make_unique<int>(1);` 是"没有可行的转换"的编译错误（约束不满足，构造函数消失），而不是 `static_assert` 失败：

```cpp run title="any-move-only.cpp" error
#include <any>
#include <memory>

std::any a = std::make_unique<int>(1);   // error: unique_ptr 不可复制，约束不满足
```

几个由 `decay_t` 带来的细节：

- `any a = "Meow";` 存的是 `const char*`，不是 `const char[5]`；
- 函数会退化成函数指针；
- 存进去的永远是**非引用、非 cv** 的对象类型——`any` 不能"装一个引用"。

排除 `in_place_type_t` 是为了让 `any(in_place_type<int>, ...)` 这种调用不会被这个转换构造截胡（否则 `any a(std::in_place_type<int>);` 会把**标签对象本身**存进去）。注意这个构造函数**不是 `explicit`**——任何可复制的值都能隐式变成 `any`，这是 `any` 作为形参类型时的一大陷阱（见"常见误区"）。

### in_place 构造（¶10–21）

- `explicit any(in_place_type_t<T>, Args&&...)`（¶10–15）：**Constraints** `is_copy_constructible_v<VT>` 且 `is_constructible_v<VT, Args...>`；**Preconditions** 同上；**Effects** 以 `std::forward<Args>(args)...` **直接非列表初始化** `VT`；**Postconditions** `*this` 含有 `VT` 类型的值。
- `initializer_list` 版本（¶16–21）同理，¶20 的后置条件写的只是"含有一个值"。

`in_place` 形式让你可以构造**不可移动**但可复制的类型、或者需要多个构造实参的类型，而无需先构造一个临时量再搬进去。

析构 `~any()`（¶22）：如同 `reset()`。

## 赋值（[any.assign]）

| 运算 | 效果 | 异常保证 |
|---|---|---|
| `operator=(const any& rhs)`（¶1–3） | 如同 `any(rhs).swap(*this)` | ¶1：抛出异常时**无效果**（强保证） |
| `operator=(any&& rhs) noexcept`（¶4–6） | 如同 `any(std::move(rhs)).swap(*this)` | ¶5：`*this` 的状态等价于 `rhs` 原来的状态 |
| `template<class T> operator=(T&& rhs)`（¶7–12） | 构造临时 `any tmp` 含有以 `std::forward<T>(rhs)` 直接初始化的 `VT`，再 `tmp.swap(*this)` | ¶10：抛出异常时**无效果** |

全部是经典的 copy-and-swap：先把新值完整地构造在临时对象里，再 `noexcept` 地交换。这也是 ¶3 小对象优化限制的又一个受益者——`swap` 能 `noexcept`，强异常保证才成立。转换赋值的 **Constraints**（¶8）是 `VT` 不是 `any` 且可复制构造（没有排除 `in_place_type_t`，因为赋值不涉及标签消歧）。

与 [[variant.variant]] 的赋值对比：`variant` 因为禁止堆分配，"先构造再交换"需要额外的缓冲区，所以只能在类型满足条件时提供强保证，否则可能 valueless；`any` 可以随意在堆上构造临时值，于是**总是**强保证。

## 修改器（[any.modifiers]）

### emplace（¶1–16）

```cpp
template<class T, class... Args> decay_t<T>& emplace(Args&&...);
template<class T, class U, class... Args> decay_t<T>& emplace(initializer_list<U>, Args&&...);
```

**Constraints** 与 `in_place` 构造相同；**Effects**：先调用 `reset()`，**然后**直接非列表初始化 `VT`；**Returns** 新值的引用。¶8/¶16 **Remarks**：

!!! std
    If an exception is thrown during the call to `VT`'s constructor, `*this` does not contain a value, and any previously contained value has been destroyed.

    若 `VT` 的构造函数抛出异常，`*this` 不含值，且先前的所含值已被销毁。

注意这里是确定性的"**不含值**"，而 `variant::emplace` 是"**允许**不持有值"（[[variant.variant]]）。`emplace` 放弃强保证换来的是：不需要临时对象，可以就地构造不可移动的类型。

### reset 与 swap（¶17–19）

- `reset() noexcept`：若有值则销毁之；后置条件 `has_value()` 为 `false`。
- `swap(any& rhs) noexcept`：交换两者的状态。

## 观察器（[any.observers]）

- `has_value() noexcept`：有所含值时为 `true`。
- `type() noexcept`：有值时返回 `typeid(T)`，否则返回 `typeid(void)`（[[expr.typeid]]）。注 1：可用于与编译期已知或仅运行期已知的类型做比较。

`type()` 依赖 RTTI。在 `-fno-rtti` 下 libc++ 不提供 `type()`，但 `any_cast` 仍然可用——它改用每个类型一个静态变量的**地址**作为类型标识（`__any_imp::__unique_typeinfo<T>::__id`）。

## 非成员函数（[any.nonmembers]）

### swap 与 make_any（¶1–3）

`swap(x, y)` 等价于 `x.swap(y)`。`make_any<T>(args...)` 等价于 `any(in_place_type<T>, std::forward<Args>(args)...)`；`initializer_list` 版本同理。`make_any` 的价值在于可以写 `auto a = std::make_any<std::vector<int>>({1, 2, 3});`——`T` 显式给出，`initializer_list<U>` 中的 `U` 由推导得到。

```cpp run title="any-construct.cpp" ok
#include <any>
#include <cassert>
#include <complex>
#include <vector>

struct Throws { Throws() { throw 1; } };

int main() {
    auto a = std::make_any<std::complex<double>>(1.0, 2.0);      // 原地构造
    auto b = std::make_any<std::vector<int>>({1, 2, 3});         // initializer_list 重载
    assert(std::any_cast<std::vector<int>&>(b).size() == 3);

    std::any c(std::in_place_type<std::vector<int>>, 5, 42);     // 等价写法
    assert(std::any_cast<const std::vector<int>&>(c)[4] == 42);

    auto& v = c.emplace<std::vector<int>>(2u, 7);                // 返回新值的引用
    v.push_back(8);
    assert(std::any_cast<std::vector<int>&>(c).size() == 3);

    try { a.emplace<Throws>(); } catch (int) {}                   // ¶8：抛出后 any 为空
    assert(!a.has_value());

    std::any d = std::move(b);                                   // any 的移动构造 noexcept
    static_assert(std::is_nothrow_move_constructible_v<std::any>);
    assert(d.has_value());
}
```

### any_cast：三类形式，两种失败方式（¶4–11）

**按引用传入 `any` 的三个重载**（¶4–8）：

```cpp
template<class T> T any_cast(const any& operand);
template<class T> T any_cast(any& operand);
template<class T> T any_cast(any&& operand);
```

¶4：令 `U` 为 `remove_cvref_t<T>`。

!!! std
    *Mandates*: For the first overload, `is_constructible_v<T, const U&>` is `true`. For the second overload, `is_constructible_v<T, U&>` is `true`. For the third overload, `is_constructible_v<T, U>` is `true`.

    **强制要求**：第一个重载要求 `is_constructible_v<T, const U&>`；第二个要求 `is_constructible_v<T, U&>`；第三个要求 `is_constructible_v<T, U>`。

¶6 **Returns**：前两个是 `static_cast<T>(*any_cast<U>(&operand))`，第三个是 `static_cast<T>(std::move(*any_cast<U>(&operand)))`。¶7 **Throws**：若 `operand.type() != typeid(remove_reference_t<T>)`，抛出 `bad_any_cast`。

把这三条拼在一起理解：

- **`T` 决定"怎么取"**：`any_cast<int>` 复制出一个 `int`；`any_cast<int&>` 返回所含值的左值引用，可以原地修改；`any_cast<const int&>` 返回只读引用；`any_cast<std::string&&>(std::move(a))` 把所含值作为右值交出来以便移动。
- **Mandates 是"const 正确性"检查**：从 `const any&` 不能取出 `U&`（`is_constructible_v<U&, const U&>` 为假）——标准例子中的 `any_cast<string&>(y)` 对 `const any y` 是编译错误；从左值 `any&` 不能取出 `U&&`。这是 *Mandates*，不是 *Constraints*：这三个重载以 `operand` 的值类别区分，`T` 写错了不会让另一个重载顶上，而是直接报错。
- **运行时检查用 `typeid(remove_reference_t<T>)`**：`typeid` 忽略顶层 cv（[[expr.typeid]]），所以 `any_cast<const int&>` 能取出 `int`；但 `int` 与 `long` 是不同类型，`any_cast<long>` 对存着 `int` 的 `any` 抛 `bad_any_cast`。
- **没有值时**：`type()` 是 `typeid(void)`，与任何对象类型都不相等，也抛 `bad_any_cast`。

**按指针传入 `any` 的两个重载**（¶9–11）：

```cpp
template<class T> const T* any_cast(const any* operand) noexcept;
template<class T> T* any_cast(any* operand) noexcept;
```

¶9 **Mandates**：`is_void_v<T>` 为 `false`。¶10 **Returns**：若 `operand != nullptr && operand->type() == typeid(T)`，返回指向所含值的指针；否则返回 `nullptr`。例 2 用它实现 `is_string`：`any_cast<string>(&operand) != nullptr`。

指针形式**从不抛异常**：空指针、无值、类型不符全部以 `nullptr` 报告——这和 `dynamic_cast` 的指针/引用两种失败方式（`nullptr` vs `bad_cast`）一模一样，也和 `variant` 的 `get_if`/`get` 对应。引用形式在内部就是调用指针形式再解引用（¶6 的 `*any_cast<U>(&operand)`）。

```cpp run title="any-cast.cpp" ok
#include <any>
#include <cassert>
#include <string>

int main() {
    std::any x = 5;                                  // 持有 int
    assert(std::any_cast<int>(x) == 5);              // 值形式：返回副本
    std::any_cast<int&>(x) = 10;                     // 引用形式：改的是 any 里的那个 int
    assert(std::any_cast<int>(x) == 10);

    try {
        (void)std::any_cast<long>(x);                // 类型必须精确匹配：int ≠ long
        assert(false);
    } catch (const std::bad_any_cast&) {}

    assert(std::any_cast<long>(&x) == nullptr);      // 指针形式：不抛，返回 nullptr
    assert(std::any_cast<const int>(&x) != nullptr); // typeid 忽略顶层 cv，所以匹配

    x = "Meow";                                      // decay：存的是 const char*
    assert(x.type() == typeid(const char*));

    x = std::string("Meow");
    std::string s = std::any_cast<std::string&&>(std::move(x)); // 从 any 里移走
    assert(s == "Meow");
    assert(x.has_value());                           // 被移走的 string 仍然在 any 里

    x.reset();
    assert(!x.has_value() && x.type() == typeid(void));
}
```

```cpp run title="any-cast-const.cpp" error
#include <any>
#include <string>

int main() {
    const std::any y = std::string("cat");
    std::any_cast<std::string&>(y);   // error: Mandates——不能用 any_cast 去掉 const
}
```

```cpp run title="any-cast-void.cpp" error
#include <any>

int main() {
    std::any a = 1;
    return std::any_cast<void>(&a) != nullptr;   // error: Mandates——T 不能是 void
}
```

libc++ 用 `static_assert` 实现这些 Mandates，消息分别是 "ValueType is required to be a const lvalue reference or a CopyConstructible type" 和 "_ValueType may not be void."。

## 为什么 any 要求可复制

`any` 本身是可复制的类型：`any b = a;` 必须工作。由于类型被擦除了，复制 `any` 时需要通过存下来的"复制函数"去复制所含值——这个函数在**存入**的那一刻就要实例化。若允许存入 `unique_ptr`，就只剩两种选择：

1. `any` 的复制在运行时发现所含值不可复制，然后抛异常——把一个本可在编译期发现的错误推迟到运行期，而且让"`any` 可复制"这一类型属性变得不可信；
2. `any` 自己不可复制——那它就不再能放进 `std::vector` 后再复制、不能作为普通值语义的参数传递，失去了"装任何值的值"的意义。

标准选择了在**入口**处拒绝：每个能放入值的成员（转换构造、`in_place` 构造、转换赋值、`emplace`）都带 `is_copy_constructible_v<VT>` 的约束。这和 `std::function` 必须要求可调用对象可复制是同一个原因；`std::function` 的这个限制后来催生了只移动的 `std::move_only_function`（C++23，[[func.wrap.move]]），而 `any` 至今没有标准的只移动版本。需要存放只移动的对象时，常见的变通是用 `std::shared_ptr<T>` 包一层（复制的是共享所有权），或者使用第三方的 move-only any 实现。

## libc++ 实现剖析

以下基于本地 libc++ 23 的 `<any>`（`include/c++/v1/any`）。

**布局**：一个函数指针 + 一个联合体存储：

```cpp
// 简化自 libc++ <any>
class any {
    using _HandleFuncPtr = void* (*)(_Action, any const*, any*, const type_info*, const void*);
    union _Storage {
        void* __ptr;                                                    // 大对象：指向堆
        alignas(void*) char __buf[3 * sizeof(void*)];                   // 小对象：就地存放
    };
    _HandleFuncPtr __h_ = nullptr;     // nullptr 表示无值
    _Storage __s_;
};
```

64 位平台上 `sizeof(any) == 32`。`has_value()` 就是 `__h_ != nullptr`。

**小对象判定**（`__any_imp::_IsSmallObject`）：`sizeof(T) <= 3 * sizeof(void*)`、`alignof(T) <= alignof(void*)`、**并且** `is_nothrow_move_constructible_v<T>`——第三个条件正是 ¶3 的 *shall*。

**handler 而非虚函数**：每个类型 `T` 对应 `_SmallHandler<T>` 或 `_LargeHandler<T>` 的一个静态函数 `__handle`，用一个 `_Action` 枚举（`_Destroy`、`_Copy`、`_Move`、`_Get`、`_TypeInfo`）分派。这相当于一个"只有一项的手写虚表"：每个 `any` 只多存一个函数指针，而不是指向 vtable 的指针 + 堆上的多态对象。

**移动**：`_LargeHandler::__move` 只是把 `__ptr` 抄给目标、把源的 `__h_` 置空——[any.cons]/4 所说的"含有 `other` 的所含值"；`_SmallHandler::__move` 则在目标缓冲区移动构造一个 `T`、销毁源对象——"由该值作为右值构造的同类型对象"。两者都使源 `any` 变空。

**any_cast 的类型比较**：`_Get` 动作调用 `__compare_typeid<T>`：有 RTTI 时比较 `type_info`；无 RTTI 时比较 `__unique_typeinfo<T>::__id` 的地址。对**函数类型**的 `T`，指针形式的 `any_cast` 直接返回 `nullptr`（`any` 不可能存函数，只能存函数指针）。

**大对象构造的异常安全**：`_LargeHandler::__create` 先分配，再用 `__exception_guard` 保护，若 `T` 的构造抛出则释放内存——不会泄漏。

## 常见误区

!!! pitfall "以 any 为形参就是放弃类型检查"
    `void set(std::string key, std::any value);` 能接受任何可复制的东西：`set("timeout", 30)` 存的是 `int`，读取方写 `any_cast<long>` 就会在运行时抛 `bad_any_cast`；`set("name", "bob")` 存的是 `const char*` 而不是 `std::string`，`any_cast<std::string>` 同样失败。存入方和读取方必须对**精确类型**有约定，通常要配合 `in_place_type` 或显式构造（`std::string("bob")`）。

!!! pitfall "以为 any 可以装引用或数组"
    `decay_t` 会把数组变成指针、函数变成函数指针、去掉引用和 cv。`int arr[3]; std::any a = arr;` 存的是 `int*`——一个可能悬空的指针，而不是三个 `int` 的副本。

!!! pitfall "依赖被移动后的 any 为空"
    [any.cons]/4 没有规定被移动的 `any` 的状态。libc++ 会把它置空，但标准允许它仍持有一个被移动过的值。需要空状态时显式 `reset()`。

## 思考题

!!! question "思考题 1"
    `std::any a = 1;` 之后，`std::any_cast<int&&>(a)` 和 `std::any_cast<const int&&>(std::as_const(a))` 分别是什么结果？

<details markdown="1">
<summary>展开查看答案与解析</summary>

第一个：`a` 是非 const 左值，选中第二个重载 `any_cast(any&)`，`U = int`，*Mandates* 要求 `is_constructible_v<int&&, int&>`——右值引用不能绑定到左值，为 `false`，**编译错误**。想要右值，需要 `any_cast<int&&>(std::move(a))`（第三个重载，要求 `is_constructible_v<int&&, int>`，为真）。

第二个：选中第一个重载，要求 `is_constructible_v<const int&&, const int&>`——同样是右值引用绑定左值，为 `false`，编译错误。要点：Mandates 中的第二个实参类型（`const U&`、`U&`、`U`）精确地刻画了"从这个 `any` 能拿出什么值类别"，`T` 只能在此基础上**添加** const 或复制，不能凭空制造右值。
</details>

!!! question "思考题 2"
    一个实现选择**完全不做**小对象优化（所有值都堆分配）。它符合标准吗？反过来，一个实现对 `sizeof(T) <= 16` 的所有类型都使用内部缓冲区，又如何？

<details markdown="1">
<summary>展开查看答案与解析</summary>

前者符合：¶3 第一句是 "*should*"，只是建议（*Recommended practice* 性质），不构成要求。后者不符合：第二句是 "*shall*"，若某个 `T` 的移动构造可能抛（`is_nothrow_move_constructible_v<T>` 为 `false`），就**不得**放入内部缓冲区，无论它多小。从机理上看，违反这一条会使 `any(any&&) noexcept` 与 `swap noexcept` 无法实现——移动 `any` 需要移动构造 `T`，`T` 抛出时只能调用 `std::terminate`。
</details>

## 小结

| 操作 | 关键契约 |
|---|---|
| 存入（转换构造、`in_place`、转换赋值、`emplace`） | Constraints：`decay_t<T>` 可复制构造（及可从实参构造）；Preconditions：满足 *Cpp17CopyConstructible* |
| 小对象优化 | 应当（should）避免小对象的动态分配；只能（shall）用于 nothrow 移动的类型 |
| 复制构造 / 复制赋值 | 可能抛；赋值为强保证（copy-and-swap） |
| 移动构造 / 移动赋值 / `swap` / `reset` | `noexcept`；被移动对象状态未规定 |
| `emplace` | 先 `reset()` 再构造；构造抛出则 `*this` **一定**为空 |
| `type()` | 有值：`typeid(T)`；无值：`typeid(void)` |
| `any_cast<T>(any&/const any&/any&&)` | Mandates：`T` 可由 `const U&`/`U&`/`U` 构造；类型不符抛 `bad_any_cast` |
| `any_cast<T>(any*)` | Mandates：`T` 不是 `void`；类型不符或空指针返回 `nullptr`，`noexcept` |
| `make_any<T>(args...)` | 等价于 `any(in_place_type<T>, args...)` |
