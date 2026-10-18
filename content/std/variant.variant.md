---
title: 类模板 variant
summary: variant 本体逐条精读——"几乎永不为空"与 valueless_by_exception 的确切成因、条件平凡的特殊成员、P0608 修正后的转换构造/转换赋值 FUN 规则（以数组列表初始化剔除窄化）、赋值时"直接构造 vs 先造临时量再移动"的选择规则、emplace/swap/index，以及 libc++ 的 __variant_detail 实现
status: done
covers: *
papers: P0088R3, P0608R3, P1957R2, P0602R4, P0848R3, P2231R1
related: variant, variant.visit, class.union, special, class.dtor, class.prop, dcl.init.list, dcl.init.aggr, over.match.best, over.ics.rank, structure.specifications, optional.optional, expected.expected
tags: 标准库, variant, 异常安全, 重载决议, 平凡性
updated: 2026-10-18
---

[variant.variant] 是 `<variant>` 的核心：类模板 `variant<Types...>` 的全部成员——构造、析构、赋值、`emplace`、状态查询、`swap`。它有 7 个子条款，本页逐一覆盖：

| 子条款 | 内容 |
|---|---|
| [variant.variant.general] | 类定义概要；"持有一个值或不持有值"；对 `Types` 的要求 |
| [variant.ctor] | 默认/复制/移动构造，**转换构造**（*FUN* 规则），`in_place` 构造 |
| [variant.dtor] | 析构；条件平凡 |
| [variant.assign] | 复制/移动/**转换赋值**；何时会变成 valueless |
| [variant.mod] | `emplace` |
| [variant.status] | `valueless_by_exception()`、`index()` |
| [variant.swap] | 成员 `swap` |

读这一页需要：联合体与活跃成员（[[class.union]]）、特殊成员函数何时平凡（[[special]]、[[class.prop]]）、列表初始化中的窄化（[[dcl.init.list]]）、重载决议的隐式转换序列排序（[[over.ics.rank]]）。取值、比较、哈希在 [[variant]]，`visit` 在 [[variant.visit]]。

## 物理图景：一个联合体加一个下标

在动手读条文之前先建立模型。`variant<int, std::string>` 在内存里大致是：

```cpp
struct variant_int_string {
    union { int i; std::string s; } storage;   // 一次只有一个活跃成员
    unsigned index;                             // 0、1，或 "npos" 表示无值
};
```

所有成员函数做的事都可以归结为：**根据 `index` 决定哪个联合体成员活着，并在切换时正确地结束旧成员、开始新成员的生命周期**（[[basic.life]]）。困难全部集中在"切换"这一步：先销毁旧值再构造新值，如果构造抛了异常，联合体里就**什么都没有了**——这就是 valueless 状态的来源。

## 总体规定（[variant.variant.general]）

¶1：任一时刻，`variant` 实例要么持有某个 alternative 类型的值，要么不持有值。持有 `T` 类型的值时，这个值（称为**所含值**，*contained value*）**嵌套在** `variant` 对象之内（[[intro.object]]）。

!!! std
    When an instance of `variant` holds a value of alternative type `T`, it means that a value of type `T` ... is nested within the `variant` object.

    当 `variant` 持有类型为 `T` 的值时，该值嵌套在 `variant` 对象之内。

"嵌套在内"是一个**禁止堆分配**的规范性要求：实现不能像 Boost.Variant 那样在异常时把备份放到堆上。这一句直接决定了后面所有异常安全的取舍。

¶2：`Types` 中所有类型必须满足 *Cpp17Destructible*。按 [[utility.arg.requirements]] 的注，**数组类型和非对象类型（引用、`void`、函数）都不满足** *Cpp17Destructible*——所以 `variant<int&>`、`variant<int[3]>`、`variant<void>` 都不被允许。这是对程序的"shall"要求，违反时按 [[res.on.functions]] 是未定义行为，但实际实现都会直接报错：libc++ 在类体内用 `static_assert` 给出 "variant can not have a reference type as an alternative" 等诊断。

¶3：实例化**没有模板实参**的 `variant<>` 的定义是非良构的（libc++：`"variant must consist of at least one alternative."`）。只是**提到** `variant<>`（不需要完整类型的场合）不会触发错误。

¶4：程序对 `variant` 声明显式或偏特化 → {{ifndr}}。这比一般的"可以特化标准库模板"（[[namespace.std]]）更严：`variant` 完全禁止用户特化。

## 构造函数（[variant.ctor]）

¶1 约定：`i` 取 `[0, sizeof...(Types))`，`T_i` 是第 `i` 个类型。

### 默认构造（¶2–6）

- **Constraints**：`is_default_constructible_v<T_0>`——只看**第一个**类型。
- **Effects**：值初始化一个 `T_0`。**Postconditions**：不 valueless，`index() == 0`。
- **Remarks**：当且仅当 `T_0` 的值初始化是 *constexpr-suitable*（[[dcl.constexpr]]）时，该函数是 `constexpr` 的；异常规格等价于 `is_nothrow_default_constructible_v<T_0>`。

第一个类型不可默认构造时，惯用法是在最前面垫一个 `monostate`（[[variant]]）。

### 复制与移动构造（¶7–13）——条件删除与条件平凡

复制构造（¶7–9）：若 `w` 有值，以 `GET<j>(w)` 直接初始化同一个 alternative；若 `w` 是 valueless，新对象也是 valueless。

!!! std
    This constructor is defined as deleted unless `is_copy_constructible_v<T_i>` is `true` for all `i`. If `is_trivially_copy_constructible_v<T_i>` is `true` for all `i`, this constructor is trivial.

    除非所有 `T_i` 都可复制构造，否则此构造函数定义为删除。若所有 `T_i` 都可平凡复制构造，则它是平凡的。

移动构造（¶10–13）：**Constraints** 为所有 `T_i` 可移动构造；异常规格是所有 `is_nothrow_move_constructible_v<T_i>` 的逻辑与；所有 `T_i` 可平凡移动构造时它是平凡的。

注意两者措辞的差别：复制构造是"**定义为删除**"，移动构造是"**Constraints**"。后者意味着移动构造在不满足时**不参与重载决议**——于是 `variant(std::move(x))` 会退回到复制构造（如果可用），这正是普通类"没有移动构造就用复制构造"的行为。

析构（[variant.dtor]）同理：¶1 若不 valueless 则销毁所含值；¶2 所有 `T_i` 可平凡析构时析构函数是平凡的。

为什么"条件平凡"如此重要？因为平凡性决定了 [[g:trivially-copyable-type]]，而后者决定了能否 `memcpy`、能否放进寄存器传参（Itanium ABI 要求非平凡复制/析构的类型通过内存传递）。`variant<int, double>` 若不是平凡可复制的，每次按值传参都要走栈——对一个"更好的联合体"来说不可接受。

```cpp run title="variant-triviality.cpp" ok
#include <string>
#include <type_traits>
#include <variant>

using V1 = std::variant<int, double, char>;
static_assert(std::is_trivially_copy_constructible_v<V1>);
static_assert(std::is_trivially_copy_assignable_v<V1>);
static_assert(std::is_trivially_destructible_v<V1>);
static_assert(std::is_trivially_copyable_v<V1>);

using V2 = std::variant<int, std::string>;
static_assert(!std::is_trivially_copyable_v<V2>);
static_assert(std::is_copy_constructible_v<V2>);

struct MoveOnly { MoveOnly(MoveOnly&&) = default; };
using V3 = std::variant<int, MoveOnly>;
static_assert(!std::is_copy_constructible_v<V3>);   // ¶9：定义为删除
static_assert(std::is_move_constructible_v<V3>);

int main() {}
```

!!! impl "如何在库中实现'条件平凡'"
    C++17 时代没有语言直接支持"这个特殊成员在某条件下是 `= default`、否则是用户提供的"，实现只能用**一串条件基类**：每层基类按 trait 选择 `= default`（平凡）、手写（非平凡）或 `= delete` 三种特化之一，`variant` 继承最外层，自己的特殊成员全部 `= default`，平凡性就从基类"传上来"。C++20 的 [[P0848R3]] 让一个类可以声明**多个带 requires 子句的预期特殊成员**，由约束挑出"合格"的那个（[[g:eligible-special-member-function]]、[[class.dtor]] 的预期析构函数），从此可以直接写：

    ```cpp
    ~variant() requires (std::is_trivially_destructible_v<Ts> && ...) = default;
    ~variant() { /* 按 index 销毁 */ }
    ```

    libc++ 出于兼容 C++17 的需要，仍然使用基类阶梯，见下文实现一节。

### 转换构造 `template<class T> variant(T&&)`（¶14–19）

这是整个 `variant` 规范最精巧、历史上也最出问题的一段。目标：给定任意实参 `t`，自动选出"最合适的" alternative `T_j` 来存它。

!!! std
    Let `T_j` be a type that is determined as follows: build an imaginary function *FUN*(`T_i`) for each alternative type `T_i` for which `T_i x[] = {std::forward<T>(t)};` is well-formed for some invented variable `x`.

    按如下方式确定 `T_j`：对每个满足"`T_i x[] = {std::forward<T>(t)};` 良构"的 alternative `T_i`，构造一个虚构函数 *FUN*(`T_i`)……

然后对表达式 *FUN*(`std::forward<T>(t)`) 做**普通的重载决议**（[[over.match.best]]），被选中的那个 *FUN*(`T_j`) 决定了所含值的类型。

拆开来看这套机制（[[g:imaginary-function-fun]]）：

1. **候选集**：每个 alternative 一个单参数函数 `FUN(T_i)`。重载决议会比较"实参 → `T_i`"的隐式转换序列（[[over.ics.rank]]），挑最好的那个；若两个一样好，就**有歧义**，构造函数不可行。
2. **窄化过滤**：只有 `T_i x[] = {std::forward<T>(t)};` 良构的 `T_i` 才进入候选集。这是一个**数组的复制列表初始化**，根据 [[dcl.init.aggr]] / [[dcl.init.list]]，若元素的初始化需要**窄化转换**（[[g:narrowing-conversion]]），程序非良构。所以这一句的作用就是：**会造成窄化的 alternative 不参选**。
3. **实参不是常量表达式**：注意被检查的是 `std::forward<T>(t)`，而不是调用处写的字面量。`std::forward<int>(t)` 不是常量表达式，因此 `int → float` 一律算窄化——"常量值恰好能精确表示就不算窄化"的豁免用不上。
4. **为什么用数组**：`T_i x[] = {e};` 而不是 `T_i x{e};`，是为了让 `T_i` 为类类型时也只做"从 `e` 复制初始化 `T_i`"，不会去匹配 `T_i` 的 `initializer_list` 构造函数或聚合初始化 `T_i` 的成员。

¶15 **Constraints**：`sizeof...(Types)` 非零；`remove_cvref_t<T>` 不是 `variant` 本身，也不是 `in_place_type_t`/`in_place_index_t` 的特化；`is_constructible_v<T_j, T>`；且 *FUN*(`std::forward<T>(t)`) 良构（即重载决议成功且无歧义）。全部是 *Constraints*——任何一条不满足，这个构造函数**从重载集中消失**，`is_convertible_v<X, variant<...>>` 会如实报告 `false`。

¶16 **Effects**：以 `std::forward<T>(t)` **直接非列表初始化** `T_j`——也就是说，*FUN* 只用来**选类型**，真正的初始化不带花括号，不受窄化检查影响。¶19：异常规格等价于 `is_nothrow_constructible_v<T_j, T>`；若所选的 `T_j` 构造函数是 `constexpr` 的，则此构造函数也是。

注意这个构造函数**不是 `explicit`**：`variant<int, std::string> v = "x";` 走的就是它。

#### C++17 原规则的问题与 P0608 的修正

C++17 的 [[P0088R3]] 只有 *FUN* 重载决议，没有窄化过滤。结果是两个著名的坑：

- `variant<std::string, bool> v = "abc";` 选中了 **`bool`**：`const char* → bool` 是标准转换（布尔转换），而 `const char* → std::string` 是用户定义转换，前者更优（[[over.ics.rank]]）。
- `variant<float, long> v = 0;` **有歧义**：`int → float`（浮点-整数转换）与 `int → long`（整数转换）同为"转换"等级。

C++20 的 [[P0608R3]]（"A sane variant converting constructor"）加入了"`T_i x[] = {...}` 必须良构"的过滤，并且当时还额外写了一条对 `bool` 的特殊规则：只有实参本身就是 `bool` 时才考虑 `bool` alternative。随后 [[P1957R2]] 把"**指针/成员指针 → `bool`**"在核心语言中定义为窄化转换（[[dcl.init.list]]），窄化过滤就自然地挡掉了 `const char* → bool`，`variant` 里那条 `bool` 特例随之删除。**当前草案的 ¶14 就只剩数组初始化这一条**，`bool` 不再有特殊措辞。

```cpp run title="p0608.cpp" ok
#include <cassert>
#include <string>
#include <variant>

