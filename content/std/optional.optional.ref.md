---
title: optional 的引用偏特化
summary: C++26 的 optional<T&> 是一个可以为空的引用，内部只存一个指针：赋值是改绑，凡是会绑定到临时对象的构造都被禁止，const 是浅的，value_or 按值返回。
status: draft
covers: *
papers: P2988, P3168, P1683R0
related: optional, optional.optional, meta.rel, dcl.init.ref, class.temporary, class.prop, basic.life, tuple, pairs
tags: 标准库, optional, 引用, C++26, 悬垂引用
updated: 2026-10-19
---

!!! tldr
    - `optional<T&>` 内部只有一个 `T*`，空指针表示无值；它总是平凡可复制的，大小与指针相同。
    - 对它赋值是改绑：`r = b` 让 `r` 指向 `b`，不会修改 `r` 原来引用的对象。
    - 凡是会让引用绑定到临时对象的构造，例如 `optional<const int&> r = 42;`，都被定义为弃置，编译时就报错。
    - const 是浅的：`const optional<T&>` 照样能修改被引用的对象，只读访问要写 `optional<const T&>`。
    - `value_or` 按值返回 `remove_cv_t<T>`，这样它永远不会返回悬垂引用。

```cpp run ok
#include <cassert>
#include <map>
#include <optional>
#include <string>

std::optional<int&> find(std::map<std::string, int>& m,
                         const std::string& key) {
  auto it = m.find(key);
  if (it == m.end()) return std::nullopt;
  return it->second;            // 引用 map 里的元素
}

int main() {
  std::map<std::string, int> m{{"a", 1}};
  if (auto r = find(m, "a")) *r = 10;
  assert(m["a"] == 10);
  assert(!find(m, "b"));
}
```

C++26 之前，表达一个也许不存在的引用只有两种办法：裸指针 `T*`，它不说明谁拥有对象，还允许指针运算；或者 `std::optional<std::reference_wrapper<T>>`，用起来要写 `opt->get().member`。泛型代码更麻烦：C++23 中 `transform` 的 `f` 若返回 `int&`，程序直接非良构。C++26 的 [[P2988]] 加入了偏特化 `optional<T&>`。主模板见 [[optional.optional]]。

## 内部是一个指针 [optional.optional.ref.general]

```cpp
template<class T>
class optional<T&> {
public:
  using value_type = T;
  // …
private:
  T* val = nullptr;                                     // exposition only
};
```

¶1 当且仅当 *val* 不是空指针时，`optional<T&>` 含有值，被包含值就是指向 `*`*val* 的引用。主模板的有值指的是联合体成员是否活跃，涉及对象的生存期；这里只看一个指针是否为空。没有联合体，也没有额外的 `bool`，`sizeof(optional<int&>) == sizeof(int*)`。

¶2 每个 `optional<T&>` 都是平凡可复制的类（[[class.prop]]）。这是直接规定的结论：复制构造和复制赋值都是 `= default` 且 `noexcept`，析构函数也是 `= default`，复制它就是复制一个指针。

类的接口与主模板有几处不同：

- `value_type` 是 `T`，不是 `T&`；
- 没有 `operator=(U&&)`，也没有声明移动构造和移动赋值，复制就是移动；
- 观察器和单子操作都是 `const` 成员函数，返回 `T&` 或 `T*`；
- 只有 `iterator`，没有 `const_iterator`。

## 赋值是改绑 [optional.ref.assign]

```cpp run ok
#include <cassert>
#include <optional>
#include <type_traits>

int main() {
  int a = 1, b = 2;
  std::optional<int&> r = a;    // 绑定到 a
  r = b;                        // 改为绑定到 b，不是 a = b
  assert(a == 1 && &*r == &b);
  *r = 20;                      // 通过 * 写的是 b
  assert(b == 20);

  r = std::nullopt;             // 解除绑定，b 不受影响
  assert(!r && b == 20);

  static_assert(sizeof(std::optional<int&>) == sizeof(int*));
  static_assert(std::is_trivially_copyable_v<std::optional<int&>>);
}
```

