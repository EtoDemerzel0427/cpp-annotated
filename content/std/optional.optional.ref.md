---
title: optional 的引用偏特化
summary: C++26 的 optional<T&>：本质是一个可空的 T*；赋值永远是改绑而不是写穿；凡是会绑定到临时量的构造一律弃置（reference_constructs_from_temporary）；浅 const、平凡可复制、borrowed range；value_or 按值返回；以及它为何拖了十年才进入标准
status: draft
covers: *
papers: P2988, P3168
related: optional, optional.optional, meta.rel, dcl.init.ref, class.temporary, class.prop, basic.life, tuple, pairs
tags: 标准库, optional, 引用, C++26, 悬垂引用
updated: 2026-10-18
---

`optional<T&>` 是 C++26 加入的偏特化（[[P2988]]），回答一个看似简单、实则吵了十多年的问题："一个**也许存在的引用**"应该是什么？

在它之前，表达"可选的引用"只有两条路：裸指针 `T*`（语义含糊——谁拥有？能不能是数组？能不能做算术？）和 `std::optional<std::reference_wrapper<T>>`（语法笨重，`opt->get().member`）。更麻烦的是**泛型代码**：`optional<T>` 的 `transform` 若 `f` 返回 `int&`，在 C++23 中直接非良构；写一个"返回容器中某元素，可能没有"的通用函数，返回类型无从下手。`optional<T&>` 把这些洞补上了。

阅读前提：[[optional.optional]] 中的主模板；引用绑定与临时量物化（[[dcl.init.ref]]、[[class.temporary]]）；类型特征 `reference_constructs_from_temporary`（[[meta.rel]]）。

## 数据模型：就是一个指针（[optional.optional.ref.general]）

```cpp
template<class T>
class optional<T&> {
public:
  using value_type = T;
  // …
private:
  T* val = nullptr;                                     // exposition only
  template<class U> constexpr void convert-ref-init-val(U&& u);  // exposition only
};
```

¶1：

!!! std
    An object of type `optional<T&>` *contains a value* if and only if *val* `!= nullptr` is `true`. When an `optional<T&>` contains a value, the *contained value* is a reference to `*`*val*.

    `optional<T&>` 含有值当且仅当 *val* 不为空指针；含有值时，被包含值是指向 `*`*val* 的引用。

这和主模板截然不同：主模板的"有值"是联合体成员活跃与否（对象级的生命周期），`optional<T&>` 的"有值"只是一个指针是否为空。没有联合体、没有额外的 `bool`，`sizeof(optional<int&>) == sizeof(int*)`。

¶2：

!!! std
    Each type `optional<T&>` is a trivially copyable class ([class.prop]).

    每个 `optional<T&>` 类型都是平凡可复制类。

这是**直接规定的结论**，而不是从各个特殊成员的 *Remarks* 推出来的：复制构造与复制赋值都是 `= default` 且 `noexcept`，析构函数 `= default`。复制一个 `optional<T&>` 就是复制一个指针。

几个关键成员的形态：

- `value_type` 是 `T`，**不是** `T&`；
- 只有 `iterator`，**没有** `const_iterator`；`begin()`/`end()` 只有 `const` 版本——见下面"浅 const"；
- 所有观察器和单子操作都是 `const` 成员函数，返回 `T&` / `T*`；
- 没有 `operator=(U&&)`，没有移动构造/移动赋值的声明（复制即移动）。

## 浅 const：`const optional<T&>` 不保护被引用对象

`optional<T&>` 的观察器全部是 `const` 成员，而且返回的是 `T&` 而非 `const T&`：

```cpp
constexpr T*  operator->() const noexcept;
constexpr T&  operator*()  const noexcept;
constexpr T&  value()      const;
```

这是**浅 const**（shallow const）语义，和指针、引用、`std::span`、`std::reference_wrapper` 一致：`const` 修饰的是"这个 optional 指向谁"，而不是"被指向的对象能否修改"。若需要只读访问，用 `optional<const T&>`。

