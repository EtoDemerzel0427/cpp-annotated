---
title: 完成签名
summary: completion_signatures 把发送器可能的完成编码成类型；get_completion_signatures 是一个 consteval 函数，用抛出异常报告类型错误或需要环境；value_types_of_t 等别名从签名集合中取出类型。
status: done
covers: exec.getcomplsigs
papers: P2300R10
related: exec.async.ops, exec.snd, exec.connect, exec.recv, exec.adapt, expr.const
tags: 标准库, std::execution, 完成签名, consteval, 类型计算
updated: 2026-10-19
---

!!! tldr
    - 一个发送器可能怎样完成，在编译期就写成了类型 `completion_signatures<...>`，每一项是 `set_value_t(Vs...)`、`set_error_t(E)` 或 `set_stopped_t()`。
    - `value_types_of_t`、`error_types_of_t`、`sends_stopped` 从签名集合中按种类取出类型，`sync_wait` 的返回类型就是这样算出来的。
    - `get_completion_signatures<Sndr, Env>()` 是一个 `consteval` 函数：先按 domain 变换发送器，再调用发送器的静态成员函数模板；问不出签名时抛出异常。
    - 不带环境问不出签名时抛 `dependent_sender_error`，表示发送器依赖环境；带了环境还问不出，就是真正的类型错误。
    - 声明的签名必须覆盖所有潜在求值的完成；不带环境得到的签名集合可以比带环境的大，但多出的只能是错误或取消完成。

本页讲 `std::execution` 的类型层面。用到 C++26 发送器库的例子没有经过编译验证，因为本机 Clang 23 附带的 libc++ 还没有实现这部分库；只演示语言机制的例子用 Clang 23 验证过。

## 为什么要在类型层面知道完成方式

