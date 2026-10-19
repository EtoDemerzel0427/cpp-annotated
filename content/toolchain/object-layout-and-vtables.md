---
title: 对象布局与虚表（Itanium C++ ABI）
summary: 标准对类对象的内存布局只规定了少数几条，其余由 ABI 决定；本页用 Clang 的布局与 vtable 转储说明 Itanium ABI 下数据成员、空基类、vptr、vtable、thunk 和虚基类是怎样排布和工作的。
status: draft
order: 35
related: class.mem, class.prop, class.virtual, class.derived, class.mi, intro.object, dcl.attr.nouniqueaddr, expr.dynamic.cast, toolchain/name-mangling, toolchain/linking-and-symbols
tags: 工具链, ABI, Itanium, 对象布局, 虚函数, vtable
updated: 2026-10-19
---

!!! tldr
    - 标准只规定：后声明的成员地址更高，标准布局类的首成员与对象同址，对象至少占一个字节（零大小子对象除外）。填充多少、vptr 放在哪、虚函数怎样分派，都由 ABI 决定。
    - 空基类和 `[[no_unique_address]]` 成员可以不占空间，但同类型的两个对象不能同址。
    - Itanium ABI 只复用非 POD 类的尾部填充，这里的 POD 沿用 C++03 的定义，与今天任何标准术语都不完全对应。
    - 多态类在偏移 0 放一个 vptr，指向 vtable 中 offset_to_top 和 RTTI 之后的位置；虚调用就是两次加载加一次间接跳转。
    - 多重继承靠次级 vtable 和 thunk 调整 `this`；虚继承靠 vbase_offset、vcall_offset、构造 vtable 和 VTT 在运行时定位虚基类。

## 标准规定了什么

标准对类对象在内存里的样子说得很少，这是有意的。它只规定了下面几条：

