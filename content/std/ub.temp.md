---
title: 核心 UB 目录 · 第 [temp] 章
summary: Annex F.7 唯一的一条：模板实例化无限递归的结果未定义——一种发生在编译期的 UB，以及实现定义的递归深度上限如何把它变成一条确定的错误。
status: draft
related: ub, temp.inst, implimits, ifndr
tags: UB, 附录, 模板, 编译期
updated: 2026-10-18
---

这一页是 [[ub]] 的一部分，对应 Annex F.7。第 13 章 [temp] 的"坑"大多是 IFNDR（见 [[ifndr#templates]]），显式写成 UB 的只有一条，而且它很特别：它是**翻译期**的未定义行为。

### F.7.1 [ub:temp.inst.inf.recursion] {#temp.inst.inf.recursion}

**模板实例化的无限递归** · 正文 [[temp.inst#18]]

实例化一个类模板特化，可能需要实例化其他特化（成员的类型要求完整类型时）。如果这条链永远不会终止，标准说"结果未定义"。同一段的前一句给了实现一条出路：递归实例化的总深度有一个**实现定义**的上限（Annex B [[implimits]] 建议至少 1024 层），可能涉及多个模板。

```cpp ub
template <class T>
class X {
  X<T>* p;   // OK：指针成员不要求 X<T> 是完整类型，不会触发实例化
  X<T*> a;   // 实例化 X<T> 需要完整的 X<T*>，后者需要 X<T**>……
};

int main() {
  X<int> x;   // UB：实例化陷入无限递归
}
```

**实测**：Clang 不会真的无限递归，而是在达到上限时停下：`fatal error: recursive template instantiation exceeded maximum depth of 1024`，并提示 `use -ftemplate-depth=N to increase recursive template instantiation depth`；加 `-ftemplate-depth=50` 后上限相应变为 50。

为什么这一条是 UB 而不是"ill-formed"？因为编译器无法在一般情况下判定一条实例化链是否终止（模板是图灵完备的），标准不能要求它"诊断无限递归"；而一旦超出资源上限，[[intro.compliance.general#2.1]] 本来就允许实现拒绝程序。"未定义"在这里的现实含义是：编译器可以报错、可以耗尽内存崩溃、也可以永不结束——标准对**翻译过程**不作要求。翻译期 UB 不止这一处：违反 IFNDR 规则同样会让整个程序失去约束（见 [[ifndr]]）。

与运行期 UB 的另一个区别：这里不存在"sanitizer 能不能抓到"的问题——程序根本生成不出来。实践中值得关心的只有上限本身，Clang 的默认值与实测见 [[implimits]]。