[[exec.async.ops#13]] 规定，一个异步操作所有可能的完成，由发送器类型和接收器环境的类型共同决定。每种可能的完成写成一个函数类型，叫做[[g:completion-signature|完成签名]]。

几乎所有算法都要在编译期知道这些签名：

- `sync_wait` 要决定返回 `optional<tuple<什么>>`；
- `when_all` 要决定把各子操作的结果存进什么样的 tuple；
- `let_value` 要知道回调会收到什么、会返回哪种发送器，以便预留操作状态的空间；
- `connect` 要检查接收器能不能接受每一种完成。

这些都在编译期完成，运行时没有任何类型擦除。

## completion_signatures（[exec.cmplsig]）

¶1 `completion_signatures` 是编码一组完成签名的类模板。¶2 例 1 是一个声明了五种完成的发送器：

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

意思是：对接收器 `rcvr`，它会调用 `set_value(rcvr)`、`set_value(rcvr, int{…}, float{…})`、`set_error(rcvr, exception_ptr{…})`、`set_error(rcvr, error_code{…})`、`set_stopped(rcvr)` 中的一个。

¶3–4 只有三种形式的函数类型能作为模板实参：

- ¶4.1 `set_value_t(Vs...)`，`Vs` 是若干对象类型或引用类型；
- ¶4.2 `set_error_t(Err)`，`Err` 是一个对象类型或引用类型；
- ¶4.3 `set_stopped_t()`。

### 遍历签名：count-of 与 for-each（¶8–9）

¶8 `completion_signatures` 有两个阐述用的静态成员，用户代码不能调用它们，但标准算法的规范大量使用。

¶9 *count-of*(tag) 数出有多少个签名的返回类型是 `Tag`。*for-each*(fn) 对每个签名 `Fn` 调用一次 `fn(static_cast<Fn*>(nullptr))`，传入一个空的函数指针。这是把类型当值传递的写法：`fn` 的形参写成 `set_value_t(*)(Ts...)`，模板实参推导就能拆出 `Ts...`。

```cpp
// then 的类型检查（[exec.then]），略作简化
auto cs = get_completion_signatures<child-type<Sndr>, FWD-ENV-T(Env)...>();
auto fn = []<class... Ts>(set_value_t(*)(Ts...)) {
  if constexpr (!invocable<remove_cvref_t<data-type<Sndr>>, Ts...>)
    throw unspecified-exception();
};
cs.for-each(overload-set(fn, [](auto){}));   // 只检查值签名，其余忽略
```

### 按种类取出类型（¶5–8）

¶8 标准提供三个公开的工具，从签名集合中按种类取出类型：

```cpp
template<class Sndr, class Env = env<>,
         template<class...> class Tuple = decayed-tuple,
         template<class...> class Variant = variant-or-empty>
  using value_types_of_t = /* 每个值签名的参数装进 Tuple，再全部装进 Variant */;

template<class Sndr, class Env = env<>,
         template<class...> class Variant = variant-or-empty>
  using error_types_of_t = /* 每个错误类型装进 Variant */;

template<class Sndr, class Env = env<>>
  constexpr bool sends_stopped = /* 是否有 set_stopped_t() */;
```

`decayed-tuple<Ts...>` 是 `tuple<decay_t<Ts>...>`。*variant-or-empty*<Ts...> 是去掉重复类型后的 `variant<decay_t<Ts>...>`；没有任何类型时，它是一个不能构造的空类（[[execution.syn]]）。

以 `my_sender` 的签名为例（假设能正确读出它的签名，见下文）：

| 表达式 | 结果 |
|---|---|
| `value_types_of_t<S>` | `variant<tuple<>, tuple<int, float>>` |
| `value_types_of_t<S, env<>, tuple, type_list>` | `type_list<tuple<>, tuple<int, float>>` |
| `error_types_of_t<S>` | `variant<exception_ptr, error_code>` |
| `sends_stopped<S>` | `true` |

`sync_wait` 用 `value_types_of_t<Sndr, sync-wait-env, decayed-tuple, type_identity_t>` 计算返回类型（[[exec.consumers]]）。`type_identity_t` 只接受一个模板实参，所以发送器有不止一种值签名时这个类型非良构，`sync_wait` 要求恰好一种值完成就是这样落实的。

¶5–7 这三个别名都基于阐述用的 *gather-signatures*<Tag, Completions, Tuple, Variant>：挑出返回类型为 `Tag` 的签名，把第 n 个签名的参数类型包 `Tsn` 交给 `Tuple`，再把所有结果交给 `Variant`，得到 `Variant<Tuple<Ts0...>, Tuple<Ts1...>, ...>`。注 1 说明，它通过 *META-APPLY* 间接实例化模板，是为了允许 `optional`、`type_identity_t` 这类非变参模板充当 `Tuple` 或 `Variant`。

## get_completion_signatures（[exec.getcomplsigs]）

```cpp
template<class Sndr, class... Env>
  consteval auto get_completion_signatures() -> valid-completion-signatures auto;

template<class Sndr, class... Env>
  requires sender_in<Sndr, Env...>
using completion_signatures_of_t = decltype(get_completion_signatures<Sndr, Env...>());
```

这是一个没有函数实参的 `consteval` 函数模板，返回一个 `completion_signatures` 特化的对象（一个空对象，信息全在类型里）。¶2 环境最多一个。

### 用抛出异常报告错误

签名计算写成 `consteval` 函数，可以用普通的 `if constexpr` 和循环，更重要的是可以抛出异常。C++26 允许在常量求值中抛出异常；异常没有被捕获时，这次求值就不是常量表达式（[[expr.const]]），`sender_in` 之类的概念据此为假（[[exec.snd]]）。编译器还可以在诊断中显示异常对象携带的信息。

下面的例子不依赖发送器库，只演示这个语言机制：

```cpp run ok
#include <exception>
#include <type_traits>

struct needs_env : std::exception {};

template<class... Env>
consteval int signatures() {
  if constexpr (sizeof...(Env) == 0)
    throw needs_env();   // 没有环境：报告“需要环境”
  else
    return 1;
}

template<class... Env>
concept known = requires {
  typename std::integral_constant<int, signatures<Env...>()>;
};

static_assert(!known<>);     // 抛出异常的调用不是常量表达式
static_assert(known<int>);
int main() {}
```

### 查找顺序（¶1、¶3）

¶1 先定义几个记号：

- *get-complsigs*<Sndr, Env...>() 调用发送器的静态成员函数模板 `remove_reference_t<Sndr>::template get_completion_signatures<Sndr, Env...>()`。第一个模板实参是带着引用和 cv 限定的发送器类型本身，所以同一个发送器可以对左值和右值给出不同的签名。
- `NewSndr`：带环境时，是 `transform_sender(declval<Sndr>(), declval<Env>()...)` 的类型，也就是先按 domain 变换发送器（[[exec.snd.transform]]）。这样得到的是真正会被 connect 的那个发送器的签名。不带环境时就是 `Sndr`。
- *CHECKED-COMPLSIGS*(e)：如果 `e` 是核心常量表达式、类型是有效的签名集合，就是 `e` 本身；否则先求值 `e`（它抛出的异常照常传出），没有抛出的话再抛出一个派生自 `exception` 的未指定异常。

¶3 `get_completion_signatures` 依次尝试：

- ¶3.1 带环境调用发送器的静态成员；
- ¶3.2 不带环境调用发送器的静态成员，用于签名与环境无关的发送器；
- ¶3.3 如果 `NewSndr` 是可等待体（能被 `co_await`），签名固定为 `set_value_t(await 的结果)`、`set_error_t(exception_ptr)`、`set_stopped_t()`（[[exec.as.awaitable]]）；
- ¶3.4 都不行，并且没有提供环境：抛出 `dependent_sender_error`（或者一个公开且无歧义地派生自它的类型）；
- ¶3.5 都不行，但提供了环境：抛出一个未指定的异常。

¶3.4 和 ¶3.5 都表示问不出签名，含义却不同。没有环境时问不出来，可能只是因为签名依赖环境，给了环境就能确定；给了环境还问不出来，就是真正的错误。

### 依赖环境的发送器

`dependent_sender_error` 是本章唯一公开的异常类型，专门用来在签名计算中表达需要环境。自己写一个依赖环境的发送器时，可以这样写：

```cpp title="dependent-sender.cpp"
namespace ex = std::execution;

struct current_scheduler_sender {   // 以环境中的调度器完成，类似 read_env(get_scheduler)
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

`if constexpr` 只实例化一个分支。`Env` 为空时，实例化的分支里没有 `return`，返回类型推导为 `void`。这没有关系：这次调用总是以异常结束，*CHECKED-COMPLSIGS* 会让异常原样传出。

### 例 1 与规范文字的出入

例 1 用成员类型别名 `completion_signatures` 声明签名。但 ¶1 和 ¶3 的规范文字只查找静态成员函数模板 `get_completion_signatures`，不看类型别名。按字面推演，`my_sender` 既没有这个成员函数模板，也不是可等待体，`get_completion_signatures<my_sender>()` 会走到 ¶3.4，抛出 `dependent_sender_error`。

例子不具规范效力。写新代码时应提供静态成员函数模板：

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

## 对签名的两条要求（¶4–5）

¶4 如果 `completion_signatures_of_t<Sndr>` 和 `completion_signatures_of_t<Sndr, Env>` 都良构，前者必须是后者的超集，而且多出来的只能是错误或取消完成。不知道环境时只能做保守估计；知道环境之后可以排除一些可能，例如环境的停止令牌是 `never_stop_token`，就可以去掉 `set_stopped_t()`，但不能多出新的值类型。

¶5 如果发送器或它的操作状态使某个完成调用 `CSO(rcvr, args...)` 成为**潜在求值**的（potentially evaluated，[[basic.def.odr]]：出现在会被实例化的代码中，而不论运行时是否真的执行到），签名集合中就必须有一个与之匹配的签名。换句话说，声明的签名必须覆盖所有可能发生的完成，这是[[exec.snd.concepts#3]]中允许的完成在发送器作者一方的义务。

潜在求值比运行时实际执行的范围宽。一条 `set_error` 即使在运行时永远走不到的分支里，只要它所在的代码被实例化，就必须有对应的签名。反过来，用 `if constexpr` 让不可能的分支不被实例化，就能缩小签名集合。标准算法阐述代码中大量的 `if constexpr (!nothrow)` 正是为此：只有某个操作可能抛出异常时，才会出现 `set_error(..., current_exception())`，签名里才会有 `set_error_t(exception_ptr)`。

## 思考题

!!! question "1. 为什么第一个模板实参带着引用？"
    *get-complsigs* 把 `Sndr`（可能是 `S&`、`const S&` 或 `S`）原样传给发送器的静态成员。这有什么用？

<details markdown="1">
<summary>答案</summary>

同一个发送器作为左值和右值被 connect 时，可能以不同的方式发出结果。例如一个保存了 `std::string` 的发送器，右值 connect 时可以把字符串移动进操作状态；左值 connect 时只能复制，或者发出一个引用自身存储的 `const std::string&`。签名要如实反映这些差别，就得知道发送器是以什么值类别被 connect 的。

另外，[[exec.snd.concepts#9]] 规定标准库的发送器只在可复制时才提供左值 connect，这时对 `S&` 计算签名也应当失败。
</details>

!!! question "2. 签名集合可以比实际大吗？"
    一个发送器声明了 `set_error_t(exception_ptr)`，实际上却永远不会以错误完成。这违反规则吗？

<details markdown="1">
<summary>答案</summary>

对用户写的发送器不违反。¶5 只要求可能发生的完成被覆盖，是单向的包含关系。代价落在下游：`sync_wait` 照样要准备处理异常，`when_all` 的错误 `variant` 多一个成员，`spawn` 则根本不接受可能以错误完成的发送器（[[exec.spawn]]）。

对标准算法的默认实现要求更严：[[exec.snd.general#2]] 规定签名集合恰好对应潜在求值的完成。[[exec.adapt.general#4]] 还专门允许实现在确定不会发出 `exception_ptr` 错误时省略这个签名。
</details>

## 小结

| 设施 | 作用 |
|---|---|
| `completion_signatures<Fns...>` | 签名集合，每项是 `set_value_t(Vs...)`、`set_error_t(E)` 或 `set_stopped_t()` |
| `value_types_of_t`、`error_types_of_t`、`sends_stopped` | 按种类取出类型，`Tuple`、`Variant` 可替换 |
| `get_completion_signatures<Sndr, Env>()` | 先变换发送器，再问静态成员，再退到无环境版本和可等待体 |
| `dependent_sender_error` | 不带环境问不出签名时抛出，表示依赖环境 |
| ¶4 | 无环境的签名集合是有环境的超集，差别只能是错误或取消 |
| ¶5 | 签名必须覆盖所有潜在求值的完成 |