int main() {
    std::variant<std::string, bool> a = "abc";
    assert(a.index() == 0);          // C++20 起：string（C++17 原规则选 bool）

    std::variant<std::string, bool> b = true;
    assert(b.index() == 1);          // 真正的 bool 仍然选 bool

    std::variant<float, long> c = 0;
    assert(c.index() == 1);          // int→float 是窄化，FUN(float) 被剔除

    std::variant<int, long> d = 0u;  // unsigned→int 窄化；unsigned→long 在 LP64 上不窄化
    assert(d.index() == 1);
}
```

最后一行值得多看一眼：`unsigned → long` 是否窄化取决于 `long` 能否表示 `unsigned` 的所有值。在 LP64（Linux、macOS）上 `long` 是 64 位，不窄化，选 `long`；在 LLP64（Windows）上 `long` 只有 32 位，两个候选都被剔除，**同一行代码在 Windows 上编译失败**。窄化规则让 `variant` 的类型选择对平台的整数宽度敏感。

窄化过滤也会把以前"能编译但很危险"的代码变成错误：

```cpp run title="no-narrowing.cpp" error
#include <string>
#include <variant>

std::variant<int, std::string> v = 3.14;   // error: double→int 窄化，FUN(int) 被剔除；无候选
```

```cpp run title="float-double.cpp" error
#include <variant>

