"""Warm up a deployed Ledgerlight backend after each deploy.

Wakes the (possibly sleeping) Render service, then runs the scanned sample SI-05 once in a throwaway sandbox so
the AI reading is saved in the shared cache. Every visitor's SI-05 run is then instant.

    python backend/scripts/warmup.py https://ledgerlight-api.onrender.com
"""
import secrets
import sys
import time

import httpx


def main(base: str) -> int:
    base = base.rstrip("/")
    h = {"X-Ledgerlight-Sandbox": secrets.token_hex(12)}
    t0 = time.time()
    while True:
        try:
            r = httpx.get(f"{base}/api/health", headers=h, timeout=60)
            if r.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        if time.time() - t0 > 180:
            print("The backend did not wake up within 3 minutes.")
            return 1
        time.sleep(5)
    health = r.json()
    print(f"Awake after {time.time() - t0:.0f} s. AI: {health.get('llm_provider')} {health.get('llm_model')}, "
          f"scans supported: {health.get('scanned_pdfs_supported')}")
    if not health.get("scanned_pdfs_supported"):
        print("No AI key is set on the server (GROQ_API_KEY). SI-05 will be held; set the key and redeploy.")
        return 1
    run = httpx.post(f"{base}/api/runs", json={"sample_id": "SI-05", "pace": "instant"}, headers=h, timeout=60).json()
    rid = run["runs"][0]["run_id"]
    t1 = time.time()
    while time.time() - t1 < 300:
        d = httpx.get(f"{base}/api/runs/{rid}", headers=h, timeout=60).json()
        if d["run"]["status"] in ("completed", "failed"):
            dec = (d.get("decision") or {}).get("outcome")
            print(f"SI-05 {d['run']['status']} in {time.time() - t1:.0f} s: {dec}")
            return 0 if dec == "approve_with_note" else 1
        time.sleep(3)
    print("SI-05 did not finish within 5 minutes (Groq rate limits?). Try again in a minute.")
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
