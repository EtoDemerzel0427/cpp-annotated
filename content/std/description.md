---
title: 描述方法：如何读懂库条文
summary: 库函数的规范由一串带标签的要素组成，Constraints、Mandates、Preconditions、Hardened preconditions 等标签各自决定违反时是退出重载、编译错误、未定义行为还是终止；Equivalent to 后面的代码怎样解读；Cpp17 命名要求与库概念的区别。
status: done
covers: description.general, structure, structure.elements, structure.summary, structure.requirements, structure.specifications, structure.see.also
papers: P0788R3, P3471R4, P2900R14
related: library, conventions, requirements, utility.requirements, res.on.requirements, intro.compliance, intro.defs, basic.contract, temp.constr, conforming
tags: 库, 阅读方法, Constraints, Mandates, Preconditions, 加固, UB
updated: 2026-10-19
---

!!! tldr
    - 库函数的条件写在哪个标签下，决定了违反它的后果：*Constraints* 让函数退出重载决议，*Mandates* 让程序非良构，*Preconditions* 是未定义行为。
    - *Hardened preconditions* 在加固实现中一定会被检查，违反时程序终止；在非加固实现中仍是未定义行为。
    - `requires` 表达式和类型萃取只能看见 *Constraints*，看不见 *Mandates*。
    - *Effects: Equivalent to* 后面的代码描述的是效果，不是实现方式；代码里各个调用的前置条件、异常等规范会一起传递过来。
    - 斜体的 *Cpp17Xxx* 是写在表格里的文字要求，等宽的 `xxx` 是真正的 C++ 概念，两者并不等价。

## 同一个条件，三种后果

```cpp run ok
#include <algorithm>
#include <functional>
#include <tuple>
#include <type_traits>
#include <vector>

// 1. std::function 的构造函数：可调用性写在 Constraints 里
static_assert(!std::is_constructible_v<std::function<void()>, int>);

// 2. std::get<T>：T 只出现一次写在 Mandates 里
std::tuple<int, int> t;
static_assert(requires { std::get<int>(t); });   // 检测说能调用

// 3. std::lower_bound：范围已划分写在 Preconditions 里
int f(std::vector<int>& v) {
  return *std::lower_bound(v.begin(), v.end(), 2);
}
int main() {}
```

三个库函数都对调用提出了条件，后果却完全不同：

- `std::function<void()>` 不能从 `int` 构造，类型萃取如实报告 `false`，没有任何错误。
- `std::get<int>` 用在 `tuple<int, int>` 上是错的，`requires` 表达式却报告可以调用。真正写出 `std::get<int>(t)` 时，本机 libc++ 报 static_assert 失败："type occurs more than once in type list"。
- `f` 传入未排序的 `vector` 时编译器什么也不说，运行结果没有任何保证。

差别来自条件写在函数规范的哪个标签下。核心语言用语法和语义规则说话，库条款则给每个函数列出一串带斜体标签的**要素**（element），每种标签都有固定的含义。[description] 就是这套写法的图例，第 17–33 章（[[support]] 到 [[exec]]）和附录 [[depr]] 都按它来读。

## 函数规范的要素 [structure.specifications]

¶3 函数语义的描述按需要包含下列要素，不适用的直接省略（没有前置条件的函数就没有 *Preconditions*）。前五项说的是调用要满足什么条件，后面各项说的是实现承诺做什么：

| ¶ | 要素 | 内容 | 不满足时 |
|---|---|---|---|
| 3.1 | *Constraints* | 函数参与重载决议的条件 | 函数不可行，静默退出候选集 |
| 3.2 | *Mandates* | 不满足就使程序非良构的条件 | {{ill-formed}}，必须诊断 |
| 3.3 | *Constant When* | 调用成为常量子表达式的条件 | 调用不能在编译期求值 |
| 3.4 | *Preconditions* | 调用时函数假定成立的条件 | {{ub}} |
| 3.5 | *Hardened preconditions* | 同上，加固实现中会检查 | 加固实现：终止；否则 {{ub}} |
| 3.6 | *Effects* | 函数执行的动作 | |
| 3.7 | *Synchronization* | 适用的同步操作 | |
| 3.8 | *Postconditions* | 函数建立的条件 | |
| 3.9 | *Result* | 类型名的含义，或表达式的类型与值类别 | |
| 3.10 | *Returns* | 返回值 | |
| 3.11 | *Throws* | 抛出的异常及其条件 | |
| 3.12 | *Complexity* | 时间和空间复杂度（上界） | |
| 3.13 | *Remarks* | 其他语义约束 | |
| 3.14 | *Error conditions* | 通过错误码报告的错误 | |

