---
title: The STL and the birth of the C++98 standard library
summary: Why containers before templates were awkward, how the STL used iterators to separate containers from algorithms, and how 1990s decisions about allocators, char_traits, copy-on-write strings, vector<bool> and auto_ptr remain in today's wording.
tags: standard library, STL, generic programming, allocators, iostream, string, vector<bool>, auto_ptr, valarray, C++98, C++03
updated: 2026-10-19
---

!!! tldr
    - Before templates, containers could only be written with a common base class plus pointers: you couldn't put an `int` in, and getting things out required a downcast. The STL used templates and iterators to separate containers from algorithms, and built-in arrays and pointers work with it directly.
    - The STL was only submitted to the committee in 1994, and went into the draft after about two thirds of it was cut. Hash tables were left out for lack of time, and when C++11 added them they had to be named `unordered_map`.
    - Iterator categories, tag dispatch and traits were all invented while templatizing the STL and iostreams. The STL's requirement tables are today's *Cpp17* named requirements, and C++20 rewrote them again with concepts.
    - Allocators were originally designed for 16-bit segmented memory; C++98 already allowed implementations not to support their main purpose, and they have been slimmed down ever since.
    - C++11's invalidation rules ruled out copy-on-write `string`; of the two controversial components `vector<bool>` and `auto_ptr`, one stayed where it was and the other was removed, and both left marks in the wording.

This page is based mainly on Stroustrup's HOPL papers (HOPL II: *A History of C++: 1979–1991*; HOPL III: *Evolving a language in and for the real world: C++ 1991–2006*), Stepanov's interviews and recollections, and the relevant WG21 papers and LWG issues. The evolution of the standard library after C++11 is in [[history/modern-library]], and the standardization process as a whole in [[history/standards-timeline]].

## Containers before templates

C++ in the 1980s already had iostreams, a complex number library and some container classes, but no templates. Parameterized types could only be simulated with macros, so most container libraries of the time followed the Simula and Smalltalk pattern: elements had to derive from a common base class, and containers stored pointers to the base class.

<div class="compare" markdown="1">

```cpp run ok title="Common base class style (1980s)"
struct Object { virtual ~Object() {} };

struct List {          // can only store Object*
  Object* items[16]; int n = 0;
  void put(Object* p) { items[n++] = p; }
  Object* get(int i) { return items[i]; }
};
struct Int : Object {  // an int has to be wrapped first
  int v; Int(int x) : v(x) {}
};

int main() {
  List l;
  l.put(new Int(42));
  Int* p = dynamic_cast<Int*>(l.get(0));
  int r = p ? p->v : -1;  // downcast on the way out
  delete l.get(0);
  return r == 42 ? 0 : 1;
}
```

```cpp run ok title="Template style (STL)"
#include <vector>

int main() {
  std::vector<int> v;
  v.push_back(42);   // stores an int directly
  int r = v[0];      // no cast, no virtual call
  return r == 42 ? 0 : 1;
}
```

</div>

Stroustrup did not accept the design on the left, for exactly the reasons visible in the code: built-in types can't be put in, getting elements out needs a downcast, it is not statically type-safe, and every access goes through an extra indirection (HOPL III §4.1.1). What he wanted were containers that could hold an `int` directly, were statically type-safe and had no extra overhead, and that could not be written in C++ without templates.

He later called this his biggest mistake: release 1.0 should have waited until there was a library with a linked list, an associative array, a range-checked array and a simple string (HOPL II §7.3). As it was, every team reinvented these classes, and the community ended up with many mutually incompatible container libraries.

Once standardization began, the policy Stroustrup proposed was: the C library, iostreams and the language support part must be standardized; beyond that, the committee would only accept building-block components, not comprehensive frameworks, and would not compete with commercial library vendors (HOPL III §4.2). For building blocks to be used by everyone, they had to be efficient and general enough: a container whose element access goes through a virtual call is not efficient enough, and a container that can't hold arbitrary types is not general enough.

## The STL model

