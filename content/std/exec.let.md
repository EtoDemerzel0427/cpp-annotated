---
title: let_value / let_error / let_stopped
summary: 动态地"接上下一个异步操作"：前驱以对应处置完成时，把结果存进操作状态、以左值传给回调，回调返回一个新发送器，立即 connect 并 start；结果在第二个操作完成前一直有效；第二个操作的环境里带着前驱的完成调度器
status: done
covers: exec.let
papers: P2300R10
related: exec.adapt, exec.on, exec.snd, exec.connect, exec.snd.transform, exec.opstate
tags: 标准库, std::execution, 发送器适配器, let_value
updated: 2026-10-18
---

`then(f)` 把一个**同步**函数接在发送器后面。但很多时候"下一步"本身也是异步的，而且要用到上一步的结果才能构造出来：读到请求之后才知道要查哪张表，查到连接之后才能发查询。`let_value(f)` 就是为此而设：`f` 接受前驱的值，**返回一个发送器**；`let_value` 把这个发送器 connect 并 start，以它的完成作为自己的完成。

在函数式编程的术语里，`then` 是 `map`，`let_value` 是 `flat_map`（monadic bind）。

```cpp title="let-value.cpp"
namespace ex = std::execution;

ex::sender auto handle(connection& conn) {
  return read_request(conn)                          // 发送器：set_value_t(request)
       | ex::let_value([&conn](request& req) {       // 注意：req 是左值引用
           return query_db(req.table)                // 发送器：set_value_t(rows)
                | ex::then([&req](rows r) {          // 可以安全地引用 req
                    return make_response(req, r);
                  });
         });
}
```

最后一行注释点出了 `let_value` 最重要的性质：**回调收到的值被存在 `let_value` 的操作状态里，以左值传给回调；它们一直活到回调返回的那个发送器的操作完成**。所以回调返回的发送器可以**按引用**使用这些值——这是结构化并发"可以安全引用"的又一体现。

## 定义（¶1–4）

¶1 `let_value`、`let_error`、`let_stopped` 分别把发送器的 value、error、stopped 完成变换为一个新的**子异步操作**：把结果数据传给用户指定的可调用对象，它返回一个新发送器，该发送器被 connect 并 start。

¶2 对应的 *set-cpo* 分别是 `set_value`、`set_error`、`set_stopped`。*let-tag* 是三者各自独有的内部空标签类型。*let-env*(sndr, env) 取下列第一个良构者：

- ¶2.1 *SCHED-ENV*(get_completion_scheduler<decayed-typeof<set-cpo>>(get_env(sndr), FWD-ENV(env)))——前驱在对应处置上的完成调度器；
- ¶2.2 *MAKE-ENV*(get_domain, get_completion_domain<decayed-typeof<set-cpo>>(get_env(sndr), FWD-ENV(env)))——退一步，只提供完成 domain；
- ¶2.3 `env<>{}`。

¶3 `sndr` 不是发送器或 `f` 不满足 *movable-value* 时非良构。另外 `let_stopped(sndr, f)` 在 `F` 不满足 `invocable`（无实参可调用）时非良构——stopped 完成没有数据，所以回调必须是零参的，这一点可以在构造时就检查。

¶4 否则等价于 *make-sender*(*let-cpo*, f, sndr)。

## 降级为 let-tag（¶5–6）

¶6 *let-cpo*.transform_sender(s, es...) 等价于 *make-sender*(*let-tag*{}, *let-data*{s.template get<2>(), s.template get<1>()})，其中 *let-data* 是 `{Sndr sndr; Fn fn;}`。也就是说 `let_value` 发送器在 connect 前被改写为一个"数据是（子发送器, 回调）、没有子发送器"的内部发送器。把子发送器从"子发送器"位置挪进"数据"，是因为 `let` 需要自己管理子操作的连接方式（下面的 *let-state* 把它放进一个 `variant`），而不是交给 *connect-all*。

## 操作状态：let-state（¶10–15）

```cpp
template<class Cpo, class Sndr, class Fn, class Rcvr, class ArgsVariant, class OpsVariant>
struct let-state {
  using env_t = decltype(let-env(declval<Sndr>(), get_env(declval<Rcvr&>())));
  Fn fn;
  env_t env;
  ArgsVariant args;      // variant<monostate, decayed-tuple<前驱结果>...>
  OpsVariant ops;        // variant<monostate, 前驱的操作状态, 各种第二个操作的操作状态...>
  …
};
```

¶12 `args_variant_t` = `variant<monostate, as-tuple<LetSigs>...>`，`LetSigs` 是前驱签名中处置与 *set-cpo* 相同的那些，`as-tuple<Tag(Args...)>` 是 `decayed-tuple<Args...>`。

