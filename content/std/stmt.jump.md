---
title: 跳转语句：break、continue、return、co_return、goto
summary: 跳转时自动对象的销毁；break/continue 的目标；return 的复制初始化、隐式移动与 C++26 禁止绑定临时对象；流出函数末尾的 UB；co_return 的改写；goto 的限制。
status: draft
covers: stmt.jump.general, stmt.break, stmt.cont, stmt.return, stmt.return.coroutine, stmt.goto
papers: P0135R1, P1825R0, P2266R3, P2748R5, P2242R3
related: stmt.dcl, class.copy.elision, expr.prim.id.unqual, class.temporary, dcl.fct.def.coroutine, except.pre, stmt.expand
tags: 语句, 控制流, 返回值, 协程
updated: 2026-10-17
---

跳转语句（jump statement）无条件地转移控制。它们本身的规则不多，难点在于它们与其他机制的交汇处：

- 离开作用域时自动对象的销毁（[[stmt.dcl]]）；
- `return` 如何初始化返回值，涉及复制初始化、复制消除（[[class.copy.elision]]）和隐式移动（[[expr.prim.id.unqual]]）；
- 返回悬空引用，C++26 把其中一部分明显的情形变成了编译错误；
- 协程的 `co_return` 改写为对 promise 对象的调用加一个 `goto`（[[dcl.fct.def.coroutine]]）。

## 总则 [stmt.jump.general]

¶1 五种跳转语句：`break;`、`continue;`、`return expr-or-braced-init-list(opt);`、`co_return ...;`、`goto identifier;`。

