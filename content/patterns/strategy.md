---
title: 策略模式的几种写法
summary: 把算法中可替换的一环抽出来，分别用虚接口、std::function 及其后继、模板参数、函数指针和 std::variant 实现同一个定价策略，比较所有权、能否运行时更换、大小、分配、间接层次、内联和报错，最后给出选择表。
status: draft
order: 50
since: c++98
papers: P0288R9, P2548R6, P0792R14
related: class.virtual, expr.call, func.wrap, func.wrap.func, func.wrap.move, func.wrap.copy, func.wrap.ref, variant.visit, unique.ptr, expr.prim.lambda.closure, dcl.attr.nouniqueaddr, patterns/type-erasure, patterns/visitor, patterns/policy-based-design, topics/lambdas, topics/ownership-and-smart-pointers
tags: 设计模式, 策略, 虚函数, std::function, variant, 模板, 类型擦除
updated: 2026-10-19
---

!!! tldr
    - 策略模式把算法里会变化的一步（这里是结算时的折扣规则）交给一个可替换的对象。C++ 里至少有五种载体：虚接口加 `unique_ptr`、`std::function` 一族、模板参数、函数指针、`std::variant` 加 `std::visit`。
    - 五种写法在两个问题上分成三类：能否在运行时更换（模板不能），策略集合是开放的还是封闭的（`variant` 是封闭的），由谁拥有策略对象（`function_ref` 和函数指针不拥有任何状态）。
    - 热路径的代价主要取决于调用点能不能看到策略的函数体。本机 Clang 23 `-O2` 下，模板和把 `visit` 提到循环外的 `variant` 能内联并向量化，约 0.15 ns/次；虚函数、`std::function`、函数指针都是一次间接调用，约 0.9 ns/次。
    - `std::function` 复制目标对象，有状态的策略会悄悄分成几份；`function_ref` 不拥有目标，绑定临时对象就会悬垂；lambda 策略捕获 `this` 后，外层对象被复制或销毁就会出错。

## 一个可以替换的环节

结算时要按促销规则算价格：不打折、打八折、满减一张优惠券。规则会增加，也可能在运行时切换。最直接的写法是把规则写死在一个 `switch` 里：

```cpp run title="switch.cpp" ok
#include <cstdio>

enum class Rule { none, percent, coupon };

struct Checkout {
  Rule rule = Rule::none;
  int arg = 0;
  int total(int cents) const {
    switch (rule) {
      case Rule::none:    return cents;
      case Rule::percent: return cents * (100 - arg) / 100;
      case Rule::coupon:  return cents > arg ? cents - arg : 0;
    }
    return cents;
  }
};

int main() {
  Checkout c{Rule::percent, 20};
  std::printf("%d\n", c.total(1000));   // 800
}
```

每加一条规则都要改 `Checkout`，规则的参数也只能挤在一个 `arg` 里。**策略模式**（strategy）把会变化的这一步抽成一个独立的对象，`Checkout` 只负责在合适的时候调用它。下文的五种实现都使用这三条规则，价格单位是分。

## ① 虚接口与 `unique_ptr`

```cpp run title="virtual.cpp" ok
#include <cstdio>
#include <memory>

struct Pricing {
  virtual ~Pricing() = default;
  virtual int price(int cents) const = 0;
};
struct Percent final : Pricing {
  int pct;
  explicit Percent(int p) : pct(p) {}
  int price(int c) const override { return c * (100 - pct) / 100; }
};
struct Coupon final : Pricing {
  int off;
  explicit Coupon(int o) : off(o) {}
  int price(int c) const override { return c > off ? c - off : 0; }
};

class Checkout {
  std::unique_ptr<Pricing> pricing_;
public:
  explicit Checkout(std::unique_ptr<Pricing> p) : pricing_(std::move(p)) {}
  void set_pricing(std::unique_ptr<Pricing> p) { pricing_ = std::move(p); }
  int total(int cents) const { return pricing_->price(cents); }
};

int main() {
  Checkout c{std::make_unique<Percent>(20)};
  std::printf("%d\n", c.total(1000));            // 800
  c.set_pricing(std::make_unique<Coupon>(150));
  std::printf("%d\n", c.total(1000));            // 850
}
```

