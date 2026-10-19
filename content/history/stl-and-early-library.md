---
title: STL 与 C++98 标准库的诞生
summary: 模板之前的容器为什么不好用，STL 怎样用迭代器把容器和算法分开，以及分配器、char_traits、写时复制字符串、vector<bool>、auto_ptr 这些 1990 年代的决定怎样留在今天的条文里。
status: draft
order: 60
since: c++98
papers: N1456, N1836, N1850, N2982, N2668, N1847, N1856, N4190, P0174R2, P0619R4, P0896R4
tags: 标准库, STL, 泛型编程, 分配器, iostream, string, vector<bool>, auto_ptr, valarray, C++98, C++03
related: library, containers, iterators, algorithms, basic.string, vector.bool, input.output, default.allocator, allocator.traits, unord, char.traits, localization, numarray, unique.ptr, history/modern-library
updated: 2026-10-19
---

!!! tldr
    - 模板出现之前，容器只能靠公共基类加指针来写：放不进 `int`，取出要向下转型。STL 用模板和迭代器把容器与算法分开，内建数组和指针也能直接用。
    - STL 在 1994 年才提交给委员会，删去约三分之二后进入草案。哈希表因为时间不够落选，C++11 补上时只好改名叫 `unordered_map`。
    - 迭代器分类、标签派发和 traits 都是在 STL 与 iostream 的模板化过程中发明的。STL 的需求表今天成了 *Cpp17* 具名要求，C++20 又用概念重写了一遍。
    - 分配器最初是为 16 位分段内存设计的，C++98 就允许实现不支持它的主要用途，此后一直在瘦身。
    - C++11 的失效规则排除了写时复制的 `string`；`vector<bool>` 和 `auto_ptr` 这两个争议组件，一个留在原处，一个被移除，都在条文里留下了痕迹。

本页的主要依据是 Stroustrup 的 HOPL 论文（HOPL II：*A History of C++: 1979–1991*；HOPL III：*Evolving a language in and for the real world: C++ 1991–2006*）、Stepanov 的访谈与回顾，以及相关的 WG21 文档和 LWG issue。C++11 之后标准库的演进见 [[history/modern-library]]，整个标准化过程见 [[history/standards-timeline]]。

## 模板之前的容器

1980 年代的 C++ 已经有 iostream、复数库和一些容器类，但没有模板。参数化类型只能用宏模拟，所以当时的容器库大多沿用 Simula 和 Smalltalk 的模式：元素必须派生自一个公共基类，容器里存的是指向基类的指针。

<div class="compare" markdown="1">

```cpp run ok title="公共基类风格（1980 年代）"
struct Object { virtual ~Object() {} };

struct List {          // 只能存 Object*
  Object* items[16]; int n = 0;
  void put(Object* p) { items[n++] = p; }
  Object* get(int i) { return items[i]; }
};
struct Int : Object {  // int 要先包一层
  int v; Int(int x) : v(x) {}
};

int main() {
  List l;
  l.put(new Int(42));
  Int* p = dynamic_cast<Int*>(l.get(0));
  int r = p ? p->v : -1;  // 取出时向下转型
  delete l.get(0);
  return r == 42 ? 0 : 1;
}
```

```cpp run ok title="模板风格（STL）"
#include <vector>

int main() {
  std::vector<int> v;
  v.push_back(42);   // 直接存 int
  int r = v[0];      // 不转型，没有虚调用
  return r == 42 ? 0 : 1;
}
```

</div>

Stroustrup 不接受左边的设计，理由正是代码里看到的这些：内建类型放不进去，取出元素要向下转型，不是静态类型安全的，每次访问还多一层间接（HOPL III §4.1.1）。他想要的是能直接容纳 `int`、静态类型安全、没有额外开销的容器，而这在没有模板的 C++ 里写不出来。

他后来把这件事称为自己最大的错误：1.0 版应该等到有一个包含链表、关联数组、带范围检查的数组和简单字符串的库再发布（HOPL II §7.3）。结果每个团队都在重新发明这些类，社区里出现了大量互不兼容的容器库。

标准化开始后，Stroustrup 提出的方针是：C 库、iostream 和语言支持部分必须标准化；此外委员会只接受积木式（building blocks）的组件，不做大而全的框架，也不和商业库厂商竞争（HOPL III §4.2）。积木要被所有人用，就必须足够高效和通用：访问元素要经过虚函数调用的容器不够高效，不能容纳任意类型的容器不够通用。

