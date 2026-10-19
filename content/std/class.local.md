---
title: 局部类声明
summary: 在函数体内定义的类能做什么、不能做什么：不能使用外层函数的局部变量（只读常量值除外），成员函数只能在类内定义，不能有静态数据成员和成员模板。
status: done
related: basic.def.odr, class.access, class.static.data, temp.mem, class.friend, expr.prim.lambda
tags: 类, 局部类, odr-use
updated: 2026-10-19
---

!!! tldr
    - 在函数体内定义的类叫局部类。它的名字只在所在的块里可见，但它的类型可以经 `auto` 返回或模板实参推导带到函数外面。
    - 局部类的成员函数不能使用外层函数的局部变量，只有读取常量的值、`sizeof` 这类不需要变量本身存储的用法例外。需要访问外层变量时改用 lambda。
    - 外层函数对局部类的私有成员没有特殊访问权；反过来，成员函数里的局部类拥有这个成员函数的全部访问权。
    - 局部类的成员函数只能在类内定义；局部类不能有静态数据成员，也不能有成员模板。

## 局部类看不到外层的局部变量（¶1）

¶1 在函数定义内声明的类称为**局部类**（local class）。下面是标准例 1 的改编，`f` 中的局部类 `local` 试图使用外层的各种名字：

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
        int g() { return x; }            // error: 外层的局部变量 x
        int h() { return s; }            // OK: s 是静态变量
        int k() { return ::x; }          // OK: 全局变量
        int l() { return q(); }          // OK: 函数
        int m() { return N; }            // OK: 只读常量 N 的值
        const int* n() { return &N; }    // error: 取 N 的地址
        int p() { return y; }            // error: 外层的结构化绑定
        int sz() { return sizeof(x); }   // OK: 不求值的操作数
    };
    (void)z;
}
```

原因在于 `local::g` 是一个独立的函数，它没有外层函数 `f` 的栈帧。调用 `g` 时，`f` 可能早已返回，也可能有好几次 `f` 的调用同时在进行，`g` 无从知道该用哪一个 `x`。所以凡是需要外层变量本身（它的存储或地址）的用法都被禁止。

用标准的术语说，这些用法是 [[g:odr-use]]：大致是需要一个变量真实存在于内存中的使用。注 1 指出，局部类中的声明不能 odr-use 外层作用域中的局部实体（局部变量、结构化绑定等）。精确规则在 [[basic.def.odr]] 的 [[g:odr-usable]] 定义里：局部实体只在它自己的作用域内可以 odr-use，中间如果隔着一个函数形参作用域（局部类的成员函数就引入了一个），就不行了。

不需要变量本身的用法不是 odr-use，所以是允许的。`m()` 和 `n()` 的对比最能说明问题：`N` 是用常量表达式初始化的 `const int`，读它的值时编译器直接代入常量 5，用不到 `N` 的存储；`&N` 则需要 `N` 的地址。`sizeof(x)` 的操作数不求值，同样用不到 `x`。

需要访问外层变量时，可以把值通过构造函数传进局部类，或者直接用 lambda。lambda 可以**捕获**外层变量，把它们复制或引用进闭包对象；局部类没有捕获机制。

### 名字不能出函数，类型可以

局部类的名字遵循普通的块作用域规则，在函数外面查找不到：

```cpp title="local-scope.cpp" error
void f() {
    struct local { int v; };
}
local* p = nullptr;   // error: 找不到 local
```

但类型本身可以离开函数。用 `auto` 作返回类型，或者让模板实参推导出它，局部类的对象就能在函数外使用。C++11 起局部类型可以作为模板实参，C++03 不允许，这让局部类和 lambda 可以直接用于标准容器和算法：

```cpp run title="local-escape.cpp" ok
#include <vector>

auto make() {
    struct Point { int x, y; };
    return Point{1, 2};            // 局部类型经推导的返回类型离开函数
}

