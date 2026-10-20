---
title: 平凡重定位（P2786 与 P1144）
summary: 把对象搬到新内存时，能不能用一次 memcpy 代替移动构造加析构：库里流行了二十年的做法，两份竞争提案在赋值语义、显式声明方式和 memcpy 是否足够上的分歧，P2786 进入 C++26 又被移出的经过，以及 libc++ 今天在 vector 扩容里已经做的事。
status: draft
order: 38
group: C++26
since: c++11
papers: P1144R12, P1144R13, P2786R13, P3233R0, P3236R1, P3559R0, P3516R2, P3915R0, P3920R0, P4197R0, CWG3049
related: class.prop, class.pre, lex.name, basic.life, intro.object, basic.types.trivial, obj.lifetime, library.class.props, vector.capacity, vector.modifiers, mem.poly.allocator.class, topics/special-members-and-elision, topics/object-model, topics/allocators-and-pmr, perf/allocation, perf/copies-and-moves, history/move-semantics
tags: 提案, 平凡重定位, 移动语义, 对象模型, vector, C++26
updated: 2026-10-19
---

!!! tldr
    - 重定位指把对象搬到新地址：在新位置移动构造，再析构旧对象。对 `std::unique_ptr` 这类类型，这两步合起来等于复制字节、忘掉源对象，称为平凡重定位。
    - Folly、BSL、Qt、Abseil 等库早就用自己的类型特征加 `memcpy` 做这件事，但按标准的对象模型，这样搬运非平凡可复制的对象是未定义行为。
    - P1144 只要一个性质：平凡可重定位就是可以 `memcpy`，而且要求类型的赋值与先析构再构造一致；P2786 把它拆成平凡可重定位和可替换两个性质，用 `trivially_relocatable_if_eligible` 这类上下文关键字声明，允许多态类型在搬运后修正 vptr。
    - P2786 在 2025 年初并入 C++26 工作草案，同年处理国家成员体意见时被整体移除（P3920R0）。当前草案的 [class.prop]、[obj.lifetime]、`<type_traits>` 里都没有平凡重定位。
    - libc++ 在内部用 `__libcpp_is_trivially_relocatable` 把 `vector` 扩容变成一次 `memcpy`。本机测得 `vector<unique_ptr<int>>` 的一次扩容比同布局但不可平凡重定位的类型快约 4 倍。

## 扩容时的一次移动加一次析构

