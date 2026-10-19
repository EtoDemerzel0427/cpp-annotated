---
title: 宏替换
summary: 对象式宏与函数式宏怎样定义和调用；实参怎样划分、为什么先展开再代入；__VA_ARGS__ 与 __VA_OPT__；# 字符串化与 ## 拼接的精确规则；宏的重定义、禁用名字与作用域。重新扫描的规则见 cpp.rescan。
status: done
covers: cpp.replace.general, cpp.subst, cpp.stringize, cpp.concat, cpp.scope
papers: N1653, P0306R4, P1042R1
related: cpp.rescan, cpp.pre, cpp.cond, cpp.import, cpp.predefined, lex.pptoken, lex.phases
tags: 预处理, 宏, 可变参数宏
updated: 2026-10-19
---

!!! tldr
    - 宏替换只在预处理记号的层面工作，不认识作用域、类型和表达式；函数式宏只有在名字后面紧跟 `(` 时才展开。
    - 实参之间用逗号分隔，只有圆括号能保护逗号，`std::map<int, int>` 会被拆成两个实参；空实参也算一个实参。
    - 普通形参代入的是完全展开后的实参，`#` 和 `##` 的操作数用的是原样的实参。这就是 `xstr(x) str(x)` 两层宏的原理。
    - `__VA_OPT__(x)` 只在可变实参展开后非空时才产生 `x`，用来解决多余的逗号。
    - `#` 和 `##` 拼出无效的结果时，程序非良构；宏定义无视块结构，一直有效到 `#undef` 或翻译单元结束。

宏替换在翻译阶段 4 进行（[[lex.phases]]）。它操作的是预处理记号（[[g:preprocessing-token]]，见 [[lex.pptoken]]），而不是字符，也不是 C++ 的表达式：预处理器不知道什么是类型、作用域或优先级，只是按规则把一串记号换成另一串记号。

一次函数式宏调用要经过下面几步，本页依次讲解前四步：

1. 识别调用，划分实参；
2. 实参替换：普通形参换成完全展开后的实参，`#` 和 `##` 的操作数换成原样的实参；
3. 执行 `#`（字符串化）和 `##`（拼接）；
4. 删除拼接过程中产生的占位记号；
5. 把结果连同后面的源码重新扫描，寻找更多的宏，但不再展开正在展开的宏，详见 [[cpp.rescan]]。

## 对象式宏与函数式宏（¶8、¶11–¶13）

```cpp
#define TABSIZE 100
int table[TABSIZE];              // 对象式宏：int table[100];

#define max(a, b) ((a) > (b) ? (a) : (b))
int m = max(1, 2);               // 函数式宏：((1) > (2) ? (1) : (2))
```

¶8 紧跟 `define` 的标识符称为**宏名**（[[g:macro-name|macro name]]）。宏名只有一个名字空间，没有作用域，也没有重载：对象式宏 `X` 和函数式宏 `X` 不能同时存在。替换列表首尾的空白不属于替换列表。

¶11 `#define 标识符 替换列表` 定义一个**对象式宏**（[[g:object-like-macro|object-like macro]]）：此后每次出现这个宏名，都被替换为替换列表，然后重新扫描。¶12 的例 2 就是上面的 `TABSIZE`。

脚注 117 提醒，到宏替换的时候，字符字面量和字符串字面量已经是完整的预处理记号，所以不会在它们内部寻找宏名或形参：

```cpp run title="no-expand-in-literal.cpp" ok
#define N 10
const char* s = "N";      // 仍是 "N"，不是 "10"
int main() { return s[0] == 'N' ? 0 : 1; }
```

¶13 宏名后面紧跟 `(`（中间没有空白）时，定义的是**函数式宏**（[[g:function-like-macro|function-like macro]]），形参写在括号里，可以是一个标识符列表、`...`，或标识符列表加 `...`。此后宏名后面的下一个预处理记号是 `(` 时，就开始一次调用，调用到与之配对的 `)` 为止，中间成对的括号被跳过。调用内部的换行算作普通空白，所以一次调用可以跨很多行。

下一个记号是不是 `(` 决定了函数式宏是否展开：

```cpp
#define min(a, b) ((a) < (b) ? (a) : (b))
int x = min(1, 2);          // 展开
int y = (std::min)(1, 2);   // 不展开：min 后面是 )，不是 (
auto f = min;               // 不展开：单独出现的函数式宏名就是普通标识符
```

`(std::min)(a, b)` 是对付 `<windows.h>` 中 `min`、`max` 宏的常用写法，原理就在这里。

