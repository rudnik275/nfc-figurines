#pragma once
#include <map>
#include <string>

// UID метки → номер статуэтки. UID считываются на стенде (nfc-bench.yaml),
// номер подписывается на основании статуэтки.
// Незнакомая метка уходит в Home Assistant как есть, по UID.
inline std::string figurine_id(const std::string &uid) {
  static const std::map<std::string, std::string> kFigurines = {
      // {"04-A1-B2-C3-D4-E5-F6", "figurka-1"},
  };
  auto it = kFigurines.find(uid);
  return it != kFigurines.end() ? it->second : uid;
}
