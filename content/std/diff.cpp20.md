---
title: C++ 与 ISO C++ 2020 的差异
summary: Annex C.3：从 C++20 升级到 C++23 会遇到的 18 条不兼容——标识符改用 UAX #31、隐式移动把 id 变成 xvalue、a[1, 2] 改作多维下标、范围 for 延长临时对象生命周期、u8 字面量初始化 char 数组引起的歧义、继承构造函数参与 CTAD、std::format 编译期检查格式串、substr 的右值重载、barrier 语义调整等。逐条给出前后对比与 Clang 23 / libc++ 实测。
status: draft
covers: *
related: diff, diff.cpp23, diff.cpp17, class.temporary, stmt.ranged, expr.prim.id, format, string.classes
tags: 附录, 兼容性, 迁移, C++23
updated: 2026-10-18
---

[diff.cpp20] 列出 C++20 → C++23 这一步引入的不兼容（之后各步见 [[diff.cpp23]]、[[diff.cpp26]]）。C++23 的语言改动大多是在修补 C++20 新特性的边角，所以这一节的条目分散：有分词层面的（标识符字符集）、值类别层面的（隐式移动）、对象生命周期层面的（范围 `for`），还有 `std::format` 的一批以 DR 方式回溯到 C++20 的修正。

值得特别注意的是 [stmt] 那一条：范围 `for` 中临时对象的生命周期延长，是一处**静默改变**，编译器不会报错，但析构时机变了，可能引起死锁。

实测环境：Clang 23.1.3 + libc++，对比 `-std=c++20` 与 `-std=c++23`。

¶1 [diff.cpp20.general]：本小节列出与 ISO C++ 2020 的差异，是在前面各小节所列差异**之外**的部分。

## Clause [lex]：词法约定 {#diff.cpp20.lex}

### ¶1 标识符字符集改用 Unicode 的 XID 属性，并要求 NFC

**受影响小节**：[[lex.name]]

**改动**：标识符的首字符必须具有 Unicode 属性 XID_Start（或是 `_`），其余字符必须具有 XID_Continue；整个标识符必须是 Unicode 规范化形式 C（NFC）。原来 C++ 用的是一张自定的字符区间表（Annex E），收录了不少 XID 之外的字符。

**理由**：避免令人困惑的字符出现在标识符里；要求规范化保证同一个名字在不同 TU、不同编辑器里有唯一的字节序列，链接器看到的符号一致。

**影响**：部分原来合法的标识符变成非良构。例如 U+00A8（分音符 ¨）在旧表中允许，但它不是 XID_Continue：

```cpp error
int a¨;     // error: 现在非良构
```

**Clang 23 实测**：`-std=c++17`、`-std=c++20`、`-std=c++23` 下都报 `character <U+00A8> not allowed in an identifier`，Clang 对所有模式统一使用新规则。另一方面，非 NFC 的标识符（如 `e` + U+0301 组合重音）在所有模式下都被**接受**，NFC 检查没有实现。

**改写难度**：容易，改名。真实代码中极少用到这类字符。

### ¶2 拼接的字符串字面量不能有冲突的编码前缀

**受影响小节**：[[lex.string]]

**改动**：相邻字符串字面量拼接时，如果两边的 *encoding-prefix* 不同且都非空（如 `L"a" U"b"`），程序非良构。原来这是**有条件支持**（conditionally-supported）的。

**理由**：删除一个没有实现支持的有条件支持特性。

```cpp error
auto c = L"a" U"b";   // error: 原来是有条件支持；现在非良构
```

一边有前缀、一边无前缀（`L"a" "b"`）仍然合法，结果取有前缀的那一种。

**Clang 23 实测**：两种模式都报 `unsupported non-standard concatenation of string literals`。Clang 从来不支持这种拼接，所以没有可见变化。

**改写难度**：无（没有编译器支持过）。

## Clause [expr]：表达式 {#diff.cpp20.expr}

### ¶1 可移动的 id-expression 从左值变成 xvalue

**受影响小节**：[[expr.prim.id.unqual]]

**改动**：`return` 语句（以及 `co_return`、`throw`）中命名一个**可移动实体**（[[g:move-eligible]]，即局部的非 volatile 对象或右值引用）的 *id-expression*，现在直接就是 **xvalue**。C++20 的做法是"先当右值做一次重载决议，失败再当左值做一次"的两阶段规则（见 [[class.copy.elision]]）。

**理由**：简化隐式移动的规则。两阶段重载决议的规则复杂，而且有不少漏洞（例如返回右值引用形参时不移动）。

**影响**：依赖"返回的 id 是左值"的代码可能改变行为或编译失败：

