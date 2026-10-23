#!/usr/bin/env python3
"""Generate timezones.h and the "Time zone" dropdown options for matrix-clock.yaml.

The clock can't parse time zone names at runtime (ESPHome pre-parses them at
build time), so this script turns a list of IANA zones into ready-made
ParsedTimezone structs, using the same tz database and parser ESPHome uses.

It also builds the table that "Auto (from Weather ZIP)" uses: every US time
zone name the geocoder can return, mapped to the matching dropdown entry.

Run from the repo root with ESPHome's Python, after editing ZONES below:

    .venv/bin/python tools/gen_timezones.py

It rewrites timezones.h and the options between the "BEGIN/END timezones"
markers in matrix-clock.yaml.
"""
from __future__ import annotations

import pathlib
import re
import sys

from aioesphomeapi.posix_tz import DSTRuleType, parse_posix_tz
from esphome.components.time import _extract_tz_string, _load_tzdata

AUTO_LABEL = "Auto (from Weather ZIP)"

# (dropdown label, IANA zone). Order = order in the dropdown.
ZONES: list[tuple[str, str]] = [
    ("US Eastern (New York)", "America/New_York"),
    ("US Central (Chicago)", "America/Chicago"),
    ("US Mountain (Denver)", "America/Denver"),
    ("US Arizona (Phoenix)", "America/Phoenix"),
    ("US Pacific (Los Angeles)", "America/Los_Angeles"),
    ("US Alaska (Anchorage)", "America/Anchorage"),
    ("US Aleutian (Adak)", "America/Adak"),
    ("US Hawaii (Honolulu)", "Pacific/Honolulu"),
    ("Puerto Rico", "America/Puerto_Rico"),
    ("Canada Atlantic (Halifax)", "America/Halifax"),
    ("Canada Newfoundland", "America/St_Johns"),
    ("Mexico (Mexico City)", "America/Mexico_City"),
    ("Colombia / Peru (Bogota)", "America/Bogota"),
    ("Chile (Santiago)", "America/Santiago"),
    ("Argentina (Buenos Aires)", "America/Argentina/Buenos_Aires"),
    ("Brazil (Sao Paulo)", "America/Sao_Paulo"),
    ("UTC", "Etc/UTC"),
    ("UK (London)", "Europe/London"),
    ("Central Europe (Paris, Berlin)", "Europe/Paris"),
    ("Eastern Europe (Athens)", "Europe/Athens"),
    ("Turkey (Istanbul)", "Europe/Istanbul"),
    ("Russia (Moscow)", "Europe/Moscow"),
    ("West Africa (Lagos)", "Africa/Lagos"),
    ("South Africa (Johannesburg)", "Africa/Johannesburg"),
    ("Egypt (Cairo)", "Africa/Cairo"),
    ("East Africa (Nairobi)", "Africa/Nairobi"),
    ("Israel (Jerusalem)", "Asia/Jerusalem"),
    ("Gulf (Dubai)", "Asia/Dubai"),
    ("Iran (Tehran)", "Asia/Tehran"),
    ("Pakistan (Karachi)", "Asia/Karachi"),
    ("India", "Asia/Kolkata"),
    ("Nepal", "Asia/Kathmandu"),
    ("Bangladesh (Dhaka)", "Asia/Dhaka"),
    ("Thailand / Vietnam (Bangkok)", "Asia/Bangkok"),
    ("China / Singapore / HK", "Asia/Shanghai"),
    ("Japan / Korea (Tokyo)", "Asia/Tokyo"),
    ("Australia West (Perth)", "Australia/Perth"),
    ("Australia Central (Adelaide)", "Australia/Adelaide"),
    ("Australia Queensland (Brisbane)", "Australia/Brisbane"),
    ("Australia East (Sydney)", "Australia/Sydney"),
    ("New Zealand (Auckland)", "Pacific/Auckland"),
]

# Every US time zone name (tzdata zone.tab / zone1970.tab, country US or PR).
# The weather geocoder is limited to US ZIP codes, so these are all the names
# Auto mode can receive. Each must match a ZONES entry's rules exactly.
US_ZONES = [
    "America/New_York", "America/Detroit", "America/Kentucky/Louisville",
    "America/Kentucky/Monticello", "America/Indiana/Indianapolis",
    "America/Indiana/Vincennes", "America/Indiana/Winamac",
    "America/Indiana/Marengo", "America/Indiana/Petersburg",
    "America/Indiana/Vevay", "America/Chicago", "America/Indiana/Tell_City",
    "America/Indiana/Knox", "America/Menominee", "America/North_Dakota/Center",
    "America/North_Dakota/New_Salem", "America/North_Dakota/Beulah",
    "America/Denver", "America/Boise", "America/Phoenix", "America/Los_Angeles",
    "America/Anchorage", "America/Juneau", "America/Sitka",
    "America/Metlakatla", "America/Yakutat", "America/Nome", "America/Adak",
    "Pacific/Honolulu", "America/Puerto_Rico",
]

