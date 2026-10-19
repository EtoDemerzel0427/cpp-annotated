---
title: 类模板 variant
summary: variant 的构造、析构、赋值、emplace、swap 与状态查询，包括转换构造怎样挑选类型、何时会变成 valueless、特殊成员何时平凡。
status: done
covers: *
papers: P0088R3, P0608R3, P1957R2, P0602R4, P0848R3, P2231R1
related: variant, variant.visit, class.union, special, class.dtor, class.prop, dcl.init.list, dcl.init.aggr, over.match.best, over.ics.rank, structure.specifications, optional.optional, expected.expected
tags: 标准库, variant, 异常安全, 重载决议, 平凡性
updated: 2026-10-19
---

!!! tldr
    - `variant<Ts...>` 在对象内部用一块联合体存储加一个下标保存当前值，标准不允许把值放到堆上。
    - `variant<std::string, bool> v = "abc";` 选 `string`：转换构造对每个候选类型做一次重载决议，并且先剔除会造成窄化的候选（C++20 起）。
    - 改变类型的 `emplace` 或赋值如果在构造新值时抛出异常，variant 可能不再持有任何值，这时 `valueless_by_exception()` 为真，`index()` 返回 `variant_npos`。
    - 赋值在构造可能抛出而移动不会抛出时，先在旁边构造一个临时值，从而保住旧值；`emplace` 没有这层保护。
    - 所有候选类型的某个特殊成员都平凡时，variant 的对应成员也平凡，所以 `variant<int, double>` 是可平凡复制的类型。

取值、比较和哈希见 [[variant]]，`std::visit` 见 [[variant.visit]]。

## 一个联合体加一个下标

`variant<int, std::string>` 在内存里大致是这样：

```cpp
struct variant_int_string {
  union { int i; std::string s; } storage;  // 同一时刻只有一个活跃成员
  unsigned index;                           // 0、1，或表示无值的特殊值
};
```

variant 的各个类型参数叫作它的**候选类型**（alternative）。所有成员函数做的事都可以归结为：根据下标知道联合体里哪个成员活着，切换类型时结束旧成员的生命周期、开始新成员的生命周期（[[basic.life]]）。

难点在切换这一步。先销毁旧值再构造新值，如果构造抛出异常，联合体里就什么也没有了。后面讲的 valueless 状态和赋值时的种种分支，都是在处理这个问题。

¶1 标准把这个模型写成两句话：任一时刻 variant 要么持有某个候选类型的值，要么不持有值；持有值时，这个值叫作**所含值**（contained value），它嵌套在 variant 对象之内（[[intro.object]]）。

嵌套在对象之内意味着不能堆分配。Boost.Variant 在异常时会把备份放到堆上，`std::variant` 不允许这样做，这一点决定了后面所有异常安全上的取舍。

### 对候选类型的要求

¶2 每个候选类型都必须满足 *Cpp17Destructible*（[[utility.arg.requirements]]）。按那张表下面的注，数组类型和非对象类型（引用、`void`、函数）都不满足，所以 `variant<int&>`、`variant<int[3]>`、`variant<void>` 都不允许。

这是对程序的要求，标准没有要求诊断，但实现都会直接报错。libc++ 在类体里用 `static_assert` 给出 "variant can not have a reference type as an alternative" 之类的消息。

¶3 实例化没有模板实参的 `variant<>` 的定义是非良构的。只是提到 `variant<>`，在不需要完整类型的地方不会出错。

## 构造（[variant.ctor]）

¶1 下文用 `T_i` 表示 `Types` 中第 `i` 个类型。

### 默认构造

¶2 默认构造只看第一个候选类型：约束是 `T_0` 可默认构造，效果是值初始化一个 `T_0`，之后 `index() == 0`。它是否 `constexpr`、是否 `noexcept`，也都取决于 `T_0` 的值初始化。

第一个类型不能默认构造时，惯用法是在最前面放一个 `std::monostate`（[[variant]]）：`variant<std::monostate, Socket, File>` 默认构造时持有 `monostate`。

### 复制、移动与平凡性

¶7 复制构造用源对象的所含值直接初始化同一个候选类型；源对象是 valueless 时，新对象也是 valueless。移动构造（¶11）同理。

