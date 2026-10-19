---
title: 重载决议
summary: 重载决议的总纲：七种语境各自列出候选函数，再统一地筛出可行函数、选出唯一的最佳函数；访问控制和 = delete 在选定之后才检查。
status: done
covers: over.match.general
related: over.match.funcs, over.match.viable, over.match.best, over.best.ics, over.ics.rank, topics/overload-resolution-walkthrough
tags: 重载决议
updated: 2026-10-19
---

!!! tldr
    - 重载决议分三步：列出候选函数，筛出可行函数，按隐式转换序列选出唯一的最佳可行函数。
    - 七种语境（普通调用、函数对象调用、运算符、构造函数、两类转换函数、引用绑定）列候选的方式各不相同，后两步完全一样。
    - 没有可行函数，或者没有一个比其他所有都好（歧义），调用就非良构。
    - 访问控制和 `= delete` 不参与选择：选中的函数不可访问或已删除时，程序非良构，不会改选次优的函数。
    - 可用候选指决议成功、且选中的是内建运算符或未删除、可访问的函数，这个术语主要服务于预置比较。

## 三步：候选、可行、最佳（¶1–¶2）

```cpp run ok
#include <cstdio>
void f(int)         { std::puts("f(int)"); }
void f(double)      { std::puts("f(double)"); }
void f(int, int)    { std::puts("f(int,int)"); }
void f(const char*) { std::puts("f(const char*)"); }

int main() {
  f('a');   // 打印 f(int)
}
```

调用 `f('a')` 时，名字查找找到四个 `f`，它们都是**候选函数**（[[g:candidate-function|candidate functions]]）。`f(int, int)` 形参个数不对，`f(const char*)` 无法从 `char` 转换过去，被排除；剩下的 `f(int)` 和 `f(double)` 是**可行函数**（[[g:viable-function|viable functions]]）。`char → int` 是整型提升，`char → double` 是浮点-整型转换，提升更好，所以 `f(int)` 是**最佳可行函数**。

