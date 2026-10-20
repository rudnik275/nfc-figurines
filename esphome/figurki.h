#pragma once
#include <map>
#include <string>

// UID метки → номер статуэтки. UID считываются на стенде (nfc-bench.yaml),
// номер подписывается на основании статуэтки.
// Незнакомая метка уходит в Home Assistant как есть, по UID.
inline std::string figurine_id(const std::string &uid) {
  static const std::map<std::string, std::string> kFigurines = {
      {"04-EA-97-6E-D1-2A-81", "figurka-1"},
      {"04-5C-D3-77-D5-2A-81", "figurka-2"},
      {"04-49-9D-60-D1-2A-81", "figurka-3"},
      {"04-9D-6A-67-D2-2A-81", "figurka-4"},
      {"04-A8-AE-65-D2-2A-81", "figurka-5"},
      {"04-72-F4-6F-D1-2A-81", "figurka-6"},
      {"04-CD-EA-6E-D1-2A-81", "figurka-7"},
      {"04-9D-1B-75-D4-2A-81", "figurka-8"},
      {"04-96-C7-60-D1-2A-81", "figurka-9"},
      {"04-68-AA-66-D2-2A-81", "figurka-10"},
  };
  auto it = kFigurines.find(uid);
  return it != kFigurines.end() ? it->second : uid;
}