std::variant<float, double> v = 0;   // error: int→float、int→double 都是窄化
```

C++17 规则下前者会悄悄把 `3.14` 截断成 `3` 存进 `int`；后者在 C++17 下是歧义。注 2 给出的标准示例 `variant<string, string> v("abc");` 则在任何版本都非良构：两个 *FUN*(`string`) 完全一样好，重载决议歧义。

!!! lawyer "*FUN* 不是真的函数"
    *FUN* 是"想象中的"：标准没有要求实现真的声明这些函数，只要求结果与"对这样一组函数做重载决议"相同。这意味着重载决议的所有细节都适用——包括引用绑定的优劣、限定转换、派生到基类的转换排序。例如 `variant<Base, Derived>` 用 `Derived` 对象初始化会选 `Derived`（精确匹配），用 `MoreDerived` 对象初始化也会选 `Derived`（派生到更近基类的转换更好，[[over.ics.rank]]）。

### `in_place` 构造（¶20–39）

四个 `explicit` 构造函数，以标签指明要构造哪个 alternative：

| 形式 | Constraints | Postconditions |
|---|---|---|
| `variant(in_place_type_t<T>, Args&&...)`（¶20–24） | `T` 在 `Types` 中**恰好出现一次**；`is_constructible_v<T, Args...>` | `holds_alternative<T>(*this)` |
| `variant(in_place_type_t<T>, initializer_list<U>, Args&&...)`（¶25–29） | 同上，`initializer_list<U>&` 在前 | 同上 |
| `variant(in_place_index_t<I>, Args&&...)`（¶30–34） | `I < sizeof...(Types)`；`is_constructible_v<T_I, Args...>` | `index() == I` |
| `variant(in_place_index_t<I>, initializer_list<U>, Args&&...)`（¶35–39） | 同上 | `index() == I` |

都是**直接非列表初始化**，不受 *FUN* 规则影响，所以 `variant<int, std::string>(std::in_place_index<0>, 3.14)` 是合法的（存入 `3`）——当你确实想要窄化时，`in_place` 是明确表态的方式。注意这里"恰好出现一次"是 *Constraints*（不参与重载决议），而 [[variant]] 中 `get<T>` 的同一条件是 *Mandates*（硬错误）。对于重复类型，只能用 `in_place_index`：

```cpp run title="duplicate-types.cpp" ok
#include <cassert>
#include <string>
#include <variant>

