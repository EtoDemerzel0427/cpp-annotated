---
title: 对实现的约束
summary: 标准库实现必须保证什么、可以自由决定什么：头文件的传递包含、函数签名与 ADL、数据竞争、库类的性质、异常，以及移出对象的状态。
status: done
covers: *
papers: P2251R1
related: constraints, namespace.constraints, description, requirements, res.on.objects, intro.races, intro.multithread, class.prop, except.spec, basic.contract, basic.lookup.argdep, class.friend
tags: 库, 实现, 数据竞争, 异常, 移动语义, 可移植性
updated: 2026-10-19
---

!!! tldr
    - 标准头文件可以顺带包含别的头文件，但程序只能依赖 synopsis 里写明的包含关系。用了没包含的头文件里的名字，换一个实现就可能编译失败。
    - 实现可以给成员函数增加重载和默认实参，所以取标准库函数的地址、形成指向成员函数的指针都不可移植。
    - 多个线程同时调用同一对象的 const 成员函数，或者各自操作不同的对象，库保证不会因此产生数据竞争。
    - 库的析构函数不抛异常；实现可以给非虚函数加上 `noexcept`，但不能擅自加 `constexpr`。
    - 标准库对象被移走之后处于有效但未指明的状态：可以赋值，可以调用没有前置条件的函数，但不知道它的值。

[[constraints]] 规定程序使用标准库时要遵守的规则，本节 [conforming] 反过来约束实现：哪些行为实现必须保证，哪些细节实现可以自由决定。可移植的代码只依赖前一类。

## 头文件可以互相包含 [res.on.headers]

<div class="compare" markdown="1">

```cpp run ifndr
#include <vector>
int main() {
  std::vector<int> v{3, 1, 2};
  std::sort(v.begin(), v.end());
}
```

```cpp run ok
#include <algorithm>
#include <vector>
int main() {
  std::vector<int> v{3, 1, 2};
  std::sort(v.begin(), v.end());
}
```

</div>

左边的程序在本机 libc++ 上报错 no member named 'sort'，在另一个实现上却可能顺利编译。两种结果都符合标准。

¶1 一个 C++ 头文件可以包含其他 C++ 头文件。它必须提供自己 synopsis 中的全部声明；如果它的 synopsis 写明包含了另一个头文件，就还要提供那个头文件的全部声明。例如 `<iostream>` 的 synopsis 写明包含 `<ios>`、`<streambuf>`、`<istream>`、`<ostream>`，所以只包含 `<iostream>` 就可以使用 `std::ostream`；所有容器头文件和 `<utility>` 都写明包含 `<compare>` 与 `<initializer_list>`。

