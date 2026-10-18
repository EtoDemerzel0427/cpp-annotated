---
title: 类模板 expected
summary: expected<T, E> 主模板精读：合法值类型、构造函数的约束与 explicit 条件、条件平凡的特殊成员（以及 libc++ 23 在赋值上的缺口）、"永不为空"不变式与 reinit-expected 的三段式异常安全策略、noexcept 的 emplace、swap、加固的观察器与 value() 抛出 bad_expected_access<E>、value_or / error_or、四个单子操作的 Constraints 与 Mandates、相等比较
status: draft
covers: *
papers: P0323, P2505, P0848, P3471
related: expected, expected.void, optional.optional, variant.variant, class.union, class.prop, class.dtor, special, structure.specifications, except.throw, specialized.construct
tags: 标准库, expected, 异常安全, 平凡性, 单子操作, 加固
updated: 2026-10-18
---

`expected<T, E>` 的主模板在很多方面是 [[optional.optional]] 的翻版：同样用联合体描述存储，同样有条件平凡的特殊成员，同样有 `explicit(see below)` 的转换构造函数和单子操作。但它多了一条 `optional` 没有的硬性不变式：

> 一个 `expected<T, E>` 对象**永远**恰好含有一个 `T` 或一个 `E`。

`optional` 赋值失败可以退回"无值"，`expected` 没有"无值"可退。这一条不变式决定了整个赋值规格的形状，也是本页的重头戏。总览、`unexpected` 与 `bad_expected_access` 见 [[expected]]；`T` 为 `void` 的偏特化见 [[expected.void]]。

## 数据模型与对 T、E 的要求（[expected.object.general]）

```cpp
template<class T, class E>
class expected {
public:
  using value_type = T;
  using error_type = E;
  using unexpected_type = unexpected<E>;
  template<class U> using rebind = expected<U, error_type>;
  // …
private:
  bool has_val;           // exposition only
  union {
    remove_cv_t<T> val;   // exposition only
    E unex;               // exposition only
  };
};
```

¶1：任何 `expected<T, E>` 对象要么含有 `T` 类型的值、要么含有 `E` 类型的值，该值**嵌套于**（[[intro.object]]）expected 对象之中；*has_val* 指示是哪一种。`rebind<U>` 方便泛型代码"换个值类型、保留错误类型"——单子操作的返回类型常常就是 `rebind`。

¶2 定义**合法的 expected 值类型**（[[g:valid-value-type-for-expected]]）：

!!! std
    A type `T` is a *valid value type for `expected`*, if `remove_cv_t<T>` is `void` or a complete non-array object type that is not `in_place_t`, `unexpect_t`, or a specialization of `unexpected`.

    若 `remove_cv_t<T>` 是 `void`，或是完整的非数组对象类型且不是 `in_place_t`、`unexpect_t`、`unexpected` 的特化，则 `T` 是 expected 的合法值类型。

用非法值类型实例化 `expected<T, E>` 非良构。同时，以非 `unexpected` 合法实参（见 [[expected]]：非对象类型、数组、cv 限定、`unexpected` 特化）作为 `E` 实例化**定义**，也非良构。与 optional 的对比：

- `expected<T&, E>` **不合法**——与 C++26 的 `optional<T&>` 不同，`expected` 没有引用特化；
- `expected<const T, E>` 合法（值一侧可以有 cv），但 `expected<T, const E>` 不合法（错误一侧不行）；
- 值类型不能是 `unexpected<X>`，否则 `expected<unexpected<int>, int>(unexpected(1))` 是值还是错误就说不清了。

¶3：`T`（非 void 时）与 `E` 都必须满足 *Cpp17Destructible*。

## 构造函数（[expected.object.cons]）

¶1 声明借用 [[optional.optional]] 中定义的 *converts-from-any-cvref*。

### 默认构造：有值，而且值被值初始化（¶2–5）

¶2 *Constraints*：`is_default_constructible_v<T>`。¶3：**值初始化** *val*。¶4：`has_value()` 为真。

这一点和 `optional` 截然相反：

```cpp
std::optional<int>      o;   // 无值
std::expected<int, Err> e;   // 有值，*e == 0
```

