---
title: 类型识别（typeid）
summary: typeid 的结果是一个生命周期贯穿程序的 const std::type_info 左值；多态 glvalue 操作数被求值并取动态类型，其他操作数是未求值操作数并取静态类型；对空指针的 *p 抛 std::bad_typeid；顶层 cv 与引用被忽略；必须先声明 std::type_info
status: draft
papers: P1327R1
related: expr.dynamic.cast, type.info, bad.typeid, class.cdtor, class.virtual, expr.context, class.temporary, basic.def.odr, std.modules
tags: RTTI, 多态, 未求值操作数
updated: 2026-10-17
---

`typeid` 是 C++ 的运行期类型识别（RTTI）的另一半（另一半是 [[expr.dynamic.cast]]）。它把一个表达式或类型映射到一个 `std::type_info` 对象，可以比较是否相等、取（实现定义的）名字、作为 `std::type_index` 放进关联容器。

本节规则不多，但有三处值得 language lawyer 注意：

1. **操作数是否被求值取决于它的类型**——多态类的 glvalue 会被求值，其他情况都不求值。这是 C++ 里唯一一个"是否求值取决于操作数类型"的运算符。
2. **空指针解引用**在这里不是 UB，而是抛异常——但只限于语法上**直接**写成 `*p` 的形式。
3. 不包含 `<typeinfo>`（或不导入 `std`）就使用 `typeid` 是**非良构**的。

## 结果（¶1）

¶1：`typeid` 表达式的结果是一个**左值**，静态类型为 `const std::type_info`（[[type.info]]），动态类型为 `const std::type_info` 或某个**实现定义的**、公有派生自 `std::type_info` 的类（脚注 46 推荐命名为 `extended_type_info`）。它引用的对象的**生命周期延续到程序结束**；程序结束时是否调用这个 `type_info` 对象的析构函数是**未指定**的。

推论：

- 可以安全地保存 `const std::type_info&` 或 `const std::type_info*`，它们永远不会悬垂；
- `std::type_info` 不可复制（复制构造与复制赋值被删除），所以只能持有引用或指针，或者包装为 `std::type_index`；
- **同一类型多次 `typeid` 得到的对象不一定是同一个**——标准只保证 `operator==` 比较相等，而不保证 `&typeid(T) == &typeid(T)`。

## 类必须完整（¶2）

¶2：若 *expression* 或 *type-id* 操作数的类型是（可能 cv 限定的）类类型或其引用，该类必须**完整定义**。指向不完整类的**指针**没问题——`typeid(I*)` 识别的是指针类型。

```cpp title="typeid-incomplete.cpp" error
#include <typeinfo>

struct I;

void f(I* p) {
    (void)typeid(I*);    // OK：指针类型
    (void)typeid(p);     // OK：表达式类型是 I*
    (void)typeid(I);     // error: 类不完整
    (void)typeid(*p);    // error: 表达式类型 I 不完整
}
```

## 多态 glvalue：动态类型（¶4）

¶4：`typeid` 作用于**多态类类型**（[[class.virtual]]）的 **glvalue** 时，结果引用的 `type_info` 代表该 glvalue 所指的**最派生对象**的类型（即动态类型）。

为此必须在运行期读取对象——所以这种情况下操作数是**潜在求值**的（[[expr.context]] 与 [[basic.def.odr]] 都把"多态类 glvalue 的 `typeid` 操作数"排除在未求值操作数之外）。

## 其他操作数：静态类型，不求值（¶5）

¶5：`typeid` 作用于**多态类 glvalue 以外**的表达式时，结果代表表达式的**静态类型**。此时：

- **不**施行左值到右值、数组到指针、函数到指针转换——所以 `typeid` 能区分数组类型和函数类型；
- 若表达式是 prvalue，施行**临时量实质化转换**（[[conv.rval]]）；
- 表达式是**未求值操作数**。

```cpp run title="typeid-eval.cpp" ok
#include <typeinfo>

struct P { virtual ~P() = default; };
struct Q : P {};
struct N {};

int calls = 0;
P& get_poly() { ++calls; static Q q; return q; }
N& get_plain() { ++calls; static N n; return n; }

int main() {
    const std::type_info& a = typeid(get_poly());    // 多态 glvalue：被求值，get_poly() 被调用
    const std::type_info& b = typeid(get_plain());   // 非多态：未求值，get_plain() 不被调用
    int arr[3];
    bool c = typeid(arr) == typeid(int[3]);          // 不做数组到指针转换
    return (calls == 1 && a == typeid(Q) && b == typeid(N) && c) ? 0 : 1;
}
```

Clang 对第一种情况会给出 `-Wpotentially-evaluated-expression` 警告（"expression with side effects will be evaluated despite being used as an operand to 'typeid'"），因为很多人误以为 `typeid` 的操作数从不求值。