From the late 1970s Alexander Stepanov had been working on what later came to be called **generic programming**: writing algorithms that depend only on the minimal requirements their types must meet, and then combining them with specific data structures. He implemented generic libraries in Scheme and then Ada, but couldn't write algorithms that worked for both linked lists and arrays while being efficient enough (Stepanov's own account, included in HOPL III §4.1.8).

C++ templates gave him what he needed. One point was that function templates can deduce template arguments from function arguments, without explicit instantiation as with Ada generics. Stepanov had argued for the latter, and Stroustrup did not adopt it; both later said that this very decision made many STL idioms possible (Stepanov's 1995 *Dr. Dobb's Journal* interview; HOPL III §4.1.2).

The core of the STL is a complete separation of containers and algorithms. Containers are parameterized on the element type, and each container provides its own **iterator** type; algorithms access elements only through iterators. The iterator interface borrows pointer notation (`*`, `++`, `!=`), so ordinary pointers are themselves iterators:

```cpp run title="find.cpp" ok
#include <algorithm>
#include <list>
#include <string>
#include <vector>

int main() {
    std::vector<int> vi{3, 7, 42};
    std::list<std::string> ls{"Koenig", "Stepanov", "Lee"};
    auto p = std::find(vi.begin(), vi.end(), 7);
    auto q = std::find(ls.begin(), ls.end(), "Stepanov");
    int a[] = {1, 2, 3};
    int* r = std::find(a, a + 3, 2);   // works for built-in arrays and pointers too
    return (p != vi.end() && q != ls.end() && *r == 2) ? 0 : 1;
}
```

The same `find` works on `vector<int>`, `list<string>` and a built-in array, with no virtual functions and no common base class. m algorithms and n containers need m + n pieces of code, not m × n.

Another STL practice was to specify the complexity of every operation. Stepanov considered complexity part of the interface: both `vector` and `list` can insert in the middle, and the difference is precisely the cost (HOPL III §4.1.7). That is why every algorithm in [[algorithms]] today has a *Complexity* paragraph, and the requirement tables in [[container.requirements]] have a complexity column.

## How the STL got into the standard

In late 1993, at Andrew Koenig's invitation, Stepanov gave a talk at a standards committee meeting. It covered only the axioms that regular types and forward iterators should satisfy, and one algorithm, `find`. Stroustrup says the talk shifted the committee's attitude from no major changes being possible at this stage to it being worth a look (HOPL III §4.1.2).

The problem was time. The committee planned to finish the standard soon, and the previous meeting had just passed a resolution to accept no more large proposals (Stepanov interview). In January 1994 Koenig told Stepanov that to get into the standard, a formal proposal had to be submitted within weeks; Stepanov and Meng Lee rushed out the proposal and presented the complete STL at the March meeting.

Size was the main obstacle. The committee worried there wasn't time to properly review such a large specification. Stroustrup recalls that in the end, at Stepanov's request, he crossed out about two thirds of the text, and every remaining item had to have someone explain why it was useful to most programmers (HOPL III §4.1.2). The trimmed STL was voted into the working draft at the Waterloo meeting in July 1994. Even so, turning it into standard wording delayed the standard by more than a year.

Stroustrup says his contribution apart from the cutting was small; one item was drawing the first **requirements table** on Stepanov's blackboard: a table listing which expressions a template argument must support, with their types and semantics. The standard still describes requirements on template parameters with such tables. He also pointed out that the very existence of requirements tables shows the language's lack of expressiveness: these requirements ought to be expressible in code (HOPL III §4.1.2). That was only partly achieved with C++20 concepts ([[history/concepts]]).

<details class="fine" markdown="1">
<summary>Discrepancies in the dates</summary>

HOPL III places Stepanov's talk at the San Jose meeting in October 1993; Stepanov says November in an interview, and the surviving slides are dated 11 November 1993. HOPL III places the Waterloo meeting in October 1994, while P. J. Plauger's column in the August 1997 *C/C++ Users Journal* says July 1994. This page uses November and July. The text adopted into the draft was based on Stepanov and Lee's HP Labs technical report HPL-94-34 (August 1994, revised 1995).

</details>

## Iterator categories, tags and traits

