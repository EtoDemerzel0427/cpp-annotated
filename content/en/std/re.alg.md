---
title: "Regex matching: results, algorithms and iterators"
summary: "The match results sub_match and match_results hold only iterators into the original sequence; the difference between regex_match and regex_search and the state after a failure; regex_replace's format rules; how regex_iterator handles zero-length matches; and the rvalue overloads deleted to prevent dangling, with the cases they cannot catch."
updated: 2026-10-19
---

!!! tldr
    - Match results own no characters; they hold only iterators into the sequence searched. Once the searched string is destroyed or modified, the results are invalid.
    - A default-constructed `match_results` is not yet ready, and calling `operator[]`, `str()` and similar members on it is UB; they can be called after one match attempt, successful or not.
    - `regex_match` requires the whole sequence to match; `regex_search` finds the leftmost match.
    - `regex_iterator` guarantees progress on zero-length matches; index -1 of `regex_token_iterator` yields the parts between matches, which can be used to split strings.
    - The standard deletes the overloads that take an rvalue `std::string` as the target, but dangling via `c_str()` gets through.

This page is the second half of [[re]]: what you get after matching with a regular expression.

## An example

```cpp run title="match-results.cpp" ok
#include <cassert>
#include <regex>
#include <string>

int main() {
  std::regex date(R"((\d{4})-(\d{2})(?:-(\d{2}))?)");
  std::smatch sm;
  std::string s = "on 2024-07 ok";
  assert(std::regex_search(s, sm, date));
  assert(sm.size() == 4);              // 1 + mark_count(); (?:...) does not count
  assert(sm[1] == "2024" && sm[2] == "07");
  assert(!sm[3].matched && sm[3].first == s.end());  // did not participate in the match
  assert(sm[99].matched == false);     // out-of-range index: returns an unmatched sub_match
  assert(sm.prefix() == "on " && sm.suffix() == " ok");
  assert(sm.position(1) == 3);
  assert(sm.format("$2/$1") == "07/2024");
  assert(std::regex_replace(s, date, "[$&]") == "on [2024-07] ok");
}
```

Each item in `sm` is a pair of iterators into `s`. `sm[1] == "2024"` holds because the characters are copied out only at comparison time. The rules for each of these members follow.

## sub_match: a pair of iterators ([re.submatch])

[re.submatch.general] ¶1 A `sub_match` represents the character sequence matched by a marked subexpression. It derives publicly from `pair<BidirectionalIterator, BidirectionalIterator>` and adds a `bool matched` member:

- `first`, `second`: the matched range `[first, second)`;
- `matched`: whether this subexpression participated in the match;
- `length()` ([re.submatch.members] ¶2): `distance(first, second)` if `matched`, otherwise 0;
- `str()` and `operator string_type()` (¶3–¶4): copy out a `basic_string` if `matched`, otherwise return an empty string;
- `compare(...)` (¶5–¶7): all defined as `str().compare(...)`.

[re.submatch.op] provides `==` and `<=>` between `sub_match` and `sub_match`, `basic_string`, character pointers and single characters, comparing contents. So you can write `sm[1] == "2024"` directly.

## match_results ([re.results])

### The ready state ([re.results.general] ¶3)

¶1–¶2 `match_results` is a collection of `sub_match`es that meets the requirements of an allocator-aware container ([[container.alloc.reqmts]]) and of a sequence container, except that only copy, move assignment and const operations are supported.

¶3 A default-constructed `match_results` does not yet have a full result state. It becomes [[g:ready-match-results|ready]] only once a match has completed and modified it:

!!! std
    The effects of calling most member functions from a match_results object that is not ready are undefined.

Specifically, `length`, `position`, `str`, `operator[]`, `prefix`, `suffix` and `format` all have `ready() == true` as a precondition ([re.results.acc], [re.results.form]). `size()`, `empty()` and `ready()` have no such restriction, and a default-constructed object has `size()` 0 ([re.results.const] ¶3).

### Index 0 and subexpressions that did not participate (¶4)