¶15 的例 3 用 `max` 说明了函数式宏的缺点：它会把某个实参求值两次（连同副作用），多次调用时生成的代码比函数多，而且宏没有地址。括号保证实参和结果表达式的结合正确。

```cpp run title="max-double-eval.cpp" ok
#define max(a, b) ((a) > (b) ? (a) : (b))
int main() {
  int i = 1, j = 0;
  int m = max(i++, j);   // i++ 被求值两次：比较一次，作为结果再一次
  return (m == 2 && i == 3) ? 0 : 1;
}
```

## 实参的划分（¶5、¶14、¶16）

```cpp
#define TWO(x, y) [x|y]
TWO({1,2})                   // [{1|2}]                  花括号不保护逗号
TWO(std::map<int,int>)       // [std::map<int|int>]      尖括号不保护逗号
TWO((std::map<int,int>), z)  // [(std::map<int,int>)|z]  圆括号保护逗号
```

¶14 最外层一对括号之间的记号构成实参列表，实参之间用逗号分隔，但内层成对圆括号中的逗号不分隔实参。只有圆括号有这个作用，预处理器不知道 `<` 是模板实参列表的开始。

在宏里使用模板类型时，常见的对策是外加一层圆括号（如果语境允许）、先用 `using` 起一个别名，或者把宏改成可变参数宏 `#define ONE(...) [__VA_ARGS__]`。

¶5 如果形参列表不以 `...` 结尾，实参个数必须等于形参个数，由零个记号构成的空实参也算一个。如果以 `...` 结尾，实参个数至少要等于 `...` 之前的形参个数。调用必须有结束它的 `)`。

| 宏 | 调用 | 实参个数 | 合法吗 |
|---|---|---|---|
| `#define F0() x` | `F0()` | 0 | 是 |
| `#define F1(a) [a]` | `F1()` | 1（一个空实参） | 是，展开为 `[]` |
| `#define F2(a,b) [a b]` | `F2(,)` | 2（两个空实参） | 是 |
| `#define F2(a,b) [a b]` | `F2()` | 1 | 否 |
| `#define V(a, ...) a` | `V(1)` | 1 | 是（C++20 起） |

C++17 及以前要求可变参数宏的实参个数多于 `...` 之前的形参个数，`V(1)` 必须写成 `V(1,)`；C++20 起放宽为至少相等。Clang 在 `-std=c++17 -pedantic` 下对 `V(1)` 给出 C++20 extension 警告。

¶16 如果形参列表以 `...` 结尾，多出来的实参连同它们之间的逗号合并成一项，称为**可变实参**（[[g:variable-arguments|variable arguments]]）。`#define V(a, ...)` 调用 `V(1, 2, 3)` 时，`a` 是 `1`，可变实参是 `2, 3`，逗号也包括在内。

¶14 的第二句规定，如果实参列表中有本来会成为预处理指令的记号序列，程序非良构。脚注 118 补充，有条件支持的指令也算。

```cpp title="directive-in-args.cpp" error
#define M(a) a
int x = M(1
#ifdef BIG
  + 1000
#endif
);
```

C++23 及以前这是 UB。Clang 和 GCC 都会实际执行这里的 `#ifdef`，Clang 给出 `-Wembedded-directive` 警告，措辞仍说是 undefined behavior。

## 实参先展开，再代入（[cpp.subst] 第 1 段）

```cpp run title="two-level.cpp" ok
#define str(x)  #x
#define xstr(x) str(x)
#define N 42
static_assert(__builtin_strlen(str(N)) == 1);    // "N"：# 的操作数不展开
static_assert(__builtin_strlen(xstr(N)) == 2);   // "42"：xstr 的 x 先展开为 42，
                                                 // 再交给 str
int main() {}
```

[[cpp.subst]] 第 1 段：确定实参之后进行实参替换。替换列表中的形参如果前面没有 `#` 或 `##`、后面也没有 `##`，就被替换成对应实参完全宏展开之后的记号。`#` 和 `##` 的操作数则按各自的规则处理，用的是原样的实参（见下文）。

`str(N)` 中，`x` 是 `#` 的操作数，拿到的是原样的 `N`，得到 `"N"`。`xstr(N)` 中，`x` 不是 `#` 的操作数，先展开成 `42` 再代入，于是 `str(42)` 得到 `"42"`。想对宏的值做字符串化或拼接时，都要像这样多套一层。

实参展开时，如同它就是翻译单元剩下的全部内容，后面再没有别的记号。也就是说，实参末尾的函数式宏名不能从实参外面借一个 `(` 来完成调用。第 1 段的例 1：

