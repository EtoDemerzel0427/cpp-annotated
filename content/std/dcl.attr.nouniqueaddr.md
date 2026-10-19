---
title: no_unique_address 属性
summary: "[[no_unique_address]] 让数据成员可以与其他成员重叠：空成员可以不占空间，尾部填充可以给后面的成员用；同类型的子对象仍然要有不同地址，是否真的压缩由实现决定。"
status: done
since: c++20
papers: P0840R2
related: intro.object, dcl.attr.grammar, class.mem, class.derived, expr.sizeof, basic.types.trivial, basic.life
tags: 属性, 布局, 空基类优化, ABI
updated: 2026-10-19
---

!!! tldr
    - 空类作为普通成员至少占 1 字节，加上对齐往往更多；标上 `[[no_unique_address]]` 后可以不占空间，与别的成员共用地址。
    - 同类型的两个子对象仍然必须地址不同，所以两个同类型的空成员不能都被压掉。
    - 是否真的压缩由实现决定。GCC 和 Clang 会压缩，MSVC 忽略它，另外提供 `[[msvc::no_unique_address]]`。
    - 这样的成员是潜在重叠子对象：`sizeof` 给出的是类型大小，可能比它实际独占的字节多，所以不能对它 `memcpy` 整个 `sizeof`。
    - 增删这个属性会改变类的布局，是破坏 ABI 的修改。

## 空成员为什么占空间

```cpp run ok
struct Empty {};
struct Plain { Empty e; int i; };
struct Packed { [[no_unique_address]] Empty e; int i; };

static_assert(sizeof(Empty) == 1);   // 完整对象至少 1 字节
static_assert(sizeof(Plain) == 8);   // 1 字节 + 3 字节填充 + int
static_assert(sizeof(Packed) == 4);  // e 与 i 共用地址
int main() {}
```

上面的大小是本机 Clang 23 的结果。C++ 要求每个完整对象至少占 1 字节，这样不同的对象才有不同的地址。一个没有任何数据成员的类作为成员时也不例外，再加上后面 `int` 的对齐，`Plain` 白白多了 4 字节。

无状态的分配器、删除器、哈希函数、比较函数都是这样的空类，几乎所有容器和智能指针都要存一个。C++20 之前，唯一能让它们不占空间的办法是**空基类优化**（empty base optimization，EBO）：空类作为基类时可以不占字节。于是标准库实现里到处是继承自分配器的 compressed pair。这种写法很别扭：继承会带来名字冲突，`final` 类无法继承，基类的虚函数还可能被意外覆盖。

[[P0840R2]] 引入了 `[[no_unique_address]]`，让数据成员也能做到这一点。

## 规则（¶1–¶2）

