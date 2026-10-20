---
title: 读懂编译错误
summary: 一条 Clang 诊断由哪几部分组成，候选列表和实例化链怎样读，最常见也最费解的十几类编译错误和链接错误各自对应哪条语言规则、该怎样修，以及控制诊断输出的编译选项。
group: 调试与诊断
status: draft
order: 150
since: c++98
related: intro.compliance.general, over.match.viable, over.match.best.general, temp.inst, temp.constr.atomic, temp.res.general, temp.names, dcl.init.list, dcl.init.ref, dcl.ambig.res, expr.prim.lambda.capture, basic.def.odr, unique.ptr.dltr.dflt, unord.hash, topics/overload-resolution-walkthrough, topics/two-phase-lookup, topics/concepts, topics/initialization, topics/lambdas, toolchain/linking-and-symbols, toolchain/name-mangling, toolchain/object-layout-and-vtables, toolchain/debugging, toolchain/static-analysis
tags: 工具链, 诊断, 编译错误, 链接错误, 重载决议, 模板, 概念
updated: 2026-10-19
---

!!! tldr
    - 一条诊断由一个 `error` 或 `warning` 和跟在它后面的若干 `note` 组成。note 不是新问题，而是在解释它前面那个错误：为什么某个候选不可行、错误是从哪次模板实例化里冒出来的。
    - 报在标准库头文件深处的错误，先往下找第一条位置在自己文件里的 `in instantiation of ... requested here`，那一行就是你写的调用；再看 `static_assert` 的消息和 `substitution failure` 后面的原因，它们通常直接说出了真正缺什么。
    - 只修第一个错误，然后重新编译。后面的错误常常是第一个错误的连锁反应。
    - 链接器报的 `Undefined symbols` 和 `duplicate symbol` 对应 ODR 中不要求诊断的规则。读法是把报出的函数签名和自己定义的签名逐字比较，必要时用 `llvm-nm` 和 `c++filt` 看真实的符号名。
    - `-ferror-limit`、`-ftemplate-backtrace-limit`、`-fdiagnostics-show-template-tree` 控制输出的多少和形式；看不懂时换一个编译器（Compiler Explorer）再编译一次，往往能得到另一种更直接的说法。

