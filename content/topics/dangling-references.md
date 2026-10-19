---
title: 悬垂引用全景
summary: 引用、指针和视图在所指对象死亡之后继续被使用的各种途径，每种途径的标准依据、编译器能否诊断，以及 AddressSanitizer 的报告。
status: draft
order: 16
since: c++98
papers: P2266R3, P2748R5, P2718R0, P2752R3
related: class.temporary, dcl.init.ref, stmt.return, stmt.ranged, basic.life, basic.compound, class.base.init, expr.prim.lambda.capture, dcl.fct.def.coroutine, dcl.init.list, topics/value-categories, topics/object-model, topics/undefined-behavior
tags: 悬垂引用, 生命周期, 临时对象, ASan, 专题
updated: 2026-10-19
---

!!! tldr
    - 引用、指针或视图在所指对象的生命周期结束后仍被使用，就是悬垂。通过它访问对象是 UB。
    - 临时对象只有在引用直接绑定到它时才延长寿命。中间经过任何一次函数调用（`std::move`、`std::max`、getter），延长就断了。
    - `string_view`、`span`、`initializer_list` 不是引用，从不延长任何对象的寿命。
    - lambda、协程、回调会推迟执行，按引用捕获或按引用传参时最容易悬垂。
    - C++23 让一部分"返回局部变量的引用"变成编译错误，并修复了范围 for；C++26 禁止 `return` 把引用绑定到临时量。其余情形靠 `-Wdangling` 系列警告、`[[clang::lifetimebound]]` 和 ASan。

## 什么叫悬垂

```cpp run title="view.cpp" ub
#include <cstdio>
#include <string>
#include <string_view>
std::string make_name() { return "a name long enough to defeat SSO"; }
int main() {
  std::string_view sv = make_name();   // 临时 string 在这一行末尾销毁
  std::printf("%c\n", sv[0]);          // UB：读已释放的堆内存
}
```

`make_name()` 返回的 `std::string` 是一个**临时对象**（[[g:temporary-object|temporary object]]），它在所在的[[g:full-expression|完整表达式]]结束时销毁，也就是这一行的分号处。`sv` 存着指向它缓冲区的指针，下一行再读就是读一块已经释放的内存。

一个引用、指针或视图在所指对象的生命周期结束之后仍被使用，就叫做**悬垂**（dangling）。标准里有两条规则管它：

