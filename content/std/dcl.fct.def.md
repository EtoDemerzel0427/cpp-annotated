---
title: 函数定义
summary: 函数定义的文法与函数体；__func__；= default（哪些函数可以预置、与隐式声明的差异、首次声明预置 vs 类外预置、隐式 constexpr/inline、"用户提供"的定义）；= delete 与 C++26 的 = delete("理由")；可替换函数
status: draft
covers: dcl.fct.def.general, dcl.fct.def.default, dcl.fct.def.delete, dcl.fct.def.replace
papers: N2346, P2573R2
related: dcl.fct, dcl.fct.def.coroutine, special, class.ctor, class.copy.ctor, class.copy.assign, class.dtor, class.compare.default, over.inc.default, basic.def.odr, dcl.inline, dcl.constexpr, replacement.functions
tags: 函数定义, default, delete, __func__, 可替换函数
updated: 2026-10-18
---

[[dcl.fct]] 规定了函数**声明**的类型；本节（[dcl.fct.def]）规定函数**定义**：函数体有哪几种形式、函数体里自动可用的 `__func__`，以及两种"不写函数体的定义"——`= default` 与 `= delete`。最后一个子条款规定**可替换函数**（`operator new` 等由程序替换实现提供的版本）的通用规则。协程定义单独成页：[[dcl.fct.def.coroutine]]。

## 函数定义的文法（[dcl.fct.def.general] ¶1）

```
function-definition:
    attr(opt) decl-specifier-seq(opt) declarator virt-specifier-seq(opt)
        function-contract-specifier-seq(opt) function-body
    attr(opt) decl-specifier-seq(opt) declarator requires-clause
        function-contract-specifier-seq(opt) function-body
function-body:
    ctor-initializer(opt) compound-statement
    function-try-block
    = default ;
    deleted-function-body           // = delete ;   或   = delete ( unevaluated-string ) ;
```

要点：

- 说明符序列可选（构造函数、析构函数、转换函数没有）；
- `virt-specifier-seq`（`override`/`final`）与 `requires-clause` 互斥地出现在两个产生式中：带 `override`/`final` 的定义必须是成员声明；带 requires 子句的定义必须定义**模板化函数**；
- 契约说明符（[[dcl.contract]]）位于函数体之前；
- 非正式地说"函数体"时，指的是 *function-body* 这个非终结符——对构造函数，还**包括**在没有 *mem-initializer* 时使用的默认成员初始化器或默认初始化。这一点对"在函数体内抛出异常"、"函数体内的 odr-use"等规则的适用范围很重要。
- 开头的属性属于函数。

¶2 在函数定义中，`void declarator ;` 或 `declarator ;` 必须是 [[dcl.fct]] 意义上良构的函数声明。函数**只能在命名空间作用域或类作用域中定义**——不能在块作用域定义函数（lambda 是表达式，不是函数定义）。函数定义的形参类型和返回类型不能是在函数体内**不完整或抽象**的类类型（可能 cv 限定），除非函数是弃置的。

```cpp title="fn-def-scope.cpp" error
struct Inc;
Inc make();                     // OK：声明可以返回不完整类型
Inc make() { return {}; }       // error: 定义中返回类型不完整
Inc oops(Inc) = delete;         // OK：弃置函数不受此限
void outer() {
    void inner() { }            // error: 不能在块作用域定义函数
}
```

为什么弃置函数豁免？弃置函数永远不会被调用，不需要知道参数和返回值的布局——这使得"禁止某种转换"的弃置重载可以针对尚不完整的类型声明。

¶3–6（例与注）：`int max(int a, int b, int c) { … }` 中 `int` 是说明符序列，`max(int a, int b, int c)` 是声明符，`{ … }` 是函数体。*ctor-initializer* 只用于构造函数（[[class.base.init]]）。成员函数声明符上的 cv 限定影响函数体中 `this` 的类型（[[expr.prim.this]]）。未使用的形参不必命名。

