#!/usr/bin/env python3
# Copyright (c) 2026 ETH Zurich and University of Bologna.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

"""Validate the print_config Verilator log against generated project config."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CROC_PKG = ROOT / "rtl" / "croc_pkg.sv"
USER_ROM = ROOT / "rtl" / "user_domain" / "user_rom.sv"
CONFIG_H = ROOT / "sw" / "config.h"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sv_int(value: str) -> int:
    value = re.sub(r"/\*.*?\*/", "", value, flags=re.DOTALL)
    value = re.sub(r"//.*", "", value)
    value = value.strip().replace("_", "")
    sized = re.fullmatch(r"(?:\d+)'([hdob])([0-9a-fA-F_xzXZ]+)", value)
    if sized:
        base = {"h": 16, "d": 10, "o": 8, "b": 2}[sized.group(1).lower()]
        return int(sized.group(2), base)
    if value.lower().startswith("0x"):
        return int(value, 16)
    return int(value, 10)


def extract(pattern: str, text: str, path: Path) -> str:
    match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    if not match:
        raise SystemExit(f"error: could not match {pattern!r} in {path}")
    return match.group(1)


def extract_pkg_config() -> dict[str, int]:
    text = read_text(CROC_PKG)
    return {
        "version": sv_int(extract(r"version:\s*([^,\n}]+)", text, CROC_PKG)),
        "idma": sv_int(extract(r"localparam\s+bit\s+iDMAEnable\s*=\s*([^;]+)", text, CROC_PKG)),
        "pmp": sv_int(extract(r"localparam\s+bit\s+CorePMPEnable\s*=\s*([^;]+)", text, CROC_PKG)),
        "core_id": sv_int(extract(r"localparam\s+int\s+unsigned\s+CoreId\s*=\s*([^;]+)", text, CROC_PKG)),
        "sram_banks": sv_int(extract(r"localparam\s+int\s+unsigned\s+NumSramBanks\s*=\s*([^;]+)", text, CROC_PKG)),
        "sram_words": sv_int(extract(r"localparam\s+int\s+unsigned\s+SramBankNumWords\s*=\s*([^;]+)", text, CROC_PKG)),
    }


def extract_config_h_defines() -> dict[str, int]:
    defines: dict[str, int] = {}
    for line in read_text(CONFIG_H).splitlines():
        match = re.match(r"#define\s+([A-Z0-9_]+)\s+(.+?)\s*(?://.*)?$", line)
        if not match:
            continue
        name, raw_value = match.groups()
        raw_value = raw_value.strip()
        try:
            defines[name] = sv_int(raw_value)
        except ValueError:
            continue
    return defines


def extract_user_rom_string() -> str:
    text = read_text(USER_ROM)
    rom_body = extract(r"RomWords\s*\[[^\]]+\]\s*=\s*'\{(.*?)\};", text, USER_ROM)
    chars: list[str] = []
    for word_text in re.findall(r"32'h([0-9A-Fa-f_]+)", rom_body):
        word = int(word_text.replace("_", ""), 16)
        for shift in range(0, 32, 8):
            byte = (word >> shift) & 0xFF
            if byte == 0:
                return "".join(chars)
            chars.append(chr(byte))
    return "".join(chars)


def expected_info_word(config: dict[str, int]) -> int:
    return (
        ((config["version"] & 0xF) << 28)
        | ((config["idma"] & 0x1) << 27)
        | ((config["core_id"] & 0x7) << 21)
        | ((config["pmp"] & 0x1) << 20)
        | ((config["sram_banks"] & 0x7) << 13)
        | (((config["sram_words"] // 64) & 0xFF) << 5)
    )


def core_name(core_id: int) -> str:
    return {0: "CVE2", 1: "Ibex", 7: "custom"}.get(core_id, "unknown")


def add_check(failures: list[str], log: str, pattern: str, hint: str) -> None:
    if not re.search(pattern, log):
        failures.append(f"Pattern not found: {pattern}\n  Hint: {hint}")


def peripheral_expectations(defines: dict[str, int], idma_enabled: int) -> list[tuple[str, int, str]]:
    return [
        ("Debug", defines["DEBUG_BASE_ADDR"], "present"),
        ("Bootrom", defines["BOOTROM_BASE_ADDR"], "present"),
        ("CLINT", defines["CLINT_BASE_ADDR"], "present"),
        ("SoC Ctrl", defines["SOCCTRL_BASE_ADDR"], "present"),
        ("UART", defines["UART_BASE_ADDR"], "present"),
        ("GPIO", defines["GPIO_BASE_ADDR"], "present"),
        ("Timer", defines["OBI_TIMER_BASE_ADDR"], "present"),
        ("iDMA", defines["IDMA_BASE_ADDR"], "present" if idma_enabled else "not present"),
    ]


def run(log_path: Path) -> int:
    log = read_text(log_path)
    pkg = extract_pkg_config()
    defines = extract_config_h_defines()
    rom_string = extract_user_rom_string()
    failures: list[str] = []

    info = expected_info_word(pkg)
    visible_version = pkg["version"] + 1

    add_check(failures, log, r"\[CORE\] Waking core via CLINT msip", "testbench core wakeup sequence")
    add_check(failures, log, r"\[JTAG\] Halting hart 0", "testbench JTAG halt sequence")
    add_check(failures, log, r"\[JTAG\] Resumed hart 0", "testbench JTAG resume sequence")

    add_check(
        failures,
        log,
        rf"\[UART\] Hello World from Croc v{visible_version:X}!",
        "rtl/croc_pkg.sv PulpJtagIdCode.version plus print_config version convention",
    )
    add_check(failures, log, rf"\[UART\]\s+Info: 0x{info:X}", "rtl/soc_ctrl/soc_ctrl_regs.sv HwInfoWord")
    add_check(failures, log, rf"\[UART\]\s+iDMAEnable: {pkg['idma']:X}", "rtl/croc_pkg.sv iDMAEnable")
    add_check(
        failures,
        log,
        rf"\[UART\]\s+Core: {core_name(pkg['core_id'])}, RV32[A-Z]+",
        "rtl/croc_pkg.sv CoreId and misa CSR ISA extension bits",
    )
    add_check(failures, log, rf"\[UART\]\s+PMPEnable: {pkg['pmp']:X}", "rtl/croc_pkg.sv CorePMPEnable")
    add_check(
        failures,
        log,
        rf"\[UART\]\s+SRAM: {pkg['sram_banks']:X}h banks x {pkg['sram_words']:X}h words",
        "rtl/croc_pkg.sv NumSramBanks and SramBankNumWords",
    )

    for name, addr, state in peripheral_expectations(defines, pkg["idma"]):
        add_check(
            failures,
            log,
            rf"\[UART\]\s+{re.escape(name)}\s+@0x{addr:X}: {state}",
            f"sw/config.h {name} base address and rtl/croc_pkg.sv presence rules",
        )

    add_check(
        failures,
        log,
        rf'\[UART\]\s+User ROM\s+@0x{defines["USER_ROM_BASE_ADDR"]:X}: "{re.escape(rom_string)}"',
        "rtl/user_domain/user_rom.sv ROM contents",
    )

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        print(f"\ncheck_print_config.py: {len(failures)} check(s) failed.", file=sys.stderr)
        return 1

    print("Print-config simulation passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", type=Path)
    args = parser.parse_args()
    return run(args.log_file)


if __name__ == "__main__":
    sys.exit(main())
