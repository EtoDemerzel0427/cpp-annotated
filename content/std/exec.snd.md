---
title: 发送器
summary: sender / sender_in / dependent_sender 概念；默认实现的完成签名、完成 domain、完成调度器怎样确定；以及读懂所有标准算法所需的阐述用骨架——make-sender、basic-sender、basic-operation、basic-receiver、impls-for，FWD-ENV / JOIN-ENV / SCHED-ENV，TRY-SET-VALUE 等
status: draft
covers: exec.snd.general, exec.snd.expos, exec.snd.concepts
papers: P2300R10
related: exec.async.ops, exec.cmplsig, exec.connect, exec.snd.transform, exec.factories, exec.adapt, exec.recv, exec.opstate, dcl.struct.bind
tags: 标准库, std::execution, 发送器, 概念, 阐述用
updated: 2026-10-18
---

[exec.snd] 是第 33 章最大的一个二级条款，本站把它拆成多页：

- 本页：总则 [exec.snd.general]、阐述用实体 [exec.snd.expos]、发送器概念 [exec.snd.concepts]；
- [[exec.cmplsig]]：`get_completion_signatures` 与 `completion_signatures`；
- [[exec.connect]]：`connect`；
- [[exec.snd.transform]]：domain、`transform_sender`、`apply_sender`；
- [[exec.as.awaitable]]：[exec.awaitable] 中的可等待体辅助设施；
- [[exec.factories]]、[[exec.adapt]]、[[exec.on]]、[[exec.let]]、[[exec.bulk]]、[[exec.when.all]]、[[exec.spawn]]、[[exec.consumers]]：具体算法。

本页的后半部分是"读懂规范的工具箱"。标准没有逐个写出每个算法的发送器类、接收器类、操作状态类，而是先定义一个通用骨架 *basic-sender*，再让每个算法只特化一个 *impls-for*<Tag>，说明"我和默认行为哪里不同"。看懂这套骨架之后，后面每个算法的规范都只有十几行。

## 发送器概念（[exec.snd.concepts]）

¶1 三个公开概念和一个阐述用概念：

```cpp
template<class Sndr>
  concept is-sender = derived_from<typename Sndr::sender_concept, sender_tag>;

template<class Sndr>
  concept enable-sender = is-sender<Sndr> || is-awaitable<Sndr, env-promise<env<>>>;

template<class Sndr>
  inline constexpr bool enable_sender = enable-sender<Sndr>;

template<class Sndr>
  concept sender =
    enable_sender<remove_cvref_t<Sndr>> &&
    requires (const remove_cvref_t<Sndr>& sndr) { { get_env(sndr) } -> queryable; } &&
    move_constructible<remove_cvref_t<Sndr>> &&
    constructible_from<remove_cvref_t<Sndr>, Sndr>;

template<class Sndr, class... Env>
  concept sender_in =
    sender<Sndr> && (sizeof...(Env) <= 1) && (queryable<Env> &&...) &&
    is-constant<get_completion_signatures<Sndr, Env...>()>;

template<class Sndr>
  concept dependent_sender =
    sender<Sndr> && bool_constant<is-dependent-sender-helper<Sndr>()>::value;

template<class Sndr, class Rcvr>
  concept sender-to =
    sender_in<Sndr, env_of_t<Rcvr>> &&
    receiver-of<Rcvr, completion_signatures_of_t<Sndr, env_of_t<Rcvr>>> &&
    requires (Sndr&& sndr, Rcvr&& rcvr) { connect(std::forward<Sndr>(sndr), std::forward<Rcvr>(rcvr)); };
```

**`sender`** 是一个很弱的概念：类型选择加入（声明 `sender_concept`，或者它是一个可等待体），有属性，可移动。它**不**检查能否 connect、会怎样完成。注意 *enable-sender* 的第二个分支：**任何可等待体（awaitable）自动是发送器**——只要它在一个只有空环境的协程里可以被 `co_await`（*env-promise* 见 [[exec.as.awaitable]]）。这让已有的协程类型（如各种 `task` 实现）无需修改就能当发送器用，connect 时由 *connect-awaitable* 包一层协程（[[exec.connect]]）。

