---
title: no_unique_address 属性
summary: no_unique_address 让非静态数据成员成为潜在重叠子对象：空成员可以不占空间、与其他成员共享地址，非 POD 成员的尾部填充可以被复用；同类型子对象仍须地址不同；MSVC 忽略它而提供 msvc::no_unique_address
status: done
since: c++20
papers: P0840R2
related: intro.object, dcl.attr.grammar, class.mem, class.derived, expr.sizeof, basic.types.trivial, basic.life
tags: 属性, 布局, 空基类优化, ABI
updated: 2026-10-17
---

在 C++20 之前，C++ 中**唯一**能让一个子对象"不占空间"的办法是**空基类优化**（empty base optimization，EBO）：空类作为**基类**时可以不占任何字节，但作为**成员**时至少占 1 字节（再加上对齐填充，往往是 8 字节）。于是标准库实现里到处是这样的代码：为了让 `std::vector` 的分配器、`std::unique_ptr` 的删除器、`std::unordered_map` 的哈希函数不占空间，把它们**继承**下来（libstdc++ 的 `_Tuple_impl`、各种 "compressed pair"）。这很别扭：继承会引入名字冲突、`final` 类不能被继承、虚函数可能被意外覆盖。

`[[no_unique_address]]`（[[P0840R2]]）把同样的能力赋予**数据成员**。

## 规则（¶1–¶2）

¶1：

