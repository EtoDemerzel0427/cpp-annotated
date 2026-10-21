---
title: 第二卷 · 初始化、值类别与引用
summary: 25 道题，考默认、值、零初始化的分叉，列表初始化与窄化，聚合规则在各版标准间的变化，复制初始化与直接初始化，引用绑定，值类别与 decltype，保证的复制消除，隐式移动，C++26 的错误行为和静态初始化。
status: done
order: 2
related: topics/initialization, topics/value-categories, topics/type-deduction, topics/special-members-and-elision, dcl.init, dcl.init.list, dcl.init.aggr, dcl.init.ref, basic.lval, dcl.type.decltype, class.copy.elision, basic.indet, basic.start.static
tags: 初始化, 列表初始化, 聚合, 引用绑定, 值类别, decltype, 复制消除, 错误行为, 考卷
updated: 2026-10-20
---

!!! tldr
    - 考查范围：[[dcl.init]] 的各种初始化形式，[[dcl.init.list]] 与窄化，[[dcl.init.aggr]]，[[dcl.init.ref]]，[[basic.lval]] 与 [[dcl.type.decltype]]，`auto` 推导，[[class.copy.elision]] 与隐式移动，[[basic.indet]] 的错误值，[[basic.start.static]]。
    - 对象生命周期与临时对象、名字查找与重载决议、模板、常量求值另有专卷，本卷只在判定需要时引用它们。
    - 共 25 题：判定题 15 道、单选题 7 道、简答题 3 道，难度大致递增。建议用时 90 分钟。
    - 判定题按整个程序中最重的一项作答；题目代码都已用 Clang 23（`-std=c++2c`）实测，编译器与草案不一致之处在解析里写明。

## 一、默认初始化、值初始化与零初始化

<div class="quiz" data-kind="verdict" data-answer="eb" markdown="1">

判定这个程序。

```cpp run
struct A { A() = default; int i; };
struct B { B(); int i; };
B::B() = default;

int main() {
  A a{};
  B b{};
  return a.i + b.i;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：错误行为。**

1. `A` 和 `B` 都有用户声明的构造函数，从 C++20 起都不是聚合（[[dcl.init.aggr#1.1]]）。空的花括号初始化一个有默认构造函数的类，做的是值初始化（[[dcl.init.list#3.5]]）。
2. 值初始化看选中的默认构造函数是不是用户提供的：不是，就先零初始化，再默认初始化（[[dcl.init#8.1]]）。一个函数在首次声明时没有写 `= default` 或 `= delete`，它就是用户提供的（[[dcl.fct.def.default#5]]）。`A()` 在类内默认化，不是用户提供的，所以 `a.i` 是 0。
3. `B()` 在类内只是声明，到类外才默认化，所以它是用户提供的。`b` 只做默认初始化，也就是调用 `B()`。`B()` 没有为 `i` 写成员初始化器，`i` 被默认初始化（[[class.base.init#9.3]]），对 `int` 来说什么也不做（[[dcl.init#6.4]]）。
4. `b` 是自动存储期的对象，没有被初始化的字节保持错误值（[[basic.indet#1.2]]）。`return` 里读取 `b.i` 产生错误值，行为是错误行为（[[basic.indet#2]]）。C++23 及以前，这里是未定义行为。

本机 Clang 23 还没有实现错误行为的语义，运行时返回一个栈上的残留值，具体数值随编译选项变化，没有诊断。

<div class="compare" markdown="1">

```cpp ok
struct B { B() = default; int i; };
int main() {
  B b{};
  return b.i;   // 0
}
```

```cpp eb
struct B { B(); int i; };
B::B() = default;
int main() {
  B b{};
  return b.i;   // 错误值
}
```

</div>

讲解见 [[topics/initialization]] 的"类外 `= default` 是用户提供的"一节。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定这个程序。`s` 具有静态存储期。

```cpp run
struct S {
  S() = default;
  int i;
};

const S s;

