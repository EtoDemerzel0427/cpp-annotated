---
title: 成员模板
summary: 在类或类模板里声明的模板；类外定义要写两层 template-head；析构函数和虚函数不能是模板；非模板成员与同类型的模板特化并存时谁优先；转换函数模板的特化怎样命名。
status: done
covers: temp.mem
since: c++98
related: temp.class, temp.over.link, class.conv.fct, temp.deduct.conv, class.virtual, class.copy.ctor, expr.prim.lambda, temp.expl.spec
tags: 模板, 成员模板, 虚函数, 转换函数
updated: 2026-10-19
---

!!! tldr
    - 类模板的成员模板在类外定义时，要先写类模板的 *template-head*，再写成员模板自己的，两层不能合并。
    - 析构函数不能是模板，成员函数模板不能是虚函数，非闭包的局部类不能有成员模板；泛型 lambda 是例外。
    - 成员函数模板的特化不会覆盖基类的虚函数，但会隐藏同名的基类成员。
    - 非模板成员函数和能生成同类型特化的成员模板可以并存；不写显式模板实参时，优先指非模板的那个。
    - 构造函数模板永远不是复制或移动构造函数，但在重载决议中可能胜过它们。

## 两层模板（¶1）

```cpp run ok
template<class T> struct string {
    template<class T2> int compare(const T2&);
    template<class T2> string(const string<T2>&) { }   // 类内定义
    string() = default;
};

template<class T> template<class T2>
int string<T>::compare(const T2&) { return 0; }        // 外层在前，内层在后

int main() {
    string<char> s;
    string<wchar_t> w(s);              // 构造函数模板：T = wchar_t, T2 = char
    return s.compare(w);
}
```

¶1 在类或类模板内部声明的模板叫**成员模板**（member template），可以是成员函数模板、成员类模板、静态数据成员模板或成员别名模板。`std::vector<T>` 的范围构造函数 `template<class InputIt> vector(InputIt, InputIt)` 就是一个成员模板：它既依赖外层的 `T`，又有自己的形参 `InputIt`。

