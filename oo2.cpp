#include <locale>
#include <cctype>
#include <algorithm>
#include <string>
void a() {
  std::string s = "abc";
  std::transform(s.begin(), s.end(), s.begin(), std::toupper); // ?
}
