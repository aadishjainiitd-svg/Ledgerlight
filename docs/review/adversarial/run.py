"""Runs every adversarial case in gen.py against a Ledgerlight server on port 8050 and prints a table.

    backend/.venv/Scripts/python docs/review/adversarial/run.py [--data-dir DIR] [--no-scans] [--only A01,A02]
                                                                [--no-server]

By default it starts its own uvicorn on 127.0.0.1:8050 with LEDGERLIGHT_DATA_DIR set to a throw-away folder
(never backend/data), in two phases:
  1. text phase: AI keys switched off (LEDGERLIGHT_DOTENV=0), so text PDFs use the deterministic parser and
     explanations are the deterministic templates;
  2. scan phase (only cases with needs_llm): backend/.env is loaded so image-only scans go to the vision model.
     The key is never read, printed or logged by this script.
Each case starts from POST /api/demo/reset. Results are written to results.json next to this file.
--no-server uses a server you already started on the port (all cases run against it).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(HERE))
import gen  # noqa: E402

PAID = {"auto_approve", "approve_with_note"}
SHORT = {"auto_approve": "APPROVE", "approve_with_note": "APPROVE+NOTE", "route_for_review": "REVIEW",
         "hold_request_info": "HOLD", "reject": "REJECT"}
MANAGER = {"X-Ledgerlight-Role": "manager", "X-Ledgerlight-User": "Adversarial review"}


# ------------------------------------------------------------------ server
def start_server(port: int, data_dir: Path, with_ai: bool) -> subprocess.Popen:
    env = dict(os.environ)
    env.update(LEDGERLIGHT_DATA_DIR=str(data_dir), LEDGERLIGHT_PACE="instant", LEDGERLIGHT_LOG="WARNING")
    if not with_ai:
        env.update(LEDGERLIGHT_DOTENV="0", GROQ_API_KEY="", ANTHROPIC_API_KEY="")
    else:
        env.pop("LEDGERLIGHT_DOTENV", None)
    data_dir.mkdir(parents=True, exist_ok=True)
    log = open(data_dir / "server.log", "w", encoding="utf-8")
    py = BACKEND / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    p = subprocess.Popen([str(py), "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                         cwd=str(BACKEND), env=env, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2).status_code == 200:
                return p
        except httpx.HTTPError:
            pass
        if p.poll() is not None:
            raise SystemExit(f"server exited early, see {data_dir / 'server.log'}")
        time.sleep(0.5)
    p.terminate()
    raise SystemExit("server did not start in 60 s")


def stop_server(p: subprocess.Popen | None):
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()


# ------------------------------------------------------------------ case execution
def wait_run(cli: httpx.Client, run_id: str, timeout: float) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = cli.get(f"/api/runs/{run_id}").json()
        st = (d.get("run") or {}).get("status")
        if st in ("completed", "failed", "cancelled"):
            return d
        time.sleep(0.25)
    return {"run": {"status": "timeout"}}


def _redact(s):
    import re
    return re.sub(r"org_[A-Za-z0-9]+", "org_[redacted]", s) if isinstance(s, str) else s


def summarise(d: dict) -> dict:
    run = d.get("run") or {}
    dec = d.get("decision") or {}
    rules = {r["rule_id"]: r for r in d.get("rules") or []}
    flagged = {k: f"{r['severity']}: {r['message']}" for k, r in rules.items() if not r.get("skipped") and r["severity"] != "pass"}
    inv = d.get("invoice") or {}
    return {"status": run.get("status"), "error": _redact(run.get("error")), "outcome": dec.get("outcome"),
            "driving": dec.get("driving_rule_ids") or [], "headline": dec.get("headline"),
            "exposure_paise": dec.get("exposure_paise"), "assigned_to": dec.get("assigned_to"), "flagged": flagged,
            "invoice_no": inv.get("invoice_no_raw"), "total_paise": inv.get("total_paise"),
            "vendor_id": inv.get("vendor_id"), "po_id": inv.get("po_id"), "po_method": inv.get("po_match_method"),
            "r05": (rules.get("R05") or {}).get("message"), "r10": (rules.get("R10") or {}).get("message"),
            "ok": (dec.get("explanation") or {}).get("ok"), "attention": (dec.get("explanation") or {}).get("attention"),
            "explanation_mode": None}


def upload(cli: httpx.Client, files: list[dict]) -> httpx.Response:
    parts = [("files", (fl["name"], fl["data"], "application/pdf")) for fl in files]
    return cli.post("/api/runs", files=parts, data={"pace": "instant", "use_cache": "false"}, timeout=120)


def run_case(cli: httpx.Client, case: dict, timeout: float, pause: float = 0) -> dict:
    r = cli.post("/api/demo/reset", headers=MANAGER, timeout=300)
    r.raise_for_status()
    for method, path, body in case.get("setup") or []:
        resp = cli.request(method, path, json=body, headers=MANAGER)
        if resp.status_code >= 400:
            return {"error": f"setup {method} {path} -> {resp.status_code} {resp.text[:200]}", "results": []}
    results = []
    if case.get("upload_error"):
        resp = upload(cli, case["files"])
        body = resp.json()
        rej = body.get("rejected") or []
        return {"upload_status": resp.status_code, "rejected": rej, "results": [],
                "runs": [x["run_id"] for x in body.get("runs") or []]}
    if case.get("flow") == "concurrent":
        resp = upload(cli, case["files"])
        runs = resp.json().get("runs") or []
        for x in runs:
            results.append({"file": x["file_name"], **summarise(wait_run(cli, x["run_id"], timeout))})
        return {"results": results}
    for i, fl in enumerate(case["files"]):
        if pause and i:
            time.sleep(pause)  # AI phase: let the per-minute token budget refill between files
        if "sample" in fl:
            resp = cli.post("/api/runs", json={"sample_id": fl["sample"], "pace": "instant", "use_cache": False})
        else:
            resp = upload(cli, [fl])
        if resp.status_code >= 400:
            results.append({"file": fl.get("name") or fl.get("sample"), "status": "upload_error", "error": resp.text[:300],
                            "outcome": None})
            continue
        x = resp.json()["runs"][0]
        results.append({"file": x["file_name"], **summarise(wait_run(cli, x["run_id"], timeout))})
    return {"results": results}


def verdict(case: dict, res: dict) -> tuple[str, str]:
    """(verdict, actual text). LOOPHOLE = unsafe or wrong; WEAK = right decision, misleading explanation."""
    if res.get("error"):
        return "ERROR", res["error"]
    if case.get("upload_error"):
        rej = res.get("rejected") or []
        msg = "; ".join(x["error"] for x in rej) or f"accepted (HTTP {res.get('upload_status')})"
        ok = any(case["upload_error"].lower() in x["error"].lower() for x in rej) and not res.get("runs")
        return ("OK" if ok else "LOOPHOLE"), ("upload rejected: " + msg if rej else msg)
    rs = res["results"]
    def one(x):
        if x.get("status") != "completed":
            return f"{x.get('status')}: {x.get('error')}"
        return f"{SHORT.get(x['outcome'], x['outcome'])} [{','.join(x['driving']) or '-'}]"
    actual = " | ".join(one(x) for x in rs)
    if any("429" in str(x.get("error") or "") or "could not be reached" in str(x.get("error") or "") for x in rs):
        return "UNTESTED", actual[:200] + "  (AI provider rate limit, not a product decision)"
    if any(x.get("status") not in ("completed",) for x in rs):
        return "LOOPHOLE", actual + "  (run did not complete)"
    if case.get("target") == "all":
        n_paid = sum(1 for x in rs if x["outcome"] in PAID)
        return ("OK" if n_paid <= 1 else "LOOPHOLE"), actual
    last = rs[-1]
    if last["outcome"] not in case["expect"]:
        return "LOOPHOLE", actual
    w = weak_check(case, last)
    return (("WEAK", actual + "  (" + w + ")") if w else ("OK", actual))


def weak_check(case: dict, x: dict) -> str | None:
    head = (x.get("headline") or "").lower()
    if case.get("weak") == "R05" and "different from the one we have on file" in head and \
            "matches" not in (x.get("r05") or "") and x.get("r05") and _same_acct(x["r05"]):
        return "headline says the account is different, but it is the account on file"
    if case.get("weak") == "R05" and x["outcome"] in PAID and "the new account" in (x.get("r05") or "").lower():
        return "notice says the bank changed from 1 Nov 2026, R05 calls the old on-file account 'new' and cites a 2025 verification"
    if case.get("weak") == "notinvoice" and "missing the invoice number" in head:
        return "a vendor statement is held as 'missing the invoice number' instead of 'this is not an invoice'"
    if case.get("weak") == "R14" and "does not add up" in head:
        return "headline says the total does not add up; it does once freight is counted"
    if case.get("weak") == "R02" and "hard to read" in head:
        return "a clean text PDF is told 'some fields were hard to read'; the date is only format-ambiguous"
    return None


def _same_acct(msg: str) -> bool:
    import re
    ends = re.findall(r"ending (\d{4})", msg)
    return len(ends) >= 2 and ends[0] == ends[1]


# ------------------------------------------------------------------ main
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8050)
    ap.add_argument("--data-dir", default=None)
    ap.add_argument("--no-scans", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--no-server", action="store_true")
    a = ap.parse_args()
    cases = gen.build_cases(include_scans=not a.no_scans)
    n = gen.write_all(cases)
    print(f"Generated {n} PDFs in {gen.OUT}")
    if a.only:
        keep = {x.strip() for x in a.only.split(",")}
        cases = [c for c in cases if c["id"] in keep]
    base = Path(a.data_dir) if a.data_dir else Path(tempfile.mkdtemp(prefix="ledgerlight-adv-"))
    phases = [("text", False, [c for c in cases if not c.get("needs_llm")]),
              ("scan", True, [c for c in cases if c.get("needs_llm")])]
    out = {}
    for name, with_ai, cs in phases:
        if not cs:
            continue
        srv = None if a.no_server else start_server(a.port, base / name, with_ai)
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{a.port}", timeout=60) as cli:
                mode = cli.get("/api/health").json().get("extraction_mode") or cli.get("/api/health").json()
                print(f"\n[{name} phase] server extraction mode: {mode}; {len(cs)} cases")
                for i, c in enumerate(cs):
                    if with_ai and i:
                        time.sleep(65)  # Groq free tier: tokens-per-minute limits
                    t0 = time.time()
                    try:
                        res = run_case(cli, c, timeout=600 if with_ai else 90, pause=65 if with_ai else 0)
                    except Exception as e:  # keep going: a crash is a finding, not a script failure
                        res = {"error": f"{type(e).__name__}: {e}", "results": []}
                    v, actual = verdict(c, res)
                    out[c["id"]] = {"id": c["id"], "title": c["title"], "attack": c["attack"], "group": c["group"],
                                    "expect": c["expect"], "severity_if_wrong": c["sev"], "verdict": v, "actual": actual,
                                    "seconds": round(time.time() - t0, 1), **res,
                                    "files": [fl.get("name") or fl.get("sample") for fl in c["files"]]}
                    print(f"  {c['id']:<5} {v:<8} {actual[:110]}", flush=True)
        finally:
            stop_server(srv)
    (HERE / "results.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    # ---- table
    print("\n" + "=" * 150)
    print(f"{'case':<5} {'verdict':<8} {'sev if wrong':<12} {'expected':<34} {'actual':<60} title")
    print("-" * 150)
    order = {"LOOPHOLE": 0, "ERROR": 1, "WEAK": 2, "UNTESTED": 3, "OK": 4}
    for r in sorted(out.values(), key=lambda r: (order.get(r["verdict"], 9), r["id"])):
        exp = "/".join(SHORT.get(e, e) for e in r["expect"])
        print(f"{r['id']:<5} {r['verdict']:<8} {r['severity_if_wrong']:<12} {exp[:34]:<34} {r['actual'][:60]:<60} {r['title'][:60]}")
    counts = {}
    for r in out.values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    print("-" * 150)
    print("Verdicts: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: order.get(kv[0], 9))))
    print(f"Data dir: {base}")


if __name__ == "__main__":
    main()
