---
title: C++ 与 ISO C++ 2020 的差异
summary: 从 C++20 升级到 C++23 时，哪些原来合法的代码会报错或改变行为：标识符字符集、隐式移动、多维下标、范围 for 的临时对象生命周期、u8 字面量初始化 char 数组、继承构造函数参与 CTAD、std::format 的编译期检查、substr 的右值重载、barrier 的完成步骤等。
status: done
covers: *
related: diff, diff.cpp23, diff.cpp17, class.temporary, stmt.ranged, expr.prim.id, format, string.classes
tags: 附录, 兼容性, 迁移, C++23
updated: 2026-10-19
---

!!! tldr
    - 范围 `for` 的初始化器中的所有临时对象都活到循环结束。代码照常编译，但析构变晚了，持锁的临时对象可能因此导致死锁。
    - `return x;` 中可移动的局部变量或右值引用现在直接是 xvalue，返回 `int&` 的函数不能再直接 `return` 一个 `int&&` 形参。
    - `a[1, 2]` 不再是逗号表达式，而是给 `operator[]` 传两个实参，为 `std::mdspan` 的多维下标让路。
    - `std::format` 在编译期检查格式串，位域不能直接作实参，`bool` 和字符不能作动态宽度。这几条主流库在 `-std=c++20` 下也已经生效。
    - 对 `std::move(s).substr(...)`，源字符串不再保证不变；`std::barrier` 的完成函数何时、在哪个线程运行，有了更多由实现决定的余地。

[diff.cpp20] 列出 C++23 相对 C++20 的不兼容：原来良构的代码，在 C++23 中变成非良构，或者含义改变。每一条在标准里都写成同样的格式：受影响的条款、改了什么、为什么改、对旧代码有什么影响。

¶1 这一节列的是在前面各节之外的差异，也就是说，从 C++20 升级到当前草案，还要再看 [[diff.cpp23]] 和 [[diff.cpp26]]。条目按正文的章节顺序排列。文中的实测都用本机 Clang 23.1.3 + libc++，对比 `-std=c++20` 与 `-std=c++23`。

## 词法约定 [diff.cpp20.lex] {#diff.cpp20.lex}

### 标识符改用 Unicode 的 XID 属性

```cpp error
int a¨;   // error: U+00A8 不是 XID_Continue
```

¶1 C++23 起，标识符的首字符必须具有 Unicode 属性 XID_Start 或是 `_`，其余字符必须具有 XID_Continue，并且整个标识符必须是 Unicode 规范化形式 C（NFC）（[[lex.name]]、[[uaxid]]）。C++20 用的是一张自定的码位区间表，收录了不少 XID 之外的字符，比如上例中的分音符 ¨。

这样改是为了把容易混淆的字符挡在标识符之外。要求 NFC，是因为同一个带重音的字母可以有两种编码（一个预组合字符，或者字母加组合附加符），规范化保证同一个名字在不同翻译单元里是同一串字节，链接器看到的符号一致。

Clang 23 在所有语言模式下都用新的 XID 规则，但没有检查 NFC：`e` 加 U+0301 组合重音这样的非 NFC 标识符在各模式下都被接受。

### 拼接的字符串字面量不能有冲突的编码前缀

```cpp error
auto c = L"a" U"b";   // error: C++20 中是有条件支持的
```

¶2 相邻的字符串字面量会拼接成一个（[[lex.string]]）。如果两边都有编码前缀而且不同，C++20 规定为**有条件支持**（实现可以选择不支持，不支持时必须诊断），C++23 改为非良构。从来没有实现支持过它，所以这条对实际代码没有影响。一边有前缀、另一边没有的拼接（`L"a" "b"`）仍然合法。

## 表达式 [diff.cpp20.expr] {#diff.cpp20.expr}

### 可移动的 id 表达式从左值变成 xvalue

```cpp
decltype(auto) f(int&& x) { return (x); }   // C++23 返回 int&&；C++20 返回 int&
int& g(int&& x) { return x; }               // error: C++20 中良构
```

¶1 函数返回一个局部对象时，编译器会尽量移动而不是复制，这叫**隐式移动**（[[class.copy.elision]]）。C++20 的做法是先把返回的名字当右值做一次重载决议，失败了再当左值做一次。C++23 换成了更简单的规则：`return`、`co_return` 语句或 throw 表达式的操作数如果是一个可移动的 id 表达式（[[g:move-eligible]]，它命名一个自动存储期的非 volatile 对象，或者这种对象的右值引用），它本身就是 xvalue（[[expr.prim.id.unqual]]）。

