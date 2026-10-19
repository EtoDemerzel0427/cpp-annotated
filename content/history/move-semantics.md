---
title: 移动语义与值类别的由来
summary: 右值引用为什么不能绑定左值、类有析构函数时为什么不生成移动操作、xvalue 这些名字从哪来、C++17 为什么改了 prvalue 的含义、return x; 何时移动的规则为什么改了四次：从 C++98 的复制问题讲到 C++26。
status: draft
order: 80
since: c++11
papers: N1377, N1385, N2812, N3050, N3153, N3203, N3055, P0135R1, P1825R0, P2266R3, P2748R5, P2786R13, P3920R0
related: basic.lval, class.temporary, class.copy.elision, dcl.init.ref, stmt.return, class.copy.ctor, class.copy.assign, unique.ptr, topics/value-categories, topics/special-members-and-elision, topics/dangling-references
tags: 移动语义, 右值引用, 值类别, 复制消除, 隐式移动, 平凡重定位
updated: 2026-10-19
---

!!! tldr
    - C++98 能区分左值和右值，却无法让函数知道实参是马上要销毁的临时对象，所以只能复制。右值引用 `T&&` 就是为这一点加的。
    - 右值引用起初可以绑定左值，在重载被移除时会悄悄移走左值，2009 年改成今天的规则。类有用户声明的析构函数时不隐式生成移动操作，也是为了不破坏旧代码。
    - glvalue、xvalue、prvalue 是 2010 年为让标准措辞自洽而起的名字。C++17 又把 prvalue 重新定义为初始化对象的方式，从而保证了 `T x = T();` 不复制。
    - `return x;` 何时自动移动，C++11、C++14、C++20、C++23 各改了一次，其中两次是追溯适用的缺陷报告，所以旧语言模式的编译器行为不一定符合当年的标准。
    - C++26 禁止返回绑定到临时对象的引用。平凡重定位一度进入 C++26，又被移出，留待 C++29。

规则本身见 [[basic.lval]]、[[class.temporary]]、[[class.copy.elision]]、[[dcl.init.ref]] 和 [[stmt.return]]；判断一个表达式的值类别见 [[topics/value-categories]]，特殊成员函数何时隐式生成见 [[topics/special-members-and-elision]]。

本页的例子都在本机 Clang 23 上用不同的 `-std=` 验证过。行为随版本变化的例子不加判定标记，判定写在行尾注释里。

## C++98：能区分左值右值，却不能拿走资源

C++98 中每个表达式要么是 **lvalue**（左值，指代一个有身份的对象，可以取地址），要么是 **rvalue**（右值，如字面量和函数返回的临时对象）。这个两分法来自 C，主要回答两个问题：能不能取地址或出现在内置赋值左边，能不能绑定到非 const 的左值引用 `T&`。

第二条规则是后来一切故事的起点。C++98 规定右值不能绑定 `T&`，只能绑定 `const T&`（[[dcl.init.ref]]）。这保护了程序员：把临时对象传给一个打算修改实参的函数，几乎总是错误。代价是，函数无法区分马上就要销毁的临时对象和调用者之后还会用的 const 对象。两者都只能以 `const T&` 接收，函数拿到之后只能复制，不能把资源拿走。

## 复制消除：只是许可

返回大对象的代价，最早靠优化解决。标准化之前有人提议加一种语言扩展，在函数头里给返回对象起名，认为没有它编译器就无法可靠地省掉复制。Zortech C++ 和 Cfront 随后不加扩展就实现了具名返回值优化（NRVO），这被当作扩展不必要的证明（Lippman, *The Name Return Value Optimization*, 2004）。

C++98 把这种做法写成了许可而不是义务：从函数返回局部对象、用同类型临时对象初始化另一个对象时，实现可以省略复制构造，即使它有副作用。由于只是许可，标准仍要求被省略的复制构造函数可访问。下面的类型在 C++14 之前都不能按值返回，尽管没有哪个主流编译器真会调用那个复制构造函数：

```cpp run title="private-copy.cpp" std=c++14
struct NoMove {
    NoMove() {}
private:
    NoMove(const NoMove&);   // C++98 风格的禁止复制
};

NoMove make() { return NoMove(); }   // C++14 及以前: error，复制构造函数不可访问
                                     // C++17 起: OK，见下文
int main() {
    NoMove x = make();               // 同上
    (void)x;
}
```

许可的另一个问题是，程序员无法从源码判断优化是否发生。用 Clang 的 `-fno-elide-constructors` 关掉可选的消除，就能看到 C++98 语义下理论上存在的两次复制：

