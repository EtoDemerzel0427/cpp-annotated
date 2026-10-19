---
title: 发送器
summary: sender、sender_in、dependent_sender 三个概念；标准算法的默认实现报告哪些完成签名、在哪个 domain 和调度器上完成；以及读懂所有标准算法规范所需的阐述用骨架：make-sender、basic-sender、basic-operation、basic-receiver、impls-for，和 FWD-ENV、TRY-SET-VALUE 等辅助设施。
status: draft
covers: exec.snd.general, exec.snd.expos, exec.snd.concepts
papers: P2300R10
related: exec.async.ops, exec.cmplsig, exec.connect, exec.snd.transform, exec.factories, exec.adapt, exec.recv, exec.opstate, dcl.struct.bind
tags: 标准库, std::execution, 发送器, 概念, 阐述用
updated: 2026-10-19
---

!!! tldr
    - `sender` 只要求类型声明自己是发送器（或者是可等待体）、有属性、可移动；`sender_in<S, Env>` 才表示在环境 `Env` 下能在编译期算出完成签名。
    - 不给环境就算不出签名的发送器是依赖发送器，它在不给环境时抛出 `dependent_sender_error`。
    - 标准算法报告的签名恰好是它实际可能发出的那些完成，不多也不少；非依赖发送器在构造时就检查类型错误。
    - 每个标准发送器在概念上都是（标签, 数据, 子发送器...）三部分，可以用结构化绑定拆开；第一个元素的类型就是 `tag_of_t`。
    - 每个算法的规范只需写出 `impls-for<Tag>` 与默认实现不同的那几个钩子：*get-env*、*get-state*、*start*、*complete*、*check-types*。

本页的 `std::execution` 例子没有经过编译验证：本机 Clang 23 附带的 libc++ 还没有实现发送器库。演示语言规则的例子经过了本机 Clang 编译。

[exec.snd] 是第 33 章最大的二级条款，本站把它拆成多页。本页讲发送器概念 [exec.snd.concepts]、总则 [exec.snd.general] 和阐述用实体 [exec.snd.expos]，其余部分见：

- [[exec.cmplsig]]：`get_completion_signatures` 与 `completion_signatures`；
- [[exec.connect]]：`connect`；
- [[exec.snd.transform]]：domain、`transform_sender`、`apply_sender`；
- [[exec.as.awaitable]]：可等待体相关设施；
- [[exec.factories]]、[[exec.adapt]]、[[exec.on]]、[[exec.let]]、[[exec.bulk]]、[[exec.when.all]]、[[exec.spawn]]、[[exec.consumers]]：具体算法。

## 发送器概念 [exec.snd.concepts]

### sender：一个很弱的概念（¶1、¶4）

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
```

¶1 `sender` 只检查三件事：类型选择加入（声明 `sender_concept` 成员类型，或者是一个可等待体），`get_env` 能取得它的属性，它可以移动。它不检查能否 connect，也不检查会怎样完成。

*enable-sender* 的第二个分支让任何可等待体都自动成为发送器：只要它能在一个环境为空的协程里被 `co_await`（*env-promise* 见 [[exec.as.awaitable]]）。已有的协程 task 类型因此不用修改就能当发送器用，connect 时由一个协程包装（[[exec.connect]]）。

¶4 用户可以为自己定义的类型特化 `enable_sender`：模型化 `sender` 的特化为 true，不模型化的为 false。特化必须能用在常量表达式里，类型为 `const bool`。这是给不方便添加 `sender_concept` 成员的第三方类型准备的。

### sender_in：能算出签名的发送器

```cpp
template<class Sndr, class... Env>
  concept sender_in =
    sender<Sndr> && (sizeof...(Env) <= 1) && (queryable<Env> &&...) &&
    is-constant<get_completion_signatures<Sndr, Env...>()>;
