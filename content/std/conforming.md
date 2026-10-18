---
title: 对实现的约束
summary: 标准库实现的义务与自由：头文件可以互相包含；非成员函数不得改变合法调用的结果、不得加默认实参、内部调用不做 ADL；成员函数可以有额外的重载与默认实参；隐藏友元只能是唯一声明；不得擅自添加 constexpr；"稳定"算法的含义；可重入性；数据竞争避免的七条规则；库类是否可平凡复制未指明；可以添加保留名字的基类；只抛 Throws 中列出的异常、析构不抛、可以加强 noexcept；可以用契约断言检查前置条件；错误码的类别；移出对象处于"有效但未指明"的状态。
status: done
covers: *
papers: P2251R1
related: constraints, namespace.constraints, description, requirements, res.on.objects, intro.races, intro.multithread, class.prop, except.spec, basic.contract, basic.lookup.argdep, class.friend
tags: 库, 实现, 数据竞争, 异常, 移动语义, 可移植性
updated: 2026-10-18
---

[[constraints]] 约束程序，本节 [conforming] 约束**实现**。读它有两个目的：

1. **知道实现必须保证什么**——这是你可以依赖的（例如"const 成员函数并发调用是安全的"、"析构函数不抛异常"、"移出后的对象仍然可以赋值"）。
2. **知道实现可以自由发挥什么**——这是你**不能**依赖的（例如"头文件 A 会顺带包含 B"、"`std::pair<int,int>` 可以 `memcpy`"、"`&std::vector<int>::push_back` 有确定的类型"）。

可移植代码就是只依赖第一类、不依赖第二类的代码。

## 概述（[conforming.overview]）

¶1 本节描述对 C++ 标准库实现的约束与许可。¶2 是导航：实现对头文件（[res.on.headers]）、宏（[res.on.macro.definitions]）、非成员函数（[global.functions]）、成员函数（[member.functions]）、数据竞争避免（[res.on.data.races]）、访问说明符（[protection.within.classes]）、类派生（[derivation]）、异常（[res.on.exception.handling]）、契约断言（[res.contract.assertions]）的使用。

## 头文件（[res.on.headers]）

¶1 C++ 头文件**可以包含其他 C++ 头文件**。C++ 头文件必须提供出现在其 synopsis 中的声明和定义。在 synopsis 中显示为包含其他 C++ 头文件的 C++ 头文件，必须提供那些头文件 synopsis 中的声明和定义。

¶2 某些类型和宏在多个头文件中定义。每个这样的实体都必须定义为：任何定义它的头文件，都可以在任何其他也定义它的头文件之后被包含（[[basic.def.odr]]）。

¶3 C 标准库头文件（`<name.h>`）只能包含其对应的 C++ 标准库头文件，如 [[headers]] 所述。

¶1 的前半句是"传递包含"的根源，也是可移植性问题的头号来源：

| synopsis 明确要求的包含 | 例子 |
|---|---|
| `<iostream>` 包含 `<ios>`、`<streambuf>`、`<istream>`、`<ostream>` | 所以 `#include <iostream>` 后可以用 `std::ostream`、`std::endl` |
| `<utility>` 包含 `<compare>`、`<initializer_list>` | |
| 所有容器头文件包含 `<compare>`、`<initializer_list>` | |
| `<ranges>` 包含 `<compare>`、`<initializer_list>`、`<iterator>` | |