标准对编译器报错的要求只有一句话：程序违反了一条**可诊断规则**（[[g:diagnosable-rule|diagnosable rule]]，即没有标注不要求诊断、也不属于未定义行为的语法和语义规则），实现就必须给出至少一条诊断消息（[[intro.compliance.general#2.3]]）。消息写成什么样、给几条、附带多少解释，全由实现决定。所以读错误信息是在读某个编译器的输出格式，而不是在读标准。

不过每条消息背后都有一条具体的规则。认出规则，就知道该去改哪里。

!!! note "实验环境"
    以下输出全部来自本机（Apple M2 Pro，macOS）上的 Homebrew Clang 23.1.3 和 libc++，命令是 `clang++ -std=c++2c -Wall -Wextra -pedantic`，链接器用 `--ld-path=/usr/bin/ld` 指定系统链接器 `ld-1266.8`。libc++ 头文件的长路径 `/opt/homebrew/Cellar/llvm/23.1.3_2/bin/../include/c++/v1/` 缩写成 `.../c++/v1/`，其余文字未改，较长的输出删去了中间部分并注明。本机没有安装 GCC（`/usr/bin/g++` 实际是 Apple clang 21），也没有 MSVC、GNU ld 和 lld，所以不引用它们的原文。

## 一条诊断的结构

```cpp title="nomatch.cpp" run error
#include <string>
void greet(const std::string& name, int times);
void greet(const char* name);
int main() {
  greet(42);
}
```

```text
nomatch.cpp:5:3: error: no matching function for call to 'greet'
    5 |   greet(42);
      |   ^~~~~
nomatch.cpp:3:6: note: candidate function not viable: no known conversion from 'int' to 'const char *' for 1st argument
    3 | void greet(const char* name);
      |      ^     ~~~~~~~~~~~~~~~~
nomatch.cpp:2:6: note: candidate function not viable: requires 2 arguments, but 1 was provided
    2 | void greet(const std::string& name, int times);
      |      ^     ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1 error generated.
```

每一条都以 `文件:行:列: 级别: 消息` 开头，下面是源代码行和标记。`^` 指向诊断的位置，`~~~` 标出相关的范围。上例的 `error` 指向调用处，两条 `note` 分别指向两个候选的声明，并用 `~~~` 标出出问题的形参。

| 级别 | 含义 |
|---|---|
| `error` | 程序非良构，或者实现无法继续；不会生成目标文件 |
| `warning` | 程序良构（或者编译器不确定），但很可能不是你想要的；末尾的 `[-Wxxx]` 是控制它的选项 |
| `note` | 附属于前一条 `error`/`warning` 的说明，本身不是问题 |
| `fatal error` | 编译立即停止，例如找不到头文件，或者错误数达到上限 |

错误后面也可能带 `[-Wxxx]`，例如下文的 `[-Wc++11-narrowing]`。这表示这条错误由一个警告选项控制，可以被降级甚至关掉。

### 候选列表

`no matching function` 后面的 note 是重载决议的记录。重载决议先收集**候选函数**（[[g:candidate-function|candidate function]]），再从中筛出**可行函数**（[[g:viable-function|viable function]]）：形参个数要对得上（[[over.match.viable#2]]），满足约束（[[over.match.viable#3]]），每个实参都要能隐式转换到对应形参（[[over.match.viable#4]]）。Clang 为每个被淘汰的候选写一条 `candidate ... not viable`，说明它卡在哪一步：

| note 的说法 | 卡在哪一步 |
|---|---|
| `requires 2 arguments, but 1 was provided` | 个数不符，[[over.match.viable#2]] |
| `no known conversion from 'X' to 'Y' for Nth argument` | 第 N 个实参没有隐式转换序列，[[over.match.viable#4]] |
| `expects an lvalue for Nth argument` | 非 const 左值引用形参遇到右值，见下文 |
| `candidate template ignored: could not match ...` | 模板实参推导失败 |
| `candidate template ignored: substitution failure [...]: 原因` | 推导成功，代入时失败（SFINAE） |
| `candidate template ignored: constraints not satisfied` | 约束不满足，后面跟 `because` 链 |
| `explicit constructor is not a candidate` | 拷贝初始化不考虑 explicit 构造函数 |

可行函数一个都没有，就是 `no matching function`；有多个但分不出最好的，就是 `ambiguous`（[[over.match.best.general#3]]）。规则本身见 [[topics/overload-resolution-walkthrough]]。

### 实例化链

错误出现在模板里时，Clang 先报出真正出错的那一行（往往在库的头文件里），再用一串 note 说明这个模板是怎么被实例化到这里的。下面是对 `std::list` 调用 `std::sort` 的第一个错误（共 4 个错误、114 行输出）：

```cpp title="sortlist.cpp" run
#include <algorithm>
#include <list>
int main() {
  std::list<int> xs{3, 1, 2};
  std::sort(xs.begin(), xs.end());
}
```

```text
In file included from sortlist.cpp:1:
In file included from .../c++/v1/algorithm:1928:
.../c++/v1/__algorithm/make_heap.h:37:31: error: invalid operands to binary expression ('std::__list_iterator<int, void *>' and 'std::__list_iterator<int, void *>')
   37 |   const __diff_t __n = __last - __first;
      |                        ~~~~~~ ^ ~~~~~~~
.../c++/v1/__algorithm/partial_sort.h:41:8: note: in instantiation of function template specialization 'std::__make_heap<std::_ClassicAlgPolicy, std::__less<void, void> &, std::__list_iterator<int, void *>>' requested here
.../c++/v1/__algorithm/partial_sort.h:65:12: note: in instantiation of function template specialization 'std::__partial_sort_impl<...>' requested here
.../c++/v1/__algorithm/sort.h:936:10: note: in instantiation of function template specialization 'std::__partial_sort<...>' requested here
.../c++/v1/__algorithm/sort.h:947:8: note: in instantiation of function template specialization 'std::__sort_impl<...>' requested here
.../c++/v1/__algorithm/sort.h:953:8: note: in instantiation of function template specialization 'std::sort<std::__list_iterator<int, void *>, std::__less<void, void>>' requested here
sortlist.cpp:5:8: note: in instantiation of function template specialization 'std::sort<std::__list_iterator<int, void *>>' requested here
    5 |   std::sort(xs.begin(), xs.end());
      |        ^
.../c++/v1/__iterator/reverse_iterator.h:279:36: note: candidate template ignored: could not match 'reverse_iterator' against 'std::__list_iterator'
.../c++/v1/__iterator/move_iterator.h:306:36: note: candidate template ignored: could not match 'move_iterator' against 'std::__list_iterator'
```

（中间几条 note 的源代码行和模板实参已删去。）

按这个顺序读：

1. 开头的 `In file included from` 只说明错误所在的文件是怎么被包含进来的，可以跳过。
2. `error` 那一行说的是现象：两个 `__list_iterator` 不能相减。
3. `in instantiation of` 从最内层往外排列，**最后一条位置在你自己文件里的**就是触发实例化的那行代码（`sortlist.cpp:5:8`）。中间的 `__make_heap`、`__partial_sort_impl` 是库的实现细节，不用看懂。
4. 实例化链之后的 `candidate template ignored` 属于同一个错误，它们列出了 `operator-` 的其他重载为什么不适用。这里的两条都与问题无关。

这条链对应的是标准中的**隐式实例化**（[[g:implicit-instantiation|implicit instantiation]]，[[temp.inst#5]]）：一个函数模板特化被使用时才实例化它的定义，而实例化内部又会使用别的模板。每条 note 是一层这样的使用。Clang 默认最多显示 10 层，超出的部分折叠成一条 `(skipping N contexts in backtrace; use -ftemplate-backtrace-limit=0 to see all)`。

本机对一个 30 层递归的类模板实验，输出 10 条 `in instantiation of` 和一条 `skipping 20 contexts`。

GCC 用另一套措辞表达同一条链。本机没有 GCC，需要对照时在 Compiler Explorer 上把同一段代码交给两个编译器（代码块右上角的 godbolt 按钮默认同时打开 Clang 和 GCC）。

## 标准库深处的模板错误

这一类错误的共同点是：你违反了标准库对模板实参的要求，但这个要求没有写成能在调用处检查的约束，于是错误要等到库的实现内部用到某个操作时才暴露。

标准对这类违反并不都要求诊断。例如 `std::sort` 的模板形参名为 `RandomAccessIterator`，[[algorithms.requirements#4.7]] 只说实参应当满足 *Cpp17RandomAccessIterator*。下面两个例子因此不标判定；实践中实现都会在实例化时报错。

### `std::sort` 用在 `std::list` 上

上一节的输出已经说明了问题：`std::sort` 要做迭代器相减，`std::list` 的迭代器是双向迭代器，不支持 `-`。修法是用 `list` 自己的成员函数 `xs.sort()`，或者先复制到 `vector`。

对比 C++20 的 `std::ranges::sort`。它的要求写成了概念约束，错误停在调用处，只有一个错误、一条 `because` 链：

```cpp title="rsort.cpp" run error
#include <algorithm>
#include <list>
int main() {
  std::list<int> xs{3, 1, 2};
  std::ranges::sort(xs);
}
```

```text
rsort.cpp:5:3: error: no matching function for call to object of type 'const __sort'
    5 |   std::ranges::sort(xs);
      |   ^~~~~~~~~~~~~~~~~
.../c++/v1/__algorithm/ranges_sort.h:64:3: note: candidate template ignored: constraints not satisfied [with _Range = std::list<int> &, _Comp = ranges::less, _Proj = identity]
.../c++/v1/__algorithm/ranges_sort.h:61:13: note: because 'std::list<int> &' does not satisfy 'random_access_range'
.../c++/v1/__ranges/concepts.h:116:59: note: because 'iterator_t<std::list<int, std::allocator<int>> &>' (aka '__list_iterator<int, void *>') does not satisfy 'random_access_iterator'
.../c++/v1/__iterator/concepts.h:218:36: note: because 'derived_from<_ITER_CONCEPT<std::__list_iterator<int, void *> >, random_access_iterator_tag>' evaluated to false
.../c++/v1/__concepts/derived_from.h:27:24: note: because 'is_base_of_v<std::random_access_iterator_tag, std::bidirectional_iterator_tag>' evaluated to false
.../c++/v1/__algorithm/ranges_sort.h:57:3: note: candidate function template not viable: requires at least 2 arguments, but 1 was provided
1 error generated.
```

（源代码行已删去。）`[with ...]` 给出推导出的模板实参；`(aka ...)` 在别名后面给出它代表的真实类型。

### `std::map` 的键没有 `operator<`

```cpp title="mapkey.cpp" run
#include <map>
struct Point { int x, y; };
int main() {
  std::map<Point, int> m;
  m[{1, 2}] = 3;
}
```

```text
.../c++/v1/__utility/lazy_synth_three_way_comparator.h:45:21: error: no matching function for call to object of type 'const std::less<void>'
   45 |     bool __result = __comp_(__lhs_, __rhs_);
      |                     ^~~~~~~
.../c++/v1/__tree:1962:20: note: in instantiation of member function 'std::__lazy_compare_result<std::less<void>, Point, Point>::__less' requested here
（中间 3 条 note 省略）
mapkey.cpp:5:4: note: in instantiation of member function 'std::map<Point, int>::operator[]' requested here
    5 |   m[{1, 2}] = 3;
      |    ^
.../c++/v1/__functional/operations.h:374:60: note: candidate template ignored: substitution failure [with _T1 = const Point &, _T2 = const Point &]: invalid operands to binary expression ('const Point' and 'const Point')
```

错误行里出现的是 `std::less<void>`，而你写的是 `std::less<Point>`（`map` 的默认比较器）。这是 libc++ 内部的替换，读的时候不必追究。真正的原因在最后一条 note 的 `substitution failure` 后面：两个 `const Point` 之间没有 `<`。

`map` 要求比较器给出严格弱序（[[associative.reqmts.general]]）。修法是给 `Point` 一个比较运算符，例如 `auto operator<=>(const Point&) const = default;`，或者给 `map` 传一个自定义比较器。

### `std::unordered_map` 的键没有哈希

```cpp title="umap.cpp" run error
#include <unordered_map>
struct Point {
  int x, y;
  bool operator==(const Point&) const = default;
};
int main() {
  std::unordered_map<Point, int> m;
  m[{1, 2}] = 3;
}
```

```text
.../c++/v1/unordered_map:653:9: error: call to implicitly-deleted default constructor of 'std::hash<Point>'
umap.cpp:7:34: note: in instantiation of member function 'std::unordered_map<Point, int>::unordered_map' requested here
.../c++/v1/__functional/hash.h:438:15: note: default constructor of 'hash<Point>' is implicitly deleted because base class '__hash_impl<Point>' has a deleted default constructor
.../c++/v1/__hash_table:592:17: error: static assertion failed due to requirement 'std::integral_constant<bool, false>::value': the specified hash does not meet the Hash requirements
.../c++/v1/unordered_map:658:75: error: type 'const std::hash<Point>' does not provide a call operator
（共 5 个错误、79 行，此处只保留各错误的首行和关键 note）
```

第一个错误说 `std::hash<Point>` 不能默认构造，乍看与哈希无关。原因是标准规定，没有为某个类型提供 `hash` 特化时，`hash<Key>` 是一个**被禁用的特化**：它存在，但不能默认构造、拷贝或移动，也不是函数对象类型（[[unord.hash#4]]）。该段的注释说明，把它当作哈希函数使用是非良构的。

第二个错误里的 `static_assert` 消息才是直接的说明。库作者用 `static_assert` 把要求翻译成人话，这类消息值得优先找。修法是为 `Point` 特化 `std::hash`：

```cpp run ok
#include <cstddef>
#include <functional>
#include <unordered_map>
struct Point {
  int x, y;
  bool operator==(const Point&) const = default;
};
template <>
struct std::hash<Point> {
  std::size_t operator()(const Point& p) const noexcept {
    std::size_t h = std::hash<int>{}(p.x);
    return h ^ (std::hash<int>{}(p.y) + 0x9e3779b9 + (h << 6) + (h >> 2));
  }
};
int main() {
  std::unordered_map<Point, int> m;
  m[{1, 2}] = 3;
}
```

## 概念：`because` 链

```cpp title="concept.cpp" run error
#include <concepts>
#include <string>
template <class T>
concept Shape = requires(const T& s) {
  { s.area() } -> std::convertible_to<double>;
  s.name();
};
struct Square {
  double side;
  double area() const { return side * side; }
};
void print(const Shape auto& s);
int main() {
  print(Square{2.0});
}
```

```text
concept.cpp:14:3: error: no matching function for call to 'print'
   14 |   print(Square{2.0});
      |   ^~~~~
concept.cpp:12:6: note: candidate template ignored: constraints not satisfied [with s:auto = Square]
   12 | void print(const Shape auto& s);
      |      ^
concept.cpp:12:18: note: because 'Square' does not satisfy 'Shape'
   12 | void print(const Shape auto& s);
      |                  ^
concept.cpp:6:5: note: because 's.name()' would be invalid: no member named 'name' in 'Square'
    6 |   s.name();
      |     ^
1 error generated.
```

约束不满足的候选不是可行函数（[[over.match.viable#3]]），所以外层仍然是 `no matching function`。`because` 链逐层展开概念的定义，直到找到那个不满足的**原子约束**（[[g:atomic-constraint|atomic constraint]]）。原子约束的判断方法是把模板实参代入表达式，代入失败就是不满足（[[temp.constr.atomic#3]]）。链的最后一条就是答案：`Square` 没有 `name()`。

`rsort.cpp` 的链更长，最后一条落在 `is_base_of_v<random_access_iterator_tag, bidirectional_iterator_tag>`，意思同样是 list 的迭代器只是双向迭代器。概念本身见 [[topics/concepts]]。

## 重载决议的其他失败

### 调用有歧义

```cpp title="ambig.cpp" run error
void f(long);
void f(double);
int main() {
  f(42);
}
```

```text
ambig.cpp:4:3: error: call to 'f' is ambiguous
    4 |   f(42);
      |   ^
ambig.cpp:1:6: note: candidate function
    1 | void f(long);
      |      ^
ambig.cpp:2:6: note: candidate function
    2 | void f(double);
      |      ^
1 error generated.
```

两个候选都可行，note 只列出它们，不说为什么分不出高下。原因要自己对照规则：`int` 到 `long` 是整型转换，`int` 到 `double` 是浮点-整型转换，在 [[over.ics.scs]] 的表里都属于 Conversion 等级，谁也不比谁好，于是没有唯一的最佳可行函数（[[over.match.best.general#3]]）。修法是让实参类型精确匹配其中一个：`f(42L)`，或者显式转换。

### `no viable conversion`

```cpp title="noconv.cpp" run error
#include <optional>
#include <string>
#include <string_view>
struct Meters { explicit Meters(double); };
int main() {
  std::string s = std::string_view("abc");
  std::optional<int> o = 3;
  int n = o;
  Meters m = 2.0;
}
```

```text
noconv.cpp:6:15: error: no viable conversion from 'std::string_view' (aka 'basic_string_view<char>') to 'std::string' (aka 'basic_string<char>')
（5 条 candidate constructor not viable 省略）
.../c++/v1/string:1091:42: note: explicit constructor is not a candidate
noconv.cpp:8:7: error: no viable conversion from 'std::optional<int>' to 'int'
noconv.cpp:9:10: error: no viable conversion from 'double' to 'Meters'
noconv.cpp:4:8: note: candidate constructor (the implicit copy constructor) not viable: no known conversion from 'double' to 'const Meters &' for 1st argument
noconv.cpp:4:8: note: candidate constructor (the implicit move constructor) not viable: no known conversion from 'double' to 'Meters &&' for 1st argument
noconv.cpp:4:26: note: explicit constructor is not a candidate
3 errors generated.
```

这三处都是 `T x = 表达式;` 形式的拷贝初始化。用构造函数完成这种转换时，只有非 explicit 构造函数是候选（[[over.match.copy#1.1]]），explicit 构造函数只在直接初始化和显式转换中使用（[[class.conv.ctor#2]]）。所以关键的 note 是 `explicit constructor is not a candidate`。`string` 从 `string_view` 构造、`Meters` 从 `double` 构造都是 explicit 的，改成直接初始化即可：`std::string s{sv};`、`Meters m{2.0};`。

`optional<int>` 到 `int` 根本没有转换函数，Clang 也就没有 note 可给。这里要明确写出取值的方式，例如 `o.value()` 或 `*o`。

### 非 const 左值引用绑定临时对象

```cpp title="tempref.cpp" run error
#include <string>
void append(std::string& out, const char* s);
std::string make();
int main() {
  append(make(), "x");
  std::string& r = std::string("tmp");
}
```

```text
tempref.cpp:5:3: error: no matching function for call to 'append'
    5 |   append(make(), "x");
      |   ^~~~~~
tempref.cpp:2:6: note: candidate function not viable: expects an lvalue for 1st argument
    2 | void append(std::string& out, const char* s);
      |      ^      ~~~~~~~~~~~~~~~~
tempref.cpp:6:16: error: non-const lvalue reference to type 'basic_string<...>' cannot bind to a temporary of type 'basic_string<...>'
    6 |   std::string& r = std::string("tmp");
      |                ^   ~~~~~~~~~~~~~~~~~~
2 errors generated.
```

[[dcl.init.ref#5.2]] 规定，初始化表达式不是合适的左值时，引用必须是 const（且非 volatile）左值引用或右值引用，否则非良构。第二条消息里的 `basic_string<...>` 是 Clang 把两边相同的模板实参省略掉了，见下文的 `-fno-elide-type`。

同一条规则在库里会换一副面孔出现。`std::thread` 把实参复制一份，再以右值传给线程函数，于是形参为 `std::string&` 的函数无法调用：

```cpp title="thread_ref.cpp" run error
#include <string>
#include <thread>
void work(std::string& out);
int main() {
  std::string s;
  std::thread t(work, s);
  t.join();
}
```

```text
.../c++/v1/__thread/thread.h:221:19: error: static assertion failed due to requirement '__is_invocable_v<void (*)(std::string &), std::string>': 
thread_ref.cpp:6:15: note: in instantiation of function template specialization 'std::thread::thread<void (&)(std::string &), std::string &, 0>' requested here
.../c++/v1/__thread/thread.h:170:3: error: no matching function for call to '__invoke'
（其余省略，共 2 个错误）
```

`static_assert` 的条件读作：能否用一个 `std::string` 右值调用 `void(*)(std::string&)`。不能，因为右值绑不到非 const 左值引用。修法是 `std::thread t(work, std::ref(s));`。值类别见 [[topics/value-categories]]。

## 不完整类型

```cpp title="incomplete.cpp" run error
struct Widget;
Widget* make();
int main() {
  Widget* w = make();
  return w->size;
}
```

```text
incomplete.cpp:5:11: error: member access into incomplete type 'Widget'
    5 |   return w->size;
      |           ^
incomplete.cpp:1:8: note: forward declaration of 'Widget'
    1 | struct Widget;
      |        ^
1 error generated.
```

只声明未定义的类是**不完整类型**（[[g:incomplete-type|incomplete type]]，[[basic.types.general#3]]）。指向它的指针可以随意传递，但访问成员要求类是完整的（[[expr.ref#5]]）。note 指出的是前置声明的位置；修法是在这个 TU 里包含定义 `Widget` 的头文件。

更难认的是 `unique_ptr` 成员加前置声明：

```cpp title="incomplete2.cpp" run error
#include <memory>
struct Impl;
struct Handle {
  std::unique_ptr<Impl> p;
};
int main() {
  Handle h;
}
```

```text
.../c++/v1/__memory/unique_ptr.h:72:19: error: invalid application of 'sizeof' to an incomplete type 'Impl'
   72 |     static_assert(sizeof(_Tp) >= 0, "cannot delete an incomplete type");
      |                   ^~~~~~~~~~~
.../c++/v1/__memory/unique_ptr.h:264:7: note: in instantiation of member function 'std::default_delete<Impl>::operator()' requested here
.../c++/v1/__memory/unique_ptr.h:229:71: note: in instantiation of member function 'std::unique_ptr<Impl>::reset' requested here
incomplete2.cpp:3:8: note: in instantiation of member function 'std::unique_ptr<Impl>::~unique_ptr' requested here
    3 | struct Handle {
      |        ^
incomplete2.cpp:7:10: note: in implicit default constructor for 'Handle' first required here
    7 |   Handle h;
      |          ^
incomplete2.cpp:2:8: note: forward declaration of 'Impl'
1 error generated.
```

`unique_ptr<T>` 允许 `T` 不完整，但默认删除器 `default_delete<T>::operator()` 要求 `T` 完整（标准用 *Mandates* 写这条要求，违反即非良构，[[unique.ptr.dltr.dflt#3]]）。链的最后两条说明了是谁需要删除：`Handle` 隐式定义的默认构造函数。构造函数会潜在调用每个成员的析构函数（[[class.base.init#14]]），以便在构造中途抛出异常时清理，而这些隐式成员都内联在 `Handle` 的定义处生成，此时 `Impl` 还不完整。

修法是 Pimpl 的标准写法：在头文件里只声明 `Handle` 的构造函数和析构函数，到 `.cpp` 中 `Impl` 定义之后再定义它们（`Handle::~Handle() = default;`）。见 [[patterns/pimpl]]。

## 使用被删除的函数

```cpp title="deleted.cpp" run error
#include <memory>
int main() {
  auto p = std::make_unique<int>(1);
  auto q = p;
}
```

```text
deleted.cpp:4:8: error: call to implicitly-deleted copy constructor of 'unique_ptr<int>'
    4 |   auto q = p;
      |        ^   ~
.../c++/v1/__memory/unique_ptr.h:181:55: note: copy constructor is implicitly deleted because 'unique_ptr<int>' has a user-declared move constructor
1 error generated.
```

使用被删除的函数是非良构的（[[dcl.fct.def.delete#2]]）。note 给出的理由是一条通用规则：类声明了移动构造函数，隐式声明的拷贝构造函数就定义为删除的（[[class.copy.ctor#6]]）。标准的 `unique_ptr` 概要其实直接写了 `unique_ptr(const unique_ptr&) = delete;`（[[unique.ptr.single.general]]），libc++ 省略了这行声明，靠隐式删除达到同样的效果，所以消息里说的是 implicitly-deleted。修法是 `auto q = std::move(p);`，所有权的含义见 [[topics/ownership-and-smart-pointers]]。

把这个错误藏进容器里，就是一条很长的链：

```text
（deleted2.cpp 第 6 行：std::vector<std::unique_ptr<int>> w = v;）
.../c++/v1/__memory/allocator_traits.h:362:5: error: no matching function for call to '__construct_at'
（5 条 in instantiation of 省略）
deleted2.cpp:6:41: note: in instantiation of member function 'std::vector<std::unique_ptr<int>>::vector' requested here
.../c++/v1/__memory/construct_at.h:43:58: note: candidate template ignored: substitution failure [with _Tp = std::unique_ptr<int>, _Args = <const std::unique_ptr<int> &>]: call to implicitly-deleted copy constructor of 'std::unique_ptr<int>'
```

错误行说 `__construct_at` 没有匹配，看不出原因。原因在最后一条 note 的 `substitution failure` 之后：拷贝 `vector` 需要拷贝元素，而 `unique_ptr` 不可拷贝。

## 依赖名缺少 `typename` 或 `template`

```cpp title="depname.cpp" run error
template <class C>
void first(const C& c) {
  C::const_iterator it = c.begin();
}
template <class T>
struct Box {
  template <class U> U get() const;
};
template <class T>
int peek(const Box<T>& b) {
  return b.get<int>();
}
```

```text
depname.cpp:3:3: error: missing 'typename' prior to dependent type name 'C::const_iterator'
    3 |   C::const_iterator it = c.begin();
      |   ^~~~~~~~~~~~~~~~~
      |   typename 
depname.cpp:11:12: error: use 'template' keyword to treat 'get' as a dependent template name
   11 |   return b.get<int>();
      |            ^
      |            template 
2 errors generated.
```

源代码行下面多出的一行是**修正建议**（fix-it）：Clang 指出在哪里插入什么。

模板定义在实例化之前就要能解析，而 `C::const_iterator` 依赖于 `C`，编译器在定义处不知道它是类型还是值。只有在**仅限类型的语境**（type-only context，例如函数返回类型、`using` 别名的右边）中，这种名字才自动当作类型（[[temp.res.general#5]]）；函数体内的声明语句不属于这种语境，必须写 `typename`。同理，`b.get` 依赖于 `T`，后面的 `<` 只有在 `get` 前写了 `template` 时才当作模板实参列表的开始（[[temp.names#7]]），否则按小于号解析。修正后是 `typename C::const_iterator it` 和 `b.template get<int>()`。为什么要分两阶段查找见 [[topics/two-phase-lookup]]。

## 花括号里的收窄

```cpp title="narrow.cpp" run error
#include <vector>
int main() {
  double d = 3.7;
  int a{d};
  long long big = 1LL << 40;
  std::vector<int> v{1, 2, big};
  unsigned u{-1};
}
```

```text
narrow.cpp:4:9: error: type 'double' cannot be narrowed to 'int' in initializer list [-Wc++11-narrowing]
    4 |   int a{d};
      |         ^
narrow.cpp:4:9: note: insert an explicit cast to silence this issue
    4 |   int a{d};
      |         ^
      |         static_cast<int>( )
narrow.cpp:6:28: error: non-constant-expression cannot be narrowed from type 'long long' to 'value_type' (aka 'int') in initializer list [-Wc++11-narrowing]
narrow.cpp:7:14: error: constant expression evaluates to -1 which cannot be narrowed to type 'unsigned int' [-Wc++11-narrowing]
（note 与两条 unused variable 警告省略）
```

列表初始化中需要**收窄转换**（[[g:narrowing-conversion|narrowing conversion]]，定义见 [[dcl.init.list#7]]）时，程序非良构（例如 [[dcl.init.list#3.9]]）。三条消息分别对应收窄的三种情形：浮点到整数；源不是常量表达式；源是常量表达式但值放不下。第三条说明，`unsigned u{1};` 这类值能放下的常量是允许的。

如果确实要截断，按 note 的建议写 `static_cast`，让意图出现在代码里。初始化的各种形式见 [[topics/initialization]]。

!!! pitfall "不要用 `-Wno-c++11-narrowing` 消掉它"
    这条错误挂在一个警告选项上。本机加上 `-Wno-c++11-narrowing` 后，`narrow.cpp` 编译通过，不再输出任何诊断。这时编译器接受了一个非良构的程序，而且没有满足 [[intro.compliance.general#2.3]] 要求的至少一条诊断。这个开关是为迁移旧代码准备的，不应该用来修错误。

## most vexing parse

```cpp title="vexing.cpp" run error
struct Timer { Timer(); void start(); };
int main() {
  Timer t();
  t.start();
}
```

```text
vexing.cpp:3:10: warning: empty parentheses interpreted as a function declaration [-Wvexing-parse]
    3 |   Timer t();
      |          ^~
vexing.cpp:3:10: note: remove parentheses to declare a variable
    3 |   Timer t();
      |          ^~
vexing.cpp:4:3: error: base of member reference is a function; perhaps you meant to call it with no arguments?
    4 |   t.start();
      |   ^
      |    ()
1 warning and 1 error generated.
```

`Timer t();` 本身是良构的：它声明了一个不接受参数、返回 `Timer` 的函数 `t`。`()` 不在初始化器的语法里，所以这一行只能解析成函数声明（[[dcl.init.general#15.4]] 的注释）。Clang 为此给出警告，真正的错误出在下一行把函数当对象用。如果 `t` 后来没有被这样使用，就只剩一条警告。

这里的教训是：`error` 前面的 `warning` 有时才是病因。

带实参的版本更隐蔽：

```cpp title="vexing2.cpp" run error
#include <string>
struct Logger {
  explicit Logger(std::string name);
  void log(const char*);
};
int main() {
  Logger lg(std::string());
  lg.log("hi");
}
```

```text
vexing2.cpp:7:12: warning: parentheses were disambiguated as a function declaration [-Wvexing-parse]
    7 |   Logger lg(std::string());
      |            ^~~~~~~~~~~~~~~
vexing2.cpp:7:13: note: add a pair of parentheses to declare a variable
    7 |   Logger lg(std::string());
      |             ^            
      |             (            )
vexing2.cpp:8:5: error: member reference base type 'Logger (std::string (*)())' (aka 'Logger (basic_string<char> (*)())') is not a structure or union
1 warning and 1 error generated.
```

`std::string()` 可以读成一个无名形参，类型是返回 `std::string` 的函数（调整为函数指针）。凡是能解析成声明的都按声明处理（[[dcl.ambig.res#1]]），这就是 [[g:most-vexing-parse|most vexing parse]]。错误消息里的类型 `Logger (std::string (*)())` 正是这个函数的类型。改用花括号 `Logger lg{std::string()};` 就不会有歧义。

## lambda 捕获错误

```cpp title="capture.cpp" run error
struct Counter {
  int n = 0;
  auto inc() { return [] { ++n; }; }
};
int main() {
  int total = 0;
  auto add = [](int x) { total += x; };
  auto add2 = [total](int x) { total += x; };
}
```

```text
capture.cpp:3:30: error: 'this' cannot be implicitly captured in this context
    3 |   auto inc() { return [] { ++n; }; }
      |                              ^
capture.cpp:3:24: note: explicitly capture 'this'
    3 |   auto inc() { return [] { ++n; }; }
      |                        ^
      |                        this
capture.cpp:7:26: error: variable 'total' cannot be implicitly captured in a lambda with no capture-default specified
    7 |   auto add = [](int x) { total += x; };
      |                          ^
capture.cpp:6:7: note: 'total' declared here
capture.cpp:7:14: note: lambda expression begins here
capture.cpp:7:15: note: capture 'total' by value
capture.cpp:7:15: note: capture 'total' by reference
capture.cpp:7:15: note: default capture by value
capture.cpp:7:15: note: default capture by reference
capture.cpp:8:38: error: cannot assign to a variable captured by copy in a non-mutable lambda
    8 |   auto add2 = [total](int x) { total += x; };
      |                                ~~~~~ ^
3 errors generated.
```

（第二个错误的四条修正建议省略了源代码行，原输出中每条都带插入位置。）

前两个错误是同一条规则：一个局部实体（包括 `*this`）在它不可 odr 使用（[[g:odr-usable|odr-usable]]）的作用域里被 odr 使用，程序非良构（[[basic.def.odr#10]]）。lambda 体和外层函数之间隔着 lambda 的作用域，只有当 lambda 写了捕获默认符或显式捕获了这个实体时，它才是可用的。Clang 列出的四个修正建议就是满足这个条件的四种写法。在成员函数里，`n` 实际上是 `this->n`，所以要捕获的是 `this`。

第三个错误：闭包类型的函数调用运算符默认是 `const` 成员函数（[[expr.prim.lambda.closure#7]]），按值捕获的副本是它的数据成员，所以不能修改。要修改副本就加 `mutable`；要修改外面的 `total` 就按引用捕获。另一个常见的错误是同一个名字在捕获列表中出现两次（[[expr.prim.lambda.capture#2]]），Clang 报 `'arr' can appear only once in a capture list`。闭包的模型见 [[topics/lambdas]]。

## 链接错误

编译器输出的最后一行如果是 `linker command failed with exit code 1`，错误就来自链接器。此时每个 TU 都已经编译通过，问题在于 TU 之间的符号对不上。这类问题在标准里对应 ODR 中不要求诊断的规则（[[basic.def.odr#12]]、[[basic.def.odr#16]]），链接器能发现它们，只是因为它们恰好在符号层面可见。符号是怎么来的见 [[toolchain/linking-and-symbols]]。

### 未定义的符号

```cpp title="shape.h"
#pragma once
#include <string>
namespace geo {
struct Circle {
  double r;
  double area() const;
};
std::string describe(const Circle& c, int precision);
}
```

```cpp title="shape.cpp"
#include "shape.h"
namespace geo {
double Circle::area() const { return 3.14159 * r * r; }
std::string describe(const Circle& c, long precision) {
  return "circle";
}
}
```

```cpp title="main.cpp"
#include "shape.h"
#include <cstdio>
int main() {
  geo::Circle c{1.0};
  std::printf("%f %s\n", c.area(), geo::describe(c, 2).c_str());
}
```

```text
$ clang++ -std=c++2c --ld-path=/usr/bin/ld main.cpp shape.cpp -o app
Undefined symbols for architecture arm64:
  "geo::describe(geo::Circle const&, int)", referenced from:
      _main in main-1135e2.o
ld: symbol(s) not found for architecture arm64
clang++: error: linker command failed with exit code 1 (use -v to see invocation)
```

`shape.cpp` 里的 `describe` 形参是 `long`，它是另一个重载，而不是头文件中那个声明的定义。链接器已经把符号名还原（demangle）成了可读的签名，读法就是把它和自己写的定义逐字比对：命名空间、类、形参类型、cv 限定、引用都要一致。

还原前的名字可以用 `llvm-nm` 查看，`c++filt` 或 `llvm-cxxfilt` 负责还原：

```text
$ clang++ -std=c++2c -c main.cpp shape.cpp
$ llvm-nm main.o | grep describe
                 U __ZN3geo8describeERKNS_6CircleEi
$ llvm-nm shape.o | grep describe
0000000000000038 T __ZN3geo8describeERKNS_6CircleEl
$ echo __ZN3geo8describeERKNS_6CircleEi | c++filt
geo::describe(geo::Circle const&, int)
```

`U` 表示引用但未定义，`T` 表示在代码段中定义。两个名字只差最后一个字母：`i` 是 `int`，`l` 是 `long`。编码规则见 [[toolchain/name-mangling]]。

两种同样常见的变体：

- 模板只在头文件里声明、在 `.cpp` 里定义。使用者的 TU 看不到定义，只能留下一个对特化的引用，本机报 `"int sum<int>(std::__1::vector<int, std::__1::allocator<int>> const&)", referenced from: _main`。`std::__1` 是 libc++ 用来区分 ABI 版本的内联命名空间。修法是把定义放进头文件，或者在 `.cpp` 中显式实例化。
- 类声明了虚函数却没有定义。本机的系统链接器会附上一句提示：

```text
Undefined symbols for architecture arm64:
  "Base::~Base()", referenced from:
      Derived::~Derived() in vt-1068a8.o
  "typeinfo for Base", referenced from:
      typeinfo for Derived in vt-1068a8.o
  "vtable for Base", referenced from:
      Base::Base() in vt-1068a8.o
   NOTE: a missing vtable usually means the first non-inline virtual member function has no definition.
```

`vtable for Base` 未定义，是因为 vtable 只在定义 key function（第一个非 inline、非纯虚的虚函数，这里是 `~Base`）的 TU 中生成，见 [[toolchain/object-layout-and-vtables]]。

### 重复定义

```cpp title="util.h"
#pragma once
int clamp01(int x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
int counter = 0;
```

两个 `.cpp` 都包含这个头文件时：

```text
duplicate symbol '_counter' in:
    /private/var/folders/.../T/a-80a5f1.o
    /private/var/folders/.../T/b-316e7d.o
duplicate symbol 'clamp01(int)' in:
    /private/var/folders/.../T/a-80a5f1.o
    /private/var/folders/.../T/b-316e7d.o
ld: 2 duplicate symbols
```

非 inline、非模板的函数或变量在多个 TU 中各有一个定义，程序非良构，不要求诊断（[[basic.def.odr#16.1]]）。修法是在头文件里写 `inline int clamp01(...)` 和 `inline int counter = 0;`，或者把定义移到一个 `.cpp` 中。链接器只能抓到这种强定义的重复；inline 函数在不同 TU 中定义不一致，链接器照样接受，见 [[toolchain/linking-and-symbols]]。

在 Linux 上，GNU ld 和 lld 对这两类错误的措辞不同，本机没有这两个链接器，无法给出原文。内容是一样的：一个符号名，加上引用或定义它的目标文件。

## 控制诊断输出

| 选项 | 作用 | 本机观察 |
|---|---|---|
| `-ferror-limit=N` | 第 N 个错误后停止 | 默认值（驱动传给前端 `-ferror-limit 19`）下，30 个错误的文件输出 19 个错误加一条 `fatal error: too many errors emitted`，共计 `20 errors generated`；`=0` 表示不限 |
| `-ftemplate-backtrace-limit=N` | 实例化链最多显示几层 | 默认显示 10 层；设为 2 时，`sortlist.cpp` 的链折叠为首尾各一层加 `(skipping 4 contexts ...)` |
| `-fno-elide-type` | 不再用 `[...]` 省略两个类型中相同的部分 | 见下例 |
| `-fdiagnostics-show-template-tree` | 把两个模板类型的差异画成树 | 见下例；默认关闭，Clang 23 不接受 `-fno-diagnostics-show-template-tree` 这种写法（`unknown argument`） |
| `-fno-caret-diagnostics` | 不打印源代码行和标记 | 输出变为每条一行，适合 grep |
| `-fdiagnostics-format=sarif` | 输出 SARIF 格式的 JSON，供工具读取 | 本机同时报 `diagnostic formatting in SARIF mode is currently unstable` |

类型很长时，默认的省略、`-fno-elide-type` 和模板树三种显示方式各有用处：

```cpp title="tree.cpp" run error
#include <map>
#include <string>
#include <vector>
using Index = std::map<std::string, std::vector<int>>;
void load(const Index& idx);
int main() {
  std::map<std::string, std::vector<long>> idx;
  load(idx);
}
```

```text
$ clang++ -std=c++2c -fsyntax-only tree.cpp
tree.cpp:5:6: note: candidate function not viable: no known conversion from 'map<[...], vector<long>>' to 'const map<[...], vector<int>>' for 1st argument

$ clang++ -std=c++2c -fsyntax-only -fno-elide-type tree.cpp
tree.cpp:5:6: note: candidate function not viable: no known conversion from 'map<std::string, vector<long>>' to 'const map<std::string, vector<int>>' for 1st argument

$ clang++ -std=c++2c -fsyntax-only -fdiagnostics-show-template-tree tree.cpp
tree.cpp:5:6: note: candidate function not viable: no known conversion from argument type to parameter type for 1st argument
  [(no qualifiers) != const] map<
    [...], 
    vector<
      [long != int]>>
```

模板树把差异定位到 `[long != int]`，嵌套层数多时比一行长字符串好读。

建议的读错误习惯：

1. 只看第一个错误。修好后重新编译，再看下一个。一个缺失的分号或类型名可以引出几十个连锁错误。
2. 错误在库头文件里时，找最后一条位置在自己代码里的 `in instantiation of`；再找 `static_assert` 消息和 `substitution failure` 后面的原因。
3. 错误前面有 `warning` 时先看警告，most vexing parse 就是这样。
4. 链接错误把报出的签名和自己的定义逐字比对。
5. 还是看不懂，就在 Compiler Explorer 上用另一个编译器编译同一段代码。不同编译器挑选的关键信息不同，两份输出合起来常常就清楚了。

编译通过之后的问题属于 [[toolchain/debugging|调试]] 和 [[toolchain/static-analysis|静态分析]] 的范围。

## 思考题

!!! question "1"
    `void f(int&); f(1);` 和 `void g(const int&); g(1);` 为什么前者报 `expects an lvalue`，后者编译通过？如果把 `f` 改成 `void f(int&&);` 呢？

<details markdown="1">
<summary>答案</summary>

[[dcl.init.ref#5.2]]：初始化表达式是右值时，非 const 左值引用不能绑定，程序非良构；const 左值引用可以，此时会实体化一个临时对象并绑定到它。`int&&` 是右值引用，同样可以绑定 `1` 这个纯右值，所以 `f(1)` 也能编译。
</details>

!!! question "2"
    `std::sort` 用在 `std::list` 上报了 4 个错误、114 行，`std::ranges::sort` 只报 1 个错误。差别从标准的哪里来？

<details markdown="1">
<summary>答案</summary>

`std::sort` 对迭代器的要求写在 [[algorithms.requirements#4.7]]，是对模板实参的文字要求，不参与重载决议，所以调用本身能通过，错误要到实现内部用 `-` 时才出现，而且每个用到 `-` 的地方各报一次。`std::ranges::sort` 用 `random_access_range` 概念约束了形参，约束不满足的候选在重载决议阶段就被淘汰（[[over.match.viable#3]]），错误停在调用处，`because` 链说明是哪个原子约束不满足。
</details>

!!! question "3"
    把 `util.h` 里的 `int counter = 0;` 改成 `static int counter = 0;` 也能消除 `duplicate symbol`。它和 `inline int counter = 0;` 有什么区别？

<details markdown="1">
<summary>答案</summary>

`static` 给了 `counter` 内部链接，每个包含该头文件的 TU 各有一个独立的 `counter`，链接器看不到重复，但一个 TU 中的修改另一个 TU 看不到。`inline` 变量仍是外部链接的同一个实体，多个 TU 中的定义由链接器合并为一份（[[basic.def.odr#16]] 允许 inline 变量在多个 TU 中定义）。要共享状态，应该用 `inline`。
</details>

## 小结

| 消息 | 规则 | 先看哪里 |
|---|---|---|
| `no matching function` + `not viable` | [[over.match.viable]] | 每个候选的 note 说明它卡在哪一步 |
| `call to ... is ambiguous` | [[over.match.best.general#3]] | 自己比较各实参的转换等级 |
| `constraints not satisfied` + `because` | [[temp.constr.atomic#3]] | `because` 链的最后一条 |
| 库头文件中的错误 + `in instantiation of` | [[temp.inst]] | 最后一条在自己文件里的实例化 note；`static_assert` 消息 |
| `incomplete type` | [[basic.types.general#3]] | `forward declaration` note；谁触发了析构 |
| `implicitly-deleted` / `deleted function` | [[dcl.fct.def.delete#2]] | note 给出被删除的原因 |
| `missing 'typename'` / `use 'template' keyword` | [[temp.res.general#5]]、[[temp.names#7]] | 按 fix-it 插入关键字 |
| `cannot be narrowed` | [[dcl.init.list#7]] | 用 `static_cast` 写明意图 |
| `-Wvexing-parse` | [[dcl.ambig.res#1]] | 改用花括号或去掉空括号 |
| `cannot be implicitly captured` | [[basic.def.odr#10]] | 按 note 选一种捕获 |
| `Undefined symbols` | [[basic.def.odr#12]] | 逐字比对签名；`llvm-nm` + `c++filt` |
| `duplicate symbol` | [[basic.def.odr#16]] | 头文件里的定义加 `inline` |