## STL 的模型

Alexander Stepanov 从 1970 年代末开始研究后来称为**泛型编程**（generic programming）的方法：把算法写成只依赖类型必须满足的最少要求，再与具体的数据结构组合。他先后在 Scheme 和 Ada 里实现过泛型库，但没能写出对链表和数组都适用、又足够高效的算法（HOPL III §4.1.8 收录的 Stepanov 自述）。

C++ 的模板给了他需要的东西。其中一点是函数模板可以从实参推导模板实参，不必像 Ada 泛型那样显式实例化。Stepanov 曾主张后者，Stroustrup 没有采纳；两人后来都说，正是这个决定让 STL 的很多写法成为可能（Stepanov 1995 年 *Dr. Dobb's Journal* 访谈；HOPL III §4.1.2）。

STL 的核心是把容器和算法完全分开。容器以元素类型为参数，每种容器提供自己的**迭代器**类型；算法只通过迭代器访问元素。迭代器的接口借用指针的写法（`*`、`++`、`!=`），所以普通指针本身就是迭代器：

```cpp run title="find.cpp" ok
#include <algorithm>
#include <list>
#include <string>
#include <vector>

int main() {
    std::vector<int> vi{3, 7, 42};
    std::list<std::string> ls{"Koenig", "Stepanov", "Lee"};
    auto p = std::find(vi.begin(), vi.end(), 7);
    auto q = std::find(ls.begin(), ls.end(), "Stepanov");
    int a[] = {1, 2, 3};
    int* r = std::find(a, a + 3, 2);   // 内建数组和指针同样适用
    return (p != vi.end() && q != ls.end() && *r == 2) ? 0 : 1;
}
```

同一个 `find` 用于 `vector<int>`、`list<string>` 和内建数组，没有虚函数，没有公共基类。m 个算法和 n 种容器只需要写 m + n 份代码，而不是 m × n 份。

STL 的另一项做法是给每个操作规定复杂度。Stepanov 认为复杂度是接口的一部分：`vector` 和 `list` 都能在中间插入元素，区别正在于代价（HOPL III §4.1.7）。所以今天 [[algorithms]] 里每个算法都有 *Complexity* 段落，[[container.requirements]] 的需求表也带有复杂度一栏。

## STL 怎样进入标准

1993 年底，Stepanov 应 Andrew Koenig 邀请在标准委员会会议上做了一次报告。报告只讲了正规类型和前向迭代器应满足的公理，以及一个算法 `find`。Stroustrup 说，这次报告让委员会的态度从这个阶段不可能再做大改动转向了不妨看一看（HOPL III §4.1.2）。

问题在于时间。委员会原计划很快完成标准，上一次会议刚通过决议，不再接受大型提案（Stepanov 访谈）。1994 年 1 月，Koenig 告诉 Stepanov，要进入标准必须在几周内提交正式提案；Stepanov 和 Meng Lee 赶出了提案，在 3 月的会议上完整介绍了 STL。

规模是主要障碍。委员会担心没有时间认真审查这么大的规范。Stroustrup 回忆，最后他应 Stepanov 的要求划掉了约三分之二的文本，留下的每一项都要有人说明为什么对大多数程序员有用（HOPL III §4.1.2）。精简后的 STL 在 1994 年 7 月的 Waterloo 会议上被投票纳入工作草案。即便如此，把它写成标准条文还是让标准推迟了一年多。

Stroustrup 说自己除了删减之外贡献很小，其中一项是在 Stepanov 的黑板上画出了最初的**需求表**（requirements table）：用一张表列出模板实参必须支持哪些表达式、表达式的类型和语义。标准至今用这种表格描述模板参数的要求。他同时指出，需求表的存在恰恰说明语言表达能力不足，这些要求本应能写在代码里（HOPL III §4.1.2）。这件事到 C++20 的概念才部分实现（[[history/concepts]]）。

<details class="fine" markdown="1">
<summary>日期上的出入</summary>

HOPL III 把 Stepanov 的报告记在 1993 年 10 月的 San Jose 会议，Stepanov 在访谈中说是 11 月，保存下来的幻灯片日期是 1993 年 11 月 11 日。HOPL III 把 Waterloo 会议记在 1994 年 10 月，而 P. J. Plauger 在 1997 年 8 月的 *C/C++ Users Journal* 专栏中写的是 1994 年 7 月。本页采用 11 月和 7 月。纳入草案的文本以 Stepanov 和 Lee 的 HP Labs 技术报告 HPL-94-34（1994 年 8 月，1995 年修订）为基础。