```cpp run title="shallow_const.cpp" ok
#include <cassert>
#include <optional>
#include <string>
#include <type_traits>

struct Widget { std::string name; };

int main() {
  Widget w{"w"};
  const std::optional<Widget&> cr = w;   // optional 本身是 const……
  cr->name = "changed";                  // ……但被引用的对象不是：浅 const
  assert(w.name == "changed");

  // or_else / and_then / transform 都是 const 成员
  std::optional<Widget&> none;
  Widget fallback{"fb"};
  auto r = none.or_else([&] { return std::optional<Widget&>(fallback); });
  assert(&*r == &fallback);

  auto len = cr.transform([](Widget& x) { return x.name.size(); });
  static_assert(std::is_same_v<decltype(len), std::optional<std::size_t>>);
  assert(*len == 7);

  static_assert(std::is_same_v<std::optional<Widget&>::value_type, Widget>);
}
```

同理，迭代器只有一种：`const optional<T&>` 的 `begin()` 返回的迭代器解引用得到 `T&`。

## 构造：凡是会绑定临时量的，一律弃置（[optional.ref.ctor]）

### 仅用于说明的 *convert-ref-init-val*（[optional.ref.expos]）

所有"绑定"类构造与 `emplace` 都归结为这个辅助函数（[optional.ref.expos] ¶1）：

!!! std
    *Effects*: Creates a variable `r` as if by `T& r(std::forward<U>(u));` and then initializes *val* with `addressof(r)`.

    效果：如同 `T& r(std::forward<U>(u));` 那样创建变量 `r`，然后以 `addressof(r)` 初始化 *val*。

也就是说，`optional<T&>` 的绑定**与声明一个 `T&` 引用完全相同**——派生类到基类的转换、用户定义的转换函数返回引用等，都按 [[dcl.init.ref]] 的规则来。用 `addressof` 而不是 `&r` 是为了绕过重载的一元 `&`。

### 从 `U&&` 构造（¶3–7）

```cpp
template<class U>
  constexpr explicit(!is_convertible_v<U, T&>)
  optional(U&& u) noexcept(is_nothrow_constructible_v<T&, U>);
```

¶4 *Constraints*：`remove_cvref_t<U>` 不是 `optional`（4.1）、不是 `in_place_t`（4.2），且 `is_constructible_v<T&, U>`（4.3）。¶7 *Remarks*：

!!! std
    This constructor is defined as deleted if `reference_constructs_from_temporary_v<T&, U>` is `true`.

    若 `reference_constructs_from_temporary_v<T&, U>` 为真，此构造函数被定义为弃置的。

`reference_constructs_from_temporary_v<T&, U>` 问的是：用一个 `U` 类型的表达式初始化 `T&`，是否会把引用**绑定到一个临时对象**上（[[meta.rel]]）。对 `const int&` 与 `int` prvalue、`const long&` 与 `int` 左值（需要转换，产生临时 `long`）、`const std::string&` 与 `"abc"`，答案都是"是"。核心语言允许 `const T&` 绑定临时量并延长其生命周期——但这种延长**只对直接绑定的引用变量有效**，经过 `optional` 的构造函数参数传递之后，临时量在完整表达式结束时就死了，`optional<const T&>` 必然悬垂。所以标准把这些构造直接弃置：

```cpp run title="no_temporaries.cpp" error
#include <optional>
#include <string>

int main() {
  int i = 0;
  std::optional<const int&> a = i;                    // OK
  std::optional<const int&> b = 42;                   // error: 会绑定到临时量，构造函数被弃置
  std::optional<const std::string&> c = "abc";        // error: 会物化一个临时 string
  std::optional<const long&> d = i;                   // error: int → long 产生临时量
  std::optional<int&> e = 42;                         // error: int& 不能绑定 prvalue（约束不满足）
}
```

注意 `b`/`c`/`d` 与 `e` 的报错性质不同：`e` 是 `is_constructible_v<int&, int>` 为假，构造函数**不参与**重载决议；`b`/`c`/`d` 是构造函数参与重载决议、被选中、然后因为**弃置**而报错。为什么不把"不绑定临时量"也写成 *Constraints*？因为弃置函数能**阻止退路**：若只是从候选集中移除，重载决议可能找到别的可行路径（例如某个更差的转换），悄无声息地编译通过；弃置的函数一旦是最佳匹配，就必然报错。`std::pair`、`std::tuple` 的引用成员构造函数采用了同样的"defined as deleted if `reference_constructs_from_temporary_v`"写法（见 [[pairs]]、[[tuple]]）。

