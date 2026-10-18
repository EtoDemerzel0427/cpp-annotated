---
title: 局部类声明
summary: 在函数体内定义的类：不能 odr-use 外层函数的自动变量；成员函数必须在类内定义；不能有静态数据成员与成员模板；嵌套类也是局部类
status: draft
related: basic.def.odr, class.access, class.static.data, temp.mem, expr.prim.lambda, dcl.fct.def
tags: 类, 局部类, odr-use
updated: 2026-10-17
---

**局部类**（local class）是在函数定义内部声明的类。它的名字只在所在块作用域中可见，因而天然是"实现细节"；lambda 的闭包类型在很多方面就是一种由编译器生成的局部类。本节规则不多，但每一条都源自同一个约束：**局部类的成员函数是独立的函数，它们没有外层函数的栈帧**。

## 定义与 odr-use 限制（¶1）

¶1 在函数定义内声明的类称为**局部类**。注 1 指出：局部类中的声明不能 **odr-use**（[[basic.def.odr]]）外层作用域中的**局部实体**。

为什么？局部类的成员函数 `local::g()` 被调用时，外层函数 `f` 的某次调用可能早已返回，也可能有多个并发的 `f` 调用——`g` 根本无法知道"哪个 `f` 的 `x`"。所以凡是需要外层自动变量**身份**（地址/存储）的使用都被禁止；而不需要身份的使用（读一个常量表达式的值、`sizeof`、未求值操作数）不构成 odr-use，就是允许的。

精确规则在 [[basic.def.odr]] 的 "odr-usable" 定义中：局部实体只在它所在的作用域内、且中间**没有**插入函数形参作用域（局部类的成员函数就引入了这样的作用域）时才是 odr-usable 的；对非 odr-usable 的局部实体做 odr-use 是 ill-formed。

```cpp title="local-odr-use.cpp" error
int x;
void f() {
    static int s;
    int x;
    const int N = 5;
    extern int q();
    int arr[2];
    auto [y, z] = arr;

    struct local {
        int g() { return x; }            // error: odr-use 了非 odr-usable 的局部变量 x
        int h() { return s; }            // OK: s 是静态存储期，不是局部实体
        int k() { return ::x; }          // OK: 全局变量
        int l() { return q(); }          // OK: 函数
        int m() { return N; }            // OK: N 是常量表达式，读它的值不是 odr-use
        const int* n() { return &N; }    // error: 取地址是 odr-use
        int p() { return y; }            // error: 结构化绑定 y 同样是局部实体
        int sz() { return sizeof(x); }   // OK: 未求值操作数，不是 odr-use
    };
    (void)z;
}
```

`m()` 与 `n()` 的对比是理解 odr-use 的经典例子：`N` 是用常量表达式初始化的 `const int`，对它做左值到右值转换可以直接用常量值替代，不需要 `N` 的存储；而 `&N` 需要它的地址。

对比 lambda：lambda 可以**捕获**外层自动变量，把它们复制或引用进闭包对象；局部类没有捕获机制。需要访问外层变量时，要么把它作为构造函数实参传入，要么改用 lambda。

### 名字的作用域

局部类的名字遵循普通的块作用域规则：在函数外部不可见。

```cpp title="local-scope.cpp" error
void f() {
    struct local { int v; };
}
local* p = nullptr;   // error: 找不到 local
```

但局部类型**可以逃逸**：通过 `auto` 返回类型、模板实参推导，局部类的对象可以出现在函数之外。C++11 起局部类型可以作为模板实参（C++03 禁止），这使得局部类和 lambda 能用于标准算法和容器。

```cpp run title="local-escape.cpp" ok
#include <vector>

auto make() {
    struct Point { int x, y; };
    return Point{1, 2};            // 局部类型通过推导出的返回类型逃逸
}

int main() {
    auto p = make();               // decltype(p) 是 make 中的局部类 Point
    std::vector<decltype(p)> v{p}; // 局部类型作为模板实参：C++11 起合法
    return v[0].x + v[0].y == 3 ? 0 : 1;
}
```

## 访问权与成员函数的定义（¶2）

¶2 第一句：外层函数对局部类的成员**没有特殊访问权**，遵循普通访问规则（[[class.access]]）。局部类并不是外层函数的"友元容器"：

```cpp title="local-access.cpp" error
int f() {
    class L {
        int secret = 1;
    };
    L l;
    return l.secret;   // error: secret 是 L 的 private 成员
}
```