</details>

## 迭代器分类、标签与 traits

如果所有迭代器都支持同一套操作，模型会很简单。但数组、链表和输入流的能力本来就不同：数组能随机访问，链表只能逐个前进或后退，输入流只能读一遍。STL 因此把迭代器分成五类：输入、输出、前向、双向、随机访问（HOPL III §4.1.6）。同一个算法可以为不同类别提供不同实现，在编译期选出最合适的一个。

怎样在编译期得知一个迭代器属于哪一类？1995 年的 STL 技术报告用的是重载函数：`iterator_category(i)` 返回一个空的标签对象，`value_type(i)`、`distance_type(i)` 返回空指针，只用来把类型传给辅助函数。这种办法既不系统，也容易出错。

更一般的办法是 Nathan Myers 在把 iostream 和 string 模板化时总结出来的 **traits**：用一个辅助类模板集中存放某一类类型的属性（Myers, *Traits: a new and useful template technique*, *C++ Report*, 1995）。用于迭代器，就是 `iterator_traits`：普通迭代器从自己的成员类型取得这些属性，指针则通过偏特化取得。类模板的偏特化本身就是 1995 年才加入 C++ 的，STL 是它的主要动机之一（HOPL III §4.1.5）。

标签派发加上 `iterator_traits`，是 C++98 到 C++17 标准库内部的典型写法，今天依然可用：

```cpp run title="tag-dispatch.cpp" ok
#include <cassert>
#include <iterator>
#include <list>
#include <vector>

template<class It>
void my_advance(It& it, int n, std::input_iterator_tag) {
    while (n-- > 0) ++it;                 // 只能一步一步走
}
template<class It>
void my_advance(It& it, int n, std::random_access_iterator_tag) {
    it += n;                              // 常数时间
}
template<class It>
void my_advance(It& it, int n) {
    my_advance(it, n, typename std::iterator_traits<It>::iterator_category{});
}

int main() {
    std::vector<int> v{0, 1, 2, 3};
    std::list<int>   l{0, 1, 2, 3};
    int a[] = {0, 1, 2, 3};
    auto vi = v.begin(); my_advance(vi, 2);   // random_access 版本
    auto li = l.begin(); my_advance(li, 2);   // 双向迭代器落到 input 版本
    int* pi = a;         my_advance(pi, 2);   // 指针：iterator_traits 的偏特化
    assert(*vi == 2 && *li == 2 && *pi == 2);
}
```

`list` 的迭代器能选中 `input_iterator_tag` 版本，是因为标签类之间有继承关系：`bidirectional_iterator_tag` 派生自 `forward_iterator_tag`，后者又派生自 `input_iterator_tag`（[[std.iterator.tags]]）。没有专门重载的类别，通过派生类到基类的转换落到最接近的版本上。

### 需求表和概念并存

今天的标准里，这套体系有两层。STL 的需求表保留了下来，改名为 *Cpp17InputIterator* 等具名要求（[[iterator.cpp17]]），供仍按 C++98 风格描述的组件使用。C++20 的 ranges 工作（[[P0896R4]]）则用概念重新定义了迭代器（[[iterator.concepts]]），并增加了 `contiguous_iterator` 一类。

两套定义并不总是一致。*Cpp17ForwardIterator* 要求解引用得到真正的引用，C++20 的 `forward_iterator` 概念没有这个要求。于是有的迭代器按概念是随机访问的，按旧分类却只是输入迭代器：

```cpp run ok
#include <iterator>
#include <ranges>
#include <type_traits>

using It = std::ranges::iterator_t<std::ranges::iota_view<int, int>>;
static_assert(std::random_access_iterator<It>);        // C++20 概念
static_assert(std::is_same_v<std::iterator_traits<It>::iterator_category,
                             std::input_iterator_tag>); // C++98 分类
int main() {}
```

`iota_view` 的迭代器解引用返回一个 `int` 值而不是引用，所以在旧体系里只能算输入迭代器。下文的 `vector<bool>` 违反的也是同一条要求。

## 被砍掉的哈希表

