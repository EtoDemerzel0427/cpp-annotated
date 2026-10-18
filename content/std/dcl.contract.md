---
title: 函数契约说明符
summary: C++26 的 pre / post：函数契约断言如何依附于函数的首次声明、重声明必须一致（ODR 式比较）、哪些函数不能有契约、后置条件中使用的形参必须是 const、结果绑定 `post(r: …)` 的类型与语义、何时"需要"实例化契约
status: draft
covers: dcl.contract.func, dcl.contract.res
since: c++26
papers: P2900
related: basic.contract, stmt.contract.assert, expr.call, expr.prim.id.unqual, dcl.decl, dcl.fct.def.coroutine, class.temporary
tags: 契约, C++26, 前置条件, 后置条件
updated: 2026-10-18
---

C++26 把**契约**（contracts）引入了核心语言。一个契约断言有三种写法：函数声明上的**前置条件** `pre(…)` 与**后置条件** `post(…)`，以及函数体里的断言语句 `contract_assert(…)`（[[stmt.contract.assert]]）。三者共享的语义——谓词怎样求值、四种求值语义（ignore / observe / enforce / quick-enforce）、违反时调用的处理函数——统一放在 [[basic.contract]]。

本节（[dcl.contract]）只负责前两者作为**声明的一部分**的规则：

- [dcl.contract.func]：文法；函数契约断言属于哪个声明；跨声明、跨翻译单元的一致性；哪些函数不能有；后置条件对形参的 const 要求；何时被"需要"；
- [dcl.contract.res]：后置条件中的**结果绑定** `post(r: r > 0)`。

!!! warning "编译器支持"
    截至写作时，本机 Clang 23 不支持契约语法（`int f(int x) pre(x > 0);` 报 "expected function body after function declarator"）。本页例子按标准判定标注，未在本地编译验证，因此也不提供 godbolt 按钮。

## 文法与基本概念（[dcl.contract.func] ¶1–2）

```
function-contract-specifier-seq:
    function-contract-specifier function-contract-specifier-seq(opt)
function-contract-specifier:
    precondition-specifier          // pre attr(opt) ( conditional-expression )
    postcondition-specifier         // post attr(opt) ( result-name-introducer(opt) conditional-expression )
```

`pre` 和 `post` 不是保留关键字，而是**上下文关键字**（像 `override`、`final`），只在声明符之后的这个位置有特殊含义——所以 `int pre = 0;` 依然合法，现有代码不受影响。

契约说明符出现在声明符之后（[[dcl.decl]] 的 *init-declarator* 文法）、函数体之前（[[dcl.fct.def.general]] 的 *function-definition* 文法），位于尾置 requires 子句和 `override`/`final` 之后：

```cpp title="contract-syntax.cpp"
#include <concepts>
int f(int x) pre(x > 0) post(r: r > x);           // 声明
template<class T>
  T g(T x) requires std::integral<T> pre(x != 0); // requires 子句在前
struct B { virtual int h(int i) pre(i >= 0); };
struct D : B { int h(int i) override pre(i >= 0) post(r: r != 0) { return i + 1; } };  // override 在前
auto l = [](int n) pre(n > 0) { return n; };      // lambda：作用于其调用运算符（¶3 注 2）
```

¶1 **函数契约断言**（function contract assertion）是与函数关联的契约断言（[[basic.contract.general]]）：

- `pre` 引入**前置条件断言**（precondition assertion），关联于**进入**函数；
- `post` 引入**后置条件断言**（postcondition assertion），关联于**正常退出**函数。

注 1：后置条件**不**关联于通过异常（[[expr.throw]]）或 `longjmp` 退出函数。换言之，后置条件描述的是"函数成功时保证什么"，抛异常不算违反后置条件。

¶2 函数契约断言的**谓词**是其 *conditional-expression* **按语境转换为 `bool`**。注意文法用的是 *conditional-expression* 而不是 *expression*：顶层不能有逗号运算符和赋值（`pre(a, b)` 非良构；要用逗号必须再加括号）。谓词中对外部变量、形参、`*this` 的引用是隐式 const 的，见 [[basic.contract.general]]。

