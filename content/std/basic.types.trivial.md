---
title: 平凡可复制类型
summary: 平凡可复制类型的"值"与"值表示"如何对应、对象如何"获得"值表示，以及 memcpy 往返/对拷保留值的保证
status: draft
related: basic.types, class.prop, basic.compound, bit.cast, intro.object, basic.lval, basic.indet
tags: 对象模型, memcpy, 指针来源
updated: 2026-10-17
---

[[basic.types.general#7]] 定义了**平凡可复制类型**（trivially copyable types）：标量、平凡可复制类（[[class.prop#1]]）、它们的数组及 cv 版本。本节说明这个类别到底"买到"了什么：**按字节复制等于按值复制**。这是 `std::memcpy`、`std::memmove`、`std::bit_cast`、`std::copy` 的 `memmove` 优化、序列化库、无锁数据结构乃至 `std::atomic<T>`（要求 `T` 平凡可复制）背后的同一条语言保证。

在 C++23 及之前，这条保证只是 [[basic.types.general]] 里的两段话：字节复制出去再复制回来，"对象应保持原值"；两个对象之间复制字节，"目标对象应持有与源相同的值"。当前草案 {{c++26}} 把它拆成独立子条款并重写，引入了"**值的集合**"与"**获得值表示**"（acquire a value representation）两个概念。重写的主要动机是**指针**：同一串比特可能对应多个不同的指针值（例如"`a` 的尾后指针"与"指向 `b` 的指针"地址相同），旧的"保持原值"说法无法回答"复制回来的究竟是哪个指针"。

阅读前提：对象表示/值表示（[[basic.types.general#2]]）、指针值的四种状态（[[basic.compound#3]]）、隐式对象创建（[[intro.object#13]]）。

## 值与值表示的对应（¶1–¶2）

¶1 为每个平凡可复制类型 `T` 建立了一个抽象模型：

1. `T` 有一个**实现定义**的离散**值**（values）集合；
2. 对象的每一种可能的**值表示**，对应这个集合的一个互不相同的、实现定义的**子集**；
3. 所有子集的并就是值的集合；
4. 对**除对象指针类型之外的标量类型**，每个子集**至多含一个值**；
5. 某些操作会使对象**获得**（acquire）一个值表示：对象的值被替换为对应子集中**一个未指定的成员——选那个能让程序具有定义行为的成员（如果有的话）**。

!!! std
    "the object's value is replaced with an unspecified member of the corresponding subset that would result in the program having defined behavior, if any."
    —— 获得值表示时，从对应子集里"天使般地"挑一个能使程序有定义行为的值。

把这几条拆开看：

**对整数、浮点、枚举、成员指针、`nullptr_t`**：一个值表示最多对应一个值。可能恰好一个（最常见），也可能是**空集**——即某个比特模式不表示任何值。例如实现可以规定 `bool` 的值表示是 8 位，但只有 `0x00`、`0x01` 对应值（[[basic.fundamental#10]]）。获得一个"空子集"的值表示时没有可选的值；`std::bit_cast` 明确规定这种情况是未定义行为（[[bit.cast#3]]："if any such object does not receive a value, the behavior is undefined"）。

**对对象指针类型**：一个值表示可以对应**多个**值。¶2 的注举了典型例子：对同一个地址，可能有"指向存储期已结束的旧对象的指针"和"指向在同一地址新分配的对象的指针"——这些存储区的存续期互不相交。再如 `int a, b;` 若 `b` 恰好紧跟 `a`，`&a + 1` 与 `&b` 比特完全相同，但前者是"`a` 的尾后指针"，不指向 `b`（[[basic.compound#3]] Note 2）。

为什么不直接规定"复制后得到原来那个值"？因为在 ¶4 这样的对象间复制里，目标对象并不"知道"源对象当时是什么；而且 C++ 允许指针经由字节、整数往返（[[expr.reinterpret.cast#5]] 对整数→指针的转换用了同样的"选一个能让程序有定义行为的值"的措辞）。**天使式选择**（angelic choice）的含义是：只要存在某个解释能让程序合法，就按那个解释——编译器可以据此做别名分析，程序员也不会因为"选错了来源"而无辜踩到 UB。

```cpp run ok
#include <cstring>
#include <cstdint>

int main() {
  int x = 42;
  int* p = &x;
  unsigned char buf[sizeof p];
  std::memcpy(buf, &p, sizeof p);   // 字节复制出去
  int* q;
  std::memcpy(&q, buf, sizeof q);   // q 获得 p 的值表示：子集中能使下一行有定义的值就是"指向 x"
  return *q == 42 ? 0 : 1;          // OK
}
```

!!! lawyer "哪些操作会'获得'值表示"
    在当前草案中使用"acquire"措辞的包括：本节 ¶3/¶4 的字节复制、`std::bit_cast` 的结果及其中隐式创建的对象（[[bit.cast#3]]）。[[basic.compound#5]] 还提到某个求值"产生或使对象具有"一个指针值——后者正是对本节的引用。

### 一个空子集的实例：`bool`

```cpp run ub
#include <cstdio>
#include <cstring>

int main() {
  unsigned char byte = 2;
  bool b;
  std::memcpy(&b, &byte, 1);  // b 获得值表示 0x02；主流实现中它不对应 true/false 中任何一个
  if (b)  std::puts("true");  // UB：Clang/UBSan 报 "load of value 2, which is not a valid value for type 'bool'"
  if (!b) std::puts("false");
}
```

在本机 Clang 23 / arm64 上：`-O0` 运行打印 `true`，`-O2` 运行只打印 `false`——同一个程序两种行为，典型的 UB 症状。编译器假定 `bool` 只能是 0 或 1，`!b` 可能被实现为 `b ^ 1`，于是 2 变成 3，`if (b)` 又可能直接测试最低位。

## 往返复制（¶3）

¶3：若平凡可复制类型 `T` 的对象**不是潜在重叠子对象**（[[intro.object#7]]），则**无论它是否持有 `T` 的有效值**，构成该对象的底层字节都可以复制到 `char`、`unsigned char` 或 `std::byte` 的数组中（脚注：例如用 `std::memcpy`/`std::memmove`）；把数组内容复制回该对象后，对象**获得其原来的值表示**。

三个要点：

1. **"无论是否持有有效值"**：哪怕对象的值是不确定的（indeterminate，[[basic.indet]]）或错误的（erroneous），也可以先保存再恢复。这使"保存寄存器上下文"、"事务回滚"之类的代码合法——只是复制，不解释。
2. **获得的是"原来的值表示"**，再经 ¶1 解释成值。对非指针标量，这就等于原值；对指针，得到的是该表示对应子集中让程序有定义的那个值——通常就是原指针。
3. **目标数组的元素类型**只能是 `char`、`unsigned char`、`std::byte`。这与 [[basic.lval#11]] 允许通过这三种类型的 glvalue 访问任何对象相呼应。注意 `signed char` 不在此列。

标准 Example 1 的可运行版本：

```cpp run ok
#include <cstring>
#include <cstddef>

struct T { int a; double b; char c; };   // 平凡可复制，含填充

int main() {
  constexpr std::size_t N = sizeof(T);
  std::byte buf[N];
  T obj{1, 2.5, 'x'};
  std::memcpy(buf, &obj, N);   // 两次 memcpy 之间 obj 可以被修改
  obj.a = 100; obj.c = 'y';
  std::memcpy(&obj, buf, N);   // obj 的每个标量子对象恢复原值
  return (obj.a == 1 && obj.b == 2.5 && obj.c == 'x') ? 0 : 1;
}
```

### 为什么排除潜在重叠子对象

**潜在重叠子对象**是基类子对象和带 `[[no_unique_address]]` 的成员（[[intro.object#7]]）。它们的 `sizeof` 可能覆盖到"不属于自己"的字节：ABI 可以把派生类的成员放进基类的尾部填充里。按 `sizeof(Base)` 整块写入一个基类子对象，就会踩坏派生类成员：

```cpp run
#include <cstdio>
#include <cstring>
#include <type_traits>

struct Base {
  int i;
  char get() const { return c; }
private:
  char c = 0;            // 访问控制不同 → 非标准布局；Itanium ABI 会复用其尾部填充
};
struct Derived : Base { char d; };   // d 被放进 Base 的尾部填充

static_assert(std::is_trivially_copyable_v<Base>);

int main() {
  Derived x{};
  x.d = 'Z';
  Base b{};
  Base& rb = x;                          // rb 指向潜在重叠的基类子对象
  std::memcpy(&rb, &b, sizeof(Base));    // 不在 ¶3/¶4 的保证范围内
  std::printf("sizeof(Base)=%zu sizeof(Derived)=%zu d=%d\n",
              sizeof(Base), sizeof(Derived), x.d);
}
```

本机（arm64 macOS，Clang 23）输出 `sizeof(Base)=8 sizeof(Derived)=8 d=0`：`d` 被清零了。x86-64 Linux 上布局相同（用 `-Xclang -fdump-record-layouts` 可以看到 `d` 位于偏移 5，`Base` 的 `dsize` 为 5）。

## 对象之间的复制（¶4）

¶4：对两个**不同**的此类对象 `obj1`、`obj2`（同为类型 `T`，且都不是潜在重叠子对象），若把 `obj1` 的底层字节复制到 `obj2`，则 `obj2` 获得 `obj1` 的值表示。

标准 Example 2 的注释值得注意：复制后，`*t1p` 中**每个平凡可复制类型的子对象**都含有与 `*t2p` 对应子对象相同的值。这里说的是"值"，不是"字节"——填充字节不一定相同（其实 `memcpy` 会复制它们，但标准不关心）。

```cpp run ok
#include <cstring>

struct Point { int x, y; };

int main() {
  Point a{1, 2}, b{};
  std::memcpy(&b, &a, sizeof(Point));   // b 获得 a 的值表示
  return (b.x == 1 && b.y == 2) ? 0 : 1;
}
```

### 对非平凡可复制类型：没有保证

对不是平凡可复制的类型，本节什么也不保证。用 `memcpy` "复制"一个 `std::string` 的结果是：标准没有说目标对象持有什么值——这属于"标准未定义其行为"的 UB；实践中 SSO 字符串的内部指针会指向源对象的缓冲区，随后两个对象析构时双重释放或悬垂。GCC 对此有 `-Wclass-memaccess` 警告。

```cpp run ub
#include <cstring>
#include <string>

int main() {
  std::string a = "a fairly long string that defeats SSO";
  alignas(std::string) unsigned char raw[sizeof(std::string)];
  std::memcpy(raw, &a, sizeof a);              // 保存字节本身没问题（只是复制字节）
  std::string& b = *reinterpret_cast<std::string*>(raw);
  return b.size() > 0 ? 0 : 1;                 // UB：raw 中没有 std::string 对象
}                                              //（string 不是隐式生存期类型，memcpy 不会创建它）
```

## 与其他条款的关系

| 机制 | 要求 | 与本节的关系 |
|---|---|---|
| `std::memcpy`/`memmove`（[[cstring.syn]]） | 无类型要求 | 在目标处**隐式创建**对象（[[intro.object#13]]），然后复制字节；若目标是平凡可复制类型的对象，¶3/¶4 赋予结果以值 |
| `std::bit_cast`（[[bit.cast]]） | 源、目标都平凡可复制，大小相等 | 结果中的对象"获得"值表示；无值可得时 UB；可用于常量求值 |
| 通过 `unsigned char*` 读字节（[[basic.lval#11]]） | 无 | 允许观察对象表示，但逐字节读写是否等价于 `memcpy` 仍有措辞上的争议 |
| `std::atomic<T>`（[[atomics.types.generic]]） | `T` 平凡可复制 | 原子操作按值表示做比较交换；填充位问题由 C++20 规定 `compare_exchange` 忽略填充来解决 |
| `std::start_lifetime_as<T>`（[[obj.lifetime]]） | `T` 隐式生存期且完整 | 在既有字节上开始 `T` 的生存期，同时保留字节——即把字节解释为值表示 |

!!! note "类型双关的正确姿势"
    想把 `float` 的比特看成 `uint32_t`？C++20 起用 `std::bit_cast<std::uint32_t>(f)`；之前用 `std::memcpy(&u, &f, 4)`。两者都依赖本节：`float` 与 `uint32_t` 都平凡可复制，目标获得的值表示被解释为一个 `uint32_t` 值。通过 `*(uint32_t*)&f` 读取则违反 [[basic.lval#11]] 的别名规则，是 UB。

## 实现视角

!!! impl
    - GCC 与 Clang 都把 `memcpy` 当作内建函数：小的定长 `memcpy` 会被降低成一两条加载/存储指令，所以"用 `memcpy` 做类型双关"没有性能损失。
    - libc++ 与 libstdc++ 的 `std::copy`、`std::uninitialized_copy` 在元素类型平凡可复制时分派到 `memmove`；`std::vector` 的重新分配也可据此整块搬移。
    - LLVM IR 中，按字节复制指针时保留指针的**来源**（provenance），这正对应 ¶1 中"一个值表示对应多个指针值、复制后天使式挑选"的模型；经由整数的往返则由 [[expr.reinterpret.cast#5]] 的同类措辞覆盖。

## 历史与演进

!!! history
    - **C++98**：保证只针对 POD 类型（[basic.types]/2–3），措辞是"对象随后应持有其原值"。
    - **C++11**：保证范围从 POD 放宽为**平凡可复制类型**——是否标准布局与能否 `memcpy` 无关。
    - **C++17**：加入 `std::byte` 作为合法的字节缓冲区类型。
    - **C++20**：早先版本排除的是"基类子对象"，C++20 随 `[[no_unique_address]]` 的引入改为排除"潜在重叠子对象"；`std::bit_cast` 加入；`memcpy`/`memmove` 被规定为隐式创建对象（[[P0593R6]]）。
    - **C++26 草案** {{c++26}}：拆为独立子条款 6.9.2，引入"值集合 / 值表示子集 / 获得值表示"模型，与指针"生存期结束失效"（pointer lifetime-end zap）相关的重写同步进行：[[basic.compound]] ¶4–¶6 用"在某求值的上下文中有效"取代了旧的"存储期结束时指针变为无效值"。

## 陷阱

!!! pitfall "`memcpy` 到 `const` 对象"
    ¶3/¶4 说的是复制字节使对象获得值表示，但修改 `const` 完整对象本身就是 UB（[[basic.life]]、[[dcl.type.cv]]）。平凡可复制不能绕过 `const`。

!!! pitfall "`memcmp` 不是 `==`"
    本节只保证"复制保留值"，不保证"值相等 ⇔ 字节相等"。填充字节、`+0.0`/`-0.0`、多种 NaN 位模式、甚至指针（来源不同）都会使两者不一致。需要按字节比较/哈希时，先检查 `std::has_unique_object_representations_v<T>`。

!!! pitfall "以为 `signed char` 缓冲区也行"
    ¶3 只列出 `char`、`unsigned char`、`std::byte`。`signed char` 数组作为中转在实践中当然能工作，但不在保证之内。

## 思考题

!!! question "1. `int* p = new int(1); delete p; int* q; std::memcpy(&q, &p, sizeof p);` 这段代码有 UB 吗？之后执行 `if (q) {}` 呢？"

<details markdown="1">
<summary>答案</summary>

复制本身没有 UB：¶3/¶4 明确"无论是否持有有效值"都可以复制字节；而且 C++26 起指针值并不会在存储期结束时"变成"另一种值，而是在后续求值的上下文中**无效**（[[basic.compound#6]]）。`q` 获得 `p` 的值表示。`if (q)` 是布尔转换，使用了一个在该求值上下文中无效的指针值，按 [[basic.compound#6.2]] 是**实现定义**行为（不是 UB）；解引用 `*q` 才是 UB。
</details>

!!! question "2. 为什么 ¶1 要说'对除对象指针类型之外的标量类型，每个子集至多一个值'，而不直接说'恰好一个'？"

<details markdown="1">
<summary>答案</summary>

"至多一个"允许空子集：有些比特模式不对应任何值。最典型的是 `bool`（只有两个值但通常占 8 位值表示）。如果要求"恰好一个"，实现就必须给 `0x02` 规定一个 `bool` 值，从而禁止编译器假定 `bool` 只能是 0/1 的优化。空子集配合 [[bit.cast#3]] 的"未得到值则 UB"，把这种情况明确为 UB。
</details>

## 小结

!!! summary
    - 平凡可复制类型 `T`：值集合（实现定义）+ 每个值表示 ↦ 值的子集；非指针标量的子集至多一个元素，指针可以多个。
    - [[g:acquire-value-representation|获得值表示]]：从子集中天使式选择一个使程序有定义行为的值；选不出来（空子集）时，`bit_cast` 明确 UB。
    - ¶3：任何（非潜在重叠的）对象，字节存进 `char`/`unsigned char`/`std::byte` 数组再拷回，恢复原值表示——即使原值不确定。
    - ¶4：同类型两对象之间拷字节，目标获得源的值表示。
    - 不覆盖：潜在重叠子对象（基类、`[[no_unique_address]]` 成员）、非平凡可复制类型、`const` 对象。
