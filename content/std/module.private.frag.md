---
title: 私有模块片段
summary: module :private; 让只有一个文件的模块也能把实现细节对导入者隐藏起来；导入者需要的一切都必须写在它之前。
status: done
since: c++20
papers: P1103R3
related: module.unit, module.interface, module.reach, module.context, basic.link, dcl.inline, dcl.spec.auto, temp.point
tags: 模块, 私有模块片段
updated: 2026-10-19
---

!!! tldr
    - `module :private;` 把一个模块接口单元分成两半：之前的部分影响导入者，之后的部分只用来生成本模块的目标代码，对导入者不可达。
    - 私有模块片段只能出现在主模块接口单元里，而且这个模块不能有其他单元（违反时不要求诊断）。
    - inline 函数、模板、返回类型待推导的导出函数，定义都必须写在私有模块片段之前。
    - 私有模块片段中的声明不受暴露检查，可以随意使用 `static` 函数之类只能在本 TU 使用的实体。
    - 典型用法是单文件模块和不透明句柄：导出一个不完整类型，把它的定义放进私有模块片段。

## 一个文件里分开接口与实现

```cpp title="handle.cppm"
export module handle;
export struct Handle;                    // 导出一个不完整类型
export Handle* make();
export int value(const Handle*);
export void destroy(Handle*);
module :private;
struct Handle { int v = 42; };           // 对导入者不可达
Handle* make() { return new Handle; }
int value(const Handle* h) { return h->v; }
void destroy(Handle* h) { delete h; }
```

<div class="compare" markdown="1">

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
int n = sizeof(Handle);
// error: Handle 的定义
// 不可达
```

</div>

传统 C++ 用头文件加源文件分开接口与实现。模块也可以这样：主接口单元放声明，实现单元（`module M;`）放定义。但对小模块来说两个文件是多余的负担，尤其是只想把一个 `.cpp` 文件改造成模块的时候。

[[g:private-module-fragment|私有模块片段]]（private module fragment）让一个文件同时承担两种角色。`module :private;` 之后的内容仍在模块的管辖范围中，仍附属于这个模块，但对其他 TU 不可达（[[module.reach#3]]）。上面 `main.cpp` 正常运行并返回 0；`peek.cpp` 看不到 `Handle` 的定义，Clang 23 报 "'Handle' must be defined before it is used"，附注 "definition here is not reachable"。

```text
private-module-fragment:
    module-keyword : private ; declaration-seq(opt)
```

## 只能用在单文件模块中（¶1）

¶1 私有模块片段只能出现在主模块接口单元中（[[module.unit#2]]）。含有私有模块片段的模块单元必须是它所在模块的唯一单元，违反时不要求诊断（{{ifndr}}）。

```cpp title="P-part.cppm" error
export module P:part;
module :private;          // error: 私有模块片段只能在主模块接口单元中
```

Clang 23 对此报 "private module fragment declaration with no preceding module declaration"。拒绝是对的，但措辞不太准确。

要求唯一，是因为私有模块片段就是为单文件模块设计的。如果模块还有实现单元，实现单元隐式导入主接口（[[module.unit#8]]），本该能看到主接口中的一切，私有片段的内容却对它不可达，同一模块内部的视图就不一致了。况且已经有实现单元可以容纳实现细节，私有片段就没有存在的必要。

编译器一次只看一个 TU，发现不了模块的其他单元，所以这条只能是不要求诊断的。本机 Clang 23 编译一个 `module A2;` 实现单元（A2 的主接口带私有片段）时没有任何诊断。

## 导入者需要的一切都在它之前（¶2）

¶2 注 1 说明，私有模块片段结束了模块接口单元中能影响其他 TU 行为的部分。它的存在影响下面六件事，相应的规范性规则散布在各处：

| | 受影响的规则 | 具体规定 |
|---|---|---|
| ¶2.1 | inline 函数、变量的定义最迟在哪里给出 | 附属于具名模块的 inline 实体，必须在声明它的定义域中定义（[[dcl.inline#5]]）。私有片段是一个单独的定义域（[[basic.def.odr#13]]） |
| ¶2.2 | 返回类型待推导的导出函数的定义最迟在哪里给出 | 必须在私有片段之外定义（[[dcl.spec.auto#12]]） |
| ¶2.3 | 声明是否不得为暴露 | [[basic.link#17]] 只检查私有片段之外的声明 |
| ¶2.4 | inline 函数和模板的定义必须出现在哪里 | 导入者需要的定义必须在私有片段之前（[[basic.def.odr]]、[[temp.pre]]） |
| ¶2.5 | 在它之前实例化的模板的实例化语境 | 额外的实例化点放在私有片段之前，而不是 TU 末尾（[[temp.point#7]]、[[module.context#3]]） |
| ¶2.6 | 其中声明的可达性 | 对其他 TU 不可达（[[module.reach#3]]） |

这些规则归结起来就是一条：导入者看到的一切，都必须写在 `module :private;` 之前。

¶2.3 中的**暴露**（[[g:exposure|exposure]]）是指一个声明用到了 TU-local 实体，即只能在本 TU 中使用的实体（例如 `static` 函数，见 [[basic.link#15]]）。模块接口中的暴露是非良构的，因为导入者可能需要那个实体却拿不到。私有片段中的声明对导入者不可达，导入者永远用不到它们，所以不必检查。

## 例子（¶3）

¶3 标准的例 1：

```cpp title="A.cppm" error
export module A;
export inline void fn_e();      // error: 导出的 inline 函数 fn_e 没有在私有片段之前定义
inline void fn_m();             // error: 未导出的 inline 函数 fn_m 没有在私有片段之前定义
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