- `no_unique_address` 指定一个非静态数据成员是**潜在重叠子对象**（potentially-overlapping subobject，[[intro.object#7]]）；
- 不得带参数；
- 可以用于**非位域**的非静态数据成员。

¶2（注）：这样的成员可以与另一个非静态数据成员或基类**共享地址**，并且对象末尾通常会插入的**填充**可以被复用来存放其他成员。

推荐做法：除非这个属性能使某个潜在重叠子对象具有**零大小**，否则 `__has_cpp_attribute(no_unique_address)` 应为 0。（这一条正是为 MSVC 的情况量身定做的，见下文。）

标准例 1：

```cpp title="nua-hashmap.cpp" ok
struct Bucket;

template<typename Key, typename Value,
         typename Hash, typename Pred, typename Allocator>
class hash_map {
    [[no_unique_address]] Hash hasher;
    [[no_unique_address]] Pred pred;
    [[no_unique_address]] Allocator alloc;
    Bucket* buckets;
    // ...
public:
    // ...
};

struct H {}; struct P {}; struct A {};
static_assert(sizeof(hash_map<int, int, H, P, A>) == sizeof(void*));   // Itanium ABI 下成立

int main() {}
```

`Hash`、`Pred`、`Allocator` 都是空类型时，它们可以与 `buckets` 共享地址，整个对象只有一个指针大。

## 精确语义：来自 [intro.object]

属性本身只说"是潜在重叠子对象"，真正的规则散落在 [[intro.object]]：

**何时可以是零大小**（[[intro.object#8]]）：对象具有**非零大小**，如果它不是潜在重叠子对象、或不是类类型、或有虚函数/虚基类、或有非零大小的子对象（或非零长度的无名位域）。否则：若它是**没有非静态数据成员的标准布局类**的**基类**子对象，大小为零；**其余情况下何时为零大小由实现定义** {{impl}}。

注意最后一句：对 `[[no_unique_address]]` 成员，**标准不保证**它一定是零大小——是否真的压缩是实现定义的。这是"可忽略性"（[[dcl.attr.grammar#8]]）的直接体现：忽略这个属性的实现也是符合标准的。

**地址规则**（[[intro.object#10]]）：两个生存期重叠的非位域对象可以有相同的地址，如果……（¶10.3）它们都是同一个完整对象的子对象、至少一个是零大小的子对象，**并且它们的类型不相似**。否则它们必须有不同的地址、占据不相交的字节。

所以：**两个同类型的空成员不能共享地址**。

```cpp run title="nua-addresses.cpp" impl
#include <cstdio>

struct Empty {};
struct Empty2 {};

struct A { [[no_unique_address]] Empty e; int i; };
struct B { [[no_unique_address]] Empty e1; [[no_unique_address]] Empty e2; int i; };
struct C { [[no_unique_address]] Empty e1; [[no_unique_address]] Empty2 e2; int i; };
struct NoNUA { Empty e; int i; };

int main() {
    A a; B b; C c;
    std::printf("A=%zu B=%zu C=%zu NoNUA=%zu\n", sizeof(A), sizeof(B), sizeof(C), sizeof(NoNUA));
    std::printf("A: &e == &i ? %d\n", (void*)&a.e == (void*)&a.i);
    std::printf("B: &e1 == &e2 ? %d\n", (void*)&b.e1 == (void*)&b.e2);   // 必须为 0：同类型
    std::printf("C: &e1 == &e2 ? %d\n", (void*)&c.e1 == (void*)&c.e2);   // 可以为 1：类型不同
}
// Clang/Itanium ABI 输出：
// A=4 B=4 C=4 NoNUA=8
// A: &e == &i ? 1
// B: &e1 == &e2 ? 0
// C: &e1 == &e2 ? 1
```

为什么同类型不能重叠？因为 C++ 的对象模型承诺"同类型的两个不同对象有不同的地址"——`&b.e1 != &b.e2` 是用户可以依赖的身份判断（比如作为 map 的键）。在 `B` 中，Clang 把 `e2` 放在偏移 1（与 `i` 重叠，但 `i` 是 `int`，与 `Empty` 不相似），`e1` 放在偏移 0，整体仍然只有 4 字节。

**零大小子对象的地址**：是其完整对象所占存储中**某个未指定字节**的地址（[[intro.object#10]] 末句）。

## 尾部填充复用

¶2 注中的"对象末尾通常会插入的填充可以被复用"指的是另一种压缩：非空成员的**尾部填充**（tail padding）被后面的成员占用。

```cpp run title="nua-tail-padding.cpp" impl
#include <cstdio>

struct Pod   { int i; char c; };                         // C++03 意义的 POD
struct NonPod { int i; char c; NonPod() {} };            // 有用户提供的构造函数

struct T1 { [[no_unique_address]] Pod p;    char d; };
struct T2 { [[no_unique_address]] NonPod p; char d; };
struct T3 { NonPod p; char d; };

int main() {
    std::printf("T1=%zu T2=%zu T3=%zu\n", sizeof(T1), sizeof(T2), sizeof(T3));
}
// Clang/Itanium ABI 输出：T1=12 T2=8 T3=12
```

只有 `T2` 被压缩：`NonPod` 占 8 字节（4 字节 `int` + 1 字节 `char` + 3 字节尾部填充），`d` 被放进了 `p` 的尾部填充里。`T1` 没有压缩，这是 **Itanium C++ ABI** 的规则：只有**不是"用于布局目的的 POD"**（POD for the purpose of layout，大致是 C++03 的 POD 概念）的类型，其尾部填充才可以被复用——这一规则原本是为基类子对象制定的，`[[no_unique_address]]` 成员沿用了它。原因是历史兼容：C 风格的结构体可能被 `memcpy` 整体复制（包括尾部填充），复用它们的尾部填充会让这种代码破坏相邻成员。

### 尾部填充复用的后果：sizeof 不再是"可以安全复制的字节数"

[[expr.sizeof#2]]：对潜在重叠子对象使用 `sizeof`，结果是**类型**的大小，而**不是**子对象实际占用的大小（脚注：实际大小可能更小）。[[basic.types.trivial#3]]：可平凡复制类型的对象"其底层字节可以复制到 char 数组再复制回来"的保证，**明确排除了潜在重叠子对象**。

```cpp run title="nua-memcpy.cpp"
#include <cstdio>
#include <cstring>

struct Inner {
    int i; char c;
    Inner(int i = 0, char c = 0) : i(i), c(c) {}   // 非"布局 POD"：尾部填充可被复用
};
struct Outer {
    [[no_unique_address]] Inner in;
    char d;
};

int main() {
    Outer o{{1, 'a'}, 'D'};
    Inner src{2, 'b'};
    std::printf("sizeof(Inner)=%zu sizeof(Outer)=%zu\n", sizeof(Inner), sizeof(Outer));
    o.in = src;                                  // OK: 赋值只写 in 的值表示
    std::printf("after assignment: d=%c\n", o.d);
    std::memcpy(&o.in, &src, sizeof(Inner));     // 错误：不受 [basic.types.trivial]/3 保护，覆盖了 d
    std::printf("after memcpy: d=%d\n", o.d);
}
// Clang/arm64 输出：
// sizeof(Inner)=8 sizeof(Outer)=8
// after assignment: d=D
// after memcpy: d=0
```

同样的问题也存在于基类子对象（它们一直都是潜在重叠的）。这意味着泛型代码中"对可平凡复制的对象做 `memcpy(&x, &y, sizeof x)`"的优化，对**引用**或**指针**所指的对象是不安全的——你不知道它是不是某个更大对象中的潜在重叠子对象。编译器自己生成的平凡复制赋值也只复制 Itanium ABI 所说的"数据大小"（dsize，不含可复用的尾部填充）而不是 `sizeof`——上例中赋值没有破坏 `d` 正是因此。

## 其他后果

- **透明替换**：潜在重叠子对象不能被透明替换（[[intro.object#2]] 第 2.3 项，[[basic.life#9]]）。在 `[[no_unique_address]]` 成员上 placement new 一个新对象后，原来的名字和指针不会自动指向新对象。
- **`offsetof`**：对潜在重叠子对象的 `offsetof`，结果可能与常规理解不同（多个空成员可以有相同的偏移）。
- **与 C 的布局兼容**：一旦发生压缩，类的布局就不再能与对应的 C 结构体一一对应；需要与 C 共享的结构体不应使用该属性。
- **ABI**：添加或删除 `[[no_unique_address]]` 会改变类布局，是 ABI 破坏性修改。

## MSVC：`msvc::no_unique_address`

!!! impl "MSVC 忽略标准属性"
    MSVC 接受 `[[no_unique_address]]` 但**不产生任何效果**。按 ¶2 的推荐做法，这种实现应当把 `__has_cpp_attribute(no_unique_address)` 报告为 0——所以可移植代码不应只靠这个宏判断"是否会压缩"。原因是 ABI：MSVC 承诺跨版本二进制兼容（VS 2015 起），而 `[[no_unique_address]]` 如果生效会改变布局；MSVC 选择不让标准属性在用户毫不知情的情况下改变 ABI。

    MSVC 另外提供了 `[[msvc::no_unique_address]]`，语义与标准属性相同（真的压缩）。以 MSVC ABI 为目标的 Clang（clang-cl）也采用同样的做法。可移植代码通常写成：

    ```cpp
    #if defined(_MSC_VER)
    #  define NO_UNIQUE_ADDRESS [[msvc::no_unique_address]]
    #else
    #  define NO_UNIQUE_ADDRESS [[no_unique_address]]
    #endif
    ```

    这也是一个很好的"属性可忽略性"的实例：两种行为都符合标准，因为零大小与否本来就是实现定义的。

## 与空基类优化的对比

| | 空基类优化 | `[[no_unique_address]]` |
|---|---|---|
| 可用于 | 基类 | 非静态数据成员 |
| 名字冲突 / 意外覆盖 | 有风险 | 无 |
| `final` 类 | 不能继承 | 可以 |
| 同类型多个 | 同类型基类不能重复直接继承 | 同类型成员不能共享地址（仍占空间） |
| 零大小保证 | 标准布局空基类：保证 | 实现定义 |
| MSVC | 多重继承下 EBO 不完整（需 `__declspec(empty_bases)`） | 需 `msvc::` 版本 |

## 历史与演进

!!! history "C++20"
    - 引入于 C++20（[[P0840R2]]）。设计讨论中曾考虑过"空成员"的其他拼写方式，最终选择属性，因为它不改变语义（何时压缩本就是实现定义的），可被忽略。
    - "潜在重叠子对象"这个术语也随之引入，统一了基类子对象与 `[[no_unique_address]]` 成员的处理：`sizeof`、`memcpy` 保证、透明替换、地址唯一性等规则都改用这个术语表述。

## 陷阱

!!! pitfall "两个同类型的空成员不会都压缩"
    `[[no_unique_address]] Empty a; [[no_unique_address]] Empty b;`——至少有一个必须有独立的地址。例如 `std::pair<Alloc, Alloc>` 风格的设计不能把两个同类型分配器都压缩掉。

!!! pitfall "不要 memcpy 潜在重叠子对象"
    `sizeof` 报告的是类型大小，子对象实际可能更小，尾部会与其他成员重叠。

!!! pitfall "MSVC 上\"属性写了但没用\""
    在 MSVC 上测出的 `sizeof` 与 GCC/Clang 不同不是 bug，是有意为之。跨平台的结构体布局断言要考虑这一点。

## 思考题

!!! question "思考题"
    在 Itanium ABI 下，下面三个类的 `sizeof` 各是多少？为什么？

    ```cpp
    struct E {};
    struct X { [[no_unique_address]] E e; char c; };
    struct Y { [[no_unique_address]] E e1; [[no_unique_address]] E e2; };
    struct Z { E e; [[no_unique_address]] E e2; };
    ```

<details markdown="1">
<summary>答案</summary>

- `X`：`e` 可与 `c` 共享地址（类型不同），大小 1。
- `Y`：`e1` 与 `e2` 同类型，必须地址不同；但它们都可以是零大小的——零大小子对象的地址只需是完整对象中某个字节的地址。一个完整对象至少 1 字节，所以 `e1` 放偏移 0、`e2` 需要另一个地址，于是需要 2 字节：`sizeof(Y) == 2`。
- `Z`：`e` 没有属性，占 1 字节（偏移 0）；`e2` 与 `e` 同类型，不能放在偏移 0，被放在偏移 1，类也就需要 2 字节：`sizeof(Z) == 2`。

（可以在本机用 `static_assert` 验证；答案依赖于 ABI，标准只保证同类型地址不同、且完整对象大小非零。）
</details>

## 小结

!!! summary "要点"
    - `[[no_unique_address]]` 使非位域的非静态数据成员成为潜在重叠子对象。
    - 效果：空成员可以零大小、与其他成员共享地址；非布局 POD 成员的尾部填充可被复用（Itanium ABI）。
    - 同类型（相似类型）的子对象仍然必须有不同地址。
    - 是否真的压缩是实现定义的：MSVC 忽略它，提供 `[[msvc::no_unique_address]]`。
    - 潜在重叠子对象：`sizeof` 是类型大小，`memcpy` 保证不适用，不能透明替换。
