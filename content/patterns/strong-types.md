---
title: 强类型与幻影类型
summary: 用只包着一个值的类把表示相同、含义不同的量分成不同的类型：typedef 为什么做不到，Strong<T, Tag> 模板与幻影标签，按需添加运算，零开销的条件与汇编，enum class 作强整数，标准库里的 chrono::duration、std::byte、align_val_t，单位换算，以及隐式转换、哈希和格式化上的陷阱。
status: draft
order: 85
since: c++11
related: dcl.typedef, dcl.type.elab, temp.arg.type, class.conv.ctor, class.compare.default, class.temporary, class.prop, dcl.init.list, dcl.enum, time.duration, support.types, unord.hash, format.formatter, namespace.std, patterns/crtp, patterns/mixin, topics/special-members-and-elision, toolchain/object-layout-and-vtables
tags: 强类型, 幻影类型, enum class, chrono, 零开销, 惯用法
updated: 2026-10-19
---

!!! tldr
    - `typedef` 和 `using` 只给已有类型起别名，`AccountId` 和 `Cents` 都是 `int` 时，编译器分不清它们。要让编译器检查，就得引入新的类型。
    - `Strong<T, Tag>` 是只有一个 `T` 成员、构造函数为 `explicit` 的类模板，`Tag` 只是一个从不定义的类名，用来让每个特化成为不同的类型。这种只在类型层面起作用的参数叫幻影类型。
    - 运算按需添加：比较用预置的 `<=>`，加法、数乘之类用 CRTP 的 skill 基类混入。基类要自带预置比较，否则派生类的预置 `<=>` 会被定义为删除。
    - 只要类是平凡可复制的，它和裸 `int` 大小相同，`-O2` 下生成的指令完全一样，按值传递时也放在寄存器里；加一个用户提供的析构函数就改成经内存传递。
    - 对整数 ID，`enum class Id : std::uint32_t {}` 是最省事的强类型：C++17 起可以写 `Id{42}`，自带比较和 `std::hash`；但 `std::format` 不认识它，自定义的 `Strong` 也一样需要特化 `std::hash` 和 `std::formatter`。

## 同一种表示，不同的含义

```cpp run title="alias.cpp" ok
#include <cstdio>

using AccountId = int;
using Cents = int;

void transfer(AccountId from, AccountId to, Cents amount) {
  std::printf("%d -> %d: %d\n", from, to, amount);
}

int main() {
  AccountId alice = 17, bob = 42;
  Cents fee = 500;
  transfer(alice, bob, fee);   // 本意
  transfer(fee, alice, bob);   // 参数顺序错了，照样编译
}
```

第二次调用把金额当成了转出账户，编译器没有任何警告，运行时输出 `500 -> 17: 42`。程序本身是良构的，错的是逻辑。三个形参写成了三个不同的名字，看起来像是有类型检查，实际上没有。