1994 年的删减和此后的时间压力，让一类人人都想要的容器没能进入 C++98：哈希表。HOPL III §6.2 说，如果有时间做好详细设计，哈希表本来会在 C++98 里；1995 年 Barreiro、Fraley 和 Musser 曾试图赶在标准完成前准备好一份提案，但委员会已经没有时间处理。

结果各家实现自己提供了 `hash_map`、`hash_set`，彼此相似但不相同。Matt Austern 在 2003 年的 [[N1456]] 中提出标准哈希容器时，特意换用新名字，避免与这些已有的类冲突（N1456 引言）。名字里的 unordered 指遍历顺序没有保证，因为哈希函数不像 `map` 的 `<` 那样定义一种顺序（HOPL III §6.2）。这份提案经 TR1（[[N1836]]）进入 C++11，成为今天的无序关联容器（[[unord]]）：

```cpp run title="unordered.cpp" ok
#include <string>
#include <unordered_map>

int main() {
    std::unordered_map<std::string, int> freq;
    for (const char* w : {"vector", "list", "vector"})
        ++freq[w];
    return freq["vector"] == 2 ? 0 : 1;
}
```

## 分配器：为分段内存而设计

分配器是 STL 里离当年的硬件最近的部分。16 位 x86 采用分段内存，同一个程序里可能同时有 near、far、huge 几种指针，大小和运算规则各不相同。委员会希望容器独立于这种内存模型，Stepanov 的办法是把内存模型的信息封装进一个对象：

> "I invented allocators to deal with Intel's memory architecture."（Stepanov，Lo Russo 访谈）

所以 1995 年 STL 技术报告里的分配器要定义 `pointer`、`const_pointer`、`reference`、`size_type`、`difference_type` 等类型，以及 `address`、`allocate`、`deallocate`、`construct` 等操作，所有容器都以分配器为参数（报告 §7；另见 Halpern [[N1850]] §4.2）。

问题在于语言不支持这种抽象。`T&` 和 `T*` 是写死在语言里的，用户无法定义一个行为像引用的类型。Stepanov 举过一个例子：两个 `vector<int>` 用不同的分配器，`b[1]` 返回的是第二个分配器的 `reference` 类型，未必是 `int&`，把它交给在第一个容器上运行的 `find` 就可能类型不匹配（Lo Russo 访谈）。

C++98 的折中是允许实现忽略这些功能：实现可以假定同一类型的分配器总是比较相等，并假定 `pointer`、`size_type` 等就是 `T*`、`size_t` 等。于是分配器原本要解决的问题（不同的指针类型），和后来人们想用它解决的问题（带状态的内存池），在 C++98 里都可以不被支持（Halpern [[N1850]] §4.1）。

C++11 以 [[allocator.traits]] 为中心重建了分配器模型（[[N2982]]）：自定义分配器只需提供很少的成员，其余由 `allocator_traits` 补齐，带状态的分配器也有了明确的传播规则。此后 `std::allocator` 逐步瘦身，冗余成员在 C++17 弃用（[[P0174R2]]）、C++20 移除（[[P0619R4]]）。

<div class="compare" markdown="1">

```cpp title="C++98 的 std::allocator（节选）"
template<class T> class allocator {
public:
  typedef T*        pointer;
  typedef const T*  const_pointer;
  typedef T&        reference;
  typedef const T&  const_reference;
  typedef size_t    size_type;
  typedef ptrdiff_t difference_type;
  template<class U> struct rebind {
    typedef allocator<U> other; };
  pointer address(reference x) const;
  pointer allocate(size_type n,
    allocator<void>::const_pointer = 0);
  void deallocate(pointer p, size_type n);
  size_type max_size() const;
  void construct(pointer p, const T& v);
  void destroy(pointer p);
};
```

```cpp title="今天的 std::allocator（节选）"
template<class T> class allocator {
public:
  using value_type      = T;
  using size_type       = size_t;
  using difference_type = ptrdiff_t;
  constexpr T* allocate(size_t n);
  constexpr allocation_result<T*>
    allocate_at_least(size_t n);
  constexpr void deallocate(T* p, size_t n);
};
```

</div>

两边都省略了构造函数等成员，今天的完整定义见 [[default.allocator]]。左边那些类型成员和 `address`、`construct`、`destroy`，正是为抽象掉指针和引用类型而设的。今天一个能用于标准容器的分配器只需要这么多：

