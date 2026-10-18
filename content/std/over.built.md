---
title: 内置运算符
summary: 为让内建运算符参与运算符重载决议而虚构的"候选运算符函数"全表：自增自减、解引用、算术、比较、三路比较、指针算术、赋值、逻辑、条件运算符；它们为什么存在，为什么比真正的内建运算符更宽松，以及由此产生的歧义与意外。
status: draft
since: c++98
related: over.match.oper, over.oper, expr.compound, expr.cond, conv.prom, expr.arith.conv, expr.spaceship, over.ics.rank
tags: 重载决议, 运算符, 内建运算符
updated: 2026-10-17
---

[[over.match.oper]] 说：只要运算符有一个操作数是类或枚举类型，就做一次重载决议，候选集里除了用户写的 `operator@`，还有一类**内建候选**（[[g:built-in-candidate|built-in candidate]]）。本节就是那份清单——一族"假想的"函数声明，如 `int operator+(int, int)`、`T& operator*(T*)`、`bool operator<(T, T)`（`T` 为指针）。

为什么需要它们？考虑：

```cpp run ok
struct Meters {
  double v;
  operator double() const { return v; }   // 可以隐式变成 double
};
int main() {
  Meters m{1.5};
  double d = m + 1;    // 没有任何 operator+ 接受 Meters——但它应该能工作：double(m) + 1
  return d == 2.5 ? 0 : 1;
}
```

`m + 1` 的操作数中有类类型，所以要做重载决议。用户没写 `operator+`，候选从哪来？如果不把内建的 `+` 也表达成"函数"放进候选集，就无从判断 `m` 应该经哪个转换函数、转换成哪种算术类型。更重要的是，当用户**确实**写了 `operator+`、而类又能转换到算术类型时，用户版本与内建版本必须在**同一张表**上按 [[over.match.best]] 比较。内建候选就是为此虚构的：它们只参与运算符重载决议，**别无他用**（¶1）。

## 定位与总注（¶1）

¶1 本节规定代表 [[expr.compound]] 中内建运算符的候选运算符函数。它们按 [[over.match.oper]] 所述参与运算符重载决议，**不用于任何其他目的**——不能取地址、不能显式调用、不能被名字查找找到。

注 1 包含三层意思，每一层都值得展开：

