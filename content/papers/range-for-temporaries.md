---
title: 修复范围 for 的临时量（P2718）
summary: C++23 让范围 for 初始化器里的所有临时对象活到循环结束；这项修复为什么拖了十三年，委员会比较过哪些改法，最后的条文改了什么，又留下了哪些没修到的悬垂。
status: draft
order: 20
group: 核心语言
since: c++23
papers: P2718R0, P2644R1, P2012R2, P0936R0, P0614R1, CWG900, CWG1498
related: class.temporary, stmt.ranged, dcl.init.ref, expr.call, diff.cpp20, cpp.predefined, stmt.expand, range.all, topics/dangling-references, topics/ranges-design, topics/object-model, papers/how-to-read-a-paper
tags: 提案, 范围 for, 临时对象, 生命周期, 悬垂, C++23
updated: 2026-10-19
---

!!! tldr
    - C++20 及以前，`for (auto x : make().items())` 中 `make()` 的临时对象在循环开始前就销毁了，`items()` 返回的引用悬空，行为未定义。
    - 原因是范围 for 被定义成一段改写：初始化器先单独初始化一个 `auto&&` 引用，而引用只延长直接绑定到它的那个临时对象。
    - C++23 的 [[P2718R0]] 在 [[class.temporary#7]] 增加了一条特例：初始化器中原本会在完整表达式末尾销毁的临时对象，一律活到循环结束。
    - 委员会没有采用改写成多条声明、改写成 lambda 调用、普遍延长生命周期、靠 `lifetimebound` 标注等方案；选中的方案不引入新的生命周期模型，只改范围 for 自己的保证。
    - 代价是一部分析构变晚，持锁的临时对象会把锁带进循环体。按值形参、普通的 `auto&&` 声明、存进变量的视图仍然会悬垂。

## 问题：没有分号的两条语句

把一个公开的数据成员换成 getter，是再普通不过的重构。下面两段代码只差这一步，左边正确，右边在 C++20 中是未定义行为：

<div class="compare" markdown="1">

```cpp
struct Person {
  std::vector<int> values{1, 2, 3, 4};
};
Person createPerson();

for (int v : createPerson().values)
  use(v);
```

```cpp
class Person {
  std::vector<int> values{1, 2, 3, 4};
public:
  const std::vector<int>& getValues() const
  { return values; }
};
Person createPerson();

for (int v : createPerson().getValues())
  use(v);   // C++20：UB
```

</div>

这个例子来自 [[P2012R2]]，作者说它是自己真实遇到的 bug。要看出差别，得知道范围 for 是怎么定义的。[[stmt.ranged#1]] 规定它等价于一段改写，大致是：

```cpp
{
  auto&& __range = createPerson().getValues();   // 一条独立的声明
  auto __begin = __range.begin();
  auto __end = __range.end();
  for (; __begin != __end; ++__begin) {
    int v = *__begin;
    use(v);
  }
}
```

第一行是一条声明，它的初始化器是一个**完整表达式**（[[g:full-expression|full-expression]]，不是其他表达式一部分的表达式）。完整表达式中创建的临时对象，默认在这个完整表达式求值结束时销毁（[[class.temporary#4]]）。例外是**生命周期延长**（[[g:lifetime-extension|lifetime extension]]）：引用直接绑定到一个临时对象或它的子对象时，临时对象活得和引用一样久（[[class.temporary#6]]）。

左边的 `createPerson().values` 是对临时对象的成员访问，`__range` 绑定到临时 `Person` 的子对象，整个 `Person` 被延长。右边中间隔了一次函数调用，`__range` 绑定的是 `getValues()` 返回的引用所指的对象；编译器不看函数体，不知道它指向哪里，所以不延长任何东西。临时 `Person` 在第一行结束时销毁，`__range` 从循环一开始就悬空。各种延长规则和例外的细节见 [[topics/dangling-references]]。

用一个可以运行的版本对比两种语言版本：

```cpp run title="person.cpp" std=c++20 ub
#include <cstdio>
#include <vector>
class Person {
  std::vector<int> values{1, 2, 3, 4};
public:
  const std::vector<int>& getValues() const { return values; }
};
Person createPerson() { return {}; }
int main() {
  int sum = 0;
  for (int v : createPerson().getValues()) sum += v;
  std::printf("%d\n", sum);
}
```

本机 Clang 23 加 `-fsanitize=address`：`-std=c++20` 报告 `stack-use-after-scope`，`-std=c++23` 正常输出 `10`。C++20 模式下编译器没有任何警告。

[[P2012R2]] 用一个观察说明了这个陷阱为什么特别危险。其他悬垂引用通常要同时出现两样看得见的东西：一个引用声明（`&`、`&&`），一个结束语句的分号。`const auto& s = get().name();` 两样都有，读者至少有机会起疑。范围 for 的头部看起来是一个整体，没有分号，也没有写出来的引用，悬垂却发生在它内部。

同样的问题出现在一长串常见写法里。[[P2644R1]] 的对照表列了 `getVector()[0]`、`get<0>(getTuple())`、`getOptionalColl().value()`、`get<string>(getVariant())`、`std::span(getVector().data(), 2)`，以及 `co_await` 一个返回引用的协程：只要初始化器先产生一个临时对象，再经过一次返回引用或返回非拥有视图的调用，C++20 下都会悬空。

### C++20 的绕行写法

C++20 的 [[P0614R1]] 给范围 for 加了 *init-statement*，可以先把对象存进一个具名变量：

```cpp run title="init-statement.cpp" std=c++20 ok
#include <cstdio>
#include <vector>
class Person {
  std::vector<int> values{1, 2, 3, 4};
public:
  const std::vector<int>& getValues() const { return values; }
};
Person createPerson() { return {}; }
int main() {
  int sum = 0;
  for (auto p = createPerson(); int v : p.getValues()) sum += v;
  std::printf("%d\n", sum);
}
```

这能用，但不能解决问题。[[P2012R2]] 给出的理由是：写这一行的人必须先知道陷阱在哪里，而不知道的人正是会踩进去的人；知道的人写了，后来的维护者也可能把它简化回去，重新引入 bug。

## 十三年没有修好

这个问题在 2009 年就作为 [[CWG900]] 提了出来，2012 年的 [[CWG1498]] 又提了一次，被归为重复。CWG900 最初的答复认为，改写中初始化器用来初始化一个引用，所以临时对象会被延长到整个语句。这个答复只考虑了直接绑定到 `__range` 的那一个临时对象，正是问题所在。

2014 年问题转到 EWG（演化工作组，负责语言设计方向）。根据 [[P2012R2]] 引用的会议记录，EWG 希望有人写提案解决，但提出两点顾虑：不要引入新的生命周期模型；临时对象在完整表达式末尾销毁这条规则，本来就是为了比在块末尾销毁更省内存，而且适合 RAII 用法。CWG 在 2017 年表示倾向于接受修改，但认为需要 EWG 先拿主意。

[[P2012R2]] 在 2020–2021 年给出了具体方案，EWG 同意问题需要解决。据 [[P2644R1]] 的说法，在讨论最终措辞时，有人希望等一个更广泛的修复，于是没有通过。到 C++23 即将定稿时，更广泛的方案仍然没人提出，P2644R1 主张回到原来的方案，并指出它不妨碍以后再做更大的修复。CWG 审查后的条文就是 [[P2718R0]]，它在 2022 年 11 月进入 C++23，同时解决了 CWG900。

## 设计空间

### 目标

[[P2012R2]] 想要的效果可以用一组声明来描述：初始化器里每一步的中间结果都像存进了一个变量。

```cpp
// for (auto elem : foo().bar().getValues()) 希望等价于
auto&& tmp1 = foo();            // 延长
auto&& tmp2 = tmp1.bar();       // 延长
auto&& rg   = tmp2.getValues();
// ……然后遍历 rg
```

问题是怎样写成条文。论文列出了三种做法，再加上讨论中出现过的几种，一共是下面这些。

### 改写成多条声明，或者改写成一次函数调用

第一种做法是保留现在的改写，但声明这几条内部声明不是会结束临时对象生命周期的独立语句。第二种做法是把循环改写成一个 lambda 的调用，初始化器作为实参：

```cpp
[&](auto&& rg) {
  auto pos = rg.begin(), end = rg.end();
  for (; pos != end; ++pos) { auto elem = *pos; /* 循环体 */ }
}(foo().bar().getValues());   // 实参中的临时对象活到这次调用结束
```

函数实参中的临时对象活到包含调用的完整表达式结束，所以整个循环都在它们的生命周期之内。[[CWG900]] 在 2017 年的记录里也提过类似的思路：把初始化器当作函数实参来对待。

这个模型很直观，但写成条文麻烦。循环体里的 `return`、`break`、`goto`、`co_yield`、`co_return` 在 lambda 里含义全变了，每一种都要另外规定。[[P2012R2]] 因此没有选它。

### 在临时对象的规则里加一条特例

论文选的是第三种做法：不碰改写，直接在 [[class.temporary]] 列出的特殊销毁时机里再加一种，即范围 for 初始化器里的临时对象活到循环结束。

它的好处正好回应了 EWG 的两点顾虑。没有新的生命周期模型，[[class.temporary]] 里本来就有几种临时对象不在完整表达式末尾销毁的情形；完整表达式末尾销毁的一般规则也没有改，改的只是范围 for 自己给出的保证。

### 普遍延长临时对象的生命周期

更彻底的做法是改一般规则，让引用延长更多的临时对象，比如经过函数调用得到的引用。这类提议以前出现过几次，都被否决了。

[[P2012R2]] 引用了 Stroustrup 的回忆：1980 年代，在 `for` 初始化部分声明的对象一直活到块结束（ARM 里有记载），他起初认为这样更安全，后来因为大量抱怨改了主意。最严重的抱怨是矩阵临时对象活得太久，占用的内存让在 `for` 里初始化变得几乎没法用。今天完整表达式末尾销毁的规则就是这次教训的结果。

### 用标注或警告代替语言改动

[[P0936R0]] 提出给形参或 `*this` 加一个标注（论文里暂称 `lifetimebound`），声明返回值的生命周期依赖于它。有了这个信息，编译器可以选择延长临时对象，或者只发出警告。该论文也把 `for (auto x : reversed(make_vector()))` 列为要解决的场景，但没有决定选哪一种，并提醒说：如果只有部分情形自动延长，悬垂会变得更难从调用处看出来。

Clang 以扩展属性 `[[clang::lifetimebound]]` 的形式提供了警告这一种。[[P2012R2]] 认为警告不能代替修复：标注不在标准里；每个返回成员引用的 getter 都要有人去标；很多项目忽略警告；而且函数体不可见时，编译器分不清 `getName()`（返回成员）和 `getAnswer()`（返回一个 `static` 对象）谁会悬垂，变成错误就会误报。

### 不改语言

最后一种选择是什么也不改，教大家用 *init-statement*，或者另外设计一种新循环。前者的问题前面说过；后者只有在旧的范围 for 被弃用、迫使人改代码时才有效，而弃用最常用的循环语法不现实。

### 对比

| 方案 | 能修好 `make().items()` | 代价或障碍 |
|---|---|---|
| 内部声明不算独立语句 | 能 | 要给改写中的声明开特例，措辞别扭 |
| 改写成 lambda 调用 | 能 | `return`、`goto`、协程语句都要特殊规定 |
| [[class.temporary]] 加一条特例（采用） | 能 | 析构变晚 |
| 普遍延长生命周期 | 能 | 改变所有代码的内存占用和 RAII 行为，以前被否决过 |
| `lifetimebound` 标注 | 只能警告或需逐个标注 | 不在标准里，有漏报和误报 |
| 只推广 *init-statement* | 不能 | 依赖程序员事先知道陷阱 |

## 代价：析构变晚

新规则只推迟析构，不增加任何操作。可观察的变化只在析构有副作用的时候出现。用一个只打印的类型模拟 `std::lock_guard`：

```cpp run title="lock.cpp" ok
#include <cstdio>
#include <vector>
struct Lock {   // 模拟 lock_guard：只打印
  Lock()  { std::printf("lock\n"); }
  ~Lock() { std::printf("unlock\n"); }
};
std::vector<int> snapshot(const Lock&) { return {1, 2}; }
int main() {
  for (int x : snapshot(Lock{}))
    std::printf("body %d\n", x);
}
```

本机 Clang 23 的输出：

```text
-std=c++20      -std=c++23
lock            lock
unlock          body 1
body 1          body 2
body 2          unlock
```

C++20 中锁只保护 `snapshot` 这一次调用；C++23 中锁一直持有到循环结束。如果循环体再去锁同一个互斥量，就会出问题。[[diff.cpp20]] 记录的正是这个例子，标准说它在 C++20 中没问题，现在会死锁。严格地说，同一线程对已持有的 `std::mutex` 再次 `lock()` 违反了它的前置条件（[[thread.mutex.requirements.mutex.general#6]]），是未定义行为，死锁只是最常见的表现。

[[P2012R2]] 认为这类代码本来就脆弱：如果 `snapshot` 返回的是引用而不是副本，C++20 中的循环体就是在锁外访问共享数据。论文还转述了一次在大型代码库里的抽样分析：初始化器中大约有一万处析构，按类型归类后没有找到会受影响的；反倒是其中很多析构属于专门为了绕开这个 bug 而写的工具类。

另一个代价是内存。初始化器里的大对象在 C++20 中会在循环开始前释放，现在要一直占着。[[P2012R2]] 承认这在极少数情况下可能突破内存上限，需要时可以用 *init-statement* 或普通 `for` 循环自己控制生命周期。

## 最终措辞

### [class.temporary] 增加第四种情形

[[P2718R0]] 把 [[class.temporary#5]] 的"三种情形"改成"四种"，并新增一段，就是今天的 ¶7：

!!! std
    If such a temporary object would otherwise be destroyed at the end of the *for-range-initializer* full-expression, the object persists for the lifetime of the reference initialized by the *for-range-initializer*. ([[class.temporary#7]])

    如果初始化器中的临时对象原本会在这个完整表达式末尾销毁，它就活到初始化器所初始化的那个引用（即 `__range`）的生命周期结束。

"原本会在完整表达式末尾销毁"这个限定把三类东西排除在外。已经被延长的临时对象（直接绑定到 `__range` 的那个）本来就活得够久；函数形参不是临时对象，它的销毁时机由 [[expr.call#7]] 另行规定；被调用函数内部创建的临时对象属于别的完整表达式。

被延长的临时对象在 `__range` 销毁时一起销毁，顺序按 [[class.temporary#11]]：与构造完成的顺序相反。

```cpp run title="order.cpp" ok
#include <cstdio>
#include <vector>
struct T {
  const char* n;
  explicit T(const char* s) : n(s) { std::printf("  make %s\n", n); }
  ~T() { std::printf("  kill %s\n", n); }
};
struct Box {
  T tag{"Box"};
  std::vector<int> v{1, 2};
  const std::vector<int>& items() const { return v; }
};
Box make(const T&) { return {}; }
int main() {
  std::printf("before\n");
  for (int x : make(T{"arg"}).items())
    std::printf("  body %d\n", x);
  std::printf("after\n");
}
```

`-std=c++23` 下，本机输出依次是 `make arg`、`make Box`、`body 1`、`body 2`、`kill Box`、`kill arg`。实参 `T{"arg"}` 本来受 [[class.temporary#6]] 中"绑定到函数引用形参的临时对象活到完整表达式结束"这条例外约束，现在也被延长了。同一个程序用 `-std=c++20` 编译，两个对象在循环开始前就按同样顺序销毁，循环体读的是已经释放的 `vector`，本机一次也没有打印 `body`。

### 配套修改

为了让多个被延长的临时对象有确定的销毁顺序，[[P2718R0]] 同时修改了今天的 [[class.temporary#11]]。原来的措辞只说"绑定到引用的临时对象"按构造的逆序销毁；新范围 for 里被延长的对象不一定绑定到引用（例子里的 `Box` 就没有），所以改成"生命周期超出所在完整表达式的临时对象"。

[[stmt.ranged]] 增加了注 2 和例 2，指向新规则并划出它的边界（见下文"仍然悬垂的写法"）。[[diff.cpp20]] 增加了上面讨论的不兼容条目。

<details class="fine" markdown="1">
<summary>措辞的几次变化</summary>

[[P2012R2]] 的写法是"这样的临时对象持续到语句执行完毕"。[[P2644R1]] 加了两处限定：只管原本会在完整表达式末尾销毁的临时对象，并排除函数形参对象。CWG 审查后，[[P2718R0]] 把"持续到语句执行完毕"改成"持续到初始化器所初始化的引用的生命周期结束"，这样销毁时机直接挂在改写中的 `__range` 上。

P2718R0 的条文写的是 "a temporary object other than a function parameter object"。当前草案的 [[class.temporary#7]] 没有这半句。形参本来就不是临时对象，删掉它不改变含义。这里没有查到删除它的文档，只记录两者的差异。

同样的思路后来用在了 C++26 的展开语句上：[[class.temporary#8]] 和 [[class.temporary#9]] 对 `template for` 的初始化器给出了对应的延长规则，见 [[stmt.expand]]。
</details>

## 后果

### 兼容性与编译器支持

这项改动作为 C++23 的新特性进入标准，不是对旧标准的缺陷修正（DR），所以编译器只在 C++23 及以后的模式下启用它。特性测试宏 `__cpp_range_based_for` 的值随之更新为 `202211L`（[[cpp.predefined]]）。

本机 Clang 23 的观察与此一致：`-std=c++20` 下宏的值是 `201603`，上面几个例子都按旧规则执行；`-std=c++23` 和 `-std=c++2c` 下宏的值是 `202211`，按新规则执行。其他编译器的支持情况这里没有在本机验证。

这意味着同一份源代码在两种模式下的行为可能不同：一段在 C++23 下正确的循环，换成 `-std=c++20` 编译就是未定义行为，而且编译器多数情况下不会提醒。需要同时支持两种模式的库，仍然应该用 *init-statement* 写法。

### 仍然悬垂的写法

这条规则只认范围 for 的初始化器里、原本会在完整表达式末尾销毁的临时对象。下面几种情况都不在其中。

第一种是按值形参。[[stmt.ranged]] 的例 2：

```cpp run title="f2.cpp" ub
#include <list>
using T = std::list<int>;
const T& f1(const T& t) { return t; }
const T& f2(T t)        { return t; }
T g() { return {1, 2, 3}; }
int main() {
  int s = 0;
  for (int e : f1(g())) s += e;   // OK：g() 的临时对象被延长
  for (int e : f2(g())) s += e;   // UB：返回的是形参 t 的引用
  return s;
}
```

`g()` 的临时对象确实被延长了，但它只用来初始化形参 `t`，`f2` 返回的是 `t`。形参在函数返回时或在完整表达式末尾销毁（由实现定义，[[expr.call#7]]），无论哪种都早于循环体。Clang 在 `f2` 的定义处给出 `-Wreturn-stack-address` 警告。值得注意的是，本机 `-std=c++23` 加 ASan 运行时没有报告任何错误，第二个循环只是悄悄地一次也没有执行；ASan 没报不等于程序正确。

第二种是范围 for 以外的地方。普通声明没有这条特例：

```cpp
auto&& r = make().items();   // make() 的临时对象在这一行结束时销毁
for (int x : r) { }          // UB，C++23 也一样
```

这也包括把视图先存进变量再遍历。`auto v = load().items() | std::views::filter(p);` 中，`load().items()` 是左值，`views::all` 选了只保存指针的 `ref_view`，临时对象在这条声明结束时就没了（见 [[topics/ranges-design]] 开头的例子）。同样的管道直接写在范围 for 的初始化器里，C++23 下是安全的。

第三种是被调用函数内部的临时对象，以及循环体里的临时对象。例如一个函数返回指向自己局部 `std::string` 的 `string_view`，无论在哪里调用都悬垂。

这些都属于更一般的悬垂问题，[[topics/dangling-references]] 把它们分类讲了一遍。范围 for 只是其中最不显眼的一种，所以单独修了。

## 思考题

!!! question "1. 下面的循环在 C++20 和 C++23 下各是什么行为？"
    ```cpp
    std::string make();   // 返回一个较长的字符串
    for (char c : std::string_view(make())) use(c);
    ```

<details markdown="1">
<summary>答案</summary>

C++20 是未定义行为。`make()` 返回的临时 `string` 用来构造 `string_view`，`__range` 绑定的是 `string_view` 这个临时对象，被延长的只有它；`string` 在初始化器结束时销毁，`string_view` 指向已释放的内存。本机 Clang 23 在 `-std=c++20` 下给出 `-Wdangling-gsl` 警告，ASan 报告 `heap-use-after-free`。

C++23 起，`string` 是初始化器中原本会在完整表达式末尾销毁的临时对象，按 [[class.temporary#7]] 活到循环结束，循环正确。本机 `-std=c++23` 下没有警告，正常运行。
</details>

!!! question "2. 把 `for (int x : make().items())` 改成 `for (auto&& r = make().items(); int x : r)`，在 C++23 下是否还安全？"

<details markdown="1">
<summary>答案</summary>

不安全。延长规则只针对 *for-range-initializer*，也就是冒号右边的部分。*init-statement* 是一条普通声明，`make()` 的临时对象在它结束时销毁，`r` 悬空。C++20 推荐的绕行写法要存的是对象本身：`for (auto m = make(); int x : m.items())`。
</details>