`optional<T&>` 只声明了两个赋值运算符：¶1 `operator=(nullopt_t)` 把 *val* 置为空指针，以及 defaulted 的复制赋值。`r = b` 能编译，是因为 `b` 先经由非 explicit 的 `optional(U&&)` 隐式转换成一个临时 `optional<int&>`，再调用复制赋值，复制的是指针。结果是**改绑**（rebind）：`r` 改为引用 `b`。

对一个已经有值的 `optional<T&>` 执行 `r = b`，有两种自洽的语义：

| 语义 | `r = b` 做什么 | 理由 |
|---|---|---|
| 写穿（assign-through） | `*r = b` | 和 `T&` 的赋值一样 |
| 改绑（rebind） | 让 `r` 引用 `b` | 赋值的含义不应取决于运行时状态 |

写穿的问题在于 `r` 无值时没有对象可写，`r = b` 只能是绑定。同一行代码，`r` 有值时修改 `a`，无值时只是绑定到 `b`，赋值的含义随运行时状态改变，泛型代码无法预测它的行为。标准选择了改绑，并且干脆不提供 `operator=(U&&)`，让赋值只有复制另一个 optional 这一种含义。

!!! history "为什么拖到 C++26"
    最初的 optional 提案包含 `optional<T&>`，因为写穿与改绑之争无法达成共识，它在 C++17 之前被拿掉了。后来对已有 optional 引用实现的调研（[[P1683R0]]）发现它们普遍采用改绑。另一个前提是 C++23 加入的类型特征 `reference_constructs_from_temporary`，有了它才能在库中精确表达禁止绑定临时对象（见下一节）。

¶4–6 `emplace(u)` 同样是改绑，返回新绑定的引用。它的约束是 `T&` 能从 `U` 构造且不会绑定到临时对象；与 `r = u` 的区别是它做的是直接初始化，可以使用显式转换。

## 不能绑定到临时对象 [optional.ref.ctor]

```cpp run error
#include <optional>
#include <string>

int main() {
  int i = 0;
  std::optional<const int&> a = i;              // OK
  std::optional<const int&> b = 42;             // error: 弃置
  std::optional<const std::string&> c = "abc";  // error: 弃置
  std::optional<const long&> d = i;             // error: 弃置
  std::optional<int&> e = 42;                   // error: 没有可行的构造函数
}
```

### 绑定的方式和声明一个引用相同（[optional.ref.expos]）

所有绑定类的构造函数和 `emplace` 都归结为一个仅用于说明的辅助函数 *convert-ref-init-val*`(u)`。[optional.ref.expos] ¶1 规定它如同用 `T& r(std::forward<U>(u));` 创建变量 `r`，然后用 `addressof(r)` 初始化 *val*。

所以 `optional<T&>` 的绑定规则就是声明一个 `T&` 的规则（[[dcl.init.ref]]），派生类到基类的转换、返回引用的转换函数都照常适用。用 `addressof` 而不用 `&r`，是为了避开重载的一元 `&`。

### 从一个值构造（¶3–7）

```cpp
template<class U>
  constexpr explicit(!is_convertible_v<U, T&>)
  optional(U&& u) noexcept(is_nothrow_constructible_v<T&, U>);
```

¶4 约束是 `remove_cvref_t<U>` 不是这个 optional 类型、不是 `in_place_t`，并且 `is_constructible_v<T&, U>`。`explicit` 的条件是 `!is_convertible_v<U, T&>`：能隐式绑定，就能隐式构造。

¶7 如果 `reference_constructs_from_temporary_v<T&, U>` 为真，这个构造函数被定义为弃置。这个类型特征（[[meta.rel]]）判断用 `U` 类型的表达式初始化 `T&` 时，引用是否会绑定到一个临时对象。上例的 `b`、`c`、`d` 都会：`42` 是纯右值，`"abc"` 要先构造一个临时 `string`，`int` 转成 `long` 也会产生临时对象。

核心语言允许 `const T&` 绑定临时对象并延长它的生存期，但只有直接绑定到引用变量时才会延长（[[class.temporary]]）。经过 optional 构造函数的参数传递之后，临时对象在完整表达式结束时销毁，`optional<const T&>` 一定悬垂。所以标准直接禁止了这些构造。

