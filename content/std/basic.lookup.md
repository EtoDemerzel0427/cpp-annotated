---
title: 名字查找
summary: 名字查找把名字的一次出现映射为一组声明。本页讲 C++23 起的新模型（程序点、先于、单次搜索、搜索、仅类型查找）、整条处理流水线（查找 → 重载决议 → 访问检查）以及隐藏与二义性。
status: done
covers: basic.lookup.general
papers: P1787R6
related: class.member.lookup, basic.lookup.unqual, basic.lookup.argdep, basic.lookup.qual, basic.lookup.elab, basic.lookup.udir, basic.scope.scope, basic.scope.pdecl, over.match, class.access, temp.res
tags: 名字查找, 作用域, 模块
updated: 2026-10-17
---

编译器在源码里每遇到一个名字，如 `x`、`std::vector`、`operator+`、`~T`，都必须回答一个问题：它指的是哪个或哪些声明？这一步叫**名字查找**（name lookup）。它是语义分析的第一道工序。没有查找的结果，编译器连 `a < b > c` 是比较还是模板实参列表都无法决定（[[temp.names]]），更谈不上类型检查、重载决议与代码生成。

第 6.5 节 [basic.lookup] 由一个总体框架和若干专门规则组成：

| 子条款 | 回答的问题 | 本站页面 |
|---|---|---|
| [basic.lookup.general] 6.5.1 | 查找的结果是什么？何时算找到、何时二义？什么叫单次搜索？ | 本页 |
| [class.member.lookup] 6.5.2 | 在类作用域里搜索一个名字时，怎样沿基类格（lattice）合并结果？ | [[class.member.lookup]] |
| [basic.lookup.unqual] 6.5.3 | 不带限定的名字从哪个作用域开始、按什么顺序往外找？using 指令如何参与？ | [[basic.lookup.unqual]] |
| [basic.lookup.argdep] 6.5.4 | 函数调用 `f(x)` 中，`x` 的类型如何把额外的命名空间拉进来（ADL）？ | [[basic.lookup.argdep]] |
| [basic.lookup.qual] 6.5.5 | `A::m`、`p->B::m` 中，`::` 后的名字在哪里找？ | [[basic.lookup.qual]] |
| [basic.lookup.elab] 6.5.6 | `struct X` 里的 `X` 怎么找？ | [[basic.lookup.elab]] |
| [basic.lookup.udir] 6.5.7 | `using namespace N;`、`namespace A = N;` 里的 `N` 怎么找？ | [[basic.lookup.udir]] |

读本节前需要先熟悉作用域（scope）的新术语：作用域、栖居（inhabit）、目标作用域（target scope）、名字绑定（bind）到声明，见 [[basic.scope.scope]]；以及声明的声明点（locus），见 [[basic.scope.pdecl]]。

## 为什么要了解新模型：C++23 的重写

如果你的 C++ 知识来自较早的教材（或 C++20 及以前的标准），你对名字查找的理解大概是这样的：

- 每个名字有一个声明区（declarative region）和潜在作用域（potential scope）；
- 内层作用域的声明会隐藏（hide）外层的同名声明（旧 [basic.scope.hiding]）；
- 名字在某点可见（visible），当且仅当它在作用域内且未被隐藏；
- [basic.lookup.unqual] 是一张长长的清单，如“在命名空间成员函数定义中使用的名字……”、“在类 X 的成员函数定义中，在函数体之后使用的名字……”、“在友元函数定义中……”，逐个场景列出查找顺序。

这套描述能用，但它是枚举式的：每出现一种新语法（lambda、概念、模块、契约等），都要追加一条，条与条之间的漏洞和矛盾积累成了数十个 CWG issue。P1787R6（"Declarations and where to find them"，Davis Herring）在 C++23 周期中把作用域与查找整体重写成了构造式的：