`price` 是**虚函数**（[[g:virtual-function]]，[[class.virtual#1]]）。`pricing_->price(cents)` 是一次虚函数调用：被调用的是 `*pricing_` 的动态类型（运行时对象的实际类型，[[g:dynamic-type]]）中的最终覆盖函数（[[expr.call#2]]）。新的策略只要从 `Pricing` 派生，可以写在别的翻译单元里，`Checkout` 不用重新编译。

所有权由 `unique_ptr` 表达：`Checkout` 独占策略对象，析构时一起销毁。代价是每个策略一次堆分配，而且 `Checkout` 只能移动、不能复制；要复制就得给 `Pricing` 加一个虚的 `clone()`。如果策略的寿命由别人保证，也可以只存一个 `const Pricing&`，所有权的取舍见 [[topics/ownership-and-smart-pointers]]。

这种写法还有两处细节：

- `override` 把签名写错变成编译错误（[[class.virtual#5]]）。少写一个 `const` 时，没有 `override` 的派生类函数只是一个新函数，派生类仍是抽象类，错误要等到 `make_unique` 时才出现，见下文的报错对比。
- 空的 `unique_ptr` 上调用 `->` 违反前置条件（[[unique.ptr.single.observers#5]]），是 UB，没有任何检查。

## ② `std::function` 及其后继

```cpp run title="function.cpp" ok
#include <cstdio>
#include <functional>

class Checkout {
  std::function<int(int)> pricing_;
public:
  explicit Checkout(std::function<int(int)> p) : pricing_(std::move(p)) {}
  void set_pricing(std::function<int(int)> p) { pricing_ = std::move(p); }
  int total(int cents) const { return pricing_(cents); }
};

int half(int c) { return c / 2; }

int main() {
  int pct = 20;
  Checkout c{[pct](int x) { return x * (100 - pct) / 100; }};
  std::printf("%d\n", c.total(1000));   // 800
  c.set_pricing(half);                  // 函数指针也可以
  std::printf("%d\n", c.total(1000));   // 500
  Checkout d = c;                       // 可以复制，目标对象随之复制
  std::printf("%d\n", d.total(1000));   // 500
}
```

`std::function<int(int)>` 能装下任何能以 `int` 调用、结果能转换为 `int` 的对象：lambda、函数指针、带 `operator()` 的类。策略不再需要共同的基类，这种手法叫做**类型擦除**（[[g:type-erasure]]），原理见 [[patterns/type-erasure|类型擦除]]。

它有值语义：复制 `function` 就复制里面的目标对象（[[func.wrap.func.con#3]]），所以目标必须可复制（[[func.wrap.func.con#10]]）。小目标不分配内存只是建议（[[func.wrap.func.con#15]]）；本机 libc++ 的 `function` 占 32 字节，目标不超过 16 字节且复制不抛异常时放在对象内部，否则分配，测量见 [[func.wrap.func]]。空的 `function` 被调用时抛 `bad_function_call`（[[func.wrap.func.inv#2]]）。

`std::function` 有两个设计缺陷：它的 `operator()` 是 `const` 成员函数，却以非 const 左值调用目标；它要求目标可复制，装不下捕获了 `unique_ptr` 的 lambda。C++23 和 C++26 各补了一个包装器，C++26 又加了一个不拥有目标的引用：

| | 拥有目标 | 可复制 | 签名里的 `const`、`&&`、`noexcept` | 空状态 |
|---|---|---|---|---|
| `function` {{c++11}} | 是 | 是 | 不支持 | 调用抛异常 |
| `move_only_function` {{c++23}} | 是 | 否，只能移动 | 支持 | 调用是 UB |
| `copyable_function` {{c++26}} | 是 | 是 | 支持 | 调用是 UB |
| `function_ref` {{c++26}} | 否 | 是，平凡复制 | `const`、`noexcept` | 没有 |

四者的完整对照见 [[func.wrap]]。

!!! impl "本机 libc++ 尚未实现"
    LLVM 23 的 libc++ 中 `__cpp_lib_move_only_function`、`__cpp_lib_copyable_function`、`__cpp_lib_function_ref` 都没有定义，下面两段代码无法在本机编译，所以不标判定。代码块上的 godbolt 按钮会同时用 GCC trunk 编译。

需要独占资源的策略用 `move_only_function`。签名里写 `const`，目标就必须能以 const 左值调用（[[func.wrap.move.class]] 中的 *is-callable-from*）：

```cpp run title="move-only.cpp"
#include <functional>
#include <memory>
#include <vector>

struct PriceTable { std::vector<int> cap; };

struct Checkout {
  std::move_only_function<int(int) const> pricing;
  int total(int cents) const { return pricing(cents); }
};

int main() {
  auto table = std::make_unique<PriceTable>(PriceTable{{500}});
  Checkout c{[t = std::move(table)](int x) {
    return x < t->cap[0] ? x : t->cap[0];
  }};
  return c.total(1000) == 500 ? 0 : 1;
}
```

换成 `std::function<int(int)>`，这段代码在构造时就被拒绝，因为闭包里的 `unique_ptr` 不能复制（[[func.wrap.func.con#10]]）。

策略只在一次调用期间使用、不需要保存时，形参写 `function_ref`。它只存一个指向目标的指针和一个函数指针（[[func.wrap.ref.class#1]]），不分配、不复制目标：

```cpp run title="function-ref.cpp"
#include <functional>
#include <span>

long sum(std::span<const int> xs,
         std::function_ref<int(int) const> pricing) {
  long s = 0;
  for (int x : xs) s += pricing(x);
  return s;
}

int main() {
  int pct = 20;
  int xs[] = {1000, 2000};
  return sum(xs, [pct](int x) { return x * (100 - pct) / 100; }) == 2400 ? 0 : 1;
}
```

lambda 临时对象活到整个调用表达式结束，`sum` 执行期间引用一直有效。把 `function_ref` 存起来就是另一回事了，见下文的陷阱。

## ③ 模板参数

```cpp run title="template.cpp" ok
#include <concepts>
#include <cstdio>

struct NoDiscount {
  int operator()(int c) const { return c; }
};
struct Percent {
  int pct;
  int operator()(int c) const { return c * (100 - pct) / 100; }
};

template <class Pricing>
  requires std::invocable<const Pricing&, int>
class Checkout {
  [[no_unique_address]] Pricing pricing_;
public:
  explicit Checkout(Pricing p = {}) : pricing_(p) {}
  int total(int cents) const { return pricing_(cents); }
};

int main() {
  Checkout a{Percent{20}};      // Checkout<Percent>
  Checkout<NoDiscount> b;
  std::printf("%d %d\n", a.total(1000), b.total(1000));   // 800 1000
  std::printf("%zu %zu\n", sizeof a, sizeof b);           // 本机：4 1
}
```

策略成了类型的一部分，在编译期选定。`Checkout<Percent>` 和 `Checkout<NoDiscount>` 是两个不相关的类型：不能放进同一个容器，不能在运行时互换，每个实例化各生成一份代码。换来的是调用点能看到策略的函数体，优化器可以把它内联，空策略借助 `[[no_unique_address]]`（[[dcl.attr.nouniqueaddr#1]]）也不占额外空间。

标准库大量使用这种写法：`std::sort` 和 `std::set` 的比较器、`unique_ptr` 的删除器、容器的分配器和哈希函数都是模板参数。一个类同时有多个这样的可替换环节时，就是 [[patterns/policy-based-design|基于策略的设计]]。`requires` 子句让不合格的策略在类模板的入口处报错，而不是在成员函数内部，见 [[topics/concepts]]。

模板参数和运行时策略并不互斥：`Checkout<std::function<int(int)>>` 就是一个能在运行时换策略的 `Checkout`，由使用者决定付不付这份代价。

## ④ 函数指针

```cpp run title="fnptr.cpp" ok
#include <cstdio>

int no_discount(int c) { return c; }
int half(int c) { return c / 2; }

struct Checkout {
  int (*pricing)(int) = no_discount;
  int total(int cents) const { return pricing(cents); }
};

int main() {
  Checkout c;
  std::printf("%d\n", c.total(1000));          // 1000
  c.pricing = half;
  std::printf("%d\n", c.total(1000));          // 500
  c.pricing = [](int x) { return x - 100; };   // 无捕获的 lambda 可以转换
  std::printf("%d\n", c.total(1000));          // 900
}
```

函数指针是最轻的运行时策略：8 字节，平凡复制，没有所有权问题，也没有状态。只有不捕获任何东西的 lambda 才有到函数指针的转换函数（[[expr.prim.lambda.closure#11]]），所以打八折里的 20 要么写死在函数里，要么像 C 接口那样多传一个 `void*` 上下文参数。

通过类型不匹配的函数指针调用函数是 UB（[[expr.call#6]]），常见于把函数指针 `reinterpret_cast` 成别的签名再调用。调用空函数指针同样是 UB。

## ⑤ `std::variant` 与 `std::visit`

```cpp run title="variant.cpp" ok
#include <cstdio>
#include <variant>

struct NoDiscount { int operator()(int c) const { return c; } };
struct Percent {
  int pct;
  int operator()(int c) const { return c * (100 - pct) / 100; }
};
struct Coupon {
  int off;
  int operator()(int c) const { return c > off ? c - off : 0; }
};

using Pricing = std::variant<NoDiscount, Percent, Coupon>;

struct Checkout {
  Pricing pricing;
  int total(int cents) const {
    return std::visit([cents](const auto& p) { return p(cents); }, pricing);
  }
};

int main() {
  Checkout c{Percent{20}};
  std::printf("%d\n", c.total(1000));   // 800
  c.pricing = Coupon{150};
  std::printf("%d\n", c.total(1000));   // 850
  std::printf("%zu\n", sizeof c);       // 本机：8
}
```

可选的策略在 `Pricing` 这个类型里列全了，集合是封闭的。策略对象直接嵌在 `variant` 里（[[variant.variant.general#1]]），不分配内存，`Checkout` 可以复制、比较，策略的参数也一目了然。

封闭有两面。加一种策略要修改 `Pricing`，所有用到它的代码都要重新编译；反过来，访问者必须能处理每一种备选类型，否则程序非良构（[[variant.visit#5]]），漏掉一种策略不会编译通过。对单个 `variant` 的 `visit` 要求常数时间（[[variant.visit#8]]），实现通常是按下标查表或分支。`variant` 因构造抛异常而处于无值状态时，`visit` 抛 `bad_variant_access`（[[variant.visit#7]]）；本例的策略都是平凡类型，不会进入这种状态。更多用法见 [[patterns/visitor|访问者]]。

## 代价：本机测量

### 大小与分配

下面的程序把五种 `Checkout` 各构造一次，用替换的 `operator new` 统计分配次数：

```cpp run title="five.cpp" ok
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <memory>
#include <new>
#include <variant>

static int allocs = 0;
void* operator new(std::size_t n) {
  ++allocs;
  if (void* p = std::malloc(n)) return p;
  throw std::bad_alloc{};
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }

struct NoDiscount { int operator()(int c) const { return c; } };
struct Percent { int pct; int operator()(int c) const { return c * (100 - pct) / 100; } };
struct Coupon  { int off; int operator()(int c) const { return c > off ? c - off : 0; } };

struct Pricing {
  virtual ~Pricing() = default;
  virtual int price(int cents) const = 0;
};
struct PercentPricing final : Pricing {
  int pct;
  explicit PercentPricing(int p) : pct(p) {}
  int price(int c) const override { return c * (100 - pct) / 100; }
};

struct CheckoutV {     // ①
  std::unique_ptr<Pricing> strategy;
  int total(int c) const { return strategy->price(c); }
};
struct CheckoutF {     // ②
  std::function<int(int)> strategy;
  int total(int c) const { return strategy(c); }
};
template <class S>
struct CheckoutT {     // ③
  [[no_unique_address]] S strategy;
  int total(int c) const { return strategy(c); }
};
int half(int c) { return c / 2; }
struct CheckoutP {     // ④
  int (*strategy)(int);
  int total(int c) const { return strategy(c); }
};
struct CheckoutX {     // ⑤
  std::variant<NoDiscount, Percent, Coupon> strategy;
  int total(int c) const {
    return std::visit([c](const auto& s) { return s(c); }, strategy);
  }
};

template <class F> void measure(const char* what, F make) {
  allocs = 0;
  auto c = make();
  std::printf("%-10s sizeof=%2zu allocs=%d total=%d\n",
              what, sizeof(c), allocs, c.total(1000));
}

int main() {
  measure("virtual",  [] { return CheckoutV{std::make_unique<PercentPricing>(20)}; });
  measure("function", [] { return CheckoutF{Percent{20}}; });
  measure("template", [] { return CheckoutT<Percent>{{20}}; });
  measure("fnptr",    [] { return CheckoutP{half}; });
  measure("variant",  [] { return CheckoutX{Percent{20}}; });
}
// 本机 libc++（arm64 macOS）输出：
//   virtual    sizeof= 8 allocs=1 total=800
//   function   sizeof=32 allocs=0 total=800
//   template   sizeof= 4 allocs=0 total=800
//   fnptr      sizeof= 8 allocs=0 total=500
//   variant    sizeof= 8 allocs=0 total=800
```

`variant` 的 8 字节是最大的备选类型（4 字节）加上下标。`std::function` 装 `Percent` 不分配，因为 4 字节的目标放得进内部缓冲区；捕获三个 `int` 的 lambda 就要分配一次（[[func.wrap.func]] 有完整的测量）。

### 热路径上的一次调用

把调用单独放进一个函数，看 `-O2` 生成的 arm64 代码。策略对象从参数传入，编译器不知道它的具体类型：

<div class="compare" markdown="1">

```text
; ① p.price(x)
ldr  x8, [x0]       ; 读 vptr
ldr  x2, [x8, #16]  ; 读虚表槽
br   x2             ; 间接跳转
```

```text
; ② f(x)，libc++ std::function
stur w1, [x29, #-4] ; x 存到栈上
ldr  x0, [x0, #24]  ; 读 __f_
cbz  x0, LBB1_2     ; 为空则抛异常
ldr  x8, [x0]       ; 读 vptr
ldr  x8, [x8, #48]  ; 读虚表槽
sub  x1, x29, #4    ; 传 &x
blr  x8             ; 间接调用
```

</div>

虚函数调用是两次读内存加一次间接跳转。libc++ 的 `function` 内部也是一个虚函数调用，前面多了判空，实参还要通过栈上的地址传递，因为内部的虚函数以 `int&&` 接收实参。函数指针 `f(x)` 的指针已经在寄存器里，除了两条寄存器间的 `mov`，只剩一条 `br x2`。

<div class="compare" markdown="1">

```text
; ③ p(x)，模板参数：直接内联
ldr   w8, [x0]      ; p.pct
mov   w9, #100
sub   w8, w9, w8
mul   w8, w8, w1
; ……除以 100 的乘法和移位
ret
```

```text
; ⑤ visit：按下标分支后内联
ldr   w8, [x0, #4]  ; 读下标
cmp   w8, #0
b.le  LBB4_3        ; NoDiscount
cmp   w8, #1
b.ne  LBB4_5        ; Coupon
; Percent 的代码直接写在这里
```

</div>

`variant` 的三个策略都被内联了，没有间接调用。libc++ 的 `visit` 在源码里用函数指针表实现，但表很小、下标的取值范围已知，Clang 把它变成了比较和分支。

### 编译器能看见具体类型时

调用点能看到对象的具体类型时，虚函数和 `std::function` 的间接层也会消失。本机 `-O2` 下：

- `int f(const PercentPricing& p, int x) { return p.price(x); }`：`PercentPricing` 是 `final` 类，`price` 不可能再被覆盖，Clang 直接内联。去掉 `final` 就回到三条指令的虚调用。
- 在同一个函数里 `make_unique<PercentPricing>(20)` 再调用，或者构造一个 `std::function` 再调用：两者都被完全内联，连堆分配都被消除了。

所以间接调用的代价出现在策略被存下来、在别处调用的地方，这正是策略模式的典型用法。

### 循环里的调用

对一百万个价格求和，重复 100 次，五种写法放在单独的翻译单元里，不开 LTO。本机（Apple Silicon，Clang 23 `-O2`）测得每次策略调用的平均时间：

| 写法 | ns/次 | 循环里发生了什么 |
|---|---|---|
| ① 虚函数 | 0.92 | 每次迭代都重新读 vptr 和虚表槽，再间接调用 |
| ② `std::function` | 0.94 | 每次迭代判空、读两层指针、间接调用 |
| ④ 函数指针 | 0.92 | 每次迭代一次间接调用 |
| ⑤ `visit` 在循环里 | 0.82 | 每次迭代按下标分支，三个策略都已内联，没有向量化 |
| ⑤ `visit` 在循环外 | 0.15 | 先选定策略，循环体里是确定的类型，向量化 |
| ③ 模板参数 | 0.16 | 内联后向量化 |

这是一个策略体只有几条指令、分支完全可预测的微基准，差距主要来自能否内联和向量化，而不是间接跳转本身。策略体本身较重时，这几种写法的差别会被摊薄。

`variant` 的两行说明了一个实用技巧：把 `visit` 提到循环外，让循环在 lambda 里面，每个备选类型各得到一份内联、可向量化的循环：

```cpp
long sum(const Pricing& v, std::span<const int> xs) {
  return std::visit([xs](const auto& p) {
    long s = 0;
    for (int x : xs) s += p(x);
    return s;
  }, v);
}
```

虚函数版本也可以做类似的事：给接口加一个处理整批数据的虚函数，一次间接调用换来一整个循环。

## 报错长什么样

策略写错时，五种写法给出的诊断差别很大。以下是本机 Clang 23 的第一条错误：

| 写错的地方 | 写法 | 错误 |
|---|---|---|
| 覆盖函数少写 `const`，没写 `override` | ① | 在 `make_unique<Bad>()` 内部："allocating an object of abstract class type 'Bad'"，附注 "unimplemented pure virtual method 'price'" |
| 同上，写了 `override` | ① | 在声明处："non-virtual member function marked 'override' hides virtual member function" |
| 策略的调用签名不对 | ② | "no viable conversion from 'Wrong' to 'std::function<int (int)>'" |
| 同上，模板没有约束 | ③ | 在 `total` 的函数体里："no matching function for call to object of type 'const Wrong'" |
| 同上，模板有 `requires` | ③ | 在使用处："constraints not satisfied for class template 'Checkout'"，附注哪个约束不满足 |
| 有捕获的 lambda 赋给函数指针 | ④ | "no viable conversion from '(lambda at …)' to 'int (*)(int)'" |
| 访问者漏掉一种策略 | ⑤ | 在 libc++ `<variant>` 内部："no matching function for call to '__invoke'"，后面跟着约 70 行实例化栈 |

`variant` 的报错最难读，但它抓住的错误在开放集合的写法里无从检查：漏处理了一种策略。

## 陷阱

### `std::function` 复制有状态的策略

```cpp run title="stateful.cpp" ok
#include <cstdio>
#include <functional>

struct CountingPricing {   // 有状态：记录调用次数
  int calls = 0;
  int operator()(int c) { ++calls; return c; }
};

int main() {
  CountingPricing counter;
  std::function<int(int)> s = counter;     // 复制了一份 counter
  s(100); s(200);
  std::printf("%d\n", counter.calls);      // 0

  auto s2 = s;                             // 连同 calls == 2 再复制一份
  s2(300);
  std::printf("%d %d\n", s.target<CountingPricing>()->calls,
                         s2.target<CountingPricing>()->calls);   // 2 3

  std::function<int(int)> r = std::ref(counter);   // 只保存引用
  r(100);
  std::printf("%d\n", counter.calls);      // 1
}
```

`function` 拥有的是目标对象的副本，原来的 `counter` 一直没有被调用。复制 `function` 又会复制状态，此后两份各自计数。注意 `CountingPricing::operator()` 不是 `const` 的，却能通过 `const` 的 `function::operator()` 调用（[[func.wrap.func.inv#1]] 以非 const 左值调用目标）。`copyable_function<int(int) const>` 会拒绝这样的目标，新包装器把 `const` 写进签名就是为了堵上这个缺口。

要共享状态，就用 `std::ref` 包一层，`function` 只保存引用，代价是自己保证 `counter` 活得更久。标准算法也按值接收函数对象，有状态的比较器或谓词同样会被复制。

### `function_ref` 绑定临时对象

`function_ref` 从可调用对象构造时，保存的是这个对象的地址（[[func.wrap.ref.ctor#8]]）。形参位置的临时对象活到调用结束，但存到变量里的 `function_ref` 比临时对象活得长：

```cpp run title="dangling-ref.cpp"
#include <functional>

struct Percent {
  int pct;
  int operator()(int c) const { return c * (100 - pct) / 100; }
};

int main() {
  std::function_ref<int(int) const> r = Percent{20};   // 临时对象在这一行末尾销毁
  return r(1000);   // UB：通过悬垂的地址调用
}
```

本机无法编译这段代码，所以不标判定；按标准它是 UB。从函数指针构造的 `function_ref` 没有这个问题，因为它保存的是函数指针本身（[[func.wrap.ref.ctor#5]]），函数不会被销毁。同样的道理适用于把 `function_ref` 作为成员保存：它和 `string_view` 一样只适合做形参，悬垂的一般规律见 [[topics/dangling-references]]。

### lambda 策略捕获了 `this`

```cpp run title="this-capture.cpp" ub
#include <cstdio>
#include <functional>
#include <memory>

struct Checkout {
  int points = 100;
  std::function<int(int)> strategy = [this](int c) { return c - points; };
  int total(int c) const { return strategy(c); }
};

int main() {
  auto a = std::make_unique<Checkout>();
  Checkout b = *a;                      // b.strategy 里的 this 仍指向 *a
  a->points = 300;
  std::printf("%d\n", b.total(1000));   // 700，读的是 a 的 points
  a.reset();
  std::printf("%d\n", b.total(1000));   // UB：*a 已经销毁
}
```

默认成员初始化器里的 lambda 捕获的是构造时的 `this`。隐式的复制构造函数逐成员复制，`b.strategy` 复制了闭包，闭包里的指针还是 `a` 的地址。本机 ASan 在第二次 `total` 处报告 heap-use-after-free。

修法是不让策略记住宿主，把它需要的东西作为实参传进去：

<div class="compare" markdown="1">

```cpp
// 捕获 this：复制后指向旧对象
std::function<int(int)> strategy =
  [this](int c) { return c - points; };
int total(int c) const {
  return strategy(c);
}
```

```cpp
// 宿主作为实参传入
std::function<int(int, const Checkout&)>
  strategy = [](int c, const Checkout& k) {
    return c - k.points;
  };
int total(int c) const {
  return strategy(c, *this);
}
```

</div>

另一种做法是禁止复制和移动 `Checkout`。`this` 捕获的一般规则见 [[topics/lambdas]]。

## 怎么选

| 需求 | 写法 | 理由 |
|---|---|---|
| 编译期就确定，追求性能 | ③ 模板参数 | 可内联、可向量化，空策略不占空间；代价是代码膨胀，每个实例化是不同类型 |
| 策略集合固定且已知，需要值语义 | ⑤ `variant` | 不分配，可复制、可比较，漏处理一种策略会报错；加策略要重新编译 |
| 策略来自外部模块或插件，集合开放 | ① 虚接口 | 新策略只需派生，可以有多个虚函数组成的完整接口 |
| 只有一个调用签名，策略来源多样 | ② `function`；只能移动时 `move_only_function` | 不需要基类，lambda、函数、函数对象都行 |
| 只在一次调用期间使用 | `function_ref` 形参，或函数模板形参 | 不拥有、不分配；不要存下来 |
| 无状态、要和 C 接口互通 | ④ 函数指针 | 最小、平凡复制；状态只能另传 |

五种写法的性质汇总（大小和分配是本机 libc++、arm64 上的数据）：

| | 能否运行时更换 | 集合 | 所有权 | `sizeof` | 分配 | 热调用 |
|---|---|---|---|---|---|---|
| ① 虚接口 + `unique_ptr` | 能 | 开放 | 独占，堆上 | 8 | 每个策略 1 次 | 读 vptr、读槽、间接调用 |
| ② `std::function` | 能 | 开放 | 持有副本 | 32 | 大目标 1 次 | 判空、读两层指针、间接调用 |
| ③ 模板参数 | 不能 | 开放（编译期） | 按值 | 策略本身 | 0 | 内联 |
| ④ 函数指针 | 能 | 开放 | 无状态 | 8 | 0 | 间接调用 |
| ⑤ `variant` | 能，限于列出的类型 | 封闭 | 按值 | 最大备选 + 下标 | 0 | 分支后内联 |

## 思考题

!!! question "1"
    上面“循环里的调用”一节的虚函数版本，是在循环里反复调用 `p.price(prices[i])` 求和。Clang 每次迭代都重新读 `p` 的 vptr。`p` 是 `const Pricing&`，循环里也没有修改它，为什么不能把这两次读提到循环外？

<details markdown="1">
<summary>答案</summary>

被调用的 `price` 对编译器是不透明的，理论上它可以结束 `*p` 的生命周期，在同一块存储上用 placement new 创建另一个派生类的对象，此后 vptr 就变了。按 [[basic.life#9]]，类型不同的新对象不能透明替换旧对象，再通过旧的引用 `p` 调用是 UB，所以按标准编译器其实可以假设 vptr 不变。Clang 默认不做这个假设；本机加上 `-fstrict-vtable-pointers` 后，vptr 和虚表槽在循环前只读一次，循环体里只剩 `blr`。这个选项要求代码在替换对象后用 `std::launder` 取得新指针，见 [[basic.life]]。
</details>

!!! question "2"
    下面哪一行能编译？为什么？
    ```cpp
    void f(int k) {
      int (*a)(int) = [](int c) { return c / 2; };
      int (*b)(int) = [k](int c) { return c - k; };
      std::function<int(int)> g = [k](int c) { return c - k; };
    }
    ```

<details markdown="1">
<summary>答案</summary>

`a` 和 `g` 能编译，`b` 不能。只有不捕获任何实体的 lambda，其闭包类型才有转换为函数指针的转换函数（[[expr.prim.lambda.closure#11]]）；`b` 的闭包要保存 `k`，一个函数指针放不下这份状态，本机 Clang 报 "no viable conversion"。`std::function` 把闭包对象连同 `k` 一起保存，所以 `g` 没有问题。
</details>

!!! question "3"
    `std::variant<NoDiscount, Percent, Coupon>` 的策略想支持从配置文件加载的第四种规则，而这种规则的实现在一个单独编译的插件里。`variant` 还合适吗？

<details markdown="1">
<summary>答案</summary>

不合适。`variant` 的备选类型必须在它的定义处全部列出，插件里的类型在编译 `Checkout` 时还不存在。常见的折中是在 `variant` 里加一个开放的备选类型，例如 `std::variant<NoDiscount, Percent, Coupon, std::unique_ptr<Pricing>>`：已知的规则保持值语义和内联，未知的规则走虚接口。代价是访问者要多处理一种情况，`variant` 的大小也变成指针加下标。
</details>