- `m[0]` represents the whole match, and `m[0].matched` is always true.
- `m[n]` represents the `n`th marked subexpression. If it participated in the match, `matched` is true and `[first, second)` is the matched range; otherwise `matched` is false and `first` and `second` both point to the end of the searched sequence. The optional third group in the example at the top is such a case.
- Note 1: several subexpressions that did not participate need not have distinct `sub_match` objects.

[re.results.acc] ¶8 says that when `n >= size()`, `operator[]` returns a `sub_match` representing an unmatched subexpression. So an out-of-range index is not UB, unlike ordinary containers.

### Size and access ([re.results.size], [re.results.acc])

- `size()` ([re.results.size] ¶1): `1 + mark_count()` after a successful match, otherwise 0. Note 1 says the state of a `match_results` can be changed only by passing it to `regex_match` or `regex_search`.
- `position(n)` ([re.results.acc] ¶4): the distance from the start of the target sequence to `(*this)[n].first`. `regex_iterator` redefines what the start of the target sequence means; see below.
- `prefix()`, `suffix()` (¶10, ¶12): the parts before and after the match.

### Formatting ([re.results.form])

¶1–¶3 `format(out, fmt_first, fmt_last, flags)` copies the format string to the output, replacing format specifiers in it with the corresponding submatches. By default (`format_default`) it uses the rules of ECMAScript `replace`: `$&` is the whole match, `$n` and `$nn` are the nth submatch, `` $` `` is the prefix, `$'` is the suffix, and `$$` is a literal `$`. With `format_sed` set it uses sed's rules instead (`&`, `\n`). ¶5–¶10 are the overloads returning `basic_string`.

### Copying, comparison, swap

- Table 122 ([re.results.const]): after copying or moving, `ready()`, `size()`, `str(n)`, `prefix()`, `suffix()`, `(*this)[n]`, `length(n)` and `position(n)` are all the same as in the source. The copied `sub_match`es still point into the original character sequence.
- [re.results.nonmember] ¶1 `operator==`: equal if neither is ready; unequal if one is ready and the other is not; if both are ready, equal if both are empty, and if both are non-empty, compares the contents of `prefix`, every submatch and `suffix` in turn.
- `swap` is a constant-time operation ([re.results.swap]).

## Algorithms ([re.alg])

### regex_match and regex_search

| Call (`re` is `"Get|GetValue"`) | Result | `m[0]` |
|---|---|---|
| `regex_search("GetValue", m, re)` | true | `"Get"` |
| `regex_match("GetValue", m, re)` | true | `"GetValue"` |
| `regex_search("GetValues", m, re)` | true | `"Get"` |
| `regex_match("GetValues", m, re)` | false | — |

This table comes from Example 1 in [re.alg.match].

[re.alg.match] ¶1 The iterators must satisfy `bidirectional_iterator`. ¶2 `regex_match` determines whether the regular expression matches the whole of `[first, last)`, considering only matches that cover the whole sequence. That is why the second row goes on to try `GetValue` after `Get` fails.

[re.alg.search] ¶2 `regex_search` determines whether some subsequence of `[first, last)` matches. Under ECMAScript semantics, the leftmost match is found; at that position the first successful alternative is taken, whereas the POSIX grammars take the longest.

¶3 of both functions says that after the call, `m.ready()` is true whether or not the match succeeded. On failure, the state of `m` other than `size() == 0` and `empty() == true` is unspecified. On success:

- `regex_match` (Table 123): `m.size()` is `1 + e.mark_count()`, `m[0]` is `[first, last)`, `prefix()` is the empty range `[first, first)` and `suffix()` is `[last, last)`;
- `regex_search` (Table 124): `prefix()` is `[first, m[0].first)` and `suffix()` is `[m[0].second, last)`.

The other overloads ([re.alg.match] ¶4–¶8, [re.alg.search] ¶4–¶8) all forward to the iterator versions. The versions without a `match_results` construct a temporary `match_results` internally and return only a `bool`.

### regex_replace ([re.alg.replace])

