---
title: 序言
summary: 类定义的语法（class-head、class-key、final）、注入类名、类在闭花括号处完整、带嵌套名说明符的类定义；以及类名规则：类定义引入新类型、详述类型说明符如何声明和引用类
status: draft
covers: class.name
related: class.mem, class.prop, dcl.type.elab, basic.lookup.elab, class.derived, class.access, class.qual
tags: 类, 注入类名, final, 详述类型说明符
updated: 2026-10-17
---

本节是第 11 章的入口，给出**类定义**（*class-specifier*）的语法骨架，以及围绕"类名"的一组基础规则。它要解决的问题看似朴素，却牵涉到名字查找和访问控制的很多边角：

- 类名在哪里被引入、从什么时候开始可用？
- 类自己的名字在类内部是什么身份？（**注入类名**，injected-class-name）
- 类什么时候算"完整"？
- 在类外定义嵌套类、类模板的成员类时，要满足什么条件？
- 当类名被同名的变量或函数遮蔽时，怎么指名这个类？（详述类型说明符 `struct X`，[[class.name]]）

本页一并覆盖 [[class.name]]（11.3 类名）。阅读前提：作用域与"栖身"（inhabit）的概念（[[basic.scope.scope]]）、详述类型说明符（[[dcl.type.elab]]）及其查找（[[basic.lookup.elab]]）。

## 类是一种类型（¶1）

¶1 开宗明义：**类是一个类型**。它的名字在其作用域内成为一个 *class-name*。*class-name* 在语法上是一个 *identifier* 或一个 *simple-template-id*（如 `vector<int>`）。

能"造出"类名的只有两种语法：

- *class-specifier*，即类定义 `struct X { ... };`；
- *elaborated-type-specifier*，即 `struct X;` 或 `struct X* p;` 里的 `struct X`（[[dcl.type.elab]]）。

一个类的对象由（可能为空的）**成员**和**基类对象**序列构成。

### class-specifier 的语法

```text
class-specifier:   class-head { member-specification(可选) }

class-head:        class-key 属性(可选) class-head-name class-property-specifier-seq(可选) base-clause(可选)
                   class-key 属性(可选) base-clause(可选)          ← 无名类

class-head-name:   nested-name-specifier(可选) class-name
class-property-specifier:  final
class-key:         class | struct | union
```

几个要点：

1. **class-key 只有三个**：`class`、`struct`、`union`。`class` 与 `struct` 的**唯一区别**是默认访问权限（成员和基类都是：`class` 默认 `private`，`struct` 默认 `public`，见 [[class.access]]）；`union` 则是一种完全不同的类（[[class.union]]）。¶4 是对此的注。
2. ***class-head-name* 可以带嵌套名说明符**（`struct N::X { ... };`），用于在外面定义已声明的嵌套类或命名空间成员类（¶3）。
3. ***class-property-specifier-seq***：当前草案中只有 `final` 一种。
4. **类名可以是 *simple-template-id***——但此时这个声明**必须**是显式特化或偏特化（`template<> struct A<int> {...}`、`template<class T> struct A<T*> {...}`）。你不能"顺便"用模板实参列表定义一个普通类。

### 无名类

省略 *class-head-name* 的 *class-specifier* 定义一个**无名类**（unnamed class）。注 1 的推论很直接：既然 `final` 必须跟在类名之后（*class-head* 的第二种形式里没有 *class-property-specifier-seq*），无名类不可能是 `final`。

```cpp run title="unnamed-class.cpp" ok
struct { int x, y; } pt;          // 无名类，同时声明变量 pt
typedef struct { int r, g, b; } Color;   // 无名类获得"用于链接的 typedef 名"
using Size = struct { int w, h; };       // 同上（alias-declaration 也可以）

int main() {
    pt.x = 1;
    Color c{1, 2, 3};
    Size s{4, 5};
    return pt.x + c.r + s.w - 6;
}
```

