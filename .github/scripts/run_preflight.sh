#!/bin/bash
# Copyright (c) 2026 ETH Zurich and University of Bologna.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

# Local/CI preflight: syntax checks, config sanity, smoke sim, and default FFT
# correctness/benchmark regression checks.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CROC_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cleanup() {
  "$SCRIPT_DIR/set_croc_config.sh"
}

trap cleanup EXIT

cd "$CROC_ROOT"

echo "============================================="
echo "Preflight: script syntax"
echo "============================================="

bash -n .github/scripts/*.sh
python3 - <<'PY'
import ast
import pathlib

for path in sorted(pathlib.Path(".github/scripts").glob("*.py")):
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
PY

echo ""
echo "============================================="
echo "Preflight: default config smoke simulation"
echo "============================================="

"$SCRIPT_DIR/set_croc_config.sh"

make -C sw

cd verilator
./run_verilator.sh --build
./run_verilator.sh --run ../sw/bin/helloworld.hex
grep -q "\[UART\] Hello World from Croc!" croc.log

./run_verilator.sh --run ../sw/bin/test/print_config.hex
"$SCRIPT_DIR/check_sim.sh" croc.log

cd "$CROC_ROOT"
git diff --exit-code -- rtl/croc_pkg.sv

echo ""
echo "============================================="
echo "Preflight: default FFT regression"
echo "============================================="

"$SCRIPT_DIR/run_fft_variant.sh" default
python3 "$SCRIPT_DIR/check_metrics.py" variant \
  --variant default \
  --baseline .github/metrics/baseline.json \
  --metrics verilator/fft-default-metrics.json

echo ""
echo "============================================="
echo " Preflight completed"
echo "============================================="
