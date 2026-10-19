---
title: 序言
summary: 类定义的写法（class、struct、union 与 final），类在闭花括号处完整，类名在类内部的身份（注入类名），在类外定义嵌套类的条件；以及类名规则：每个类定义引入一个新类型，被同名变量遮蔽的类要用 struct X 指名。
status: draft
covers: class.name
related: class.mem, class.prop, dcl.type.elab, basic.lookup.elab, class.derived, class.access, class.qual
tags: 类, 注入类名, final, 详述类型说明符
updated: 2026-10-19
---

!!! tldr
    - `class` 和 `struct` 只差默认访问权限：`class` 默认 private，`struct` 默认 public；`union` 是另一种类。
    - 类在定义的 `}` 处就完整了。在类内部，只有函数体、默认实参这类完整类上下文能把它当作完整类型。
    - 类名也作为一个 public 成员出现在类自己的作用域里，叫注入类名。私有继承之后，更深的派生类里写无限定的基类名可能不可访问。
    - `final` 不是保留字。只有出现在类名之后、紧跟 `:` 或 `{` 时，它才表示类不能被继承。
    - 两个结构相同的类是不同的类型。类名被同名的变量或函数遮蔽时，用 `struct X` 指名这个类。

## 类定义的写法（¶1、¶4）

```cpp run title="class-def.cpp" ok
struct Point { int x, y; };          // 成员默认 public
class Account {                       // 成员默认 private
    long balance = 0;
public:
    long get() const { return balance; }
};
union Value { int i; float f; };      // 同一时刻至多持有一个成员的值

int main() {
    Point p{1, 2};
    Account a;
    Value v{.i = 3};
    return p.x + int(a.get()) + v.i - 4;
}
```

¶1 类是一个类型，它的名字在所在作用域里成为一个**类名**（*class-name*）。能引入类名的语法只有两种：类定义 `struct X { ... };`，以及**详述类型说明符**（elaborated-type-specifier）`struct X;`、`struct X* p;` 里的 `struct X`（[[dcl.type.elab]]）。一个类对象由成员和基类子对象组成，这个序列可以为空。

类定义在语法上叫 *class-specifier*，骨架如下：

```text
class-specifier:  class-head { member-specification(可选) }
class-head:       class-key 属性(可选) class-head-name final(可选) base-clause(可选)
                  class-key 属性(可选) base-clause(可选)            ← 无名类
class-head-name:  nested-name-specifier(可选) class-name
class-key:        class | struct | union
```

¶4 *class-key* 决定两件事（这一段是注）：类是不是联合体（[[class.union]]），以及成员和基类的默认访问是 public 还是 private（[[class.access]]）。`class` 和 `struct` 之间没有别的区别。

*class-head-name* 有两种不寻常的形式。带嵌套名说明符的 `struct N::X { ... }` 用来在外面定义已经声明过的类，见下文 ¶3。写成模板实参列表的 `A<int>` 只能出现在显式特化或偏特化里，如 `template<> struct A<int> { ... };`，不能用来定义普通类。

### 无名类

省略类名的类定义定义一个**无名类**（unnamed class）。`final` 只能跟在类名后面，所以无名类不可能是 `final` 的（注 1）。

```cpp run title="unnamed-class.cpp" ok
struct { int x, y; } pt;                 // 无名类，同时声明变量 pt
typedef struct { int r, g, b; } Color;   // Color 是用于链接的 typedef 名
using Size = struct { int w, h; };       // alias-declaration 也可以

int main() {
    pt.x = 1;
    Color c{1, 2, 3};
    Size s{4, 5};
    return pt.x + c.r + s.w - 6;
}
```