¶4 *Remarks*：按 [[namespace.std]]，用户可以为 cv 无限定的程序定义类型特化 `enable_sender`：对模型化 `sender` 的类型特化为 true，对不模型化的特化为 false。特化必须可用于常量表达式，类型为 `const bool`。这是给"不方便加 `sender_concept` 成员"的第三方类型准备的后门。

**`sender_in<Sndr, Env>`** 才是"能用"的发送器：在环境 `Env` 下，`get_completion_signatures<Sndr, Env>()` 是一个**常量表达式**（*is-constant* 是一个接受任意非类型模板实参、恒为 true 的概念；把调用放进模板实参，就强制它在编译期求值成功）。`get_completion_signatures` 是 `consteval` 函数，遇到类型错误时会**抛异常**（[[exec.cmplsig]]），抛异常的调用不是常量表达式，于是 `sender_in` 为 false。最多一个环境：`sender_in<S>` 表示"不需要环境就能确定签名"。

**`dependent_sender<Sndr>`**：调用 `get_completion_signatures<Sndr>()`（不给环境）时抛出 `dependent_sender_error`。*is-dependent-sender-helper* 是一个带函数 try 块的 `consteval` 函数，捕获该异常返回 true。¶2：`sender<Sndr>` 为 true 且 `dependent_sender<Sndr>` 为 false 的类型，就是 [[exec.async.ops#13]] 所说的[[g:non-dependent-sender|非依赖发送器]]。

!!! example "依赖与非依赖"
    - `just(1)`：签名永远是 `set_value_t(int)`，非依赖，`sender_in<decltype(just(1))>` 为 true。
    - 一个用户发送器，它的值类型取决于环境里的调度器类型：它的 `get_completion_signatures<Self>()`（不带环境）应当 `throw dependent_sender_error()`，`get_completion_signatures<Self, Env>()` 才返回具体签名。它是**依赖**发送器：`sender_in<S>` 为 false，`sender_in<S, Env>` 为 true。
    - `then(那个用户发送器, f)`：[[exec.adapt.general#3]] ¶3.5 只保证"子发送器都非依赖时适配器非依赖"；子发送器依赖时，从行文看似乎希望适配器也依赖。不过标准适配器的签名计算机制（下文 ¶47）在不给环境时会拿 `env<>` 去检查子发送器，这两处如何配合，草案文字并不清楚，见下文的 lawyer 框。
    - `read_env(get_scheduler)` 的情况也很微妙，见 [[exec.factories]]。

¶3 定义**允许的完成**（[[g:permissible-completion]]）：完成签名出现在 `completion_signatures_of_t<Sndr, Env>` 中的完成操作。`Sndr` 与 `Env` **模型化** `sender_in<Sndr, Env>`，当且仅当 connect 并启动后所有潜在求值的完成操作都是允许的完成。也就是说，类型层面声明的签名集合必须**覆盖**实际可能发生的完成——声明多了可以（[[exec.getcomplsigs#4]] 允许无环境的签名集是有环境时的超集），少了不行。

**`sender-to<Sndr, Rcvr>`**（阐述用）：发送器在接收器的环境下有签名、接收器能接受所有签名、`connect` 良构。这是"可以 connect"的完整条件。

¶5 *sender-of*<Sndr, Values...> 与 *sender-in-of*<Sndr, Env, Values...>：发送器恰好有一个 value 完成签名，且它与 `set_value_t(Values...)` 匹配（*MATCHING-SIG*）。比如 [[exec.sched#2]] 用 *sender-in-of*<schedule_result_t<Sch>, Env> 要求调度发送器的 value 完成是 `set_value_t()`。

¶6 `tag_of_t<Sndr>`：若 `auto&& [tag, data, ...children] = sndr;` 良构（结构化绑定，[[dcl.struct.bind]]），就是 `decltype(auto(tag))`；否则非良构。所有标准发送器都可以这样拆开，第一个元素就是它的**标签**——通常是创建它的 CPO 的类型，如 `then_t`。¶7 的 *sender-for*<Sndr, Tag> 就是"`Sndr` 是 `Tag` 这个算法造出来的发送器"。domain 定制正是靠它识别发送器（[[exec.snd.transform]]）。

¶8 *SET-VALUE-SIG*(T)：`T` 为 cv `void` 时是 `set_value_t()`，否则 `set_value_t(T)`。

¶9 标准库的发送器类型：
- 总是提供接受**右值**发送器的 `connect` 成员重载；
- 只有在模型化 `copy_constructible` 时才提供接受**左值**发送器的 `connect` 重载。

于是"能否重复使用一个发送器"由它是否可复制决定：持有 `unique_ptr` 的 `just(std::make_unique<int>(1))` 只能 `std::move` 后 connect 一次。

## 总则：默认实现的完成行为（[exec.snd.general]）

¶1 [[exec.factories]] 和 [[exec.adapt]] 中的算法都是**可定制**的，每个都有默认实现。设 `sndr` 是某算法默认实现的结果（或与之相等的对象），`rcvr` 是环境为 `env` 的接收器且 *sender-to* 成立：connect 并启动后，**必然**会潜在求值一组以（等于）`rcvr` 为第一实参的完成操作。

¶2 设 `Sigs` 是这组完成操作对应的签名，`CS` 是 `get_completion_signatures<Sndr, Env>()` 的类型。则 `CS` 是以 `Sigs` 为模板实参集合的 `completion_signatures` 特化。若 `Sigs` 都不依赖 `Env`，则 `get_completion_signatures<Sndr>()` 良构，类型就是 `CS`。

换句话说，标准算法报告的签名**恰好**是它实际可能发出的那些——不多也不少。这一点很重要，因为下游（比如 `when_all` 检查"只有一种 value 完成"，`sync_wait` 计算返回类型）完全依赖签名的精确性。

¶3 **完成 domain**。每个完成操作可能在若干不同的执行代理上求值，取决于算法语义、接收器环境、子发送器的完成。对完成标签 `T`，设 `DsT` 是"所有可能求值 `T` 完成的执行代理所关联的 domain 标签"构成的包。若没有潜在求值的 `T` 完成，`get_completion_domain<T>(get_env(sndr), env)` 非良构；否则其类型是 *COMMON-DOMAIN*<DsT...>。

例 1：`sndr2 = then(sndr, fn)`。`sndr2` 的 value 完成 domain 与 `sndr` 相同；但若 `fn` 的调用可能抛异常，`sndr2` 的 error 完成可能来自两处——转发 `sndr` 的 error 完成，或者在 `sndr` 的 value 完成处捕获 `fn` 抛出的异常——于是它的 error 完成 domain 是 `sndr` 的 value 与 error 完成 domain 的 *COMMON-DOMAIN*。

¶4 **完成调度器**。若 `sndr` 能确定所有 `T` 完成都发生在某个调度器 `sch` 的代理上，则 `get_completion_scheduler<T>(get_env(sndr), env)` 良构，类型和值都是 `sch`；否则非良构。

例 2（续上例）：`sndr2` 的 value 完成调度器就是 `sndr` 的（如果有）；但只有当 `fn` 不会抛异常、或 `sndr` 没有 error 完成时，`sndr2` 才能报告 error 完成调度器——否则 error 可能在 `sndr` 的 value 完成调度器上（`fn` 抛异常时）或 error 完成调度器上发生，二者未必相同。

¶5 若选择了**用户提供**的算法实现（通过 domain 定制，[[exec.snd.transform]]）而非默认实现：

- ¶5.1 除非另有规定，`completion_signatures_of_t<Sndr, Env>` 中有而 `Sigs` 中没有的签名，只能对应 error 或 stopped 完成——定制实现**不能**引入新的 value 完成类型；
- ¶5.2 若 `Sigs` 不依赖 `Env`，则有无环境的签名必须一致。

¶6 本条款的一些函数模板会抛出 *unspecified-exception*：类型未指定，能被 `catch (exception&)` 捕获，但**不能**被 `catch (dependent_sender_error&)` 捕获。注 1：两个这样的异常不必同类型。这些异常在 `consteval` 的 `get_completion_signatures` 中抛出，用来报告类型错误（"你的 `then` 回调不能用这些值调用"），见 [[exec.cmplsig]]。

## 阐述用实体（[exec.snd.expos]）

### 成员定制的余地（¶1–2）

¶1 对标准库任何发送器类型的表达式 `sndr`，`sndr.affine()` 是否良构未指定；若良构，其求值满足 `affine` 算法（[[exec.affine]]）的语义要求。

¶2 同理，`sndr.as_awaitable(p)`（`p` 是承诺类型的对象）是否良构未指定；若良构，满足 `as_awaitable`（[[exec.as.awaitable]]）的语义。

这两条允许实现为特定发送器提供更高效的 `affine` / `as_awaitable`（比如 `just` 根本不需要切换调度器），而不改变可观察语义。

### 环境运算（¶4–10）

| 实体 | 定义 | 用途 |
|---|---|---|
| *FWD-ENV*(env) | `query(q, as...)`：`forwarding_query(q)` 为 false 时非良构，否则等价于 `env.query(q, as...)` | 适配器把环境传给子操作（[[exec.adapt.general#3]]）；*FWD-ENV-T*(Env) 是其类型 |
| *MAKE-ENV*(q, v) | 只回答 `q`，结果等于 `v` | 构造单项环境 |
| *JOIN-ENV*(e1, e2) | 先 `e1.query(...)`，不行再 `e2.query(...)` | 覆盖/补充环境 |
| *SCHED-ENV*(sch) | `query(get_start_scheduler)` 是 `sch` 的副本（prvalue）；`query(get_domain)` 等价于 `sch.query(get_domain)` | 告诉子操作"你在 `sch` 上被启动" |

¶7 这三个的结果可以**依赖上下文**：同样的实参在不同地方可以得到不同类型和值类别的表达式。这给实现留了余地（比如存引用还是存值）。

¶8 ***COMMON-DOMAIN*(domains...)**：若 `common_type_t<decltype(auto(domains))...>()` 良构，就是它；否则是 `indeterminate_domain<Ds...>()`（`Ds` 去重）。多个 domain 有公共类型（例如一个派生自另一个，或用户特化了 `common_type`）时取公共类型，否则得到一个"不确定"的 domain（[[exec.snd.transform]]）。

¶9 ***COMPL-DOMAIN*(Tag, sndr, envs)**：`get_completion_domain<Tag>(get_env(sndr), envs...)` 良构或 `envs` 为空时，取其类型的默认构造值；否则 `indeterminate_domain()`。

### 完成辅助（¶11）

- ***SET-VALUE*(rcvr, expr)**：`expr` 为 `void` 时 `(expr, set_value(std::move(rcvr)))`，否则 `set_value(std::move(rcvr), expr)`。
- ***TRY-EVAL*(rcvr, expr)**：`expr` 可能抛异常时，
  ```cpp
  try { expr; } catch(...) { set_error(std::move(rcvr), current_exception()); }
  ```
  否则就是 `expr`。
- ***TRY-SET-VALUE*(rcvr, expr)**：*TRY-EVAL*(rcvr, *SET-VALUE*(rcvr, expr))，`rcvr` 只求值一次。

这三个宏是"把普通函数调用接进发送器世界"的标准方式：计算结果，用 `set_value` 送出；计算抛异常，用 `set_error(exception_ptr)` 送出。`then` 的实现就是一行 *TRY-SET-VALUE*（[[exec.adapt]]）。

!!! lawyer "TRY-EVAL 包住了 set_value"
    *TRY-SET-VALUE* 把 `set_value(...)` 也放进了 `try` 块。`set_value` 本身是 noexcept 的，不会抛异常；但 `expr` 的结果作为实参传给 `set_value` 时可能要**构造形参**（如果接收器的 `set_value` 按值接收），这个构造发生在调用之前、属于调用表达式的一部分，可能抛异常。把它们一起包进 `try`，保证这种异常也变成 `set_error`。

### query-with-default 与 call-with-default（¶12–14、¶56–58）

`query-with-default(tag, env, value)`：`tag(env)` 良构就用它，否则用 `value`。`call-with-default(fn, value, args...)`：`fn(args...)` 良构就用它，否则 `value`。用于"环境里没有就用默认值"的地方，比如 `on` 取原调度器时，取不到就用 *not-a-scheduler*（[[exec.on]]）。

### emplace-from（¶15）

```cpp
template<callable Fun>
  requires is_nothrow_move_constructible_v<Fun>
struct emplace-from {
  Fun fun;
  using type = call-result-t<Fun>;
  constexpr operator type() && noexcept(nothrow-callable<Fun>) { return std::move(fun)(); }
  constexpr type operator()() && noexcept(nothrow-callable<Fun>) { return std::move(fun)(); }
};
```

注 1：用来把**不可移动**的类型就地放进 `tuple`、`optional`、`variant`。原理见 [[exec.opstate]]：容器内部用实参构造元素时触发转换函数，转换函数返回 prvalue，保证复制消除使元素被直接构造。

### on-stop-request（¶16）

一个持有 `inplace_stop_source&` 的函数对象，调用时 `request_stop()`。用作停止回调：外部令牌被请求停止时，转发到内部的 stop source（`when_all` 用它把外部取消传播给所有子操作，[[exec.when.all]]）。

### product-type（¶17–22）

```cpp
template<class T0, class T1, …, class Tn>
struct product-type {
  T0 t0; T1 t1; … Tn tn;
  template<size_t I, class Self> constexpr decltype(auto) get(this Self&& self) noexcept;
  template<class Self, class Fn>  constexpr decltype(auto) apply(this Self&& self, Fn&& fn) noexcept(see below);
};
```

一个可以做结构化绑定的"轻量 tuple"。注 2 说它是伪代码，可以用标准 C++ 以 tuple 式的实现近似，但要注意保持它是**聚合**、能用作结构化绑定的初始化器。`get<I>` 和 `apply` 都用 C++26 的**结构化绑定包**实现：

```cpp
auto& [...ts] = self;                          // ¶19：结构化绑定引入包
return std::forward_like<Self>(ts...[I]);      //      包索引
```

这类写法遍布 [exec]：`auto& [_, data, ...child] = sndr;` 是标准发送器最常见的拆包方式。`_` 是 C++26 的占位符名（可以重复声明而不冲突）。

### make-sender 与 basic-sender（¶23–49）——整个骨架的核心

```cpp
template<class Tag, class Data = see below, class... Child>
  constexpr auto make-sender(Tag tag, Data&& data, Child&&... child);
```

¶24 *Mandates*：`Tag` 是 `semiregular`；`Data` 满足 *movable-value*；每个 `Child` 是发送器；且结果类型 `Sndr` 满足 `dependent_sender<Sndr> || sender_in<Sndr>`。

最后一条意味着：**非依赖**发送器在**构造时**就检查类型错误。`then(just(1), [](std::string){})` 在调用 `then` 的那一行就非良构，而不是等到 connect 时才报一个几十层深的模板错误。*Recommended practice*：若 `sender_in<Sndr>` 的求值中 `get_completion_signatures` 抛出了未捕获的异常，实现应该在诊断信息中包含该异常的信息——C++26 允许在常量求值中抛出异常，于是"类型错误"可以作为一个带说明的异常对象报告，而不是一串模板实例化回溯。

¶25 返回 *basic-sender*<Tag, decay_t<Data>, decay_t<Child>...> 的 prvalue，用转发的实参直接列表初始化。¶26：`Data` 的默认模板实参是一个未指定的、平凡可复制的空类类型。

```cpp
template<class Tag, class Data, class... Child>
struct basic-sender : product-type<Tag, Data, Child...> {
  using sender_concept = sender_tag;
  using indices-for = index_sequence_for<Child...>;

  decltype(auto) get_env() const noexcept {
    auto& [_, data, ...child] = *this;
    return impls-for<Tag>::get-attrs(data, child...);
  }

  template<decays-to<basic-sender> Self, receiver Rcvr>
  auto connect(this Self&& self, Rcvr rcvr) noexcept(see below) -> basic-operation<Self, Rcvr> {
    return {std::forward<Self>(self), std::move(rcvr)};
  }

  template<decays-to<basic-sender> Self, class... Env>
  static constexpr auto get_completion_signatures();
};
```

所以每个标准发送器在概念上都是一个三段式的元组：**（标签, 数据, 子发送器...）**。`then(sndr, f)` 是 `{then, f, sndr}`；`just(1, 2)` 是 `{just, product-type{1, 2}}`；`when_all(a, b)` 是 `{when_all, {}, a, b}`。¶44：*basic-sender* 是否为聚合未指定；¶45：它可用作结构化绑定的初始化器（`tag_of_t` 依赖这一点）。

!!! lawyer "get-attrs 去哪了？"
    `basic-sender::get_env` 调用 `impls-for<Tag>::get-attrs`，但在本站所据的草案文字中，¶35 的 *default-impls* 并没有列出 *get-attrs* 成员，全文也只有这一处提到它。属性的实际内容由 [[exec.adapt.general#3]] ¶3.2–3.3（单子发送器转发子发送器属性、多子发送器为 `env<>` 加完成调度器/domain）和 [exec.snd.general] ¶3–4 规定，读规范时以那里为准即可。

¶47–49 `basic-sender::get_completion_signatures`：取 `Env...` 的第一个（没有就是 `env<>`）为 `E`。先求 *CHECK-TYPES*() = `impls-for<Tag>::check-types<Sndr, E>()`：

- 若它是核心常量表达式，`CS` 就是"connect 并 start 后**潜在求值**的那些完成操作"对应的签名集合；
- 否则（非良构的情况被 ¶48 的约束排除，所以这里是"抛了异常"）`CS` 是 `completion_signatures<>`，但效果里会先执行 *CHECK-TYPES*()，于是异常传播出去。

这是一个很特别的规范手法：签名集合**不是**由一个类型计算公式给出，而是由"阐述代码中实际潜在求值了哪些 `set_*` 调用"决定的。读 `then` 的 *impls-for* 时，你看到 `TRY-SET-VALUE(rcvr, invoke(fn, args...))`，就知道它会产生 `set_value_t(invoke 的结果)`，在 `invoke` 可能抛异常时还会产生 `set_error_t(exception_ptr)`。

¶42 注 4：对任意 `T`、`S`、`E...`，`impls-for<T>::check-types<S, E...>()` 要么非良构，要么求值时抛异常，要么是核心常量表达式；是核心常量表达式时，`S, E...` 唯一确定一个签名集合。

!!! lawyer "不给环境时，¶47 用的是 env<>"
    ¶47 规定 `E` 是 "`Env...` 中的第一个，没有就是 `env<>`"。于是 `get_completion_signatures<Sndr>()`（不带环境）对标准适配器而言，实际上是拿**空环境** `env<>` 去跑 *check-types*，子发送器也是在 *FWD-ENV-T*(env<>) 下被检查的。而 [exec.snd.general] ¶2 与 [[exec.adapt.general#3]] ¶3.5 的说法暗示"依赖性"应当从子发送器传到父发送器。按字面读，一个在空环境下抛出普通异常（而非 `dependent_sender_error`）的子发送器会让父发送器既非依赖、也不满足 `sender_in`。本站不对委员会的意图作推断，只提醒：涉及依赖发送器与标准适配器的组合时，以实现的实际行为与后续草案为准。

### basic-state、basic-receiver、basic-operation（¶27–34）

```cpp
template<class Sndr, class Rcvr>
struct basic-state {
  basic-state(Sndr&& sndr, Rcvr&& rcvr) noexcept(see below)
    : rcvr(std::move(rcvr)),
      state(impls-for<tag_of_t<Sndr>>::get-state(std::forward<Sndr>(sndr), rcvr)) {}
  Rcvr rcvr;
  state-type<Sndr, Rcvr> state;
};

template<class Sndr, class Rcvr, class Index>
struct basic-receiver {
  using receiver_concept = receiver_tag;
  template<class... Args> void set_value(Args&&... args) && noexcept {
    complete(Index(), op->state, op->rcvr, set_value_t(), std::forward<Args>(args)...);
  }
  // set_error、set_stopped 同理
  auto get_env() const noexcept -> env-type<Index, Sndr, Rcvr> {
    return impls-for<tag-t>::get-env(Index(), op->state, op->rcvr);
  }
  basic-state<Sndr, Rcvr>* op;
};

template<class Sndr, class Rcvr>
struct basic-operation : basic-state<Sndr, Rcvr> {
  using operation_state_concept = operation_state_tag;
  connect-all-result<Sndr, Rcvr> inner-ops;
  basic-operation(Sndr&& sndr, Rcvr&& rcvr)
    : basic-state<Sndr, Rcvr>(std::forward<Sndr>(sndr), std::move(rcvr)),
      inner-ops(connect-all(this, std::forward<Sndr>(sndr), indices-for<Sndr>())) {}
  void start() & noexcept {
    auto& [...ops] = inner-ops;
    impls-for<tag-t>::start(this->state, this->rcvr, ops...);
  }
};
```

把它画成内存布局：

```text
basic-operation<then-sender, R>
├── rcvr   : R                          （外部接收器，被移进来）
├── state  : get-state 的结果           （对 then 来说就是 f 的副本）
└── inner-ops : product-type<
        connect(子发送器, basic-receiver<…, Index=0>{this})   （子操作状态，内嵌）
    >
```

- *connect-all*（¶30）对每个子发送器 `child_i` 调用 `connect(child_i, basic-receiver<..., integral_constant<size_t, i>>{op})`，结果收进一个 *product-type*。子接收器只是一个指针 `op`，指回父操作状态；`Index` 告诉父操作"是第几个子操作完成了"。
- 子操作完成时调用 `basic-receiver::set_value(args...)`，它转去调用 `impls-for<Tag>::complete(Index, state, rcvr, set_value_t(), args...)`——由**父算法**决定怎么处理。
- 子操作问环境时，`basic-receiver::get_env` 转去调用 `impls-for<Tag>::get-env(Index, state, rcvr)`——由父算法决定给子操作看什么环境。

注意 `basic-state` 的构造顺序：先移入 `rcvr`，再用 `rcvr`（成员，已经移入）去调用 *get-state*，这样 *get-state* 拿到的引用指向操作状态内部，可以安全地保存。

### impls-for 与 default-impls（¶35–41）

```cpp
struct default-impls {
  static constexpr auto get-env   = [](auto, auto&, const auto& rcvr) noexcept -> decltype(auto) {
    return FWD-ENV(get_env(rcvr));
  };
  static constexpr auto get-state = []<class Sndr, class Rcvr>(Sndr&& sndr, Rcvr& rcvr) noexcept -> decltype(auto) {
    auto& [_, data, ...child] = sndr;
    return allocator-aware-forward(std::forward_like<Sndr>(data), rcvr);
  };
  static constexpr auto start     = [](auto&, auto&, auto&... ops) noexcept -> void {
    (execution::start(ops), ...);
  };
  static constexpr auto complete  = []<class Index, class Rcvr, class Tag, class... Args>(
      Index, auto& state, Rcvr& rcvr, Tag, Args&&... args) noexcept -> void
      requires callable<Tag, Rcvr, Args...> {
    static_assert(Index::value == 0);
    Tag()(std::move(rcvr), std::forward<Args>(args)...);
  };
  template<class Sndr, class... Env> static consteval void check-types();
};
template<class Tag> struct impls-for : default-impls {};
```

默认行为是"什么都不做的透传"：

| 钩子 | 默认 | 典型覆盖 |
|---|---|---|
| *get-env* | 把外部环境 *FWD-ENV* 后给子操作 | `when_all` 换上自己的停止令牌；`write_env` 合并新环境 |
| *get-state* | 把数据（经分配器感知地转发）存进状态 | `continues_on` 预先 connect 调度发送器；`let` 预留第二个操作的空间 |
| *start* | 依次启动所有子操作 | `just` 直接完成；`when_all` 先注册停止回调 |
| *complete* | 原样把子操作的完成转给外部接收器（只允许一个子操作） | `then` 调用函数；`when_all` 计数 |
| *check-types* | 检查每个子发送器在 *FWD-ENV-T*(Env) 下都有签名 | `then` 检查回调可调用 |

¶41 *check-types* 的默认效果：`((void)get_completion_signatures<child-type<Sndr, Is>, FWD-ENV-T(Env)...>(), ...);`——子发送器有错误，父发送器就有错误（异常向上传播）。

每个具体算法的规范就是"`impls-for<xxx_t>` 继承 *default-impls*，覆盖其中某几个"。例如 `just` 只覆盖 *start*（[[exec.factories]]），`then` 只覆盖 *complete* 和 *check-types*（[[exec.adapt]]）。

### allocator-aware-forward（¶54–55）

把数据存进操作状态时，如果接收器环境提供了分配器（`get_allocator(get_env(rcvr))` 有效），就用 uses-allocator 构造（`make_obj_using_allocator`）创建副本；数据是 *product-type* 时逐元素这样做。否则原样转发。这样 `just(std::vector<int>{...})` 在一个提供了 pmr 分配器的环境里 connect 时，操作状态里的 vector 会使用那个分配器。

### 其他小工具（¶50–53、¶59–61）

- *overload-set*<Fns...>：把多个 lambda 合成一个重载集合（用于 `cs.for-each(overload-set{fn, [](auto){}})`：只处理某一类签名，其余忽略）。
- *not-a-sender*：一个 `get_completion_signatures` 永远抛异常的发送器。transform 函数用它表示"这里不能用"（比如 `stopped_as_optional` 子发送器没有签名时返回它），错误会在之后计算签名时报出来。
- *not-a-scheduler*：`schedule()` 返回 *not-a-sender* 的调度器，用作"找不到调度器"的占位默认值。
- *decay-copyable-result-datums*(cs)：任何结果数据不能 decay-copy 就抛异常。需要把结果**存起来**的算法（`continues_on`、`when_all`、`into_variant`）用它检查。
- *inline-attrs*<Tag>：一个属性对象，回答 `get_completion_scheduler<Tag>(env)` 为 `get_scheduler(env)`、`get_completion_domain<Tag>(env)` 为 `get_domain(env)`。意思是"我在调用者所在的地方完成"——同步完成的发送器（`just`、`inline_scheduler` 的调度发送器）用它。

## 思考题

!!! question "1. 构造即报错"
    `auto s = then(just(1), [](std::string) {});` 在哪一步、根据哪条规则成为非良构？

<details markdown="1">
<summary>答案</summary>

`then` 调用 *make-sender*，其 *Mandates* ¶24.4 要求 `dependent_sender<Sndr> || sender_in<Sndr>`。`just(1)` 非依赖，`then` 的 *check-types* 发现 `invocable<lambda, int>` 为 false（`int` 不能隐式转换为 `std::string`），抛出 *unspecified-exception*（[[exec.adapt]]）；于是 `get_completion_signatures<Sndr>()` 不是常量表达式，`sender_in<Sndr>` 为 false；它也不是依赖发送器，因为抛出的不是 `dependent_sender_error`（[exec.snd.general] ¶6）。*Mandates* 不满足，`then(...)` 这一行就非良构——错误出现在构造发送器的地方，而不是 connect 的地方。
</details>

!!! question "2. 子接收器为什么只存一个指针？"
    *basic-receiver* 只有一个 `basic-state*` 成员。这依赖了 [[exec.async.ops]] 的哪条保证？

<details markdown="1">
<summary>答案</summary>

依赖两条：(1) 子操作状态嵌在父操作状态里（*inner-ops* 是 *basic-operation* 的成员），且父操作状态在异步生存期内不移动、不销毁（[[exec.async.ops#7]]，[[exec.opstate]] ¶3），所以指针在子操作的整个生存期内有效；(2) 子操作若被启动，必在父操作完成之前完成（[[exec.async.ops#2]] ¶2.5），所以子接收器被调用时父操作还活着。这两条加起来，就是"结构化并发让引用安全"的具体体现。
</details>

## 小结

- `sender`：选择加入或是可等待体 + 有属性 + 可移动；`sender_in<S, E>`：在 `E` 下签名能在编译期算出来；`dependent_sender`：不给环境就算不出来。
- 标准算法的签名**精确**等于实际可能发出的完成；完成 domain/调度器按实际执行位置确定。
- 每个标准发送器 =（标签, 数据, 子发送器...），可以结构化绑定拆开。
- 读算法规范时，只需看 `impls-for<Tag>` 覆盖了 *get-env* / *get-state* / *start* / *complete* / *check-types* 中的哪几个。
- 非依赖发送器在构造时就检查类型错误。