上例中 `e` 的错误性质不同：`int&` 不能绑定纯右值，`is_constructible_v<int&, int>` 为假，构造函数根本不参与重载决议。`b`、`c`、`d` 的构造函数参与重载决议、被选中，然后因为是弃置的而报错。

把不绑定临时对象写成弃置而不是 *Constraints*，是为了堵住退路。如果只是把构造函数从候选中移除，重载决议可能找到别的可行路径，悄无声息地编译通过；弃置的函数一旦被选为最佳匹配，就一定报错。`std::pair` 和 `std::tuple` 的引用成员构造也采用同样的写法（[[pairs]]、[[tuple]]）。

¶1 `optional(in_place_t, Arg&& arg)` 只接受一个实参，因为引用只能从一个东西绑定。它的两个条件都是 *Constraints*：`is_constructible_v<T&, Arg>` 为真，且 `reference_constructs_from_temporary_v<T&, Arg>` 为假。`in_place` 构造总是显式调用，不存在被其他候选顶替的问题。

### 从另一个 optional 构造（¶8–19）

主模板只有 `const optional<U>&` 和 `optional<U>&&` 两个转换构造函数，`optional<T&>` 有四个：`optional<U>&`、`const optional<U>&`、`optional<U>&&`、`const optional<U>&&`。因为源对象的 const 和值类别直接决定能否绑定：从 `optional<int>&` 可以得到 `int&`，从 `const optional<int>&` 只能得到 `const int&`。

以 `optional<U>&` 版本为例，¶8 的约束是：

- ¶8.1 `remove_cv_t<T>` 不是 `optional<U>`。如果 `T` 本身就是 `optional<U>`，例如用 `optional<int>&` 构造 `optional<optional<int>&>`，要的是绑定到那个 optional 对象本身，交给 `optional(U&&)` 处理；
- ¶8.2 `T&` 不是 `U`，否则源就是同类型的 `optional<T&>`，交给复制构造函数；
- ¶8.3 `is_constructible_v<T&, U&>`。

¶9 有值时调用 *convert-ref-init-val*`(rhs.operator*())`，也就是绑定到源 optional 内部的那个值。¶10 如果这会绑定到临时对象，构造函数被定义为弃置。

```cpp run ok
#include <cassert>
#include <optional>

struct Base { int id = 1; };
struct Derived : Base { };

int f() { return 7; }

int main() {
  std::optional<Derived> od = Derived{};
  std::optional<Base&> rb = od;   // 绑定到 od 内部的 Derived
  assert(&*rb == &*od);

  std::optional<int(&)()> fr = f; // 函数引用也可以
  assert((*fr)() == 7);
}
```

`rb` 是否有效，完全取决于 `od` 的被包含值是否还活着：

```cpp run ub
#include <optional>

int main() {
  std::optional<int> src = 1;
  std::optional<int&> r = src;    // 引用 src 的被包含值
  src.reset();                    // 被包含值的生存期结束
  return *r;                      // UB：r 仍然有值，但已悬垂
}
```

`r.has_value()` 仍然为真，`optional<T&>` 只看自己的指针，不知道源对象已经销毁。这和裸指针的悬垂一样，`reference_constructs_from_temporary` 只拦得住临时对象，拦不住过早销毁的具名对象。

右值版本则能拦住一种常见错误。`optional<const int&> r = make_opt();`（`make_opt` 返回 `optional<int>`）中，`U = int`，`reference_constructs_from_temporary_v<const int&, int>` 为真，构造函数被弃置，从临时 optional 里取引用的写法在编译期就被拒绝。

!!! impl "libc++"
    libc++ 23 为每个被定义为弃置的构造函数写了两份声明，用互斥的 `requires` 区分：一份正常实现，一份 `= delete`。存储只有一个指针成员，`__convert_init_ref_val` 对应规范里的 *convert-ref-init-val*。本机 libc++ 23 在 C++26 模式下把 `__cpp_lib_optional` 定义为 `202506L`，包含 `optional<T&>`。

## const 是浅的 [optional.ref.observe]

