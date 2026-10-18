---
title: static_cast
summary: static_cast 的全部合法转换，按标准顺序：引用向下转换、左值到右值引用（std::move 的本质）、转换到 void、"能隐式转换或能直接初始化"的一切、以及标准转换的逆——有作用域枚举到整数、整数/浮点到枚举、浮点之间、指针向下转换、成员指针向上转换、void* 到 T*（指针可互转规则）；每种情形的 UB 边界
status: draft
papers: P0137R1, P0960R3, P2738R1
related: expr.cast, expr.dynamic.cast, expr.reinterpret.cast, expr.const.cast, conv, over.best.ics, dcl.init, dcl.init.ref, dcl.enum, conv.ptr, conv.mem, basic.compound, topics/casts, topics/value-categories
tags: 类型转换, 继承, 枚举, 指针, 移动语义, UB
updated: 2026-10-17
---

`static_cast` 是"**有道理的**"转换：凡是语言认为合理、但可能需要你明确表态的转换，都归它管。它的规则可以粗略概括为三句话：

1. 能**隐式**完成的转换（以及能**直接初始化**完成的转换），`static_cast` 都能做（¶5）；
2. 大多数**标准转换的逆**，`static_cast` 也能做（¶7–¶12），比如基类指针 → 派生类指针、`void*` → `T*`、`int` → 枚举；
3. 它**不做**的事：去掉 `const`（交给 `const_cast`）、在无关指针类型之间转换、指针 ↔ 整数（交给 `reinterpret_cast`）、运行期检查（交给 `dynamic_cast`）。

第二类转换是"逆向"的，标准只能信任你：**向下转换不做任何检查**，若对象实际上不是那个派生类，就是 UB。

本节的结构很规整：¶1 定义结果的值类别，¶2–¶5 按顺序列出若干**优先**的情形，¶6 说"否则"，然后 ¶7–¶12 列出剩下的允许转换，并宣布**除此之外一概不允许**。

## 结果的值类别（¶1）

¶1：`static_cast<T>(v)` 的结果是把 `v` 转换为 `T`。值类别**只由 `T` 决定**：

| `T` | 结果 |
|---|---|
| 左值引用；或函数的右值引用 | lvalue |
| 对象的右值引用 | **xvalue** |
| 非引用 | prvalue |