If all iterators supported the same set of operations, the model would be simple. But arrays, linked lists and input streams inherently have different capabilities: an array allows random access, a linked list can only step forward or backward one at a time, and an input stream can only be read once. So the STL divides iterators into five categories: input, output, forward, bidirectional and random access (HOPL III §4.1.6). The same algorithm can have different implementations for different categories, with the most suitable one chosen at compile time.

How do you find out at compile time which category an iterator belongs to? The 1995 STL technical report used overloaded functions: `iterator_category(i)` returned an empty tag object, and `value_type(i)` and `distance_type(i)` returned null pointers, used only to pass types to helper functions. This approach was unsystematic and error-prone.

The more general approach was **traits**, distilled by Nathan Myers while templatizing iostreams and string: a helper class template that collects the properties of some kind of type in one place (Myers, *Traits: a new and useful template technique*, *C++ Report*, 1995). Applied to iterators, that is `iterator_traits`: ordinary iterators provide these properties through their member types, and pointers get them through a partial specialization. Partial specialization of class templates was itself only added to C++ in 1995, and the STL was one of its main motivations (HOPL III §4.1.5).

Tag dispatch plus `iterator_traits` was the typical technique inside the standard library from C++98 to C++17, and it still works today:

```cpp run title="tag-dispatch.cpp" ok
#include <cassert>
#include <iterator>
#include <list>
#include <vector>

template<class It>
void my_advance(It& it, int n, std::input_iterator_tag) {
    while (n-- > 0) ++it;                 // can only step one at a time
}
template<class It>
void my_advance(It& it, int n, std::random_access_iterator_tag) {
    it += n;                              // constant time
}
template<class It>
void my_advance(It& it, int n) {
    my_advance(it, n, typename std::iterator_traits<It>::iterator_category{});
}

int main() {
    std::vector<int> v{0, 1, 2, 3};
    std::list<int>   l{0, 1, 2, 3};
    int a[] = {0, 1, 2, 3};
    auto vi = v.begin(); my_advance(vi, 2);   // random_access version
    auto li = l.begin(); my_advance(li, 2);   // bidirectional iterator falls back to the input version
    int* pi = a;         my_advance(pi, 2);   // pointer: partial specialization of iterator_traits
    assert(*vi == 2 && *li == 2 && *pi == 2);
}
```

`list`'s iterator can select the `input_iterator_tag` version because the tag classes are related by inheritance: `bidirectional_iterator_tag` derives from `forward_iterator_tag`, which derives from `input_iterator_tag` ([[std.iterator.tags]]). A category without its own overload falls back to the nearest version through the derived-to-base conversion.

### Requirement tables and concepts side by side

In today's standard this system has two layers. The STL's requirement tables were kept, renamed to named requirements such as *Cpp17InputIterator* ([[iterator.cpp17]]), for components still specified in C++98 style. The C++20 ranges work ([[P0896R4]]) redefined iterators with concepts ([[iterator.concepts]]) and added the `contiguous_iterator` category.

The two definitions don't always agree. *Cpp17ForwardIterator* requires dereferencing to yield a real reference; the C++20 `forward_iterator` concept does not. So some iterators are random access according to the concepts but only input iterators according to the old categories:

```cpp run ok
#include <iterator>
#include <ranges>
#include <type_traits>

using It = std::ranges::iterator_t<std::ranges::iota_view<int, int>>;
static_assert(std::random_access_iterator<It>);        // C++20 concept
static_assert(std::is_same_v<std::iterator_traits<It>::iterator_category,
                             std::input_iterator_tag>); // C++98 category
int main() {}
```

Dereferencing an `iota_view` iterator returns an `int` value rather than a reference, so in the old system it only counts as an input iterator. `vector<bool>`, below, violates the same requirement.

## The hash tables that were cut

The 1994 cuts and the time pressure that followed kept one kind of container everybody wanted out of C++98: hash tables. HOPL III §6.2 says hash tables would have been in C++98 if there had been time to do the detailed design; in 1995 Barreiro, Fraley and Musser tried to get a proposal ready before the standard was finished, but the committee no longer had time to deal with it.