```cpp
decltype(auto) f(int&& x) { return (x); }   // 现在返回 int&&；C++20 返回 int&
int& g(int&& x) { return x; }               // error: 现在非良构；C++20 良构
```

`f` 中 `(x)` 的 `decltype` 由值类别决定：xvalue 得 `int&&`。`g` 中 `x` 是 xvalue，不能绑定到 `int&`。

**Clang 23 实测**：

```text
$ clang++ -std=c++20 ...   # 静态断言 decltype(f(1)) == int&& 失败：实际是 int&
c20_move.cpp:3:15: error: static assertion failed due to requirement '__is_same(int &, int &&)'
$ clang++ -std=c++23 ...   # 断言通过，g 报错
c20_move.cpp:2:34: error: non-const lvalue reference to type 'int' cannot bind to a temporary of type 'int'
```

已实现，按模式区分。

**改写难度**：容易。`g` 改成 `return static_cast<int&>(x);`；`f` 若确实要返回左值引用，把返回类型写明。

### ¶2 下标表达式中逗号的含义改变

**受影响小节**：[[expr.sub]]

**改动**：`a[x, y]` 中的逗号不再是逗号运算符，而是分隔下标运算符的多个实参（C++20 已经弃用了下标中的顶层逗号表达式）。

**理由**：把一个已弃用的语法改作他用，支持多维下标（`std::mdspan` 的 `m[i, j]`）。

```cpp
int a[3];
int x = a[1, 2];   // C++20：等价于 a[(1, 2)]（弃用）；现在：非良构（内置下标只接受一个实参）
// 对类类型：m[1, 2] 现在调用 m.operator[](1, 2)
```

**Clang 23 实测**：

```text
$ clang++ -std=c++20 ...
c20_sub.cpp:3:11: warning: top-level comma expression in array subscript is deprecated in C++20 and unsupported in C++23 [-Wdeprecated-comma-subscript]
$ clang++ -std=c++23 ...
c20_sub.cpp:3:9: error: built-in subscript operator for type 'int[3]' expects exactly one argument
```

**改写难度**：容易。若确实需要逗号运算符，加括号：`a[(1, 2)]`。

## Clause [stmt]：语句 {#diff.cpp20.stmt}

### ¶1 范围 `for` 的初始化器中临时对象的生命周期延长到循环结束

**受影响小节**：[[stmt.ranged]]

**改动**：*for-range-initializer* 中创建的**所有**临时对象，生命周期都延长到整个循环结束（[[class.temporary]]）。C++20 中只有直接绑定到 `auto&& __range` 的那个临时对象被延长，中间的临时对象在初始化完成时就销毁了。

**理由**：提升范围 `for` 的可用性。经典陷阱 `for (auto x : make().items())` 中，`make()` 返回的临时对象在循环开始前就销毁，`items()` 返回的引用悬空，是 UB；新规则让它变得安全。

**影响**：一部分临时对象的析构函数调用**变晚了**。如果析构有副作用（解锁、关闭、计数），行为就变了：

```cpp
void f() {
  std::vector<int> v = { 42, 17, 13 };
  std::mutex m;

  for (int x : static_cast<void>(std::lock_guard<std::mutex>(m)), v) {   // C++20：锁在循环前就释放
    std::lock_guard<std::mutex> guard(m);   // C++20 中 OK；现在死锁（第一个锁还没释放）
  }
}
```

这个例子是刻意构造的，但它展示了本质：凡是初始化器里有"RAII 临时对象"的范围 `for`，作用范围都扩大到了整个循环体。

**Clang 23 实测**：用一个带打印析构函数的临时对象观察析构时机：

```cpp run title="for_temp.cpp" ok
#include <cstdio>
#include <vector>
struct G { const char* n; ~G() { std::printf("~G %s\n", n); } };
std::vector<int> make(const G&) { return {1, 2}; }
int main() {
  for (int x : make(G{"temp"})) std::printf("x=%d\n", x);
}
```

```text
-std=c++20:            -std=c++23:
~G temp                x=1
x=1                    x=2
x=2                    ~G temp
```

已实现。

**改写难度**：需人工审查。编译器不报任何诊断。搜索范围 `for` 中带锁、作用域守卫、计时器等临时对象的地方，把它们移到循环外的具名变量里，明确生命周期。

## Clause [dcl]：声明 {#diff.cpp20.dcl}

### ¶1 UTF-8 字符串字面量可以初始化 `char` / `unsigned char` 数组

**受影响小节**：[[dcl.init.string]]