`expected` 的默认状态是"成功"，因为它没有"空"状态可用。从 optional 迁移代码时要特别注意这一点。

### 复制与移动构造（¶6–16）

复制构造：按 `rhs` 的状态直接非列表初始化 *val* 或 *unex*。¶9：除非 `T` 与 `E` 都可复制构造，否则**定义为弃置**；¶10：若两者都可平凡复制构造，则**平凡**。

移动构造：¶11 *Constraints*（不是弃置）：`T`、`E` 都可移动构造；¶15 `noexcept` 等价于两者都 nothrow 可移动构造；¶16：两者都可平凡移动构造则平凡。¶13：`rhs.has_value()` 不变。

### 从 `expected<U, G>` 转换（¶17–22）

两个重载（`const expected<U, G>&` 与 `expected<U, G>&&`）合在一起规定。¶17 令 `UF` 为 `const U&` 或 `U`，`GF` 为 `const G&` 或 `G`。¶18 *Constraints*：

- (18.1)、(18.2)：`T` 可从 `UF` 构造、`E` 可从 `GF` 构造；
- (18.3)：若 `T` 不是 cv `bool`，*converts-from-any-cvref*`<T, expected<U, G>>` 为假——与 optional 同理，若 `T` 能直接"吃下"一整个 `expected<U, G>`，逐成员转换就让路；
- (18.4)–(18.7)：`unexpected<E>` 不能从 `expected<U, G>` 的四种 cvref 形式构造——这是错误一侧的对称检查：若 `E` 能从整个 `expected<U, G>` 构造，"逐成员转换"与"把整个对象当作错误"两种解释就会打架，同样让路。

¶22：`explicit` 等价于 `!is_convertible_v<UF, T> || !is_convertible_v<GF, E>`——**两侧都能隐式转换**，整体才是隐式的。

### 从 `U&&` 构造值（¶23–26）

```cpp
template<class U = remove_cv_t<T>>
  constexpr explicit(!is_convertible_v<U, T>) expected(U&& v);
```

¶23 *Constraints* 有 6 条：`remove_cvref_t<U>` 不是 `in_place_t`（23.1）、不是 `expected` 本身（23.2）、不是 `unexpect_t`（23.3）、不是 `unexpected` 的特化（23.4）；`is_constructible_v<T, U>`（23.5）；若 `T` 是 cv `bool`，`remove_cvref_t<U>` 不是 `expected` 的特化（23.6，与 optional 的 (23.4) 同理：`bool` 能从 `expected` 经 `explicit operator bool` 直接初始化，必须堵住）。

(23.4) 是 `expected` 区分"值"与"错误"的核心：任何 `unexpected<X>` 都不会被当作值，只会走下面的错误构造函数。

### 从 `unexpected<G>` 构造错误（¶27–31）

```cpp
template<class G> constexpr explicit(!is_convertible_v<const G&, E>) expected(const unexpected<G>& e);
template<class G> constexpr explicit(!is_convertible_v<G, E>)        expected(unexpected<G>&& e);
```

¶28 *Constraints*：`is_constructible_v<E, GF>`。¶29：以 `std::forward<GF>(e.error())` 直接非列表初始化 *unex*。这正是 `return std::unexpected("not found");` 能返回 `expected<T, std::string>` 的原因：`unexpected<const char*>` 经此构造函数隐式转换，`const char*` → `std::string` 可隐式转换，所以构造函数不是 explicit 的。

### 原地构造（¶32–47）

`expected(in_place_t, Args&&...)`、`expected(in_place_t, initializer_list<U>, Args&&...)` 构造值；`expected(unexpect_t, Args&&...)`、`expected(unexpect_t, initializer_list<U>, Args&&...)` 构造错误。全部 `explicit`，*Constraints* 为相应的 `is_constructible_v`。

## 析构与条件平凡（[expected.object.dtor]）

¶1：有值销毁 *val*，否则销毁 *unex*。¶2：若 `T` 与 `E` 都可平凡析构，析构函数平凡。

把全部"平凡"条款汇总：