- 非位域、非零大小的非静态数据成员，后声明的地址更高（[[expr.rel#4.2]]，[[class.mem.general#24]] 的注复述了这一点）。成员之间可以有填充，也可以有管理虚函数和虚基类所需的空间。
- **标准布局类**（standard-layout class）的对象，地址等于它第一个非静态数据成员的地址，也等于它每个基类子对象的地址（[[class.mem.general#31]]）。标准布局类的条件列在 [[class.prop#2]]，例如没有虚函数和虚基类、所有非静态数据成员的访问控制相同。
- 每个对象（位域和零大小子对象除外）至少占一个字节。生存期重叠的两个对象只有在一个嵌套在另一个里面，或者其中有零大小子对象时，才能同址（[[intro.object#8]]、[[intro.object#10]]）。

除此之外，成员之间填充多少、vptr 放在哪、基类子对象排在哪、虚函数怎样分派，都留给实现。不同编译器生成的代码要能互相调用，就必须在这些问题上达成一致，这份约定就是 **ABI**（application binary interface）。本页讲 GCC 和 Clang 在 Linux、macOS 等平台上使用的 Itanium C++ ABI。

本页的布局和 vtable 输出都由本机 Clang 23 生成：

```bash
clang++ -std=c++2c --target=x86_64-linux-gnu \
  -Xclang -fdump-record-layouts -Xclang -fdump-vtable-layouts -c x.cpp -o /dev/null
```

这两个是编译器前端（`-cc1`）的选项，需要用 `-Xclang` 转发。只有实际被用到（需要知道大小或需要生成代码）的类才会被打印，所以例子里常用 `sizeof` 或函数定义来触发。

## 数据成员与填充

```cpp
struct Padded    { char c; int i; char d; };
struct Reordered { int i; char c; char d; };
```

```text
         0 | struct Padded
         0 |   char c
         4 |   int i
         8 |   char d
           | [sizeof=12, dsize=12, align=4,
           |  nvsize=12, nvalign=4]

         0 | struct Reordered
         0 |   int i
         4 |   char c
         5 |   char d
           | [sizeof=8, dsize=8, align=4,
           |  nvsize=8, nvalign=4]
```

规则与 C 相同。每个成员放在满足其对齐要求（[[basic.align]]）的下一个偏移上；整个类的对齐等于成员中最大的对齐；`sizeof` 向上取整到对齐的倍数，这样数组的每个元素都是对齐的。

`Padded` 只有 6 个字节的数据，却占 12 个字节，调整声明顺序就能省下 4 个。编译器不会替你重排，因为 [[expr.rel#4.2]] 要求后声明的成员地址更高。

!!! history "访问控制不再允许重排"
    C++23 之前，标准只要求同一访问控制下的成员按声明顺序排列，不同访问控制段之间的先后未指定。[[P1847R4]] 去掉了这项自由，现在所有非静态数据成员都按声明顺序排列。主流 ABI 本来就没有利用过这项自由。

输出中的另外几个量是 Itanium ABI 的术语：

| 量 | 含义 |
|---|---|
| `sizeof` | 完整对象的大小 |
| `dsize`（data size） | 去掉尾部填充后的大小，即最后一个有效字节之后的位置 |
| `nvsize` / `nvalign` | 不含虚基类时的大小与对齐，也就是本类作为基类子对象被嵌入时占用的部分 |

`dsize` 与 `sizeof` 的差别决定了尾部填充能否被复用，见后文。

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

`Empty` 的 `sizeof` 是 1，因为完整对象必须有非零大小（[[intro.object#8]]），否则 `Empty a[2]` 的两个元素会同址。

基类子对象和带 `[[no_unique_address]]` 的成员是**潜在重叠子对象**（potentially-overlapping subobject，[[intro.object#7]]），它们可以是零大小的。对于没有非静态数据成员的标准布局基类，[[intro.object#8]] 直接规定它是零大小。所以 `EBO` 里的 `Empty` 基类和 `x` 同在偏移 0，`sizeof(EBO) == sizeof(int)`。这叫**空基类优化**（empty base optimization，EBO）。

`NoEBO` 的普通数据成员 `e` 不是潜在重叠子对象，必须至少占一个字节，再加上 `int` 的对齐，多出 4 个字节。`NUA` 用 `[[no_unique_address]]`（[[dcl.attr.nouniqueaddr]]）把成员也变成潜在重叠子对象，效果与 EBO 相同。C++20 之前，标准库实现为了让分配器、删除器、比较器不占空间，大量用私有继承来借用 EBO；现在直接用带这个属性的成员即可。

`TwoEmpty` 的基类 `Empty` 和成员 `e` 类型相同。按 [[intro.object#10]]，同类型的两个不同对象不能同址，所以 `e` 被挤到偏移 1。[[class.prop#2]] 第 2.7 项因此规定：如果基类类型可能出现在类的偏移 0 处（比如与首个成员的类型相同），这个类就不是标准布局类，因为它的首成员不可能和基类同址。

!!! impl "MSVC"
    据公开资料（本机未验证），MSVC 在多重继承时默认只对第一个空基类做 EBO，要用 `__declspec(empty_bases)` 才能对所有空基类生效。MSVC 为保持 ABI 兼容而忽略 `[[no_unique_address]]`，另外提供 `[[msvc::no_unique_address]]`。

## 尾部填充复用

`struct D : Base { char d; }` 中，`d` 能不能放进 `Base` 末尾的填充？Itanium ABI 的回答取决于 `Base` 是不是**布局意义上的 POD**（POD for the purpose of layout），这个概念沿用 C++03 的 POD 定义。C++03 的 POD 类必须是聚合，因此不能有用户声明的构造函数，也不能有私有或受保护的非静态数据成员。

```cpp
struct PodBase    { int i; char c; };                 // C++03 意义上的 POD
struct NonPodBase { int i; char c; NonPodBase() {} }; // 有用户声明的构造函数，不是 POD
struct PrivBase   { int i; private: char c; };        // 有私有数据成员，不是 POD
struct D1 : PodBase    { char d; };
struct D2 : NonPodBase { char d; };
struct D3 : PrivBase   { char d; };
```

```text
         0 | struct D1
         0 |   struct PodBase (base)
         0 |     int i
         4 |     char c
         8 |   char d
           | [sizeof=12, dsize=9, align=4,

         0 | struct D2
         0 |   struct NonPodBase (base)
         0 |     int i
         4 |     char c
         5 |   char d
           | [sizeof=8, dsize=6, align=4,

         0 | struct D3
         0 |   struct PrivBase (base)
         0 |     int i
         4 |     char c
         5 |   char d
           | [sizeof=8, dsize=6, align=4,
```

`PodBase` 的 `dsize` 是 8：它尾部 3 个字节的填充被当作数据，不能复用，所以 `D1` 只能把 `d` 放在偏移 8，总大小 12。`NonPodBase` 和 `PrivBase` 的 `dsize` 是 5，派生类把 `d` 放在偏移 5，总大小仍是 8。

POD 的尾部填充不能复用，是因为 C 和 C++98 的代码会对 POD 做 `memcpy(&base, &other, sizeof(Base))`。如果派生类的成员住在基类的尾部填充里，这次拷贝就会把它覆盖掉。对非 POD 类，ABI 假定没有人会这样拷贝基类子对象。按今天的标准，平凡可复制类型拷出字节再拷回、值不变的保证明确排除了潜在重叠子对象（[[basic.types.trivial#3]]），所以对基类子对象做这种 `memcpy` 本来就没有保证。

!!! pitfall "布局意义上的 POD 不是现行标准的术语"
    `PrivBase` 是平凡可复制的，但因为有私有数据成员，它既不是 C++03 的 POD，也不是标准布局类。反过来，只给 `PodBase` 加一个什么也不做的用户构造函数，它仍然是标准布局类，却不再是 C++03 的 POD。`std::is_trivial`、`std::is_standard_layout` 和已弃用的 `std::is_pod` 都不能准确预测 Itanium ABI 会不会复用尾部填充。改一个成员的访问控制、加一个空的构造函数，都可能改变派生类的大小，这是一种 ABI 变化。

`[[no_unique_address]]` 成员同样适用这条规则：

```cpp
struct M1 { [[no_unique_address]] PodBase p;    char d; };
struct M2 { [[no_unique_address]] NonPodBase p; char d; };
struct M3 { NonPodBase p; char d; };
```

```text
         0 | struct M1
         0 |   struct PodBase p
         ...
         8 |   char d
           | [sizeof=12, dsize=12, align=4,

         0 | struct M2
         0 |   struct NonPodBase p
         ...
         5 |   char d
           | [sizeof=8, dsize=6, align=4,

         0 | struct M3
         0 |   struct NonPodBase p
         ...
         8 |   char d
           | [sizeof=12, dsize=9, align=4,
```

`M2::d` 在偏移 5，复用了 `p` 的尾部填充；普通成员 `M3::d` 在偏移 8。`M1` 的 `p` 虽然带属性，但 `PodBase` 的 `dsize` 本来就是 8，所以 `d` 也在偏移 8。

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

有虚函数的类在对象开头放一个指向**虚函数表**（vtable）的指针，叫做 **vptr**。多态类不是标准布局类（[[class.prop#2]] 第 2.2 项），所以对象地址等于首成员地址的保证不适用，`b` 在偏移 8。

`Derived` 与 `Base` 共用同一个 vptr。`Base` 是 `Derived` 的**主基类**（primary base），即第一个非虚的动态基类，它放在偏移 0，派生类直接在它的 vtable 后面扩展。`Derived::d` 放在偏移 12，复用了 `Base` 的尾部填充，因为多态类不是 POD。

### vtable 的结构

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
| offset_to_top | 从这个 vptr 所在的子对象到完整对象起点的偏移，这里是 0。`dynamic_cast<void*>` 用它找到最派生对象（[[expr.dynamic.cast]]） |
| RTTI | 指向本类的 `type_info` 对象（`_ZTI…`），供 `typeid` 与 `dynamic_cast` 使用 |
| vtable address | vptr 实际指向这里，而不是 vtable 开头 |
| 虚函数指针 | 按声明顺序排列；派生类的覆盖函数替换对应的槽，新增的虚函数追加到末尾 |

虚析构函数占两个槽：`[complete]` 只析构，对应修饰名中的 D1；`[deleting]` 析构后再调用 `operator delete`，对应 D0（见 [[toolchain/name-mangling]]）。`delete p` 通过 D0 分派，因此能调用到最派生类作用域中的 `operator delete`（[[expr.delete]]、[[class.free]]）。

在目标文件里，vtable 就是一个指针数组，内容由重定位填写。下面是 `-O0` 编译的 `v1.o` 中 `Derived` 的 vtable（起始于 `0x40`）：

```text
$ llvm-readelf -r v1.o        # .rela.data.rel.ro 节，摘录
0000000000000048 R_X86_64_64 _ZTI7Derived + 0
0000000000000050 R_X86_64_64 _ZN7DerivedD2Ev + 0
0000000000000058 R_X86_64_64 _ZN7DerivedD0Ev + 0
0000000000000060 R_X86_64_64 _ZN7Derived1fEv + 0
0000000000000068 R_X86_64_64 _ZN4Base1gEv + 0
0000000000000070 R_X86_64_64 _ZN7Derived1hEv + 0
```

`0x40` 处的 offset_to_top 是常量 0，不需要重定位。complete 析构函数的槽里放的是 D2：没有虚基类时 D1 与 D2 相同，Clang 直接引用 D2。

### 构造函数写 vptr，虚调用读 vptr

```cpp
Derived* make() { return new Derived; }
int call_g(Base& b) { return b.g(); }
void* most_derived(Base* p) { return dynamic_cast<void*>(p); }
```

```text
_Z4makev:
	pushq	%rax
	movl	$16, %edi
	callq	_Znwm@PLT
	movabsq	$8589934593, %rcx               # 0x200000001：b = 1, d = 2 一次写入
	movq	%rcx, 8(%rax)
	leaq	_ZTV7Derived+16(%rip), %rcx     # vptr = vtable + 16，跳过 offset_to_top 和 RTTI
	movq	%rcx, (%rax)
	popq	%rcx
	retq
_Z6call_gR4Base:
	movq	(%rdi), %rax                    # 读 vptr
	jmpq	*24(%rax)                       # vptr 之后第 3 个槽：g
_Z12most_derivedP4Base:
	testq	%rdi, %rdi
	je	.LBB7_1                         # 空指针得到空指针
	movq	%rdi, %rax
	movq	(%rdi), %rcx
	addq	-16(%rcx), %rax                 # p + offset_to_top
	retq
.LBB7_1:
	xorl	%eax, %eax
	retq
```

这是 `-O2` 的输出。`g` 位于 vptr 之后的第 3 个槽（D1、D0、f、g 依次排列），偏移 24，所以虚调用就是两次加载加一次间接跳转。`dynamic_cast<void*>` 读的是 vptr 前面两个槽处的 offset_to_top。

### RTTI 对象

`_ZTI7Derived` 本身也是一个多态对象。它的 vptr 指向 C++ 运行时库中某个 `type_info` 子类的 vtable：没有基类的类用 `__cxxabiv1::__class_type_info`，只有一个非虚公有基类的类用 `__si_class_type_info`，其余情况（多重继承、虚继承）用 `__vmi_class_type_info`。本页的三个例子分别引用了这三者。`dynamic_cast` 的运行时实现 `__dynamic_cast` 就是沿着这些对象记录的基类信息搜索。

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
```

`C` 有两个 vptr：`A` 子对象（主基类，与 `C` 共用）一个，偏移 16 处的 `B` 子对象一个。`C` 的 vtable 实际上是两张表拼在一起：主 vtable（槽 0–3）和 `B`-in-`C` 的**次级 vtable**（槽 4–6）。次级 vtable 的 offset_to_top 是 −16，因为从 `B` 子对象回到 `C` 的起点要减 16。

`call_fb` 只知道自己拿到的是 `B&`，它把指向 `B` 子对象的指针作为 `this` 传给 vtable 槽里的函数。但 `C::fb` 期望 `this` 指向 `C` 的起点。所以次级 vtable 的槽 6 放的不是 `C::fb` 本身，而是一个 **thunk**：一小段先把 `this` 减 16、再执行 `C::fb` 的代码。

```text
_ZN1C2fbEv:                                   # C::fb()
	movl	0x1c(%rdi), %eax          # this->c，c 在 C 中的偏移是 28
	retq
_ZThn16_N1C2fbEv:                             # non-virtual thunk to C::fb()
	movl	0xc(%rdi), %eax           # this 指向 B 子对象，c 在它后面 12 字节
	retq
_Z4to_bP1C:
	leaq	0x10(%rdi), %rax
	testq	%rdi, %rdi
	cmoveq	%rdi, %rax                # 派生类到基类的转换：空指针保持为空
	retq
```

`-O2` 下 thunk 被优化成了 `C::fb` 的一份带偏移的副本（`0x1c - 0x10 = 0xc`），不需要真的跳转。修饰名 `_ZThn16_` 中的 `h` 表示非虚调整，`n16` 是 −16。

`to_b` 说明，在多重继承下，派生类指针到基类指针的转换（[[conv.ptr]]）会改变指针的值，而且必须单独处理空指针。

## 虚基类

虚继承让菱形继承中的公共基类只有一个子对象（[[class.mi]]）。代价是虚基类相对于其他基类子对象的位置不再固定，它取决于最派生类型。

```cpp title="vb.cpp"
struct V { virtual int fv(); int v = 0; };
struct L : virtual V { virtual int fl(); int l = 1; };
struct R : virtual V { virtual int fr(); int r = 2; };
struct D : L, R { int fv() override; int d = 3; };
int V::fv() { return 0; }
int L::fl() { return 1; }
int R::fr() { return 2; }
int D::fv() { return d; }
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

在独立的 `L` 对象中，`V` 位于偏移 16；而在 `D` 中，`L` 子对象位于偏移 0，`V` 却在偏移 32。`L` 的 `nvsize=12` 说明，`L` 作为基类被嵌入时只带上自己的 12 个字节，虚基类由最派生类统一放在末尾。

### vbase_offset

既然偏移不固定，`L&` 转 `V&` 就只能在运行时查表。查的是 vtable 中 offset_to_top 前面的 **vbase_offset**：

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
	movq	(%rdi), %rcx              # 读 vptr
	addq	-0x18(%rcx), %rax         # vptr 往前 3 个槽：vbase_offset
	retq
```

对 `D` 中的 `L` 子对象，vbase_offset 是 32；对独立的 `L` 对象是 16。同一段 `to_v` 代码在两种情况下都正确。

### vcall_offset 与虚 thunk

`D::fv` 覆盖了虚基类 `V` 的 `fv`。通过 `V&` 调用时，`this` 指向 `V` 子对象，需要调整回 `D` 的起点。但调整量取决于最派生类型（`V` 在 `D` 中偏移 32，在别的类中可能不同），不能写死在 thunk 里。所以 `V`-in-`D` 的次级 vtable 多了一个 **vcall_offset**（槽 9，值 −32），由 thunk 在运行时读取：

```text
_ZTv0_n24_N1D2fvEv:                           # virtual thunk to D::fv()
	movq	(%rdi), %rax              # 读 V 子对象的 vptr
	movq	-0x18(%rax), %rax         # vptr - 24 处的 vcall_offset（-32）
	movl	0x1c(%rdi,%rax), %eax     # (this + vcall_offset)->d，d 在 D 中的偏移是 28
	retq
```

修饰名中的 `v0_n24_` 表示：先做 0 的非虚调整，再从 vptr 偏移 −24 处读出 vcall_offset 并加到 `this` 上，正对应转储中的 `-24 vcall offset offset`。

### 构造 vtable 与 VTT

最麻烦的是构造过程。按 [[class.cdtor#4]]，在 `L` 的构造函数执行期间，虚调用分派到 `L` 的版本，`typeid` 也得到 `L`。但此刻 `L` 子对象位于 `D` 中，`V` 在偏移 32 而不是独立 `L` 对象中的 16。如果直接使用 `L` 自己的 vtable，vbase_offset 就是错的。

Itanium ABI 为 `L` 作为 `D` 的基类这种情形专门生成一张**构造 vtable**（construction vtable）：虚函数按 `L` 的语义填写，偏移按 `D` 的布局填写。

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

与 `L` 自己的 vtable 相比，只有 vbase_offset（16 变成 32）和对应的 offset_to_top（−16 变成 −32）不同。

`D` 的构造函数通过 **VTT**（virtual table table，`_ZTT1D`）把这些构造 vtable 的地址交给基类的基类子对象构造函数（C2）。这正是 C1 和 C2 必须区分的原因之一。本机生成的 `_ZTT1D` 有 7 项（加数是十六进制）：

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

依次是：`D` 主 vtable 的地址点；`L`-in-`D` 构造 vtable 的两个地址点（`L` 自己的和其中 `V` 的）；`R`-in-`D` 的两个地址点；以及 `D` 完整 vtable 中 `V` 和 `R` 的次级地址点。构造过程中每进入一层构造函数，各子对象的 vptr 就被改写成这一层对应的地址点。构造期间动态类型逐层变化的语义，就是这样通过一次次写 vptr 实现的。

## key function：vtable 在哪个 TU 中生成

很多 TU 都可能需要同一个类的 vtable，但它只应该有一份定义。Itanium ABI 的规则是：

- 类的 **key function** 是在类定义结束时，第一个既不是纯虚函数、也不是 inline 函数的虚函数。
- 有 key function 的类，vtable 和 typeinfo 只在定义 key function 的那个 TU 中生成，是强定义。
- 没有 key function 的类，vtable 在每个用到它的 TU 中都生成一份弱定义（放在 COMDAT 组里），由链接器去重。这种做法叫 vague linkage，见 [[toolchain/linking-and-symbols]]。

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

- `HasKey` 的 key function 是 `f`，本 TU 定义了它，所以 vtable 是强定义（`D`）。其他包含 `HasKey` 的定义但不定义 `f` 的 TU 只有一个未定义引用（`U`）。
- `NoKey` 的虚函数全是 inline，vtable 是弱定义（`V`）。`-Wweak-vtables` 会提醒这一点，因为每个 TU 都要付出生成和去重的代价。
- `LateInl` 的 `f` 在类定义结束时还没有被声明为 inline，之后才定义为 inline。Clang 的处理结果是它也没有 key function，vtable 为弱定义。

这条规则与标准的联系在 [[basic.def.odr#8]] 和 [[class.virtual#12]]：非纯虚的虚函数总是被 odr-use，所以必须有定义。如果声明了 key function 却忘了定义它，vtable 就不会在任何 TU 中生成，而所有构造函数都引用这个 vtable。结果就是常见的链接错误 "undefined reference to vtable for X"（GNU ld 的说法，本机 Apple ld 的输出见 [[toolchain/linking-and-symbols]]）。报错指向 vtable 而不是那个忘了定义的函数，所以常常让人摸不着头脑。

## 思考题

!!! question "思考题 1"
    `struct P { int i; char c; };` 是一个库的公开类型，用户代码里有 `struct Q : P { char x; };`。库的新版本只给 `P` 加了一个空的用户构造函数 `P() {}`。用户不重新编译，只换上新的库，会出什么问题？

<details markdown="1">
<summary>答案</summary>

加构造函数之前，`P` 是 C++03 意义上的 POD，`dsize` 是 8，`Q::x` 在偏移 8，`sizeof(Q)` 是 12。加了之后 `P` 不再是 POD，`dsize` 变成 5，按新头文件编译的代码会把 `Q::x` 放在偏移 5，`sizeof(Q)` 变成 8。

没有重新编译的用户代码仍按旧布局访问 `Q`。只要有一处按新头文件编译的代码（比如库里的模板实例化或 inline 函数）和它交换 `Q` 对象，两边对 `x` 的位置和 `Q` 的大小就理解不同。在标准层面，这是同一个类在不同 TU 中有不同的定义，违反 ODR，程序非良构、不要求诊断（[[basic.def.odr]]）。
</details>

!!! question "思考题 2"
    为什么通过 `B&` 调用 `C::fb` 用的是非虚 thunk（`_ZThn16_`），而通过 `V&` 调用 `D::fv` 要用虚 thunk（`_ZTv0_n24_`）？

<details markdown="1">
<summary>答案</summary>

非虚基类 `B` 在 `C` 中的偏移只由 `C` 的定义决定，无论 `C` 对象嵌在什么更大的对象里，从 `B` 子对象回到 `C` 起点都是减 16，可以写死在 thunk 里。虚基类 `V` 的位置由最派生类型决定：`D` 若再被别的类虚继承或继承，`V` 与 `D` 子对象的距离会变化，所以调整量只能放在 vtable 的 vcall_offset 里，由 thunk 在运行时读取。
</details>