¶13 `ops_variant_t` = `variant<monostate, connect_result_t<child_t, let-state::receiver>, connect_result_t<as-sndr2<LetSigs>, receiver2<Rcvr, env_t>>...>`，`as-sndr2<Tag(Args...)>` 是 `call-result-t<F, decay_t<Args>&...>`——用**左值**调用回调得到的发送器类型。

关键的设计是 **`ops` 是一个 variant**：前驱的操作状态和第二个操作的操作状态**共用同一块存储**。前驱完成后它的操作状态就没用了（[[exec.async.ops#7]]：完成后失效），于是可以就地销毁、再在同一位置构造第二个操作状态。整个 `let_value` 的操作状态大小是 max(前驱, 第二个) 而不是二者之和——一长串 `let_value` 嵌套时这很重要。

构造时（¶10）：`ops` 先就地构造前驱的操作状态（`in_place_type<op_t>`，用 `let-state::receiver{*this, rcvr}` connect）。*start*（¶15）就是 `start(get<op_t>(state.ops))`。

前驱完成时调用 *impl*：

```cpp
if constexpr (is_same_v<Tag, Cpo>) {          // 对应的处置
  try {
    auto& tuple = args.template emplace<args_t>(std::forward<Ts>(ts)...);   // 1. 存下结果
    ops.template emplace<monostate>();                                       // 2. 销毁前驱的操作状态
    auto&& sndr = apply(std::move(fn), tuple);                               // 3. 以左值调用回调
    auto mkop2 = [&] { return connect(std::forward<sender_type>(sndr), receiver_type{rcvr, env}); };
    auto& op = ops.template emplace<op_t>(emplace-from{mkop2});              // 4. 就地 connect
    start(op);                                                               // 5. 启动
  } catch (...) {
    if constexpr (!nothrow) set_error(std::move(rcvr), current_exception());
  }
} else {
  tag(std::move(rcvr), std::forward<Ts>(ts)...);   // 其他处置原样转发
}
```

逐步看：

1. **结果先 decay-copy 进 `args`**。前驱完成函数的实参可能是指向前驱操作状态内部的引用，第 2 步就要销毁它，所以必须先复制。
2. **`ops.emplace<monostate>()` 销毁前驱的操作状态**。注意这发生在前驱的 `set_value` **之内**——前驱正在调用我们的接收器。这依赖 [[exec.async.ops#8]] "操作状态的生存期可以在完成操作执行期间结束"。
3. **回调以 `apply(std::move(fn), tuple)` 调用**：`tuple` 是左值，所以每个值以 `decay_t<Args>&` 传入——回调可以接受 `T&`（甚至修改它），也可以接受 `const T&` 或按值。回调本身以右值调用。
4. **用 *emplace-from* 就地构造**第二个操作状态（[[exec.snd]]、[[exec.opstate]]：操作状态不可移动）。
5. **启动**。第二个操作完成时，*receiver2* 直接把完成转发给外部接收器。

`nothrow` 为假时才有 `catch` 中的 `set_error`：它取决于复制结果、调用回调、connect 第二个发送器三者是否都不抛异常。这就是为什么 [[exec.connect]] 要求 connect 的 noexcept 性只取决于环境类型：签名计算阶段需要据此决定是否报告 `set_error_t(exception_ptr)`。

## 第二个操作的环境：receiver2（¶8）

*receiver2*<Rcvr, Env> 把三种完成原样转给外部接收器，它的 `get_env()` 返回的环境对查询 `q`：

- 先问 `env`（即 *let-env* 的结果）；
- 不行且 `q` 是转发查询，就问外部接收器的环境；
- 否则非良构。

结合 ¶2 的 *let-env*：第二个操作的环境里，`get_start_scheduler` 是**前驱的完成调度器**。这是事实："第二个发送器在前驱完成的地方被 connect 和 start"——前驱在线程池上完成，回调就在线程池线程上被调用，第二个操作也在那里启动。环境如实报告这一点，第二个发送器（比如 `on`、`affine`、`task`）就能据此做正确的决定。

## 类型检查（¶9、¶14）

¶9 *check-types*：对前驱每个对应处置的签名 `Tag(Ts...)`，要求

- ¶9.1 `Ts` 都能 decay-copy；
- ¶9.2 `invocable<LetFn, decay_t<Ts>&...>`——回调能以左值调用；
- ¶9.3 回调返回值是发送器；
- ¶9.4 有环境时，返回的发送器在 *JOIN-ENV*(*let-env*(...), *FWD-ENV*(env)) 下满足 `sender_in`。

否则抛异常（类型错误）。

¶14 *get-state* 的约束：`args_variant_t` 和 `ops_variant_t` 都良构。（草案此处写作 `ops2_variant_t`，应是 ¶13 中 `ops_variant_t` 的笔误。）

## 语义要求（¶16）

¶16 若 connect 结果的异步操作在启动后不满足下列要求，`connect(out_sndr, rcvr)` 行为未定义：

- ¶16.1 当 *set-cpo* 以 `sndr` 的结果数据被调用时，调用 `f`；
- ¶16.2 使自己的完成依赖于 `f` 返回的发送器的完成；
- ¶16.3 传播 `sndr` 发出的其他完成。

与 `then` 一样，这条约束的是 domain 定制的替代实现。

## let_error 与 let_stopped

`let_error(f)`：前驱以 error 完成时，以 `f(err)` 返回的发送器继续——"出错时换一条路"，例如重试、降级到缓存。`let_stopped(f)`：前驱被取消时，以 `f()` 返回的发送器继续。[[exec.adapt]] 中的 `stopped_as_optional`、`stopped_as_error` 都是用 `let_stopped` 实现的。

```cpp title="let-error-retry.cpp"
namespace ex = std::execution;

auto fetch_with_fallback = fetch_remote()
  | ex::let_error([](auto&& err) {           // 远端失败：改读本地缓存
      return read_cache();
    });
```

注意：`let_error` 的回调返回的发送器必须对**所有**错误类型都可以调用（如果前驱可能以多种错误类型完成，回调要对每种都能调用，返回的发送器类型可以不同——`ops_variant_t` 为每种可能分别预留了一个分支）。

## 陷阱

!!! pitfall "按值接收后返回引用它的发送器"
    ```cpp title="let-dangling.cpp"
    auto s = read_request(conn)
      | ex::let_value([](request req) {            // 按值：req 是回调的局部变量
          return ex::just() | ex::then([&req] { use(req); });   // UB：req 在回调返回时已销毁
        });
    ```
    `let_value` 保证的是**它自己存储的** `decay_t<Args>` 对象活到第二个操作结束；回调形参若按值接收，得到的是一份副本，回调一返回就没了。要引用就用 `request&` 形参。

!!! pitfall "以为 let_value 的回调在 connect 时调用"
    回调在前驱**完成时**调用，在前驱完成所在的执行代理上，与 `then` 一样。它返回的发送器的 connect 也发生在那时。所以回调里的代码需要考虑它在哪个线程上运行；第二个发送器在环境中可以通过 `get_start_scheduler` 得知这一点。

## 思考题

!!! question "1. 两个操作状态为什么可以共用存储？"
    `ops` 是一个 `variant`，前驱的操作状态在其完成函数内部被销毁。请指出允许这一做法的两条规则。

<details markdown="1">
<summary>答案</summary>

(1) [[exec.async.ops#7]]：完成操作开始执行时异步生存期结束，此后操作状态失效，前驱的实现不能再访问它；(2) [[exec.async.ops#8]]：操作状态的生存期可以在完成操作执行期间结束。前驱调用 `set_value` 后不再触碰自己，所以在 `set_value` 内部销毁前驱的操作状态是安全的。另外第 1 步先把结果数据复制进 `args`，保证了即使实参是引用、指向前驱的操作状态，复制之后再销毁也不会悬空。
</details>

!!! question "2. 回调抛异常"
    `let_value` 的回调抛出异常时，外部接收器收到什么？此时 `args` 与 `ops` 各处于什么状态？

<details markdown="1">
<summary>答案</summary>

按 *impl* 的阐述代码：第 1 步已把结果存进 `args`，第 2 步已把 `ops` 置为 `monostate`（前驱的操作状态已销毁），第 3 步回调抛出异常，跳到 `catch`。只要 `nothrow` 为假（回调未声明 noexcept 时就是如此），就执行 `set_error(std::move(rcvr), current_exception())`，外部接收器以 `exception_ptr` 收到这个异常；相应地，签名中会有 `set_error_t(exception_ptr)`。此后 `args` 仍持有那份结果副本、`ops` 是 `monostate`，它们随整个操作状态在外部决定销毁时一起销毁。如果回调声明为 noexcept 且复制、connect 也都不抛，`catch` 分支里的 `set_error` 不会被实例化，签名里也就没有那个 `exception_ptr`。
</details>

## 小结

- `let_value(f)`：前驱值 → 存进操作状态 → 以左值传给 `f` → `f` 返回的发送器就地 connect 并 start。
- 存储的结果活到第二个操作完成，可以被安全引用；回调形参要用引用才能享受这一点。
- 前驱与第二个操作的操作状态共用一个 `variant`，前驱在其完成函数内被销毁。
- 第二个操作的环境报告前驱的完成调度器为 `get_start_scheduler`。
- `let_error`、`let_stopped` 同理；后者回调无参，构造时即检查。