```cpp run title="minimal-allocator.cpp" ok
#include <cstddef>
#include <new>
#include <vector>

template<class T>
struct Mallocator {
    using value_type = T;
    Mallocator() = default;
    template<class U> constexpr Mallocator(const Mallocator<U>&) noexcept {}
    T* allocate(std::size_t n) {
        return static_cast<T*>(::operator new(n * sizeof(T)));
    }
    void deallocate(T* p, std::size_t) noexcept { ::operator delete(p); }
};
template<class T, class U>
bool operator==(const Mallocator<T>&, const Mallocator<U>&) { return true; }

int main() {
    std::vector<int, Mallocator<int>> v{1, 2, 3};   // 其余成员由 allocator_traits 补齐
    v.push_back(4);
    return v.size() == 4 ? 0 : 1;
}
```

分配器还有一个设计问题没有解决：它是容器类型的一部分，用不同分配器的 `vector<int>` 是不同的类型。C++17 的 `std::pmr` 用运行期多态的内存资源处理了这一点，见 [[history/modern-library]]。

## 以字符类型为参数：char_traits 与 locale

标准化开始时，国际化是库工作组的任务之一，其中一个结论是：凡是处理字符的设施，都必须以字符类型为模板参数（Myers 1995）。把已有的 iostream 和 string 改写成模板，比预想的难。

难点在于字符之外还有一组相关的类型和值。传统的 `streambuf` 和 C 的 stdio 一样，用一个与所有字符都不同的 `EOF` 表示文件结束，所以读字符的函数返回 `int`。模板化之后，除了字符类型，还需要一个能容纳 EOF 的整数类型和 EOF 的值；都做成模板参数，用户每次都要写一长串与他无关的参数。traits 的做法是用一个以字符类型为参数的模板集中存放 `int_type`、`eof()` 这类信息，这就是 [[char.traits]]。

于是 `basic_string`、`basic_istream`、`basic_ostream` 都多了一个 `traits` 参数，默认为 `char_traits<charT>`，`string`、`istream`、`ostream` 成了 `char` 特化的别名。这个设计的一个副作用是，字符的比较规则可以通过 traits 替换：

```cpp run title="ci-string.cpp" ok
#include <cassert>
#include <cctype>
#include <cstddef>
#include <string>

struct ci_traits : std::char_traits<char> {
    static bool eq(char a, char b) {
        return std::tolower((unsigned char)a) == std::tolower((unsigned char)b);
    }
    static bool lt(char a, char b) {
        return std::tolower((unsigned char)a) < std::tolower((unsigned char)b);
    }
    static int compare(const char* p, const char* q, std::size_t n) {
        for (; n; --n, ++p, ++q) {
            if (lt(*p, *q)) return -1;
            if (lt(*q, *p)) return 1;
        }
        return 0;
    }
};
using ci_string = std::basic_string<char, ci_traits>;

int main() {
    ci_string a = "STL", b = "stl";
    assert(a == b);          // 比较规则来自 traits，而不是 basic_string 本身
}
```

标准 iostream 还依赖 locale（[[localization]]）：数值的格式化和解析通过 `num_put`、`num_get` 等 facet 完成。locale 是为了支持英语以外的语言加入的（HOPL III §6.1）。Stroustrup 对这部分的评价不高：iostream 和 locale 受到了第二系统效应的影响，设计者想同时满足各种需求和既有实践（HOPL III §4.2）。iostream 的格式化接口此后二十年没有大的变化，直到 C++20 的 `std::format` 和 C++23 的 `std::print`（[[format]]）。

## std::string 与写时复制

`basic_string` 的提案早于 STL，STL 被接纳之后又补上了迭代器接口和容器式的成员，所以它同时有以下标、以迭代器、以 C 字符串为参数的几套成员函数。HOPL III §4.2 说它同时呈现了好几种风格；Herb Sutter 数过，`basic_string` 连构造函数在内有 103 个成员函数，其中 71 个本可以写成非成员函数（GotW #84）。

更有后果的是 C++98 允许**写时复制**（copy-on-write，COW）实现：复制字符串时只增加引用计数，等到可能修改时再真正复制。为此，C++98 的引用失效规则里有一条特殊条款：构造之后第一次调用非 const 的 `operator[]`、`at`、`begin`、`end` 等，也可能使已有的引用、指针和迭代器失效。COW 实现必须在交出可写引用之前先取消共享。