// 两个 string 分别表示"用户名"和"错误信息"：只能用下标区分
using Result = std::variant<std::string, std::string>;

int main() {
    Result r(std::in_place_index<1>, "file not found");
    assert(r.index() == 1);
    r.emplace<0>("alice");                   // 按下标 emplace：OK
    assert(std::get<0>(r) == "alice");
    // r.emplace<std::string>("bob");       // error: string 出现两次，约束不满足
    // r = "bob";                           // error: FUN 重载决议有歧义
}
```

## 几乎永不为空：valueless_by_exception（[variant.status]）

¶1：`valueless_by_exception()` 当且仅当 variant 不持有值时返回 `true`。¶3：`index()` 在 valueless 时返回 `variant_npos`，否则返回所含值的 alternative 下标。两者都是 `constexpr noexcept`。

¶2 的注 1 说明了这种状态如何出现——**类型改变的赋值或 emplace 抛出异常**，并给出了一个反直觉的例子：即使所有 alternative 都是平凡类型，`variant<float, int>` 也能变成 valueless：

```cpp
struct S { operator int() { throw 42; } };
variant<float, int> v{12.f};
v.emplace<1>(S());     // 先销毁 float，再用 S 初始化 int —— 转换函数抛出
```

`emplace` 的规定是"先销毁旧值，再直接初始化新值"（[variant.mod]/7），抛出点在新值的初始化里，旧值已经没了。"类型安全的联合体"就这样落入一个第三种状态。

这种设计被称为"**几乎永不为空**"（[[g:never-quite-empty]]）：正常使用中 variant 总有值；只有在异常打断了类型切换的那一瞬间才可能失去值，而且失去值之后，你只能对它重新赋值/emplace、析构，或者查询它。为什么不提供"永不为空"的强保证？因为在"所含值必须嵌套在对象内"（¶1）的前提下，要做到这一点只有两条路：

1. 双缓冲——对象里预留两份存储，新值先在另一份里构造好再切换，代价是 `sizeof` 翻倍；
2. 先在临时量里构造新值，再 noexcept 地移进去——要求新类型的移动构造 `noexcept`，不是总能满足。

标准的选择是：**不强求，但在能便宜地做到时就做到**——这就是下一节赋值规则里"直接构造还是先造临时量"的判断。

### valueless 的确切成因清单

把标准里所有"*is permitted to not hold a value*"/"*will hold no value*"的位置汇总：

| 操作 | 条文 | 何时变成 valueless |
|---|---|---|
| `emplace<I>(args...)` | [variant.mod]/11、/18 | 新值初始化抛异常时**允许**（*permitted*）不持有值 |
| 转换赋值 `v = t`（类型改变） | [variant.assign]/16.2 | 走 (13.2) 直接 `emplace` 的路径且初始化抛出时允许 |
| 复制赋值（类型改变） | [variant.assign]/2.4、2.5 | (2.4) 是 `emplace`；(2.5) 先复制到临时 `variant` 再移动赋值，移动构造抛出则 valueless |
| 移动赋值（类型改变） | [variant.assign]/10.1 | `T_j` 的移动构造抛出时**一定**（*will*）不持有值 |
| `swap`（下标不同） | [variant.swap]/5 | 由 `variant` 移动构造的异常保证决定 |
| 复制/移动一个 valueless 的 variant | [variant.ctor]/7、/11 | 结果也是 valueless |

而**下标相同**的赋值（2.3、8.3、13.1）只调用 `T_j` 自己的赋值运算符，[variant.assign]/16.1 明确说此时 `valueless_by_exception()` 仍为 `false`，所含值的状态由 `T_j` 赋值的异常保证决定。

"*permitted*"的措辞给实现留了余地：如果实现能证明某个类型不会让构造中途失败（例如构造平凡），可以先在别处构造再拷贝进去，从而**永不** valueless。libstdc++ 对一部分类型做了这类优化；libc++ 没有——它的 `__emplace` 一律是"`__destroy()`（同时把下标置为 npos）→ `construct_at` → 写下标"，所以上面 `variant<float, int>` 的例子在 libc++ 上确实会变成 valueless。

## 赋值（[variant.assign]）

### 复制赋值（¶1–5）

令 `j = rhs.index()`：

- (2.1) 两边都无值 → 无效果；
- (2.2) `*this` 有值、`rhs` 无值 → 销毁 `*this` 的值，置为无值；
- (2.3) 下标相同 → 对所含值做**赋值**（`T_j` 的复制赋值）；
- (2.4) 否则，若 `is_nothrow_copy_constructible_v<T_j>` **或** `!is_nothrow_move_constructible_v<T_j>`，等价于 `emplace<j>(GET<j>(rhs))`；
- (2.5) 否则，等价于 `operator=(variant(rhs))`。

(2.4)/(2.5) 的逻辑是：

| `T_j` 复制构造 noexcept? | `T_j` 移动构造 noexcept? | 策略 | 理由 |
|---|---|---|---|
| 是 | — | 直接 `emplace` | 复制不会抛，直接造最省 |
| 否 | 否 | 直接 `emplace` | 先造临时量也救不了——之后的移动同样可能抛 |
| 否 | 是 | 先复制出临时 `variant`，再移动赋值 | 复制在**动 `*this` 之前**完成；随后的移动不抛，`*this` 不会 valueless |

¶5 Remarks：除非所有 `T_i` **既可复制构造又可复制赋值**，否则定义为删除；若所有 `T_i` 都可平凡复制构造、平凡复制赋值、平凡析构，则它是平凡的。（三者都要：赋值可能要销毁旧值、构造新值。）

### 移动赋值（¶6–10）

¶7 **Constraints**：所有 `T_i` 可移动构造且可移动赋值。效果与复制赋值平行，(8.4) 下标不同时直接 `emplace<j>(GET<j>(std::move(rhs)))`——没有"先造临时量"的分支，因为移动出来的临时量还得再移动一次，毫无收益。¶10：平凡性条件同复制赋值；异常规格是所有 `is_nothrow_move_constructible_v<T_i> && is_nothrow_move_assignable_v<T_i>` 的与；(10.1) `T_j` 移动构造抛出 → variant **将**不持有值；(10.2) `T_j` 移动赋值抛出 → 状态由 `T_j` 决定，`index()` 仍为 `j`。

### 转换赋值 `template<class T> variant& operator=(T&&)`（¶11–16）

¶11 用与转换构造**完全相同**的 *FUN* 规则选出 `T_j`（包括窄化过滤）。¶12 **Constraints**：`T` 不是 `variant` 本身；`is_assignable_v<T_j&, T> && is_constructible_v<T_j, T>`；*FUN* 重载决议成功。注 1：`variant<string, string> v; v = "abc";` 非良构。

¶13 **Effects** 是本页最值得背下来的规则：

!!! std
    Otherwise, if `is_nothrow_constructible_v<T_j, T> || !is_nothrow_move_constructible_v<T_j>` is `true`, equivalent to `emplace<j>(std::forward<T>(t))`. Otherwise, equivalent to `emplace<j>(T_j(std::forward<T>(t)))`.

    否则，若"从 `T` 构造 `T_j` 不抛"或"`T_j` 的移动构造可能抛"，等价于直接 `emplace`；否则，**先构造一个 `T_j` 临时量**，再把它移动进去。

完整的三路分支：

- (13.1) `*this` 已经持有 `T_j` → 直接 `GET<j>(*this) = std::forward<T>(t)`（调用 `T_j` 的赋值运算符，不重建对象）；
- (13.2) 构造不抛，或者移动可能抛 → `emplace<j>(std::forward<T>(t))`，就地构造；
- (13.3) 构造可能抛、但移动不抛 → `emplace<j>(T_j(std::forward<T>(t)))`：可能抛的那一步发生在销毁旧值**之前**，旧值得以保全。

这和复制赋值的 (2.4)/(2.5) 是同一个思想：**只要存在一个 noexcept 的"最后一步"，就把可能失败的工作挪到动旧值之前**。下面的例子用两个只在"移动构造是否 noexcept"上不同的类型展示两条路径：

```cpp run title="assign-strategy.cpp" ok
#include <cassert>
#include <variant>

