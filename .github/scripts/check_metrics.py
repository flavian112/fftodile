#!/usr/bin/env python3
# Copyright (c) 2026 ETH Zurich and University of Bologna.
# Licensed under the Apache License, Version 2.0, see LICENSE for details.
# SPDX-License-Identifier: Apache-2.0

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_metric_value(value: Any, *, force_hex: bool = False) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if s == "":
        return None

    if force_hex:
        return float(int(s, 16))

    if s.lower().startswith("0x"):
        return float(int(s, 16))

    # Treat plain hex strings with alphabetic digits (e.g. "5D11") as hex.
    # All-digit benchmark cycle values are handled by the force_hex path.
    if re.fullmatch(r"[0-9A-Fa-f]+", s):
        if re.search(r"[A-Fa-f]", s):
            return float(int(s, 16))
        return float(int(s, 10))

    return float(s)


def compare_pct(
    metric: str,
    current_raw: Any,
    baseline_raw: Any,
    threshold_pct: Optional[float],
    *,
    force_hex: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    if threshold_pct is None:
        return None, f"SKIP {metric}: no threshold configured"

    try:
        current = parse_metric_value(current_raw, force_hex=force_hex)
        baseline = parse_metric_value(baseline_raw, force_hex=force_hex)
    except ValueError as err:
        return f"FAIL {metric}: invalid numeric value ({err})", None

    if current is None:
        return f"FAIL {metric}: current value missing", None
    if baseline is None:
        return None, f"SKIP {metric}: baseline value missing"

    if baseline <= 0:
        return None, f"SKIP {metric}: baseline must be > 0 (got {baseline})"

    allowed = baseline * (1.0 + threshold_pct / 100.0)
    if current > allowed:
        return (
            f"FAIL {metric}: current={current:g} exceeds allowed={allowed:g} "
            f"(baseline={baseline:g}, threshold={threshold_pct:g}%)",
            None,
        )

    return None, (
        f"PASS {metric}: current={current:g} <= allowed={allowed:g} "
        f"(baseline={baseline:g}, threshold={threshold_pct:g}%)"
    )


def run_variant(args: argparse.Namespace) -> int:
    baseline = load_json(args.baseline)
    current = load_json(args.metrics)

    thresholds = baseline.get("variant_threshold_pct", {})
    baselines = baseline.get("variant_baseline", {})
    variant_base = baselines.get(args.variant)

    if variant_base is None:
        print(f"SKIP: no baseline entry for variant '{args.variant}'")
        return 0

    metrics_to_check = [
        "sim_runtime_seconds",
        "rnd1_sw_visible_median_hex",
        "rnd1_hop_visible_median_hex",
        "rnd1_hip_visible_median_hex",
    ]

    failures: List[str] = []
    notes: List[str] = []

    for metric in metrics_to_check:
        fail, note = compare_pct(
            metric,
            current.get(metric),
            variant_base.get(metric),
            thresholds.get(metric),
            force_hex=metric.endswith("_hex"),
        )
        if fail:
            failures.append(fail)
        if note:
            notes.append(note)

    print(f"Variant metrics check: {args.variant}")
    for note in notes:
        print(note)

    if failures:
        for fail in failures:
            print(fail)
        return 1

    return 0


def run_synth(args: argparse.Namespace) -> int:
    baseline = load_json(args.baseline)
    current = load_json(args.metrics)

    thresholds = baseline.get("synthesis_threshold_pct", {})
    baselines = baseline.get("synthesis_baseline", {})
    synth_base = baselines.get(args.config)

    if synth_base is None:
        print(f"SKIP: no synthesis baseline entry for config '{args.config}'")
        return 0

    metrics_to_check = [
        "chip_area_um2",
        "user_domain_um2",
        "design_cell_count",
        "netlist_size_bytes",
    ]

    failures: List[str] = []
    notes: List[str] = []

    for metric in metrics_to_check:
        fail, note = compare_pct(
            metric,
            current.get(metric),
            synth_base.get(metric),
            thresholds.get(metric),
        )
        if fail:
            failures.append(fail)
        if note:
            notes.append(note)

    # Critical path is tracked as a placeholder for now; synth-only flow has no STA.
    if current.get("critical_path_ns") is None:
        notes.append("SKIP critical_path_ns: synth-only flow does not provide STA")

    print(f"Synthesis metrics check: {args.config}")
    for note in notes:
        print(note)

    if failures:
        for fail in failures:
            print(fail)
        return 1

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check CI metrics against baseline thresholds")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    parser_variant = subparsers.add_parser("variant", help="Check FFT variant metrics")
    parser_variant.add_argument("--variant", required=True, help="Variant name")
    parser_variant.add_argument("--baseline", required=True, help="Baseline JSON path")
    parser_variant.add_argument("--metrics", required=True, help="Current metrics JSON path")

    parser_synth = subparsers.add_parser("synth", help="Check synthesis metrics")
    parser_synth.add_argument("--config", required=True, help="Synthesis config name")
    parser_synth.add_argument("--baseline", required=True, help="Baseline JSON path")
    parser_synth.add_argument("--metrics", required=True, help="Current metrics JSON path")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.mode == "variant":
        return run_variant(args)
    if args.mode == "synth":
        return run_synth(args)

    print(f"Unsupported mode: {args.mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