### *Constraints*：不满足就退出重载决议（¶3.1）

!!! std
    *Constraints*: the conditions for the function's participation in overload resolution.

¶3.1 [[g:constraints-element|*Constraints*]] 是函数参与重载决议的条件。注 1 说明，不满足时函数静默地不可行（silent non-viability）：它只是从候选集里消失，不算错误。例 1 指出实现可以用 `requires` 子句表达这种条件；C++20 之前的实现用 `enable_if`，效果相同。

因为不算错误，这种条件可以被探测。`is_constructible`、`is_invocable`、`is_convertible` 这些类型萃取和 `requires` 表达式都能看见它，结果为 `false`；如果还有别的候选，重载决议直接选别的。

```cpp run ok
#include <memory>
template<class T>
concept can_make_unique = requires { std::make_unique<T>(); };
static_assert( can_make_unique<int>);
static_assert(!can_make_unique<int[3]>);
int main() {}
```

`make_unique<int[3]>()` 的情形是另一种写法。标准给已知边界的数组专门声明了一个删除的重载，它的 *Constraints* 是 T is an array of known bound。这个重载参与重载决议并被选中，然后因为是删除函数而使调用非良构，`requires` 表达式也就得到 `false`。下一节例 2 讲的正是这种技巧。

### *Mandates*：不满足就是编译错误（¶3.2）

!!! std
    *Mandates*: the conditions that, if not met, render the program ill-formed.

¶3.2 [[g:mandates-element|*Mandates*]] 不满足时程序非良构，编译器必须诊断。例 2 给出两种实现手段：

1. 在函数体里写 `static_assert`，这是最常见的做法；
2. 如果希望在重载决议选中这个函数之后才报错，就写成约束表达式，同时把函数定义为删除的。

用 `static_assert` 实现时，*Mandates* 不影响重载决议。类型萃取和 `requires` 表达式只检查声明，而 `static_assert` 在函数体里，只有函数体被实例化时才触发，这已经不在替换失败可以静默处理的范围内（[[temp.deduct]]）。所以开头的 `requires { std::get<int>(t); }` 得到 `true`，真正调用时才出错。

<div class="compare" markdown="1">

```cpp run ok
#include <tuple>
std::tuple<int, int> t;
// requires 表达式看不到 Mandates
static_assert(requires { std::get<int>(t); });
```

```cpp run error
#include <tuple>
std::tuple<int, int> t;
// error: Mandates 不满足，int 出现两次
int x = std::get<int>(t);
```

</div>

!!! tip "为什么不全都写成 Constraints"
    *Constraints* 适合在几个重载之间分派，例如 `optional<T>` 的几个构造函数按 `T` 能否从 `U` 构造、能否隐式转换来选择。*Mandates* 适合调用本身就写错了的场合：如果 `get<int>` 静默消失，用户只会看到 no matching function，远不如一句类型出现了不止一次清楚。把条件放进签名还会增加编译开销，也可能引起不想要的递归约束检查。

### *Preconditions*：违反就是未定义行为（¶3.4）

!!! std
    *Preconditions*: conditions that the function assumes to hold whenever it is called; violation of any preconditions results in undefined behavior.

¶3.4 [[g:preconditions-element|*Preconditions*]] 是调用者负责保证的条件，函数不必检查。违反任何一条前置条件，行为就是未定义的。例 3 提到实现可以用契约断言（如 `pre`，[[dcl.contract.func]]）表达其中一部分，[[res.contract.assertions]] 也允许这样做；但在标准层面，不管实现查不查，违反了就是 UB。

