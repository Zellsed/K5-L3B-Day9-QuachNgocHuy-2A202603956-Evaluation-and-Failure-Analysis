
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
   
    problems: list[str] = []
    metric_ids = {m["id"] for m in spec.get("metrics", [])}

    for name, value in pr.get("metrics", {}).items():
        if isinstance(value, float) and not math.isfinite(value):
            problems.append(f"metric {name} is non-finite")
    if pr.get("evaluator_failures"):
        problems.append("evaluator_failures is non-empty")

    manifest = pr.get("manifest", {})
    expected_rows = int(manifest.get("items", 0)) * len(manifest.get("seeds", []))
    rows = pr.get("rows", [])
    if len(rows) != expected_rows:
        problems.append(f"row count {len(rows)} != manifest {expected_rows}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    if len(set(keys)) != len(keys):
        problems.append("duplicate (item_id, seed) row")
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows", [])}
    if set(keys) != base_keys:
        problems.append("(item_id, seed) set differs from baseline")
    for r in rows:
        for mid in metric_ids:
            if mid in r and r[mid] is None:
                problems.append(f"{r.get('item_id')}@{r.get('seed')} has missing {mid}")
    base_slices = {(r.get("item_id"), r.get("seed")): tuple(sorted(r.get("slices") or [])) for r in base.get("rows", [])}
    for r in rows:
        key = (r.get("item_id"), r.get("seed"))
        if key in base_slices and tuple(sorted(r.get("slices") or [])) != base_slices[key]:
            problems.append(f"slice tags changed for {key[0]}@{key[1]}")

    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        current = {m["id"]: m for m in spec.get("metrics", [])}
        for old in base_spec.get("metrics", []):
            mid = old["id"]
            new = current.get(mid)
            if new is None:
                problems.append(f"ratchet: metric {mid} was removed")
                continue
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"ratchet: metric {mid} is no longer blocking")
            old_t, new_t = old.get("threshold", {}), new.get("threshold", {})
            for key, comparator in (("min", lambda n, o: n < o), ("max", lambda n, o: n > o),
                                    ("max_increase", lambda n, o: n > o)):
                if key in old_t and (key not in new_t or comparator(new_t[key], old_t[key])):
                    problems.append(f"ratchet: {mid}.{key} was loosened")
            if old_t.get("no_significant_drop") and not new_t.get("no_significant_drop"):
                problems.append(f"ratchet: {mid}.no_significant_drop was removed")
        current_slices = {s["name"]: s for s in spec.get("slices", [])}
        for old in base_spec.get("slices", []):
            new = current_slices.get(old["name"])
            if new is None:
                problems.append(f"ratchet: slice {old['name']} was removed")
                continue
            if old.get("blocking") and not new.get("blocking"):
                problems.append(f"ratchet: slice {old['name']} is no longer blocking")
            for key, comparator in (("min", lambda n, o: n < o), ("max", lambda n, o: n > o)):
                if key in old and (key not in new or comparator(new[key], old[key])):
                    problems.append(f"ratchet: slice {old['name']}.{key} was loosened")
            if old.get("no_significant_drop") and not new.get("no_significant_drop"):
                problems.append(f"ratchet: slice {old['name']}.no_significant_drop was removed")
    return list(dict.fromkeys(problems))


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for slice_spec in spec.get("slices", []):
        name, metric = slice_spec["name"], slice_spec["metric"]
        values = per_item(pr, metric, slice_name=name)
        base_values = per_item(base, metric, slice_name=name)
        value = sum(values.values()) / len(values) if values else None
        verdict, note = "ok", ""
        if value is None:
            verdict = "missing"
        elif "min" in slice_spec and value < slice_spec["min"]:
            verdict = "fail"
        elif "max" in slice_spec and value > slice_spec["max"]:
            verdict = "fail"
        if slice_spec.get("no_significant_drop") and value is not None:
            keys = sorted(set(values) & set(base_values))
            if not keys:
                verdict, note = "missing", "no paired slice items"
            else:
                delta, lo, hi = stats.paired_bootstrap(
                    [values[k] for k in keys], [base_values[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95),
                )
                note = f"Δ {delta:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        ident = f"slice:{name}/{metric}"
        if verdict != "ok" and slice_spec.get("blocking"):
            blocked.append(ident)
        label = "ok" if verdict == "ok" else ("MISSING" if verdict == "missing" else "BLOCK")
        lines.append(f"  {ident:<30} {value!s:<8} {json.dumps(slice_spec):<50} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