```

`sender_in<Sndr, Env>` 表示在环境 `Env` 下，`get_completion_signatures<Sndr, Env>()` 能在编译期求值成功。*is-constant* 是一个接受任意非类型模板实参、恒为 true 的概念；把调用放进模板实参，就迫使它成为常量表达式。

`get_completion_signatures` 是 `consteval` 函数，遇到类型错误时会抛出异常（[[exec.cmplsig]]）。抛出异常的调用不是常量表达式，于是 `sender_in` 为 false。环境最多一个；`sender_in<S>` 表示不需要环境就能确定签名。

¶3 `sender_in` 还有语义要求。connect 并启动后，所有可能被调用的完成操作都必须是**允许的完成**（[[g:permissible-completion|permissible completion]]），即签名出现在 `completion_signatures_of_t<Sndr, Env>` 中的完成。声明的签名集合必须覆盖实际可能发生的完成：声明多了可以，少了不行。

### dependent_sender（¶2）

```cpp
template<class Sndr>
  consteval bool is-dependent-sender-helper() try {
    get_completion_signatures<Sndr>();
    return false;
  } catch (dependent_sender_error&) {
    return true;
  }

template<class Sndr>
  concept dependent_sender =
    sender<Sndr> && bool_constant<is-dependent-sender-helper<Sndr>()>::value;
```

不给环境调用 `get_completion_signatures<Sndr>()` 时抛出 `dependent_sender_error` 的发送器是**依赖发送器**。¶2 满足 `sender` 而不满足 `dependent_sender` 的类型，就是[[g:non-dependent-sender|非依赖发送器]]（[[exec.async.ops#13]]）。

- `just(1)` 的签名永远是 `set_value_t(int)`，是非依赖的，`sender_in<decltype(just(1))>` 为 true。
- 一个用户发送器的值类型取决于环境里的调度器类型。它不带环境的 `get_completion_signatures` 应当 `throw dependent_sender_error()`，带环境的才返回具体签名。它是依赖发送器：`sender_in<S>` 为 false，`sender_in<S, Env>` 为 true。
- `read_env(get_scheduler)` 按字面却不是依赖发送器，见 [[exec.factories]]。

### sender-to、sender-of、tag_of_t（¶1、¶5–9）

```cpp
template<class Sndr, class Rcvr>
  concept sender-to =
    sender_in<Sndr, env_of_t<Rcvr>> &&
    receiver-of<Rcvr, completion_signatures_of_t<Sndr, env_of_t<Rcvr>>> &&
    requires (Sndr&& sndr, Rcvr&& rcvr) { connect(std::forward<Sndr>(sndr), std::forward<Rcvr>(rcvr)); };
```

阐述用概念 *sender-to* 是能够 connect 的完整条件：发送器在接收器的环境下有签名，接收器能接受所有签名，`connect` 良构。

¶5 *sender-of*<Sndr, Values...> 和 *sender-in-of*<Sndr, Env, Values...> 要求发送器恰好有一种值完成签名，并与 `set_value_t(Values...)` 匹配。例如 [[exec.sched#2]] 用 *sender-in-of*<schedule_result_t<Sch>, Env> 要求调度发送器以 `set_value_t()` 完成。

¶6 如果 `auto&& [tag, data, ...children] = sndr;` 良构，`tag_of_t<Sndr>` 就是 `decltype(auto(tag))`，否则不良构。所有标准发送器都能这样拆开，第一个元素就是它的**标签**，通常是创建它的定制点对象的类型，比如 `then_t`。¶7 *sender-for*<Sndr, Tag> 表示 `Sndr` 是由算法 `Tag` 造出来的发送器，domain 定制就是靠它认出发送器的（[[exec.snd.transform]]）。

下面的程序用两个普通结构体模拟这种布局，并用 C++26 的结构化绑定包把子发送器收进一个包：

```cpp run ok
#include <cstdio>

struct just_t {};
struct then_t {};
struct just_sender { just_t tag; int data; };
template<class F, class Child>
struct then_sender { then_t tag; F data; Child child; };

template<class Sndr>
void inspect(const Sndr& sndr) {
  auto& [tag, data, ...children] = sndr;   // 结构化绑定引入包
  (void)tag; (void)data;
  std::printf("%zu\n", sizeof...(children));
}

