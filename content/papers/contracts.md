---
title: 契约（P2900）
summary: P2900 怎样把前置条件、后置条件和断言变成语言的一部分：为什么用 pre/post/contract_assert 而不是属性语法或 assert，为什么检查与否交给构建而不是写在每条断言上，谓词为什么被当作 const、可能被求值零次或多次，以及最小可行产品刻意留下的空白和至今未消的反对意见。
status: draft
order: 32
group: C++26
since: c++26
papers: P2900R14, P2961R2, P2935R3, P2461R1, P2737R0, P3173R0, P3573R0, P1774R8, P3097R3
related: basic.contract, basic.contract.eval, basic.contract.handler, dcl.contract, dcl.contract.res, stmt.contract.assert, support.contract, expr.prim.id.unqual, dcl.attr.assume, diff.cpp23, history/contracts, topics/undefined-behavior, papers/library-hardening, papers/erroneous-behaviour
tags: 契约, 提案, C++26, 断言, 设计取舍
updated: 2026-10-19
---

!!! tldr
    - P2900 引入三种契约断言：函数声明上的 `pre`、`post`，函数体里的 `contract_assert` 语句。条件写在接口上，调用者和工具都能看到。
    - 每次求值用 ignore、observe、enforce、quick-enforce 中的哪一种，由实现决定（通常是编译选项），代码里不能指定，也不能查询。
    - 谓词应当没有副作用：它可能被求值零次、一次或多次；谓词里提到的外部变量一律当作 const。
    - 后置条件里用到的值形参必须在所有声明上都是 const，否则函数体改了形参，后置条件就失去意义。
    - 虚函数、类不变式、旧值、假设语义、逐条指定语义都不在最小可行产品里；谓词自身的 UB、语义由实现决定等问题至今仍有反对意见。

## 契约之前：注释和 assert

一个函数对调用者的要求，过去只能写在注释里，再在函数体里用 `assert` 检查一遍：

```cpp
#include <cassert>
#include <cstddef>

// 要求：p 非空，i < n
int at(const int* p, std::size_t n, std::size_t i) {
    assert(p != nullptr);
    assert(i < n);
    return p[i];
}
```

这样写有三个问题。第一，条件藏在函数体里，调用处的编译器和静态分析器看不到它，除非内联展开。第二，`assert` 只有开、关两种状态，由每个翻译单元里 `NDEBUG` 是否定义决定。第三，`assert` 是宏，关掉时整个参数被预处理器删掉，参数里的副作用也随之消失：

```cpp title="assert.cpp" run ok
#include <cassert>
#include <cstdio>

int calls = 0;
bool check() { ++calls; return true; }

int main() {
    assert(check());          // 副作用随 NDEBUG 消失
    std::printf("calls = %d\n", calls);
}
```

本机 Clang 23 上，不加 `-DNDEBUG` 输出 `calls = 1`，加上则输出 `calls = 0`。宏还有自己的语法毛病：参数里没被圆括号包住的逗号会把参数拆开，`assert(std::is_same_v<T, int>);` 在 Clang 上报 "too many arguments provided to function-like macro invocation"。

契约的长期演变（D 语言式的 `in`/`out` 块、Bloomberg 的断言宏、C++20 草案里的 `[[expects:]]` 以及它为什么被撤回）见 [[history/contracts|契约沿革]]。下面只讲 [[P2900R14]] 这一版的设计：它在 C++20 失败之后，以最小可行产品（minimum viable product，MVP）为目标重新设计，2025 年 2 月并入 C++26 草案。

## 语法：为什么是 pre、post、contract_assert

### 最终的样子

```cpp title="C++26（本机 Clang 23 无法编译）"
int f(const int x)
    pre(x != 1)                  // 前置条件
    post(r: r == x && r != 2)    // 后置条件，r 指代返回值
{
    contract_assert(x != 3);     // 断言语句
    return x;
}
```