`std::vector` 的容量用完时，要申请一块更大的内存，把旧元素搬过去，再释放旧内存。`reserve` 只要求元素可移动插入（[[vector.capacity#3]]），实现的做法是对每个元素做两步：在新内存里移动构造一个元素，再析构旧元素。

```cpp title="grow-count.cpp" run ok
#include <cstdio>
#include <memory>
#include <vector>

int moves = 0, dtors = 0;

struct Box {
  std::unique_ptr<int> p;
  explicit Box(int i) : p(new int(i)) {}
  Box(Box&& o) noexcept : p(std::move(o.p)) { ++moves; }
  ~Box() { ++dtors; }
};

int main() {
  std::vector<Box> v;
  v.reserve(4);
  for (int i = 0; i < 4; ++i) v.emplace_back(i);
  moves = dtors = 0;
  v.reserve(8);              // 重新分配，搬 4 个元素
  std::printf("moves=%d dtors=%d\n", moves, dtors);
}
```

本机 Clang 23（libc++）输出 `moves=4 dtors=4`。每次移动把源对象的指针置空，唯一的目的是让紧接着的析构函数什么也不做。两步合起来的净效果只是：新位置得到旧位置的字节，旧对象消失。

把对象从一个地址搬到另一个地址、源对象随之结束生存期，称为**重定位**（relocation）。如果对某个类型来说，重定位的效果等同于复制对象的字节并且不再理会源对象（不调用它的析构函数），就说这个类型是**平凡可重定位的**（trivially relocatable）。`std::unique_ptr`、`std::shared_ptr`、多数 `std::vector` 实现都是这样；对它们，扩容可以整块 `memcpy`。

为什么 `vector` 只在移动构造函数不抛出异常时才移动、否则退回复制，见 [[topics/special-members-and-elision]]。平凡重定位顺带解决了这个问题：`memcpy` 不会抛出异常。

## 标准里写不出来的 `memcpy`

### 库里的做法

很多库都给类型加了一个自己的特征，然后据此选择 `memcpy`。[[P3559R0]] 列出了它们的名字：Folly 的 `folly::IsRelocatable`、BSL 的 `bslmf::IsBitwiseMoveable`、Qt 的 `Q_IS_RELOCATABLE`、Abseil 的 `absl::is_trivially_relocatable`，等等。写法大致如下：

```cpp title="lib-relocate.cpp" run ub
#include <cstring>
#include <memory>
#include <new>
#include <type_traits>

template<class T>
struct is_relocatable : std::is_trivially_copyable<T> {};
template<class T>
struct is_relocatable<std::unique_ptr<T>> : std::true_type {};

template<class T>
void relocate_n(T* from, std::size_t n, T* to) {
  if constexpr (is_relocatable<T>::value) {
    std::memcpy(static_cast<void*>(to), from, n * sizeof(T));
  } else {
    for (std::size_t i = 0; i < n; ++i) {
      ::new (static_cast<void*>(to + i)) T(std::move(from[i]));
      from[i].~T();
    }
  }
}

int main() {
  using P = std::unique_ptr<int>;
  alignas(P) unsigned char a[sizeof(P)], b[sizeof(P)];
  ::new (static_cast<void*>(a)) P(new int(1));
  relocate_n(std::launder(reinterpret_cast<P*>(a)), 1,
             reinterpret_cast<P*>(b));
  P* q = std::launder(reinterpret_cast<P*>(b));
  int r = **q - 1;           // UB: b 里没有 unique_ptr 对象
  q->~P();
  return r;
}
```

这个程序在本机按预期返回 0，ASan 和 UBSan 也不报错，但按标准它的行为是未定义的。问题不在源对象：[[basic.life#6]] 允许不调用析构函数就结束一个对象的生存期，只要重用或释放它的存储。问题在目标位置。

[[basic.types.trivial#3]] 和 [[basic.types.trivial#4]] 只对平凡可复制的类型保证复制字节能复制出值；`memcpy` 能隐式创建对象（[[intro.object#13]]），但只创建隐式生存期类型的对象，而 `unique_ptr` 有用户提供的析构函数，两者都不是。所以 `memcpy` 之后，`b` 里没有任何 `unique_ptr` 对象，`*q` 访问的是一个不存在的对象。库作者依赖的是编译器不会利用这一点。

### 不能平凡重定位的类型

不是所有类型都可以这样搬。一个对象如果存有指向自己的指针，复制字节后，新对象里的指针仍然指向旧地址。libstdc++ 的 `std::string` 就是这样：短字符串存在对象内部的缓冲区里，数据指针指向这个缓冲区。

```cpp title="self-pointer.cpp" run ub
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>

struct SsoStr {                      // 仿 libstdc++ 的布局
  char* p;                           // 短串时指向自己的 buf
  char buf[16];
  explicit SsoStr(const char* s) : p(buf) { std::strcpy(buf, s); }
  SsoStr(SsoStr&& o) noexcept : p(buf) { std::strcpy(buf, o.p); }
  ~SsoStr() {}
};

int main() {
  void* from = std::malloc(sizeof(SsoStr));
  void* to   = std::malloc(sizeof(SsoStr));
  auto* s = new (from) SsoStr("hi");
  std::memcpy(to, s, sizeof(SsoStr));   // 假装平凡重定位
  std::free(from);                      // 源对象不析构，直接丢弃
  auto* t = static_cast<SsoStr*>(to);   // （t 甚至不指向一个对象）
  std::puts(t->p);                      // t->p 仍指向旧的 buf
  std::free(to);
}
```

本机加 `-fsanitize=address` 运行，ASan 在 `puts` 处报告 heap-use-after-free。移动构造函数会把 `p` 重新指向自己的 `buf`，复制字节则不会。同类的还有哨兵节点放在对象内部的 `std::list` 实现（首尾节点指回容器对象），以及把自己的地址登记到外部注册表的类型。libc++ 的 `std::string` 用一个标志位区分长短串，不存自指针，所以它可以平凡重定位。

因此，平凡可重定位不能由编译器对所有类型自动推出：用户写了移动构造函数和析构函数，编译器看不出两者合起来是不是等于复制字节。这需要一个规则来推断简单的类型，再加一个让作者声明的办法。

## 两份提案

### P1144：重定位等于移动加析构，平凡就是 `memcpy`

[[P1144R12]] 把**重定位操作**定义为一次移动构造紧接着析构源对象，由新函数 `std::relocate_at(source, dest)` 执行；如果类型平凡可重定位，这一操作就等于复制字节。它的规则有三部分：

1. 隐式推断。一个类如果合格的复制、移动构造函数，复制、移动赋值运算符和析构函数都不是用户提供的，没有虚函数和虚基类，所有成员和基类都平凡可重定位，它就是平凡可重定位的。平凡可复制的类型都包括在内。
2. 显式声明。`[[trivially_relocatable]]` 属性写在类定义上，可以带一个 `bool` 常量表达式作条件。它是一把不加检查的刀：即使某个成员本身不是平凡可重定位的，属性也让整个类成为平凡可重定位的，声明错了，依赖它的程序就是未定义行为。
3. 语义要求。新概念 `std::relocatable` 要求：如果类型可以赋值，赋值必须与先析构、再在原地构造效果相同。这条要求让 `vector::insert`、`vector::erase` 也能用字节搬运。

属性的措辞把语义说得很直接：

!!! note "P1144R12 [dcl.attr.trivreloc]"
    "specifies that a class type's relocation operation has no visible side-effects other than a copy of the underlying bytes, as if by the library function `std::memcpy`."

### P2786：两个独立的性质

[[P2786R13]] 也从移动加析构出发，但把问题拆成两个互相独立的性质：

- 平凡可重定位：移动构造加析构等价于库函数 `std::trivially_relocate` 的效果。注意它不说等价于 `memcpy`。
- **可替换**（replaceable）：对这个类型的对象做移动赋值，等价于先析构它、再从同一个 xvalue 移动构造。

两者都有隐式规则和显式声明。隐式规则要求类是 default-movable 的：移动构造、移动赋值选中的函数和析构函数都不是用户提供的，也没有被删除。显式声明用两个上下文关键字，写在类名后面，位置和 `final` 一样：

<div class="compare" markdown="1">

```cpp title="P1144 的写法"
struct [[trivially_relocatable]] Buf {
  Buf(Buf&&);
  Buf& operator=(Buf&&);
  ~Buf();
};
```

```cpp title="P2786 的写法"
struct Buf trivially_relocatable_if_eligible
           replaceable_if_eligible {
  Buf(Buf&&);
  Buf& operator=(Buf&&);
  ~Buf();
};
```

</div>

两段都没有判定标记：当前草案里既没有这个属性，也没有这两个关键字，本机 Clang 23 把右边一段当作变量声明而报错，左边一段只给出未知属性的警告。

`if_eligible` 的意思是：只有类本来就有资格时，关键字才起作用。资格要求没有虚基类，所有基类和非静态数据成员都平凡可重定位（对可替换性也类似）。成员不合格，关键字就被静默忽略，类照样不是平凡可重定位的。

P2786 还提供了库函数 `std::trivially_relocate(first, last, result)`。它是唯一被认可的平凡重定位手段：结束源对象的生存期、开始目标对象的生存期，不调用任何构造函数和析构函数。用户自己调用 `memcpy` 仍然不行。另一个函数 `std::relocate` 对平凡可重定位的类型调用它，对其他类型逐个移动加析构。

P2786 用一张表说明两个性质为什么是独立的（`string1` 指存有自指针的 `std::string` 实现，`string2` 指不存的；`list1`、`list2` 类似地指哨兵节点在对象内部和在堆上的 `std::list`）：

| | 不可替换 | 可替换 |
|---|---|---|
| 不可平凡重定位 | `pmr::list1<T>`、`tuple<pmr::string1>` | `list1<T>`、`string1` |
| 可平凡重定位 | `tuple<T&>`、`pmr::vector<T>`、`pmr::list2<T>` | `shared_ptr<T>`、`vector<T>`、`string2`、`list2<T>` |

## 分歧在哪里

### 赋值算不算数

`vector::erase` 的规格写的是赋值：被删元素之后的每个元素都由赋值运算符移到前一个位置，再析构最后一个（[[vector.modifiers#6]]）。对 `unique_ptr`，用 `memmove` 把后面的元素整体前移，结果完全一样；对另一些类型就不一样。

```cpp title="erase-assigns.cpp" run ok
#include <cstdio>
#include <tuple>
#include <vector>

int main() {
  int a = 1, b = 2, c = 3;
  std::vector<std::tuple<int&>> v{{a}, {b}, {c}};
  v.erase(v.begin());          // v[0] = std::move(v[1]); ...
  std::printf("a=%d b=%d c=%d  v: %d %d\n",
              a, b, c, std::get<0>(v[0]), std::get<0>(v[1]));
  std::get<0>(v[0]) = 100;
  std::printf("a=%d b=%d\n", a, b);
}
```

本机输出 `a=2 b=3 c=3  v: 2 3` 和 `a=100 b=3`。`tuple<int&>` 的赋值写的是被引用的变量，所以 `erase` 改写了 `a` 和 `b`，`v[0]` 仍然引用 `a`。如果 `erase` 改成搬运字节，`a`、`b`、`c` 都不会变，`v[0]` 会引用 `b`。

带分配器的类型也一样。`std::pmr::polymorphic_allocator` 在赋值时不传播（它的复制赋值被删除，[[mem.poly.allocator.class]]），赋值后目标保留自己的内存资源：

```cpp title="pmr-erase.cpp" run ok
#include <cstdio>
#include <memory_resource>
#include <string>
#include <vector>

int main() {
  std::pmr::monotonic_buffer_resource r1, r2;
  std::vector<std::pmr::string> v;
  v.emplace_back("first, a fairly long string", &r1);
  v.emplace_back("second, a fairly long string", &r2);
  v.erase(v.begin());            // v[0] = std::move(v[1])
  std::printf("v[0] uses r1? %d  r2? %d\n",
              v[0].get_allocator().resource() == &r1,
              v[0].get_allocator().resource() == &r2);
}
```

本机输出 `v[0] uses r1? 1  r2? 0`。搬运字节会让 `v[0]` 带着 `r2` 走。

这两个类型的移动构造加析构仍然等于复制字节：新对象引用同一个变量、使用同一个资源。所以它们在扩容时可以 `memcpy`，在 `erase` 时不可以。两份提案在这里分道：

- P1144 认为一个特征就够了，它对应库作者真正关心的性质：任何搬运都可以换成字节复制。代价是 `tuple<int&>` 和含 `pmr` 容器的类不算平凡可重定位，连扩容也享受不到 `memcpy`。
- P2786 认为两件事应分开：扩容只需要平凡可重定位，`erase`、`swap` 还需要可替换。这样 `pmr::vector` 可以在扩容时被 `memcpy`；但想优化 `erase` 的库必须同时检查两个特征。

[[P3233R0]] 针对 P2786 的早期版本指出，当时的模型无法区分 `tuple<int&>` 和 `unique_ptr`，因而 `erase` 一类操作得不到优化；P2786 后来的修订版加入了可替换这一性质作为回应。[[P3559R0]] 则认为第三方库已经用 `is_trivially_relocatable` 这个名字表示了 P1144 的含义，标准用同一个名字表示更弱的性质，这些库会把只满足 P2786 的类型错误地交给 `memswap`、`memmove`。

### 推断还是声明，声明是刀还是开关

两份提案的隐式规则差别不大，都要求特殊成员函数不是用户提供的。差别在显式声明：

- P1144 的属性是覆盖式的。[[P1144R13]] 举了一个例子：一个容器内部有 `offset_ptr` 这样存相对地址的成员，成员本身不能平凡重定位，但整个容器可以，作者用属性声明即可。P2786 的 `if_eligible` 做不到这一点。
- P2786 的关键字只在有资格时生效，好处是不会因为一个成员的实现改变而悄悄引入未定义行为。P2786 举的理由是：同一个 `std::list` 在不同标准库中可能可以或不可以平凡重定位，一个含 `std::list` 成员的类加上关键字，在两种实现上都良构，只是结果不同。[[P3236R1]] 反过来认为，这让每一层成员类型都必须先被标记，标记会层层向下蔓延。
- 属性可以在旧语言模式中由实现支持；上下文关键字只能用于新标准，而且改变了已有代码的含义。P2786 为此在 Annex C 加了一条：`struct C {}; struct C replaceable_if_eligible {};` 在 C++23 中声明了一个名为 `replaceable_if_eligible` 的变量，在 C++26 中则重复定义了 `C`。

### `memcpy` 够不够

P2786 的 `trivially_relocate` 规定目标对象的对象表示与源对象相同，但有一个例外：

!!! note "P2786R13 当时的 [obj.lifetime] 措辞"
    "except for any parts of the object representations used by the implementation to represent type information"

这个例外是为 arm64e 这类平台准备的。那里的指针认证会把 vptr 和它自身的存储地址一起签名，对象换了地址，vptr 必须重新签名，单纯复制字节得到的是一个无效的 vptr。P2786 因此允许多态类型平凡可重定位，由 `trivially_relocate` 负责修正；含多态成员的联合体是否平凡可重定位由实现定义，因为编译器不知道哪个成员是活跃的。

P1144 的作者和多个国家成员体意见认为，平凡可重定位必须意味着可以 `memcpy`、`realloc`，否则对 Qt 这类用 `realloc` 扩容的库毫无用处；因此多态类型不应算作平凡可重定位。[[P4197R0]] 把这一点列为 C++29 需要先回答的问题之一，还指出一个连带问题：把对象存在字节缓冲区里的类型擦除包装（如小对象优化的 `std::function`）复制字节时，不知道缓冲区里的对象需要修正。

### 三种立场下的常见类型

| 类型 | P1144R12 | P2786R13 平凡可重定位 | P2786R13 可替换 | libc++ 内部特征（本机） |
|---|---|---|---|---|
| `unique_ptr<int>`、`shared_ptr<int>` | 由库声明 | 由库声明 | 由库声明 | 是 |
| `tuple<int&>` | 否（赋值写穿引用） | 是 | 否 | 否 |
| `pmr::string`（无自指针的实现） | 否 | 可以 | 否 | 是 |
| 有自指针的 `string`、内含哨兵的 `list` | 否 | 否 | 是 | `list<int>`：否 |
| `struct A { const int i; };` | 是 | 否（见下文 CWG3049） | 否 | 是 |
| `struct W { virtual void f(); };` | 否 | 是 | 是 | 否 |

P1144 和 P2786 两列来自各自的措辞和示例。标准库类型是否平凡可重定位，两份提案都留给实现决定，所以前两行写作由库声明。最后一列是下文 libc++ 内部特征的实测值。

## 进入 C++26，又被移出

P2786R13 在 2025 年初并入 C++26 工作草案，带来了 [class.prop] 中的 default-movable、eligible for trivial relocation、trivially relocatable class、replaceable class 等定义，`<type_traits>` 中的 `is_trivially_relocatable`、`is_replaceable`、`is_nothrow_relocatable`，`<memory>` 中的 `trivially_relocate` 和 `relocate`，以及特性测试宏 `__cpp_trivial_relocatability` 和 `__cpp_lib_trivially_relocatable`。

国家成员体对 C++26 委员会草案提出的意见里，有一组针对平凡重定位。[[P3915R0]] 把它们分成几类，其中包括：删除 `*_if_eligible` 关键字；让平凡重定位等同于 `memcpy`；用 [[P3516R2]] 的 `uninitialized_relocate` 一类算法代替 `std::relocate`；允许 `const` 类型；以及一个措辞缺陷 [[CWG3049]]。

CWG3049 说明了隐式规则的一个漏洞。default-movable 要求移动赋值选中的函数没有被删除，而 `const` 成员和引用成员会让赋值运算符被隐式删除：

```cpp
struct A { const int i; };  // 平凡可复制，但按 P2786R13 不是平凡可重定位的
struct B { int& r; };       // 同上
```

这与 P2786 自己的设计说明（平凡可复制的类型都平凡可重定位）相矛盾。

委员会最终以共识把整个特性从 C++26 中移除，希望在 C++29 中解决这些问题。[[P3920R0]] 是移除用的措辞。它基本上是 P2786R13 的逆操作，但保留了 P2786 顺带做的几处改进，例如 [class.pre] 中 *class-property-specifier* 的文法和 [library.class.props] 的第一段。

### 当前草案怎么说

当前草案里没有平凡重定位的任何痕迹：

- [[class.prop]] 只定义平凡可复制类（¶1）、标准布局类（¶2）和隐式生存期类（¶8），没有 trivially relocatable 和 replaceable。
- [[lex.name]] 表 4 中有特殊含义的标识符是 `final`、`import`、`module`、`override`、`post`、`pre`，没有两个 `_if_eligible`。
- [[class.pre]] 保留了 *class-property-specifier* 这个文法名，但它只剩 `final` 一项，¶5 只讨论 `final`。
- [[library.class.props]] 只有一段：标准库类是否平凡可复制、标准布局或隐式生存期，除非另有说明都是未指明的。
- [[obj.lifetime]] 只有 `start_lifetime_as` 和 `start_lifetime_as_array`；[[meta.unary.prop]] 没有 `is_trivially_relocatable`；`<version>` 没有 `__cpp_lib_trivially_relocatable`。

由于这个特性从未出现在已发布的标准中，Annex C 里也没有相关条目。

[[P4197R0]] 整理了 C++29 需要先达成一致的设计问题：平凡重定位是复制字节还是专门的抽象机操作，是否允许非按位的重定位，是否支持常量求值，用户通过特征、关键字还是由编译器决定，以及是否必须同时提供非平凡重定位和完整的库支持。从 C++11 移动语义到这一次尝试的长线，见 [[history/move-semantics]]。

## libc++ 已经在做的事

标准不提供这个性质，但标准库的实现者可以在实现内部依赖编译器的行为。libc++ 有一个内部特征 `std::__libcpp_is_trivially_relocatable<T>`：默认等于 `is_trivially_copyable<T>`；类型如果声明了成员别名 `__trivially_relocatable` 并且它就是该类型本身，特征为真。

`unique_ptr`、`shared_ptr`、`weak_ptr`、`basic_string`、`vector`、`deque`、`array`、`pair`、`tuple`、`optional`、`variant`、`expected`、`locale` 等都声明了这个别名，多数带有依赖成员类型的条件。注释中解释了原因，例如 `basic_string` 只用一个标志位区分长短串，不存指向自身的指针。本机检查的结果：`unique_ptr<int>`、`string`、`pmr::string`、`pmr::vector<int>`、`tuple<string>` 为真；`tuple<int&>`、`function<void()>`、`list<int>` 为假。

这个特征真正被用来选择算法的只有一处：`vector`（以及它借助的 `__split_buffer`）重新分配时调用的内部函数 `__uninitialized_allocator_relocate`。条件同时满足时它直接 `__builtin_memcpy`，否则逐个移动构造再析构：

- 元素类型满足 `__libcpp_is_trivially_relocatable`；
- 分配器没有自定义的 `construct` 和 `destroy`（`std::allocator` 满足）；
- 不在常量求值中。

`erase` 和不需要重新分配的 `insert` 移动元素时仍然用赋值。所以 libc++ 实际采用的是 P2786 式的平凡可重定位（`pmr::string` 也为真），只在扩容这种不涉及赋值的场合使用，绕开了可替换性问题。

分配器那一条的效果可以从汇编看出：本机 `-O2` 下，`std::vector<std::pmr::string>` 的 `reserve` 调用 `memcpy`，而 `std::pmr::vector<std::pmr::string>` 的 `reserve` 逐个构造，因为 `polymorphic_allocator` 有自己的 `construct`（它做 [[g:uses-allocator-construction|uses-allocator construction]]）。

### 数一数，再量一量

把开头的 `Box` 接上 libc++ 的钩子，扩容就不再调用移动构造函数和析构函数：

```cpp title="hooked.cpp" run ifndr
#include <cstdio>
#include <memory>
#include <type_traits>
#include <vector>

int moves = 0, dtors = 0;

template<bool Hook>
struct Box {
  std::unique_ptr<int> p;
  explicit Box(int i) : p(new int(i)) {}
  Box(Box&& o) noexcept : p(std::move(o.p)) { ++moves; }
  ~Box() { ++dtors; }
  // libc++ 的内部钩子：声明移动加析构等价于 memcpy
  using __trivially_relocatable =
      std::conditional_t<Hook, Box, void>;
};

template<class T>
void grow(const char* name) {
  std::vector<T> v;
  v.reserve(4);
  for (int i = 0; i < 4; ++i) v.emplace_back(i);
  moves = dtors = 0;
  v.reserve(8);
  std::printf("%-8s moves=%d dtors=%d  *v[3]=%d\n",
              name, moves, dtors, *v[3].p);
}

int main() {
  grow<Box<false>>("plain");
  grow<Box<true>>("hooked");
}
```

本机输出 `plain moves=4 dtors=4  *v[3]=3` 和 `hooked moves=0 dtors=0  *v[3]=3`，ASan 和 UBSan 不报错。判定标为 IFNDR，是因为含双下划线的标识符保留给实现（[[lex.name#4]]），用户程序不应声明它；这里只用来观察 libc++ 的行为，不要在代码里这样做。它也说明了 P1144 属性那把刀的风险：库完全相信这个声明，`Box` 的计数副作用就这样消失了。

再比较 `std::unique_ptr<int>` 和一个布局、语义都相同，但写了空析构函数因而不可平凡重定位的类型：

```cpp title="reserve-bench.cpp" run ok
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <memory>
#include <vector>

struct Plain {                       // 与 unique_ptr 同样大小、同样语义
  std::unique_ptr<int> p;
  Plain() = default;
  Plain(Plain&&) noexcept = default;
  ~Plain() {}                        // 用户提供：不再平凡可复制
};

template<class T>
double reserve_ns_per_elem(std::size_t n) {
  std::vector<double> t;
  for (int s = 0; s < 31; ++s) {
    std::vector<T> v(n);
    auto a = std::chrono::steady_clock::now();
    v.reserve(2 * n);                // 一次重新分配
    auto b = std::chrono::steady_clock::now();
    asm volatile("" : : "r"(v.data()) : "memory");
    t.push_back(std::chrono::duration<double, std::nano>(b - a).count() / n);
  }
  std::nth_element(t.begin(), t.begin() + 15, t.end());
  return t[15];
}

int main() {
  for (std::size_t n : {1u << 10, 1u << 16, 1u << 22}) {
    double u = reserve_ns_per_elem<std::unique_ptr<int>>(n);
    double p = reserve_ns_per_elem<Plain>(n);
    std::printf("n=%-8zu unique_ptr %.3f  Plain %.3f ns/elem\n", n, u, p);
  }
}
```

本机（Apple M2 Pro，`-O2`）五次运行，每次取 31 个样本的中位数：

| 元素个数 | `unique_ptr<int>` | `Plain` | 倍数 |
|---|---|---|---|
| 1 024 | 0.16 – 0.33 ns/元素 | 0.57 – 1.02 ns/元素 | 3.1 – 3.7 |
| 65 536 | 0.14 – 0.28 ns/元素 | 0.62 – 1.10 ns/元素 | 3.9 – 4.8 |
| 4 194 304 | 0.17 – 0.26 ns/元素 | 0.69 – 0.97 ns/元素 | 3.8 – 4.1 |

测量时机器负载很高（load average 在 29 到 118 之间），绝对数值偏大且波动明显，倍数比较稳定。时间里包含新缓冲区的分配。`-O2` 汇编中，`unique_ptr` 版本的 `reserve` 在 `operator new` 之后只有一次 `bl _memcpy`；`Plain` 版本是一个循环，每个元素读指针、写到新位置、把源置零，再有第二个循环逐个检查指针是否为空并决定是否调用 `operator delete`。分配本身的代价见 [[perf/allocation]]。

## 编译器支持

本机 Clang 23.1.3 / libc++ 的状态与当前草案一致：

- `trivially_relocatable_if_eligible` 和 `replaceable_if_eligible` 不被识别为关键字；
- `std::is_trivially_relocatable_v`、`std::trivially_relocate` 不存在，`<version>` 不定义 `__cpp_lib_trivially_relocatable`。

但 Clang 保留了一些实现层面的东西。内建函数 `__builtin_is_cpp_trivially_relocatable(T)` 和 `__builtin_trivially_relocate` 仍然可用，前者按 P2786R13 的规则计算：本机上，只有虚函数的类为真，`struct A { const int i; }` 为假（正是 CWG3049 的情形），`unique_ptr<int>` 为假（标记它的关键字已经没有了）。预定义宏 `__cpp_trivial_relocatability` 仍定义为 `202502L`，在 `-std=c++17` 下也是如此。旧的 `__is_trivially_relocatable` 已被标为弃用。GCC 和 MSVC 本机未验证。

## 思考题

!!! question "1. 为什么 libc++ 敢对 `pmr::string` 用 `memcpy`"
    上文说 `pmr::string` 不可替换，`erase` 不能把它当字节搬运。libc++ 却让 `__libcpp_is_trivially_relocatable<pmr::string>` 为真。这会出错吗？

<details markdown="1">
<summary>答案</summary>

不会。libc++ 只在重新分配时使用这个特征：目标是未初始化的新内存，源对象随后被丢弃，标准要求的操作是移动构造加析构，不涉及赋值。`pmr::string` 的移动构造会带走源对象的内存资源，复制字节也是一样的效果。`erase` 涉及赋值，libc++ 在那里不用这个特征，[[vector.modifiers#6]] 要求的赋值次数照常发生。这正是 P2786 区分平凡可重定位与可替换的理由。

</details>

!!! question "2. 一个带 `const` 成员的类"
    `struct A { const int i; };` 是平凡可复制的吗？按 P1144R12 和 P2786R13，它是平凡可重定位的吗？

<details markdown="1">
<summary>答案</summary>

它是平凡可复制的：复制、移动构造函数平凡，复制、移动赋值运算符被删除因而不合格，析构函数平凡，满足 [[class.prop#1]]。P1144R12 把所有平凡可复制类型都算作平凡可重定位。P2786R13 的 default-movable 要求移动赋值选中的函数没有被删除，所以 `A` 不是平凡可重定位的，尽管 P2786 自己说明 `const` 成员不妨碍平凡重定位。这一矛盾就是 [[CWG3049]]，P2786 的作者在 [[P3915R0]] 中建议把条件改为没有被显式删除。本机 Clang 23 的 `__builtin_is_cpp_trivially_relocatable(A)` 为假，与 P2786R13 的原始措辞一致。

</details>