旧的两阶段规则复杂，而且有漏洞：`int&& h(int&& x) { return x; }` 在 C++20 中无法编译，因为返回类型是引用时不做那次右值重载决议，`x` 仍按左值处理。改成 xvalue 之后，依赖这个名字是左值的代码就会变：`f` 中 `decltype((x))` 由值类别决定，xvalue 得到 `int&&`；`g` 中 xvalue 不能绑定到 `int&`。

确实要返回左值引用时，写 `return static_cast<int&>(x);`。Clang 23 已经实现，两种模式的结果与上面的注释一致。

### 下标中的逗号

```cpp
int a[3];
int x = a[1, 2];     // error: C++20 中等价于 a[(1, 2)]
int y = a[(1, 2)];   // OK：逗号表达式，取 a[2]
```

¶2 C++23 起，`a[x, y]` 中的逗号不再是逗号运算符，而是分隔下标运算符的多个实参（[[expr.sub]]）。对类类型，`m[1, 2]` 调用 `m.operator[](1, 2)`，这是 `std::mdspan` 多维下标所用的语法。内置的下标运算符只接受一个实参，所以对数组这样写是非良构的。

C++20 已经把下标里不加括号的逗号表达式列为弃用，C++23 把这个语法改作他用。真的需要逗号运算符时加括号。Clang 23 在 `-std=c++20` 下给出 `-Wdeprecated-comma-subscript` 警告，`-std=c++23` 下报错。

## 语句 [diff.cpp20.stmt] {#diff.cpp20.stmt}

### 范围 `for` 初始化器中的临时对象活到循环结束

```cpp run title="for_temp.cpp" ok
#include <cstdio>
#include <vector>
struct G { const char* n; ~G() { std::printf("~G %s\n", n); } };
std::vector<int> make(const G&) { return {1, 2}; }
int main() {
  for (int x : make(G{"temp"})) std::printf("x=%d\n", x);
}
```

本机输出如下。`-std=c++20` 下 `~G temp` 在循环开始前打印，`-std=c++23` 下在循环结束后打印：

```text
-std=c++20      -std=c++23
~G temp         x=1
x=1             x=2
x=2             ~G temp
```

¶1 范围 `for` 等价于先用初始化器初始化一个引用 `auto&& __range`，再遍历它（[[stmt.ranged]]）。C++20 中，只有直接绑定到 `__range` 的那个临时对象会延长生命周期，初始化器里的其他临时对象在初始化完成时就销毁了。C++23 规定初始化器中创建的所有临时对象都活到整个循环结束（[[class.temporary]]）。

这条改动修掉了一个经典陷阱：`for (auto x : make().items())` 中，`make()` 返回的临时对象原来在循环开始前就销毁，`items()` 返回的引用随之悬空，行为未定义。新规则下这样写是安全的。

代价是一部分临时对象的析构变晚了。如果析构有副作用，比如解锁，行为就变了。标准给的例子：

```cpp
void f() {
  std::vector<int> v = { 42, 17, 13 };
  std::mutex m;

  for (int x : static_cast<void>(std::lock_guard<std::mutex>(m)), v) {
    // C++20：上面的临时 lock_guard 在循环开始前就解锁了
    std::lock_guard<std::mutex> guard(m);   // C++23：m 仍被锁着，死锁
  }
}
```

本机运行这个例子，`-std=c++20` 正常结束，`-std=c++23` 卡住不动。编译器对此不给任何诊断，升级时要检查初始化器里带锁、作用域守卫之类临时对象的范围 `for`，把它们移到循环外的具名变量中。

## 声明 [diff.cpp20.dcl] {#diff.cpp20.dcl}

### UTF-8 字符串字面量可以初始化 `char` 数组

```cpp error
struct A { char8_t s[10]; };
struct B { char s[10]; };

void f(A);
void f(B);

int main() {
  f({u8""});   // error: 歧义；C++20 中只能匹配 A
}
```

