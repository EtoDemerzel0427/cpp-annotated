---
title: 跳转语句：break、continue、return、co_return、goto
summary: 跳转语句怎样转移控制、跳出作用域时哪些对象被销毁；return 怎样初始化返回值、何时隐式移动、为什么返回绑定临时对象的引用在 C++26 中非良构；co_return 和 goto 的规则。
status: done
covers: stmt.jump.general, stmt.break, stmt.cont, stmt.return, stmt.return.coroutine, stmt.goto
papers: P0135R1, P1825R0, P2266R3, P2748R5, P2242R3
related: stmt.dcl, class.copy.elision, expr.prim.id.unqual, class.temporary, dcl.fct.def.coroutine, except.pre, stmt.expand
tags: 语句, 控制流, 返回值, 协程
updated: 2026-10-19
---

!!! tldr
    - 无论用哪种跳转离开一个作用域，其中已构造的局部对象都按构造的逆序析构；`std::exit` 和 `std::abort` 不析构局部对象。
    - `break` 只结束最内层的循环或 `switch`；`continue` 跳到当前这一轮循环体的末尾，在 `for` 里会先执行迭代表达式。
    - `return x;` 用复制初始化构造返回值；C++23 起，返回的局部变量直接被当作 xvalue，所以会优先移动，而返回它的左值引用成了编译错误。
    - C++26 起，`return` 把返回的引用绑定到临时对象（例如 `const std::string& f() { return "abc"; }`）是非良构的。
    - 流出非 `void` 函数的末尾是未定义行为（`main` 和协程除外）；协程里不能写 `return`，要用 `co_return`。

¶1 跳转语句无条件地转移控制，共五种：`break;`、`continue;`、`return 操作数(可选);`、`co_return 操作数(可选);`、`goto 标号;`。

## 离开作用域时析构对象 [stmt.jump.general]

```cpp run ok
#include <cstdio>
struct T { const char* n; ~T() { std::printf("~%s ", n); } };
int f() {
    T a{"a"};
    for (int i = 0; ; ++i) {
        T b{"b"};
        {
            T c{"c"};
            if (i == 1) return i;   // 依次析构 c、b、a
        }                           // 第 0 轮：析构 c
    }                               // 第 0 轮：析构 b
}
int main() { f(); std::printf("\n"); }   // ~c ~b ~c ~b ~a
```

