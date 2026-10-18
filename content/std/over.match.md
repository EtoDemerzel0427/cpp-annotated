---
title: 重载决议
summary: 重载决议的总纲：在七种语境下构造候选函数集，筛出可行函数，再按隐式转换序列选出唯一的最佳可行函数；访问控制与 deleted 都在选定之后才检查。
status: draft
covers: over.match.general
related: over.match.funcs, over.match.viable, over.match.best, over.best.ics, over.ics.rank, topics/overload-resolution-walkthrough
tags: 重载决议
updated: 2026-10-17
---

[[over.match]] 是第 12 章的心脏。它的总则 [[over.match.general]] 只有四段，却规定了整个算法的骨架：**在哪些场合**要做重载决议、**按什么步骤**做、**结果意味着什么**。之后的子条款分别填充每一步的细节：

| 步骤 | 子条款 | 本站页面 |
|---|---|---|
| 构造候选函数与实参列表 | [over.match.funcs] | [[over.match.funcs]]、[[over.match.oper]]、[[over.match.class.deduct]] |
| 筛选可行函数 | [over.match.viable] | [[over.match.viable]] |
| 选出最佳可行函数 | [over.match.best] | [[over.match.best]] |
| 隐式转换序列及其排序 | [over.best.ics]、[over.ics.rank] | [[over.best.ics]]、[[over.ics.rank]] |

读这一节前最好先熟悉名字查找（[[basic.lookup]]）：重载决议**只**在查找交给它的集合上工作。

## 重载决议是什么（¶1）

¶1 重载决议是一种机制：给定一组将作为调用实参的表达式，以及一组根据调用语境可被调用的**候选函数**（candidate functions），从中选出**最佳**的那个。选择依据有：