`explicit` 条件 `!is_convertible_v<U, T&>`：能隐式绑定就能隐式构造。

### `in_place` 构造（¶1–3）

`optional(in_place_t, Arg&& arg)`：只接受**一个**实参（引用只能从一个东西绑定）。¶1 的两条都是 *Constraints*——`is_constructible_v<T&, Arg>` 且 `reference_constructs_from_temporary_v<T&, Arg>` 为假。这里"绑定临时量"是约束而不是弃置：`in_place` 构造是显式的、很少参与隐式转换的竞争，不存在"退路"问题。

!!! impl "libc++"
    libc++ 23 在 `<optional>` 中为每个"defined as deleted if"的构造函数写了**两份**带互斥 `requires` 的声明：一份正常实现，一份 `= delete`。存储放在 `__optional_storage_base<_Tp, true>`（第二个模板参数是 `is_reference<_Tp>`），只有一个 `__raw_type* __value_` 成员；`__convert_init_ref_val` 就是规范里的 *convert-ref-init-val*：`_Tp& __r(std::forward<_Up>(__val)); __value_ = std::addressof(__r);`。

### 从另一个 optional 构造（¶8–19）

主模板只有 `const optional<U>&` 和 `optional<U>&&` 两个转换构造函数，`optional<T&>` 却有**四个**：`optional<U>&`、`const optional<U>&`、`optional<U>&&`、`const optional<U>&&`。原因是绑定引用时源对象的 cv 限定和值类别**直接决定能否绑定**：从非 const 左值 `optional<int>&` 可以得到 `int&`，从 `const optional<int>&` 只能得到 `const int&`。

以 `optional<U>&` 版本为例（¶8）：

- (8.1) `is_same_v<remove_cv_t<T>, optional<U>>` 为假——若 `T` 本身就是 `optional<U>`（即 `optional<optional<int>&>` 从 `optional<int>&` 构造），我们想要的是**绑定到那个 optional 对象本身**，交给 `optional(U&&)` 处理，而不是去绑定它的被包含值；
- (8.2) `is_same_v<T&, U>` 为假——`U` 已经是 `T&`，即源是同类型的 `optional<T&>`，交给复制构造函数；
- (8.3) `is_constructible_v<T&, U&>`。

¶9 效果：`if (rhs.has_value())` *convert-ref-init-val*`(rhs.operator*())`——**绑定到源 optional 内部的那个值**。¶10：若 `reference_constructs_from_temporary_v<T&, U&>`，定义为弃置。

于是有一个必须牢记的后果：

```cpp run title="bind_to_contents.cpp" ok
#include <cassert>
#include <optional>

struct Base { int id = 1; };
struct Derived : Base { };

int f() { return 7; }

int main() {
  std::optional<Derived> od = Derived{};
  std::optional<Base&> rb = od;          // 绑定到 od 内部的那个 Derived 对象（的 Base 子对象）
  assert(&*rb == &*od);

  std::optional<int(&)()> fr = f;        // 函数引用也是合法的被包含类型
  assert((*fr)() == 7);

  // 比较的是被引用的值，而不是地址
  int x = 3, y = 3;
  std::optional<int&> px = x, py = y;
  assert(px == py);
}
```

`rb` 的有效性完全依赖 `od` 的被包含值存活：

!!! ub "源 optional 被重置后的悬垂"
    ```cpp
    std::optional<int> src = 1;
    std::optional<int&> r = src;   // 指向 src 的被包含值
    src.reset();                   // 被包含值的生命周期结束
    int v = *r;                    // UB：通过悬垂引用访问生命周期已结束的对象
    ```
    `r.has_value()` 仍为真——`optional<T&>` 只看自己的指针，根本不知道源对象已经死了。这与裸指针的悬垂问题一模一样，`reference_constructs_from_temporary` 只拦得住**临时量**，拦不住**过早销毁的具名对象**。

