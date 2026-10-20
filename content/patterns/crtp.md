---
title: CRTP 与静态多态
summary: 派生类把自己作为模板实参传给基类（class D : public Base<D>）：这种写法为什么能编译，static_cast<D&>(*this) 为什么安全，它和虚函数在代码生成与对象大小上的差别，标准库里的用法，常见陷阱，以及 C++23 的显式对象形参取代了它的哪些用途。
status: draft
order: 35
since: c++98
papers: P0847R7, P2387R3, P0515R3
related: temp.inst, temp.point, expr.static.cast, class.cdtor, class.access.base, dcl.fct, view.interface, range.adaptor.object, util.smartptr.enab, patterns/mixin, patterns/policy-based-design, patterns/nvi, patterns/type-erasure, topics/concepts, toolchain/object-layout-and-vtables
tags: CRTP, 静态多态, 模板, deducing this, 惯用法
updated: 2026-10-19
---

!!! tldr
    - CRTP 让基类模板以派生类为实参：`class D : public Base<D>`。基类在成员函数里用 `static_cast<D&>(*this)` 拿到派生类对象，调用哪个函数在编译期就确定了。
    - 它能编译，是因为类模板实例化时只生成成员函数的声明，函数体要等用到时才实例化，那时 `D` 已经完整。反过来，基类的成员声明（成员类型、形参和返回类型）不能用 `D` 的成员。
    - 与虚函数相比，CRTP 没有 vptr，调用可以内联；代价是没有公共基类型，不同派生类不能放进同一个容器，每个 `D` 各生成一份代码。
    - 模板实参写错（`class E : public Base<D>`）时，`static_cast` 是未定义行为，编译器不报错。把基类构造函数设为私有、再声明 `friend D`，可以把它变成编译错误。
    - C++23 的显式对象形参（deducing this）取代了只为调用派生类成员而写的 CRTP。需要每个派生类一份静态数据、需要以 `D` 为形参的非成员运算符，或者需要通过基类引用保留 `D` 时，仍然要用 CRTP。

## 基类想调用派生类的函数

几种图形共享一段打印逻辑，只有面积的算法不同。通常的写法是把面积声明成虚函数：

<div class="compare" markdown="1">

```cpp
struct Shape {
  virtual double area() const = 0;
  void print() const {
    std::printf("%.2f\n", area());
  }
protected:
  ~Shape() = default;
};

struct Square : Shape {
  double s = 2;
  double area() const override {
    return s * s;
  }
};
```

```cpp
template<class D>
struct Shape {
  void print() const {
    auto& d = static_cast<const D&>(*this);
    std::printf("%.2f\n", d.area());
  }
protected:
  ~Shape() = default;
};

struct Square : Shape<Square> {
  double s = 2;
  double area() const { return s * s; }
};
```

</div>

左边，每个 `Square` 对象带一个指向虚函数表的指针（vptr），`print` 通过它间接调用 `area`。如果程序里每一处调用点都知道对象的具体类型，基类只是用来共享代码，这次运行期分派就是多余的。

右边，基类是一个模板，派生类把自己作为模板实参传进去。`Shape<Square>::print` 知道 `*this` 其实是一个 `Square` 的基类子对象，把它转换成 `const Square&`，直接调用 `Square::area`。这种写法叫 **CRTP**（curiously recurring template pattern，奇异递归模板模式）。

调用哪个函数在模板实例化时就确定了，这叫**静态多态**；虚函数在运行时按对象的动态类型选择函数，叫动态多态。下面是一个完整的程序：

```cpp run title="crtp-shape.cpp" ok
#include <cstdio>

template<class D>
class Shape {
public:
  double area() const {                      // 公共接口
    return self().area_impl();               // 转给派生类的实现
  }
  void print() const {
    std::printf("%s: %.2f\n", self().name(), area());
  }
protected:
  Shape() = default;
  ~Shape() = default;
private:
  const D& self() const { return static_cast<const D&>(*this); }
};

class Square : public Shape<Square> {
  double s_;
public:
  explicit Square(double s) : s_(s) {}
  double area_impl() const { return s_ * s_; }
  const char* name() const { return "square"; }
};

class Circle : public Shape<Circle> {
  double r_;
public:
  explicit Circle(double r) : r_(r) {}
  double area_impl() const { return 3.14159 * r_ * r_; }
  const char* name() const { return "circle"; }
};

template<class D>
void report(const Shape<D>& s) { s.print(); }

int main() {
  report(Square{2});                         // square: 4.00
  report(Circle{1});                         // circle: 3.14
  static_assert(sizeof(Square) == sizeof(double));
}
```

`Shape<Square>` 和 `Shape<Circle>` 是两个互不相关的类。`report` 是函数模板，每个实例都知道参数的具体类型。基类不含数据成员，作为空基类不占空间，`Square` 的大小就是一个 `double`。

接口函数 `area` 和实现函数 `area_impl` 用不同的名字，构造函数和析构函数设为 `protected`，这两点的原因见后文的陷阱一节。