除此之外的传递包含都是实现细节。`#include <iostream>` 后用 `std::string`、`#include <vector>` 后用 `std::sort`、`#include <map>` 后用 `std::pair` 以外的 `<utility>` 设施——都是依赖了实现的自由（违反 [[using.headers#3]]，IFNDR）。libc++ 近年来持续减少传递包含，并且按语言标准版本区分：在较新的 `-std=` 模式下，头文件之间的传递包含更少——同一段代码用 `-std=c++17` 能编译、换成 `-std=c++2c` 就找不到 `std::string`，并不罕见。

¶2 说的是 `size_t`、`NULL`、`nullptr_t` 这样在多个头文件中都有定义的实体：它们的定义必须彼此兼容，不能因为包含顺序不同而产生 ODR 违规或重定义错误。

## 宏定义的限制（[res.on.macro.definitions]）

¶1 [[contents]] 中描述的名字和全局函数签名保留给实现。

¶2 C 标准库定义、并在本章中被描述为展开为**整型常量表达式**的所有对象式宏，除非明确另有说明，也都适用于 `#if` 预处理指令。——例如 `INT_MAX`、`CHAR_BIT`、`EOF`、`SIZE_MAX` 都可以写在 `#if` 里。这排除了"用 `sizeof` 或枚举常量来定义宏"的实现方式（`#if` 中不能求值 `sizeof`）。

## 非成员函数（[global.functions]）

¶1 C++ 标准库中任何非成员函数是否定义为 `inline`，是**未指明**的。

¶2 对第 17–33 章及附录 D 描述的非成员函数签名的调用，必须表现得**如同实现没有声明额外的非成员函数签名**。脚注：合法的 C++ 程序总是调用预期的库非成员函数；实现也可以定义额外的非成员函数，只要合法程序不会调用到它们。

¶3 实现不得为非成员函数签名声明**额外的默认实参**。

¶4 除非另有说明，标准库中函数对**非运算符、非成员**函数的调用，不使用通过实参依赖查找（[[basic.lookup.argdep]]）在其他命名空间中找到的函数。Note 1："除非另有说明"适用于可交换要求（[[swappable.requirements]]）这样的情形。对重载运算符的例外允许在 `ostream_iterator::operator=` 这样的情形中进行 ADL：表达式 `*out_stream << value` 的查找包含 `value` 类型的关联命名空间。

逐条看：

- **¶1** 意味着你不能依赖某个标准函数**有**外部定义（例如在库的 `.so` 中能找到符号），也不能依赖它**没有**。
- **¶2** 允许实现添加辅助重载（通常是保留名字的 `__xxx`，或者对标准名字的额外重载），但这些重载不能"抢走"合法调用。这也是 [[namespace.std#6]] 禁止取地址的根据之一：额外的重载会让 `&std::f` 变得有歧义——那不是合法调用。
- **¶3** 与成员函数形成对比：非成员函数**不能**加默认实参，因为默认实参会改变函数的类型被使用的方式（例如作为模板实参推导的来源）。
- **¶4** 是 [[contents#3]] 在"实现内部"的对应物：库的实现代码在调用非运算符函数时不能被用户的同名函数通过 ADL 劫持。这就是为什么 libc++ 源码里到处写 `std::__invoke(...)`、`std::move(...)`、`std::__to_address(...)`——而**运算符**（`==`、`<`、`<<`）则必须经过 ADL，否则用户为自己类型定义的运算符就找不到了。

```cpp run ok
#include <algorithm>
#include <vector>
namespace app {
  struct X { int v; };
  bool operator==(X a, X b) { return a.v == b.v; }      // 运算符：库通过 ADL 找到它（¶4 的例外）
  template<class It, class T> It find(It, It, const T&); // 同名的非运算符函数：库内部不会找到它
}
int main() {
  std::vector<app::X> v{{1}, {2}};
  return std::find(v.begin(), v.end(), app::X{2}) != v.end() ? 0 : 1;
}
```

## 成员函数（[member.functions]）

¶1 C++ 标准库中任何成员函数是否定义为 `inline`，是未指明的。

¶2 对标准库中描述的**非虚**成员函数，实现可以声明**不同的成员函数签名集合**，只要任何会从本文档描述的声明集合中选中某个重载的调用，都表现得如同选中了那个重载。Note 1：例如，实现可以添加带默认值的形参，或把带默认实参的成员函数替换为两个或多个行为等价的成员函数，或为某个成员函数名添加额外的签名。

这条自由度比非成员函数大得多——因为成员函数不能被用户重载或在类外声明，实现可以随意调整，只要**通过调用**观察不到差别。后果：

- `&std::vector<int>::push_back` 的类型不确定（可能有更多重载、可能多一个默认形参）——这就是 [[namespace.std#6]] 禁止形成指向标准库成员函数的成员指针的原因；
- `decltype(&std::string::size)` 不可移植；
- 虚函数**不在**此列：虚函数的签名是派生类覆盖的依据（[[derived.classes]]），必须与标准一致。

## 友元函数（[hidden.friends]）

¶1 只要本文档在类或类模板定义中规定了函数或函数模板的**友元声明**，该声明就必须是实现提供的该函数或函数模板的**唯一声明**。Note 1：特别地，符合标准的实现不会在命名空间作用域提供该函数的任何额外声明。Note 2：这样的友元函数（模板）声明被称为**隐藏友元**（hidden friend），因为它对普通的非限定查找（[[basic.lookup.unqual]]）和限定查找（[[basic.lookup.qual]]）都不可见。

隐藏友元**只能**通过 ADL 找到（[[class.friend]]）。标准选择这种方式定义很多运算符（比较类别类型的比较、迭代器的 `iter_move`/`iter_swap`、各种视图迭代器的 `==`），好处是：它们不参与无关类型的重载决议（减少编译时间和意外的隐式转换），也不能被限定名调用。

```cpp error
#include <compare>
int main() {
  auto r = std::strong_ordering::less;
  bool b1 = (r == 0);                // OK：ADL 找到隐藏友元 operator==(strong_ordering, unspecified)
  bool b2 = std::operator==(r, 0);   // error: no member named 'operator==' in namespace 'std'
  return b1 && b2;
}
```

[hidden.friends] 把"实现只能提供友元声明"写成了规范：若实现在命名空间作用域也声明了一份，第二行就能编译——那就违背了标准。

## constexpr 函数（[constexpr.functions]）

¶1 本文档明确要求某些标准库函数是 `constexpr` 的（[[dcl.constexpr]]）。实现**不得**把任何标准库函数签名声明为 `constexpr`，除非明确要求。在任何提供 `constexpr` 函数的非定义声明的头文件中，实现必须提供相应的定义。

为什么禁止实现"好心"地多加 `constexpr`？因为 `constexpr` 是**可观测的**：

```cpp
template<int N> struct tag { };
template<class F> concept constant_callable = requires { typename tag<(F{}(), 0)>; };
// 若某实现给一个标准函数擅自加了 constexpr，这类探测的结果就会因实现而异——
// 一段代码在实现 A 上能编译、在实现 B 上不能，而两者都声称符合标准。
```

第二句（必须提供定义）保证了 `constexpr` 函数在常量求值时可用：只有声明没有定义的 `constexpr` 函数无法在编译期调用。

!!! impl "实现的现状"
    这一条在实践中并没有被严格遵守：GCC 长期把许多 `<cmath>` 函数作为内建函数在常量表达式中求值（作为扩展），使得 `constexpr double x = std::sqrt(2.0);` 在 C++26 之前就能通过 GCC 编译。这是 [[intro.compliance]] 意义上的扩展，严格来说与 [constexpr.functions] 冲突。反过来，标准要求为 `constexpr` 的函数，实现可能还没跟上——例如本机 libc++ 尚未把 C++23/26 要求的 `<cmath>` 函数实现为 `constexpr`（见 [[library.c]]）。

## 稳定算法（[algorithm.stable]）

¶1 当算法的要求声明它是"**稳定的**"（stable）而无进一步说明时，其含义是：

- **¶1.1** 对**排序**算法：等价元素的相对顺序被保持。
- **¶1.2** 对**删除和复制**算法：未被删除的元素的相对顺序被保持。
- **¶1.3** 对**归并**算法：对于原来两个范围中的等价元素，来自第一个范围的元素（保持原有顺序）排在来自第二个范围的元素（保持原有顺序）之前。

所以 `std::stable_sort`、`std::stable_partition`、`std::remove`/`std::remove_if`/`std::copy_if`（标准说它们是 stable 的）、`std::merge`/`std::inplace_merge` 都有这些保证；`std::sort`、`std::partition`、`std::unique`（除第一个外删除，相对顺序保持——它属于"删除"类）则按各自的规范。

```cpp run ok
#include <algorithm>
#include <string>
#include <utility>
#include <vector>
int main() {
  std::vector<std::pair<int, std::string>> v{{2, "a"}, {1, "b"}, {2, "c"}, {1, "d"}};
  std::ranges::stable_sort(v, {}, &std::pair<int, std::string>::first);
  // ¶1.1：键相等的元素保持原相对顺序 → {1,b} {1,d} {2,a} {2,c}
  return v[0].second == "b" && v[1].second == "d" && v[2].second == "a" ? 0 : 1;
}
```

（这里 `&std::pair<int, std::string>::first` 是指向**数据成员**的成员指针，不受 [[namespace.std#6]] 对成员**函数**的限制。）

## 可重入性（[reentrancy]）

¶1 除本文档明确规定之处外，标准库中哪些函数可以被**递归重入**，是**实现定义**的。

¶2 在对某个对象执行标准库非静态成员函数 F 期间，若通过一个**并非（直接或间接）从 F 的对象形参获得的** glvalue 访问该对象，且这种访问可能与 F 被允许进行的任何访问（[[res.on.data.races]]）**冲突**（[[intro.races]]），则行为未定义，除非另有说明。

¶2 是 C++23 之后更新的措辞中加入的一条重要澄清。它处理的是"回调中修改正在调用自己的对象"这种情形：

```cpp ub
#include <functional>
std::function<void()> f;
int main() {
  f = [] { f = nullptr; };   // 在 f 的 operator() 执行期间，通过全局名 f（不是从 operator() 的
  f();                       // 对象形参得到的 glvalue）修改 f —— 与 operator() 对 *this 的访问冲突
}                            // UB（¶2）：被销毁的恰恰是正在执行的那个 lambda
```

同类问题：在 `std::vector` 的元素的拷贝构造函数里修改那个 vector；在 `std::map` 的比较器里向 map 插入元素；在 `std::shared_ptr` 的删除器里重置同一个 `shared_ptr`。

## 数据竞争避免（[res.on.data.races]）

¶1 本小节规定实现为**防止数据竞争**必须满足的要求。除非另有说明，每个标准库函数都必须满足每条要求。实现可以在下面规定之外的情形中也防止数据竞争。

¶2 标准库函数不得直接或间接**访问**可被当前线程以外的线程访问的对象（[[intro.multithread]]），除非这些对象是通过函数的**实参**（包括 `this`）直接或间接访问的。

¶3 标准库函数不得直接或间接**修改**可被当前线程以外的线程访问的对象，除非这些对象是通过函数的**非 const 实参**（包括 `this`）直接或间接访问的。

¶4 Note 1：这意味着，例如，实现不能在没有同步的情况下为内部目的使用具有静态存储期的对象，因为即使在没有显式共享对象的程序中，这样做也可能导致数据竞争。

¶5 标准库函数不得通过其实参、或其容器实参的元素间接访问对象，除非通过调用其规范所要求的、作用于那些容器元素的函数。

¶6 对通过调用标准库容器或字符串成员函数获得的迭代器进行的操作，可以访问底层容器，但不得修改它。Note 2：特别地，使迭代器失效的容器操作与对与该容器关联的迭代器的操作冲突。

¶7 实现可以在线程间共享其自己的内部对象，前提是这些对象对用户不可见且受到防止数据竞争的保护。

¶8 除非另有说明，若操作具有对用户可见的效果，C++ 标准库函数必须**仅在当前线程内**执行所有这些操作。

¶9 Note 3：这允许实现在没有可见副作用时并行化操作。

把这几条翻译成用户可以依赖的结论：

| 结论 | 依据 |
|---|---|
| 多个线程同时对**同一个**对象调用 **const** 成员函数（如 `v.size()`、`m.find(k)`、`s.c_str()`）是安全的 | ¶3：const 实参不允许被修改 |
| 多个线程分别操作**不同**的对象（哪怕是同一类型）是安全的 | ¶2、¶4：库不能偷偷共享静态状态 |
| `std::rand()`、`std::strtok`、`std::localtime` 等 C 函数**不在**此列 | 它们各自"另有说明"——C 标准规定它们使用内部静态状态 |
| 一个线程修改容器、另一个线程读取同一容器 | 冲突，按 [[res.on.objects]] 是 UB |
| 不同线程修改同一 `vector` 的**不同元素**是安全的——**`vector<bool>` 除外** | [container.reqmts] 的数据竞争条款；`vector<bool>` 的元素共享字节 |
| 库可以内部使用线程池（如并行算法），但用户可见的操作（调用用户函数、I/O）必须在当前线程中执行，除非另有说明 | ¶8、¶9；执行策略就是那个"另有说明" |

¶2 中"通过实参间接访问"包括了 `shared_ptr` 的引用计数：两个线程分别拷贝**不同的** `shared_ptr` 对象（指向同一控制块），库必须保证安全——控制块是经由实参可达的，但标准在 [util.smartptr.shared] 中另有规定要求引用计数的更新是原子的。而两个线程同时对**同一个** `shared_ptr` 对象赋值，仍然是数据竞争（应当使用 `std::atomic<std::shared_ptr<T>>`）。

## 库类的性质（[library.class.props]）

¶1 除非明确另有说明，第 17–33 章和附录 D 描述的任何类是否为**可平凡复制**类、**标准布局**类或**隐式生存期**类（[[class.prop]]），是**未指明**的。

这意味着 `memcpy` 一个标准库对象、把它放进 `union`、用 `std::bit_cast` 转换它、通过共享内存在进程间传递它——除非标准明确规定，都不可移植。本机 libc++ 的实测：

| 类型 | 可平凡复制？ | 标准是否规定 |
|---|---|---|
| `std::pair<int, int>` | **否** | 未指明 |
| `std::tuple<int, int>` | **否** | 未指明 |
| `std::optional<int>` | 是 | 实际上被规定：其拷贝/移动构造、赋值与析构在 `T` 的对应操作平凡时为平凡 |
| `std::array<int, 3>` | 是 | 是聚合，性质由元素决定 |
| `std::span<int>`、`std::string_view` | 是 | C++23 起明确规定（[[P2251R1]]） |
| `std::chrono::seconds` | 是 | 未明确规定 |

`std::pair<int, int>` 不可平凡复制，是因为它的赋值运算符需要处理引用成员（`pair<int&, int&>` 的赋值语义是"赋值给被引用对象"，而不是重新绑定），libc++ 的 `__utility/pair.h` 用用户提供的 `operator=` 统一实现，于是对所有 `pair` 都不平凡；改变这一点会影响 ABI（例如函数参数的传递方式）。

## 类内的保护（[protection.within.classes]）

¶1 第 17–33 章及附录 D 描述的任何函数签名或类，是否为 C++ 标准库中另一个类的**友元**，是**未指明**的。——实现可以随意让标准类彼此成为友元（例如让 `std::basic_string` 访问 `std::basic_string_view` 的内部），用户代码不能依赖、也不能反向利用这一点。

## 派生（[derivation]）

¶1 实现可以让 C++ 标准库中的任何类派生自一个**名字保留给实现**的类。

¶2 某些标准库类被要求派生自其他标准库类。实现可以让这样的类直接派生自所要求的基类，也可以通过一个由名字保留给实现的基类构成的层次间接派生。

¶3 在任何情况下：**¶3.1** 每个被描述为 `virtual` 的基类必须是虚基类；**¶3.2** 每个未被规定为 `virtual` 的基类不得是虚基类；**¶3.3** 除非明确另有说明，名字不同的类型必须是不同的类型。Note 1：对于被描述为同义词的类型（[[dcl.typedef]]、[[namespace.udecl]]），如 `size_t` 和 `streamoff`，这条规则有隐含的例外。

¶4 标准库中规定的所有类型都必须是**非 final** 的，除非另有说明。

¶1、¶2 解释了为什么 `std::vector` 在 libstdc++ 中派生自内部基类 `_Vector_base`。后果：

- 用 `std::is_base_of` 探测标准类之间的关系，只能依赖标准明确规定的那些（例如 `is_base_of_v<std::exception, std::runtime_error>`）；
- 结构化绑定、聚合初始化等依赖"无基类"的语言特性，不能用于标准库类（即使它看起来像一个简单的结构体）；
- ¶3.3 保证 `std::ios_base::failure` 与 `std::system_error` 是不同类型（尽管前者派生自后者）。

¶4 保证了你可以派生自 `std::vector`、`std::function`、`std::exception` 等（本机 libc++ 中 `std::is_final_v<std::vector<int>>` 为 `false`）。是否**应该**这样做是另一个问题——见 [[derived.classes]] 关于非虚析构函数的讨论。

## 异常处理的限制（[res.on.exception.handling]）

¶1 C++ 标准库中定义的任何函数，都可以通过抛出其 *Throws:* 段落中描述的类型的异常、或者派生自 *Throws:* 段落所命名类型的、会被该基类型的处理器（[[except.handle]]）捕获的类型的异常，来报告失败。

¶2 来自 C 标准库的函数不得抛出异常，除非该函数调用了一个抛出异常的程序提供的函数。脚注：即 C 标准库函数都可以被视为标记了 `noexcept`，这允许实现基于运行期没有异常进行性能优化；`qsort()` 和 `bsearch()`（[alg.c.library]）满足"调用程序提供的函数"这一条件。

¶3 C++ 标准库中定义的析构操作不得抛出异常。标准库中的每个析构函数都必须表现得如同具有**不抛出的异常规范**（[[except.spec]]）。

¶4 标准库中定义的、没有 *Throws:* 段落但具有**潜在抛出**的异常规范的函数，可以抛出**实现定义**的异常。脚注：特别地，它们可以通过抛出 `bad_alloc` 或其派生类型的异常来报告分配存储失败。实现**应当**通过抛出标准异常类（[bad.alloc]、[support.exception]、[std.exceptions]）或其派生类的异常来报告错误。

¶5 实现可以通过添加不抛出的异常规范来**加强**非虚函数的异常规范。

| 你能依赖的 | 你不能依赖的 |
|---|---|
| 抛出的异常类型是 *Throws* 列出的类型或其派生类 | 具体抛出的是哪个派生类 |
| 标准库析构函数不抛 | `noexcept(f())` 对某个非 `noexcept` 声明的标准函数一定为 `false`（¶5 允许加强） |
| C 库函数不抛（`qsort`/`bsearch` 回调抛出时除外） | 没有 *Throws* 的潜在抛出函数只抛 `bad_alloc` |

¶5 的典型应用就是 libc++ 给 `vector::operator[]` 加上了 `noexcept`（见 [[description]] 的实现视角）：

```cpp run ok
#include <vector>
std::vector<int> v;
// 标准中 vector::operator[] 没有声明 noexcept；libc++ 按 ¶5 加强了它
static_assert(noexcept(v[0]));   // 本机 libc++ 成立——但不可移植
int main() { }
```

（这段代码"能编译"只说明本机实现的选择；在不加强异常规范的实现上，`static_assert` 会失败。）

¶5 只适用于**非虚**函数：给虚函数加 `noexcept` 会使用户的覆盖函数（没有 `noexcept`）变得非良构（[[except.spec]] 要求覆盖函数的异常规范不弱于被覆盖者）。

## 契约断言（[res.contract.assertions]）{{c++26}}

¶1 除非另有规定，实现**可以**使用契约断言（[[basic.contract]]、[[structure.specifications]]）检查标准库函数规定的前置条件和后置条件。

这是 [[structure.specifications#3.4]] Example 3 的规范授权：实现可以在 `std::vector::front()` 中写 `pre(!empty())`。注意它是"**可以**"——检查与否、以何种求值语义（ignore / observe / enforce / quick-enforce）检查，都由实现决定；违反前置条件在标准层面仍然是 UB。只有 *Hardened preconditions* 在加固实现中被**要求**以终止语义检查。

## 错误码的值（[value.error.codes]）

¶1 标准库中某些函数通过 `error_code` 对象（[syserr.errcode.overview]）报告错误。对于**源自操作系统**的错误，该对象的 `category()` 必须返回 `system_category()`；对于源自其他地方的错误，返回对某个实现定义的 `error_category` 对象的引用。实现必须为每个这样的错误类别定义 `value()` 的可能取值。Example 1：对于基于 POSIX 的操作系统，实现应当把 `std::system_category()` 的值定义为与 POSIX `errno` 值相同，并加上操作系统文档定义的附加值；对于非 POSIX 系统，应当与操作系统自身的值相同。

所以 `std::filesystem` 操作失败时，`ec.category() == std::system_category()`，`ec.value()` 在 Linux/macOS 上就是 `errno` 值（如 `ENOENT`）——要做可移植的比较，应该与 `std::errc::no_such_file_or_directory`（一个 `error_condition`）比较，而不是比较数值。

## 标准库类型的移出状态（[lib.types.movedfrom]）

¶1 C++ 标准库中定义的类型的对象可以被移动（[[class.copy.ctor]]）。移动操作可以是明确规定的，也可以是隐式生成的。除非另有说明，这样的**移出对象**处于**有效但未指明的状态**（valid but unspecified state，[intro.defs]）。

¶2 标准库中定义的类型的对象可以被**移动赋值给自身**（[[class.copy.assign]]）。除非另有说明，这样的赋值使对象处于有效但未指明的状态。

**有效但未指明**的意思是：对象的不变式仍然成立，所有**没有前置条件**的操作都可以安全调用；但你不知道它的值。

```cpp run ok
#include <string>
#include <utility>
#include <vector>
int main() {
  std::vector<int> a{1, 2, 3};
  std::vector<int> b = std::move(a);
  [[maybe_unused]] auto n = a.size();  // OK：无前置条件，返回某个值（实践中为 0，但标准不保证）
  a.clear();         // OK：无前置条件，之后 a.empty() 为 true——状态重新变得已知
  a.push_back(4);    // OK
  // a.front();      // 不行（在 clear 之前）：front() 有前置条件 !empty()，而 a 的值未知

  std::string s = "hello";
  std::string& r = s;
  s = std::move(r);  // ¶2：自移动赋值，s 处于有效但未指明的状态（不是 UB）
  s = "again";       // OK
  return a.size() == 1 && s == "again" ? 0 : 1;
}
```

"除非另有说明"的例外不少，而且都是**更强**的保证：`std::unique_ptr`、`std::shared_ptr` 移出后为空；`std::optional<T>` 移出后**仍然有值**（值本身是 `T` 的移出状态）；`std::thread`、`std::unique_lock`、`std::promise` 等移出后不再关联任何东西；`std::basic_string`、`std::vector` 的移动**构造**（而非赋值）后，源对象在实践中为空，但标准只对少数情况作了规定。

## 思考题

!!! question "思考题 1"
    实现 A 的 `<algorithm>` 包含了 `<string>`，实现 B 没有。程序 `#include <algorithm>` 后使用了 `std::string`。在实现 A 上它是良构的吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

不是。[res.on.headers] ¶1 允许实现 A 这样做，但 `<algorithm>` 的 synopsis 并不显示包含 `<string>`，所以程序不能依赖它。[[using.headers#3]] 要求在引用 `std::string` 之前包含声明它的头文件（`<string>`），违反者 IFNDR——在实现 A 上"恰好能编译"是 IFNDR 的典型表现。
</details>

!!! question "思考题 2"
    一个线程在调用 `std::vector<int>::size() const`，另一个线程同时调用同一个对象的 `std::vector<int>::data()`（非 const 重载）。有数据竞争吗？

<details markdown="1">
<summary>展开查看答案与解析</summary>

调用非 const 的 `data()` 在**库的层面**算"通过非 const 实参访问"，[res.on.data.races] ¶3 允许它修改对象。但 [container.reqmts] 的数据竞争条款专门规定：为避免数据竞争，`begin`、`end`、`data`、`find`、`at`（关联容器除外的）`operator[]` 等函数应被视为 const 的——即使调用的是非 const 重载。所以两者都只是"读"，不冲突，没有数据竞争。若改为 `push_back`，则构成冲突，按 [[res.on.objects]] 为 UB。
</details>

## 小结

!!! summary "实现的义务（可以依赖）vs 实现的自由（不能依赖）"
    | 可以依赖 | 不能依赖 |
    |---|---|
    | 头文件提供其 synopsis（含其中列出的包含） | 其他任何传递包含 |
    | 合法调用总是选中标准规定的非成员重载；非成员不加默认实参 | 函数是否 inline；成员函数的签名集合 |
    | 库内部对非运算符函数不做 ADL；运算符做 ADL | 能否取地址 / 成员指针的类型 |
    | 规定为友元的函数只能经 ADL 找到 | 标准类之间是否互为友元 |
    | 实现不擅自添加 constexpr | 实现已经实现了所有要求的 constexpr |
    | "stable" 的精确含义 | 哪些函数可递归重入 |
    | const 并发调用安全；不同对象并发安全；库不暗中共享状态 | 库内部是否用线程池（只要无可见副作用） |
    | 规定为虚的基类是虚的，规定为非虚的不是；类型非 final | 是否有额外的（保留名字的）基类；是否可平凡复制 |
    | 只抛 *Throws* 中的类型或其派生类；析构不抛；C 函数不抛 | `noexcept` 运算符对非 noexcept 声明的结果 |
    | OS 错误使用 `system_category()` | 错误码的具体数值 |
    | 移出对象有效、可赋值、可调用无前置条件的操作；自移动赋值不是 UB | 移出对象的值 |
