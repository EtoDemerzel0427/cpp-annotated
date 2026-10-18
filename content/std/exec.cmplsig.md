---
title: 完成签名
summary: completion_signatures<Sigs...> 把一个发送器可能的完成编码成类型；get_completion_signatures<Sndr, Env> 是 consteval 函数，用"抛异常"报告类型错误、用 dependent_sender_error 报告"需要环境"；value_types_of_t / error_types_of_t / sends_stopped 从签名集合里取出类型
status: done
covers: exec.getcomplsigs
papers: P2300R10
related: exec.async.ops, exec.snd, exec.connect, exec.recv, exec.adapt, expr.const
tags: 标准库, std::execution, 完成签名, consteval, 类型计算
updated: 2026-10-18
---

[[exec.async.ops#13]] 说：发送器类型和环境类型一起决定异步操作所有可能的完成签名。本页讲这个"决定"在代码里的形态：

- [exec.cmplsig]：类模板 `completion_signatures<Fns...>`，以及从中提取类型的 `value_types_of_t`、`error_types_of_t`、`sends_stopped`；
- [exec.getcomplsigs]：`get_completion_signatures<Sndr, Env...>()`——怎样问一个发送器"你会怎样完成"。

为什么要在**类型**层面知道这些？因为几乎所有算法都需要提前知道：`sync_wait` 要决定返回 `optional<tuple<什么>>`；`when_all` 要决定把结果存进什么样的 tuple；`let_value` 要知道回调会收到什么、会返回哪种发送器，从而预留操作状态的空间；`connect` 要检查接收器能不能接住每一种完成。这一切都在编译期完成，运行期没有任何类型擦除。

## completion_signatures（[exec.cmplsig]）

¶1 `completion_signatures` 是编码一组完成签名的类型。

¶4 能作为它模板实参的函数类型（*completion-signature*）只有三种形式：

- ¶4.1 `set_value_t(Vs...)`，`Vs` 是对象类型或引用类型的包；
- ¶4.2 `set_error_t(Err)`，`Err` 是对象类型或引用类型；
- ¶4.3 `set_stopped_t()`。

```cpp
template<completion-signature... Fns>
struct completion_signatures {
  template<class Tag> static constexpr size_t count-of(Tag) { return see below; }
  template<class Fn>  static constexpr void for-each(Fn&& fn) {        // exposition only
    (fn(static_cast<Fns*>(nullptr)), ...);
  }
};
```

¶9 *count-of*(tag) 返回 `Fns...` 中形如 `Tag(Ts...)` 的个数。*for-each* 对每个签名用一个**空函数指针**调用 `fn`——这是把类型当值传递的技巧：`fn` 的形参写成 `Tag(*)(Ts...)`，模板实参推导就能拆出 `Tag` 和 `Ts...`。标准算法的 *check-types* 大量使用它：

```cpp
// then 的类型检查（[exec.then] ¶5）
auto cs = get_completion_signatures<child-type<Sndr>, FWD-ENV-T(Env)...>();
auto fn = []<class... Ts>(set_value_t(*)(Ts...)) {
  if constexpr (!invocable<remove_cvref_t<data-type<Sndr>>, Ts...>)
    throw unspecified-exception();
};
cs.for-each(overload-set{fn, [](auto){}});   // 只检查 value 签名，其余忽略
```

注意 *count-of* 和 *for-each* 都是阐述用的——你在代码里不能调用它们。

¶2 例 1 展示了一个声明了五种完成的发送器：

```cpp
struct my_sender {
  using sender_concept = sender_tag;
  using completion_signatures =
    execution::completion_signatures<
      set_value_t(), set_value_t(int, float),
      set_error_t(exception_ptr), set_error_t(error_code),
      set_stopped_t()>;
};
```

意思是：对接收器 `rcvr`，它可能调用 `set_value(rcvr)`、`set_value(rcvr, int{…}, float{…})`、`set_error(rcvr, exception_ptr{…})`、`set_error(rcvr, error_code{…})`、`set_stopped(rcvr)` 之一。

!!! lawyer "这个例子与规范文字之间有落差"
    例子用**成员类型别名** `completion_signatures` 声明签名。但按 [exec.getcomplsigs] ¶1、¶3 的规范文字，`get_completion_signatures` 只查找**静态成员函数模板** `remove_reference_t<Sndr>::template get_completion_signatures<Sndr, Env...>()`；类型别名不在查找范围内。按字面推演，`my_sender` 既没有那个成员函数模板、也不是可等待体，于是 `get_completion_signatures<my_sender>()` 走到 ¶3.4，抛出 `dependent_sender_error`。例子不具规范效力；写新代码时应提供静态成员函数：

    ```cpp
    struct my_sender {
      using sender_concept = std::execution::sender_tag;
      template<class Self, class... Env>
      static consteval auto get_completion_signatures() {
        return std::execution::completion_signatures<
          std::execution::set_value_t(int), std::execution::set_stopped_t()>{};
      }
      // ... connect ...
    };
    ```

### gather-signatures 与三个公开别名（¶5–8）

*gather-signatures*<Tag, Completions, Tuple, Variant>：从 `Completions` 中挑出返回类型为 `Tag` 的签名，第 n 个签名的形参包为 `Tsn`，结果是

```text
Variant< Tuple<Ts0...>, Tuple<Ts1...>, …, Tuple<Tsm-1...> >
```

¶7 注 1：*META-APPLY* 绕一道 `indirect-meta-apply<always-true<As...>>`，是为了允许把**非变参**模板（比如 `optional`、`type_identity_t`）当作 `Tuple`/`Variant` 传进来——直接写 `T<As...>` 时，把包展开到非变参模板的形参上会让模板在定义时就出问题。

基于它的三个公开设施：

```cpp
template<class Sndr, class Env = env<>,
         template<class...> class Tuple = decayed-tuple,
         template<class...> class Variant = variant-or-empty>
  requires sender_in<Sndr, Env>
using value_types_of_t = gather-signatures<set_value_t, completion_signatures_of_t<Sndr, Env>, Tuple, Variant>;

template<class Sndr, class Env = env<>, template<class...> class Variant = variant-or-empty>
  requires sender_in<Sndr, Env>
using error_types_of_t = gather-signatures<set_error_t, completion_signatures_of_t<Sndr, Env>, type_identity_t, Variant>;

template<class Sndr, class Env = env<>>
  requires sender_in<Sndr, Env>
constexpr bool sends_stopped = !same_as<type-list<>, gather-signatures<set_stopped_t, …, type-list, type-list>>;
```

对 `my_sender` 那组签名（假设它能被正确读取）：

| 表达式 | 结果 |
|---|---|
| `value_types_of_t<S>` | `variant<tuple<>, tuple<int, float>>` |
| `value_types_of_t<S, env<>, tuple, type_list>` | `type_list<tuple<>, tuple<int, float>>`（换掉 Variant） |
| `error_types_of_t<S>` | `variant<exception_ptr, error_code>` |
| `sends_stopped<S>` | `true` |

`decayed-tuple` 是 `tuple<decay_t<Ts>...>`；*variant-or-empty* 在没有任何元素时给出一个不可构造的空类型（[[exec]] 中的 [execution.syn] ¶1）。

`sync_wait` 就是用 `value_types_of_t<Sndr, sync-wait-env, decayed-tuple, type_identity_t>` 计算返回类型的：`type_identity_t` 作为 `Variant` 只接受**一个**实参，所以当发送器有不止一种 value 签名时类型非良构——这正是"`sync_wait` 要求恰好一种 value 完成"的实现方式（[[exec.consumers]]）。

## get_completion_signatures（[exec.getcomplsigs]）

```cpp
template<class Sndr, class... Env>
  consteval auto get_completion_signatures() -> valid-completion-signatures auto;

template<class Sndr, class... Env>
  requires sender_in<Sndr, Env...>
using completion_signatures_of_t = decltype(get_completion_signatures<Sndr, Env...>());
```

先注意形式：它是一个**无实参的 `consteval` 函数模板**，返回一个 `completion_signatures` 特化的**值**（空对象）。早期 P2300 用类型别名 + 元编程计算签名；改成 `consteval` 函数之后，签名计算可以用普通的 `if constexpr`、循环，而且最重要的是——**可以抛异常**。在常量求值中抛出且未捕获的异常使表达式不是常量表达式（[[expr.const]]），`sender_in` 据此为 false（[[exec.snd]]）；而实现可以在诊断中带上异常对象携带的信息。

¶2 *Constraints*：`sizeof...(Env) <= 1`。

¶1 几个辅助定义：

- `except`：一个未指定类类型 `Except` 的右值，`Except` 可移动构造且派生自 `exception`；
- ***CHECKED-COMPLSIGS*(e)**：若 `e` 是核心常量表达式且类型是 `completion_signatures` 的特化，就是 `e`；否则是 `(e, throw except, completion_signatures())`——即先求值 `e`（若它抛异常，异常照常传出），没抛的话再抛一个 `except`；
- ***get-complsigs***<Sndr, Env...>()：`remove_reference_t<Sndr>::template get_completion_signatures<Sndr, Env...>()`——发送器的**静态成员函数模板**，第一个模板实参是（可能带引用、cv 的）发送器类型本身，所以同一个发送器可以对左值/右值给出不同的签名；
- `NewSndr`：不带环境时是 `Sndr`；带环境时是 `decltype(transform_sender(declval<Sndr>(), declval<Env>()...))`——**先按 domain 变换**，再问签名（[[exec.snd.transform]]）。这保证报告的签名是**真正会被 connect 的那个发送器**的签名。

¶3 效果：`return e;`，`e` 依次为：

- ¶3.1 *CHECKED-COMPLSIGS*(*get-complsigs*<NewSndr, Env...>())，若良构；
- ¶3.2 否则 *CHECKED-COMPLSIGS*(*get-complsigs*<NewSndr>())，若良构——发送器只提供了"不看环境"的版本；
- ¶3.3 否则，若 `NewSndr` 是可等待体（*is-awaitable*<NewSndr, *env-promise*<Env>...>），是
  ```cpp
  completion_signatures<SET-VALUE-SIG(await-result-type<NewSndr, env-promise<Env>...>),
                        set_error_t(exception_ptr), set_stopped_t()>
  ```
  ——可等待体的签名是固定格式（[[exec.as.awaitable]]）；
- ¶3.4 否则，若没有环境：`(throw dependent-sender-error(), completion_signatures())`，*dependent-sender-error* 是 `dependent_sender_error` 或公开无歧义地派生自它的未指定类型；
- ¶3.5 否则：`(throw except, completion_signatures())`。

¶3.4 与 ¶3.5 的区别值得体会：同样是"问不出签名"，不带环境时的含义是"也许给了环境就能问出来"（依赖），带了环境还问不出就是真正的错误。

### 两条语义要求（¶4–5）

¶4 若 `completion_signatures_of_t<Sndr>` 和 `completion_signatures_of_t<Sndr, Env>` 都良构，前者必须是后者的**超集**，且多出来的只能是 error 或 stopped 完成。直觉：不知道环境时只能做保守估计；知道了环境之后可以排除一些可能（比如环境的停止令牌是 `never_stop_token`，就可以去掉 `set_stopped_t()`），但不能凭空多出新的值类型。

¶5 设 `rcvr` 是右值接收器，`Sndr` 满足 `sender_in<Sndr, env_of_t<Rcvr>>`，`Sigs...` 是其签名。若发送器或其操作状态使 `CSO(rcvr, args...)` 被**潜在求值**（[[basic.def.odr]]），则必须存在某个 `Sig` 使 *MATCHING-SIG*(decayed-typeof<CSO>(decltype(args)...), Sig) 成立。这就是 [[exec.snd.concepts#3]] 中"允许的完成"在发送器作者一侧的义务：**声明的签名必须覆盖实际可能的完成**。

!!! pitfall "\"潜在求值\"比\"实际执行\"宽"
    ¶5 说的是**潜在求值**，不是"运行时真的会走到"。即使某条 `set_error` 只在一个运行期永远不成立的分支里，只要它出现在被实例化的代码中、是潜在求值的，就必须有对应的签名。反过来，实现可以利用 `if constexpr` 让不可能的分支根本不实例化，从而缩小签名集合——标准算法的阐述代码里大量的 `if constexpr (!nothrow)` 就是在做这件事：只有当某个操作可能抛异常时，才会出现 `set_error(…, current_exception())`，进而出现 `set_error_t(exception_ptr)` 签名。

## dependent_sender_error

```cpp
struct dependent_sender_error : exception {};
```

这是本章唯一一个公开的异常类型，专门用来在 `consteval` 签名计算中表达"需要环境"。用户写依赖发送器时应该这样做：

```cpp title="dependent-sender.cpp"
namespace ex = std::execution;

struct current_scheduler_sender {           // 以环境中的调度器完成，类似 read_env(get_scheduler)
  using sender_concept = ex::sender_tag;

  template<class Self, class... Env>
  static consteval auto get_completion_signatures() {
    if constexpr (sizeof...(Env) == 0) {
      throw ex::dependent_sender_error();   // 不知道环境，无法确定值类型
    } else {
      using Sch = decltype(ex::get_scheduler(std::declval<const Env&>()...));
      return ex::completion_signatures<ex::set_value_t(Sch)>{};
    }
  }
  // ... connect ...
};
```

`if constexpr` 的两个分支只有一个被实例化。`Env` 为空时，实例化的分支里没有 `return`，返回类型推导为 `void`——这无妨，因为这个调用总是以异常结束，[exec.getcomplsigs] ¶1 的 *CHECKED-COMPLSIGS* 会让异常原样传出。这种"用抛异常表达类型层面的失败"的写法，是 C++26 允许常量求值中抛出异常之后才变得自然的。

## 思考题

!!! question "1. 为什么 get_completion_signatures 的第一个模板实参带着引用？"
    *get-complsigs* 把 `Sndr`（可能是 `S&`、`const S&`、`S`）原样传给发送器的静态成员。这有什么用？

<details markdown="1">
<summary>答案</summary>

同一个发送器作为左值和右值被 connect 时，可能以不同的值类别发出结果。例如一个持有 `std::string` 的 `just`：右值 connect 时可以把字符串**移动**进操作状态，完成时 `set_value(rcvr, std::move(s))`；左值 connect 时必须复制。若发送器想对左值版本发出 `const std::string&`（引用自身存储）之类的签名，就需要知道自己是以什么值类别被 connect 的。另外，[[exec.snd.concepts#9]] 规定不可复制的标准发送器不提供左值 `connect`，此时对 `S&` 的签名计算也应当失败。
</details>

!!! question "2. 签名集合可以比实际大吗？"
    一个发送器声明了 `set_error_t(exception_ptr)`，但实际上永远不会以 error 完成。这违反规则吗？

<details markdown="1">
<summary>答案</summary>

对用户发送器不违反：¶5 只要求实际可能的完成被覆盖，[[exec.snd.concepts#3]] 的"允许的完成"也只是单向包含。代价是下游会为不可能发生的情况付出代价：`sync_wait` 照样要准备 `exception_ptr`，`when_all` 的错误 variant 多一个成员，`spawn` 根本不接受有 error 完成的发送器（[[exec.spawn]]）。对标准算法的默认实现则有更严格的要求：[[exec.snd.general#2]] 规定签名集合**恰好**等于潜在求值的完成；[[exec.adapt.general#4]] 还专门允许实现在确定不会发出 `exception_ptr` 错误时省略那个签名。
</details>

## 小结

- `completion_signatures<Fns...>`：每个 `Fn` 是 `set_value_t(Vs...)`、`set_error_t(E)` 或 `set_stopped_t()`。
- `value_types_of_t`/`error_types_of_t`/`sends_stopped`：按标签收集签名，`Tuple`/`Variant` 可替换。
- `get_completion_signatures<Sndr, Env>()`：`consteval`；先 `transform_sender`，再问静态成员 `get_completion_signatures<Sndr, Env...>()`，再退到无环境版本，再退到可等待体；都不行就抛异常。
- 不带环境问不出来 → `dependent_sender_error`（依赖发送器）；带环境问不出来 → 一般异常（类型错误）。
- 声明的签名必须覆盖所有潜在求值的完成；无环境签名集是有环境签名集的超集，差别只能是 error/stopped。
