---
title: 查询与可查询对象
summary: 环境和发送器属性都是可查询对象，即以查询对象为键的只读表；q(env) 调用 env.query(q)，prop 构造单个键值对，env 按顺序合并多个可查询对象。
status: draft
covers: exec.queryable.general, exec.queryable.concept, exec.envs, exec.prop, exec.env
papers: P2300R10
related: exec.async.ops, exec.queries, exec.adapt, exec.snd
tags: 标准库, std::execution, 环境, 查询
updated: 2026-10-19
---

!!! tldr
    - 可查询对象是一张只读的键值表，键是查询对象（如 `get_stop_token`），在编译期按类型查找。
    - 写一个 `query(Tag) const noexcept` 成员就能回答查询：`q(env)` 等价于 `env.query(q)`。
    - 查询结果不能是 `void`，不能修改环境，在可查询对象有效期间一直有效。
    - `prop(q, v)` 造一个只回答 `q` 的环境；`env{a, b}` 按顺序查找，`a` 能回答的查询会遮蔽 `b`。
    - `env` 要用花括号初始化；`prop` 和 `env` 都不可赋值。

接收器的环境和发送器的属性（[[exec.async.ops]]）都是可查询对象。它们遵守同一套协议（[exec.queryable]），标准还提供了构造它们的两个工具 `prop` 和 `env`（[exec.envs]）。Clang 23 的 libc++ 还没有实现这些设施，下面的例子没有经过编译。

## 一个环境长什么样

```cpp title="my-env.cpp"
#include <execution>
#include <memory>
#include <stop_token>

struct my_env {
  std::stop_token token;
  std::allocator<int> alloc;

  auto query(std::get_stop_token_t) const noexcept { return token; }
  auto query(std::get_allocator_t) const noexcept { return alloc; }
};

void f(const my_env& e) {
  auto t = std::get_stop_token(e);     // 调用 e.query(get_stop_token)
  auto a = std::get_allocator(e);      // 调用 e.query(get_allocator)
  // std::execution::get_scheduler(e); // 非良构：my_env 不回答这个查询
}
```

环境不用普通结构体的固定成员，是因为它要能任意扩展。库定义了停止令牌、分配器、调度器等查询，用户可以定义自己的查询，适配器还要能在原环境上增加一项、或只把某几项转发下去。以查询对象类型为键的表正好满足这些需求，而且查找在编译期完成。

`query` 成员必须是 const 且 `noexcept` 的：标准查询总是以 const 方式调用它，并要求调用不抛异常（[[exec.queries]]）。非 const 的 `query` 根本不会被找到，非 `noexcept` 的会让程序非良构。

## 可查询对象的规则（[exec.queryable.general]）

¶1 **可查询对象**（[[g:queryable-object|queryable object]]）是一个只读的键值对集合，每个键是一个称为**查询对象**（query object）的[[g:customization-point-object|定制点对象]]。**查询**（query）是以可查询对象为第一实参、外加（可能为空的）其他实参，调用查询对象。每个查询可以对调用施加自己的语法和语义要求，例如 `get_stop_token` 要求结果满足 `stoppable_token`。

¶2 设 `env` 指代 `O` 类型的可查询对象 `o`，`cenv` 以 `const O&` 指代同一个对象。那么 `q(env, args...)` 与 `q(cenv, args...)` 的结果必须相等。拿着非 const 引用查询，不能得到不同的答案。

¶3 查询表达式的类型不能是 `void`。

¶4 查询保持相等性（相同输入给出相等结果），且不修改查询对象或实参。

¶5 如果 `env.query(q, args...)` 良构，它与 `q(env, args...)` [[g:expression-equivalent|表达式等价]]。这就是定制的方式：写一个以查询对象类型为第一个形参的 `query` 成员。

¶6 除非另有规定，查询结果在可查询对象有效期间一直有效。所以查询可以返回引用，指向可查询对象内部的数据。

## queryable 概念（[exec.queryable.concept]）

```cpp
template<class T>
  concept queryable = destructible<T>;   // exposition only
```

¶1 仅用于阐述的 *queryable* 概念在语法上只要求 `destructible`，几乎任何对象类型都满足。

¶2 语义要求是：对任何可调用对象 `q`，只要 `q(env, args...)` 良构，结果就满足 `q` 施加的语义要求。

能问什么完全由各个查询对象决定，概念本身不列出必须支持的查询。一个空结构体也是合法的环境：对它的查询要么非良构，要么取查询的默认值（例如 `get_stop_token` 默认返回 `never_stop_token`）。标准提供的空环境是 `env<>`。

## prop：一个键值对（[exec.prop]）

```cpp
template<class QueryTag, class ValueType>
struct prop {
  QueryTag query_;            // exposition only
  ValueType value_;           // exposition only

  constexpr const ValueType& query(QueryTag, auto&&...) const noexcept { return value_; }
};

template<class QueryTag, class ValueType>
  prop(QueryTag, ValueType) -> prop<QueryTag, unwrap_reference_t<ValueType>>;
```

¶1 `prop` 用一个查询对象和一个值构造可查询对象。`prop(get_allocator, my_alloc{})` 只回答 `get_allocator`，答案是 `my_alloc{}`。¶3 的例 1 把它交给 `write_env`（[[exec.adapt]]），让一个发送器看到的环境里多一个分配器：