### 何时求值

求值时机由 [[expr.call]] 规定：

- 前置条件在**所有形参初始化之后**、函数体开始之前求值；
- 后置条件在**返回值（结果对象）初始化之后**、局部变量销毁之后、**形参销毁之前**求值（[[stmt.return]]）。

对于虚函数调用，[[expr.call#5]] 规定的顺序是：**静态选择的函数**的前置条件 → **实际调用的函数**的前置条件 → 函数体 → 实际调用的函数的后置条件 → 静态选择的函数的后置条件。所以通过基类引用调用时，基类与最终覆盖函数的契约**都**会被检查。

!!! note "虚函数上的契约"
    当前草案允许虚函数及其覆盖函数各自声明契约，并按上述顺序检查（标准在 [[expr.call#5]] 有一个详细例子：通过 `X1&` 调用 `Z::f` 时依次断言 `a, g, h, b`）；用限定名 `x1ref.X1::f()` 非虚调用时只检查 `X1::f` 自己的契约；通过成员函数指针调用时只检查实际调用的函数的契约。据作者了解，C++26 正式版（P2900）中虚函数不能带函数契约说明符，这部分是之后才并入草案的扩展——具体版本归属请以 [[diff]] 附录与提案记录为准。

## 契约属于首次声明（¶3）

¶3 函数的某个**首次声明**（first declaration，[[basic.def]]：没有其他声明从它可达的声明）上的 *function-contract-specifier-seq* 为该函数**引入**对应的函数契约断言。`pre`/`post` 之后的属性属于所引入的契约断言。

注 2：lambda 声明符上的契约说明符作用于闭包类型的函数调用运算符（或运算符模板）。

这意味着契约是**函数**的属性，不是某个声明的属性（与默认实参形成鲜明对比，参见 [[dcl.fct.default]]）：一旦首次声明给出了契约，所有调用——不论通过哪个声明找到函数——都使用这组契约。

## 重声明的一致性（¶4–5）

¶4 不是首次声明的声明 D（即重声明），要么**完全省略**契约说明符，要么给出与任何从 D 可达的首次声明 F **相同**的契约说明符序列。

- 若 D 与 F 在**不同翻译单元**（例如 F 在模块接口中导出，D 在实现单元中），只有当 D 附属于具名模块时才要求诊断。
- 若 F1 是 TU1 中的首次声明，F2 是 TU2 中的首次声明（典型情况：两个 TU 各自包含同一个头文件，头文件中的声明在各自 TU 里都是首次声明），F1 与 F2 必须指定相同的契约说明符序列，否则 {{ifndr}}。

¶5 "相同"的定义：两个序列由相同的说明符按**相同顺序**组成；两个说明符 C1（在 D1 上）与 C2（在 D2 上）相同，当且仅当：

- ¶5.1 把它们的谓词分别放进 D1 与 D2 上的函数定义里时，满足 **ODR**（[[basic.def.odr]]）——但允许形参改名、外围模板的模板形参改名、结果绑定改名；不同 TU 中谓词内定义的实体视为同一个；
- ¶5.2 两者要么都有 *result-name-introducer*，要么都没有。

若仅仅因为谓词中两个 **lambda 表达式**的比较而不满足条件，不要求诊断（每个 lambda 表达式有独一无二的闭包类型，按 ODR 它们"不同"）。注 3：等价的契约说明符序列在所有 TU 的所有使用与定义中生效。

标准例 1：

```cpp title="contract-redecl.cpp" error
bool b1, b2;

void f() pre (b1) pre ([]{ return b2; }());
void f();                                     // OK：省略契约说明符
void f() pre (b1) pre ([]{ return b2; }());   // IFNDR：两个 lambda 的闭包类型不同
void f() pre (b1);                            // error: 只重复了一部分

int g() post(r : b1);
int g() post(b1);         // error: 一个有结果绑定、一个没有

namespace N {
    void h() pre (b1);    // 这里的 b1 是 ::b1
    bool b1;
    void h() pre (b1);    // error: 这里的 b1 是 N::b1——按 ODR 两个谓词不同
}
```

最后一例说明"相同"不是**文本**相同，而是**含义**相同：同样写 `b1`，名字查找的结果不同，契约就不同。

!!! tip "实践建议"
    在头文件中的声明上写契约，定义处（`.cpp`）省略——这是 ¶4 明确允许的，也避免了维护两份副本。若定义也要写，保持逐字一致，且谓词中不要用 lambda。

## 不能有契约的函数（¶6）

¶6 以下函数不能有函数契约说明符：

- **弃置函数**（[[dcl.fct.def.delete]]）——它永远不会被调用；
- **在首次声明上预置的函数**（[[dcl.fct.def.default]]）——它的行为由语言规定，没有"用户的"前置条件可言；而且它可能是平凡的，契约检查会破坏平凡性。

```cpp title="contract-deleted.cpp" error
struct S {
    S() pre(true) = default;          // error: 在首次声明上预置
    void f(int) pre(true) = delete;   // error: 弃置函数
    S(const S&);
};
S::S(const S&) pre(true) = default;   // 契约必须在首次声明上给出；这里是重声明，
                                      // 且与类内的首次声明（无契约）不一致——error
```

## 后置条件中使用的形参必须是 const（¶7）

¶7 若函数 *f* 的后置条件谓词 **odr-use** 了 *f* 的某个**非引用形参**，那么该形参以及 *f* 的**所有声明**中的对应形参都必须具有 **const 类型**。

为什么？后置条件在函数体执行之后求值，而函数体可能修改了形参：

```cpp
int clamp_inc(int x) post(r: r == x + 1) {   // 若允许：r 与"修改后的 x"比较
    x = 100;                                 // 函数体改了 x
    return 1;                                // 后置条件读到的 x 是 100，而不是调用时的值
}
```

调用者理解的"`x`"是**传入的值**，后置条件若看到被修改后的副本，语义就错了。要求 const 保证了形参在函数体内不会被修改，后置条件看到的就是传入值。注 4：

- 该要求甚至适用于**没有**写这个后置条件的声明（因为 const 与否必须在所有声明中一致——尽管顶层 const 不属于函数类型，[[dcl.fct#5]]）；
- **数组和函数类型的形参**会退化成**非 const** 的指针，即使写了 const：

```cpp title="post-const-param.cpp" error
int f(const int i[10])
    post(r : r == i[0]);   // error: i 的类型是 const int*（指针本身不是 const），不是 int* const

int g(int x) post(r: r > x);          // error: x 不是 const
int h(const int x) post(r: r > x);    // OK
int k(int& x) post(x > 0);            // OK：引用形参不受此限
```

注意引用形参不受此限：引用不能"重新绑定"，后置条件读到的是被引用对象的**当前**值——这正是对 `int& x` 形参"函数返回后 `x` 满足什么"的自然表达。

对**协程**，[[dcl.fct.def.coroutine#6]] 的注释指出：后置条件中 odr-use 非引用形参是非良构的——协程的形参会被复制到协程帧中，函数体修改的是副本，const 也无法挽救这一语义鸿沟。

## 函数指针与间接调用（¶8）

¶8（注）函数契约断言在**间接调用**时同样求值——通过函数指针、成员函数指针调用都会检查。但**函数指针、成员函数指针、函数类型别名本身不能带契约说明符**：契约属于函数，不属于类型（契约说明符不是函数类型的一部分，[[dcl.fct#13]]）。

```cpp title="contract-fptr.cpp" error
int f(int x) pre(x > 0);
int (*pf)(int) = f;            // OK：调用 pf(-1) 时仍会检查 f 的前置条件
int (*pg)(int) pre(true);      // error: 契约说明符只能用于声明函数的声明符（[dcl.decl] ¶6）
using F = int(int) pre(true);  // error: 别名不能带契约
```

## 契约何时被"需要"（¶9）

¶9 函数的契约断言在以下情况下被认为是**需要的**（needed，[[temp.inst]]）：

- ¶9.1 函数被 odr-use；
- ¶9.2 函数被定义。

这对模板很重要：函数模板特化的契约谓词只有在"需要"时才实例化。注 6：**重载决议不考虑契约说明符**——契约不像 requires 子句那样参与候选筛选：

```cpp title="contract-overload.cpp" error
template <typename T> void f(T t) pre( t == "" );
template <typename T> void f(T&& t);
void g() {
    f(5);     // error: 二义性——即使第一个的前置条件对 int 根本无法实例化
}
```

这是有意的设计：契约是**运行期**对正确性的检查，不是编译期的重载约束。若前置条件参与 SFINAE，"写不写契约"就会改变程序调用哪个函数，契约就不再是可以安全添加或移除的注解。

## 结果绑定（[dcl.contract.res]）

```
attributed-identifier:   identifier attribute-specifier-seq(opt)
result-name-introducer:  attributed-identifier :
```

¶1 后置条件中的 *result-name-introducer*（`r:`）是一个**声明**，它把标识符引入为关联函数的**结果绑定**（[[g:result-binding|result binding]]）的名字。

- 若函数的返回类型是 cv `void`，带结果绑定的后置条件非良构；
- 结果绑定**指代函数调用所返回的对象或引用**——不是一个副本；
- 它的类型是函数的返回类型；
- 注 1：命名结果绑定的 *id-expression* 是 **const 左值**（[[expr.prim.id.unqual#6]]：返回类型是 `T&` 时表达式类型为 `const T`，否则为 `const U`）。

```cpp title="result-binding.cpp" ok
int f()
    post(r : r == 1)      // r 指代 f() 返回的 int
{
    return 1;
}
int i = f();              // 后置条件检查通过
```

"指代返回的对象本身"有一个精细的后果，与 [[class.temporary]] 中"实现可以为平凡可复制类型的返回值引入临时量"的许可相互作用（标准例 2）：

```cpp title="result-binding-temp.cpp"
struct A {};                          // 平凡可复制：实现可以经由寄存器返回，引入临时量
struct B { B() {} B(const B&) {} };   // 非平凡复制：不会引入临时量

template <typename T>
T f(T* const ptr)
    post(r: &r == ptr)
{
    return {};
}

int main() {
    A a = f(&a);   // 后置条件可能失败：若实现引入了临时量，r 指代该临时量（[expr.prim.id.unqual] ¶14），
                   // 其地址不是 &a
    B b = f(&b);   // 后置条件必定成立：没有临时量，r 就是 b
}
```

¶2 若**非模板化**函数的声明返回类型含**占位符类型**（`auto`），带结果绑定的后置条件只能出现在**定义**上——因为没有函数体就无法推导返回类型，结果绑定的类型也就无从确定。模板化函数没有这个限制（实例化时会有定义）。

```cpp title="result-binding-auto.cpp" error
auto g(auto&) post (r: r >= 0);    // OK：g 是（简写）函数模板
auto h()      post (r: r >= 0);    // error: 不能在非定义声明上命名返回值
auto k()      post (r: r >= 0)     // OK：定义
{
    return 0;
}
```

## 实现视角

!!! impl
    - **在哪里检查**：标准允许实现在调用方或被调方插入检查代码。常见的实现策略是在被调函数入口/出口检查（只需一份代码），或在调用点检查（能利用调用方的语义选择，并允许跨 TU 混合不同的求值语义，[[basic.contract.eval]]）。由于契约属于函数而不属于类型，通过函数指针调用时，被调方检查是最自然的方案。
    - **ABI**：契约说明符不进入函数类型，不影响名字修饰；在头文件中给已有函数添加契约不改变 ABI。
    - **¶4 的诊断**：同一 TU 内的不一致必须诊断；跨 TU 的不一致（典型：头文件被不同宏配置包含）是 IFNDR，链接器通常无法发现。

## 历史与演进

!!! history
    - **C++20 草案**：曾以属性语法 `[[expects: …]]` / `[[ensures r: …]]` / `[[assert: …]]` 加入契约（[[P0542R5]]），2019 年 7 月因设计分歧被整体移出 C++20。
    - **SG21**：之后成立的契约研究组以"最小可行产品"（MVP）为目标重新设计，最终形成 [[P2900]]：使用上下文关键字 `pre`/`post` 与 `contract_assert`，引入四种求值语义。
    - **C++26**：P2900 并入，本节规则成形。
    - **C++26 之后的草案**：允许虚函数带契约（[[expr.call#5]] 规定检查顺序）——版本归属请编辑核对。

## 陷阱

!!! pitfall "后置条件看不到异常"
    抛异常退出的函数不检查后置条件。若要表达"无论如何都要成立"的不变式，需要在函数体内用 RAII 或 `contract_assert`。

!!! pitfall "按值形参与后置条件"
    `int f(int x) post(r: r > x)` 非良构；必须写 `int f(const int x) …`，并且**所有**声明都要写 `const`——包括头文件中没有写后置条件的那一个。

!!! pitfall "契约不是重载约束"
    想按条件屏蔽重载，用 requires 子句；想在运行期检查调用者是否守约，用 `pre`。二者在重载决议中的地位完全不同（¶9 注 6）。

!!! pitfall "谓词有副作用"
    谓词可能被求值 0 次、1 次或多次（[[basic.contract.eval]]），且其中的变量隐式 const。不要依赖谓词的副作用。

## 思考题

!!! question "思考题 1"
    头文件 `a.h` 中有 `int f(int x) pre(x > LIMIT);`，`LIMIT` 是宏。TU1 在包含前 `#define LIMIT 0`，TU2 中 `#define LIMIT 1`。程序是否良构？

<details markdown="1">
<summary>答案</summary>

两个 TU 中的声明各自都是首次声明（彼此不可达），¶4 要求它们的契约说明符序列"相同"。宏展开后谓词分别是 `x > 0` 与 `x > 1`，按 ¶5.1 的 ODR 比较不同，所以程序非良构，不要求诊断（IFNDR）。这与 inline 函数体中使用不同宏值违反 ODR 是同一类问题。
</details>

!!! question "思考题 2"
    为什么 ¶7 只对**非引用**形参要求 const，而 `int& x` 形参在后置条件中随便用？

<details markdown="1">
<summary>答案</summary>

非引用形参是函数的**局部副本**：调用者关心的是传入的值，若函数体修改了副本，后置条件读到的值与调用者心目中的"x"不一致——要求 const 消除了这种分歧。引用形参指代调用者的对象，函数体通过引用修改它正是函数的可观察效果之一，后置条件读取修改后的值（"返回时 x 是什么状态"）恰好是想要表达的语义。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 语法 | `pre(谓词)`、`post(r: 谓词)`；上下文关键字；位于 requires 子句、`override` 之后，函数体之前 |
    | 归属 | 首次声明引入契约，契约属于函数而非声明或类型 |
    | 重声明 | 省略，或按 ODR 意义完全相同（含顺序、是否有结果绑定）；跨 TU 不一致为 IFNDR |
    | 禁止 | 弃置函数、首次声明即预置的函数；函数指针与别名不能带契约 |
    | 后置条件与形参 | odr-use 的非引用形参在所有声明中都须为 const；数组/函数形参退化后非 const |
    | 求值 | 前置：形参初始化后；后置：结果初始化后、形参销毁前；异常退出不检查后置条件 |
    | 重载 | 契约不参与重载决议；在 odr-use 或定义时才"需要" |
    | 结果绑定 | const 左值，指代返回的对象本身（可能是实现引入的临时量）；`void` 函数不能有；`auto` 返回的非模板函数只能在定义上写 |