¶9 只要有一个 `T_i` 不可复制构造，复制构造就定义为删除。¶10 移动构造则写成约束：所有 `T_i` 可移动构造时它才参与重载决议。这个区别让 variant 的行为和普通的类一致：没有可用的移动构造时，`variant(std::move(x))` 退回到复制构造。

第 9、13 段还规定，所有 `T_i` 的复制（移动）构造都平凡时，variant 的复制（移动）构造也平凡；[variant.dtor]/2 对析构函数作了同样的规定。

```cpp run title="variant-triviality.cpp" ok
#include <string>
#include <type_traits>
#include <variant>

using V1 = std::variant<int, double, char>;
static_assert(std::is_trivially_copyable_v<V1>);
static_assert(std::is_trivially_destructible_v<V1>);

using V2 = std::variant<int, std::string>;
static_assert(!std::is_trivially_copyable_v<V2>);
static_assert(std::is_copy_constructible_v<V2>);

struct MoveOnly { MoveOnly(MoveOnly&&) = default; };
using V3 = std::variant<int, MoveOnly>;
static_assert(!std::is_copy_constructible_v<V3>);  // ¶9：删除
static_assert(std::is_move_constructible_v<V3>);

int main() {}
```

平凡性有实际后果：它决定类型是否可平凡复制（[[g:trivially-copyable-type]]），进而决定能否 `memcpy`、能否在寄存器里传参。Itanium C++ ABI 规定，复制构造或析构不平凡的类型按值传参时必须经过内存。C++17 最初的规格没有这些平凡性要求，[[P0602R4]] 补上了它们。

!!! impl "库怎样实现条件平凡"
    C++17 的语言无法直接表达"这个特殊成员在某条件下是 `= default`，否则是手写的"。实现只能用一串条件基类：每层基类按类型特征选择 `= default`、手写或 `= delete` 三种偏特化之一，最外层的类自己的特殊成员全部 `= default`，平凡性就从基类传上来。

    C++20 的 [[P0848R3]] 允许一个类声明多个带 requires 子句的预期特殊成员，由约束选出合格的那个（[[g:eligible-special-member-function]]），于是可以直接写：

    ```cpp
    ~variant() requires (std::is_trivially_destructible_v<Ts> && ...) = default;
    ~variant() { /* 按下标销毁 */ }
    ```

    libc++ 为了兼容 C++17 模式，仍然使用基类阶梯，见下文实现一节。

### 转换构造：选哪个候选类型

`template<class T> variant(T&&)` 接受任意实参，要自动选出存放它的候选类型。下面几行在当前标准下的结果，C++17 时并不都是这样：

```cpp run title="p0608.cpp" ok
#include <cassert>
#include <string>
#include <variant>

int main() {
  std::variant<std::string, bool> a = "abc";
  assert(a.index() == 0);  // string；C++17 原规则选 bool

  std::variant<std::string, bool> b = true;
  assert(b.index() == 1);  // 真正的 bool 仍然选 bool

  std::variant<float, long> c = 0;
  assert(c.index() == 1);  // int→float 是窄化，float 被剔除

  std::variant<int, long> d = 0u;  // unsigned→int 窄化
  assert(d.index() == 1);          // LP64 上 unsigned→long 不窄化
}
```

¶14 规则是这样的。对每个候选类型 `T_i` 想象一个单参数函数 *FUN*(`T_i`)（[[g:imaginary-function-fun]]），然后对表达式 *FUN*(`std::forward<T>(t)`) 做普通的重载决议（[[over.match.best]]），选中的那个 *FUN*(`T_j`) 就决定了所含值的类型 `T_j`。但只有满足下面条件的 `T_i` 才会有对应的 *FUN*：

!!! std
    build an imaginary function *FUN*(`T_i`) for each alternative type `T_i` for which `T_i x[] = {std::forward<T>(t)};` is well-formed for some invented variable `x`.

`T_i x[] = {e};` 是对数组的列表初始化，元素从 `e` 复制初始化；如果这一步需要窄化转换（[[g:narrowing-conversion]]），程序就非良构（[[dcl.init.list]]）。所以这个条件的作用是：会造成窄化的候选类型不参加重载决议。剩下的候选之间，仍按隐式转换序列的优劣（[[over.ics.rank]]）比较，两个一样好就是歧义。