原因在 [[dcl.typedef#1]]：typedef 声明的名字是一个**类型别名**（[[g:type-alias|type alias]]），它指向已有的类型，不引入新类型。`using X = Y;` 的别名声明与 typedef 语义相同（[[dcl.typedef#2]]）。

!!! std
    A *typedef-name* does not introduce a new type the way a class declaration or enum declaration does.

    typedef 名不像类声明或枚举声明那样引入新类型。

所以 `AccountId`、`Cents` 和 `int` 是同一个类型，重载决议和类型检查都看不出差别。要让编译器拦住这类错误，只能借助会引入新类型的声明：类，或者枚举。

## 最小的强类型模板

**强类型**（strong type，也叫 strong typedef）指的是一个只包着一个值的类，它和被包的类型表示相同，但彼此不能隐式转换。写成模板，一次定义就能造出任意多个这样的类型：

```cpp run title="strong.cpp" error
#include <compare>

template <class T, class Tag>
class Strong {
  T value_;
public:
  constexpr explicit Strong(T v) : value_(v) {}
  constexpr const T& get() const { return value_; }
  friend constexpr auto operator<=>(const Strong&,
                                    const Strong&) = default;
};

using AccountId = Strong<int, struct AccountIdTag>;
using Cents     = Strong<int, struct CentsTag>;

void transfer(AccountId from, AccountId to, Cents amount);

void test() {
  AccountId alice{17}, bob{42};
  Cents fee{500};
  transfer(alice, bob, fee);   // OK
  transfer(fee, alice, bob);   // error: Cents 不能转换为 AccountId
  transfer(17, 42, 500);       // error: 构造函数是 explicit
  bool b = alice < bob;        // OK：预置的 <=>
  bool c = alice == fee;       // error: 不同类型
}
```

这个模板只有三个部分，每一部分都对应一条语言规则。

- `explicit` 构造函数不参与隐式转换，只在直接初始化和显式转型时使用（[[class.conv.ctor#2]]）。所以 `transfer(17, 42, 500)` 找不到从 `int` 到 `AccountId` 的转换，而 `AccountId{17}` 可以。
- 预置的 `operator<=>` 逐个比较子对象（[[class.compare.default#5]]），类里没有声明 `operator==` 时，还会隐式声明一个预置的 `==`（[[class.compare.default#4]]）。于是 `<`、`==` 等六个比较都有了，而且只在同一个 `Strong` 特化之间成立。
- `get()` 是唯一通往底层值的出口。需要裸值的地方（序列化、调用 C 接口）必须显式写出来，这正是我们想要的。

### 幻影标签

`AccountId` 和 `Cents` 的 `T` 都是 `int`，把它们区分开的只有第二个模板实参。`struct AccountIdTag` 是一个**详述类型说明符**（elaborated type specifier）：在它所在的位置查找 `AccountIdTag` 什么也找不到，它就在最近的外围命名空间里声明一个同名类（[[dcl.type.elab#3]]）。这个类从来没有定义，是一个不完整类型，而类型模板实参本来就可以是不完整类型（[[temp.arg.type#2]] 的注）。

`Strong` 的实现从不使用 `Tag`：不创建 `Tag` 的对象，不取它的大小，也就不需要它完整。这种只出现在类型里、不对应任何数据的模板参数叫**幻影类型**（phantom type）。它的唯一作用是让 `Strong<int, AccountIdTag>` 和 `Strong<int, CentsTag>` 成为两个不同的类模板特化。

标签只认名字。在同一个命名空间里两次写 `Strong<int, struct Tag>`，得到的是同一个类型，因为第二次查找会找到第一次声明的 `Tag`。每个强类型应当用自己专属的标签名。

<details class="fine" markdown="1"><summary>标签会参与 ADL</summary>

实参依赖查找（ADL）为类模板特化收集关联实体时，也会收集各模板实参类型的关联实体（[[basic.lookup.argdep#3.3]]）。如果标签声明在命名空间 `bank` 里，以 `Strong<int, bank::AccountIdTag>` 为实参的无限定调用也会到 `bank` 里找函数。一般无害，但把标签放进一个充满泛型函数模板的命名空间时，可能意外地多出候选函数。
</details>

## 按需添加运算

`Strong` 只提供比较。是否需要别的运算，取决于这个量的含义：账户 ID 相加没有意义，金额可以相加，金额乘以一个比例可以，金额乘以金额不行。合理的做法是让每个强类型自己声明需要哪些运算。

一种常见的写法是把每种运算做成一个 **skill** 基类，用 [[patterns/crtp|CRTP]] 把派生类型传给它，再像 [[patterns/mixin|mixin]] 那样按需继承：

```cpp run title="skills.cpp" ok
#include <compare>
#include <cstdio>
#include <type_traits>

template <class D> struct Addable {
  friend constexpr D operator+(D a, D b) {
    return D{a.get() + b.get()};
  }
  friend constexpr D& operator+=(D& a, D b) { return a = a + b; }
  friend constexpr auto operator<=>(const Addable&,
                                    const Addable&) = default;
};

template <class D> struct Scalable {
  template <class S>
    requires std::is_arithmetic_v<S>
  friend constexpr D operator*(D a, S k) { return D{a.get() * k}; }
  friend constexpr auto operator<=>(const Scalable&,
                                    const Scalable&) = default;
};

template <class T, class Tag, template <class> class... Skills>
class Strong : public Skills<Strong<T, Tag, Skills...>>... {
  T value_;
public:
  constexpr explicit Strong(T v) : value_(v) {}
  constexpr const T& get() const { return value_; }
  friend constexpr auto operator<=>(const Strong&,
                                    const Strong&) = default;
};

using AccountId = Strong<int, struct AccountIdTag>;
using Cents = Strong<long, struct CentsTag, Addable, Scalable>;

static_assert(sizeof(Cents) == sizeof(long));
static_assert(std::is_trivially_copyable_v<Cents>);

int main() {
  Cents a{250}, b{100};
  a += b;
  Cents c = a * 2;
  std::printf("%ld %d\n", c.get(), a < c);
  // AccountId{1} + AccountId{2};  // error: AccountId 没有 Addable
}
```

输出 `700 1`。运算符都写成类内定义的友元函数（hidden friend），它们只能通过 ADL 找到，也就是只在实参里出现 `Cents` 时才参与重载决议，不会污染其他类型的候选集（详见 [[topics/name-lookup-and-customization]]）。`Cents{1} * Cents{2}` 和 `AccountId{1} + AccountId{2}` 都找不到可用的运算符，编译失败。

每个 skill 里那行预置的 `<=>` 不是摆设。预置比较按展开后的子对象列表逐个比较，列表里先是直接基类子对象，再是成员（[[class.compare.default#5]]）。只要有一个子对象的 `<=>` 不可用，预置的 `<=>` 就定义为删除（[[class.spaceship#2]]），`==` 同理（[[class.eq#2]]）。空的 `Addable<D>` 如果不声明比较，`Cents` 的 `<=>` 和 `==` 就都是删除的，Clang 报 `overload resolution selected deleted operator '<=>'`。另一种做法是在 `Strong` 里手写比较，只比 `value_`。

运算该不该提供，可以按量的性质判断：

| 量 | 合理的运算 | 不该有的运算 |
|---|---|---|
| 标识符（ID、句柄） | `==`、哈希，可能还有 `<`（用于有序容器） | 一切算术 |
| 数量（金额、长度、时长） | `+`、`-`、乘除标量、同类相除得到标量 | 同类相乘（量纲变了） |
| 位置（时刻、坐标） | 位置减位置得到数量，位置加减数量 | 位置加位置 |

最后一行就是 `std::chrono` 区分 `time_point` 和 `duration` 的原因：两个时刻相减得到时长，两个时刻相加没有意义。

## 零开销：大小、平凡性与汇编

强类型的价值在于它不比裸值慢。这个承诺有两个前提：对象大小相同，类是平凡可复制的。上面的 `static_assert` 已经验证了前者，`Cents` 有两个空基类，本机 Clang 上大小仍是 `sizeof(long)`，因为两个空基类类型不同，空基类优化让它们不占空间（布局细节见 [[toolchain/object-layout-and-vtables]]）。

!!! impl "MSVC 与多个空基类"
    MSVC 在 x64 上默认只对第一个空基类做空基类优化，后续空基类各占至少一个字节，`Cents` 会变大。给 `Strong` 加上 `__declspec(empty_bases)` 可以改回来。用 skill 基类时值得在代码里放一条 `static_assert(sizeof(...) == sizeof(T))`。

**平凡可复制**（[[g:trivially-copyable-class|trivially copyable]]）的类，复制、移动和析构都不运行用户代码（[[class.prop#1]]）。`Strong` 的特殊成员全部由编译器隐式声明，自然满足。把它和裸 `long` 放在一起编译：

```cpp run title="codegen.cpp" ok flags="-std=c++2c -O2"
template <class T, class Tag>
class Strong {
  T value_;
public:
  constexpr explicit Strong(T v) : value_(v) {}
  constexpr T get() const { return value_; }
};

template <class T, class Tag>
class Logged {                     // 多了一个用户提供的析构函数
  T value_;
public:
  constexpr explicit Logged(T v) : value_(v) {}
  constexpr T get() const { return value_; }
  ~Logged() {}
};

using Cents  = Strong<long, struct CentsTag>;
using LCents = Logged<long, struct CentsTag>;

long  add_raw(long a, long b)       { return a + b; }
Cents add_strong(Cents a, Cents b)  { return Cents{a.get() + b.get()}; }
LCents add_logged(LCents a, LCents b) {
  return LCents{a.get() + b.get()};
}
```

本机 Clang 23 以 `-O2 --target=x86_64-linux-gnu -masm=intel` 生成的函数体（去掉了汇编指示）：

```text
add_raw:                  add_strong:              add_logged:
  lea rax, [rdi + rsi]      lea rax, [rdi + rsi]     mov rax, rdi
  ret                       ret                      mov rcx, qword ptr [rdx]
                                                     add rcx, qword ptr [rsi]
                                                     mov qword ptr [rdi], rcx
                                                     ret
```

`add_strong` 和 `add_raw` 一字不差：两个实参在 `rdi`、`rsi` 里，结果在 `rax` 里。`add_logged` 的每个实参都变成了一个地址（`rsi`、`rdx`），结果写进调用方通过 `rdi` 传来的内存。本机 arm64 上同样如此：前两个函数都是 `add x0, x1, x0; ret`，第三个从 `x0`、`x1` 指向的内存读出两个值，再写到 `x8` 指向的位置。

这条分界线来自 [[class.temporary#3]]。对象按值传入或从函数返回时，如果类至少有一个合格的复制或移动构造函数，且它们都是平凡的，析构函数也平凡或被删除，实现就可以创建临时对象来保存形参和返回值，也就是把它放进寄存器再取出来。

!!! std
    This latitude is granted to allow objects to be passed to or returned from functions in registers.

    给出这一自由，是为了允许在寄存器中传递对象或从函数返回对象。

注意这个条件比平凡可复制宽一点：它不管赋值运算符。`Logged` 只多了一个什么也不做的析构函数，就不再满足条件，Itanium C++ ABI 规定这样的类经内存传递（细节和 `[[clang::trivial_abi]]` 见 [[class.temporary]] 页）。给强类型加日志、调试检查之类的析构函数时，要知道这会改变调用约定。

调用点上的差别也一样消失。用 `skills.cpp` 里的 `Cents` 写一个求和循环，和对 `long` 数组求和的版本比较：

```cpp
long sum_raw(const long* p, std::size_t n) {
  long s = 0;
  for (std::size_t i = 0; i < n; ++i) s += p[i];
  return s;
}
Cents sum_strong(const Cents* p, std::size_t n) {
  Cents s{0};
  for (std::size_t i = 0; i < n; ++i) s += p[i];
  return s;
}
```

本机 `-O2` 下，两个函数生成的指令序列逐条相同（x86-64 上 35 条，都向量化成了 `paddq`；arm64 上 39 条）。`operator+=`、`operator+`、构造函数和 `get()` 全部内联，什么也没有留下。

## `enum class` 作为强整数

如果被包的是整数，而且只需要比较和哈希，还有一个不用写类的办法：

```cpp run title="enum-id.cpp" error
#include <cstdint>
#include <unordered_set>
#include <utility>

enum class UserId  : std::uint32_t {};
enum class OrderId : std::uint32_t {};

void cancel(UserId who, OrderId what);

void test(std::uint32_t raw) {
  UserId u{raw};                    // OK：直接列表初始化
  OrderId o{7};                     // OK
  cancel(u, o);                     // OK
  cancel(o, u);                     // error: 类型不同
  UserId v = raw;                   // error: 没有隐式转换
  UserId w = {raw};                 // error: 复制列表初始化
  UserId x{-1};                     // error: 窄化
  auto n = std::to_underlying(u);   // std::uint32_t
  std::unordered_set<UserId> seen;  // OK：枚举有 std::hash
  bool lt = u < UserId{3};          // OK：同类型的内置比较
}
```

一个没有枚举项的作用域枚举就是一个新的整数类型。它的底层类型是固定的，所以 `std::uint32_t` 的每一个值都是它的合法值（[[dcl.enum#8]]），不存在超出范围的问题。

`UserId u{raw}` 能编译，靠的是 C++17 加入的一条列表初始化规则（[[dcl.init.list#3.8]]）：如果目标是有固定底层类型的枚举，初始化列表只有一个可以隐式转换为底层类型的标量元素，而且是直接列表初始化，对象就初始化为 `T(v)`。窄化转换仍然非良构，所以 `UserId x{-1}` 被拒绝。规则只认直接列表初始化，`UserId w = {raw}` 和把 `{42}` 传给 `UserId` 形参都不行，这样隐式转换不会通过花括号溜回来。

取出底层值用 `std::to_underlying`（C++23）或 `static_cast`（[[expr.static.cast#7]]）。比较是内置的，`std::hash` 对所有枚举类型都有启用的特化（[[unord.hash#2]]），所以 `UserId` 可以直接作为 `unordered_set` 的键。

<div class="compare" markdown="1">

```cpp
// 类模板：可以有不变式和成员函数
using UserId =
  Strong<std::uint32_t, struct UserTag>;
UserId u{42};
auto raw = u.get();
// 需要自己特化 std::hash
```

```cpp
// enum class：只是一个新整数类型
enum class UserId : std::uint32_t {};

UserId u{42};
auto raw = std::to_underlying(u);
// std::hash 现成可用
```

</div>

`enum class` 的局限也来自它不是类：不能有成员函数，不能在构造时检查不变式（比如 ID 不能为 0），算术运算只能用非成员运算符重载一个个补上。底层不是整数的量（`double` 表示的长度、`std::string` 表示的名字）也只能用类模板。

## 标准库里的强类型

### `std::chrono::duration`：比例是幻影参数

`duration<Rep, Period>` 只有一个 `Rep` 类型的数据成员（[[time.duration]]）。`Period` 是 `std::ratio` 的一个特化，表示一个刻度是多少秒：`milliseconds` 就是 `duration<整数类型, std::milli>`，`std::milli` 即 `ratio<1, 1000>`。`ratio` 的对象从不被创建，它只通过静态成员 `num`、`den` 在编译期参与计算，是一个带算术的幻影参数。

```cpp run title="chrono.cpp" ok
#include <chrono>
#include <print>
#include <type_traits>
using namespace std::chrono;

static_assert(std::is_same_v<milliseconds::period, std::milli>);
static_assert(sizeof(milliseconds) == sizeof(milliseconds::rep));

int main() {
  milliseconds a = 2s;                         // OK：无损
  // seconds b = 1500ms;                       // error: 会截断
  seconds c = duration_cast<seconds>(1500ms);  // 显式截断：1s
  auto d = 1s + 250ms;                         // milliseconds
  duration<double> e = 1500ms;                 // OK：浮点表示
  std::println("{} {} {} {}", a, c, d, e);
}
```

输出 `2000ms 1s 1250ms 1.5s`。从别的 `duration` 转换的构造函数不是 `explicit` 的，但带约束（[[time.duration.cons#3]]）：目标是浮点表示，或者源周期是目标周期的整数倍。所以秒到毫秒可以隐式转换，毫秒到秒不行，必须用 `duration_cast` 显式截断。这和本页 `Strong` 的思路一致：无损的转换可以隐式，可能出错的转换必须写出来。

从裸数值构造 `duration` 的构造函数是 `explicit` 的（[[time.duration.cons#1]]），`seconds s = 5;` 不能编译。

### `std::byte`、`std::align_val_t` 与只是别名的 `size_t`

```cpp run title="std-strong.cpp" ok
#include <cstddef>
#include <cstdio>
#include <new>

int main() {
  std::byte b{0x3f};
  b <<= 1;
  b |= std::byte{1};
  // b + 1;                       // error: byte 没有算术运算
  std::printf("%d\n", std::to_integer<int>(b));

  void* p = ::operator new(256, std::align_val_t{64});
  ::operator delete(p, std::align_val_t{64});
  // ::operator new(256, 64);     // error: 64 不是 align_val_t

  std::size_t s = -1;             // 只是无符号整数类型的别名
  std::ptrdiff_t d = s;           // 两个方向都能隐式转换
  std::printf("%zu %td\n", s, d);
}
```

`std::byte` 声明为 `enum class byte : unsigned char {}`（[[support.types]]），它表示原始内存里的一个字节，而不是一个数。标准库只为它提供位运算和移位（[[support.types.byteops]]），没有加减乘除，转成整数要用 `std::to_integer`。

`std::align_val_t` 声明为 `enum class align_val_t : size_t {}`（[[new.syn]]）。对齐分配函数的签名是 `operator new(std::size_t, std::align_val_t)`。如果对齐值也是 `std::size_t`，这个签名就和程序可能自己定义的放置形式 `operator new(std::size_t, std::size_t)` 撞在一起；做成独立的类型以后，`new (64) T` 不会被误当成对齐分配。

`std::size_t` 和 `std::ptrdiff_t` 则是反例：它们是 typedef（[[support.types.layout]]），只是某个整数类型的别名。上例中 `-1` 隐式转换成 `size_t` 的最大值，再隐式转换回 `ptrdiff_t` 变成 `-1`，`-Wall -Wextra` 下都没有警告。下标、长度、差值之间的混用，标准库的类型系统不会帮你检查。

## 单位与量纲

`duration` 的做法可以推广到任意物理量：再加一个幻影参数表示量纲，用 `std::ratio` 表示单位相对基准单位的倍数。

```cpp run title="units.cpp" ok
#include <compare>
#include <cstdio>
#include <ratio>

template <class Dim, class Rep, class Ratio>
class Quantity {
  Rep n_;
public:
  constexpr explicit Quantity(Rep n) : n_(n) {}

  // 只允许无损的换算：R2 是 Ratio 的整数倍
  template <class R2>
    requires (std::ratio_divide<R2, Ratio>::den == 1)
  constexpr Quantity(Quantity<Dim, Rep, R2> q)
      : n_(q.count() * std::ratio_divide<R2, Ratio>::num) {}

  constexpr Rep count() const { return n_; }

  friend constexpr Quantity operator+(Quantity a, Quantity b) {
    return Quantity{a.n_ + b.n_};
  }
  friend constexpr auto operator<=>(Quantity, Quantity) = default;
};

struct Length;   // 维度标签：只声明，不定义
struct Mass;

template <class R> using Len = Quantity<Length, long, R>;
using Millimeters = Len<std::milli>;
using Meters      = Len<std::ratio<1>>;
using Kilometers  = Len<std::kilo>;
using Grams       = Quantity<Mass, long, std::ratio<1>>;

static_assert(sizeof(Kilometers) == sizeof(long));

int main() {
  Millimeters a = Kilometers{2};       // OK：2'000'000 mm
  auto b = Kilometers{1} + Meters{5};  // Meters：km 换算成 m
  // Kilometers c = Meters{5};         // error: 会丢失精度
  // auto d = Meters{1} + Grams{1};    // error: 维度不同
  std::printf("%ld %ld %d\n", a.count(), b.count(),
              Kilometers{1} > Meters{999});
}
```

输出 `2000000 1005 1`。`Kilometers{1} + Meters{5}` 的结果类型由重载决议决定。ADL 在两个特化里各找到一个隐藏友元 `operator+`：`Kilometers` 版本要求把 `Meters` 转成 `Kilometers`，`ratio_divide<ratio<1>, kilo>` 的分母是 1000，约束不满足，不可行；`Meters` 版本只需要把 `Kilometers` 转成 `Meters`，可行。于是结果自动落在更细的单位上，不需要另写求公共单位的代码。

转换构造函数只做一次乘法，`ratio_divide` 在编译期算完，运行时没有额外开销。真正的单位库还要做量纲代数（长度除以时间得到速度），需要把量纲表示成各基本量的指数列表，思路相同，只是类型计算更多，属于 [[topics/compile-time-programming]] 的范围。

## 陷阱

### 隐式转换从后门回来

```cpp run title="leaky.cpp" ok
#include <cstdio>

template <class T, class Tag>
class Leaky {
  T value_;
public:
  Leaky(T v) : value_(v) {}                // 忘了 explicit
  operator T() const { return value_; }    // 隐式转回 T
};

using Meters  = Leaky<double, struct MetersTag>;
using Seconds = Leaky<double, struct SecondsTag>;

double speed(Meters d, Seconds t) { return d / t; }

int main() {
  Meters d = 100.0;
  Seconds t = 9.58;
  Meters total = d + t;            // 编译通过：两边都先转成 double
  double v = speed(9.58, 100.0);   // 编译通过：double -> Meters
  std::printf("%.2f %.4f\n", static_cast<double>(total), v);
}
```

两处都是良构的，输出 `109.58 0.0958`，两个结果都没有意义。非 `explicit` 的构造函数让裸 `double` 能变成任何一个 `Leaky`，隐式转换函数又让任何一个 `Leaky` 能变回 `double`，`d + t` 就先把两边转成 `double` 再相加，最后再隐式变成 `Meters`。

有一点保护是语言本身给的：一个值上最多隐式应用一次用户定义转换（[[class.conv.general#4]]），所以 `speed(t, d)` 这种 `Seconds → double → Meters` 的链条走不通。但只要允许其中任何一个方向的隐式转换，混用就有了缺口。构造函数一律写 `explicit`；需要裸值时用具名函数 `get()`，或者至少给转换函数也加上 `explicit`。

### `explicit` 构造函数仍然接受窄化

`Cents(price)` 中的 `price` 是 `double` 时，`explicit Strong(long)` 照样被选中，小数部分静默截断，本机 `-Wall -Wextra` 下没有警告（只有实参是字面量时 Clang 才给 `-Wliteral-conversion`）。两个补救办法：

- 养成用花括号构造的习惯，`Cents{price}` 需要窄化转换，非良构（[[dcl.init.list#3.7]]）。
- 在类里加一个删除的构造函数模板：`template <class U> Strong(U) = delete;`。实参类型恰好是 `T` 时，非模板构造函数与模板一样好，非模板胜出；其他任何类型都精确匹配模板，选中被删除的函数，编译失败。代价是连 `Cents(299)` 都要写成 `Cents(299L)`。

### 哈希和格式化不会自动跟上

`std::hash` 和 `std::formatter` 对没有特化的类型都是禁用的（[[unord.hash#2]]、[[format.formatter.spec#5]]），`std::unordered_map<AccountId, int>` 和 `std::format("{}", id)` 都不能编译。对 `enum class`，`std::hash` 现成可用，但 `std::formatter` 仍然没有。程序可以为依赖于程序定义类型的特化向 `std` 里添加特化（[[namespace.std#2]]），一次写给整个模板即可：

```cpp run title="hash-format.cpp" ok
#include <compare>
#include <cstdint>
#include <format>
#include <functional>
#include <print>
#include <unordered_map>
#include <utility>

template <class T, class Tag>
class Strong {
  T value_;
public:
  constexpr explicit Strong(T v) : value_(v) {}
  constexpr const T& get() const { return value_; }
  friend constexpr auto operator<=>(const Strong&,
                                    const Strong&) = default;
};

template <class T, class Tag>
struct std::hash<Strong<T, Tag>> {
  std::size_t operator()(const Strong<T, Tag>& s) const noexcept {
    return std::hash<T>{}(s.get());
  }
};

template <class T, class Tag, class CharT>
struct std::formatter<Strong<T, Tag>, CharT> : std::formatter<T, CharT> {
  auto format(const Strong<T, Tag>& s, auto& ctx) const {
    return std::formatter<T, CharT>::format(s.get(), ctx);
  }
};

enum class OrderId : std::uint32_t {};

template <class CharT>
struct std::formatter<OrderId, CharT>
    : std::formatter<std::uint32_t, CharT> {
  auto format(OrderId id, auto& ctx) const {
    return std::formatter<std::uint32_t, CharT>::format(
        std::to_underlying(id), ctx);
  }
};

using AccountId = Strong<int, struct AccountIdTag>;

int main() {
  std::unordered_map<AccountId, int> balance;
  balance[AccountId{17}] = 500;
  std::println("{:>6} -> {}", AccountId{17}, balance[AccountId{17}]);
  std::println("order #{:08x}", OrderId{0xbeef});
}
```

输出 `    17 -> 500` 和 `order #0000beef`。`formatter` 特化继承底层类型的 `formatter`，`parse` 直接沿用，所以 `{:>6}`、`{:08x}` 这样的格式说明照常工作。`unordered_map` 还需要 `==`，它来自预置 `<=>` 隐式声明的那个 `operator==`。

这两个特化是偏特化，覆盖所有 `Strong<T, Tag>`。如果某个 `T` 本身没有 `std::hash` 或 `std::formatter`，对应的 `Strong` 特化在使用时才会报错。

## 什么时候用

| 情况 | 建议 |
|---|---|
| 同一函数有多个相同类型的形参，顺序容易弄错 | 用强类型；或者改用 [[patterns/named-parameters\|命名参数]] |
| 整数 ID、句柄，只需要比较和哈希 | `enum class Id : 整数类型 {}` |
| 需要不变式检查、非整数表示或成员函数 | `Strong<T, Tag>` 类模板 |
| 有单位或量纲的量 | `duration` 式的 `Quantity<Dim, Rep, Ratio>`，或现成的单位库 |
| 时间 | 直接用 `std::chrono`，不要自己包 |
| 局部变量、实现细节里的中间值 | 不值得，名字和注释就够了 |
| 底层值需要频繁参与各种算术 | 运算会越加越多，最后变回裸值；先确认这个量真的有独立的含义 |

## 思考题

!!! question "1"
    下面四行哪些能编译？`enum class Handle : std::uint32_t {}; void f(Handle);`，然后 `Handle a{42};`、`Handle b = {42};`、`f({42});`、`f(Handle{42});`。

<details markdown="1">
<summary>答案</summary>

第一行和第四行能编译，第二、三行非良构。[[dcl.init.list#3.8]] 只对直接列表初始化开放：`Handle a{42}` 和函数式转型 `Handle{42}` 都是直接列表初始化；`Handle b = {42}` 是复制列表初始化，`f({42})` 用花括号列表初始化形参，也是复制列表初始化，都不适用这一条。标准在这一条的例子里列出了同样的四种情形。
</details>

!!! question "2"
    为了调试，你给 `Strong` 加了一个在析构时检查不变式的析构函数，只在调试构建中启用。发布构建和调试构建的 `Strong` 会有什么 ABI 上的差别？

<details markdown="1">
<summary>答案</summary>

调试构建里析构函数是用户提供的，不再平凡，类不满足 [[class.temporary#3]] 的条件，Itanium ABI 下按值传递时改为传地址（见上文 `add_logged` 的汇编）；发布构建里仍然在寄存器中传递。`sizeof` 不变，但调用约定变了。如果两种构建的目标文件混合链接，以 `Strong` 为形参的函数两边理解不一致，结果是 ODR 违规，不要求诊断（[[basic.def.odr]]）。这种条件编译应当放在不影响类定义的地方，比如成员函数内部的断言。
</details>

!!! question "3"
    `std::chrono::milliseconds m = 2s;` 能编译，`std::chrono::seconds s = 1500ms;` 不能。可是 `duration<double> d = 1500ms;` 又能编译。这三者用的是同一个构造函数模板吗？是什么区分了它们？

<details markdown="1">
<summary>答案</summary>

是同一个非 `explicit` 的转换构造函数模板 `template<class Rep2, class Period2> duration(const duration<Rep2, Period2>&)`，区别在它的约束（[[time.duration.cons#3]]）：目标的 `rep` 是浮点类型时总是满足；否则要求 `ratio_divide<Period2, period>::den` 为 1，并且源 `Rep2` 不是浮点。秒到毫秒的比值是 1000/1，满足；毫秒到秒是 1/1000，不满足，候选被排除，没有其他转换可用；到 `duration<double>` 时目标是浮点，满足。这个约束把会截断的转换从隐式转换中剔除，留给显式的 `duration_cast`。
</details>