成员模板可以在类内定义，也可以在类外定义。类模板的成员模板在类外定义时，要先写一个与类模板等价的 *template-head*，再写一个与成员模板等价的 *template-head*（等价的含义见 [[temp.over.link#6]]）。

两层不能合并成 `template<class T, class T2>`。那样写的是一个有两个形参的模板，而要定义的是单形参类模板的一个成员，这个成员自己又是一个单形参模板。

约束也要逐层等价：

```cpp error
template<typename T> concept C1 = true;
template<typename T> concept C2 = sizeof(T) <= 4;

template<C1 T> struct S {
    template<C2 U> void f(U);
    template<C2 U> void g(U);
};

template<C1 T> template<C2 U>
void S<T>::f(U) { }             // OK
template<C1 T> template<typename U>
void S<T>::g(U) { }             // error: S<T> 中没有无约束的 g
```

普通类的成员模板，类外定义只需要一层：

```cpp run ok
struct Logger {
    template<class T> void log(const T&);
};
template<class T> void Logger::log(const T&) { }
int main() { Logger{}.log(42); }
```

## 哪些成员不能是模板

### 局部类（¶2）

¶2 第一句规定，非闭包类型的局部类（在函数体内定义的类，[[class.local]]）不能有成员模板。同样，局部类里也不能声明友元模板（[[temp.friend#6]]）。

<div class="compare" markdown="1">

```cpp error
void f() {
  struct Local {
    template<class T>
    void g(T) { }    // error
  };
}
```

```cpp run ok
int main() {
  auto id = [](auto x) {
    return x;
  };
  return id(0);
}
```

</div>

非闭包类型这个限定是为泛型 lambda 留的。泛型 lambda 的闭包类型也是局部类，它的函数调用运算符是一个成员函数模板（[[expr.prim.lambda.closure]]），这是允许的。

¶2 第二句说明访问控制照常适用于成员模板的名字：`private` 的成员模板在类外不能访问（[[class.access]]）。

### 析构函数（¶2）

¶2 第三句：析构函数不能是成员模板。析构函数没有参数，模板实参无从推导，也没有语法可以显式指定。

```cpp error
struct X {
    template<class T> ~X();       // error: 析构函数不能是模板
};
```

C++20 起一个类可以有多个带不同约束的预期析构函数（prospective destructor），但它们都不是模板（[[class.dtor]]）。

构造函数可以是模板，但要注意两点。第一，构造函数模板的模板实参必须都能推导或有默认值，因为没有语法给构造函数显式指定模板实参（[[temp.arg.explicit]]）。第二，构造函数模板永远不是复制或移动构造函数（[[class.copy.ctor]]）：即使它能实例化出 `X(const X&)` 这样的签名，类仍会隐式声明复制构造函数。

不过在重载决议中，构造函数模板可能比复制构造函数更好：

```cpp run ok
#include <cstdio>
struct S {
    S() = default;
    S(const S&) { std::puts("copy ctor"); }
    template<class T> S(T&&) { std::puts("template ctor"); }
};
int main() {
    S a;
    S b = a;          // template ctor：T = S&，形参 S& 比 const S& 匹配得更好
    const S c;
    S d = c;          // copy ctor：形参类型相同，非模板优先
    (void)b; (void)d;
}
```

`S b = a` 复制一个非 const 左值，却调用了转发引用构造函数。常见的解决办法是给模板加约束，例如 `requires (!std::is_same_v<std::remove_cvref_t<T>, S>)`。

### 虚函数（¶3）

¶3 成员函数模板不能声明为 `virtual`：

```cpp error
template<class T> struct AA {
    template<class C> virtual void g(C);   // error: 虚成员函数模板
    virtual void f();                      // OK：类模板的普通成员函数可以是虚函数
};
```

虚函数通常用虚表实现：编译类定义时就要确定虚表的大小，每个虚函数占一个固定槽位。而成员函数模板的特化集合是开放的，任何翻译单元都可能用新的实参实例化 `g<C>`，编译类定义时无法知道需要多少个槽位。

`AA<T>::f` 不受影响。它不是函数模板，对每个特化 `AA<int>`，它就是一个普通成员函数，虚函数集合在该特化里是固定的。需要虚函数加泛型时，通常改用类型擦除（`std::function`、`std::any`）、访问者模式或 CRTP。

### 特化不覆盖虚函数（¶4）

¶4 成员函数模板的特化不会覆盖基类的虚函数：

```cpp run ok
#include <cstdio>
struct B {
    virtual void f(int) { std::puts("B::f"); }
    virtual ~B() = default;
};
struct D : B {
    template<class T> void f(T) { std::puts("D::f<T>"); }   // 不覆盖 B::f(int)
};
struct E : B {
    template<class T> void f(T) { std::puts("E::f<T>"); }
    void f(int i) override { f<>(i); }                       // 覆盖，再转发给模板
};
int main() {
    D d; E e;
    B& rd = d; B& re = e;
    rd.f(1);          // B::f
    re.f(1);          // E::f<T>
    d.f(1);           // D::f<T>
}
```

这是 ¶3 的推论：模板特化如果能覆盖虚函数，就等于进了虚表。`D::f` 仍然会隐藏 `B::f`，名字查找在 `D` 中找到 `f` 就停止（[[class.member.lookup]]），所以 `d.f(1)` 调用 `D::f<int>`；只是经 `B&` 的虚调用不会派发到它。

## 非模板成员优先（¶2）

¶2 最后一句：类中可以同时声明一个非模板成员函数，和一个同名的、能生成同类型特化的成员函数模板。两者并存时，用这个名字和类型指的是非模板成员，除非写了显式模板实参列表。

```cpp run ok
#include <cstdio>
template<class T> struct A {
    void f(int) { std::puts("non-template"); }
    template<class T2> void f(T2) { std::puts("template"); }
};

int main() {
    A<char> ac;
    ac.f(1);          // non-template：两者都是精确匹配，非模板优先
    ac.f('c');        // template：T2 = char 精确匹配，胜过 char 到 int 的提升
    ac.f<>(1);        // template：有显式模板实参列表（即使为空）
}
```

调用时，这与 [[over.match.best]] 中非模板优于模板特化的规则一致。在显式特化这类需要指名一个函数的地方，也按这条规则区分：

```cpp run ok
template<class T> struct A {
    void f(int);
    template<class T2> void f(T2);
};
template<> void A<int>::f(int) { }                  // 非模板成员 f(int)
template<> template<> void A<int>::f<>(int) { }     // 成员模板的特化 f<int>
int main() { A<int> a; a.f(1); a.f<>(1); }
```

两行的差别在 `f` 后有没有 `<>`。有 `<>` 就指模板的特化，这时成员模板本身也被特化了，所以要多写一层 `template<>`。

## 转换函数模板（¶5）

¶5 是一条注：转换函数模板的特化，与转换到同一类型的非模板转换函数用同样的方式命名（[[class.conv.fct]]）。`operator char*` 既可以指非模板的转换函数，也可以指 `template<class T> operator T*()` 在 `T = char` 时的特化。

```cpp run ok
struct A {
    template<class T> operator T*();
};
template<class T> A::operator T*() { return nullptr; }
template<> A::operator char*() { return nullptr; }      // 显式特化：T = char
template A::operator void*();                           // 显式实例化：T = void

int main() {
    A a;
    int* ip = a.operator int*();       // 显式调用，T 从 int* 推导
    double* dp = a;                    // 隐式转换，T 从目标类型推导
    return ip == nullptr && dp == nullptr ? 0 : 1;
}
```

转换函数模板的模板实参只能从转换的目标类型推导（[[temp.deduct.conv]]），没有显式指定的语法。

!!! std
    An expression designating a particular specialization of a conversion function template can only be formed with a *splice-expression*.

{{c++26}} 注的最后一句说，要写出一个指称转换函数模板某个特化的表达式，只能用静态反射的 *splice-expression*（[[expr.prim.splice]]），普通语法里没有对应的 *template-id* 写法。本机 Clang 23 还没有实现静态反射，这里不给例子。

!!! lawyer "转换函数模板与非模板转换函数并存"
    类中可以同时有 `operator int*()` 和 `template<class T> operator T*()`。转换到 `int*` 时两者的转换序列相同，非模板优先（[[over.match.best]]）。偏序比较两个转换函数模板时，比较的是返回类型（[[temp.deduct.partial#3.2]]）；两者返回类型不同时，约束不参与决胜（[[temp.func.order#8.3]]）。

## 思考题

!!! question "思考题"
    下面三个调用各选择哪个函数？

    ```cpp
    struct X {
        void g(long);
        template<class T> void g(T);
    };
    X x;
    x.g(1);       // (a)
    x.g(1L);      // (b)
    x.g<long>(1); // (c)
    ```

<details markdown="1">
<summary>答案</summary>

(a) 模板 `g<int>`。推导出 `T = int`，精确匹配；非模板 `g(long)` 要做 int 到 long 的整型转换。精确匹配更好，模板胜出。非模板优先只在两者的转换序列分不出高下时才起作用。

(b) 非模板 `g(long)`。两者都是精确匹配，非模板优先。

(c) 模板 `g<long>`。显式模板实参列表排除了非模板。
</details>