| 特殊成员 | 平凡条件（`T` 与 `E` 都须满足） | 段落 |
|---|---|---|
| 复制构造 | 可平凡复制构造 | [expected.object.cons] ¶10 |
| 移动构造 | 可平凡移动构造 | [expected.object.cons] ¶16 |
| 析构 | 可平凡析构 | [expected.object.dtor] ¶2 |
| 复制赋值 | 可平凡复制构造 ∧ 可平凡复制赋值 ∧ 可平凡析构 | [expected.object.assign] ¶5 |
| 移动赋值 | 可平凡移动构造 ∧ 可平凡移动赋值 ∧ 可平凡析构 | [expected.object.assign] ¶10 |

按 [[class.prop]]，这些合起来意味着 `expected<int, int>`、`expected<double, std::errc>` 这类类型应当是**平凡可复制**的。

!!! impl "libc++ 23：受约束的特殊成员，以及一个缺口"
    与 `<optional>` 的基类阶梯不同，libc++ 的 `__expected/expected.h` 直接使用 C++20 的受约束特殊成员（[[P0848]]，[[class.dtor]]、[[special]]）。以复制构造为例，它声明了**三个**：

    ```cpp
    constexpr expected(const expected&) = delete;
    constexpr expected(const expected&)
      requires(is_copy_constructible_v<_Tp> && is_copy_constructible_v<_Err> &&
               is_trivially_copy_constructible_v<_Tp> && is_trivially_copy_constructible_v<_Err>)
    = default;
    constexpr expected(const expected& __other) noexcept(/* strengthened */ …)
      requires(is_copy_constructible_v<_Tp> && is_copy_constructible_v<_Err> &&
               !(is_trivially_copy_constructible_v<_Tp> && is_trivially_copy_constructible_v<_Err>))
      : __base(__other.__has_val(), __other.__union()) {}
    ```

    无约束的 `= delete` 版本在其余两个都不满足时被选中，实现"定义为弃置"；两个有约束的版本互斥。内部存储 `__expected_base::__union_t` 的析构函数同样有 `requires(is_trivially_destructible_v<_Tp> && is_trivially_destructible_v<_Err>) = default` 与 `{}` 两个版本。

    但复制/移动**赋值**运算符在 libc++ 23 中只有"弃置"与"用户提供"两个版本，没有 `= default` 的平凡版本。实测（clang 23 + libc++，`-std=c++2c`）：`std::is_trivially_copy_constructible_v<std::expected<int,int>>`、`is_trivially_move_constructible_v`、`is_trivially_destructible_v` 都为真，而 `is_trivially_copy_assignable_v`、`is_trivially_move_assignable_v` 为假，因此 `std::is_trivially_copyable_v<std::expected<int, int>>` 为**假**，诊断信息是"has a user provided copy assignment operator"。也就是说，当前草案对赋值平凡性的要求（[expected.object.assign] ¶5、¶10，以及 [expected.void.assign] 的对应条款）截至本文编写时 libc++ 尚未实现。

    libc++ 还有一个布局优化：若"有值"标志能放进联合体的尾部填充，就放进去；它用一个 `__conditional_no_unique_address` 包装来条件地施加 `[[no_unique_address]]`，并在源码注释中详细解释了为什么必须保证被透明替换的那个成员不是 `[[no_unique_address]]`（否则会违反 [[basic.life]] 的透明替换条件）。

## 赋值：永不为空的代价（[expected.object.assign]）

### *reinit-expected*：三段式切换（¶1）

当赋值要求从"含 `U`（旧）"切换到"含 `T`（新）"时，标准用一个仅用于说明的函数模板 [[g:reinit-expected]] 描述：

```cpp
template<class T, class U, class... Args>
constexpr void reinit-expected(T& newval, U& oldval, Args&&... args) {  // exposition only
  if constexpr (is_nothrow_constructible_v<T, Args...>) {
    destroy_at(addressof(oldval));
    construct_at(addressof(newval), std::forward<Args>(args)...);
  } else if constexpr (is_nothrow_move_constructible_v<T>) {
    T tmp(std::forward<Args>(args)...);
    destroy_at(addressof(oldval));
    construct_at(addressof(newval), std::move(tmp));
  } else {
    U tmp(std::move(oldval));
    destroy_at(addressof(oldval));
    try {
      construct_at(addressof(newval), std::forward<Args>(args)...);
    } catch (...) {
      construct_at(addressof(oldval), std::move(tmp));
      throw;
    }
  }
}
```

