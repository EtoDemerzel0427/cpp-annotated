---
title: 内置运算符
summary: 为了让内建运算符参与运算符重载决议而设想的候选函数清单，以及它们与用户写的运算符竞争时带来的歧义和意外。
status: draft
since: c++98
papers: P2864R2
related: over.match.oper, over.oper, expr.compound, expr.cond, conv.prom, expr.arith.conv, expr.spaceship, over.ics.rank
tags: 重载决议, 运算符, 内建运算符
updated: 2026-10-19
---

!!! tldr
    - 只要运算符有一个操作数是类或枚举类型，就要做重载决议。内建运算符以一组设想的函数（如 `int operator+(int, int)`）的身份进入候选集，这一页就是那份清单。
    - 内建候选与用户写的 `operator@` 平等竞争：可能胜出，也可能造成歧义。它们不是没有别的选择时才用的后备。
    - 算术候选只针对提升后的类型；`const` 左值、`bool` 的自增、`void*` 的解引用和算术都没有候选。
    - 选中内建候选之后，类类型操作数只经过用户定义转换本身，再按 [[expr.compound]] 中内建运算符的要求检查，这一步仍可能失败。
    - 双向隐式转换、多个转换函数、同时能转换成指针和 `bool`，是三种最常见的问题来源；把转换函数标为 `explicit` 能解决大部分。

## 为什么需要内建候选

```cpp run ok
struct Meters {
  double v;
  operator double() const { return v; }   // 可以隐式转换为 double
};
int main() {
  Meters m{1.5};
  double d = m + 1;   // 没有接受 Meters 的 operator+，实际做的是 double(m) + 1
  return d == 2.5 ? 0 : 1;
}
```

`m + 1` 有一个类类型的操作数，所以按 [[over.match.oper]] 做重载决议。用户没有写 `operator+`，可它应该能工作。编译器要决定 `m` 经哪个转换函数转换、转换成哪种算术类型，最直接的办法是把内建的 `+` 也写成一组函数放进候选集。

更重要的是用户确实写了 `operator+`、类又能转换成算术类型的情况。这时用户版本和内建版本必须放在一起，按 [[over.match.best]] 比出最佳的一个。内建候选就是为此设想出来的。

¶1 本节规定代表 [[expr.compound]] 中内建运算符的候选函数。它们只按 [[over.match.oper]] 参与运算符的重载决议，不作他用：不能取地址，不能显式调用，名字查找也找不到它们。

注 1 补充了三点：