int main() { return s.i; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. `s` 没有初始化器，所以被默认初始化（[[dcl.init#11]]）。
2. 程序要求默认初始化一个 const 类型的对象时，这个类型必须是 const-default-constructible 的（[[dcl.init#7]]）。
3. 逐条检查 `S`：默认初始化调用的 `S()` 不是用户提供的，[[dcl.init#7.3]] 不满足；`S` 的成员 `i` 既没有默认成员初始化器，`int` 本身也不是 const-default-constructible 的，[[dcl.init#7.4.1]] 不满足。所以 `S` 不是 const-default-constructible 的，程序非良构。

容易误判为良构的理由是：`s` 有静态存储期，会先被零初始化，`s.i` 的值是确定的 0。但 [[dcl.init#7]] 约束的是默认初始化这个要求本身，不看存储期，也不看零初始化之后的结果。规则的用意是：一个 const 对象以后不能再赋值，如果构造过程什么都不初始化，它的值就只能来自零初始化或者干脆不确定，标准要求写代码的人明确表态。

Clang 的诊断是 `default initialization of an object of const type 'const S' without a user-provided default constructor`。

<div class="compare" markdown="1">

```cpp ok
struct S {
  S() = default;
  int i = 0;    // 有默认成员初始化器
};
const S s;
```

```cpp ok
struct S {
  S() = default;
  int i;
};
const S s{};    // 值初始化，不是默认初始化
```

</div>

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

`f` 里的四个对象中，哪一个的成员 `n` 不保证是 0？

```cpp run
struct M { M() { } };
struct S1 { M m; int n; };
struct S2 { M m; int n; S2() = default; };
struct S3 { M m; int n; S3(); };
S3::S3() = default;

void f() {
  S1 a{};               // A: a.n
  S2 b{};               // B: b.n
  S3* p = new S3();     // C: p->n
  thread_local S3 t;    // D: t.n
  delete p;
}
```

- A. `a.n`
- B. `b.n`
- C. `p->n`
- D. `t.n`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

- A：`S1` 是聚合，`{}` 做聚合初始化。`n` 没有被显式初始化，又没有默认成员初始化器，就从空的初始化列表复制初始化（[[dcl.init.aggr#6.2]]），得到 0。
- B：`S2` 有用户声明的构造函数，不是聚合，`b{}` 做值初始化（[[dcl.init.list#3.5]]）。`S2()` 在类内默认化，不是用户提供的，所以先零初始化（[[dcl.init#8.1]]）。成员 `m` 的构造函数是用户提供的，这让 `S2()` 变成非平凡的，但零初始化看的只是 `S2()` 本身是不是用户提供的，与是否平凡无关。
- C：`new S3()` 的 `()` 按直接初始化的规则解释（[[expr.new#24.2]]），即值初始化（[[dcl.init#15.4]]）。`S3()` 在类外默认化，是用户提供的，所以不做零初始化，只调用 `S3()`，`n` 没有被初始化。动态存储期对象的字节是不确定值（[[basic.indet#1.1]]），读取 `p->n` 是未定义行为。
- D：`t` 具有线程存储期，它不是常量初始化的，于是先被零初始化（[[basic.start.static#2]]），之后的动态初始化调用 `S3()`，不碰 `n`，`n` 仍是 0。

干扰项是 D：`thread_local S3 t;` 用的是默认初始化，看起来和 C 一样什么也不做。区别在于静态和线程存储期的对象在任何动态初始化之前一定先清零。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定这个程序。

```cpp run
struct Timer { };
struct Clock {
  Clock(Timer) { }
  int now() const { return 0; }
};

int main() {
  Clock c(Timer());
  return c.now();
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. `Clock c(Timer());` 既可以读成用函数式转换 `Timer()` 初始化对象 `c`，也可以读成声明一个函数 `c`，它的参数是一个没有名字、类型为"返回 `Timer` 的无参函数"的形参。凡是能被解释成声明的，都按声明处理（[[dcl.ambig.res#1]]）。
2. 函数类型的形参调整为指向函数的指针（[[dcl.fct#5]]），所以 `c` 的类型是 `Clock(Timer (*)())`。
3. `c.now()` 对一个函数做成员访问，非良构。Clang 先给出 `-Wvexing-parse` 警告，再报 `member reference base type 'Clock (Timer (*)())' is not a structure or union`。

只有第 1 步这一句话本身是良构的，它声明了一个函数；出错的是下一行。改法是让它不可能是声明：

<div class="compare" markdown="1">

```cpp ok
Clock c{Timer()};     // 列表初始化
Clock d((Timer()));   // 实参外多一层括号
Clock e = Timer();    // 复制初始化
```

```cpp error
Clock c(Timer());     // 函数声明
int n = c.now();      // error: c 是函数
```

</div>

</details>
</div>

## 二、列表初始化、窄化与聚合

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

下面四个命名空间作用域的声明，哪一个非良构？假设 `float` 是 IEEE 754 单精度类型。

```cpp run
const int big = 255;
constexpr long long p = 1LL << 40;

unsigned char c{big};   // A
float f{p};             // B
float g{0.1};           // C
bool b = {nullptr};     // D
```

- A. `unsigned char c{big};`
- B. `float f{p};`
- C. `float g{0.1};`
- D. `bool b = {nullptr};`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：D。**

- A：`int` 到 `unsigned char` 一般是窄化，但源是常量表达式，值 255 在提升后放得进目标类型，属于例外（[[dcl.init.list#7.4.2]]）。
- B：整数到浮点一般是窄化，但源是常量表达式，2⁴⁰ 能被 `float` 精确表示、转回去还是原值，属于例外（[[dcl.init.list#7.3]]）。换成 `(1LL << 53) + 1` 就放不下了，Clang 报 `constant expression evaluates to 9007199254740993 which cannot be narrowed to type 'float'`。
- C：`double` 到 `float` 是降低浮点转换等级的转换，但转换结果是常量表达式，值有限、没有溢出，就不算窄化（[[dcl.init.list#7.2]]）。0.1 不能被 `float` 精确表示也没关系，这条例外只要求不溢出。
- D：这里没有窄化。`= {nullptr}` 是复制列表初始化，单个元素，按复制初始化处理（[[dcl.init.list#3.9]]）。从 `std::nullptr_t` 到 `bool` 只有直接初始化才有特殊规则（[[dcl.init#15.8]]）；复制初始化走标准转换（[[dcl.init#15.9]]），而布尔转换的源类型里没有 `std::nullptr_t`（[[conv.bool#1]]）。所以非良构。

把 D 改成 `bool b{nullptr};` 就是良构的，`b` 为 `false`：直接列表初始化按直接初始化处理，正好落在 [[dcl.init#15.8]]。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

这个程序输出什么？（每次 `puts` 输出一行，这里按顺序列出各行。）

```cpp run
#include <cstdio>
#include <initializer_list>

struct X {
  X() { }
  X(const X&) { std::puts("copy"); }
  X(std::initializer_list<X>) { std::puts("list"); }
};

int main() {
  X a;
  X b{a};
  X c(a);
}
```

- A. `copy` `copy`
- B. `list` `copy`
- C. `copy` `list` `copy`
- D. `list` `list`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

1. `X b{a};`：`X` 不是聚合，所以 [[dcl.init.list#3.2]] 那条规则（用同类型的单个元素直接复制）不适用，走到 [[dcl.init.list#3.7]]，按 [[over.match.list#1]] 分两阶段选构造函数。第一阶段只看初始化列表构造函数，把整个 `{a}` 当作一个实参。`{a}` 能转换成 `std::initializer_list<X>`，第一阶段就成功了，复制构造函数根本不参与比较。
2. 构造 `std::initializer_list<X>` 时，实现生成一个 `const X[1]` 的后备数组，元素从 `a` 复制初始化（[[dcl.init.list#5]]），这里输出 `copy`；然后执行列表构造函数体，输出 `list`。
3. `X c(a);` 是直接初始化，不是列表初始化，按 [[over.match.ctor#1]] 在全部构造函数中选。`a` 不能转换成 `std::initializer_list<X>`，只有复制构造函数可行，输出 `copy`。

B 是最常见的错误答案：它记住了列表构造函数优先，却漏掉了后备数组的元素本身也要复制。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定这个程序。

```cpp run
#include <cstdio>
#include <string>
#include <vector>

int main() {
  std::vector<std::string> v{{"a", "b"}};
  std::printf("%zu\n", v.size());
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为。**

1. 外层 `{…}` 只有一个元素 `{"a", "b"}`。`vector` 有初始化列表构造函数，第一阶段先试它（[[over.match.list#1]]）：需要把 `{"a", "b"}` 转换成 `std::string`。
2. 用 `{"a", "b"}` 列表初始化 `std::string`：`initializer_list<char>` 构造函数不可行（字符串字面量不能转换成 `char`），第二阶段在全部构造函数中选，唯一可行的是迭代器区间构造函数 `basic_string(InputIterator, InputIterator)`，`InputIterator` 推导为 `const char*`（[[string.cons#20]]）。
3. 所以第一阶段成功，`v` 只有一个元素，它从区间 `["a", "b")` 构造。两个字面量是两个不同的数组对象，从一个指针出发自增到不了另一个，区间无效。把库函数用于无效区间，结果未定义（[[iterator.requirements.general#12]]）。

实测 AddressSanitizer 报告 `global-buffer-overflow`，`basic_string` 按 `"b" - "a"` 的长度从 `"a"` 开始读。

容易选的是良构，理由是"外层花括号等于调用 `vector(initializer_list<string>)`，内层是两个字符串"。实际上内层花括号是一个元素，两个字面量是这个元素的构造实参。

<div class="compare" markdown="1">

```cpp ok
std::vector<std::string> v{"a", "b"};      // 2 个元素
std::vector<std::string> w{{"a"}, {"b"}};  // 2 个元素
```

```cpp ub
std::vector<std::string> v{{"a", "b"}};    // 1 个元素，区间无效
```

</div>

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

按当前草案判定这个程序。

```cpp run
struct A {
  A() = delete;
  int x;
};

A a{};

int main() { return a.x; }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. `A() = delete` 是用户声明的构造函数，所以 `A` 不是聚合（[[dcl.init.aggr#1.1]]）。
2. `a{}` 是空列表，`A` 有默认构造函数（被删除的也算声明了），做值初始化（[[dcl.init.list#3.5]]）。值初始化先判断要不要零初始化，然后默认初始化，也就是调用选中的 `A()`（[[dcl.init#8.1]]、[[dcl.init#6.1]]）。
3. 调用被删除的函数，非良构（[[dcl.fct.def.delete#2]]）。

C++17 中这个程序是良构的：当时的聚合定义只排除用户提供的、explicit 的和继承的构造函数，`= delete` 不是用户提供的，`A` 仍是聚合，`a{}` 做聚合初始化，根本不调用构造函数。这让删除了默认构造函数的类照样能用 `{}` 创建对象。C++20 的 [[P1008R1]] 把条件改成没有用户声明的构造函数，堵上了这个缺口。用 `-std=c++17` 编译，Clang 接受这个程序。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定这个程序。

```cpp run
struct A {
  int a;
  const int& r;
};

int main() {
  A x(1.5, 2);
  return x.a + x.r;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为。**

1. `A` 是聚合，没有构造函数可行，初始化器是圆括号表达式列表，于是按 C++20 引入的圆括号聚合初始化处理：各元素依次从对应的表达式复制初始化（[[dcl.init#15.6.2.2]]）。
2. 圆括号形式允许窄化，`1.5` 转成 `int` 得到 1，不报错（[[dcl.init#15.6.2.2]] 的注 7）。
3. `r` 绑定到从 `2` 实质化出来的临时对象。用圆括号表达式列表初始化聚合时，绑定到引用元素的临时对象只活到包含该表达式列表的完整表达式结束（[[class.temporary#6.11]]）。下一行读取 `x.r` 时临时对象已经销毁，访问它是未定义行为（[[basic.life]]）。

实测 Clang 给出 `-Wdangling` 警告，AddressSanitizer 报告 `stack-use-after-scope`。

换成花括号，两件事都会变：窄化让程序非良构，而引用成员绑定的临时对象会被延长寿命。

<div class="compare" markdown="1">

```cpp ok
A x{1, 2};      // 临时对象寿命延长到 x 结束
int n = x.r;    // 2
```

```cpp error
A y{1.5, 2};    // error: 窄化
```

</div>

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

按当前草案，下面哪一行非良构？

```cpp
struct A { int x; int y; };
struct B : A { int z; };

A a1{.x = 1};               // A
B b1{.x = 1, .z = 3};       // B
B b2{A{1, 2}, .z = 3};      // C
A a2{1, .y = 2};            // D
```

- A. `A a1{.x = 1};`
- B. `B b1{.x = 1, .z = 3};`
- C. `B b2{A{1, 2}, .z = 3};`
- D. `A a2{1, .y = 2};`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：D。**

当前草案的语法允许一个指派初始化列表先写若干普通子句，再写指派子句（[[dcl.init]] 的 *designated-initializer-list*），并且允许指派符命名聚合基类的成员。约束集中在 [[dcl.init.aggr#4.1]]：

- 每个指派符在类 `C` 中查找，必须找到唯一的非静态数据成员，它所在的子对象的类型必须是 `C` 的聚合基类（`C` 本身，或递归地是其直接基类）。
- 列表前面的普通子句，每一个都必须对应 `C` 的一个直接基类子对象。

逐行套用：

- A：只指派 `x`，`y` 从空列表初始化为 0（[[dcl.init.aggr#6.2]]）。良构。
- B：`.x` 找到的是基类 `A` 的成员，`A` 是 `B` 的聚合基类；显式初始化的元素是基类 `A` 和 `B::z`，基类 `A` 再从 `{.x = 1}` 初始化（[[dcl.init.aggr#5.2.2]]）。良构。
- C：普通子句 `A{1, 2}` 对应直接基类 `A`，`.z` 指派自己的成员。良构。
- D：普通子句 `1` 对应的是数据成员 `x`，不是基类子对象，违反 [[dcl.init.aggr#4.1]]。草案在同一处的例子 `A{1, .a2=2}` 就标为 error。

指派初始化的顺序规则也还在：指派符必须按成员的声明顺序出现（[[dcl.init.list#3.1]]）。

放宽基类指派来自 [[P2287R5]]，是 C++23 之后的新措辞。本机 Clang 23 尚未实现：B 被拒绝（`field designator 'x' does not refer to any field in type 'B'`），C 和 D 都只得到 `-Wc99-designator` 扩展警告。所以在 Clang 上 B 出错而 D 通过，正好与草案相反。实际写法的取舍见 [[patterns/named-parameters]]。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

分别按 C++17 和当前草案，判断四个变量定义各自是否良构，并说明理由。

```cpp
struct P { explicit P() = default; int i; };
struct Q { private: Q() = default; public: int i; };
struct R { int i; int j; };

P p1{};
P p2 = {};
Q q1{};
R r1(1, 2);
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：**

| 定义 | C++17 | 当前草案 |
|---|---|---|
| `P p1{};` | 良构 | 良构 |
| `P p2 = {};` | 非良构 | 非良构 |
| `Q q1{};` | 良构 | 非良构 |
| `R r1(1, 2);` | 非良构 | 良构 |

**`P`**。C++17 的聚合不能有 explicit 构造函数，当前草案的聚合不能有任何用户声明的构造函数（[[dcl.init.aggr#1.1]]），所以 `P` 在两个版本中都不是聚合，结论也相同。

- `p1{}` 是直接列表初始化，空列表，值初始化（[[dcl.init.list#3.5]]）。默认初始化在全部构造函数中选（[[over.match.ctor#1]]），选中 explicit 的 `P()` 没有问题。`P()` 不是用户提供的，`i` 先被清零。
- `p2 = {}` 是复制列表初始化。它同样值初始化，但 [[over.match.ctor#1]] 的最后一句规定：在复制列表初始化语境里做默认初始化，如果选中的是 explicit 构造函数，初始化非良构。这条规则来自 [[CWG1518]]，Clang 在 C++17 模式下也执行它。

**`Q`**。C++17 中 `Q` 是聚合：默认化的私有构造函数既不是用户提供的，也不是 explicit 的，聚合定义当时并不看构造函数的访问权限。`q1{}` 做聚合初始化，根本不调用构造函数，私有构造函数形同虚设。当前草案中 `Q` 有用户声明的构造函数，不是聚合，`q1{}` 值初始化，调用私有的 `Q()`，访问检查失败（[[class.access]]）。修改这条规则的是 [[P1008R1]]，`Q` 这种绕过访问控制的写法正是它的动机之一。

**`R`**。C++17 只有花括号能聚合初始化，`R` 没有接受两个 `int` 的构造函数，`r1(1, 2)` 非良构。C++20 起，没有构造函数可行、目标是聚合、初始化器是圆括号表达式列表时，按元素逐个复制初始化（[[dcl.init#15.6.2.2]]，[[P0960R3]]）。

以上每一格都用 Clang 23 的 `-std=c++17` 和 `-std=c++2c` 核对过。

</details>
</div>

## 三、复制初始化、直接初始化与引用绑定

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定这个翻译单元（假设两个构造函数在别处定义）。

```cpp
struct E {
  explicit E(int);
  E(long);
};

E a = 1;
E b = {1};
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。** 出错的是 `b`。

1. `E a = 1;` 是从 `int` 复制初始化类对象，源类型与目标类型不同，走 [[dcl.init#15.6.3]]，按 [[over.match.copy#1]] 枚举候选：只有非 explicit 的构造函数是候选。`E(int)` 根本不参与，选中 `E(long)`，良构。
2. `E b = {1};` 是复制列表初始化，走 [[dcl.init.list#3.7]] 和 [[over.match.list#1]]。`E` 没有初始化列表构造函数，第二阶段的候选是全部构造函数，包括 explicit 的。`1` 到 `int` 是精确匹配，到 `long` 是整型转换，按等级 `E(int)` 胜出（[[over.ics.rank#4]]）。
3. 选出来之后，[[over.match.list#1]] 规定：复制列表初始化选中了 explicit 构造函数，初始化非良构。它不会退回去选 `E(long)`。

这是 [[over.match.list]] 的注 1 专门指出的差别：普通复制初始化把 explicit 构造函数排除在候选之外，复制列表初始化让它们参加重载决议，只在最后选中时报错。Clang 的诊断是 `chosen constructor is explicit in copy-initialization`。

<div class="compare" markdown="1">

```cpp ok
E a = 1;      // 只看非 explicit：E(long)
E c{1};       // 直接列表初始化：E(int)
E d = {1L};   // E(long) 精确匹配
```

```cpp error
E b = {1};    // 选中 explicit E(int)，报错
```

</div>

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定这个程序。

```cpp run
struct Flag {
  explicit operator bool() const { return true; }
};

int main() {
  Flag f;
  bool b1(f);
  bool b2{f};
  int n = f ? 1 : 0;
  return b1 + b2 + n;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构。** 程序返回 3。

1. `bool b1(f);` 是直接初始化，目标不是类类型，源是类类型，按 [[dcl.init#15.7]] 考虑转换函数，候选由 [[over.match.conv#1]] 给出：直接初始化时，返回类型经限定转换就能变成 `bool` 的 explicit 转换函数也是候选。`explicit operator bool` 被选中。
2. `bool b2{f};` 是直接列表初始化，单个元素，按直接初始化处理（[[dcl.init.list#3.9]]），同样落到 [[dcl.init#15.7]]，可以用 explicit 转换函数。这里经过的是用户定义转换，不是窄化。
3. `f ? 1 : 0` 的第一个操作数按语境转换为 `bool`（[[expr.cond#1]]），它的定义就是 `bool t(f);` 良构（[[conv.general#4]]），这正是第 1 步。

容易误判为非良构的理由是 explicit 转换函数只能用在 `if`、`!`、`&&` 这些语境里。实际上它在任何直接初始化中都可用，语境转换只是借用了直接初始化的形式。

<div class="compare" markdown="1">

```cpp ok
bool b1(f);
bool b2{f};
bool b3 = static_cast<bool>(f);
```

```cpp error
bool b4 = f;      // 复制初始化：没有可用的转换
bool b5 = {f};    // 复制列表初始化：同上
```

</div>

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定这个程序。

```cpp run
int main() {
  int i = 1;
  long&& r = i;
  r = 5;
  return i;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构。** 程序返回 1。

按 [[dcl.init.ref#5]] 的分支逐条走：

1. [[dcl.init.ref#5.1]]、[[dcl.init.ref#5.2]] 只适用于左值引用，跳过。
2. [[dcl.init.ref#5.3]] 要求初始化器是右值（或函数左值），或者是能转换出右值的类类型。`i` 是 `int` 左值，都不满足。
3. [[dcl.init.ref#5.4]] 要求 `long` 与 `int` 不是引用相关的。`long` 与 `int` 引用相关，是指 `long` 与 `int` 相似，或者 `long` 是 `int` 的基类（[[dcl.init.ref#4]]），两者都不成立，条件满足。
4. [[dcl.init.ref#5.4.2]]：`i` 隐式转换成 `long` 类型的 prvalue，经临时对象实质化，`r` 绑定到这个临时对象。临时对象的寿命延长到 `r` 的寿命（[[class.temporary#6]]）。

`r = 5` 改的是临时对象，`i` 仍然是 1。

误判为非良构的理由是右值引用不能绑定到左值。这条规则其实只针对引用相关的类型：[[dcl.init.ref#5.4]] 开头要求不是引用相关的，所以 `int&& r = i;` 非良构；而 `long&&` 绑定的根本不是 `i`，是转换出来的新对象。同理，`const long& cr = i;` 也绑定到一个临时对象，之后修改 `i` 不会反映到 `cr` 上。

<div class="compare" markdown="1">

```cpp ok
int i = 1;
long&& r = i;          // 绑定到临时 long
const long& cr = i;    // 也是临时对象
```

```cpp error
int i = 1;
int&& r = i;           // 引用相关，且 i 是左值
```

</div>

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定这个程序。

```cpp run
#include <utility>

struct S { int bf : 4; };

int main() {
  S s{3};
  int&& r = std::move(s.bf);
  return r;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。**

1. `std::move` 的形参是转发引用 `T&&`。实参 `s.bf` 是 `int` 左值，`T` 推导为 `int&`，形参类型折叠为 `int&`。
2. 用位域初始化 `int&`：[[dcl.init.ref#5.1.1]] 明确排除位域，[[dcl.init.ref#5.2]] 规定非 const 的左值引用在剩下的情况下一律非良构。[[class.bit#3]] 也直接写了：非 const 引用不能绑定到位域。
3. 隐式转换序列的形成不看实参是不是位域（[[over.best.ics.general#2]] 的注 1），所以重载决议照样选中 `std::move`，错误发生在真正绑定形参的时候。

Clang 报 `non-const reference cannot bind to bit-field 'bf'`，指向 `std::move` 的调用处。

容易误判为良构，是因为习惯上把 `std::move(x)` 当作能对任何左值使用的转换。它是一个以引用为形参的函数调用，位域没有地址，引用无法指向它。需要一个右值时，先把位域的值取出来：

```cpp ok
int v = s.bf;
int&& r = std::move(v);
```

</details>
</div>

## 四、值类别、decltype 与 auto

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

下面四条 `static_assert` 中，哪一条会失败？

```cpp
#include <type_traits>
#include <utility>

struct S { int m; };
S make();
void fn();

void test(bool b, int x, int y) {
  static_assert(std::is_same_v<decltype((make().m)), int&&>);              // A
  static_assert(std::is_same_v<decltype((std::move(fn))), void(&&)()>);    // B
  static_assert(std::is_same_v<decltype((b ? x : std::move(y))), int>);    // C
  static_assert(std::is_same_v<decltype(("abc")), const char(&)[4]>);      // D
}
```

- A. 断言 A（`make().m`）
- B. 断言 B（`std::move(fn)`）
- C. 断言 C（条件表达式）
- D. 断言 D（字符串字面量）

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B。**

四个操作数都加了括号，不是不带括号的 *id-expression* 或成员访问，所以 `decltype` 按值类别给出类型：xvalue 得 `T&&`，左值得 `T&`，prvalue 得 `T`（[[dcl.type.decltype#1.5]]、[[dcl.type.decltype#1.6]]、[[dcl.type.decltype#1.7]]）。

- A：`make()` 是 prvalue。成员访问要求左操作数是 glvalue，prvalue 先经临时对象实质化变成 xvalue（[[basic.lval#7]]）；左操作数不是左值时，`E1.E2` 是 xvalue（[[expr.ref#8.2]]）。所以是 `int&&`，成立。
- B：`std::move(fn)` 返回 `void(&&)()`。返回类型是函数的右值引用时，函数调用是左值（[[expr.call#15]]）。对函数类型来说，无论具名与否，右值引用都表现为左值（[[basic.lval#4]] 的注 3）。所以 `decltype` 得 `void(&)()`，断言失败。
- C：第二、三操作数类型相同（`int`），但一个是左值、一个是 xvalue。[[expr.cond#4]] 只在类型不同且有一方是类类型，或者两者是同一值类别、类型只差 cv 限定的 glvalue 时尝试转换，这里都不适用；[[expr.cond#5]] 要求值类别相同，也不满足；于是落到 [[expr.cond#6]]，结果是 prvalue（[[expr.cond#6]]），类型 `int`，成立。
- D：字符串字面量是左值（[[expr.prim.literal#1]]），类型 `const char[4]`，成立。

Clang 的报错是 `static assertion failed due to requirement 'std::is_same_v<void (&)(), void (&&)()>'`。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

`f` 的返回类型是什么？

```cpp
decltype(auto) f() {
  int x = 1;
  return (x);
}
```

- A. `int`
- B. `int&`
- C. `int&&`
- D. 非良构：不能返回局部变量的引用

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

1. `decltype(auto)` 的返回类型按 `decltype(E)` 推导，`E` 是 `return` 的操作数 `(x)`（[[dcl.type.auto.deduct#2.1]]、[[dcl.type.auto.deduct#4]]）。
2. `(x)` 带括号，所以不适用 [[dcl.type.decltype#1.3]]（取实体的声明类型），要看它的值类别。
3. `x` 是自动存储期的非 volatile 对象，是隐式可移动的实体；它作为 `return` 的操作数出现（允许带括号），中间只隔着块作用域，所以这个 *id-expression* 是 move-eligible 的（[[expr.prim.id.unqual#15]]）。move-eligible 的 *id-expression* 是 xvalue（[[expr.prim.id.unqual#12]]）。
4. xvalue 的 `decltype` 是 `int&&`（[[dcl.type.decltype#1.5]]）。

B 是 C++20 及以前的答案：那时 `(x)` 是左值，返回 `int&`。C++23 的 [[P2266R3]] 让被返回的名字直接成为 xvalue，草案在 [[dcl.type.auto.deduct#4]] 的例子里也写明 `auto f2(int x) -> decltype(auto) { return (x); }` 返回 `int&&`。

D 不对：返回局部变量的引用不是非良构，Clang 只给出 `-Wreturn-stack-address` 警告；调用方使用这个引用才是未定义行为。C++26 新增的非良构规则（[[P2748R5]]）只针对把返回的引用绑定到临时对象，`x` 不是临时对象。

在 Clang 23 上用 `static_assert(std::is_same_v<decltype(f()), int&&>)` 验证通过。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定这个程序。

```cpp run
#include <initializer_list>

int main() {
  auto a = {1, 2};
  auto b{3};
  for (auto e : {4, 5}) (void)e;
  auto c = {a.size(), 6};
  return b;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。** 出错的是 `c`。

1. `auto a = {1, 2};` 是复制列表初始化，`auto` 被替换成 `std::initializer_list<U>`，再按函数调用的模板实参推导求 `U`（[[dcl.type.auto.deduct#3]]）。实参是初始化列表时，对每个元素分别推导（[[temp.deduct.call#1]]），两个元素都推出 `int`，`a` 是 `std::initializer_list<int>`。
2. `auto b{3};` 是直接列表初始化，只允许一个元素，`E` 就是这个元素（[[dcl.type.auto.deduct#2.2.2]]），`b` 是 `int`。
3. 范围 `for` 里 `{4, 5}` 初始化的是 `auto&& __range`，也推出 `std::initializer_list<int>`，良构。
4. `auto c = {a.size(), 6};` 对两个元素分别推导，得到 `std::size_t` 和 `int`，推导冲突，声明非良构（[[dcl.type.auto.deduct#3]]）。

Clang 报 `deduced conflicting types ('size_t' (aka 'unsigned long') vs 'int') for initializer list element type`。初始化列表的推导不做公共类型，也不做任何转换，它和函数模板 `template<class U> void g(std::initializer_list<U>)` 用同一个实参调用时的推导完全一致。草案例子 `auto x2 = { 1, 2.0 };` 也是这个原因。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

写出下面每个表达式的值类别，以及 `decltype((e))` 的结果。

```cpp
struct S { int m; int& r; static int sm; };
S make();
enum E { e1 };
void fn();
template<int N> void t();

void test(int n, int* p) {
  int arr[2] = {};
  // 1. make().r          2. make().sm          3. std::move(arr)[0]
  // 4. e1                5. n = 1              6. (1, n)
  // 7. n++               8. *p                 9. fn
  // 10. static_cast<int&&>(n)                  11. t 体内的 N
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：**

| # | 表达式 | 值类别 | `decltype((e))` | 依据 |
|---|---|---|---|---|
| 1 | `make().r` | 左值 | `int&` | 成员是引用时，`E1.E2` 总是左值，不管 `E1` 是什么（[[expr.ref#8]]） |
| 2 | `make().sm` | 左值 | `int&` | 静态数据成员，`E1.E2` 是左值（[[expr.ref#8.1]]） |
| 3 | `std::move(arr)[0]` | xvalue | `int&&` | 对 xvalue 数组下标得 xvalue（[[basic.lval#4.4]]，属于注 3） |
| 4 | `e1` | prvalue | `E` | 枚举项不是变量，*id-expression* 是 prvalue（[[expr.prim.id.unqual#12]]） |
| 5 | `n = 1` | 左值 | `int&` | 内置赋值的结果是左操作数（[[expr.assign#1]]） |
| 6 | `(1, n)` | 左值 | `int&` | 逗号表达式的值类别跟随右操作数（[[expr.comma#1]]） |
| 7 | `n++` | prvalue | `int` | 后置自增得到旧值的副本（[[expr.post.incr#1]]） |
| 8 | `*p` | 左值 | `int&` | 间接运算的结果是左值（[[expr.unary.op#1]]） |
| 9 | `fn` | 左值 | `void(&)()` | 命名函数的 *id-expression* 是左值（[[expr.prim.id.unqual#12]]） |
| 10 | `static_cast<int&&>(n)` | xvalue | `int&&` | 转换到对象类型的右值引用得 xvalue（[[basic.lval#4.3]]，属于注 3） |
| 11 | `N` | prvalue | `int` | 非类类型的常量模板形参不是对象，*id-expression* 是 prvalue（[[expr.prim.id.unqual#12]]） |

容易错的是 1 和 2：常见的误解是临时对象的成员都是 xvalue。[[expr.ref#8]] 先处理引用成员，再处理静态成员，只有非引用的非静态数据成员才看 `E1` 的值类别。第 11 项的反面是类类型的常量模板形参：它命名的是一个模板形参对象，是左值。

把每一行写成 `static_assert(std::is_same_v<decltype((e)), …>)`，在 Clang 23 上全部通过。

</details>
</div>

## 五、复制消除、隐式移动、错误行为与静态初始化

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定这个程序。`Pinned` 既不能复制也不能移动。

```cpp run
struct Pinned {
  Pinned() = default;
  Pinned(const Pinned&) = delete;
  Pinned(Pinned&&) = delete;
  int v = 7;
};

Pinned make() { return Pinned{}; }
Pinned relay() { return make(); }

int main() {
  Pinned a = relay();
  Pinned b = Pinned(Pinned(make()));
  Pinned* p = new Pinned(make());
  Pinned arr[2] = {make(), relay()};
  int r = a.v + b.v + p->v + arr[1].v;
  delete p;
  return r;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构。** 程序返回 28。

核心规则只有一条：用类型相同（忽略 cv）的 prvalue 初始化一个类对象时，直接用这个初始化表达式初始化目标对象（[[dcl.init#15.6.1]]）。prvalue 在被实质化之前不是对象，它只是初始化某个结果对象的配方（[[basic.lval#5]]）。没有中间对象，就没有复制或移动，也就不需要可用的复制、移动构造函数。

- `return Pinned{};` 与 `return make();`：`return` 从操作数复制初始化函数调用的结果对象（[[stmt.return#2]]），操作数是同类型 prvalue，适用 [[dcl.init#15.6.1]]。`relay()` 的结果对象一路传到 `a`。
- `Pinned(Pinned(make()))`：圆括号里只有一个表达式的函数式转换等价于对应的强制转换（[[expr.type.conv#1.1]]），这里归结为 `static_cast`，其结果对象从操作数直接初始化（[[expr.static.cast#5]]），又是 [[dcl.init#15.6.1]]。草案例子 `T x = T(T(T()));` 说的就是这件事。
- `new Pinned(make())`：*new-initializer* 按直接初始化解释（[[expr.new#24.2]]），同上。
- 数组元素从初始化列表的元素复制初始化，元素是同类型 prvalue，同上。

这不是允许的复制消除，[[class.copy.elision]] 在这里不起作用：根本没有被省略的对象。[[class.copy.elision#1.1]] 允许省略的只是具名局部变量的复制，与这里的 prvalue 无关。

<div class="compare" markdown="1">

```cpp ok
Pinned make() { return Pinned{}; }   // prvalue
```

```cpp error
Pinned make() {
  Pinned p;
  return p;    // error: 需要移动构造函数，已删除
}
```

</div>

讲解见 [[papers/guaranteed-copy-elision]] 和 [[topics/value-categories]]。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

按当前草案判定这个程序。`M` 只能移动，不能复制。

```cpp run
struct M {
  M() = default;
  M(M&&) = default;
  M(const M&) = delete;
};

struct Holder { Holder(M) { } };

M from_ref(M&& r) { return r; }
M paren() { M m; return (m); }
Holder convert() { M m; return m; }
int&& pass(int&& x) { return x; }

int main() {
  M a = from_ref(M{});
  M b = paren();
  Holder h = convert();
  (void)a; (void)b; (void)h;
  return pass(1) - 1;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构。**

四个 `return` 都依赖同一条规则：如果 *id-expression* 命名的是隐式可移动的实体（自动存储期的非 volatile 对象，或者指向非 volatile 对象类型的右值引用），作为 `return` 的操作数出现（可以带括号），中间只隔着块作用域，它就是 move-eligible 的（[[expr.prim.id.unqual#15]]），而 move-eligible 的 *id-expression* 是 xvalue（[[expr.prim.id.unqual#12]]）。

- `from_ref`：`r` 是具名的右值引用，在别处是左值。但它是指向对象类型的右值引用变量，属于隐式可移动实体，`return r;` 里的 `r` 是 xvalue，选中移动构造函数。
- `paren`：`(m)` 带括号仍然算，[[expr.prim.id.unqual#15.2]] 明写"possibly parenthesized"。
- `convert`：`m` 是 xvalue，用它复制初始化 `Holder` 的结果对象，调用 `Holder(M)`，其形参从 xvalue 初始化，用移动构造函数。返回类型与变量类型不同也不影响，规则只看表达式本身。
- `pass`：`x` 是 xvalue，可以直接绑定到返回类型 `int&&`。`pass(1)` 返回的引用指向实参 `1` 的临时对象，它活到包含这次调用的完整表达式结束（[[class.temporary#6.10]]），在同一个完整表达式里读取没有问题。

历史上这四种情况是分几次放宽的：`from_ref` 和 `convert` 在 C++20 之前非良构（[[P1825R0]]），`pass` 在 C++23 之前非良构（[[P2266R3]]）。用 `-std=c++20` 编译，Clang 只拒绝 `pass`：`rvalue reference to type 'int' cannot bind to lvalue of type 'int'`。演变过程见 [[papers/implicit-move]]。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定这个翻译单元。

```cpp
struct M {
  M() = default;
  M(M&&) = default;
  M(const M&) = delete;
};

M pick(bool b) {
  M x, y;
  if (b) return x;
  return [&] { return y; }();
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构。** 出错的是 lambda 里的 `return y;`。

1. `return x;`：`x` 满足 [[expr.prim.id.unqual#15]] 的三个条件，是 xvalue，用移动构造函数，良构。
2. lambda 按引用捕获，`return y;` 里的 `y` 命名的仍是 `pick` 的局部变量 `y`，它本身是隐式可移动的实体。但 [[expr.prim.id.unqual#15.3]] 要求从 `y` 的声明到这个表达式之间的每一层作用域都是块作用域，这里隔着 lambda 的函数形参作用域，不是块作用域。所以 `y` 不是 move-eligible 的，是左值。
3. lambda 的返回类型推导为 `M`，从左值 `y` 复制初始化结果对象，需要复制构造函数，它被删除（[[dcl.fct.def.delete#2]]）。
4. 外层 `return [&]{…}();` 的操作数是 prvalue，适用保证的复制消除，本身没问题。

这条限制有道理：lambda 可能在 `pick` 返回前被调用多次，把外层变量悄悄移走会改变后续调用看到的值。

同样非良构的还有 `return b ? x : y;`（条件表达式不是 *id-expression*，[[expr.prim.id.unqual#15.2]] 不满足）和返回静态局部变量（不是自动存储期，[[expr.prim.id.unqual#15.1]] 不满足）。这两种 Clang 也都报 `call to deleted constructor of 'M'`。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

按当前草案判定这个程序。

```cpp
int main() {
  unsigned char c [[indeterminate]];
  unsigned char d = c;
  c = d;
  unsigned char e = true ? c : d;
  (void)e;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，行为有定义。**

1. `c` 标了 `[[indeterminate]]`，它的字节是不确定值，而不是错误值（[[basic.indet#1.1]]、[[dcl.attr.indet#1]]）。一般来说，求值产生不确定值就是未定义行为（[[basic.indet#2]]）。
2. 但 [[basic.indet#2]] 为无符号普通字符类型和 `std::byte` 列了例外：
    - 用不确定值初始化一个 `unsigned char` 对象，该对象得到不确定值（[[basic.indet#2.3]]）。`d = c` 属于这种情况。
    - 简单赋值的右操作数是不确定值、左操作数是 `unsigned char` 左值时，左操作数的对象得到不确定值（[[basic.indet#2.2]]）。`c = d` 属于这种情况。
    - 条件表达式的第二、三操作数产生不确定值时，结果是不确定值（[[basic.indet#2.1.1]]）；再用它初始化 `e`，又是 [[basic.indet#2.3]]。
3. `(void)e` 是弃值表达式（[[basic.indet#2.1.4]]）。

全程只是在 `unsigned char` 之间搬运不确定值，没有一次求值落在例外之外，所以没有未定义行为。去掉 `[[indeterminate]]`，`c` 持有错误值，同样的例外对错误值也适用，结论不变。

只要把值用到别处，例外就结束了：

```cpp ub
unsigned char c [[indeterminate]];
unsigned char d = c;
int i = d;       // 整型提升产生不确定值：未定义行为
```

去掉这里的 `[[indeterminate]]`，最后一行变成错误行为。

本机 Clang 23 不认识 `[[indeterminate]]`，给出 `unknown attribute 'indeterminate' ignored` 警告，并对 `d = c` 给出 `-Wuninitialized` 警告；这两条都不影响按草案的判定。详见 [[papers/erroneous-behaviour]]。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

这个程序输出什么？整个程序只有这一个翻译单元。

```cpp run
#include <cstdio>

extern int b;
int a = b + 1;
int b = 41;

int main() { std::printf("%d\n", a); }
```

- A. `1`
- B. `42`
- C. `1` 或 `42`，未指明
- D. 未定义行为：`a` 在 `b` 初始化之前读取了它

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B。**

1. `b` 的初始化器 `41` 是常量表达式，`b` 是常量初始化的（[[expr.const.init#4]]、[[expr.const.init#5]]），执行的是常量初始化，属于静态初始化（[[basic.start.static#2]]）。
2. `a` 的初始化器 `b + 1` 要对 `b` 做左值到右值转换，而 `b` 不是 const，不能在常量表达式中使用，所以 `b + 1` 不是核心常量表达式（[[expr.const.core#2.10]]）。`a` 不是常量初始化的，先被零初始化，然后做动态初始化。
3. 所有静态初始化都强先发生于任何动态初始化（[[basic.start.static#2]]）。所以 `a` 动态初始化时，`b` 已经是 41，`a` 为 42。
4. 实现可以把 `a` 也改成静态初始化，但前提是结果与动态初始化相同（[[basic.start.static#3]]），所以仍是 42。

干扰项 C 对应的是另一种写法：如果 `b` 本身也需要动态初始化，结果才取决于实现。[[basic.start.static#3]] 的注 2 举的正是这种例子：

```cpp unspecified
inline int g() { return 41; }
extern int b;
int a = b + 1;   // 1 或 42
int b = g();
```

这时 `b` 有动态初始化，按定义顺序在 `a` 之后（[[basic.start.dynamic#3]]），但实现可以把它提前做成静态初始化。只有 `b` 静态初始化而 `a` 动态初始化时，`a` 读到 41，结果为 42；其余情况结果都是 1：`b` 动态初始化时，`a` 读到零初始化的 0；`a` 也被提前做成静态初始化时，它的值必须等于所有不要求静态初始化的变量都动态初始化时的结果（[[basic.start.static#3.2]]），同样是 1。本机 Clang 在 `-O0` 和 `-O2` 下都输出 1。

D 不对：`b` 有静态存储期，在任何代码运行之前它的存储已经存在并初始化，读取它不是未定义行为。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

对 `main` 中编号的每一行，说明会调用哪些构造函数，其中哪些是标准要求一定不发生的、哪些是允许省略的、哪些是一定发生的。

```cpp run
#include <cstdio>
#include <utility>

struct S {
  S() { std::puts("S()"); }
  S(const S&) { std::puts("S(const S&)"); }
  S(S&&) { std::puts("S(S&&)"); }
  ~S() { std::puts("~S()"); }
};

S f() { return S(); }
S g() { S s; return s; }
S h(S p) { return p; }
void take(S) { }

int main() {
  S a = f();                // 1
  S b = g();                // 2
  take(S());                // 3
  S c = std::move(S());     // 4
  S d = h(S());             // 5
  const S& e = S();         // 6
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：**

| 行 | 构造 | 性质 | 依据 |
|---|---|---|---|
| 1 | `S()` | 只有一次构造，不可能有复制或移动 | `S()` 与 `f()` 都是同类型 prvalue，`a` 就是结果对象（[[dcl.init#15.6.1]]） |
| 2 | `S()`，可能再加 `S(S&&)` | 移动可以省略 | 具名返回值优化（[[class.copy.elision#1.1]]）；不省略时 `s` 是 move-eligible 的，用移动而不是复制（[[expr.prim.id.unqual#15]]） |
| 3 | `S()` | 只有一次构造 | 形参从同类型 prvalue 复制初始化，适用 [[dcl.init#15.6.1]] |
| 4 | `S()`、`S(S&&)` | 两次都一定发生 | `std::move` 的实参让 prvalue 实质化成临时对象（[[dcl.init.ref#5.3]]），返回 xvalue；`c` 从 xvalue 初始化，选中移动构造函数，没有任何省略的余地 |
| 5 | `S()`、`S(S&&)` | 两次都一定发生 | 实参直接初始化形参 `p`；`return p;` 的 `p` 是函数形参，[[class.copy.elision#1.1]] 明确排除形参，不能省略，`p` 是 move-eligible 的，用移动 |
| 6 | `S()` | 只有一次构造 | prvalue 实质化为临时对象，引用直接绑定，寿命延长到 `e` 的寿命（[[class.temporary#6.1]]） |

几个要点：

- 第 1、3 行不是复制消除。C++17 起 prvalue 不再是临时对象，[[class.copy.elision]] 讨论的省略只剩第 2 行这种具名对象的情况。用 `-fno-elide-constructors` 编译，第 1、3 行的输出不变，只有第 2 行多出一次 `S(S&&)` 和随后的一次 `~S()`。
- 第 4 行是常说的悲观化移动：`std::move` 把本可以直接初始化 `c` 的 prvalue 变成了 xvalue，强制多出一次移动。Clang 用 `-Wpessimizing-move` 提示。
- 第 5 行说明按值传入的形参不能做具名返回值优化：形参的存储由调用方安排，函数无法把它构造在返回值的位置上。C++11 起它至少会被移动而不是复制。

实测 Clang 23 默认输出中，2 行只调用 `S()`；4、5 行各有一次 `S(S&&)`，紧跟着一次 `~S()`（第 4 行是被移动的临时对象在完整表达式结束时销毁，第 5 行是形参 `p` 销毁）。程序结束时按 `e`、`d`、`c`、`b`、`a` 的逆序销毁 5 个对象。更多逐行追踪见 [[topics/special-members-and-elision]]。

</details>
</div>

## 题目与条款对照

| 题号 | 考查点 | 条款 |
|---|---|---|
| 1 | 类外 `= default` 是用户提供的；值初始化不清零；错误值 | [[dcl.init#8]]、[[dcl.fct.def.default#5]]、[[basic.indet#2]] |
| 2 | const 对象的默认初始化 | [[dcl.init#7]] |
| 3 | 聚合、值初始化、`new T()`、线程存储期的零初始化 | [[dcl.init.aggr#6]]、[[dcl.init#8]]、[[expr.new#24]]、[[basic.start.static#2]] |
| 4 | 最令人烦恼的解析 | [[dcl.ambig.res#1]]、[[dcl.fct#5]] |
| 5 | 窄化的常量例外；`nullptr` 到 `bool` | [[dcl.init.list#7]]、[[dcl.init#15.8]] |
| 6 | 初始化列表构造函数优先；后备数组的复制 | [[over.match.list#1]]、[[dcl.init.list#5]] |
| 7 | 嵌套花括号选中迭代器区间构造函数 | [[over.match.list#1]]、[[iterator.requirements.general#12]] |
| 8 | 删除的默认构造函数与聚合定义 | [[dcl.init.aggr#1]]、[[dcl.init.list#3.5]] |
| 9 | 圆括号聚合初始化：窄化与临时对象寿命 | [[dcl.init#15.6.2.2]]、[[class.temporary#6.11]] |
| 10 | 指派初始化与聚合基类 | [[dcl.init.aggr#4.1]]、[[dcl.init.list#3.1]] |
| 11 | 聚合定义在 C++17 与 C++20 之间的变化 | [[dcl.init.aggr#1]]、[[over.match.ctor#1]]、[[dcl.init#15.6.2.2]] |
| 12 | 复制列表初始化选中 explicit 构造函数 | [[over.match.list#1]]、[[over.match.copy#1]] |
| 13 | explicit 转换函数与直接初始化 | [[dcl.init#15.7]]、[[over.match.conv#1]]、[[conv.general#4]] |
| 14 | 右值引用绑定到转换出的临时对象 | [[dcl.init.ref#5.4]] |
| 15 | 位域与非 const 引用 | [[dcl.init.ref#5.2]]、[[class.bit#3]] |
| 16 | 值类别与 `decltype` | [[dcl.type.decltype#1]]、[[expr.ref#8]]、[[expr.call#15]]、[[expr.cond#6]] |
| 17 | `decltype(auto)` 与 move-eligible | [[dcl.type.auto.deduct#4]]、[[expr.prim.id.unqual#15]] |
| 18 | `auto` 与初始化列表的推导 | [[dcl.type.auto.deduct#3]]、[[temp.deduct.call#1]] |
| 19 | 表达式的值类别分类 | [[basic.lval#4]]、[[expr.ref#8]]、[[expr.prim.id.unqual#12]] |
| 20 | 保证的复制消除 | [[dcl.init#15.6.1]]、[[basic.lval#5]] |
| 21 | 隐式移动的范围 | [[expr.prim.id.unqual#15]]、[[class.temporary#6.10]] |
| 22 | lambda 与条件表达式不触发隐式移动 | [[expr.prim.id.unqual#15]] |
| 23 | `[[indeterminate]]` 与 `unsigned char` 的例外 | [[basic.indet#2]]、[[dcl.attr.indet#1]] |
| 24 | 静态初始化先于动态初始化 | [[basic.start.static#2]]、[[basic.start.static#3]] |
| 25 | 复制消除、实质化与移动的综合 | [[dcl.init#15.6.1]]、[[class.copy.elision#1]]、[[class.temporary#6]] |