`pre`、`post` 放在声明符的最后：在尾置返回类型、`requires` 子句之后，紧挨着分号或函数体（[[dcl.contract.func]] 的语法；类成员里还在 `override` 之后，见 [[class.mem.general]]）。它们是上下文关键字，只在这个位置有特殊含义，名叫 `pre` 的变量不受影响。`contract_assert` 是完整关键字（[[stmt.contract.assert]]），因为它要和函数调用区分开。

括号里的文法是 *conditional-expression*，不是任意表达式。所以 `pre(a = b)` 这种把 `==` 误写成 `=` 的情况非良构，真想写赋值得再加一层括号（P2900R14 §3.2）。

### 被放弃的属性式语法

C++20 草案用的是 `[[expects: x > 0]]` 这类写法。在 P2900 的讨论期间它仍是一个候选（[[P2935R3]]），最后被 [[P2961R2]] 的写法取代。P2961R2 §1 给出的理由可以归成三条：

1. 契约不是属性。 标准属性被设计成可以忽略的（去掉它不改变程序含义），契约不能被忽略：它可能终止程序，处理函数抛异常时甚至会从函数中间开出一条新的控制流路径。写成双方括号会让用户以为二者是同一类东西。
2. 位置不对。 属性要跟在它所修饰的东西后面。函数类型的属性位置在尾置返回类型、`override` 和 `requires` 子句之前，违背阅读顺序，后置条件还得延迟解析；断言只能挂在空语句上，没法当表达式用。
3. 扩展余地太小。 `[[post r: …]]` 里，冒号前只有一个位置可以放东西。以后想加标签、捕获、结构化绑定形式的返回值名时，这些都挤在同一处，会出现歧义：冒号前的标识符是标签还是返回值名？方括号是捕获还是结构化绑定？

另外两种替代方案也被比较过：[[P2461R1]] 把谓词放在花括号里，看起来像 lambda，可谓词是表达式而不是语句；[[P2737R0]] 首先采用了 `关键字(谓词)` 的结构，但同时提出改名为 `precond`/`postcond`/`incond`、改用预定义的 `result` 名字等，这些附加选择在 SG21 反响不佳（P2961R2 §2）。P2961R2 保留了它的基本结构，去掉了其余部分。

### 为什么不叫 assert

最自然的名字是 `assert`，几乎所有语言都这么叫。P2961R2 §5.2 列出了让它与 `<cassert>` 的宏共存的几种办法，并逐一否定：

| 方案 | 问题 |
|---|---|
| 删除 `<cassert>` | 破坏大量现有代码，包括 C 与 C++ 共用的代码 |
| 把 `assert` 改成关键字，行为改为契约断言 | 宏的行为取决于 `NDEBUG`。即使让 `NDEBUG` 对应 ignore 语义，ignore 下谓词仍要解析并 odr-use，`#ifndef NDEBUG` 里才声明的调试变量就编译不过了 |
| 包含了 `<cassert>` 就是宏，否则是契约 | 同一行 `assert(x)` 的含义取决于别处有没有包含头文件，库头文件的作者无从判断 |