As a result, each implementation provided its own `hash_map` and `hash_set`, similar but not identical. When Matt Austern proposed standard hash containers in [[N1456]] in 2003, he deliberately chose new names to avoid clashing with these existing classes (introduction of N1456). The "unordered" in the name means the iteration order is not guaranteed, because a hash function does not define an order the way `map`'s `<` does (HOPL III §6.2). The proposal went through TR1 ([[N1836]]) into C++11 and became today's unordered associative containers ([[unord]]):

```cpp run title="unordered.cpp" ok
#include <string>
#include <unordered_map>

int main() {
    std::unordered_map<std::string, int> freq;
    for (const char* w : {"vector", "list", "vector"})
        ++freq[w];
    return freq["vector"] == 2 ? 0 : 1;
}
```

## Allocators: designed for segmented memory

Allocators are the part of the STL closest to the hardware of the time. 16-bit x86 used segmented memory, and a single program might have near, far and huge pointers at once, with different sizes and arithmetic rules. The committee wanted containers to be independent of such memory models, and Stepanov's solution was to encapsulate the memory model's information in an object:

> "I invented allocators to deal with Intel's memory architecture." (Stepanov, Lo Russo interview)

That is why allocators in the 1995 STL technical report had to define types such as `pointer`, `const_pointer`, `reference`, `size_type` and `difference_type`, and operations such as `address`, `allocate`, `deallocate` and `construct`, and every container was parameterized on an allocator (report §7; see also Halpern [[N1850]] §4.2).

The problem was that the language did not support this abstraction. `T&` and `T*` are hard-wired into the language, and users cannot define a type that behaves like a reference. Stepanov gave an example: two `vector<int>`s with different allocators; `b[1]` returns the second allocator's `reference` type, which is not necessarily `int&`, and handing it to a `find` running on the first container could cause a type mismatch (Lo Russo interview).

C++98's compromise was to allow implementations to ignore these features: an implementation may assume that allocators of the same type always compare equal, and that `pointer`, `size_type` and so on are `T*`, `size_t` and so on. So both the problem allocators were originally meant to solve (different pointer types) and the problem people later wanted them to solve (stateful memory pools) could go unsupported in C++98 (Halpern [[N1850]] §4.1).

C++11 rebuilt the allocator model around [[allocator.traits]] ([[N2982]]): a custom allocator only needs to provide a few members, `allocator_traits` fills in the rest, and stateful allocators got well-defined propagation rules. Since then `std::allocator` has been slimmed down step by step, with the redundant members deprecated in C++17 ([[P0174R2]]) and removed in C++20 ([[P0619R4]]).

<div class="compare" markdown="1">

```cpp title="std::allocator in C++98 (excerpt)"
template<class T> class allocator {
public:
  typedef T*        pointer;
  typedef const T*  const_pointer;
  typedef T&        reference;
  typedef const T&  const_reference;
  typedef size_t    size_type;
  typedef ptrdiff_t difference_type;
  template<class U> struct rebind {
    typedef allocator<U> other; };
  pointer address(reference x) const;
  pointer allocate(size_type n,
    allocator<void>::const_pointer = 0);
  void deallocate(pointer p, size_type n);
  size_type max_size() const;
  void construct(pointer p, const T& v);
  void destroy(pointer p);
};
```

```cpp title="std::allocator today (excerpt)"
template<class T> class allocator {
public:
  using value_type      = T;
  using size_type       = size_t;
  using difference_type = ptrdiff_t;
  constexpr T* allocate(size_t n);
  constexpr allocation_result<T*>
    allocate_at_least(size_t n);
  constexpr void deallocate(T* p, size_t n);
};
```

</div>

Both sides omit constructors and other members; the full definition today is in [[default.allocator]]. The type members on the left, along with `address`, `construct` and `destroy`, were there precisely to abstract away pointer and reference types. Today, an allocator usable with the standard containers needs only this much:

```cpp run title="minimal-allocator.cpp" ok
#include <cstddef>
#include <new>
#include <vector>

template<class T>
struct Mallocator {
    using value_type = T;
    Mallocator() = default;
    template<class U> constexpr Mallocator(const Mallocator<U>&) noexcept {}
    T* allocate(std::size_t n) {
        return static_cast<T*>(::operator new(n * sizeof(T)));
    }
    void deallocate(T* p, std::size_t) noexcept { ::operator delete(p); }
};
template<class T, class U>
bool operator==(const Mallocator<T>&, const Mallocator<U>&) { return true; }

int main() {
    std::vector<int, Mallocator<int>> v{1, 2, 3};   // the remaining members are filled in by allocator_traits
    v.push_back(4);
    return v.size() == 4 ? 0 : 1;
}
```

One allocator design problem remained unsolved: the allocator is part of the container's type, so `vector<int>`s with different allocators are different types. C++17's `std::pmr` dealt with this using run-time polymorphic memory resources; see [[history/modern-library]].

## Parameterizing on the character type: char_traits and locale

When standardization began, internationalization was one of the library working group's tasks, and one conclusion was that every facility that handles characters must take the character type as a template parameter (Myers 1995). Rewriting the existing iostreams and string as templates turned out to be harder than expected.

The difficulty was that besides the character itself there is a set of related types and values. The traditional `streambuf`, like C's stdio, represents end of file with an `EOF` distinct from every character, so functions that read characters return `int`. After templatization, besides the character type you also need an integer type that can hold EOF, and the value of EOF; making them all template parameters would force users to write a long list of parameters irrelevant to them every time. The traits approach collects information like `int_type` and `eof()` in one template parameterized on the character type; that is [[char.traits]].

So `basic_string`, `basic_istream` and `basic_ostream` all gained a `traits` parameter, defaulting to `char_traits<charT>`, and `string`, `istream` and `ostream` became aliases for the `char` specializations. One side effect of this design is that the comparison rules for characters can be replaced through the traits:

```cpp run title="ci-string.cpp" ok
#include <cassert>
#include <cctype>
#include <cstddef>
#include <string>

struct ci_traits : std::char_traits<char> {
    static bool eq(char a, char b) {
        return std::tolower((unsigned char)a) == std::tolower((unsigned char)b);
    }
    static bool lt(char a, char b) {
        return std::tolower((unsigned char)a) < std::tolower((unsigned char)b);
    }
    static int compare(const char* p, const char* q, std::size_t n) {
        for (; n; --n, ++p, ++q) {
            if (lt(*p, *q)) return -1;
            if (lt(*q, *p)) return 1;
        }
        return 0;
    }
};
using ci_string = std::basic_string<char, ci_traits>;

int main() {
    ci_string a = "STL", b = "stl";
    assert(a == b);          // the comparison rule comes from the traits, not from basic_string itself
}
```

Standard iostreams also depend on locales ([[localization]]): formatting and parsing of numbers is done through facets such as `num_put` and `num_get`. Locales were added to support languages other than English (HOPL III §6.1). Stroustrup does not think highly of this part: iostreams and locales suffered from the second-system effect, with the designers trying to satisfy every need and every existing practice at once (HOPL III §4.2). The formatting interface of iostreams did not change much for the next twenty years, until C++20's `std::format` and C++23's `std::print` ([[format]]).

## std::string and copy-on-write