```cpp
#define LPAREN() (
#define G(Q) 42
#define F(R, X, ...)  __VA_OPT__(G R X) )
int x = F(LPAREN(), 0, <:-);    // 替换为 int x = 42;
```

实参 `R` 是 `LPAREN()`，完全展开为 `(`；`X` 是 `0`；可变实参是 `<:-`，非空。`__VA_OPT__(G R X)` 代入后得到 `G ( 0`，连同替换列表末尾的 `)` 一起重新扫描，才形成调用 `G(0)`，结果是 `42`。`G` 和 `(` 是在重新扫描时相遇的，不是在展开实参时。

## 可变参数：__VA_ARGS__ 与 __VA_OPT__（¶6、[cpp.subst] 第 2–4 段）

[[cpp.subst]] 第 2 段：替换列表中的 `__VA_ARGS__` 当作一个形参，用可变实参替换。第 3 段的例 2：

```cpp
#define debug(...) fprintf(stderr, __VA_ARGS__)
#define showlist(...) puts(#__VA_ARGS__)
#define report(test, ...) ((test) ? puts(#test) : printf(__VA_ARGS__))
debug("Flag");                              // fprintf(stderr, "Flag");
debug("X = %d\n", x);                       // fprintf(stderr, "X = %d\n", x);
showlist(The first, second, and third items.);
                                            // puts("The first, second, and third items.");
report(x>y, "x is %d but y is %d", x, y);   // ((x>y) ? puts("x>y") : printf("x is %d but y is %d", x, y));
```

`showlist` 说明 `#__VA_ARGS__` 会把可变实参中的逗号也字符串化。

¶6 `__VA_ARGS__` 和 `__VA_OPT__` 只能出现在使用了 `...` 的函数式宏的替换列表中。Clang 对出现在别处的 `__VA_ARGS__` 只在 `-pedantic` 下给出警告。

### __VA_OPT__ 解决多余的逗号

C++20 之前，可变参数宏有一个老问题：

```cpp
#define LOG(fmt, ...) printf(fmt, __VA_ARGS__)
LOG("hi");          // printf("hi", )：多余的逗号，语法错误
```

GCC 的扩展 `, ## __VA_ARGS__` 在可变实参为空时吞掉前面的逗号，流行了很多年，但它不是标准，语义也古怪。C++20 的 `__VA_OPT__`（[[P0306R4]]，[[P1042R1]] 修订了措辞）给出了标准的写法：

```cpp
#define LOG(fmt, ...) printf(fmt __VA_OPT__(,) __VA_ARGS__)
LOG("hi");          // printf("hi" )
LOG("%d", 1);       // printf("%d" , 1)
```

[[cpp.subst]] 第 4 段的规则：

1. `__VA_OPT__` 只能以 `__VA_OPT__( 记号 )` 的形式出现，括号中不能再有 `__VA_OPT__`。
2. 如果括号中的记号作为这个宏的替换列表是非良构的（例如以 `##` 开头），程序非良构。
3. `__VA_OPT__(...)` 整体当作一个形参处理。如果 `__VA_ARGS__` 替换之后没有任何记号，它对应的实参是一个占位记号（placemarker，见 `##` 一节），也就是什么也不产生；否则，它对应的实参是括号内的记号按替换列表展开的结果（做实参替换、`#` 和 `##`），这时还没有删除占位记号，也还没有重新扫描。

判断的是 `__VA_ARGS__` 替换之后是否为空，而 `__VA_ARGS__` 替换时可变实参已经完全展开。所以展开为空的宏也算空：

```cpp
#define F(...)           f(0 __VA_OPT__(,) __VA_ARGS__)
#define G(X, ...)        f(0, X __VA_OPT__(,) __VA_ARGS__)
#define SDEF(sname, ...) S sname __VA_OPT__(= { __VA_ARGS__ })
#define EMP

F(a, b, c)          // f(0, a, b, c)
F()                 // f(0)
F(EMP)              // f(0)：EMP 展开为空
G(a, b, c)          // f(0, a, b, c)
G(a, )              // f(0, a)：可变实参是一个空实参
G(a)                // f(0, a)：没有可变实参（C++20 起合法）
SDEF(foo);          // S foo;
SDEF(bar, 1, 2);    // S bar = { 1, 2 };
```

这是第 4 段的例 3 的前半部分。`SDEF` 说明 `__VA_OPT__` 不只用于逗号，任何只在有可变实参时才需要的记号都可以放进去。例 3 的后半部分涉及 `__VA_OPT__` 与 `#`、`##` 的配合，放在讲完这两个运算符之后。