难点在于：`newval` 和 `oldval` 共用同一块联合体存储，**必须先销毁旧的才能构造新的**。销毁之后、新对象构造完成之前，对象处于"两者皆无"的危险窗口。三个分支各自用不同手段保证这个窗口不会因异常而暴露：

1. **新值可以 nothrow 地从实参构造**：直接销毁旧值、构造新值。窗口存在，但构造不会抛，所以安全。
2. **新值类型可以 nothrow 移动构造**：先在**栈上**用实参构造一个临时 `T`——这一步可能抛，但此时旧值还完好无损，抛了就什么都没变。然后销毁旧值，再把临时量**移动**进来（不会抛）。
3. **都不行**：先把**旧值**移动到栈上的临时 `U` 里备份，销毁旧值，尝试构造新值；若抛异常，把备份**移动回**原处，再重新抛出。这一步要求把备份移回去不会抛——否则在 `catch` 里又失败，对象就真的空了。

第 3 分支隐含的要求"`U` 可 nothrow 移动构造"体现在赋值运算符的约束里：

!!! std
    This operator is defined as deleted unless: … `is_nothrow_move_constructible_v<T> || is_nothrow_move_constructible_v<E>` is `true`.

    除非……`T` 或 `E` 至少有一个可 nothrow 移动构造，否则此运算符被定义为弃置。（[expected.object.assign] ¶4.5）

这条保证了：要切换到的新类型若不能 nothrow 移动（走不了第 2 分支），那么旧类型一定能 nothrow 移动（第 3 分支的回滚安全）。libc++ 在第 3 分支里写了一个 `static_assert(is_nothrow_move_constructible_v<_T2>, "To provide strong exception guarantee, T2 has to satisfy ...")` 来自证这一点，并用 `__make_exception_guard` 实现 `try`/`catch` 回滚。

最终效果：**切换类型的赋值提供强异常保证**——要么成功，要么对象保持原状（原来的值或错误、原来的 *has_val*）。

```cpp run title="strong_guarantee.cpp" ok
#include <cassert>
#include <expected>
#include <stdexcept>

struct Fragile {
  int v;
  Fragile(int n) : v(n) { if (n < 0) throw std::invalid_argument("negative"); }
  Fragile(Fragile&&) noexcept = default;   // 移动不抛
  Fragile& operator=(Fragile&&) = default;
  Fragile(const Fragile&) = default;
  Fragile& operator=(const Fragile&) = default;
};

int main() {
  std::expected<Fragile, int> e = std::unexpected(7);
  try {
    e = -1;                           // reinit-expected 第二分支：先在临时量里构造 Fragile(-1)，抛了
  } catch (const std::invalid_argument&) {}
  assert(!e.has_value() && e.error() == 7);   // 原来的错误值原封不动

  e = 5;                              // 成功：错误被销毁，值被构造
  assert(e && e->v == 5);
}
```

两个都可能抛的组合则根本不能赋值：

```cpp run title="no_assign.cpp" ok
#include <expected>
#include <type_traits>

struct Throwy {                         // 移动可能抛异常
  Throwy() = default;
  Throwy(const Throwy&) {}
  Throwy(Throwy&&) noexcept(false) {}
  Throwy& operator=(const Throwy&) = default;
  Throwy& operator=(Throwy&&) = default;
};

// T、E 至少一个 nothrow 可移动构造：可以赋值
static_assert(std::is_copy_assignable_v<std::expected<Throwy, int>>);
// 两个都可能抛：复制赋值被定义为弃置
static_assert(!std::is_copy_assignable_v<std::expected<Throwy, Throwy>>);
static_assert(!std::is_move_assignable_v<std::expected<Throwy, Throwy>>);
// 但构造不受影响
static_assert(std::is_copy_constructible_v<std::expected<Throwy, Throwy>>);
int main() {}
```