¶2 无论以什么方式离开一个作用域，其中已经构造的自动存储期对象（普通局部变量）都按构造的逆序析构。规范性的规则在 [[stmt.dcl#2]]，临时对象见 [[class.temporary]]。这就是 RAII 的语言基础：`break`、`continue`、`return`、`goto` 一次跳出好几层块时，每一层的对象都会正确析构。

注 1 提醒，程序可以不经过这一步就终止：`std::exit()` 只析构静态存储期对象、调用 `atexit` 注册的函数，`std::abort()` 什么都不析构（[[support.start.term]]）。注 2 说明协程挂起（[[expr.await]]）不算离开作用域，挂起期间局部变量保存在协程帧里，不会析构。

## break 和 continue [stmt.break] [stmt.cont]

[[stmt.break#1]] `break` 必须位于某个迭代语句、展开语句（[[stmt.expand]]）或 `switch` 之内，它结束最内层的这类语句，控制转到被结束的语句之后。

因为结束的是最内层那个，循环里的 `switch` 中写 `break` 只跳出 `switch`：

```cpp run ok
int main() {
    int i = 0;
    for (; i < 10; ++i) {
        switch (i) {
        case 3:
            break;      // 只结束 switch
        default:
            continue;
        }
        break;          // 这个 break 才结束 for
    }
    return i == 3 ? 0 : 1;
}
```

C++ 没有带标号的 `break`。要跳出多层循环，可以用 `goto`、把循环提成函数再 `return`，或者用标志变量。

[[stmt.cont#1]] `continue` 必须位于迭代语句或展开语句之内，`switch` 不算。设最内层的这类语句为 X：

- X 是迭代语句时，控制转到 X 的循环体末尾。接下来，`while` 和 `do` 测试条件；`for` 先执行迭代表达式（[[stmt.for#1]]）；范围 `for` 执行 `++begin`。
- X 是展开语句时，控制转到当前这一份循环体的末尾，进入下一份（[[stmt.expand]]）。

转到循环体末尾，意味着循环体里的局部对象照常析构，与正常走完一轮相同。

```cpp error
void f(int k) {
    switch (k) {
    case 0:
        continue;   // error: 不在循环里
    }
}
```

## return [stmt.return]

### 操作数

¶1 函数用 `return` 把控制交还给调用者。¶2 `return` 后面的表达式或花括号列表叫它的**操作数**（operand）。

| 操作数 | 只能用在 |
|---|---|
| 无 | 返回类型为 `void`（可带 cv）的函数、构造函数、析构函数 |
| 类型为 `void` 的表达式 | 返回类型为 `void` 的函数 |
| 其他 | 返回类型不是 `void` 的函数 |

第二行让泛型代码可以原样转发一个可能返回 `void` 的调用：

```cpp ok
void log();
void wrapper() { return log(); }   // OK
template<class F> decltype(auto) call(F f) {
    return f();                    // F 返回 void 时也成立
}
```

### 复制初始化

第三种情形下，`return` 用**复制初始化**（copy-initialization，`T x = e;` 那种形式的初始化，见 [[dcl.init]]）从操作数初始化函数调用的结果，也就是返回的引用或 prvalue 的结果对象。由此有三个后果。

第一，复制初始化不用 `explicit` 构造函数，所以 `return {1};` 选中 explicit 构造函数时非良构：

```cpp error
struct E { explicit E(int); };
E ee() { return {1}; }   // error: explicit 构造函数
```

第二，返回类型不是引用时，结果对象是调用者准备好的那个对象。C++17 起（[[P0135R1]]），操作数是同类型的 prvalue 时，直接在结果对象上初始化，中间没有临时对象，也就不需要拷贝或移动构造函数。这叫保证的复制消除：

```cpp ok
struct NoMove {
    NoMove(int);
    NoMove(const NoMove&) = delete;
    NoMove(NoMove&&) = delete;
};
NoMove make()  { return NoMove(1); }  // OK
NoMove make2() { return 1; }          // OK
```

第三，操作数是局部变量时，编译器可以直接在结果对象里构造这个变量（具名返回值优化，NRVO），但不保证一定这样做。不这样做时，会尝试移动而不是拷贝，规则见下一节。

¶3 结果对象的析构函数是潜在调用的（potentially invoked，[[class.dtor]]）：即使实际上永远不会调用，它也必须可访问、未被删除。

```cpp error
class A {
    ~A() {}               // 私有
};
A f() { return A(); }     // error: 析构函数是私有的
```

编译函数定义时并不知道调用者怎样用这个结果，可能丢弃，可能绑定到引用；而且如果 `return` 之后析构某个局部变量时抛出异常，已经构造好的结果对象需要析构（[[except.ctor]]）。所以这里统一要求析构函数可用。

### 隐式移动

```cpp ok
#include <memory>
std::unique_ptr<int> take(std::unique_ptr<int>&& p) {
    return p;     // p 是右值引用变量：移动
}
struct B {}; struct D : B {};
std::unique_ptr<B> up() {
    auto d = std::make_unique<D>();
    return d;     // 类型不同也会移动
}
```

`unique_ptr` 不能拷贝，这两个函数却都能编译，因为 `return p;` 和 `return d;` 里的名字被当作右值。¶2 的注 2 指向 [[class.copy.elision]]，具体规则在 [[expr.prim.id.unqual#15]]。一个名字满足下面三点时是**可移动的**（move-eligible）：

- 它指名一个可隐式移动的实体：非 volatile 的自动存储期对象，或者指向非 volatile 对象类型的右值引用变量；
- 它是 `return`、`co_return` 或 `throw` 的操作数，外面可以有括号；
- 从实体的声明到这个表达式之间只隔着块作用域。

[[expr.prim.id.unqual#12]] 规定可移动的名字是 xvalue。所以 `return x;` 里的 `x` 像 `std::move(x)` 一样参与重载决议，优先选移动构造函数。

C++23 的 [[P2266R3]] 简化成了这个样子。此前的规则是两阶段重载决议：先把操作数当右值做一次，失败了再当左值重做。两种规则的结果在几种情形下不同：

| 情形 | C++20 | C++23 起 |
|---|---|---|
| 返回 `T&`，操作数是局部变量 | 能编译，返回悬空引用 | 非良构：左值引用不能绑定 xvalue |
| 类型只有 `T(T&)` 拷贝构造函数 | 回退为左值，调用 `T(T&)` | 非良构 |
| `decltype(auto)` 函数里 `return (x);` | 推导为 `T&` | 推导为 `T&&`，仍然悬空 |

<div class="compare" markdown="1">

```cpp error
struct Weird {
    Weird();
    Weird(Weird&);
};
Weird g(bool b) {
    static Weird w1;
    Weird w2;
    if (b) return w1;  // OK: 静态变量
    return w2;         // error: xvalue
}
```

```cpp error
int& h(int i) {
    return i;   // error: i 是 xvalue
}
```

</div>

在这之前，C++20 的 [[P1825R0]] 已经在两阶段框架内把隐式移动扩展到右值引用变量等情形。

!!! pitfall "`return std::move(x);` 通常更慢"
    `return std::move(x);` 的操作数不再是一个名字，NRVO 无法发生，只能移动。而 `return x;` 在不做 NRVO 时本来就会移动。Clang 和 GCC 对此有 `-Wpessimizing-move` 警告。只有返回成员、全局变量这类不可隐式移动的实体时，`std::move` 才有用。

### 流出函数末尾

¶4 执行到函数体末尾而没有遇到 `return`（flowing off the end）时：

- 构造函数、析构函数、返回 `void` 的非协程函数：相当于 `return;`；
- `main`：相当于 `return 0;`（[[basic.start.main]]）；
- 协程：见下文的 `co_return`；
- 其他函数：未定义行为 {{ub}}。

未定义行为发生在真正执行到末尾的时候，而不是可能执行到末尾的时候。所以编译器不能拒绝这样的函数，只能警告（`-Wreturn-type`）：

<div class="compare" markdown="1">

```cpp ok
int sign(int x) {
    if (x > 0) return 1;
    if (x < 0) return -1;
    if (x == 0) return 0;
}   // 到不了这里，但会有警告
```

```cpp run ub
int f(bool b) {
    if (b) return 1;
}   // f(false) 流出末尾
int main() {
    return f(false);
}
```

</div>

本机 Clang 23 在 `-O0` 和 `-O2` 下都在 `f` 的末尾放了一条陷阱指令，右边的程序因 `SIGTRAP` 终止。这只是一种可能的结果：优化器可以认定这条路径不会发生，把它连同前面的代码一起删掉。建议打开 `-Werror=return-type`。

### 析构的顺序

¶5 规定 `return` 语句里三件事的先后：先复制初始化结果，然后析构操作数这个完整表达式里的临时对象，最后析构 `return` 所在块的局部变量。注 3 往外推：再析构各外层块的局部变量，然后求值函数的后置条件断言（[[dcl.contract.func]]，{{c++26}}），最后析构函数形参（[[expr.call]]）。

先构造结果、后析构局部变量，所以返回值可以安全地从局部变量算出来，例如在锁的保护下拷贝数据：

```cpp run ok
#include <mutex>
#include <vector>
std::mutex m;
std::vector<int> data{1, 2, 3};
std::vector<int> snapshot() {
    std::lock_guard lk(m);
    return data;   // 先拷贝出结果，再析构 lk（解锁）
}
int main() { return snapshot().size() == 3 ? 0 : 1; }
```

### 返回的引用绑定到临时对象 {{c++26}}

```cpp error
#include <string>
auto&& f1() {
    return 42;     // error: 绑定到 42 物化出的临时对象
}
const double& f2() {
    static int x = 42;
    return x;      // error: int → double 产生临时对象
}
const std::string& f3() {
    return "abc";  // error: 构造了临时 std::string
}
struct R { const int& r; };
R f4() {
    return {42};   // error: 成员引用 r 绑定到临时对象
}
```

这些函数在 C++23 及之前都能编译，但每次调用必然返回悬空引用：临时对象在 `return` 的完整表达式结束时就析构了，绑定到返回值的引用不会延长它的生命周期（[[class.temporary]]）。C++26 的 [[P2748R5]] 把它们变成了编译错误。

¶6 具体地说，如果 `return` 语句把下面两种引用之一绑定到一个临时对象，程序非良构：

- ¶6.1 返回的引用；
- ¶6.2 返回对象的组成引用（constituent reference，[[intro.object]]），也就是它的引用类型成员，以及递归地其子对象的这类成员。

`f2` 容易看走眼：`x` 是静态变量，但 `const double&` 不能直接绑定到 `int`，要先转换出一个 `double` 临时对象。

这条规则只看 `return` 直接做的绑定。经过一次函数调用再返回的临时对象不在其中（标准例 2）：

```cpp ok
auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
auto&& f3() {
    return id(42);   // 良构，但返回悬空引用
}
```

¶6 为 `std::is_convertible` 开了一个例外。[[meta.rel]] 用一个虚构的函数 `To test() { return std::declval<From>(); }` 是否良构来定义 `is_convertible<From, To>`；没有这个例外，`is_convertible_v<int, const double&>` 就会变成 `false`，改变既有代码的行为。

!!! impl "返回值在 ABI 中怎样传递"
    Itanium C++ ABI（GCC、Clang 在类 Unix 平台上使用）规定，不能平凡拷贝或不能平凡析构的类类型返回值，由调用者分配存储，把地址作为隐藏参数传进去，被调函数直接在那里构造。这就是结果对象由调用者提供在机器层面的样子，也是保证的复制消除没有额外开销的原因。小的平凡类型通过寄存器返回。

## co_return [stmt.return.coroutine]

¶1 `co_return` 把控制交给协程的调用者或恢复者（[[dcl.fct.def.coroutine]]）。协程里不能出现 `return` 语句；注 1 补充说，即使 `return` 位于 `if constexpr` 的弃置分支里也不行。

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
    if constexpr (false) { return T{}; }   // error
    co_return;
}
```

一个函数是不是协程，看函数体里有没有 `co_await`、`co_yield`、`co_return`。弃置语句里的 `return` 也被禁止，函数是不是协程、能不能写 `return`，就不会随模板参数变化。

¶2 设 *p* 是指名协程 promise 对象的左值。`co_return` 语句等价于 `{ S; goto final-suspend; }`，其中 *final-suspend* 是 [[dcl.fct.def.coroutine]] 定义的说明用标号，位于协程体之后、`co_await p.final_suspend()` 之前。S 是：

- ¶2.1 操作数是花括号列表或非 `void` 表达式时，`p.return_value(操作数)`；
- ¶2.2 否则，`{ 表达式(可选); p.return_void(); }`。

两种情况下这个调用都必须是 `void` 类型的 prvalue。由此可知：`co_return x;` 里的 `x` 同样是可移动的，会选中 `return_value(T&&)`；`goto final-suspend` 离开协程体的作用域，所以协程体的局部变量在 `final_suspend` 之前析构，协程帧本身稍后才释放。

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
        void return_value(int v) { value = v; }   // co_return e; 调用它
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

¶3 如果对 `p.return_void()` 的重载决议成功，流出协程体末尾相当于 `co_return;`；否则（promise 只有 `return_value`）是未定义行为 {{ub}}。这和普通函数对应：返回值的协程必须显式 `co_return` 一个值。

## goto [stmt.goto]

¶1 `goto` 无条件地跳到标号标记的语句。标号必须在当前函数里，不能跳到外围函数或 lambda 之外。

`goto` 自身只有这一句规则，其他条款给它加了不少限制：

| 限制 | 出处 |
|---|---|
| 不能越过一个带初始化的局部变量的声明、进入它的作用域（`int x;` 这种空初始化除外） | [[stmt.dcl#2]] |
| 不能跳进 `if constexpr`、`if consteval` 的分支或展开语句的循环体 | [[stmt.label#3]] |
| 不能跳进 `try` 块或 handler | [[except.pre#3]] |
| 展开语句里不能有标号 | [[stmt.label#4]] |
| 常量求值中执行了 `goto`，表达式就不是常量表达式 | [[expr.const.core#2.36]] |

往回跳会先析构越过的变量，再重新初始化（[[stmt.dcl#2]] 的例 1）：

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
    X a = ++k;          // 每次 goto ly 都先析构 a，再重新构造
    if (k < 3) goto ly;
    std::printf("done ");
}   // X(1) ~X(1) X(2) ~X(2) X(3) done ~X(3)
```

```cpp error
void f() {
    goto l1;   // error: 不能跳进 try 块
    try {
    l1: ;
    } catch (...) { }
}
```

C++23 起（[[P2242R3]]），`constexpr` 函数里可以出现 `goto` 和标号，但常量求值时真正执行了一条 `goto`，求值就不是常量表达式。标准用 `goto` 来定义 `while` 等语句，[[expr.const.core]] 的注说明这些改写里的 `goto` 不算。

```cpp error
constexpr int f(int n) {
    if (n < 0) goto fail;
    return n;
fail:
    return -1;
}
static_assert(f(3) == 3);   // OK：没有执行 goto
constexpr int y = f(-1);    // error: 执行了 goto
```

## 历史

!!! history
    - C++98：`return` 以复制初始化返回值，允许但不保证省略拷贝；流出非 `void` 函数末尾是未定义行为。
    - C++11：操作数可以是花括号列表；引入隐式移动（两阶段重载决议）。
    - C++17：保证的复制消除（[[P0135R1]]）。
    - C++20：协程与 `co_return`；隐式移动扩展到右值引用变量等情形（[[P1825R0]]）。
    - C++23：可移动的名字直接是 xvalue（[[P2266R3]]）；`constexpr` 函数里允许 `goto` 和标号（[[P2242R3]]）。
    - C++26：返回的引用绑定到临时对象非良构（[[P2748R5]]）；后置条件在局部变量析构后、形参析构前求值；`break`、`continue` 可用于展开语句。

## 思考题

!!! question "1. 下面的函数在 C++20 和 C++23 中分别返回什么类型？"
    ```cpp
    decltype(auto) f() { int x = 0; return (x); }
    ```

<details markdown="1">
<summary>答案</summary>

C++20 中是 `int&`：`(x)` 是左值，`decltype((x))` 是 `int&`。C++23 起是 `int&&`：`x` 是可移动的，`(x)` 是 `return` 带括号的操作数，因此是 xvalue。两种情况都返回对局部变量的悬空引用。这不是绑定到临时对象，所以 ¶6 不管，Clang 只给出 `-Wreturn-stack-address` 警告。
</details>

!!! question "2. `struct S { const int& r; }; S g() { return S{42}; }` 违反 ¶6 吗？"

<details markdown="1">
<summary>答案</summary>

按措辞应该违反。由于保证的复制消除，`S{42}` 初始化的就是返回的对象，它的组成引用 `r` 在这条 `return` 里绑定到由 `42` 物化出的临时对象，属于 ¶6.2。不过本机 Clang 23 只对 `return {42};` 报错，对 `return S{42};` 不报错，也没有警告。无论编译器是否诊断，调用者拿到的 `r` 都是悬空的。
</details>

!!! question "3. 为什么 `return` 必须先初始化结果、再析构局部变量？举一个反过来会出错的例子。"

<details markdown="1">
<summary>答案</summary>

因为操作数常常要读局部变量。例如 `std::string s = ...; return s.substr(1);`，如果先析构 `s`，`substr` 读的就是已经析构的对象。上文 `snapshot` 里，如果先析构 `lock_guard` 再拷贝 `data`，拷贝就发生在锁外，可能与其他线程形成数据竞争。¶5 保证了先构造结果，再析构临时对象，再析构局部变量。
</details>

## 小结

| 语句 | 要点 |
|---|---|
| 所有跳转 | 离开作用域时按逆序析构已构造的局部对象；`std::exit`、`std::abort` 例外；协程挂起不算离开 |
| `break` | 位于循环、展开语句或 `switch` 中，结束最内层的那个 |
| `continue` | 位于循环或展开语句中，转到当前循环体末尾 |
| `return` | 复制初始化结果；可移动的局部变量是 xvalue（C++23）；结果对象的析构函数必须可用；先初始化结果，再析构临时对象和局部变量 |
| 返回绑定临时对象 | C++26 起非良构 |
| 流出末尾 | `void`、构造、析构函数相当于 `return;`；`main` 相当于 `return 0;`；协程看有没有 `return_void`；其他是未定义行为 |
| `co_return` | `{ p.return_value(e) 或 p.return_void(); goto final-suspend; }`；协程里不能有 `return` |
| `goto` | 只能跳到当前函数的标号；不能越过带初始化的声明，不能跳进控制流受限语句或 `try` 块 |