```cpp run ok
#include <cassert>
#include <optional>
#include <string>
#include <type_traits>

struct Widget { std::string name; };

int main() {
  Widget w{"w"};
  const std::optional<Widget&> cr = w;  // optional 本身是 const
  cr->name = "changed";                 // 被引用的对象不是
  assert(w.name == "changed");

  std::optional<Widget&> none;
  Widget fallback{"fb"};
  auto r = none.or_else(
      [&] { return std::optional<Widget&>(fallback); });
  assert(&*r == &fallback);

  auto len = cr.transform([](Widget& x) { return x.name.size(); });
  static_assert(std::is_same_v<decltype(len),
                               std::optional<std::size_t>>);
  assert(*len == 7);
}
```

观察器全是 `const` 成员函数，返回 `T&` 而不是 `const T&`：

```cpp
constexpr T* operator->() const noexcept;
constexpr T& operator*()  const noexcept;
constexpr T& value()      const;
```

这是**浅 const**（shallow const），和指针、`std::span`、`std::reference_wrapper` 一样：`const` 限制的是这个 optional 引用谁，不限制被引用的对象。需要只读访问时用 `optional<const T&>`。

¶1–4 `operator->` 和 `operator*` 有加固前置条件 `has_value()`。与主模板一样，加固实现会检查并终止，非加固实现中违反它是 {{ub}}，这里就是解引用空指针。¶5–6 `operator bool` 和 `has_value()` 返回 *val* 是否非空。¶7 `value()` 等价于 `return has_value() ? *val : throw bad_optional_access();`，在独立实现中是弃置的。

### `value_or` 按值返回（¶8–12）

```cpp
template<class U = remove_cv_t<T>>
  constexpr remove_cv_t<T> value_or(U&& u) const;
```

¶9–11 令 `X` 为 `remove_cv_t<T>`，效果等价于 `has_value() ? *val : static_cast<X>(std::forward<U>(u))`。¶10 要求 `X` 能从 `T&` 构造、`U` 能隐式转换为 `X`（*Mandates*）。

返回 `T&` 看起来更自然，但备选值几乎总是临时对象，例如 `r.value_or(0)`、`name.value_or("unknown")`。如果返回 `T&`，引用就要绑定到这个实参上，`const int& x = r.value_or(0);` 立刻悬垂。按值返回放弃了返回引用的能力，换来 `value_or` 永远不会造成悬垂。需要引用或备选引用时，写 `r ? *r : fallback`，或者用 `or_else` 返回另一个 `optional<T&>`。

```cpp run error
#include <optional>
int main() {
  int a = 1;
  std::optional<int&> r = a;
  int& x = r.value_or(a);   // error: value_or 返回 int 纯右值
}
```

¶8 `value_or` 只在 `T` 是非数组对象类型时可调用（*Constraints*）。¶12 如果 `T` 是数组或非对象类型（如函数类型），返回类型未指定。注 1 说明这是为了避免声明本身非良构：`remove_cv_t<int[3]>` 不能作为函数的返回类型，照写的话 `optional<int(&)[3]>` 一实例化就出错，即使从不调用 `value_or`。libc++ 的返回类型写成 `decay_t<T>`，对非数组对象类型就是 `remove_cv_t<T>`，对数组和函数退化为指针，声明总是合法。

## 单子操作 [optional.ref.monadic]

三个单子操作都是 `const` 成员，各只有一个重载：

- ¶1–3 `and_then`：令 `U` 为 `invoke_result_t<F, T&>`，要求 `remove_cvref_t<U>` 是 `optional` 的特化；有值时返回 `invoke(f, *val)`，否则返回空的 `remove_cvref_t<U>`。
- ¶4–6 `transform`：令 `U` 为 `remove_cv_t<invoke_result_t<F, T&>>`，要求它是合法被包含类型且 `U u(invoke(f, *val));` 良构，不要求可移动；返回 `optional<U>`。`f` 返回引用时得到另一个 `optional<X&>`，可以一路投影下去，例如 `person.transform(&Person::address).transform(&Address::city)`。
- ¶7–9 `or_else`：要求 `F` 可无参调用（*Constraints*），`f()` 返回这个 `optional<T&>`（*Mandates*）；有值时返回指向同一对象的 optional，否则返回 `f()`。

