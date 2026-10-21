---
title: 第一卷 · 对象模型与生命周期
summary: 25 道题，考对象从哪里来、生命周期何时开始和结束、存储复用之后旧名字还能不能用、临时对象活多久，以及能用什么类型的 glvalue 读写一个对象。每题给出判定和当前草案的段落出处。
status: done
order: 1
related: intro.object, basic.life, basic.stc, class.temporary, ptr.launder, class.union, basic.lval, basic.types.trivial, topics/object-model, topics/type-punning, topics/dangling-references
tags: 对象模型, 生命周期, 存储期, 临时对象, launder, 联合体, 别名, UB
updated: 2026-10-20
---

!!! tldr
    - 考查范围：对象的创建与隐式对象创建、存储期与地址，生命周期的开始与结束、存储复用，透明替换与 `std::launder`，临时对象及其生命周期延长，联合体的活跃成员、trivially copyable 类型、类型可访问性规则和无效指针值。
    - 共 25 题：判定题 15 道、选择题 7 道、简答题 3 道，难度大致递增。建议用时 90 分钟。
    - 判定题按整个程序中最重的一项作答：`ok` 良构且行为明确，`error` 非良构，`ub` 未定义行为，`impl` 实现定义。题目代码都以当前工作草案为准，默认 `-std=c++2c`。
    - 每题的解析先给答案，再给推理链和 `[条款]/段` 出处，最后说明看起来也合理的选项错在哪里。

## 一、对象从哪里来

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。`Record` 有一个 `std::string` 成员，存储却来自 `std::malloc`，也没有调用构造函数。

```cpp run
#include <cstdlib>
#include <string>

struct Record {
    int id;
    std::string name;
};

int main() {
    auto* p = static_cast<Record*>(std::malloc(sizeof(Record)));
    if (!p) return 1;
    p->id = 42;
    int r = p->id;
    std::free(p);
    return r == 42 ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，行为明确（ok）。**

1. `std::malloc` 会在返回的存储里隐式创建对象，并返回指向一个合适的已创建对象的指针（[[c.malloc#4]]）。隐式创建只创建隐式生存期类型的对象，而且只在这样做能让程序有定义时才创建（[[intro.object#13]]、[[intro.object#14]]）。
2. `Record` 是聚合，析构函数不是用户提供的，所以它是隐式生存期类（[[class.prop#8]] 第 8.1 项）。成员 `std::string` 不是隐式生存期类型，但这不影响外层类的分类。
3. 于是 `malloc` 可以创建一个 `Record` 对象和它的 `int` 子对象 `id`，返回的指针指向这个 `Record`，`p->id` 的读写都有定义。按 [[intro.object#13]] 的注 4，`name` 子对象的生命周期没有开始，但程序没有碰它。
4. `std::free` 释放存储，结束了 `Record` 的生命周期而没有调用析构函数，这是 [[basic.life#6]] 允许的。

很多人会以为成员有非平凡构造函数就必须用 `new`。实际上要区分两件事：外层对象能否被隐式创建（能），以及哪些子对象的生命周期因此开始（只有隐式生存期类型的那些）。改一处，去用 `name`，就是未定义行为：

```cpp run ub
#include <cstdlib>
#include <string>

struct Record {
    int id;
    std::string name;
};

int main() {
    auto* p = static_cast<Record*>(std::malloc(sizeof(Record)));
    if (!p) return 1;
    p->name = "x";   // UB: p->name 不在生命周期内
    std::free(p);
}
```

`p->name` 是指代生命周期之外的对象的 glvalue，用它调用成员函数 `operator=` 是 [[basic.life#8]] 第 8.2 项列出的未定义行为；本机运行时在 `operator=` 里读到垃圾指针而崩溃。另一种改法是给 `Record` 加上 `~Record() {}`：析构函数成为用户提供的，8.1 项不再成立，类里也没有平凡的合格构造函数，8.2 项也不成立，`Record` 不再是隐式生存期类，连 `p->id = 42` 也变成未定义行为。详见 [[papers/implicit-object-creation]]。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

下列对象中，哪一个不具有动态存储期？

- A. `alignas(int) unsigned char buf[4]; int* p = ::new (buf) int(1);` 中的 `*p`，其中 `buf` 是块作用域的局部变量
- B. `std::malloc` 返回的存储中隐式创建的对象
- C. `new Node` 创建的 `Node` 对象的某个非静态数据成员子对象
- D. 函数 `void f(std::string s)` 被调用时的形参 `s`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：D。**

存储期是对象的属性，由创建对象的语法构造决定（[[basic.stc.general#1]]），不由存储在内存的哪个区域决定。

- A 是动态存储期。[[expr.new#10]] 规定，new 表达式创建的对象都具有动态存储期，placement new 也不例外，哪怕存储来自一个局部数组。这个 `int` 的存储仍然是 `buf` 的存储：块退出时 `buf` 的存储被释放，`*p` 的生命周期随之结束（[[basic.life#2]] 第 2.5 项）。
- B 是动态存储期：隐式创建的对象与 new 表达式创建的对象一样，归入动态存储期（[[basic.stc.general#2]]）。
- C 是动态存储期：子对象的存储期与其完整对象相同（[[basic.stc.general#4]]）。
- D 是自动存储期：属于形参作用域的变量具有自动存储期（[[basic.stc.auto#1]]）。

A 是最容易选错的一项。动态存储期不等于在堆上，它只说明这个对象不会在某个作用域结束时被隐式销毁。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

下面的程序输出什么？

```cpp run
#include <cstdio>

struct E {};
struct F {};

struct S {
    [[no_unique_address]] E a;
    [[no_unique_address]] E b;
};

struct T {
    [[no_unique_address]] E a;
    [[no_unique_address]] F b;
};

