---
title: "Conformance with UAX #31"
summary: "Informative Annex E describes C++'s identifier rules in the terms of the Unicode identifier specification UAX #31: it conforms to R1 (the default identifier syntax, plus mathematical notation and the underscore) and R4 (identifiers must be in NFC); the other requirements are either not adopted or not applicable."
updated: 2026-10-19
---

!!! tldr
    - A C++ identifier consists of a start character followed by continue characters; which characters are allowed is determined by the Unicode properties XID_Start and XID_Continue, plus a leading `_` and some mathematical notation (`∂`, `x₁`).
    - Identifiers must be in NFC form, otherwise the program is ill-formed. So two identifiers are the same exactly when their code point sequences are the same, and `ﬁ` and `fi` are two different names.
    - C++ doesn't guarantee that the identifier character set never changes: when Unicode adds new scripts, new letters can become valid identifier characters.
    - Identifiers are case-sensitive; `$` isn't a standard identifier character, but GCC and Clang accept it as an extension.
    - Clang 23 doesn't check for NFC, and treats two `Å`s that look the same but are encoded differently as two variables.

```cpp run ok
int 变量 = 1;        // Chinese characters: XID_Start
int _tmp = 2;        // _ can start a name: C++ adds it beyond UAX #31
int café = 3;        // é is the precomposed character U+00E9, NFC
int x·y = 4;         // U+00B7 MIDDLE DOT: XID_Continue, but not XID_Start
int ﬁ = 5;           // U+FB01 ligature: unchanged under NFC, so valid
int fi = 6;          // a different name from the previous line (C++ uses NFC, not NFKC)
int ∂f = 7;          // U+2202: ID_Compat_Math_Start
int x₁ = 8, x² = 9;  // subscript and superscript digits: ID_Compat_Math_Continue
int main() {}
```

Every line above is well-formed. Chinese characters, accented letters and superscript digits can all appear in C++ identifiers, but not arbitrarily: the normative rules are in [[lex.name]], which hands the range of identifier characters over to Unicode character properties.

