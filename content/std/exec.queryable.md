---
title: 查询与可查询对象
summary: 环境和发送器属性都是"可查询对象"——以查询对象为键的只读键值表；q(env) 等价于 env.query(q)；prop 造一个键值对，env 把多个可查询对象按顺序合并
status: done
covers: exec.queryable.general, exec.queryable.concept, exec.envs, exec.prop, exec.env
papers: P2300R10
related: exec.async.ops, exec.queries, exec.adapt, exec.snd
tags: 标准库, std::execution, 环境, 查询
updated: 2026-10-18
---

[[exec.async.ops]] 里有两样东西被定义成"可查询对象"：接收器的**环境**（调用者希望子操作知道的信息）和发送器的**属性**（发送器关于自己的信息）。这一节给出可查询对象的统一协议；[exec.envs] 则提供两个用来**构造**可查询对象的小工具 `prop` 和 `env`。

为什么不用一个普通结构体当环境？因为环境要能**任意扩展**：库定义了停止令牌、分配器、调度器等查询，用户可以定义自己的查询，适配器还要能"在原环境上加一项"、"把原环境的某几项转发下去"。一个以**类型**（查询对象的类型）为键的编译期键值表正好满足这些需求，而且查找在编译期完成，没有运行期开销。

## 可查询对象与查询（[exec.queryable.general]）

¶1 三个定义：

- [[g:queryable-object|**可查询对象**]]（queryable object）：一个只读的键值对集合，每个键是一个称为**查询对象**（query object）的[[g:customization-point-object|定制点对象]]。
- **查询**（query）：以可查询对象为第一实参、外加（可能为空的）其他实参来调用查询对象。
- 查询对其调用施加语法和语义要求（例如 `get_stop_token` 要求结果满足 `stoppable_token`）。

¶2 设 `q` 是查询对象，`env` 指代 `O` 类型的可查询对象 `o`，`cenv` 指代同一个 `o` 但类型是 `const O&`。则 `q(env, args...)` **等于**（[[concepts.equality]]）`q(cenv, args...)`。也就是说，查询结果不能因为你拿的是非 const 引用就不同——环境是只读的。

¶3 查询表达式的类型不能是 `void`。

¶4 `q(env, args...)` 保持相等性（equality-preserving），且不修改查询对象或实参。

¶5 若 `env.query(q, args...)` 良构，则它与 `q(env, args...)` **表达式等价**（[[g:expression-equivalent]]）。这就是定制的方式：**写一个 `query` 成员函数**，以查询对象（的类型）作第一个形参。

¶6 除非另有规定，查询结果在可查询对象有效期间一直有效。所以查询可以返回引用，指向可查询对象内部的数据。

```cpp title="my-env.cpp"
#include <execution>
#include <memory>

struct my_env {
  std::stop_token token;
  std::allocator<int> alloc;

  auto query(std::get_stop_token_t) const noexcept { return token; }
  auto query(std::get_allocator_t) const noexcept { return alloc; }
};

void f(const my_env& e) {
  auto t = std::get_stop_token(e);     // 等价于 e.query(get_stop_token)
  auto a = std::get_allocator(e);      // 等价于 e.query(get_allocator)
  // std::execution::get_scheduler(e); // 非良构：my_env 没有回答这个查询
}
```

注意 `query` 必须是 const 且 noexcept 的：查询对象实际上用 *AS-CONST*(env).query(q) 调用（[[exec.queries]]），并用 *MANDATE-NOTHROW* 包裹，非 noexcept 的 `query` 会让程序非良构。

## queryable 概念（[exec.queryable.concept]）

```cpp
template<class T>
  concept queryable = destructible<T>;   // exposition only
```

¶1 *queryable* 是仅用于阐述的概念，约束可查询对象的类型。它在**语法上**只要求 `destructible`——任何对象类型都满足。