```cpp
template<sender Sndr>
sender auto parameterize_work(Sndr sndr) {
  auto e = prop(get_allocator, my_alloc{});
  return write_env(sndr, e);
}
```

几个细节：

- `query` 返回 `const ValueType&`，指向 `prop` 内部的值，所以查询结果在 `prop` 有效期间有效。
- 推导指引使用 `unwrap_reference_t`，于是 `prop(get_stop_token, std::ref(tok))` 得到 `prop<get_stop_token_t, inplace_stop_token&>`，保存的是引用而不是副本（`tok` 是一个 `inplace_stop_token`）。
- `query` 接受并忽略任意额外实参。

¶2 `prop` 要求查询对象能接受这样一个值：*Mandates* 是 *callable*<QueryTag, *prop-like*<ValueType>>，其中 *prop-like* 是一个只有 `const ValueType& query(auto) const noexcept;` 的类。所以 `prop(get_scheduler, 42)` 非良构 {{ill-formed}}：`get_scheduler` 要求结果是调度器（[[exec.get.scheduler]]），而 `int` 不是。错误在构造 `prop` 的地方就报出，而不是等到很久以后某个算法查询它时。

¶4 `prop` 的特化不可赋值。环境是只读的，赋值没有意义，而且 `ValueType` 可能是引用。

## env：合并多个可查询对象（[exec.env]）

```cpp title="env-shadow.cpp"
namespace ex = std::execution;

auto base   = ex::env{ex::prop(ex::get_scheduler, sch_a), ex::prop(std::get_allocator, alloc)};
auto merged = ex::env{ex::prop(ex::get_scheduler, sch_b), base};

// ex::get_scheduler(merged) 返回 sch_b：第一个子对象先回答
// std::get_allocator(merged) 返回 alloc：第一个子对象不回答，转到 base
```

¶1 `env` 由多个可查询对象构造一个可查询对象，查询按词法顺序依次尝试每个子对象。

¶6–8 精确地说，设 *fe* 是子对象中第一个使 `fe.query(q, args...)` 良构的元素。`query` 成员的约束是至少有一个这样的元素（¶7），效果是返回 `fe.query(q, std::forward<Args>(args)...)`（¶8）。¶9 规定它的 `noexcept` 与 `fe.query(...)` 一致。

所以在 `env{a, b}` 中，两者都能回答的查询取 `a` 的答案。这正是在原环境上覆盖一项所需要的语义。¶4 的例 1 用 `env{prop(get_allocator, my_alloc{}), prop(get_scheduler, my_sched{})}` 同时提供两个查询。

¶2 `env` 的特化不可赋值。

¶3 除了用另一个 `env` 复制或移动构造的情形，`env` 是否支持圆括号初始化未指定 {{unspec}}。`env` 被描述成一个有若干成员的类，实现可能把它做成聚合（C++20 起聚合支持圆括号初始化），也可能不是。实际写代码时用花括号：`env{a, b}`。

`env<>` 是没有子对象的空环境。对象没有 `get_env` 成员时，`get_env(o)` 返回 `env<>{}`（[[exec.get.env]]）；`value_types_of_t<Sndr>` 等别名的默认环境实参也是 `env<>`（[[exec.cmplsig]]）。

规范描述适配器时更常用 [[exec.snd]] 中的几个阐述用操作：*FWD-ENV*(env) 只转发 `forwarding_query(q)` 为真的查询，*MAKE-ENV*(q, v) 类似 `prop(q, v)`，*JOIN-ENV*(e1, e2) 类似 `env{e1, e2}`。`prop` 和 `env` 是给用户的公开版本。

## 思考题

!!! question "1. 为什么 env 的 query 要求至少一个子对象能回答？"
    如果去掉 ¶7 的约束，`env<>{}.query(get_scheduler)` 会怎样？

<details markdown="1">
<summary>答案</summary>

有约束时，没有子对象能回答的查询不参与重载决议，`env.query(q)` 非良构。查询对象于是可以回落到它的默认行为（如 `get_stop_token` 返回 `never_stop_token{}`），或者整个查询非良构，能被 `requires` 表达式检测到。

没有约束的话，`query` 在声明上总是存在，只在实例化函数体时才出错。适配器检测环境里有没有调度器之类的写法就全部失效了。
</details>

!!! question "2. 查询可以返回悬空引用吗？"
    `prop` 的 `query` 返回 `const ValueType&`。一个算法写 `auto& s = get_scheduler(get_env(rcvr));` 然后把 `s` 存起来，安全吗？

<details markdown="1">
<summary>答案</summary>

不一定安全。¶6 只保证结果在可查询对象有效期间有效，[[exec.get.env]] ¶2 也只保证 `get_env(o)` 的值在 `o` 有效期间有效。如果 `get_env(rcvr)` 按值返回一个临时环境对象，`s` 在这个完整表达式结束后就悬空了。

安全的写法是按值保存：`auto s = get_scheduler(get_env(rcvr));`。调度器要求可复制（[[exec.sched]]），复制它很便宜。
</details>