- 实参的**个数**；
- 实参与候选函数**形参类型列表**的匹配程度；
- （对非静态成员函数）**对象**与**对象形参**的匹配程度；
- 候选函数的某些**其他属性**——比如是不是模板、约束强弱、是不是改写候选，见 [[over.match.best#2]] 的决胜规则。

注 1 是整节最重要的一句提醒：

!!! std
    "The function selected by overload resolution is not guaranteed to be appropriate for the context."

    重载决议选出的函数不保证适合该语境。

换句话说，重载决议是**纯粹基于类型**的竞赛。比赛结束、冠军产生之后，才检查冠军能否上场——访问控制、是否被删除、默认实参是否唯一、窄化……冠军不合格，**不会**让亚军顶替，而是整个程序非良构。

## 七种语境（¶2）

¶2 标准列出了重载决议介入的七种语境。每种语境以**自己的方式**确定候选函数集与实参列表：

| # | 语境 | 典型代码 | 候选集定义 |
|---|---|---|---|
| 2.1 | 函数调用语法中指名的函数 | `f(x)`、`obj.m(x)` | [[over.call.func]] |
| 2.2 | 对类对象使用函数调用语法：`operator()`，或转换到函数指针/函数引用的转换函数 | `fn(x)`，其中 `fn` 是对象 | [[over.call.object]] |
| 2.3 | 表达式中的运算符 | `a + b`、`a == b`、`!a` | [[over.match.oper]] |
| 2.4 | 类对象的默认初始化或直接初始化时调用构造函数 | `T t(1, 2);`、`T t;` | [[over.match.ctor]] |
| 2.5 | 类对象拷贝初始化中的用户定义转换 | `T t = u;`（`u` 不是 `T` 或其派生类） | [[over.match.copy]] |
| 2.6 | 用类类型表达式初始化非类类型对象时的转换函数 | `int i = obj;` | [[over.match.conv]] |
| 2.7 | 引用直接绑定到转换函数结果 | `int& r = obj;` | [[over.match.ref]] |

此外还有两个"派生"语境用的是同一套机器：列表初始化（[[over.match.list]]，构造函数分两阶段挑）和类模板实参推导（[[over.match.class.deduct]]，在推导指引上做一次假想的构造函数重载决议）。取函数地址（[[over.over]]）则**不是**重载决议——它按目标类型做匹配，规则不同。

一旦候选集和实参列表确定，**选择过程在所有语境下都相同**：

- ¶2.8 首先，从候选函数中挑出**可行函数**（viable functions）：实参个数合适、约束满足、每个实参都存在到对应形参的隐式转换序列（[[over.match.viable]]）。
- ¶2.9 然后，根据每个实参到对应形参所需的**隐式转换序列**（implicit conversion sequence，ICS），选出**最佳可行函数**（[[over.match.best]]）。

这个"候选 → 可行 → 最佳"的三段式是整章的主线。把它记牢，任何一个具体问题都能拆成这三个子问题。

```cpp run ok
#include <cstdio>
void f(int)    { std::puts("f(int)"); }
void f(double) { std::puts("f(double)"); }
void f(int, int) { std::puts("f(int,int)"); }
void f(const char*) { std::puts("f(const char*)"); }

int main() {
  f('a');
  // 候选：4 个 f（名字查找找到的全部）
  // 可行：f(int)       —— char→int 是整型提升（Promotion）
  //       f(double)    —— char→double 是浮点-整型转换（Conversion）
  //       f(int,int)   —— 个数不符，不可行
  //       f(const char*) —— char 无法隐式转换为指针，不可行
  // 最佳：f(int)，因为 Promotion 优于 Conversion
}
```

## 成功、失败与访问检查（¶3）

¶3 若存在唯一的最佳可行函数，重载决议**成功**并以它为结果；否则**失败**，调用非良构。失败有两种形态：

- **无可行函数**（no viable function）：候选集为空，或者没有一个候选可行；
- **歧义**（ambiguous）：有可行函数，但没有一个比其余所有都好。

成功之后，如果最佳可行函数在使用它的语境中**不可访问**，程序非良构。

```cpp
class C {
  void f(int);          // private
public:
  void f(double);
};
void use(C& c) {
  c.f(1.0);             // OK：选中 public 的 f(double)
  c.f(1);               // error: 选中 f(int)（精确匹配），但它是 private 的
}
```

`c.f(1)` 失败的原因不是"没有合适的函数"——`f(double)` 完全可以接受 `1`——而是重载决议先**无视访问性**选出了 `f(int)`，然后访问检查失败。这正是 C++ 的刻意设计：

!!! note "为什么访问控制不参与重载决议？"
    如果 `private` 成员会从候选集中消失，那么**同一个调用在类内和类外会选中不同的函数**，类的作者把一个成员从 `public` 改成 `private`，就可能静默改变外部代码的行为。C++ 选择让访问控制只能**拒绝**、不能**改变**选择：访问性改变只会导致编译错误，绝不会导致行为悄悄变化。这个原则（"access control doesn't affect overload resolution"）自 C++98 起一直不变。

被删除的函数（[[dcl.fct.def.delete]]）同理：它们**是**候选、**可以**被选中，被选中后对它的引用才非良构。这正是 `= delete` 能用来"禁掉某些转换"的原因：

```cpp
void take(double);
void take(int) = delete;   // 不让 int 静默转成 double
void use() {
  take(1.0);               // OK
  take(1);                 // error: 选中被删除的 take(int)
  take(1.0f);              // OK：float→double 是提升，float→int 是转换
}
```

如果被删除的函数不参与重载决议，`take(1)` 会悄悄调用 `take(double)`，`= delete` 就失去了意义。

!!! lawyer "例外：被定义为删除的默认移动操作"
    [[over.match.funcs#9]] 规定：被**隐式**定义为删除的**预置**移动构造/移动赋值**不是**候选。这是有意为之的特殊处理：否则一个不可移动的成员会让整个类在右值上"选中已删除的移动构造"而报错，而不是回退到拷贝构造。见 [[over.match.funcs]]。

## 可用候选（¶4）

¶4 定义了一个术语**可用候选**（[[g:usable-candidate|usable candidate]]）：重载决议成功，且选出的候选要么不是函数（即内建运算符候选，[[over.built]]），要么是**未被删除且可访问**的函数。

这个术语是为 C++20 的预置比较运算符服务的：[[class.compare.default]] 用"`a @ b` 是否 *usable*"来决定一个 `= default` 的 `operator==`/`operator<=>` 是被定义还是被定义为删除；[[class.compare.secondary]] 用它来决定 `operator<` 等次级比较运算符的预置定义是否可用。它把"决议成功"与"选中的东西真能用"打包成一个判定，避免在多处重复"不是 deleted、可以访问"的措辞。

```cpp run ok
#include <compare>
struct NoEq {
  bool operator==(const NoEq&) const = delete;
};
struct S {
  NoEq m;
  bool operator==(const S&) const = default;   // m == m 不是 usable → 本函数被定义为删除
                                               // （Clang 对此给出 -Wdefaulted-function-deleted 警告）
};
template<class T> concept EqComparable = requires(const T& a, const T& b) { a == b; };
static_assert(!EqComparable<S>);   // S 的 == 存在但被删除：表达式无效
int main() {}
```

## 实现视角

!!! impl
    - 主流编译器都按"候选 → 可行 → 最佳"实现，但为了诊断质量会保留所有不可行候选的失败原因：Clang 的"candidate function not viable: no known conversion from … to …"、GCC 的"candidate: … / no known conversion for argument 1 from … to …"都是在列举候选集中每个成员为何出局。读懂这类诊断，本质上就是读懂 [[over.match.viable]]。
    - [[over.match.best]] 的脚注描述了一个线性算法（锦标赛 + 二次验证），Clang 的 `OverloadCandidateSet::BestViableFunction` 正是这样实现的：先遍历一次找出"不比任何对手差"的候选，再遍历一次验证它确实比所有其他候选都好。

## 历史与演进

!!! history
    - **C++98**：七种语境、三步算法、"访问检查在决议之后"已经全部到位，整体框架此后基本不变。
    - **C++11**：加入列表初始化（[[over.match.list]]）、引用限定符、被删除函数参与决议、隐式删除的移动操作不是候选。
    - **C++17**：加入类模板实参推导（[[over.match.class.deduct]]）。
    - **C++20**：加入约束（不满足 → 不可行；更受约束 → 胜出）、运算符改写候选（`==`/`!=`/`<=>`），并引入 ¶4 的"可用候选"以服务于预置比较。
    - **C++23**：显式对象形参；[[P1787R6]] 重写了查找与"对应声明"，¶2.2 的措辞也随之调整。
    - **C++26**：{{c++26}} 反射的 *splice-expression* 可以指定候选集（见 [[over.call.func]]）。

## 陷阱

!!! pitfall "以为 private/deleted 会让编译器'退而求其次'"
    不会。冠军不合格 = 程序非良构。若要让某个重载对外不可见，需要让它在**名字查找**阶段就看不到（例如放在别的作用域），或者用约束让它在**可行性**阶段被排除。

!!! pitfall "把'歧义'理解成'有两个可行函数'"
    有多少个可行函数都没关系，只要有一个比其余所有都好。歧义指的是**没有**唯一最好者——通常是 A 在某个实参上更好、B 在另一个实参上更好（见 [[over.match.best#3]] 的 `Fcn` 例子）。

## 思考题

!!! question "1. 下面的调用选中哪个函数？程序良构吗？"
    ```cpp nocheck
    struct S {
      void g(long);
    private:
      void g(int);
    public:
      void call() { g(1); }
    };
    void h(S s) { s.g(1); }
    ```

<details markdown="1">
<summary>答案</summary>

两处都选中 `S::g(int)`（精确匹配胜过 int→long 的整型转换）。在 `S::call` 内部它可访问，良构；在 `h` 中不可访问，非良构。这正好演示了"访问性不影响选择"：如果访问性参与决议，`h` 里会静默调用 `g(long)`。
</details>

!!! question "2. 为什么 [[over.match.general]] 要专门定义'usable candidate'，而不直接说'重载决议成功'？"

<details markdown="1">
<summary>答案</summary>

因为在预置比较运算符的语境下，"决议成功但选中了 deleted 或不可访问的函数"必须被当作"不可用"，从而让外层的 `= default` 函数被定义为删除，而不是让整个程序非良构。普通调用中这两种情况都是错误，没必要区分；但 [[class.compare.default]] 需要一个"安静地失败"的判定，所以引入了这个术语。另外，内建运算符候选不是函数，谈不上 deleted 或访问性，定义中也专门把它排除在外。
</details>

## 小结

!!! summary
    - 重载决议 = 在**名字查找给出的**候选集上，按 候选 → 可行 → 最佳 三步选出唯一函数。
    - 七种语境各自定义候选集和实参列表；选择过程统一。
    - 失败 = 无可行函数 或 歧义；两者都非良构。
    - 选定之后才检查访问性、是否删除；它们只能让程序非良构，不会改变选择。
    - "可用候选" = 决议成功且结果是内建运算符或未删除、可访问的函数；服务于预置比较。