¶2 语义要求：类型 `Env` **模型化** *queryable*，当且仅当对每个可调用对象 `q` 和实参包 `args`，只要 `requires { q(env, args...) }` 为 true，`q(env, args...)` 就满足 `q` 施加的语义要求。

换句话说，"能被问什么"完全由各个查询对象自己决定（一个查询是否良构由 `env.query(q)` 是否存在、以及查询对象的默认行为决定），概念本身不列出任何必须支持的查询。一个空结构体 `struct {}` 也是合法的环境：所有查询要么非良构，要么取默认值（比如 `get_stop_token` 默认返回 `never_stop_token`）。`env<>` 就是标准提供的空环境。

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

¶1 `prop` 用一个查询对象和一个值构造可查询对象：`prop(get_allocator, my_alloc{})` 就是"对 `get_allocator` 回答 `my_alloc{}`"。

- `query` 返回 `const ValueType&`，指向 `prop` 内部存的值，所以 ¶6 的"查询结果在可查询对象有效期间有效"在这里是字面意义上的。
- 推导指引用了 `unwrap_reference_t`：`prop(get_stop_token, std::ref(tok))` 得到 `prop<get_stop_token_t, inplace_stop_token&>`——存引用而不是副本。
- `query` 接受任意额外实参并忽略它们（`auto&&...`）。

¶2 *Mandates*：*callable*<QueryTag, *prop-like*<ValueType>> 成立，其中 *prop-like* 是一个只有 `const ValueType& query(auto) const noexcept;` 的类。意思是：**查询对象本身必须接受这样一个值**。例如 `prop(get_scheduler, 42)` 非良构 {{ill-formed}}：按 [[exec.get.scheduler]]，`get_scheduler(e)` 会把 `e.query(get_scheduler)` 的结果交给 `get_completion_scheduler<set_value_t>(…)`，而后者对一个既不能回答该查询、本身也不是调度器的 `int` 是非良构的，于是 *callable* 不成立。错误在构造 `prop` 的地方报出，而不是等到很久以后某个算法查询它时。

¶3 例 1 展示典型用法：`write_env(sndr, prop(get_allocator, my_alloc{}))` 让 `sndr` 看到的环境里多一个分配器（[[exec.adapt]] 中的 `write_env`）。

¶4 `prop` 的特化**不可赋值**。环境是只读的，赋值没有意义；而且 `ValueType` 可能是引用。

## env：合并多个可查询对象（[exec.env]）

```cpp
template<queryable... Envs>
struct env {
  Envs0 envs0;  Envs1 envs1;  …  Envsn-1 envsn-1;   // exposition only

  template<class QueryTag, class... Args>
    constexpr decltype(auto) query(QueryTag q, Args&&... args) const noexcept(see below);
};

template<class... Envs>
  env(Envs...) -> env<unwrap_reference_t<Envs>...>;
```

¶1 `env` 由多个可查询对象构造一个可查询对象。对结果的查询按**词法顺序**依次尝试每个子对象。

¶5–8 精确地说：设 *fe* 是 `envs0, envs1, …` 中**第一个**使 `fe.query(q, args...)` 良构的元素；`query` 的约束是至少有一个这样的元素（¶7），效果是 `return fe.query(q, std::forward<Args>(args)...);`（¶8）。¶9：noexcept 说明与 `fe.query(...)` 一致。

所以 `env{a, b}` 中 `a` **遮蔽** `b`：两者都能回答同一查询时，取 `a` 的答案。这正是"在原环境上覆盖一项"所需要的语义：

```cpp title="env-shadow.cpp"
namespace ex = std::execution;

auto base   = ex::env{ex::prop(ex::get_scheduler, sch_a), ex::prop(std::get_allocator, alloc)};
auto merged = ex::env{ex::prop(ex::get_scheduler, sch_b), base};

// ex::get_scheduler(merged) 返回 sch_b：第一个子对象先回答
// std::get_allocator(merged) 返回 alloc：第一个子对象不回答，落到 base
```

