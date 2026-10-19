---
title: assume 属性
summary: "[[assume(expr)]]; 告诉编译器 expr 在这里为真，供它优化：表达式从不执行，但假设不成立就是未定义行为；编译器也可以完全不理会它。"
status: done
since: c++23
papers: P1774R8
related: dcl.attr.grammar, intro.defs, expr.const.core, basic.def.odr, conv.general, stmt.pre, basic.contract, utility.unreachable
tags: 属性, 优化, UB, assume
updated: 2026-10-19
---

!!! tldr
    - `[[assume(e)]];` 是程序员对编译器的保证：执行到这里时 `e` 为真。编译器可以据此删掉多余的检查和分支，也可以完全忽略它。
    - `e` 从不执行，`[[assume(++y == 43)]]` 不会递增 `y`；但 `e` 仍算潜在求值，用到的变量要被 lambda 捕获。
    - 如果 `e` 在这里求值不会得到 `true`，执行这个假设就是未定义行为。错误的假设可以让编译器删掉你的兜底检查。
    - 常量求值中遇到为假的假设，是否报错由实现决定，本机 Clang 会报错。
    - Clang 会忽略含副作用（包括调用普通函数）的假设，并给出 `-Wassume` 警告。

## 一个假设能带来什么

<div class="compare" markdown="1">

```cpp run ok
int divide_by_32(int x) {
  [[assume(x >= 0)]];
  return x / 32;
}
```

```cpp run ok
int plain(int x) {
  return x / 32;
}
```

</div>

本机 Clang 23 以 `-O2` 为 x86-64 生成的代码：

```text
divide_by_32:                plain:
    mov  eax, edi                lea   eax, [rdi + 31]
    shr  eax, 5                  test  edi, edi
    ret                          cmovns eax, edi
                                 sar   eax, 5
                                 ret
```

有符号整数除法向零取整。负数右移会向负无穷取整，所以 `plain` 要先给负数加上 31 再做算术右移。`divide_by_32` 告诉了编译器 `x >= 0`，一条逻辑右移就够了。

`[[assume(e)]];` 是 C++23 引入的**假设**（[[g:assumption|assumption]]），由 [[P1774R8]] 把各家已有的内建功能标准化：Clang 的 `__builtin_assume`、MSVC 的 `__assume`，以及 GCC 上常用的 `if (!(e)) __builtin_unreachable();`。

## 规则（¶1）

!!! std
    If the converted expression would evaluate to `true` at the point where the assumption appears, the assumption has no effect. Otherwise, evaluation of the assumption has runtime-undefined behavior.

¶1 的规定可以分成四点：

1. `assume` 只能用于空语句，也就是单独一个 `;`。这样的语句叫做假设。
2. 必须带参数，形式是 `( conditional-expression )`，表达式按上下文转换为 `bool`（[[conv.general]]）。
3. 表达式不求值。
4. 如果转换后的表达式在假设所在的位置会求值为 `true`，假设没有效果；否则，执行这个假设具有**运行期未定义行为**（[[g:runtime-undefined-behavior|runtime-undefined behavior]]）：普通执行中是 UB，常量求值中另有规定，见下文。

```cpp run error
int g(int x) {
  [[assume(x > 0), assume(x < 10)]];  // OK：两个假设
  [[assume(x > 0 && x < 10)]];        // OK
  [[assume(x > 0, x < 10)]];          // error: 顶层逗号
  return x;
}
int h(int x) {
  [[assume(x > 0)]] return x;         // error: 只能用于空语句
}
[[assume(true)]] int bad;             // error: 不能用于声明
```

参数限定为 *conditional-expression*，就排除了赋值和逗号表达式。`[[assume(x = 1)]]` 几乎一定是把 `==` 写成了 `=`；顶层逗号容易被误读成两个参数。真想写它们时可以加括号，比如 `[[assume((x > 0, x < 10))]]`，但这是一个逗号表达式，只假设了 `x < 10`。

## 表达式不执行，判断的是假想的结果

```cpp run ok
int f(int y) {
  [[assume(++y == 43)]];   // y 不会被递增
  return y;                // 可以换成 return 42;
}
int main() { return f(42) - 42; }
```

这是标准的例子。规则说的是会求值为 `true`（would evaluate to true），判断的是假如在这里求值一次，结果是什么。`f(42)` 中，假想地求值 `++y == 43` 得到 `true`，所以没有 UB，`y` 也没有真的被递增。编译器由此推出 `y` 进入时等于 42，可以把 `return y;` 换成 `return 42;`。调用 `f(41)` 时假想的结果是 `false`，那就是 UB。

按这种理解，下面的情形也不算求值为 `true`，同样是 UB：

- 假想的求值本身就有 UB，比如 `p` 为空时的 `[[assume(*p == 0)]]`；
- 假想的求值会抛出异常、不会结束，或者调用 `std::exit`。

本机 Clang 23 实际上会忽略这个假设，因为表达式有副作用，见后文。

## 潜在求值：会 odr-use（¶2）

```cpp run error
void f(int x) {
  auto l1 = [] { [[assume(x > 0)]]; };   // error: 没有捕获 x
  auto l2 = [=] { [[assume(x > 0)]]; };  // OK：按值捕获了 x
  static_assert(sizeof(l2) == sizeof(int));
  (void)l1;
}
```

¶2 注 1 指出，假设的表达式是**潜在求值**的（[[basic.def.odr]]）。它和 `sizeof`、`decltype` 的操作数不同，后者是不求值操作数。所以表达式中出现的变量算作被使用（odr-use），用到的函数必须有定义，在 lambda 里还要被捕获。上例的 `l2` 因此多出了一个 `int` 大小的成员。