剩下的办法只有换一个关键字。P2961R2 比较了一批候选，最后选了 `contract_assert`。这个新关键字是 C++26 对 C++23 的一处不兼容，记录在 [[diff.cpp23.lex#2]]：把 `contract_assert` 当标识符的 C++23 代码不再合法。另一处在 [[diff.cpp23.cpp#1]]：`pre`、`post` 这类有特殊含义的标识符不能再定义成宏。

## 四种语义，由构建决定

### 语义不写在断言上

每次求值一个契约断言，都使用四种[[g:evaluation-semantic|求值语义]]之一（[[basic.contract.eval#1]]）：

| 语义 | 检查谓词 | 违反之后 |
|---|---|---|
| ignore | 否 | 不发生任何事 |
| observe | 是 | 调用违约处理函数，返回后继续执行 |
| enforce | 是 | 调用违约处理函数，返回后终止程序 |
| quick-enforce | 是 | 不调用处理函数，立即终止 |

¶2 用哪一种是实现定义的，同一条断言的不同次求值也可以不同（[[basic.contract.eval#2]]）。¶3 只给出建议做法：提供全部 ignore 和全部 enforce 两种编译选项，默认 enforce。

P2900 刻意没有在源码里提供指定语义的方法。§2.3 列出的未提议特性里，就有在断言上直接写出语义、给断言分级（C++20 的 `default`/`audit`/`axiom`）两项。§3.5.5 说明了理由：程序员写断言时说的是"这里应当成立什么"，该不该检查、失败了怎么办，是部署时的决定，应由构建方式决定。平台也可以只提供一部分语义，比如一个安全关键的嵌入式平台可以根本不提供 observe。

### 不能在编译期查询

`assert` 有 `NDEBUG` 可以测，契约故意没有对应物。P2900 的原则 5 要求，一次求值用哪种语义一般不应在编译期可检测，否则打开检查就等于编译了另一个程序（§3.1.1）。同一原则也解释了为什么 ignore 下谓词仍是潜在求值的（[[basic.contract.eval#4]]）：谓词总要能编译，代码不会因为长期关闭检查而腐烂，切换语义也不会改变程序的其余部分。

这直接带来一个后果：同一个内联函数可能在两个翻译单元里以不同语义编译。P2900 §3.5.11 把这称为混合模式，认为它本身不违反 ODR，因为两份定义的记号完全相同。链接器最终保留哪一份，在不改动链接器的实现上相当于随机。作者们认为这比把混合编译定为 IFNDR 要好，因为 IFNDR 相当于整个程序范围的 UB。草案只在一种情况下承认这会违反 ODR：谓词有副作用，并且改变了某个常量表达式的值（[[basic.contract.eval#8]] 注 6）。

### 编译期求值

契约断言在常量求值中也会求值。此时没有处理函数可调：observe 下违反只产生一条诊断，enforce 和 quick-enforce 下违反使程序非良构（[[basic.contract.eval#8]]）。谓词在常量求值中不是核心常量表达式，也算违反（[[basic.contract.eval#7]] ¶7.3）。

### 为什么有 quick-enforce

enforce 要构造一个 `contract_violation` 对象、调用处理函数，生成的代码不小。草案的注说明，quick-enforce 的用途是尽快终止，并尽量减少检查对代码体积的影响（[[basic.contract.eval#16]]）。终止的方式也是实现定义的：调用 `std::terminate`、调用 `std::abort`，或者直接停止执行（[[basic.contract.eval#9]]），后者允许实现只插入一条陷阱指令。

## 违约处理函数

违反发生在运行期、语义是 observe 或 enforce 时，程序调用[[g:contract-violation-handler|违约处理函数]] `::handle_contract_violation`（[[basic.contract.handler#1]]）。实现提供一个默认版本，是否允许用户替换是实现定义的（[[basic.contract.handler#3]]）。替换的方式和全局 `operator new` 一样：在程序里定义一个同名、同签名的函数。

```cpp title="handler.cpp（C++26，本机无法编译）"
#include <contracts>
#include <cstdio>

void handle_contract_violation(
    const std::contracts::contract_violation& v) {
    std::fprintf(stderr, "%s:%u: %s\n",
                 v.location().file_name(),
                 v.location().line(),
                 v.comment());
}
```

有两处细节来自 P2900 §3.5.9 的明确选择。标准库的任何头文件都不声明这个函数（[[basic.contract.handler#1]] 注 1），这样用户的替换版本可以自己决定是否 `noexcept`；`operator new` 的声明由库提供，替换时就只能跟着它的异常说明走。`contract_violation` 没有用户可用的构造函数，所以在处理函数之外无法伪造一次违反。

`contract_violation` 的成员（[[support.contract.violation]]）报告谓词的文本、源位置、断言种类、使用的语义、是否为终止型语义，以及违反的检测方式：谓词为假，还是谓词抛出了异常。P2900R14 里还有一个 `evaluation_exception()` 成员，当前草案的类定义中已经没有它。处理函数是在那个异常的隐式处理器内被调用的（[[basic.contract.eval#12]]），可以在里面重新抛出它。

处理函数自己也可以抛异常。从函数契约断言里抛出时，效果如同函数体抛出了这个异常，所以 `noexcept` 函数会调用 `std::terminate`（[[basic.contract.eval#17]]）。P2900 §3.6.6 指出这个设计的代价：只要平台允许安装可能抛异常的处理函数，编译器就得假设每个契约断言都可能抛异常。

## 谓词：可能求值零次或多次

### 冗余原则

P2900 §3.1 把整个设计建立在几条原则上，前两条是：

- **首要原则**（Prime Directive）：契约断言的存在或求值，不应改变程序是否正确。
- **冗余原则**：在正确的程序里，契约断言是多余的，去掉任意一部分都不改变程序的正确性。

由此可以推出，谓词的副作用不能是程序依赖的东西。P2900 没有把有副作用的谓词定为非良构，因为编译器分不清哪些副作用有害（记日志通常无害），这样的限制也太严（§3.1.2）。它的做法是不保证副作用发生的次数：

```cpp title="P2900R14 §3.5.8 的例子（本机无法编译）"
int i = 0;
void f() pre((++i, true));

void g() {
    f();   // i 可能是 0、1、17……
}
```

零次来自 [[basic.contract.eval#5]]：用检查型语义求值时，是否真的求值谓词是未指明的，实现可以改用一个没有副作用、结果相同的表达式。多次来自[[basic.contract.eval#18]] 的按序求值：一个函数的全部前置条件（或全部后置条件、或一串相邻的 `contract_assert`）作为一组，其中的断言可以重复求值实现定义的次数，只要每条第一次出现的先后顺序不变。一个常见的来源是调用方和被调用方各检查一次（P2900R14 §3.5.7）。

`assert` 的参数要么求值零次（定义了 `NDEBUG`），要么正好一次。依赖这一点的老代码改成契约时要调整。P2900 §3.6.7 用的例子改写自 Clang 源码：`assert(++nIter < 6)` 在断言里递增计数器，换成契约就不对了。正确的写法是把状态维护挪到断言外面，让谓词只做判断：

```cpp title="counter.cpp" run ok
#include <cassert>
bool keep_iterating(unsigned i) { return i < 5; }

int main() {
    unsigned n_iter = 0;
    while (keep_iterating(n_iter)) {
        ++n_iter;               // 状态在断言外面维护
        assert(n_iter < 6);     // 谓词没有副作用
    }
}
```

把这里的 `assert` 换成 `contract_assert`，含义在各种语义下都不变。

### 名字自动变成 const

为了尽早拦住无意中修改状态的谓词，P2900 让谓词里指代外部变量的名字都成为 const 左值（[[expr.prim.id.unqual#7]]），`this` 成为指向 const 的指针（[[expr.prim.this#3]]），结果绑定也是 const（[[expr.prim.id.unqual#6]]）。这和 const 成员函数里成员变成 const 是同一个思路。

```cpp title="（本机无法编译）"
int global = 0;
void f(int x, char* p, int& ref)
    pre((x = 0) == 0)    // error: x 是 const 左值
    pre((*p = 5))        // OK：const 是浅的，不穿透指针
    pre((ref = 5))       // error: 引用指代的对象也按 const 看待
    pre((global = 2));   // error
```

const 只加在名字这一层，不穿透指针。P2900 §3.4.2 的解释是，深 const 会让裸指针和智能指针表现不同。`mutable` 成员仍然可以修改，`const_cast` 也能绕过，但修改本来就是 const 的对象仍是 UB。

这条规则有一个不太直观的后果：同一个表达式挪进谓词，重载决议的结果可能变化。

<div class="compare" markdown="1">

```cpp
// 契约（本机无法编译）
struct X {};
bool p(X&);        // 返回 true
bool p(const X&);  // 返回 false

void f(X x)
    pre(p(x));     // 选 p(const X&)
```

```cpp
// 等价的 C++23 写法
#include <utility>
// p 的声明同左
void g(X x) {
    p(x);                 // p(X&)
    p(std::as_const(x));  // 谓词里
}                         // 相当于这样
```

</div>

右侧的完整版本在本机 Clang 23 上验证过：`p(x)` 选中 `p(X&)`，`p(std::as_const(x))` 选中 `p(const X&)`。P2900 认为一个对 const 与否给出不同答案的重载集本身就是缺陷。反对者的看法不同，见后文。

## 后置条件：返回值和形参

### 结果绑定

`post(r: …)` 里的 `r` 叫**结果绑定**（result binding），指代函数返回的对象或引用（[[dcl.contract.res#1]]），在谓词里是 const 左值。它的名字由用户自己取，而不是预定义的 `result`，这正是 P2737R0 被否决的附加选择之一。

如果返回类型是推导的，又没有更早的声明，后置条件要等函数体确定类型后才能解析，所以带结果绑定的后置条件只能写在定义上（[[dcl.contract.res#2]]）。

对于可以放在寄存器里传递的类型，实现可以先构造一个临时对象再复制到最终的结果对象。后置条件看到的可能是这个临时对象，所以 `post(r: &r == ptr)` 这种比较地址的断言可能失败（[[dcl.contract.res#1]] 例 2，[[expr.prim.id.unqual#14]]）。P2900 §3.4.5 的态度是：值一定相同，用户不应依赖这两个对象的身份。

### 值形参必须是 const

如果后置条件 odr-use 了一个非引用形参，这个形参在函数的所有声明上都必须是 const 类型（[[dcl.contract.func#7]]），即使顶层 const 在其他场合会被忽略。P2900 §3.4.4 用 `clamp` 说明原因：

```cpp title="没有 const 规则时的问题（本机无法编译）"
double clamp(double lo, double hi, double v)
    post(r: (v < lo && r == lo) || (v > hi && r == hi)
            || r == v);

double clamp(double lo, double hi, double v) {
    lo = hi = v = 0.0;    // 满足后置条件，但毫无用处
    return 0.0;
}
```

后置条件是写给调用者看的，`v` 应当指调用者传入的值。如果函数体可以修改形参，后置条件检查的就是被改过的值，而这一点只看声明无从知道。修改也可能是隐式的：`std::string g(std::string p) post(r: r.starts_with(p)) { return p; }` 里，`return p` 会把 `p` 移走，后置条件看到的是移动后的字符串。要求形参是 const，函数体就改不了它。

同样的理由带出两个推论。数组形参会退化成指针，`const int a[10]` 退化成 `const int*` 而不是 `int* const`，所以在后置条件里使用数组形参总是非良构（[[dcl.contract.func#7]] 例 2）。协程会把形参复制到协程帧里，复制时忽略 const，之后照样可以修改，所以协程的后置条件 odr-use 值形参也是非良构（[[dcl.fct.def.coroutine#6]] 注 1）。

## 其他几处限制

- 只看第一次声明。 函数的契约由它的第一次声明引入；后续声明要么不写，要么一字不差地重复（[[dcl.contract.func#4]]）。不同翻译单元里各自的第一次声明不一致则是 IFNDR。
- 不进入类型。 契约不是函数类型的一部分，函数指针、成员函数指针和类型别名都不能带契约；但通过指针间接调用时，被调函数的契约照样要检查（[[dcl.contract.func#8]]）。这意味着实现不能总在调用处检查，有时必须在函数内部或一段转接代码（thunk）里检查。
- 重载决议看不见契约。 契约不影响重载决议（[[dcl.contract.func#9]] 注 6），也不影响 `noexcept` 运算符的结果、概念是否满足（P2900 原则 3）。
- 构造与析构。 构造函数的前置条件在成员初始化之前求值，析构函数的后置条件在成员销毁之后求值，此时直接读成员是 UB。所以在这两处通过隐式 `this->` 引用成员是非良构的（[[expr.prim.id.general#2]]），需要时得显式写 `this->`，只用地址而不读值。
- 默认、删除的函数。 在第一次声明上被 `= default` 或 `= delete` 的函数不能带契约（[[dcl.contract.func#6]]）。

## MVP 刻意留下的空白

P2900R14 §2.3 列出了有意不提议的功能，并说明以后会作为扩展单独提出：

| 没有提议的功能 | 现状 |
|---|---|
| 虚函数上的 `pre`/`post` | C++26 中非良构；[[P3097R3]] 的方案已进入 C++29 草案，虚调用先检查静态选中函数的前置条件，再检查实际调用函数的（[[expr.call#5]]） |
| 函数指针、类型别名上的契约 | 不支持 |
| 在后置条件里引用形参的旧值 | 不支持，只能靠 const 形参 |
| 假设语义（未检查的谓词视为成立，供优化使用） | 不提供；需要优化提示时用 C++23 的 `[[assume]]`（[[P1774R8]]，[[dcl.attr.assume]]） |
| 在断言上写出语义、给断言分级 | 不提供，语义完全由实现选择 |
| 抛异常退出时的后置条件 | 不支持，后置条件只在正常返回时求值（[[dcl.contract.func#1]]） |
| 无法在运行期求值的谓词（如调用无定义的函数） | 不支持，谓词总是潜在求值 |
| 跨断言保持的状态（类似 `#ifndef NDEBUG` 里的变量） | 不支持 |
| 类不变式、过程式接口 | 不支持 |

决定先不做的地方怎样写进条文，由原则 14 规定（P2900R14 §3.1.4）：没有共识的构造一律非良构，而不是未指明或未定义。以后放宽为合法时，不会改变任何已有程序的含义。C++26 里虚函数带 `pre` 非良构，到 C++29 草案变成合法，就是这样走的。

假设语义值得单独说一句。C++20 契约被撤回的一个原因，正是没有检查的契约被当作假设、反过来让检查本身被优化掉。P2900 的原则 13 规定契约不引入新的 UB（§3.1.4），所以 ignore 真的什么也不做；向编译器注入事实的需求由 `[[assume]]` 承担，两者从此是不同的工具。R14 的 `<contracts>` 草稿里给 `evaluation_semantic` 留了一行注释掉的 `assume = 5`，标注为预期的未来扩展（§3.7.1）。

## 争议：几个公开的反对意见

P2900 进入 C++26 时并不是全体一致的。下面按技术问题归纳两份反对文件，以及 P2900 自己对相应问题的立场。

谓词里的 UB。 [[P3173R0]] 认为，谓词求值可以出现 UB，这违背了 SG21 先前达成的"安全优先"共识；它还认为不支持虚函数和函数指针的契约设施不够用，并要求先展示在标准库上的应用。P2900R14 §3.6.1 承认这一点：契约不引入新的 UB，但谓词是普通表达式，自身的 UB 照旧。它给出的例子是 `pre(f(a) > a)`，其中 `f(a)` 返回 `a + 100`：编译器可以假设有符号加法不溢出，把整个前置条件优化成 `true`，即使语义是 enforce。可观察检查点（[[g:observable-checkpoint]]，[[basic.contract.eval#6]]、[[basic.contract.eval#15]]）只防住了断言之外的 UB 回头影响断言的情况。

太多实现定义的东西。 [[P3573R0]] 列出了十几条担忧，其中几条直接针对上文讲到的设计选择：

- 语义和终止方式都由实现决定，普通用户很难知道什么会被检查、失败后发生什么，可移植的契约很难写；
- 不能把契约分组分别开关；
- 以不同设置编译的翻译单元链接在一起时，模板、内联函数最终用哪种设置没有说清；
- const 化（名字自动变成 const）是一条新的不规则规则，警告也能抓住它想抓的大部分错误；
- 谓词抛异常不应算作违反，应当像其他异常一样正常传播；
- 虚函数的方案没有实践经验，而且很多设计需要契约被继承。

P2900 对这些问题都有明确的选择，前文已经讲到它们的理由：语义交给构建是原则 5 和原则 12（契约不是控制流）的直接结果；混合模式被认为好于 IFNDR；把抛异常算作违反，是因为谓词没算出值就等于没能确认契约成立（§3.5.6）。双方的分歧在于这些取舍的代价是否可以接受，而不在于事实。分组控制（标签）、总是强制检查的断言等后续工作，以及进入 C++26 之后仍在继续的争论，见 [[history/contracts|契约沿革]]。

## 措辞落在哪里

| 条款 | 内容 |
|---|---|
| [[basic.contract.general]] | 什么是契约断言、谓词；`va_start` 不能出现在谓词里 |
| [[basic.contract.eval]] | 四种语义、违反的判定、处理流程、按序求值与重复 |
| [[basic.contract.handler]] | `::handle_contract_violation`，默认版本与替换 |
| [[dcl.contract.func]] | `pre`/`post` 的语法、第一次声明、const 形参规则 |
| [[dcl.contract.res]] | 结果绑定 |
| [[stmt.contract.assert]] | `contract_assert` 语句 |
| [[expr.prim.id.unqual]]、[[expr.prim.this]] | 谓词里名字和 `this` 的 const 化 |
| [[support.contract]] | `<contracts>` 头文件与 `contract_violation` |
| [[diff.cpp23.lex]]、[[diff.cpp23.cpp]] | 新关键字、`pre`/`post` 不能作宏名 |

特性测试宏是 `__cpp_contracts`，当前草案中它的值是 `202606L`（[[cpp.predefined]]）。

!!! impl "编译器支持"
    本机 Homebrew Clang 23.1.3 不支持契约：`pre(…)` 报 "expected function body after function declarator"，`__cpp_contracts` 未定义，libc++ 也没有 `<contracts>` 头文件。本页的契约代码因此都不带判定，结论依据标准条文和 P2900R14。GCC 的开发分支有一个按 P2900 实现的版本，本机没有 GCC，未做验证。

## 常见误解

!!! pitfall "`contract_assert` 是换了名字的 `assert`"
    不是。它是语句而不是宏，不受 `NDEBUG` 控制，谓词总要能编译；求值次数不保证是 0 或 1；外部变量在谓词里是 const，同一个表达式可能选中不同的重载；违反时走违约处理函数。

!!! pitfall "observe 可以用来做错误处理"
    P2900 的原则 12 明确说契约不是控制流。同一条断言在另一个构建里可能是 ignore，所以必须处理的错误（比如校验外部输入）要用普通的 `if` 和异常，而不是契约。

!!! pitfall "写了 `pre` 就保证不会带着违反的条件进入函数"
    只有终止型语义才有这个保证，而用哪种语义由实现决定。即使是 enforce，谓词自身的 UB 也可能让检查被优化掉。

## 思考题

!!! question "1"
    下面的后置条件哪里有问题？怎样改？
    ```cpp
    int scale(int x, int k)
        post(r: r == x * k);
    ```

<details markdown="1">
<summary>答案</summary>

后置条件 odr-use 了非引用形参 `x` 和 `k`，按 [[dcl.contract.func#7]] 它们在所有声明（包括定义）上都必须是 const，这里没有，程序非良构。改成 `int scale(const int x, const int k) post(r: r == x * k);`，定义也要写成 `const int`。这样函数体不能修改 `x`、`k`，后置条件检查的就是调用者传入的值。顺带一提，`x * k` 溢出时谓词本身是 UB，契约不会替你挡住它。
</details>

!!! question "2"
    一个函数有 `pre(a) pre(b)` 两个前置条件。下面哪些求值序列是合法的：`a b`、`a b a b`、`b a`、`a a b`、`b`？

<details markdown="1">
<summary>答案</summary>

`a b`、`a b a b`、`a a b` 合法；`b a` 和 `b` 不合法。按 [[basic.contract.eval#18]]，实现可以把列表里的断言重复任意（实现定义的）次数，但每个断言都必须至少出现一次，且第一次出现的顺序必须与声明顺序一致。`b a` 让 `b` 先于 `a` 首次出现，`b` 漏掉了 `a`。
</details>

!!! question "3"
    为什么 `<contracts>` 不声明 `handle_contract_violation`，而 `<new>` 却声明了可替换的 `operator new`？

<details markdown="1">
<summary>答案</summary>

如果库提供声明，用户的替换版本就必须和它的异常说明一致。不声明，用户就可以自己决定处理函数是否 `noexcept`：想把违反转成异常的项目可以让它抛出，想保证不抛的项目可以标 `noexcept`（[[basic.contract.handler#1]]，P2900R14 §3.5.9）。另一方面，`contract_violation` 没有用户可用的构造函数，即使有声明，用户在处理函数之外也没法调用它。
</details>