## # 运算符：字符串化（[cpp.stringize]）

```cpp
#define str(x) #x
str(  a   +    b  )        // "a + b"：空白规范化
str(a "\n" b)              // "a \"\\n\" b"：字面量中的 " 和 \ 被转义
str('"')                   // "'\"'"
str()                      // ""
str(R"(line1
line2)")                   // "R\"(line1\nline2)\""：真实的换行变成 \n
```

[[cpp.stringize]] 第 1 段：函数式宏替换列表中的每个 `#` 后面都必须紧跟一个形参。对象式宏中的 `#` 只是普通记号，不受这个限制。

```cpp
#define S(a) #b     // error: # 后面不是形参
#define HASH #      // OK：对象式宏，# 只是普通记号
```

第 2 段：形参紧跟在 `#` 之后时，二者被替换为一个不带前缀的字符串字面量（标准称之为 [[g:character-string-literal|character string literal]]），内容是对应实参（去掉占位记号）的拼写。具体规则是：

- 实参记号之间的每一处空白都变成一个空格，首尾的空白删除；
- 每个记号保持原来的拼写，只有在头文件名、字符字面量和字符串字面量内部（包括两端的 `"`），每个 `"` 和 `\` 前面插入一个 `\`，每个换行字符换成 `\n` 两个字符；
- 空实参得到 `""`；
- 结果不是合法的字符串字面量时，程序非良构；
- `#` 和 `##` 的求值顺序未指定。

换行替换为 `\n` 这条规则是为原始字符串字面量准备的：原始字符串字面量里可以有真实的换行，普通字符串字面量不行，所以要改写。

!!! lawyer "转义只发生在字面量内部"
    字面量之外的 `\` 是一个单独的预处理记号，不会被转义。所以 `str(\)` 得到 `"\"`，这不是合法的字符串字面量，程序非良构。Clang 23 只给出 invalid string literal, ignoring final '\' 警告，结果是 `""`。

!!! lawyer "空白的多少不影响结果"
    阶段 3 中连续的非换行空白是保留还是压缩成一个空格，是未指定的（[[lex.phases]]）。但这对字符串化没有影响，因为每一处空白都变成一个空格，只有有没有空白才影响结果，而这在阶段 3 就确定了。所以 `str(a+b)` 一定是 `"a+b"`，`str(a + b)` 一定是 `"a + b"`。

## ## 运算符：记号拼接（[cpp.concat]）

```cpp
#define CAT(a, b) a ## b
CAT(x, 1)        // x1
CAT(+, =)        // +=
CAT(/, /)        // error: // 不是预处理记号，注释在阶段 3 就处理完了
CAT(+, -)        // error: +- 不是一个预处理记号
CAT(., .)        // error: .. 不是预处理记号（... 才是）
```

[[cpp.concat]] 第 1 段：`##` 不能出现在替换列表的开头或结尾，它需要左右两个操作数。

第 2 段：函数式宏中，紧挨着 `##`（在前或在后）的形参被替换为对应实参原样的记号，不展开。如果实参是空的，就换成一个**占位记号**（[[g:placemarker|placemarker]]）。脚注 119 说明，占位记号不出现在文法中，只是阶段 4 内部的临时实体。

第 3 段：在重新扫描之前，替换列表中每个不是来自实参的 `##` 被删除，它前后的两个记号拼接成一个记号。占位记号与占位记号拼接得到占位记号，占位记号与其他记号拼接得到那个记号。拼接的结果不是合法的预处理记号时，程序非良构；C++23 及以前这是 UB。拼出的记号可以参与后续的宏替换。注 1 指出，拼接可以形成通用字符名。Clang 对上面三个错误都报 pasting formed '...', an invalid preprocessing token。

不是来自实参这个限定意味着，写在实参里的 `##` 只是普通记号：

```cpp
#define F(x) [x]
F(a ## b)        // [a ## b]：## 来自实参，不是 F 的替换列表中的运算符
```

!!! lawyer "拼接顺序未指定，何时有影响"
    `a ## b ## c` 的拼接顺序是未指定的。通常结果相同，但中间结果不是合法记号时就不同了：
    ```cpp
    #define cat3(a, b, c) a ## b ## c
    cat3(-, >, *)   // 从左到右：-> 再 ->*，合法；从右到左：>* 不是记号，非良构
    ```
    Clang 23 从左到右处理，得到 `->*`。可移植的代码应保证任何顺序下的中间结果都合法。

### 两层宏的完整例子

