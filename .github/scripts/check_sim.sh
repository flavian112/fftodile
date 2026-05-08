#!/bin/bash
# Copyright (c) 2026 ETH Zurich and University of Bologna.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Author:  Philippe Sauter <phsauter@iis.ee.ethz.ch>

# Validate a Verilator simulation log against the expected SoC configuration.
# Dynamic fields (iDMAEnable, PMPEnable, core type) are derived from
# rtl/croc_pkg.sv so that legitimate config changes do not produce stale
# failures.  Fixed fields (version, peripheral presence, user ROM string) are
# checked with tight patterns.  Every failure prints a hint pointing to the
# authoritative source.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <log_file>" >&2
    exit 1
fi

LOG_FILE=$1
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CROC_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PKG="$CROC_ROOT/rtl/croc_pkg.sv"

# ---------------------------------------------------------------------------
# Derive authoritative config values from croc_pkg.sv
# ---------------------------------------------------------------------------
extract_pkg() { grep -oP "$1" "$PKG" | head -1; }

IDMA_ENABLE=$(extract_pkg "localparam\s+bit\s+iDMAEnable\s*=\s*1'b\K[01]")
PMP_ENABLE=$(extract_pkg "localparam\s+bit\s+CorePMPEnable\s*=\s*1'b\K[01]")
CORE_ID=$(extract_pkg "localparam\s+int\s+unsigned\s+CoreId\s*=\s*\K[0-9]+")

if [[ -z "$IDMA_ENABLE" || -z "$PMP_ENABLE" || -z "$CORE_ID" ]]; then
    echo "Error: Failed to read configuration from $PKG" >&2
    exit 1
fi

case "$CORE_ID" in
    0) CORE_STR="CVE2"   ;;
    1) CORE_STR="Ibex"   ;;
    7) CORE_STR="custom" ;;
    *) CORE_STR="unknown" ;;
esac

IDMA_PERIPH=$([ "$IDMA_ENABLE" = "1" ] && echo "present" || echo "not present")

# ---------------------------------------------------------------------------
# Check helper — accumulates failures so all issues are shown at once
# ---------------------------------------------------------------------------
FAILURES=0
check() {
    local pattern=$1
    local hint=$2
    if ! grep -qP "$pattern" "$LOG_FILE"; then
        echo "FAIL: Pattern not found in log."
        echo "      Pattern: $pattern"
        echo "      Hint:    $hint"
        FAILURES=$((FAILURES + 1))
    fi
}

# ---------------------------------------------------------------------------
# Simulation control-flow (testbench sequencing)
# ---------------------------------------------------------------------------
check '\[CORE\] Waking core via CLINT msip' "Testbench: core wakeup via CLINT"
check '\[JTAG\] Halting hart 0'             "Testbench: JTAG halt sequence"
check '\[JTAG\] Resumed hart 0'             "Testbench: JTAG resume sequence"

# ---------------------------------------------------------------------------
# Fixed SoC identity (must not change without a version bump)
# ---------------------------------------------------------------------------
check '\[UART\] Hello World from Croc v2!' \
    "rtl/croc_pkg.sv (PulpJtagIdCode.version = 4'h1 → version+1 = 2)"

# ---------------------------------------------------------------------------
# Configurable features — derived from croc_pkg.sv, not hardcoded here
# ---------------------------------------------------------------------------
check "\[UART\]\s+iDMAEnable: ${IDMA_ENABLE}" \
    "rtl/croc_pkg.sv (iDMAEnable = 1'b${IDMA_ENABLE})"

check "\[UART\]\s+Core: ${CORE_STR}, RV32[A-Z]+" \
    "rtl/croc_pkg.sv (CoreId = ${CORE_ID} → ${CORE_STR}; ISA extensions may vary)"

check "\[UART\]\s+PMPEnable: ${PMP_ENABLE}" \
    "rtl/croc_pkg.sv (CorePMPEnable = 1'b${PMP_ENABLE})"

# ---------------------------------------------------------------------------
# SRAM — dynamic sizing; accept any valid hex count
# ---------------------------------------------------------------------------
check '\[UART\]\s+SRAM: [0-9A-Fa-f]+h banks x [0-9A-Fa-f]+h words' \
    "rtl/croc_pkg.sv (NumSramBanks, SramBankNumWords)"

# ---------------------------------------------------------------------------
# Peripheral presence — always-present peripherals
# ---------------------------------------------------------------------------
for periph in "Debug" "Bootrom" "CLINT" "SoC Ctrl" "UART" "GPIO" "Timer"; do
    check "\[UART\]\s+${periph}\s*: present" \
        "sw/test/print_config.c peripheral table (${periph} must always be present)"
done

# iDMA presence tracks iDMAEnable
check "\[UART\]\s+iDMA\s*: ${IDMA_PERIPH}" \
    "rtl/croc_pkg.sv (iDMAEnable = 1'b${IDMA_ENABLE} → iDMA peripheral ${IDMA_PERIPH})"

# ---------------------------------------------------------------------------
# User ROM product string — tightly checked; update when the string changes
# ---------------------------------------------------------------------------
check '\[UART\]\s+User ROM\s*: "FFTodile REV 1\.0 - Flavian Kaufmann, Thanu Kanagalingam"' \
    "rtl/user_domain/user_rom.sv (product string literal)"

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [[ $FAILURES -ne 0 ]]; then
    echo ""
    echo "check_sim.sh: ${FAILURES} check(s) failed. See hints above for the source of truth."
    exit 1
fi

echo "Hello world simulation passed."
exit 0