int main() {
  just_sender j{{}, 1};
  then_sender<int (*)(int), just_sender> t{{}, [](int x) { return x + 1; }, j};
  inspect(j);   // 0
  inspect(t);   // 1
}
```

¶8 *SET-VALUE-SIG*(T)：`T` 为 cv `void` 时是 `set_value_t()`，否则是 `set_value_t(T)`。

¶9 标准库的发送器总是提供接受右值发送器的 `connect` 成员；只有可复制的发送器才提供接受左值的版本。所以能否重复使用一个发送器取决于它能否复制：`just(std::make_unique<int>(1))` 只能 `std::move` 之后 connect 一次。

## 标准算法的完成行为 [exec.snd.general]

### 签名不多也不少（¶1–2）

¶1 [[exec.factories]] 和 [[exec.adapt]] 中的算法都可以定制，每个都有默认实现。设 `sndr` 是某个算法默认实现的结果，`rcvr` 是环境为 `env` 的接收器，且 *sender-to* 成立。connect 并启动之后，必然会调用一组以 `rcvr` 为第一个实参的完成操作（潜在求值意义上）。

¶2 设 `Sigs` 是这组完成操作对应的签名。`get_completion_signatures<Sndr, Env>()` 的类型恰好是以 `Sigs` 为实参的 `completion_signatures`。如果 `Sigs` 都不依赖 `Env`，不带环境的版本也良构，结果相同。

换句话说，标准算法报告的签名恰好是它实际可能发出的那些。下游完全依赖这一点：`when_all` 要检查子发送器是否只有一种值完成，`sync_wait` 要据此计算返回类型。

### 完成 domain 与完成调度器（¶3–4）

¶3 每种完成可能发生在几个不同的执行代理上，取决于算法的语义、接收器的环境和子发送器的完成。对完成标签 `T`（`set_value_t` 等），把所有可能执行 `T` 完成的代理所关联的 domain 收集起来，记作 `DsT`。如果根本不会有 `T` 完成，`get_completion_domain<T>(get_env(sndr), env)` 不良构；否则它的类型是 *COMMON-DOMAIN*<DsT...>（见下文）。

例 1：`sndr2 = then(sndr, fn)` 的值完成 domain 与 `sndr` 相同。如果 `fn` 可能抛异常，`sndr2` 的错误完成有两个来源：转发 `sndr` 的错误完成，或者在 `sndr` 的值完成处捕获 `fn` 抛出的异常。所以它的错误完成 domain 是 `sndr` 的值完成和错误完成两个 domain 的 *COMMON-DOMAIN*。

¶4 如果 `sndr` 能确定所有 `T` 完成都发生在某个调度器 `sch` 的执行代理上，`get_completion_scheduler<T>(get_env(sndr), env)` 良构，类型和值都是 `sch`；否则不良构。

例 2：沿用上例，`sndr2` 的值完成调度器就是 `sndr` 的值完成调度器（如果有）。但只有当 `fn` 不会抛异常，或者 `sndr` 没有错误完成时，`sndr2` 才能报告错误完成调度器。否则错误可能发生在 `sndr` 的值完成调度器上（`fn` 抛异常时），也可能发生在错误完成调度器上，两者未必相同。

### 定制实现的约束（¶5–6）

¶5 如果选中的是用户提供的实现（通过 domain 定制，[[exec.snd.transform]]），而不是默认实现：

- ¶5.1 除非另有规定，签名中有而 `Sigs` 中没有的，只能是错误或取消完成。定制实现不能引入新的值完成类型。
- ¶5.2 如果 `Sigs` 不依赖 `Env`，带不带环境得到的签名必须相同。

¶6 本条款有些函数模板会抛出 *unspecified-exception*：类型未指定，能被 `catch (exception&)` 捕获，但不能被 `catch (dependent_sender_error&)` 捕获。注 1 补充，两个这样的异常不必同类型。它们在 `consteval` 的 `get_completion_signatures` 中抛出，用来报告类型错误，比如回调不能用这些值调用（[[exec.cmplsig]]）。

## 阐述用的骨架 [exec.snd.expos]

标准没有为每个算法逐个写出发送器类、接收器类和操作状态类，而是先定义一个通用的骨架 *basic-sender*，再让每个算法只特化一个 *impls-for*<Tag>，说明自己和默认行为有什么不同。看懂这套骨架之后，每个算法的规范只有十几行。

### make-sender 与 basic-sender（¶23–26、¶43–46）

```cpp
template<class Tag, class Data = see below, class... Child>
  constexpr auto make-sender(Tag tag, Data&& data, Child&&... child);