[[cpp.concat]] 第 4 段的例 1 综合了 `#`、`##` 和实参展开：

```cpp
#define str(s)      # s
#define xstr(s)     str(s)
#define debug(s, t) printf("x" # s "= %d, x" # t "= %s", \
               x ## s, x ## t)
#define INCFILE(n)  vers ## n
#define glue(a, b)  a ## b
#define xglue(a, b) glue(a, b)
#define HIGHLOW     "hello"
#define LOW         LOW ", world"

debug(1, 2);
fputs(str(strncmp("abc\0d", "abc", '\4')        // this goes away
    == 0) str(: @\n), s);
#include xstr(INCFILE(2).h)
glue(HIGH, LOW);
xglue(HIGH, LOW)
```

结果是：

```cpp
printf("x" "1" "= %d, x" "2" "= %s", x1, x2);
fputs("strncmp(\"abc\\0d\", \"abc\", '\\4') == 0" ": @\n", s);
#include "vers2.h"      // 宏替换之后、访问文件之前
"hello";
"hello" ", world"
```

逐行来看：

- `debug(1, 2)`：`# s` 得到 `"1"`，`x ## s` 得到 `x1`。阶段 6 再把相邻的字符串字面量拼接成 `"x1= %d, x2= %s"`。
- `fputs(...)`：实参跨了行，行尾注释在阶段 3 已经变成空格，所以 this goes away。字符串化时 `"abc\0d"` 中的 `"` 和 `\` 被转义。`str(: @\n)` 中的 `@`、`\`、`n` 不在字面量内部，原样保留，得到 `": @\n"`，到阶段 7 它恰好是一个含换行转义的合法字符串。
- `#include xstr(INCFILE(2).h)`：`xstr` 的实参先完全展开，`INCFILE(2)` 变成 `vers2`，得到 `vers2.h`，再由 `str` 字符串化为 `"vers2.h"`。这是 [[cpp.include]] 宏形式的典型用法。
- `glue(HIGH, LOW)`：`a`、`b` 紧挨着 `##`，不展开，直接拼成 `HIGHLOW`；重新扫描时 `HIGHLOW` 是宏，得到 `"hello"`。
- `xglue(HIGH, LOW)`：`xglue` 的形参不挨着 `##`，实参先展开。`HIGH` 不是宏；`LOW` 展开为 `LOW ", world"`，其中的 `LOW` 在它自己的展开中不再展开（[[cpp.rescan]]）。于是 `glue(HIGH, LOW ", world")` 得到 `HIGHLOW ", world"`，再得到 `"hello" ", world"`。

例子末尾说明，宏定义中 `#` 和 `##` 周围的空白可有可无，`# s` 与 `#s`、`a ## b` 与 `a##b` 等价。

### 拼出来的 ## 不是运算符

第 5 段的例 2：

```cpp
#define hash_hash # ## #
#define mkstr(a) # a
#define in_between(a) mkstr(a)
#define join(c, d) in_between(c hash_hash d)
char p[] = join(x, y);          // 等价于 char p[] = "x ## y";
```

展开过程是 `join(x, y)`，`in_between(x hash_hash y)`，`in_between(x ## y)`，`mkstr(x ## y)`，最后是 `"x ## y"`。`hash_hash` 的替换列表 `# ## #` 中间的 `##` 是运算符，把两个 `#` 拼成一个 `##` 记号。但这个新记号不是 `##` 运算符，因为第 3 段只处理替换列表中原有的 `##`。它作为实参的一部分传下去，最后被原样字符串化。

### 占位记号

第 6 段的例 3：

```cpp
#define t(x,y,z) x ## y ## z
int j[] = { t(1,2,3), t(,4,5), t(6,,7), t(8,9,),
  t(10,,), t(,11,), t(,,12), t(,,) };
// 结果：int j[] = { 123, 45, 67, 89, 10, 11, 12, };
```

`t(6,,7)` 中，空实参 `y` 变成占位记号，`6 ## 占位 ## 7` 得到 `67`。`t(,,)` 的三个空实参都变成占位记号，拼接后仍是占位记号，最后被删除，什么也不剩，所以初始化器以 `12, ` 结尾，留下一个合法的尾逗号。占位记号让每个 `##` 都有两个操作数，不必单独讨论和空的东西拼接是什么意思。

### __VA_OPT__ 与 # 和 ## 的配合

回到 [[cpp.subst]] 第 4 段例 3 的后半部分：

