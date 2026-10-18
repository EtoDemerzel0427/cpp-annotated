---
title: 悬垂引用全景
summary: 引用、指针、视图在所指对象死亡后继续被使用的每一种途径——返回局部量与临时量（含 C++23/26 的新禁令）、生命周期延长的规则与例外、聚合中的引用成员、string_view/span 绑定临时量、范围 for 的 C++23 修复、lambda 按引用捕获、协程引用形参、initializer_list 的 backing array、迭代器失效；以及 -Wdangling 家族、[[clang::lifetimebound]] 与 ASan 的真实输出
status: draft
order: 16
since: c++98
papers: P2266R3, P2748R5, P2718R0, P2752R3
related: class.temporary, dcl.init.ref, stmt.return, stmt.ranged, basic.life, basic.compound, class.base.init, expr.prim.lambda.capture, dcl.fct.def.coroutine, dcl.init.list, topics/value-categories, topics/object-model, topics/undefined-behavior
tags: 悬垂引用, 生命周期, 临时对象, ASan, 专题
updated: 2026-10-18
---

**悬垂**（dangling）是指一个引用、指针或"视图"对象在它所指的对象**生命周期结束之后**仍被使用。从标准看，它落在两条规则上：

- 通过指代生命周期外对象的 glvalue **访问**对象、调用非静态成员函数等，是 UB（[[basic.life#8]]）；
- 如果连**存储**都已结束，指针值在之后的求值中**无效**，通过它间接是 UB（[[basic.compound#6]]）。

规则本身很简单，难的是**发现对象已经死了**。C++ 的引用不拥有对象，编译器不追踪借用关系；对象的死亡时刻由存储期（[[basic.stc]]）和临时对象规则（[[class.temporary]]）决定，后者充满例外。本专题把所有常见的悬垂途径按"对象是怎么死的"分类，每一类给出标准依据、编译器能否诊断、以及 AddressSanitizer 的真实报告。

| # | 途径 | 对象怎么死的 | 标准判定 | Clang 默认警告 | ASan 报告类别 |
|---|---|---|---|---|---|
| 1 | 返回局部变量的引用 | 函数返回，自动存储期结束 | C++23 起部分非良构，其余 UB | `-Wreturn-stack-address` | stack-use-after-return* |
| 2 | 返回绑定到临时量的引用 | 完整表达式结束 | C++26 非良构 | 错误 | — |
| 3 | 引用绑定到函数返回的引用 | 实参临时量在完整表达式末尾销毁 | UB | 部分（`-Wdangling`） | stack-use-after-scope |
| 4 | 聚合的引用成员 | 圆括号/new 初始化不延寿 | UB | `-Wdangling`、`-Wdangling-field` | stack-use-after-scope |
| 5 | `string_view`/`span` 绑定临时量 | 视图不是引用，无延寿可言 | UB | `-Wdangling-gsl` | heap-use-after-free |
| 6 | 范围 for 初始化器中的临时量 | C++20：初始化器末尾销毁 | C++20 UB，C++23 修复 | 无 | stack-use-after-scope |
| 7 | lambda 按引用捕获后逃逸 | 外层函数返回 | UB | 通常无 | stack-use-after-return* |
| 8 | 协程的引用形参 | 调用者的完整表达式结束 | UB | 无 | stack-use-after-scope |
| 9 | 返回/存储 `initializer_list` | backing array 是临时量 | UB | `-Wreturn-stack-address` | stack-use-after-return* |
| 10 | 迭代器/引用失效 | 容器重新分配 | UB（库前置条件） | 无 | heap-use-after-free |

\* 在本机（macOS arm64，Clang 23），stack-use-after-return 检测默认关闭，需 `ASAN_OPTIONS=detect_stack_use_after_return=1` 运行。

## 1. 返回局部变量的引用

```cpp
int& r1()        { int x = 0; return x; }
const int& r1c() { int x = 0; return x; }
int& r1p()       { int x = 0; return (x); }
int& r1r()       { int x = 0; int& y = x; return y; }
```

这四个函数在 C++20 中都是**良构**的，调用后使用返回值是 UB，Clang 对每一个都给出 `-Wreturn-stack-address` 警告。C++23 起情况变了：[[P2266R3]] 让 `return` 中的局部变量名（可带括号）成为**可移动的 id 表达式**，即 **xvalue**（[[expr.prim.id.unqual]]、[[class.copy.elision]]）。于是：

| | C++20 | C++23 / C++26 | 原因 |
|---|---|---|---|
| `r1`：`int&` 返回 `x` | 警告 | **错误** | 非 const 左值引用不能绑定 xvalue |
| `r1p`：`return (x);` | 警告 | **错误** | 带括号同样是可移动实体 |
| `r1c`：`const int&` 返回 `x` | 警告 | 警告 | const 左值引用可以绑定 xvalue，仍然悬垂 |
| `r1r`：经由引用 `y` 返回 | 警告 | 警告 | `y` 是引用，不是可移动实体 |

（本机 Clang 23 对 `r1` 的错误信息是"non-const lvalue reference to type 'int' cannot bind to a temporary of type 'int'"——说"temporary"并不准确，实际是 xvalue。）这个变化是 P2266 的副产品，不是它的目的，所以覆盖面有限：`r1c`、`r1r` 仍然只是警告。

当编译器看不穿时，连警告都没有：

```cpp run title="escape.cpp" ub
#include <cstdio>
int* make() {
  int local = 42;
  int* p = &local;
  return p;               // 编译器看不穿：没有警告
}
int main() {
  int* p = make();
  std::printf("%d\n", *p);   // UB: local 的存储期已结束
}
```

```text
$ clang++ -std=c++2c -g -fsanitize=address escape.cpp && ./a.out
42
$ ASAN_OPTIONS=detect_stack_use_after_return=1 ./a.out
==10873==ERROR: AddressSanitizer: stack-use-after-return on address 0x000102500020 ...
READ of size 4 at 0x000102500020 thread T0
    #0 0x000102fc3c6c in main escape.cpp:9

Address 0x000102500020 is located in stack of thread T0 at offset 32 in frame
    #0 0x000102fc3a58 in make() escape.cpp:2

  This frame has 1 object(s):
    [32, 36) 'local' (line 3) <== Memory access at offset 32 is inside this variable
```

注意第一次运行"正常"输出了 `42`——栈上的旧值还没被覆盖。这是悬垂最危险的地方：它通常**看起来能用**。

## 2. 返回绑定到临时量的引用 {{c++26}}

```cpp run title="return-temp.cpp" error
const int& f1() { return 42; }                 // 引用绑定到临时 int
const double& f2() { static int x = 42; return x; }   // int → double 转换产生临时量
struct R { const int& r; };
R f3() { return {42}; }                        // 返回对象的"组成引用"绑定到临时量
```

C++23 中这些都是良构的"必然悬垂"代码。C++26 通过 [[P2748R5]] 规定：`return` 语句把**返回的引用**绑定到**临时表达式**，程序非良构；当前草案的 [[stmt.return#6]] 还把返回对象的**组成引用**（[[intro.object#12]]）一并纳入（¶6.2）。本机 Clang 23 在 `-std=c++2c` 下对三者都报"returning reference to local temporary object"。

!!! lawyer "规则只看语法上的“临时表达式”"
    ```cpp
    auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
    auto&& f4() { return id(42); }      // 良构，但必然悬垂
    ```
    `id(42)` 是函数调用，不是临时表达式。这正是标准自己的例子（注释为 "OK, but probably a bug"）。另外，`return R{42};` 按 ¶6.2 的字面同样把临时量绑定到返回对象的组成引用，但本机 Clang 23 只诊断 `return {42};` 的形式。

## 3. 生命周期延长：规则与例外

**生命周期延长**（[[g:lifetime-extension]]）是唯一能让临时对象活过完整表达式的机制：引用直接绑定到临时对象（或其子对象）时，临时对象的寿命延长到引用的寿命（[[class.temporary#6]]）。问题在于"直接绑定"的判定是**语法性**的——只有经过 ¶6.1–¶6.9 那张清单上的表达式得到的 glvalue 才算：

- 临时量实质化本身、括号、对数组临时量下标、`.` 访问非引用数据成员、`.*`、不经用户定义转换的四种 cast、条件表达式、逗号表达式。

**函数调用不在清单上**。凡是临时量经过一次函数调用再"出来"，延长就断了：

```cpp
#include <algorithm>
#include <string>
#include <utility>
std::string make();
struct Person { std::string name; const std::string& get_name() const { return name; } };
Person make_person();

const std::string& a = make();                       // 延长：直接绑定
const std::string& b = make_person().name;           // 延长：成员访问，整个 Person 活到 b 结束
const std::string& c = make_person().get_name();     // 悬垂：经过了成员函数调用（Clang 无警告）
const std::string& d = std::move(make());            // 悬垂：std::move 是函数调用（-Wdangling）
const int& m = std::max(1, 2);                       // 悬垂：max 返回的是形参引用（-Wdangling）
```

最后一行最阴险，因为 `std::max` 的签名 `const T& max(const T&, const T&)` 看起来完全无害：

```cpp run title="max.cpp" ub
#include <algorithm>
#include <cstdio>
int main(int argc, char**) {
  const int& m = std::max(argc, 2);   // 2 是绑定到 max 形参的临时量：完整表达式结束即销毁
  std::printf("%d\n", m);             // UB
}
```

```text
==12099==ERROR: AddressSanitizer: stack-use-after-scope on address 0x00016fad6690 ...
READ of size 4 at 0x00016fad6690 thread T0
    #0 0x00010032f86c in main max.cpp:5
  This frame has 2 object(s):
    [32, 36) 'argc.addr'
    [48, 52) 'ref.tmp' (line 4) <== Memory access at offset 48 is inside this variable
```

Clang 对这一行（以及 `std::move` 那一行）给出 `-Wdangling` 警告——libc++ 给 `std::max` 和 `std::move` 的形参都标注了 `_LIBCPP_LIFETIMEBOUND`，即 `[[clang::lifetimebound]]`（见第 11 节）。对于你自己写的 `get_name()`，除非同样加上注解，编译器不会说什么。

¶6 的清单之外还有三条**明确不延长**的例外（¶6.10–¶6.12）：绑定到函数调用的引用形参、绑定到**圆括号**聚合初始化中的引用成员、绑定到 *new-initializer* 中的引用。以及另外两种情形如今已是非良构（构造函数 *mem-initializer* 中把引用成员绑定到临时量，[[class.base.init#8]]；以及上一节的 `return`）。完整清单和标准例子见 [[class.temporary]]。

## 4. 聚合中的引用成员

```cpp run title="agg-ref.cpp" ub
#include <cstdio>
#include <string>
struct Ref { const std::string& s; };
std::string temp() { return "a string long enough to be heap allocated"; }
int main() {
  Ref a{temp()};                 // OK: 花括号聚合初始化，临时量延寿至 a 结束
  Ref b(temp());                 // C++20 圆括号聚合初始化：不延寿（[class.temporary]/6.11）
  Ref* c = new Ref{temp()};      // new-initializer：不延寿（/6.12）
  std::printf("%zu\n", a.s.size());
  std::printf("%zu\n", b.s.size());   // UB
  std::printf("%zu\n", c->s.size());  // UB
  delete c;
}
```

本机 Clang 23 对 `b` 给出 `-Wdangling`、对 `c` 给出 `-Wdangling-field`，ASan 在读取 `b.s` 时报告 stack-use-after-scope。

花括号与圆括号的差异来自 [[dcl.init#15]]：C++20 的圆括号聚合初始化被设计为"像调用一个构造函数"，而构造函数的引用形参不延长实参临时量的寿命——为了让 `Ref(temp())` 和"假想的构造函数 `Ref(const std::string&)`"行为一致，标准刻意不延寿。

带引用成员的类型几乎总是"视图"或"参数包"——它们应该只活在一个完整表达式里，或者只从**左值**构造。把这种约束写进类型的办法是删除右值重载：

```cpp ok
#include <string>
struct NameRef {
  const std::string& s;
  explicit NameRef(const std::string& x) : s(x) {}
  explicit NameRef(std::string&&) = delete;     // 拒绝临时量
};
std::string temp();
std::string keep = "x";
NameRef ok{keep};
// NameRef bad{temp()};                         // error: 调用被删除的构造函数
```

## 5. 视图类型：`string_view`、`span`

`std::string_view` 和 `std::span` 不是引用，它们是**存着指针的值类型**。生命周期延长只针对引用，所以视图**永远**不会延长任何东西的寿命：

```cpp run title="view.cpp" ub
#include <cstdio>
#include <string>
#include <string_view>
std::string make_name() { return "a name long enough to defeat SSO"; }
int main() {
  std::string_view sv = make_name();   // 临时 string 在分号处销毁
  std::printf("%c\n", sv[0]);          // UB: 读已释放的堆内存
}
```

```text
view.cpp:6:25: warning: object backing the pointer will be destroyed at the end of the full-expression [-Wdangling-gsl]

==12022==ERROR: AddressSanitizer: heap-use-after-free on address 0x604000000390 ...
READ of size 1 at 0x604000000390 thread T0
    #0 0x000104a8f00c in main view.cpp:7
freed by thread T0 here:
    ...
    #1 0x0001807816ec in std::__1::basic_string<...>::~basic_string()+0x28 (libc++.1.dylib:arm64e+0x46ec)
    #2 0x000104a8ef9c in main view.cpp:6
previously allocated by thread T0 here:
    ...
    #4 0x000104a8ed6c in make_name() view.cpp:4
```

（字符串短到能放进 SSO 缓冲区时，数据在临时 `string` 对象内部，ASan 报告的会是 stack-use-after-scope。）

Clang 的 `-Wdangling-gsl` 系列基于"所有者/指针"（Owner/Pointer）类型注解工作：libc++ 把 `std::string`、`std::vector` 标为 Owner，把 `string_view`、`span`、迭代器标为 Pointer。本机 Clang 23 能识别的模式包括：

```cpp
#include <span>
#include <string>
#include <string_view>
#include <vector>
std::string make_name();
std::vector<int> make_vec();
std::string_view f() { std::string s = "abc"; return s; }   // -Wreturn-stack-address
void g() {
  std::string_view sv = make_name();          // -Wdangling-gsl
  std::span<const int> sp = make_vec();       // -Wdangling-gsl
  std::string_view v; v = std::string("t");   // -Wdangling-assignment-gsl
}
```

但只要中间多一层你自己的函数，它就看不见了。设计接口时的原则：**接受 `string_view` 作为形参很安全，返回或存储 `string_view` 要非常小心**。

## 6. 范围 for 的初始化器 {{c++23}}

```cpp run title="range-for.cpp" std=c++20 ub
#include <cstdio>
#include <string>
#include <vector>
struct Doc {
  std::vector<std::string> lines{"first line, long enough to live on the heap"};
  const std::vector<std::string>& get() const { return lines; }
};
Doc load() { return {}; }
int main() {
  for (const std::string& s : load().get())   // C++20：load() 的临时 Doc 在循环开始前销毁
    std::printf("%zu\n", s.size());
}
```

范围 for 被改写为 `auto&& __range = load().get();` 再循环（[[stmt.ranged#1]]）。`__range` 绑定的是 `get()` 的返回值——又一次"经过函数调用"——所以按 ¶6 的一般规则，临时 `Doc` 在这个声明结束时就销毁了。本机 Clang 23 的结果：

```text
-std=c++20:  ERROR: AddressSanitizer: stack-use-after-scope ... in main range-for.cpp:10
-std=c++23:  43
```

C++23 的 [[P2718R0]] 新增了 [[class.temporary#7]]：*for-range-initializer* 中创建的**所有**临时对象，若本应在该完整表达式末尾销毁，都延长到 `__range` 的寿命。没有任何警告会提醒你 C++20 版本有问题，所以如果代码库仍在 C++20，用 *init-statement* 显式持有对象：`for (auto d = load(); const auto& s : d.get())`。

修复的边界：它只管 *for-range-initializer* 里的临时对象。函数**形参**不是临时对象——`const T& f2(T t) { return t; }` 然后 `for (auto e : f2(g()))` 依然悬垂，详见 [[stmt.ranged]]。

## 7. lambda 按引用捕获

```cpp run title="lambda-ref.cpp" ub
#include <cstdio>
#include <functional>
std::function<int()> make_counter() {
  int count = 0;
  return [&] { return ++count; };    // 按引用捕获局部变量，闭包逃出了作用域
}
int main() {
  auto next = make_counter();
  std::printf("%d\n", next());       // UB: count 已经不存在
}
```

按引用捕获的实体，标准只说闭包里的引用"指代同一个实体"；实体死后再调用闭包，[[expr.prim.lambda.capture#17]] 的注明确指出"很可能导致未定义行为"。本机 Clang 23 对上例**没有任何警告**（闭包被装进了 `std::function`），ASan（开启 stack-use-after-return）报告：

```text
==13108==ERROR: AddressSanitizer: stack-use-after-return on address 0x000101bc0020 ...
READ of size 4 at 0x000101bc0020 thread T0
    #0 0x000100382af0 in make_counter()::$_0::operator()() const lambda-ref.cpp:5
Address 0x000104680020 is located in stack of thread T0 at offset 32 in frame
    #0 0x000102e31d54 in make_counter() lambda-ref.cpp:3
```

同类陷阱：

- `[=]` 在成员函数里**隐式捕获 `this`**（按引用捕获了整个对象）。C++20 弃用了经由 `[=]` 隐式捕获 `this`，应写 `[=, this]` 或 `[=, *this]`（后者复制对象）。
- 异步回调：`std::thread`、线程池、`asio` 的 handler 里按引用捕获局部变量，函数返回后回调才执行。
- 规则：**闭包活得比当前作用域长，就不要用 `[&]`**。

## 8. 协程的引用形参

协程的形参会被复制进协程帧，但对**引用**形参，"副本"仍是一个引用（[[dcl.fct.def.coroutine#13]] ¶13.1）。标准的注 3 直接警告：若协程有按引用传递的形参，在被引用实体生命周期结束后恢复协程，很可能导致 UB。

```cpp run title="coro-ref.cpp" ub
#include <coroutine>
#include <cstdio>
#include <exception>
#include <string>
#include <utility>

struct Lazy {                                   // 最小的惰性协程：创建时挂起，get() 时才运行
  struct promise_type {
    std::size_t value = 0;
    Lazy get_return_object() { return Lazy{Handle::from_promise(*this)}; }
    std::suspend_always initial_suspend() noexcept { return {}; }
    std::suspend_always final_suspend() noexcept { return {}; }
    void return_value(std::size_t v) { value = v; }
    void unhandled_exception() { std::terminate(); }
  };
  using Handle = std::coroutine_handle<promise_type>;
  explicit Lazy(Handle h) : h(h) {}
  Lazy(Lazy&& o) noexcept : h(std::exchange(o.h, {})) {}
  ~Lazy() { if (h) h.destroy(); }
  std::size_t get() { h.resume(); return h.promise().value; }
  Handle h;
};

Lazy length(const std::string& s) {   // 协程帧里保存的只是引用
  co_return s.size();
}

int main() {
  Lazy t = length(std::string(100, 'x'));   // 临时 string 在这一行结束时销毁
  std::printf("%zu\n", t.get());            // 协程此时才开始执行：s 悬垂
}
```

```text
==13242==ERROR: AddressSanitizer: stack-use-after-scope on address 0x00016b4ae637 ...
    #0 ... in std::__1::basic_string<...>::__is_long() const string:2053
    #1 ... in std::__1::basic_string<...>::size() const string:1207
    ...
```

对普通函数而言，`const std::string&` 形参接临时量是最安全的写法；对协程而言，它是最危险的写法——因为协程体的执行被推迟到了调用表达式之后。**协程的形参优先按值传递**；`std::string_view`、`std::span` 形参同样危险。

## 9. `std::initializer_list` 的 backing array

`std::initializer_list<E>` 只是一对指针，指向一个编译器生成的 `const E[N]` **backing array**。该数组的寿命与其他临时对象相同，只是"用它初始化 `initializer_list` 对象"会像引用绑定一样延长它的寿命（[[dcl.init.list#6]]）——而这种延长**不会**再传递到复制出来的 `initializer_list`：

```cpp run title="ilist.cpp" ub
#include <cstdio>
#include <initializer_list>
std::initializer_list<int> defaults(int a) { return {a, a + 1, a + 2}; }  // backing array 是局部临时量
int main(int argc, char**) {
  for (int x : defaults(argc)) std::printf("%d ", x);   // UB
  std::puts("");
}
```

```text
ilist.cpp:3:53: warning: returning address of local temporary object [-Wreturn-stack-address]

==13597==ERROR: AddressSanitizer: stack-use-after-return on address 0x000105d00060 ...
    [32, 44) 'ref.tmp' (line 3) <== Memory access at offset 32 is inside this variable
SUMMARY: AddressSanitizer: stack-use-after-return ilist.cpp:5 in main
```

C++26 的 [[P2752R3]] 允许实现把元素均为常量的 backing array 放进**静态存储**（标准例子里的 `static constexpr double __b[3]`），但例子同时强调"`__b` 不会活过对 `f` 的调用"——存储位置变了，**生命周期规则没变**。不要把 `initializer_list` 存进成员、不要返回它；需要保存时复制到 `std::vector` 或 `std::array`。

## 10. 迭代器与引用失效

标准库容器的成员函数会在说明中写明哪些操作**使引用、指针、迭代器失效**。例如 `vector::push_back` 在发生重新分配时使**所有**引用、指针和迭代器失效（[[vector.modifiers]] ¶2）。失效之后使用它们，违反的是库函数的前置条件，也是 UB。

```cpp run title="invalidate.cpp" ub
#include <cstdio>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  int& first = v[0];
  v.push_back(4);                  // 容量不足 → 重新分配，first 悬垂
  std::printf("%d\n", first);      // UB
}
```

```text
==13613==ERROR: AddressSanitizer: heap-use-after-free on address 0x6020000000d0 ...
    #0 0x000104cd3ccc in main invalidate.cpp:7
SUMMARY: AddressSanitizer: heap-use-after-free invalidate.cpp:7 in main
```

经典变体：边遍历边 `push_back`/`erase`；把 `&v[i]` 存进另一个容器；`std::string` 的 `c_str()` 在修改后继续使用；`unordered_map` rehash 使迭代器（但不使引用）失效。不同容器的失效规则差别很大（`std::list`、`std::map` 插入不使任何东西失效，`std::deque` 两端插入使迭代器失效但不使引用失效），以各容器条款为准。

## 11. 工具

### 编译器警告

本机 Clang 23 的 `-Wdangling` 组包含以下子警告（本文出现过的几种无需任何 `-W` 选项即默认开启）：

```text
-Wdangling
  -Wdangling-assignment
  -Wdangling-assignment-gsl
  -Wdangling-capture
  -Wdangling-field
  -Wdangling-initializer-list
  -Wdangling-gsl
  -Wreturn-stack-address
```

（由 `diagtool tree dangling` 列出。）这些警告都是**局部的**：它们只看一个声明或一条 `return` 语句里的模式。跨函数的生命周期推理需要注解。

### `[[clang::lifetimebound]]`

把"返回值的寿命受这个形参约束"告诉编译器：

```cpp
#include <map>
#include <string>
const std::string& get_or(const std::map<int, std::string>& m, int key,
                          const std::string& fallback [[clang::lifetimebound]]) {
  auto it = m.find(key);
  return it == m.end() ? fallback : it->second;
}
struct Person {
  std::string name;
  const std::string& get_name() const [[clang::lifetimebound]] { return name; }
};
Person make_person();
void use(const std::map<int, std::string>& m) {
  const std::string& a = get_or(m, 1, "none");      // 警告：临时 string 绑定到 lifetimebound 形参
  const std::string& b = make_person().get_name();  // 警告：临时 Person
  const std::string& c = make_person().name;        // OK：成员访问，延长整个 Person 的寿命
  (void)a; (void)b; (void)c;
}
```

上例编译时 Clang 23 对 `a`、`b` 两行给出 `-Wdangling`；删掉两个注解后，同一份代码**零警告**。放在成员函数声明符之后的 `[[clang::lifetimebound]]` 作用于隐式对象形参（`*this`）。这个注解不改变语义，只增加诊断；它也是 libc++ 能对 `std::max` 报警的原因。

### AddressSanitizer

| 报告类别 | 对应悬垂 | 备注 |
|---|---|---|
| `heap-use-after-free` | 堆对象已释放（`string` 缓冲区、`vector` 重新分配） | 默认开启 |
| `stack-use-after-scope` | 临时量或块内变量的作用域已结束，但仍在同一栈帧 | 默认开启 |
| `stack-use-after-return` | 函数已返回 | 本机需 `ASAN_OPTIONS=detect_stack_use_after_return=1`；有额外开销 |

ASan 只能报告**真正执行到**的访问，而且只在对象所在的内存被"投毒"时才报告——内存池、自定义分配器、尚未回收的栈帧都会让它沉默。

!!! tip "让 ASan 报告带上行号"
    本机 Homebrew Clang 23 搭配系统链接器时，默认 DWARF 5 调试信息无法被 ASan 的符号化器解析（只显示 `main+0x70`）；加 `-gdwarf-4` 即可得到上文那样的 `file.cpp:行号`。

## 思考题

!!! question "1"
    `const auto& [k, v] = *map.find(key);` 中，`k`、`v` 会悬垂吗？如果 `find` 换成一个按值返回 `std::pair` 的函数呢？

<details markdown="1">
<summary>答案</summary>

`*map.find(key)` 是左值（指代 map 中的元素），结构化绑定的隐藏变量是对该元素的引用，没有临时量，不悬垂（只要元素没被删除）。换成按值返回 `std::pair` 的函数调用后，初始化器是 prvalue，隐藏变量 `const auto& e = f();` 直接绑定到实质化的临时量，按 [[class.temporary#6]] ¶6.1 **延寿**——`k`、`v` 指代该临时 pair 的成员，同样不悬垂。悬垂只会出现在 `const auto& [k, v] = f().first_and_second();` 这类"经过函数调用返回引用"的情形。
</details>

!!! question "2"
    `std::string_view sv = "literal";` 和 `std::string_view sv = std::string("literal");` 有何区别？

<details markdown="1">
<summary>答案</summary>

前者的字符串字面量对象具有**静态存储期**（[[lex.string]]），`sv` 永不悬垂。后者构造了一个临时 `std::string`，`sv` 指向它的缓冲区，分号处临时量销毁，`sv` 立即悬垂——Clang 给出 `-Wdangling-gsl`。同理 `using namespace std::literals; std::string_view sv = "x"s;` 也悬垂，而 `"x"sv` 不悬垂。
</details>

!!! question "3"
    为什么 C++26 只把 `return` 绑定临时量定为非良构，而没有把 `const int& m = std::max(1, 2);` 也定为非良构？

<details markdown="1">
<summary>答案</summary>

`return` 的情形可以纯语法判定：被绑定的就是一个**临时表达式**，返回后它必然已死。`std::max` 的情形需要知道"返回的引用来自哪个形参"——这是函数体的属性，不在声明中，标准在调用处无法判定（`max` 也可能返回一个静态对象的引用）。表达这种跨函数信息需要像 `[[clang::lifetimebound]]` 那样的注解，标准目前没有对应的语言机制。
</details>

## 小结

!!! summary
    - 悬垂的本质：**引用/指针/视图的寿命比所指对象长**。标准从不追踪借用，编译器只能识别局部模式。
    - 生命周期延长是**语法性**的：只有直接绑定（经 ¶6.1–¶6.9 的表达式）才延长；**任何函数调用都会切断它**，包括 `std::move`、`std::max`、getter。
    - **视图类型永不延寿**；返回或存储 `string_view`、`span`、`initializer_list` 前先问"底层对象谁拥有"。
    - 推迟执行的代码——lambda、协程、回调——是悬垂的高发区：**按值捕获、按值传参**。
    - 语言在逐步收紧：C++23 让 `return` 局部变量绑定非 const 左值引用变成错误、修复了范围 for；C++26 禁止 `return` 绑定临时量。其余靠 `-Wdangling` 家族、`[[clang::lifetimebound]]` 和 ASan（记得开 `detect_stack_use_after_return`）。