```

¶25 *make-sender* 返回 *basic-sender*<Tag, decay_t<Data>, decay_t<Child>...> 的纯右值，用转发的实参直接列表初始化。¶26 不需要数据的算法用默认的 `Data`：一个未指定的、平凡可复制的空类。

¶43 *basic-sender* 的定义：

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

所以每个标准发送器在概念上都是一个三段式的元组（标签, 数据, 子发送器...）。`then(sndr, f)` 是 `{then, f, sndr}`，`just(1, 2)` 是 `{just, product-type{1, 2}}`，`when_all(a, b)` 是 `{when_all, {}, a, b}`。¶44 它是否为聚合未指定，¶45 但一定能用作结构化绑定的初始化器，`tag_of_t` 依赖这一点。

¶24 *make-sender* 的 *Mandates* 有四条：`Tag` 是 `semiregular`；`Data` 满足 *movable-value*；每个 `Child` 是发送器；结果类型 `Sndr` 满足 `dependent_sender<Sndr> || sender_in<Sndr>`。

最后一条意味着非依赖发送器在构造时就检查类型错误。`then(just(1), [](std::string) {})` 在调用 `then` 的那一行就非良构，而不是等到 connect 时才报出几十层深的模板错误。¶24 还建议，`get_completion_signatures` 因异常而失败时，实现应当把异常的信息放进诊断。C++26 允许在常量求值中抛出异常，类型错误因此可以作为一个带说明的异常对象报告。

### 操作状态：basic-state、basic-receiver、basic-operation（¶27–34）

`basic-sender::connect` 返回 *basic-operation*。三个类模板的骨架如下（省略了 noexcept 说明和约束）：

```cpp
template<class Sndr, class Rcvr>
struct basic-state {
  basic-state(Sndr&& sndr, Rcvr&& rcvr)
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

以 `then` 为例，内存布局是这样的：

```text
basic-operation<then 的发送器, R>
├── rcvr      : R                 外部接收器，移动进来
├── state     : get-state 的结果  对 then 来说就是 f 的副本
└── inner-ops : product-type<
        connect(子发送器, basic-receiver<..., Index = 0>{this})   子操作状态，内嵌在这里
    >
```

- ¶30 *connect-all* 用 `basic-receiver<..., integral_constant<size_t, i>>{op}` 连接第 `i` 个子发送器，结果收进一个 *product-type*。子接收器里只有一个指针 `op`，指回父操作状态；`Index` 告诉父操作是哪一个子操作完成了。
- 子操作完成时调用 `basic-receiver::set_value(args...)`，它转去调用 `impls-for<Tag>::complete(Index, state, rcvr, set_value_t(), args...)`，怎么处理由父算法决定。
- 子操作查询环境时，`basic-receiver::get_env` 转去调用 `impls-for<Tag>::get-env(Index, state, rcvr)`，给子操作看什么环境也由父算法决定。

子接收器只存一个指针是安全的：子操作状态嵌在父操作状态里，父操作状态在操作进行期间不移动、不销毁（[[exec.opstate]]）。

!!! lawyer "basic-state 的初始化器里，rcvr 指的是形参"
    *basic-state* 的构造函数先用 `std::move(rcvr)` 初始化成员 `rcvr`，再把 `rcvr` 传给 *get-state*。意图显然是传入已经移进操作状态的成员，这样 *get-state* 保存的引用指向操作状态内部，比如 `continues_on` 的状态里就存着 `Rcvr&`（[[exec.on]]）。但在成员初始化器的表达式里，名字 `rcvr` 先找到的是构造函数的形参，也就是那个已被移走的对象。按字面读，*get-state* 拿到的是形参的引用，构造函数返回后就悬空了。