This Annex E is informative and adds no rules. It uses the terms of Unicode Standard Annex 31 (**UAX #31**, [[g:uax31]], *Unicode Identifier and Pattern Syntax*) to explain which of its requirements C++'s identifier rules meet. UAX #31 is a reference specification for programming languages, configuration formats and other systems that need identifiers; it defines a default identifier syntax and a set of numbered optional requirements (R1, R1b, R2 … R8). A system that claims conformance to UAX #31 has to state which of them it meets and how.

## Overview ([uaxid.general])

!!! std
    In terms of UAX #31, this document conforms by meeting the requirements R1 "Default Identifiers" and R4 "Equivalent Normalized Identifiers" from UAX #31.

¶1 C++ conforms to R1 and R4. The other requirements are either an alternative approach C++ doesn't adopt, or don't apply to C++. The whole annex can be condensed into one table:

| Requirement | Content | C++'s position |
|---|---|---|
| R1 | Default identifier syntax | Conforms: adopts the mathematical notation profile, adds `_` as a start character, and has an empty Medial set |
| R1b | Stable identifiers | Holds only to the extent that the XID properties themselves are stable |
| R2 | Immutable identifier character set | Not adopted; the usable characters grow with Unicode versions |
| R3 | Defining whitespace and syntax characters with Pattern_White_Space and Pattern_Syntax | Conformance not claimed |
| R4 | Equivalence by normalization form | Conforms: identifiers must be in NFC |
| R5, R7 | Case-insensitive equivalence | Not applicable; C++ is case-sensitive |
| R6 | Excluding certain characters from normalization | No exclusions made |
| R8 | Hashtag identifiers | Not applicable |

## R1 Default identifiers ([uaxid.def.general])

### UAX #31's default syntax

¶1 UAX #31 defines the default syntax in terms of character properties in the Unicode Character Database (UAX #44):

```text
<Identifier> := <Start> <Continue>* (<Medial> <Continue>+)*
```

`<Start>` is a character with the **XID_Start** property, and `<Continue>` a character with the **XID_Continue** property ([[g:xid-start]]). `<Medial>` is a character that may only appear between two continue characters; some languages use it to allow the hyphen in `foo-bar`.

| Property | Roughly contains | Examples |
|---|---|---|
| XID_Start | Letters of all scripts (general categories Lu, Ll, Lt, Lm, Lo) and letter numbers (Nl) | `a`, `Ω`, `变`, `ア` |
| XID_Continue | XID_Start, plus decimal digits (Nd), combining marks (Mn, Mc) and connector punctuation (Pc) | `0`, `٣`, U+0301, `·` (U+00B7), `_` |

The X in the names means they are revised versions of ID_Start and ID_Continue, closed under NFKC normalization. `_` (U+005F) is connector punctuation (Pc), so it is XID_Continue but not XID_Start.

### C++'s choices

¶1 goes on to explain three adjustments C++ makes to the default syntax:

1. It adopts the Mathematical Compatibility Notation profile defined by UAX #31. This adds ID_Compat_Math_Start (such as `∂`, `∇`, `∞`) to the start characters and ID_Compat_Math_Continue (adding superscript and subscript digits and so on, such as `²`, `₁`) to the continue characters, so that mathematical and physics code can use names like `∂f` and `x₁`.
2. It adds `_` to the start characters. C and C++ have always allowed names like `_x`.
3. The Medial set is empty. In C++, `-`, `'` and `.` are all operators or punctuators and can't appear in the middle of an identifier.

Written in UAX #31's notation:

```text
<Identifier> := <Start> <Continue>*
<Start>      := XID_Start + ID_Compat_Math_Start + U+005F
<Continue>   := <Start> + XID_Continue + ID_Compat_Math_Continue
```

¶2 In the C++ grammar this rule corresponds to *identifier*, *identifier-start* and *identifier-continue* in [[lex.name]].

```cpp error
int 1x;          // error: a digit can't start a name (digits aren't XID_Start)
int ·y;          // error: U+00B7 isn't XID_Start; it can only come later
int 😀;          // error: an emoji is neither XID_Start nor XID_Continue
int a­b;    // error: U+00AD SOFT HYPHEN is a format character, not XID_Continue
int x⁠y;    // error: likewise U+2060 WORD JOINER
int ①;           // error: U+2460 CIRCLED DIGIT ONE isn't XID_Start
```

Clang 23 reports errors for all six lines. The emoji and `①` can't start an identifier and are treated as unexpected characters; `·`, U+00AD and U+2060 are reported as not allowed at the start of an identifier, or not allowed in an identifier.

In the example at the start, Clang 23 gives `-Wmathematical-notation-identifier-extension` warnings for `∂`, `₁` and `²`, calling them a Clang extension. Under the current draft these characters are allowed by the standard; the wording of the diagnostic still reflects the old rule that recognized only the XID properties.

`ﬁ` (the U+FB01 ligature) and `fi` are two different variables. NFKC normalization folds compatibility characters such as ligatures and fullwidth letters into ordinary letters; NFC doesn't. C++ chose NFC (see R4 below), which leaves compatibility characters as they are, so these are different identifiers.

!!! lawyer "The zero-width joiners ZWJ and ZWNJ"
    U+200D ZERO WIDTH JOINER and U+200C ZERO WIDTH NON-JOINER are required for correct spelling in scripts such as Persian and Hindi. Annex E of C++23 had a section R1a explaining that C++ doesn't allow them in identifiers. The current draft no longer has that section: the Unicode version the draft references is 15.1 ([[intro.refs]]), and Unicode 15.1 added these two characters to XID_Continue.

    Clang 23 accepts an identifier like `a<U+200D>b`, giving only a `-Wunicode-zero-width` warning. These two characters are invisible, so two identifiers that look identical may differ in that one contains a ZWJ and the other doesn't, making them two different names.

## R1b Stable identifiers ([uaxid.def.stable])

¶1 R1b is an optional guarantee: once a string is a valid identifier, it remains one in all later versions of Unicode.

¶2 C++ doesn't make this guarantee, except to the extent that UAX #31 guarantees the stability of the XID_Start and XID_Continue properties. Unicode's stability policy guarantees that once a character has these properties it never loses them, so identifiers made only of XID characters are in fact stable. C++ makes no commitment about the set of characters in the mathematical notation profile.

## R2 Immutable identifiers ([uaxid.immutable])

¶1 R2 is a different approach: permanently fix the set of code points allowed in identifiers, so that characters Unicode adds later don't change it.

¶2 C++ doesn't take this approach. When Unicode adds a new script, its letters may acquire the XID properties and become valid identifier characters. An identifier that is ill-formed today may become well-formed after an implementation upgrades its Unicode data.

Annex E from C++11 through C++20 was a fixed table of code point ranges, closer to the R2 approach. The table was permissive: many symbols and emoji could be used in identifiers, and there was no normalization requirement. C++23 adopted [[P1949R7]], switching to a syntax based on the XID properties and requiring NFC; from then on, which characters count as letters is maintained by Unicode. [[diff.cpp20.lex]] records this incompatible change.

## R3 Pattern_White_Space and Pattern_Syntax ([uaxid.pattern])

¶1 UAX #31 recommends that formal languages use two stable character properties, Pattern_White_Space and Pattern_Syntax, to determine which characters are whitespace and which have syntactic meaning, so that future language extensions don't collide with identifiers.

¶2 C++ doesn't claim conformance with this requirement. C++'s whitespace characters, operators and punctuators are listed one by one in [[lex.charset]], [[lex.pptoken]] and [[lex.operators]].

## R4 Equivalent normalized identifiers ([uaxid.eqn])

```cpp
int Å = 1;      // Å: U+00C5, NFC
int Å = 2;     // error: A + U+030A COMBINING RING ABOVE, not NFC
int Å = 3;      // error: U+212B ANGSTROM SIGN, which NFC normalizes to U+00C5; not NFC itself
```

¶1 R4 requires an implementation to specify how identifiers are compared and when they are considered equivalent.

¶2 C++ requires identifiers to be in **NFC** (Normalization Form C, [[g:nfc]]), so identifiers that are the same under NFC are equivalent. The normative rule is in [[lex.name#1]]: if an identifier isn't in NFC, the program is ill-formed.

C++'s approach isn't to normalize identifiers before comparing them; instead it requires identifiers in the source code to already be in NFC. So in a well-formed program, two identifiers are equivalent if and only if their code point sequences are exactly the same. The compiler only has to check, not rewrite, and name mangling and linking can't diverge because of normalization.

!!! impl "Clang 23 doesn't check NFC"
    Compiling the example above with `-std=c++2c -Wall -Wextra -pedantic`, Clang 23 gives no diagnostic at all, and treats the three lines as three different variables, with no redefinition error. According to the standard, the last two lines are ill-formed and require a diagnostic.

    So don't rely on the compiler to catch normalization problems; normalize source files uniformly to NFC in your editor or in CI.

## The remaining requirements (R5–R8)

[uaxid.eqci] ¶1 C++ is case-sensitive when comparing identifiers and does no case folding, so R5 doesn't apply. `Value` and `value` are two names.

[uaxid.filter] ¶1–¶2 If certain characters are excluded from normalization, R6 requires those exclusions to be specified precisely. C++ makes no exclusions; all identifier characters are subject to the NFC requirement.

[uaxid.filterci] ¶1 R7 is the filtered version of R5, and likewise doesn't apply because C++ is case-sensitive.

[uaxid.hashtag] ¶1 R8 is for identifiers like `#tag` on social media. C++ has no hashtags, so it doesn't apply.

## Identifier rules outside UAX #31

Annex E only discusses the requirements of UAX #31. The following identifier-related rules are outside its framework:

| Rule | Source | Description |
|---|---|---|
| Reserved identifiers | [[lex.name#4]] | Names containing `__` or beginning with `_` followed by an uppercase letter are reserved to the implementation; names beginning with `_` in the global namespace are also reserved |
| Identifiers with special meaning | [[lex.name#2]] | `final`, `override`, `import`, `module`, `pre`, `post` and so on |
| Keywords | [[lex.key]] | Keywords can't be used as identifiers |
| Universal character names | [[lex.charset]] | A character in an identifier can be written in a form like `\u00E9`, with the same effect as writing the character directly |
| `$` | [[lex.charset]] | The current draft's basic character set includes `$`, but it has no XID property and can't be used in identifiers |

```cpp error
int $x = 1;  // error (per the standard): $ isn't an identifier character
```

GCC and Clang both accept `$` in identifiers as an extension, for compatibility with symbol names on some old systems. Clang 23 accepts the example above by default, gives a `-Wdollar-in-identifier-extension` warning under `-pedantic`, and reports an error with `-fno-dollars-in-identifiers`.

## Questions

!!! question "1. A compiler normalizes all identifiers to NFC before processing them, and so treats `Å` and `Å` as the same name, without a diagnostic. Is it conforming?"

<details markdown="1">
<summary>Answer</summary>

No. [[lex.name#1]] makes an identifier that isn't in NFC render the program ill-formed, and an ill-formed program requires at least one diagnostic ([[intro.compliance]]). Issuing a warning and then continuing translation with the normalized name is allowed. R4's "the same under NFC means equivalent" is a conclusion drawn from identifiers having to already be in NFC; it doesn't authorize implementations to normalize silently.
</details>

!!! question "2. A letter is added in Unicode 18 and gets the XID_Start property. A compiler using Unicode 15.1 data rejects an identifier containing it, and a compiler using Unicode 18 data accepts it. Which is right?"

<details markdown="1">
<summary>Answer</summary>

Either. The draft's normative reference is Unicode 15.1 ([[intro.refs]]), so rejecting it conforms to the draft. But [[intro.compliance#10]] allows implementations to use a later Unicode version (which one is implementation-defined), so accepting it conforms too. The R2 section explains that C++ never promised an unchanging identifier character set in the first place.
</details>

!!! question "3. Why did C++ choose NFC rather than NFKC?"

<details markdown="1">
<summary>Answer</summary>

The annex gives no reason. In terms of effect, NFKC folds compatibility characters: `ﬁ` becomes `fi`, and `x²` becomes `x2`. If NFKC equivalence were adopted, `x²` and `x2` would be the same name, which conflicts with the purpose of adopting the mathematical notation profile. NFC only merges canonically equivalent encodings, such as the precomposed `é` and `e` plus a combining accent, without changing what the characters mean.
</details>