## `__func__`（¶7–8）

¶7 **函数局部预定义变量**（function-local predefined variable）是在函数形参作用域中隐式定义的、具有静态存储期的变量。

¶8 `__func__` 就是这样一个变量，其定义如同：

```cpp
static const char __func__[] = "function-name";
```

其中 *function-name* 是**实现定义**的字符串。它是否与程序中其他对象的地址不同是**未指定**的（允许与内容相同的字符串字面量合并）。脚注：实现可以提供其他以保留名命名的预定义变量（如 GCC/Clang 的 `__PRETTY_FUNCTION__`、MSVC 的 `__FUNCSIG__`）；预定义变量若未被 odr-use，其字符串可以不出现在程序映像中。

```cpp run title="func.cpp" ok
#include <cstdio>
struct S {
    S() : s(__func__) { }        // OK：构造函数的 ctor-initializer 属于函数体
    const char* s;
};
template<class T> void tf() { std::puts(__func__); }
int main() {
    std::puts(__func__);         // Clang/GCC: "main"
    std::puts(S{}.s);            // Clang/GCC: "S"
    tf<int>();                   // Clang/GCC: "tf"（不含模板实参）
    [] { std::puts(__func__); }();   // Clang/GCC: "operator()"
    std::printf("%s\n", __PRETTY_FUNCTION__);   // 扩展："int main()"
}
```

标准例 2 还指出：`void f(const char* s = __func__);` 中的 `__func__` 未声明——默认实参不在函数形参作用域之"内"的函数体中，而是在命名空间作用域。（Clang 对此只给出警告 `-Wpredefined-identifier-outside-function`，不报错。）