!!! lawyer "prvalue 的实质化与析构函数"
    ¶5 对 prvalue 施行临时量实质化，而 [[class.temporary#1]] 规定：即使临时对象的创建是未求值的，也必须满足"如同创建并销毁了临时对象"的全部语义限制——包括析构函数可访问且未被删除。所以对一个析构函数被删除的类 `S`，`typeid(S())` 按标准是**非良构**的（唯一的豁免是 `decltype` 的操作数）。截至写作时，本机 Clang 接受 `typeid(S())` 而不报错，这是 Clang 与标准的一个分歧。

## 对空指针的 `*p`：抛 `std::bad_typeid`（¶3）

¶3：若 *expression* 操作数是一个**（可带括号的）一元 `*` 表达式**，且其操作数求值为**空指针值**，`typeid` 表达式抛出能被 `std::bad_typeid`（[[bad.typeid]]）处理器捕获的异常。注 1：在其他语境中，这样的 `*` 表达式是 UB（[[expr.unary.op]]）。

```cpp run title="bad-typeid.cpp" ok
#include <typeinfo>

struct P { virtual ~P() = default; };

int main() {
    P* p = nullptr;
    try {
        (void)typeid(*p);       // 抛 std::bad_typeid（而不是 UB）
        return 1;
    } catch (const std::bad_typeid&) {}
    try {
        (void)typeid((*p));     // 带括号也算
        return 1;
    } catch (const std::bad_typeid&) {}
    return 0;
}
```

为什么要特殊对待？因为对多态 glvalue，`typeid` 必须读 vptr，而对空指针读 vptr 必然崩溃。标准选择在**语法上**识别最常见的形式 `typeid(*p)`，让实现在读 vptr 之前插入一次空指针检查。这个豁免是**语法性的**，范围非常窄：

```cpp title="bad-typeid-narrow.cpp" ub
#include <typeinfo>

struct P { virtual ~P() = default; P& self() { return *this; } };

int main() {
    P* p = nullptr;
    (void)typeid(p->self());   // UB: 不是 "* 表达式" 的形式；p->self() 先对空指针调用成员函数
    (void)typeid(*&*p);        // UB: 最外层是 *，但它的操作数 &*p 的求值里已经对空指针做了 *
}
```

第二行的道理：¶3 只豁免**最外层**那个 `*`；内层的 `*p` 是普通的一元 `*`，对空指针求值是 UB。另外，对**非多态**类型，`typeid(*p)` 是未求值操作数，`*p` 根本不会被求值，所以既不抛异常也不是 UB——只是返回静态类型。

## `type-id` 操作数（¶6）与 cv 的忽略（¶7）

¶6：`typeid(type-id)` 的结果代表该类型；若是**引用类型**，结果代表**被引用类型**（去掉 cv）。注 2：*type-id* 不能是带 cv 限定符或引用限定符的函数类型（`typeid(void() const)` 非良构）。

¶7：若表达式或 *type-id* 的类型带**顶层 cv 限定**，结果代表 **cv 去除**的类型。

标准例 1 的四行全部为 `true`：

```cpp run title="typeid-cv.cpp" ok
#include <typeinfo>

class D {};
D d1;
const D d2;

int main() {
    bool ok = typeid(d1) == typeid(d2)            // true
           && typeid(D) == typeid(const D)        // true
           && typeid(D) == typeid(d2)             // true
           && typeid(D) == typeid(const D&);      // true
    // 只去掉"顶层" cv：指针所指类型的 cv 是类型的一部分
    bool diff = typeid(int*) != typeid(const int*);
    static_assert(typeid(int) == typeid(const volatile int&));   // C++23 起 type_info::operator== 是 constexpr
    return (ok && diff) ? 0 : 1;
}
```

为什么去掉 cv 和引用？因为 `typeid` 的典型用途是"这个对象是什么类型"——`const` 与否、通过引用还是直接访问，都不改变对象的类型。这与模板实参推导中按值推导时的退化相似，但 `typeid` 不做数组/函数退化。

## 必须先声明 `std::type_info`（¶8）

¶8：`std::type_info` **不是预定义的**；若在 `typeid` 表达式之前，没有可达的标准库声明（来自 `<typeinfo>` 或标准库模块 `std`，[[std.modules]]），程序**非良构**。

```cpp title="typeid-no-header.cpp" error
int main() {
    return typeid(int) == typeid(int);   // error: 未包含 <typeinfo>，也未 import std
}
```

这是语言与库耦合的少数地方之一（类似的还有 `std::initializer_list`、`<=>` 需要 `<compare>`、协程需要 `<coroutine>`）。Clang 的诊断会直接提示"you need to include <typeinfo> or import std"。

## 构造与析构期间（¶9）

¶9 是注，指向 [[class.cdtor#5]]：在构造函数或析构函数中（或从它们直接/间接调用的函数中），若 `typeid` 的操作数指向**正在构造/析构的对象**，结果是**构造函数/析构函数所属类**的 `type_info`。若操作数的静态类型既不是该类也不是其基类，行为未定义。

```cpp run title="typeid-ctor.cpp" ok
#include <typeinfo>

struct B {
    virtual ~B() = default;
    B() { in_ctor = &typeid(*this); }
    const std::type_info* in_ctor;
};
struct D : B {};

int main() {
    D d;
    return (*d.in_ctor == typeid(B) && typeid(d) == typeid(D)) ? 0 : 1;
}
```

## 常量求值

C++20 起（[[P1327R1]]），多态 `typeid` 可用于常量表达式（只要对象的动态类型在常量求值中已知）；C++23 起 `std::type_info::operator==` 是 `constexpr`。所以 `static_assert(typeid(x) == typeid(Y))` 在编译期可以判定。若对象的动态类型是"constexpr 未知"的（例如引用形参所指的对象），则不是常量表达式（[[expr.const.core]]）。

## 实现视角

!!! impl
    - **Itanium ABI**：每个多态类的虚表中，vptr 前一个字是指向其 `type_info` 对象（`__class_type_info` 及其派生类）的指针；`typeid(*p)` 编译为"检查空指针 → 读 vptr → 读 vptr[-1]"。非多态和 `typeid(T)` 则直接引用编译期确定的 `_ZTI...` 符号。
    - **名字**：`type_info::name()` 的结果由实现定义。GCC/Clang 返回 Itanium 改编名（`1D`、`PKi`），可用 `abi::__cxa_demangle` 还原；MSVC 返回可读的名字（`class D`）。不要依赖 `name()` 的内容做逻辑判断，它不保证唯一，也不保证可读。
    - **相等比较**：在类型 `type_info` 对象全局唯一的平台上比较指针即可；某些平台（尤其涉及动态库、符号可见性时）需要比较名字字符串。
    - **`-fno-rtti`**：GCC/Clang 在关闭 RTTI 时拒绝 `typeid`（Clang："use of typeid requires -frtti"），也不生成多态类的 `type_info`。
    - **MSVC** 的 `/GR-` 类似；MSVC 的 RTTI 结构（Complete Object Locator 等）与 Itanium 不同，但语义相同。

## 历史与演进

!!! history
    - **C++98**：`typeid` 与 `std::type_info` 一同标准化；`type_info::before()` 提供实现定义的排序。
    - **C++11**：增加 `type_info::hash_code()` 和 `std::type_index`，便于放入无序容器；`type_info` 的复制操作明确为删除的。
    - **C++20**：多态 `typeid` 可用于常量表达式（[[P1327R1]]）。
    - **C++23**：`type_info::operator==` 成为 `constexpr`。
    - **C++23**：引入标准库模块 `std`（[[std.modules]]），¶8 中 `std::type_info` 的声明也可以由 `import std;` 提供。

## 陷阱

!!! pitfall "以为 `typeid` 的操作数不求值"
    `typeid(*make_shape())` 中，若 `make_shape()` 返回指向多态类的指针，函数会被调用；若对返回的引用调用，同理。对非多态类型则不会。同一段代码，加一个虚函数后行为就变了。

!!! pitfall "对非多态类型 `typeid(*base_ptr)` 只给出静态类型"
    基类没有虚函数时，`typeid(*p)` 永远是基类类型，与对象实际是什么无关。要得到动态类型，基类至少要有一个虚函数（通常是虚析构函数）。

!!! pitfall "比较 `name()` 或 `&typeid(T)`"
    用 `strcmp(a.name(), b.name())` 或比较 `type_info` 的地址来判断类型相等都不可移植。应当用 `operator==` 或 `std::type_index`。

## 思考题

!!! question "思考题 1"
    `struct P { virtual ~P(); }; P* f();` 下，`sizeof(typeid(*f()))` 会调用 `f` 吗？`noexcept(typeid(*f()))` 的值是什么？

<details markdown="1">
<summary>答案</summary>

`sizeof` 的操作数是未求值操作数，它的所有子表达式也都不求值，所以不会调用 `f`——`typeid` 内部"多态 glvalue 被求值"只在 `typeid` 表达式本身被求值时才有意义。`noexcept(typeid(*f()))`：表达式包含一个潜在抛出的 `typeid`（对多态类的 `*p` 形式可能抛 `std::bad_typeid`，见 [[except.spec]]），以及对 `f`（未声明 `noexcept`）的调用，结果为 `false`。
</details>

!!! question "思考题 2"
    `int a[3]; typeid(a) == typeid(int*)` 与 `typeid(+a) == typeid(int*)` 分别是什么？

<details markdown="1">
<summary>答案</summary>

`typeid(a)`：¶5 不做数组到指针转换，类型是 `int[3]`，与 `int*` 不等，结果 `false`。`+a`：一元 `+` 要求算术或指针操作数，`a` 先退化为 `int*`，结果是 `int*` 的 prvalue，所以 `typeid(+a) == typeid(int*)` 为 `true`。
</details>

## 小结

!!! summary
    | 操作数 | 是否求值 | 结果代表 |
    |---|---|---|
    | 多态类类型的 glvalue | 求值 | 动态类型（最派生对象的类型） |
    | 可带括号的 `*p`，`p` 为空且类型多态 | 求值 | 抛 `std::bad_typeid` |
    | 其他表达式 | 不求值；无数组/函数退化；prvalue 实质化 | 静态类型 |
    | *type-id* | — | 该类型，去引用、去顶层 cv |
    | 构造/析构中的对象 | | 当前构造/析构函数所属的类 |

    另外：结果是 `const std::type_info` 左值，生命周期到程序结束；类须完整；须先声明 `std::type_info`。