**改动**：C++20 把 `u8"…"` 的类型改成 `const char8_t[N]` 之后，`char s[] = u8"x";` 变成了非良构（见 [[diff.cpp17]] [lex] ¶5）。C++23 恢复了这种初始化。

**理由**：与按以前版本编写的代码兼容。

**影响**：恢复带来一个副作用：一个 `u8` 字面量现在既能初始化 `char8_t` 数组也能初始化 `char` 数组，原来唯一的重载选择可能变成歧义：

```cpp error
struct A { char8_t s[10]; };
struct B { char s[10]; };

void f(A);
void f(B);

int main() {
  f({u8""});   // error: 歧义（C++20 中只能匹配 A）
}
```

**Clang 23 实测**：`-std=c++20` 与 `-std=c++23` 都报歧义，`char a[] = u8"abc";` 也在两种模式下都被接受。Clang 把这条作为 DR 回溯到了 C++20。

**改写难度**：容易，给实参写明类型。

## Clause [over]：重载 {#diff.cpp20.over}

### ¶1 类模板实参推导考虑继承的构造函数

**受影响小节**：[[over.match.class.deduct]]

**改动**：如果派生类模板用 *using-declaration* 继承了基类的构造函数，CTAD 也会从这些继承的构造函数生成推导指引。

**理由**：使 CTAD 与实际构造一致：既然 `D(args)` 能调用继承来的 `B(T*)`，推导时也应当考虑它。

**影响**：多出来的推导候选可能胜出，推出不同的模板实参：

```cpp error
template<typename T>
struct B { B(T); };

template<typename T>
struct D : B<T*> {
  D(T);
  using B<T*>::B;
  T m = "a";     // #1
};

D d("");   // 现在：继承的 B(T*) 胜出，T 推导为 const char，#1 处非良构
           // C++20：只有 D(T)，T 推导为 const char*，良构
```

**Clang 23 实测**：两种模式都推导出 `D<const char*>`，新规则尚未实现。

**改写难度**：容易。写出模板实参，或加一个显式推导指引。

## Clause [temp]：模板 {#diff.cpp20.temp}

### ¶1 可以从异常说明推导模板实参

**受影响小节**：[[temp.deduct.type]]

**改动**：`noexcept(B)` 中的 `B` 现在是可推导的上下文。

**理由**：方便泛型地处理抛出和不抛出的函数。

```cpp error
template<bool> struct A { };
template<bool B> void f(void (*)(A<B>) noexcept(B));
void g(A<false>) noexcept;
void h() {
  f(g);   // error: 现在非良构；C++20 良构
}
```

C++20 中只能从 `A<B>` 推出 `B = false`，参数类型是 `void(*)(A<false>)`，`noexcept` 函数指针可以隐式转换为它。现在还从 `noexcept(B)` 推出 `B = true`，两次推导冲突，推导失败。

**Clang 23 实测**：两种模式都报 `no matching function for call to 'f'`，即 Clang 在 C++20 模式下也按新规则推导。

**改写难度**：容易。显式指定模板实参：`f<false>(g)`。

## Clause [library]：库引言 {#diff.cpp20.library}

### ¶1 新头文件

**受影响小节**：[[headers]]

**改动**：新增 `<expected>`、`<flat_map>`、`<flat_set>`、`<generator>`、`<mdspan>`、`<print>`、`<spanstream>`、`<stacktrace>`、`<stdatomic.h>`、`<stdfloat>`。

**改写难度**：容易。`<print>` 和 `<expected>` 是项目里最常见的同名自定义头文件。

## Clause [concepts]：概念库 {#diff.cpp20.concepts}

### ¶1 `equality_comparable_with` 等不再直接包含 `common_reference_with`

**受影响小节**：[[cmp.concept]]、[[concept.equalitycomparable]]、[[concept.totallyordered]]

**改动**：`three_way_comparable_with`、`equality_comparable_with`、`totally_ordered_with` 中的 `common_reference_with` 要求被换成一个仅用于阐述的概念（*comparison-common-type-with*）。

**理由**：允许不可复制但可移动的类型满足这些概念（例如与 `nullptr` 比较的 `unique_ptr`）。

**影响**：概念的规范形式变了，原来"`equality_comparable_with` 包含 `common_reference_with`"的包含关系不再成立，依赖这个包含关系做重载排序的代码会变成歧义：

```cpp error
template<class T, class U>
  requires equality_comparable_with<T, U>
bool attempted_equals(const T&, const U& u);   // C++20 中被选中

template<class T, class U>
  requires common_reference_with<const remove_reference_t<T>&, const remove_reference_t<U>&>
bool attempted_equals(const T& t, const U& u); // 现在歧义；C++20 中因偏序更弱被淘汰

bool test(shared_ptr<int> p) {
  return attempted_equals(p, nullptr);         // error: 现在非良构；C++20 良构
}
```

