#pragma once
// Версии прошивки вида «0.8», «0.8.1» — esphome.project.version и version в манифесте.
// ESPHome считает обновлением любую другую строку, в том числе старую версию. Сама
// подставка ставит только версию новее своей: собранная на стенде 0.9 не откатится
// на опубликованную 0.8. Чистый C++, тесты — tests/firmware_version_test.cpp.
#include <string>

// Часть номер index версии как число; хвост после цифр и точек («-dev») отбрасывается,
// недостающие части — 0.
inline int version_part(const std::string &v, int index) {
  size_t end = v.find_first_not_of("0123456789.");
  if (end == std::string::npos) end = v.size();
  size_t pos = 0;
  for (int i = 0; i < index; i++) {
    pos = v.find('.', pos);
    if (pos == std::string::npos || pos >= end) return 0;
    pos++;
  }
  int n = 0;
  while (pos < end && v[pos] != '.') n = n * 10 + (v[pos++] - '0');
  return n;
}

// true, если версия a новее b.
inline bool version_newer(const std::string &a, const std::string &b) {
  for (int i = 0; i < 4; i++) {
    int x = version_part(a, i), y = version_part(b, i);
    if (x != y) return x > y;
  }
  return false;
}
