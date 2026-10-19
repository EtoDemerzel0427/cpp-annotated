---
title: 名字查找
summary: 名字查找把源码中一个名字的使用对应到一组声明；本页讲查找的结果怎么用（重载决议与访问检查在它之后）、查找能看到哪些声明（程序点与先于，包括模块）、最基本的单次搜索，以及类名被同名变量或函数隐藏的规则。
status: done
covers: basic.lookup.general
papers: P1787R6
related: class.member.lookup, basic.lookup.unqual, basic.lookup.argdep, basic.lookup.qual, basic.lookup.elab, basic.lookup.udir, basic.scope.scope, basic.scope.pdecl, over.match, class.access, temp.res
tags: 名字查找, 作用域, 模块
updated: 2026-10-19
---

!!! tldr
    - 名字查找把一个名字的使用对应到一组声明。结果全是函数时叫重载集，交给重载决议；否则这些声明必须指同一个实体，不然查找有二义，程序非良构。
    - 处理顺序是固定的：查找，然后重载决议，然后访问检查。`private` 不会让名字从查找中消失，也不会让重载决议退而选择别的函数。
    - 查找只能找到先于使用处的声明。对模块来说，导入的命名空间成员要被导出才算先于；类成员只要类的定义可达就算。
    - 同一作用域里，类名与变量或函数同名时，类名被隐藏，要写 `struct X` 才能指那个类型。
    - 所有查找规则都建立在单次搜索之上：在一个作用域里找出绑定到这个名字、并且先于使用处的声明。

编译器每遇到一个名字，`x`、`std::vector`、`operator+`、`~T`，都要先确定它指的是哪个或哪些声明，这一步叫**名字查找**（name lookup）。查找的结果决定了后面的一切：`a < b > c` 是比较还是模板实参列表（[[temp.names]]），表达式是什么类型，调用哪个函数。

第 6.5 节由一个总框架（本页）和若干具体规则组成：

| 条款 | 回答的问题 |
|---|---|
| [[class.member.lookup]] | 在类作用域里找名字时，怎样把各个基类里找到的结果合并起来？ |
| [[basic.lookup.unqual]] | 不带 `::` 的名字从哪里开始、按什么顺序向外找？using 指令怎么参与？ |
| [[basic.lookup.argdep]] | 调用 `f(x)` 时，`x` 的类型怎样把别的命名空间也拉进来（ADL）？ |
| [[basic.lookup.qual]] | `A::m`、`p->B::m` 中 `::` 后面的名字在哪里找？ |
| [[basic.lookup.elab]] | `struct X` 里的 `X` 怎么找？ |
| [[basic.lookup.udir]] | `using namespace N;`、`namespace A = N;` 里的 `N` 怎么找？ |

本页用到作用域的几个术语：声明**栖居**（[[g:inhabit]]）于某个作用域，它的名字**绑定**在目标作用域中；声明从**声明点**（[[g:locus]]）开始生效。它们的定义见 [[basic.scope]]。

## 查找之后：重载决议与访问检查（¶1）

```cpp run error
struct B { void f(int); };
struct D : B {
private:
    void f(double);        // 隐藏 B::f
};

class X {
public:  void g(double);
private: void g(int);
};

void t() {
    D d;
    d.f(1);   // error: 查找只找到私有的 D::f，B::f 被隐藏
    X x;
    x.g(1);   // error: 重载决议选中 g(int)，访问检查失败
}
```

两处调用都有一个看起来可用的公有函数，但都出错。原因在于名字的处理顺序。

¶1 名字查找把名字的一次使用对应到这个名字的一组声明（[[basic.def]]）。规则对所有名字一视同仁，typedef 名、命名空间名、类名都一样，只是有些语境会过滤结果（见下文第 4 段）。除非另有规定，什么也没找到就是非良构。

