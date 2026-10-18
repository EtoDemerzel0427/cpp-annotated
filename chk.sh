#!/bin/zsh
# usage: chk.sh file...  ; prints result and first errors
for f in "$@"; do
  out=$(clang++ -std=c++2c -Wall -Wextra -pedantic -fsyntax-only $f 2>&1)
  if [ $? -eq 0 ]; then echo "== $f: OK"; else echo "== $f: FAIL"; fi
  echo "$out" | grep -E "error|warning" | head -6
done