!!! lawyer "概要与详细规格不一致"
    [optional.optional.ref.general] 的类概要把 `transform` 的返回类型写成 `optional<invoke_result_t<F, T&>>`，[optional.ref.monadic] 的详细声明却是 `optional<remove_cv_t<invoke_result_t<F, T&>>>`。`f` 返回 `const int` 这种带 cv 的纯右值类型时，两者不同。看起来是合入时留下的编辑性问题。libc++ 23 按详细声明实现。

## swap、迭代器和 reset

[optional.ref.swap] ¶1 `swap` 等价于 `std::swap(val, rhs.val)`，只交换两个指针，总是 `noexcept`。所以 [[optional]] 中非成员 `swap` 的约束有一个 `is_reference_v<T> ||` 分支，不要求 `T` 可交换。

[optional.ref.iterators] {{c++26}} 只有当 `T` 是对象类型且不是未知边界数组时才有 `iterator` 和 `begin`、`end`（¶3、¶5）。¶1 迭代器满足 `contiguous_iterator`，引用类型是 `T&`；¶4、¶6 有值时 `begin()` 指向 `*`*val*，`end()` 是 `begin() + has_value()`。迭代器指向外部对象，不依赖 optional 本身是否还活着，所以 [[optional]] 声明了 `enable_borrowed_range<optional<T&>>` 为真。本机 libc++ 23 与主模板一样，要加 `-fexperimental-library` 才提供迭代器。

[optional.ref.mod] `reset()` 把 *val* 置为空指针。

## 比较与 hash

`optional<T&>` 没有自己的比较运算符。[[optional]] 中的比较函数模板以 `optional<T>` 为参数，对 `T&` 同样适用，比较的是 `*x == *y`，也就是被引用的值，而不是地址：

```cpp run ok
#include <cassert>
#include <optional>

int main() {
  int x = 3, y = 3;
  std::optional<int&> px = x, py = y;
  assert(px == py);           // 值相等
  assert(&*px != &*py);       // 引用的不是同一个对象
}
```

这和指针相反。要比较是否引用同一个对象，就比较 `&*x == &*y`，比较前先确认两边都有值。

[optional.hash] 规定 `hash<optional<T>>` 当且仅当 `hash<remove_const_t<T>>` 启用时才启用。对 `optional<int&>` 来说，这要求 `hash<int&>` 启用，而标准没有为引用类型启用 `hash`，所以按字面规则 `hash<optional<T&>>` 是禁用的，见 [[optional]]。

## 思考题

!!! question "思考题 1"
    `optional<T&>` 没有 `operator=(U&&)`，为什么 `r = b;` 能编译？如果 `T&` 只能从 `U` 显式构造（例如 `U` 有一个 `explicit operator T&()`），`r = u;` 还能编译吗？该怎么写？

<details markdown="1">
<summary>答案</summary>

`r = b` 中，`b` 经由非 explicit 的 `optional(U&&)` 隐式转换为一个临时 `optional<T&>`，再匹配复制赋值 `operator=(const optional&)`。如果转换是显式的，`optional(U&&)` 是 `explicit(true)`，不能用于初始化赋值运算符的参数，`r = u` 没有可行函数。可以写 `r = std::optional<T&>(u);` 或 `r.emplace(u);`。`emplace` 经过 *convert-ref-init-val* 中的 `T& r(std::forward<U>(u));`，这是直接初始化，显式转换函数可用。
</details>

!!! question "思考题 2"
    `std::optional<const std::string&> name = get_name();` 中，如果 `get_name()` 返回 `std::string`，结果如何？返回 `const std::string&` 呢？

<details markdown="1">
<summary>答案</summary>

返回 `std::string` 纯右值时，`U = std::string`，`reference_constructs_from_temporary_v<const std::string&, std::string>` 为真，`optional(U&&)` 是弃置的，编译失败，这正是这条规则要拦截的悬垂。返回 `const std::string&` 时，`U = const std::string&`，引用直接绑定到一个左值，不涉及临时对象，编译通过。这时是否有效取决于 `get_name()` 返回的引用本身，标准库无从检查。
</details>