被检查的是 `std::forward<T>(t)`，不是调用处写的字面量。它不是常量表达式，所以"常量的值能被精确表示就不算窄化"这条豁免用不上：`int` 到 `float` 一律算窄化，哪怕实参写的是 `0`。

¶15 下面这些条件全部是约束，任何一条不满足，这个构造函数就从重载集中消失，`is_convertible_v<X, variant<...>>` 如实报告 `false`：

- 实参类型去掉 cv 和引用后不是 variant 本身，也不是 `in_place_type_t`、`in_place_index_t` 的特化；
- `is_constructible_v<T_j, T>` 为真；
- *FUN* 的重载决议成功并且没有歧义。

¶16 选定 `T_j` 之后，所含值用 `std::forward<T>(t)` 直接初始化，不带花括号。*FUN* 只负责选类型，真正的初始化不做窄化检查。这个构造函数不是 `explicit` 的，`variant<int, std::string> v = "x";` 用的就是它。

窄化过滤也会把一些以前能编译的代码变成错误：

<div class="compare" markdown="1">

```cpp error
#include <string>
#include <variant>
// double→int 窄化，int 被剔除；
// double 也不能隐式转成 string
std::variant<int, std::string> v
    = 3.14;  // error
```

```cpp error
#include <variant>
// int→float、int→double
// 都是窄化，没有候选
std::variant<float, double> w
    = 0;  // error
```

</div>

在 C++17 的规则下，左边会悄悄把 `3.14` 截断成 `3` 存进 `int`，右边是歧义。¶15 的注 2 给出的 `variant<string, string> v("abc");` 在任何版本下都非良构：两个 *FUN*(`string`) 一样好。

`unsigned` 到 `long` 是否窄化，取决于 `long` 能否表示 `unsigned` 的所有值。在 LP64（Linux、macOS）上 `long` 是 64 位，上面的 `d` 选 `long`；在 LLP64（Windows）上 `long` 只有 32 位，两个候选都被剔除，同一行代码编译失败。

!!! history "从 C++17 到当前规则"
    C++17 的 [[P0088R3]] 只有 *FUN* 重载决议，没有窄化过滤，因而有两个著名的问题：`variant<std::string, bool> v = "abc";` 选中 `bool`，因为 `const char*` 到 `bool` 是标准转换，比到 `string` 的用户定义转换更好；`variant<float, long> v = 0;` 有歧义，因为两个转换等级相同。

    C++20 的 [[P0608R3]] 加入了数组初始化的过滤，当时还附带一条 `bool` 的特殊规则：只有实参本身是 `bool` 时才考虑 `bool` 候选。随后 [[P1957R2]] 在核心语言里把指针和成员指针到 `bool` 的转换定为窄化转换，窄化过滤就能挡掉 `const char*` 到 `bool`，那条特例随之删除。当前草案的 ¶14 只剩数组初始化这一个条件。

!!! lawyer "*FUN* 的重载决议和普通函数完全一样"
    标准不要求实现真的声明这些函数，只要求结果和对这样一组函数做重载决议相同。所以重载决议的全部细节都适用。例如 `variant<Base, Derived>` 用 `MoreDerived` 对象初始化会选 `Derived`：两个候选都是派生类到基类的转换，转换到更近的基类更好（[[over.ics.rank]]）。

### 用 `in_place` 指定候选类型

¶20 另外四个构造函数用标签直接指明要构造哪个候选类型，全部是 `explicit` 的：

| 形式 | 约束 | 构造后 |
|---|---|---|
| `variant(in_place_type_t<T>, Args&&...)`（¶20–24） | `T` 在 `Types` 中恰好出现一次；`is_constructible_v<T, Args...>` | `holds_alternative<T>(*this)` |
| `variant(in_place_type_t<T>, initializer_list<U>, Args&&...)`（¶25–29） | 同上，`initializer_list<U>&` 在前 | 同上 |
| `variant(in_place_index_t<I>, Args&&...)`（¶30–34） | `I < sizeof...(Types)`；`is_constructible_v<T_I, Args...>` | `index() == I` |
| `variant(in_place_index_t<I>, initializer_list<U>, Args&&...)`（¶35–39） | 同上 | `index() == I` |

