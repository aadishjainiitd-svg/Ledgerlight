"""End-to-end HTTP check: upload SI-01 as a real multipart file, consume the SSE stream, print the event
sequence, then fetch the run detail and print the decision.

    python scripts/check_sse.py [--base http://127.0.0.1:8010] [--file ../samples/SI-01_brightline_BL-2026-0412.pdf]
                                [--pace normal]
Exit code 0 only if all nine stages completed and a decision arrived."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8010")
    ap.add_argument("--file", default=str(HERE.parent.parent / "samples" / "SI-01_brightline_BL-2026-0412.pdf"))
    ap.add_argument("--pace", default="normal")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    with httpx.Client(base_url=a.base, timeout=60) as c:
        h = c.get("/api/health").json()
        print(f"health: ok={h['ok']} extraction_mode={h['extraction_mode']} runs_in_db={h['runs']}")
        p = Path(a.file)
        r = c.post("/api/runs", files={"files": (p.name, p.read_bytes(), "application/pdf")}, data={"pace": a.pace})
        r.raise_for_status()
        run = r.json()["runs"][0]
        print(f"POST /api/runs -> 201 run_id={run['run_id']} invoice_id={run['invoice_id']}")
        t0 = time.time()
        seq, counts, stages_done, decision = [], {}, [], None
        with c.stream("GET", run["events_url"], timeout=120) as s:
            ev = {}
            for line in s.iter_lines():
                if line.startswith("id:"):
                    ev["id"] = int(line[3:])
                elif line.startswith("event:"):
                    ev["event"] = line[6:].strip()
                elif line.startswith("data:"):
                    ev["data"] = json.loads(line[5:])
                elif line == "" and "event" in ev:
                    name, d = ev["event"], ev.get("data", {})
                    counts[name] = counts.get(name, 0) + 1
                    t = f"{time.time() - t0:5.2f}s"
                    if name == "stage_started":
                        print(f"  {t} #{ev['id']:<3} stage_started   {d['stage_no']} {d['name']}")
                    elif name == "stage_completed":
                        stages_done.append(d["stage_no"])
                        print(f"  {t} #{ev['id']:<3} stage_completed {d['stage_no']} {d['status']:<7} "
                              f"severity={d['severity_max']:<6} {d['duration_ms']}ms  {d['message'][:70]}")
                    elif name in ("run_started", "decision", "run_completed", "run_failed", "run_cancelled"):
                        extra = (f"outcome={d['outcome']} exposure={d['exposure_paise']} headline=\"{d['headline']}\""
                                 if name == "decision" else json.dumps({k: v for k, v in d.items() if k in
                                                                         ("run_id", "duration_ms", "outcome", "error")}))
                        print(f"  {t} #{ev['id']:<3} {name:<15} {extra}")
                        if name == "decision":
                            decision = d
                    seq.append(name)
                    if name in ("run_completed", "run_failed", "run_cancelled"):
                        break
                    ev = {}
        other = {k: v for k, v in counts.items() if k not in ("stage_started", "stage_completed")}
        print(f"event counts: stage_started={counts.get('stage_started', 0)} stage_completed={counts.get('stage_completed', 0)} "
              + " ".join(f"{k}={v}" for k, v in sorted(other.items())))
        detail = c.get(f"/api/runs/{run['run_id']}").json()
        dec = detail["decision"]
        print(f"GET /api/runs/{run['run_id']} -> decision={dec['outcome']} ({dec['outcome_long']}) "
              f"headline=\"{dec['headline']}\" rules={len(detail['rules'])} "
              f"failing_rules={[x['rule_id'] for x in detail['rules'] if x['severity'] not in ('pass', None)]}")
        ok = stages_done == list(range(1, 10)) and decision is not None and seq[-1] == "run_completed"
        print("CHECK", "PASS" if ok else "FAIL")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
