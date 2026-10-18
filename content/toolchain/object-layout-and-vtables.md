---
title: 对象布局与虚表（Itanium C++ ABI）
summary: 标准只规定布局的少数约束，其余交给 ABI。Itanium ABI 下的数据成员布局与填充、空基类优化与 [[no_unique_address]]、尾部填充复用及"布局意义上的 POD"、vptr 的位置、vtable 的结构（offset-to-top、RTTI、虚函数指针）、多重继承与 thunk、虚基类（vbase offset、vcall offset、VTT、构造 vtable）、key function 与 vtable 的发射位置；全部用 -fdump-record-layouts / -fdump-vtable-layouts 的真实输出说明
status: draft
order: 35
related: class.mem, class.prop, class.virtual, class.derived, class.mi, intro.object, dcl.attr.nouniqueaddr, expr.dynamic.cast, toolchain/name-mangling, toolchain/linking-and-symbols
tags: 工具链, ABI, Itanium, 对象布局, 虚函数, vtable
updated: 2026-10-18
---

标准对类对象在内存里长什么样说得很少，而且是刻意的：

- 非位域、非零大小的非静态数据成员，**后声明的地址更高**（[[expr.rel#4.2]]；[[class.mem.general#24]] 的注释复述了这一点）。中间可以有填充，也可以插入"管理虚函数和虚基类所需的空间"。
- **标准布局类**（[[class.prop#2]]）的对象地址等于其第一个非静态数据成员的地址，也等于其基类子对象的地址（[[class.mem.general#31]]）。
- 每个对象（除位域和零大小子对象外）占据至少一个字节；生存期重叠的两个对象只有在嵌套或满足零大小子对象的条件时才能同址（[[intro.object#8]]、[[intro.object#10]]）。

除此之外——成员之间填充多少、vptr 放在哪、基类子对象排在哪、虚函数怎么分派——都留给实现。不同编译器的 C++ 代码要能互相调用，就必须在这些问题上达成一致，这份约定就是 **ABI**。本页讲 GCC/Clang 在 Linux、macOS 等平台上使用的 Itanium C++ ABI。

本页所有布局和 vtable 输出都由本机 Homebrew Clang 23.1.3 生成：

```bash
clang++ -std=c++2c --target=x86_64-linux-gnu -Xclang -fdump-record-layouts -Xclang -fdump-vtable-layouts -c x.cpp -o /dev/null
```

这两个是 `-cc1` 选项，需要 `-Xclang` 转发。只有被实际"用到"（需要知道大小、需要生成代码）的类才会被打印，所以例子里常用 `sizeof` 或定义函数来触发。`-fdump-record-layouts-simple` 输出以比特为单位的紧凑格式。macOS arm64 原生目标在本页涉及的例子上布局相同（抽查了尾部填充的例子），x86-64 Linux 的输出更便于与汇编对照。

## 数据成员与填充

```cpp
struct Padded    { char c; int i; char d; };
struct Reordered { int i; char c; char d; };
```

```text
*** Dumping AST Record Layout
         0 | struct Padded
         0 |   char c
         4 |   int i
         8 |   char d
           | [sizeof=12, dsize=12, align=4,
           |  nvsize=12, nvalign=4]

*** Dumping AST Record Layout
         0 | struct Reordered
         0 |   int i
         4 |   char c
         5 |   char d
           | [sizeof=8, dsize=8, align=4,
           |  nvsize=8, nvalign=4]
```

规则就是 C 的规则：每个成员放在满足其对齐要求（[[basic.align]]）的下一个偏移；整个类的对齐等于成员中最大的对齐；`sizeof` 向上取整到对齐的倍数，使数组中每个元素都对齐。`Padded` 浪费了 6 个字节，仅仅调整声明顺序就能省下 4 个。**编译器不会替你重排**：[[expr.rel#4.2]] 要求后声明的成员地址更高。

!!! history "访问控制不再允许重排"
    C++23 之前，标准只要求**同一访问控制**下的成员按声明顺序排列，不同访问控制段之间的顺序未指明。P1847R4 去掉了这一自由，现在所有非静态数据成员都按声明顺序排列。实际上主流 ABI 本来就从未利用过这个自由。

输出中的另外几个量是 Itanium ABI 的术语：

| 量 | 含义 |
|---|---|
| `sizeof` | 完整对象的大小 |
| `dsize`（data size） | 去掉尾部填充后的大小：最后一个有效字节之后 |
| `nvsize` / `nvalign` | 不含虚基类时的大小与对齐：本类作为**基类子对象**被嵌入时占用的部分 |

`dsize` 与 `sizeof` 的差别是理解"尾部填充复用"的关键，见下文。

## 空类与空基类优化

```cpp
struct Empty {};
struct EBO      : Empty { int x; };
struct NoEBO    { Empty e; int x; };
struct NUA      { [[no_unique_address]] Empty e; int x; };
struct TwoEmpty : Empty { Empty e; int x; };
```

```text
         0 | struct Empty (empty)
           | [sizeof=1, dsize=1, align=1,
           |  nvsize=1, nvalign=1]

         0 | struct EBO
         0 |   struct Empty (base) (empty)
         0 |   int x
           | [sizeof=4, dsize=4, align=4,

         0 | struct NoEBO
         0 |   struct Empty e (empty)
         4 |   int x
           | [sizeof=8, dsize=8, align=4,

         0 | struct NUA
         0 |   struct Empty e (empty)
         0 |   int x
           | [sizeof=4, dsize=4, align=4,

         0 | struct TwoEmpty
         0 |   struct Empty (base) (empty)
         1 |   struct Empty e (empty)
         4 |   int x
           | [sizeof=8, dsize=8, align=4,
```

逐个对应标准：

- **`Empty` 的 `sizeof` 是 1**：完整对象必须有非零大小（[[intro.object#8]]），否则 `Empty a[2]` 的两个元素会同址。
- **`EBO`：空基类优化**（EBO）。基类子对象是**潜在重叠子对象**（[[intro.object#7]]），可以是零大小的；对于没有非静态数据成员的标准布局基类，[[intro.object#8]] 直接规定它**是**零大小。`Empty` 基与 `x` 同在偏移 0，`sizeof(EBO) == sizeof(int)`。
- **`NoEBO`**：普通数据成员不是潜在重叠子对象，必须占至少一个字节，加上 `int` 的对齐，凭空多出 4 字节。
- **`NUA`**：`[[no_unique_address]]`（[[dcl.attr.nouniqueaddr]]）把数据成员也变成潜在重叠子对象，效果与 EBO 相同——这是 C++20 之前标准库实现（分配器、删除器、比较器）大量用私有继承"借"EBO 的原因，现在可以直接用成员。
- **`TwoEmpty`**：基类 `Empty` 和成员 `e` 类型相同，[[intro.object#10]] 要求同类型的两个不同对象**不能**同址（¶10.3 中的"不是相似类型"条件），所以 `e` 被挤到偏移 1。这也是为什么 [[class.prop#2]] 的 ¶2.7 规定：基类类型若与首个成员的类型相同（集合 M(S)），这个类就不是标准布局的——它的首成员不可能和基类同址。

!!! impl "MSVC"
    据公开资料（本机未验证），MSVC 在多重继承时默认只对**第一个**空基类做 EBO，需要 `__declspec(empty_bases)` 才能对所有空基类生效；对 `[[no_unique_address]]`，MSVC 为保持 ABI 兼容而忽略它，提供 `[[msvc::no_unique_address]]` 作为替代。

## 尾部填充复用

`struct D : Base { char d; }` 里，`d` 能不能塞进 `Base` 末尾的填充？Itanium ABI 的回答取决于 `Base` 是不是"**布局意义上的 POD**"（POD for the purpose of layout）——该定义沿用 C++03 的 POD 概念：

```cpp
struct PodBase    { int i; char c; };                 // C++03 意义上的 POD
struct NonPodBase { int i; char c; NonPodBase() {} }; // 有用户提供的构造函数 ⇒ 非 POD
struct PrivBase   { int i; private: char c; };        // 有私有成员 ⇒ 非 POD（尽管平凡）
struct D1 : PodBase    { char d; };
struct D2 : NonPodBase { char d; };
struct D3 : PrivBase   { char d; };
```

```text
         0 | struct PodBase
         0 |   int i
         4 |   char c
           | [sizeof=8, dsize=8, align=4,

         0 | struct D1
         0 |   struct PodBase (base)
         0 |     int i
         4 |     char c
         8 |   char d
           | [sizeof=12, dsize=9, align=4,

         0 | struct NonPodBase
         0 |   int i
         4 |   char c
           | [sizeof=8, dsize=5, align=4,

         0 | struct D2
         0 |   struct NonPodBase (base)
         0 |     int i
         4 |     char c
         5 |   char d
           | [sizeof=8, dsize=6, align=4,

         0 | struct D3
         0 |   struct PrivBase (base)
         ...
         5 |   char d
           | [sizeof=8, dsize=6, align=4,
```

`PodBase` 的 `dsize` 是 8——尾部 3 字节填充被视为"数据"，不能复用，`D1` 只好把 `d` 放在偏移 8，总大小 12。`NonPodBase` 和 `PrivBase` 的 `dsize` 是 5，派生类把 `d` 放进偏移 5，总大小仍是 8。

为什么 POD 不能复用？因为 C 和 C++98 的代码会对 POD 做 `memcpy(&base, &other, sizeof(Base))`——如果派生类的成员住在基类的尾部填充里，这次拷贝就会把它覆盖掉。对非 POD 类，ABI 认为没有人会这么拷贝基类子对象。（按今天的标准，平凡可复制类型"拷出字节再拷回、值不变"的保证明确排除了**潜在重叠子对象**（[[basic.types.trivial#3]]），所以对基类子对象做这种 `memcpy` 本来就没有保证。）

!!! pitfall "\"布局意义上的 POD\"不是任何现行标准术语"
    `PrivBase` 是平凡的、平凡可复制的，但因为有私有成员，它不是 C++03 的聚合，因而不是 C++03 的 POD；它甚至**是**标准布局类（所有成员访问控制相同）。今天的 `std::is_pod`（已弃用）、`is_trivial`、`is_standard_layout` 都不能准确预测 Itanium ABI 会不会复用它的尾部填充。改一个成员的访问控制、加一个空的用户构造函数，都可能改变派生类的大小——这是一种 ABI 变化。

`[[no_unique_address]]` 成员同样适用这条规则（`-fdump-record-layouts-simple` 输出，单位为比特）：

```text
Type: struct M2          // struct M2 { [[no_unique_address]] NonPodBase p; char d; };
  Size:64
  DataSize:48
  FieldOffsets: [0, 40]>

Type: struct M3          // struct M3 { NonPodBase p; char d; };
  Size:96
  DataSize:72
  FieldOffsets: [0, 64]>
```

`M2` 的 `d` 位于第 40 比特（字节 5），复用了 `p` 的尾部填充；普通成员 `M3::d` 则在字节 8。而对 POD 类型的 `[[no_unique_address]]` 成员（`struct M1 { [[no_unique_address]] PodBase p; char d; }`），`d` 仍在字节 8——`PodBase` 的 `dsize` 本来就是 8。

## 多态类：vptr 与 vtable

```cpp title="v1.cpp"
struct Base {
    virtual ~Base();
    virtual int f();
    virtual int g();
    int b = 1;
};
struct Derived : Base {
    int f() override;
    virtual int h();
    int d = 2;
};
Base::~Base() {}
int Base::f() { return 1; }
int Base::g() { return 2; }
int Derived::f() { return 3; }
int Derived::h() { return 4; }
```

```text
         0 | struct Base
         0 |   (Base vtable pointer)
         8 |   int b
           | [sizeof=16, dsize=12, align=8,
           |  nvsize=12, nvalign=8]

         0 | struct Derived
         0 |   struct Base (primary base)
         0 |     (Base vtable pointer)
         8 |     int b
        12 |   int d
           | [sizeof=16, dsize=16, align=8,
           |  nvsize=16, nvalign=8]
```

- **vptr 在偏移 0**。有虚函数的类在开头放一个指向 vtable 的指针。多态类不是标准布局类（[[class.prop#2]] ¶2.2），所以"对象地址 = 首成员地址"的保证不适用——`b` 在偏移 8。
- `Derived` 与 `Base` **共享**同一个 vptr：`Base` 是它的**主基类**（primary base）——第一个非虚的动态基类，放在偏移 0，派生类直接扩展它的 vtable。
- `Derived::d` 放在偏移 12，复用了 `Base` 的尾部填充（多态类不是 POD）。

vtable 的结构：

```text
Vtable for 'Base' (6 entries).
   0 | offset_to_top (0)
   1 | Base RTTI
       -- (Base, 0) vtable address --
   2 | Base::~Base() [complete]
   3 | Base::~Base() [deleting]
   4 | int Base::f()
   5 | int Base::g()

Vtable for 'Derived' (7 entries).
   0 | offset_to_top (0)
   1 | Derived RTTI
       -- (Base, 0) vtable address --
       -- (Derived, 0) vtable address --
   2 | Derived::~Derived() [complete]
   3 | Derived::~Derived() [deleting]
   4 | int Derived::f()
   5 | int Base::g()
   6 | int Derived::h()
```

| 槽 | 内容 |
|---|---|
| **offset_to_top** | 从这个 vptr 所在的子对象到**完整对象**起点的偏移（这里是 0）。`dynamic_cast<void*>` 用它找到最派生对象（[[expr.dynamic.cast]]） |
| **RTTI** | 指向本类的 `type_info` 对象（`_ZTI…`），供 `typeid` 与 `dynamic_cast` 使用 |
| （vtable address） | **vptr 实际指向这里**，而不是 vtable 开头 |
| 虚函数指针 | 按声明顺序；派生类覆盖的替换对应槽位，新增的追加到末尾 |

虚析构函数占**两个**槽：`[complete]`（D1，只析构）和 `[deleting]`（D0，析构后调用 `operator delete`）。`delete p` 通过 D0 分派，因此能调用到最派生类所在作用域中的 `operator delete`（[[expr.delete]]、[[class.free]]）。

在目标文件里，vtable 就是一个指针数组，内容由重定位填写：

```text
$ llvm-readelf -r v1.o        # .rela.data.rel.ro 节，摘录 Derived 的部分（vtable 起始于 0x40）
0000000000000048 R_X86_64_64 _ZTI7Derived + 0
0000000000000050 R_X86_64_64 _ZN7DerivedD2Ev + 0
0000000000000058 R_X86_64_64 _ZN7DerivedD0Ev + 0
0000000000000060 R_X86_64_64 _ZN7Derived1fEv + 0
0000000000000068 R_X86_64_64 _ZN4Base1gEv + 0
0000000000000070 R_X86_64_64 _ZN7Derived1hEv + 0
```

（`0x40` 处的 offset_to_top 是常量 0，不需要重定位。complete 析构函数槽里放的是 `D2`：没有虚基类时 D1 与 D2 相同，Clang 直接引用 D2。）

构造函数写 vptr、虚调用读 vptr（`-O2`）：

```cpp
Derived* make() { return new Derived; }
int call_g(Base& b) { return b.g(); }
```

```text
_Z4makev:
	pushq	%rax
	movl	$16, %edi
	callq	_Znwm@PLT
	movabsq	$8589934593, %rcx               # imm = 0x200000001
	movq	%rcx, 8(%rax)                   # b = 1, d = 2 一次写入
	movq	_ZTV7Derived@GOTPCREL(%rip), %rcx
	addq	$16, %rcx                       # vptr = vtable + 16，跳过 offset_to_top 与 RTTI
	movq	%rcx, (%rax)
	popq	%rcx
	retq
_Z6call_gR4Base:
	movq	(%rdi), %rax                    # 读 vptr
	jmpq	*24(%rax)                       # 第 3 个虚函数槽：g
```

`g` 在 vptr 之后的第 3 个槽（D1、D0、f、g），偏移 24。虚调用就是两次加载加一次间接跳转。

`dynamic_cast<void*>` 则用 vptr 前面的 offset_to_top：

```text
_Z12most_derivedP1B:                    # void* most_derived(B* p) { return dynamic_cast<void*>(p); }
	testq	%rdi, %rdi
	je	.LBB0_1                         # 空指针 → 空指针
	movq	%rdi, %rax
	movq	(%rdi), %rcx
	addq	-16(%rcx), %rax                 # p + offset_to_top
	retq
```

### RTTI 对象

`_ZTI7Derived` 本身也是一个多态对象，它的 vptr 指向 C++ 运行时库中 `__cxxabiv1` 的某个 `type_info` 子类的 vtable：没有基类用 `__class_type_info`，单一非虚公有基类用 `__si_class_type_info`，其他情况（多重继承、虚继承）用 `__vmi_class_type_info`——本页的三个例子分别引用了这三者。`dynamic_cast` 的运行时实现（`__dynamic_cast`）就是沿着这些对象记录的基类信息搜索。

## 多重继承与 thunk

```cpp title="mi.cpp"
struct A { virtual int fa(); int a = 1; };
struct B { virtual int fb(); int b = 2; };
struct C : A, B { int fb() override; int c = 3; };
int C::fb() { return c; }
int call_fb(B& b) { return b.fb(); }
B* to_b(C* p) { return p; }
```

```text
         0 | struct C
         0 |   struct A (primary base)
         0 |     (A vtable pointer)
         8 |     int a
        16 |   struct B (base)
        16 |     (B vtable pointer)
        24 |     int b
        28 |   int c
           | [sizeof=32, dsize=32, align=8,

Vtable for 'C' (7 entries).
   0 | offset_to_top (0)
   1 | C RTTI
       -- (A, 0) vtable address --
       -- (C, 0) vtable address --
   2 | int A::fa()
   3 | int C::fb()
   4 | offset_to_top (-16)
   5 | C RTTI
       -- (B, 16) vtable address --
   6 | int C::fb()
       [this adjustment: -16 non-virtual] method: int B::fb()

Thunks for 'int C::fb()' (1 entry).
   0 | this adjustment: -16 non-virtual
```

`C` 有**两个 vptr**：`A` 子对象（主基类，与 `C` 共享）一个，`B` 子对象在偏移 16 处一个。`C` 的 vtable 实际上是一组 vtable 拼在一起：主 vtable（0–3）和 `B`-in-`C` 的**次级 vtable**（4–6）。次级 vtable 的 offset_to_top 是 −16：从 `B` 子对象回到 `C` 的起点要减 16。

这里有个问题：`call_fb` 只知道自己拿到的是 `B&`，它把指向 `B` 子对象的指针作为 `this` 传给 vtable 槽里的函数；但 `C::fb` 期望 `this` 指向 `C` 的起点。所以次级 vtable 的槽 6 放的不是 `C::fb` 本身，而是一个 **thunk**：先把 `this` 减 16，再跳到 `C::fb`。

```text
$ llvm-nm mi.o | grep -i thn
_ZThn16_N1C2fbEv           non-virtual thunk to C::fb()

$ llvm-objdump -d --no-show-raw-insn mi.o
0000000000000010 <_ZN1C2fbEv>:
      10:      	movl	0x1c(%rdi), %eax          # this->c，c 在 C 中的偏移 28
      13:      	retq

0000000000000014 <_ZThn16_N1C2fbEv>:
      14:      	movl	0xc(%rdi), %eax           # thunk：this 指向 B 子对象，c 在其后 12 字节
      17:      	retq

0000000000000020 <_Z4to_bP1C>:
      20:      	leaq	0x10(%rdi), %rax
      24:      	testq	%rdi, %rdi
      27:      	cmoveq	%rdi, %rax                # 派生到基类的转换：空指针保持为空
      2b:      	retq
```

`-O2` 下 thunk 被优化成了 `C::fb` 的一份带偏移的副本（`0x1c - 0x10 = 0xc`），不需要真的跳转。修饰名 `_ZThn16_` 中的 `h` 表示非虚调整，`n16` 是 −16。`to_b` 展示了派生类指针到基类指针的转换（[[conv.ptr]]）在多重继承下**会改变指针的值**——并且必须特殊处理空指针。

## 虚基类

虚继承让菱形继承中的公共基类只有一个子对象（[[class.mi#6]]）。代价是：虚基类相对于各个基类子对象的位置**不再固定**，取决于最派生类型。

```cpp title="vb.cpp"
struct V { virtual int fv(); int v = 0; };
struct L : virtual V { virtual int fl(); int l = 1; };
struct R : virtual V { virtual int fr(); int r = 2; };
struct D : L, R { int fv() override; int d = 3; };
V& to_v(L& l) { return l; }
```

```text
         0 | struct L
         0 |   (L vtable pointer)
         8 |   int l
        16 |   struct V (virtual base)
        16 |     (V vtable pointer)
        24 |     int v
           | [sizeof=32, dsize=28, align=8,
           |  nvsize=12, nvalign=8]

         0 | struct D
         0 |   struct L (primary base)
         0 |     (L vtable pointer)
         8 |     int l
        16 |   struct R (base)
        16 |     (R vtable pointer)
        24 |     int r
        28 |   int d
        32 |   struct V (virtual base)
        32 |     (V vtable pointer)
        40 |     int v
           | [sizeof=48, dsize=44, align=8,
           |  nvsize=32, nvalign=8]
```

独立的 `L` 对象中，`V` 在偏移 16；而在 `D` 中，`L` 子对象位于偏移 0，`V` 却在偏移 32。`nvsize=12` 说明：`L` 作为基类被嵌入时只带上它自己的 12 字节，虚基类由最派生类统一放在末尾。

既然偏移不固定，`L&` 转 `V&` 就只能**运行时**查表——查的是 vtable 中 offset_to_top **之前**的 **vbase_offset**：

```text
Vtable for 'D' (13 entries).
   0 | vbase_offset (32)
   1 | offset_to_top (0)
   2 | D RTTI
       -- (D, 0) vtable address --
       -- (L, 0) vtable address --
   3 | int L::fl()
   4 | int D::fv()
   5 | vbase_offset (16)
   6 | offset_to_top (-16)
   7 | D RTTI
       -- (R, 16) vtable address --
   8 | int R::fr()
   9 | vcall_offset (-32)
  10 | offset_to_top (-32)
  11 | D RTTI
       -- (V, 32) vtable address --
  12 | int D::fv()
       [this adjustment: 0 non-virtual, -24 vcall offset offset] method: int V::fv()
```

```text
_Z4to_vR1L:
	movq	%rdi, %rax
	movq	(%rdi), %rcx              # vptr
	addq	-0x18(%rcx), %rax         # vptr 往前 3 个槽 = vbase_offset
	retq
```

对 `D` 中的 `L` 子对象，vbase_offset 是 32；对一个独立的 `L` 对象是 16——同一段 `to_v` 代码在两种情况下都正确。

### vcall offset 与虚 thunk

`D::fv` 覆盖了虚基类 `V` 的 `fv`。通过 `V&` 调用时，`this` 指向 `V` 子对象，需要调整回 `D` 的起点；但调整量取决于最派生类型（`V` 在 `D` 中偏移 32，在别的类中可能不同），不能写死在 thunk 里。于是 `V`-in-`D` 的次级 vtable 中多了一个 **vcall_offset**（槽 9，值 −32），thunk 在运行时读它：

```text
_ZTv0_n24_N1D2fvEv         virtual thunk to D::fv()
```

修饰名中的 `v0_n24_` 表示：非虚调整 0，然后从 vptr 偏移 −24 处读取 vcall offset 再调整——正是 dump 中的 "-24 vcall offset offset"。（本例中 `D::fv` 返回常量，`-O2` 下 thunk 被优化为直接 `movl $0x3, %eax`。）

### VTT 与构造 vtable

最棘手的是**构造过程中**。按 [[class.cdtor]]，在 `L` 的构造函数体执行期间，对象的动态类型是 `L`：虚调用应分派到 `L` 的版本，`typeid` 应得到 `L`。但 `L` 子对象此刻位于 `D` 中，`V` 在偏移 32 而不是独立 `L` 的 16——直接用 `L` 自己的 vtable，vbase_offset 就错了。

Itanium ABI 的解法是为"`L` 作为 `D` 的基类"专门生成**构造 vtable**（construction vtable）：内容按 `L` 的语义（虚函数是 `L` 的版本），偏移按 `D` 的布局：

```text
Construction vtable for ('L', 0) in 'D' (8 entries).
   0 | vbase_offset (32)
   1 | offset_to_top (0)
   2 | L RTTI
       -- (L, 0) vtable address --
   3 | int L::fl()
   4 | vcall_offset (0)
   5 | offset_to_top (-32)
   6 | L RTTI
       -- (V, 32) vtable address --
   7 | int V::fv()
```

对比 `L` 自己的 vtable，唯一的差别是 vbase_offset（16 → 32）与对应的 offset_to_top（−16 → −32）。`D` 的构造函数通过 **VTT**（Virtual Table Table，`_ZTT1D`）把这些构造 vtable 的地址传给基类的**基类子对象构造函数**（C2）——这正是 C1/C2 必须区分的原因（[[toolchain/name-mangling]]）。本机生成的 `_ZTT1D` 有 7 项：

```text
$ llvm-readelf -r vb.o     # _ZTT1D 位于 .data.rel.ro 的 0x180
0000000000000180 _ZTV1D + 18
0000000000000188 _ZTC1D0_1L + 18
0000000000000190 _ZTC1D0_1L + 38
0000000000000198 _ZTC1D16_1R + 18
00000000000001a0 _ZTC1D16_1R + 38
00000000000001a8 _ZTV1D + 60
00000000000001b0 _ZTV1D + 40
```

依次是：`D` 主 vtable 的地址点、`L`-in-`D` 构造 vtable 的两个地址点（`L` 与其中的 `V`）、`R`-in-`D` 的两个、以及 `D` 完整 vtable 中 `V` 与 `R` 的次级地址点。构造过程中，每进入一层构造函数，各子对象的 vptr 就被改写成该层对应的地址点——"构造期间动态类型逐层变化"的语义就是这样一次次 vptr 写入实现的。

## key function：vtable 在哪个 TU 中发射

vtable 是一个需要定义的实体，可能有很多 TU 都需要它。Itanium ABI 的规则：

- 类的 **key function** 是类定义结束时，**第一个**非纯虚、非 inline 的虚函数。
- 有 key function 的类，vtable 和 typeinfo **只在定义 key function 的那个 TU 中**发射，是强定义。
- 没有 key function 的类，vtable 在每个用到它的 TU 中以 vague linkage（弱定义 + COMDAT）发射。

```cpp title="key.cpp"
struct NoKey   { virtual int f() { return 1; } };
struct HasKey  { virtual int f(); virtual int g() { return 2; } };
struct LateInl { virtual int f(); };
inline int LateInl::f() { return 3; }
int HasKey::f() { return 1; }
int use() { NoKey a; HasKey b; LateInl c; return a.f() + b.g() + c.f(); }
```

```text
$ clang++ -std=c++2c --target=x86_64-linux-gnu -Wweak-vtables -c key.cpp -o key.o
key.cpp:3:8: warning: 'LateInl' has no out-of-line virtual method definitions; its vtable will be emitted in every translation unit [-Wweak-vtables]
key.cpp:1:8: warning: 'NoKey' has no out-of-line virtual method definitions; its vtable will be emitted in every translation unit [-Wweak-vtables]
$ llvm-nm -C key.o | grep vtable
0000000000000000 V vtable for NoKey
0000000000000000 D vtable for HasKey
0000000000000000 V vtable for LateInl
```

- `HasKey`：key function 是 `f`，本 TU 定义了它，vtable 是 `D`（强定义）。其他包含 `HasKey` 定义但不定义 `f` 的 TU 只会有 `U vtable for HasKey`。
- `NoKey`：全部 inline，vtable 是 `V`（弱）。`-Wweak-vtables` 会提醒这一点，因为每个 TU 都要付出生成和去重的代价。
- `LateInl`：在类定义结束时 `f` 尚未被声明为 inline，但之后定义为 inline。按 Clang 的处理，它最终也没有 key function，vtable 为弱定义。

这条规则与标准的联系在于 [[basic.def.odr#8]] 与 [[class.virtual#12]]：非纯虚的虚函数总是被 odr-use，因此必须有定义。如果你声明了 key function 却忘了定义它，vtable **就不会在任何地方发射**，于是所有构造函数都会引用一个不存在的 vtable——这就是那条著名的链接错误 "undefined reference to vtable for X"（GNU ld 的说法；本机 Apple ld 的输出及其提示见 [[toolchain/linking-and-symbols]]）。报错指向 vtable 而不是那个函数，常常让人摸不着头脑。

## 小结

!!! summary
    - 标准只规定：成员按声明顺序递增排列、标准布局类首成员与对象同址、对象占非零字节（潜在重叠子对象除外）。其余是 ABI。
    - Itanium：成员按对齐顺序放置；空基类与 `[[no_unique_address]]` 成员可零大小，但同类型对象不能同址；只有"布局意义上的 POD"（C++03 定义）之外的类的尾部填充可被复用。
    - 多态类在偏移 0 放 vptr；vptr 指向 vtable 中 offset_to_top 与 RTTI **之后**；虚析构函数占两个槽（D1、D0）。
    - 多重继承：每个非主基类子对象有自己的 vptr 和次级 vtable；覆盖函数通过非虚 thunk（`_ZThn`）调整 this；派生到基类的指针转换要加偏移并保留空指针。
    - 虚继承：vbase_offset 在运行时定位虚基类；vcall_offset + 虚 thunk（`_ZTv`）处理经虚基类的调用；VTT 与构造 vtable 实现构造期间的动态类型。
    - key function 决定 vtable 在哪个 TU 中以强定义发射；没有 key function 时为 vague linkage。