¶1 `regex_replace` constructs a `regex_iterator` to go through all matches. For each match, it first outputs the match's prefix (not if `format_no_copy` is set), then `m.format(fmt, flags)`. Finally it outputs the remainder after the last match (also governed by `format_no_copy`). With `format_first_only`, only the first match is replaced. If there are no matches at all, the whole input is copied to the output unchanged. ¶3–¶6 are the overloads returning `basic_string`.

### Only two kinds of exceptions ([re.except])

```cpp run title="regex-complexity.cpp" ok
#include <cassert>
#include <regex>
#include <string>

int main() {
  std::regex re("(a*)*c");          // nested quantifiers: catastrophic backtracking
  std::string s(26, 'a');
  try {
    std::regex_match(s + "b", re);
  } catch (const std::regex_error& e) {
    assert(e.code() == std::regex_constants::error_complexity ||
           e.code() == std::regex_constants::error_stack);
  }
}
```

¶1 The algorithms in this subclause may throw `regex_error`, but its `code()` can only be `error_complexity` or `error_stack`. That is, a match that is too complex or runs out of stack should be reported by an exception rather than a crash, provided the implementation detects these situations. libc++ in our tests throws `error_complexity` in the example above; the standard does not require a throw, and another implementation might just run for a long time.

## Iterators ([re.iter])

```cpp run title="regex-iterators.cpp" ok
#include <cassert>
#include <regex>
#include <string>
#include <vector>

int main() {
  std::string s = "a,b,,c";
  std::regex sep(",");
  std::vector<std::string> v(
      std::sregex_token_iterator(s.begin(), s.end(), sep, -1), {});
  assert((v == std::vector<std::string>{"a", "b", "", "c"}));  // -1: the parts between matches

  std::string t = "ab";
  std::regex empty("x*");
  int n = 0;
  for (std::sregex_iterator it(t.begin(), t.end(), empty), end; it != end; ++it)
    ++n;
  assert(n == 3);   // one zero-length match at each of positions 0, 1, 2
}
```

### regex_iterator ([re.regiter])

[re.regiter.general] ¶1 `regex_iterator` is an iterator adaptor that uses `regex_search` to find all the matches in a sequence in turn. Each `++` finds the next match and stores it in an internal `match_results`, and dereferencing yields a `const match_results&`. A default-constructed one is the end-of-sequence iterator. Two non-end iterators are equal when constructed from the same arguments.

The iterator stores a pointer to the regex ([re.regiter.cnstr] ¶2 sets `pregex` to `addressof(re)`), so the regex must outlive the iterator.

¶2 If `match[0].matched` is true and `match[0].first == match[0].second`, the iterator holds a [[g:zero-length-match|zero-length match]]. This happens when the pattern consists only of assertions like `^`, `$` and `\b`, or when `x*` matches at a position containing no `x`.

`operator++` as specified in [re.regiter.incr] guarantees progress at every step:

1. ¶1 Continue from `start = match[0].second`.
2. ¶2 If the current match is zero-length and `start == end`, the iterator becomes the end-of-sequence iterator.
3. ¶3 If the current match is zero-length, first try again at `start` with `match_not_null | match_continuous` added, that is, look for a non-empty match starting at the same position. If that fails, advance `start` by one and proceed with the next step.
4. ¶4 In the ordinary case, search with `match_prev_avail` added. That way `^` does not falsely match at the position where the last match ended, and `\b` can see the previous character.

¶5–¶6 After each success, `match.prefix().first` equals the previous `match[0].second`, and `match.position(i)` is the offset from the original `begin`, not from the start of this search. ¶7 How an implementation achieves this is unspecified; Note 2 says an implementation may call its own internal search function, so a specialization of `regex_search` provided by the program is not necessarily called.

### regex_token_iterator ([re.tokiter])

`regex_token_iterator` is built on `regex_iterator` and yields `sub_match`es according to a given list of submatch indices. An index `n >= 0` takes the `n`th submatch of each match; index -1 takes the parts between matches, which is the standard way to split a string with a regular expression. If characters remain after the last match, -1 also yields them as the last token.