这是 `expected` 与 `variant` 的分水岭：`variant` 选择在这种情况下允许赋值、失败时进入 `valueless_by_exception` 状态（[[variant.variant]]）；`expected` 选择在编译期拒绝，换取"永不为空"。

### 复制赋值与移动赋值（¶2–10）

¶2 复制赋值的四种情况：

- (2.1) 都有值：`val = *rhs`（`T` 的赋值，异常保证随 `T`）；
- (2.2) 自己有值、`rhs` 是错误：*reinit-expected*`(unex, val, rhs.error())`；
- (2.3) 自己是错误、`rhs` 有值：*reinit-expected*`(val, unex, *rhs)`；
- (2.4) 都是错误：`unex = rhs.error()`。

然后，**若没有抛出异常**，`has_val = rhs.has_value()`。把标志更新放在最后，正是 (2.2)/(2.3) 强保证的另一半。

¶4 弃置条件：`T`、`E` 都可复制赋值且可复制构造，并满足上面的 (4.5)。¶6 移动赋值把同样的条件写成 *Constraints*；¶9 `noexcept` 等价于 `T`、`E` 都 nothrow 可移动赋值且 nothrow 可移动构造。

### 从 `U&&` 赋值值、从 `unexpected<G>` 赋值错误（¶11–17）

`operator=(U&&)` 的 *Constraints*（¶11）：不是 `expected` 本身、不是 `unexpected` 特化、`T` 可从 `U` 构造且可从 `U` 赋值，以及

> (11.5) `is_nothrow_constructible_v<T, U> || is_nothrow_move_constructible_v<T> || is_nothrow_move_constructible_v<E>`

——恰好是 *reinit-expected* 三个分支各自的前提的析取：只要有一个分支可用，就能提供强保证。效果（¶12）：有值则 `val = std::forward<U>(v)`，否则 *reinit-expected*`(val, unex, std::forward<U>(v)); has_val = true;`。

`operator=(const unexpected<G>&)` / `operator=(unexpected<G>&&)` 对称（¶14–17）：(15.3) 要求 `is_nothrow_constructible_v<E, GF> || is_nothrow_move_constructible_v<T> || is_nothrow_move_constructible_v<E>`。

注意这里**没有** optional 那种 `o = {}` 的特殊处理：`e = {}` 会以 `U = remove_cv_t<T>` 值初始化一个 `T` 并赋值——把 `e` 设为"成功、值为 `T{}`"，而不是什么"重置"。

### `emplace` 必须 noexcept（¶18–21）

```cpp
template<class... Args> constexpr T& emplace(Args&&... args) noexcept;
```

¶18 *Constraints*：`is_nothrow_constructible_v<T, Args...>`。效果：销毁当前的值或错误，置 *has_val*，原地构造新值。

`optional::emplace` 允许构造抛异常（抛了就变成空）；`expected::emplace` 没有"空"可退，又不想为了原地构造付出备份旧对象的代价，于是干脆**只允许 nothrow 构造**。构造可能抛的，请用 `e = T(args...)`，走 *reinit-expected*。

```cpp
struct Fragile { explicit Fragile(int); };    // 构造可能抛
std::expected<Fragile, int> e = std::unexpected(7);
e.emplace(-1);   // error: 不满足 is_nothrow_constructible_v，emplace 不参与重载决议
```

（本机 clang 23 + libc++ 报"no matching member function for call to 'emplace'"。）

## swap（[expected.object.swap]）

¶1 *Constraints*：`T`、`E` 都可交换、都可移动构造，且至少一个可 nothrow 移动构造（同样是为了回滚）。表 72：

- 都有值：`using std::swap; swap(val, rhs.val);`
- 都是错误：`swap(unex, rhs.unex)`；
- `*this` 是错误、`rhs` 有值：调用 `rhs.swap(*this)`，转为下一种情况；
- `*this` 有值、`rhs` 是错误：一段专门的代码——若 `E` 可 nothrow 移动，就先把 `rhs.unex` 移到临时量里，再搬 `val`；否则把 `val` 移到临时量里，再搬 `unex`。思路与 *reinit-expected* 完全一样：**先备份那个可以安全搬回去的对象**，出错时 `catch` 里恢复并重抛。