多线程程序普及之后，这条规则成了问题。线程安全的 COW 必须对引用计数做原子操作或加锁，所有用户都要付出这个代价（Sutter, *Optimizations That Aren't (In a Multithreaded World)*, 1999）。C++11 引入线程时，[[N2668]] 指出了更具体的麻烦：对 `vector` 可以直接并行地给每个元素赋值，对 `basic_string` 却必须先在单线程里调用一次 `s[0]`，否则第一次非 const 访问可能使其他线程拿到的引用失效。

N2668 的修改是让所有元素访问操作都不使引用失效，它明确说明这实际上不允许 COW 实现。今天 [[string.require#4]] 的失效列表就是修改后的版本，附录 C 的 [[diff.cpp03.strings]] 把它记为 C++03 与 C++11 之间的不兼容：

```cpp run title="string-invalidation.cpp" ok
#include <cassert>
#include <string>

int main() {
    std::string s = "abc";
    const char* p = s.c_str();
    char& c = s[0];          // C++11 起：非 const operator[] 不再使引用失效
    c = 'x';
    assert(p[0] == 'x');     // p 仍然有效，指向同一块缓冲区
}
```

在 C++03 的规则下，`s[0]` 是构造之后第一次非 const 调用，标准允许它使 `p` 失效。实现的跟进花了几年：GCC 的 libstdc++ 由于 ABI 兼容的要求，到 GCC 5（2015）才默认启用不使用 COW 的新 `std::string`，旧实现仍可通过 `_GLIBCXX_USE_CXX11_ABI=0` 选用（GCC 5 发布说明）。ABI 对标准库演进的约束见 [[history/modern-library]]。

## vector&lt;bool&gt;：不是容器的容器

C++98 为 `vector<bool>` 规定了一个以位存储元素的特化（今天在 [[vector.bool.pspc]]）。一个位没法被引用，所以它的 `reference` 是一个代理类，而容器要求 `reference` 必须是 `T&`。1998 年提交的 [[LWG96]] 标题就是 *Vector&lt;bool&gt; is not a container*。

问题在泛型代码里最明显。下面的函数对除 `bool` 以外的所有 `T` 都成立：

```cpp title="vector-bool-ref.cpp" error
#include <vector>

template<class T>
void first_ref(std::vector<T>& v) {
    T& r = v.front();        // 对除 bool 以外的所有 T 都成立
    (void)r;
}

int main() {
    std::vector<int> vi{1};
    std::vector<bool> vb{true};
    first_ref(vi);           // OK
    first_ref(vb);           // error: bool& 不能绑定到代理对象
}
```

反过来，用 `auto` 接住 `vb[0]` 时得到的不是 `bool` 的拷贝，而是一个仍然指向容器的代理：

```cpp run title="vector-bool-proxy.cpp" ok
#include <cassert>
#include <type_traits>
#include <vector>

int main() {
    std::vector<bool> vb{true, false};
    auto x = vb[0];          // x 是 vector<bool>::reference 代理
    static_assert(!std::is_same_v<decltype(x), bool>);
    vb[0] = false;
    assert(x == false);      // 通过代理看到了修改：x 并不是一份拷贝
}
```

此后十年里，委员会讨论过补全它的规范、弃用它、换一个名字（如 `bit_vector`）提供同样的功能，都没有形成可以投票的方案（[[N1847]] 及 LWG96 的讨论记录）。2009 年 LWG 以 NAD（Not A Defect）关闭了这个 issue，理由是：委员会希望支持代理迭代器，但那是另外的工作；能想到的接近的修改都会破坏现有代码；移除它不可行。

Howard Hinnant 后来的看法是，位数组本身是好的数据结构，正确实现时既省空间又可能更快；错误在于给它起名 `vector<bool>`，让它假装是一个 `bool` 数组（*On vector&lt;bool&gt;*, 2012）。代理引用的问题后来在 ranges 里得到了正面处理：C++20 的迭代器概念允许代理引用，C++23 的 `views::zip` 也围绕代理元组设计。

## auto_ptr：没有移动语义时的移动

`auto_ptr` 是 C++98 里唯一的智能指针，表示独占所有权。当时没有右值引用，它只能借用复制的语法来转移所有权：`b = a` 之后 `a` 变为空。

按值返回一个 `auto_ptr` 还有一个障碍：返回的是临时对象，而临时对象不能绑定到复制构造函数的非 const 引用形参上。标准化后期的解决办法是 Colvin 和 Gibbons 的辅助类 `auto_ptr_ref`：右值先通过转换函数变成 `auto_ptr_ref`，再通过接受它的构造函数变回 `auto_ptr`（Gibbons, Colvin, *Fixing auto_ptr*, 1997）。

```cpp title="历史代码：C++98 的 auto_ptr（C++11 弃用，C++17 移除）"
#include <memory>

std::auto_ptr<int> source() { return std::auto_ptr<int>(new int(42)); }
void sink(std::auto_ptr<int> p) { }   // 按值接收，取得所有权

int main()
{
    std::auto_ptr<int> a(new int(1));
    std::auto_ptr<int> b = a;    // 看起来是复制，实际上转移了所有权：a 变为空
    sink(source());              // 右值经由 auto_ptr_ref 传入
}
```

这个技巧依赖重载决议里很微妙的地方，并引出了一个核心语言问题（[[CWG84]]）。更根本的问题是，泛型代码默认复制之后源和目标相等，而 `auto_ptr` 违反了这一点（Hinnant [[N1856]]）。C++11 有了右值引用，`unique_ptr` 把转移写成显式的 `std::move`；`auto_ptr` 在 C++11 弃用、C++17 移除（[[N4190]]）。经过和对比代码见 [[history/modern-library]]。

今天 `auto_ptr` 和 `auto_ptr_ref` 列在 [[zombie.names]] 里，作为为以往标准保留的名字：实现可以继续为旧代码提供它们，用户代码不能拿来另作他用。

## valarray

`valarray` 走的是另一条路。它在 1993 年就被提出，目标是在向量处理器上获得 Fortran 那样的性能，设计主要基于 Sandia 国家实验室的经验；1994 年 STL 被纳入的同一次会议上，它也几乎没有讨论就被加进了草案（Plauger, *C/C++ Users Journal*, 1997 年 8 月）。

为了让编译器能做向量化优化，它的规范假定这些数值数组不存在某些形式的别名，今天的 [[valarray.syn]] 仍然这样说明。但它在标准化之后评价不高。2000 年，Nathan Myers 说库工作组差不多把它看作一次失败的实验（libstdc++ 邮件列表）。它至今仍在标准里（[[numarray]]）；标准库在数值计算上的新方向是 C++23 的 `mdspan` 和 C++26 的线性代数接口。

## 异常安全的三个保证

异常和模板几乎同时进入 C++，标准库是第一个大规模同时使用两者的地方。为 STL 写规范时，委员会发现不知道该怎样描述模板与异常之间的相互作用；Myers、Colvin、Abrahams 等人研究后认为，问题在于资源（更一般地说是不变量）与异常的关系（HOPL III §5.3）。

David Abrahams 在 1997 年提出的三个保证成了描述整个标准库的框架：

- **基本保证**：操作抛出异常后，不变量仍然成立，没有资源泄漏；
- **强保证**：操作要么成功，要么抛出异常并使状态保持操作前的样子；
- **不抛出保证**：操作不会抛出异常。

标准库的所有操作至少提供基本保证（前提是用户的析构函数不抛出），关键操作提供强保证或不抛出保证。今天这些保证分散在各处条文里：[[res.on.exception.handling]] 规定库函数何时可以抛出异常，[[string.require#2]] 规定 `basic_string` 的成员抛出异常时没有其他效果，`vector::push_back` 等操作各自规定了强保证。

## C++03 的两项修正

C++03 是一次纯修正，库方面最常被提到的是 [[LWG69]]：Koenig 在 1998 年提出 `vector` 的元素是否必须连续存储，C++98 的文字没有要求，C++03 明确规定必须连续。从此 `&v[0]` 可以当作 C 数组传给 C 接口。`string` 的连续存储要到 C++11 才写进标准（[[LWG530]]）。

## 今天条文里的痕迹

| 今天的条文 | 来历 |
|---|---|
| [[iterator.cpp17]] 的 *Cpp17* 具名要求与 [[iterator.concepts]] 的概念并存 | 1994 年的需求表，C++20 用概念重写 |
| [[std.iterator.tags]] 的标签类、[[iterator.traits]] | 1995 年前后为标签派发和 traits 设计 |
| [[default.allocator]] 只剩 `allocate`、`allocate_at_least`、`deallocate` | 为分段内存设计的成员先被允许忽略，再弃用、移除 |
| [[allocator.traits]] 仍有 `pointer`、`size_type`、`difference_type` | 1994 年分配器需求表里的条目 |
| `basic_string<charT, traits, Allocator>`、`basic_ostream<charT, traits>` 的 `traits` 参数 | 1994–1995 年 iostream 与 string 的模板化 |
| [[string.require#4]] 的失效列表；[[diff.cpp03.strings]] | C++11 排除写时复制实现 |
| `unordered_map` 这个名字 | 避开 C++98 之后各家互不兼容的 `hash_map` |
| [[vector.bool]] 不满足容器要求 | 1998–2009 年的讨论没有找到不破坏旧代码的改法 |
| [[zombie.names]] 里的 `auto_ptr`、`auto_ptr_ref` | C++11 弃用、C++17 移除 |

## 时间线

| 时间 | 事件 |
|---|---|
| 1984–1989 | stream I/O 库、复数库；Cfront 2.0 带来 Jerry Schwarz 重写的 iostream |
| 1993 年底 | Stepanov 在标准委员会会议上报告泛型编程 |
| 1994 年 3 月 | STL 提案在委员会上完整介绍 |
| 1994 年 7 月 | 删去约三分之二的 STL 纳入工作草案；同次会议加入 valarray |
| 1995 | traits 技术发表；偏特化加入 C++；哈希表提案没赶上 C++98 |
| 1997 | 异常安全的三个保证；`auto_ptr_ref` |
| 1998 | C++98；[[LWG96]] 指出 `vector<bool>` 不是容器 |
| 2003 | C++03：`vector` 必须连续存储 |
| 2003–2005 | 无序容器提案 [[N1456]] 进入 TR1 草案 [[N1836]] |
| 2008–2009 | [[N2668]] 排除写时复制 `string`；[[N2982]] 确立 `allocator_traits`；LWG96 以 NAD 关闭 |
| 2011 | C++11：无序容器、`unique_ptr`、`allocator_traits`；弃用 `auto_ptr` |
| 2015 | GCC 5 默认启用不使用写时复制的 `std::string` |
| 2017 | C++17：移除 `auto_ptr`；弃用 `std::allocator` 的冗余成员；引入 `pmr` |
| 2020 | C++20：移除这些冗余成员；迭代器概念与 ranges |

## 参考资料

- Bjarne Stroustrup. *A History of C++: 1979–1991*. HOPL II, 1993.
- Bjarne Stroustrup. *Evolving a language in and for the real world: C++ 1991–2006*. HOPL III, 2007. §4.1（STL）、§4.2（其他库组件）、§5.3（异常安全）、§6（C++03 与库技术报告）。
- Al Stevens. *Al Stevens Interviews Alex Stepanov*. *Dr. Dobb's Journal*, 1995 年 3 月。
- Graziano Lo Russo. *An Interview with A. Stepanov*（stepanovpapers.com 转载）。
- Alexander Stepanov, Meng Lee. *The Standard Template Library*. HP Labs 技术报告 HPL-94-34, 1994；修订版 1995。
- Nathan C. Myers. *Traits: a new and useful template technique*. *C++ Report*, 1995 年 6 月。
- P. J. Plauger. *Standard C/C++: The Header &lt;valarray&gt;*. *C/C++ Users Journal*, 1997 年 8 月。
- Pablo Halpern. *Towards a Better Allocator Model*. [[N1850]], 2005；[[N2982]]。
- Matthew Austern. *A Proposal to Add Hash Tables to the Standard Library (revision 4)*. [[N1456]], 2003。
- A. Meredith 等. *Concurrency Modifications to Basic String*. [[N2668]], 2008。
- Herb Sutter. *Optimizations That Aren't (In a Multithreaded World)*. *C/C++ Users Journal*, 1999 年 6 月；GotW #84；[[N1847]]。
- Howard E. Hinnant. *On vector&lt;bool&gt;*, 2012；[[N1856]], 2005。
- Bill Gibbons, Greg Colvin. *Fixing auto_ptr*. J16/97-0090R1, 1997。
- [[LWG69]]、[[LWG96]]、[[LWG530]]、[[CWG84]]；[[P0174R2]]、[[P0619R4]]、[[N4190]]。
- GCC 5 Release Series: Changes, New Features, and Fixes（libstdc++ 部分）。