TYPE_CPP = {
    DSTRuleType.NONE: "esphome::time::DSTRuleType::NONE",
    DSTRuleType.MONTH_WEEK_DAY: "esphome::time::DSTRuleType::MONTH_WEEK_DAY",
    DSTRuleType.JULIAN_NO_LEAP: "esphome::time::DSTRuleType::JULIAN_NO_LEAP",
    DSTRuleType.DAY_OF_YEAR: "esphome::time::DSTRuleType::DAY_OF_YEAR",
}


def posix_for(iana: str) -> str:
    data = _load_tzdata(iana)
    if data is None:
        sys.exit(f"Unknown time zone: {iana}")
    return _extract_tz_string(data)


def rule_cpp(r) -> str:
    return (f"{{{r.time_seconds}, {r.day}, {TYPE_CPP[r.type]}, "
            f"{r.month}, {r.week}, {r.day_of_week}}}")


def main() -> None:
    root = pathlib.Path(__file__).resolve().parent.parent
    labels = [label for label, _ in ZONES]
    assert len(set(labels)) == len(labels), "duplicate labels"
    assert AUTO_LABEL not in labels

    posix = {iana: posix_for(iana) for _, iana in ZONES}

    # IANA name -> index into ZONES, for Auto mode.
    alias: dict[str, int] = {iana: i for i, (_, iana) in enumerate(ZONES)}
    for name in US_ZONES:
        if name in alias:
            continue
        p = posix_for(name)
        matches = [i for i, (_, iana) in enumerate(ZONES) if posix[iana] == p]
        if not matches:
            sys.exit(f"{name} ({p}) matches no dropdown entry; add one to ZONES")
        alias[name] = matches[0]

    out = [
        "// GENERATED by tools/gen_timezones.py - do not edit by hand.",
        "#pragma once",
        '#include "esphome/core/defines.h"',
        '#include "esphome/components/time/posix_tz.h"',
        "#include <cstring>",
        "",
        "namespace tzc {",
        "",
        "struct Zone {",
        "  const char *label;",
        "  const char *iana;",
        "  const char *posix;",
        "  esphome::time::ParsedTimezone tz;",
        "};",
        "",
        f'static const char *const AUTO_LABEL = "{AUTO_LABEL}";',
        "",
        "// Dropdown option i+1 (option 0 is Auto) is ZONES[i].",
        "static const Zone ZONES[] = {",
    ]
    for label, iana in ZONES:
        t = parse_posix_tz(posix[iana])
        out.append(
            f'    {{"{label}", "{iana}", "{posix[iana]}", '
            f"{{{t.std_offset_seconds}, {t.dst_offset_seconds}, "
            f"{rule_cpp(t.dst_start)}, {rule_cpp(t.dst_end)}}}}},")
    out += [
        "};",
        "static const int ZONE_COUNT = sizeof(ZONES) / sizeof(ZONES[0]);",
        "",
        "struct Alias {",
        "  const char *iana;",
        "  int zone;",
        "};",
        "",
        "// IANA names the weather geocoder can return -> ZONES index.",
        "static const Alias ALIASES[] = {",
    ]
    for name, idx in sorted(alias.items()):
        out.append(f'    {{"{name}", {idx}}},  // {ZONES[idx][0]}')
    out += [
        "};",
        "static const int ALIAS_COUNT = sizeof(ALIASES) / sizeof(ALIASES[0]);",
        "",
        "/// ZONES index for an IANA name, or -1 if it isn't in the table.",
        "inline int find_iana(const char *name) {",
        "  if (name == nullptr) return -1;",
        "  for (int i = 0; i < ALIAS_COUNT; i++)",
        "    if (std::strcmp(ALIASES[i].iana, name) == 0) return ALIASES[i].zone;",
        "  return -1;",
        "}",
        "",
        "/// Make ZONES[i] the clock's time zone. Returns false if i is out of range.",
        "inline bool apply(int i) {",
        "  if (i < 0 || i >= ZONE_COUNT) return false;",
        "  esphome::time::set_global_tz(ZONES[i].tz);",
        "  return true;",
        "}",
        "",
        "}  // namespace tzc",
        "",
    ]
    (root / "timezones.h").write_text("\n".join(out))

    # Rewrite the dropdown options in matrix-clock.yaml between the markers.
    yaml_path = root / "matrix-clock.yaml"
    y = yaml_path.read_text()
    begin = "      # BEGIN timezones (generated by tools/gen_timezones.py)\n"
    end = "      # END timezones\n"
    opts = "".join(f'      - "{lab}"\n' for lab in [AUTO_LABEL] + labels)
    pat = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
    if not pat.search(y):
        sys.exit("timezone markers not found in matrix-clock.yaml")
    yaml_path.write_text(pat.sub(lambda _: begin + opts + end, y))
    print(f"timezones.h: {len(ZONES)} zones, {len(alias)} names for Auto")


if __name__ == "__main__":
    main()