!!! tip "`std::source_location`"
    C++20 的 `std::source_location::current().function_name()` 提供可移植的函数名（同样实现定义），且可以通过默认实参获取**调用者**的信息（[[dcl.fct.default#5]]），比 `__func__` 更适合日志。

## 显式预置的函数（[dcl.fct.def.default]）

### 哪些函数可以预置（¶1）

¶1 函数体为 `= default;` 的函数定义称为**显式预置的**（explicitly-defaulted）定义。显式预置的函数必须：

- ¶1.1 是**特殊成员函数**（[[special]]：默认构造、复制/移动构造、复制/移动赋值、析构）、**比较运算符函数**（[[class.compare.default]]：`==`、`<=>` 及由它们定义的 `!=`、`<` 等），或**后缀自增/自减运算符函数**（[[over.inc.default]]）；
- ¶1.2 没有默认实参。

!!! note "预置后缀 ++/--"
    允许 `C operator++(int) = default;`（按前缀 `++` 加复制实现后缀版本）是 C++26 之后才出现在草案中的新特性，Clang 23 尚不支持（"only special member functions and comparison operators may be defaulted"）。请编辑核对其确切版本归属。

### 与隐式声明的差异（¶2）

¶2 显式预置的特殊成员函数 F1 若与"本来会被隐式声明的"对应函数 F2 有差异，程序非良构，以下差异除外：

- ¶2.1 若 F1 是赋值运算符，可以有 `&` 引用限定符；
- ¶2.2 若 F2 是赋值运算符（其隐式对象参数类型为"`C` 的左值引用"），F1 可以改用类型为"`C` 的左值引用"的**显式对象参数**（`C& operator=(this C&, const C&) = default;`）；
- ¶2.3 异常规格可以不同；
- ¶2.4 若 F2 有类型为 `const C&` 的非对象形参，F1 对应形参可以是 `C&`；
- ¶2.5 若 F2 有类型为 `C&` 的非对象形参（因为某个成员或基类只能从非 const 左值复制），F1 可以是 `const C&`——**此时**，若 F1 在首次声明上预置，它被定义为**弃置的**；否则程序非良构。

```cpp title="default-mismatch.cpp" error
struct S {
    S(int a = 0) = default;               // error: 有默认实参
    void operator=(const S&) = default;   // error: 返回类型不匹配（应为 S&）
    ~S() noexcept(false) = default;       // OK：异常规格可以不同
private:
    int i;
    S(S&);                                // OK：私有的复制构造函数
};
S::S(S&) = default;                       // OK：定义复制构造函数（形参 S& 是 ¶2.4 允许的差异）

struct M { M(M&); };                      // 只能从非 const 左值复制
struct H  { M m; H(const H&) = default; };    // ¶2.5：首次声明预置 ⇒ 定义为弃置
struct H2 { M m; H2(const H2&); };
H2::H2(const H2&) = default;              // error: ¶2.5 中非首次声明的情形 ⇒ 非良构
```

!!! warning "C++26 之后的收紧 {{c++29}}"
    [[diff.cpp26.dcl]] 记录了一项与 C++26 不兼容的修改：预置的赋值运算符**不再允许** cv 限定符或 `&&` 引用限定符（¶2.1 现在只允许 `&`），预置的**移动**赋值运算符的形参也不再允许是 cv 限定的 `T&&`：

    ```cpp
    struct S { S& operator=(const S&) && = default; };       // 现在非良构；C++26 中良构
    struct T { T& operator=(const T&) const = default; };    // 现在非良构；C++26 中良构但弃置
    struct U { U& operator=(const U&&) = default; };         // 现在非良构；C++26 中良构但弃置
    ```

    理由是"移除少用且令人困惑的特性"。截至写作时 Clang 23 仍按 C++26 规则接受这三行（后两者给出"implicitly deleted"警告）。

### 隐式 inline 与 constexpr（¶3）

¶3 在**首次声明**上显式预置的函数是隐式 `inline` 的（[[dcl.inline]]），并且若满足 **constexpr-suitable**（[[dcl.constexpr]]）的条件，就是隐式 `constexpr` 的。注 1：其他预置函数（类外预置的）**不是**隐式 constexpr 的。

```cpp title="default-constexpr.cpp" error
struct C1 { int x; constexpr C1() : x(0) { } C1(const C1&) = default; };
constexpr C1 a;
constexpr C1 b = a;        // OK：首次声明预置的复制构造函数隐式 constexpr

struct C2 { int x; constexpr C2() : x(0) { } C2(const C2&); };
C2::C2(const C2&) = default;
constexpr C2 c;
constexpr C2 d = c;        // error: 类外预置的复制构造函数不是 constexpr
```

¶4（例）异常规格可以与隐式版本不同；标准例中 `U(U&&) noexcept = default;`，但成员 `T` 的移动构造函数可能抛出——那么 `U` 的移动构造函数在 `T::T(T&&)` 抛出时调用 `std::terminate`（noexcept 函数的通常语义）。

### 预置函数的定义时机与"用户提供"（¶5–6）

¶5 显式预置的函数与隐式声明的函数统称**预置函数**（defaulted functions）。实现为它们提供隐式定义（[[class.ctor]]、[[class.dtor]]、[[class.copy.ctor]]、[[class.copy.assign]]），可能定义为弃置的：

- 不是析构函数的预置**预期析构函数**（prospective destructor，C++20 起析构函数可以有多个带约束的候选）定义为弃置；
- 既不是预期析构函数、也不是**合格的**（eligible，[[special]]）特殊成员函数的预置特殊成员函数，定义为弃置。

**用户提供**（user-provided）的定义：用户声明的、且**没有在首次声明上**显式预置或弃置的函数。

| 写法 | 用户声明？ | 用户提供？ | 可能平凡？ |
|---|---|---|---|
| （不写） | 否 | 否 | 是 |
| 类内 `S() = default;` | 是 | **否** | 是 |
| 类内 `S();` + 类外 `S::S() = default;` | 是 | **是** | **否** |
| 类内 `S() = delete;` | 是 | 否 | — |
| 类内 `S() { }` | 是 | 是 | 否 |

用户提供的显式预置函数（即在首次声明之后预置的）**在预置处被隐式定义**；若它被隐式定义为弃置，程序非良构。注 2：在首次声明之后预置，可以在**保持稳定的二进制接口**的同时获得高效、简洁的定义——函数有一个"真正的"外部定义，以后可以换成手写实现而不改变头文件和 ABI。

非用户提供的预置函数（隐式声明的，或在类内预置的）若没有被定义为弃置，则在被 **odr-use** 或**常量求值需要**（[[expr.const.defns]]）时才隐式定义。注 3：非用户提供的预置函数的隐式定义不绑定任何名字。

```cpp title="user-provided.cpp" ok
#include <type_traits>
struct trivial {
    trivial() = default;                             // 首次声明预置：非用户提供
    trivial(const trivial&) = default;
    trivial(trivial&&) = default;
    trivial& operator=(const trivial&) = default;
    trivial& operator=(trivial&&) = default;
    ~trivial() = default;
};
struct nontrivial1 { nontrivial1(); };
nontrivial1::nontrivial1() = default;                // 非首次声明：用户提供

static_assert(std::is_trivially_default_constructible_v<trivial>);
static_assert(!std::is_trivially_default_constructible_v<nontrivial1>);
static_assert(std::is_trivially_copyable_v<trivial>);
int main() { }
```

"用户提供"的区分影响：平凡性（[[class.default.ctor]] 等）、值初始化时是否先零初始化（[[dcl.init]]：没有用户提供的默认构造函数时，值初始化先零初始化）、const 对象默认初始化是否需要初始化器（[[dcl.init]] 中的 const-default-constructible）。

```cpp title="user-provided-init.cpp" error
struct A { int x; A() = default; };
struct B { int x; B(); };
B::B() = default;

const A ca;      // error: A 不是 const-default-constructible（没有用户提供的默认构造函数，且 x 没有默认成员初始化器）
const B cb;      // OK：B 有用户提供的默认构造函数（虽然它什么也不做，cb.x 的值是错误值/不确定值）
```

## 弃置的定义（[dcl.fct.def.delete]）

### 什么是弃置函数（¶1）

¶1 函数的**弃置定义**（deleted definition）是函数体为 *deleted-function-body*（`= delete;` 或 `= delete("…");`）的定义，或者被定义为弃置的显式预置定义。**弃置函数**（deleted function）是具有弃置定义的函数，或被隐式定义为弃置的函数。

### 指代弃置函数即非良构（¶2）

!!! std
    A construct that designates a deleted function implicitly or explicitly, other than to declare it or to appear as the operand of a *reflect-expression*, is ill-formed.

    除了声明它、或作为 `^^` 的操作数之外，任何隐式或显式**指代**弃置函数的构造都是非良构的。

注 1 展开说明：

- 包括隐式或显式**调用**、**取地址**、形成成员指针；
- **即使在不潜在求值的表达式中**（`sizeof(f(1))`、`decltype(f(1))`）也非良构——这与"未定义的函数只要不 odr-use 就没事"截然不同；
- 对重载集合，只有**被重载决议选中的**函数算被指代——弃置函数**参与**重载决议，被选中才报错。这就是"用弃置重载屏蔽转换"的原理；
- 虚函数的隐式 odr-use 本身不构成指代（虚函数可以被弃置，只要从不调用）。

**推荐做法**（Recommended practice）：若提供了 *unevaluated-string*，诊断信息应包含其文本。注：这段字符串可以用来解释弃置的原因或建议替代方案。

```cpp title="delete-overload.cpp" error
void g(int) = delete("use g(long) to make the width explicit");   // C++26
void g(long) { }

void use() {
    g(1L);                  // OK
    g(1);                   // error: 选中了弃置的 g(int)；诊断中包含上面的字符串
    (void)sizeof(g(1));     // error: 即使在未求值操作数中
}
```

Clang 23 对 `g(1)` 的诊断形如 "call to deleted function 'g': use g(long) to make the width explicit"；对成员函数则形如 "attempt to use a deleted function: …"。

!!! note "为什么弃置函数要参与重载决议"
    若弃置函数不参与重载决议，`g(1)` 会悄悄选中 `g(long)`（整型转换）——这恰恰是作者想阻止的。弃置函数的本质是"**存在，但不许用**"：它占据重载集合中的位置，在它是最佳匹配时让调用失败。这与 C++03 中"声明为 private 且不定义"的老技巧不同：那种做法的错误要么是访问错误（类内调用时则推迟到链接期），而 `= delete` 在编译期给出精确的错误。

### 典型用法（¶3）

标准给出三个例子：

```cpp title="delete-uses.cpp" error
#include <cstddef>

struct onlydouble {                       // 1. 只允许用 double 初始化
    onlydouble() = delete;                // OK，但冗余（已有其他构造函数，不会隐式声明默认构造）
    template<class T> onlydouble(T) = delete;   // 模板比任何转换都更匹配非 double 实参
    onlydouble(double);
};
onlydouble b(1);                          // error: 选中弃置的模板 onlydouble<int>

struct sometype {                         // 2. 禁止在堆上创建
    void* operator new(std::size_t) = delete;
    void* operator new[](std::size_t) = delete;
};
sometype* p = new sometype;               // error: 弃置的类 operator new
sometype* q = new sometype[3];            // error: 弃置的类 operator new[]

struct moveonly {                         // 3. 只能移动，不能复制
    moveonly() = default;
    moveonly(const moveonly&) = delete;
    moveonly(moveonly&&) = default;
    moveonly& operator=(const moveonly&) = delete;
    moveonly& operator=(moveonly&&) = default;
    ~moveonly() = default;
};
moveonly* mp;
moveonly mq(*mp);                         // error: 弃置的复制构造函数
```

其他常见用法：`void f(std::nullptr_t) = delete;`（禁止传 `nullptr`）、`template<class T> void f(T*) = delete; void f(char*);`、禁止临时量绑定（`void ref(const T&&) = delete;`，标准库 `std::ref` 就是这样做的）。

### 弃置定义必须是首次声明（¶4）

¶4 弃置函数是隐式 `inline` 的（[[dcl.inline]]）。注 2：ODR 适用于弃置定义——各 TU 中必须一致。

弃置定义必须是函数的**首次声明**（对函数模板的显式特化，则是该特化的首次声明）。隐式声明的分配/解分配函数（[[basic.stc.dynamic]]，即全局 `operator new`/`delete`）不能定义为弃置。

```cpp title="delete-first.cpp" error
struct sometype { sometype(); };
sometype::sometype() = delete;    // error: 不是首次声明
```

为什么？如果允许先声明、后弃置，那么在弃置定义之前的调用点上编译器认为这个函数可用、生成了调用，到后面才发现它是弃置的——"指代即非良构"的规则就无法在每个使用点一致地执行。要求首次声明即弃置，使得每个能看到函数的地方都知道它是弃置的。

对显式特化的特殊处理允许"主模板正常、某个特化弃置"：

```cpp title="delete-spec.cpp" ok
template<class T> void process(T) { }
template<> void process<bool>(bool) = delete;   // OK：特化的首次声明
int main() { process(1); }
```

## 可替换函数定义（[dcl.fct.def.replace]）

¶1 某些由实现提供定义的函数是**可替换的**（replaceable）。C++ 程序可以提供一个签名与可替换函数相同的定义，称为**替换函数**（replacement function）；它代替实现提供的默认版本被使用。替换在**程序启动之前**发生（[[basic.def.odr]]、[[basic.start]]）——不是运行期的动态切换。

替换函数的声明必须：

- ¶1.1 不是 `inline` 的；
- ¶1.2 附属于**全局模块**（不能在具名模块中替换）；
- ¶1.3 具有 C++ 语言链接；
- ¶1.4 返回类型与可替换函数相同；
- ¶1.5 若该函数在标准库头文件中声明，它必须能作为那个声明的合法重声明。

违反任何一条：{{ifndr}}。

注 1：ODR 适用于程序提供的替换函数定义（整个程序只能有一个）；实现提供的定义是一个**没有名字、没有链接**的函数——所以替换函数与它不构成 ODR 冲突。

可替换函数的清单由各处的规定给出，最主要的是全局 `operator new`/`operator delete` 的各种形式（[[replacement.functions]]、[[new.delete]]）；C++26 的契约违反处理函数 `::handle_contract_violation` 也是可替换的（[[basic.contract.handler]]）。这一子条款是 C++26 草案中新增的，把原先分散在库条款中的"替换"规则提升为核心语言的统一机制。

```cpp run title="replace-new.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <new>

static int allocations = 0;

void* operator new(std::size_t n) {          // 替换函数：非 inline、全局模块、C++ 链接、返回类型相同
    ++allocations;
    if (void* p = std::malloc(n ? n : 1)) return p;
    throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

int main() {
    delete new int(1);
    std::printf("allocations: %d\n", allocations);   // 至少 1
}
```

为什么要求不能 `inline`？替换函数必须是程序中的**唯一**定义，且必须在程序启动前就"接管"所有调用（包括库内部、其他 TU 的调用）；`inline` 函数可以在多个 TU 中各有定义且可能被内联进调用点，与"全程序替换"的语义冲突。

## 实现视角

!!! impl
    - **`= default` 的代码生成**：首次声明预置的函数若平凡，编译器根本不生成函数（复制就是 `memcpy`，构造什么都不做）；类外预置的函数是一个真正的外部函数，即使函数体为空也有调用开销（除非 LTO 内联），并且使类型失去平凡性——这会影响 ABI：在 Itanium ABI 中，具有非平凡复制构造函数或析构函数的类型**不能通过寄存器传递**，而必须通过内存间接传递。
    - **`= delete`**：弃置函数不生成任何代码，也不产生符号。
    - **替换 `operator new`**：在链接器层面，通常表现为用户目标文件中的定义优先于运行库中的（弱）定义；使用共享库形式的 C++ 运行库时，还依赖动态链接器的符号介入（interposition）让库内部的调用也转到替换函数。
    - **`__func__`**：GCC 与 Clang 产出未修饰的函数名；MSVC 同样如此，且提供 `__FUNCSIG__` 给出完整签名。

## 历史与演进

!!! history
    - **C++98**：函数定义、函数 try 块；替换全局 `operator new`/`delete` 的规则在库条款中。
    - **C++11**：`= default` 与 `= delete`（[[N2346]]）；`__func__`（来自 C99）。
    - **C++14**：放宽 constexpr，使更多首次声明预置的函数可以隐式 constexpr。
    - **C++20**：可预置比较运算符 `==`、`<=>`（[[class.compare.default]]）；预期析构函数；预置特殊成员可以带显式对象参数的规则在 C++23 加入（¶2.2）。
    - **C++26**：`= delete("reason")`（[[P2573R2]]）；`dcl.fct.def.replace` 子条款；弃置函数可以作为 `^^` 的操作数（反射）。
    - **C++26 之后的草案**：预置赋值运算符不再允许 cv 与 `&&` 限定（[[diff.cpp26.dcl]]）；可预置后缀 `++`/`--`。

## 陷阱

!!! pitfall "类外 `= default` 使类型非平凡"
    `struct S { S(); }; S::S() = default;` 中 `S` 不再平凡默认可构造。若目的只是"不想在头文件中写实现"，这是对的；若想要平凡性（例如用于 `std::is_trivially_*` 优化或 C 互操作），应在类内预置。

!!! pitfall "预置不等于存在"
    `S(const S&) = default;` 可能被**定义为弃置**（成员不可复制时），且在类内预置时不报错，只有使用时才报错。Clang 的 `-Wdefaulted-function-deleted` 会提示这种情况。

!!! pitfall "弃置函数在 decltype/sizeof 中也报错"
    不能用 `decltype(f(x))` 来"探测"一个弃置重载的返回类型——即使不求值也非良构。在 SFINAE 语境中（模板实参推导的替换中），这会导致替换失败，这正是 `requires { f(x); }` 能检测到弃置函数的原因。

!!! pitfall "`= delete` 的位置"
    弃置定义必须在首次声明上：不能在头文件中声明 `void f(int);`，然后在 `.cpp` 中 `void f(int) = delete;`。

## 思考题

!!! question "思考题 1"
    下面哪些类型 `std::is_trivially_copyable_v` 为真？
    ```cpp
    struct A { A(const A&) = default; };
    struct B { B(const B&); };  B::B(const B&) = default;
    struct C { C(const C&) = delete; };
    struct D { D(const D&) = default; int& r; };
    ```

<details markdown="1">
<summary>答案</summary>

- `A`：真。复制构造函数在首次声明上预置，是平凡的。
- `B`：假。类外预置 ⇒ 用户提供 ⇒ 非平凡。
- `C`：真。平凡可复制要求"至少有一个合格的复制/移动操作，且所有合格的复制/移动操作与析构函数都平凡"（[[class.prop]]）。弃置的复制构造函数不合格（[[special]]）；移动操作因用户声明了复制构造函数而不被隐式声明；但复制赋值运算符仍被隐式声明为预置且平凡——于是有一个合格的平凡操作。一个不能复制构造的类型却是"平凡可复制"的，这是经典的反直觉结论。
- `D`：真。复制构造函数平凡；复制赋值因引用成员被定义为弃置（不合格），移动操作未声明；仍有平凡且合格的复制构造与析构，所以平凡可复制。
</details>

!!! question "思考题 2"
    为什么 `template<class T> onlydouble(T) = delete;` 能阻止 `onlydouble x(1.0f);`（`float`）？

<details markdown="1">
<summary>答案</summary>

重载决议中，模板 `onlydouble<float>(float)` 是精确匹配，而 `onlydouble(double)` 需要浮点提升；精确匹配优于提升（[[over.ics.rank]]），所以选中弃置的模板特化，调用非良构。只有实参恰好是 `double` 时，两者都是精确匹配，按"非模板优先"选中 `onlydouble(double)`。
</details>

## 小结

!!! summary
    | 主题 | 要点 |
    |---|---|
    | 函数定义 | 只能在命名空间或类作用域；参数/返回类型须完整、非抽象（弃置函数除外） |
    | `__func__` | 函数形参作用域中的 `static const char[]`；内容实现定义；默认实参中不可用 |
    | `= default` 适用 | 特殊成员、比较运算符、（草案新增）后缀 `++`/`--`；不能有默认实参 |
    | 与隐式声明的差异 | 允许 `&` 限定、显式对象参数、不同异常规格、`const` 与非 `const` 引用形参互换（有条件） |
    | 首次声明预置 | 隐式 inline、满足条件则隐式 constexpr、非用户提供、可平凡 |
    | 类外预置 | 用户提供、非平凡；在预置处定义，若会被弃置则非良构 |
    | `= delete` | 参与重载决议；被选中即非良构（含未求值操作数）；必须是首次声明；隐式 inline |
    | `= delete("…")` | C++26，理由文本进入诊断 |
    | 可替换函数 | 程序提供唯一定义，启动前替换；非 inline、全局模块、C++ 链接、返回类型相同 |