¶1 C++20 把 `u8"..."` 的类型改成 `const char8_t` 的数组之后，`char s[] = u8"x";` 变成了非良构（见 [[diff.cpp17]] 的 [lex] 一节）。C++23 为了兼容旧代码，又允许用 UTF-8 字符串字面量初始化 `char` 和 `unsigned char` 数组（[[dcl.init.string]]）。

副作用是一个 `u8` 字面量现在既能初始化 `char8_t` 数组，也能初始化 `char` 数组。上例中 `{u8""}` 对两个聚合都可行，原来唯一的选择变成了歧义。给实参写明类型，例如 `f(A{u8""})`，即可解决。

Clang 23 把这条当作缺陷修正，在 `-std=c++20` 下也报歧义，`char a[] = u8"abc";` 在两种模式下都被接受。

## 重载 [diff.cpp20.over] {#diff.cpp20.over}

### 类模板实参推导考虑继承的构造函数

```cpp error
template<typename T>
struct B { B(T); };

template<typename T>
struct D : B<T*> {
  D(T);
  using B<T*>::B;
  T m = "a";   // #1
};

D d("");   // error: T 推导为 const char，#1 非良构
           // C++20：T 推导为 const char*，良构
```

¶1 写 `D d("");` 而不给模板实参时，编译器根据构造函数推导 `T`，这叫**类模板实参推导**（CTAD，[[over.match.class.deduct]]）。C++23 起，派生类模板用 using 声明继承的基类构造函数也参与推导。既然 `D("")` 能调用继承来的 `B(T*)`，推导时也应当考虑它。

C++20 中只有 `D(T)` 参与，`T` 推导为 `const char*`。C++23 中继承来的 `B(T*)` 匹配得更好，`T` 推导为 `const char`，于是成员 `T m = "a";` 非良构。写出模板实参或者加一条推导指引就能恢复原意。

Clang 23 还没有实现这条，两种模式都推导出 `D<const char*>`。

## 模板 [diff.cpp20.temp] {#diff.cpp20.temp}

### 从异常说明推导模板实参

```cpp error
template<bool> struct A { };
template<bool B> void f(void (*)(A<B>) noexcept(B));
void g(A<false>) noexcept;
void h() {
  f(g);   // error: C++20 中良构
}
```

¶1 C++23 起，`noexcept(B)` 中的 `B` 可以被推导（[[temp.deduct.type]]），这样泛型代码就能用一个模板同时处理抛出和不抛出的函数。

C++20 中只能从 `A<B>` 推出 `B = false`，形参类型是普通的函数指针，`noexcept` 函数的指针可以隐式转换成它，调用成功。C++23 中还从 `noexcept(B)` 推出 `B = true`，两次推导冲突，推导失败。显式写出 `f<false>(g)` 就能编译。

Clang 23 在 `-std=c++20` 下也按新规则推导，两种模式都报错。

## 库引言 [diff.cpp20.library] {#diff.cpp20.library}

¶1 C++23 新增头文件 `<expected>`、`<flat_map>`、`<flat_set>`、`<generator>`、`<mdspan>`、`<print>`、`<spanstream>`、`<stacktrace>`、`<stdatomic.h>` 和 `<stdfloat>`（[[headers]]）。项目里有同名头文件并用 `#include <...>` 包含时，可能拿到标准库的版本，`<print>` 和 `<expected>` 最常撞名。

## 概念库 [diff.cpp20.concepts] {#diff.cpp20.concepts}

### `equality_comparable_with` 不再包含 `common_reference_with`

```cpp error
template<class T, class U>
  requires equality_comparable_with<T, U>
bool attempted_equals(const T&, const U& u);   // C++20 选中这个

template<class T, class U>
  requires common_reference_with<const remove_reference_t<T>&,
                                 const remove_reference_t<U>&>
bool attempted_equals(const T& t, const U& u);

bool test(shared_ptr<int> p) {
  return attempted_equals(p, nullptr);   // error: 歧义；C++20 中良构
}
```

¶1 两个重载都满足约束时，约束更强的那个胜出。判断强弱看一个约束是否**包含**（subsume）另一个，也就是展开后是否包含对方的全部原子约束（[[temp.constr.order]]）。C++20 的 `equality_comparable_with<T, U>` 里直接写了 `common_reference_with<...>`，所以第一个重载更强，被选中。