除此之外的传递包含都是实现细节。[[using.headers#3]] 要求程序在使用一个名字之前包含声明它的头文件，违反时不要求诊断。所以左边的程序在某个实现上能编译，并不说明它正确。libc++ 近些年一直在削减头文件之间的传递包含，这类代码在升级编译器时最容易出问题。

¶2 `size_t`、`NULL` 这类在多个头文件中都有定义的实体，各处的定义必须相容，按任何顺序包含这些头文件都不会产生重定义错误。¶3 C 头文件（`<stdlib.h>` 这类形式）只能包含它对应的 C++ 头文件（[[headers]]）。

## 函数的签名与查找

### 非成员函数 [global.functions]

¶1 标准库中哪些非成员函数定义为 `inline` 是未指明的。程序既不能依赖某个函数在库的二进制文件里有符号，也不能依赖它没有。

¶2 实现可以声明额外的非成员函数，比如带保留名字的辅助函数，或者标准名字的额外重载。条件是合法程序的调用结果不受影响：对标准描述的签名的调用，表现得如同实现没有声明任何额外的签名。¶3 实现不能给非成员函数添加默认实参。额外的默认实参相当于一个额外的签名，会让原本不可行的调用变得可行。

正因为可能存在额外的重载，对一个标准库函数取地址，可能有歧义，也可能得到意料之外的类型。[[namespace.std#6]] 规定，除非标准把函数指定为可寻址函数（addressable function），程序取标准库函数的地址或引用，结果未指明，甚至可能非良构。

¶4 除非另有说明，标准库函数内部调用非运算符的非成员函数时，不会使用实参依赖查找（ADL，按实参类型所在的命名空间查找函数名，见 [[basic.lookup.argdep]]）在其他命名空间找到的函数。所以库的实现代码到处写成 `std::move(x)`、`std::__invoke(...)` 这样的限定调用，用户命名空间里恰好同名的函数不会被误调用。

运算符是例外：库调用 `==`、`<`、`<<` 时必须经过 ADL，否则用户为自己的类型定义的运算符就找不到了。注 1 还提到了 swap 这类另有说明的情形：[[swappable.requirements]] 要求通过 ADL 找到用户的 `swap`。

```cpp run ok
#include <algorithm>
#include <vector>
namespace app {
  struct X { int v; };
  bool operator==(X a, X b) { return a.v == b.v; }
}
int main() {
  std::vector<app::X> v{{1}, {2}};
  // std::find 内部的 *it == value 经 ADL 找到 app::operator==
  return std::find(v.begin(), v.end(), app::X{2}) != v.end() ? 0 : 1;
}
```

### 成员函数 [member.functions]

¶2 对于非虚成员函数，实现可以声明一组不同的签名，只要任何按标准签名能选中某个重载的调用，结果都与选中那个重载相同。注 1 举的例子是：添加带默认值的形参，把一个带默认实参的函数拆成几个重载，或者为同一个名字增加签名。

成员函数不能被用户在类外重新声明或重载，所以实现在这里的自由比非成员函数大。代价是 `&std::vector<int>::push_back` 的类型没有保证，[[namespace.std#6]] 因此也禁止形成指向标准库非静态成员函数的成员指针。虚函数不在此列，它的签名决定了派生类能否覆盖它，必须与标准一致。

¶1 和非成员函数一样，成员函数是否为 `inline` 也是未指明的。

### 隐藏友元 [hidden.friends]

¶1 如果标准在类定义里把某个函数声明为友元，那么这个友元声明就必须是实现提供的唯一声明，命名空间作用域不能再有它的声明。注 2 说明，这样的函数叫做**隐藏友元**（hidden friend）：普通的非限定查找和限定查找都找不到它，只有 ADL 能找到（[[class.friend]]）。

<div class="compare" markdown="1">

```cpp run ok
#include <compare>
int main() {
  auto r = std::strong_ordering::less;
  return r < 0;   // ADL 找到隐藏友元
}
```

```cpp run error
#include <compare>
int main() {
  auto r = std::strong_ordering::less;
  return std::operator<(r, 0);
  // error: std 中没有 operator<
}
```

</div>

比较类别类型的比较运算符、迭代器的 `iter_move` 和 `iter_swap`、许多视图迭代器的 `==` 都是隐藏友元。它们只在实参涉及这个类时才参与重载决议，不会被无关的类型通过隐式转换选中，也减少了编译器要考虑的候选函数。

### constexpr 函数 [constexpr.functions]

¶1 标准明确要求某些库函数是 `constexpr` 的，实现不得把其他库函数声明为 `constexpr`。头文件里只要有 `constexpr` 函数的非定义声明，就必须同时提供定义，否则这个函数无法在常量求值中调用。

为什么禁止实现多加 `constexpr`？因为它是可观察的。假如某个实现把 `std::strlen` 声明为 `constexpr`，`constexpr auto n = std::strlen("abc");` 就会在这个实现上编译通过、在其他实现上失败，用 `requires` 表达式探测一个调用能否常量求值的代码也会因实现而得到不同的答案。

!!! impl "实现的现状"
    这一条并没有被严格遵守。GCC 把许多 `<cmath>` 函数当作内建函数，在常量表达式中直接求值，所以 `constexpr double x = std::sqrt(2.0);` 很早就能用 GCC 编译。反方向的落后也存在：C++23 已经要求 `<cstdlib>` 的 `std::abs` 是 `constexpr`，本机 Clang 23 + libc++ 上 `constexpr int y = std::abs(-1);` 仍然报错。

## 并发访问 [res.on.data.races]

### 库函数保证不制造数据竞争

两个线程在没有同步的情况下访问同一个对象，其中至少一个是修改，就构成**数据竞争**，程序的行为未定义（[[intro.races]]）。下面几段保证，只要程序自己没有共享对象，调用库函数不会凭空制造数据竞争。

¶2 库函数只能访问通过实参（包括 `this`）直接或间接到达的、可能被其他线程访问的对象。¶3 库函数只能修改通过非 const 实参（包括 `this`）到达的这类对象。¶4 注 1 指出，这意味着实现不能在没有同步的情况下使用静态存储期的内部对象。

¶5 库函数访问容器实参的元素时，只能通过其规范要求调用的函数。¶6 从容器或字符串的成员函数得到的迭代器，对它的操作可以访问底层容器，但不能修改它。¶7 实现可以在线程间共享自己的内部对象，前提是这些对象对用户不可见，并且受到保护。

¶8 除非另有说明，有用户可见效果的操作必须在当前线程中执行。¶9 注 3 补充，这允许实现在没有可见副作用时把操作并行化。并行算法的执行策略就是这里的另有说明。

### 用户可以依赖的结论

| 情形 | 是否安全 | 依据 |
|---|---|---|
| 多个线程同时调用同一对象的 const 成员函数，如 `v.size()`、`m.find(k)` | 安全 | ¶3 |
| 多个线程各自操作不同的对象，即使类型相同 | 安全 | ¶2、¶4 |
| 一个线程修改容器，另一个线程读取同一容器 | 数据竞争 | [[res.on.objects]] |
| 不同线程修改同一个 `vector` 的不同元素 | 安全，`vector<bool>` 除外 | [[container.requirements.dataraces]] |
| `std::rand`、`std::strtok`、`std::localtime` | 可能竞争 | 它们的规范另有说明，允许使用内部静态状态 |

容器有一条补充：[[container.requirements.dataraces]] 规定 `begin`、`end`、`data`、`find`、`at` 等函数即使调用的是非 const 重载，在判断数据竞争时也视为 const。所以一个线程调用 `v.size()`、另一个线程调用同一个 `v` 的非 const `data()`，并不构成竞争。

`shared_ptr` 也有专门的规定（[[util.smartptr.shared]]）：判断数据竞争时，成员函数只算访问 `shared_ptr` 对象本身，引用计数的变化不算修改。所以两个线程各自拷贝或销毁指向同一控制块的不同 `shared_ptr` 对象是安全的；两个线程同时给同一个 `shared_ptr` 对象赋值仍然是数据竞争，这时应该用 `std::atomic<std::shared_ptr<T>>`。

### 可重入性 [reentrancy]

¶1 除非标准明确规定，哪些库函数可以递归重入由实现定义。

¶2 在一个非静态成员函数 F 对某个对象执行期间，如果程序通过另一条路径访问这个对象，也就是使用的 glvalue 不是从 F 的对象形参得到的，并且这次访问可能与 F 有权进行的访问冲突，行为未定义，除非另有说明。

```cpp run ub
#include <functional>
std::function<void()> f;
int main() {
  f = [] { f = nullptr; };   // 在 f 的 operator() 执行期间，
  f();                       // 经全局名 f 修改 f 本身：UB
}
```

`operator()` 执行时会读取 `*this`，而 lambda 内部通过全局变量名 `f` 修改了同一个对象，被销毁的正是正在执行的那个可调用对象。同类的问题还有：在 `std::map` 的比较器里向这个 map 插入元素，在 `shared_ptr` 的删除器里重置同一个 `shared_ptr`。

## 库类的性质

### 是否可平凡复制 [library.class.props]

¶1 除非明确另有说明，标准库中的类是否为可平凡复制类、标准布局类或隐式生存期类（[[class.prop]]）是未指明的。所以对标准库对象做 `memcpy`、`std::bit_cast`，或者通过共享内存在进程间传递，只有在标准明确规定时才可移植。本机 libc++ 的结果：

| 类型 | 可平凡复制 | 标准是否规定 |
|---|---|---|
| `std::pair<int, int>` | 否 | 未规定 |
| `std::tuple<int, int>` | 否 | 未规定 |
| `std::optional<int>` | 是 | 规定了：`T` 的复制、移动和析构平凡时，`optional<T>` 的对应操作也平凡 |
| `std::array<int, 3>` | 是 | 它是聚合，性质由元素决定 |
| `std::span<int>`、`std::string_view` | 是 | C++23 起规定（[[P2251R1]]） |
| `std::chrono::seconds` | 是 | 未规定 |

`std::pair<int, int>` 不可平凡复制，是因为 `pair` 要支持引用成员：`pair<int&, int&>` 的赋值是给被引用的对象赋值，而不是重新绑定。libc++ 用一个用户提供的 `operator=` 统一处理所有 `pair`，于是它对任何 `pair` 都不平凡。改变这一点会影响 ABI，比如函数参数的传递方式。

### 友元与派生 [protection.within.classes] [derivation]

[protection.within.classes] ¶1 规定，标准库中的函数或类是否是另一个库类的友元是未指明的。实现可以让库类彼此成为友元，用户代码不能依赖这一点。

[derivation] ¶1–¶2 允许实现让任何库类派生自一个名字保留给实现的类，要求派生自某个库类时，也可以经由若干这样的中间基类间接派生。例如 libstdc++ 的 `std::vector` 派生自内部的 `_Vector_base`。所以用 `std::is_base_of` 探测库类之间的关系，只能依赖标准写明的那些，比如 `std::runtime_error` 派生自 `std::exception`。

¶3 无论怎样派生，规定为虚基类的必须是虚基类，没有规定为虚基类的不能是虚基类。名字不同的类型必须是不同的类型，除非标准另有说明；注 1 指出，`size_t` 这类被描述为同义词的 typedef 名字是例外。

¶4 除非另有说明，标准库中的类型都不是 `final`，可以被继承（本机 `std::is_final_v<std::vector<int>>` 为 `false`）。能继承不等于应该继承，例如 `std::vector` 的析构函数不是虚函数。

## 异常 [res.on.exception.handling]

¶1 库函数报告失败时，抛出的是 *Throws* 段落列出的类型，或者能被该类型的处理器捕获的派生类型。¶4 没有 *Throws* 段落、但异常规范是潜在抛出的函数，可以抛出由实现定义的异常；脚注 147 说明，它们可以抛 `bad_alloc` 或其派生类来报告分配失败。实现应当只抛标准异常类或其派生类。

¶2 来自 C 标准库的函数不抛异常，除非它调用了程序提供的、会抛异常的函数。脚注 146 指出 `qsort` 和 `bsearch` 属于这种情况。

¶3 标准库中的析构函数不抛异常，它们都表现得如同具有不抛出的异常规范（[[except.spec]]）。

¶5 实现可以给非虚函数加上不抛出的异常规范。libc++ 就给 `vector::operator[]` 加了 `noexcept`：

```cpp run impl
#include <vector>
std::vector<int> v;
// 标准没有把 vector::operator[] 声明为 noexcept
static_assert(noexcept(v[0]));   // 本机 libc++ 成立，不可移植
int main() {}
```

所以 `noexcept(f())` 对一个标准中没有声明 `noexcept` 的库函数，结果不一定是 `false`。这一条只适用于非虚函数：虚函数一旦是 `noexcept` 的，所有覆盖它的函数也必须是 `noexcept` 的（[[except.spec]]），实现擅自加上会让用户原本合法的覆盖函数变得非良构。

## 契约断言 [res.contract.assertions] {{c++26}}

¶1 除非另有规定，实现可以用契约断言（[[basic.contract]]）检查库函数规定的前置条件和后置条件，例如在 `std::vector::front()` 上写 `pre(!empty())`。这是一项许可，不是要求：检查与否、采用哪种求值语义都由实现决定。只有加固实现中的加固前置条件（hardened precondition）才必须检查，见 [[structure.specifications]]。

## 移出对象的状态 [lib.types.movedfrom]

¶1 标准库类型的对象可以被移动。除非另有说明，被移走的对象处于**有效但未指明的状态**（valid but unspecified state，[[defns.valid]]）：对象的不变式仍然成立，没有前置条件的操作都可以调用，但不知道它的值。¶2 标准库对象可以移动赋值给自己，结果同样是有效但未指明的状态。

```cpp run ok
#include <string>
#include <utility>
#include <vector>
int main() {
  std::vector<int> a{1, 2, 3};
  std::vector<int> b = std::move(a);
  [[maybe_unused]] auto n = a.size(); // OK：值未知
  // a.front();   // 不行：前置条件 !empty()，而 a 的值未知
  a.clear();      // OK：此后 a 一定为空
  a.push_back(4); // OK

  std::string s = "hello";
  std::string& r = s;
  s = std::move(r);  // 自移动赋值：不是 UB（¶2）
  s = "again";       // OK
  return a.size() == 1 && s == "again" ? 0 : 1;
}
```

许多类型另有说明，给出了更强的保证：`unique_ptr` 和 `shared_ptr` 移出后为空；`optional` 移出后仍然有值，值本身处于 `T` 的移出状态；`thread`、`unique_lock`、`promise` 移出后不再关联任何东西。`string` 和 `vector` 移动构造后，源对象在主流实现中为空，但标准没有这样保证。

## 错误码 [value.error.codes]

¶1 有些库函数通过 `error_code` 报告错误。来自操作系统的错误，其 `category()` 返回 `system_category()`；其他来源的错误返回某个由实现定义的错误类别。例 1 建议基于 POSIX 的实现让 `system_category()` 的值与 `errno` 相同。

所以 `std::filesystem` 的操作失败时，`ec.value()` 在 Linux 和 macOS 上就是 `errno` 的值，例如 `ENOENT`。可移植的写法是与 `std::errc::no_such_file_or_directory` 比较，它是一个 `error_condition`，比较时会按类别做映射，不依赖具体数值。

<details class="fine" markdown="1"><summary>其余条文</summary>

[conforming.overview] ¶1–¶2 是本节的目录：列出实现对头文件、宏、非成员函数、成员函数、数据竞争避免、访问说明符、类派生、异常、契约断言的使用分别在哪个子条款讨论。

[res.on.macro.definitions] ¶1 [[contents]] 描述的名字和全局函数签名保留给实现。¶2 C 标准库中被描述为展开为整型常量表达式的对象式宏，例如 `INT_MAX`、`CHAR_BIT`、`EOF`、`SIZE_MAX`，都可以用在 `#if` 中。这排除了用 `sizeof` 或枚举常量定义这些宏的实现方式。

[algorithm.stable] ¶1 规定算法说明里稳定（stable）一词的含义。对排序算法（如 `stable_sort`），等价元素的相对顺序保持不变；对删除和复制算法（如 `remove_if`、`copy_if`），留下的元素保持相对顺序；对归并算法（如 `merge`），等价元素中来自第一个范围的排在来自第二个范围的之前，各自保持原有顺序。

</details>

## 思考题

!!! question "思考题 1"
    实现 A 的 `<algorithm>` 包含了 `<string>`，实现 B 没有。一个程序只包含 `<algorithm>` 就使用了 `std::string`。它在实现 A 上是正确的程序吗？

<details markdown="1">
<summary>答案</summary>

不是。[res.on.headers] ¶1 允许实现 A 这样包含，但 `<algorithm>` 的 synopsis 并没有写明包含 `<string>`。[[using.headers#3]] 要求在使用 `std::string` 之前包含声明它的头文件，违反时不要求诊断。在实现 A 上恰好能编译，正是这类不要求诊断的错误的典型表现。
</details>

!!! question "思考题 2"
    一个线程调用 `std::vector<int>` 对象的 `size()`，另一个线程同时调用同一个对象的非 const `data()`。有数据竞争吗？

<details markdown="1">
<summary>答案</summary>

没有。按 [res.on.data.races] ¶3，非 const 的 `data()` 原则上允许修改对象；但 [[container.requirements.dataraces]] ¶1 规定，判断数据竞争时 `data`、`begin`、`find` 等函数视为 const。两个调用都只是读取，不冲突。如果把 `data()` 换成 `push_back`，就构成冲突，按 [[res.on.objects]] 行为未定义。
</details>

## 小结

!!! summary "可以依赖的与不能依赖的"
    | 可以依赖 | 不能依赖 |
    |---|---|
    | 头文件提供其 synopsis 中的声明，包括写明的包含 | 其他任何传递包含 |
    | 合法调用总是选中标准规定的非成员重载；非成员函数没有额外的默认实参 | 函数是否 inline；成员函数的签名集合；能否取地址 |
    | 库内部对非运算符函数不做 ADL，对运算符做 ADL | 库类之间是否互为友元 |
    | 规定为友元的函数只能经 ADL 找到 | |
    | 实现不擅自添加 constexpr | 实现已经实现了所有要求的 constexpr |
    | const 并发调用安全；不同对象并发安全 | 库内部是否并行执行（只要没有可见副作用） |
    | 规定的虚基类关系；类型不是 final | 是否有额外的保留名字基类；是否可平凡复制 |
    | 只抛 *Throws* 中的类型或其派生类；析构不抛；C 函数不抛 | `noexcept` 运算符对未声明 noexcept 的函数的结果 |
    | 移出对象有效，可以赋值，可以调用无前置条件的操作 | 移出对象的值 |