¶4 `noexcept` 等价于 `T`、`E` 都 nothrow 可移动构造且 nothrow 可交换。

## 观察器（[expected.object.obs]）

### 加固的 `*`、`->` 和 `error()`

- `operator->`、`operator*`（¶1–6）：*Hardened preconditions* `has_value()` 为真；
- `error()`（¶15–18）：*Hardened preconditions* `has_value()` **为假**。

`error()` 也被加固，这一点与"错误一侧只是辅助"的印象不同：在成功的 `expected` 上调用 `error()`，读的是联合体里非活跃的 *unex*——同样是越界读。按 [[structure.specifications]]，加固实现中这些违反必定终止，非加固实现中是 {{ub}}（[[P3471]]）。libc++ 用 `_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS` 检查。

`operator bool` 与 `has_value()`（¶7）返回 *has_val*。较新的草案还新增了 `has_error()`（¶8，等价于 `!has_value()`），libc++ 23 尚未提供（`e.has_error()` 报"no member named 'has_error'"）。

### `value()`：抛出携带错误的异常（¶9–14）

```cpp
constexpr const T& value() const &;   constexpr T& value() &;
```

- ¶9 *Mandates*：`is_copy_constructible_v<E>`；
- ¶10 有值返回 *val*；
- ¶11 *Throws*：若无值，抛出 `bad_expected_access(as_const(error()))`。

为什么 *Mandates* 要求 `E` 可复制构造？被抛出的异常对象必须可复制构造（[[except.throw]]），`bad_expected_access<E>` 里装着一个 `E`。注意 `as_const`：左值版本的 `value()` 不能偷走 `*this` 里的错误，必须复制。右值版本（¶12–14）则抛 `bad_expected_access(std::move(error()))`，*Mandates* 额外要求 `E` 可从 `std::move(error())` 构造。

### `value_or` 与 `error_or`（¶19–26）

- `value_or(U&& v) const &`：¶19 *Mandates* `is_copy_constructible_v<T>` 且 `is_convertible_v<U, T>`；返回 `has_value() ? **this : static_cast<T>(std::forward<U>(v))`。
- `error_or(G&& e) const &`：¶23 *Mandates* `is_copy_constructible_v<E>` 且 `is_convertible_v<G, E>`；**有值**时返回 `std::forward<G>(e)`，否则返回 `error()`。默认 `G = E`，所以 `e.error_or({})` 可用。

`error_or` 是 `value_or` 的镜像，适合"没出错就当作某个默认错误码（通常是'成功'码）"的场景，例如把 `expected<T, std::errc>` 转成 C 风格的状态码：`return r.error_or(std::errc{});`。

## 单子操作（[expected.object.monadic]）

[[P2505]] 加入的四个操作，各有 `&`、`const &`、`&&`、`const &&` 四个重载。规律是：**被传给 `f` 的那一侧决定 `Mandates`；被原样搬运的另一侧决定 `Constraints`**。

| 操作 | `f` 的实参 | 令 | *Constraints*（原样搬运的那一侧） | *Mandates* | 无值/无错误时 |
|---|---|---|---|---|---|
| `and_then` | *val* | `U = remove_cvref_t<invoke_result_t<F, decltype((val))>>` | `is_constructible_v<E, decltype(error())>` | `U` 是 `expected` 特化且 `U::error_type` 就是 `E` | `U(unexpect, error())` |
| `or_else` | `error()` | `G = remove_cvref_t<invoke_result_t<F, decltype(error())>>` | `is_constructible_v<T, decltype((val))>` | `G` 是 `expected` 特化且 `G::value_type` 就是 `T` | `G(in_place, val)` |
| `transform` | *val* | `U = remove_cv_t<invoke_result_t<…>>` | `is_constructible_v<E, decltype(error())>` | `U` 是合法值类型；非 void 时 `U u(invoke(…));` 良构 | `expected<U, E>(unexpect, error())` |
| `transform_error` | `error()` | `G = remove_cv_t<invoke_result_t<…>>` | `is_constructible_v<T, decltype((val))>` | `G` 是 `unexpected` 的合法实参；`G g(invoke(…));` 良构 | `expected<T, G>(in_place, val)` |

