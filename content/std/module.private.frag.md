---
title: 私有模块片段
summary: module :private; 让只有一个文件的模块也能对导入者隐藏实现细节；它只能出现在唯一的模块单元中，并影响 inline 定义的位置、暴露检查、实例化语境与可达性。
status: done
since: c++20
papers: P1103R3
related: module.unit, module.interface, module.reach, module.context, basic.link, dcl.inline, dcl.spec.auto, temp.point
tags: 模块, 私有模块片段
updated: 2026-10-18
---

传统 C++ 用头文件加源文件的方式分离接口与实现。模块也可以这样做：主接口单元放声明，实现单元放定义。但对小模块来说，两个文件是不必要的负担，尤其是只想把一个 `.cpp` 文件改造成模块的时候。

[[g:private-module-fragment|私有模块片段]]（private module fragment）让一个文件同时承担这两种角色：

```cpp
export module A;
export int f();          // 接口：影响导入者
module :private;
int f() { return 42; }   // 实现：对导入者不可达，修改它不应引起导入者重新编译
```

`module :private;` 之后的内容仍在模块 A 的管辖范围中（附属于 A），但**不会影响其他 TU**：它们既不可达，也不参与暴露检查。

阅读前需要：[[module.unit]]、[[module.reach]]。

## 语法与约束（¶1）

```text
private-module-fragment:
    module-keyword : private ; declaration-seq(opt)
```