这样规定是因为假设的含义建立在假如求值的结果之上。要让这个结果有定义，表达式就得像普通表达式一样，完整地完成名字绑定、模板实例化和 odr-use。

## 编译器可以不理会（¶2）

¶2 注 1 的后半说明了设计意图：实现可以分析表达式的形式，推导出用于优化的信息，但并不需要从任何一个假设中推导出任何东西。完全不利用假设的实现，`__has_cpp_attribute(assume)` 应为 0。

所以假设是一份单方面的承诺：程序员保证 `e` 为真，做不到就是 UB；编译器可以利用，也可以不利用。删掉一个假设只会让原来 UB 的执行变成有定义的执行，这正是 [[dcl.attr.grammar#8]] 要求标准属性满足的可忽略性。

### 含副作用的假设

```cpp run ok
int counter();
void f() {
  [[assume(counter() > 0)]];   // 合法，但被 Clang 忽略
}
int main() {}
```

标准允许表达式有副作用，反正它不会执行。但编译器很难从这样的表达式里推出有用的事实。本机 Clang 23 只要发现表达式可能有副作用，包括调用一个没有标为 `const` 或 `pure` 的函数，就整个忽略这个假设，并警告 `assumption is ignored because it contains (potential) side-effects`。实现不需要推导任何信息，所以这样做是允许的。

## 常量求值中的假设

```cpp run impl
constexpr int g(int x) {
  [[assume(x > 0)]];
  return x;
}
constexpr int a = g(1);    // OK
constexpr int b = g(-1);   // 是否报错由实现决定
```

常量求值中通常不允许出现未定义行为，遇到就不是常量表达式。运行期未定义行为是一个例外：按 [[expr.const.core#3]]，一个表达式如果只因为它而可能不是常量表达式，结果由实现定义。所以常量求值遇到一个为假的假设时，实现可以报错，也可以忽略它继续算。本机 Clang 23 选择报错，提示 `assumption evaluated to false`。

不要求一律报错，是因为那样会迫使实现在常量求值中真的去算每个假设表达式。而假设表达式可能代价很高，或者有副作用，例如 `++y == 43`，它从设计上就不该被求值。

## 与相近工具的比较

| 写法 | 条件为假时 | 是否执行表达式 | 用途 |
|---|---|---|---|
| `[[assume(e)]];` | 运行期 UB | 否 | 给优化器提供事实 |
| `assert(e)` | 调试版终止；定义 `NDEBUG` 时什么也不做 | 仅调试版 | 调试检查 |
| `contract_assert(e)`（C++26，[[basic.contract]]） | 取决于求值语义：忽略、报告后继续、终止 | 取决于语义 | 检查和文档 |
| `if (!e) std::unreachable();`（C++23） | UB | 是 | 标记不可达的代码 |

`std::unreachable()` 的写法会执行 `e`，有副作用就会发生；`assume` 不会。

一种常见做法是写一个宏，调试版里检查条件、发布版里改成假设。这样做会把发布版里的断言失败从可以报告的错误变成任意行为，使用前要清楚这个代价。

!!! impl "实现视角"
    - Clang 把 `[[assume(e)]]` 降低为 LLVM 的 `llvm.assume`，与 `__builtin_assume(e)` 相同。
    - GCC 13 起支持 `[[assume]]`，也接受 `__attribute__((assume(e)))`。
    - MSVC 长期提供 `__assume(e)`，`__assume(0)` 表示不可达。
    - 假设会在优化器的中间表示里留下额外的节点，过多或过于复杂的假设可能妨碍其他优化。只在测量证明有收益时使用。

## 历史与演进

!!! history
    - C++23 引入（[[P1774R8]]）。提案讨论过函数、关键字、属性等多种形式，最终选了属性，因为删掉它不会改变正确程序的含义。
    - C++23 的措辞是行为未定义，并把常量求值中为假的假设列为是否构成核心常量表达式未指定的情形。当前草案引入了运行期未定义行为这个术语，改为由实现定义。

## 常见误解

!!! pitfall "假设错了只是优化失效"
    假设错了是 UB。编译器可以基于假设删掉代码，包括你用来兜底的检查：

    ```cpp
    int f(int* p) {
      [[assume(p != nullptr)]];
      if (!p) return -1;   // 这一行可以被直接删掉
      return *p;
    }
    ```

!!! pitfall "表达式会被执行"
    `[[assume(init() == 0)]];` 不会调用 `init()`。

## 思考题

!!! question "思考题 1"
    下面的 `f(41)` 有没有 UB？`f(42)` 返回什么？
    ```cpp
    int f(int y) {
      [[assume(++y == 43)]];
      return y;
    }
    ```

<details markdown="1">
<summary>答案</summary>

`f(41)`：假想求值时 `y` 变成 42，比较结果为 `false`，假设不会求值为 `true`，所以执行这个假设是 UB，返回值没有任何保证。

`f(42)`：假设成立，没有 UB。表达式没有真的执行，`y` 仍是 42，返回 42。
</details>

!!! question "思考题 2"
    为什么说 `[[assume]]` 满足 [[dcl.attr.grammar#8]] 的可忽略性要求？设想一个违反它的属性。

<details markdown="1">
<summary>答案</summary>

带 `[[assume(e)]]` 的程序，在 `e` 为假的执行中是 UB，允许任何行为。删掉它之后，这些执行按普通规则继续，结果落在任何行为之内；`e` 为真的执行不受影响。所以删除后的可能执行是原来的子集。

一个违反它的假想属性是 `[[check(e)]]`，含义是 e 为假时调用 `std::terminate`。删掉它，原本必定终止的执行会继续运行下去，出现了原程序里不可能有的执行。契约断言要有自己的语法而不能做成属性，原因就在这里。
</details>
