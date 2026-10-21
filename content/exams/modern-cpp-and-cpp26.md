---
title: 第六卷 · C++20 到 C++26 的新规则
summary: 25 道题，考查 C++20 以来新增规则的边界：显式对象形参、C++23 的几处语法放宽、协程的限制与形参生命周期、默认比较与改写候选、consteval 与 if consteval、模块中的暴露，以及 C++26 的错误行为、占位符 _、包索引、结构化绑定包与条件、带理由的 delete、static_assert 消息、constexpr placement new、契约和静态反射。
status: done
order: 6
related: dcl.fct, expr.prim.this, dcl.fct.def.coroutine, class.compare.default, over.match.oper, expr.const.imm, basic.link, basic.indet, basic.scope.scope, dcl.struct.bind, dcl.contract.func, basic.contract.eval, dcl.type.splice, papers/deducing-this, papers/contracts, papers/reflection, papers/erroneous-behaviour, papers/pack-indexing, topics/coroutines
tags: 考卷, C++20, C++23, C++26, 协程, 默认比较, consteval, 模块, 错误行为, 契约, 反射
updated: 2026-10-20
---

!!! tldr
    - 考查范围：显式对象形参（[[dcl.fct]]）、C++23 的 `[[assume]]` 与复合语句末尾的标号，协程（[[dcl.fct.def.coroutine]]），默认比较与 `==` 的改写（[[class.compare.default]]、[[over.match.oper]]），`if consteval`（[[expr.const.imm]]），模块接口中的暴露（[[basic.link]]），以及 C++26 的错误行为、`_`、包索引、结构化绑定、`= delete("…")`、`static_assert` 消息、constexpr placement new、契约和反射。
    - 生命周期、初始化、名字查找与重载决议的经典规则、模板、常量求值的一般规则各有单独的考卷，本卷只在新规则需要时引用它们。
    - 不少题的标准判定与本机 Clang 23 的表现不同：有的是 Clang 只给警告，有的是尚未实现。解析里都单独说明，作答时一律按当前草案判定。
    - 建议用时 100 分钟。判定题按整个程序给出最重的一项判定；选择题如果问输出，都已实际运行核对。

## 一、显式对象形参与 C++23 的小改动

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++23}} 判定整个程序。

```cpp run
struct Counter {
  int n = 0;
  int next(this Counter& self) {
    self.n += 1;
    return n;
  }
};

int main() {
  Counter c;
  return c.next();
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`return n;` 不能使用。**

`next` 的第一个形参带 `this`，它是显式对象成员函数（[[dcl.fct#8]]）。问题出在函数体里不加限定的 `n`。

1. [[expr.prim.id.general#2]]：当一个 *id-expression* 指代某个类的非静态成员，而且出现在这个类的作用域里，它会被改写成以 `(*this)` 为对象表达式的成员访问。`n` 满足条件，于是变成 `(*this).n`。
2. [[expr.prim.this#4]]：`this` 不得出现在静态成员函数或显式对象成员函数的声明里。改写得到的 `this` 也算，所以程序非良构。[[expr.prim.id.general#2]] 的注 2 直接点明了这一点。

这正是显式对象成员函数的设计：函数体内没有 `this`，也没有隐式的成员访问，一切都通过 `self`。`self.n += 1` 是合法的，把 `return n;` 改成 `return self.n;` 程序就良构。Clang 23 报告 invalid use of member 'n' in explicit object member function。

显式对象形参的其他限制都写在 [[dcl.fct#7]] 里：它只能是第一个形参，函数不能带 cv 限定符或引用限定符，不能声明为 `static` 或 `virtual`。

```cpp error
struct S {
  void a(this S&) const;     // error: 不能带 cv 限定符
  virtual void b(this S&);   // error: 不能是 virtual
  static void c(this S&);    // error: 不能是 static
};
```

背景见 [[papers/deducing-this]]。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

{{c++23}} 给定下面的类和 `S s;`，哪一段代码放进函数体后是良构的？

```cpp
struct S {
  int v = 7;
  int get(this const S& s) { return s.v; }
  int via_this() const;
};
```

- A. `int (S::*p)() const = &S::get;`
- B. `auto p = &S::get; int r = (s.*p)();`
- C. `int (*p)(const S&) = &S::get; int r = p(s);`
- D. 在 `S::via_this` 的定义里写 `auto p = &get; return p(*this);`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

[[expr.unary.op#3]] 把取地址分成两种情况。¶3.1 说，对非静态成员 `m` 的 *qualified-id* 取地址，得到"指向 `C` 的成员的指针"，但显式对象成员函数被明确排除在外。于是它落入 ¶3.2：结果是普通的"指向 `T` 的指针"，`T` 是函数类型 `int(const S&)`。

- C 正确：`&S::get` 的类型就是 `int(*)(const S&)`，对象作为第一个实参传入。
- A 错：类型不匹配，成员函数指针要求函数没有显式对象形参。
- B 错：`p` 不是指向成员的指针，而 `.*` 的右操作数必须是"指向 `T` 的成员的指针"（[[expr.mptr.oper#2]]）。Clang 报告 right hand operand to .* has non-pointer-to-member type。
- D 错：¶3.2 最后一句要求，取显式对象成员函数的地址时，操作数必须是 *qualified-id* 或 *splice-expression*。只写 `&get` 不行，要写 `&S::get`。这与隐式对象成员函数一致，后者只有写成 `&S::f` 才形成成员指针（[[expr.unary.op#4]]）。

从外部看，显式对象成员函数仍是非静态成员函数，用 `s.get()` 调用；从指针的角度看，它更像静态成员函数。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

{{c++23}} 判定整个程序。如果良构，写出输出。

```cpp run
#include <cstdio>