它们都是直接非列表初始化，不经过 *FUN*，所以 `variant<int, std::string>(std::in_place_index<0>, 3.14)` 合法，存入 `3`。确实想要窄化或想用 `explicit` 构造函数时，`in_place` 是明确表态的写法。

同一个类型出现两次时，只能用下标区分：

```cpp run title="duplicate-types.cpp" ok
#include <cassert>
#include <string>
#include <variant>

// 两个 string 分别表示用户名和错误信息
using Result = std::variant<std::string, std::string>;

int main() {
  Result r(std::in_place_index<1>, "file not found");
  assert(r.index() == 1);
  r.emplace<0>("alice");  // 按下标 emplace：OK
  assert(std::get<0>(r) == "alice");
  // r.emplace<std::string>("bob");  // error: string 出现两次
  // r = "bob";                      // error: FUN 有歧义
}
```

## valueless：variant 失去值的时候（[variant.status]）

```cpp run title="valueless.cpp" ok
#include <cassert>
#include <variant>

struct S { operator int() { throw 42; } };

int main() {
  std::variant<float, int> v{12.f};
  try { v.emplace<1>(S()); } catch (int) {}
  assert(v.valueless_by_exception());
  assert(v.index() == std::variant_npos);
}
```

这是 [variant.status] 第 2 段注 1 里的例子。两个候选类型都是平凡类型，variant 照样失去了值：`emplace` 先销毁旧的 `float`，再用 `S()` 初始化 `int`（[variant.mod]/7），转换函数在这时抛出异常，旧值已经没了，新值没造出来。

¶1 `valueless_by_exception()` 在 variant 不持有值时返回 `true`。¶3 `index()` 这时返回 `variant_npos`，否则返回所含值的候选类型下标。两者都是 `constexpr noexcept`。

这种设计叫作**几乎永不为空**（[[g:never-quite-empty]]）：正常使用时 variant 总有值，只有异常打断了类型切换时才可能失去值。失去值之后，只能对它重新赋值或 `emplace`、析构，或者查询状态；`get` 和 `visit` 会抛 `bad_variant_access`。

为什么不保证永不为空？所含值必须放在对象内部，要做到永不为空只有两条路：

1. 双缓冲：对象里留两份存储，新值在另一份里构造好再切换，代价是体积翻倍；
2. 先在临时量里构造新值，再不抛异常地移进去：要求新类型的移动构造不抛出，不是总能满足。

标准的选择是不强求，但在代价小的时候做到。下一节赋值的分支规则就是这样设计的。

### 哪些操作会让 variant 失去值

| 操作 | 条文 | 什么时候失去值 |
|---|---|---|
| `emplace` | [variant.mod]/11、/18 | 新值初始化抛出时，允许不持有值 |
| 转换赋值（类型改变） | [variant.assign]/16.2 | 走直接 `emplace` 的分支且初始化抛出时，允许不持有值 |
| 复制赋值（类型改变） | [variant.assign]/2.4、2.5 | 2.4 就是 `emplace`；2.5 先复制到临时 variant，再移动赋值 |
| 移动赋值（类型改变） | [variant.assign]/10.1 | `T_j` 的移动构造抛出时，一定不持有值 |
| `swap`（下标不同） | [variant.swap]/5 | 取决于 variant 移动构造的异常保证 |
| 复制或移动一个 valueless 的 variant | [variant.ctor]/7、/11 | 结果也是 valueless |

下标相同的赋值只调用 `T_j` 自己的赋值运算符，[variant.assign]/16.1 明确说这时 `valueless_by_exception()` 仍为 `false`。

允许不持有值的措辞给实现留了余地：如果实现知道某个类型的构造不会中途失败，可以先在别处构造再复制进去，从而永不失去值。libstdc++ 对一部分类型这样做；libc++ 不做，它的 `emplace` 一律是先销毁（同时把下标置为无值），再构造，最后写下标，所以上面的例子在 libc++ 上确实失去了值。

## 赋值（[variant.assign]）

三种赋值的思路相同：下标相同时调用所含值自己的赋值运算符；下标不同时要切换类型，并且只要存在一个不会抛出的最后一步，就把可能失败的工作挪到销毁旧值之前。

### 转换赋值

