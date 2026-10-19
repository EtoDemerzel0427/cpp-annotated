## 这个网站怎么读

C++ 标准是写给编译器作者和委员会的规格说明，不是教材：概念定义先于使用场景，同一个语言机制的规则往往拆散在好几个条款里，例子通常只标一句 `// error`，不解释为什么错，也不说怎么改。

这里的每一页对应标准中的一个条款，用稳定名称（**stable name**，如 `[basic.life]`）标识，在原文结构之上补三样东西：

- **释义**：把规范性条文讲成人话，标出它的精确边界。段落号 ¶ 与最新工作草案一致，随时可以对照 eel.is 原文。
- **背景与关联**：这条规则为什么存在（比如不这样限制，编译器的哪些优化就无法成立），和哪些条款联动，在历次标准和缺陷报告（DR）里怎么演变过来的。
- **例子**：针对核心规则和边界情形给出最小的代码，标明判定（✓ 良构 / ✗ 非良构 / ☠ 未定义行为 …），大多数可以一键在 Compiler Explorer 里运行。

## 建议的阅读路线

标准不是按教学顺序写的，不必从第一页读起。下面几条路线按语言机制组织，按需要选读。

### 1. 规范基础与术语

分不清未定义行为、未指明行为和编译错误，就先从这里开始，这是读懂后面所有条款的基本词汇：

- [[topics/how-to-read-the-standard|专题：如何阅读 C++ 标准]]：stable name、段落号，以及怎么查提案和缺陷报告；
- [[intro.defs|术语与定义]] 和 [[intro.compliance|实现合规性]]：弄清未定义行为（UB）、未指明行为、实现定义行为、非良构（ill-formed）、非良构且无须诊断（IFNDR）的区别，以及 C++26 新增的错误行为（erroneous behavior）。

### 2. 对象模型与生命周期

对象什么时候开始存在、什么时候结束，placement new 和存储复用，以及为什么在旧对象的存储上构造新对象后，有时要用 `std::launder` 才能通过旧指针访问新对象：

- [[basic.def.odr|单一定义规则（ODR）]] → [[intro.object|对象模型]] → [[basic.life|生命周期]] → [[basic.stc|存储期]] → [[class.temporary|临时对象]]。

### 3. 表达式与求值

为什么具名的右值引用是左值，各种隐式转换做了什么，一个表达式里各部分按什么顺序求值：

- [[topics/value-categories|专题：值类别]] → [[basic.lval|值类别]] → [[conv|标准转换]] → [[expr.arith.conv|寻常算术转换]] → [[intro.execution|求值顺序]]。

### 4. 作用域、名字查找与链接

编译器为什么找不到某个名字，为什么报歧义，同一个名字在不同翻译单元里是不是同一个实体：

- [[basic.scope|作用域]] → [[basic.lookup|名字查找]] → [[basic.lookup.argdep|实参依赖查找（ADL）]] → [[basic.link|链接]]。

### 5. 之后

- **初始化**：[[topics/initialization|专题：初始化]] 与 [[dcl.init]]；
- **重载决议**：[[topics/overload-resolution-walkthrough|专题：重载决议推演]] 与 [[over.match]]；
- **模板与名字绑定**：[[topics/two-phase-lookup|专题：两阶段查找]]、[[temp.res]]、[[temp.dep]]、[[temp.deduct]]；
- **常量表达式与编译期求值**：[[topics/compile-time-programming|专题：编译期编程]] 与 [[expr.const]]。

---

左侧目录里加粗、带朱点的条款已有笔记；灰色条款点击后直接跳到 eel.is 原文。按 <kbd>/</kbd> 可以随时按 stable name 或关键词检索。