```cpp run ub
#include <algorithm>
#include <vector>
int main() {
  std::vector<int> v{3, 1, 2};   // 未排序
  // [lower.bound]：范围必须关于 e < value 划分好
  auto it = std::lower_bound(v.begin(), v.end(), 2);  // UB
  return *it;
}
```

二分查找本身不会越界，所以这段代码实际上总会返回某个位置，本机运行返回 2。但标准对结果不作任何要求，编译器也可以假定前置条件成立并据此优化。

前置条件一般涉及运行时的值：指针非空、下标在范围内、范围已排序。编译器无法静态判定这些条件，所以它们不能写成 *Constraints* 或 *Mandates*，后两者只涉及类型和编译期性质。

### *Hardened preconditions*：加固实现会检查（¶3.5）{{c++26}}

¶3.5 [[g:hardened-precondition|*Hardened preconditions*]] 同样是调用时函数假定成立的条件，区别在于违反时的后果取决于实现是否加固。**加固实现**（hardened implementation）是标准库会检查这类条件的实现，一个实现是否加固由实现定义（[[intro.compliance#8]]），实践中通常是一个编译选项。

- ¶3.5.1 在加固实现中，函数产生任何其他可观察副作用之前，以加固前置条件为谓词的契约断言会以终止语义求值（[[basic.contract.eval]]）。终止语义指 enforce 或 quick-enforce：检查失败后程序终止，不会继续执行。
- ¶3.5.2 在非加固实现中，违反加固前置条件是未定义行为。

标为加固前置条件的大多是防止越界访问的条件，例如序列容器的 `a[n]` 要求 `n < a.size()`，`optional::operator*` 要求 `has_value()`，`span::operator[]` 要求下标在范围内。越界访问是内存安全漏洞最主要的来源，加固实现保证它不会悄悄发生。

```cpp run ub
#include <cstdio>
#include <vector>
int main(int argc, char**) {
  std::vector<int> v{1, 2, 3};
  if (argc > 1)
    std::printf("%d\n", v[3]);  // 非加固实现：UB；加固实现：终止
}
```

本机 libc++ 带一个参数运行：默认配置下什么也不检查，直接读越界内存；加 `-D_LIBCPP_HARDENING_MODE=_LIBCPP_HARDENING_MODE_FAST` 后进程收到 `SIGTRAP`（退出码 133）；换成 `_LIBCPP_HARDENING_MODE_DEBUG` 则先打印 `libc++ Hardening assertion __n < size() failed` 再 abort。

加固实现还要定义 `__cpp_lib_hardened_vector`、`__cpp_lib_hardened_optional` 等一组特性测试宏（[[version.syn#3]]），代码可以据此判断自己是否运行在加固实现上。加固由 [[P3471R4]] 引入 C++26，它和契约（[[P2900R14]]）是一起设计的，所以违反时的处理方式与用户自己写的 `pre` 断言相同。

### *Constant When*：能否在编译期调用（¶3.3）

¶3.3 *Constant When* 规定调用成为常量子表达式（[[defns.const.subexpr]]）所需的条件。它用于这样的函数：函数本身是 `constexpr` 的，但不是每次调用都能在编译期完成。例如 `std::bit_cast` 的规范写着：

!!! std
    *Constant When*: Neither `To` nor `From` has constexpr-unknown representation.

也就是说，涉及的类型如果含有指针、联合体、引用成员这类编译期无法确定位模式的部分（[[expr.const]]），这次调用就不是常量子表达式，在要求常量表达式的地方使用它是非良构的。

它和 *Mandates* 的区别是：*Constant When* 不满足时，调用在运行期照样合法，只是不能在编译期求值。另一种写法是 *Constant When*: Preconditions are met，意思是在常量求值中违反前置条件不会成为 UB，而是让表达式不再是常量表达式，编译器必须报错。这与核心语言在常量求值中不允许 UB 的设计一致。*Constant When* 是 C++23 之后的新措辞。

### 实现的承诺（¶3.6–¶3.14）

¶3.6 *Effects* 描述函数执行的动作。最常见的写法是 *Effects*: Equivalent to 加一段代码，解读规则见下一节。

¶3.7 *Synchronization* 描述函数涉及的同步操作（[[intro.multithread]]）。例如 `std::thread` 构造函数的 *Synchronization* 说，构造函数调用的完成与 `f` 副本调用的开始同步（synchronizes with）。库函数之间有没有先后关系，要看这个要素。

¶3.8 *Postconditions* 描述函数返回后一定成立的条件，例 4 指出实现可以用 `post` 断言表达它们。

¶3.9 *Result* 用于类型名或表达式：对类型名，它说明所命名的类型；对表达式，它给出类型，值类别由类型推出，左值引用类型是左值，右值引用类型是 xvalue，否则是 prvalue（[[topics/value-categories]]）。它主要出现在要求表格里，例如 [[allocator.requirements]] 中 `a.allocate(n)` 的 *Result* 是 `XX::pointer`。

¶3.10 *Returns* 描述返回值。¶3.11 *Throws* 描述抛出的异常和抛出的条件。常见措辞的确切含义如下：

| 措辞 | 含义 |
|---|---|
| *Throws*: Nothing. | 不抛异常，但不等于声明了 `noexcept`（见下文常见误解） |
| *Throws*: `out_of_range` if `pos > size()`. | 抛 `out_of_range` 或它的派生类（[[res.on.exception.handling#1]]） |
| *Throws*: Any exception thrown by the constructor of `T`. | `T` 的构造函数抛什么，这里就透传什么 |
| 没有 *Throws*，函数也不是 `noexcept` | 可以抛实现定义的异常（[[res.on.exception.handling#4]]），典型是 `bad_alloc` |

¶3.12 *Complexity* 给出时间或空间复杂度。¶7 说明这些都是上界，做得更好的实现也符合要求；¶6 规定公式算出负数次操作时按零次算，于是至多 `N - 1` 次比较这类写法在 `N == 0` 时不必另作说明。标准计数的是比较、谓词调用、赋值之类的操作，不是机器指令或时间。例如 `std::lower_bound` 至多做 log₂(last − first) + O(1) 次比较，但对非随机访问迭代器，移动迭代器的次数可以是线性的。

¶3.13 *Remarks* 收纳其他语义约束，常见的有：异常规范的确切条件（对应 synopsis 里的 `noexcept(see below)`）、`explicit(see below)` 的条件、构造函数何时平凡或何时是 `constexpr` 的，以及少数旧式的 This function shall not participate in overload resolution unless …，它的意思等同于 *Constraints*。

¶3.14 *Error conditions* 列出函数通过错误码报告的错误。¶8 补充，这些条件以 `enum class errc` 的常量给出（[[syserr]]）。例如 `std::mutex::lock()` 的错误条件包括 `resource_deadlock_would_occur` 和 `operation_not_permitted`。

## Equivalent to 怎么读（¶4）

库规范里最常见的一句话是 *Effects*: Equivalent to 后接一段代码。以 [utility.exchange] 为例：

```cpp
template<class T, class U = T>
  constexpr T exchange(T& obj, U&& new_val) noexcept(see below);
// Effects: Equivalent to:
//   T old_val = std::move(obj);
//   obj = std::forward<U>(new_val);
//   return old_val;
// Remarks: The exception specification is equivalent to:
//   is_nothrow_move_constructible_v<T> && is_nothrow_assignable_v<T&, U>
```

¶4 规定，函数 F 的语义按下面的顺序确定：

1. F 自己的 *Constraints* 和 *Mandates* 先施加。
2. 代码序列的语义，由其中每个函数调用的全部要素（*Constraints*、*Mandates*、*Preconditions*、*Effects*、*Throws*、*Complexity* 等）决定。被调函数的规范整个传递过来。
3. 返回值由 F 的 *Returns* 决定；F 没有 *Returns* 时，由代码里的 `return` 语句决定。
4. F 自己如果有 *Throws*、*Postconditions* 或 *Complexity*，就以 F 的为准，覆盖代码中各调用的同名要素。

对 `exchange` 应用这几条：它的前置条件和可能抛出的异常，就是 `T` 的移动构造和 `T&` 从 `U` 赋值的前置条件和异常；它没有自己的 *Throws*，所以不覆盖；返回值由 `return old_val;` 决定。

[[structure.requirements#7]] 说明，以代码给出的语义只规定等价性，不规定实现方式。不过代码的写法本身也有后果：

- 代码里写出的拷贝、移动、临时对象都是语义的一部分。等价代码写 `return T(x);`，就意味着对 `T` 的拷贝构造函数有要求。
- 代码里的非限定名按声明处的非限定查找解释，不做实参依赖查找（ADL），`swap` 等少数名字除外（[[contents#3]]）。所以代码里的 `move` 就是 `std::move`。
- Equivalent to: `return f(args...);` 不意味着 F 与 `f(args...)` 有相同的 `noexcept`，异常规范要看 synopsis 和 *Remarks*。

还有两种相近的说法。as if 比 equivalent to 宽松，通常配一段说明性代码描述效果，不精确地传递全部要素。**表达式等价**（expression-equivalent，[[defns.expression.equivalent]]）更强：两个表达式效果相同，并且要么都可能抛出、要么都不抛出，要么都是常量子表达式、要么都不是。定制点对象和范围适配器（[[conventions]]）大量使用这种说法。

!!! lawyer "Equivalent to 代码里的 UB 也算在 F 头上"
    如果 F 的 *Effects* 等价于一段代码，而代码中某个调用的前置条件被违反，调用 F 就违反了前置条件，即使 F 自己没有 *Preconditions* 要素。

## 对用户类型的要求 [structure.requirements]

函数规范管的是一次调用。库对用户写的类型还有另一类要求：把自己的类型放进 `std::vector<T>`，给 `std::sort` 传比较器，从 `std::streambuf` 派生，或者写一个迭代器交给标准算法，这些类型都要满足库规定的条件。

¶1 这类要求就是 Requirements 子条款的内容，它约束扩展标准库的程序。扩展通常是三种之一：模板实参（¶1.1）、派生类（¶1.2）、满足某种接口约定或建模某个概念的容器、迭代器和算法（¶1.3）。违反的后果见 [[res.on.functions#2.3]]（UB）和 [[res.on.requirements]]。

### 要求的是表达式，不是成员（¶3–¶4）

¶3 接口要求尽量写得宽泛。标准不说类 `X` 必须定义成员函数 `operator++()`，而说对 `X` 类型的任意对象 `x`，`++x` 有定义。所以运算符是不是成员是未指明的。

对用户来说，迭代器的 `++it` 用成员函数、非成员函数、隐藏友元还是继承来的成员实现都可以。对库实现来说，它也只能以表达式的形式使用你的类型，写 `++it`，而不写 `it.operator++()`。

¶4 每一组这样的表达式要求，要么对应一个具名的概念，要么对应一张表格，列出有效表达式和它们的语义。泛型算法（[[algorithms]]）用模板形参的有效表达式来描述。

### *Cpp17Xxx* 与库概念（¶5）

¶5 库规范用排版区分两种命名要求：

| 写法 | 指什么 | 例子 |
|---|---|---|
| 斜体，以 *Cpp17* 开头 | 以表格给出的表达式要求，可能附带文字说明（[[g:cpp17-named-requirement]]）；编译器不知道它们 | *Cpp17Destructible*（[[utility.arg.requirements]]）、*Cpp17InputIterator* |
| 等宽字体 | 库概念，用 `concept` 定义（[[temp]]），可能附带文字说明的语义要求 | `destructible`、`input_iterator` |

C++20 引入概念库时，许多旧的命名要求与新概念同名但含义不同，于是旧的表格式要求统一加上了 *Cpp17* 前缀。两者并不等价。例如 *Cpp17InputIterator* 要求 `iterator_traits` 里的嵌套类型齐全、可以比较相等，而 `input_iterator` 概念不要求迭代器可拷贝、也不要求能比较相等。一个迭代器可以建模 `std::input_iterator` 却不满足 *Cpp17InputIterator*，反过来也可能。

### 必需操作不必对所有值有定义（¶8）

¶8 概念的必需操作（required operations）不必是全函数：某些实参可能使必需的语义不成立。标准的例子是，`totally_ordered` 要求的 `<` 在 NaN 上不满足这个概念的语义，但这不影响类型是否建模该概念。

如果因为存在 NaN 就说 `double` 不建模 `totally_ordered`，`std::ranges::sort` 就不能用于 `double` 了。¶8 的意思是，建模概念的是类型；具体的值是否落在必需操作有意义的范围内，是每次调用要满足的条件。

```cpp run ok
#include <algorithm>
#include <concepts>
#include <vector>
static_assert(std::totally_ordered<double>);    // 类型层面成立
int main() {
  std::vector<double> v{3.0, 1.0, 2.0};
  std::ranges::sort(v);    // OK：没有 NaN
  return v.front() == 1.0 ? 0 : 1;
}
```

如果 `v` 里有 NaN，`<` 不再构成严格弱序，这次 `sort` 违反了它的语义要求，行为未定义。但这是这一次调用的问题，不是 `double` 这个类型的问题。

### 约束里的概念还带着语义要求（¶9）

¶9 声明可以通过关联约束（[[temp.constr.decl]]）施加要求。约束引用了某个概念时，这个概念的语义要求也一并施加在对该声明的使用上。

所以库函数模板写着 `template<std::regular T>`，意思不只是编译器检查 `regular<T>` 得到**满足**（satisfied，语法层面成立），还要求 `T` **建模**（models）`regular`，即满足所有文字描述的语义要求，比如 `==` 是等价关系、拷贝之后两者相等。编译器只能检查前者；后者不成立时程序非良构，不要求诊断（[[res.on.requirements#3]]）。

## 替换函数的必需行为与默认行为（¶5）

¶5 对于程序可以替换的函数（如全局 `operator new`）和处理函数（如 `new_handler`），[[support]] 分别规定两种行为：

- **默认行为**（default behavior）：实现提供的那个定义做什么；
- **必需行为**（required behavior）：不管定义由实现还是由程序提供，都必须具备的语义。

没有明确区分时，描述的是必需行为。例如全局 `operator new(size_t)` 的必需行为是返回指向至少 `size` 字节、适当对齐的存储的非空指针，或者抛出 `bad_alloc`。它的默认行为更具体：循环尝试分配，失败时如果当前 new_handler 为空就抛 `bad_alloc`，否则调用它然后重试。替换它时只需满足必需行为，否则是 UB（[[res.on.functions#2.1]]）。详见 [[constraints]]。

## 实现视角

三个主流标准库落实这些要素的方式大同小异：

| 要素 | libc++ | libstdc++ | MSVC STL |
|---|---|---|---|
| *Constraints* | `requires`，旧模式用 `enable_if` | `requires` / `enable_if` / `_Require<...>` | `enable_if_t` / `requires` |
| *Mandates* | `static_assert` | `static_assert` | `static_assert` |
| *Preconditions* 与加固检查 | `_LIBCPP_ASSERT_*` 宏族，由 `_LIBCPP_HARDENING_MODE`（none / fast / extensive / debug）决定启用哪些 | `__glibcxx_assert`，由 `_GLIBCXX_ASSERTIONS` 启用 | `_STL_VERIFY` 等，受 `_ITERATOR_DEBUG_LEVEL` 等开关控制 |

libc++ 的检查宏按类别划分（`_LIBCPP_ASSERT_VALID_ELEMENT_ACCESS`、`_LIBCPP_ASSERT_NON_NULL` 等），fast 模式只开启安全相关、常数时间的检查。本机 `vector::operator[]` 的实现是这样的：

```cpp
reference operator[](size_type __n) _NOEXCEPT {
  _LIBCPP_ASSERT_VALID_ELEMENT_ACCESS(__n < size(), "vector[] index out of bounds");
  return this->__layout_.__begin_ptr()[__n];
}
```

标准的 `vector::operator[]` 没有 `noexcept`，libc++ 用 [[res.on.exception.handling#5]] 的许可加上了它。这不妨碍加固检查，因为检查失败时是 trap 或 abort，不是抛异常。libc++ 还提供 `_LIBCPP_ASSERTION_SEMANTIC`，取值 ignore / observe / quick-enforce / enforce，与契约的四种求值语义一一对应。

## 历史与演进

!!! history
    - C++17 及以前，函数规范里有一个 *Requires:* 要素，含义并不统一：有时表示违反即 UB，有时表示违反即非良构，有时又被理解成不满足就不参与重载决议。最后一种另有固定说法，写在 *Remarks* 里：This function shall not participate in overload resolution unless …。
    - C++20 的 [[P0788R3]] 把 *Requires:* 拆成含义明确的 *Constraints:*、*Mandates:* 和 *Expects:*（前置条件），并引入 *Ensures:*；之后一系列提案逐章改写了全部库条款。C++20 定稿前，*Expects:* 和 *Ensures:* 改称 *Preconditions:* 和 *Postconditions:*。同一时期，旧的表格式命名要求加上了 *Cpp17* 前缀。
    - C++26 的 [[P3471R4]] 引入标准库加固和 *Hardened preconditions*；[[P2900R14]] 引入契约，使 ¶3.4 的例 3 和 ¶3.5.1 有了语言层面的依据。*Constant When* 是 C++23 之后的新措辞。

## 常见误解

!!! pitfall "以为 Preconditions 会被检查"
    违反 *Preconditions* 是 UB，标准从不要求检查。对空容器调用 `front()`、对未排序范围调用 `binary_search`，在非加固实现上都可能看起来一切正常。只有 *Hardened preconditions* 在加固实现中才保证检查。

!!! pitfall "用 requires 表达式探测 Mandates"
    `requires { std::get<T>(t); }` 和 `std::is_invocable_v<...>` 只能探测 *Constraints*。依赖它们判断 *Mandates* 是否满足，会得到错误的肯定答案，然后在真正调用时遇到编译错误。

!!! pitfall "*Throws*: Nothing 等于 noexcept"
    *Throws*: Nothing 是行为上的承诺。函数如果有前置条件，标准通常有意不把它声明为 `noexcept`（这一惯例常被称为 Lakos 规则），好让调试型实现在前置条件被违反时抛异常，便于测试。所以 `noexcept(v[0])` 的结果因实现而异：本机 libc++ 为 `true`，因为它加强了异常规范。可移植代码不要依赖它。

!!! pitfall "把 Complexity 当成性能保证"
    *Complexity* 是上界，而且只计数特定操作，不约束内存分配次数和缓存行为。`std::unordered_map::find` 平均常数、最坏线性，这两点都写在 *Complexity* 里。

## 思考题

!!! question "思考题 1"
    `std::optional<T>` 的转换构造函数 `template<class U = T> constexpr explicit(see below) optional(U&& v);` 把 `is_constructible_v<T, U>` 等条件写在 *Constraints* 里。如果改写在 *Mandates* 里，`std::is_convertible_v<int, std::optional<std::string>>` 会是什么？对重载决议有什么影响？

<details markdown="1">
<summary>答案</summary>

写在 *Constraints* 里时，`std::string` 不能从 `int` 构造，这个构造函数不参与重载决议，`is_convertible_v<int, optional<string>>` 为 `false`。

改成 *Mandates*（函数体里的 `static_assert`）后，构造函数总是参与重载决议，`is_convertible_v` 只看声明，会得到 `true`；写 `std::optional<std::string> o = 42;` 时才在实例化中出错。重载决议也会受影响：同时有 `f(std::optional<std::string>)` 和 `f(std::optional<int>)` 时，`f(42)` 现在只能选后者；改写之后两个都是可行的用户定义转换，调用变成歧义。这正是 ¶3.1 和 ¶3.2 区分两种要素的原因。
</details>

!!! question "思考题 2"
    在非加固实现上，`std::optional<int> o; int x = *o;` 是什么行为？在加固实现上呢？如果契约违反处理函数直接返回，又会怎样？

<details markdown="1">
<summary>答案</summary>

`optional::operator*` 的加固前置条件是 `has_value()` 为 `true`（[[optional.observe]]）。

非加固实现上，按 ¶3.5.2，行为未定义。加固实现上，按 ¶3.5.1，在任何其他副作用之前以终止语义检查 `has_value()`，结果为假，发生契约违反。enforce 语义下先调用违反处理函数，处理函数正常返回后程序仍然以实现定义的方式终止；quick-enforce 语义下不调用处理函数，直接终止（[[basic.contract.eval]]）。无论哪种，都不会继续执行到解引用，处理函数直接返回也没有用。
</details>

!!! question "思考题 3"
    *Effects*: Equivalent to: `return std::invoke(f, args...);` 与 F 的调用 expression-equivalent to `std::invoke(f, args...)` 有什么区别？

<details markdown="1">
<summary>答案</summary>

前者按 ¶4 传递效果、前置条件、返回值、异常等语义，但不保证 F 的 `noexcept` 与 `invoke` 相同，也不保证两者同为或同不为常量子表达式，这些要看 F 自己的 synopsis 和 *Remarks*。`return` 语句本身还会引入一次返回值的初始化。

后者是表达式等价（[[defns.expression.equivalent]]）：效果相同，异常规范一致，能否在编译期求值也一致。它是更强的保证，`noexcept(F(args...))` 这类探测可以得到与 `invoke` 完全相同的结果。
</details>

<details class="fine" markdown="1"><summary>其余条文</summary>

[description.general] ¶1：[description] 描述标准库的规范写法，[structure] 讲每个库条款的结构，[[conventions]] 讲其余的编辑约定。

[structure.elements] ¶1：每个库条款按需要包含概要（Summary）、要求（Requirements）、详细规范（Detailed specifications）和对 C 标准库的引用，不适用的部分省略。以 [[containers]] 为例，[containers.general] 是概要，[container.requirements] 是所有容器共享的要求表格，[sequences]、[associative] 等是各容器的详细规范。

[structure.summary] ¶1–¶2：概要介绍本类别的第一级子条款；每个子条款也有概要，列出它规定的头文件和每个头文件提供的实体，即常见的 header synopsis（如 [utility.syn]）。内容包括宏、值、类型与别名模板、类与类模板、函数与函数模板、对象与变量模板、概念。synopsis 里的声明是规范性的（[[contents#1]]、[[res.on.headers#1]]），其中的 `constexpr`、`noexcept`、`explicit` 也是；实现可以加强 `noexcept`（[[res.on.exception.handling#5]]），不能自行添加 `constexpr`（[[constexpr.functions]]）。`// freestanding`、`// exposition only` 这类注释的含义见 [[conventions]]。

[structure.requirements] ¶2：string 和 iostream 组件用类模板 `char_traits` 显式表达对字符类型的要求。¶6：模板实参的要求有时直接以名字引用，见 [[type.descriptions]]。¶7：以 C++ 代码给出的语义要求只规定等价性；脚注补充说，有时给出的代码明显就是最优实现。

[structure.specifications] ¶1：每个详细规范包含名字与简述、synopsis、对模板实参的限制、类不变式和函数语义。¶2：类成员函数按构造与析构、拷贝移动与赋值、比较运算符、修改器、观察器、非成员函数的顺序描述，所以 [optional.ctor] 在 [optional.assign] 之前。

[structure.see.also] ¶1：标为 See also 的段落指向其他标准的相关部分（[[intro.refs]]），主要是 C 标准，例如 `<cstring>` 之后的 See also: ISO/IEC 9899:2024, 7.26。具体规则见 [[library.c]]。

</details>