¶11 `template<class T> variant& operator=(T&&)` 用和转换构造完全相同的 *FUN* 规则选出 `T_j`，包括窄化过滤。¶12 的约束是：`T` 不是 variant 本身，`T_j` 既能从 `T` 赋值也能从 `T` 构造，并且 *FUN* 的重载决议成功。

¶13 效果分三种情况：

- (13.1) `*this` 已经持有 `T_j`：直接把 `std::forward<T>(t)` 赋给所含值，不重建对象；
- (13.2) 从 `T` 构造 `T_j` 不会抛出，或者 `T_j` 的移动构造可能抛出：等价于 `emplace<j>(std::forward<T>(t))`，就地构造；
- (13.3) 其他情况，即构造可能抛出、移动不会抛出：等价于 `emplace<j>(T_j(std::forward<T>(t)))`，先构造一个临时量，再移进去。

13.3 的临时量在销毁旧值之前构造，抛出异常时旧值还在。13.2 的第二种情况看起来奇怪，其实是因为先造临时量也没用：之后的移动同样可能抛出。

```cpp run title="assign-strategy.cpp" ok
#include <cassert>
#include <variant>

struct Direct {  // 移动构造可能抛出
  Direct(const char*) { throw 1; }
  Direct(Direct&&) noexcept(false) {}
  Direct& operator=(Direct&&) = default;
};
struct ViaTemp {  // 移动构造不抛出
  ViaTemp(const char*) { throw 1; }
  ViaTemp(ViaTemp&&) noexcept {}
  ViaTemp& operator=(ViaTemp&&) = default;
};

int main() {
  std::variant<int, Direct> a = 42;
  try { a = "x"; } catch (int) {}  // 13.2：直接 emplace
  assert(a.valueless_by_exception());

  std::variant<int, ViaTemp> b = 42;
  try { b = "x"; } catch (int) {}  // 13.3：先造临时量
  assert(!b.valueless_by_exception());
  assert(std::get<int>(b) == 42);
}
```

两个类型都要能从 `const char*` 赋值，才满足 ¶12 的 `is_assignable_v<T_j&, T>`。这里靠隐式构造一个临时量再移动赋值做到。

最常见的 `std::string` 走 13.3：从 `const char*` 构造可能抛 `bad_alloc`，移动构造不抛。所以 `variant<int, std::string> v = 1; v = "hello";` 在分配失败时 `v` 仍然持有 `1`。对标准库的常见类型，转换赋值通常有强异常保证；真正容易让 variant 失去值的，是 `emplace` 和移动构造可能抛出的类型。

¶16 转换赋值的异常规格是 `is_nothrow_assignable_v<T_j&, T> && is_nothrow_constructible_v<T_j, T>`。

### 复制赋值

¶2 设 `j = rhs.index()`：

- (2.1) 两边都没有值：什么也不做；
- (2.2) `*this` 有值、`rhs` 没有值：销毁 `*this` 的值，使它不持有值；
- (2.3) 下标相同：调用 `T_j` 的复制赋值；
- (2.4) 如果 `T_j` 的复制构造不抛出，或者 `T_j` 的移动构造可能抛出：等价于 `emplace<j>(GET<j>(rhs))`；
- (2.5) 否则：等价于 `operator=(variant(rhs))`，先复制出一个临时 variant，再移动赋值。

2.4 和 2.5 的分法与转换赋值的 13.2、13.3 完全对应：复制在动 `*this` 之前完成，随后的移动不会抛出，`*this` 就不会失去值。

¶5 只要有一个 `T_i` 不同时满足可复制构造和可复制赋值，复制赋值就定义为删除。所有 `T_i` 的复制构造、复制赋值和析构都平凡时，它是平凡的。三者都要求平凡，因为切换类型时要销毁旧值、构造新值。

### 移动赋值

¶7 移动赋值的约束是所有 `T_i` 可移动构造且可移动赋值。前三种情况与复制赋值平行，下标不同时（8.4）直接 `emplace<j>(GET<j>(std::move(rhs)))`，没有先造临时量的分支（理由见思考题 2）。

¶10 它的平凡性条件与复制赋值相同，异常规格是所有 `T_i` 的 `is_nothrow_move_constructible_v && is_nothrow_move_assignable_v` 的逻辑与。如果 `T_j` 的移动构造抛出，variant 一定不持有值（10.1）；如果移动赋值抛出，所含值的状态由 `T_j` 决定，`index()` 仍是 `j`（10.2）。