C++23 把 `three_way_comparable_with`、`equality_comparable_with`、`totally_ordered_with` 中的 `common_reference_with` 换成了一个仅用于阐述的概念（[[cmp.concept]]、[[concept.equalitycomparable]]、[[concept.totallyordered]]），目的是让不可复制、只能移动的类型（例如与 `nullptr` 比较的 `unique_ptr`）也能满足这些概念。包含关系随之消失，两个重载不分强弱，调用变成歧义。

libc++ 把这条当作缺陷修正，`-std=c++20` 下也报歧义。

## 内存管理库 [diff.cpp20.memory] {#diff.cpp20.memory}

¶1 C++23 禁止程序对 `allocator_traits` 做部分特化或显式特化（[[allocator.traits.general]]），以便给它增加 `allocate_at_least` 以及将来的其他成员：用户自己的特化会缺少这些新成员。

违反这条规则的程序是**非良构、不要求诊断**的（IFNDR）：编译器不必报错，代码可能照常编译，但标准不再保证任何结果。本机 Clang 23 对这样的特化没有任何诊断。定制应当放回分配器类型本身，`allocator_traits` 会读取分配器里的同名成员。

## 通用工具库 [diff.cpp20.utilities] {#diff.cpp20.utilities}

这一节的四条都是对 `std::format` 的修正。libc++ 在 `-std=c++20` 下也已经是新行为，其中编译期检查格式串和改用转发引用两项是以缺陷报告的形式追溯适用于 C++20 的。

### 格式串在编译期检查

```cpp error
auto s = std::format("{:d}", "I am not a number");
// error: C++20 中运行时抛出 format_error
```

¶1 `format`、`format_to`、`vformat_to`、`format_to_n`、`formatted_size` 的格式串形参改为 `format_string<Args...>` 类型（[[format]]）。它的构造函数是 `consteval` 的，在编译期解析格式串，并检查它与实参类型是否匹配，所以格式串写错直接编译失败。`format_args_t` 同时被删除。

运行期才确定的格式串改用 `std::vformat(fmt, std::make_format_args(args...))`，或者 C++26 的 `std::runtime_format`。

### 位域不能直接作格式化实参

```cpp
struct tiny { int bit: 1; };
auto t = tiny();
std::format("{}", t.bit);    // error: C++20 中返回 "0"
std::format("{}", +t.bit);   // OK：先复制成 int
```

¶2 `format` 等函数的实参类型从 `const Args&...` 改为转发引用 `Args&&...`（[[format]]），这样才能格式化那些在 const 状态下不能迭代、也不能复制的视图，例如 `filter_view`。非 const 的引用不能绑定到位域，所以位域作实参变成非良构，先复制一份即可。

### 动态宽度和精度只接受整数类型

```cpp
std::format("{:*^{}}", "", true);   // error: C++20 中返回 "*"
std::format("{:*^{}}", "", '1');    // error: C++20 中输出个数由实现定义
```

¶3 格式串 `{:*^{}}` 中内层的 `{}` 表示宽度取自下一个实参。C++23 要求这个实参是标准的有符号或无符号整数类型，`bool` 和字符类型都不行（[[format.string.std]]），因为它们作宽度或精度没有有用、可移植的含义。libc++ 在两种模式下都在编译期拒绝这两行。

### 删除 `formatter<const charT[N], charT>`

¶4 C++23 删除了特化 `formatter<const charT[N], charT>`（[[format.formatter.spec]]）。`formatter` 的设计只打算用 cv 无限定的对象类型实例化，这个特化与之不符。普通的 `std::format("{}", "abc")` 不受影响，只有直接用到这个特化的代码会失效。

## 字符串库 [diff.cpp20.strings] {#diff.cpp20.strings}

### `substr` 的右值重载

```cpp
std::string s1 = "some long string that forces allocation", s2 = s1;
std::move(s1).substr(10, 5);
assert(s1 == s2);   // C++23：未指定；C++20：一定成立
std::string s3(std::move(s2), 10, 5);
assert(s1 == s2);   // 同上
```

¶1 C++23 给 `basic_string` 增加了 `substr(...) &&` 重载，以及对应的构造函数 `basic_string(basic_string&&, size_type pos, size_type n, ...)`（[[string.classes]]）。从一个即将销毁的字符串取子串时，可以直接复用它的缓冲区，省去一次分配。