struct Direct {                       // 移动构造可能抛异常
    Direct(const char*) { throw 1; }
    Direct(Direct&&) noexcept(false) {}
    Direct& operator=(Direct&&) = default;
};
struct ViaTemp {                      // 移动构造 noexcept
    ViaTemp(const char*) { throw 1; }
    ViaTemp(ViaTemp&&) noexcept {}
    ViaTemp& operator=(ViaTemp&&) = default;
};

int main() {
    std::variant<int, Direct> a = 42;
    try { a = "x"; } catch (int) {}              // (13.2)：直接 emplace
    assert(a.valueless_by_exception());          // 旧值已销毁，新值没造出来
    assert(a.index() == std::variant_npos);

    std::variant<int, ViaTemp> b = 42;
    try { b = "x"; } catch (int) {}              // (13.3)：先构造临时量
    assert(!b.valueless_by_exception());         // 抛出时还没碰旧值
    assert(std::get<int>(b) == 42);
}
```

（两个类型都需要能从 `const char*` 赋值，即 ¶12 的 `is_assignable_v<T_j&, T>`——这里通过"隐式构造临时量 + 移动赋值"满足。）

对最常见的 `std::string`：`is_nothrow_constructible_v<string, const char*>` 为 `false`（可能 `bad_alloc`），`is_nothrow_move_constructible_v<string>` 为 `true`，所以 `variant<int, string> v = 1; v = "hello";` 走 (13.3)：先构造临时 `string`，分配失败时 `v` 仍然持有 `1`。**对标准库常见类型，转换赋值通常是强异常安全的**；真正会让 variant 变成 valueless 的，主要是 `emplace` 和"移动构造可能抛"的类型。

¶16 异常规格：`is_nothrow_assignable_v<T_j&, T> && is_nothrow_constructible_v<T_j, T>`。

## emplace（[variant.mod]）

- `emplace<T>(args...)`（¶1–2）：**Constraints** `is_constructible_v<T, Args...>` 且 `T` **恰好出现一次**；等价于 `emplace<I>(...)`，`I` 是 `T` 的下标。`initializer_list` 版本（¶3–4）同理。
- `emplace<I>(args...)`（¶5–11）：**Mandates** `I < sizeof...(Types)`；**Constraints** `is_constructible_v<T_I, Args...>`；**Effects**：若不 valueless 则销毁当前值，然后**直接非列表初始化** `T_I`；**Postconditions** `index() == I`；**Returns** 新值的引用；¶11 初始化抛出时 variant **允许**不持有值。`initializer_list` 版本 ¶12–18 相同。

注意 `emplace<I>` 中下标越界是 *Mandates*（硬错误），而类型是否可构造是 *Constraints*。另一个细节：`emplace` **即使下标没变也会先销毁再构造**，不会调用赋值运算符——想要"同类型时赋值"的语义，请用 `operator=`。

`emplace` 没有"先造临时量"的保护：它的语义就是"就地构造"，若要先造临时量，你可以自己写 `v.emplace<I>(T_I(args...))`——这正是 (13.3) 的展开形式。

## 成员 swap（[variant.swap]）

- ¶1 **Mandates**：所有 `T_i` 可移动构造。
- ¶2 **Preconditions**：每个 `T_i` 满足 *Cpp17Swappable*（[[swappable.requirements]]）。
- ¶3 **Effects**：(3.1) 两边都 valueless → 无效果；(3.2) 下标相同 → 对所含值调用 `swap(GET<i>(*this), GET<i>(rhs))`（经 ADL 找到用户的 `swap`）；(3.3) 否则交换两者的值（包括类型）。
- ¶4/¶5：下标相同时异常与安全性由 `T_i` 的 `swap` 决定；下标不同时由 variant 移动构造的异常保证决定；异常规格是所有 `is_nothrow_move_constructible_v<T_i> && is_nothrow_swappable_v<T_i>` 的与。

注意 (3.1) 只写了"两边都 valueless"——一边 valueless、一边有值落入 (3.3)：交换后有值的一方变成 valueless，另一方得到值。

```cpp run title="variant-swap.cpp" ok
#include <cassert>
#include <string>
#include <variant>