（上表为 `&` / `const &` 重载；`&&` 版本把 `val`、`error()` 换成 `std::move(val)`、`std::move(error())`，¶5–8、¶13–16、¶21–24、¶29–32。）

几点解读：

- **为什么搬运侧是 *Constraints***：以 `and_then` 为例，若 `E` 只能移动、而你在左值上调用 `and_then`，`&` 重载需要**复制** `error()` 到结果里，做不到——这个重载应当**不可行**，而不是硬错误。于是在左值上调用失败、在右值上调用（`std::move(e).and_then(f)`）成功，用户得到清晰的重载决议错误。
- **`and_then` 不能换错误类型**：*Mandates* 要求 `U::error_type` 与 `E` 完全相同。想换错误类型，先 `transform_error`。同理 `or_else` 不能换值类型。
- **`transform` 可以产生 `expected<void, E>`**：¶19 只在 `U` 非 void 时检查声明；¶20.3：若 `U` 是 void，求值 `invoke(f, val)` 然后返回 `expected<U, E>()`。
- **直接非列表初始化**：`transform` 的结果 *val* 以 `invoke(...)` 直接非列表初始化（¶20.2），`transform_error` 的 *unex* 同理（¶28），不要求结果类型可移动——与 optional 的 `transform` 是同一个设计，libc++ 用 `__expected_construct_in_place_from_invoke_tag` / `__expected_construct_unexpected_from_invoke_tag` 两个私有标签实现。

```cpp run title="monadic.cpp" ok
#include <cassert>
#include <expected>
#include <string>

enum class Err { empty, too_big };

std::expected<int, Err> nonempty(std::string s) {
  if (s.empty()) return std::unexpected(Err::empty);
  return static_cast<int>(s.size());
}
std::expected<int, Err> small(int n) {
  if (n > 3) return std::unexpected(Err::too_big);
  return n;
}

int main() {
  auto r = nonempty("ab")
             .and_then(small)                          // f 必须返回 expected<_, Err>
             .transform([](int n) { return n * 10; }); // 值 → 值
  assert(r == 20);

  auto e = nonempty("abcdef").and_then(small);
  assert(e.error() == Err::too_big);

  // transform_error：只改错误类型；or_else：从错误中恢复
  std::expected<int, std::string> msg =
      e.transform_error([](Err x) { return std::string(x == Err::empty ? "empty" : "too big"); });
  assert(msg.error() == "too big");
  auto recovered = e.or_else([](Err) { return std::expected<int, Err>(0); });
  assert(recovered == 0);

  // transform 可以产生 expected<void, E>
  auto v = r.transform([](int) {});
  static_assert(std::is_same_v<decltype(v), std::expected<void, Err>>);
  assert(v.has_value());

  assert(e.error_or(Err::empty) == Err::too_big);
  assert(r.error_or(Err::empty) == Err::empty);
  assert(e.value_or(-1) == -1);
}
```

## 相等比较（[expected.object.eq]）

三个隐藏友元：

- `operator==(const expected& x, const expected<T2, E2>& y)`，`requires (!is_void_v<T2>)`：¶1 *Constraints* `*x == *y` 与 `x.error() == y.error()` 都良构且可转换为 `bool`；¶2 状态不同则 `false`，都有值比值，都是错误比错误。
- `operator==(const expected& x, const T2& v)`：¶3 *Constraints* `T2` 不是 `expected` 的特化，`*x == v` 良构；¶4 有值则 `*x == v`，否则 `false`。
- `operator==(const expected& x, const unexpected<E2>& e)`：¶5 *Constraints* `x.error() == e.error()` 良构；¶6 是错误则比较错误，否则 `false`。

没有 `<`、`<=>`——"成功"与"失败"之间没有自然的序。`!=` 由 C++20 的重写规则自动得到（[[over.match.oper]]）。注意这里全是 *Constraints*，而 `unexpected` 自己的 `operator==` 用的是 *Mandates*（见 [[expected]]），两者对概念检测的友好程度不同。