¶1 重载决议从一组候选函数里选出最适合给定实参列表的那一个。依据是实参个数、实参与形参类型的匹配程度、（对非静态成员函数）对象与对象形参的匹配程度，以及候选函数的其他一些性质，比如是不是模板、约束的强弱，见 [[over.match.best#2]] 的决胜规则。

¶2 下面七种语境要做重载决议，每种语境用自己的方式确定候选函数和实参列表：

| | 语境 | 例子 | 候选从哪里来 |
|---|---|---|---|
| ¶2.1 | 函数调用语法中指名的函数 | `f(x)`、`obj.m(x)` | [[over.call.func]] |
| ¶2.2 | 用调用语法调用类对象：`operator()`，或转换成函数指针、函数引用的转换函数 | `fn(x)`，`fn` 是对象 | [[over.call.object]] |
| ¶2.3 | 表达式中的运算符 | `a + b`、`!a` | [[over.match.oper]] |
| ¶2.4 | 默认初始化或直接初始化类对象时的构造函数 | `T t(1, 2);` | [[over.match.ctor]] |
| ¶2.5 | 复制初始化类对象时的用户定义转换 | `T t = u;`（`u` 不是 `T` 类型） | [[over.match.copy]] |
| ¶2.6 | 用类类型表达式初始化非类类型对象时的转换函数 | `int i = obj;` | [[over.match.conv]] |
| ¶2.7 | 引用直接绑定到转换函数的结果 | `int& r = obj;` | [[over.match.ref]] |

列表初始化（[[over.match.list]]）和类模板实参推导（[[over.match.class.deduct]]）也复用这套机制。取重载函数的地址（[[over.over]]）不是重载决议，它按目标类型匹配，规则不同。

候选函数和实参列表确定之后，选择过程在所有语境中都相同：

- ¶2.8 先筛出**可行函数**：实参个数合适、约束满足、每个实参都有到对应形参的隐式转换序列（[[over.match.viable]]）；
- ¶2.9 再根据每个实参所需的**隐式转换序列**（[[g:implicit-conversion-sequence|implicit conversion sequence]]，把实参转换成形参类型所经过的步骤）选出**最佳可行函数**（[[over.match.best]]）。

## 选中之后：访问控制与删除（¶3）

¶3 存在唯一的最佳可行函数时，重载决议成功，结果就是它。否则重载决议失败，调用非良构。失败有两种：没有任何可行函数，或者有可行函数但没有一个比其他所有都好，后者就是**歧义**。

决议成功后，如果选中的函数在使用处不可访问，程序非良构。

```cpp error
class C {
  void f(int);          // private
public:
  void f(double);
};
void use(C& c) {
  c.f(1.0);             // OK: 选中 f(double)
  c.f(1);               // error: 选中 f(int)，但它是 private 的
}
```

`f(double)` 完全能接受 `1`，但重载决议不考虑访问权限，先选中精确匹配的 `f(int)`，再做访问检查，失败。¶1 的注 1 说的就是这一点：重载决议选出的函数不保证在当前语境下能用。

这样设计是为了让访问控制只能拒绝选择，不能改变选择。如果 `private` 成员从候选里消失，同一个调用在类内和类外就会选中不同的函数；类的作者把一个成员改成 `private`，可能悄悄改变外部代码调用的函数。现在这种改动最多导致编译错误。

被删除的函数（[[dcl.fct.def.delete]]）同理：它们照常参与重载决议，被选中后才报错。`= delete` 能用来禁止某些转换，靠的就是这一点：

```cpp error
void take(double);
void take(int) = delete;   // 不让 int 悄悄转成 double
void use() {
  take(1.0);               // OK
  take(1);                 // error: 选中被删除的 take(int)
  take(1.0f);              // OK: float → double 是提升，优于 float → int
}
```

如果被删除的函数不参与决议，`take(1)` 就会调用 `take(double)`，`= delete` 也就没有意义了。

!!! lawyer "例外：被定义为删除的预置移动操作"
    [[over.match.funcs#9]] 规定，预置的移动构造函数或移动赋值运算符被定义为删除时，在任何语境中都不是候选。否则，一个含不可移动成员的类在用右值初始化时会选中已删除的移动构造函数并报错，而不是退回到复制构造函数。

## 可用候选（¶4）

¶4 如果重载决议成功，并且选中的候选要么不是函数（即内建运算符候选，[[over.built]]），要么是未被删除且在决议处可访问的函数，就说结果是一个**可用候选**（[[g:usable-candidate|usable candidate]]）。

这个术语供 C++20 的预置比较使用。预置的 `==` 要逐个成员做 `==`，如果某个成员的 `==` 不是可用候选，外层的 `= default` 不报错，而是被定义为删除（[[class.compare]]）：

```cpp run ok
struct NoEq {
  bool operator==(const NoEq&) const = delete;
};
struct S {
  NoEq m;
  bool operator==(const S&) const = default;   // 被定义为删除
};
template<class T>
concept EqComparable = requires(const T& a, const T& b) { a == b; };
static_assert(!EqComparable<S>);
int main() {}
```

Clang 对 `S::operator==` 给出 `-Wdefaulted-function-deleted` 警告，说明它被隐式定义为删除。

!!! impl "编译器的实现"
    Clang 和 GCC 都按候选、可行、最佳三步实现，并记录每个不可行候选被排除的原因。诊断里的 "candidate function not viable: no known conversion from ... to ..." 就是在逐个解释候选为什么不可行。选最佳函数时，Clang 先遍历一遍找出一个不比任何对手差的候选，再遍历一遍确认它确实比所有其他候选都好，这正是 [[over.match.best]] 脚注描述的线性算法。

!!! history
    三步算法、七种语境、访问检查在决议之后，这些在 C++98 就已确立。之后各版本只是往里添加内容：C++11 的列表初始化、引用限定符、被删除的函数；C++17 的类模板实参推导；C++20 的约束、`==`/`<=>` 的改写候选和 ¶4 的可用候选；C++23 的显式对象形参。

## 常见误解

!!! pitfall "private 或 deleted 会让编译器改选次优的函数"
    不会。最佳函数不合格，程序就非良构。要让某个重载在外部不参与竞争，得让名字查找找不到它（例如放进别的作用域），或者用约束让它在可行性阶段就被排除。

!!! pitfall "有两个可行函数就是歧义"
    可行函数有多少个都没关系，只要有一个比其余的都好。歧义指没有唯一的最佳者，典型情况是 A 在第一个实参上更好、B 在第二个实参上更好（见 [[over.match.best#3]] 的例子）。

## 思考题

!!! question "1. 下面两处调用各选中哪个函数？程序良构吗？"
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

两处都选中 `S::g(int)`：`int → int` 精确匹配，胜过 `int → long` 的整型转换。在 `S::call` 里它可访问，良构；在 `h` 里不可访问，非良构（¶3）。如果访问权限参与决议，`h` 里会悄悄调用 `g(long)`。
</details>

!!! question "2. 为什么要专门定义可用候选，而不直接说重载决议成功？"

<details markdown="1">
<summary>答案</summary>

普通调用中，选中已删除或不可访问的函数直接就是错误，不需要单独的术语。但预置比较需要一个不直接报错的判定：成员的比较选中了已删除的函数时，外层的 `= default` 应当被定义为删除，而不是让整个程序非良构。内建运算符候选不是函数，谈不上删除和访问权限，所以定义里单独把它列为可用。
</details>