右值版本也一样：`optional<const int&> r = make_optional_int();` 中 `U = int`，`reference_constructs_from_temporary_v<const int&, int>` 为真，于是被弃置——一个从临时 `optional<int>` 里取引用的写法在编译期就被拒绝了（本机 clang 23 + libc++ 报"invokes a deleted function"）。

## 赋值：改绑，永不写穿（[optional.ref.assign]）

`optional<T&>` 只声明了两个赋值运算符：

```cpp
constexpr optional& operator=(nullopt_t) noexcept;                    // val = nullptr
constexpr optional& operator=(const optional& rhs) noexcept = default; // 复制指针
```

**没有** `operator=(U&&)`。但下面的代码能编译：

```cpp run title="rebind.cpp" ok
#include <cassert>
#include <optional>
#include <type_traits>

int main() {
  int a = 1, b = 2;
  std::optional<int&> r = a;    // 绑定到 a
  r = b;                        // 重新绑定到 b——不是 a = b！
  assert(a == 1 && &*r == &b);
  *r = 20;                      // 通过 * 写的是 b
  assert(b == 20);

  r = std::nullopt;             // 解绑，b 不受影响
  assert(!r && b == 20);

  static_assert(sizeof(std::optional<int&>) == sizeof(int*));
  static_assert(std::is_trivially_copyable_v<std::optional<int&>>);

  int v = r.value_or(-1);       // value_or 按值返回 remove_cv_t<T>
  assert(v == -1);
}
```

`r = b` 的过程：`b` 经非 explicit 的 `optional(U&&)` 隐式转换成一个临时 `optional<int&>`，再调用（defaulted 的）复制赋值——复制的是**指针**。结果是**改绑**（rebind）。

这正是十多年争论的焦点。对一个**已经有值**的 `optional<T&>` 执行 `r = b`，有两种自洽的语义：

| 语义 | `r = b` 做什么 | 支持者的理由 |
|---|---|---|
| 写穿（assign-through） | `*r = b`，像真正的引用 | `optional<T&>` 应该"像 `T&`"；`T&` 的赋值就是写穿 |
| 改绑（rebind） | 让 `r` 指向 `b` | 赋值行为不能取决于运行时状态 |

写穿的致命问题：若 `r` **无值**，`r = b` 只能是绑定（没有东西可写穿）。于是同一行代码，`r` 有值时修改 `a`、无值时不修改任何东西——赋值的**语义随运行时状态改变**。这对泛型代码是灾难（`std::vector<optional<T&>>` 的元素赋值行为不可预测）。Boost.Optional 早就选择了改绑；C++26 的 `optional<T&>` 也选择改绑，并且干脆不提供 `operator=(U&&)`，让"赋值"只有"复制另一个 optional"一种含义。

!!! history "为什么拖了这么久"
    `optional<T&>` 原本是最初 optional 提案的一部分，因为"写穿 vs 改绑"无法达成共识，在 C++17 标准化之前被拿掉。其后十年，社区中有人统计过大量实际代码库中的自制 optional 引用实现，几乎全部采用改绑语义；这些调研最终促成 [[P2988]] 在 C++26 周期被接受。同时它的成功也依赖于 C++23 引入的 `reference_constructs_from_temporary` 特征——没有它，"禁止绑定临时量"无法在库中精确表达。

### `emplace`（¶4–6）

```cpp
template<class U> constexpr T& emplace(U&& u) noexcept(is_nothrow_constructible_v<T&, U>);
```

*Constraints*：`is_constructible_v<T&, U>` 且**不**绑定临时量。效果 *convert-ref-init-val*`(std::forward<U>(u))`，返回 `*val`。与 `r = b` 一样是改绑，区别是它可以使用显式转换（因为不经过隐式构造），并返回新绑定的引用。

## swap、迭代器、修改器

