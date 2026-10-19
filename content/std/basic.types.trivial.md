---
title: 平凡可复制类型
summary: 平凡可复制类型的对象可以按字节复制：存出去再拷回来、或在两个对象之间拷贝，值都会保留；对象获得值表示时具体得到哪个值，由一个值集合模型规定。
status: draft
related: basic.types, class.prop, basic.compound, bit.cast, intro.object, basic.lval, basic.indet
tags: 对象模型, memcpy, 指针来源
updated: 2026-10-19
---

!!! tldr
    - 平凡可复制类型的对象，字节复制到 `char`、`unsigned char` 或 `std::byte` 数组再拷回来，就恢复原来的值，即使原值不确定。
    - 在两个同类型的这种对象之间拷贝字节，目标得到源的值。`memcpy`、`bit_cast` 和用 `memcpy` 做类型双关，都以此为依据。
    - 基类子对象和 `[[no_unique_address]]` 成员不在保证之内，因为它们的尾部填充可能被别的对象占用。
    - 对不是平凡可复制的类型（如 `std::string`），`memcpy` 什么都不保证。
    - 一种位模式可以不对应任何值（如 `bool` 的 `0x02`），对指针也可以对应多个值；获得这种位模式时，从中挑一个能让程序有定义行为的值。

[[basic.types.general#7]] 定义了[[g:trivially-copyable-type|平凡可复制类型]]（trivially copyable type）：标量类型、平凡可复制类（[[class.prop#1]]）、它们的数组以及 cv 版本。本节说明这个类别保证了什么：对这些类型，按字节复制就是按值复制。

## 字节存出去再拷回来（¶3）

```cpp run ok
#include <cstring>
#include <cstddef>

struct T { int a; double b; char c; };   // 平凡可复制，含填充

int main() {
  constexpr std::size_t N = sizeof(T);
  std::byte buf[N];
  T obj{1, 2.5, 'x'};
  std::memcpy(buf, &obj, N);   // 存出去
  obj.a = 100; obj.c = 'y';    // 中间可以修改 obj
  std::memcpy(&obj, buf, N);   // 拷回来：每个标量子对象恢复原值
  return (obj.a == 1 && obj.b == 2.5 && obj.c == 'x') ? 0 : 1;
}
```

这是标准例 1 的可运行版本。

¶3 如果平凡可复制类型 `T` 的对象不是潜在重叠子对象（见下文），那么无论它是否持有 `T` 的有效值，组成它的底层字节都可以复制到 `char`、`unsigned char` 或 `std::byte` 的数组里，例如用 `std::memcpy` 或 `std::memmove`。把数组内容复制回这个对象，对象就获得它原来的值表示。获得值表示的确切含义见后文的值集合模型；对整数、浮点这类类型，结果就是原值。

有两点值得注意：

- 无论是否持有有效值。对象的值即使是不确定的（[[basic.indet]]），也可以先存再恢复。保存上下文、事务回滚这类代码只复制字节，不解释字节，因此是合法的。
- 中转数组的元素类型只能是 `char`、`unsigned char` 或 `std::byte`。这与 [[basic.lval#11]] 允许通过这三种类型访问任何对象的字节相对应。`signed char` 不在其中。

## 在两个对象之间拷贝（¶4）

```cpp run ok
#include <cstring>

struct Point { int x, y; };

int main() {
  Point a{1, 2}, b{};
  std::memcpy(&b, &a, sizeof(Point));   // b 获得 a 的值表示
  return (b.x == 1 && b.y == 2) ? 0 : 1;
}
```

¶4 对两个不同的这种对象 `obj1` 和 `obj2`，把 `obj1` 的底层字节复制到 `obj2`，`obj2` 就获得 `obj1` 的值表示。

标准例 2 的注释说的是，复制之后 `*t1p` 中每个平凡可复制类型的子对象都含有与 `*t2p` 对应子对象相同的值。保证的是值相同，不是字节相同。填充字节是否一致，标准不关心。

## 保证不覆盖的情况

### 潜在重叠子对象

[[g:potentially-overlapping-subobject|潜在重叠子对象]]（potentially-overlapping subobject）指基类子对象和带 `[[no_unique_address]]` 的非静态数据成员（[[intro.object#7]]）。ABI 可以把派生类的成员放进基类的尾部填充里，于是按 `sizeof(Base)` 整块写入基类子对象，会覆盖不属于它的字节：

```cpp run
#include <cstdio>
#include <cstring>
#include <type_traits>

struct Base {
  int i;
  char get() const { return c; }
private:
  char c = 0;  // 访问控制不同：Base 不是标准布局，
};             // Itanium ABI 允许复用它的尾部填充
struct Derived : Base { char d; };

static_assert(std::is_trivially_copyable_v<Base>);

int main() {
  Derived x{};
  x.d = 'Z';
  Base b{};
  Base& rb = x;                        // 基类子对象：潜在重叠
  std::memcpy(&rb, &b, sizeof(Base));  // 不在保证范围内
  std::printf("%zu %zu %d\n", sizeof(Base), sizeof(Derived), x.d);
}
```

本机（arm64 macOS，Clang 23）输出 `8 8 0`：`Derived` 和 `Base` 一样大，`d` 就放在 `Base` 的尾部填充里，被这次 `memcpy` 清零了。x86-64 Linux 上布局相同。

### 不是平凡可复制的类型

对其他类型，本节不作任何保证，标准没有说复制之后目标对象持有什么值。用 `memcpy` 覆盖一个 `std::string` 就是这样：

```cpp run ub
#include <cstring>
#include <string>

int main() {
  std::string a = "a fairly long string that defeats SSO";
  std::string b;
  std::memcpy(static_cast<void*>(&b), &a, sizeof a);  // UB：string 不是平凡可复制的
}   // a 和 b 析构时释放同一块堆内存
```

实践中的后果取决于字符串长短：

- 长字符串的字符放在堆上。复制之后 `a` 和 `b` 的内部指针指向同一块堆内存，两次析构就是重复释放。本机用 `-fsanitize=address` 运行，ASan 报告 `attempting double-free`。
- 短字符串可能使用小字符串优化（SSO），字符直接存在对象内部。如果实现的内部指针指向对象自己的缓冲区（libstdc++ 就是这样），复制过去的指针仍然指向 `a` 内部，`a` 销毁后 `b` 就悬垂了。

GCC 对这类调用有 `-Wclass-memaccess` 警告。

### const 对象

¶3 和 ¶4 说的是复制字节使对象获得值表示，但修改 const 完整对象本身就是 UB（[[basic.life]]、[[dcl.type.cv]]）。平凡可复制不能用来绕过 const。

## 获得值表示时得到哪个值（¶1–¶2）

对 `int` 来说，拷回原来的字节就得到原来的值，这一点不言自明。但有两种情况需要更精确的规则：一种位模式可能不对应任何值，也可能对应不止一个值。

### 值集合模型

¶1 为每个平凡可复制类型 `T` 建立了这样一个模型：

1. `T` 有一个由实现定义的、离散的**值**（value）的集合。
2. 对象的每一种可能的值表示，对应这个集合的一个子集，不同的值表示对应的子集互不相同。
3. 所有子集合起来就是整个值集合。对除对象指针以外的标量类型，每个子集至多有一个值。
4. 有些操作会使对象[[g:acquire-value-representation|获得值表示]]（acquire a value representation）：对象的值被替换为对应子集中的某个成员。具体选哪个未指定，但选的是能让程序具有定义行为的那一个，如果存在的话。

!!! std
    the object's value is replaced with an unspecified member of the corresponding subset that would result in the program having defined behavior, if any.

这种只要有一种选择能让程序合法、就按那种选择解释的规则，常被称为**天使式选择**（angelic choice）。

### 位模式不对应任何值：`bool`

至多一个，意味着子集可以是空的。`bool` 通常占 8 位，但只有 `0x00` 和 `0x01` 对应 `false` 和 `true`（[[basic.fundamental#10]]），其余 254 种位模式在主流实现上不对应任何值。

```cpp run ub
#include <cstdio>
#include <cstring>

int main() {
  unsigned char byte = 2;
  bool b;
  std::memcpy(&b, &byte, 1);  // b 获得值表示 0x02，它不对应任何 bool 值
  if (b)  std::puts("true");  // UB
  if (!b) std::puts("false");
}
```

本机 Clang 23 / arm64 上，`-O0` 运行打印 `true`，`-O2` 运行打印 `false`，同一个程序表现不同。加 `-fsanitize=undefined` 运行，UBSan 报告 `load of value 2, which is not a valid value for type 'bool'`。

`std::bit_cast` 明确规定了这种情况：结果中如果有对象得不到值，行为未定义（[[bit.cast#3]]）。

### 位模式对应多个值：指针

对对象指针，一个值表示可以对应多个值。¶2 的注 1 举了一种情况：同一个地址上，可以有指向某个已经销毁的旧对象的指针，也可以有指向之后在同一位置分配的新对象的指针，它们所在存储的存续期互不重叠。

另一种情况是尾后指针。`int a, b;` 中如果 `b` 恰好紧跟在 `a` 后面，`&a + 1` 和 `&b` 的位完全相同，但前者是 `a` 的尾后指针，并不指向 `b`（[[basic.compound#3]]）。

所以把指针的字节拷回来时，标准不能简单地说得到原来的值，因为 ¶4 那样在对象之间复制时，目标对象并不知道源对象当时持有哪一个。天使式选择回答了这个问题：从候选值里挑一个能让程序有定义行为的值。

```cpp run ok
#include <cstring>

int main() {
  int x = 42;
  int* p = &x;
  unsigned char buf[sizeof p];
  std::memcpy(buf, &p, sizeof p);   // 字节存出去
  int* q;
  std::memcpy(&q, buf, sizeof q);   // q 获得 p 的值表示
  return *q == 42 ? 0 : 1;          // OK：能让这里有定义的值就是指向 x 的指针
}
```

整数转换为指针时，[[expr.reinterpret.cast#5]] 用了同样的措辞：选一个能让程序有定义行为的指针值，没有这样的值时行为未定义。

!!! note "这套模型是 C++23 之后的新措辞"
    C++23 及以前，这条保证只是 [[basic.types.general]] 里的两句话：字节存出去再拷回来，对象随后持有原值；在两个对象之间拷贝字节，目标持有与源相同的值。当前草案把它拆成独立的子条款，引入值集合和获得值表示，主要就是为了回答上面的指针问题。[[basic.compound]] ¶4–¶6 关于指针何时有效的规则是同一次修改的一部分。

## 与其他工具的关系

| 工具 | 类型要求 | 与本节的关系 |
|---|---|---|
| `std::memcpy`、`std::memmove` | 无 | 先在目标处隐式创建对象（[[intro.object#13]]），再复制字节；目标是平凡可复制类型的对象时，¶3、¶4 给出复制后的值 |
| `std::bit_cast`（[[bit.cast]]） | 源和目标都平凡可复制，大小相等 | 结果中的对象获得值表示，得不到值时 UB；可以用于常量求值 |
| `std::atomic<T>` | `T` 平凡可复制 | 原子操作按值表示比较和交换；C++20 起 `compare_exchange` 忽略填充位 |
| `std::start_lifetime_as<T>`（[[obj.lifetime]]） | `T` 是完整的隐式生存期类型 | 在已有的字节上开始 `T` 的生存期，把这些字节当作 `T` 的值表示 |

!!! note "类型双关的正确写法"
    想把 `float` 的位当作 `std::uint32_t` 看，C++20 起用 `std::bit_cast<std::uint32_t>(f)`，之前用 `std::memcpy(&u, &f, sizeof u)`。两种写法都依赖本节：两个类型都平凡可复制，目标获得的值表示被解释为一个 `uint32_t` 的值。写成 `*(std::uint32_t*)&f` 则违反 [[basic.lval#11]] 的别名规则，是 UB。

!!! impl
    - GCC 和 Clang 都把 `memcpy` 当作内建函数，长度固定的小 `memcpy` 会被编译成一两条加载和存储指令，所以用它做类型双关没有性能损失。
    - libc++ 和 libstdc++ 的 `std::copy`、`std::uninitialized_copy` 在元素类型平凡可复制时改用 `memmove`。
    - LLVM IR 里，按字节复制指针时保留指针的来源（provenance，即指针指向哪个对象的信息），这与 ¶1 中一个值表示对应多个指针值的模型相符。

## 历史与演进

!!! history
    - C++98 的这条保证只针对 POD 类型，并排除了基类子对象，措辞是对象随后持有原值。
    - C++11 把范围从 POD 放宽到平凡可复制类型，因为能否 `memcpy` 与是否标准布局无关。
    - C++17 加入 `std::byte` 作为合法的中转缓冲区类型。
    - C++20 随 `[[no_unique_address]]` 把排除的对象从基类子对象改为潜在重叠子对象；加入 `std::bit_cast`；规定 `memcpy`、`memmove` 隐式创建对象（[[P0593R6]]）。
    - C++23 之后的草案把这部分拆成独立的子条款 6.9.2，引入值集合和获得值表示的模型。

## 常见误解

!!! pitfall "`memcmp` 相等就是值相等"
    本节只保证复制保留值，不保证值相等等价于字节相等。填充字节、`+0.0` 和 `-0.0`、多种 NaN 位模式，以及来源不同的指针，都会让两者不一致。需要按字节比较或哈希时，先检查 `std::has_unique_object_representations_v<T>`（[[basic.types]]）。

!!! pitfall "`signed char` 缓冲区也可以"
    ¶3 只列出 `char`、`unsigned char` 和 `std::byte`。用 `signed char` 数组中转在实践中能工作，但不在标准的保证之内。

## 思考题

!!! question "1. `int* p = new int(1); delete p; int* q; std::memcpy(&q, &p, sizeof p);` 有 UB 吗？之后执行 `if (q) {}` 呢？"

<details markdown="1">
<summary>答案</summary>

复制本身没有 UB。¶3、¶4 说无论对象是否持有有效值都可以复制字节，而且在当前草案中，存储释放之后指针的值本身并不改变，只是在之后的求值中不再有效（[[basic.compound#6]]）。`q` 获得 `p` 的值表示。

`if (q)` 是布尔转换，用到了一个在该求值中无效的指针值，按 [[basic.compound#6.2]] 是实现定义行为，不是 UB。只有 `*q` 这样的间接才是 UB。
</details>

!!! question "2. ¶1 为什么说除对象指针外的标量类型，每个子集至多一个值，而不说恰好一个？"

<details markdown="1">
<summary>答案</summary>

至多一个允许子集为空，也就是有些位模式不对应任何值。最典型的是 `bool`：只有两个值，值表示却通常有 8 位。如果要求恰好一个，实现就得给 `0x02` 规定一个 `bool` 值，编译器也就不能再假定 `bool` 只能是 0 或 1。空子集加上 [[bit.cast#3]] 中得不到值则 UB 的规定，使这种情况明确成为 UB。
</details>