| 旧的理解方式 | C++23 起的表述 |
|---|---|
| 声明区 / 潜在作用域 | 声明栖居于某个作用域，名字绑定到其目标作用域（[[basic.scope.scope]]） |
| 名字在某点可见 | 声明 X **先于**（precedes）程序点 P（¶2），统一处理同一 TU 与模块导入 |
| 内层声明隐藏外层声明 | 不再需要单独的规则：无限定搜索从最内层作用域开始，找到就停（[[basic.lookup.unqual#2]]） |
| 一张十几条的场景清单 | 一个算法：沿作用域的父链做搜索，类作用域的搜索按 [[class.member.lookup]] 展开到基类 |
| 在类的成员函数体内，名字先在……再在…… | 函数体所在的作用域本来就包含在类作用域中；完整类上下文（complete-class context）决定从哪个程序点搜索（[[class.member.lookup#3]]） |
| using 指令使名字如同声明在最近的公共外围命名空间中 | 在规范中改写为活跃的 using 指令在哪一层作用域被搜索（[[basic.lookup.unqual#1]]）；旧说法降格为注（[[namespace.udir#3]]） |

本页及后续几页的用语都遵循新模型。旧说法仍然有助于建立直观理解，但需要给出精确论证（例如说明为什么这里是二义的）时，应当用新术语推导。

## 查找的结果与后续流水线（¶1）

¶1 规定，名字查找把名字的一次使用关联到该名字的一组声明（[[basic.def]]）。要点如下：

1. 规则对所有名字一视同仁。typedef 名、命名空间名、类名等所有名字都走同一套查找规则，只要文法在该语境中允许这种名字。区别只在于某些语境会过滤结果（¶4，比如只考虑类型）。
2. 除非另有规定，找不到就非良构。另有规定的典型例子有：
    - 函数调用 `f(x)` 中，无限定查找什么也没找到时，ADL 仍可能找到（[[basic.lookup.argdep]]）；
    - `f<T>(x)` 中，无限定查找找不到任何东西时，`f` 仍被当作模板名（[[temp.names]]，C++20 起）；
    - `struct X* p;` 中找不到 `X` 时，会声明一个新类（[[dcl.type.elab]]）；
    - 非限定的友元函数声明 `friend void f();` 根本不做查找（[[dcl.meaning.general#2]]）。
3. 如果结果全是函数或函数模板，这组声明称为一个[[g:overload-set|重载集]]（overload set），此后交给重载决议（[[over.match]]、[[over.over]]）从中挑出一个。
4. 否则（结果中混有非函数），如果这些声明并不都指代同一实体，查找就是**二义的**（ambiguous），程序非良构。注意这里说的是同一实体：经由两条 using 路径找到同一个变量不算二义（见 [[namespace.qual#2]]）。

!!! std
    The access rules are considered only once name lookup and function overload resolution (if applicable) have succeeded.

    访问检查发生在查找与重载决议都成功之后。

于是一个名字的处理顺序是一条固定的流水线：

```
名字查找 ──► 重载决议（若结果是重载集）──► 访问检查 ──► 使用声明引入的语义性质
 [basic.lookup]     [over.match]              [class.access]     （类型、值类别、constexpr……）
```

为什么访问检查在最后？这是 C++ 有意的设计：**访问控制不影响可见性**（access control is not visibility control）。`private` 只决定能不能使用，不决定找到的是谁。这样做的好处是：

- 把一个成员从 `public` 改成 `private`，程序要么含义不变，要么报错，绝不会悄悄改为调用另一个函数。如果访问权参与查找或重载决议，修改访问说明符就可能在没有任何提示的情况下改变重载选择，造成难以排查的语义变化。
- 同一段代码在类内（有访问权）与类外（无访问权）查找到的东西是一样的，只是类外会报错。语义一致，便于推理。

代价是，私有成员同样会隐藏基类成员，同样参与重载决议，因此可能出现明明有一个可访问的候选却报错的情况：

```cpp run error
struct B { void f(int); };
struct D : B {
private:
    void f(double);        // 隐藏 B::f（查找不看访问权）
};

class X {
public:  void g(double);
private: void g(int);
};

void t() {
    D d;
    d.f(1);   // error: 查找只找到 D::f（私有）；B::f 被隐藏，根本不是候选
    X x;
    x.g(1);   // error: 重载决议选中 g(int)，随后访问检查失败；不会退而选 g(double)
}
```

¶1 的最后一句也值得注意：声明引入的语义性质（比如变量的类型、函数是否 `constexpr`、是否 `[[deprecated]]`）只有在这三步都成功后才会被使用。例如重载决议过程中只看函数签名等决议所需的信息；被淘汰的候选上的 `[[deprecated]]` 不会触发警告，只有被选中且访问合法的那个才会。

!!! note "查找结果 ≠ 最终实体"
    查找的产出是声明的集合，而不是一个实体。重载集、成员的子对象集合（[[class.member.lookup]]）、依赖名延迟到实例化时再查找（[[temp.res]]），都说明后续阶段还要在这个集合上继续工作。

## 程序点、跟随与先于（¶2）

¶2 用[[g:program-point|程序点]]（program point）精确定义了源码中的位置：翻译单元的第一个记号之前有一个程序点，每对相邻记号之间至少有一个，最后一个记号之后有一个。在此基础上：

- 对于同一翻译单元中声明点（locus，[[basic.scope.pdecl]]）在程序点 P 之前的任何声明，就说 P **跟随**（follows）这个声明。注 1 提醒，这个声明可以位于一个不包含 P 的作用域里。跟随只是文本上的先后关系，不涉及作用域，作用域由查找算法本身处理。
- 声明 X [[g:precedes|先于]]（precedes）翻译单元 L 中的程序点 P，当且仅当：
    1. P 跟随 X；或
    2. X 栖居于类作用域，且从 P 可达（reachable，[[module.reach]]）；或
    3. X 出现在另一个翻译单元 D 中，并且同时满足：
        - ¶2.1 P 跟随一个（直接或间接地）导入 D 的 *module-import-declaration* 或 *module-declaration*；
        - ¶2.2 X 在 D 的 *module-declaration* 之后、*private-module-fragment* 之前；
        - ¶2.3 X 是被导出（exported）的，或者 D 与 L 属于同一模块，且 X 既不栖居于具有内部链接的命名空间，也不声明具有内部链接的名字。

先于是旧标准中可见这一概念的精确替代。它是所有查找规则的基础：单次搜索（¶3）只找先于 P 的声明。

第 2 条值得仔细想一想：**类成员不需要被导出，也不需要在本 TU 中声明，只要类的定义可达，成员就能被找到。** 这正是模块的设计意图：一个模块可以不导出类名，但导出返回该类对象的函数；导入者拿到对象后，理应能够访问其成员：

```cpp title="m.cppm"
export module M;
struct S { int x = 1; };          // S 未导出
export S make() { return {}; }
```

```cpp title="use.cpp" error
import M;
int main() {
    auto s = make();
    int v = s.x;    // OK：S::x 栖身于类作用域，且 S 的定义从此处可达
    S s2;           // error: S 是命名空间作用域的声明且未导出，不"先于"此处
    return v;
}
```

注 2 指出，using 声明引入的名字没有链接，所以 ¶2.3 中关于内部链接的排除不会误伤它们。注 3 说明导入是传递的：导入含有 `export import Q;` 的模块 R 时，Q 也被导入。

!!! lawyer "可达 ≠ 先于"
    可达（reachable）关心的是声明的语义性质能否被使用（例如类是否完整），先于关心的是名字查找能否找到它。一个模块接口单元即使只是以非导出的方式被间接导入，它的声明也可能可达（[[module.reach#1]]），但其命名空间作用域中的名字不会被查找到。类成员是例外，它们只要可达就先于。

## 单次搜索（¶3）

¶3 定义的[[g:single-search|单次搜索]]（single search）是一切查找的基本操作：

!!! std
    A single search in a scope S for a name N from a program point P finds all declarations that precede P to which any name that is the same as N is bound in S.

    在作用域 S 中、从程序点 P 出发对名字 N 的单次搜索，找出 S 中绑定了与 N 相同的名字、且先于 P 的所有声明。

逐项来看：

- 绑定在 S 中：只看这一个作用域，不往外层找，也不往基类找。名字绑定到哪个作用域由 [[basic.scope.scope#2]] 决定，要注意其中的特例：友元声明与模板特化声明不绑定名字；块作用域的 `extern` 声明或函数声明以外层作用域为目标，但名字绑定在块作用域；无作用域枚举的枚举项绑定在两层作用域中；类名同时绑定在自己的类作用域中（注入类名）。
- 相同的名字：标识符按字符序列比较；*conversion-function-id* 按类型是否等价比较（[[basic.pre#4]]），所以 `operator T*` 在不同上下文中需要专门的规则（[[class.member.lookup#7]]）。
- 先于 P：见 ¶2。
- using 声明的替换：如果找到的是一个 *using-declarator*，且其终端名（terminal name）不是依赖的，就把它替换为它所指名的那些声明（[[namespace.udecl]]）。因此查找结果里看到的是原本的声明，而不是 using 声明本身。这保证了 `using N::f;` 引入的 `f` 和 `N::f` 是同一实体，不会造成二义。

```cpp run ok
namespace N { int v = 1; void f(int); }
namespace M { using N::v; using N::f; void f(double); }

using namespace N;
using namespace M;

void t() {
    v = 2;       // OK：通过 N 找到 N::v，通过 M 的 using 声明也找到 N::v——同一实体
    f(1);        // OK：重载集 {N::f(int), M::f(double)}，选 N::f(int)
}
```

在单次搜索之上，标准又定义了几层操作：

| 操作 | 定义处 | 做什么 |
|---|---|---|
| **单次搜索** single search | 本节 ¶3 | 只看一个作用域 |
| **搜索** search | [[class.member.lookup#1]] | 对非类作用域等于单次搜索；对类作用域要沿基类计算查找集 |
| **无限定搜索** unqualified search | [[basic.lookup.unqual#2]] | 在作用域 S 搜索，并加上活跃 using 指令提名的命名空间；找不到就去父作用域 |
| **无限定名字查找** | [[basic.lookup.unqual#3]] | 从程序点的直接作用域做一次无限定搜索 |
| **限定名字查找** | [[basic.lookup.qual#3]] | 在查找上下文（类/命名空间/枚举）中做一次搜索 |
| **实参依赖查找** ADL | [[basic.lookup.argdep]] | 在关联命名空间中搜索，并收集关联类的友元 |

## 结果的过滤：类型被隐藏，与仅类型查找（¶4）

¶4 指出，有些语境只接受某些种类的声明（例如嵌套名说明符之前只考虑命名空间与类型，[[basic.lookup.qual#1]]）。在完成这类限制之后，还有一条通用的隐藏规则：

!!! std
    any declarations of classes or enumerations are discarded if any other declarations are found.

    只要找到了其他声明，类与枚举的声明就被丢弃。

这就是为兼容 C 而保留的 `struct stat` 现象。C 中结构体标签与普通标识符处于不同的名字空间，`struct stat` 与函数 `stat` 可以共存。C++ 把类名放进了普通作用域，为了让这类 C 代码继续工作，规定在同一作用域里，类型名被其他实体（变量、函数、枚举项等）隐藏，需要用详述类型说明符（`struct stat`）才能指名类型（[[basic.lookup.elab]]）。

```cpp run error
struct stat { long st_size; };
int stat(const char* path, struct stat* buf);   // 与类名同名的函数：合法

void t() {
    struct stat s;          // OK：详述类型说明符的查找是仅类型的
    stat("/tmp", &s);       // OK：查找找到 {class stat, function stat}，类被丢弃 → 函数
    stat s2;                // error: stat 在此指函数，不是类型
}
```

注 4 强调了两个限定，即“类型（而非类型别名或模板）”：`typedef`/`using` 别名和模板不会这样被丢弃。如果同一作用域里同时存在别名 `T` 与变量 `T`，那是冲突的重声明（[[basic.scope.scope]]），根本到不了查找这一步。

**同一次查找的边界**：这条丢弃规则作用于一次查找的结果。[[namespace.qual#4]] 的注提醒，经由 using 指令在不同搜索中找到的类声明，不会因为另一次搜索找到了变量而被丢弃，于是会产生二义。这正是 [[namespace.udir#7]] 所说的，变量、函数或枚举项的名字不会隐藏在另一个命名空间中声明的类或枚举的名字。

### 仅类型查找（type-only lookup）

¶4 后半段定义了[[g:type-only-lookup|仅类型查找]]：只考虑类型，以及特化为类型的模板的声明。此外，如果同时找到了类型别名和它的底层实体，丢弃的是别名而不是类型。用到仅类型查找的地方有：

- 详述类型说明符 `struct X`、`enum E` 中的标识符（[[basic.lookup.elab]]）；
- 基类说明符 *base-specifier* 中的类型名（[[class.derived.general]]）。

丢弃别名而非类型是有原因的。详述类型说明符不能指名 typedef 名（[[dcl.type.elab#6]]），所以当别名与原类型都被找到时，必须保留原类型，`struct X` 才能合法：

```cpp run ok
namespace A { struct X {}; }
namespace B { using X = A::X; }
using namespace A;
using namespace B;

struct X* p;   // OK：找到 {A::X, B::X(别名)}，仅类型查找丢弃别名，留下 A::X
X* q;          // OK：普通查找也不二义——两者指代同一实体
```

```cpp run error
struct S {};
typedef S T;
struct T* p;   // error: 只找到别名 T，详述类型说明符不能指名 typedef 名
```

## 模板中的查找

模板定义中的名字分成非依赖名与依赖名（[[temp.dep]]）：

- 非依赖名在模板定义点查找并绑定（[[temp.res]]）；
- 依赖的函数调用名（如 `g(t)`，`t` 的类型是依赖的）分两个阶段查找：无限定查找在定义点进行，ADL 在定义上下文和实例化上下文中都进行（[[temp.dep.res]]、[[temp.dep.candidate]]、[[basic.lookup.argdep#4]]）；
- 无限定查找找不到依赖基类的成员（[[class.member.lookup#4]] 只考虑非依赖的直接基类），所以要写 `this->f()`。

下面是典型的两阶段查找错误：

```cpp run error
template<class T> void call(T t) { g(t); }   // g 是依赖名：定义点无限定查找什么也没找到
void g(int);                                  // 在模板定义之后才声明
int main() { call(1); }   // error: 实例化时只做 ADL，而 int 没有关联命名空间
```

如果把 `int` 换成某个命名空间里的类类型，并把 `g` 声明在同一命名空间里，ADL 就能在实例化上下文中找到它。ADL 能作为模板定制点机制使用，基础就在这里，详见 [[basic.lookup.argdep]]。

!!! impl "实现视角"
    - Clang 的 `LookupResult` 记录查找结果的种类：未找到、找到单个声明、找到重载集、找到尚待解析的值（依赖情形）、二义等。重载决议与访问检查是之后单独的步骤，正好对应 ¶1 的流水线。
    - 对上面两阶段查找的例子，Clang 23 的诊断大意是：调用的函数 `g` 在模板定义中不可见，ADL 也找不到。MSVC 在 `/permissive-` 之前长期没有实现两阶段查找，会接受这段代码，许多旧代码迁移时出错就是因为这一点。
    - 拼写纠错（"did you mean …"）不是查找的一部分。它在查找失败之后由前端额外执行，结果不影响程序含义。

!!! history "历史与演进"
    - **C++98/03**：查找规则以场景清单的形式给出；引入了 Koenig 查找（ADL）与两阶段查找的雏形。
    - **C++11**：内联命名空间进入查找与 ADL（[[namespace.def]]）；`decltype` 可以出现在嵌套名说明符中。
    - **C++20**：模块带来了可见与可达的区分；`f<T>(x)` 在找不到模板时也按模板名解析（[[basic.lookup.argdep]]）。
    - **C++23**：P1787R6 重写了第 6.4、6.5 节，引入程序点、先于、栖居/目标作用域、单次搜索/搜索、仅类型查找、成员限定名、查找上下文等术语，删除了旧的隐藏条款与场景清单。大多数代码的含义没有变化，但许多此前标准文本没有覆盖或互相矛盾的边角情形有了确定的答案。
    - **C++26**：静态反射加入 `std::meta::info` 的 ADL 特殊规则（[[basic.lookup.argdep#3]]）与 *splice-scope-specifier*（[[basic.lookup.qual#1]]）。

## 陷阱

!!! pitfall "以为 private 能把名字藏起来"
    私有成员照样参与查找与重载决议。如果想让某个重载对外不可用，应该用 `= delete`（它会参与决议并报错，意图明确）、约束（requires），或者干脆把它移出类，而不是依赖 `private`。

!!! pitfall "以为找到了就一定能用"
    查找成功只是第一步。即使 `d.x` 的查找没有二义，仍可能因为从对象表达式到声明所在基类的转换有二义而非良构（[[class.member.lookup#11]]、[[expr.ref#9]]）。

!!! pitfall "混淆重载集与二义"
    两个命名空间各有一个函数 `f`，通过 using 指令同时找到，这不是二义，它们组成重载集，交给重载决议处理。只有结果中混入了非函数（变量、类型等）且不是同一实体时，查找才是二义的。

## 思考题

!!! question "思考题 1"
    下面的 `f(0)` 调用哪个函数？如果把 `private:` 删掉呢？
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

对 `f` 的查找在 D 的作用域中找到 using 声明（替换为 `B::f(long)`）与 `D::f(int)`，二者组成重载集。重载决议对实参 `0`（`int`）选择精确匹配的 `D::f(int)`，随后访问检查失败，所以程序**非良构**。删掉 `private:` 后调用的是 `D::f(int)`。访问说明符从来不会让重载决议退而选择 `B::f(long)`。
</details>

!!! question "思考题 2"
    `struct X {}; int X;` 之后，`sizeof(X)` 指什么？`sizeof(struct X)` 呢？

<details markdown="1">
<summary>答案</summary>

`sizeof(X)`：查找找到 `{class X, variable X}`，类声明被丢弃（¶4），所以指的是变量 `X`，结果是 `sizeof(int)`。`sizeof(struct X)` 使用仅类型查找，只考虑类型，结果是类 `X` 的大小（1）。
</details>

!!! question "思考题 3"
    为什么 ¶2 要单独规定栖居于类作用域且可达的声明先于 P，而不是要求类成员也像命名空间成员那样被导出？

<details markdown="1">
<summary>答案</summary>

类成员没有单独的导出概念，`export` 作用于命名空间作用域的声明。成员能否被使用，应该取决于类的定义是否可达（这决定了类是否完整、布局是否已知），而不是成员名字本身是否以某种方式公开。否则，模块就无法只导出工厂函数而隐藏类名，同时又让使用者访问对象的成员。
</details>

## 小结

| 概念 | 一句话 |
|---|---|
| 名字查找 | 把名字的使用映射为声明的集合 |
| 重载集 | 查找结果全是函数/函数模板 |
| 二义 | 结果不全是函数，且不都指同一实体 → 非良构 |
| 流水线 | 查找 → 重载决议 → 访问检查 → 使用语义性质 |
| 程序点 / 先于 | 可见的精确版本；涵盖模块导入；类成员只需可达 |
| 单次搜索 | 一个作用域内、先于 P 的、绑定了同名的声明；using 声明被替换 |
| 类型隐藏 | 同一次查找里，类/枚举被其他声明隐藏（`struct stat`） |
| 仅类型查找 | 只看类型与类模板；别名与原类型同时找到时丢弃别名 |