无名类的限制散落在别处：它不能有构造函数、析构函数（没有名字可以写 `~X()`），不能有静态数据成员（[[class.static.data#2]]）；`typedef struct {...} Color;` 中的 `Color` 是"用于链接目的的 typedef 名"（[[dcl.typedef]]），使这个类可以跨翻译单元一致地指名。

### 类名不被查找，而是被引入

¶1 最后一句：除了上面两种特殊情形（*simple-template-id*、带 *nested-name-specifier*），*class-name* 就是一个标识符，它**不被查找**，*class-specifier* **引入**它。这句话的意义在于：`struct X { ... };` 一定是在当前作用域引入（或重新声明）一个叫 `X` 的类，而不会因为外层作用域已经有一个 `X` 就去"补全"那个 `X`。

```cpp run title="introduce-not-lookup.cpp" ok
struct X { int a; };

namespace N {
    struct X { double d; };   // 在 N 中引入新的类 N::X，不是去定义 ::X
}

static_assert(sizeof(N::X) == sizeof(double));
int main() { }
```

## 注入类名（¶2 前半）

¶2：*class-name* 的组成名字（component name）**也被绑定在类（模板）自身的作用域中**，称为**注入类名**（injected-class-name）。也就是说，`struct X {}` 内部有一个隐式的"成员"`X`，它指代 `X` 本身。为了访问检查的目的，注入类名被当作一个 **public 成员名**。

为什么需要这个东西？

1. **在类内部，类名总能找到"自己"**，即使外层作用域里有同名的其他实体，或者类名被外部的 `using`/`typedef` 遮蔽。
2. **通过继承，基类的名字成为派生类作用域中可查找的成员**，`Derived::Base` 能找到基类。
3. **在类模板中，模板名本身可以当作当前特化使用**：`template<class T> struct L { L* next; };` 里的 `L` 就是 `L<T>`。

```cpp run title="injected-class-name.cpp" ok
#include <type_traits>

template<class T>
struct List {
    List* next;                 // 注入类名：List 即 List<T>
    List<int>* other;           // 也可以当模板名用，后接实参列表
    static_assert(std::is_same_v<List, List<T>>);
};

struct Base { int v = 1; };
struct Derived : Base {
    int f() { return Base::v; }  // Base 经由继承得到的注入类名找到
};

int main() {
    List<char> l{};
    Derived d;
    return d.f() - 1 + (l.next == nullptr ? 0 : 1);
}
```

### "public 成员"身份带来的陷阱

正因为注入类名是作为成员参与查找和访问检查的，**私有继承会让基类的注入类名在更深的派生类中不可访问**：

```cpp title="injected-private.cpp" error
struct A { };
struct B : private A { };
struct C : B {
    void f() { A a; }      // error: 查找到的是经由 B 继承来的 A 的注入类名，而 B 私有继承 A
    void g() { ::A a; }    // OK: 限定查找直接找到全局的 A
};
```

无限定查找 `A` 时，先在 `C` 的类作用域里搜索，沿基类找到 `B` 中继承来的 `A::A`（注入类名），这比全局作用域的 `::A` 先被找到；而它经由私有继承到达，不可访问（[[class.access.base]]）。Clang 的诊断说得很清楚：`'A' is a private member of 'A'`。修复方法就是写 `::A`。

### 注入类名有时指构造函数

在某些限定名语境下，`X::X` 不是指类型 `X`，而是指**构造函数**（[[class.qual]]）。因此：

```cpp title="ctor-name.cpp" error
struct D { };
D::D d;   // error: 在这里 D::D 指名的是构造函数，不是类型
```

这条规则（[[class.qual#1]]）使得 `X::X() { }` 这样的类外构造函数定义、以及 `using Base::Base;`（继承构造函数）能够被识别；它的代价是 `D::D` 在普通语境下不再是类型名。标准例子里给了两个绕法：`B::A ba;`（经派生类 `B` 指名基类 `A`，查找上下文不是 `A` 本身，所以是类型）和 `struct A::A a2;`（详述类型说明符只找类型）。

## 类在闭花括号处完整（¶2 中段）

*class-specifier* 通常被称为**类定义**（class definition）。¶2 规定：**一旦看到类定义的闭花括号 `}`，类就被视为已定义**——即使它的成员函数一般都还没有定义。

这条规则把"类型完整"与"成员函数已定义"解耦：编译器在 `}` 处就已经确定了类的大小、对齐、布局、所有成员的声明（包括隐式声明的特殊成员函数，[[special#1]]），之后任何需要完整类型的操作（`sizeof`、定义对象、访问成员）都可以进行。成员函数的定义可以在别的翻译单元里。

```cpp title="complete-at-brace.cpp" error
struct S;
S s1;                 // error: S 尚不完整

struct T {
    T* self;          // OK: 指向不完整类型的指针
    // T member;      // error: 类不能包含自身类型的成员（[class.mem] ¶20）
    static_assert(sizeof(T*) > 0);
    // static_assert(sizeof(T) > 0);   // error: T 在此处尚不完整
};
static_assert(sizeof(T) == sizeof(T*));  // OK: } 之后 T 完整
```

在类定义**内部**，类一般是不完整的；但在**完整类上下文**（函数体、默认实参、默认成员初始化器等）中，类被视为完整（[[class.mem.general#10]]、[[class.mem.general#11]]）。这就是成员函数体可以写 `sizeof(*this)` 的原因。

### 属性归属于类

¶2 最后一句：*class-head* 中可选的 *attribute-specifier-seq* 归属于类本身；此后**每次指名该类时**，这些属性都被视为类的属性。最典型的是 `[[deprecated]]`、`[[nodiscard]]` 和对齐说明符：

```cpp run title="class-attrs.cpp" ok
struct [[nodiscard]] Error { int code; };
struct alignas(64) CacheLine { char data[64]; };

Error make() { return {0}; }

int main() {
    static_assert(alignof(CacheLine) == 64);
    (void)make();           // 去掉 (void) 会得到 nodiscard 警告
}
```

## 带嵌套名说明符的类定义（¶3）

当 *class-head-name* 带有 *nested-name-specifier*（如 `struct N::X {...}`、`template<class T> struct A<T>::B {...}`）时：

1. **这样的 *class-specifier* 不能栖身于类作用域**。也就是说，不能在一个类里面用限定名定义另一个类的嵌套类；
2. 若 *class-name* 是标识符，*class-specifier* 必须**对应**（correspond，[[basic.scope.scope]]）于 *nested-name-specifier* 所指的类、类模板或命名空间中**可被指名的**一个或多个声明——即必须是"在外面补定义"，不能借此引入新名字；
3. 这些声明必须有同一个目标作用域，而 *class-specifier* 的目标作用域就是那个作用域。

```cpp title="qualified-class-def.cpp" error
namespace N {
    template<class> struct A { struct B; };
    struct C;
}
using N::A;
template<class T> struct A<T>::B { };   // OK: 定义 N::A<T>::B（可经 using 声明指名）
struct N::C { };                        // OK: 定义先前声明的 N::C
struct N::D { };                        // error: N 中没有可对应的 D 声明

struct E { struct F; };
struct G {
    struct E::F { };                    // error: 带限定名的类定义栖身于类作用域
};
```

第一行是标准例 1 的改编：`A<T>::B` 中的 `A` 通过 *using-declaration* 找到 `N::A`，这是允许的——"可被指名"（nominable）只要求名字能从那里被找到。

## class-key 的含义（¶4）

¶4 是注：*class-key* 决定类是不是联合体，以及默认访问是 public 还是 private。联合体在任一时刻至多持有一个数据成员的值。

!!! impl "struct 与 class 混用的 ABI 后果"
    标准允许先 `class X;` 再 `struct X { };`——*class-key* 不同的重声明是良构的（[[dcl.type.elab]] 只要求 `union` 与非 `union` 不混用）。Itanium ABI 的名字修饰不区分两者，但 **MSVC 的修饰名区分 `struct` 和 `class`**，混用可能导致链接错误。所以 Clang 有 `-Wmismatched-tags` 警告，MSVC 有对应的 C4099 警告。

## `final` 与上下文关键字（¶5–¶6）

¶5：每个 *class-property-specifier* 在一个序列里至多出现一次。`final` 不是保留关键字，而是**有特殊含义的标识符**（[[lex.name]]）。当 *class-key* 后跟 *class-head-name*、再跟标识符 `final`、再跟冒号或左花括号时，`final` 被解释为 *class-property-specifier*。

这条消歧规则处理的是确实存在的歧义（标准例 2 的改编）：

```cpp run title="final-disambig.cpp" ok
struct A;
struct A final { };     // 定义 struct A（final），不是"值初始化一个名叫 final 的 A 类型变量"

struct X {
    struct C { constexpr operator int() { return 5; } };
    struct B final : C { };   // 定义嵌套类 B（final），不是声明一个名叫 final、宽度为 C{} 的位域
};

struct final { };       // final 仍可以当普通标识符用
final f;

int main() { (void)f; }
```

第二个例子尤其精彩：`struct B final : C{};` 在语法上也可以读成"声明一个类型为 `struct B`、名为 `final` 的位域成员，宽度是 `C{}`（经转换函数得到 5）"。¶5 的规则一刀切：只要满足"类名 + `final` + `:`/`{`"的模式，就当作 `final` 说明符。

¶6：被标为 `final` 的类如果出现在 *base-clause* 中作为基类，程序非良构。

```cpp title="final-base.cpp" error
struct H final { };
struct I : H { };       // error: H 是 final 的
```

`final` 的用途：

- **表达设计意图**：这个类不是为继承而设计的（没有虚析构函数、没有受保护的扩展点）；
- **帮助去虚化**：对 `final` 类的对象（或指针）调用虚函数时，编译器知道不可能有更派生的覆盖者，可以直接调用；
- **与 `std::is_final` 配合**：标准库的某些实现利用 EBO（空基类优化）时需要从用户类型派生，若用户类型是 `final` 就必须换成成员存储，`std::is_final` 就是为此提供的。

!!! history "C++26 周期中的类属性说明符"
    `final` 从 C++11 起存在。C++26 周期中曾经通过 [[P2786]] 在 *class-property-specifier* 中加入 `trivially_relocatable_if_eligible` 与 `replaceable_if_eligible`（"平凡可重定位"相关），但后来在 2025 年的会议上被撤回。当前草案中 *class-property-specifier* 只剩 `final` 一种。

## 非零大小与类对象的基本操作（¶7–¶8）

¶7 注 3：类类型的**完整对象**大小非零。基类子对象和带 `[[no_unique_address]]` 的成员不受此约束（它们是**潜在重叠子对象**，[[intro.object]]）。这就是"空基类优化"（EBO）与 `[[no_unique_address]]` 能节省空间的依据：

```cpp run title="nonzero-size.cpp" ok
struct Empty { };
struct D : Empty { int x; };                         // 基类子对象可以零大小
struct M { [[no_unique_address]] Empty e; int x; };  // 同上（若实现支持）

static_assert(sizeof(Empty) >= 1);                    // 完整对象非零大小
static_assert(sizeof(D) == sizeof(int));              // 主流实现上 EBO 生效
int main() { return sizeof(M) == sizeof(int) ? 0 : 0; }
```

（`sizeof(D) == sizeof(int)` 是主流 ABI 的实际行为，标准本身并不保证 EBO 一定发生；`[[no_unique_address]]` 在 MSVC 上默认被忽略，需写 `[[msvc::no_unique_address]]`。）

为什么完整对象不能是零大小？因为**不同的对象必须有不同的地址**（[[intro.object]]），数组 `Empty a[10]` 的各元素需要可以区分；指针算术 `p + 1` 也要求元素大小非零。

¶8 注 4：类对象可以被赋值、作为实参传递、被函数返回（除非复制/移动被限制，[[dcl.fct.def.delete]]、[[class.access]]）；其他运算（如相等比较）可以由用户定义（[[over.oper]]），C++20 起也可以 `= default`（[[class.compare]]）。

---

# 类名（[class.name]）

## 类定义引入新类型（[class.name] ¶1）

[[class.name#1]]：**每个类定义引入一个新的类型**。这是 C++ 的**名义类型系统**（nominal typing）：两个结构完全相同的类也是不同的类型。

```cpp title="distinct-types.cpp" error
struct X { int a; };
struct Y { int a; };

int f(X);
int f(Y);          // 重载，不是重复声明

void g() {
    X a1;
    Y a2;
    int a3 = 0;
    a1 = a2;       // error: 不能把 Y 赋给 X
    a1 = a3;       // error: 不能把 int 赋给 X
}

struct S { int a; };
struct S { int a; };   // error: S 被定义两次
```

最后两行在同一个翻译单元里是重定义错误；在**不同**翻译单元里出现相同的定义则是允许的（ODR 的"定义可以出现在多个 TU 中"，[[basic.def.odr]]），条件是各定义满足 ODR 的一致性要求，否则 IFNDR。

## 用详述类型说明符指名被遮蔽的类（[class.name] ¶2）

[[class.name#2]] 是一个注，说明 C 遗留下来的"类名与变量/函数同名"情形。在 C 里，`struct stat` 和函数 `stat` 处在不同的"名字空间"（tag namespace）；C++ 把类名放进普通作用域，但为了兼容，允许同一作用域里**同一个名字既是类又是变量/函数/枚举项**——此时普通名字**遮蔽**类名，要指名类必须用**详述类型说明符**（*elaborated-type-specifier*），它做的是只考虑类型的查找（[[basic.lookup.elab]]）。

```cpp run title="stat.cpp" ok
struct stat { int size; };

stat gstat;                        // 此时 stat 只是类名，可以直接用

int stat(struct stat* p) { return p->size; }   // 现在 stat 也是函数名

int main() {
    struct stat s{42};             // 必须写 struct：无修饰的 stat 找到的是函数
    return stat(&s) - 42;          // 调用函数 stat
}
```

这正是 POSIX `<sys/stat.h>` 的真实情形：`struct stat` 和 `stat()` 函数同名。

### 用详述类型说明符声明类名

详述类型说明符也可以**声明**一个新的类名，例如块作用域里的 `struct s;` 会在该块中引入一个局部类 `s`，遮蔽外层的同名类：

```cpp run title="local-redecl.cpp" ok
struct s { int a; };

void g() {
    struct s;                 // 在块作用域声明新的类 s，遮蔽全局 s
    s* p = nullptr;           // 指向局部 s
    struct s { char* q; };    // 定义局部 s
    struct s;                 // 重声明，无效果
    (void)p;
}

int main() { g(); }
```

这种前置声明使相互引用的类成为可能：`class Vector;` 之后 `Matrix` 就可以在友元声明中使用 `Vector`。

!!! lawyer "形参列表中的 `struct Q*` 声明在哪里？"
    `void h(struct Q* q);` 中的 `struct Q` 如果无限定查找找不到 `Q`，就把 `Q` 声明为类名，其目标作用域是**最近的外围命名空间或块作用域**（[[dcl.type.elab#3]]），而不是函数形参作用域——所以之后在同一命名空间里写 `Q* qq;` 是合法的。C 的处理不同：C 中这样声明的结构体标签只有"函数原型作用域"，原型之外不可见，编译器常为此给出警告。

## 详述类型说明符引用已有类（[class.name] ¶3）

[[class.name#3]] 注 2：详述类型说明符也可以作为普通的 *type-specifier* 出现在声明中。它与类声明的区别在于：**它可以引用一个已有的同名类**，而不是总是引入新的。标准例 5：

```cpp run title="elab-refer.cpp" ok
struct s { int a; };

void g(int s) {
    struct s* p = new struct s;   // 全局的 struct s（形参 s 遮蔽了无修饰的名字）
    p->a = s;                     // 形参 s
    delete p;
}

int main() { g(1); }
```

## 声明在标识符之后立即生效（[class.name] ¶4）

[[class.name#4]] 注 3：类名的声明在类定义或详述类型说明符中**标识符一出现就生效**（[[basic.scope.pdecl]]）。标准举了一个"刁钻"的例子：

```cpp run title="class-A-star-A.cpp" ok
class A * A;     // 先把 A 声明为类，再把 A 重新声明为"指向该类对象的指针"变量

int main() {
    class A* p = A;   // 之后要指名这个类，只能写 class A
    (void)p;
}
```

标准自己也评价这种"名字艺术"容易让人困惑，最好避免。它的实际意义在于说明**声明点**的精确位置：`class A` 一读完，`A` 就是类名了，所以同一声明中的 `* A` 能看到它。

## simple-template-id 作为类名（[class.name] ¶5）

[[class.name#5]]：*simple-template-id* 只有在其模板名指名一个**类模板**时才是 *class-name*。别名模板的 *simple-template-id*（`template<class T> using V = vector<T>; V<int>`）是 *type-name*，但不是 *class-name*——这在需要 *class-name* 的语法位置（如 *class-head-name*、析构函数名 `~X`）上会有区别。

## 实现视角

!!! impl "注入类名与模板"
    在类模板内部，注入类名有双重身份：后面跟 `<` 时它是模板名（`List<int>`），否则是当前特化的类型（`List` 即 `List<T>`）。作为模板模板形参的实参时它被当作模板本身（[[temp.local]]）：若 `Foo` 接受一个模板模板形参，在 `List` 内部写 `Foo<List>` 传入的是模板 `List`，而不是类型 `List<T>`。GCC、Clang 都按这个规则实现；早期编译器在这里有大量不一致。

!!! impl "final 与去虚化"
    GCC 和 Clang 都会利用 `final`：若 `p` 的静态类型是 `final` 类 `F*`，`p->vf()` 直接调用 `F::vf`（或 `F` 继承来的最终覆盖者），无需查虚表；`final` 修饰的虚函数同理。GCC 还提供 `-Wsuggest-final-types` / `-Wsuggest-final-methods`，在 LTO 下提示哪些类型/方法加上 `final` 能带来去虚化收益。

## 历史与演进

!!! history "历史与演进"
    - **C++98**：类定义语法、注入类名、详述类型说明符的"tag 名"兼容规则都已存在；`struct`/`class` 唯一区别是默认访问。
    - **C++11**：引入 `final`（以及 `override`）作为上下文关键字；*class-head* 允许属性（`alignas`、`[[deprecated]]` 是后者 C++14 加入）。
    - **C++20**：模块使"完整性"的判定从"定义可见"变为"定义**可达**"（[[module.reach]]），见 [[class.mem.general#11]]。
    - **C++23 / C++26**：¶3 改用 "correspond"/"nominable"/"target scope" 等新的作用域术语重述（随 C++23 名字查找条款的重写而来）；C++26 周期中短暂加入又撤回了 `trivially_relocatable_if_eligible`/`replaceable_if_eligible`。

## 陷阱

!!! pitfall "私有继承后基类名“突然”不可访问"
    见上面 `injected-private.cpp`：在私有继承链下方的类里写无限定的基类名，找到的是不可访问的注入类名。用 `::A` 或完整的限定名。

!!! pitfall "`struct X;` 与 `class X {}` 混用"
    在标准层面合法，但在 MSVC 上可能导致链接错误。整个代码库对同一个类使用同一个 *class-key*。

!!! pitfall "以为类在定义内部就是完整的"
    `struct T { char buf[sizeof(T)]; };` 是非良构的；只有完整类上下文（函数体等）才能把类当作完整类型。

## 思考题

!!! question "思考题 1"
    下面每一行是什么？

    ```cpp
    struct A { };
    struct B final : A { };
    struct C { struct D { constexpr operator int() const { return 3; } }; struct E final : D { }; };
    struct final { };
    struct F : final { };
    ```

<details markdown="1">
<summary>答案</summary>

- `struct B final : A { };`：定义 `final` 类 `B`，派生自 `A`。
- `struct E final : D { };`：按 ¶5，`类名 final :` 的模式一律解释为 `final` 说明符，所以这是定义嵌套类 `E`（`final`），**不是**名为 `final`、宽度为 `D{}` 的位域。
- `struct final { };`：定义一个名叫 `final` 的普通类——`final` 不是保留字。
- `struct F : final { };`：`F` 派生自类 `final`。这里 `final` 前面是 `:` 而不是类名，不触发 ¶5 的消歧，它就是基类名。整个程序良构。
</details>

!!! question "思考题 2"
    为什么标准规定注入类名"为访问检查目的被视为 public 成员"，而不是干脆让它没有访问属性？

<details markdown="1">
<summary>答案</summary>

因为注入类名是通过**成员名字查找**（[[class.member.lookup]]）被找到的，查找到的东西需要一个确定的访问属性才能进行访问检查（[[class.access]]）。把它定为 public，意味着在类自身及公有派生类中它总是可访问的；只有经过非公有继承"降级"之后（[[class.access.base]]）才可能变得不可访问。如果它没有访问属性，私有继承就无法"隐藏"基类的身份，而私有继承的语义正是"派生关系是实现细节"。
</details>

!!! question "思考题 3"
    `template<class T> struct X; template<> struct X<int> { };` 合法，那么 `struct Y<int> { };`（`Y` 不是模板）呢？`template<class T> struct Z { }; struct Z<int> { };` 呢？

<details markdown="1">
<summary>答案</summary>

`struct Y<int> { };`：`Y` 不是模板名，`Y<int>` 根本不构成 *simple-template-id*，语法错误。

`struct Z<int> { };`：类名是 *simple-template-id*，按 ¶1 这样的声明必须是显式特化或偏特化，而它缺少 `template<>` 前缀，所以非良构。正确写法是 `template<> struct Z<int> { };`。
</details>

## 小结

| 规则 | 出处 | 要点 |
|---|---|---|
| 类是类型 | ¶1 | *class-specifier* 或 *elaborated-type-specifier* 引入类名；标识符形式的类名不被查找 |
| class-key | ¶1、¶4 | `class`/`struct` 只差默认访问；`union` 是另一种类 |
| 无名类 | ¶1 | 不能 `final`，无构造/析构函数，无静态数据成员 |
| 注入类名 | ¶2 | 类名也绑定在类作用域内，按 public 成员做访问检查 |
| 完整性 | ¶2 | 闭花括号之后即完整；类内仅完整类上下文视为完整 |
| 限定类名定义 | ¶3 | 不能栖身于类作用域；必须对应已有声明 |
| `final` | ¶5–¶6 | 上下文关键字；`类名 final :`/`{` 一律视为说明符；`final` 类不能做基类 |
| 新类型 | [class.name] ¶1 | 名义类型：结构相同也是不同类型 |
| 详述类型说明符 | [class.name] ¶2–¶3 | 指名被变量/函数遮蔽的类；可声明新类名或引用已有类 |
| 声明点 | [class.name] ¶4 | 标识符一出现即生效：`class A * A;` |
