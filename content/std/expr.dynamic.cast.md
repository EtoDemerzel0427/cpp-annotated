---
title: dynamic_cast
summary: 唯一带运行期检查的转换：目标类型的要求、向上转换（编译期完成）、转换到 void*（取最派生对象）、向下转换与交叉转换的运行期检查算法、失败时返回空指针或抛 std::bad_cast、对生命周期外对象的 UB、构造析构期间的行为，以及 Itanium ABI 中 __dynamic_cast 的实现与代价
status: draft
papers: P1327R1
related: expr.static.cast, expr.typeid, class.cdtor, class.virtual, class.derived, intro.object, conv.ptr, bad.cast, basic.life, topics/casts
tags: 类型转换, RTTI, 多态, 继承
updated: 2026-10-17
---

`dynamic_cast` 是四个具名转换中唯一一个**可能在运行期检查**的：给它一个指向基类子对象的指针，它会查看对象的**动态类型**，判断"这个对象里到底有没有我要的那个类的子对象"，有就返回指向它的指针，没有就返回空指针（或抛异常）。这是 C++ 版的 `instanceof` / 安全向下转换。

但 `dynamic_cast` 也处理几种根本不需要运行期检查的情况：向上转换、同类型转换。本节按顺序列出全部情形（¶3、¶4、¶8、¶9），顺序本身就是规则：**先匹配的情形优先**。

阅读前提：多态类（[[class.virtual]]）、最派生对象与基类子对象（[[intro.object]]）、继承中的访问与二义性（[[class.derived]]、[[class.access.base]]）。

## 形式与目标类型（¶1–2）

¶1：`dynamic_cast<T>(v)` 的结果是把 `v` 转换为 `T` 的结果。`T` 必须是：

- 指向**完整类类型**的指针或引用，或
- "指向 cv `void` 的指针"。