The `basic_string` proposal predates the STL; after the STL was accepted, an iterator interface and container-style members were added, so it has several sets of member functions taking indices, iterators and C strings. HOPL III §4.2 says it exhibits several styles at once; Herb Sutter counted 103 member functions in `basic_string`, including constructors, 71 of which could have been non-members (GotW #84).

More consequential was that C++98 allowed **copy-on-write** (COW) implementations: copying a string only increments a reference count, and the real copy happens when a modification may occur. For this, C++98's reference invalidation rules had a special clause: the first call to non-const `operator[]`, `at`, `begin`, `end` and so on after construction may also invalidate existing references, pointers and iterators. A COW implementation has to unshare before handing out a writable reference.

Once multithreaded programs became common, this rule became a problem. Thread-safe COW requires atomic operations or locks on the reference count, a cost every user pays (Sutter, *Optimizations That Aren't (In a Multithreaded World)*, 1999). When C++11 introduced threads, [[N2668]] pointed out a more concrete headache: with a `vector`, you can assign to each element in parallel directly, but with a `basic_string` you had to call `s[0]` once single-threaded first, otherwise the first non-const access might invalidate references other threads had obtained.

N2668's change was to make no element access operation invalidate references, and it states explicitly that this effectively disallows COW implementations. The invalidation list in today's [[string.require#4]] is the amended version, and [[diff.cpp03.strings]] in Annex C records it as an incompatibility between C++03 and C++11:

```cpp run title="string-invalidation.cpp" ok
#include <cassert>
#include <string>

int main() {
    std::string s = "abc";
    const char* p = s.c_str();
    char& c = s[0];          // since C++11: non-const operator[] no longer invalidates references
    c = 'x';
    assert(p[0] == 'x');     // p is still valid and points to the same buffer
}
```

Under the C++03 rules, `s[0]` is the first non-const call after construction, and the standard allows it to invalidate `p`. Implementations took years to follow: because of ABI compatibility, GCC's libstdc++ only enabled the new non-COW `std::string` by default in GCC 5 (2015), and the old implementation can still be selected with `_GLIBCXX_USE_CXX11_ABI=0` (GCC 5 release notes). How ABI constrains the evolution of the standard library is covered in [[history/modern-library]].

## vector&lt;bool&gt;: a container that isn't one

C++98 specified a specialization of `vector<bool>` that stores elements as bits (today in [[vector.bool.pspc]]). A bit cannot be referred to, so its `reference` is a proxy class, while the container requirements say `reference` must be `T&`. The title of [[LWG96]], submitted in 1998, is *Vector&lt;bool&gt; is not a container*.

The problem shows most clearly in generic code. The function below works for every `T` except `bool`:

```cpp title="vector-bool-ref.cpp" error
#include <vector>

template<class T>
void first_ref(std::vector<T>& v) {
    T& r = v.front();        // works for every T except bool
    (void)r;
}

int main() {
    std::vector<int> vi{1};
    std::vector<bool> vb{true};
    first_ref(vi);           // OK
    first_ref(vb);           // error: bool& can't bind to a proxy object
}
```

Conversely, catching `vb[0]` with `auto` does not give you a copy of a `bool`, but a proxy that still refers to the container:

```cpp run title="vector-bool-proxy.cpp" ok
#include <cassert>
#include <type_traits>
#include <vector>

int main() {
    std::vector<bool> vb{true, false};
    auto x = vb[0];          // x is a vector<bool>::reference proxy
    static_assert(!std::is_same_v<decltype(x), bool>);
    vb[0] = false;
    assert(x == false);      // the change is visible through the proxy: x is not a copy
}
```

Over the next ten years, the committee discussed completing its specification, deprecating it, and providing the same functionality under another name (such as `bit_vector`), but none of these became a proposal that could be voted on ([[N1847]] and the discussion record of LWG96). In 2009 LWG closed the issue as NAD (Not A Defect), reasoning that the committee wanted to support proxy iterators, but that was separate work; every close modification anyone could think of would break existing code; and removing it was not feasible.

Howard Hinnant's later view was that a bit array is a fine data structure, both space-saving and potentially faster when implemented correctly; the mistake was naming it `vector<bool>` and making it pretend to be an array of `bool` (*On vector&lt;bool&gt;*, 2012). The proxy reference problem was later tackled head-on in ranges: C++20's iterator concepts allow proxy references, and C++23's `views::zip` is also designed around proxy tuples.

## auto_ptr: moving without move semantics

`auto_ptr` was C++98's only smart pointer, representing exclusive ownership. There were no rvalue references then, so it had to borrow copy syntax to transfer ownership: after `b = a`, `a` is null.

Returning an `auto_ptr` by value had another obstacle: the return value is a temporary, and a temporary cannot bind to the copy constructor's non-const reference parameter. The solution late in standardization was Colvin and Gibbons' helper class `auto_ptr_ref`: an rvalue is first turned into an `auto_ptr_ref` by a conversion function, then back into an `auto_ptr` by a constructor that accepts it (Gibbons, Colvin, *Fixing auto_ptr*, 1997).

```cpp title="Historical code: C++98 auto_ptr (deprecated in C++11, removed in C++17)"
#include <memory>

std::auto_ptr<int> source() { return std::auto_ptr<int>(new int(42)); }
void sink(std::auto_ptr<int> p) { }   // takes by value, acquiring ownership

int main()
{
    std::auto_ptr<int> a(new int(1));
    std::auto_ptr<int> b = a;    // looks like a copy, actually transfers ownership: a becomes null
    sink(source());              // the rvalue is passed in via auto_ptr_ref
}
```

This trick relies on very subtle corners of overload resolution, and it led to a core language issue ([[CWG84]]). The more fundamental problem is that generic code assumes the source and target are equal after a copy, and `auto_ptr` violates this (Hinnant [[N1856]]). With rvalue references in C++11, `unique_ptr` makes transfer explicit with `std::move`; `auto_ptr` was deprecated in C++11 and removed in C++17 ([[N4190]]). The story, with code comparing the two, is in [[history/modern-library]].

Today `auto_ptr` and `auto_ptr_ref` are listed in [[zombie.names]] as names reserved for previous standards: implementations may keep providing them for old code, and user code may not use them for anything else.

## valarray

`valarray` took a different path. It was proposed in 1993 with the goal of Fortran-like performance on vector processors, its design based mainly on experience at Sandia National Laboratories; at the same 1994 meeting where the STL was accepted, it was added to the draft with almost no discussion (Plauger, *C/C++ Users Journal*, August 1997).

To let compilers vectorize, its specification assumes these numeric arrays are free of certain forms of aliasing, and today's [[valarray.syn]] still says so. But it was not well regarded after standardization. In 2000 Nathan Myers said the library working group more or less regarded it as a failed experiment (libstdc++ mailing list). It is still in the standard ([[numarray]]); the standard library's new direction in numerics is C++23's `mdspan` and C++26's linear algebra interface.

## The three exception-safety guarantees

Exceptions and templates entered C++ at almost the same time, and the standard library was the first place to use both on a large scale. While writing the specification for the STL, the committee found it did not know how to describe the interaction between templates and exceptions; after studying it, Myers, Colvin, Abrahams and others concluded that the issue was the relationship between resources (more generally, invariants) and exceptions (HOPL III §5.3).

The three guarantees David Abrahams proposed in 1997 became the framework for describing the whole standard library:

- **The basic guarantee**: after an operation throws, invariants still hold and no resources leak;
- **The strong guarantee**: an operation either succeeds, or throws and leaves the state as it was before the operation;
- **The nothrow guarantee**: the operation does not throw.

Every standard library operation provides at least the basic guarantee (provided user destructors don't throw), and key operations provide the strong or nothrow guarantee. Today these guarantees are spread across the wording: [[res.on.exception.handling]] specifies when library functions may throw, [[string.require#2]] specifies that a throwing `basic_string` member has no other effects, and operations such as `vector::push_back` each specify their strong guarantee.

## Two fixes in C++03

C++03 was purely a corrective release; on the library side the most frequently mentioned change is [[LWG69]]: in 1998 Koenig asked whether the elements of a `vector` must be stored contiguously; the C++98 text did not require it, and C++03 made it explicit that they must be. From then on, `&v[0]` could be passed to C interfaces as a C array. Contiguous storage for `string` was only written into the standard in C++11 ([[LWG530]]).

## Traces in today's wording

| Today's wording | Origin |
|---|---|
| The *Cpp17* named requirements in [[iterator.cpp17]] alongside the concepts in [[iterator.concepts]] | The 1994 requirement tables, rewritten with concepts in C++20 |
| The tag classes in [[std.iterator.tags]], [[iterator.traits]] | Designed around 1995 for tag dispatch and traits |
| [[default.allocator]] has only `allocate`, `allocate_at_least` and `deallocate` left | Members designed for segmented memory were first allowed to be ignored, then deprecated and removed |
| [[allocator.traits]] still has `pointer`, `size_type`, `difference_type` | Entries from the 1994 allocator requirements table |
| The `traits` parameter of `basic_string<charT, traits, Allocator>` and `basic_ostream<charT, traits>` | Templatization of iostreams and string, 1994–1995 |
| The invalidation list in [[string.require#4]]; [[diff.cpp03.strings]] | C++11 ruling out copy-on-write implementations |
| The name `unordered_map` | Avoiding the mutually incompatible `hash_map`s implementations provided after C++98 |
| [[vector.bool]] does not meet the container requirements | Discussions from 1998–2009 found no change that wouldn't break old code |
| `auto_ptr` and `auto_ptr_ref` in [[zombie.names]] | Deprecated in C++11, removed in C++17 |

## Timeline

| Date | Event |
|---|---|
| 1984–1989 | Stream I/O library, complex number library; Cfront 2.0 brings Jerry Schwarz's rewritten iostreams |
| Late 1993 | Stepanov presents generic programming at a standards committee meeting |
| March 1994 | The STL proposal is presented in full to the committee |
| July 1994 | The STL, with about two thirds cut, adopted into the working draft; valarray added at the same meeting |
| 1995 | The traits technique published; partial specialization added to C++; hash table proposal misses C++98 |
| 1997 | The three exception-safety guarantees; `auto_ptr_ref` |
| 1998 | C++98; [[LWG96]] points out that `vector<bool>` is not a container |
| 2003 | C++03: `vector` must be stored contiguously |
| 2003–2005 | The unordered containers proposal [[N1456]] goes into the TR1 draft [[N1836]] |
| 2008–2009 | [[N2668]] rules out copy-on-write `string`; [[N2982]] establishes `allocator_traits`; LWG96 closed as NAD |
| 2011 | C++11: unordered containers, `unique_ptr`, `allocator_traits`; `auto_ptr` deprecated |
| 2015 | GCC 5 enables the non-COW `std::string` by default |
| 2017 | C++17: `auto_ptr` removed; redundant members of `std::allocator` deprecated; `pmr` introduced |
| 2020 | C++20: those redundant members removed; iterator concepts and ranges |

## References

- Bjarne Stroustrup. *A History of C++: 1979–1991*. HOPL II, 1993.
- Bjarne Stroustrup. *Evolving a language in and for the real world: C++ 1991–2006*. HOPL III, 2007. §4.1 (STL), §4.2 (other library components), §5.3 (exception safety), §6 (C++03 and the library technical report).
- Al Stevens. *Al Stevens Interviews Alex Stepanov*. *Dr. Dobb's Journal*, March 1995.
- Graziano Lo Russo. *An Interview with A. Stepanov* (reprinted at stepanovpapers.com).
- Alexander Stepanov, Meng Lee. *The Standard Template Library*. HP Labs technical report HPL-94-34, 1994; revised 1995.
- Nathan C. Myers. *Traits: a new and useful template technique*. *C++ Report*, June 1995.
- P. J. Plauger. *Standard C/C++: The Header &lt;valarray&gt;*. *C/C++ Users Journal*, August 1997.
- Pablo Halpern. *Towards a Better Allocator Model*. [[N1850]], 2005; [[N2982]].
- Matthew Austern. *A Proposal to Add Hash Tables to the Standard Library (revision 4)*. [[N1456]], 2003.
- A. Meredith et al. *Concurrency Modifications to Basic String*. [[N2668]], 2008.
- Herb Sutter. *Optimizations That Aren't (In a Multithreaded World)*. *C/C++ Users Journal*, June 1999; GotW #84; [[N1847]].
- Howard E. Hinnant. *On vector&lt;bool&gt;*, 2012; [[N1856]], 2005.
- Bill Gibbons, Greg Colvin. *Fixing auto_ptr*. J16/97-0090R1, 1997.
- [[LWG69]], [[LWG96]], [[LWG530]], [[CWG84]]; [[P0174R2]], [[P0619R4]], [[N4190]].
- GCC 5 Release Series: Changes, New Features, and Fixes (libstdc++ section).