**libc++ 实测**：两种模式都报 `call to 'attempted_equals' is ambiguous`，libc++ 把这条作为 DR 回溯到了 C++20。

**改写难度**：容易，给第二个重载补上约束或改用不依赖包含关系的写法。

## Clause [mem]：内存管理库 {#diff.cpp20.memory}

### ¶1 禁止用户特化 `allocator_traits`

**受影响小节**：[[allocator.traits.general]]

**改动**：程序不得对 `allocator_traits` 做部分特化或显式特化。

**理由**：为了能给 `allocator_traits` 增加 `allocate_at_least` 以及将来的其他成员。用户特化会缺少这些新成员。

**影响**：特化了 `allocator_traits` 的 C++20 代码变成 **IFNDR**——编译器不必诊断，所以升级后代码可能照常编译，只是不再有保证。

**改写难度**：中等，需人工审查。把定制放回分配器类型本身（`allocator_traits` 会读取分配器的同名成员）。

## Clause [utilities]：通用工具库 {#diff.cpp20.utilities}

这一节的四条都是 `std::format` 的修正，委员会把它们作为针对 C++20 的 DR 处理，所以主流库在 `-std=c++20` 下就已经是新行为。

### ¶1 格式串在编译期检查；删除 `format_args_t`

**受影响小节**：[[format]]

**改动**：`format`、`format_to`、`vformat_to`、`format_to_n`、`formatted_size` 的签名改为接受 `format_string<Args...>`，其构造函数是 `consteval` 的，在编译期解析并检查格式串；删除 `format_args_t`。

**理由**：通过编译期检查提高安全性，避免不必要的模板实例化。

```cpp error
auto s = std::format("{:d}", "I am not a number");   // error: 现在编译期报错；原来运行时抛 format_error
```

**libc++ 实测**：两种模式都在编译期报错：

```text
error: call to consteval function 'std::basic_format_string<char, const char (&)[18]>::basic_format_string<char[5]>' is not a constant expression
note: non-constexpr function '__throw_format_error' cannot be used in a constant expression
```

**改写难度**：容易，修正格式串。运行期才确定的格式串改用 `std::vformat(fmt, std::make_format_args(args...))` 或 `std::runtime_format`（C++26）。

### ¶2 格式化函数改为按转发引用接收实参：位域不能再直接传入

**受影响小节**：[[format]]

**改动**：`format` 等函数的实参从 `const Args&...` 改为 `Args&&...`。

**理由**：支持格式化那些"const 时不能迭代"且不可复制的视图（例如 `filter_view`）。

**影响**：非 const 左值引用不能绑定到位域，位域作为实参变成非良构：

```cpp error
struct tiny { int bit: 1; };
auto t = tiny();
std::format("{}", t.bit);   // error: 现在非良构；原来返回 "0"
```

**libc++ 实测**：两种模式都报 `non-const reference cannot bind to bit-field 'bit'`。

**改写难度**：容易，先复制出来：`std::format("{}", int(t.bit))` 或 `+t.bit`。

### ¶3 限制用作动态宽度/精度的实参类型

**受影响小节**：[[format.string.std]]

**改动**：`{:{}}` 中作为宽度或精度的实参必须是标准有符号或无符号整数类型，不能是 `bool` 或字符类型。

```cpp error
std::format("{:*^{}}", "", true);   // error: 现在非良构；原来返回 "*"
std::format("{:*^{}}", "", '1');    // error: 现在非良构；原来返回实现定义个数的 '*'
```

**libc++ 实测**：`true` 作宽度在两种模式下都于编译期被拒绝。

**改写难度**：容易。

### ¶4 删除 `formatter<const charT[N], charT>` 特化

**受影响小节**：[[format.formatter.spec]]

**理由**：`formatter` 的设计意图是只用 cv 无限定的对象类型实例化，这个特化与之不符。

**影响**：显式实例化或直接使用了该特化的代码非良构。正常的 `std::format("{}", "abc")` 不受影响（字符数组走 `formatter<charT[N], charT>` 或退化为指针）。

**改写难度**：容易。

## Clause [strings]：字符串库 {#diff.cpp20.strings}

### ¶1 `substr` 和对应构造函数增加右值重载

**受影响小节**：[[string.classes]]

**改动**：增加 `basic_string::substr(…) &&` 以及 `basic_string(basic_string&&, size_type pos, size_type n, …)` 构造函数。

**理由**：提高对右值操作的效率：从一个即将销毁的字符串取子串时，可以直接复用它的缓冲区。

