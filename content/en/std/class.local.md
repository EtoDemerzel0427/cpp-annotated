---
title: Local class declarations
summary: "What a class defined inside a function body can and can't do: it can't use the enclosing function's local variables (except to read constant values), its member functions can only be defined in the class, and it can't have static data members or member templates."
updated: 2026-10-19
---

!!! tldr
    - A class defined inside a function body is called a local class. Its name is visible only in its block, but its type can be carried out of the function through an `auto` return type or template argument deduction.
    - Member functions of a local class can't use the enclosing function's local variables, except for uses like reading a constant's value or `sizeof` that don't need the variable's storage. When you need access to enclosing variables, use a lambda instead.
    - The enclosing function has no special access to a local class's private members; conversely, a local class inside a member function has all the access that member function has.
    - Member functions of a local class can only be defined inside the class; a local class can't have static data members or member templates.

## A local class can't see enclosing local variables (¶1)

¶1 A class declared inside a function definition is called a **local class**. The following is adapted from Example 1 in the standard; the local class `local` in `f` tries to use various enclosing names:

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
        int g() { return x; }            // error: enclosing local variable x
        int h() { return s; }            // OK: s is a static variable
        int k() { return ::x; }          // OK: global variable
        int l() { return q(); }          // OK: function
        int m() { return N; }            // OK: only reads the value of the constant N
        const int* n() { return &N; }    // error: takes the address of N
        int p() { return y; }            // error: enclosing structured binding
        int sz() { return sizeof(x); }   // OK: unevaluated operand
    };
    (void)z;
}
```

The reason is that `local::g` is a separate function with no access to the stack frame of the enclosing function `f`. When `g` is called, `f` may have long since returned, or several calls to `f` may be in progress at once, and `g` has no way of knowing which `x` to use. So every use that needs the enclosing variable itself (its storage or address) is forbidden.

In the standard's terms, these uses are [[g:odr-use|odr-uses]]: roughly, uses that need a variable to actually exist in memory. Note 1 points out that a declaration in a local class can't odr-use a local entity (a local variable, structured binding and so on) from an enclosing scope. The precise rule is in [[basic.def.odr]], in the definition of [[g:odr-usable]]: a local entity is odr-usable only within its own scope, and not if a function parameter scope intervenes (a member function of a local class introduces one).

Uses that don't need the variable itself are not odr-uses, so they are allowed. The contrast between `m()` and `n()` shows this best: `N` is a `const int` initialized with a constant expression, so reading its value lets the compiler substitute the constant 5 without using `N`'s storage; `&N` needs `N`'s address. The operand of `sizeof(x)` is unevaluated, so it doesn't use `x` either.

When you need access to enclosing variables, pass the values into the local class through a constructor, or just use a lambda. A lambda can **capture** enclosing variables, copying them into or referring to them from the closure object; a local class has no capture mechanism.

### The name can't leave the function, but the type can

The name of a local class follows the ordinary block scope rules and can't be found outside the function:

```cpp title="local-scope.cpp" error
void f() {
    struct local { int v; };
}
local* p = nullptr;   // error: local not found
```

But the type itself can leave the function. With `auto` as the return type, or by having template argument deduction deduce it, objects of a local class can be used outside the function. Since C++11 local types can be template arguments (C++03 didn't allow it), which lets local classes and lambdas be used directly with standard containers and algorithms:

```cpp run title="local-escape.cpp" ok
#include <vector>

auto make() {
    struct Point { int x, y; };
    return Point{1, 2};            // the local type leaves the function via the deduced return type
}

int main() {
    auto p = make();               // p's type is the Point inside make
    std::vector<decltype(p)> v{p}; // a local type as a template argument
    return v[0].x + v[0].y == 3 ? 0 : 1;
}
```

## Access (¶2, first sentence)

¶2 The enclosing function has no special access to the members of a local class; ordinary access rules apply ([[class.access]]):

```cpp title="local-access.cpp" error
int f() {
    class L {
        int secret = 1;
    };
    L l;
    return l.secret;   // error: secret is a private member of L
}
```

The other direction is different. [[class.access.general#2]] says a local class in a member function can access every member that the member function itself can access:

```cpp run title="local-in-member.cpp" ok
class Outer {
    int secret = 42;
public:
    int peek() {
        struct Helper {
            static int get(Outer& o) {
                return o.secret;   // OK: peek can access secret
            }
        };
        return Helper::get(*this);
    }
};

int main() { Outer o; return o.peek() == 42 ? 0 : 1; }
```

## Members can only be defined in the class (¶2, second sentence; ¶3)

¶2 Member functions of a local class, if defined, must be defined inside the class definition. An out-of-class definition would have to be written `local::g() { ... }`, but function definitions can only appear at namespace or class scope, where the name `local` isn't visible, so it can't be written in the first place.

For the same reason, [[class.friend#5]] says only a non-local class can define a function in a friend declaration. A friend function defined in a class belongs to the enclosing namespace, and there is no way to arrange for its definition to sit inside a function body.

¶3 A class nested within a local class is also a local class. Members of a local class `X` can only be declared in the definition of `X`, with one exception, nested classes: one can be declared in `X` and then defined in the block scope that contains `X`.

```cpp run title="local-nested.cpp" ok
int f() {
    struct X {
        struct Inner;                 // declared only
        int use();                    // can't be defined outside the class; not needed unless called
    };
    struct X::Inner { int v = 7; };   // OK: defined in the block that contains X
    return X::Inner{}.v;
}

int main() { return f() == 7 ? 0 : 1; }
```

## No static data members or member templates (¶4)

¶4 Note 2 points out that a local class can't have static data members; the formal rule is in [[class.static.data#2]]. A static data member needs a definition with linkage so that every translation unit refers to the same object, but a local class has no linkage, so its members couldn't be matched up. `inline` and `constexpr` static data members are forbidden as well.

In addition, [[temp.mem#2]] says a local class can't have member templates. Closure types are the exception: the `operator()` of a generic lambda is a member template.

```cpp title="local-limits.cpp" error
void f() {
    struct L {
        static int count;                    // error: static data member
        static constexpr int k = 1;          // error: likewise
        template<class T> void g(T) {}       // error: member template
        static int ok() { return 0; }        // OK: static member function
    };
}
```

Static member functions, type aliases, nested classes, virtual functions, constructors and destructors can all appear in a local class. When you need an in-class constant, use an enumeration or a static member function that returns the constant.

## Local classes and lambdas

| Capability | Local class | Lambda closure type |
|---|---|---|
| Use enclosing local variables | No (except constant values and unevaluated operands) | Can capture them |
| Member templates | No | A generic lambda's call operator is a template |
| Static data members | No | Can't be declared |
| Several member functions, virtual functions, base classes | Yes | Only one call operator |
| As a template argument | Yes, since C++11 | Yes |

## Questions

!!! question "Question"
    Is `g` below valid? What if its body is changed to `const int& r = n; return r;`?

    ```cpp
    void f() {
        const int n = 3;
        struct L { int g() { int a[n]; return sizeof a; } };
    }
    ```

<details markdown="1">
<summary>Answer</summary>

Valid. `n` is a `const int` initialized with a constant expression, and the array bound uses only its constant value, which is not an odr-use, so it doesn't matter that `n` isn't odr-usable in `L::g`.

With `const int& r = n;` it is no longer valid: the reference must bind to the object `n` itself, which is an odr-use, so the program is ill-formed.
</details>