## emplace（[variant.mod]）

¶7 `emplace<I>(args...)` 先销毁当前值（如果有），再用 `args...` 直接非列表初始化一个 `T_I`，返回新值的引用。如果初始化抛出异常，variant 允许不持有值（第 11 段）。

¶1 `emplace<T>` 要求 `T` 在 `Types` 中恰好出现一次，然后转给 `emplace<I>`。两者各有一个 `initializer_list` 版本（第 3、12 段）。

几个细节：

- 下标越界是 *Mandates*（第 5 段），直接编译错误；能否构造是 *Constraints*（第 6 段），不满足时不参与重载决议（[[structure.specifications]]）。
- 即使下标没变，`emplace` 也是先销毁再构造，不调用赋值运算符。想要同类型时赋值的语义，用 `operator=`。
- `emplace` 没有先造临时量的保护，它的语义就是就地构造。需要保护时可以自己写 `v.emplace<I>(T_I(args...))`，这正是 13.3 的展开形式。

## swap（[variant.swap]）

¶1 成员 `swap` 要求（*Mandates*）所有 `T_i` 可移动构造，前提（第 2 段）是每个 `T_i` 满足 *Cpp17Swappable*（[[swappable.requirements]]）。

¶3 效果分三种：两边都 valueless 时什么也不做；下标相同时调用 `swap(GET<i>(*this), GET<i>(rhs))`，可以经 ADL 找到用户自定义的 `swap`；否则交换两者的值，类型也一起交换。

一边 valueless、一边有值的情况落入第三种：交换之后有值的一方变成 valueless，另一方得到值。

```cpp run title="variant-swap.cpp" ok
#include <cassert>
#include <string>
#include <variant>

int main() {
  std::variant<int, std::string> a = 1, b = "two";
  a.swap(b);  // 下标不同：连同类型一起交换
  assert(std::get<std::string>(a) == "two");
  assert(std::get<int>(b) == 1);

  std::variant<int, std::string> c = "three";
  a.swap(c);  // 下标相同：调用 string 的 swap
  assert(std::get<1>(a) == "three" && std::get<1>(c) == "two");
  static_assert(noexcept(a.swap(c)));
}
```

¶5 异常规格是所有 `T_i` 的 `is_nothrow_move_constructible_v && is_nothrow_swappable_v` 的逻辑与。

## 常量求值中的 variant

所有成员都是 `constexpr` 的，包括析构、赋值和 `emplace`。这要依靠核心语言允许在常量求值中改变联合体的活跃成员（[[class.union]]）。最初的 C++20 只有部分成员是 `constexpr`，[[P2231R1]] 补全了其余部分，各实现把它当作对 C++20 的修正。

```cpp run title="variant-constexpr.cpp" ok
#include <variant>

constexpr int f() {
  std::variant<int, double> v = 1;
  v = 2.5;  // 改变活跃的候选类型
  v.emplace<0>(7);
  return std::get<0>(v) + int(v.index());
}
static_assert(f() == 7);
int main() {}
```

## libc++ 的实现

以下基于本机 libc++ 23 的 `<variant>`。

### 存储：递归的联合体

```cpp
// 简化自 __variant_detail::__union
template <_Trait _DestructibleTrait, size_t _Index, class _Tp, class... _Types>
union __union<_DestructibleTrait, _Index, _Tp, _Types...> {
  char __dummy;                    // valueless 时的活跃成员
  __alt<_Index, _Tp> __head;       // 当前这个候选类型
  __union<_DestructibleTrait, _Index + 1, _Types...> __tail;  // 其余的
};
```

`variant<A, B, C>` 的存储是 `union { A; union { B; union { C; }; }; }` 这样的嵌套。`get<I>` 在编译期展开成 `.__tail.__tail.__head` 这样的成员访问链，运行时没有循环。valueless 时联合体的活跃成员是 `__dummy`，不需要构造任何候选类型。

### 下标的类型

libc++ 有一个按候选类型数量选用 `unsigned char`、`unsigned short` 的优化，但它受宏 `_LIBCPP_ABI_VARIANT_INDEX_TYPE_OPTIMIZATION` 控制，只在 ABI v2 中开启。默认的 ABI v1（包括 macOS 系统库和 Homebrew LLVM）中下标总是 `unsigned int`，为了 ABI 稳定无法更改。本机实测 `sizeof(std::variant<char>) == 8`，`sizeof(std::variant<int, double>) == 16`。