- [optional.ref.swap]：`swap` 等价于 `std::swap(val, rhs.val)`——交换两个指针，`noexcept`。所以 [[optional]] 中非成员 `swap` 的约束有 `is_reference_v<T> ||` 一支：不要求 `T` 可交换。
- [optional.ref.iterators] {{c++26}}：仅当 `T` 是对象类型且不是未知边界数组时存在 `iterator`；它满足 `contiguous_iterator`，引用类型 `T&`；`begin()` 有值时指向 `*val`，`end()` 为 `begin() + has_value()`。因为迭代器指向外部对象，[[optional]] 中声明了 `enable_borrowed_range<optional<T&>> = true`。libc++ 23 同主模板一样，需要 `-fexperimental-library`。
- [optional.ref.mod]：`reset()` 把 *val* 置为 `nullptr`。

## 观察器（[optional.ref.observe]）

- `operator->`（¶1–2）、`operator*`（¶3–4）：*Hardened preconditions* `has_value()`，返回 *val* 与 `*`*val*。与主模板一样，加固实现中违反即终止，否则 {{ub}}（这里是解引用空指针）。
- `operator bool`、`has_value`（¶5–6）：*val* `!= nullptr`。
- `value()`（¶7）：`return has_value() ? *val : throw bad_optional_access();`，独立实现中弃置。

### `value_or` 为什么按值返回（¶8–12）

```cpp
template<class U = remove_cv_t<T>> constexpr remove_cv_t<T> value_or(U&& u) const;
```

¶8 *Constraints*：`T` 是非数组对象类型。¶9 令 `X = remove_cv_t<T>`。¶10 *Mandates*：`is_constructible_v<X, T&> && is_convertible_v<U, X>`。¶11：`has_value() ? *val : static_cast<X>(std::forward<U>(u))`。

返回 `T&` 看起来更"自然"，但备选值几乎总是临时量：`r.value_or(0)`、`name.value_or("unknown")`。若返回 `T&`，就得把引用绑定到这个实参上，而实参在完整表达式末尾销毁——`const int& x = r.value_or(0);` 立刻悬垂。按值返回 `remove_cv_t<T>` 牺牲了"返回引用"的能力，换来"永远不会因为 `value_or` 悬垂"。需要"引用或备选引用"的语义时，写 `r ? *r : fallback`，或用 `or_else` 返回另一个 `optional<T&>`。

```cpp run title="value_or_by_value.cpp" error
#include <optional>
int main() {
  int a = 1;
  std::optional<int&> r = a;
  int& x = r.value_or(a);   // error: value_or 返回 int（prvalue）
}
```

¶12 *Remarks*：若 `T` 是数组类型或非对象类型（如函数类型），返回类型**未指明**。注 1 解释：这是为了避免声明本身非良构——`remove_cv_t<int[3]>` 作为函数返回类型是非法的，若照写，`optional<int(&)[3]>` 一实例化就会出错，即使从未调用 `value_or`。规范用"返回类型未指明"让实现随便写个合法的类型占位，而 ¶8 的 *Constraints* 保证这种情况下函数根本不可调用。libc++ 的写法是返回 `decay_t<_Tp>`：对非数组对象类型就是 `remove_cv_t<_Tp>`，对数组和函数退化为指针，声明总是合法。

## 单子操作（[optional.ref.monadic]）

都是 `const` 成员（浅 const），只有一个重载：

- `and_then`（¶1–3）：`U = invoke_result_t<F, T&>`，*Mandates* `remove_cvref_t<U>` 是 `optional` 的特化；有值则 `invoke(f, *val)`，否则 `remove_cvref_t<U>()`。
- `transform`（¶4–6）：`U = remove_cv_t<invoke_result_t<F, T&>>`，*Mandates* `U` 是合法被包含类型且 `U u(invoke(f, *val));` 良构（注 1：不要求可移动）；返回 `optional<U>`，被包含值以 `invoke(f, *val)` 直接非列表初始化。`f` 返回引用时得到另一个 `optional<X&>`，可以一路"投影"下去：`opt_person.transform(&Person::address).transform(&Address::city)`。
- `or_else`（¶7–9）：*Constraints* `F` 满足 `invocable`；*Mandates* `f()` 返回 `optional`（即 `optional<T&>`）；有值则 `return *val;`（经由 `optional(U&&)` 构造一个指向同一对象的 optional），否则 `f()`。

