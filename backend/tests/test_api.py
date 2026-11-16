"""API tests through FastAPI's TestClient: runs, SSE stream and replay, detail, override rules, settings,
review queue, master data and metrics."""
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

MANAGER = {"X-Ledgerlight-Role": "manager"}


@pytest.fixture()
def client(fresh_db):
    with TestClient(app) as c:
        yield c


def wait_done(client, run_id, timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = client.get(f"/api/runs/{run_id}").json()
        if r["run"]["status"] in ("completed", "failed", "cancelled"):
            return r
        time.sleep(0.1)
    raise AssertionError("run did not finish")


def read_sse(client, url):
    events = []
    with client.stream("GET", url) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        cur = {}
        for line in resp.iter_lines():
            if line.startswith("id:"):
                cur["id"] = int(line[3:].strip())
            elif line.startswith("event:"):
                cur["event"] = line[6:].strip()
            elif line.startswith("data:"):
                cur["data"] = json.loads(line[5:].strip())
            elif line == "" and cur:
                events.append(cur)
                if cur.get("event") in ("run_completed", "run_failed", "run_cancelled"):
                    break
                cur = {}
    return events


def test_health_and_samples(client):
    h = client.get("/api/health").json()
    assert h["ok"] and h["extraction_mode"] in ("llm", "text-only")
    s = client.get("/api/samples").json()["samples"]
    assert [x["id"] for x in s] == [f"SI-0{i}" for i in range(1, 8)]
    assert client.get("/api/samples/SI-01/pdf").headers["content-type"] == "application/pdf"


def test_upload_run_stream_and_detail(client):
    pdf = (config.SAMPLES_DIR / "SI-01_brightline_BL-2026-0412.pdf").read_bytes()
    r = client.post("/api/runs", files={"files": ("invoice.pdf", pdf, "application/pdf")}, data={"pace": "instant"})
    assert r.status_code == 201, r.text
    run_id = r.json()["runs"][0]["run_id"]
    events = read_sse(client, f"/api/runs/{run_id}/events")
    names = [e["event"] for e in events]
    assert names[0] == "run_started" and names[-1] == "run_completed"
    done = [e["data"]["stage_no"] for e in events if e["event"] == "stage_completed"]
    assert done == list(range(1, 10))
    dec = next(e for e in events if e["event"] == "decision")
    assert dec["data"]["outcome"] == "auto_approve"
    assert [e["id"] for e in events] == sorted(e["id"] for e in events)
    # reconnect with Last-Event-ID replays only what was missed
    later = read_sse(client, f"/api/runs/{run_id}/events?last_event_id=10")
    assert later[0]["id"] == 11 and later[-1]["event"] == "run_completed"
    d = client.get(f"/api/runs/{run_id}").json()
    assert d["decision"]["outcome"] == "auto_approve" and len(d["rules"]) == 16
    assert d["po_panel"]["po"]["id"] == "PO-2026-1001" and len(d["po_panel"]["table"]) == 2
    assert client.get(d["pdf_url"]).status_code == 200
    assert client.get(f"/api/runs/{run_id}/decision.json").status_code == 200


def test_rejects_non_pdf(client):
    r = client.post("/api/runs", files={"files": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400 and r.json()["rejected"][0]["error"] == "Only PDF files are supported."


def test_override_requires_reason_and_respects_roles(client):
    rid = client.post("/api/runs", json={"sample_id": "SI-03", "pace": "instant"}).json()["runs"][0]["run_id"]
    d = wait_done(client, rid)
    inv = d["invoice"]["id"]
    assert d["decision"]["outcome"] == "route_for_review"
    bad = client.post(f"/api/invoices/{inv}/override", json={"action": "approve", "reason_code": "Other", "reason_text": "short"})
    assert bad.status_code == 422
    clerk = client.post(f"/api/invoices/{inv}/override",
                        json={"action": "approve", "reason_code": "PO amended by Procurement", "reason_text": "PO raised by 500 cartons"})
    assert clerk.status_code == 403  # exposure ₹23,600 is above the clerk limit
    ok = client.post(f"/api/invoices/{inv}/override", headers=MANAGER,
                     json={"action": "hold", "reason_code": "Credit note requested",
                           "reason_text": "Credit note for 500 cartons requested"})
    assert ok.status_code == 200 and ok.json()["outcome"] == "hold_request_info"
    det = client.get(f"/api/invoices/{inv}").json()
    assert det["overridden"] and det["decision"]["version"] == 2 and det["decision_history"][0]["outcome"] == "route_for_review"
    audit = client.get("/api/audit", params={"event_type": "decision_overridden"}).json()
    assert audit["total"] == 1 and audit["items"][0]["payload"]["reason_code"] == "Credit note requested"


def test_bank_hold_release_needs_manager_and_checklist(client):
    rid = client.post("/api/runs", json={"sample_id": "SI-06", "pace": "instant"}).json()["runs"][0]["run_id"]
    inv = wait_done(client, rid)["invoice"]["id"]
    body = {"action": "approve", "reason_code": "Vendor confirmed by phone", "reason_text": "Called the number on file"}
    assert client.post(f"/api/invoices/{inv}/override", json=body).status_code == 403
    assert client.post(f"/api/invoices/{inv}/override", headers=MANAGER, json=body).status_code == 422
    body["checklist"] = {"called_vendor_on_master_number": True, "written_request_received": True,
                         "second_person_confirmed": True}
    assert client.post(f"/api/invoices/{inv}/override", headers=MANAGER, json=body).status_code == 200


def test_review_queue_metrics_and_runs_list(client):
    q = client.get("/api/review-queue").json()
    assert q["open_exceptions"] == 14 and q["counts"]["review"] == 9 and q["counts"]["hold"] == 5
    m = client.get("/api/metrics?range=30d").json()
    assert m["tiles"]["processed"]["value"] == 60
    assert m["tiles"]["straight_through_rate"]["value"] == 70.0
    assert m["tiles"]["open_exceptions"]["value_all_time"] == 14
    runs = client.get("/api/runs", params={"status": "route_for_review"}).json()
    assert runs["total"] == 9 and runs["counts"]["all"] == 60


def test_settings_validation_save_and_preview(client):
    s = client.get("/api/settings").json()
    assert len(s["rules"]) == 16 and s["version"] == 14
    bad = client.put("/api/settings", json={"config": {"rules": {"R10": {"note_pct": 20}}}, "reason": "testing a bad value"})
    assert bad.status_code == 422 and "R10.note_pct" in bad.json()["fields"]
    no_reason = client.put("/api/settings", json={"config": {"rules": {"R10": {"note_pct": 1}}}, "reason": ""})
    assert no_reason.status_code == 422
    ok = client.put("/api/settings", json={"config": {"rules": {"R10": {"note_pct": 1}}}, "reason": "Tighter price tolerance"})
    assert ok.status_code == 200 and ok.json()["version"] == 15
    pv = client.post("/api/settings/preview", json={"config": {"rules": {"R10": {"note_pct": 2}}}}).json()
    assert pv["valid"]


def test_master_data_bank_change_then_rerun_releases_ec4(client):
    rid = client.post("/api/runs", json={"sample_id": "SI-06", "pace": "instant"}).json()["runs"][0]["run_id"]
    inv = wait_done(client, rid)["invoice"]["id"]
    bank = {"bank_name": "Riverbend Co-operative Bank", "bank_account_no": "5020 0091 2334 7", "bank_ifsc": "RBCB0000412",
            "reason": "Verified by phone and letterhead", "verified_by": "Meera Rao"}
    assert client.post("/api/vendors/V-102/bank", json=bank).status_code == 403
    assert client.post("/api/vendors/V-102/bank", json=bank, headers=MANAGER).status_code == 200
    rr = client.post(f"/api/invoices/{inv}/rerun", json={"pace": "instant"}).json()["run_id"]
    d = wait_done(client, rr)
    assert d["decision"]["outcome"] == "auto_approve"   # re-checked R05 against the new master


def test_pos_and_vendors_lists(client):
    pos = {p["id"]: p for p in client.get("/api/pos").json()["items"]}
    assert pos["PO-2026-1005"]["status"] == "open" and pos["PO-2026-1005"]["billed_subtotal_paise"] == 0
    assert pos["PO-2026-1004"]["status"] == "partially_billed"
    vendors = client.get("/api/vendors").json()["items"]
    assert len(vendors) == 6 and vendors[-1]["status"] == "pending"
    csv_text = ("po_number,vendor_id,issue_date,valid_to,currency,item_code,description,uom,ordered_qty,unit_price,tax_rate_pct\n"
                "PO-2026-1010,V-105,2026-11-10,2026-12-31,INR,FR-X,Freight,trips,-3,1000,18\n")
    pv = client.post("/api/import/pos", files={"file": ("pos.csv", csv_text, "text/csv")}).json()
    assert not pv["valid"] and pv["problems"][0]["errors"]["ordered_qty"]