- `fn_e` 和 `fn_m` 附属于具名模块 A，在私有片段之前的定义域中声明，却在私有片段中定义，违反 [[dcl.inline#5]]。`fn_m` 没有导出也不行，这条规则看的是附属，与导出无关。Clang 23 对两者都报 "inline function not defined before the private module fragment"，附注 "private module fragment begins here"。
- `g` 调用 `static` 的 `fn_s`。`g` 不是 inline 函数，判断暴露时忽略它的函数体（[[basic.link#14]]），所以这不是暴露。导入者调用 `g` 只需要它的符号。
- `X` 以不完整类型导出，定义放在私有片段中，导入者只能使用 `X*`。这就是开头 `handle` 的写法。
- `factory` 是普通函数，导入者只需要它的声明，定义可以放在私有片段里。

### 返回类型待推导的导出函数

```cpp title="auto.cppm" error
export module autom;
export auto deduced();
module :private;
auto deduced() { return 1; }    // error: 必须在私有片段之外定义（[dcl.spec.auto]/12）
```

导入者调用 `deduced()` 时需要知道返回类型，而私有片段中的定义对它不可达，所以 [[dcl.spec.auto#12]] 要求定义写在私有片段之外。

!!! impl "Clang 的偏差"
    本机 Clang 23 接受 `auto.cppm`，不给任何诊断。导入者调用 `deduced()` 也能编译，程序返回 1，说明 Clang 用到了私有片段中的定义。[[dcl.spec.auto#12]] 是可诊断规则，这是 Clang 不符合标准之处。

## 私有模块片段与实现单元

| | 私有模块片段 | 实现单元 `module M;` |
|---|---|---|
| 文件数 | 1 | 至少 2 |
| 修改实现后导入者是否需要重新编译 | 按标准不需要，实际上取决于工具链（见下） | 不需要，实现单元不产出 BMI |
| 能否有分区 | 不能，模块只有这一个单元 | 能 |
| 实现中能否使用接口里的 `static` 函数 | 能，同一个 TU | 不能，内部链接不跨 TU |
| 适合 | 小模块、把单个 `.cpp` 改成模块 | 大模块、并行编译 |

在标准层面，私有片段不影响其他 TU 的行为。能否借此避免重新编译导入者，取决于编译器能否在私有片段改变时产出逐字节不变的 BMI（二进制模块接口，编译器为导入者缓存的接口信息），以及构建系统是按内容还是按时间戳判断是否过期。BMI 和目标文件由同一个文件产出，按时间戳判断的构建系统仍会重新编译导入者。这是实现质量问题。

## 历史与演进

!!! history
    私有模块片段随 [[P1103R3]] 进入 C++20，目的是让单文件模块也能分开接口与实现。Modules TS 中没有对应的设施。

## 常见误解

!!! pitfall "constexpr 函数可以定义在私有片段里"
    不行。`constexpr` 函数隐式 inline，和显式写了 `inline` 的函数一样，必须在私有片段之前定义。具名模块中类内定义的成员函数不是隐式 inline 的（[[class.mfct#1]]），所以在私有片段之前声明、在私有片段中定义的普通成员函数没有问题。

!!! pitfall "模板定义可以放进私有片段"
    导出的模板如果只在私有片段中定义，导入者实例化时看不到定义，无法使用它。模板定义要写在私有片段之前。

## 思考题

!!! question "思考题 1"
    下面的模块中，`get` 在私有片段中定义。导入者能否调用 `S{}.get()`？如果把类内的声明改成 `inline int get();` 呢？

    ```cpp
    export module m;
    export struct S { int get(); };
    module :private;
    int S::get() { return 1; }
    ```

<details markdown="1">
<summary>答案</summary>

能。`get` 不是 inline 函数（在类外定义，也没有写 `inline`），导入者只需要它的声明和符号；`S` 的定义在私有片段之前，可达。本机 Clang 23 编译运行通过。

改成 `inline int get();` 之后，`get` 是附属于具名模块的 inline 函数，在私有片段之前的定义域中声明，就必须在那里定义（¶2.1、[[dcl.inline#5]]），在私有片段中定义是非良构的。
</details>

!!! question "思考题 2"
    `export inline int api() { return helper(); }` 中的 `helper` 是 `static` 函数。把 `api` 的定义挪进私有片段能否解决暴露问题？

<details markdown="1">
<summary>答案</summary>

不能。暴露检查确实不管私有片段中的声明（¶2.3），但 `api` 是 inline 函数，必须在私有片段之前定义（¶2.1）。可行的做法是去掉 `inline`：在私有片段之前只写 `export int api();`，把定义放进私有片段。另一种做法是让 `helper` 不再是 `static` 的，它具有模块链接，就不是 TU-local 实体了。
</details>
