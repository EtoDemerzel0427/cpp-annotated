## 体例说明

C++ 标准（ISO/IEC 14882）是面向编译器与标准库实现者的规范文档，表述高度形式化：概念定义先于使用场景，单一语言机制的完整规则往往分布于不同章节，随附示例通常仅标注合规性结论（如 `// error`），略去了推导过程与背景阐释。

本站以公开的 WG21 最新工作草案（[eel.is/c++draft](https://eel.is/c++draft/)）为底本。除专题、工具链与历史沿革外，主体内容为各条款的逐节注疏（以 **stable name** 标识，如 `[basic.life]`），在原文结构之上提供三项内容：

- **条文释义**：梳理规范性条文（normative wording）的精确语义与适用边界。章节与段落编号（¶）同 eel.is 工作草案保持一致，便于随时对照原文。
- **背景与关联**：阐明规则背后的设计考量（如特定的优化假设或对象模型约束）、跨章节条款的交互关系，以及在历次标准与缺陷报告（DR）中的演进脉络。
- **代码示例**：针对核心规则与边界情形提供最小复现代码，明确标注标准判定结果（✓ 良构 / ✗ 非良构 / ☠ 未定义行为等），多数示例可在 Compiler Explorer 中一键运行验证。

## 导读路径

标准文档并非按教学顺序编排。以下路径按核心语言机制组织，供按需切入：

### 1. 规范基础与术语体系

理解标准的表述惯例与行为分类是阅读后续条款的前提：

- [[topics/how-to-read-the-standard|专题：如何阅读 C++ 标准]]：章节结构、stable name、段落编号，以及提案与缺陷报告（DR）的检索方法；
- [[intro.defs|术语与定义]] 与 [[intro.compliance|实现合规性]]：辨析未定义行为（UB）、未指明行为（unspecified）、实现定义行为（implementation-defined）、非良构（ill-formed）、非良构且无须诊断（IFNDR），以及 C++26 引入的错误行为（erroneous behavior）。

### 2. 对象模型与生命周期

围绕对象的创建、存储期与生命周期起止，厘清原位构造（placement new）、存储复用及指针有效性边界（例如在既有存储上重新构造对象后，何时须经由 `std::launder` 访问）：

- [[basic.def.odr|单一定义规则（ODR）]] → [[intro.object|对象模型]] → [[basic.life|生命周期]] → [[basic.stc|存储期]] → [[class.temporary|临时对象]]。

### 3. 表达式与求值语义

厘清表达式的值类别（value category）、标准隐式转换序列与求值顺序（sequencing）——例如具名右值引用何以归入左值、算术转换如何决定公共类型、子表达式的值计算与副作用按何种次序发生：

- [[topics/value-categories|专题：值类别]] → [[basic.lval|值类别]] → [[conv|标准转换]] → [[expr.arith.conv|寻常算术转换]] → [[intro.execution|求值顺序]]。

### 4. 作用域、名字查找与链接

梳理声明的作用域划分、无限定与限定名字查找、实参依赖查找（ADL）及链接属性，解答名字不可见、重载歧义，以及同一名字在不同翻译单元中是否指代同一实体等问题：

- [[basic.scope|作用域]] → [[basic.lookup|名字查找]] → [[basic.lookup.argdep|实参依赖查找（ADL）]] → [[basic.link|链接]]。

### 5. 核心语言机制进阶

- **初始化**：[[topics/initialization|专题：初始化]] 与 [[dcl.init]]；
- **重载决议**：[[topics/overload-resolution-walkthrough|专题：重载决议推演]] 与 [[over.match]]；
- **模板与名字绑定**：[[topics/two-phase-lookup|专题：两阶段查找]]、[[temp.res]]、[[temp.dep]]、[[temp.deduct]]；
- **常量表达式与编译期求值**：[[topics/compile-time-programming|专题：编译期编程]] 与 [[expr.const]]。

---

按 <kbd>/</kbd> 可随时通过 stable name 或关键词检索。