## 为什么能编译

在 `class Square : public Shape<Square>` 这一行，`Square` 的定义还没有结束，它是一个不完整类型（[[g:incomplete-type]]）。而基类必须是完整的类（[[class.derived.general#2]]），所以编译器在这里隐式实例化 `Shape<Square>`（[[temp.inst#2]]），此时 `D` 是不完整的。

类模板特化的隐式实例化只生成成员函数的声明，不生成定义（[[temp.inst#3]]）。非虚成员函数的定义只在需要时才实例化（[[temp.inst#12]]）。所以实例化 `Shape<Square>` 时，`area`、`print`、`self` 只有声明，函数体里的 `static_cast<const D&>` 还没有被检查。

`main` 调用 `print` 时才需要 `Shape<Square>::print` 的定义。它的实例化点（[[g:point-of-instantiation]]）紧跟在引用它的命名空间作用域声明之后，在这里就是 `main` 的定义之后（[[temp.point#1]]）；翻译单元末尾也是它的实例化点（[[temp.point#7]]）。两个位置都在 `Square` 的定义之后，`Square` 已经完整，`static_cast` 和对 `area_impl` 的调用都能通过。

!!! note "这和完整类上下文无关"
    成员函数体是所在类的完整类上下文（[[g:complete-class-context]]，[[class.mem.general#10]]），在其中这个类被视为完整（[[class.mem.general#11]]）。这条规则让 `Shape` 的成员函数体可以使用 `Shape` 中后声明的成员，但它说的是 `Shape` 自己，不涉及 `D`。`D` 在函数体里完整，完全是因为函数体推迟到了 `D` 定义之后才实例化。

### 基类的声明不能用 D 的成员

函数体推迟实例化，成员声明却不推迟。基类想用派生类的成员类型时就会出错：

```cpp title="member-type.cpp" error
#include <vector>

template<class D>
struct Container {
  using value_type = typename D::value_type;   // error
  value_type first() const {
    return static_cast<const D&>(*this).data().front();
  }
};

struct IntBag : Container<IntBag> {
  using value_type = int;
  std::vector<int> v{1, 2, 3};
  const std::vector<int>& data() const { return v; }
};
```

本机 Clang 23 报告 `no type named 'value_type' in 'IntBag'`，并指出实例化来自 `struct IntBag : Container<IntBag>` 这一行。`Container<IntBag>` 是在 `IntBag` 的基类列表里实例化的，这时在 `IntBag` 的类作用域里查找，只能找到已经声明的成员，而此时一个都还没有（见 [[basic.scope]] 中同样的例子）。

成员函数的形参类型和返回类型同样属于声明，写 `typename D::value_type first() const` 也会失败。有三种常见的绕法：

```cpp run title="deferred-types.cpp" ok
#include <vector>

template<class D>
struct Container {
  auto first() const {                        // 返回类型在实例化函数体时推导
    return static_cast<const D&>(*this).data().front();
  }
  template<class Self = D>
  typename Self::value_type second() const {  // 推迟到调用时才替换
    return static_cast<const Self&>(*this).data()[1];
  }
};

struct IntBag : Container<IntBag> {
  using value_type = int;
  std::vector<int> v{1, 2, 3};
  const std::vector<int>& data() const { return v; }
};

int main() { IntBag b; return b.first() + b.second(); }   // 退出码 3
```

第一种用 `auto` 返回类型，类型在函数体实例化时才推导。第二种把成员写成默认实参为 `D` 的成员模板，声明里的 `Self::value_type` 要到调用时才替换；标准库的 `view_interface::operator[]` 就是这样写的（[[view.interface]]）。第三种是在 `D` 之前声明一个特征类（traits class）的特化，让基类从特征类而不是从 `D` 取类型，这种做法需要多写一个特化，但成员类型可以在类的层面上使用。

## static_cast 为什么是安全的

`static_cast<const D&>(*this)` 是从基类到派生类的向下转换。[[expr.static.cast#2]] 允许把 `B` 类型的左值转换成 `D&`，条件是：`D` 是完整类型，`B` 是 `D` 的非虚基类，并且从 `D*` 到 `B*` 的标准转换有效，也就是 `B` 是可访问、无歧义的基类。如果被转换的 `B` 对象确实是某个 `D` 对象的基类子对象，结果就指向那个 `D` 对象；否则行为未定义。

!!! std
    If the object of type "cv1 B" is actually a base class subobject of an object of type D, the result refers to the enclosing object of type D. Otherwise, the behavior is undefined.

    转换本身不做运行期检查。只要 `Shape<D>` 只被 `D` 继承，`*this` 就一定是某个 `D` 的子对象，转换就有定义。

这与 `dynamic_cast` 不同，它不读取任何运行期信息，也不要求类是多态的。编译器只需要在编译期算出基类子对象在 `D` 里的偏移。单继承时偏移通常是 0，转换不生成任何指令；基类不在开头时就是减去一个常量：

```cpp title="offset.cpp" ok
struct Other { long x; };
template<class D> struct Base {
  long b;
  const D& self() const { return static_cast<const D&>(*this); }
};
struct D : Other, Base<D> { long d; };

const D& down(const Base<D>& b) { return b.self(); }
```

本机 Clang 23 以 `-O2` 为 x86-64 Linux 生成的 `down` 只有 `lea rax, [rdi - 8]` 和 `ret` 两条指令。

## 与虚函数比较：大小与代码生成

把同一个 `area` 分别写成虚函数和 CRTP，比较对象大小和一个不内联的调用者：

```cpp title="codegen.cpp" ok
struct VShape {
  virtual double area() const = 0;
  virtual ~VShape() = default;
};
struct VSquare final : VShape {
  double s;
  double area() const override { return s * s; }
};
double twice_v(const VShape& x) { return x.area() * 2; }

template<class D>
struct Shape {
  double area() const { return static_cast<const D&>(*this).area_impl(); }
};
struct Square : Shape<Square> {
  double s;
  double area_impl() const { return s * s; }
};
template<class D>
double twice(const Shape<D>& x) { return x.area() * 2; }
template double twice(const Shape<Square>&);   // 显式实例化，便于看汇编

static_assert(sizeof(VSquare) == 16);          // vptr + double（本机 64 位目标）
static_assert(sizeof(Square) == 8);            // 只有 double
```

本机 Clang 23，`-O2 -target x86_64-linux-gnu -masm=intel`：

<div class="compare" markdown="1">

```text
twice_v(VShape const&):
  push  rax
  mov   rax, qword ptr [rdi]   ; 读 vptr
  call  qword ptr [rax]        ; 间接调用
  addsd xmm0, xmm0
  pop   rax
  ret
```

```text
twice<Square>(Shape<Square> const&):
  movsd xmm0, qword ptr [rdi]
  mulsd xmm0, xmm0             ; 已内联
  addsd xmm0, xmm0
  ret
```

</div>

虚函数版本要读 vptr、再读表项、再间接调用，`area` 的函数体无法内联到调用者里。CRTP 版本里 `area` 和 `area_impl` 都内联了，只剩一次乘法和一次加法。

差别只在编译器不知道动态类型的地方才存在。同一个文件里加上 `double local_v(double s) { VSquare q; q.s = s; return twice_v(q); }`，Clang 内联 `twice_v` 后知道 `q` 的类型就是 `VSquare`，把调用去虚化（devirtualize），生成的代码和 CRTP 版本一样短。参数类型是 `final` 类的引用时也一样。vptr 和虚函数表的布局见 [[toolchain/object-layout-and-vtables]]。

CRTP 的代价在别处：

| | 虚函数 | CRTP |
|---|---|---|
| 对象大小 | 多一个 vptr | 不变（空基类不占空间） |
| 调用 | 间接调用，通常不能内联 | 直接调用，可以内联 |
| 公共基类型 | 有，`VShape&` 能指向任何派生类 | 没有，`Shape<Square>` 与 `Shape<Circle>` 无关 |
| 异构容器 | `vector<unique_ptr<VShape>>` | 不能直接放，需要 `variant` 或类型擦除 |
| 使用方 | 普通函数，可以放在 .cpp 里 | 必须是模板，定义放在头文件 |
| 代码体积 | 一份 | 每个 `D` 各实例化一份 |
| 新增派生类 | 不需要重新编译使用方 | 使用方要重新实例化 |

需要运行时才决定具体类型时，CRTP 帮不上忙，应当用虚函数、`std::variant` 或 [[patterns/type-erasure|类型擦除]]。

## 典型用法

### 由一个运算符生成其余运算符

C++20 之前，比较运算符要一个一个写。CRTP 基类可以根据派生类提供的 `<` 生成其余几个：

```cpp run title="ordered.cpp" ok
#include <cstdio>

template<class D>
struct Ordered {                       // 由 < 推出其余比较
  friend bool operator> (const D& a, const D& b) { return b < a; }
  friend bool operator<=(const D& a, const D& b) { return !(b < a); }
  friend bool operator>=(const D& a, const D& b) { return !(a < b); }
  friend bool operator!=(const D& a, const D& b) { return a < b || b < a; }
};

struct Version : Ordered<Version> {
  int major, minor;
  Version(int ma, int mi) : major(ma), minor(mi) {}
  friend bool operator<(const Version& a, const Version& b) {
    return a.major < b.major || (a.major == b.major && a.minor < b.minor);
  }
};

int main() {
  Version a{1, 2}, b{1, 10};
  std::printf("%d %d %d\n", a < b, a >= b, a != b);   // 1 0 1
}
```

这些运算符是定义在类内的友元函数，只能通过实参依赖查找（[[g:argument-dependent-lookup|ADL]]）找到，这种函数叫隐藏友元（[[g:hidden-friend]]）。`Version` 的基类 `Ordered<Version>` 是它的关联类（[[basic.lookup.argdep#3.3]]），关联类的友元函数在 ADL 中可见（[[basic.lookup.argdep#4.2]]），所以 `a >= b` 能找到 `Ordered<Version>` 里的 `operator>=`。形参写成 `const D&` 而不是 `const Ordered&`，比较的两边就必须是同一个派生类。

C++20 起，这个用途基本被预置的 `<=>` 取代（[[P0515R3]]）：

```cpp run title="spaceship.cpp" ok
#include <compare>
#include <cstdio>

struct Version {
  int major, minor;
  auto operator<=>(const Version&) const = default;   // 同时隐式声明 ==
};

int main() {
  Version a{1, 2}, b{1, 10};
  std::printf("%d %d %d\n", a < b, a >= b, a != b);   // 1 0 1
}
```

预置的 `<=>` 会隐式声明一个预置的 `==`（[[class.compare.default#4]]），`a >= b` 和 `a != b` 由重写候选处理，见 [[class.compare]]。只有当比较语义不是逐成员比较时，才需要自己写 `<=>` 或 `==`。

### 每个派生类一份静态数据

```cpp run title="counted.cpp" ok
#include <cstdio>

template<class D>
class Counted {
  static inline int alive_ = 0;          // Counted<Socket> 和 Counted<File> 各一份
protected:
  Counted() { ++alive_; }
  Counted(const Counted&) { ++alive_; }
  ~Counted() { --alive_; }
public:
  static int alive() { return alive_; }
};

struct Socket : Counted<Socket> {};
struct File   : Counted<File>   {};

int main() {
  Socket a, b;
  {
    File f;
    Socket c = a;
    std::printf("%d %d\n", Socket::alive(), File::alive());   // 3 1
  }
  std::printf("%d %d\n", Socket::alive(), File::alive());     // 2 0
}
```

这里基类根本没有用到 `D` 的成员，`D` 只起区分作用：每个派生类得到一个不同的基类特化，也就各有一个 `alive_`。如果用一个普通基类，所有派生类会共享同一个计数。

### 标准库中的 CRTP 基类

- `std::enable_shared_from_this<T>`：派生类从它继承 `shared_from_this()`，得到与已有 `shared_ptr` 共享所有权的 `shared_ptr<T>`。基类需要 `T` 才能写出返回类型 `shared_ptr<T>`（[[util.smartptr.enab]]）。
- `std::ranges::view_interface<D>`：派生类只写 `begin` 和 `end`，基类根据迭代器的类别提供 `empty`、`operator bool`、`size`、`front`、`back`、`operator[]` 等（[[view.interface]]）。
- `std::ranges::range_adaptor_closure<D>`（{{c++23}}，[[P2387R3]]）：继承它的函数对象可以用 `|` 接在范围后面，也可以和其他适配器组合（[[range.adaptor.object]]）。

```cpp run title="std-crtp.cpp" ok
#include <cstdio>
#include <ranges>
#include <vector>

class IntSpan : public std::ranges::view_interface<IntSpan> {
  int* first_ = nullptr;
  int* last_ = nullptr;
public:
  IntSpan() = default;
  IntSpan(int* f, int* l) : first_(f), last_(l) {}
  int* begin() const { return first_; }
  int* end() const { return last_; }
};

struct Doubled : std::ranges::range_adaptor_closure<Doubled> {
  auto operator()(std::ranges::viewable_range auto&& r) const {
    return std::views::transform(std::forward<decltype(r)>(r),
                                 [](int x) { return 2 * x; });
  }
};
inline constexpr Doubled doubled;

int main() {
  std::vector<int> v{1, 2, 3, 4};
  IntSpan s{v.data(), v.data() + v.size()};
  std::printf("%zu %d %d %d\n", s.size(), s.front(), s.back(), s[2]);  // 4 1 4 3
  for (int x : v | std::views::reverse | doubled)
    std::printf("%d ", x);                                             // 8 6 4 2
  std::puts("");
}
```

### 给虚函数提供统一的实现

CRTP 也可以和虚函数配合。多态的 `clone` 在每个派生类里写法都一样，只是类型不同，可以由一个夹在中间的 CRTP 类统一提供：

```cpp run title="clone.cpp" ok
#include <cstdio>
#include <memory>

struct Animal {
  virtual ~Animal() = default;
  virtual std::unique_ptr<Animal> clone() const = 0;
  virtual const char* name() const = 0;
};

template<class D>
struct Clonable : Animal {
  std::unique_ptr<Animal> clone() const override {
    return std::make_unique<D>(static_cast<const D&>(*this));
  }
};

struct Cat : Clonable<Cat> {
  const char* name() const override { return "cat"; }
};
struct Dog : Clonable<Dog> {
  const char* name() const override { return "dog"; }
};

int main() {
  std::unique_ptr<Animal> a = std::make_unique<Dog>();
  std::puts(a->clone()->name());   // dog
}
```

<details class="fine" markdown="1"><summary>虚函数的实例化点</summary>

`Clonable<Cat>::clone` 是虚函数，按 [[temp.inst#12]]，实现是否在实例化类时一并实例化它是未指明的。按 [[temp.point#5]]，虚函数的实例化点紧跟在 `Clonable<Cat>` 的实例化点之后，那时 `Cat` 还不完整，函数体里的 `static_cast<const D&>` 和 `make_unique<D>` 都需要完整的 `D`。[[temp.point#7]] 又把翻译单元末尾也算作它的实例化点，那时 `Cat` 已经完整。本机 Clang 23 接受这个程序并正确运行，实现普遍在翻译单元末尾实例化这类函数，但标准措辞对这种情形并不清晰。

</details>

## 陷阱

### 模板实参写错

复制粘贴一个派生类时，很容易忘记改基类的模板实参：

```cpp run title="wrong-derived.cpp" ub
#include <cstdio>

template<class D>
struct Shape {
  double area() const { return static_cast<const D&>(*this).area_impl(); }
};

struct Square : Shape<Square> {
  double s = 2;
  double area_impl() const { return s * s; }
};

struct Circle : Shape<Square> {               // 忘了改成 Shape<Circle>
  double r = 1;
  double area_impl() const { return 3.14159 * r * r; }
};

int main() {
  Circle c;
  std::printf("%f\n", c.area());  // UB: *this 不是某个 Square 的基类子对象
}
```

这个程序能编译，因为 `Square` 确实从 `Shape<Square>` 公有派生，转换满足 [[expr.static.cast#2]] 的所有编译期条件。但 `c` 里的 `Shape<Square>` 子对象不属于任何 `Square` 对象，转换的行为未定义。本机运行输出 `1.000000`：`Square::area_impl` 把 `Circle` 的 `r` 当成了 `s`。UBSan 没有报告，它的类型检查只针对多态类。

把基类的构造函数设为私有，只让 `D` 成为友元，就能把这个错误挡在编译期：

```cpp title="guard.cpp" error
template<class D>
class Shape {
public:
  double area() const { return static_cast<const D&>(*this).area_impl(); }
private:
  Shape() = default;
  friend D;                                   // 只有 D 能构造 Shape<D>
};

struct Square : Shape<Square> {
  double s = 2;
  double area_impl() const { return s * s; }
};

struct Circle : Shape<Square> {
  double r = 1;
  double area_impl() const { return 3.14159 * r * r; }
};

int main() {
  Square s;                                   // OK
  Circle c;                                   // error
}
```

`friend D;` 中的 `D` 是模板形参，当它指一个类类型时，这个类成为友元（[[class.friend#3]]）。`Circle` 的隐式默认构造函数要调用 `Shape<Square>` 的私有构造函数，`Circle` 不是 `Shape<Square>` 的友元，所以这个默认构造函数被定义为弃置。本机 Clang 23 在 `Circle c;` 处报告 `call to implicitly-deleted default constructor of 'Circle'`，并说明原因是 `base class 'Shape<Square>' has an inaccessible default constructor`。`Circle` 如果自己写了构造函数，错误会出现在那个构造函数的定义处。

### 构造函数和析构函数的访问权限

CRTP 基类不是用来单独创建对象的，构造函数通常设为 `protected`（或者像上一节那样设为私有加友元）。析构函数也应当是 `protected` 且非虚：基类没有虚析构函数，通过 `Shape<Square>*` 删除一个 `Square` 是未定义行为（[[expr.delete]]），设为 `protected` 后这样的 `delete` 无法编译：

```cpp title="protected-dtor.cpp" error
template<class D>
struct Shape {
protected:
  ~Shape() = default;
};
struct Square : Shape<Square> { double s = 2; };

void destroy(Shape<Square>* p) { delete p; }   // error
```

本机 Clang 23 报告 `calling a protected destructor of class 'Shape<Square>'`。

`protected` 构造函数有一个副作用：没有用户声明构造函数的派生类是聚合（[[g:aggregate]]），用 `{}` 初始化它时，基类子对象在调用方的上下文里初始化，那里访问不到 `protected` 构造函数：

```cpp title="aggregate.cpp" error
template<class D>
class Shape {
protected:
  Shape() = default;
};
struct Square : Shape<Square> { double s = 2; };

int main() {
  Square a;          // OK：调用 Square 的隐式默认构造函数
  Square b{};        // error：聚合初始化
}
```

本机 Clang 23 对 `b` 报告 `base class 'Shape<Square>' has protected default constructor`。给派生类写一个构造函数，它就不再是聚合。

### 基类是私有的

用 `class` 定义派生类时，基类默认是私有的：

```cpp title="private-base.cpp" error
template<class D>
struct Shape {
  double area() const { return static_cast<const D&>(*this).area_impl(); }
};

class Square : Shape<Square> {                // 私有继承
public:
  using Shape::area;
  double area_impl() const { return 4; }
};

int main() { return Square{}.area(); }
```

[[expr.static.cast#2]] 要求从 `D*` 到 `B*` 存在有效的标准转换，私有基类在 `Shape<Square>` 的成员里不可访问（[[class.access.base#4]]），转换非良构。本机 Clang 23 报告 `cannot cast private base class 'const Shape<Square>' to 'const Square'`，位置在 `Shape<Square>::area` 的函数体里，附注指出实例化来自 `main` 中的调用。

同样的道理，派生类如果把 `area_impl` 设为私有，基类也调用不到它，需要在派生类里写 `friend Shape;`。这里的 `Shape` 是从基类继承来的注入类名（[[g:injected-class-name]]），指 `Shape<Square>`。

### 接口和实现同名

如果基类的接口函数和它要调用的派生类函数同名，派生类忘了提供实现时，名字查找会找到基类自己的函数：

```cpp run title="recursion.cpp" ub
#include <cstdio>

template<class D>
struct Printable {
  void print() const { static_cast<const D&>(*this).print(); }  // 接口和实现同名
};

struct Point : Printable<Point> {
  int x = 1, y = 2;
  // 忘了写 print()
};

int main() { Point{}.print(); }
```

`Point` 里没有 `print`，`static_cast<const Point&>(*this).print()` 找到的是继承来的 `Printable<Point>::print`，函数无限递归。没有副作用的无限递归违反了前进保证（[[intro.progress#1]]），行为未定义。本机 Clang 23 给出 `-Winfinite-recursion` 警告；`-O0` 下运行时栈溢出崩溃，`-O2` 下进程因 `SIGTRAP` 终止。

接口和实现用不同的名字（`area` 与 `area_impl`），派生类漏写时就是编译错误，而不是运行时的无限递归。这与 [[patterns/nvi|非虚接口]] 把公有接口和可定制部分分开是同一个思路。

### 隐藏不是覆盖

派生类定义了与基类同名的函数时，它隐藏基类的函数，但不覆盖它。结果取决于从哪里调用：

```cpp run title="hiding.cpp" ok
#include <cstdio>

template<class D>
struct Widget {
  const char* name() const { return "widget"; }   // 默认实现
  void show() const {
    std::printf("%s / %s\n",
                name(),                             // Widget::name
                static_cast<const D&>(*this).name());
  }
};

struct Button : Widget<Button> {
  const char* name() const { return "button"; }   // 隐藏 Widget::name
};

int main() {
  Button b;
  b.show();                        // widget / button
  const Widget<Button>& w = b;
  std::printf("%s\n", w.name());   // widget
  std::printf("%s\n", b.name());   // button
}
```

基类里直接写 `name()` 就是 `this->name()`，查找从 `Widget` 开始，找到的是 `Widget::name`；只有通过 `static_cast<const D&>(*this)` 才会从 `Button` 开始查找（[[class.member.lookup]]）。通过 `Widget<Button>&` 调用 `name` 时同理。用 CRTP 提供默认实现时，基类内部的每一处调用都要经过 `self()`，否则就会悄悄用上默认版本。

多层派生时也是这样。`struct Tile : Square` 里再定义一个 `area_impl`，`Tile` 对象调用 `area()` 仍然走 `Shape<Square>`，调用的是 `Square::area_impl`，因为基类只知道 `Square`。

### 在基类构造函数里调用派生类

基类的构造函数在派生类的成员初始化之前运行。这时通过 `static_cast` 调用派生类的成员函数，函数会访问还没有构造的成员：

```cpp run title="ctor-call.cpp" ub
#include <cstdio>
#include <string>

template<class D>
struct Registered {
  Registered() {
    std::printf("registering %s\n", static_cast<D&>(*this).key().c_str());
  }
};

struct Plugin : Registered<Plugin> {
  std::string name = "a-plugin-with-a-long-name";
  const std::string& key() const { return name; }
};

int main() { Plugin p; }   // UB: name 还没有构造
```

`Plugin` 对象正在构造，对正在构造的对象调用成员函数是允许的（[[class.cdtor#4]]），所以 `key()` 这个调用本身没有问题。问题在于 `name` 的构造还没有开始，它的生存期没有开始，对它调用 `c_str()` 是未定义行为（[[basic.life#8]]）。本机运行时输出了乱码，ASan 和 UBSan 都没有报告。

虚函数在这里至少是有定义的：构造期间的虚调用落到正在构造的那个类的版本上（[[class.cdtor#4]]），不会调用到派生类。CRTP 绕过了这层保护，所以基类的构造函数和析构函数里不应当调用派生类的成员。派生类构造完成后才需要做的事，交给派生类自己的构造函数，或者在对象构造完后由调用方显式调用。

## C++23：显式对象形参

C++23 允许非静态成员函数把对象参数写成显式的第一个形参（[[dcl.fct#7]]，[[P0847R7]]）。它常被称作 deducing this：把这个形参写成模板，`Self` 就会被推导为调用对象的实际类型，基类因此不必再是模板。

<div class="compare" markdown="1">

```cpp
template<class D>
struct Shape {
  double area() const {
    return static_cast<const D&>(*this)
        .area_impl();
  }
};

struct Square : Shape<Square> {
  double s;
  double area_impl() const {
    return s * s;
  }
};
```

```cpp
struct Shape {
  template<class Self>
  double area(this const Self& self) {
    return self.area_impl();
  }
};

struct Square : Shape {
  double s;
  double area_impl() const {
    return s * s;
  }
};
```

</div>

右边对 `Square` 对象调用 `area()` 时，`Self` 推导为 `Square`，`self` 就是 `const Square&`，不需要任何转换，也就不存在实参写错和私有基类的问题。这样的函数叫显式对象成员函数（[[g:explicit-object-member-function]]，[[dcl.fct#8]]）。

两者的差别在于 `Self` 是从调用处的静态类型推导出来的。通过基类引用调用时，`Self` 就是基类：

```cpp run title="deducing-this.cpp" ok
#include <cstdio>

struct Shape {
  template<class Self>
  double area(this const Self& self) { return self.area_impl(); }
  template<class Self>
  void print(this const Self& self) {
    std::printf("%s: %.2f\n", self.name(), self.area());
  }
};

struct Square : Shape {
  double s;
  explicit Square(double s) : s(s) {}
  double area_impl() const { return s * s; }
  const char* name() const { return "square"; }
};

void report(const auto& s) { s.print(); }

int main() {
  Square q{2};
  q.print();                       // square: 4.00，Self = Square
  report(q);                       // square: 4.00
  [[maybe_unused]] const Shape& base = q;
  // base.print();                 // error: Self = Shape，Shape 没有 name
}
```

取消最后一行的注释，本机 Clang 23 报告 `no member named 'name' in 'Shape'`，来自 `Shape::print<Shape>` 的实例化。CRTP 的 `const Shape<Square>&` 仍然知道 `D` 是 `Square`，显式对象形参的 `const Shape&` 已经丢掉了这个信息。

多层派生时，结论反过来。前面的 `Tile : Square` 例子里，CRTP 版本调用 `Square::area_impl`；改用显式对象形参后，`Tile{}.area()` 推导出 `Self = Tile`，调用的是 `Tile::area_impl`。本机实测两者分别返回 4 和 5。

显式对象形参取代了只为在成员函数里拿到派生类类型而写的 CRTP。下面这些情形仍然需要 CRTP：

| 需求 | 为什么显式对象形参做不到 |
|---|---|
| 每个派生类一份静态数据（如 `Counted<D>`） | 显式对象形参只出现在成员函数里，类本身只有一个 |
| 以 `D` 为形参的非成员运算符（如 `Ordered<D>`） | 隐藏友元不是成员函数，没有对象参数可以推导 |
| 基类的成员类型、构造函数、析构函数要用到 `D` | 这些都不是可以带显式对象形参的成员函数（[[dcl.fct#7]]） |
| 通过基类引用或指针调用时仍要分派到 `D` | `Self` 只能推导出静态类型 |
| 标准库接口规定了 CRTP 基类 | `view_interface`、`enable_shared_from_this`、`range_adaptor_closure` 都以 `D` 为模板实参 |

显式对象形参还有一个限制：这样的成员函数不能是虚函数（[[dcl.fct#7]]），带模板形参的版本也只能定义在头文件里。

## CRTP 与 concepts

想要求 `D` 提供 `area_impl`，最直接的写法是在基类的模板头里加约束，但这一定会失败：

```cpp title="constrained-base.cpp" error
#include <concepts>

template<class T>
concept HasAreaImpl = requires(const T& t) {
  { t.area_impl() } -> std::convertible_to<double>;
};

template<HasAreaImpl D>                         // 约束 D
struct Shape {
  double area() const { return static_cast<const D&>(*this).area_impl(); }
};

struct Square : Shape<Square> {                 // error
  double s = 2;
  double area_impl() const { return s * s; }
};
```

模板头的约束在形成 `Shape<Square>` 时就要检查，而那时 `Square` 还在基类列表里，什么成员都没有。本机 Clang 23 报告 `constraints not satisfied for class template 'Shape' [with D = Square]`，原因是 `no member named 'area_impl' in 'Square'`。

约束要放在推迟检查的地方。成员函数的 *requires-clause* 不随类一起实例化（[[temp.inst#19]]），只在重载决议用到这个函数时才检查；函数体里的 `static_assert` 则在函数体实例化时检查。

```cpp run title="crtp-concepts.cpp" ok
#include <concepts>
#include <cstdio>

template<class T>
concept HasAreaImpl = requires(const T& t) {
  { t.area_impl() } -> std::convertible_to<double>;
};

template<class D>
struct Shape {
  double area() const requires HasAreaImpl<D> {   // 调用 area 时才检查
    return static_cast<const D&>(*this).area_impl();
  }
protected:
  Shape() = default;
  ~Shape() {                                       // 每个 D 的析构函数被定义时检查
    static_assert(HasAreaImpl<D>, "D must provide area_impl()");
  }
};

template<class T>
concept AShape = std::derived_from<T, Shape<T>>;   // T 是一个 CRTP 派生类

void report(const AShape auto& s) { std::printf("%.2f\n", s.area()); }

struct Square : Shape<Square> {
  double s = 2;
  double area_impl() const { return s * s; }
};

int main() {
  Square sq;
  report(sq);                                      // 4.00
}
```

加上一个 `struct Blob : Shape<Blob> {};` 并在 `main` 里创建 `Blob` 对象，本机 Clang 23 报告 `static assertion failed: D must provide area_impl()`，附注指向 `Blob` 的定义和不满足的要求。不放 `static_assert` 的话，只有调用 `blob.area()` 时才报错。

`AShape` 这样的概念可以用来约束接受 CRTP 派生类的函数模板，它比 `const Shape<D>&` 形参更宽松：`report` 的形参就是派生类本身，不发生到基类的转换。注意它和私有构造函数加友元不是一回事：前文的 `Circle : Shape<Square>` 仍然不满足 `AShape<Circle>`，但 `Shape<Square>` 内部无法用概念发现自己被错误地继承了。

再进一步，如果只需要静态多态而不需要基类提供任何实现，可以完全不用继承，直接用概念约束函数模板：`void report(const HasAreaImpl auto& s)`。CRTP 的价值在于基类能给派生类添加成员，这是概念做不到的。概念的规则见 [[topics/concepts]]。

## 什么时候用

| 情形 | 建议 |
|---|---|
| 运行时才知道具体类型，需要异构容器 | 虚函数、`std::variant` 或 [[patterns/type-erasure|类型擦除]] |
| 基类的成员函数要调用派生类的成员，C++23 可用 | 显式对象形参 |
| 每个派生类需要独立的静态数据 | CRTP |
| 给派生类生成以 `D` 为形参的非成员函数或运算符 | CRTP；比较运算符优先用预置的 `<=>` 和 `==` |
| 基类的声明要用到派生类的类型 | CRTP，配合 `auto` 返回类型、默认模板实参或特征类 |
| 只需要对一组类型统一调用，不需要共享实现 | 用概念约束的函数模板，不需要继承 |
| 多个独立的功能片段要按需组合 | 见 [[patterns/mixin|mixin]] 和 [[patterns/policy-based-design|基于策略的设计]] |

## 思考题

!!! question "1"
    把私有继承一节的 `class Square : Shape<Square>` 保留为私有继承，只在 `Square` 里加一句 `friend Shape;`，程序能编译吗？

<details markdown="1">
<summary>答案</summary>

能。`static_cast` 要求从 `Square*` 到 `Shape<Square>*` 的转换在 `Shape<Square>::area` 里有效。按 [[class.access.base#4]]，如果转换发生在 `Square` 的成员或友元里，私有基类是可访问的；`Shape<Square>` 是 `Square` 的友元类，它的成员函数体可以使用 `Square` 的私有成员和私有基类（[[class.friend#2]]）。本机 Clang 23 编译通过，程序返回 4。

私有继承加友元可以把 CRTP 基类当作纯实现细节：外界不能把 `Square&` 转换成 `Shape<Square>&`，需要公开的接口用 `using Shape::area;` 逐个引出。
</details>

!!! question "2"
    `struct Tile : Square` 重新定义了 `area_impl`。用 CRTP 写的 `Shape<Square>` 和用显式对象形参写的 `Shape`，`Tile{}.area()` 分别调用谁的 `area_impl`？

<details markdown="1">
<summary>答案</summary>

CRTP 版本调用 `Square::area_impl`。`Tile` 的基类是 `Square`，而 `Square` 的基类固定为 `Shape<Square>`，`static_cast<const Square&>(*this).area_impl()` 从 `Square` 开始查找，看不到 `Tile` 里的同名函数。

显式对象形参版本调用 `Tile::area_impl`。`Self` 从对象表达式 `Tile{}` 推导为 `Tile`，`self.area_impl()` 从 `Tile` 开始查找，找到 `Tile::area_impl`，它隐藏了 `Square::area_impl`。本机实测分别返回 4 和 5。

两种结果都不是虚函数意义上的覆盖：CRTP 绑定到继承时写下的 `D`，显式对象形参绑定到调用处的静态类型。
</details>

!!! question "3"
    `crtp-concepts.cpp` 里，如果把 `main` 改成 `report(Square{});`，会发生什么？

<details markdown="1">
<summary>答案</summary>

编译失败。`Square` 没有用户声明的构造函数，基类又是公有的，它是聚合，`Square{}` 是聚合初始化（[[dcl.init.aggr]]）。基类子对象 `Shape<Square>` 在 `main` 的上下文里初始化，访问不到它的 `protected` 构造函数；临时对象在 `main` 里销毁，`protected` 析构函数同样不可访问。本机 Clang 23 报告 `base class 'Shape<Square>' has protected default constructor` 和 `temporary of type 'Shape<Square>' has protected destructor`。

`Square sq;` 没有问题，它调用的是 `Square` 的隐式默认构造函数，基类构造函数在 `Square` 的成员里调用，可以访问。给 `Square` 加一个构造函数后，`Square{}` 也能编译。
</details>