找到的声明如果全是函数或函数模板，就叫一个**重载集**（[[g:overload-set]]），之后由重载决议（[[over.match]]、[[over.over]]）从中选一个。否则，如果找到的声明不都指同一个实体，查找就是**二义的**（ambiguous），程序非良构。经由两条路径找到同一个变量不算二义（[[namespace.qual#2]]）。

!!! std
    The access rules ([class.access]) are considered only once name lookup and function overload resolution (if applicable) have succeeded.

访问检查在查找和重载决议都成功之后才进行。之后，声明带来的语义性质（类型、是否 `constexpr`、`[[deprecated]]` 等）才被使用。所以一个名字的处理顺序是：

| 步骤 | 规则 | 结果 |
|---|---|---|
| 1. 名字查找 | [basic.lookup] | 一组声明 |
| 2. 重载决议（结果是重载集时） | [[over.match]] | 一个函数 |
| 3. 访问检查 | [[class.access]] | 能否使用 |
| 4. 使用声明的性质 | 各条款 | 类型、值类别等 |

回到上面的例子。`d.f(1)`：在 `D` 中查找 `f` 找到私有的 `D::f(double)`，派生类的声明隐藏了 `B::f`（[[class.member.lookup]]），`B::f` 根本不是候选；随后访问检查失败。`x.g(1)`：两个 `g` 都是候选，重载决议选中精确匹配的 `g(int)`，随后访问检查失败，编译器不会退而选择 `g(double)`。

这是有意的设计：访问控制只决定能不能用，不决定找到的是谁。把一个成员从 `public` 改成 `private`，程序要么含义不变，要么报错，不会悄悄改调另一个函数。同一段代码在类内和类外找到的也总是同样的声明。

找不到就非良构的另有规定，常见的有：

- 调用 `f(x)` 时，即使普通查找什么也没找到，ADL 仍可能找到函数（[[basic.lookup.argdep]]）；
- `f<T>(x)` 中，普通查找什么也没找到时，`f` 仍按模板名解析（[[temp.names]]，C++20 起）；
- `struct X* p;` 找不到 `X` 时会声明一个新类（[[dcl.type.elab]]）；
- 不带限定的友元声明 `friend void f();` 不做查找（[[dcl.meaning.general#2]]）。

## 查找能看到哪些声明：程序点与先于（¶2）

¶2 为了精确描述一个声明在使用处之前，标准定义了**程序点**（[[g:program-point]]）：翻译单元第一个记号之前有一个程序点，每两个相邻记号之间至少有一个，最后一个记号之后有一个。

如果同一翻译单元中某个声明的声明点在程序点 P 之前，就说 P **跟随**（follows）这个声明。注 1 提醒，这个声明可以在一个不包含 P 的作用域里；跟随只看文本先后，作用域由查找算法另外处理。

声明 X **先于**（[[g:precedes]]）翻译单元 L 中的程序点 P，是指下列情况之一：

1. P 跟随 X；
2. X 栖居于类作用域，并且从 P 可达（reachable，[[module.reach]]）；
3. X 在另一个翻译单元 D 中，并且同时满足：
    - ¶2.1 P 跟随一个直接或间接导入 D 的模块导入声明或模块声明；
    - ¶2.2 X 在 D 的模块声明之后、私有模块片段之前；
    - ¶2.3 X 被导出了；或者 D 与 L 属于同一个模块，并且 X 既不栖居于具有内部链接的命名空间，也不声明具有内部链接的名字。

先于是旧教材中可见这个说法的精确版本，所有查找都只找先于使用处的声明。对单个翻译单元来说，它就是声明出现在前面；第 2、3 条是为模块准备的。

第 2 条的意思是，类成员不需要导出，只要类的定义可达，成员就能被找到。一个模块可以不导出类名，只导出返回这个类对象的函数，导入者拿到对象之后照样能访问成员：

```cpp title="m.cppm"
export module M;
struct S { int x = 1; };          // S 没有导出
export S make() { return {}; }
```

```cpp title="use.cpp" error
import M;
int main() {
    auto s = make();
    int v = s.x;    // OK：S::x 栖居于类作用域，S 的定义从这里可达
    S s2;           // error: S 栖居于命名空间作用域且没有导出，不先于这里
    return v;
}
```

本机 Clang 23 对 `S s2;` 报告 unknown type name 'S'，删掉这一行后编译通过。

注 2 补充，using 声明引入的名字没有链接，所以第 2.3 项关于内部链接的排除不会影响它们。注 3 说明导入是传递的：模块 R 中有 `export import Q;`，导入 R 时也就导入了 Q。

!!! lawyer "可达与先于"
    可达关心的是声明的语义性质能不能用，例如类是否完整；先于关心的是名字查找能不能找到它。一个声明可以可达而不先于：间接导入的模块接口单元，它的声明可能可达（[[module.reach#1]]），但其中命名空间作用域的名字查找不到。类成员是例外，可达即先于。

## 单次搜索（¶3）

¶3 定义了一切查找的基本操作，**单次搜索**（[[g:single-search]]）：

!!! std
    A single search in a scope S for a name N from a program point P finds all declarations that precede P to which any name that is the same as N is bound in S.

在作用域 S 中、从程序点 P 出发对名字 N 做单次搜索，找出 S 中绑定了与 N 相同的名字、并且先于 P 的所有声明。分开来看：

- 只看 S 这一个作用域，不往外层找，也不往基类找。名字绑定在哪个作用域由 [[basic.scope.scope#2]] 决定，那里列出的例外在这里都起作用，例如友元声明不绑定名字，块作用域的函数声明把名字绑定在块里。
- 名字相同：标识符按字符序列比较；转换函数名 `operator T` 按类型是否相同比较（[[basic.pre#4]]）。
- 如果找到的是一个 using 声明符，并且它指名的名字不是依赖的，就把它替换成它所指的那些声明（[[namespace.udecl]]）。所以查找结果里出现的是原来的声明，`using N::f;` 引入的 `f` 和 `N::f` 是同一个实体，不会造成二义。

```cpp run ok
namespace N { int v = 1; void f(int); }
namespace M { using N::v; using N::f; void f(double); }

using namespace N;
using namespace M;

void t() {
    v = 2;       // OK：经 N 和经 M 的 using 声明找到的都是 N::v
    f(1);        // OK：重载集 {N::f(int), M::f(double)}，选 N::f(int)
}
```

其他查找都由单次搜索组合而成：

| 操作 | 定义处 | 做什么 |
|---|---|---|
| 单次搜索 | 本页第 3 段 | 只看一个作用域 |
| 搜索 | [[class.member.lookup#1]] | 非类作用域就是单次搜索；类作用域还要沿基类合并结果 |
| 无限定搜索 | [[basic.lookup.unqual#2]] | 搜索一个作用域，连同在那里生效的 using 指令；找不到就去父作用域 |
| 限定名字查找 | [[basic.lookup.qual#3]] | 在 `::` 前指定的类、命名空间或枚举中搜索 |
| 实参依赖查找（ADL） | [[basic.lookup.argdep]] | 在实参类型的关联命名空间中搜索 |

## 类名被同名实体隐藏（¶4）

```cpp run error
struct stat { long st_size; };
int stat(const char* path, struct stat* buf);   // 与类同名的函数：合法

void t() {
    struct stat s;          // OK：struct stat 只考虑类型
    stat("/tmp", &s);       // OK：找到类和函数，类被丢弃，指函数
    stat s2;                // error: stat 在这里指函数
}
```

C 语言把结构体标签和普通标识符放在不同的名字空间里，`struct stat` 和函数 `stat` 可以共存，POSIX 正是这样用的。C++ 把类名放进了普通作用域，为了让这类代码继续工作，规定类名会被同一作用域中的其他实体隐藏。

¶4 有些语境只接受某几种声明。例如 `::` 前面的标识符，查找时只考虑命名空间、类型和特化为类型的模板（[[basic.lookup.qual#1]]）。经过这样的过滤之后，还有一条通用规则：

!!! std
    any declarations of classes or enumerations are discarded if any other declarations are found.

只要还找到了其他声明，类和枚举的声明就被丢弃。注 4 由此得出：类型会被同一作用域中的任何其他实体隐藏。这条规则只丢弃类和枚举的声明，类型别名和模板不会被这样丢弃。别名与变量本来也不能在同一作用域同名，那是冲突的重声明（[[basic.scope.scope#6]]）。

这条规则只作用于一次搜索的结果。经由 using 指令从不同的命名空间分别找到一个类和一个变量时，类不会被丢弃，查找有二义（[[namespace.qual#4]] 的注 3、[[namespace.udir#7]]）。

### 仅类型查找

¶4 后半段定义了**仅类型查找**（[[g:type-only-lookup]]）：只考虑类型，以及特化为类型的模板。此外，如果同时找到了一个类型别名和它所指的类型，丢弃的是别名。用到仅类型查找的地方有：

- `struct X`、`enum E` 这类详述类型说明符中的名字（[[basic.lookup.elab]]）；
- 基类列表中的类名（[[class.derived.general]]）。

为什么丢弃别名而保留类型？详述类型说明符不能指名 typedef 名（[[dcl.type.elab#6]]），别名和原类型都找到时，必须留下原类型，`struct X` 才能合法：

<div class="compare" markdown="1">

```cpp run ok
namespace A { struct X {}; }
namespace B { using X = A::X; }
using namespace A;
using namespace B;
struct X* p;  // 丢弃别名，留下 A::X
X* q;         // 两者是同一实体
```

```cpp run error
struct S {};
typedef S T;
struct T* p;
// error: 只找到别名 T，
// 详述类型说明符不能指名
// typedef 名
```

</div>

## 模板中的查找

模板定义里的名字分成依赖名和非依赖名（[[temp.dep]]）：

- 非依赖名在模板定义处查找并绑定（[[temp.res]]）；
- 依赖的函数调用 `g(t)`（`t` 的类型依赖于模板形参）分两步：普通的无限定查找在定义处进行，ADL 在定义处和实例化处都进行（[[temp.dep.candidate]]、[[basic.lookup.argdep#4]]）；
- 无限定查找不会进入依赖基类（[[class.member.lookup#4]]），所以要写 `this->f()`。

```cpp run error
template<class T> void call(T t) { g(t); }   // 定义处找不到 g
void g(int);                                  // 在模板定义之后才声明
int main() { call(1); }   // error: 实例化时只做 ADL，int 没有关联命名空间
```

如果把 `int` 换成某个命名空间里的类类型，并把 `g` 声明在同一个命名空间里，ADL 就能在实例化处找到它。ADL 能用作模板的定制点，依据就在这里。

## 实现视角

!!! impl "编译器怎么做"
    - Clang 用 `LookupResult` 记录查找结果的种类：没找到、找到一个声明、找到重载集、依赖情形下暂时无法确定、二义。重载决议和访问检查是之后单独的步骤，正好对应第 1 段规定的顺序。
    - 对上面两阶段查找的例子，Clang 23 报告 call to function 'g' that is neither visible in the template definition nor found by argument-dependent lookup。MSVC 在 `/permissive-` 之前长期没有实现两阶段查找，会接受这段代码。
    - "did you mean …" 之类的拼写纠错发生在查找失败之后，不影响程序的含义。

## 历史与演进

!!! history
    - C++20 及以前，标准用声明区、潜在作用域和可见来描述查找。内层声明隐藏外层声明有专门的条款，无限定查找是一张按场景罗列的清单（命名空间成员函数里的名字、成员函数体里的名字、友元函数里的名字……）。每出现一种新语法就要追加一条，条与条之间积累了不少漏洞。
    - C++23 由 [[P1787R6]] 改为今天的模型：可见换成了先于，以便处理模块；隐藏不再需要单独的规则，无限定搜索在内层找到就停下（[[basic.lookup.unqual#2]]）；场景清单换成沿作用域树向外搜索的一个算法。大多数代码的含义没有变化，但许多旧文本没有覆盖或互相矛盾的边角情况有了确定的答案。
    - C++26 的静态反射为 `std::meta::info` 增加了 ADL 的特殊规则（[[basic.lookup.argdep#3]]），并允许拼接（splice）出现在 `::` 之前（[[basic.lookup.qual#1]]）。

## 常见误解

!!! pitfall "private 能把名字藏起来"
    私有成员照样参与查找和重载决议，照样隐藏基类的同名成员。想让某个重载对外不可用，应该用 `= delete` 或约束，而不是 `private`。

!!! pitfall "查找成功就一定能用"
    即使 `d.x` 的查找没有二义，从 `d` 转换到 `x` 所在的基类仍可能有二义，程序照样非良构（[[class.member.lookup#11]]、[[expr.ref]]）。

!!! pitfall "找到两个同名函数就是二义"
    两个命名空间各有一个函数 `f`，经 using 指令同时找到，这不是二义：它们组成重载集，交给重载决议。只有结果里有非函数（变量、类型等），并且不都指同一个实体时，查找才是二义的。

## 思考题

!!! question "思考题 1"
    下面的 `d.f(0)` 调用哪个函数？如果删掉 `private:` 呢？
    ```cpp
    struct B { void f(long); };
    struct D : B {
        using B::f;
    private:
        void f(int);
    };
    void t(D& d) { d.f(0); }
    ```

<details markdown="1">
<summary>答案</summary>

在 `D` 中查找 `f`，找到 using 声明（替换为 `B::f(long)`）和 `D::f(int)`，组成重载集。重载决议对实参 `0` 选择精确匹配的 `D::f(int)`，随后访问检查失败，程序非良构。删掉 `private:` 之后，调用的是 `D::f(int)`。访问说明符不会让重载决议改选 `B::f(long)`。
</details>

!!! question "思考题 2"
    `struct X {}; int X;` 之后，`sizeof(X)` 指什么？`sizeof(struct X)` 呢？

<details markdown="1">
<summary>答案</summary>

`sizeof(X)`：查找找到类 `X` 和变量 `X`，按第 4 段丢弃类，指的是变量，结果是 `sizeof(int)`。`sizeof(struct X)`：仅类型查找只考虑类型，结果是类 `X` 的大小 1。
</details>

!!! question "思考题 3"
    为什么第 2 段规定栖居于类作用域、可达的声明就先于 P，而不要求类成员也被导出？

<details markdown="1">
<summary>答案</summary>

`export` 只作用于命名空间作用域的声明，类成员没有单独导出的概念。成员能否使用，应该取决于类的定义是否可达，因为这决定了类是否完整、布局是否已知。否则模块就无法只导出工厂函数而隐藏类名，同时又让使用者访问对象的成员。
</details>
