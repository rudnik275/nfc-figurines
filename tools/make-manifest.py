"""Манифест обновления для подставок: figurki.manifest.json + figurki.ota.bin в одну папку.

    python3 tools/make-manifest.py --tag v0.8 --bin esphome/.esphome/build/figurki/build/firmware.ota.bin --out dist

Подставка читает манифест с GitHub Pages (update: http_request в esphome/figurki.yaml),
сравнивает version со своей esphome.project.version и скачивает прошивку по path —
относительно адреса манифеста. Запускает CI (.github/workflows/firmware.yml).
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
YAML = ROOT / "esphome" / "figurki.yaml"
BIN = "figurki.ota.bin"
MANIFEST = "figurki.manifest.json"


def project_version() -> str:
    # Единственный ключ version в figurki.yaml — esphome.project.version.
    found = re.findall(r'^\s+version:\s*"([^"]+)"', YAML.read_text(), re.M)
    if len(found) != 1:
        sys.exit(f"{YAML.name}: ожидался один version, найдено {len(found)}")
    return found[0]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tag", help="тег релиза, должен быть v<version>")
    p.add_argument("--bin", required=True, type=Path, help="firmware.ota.bin из сборки ESPHome")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--release-url", default="")
    p.add_argument("--summary", default="")
    a = p.parse_args()

    version = project_version()
    if a.tag is not None and a.tag != f"v{version}":
        sys.exit(f"Тег {a.tag}, а в {YAML.name} version {version}: поправь одно из двух")

    a.out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(a.bin, a.out / BIN)
    ota = {"path": BIN, "md5": hashlib.md5((a.out / BIN).read_bytes()).hexdigest()}
    if a.release_url:
        ota["release_url"] = a.release_url
    if a.summary:
        ota["summary"] = a.summary
    manifest = {
        "name": "Статуэтки",
        "version": version,
        # chipFamily сверяется с ESPHOME_VARIANT прошивки: esp32dev → ESP32.
        "builds": [{"chipFamily": "ESP32", "ota": ota}],
    }
    (a.out / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(f"{MANIFEST}: {version}, md5 {ota['md5']}, {(a.out / BIN).stat().st_size} байт")


if __name__ == "__main__":
    main()