## Dangling: the deleted overloads and what they cannot catch

`match_results` stores only iterators, so using a temporary `std::string` as the search target and reading the results afterwards dangles ([[class.temporary]]). [re.syn] deletes two sets of overloads for this reason:

- the versions of `regex_match` and `regex_search` that take a `const basic_string&&` target together with a `match_results&`;
- the constructors of `regex_iterator` and `regex_token_iterator` taking a `const regex_type&&`, since the iterators store the regex's address.

```cpp title="deleted-overloads.cpp" error
#include <regex>
#include <string>
std::string get() { return "key=value"; }
int main() {
  std::regex re("(\\w+)=(\\w+)");
  std::smatch m;
  std::regex_search(get(), m, re);   // error: call to deleted function
  std::string s = get();
  std::sregex_iterator it(s.begin(), s.end(),
                          std::regex("x"));   // error: call to deleted constructor
}
```

`regex_search(get(), re)` without a `match_results` is still valid; it returns only a `bool` and cannot dangle. But the deleted overloads recognize only `basic_string` rvalues and cannot catch cases that go through a pointer:

```cpp run title="dangling-cmatch.cpp" ub
#include <iostream>
#include <regex>
#include <string>

std::string load() {
  return "user=alice; a long enough line to defeat SSO";
}

int main() {
  std::regex re(R"((\w+)=(\w+))");
  std::cmatch m;
  std::regex_search(load().c_str(), m, re);  // the const char* overload is not deleted
  // the full-expression has ended; the temporary string is destroyed
  std::cout << m[2] << '\n';                 // UB: the pointers in m dangle
}
```

Run with `-fsanitize=address` in our tests, this reports heap-use-after-free. Likewise, destroying the string a `std::string_view` points to, or modifying a `std::string` after matching (which may reallocate), invalidates existing `match_results`.

## Questions

!!! question "Question 1"
    For a freshly default-constructed `std::smatch m;`, are `m.size()`, `m.empty()` and `m[0]` each valid? What about after a failed match?

<details markdown="1">
<summary>Answer</summary>

`m.size()` (returning 0) and `m.empty()` (returning true) are valid; they have no `ready()` precondition ([re.results.size], [re.results.const] ¶3). `m[0]` is UB: [re.results.acc] ¶7 requires `ready() == true`, and a default-constructed object is not ready ([re.results.general] ¶3).

After a failed match, `m` is ready ([re.alg.match] ¶3) and `size()` is 0. `m[0]` then satisfies `0 >= size()` and, per [re.results.acc] ¶8, returns an unmatched `sub_match`, which is valid.
</details>

!!! question "Question 2"
    When iterating with `sregex_iterator`, what is `it->position(0)` an offset from?

<details markdown="1">
<summary>Answer</summary>

From the `begin` passed when the iterator was constructed, not from the start of the current `regex_search` ([re.regiter.incr] ¶5–¶6). The implementation must adjust the `match_results` so that `position` reflects the position in the whole target sequence, and `prefix().first` must equal the previous match's `match[0].second`.
</details>

## Summary

| Point | Source |
|---|---|
| A `sub_match` is a pair of iterators plus `matched`, owning no characters | [re.submatch.general] |
| Calling most members on a `match_results` that is not ready is UB | [re.results.general] ¶3 |
| A subexpression that did not participate: `matched` is false, iterators point to the end of the sequence | [re.results.general] ¶4 |
| An out-of-range `operator[]` returns an unmatched `sub_match` | [re.results.acc] ¶8 |
| The algorithms throw only `error_complexity` or `error_stack` | [re.except] ¶1 |
| `regex_match` requires covering the whole sequence; `regex_search` finds the leftmost match | [re.alg.match] ¶2, [re.alg.search] ¶2 |
| On a zero-length match, first try a non-empty match at the same position, then advance by one | [re.regiter.incr] ¶3 |
| Overloads taking rvalue `basic_string` and rvalue regex are deleted, but `c_str()` dangling gets through | [re.syn] |
