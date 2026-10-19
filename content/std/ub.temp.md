---
title: 核心 UB 目录 · 第 [temp] 章
summary: 模板实例化陷入无限递归的结果未定义；这是一种编译期的 UB，实际编译器会在实现定义的深度上限处停下并报错。
status: done
related: ub, temp.inst, implimits, ifndr
tags: UB, 附录, 模板, 编译期
updated: 2026-10-19
---

!!! tldr
    - 第 13 章里明文写成未定义行为的只有一处：模板实例化陷入无限递归（[[temp.inst#18]]）。
    - 这是编译期的 UB。标准对编译过程本身不作要求，编译器可以报错、耗尽内存，也可以一直不结束。
    - 实际的编译器会在一个实现定义的递归深度上限处停下并报错。Clang 默认是 1024 层，可以用 `-ftemplate-depth=N` 调整。
    - 模板相关的其他陷阱大多是 IFNDR（程序非良构，但标准不要求编译器诊断），收录在 Annex G [[ifndr]]。

Annex F 汇总了核心语言中明文写出的未定义行为，总览见 [[ub]]。它的 F.7 节对应第 13 章 [temp]，只有一条，而且与其他条目不同：它发生在编译期，不在程序运行时。

### F.7.1 模板实例化的无限递归 {#temp.inst.inf.recursion}

`[ub:temp.inst.inf.recursion]` · 正文 [[temp.inst#18]]

```cpp ub
template <class T>
class X {
  X<T>* p;   // OK：指针成员不要求 X<T> 是完整类型，不触发实例化
  X<T*> a;   // 实例化 X<T> 需要完整的 X<T*>，后者又需要 X<T**>……
};

int main() {
  X<int> x;   // UB：实例化陷入无限递归
}
```

定义 `X<int>` 类型的变量，需要隐式实例化 `X<int>`。它有一个 `X<int*>` 类型的成员，成员的类型必须是完整类型，于是又要实例化 `X<int*>`，以此类推，这条链永远不会结束。成员 `p` 只是指针，指针指向的类型不必完整，所以不会引起实例化。

[[temp.inst#18]] 先规定递归实例化的总深度有一个实现定义的上限，这个上限可能涉及多个模板；然后说无限递归的结果是未定义的。Annex B [[implimits]] 建议这个上限至少是 1024。

本机 Clang 23 不会真的无限递归。它在到达上限时报 `fatal error: recursive template instantiation exceeded maximum depth of 1024`，并提示可以用 `-ftemplate-depth=N` 调整上限；加上 `-ftemplate-depth=50` 后，报错里的数字相应变为 50。

为什么标准不把它规定成非良构、要求编译器诊断？模板实例化的能力等价于一台图灵机，编译器无法在一般情况下判定一条实例化链会不会终止，所以标准无法要求它可靠地报告无限递归。另一方面，超出实现限制的程序本来就可以被拒绝（[[intro.compliance.general#2.1]]）。于是这里的未定义只有一个实际含义：标准对编译过程不作要求，编译器报错、因内存耗尽而崩溃、一直运行下去，都不违反标准。

这条 UB 不会留到运行时，程序根本生成不出来，所以也就谈不上用 sanitizer 检测。实践中需要关心的只是深度上限本身，各编译器的默认值见 [[implimits]]。