无名类写不出 `~X()`，所以不能声明构造函数和析构函数，也不能有静态数据成员（[[class.static.data#2]]）。`typedef struct {...} Color;` 里的 `Color` 是用于链接目的的 typedef 名（[[dcl.typedef]]），各翻译单元靠它指名同一个类。

### 类名由定义引入，不经过查找

¶1 最后一句规定，除了上面两种特殊形式，类名就是一个标识符：它不经过名字查找，而是由类定义引入。所以 `struct X { ... };` 总是在当前作用域里引入或重新声明一个 `X`，不会因为外层已经有一个 `X` 就去补全那个 `X`。

```cpp run title="introduce-not-lookup.cpp" ok
struct X { int a; };

namespace N {
    struct X { double d; };   // 引入新的类 N::X，不是定义 ::X
}

static_assert(sizeof(N::X) == sizeof(double));
int main() { }
```

## 类在闭花括号处完整（¶2）

```cpp title="complete-at-brace.cpp" error
struct S;
S s1;                     // error: S 尚不完整

struct T {
    T* self;              // OK：指向不完整类型的指针
    char buf[sizeof(T)];  // error: T 在这里还不完整
    int f() { return sizeof(T); }   // OK：函数体是完整类上下文
};
static_assert(sizeof(T*) > 0);
```

¶2 类定义（*class-specifier* 通常就叫类定义）的闭花括号一出现，类就被视为已定义，即使它的成员函数一般还没有定义。到这里，编译器已经确定了类的大小、对齐、布局和全部成员的声明，包括隐式声明的特殊成员函数（[[special#1]]）。成员函数的定义可以放在别的翻译单元。

在类定义内部，类一般是不完整的。例外是**完整类上下文**：函数体、默认实参、默认成员初始化器、`noexcept` 说明符等，在那里类被视为完整（[[class.mem.general#10]]、[[class.mem.general#11]]）。所以成员函数体里可以写 `sizeof(T)`，数据成员的声明里不行。

### 写在 class-head 上的属性属于类

¶2 最后一句：*class-head* 里的属性归属于类本身，此后每次指名这个类都带着这些属性。

```cpp run title="class-attrs.cpp" ok
struct [[nodiscard]] Error { int code; };
struct alignas(64) CacheLine { char data[64]; };

Error make() { return {0}; }

int main() {
    static_assert(alignof(CacheLine) == 64);
    (void)make();           // 去掉 (void) 会得到 nodiscard 警告
}
```

## 注入类名（¶2）

```cpp run title="injected-class-name.cpp" ok
#include <type_traits>

template<class T>
struct List {
    List* next;                 // List 就是 List<T>
    List<int>* other;           // 后面跟 <，就当模板名用
    static_assert(std::is_same_v<List, List<T>>);
};

struct Base { int v = 1; };
struct Derived : Base {
    int f() { return Base::v; } // Base 经由继承得到的注入类名找到
};

int main() {
    List<char> l{};
    Derived d;
    return d.f() - 1 + (l.next == nullptr ? 0 : 1);
}
```

¶2 类名也绑定在类（或类模板）自身的作用域里，这叫**注入类名**（[[g:injected-class-name|injected-class-name]]）。可以把它想成每个类都有一个隐式的成员 `X`，指代 `X` 本身。做访问检查时，它被当作 public 成员名。

这样规定有三个好处。在类内部，类名总能找到类自己，不受外层同名实体的影响。经过继承，基类名成为派生类作用域里可以查找的成员，所以 `Derived` 里可以写 `Base::v`。在类模板里，模板名本身就表示当前特化，`List` 就是 `List<T>`。

### 私有继承让基类名不可访问

注入类名既然是成员，就和其他成员一样受继承方式影响：

<div class="compare" markdown="1">

```cpp error
struct A { };
struct B : private A { };
struct C : B {
  void f() { A a; }
  // error: 找到的是 B 继承来的
  //   注入类名 A，而 B 私有继承 A
};
```

```cpp run ok
struct A { };
struct B : private A { };
struct C : B {
  void f() { ::A a; (void)a; }
  // OK：限定名直接找到全局的 A
};
int main() { C{}.f(); }
```

</div>

在 `C` 的成员函数里无限定地查找 `A`，先在 `C` 的类作用域里沿基类搜索，找到 `B` 继承来的注入类名 `A`。它比全局的 `::A` 先被找到，而它经由私有继承到达，因此不可访问（[[class.access.base]]）。Clang 的诊断是 `'A' is a private member of 'A'`。

### `X::X` 指的是构造函数

```cpp title="ctor-name.cpp" error
struct D { };
D::D d;   // error: 这里 D::D 指名的是构造函数，不是类型
```

在查找上下文是类 `C` 的限定名里，`C::C` 指名的是构造函数而不是注入类名（[[class.qual#1]]）。正是这条规则让编译器能识别类外的构造函数定义 `X::X() { }` 和继承构造函数 `using Base::Base;`。代价是 `D::D` 在普通语境下不再是类型名。需要类型时可以写 `struct D::D`，因为详述类型说明符只找类型。

## 在类外定义嵌套类（¶3）

```cpp title="qualified-class-def.cpp" error
namespace N {
    template<class> struct A { struct B; };
    struct C;
}
using N::A;
template<class T> struct A<T>::B { };  // OK：定义 N::A<T>::B
template<> struct A<void> { };         // OK：显式特化
struct N::C { };                       // OK：定义先前声明的 N::C
struct N::D { };                       // error: N 里没有 D 的声明

struct E { struct F; };
struct G {
    struct E::F { };                   // error: 不能写在类作用域里
};
```

¶3 类名带嵌套名说明符时（`struct N::C { }`），有三条限制：

1. 这个类定义不能位于类作用域里，不能在一个类内部用限定名定义另一个类的成员类；
2. 它必须对应（[[basic.scope.scope]]）嵌套名说明符所指的类、类模板或命名空间里已有的声明。换句话说，限定名只能给已有声明补上定义，不能借此引入新名字；
3. 这些声明要有同一个目标作用域，类定义的目标作用域就是它。

前两行改编自标准例 1。嵌套名说明符本身怎样找到都可以：`A<T>::B` 里的 `A` 经 using 声明找到 `N::A`。条文要求的只是 `N::A<T>` 里有一个可被指名（nominable）的 `B` 的声明，也就是在此之前、目标作用域就是这个类的声明。

## `final`（¶5、¶6）

```cpp run title="final-disambig.cpp" ok
struct A;
struct A final { };     // 定义 final 类 A，不是值初始化一个名叫 final 的变量

struct X {
    struct C { constexpr operator int() { return 5; } };
    struct B final : C { };   // 定义 final 嵌套类 B，不是位域
};

struct final { };       // final 仍可以当普通标识符用
final f;

int main() { (void)f; }
```

¶5 `final` 不是保留字，而是有特殊含义的标识符（[[lex.name]]）。规则是：*class-key* 后面依次跟着类名、标识符 `final`、冒号或左花括号时，`final` 就解释为类属性说明符。一个类上 `final` 最多写一次。

这条规则消除了真实存在的歧义。上例的 `struct B final : C { };` 在语法上也能读成：声明一个类型为 `struct B`、名叫 `final` 的位域，宽度是 `C{}` 经转换函数得到的 5。按 ¶5，只要符合类名、`final`、`:` 或 `{` 的模式，就一律当作 `final` 说明符。

¶6 把 `final` 类写在基类列表里，程序非良构：

```cpp title="final-base.cpp" error
struct H final { };
struct I : H { };       // error: H 是 final 的
```

`final` 表明这个类不是为继承设计的。它还能帮助编译器去虚化：通过 `final` 类的指针或引用调用虚函数时，不可能有更派生的覆盖者，可以直接调用。标准库里需要从用户类型派生以利用空基类优化的地方，会先用 `std::is_final` 检查，`final` 类就改用成员存储。

!!! impl "去虚化与 `-Wsuggest-final-types`"
    GCC 和 Clang 都会利用 `final`：静态类型为 `F*`（`F` 是 `final` 类）时，`p->vf()` 直接调用最终覆盖者，不查虚表。GCC 的 `-Wsuggest-final-types`、`-Wsuggest-final-methods` 在 LTO 下会提示哪些类型或函数加上 `final` 能带来去虚化收益。

## 完整对象的大小非零（¶7）

```cpp run title="nonzero-size.cpp" ok
struct Empty { };
struct D : Empty { int x; };                         // 基类子对象可以不占空间
struct M { [[no_unique_address]] Empty e; int x; };  // 同上

static_assert(sizeof(Empty) >= 1);                   // 完整对象大小非零
int main() { return sizeof(D) == sizeof(int) ? 0 : 1; }
```

¶7 这一段是注：类类型的完整对象大小不为零。基类子对象和带 `[[no_unique_address]]` 的成员不受这条限制，它们是潜在重叠子对象（[[intro.object]]）。空基类优化（EBO）就以此为依据。

完整对象不能是零大小，是因为不同的对象必须有不同的地址，`Empty a[10]` 的十个元素要能区分，指针算术 `p + 1` 也要求元素大小非零。标准不保证 EBO 一定发生，`sizeof(D) == sizeof(int)` 是主流 ABI 的实际行为。MSVC 默认忽略 `[[no_unique_address]]`，要写 `[[msvc::no_unique_address]]`。

## 每个类定义引入一个新类型 [class.name]

```cpp title="distinct-types.cpp" error
struct X { int a; };
struct Y { int a; };

int f(X);
int f(Y);          // 重载，不是重复声明

void g() {
    X a1;
    Y a2;
    a1 = a2;       // error: 不能把 Y 赋给 X
}

struct S { int a; };
struct S { int a; };   // error: S 被定义两次
```

[[class.name#1]] 每个类定义引入一个新的类型。C++ 的类型系统是名义的：两个结构完全相同的类也是不同的类型，可以分别作为重载的形参类型。

同一个翻译单元里把 `S` 定义两次是重定义错误。不同翻译单元里各有一份相同的定义则是允许的，头文件里的类定义就是这样被包含进多个源文件的；各份定义不一致时违反 ODR（[[basic.def.odr]]）。

### 用 `struct X` 指名被遮蔽的类

```cpp run title="stat.cpp" ok
struct stat { int size; };

stat gstat;                        // 此时 stat 只是类名，可以直接用

int stat(struct stat* p) { return p->size; }   // stat 现在也是函数名

int main() {
    struct stat s{42};             // 必须写 struct：只写 stat 找到的是函数
    return stat(&s) - 42;          // 调用函数 stat
}
```

[[class.name#2]] C 把结构体标签放在单独的名字空间里，`struct stat` 和函数 `stat` 互不干扰。C++ 把类名放进普通作用域，但为了兼容 C，允许同一作用域里同一个名字既是类又是变量、函数或枚举项。这时普通名字遮蔽类名，要指名类就得写详述类型说明符 `struct stat`，它执行只考虑类型的查找（[[basic.lookup.elab]]）。POSIX 的 `<sys/stat.h>` 正是这种情形。

详述类型说明符还可以声明新的类名。块作用域里的 `struct s;` 引入一个局部类，遮蔽外层的同名类：

```cpp run title="local-redecl.cpp" ok
struct s { int a; };

void g() {
    struct s;                 // 声明局部类 s，遮蔽全局 s
    s* p = nullptr;           // 指向局部 s
    struct s { char* q; };    // 定义局部 s
    struct s;                 // 重声明，无效果
    (void)p;
}

int main() { g(); }
```

前置声明 `class Vector;` 之后，`Matrix` 就能在友元声明里使用 `Vector`，两个类可以互相引用。

[[class.name#3]] 用在普通声明里时，`struct s` 也可以指一个已有的类，而不是引入新类：

```cpp run title="elab-refer.cpp" ok
struct s { int a; };

void g(int s) {
    struct s* p = new struct s;   // 全局的 struct s（形参 s 遮蔽了普通名字）
    p->a = s;                     // 形参 s
    delete p;
}

int main() { g(1); }
```

!!! lawyer "形参列表里的 `struct Q*` 声明在哪里"
    对 `void h(struct Q* q);`，如果无限定查找找不到 `Q`，就把 `Q` 声明为类名，目标作用域是最近的外围命名空间或块作用域（[[dcl.type.elab#3]]），而不是形参作用域。所以之后在同一命名空间里写 `Q* qq;` 是合法的。C 的规则不同：这样声明的结构体标签只在函数原型内有效，编译器常为此警告。

### 声明在标识符之后立即生效

```cpp run title="class-A-star-A.cpp" ok
class A * A;     // 先把 A 声明为类，再把 A 声明为指向该类对象的指针变量

int main() {
    class A* p = A;   // 之后要指名这个类，只能写 class A
    (void)p;
}
```

[[class.name#4]] 类名的声明在标识符出现之后立即生效（[[basic.scope.pdecl]]）。所以读完 `class A`，`A` 就已经是类名，同一声明里的 `* A` 再把 `A` 声明为变量。标准也说这种写法容易让人困惑，最好避免。

[[class.name#5]] 只有模板名指名类模板时，`T<...>` 才是类名。别名模板 `template<class T> using V = std::vector<T>;` 的 `V<int>` 是类型名，但不是类名，不能出现在要求类名的位置，比如类定义的 *class-head-name*。

<details class="fine" markdown="1"><summary>其余条文</summary>

¶8 是注：类对象可以被赋值、作为实参传递、作为返回值，除非复制或移动被删除或不可访问（[[dcl.fct.def.delete]]、[[class.access]]）。相等比较等其他运算可以由用户定义（[[over.oper]]），C++20 起也可以 `= default`（[[class.compare]]）。

</details>

!!! impl "struct 与 class 混用的 ABI 后果"
    先写 `class X;` 再写 `struct X { };` 是良构的，[[dcl.type.elab]] 只禁止 `union` 与非 `union` 混用。Itanium ABI 的名字修饰不区分两者，MSVC 的修饰名却区分 `struct` 和 `class`，混用可能导致链接错误。Clang 为此有 `-Wmismatched-tags` 警告，MSVC 有 C4099。

## 历史与演进

!!! history
    - C++98 已有类定义语法、注入类名，以及兼容 C 标签名的详述类型说明符规则；`struct` 与 `class` 只差默认访问。
    - C++11 引入上下文关键字 `final`，*class-head* 上可以写属性。
    - C++20 的模块把类是否完整从定义是否在前面改成定义是否可达（[[module.reach]]，见 [[class.mem.general#11]]）。
    - C++26 的工作中曾在 `final` 旁边加入与平凡可重定位相关的两个类属性说明符（[[P2786]]），后来撤回。当前草案中类属性说明符只有 `final`。

## 常见误解

!!! pitfall "类在自己的定义里是完整的"
    `struct T { char buf[sizeof(T)]; };` 是非良构的。只有函数体、默认实参等完整类上下文才把类当作完整类型。

!!! pitfall "`struct X;` 和 `class X { }` 可以随便混用"
    在标准层面合法，在 MSVC 上可能导致链接错误。同一个类在整个代码库里应当用同一个 *class-key*。

## 思考题

!!! question "思考题 1"
    下面每一行在做什么？整个程序良构吗？

    ```cpp
    struct A { };
    struct B final : A { };
    struct C { struct D { constexpr operator int() const { return 3; } }; struct E final : D { }; };
    struct final { };
    struct F : final { };
    ```

<details markdown="1">
<summary>答案</summary>

- `struct B final : A { };` 定义 `final` 类 `B`，派生自 `A`。
- `struct E final : D { };` 符合类名、`final`、`:` 的模式，按 ¶5 是定义 `final` 嵌套类 `E`，不是宽度为 `D{}` 的位域。
- `struct final { };` 定义一个名叫 `final` 的普通类，`final` 不是保留字。
- `struct F : final { };` 里 `final` 前面是 `:` 而不是类名，不触发 ¶5，它就是基类名。

整个程序良构。
</details>

!!! question "思考题 2"
    为什么注入类名在访问检查中被当作 public 成员，而不是干脆没有访问属性？

<details markdown="1">
<summary>答案</summary>

注入类名是通过成员名字查找（[[class.member.lookup]]）找到的，找到的东西需要一个确定的访问属性才能做访问检查（[[class.access]]）。定为 public，意味着在类本身和公有派生类里它总是可访问的；经过非公有继承降低访问级别之后（[[class.access.base]]），它才可能不可访问。私有继承要把派生关系当作实现细节隐藏起来，这正需要基类名也随之变得不可访问。
</details>

!!! question "思考题 3"
    `template<class T> struct Z { }; struct Z<int> { };` 合法吗？`struct Y<int> { };`（`Y` 不是模板）呢？

<details markdown="1">
<summary>答案</summary>

`struct Z<int> { };` 的类名是 *simple-template-id*，按 ¶1 这样的声明必须是显式特化或偏特化。它缺少 `template<>`，所以非良构，应写成 `template<> struct Z<int> { };`。

`struct Y<int> { };` 里 `Y` 不是模板名，`Y<int>` 根本构不成 *simple-template-id*，是语法错误。
</details>