1. **何时会选中内建候选**：内建运算符只接受非类类型操作数，而运算符重载决议只在某个操作数**原本**是类或枚举类型时发生。所以选中内建候选只有两种途径——类类型操作数有到合适非类类型的**用户定义转换**；或者枚举类型操作数能转换到合适的类型（如经整型提升）。
2. **候选比内建运算符本身更宽松**：选中内建候选后，表达式还要按 [[expr.compound]] 中该内建运算符的要求检查（[[over.match.oper#11]]），那里的额外语义约束仍然适用。下文有多个例子。
3. **同签名的用户候选会让内建候选退出**：[[over.match.oper#3.3.4]] 规定，与某个非模板非成员候选形参类型列表相同的内建候选不进入候选集。

## 术语（¶2–¶3）

¶2 **提升后的整型**（[[g:promoted-integral-type|promoted integral type]]）：经整型提升后保持不变的 cv 无限定整型，例如 `int`、`long`、`unsigned`、`long long`，但**不包括** `char`、`short`、`bool`、`char8_t` 等（它们会被提升成别的类型，[[conv.prom]]）。注 2：凡要求提升后整型的地方，无作用域枚举的操作数都可以经整型提升被接受。

为什么候选只用"提升后的"类型？因为内建算术运算本来就先对操作数做整型提升（[[expr.arith.conv]]），`char + char` 实际上是 `int + int`。只为提升后的类型生成候选，既与内建语义一致，又让候选集小得多。

```cpp run ok
struct C { operator char() const { return 'a'; } };
int main() {
  C c;
  auto x = c + c;     // 选中 int operator+(int, int)：C → char（用户定义）→ int（提升）
  static_assert(__is_same(decltype(x), int));
  return x == 2 * 'a' ? 0 : 1;
}
```

¶3 下文中 *vq* 表示 `volatile` 或无限定。注意**不含 `const`**——这些候选的形参是"被修改的左值"，`const` 左值不能被修改，所以根本不生成相应候选。

## 候选全表（¶4–¶25）

下表按段落列出全部候选族。`L`、`R` 常表示"cv 无限定的浮点或提升后整型"，`LR` 是二者经寻常算术转换的结果类型。

| ¶ | 对哪些类型 | 候选 |
|---|---|---|
| ¶4 | `T`：除 `bool` 外的算术类型，或指向（可能 cv 的）对象类型的指针 | `vq T& operator++(vq T&)`、`T operator++(vq T&, int)`，`--` 同 |
| ¶5 | `T`：（可能 cv 的）对象类型，或没有 cv/引用限定符的函数类型 | `T& operator*(T*)` |
| ¶6 | 每个类型 `T` | `T* operator+(T*)`（一元 `+` 作用于指针） |
| ¶7 | `T`：浮点或提升后整型 | `T operator+(T)`、`T operator-(T)` |
| ¶8 | `T`：提升后整型 | `T operator~(T)` |
| ¶9 | `C1` 是 `C2` 或其派生类，`T` 为对象或函数类型 | `cv12 T& operator->*(cv1 C1*, cv2 T C2::*)` |
| ¶10 | `L`、`R`：浮点或提升后整型 | `LR operator* / + -(L, R)`；`bool operator== != < > <= >=(L, R)` |
| ¶11 | `T`：整型 | `std::strong_ordering operator<=>(T, T)` |
| ¶12 | `L`、`R`：浮点类型 | `std::partial_ordering operator<=>(L, R)` |
| ¶13 | `T`：（可能 cv 的）对象类型 | `T* operator+(T*, ptrdiff_t)`、`T* operator+(ptrdiff_t, T*)`、`T* operator-(T*, ptrdiff_t)`、`T& operator[](T*, ptrdiff_t)`、`T& operator[](ptrdiff_t, T*)` |
| ¶14 | `T`：指向对象类型的指针 | `ptrdiff_t operator-(T, T)` |
| ¶15 | `T`：枚举或指针类型 | `bool operator== != < > <= >=(T, T)`、`R operator<=>(T, T)` |
| ¶16 | `T`：成员指针、`std::meta::info`、`std::nullptr_t` | `bool operator==(T, T)`、`bool operator!=(T, T)` |
| ¶17 | `L`、`R`：提升后整型 | `LR operator% & ^ \|(L, R)`；`L operator<< >>(L, R)` |
| ¶18 | `L`：算术类型；`R`：浮点或提升后整型 | `vq L& operator= *= /= += -=(vq L&, R)` |
| ¶19 | 每个类型 `T` | `T* vq& operator=(T* vq&, T*)` |
| ¶20 | `T`：枚举或成员指针类型 | `vq T& operator=(vq T&, T)` |
| ¶21 | `T`：（可能 cv 的）对象类型 | `T* vq& operator+= -=(T* vq&, ptrdiff_t)` |
| ¶22 | `L`：整型；`R`：提升后整型 | `vq L& operator%= <<= >>= &= ^= \|=(vq L&, R)` |
| ¶23 | — | `bool operator!(bool)`、`bool operator&&(bool, bool)`、`bool operator\|\|(bool, bool)` |
| ¶24 | `L`、`R`：浮点或提升后整型 | `LR operator?:(bool, L, R)` |
| ¶25 | `T`：指针、成员指针或有作用域枚举类型 | `T operator?:(bool, T, T)` |

几处细节：

- ¶9 的返回类型"仅作说明"，真正的结果类型由 [[expr.mptr.oper]] 决定（例如对右值对象应用 `->*`… 这里左操作数是指针，结果总是左值）。
- ¶11–¶12：三路比较的内建候选要用 `std::strong_ordering`/`std::partial_ordering`，所以需要 `#include <compare>`，否则 Clang 报 "cannot use builtin operator '<=>' because type 'std::strong_ordering' was not found"。¶15 中 `R` 由 [[expr.spaceship]] 决定。
- ¶16 的 `std::meta::info` 是 C++26 静态反射加入的 {{c++26}}：反射值只能比较相等，不能排序。
- ¶24 注 3：`?:` 不能重载，这里的"`operator?:`"只是为 [[expr.cond#6]] 的重载决议而写的描述。¶24 没有列出无作用域枚举，因为它们可经提升匹配 `L`、`R`；¶25 才补上有作用域枚举（它们不能提升）。
- 有几个**刻意的空缺**：`bool` 没有 `++`/`--`（C++17 删除了 `bool` 的自增）；`void*` 没有 `*`、`++`、`+ ptrdiff_t`、指针相减（`void` 不是对象类型）；`const` 左值没有任何赋值/自增候选。

## 内建候选的作用：一组例子

### 类经转换成为指针

只要类可以隐式转换为指针，指针上的所有内建运算就都"自动可用"：

```cpp run ok
int arr[3] = {10, 20, 30};
struct P { operator int*() const { return arr; } };
int main() {
  P p;
  int a = *p;           // ¶5：int& operator*(int*)
  int b = p[1];         // ¶13：int& operator[](int*, ptrdiff_t)
  int c = 2[p];         // ¶13：int& operator[](ptrdiff_t, int*)
  int* d = p + 1;       // ¶13
  auto e = p - p;       // ¶14：ptrdiff_t operator-(int*, int*)
  return a + b + c + *d + int(e) - 80;
}
```

### `+lambda` 的秘密

无捕获 lambda 的闭包类型有到函数指针的转换函数。`+[]{}` 中一元 `+` 的操作数是类类型，于是重载决议；唯一可行的是 ¶6 的 `T* operator+(T*)`（`T` 为函数类型）。结果就是函数指针——这是把 lambda "显式退化"为函数指针的惯用法。同理，`*[]{}` 经 ¶5 得到函数引用。

```cpp run ok
int main() {
  auto p = +[](int x) { return x + 1; };
  static_assert(__is_same(decltype(p), int (*)(int)));
  auto& r = *[](int x) { return x * 2; };
  static_assert(__is_same(decltype(r), int (&)(int)));
  return p(1) + r(1) - 4;
}
```

### `->*` 经转换

```cpp run ok
struct A { int m = 7; };
A a;
struct Q { operator A*() const { return &a; } };
int main() {
  Q q;
  int A::* pm = &A::m;
  return q->*pm - 7;    // ¶9：int& operator->*(A*, int A::*)
}
```

### 自增：`int&` 可以，`bool&`、`const int&`、`void*` 不行

```cpp
int g;
struct R { operator int&() { return g; } };
struct BR { operator bool&(); };
struct CR { operator const int&(); };
struct VP { operator void*(); };
void f(R r, BR b, CR c, VP v) {
  ++r; r++;      // OK：¶4，int& operator++(int&)
  ++b;           // error: bool 没有 ++ 候选
  ++c;           // error: 没有 const 版本的候选
  ++v;           // error: void* 不是指向对象类型的指针
  (void)*v;      // error: 同上，¶5 不覆盖 void
  (void)(v == v);  // OK：¶15 对所有指针类型
}
```

### 赋值：左操作数只考虑标准转换

[[over.match.oper#5]]：内建赋值运算符的**第一个**形参只考虑标准转换序列。所以即使类能转换为 `int&`，`r = 1` 也不会选中 `int& operator=(int&, int)`：

```cpp error
int g;
struct R { operator int&() { return g; } };
void f(R r) { r = 1; }    // error: 内建候选不可行；R 的隐式拷贝/移动赋值也无法接受 1
```

!!! lawyer "复合赋值也受限吗？"
    [[expr.assign]] 中 *assignment-operator* 包括 `=` 与全部复合赋值，所以从字面看，[[over.match.oper#5]] 的"内建赋值运算符"也覆盖 `+=` 等，`r += 1` 同样不应选中 ¶18 的候选。但截至写作时 Clang 23 接受 `r += 1`（只对 `=` 施加限制）。

而右操作数没有限制：

```cpp run ok
struct I { operator int() const { return 3; } };
int main() {
  int i = 0;
  I s;
  i = s;      // ¶18：int& operator=(int&, int)，右侧经用户定义转换
  i += s;
  return i - 6;
}
```

## 歧义与意外

内建候选不是"兜底"——它们与用户候选**平等竞争**，这会带来歧义，也会带来出人意料的"胜出"。

### 用户运算符 vs 内建运算符：转换方向相反

```cpp error
struct S {
  S(int);              // int → S
  operator int();      // S → int
};
S operator+(S, S);
void f(S s) {
  s + 1;               // error: 歧义
}
```

- 用户 `operator+(S, S)`：`s` 恒等；`1 → S` 用户定义转换。
- 内建 `operator+(int, int)`：`s → int` 用户定义转换；`1` 恒等。

两者各在一个实参上更好，歧义（[[over.match.best]]）。这是"双向隐式转换"类型的经典问题。解法：把其中一个转换标为 `explicit`（最常见的是 `explicit operator int()`），内建候选便不再可行。

### 多个转换函数：同等的用户定义转换无法比较

```cpp error
struct S {
  operator int();
  operator double();
};
void f(S s) {
  (void)(s + 1);      // error: 歧义
}
```

`int operator+(int, int)` 与 `double operator+(double, int)` 中，第一个实参分别经 `operator int()` 和 `operator double()`——**不同**转换函数的用户定义转换序列不可比较（[[over.ics.rank#3.3]]），第二个实参都是恒等。无法分出高下。

### `%` 与 `<<`：浮点转换产生的歧义

```cpp error
struct D { operator double(); };
void f(D d) {
  (void)(d % 2);      // error: 歧义——而不是"double 不能取模"
  (void)(1 << d);     // error: 同样歧义
}
```

¶17 为**每一对**提升后整型生成候选：`int % int`、`long % int`、`unsigned % int`……`D → double → int`、`D → double → long` 等都是"用户定义转换 + 浮点-整型转换"，第二标准转换序列的等级相同，彼此不分高下。Clang 报的是 "use of overloaded operator '%' is ambiguous"，而不是直接对 `double % int` 报错——后者只有在 `d` 本身就是 `double` 时才会出现。

### 意外的胜出："智能指针"加上 `operator bool`

```cpp run ok
int x = 5;
struct Ptr {
  operator int*() const { return &x; }
  operator bool() const { return true; }
};
int main() {
  Ptr p;
  auto r = p + 1;     // 你以为是 int* + 1？
  static_assert(__is_same(decltype(r), int));   // 实际是 bool → int 的整数加法！
  return r - 2;
}
```

- `int* operator+(int*, ptrdiff_t)`：`p` 经 `operator int*`；`1 → ptrdiff_t` 是整型**转换**。
- `int operator+(int, int)`：`p` 经 `operator bool` 再**提升**到 `int`；`1` 恒等。

第一个实参用的是不同转换函数，不可比较；第二个实参恒等优于转换。于是 `int + int` 胜出。这正是 C++11 之前"safe bool 惯用法"想要避免的灾难，也是 `explicit operator bool` 的动机。

### 模板转换函数 + 内建候选 = 歧义

```cpp error
struct Any { template<class T> operator T(); };
void f(Any a) {
  (void)(a + 1);      // error: 歧义——每一个算术类型的候选都能经模板转换函数推导出 T
}
```

### 选中之后再检查：候选比运算符宽松

选中内建候选后，类类型操作数**只经用户定义转换本身**（不应用第二标准转换序列）转换，然后按 [[expr.compound]] 检查（[[over.match.oper#11]]）。候选列表中"看起来可以"的组合，内建运算符本身未必接受：

```cpp error
struct Inc;
struct P { operator Inc*(); };
enum E { e };
struct S { operator E(); };
void f(P p, S s) {
  (void)(p + 1);      // error: ¶13 的候选对任何对象类型都存在，但内建 + 要求完整的对象类型
  (void)(s + 1.0);    // error: 候选 (int, double) 被选中，但随后 s 只转换为 E，
                      //        而 C++26 起枚举与浮点的混合算术非良构
}
```

第二行很能说明 ¶11 的设计：如果直接应用完整的转换序列（`S → E → int`），`s + 1.0` 本该是 `int + double`；但标准只应用到 `E`，于是落入 [[expr.arith.conv]] 对"枚举与浮点混合"的禁止（[[diff.cpp23.expr]]）。这样，"类经转换参与内建运算"与"直接对转换结果做内建运算"的行为保持一致。

### `explicit operator bool` 与 `&&`、`!`

```cpp run ok
struct B { explicit operator bool() const { return true; } };
int main() {
  B b;
  bool r = b && !b;   // 各编译器都接受
  return r;
}
```

[[expr.log.and]]、[[expr.unary.op]] 规定 `&&`、`||`、`!` 的操作数**按语境转换**为 `bool`，而 explicit 转换函数正是为按语境转换设计的。但严格按本节与 [[over.match.oper]] 的字面：`b && !b` 的操作数是类类型，要对 ¶23 的候选 `bool operator&&(bool, bool)` 做重载决议，而形参的隐式转换序列是按**拷贝初始化**建模的，explicit 转换函数不参与。措辞上没有明确说明这里如何使用按语境转换；实践中所有主流编译器都接受，`std::unique_ptr` 一类类型也依赖这个行为（`if (p && q)`）。读标准时知道这里有一条缝即可。

## 条件运算符的候选（¶24–¶25）

`?:` 不能重载，但当第二、三操作数类型不同且至少一个是类类型时，[[expr.cond#6]] 借用 [[over.match.oper]] 与本节的候选来决定如何转换操作数：

```cpp run ok
struct S { operator int() const { return 1; } };
struct T { operator double() const { return 2.5; } };
int main(int argc, char**) {
  auto x = argc > 0 ? S{} : T{};    // ¶24：double operator?:(bool, int, double)
  static_assert(__is_same(decltype(x), double));
  return x == 1.0 ? 0 : 1;
}
```

## 实现视角

!!! impl
    - **候选族是无限的**，编译器不会真的生成它们。Clang 先为每个类类型操作数收集其转换函数能产生的指针类型、枚举类型、成员指针类型等（`BuiltinCandidateTypeSet`），再只为这些类型添加 ¶4–¶25 中相关的候选；算术候选则固定为若干提升后类型的组合。
    - 因为只根据**非模板**转换函数的返回类型收集候选类型，对模板转换函数（如 `template<class T> operator T*()`）Clang 无法枚举"所有 `T*`"，于是 `*s` 直接报 "indirection requires pointer operand"——结论（非良构）与按标准逐字推导的结果一致，但理由不同。
    - 诊断中，内建候选通常显示为 "built-in candidate operator+(int, int)" 之类的注释，按标准的写法列出。

## 历史与演进

!!! history
    - **C++98**：本节框架确立，包括 ¶24 的"`operator?:`"描述手法。
    - **C++11**：加入 `std::nullptr_t` 的比较候选；有作用域枚举出现，¶25 为其补上 `?:` 候选（有作用域枚举不能提升，不被 ¶24 覆盖）。
    - **C++17**：删除 `bool` 的 `++`（¶4 中"除 `bool` 外"）。
    - **C++20**：三路比较 `<=>` 的候选（¶11、¶12、¶15）；对 `volatile` 的部分复合操作的弃用不影响候选本身。
    - **C++26**：`std::meta::info` 的相等比较（¶16）；枚举与浮点/其他枚举的混合算术非良构，使部分经 ¶10 选中的组合在随后检查中失败。

## 陷阱

!!! pitfall "类同时有到指针和到 `bool` 的隐式转换"
    `p + 1`、`p == 0` 会选中整数版本。用 `explicit operator bool`。

!!! pitfall "隐式的双向转换"
    同时有非 explicit 的转换构造函数与转换函数，再加上用户运算符，几乎必然与内建候选歧义。

!!! pitfall "以为内建候选只是兜底"
    它们与用户候选平等竞争，可能胜出（如上面的 `Ptr` 例子），也可能造成歧义。只有 `,`、一元 `&`、`->` 是"无可行函数时才回退到内建"（[[over.match.oper#13]]）。

## 思考题

!!! question "1. 下面的 `s - t` 选中哪个候选？结果类型是什么？"
    ```cpp
    struct S { operator short() const; };
    struct T { operator unsigned char() const; };
    auto f(S s, T t) { return s - t; }
    ```

<details markdown="1">
<summary>答案</summary>

`int operator-(int, int)`（¶10 中 `L = R = int`）。两个实参都是"用户定义转换 + 整型提升"；其他组合（如 `long - long`）的第二标准转换序列是整型转换，等级低于提升，而同一转换函数下的用户定义转换序列可以按第二标准转换序列比较（[[over.ics.rank#3.3]]）。选中后，`s`、`t` 只转换为 `short` 与 `unsigned char`，再按内建 `-` 做寻常算术转换——结果仍是 `int`。
</details>

!!! question "2. `struct E { operator int*(); operator long*(); }; E e; *e;` 合法吗？"

<details markdown="1">
<summary>答案</summary>

非良构，歧义。候选 `int& operator*(int*)` 与 `long& operator*(long*)` 都可行，各自经不同的转换函数，彼此不可比较。
</details>

!!! question "3. 为什么 ¶18 的左形参是 `vq L&` 而不是 `const L&`，并且 ¶3 特意把 `const` 排除在 *vq* 之外？"

<details markdown="1">
<summary>答案</summary>

这些候选模拟的是"修改左操作数"的运算。如果存在 `const int& operator=(const int&, int)` 这样的候选，一个转换为 `const int&` 的类对象在重载决议中就会找到"可行"的赋值，随后才在 [[expr.assign]] 的检查中失败——这会在有其他候选时制造莫名的歧义。直接不生成 `const` 版本，让这类候选在第一步就不存在，结果更清晰。`volatile` 则是可修改的，所以保留。
</details>

## 小结

!!! summary
    - 内建候选是**虚构的函数声明**，只用于运算符重载决议，使"类经转换后用内建运算"能与用户运算符同台比较。
    - 算术候选只针对**提升后**的类型；`const` 左值、`bool` 自增、`void*` 解引用/算术都没有候选。
    - 选中内建候选后，类操作数只经用户定义转换本身转换，再按 [[expr.compound]] 检查——候选比运算符宽松，可能在这一步失败。
    - 常见后果：双向转换导致歧义；多个转换函数导致歧义；`operator bool` 在指针算术中意外胜出。用 `explicit` 收紧转换是根治办法。