int main() {
    S s;
    T t;
    std::printf("%d %d\n",
                static_cast<void*>(&s.a) == static_cast<void*>(&s.b),
                static_cast<void*>(&t.a) == static_cast<void*>(&t.b));
}
```

- A. 一定是 `0 0`
- B. 一定是 `0 1`
- C. 第一个数一定是 0；第二个数可能是 0，也可能是 1
- D. 两个数都可能是 0，也可能是 1

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

1. 带 `[[no_unique_address]]` 的成员是潜在重叠子对象（[[dcl.attr.nouniqueaddr#1]]、[[intro.object#7]]）。这样的成员如果是没有子对象的类类型，标准不要求它有非零大小；它不是基类子对象，所以是否为零大小由实现定义（[[intro.object#8]]）。
2. 生命周期重叠的两个对象只有在 [[intro.object#10]] 列出的四种情况下才可以同址，其余情况必须地址不同。`s.a` 和 `s.b` 互不嵌套，也不是字符串字面量之类的潜在非唯一对象；第 10.3 项要求它们的类型不相似，而两者都是 `E`。所以 `&s.a != &s.b` 总成立，第一个数一定是 0。
3. `t.a` 和 `t.b` 的类型 `E`、`F` 不相似，只要其中一个是零大小，第 10.3 项就允许它们同址。是否零大小由实现定义；零大小子对象的地址是其完整对象所占的某个未指定的字节（[[intro.object#10]] 末句）。

本机 Clang（Itanium ABI）输出 `0 1`。MSVC 忽略标准的 `[[no_unique_address]]`（它提供的是 `[[msvc::no_unique_address]]`），输出 `0 0`，同样符合标准。所以 B 不对，它把一个实现的行为当成了保证。

同类型的两个对象必须地址不同，是对象同一性的基础：用 `==` 比较两个 `E*`，结果要能区分两个不同的 `E` 对象。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定整个程序。

```cpp run
int main() {
    alignas(int) unsigned char buf[sizeof(int)];
    int* p = reinterpret_cast<int*>(buf);
    *p = 5;
    return *p == 5 ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为（ub）。**

1. `buf` 的生命周期开始时，会在它占用的存储里隐式创建对象（[[intro.object#16]]），所以 `buf` 里可以有一个 `int` 对象。问题不在对象是否存在，而在 `p` 指向哪个对象。
2. `reinterpret_cast<int*>(buf)` 等价于先转换成 `void*` 再 `static_cast` 成 `int*`（[[expr.reinterpret.cast#7]]）。按 [[expr.static.cast#12]]，只有当原指针指向的对象与某个 `int` 对象指针可互相转换时，结果才指向那个 `int`；否则指针值不变。
3. `buf` 退化成指向 `buf[0]` 的指针。`buf[0]` 与嵌套在 `buf` 里的 `int` 不满足 [[basic.compound#7]] 的任何一项（同一对象、联合体与成员、标准布局类与首成员或基类），所以 `p` 仍然指向 `unsigned char` 对象 `buf[0]`。
4. `*p` 指代 `buf[0]`（[[expr.unary.op#1]]）。通过 `int` 类型的 glvalue 修改 `unsigned char` 对象，违反 [[basic.lval#11]]，行为未定义。无论隐式创建哪组对象都改变不了 `p` 的指针值，[[intro.object#13]] 也就救不了它。

改一处就有定义：

```cpp run ok
#include <new>

int main() {
    alignas(int) unsigned char buf[sizeof(int)];
    int* p = std::launder(reinterpret_cast<int*>(buf));
    *p = 5;                     // OK
    return *p == 5 ? 0 : 1;
}
```

`std::launder` 的前置条件要求该地址上有一个类型相似、在生命周期内的对象（[[ptr.launder#2]]）。隐式对象创建正好可以提供这个 `int`，于是 `launder` 返回指向它的指针。

第 1 题的 `malloc` 不需要 `launder`，因为 `malloc` 返回的就是指向已创建对象的指针（[[intro.object#14]]），而数组的生命周期开始时没有这样的返回值。Clang 对原程序不给诊断，结果也符合直觉。[[P3006R1]]（Launder less）提议在这种场合免去 `launder`，当前草案尚未采纳。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定整个程序。`raw` 的元素类型是 `char`。

```cpp run
#include <new>
#include <string>

struct Slot {
    std::string label;
    alignas(int) char raw[sizeof(int)];
};

int main() {
    Slot s;
    ::new (s.raw) int(42);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为（ub）。**

1. 只有 `unsigned char` 数组和 `std::byte` 数组能为其他对象提供存储（[[intro.object#3]]），`char` 数组不能。
2. 新建的 `int` 也不是 `s` 的子对象：要成为子对象，它必须与 `raw` 类型相同并恰好覆盖（[[intro.object#2]]）。因此它不嵌套在 `s` 之内（[[intro.object#4]]）。
3. `s` 的存储被一个不嵌套在 `s` 之内的对象复用，`s` 的生命周期结束（[[basic.life#2]] 第 2.5 项）。
4. `main` 结束时要隐式调用 `s` 的析构函数（[[class.dtor#14]]），而 `Slot` 的析构函数非平凡，该位置上却没有 `Slot` 对象，这是 [[basic.life#11]] 规定的未定义行为；在生命周期已结束的对象上调用析构函数，也违反 [[class.dtor#18]]。

只改元素类型就成了良构、行为明确的程序：

```cpp run ok
#include <new>
#include <string>

struct Slot {
    std::string label;
    alignas(int) unsigned char raw[sizeof(int)];
};

int main() {
    Slot s;
    ::new (s.raw) int(42);   // OK: raw 为 int 提供存储，int 嵌套在 s 之内
}
```

这时 `raw` 为 `int` 提供存储，`int` 嵌套在 `raw` 之内，进而嵌套在 `s` 之内（[[intro.object#4]] 第 4.2、4.3 项）。`s` 和 `raw` 的生命周期都不结束。两个版本运行起来没有区别，sanitizer 也不报告，差别只在标准的对象模型里。用来存放其他对象的缓冲区应当声明成 `unsigned char` 或 `std::byte` 数组，原因就在这里。

</details>
</div>

## 二、生命周期的结束与存储复用

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。第一个字符串的析构函数始终没有被调用。

```cpp run
#include <new>
#include <string>

int main() {
    auto* p = new std::string(100, 'x');
    ::new (p) std::string("y");
    bool ok = (*p == "y");
    delete p;
    return ok ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，行为明确（ok）。程序泄漏了 100 字节，但泄漏不是未定义行为。**

1. placement new 复用了第一个字符串的存储，它的生命周期就此结束（[[basic.life#2]] 第 2.5 项）。[[basic.life#6]] 明确允许这样结束类对象的生命周期而不调用析构函数，并说明此时析构函数不会被隐式调用。同段的注 4 提醒正确的程序往往依赖析构函数被调用，但注不具规范效力。
2. 原对象可以被新对象透明替换（[[basic.life#9]] 第 9.1 项）：两者都是完整对象，原对象不是 `const`，存储恰好重合，类型相同。所以 `p` 自动指向新对象（[[basic.life#10]]），`*p == "y"` 和 `delete p` 都作用于新对象。
3. 第一个字符串的堆缓冲区没有释放，这是资源泄漏，标准不把它算作未定义行为。

如果原对象是 `const` 的，透明替换就不成立：

```cpp run ub
#include <new>
#include <string>

int main() {
    const auto* p = new const std::string(100, 'x');
    ::new (const_cast<std::string*>(p)) const std::string("y");
    delete p;   // UB: p 仍指向已经结束生命周期的原对象
}
```

第 9.1.1 项要求原对象不是 `const`，所以 `p` 不会自动指向新对象。`p` 指向生命周期已结束的对象，把它用作 delete 表达式的操作数是 [[basic.life#7]] 第 7.1 项的未定义行为。写成 `delete std::launder(p)` 就有定义。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定整个程序。

```cpp run
#include <new>

struct S { int m; };

int main() {
    S x{1};
    ::new (&x) S{x.m + 1};
    return x.m;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为（ub）。**

1. [[basic.life#2]] 的最后一句规定：求值 new 表达式时，存储在分配函数返回之后、new 初始化器求值之前就算作被复用。这里的分配函数是 `operator new(std::size_t, void*)`。
2. 所以求值 `x.m + 1` 时，原来的 `x` 的生命周期已经结束，而新对象的生命周期还没有开始。
3. `x` 可以被新对象透明替换，但 [[basic.life#10]] 说的是名字在新对象的生命周期开始之后才能用来操作新对象。此刻 `x.m` 指代的是生命周期之外的原对象，读它的值属于 [[basic.life#8]] 第 8.1 项的未定义行为。这正是 [[basic.life#2]] 例 1 的情形。

本机运行返回 2，没有任何诊断。先把值读出来就没有问题：

```cpp run ok
#include <new>

struct S { int m; };

int main() {
    S x{1};
    int old = x.m;           // 先读出旧值
    ::new (&x) S{old + 1};   // OK
    return x.m;              // OK，x 指向新对象，值为 2
}
```

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定整个程序。`reset` 想用先析构、再原地构造的方式给 `Entry` 赋新值，而这一次 `load` 会抛异常。

```cpp run
#include <new>
#include <stdexcept>
#include <string>

struct Entry { std::string text; };

std::string load(bool fail) {
    if (fail) throw std::runtime_error("load failed");
    return std::string(64, 'n');
}

void reset(Entry& e, bool fail) {
    e.~Entry();
    ::new (&e) Entry{load(fail)};
}

int main() {
    try {
        Entry e{std::string(64, 'o')};
        reset(e, true);
    } catch (const std::exception&) {
    }
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为（ub）。**

1. `e.~Entry()` 结束了 `e` 的生命周期（[[class.dtor#18]]）。
2. placement new 的初始化器抛出异常，新的 `Entry` 从未构造完成，`e` 的位置上没有 `Entry` 对象。
3. 异常传出 `try` 块，`e` 是自动存储期对象，`Entry` 的析构函数非平凡，块退出时要隐式调用它（[[class.dtor#14]]）。[[basic.life#11]] 规定，此时该位置上必须有一个原类型的对象，否则行为未定义，并特别写明"即使块因异常而退出也是如此"。
4. 同时这也是在生命周期已结束的对象上再次调用析构函数（[[class.dtor#18]]）。

本机 ASan 报告 `attempting double-free`：第一个字符串的缓冲区被 `e.~Entry()` 和栈展开时的析构各释放一次。

修法是先把可能抛异常的部分做完，再修改 `e`：

```cpp run ok
#include <stdexcept>
#include <string>

struct Entry { std::string text; };

std::string load(bool fail) {
    if (fail) throw std::runtime_error("load failed");
    return std::string(64, 'n');
}

void reset(Entry& e, bool fail) {
    e = Entry{load(fail)};   // 先构造新值；抛异常时 e 原样保留
}

int main() {
    try {
        Entry e{std::string(64, 'o')};
        reset(e, true);
    } catch (const std::exception&) {
    }
}
```

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

下面标了字母的四行中，哪一行有未定义行为？（只有一行。）

```cpp run
struct Counter {
    mutable int hits;
    int limit;
    Counter() : hits(0), limit(0) { limit = 10; }
};

const Counter cfg;

int main() {
    const_cast<Counter&>(cfg).hits = 1;      // A
    int* p = const_cast<int*>(&cfg.limit);   // B
    int n = 0;
    const int& r = n;
    const_cast<int&>(r) = 2;                 // C
    *p = 3;                                  // D
}
```

- A. A 行
- B. B 行
- C. C 行
- D. D 行

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：D。**

规则在 [[dcl.type.cv#4]]：在 const 对象的生命周期内修改它是未定义行为。关键是哪些对象是 const 对象。按 [[basic.type.qualifier#1]] 第 1.1 项，const 对象是类型为 `const T` 的对象，或者 const 对象的非 `mutable` 子对象。

- A：`hits` 是 `mutable` 成员，不是 const 对象，修改它有定义。
- B：`const_cast` 本身不修改任何东西。
- C：`n` 不是 const 对象，只是通过 const 的访问路径看到它。去掉 const 之后修改有定义（[[dcl.type.cv#3]]）。
- D：`cfg.limit` 是 const 对象 `cfg` 的非 `mutable` 子对象，也是 const 对象，修改它是未定义行为。

还有一处容易误判：构造函数体里的 `limit = 10` 没有问题。const 语义在对象构造期间不生效，要等最派生对象的构造函数结束才开始生效（[[class.ctor.general#4]]）。

`cfg` 需要动态初始化，本机没有把它放进只读段，运行时看不到症状。如果 `cfg` 是常量初始化的，编译器可能把它放进只读内存，D 行会直接崩溃。

</details>
</div>

## 三、透明替换与 std::launder

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序。`Point` 有一个 `const` 成员。

```cpp run
#include <new>

struct Point {
    const int x;
    int y;
};

int main() {
    Point pt{1, 2};
    pt.~Point();
    ::new (&pt) Point{3, 4};
    return pt.x + pt.y;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，行为明确（ok），返回 7。**

1. 按 [[basic.life#9]] 第 9.1 项，原来的 `pt` 可以被新对象透明替换：两者都是完整对象，`pt` 本身不是 `const`（它的成员 `x` 是 const，但条件问的是完整对象），存储恰好重合，类型相同。
2. 因此名字 `pt` 自动指代新对象（[[basic.life#10]]），`pt.x` 读到 3。
3. [[basic.life#12]] 禁止在 const 完整对象的存储上创建新对象。`pt.x` 是 const 对象，但不是完整对象，这条限制不适用。

容易选错的理由是记得旧规则。C++20 之前，旧名字要自动指向新对象，还要求原对象的类型不含 const 或引用类型的非静态数据成员；不满足时只能用 C++17 为此引入的 `std::launder`（见 [[CWG1776]]）。C++20 删去了这一条件，现在 const 成员和引用成员都不影响透明替换。

改一处，把 `pt` 本身声明为 `const`，就是未定义行为：

```cpp run ub
#include <new>

struct Point {
    const int x;
    int y;
};

int main() {
    const Point pt{1, 2};
    ::new (const_cast<Point*>(&pt)) Point{3, 4};   // UB: pt 是 const 完整对象
    return pt.x + pt.y;
}
```

这一版违反 [[basic.life#12]]。本机 `-O0` 下返回 3：编译器假设 const 对象 `pt` 的值不会变，直接用了初始值 1 和 2。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="B" markdown="1">

下面四个函数中，哪一个必须改用 `std::launder` 才有定义行为？（其余三个不改也有定义。）

```cpp run
#include <new>

struct X { int n; };
struct Y { const int n; };

int a() { X* p = new X{1}; p->~X(); ::new (p) X{2}; int r = p->n; delete p; return r; }
int b() { const X* p = new const X{1}; ::new (const_cast<X*>(p)) const X{2}; int r = p->n; delete p; return r; }
int c() { X x{1}; ::new (&x) X{2}; return x.n; }
int d() { Y* p = new Y{1}; p->~Y(); ::new (p) Y{2}; int r = p->n; delete p; return r; }
```

- A. `a`
- B. `b`
- C. `c`
- D. `d`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：B。**

四个函数都在原对象的存储上创建了同类型的新对象，区别只在原对象能否被透明替换（[[basic.life#9]]）。能替换时，旧指针和旧名字自动指向新对象（[[basic.life#10]]）；不能替换时，要用 `std::launder` 取得指向新对象的指针（[[basic.life#10]] 的注 6、[[ptr.launder#5]]）。

- `a`：完整对象、非 const、同类型、恰好重合，可以透明替换。
- `b`：原对象的类型是 `const X`，违反第 9.1.1 项，`p` 不指向新对象。`p->n` 读的是生命周期已结束的原对象（[[basic.life#7]] 第 7.2 项），`delete p` 也有同样的问题（第 7.1 项）。两处都要写成 `std::launder(p)`。这个对象是动态存储期的，所以 [[basic.life#12]] 不禁止在它的存储上创建新对象。
- `c`：自动存储期的非 const 对象，可以透明替换，`x` 指代新对象。
- `d`：`Y` 含 const 成员，但自 C++20 起这不影响透明替换（见上一题）。

`d` 是陷阱项，它在 C++17 中确实需要 `launder`。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定整个程序。这次替换的是基类子对象。

```cpp run
#include <new>

struct Base { int v; };
struct Derived : Base { int extra; };

int main() {
    Derived d{{1}, 2};
    Base* pb = &d;
    ::new (pb) Base{5};
    return pb->v;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为（ub）。**

1. 新建的 `Base` 能否成为 `d` 的子对象，看 [[intro.object#2]]。第 2.3 项要求原子对象不是潜在重叠子对象，而基类子对象一定是潜在重叠子对象（[[intro.object#7]]）。所以新的 `Base` 是一个完整对象。
2. 它复用了 `d` 的一部分存储，又不嵌套在 `d` 之内，于是原来的基类子对象和 `d` 本身的生命周期都结束了（[[basic.life#2]] 第 2.5 项）。
3. 透明替换的两种情形（[[basic.life#9]]）都不成立：原对象不是完整对象，两者也不是对应的直接子对象。`pb` 仍指向生命周期已结束的原基类子对象。
4. `pb->v` 通过这样的指针访问非静态数据成员，属于 [[basic.life#7]] 第 7.2 项的未定义行为。

本机返回 5，看不出问题。[[ptr.launder#5]] 的注概括了需要 `launder` 的两种情况：完整对象是 const 的，或者原对象是基类子对象。下面这一版用 `launder` 取得指向新对象的指针；为了不在块退出时触及已结束生命周期的 `Derived`，把它放在一个提供存储的字节数组里：

```cpp run ok
#include <new>

struct Base { int v; };
struct Derived : Base { int extra; };

int main() {
    alignas(Derived) unsigned char buf[sizeof(Derived)];
    Derived* d = ::new (buf) Derived{{1}, 2};
    Base* pb = d;
    ::new (pb) Base{5};
    return std::launder(pb)->v;   // OK
}
```

</details>
</div>

## 四、临时对象活多久

<div class="quiz" data-kind="choice" data-answer="A" markdown="1">

下面的程序输出什么？

```cpp run
#include <cstdio>

struct T {
    char c;
    T(char c) : c(c) {}
    ~T() { std::putchar(c); }
};

const T& pass(const T& t) { return t; }

int main() {
    const T& a = T('a');
    const T& b = pass(T('b'));
    T('c');
    std::putchar('|');
    (void)a; (void)b;
}
```

- A. `bc|a`
- B. `c|ba`
- C. `c|ab`
- D. `cb|a`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：A。本机实测输出 `bc|a`。**

1. `T('a')` 经临时量实质化后直接绑定到 `a`，生命周期延长到 `a` 的生命周期结束，即 `main` 的块退出时（[[class.temporary#6]] 第 6.1 项）。所以 `a` 在 `|` 之后输出。
2. `T('b')` 绑定的是 `pass` 的引用形参。这是延长规则的例外：它只活到包含这次调用的完整表达式结束（[[class.temporary#6]] 第 6.10 项）。`b` 绑定的是 `pass` 返回的引用，而不是临时对象本身，所以 `b` 从下一条语句起就是悬垂引用。`b` 在第二条语句结束时输出。
3. `T('c');` 是弃值表达式，类类型的纯右值在这里会实质化（[[class.temporary#2]] 的注 2），在完整表达式结束时销毁（[[class.temporary#4]]）。
4. 然后输出 `|`，最后块退出，销毁 `a` 绑定的临时对象。

B、C 都假设 `b` 的临时对象也被延长了，这是这道题要考的误解：引用只延长直接绑定到它的临时对象，中间隔了一次函数调用，就不再延长。程序最后的 `(void)b` 不读取对象的值，所以本身没有未定义行为。

</details>
</div>

<div class="quiz" data-kind="choice" data-answer="C" markdown="1">

设 `struct S { int v; const int& ref() const { return v; } };`，`cond` 是一个 `bool` 变量。下列四个声明中，哪一个在声明结束后得到悬垂引用？

- A. `const int& a = S{1}.v;`
- B. `const int& b = static_cast<const int&>(S{2}.v);`
- C. `const int& c = S{3}.ref();`
- D. `const int& d = cond ? S{4}.v : S{5}.v;`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：C。**

[[class.temporary#6]] 列出了能把临时对象的生命周期传递给引用的表达式形式：临时量实质化本身，以及在它外面套上括号、数组下标、`.` 访问非引用类型的数据成员、不经用户定义转换的四种具名转型、条件表达式、逗号表达式等。引用最终绑定的 glvalue 必须是经由这些形式之一得到的。

- A：`S{1}` 实质化为临时对象，`.v` 访问非引用类型的成员（第 6.4 项），整个临时对象延长。
- B：`static_cast` 把指代该成员的 glvalue 转成指代同一对象的 glvalue，没有用户定义转换（第 6.6.2 项），延长。
- C：`ref()` 是函数调用，不在列表里。返回的引用指向临时对象的成员，但这个临时对象在完整表达式结束时销毁，`c` 悬垂。
- D：两个分支都是 `int` 类型的 xvalue，条件表达式是 glvalue，并且第二、第三操作数属于上述形式（第 6.8 项）。只有被求值的那个分支创建临时对象，它被延长。

本机用 ASan 运行，读 `c` 时报告 `stack-use-after-scope`，其余三个没有报告。D 的情形就是 [[class.temporary#6]] 例 2 的第三行。更多悬垂场景见 [[topics/dangling-references]]。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。被返回的是一个静态变量。

```cpp run
const long& counter() {
    static int n = 0;
    ++n;
    return n;
}

int main() { return counter(); }
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构（error）。**

1. 返回类型是 `const long&`，而 `n` 是 `int`，两者不是引用相关的类型。按 [[dcl.init.ref#5]] 第 5.4.2 项，初始化器先转换成 `long` 类型的纯右值，再经临时量实质化，引用绑定到这个临时 `long` 上，而不是绑定到 `n`。
2. [[stmt.return#6]] 规定：return 语句把返回的引用绑定到临时对象，程序非良构。这是 C++26 采纳 [[P2748R5]] 后的规则；在此之前，这段代码能编译，返回一个悬垂引用。

`static` 是干扰项。`n` 确实一直存活，但引用根本没有绑定到它。本机 Clang 在 `-std=c++2c` 下报错 `returning reference to local temporary object`，在 `-std=c++23` 下只给同一内容的警告，与标准版本的变化一致。把返回类型改成 `const int&` 就是良构的。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="error" markdown="1">

判定整个程序。

```cpp run
#include <string>

struct Config {
    const std::string& name;
    Config() : name("default") {}
};

int main() {
    Config c;
    return c.name.size() == 7 ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：非良构（error）。**

`"default"` 要先转换成一个 `std::string` 临时对象，引用成员 `name` 绑定到它。[[class.base.init#8]] 规定，在 mem-initializer 中把临时表达式绑定到引用成员，程序非良构。

为什么不直接延长生命周期？临时对象在构造函数的 mem-initializer 里创建，没有办法让它活得和 `Config` 对象一样久；如果按普通规则在完整表达式结束时销毁，`name` 一出生就悬垂。标准选择直接拒绝这种代码。默认成员初始化器有同样的规则（[[class.base.init#13]]），但只在某个构造函数实际使用了它时才报错。

本机 Clang 报错 `reference member 'name' binds to a temporary object whose lifetime would be shorter than the lifetime of the constructed object`。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定整个程序。`Ref` 是聚合，用圆括号初始化。

```cpp run
struct Ref {
    const int& r;
};

int main() {
    Ref x(42);
    return x.r;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为（ub）。**

1. 用圆括号的表达式列表初始化聚合（C++20，[[P0960R3]]）时，绑定到引用成员的临时对象只活到包含该表达式列表的完整表达式结束（[[class.temporary#6]] 第 6.11 项）。
2. 所以声明结束后 `x.r` 悬垂，`return x.r` 读取生命周期已结束的对象，行为未定义（[[basic.life#8]] 第 8.1 项）。

把圆括号换成花括号就有定义：

```cpp run ok
struct Ref {
    const int& r;
};

int main() {
    Ref x{42};       // OK: 临时对象的生命周期延长到 x.r 的生命周期
    return x.r;      // 返回 42
}
```

花括号的聚合初始化让引用成员直接绑定实质化的临时对象，适用一般的延长规则。圆括号形式被设计成与调用构造函数一致，而构造函数的引用形参也不延长实参临时对象的生命周期（第 6.10 项）。本机 Clang 对原程序给出 `-Wdangling` 警告，ASan 运行时报告 `stack-use-after-scope`。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ok" markdown="1">

判定整个程序（按当前草案）。

```cpp run
#include <vector>

struct Holder {
    std::vector<int> v{1, 2, 3};
    const std::vector<int>& get() const { return v; }
};

Holder make() { return {}; }

int main() {
    int sum = 0;
    for (int x : make().get())
        sum += x;
    return sum == 6 ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：良构，行为明确（ok）。在 C++20 及以前是未定义行为。**

1. 范围 for 等价于先用 for-range-initializer 初始化一个 `auto&&` 引用，再用它取迭代器（[[stmt.ranged#1]]）。这里引用绑定的是 `get()` 返回的引用，`make()` 产生的 `Holder` 临时对象并没有直接绑定到它。
2. C++20 中，这个临时对象在初始化器的完整表达式结束时销毁，循环遍历的是已销毁对象的成员，行为未定义。
3. C++23 起，[[class.temporary#7]] 增加了一条特例：在 for-range-initializer 中创建、原本会在该完整表达式末尾销毁的临时对象，一律活到初始化器所初始化的那个引用的生命周期结束，也就是整个循环结束（[[P2718R0]]）。

本机 Clang 23 在 `-std=c++2c` 下 ASan 运行无报告；改用 `-std=c++20` 编译，ASan 报告 `stack-use-after-scope`。

这条特例只管临时对象。[[stmt.ranged#1]] 例 2 中的 `f2(g())` 仍然是未定义行为：`f2` 按值接收形参，返回指向形参的引用，而形参不是临时对象。形参在函数返回时还是在完整表达式末尾销毁由实现定义（[[expr.call#7]]），两种情况下都早于循环开始。来龙去脉见 [[papers/range-for-temporaries]]。

</details>
</div>

## 五、访问对象的值与综合题

<div class="quiz" data-kind="choice" data-answer="D" markdown="1">

下列哪个类型是 trivially copyable 类型？

- A. `struct A { int x; virtual ~A() = default; };`
- B. `struct B { int x; B() = default; B(const B&) = delete; B(B&&) = delete; B& operator=(const B&) = delete; B& operator=(B&&) = delete; };`
- C. `struct C { int x; C() = default; C(const C& o) : x(o.x) {} };`
- D. `struct D { const int x; int& r; };`

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：D。**

[[class.prop#1]] 要求 trivially copyable 类同时满足三条：至少有一个合格的复制/移动构造函数或复制/移动赋值运算符；每个合格的这类函数都是平凡的；析构函数平凡且未被删除。合格是指未被删除、约束满足、且没有更受约束的同类函数（[[special#6]]）。

- A：有虚函数，复制构造函数等都不是平凡的（虚析构函数本身也不平凡）。
- B：四个复制/移动函数全被删除，一个合格的都没有，不满足第 1.1 项。
- C：复制构造函数是用户提供的，不平凡。
- D：`const` 成员和引用成员使复制赋值和移动赋值被定义为删除，它们不再合格；隐式的复制和移动构造函数仍然合格且平凡，析构函数平凡。三条都满足。

D 看起来最不像，因为它不能赋值。但 trivially copyable 只要求存在的合格操作都是平凡的，不要求每种操作都可用。对这样的对象，[[basic.types.trivial#4]] 保证用 `memcpy` 把一个对象的底层字节复制到另一个对象后，后者取得前者的值表示。

本机 Clang 23 的 `std::is_trivially_copyable_v<B>` 给出 `true`，与 [[class.prop#1]] 第 1.1 项不一致。"至少有一个合格函数"这一要求的讨论见 [[CWG1734]]。其余三项的实测结果与标准一致。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定整个程序。联合体当前的活跃成员是 `raw`，`Pair` 有用户提供的默认构造函数。

```cpp run
struct Pair {
    int first;
    int second;
    Pair() : first(0), second(0) {}
};

union Storage {
    int raw;
    Pair pair;
    Storage() : raw(0) {}
};

int main() {
    Storage s;
    s.pair.first = 1;
    return s.pair.first;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为（ub）。**

1. 对联合体成员赋值可以切换活跃成员，但规则只覆盖特定的左操作数（[[class.union.general#5]]）。对 `E1 = E2`，先算出 `E1` 的子表达式集合 S(E1)，只有集合中的成员会被隐式创建。
2. `s.pair.first` 的形式是 `A.B`，其中 `A` 是 `s.pair`，`first` 不是联合体成员，所以 S(`s.pair.first`) 就是 S(`s.pair`)。
3. S(`s.pair`) 包含 `s.pair` 的前提是 `pair` 的类型是非类、非数组类型，或者是默认构造函数平凡且未删除的类类型。`Pair` 的默认构造函数是用户提供的，不平凡，所以集合为空，赋值不会开始 `s.pair` 的生命周期。
4. 于是 `s.pair.first = 1` 修改的是生命周期之外的对象，属于 [[basic.life#8]] 第 8.1 项的未定义行为；[[class.union.general#2]] 也说明此时活跃成员仍是 `raw`。

陷阱在于 `Pair` 是隐式生存期类型（它的复制构造函数平凡，[[class.prop#8]] 第 8.2 项），但联合体赋值的规则看的不是隐式生存期，而是默认构造函数是否平凡。删掉 `Pair` 的构造函数，程序就有定义；保留构造函数时，正确的做法是 placement new：

```cpp run ok
#include <new>

struct Pair {
    int first;
    int second;
    Pair() : first(0), second(0) {}
};

union Storage {
    int raw;
    Pair pair;
    Storage() : raw(0) {}
};

int main() {
    Storage s;
    ::new (&s.pair) Pair;   // 切换活跃成员（[class.union.general]/6 的注）
    s.pair.first = 1;       // OK
    return s.pair.first;
}
```

两个版本在本机都返回 1，sanitizer 不报告。[[class.union.general#5]] 例 2 中带 const 成员的 `X` 是同一个道理：它的默认构造函数被删除，赋值 `y.x.b` 同样不会开始 `y.x` 的生命周期。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="ub" markdown="1">

判定整个程序。

```cpp run
#include <cstdio>

int main() {
    int x = 0x01020304;
    auto* p = reinterpret_cast<signed char*>(&x);
    std::printf("%d\n", *p);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：未定义行为（ub）。**

1. `p` 的指针值不因转换而改变，仍然指向 `int` 对象 `x`（[[expr.static.cast#12]]），`*p` 是指代 `x` 的 `signed char` 类型的 lvalue。
2. [[basic.lval#11]] 规定，动态类型为 `int` 的对象只能通过与下列类型相似的 glvalue 访问：`int` 本身，对应的有符号或无符号类型（`int`、`unsigned int`），以及 `char`、`unsigned char`、`std::byte`。
3. `signed char` 不在这个列表里。读取 `*p` 是通过不可访问的类型访问对象的存储值，行为未定义。

把 `signed char` 换成 `char` 或 `unsigned char`，访问本身就被允许了（第 11.3 项）。C 的对应规则允许任意字符类型，包括 `signed char`，C++ 只列了三种，这是两门语言的一个细微差别。

本机输出 `4`，sanitizer 不报告。主流编译器的别名分析通常把所有字符类型都当作可以别名任何对象，所以实践中看不到差别；但按标准，这个程序没有定义。读到的值是什么，见第 24 题。

</details>
</div>

<div class="quiz" data-kind="verdict" data-answer="impl" markdown="1">

判定整个程序。`p` 在被 `delete` 之后又参与了一次比较。

```cpp run
#include <cstdio>

int main() {
    int* p = new int(1);
    int* q = p;
    delete p;
    std::printf("%d\n", p == q);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**答案：实现定义（impl）。**

1. `delete p` 释放存储，结束这块存储区域的存续期（[[basic.stc.dynamic.deallocation#5]]）。此后 `p` 和 `q` 的值都是在当前求值中无效的指针值（[[basic.compound#6]]）。
2. 读取 `p`、`q` 这两个变量本身没有问题：它们是还活着的指针对象，左值到右值转换直接得到其中存的值（[[conv.lval#3]] 第 3.4.3 项）。
3. 用无效指针值做相等比较，按 [[basic.compound#6]] 第 6.2.2 项，行为由实现定义。只有间接访问（解引用）才是未定义行为（第 6.1 项）。

本机输出 `1`。容易选错的是 `ub`：常有人认为碰一下悬垂指针就是未定义行为。当前草案对此分得很细，解引用是未定义行为，比较、转成 `bool`、做加减由实现定义，单纯的读取和复制有定义。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

`Base` 是 trivially copyable 类型。下面的 `assign` 用 `memcpy` 给一个 `Base&` 赋值，传入的却是 `Derived` 的基类子对象。说明标准是否保证这段代码只改变 `d` 的 `Base` 部分，并解释本机输出 `8 8 2 0` 的原因。

```cpp run
#include <cstdio>
#include <cstring>
#include <type_traits>

class Base {
    int  id_;
    char kind_;
public:
    Base(int id, char kind) : id_(id), kind_(kind) {}
    int id() const { return id_; }
    char kind() const { return kind_; }
};

struct Derived : Base {
    char tag;
    Derived(int id, char kind, char t) : Base(id, kind), tag(t) {}
};

static_assert(std::is_trivially_copyable_v<Base>);

void assign(Base& dst, const Base& src) {
    std::memcpy(&dst, &src, sizeof(Base));
}

int main() {
    Derived d(1, 'a', 'T');
    assign(d, Base(2, 'b'));
    std::printf("%zu %zu %d %d\n", sizeof(Base), sizeof(Derived), d.id(), d.tag == 'T');
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**要点：标准不保证。[[basic.types.trivial#3]] 和 [[basic.types.trivial#4]] 关于复制底层字节的保证明确排除了潜在重叠子对象，而基类子对象正是潜在重叠子对象。**

1. 基类子对象和 `[[no_unique_address]]` 成员都是潜在重叠子对象（[[intro.object#7]]）。它们的 `sizeof` 是作为完整对象时的大小，但作为子对象时，末尾的填充字节可以被派生类或相邻成员拿去放别的数据。
2. 本机 Clang 遵循 Itanium C++ ABI：`Base` 有私有数据成员，不是 C++03 意义上的 POD，因此允许复用它的尾部填充。`Base` 占 8 字节（4 字节 `id_`、1 字节 `kind_`、3 字节填充），`Derived::tag` 被放进了这 3 字节填充里，所以 `sizeof(Derived)` 也是 8。
3. `memcpy(&dst, &src, sizeof(Base))` 复制 8 个字节，连同 `src` 的填充字节一起写进 `d`，覆盖了 `tag`。所以 `d.id()` 变成 2，`d.tag == 'T'` 变成假。
4. 这正是 [[basic.types.trivial#3]] 加上"不是潜在重叠子对象"这个限定的原因：对潜在重叠子对象，`sizeof` 个字节可能不全属于它。

结论是：trivially copyable 只保证对完整对象和普通成员子对象可以按字节复制；对基类子对象或 `[[no_unique_address]]` 成员，应当用它的复制赋值运算符（`static_cast<Base&>(d) = src`），编译器生成的平凡赋值知道哪些字节属于它。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

下面两行试图逐字节查看 `int` 的对象表示。按当前草案的字面规定，标了 (1) 和 (2) 的两行分别是否有定义？如果有定义，读到的值由哪条规则决定？

```cpp run
#include <cstdio>

int main() {
    int x = 0x01020304;
    auto* p = reinterpret_cast<unsigned char*>(&x);
    unsigned b0 = *p;         // (1)
    unsigned b1 = *(p + 1);   // (2)
    std::printf("%u %u\n", b0, b1);
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**要点：(1) 的访问是允许的，但按字面读到的是与 `x` 的值同余的 `unsigned char` 值，并不是该地址上那个字节的内容；(2) 按字面是未定义行为。当前草案没有真正支持逐字节读取对象表示，这是一个已知缺陷。**

1. 转换后 `p` 仍然指向 `int` 对象 `x`（[[expr.static.cast#12]]），因为 `x` 所在的位置上没有与它指针可互相转换的 `unsigned char` 对象。
2. (1)：`*p` 是指代 `x` 的 `unsigned char` lvalue（[[expr.unary.op#1]]）。通过 `unsigned char` 访问 `int` 对象被 [[basic.lval#11]] 第 11.3 项允许。读取的结果由 [[conv.lval#3]] 第 3.4.1 项决定：取对象中存的值 V（一个 `int` 值），结果是与 V 同余的 `unsigned char` 值，也就是 `0x01020304` 对 256 取模得到的 4，与这个字节在内存中的实际内容无关。
3. (2)：`p + 1` 中，`p` 的类型是 `unsigned char*`，而它指向的对象 `x`（按 [[basic.compound#3]] 视为单元素数组 `int[1]` 的元素）的类型是 `int`，两者不相似，[[expr.add#6]] 规定行为未定义。即使不考虑这一条，`p + 1` 也只能得到尾后指针，不能解引用。同样的理由也适用于加 0：如果把 (1) 写成 `p[0]`，它按定义就是 `*(p + 0)`（[[expr.sub#2]]），这次加法同样落入 [[expr.add#6]]，也是未定义行为。
4. [[basic.types.general#2]] 把对象表示定义为对象所占的 N 个 `unsigned char` 对象，但没有任何规则让这些 `unsigned char` 对象真的存在于 `x` 的位置上，也没有规则让指针能在它们之间移动。

本机输出 `4 3`，所有实现都按程序员期望的方式处理这种代码，`memcpy`、`std::bit_cast` 等库设施也依赖它。[[P1839R7]]（Accessing object representations）试图修正这一缺陷，让对象表示成为可以通过 `unsigned char*` 遍历的真正的数组；截至当前草案尚未并入。需要可移植地取得字节时，用 `std::bit_cast<std::array<unsigned char, sizeof(int)>>(x)` 或 `memcpy` 到 `unsigned char` 数组，这两种写法的语义是明确的（[[basic.types.trivial#3]]）。

</details>
</div>

<div class="quiz" data-kind="open" markdown="1">

下面是一个简化的 `Optional<T>`。回答三个问题：(a) `operator*` 是否有问题，怎么改；(b) 用编译器生成的复制构造函数复制一个持有 `std::string` 的 `Optional` 会怎样；(c) `emplace` 中 `T` 的构造函数抛出异常时，对象处于什么状态，是否有未定义行为。

```cpp run
#include <cstddef>
#include <new>
#include <string>
#include <utility>

template<class T>
class Optional {
    alignas(T) std::byte buf_[sizeof(T)];
    bool engaged_ = false;

public:
    Optional() = default;
    ~Optional() { reset(); }

    template<class... Args>
    T& emplace(Args&&... args) {
        reset();
        ::new (buf_) T(std::forward<Args>(args)...);
        engaged_ = true;
        return **this;
    }

    void reset() {
        if (engaged_) {
            (**this).~T();
            engaged_ = false;
        }
    }

    T& operator*() { return *reinterpret_cast<T*>(buf_); }
};

int main() {
    Optional<std::string> a;
    a.emplace(40, 'x');
    a.emplace("short");
    return *a == "short" ? 0 : 1;
}
```

<details class="quiz-key" markdown="1"><summary>答案与解析</summary>

**要点：(a) 需要 `std::launder`；(b) 复制得到的 `Optional` 声称持有对象，但其中没有 `std::string` 对象，析构时是未定义行为；(c) 抛异常后对象为空，没有未定义行为。**

(a) 与第 4 题相同。`buf_` 是 `std::byte` 数组，为 placement new 创建的 `T` 提供存储（[[intro.object#3]]），但 `reinterpret_cast<T*>(buf_)` 的结果仍指向 `buf_[0]`（[[expr.static.cast#12]]），通过它访问 `T` 违反 [[basic.lval#11]]，通过它调用成员函数和析构函数违反 [[basic.life#7]] 的限制（`buf_[0]` 不是 `T`）。改成 `*std::launder(reinterpret_cast<T*>(buf_))`：此时该地址上有一个在生命周期内的 `T`，满足 [[ptr.launder#2]]。另一种改法是在 `emplace` 里保存 placement new 返回的指针，以后都用它，代价是多存一个指针。本站 [[ptr.launder]] 页有同样的例子。

(b) 隐式复制构造函数逐元素复制 `buf_`，只复制了字节。新数组的生命周期开始时会隐式创建对象（[[intro.object#16]]），但只能创建隐式生存期类型的对象，`std::string` 不是，所以副本的 `buf_` 里没有 `std::string`。副本的 `engaged_` 却是 `true`，它的析构函数会在一个不存在的 `std::string` 上调用析构函数，这是未定义行为（[[basic.life#7]] 第 7.2 项）。实践中，如果字符串长到使用堆缓冲区，两个 `Optional` 会共享同一块缓冲区，本机 ASan 报告 `attempting double-free`。必须自己定义复制和移动操作，在目标里用 placement new 复制构造 `T`。

(c) `emplace` 先 `reset()`，`engaged_` 已经是 `false`；之后 `T` 的构造函数抛出异常，new 表达式不会留下对象，异常传出 `emplace`。此时 `Optional` 是空的，析构函数因为 `engaged_ == false` 不会去析构 `T`。`buf_` 是 `std::byte` 数组，析构函数平凡，第 8 题中 [[basic.life#11]] 的问题在这里不会出现。所以这里给出的是基本异常安全保证：失败后对象有效但为空，原来的值已经丢失。如果要求失败时保留旧值，就得先在别处构造好新值，这正是第 8 题修正版的思路。

</details>
</div>

## 题目与条款对照

| 题号 | 考查点 | 条款 |
|---|---|---|
| 1 | `malloc` 隐式创建含非平凡成员的聚合 | [[intro.object#13]]、[[c.malloc#4]]、[[class.prop#8]] |
| 2 | placement new 创建的对象的存储期 | [[basic.stc.general#2]]、[[expr.new#10]]、[[basic.stc.auto#1]] |
| 3 | `[[no_unique_address]]` 与地址唯一性 | [[intro.object#8]]、[[intro.object#10]] |
| 4 | 字节数组中的隐式对象与 `reinterpret_cast` | [[intro.object#16]]、[[expr.static.cast#12]]、[[basic.lval#11]] |
| 5 | `char` 数组不提供存储 | [[intro.object#3]]、[[basic.life#2]]、[[basic.life#11]] |
| 6 | 复用存储而不调用析构函数 | [[basic.life#6]]、[[basic.life#9]]、[[basic.life#10]] |
| 7 | new 初始化器求值前存储已被复用 | [[basic.life#2]]、[[basic.life#8]] |
| 8 | 析构后重建时抛出异常 | [[basic.life#11]]、[[class.dtor#18]] |
| 9 | 修改 const 对象与 `mutable` | [[dcl.type.cv#4]]、[[basic.type.qualifier#1]]、[[class.ctor.general#4]] |
| 10 | 含 const 成员的对象的透明替换 | [[basic.life#9]]、[[basic.life#12]] |
| 11 | 何时必须用 `std::launder` | [[basic.life#9]]、[[ptr.launder#5]] |
| 12 | 替换基类子对象 | [[intro.object#2]]、[[basic.life#7]]、[[basic.life#9]] |
| 13 | 临时对象的销毁时机 | [[class.temporary#4]]、[[class.temporary#6]] |
| 14 | 哪些表达式形式传递生命周期延长 | [[class.temporary#6]] |
| 15 | return 语句绑定临时对象 | [[stmt.return#6]]、[[dcl.init.ref#5]] |
| 16 | mem-initializer 中引用成员绑定临时对象 | [[class.base.init#8]] |
| 17 | 圆括号聚合初始化中的引用成员 | [[class.temporary#6]] |
| 18 | 范围 for 初始化器中的临时对象 | [[class.temporary#7]]、[[stmt.ranged#1]] |
| 19 | trivially copyable 的判定 | [[class.prop#1]]、[[special#6]] |
| 20 | 联合体成员赋值与活跃成员 | [[class.union.general#5]]、[[basic.life#8]] |
| 21 | 通过 `signed char` 访问对象 | [[basic.lval#11]] |
| 22 | 比较无效指针值 | [[basic.compound#6]]、[[conv.lval#3]] |
| 23 | 潜在重叠子对象与 `memcpy` | [[basic.types.trivial#3]]、[[intro.object#7]] |
| 24 | 逐字节读取对象表示 | [[basic.lval#11]]、[[conv.lval#3]]、[[expr.add#6]] |
| 25 | 自制 `Optional` 的存储管理 | [[intro.object#3]]、[[ptr.launder#2]]、[[basic.life#7]] |