```cpp
#define H1(X, ...) X __VA_OPT__(##) __VA_ARGS__   // error: ## 不能出现在替换列表开头
#define H2(X, Y, ...) __VA_OPT__(X ## Y,) __VA_ARGS__
H2(a, b, c, d)      // ab, c, d
#define H3(X, ...) #__VA_OPT__(X##X X##X)
H3(, 0)             // ""
#define H4(X, ...) __VA_OPT__(a X ## X) ## b
H4(, 1)             // a b
#define H5A(...) __VA_OPT__()/**/__VA_OPT__()
#define H5B(X) a ## X ## b
#define H5C(X) H5B(X)
H5C(H5A())          // ab
```

- `H1`：`__VA_OPT__` 括号里的 `##` 当作替换列表时位于开头，违反 [[cpp.concat]] 第 1 段，非良构。
- `H2`：`##` 在 `__VA_OPT__` 内部照常生效，拼出 `ab`。
- `H3`：`#` 可以作用于 `__VA_OPT__`，因为它被当作形参。可变实参 `0` 非空，括号内容被展开：`X` 是空实参，挨着 `##` 变成占位记号，两次拼接都得到占位记号。占位记号在字符串化之前删除，空序列字符串化得到 `""`。
- `H4`：`__VA_OPT__(...)` 整体是 `##` 的左操作数。它对应的实参是 `a X ## X` 展开的结果 `a 占位`，此时占位记号还没有删除。然后 `占位 ## b` 得到 `b`，结果是 `a b` 而不是 `ab`，因为与 `b` 拼接的是占位记号，不是 `a`。
- `H5`：`H5A()` 的可变实参为空，两个 `__VA_OPT__` 都只产生占位记号，最后被删除，`H5A()` 展开为空。于是 `H5B` 收到一个空实参，`a ## 占位 ## b` 得到 `ab`。

!!! impl "实测"
    本页 `F`、`G`、`SDEF`、`H2` 到 `H5`、`LPAREN` 以及 [[cpp.concat]] 的三个标准例子，Clang 23 `-E` 的输出都与标准一致（空白除外）。

## 定义宏的限制（¶1–¶4、¶7、¶9、¶10）

### 重定义必须完全相同（¶1–¶3）

<div class="compare" markdown="1">

```cpp run ok
#define OBJ_LIKE (1-1)
#define OBJ_LIKE /* 空白 */ (1-1) /* 其他 */
#define FUNC_LIKE(a)   ( a )
#define FUNC_LIKE( a )(  \
            a /* 跨行
              */ )
int main() {}
```

```cpp error
#define OBJ_LIKE (1-1)
#define OBJ_LIKE (0)       // 记号不同
#define OBJ_LIKE (1 - 1)   // 空白不同
#define FUNC_LIKE(a) ( a )
#define FUNC_LIKE(b) ( a ) // 形参用法不同
#define FUNC_LIKE(b) ( b ) // 形参拼写不同
```

</div>

这是 ¶3 的例 1。¶1 两个替换列表**相同**，当且仅当其中的预处理记号在个数、顺序、拼写和空白分隔上都相同，所有的空白分隔都视为相同。也就是说，两个记号之间有没有空白必须一致，有多少空白、是什么空白不要紧。注释在阶段 3 已经变成空格，所以左边的写法都相同。

¶2 已定义为对象式宏的标识符，只能被替换列表相同的对象式宏重定义；函数式宏还要求形参的个数和拼写都相同。否则程序非良构。

要求逐记号相同而不是语义等价，是因为同一个宏常常在几个头文件中重复定义，例如 C 的 `NULL` 在好几个标准头文件里都有定义。逐记号比较既允许这种无害的重复，又能简单地发现真正的冲突。

!!! note "Clang 只给警告"
    Clang 对不兼容的重定义只给 `-Wmacro-redefined` 警告，然后采用新定义。警告就是标准意义上的诊断，所以这是符合标准的。但不少项目因此在不知不觉中依赖了后定义覆盖前定义，可移植的做法是先 `#undef`。

### 其他形式要求（¶4、¶7、¶10）

¶4 对象式宏的宏名和替换列表之间必须有空白。`#define NOSPACE+1` 违反了这一条，Clang 给出 ISO C99 requires whitespace after the macro name 警告。

¶7 函数式宏的形参不能重名，`#define G(x, x) x` 非良构，Clang 报 duplicate macro parameter name。

¶10 在可以开始预处理指令的位置，`#` 后面的标识符不做宏替换。所以 `#define include xxx` 之后，`#include` 仍然是 `#include`。

### 不能定义为宏的名字（¶9）