int main() {
    std::variant<int, std::string> a = 1, b = "two";
    a.swap(b);                                   // index 不同：交换整个"值+类型"
    assert(std::get<std::string>(a) == "two" && std::get<int>(b) == 1);
    std::variant<int, std::string> c = "three";
    a.swap(c);                                   // index 相同：调用 string 的 swap
    assert(std::get<1>(a) == "three" && std::get<1>(c) == "two");
    static_assert(noexcept(a.swap(c)));
}
```

## constexpr

C++20 起（[[P2231R1]]）所有成员都是 `constexpr` 的，包括析构、赋值和 `emplace`——在常量求值中切换 variant 的 alternative 依赖于核心语言允许"在常量求值中改变联合体的活跃成员"（[[class.union]]）：

```cpp run title="variant-constexpr.cpp" ok
#include <variant>

constexpr int f() {
    std::variant<int, double> v = 1;
    v = 2.5;                       // 改变活跃 alternative
    v.emplace<0>(7);
    return std::get<0>(v) + int(v.index());
}
static_assert(f() == 7);
int main() {}
```

## libc++ 实现剖析

以下基于本地 libc++ 23 的 `<variant>`（`include/c++/v1/variant`）。

### 存储：递归联合体

```cpp
// 简化自 __variant_detail::__union
template <_Trait _DestructibleTrait, size_t _Index, class _Tp, class... _Types>
union __union<_DestructibleTrait, _Index, _Tp, _Types...> {
    char __dummy;                                         // valueless 时的活跃成员
    __alt<_Index, _Tp> __head;                            // 当前这个 alternative
    __union<_DestructibleTrait, _Index + 1, _Types...> __tail;  // 其余的，递归
};
```

`variant<A, B, C>` 的存储是 `union { A; union { B; union { C; }; }; }` 的嵌套。`get<I>` 编译期展开为 `.__tail.__tail....__head.__value` 的成员访问链（`__access::__union::__get_alt`），运行期没有任何循环。`__dummy` 供 `__union(__valueless_t)` 构造函数初始化——valueless 状态下联合体的活跃成员就是这个 `char`，不需要任何 alternative 被构造。`__union` 本身按 `_DestructibleTrait` 有三个特化，析构函数分别是 `= default`、`{}`、`= delete`。

### 下标类型

```cpp
template <size_t _NumAlternatives>
constexpr auto __choose_index_type() {
#ifdef _LIBCPP_ABI_VARIANT_INDEX_TYPE_OPTIMIZATION
  if constexpr (_NumAlternatives < numeric_limits<unsigned char>::max())
    return static_cast<unsigned char>(0);
  else if constexpr (_NumAlternatives < numeric_limits<unsigned short>::max())
    return static_cast<unsigned short>(0);
  else
#endif
    return static_cast<unsigned int>(0);
}
```

`__variant_npos<_IndexType>` 是该类型的全 1 值，所以用 `<` 而不是 `<=`：要给 npos 留一个位置。但注意那个宏：`_LIBCPP_ABI_VARIANT_INDEX_TYPE_OPTIMIZATION` 只在 **ABI v2**（`__configuration/abi.h`）中定义。默认的 ABI v1（包括 macOS 系统库和 Homebrew LLVM）下下标**总是 `unsigned int`**——在本机实测 `sizeof(std::variant<char>) == 8`、`sizeof(std::variant<int, double>) == 16`。为了 ABI 稳定，这个优化无法在 v1 中开启。

`index()` 把内部的 npos 翻译为 `size_t` 的 `variant_npos`；`valueless_by_exception()` 就是 `index() == variant_npos`。

### 特殊成员：五层条件基类

```
variant                                  // 私有继承 __sfinae_ctor_base / __sfinae_assign_base
 │  成员 __impl_ : __impl<Types...>
 └─ __impl
     └─ __copy_assignment<_Traits>      // 按 __copy_assignable_trait 三选一
         └─ __move_assignment<_Traits>
             └─ __assignment            // 公共的 __assign_alt / __generic_assign / __emplace
                 └─ __copy_constructor<_Traits>
                     └─ __move_constructor<_Traits>
                         └─ __ctor      // __generic_construct
                             └─ __dtor<_Traits>
                                 └─ __base   // __data（递归联合体）+ __index