int main() {
  int i = 0;
  [[assume(++i == 1)]];
  std::printf("%d\n", i);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，输出 `0`。**

[[dcl.attr.assume#1]] 规定了三件事：

1. 假设的表达式不求值，所以 `++i` 不会发生，`i` 仍为 0。
2. 如果这个表达式在该处求值会得到 `true`，假设没有任何效果。`i` 此时为 0，`++i == 1` 会得到 `true`。
3. 只有在它会得到 `false` 时，执行这条语句才是运行期未定义行为。

所以这里既没有副作用，也没有 UB。草案自带的例子 `[[assume(++y == 43)]]` 也注明 `y` 不会递增。¶2 的注 1 补充说，这个表达式仍是潜在求值的，其中用到的变量照样算 odr-use。

Clang 23 给出警告 assumption is ignored because it contains (potential) side-effects，`-O0` 和 `-O2` 下都输出 0。

只要把初值改成 1，假设在该处为假，程序就有未定义行为：

```cpp ub
int f() {
  int i = 1;
  [[assume(++i == 1)]];   // UB: 若求值会得到 false
  return i;
}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++23}} 判定下面的函数。

```cpp run
void f(bool b) {
  if (b) goto done;
  int n = 42;
  (void)n;
done:
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。标号放在末尾没有问题，问题在于跳过了 `n` 的初始化。**

先看 C++23 新增的部分。[[stmt.block#1]] 的文法是 `{ statement-seq(opt) label-seq(opt) }`，复合语句可以以若干标号结尾，后面不必再跟一条语句；[[stmt.label#1]] 也说标号可以出现在复合语句中的任何位置。C++20 中 `done:` 后面必须写一个 `;`。

再看跳转。[[stmt.dcl#2]] 规定：控制从 P 转移到 Q 时，在 Q 处活跃（处于作用域内、已过声明点）而在 P 处不活跃的自动变量要按声明顺序初始化；除非这些变量都是空初始化（vacuous initialization），这次转移就不能是跳转。`done:` 位于 `n` 的作用域内、声明之后，所以 `n` 在 Q 处活跃，在 `goto` 处不活跃。`int n = 42;` 有初始化器，不是空初始化（空初始化的定义见 [[basic.life#2]]：默认初始化且没有其他初始化），`goto` 非良构。Clang 报告 cannot jump from this goto statement to its label。

去掉初始化器就良构了，即使 C++26 中 `n` 的值是错误值（见第 14 题）：

```cpp run ok
void f(bool b) {
  if (b) goto done;
  int n;
  (void)n;
done:
}
int main() { f(true); }
```

</details>
</div>

## 二、协程

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++20}} 判定整个程序。`task` 是一个满足协程要求的返回类型，`promise_type` 提供了 `return_void`。

```cpp
template<bool Early>
task work() {
  if constexpr (Early) {
    return task{{}};
  }
  co_return;
}

int main() { work<false>().run(); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

[[dcl.fct.def.coroutine#1]]：函数体中出现 `co_return`、`co_await` 或 `co_yield`，这个函数就是协程。`work` 有 `co_return`，所以无论 `Early` 取什么值，它都是协程。

[[stmt.return.coroutine#1]]：协程不得包含 `return` 语句。紧接着的注说明，`return` 是否位于被丢弃的语句（discarded statement）里，对这条规则无关紧要。所以 `work<false>` 里那个永远不会实例化的 `return` 分支照样让程序非良构。

容易误选良构，理由是被丢弃的分支不实例化。但一个函数是不是协程、有没有 `return` 语句，都按函数体的字面判断，不看 `if constexpr` 的条件。Clang 23 报告 return statement not allowed in coroutine; did you mean 'co_return'?

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

{{c++20}} 下面四个函数的函数体都只有 `co_return;`，`task` 满足协程要求。哪一个可以成为协程？

- A. `constexpr task a() { co_return; }`
- B. `task b(int, ...) { co_return; }`
- C. `struct C { C() { co_return; } };` 中的构造函数
- D. `auto d = []() -> task { co_return; };` 中闭包类型的函数调用运算符

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：D。**

逐个对照条文：

- A：[[dcl.constexpr#3]] 规定协程不是 constexpr 适用（constexpr-suitable）的，而非模板的 constexpr 函数必须是 constexpr 适用的。非良构。
- B：[[dcl.fct.def.coroutine#1]] 要求协程的形参列表不能以不属于形参声明的省略号结尾，也就是不能是 C 风格的变参函数。非良构。注意 `template<class... Args> task g(Args&&...)` 中的 `...` 是包展开，不受此限。
- C：[[class.ctor.general#6]]：构造函数不能是协程。析构函数同理（[[class.dtor#20]]），`main` 也不能是协程（[[basic.start.main#3]]）。
- D：lambda 的函数调用运算符是普通成员函数，没有任何限制。正确。

A 有一个细节：[[dcl.constexpr#3]] 只约束非模板的 constexpr 函数，字面上不禁止 constexpr 函数模板是协程，它的实例只是不能用于常量求值。Clang 23 对 `template<class T> constexpr task c(T) { co_return; }` 同样报错 'co_return' cannot be used in a constexpr function，比草案更严。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

{{c++20}} 判定整个程序。`task` 的 `initial_suspend` 返回 `std::suspend_always`，`run()` 调用 `resume()`，析构函数销毁协程。

```cpp
#include <cstdio>
#include <string>
#include <string_view>

task greet(std::string_view name) {
  std::printf("hello, %.*s\n", int(name.size()), name.data());
  co_return;
}

int main() {
  task t = greet(std::string(40, 'x'));
  t.run();
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为。**

形参按值传递，看起来是安全的，但被复制进协程帧的只是 `string_view` 本身。

1. [[dcl.fct.def.coroutine#13]]：协程被调用时，在替换函数体的开头为每个形参创建一个副本。非引用形参的副本从原形参直接初始化（¶13.2），引用形参的副本仍是绑定到同一对象的引用（¶13.1）。`name` 的副本是一个 `string_view`，指向调用者那个临时 `std::string` 的缓冲区。
2. 协程在初始挂起点挂起，控制回到 `main`。临时 `std::string` 在完整表达式 `task t = greet(...)` 结束时销毁（[[class.temporary#4]]），缓冲区随之释放。
3. `t.run()` 恢复协程，`name.data()` 指向的存储已经结束了存储期。经由在该求值中无效的指针值做间接访问是未定义行为（[[basic.compound#6]] 的 ¶6.1）。

¶13 的注 3 就是这个提醒：如果协程有引用形参，在被引用的实体生命周期结束后恢复协程，很可能导致未定义行为。`string_view`、`span` 这类按值传递的视图类型有同样的问题，只是不会被这条注直接点名。

本机用 `-fsanitize=address` 运行，ASan 报告 heap-use-after-free。把形参改成 `std::string name`，副本拥有自己的缓冲区，程序正常输出。

```cpp ok
task greet(std::string name) {   // 副本拥有数据
  std::printf("hello, %s\n", name.c_str());
  co_return;
}
```

更多悬垂的场景见 [[topics/dangling-references]] 和 [[topics/coroutines]]。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

{{c++23}} 下面两个成员协程都在临时对象上调用，结果立即保存、稍后恢复（`task` 同上题，初始挂起）。分别判断 `a.run()` 和 `b.run()` 是否有未定义行为，并用协程形参复制的规则解释差别。

```cpp
struct Widget {
  std::string name = std::string(40, 'w');
  task show() { std::printf("%s\n", name.c_str()); co_return; }
  task show_copy(this Widget self) { std::printf("%s\n", self.name.c_str()); co_return; }
};

int main() {
  task a = Widget{}.show_copy();
  a.run();
  task b = Widget{}.show();
  b.run();
}
```

<details class="quiz-key" markdown="1"><summary>答案要点</summary>

**答案要点：`a.run()` 良构且行为明确；`b.run()` 是未定义行为。**

1. `show` 是隐式对象成员函数。按 [[dcl.fct.def.coroutine#4]]，它的 q1 是指代 `*this` 的左值，不是一个被复制的形参。[[dcl.fct.def.coroutine#13]] 只为函数形参创建副本，隐式对象形参不属于函数形参（它甚至不在形参类型列表里），所以协程帧里保存的只是 `this` 指针的值。
2. 临时 `Widget` 在 `task b = Widget{}.show();` 这个完整表达式结束时销毁（[[class.temporary#4]]）。恢复后访问 `name` 就是访问生命周期已结束的对象，未定义行为。
3. `show_copy` 的对象形参是一个写出来的按值形参 `Widget self`。它是普通的函数形参，适用 ¶13.2：协程帧中有一个从 `self` 直接初始化（移动构造）的副本，函数体中的 `self` 指的是这个副本（[[expr.prim.id.unqual#5]]）。临时对象销毁不影响副本，`a.run()` 正常输出。
4. 如果写成 `this Widget& self` 或 `this const Widget& self`，副本又只是引用（¶13.1），与 `show` 一样悬垂。

本机 ASan 对 `b.run()` 报告 stack-use-after-scope，单独运行 `a` 的部分正常输出 40 个 `w`。注意 ASan 中止时，标准输出缓冲区里 `a` 的输出可能来不及刷新。

这说明显式对象形参不只用于推导 `Self`：按值的对象形参让协程能拥有它的对象。

</details>
</div>

## 三、比较、consteval 与模块

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++20}} 判定下面的类定义。

```cpp run
struct P {
  int x, y;
  bool operator==(P) const = default;
};
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

[[class.compare.default#1]] 的 ¶1.3 要求默认比较运算符函数有两个类型都是 `const C&` 的形参，或者两个类型都是 `C` 的形参，并且把隐式对象形参（如果有）算作第一个形参。

`const` 成员函数的隐式对象形参类型是 `const P&`（[[over.match.funcs.general#4]]），第二个形参却是 `P`。两者不同，不满足 ¶1.3。Clang 23 报告 invalid parameter type for defaulted equality comparison operator; found 'P', expected 'const P &'。

改法有两种：成员版本写成 `bool operator==(const P&) const = default;`；或者改成友元 `friend bool operator==(P, P) = default;`，两个形参都是 `P`，这时按值传递是允许的。反过来，漏掉 `const` 的 `bool operator==(const P&) = default;` 也非良构，因为隐式对象形参变成了 `P&`。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

{{c++20}} 下面四个函数中，哪些非良构？

```cpp
#include <compare>

struct Ver {
  int major, minor;
  auto operator<=>(const Ver&) const = default;
  bool operator==(int m) const { return major == m; }
};

bool lt(Ver a, Ver b) { return a < b; }
bool eq(Ver a, Ver b) { return a == b; }
bool ne(Ver a, Ver b) { return a != b; }
bool eqi(Ver a) { return a == 1 && 1 == a; }
```

- A. 只有 `eq`
- B. `eq` 和 `ne`
- C. `eq`、`ne` 和 `eqi`
- D. 全部良构

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B。**

1. [[class.compare.default#4]]：只有当类的成员说明中没有显式声明任何名为 `operator==` 的成员或友元时，才会为默认的 `operator<=>` 隐式声明一个默认的 `operator==`。`Ver` 声明了 `operator==(int)`，所以不会生成 `operator==(const Ver&)`。
2. `a == b`：`==` 从来不会改写成 `<=>`。候选只有 `operator==(int)` 及其颠倒形式，`Ver` 转换不到 `int`，都不可行。非良构。
3. `a != b`：按 [[over.match.oper#3]] 的 ¶3.4.3，`!=` 的改写候选来自 `x == y` 的候选，同样只有 `operator==(int)`，不可行。非良构。
4. `a < b`：关系运算符的改写候选包括 `x <=> y`（¶3.4.1），默认的 `<=>` 可行，良构。
5. `eqi`：`a == 1` 直接调用成员；`1 == a` 使用颠倒的合成候选（¶3.4.4），也可行。良构。

Clang 23 对 `eq` 和 `ne` 报告 invalid operands to binary expression ('Ver' and 'Ver')。补上 `bool operator==(const Ver&) const = default;` 就全部良构。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++20}} 判定整个程序（按标准判定，不考虑编译器扩展）。

```cpp run
struct Id {
  int v;
  int operator==(const Id& o) const { return v == o.v; }
};

int main() {
  Id a{1}, b{2};
  return a != b;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。Clang 只给出警告。**

`Id` 没有 `operator!=`。按 [[over.match.oper#3]] 的 ¶3.4.3，`a != b` 的改写候选包括 `a == b` 的非改写候选，于是 `Id::operator==` 被选中。

[[over.match.oper#10]]：如果重载决议选中了改写的 `operator==` 候选，它的返回类型必须是 cv `bool`，然后 `x != y` 才被解释为 `!(x == y)`。这里返回 `int`，违反了这条"shall"，程序非良构。

为什么要这样规定？改写把结果交给内建的 `!`，标准不想让 `!` 作用于任意类型、再经过用户定义的转换。直接写 `a == b` 不涉及改写，返回 `int` 没有问题。

Clang 23 只给出 `-Wrewrite-not-bool` 警告：ISO C++20 requires return type of selected 'operator==' function for rewritten '!=' comparison to be 'bool', not 'int'，仍然编译通过。这是兼容旧代码的扩展。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++23}} 判定整个程序。

```cpp run
consteval int sq(int x) { return x * x; }

constexpr int area(int side) {
  if !consteval {
    return side * side;
  }
  return sq(side);
}

int main() {
  static_assert(area(4) == 16);
  int n = 5;
  return area(n);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`return sq(side);` 不在立即函数语境中。**

直觉上，`return sq(side);` 只会在编译期执行，因为运行期已经从 `if !consteval` 分支返回了。但规则看的是语法位置，不是控制流。

1. [[stmt.if#6]]：`if ! consteval { A }` 本身不是 consteval if 语句，它等价于 `if consteval { } else { A }`。
2. [[expr.const.imm#1]]：只有 consteval if 语句的第一个子语句（`if consteval` 后面那个复合语句）里的表达式才处于立即函数语境（¶1.3）。`return sq(side);` 在 `if` 语句之外，不满足；`area` 也不是立即函数，¶1.1 不满足。
3. 所以 `sq(side)` 是立即调用（immediate invocation）。`side` 是函数形参，它不是常量表达式，按 [[expr.const.imm#2]] 的 ¶2.2 是一个立即升级（immediate-escalating）表达式。
4. [[expr.const.imm#3]] 最后一句：立即升级表达式只能出现在立即升级函数中。`area` 是非模板的、用户写的 constexpr 函数，不属于 ¶3 列出的三类，程序非良构。

Clang 23 报告 call to consteval function 'sq' is not a constant expression。把 `sq(side)` 放进 else 分支就良构了，因为 `if !consteval { A } else { B }` 等价于 `if consteval { B } else { A }`：

```cpp run ok
consteval int sq(int x) { return x * x; }
constexpr int area(int side) {
  if !consteval {
    return side * side;
  } else {
    return sq(side);      // 位于 consteval if 的第一个子语句中
  }
}
int main() { static_assert(area(4) == 16); int n = 5; return area(n); }
```

如果 `area` 是函数模板，它的实例属于立即升级函数（¶3.3），会被升级为立即函数（¶4.2），错误转移到 `area(n)` 这个调用上：它成了不是常量表达式的立即调用。Clang 对这种写法报告 call to immediate function 'area<int>' is not a constant expression。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++20}} 判定下面这个模块接口单元。

```cpp
export module geom;

namespace {
  int scale(int x) { return 2 * x; }
}

inline int area(int w, int h) { return scale(w) * h; }

export int volume(int w, int h, int d) { return area(w, h) * d; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`area` 的定义暴露了 TU 局部实体 `scale`。Clang 只给出警告。**

1. 无名命名空间具有内部链接，其中声明的 `scale` 也是内部链接（[[basic.link#4]]）。具有内部链接名字的函数是 TU 局部（TU-local）实体（[[basic.link#15]] 的 ¶15.1.1）。
2. [[basic.link#14]]：如果一个声明指名了 TU 局部实体，它就是一个暴露（exposure）。计算时忽略非 inline 函数的函数体（¶14.1），但 inline 函数的函数体不忽略。`area` 是 inline 函数，函数体指名了 `scale`，所以 `area` 的定义是暴露。
3. `area` 没有导出，但它在模块的接口单元里，具有模块链接，不是 TU 局部的。[[basic.link#17]]：模块接口单元中非 TU 局部实体的声明如果是暴露，程序非良构。

为什么？inline 函数的定义要在导入它的翻译单元里可用，而那里无法引用另一个翻译单元的内部链接函数。容易误以为只有 `export` 的声明才受检查，但这条规则管的是接口单元中所有非 TU 局部的实体。

去掉 `inline`，函数体在计算暴露时被忽略，程序良构；`volume` 的函数体同理。Clang 23 对上面的代码只给出 `-WTU-local-entity-exposure` 警告 TU local entity 'scale' is exposed，去掉 `inline` 后加 `-Werror` 也能编译通过。

</details>
</div>

## 四、C++26：值、名字、包与常量求值

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

{{c++26}} 下面四个函数互相独立，各自只调用一次。哪一个有未定义行为（不是错误行为）？

```cpp
int a() { int x; int y = x; return y; }

unsigned char b() {
  unsigned char* p = new unsigned char;
  unsigned char c = *p;
  delete p;
  return 0;
}

int c() { int* q = new int; int d = *q; delete q; return d; }

int d() { unsigned char e; int f = e; return f; }
```

- A. `a`
- B. `b`
- C. `c`
- D. `d`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

[[basic.indet#1]] 按存储期区分初始值：动态存储期的对象，以及带 `[[indeterminate]]` 的变量，字节是不确定值（indeterminate value）；其余自动存储期的对象，字节是错误值（erroneous value），由实现选定，与程序状态无关。

[[basic.indet#2]] 再规定：一次求值产生不确定值是未定义行为，产生错误值是错误行为（erroneous behavior），结果就是那个错误值。无符号窄字符类型和 `std::byte` 有几个例外。

- `a`：`x` 是自动变量，值是错误值，`int y = x;` 是错误行为 {{erroneous}}。
- `b`：`*p` 是不确定值，但它是 `unsigned char`，用来初始化 `unsigned char` 对象属于 ¶2.3 的例外：`c` 也得到不确定值，没有 UB。
- `c`：`*q` 是动态存储期的 `int`，值不确定，读取它是未定义行为 {{ub}}。
- `d`：`e` 的值是错误值。把它转换成 `int` 不在例外之列，产生错误值，是错误行为。草案的例子 `int e = d;` 标的也是 erroneous behavior。

C++26 并没有让所有未初始化读取都变成错误行为：堆上的对象和 `[[indeterminate]]` 变量仍然是 UB。这也是 `[[indeterminate]]` 的用途，它换回旧的语义，同时也换回旧的风险（[[dcl.attr.indet#1]]）。

本机 Clang 23 不认识 `[[indeterminate]]`（unknown attribute 警告），对 `a` 和 `d` 给出 `-Wuninitialized` 警告；ASan 和 UBSan 都不报告 `c`，UB 不保证可以观察到。详见 [[papers/erroneous-behaviour]]。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

{{c++26}} 下面哪一个声明非良构？

- A. `struct S { int _; int _; };`
- B. `void f() { auto [_, _] = std::pair{1, 2}; }`
- C. `void f(int _, int _) {}`
- D. `void f() { static int _; int _; }`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

[[basic.scope.scope#6]]：同一作用域中两个相互潜在冲突的声明 A 在前、B 在后，程序非良构，除非 B 是与名字无关的声明（name-independent declaration）。[[basic.scope.scope#5]] 列出了哪些名为 `_` 的声明与名字无关：

- ¶5.1：自动存储期的变量，但函数形参除外；
- ¶5.2：不带存储类说明符、不在命名空间作用域的结构化绑定；
- ¶5.3：结果绑定（契约的 `post(r: …)`）；
- ¶5.4：*init-capture* 引入的变量；
- ¶5.5：非静态数据成员（匿名联合的成员除外）。

逐项看：

- A：非静态数据成员适用 ¶5.5，良构。只是此后 `s._` 会有歧义。
- B：结构化绑定适用 ¶5.2，良构。
- C：函数形参被 ¶5.1 明确排除，第二个 `_` 与第一个冲突，非良构。Clang 报告 redefinition of parameter '_'。
- D：容易误选。规则只要求后一个声明 B 与名字无关。这里 A 是 `static int _`（静态存储期，不是与名字无关的声明），B 是自动变量 `int _`，与名字无关，所以良构。顺序反过来就非良构，草案的例子 `int _; static int _;` 标的就是 error。

声明可以重复，使用却不行。第二个 `_` 引入后再写 `_`，名字查找会找到两个都不是函数的声明，结果有歧义（[[basic.lookup.general#1]]，¶6 的注 3）。第 25 题会用到这一点。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++26}} 判定整个程序。

```cpp run
template<class... T>
auto first(T...[0] x) { return x; }

int main() {
  return first(42);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`first(42)` 没有可行函数。**

1. `T...[0]` 是包索引说明符（[[dcl.type.pack.index]]）。按 [[temp.deduct.type#5]] 的 ¶5.2，包索引是非推导语境，所以实参 `42` 不能用来推导 `T`。
2. `T` 只出现在非推导语境中，又没有显式指定。[[temp.deduct.type#4]] 说这时推导失败；就算按 [[temp.arg.explicit#4]] 的注把尾随的包推导为空，接下来替换 `T...[0]` 时，下标 0 也不满足 [[dcl.type.pack.index#2]] 的 0 ≤ V < `sizeof...(T)`，同样失败。
3. 唯一的候选不可行，调用非良构。

Clang 23 报告 no matching function for call to 'first'，附注 substitution failure [with T = <>]: invalid index 0 for pack 'T' of size 0。

显式给出模板实参就良构：

```cpp run ok
template<class... T>
auto first(T...[0] x) { return x; }
int main() { return first<int>(42); }
```

提案为什么不让包索引参与推导，以及无名形参 `T...[n]` 的含义在 C++26 中怎样改变，见 [[papers/pack-indexing]]。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++26}} 判定整个程序。

```cpp run
#include <tuple>

int sum3() {
  auto [...xs] = std::tuple{1, 2, 3};
  return (xs + ...);
}

int main() { return sum3(); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，结构化绑定包只能出现在模板化实体中。**

`...xs` 是一个结构化绑定包（[[temp.variadic#4]]），它本身没有问题，结构化绑定大小是 3，包里有三个结构化绑定（[[dcl.struct.bind#2]]）。

问题在 [[dcl.pre#7]]：如果结构化绑定声明含有带省略号的 *sb-identifier*，它必须声明一个模板化实体（templated entity）。按 [[temp.pre#8]]，模板化实体包括模板、在模板化实体中定义的实体、在展开语句中定义的实体等。`sum3` 是普通函数，其中的变量不是模板化实体，所以非良构。Clang 23 报告 pack declaration outside of template。

这个限制让编译器总是在模板实例化的框架里处理包。放进泛型 lambda 就良构，lambda 的函数调用运算符是模板：

```cpp run ok
#include <tuple>
int sum3() {
  auto f = [](auto t) { auto [...xs] = t; return (xs + ...); };
  return f(std::tuple{1, 2, 3});
}
int main() { return sum3(); }   // 返回 6
```

按 ¶8.2，`template for` 的循环体里定义的实体也是模板化的，所以在普通函数里的展开语句中写结构化绑定包同样合法。本机 Clang 23 编译这种写法时崩溃，所以这里没有给出代码。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

{{c++26}} 程序输出什么？

```cpp run
#include <cstdio>
#include <tuple>

struct R {
  int code, value;
  explicit operator bool() const { std::puts("bool"); return code == 0; }
};
template<std::size_t I> int get(const R& r) {
  std::puts("get");
  return I == 0 ? r.code : r.value;
}
template<> struct std::tuple_size<R> : std::integral_constant<std::size_t, 2> {};
template<std::size_t I> struct std::tuple_element<I, R> { using type = int; };

R parse() { return {0, 7}; }

int main() {
  if (auto [code, value] = parse())
    std::printf("%d %d\n", code, value);
}
```

- A. `bool`、`get`、`get`、`0 7`（各占一行）
- B. `get`、`get`、`bool`、`0 7`
- C. `get`、`get`、`0 7`，不调用 `operator bool`
- D. 编译失败：结构化绑定不能用作条件

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：A。**

C++26 允许结构化绑定声明出现在条件里（[[stmt.pre]] 的 *condition* 文法）。

1. 测试的是哪个值？[[stmt.pre#6]]：非表达式条件的值，是判定变量（decision variable）按语境转换为 `bool` 的结果。[[dcl.struct.bind#4]]：结构化绑定声明作条件时，判定变量是那个引入的无名变量 *e*，也就是整个 `R` 对象，不是 `code` 或 `value`。所以调用的是 `R::operator bool`，`explicit` 不妨碍语境转换。
2. 先后顺序？`R` 特化了 `tuple_size`，按类元组方式绑定。[[dcl.struct.bind#7]] 规定：*e* 的初始化以及把 *e* 作为判定变量所做的任何转换，都按顺序先于任何 ri 的初始化，也就是先于对 `get` 的调用。所以先输出 `bool`，再输出两次 `get`。

B 是把结构化绑定看成先拆开、再判断的直觉。C 误以为判定的是第一个绑定。这个顺序是有意的：如果转换结果是假，往往说明对象处于不能拆解的状态（例如表示失败的结果类型），不应该再调用 `get`。

本机 Clang 23 运行输出与 A 相同。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++26}} 判定整个程序。

```cpp run
int legacy(int) = delete("use modern(int) instead");
long legacy(long);

constexpr auto n = sizeof(legacy(0L));
constexpr auto m = sizeof(legacy(0));

int main() { return n + m; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`sizeof(legacy(0))` 引用了被删除的函数。**

1. `legacy(0L)` 的重载决议选中 `legacy(long)`，没有问题。
2. `legacy(0)` 选中精确匹配的 `legacy(int)`。被删除的函数照样参与重载决议，删除只在选中之后才检查。
3. [[dcl.fct.def.delete#2]]：除了声明它、或作为反射表达式 `^^` 的操作数之外，任何隐式或显式指代被删除函数的构造都非良构。注 1 说明，这也适用于不是潜在求值的表达式。`sizeof` 的操作数不求值，但仍然非良构。

C++26 新增的是括号里的字符串：它是一个 *unevaluated-string*，¶2 的"推荐做法"建议诊断信息包含这段文字。Clang 23 报告 call to deleted function 'legacy': use modern(int) instead。

另一个限制：被删除的定义必须是函数的第一个声明（[[dcl.fct.def.delete#4]]），带不带理由都一样。

```cpp error
void f();
void f() = delete("no");   // error: deleted definition must be first declaration
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

{{c++26}} 判定整个程序（按标准判定，不考虑编译器的默认诊断设置）。

```cpp run
#include <cstddef>

struct Msg {
  std::size_t size() const;
  const char* data() const;
};

static_assert(sizeof(long) >= sizeof(int), Msg{});

int main() {}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构。**

C++26 允许 `static_assert` 的第二个操作数是一个表达式，而不只是字符串字面量。

1. [[dcl.pre#12]]：消息不是字符串字面量时，必须是一个表达式 M，满足 `M.size()` 能隐式转换为 `std::size_t`，`M.data()` 能隐式转换为"指向 `const char` 的指针"。这只是对类型的要求，`Msg` 满足：两个成员函数声明了，返回类型对，有没有定义、是不是 constexpr 都不影响。
2. [[dcl.pre#13]]：条件为真时，这个声明没有效果，消息是一个不求值操作数。只有断言失败时，¶13.2 才要求 `M.size()` 是常量表达式、`M.data()` 是核心常量表达式。
3. 按 [[basic.fundamental#1]]，`long int` 提供的存储至少与 `int` 一样多，所以 `sizeof(long) >= sizeof(int)` 必为真，消息不会被求值，也不必是常量表达式。

Clang 23 按 `-Winvalid-static-assert-message` 报告 the message in this static assertion is not a constant expression。这个诊断是默认作为错误的警告，加 `-Wno-invalid-static-assert-message` 后编译通过。Clang 在条件为真时也检查消息，比草案更严。

断言失败时，消息必须能在编译期求出；这时 `Msg{}` 不满足 ¶13.2，Clang 报告 the message in a static assertion must be produced by a constant expression，程序当然也非良构。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

{{c++26}} 下面四个函数中，哪一个的调用能用作常量表达式（例如 `constexpr int r = a();`）？

```cpp
#include <memory>
#include <new>

constexpr int a() {
  std::allocator<int> al;
  int* p = al.allocate(1);
  int* q = ::new (p) int(42);
  int r = *q;
  al.deallocate(p, 1);
  return r;
}

constexpr int b() {
  std::allocator<double> al;
  double* p = al.allocate(1);
  int* q = ::new (static_cast<void*>(p)) int(42);
  int r = *q;
  al.deallocate(p, 1);
  return r;
}

int g = 0;
constexpr int c() { return *::new (&g) int(42); }

constexpr int d() {
  std::allocator<int> al;
  int* p = al.allocate(1);
  return *::new (p) int(42);
}
```

- A. `a`
- B. `b`
- C. `c`
- D. `d`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：A。**

C++26 允许在常量求值中使用不分配内存的 placement new。条件写在 [[expr.const.core#2]] 的 ¶2.20.2：设被求值的表达式为 E，分配类型为 T，

- ¶2.20.2.1：placement 实参指向的对象能被新对象透明替换（[[basic.life#9]]）；
- ¶2.20.2.2：placement 实参指向的存储，其存储期在 E 的求值中开始。

逐个看：

- `a`：`allocate(1)` 返回一个 `int` 数组首元素的指针（[[allocator.members#3]]），元素的生命周期尚未开始。在它上面创建 `int`，按 [[intro.object#2]] 新对象成为这个数组元素，可以透明替换原元素。存储在 E 中分配，也在 E 中释放（¶2.22、¶2.23）。是常量表达式。
- `b`：存储是为 `double` 分配的，新对象是 `int`。类型不同，它不会成为数组元素（[[intro.object#2]] 的 ¶2.4），与原来的 `double` 元素不是对应的直接子对象；原元素又不是完整对象，[[basic.life#9]] 的两种情形都不满足，不能透明替换，违反 ¶2.20.2.1。Clang 23 附注 placement new would change type of storage from 'double' to 'int'。
- `c`：`g` 的存储期在程序开始时就开始了，不在 E 内，违反 ¶2.20.2.2。Clang 23 附注 a constant expression cannot modify an object that is visible outside that expression。
- `d`：分配的存储没有在 E 内释放，违反 ¶2.22。Clang 23 附注 allocation performed here was not deallocated。

本机 Clang 23 已经实现 constexpr placement new，以上四个判断都和它一致。同为 C++26 新增的常量求值中抛出并捕获异常，Clang 23 尚未实现，见 [[papers/constexpr-exceptions]]。

</details>
</div>

## 五、C++26：契约与静态反射

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++26}} 判定下面两个声明。

```cpp
int add_nonneg(int x, int delta)
  pre(delta >= 0)
  post(r : r >= x);

int add_nonneg(int x, int delta) { return x + delta; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，后置条件使用了非 `const` 的按值形参 `x`。**

1. 第二个声明不带契约说明符，这是允许的（[[dcl.contract.func#4]]：非首次声明可以不写，或者写完全相同的一套）。
2. [[dcl.contract.func#7]]：如果函数 *f* 的后置条件谓词 odr-use 了 *f* 的一个非引用形参，这个形参以及所有声明中对应的形参都必须是 `const` 类型。`post(r : r >= x)` odr-use 了 `x`，而 `x` 在两个声明里都是 `int`，非良构。
3. `pre(delta >= 0)` 用到 `delta` 没有问题，¶7 只约束后置条件。

为什么？后置条件在函数返回时求值，看到的是形参当时的值。如果函数体修改了 `x`，`r >= x` 比较的就不是调用者传进来的值，后置条件会悄悄地失去意义。要求 `const` 就排除了这种可能。注 4 强调，这个要求也适用于没有写后置条件的那些声明，所以两处都要改：

```cpp
int add_nonneg(const int x, int delta)
  pre(delta >= 0)
  post(r : r >= x);

int add_nonneg(const int x, int delta) { return x + delta; }
```

截至写作时，本机 Clang 23 尚未实现契约，遇到 `pre(` 报告 expected function body after function declarator，所以本题与本节其余契约代码都未经编译，判定依据草案条文。设计背景见 [[papers/contracts]]。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

{{c++26}} 判定整个程序。

```cpp
#include <meta>

[:^^int:] g = 1;

int main() {
  [:^^int:] n = g;
  return n;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构，`main` 中的 `[:^^int:] n = g;` 不能当作声明。**

`^^int` 是 `int` 的反射，`[: … :]` 是拼接（splice）。问题在于拼接什么时候被当成类型。

1. [[dcl.type.splice#1]]：没有前置 `typename` 的拼接说明符，只在仅类型语境（type-only context）中才被解释为 *splice-type-specifier*。
2. [[temp.res.general#4]] 列出了仅类型语境。¶4.4.1 包括命名空间作用域中 *simple-declaration* 的 *decl-specifier*，¶4 最后一句又规定拼接说明符比照同一位置上的限定名处理，所以第一行 `[:^^int:] g = 1;` 是声明，良构。块作用域中的简单声明不在列表里。
3. 所以 `main` 中的 `[:^^int:]` 只能是拼接表达式。它指代一个类型，而 [[expr.prim.splice#2]] 的 ¶2.7 规定，拼接的不是函数、对象、变量、值等时，表达式非良构。

这与 `T::type` 需要 `typename` 是同一个道理：在函数体内，编译器无法事先知道一个依赖于常量值的构造是类型还是表达式，所以默认按表达式解析。改成 `typename [:^^int:] n = g;` 就良构，草案中 `typename [:^^S::type:] *var;` 的例子也是这样写的。

截至写作时，本机 Clang 23 尚未实现反射：libc++ 没有 `<meta>` 头文件，遇到 `^^` 会按 Clang 的 block 扩展解析，所以本题未经编译。详见 [[papers/reflection]]。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

{{c++26}} 下面的程序调用 `f(-1)`，前置条件不成立。对 ignore、observe、enforce、quick-enforce 四种求值语义，分别说明程序可能怎样执行、`checks` 最后可能是几，并说明语义由谁决定。

```cpp
#include <cstdio>

int checks = 0;
bool audit(int v) { ++checks; return v > 0; }

int f(int v) pre(audit(v)) { return v; }

int main() {
  f(-1);
  std::printf("%d\n", checks);
}
```

<details class="quiz-key" markdown="1"><summary>答案要点</summary>

**答案要点：语义由实现决定；ignore 下输出 0；observe 下调用违约处理函数后继续执行，`checks` 可能是 0、1 或更大；enforce 和 quick-enforce 下程序终止，不会输出。**

先确认程序良构。谓词中直接命名的 `v` 按 [[expr.prim.id.unqual#7]] 被视为 `const int`，但 `audit(v)` 只是按值传递，不修改它；`audit` 修改全局变量不受限制，常量化只作用于谓词里直接出现的名字。

1. 选哪种语义？[[basic.contract.eval#2]]：每次求值使用哪种语义由实现定义，同一断言的不同求值可以不同。¶3 建议实现提供两种编译选项，分别让所有求值都用 ignore 和都用 enforce，默认用 enforce。
2. ignore：[[basic.contract.eval#4]]，求值没有效果，谓词不求值，`audit` 不被调用。正常返回，输出 `0`。
3. 检查语义的共同点：[[basic.contract.eval#5]] 说，谓词是否真的求值是未指明的，实现可以用一种没有副作用、结果相同的方式确定它的值。另外，按 [[expr.call#8]]，前置条件"按顺序求值"，而 [[basic.contract.eval#18]] 允许每个断言重复实现定义的次数。所以在检查语义下，`audit` 可能被调用 0 次、1 次或多次。
4. observe：谓词为假，发生契约违反（¶7.1），调用违约处理函数（¶11）。处理函数正常返回后继续执行（¶14 的注 10），`f` 返回 −1，输出 `checks` 的值，按第 3 点可能是 0、1 或更大。
5. enforce：同样调用违约处理函数。它正常返回后程序被契约终止（¶13），即调用 `std::terminate`、`std::abort` 或直接结束执行，具体哪一种由实现定义（¶9），不会输出。处理函数也可以抛出异常，这时效果如同 `f` 的函数体抛出该异常（¶17）。
6. quick-enforce：不调用违约处理函数，直接契约终止（¶10），不会输出。

所以，让谓词带副作用的程序是不可移植的：它的输出取决于实现选择的语义和求值次数。[[papers/contracts]] 讨论过的 `assert(++nIter < 6)` 改写成契约时必须调整，原因也在这里。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

{{c++26}} 综合题。逐行判定 #1、#2、#3，给出整个程序的判定；再说明如果把最后一行改成 `double s = pick(1);`（并修好其他问题），会发生什么。

```cpp run
#include <tuple>

template<class... Ts>
auto pick(Ts... xs) {
  auto [_, ...rest] = std::tuple{xs...};   // #1
  int _ = 0;                                // #2
  return rest...[0] + _;                    // #3
}

double r = pick(1, 2.5);
```

<details class="quiz-key" markdown="1"><summary>答案要点</summary>

**答案要点：#1、#2 良构，#3 非良构，所以整个程序非良构。改成 `pick(1)` 后，`rest` 是空包，`rest...[0]` 下标越界，实例化失败。**

1. #1：结构化绑定声明带包 `...rest`，它位于函数模板中，是模板化实体，满足 [[dcl.pre#7]]（对比第 17 题）。第一个绑定名为 `_`，按 [[basic.scope.scope#5]] 的 ¶5.2 是与名字无关的声明。`pick(1, 2.5)` 时结构化绑定大小是 2，`_` 绑定 `1`，`rest` 含一个元素 `2.5`（[[dcl.struct.bind#2]]）。
2. #2：又声明一个自动变量 `_`，它与 #1 的 `_` 潜在冲突，但它自己是与名字无关的声明（¶5.1），按 [[basic.scope.scope#6]] 良构。
3. #3：`rest...[0]` 是包索引表达式，下标 0 小于 `sizeof...(rest)` 即 1，合法（[[expr.prim.pack.index#2]]）。问题在 `_`：此时作用域中有两个名为 `_` 的变量声明，名字查找找到的两个声明都不是函数，而且指代不同的实体，结果有歧义，非良构（[[basic.lookup.general#1]]；[[basic.scope.scope#6]] 的注 3）。`_` 不依赖模板形参，所以在模板定义时就能报错。Clang 23 报告 ambiguous reference to placeholder '_', which is defined multiple times。
4. 改成 `pick(1)` 并去掉 `+ _`：结构化绑定大小是 1，`_` 绑定 `1`，`rest` 是空包，这是允许的。但 `rest...[0]` 要求 0 < `sizeof...(rest)`，即 0 < 0，不满足 [[expr.prim.pack.index#2]]，`pick<int>` 的实例化非良构。这发生在函数体内而不是在替换函数类型时，所以是硬错误，不是 SFINAE。Clang 23 报告 invalid index 0 for pack 'rest' of size 0。

这道题说明 `_` 的设计取舍：可以随意声明多个不再使用的名字，但一旦声明了第二个，就不能再读其中任何一个。

</details>
</div>

## 考查条款一览

| 题号 | 考查点 | 条款 |
|---|---|---|
| 1 | 显式对象成员函数中的隐式成员访问 | [[expr.prim.id.general#2]]、[[expr.prim.this#4]]、[[dcl.fct#7]] |
| 2 | 显式对象成员函数的地址是普通函数指针 | [[expr.unary.op#3]]、[[expr.mptr.oper#2]] |
| 3 | `[[assume]]` 的表达式不求值 | [[dcl.attr.assume#1]] |
| 4 | 复合语句末尾的标号；跳过有初始化的声明 | [[stmt.block#1]]、[[stmt.dcl#2]]、[[basic.life#2]] |
| 5 | 被丢弃语句中的 `return` 也使协程非良构 | [[dcl.fct.def.coroutine#1]]、[[stmt.return.coroutine#1]] |
| 6 | 哪些函数不能是协程 | [[dcl.fct.def.coroutine#1]]、[[dcl.constexpr#3]]、[[class.ctor.general#6]] |
| 7 | 协程形参副本与按值传递的视图 | [[dcl.fct.def.coroutine#13]]、[[class.temporary#4]]、[[basic.compound#6]] |
| 8 | 隐式对象形参不被复制；按值的显式对象形参 | [[dcl.fct.def.coroutine#4]]、[[dcl.fct.def.coroutine#13]] |
| 9 | 默认比较运算符的形参类型 | [[class.compare.default#1]] |
| 10 | 用户声明的 `operator==` 抑制隐式的 `==` | [[class.compare.default#4]]、[[over.match.oper#3]] |
| 11 | 改写的 `!=` 要求 `operator==` 返回 `bool` | [[over.match.oper#3]]、[[over.match.oper#10]] |
| 12 | `if !consteval` 与立即函数语境 | [[stmt.if#6]]、[[expr.const.imm#1]]、[[expr.const.imm#3]] |
| 13 | 模块接口中 inline 函数暴露 TU 局部实体 | [[basic.link#14]]、[[basic.link#15]]、[[basic.link#17]] |
| 14 | 错误值与不确定值；无符号窄字符的例外 | [[basic.indet#1]]、[[basic.indet#2]] |
| 15 | 与名字无关的声明 | [[basic.scope.scope#5]]、[[basic.scope.scope#6]] |
| 16 | 包索引是非推导语境 | [[temp.deduct.type#5]]、[[dcl.type.pack.index#2]] |
| 17 | 结构化绑定包只能出现在模板化实体中 | [[dcl.pre#7]]、[[temp.pre#8]] |
| 18 | 结构化绑定作条件：判定变量与求值顺序 | [[stmt.pre#6]]、[[dcl.struct.bind#4]]、[[dcl.struct.bind#7]] |
| 19 | 带理由的删除；不求值语境也不能引用 | [[dcl.fct.def.delete#2]]、[[dcl.fct.def.delete#4]] |
| 20 | `static_assert` 消息在条件为真时不求值 | [[dcl.pre#12]]、[[dcl.pre#13]] |
| 21 | 常量求值中的 placement new | [[expr.const.core#2]]、[[basic.life#9]]、[[intro.object#2]] |
| 22 | 后置条件使用的按值形参必须是 `const` | [[dcl.contract.func#4]]、[[dcl.contract.func#7]] |
| 23 | 块作用域中的拼接默认是表达式 | [[dcl.type.splice#1]]、[[temp.res.general#4]]、[[expr.prim.splice#2]] |
| 24 | 契约的四种求值语义 | [[basic.contract.eval#2]]、[[basic.contract.eval#5]]、[[basic.contract.eval#18]] |
| 25 | `_`、结构化绑定包与包索引的综合 | [[basic.scope.scope#6]]、[[basic.lookup.general#1]]、[[expr.prim.pack.index#2]] |