代价是对 xvalue 调用 `substr` 之后，源字符串处于有效但未指定的状态，而 C++20 保证它不变。本机 libc++ 在 `-std=c++23` 下确实把 `s1` 清空了（`s1.size()` 为 0），`-std=c++20` 下仍是 39。只有对 `std::move(s)` 调用 `substr` 之后还继续使用 `s` 的代码受影响，这种代码本来就违反了移动之后不再使用的惯例。

## 容器库 [diff.cpp20.containers] {#diff.cpp20.containers}

### 关联容器的异质 `erase` 和 `extract`

```cpp error
struct B {
  auto operator<=>(const B&) const = default;
};

struct D : private B {
  void f(std::set<B, std::less<>>& s) {
    s.erase(*this);   // error: C++20 中良构
  }
};
```

¶1 比较器是透明的（有 `is_transparent` 成员，例如 `std::less<>`）时，C++23 给关联容器和无序容器增加了接受任意键类型的 `erase(K&&)` 和 `extract(K&&)` 模板重载（[[associative.reqmts]]、[[unord.req]]），删除时不必先构造一个 `key_type` 对象。

模板重载对实参是精确匹配，胜过原来需要转换的 `erase(const key_type&)`。上例中 `D` 私有继承 `B`，从 `D` 到 `B` 的转换只在 `D` 内部可以访问。C++20 中这次转换发生在调用处，合法；现在它发生在库的内部，不可访问，程序非良构。在调用处先转换（`s.erase(static_cast<const B&>(*this))`）即可。

本机 libc++ 还没有实现异质 `erase`，两种模式都接受这段代码。

## 并发支持库 [diff.cpp20.thread] {#diff.cpp20.thread}

### `barrier` 的阶段完成步骤

```cpp
auto b0 = std::barrier(1);
b0.arrive();
b0.arrive();         // C++23：由实现定义；C++20：良定义

int data = 0;
auto b1 = std::barrier(1, [&]() noexcept { data++; });
b1.arrive();
assert(data == 1);   // C++23：由实现定义；C++20：良定义
b1.arrive();         // 同上
```

¶1 `std::barrier` 让一组线程分阶段同步：每个阶段所有参与者都到达（arrive）之后，执行一次**阶段完成步骤**，也就是调用构造时给的完成函数，然后进入下一阶段（[[thread.barrier]]）。

C++20 规定完成步骤一定执行，而且在该阶段最后一个调用 `arrive` 或 `arrive_and_drop` 的线程上执行。C++23 改为：如果这一阶段没有线程调用 `wait`，是否执行完成步骤由实现定义；执行时可以在该阶段任何一个到达或等待的线程上运行。这既纠正了原来自相矛盾的措辞，也给实现留出了优化空间。

依赖完成函数恰好执行一次、在特定线程上执行，或者不调用 `wait` 也会执行的代码，行为可能改变。可移植的写法是让参与线程用 `arrive_and_wait`，或者到达后调用 `wait`。本机 libc++ 在两种模式下都在 `arrive` 时执行了完成函数，`data` 为 1。

## 小结

| 条目 | 旧代码的结局 | Clang 23 / libc++ |
|---|---|---|
| 标识符 XID、NFC | 非良构 | XID 已实现并用于所有模式；NFC 未检查 |
| `L"a" U"b"` | 非良构 | 一直拒绝 |
| 隐式移动得到 xvalue | 含义改变或非良构 | 已实现 |
| `a[1, 2]` | 非良构或含义改变 | 已实现 |
| 范围 `for` 的临时对象 | 析构变晚，无诊断 | 已实现 |
| `u8` 字面量初始化 `char` 数组 | 歧义 | 已实现，C++20 模式同样处理 |
| 继承构造函数参与 CTAD | 非良构或含义改变 | 未实现 |
| 从 `noexcept(B)` 推导 | 非良构 | 已实现，C++20 模式同样处理 |
| 比较概念的包含关系 | 歧义 | 已实现，C++20 模式同样处理 |
| 特化 `allocator_traits` | IFNDR | 无诊断 |
| `std::format` 四条 | 非良构 | 已实现，C++20 模式同样处理 |
| `substr() &&` | 源字符串状态未指定 | 已实现 |
| 异质 `erase` | 非良构 | 未实现 |
| `barrier` 完成步骤 | 由实现定义 | 行为未变 |