内部的无值标记是下标类型的全 1 值，`index()` 把它翻译成 `size_t` 的 `variant_npos`。

### 特殊成员：条件基类阶梯

`variant` 持有一个 `__impl<Types...>` 类型的成员 `__impl_`，自己的特殊成员全部 `= default`，平凡与否由这个成员的类型决定。`__impl` 往下是一串基类：`__copy_assignment`、`__move_assignment`、`__copy_constructor`、`__move_constructor`、`__dtor`，最底层的 `__base` 持有递归联合体和下标。

每层基类按一个三值枚举（平凡可用、可用、不可用）选择 `= default`、手写实现或 `= delete` 三种偏特化之一，枚举值取所有候选类型中最差的那个。复制赋值那一层同时考虑复制构造与复制赋值的平凡性，正好对应 [variant.assign]/5。`variant` 另外私有继承 `__sfinae_ctor_base` 和 `__sfinae_assign_base`，专门负责定义为删除的情况。

### 转换赋值与 FUN

`__assign_alt` 几乎是 [variant.assign]/13 的逐字翻译：

```cpp
if (this->index() == _Ip) {
  __a.__value = std::forward<_Arg>(__arg);                  // 13.1
} else if constexpr (is_nothrow_constructible_v<_Tp, _Arg> ||
                     !is_nothrow_move_constructible_v<_Tp>) {
  this->__emplace<_Ip>(std::forward<_Arg>(__arg));          // 13.2
} else {
  this->__emplace<_Ip>(_Tp(std::forward<_Arg>(__arg)));     // 13.3
}
```

复制赋值也调用它，这时 `_Arg` 是 `const T_j&`，`is_nothrow_constructible_v<T_j, const T_j&>` 就是复制构造是否不抛出，恰好重现 2.4 和 2.5。

*FUN* 的实现是每个候选类型生成一个 `__overload<T_i, i>`，再用 `using _Bases::operator()...;` 合并成一个重载集，与 [[variant.visit]] 中 overload 模式的技巧相同。窄化检查放在返回类型里，失败时用 SFINAE 去掉该候选。libc++ 只对算术类型的候选做这项检查，因为只有到算术类型（包括 `bool`）的转换可能是窄化转换。

### swap 的额外保证

下标不同时，`swap` 先把一方移动到临时量，再交叉移动构造，最后移回。源码里有一处标为 EXTENSION 的逻辑：如果中间一步移动构造抛出，而临时量可以不抛出地移动，就把它移回去，从而提供强异常保证。标准只要求取决于移动构造的异常保证，这是 libc++ 额外给的。

## 常见误解

!!! pitfall "以为只有特殊的类型才会让 variant 失去值"
    注 1 的 `variant<float, int>` 说明，只要新值的初始化过程会抛出异常（例如转换函数、构造实参的求值），任何 variant 都可能失去值。`emplace` 尤其如此，它没有先造临时量的路径。

!!! pitfall "以为 `emplace` 和 `=` 对同类型的处理相同"
    `v = x` 在已持有 `T_j` 时调用 `T_j::operator=`（13.1），保留对象身份，还可能复用资源，例如 `string` 的缓冲区。`v.emplace<j>(x)` 总是销毁再构造。对注册了回调或持有互斥量这类有身份的对象，两者效果完全不同。

!!! pitfall "以为 variant 会选看起来最像的类型"
    *FUN* 是重载决议，不会猜测意图。`variant<std::string, std::string_view> v = "abc";` 中，`const char[4]` 到两者都是用户定义转换，有歧义，编译失败。需要明确时用 `in_place_type`，或者先构造出目标类型。

## 思考题

!!! question "思考题 1"
    `std::variant<int, std::vector<int>> v = 1; v = std::vector<int>{1, 2, 3};` 会走 [variant.assign]/13 的哪一种情况？改成 `v = {1, 2, 3};` 呢？

<details markdown="1">
<summary>答案</summary>