¶1 `no_unique_address` 规定一个非静态数据成员是**潜在重叠子对象**（[[g:potentially-overlapping-subobject|potentially-overlapping subobject]]，[[intro.object#7]]）。它不带参数，可以用于除位域以外的非静态数据成员。基类子对象本来就是潜在重叠子对象，这个属性让成员获得了同样的地位。

¶2 的注解释了这意味着什么：这个成员可以与另一个成员或基类共用地址；对象末尾本来要插入的填充，也可以用来存放其他成员。

¶2 还建议：只有当这个属性确实能让潜在重叠子对象的大小为零时，`__has_cpp_attribute(no_unique_address)` 才应非零。

标准的例子是一个哈希表：

```cpp run ok
struct Bucket;
template<typename Key, typename Value,
         typename Hash, typename Pred, typename Allocator>
class hash_map {
  [[no_unique_address]] Hash hasher;
  [[no_unique_address]] Pred pred;
  [[no_unique_address]] Allocator alloc;
  Bucket* buckets;
};

struct H {}; struct P {}; struct A {};
static_assert(sizeof(hash_map<int, int, H, P, A>)
              == sizeof(void*));   // 本机 Clang 23 成立
int main() {}
```

`Hash`、`Pred`、`Allocator` 都是空类型时，它们可以和 `buckets` 共用地址，整个对象只有一个指针大。

## 何时为零大小，何时可以共用地址

属性本身只说成员是潜在重叠子对象，具体效果由 [[intro.object]] 的两段规定。

[[intro.object#8]] 规定了零大小。一个对象只要满足下面任何一条，就有非零大小：不是潜在重叠子对象；不是类类型；有虚函数或虚基类；有非零大小的子对象或非零长度的无名位域。剩下的对象里，没有非静态数据成员的标准布局类的基类子对象大小为零；其余情况下何时为零大小由实现定义 {{impl}}。

所以对 `[[no_unique_address]]` 成员，标准并不保证它一定是零大小。完全忽略这个属性的实现也符合标准，这与 [[dcl.attr.grammar#8]] 的可忽略性一致。

[[intro.object#10]] 规定了地址。两个生存期重叠的对象可以有相同的地址，情形之一（¶10.3）是：它们是同一个完整对象的子对象，至少一个是零大小的，而且两者的类型不相似。其他情况下它们必须地址不同、占据不相交的字节。零大小子对象的地址，是它所在完整对象的存储中某个未指定字节的地址。

```cpp run impl
#include <cstdio>
struct Empty {};
struct Empty2 {};
struct B { [[no_unique_address]] Empty e1;
           [[no_unique_address]] Empty e2; int i; };
struct C { [[no_unique_address]] Empty e1;
           [[no_unique_address]] Empty2 e2; int i; };
int main() {
  B b; C c;
  std::printf("B=%zu C=%zu\n", sizeof(B), sizeof(C));
  std::printf("B: %d\n", (void*)&b.e1 == (void*)&b.e2);
  std::printf("C: %d\n", (void*)&c.e1 == (void*)&c.e2);
}
```

本机输出 `B=4 C=4`、`B: 0`、`C: 1`。`B` 的两个成员类型相同，地址必须不同，Clang 把 `e1` 放在偏移 0、`e2` 放在偏移 1，两者都与 `int` 重叠，整个类仍是 4 字节。`C` 的两个成员类型不同，可以共用同一个地址。

同类型对象地址不同，是 C++ 对象模型给出的身份保证：`&b.e1 != &b.e2` 可以被程序依赖，比如用地址作为 map 的键。

## 尾部填充复用

¶2 注中的另一种压缩，是让后面的成员占用一个非空成员的**尾部填充**（tail padding），即对象末尾为了对齐而补上的字节。

```cpp run impl
#include <cstdio>
struct Pod    { int i; char c; };              // 平凡的 C 风格结构体
struct NonPod { int i; char c; NonPod() {} };  // 有用户提供的构造函数

struct T1 { [[no_unique_address]] Pod p;    char d; };
struct T2 { [[no_unique_address]] NonPod p; char d; };
struct T3 { NonPod p; char d; };

int main() {
  std::printf("T1=%zu T2=%zu T3=%zu\n", sizeof(T1), sizeof(T2), sizeof(T3));
}
```

本机输出 `T1=12 T2=8 T3=12`。`NonPod` 占 8 字节，其中最后 3 字节是尾部填充，`T2` 把 `d` 放进了这 3 字节里。

`T1` 没有被压缩，这是 Itanium C++ ABI（GCC 和 Clang 在 Linux、macOS 上使用的 ABI）的规则：只有不属于布局意义上的 POD（大致相当于 C++03 的 POD）的类型，尾部填充才可以复用。这条规则原本是为基类制定的，`[[no_unique_address]]` 成员沿用了它。C 风格的结构体常被 `memcpy` 整体复制，连尾部填充一起；如果复用它们的尾部填充，这类代码就会写坏相邻的成员。

### sizeof 不再等于可以安全复制的字节数

```cpp run
#include <cstdio>
#include <cstring>
struct Inner {
  int i; char c;
  Inner(int i = 0, char c = 0) : i(i), c(c) {}
};
struct Outer {
  [[no_unique_address]] Inner in;
  char d;   // 放在 in 的尾部填充里
};
int main() {
  Outer o{{1, 'a'}, 'D'};
  Inner src{2, 'b'};
  o.in = src;                              // 只写 in 自己的字节
  std::printf("d=%c\n", o.d);
  std::memcpy(&o.in, &src, sizeof(Inner)); // 连 d 一起覆盖
  std::printf("d=%d\n", o.d);
}
```

本机输出 `d=D`，然后是 `d=0`：`sizeof(Inner)` 和 `sizeof(Outer)` 都是 8，`memcpy` 覆盖 `in` 的 8 字节时把 `d` 也写掉了。编译器生成的赋值只复制 `Inner` 自己的数据（Itanium ABI 称为 dsize），不碰尾部填充，所以没有问题。

标准中有两处与此对应。[[expr.sizeof#2]] 规定，对潜在重叠子对象使用 `sizeof`，得到的是类型的大小，而不是子对象实际占用的大小。[[basic.types.trivial#3]] 允许把可平凡复制类型的对象逐字节复制出去再复制回来，但明确排除了潜在重叠子对象。

基类子对象一直有同样的问题。所以泛型代码里拿到一个引用或指针，用 `memcpy(&x, &y, sizeof x)` 优化可平凡复制类型的赋值是不安全的：你不知道 `x` 是不是某个更大对象里的潜在重叠子对象。

## 其他后果

- 透明替换：在潜在重叠子对象的存储上用 placement new 创建一个同类型的新对象，新对象不会成为外层对象的子对象（[[intro.object#2]] 第 2.3 项），原来的成员名和指针也不会自动指向它（[[basic.life#9]]）。
- `offsetof`：多个空成员可以有相同的偏移，与其他成员的偏移也可能相同。
- 与 C 的布局兼容：一旦发生压缩，类的布局就不再与对应的 C 结构体一致，需要与 C 共享的结构体不要用这个属性。
- ABI：增删这个属性会改变布局，属于破坏 ABI 的修改。

!!! impl "MSVC 与 `msvc::no_unique_address`"
    MSVC 接受 `[[no_unique_address]]`，但不产生任何效果。MSVC 承诺 VS 2015 以来的各版本二进制兼容，不希望一个标准属性在用户不知情的情况下改变布局。它另外提供了 `[[msvc::no_unique_address]]`，确实会压缩。以 MSVC ABI 为目标的 Clang（`-target x86_64-pc-windows-msvc`）行为相同：本机实测它对 `[[no_unique_address]]` 给出未知属性警告，`__has_cpp_attribute(no_unique_address)` 为 0，而 `[[msvc::no_unique_address]]` 能让空成员不占空间。

    可移植代码通常这样写：

    ```cpp
    #if defined(_MSC_VER)
    #  define NO_UNIQUE_ADDRESS [[msvc::no_unique_address]]
    #else
    #  define NO_UNIQUE_ADDRESS [[no_unique_address]]
    #endif
    ```

    两种行为都符合标准，因为何时为零大小本来就由实现定义。

## 与空基类优化的比较

| | 空基类优化 | `[[no_unique_address]]` |
|---|---|---|
| 用于 | 基类 | 非静态数据成员 |
| 名字冲突、意外覆盖 | 有风险 | 没有 |
| `final` 类 | 不能继承 | 可以用 |
| 同类型多个 | 不能重复直接继承同一个类 | 可以声明，但不能共用地址 |
| 零大小 | 标准布局的空基类保证为零 | 由实现定义 |
| MSVC | 多重继承下需要 `__declspec(empty_bases)` | 需要 `msvc::` 版本 |

## 历史与演进

!!! history
    - C++20 引入（[[P0840R2]]）。选择属性而不是新语法，是因为何时压缩本来就可以由实现决定，忽略它不会改变程序的含义。
    - 潜在重叠子对象这个术语也是这时引入的。此后 `sizeof`、逐字节复制的保证、透明替换、地址唯一性等规则都用它来表述，基类子对象和带这个属性的成员得到统一处理。

## 思考题

!!! question "思考题"
    在 Itanium ABI 下，下面三个类的 `sizeof` 各是多少？
    ```cpp
    struct E {};
    struct X { [[no_unique_address]] E e; char c; };
    struct Y { [[no_unique_address]] E e1; [[no_unique_address]] E e2; };
    struct Z { E e; [[no_unique_address]] E e2; };
    ```

<details markdown="1">
<summary>答案</summary>

- `X` 是 1。`e` 与 `c` 类型不同，可以共用地址。
- `Y` 是 2。`e1` 和 `e2` 类型相同，地址必须不同。两者都可以是零大小，但零大小子对象的地址也必须落在完整对象的某个字节上，两个不同的地址就需要至少 2 字节。
- `Z` 是 2。`e` 没有属性，占偏移 0 的 1 字节；`e2` 与它同类型，不能放在偏移 0，只能放在偏移 1。

本机 Clang 23 用 `static_assert` 验证了这三个值。标准本身只保证同类型的子对象地址不同、完整对象大小非零，具体数值取决于 ABI。
</details>
