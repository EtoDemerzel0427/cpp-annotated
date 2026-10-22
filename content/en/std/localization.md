---
title: "Localization library: locales and facets"
summary: "A std::locale is a reference-counted, immutable set of facets indexed by type; this page covers facet identity and lifetime, locale construction and names, how locale::global interacts with the C locale, and convenience functions like isspace(c, loc)."
updated: 2026-10-19
---

!!! tldr
    - A `std::locale` is a collection of facets, each responsible for one kind of localization rule (decimal point, character classification, collation, ...), looked up with the facet's type as the key.
    - A locale is reference-counted internally, so copying it is cheap; a facet installed in a locale never changes, and the reference obtained from `use_facet` stays valid as long as a locale holding it exists.
    - To customize a standard facet, derive a class, override the protected virtual functions, and install it in a new locale with `locale(old, new my_facet)`.
    - A locale constructed from a name has a name; a locale with a custom facet installed does not. `locale::global` calls `setlocale` only when its argument has a name, and nothing ever syncs in the other direction.
    - Whether there is one global locale per thread is implementation-defined; libstdc++ and libc++ both have one for the whole process.

## A locale is a set of facets [locale.general]

```cpp run title="custom-numpunct.cpp" ok
#include <cassert>
#include <format>
#include <locale>
#include <sstream>
#include <string>

struct swiss_punct : std::numpunct<char> {
protected:
    char do_thousands_sep() const override { return '\''; }
    std::string do_grouping() const override { return "\3"; }    // groups of 3 digits
    std::string do_truename() const override { return "ja"; }
};

int main() {
    // refs defaults to 0: the library deletes it when the last locale holding it is destroyed
    std::locale loc(std::locale::classic(), new swiss_punct);

    std::ostringstream os;
    os.imbue(loc);
    os << 1234567 << ' ' << std::boolalpha << true;
    assert(os.str() == "1'234'567 ja");

    assert(std::format(loc, "{:L}", 1234567) == "1'234'567");   // format's L option uses numpunct too
    assert(std::format(loc, "{}", 1234567) == "1234567");       // without L it is locale-independent
    assert(loc.name() == "*");                                  // no name after installing a custom facet
}
```

The same number is written `1.234.567` in Germany and `1'234'567` in Switzerland; dates, currency, character classification and string collation each have their own conventions too. The C library handles these differences with a single process-wide `setlocale`. C++ wraps each kind of rule in an object called a **facet**, and bundles a set of facets into a `std::locale`. Each stream can imbue its own locale; `os` above uses a custom thousands separator.

¶1 A `locale` is a set of polymorphic facets indexed by facet type. A facet therefore has a double identity: it is a class interface (`numpunct<char>`, for example, has a member `decimal_point()`), and its type is also the key for finding it in a locale.

¶2 There are only two function templates for accessing facets. ¶4 `use_facet<Facet>(loc)` returns a reference to that facet in the locale and throws `bad_cast` if it is absent; `has_facet<Facet>(loc)` asks whether it is present. User-defined facets can also be installed in a locale and are used the same way as standard facets.

¶5 Note 1 lists two convenient entry points that bypass `use_facet`: the locale's own `operator()`, which can serve as a string comparison predicate, and global functions like `isspace(c, loc)` (see below).

In implementations, a `locale` object is usually just a pointer to a reference-counted array of facet pointers, arranged by each facet's `id` number. Copying a `locale` just increments the reference count.

## Facet identity: `locale::facet` and `locale::id`

### What classes are facets [locale.facet]

!!! std
    A class is a *facet* if it is publicly derived from another facet, or if it is a class derived from `locale::facet` and contains a publicly accessible declaration as follows: `static ::std::locale::id id;`

¶1 The definition of a [[g:facet]] has two cases: a class publicly derived from another facet; or a class derived from `locale::facet` that has a public `static locale::id id;`. A footnote stresses that this is the complete requirement: a facet needs no public copy constructor, assignment, default constructor or destructor. In fact `locale::facet` forbids copying, and the destructors of the standard facets are all `protected`, so facets are generally created with `new` and handed to a locale to manage.

¶2 Template parameters named `Facet` in the locale function templates are required to be facets. Passing a type that is not a facet, or a `volatile`-qualified facet, makes the program {{ill-formed}}; a `const`-qualified facet is fine.

### A derived facet shares a slot with the standard facet