    ```cpp run ok
    #include <cstdio>
    #include <utility>
    struct R { int id; };
    struct S {
      R* saved;
      explicit S(R& r) : saved(&r) {}
    };
    struct basic_state {
      basic_state(R&& rcvr) : rcvr(std::move(rcvr)), state(rcvr) {}
      R rcvr;
      S state;
    };
    int main() {
      basic_state b(R{1});
      std::printf("%d\n", b.state.saved == &b.rcvr);   // 输出 0
    }
    ```

    写成 `this->rcvr` 才符合意图。阐述代码只描述行为，实现不会照抄这个缺陷。

### impls-for 与 default-impls（¶35–42）

¶35 *impls-for*<Tag> 默认继承 *default-impls*，提供五个钩子的默认行为（省略了部分签名细节）：

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

默认行为就是原样透传：

| 钩子 | 默认行为 | 典型的覆盖 |
|---|---|---|
| *get-env*（¶36） | 把外部环境经 *FWD-ENV* 交给子操作 | `when_all` 换上自己的停止令牌；`write_env` 合并新环境 |
| *get-state*（¶37） | 把数据存进状态，有分配器时用分配器构造 | `continues_on` 预先 connect 调度发送器；`let_value` 预留第二个操作的空间 |
| *start*（¶38） | 依次启动所有子操作 | `just` 直接完成；`when_all` 先注册停止回调 |
| *complete*（¶39） | 把唯一子操作的完成原样转给外部接收器 | `then` 调用回调；`when_all` 计数 |
| *check-types*（¶40–41） | 检查每个子发送器在 *FWD-ENV-T*(Env) 下都有签名 | `then` 检查回调能否调用 |

¶41 默认的 *check-types* 依次对每个子发送器调用 `get_completion_signatures`，子发送器有类型错误，父发送器也就有（异常向上传播）。¶42 注 4 说明，*check-types* 要么不良构，要么抛出异常，要么是核心常量表达式；是核心常量表达式时，发送器和环境类型唯一确定一个签名集合。

每个算法的规范都是"`impls-for<xxx_t>` 继承 *default-impls*，覆盖其中几个"。`just` 只覆盖 *start*（[[exec.factories]]），`then` 只覆盖 *complete* 和 *check-types*（[[exec.adapt]]）。

### 签名从阐述代码里读出来（¶47–49）

¶47 `basic-sender::get_completion_signatures` 取 `Env...` 中的第一个作为环境 `E`，没有就用 `env<>`，然后求值 *CHECK-TYPES*()，即 `impls-for<Tag>::check-types<Sndr, E>()`：

- ¶47.1 如果它是核心常量表达式，签名集合就是 connect 后调用 `op.start()` 时潜在求值的那些完成操作所对应的签名；
- ¶47.2 否则签名集合是空的 `completion_signatures<>`。¶49 这时函数先执行 *CHECK-TYPES*()，异常会传播出去，所以实际结果是计算签名失败。

¶48 *CHECK-TYPES*() 必须是良构的表达式（*Constraints*）。

这是一种很特别的写法：签名集合不是由一个类型公式给出，而是由阐述代码中实际可能调用了哪些 `set_*` 决定的。读 `then` 的 *impls-for* 时看到 `TRY-SET-VALUE(rcvr, invoke(fn, args...))`，就知道它会产生 `set_value_t(invoke 的结果)`，`invoke` 可能抛异常时还会产生 `set_error_t(exception_ptr)`。

!!! lawyer "不给环境时用的是 env<>"
    按 ¶47，不带环境的 `get_completion_signatures<Sndr>()` 对标准适配器而言，实际上是拿空环境 `env<>` 去运行 *check-types*，子发送器也是在 *FWD-ENV-T*(env<>) 下被检查的。而 ¶2 与 [[exec.adapt.general#3]] ¶3.5 都暗示依赖性应当从子发送器传到父发送器。

    按字面读，如果子发送器在空环境下抛出的是普通异常而不是 `dependent_sender_error`，父发送器既不是依赖的，也不满足 `sender_in`。[[exec.factories]] 中 `read_env` 的问题就出在这里。涉及依赖发送器与标准适配器的组合时，以实现的实际行为和后续草案为准。

!!! lawyer "get-attrs 去哪了？"
    `basic-sender::get_env` 调用的是 `impls-for<Tag>::get-attrs`，但 ¶35 的 *default-impls* 没有这个成员，整个草案也只在这一处提到它。父发送器的属性实际由 [[exec.adapt.general#3]] ¶3.2–3.3 以及本页的 [exec.snd.general] ¶3–4 规定，读规范时以那里为准。

### 环境运算（¶4–10）

| 实体 | 含义 | 用途 |
|---|---|---|
| *FWD-ENV*(env)（¶4） | 只回答[[g:forwarding-query|转发查询]]，其余查询不良构；它的类型记作 *FWD-ENV-T*(Env) | 适配器把环境传给子操作 |
| *MAKE-ENV*(q, v)（¶5） | 只回答查询 `q`，结果等于 `v` | 构造只有一项的环境 |
| *JOIN-ENV*(e1, e2)（¶6） | 先问 `e1`，回答不了再问 `e2` | 覆盖或补充环境 |
| *SCHED-ENV*(sch)（¶10） | `get_start_scheduler` 返回 `sch` 的副本，`get_domain` 转问 `sch` | 告诉子操作它在 `sch` 上启动 |

¶7 前三者的结果可以随上下文变化：同样的实参在不同地方可以得到类型和值类别不同的表达式。这给实现留了余地，比如存引用还是存值。

¶8 *COMMON-DOMAIN*(domains...)：如果这些 domain 有公共类型（`common_type_t` 良构，比如一个派生自另一个，或者用户特化了 `common_type`），就取公共类型的值；否则是去重后的 `indeterminate_domain<Ds...>()`，表示无法确定（[[exec.snd.transform]]）。

¶9 *COMPL-DOMAIN*(Tag, sndr, envs)：`get_completion_domain<Tag>(get_env(sndr), envs...)` 良构或者 `envs` 为空时，取它的类型的默认构造值；否则是 `indeterminate_domain()`。

### 把普通调用接进发送器（¶11）

- *SET-VALUE*(rcvr, expr)：`expr` 为 `void` 时是 `(expr, set_value(std::move(rcvr)))`，否则是 `set_value(std::move(rcvr), expr)`。
- *TRY-EVAL*(rcvr, expr)：`expr` 可能抛异常时是

    ```cpp
    try { expr; } catch(...) { set_error(std::move(rcvr), current_exception()); }
    ```

    否则就是 `expr`。
- *TRY-SET-VALUE*(rcvr, expr)：*TRY-EVAL*(rcvr, *SET-VALUE*(rcvr, expr))，`rcvr` 只求值一次。

这是把普通函数调用接进发送器的标准写法：算出结果，用 `set_value` 发出；计算时抛出异常，用 `set_error(exception_ptr)` 发出。`then` 的实现就是一行 *TRY-SET-VALUE*（[[exec.adapt]]）。`expr` 是 `set_value` 的实参，求值它就在这次调用之中，所以 `try` 包住了整个调用；`set_value` 本身必须是 noexcept 的（[[exec.set.value]]），捕获到的异常只能来自 `expr`。

### 其他辅助设施

¶12–14 *query-with-default*(tag, env, value)：`tag(env)` 良构就用它，否则用 `value`。¶56–58 *call-with-default*(fn, value, args...)：`fn(args...)` 良构就用它，否则用 `value`。环境里查不到时就用默认值，比如 `on` 取原调度器时，取不到就用 *not-a-scheduler*（[[exec.on]]）。

¶15 *emplace-from*：

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

注 1：它用来把不可移动的类型就地放进 `tuple`、`optional`、`variant`。容器用实参构造元素时调用转换函数，转换函数返回纯右值，保证复制消除让元素被直接构造。[[exec.opstate]] 有一个能在本机编译的演示。

¶16 *on-stop-request*：持有一个 `inplace_stop_source&`，调用时 `request_stop()`。它用作停止回调：外部令牌请求停止时，转发给内部的停止源。`when_all` 用它把外部的取消传给所有子操作（[[exec.when.all]]）。

¶17–22 *product-type*<T0, ..., Tn> 是一个能做结构化绑定的轻量元组，成员 `get<I>` 和 `apply` 用 C++26 的结构化绑定包实现：

```cpp
auto& [...ts] = self;                          // ¶19：结构化绑定引入包
return std::forward_like<Self>(ts...[I]);      //      包索引
```

注 2 说明它是伪代码，用标准 C++ 实现时要保持它是聚合、能用作结构化绑定的初始化器。`auto& [_, data, ...child] = sndr;` 是整个 [exec] 里最常见的拆包写法，`_` 是 C++26 的占位符名，可以重复声明。

¶54–55 *allocator-aware-forward*：把数据存进操作状态时，如果接收器的环境提供了分配器（`get_allocator(get_env(rcvr))` 有效），就用 uses-allocator 构造（`make_obj_using_allocator`）创建副本，*product-type* 则逐个元素这样做；否则原样转发。所以 `just(std::vector<int>{...})` 在一个提供了 pmr 分配器的环境里 connect 时，操作状态里的 vector 会使用那个分配器。

其余几个：

- ¶50 *overload-set*<Fns...>：把几个 lambda 合成一个重载集合，常用来只处理某一类签名，其余忽略。
- ¶51 *not-a-sender*：计算签名时总是抛异常的发送器。改写函数用它表示这里不能用，错误在之后计算签名时报出。
- ¶52 *not-a-scheduler*：`schedule()` 返回 *not-a-sender* 的调度器，用作找不到调度器时的占位默认值。
- ¶53 *decay-copyable-result-datums*(cs)：有结果数据不能退化复制时抛异常。需要把结果存起来的算法（`continues_on`、`when_all`、`into_variant`）用它检查。
- ¶59–61 *inline-attrs*<Tag>：一个属性对象，回答完成调度器为 `get_scheduler(env)`、完成 domain 为 `get_domain(env)`，意思是在调用者所在的地方完成。同步完成的发送器（`just`、`inline_scheduler` 的调度发送器）用它。

¶1–2 标准库发送器是否提供 `affine()`、`as_awaitable(p)` 成员未指定；如果提供，必须满足 `affine`（[[exec.affine]]）、`as_awaitable`（[[exec.as.awaitable]]）算法的语义。这允许实现为特定发送器提供更高效的版本，比如 `just` 根本不需要切换调度器。

## 思考题

!!! question "1. 构造即报错"
    `auto s = then(just(1), [](std::string) {});` 在哪一步、根据哪条规则成为非良构？

<details markdown="1">
<summary>答案</summary>

`then` 调用 *make-sender*，¶24.4 要求 `dependent_sender<Sndr> || sender_in<Sndr>`。`just(1)` 是非依赖的；`then` 的 *check-types* 发现回调不能用 `int` 调用（`int` 不能隐式转换为 `std::string`），抛出 *unspecified-exception*（[[exec.adapt]]）。于是 `get_completion_signatures<Sndr>()` 不是常量表达式，`sender_in<Sndr>` 为 false。它也不是依赖发送器，因为抛出的不是 `dependent_sender_error`（[exec.snd.general] ¶6）。*Mandates* 不满足，错误出现在构造发送器的这一行，而不是 connect 的地方。
</details>

!!! question "2. 子接收器为什么只存一个指针？"
    *basic-receiver* 只有一个 `basic-state*` 成员。这依赖了 [[exec.async.ops]] 的哪些保证？

<details markdown="1">
<summary>答案</summary>

依赖两条。第一，子操作状态嵌在父操作状态里（*inner-ops* 是 *basic-operation* 的成员），而父操作状态在异步生存期内不移动、不销毁（[[exec.async.ops#7]]、[[exec.opstate]]），所以指针在子操作的整个生存期内有效。第二，子操作如果被启动，一定在父操作完成之前完成（[[exec.async.ops#2]] ¶2.5），所以子接收器被调用时父操作还活着。
</details>