```cpp run title="elision-count.cpp" flags="-std=c++14 -fno-elide-constructors"
#include <cstdio>
struct S {
    S()         { std::puts("ctor"); }
    S(const S&) { std::puts("copy"); }
    ~S()        { std::puts("dtor"); }
};
S make() { return S(); }
int main() { S s = make(); }
// -std=c++98/c++14 -fno-elide-constructors: ctor copy dtor copy dtor dtor
// -std=c++17       -fno-elide-constructors: ctor dtor
```

## C++11 之前的绕行办法

复制消除只覆盖返回和用临时对象初始化两种情形。放进容器、容器扩容、转交所有权，在 C++98 中都只能复制。Stroustrup 认为这是大量显式使用指针的主要来源之一：为了把大块数据交出函数，人们在自由存储上分配它，再传递指针（HOPL IV §4.2.3）。库作者想出了几种办法，每一种都暴露了语言缺的东西。

**swap 技巧**。容器的成员 `swap` 只交换几个内部指针，于是先在局部构造好、再 swap 进目标成了惯用法：

```cpp run title="swap98.cpp" std=c++98 ok
#include <vector>
#include <string>
std::vector<std::string> v;

void refill() {
    std::vector<std::string> tmp(1000, std::string(100, 'x'));
    v.swap(tmp);                              // 交换三根指针，不复制元素
}
void shrink() {
    std::vector<std::string>(v).swap(v);      // C++98 缩减容量的写法
}
int main() { refill(); shrink(); return v.size() == 1000 ? 0 : 1; }
```

它只适用于能写成交换的操作，容器自己扩容时仍然逐个复制元素。

**auto_ptr**。`std::auto_ptr` 用复制的语法实现所有权转移：复制构造函数接受非 const 引用，并把源对象置空。

```cpp run title="auto-ptr.cpp" std=c++98 ok
#include <memory>
#include <cassert>
int main() {
    std::auto_ptr<int> p(new int(1));
    std::auto_ptr<int> q = p;     // 看起来是复制，实际转移了所有权
    assert(p.get() == 0);         // p 被置空
    assert(*q == 1);
}
```

复制语法却不满足复制语义，所以 `auto_ptr` 不能安全地放进容器，也不能交给假定复制后两者相等的泛型算法。为了能从函数返回的临时对象构造，它还需要辅助类 `auto_ptr_ref`。C++11 弃用了它，由 [[unique.ptr]] 取代；C++17 将它删除（[[N4190]]）。本机 Clang 23 搭配 libc++ 在 `-std=c++11` 下给出弃用警告，在 `-std=c++17` 下报告 `no member named 'auto_ptr' in namespace 'std'`。

**Mojo**。2003 年 Andrei Alexandrescu 的纯库方案，用一组包装类型和重载决议在库层面区分出可以拿走资源的实参（Alexandrescu, *Move Constructors*, CUJ 2003）。它证明这种区分可行，也说明了代价：每个类型都要改写，重载数目翻倍。

## 右值引用的设计（2002）

[[N1377]]（Hinnant、Dimov、Abrahams）提出一种新的引用类型 `A&&`，称为**右值引用**。它的几条核心设计一直保留到今天：

- `A&&` 是与 `A&` 不同的类型，可以构成重载，于是移动构造函数 `A(A&&)` 和复制构造函数 `A(const A&)` 可以并存；
- 有名字的右值引用当作左值，没有名字的当作右值。这样一个对象在函数体内用过一次之后，不会在下一次使用时被意外移走；
- 要从左值移动，必须显式转换，例如 `static_cast<A&&>(x)`，也就是后来的 `std::move`；
- 形参为 `T&&` 时，左值实参把 `T` 推导为左值引用类型。这是完美转发的基础。

最后一条解决的是同期 [[N1385]] 提出的转发问题：写一个包装函数，把实参原样转给另一个函数。C++98 的两种写法各有缺陷，正确转发 n 个参数需要 2ⁿ 个重载：

<div class="compare" markdown="1">

```cpp title="C++98" error
void g(int&);
void g(const int&);

template <class T>
void wrap1(T& a) { g(a); }
template <class T>
void wrap2(const T& a) { g(a); }

void test() {
  int i = 0;
  wrap1(42); // error: 右值不能绑 T&
  wrap2(i);  // 选中了 g(const int&)
}
```