反方向则不同：[[class.access#2|[class.access.general]/2]] 规定，**成员函数中的局部类**可以访问该成员函数本身能访问的所有成员——局部类继承了外层成员函数的访问权限。

```cpp run title="local-in-member.cpp" ok
class Outer {
    int secret = 42;
public:
    int peek() {
        struct Helper {
            static int get(Outer& o) { return o.secret; }   // OK: Outer::peek 能访问 secret
        };
        return Helper::get(*this);
    }
};

int main() { Outer o; return o.peek() == 42 ? 0 : 1; }
```

¶2 第二句：局部类的成员函数**如果要定义，就必须在类定义内部定义**。原因是语法上无法在类外定义：类外定义需要写 `local::g`，而函数定义只能出现在命名空间或类作用域中（[[dcl.fct.def]]），在命名空间作用域中 `local` 又不可见。

这也是 [[class.friend#5|[class.friend]/5]] 规定"只有非局部类才能在友元声明中定义函数"的原因之一：在局部类中定义的友元函数会成为一个命名空间作用域的函数，却定义在块作用域内部，这在语法和链接上都无从安排。

## 嵌套的局部类（¶3）

¶3：嵌套在局部类中的类也是局部类。局部类 `X` 的成员只能在 `X` 的定义中声明；但如果成员是**嵌套类**，可以在 `X` 的定义中先声明，然后在**离 `X` 最近的外围块作用域**中定义：

```cpp run title="local-nested.cpp" ok
int f() {
    struct X {
        struct Inner;                 // 只声明
        int use();                    // 成员函数：声明了但永远无法在类外定义（这里不调用它就不需要定义）
    };
    struct X::Inner { int v = 7; };   // OK: 在 X 所在的块作用域中定义嵌套类
    return X::Inner{}.v;
}

int main() { return f() == 7 ? 0 : 1; }
```

## 不能有静态数据成员与成员模板（¶4）

¶4（注 2）：局部类不能有静态数据成员。正式规则在 [[class.static.data#2]]：静态数据成员不能是无名类、局部类或它们（间接）嵌套类的直接成员。原因：静态数据成员需要命名空间作用域中的定义（或 `inline` 定义）并具有链接，而局部类没有链接，它的静态成员无法在多个 TU 之间对应，也无法在类外定义。

此外，[[temp.mem#2]] 规定非闭包类型的局部类**不能有成员模板**。（闭包类型例外：泛型 lambda 的 `operator()` 就是成员模板。）

```cpp title="local-limits.cpp" error
void f() {
    struct L {
        static int count;                    // error: 局部类不能有静态数据成员
        static constexpr int k = 1;          // error: 同上（inline 也不行）
        template<class T> void g(T) {}       // error: 局部类不能有成员模板
        static int ok() { return 0; }        // OK: 静态成员函数可以
    };
}
```

静态成员**函数**、`using` 类型别名、嵌套类、虚函数、构造/析构函数都可以出现在局部类中。

## 局部类与 lambda 的对比

| 能力 | 局部类 | lambda 闭包类型 |
|---|---|---|
| 访问外层自动变量 | 不能 odr-use | 可以捕获 |
| 成员模板 | 不能 | 泛型 lambda 的调用运算符是模板 |
| 静态数据成员 | 不能 | 不能（也无法声明） |
| 多个成员函数、虚函数、继承 | 可以 | 只有一个调用运算符；但可以继承多个 lambda 组成重载集 |
| 作为模板实参 | C++11 起可以 | 可以 |

## 陷阱

!!! pitfall
    1. **以为局部类能"看到"外层变量**：读常量表达式的值可以，其他用法（包括取地址、绑定引用、读非常量变量）都不行。
    2. **想在类外定义成员函数**：做不到，必须写在类内。
    3. **`static constexpr` 数据成员**：在普通类中很常见，在局部类中被禁止。可以改用静态成员函数或枚举。

## 思考题

!!! question "思考题"
    下面的 `g` 合法吗？

    ```cpp
    void f() {
        const int n = 3;
        struct L { int g() { int a[n]; return sizeof a; } };
    }
    ```

<details markdown="1">
<summary>答案</summary>

合法。`n` 是用常量表达式初始化的 `const int`，在数组边界中使用它是对其值的常量求值，不构成 odr-use；因此即使 `n` 在 `L::g` 中不是 odr-usable 的，这个用法也没问题。若改成 `const int& r = n;`（绑定引用需要 `n` 的身份），就是 odr-use，ill-formed。
</details>

## 小结

!!! summary
    - 局部类 = 函数体内定义的类，名字只在块作用域内可见，但类型可以经推导逃逸。
    - 不能 odr-use 外层自动变量和结构化绑定（常量值与未求值操作数可以）。
    - 外层函数对它没有特殊访问权；成员函数中的局部类继承该成员函数的访问权。
    - 成员函数只能在类内定义；嵌套类可以在最近外围块作用域中定义。
    - 没有静态数据成员，没有成员模板，不能在友元声明中定义函数。