¶9 翻译单元不得 `#define` 或 `#undef` 与下列名字拼写相同的宏名：

- 关键字（[[lex.key]]）；
- 表 4 中有特殊含义的标识符：`final`、`import`、`module`、`override`、`post`、`pre`（[[lex.name]]）；
- [[dcl.attr]] 中描述的属性名，如 `noreturn`、`nodiscard`、`deprecated`、`fallthrough`、`assume`。

例外是 `likely` 和 `unlikely`，它们可以定义为函数式宏，也可以 `#undef`。

```cpp title="reserved-macro-names.cpp" error
#define new  my_new      // error: 关键字
#define override         // error: 表 4
#define pre  1           // error: 表 4（C++26 契约中的 pre）
#define noreturn         // error: 属性名
#define likely(x) __builtin_expect(!!(x), 1)   // OK：likely 可以是函数式宏
#define unlikely 0       // error: unlikely 只能定义为函数式宏
```

这个例外是向现实妥协：Linux 内核等大量 C 代码早就定义了 `likely(x)` 和 `unlikely(x)` 宏。函数式宏只在后面紧跟 `(` 时才展开，而 `[[likely]]` 中 `likely` 后面是 `]`，二者互不干扰；对象式的 `#define likely` 则会破坏 `[[likely]]`。

注 1 指出，`and`、`bitor` 这类替代记号（[[lex.digraph]]）不是标识符，所以根本无法定义名为 `and` 的宏。

!!! impl "实现现状"
    Clang 23 对 `#define new ...` 和 `#define override` 给出 `-Wkeyword-macro` 警告；对 `#define noreturn`、`#define pre 1`、`#define unlikely 0` 不给任何诊断。所以在 Clang 上，这条规则只有一部分被检查。