¶2 `env` 的特化不可赋值。

¶3 除非 *expression-list* 只有一个类型为（可能 const 的）`env` 的元素，`env` 是否支持**圆括号**初始化未指定 {{unspec}}。实践上就是：**用花括号** `env{a, b}`。因为 `env` 被描述成一个有若干成员的聚合，实现可能真的把它做成聚合（C++20 起聚合支持圆括号初始化），也可能不是；标准不想对此作承诺。只有 `env(other_env)` 这种复制/移动形式保证可用。

¶4 例 1：`env{prop(get_allocator, my_alloc{}), prop(get_scheduler, my_sched{})}` 同时提供两个查询，再交给 `write_env`。

!!! note "env<> 的地位"
    `env<>` 是没有任何子对象的空环境；`get_env(o)` 在 `o` 没有 `get_env` 成员时就返回 `env<>{}`（[[exec.get.env]]），`value_types_of_t<Sndr>` 等别名的默认环境实参也是 `env<>`（[[exec.cmplsig]]）。对它的任何查询都只能走查询对象的默认路径。

## 与阐述用的 FWD-ENV / MAKE-ENV / JOIN-ENV 的关系

规范描述适配器时更多使用 [[exec.snd]] 中定义的几个阐述用"环境运算"：

| 阐述用实体 | 含义 | 类似于 |
|---|---|---|
| *FWD-ENV*(env) | 只转发 `forwarding_query(q)` 为 true 的查询 | — |
| *MAKE-ENV*(q, v) | 只回答 `q`，值为 `v` | `prop(q, v)` |
| *JOIN-ENV*(e1, e2) | 先问 `e1`，再问 `e2` | `env{e1, e2}` |

`prop` 与 `env` 是这些操作的**公开**版本，让用户在 `write_env` 等地方自己构造环境。

## 思考题

!!! question "1. 为什么 env 的 query 要求 “至少一个子对象能回答”？"
    如果没有 ¶7 的约束，`env<>{}.query(get_scheduler)` 会怎样？有约束又会怎样？

<details markdown="1">
<summary>答案</summary>

有了约束，没有子对象能回答时 `env<...>::query(q)` 不参与重载决议，于是 `env.query(q)` 非良构，查询对象可以回落到它的默认行为（如 `get_stop_token` 返回 `never_stop_token{}`），或者整个查询非良构，从而被 `requires` 表达式检测到。没有约束的话，`query` 在声明上总是存在，只有在实例化函数体时才出错——这会让"环境里有没有调度器"这种 SFINAE 式的检测全部失效，适配器就无法根据环境里有什么来选择行为了。
</details>

!!! question "2. 查询可以返回悬空引用吗？"
    `prop` 的 `query` 返回 `const ValueType&`。如果一个算法写 `auto& s = get_scheduler(get_env(rcvr));` 然后把 `s` 存起来，安全吗？

<details markdown="1">
<summary>答案</summary>

[exec.queryable.general] ¶6 只保证结果在可查询对象有效期间有效；[[exec.get.env]] ¶2 又只保证 `get_env(o)` 的值在 `o` 有效期间有效。如果 `get_env(rcvr)` 返回的是一个临时环境对象（很多接收器的 `get_env` 按值返回），那么 `s` 在该完整表达式结束后就悬空了。安全的写法是按值保存：`auto s = get_scheduler(get_env(rcvr));`——调度器要求可复制（[[exec.sched]]），复制它很便宜。
</details>

## 小结

- 可查询对象 = 以查询对象为键的只读表；`q(env)` ≡ `env.query(q)`（若良构）。
- `query` 成员应是 const、noexcept；查询结果不能是 `void`。
- `prop(q, v)`：单个键值对，构造时就检查 `q` 能否接受 `v`。
- `env{e1, e2, ...}`：按顺序查找，前者遮蔽后者；用花括号初始化；不可赋值。
