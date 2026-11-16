"""Versioned rule configuration. Each save creates a new version; runs are stamped with it."""
from __future__ import annotations

import copy

from . import db
from .catalogue import RULES, default_config, validate_config


class SettingsError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _merge(base: dict, patch: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def current(con=None) -> tuple[int, dict]:
    close = con is None
    con = con or db.connect()
    try:
        r = con.execute("SELECT version, config FROM settings_versions ORDER BY version DESC LIMIT 1").fetchone()
        if not r:
            return 1, default_config()
        # Merge onto defaults so newly added keys always exist.
        return int(r["version"]), _merge(default_config(), db.loads(r["config"], {}))
    finally:
        if close:
            con.close()


def get_version(version: int) -> dict | None:
    with db.conn() as con:
        r = con.execute("SELECT config FROM settings_versions WHERE version=?", (version,)).fetchone()
        return _merge(default_config(), db.loads(r["config"], {})) if r else None


def diff(old: dict, new: dict, prefix: str = "") -> list[dict]:
    out = []
    for k in sorted(set(old) | set(new)):
        a, b = old.get(k), new.get(k)
        path = f"{prefix}{k}"
        if isinstance(a, dict) and isinstance(b, dict):
            out.extend(diff(a, b, path + "."))
        elif a != b:
            out.append({"key": path, "before": a, "after": b})
    return out


def save(patch: dict, *, changed_by: str, reason: str, replace: bool = False, summary: str | None = None,
         actor_type: str = "human") -> tuple[int, dict, list[dict]]:
    if not reason or len(reason.strip()) < 10:
        raise SettingsError({"reason": "Give a reason of at least 10 characters."})
    with db.tx() as con:
        ver, cur = current(con)
        new = _merge(default_config(), patch) if replace else _merge(cur, patch)
        # Keep the global high-value cap and R15 in step (both are shown in S7).
        if new["global"].get("cap") != cur["global"].get("cap") and new["rules"]["R15"]["cap"] == cur["rules"]["R15"]["cap"]:
            new["rules"]["R15"]["cap"] = new["global"]["cap"]
        else:
            new["global"]["cap"] = new["rules"]["R15"]["cap"]
        errs = validate_config(new)
        if errs:
            raise SettingsError(errs)
        changes = diff(cur, new)
        if not changes:
            raise SettingsError({"config": "Nothing changed."})
        nv = ver + 1
        names = {r["id"]: r["name"] for r in RULES}
        if summary is None:
            touched = []
            for c in changes:
                parts = c["key"].split(".")
                label = f"{parts[1]} {names.get(parts[1], '')}".strip() if parts[0] in ("rules", "enabled") else c["key"]
                if label not in touched:
                    touched.append(label)
            summary = ", ".join(touched) + " changed"
        con.execute("INSERT INTO settings_versions (version, config, changed_by, reason, summary, changes, changed_at) "
                    "VALUES (?,?,?,?,?,?,?)", (nv, db.dumps(new), changed_by, reason.strip(), summary,
                                                db.dumps(changes), db.now_iso()))
        db.audit(con, actor_type=actor_type, actor_id=changed_by, event_type="settings_changed",
                 object_type="setting", object_id=changes[0]["key"].split(".")[1] if "." in changes[0]["key"] else "config",
                 summary=f"Saved rule set version {nv}: {summary}",
                 payload={"version": f"{ver} to {nv}", "reason": reason.strip(), "changes": changes})
        return nv, new, changes


def history() -> list[dict]:
    with db.conn() as con:
        out = []
        for r in con.execute("SELECT version, changed_by, reason, summary, changes, changed_at FROM settings_versions "
                             "ORDER BY version DESC"):
            d = dict(r)
            d["changes"] = db.loads(d["changes"], [])
            out.append(d)
        return out