这条与 [[expr.call#15]]（函数调用按返回类型）、[[expr.reinterpret.cast#1]]、[[expr.cast#1]] 完全平行。`std::move(x)` 的实现就是 `static_cast<std::remove_reference_t<T>&&>(x)`——一个结果为亡值的 `static_cast`。

## 引用的向下转换（¶2）

¶2：类型为 *cv1* `B` 的**左值**（`B` 是类类型）可以被转换为"*cv2* `D` 的引用"，其中 `D` 是从 `B` **派生**的**完整**类，且 *cv2* 不少于 *cv1*。限制：

- 若 `B` 是 `D` 的**虚基类**，或虚基类的基类，非良构；
- 若不存在从"指向 `D` 的指针"到"指向 `B` 的指针"的有效标准转换（[[conv.ptr]]）——即 `B` 是 `D` 的**不可访问**或**二义**基类——非良构；
- 类型为 *cv1* `B` 的 **xvalue** 可以按同样的限制转换为"*cv2* `D` 的右值引用"。

结果：若 `B` 对象**确实是**某个 `D` 对象的基类子对象，结果指代那个外围的 `D` 对象；**否则行为未定义**。

```cpp run title="ref-downcast.cpp" ok
struct B {};
struct D : public B { int extra = 42; };

int main() {
    D d;
    B& br = d;
    D& dr = static_cast<D&>(br);   // OK：br 确实是 D 的基类子对象
    return dr.extra == 42 ? 0 : 1;
}
```

```cpp run title="ref-downcast-ub.cpp" ub
struct B {};
struct D : B { int extra = 42; };

int main() {
    B b;
    D& dr = static_cast<D&>(b);    // UB: b 不是任何 D 对象的子对象
    return dr.extra;
}
```

为什么不能经虚基类向下转换？因为虚基类子对象在最派生对象中的位置**取决于最派生类型**：`struct D : virtual B` 中，`B` 子对象相对 `D` 的偏移在 `D` 作为完整对象时是一个值，在 `D` 作为某个 `E` 的基类子对象时可能是另一个值。`static_cast` 只做编译期偏移计算，无从得知。要经虚基类向下转换，必须用 [[expr.dynamic.cast]]。

## 左值到右值引用（¶3）

¶3：类型为 `T1` 的**左值**可以转换为"`T2` 的右值引用"，若 `T2` 与 `T1` **引用兼容**（reference-compatible，[[dcl.init.ref]]）——即 `T2` 是 `T1` 本身或其基类，cv 不少于 `T1`。

- 若不是位域，结果指代该对象或其指定的**基类子对象**；
- 若是**位域**，先对位域施行左值到右值转换，然后把得到的 prvalue 作为本节其余部分的操作数（于是最终绑定到一个临时量）；
- 若 `T2` 是 `T1` 的不可访问或二义基类，"需要这种转换的程序"非良构。

这就是 `std::move` 的语言基础：**它不移动任何东西，只是把左值标记为亡值**，让重载决议选中移动构造函数/移动赋值运算符。

```cpp run title="lvalue-to-xvalue.cpp" ok
#include <string>
#include <type_traits>

struct B {};
struct D : B {};
struct BF { int b : 3; };

int main() {
    std::string s = "hello";
    std::string t = static_cast<std::string&&>(s);   // 等同于 std::move(s)：调用移动构造
    D d;
    B&& br = static_cast<B&&>(d);                     // 指代 d 的 B 子对象
    BF bf{1};
    int&& r = static_cast<int&&>(bf.b);               // 位域：先读值，再绑定到临时量
    static_assert(std::is_same_v<decltype(static_cast<int&&>(bf.b)), int&&>);
    (void)br;
    return (t == "hello" && r == 1) ? 0 : 1;
}
```

## 转换到 `void`（¶4）

¶4：**任何**表达式都可以显式转换为 cv `void`，此时操作数是一个**弃值表达式**（[[expr.context]]）。注 1：这样的 `static_cast` 是 `void` 类型的 prvalue，没有结果。注 2：若值位于临时对象中，该对象的析构函数照常在通常的时间执行。

用途：明确表示"我故意丢弃这个值"，压制 `[[nodiscard]]` 和"未使用"警告；在 `,` 运算符中阻止用户重载的 `operator,` 被选中（`(void)a, b`）。

## "能初始化就能转换"（¶5）

¶5 是 `static_cast` 最宽的一条。"否则"（即不属于 ¶2–¶4）时，表达式 `E` 能显式转换为类型 `T`，只要满足以下之一：

1. 存在从 `E` 到 `T` 的**隐式转换序列**（[[over.best.ics]]）；
2. 对 `T` 类型对象或引用从 `E` 进行**直接初始化**时，重载决议能找到**至少一个可行函数**（[[over.match.viable]]）——这就把 **`explicit` 构造函数和 `explicit` 转换函数**纳入了进来；
3. `T` 是**聚合**类型，有第一个元素 `x`，且存在从 `E` 到 `x` 的类型的隐式转换序列 {{c++20}}（配合圆括号聚合初始化 [[P0960R3]]）。

效果：若 `T` 是引用类型，如同声明 `T t(E);` 并使用 `t`；否则结果对象从 `E` **直接初始化**。

```cpp run title="static-cast-init.cpp" ok
struct Ex { explicit Ex(int) {} };
struct Conv { explicit operator int() const { return 7; } };
struct Agg { int a; double b; };

int main() {
    double d = static_cast<double>(3);     // 隐式转换（int → double）
    long l = static_cast<long>(3.9);       // 隐式转换（浮点 → 整数，截断）
    Ex e = static_cast<Ex>(1);             // explicit 构造函数：直接初始化可行
    int i = static_cast<int>(Conv{});      // explicit 转换函数：直接初始化可行
    Agg g = static_cast<Agg>(1);           // C++20：聚合，以 1 初始化第一个元素 a
    const int& cr = static_cast<const int&>(42);   // 引用：如同 const int& t(42);
    (void)e;
    return (d == 3.0 && l == 3 && i == 7 && g.a == 1 && cr == 42) ? 0 : 1;
}
```

注 3：转换到**不可访问或二义的基类**时非良构。注 4：若 `T` 是"`U` 的未知边界数组"，这一直接初始化把表达式的类型定为 `U[1]`。

!!! lawyer "Clang 与注 4"
    按注 4，`decltype(static_cast<int[]>(1))` 应为 `int[1]`。本机 Clang 给出的是 `int[]`（`static_assert(std::is_same_v<decltype(static_cast<int[]>(1)), int[1]>)` 失败）。注 4 本身不具规范效力，但它描述的是 [[dcl.init]] 中"以圆括号初始化未知边界数组时确定边界"规则的推论，所以这是 Clang 与标准的一个分歧。

¶5 也解释了为什么 `static_cast` 能做**窄化**：窄化只在列表初始化中被禁止，`static_cast<int>(3.9)` 走的是直接初始化，允许。

## 其余的转换（¶6）

¶6："否则"，对操作数施行左值到右值、数组到指针、函数到指针转换，可以用 `static_cast` 进行的转换**列举如下**（¶7–¶12），**除此之外的转换都不能用 `static_cast` 完成**。这些基本都是**某个标准转换的逆向**：

| 条款 | 转换 | 对应的正向隐式转换 |
|---|---|---|
| ¶7 | 有作用域枚举 → 整型 / 浮点 | （无隐式转换；有作用域枚举故意不隐式转换） |
| ¶8 | 整型/枚举/浮点 → 枚举 | 无作用域枚举 → 整型（整型提升） |
| ¶9 | 浮点 → 任意其他浮点 | 浮点转换（[[conv.double]]，对扩展浮点类型只允许等级不降） |
| ¶10 | 指向基类的指针 → 指向派生类的指针 | 派生类指针 → 基类指针（[[conv.ptr]]） |
| ¶11 | 派生类成员指针 → 基类成员指针 | 基类成员指针 → 派生类成员指针（[[conv.mem]]） |
| ¶12 | `void*` → `T*` | `T*` → `void*`（[[conv.ptr]]） |

## 有作用域枚举 → 数值（¶7）

¶7：有作用域枚举的值可以显式转换为**整型**：结果等同于先转换到枚举的**底层类型**，再转换到目标类型。也可以转换为**浮点类型**：结果等同于把原值转换为该浮点类型。

```cpp run title="scoped-enum-out.cpp" ok
enum class Color : unsigned char { red = 1, big = 200 };

int main() {
    int a = static_cast<int>(Color::big);            // 200
    signed char b = static_cast<signed char>(Color::big);   // 先到 unsigned char 200，再转 signed char：模 2^8，-56
    double c = static_cast<double>(Color::red);      // 1.0
    return (a == 200 && b == -56 && c == 1.0) ? 0 : 1;
}
```

（C++20 起有符号整数采用二进制补码，整数转换"模 2^N"的结果是确定的，见 [[conv.integral]]。）

## 数值 → 枚举（¶8）

¶8：整型或枚举类型的值可以显式转换为**完整的**枚举类型。

- 枚举有**固定底层类型**（有作用域枚举总是有；无作用域枚举写了 `: type` 才有）：值先经整型提升或整型转换变为底层类型，再变为枚举类型——**总是有定义**，任何底层类型的值都是合法的枚举值。
- 枚举**没有固定底层类型**：若原值在枚举的**值域**（range of the enumeration values，[[dcl.enum]]）之内，值不变；**否则行为未定义**。
- **浮点**值也可以转换为枚举：等同于先把原值转换为枚举的底层类型（[[conv.fpint]]，截断；超出范围是 UB），再转换为枚举。

无固定底层类型的枚举的"值域"是能表示所有枚举符的**最小位域**的范围：`enum E { a, b, c };` 的枚举符是 0–2，需要 2 位，值域是 0–3。所以 `static_cast<E>(3)` 合法，`static_cast<E>(4)` 是 UB。

```cpp title="enum-range.cpp" error
enum E { a, b, c };                          // 无固定底层类型，值域 [0, 3]
enum F : unsigned char { x };                // 固定底层类型

constexpr E e1 = static_cast<E>(3);          // OK：在值域内（虽然不等于任何枚举符）
constexpr E e2 = static_cast<E>(4);          // error: UB，常量求值中必须诊断
constexpr F f1 = static_cast<F>(255);        // OK：固定底层类型，任何 unsigned char 值都合法
constexpr F f2 = static_cast<F>(300);        // OK：300 先整型转换为 unsigned char（44）
```

Clang 在常量求值中会给出"integer value 4 is outside the valid range of values [0, 3] for the enumeration type 'E'"。运行期则不检查（UBSan 的 `-fsanitize=enum` 只检查**读取**枚举对象时的值）。

为什么无固定底层类型的枚举要这样规定？因为编译器可以利用值域做优化：例如 `switch` 覆盖了所有可能的值域后省略默认分支，或者用更窄的类型存储。有固定底层类型的枚举则被视为"带名字常量的整数类型"，常用作强类型的 ID 或位标志，必须容纳任何值。

## 浮点之间（¶9）

¶9：浮点类型的 prvalue 可以显式转换为**任何其他**浮点类型：

- 若源值能在目标类型中**精确表示**，结果就是那个精确值；
- 若源值介于目标类型的**两个相邻值之间**，结果是二者之一，**由实现定义**选哪个（通常按当前舍入模式）；
- **否则行为未定义**（源值超出目标类型的范围，例如把 `1e300` 转换为 `float`）。

为什么这一条要单独列出？因为 C++23 引入了**扩展浮点类型**（`std::float16_t`、`std::bfloat16_t` 等，[[basic.extended.fp]]），它们之间的隐式转换只允许**等级不降**（[[conv.double]]）。`double` → `std::float16_t` 不能隐式进行，必须 `static_cast`——这条规则就是那扇门。

!!! lawyer "IEEE 754 下什么叫“超出范围”"
    若目标类型能表示无穷大（IEEE 754，`std::numeric_limits<float>::has_infinity`），那么 `+inf` 也是 `float` 的一个值，`1e300` 就落在 `FLT_MAX` 与 `+inf` 这"两个相邻值之间"，按第二条成为实现定义的选择而非 UB。主流实现正是这样处理的：本机 Clang 在常量求值中接受 `constexpr float f = static_cast<float>(1e300);` 并得到 `+inf`。对没有无穷大的浮点格式，第三条的 UB 才真正适用。

## 指针的向下转换（¶10）

¶10：类型为"指向 *cv1* `B` 的指针"的 prvalue（`B` 是类类型）可以转换为"指向 *cv2* `D` 的指针"，`D` 是从 `B` 派生的**完整**类，*cv2* 不少于 *cv1*。限制与 ¶2 相同：虚基类（或虚基类的基类）非良构；不可访问或二义非良构。空指针值转换为目标类型的空指针值。若 `B` 对象**确实是** `D` 对象的基类子对象，结果指向外围的 `D`；**否则 UB**。

```cpp title="ptr-downcast-rules.cpp" error
struct VB {};
struct VD : virtual VB {};
struct B {};
struct PD : private B {};
struct A {};
struct L : A {};
struct R : A {};
struct M : L, R {};

VD* f(VB* p) { return static_cast<VD*>(p); }   // error: 经虚基类
PD* g(B* p)  { return static_cast<PD*>(p); }   // error: 私有基类
M*  h(A* p)  { return static_cast<M*>(p); }    // error: A 是 M 的二义基类
M*  k(L* p)  { return static_cast<M*>(p); }    // OK：L 是 M 的无二义基类
```

与 `dynamic_cast` 的对比：

| | `static_cast<D*>(pb)` | `dynamic_cast<D*>(pb)` |
|---|---|---|
| 检查 | 无（编译期偏移调整） | 运行期检查动态类型 |
| 错误时 | UB | 空指针 |
| 要求多态 | 否 | 是 |
| 经虚基类 | 非良构 | 可以 |
| 交叉转换 | 非良构 | 可以 |
| 代价 | 一次加/减常量（并检查空指针） | 运行时库调用 |

注意"并检查空指针"：当基类子对象偏移非零时，`static_cast` 必须先检查 `pb` 是否为空——空指针减偏移仍应为空指针。所以即使是 `static_cast`，多重继承下的指针转换也不是"零开销"。

## 成员指针的向上转换（¶11）

¶11：类型为"`D` 的成员指针，类型为 *cv1* `T`"的 prvalue 可以转换为"`B` 的成员指针，类型为 *cv2* `T`"，其中 `D` 是完整类、`B` 是 `D` 的基类，*cv2* 不少于 *cv1*（注 5：函数类型没有 cv，这里的 cv 只对数据成员有意义）。

注意方向：**隐式**成员指针转换是"基类 → 派生类"（[[conv.mem]]：基类的成员当然也是派生类的成员），所以 `static_cast` 的逆向是"派生类 → 基类"。限制：若不存在从"`B` 的成员指针"到"`D` 的成员指针"的有效标准转换，非良构。空成员指针转换为空成员指针。

结果：若 `B` **包含**原成员，或者是包含原成员的类的**基类**，结果成员指针指向原成员；**否则 UB**。注 6：`B` 本身不必包含原成员；但随后用这个成员指针做间接访问时，对象的**动态类型**必须包含原成员（[[expr.mptr.oper]]）。

```cpp run title="pm-upcast.cpp" ok
struct B { int b = 1; };
struct D : B { int d = 2; };

int main() {
    int D::* pmd = &D::d;
    int B::* pmb = static_cast<int B::*>(pmd);   // OK：B 是"包含原成员 d 的类"D 的基类
    D obj;
    B& br = obj;
    int v = br.*pmb;      // OK：br 的动态类型 D 包含成员 d
    return v == 2 ? 0 : 1;
    // 若 br 指代一个纯粹的 B 对象，br.*pmb 是 UB（[expr.mptr.oper]）
}
```

这条规则是 Qt 信号槽、早期 MFC 消息映射之类"在基类中存储派生类成员函数指针"的技术基础。

## `void*` → `T*`（¶12）

¶12：类型为"指向 *cv1* `void` 的指针"的 prvalue 可以转换为"指向 *cv2* `T` 的指针"，`T` 是对象类型，*cv2* 不少于 *cv1*。结果分三种情况：

1. 若原指针值表示内存中字节的地址 `A`，而 `A` **不满足** `T` 的对齐要求：结果指针值**未指定**；
2. 否则，若原指针值**指向对象 *a***，且存在一个类型与 `T` 相似、与 *a* **指针可互转**（pointer-interconvertible，[[basic.compound]]）的对象 *b*：结果**指向 *b***；
3. 否则，**指针值不变**。

第 2 条是 C++17（[[P0137R1]]）引入的对象模型的关键：指针不再只是"地址"，还携带"指向哪个对象"的信息。从 `void*` 回到 `T*` 时，只有在那个地址上**真的有**一个可以"跳过去"的 `T` 对象时，结果才指向 `T` 对象。指针可互转的情形包括：同一个对象；联合体与其成员；标准布局类对象与其第一个非静态数据成员（或基类子对象）。

第 3 条意味着：若那里没有可互转的 `T` 对象，结果指针**仍然指向原来的对象**（只是类型变成了 `T*`）——通过它访问就可能违反 [[basic.lval#11]] 的严格别名规则。

```cpp run title="void-to-T.cpp" ok
struct S { int first; double second; };   // 标准布局

int main() {
    S s{1, 2.0};
    void* vp = &s;
    int* pi = static_cast<int*>(vp);       // OK：s 与 s.first 指针可互转 ⇒ pi 指向 s.first
    *pi = 10;                              // OK
    int x = 5;
    void* vx = &x;
    int* px = static_cast<int*>(vx);       // 指向同一个对象 x
    return (s.first == 10 && px == &x) ? 0 : 1;   // 标准例 2：往返得到原指针值
}
```

```cpp run title="void-to-T-alias.cpp" ub
int main() {
    float f = 1.0f;
    void* vp = &f;
    int* pi = static_cast<int*>(vp);   // 合法：没有可互转的 int 对象，指针值不变（仍指向 f）
    return *pi;                        // UB: 经 int 左值读取 float 对象，违反严格别名规则
}
```

这正是 `reinterpret_cast<T*>(p)` 的定义方式：[[expr.reinterpret.cast#7]] 规定对象指针之间的 `reinterpret_cast` 就是 `static_cast<cv T*>(static_cast<cv void*>(v))`。所以"`static_cast` 经 `void*` 中转"并不比 `reinterpret_cast` 更安全——两者完全等价。

### C++26：常量求值中的 `void*` → `T*`

C++26（[[P2738R1]]）允许在常量表达式中把 `void*` 转换为 `T*`，前提是指针确实指向一个类型与 `T` 相似的对象。这让 `std::any`、类型擦除的函数包装器等可以在编译期工作。C++23 及之前，常量求值中的这种转换直接使表达式不是常量表达式。

```cpp run title="constexpr-void-cast.cpp" ok
constexpr int f() {
    int x = 42;
    void* p = &x;
    return *static_cast<int*>(p);   // C++26 起可以出现在常量求值中
}
static_assert(f() == 42);

int main() {}
```

本机 Clang 在 `-std=c++23` 下拒绝此例（"cast from 'void *' is not allowed in a constant expression in C++ standards before C++2c"），在 `-std=c++2c` 下接受。

## `static_cast` 不能做的事

```cpp title="static-cast-no.cpp" error
struct A {};
struct B {};

void f(const int* cp, int* ip, A* pa, void (*fp)()) {
    static_cast<int*>(cp);       // error: 去掉 const —— 用 const_cast
    static_cast<long*>(ip);      // error: 无关指针类型 —— 用 reinterpret_cast（或经 void*）
    static_cast<B*>(pa);         // error: 无继承关系
    static_cast<long>(ip);       // error: 指针 → 整数 —— 用 reinterpret_cast
    static_cast<void*>(fp);      // error: 函数指针 → 对象指针 —— 有条件支持，只能用 reinterpret_cast
}
```

## 历史与演进

!!! history
    - **C++98**：引入四个具名转换，取代 C 风格转换的大部分用途。
    - **C++11**：¶3 左值到右值引用（为移动语义服务）；有作用域枚举的转换（¶7）。
    - **C++17**：[[P0137R1]] 引入指针可互转与"指针指向对象"的模型，¶12 改写为当前形式；无固定底层类型的枚举值域外转换由"未指定"改为 UB（CWG issue 解决）。
    - **C++20**：聚合的"第一个元素"情形（¶5，配合 [[P0960R3]]）；有符号整数二进制补码使整数转换结果确定。
    - **C++23**：扩展浮点类型使 ¶9 的显式浮点转换变得必要。
    - **C++26**：常量求值中的 `void*` → `T*`（[[P2738R1]]）。

## 陷阱

!!! pitfall "向下转换写错了类型：静默的 UB"
    `static_cast<Derived*>(base_ptr)` 在类型不对时不会失败，只会给你一个错误偏移的指针。在不能保证类型的地方用 `dynamic_cast`，或者用 `assert(dynamic_cast<D*>(p))` 在调试构建中检查。

!!! pitfall "`static_cast<E>(n)` 对无固定底层类型的枚举可能是 UB"
    从网络或文件读入的整数转换为枚举前，要么给枚举指定底层类型，要么先检查范围。

!!! pitfall "“经 `void*` 中转”不是类型双关的合法途径"
    `static_cast<int*>(static_cast<void*>(&f))` 与 `reinterpret_cast<int*>(&f)` 完全等价；读取结果都违反严格别名规则。合法的位模式重新解释请用 `std::bit_cast` 或 `std::memcpy`（见 [[topics/casts]]）。

## 思考题

!!! question "思考题 1"
    `struct B {}; struct D : B {}; B b; D&& r = static_cast<D&&>(std::move(b));` 是否良构？行为如何？

<details markdown="1">
<summary>答案</summary>

良构：¶2 允许"cv1 `B` 的亡值"转换为"cv2 `D` 的右值引用"（`D` 派生自 `B`，非虚、可访问、无二义）。但 `b` 不是任何 `D` 对象的基类子对象，所以行为未定义——即使之后不使用 `r`，转换本身就已经是 UB。
</details>

!!! question "思考题 2"
    `enum class E : int { a }; float f = 3.9f;` 下，`static_cast<E>(f)` 是否合法？结果是什么？`static_cast<E>(1e20f)` 呢？

<details markdown="1">
<summary>答案</summary>

合法（¶8 最后一句，浮点可转换为枚举）：等同于先把 3.9f 转换为底层类型 `int`（截断为 3，[[conv.fpint]]），再转换为 `E`，结果是值为 3 的 `E`。`1e20f` 截断后的值超出 `int` 的范围，[[conv.fpint]] 规定为 UB。
</details>

!!! question "思考题 3"
    为什么 `static_cast<int B::*>(&D::d)` 被允许，而 `int B::* p = &D::d;` 不行？哪一个方向是"安全的"？

<details markdown="1">
<summary>答案</summary>

隐式成员指针转换的方向是 `int B::*` → `int D::*`：`B` 的任何成员都是 `D` 的成员，所以对任何 `D` 对象使用它都安全。反方向 `int D::*` → `int B::*` 并非对每个 `B` 对象都有意义（纯 `B` 对象没有 `d` 成员），所以只能显式 `static_cast`（¶11），并由程序员保证使用时对象的动态类型包含该成员。这与指针转换恰好方向相反：`D*` → `B*` 是隐式安全的，`B*` → `D*` 需要 `static_cast`。
</details>

## 小结

!!! summary
    | 条款 | 转换 | 失败/错误时 |
    |---|---|---|
    | ¶2 | `B` 左值/亡值 → `D&`/`D&&` | 非真子对象 ⇒ UB；虚基/不可访问/二义 ⇒ 非良构 |
    | ¶3 | 左值 → `T&&`（`std::move`） | 不可访问/二义基类 ⇒ 非良构 |
    | ¶4 | 任意 → `void` | — |
    | ¶5 | 隐式转换、显式构造/转换函数、聚合首元素 | 按初始化规则 |
    | ¶7 | 有作用域枚举 → 整数/浮点 | — |
    | ¶8 | 整数/枚举/浮点 → 枚举 | 无固定底层类型且超出值域 ⇒ UB |
    | ¶9 | 浮点 → 浮点 | 超出范围 ⇒ UB；介于两值之间 ⇒ 实现定义 |
    | ¶10 | `B*` → `D*` | 非真子对象 ⇒ UB |
    | ¶11 | `T D::*` → `T B::*` | 不含原成员 ⇒ UB |
    | ¶12 | `void*` → `T*` | 未对齐 ⇒ 未指定值；无可互转对象 ⇒ 指针值不变 |