`id` is the index for finding a facet in a locale ([locale.id] ¶1). `swiss_punct` above declares no `id` of its own; the `id` it inherits is `numpunct<char>::id`, so the two occupy the same slot. `locale(loc, new swiss_punct)` replaces exactly `numpunct<char>`, and that is what `num_put` and `format` find through `use_facet<numpunct<char>>`. This is the standard way to customize a standard facet.

To add an entirely new facet rather than replace an existing one, redeclare `static std::locale::id id;` in the derived class.

!!! lawyer "A derived facet without its own id can be found in classic() too"
    Because they share a slot, `has_facet<swiss_punct>(std::locale::classic())` is also true: it only checks whether that slot holds something. Calling `use_facet<swiss_punct>(classic())` then yields a `swiss_punct&` that actually refers to an ordinary `numpunct<char>` object (libc++ uses `static_cast` internally), and accessing members specific to `swiss_punct` is {{ub}}. Also, [locale.global.templates] ¶1 requires the definition of `use_facet`'s `Facet` to contain a public static member `id`; the wording does not make clear whether an inherited `id` counts. Clang 23 + libc++ accept this usage.

¶2 Note 1 in [locale.id] explains an implementation detail of `id`: iostreams may be used during static initialization, so initializing `id` cannot depend on dynamic initialization. One approach is to assign `id` its number only when the facet is first installed in a locale, which relies only on static storage being zero-initialized before any constructor runs ([[basic.start.static]]).

## Facet lifetime

### The `refs` parameter ([locale.facet] ¶3–¶4)

¶3 Every facet constructor has a `refs` parameter for lifetime management. With `refs == 0`, when the last locale containing the facet is destroyed, the implementation does `delete static_cast<locale::facet*>(f)`; with `refs == 1`, the implementation never destroys it, which suits facets with static storage duration or ones you manage yourself.

¶4 The constructors of the standard facets all accept this parameter and pass it to the base class; all single-argument constructors are `explicit`.

### When references are valid ([locale.general] ¶6–¶7)

¶6 A reference obtained from `use_facet` remains usable as long as some locale object refers to that facet, and the results of its member functions may be cached. [locale.global.templates] ¶4 gives a more direct guarantee: the returned reference is valid at least as long as any copy of `loc` exists.

¶7 Repeated calls to the same member function on the same facet in the same locale must return the same result; in other words, facets are immutable. This is the basis for caching; iostream implementations usually store the `ctype` and `numpunct` pointers in the stream at imbue time.

!!! ub "A facet reference obtained from a temporary locale"
    ```cpp
    const auto& np = std::use_facet<std::numpunct<char>>(std::locale("de_DE.UTF-8"));
    char c = np.decimal_point();   // the temporary locale is gone; there may be no locale referring to this facet any more
    ```
    The temporary locale is destroyed at the end of the full-expression. If no other locale holds this facet, it has been deleted, `np` dangles, and calling through it is {{ub}}. Implementations often keep an internal cache for named locales, so this code may happen to work, but the standard does not guarantee it. Store the locale in a named variable first.

## Categories [locale.category]

`locale::category` is just `int`. ¶1 Its valid values are the six bitmask elements `collate`, `ctype`, `monetary`, `numeric`, `time` and `messages`, each representing a category; `none` is 0 and `all` is the union of all categories; the bitwise OR of two categories represents their union.

¶2 Member functions taking a category argument use it to select a set of facets. Each category includes at least the facets listed in Table 91 (each in `char` and `wchar_t` versions):

| Category | Facets |
|---|---|
| `collate` | `collate` |
| `ctype` | `ctype`, `codecvt<char, char, mbstate_t>`, `codecvt<wchar_t, char, mbstate_t>` |
| `monetary` | `moneypunct` (including the `Intl = true` version), `money_get`, `money_put` |
| `numeric` | `numpunct`, `num_get`, `num_put` |
| `time` | `time_get`, `time_put` |
| `messages` | `messages` |

The `codecvt` specializations for `char16_t` and `char32_t` are in Annex [[depr.locale.category]] and are deprecated.

¶3 For every constructed locale and for `classic()`, `has_facet` is true for all facets in Table 91: the standard facets are always complete. ¶4 and Table 92 also require implementations to provide the `_byname` versions and specializations of `num_get`, `num_put`, `money_get` and others for arbitrary iterator types.