- 对象的生命周期已经结束、存储还在时，通过指代它的 glvalue 访问对象或调用非静态成员函数是 UB（[[basic.life#8]]）；
- 存储也已经释放时，指向它的指针在之后的求值中不再有效，通过它间接访问是 UB（[[basic.compound#6]]）。

规则本身很简单，难点在于看出对象已经死了。C++ 的引用不拥有对象，编译器也不追踪谁借用了谁。对象什么时候死，由它的存储期（[[basic.stc]]）和临时对象的规则（[[class.temporary]]）决定，后者有不少例外。

下表按对象怎么死的分类，后面各节逐一展开：

| # | 途径 | 对象怎么死的 | 标准判定 | Clang 默认警告 | ASan 报告 |
|---|---|---|---|---|---|
| 1 | 返回局部变量的引用 | 函数返回，自动变量销毁 | C++23 起部分非良构，其余 UB | `-Wreturn-stack-address` | stack-use-after-return\* |
| 2 | 返回绑定到临时量的引用 | 完整表达式结束 | C++26 起非良构 | 错误 | — |
| 3 | 临时量经过函数调用再绑定到引用 | 完整表达式结束 | UB | 部分（`-Wdangling`） | stack-use-after-scope |
| 4 | 聚合的引用成员 | 圆括号或 `new` 初始化不延长寿命 | UB | `-Wdangling`、`-Wdangling-field` | stack-use-after-scope |
| 5 | `string_view`、`span` 指向临时量 | 视图不是引用，没有寿命延长 | UB | `-Wdangling-gsl` | heap-use-after-free |
| 6 | 范围 for 初始化器中的临时量 | C++20：初始化器末尾销毁 | C++20 UB，C++23 修复 | 无 | stack-use-after-scope |
| 7 | lambda 按引用捕获后逃逸 | 外层函数返回 | UB | 通常无 | stack-use-after-return\* |
| 8 | 协程的引用形参 | 调用者的完整表达式结束 | UB | 无 | stack-use-after-scope |
| 9 | 返回或保存 `initializer_list` | 背后的数组是临时量 | UB | `-Wreturn-stack-address` | stack-use-after-return\* |
| 10 | 迭代器、引用失效 | 容器重新分配内存 | UB（违反库的前置条件） | 无 | heap-use-after-free |

\* 本机（macOS arm64，Clang 23）的 ASan 默认不检测 stack-use-after-return，要用 `ASAN_OPTIONS=detect_stack_use_after_return=1` 运行。

## 1. 返回局部变量的引用

```cpp
int& r1()        { int x = 0; return x; }
const int& r1c() { int x = 0; return x; }
int& r1p()       { int x = 0; return (x); }
int& r1r()       { int x = 0; int& y = x; return y; }
```

C++20 中这四个函数都是良构的，调用后使用返回值才是 UB，Clang 对每一个都给出 `-Wreturn-stack-address` 警告。

C++23 的 [[P2266R3]] 改变了 `return` 语句里局部变量名的值类别：`return x;` 和 `return (x);` 中的 `x` 是[[g:move-eligible|可移动的]] id 表达式，属于 xvalue（[[expr.prim.id.unqual]]）。非 const 左值引用不能绑定 xvalue，所以：

| | C++20 | C++23 起 | 原因 |
|---|---|---|---|
| `r1`：`int&` 返回 `x` | 警告 | 错误 | 非 const 左值引用不能绑定 xvalue |
| `r1p`：`return (x);` | 警告 | 错误 | 带括号同样可移动 |
| `r1c`：`const int&` 返回 `x` | 警告 | 警告 | const 左值引用可以绑定 xvalue，仍然悬垂 |
| `r1r`：经由引用 `y` 返回 | 警告 | 警告 | `y` 是引用变量，不可移动 |

本机 Clang 23 对 `r1` 的错误信息说 "cannot bind to a temporary of type 'int'"，但 `x` 其实是 xvalue，不是临时量。这项变化是 P2266 的副作用，并不是专为悬垂设计的，所以 `r1c`、`r1r` 仍然只是警告。

编译器看不穿的写法连警告都没有：

```cpp run title="escape.cpp" ub
#include <cstdio>
int* make() {
  int local = 42;
  int* p = &local;
  return p;                  // 没有警告
}
int main() {
  int* p = make();
  std::printf("%d\n", *p);   // UB：local 已经销毁
}
```

```text
$ clang++ -std=c++2c -g -gdwarf-4 -fsanitize=address escape.cpp && ./a.out
42
$ ASAN_OPTIONS=detect_stack_use_after_return=1 ./a.out
==ERROR: AddressSanitizer: stack-use-after-return on address 0x000105fa0020 ...
READ of size 4 at 0x000105fa0020 thread T0
    #0 ... in main escape.cpp:9
Address 0x000105fa0020 is located in stack of thread T0 at offset 32 in frame
    #0 ... in make() escape.cpp:2
  This frame has 1 object(s):
    [32, 36) 'local' (line 3) <== Memory access at offset 32 is inside this variable
```

第一次运行输出了 `42`，因为栈上的旧值还没被覆盖。悬垂的代码通常看起来能用，这正是它危险的地方。

## 2. 返回绑定到临时量的引用 {{c++26}}

```cpp run title="return-temp.cpp" error
const int& f1() { return 42; }                        // 引用绑定到临时 int
const double& f2() { static int x = 42; return x; }   // int 转 double 产生临时量
struct R { const int& r; };
R f3() { return {42}; }                               // 返回对象的引用成员绑定到临时量
```

C++23 中这些都是良构的，只是必然悬垂。C++26 的 [[P2748R5]] 规定：`return` 语句把返回的引用绑定到一个临时表达式，程序非良构（[[stmt.return#6]]）。当前草案还把返回对象的**组成引用**（constituent reference：对象本身及其子对象中的引用成员，[[intro.object#12]]）也算在内（[[stmt.return#6.2]]），`f3` 就属于这种情况。本机 Clang 23 在 `-std=c++2c` 下对三者都报 "returning reference to local temporary object"，在 `-std=c++23` 下只是警告。

!!! lawyer "规则只看语法上的临时表达式"
    ```cpp
    auto&& id(auto&& r) { return static_cast<decltype(r)&&>(r); }
    auto&& f4() { return id(42); }   // 良构，但必然悬垂
    ```
    `id(42)` 是函数调用，不是临时表达式，所以规则管不到它。标准自己的例子也这样注释："OK, but probably a bug"。另外，`return R{42};` 按 [[stmt.return#6.2]] 的字面同样是把临时量绑定到返回对象的组成引用，但本机 Clang 23 只诊断 `return {42};` 这种写法。

## 3. 生命周期延长的规则与例外

[[g:lifetime-extension|生命周期延长]]是让临时对象活过完整表达式的唯一机制：引用直接绑定到一个临时对象（或它的子对象）时，临时对象的寿命延长到与引用相同（[[class.temporary#6]]）。

是否直接绑定按语法判定。只有经过 [[class.temporary#6]] 第 6.1–6.9 项列出的表达式得到的 glvalue 才算：临时量实质化本身、括号、对数组临时量取下标、用 `.` 访问非引用的数据成员、`.*`、不经过用户定义转换的四种 cast、目标是引用的花括号函数式转换、条件表达式、逗号表达式。

函数调用不在其中。临时量只要经过一次函数调用再出来，延长就断了：

```cpp
#include <algorithm>
#include <string>
#include <utility>
std::string make();
struct Person {
  std::string name;
  const std::string& get_name() const { return name; }
};
Person make_person();

const std::string& a = make();                    // 延长：直接绑定
const std::string& b = make_person().name;        // 延长：成员访问，整个 Person 活到 b 结束
const std::string& c = make_person().get_name();  // 悬垂：经过成员函数调用（无警告）
const std::string& d = std::move(make());         // 悬垂：std::move 是函数调用（-Wdangling）
const int& m = std::max(1, 2);                    // 悬垂：max 返回形参的引用（-Wdangling）
```

最后一行最不容易看出来，因为 `const T& max(const T&, const T&)` 的签名看起来没有问题：

```cpp run title="max.cpp" ub
#include <algorithm>
#include <cstdio>
int main(int argc, char**) {
  const int& m = std::max(argc, 2);   // 2 是绑定到形参的临时量，这一行末尾销毁
  std::printf("%d\n", m);             // UB
}
```

```text
max.cpp:4:33: warning: temporary bound to local reference 'm' will be destroyed at the end of the full-expression [-Wdangling]
==ERROR: AddressSanitizer: stack-use-after-scope ...
    #0 ... in main max.cpp:5
    [48, 52) 'ref.tmp' (line 4) <== Memory access at offset 48 is inside this variable
```

Clang 能对 `std::max` 和 `std::move` 报警，是因为 libc++ 给它们的形参标注了 `[[clang::lifetimebound]]`（见第 11 节）。自己写的 `get_name()` 不加注解，编译器不会提示。

同一段后面还列了三条明确不延长的例外（第 6.10–6.12 项）：绑定到函数调用的引用形参、绑定到圆括号聚合初始化中的引用成员、绑定到 *new-initializer* 中的引用。另外两种情形直接是非良构：构造函数的 *mem-initializer* 把引用成员绑定到临时量（[[class.base.init#8]]），以及上一节的 `return`。

## 4. 聚合中的引用成员

```cpp run title="agg-ref.cpp" ub
#include <cstdio>
#include <string>
struct Ref { const std::string& s; };
std::string temp() { return "a string long enough to be heap allocated"; }
int main() {
  Ref a{temp()};                 // OK：花括号聚合初始化，临时量延长到 a 结束
  Ref b(temp());                 // C++20 圆括号聚合初始化：不延长（[class.temporary]/6.11）
  Ref* c = new Ref{temp()};      // new-initializer：不延长（[class.temporary]/6.12）
  std::printf("%zu\n", a.s.size());
  std::printf("%zu\n", b.s.size());   // UB
  std::printf("%zu\n", c->s.size());  // UB
  delete c;
}
```

本机 Clang 23 对 `b` 给出 `-Wdangling`，对 `c` 给出 `-Wdangling-field`。ASan 在读取 `b.s` 时报告 stack-use-after-scope。

花括号和圆括号的区别是有意的。C++20 的圆括号聚合初始化按"调用一个构造函数"的模型设计（[[dcl.init#15]] 注 7），而构造函数的引用形参不会延长实参的寿命，所以 `Ref(temp())` 也不延长。

带引用成员的类型通常只应该从左值构造。把这条约束写进类型的办法是删除右值重载：

```cpp ok
#include <string>
struct NameRef {
  const std::string& s;
  explicit NameRef(const std::string& x) : s(x) {}
  explicit NameRef(std::string&&) = delete;   // 拒绝临时量
};
std::string temp();
std::string keep = "x";
NameRef ok{keep};
// NameRef bad{temp()};                       // error: 调用被删除的构造函数
```

## 5. 视图类型：`string_view`、`span`

`std::string_view` 和 `std::span` 不是引用，而是存着指针的普通类类型。生命周期延长只对引用起作用，所以视图从不延长任何对象的寿命。开头的 `view.cpp` 就是这种情况，Clang 和 ASan 的报告是：

```text
view.cpp:6:25: warning: object backing the pointer will be destroyed at the end of the full-expression [-Wdangling-gsl]
==ERROR: AddressSanitizer: heap-use-after-free ...
    #0 ... in main view.cpp:7
freed by thread T0 here:
    #1 ... in std::__1::basic_string<...>::~basic_string()
    #2 ... in main view.cpp:6
```

如果字符串短到能放进[[g:short-string-optimization|短字符串优化]]（SSO）的内部缓冲区，数据就在临时 `string` 对象内部，ASan 报告的会是 stack-use-after-scope。

Clang 的 `-Wdangling-gsl` 系列靠所有者（Owner）和指针（Pointer）两类类型注解工作：libc++ 把 `std::string`、`std::vector` 标为 Owner，把 `string_view`、`span`、迭代器标为 Pointer。本机 Clang 23 能识别这些模式：

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

中间只要多一层自己写的函数，它就看不出来了。设计接口时，`string_view` 作为形参很安全；作为返回值或成员保存时，要先确认底层的字符串由谁拥有、活多久。

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
  for (const std::string& s : load().get())   // C++20：临时 Doc 在循环开始前销毁
    std::printf("%zu\n", s.size());
}
```

范围 for 会改写成 `auto&& __range = load().get();` 再循环（[[stmt.ranged#1]]）。`__range` 绑定的是 `get()` 的返回值，又一次经过了函数调用，所以按第 3 节的规则，临时 `Doc` 在这个声明结束时就销毁了。本机 Clang 23 加 ASan 的结果：`-std=c++20` 报告 stack-use-after-scope，`-std=c++23` 正常输出 `43`。

C++23 的 [[P2718R0]] 新增了 [[class.temporary#7]]：范围 for 的初始化器中创建的所有临时对象，只要原本会在这个完整表达式末尾销毁，都延长到 `__range` 的寿命。C++20 版本没有任何警告。仍在用 C++20 的代码可以用 *init-statement* 显式持有对象：`for (auto d = load(); const auto& s : d.get())`。

这项修复只管初始化器里的临时对象。函数形参不是临时对象，所以 `const T& f2(T t) { return t; }` 配上 `for (auto e : f2(g()))` 仍然悬垂，详见 [[stmt.ranged]]。

## 7. lambda 按引用捕获

```cpp run title="lambda-ref.cpp" ub
#include <cstdio>
#include <functional>
std::function<int()> make_counter() {
  int count = 0;
  return [&] { return ++count; };   // 按引用捕获局部变量，闭包离开了作用域
}
int main() {
  auto next = make_counter();
  std::printf("%d\n", next());      // UB：count 已经不存在
}
```

按引用捕获的实体，闭包里的引用指代的就是原来那个实体。实体死后再调用闭包，[[expr.prim.lambda.capture#17]] 的注指出这很可能导致 UB。本机 Clang 23 对上例没有警告（闭包被装进了 `std::function`），开启 stack-use-after-return 检测后 ASan 报告：

```text
==ERROR: AddressSanitizer: stack-use-after-return ...
    #0 ... in make_counter()::$_0::operator()() const lambda-ref.cpp:5
```

同类的问题：

- 成员函数里的 `[=]` 会隐式捕获 `this`，实际上是按引用捕获了整个对象。C++20 弃用了这种隐式捕获，应写成 `[=, this]`，或者用 `[=, *this]` 复制对象。
- 异步回调：交给 `std::thread`、线程池或 I/O 库的回调按引用捕获了局部变量，函数返回之后回调才执行。

闭包只要可能活得比当前作用域长，就不要用 `[&]`。

## 8. 协程的引用形参

协程被调用时，形参会复制进协程状态，但引用形参的副本仍然是引用（[[dcl.fct.def.coroutine#13.1]]）。同一段的注 3 提醒：协程有按引用传递的形参时，在被引用的实体死后恢复协程，很可能导致 UB。

```cpp run title="coro-ref.cpp" ub
#include <coroutine>
#include <cstdio>
#include <exception>
#include <string>
#include <utility>

struct Lazy {                 // 最小的惰性协程：创建时挂起，get() 时才运行
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

Lazy length(const std::string& s) {   // 协程里保存的只是引用
  co_return s.size();
}

int main() {
  Lazy t = length(std::string(100, 'x'));   // 临时 string 在这一行末尾销毁
  std::printf("%zu\n", t.get());            // 协程这时才开始执行：s 悬垂
}
```

ASan 报告 stack-use-after-scope，位置在 `s.size()` 内部。

对普通函数，`const std::string&` 形参接临时量是安全的；对协程，函数体的执行被推迟到调用表达式之后，这种写法反而最危险。协程的形参应当按值传递，`std::string_view`、`std::span` 形参同样有问题。更多协程特有的生命周期问题见 [[topics/coroutines]]。

## 9. `std::initializer_list` 背后的数组

`std::initializer_list<E>` 只是一对指针，指向编译器生成的一个 `const E[N]` 数组，标准称为[[g:backing-array|backing array]]。这个数组和其他临时对象一样，只是用它初始化 `initializer_list` 对象时，会像引用绑定一样延长它的寿命（[[dcl.init.list#6]]）。这种延长不会传递给复制出来的 `initializer_list`：

```cpp run title="ilist.cpp" ub
#include <cstdio>
#include <initializer_list>
std::initializer_list<int> defaults(int a) { return {a, a + 1, a + 2}; }  // 数组是局部临时量
int main(int argc, char**) {
  for (int x : defaults(argc)) std::printf("%d ", x);   // UB
  std::puts("");
}
```

Clang 给出 `-Wreturn-stack-address` 警告，ASan 报告 stack-use-after-return。

C++26 的 [[P2752R3]] 允许实现把元素都是常量的 backing array 放进静态存储，但存储位置变了，生命周期规则没有变，标准的例子也强调这个数组不会活过函数调用。不要把 `initializer_list` 存进成员或作为返回值，需要保存时复制到 `std::vector` 或 `std::array`。

## 10. 迭代器与引用失效

标准库容器的每个修改操作都写明了它会使哪些引用、指针和迭代器**失效**（[[g:iterator-invalidation|invalidate]]）。例如 `vector::push_back` 在新大小超过容量时重新分配内存，使所有引用、指针和迭代器失效（[[vector.modifiers#2]]）。之后再使用它们违反了库的前置条件，同样是 UB。

```cpp run title="invalidate.cpp" ub
#include <cstdio>
#include <vector>
int main() {
  std::vector<int> v{1, 2, 3};
  int& first = v[0];
  v.push_back(4);                  // 容量不足，重新分配，first 悬垂
  std::printf("%d\n", first);      // UB
}
```

ASan 报告 heap-use-after-free。常见的变体有：边遍历边 `push_back` 或 `erase`；把 `&v[i]` 存进别的容器；修改 `std::string` 之后继续用之前的 `c_str()`。不同容器的规则差别很大：`std::list`、`std::map` 插入时不使任何东西失效；`std::deque` 在两端插入使迭代器失效但不使引用失效；`unordered_map` 重新散列使迭代器失效但不使引用失效。以各容器的条款为准。

## 11. 工具

### 编译器警告

`diagtool tree dangling` 列出本机 Clang 23 的 `-Wdangling` 组：

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

本页出现的几种都默认开启，不需要额外的 `-W` 选项。它们都只看一个声明或一条 `return` 语句内部的模式，跨函数的推理需要注解。

### `[[clang::lifetimebound]]`

这个属性告诉编译器，返回值的寿命受某个形参约束：

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
  const std::string& c = make_person().name;        // OK：成员访问，整个 Person 延长寿命
  (void)a; (void)b; (void)c;
}
```

Clang 23 对 `a`、`b` 两行给出 `-Wdangling`；去掉两个注解后，同一份代码没有任何警告。写在成员函数声明符之后的 `[[clang::lifetimebound]]` 作用于 `*this`。这个属性不改变程序的语义，只增加诊断。

### AddressSanitizer

| 报告类别 | 对应的悬垂 | 备注 |
|---|---|---|
| `heap-use-after-free` | 堆内存已释放（`string` 的缓冲区、`vector` 重新分配） | 默认开启 |
| `stack-use-after-scope` | 临时量或块内变量已经销毁，但还在同一个栈帧里 | 默认开启 |
| `stack-use-after-return` | 函数已经返回 | 本机需 `ASAN_OPTIONS=detect_stack_use_after_return=1`，有额外开销 |

ASan 只能报告真正执行到的访问，而且只有对象所在的内存被标记为不可访问时才会报告。内存池、自定义分配器都可能让它漏报。

本机 Homebrew Clang 23 搭配系统链接器时，ASan 的符号化器读不了默认的 DWARF 5 调试信息，报告里只有 `main+0x70` 这样的偏移。加 `-gdwarf-4` 就能看到上文那样的文件名和行号。

## 思考题

!!! question "1"
    `const auto& [k, v] = *map.find(key);` 中，`k`、`v` 会悬垂吗？如果 `find` 换成一个按值返回 `std::pair` 的函数呢？

<details markdown="1">
<summary>答案</summary>

`*map.find(key)` 是左值，指代 map 里的元素。结构化绑定背后的隐藏变量是对这个元素的引用，没有临时量，只要元素没被删除就不会悬垂。

换成按值返回 `std::pair` 的函数后，初始化器是 prvalue，隐藏变量 `const auto& e = f();` 直接绑定到实质化的临时量，按 [[class.temporary#6.1]] 延长寿命，`k`、`v` 指代这个临时 pair 的成员，同样不悬垂。只有 `const auto& [k, v] = f().get_pair_ref();` 这种经过函数调用返回引用的写法才会悬垂。
</details>

!!! question "2"
    `std::string_view sv = "literal";` 和 `std::string_view sv = std::string("literal");` 有什么区别？

<details markdown="1">
<summary>答案</summary>

字符串字面量对象具有静态存储期（[[lex.string]]），前者的 `sv` 永远不会悬垂。后者构造了一个临时 `std::string`，`sv` 指向它的缓冲区，分号处临时量销毁，`sv` 立刻悬垂，Clang 给出 `-Wdangling-gsl`。同理，`using namespace std::literals;` 之后 `std::string_view sv = "x"s;` 悬垂，而 `"x"sv` 不会。
</details>

!!! question "3"
    C++26 把 `return` 绑定临时量定为非良构，为什么没有把 `const int& m = std::max(1, 2);` 也定为非良构？

<details markdown="1">
<summary>答案</summary>

`return` 的情形能纯按语法判定：被绑定的就是一个临时表达式，函数返回后它必然已经销毁。`std::max` 的情形要知道返回的引用来自哪个形参，这是函数体的性质，声明里看不出来，标准在调用处无法判定（`max` 也可能返回一个静态对象的引用）。表达这种跨函数的信息需要 `[[clang::lifetimebound]]` 这样的注解，标准目前没有对应的语言机制。
</details>
