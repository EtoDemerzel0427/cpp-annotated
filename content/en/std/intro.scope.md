---
title: Scope
summary: The C++ standard directly constrains implementations (compilers and standard libraries), not programmers; every rule the text states about programs ultimately becomes an obligation on the implementation.
updated: 2026-10-18
---

!!! tldr
    - What the C++ standard directly constrains is the **implementation** (the compiler, standard library and execution environment taken together), not the programmer writing the code.
    - To say what it means for an implementation to support C++, the standard first has to define the language's syntax, semantics and library completely.
    - Every rule the text states about code is ultimately converted into a requirement on the implementation; undefined behavior means, in essence, that the standard places no requirements on the implementation for such a program.

## What the standard specifies (¶1)

¶1 C++ is a general-purpose programming language, but what this document directly constrains is not the programmer but **implementations** of C++ (the compiler, standard library and execution environment taken together). As a technical specification addressed to implementers, its first requirement is that an implementation fully supports the C++ language; to say what supporting the language means, the document then gives a complete definition of C++ in its body. Other requirements on implementations (such as issuing diagnostic messages or providing documentation), as well as exemptions from and relaxations of that first requirement, are spread over the later clauses.

!!! std
    This document specifies requirements for implementations of C++, which is a general-purpose programming language. The first such requirement is that an implementation implements the language, so this document also defines C++.

Understanding that the standard constrains implementations, not programmers directly, is a prerequisite for reading the rest of the text. Take signed integer overflow: the standard does not forbid programmers from writing code that overflows; it says that once overflow happens, this document places no requirements on the implementation. That is exactly what **undefined behavior** ([[defns.undefined]]) means. Since the standard has given up its constraints, the optimizer may assume overflow never happens and remove branches accordingly, and a sanitizer may intercept it at run time and report an error; both conform.

Still, to keep the text readable, the body often states rules from the code's point of view, for example requiring that a program have only one `main` function. [[intro.compliance]] ¶2 specifies how such rules about programs are converted into obligations on the implementation: a program that violates no rule must be accepted and executed correctly (unless it exceeds the implementation limits); for a program that violates a diagnosable rule, the implementation must issue a diagnostic message; when a program violates a rule marked "no diagnostic required", the standard places no requirements on that program. Undefined behavior is specified by the individual subclauses.

The relaxations mentioned at the end of the paragraph are the cases in which an implementation need not literally fulfill the requirement to support the whole language; the rules are collected in [[intro.compliance]]:

- **Implementation limits**: physical machines have finite resources, so when a program is too large or its syntactic constructs are nested too deeply, the implementation may refuse to compile it;
- **Conditionally-supported** constructs: some features may be left unsupported by an implementation, as long as its documentation says so;
- **Freestanding implementations**: implementations for environments without an operating system (such as kernels and embedded devices) need to provide only a subset of the standard library;
- **The as-if rule**: an implementation need not mechanically reproduce every step of the standard's abstract machine; as long as the observable behavior is the same, it may transform and optimize the code freely.

!!! history
    From C++98 through C++14, Clause 1 was titled General, and the scope (`[intro.scope]`) was only its subclause 1.1. C++17 reorganized the clause structure to follow the common layout of ISO documents: Clause 1 keeps only the scope, and the former normative references, terms and definitions, and compliance and general principles became Clauses 2, 3 and 4. In addition, the scope clause of the early standards stated explicitly that C++ is based on the C language; that statement has since been removed, and the relationship between C++ and C is now described by [[intro.refs]] and Annex C ([[diff]]).