`requires (!is_void_v<T2>)` 把与 `expected<void, E2>` 的比较排除在外：一边有值、一边 void 的比较没有意义，`*y` 也不可用。

## 常见误区

!!! pitfall "默认构造的 expected 是“成功”"
    `std::expected<int, E> e;` 有值，`*e == 0`。不要把它当作"尚未赋值"的占位状态。

!!! pitfall "`e = {}` 不是重置"
    它把 `e` 设成"成功、值为 `T{}`"。`expected` 没有重置操作，也不需要。

!!! pitfall "只能移动的 E 与 value()"
    `expected<T, std::unique_ptr<ErrInfo>>` 可以用，但 `value()` 违反 *Mandates*（`E` 不可复制构造）是硬错误；只能用 `has_value()` + `*e` / `error()`。

## 思考题

!!! question "思考题 1"
    为什么 [expected.object.assign] ¶4.5 只要求 "`T` **或** `E` 可 nothrow 移动构造"，而不是两者都要？请分别考虑"值→错误"和"错误→值"两个方向的切换。

<details markdown="1">
<summary>展开查看答案与解析</summary>

设 `T` 可 nothrow 移动、`E` 不行。错误→值（新类型 `T`）：若 `T` 可从实参 nothrow 构造走第 1 分支；否则 `T` 可 nothrow 移动，走第 2 分支（先构造临时 `T`，再销毁 `E`、移动进来），安全。值→错误（新类型 `E`）：若 `E` 可从实参 nothrow 构造走第 1 分支；否则 `E` 不可 nothrow 移动，只能走第 3 分支——备份**旧值 `T`**，而 `T` 可 nothrow 移动，回滚安全。两个方向都有路可走。反之亦然。只有两者都不可 nothrow 移动时，某个方向会落到"第 3 分支但回滚可能抛"的境地，所以只排除这一种组合。
</details>

!!! question "思考题 2"
    `optional::emplace` 允许 `T` 的构造抛异常，`expected::emplace` 却要求 `is_nothrow_constructible_v`。如果 `expected::emplace` 也允许抛异常，标准应当怎么写它的 *Effects* 才能维持"永不为空"？代价是什么？

<details markdown="1">
<summary>展开查看答案与解析</summary>

它得像 *reinit-expected* 一样：要么先在临时量中构造新值再移动进来（要求 `T` nothrow 可移动，且新值会多一次移动——这就违背了"原地构造"的初衷，并且对不可移动的 `T` 无法实现），要么先备份旧对象再尝试原地构造、失败回滚（多一次移动，并要求旧对象类型 nothrow 可移动）。无论哪种，`emplace` 都不再是"零额外开销的原地构造"。标准选择把 `emplace` 限定在 nothrow 构造的场景，其余情况交给赋值运算符和 *reinit-expected*。
</details>

## 小结

| 主题 | 要点 |
|---|---|
| 存储 | *has_val* + `union { remove_cv_t<T> val; E unex; }`，永远恰好一个活跃 |
| 合法类型 | `T`：void 或完整非数组对象类型，非 `in_place_t`/`unexpect_t`/`unexpected`；`E`：`unexpected` 的合法实参 |
| 默认构造 | 值初始化 `T`，**有值** |
| 区分值与错误 | `unexpected<X>` 永远是错误（(23.4)）；`unexpect` 标签原地构造错误 |
| 条件平凡 | 5 个特殊成员随 `T`、`E` 平凡；libc++ 23 赋值尚未平凡 |
| 切换类型的赋值 | *reinit-expected* 三段式，强异常保证；`T`、`E` 都可能抛移动时弃置 |
| `emplace` | `noexcept`，要求 nothrow 构造 |
| `*` / `->` / `error()` | 加固前置条件（`error()` 要求无值） |
| `value()` | *Mandates* `E` 可复制；抛 `bad_expected_access<E>` |
| `value_or` / `error_or` | 镜像对称，都是 *Mandates* |
| 单子操作 | 传给 `f` 的一侧 → *Mandates*；原样搬运的一侧 → *Constraints*；`and_then` 不换错误类型 |
| 比较 | 只有 `==`，全是 *Constraints* |