```

注意 `variant` 自己并不继承这条阶梯：它持有一个 `__impl_` **成员**，自己的特殊成员全部 `= default`，平凡与否由这个成员的类型决定。`__traits<Types...>` 为每个特殊成员计算一个三值枚举 `_Trait { _TriviallyAvailable, _Available, _Unavailable }`（取所有 alternative 中"最差"的那个），每一层用宏 `_LIBCPP_VARIANT_*` 生成三个偏特化：`= default`、手写实现、`= delete`。注意复制赋值的 trait 是 `__common_trait({__copy_constructible_trait, is_trivially_copy_assignable...})`——同时考虑了构造与赋值，正好对应 [variant.assign]/5 的"三个都平凡才平凡"。（析构的平凡性已经由 `__dtor` 层传递。）

此外 `variant` 还私有继承 `__sfinae_ctor_base` / `__sfinae_assign_base`（`__tuple/sfinae_helpers.h`），专门负责"定义为删除"——这也是为什么在不满足条件时，Clang 的诊断会说 variant 的复制赋值运算符 "is implicitly deleted because base class `__sfinae_assign_base<...>` has a deleted copy assignment operator"。

### 转换赋值的三路分支

`__assignment::__assign_alt` 几乎是 [variant.assign]/13 的逐字翻译：

```cpp
if (this->index() == _Ip) {
  __a.__value = std::forward<_Arg>(__arg);                       // (13.1)
} else if constexpr (is_nothrow_constructible_v<_Tp, _Arg> ||
                     !is_nothrow_move_constructible_v<_Tp>) {
  this->__emplace<_Ip>(std::forward<_Arg>(__arg));               // (13.2)
} else {
  this->__emplace<_Ip>(_Tp(std::forward<_Arg>(__arg)));          // (13.3)
}
```

复制/移动赋值则统一走 `__generic_assign`，它对下标不同的情况也调用 `__assign_alt`——对复制赋值来说，`_Arg` 是 `const T_j&`，`is_nothrow_constructible_v<T_j, const T_j&>` 就是 `is_nothrow_copy_constructible_v<T_j>`，恰好重现 (2.4)/(2.5)。

### FUN 的实现

```cpp
template <class _Tp, size_t _Idx>
struct __overload {
  template <class _Up>
  auto operator()(_Tp, _Up&&) const -> __check_for_narrowing<_Tp, _Up>;
};
template <class... _Bases>
struct __all_overloads : _Bases... {
  void operator()() const;
  using _Bases::operator()...;
};
```

每个 alternative 生成一个 `__overload<T_i, i>`，用 `using ...::operator()...` 合并成一个重载集——这正是 [[variant.visit]] 中"overload 模式"的同一个技巧。第二个参数 `_Up&&` 把实参类型带进返回类型，`__check_for_narrowing` 用 `_Dest (&&)[1]` 参数 + `{std::declval<_Source>()}` 来检测窄化，失败则 SFINAE 掉该候选。libc++ 只对 `is_arithmetic<_Dest>` 的 alternative 做这个检测，因为只有算术类型（含 `bool`）的初始化可能是窄化转换。重载决议的结果 `__best_match_t` 再交给 `__find_unambiguous_index_sfinae` 求下标——重复类型时这里会 SFINAE 失败，对应 `variant<string, string> v("abc")` 不可行。

### swap 的扩展保证

`__impl::__swap` 在下标不同时用"移动到临时量 → 交叉移动构造 → 移回"三步完成，并且有一处注释为 *EXTENSION* 的逻辑：若中间一步移动构造抛出，而临时量可以 noexcept 移动，就把它移回去，提供**强异常保证**。标准只要求"由移动构造的异常保证决定"，这是 libc++ 额外给的。

## 常见误区

!!! pitfall "以为 valueless 只发生在'坏类型'上"
    注 1 的 `variant<float, int>` 例子说明：只要**新值的初始化表达式**会抛（例如转换函数、构造实参的求值过程），任何 variant 都可能 valueless。`emplace` 尤其危险：它没有"先造临时量"的路径。

!!! pitfall "`emplace` 与 `=` 对同类型的处理不同"
    `v = x` 在已持有 `T_j` 时调用 `T_j::operator=`（13.1），保留对象身份，可能复用资源（如 `string` 的缓冲区）；`v.emplace<j>(x)` 总是销毁再构造。两者对有身份语义的类型（如持有互斥量、注册了回调的对象）效果截然不同。

!!! pitfall "依赖 `variant` 选'看起来最像'的类型"
    *FUN* 是重载决议，不是"语义猜测"。`variant<std::string, std::string_view> v = "abc";`：`const char[4]` 到两者都是用户定义转换，**有歧义**，编译失败。需要明确时用 `in_place_type` 或先构造出目标类型。

## 思考题

!!! question "思考题 1"
    `std::variant<int, std::vector<int>> v = 1; v = std::vector<int>{1, 2, 3};` 会走 [variant.assign]/13 的哪一条？如果改成 `v = {1, 2, 3};` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

第一种：`T` 是 `vector<int>`（右值），*FUN* 选 `vector<int>`（精确匹配；`vector → int` 不可能）。`v` 当前持有 `int`，不走 (13.1)。`is_nothrow_constructible_v<vector<int>, vector<int>>` 即移动构造，是 `noexcept` 的，所以走 (13.2) 直接 `emplace`——移动不会抛，直接移进去即可。

第二种：`v = {1, 2, 3};` 根本**不会**调用转换赋值。花括号初始化列表没有类型，`template<class T> operator=(T&&)` 无法推导 `T`（[[temp.deduct.call]]）；剩下的候选是复制/移动赋值 `operator=(const variant&)` / `operator=(variant&&)`，它们需要从 `{1, 2, 3}` 复制列表初始化一个 `variant`。`variant` 没有 `initializer_list` 构造函数，按 [[over.match.list]]，三个元素被当作**三个实参**去匹配所有构造函数：转换构造只接受一个实参；`in_place` 构造要求第一个实参是 `in_place_type_t`/`in_place_index_t`，何况它们是 `explicit` 的。没有可行的构造函数，Clang 报告 "no viable overloaded '='"。正确写法是 `v = std::vector{1, 2, 3};` 或 `v.emplace<1>({1, 2, 3});`（`emplace` 有 `initializer_list<U>` 重载，`U` 可以推导）。
</details>

!!! question "思考题 2"
    为什么移动赋值（¶8.4）没有像复制赋值（¶2.5）那样的"先构造临时量"分支？

<details markdown="1">
<summary>展开查看答案与解析</summary>

先构造临时量的意义在于把"可能抛"的操作挪到销毁旧值之前，然后用一个**不抛**的移动完成最后一步。对移动赋值来说，构造临时量本身就是一次 `T_j` 的移动构造；若它可能抛，那么最后把临时量移进去的那一步同样是一次可能抛的移动构造，没有任何收益；若它不抛，那么直接 `emplace` 也不会抛。两种情况下"先造临时量"都没有意义，所以标准直接写 `emplace<j>(GET<j>(std::move(rhs)))`，并在 (10.1) 承认移动构造抛出时 variant **将**不持有值。
</details>

!!! question "思考题 3"
    `std::variant<bool, std::string> v = std::string_view("x");` 在 C++17 原规则、P0608R3 原始版本、当前草案下分别是什么结果？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`string_view` 到 `bool` 没有任何隐式转换（`string_view` 没有 `operator bool`），到 `string` 只有 `explicit` 构造函数，复制初始化不可用。三个版本下 *FUN*(`bool`) 与 *FUN*(`string`) 都不可行，重载决议失败，转换构造被约束排除——编译错误。这个例子说明 *FUN* 规则是"隐式转换"语义：`explicit` 构造函数永远不会被 *FUN* 选中（`T_i x[] = {...}` 也是复制初始化）。要存入，需写 `v.emplace<1>(sv)` 或 `variant<bool, string>(in_place_index<1>, sv)`——`in_place` 和 `emplace` 是直接初始化，可以使用 `explicit` 构造函数。
</details>

## 小结

| 成员 | 关键契约 |
|---|---|
| 默认构造 | Constraints：`T_0` 可默认构造；`index() == 0` |
| 复制构造 | 非全部可复制则**删除**；全部平凡则平凡 |
| 移动构造 | Constraints：全部可移动；全部平凡则平凡；noexcept 取与 |
| 转换构造 / 转换赋值 | *FUN* 重载决议 + `T_i x[] = {t}` 剔除窄化；歧义或无候选则不参与重载决议 |
| `in_place_type` / `in_place_index` | `explicit`；直接初始化；`in_place_type<T>` 要求 `T` 恰好出现一次（Constraints） |
| 析构 | 全部平凡析构则平凡 |
| 复制赋值 | 删除除非全部可复制构造+可复制赋值；下标不同时：复制 noexcept 或移动非 noexcept → `emplace`，否则先造临时量 |
| 移动赋值 | Constraints；下标不同时 `emplace`；移动构造抛出 → valueless |
| 转换赋值 | 同下标：赋值；构造 noexcept 或移动非 noexcept → `emplace`；否则 `emplace<j>(T_j(t))` |
| `emplace<I>` / `emplace<T>` | 先销毁再构造；抛出时**允许** valueless；`I` 越界 Mandates，`T` 唯一 Constraints |
| `valueless_by_exception` / `index` | 无值 ⇔ `index() == variant_npos` |
| 成员 `swap` | Mandates 可移动构造；同下标调用 `swap`，否则交换值 |