int main() {
    auto p = make();               // p 的类型是 make 里的 Point
    std::vector<decltype(p)> v{p}; // 局部类型作为模板实参
    return v[0].x + v[0].y == 3 ? 0 : 1;
}
```

## 访问权（¶2 第一句）

¶2 外层函数对局部类的成员没有特殊访问权，按普通的访问规则处理（[[class.access]]）：

```cpp title="local-access.cpp" error
int f() {
    class L {
        int secret = 1;
    };
    L l;
    return l.secret;   // error: secret 是 L 的私有成员
}
```

反方向则不同。[[class.access.general#2]] 规定，成员函数中的局部类可以访问这个成员函数本身能访问的所有成员：

```cpp run title="local-in-member.cpp" ok
class Outer {
    int secret = 42;
public:
    int peek() {
        struct Helper {
            static int get(Outer& o) {
                return o.secret;   // OK: peek 能访问 secret
            }
        };
        return Helper::get(*this);
    }
};

int main() { Outer o; return o.peek() == 42 ? 0 : 1; }
```

## 成员只能在类内定义（¶2 第二句、¶3）

¶2 局部类的成员函数如果要定义，就必须在类定义内部定义。在类外定义要写 `local::g() { ... }`，而函数定义只能出现在命名空间或类作用域中，那里又看不到 `local` 这个名字，所以本来就写不出来。

出于同样的原因，[[class.friend#5]] 规定只有非局部类才能在友元声明里定义函数。在类内定义的友元函数属于外围命名空间，把它的定义放在一个函数体内部，无法安排。

¶3 嵌套在局部类中的类也是局部类。局部类 `X` 的成员只能在 `X` 的定义里声明，唯一的例外是嵌套类：它可以在 `X` 里先声明，再到 `X` 所在的那个块作用域里定义。

```cpp run title="local-nested.cpp" ok
int f() {
    struct X {
        struct Inner;                 // 只声明
        int use();                    // 无法在类外定义；不调用就不需要定义
    };
    struct X::Inner { int v = 7; };   // OK: 在 X 所在的块中定义
    return X::Inner{}.v;
}

int main() { return f() == 7 ? 0 : 1; }
```

## 不能有静态数据成员和成员模板（¶4）

¶4 注 2 指出局部类不能有静态数据成员，正式规则在 [[class.static.data#2]]。静态数据成员需要一个具有链接的定义，好让各个翻译单元引用同一个对象，而局部类没有链接，它的成员无从对应。`inline` 和 `constexpr` 的静态数据成员也一样被禁止。

另外，[[temp.mem#2]] 规定局部类不能有成员模板。闭包类型是例外：泛型 lambda 的 `operator()` 就是成员模板。

```cpp title="local-limits.cpp" error
void f() {
    struct L {
        static int count;                    // error: 静态数据成员
        static constexpr int k = 1;          // error: 同上
        template<class T> void g(T) {}       // error: 成员模板
        static int ok() { return 0; }        // OK: 静态成员函数
    };
}
```

静态成员函数、类型别名、嵌套类、虚函数、构造函数和析构函数都可以出现在局部类里。需要一个类内常量时，可以改用枚举或返回常量的静态成员函数。

## 局部类与 lambda

| 能力 | 局部类 | lambda 的闭包类型 |
|---|---|---|
| 使用外层局部变量 | 不能（常量值、不求值操作数除外） | 可以捕获 |
| 成员模板 | 不能 | 泛型 lambda 的调用运算符是模板 |
| 静态数据成员 | 不能 | 无法声明 |
| 多个成员函数、虚函数、基类 | 可以 | 只有一个调用运算符 |
| 作为模板实参 | C++11 起可以 | 可以 |

## 思考题

!!! question "思考题"
    下面的 `g` 合法吗？如果把函数体改成 `const int& r = n; return r;` 呢？

    ```cpp
    void f() {
        const int n = 3;
        struct L { int g() { int a[n]; return sizeof a; } };
    }
    ```

<details markdown="1">
<summary>答案</summary>

合法。`n` 是用常量表达式初始化的 `const int`，在数组边界里只用到它的常量值，不是 odr-use，所以即使 `n` 在 `L::g` 中不是 odr-usable 的也没有问题。

改成 `const int& r = n;` 就不合法了：引用要绑定到 `n` 这个对象本身，这是 odr-use，程序非良构。
</details>