**影响**：对一个 xvalue 调用 `substr`，原来保证源字符串不变，现在源字符串处于**有效但未指定**的状态：

```cpp
std::string s1 = "some long string that forces allocation", s2 = s1;
std::move(s1).substr(10, 5);
assert(s1 == s2);   // 现在：未指定；C++20：保证成立
std::string s3(std::move(s2), 10, 5);
assert(s1 == s2);   // 同上
```

**libc++ 实测**：

```text
-std=c++20:  s1 == s2: 1, s1.size()=39
-std=c++23:  s1 == s2: 0, s1.size()=0
```

已实现：C++23 模式下 libc++ 确实把 `s1` 的缓冲区"偷"走了。

**改写难度**：需人工审查。只有"对 `std::move(s)` 调用 `substr` 之后还使用 `s`"的代码受影响，这种代码本来就违反"移动后不再使用"的惯例。

## Clause [containers]：容器库 {#diff.cpp20.containers}

### ¶1 关联容器的异质 `extract` / `erase` 重载

**受影响小节**：[[associative.reqmts]] 与 [[unord.req]]

**改动**：比较器透明（有 `is_transparent`）时，`erase(K&&)` 和 `extract(K&&)` 增加接受任意键类型的模板重载。

**理由**：提高删除效率，不必先构造一个 `key_type` 对象。

**影响**：模板重载对实参类型是精确匹配，会胜过原来需要转换的 `erase(const key_type&)`。如果实参到 `key_type` 的转换在调用处不可访问（例如私有基类），原来在类内部可以完成的转换，现在发生在库的内部，变成非良构：

```cpp error
struct B {
  auto operator<=>(const B&) const = default;
};

struct D : private B {
  void f(std::set<B, std::less<>>& s) {
    s.erase(*this);   // error: 现在非良构；C++20 良构
  }
};
```

**libc++ 实测**：两种模式都接受，异质 `erase` 尚未实现。

**改写难度**：容易。在类内部先转换：`s.erase(static_cast<const B&>(*this))`。

## Clause [thread]：并发支持库 {#diff.cpp20.thread}

### ¶1 `barrier` 的阶段完成步骤

**受影响小节**：[[thread.barrier]]

**改动**：如果在某一阶段中**没有**线程调用 `wait`，阶段完成步骤是否执行由实现定义；完成步骤可以在该阶段中任何一个 arrive 或 wait 的线程上执行。C++20 规定完成步骤在该阶段最后一个调用 `arrive` / `arrive_and_drop` 的线程上执行，且必定执行。

**理由**：纠正自相矛盾的措辞，并给实现更多性能上的灵活性。

**影响**：依赖"完成函数恰好执行一次"、"在特定线程执行"或"不调用 `wait` 也会执行"的代码，行为可能改变：

```cpp
auto b0 = std::barrier(1);
b0.arrive();
b0.arrive();            // 现在：实现定义；C++20：良定义

int data = 0;
auto b1 = std::barrier(1, [&]() noexcept { data++; });
b1.arrive();
assert(data == 1);      // 现在：实现定义；C++20：良定义
```

**libc++ 实测**：两种模式下 `b1.arrive()` 后 `data == 1`，即 libc++ 仍在最后一个 arrive 的线程上执行完成步骤。

**改写难度**：需人工审查。可移植的写法是每个阶段都让参与线程调用 `wait`（或用 `arrive_and_wait`）。

## 小结

| 条目 | 类型 | Clang 23 / libc++ |
|---|---|---|
| 标识符 XID / NFC | 非良构 | XID 已实现并回溯；NFC 未检查 |
| `L"a" U"b"` | 非良构 | 一直拒绝 |
| 隐式移动 → xvalue | 改变含义 / 非良构 | 已实现 |
| `a[1, 2]` | 非良构 / 改变含义 | 已实现 |
| 范围 `for` 临时对象 | **静默改变** | 已实现 |
| `u8` 初始化 `char` 数组 | 歧义 | 已实现并回溯 |
| 继承构造函数 CTAD | 非良构 / 改变含义 | 未实现 |
| 从 `noexcept(B)` 推导 | 非良构 | 已实现并回溯 |
| `equality_comparable_with` 包含关系 | 歧义 | 已实现并回溯 |
| 特化 `allocator_traits` | IFNDR | — |
| `std::format` 四条 | 非良构 | 已实现并回溯 |
| `substr() &&` | 改变状态 | 已实现 |
| 异质 `erase` | 非良构 | 未实现 |
| `barrier` 完成步骤 | 实现定义 | 行为未变 |