```cpp title="C++11" ok
#include <utility>
void g(int&);
void g(const int&);
void g(int&&);

template <class T>
void wrap(T&& a) {
  g(std::forward<T>(a));
}
// wrap(i)  → g(int&)
// wrap(ci) → g(const int&)
// wrap(42) → g(int&&)
```

</div>

标准没有为推导语境中的 `T&&` 引入单独的类型。[[N4164]] 建议把这种形参称为**转发引用**（forwarding reference），C++17 起标准采用了这个术语（[[temp.deduct.call]]）。

## 弯路一：右值引用曾经能绑定左值（2009 年修正）

按 N1377 和 2006 年进入草案的版本，左值可以绑定到右值引用，只是在同时有 `A&` 重载时，重载决议优先选后者。只要两个重载都在，这没有问题。

[[N2812]] 指出，一旦其中一个重载被移除，这条规则就不安全了。例子是 `std::list<std::unique_ptr<int>>`：元素不可复制，`push_back(const value_type&)` 被约束或 SFINAE 移除，剩下的 `push_back(value_type&&)` 却能接受左值，于是 `l.push_back(a)` 悄悄把左值 `a` 移走。论文的概括是复制/移动重载集 "doesn't degrade safely"。

修正是禁止右值引用绑定左值。这样复制/移动重载中有一个被移除时，左值实参得到的是编译错误，而不是被静默移走：

```cpp run title="rvalue-ref-binding.cpp" error
int main() {
    int i = 0;
    int&& r = i;     // error: 右值引用不能绑定到左值
    (void)r;
}
```

这次修改的痕迹留在 `std::forward` 上：它必须重新设计，因为旧实现依赖于左值能绑定右值引用。

## 弯路二：会抛异常的移动（noexcept 的由来）

`std::vector::push_back` 在 C++98 中提供强异常安全保证：扩容时复制元素失败，原来的元素完好无损。改用移动后，如果移动构造函数在中途抛异常，已经移走的元素就恢复不了（[[N2855]]）。

最终方案（[[N3050]]）允许移动构造函数抛异常，同时加入 `noexcept` 说明符和 `std::move_if_noexcept`：标准库在需要强保证的地方，只在移动不会抛异常（或类型不可复制）时才移动。这就是今天 `std::vector` 扩容时只对 `noexcept` 移动构造函数使用移动的原因，细节见 [[topics/special-members-and-elision]]。

## 弯路三：隐式生成移动操作（Rule of Five 的由来）

右值引用进入草案时，编译器不会为类隐式生成移动操作。2010 年的 [[N3053]] 加入了隐式生成：只要类没有用户声明的复制构造函数，并且隐式的移动构造函数不会被定义为弃置的，就隐式声明一个。用户声明的析构函数不在抑制条件之列。

[[N3153]]（*Implicit Move Must Go*）随即指出这会悄悄改变正确的旧程序。它的例子是一个维护不变式的类：成员 `vector` 总是有 5 个元素，析构函数读取 `v[0]`。按 N3053，`y.push_back(X())` 会隐式移动临时对象，掏空它的 `vector`，析构函数随即越界读取。论文记录了当时 g++ 4.6 的 C++0x 模式确实让这个 C++03 程序出错。

委员会面前有两个选择：删除隐式移动（[[N3216]]），或收紧条件（[[N3203]]）。删除会让聚合体之类的简单类型失去移动能力，用户得为每个类写一组 `= default`；保留则必须保证有不变式的旧类不受影响。最后通过的是收紧：只要类有用户声明的复制构造函数、复制赋值、移动操作或析构函数，就不隐式声明移动操作。同时，有用户声明的析构函数或另一个复制操作时，隐式生成复制操作被标为弃用。

这就是 Rule of Five 背后的规则，也解释了下面程序的输出：

```cpp run title="implicit-move.cpp" std=c++11 ok
#include <cstdio>
#include <utility>
struct Tracer {
    Tracer() {}
    Tracer(const Tracer&) { std::puts("copy"); }
    Tracer(Tracer&&)      { std::puts("move"); }
};
struct Plain    { Tracer t; };                 // 隐式声明移动构造函数
struct WithDtor { Tracer t; ~WithDtor() {} };  // 有用户声明的析构函数：没有移动
int main() {
    Plain a;    Plain b = std::move(a);        // 输出 move
    WithDtor c; WithDtor d = std::move(c);     // 输出 copy：落到复制构造函数
}
```

用 `-Wdeprecated` 编译时，本机 Clang 23 对第二个类给出 `-Wdeprecated-copy-with-user-provided-dtor` 警告，对应的正是 N3203 引入的弃用。这条弃用至今没有变成删除，见 [[depr.impldec]]。