`dynamic_cast` **不能去掉常量性**（casts away constness，[[expr.const.cast#6]]）——想同时去 `const` 需要再套一层 `const_cast`。

¶2 规定操作数与结果的值类别：

| `T` | 操作数 `v` | 结果 |
|---|---|---|
| 指针类型 | 指向完整类类型的指针 prvalue | prvalue |
| 左值引用 `C&` | 完整类类型的**左值** | lvalue |
| 右值引用 `C&&` | 完整类类型的 **glvalue** | xvalue |

```cpp title="dyn-requirements.cpp" error
struct V { virtual ~V() = default; };
struct D : V {};
struct Inc;
struct N {};
struct M : N {};

void f(const V* cv, V* v, N* n, Inc* pi) {
    dynamic_cast<D*>(cv);         // error: 去掉了 const
    dynamic_cast<const D*>(cv);   // OK
    dynamic_cast<int*>(v);        // error: T 必须是指向类类型的指针（或 void*）
    dynamic_cast<D>(*v);          // error: T 必须是指针或引用
    dynamic_cast<M*>(n);          // error: 向下转换要求操作数是多态类型（¶5）
    dynamic_cast<D&>(V{});        // error: 左值引用要求左值操作数
    dynamic_cast<D&&>(V{});       // OK：右值引用接受 glvalue（prvalue 被实质化）
    dynamic_cast<Inc*>(v);        // error: 目标类不完整
    dynamic_cast<V*>(pi);         // error: 操作数指向不完整类
}
```

## 无需检查的情形（¶3–4）

### 同类型（¶3）

¶3：若 `v` 的类型与 `T` 相同（忽略 cv），结果就是 `v`（必要时加上 cv）。

### 向上转换（¶4）

¶4：若 `T` 是"指向 *cv1* `B` 的指针"而 `v` 是"指向 *cv2* `D` 的指针"，且 `B` 是 `D` 的基类，结果是指向 `v` 所指 `D` 对象中**唯一的** `B` 子对象的指针（`v` 为空则结果为空）。引用同理。`B` 是**不可访问或二义**的基类时，程序非良构。脚注 45：最派生对象中可能还有其他 `B` 子对象，但它们被忽略——这里只看静态类型 `D` 的视角。

标准例 1：

```cpp run title="dyn-upcast.cpp" ok
struct B {};
struct D : B {};

void foo(D* dp) {
    B* bp = dynamic_cast<B*>(dp);   // 等价于 B* bp = dp;
    (void)bp;
}

int main() { D d; foo(&d); }
```

注意：向上转换**不要求多态类型**（`B` 没有虚函数也可以），也**不需要 RTTI**。它与隐式转换完全一样，在编译期完成。这条规则的存在只是为了让 `dynamic_cast` 在泛型代码里能统一地处理"上"和"下"。

## 需要运行期检查的情形（¶5–9）

### 操作数必须是多态的（¶5）

¶5：除上述情形外，`v` 必须是**多态类型**的指针或 glvalue——即类至少有一个虚函数（[[class.virtual]]）。为什么？运行期检查需要知道对象的动态类型，而只有多态对象才在对象里携带这一信息（vptr 指向的虚表中的 RTTI 指针）。非多态类根本无从查询。

### 空指针（¶6）

¶6：`v` 是空指针值时，结果是空指针值。（引用不可能为"空"，所以无需规定。）

### 生命周期之外：UB（¶7）

¶7：若 `v` 是"指向 cv `U` 的指针"而它**不指向**一个类型与 `U` 相似、且处于**生命周期内**或**构造/析构期间**的对象，行为未定义；glvalue 同理。也就是说：悬垂指针、指向已析构对象的指针、类型错误（经 `reinterpret_cast` 得到）的指针，交给 `dynamic_cast` 都是 UB——`dynamic_cast` 不是"万能的指针有效性检查"。它要读 vptr，而 vptr 已经不存在或不对。这与 [[basic.life#7]] 的第 4 项相呼应。

```cpp run title="dyn-dangling.cpp" ub
struct B { virtual ~B() = default; };
struct D : B {};

int main() {
    B* p = new D;
    delete p;
    D* d = dynamic_cast<D*>(p);   // UB: *p 不在生命周期内（¶7）；不会"安全地"返回空指针
    return d != nullptr;
}
```

### 转换到 `void*`（¶8 前半）

¶8：若 `T` 是"指向 cv `void` 的指针"，结果是指向 `v` 所指的**最派生对象**（[[intro.object]]）的指针。这是从任意基类子对象找回"整个对象起始地址"的唯一可移植方式，在多重继承中非常有用（例如用对象地址作为身份比较、或者实现自定义的内存管理）。

```cpp run title="dyn-void.cpp" ok
struct A { virtual ~A() = default; int a; };
struct B { virtual ~B() = default; int b; };
struct D : A, B {};

int main() {
    D d;
    B* pb = &d;                       // 指向 B 子对象，地址 ≠ &d
    void* whole = dynamic_cast<void*>(pb);
    return (whole == static_cast<void*>(&d) && static_cast<void*>(pb) != whole) ? 0 : 1;
}
```

### 运行期检查（¶8 后半、¶9）

其他情形施加**运行期检查**，判断 `v` 所指对象能否转换为 `T` 所指类型 `C`。¶9 给出逻辑步骤：

1. **¶9.1 向下转换**：若在 `v` 所指的最派生对象中，`v` 指向某个 `C` 对象的 **public 基类子对象**，并且从 `v` 所指的子对象派生出的 `C` 对象**只有一个**，结果指向那个 `C` 对象。
2. **¶9.2 交叉转换**（cross-cast / sidecast）：否则，若 `v` 指向最派生对象的一个 **public 基类子对象**，并且最派生对象的类型有一个**无二义的 public** 基类 `C`，结果指向最派生对象的那个 `C` 子对象。
3. **¶9.3**：否则检查**失败**。

直觉：

- ¶9.1 是"从我往下找"：我所在的这个子对象，是不是某个 `C` 的一部分？只看包含"我"的那一条继承链。
- ¶9.2 是"从顶部找"：先走到最派生对象，再看它有没有唯一的 public `C` 基类。这一步允许"横跳"到另一个分支。
- 两步都要求路径是 **public** 的：`dynamic_cast` 尊重访问控制，私有继承的关系在运行期是"看不见"的。

```cpp run title="dyn-cross.cpp" ok
struct Shape { virtual ~Shape() = default; };
struct Drawable { virtual ~Drawable() = default; virtual int draw() const = 0; };
struct Circle : Shape, Drawable { int draw() const override { return 1; } };
struct Square : Shape {};

int main() {
    Circle c;
    Square s;
    Shape* p1 = &c;
    Shape* p2 = &s;
    Circle* down = dynamic_cast<Circle*>(p1);        // ¶9.1 向下转换：成功
    Drawable* side = dynamic_cast<Drawable*>(p1);    // ¶9.2 交叉转换：Shape → Drawable，成功
    Drawable* none = dynamic_cast<Drawable*>(p2);    // Square 不是 Drawable：失败，空指针
    return (down == &c && side && side->draw() == 1 && none == nullptr) ? 0 : 1;
}
```

交叉转换是 `dynamic_cast` 独有的能力：`static_cast<Drawable*>(p1)` 是非良构的（`Shape` 和 `Drawable` 没有继承关系）；`reinterpret_cast` 能编译，但结果不指向 `Drawable` 子对象。

### 失败的结果（¶10）

¶10：转换到**指针**失败时，结果是目标类型的空指针值；转换到**引用**失败时，抛出一个能被 `std::bad_cast`（[[bad.cast]]）处理器捕获的异常。理由很简单：引用不能为空，只能用异常表达失败。

```cpp run title="dyn-bad-cast.cpp" ok
#include <typeinfo>

struct B { virtual ~B() = default; };
struct D : B {};

int main() {
    B b;
    try {
        D& d = dynamic_cast<D&>(b);   // 失败：抛出 std::bad_cast
        (void)d;
        return 1;
    } catch (const std::bad_cast&) {
        return 0;
    }
}
```

### 标准例 2：私有继承、虚继承与多重子对象

标准的例 2 浓缩了所有边界情况，逐行解释如下：

```cpp run title="dyn-std-example.cpp" ok
class A { virtual void f() {} };
class B { virtual void g() {} };
class D : public virtual A, private B { };

void g() {
    D   d;
    B*  bp = (B*)&d;                  // C 风格转换无视私有继承（[expr.cast]/4.6）
    A*  ap = &d;                      // public 派生，无需转换
    // D&  dr = dynamic_cast<D&>(*bp);  // 失败（抛 bad_cast）：B 是 D 的私有基类，¶9.1 要求 public
    ap = dynamic_cast<A*>(bp);        // 失败：bp 指向的不是 public 基类子对象，¶9.2 不适用
    bp = dynamic_cast<B*>(ap);        // 失败：最派生对象 D 的 B 基类不是 public
    ap = dynamic_cast<A*>(&d);        // 成功：¶4 向上转换
    // bp = dynamic_cast<B*>(&d);     // 非良构：¶4 向上转换到不可访问的基类（编译期错误，不是运行期检查）
}

class E : public D, public B { };
class F : public E, public D { };

void h() {
    F   f;
    A*  ap  = &f;                     // 成功：A 是虚基类，F 中只有一个 A
    D*  dp  = dynamic_cast<D*>(ap);   // 失败，得到空指针：F 有两个 D 子对象，¶9.1 要求唯一、¶9.2 要求无二义
    // E*  ep  = (E*)ap;              // 非良构：不能从虚基类 static_cast 向下转换
    E*  ep1 = dynamic_cast<E*>(ap);   // 成功：F 中只有一个 E
    (void)dp; (void)ep1;
}

int main() { g(); h(); }
```

几个要点：

- **私有继承在运行期不可见**：即使对象里"物理上"有 `B` 子对象，`dynamic_cast` 也不会经由私有继承关系转换。
- **虚基类**：`static_cast` 无法从虚基类向下转换（[[expr.static.cast#10]]），因为虚基类子对象的偏移在编译期未知；`dynamic_cast` 可以，因为它在运行期查询对象布局。这是 `dynamic_cast` 不可替代的场景之一。
- **多个同类子对象**：`F` 有两个 `D`，从 `A`（经虚继承共享的唯一子对象）出发无法确定是哪一个，失败。

## 构造与析构期间（注 1）

注 1 指向 [[class.cdtor#6]]：在构造函数或析构函数中（包括其调用的函数），若 `dynamic_cast` 的操作数指向**正在构造/析构的对象**，该对象被视为一个**类型为当前构造函数/析构函数所属类的最派生对象**。于是：在 `B` 的构造函数里，即使最终对象是 `D`，`dynamic_cast<D*>(this)` 也会失败。另外，若操作数的静态类型既不是当前类也不是其基类，行为未定义。

```cpp run title="dyn-ctor.cpp" ok
struct V { virtual ~V() = default; };
struct D;
struct B : V { B(); bool saw_d = true; };
struct D : B {};

B::B() {
    V* v = this;
    saw_d = dynamic_cast<D*>(v) != nullptr;   // 构造 B 期间，对象被视为最派生类型 B：失败
}

int main() {
    D d;
    V* v = &d;
    bool after = dynamic_cast<D*>(v) != nullptr;   // 构造完成后：成功
    return (!d.saw_d && after) ? 0 : 1;
}
```

这与虚函数在构造期间按当前类分派（[[class.cdtor#4]]）是同一个原理：派生类部分还没有构造，不能让任何机制"看到"它。实现上，构造 `B` 期间对象的 vptr 指向的就是 `B` 的虚表（或构造虚表）。

## 常量求值

C++20 起（[[P1327R1]]），`dynamic_cast` 和多态 `typeid` 可以出现在常量表达式中。常量求值器知道每个对象的确切类型，所以检查是精确的：

```cpp run title="dyn-constexpr.cpp" ok
struct B { virtual ~B() = default; };
struct D : B {};
struct E : B {};

constexpr bool test() {
    D d;
    B* p = &d;
    return dynamic_cast<D*>(p) != nullptr && dynamic_cast<E*>(p) == nullptr;
}
static_assert(test());

int main() {}
```

常量求值中失败的**引用**转换会抛 `std::bad_cast`。C++23 及之前，常量求值中抛异常直接使表达式不是常量表达式；C++26 {{c++26}} 允许在常量求值中抛出并捕获异常，只是当异常类型的定义不可达时（例如没有包含 `<typeinfo>`），这样的 `dynamic_cast` 不是核心常量表达式（[[expr.const.core#2]]，列表项 2.31）。另外，对动态类型"constexpr 未知"的对象（例如函数形参引用的对象）做 `dynamic_cast` 也不是核心常量表达式（列表项 2.30）。

## 实现视角

!!! impl "Itanium C++ ABI 中的 dynamic_cast"
    - **向上转换**（¶4）：编译期计算偏移，与 `static_cast` 生成相同的代码（虚基类则从虚表读取偏移）。不需要 RTTI。
    - **转换到 `void*`**（¶8）：从虚表的 *offset-to-top* 槽（vptr 前第二个字）读出当前子对象到最派生对象起点的偏移，加到指针上。只需要两次加载，也不需要 RTTI——本机 Clang 在 `-fno-rtti` 下仍接受 `dynamic_cast<void*>`，但拒绝其他需要运行期检查的 `dynamic_cast`（"use of dynamic_cast requires -frtti"）。
    - **向下/交叉转换**：调用运行时库函数 `__dynamic_cast(const void* src, const __class_type_info* src_type, const __class_type_info* dst_type, ptrdiff_t hint)`（libstdc++ 的 libsupc++、LLVM 的 libc++abi 都提供）。它先用 offset-to-top 找到最派生对象，再从最派生对象的 `type_info`（`__si_class_type_info` 或 `__vmi_class_type_info`）开始**遍历整棵继承图**，寻找 `dst_type` 的 public 子对象，并检查唯一性与可访问性。`hint` 是编译器静态计算出的提示（例如"`src_type` 是 `dst_type` 的唯一 public 非虚基类，偏移为 N"），用于加速常见情况。
    - **类型比较**：遍历中需要比较 `type_info`。在类型名唯一的平台上比较指针即可；在某些平台/动态库配置下需要比较类型名字符串，代价显著更高。

!!! impl "final 类的快速路径"
    若目标类是 `final` 的，最派生对象只可能是它本身，检查就退化为"对象的 vptr 是否等于 `C` 的虚表地址"。本机 Clang 以 `--target=x86_64-linux-gnu -O2` 编译 `dynamic_cast<D*>(b)`（`D` 为 `final`）时，生成的就是一次 vptr 比较，不调用 `__dynamic_cast`；而以默认的 macOS 目标编译时仍调用 `__dynamic_cast`。能否使用这条快速路径取决于虚表在整个程序中是否唯一，因此与目标平台和链接模型有关。

!!! impl "代价与替代"
    非 final 的 `dynamic_cast` 要调用运行时库并遍历继承图，通常比一次虚函数调用贵得多，且代价随继承图的复杂度增长。性能敏感的代码常用以下替代：在基类里放一个虚函数 `kind()` 或枚举标签再 `static_cast`；用 `std::variant` 代替继承体系；LLVM 项目自己的 `isa<>`/`dyn_cast<>` 就是"手写标签 + `static_cast`"的模式，LLVM 本身以 `-fno-rtti` 编译。

## 历史与演进

!!! history
    - **C++98**：`dynamic_cast` 与 RTTI 一同标准化。
    - **C++11**：增加右值引用目标类型（结果为亡值）。
    - **C++20**：可用于常量表达式（[[P1327R1]]）。

## 陷阱

!!! pitfall "`dynamic_cast` 不能检测悬垂指针"
    ¶7：对已析构对象使用 `dynamic_cast` 是 UB，不会返回空指针。

!!! pitfall "私有/保护继承导致运行期失败"
    即使对象确实有那个基类子对象，非 public 继承路径会让运行期检查失败（或在向上转换时编译失败）。

!!! pitfall "构造/析构函数中向下转换总是失败"
    在基类构造函数中 `dynamic_cast<Derived*>(this)` 永远得到空指针——这不是 bug，是规则。

!!! pitfall "跨动态库的 RTTI"
    若同一个类在两个动态库中各有一份 `type_info`（例如符号可见性设置为隐藏），某些平台上 `dynamic_cast` 会因类型比较失败而返回空指针。这超出了标准的范围（标准不涉及动态库），但在实践中是 `dynamic_cast` "莫名失败"的常见原因。

## 思考题

!!! question "思考题 1"
    `struct L { virtual ~L(); }; struct R { virtual ~R(); }; struct X : L, R {}; struct Y : X, R {};`（`Y` 有两个 `R` 子对象），`L* pl = static_cast<X*>(&y);` 之后 `dynamic_cast<R*>(pl)` 结果如何？

<details markdown="1">
<summary>答案</summary>

¶9.1：`pl` 指向的 `L` 子对象不是任何 `R` 的基类子对象（`L` 与 `R` 无继承关系），不适用。¶9.2：最派生对象类型 `Y` 有两个 `R` 基类子对象（一个经 `X`，一个直接），`R` 是**二义**基类，不适用。检查失败，结果为空指针。若想取得经 `X` 的那个 `R`，先 `dynamic_cast<X*>(pl)`（¶9.1 成功）再隐式向上转换。
</details>

!!! question "思考题 2"
    为什么 `dynamic_cast<void*>(p)` 要求 `*p` 是多态类型，而 `static_cast<void*>(p)` 不要求？二者结果何时不同？

<details markdown="1">
<summary>答案</summary>

`dynamic_cast<void*>` 要找的是**最派生对象**的起始地址，这需要运行期知道 `*p` 是哪个更大对象的一部分，只有多态对象（通过 vptr 和 offset-to-top）携带这一信息。`static_cast<void*>(p)` 只是把 `p` 本身的地址值换个类型，不关心更大的对象。当 `*p` 是某个最派生对象的非首个基类子对象（多重继承中第二个及以后的基类）时，二者的值不同。
</details>

## 小结

!!! summary
    | 情形 | 条款 | 需要多态？ | 需要 RTTI？ | 失败可能？ |
    |---|---|---|---|---|
    | 同类型 | ¶3 | 否 | 否 | 否 |
    | 向上转换到可访问、无二义的基类 | ¶4 | 否 | 否 | 否（不可访问/二义则编译期非良构） |
    | 转换到 `void*` | ¶8 | 是 | 否（Itanium 只读 offset-to-top） | 否 |
    | 向下转换 | ¶9.1 | 是 | 是 | 是 |
    | 交叉转换 | ¶9.2 | 是 | 是 | 是 |
    | 失败 | ¶10 | | | 指针 ⇒ 空指针；引用 ⇒ `std::bad_cast` |
    | 操作数不指向生命周期内对象 | ¶7 | | | UB |