!!! lawyer "概要与详细规格不一致"
    [optional.optional.ref.general] 的类概要把 `transform` 声明为返回 `optional<invoke_result_t<F, T&>>`，而 [optional.ref.monadic] 的详细声明返回 `optional<remove_cv_t<invoke_result_t<F, T&>>>`。当 `f` 返回 `const int` 这种 cv 限定的 prvalue 类型时两者不同。按库规范惯例，详细规格优先；libc++ 23 按详细规格实现（返回类型中带 `remove_cv_t`）。这看起来是合入时留下的编辑性瑕疵。

## 比较与 hash

`optional<T&>` 没有自己的比较运算符——[[optional]] 中的比较函数模板都以 `optional<T>` 为参数，对 `T&` 同样适用，比较的是 `*x == *y`，即**被引用的值**，而不是地址（上面 `px == py` 的例子）。这与指针相反：两个指向不同对象但值相等的 `optional<int&>` 是相等的。如果要比较身份，请比较 `&*x == &*y`（注意先检查有值）。

`hash<optional<T&>>` 按 [optional.hash] 的字面规则是禁用的（`hash<T&>` 未启用），见 [[optional]]。

## 实现状态

本机 libc++ 23 的 `<version>` 在 C++26 模式下定义 `__cpp_lib_optional` 为 `202506L`，即包含 `optional<T&>`。上面所有示例均在 `clang++ -std=c++2c` 下验证。迭代器部分需要 `-fexperimental-library`。

## 思考题

!!! question "思考题 1"
    `optional<T&>` 没有 `operator=(U&&)`，为什么 `r = b;` 还能编译？如果 `T&` 只能从 `U` **显式**构造（例如 `U` 有一个 `explicit operator T&()`），`r = u;` 还能编译吗？该怎么写？

<details markdown="1">
<summary>展开查看答案与解析</summary>

`r = b` 中，`b` 通过非 explicit 的 `optional(U&&)` 隐式转换为 `optional<T&>` 临时量，再匹配复制赋值 `operator=(const optional&)`。若转换是显式的，`optional(U&&)` 是 `explicit(true)`，不能用于复制初始化赋值运算符的参数，于是 `r = u` 无可行函数。可以写 `r = std::optional<T&>(u);`，或 `r.emplace(u);`——`emplace` 走的是 *convert-ref-init-val* 中的 `T& r(std::forward<U>(u));`，这是直接初始化，显式转换函数可用。
</details>

!!! question "思考题 2"
    `std::optional<const std::string&> name = get_name();`，其中 `get_name()` 返回 `std::string`。这行代码在 C++26 中会怎样？如果 `get_name()` 返回 `const std::string&` 呢？

<details markdown="1">
<summary>展开查看答案与解析</summary>

返回 `std::string`（prvalue）时，`U = std::string`，`reference_constructs_from_temporary_v<const std::string&, std::string>` 为真，`optional(U&&)` 被定义为弃置，编译失败——这正是该规则要拦截的悬垂。返回 `const std::string&` 时，`U = const std::string&`，引用直接绑定到一个左值，不涉及临时量，编译通过；此时有效性取决于 `get_name()` 返回的引用本身是否有效，标准库无从检查。
</details>

## 小结

| 方面 | `optional<T&>` | 主模板 `optional<T>` |
|---|---|---|
| 存储 | `T* val`，空指针 = 无值 | 联合体 + 有值标志 |
| 平凡可复制 | 总是（¶2 直接规定） | 随 `T` |
| `value_type` | `T` | `T` |
| 赋值 | 只有 `= nullopt` 和复制；`r = x` 是**改绑** | `T` 的赋值或构造 |
| 绑定临时量 | 构造函数弃置（`in_place`/`emplace` 为约束） | 不适用 |
| const 语义 | 浅 const，观察器全是 const 成员返回 `T&` | 深 const |
| `value_or` | 按值返回 `remove_cv_t<T>`；`T` 非对象/数组时不可调用 | 按值返回 `T` |
| 迭代器 | 仅对象类型（非未知边界数组）；borrowed range | 总有；view |
| 比较 | 比较被引用的值 | 比较值 |
| swap | 交换指针，`noexcept` | 交换值或移动 |