¶2（注 1）无论以何种方式离开一个作用域，在该作用域中已构造的自动存储期对象都**按构造的逆序销毁**（规范性规则在 [[stmt.dcl#2]]；临时对象见 [[class.temporary]]）。这是 RAII 在语言层面的保证：`break`、`continue`、`return`、`goto` 跳出若干层嵌套块时，每一层中已构造的对象都会正确析构。

不过，程序可以不经析构而终止。`std::exit()` 不销毁自动对象，只销毁静态存储期对象并调用 `atexit` 注册的函数；`std::abort()` 什么都不销毁（[[support.start.term]]）。

（注 2）协程的挂起（[[expr.await]]）不算离开作用域。挂起时局部变量保存在协程帧中，不会销毁。

```cpp run ok
#include <cstdio>
struct T { const char* n; ~T() { std::printf("~%s ", n); } };
int f() {
    T a{"a"};
    for (int i = 0; ; ++i) {
        T b{"b"};
        {
            T c{"c"};
            if (i == 1) return i;   // 依次销毁 c、b、a
        }                           // 第 0 轮：销毁 c
    }                               // 第 0 轮：销毁 b
}
int main() { f(); std::printf("\n"); }   // 输出：~c ~b ~c ~b ~a
```

## break [stmt.break]

¶1 `break` 必须位于某个迭代语句、展开语句（[[stmt.expand]]）或 `switch` 之内（[[stmt.pre#3]]）。它终止最内层的这类语句，控制转到被终止语句之后的语句（如果有的话）。

终止的是最内层语句，这带来一个经典陷阱：在循环中的 `switch` 里写 `break`，只会跳出 `switch`，不会跳出循环：

```cpp run ok
int main() {
    int i = 0;
    for (; i < 10; ++i) {
        switch (i) {
        case 3:
            break;          // 只终止 switch，循环继续
        default:
            continue;
        }
        break;              // 这个 break 才终止 for
    }
    return i == 3 ? 0 : 1;
}
```

C++ 没有带标号的 break。要跳出多层循环，可以用 `goto`、把循环提取成函数后 `return`，或者用标志变量。（C 语言的下一个版本已经接纳了命名循环，C++ 中也有类似的提案在讨论中。）

## continue [stmt.cont]

¶1 `continue` 必须位于迭代语句或展开语句之内（`switch` 不行）。设最内层的这类语句为 X：

- 如果 X 是迭代语句，控制转到 X 的子语句的末尾。对 `while`/`do` 来说，下一步是测试条件；对 `for` 来说，先执行迭代表达式（[[stmt.for#1]] 的但书）；对范围 `for` 来说，是 `++begin`。
- 如果 X 是展开语句，控制转到当前 Si 的复合语句的末尾，即进入下一份展开（[[stmt.expand]]）。

控制转到子语句末尾，意味着子语句块中的自动对象会销毁，就像正常走完一轮一样。

```cpp error
void f(int k) {
    switch (k) {
    case 0:
        continue;           // error: continue 没有被迭代语句或展开语句包围
    }
}
```

## return [stmt.return]

### 操作数与复制初始化（¶1–¶2）

¶1 函数通过 `return` 把控制返回给调用者。

¶2 `return` 后的 *expr-or-braced-init-list* 称为**操作数**（operand）。

| 操作数 | 允许出现的函数 |
|---|---|
| 无 | 返回类型为 cv `void` 的函数、构造函数、析构函数 |
| 类型为 `void` 的表达式 | 返回类型为 cv `void` 的函数 |
| 其他 | 返回类型不是 cv `void` 的函数 |

第二行在泛型代码里很有用：`return f();` 可以原样转发一个可能返回 `void` 的调用。

```cpp ok
void log();
void wrapper() { return log(); }     // OK: void 函数返回 void 表达式
template<class F> decltype(auto) call(F f) { return f(); }   // F 返回 void 时也成立
```

在第三种情形下，`return` 语句**以复制初始化**（copy-initialization，[[dcl.init]]）初始化函数调用的返回引用或 prvalue 结果对象。由此可以推出：

- 复制初始化不考虑 `explicit` 构造函数，所以 `return {1};` 不能调用 explicit 构造函数（复制列表初始化选中 explicit 构造函数时非良构）。
- 返回类型不是引用时，结果对象就是由调用者提供的那个对象（[[basic.lval]]）。C++17（[[P0135R1]]）起，如果操作数是同类型的 prvalue，就直接在结果对象上初始化，不存在临时对象，也就不需要可访问的拷贝/移动构造函数。这就是保证的复制消除。
- 操作数是局部变量时，可以（但不保证）发生具名返回值优化（NRVO）；不发生时执行隐式移动（见下文）。

```cpp error
struct E { explicit E(int); };
E ee() { return {1}; }      // error: 复制列表初始化选中了 explicit 构造函数
```

```cpp ok
struct NoMove {
    NoMove(int);
    NoMove(const NoMove&) = delete;
    NoMove(NoMove&&) = delete;
};
NoMove make() { return NoMove(1); }   // C++17 起 OK：prvalue 直接初始化结果对象，不需要拷贝/移动
NoMove make2() { return 1; }          // OK: 复制初始化，同样不需要拷贝/移动
```

### 隐式移动

注 2 指向 [[class.copy.elision]]，但具体规则在 [[expr.prim.id.unqual#15]]。一个 *id-expression* 在满足以下条件时是**可移动的**（move-eligible）：

- 它指名一个可隐式移动的实体（implicitly movable entity），即自动存储期的非 volatile 对象变量，或指向非 volatile 对象类型的右值引用变量；
- 它是 `return`/`co_return` 语句或 *throw-expression* 的（可能带括号的）操作数；
- 实体的声明与该表达式之间只隔着块作用域（对 `throw` 还不能隔着 *try-block* 的块作用域）。

可移动的 *id-expression* 是 xvalue（[[expr.prim.id.unqual#12]]）。于是 `return x;` 中的 `x` 像 `std::move(x)` 一样参与重载决议，优先选择移动构造函数。

```cpp ok
#include <memory>
std::unique_ptr<int> take(std::unique_ptr<int>&& p) { return p; }  // p 是右值引用变量：隐式移动
struct B {}; struct D : B {};
std::unique_ptr<B> up() {
    auto d = std::make_unique<D>();
    return d;     // 类型不同（unique_ptr<D> → unique_ptr<B>）也会隐式移动
}
```

这条规则在 C++23 前后有实质变化（[[P2266R3]]）：

| | C++11 ~ C++20 | C++23 起 |
|---|---|---|
| 机制 | 两阶段重载决议：先把操作数当作右值做一次，失败（或选中的构造函数不接受右值引用）再当作左值重做一次 | 操作数就是 xvalue，只做一次重载决议 |
| 返回 `T&` 引用局部变量 | 编译通过，返回悬空引用 | 非良构：左值引用不能绑定 xvalue |
| 拷贝构造函数参数为非 const 引用 `T(T&)` 的类型 | 第一阶段失败后回退为左值，调用 `T(T&)` | 非良构 |
| `decltype(auto)` 函数中的 `return (x);` | 推导为 `T&` | 推导为 `T&&`（依然悬空） |

[[class.copy.elision]] 中的例子正是这几种情形：

```cpp error
struct Weird {
    Weird();
    Weird(Weird&);            // 只接受非 const 左值
};
Weird g(bool b) {
    static Weird w1;
    Weird w2;
    if (b)
        return w1;            // OK: w1 不是自动变量，是左值，用 Weird(Weird&)
    else
        return w2;            // C++23 起 error: w2 在此是 xvalue，无法绑定到 Weird&
}
```

```cpp error
int& h(int i) {
    return i;                 // C++23 起 error: i 是 xvalue（C++20 中编译通过，返回悬空引用）
}
```

C++20（[[P1825R0]]）则在两阶段框架内扩大了隐式移动的范围：右值引用变量也可以隐式移动，选中的构造函数也不再要求其第一个参数恰好是返回对象类型的右值引用。

!!! pitfall "`return std::move(x);` 通常是负优化"
    对局部变量写 `return std::move(x);` 时，操作数不再是 *id-expression*，NRVO 无法发生，只能移动构造。而 `return x;` 在 NRVO 不发生时本来就会隐式移动。Clang 和 GCC 都有 `-Wpessimizing-move` 警告。只有返回成员、全局变量等不可隐式移动的实体时，`std::move` 才有意义。

### 结果对象的析构函数（¶3）

¶3 结果对象的析构函数是**潜在调用的**（potentially invoked，[[class.dtor]]）。即使它实际上从不会调用（比如调用者用结果初始化一个变量，保证复制消除使得根本没有临时对象），它也必须可访问且未被删除。

```cpp error
class A {
    ~A() {}                   // 私有析构函数
};
A f() { return A(); }         // error: A 的析构函数是私有的（即使从不会被调用）
```

原因有两点。调用者可能以多种方式使用结果（丢弃它、绑定到引用、初始化变量），而编译函数定义时无法知道是哪一种；另外，如果 `return` 之后某个局部变量的析构抛出异常，已构造的结果对象需要销毁（[[except.ctor]]）。

### 流出函数末尾（¶4）

¶4 控制流到函数体末尾（flowing off the end）时：

- 构造函数、析构函数、返回 cv `void` 的非协程函数：等价于 `return;`；
- `main`：等价于 `return 0;`（[[basic.start.main]]）；
- 协程：见 [[stmt.return.coroutine#3]]；
- **其他函数：未定义行为** {{ub}}。

注意，UB 发生在真正执行到函数末尾时，而不是函数可能执行到末尾时。因此编译器不能拒绝这样的程序，只能给出警告（`-Wreturn-type`）：

```cpp ok
int sign(int x) {
    if (x > 0) return 1;
    if (x < 0) return -1;
    if (x == 0) return 0;
}   // 实际上永远到不了这里；但编译器通常会警告"并非所有路径都有返回值"
```

```cpp ub
int f(bool b) {
    if (b) return 1;
}                        // f(false) 流出末尾：UB
int main() { return f(false); }
```

!!! warning "这个 UB 的后果非常真实"
    优化器可以假定流出非 void 函数末尾的情况不会发生，于是删除导致它的路径，甚至把 `f(false)` 之后的代码当作不可达。在 Clang 中，常见的表现是执行直接落入紧随其后的另一个函数的机器码。务必开启 `-Werror=return-type`。

### 求值顺序（¶5）

¶5 规定了 `return` 语句中几件事的顺序：

1. 结果的复制初始化，
2. 先于操作数完整表达式中临时对象的销毁，
3. 再先于 `return` 所在块中局部变量的销毁。

注 3 继续往外推：接下来是各外层块的局部变量，然后是函数后置条件断言的求值（[[dcl.contract.func]]，{{c++26}}），最后是函数形参的销毁（[[expr.call]]）。

第 1 条先于第 3 条，保证了返回值可以安全地从局部变量（包括由持锁守卫对象保护的数据）中计算出来，因为构造返回值时守卫对象还活着。

```cpp run ok
#include <mutex>
#include <vector>
std::mutex m;
std::vector<int> data{1, 2, 3};
std::vector<int> snapshot() {
    std::lock_guard lk(m);
    return data;             // 先拷贝出结果对象，再析构 lk（解锁）
}
int main() { return snapshot().size() == 3 ? 0 : 1; }
```

### 返回引用绑定到临时对象：非良构（¶6）{{c++26}}

¶6 在一个函数中（[[meta.rel]] 中为 `std::is_convertible` 虚构的函数除外），如果 `return` 语句把

- ¶6.1 返回的引用，或
- ¶6.2 返回对象的组成引用（constituent reference，[[intro.object]]，即其引用类型的直接成员，以及递归地其子对象的组成引用）

绑定到一个临时对象表达式上，程序**非良构**。

这类代码在 C++23 及之前是良构的，但必然产生悬空引用：临时对象在 `return` 的完整表达式结束时就销毁了（返回值的引用绑定不延长生命周期，[[class.temporary]]）。C++26（[[P2748R5]]）把这个各编译器都会警告的 UB 来源升级为错误。

```cpp error
#include <string>
auto&& f1() {
    return 42;                // error: 返回引用绑定到 prvalue 42 物化出的临时对象
}
const double& f2() {
    static int x = 42;
    return x;                 // error: int → double 转换产生临时对象，引用绑定到它
}
const std::string& f3() {
    return "abc";             // error: 构造了一个临时 std::string
}
struct R { const int& r; };
R f4() {
    return {42};              // error: 返回对象的组成引用 r 绑定到临时对象
}
```

`f2` 容易让人误判：`x` 是静态变量，看似安全，但 `const double&` 不能直接绑定到 `int`，必须先转换出一个 `double` 临时对象。

这条规则只看直接的绑定。经过一层函数调用再返回的临时对象不在此列（标准例 2 中的 `f3`）：

```cpp ok
auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
auto&& f3() {
    return id(42);            // 良构，但返回悬空引用：42 是 id 的实参，而非 return 直接绑定的临时对象
}
```

之所以为 `std::is_convertible` 开例外，是因为 [[meta.rel]] 用虚构函数 `To test() { return std::declval<From>(); }` 是否良构来定义 `is_convertible<From, To>`。如果不开例外，`is_convertible_v<int, const double&>` 就会因为 ¶6 而变为 `false`，改变既有库的行为。

### 实现视角

!!! impl "返回值在 ABI 中的传递"
    Itanium C++ ABI（GCC、Clang 在类 Unix 平台上使用）规定，非平凡可拷贝（或非平凡析构）的类类型返回值由调用者分配存储，并把地址作为隐藏参数传入，被调函数直接在该地址上构造。这就是结果对象由调用者提供在机器层面的实现，也是保证复制消除没有额外开销的原因。平凡类型的小对象则通过寄存器返回。MSVC ABI 的规则类似，但细节不同。

!!! impl "诊断"
    Clang 对返回局部变量或临时对象的引用一直有 `-Wreturn-stack-address` 警告（默认开启）；在 C++26 模式下，¶6 覆盖的情形变成错误（"returning reference to local temporary object"）。¶6 只覆盖临时对象。返回局部变量的左值引用，C++23 起因为隐式移动而成为错误（见上文）；但通过 `decltype(auto)` 加括号返回右值引用，仍然只是警告。

## co_return [stmt.return.coroutine]

### 协程中不能有 return（¶1）

¶1 `co_return` 把控制转移给协程的调用者或恢复者（[[dcl.fct.def.coroutine]]）。**协程中不得出现 `return` 语句**。注 1 指出，判断时不考虑 `return` 是否位于弃置语句中。

一个函数是不是协程，取决于其函数体中是否出现 `co_await`、`co_yield`、`co_return`。为了不让这一点取决于模板参数，标准连弃置语句中的 `return` 也禁止了。

```cpp error
#include <coroutine>
struct T {
    struct promise_type {
        T get_return_object() { return {}; }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_never final_suspend() noexcept { return {}; }
        void return_void() {}
        void unhandled_exception() {}
    };
};
T d() {
    if constexpr (false) { return T{}; }   // error: 协程中不能有 return，即使在弃置语句中
    co_return;
}
```

### 改写（¶2）

¶2 设 *p* 是指名协程 promise 对象的左值。`co_return` 语句等价于

```text
{ S; goto final-suspend; }
```

其中 *final-suspend* 是 [[dcl.fct.def.coroutine]] 定义的仅供说明的标号（在协程体之后、`co_await promise.final_suspend()` 之前），S 为：

- ¶2.1 操作数是 *braced-init-list* 或非 void 表达式：`p.return_value(operand)`；它必须是 `void` 类型的 prvalue。
- ¶2.2 否则（无操作数或 void 表达式）：`{ expression(opt); p.return_void(); }`；`p.return_void()` 必须是 `void` 类型的 prvalue。

由此可以推出：

- 由于 `co_return x;` 中的 `x` 也是可移动的（[[expr.prim.id.unqual#15]]），会选中 `return_value(T&&)` 重载。
- `goto final-suspend` 离开协程体的作用域，所以协程体中的局部变量在 `final_suspend` 之前销毁（协程帧本身稍后才释放）。
- 一个 promise 类型不应同时提供 `return_value` 和 `return_void`（[[dcl.fct.def.coroutine]]）。

```cpp run ok
#include <coroutine>
#include <exception>
struct Task {
    struct promise_type {
        int value = 0;
        Task get_return_object() {
            return Task{std::coroutine_handle<promise_type>::from_promise(*this)};
        }
        std::suspend_never initial_suspend() noexcept { return {}; }
        std::suspend_always final_suspend() noexcept { return {}; }
        void return_value(int v) { value = v; }      // co_return expr; → p.return_value(expr)
        void unhandled_exception() { std::terminate(); }
    };
    std::coroutine_handle<promise_type> h;
    ~Task() { if (h) h.destroy(); }
    int get() const { return h.promise().value; }
};
Task answer(bool b) {
    if (b) co_return 42;
    co_return 0;
}
int main() { return answer(true).get() == 42 ? 0 : 1; }
```

### 流出协程末尾（¶3）

¶3 如果对 `p.return_void()` 的重载决议成功，流出协程函数体末尾等价于 `co_return;`；否则（promise 只有 `return_value`），流出末尾是 UB {{ub}}。这与普通函数的规则对应：返回值的协程必须显式 `co_return` 一个值。

## goto [stmt.goto]

¶1 `goto` 无条件地把控制转移到由标识符标记的语句。标识符必须是当前函数中的标号，不能跳到另一个函数，包括外围函数或 lambda。

`goto` 本身的规则只有这一句，但其他条款对它有不少限制：

| 限制 | 出处 |
|---|---|
| 不能跳过非 vacuous 初始化的自动变量的声明而进入其作用域 | [[stmt.dcl#2]] |
| 不能跳进控制流受限语句（`if constexpr`/`if consteval` 的分支、展开语句的体） | [[stmt.label#3]] |
| 不能跳进 *try-block* 或 handler 的复合语句 | [[except.pre#3]] |
| 展开语句内不得有标识符标号 | [[stmt.label#4]] |
| 常量求值中执行 `goto` 使表达式不是核心常量表达式 | [[expr.const.core#2.36]] |

向后跳会销毁跳过的变量，再重新初始化（[[stmt.dcl#2]] 的例 1）：

```cpp run ok
#include <cstdio>
struct X {
    int n;
    X(int n) : n(n) { std::printf("X(%d) ", n); }
    ~X() { std::printf("~X(%d) ", n); }
};
int main() {
    int k = 0;
ly:
    X a = ++k;               // 每次 goto ly 都先销毁 a，再在这里重新构造
    if (k < 3) goto ly;
    std::printf("done ");
}                            // 输出：X(1) ~X(1) X(2) ~X(2) X(3) done ~X(3)
```

```cpp error
void f() {
    goto l1;                 // error: 不能跳进 try 块
    try {
    l1: ;
    } catch (...) { }
}
```

关于 constexpr 函数中的 goto：C++23 起（[[P2242R3]]），constexpr 函数的定义中可以出现 `goto` 和标号，但如果常量求值时实际执行了一条 `goto`，求值就不是常量表达式。（标准用 `goto` 来定义 `while` 等语句，[[expr.const.core]] 的注明确说明这些改写中引入的 goto 不算在内。）

```cpp error
constexpr int f(int n) {
    if (n < 0) goto fail;    // C++23 起允许出现在 constexpr 函数中
    return n;
fail:
    return -1;
}
static_assert(f(3) == 3);    // OK: 没有执行 goto
constexpr int y = f(-1);     // error: 常量求值中执行了 goto
```

## 历史与演进

!!! history
    - C++98：`return` 以复制初始化返回值；允许（不保证）RVO/NRVO；流出非 void 函数末尾是 UB（`main` 除外）。
    - C++11：`return` 的操作数可以是花括号列表；引入隐式移动（两阶段重载决议）。
    - C++14：隐式移动扩展到返回类型与局部变量类型不同的情形（通过缺陷报告）。
    - C++17：保证的复制消除（[[P0135R1]]）。
    - C++20：协程与 `co_return`；隐式移动扩展到右值引用变量等（[[P1825R0]]）。
    - C++23：可移动的 *id-expression* 直接是 xvalue（[[P2266R3]]）；constexpr 函数中允许 `goto` 和标号（[[P2242R3]]）。
    - C++26：返回引用绑定到临时对象非良构（[[P2748R5]]）；后置条件在局部变量销毁后、形参销毁前求值（契约）；`break`/`continue` 可用于展开语句。

## 陷阱

!!! pitfall "`const T&` 返回类型 + 不同类型的操作数"
    `const std::string& name() const { return "anon"; }`、`const double& get() { return int_member; }` 这类代码在 C++26 中直接报错；在旧标准中它们能编译，但每次调用都返回悬空引用。

!!! pitfall "以为 `std::exit` 会析构局部对象"
    如果在 `main` 中调用 `std::exit(0)` 而不是 `return 0;`，`main` 的局部对象（例如负责刷新缓冲区的日志对象）不会析构。

## 思考题

!!! question "1. 下面的函数在 C++20 和 C++23 中分别返回什么类型？"
    ```cpp
    decltype(auto) f() { int x = 0; return (x); }
    ```

<details markdown="1">
<summary>答案</summary>

C++20 中是 `int&`（`(x)` 是左值，`decltype((x))` 为 `int&`）。C++23 起是 `int&&`：`x` 是可移动实体，`(x)` 是 return 语句的带括号操作数，因此是 xvalue，`decltype` 得到 `int&&`（[[P2266R3]] 有意接受了这一后果）。两种情况都返回对局部变量的悬空引用。这不是绑定到临时对象，所以 ¶6 不会让它非良构，Clang 只给出警告。
</details>

!!! question "2. `struct S { const int& r; }; S g() { return S{42}; }` 违反 ¶6 吗？"

<details markdown="1">
<summary>答案</summary>

按措辞看，应该违反。由于保证的复制消除，`S{42}` 初始化的就是返回的对象，其组成引用 `r` 在这条 `return` 语句中绑定到由 `42` 物化出的临时对象，属于 ¶6.2。不过截至写作时，Clang 只对 `return {42};` 形式报错，对 `return S{42};` 不报错。无论编译器是否诊断，都不要写这样的代码，因为不能指望调用者拿到的 `r` 指向一个仍然存活的 `int`。
</details>

!!! question "3. 为什么 `return` 的结果初始化必须先于局部变量的析构？举一个反过来会出错的例子。"

<details markdown="1">
<summary>答案</summary>

因为操作数经常引用局部变量。例如 `std::string s = ...; return s.substr(1);`，如果先析构 `s` 再求值、初始化结果，`substr` 读的就是已销毁的对象。又如上文的 `lock_guard`，如果先解锁再拷贝 `data`，就是数据竞争。¶5 保证了先构造结果，再销毁临时对象，再销毁局部变量。
</details>

## 小结

| 语句 | 要点 |
|---|---|
| 所有跳转 | 离开作用域时逆序销毁已构造的自动对象；`std::exit`/`abort` 例外；协程挂起不算离开 |
| `break` | 被迭代/展开/`switch` 语句包围；终止最内层者 |
| `continue` | 被迭代/展开语句包围；转到当前循环体（或当前 Si）的末尾 |
| `return` | 复制初始化结果；可移动的局部变量是 xvalue（C++23）；结果对象析构函数潜在调用；结果初始化 → 临时对象销毁 → 局部变量销毁 → 后置条件 → 形参销毁 |
| `return` 绑定临时对象 | C++26 起非良构（返回引用或返回对象的组成引用） |
| 流出末尾 | void/构造/析构 → `return;`；`main` → `return 0;`；协程看有无 `return_void`；其他 UB |
| `co_return` | `{ p.return_value(x) 或 p.return_void(); goto final-suspend; }`；协程中不得有 `return` |
| `goto` | 当前函数中的标号；不能跳过非 vacuous 初始化、不能跳进控制流受限语句或 try 块 |