¶5 The standard `num_get` and `num_put` call `use_facet` only for `numpunct<charT>` and `ctype<charT>`, using the `getloc()` of the `ios_base&` argument. So if you replace the stream's `numpunct`, `num_put` is certain to use it. The rules for each facet are in [[locale.categories]].

## Construction, names and equality

### Named and unnamed locales ([locale.general] ¶8)

¶8 A locale constructed from a name string (such as `"POSIX"`), or composed of parts of two named locales, has a name; all other locales do not. Named locales compare equal by name; an unnamed locale is equal only to itself and its copies, and its `name()` returns `"*"`.

Names matter because only named locales can be handed to C's `setlocale`; see `locale::global` below.

### Constructors [locale.cons]

| Construction | Result | Named? |
|---|---|---|
| `locale()` (¶1) | a copy of the current global locale; same as `classic()` if `global` has never been called | as the global locale |
| `locale(const char* name)` (¶2–¶4) | constructed from a C locale name; throws `runtime_error` if the name is invalid or a null pointer | yes |
| `locale(other, name, cats)` (¶6–¶9) | a copy of `other`, except the categories in `cats` come from `locale(name)` | if and only if `other` is |
| `locale(other, Facet* f)` (¶11–¶12) | a copy of `other` with `Facet`'s slot replaced by `f`; just `other` if `f` is null | not if `f` is non-null |
| `locale(other, one, cats)` (¶13–¶15) | a copy of `other`, except the facets of the `cats` categories come from `one` | as `other` if `cats == none`; otherwise only if both are named |

¶4 The only valid names are `"C"`, `""` and other implementation-defined values. `""` means the user's environment preferences, which on POSIX are determined by the `LANG` and `LC_*` environment variables. ¶6 and ¶13 require `cats` to be a valid category value.

### Members and operators ([locale.members], [locale.operators])

- `combine<Facet>(other)` (¶1–¶4): returns a copy of `*this` except that `Facet` comes from `other`; throws `runtime_error` if `other` lacks that facet. The result has no name.
- `name()` (¶5): returns the name if there is one, otherwise `"*"`.
- `encoding()` (¶6–¶7, {{c++26}}): requires `CHAR_BIT == 8` and returns a [[text.encoding|`text_encoding`]] representing the encoding associated with the locale, as implementation-defined. libc++ queries it via `name()`, so an unnamed locale gets an empty name.
- `operator==` ([locale.operators] ¶1): true when both are the same locale, one is a copy of the other, or both are named with the same name. Two unnamed locales are unequal even if their facets are identical.
- `operator()(s1, s2)` (¶2–¶5): compares two `basic_string`s with `collate<charT>` and returns `compare(...) < 0`. So a locale is itself a comparison predicate, and you can write `std::sort(v.begin(), v.end(), loc)` (Example 1).

## The global locale [locale.statics]

!!! std
    If the argument has a name, does `setlocale(LC_ALL, loc.name().c_str());` otherwise, the effect on the C locale, if any, is implementation-defined.

¶1 `locale::global(loc)` sets the global locale, after which `locale()` returns copies of it. If `loc` has a name, it also calls `setlocale(LC_ALL, ...)`; if not, the effect on the C locale is implementation-defined. ¶2 It returns the previous global locale.

¶3 No library function other than `global` changes the value returned by `locale()`. In particular, calling C's `setlocale` directly does not affect C++'s global locale. This asymmetry often causes hard-to-find problems:

- `std::locale::global(std::locale(""))` also changes the behavior of the C library (`printf`, `strtod` and so on);
- `std::locale::global(std::locale(std::locale::classic(), new my_punct))` passes an unnamed locale, and libc++ in our tests leaves the C locale unchanged;
- `setlocale(LC_ALL, "C")` changes only the C locale; a `std::locale()` created afterwards is still the old global locale.

Existing streams are not affected by `global`. `std::cout` imbued the global locale of the time when it was constructed; to change it later you must call `std::cout.imbue(...)` explicitly.

¶4–¶6 `classic()` returns the `"C"` locale, equivalent to `locale("C")`; it, its facets, and the member functions of those facets never change over time.

### One per thread or one per program ([locale.general] ¶9)

!!! std
    Whether there is one global locale object for the entire program or one global locale object per thread is implementation-defined.

¶9 Whether the global locale is one for the whole program or one per thread is implementation-defined ({{impl}}). The standard recommends one per thread; if there is only one for the whole program, the implementation need not avoid data races on it ([[res.on.data.races]]). libstdc++ and libc++ both have one per process, so multithreaded programs calling `locale::global` must synchronize themselves, preferably calling it only before starting other threads.