¶1 *private-module-fragment* 只能出现在主模块接口单元中（[[module.unit#2]]）。含有私有模块片段的模块单元必须是其模块唯一的模块单元；{{ifndr}}。

为什么要求唯一？私有片段是为单文件模块设计的。如果模块还有别的单元：

- 实现单元会隐式导入主接口单元（[[module.unit#8]]），理应能看到主接口中的一切，但私有片段的内容对它们不可达，同一模块内部的视图就不一致了；
- 已经有实现单元可以容纳实现细节了，私有片段就失去了存在的理由。

由于编译器看不见整个模块，这条只能是 IFNDR。本机 Clang 23 编译一个 `module A2;` 实现单元（A2 的主接口带私有片段）时没有任何诊断。

```cpp title="P-part.cppm" error
export module P:part;
module :private;        // error: 私有模块片段只能在主模块接口单元中
```

Clang 23 对此报出 "private module fragment declaration with no preceding module declaration"。拒绝是对的，但措辞不太准确。

## 私有片段影响什么（¶2）

¶2 Note 1（非规范性的，但列出了散布在各处的规范性规则）：私有模块片段结束了模块接口单元中能影响其他 TU 行为的部分。有了它，模块可以表示为单个 TU，而不必让模块的全部内容对导入者可达。私有片段的存在会影响以下几方面：

| | 规则 | 效果 |
|---|---|---|
| **¶2.1** | inline 函数/变量的定义最迟何时必须给出（[[dcl.inline]]） | 附属于具名模块的 inline 实体必须在声明它的定义域中定义（[[dcl.inline#5]]）；私有片段是单独的定义域（[[basic.def.odr]]），所以在私有片段之前声明的 inline 函数，必须在私有片段之前定义 |
| **¶2.2** | 返回类型含占位符的导出函数的定义最迟何时给出（[[dcl.spec.auto]]） | 必须在私有片段之外定义（[[dcl.spec.auto#12]]），否则导入者无法推导返回类型 |
| **¶2.3** | 声明是否需要不是暴露（[[basic.link]]） | [[basic.link#17]] 只检查私有片段之外的声明；私有片段中的声明可以随意引用 TU-local 实体 |
| **¶2.4** | inline 函数与模板的定义必须出现在哪里（[[basic.def.odr]]、[[dcl.inline]]、[[temp.pre]]） | 导入者需要的定义（inline 函数体、模板定义）必须在私有片段之前 |
| **¶2.5** | 在它之前实例化的模板的实例化语境（[[module.context]]） | 把实例化点推迟到 TU 末尾的规则以私有片段为界（[[temp.point#7]]） |
| **¶2.6** | 其中声明的可达性（[[module.reach]]） | 私有片段中的声明对其他 TU 不可达（[[module.reach#3]] ¶3.1.2） |

归结起来只有一条：**导入者看到的一切，都必须在 `module :private;` 之前。**私有片段之后的东西只用于为本 TU 生成目标代码。

## 例子（¶3）

¶3 Example 1（加注）：

```cpp title="A.cppm" error
export module A;
export inline void fn_e();      // error: 导出的 inline 函数 fn_e 未在私有片段之前定义
inline void fn_m();             // error: 未导出的 inline 函数 fn_m 未在私有片段之前定义
static void fn_s();
export struct X;
export void g(X *x) {
  fn_s();                       // OK：调用同一 TU 中的 static 函数
}
export X *factory();            // OK

module :private;
struct X {};                    // 这个定义对 A 的导入者不可达
X *factory() {
  return new X ();
}
void fn_e() {}
void fn_m() {}
void fn_s() {}
```

逐行分析：

- `fn_e`、`fn_m`：inline 函数附属于具名模块 A，必须在声明它的定义域中定义（[[dcl.inline#5]]）。它们在私有片段之前的定义域中声明，却在私有片段中定义，所以非良构。注意未导出的 `fn_m` 也不行：这条规则针对的是附属于具名模块的实体，与是否导出无关。
- `g` 调用 `static` 的 `fn_s`：`g` 不是 inline 的，暴露检查会忽略它的函数体（[[basic.link#14]] ¶14.1），所以这不是暴露。导入者调用 `g` 只需要它的符号。
- `X` 以不完整类型导出，定义放在私有片段中，导入者只能使用 `X*`。这就是 PIMPL / 不透明句柄在模块中的写法。
- `factory` 的定义在私有片段中：普通函数，导入者只需声明。

!!! impl "本机诊断"
    Clang 23 对 `fn_e` 和 `fn_m` 都报 "inline function not defined before the private module fragment"，并附注 "private module fragment begins here"。

### 一个完整的不透明句柄

```cpp title="handle.cppm"
export module handle;
export struct Handle;                    // 导出不完整类型
export Handle* make();
export int value(const Handle*);
export void destroy(Handle*);
module :private;
struct Handle { int v = 42; };           // 对导入者不可达
Handle* make() { return new Handle; }
int value(const Handle* h) { return h->v; }
void destroy(Handle* h) { delete h; }
```

```cpp title="main.cpp" ok
import handle;
int main() {
  Handle* h = make();
  int r = value(h) - 42;
  destroy(h);
  return r;
}
```

```cpp title="peek.cpp" error
import handle;
int n = sizeof(Handle);   // error: Handle 的定义不可达（在私有片段中）
```

Clang 23 对 `peek.cpp` 报 "'Handle' must be defined before it is used"，附注 "definition here is not reachable"。

### 占位符返回类型

```cpp title="auto.cppm" error
export module autom;
export auto deduced();          // 返回类型待推导
module :private;
auto deduced() { return 1; }    // error: 导出的占位符返回类型函数必须在私有片段之外定义（[dcl.spec.auto]/12）
```

!!! impl "Clang 的偏差"
    本机 Clang 23 接受上面的 `auto.cppm`，不给出诊断。[[dcl.spec.auto#12]] 是可诊断规则，所以这是 Clang 不符合标准之处。直到导入者调用 `deduced()`，才会因返回类型无法推导而失败。

## 私有片段 vs 实现单元

| | 私有模块片段 | 实现单元 `module M;` |
|---|---|---|
| 文件数 | 1 | ≥ 2 |
| 修改实现后导入者是否需要重编 | 概念上不需要；但实际上 BMI 由同一个文件产出，构建系统通常只看文件时间戳，仍会触发重编 | 不需要（实现单元不产出 BMI） |
| 能否有分区 | 不能（模块只有这一个单元） | 能 |
| 实现中能否使用接口中的 `static` 函数 | 能（同一 TU） | 不能（内部链接，跨 TU） |
| 适合 | 小模块、把单个 `.cpp` 改成模块 | 大模块、并行编译 |

注意第二行：在标准层面，私有片段不影响其他 TU 的行为，但能否利用这一点，取决于编译器能否产出内容稳定的 BMI（私有片段改变时 BMI 字节不变），以及构建系统是否按内容而非时间戳判断。这属于实现质量问题。

## 历史与演进

!!! history "C++20"
    私有模块片段随 [[P1103R3]] 进入 C++20，起因是希望单文件模块也能分离接口与实现。Modules TS 中没有对应设施。

## 陷阱

!!! pitfall "在私有片段中定义 inline 函数"
    这包括 `constexpr` 函数（隐式 inline）和显式写了 `inline` 的成员函数。具名模块中类内定义的成员函数不是隐式 inline 的（[[class.mfct#1]]），所以在私有片段之前声明、在私有片段中定义的普通成员函数没有问题。

!!! pitfall "以为私有片段中的东西对模块其他单元可见"
    模块根本不能有其他单元（¶1，IFNDR）。

!!! pitfall "模板定义放进私有片段"
    导出的模板若只在私有片段中定义，导入者实例化时看不到定义（不可达），只能使用私有片段之前已显式实例化的特化。

## 思考题

!!! question "思考题 1"
    下面的模块中，`get` 在私有片段中定义。导入者能否调用 `S{}.get()`？如果在全局模块（普通头文件）中这样写呢？

    ```cpp
    export module m;
    export struct S { int get(); };
    module :private;
    int S::get() { return 1; }
    ```

<details markdown="1">
<summary>答案</summary>

能。`get` 不是 inline 函数（类外定义且未写 `inline`），导入者只需它的声明和符号；`S` 的定义在私有片段之前，可达。在普通头文件+源文件中，这相当于把 `S::get` 定义在源文件里，同样没问题。若把 `get` 改成在类内声明为 `inline int get();`，则在私有片段中定义它就是非良构的（¶2.1、[[dcl.inline#5]]）。
</details>

!!! question "思考题 2"
    为什么私有片段中的声明可以命名 TU-local 实体而不构成被禁止的暴露？

<details markdown="1">
<summary>答案</summary>

暴露规则的目的，是防止导入者需要用到某个 TU-local 实体（例如 inline 函数体中调用了 `static` 函数，导入者内联它时就需要那个 `static` 函数）。私有片段中的声明对其他 TU 不可达（[[module.reach#3]]），导入者永远看不到它们，自然也不需要它们引用的 TU-local 实体。所以 [[basic.link#17]] 明确只检查私有片段之外的声明。
</details>

## 小结

| 规则 | 依据 |
|---|---|
| 只能在主模块接口单元中；该模块只能有这一个单元（IFNDR） | ¶1 |
| 私有片段中不能 `export` | [[module.interface#1]] |
| 私有片段之前声明的 inline 函数必须在私有片段之前定义 | ¶2.1、[[dcl.inline#5]] |
| 导出的 `auto` 返回类型函数必须在私有片段之前定义 | ¶2.2、[[dcl.spec.auto#12]] |
| 私有片段中的声明不受暴露检查，对其他 TU 不可达 | ¶2.3、¶2.6 |
| 典型用途：单文件模块、不透明句柄 | ¶3 |
