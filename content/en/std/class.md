---
title: Classes
summary: "A guide to Clause 11: how class definitions are written and their type-level properties, what members a class can contain, which special member functions the compiler generates for you, and where inheritance, access control, initialization and defaulted comparisons are covered."
updated: 2026-10-19
---

!!! tldr
    - A class is a complete type at its closing brace `}`; but inside a complete-class context, such as a function body or a default argument, the whole class is visible even from within the class.
    - The special member functions (construction, copy, move, assignment, destruction) can be implicitly declared and defined by the compiler; whether they are trivial determines whether objects can be copied byte by byte.
    - Three properties, trivially copyable, standard-layout and implicit-lifetime, determine whether you can `memcpy`, whether `offsetof` is usable, and whether objects can be used directly in memory obtained from `malloc`.
    - An implicit conversion goes through at most one user-defined conversion (a converting constructor or a conversion function).
    - Suggested order: [[class.pre]] → [[class.mem]] → [[special]] and its subclauses → [[class.prop]], then inheritance, access control and initialization as needed.

## Class definitions: rules at the type level

A class is a type. Two classes with exactly the same members are still distinct types ([[class.name#1]]). [[class.pre]] covers the syntax of a class definition (the three forms `class`, `struct`, `union`, and `final`), and the identity of the class's own name inside the class, the injected-class-name.

A class is complete at `}`: from there on `sizeof`, defining objects and accessing members all work, even if not a single member function has been defined yet. Inside the class definition, function bodies, default arguments, default member initializers, `noexcept` specifiers and contract specifiers are **complete-class contexts** ([[class.mem.general#10]]), where members declared later can be used. That is why a member function body can call a member function written below it, while the type of a data member cannot refer to a later declaration.

## Members

[[class.mem]] specifies what can go in a class: data members, member functions, nested types, enumerations, member templates, bit-fields, static members, plus layout rules such as non-static data members being laid out in memory in declaration order. Static members, bit-fields, class-specific `operator new`/`delete` and nested classes also live under 11.4; this site folds them into [[class.mem]].

## Special member functions

The default constructor, copy constructor, move constructor, copy assignment, move assignment and destructor can be implicitly declared by the compiler when you don't declare them, implicitly defined when they are used, and defined as deleted (`= delete`) when necessary. The way they suppress one another is the language-level basis of the Rule of 0/3/5. [[special]] gives the overall table; [[class.ctor]], [[class.copy.ctor]], [[class.copy.assign]] and [[class.dtor]] cover the details.

A special member function that does nothing extra (byte-wise copy, a destructor that does nothing) is **trivial**. Triviality determines the three properties below.

## Three properties of classes

[[class.prop]] defines the three classifications used most often when dealing with C and hardware:

| Property | What it gives you |
|---|---|
| Trivially copyable | Can be copied with `memcpy` or `std::bit_cast`, can be put in `std::atomic` |
| Standard-layout | The first member has the same address as the object, `offsetof` is guaranteed, data can be exchanged with C |
| Implicit-lifetime | Such objects can be used directly in storage obtained from `malloc` or `memcpy` |

## User-defined conversions

A non-`explicit` constructor provides an implicit conversion from its parameter type to the class type, and a conversion function `operator T()` provides an implicit conversion from the class type to `T` ([[class.conv]]). An implicit conversion uses at most one user-defined conversion ([[class.conv.general#4]]), so a two-step conversion like `A → B → C` never happens automatically, and overload resolution doesn't expand indefinitely because of it.

## The remaining subclauses

| Subclause | Contents | On this site |
|---|---|---|
| 11.5 | Unions and anonymous unions | [[class.union]] |
| 11.6 | Local classes | [[class.local]] |
| 11.7 | Derived classes, multiple inheritance, virtual functions, abstract classes | [[class.derived]] |
| 11.8 | Member access control, friends | [[class.access]] |
| 11.9 | Member initializer lists, inheriting constructors, rules during construction and destruction, copy elision | [[class.init]] |
| 11.10 | `= default` for `operator==` and `operator<=>` | [[class.compare]] |

## Changes to this clause in C++26

- Trivial unions {{c++26}}: a union's default constructor and destructor are no longer defined as deleted just because a variant member has a non-trivial default constructor or destructor (see [[class.default.ctor]] and [[class.dtor]]).
- The notion of a trivial class, together with `std::is_trivial`, moved to Annex D and is deprecated {{c++26}} ([[depr.meta.types]]); [[class.prop]] keeps only the three properties above.
- Data member descriptions were introduced for static reflection's `std::meta::define_aggregate` ([[class.mem.general#32]]) {{c++26}}.
- Member declarations can contain `consteval` blocks and contract specifiers {{c++26}}.