## Convenience functions [locale.convenience]

[classification] ¶1 The 12 function templates from `isspace(c, loc)` to `isblank(c, loc)` each return `use_facet<ctype<charT>>(loc).is(ctype_base::F, c)`. They take a `charT` and, unlike `<cctype>`'s `std::isspace(int)`, have no requirement that the argument be representable as `unsigned char` (see [[text.c.strings]]). A footnote suggests that in loops you should extract the `ctype` facet first and use it directly, or use its bulk version `is(low, high, vec)`, because each call to a convenience function does a `use_facet`.

[conversions.character] `toupper(c, loc)` and `tolower(c, loc)` forward to the same-named members of `ctype<charT>`. This is a per-character mapping and cannot express one-to-many case conversions like `ß` to `SS`.

<details class="fine" markdown="1"><summary>Remaining wording</summary>

[localization.general] ¶1 lists the areas the localization library covers: character classification and string collation, formatting and parsing of numbers, monetary amounts and dates/times, and message retrieval. ¶2 and Table 90 divide it into three parts: [locales] (this page), [[locale.categories]] and [[c.locales]].

[locale.syn] is the synopsis of `<locale>`: `locale`, `use_facet`/`has_facet`, the 12 classification functions and 2 case conversion functions, and all the facet templates of the six categories with their `_byname` versions.

Example 1 in [locale.general] ¶3 shows how to implement `operator<<` for a date type using `time_put`.

[locale.category] ¶6 explains which sets of types the template parameters named `InputIterator`, `OutputIterator`, `C` and `International` in facet declarations stand for.

[locale.facet] ¶5 specifies that `xxx_byname(name)` has the same semantics as the same-named facet of `locale(name)` and accepts names as `const char*` or `string`; facets without a `_byname` version (such as `num_get`) implement named-locale semantics by consulting other facets.

[locale.cons] ¶5 and ¶10 are the overloads taking `string`, equivalent to the `c_str()` versions; ¶16–¶17 is copy assignment.

[locale.global.templates] ¶1–¶3 and ¶5 are the formal specification of `use_facet` and `has_facet`, covered above.

</details>

## Common misconceptions

!!! pitfall "Assuming constructing a locale from an empty string always succeeds"
    `locale("")` depends on the `LANG` and `LC_*` variables of the runtime environment. If they name a locale the system does not have installed, the constructor throws `runtime_error` ([locale.cons] ¶3). This is common in slimmed-down container images.

!!! pitfall "Assuming `imbue` affects output already written"
    `basic_ios::imbue` affects only subsequent input and output. Switch locales in the middle of a sequence of output, and the two parts follow different rules.

## Questions

!!! question "Question 1"
    Given `std::locale a("C"), b = std::locale::classic();`, are the two equal? Is `std::locale(a, new std::numpunct<char>)` equal to `a`?

<details markdown="1">
<summary>Answer</summary>

`a == b` is true: both are named `"C"`, and [locale.operators] ¶1 says equal names mean equal locales.

The second is false: a locale obtained by installing a non-null facet pointer has no name ([locale.cons] ¶12), and an unnamed locale equals only itself and its copies ([locale.general] ¶8), even though the installed `numpunct<char>` behaves exactly like the original.
</details>

!!! question "Question 2"
    A facet with static storage duration, constructed with `refs == 1`, is installed in a locale, and then the locale is destroyed. What happens? What if the default `refs == 0` was used?

<details markdown="1">
<summary>Answer</summary>

With `refs == 1`, nothing happens: [locale.facet] ¶3 says the implementation never destroys it.

With the default `refs == 0`, the implementation `delete`s it when the last locale is destroyed. Calling `delete` on a pointer that did not come from `new` is {{ub}} ([[expr.delete]]).
</details>

## Summary

- A locale is a reference-counted, immutable set of facets indexed by `Facet::id`, and copying it is cheap.
- The reference returned by `use_facet` is valid as long as a locale holding the facet exists, and results may be cached.
- Derive from a standard facet and keep its `id`, and you replace it; redeclare `static locale::id id`, and you add a new facet.
- Only named locales can sync with the C locale: `locale::global` calls `setlocale` only when its argument is named, and `setlocale` never affects `std::locale()`.
- Whether there is one global locale per thread is implementation-defined; mainstream implementations have one per process.