另外两处有类似的限制：包含了标准库头文件的翻译单元，不得 `#define` 或 `#undef` 任何标准库头文件中声明的名字，例如不能 `#define move ...`（[[macro.names]]）；预定义宏名和 `defined` 也不得 `#define` 或 `#undef`（[[cpp.predefined#4]]）。

## 宏的作用域（[cpp.scope]）

```cpp run title="macro-scope.cpp" ok
void f() {
#define LOCAL 1          // 并不是局部的
}
namespace n {
  int g() { return LOCAL; }   // 照样可见：宏无视作用域和命名空间
}
#undef LOCAL
#undef NEVER_DEFINED     // OK：被忽略
int main() { return n::g() - 1; }
```

[[cpp.scope]] 第 1 段：宏定义从定义处开始一直有效，与块结构无关，直到遇到对应的 `#undef`，没有的话直到翻译单元结束。阶段 4 之后宏定义不再有任何意义。

第 2 段：`#undef 标识符` 使这个标识符不再是宏名。如果它本来就不是宏名，这条指令被忽略，不是错误。

阶段 4 之后宏不复存在，这意味着调试器看不到宏（除非编译器另外记录，如 GCC 和 Clang 的 `-g3`），命名模块不导出宏（[[cpp.import]]），宏也不参与链接。两个翻译单元可以给同一个宏名完全不同的定义。但如果宏影响了某个 `inline` 函数或类定义展开后的记号，两个翻译单元中这个定义的记号不同，就违反了 ODR（[[basic.def.odr]]），程序非良构且不要求诊断。

!!! tip "push_macro 和 pop_macro"
    标准没有提供临时改写一个宏、之后再恢复原定义的机制。GCC、Clang 和 MSVC 都支持 `#pragma push_macro("X")` 和 `#pragma pop_macro("X")`，它们是实现定义的 pragma（[[cpp.pragma]]）。

## 常见陷阱

!!! pitfall "多语句宏"
    ```cpp
    #define SWAP(a, b) tmp = a; a = b; b = tmp
    if (x > y) SWAP(x, y);    // 只有第一条语句受 if 控制
    ```
    惯用写法是 `#define SWAP(a, b) do { auto t = a; a = b; b = t; } while (0)`。它是一条语句，而且要求调用处加分号，用起来和函数调用一样。

!!! pitfall "形参周围不加括号"
    ```cpp
    #define SQ(x) x * x
    SQ(1 + 2)     // 1 + 2 * 1 + 2，结果是 5
    ```
    宏只替换记号，不管优先级。替换列表中的每个形参和整个替换列表都应当加括号。

!!! pitfall "实参中的模板逗号"
    `ASSERT(std::is_same_v<A, B>)` 会被分成两个实参。加一层圆括号：`ASSERT((std::is_same_v<A, B>))`。

## 历史与演进

!!! history
    - C++98 的宏与 C89 一致：对象式宏、函数式宏、`#` 和 `##`。空实参在那时是 UB。
    - C++11 与 C99 同步（[[N1653]]），加入可变参数宏和 `__VA_ARGS__`，允许空实参，引入占位记号的规则。
    - C++20 加入 `__VA_OPT__`（[[P0306R4]]，[[P1042R1]] 修订了措辞），并允许可变参数宏省略全部可变实参。
    - C++23 之后的新措辞把多处 UB 改为非良构：`##` 拼出无效记号、实参中出现指令、字符串化的结果不是合法的字符串字面量等。

## 思考题

!!! question "思考题 1"
    下面各调用分别展开为什么？
    ```cpp
    #define F(x, ...) f(x __VA_OPT__(,) __VA_ARGS__)
    #define E
    F(1)
    F(1,)
    F(1, E)
    F(1, E E, )
    F(, 2)
    ```

<details markdown="1">
<summary>答案</summary>

- `F(1)` 得到 `f(1 )`：没有可变实参，C++20 起合法。
- `F(1,)` 得到 `f(1 )`：可变实参是一个空实参。
- `F(1, E)` 得到 `f(1 )`：`__VA_ARGS__` 替换之后为空，[[cpp.subst]] 第 4 段看的是替换结果。
- `F(1, E E, )` 得到 `f(1 , ,)`：可变实参是 `E E,`，展开后是一个逗号，不是空的，所以 `__VA_OPT__(,)` 产生逗号。可变实参中的逗号属于可变实参（¶16）。
- `F(, 2)` 得到 `f( , 2)`：`x` 是空实参，可变实参是 `2`。

以上结果都经 Clang 23 `-E` 验证。
</details>

!!! question "思考题 2"
    为什么 `glue(HIGH, LOW)` 得到 `"hello"`，`xglue(HIGH, LOW)` 得到 `"hello" ", world"`？如果把 `LOW` 改成 `#define LOW "!"`，`xglue(HIGH, LOW)` 又会怎样？

<details markdown="1">
<summary>答案</summary>

`glue` 的形参挨着 `##`，实参不展开，直接拼成 `HIGHLOW`。`xglue` 的形参不挨着 `##`，实参先完全展开：`LOW` 变成 `LOW ", world"`，其中的 `LOW` 不再展开。然后 `glue` 拼接的是 `HIGH` 和这个不再展开的 `LOW`，得到 `HIGHLOW`。这是一个新记号，重新扫描时展开为 `"hello"`，后面跟着 `", world"`。

如果 `#define LOW "!"`，`xglue` 先把 `LOW` 展开为 `"!"`，`glue(HIGH, "!")` 要把 `HIGH` 和 `"!"` 拼成一个记号，得到的 `HIGH"!"` 不是合法的预处理记号（`HIGH` 不是字符串字面量的前缀），程序非良构。Clang 23 报 pasting formed 'HIGH"!"', an invalid preprocessing token。
</details>

!!! question "思考题 3"
    `#define EMPTY` 之后，`#define F(x) #x` 的 `F(EMPTY)` 是 `""` 还是 `"EMPTY"`？`#define G(x) F(x)` 的 `G(EMPTY)` 呢？

<details markdown="1">
<summary>答案</summary>

`F(EMPTY)` 是 `"EMPTY"`：`#` 的操作数用原样的实参，不展开。`G(EMPTY)` 是 `""`：`G` 的 `x` 不是 `#` 的操作数，实参先完全展开为空，`F` 收到一个空实参，字符串化得到 `""`。
</details>

## 小结

!!! summary
    - 重定义必须逐记号相同，空白只看有没有；函数式宏还要求形参个数和拼写相同。
    - 空实参也算实参，`F()` 对单形参的宏有一个空实参；只有圆括号能保护实参中的逗号。
    - 关键字、`final`、`override`、`import`、`module`、`pre`、`post` 和标准属性名都不能定义为宏；`likely`、`unlikely` 只能定义为函数式宏。
    - 实参在代入前完全展开，除非它是 `#` 或 `##` 的操作数，这是两层宏写法的原理。
    - `__VA_OPT__(x)` 只在 `__VA_ARGS__` 替换后非空时产生 `x`。
    - `#` 把空白规范为单个空格，转义字面量中的 `"` 和 `\`；`##` 拼不出合法记号时非良构，空实参变成占位记号，拼出来的 `##` 不是运算符。
    - 宏定义无视块结构，一直有效到 `#undef` 或翻译单元结束，阶段 4 之后不复存在。