第一种：*FUN* 选中 `vector<int>`（`vector` 不能转换为 `int`）。`v` 当前持有 `int`，不是 13.1。从 `vector<int>` 右值构造 `vector<int>` 就是移动构造，不会抛出，所以走 13.2，直接 `emplace`。

第二种根本不会调用转换赋值。花括号初始化列表没有类型，`template<class T> operator=(T&&)` 推导不出 `T`（[[temp.deduct.call]]）。剩下的候选是复制赋值和移动赋值，它们需要从 `{1, 2, 3}` 复制列表初始化一个 variant。variant 没有 `initializer_list` 构造函数，按 [[over.match.list]]，三个元素被当作三个实参去匹配所有构造函数：转换构造只接受一个实参，`in_place` 构造要求第一个实参是标签而且是 `explicit` 的。没有可行的构造函数，Clang 报告 "no viable overloaded '='"。正确写法是 `v = std::vector{1, 2, 3};` 或 `v.emplace<1>({1, 2, 3});`。
</details>

!!! question "思考题 2"
    为什么移动赋值（8.4）没有像复制赋值（2.5）那样先构造临时量的分支？

<details markdown="1">
<summary>答案</summary>

先构造临时量的意义，是把可能抛出的操作挪到销毁旧值之前，再用一次不抛出的移动完成最后一步。对移动赋值来说，构造临时量本身就是一次 `T_j` 的移动构造。如果它可能抛出，最后把临时量移进去同样可能抛出，没有收益；如果它不抛出，直接 `emplace` 也不会抛出。两种情况下临时量都没有意义，所以标准直接写 `emplace<j>(GET<j>(std::move(rhs)))`，并在 10.1 规定移动构造抛出时 variant 一定不持有值。
</details>

!!! question "思考题 3"
    `std::variant<bool, std::string> v = std::string_view("x");` 能编译吗？

<details markdown="1">
<summary>答案</summary>

不能，在 C++17 和当前规则下都不能。`string_view` 到 `bool` 没有隐式转换，到 `string` 只有 `explicit` 构造函数，复制初始化用不上它。*FUN*(`bool`) 和 *FUN*(`string`) 都不可行，转换构造被约束排除。可见 *FUN* 只考虑隐式转换，`explicit` 构造函数永远不会被它选中。要存入，写 `v.emplace<1>(sv)` 或 `variant<bool, std::string>(std::in_place_index<1>, sv)`，它们是直接初始化，可以使用 `explicit` 构造函数。
</details>

## 小结

| 成员 | 要点 |
|---|---|
| 默认构造 | 约束 `T_0` 可默认构造；`index() == 0` |
| 复制构造 | 有一个不可复制就删除；全部平凡则平凡 |
| 移动构造 | 约束全部可移动；全部平凡则平凡 |
| 转换构造、转换赋值 | *FUN* 重载决议，先剔除会窄化的候选；歧义或无候选时不参与重载决议 |
| `in_place_type`、`in_place_index` | `explicit`，直接初始化；`in_place_type<T>` 要求 `T` 只出现一次 |
| 复制赋值、转换赋值 | 下标相同时赋值；构造可能抛出而移动不抛出时先造临时量，否则直接 `emplace` |
| 移动赋值 | 下标不同时直接 `emplace`；移动构造抛出则失去值 |
| `emplace` | 先销毁再构造；抛出时允许失去值 |
| `valueless_by_exception`、`index` | 无值时 `index() == variant_npos` |
| `swap` | 下标相同时交换所含值，否则连类型一起交换 |

<details class="fine" markdown="1"><summary>其余条文</summary>

[variant.variant.general]/4：程序为 `variant` 声明显式特化或偏特化，属于非良构、不要求诊断。这比一般的标准库模板更严，后者在满足条件时允许用户特化（[[namespace.std]]）。

[variant.ctor] 中各构造函数的 *Throws* 元素（¶5、¶8、¶12、¶18 等）都只说抛出所含值初始化时抛出的异常；*Postconditions* 元素说明构造后 `index()` 或 `holds_alternative` 的值，正文已经涉及。

[variant.assign]/3、/9、/14、/15 是复制赋值的后置条件 `index() == rhs.index()` 和各赋值运算符返回 `*this`。

[variant.mod]/8–10 说明 `emplace` 之后 `index() == I`、返回新值的引用、抛出初始化时抛出的异常。

</details>