1. 内建运算符只接受非类类型的操作数，而运算符重载决议只在某个操作数原本是类或枚举类型时发生。所以选中内建候选，要么是类有到合适的非类类型的用户定义转换，要么是枚举能转换成合适的类型。
2. 有些候选比内建运算符本身更宽松。选中之后，表达式还要满足 [[expr.compound]] 的要求（[[over.match.oper#11]]），下文有例子。
3. 如果用户写了一个非模板非成员函数，形参类型和某个内建候选完全相同，这个内建候选就不进入候选集（[[over.match.oper#3.3.4]]）。

## 候选清单（¶2–¶25）

¶2 **提升后的整型**（[[g:promoted-integral-type|promoted integral type]]）指经过整型提升后不变的无 cv 限定整型，例如 `int`、`unsigned`、`long`、`long long`；`char`、`short`、`bool` 会提升成别的类型，所以不算（[[conv.prom]]）。注 2 指出，凡是要求提升后整型的地方，无作用域枚举都可以经整型提升被接受。

候选只用提升后的类型，因为内建算术本来就先做整型提升（[[expr.arith.conv]]），`char + char` 实际上是 `int + int`：

```cpp run ok
struct C { operator char() const { return 'a'; } };
int main() {
  C c;
  auto x = c + c;   // int operator+(int, int)：C 转换为 char，再提升为 int
  static_assert(__is_same(decltype(x), int));
  return x == 2 * 'a' ? 0 : 1;
}
```

¶3 下文的 *vq* 表示 `volatile` 或无限定，不含 `const`。这些形参都是要被修改的左值，`const` 左值不能修改，所以根本不生成相应的候选。

下表按段落列出全部候选。`L`、`R` 一般是无 cv 限定的浮点类型或提升后整型，`LR` 是两者经寻常算术转换得到的类型。

| ¶ | 对哪些类型 | 候选 |
|---|---|---|
| ¶4 | `T`：`bool` 以外的算术类型，或指向对象类型的指针 | `vq T& operator++(vq T&)`、`T operator++(vq T&, int)`，`--` 同理 |
| ¶5 | `T`：对象类型，或没有 cv、引用限定符的函数类型 | `T& operator*(T*)` |
| ¶6 | 任何类型 `T` | `T* operator+(T*)` |
| ¶7 | `T`：浮点类型或提升后整型 | `T operator+(T)`、`T operator-(T)` |
| ¶8 | `T`：提升后整型 | `T operator~(T)` |
| ¶9 | `C1` 是 `C2` 或其派生类，`T` 是对象或函数类型 | `cv12 T& operator->*(cv1 C1*, cv2 T C2::*)` |
| ¶10 | `L`、`R`：浮点类型或提升后整型 | `LR operator* / + -(L, R)`；`bool operator== != < > <= >=(L, R)` |
| ¶11 | `T`：整型 | `std::strong_ordering operator<=>(T, T)` |
| ¶12 | `L`、`R`：浮点类型 | `std::partial_ordering operator<=>(L, R)` |
| ¶13 | `T`：对象类型 | `T* operator+(T*, ptrdiff_t)`、`T* operator+(ptrdiff_t, T*)`、`T* operator-(T*, ptrdiff_t)`、`T& operator[](T*, ptrdiff_t)`、`T& operator[](ptrdiff_t, T*)` |
| ¶14 | `T`：指向对象类型的指针 | `ptrdiff_t operator-(T, T)` |
| ¶15 | `T`：枚举或指针类型 | `bool operator== != < > <= >=(T, T)`、`R operator<=>(T, T)` |
| ¶16 | `T`：成员指针、`std::meta::info`、`std::nullptr_t` | `bool operator==(T, T)`、`bool operator!=(T, T)` |
| ¶17 | `L`、`R`：提升后整型 | `LR operator% & ^ \|(L, R)`；`L operator<< >>(L, R)` |
| ¶18 | `L`：算术类型；`R`：浮点类型或提升后整型 | `vq L& operator= *= /= += -=(vq L&, R)` |
| ¶19 | 任何类型 `T` | `T* vq& operator=(T* vq&, T*)` |
| ¶20 | `T`：枚举或成员指针类型 | `vq T& operator=(vq T&, T)` |
| ¶21 | `T`：对象类型 | `T* vq& operator+= -=(T* vq&, ptrdiff_t)` |
| ¶22 | `L`：整型；`R`：提升后整型 | `vq L& operator%= <<= >>= &= ^= \|=(vq L&, R)` |
| ¶23 | | `bool operator!(bool)`、`bool operator&&(bool, bool)`、`bool operator\|\|(bool, bool)` |
| ¶24 | `L`、`R`：浮点类型或提升后整型 | `LR operator?:(bool, L, R)` |
| ¶25 | `T`：指针、成员指针或有作用域枚举类型 | `T operator?:(bool, T, T)` |

表中凡是说对象类型的地方，都允许带 cv 限定。几处需要说明：

- ¶9 的返回类型只是示意，结果的类型和值类别由 [[expr.mptr.oper]] 决定。
- ¶11、¶12 的结果类型 `std::strong_ordering` 和 `std::partial_ordering` 定义在 `<compare>` 中。没有包含这个头文件时，Clang 报告 `cannot use builtin operator '<=>' because type 'std::strong_ordering' was not found`。¶15 中的 `R` 由 [[expr.spaceship]] 决定。
- ¶16 的 `std::meta::info` {{c++26}} 是静态反射的值类型，只能比较是否相等，不能排序。
- `?:` 不能重载，¶24、¶25 的 `operator?:` 只是为 [[expr.cond#6]] 的重载决议写出的描述（注 3）。无作用域枚举经提升匹配 ¶24，有作用域枚举不能提升，由 ¶25 补上。
- 清单里有几处刻意的空缺：`bool` 没有 `++`、`--`；`void*` 没有 `*`、`++`、指针加减（`void` 不是对象类型）；`const` 左值没有任何赋值或自增候选。

## 经转换使用内建运算

### 能转换成指针的类

类只要能隐式转换成指针，指针上的内建运算就都能直接用于它：

```cpp run ok
int arr[3] = {10, 20, 30};
struct P { operator int*() const { return arr; } };
int main() {
  P p;
  int a = *p;       // ¶5：int& operator*(int*)
  int b = p[1];     // ¶13：int& operator[](int*, ptrdiff_t)
  int c = 2[p];     // ¶13：int& operator[](ptrdiff_t, int*)
  int* d = p + 1;   // ¶13
  auto e = p - p;   // ¶14：ptrdiff_t operator-(int*, int*)
  return a + b + c + *d + int(e) - 80;
}
```

无捕获 lambda 的闭包类型有到函数指针的转换函数，`+[]{}` 正是利用 ¶6 的 `T* operator+(T*)`（`T` 是函数类型）把 lambda 变成函数指针。同理，`*[]{}` 经 ¶5 得到函数引用：

```cpp run ok
int main() {
  auto p = +[](int x) { return x + 1; };
  static_assert(__is_same(decltype(p), int (*)(int)));
  auto& r = *[](int x) { return x * 2; };
  static_assert(__is_same(decltype(r), int (&)(int)));
  return p(1) + r(1) - 4;
}
```

### 哪些情况没有候选

```cpp
int g;
struct R  { operator int&() { return g; } };
struct BR { operator bool&(); };
struct CR { operator const int&(); };
struct VP { operator void*(); };
void f(R r, BR b, CR c, VP v) {
  ++r; r++;          // OK：¶4，int& operator++(int&)
  ++b;               // error: bool 没有 ++ 候选
  ++c;               // error: 没有 const 版本的候选
  ++v;               // error: void* 不指向对象类型
  (void)*v;          // error: ¶5 不包括 void
  (void)(v == v);    // OK：¶15 适用于所有指针类型
}
```

### 赋值的左操作数

[[over.match.oper#5]] 规定，内建赋值运算符的第一个形参只考虑标准转换序列。所以即使类能转换成 `int&`，`r = 1` 也选不中 `int& operator=(int&, int)`：

```cpp error
int g;
struct R { operator int&() { return g; } };
void f(R r) { r = 1; }   // error: 内建候选不可行，R 的隐式复制、移动赋值也不接受 1
```

右操作数没有这个限制，`i = s` 中的 `s` 可以经用户定义转换变成 `int`。

!!! lawyer "复合赋值是否也受限"
    [[expr.assign]] 的 *assignment-operator* 包括 `=` 和所有复合赋值，所以按字面，[[over.match.oper#5]] 也覆盖 `+=` 等，`r += 1` 同样不应选中 ¶18 的候选。截至写作时，Clang 23 接受 `r += 1`，只对 `=` 施加了这条限制。

## 歧义与意外

内建候选和用户候选平等竞争。下面几种情况都是实际代码里常见的。

### 双向转换

```cpp error
struct S {
  S(int);           // int → S
  operator int();   // S → int
};
S operator+(S, S);
void f(S s) {
  s + 1;            // error: 歧义
}
```

用户的 `operator+(S, S)`：`s` 不需要转换，`1` 要经用户定义转换变成 `S`。内建的 `operator+(int, int)`：`s` 要经用户定义转换变成 `int`，`1` 不需要转换。两个候选各在一个实参上更好，所以有歧义（[[over.match.best]]）。把其中一个转换标为 `explicit`（最常见的是 `explicit operator int()`），内建候选就不再可行。

### 多个转换函数

```cpp error
struct S {
  operator int();
  operator double();
};
void f(S s) {
  (void)(s + 1);   // error: 歧义
}
```

`int operator+(int, int)` 和 `double operator+(double, int)` 的第一个实参分别经 `operator int()` 和 `operator double()` 转换。经不同转换函数的用户定义转换序列不能比较（[[over.ics.rank#3.3]]），第二个实参又都不需要转换，分不出高下。

同样的道理，只有一个 `operator double()` 的类型 `D` 写 `d % 2` 也是歧义，而不是报告 `double` 不能取模。¶17 为每一对提升后整型都生成了候选，`D` 经 `double` 再转换成 `int`、`long`、`unsigned` 的序列等级相同，彼此分不出高下。Clang 报告 `use of overloaded operator '%' is ambiguous`。

带模板转换函数的类型也一样：`struct Any { template<class T> operator T(); };` 的 `a + 1` 是歧义，因为每个算术候选都能推导出一个 `T`。

### 指针和 `bool` 两种转换

```cpp run ok
int x = 5;
struct Ptr {
  operator int*() const { return &x; }
  operator bool() const { return true; }
};
int main() {
  Ptr p;
  auto r = p + 1;   // 不是 int* + 1，而是 bool 提升成 int 之后的整数加法
  static_assert(__is_same(decltype(r), int));
  return r - 2;
}
```

指针候选 `int* operator+(int*, ptrdiff_t)` 的第二个实参要从 `int` 转换成 `ptrdiff_t`；整数候选 `int operator+(int, int)` 的第一个实参经 `operator bool` 再提升，第二个实参不需要转换。第一个实参用了不同的转换函数，无法比较，第二个实参上整数候选更好，于是整数加法胜出。C++11 引入 `explicit operator bool`，就是为了避免这类问题。

### 选中之后的检查

[[over.match.oper#11]] 规定，选中内建候选之后，类类型操作数只经过用户定义转换本身，不再做后面的第二个标准转换，然后按 [[expr.compound]] 检查。候选清单里看起来可行的组合，内建运算符本身未必接受：

```cpp error
struct Inc;
struct P { operator Inc*(); };
enum E { e };
struct S { operator E(); };
void f(P p, S s) {
  (void)(p + 1);     // error: ¶13 的候选对任何对象类型都存在，但内建 + 要求完整类型
  (void)(s + 1.0);   // error: 选中 (int, double)，但 s 只转换为 E，枚举与浮点的混合算术非良构
}
```

第二行中，如果把完整的转换序列 `S → E → int` 都做完，`s + 1.0` 就是合法的 `int + double`。但标准只转换到 `E`，于是落入 C++26 对枚举与浮点混合算术的禁止（[[P2864R2]]，[[expr.arith.conv]]）。这样，经转换参与内建运算的类，与直接对转换结果做内建运算，结果保持一致。

### `explicit operator bool` 与 `&&`

```cpp run ok
struct B { explicit operator bool() const { return true; } };
int main() {
  B b;
  bool r = b && !b;   // 主流编译器都接受
  return r;
}
```

[[expr.log.and]] 和 [[expr.unary.op]] 规定 `&&`、`||`、`!` 的操作数按语境转换为 `bool`，explicit 转换函数正是为按语境转换设计的。可是严格按本节和 [[over.match.oper]] 的字面，操作数是类类型，要对 ¶23 的 `bool operator&&(bool, bool)` 做重载决议，而形参的隐式转换序列按复制初始化建模，explicit 转换函数不参与。措辞没有明确说明这里怎样使用按语境转换。所有主流编译器都接受这段代码，`if (p && q)` 这类写法也依赖它。

## 条件运算符（¶24–¶25）

`?:` 不能重载。但第二、三操作数类型不同、至少一个是类类型时，[[expr.cond#6]] 借用 [[over.match.oper]] 和本节的候选来决定怎样转换操作数：

```cpp run ok
struct S { operator int() const { return 1; } };
struct T { operator double() const { return 2.5; } };
int main(int argc, char**) {
  auto x = argc > 0 ? S{} : T{};   // ¶24：double operator?:(bool, int, double)
  static_assert(__is_same(decltype(x), double));
  return x == 1.0 ? 0 : 1;
}
```

!!! impl
    - 候选族是无限的，编译器不会真的生成全部。Clang 先收集每个类类型操作数的转换函数能产生的指针、枚举、成员指针等类型，只为这些类型添加 ¶4–¶25 中相关的候选；算术候选固定为若干提升后类型的组合。
    - 因为只看非模板转换函数的返回类型，对 `template<class T> operator T*()` 这样的模板转换函数，Clang 无法枚举所有 `T*`，`*s` 直接报 `indirection requires pointer operand`。结论（非良构）和按标准推导的一样，理由不同。
    - 诊断里，内建候选通常显示为 `built-in candidate operator+(int, int)` 这样的注释。

## 历史与演进

!!! history
    - C++98 就有这份候选清单，包括用 `operator?:` 描述条件运算符的写法。
    - C++11 加入了 `std::nullptr_t` 的相等比较候选，以及有作用域枚举的 `?:` 候选。
    - C++17 删除了 `bool` 的自增，¶4 因而写着 `bool` 以外。
    - C++20 加入了 `<=>` 的候选（¶11、¶12、¶15）。
    - C++26 加入了 `std::meta::info` 的相等比较（¶16）。[[P2864R2]] 让枚举与浮点、两个不同枚举之间的混合算术非良构，部分经 ¶10 选中的组合会在随后的检查中失败。

## 常见误解

!!! pitfall "内建候选只在没有用户运算符时才用"
    它们和用户候选平等竞争，可能胜出（如上面的 `Ptr`），也可能造成歧义。只有 `,`、一元 `&`、`->` 在没有可行函数时才退回内建运算符（[[over.match.oper#13]]）。

!!! pitfall "类同时有到指针和到 `bool` 的隐式转换"
    `p + 1` 会选中整数加法。转换到 `bool` 应该用 `explicit operator bool`。

## 思考题

!!! question "1. 下面的 `s - t` 选中哪个候选？结果是什么类型？"
    ```cpp
    struct S { operator short() const; };
    struct T { operator unsigned char() const; };
    auto f(S s, T t) { return s - t; }
    ```

<details markdown="1">
<summary>答案</summary>

`int operator-(int, int)`，即 ¶10 中 `L = R = int`。两个实参都是用户定义转换加整型提升。其他组合（如 `long - long`）的第二个标准转换是整型转换，等级低于提升；经同一个转换函数的用户定义转换序列可以按第二个标准转换比较（[[over.ics.rank#3.3]]），所以 `int, int` 胜出。选中之后，`s`、`t` 只转换为 `short` 和 `unsigned char`，再做内建 `-` 的寻常算术转换，结果仍是 `int`。
</details>

!!! question "2. `struct E { operator int*(); operator long*(); }; E e; *e;` 合法吗？"

<details markdown="1">
<summary>答案</summary>

非良构，有歧义。`int& operator*(int*)` 和 `long& operator*(long*)` 都可行，各自经不同的转换函数，无法比较。
</details>