## 五个值类别的命名（2010）

右值引用给标准措辞带来一个问题：`static_cast<T&&>(x)` 或返回 `T&&` 的函数调用，这种表达式该叫什么？它指代一个确定的对象，像 lvalue；它又能绑定右值引用、可以被移动，像 rvalue。当时核心语言部分和标准库部分对 rvalue 一词的用法已经不一致。

Stroustrup 的分析是，只有两个相互独立的性质（Stroustrup, *"New" Value Terminology*；HOPL IV §4.2.3）：

- **有身份**：有地址，能判断两个表达式是否指代同一个对象；
- **可以被移动**：允许把源对象留在有效但未指定的状态。

没有身份又不能移动的组合在 C++ 里没有用处，剩下三种基本类别，再按两个性质各归并出两个大类。命名的约束是保留"每个表达式要么是 lvalue 要么是 rvalue"，并与标准库措辞中 rvalue 指"可以被移动"一致：

| 性质 | 名称 | 由来 |
|---|---|---|
| 有身份，不能移动 | lvalue | 保留传统含义 |
| 有身份 | glvalue | generalized lvalue |
| 有身份，能移动 | xvalue | 标准的注释解读为 eXpiring（[[basic.lval#3]]） |
| 没有身份，能移动 | prvalue | pure rvalue |
| 能移动 | rvalue | 与标准库措辞一致 |

[[N3055]] 据此改写了措辞。它没有改变 lvalue 和 rvalue 的外延，只是给 rvalue 中有身份的那部分起了名字。值类别仍然是表达式的性质，不是值或对象的性质（[[basic.lval#3]] 的注释特意强调了这一点）。

## C++11 和 C++14 的返回规则

C++11 让 `return local;` 在不写 `std::move` 时也能移动，这样才能按值返回 `std::unique_ptr` 这样只能移动的类型。规则是两阶段重载决议：如果操作数是满足复制消除条件的局部对象，先把它当右值做一次重载决议；如果选中的构造函数的第一个形参不是该对象类型的右值引用，再当左值重做一次。

C++14 期间有两项缺陷修复，都放宽了这一机制：

- [[CWG1579]]：原规则要求操作数与返回类型相同，`optional<T> f() { T t; return t; }` 只能复制。修正后只要满足其余条件，就先按右值尝试。
- [[CWG1402]]：原规则下，显式预置（`= default`）的移动构造函数很容易被定义为弃置，而弃置的函数参与重载决议，按值返回会选中它并报错。修正后，被定义为弃置的预置移动操作不参与重载决议，决议会退回到复制。

## C++17：保证的复制消除

到 C++14，返回临时对象时的复制消除仍然只是许可，上面的 `NoMove` 依旧不能按值返回。[[P0135R1]] 没有简单地把许可改成义务，而是改变了 prvalue 的含义。

C++14 中，`T()` 是一个临时对象，`T x = T();` 理论上从这个临时对象复制或移动到 `x`。C++17 起，prvalue 本身不是对象，而是一个初始化对象的方式。它初始化的那个对象称为**结果对象**（result object）。只有 prvalue 出现在需要 glvalue 的地方，比如绑定引用或访问成员时，才通过**临时量实质化**（temporary materialization）创建一个临时对象（[[basic.lval#5]]、[[class.temporary]]）。

<div class="compare" markdown="1">

```cpp title="C++14 的理解"
T x = T();
// 1. T() 创建临时对象
// 2. 从它复制/移动到 x（可省略）
// 3. 复制/移动构造函数必须可用
```

```cpp title="C++17 的理解"
T x = T();
// T() 是 prvalue，直接初始化 x
// 中间没有临时对象，
// 不需要复制/移动构造函数
```

</div>

返回 prvalue 也一样，return 语句直接初始化调用方的结果对象。所以 `NoMove` 在 C++17 中可以按值返回，`-fno-elide-constructors` 也插不进复制了。同理，`std::atomic<int> a = std::atomic<int>(0);` 在 C++14 中非良构（Clang 报告调用了被隐式删除的复制构造函数），在 C++17 中合法。

保证的只是 prvalue 的情形。`T f() { T x; return x; }` 中省略 `x` 到结果对象的复制，也就是 NRVO，至今仍然只是许可（[[class.copy.elision#1.1]]）。保证 NRVO 的提案 [[P2025R2]] 没有进入工作草案。

## 隐式移动再放宽两次（C++20、C++23）

### C++20：更多情形可以移动（P1825）

C++11/14 的规则仍有缺口：局部变量是右值引用时 `return r;` 不移动；形参在 `throw` 中不移动；第一个形参必须是"该对象类型的右值引用"，所以 `Base f() { Derived d; return d; }` 第一次选中 `Base(Base&&)`，又因为它不是 `Derived&&` 而退回复制。[[P1825R0]] 补上了这些缺口，引入了 implicitly movable entity 这个术语，并作为缺陷报告通过。

```cpp run title="more-implicit-moves.cpp" std=c++20 ok
#include <cstdio>
struct Base {
    Base() {}
    Base(const Base&) { std::puts("copy"); }
    Base(Base&&)      { std::puts("move"); }
};
struct Derived : Base {};

Base f() { Derived d; return d; }   // P1825 之前的措辞：copy；之后：move
Base g(Base&& r) { return r; }      // P1825 之前的措辞：copy；之后：move

int main() { f(); Base b; g(static_cast<Base&&>(b)); }
```

因为是缺陷报告，实现把它应用到了旧语言模式：本机 Clang 23 在 `-std=c++11` 到 `-std=c++20` 下都输出两行 move。用今天的编译器已经看不到 C++17 原始措辞的行为了。

### C++23：一条规则取代两阶段（P2266）

两阶段重载决议规则复杂，而且只作用于构造函数的选择，对返回引用的函数不起作用。[[P2266R3]] 把它换成一条规则：在 return、co_return 和 throw 中，指代 implicitly movable entity 的 id-expression 本身就是 xvalue，称为 **move-eligible**（[[expr.prim.id.unqual#15]]）。没有第二次尝试。

从此，同一个名字 `w` 在 return 语句里是 xvalue，在别处是 lvalue。这一改动不是缺陷报告，Clang 只在 C++23 及以后应用它，可以直接对比：

```cpp run title="simpler-implicit-move.cpp" std=c++23
#include <type_traits>

struct Widget { Widget(); Widget(Widget&&); };
Widget&& pass(Widget&& w) {
    return w;          // C++20: error，w 是左值；C++23: OK，w 是 xvalue
}

int& bad(int&& x) {
    return x;          // C++20: OK；C++23: error，xvalue 不能绑定到 int&
}

decltype(auto) h(int&& x) { return (x); }
static_assert(std::is_same_v<decltype(h(0)), int&&>);   // C++23 成立；C++20 下是 int&

int main() {}
```

`bad` 在 C++20 中合法、在 C++23 中非良构，这是 P2266 明确接受的不兼容。`decltype(auto)` 的变化是同一个原因：`decltype` 作用于带括号的表达式时反映它的值类别，而这个值类别在 return 语句里变了。

## C++26：禁止返回绑定到临时对象的引用

返回一个绑定到临时对象的引用，从来都是悬垂引用，但过去程序是良构的，编译器只能警告。[[P2748R5]] 把它改为非良构：

```cpp run title="return-temporary.cpp" std=c++2c
const int& f() {
    return 42;         // C++23 及以前：良构，Clang 给出警告
}                      // C++26：error，返回的引用绑定到临时对象
struct S { };
const S& g() { return S(); }   // 同上
int main() {}
```

本机 Clang 23 在 `-std=c++23` 下对两处给出 `returning reference to local temporary object` 警告，在 `-std=c++2c` 下把同样的诊断作为错误。现行草案的 [[stmt.return#6]] 更进一步：被返回对象的 constituent reference（例如聚合体中的引用成员）绑定到临时对象，同样非良构。这是 C++23 之后的新措辞，本页没有核实它对应的提案。悬垂引用的其他形式见 [[topics/dangling-references]]。

## 平凡重定位：进入 C++26 又被移出

很多类型的移动加析构（把对象移到新位置，再析构原对象）可以用一次 `memcpy` 完成，例如常见实现中的 `std::unique_ptr` 和 `std::vector`。容器扩容时知道这一点，就能整块复制内存。Abseil、Folly、Qt 等库已经这样做（[[P1144R13]]），但按标准的对象模型，用 `memcpy` 搬运非平凡可复制的对象是未定义行为。

标准化有两条竞争的路线：[[P1144R13]]（*std::is_trivially_relocatable*）和 [[P2786R13]]（*Trivial Relocatability For C++26*）。两者在怎样声明一个类型可平凡重定位、swap 和赋值能否同样优化等问题上取舍不同。2025 年 2 月 C++26 采纳了 P2786R13。

同年 11 月处理国家成员体意见时，委员会以共识把它从 C++26 中移除，包括 `trivially_relocatable_if_eligible` 等上下文关键字、`is_trivially_relocatable` 等类型特征和 `std::trivially_relocate`（[[P3920R0]]）。Sutter 的会议报告称委员会发现了一个无法在 C++26 时间内修好的问题（Sutter, Kona trip report, 2025-11）。[[P4197R0]] 随后整理了 C++29 需要回答的设计问题，例如重定位应当是字节复制还是一种专门的抽象机操作、是否允许需要修正指针的重定位。所以截至本文写作，C++26 中没有平凡重定位。

## 回头看

这段历史一直在回答同一个问题：什么时候可以不复制。C++98 允许实现不复制；C++11 让程序员能显式要求移动，返回局部变量时自动移动；C++17 让某些情形下根本不存在复制。每一步留下的痕迹，今天读标准时都会碰到：

- 值类别是表达式的性质，而且自 C++23 起还取决于语境（return、co_return、throw 中的 move-eligible id-expression）。
- C++17 之后 prvalue 不是临时对象。问"这里有没有临时对象"，要看 prvalue 是否被实质化，而不是看它是不是右值。
- 只有 prvalue 的复制消除是保证的。NRVO 仍然是许可，被消除的复制或移动构造函数仍须可用（[[class.copy.elision]]）。
- 隐式移动的规则改过四次，其中两次是缺陷报告。验证版本差异时，要分清标准的原始措辞和编译器在旧模式下的实际行为。

## 时间线

| 年份 | 事件 | 文献 |
|---|---|---|
| 1998 | lvalue/rvalue 两分法；复制消除只是许可；`auto_ptr` | C++98 |
| 2002 | 右值引用与移动语义提案；转发问题 | [[N1377]]、[[N1385]] |
| 2009 | 右值引用不再绑定左值 | [[N2812]] |
| 2010 | `noexcept` 与 `move_if_noexcept`；五个值类别；收紧隐式移动 | [[N3050]]、[[N3055]]、[[N3203]] |
| 2011 | C++11 发布 | |
| 2013–2014 | 返回时按转换构造函数移动；弃置的预置移动不参与重载决议（DR） | [[CWG1579]]、[[CWG1402]] |
| 2016 | 保证的复制消除，prvalue 重新定义（C++17） | [[P0135R1]] |
| 2019 | 更多的隐式移动（DR） | [[P1825R0]] |
| 2022 | 更简单的隐式移动（C++23） | [[P2266R3]] |
| 2024 | 禁止返回绑定到临时对象的引用（C++26） | [[P2748R5]] |
| 2025 | 平凡重定位进入又移出 C++26 | [[P2786R13]]、[[P3920R0]] |

## 参考资料

- Bjarne Stroustrup. *Thriving in a Crowded and Changing World: C++ 2006–2020*. HOPL IV (2020)，§4.2.3 *Move Semantics*。
- Bjarne Stroustrup. *"New" Value Terminology*, 2010，stroustrup.com/terminology.pdf。
- Stanley B. Lippman. *The Name Return Value Optimization*, MSDN 博客，2004。
- Andrei Alexandrescu. *Generic&lt;Programming&gt;: Move Constructors*, C/C++ Users Journal, 2003-02。
- [[N1377]] *A Proposal to Add Move Semantics Support to the C++ Language*；[[N1385]] *The Forwarding Problem: Arguments*。
- [[N2812]] *A Safety Problem with RValue References (and what to do about it)*。
- [[N2855]] *Rvalue References and Exception Safety*；[[N3050]] *Allowing Move Constructors to Throw*。
- [[N3053]] *Defining Move Special Member Functions*；[[N3153]] *Implicit Move Must Go*；[[N3203]] *Tightening the conditions for generating implicit moves*；[[N3216]] *Removing Implicit Move Constructors and Move Assignment Operators*。
- [[N3055]] *A Taxonomy of Expression Value Categories*。
- [[P0135R1]] *Wording for guaranteed copy elision through simplified value categories*。
- [[P1825R0]] *Merged wording for P0527R1 and P1155R3*；[[P2266R3]] *Simpler implicit move*；[[P2748R5]] *Disallow Binding a Returned Glvalue to a Temporary*。
- [[P1144R13]]、[[P2786R13]]、[[P3920R0]]、[[P4197R0]]：平凡重定位；Herb Sutter, *Trip report: November 2025 ISO C++ standards meeting (Kona, USA)*。
