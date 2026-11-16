"""Run events: persisted first, then published to live SSE subscribers (spec 8.2: every event is
persisted before it is published, so a late or reconnecting page replays from the database)."""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone

from . import db


class Bus:
    def __init__(self):
        self._lock = threading.Lock()
        self._subs: dict[str, set] = {}
        self._global: set = set()

    def subscribe(self, run_id: str | None) -> asyncio.Queue:
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            (self._global if run_id is None else self._subs.setdefault(run_id, set())).add((loop, q))
        return q

    def unsubscribe(self, run_id: str | None, q: asyncio.Queue) -> None:
        with self._lock:
            target = self._global if run_id is None else self._subs.get(run_id, set())
            for item in list(target):
                if item[1] is q:
                    target.discard(item)

    def _send(self, subs, ev):
        for loop, q in list(subs):
            try:
                loop.call_soon_threadsafe(q.put_nowait, ev)
            except RuntimeError:
                pass  # loop closed

    def publish(self, run_id: str, ev: dict) -> None:
        with self._lock:
            subs = set(self._subs.get(run_id, set()))
        self._send(subs, ev)

    def publish_global(self, ev: dict) -> None:
        with self._lock:
            subs = set(self._global)
        self._send(subs, ev)


BUS = Bus()


class Clock:
    """Wall clock, or a shifted clock for seeding history at past timestamps."""

    def __init__(self, base: datetime | None = None):
        self.base = base
        self.t0 = time.monotonic()

    def now(self) -> datetime:
        if self.base is None:
            return datetime.now(timezone.utc)
        return self.base + timedelta(seconds=time.monotonic() - self.t0)

    def iso(self) -> str:
        return self.now().isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Emitter:
    def __init__(self, run_id: str, clock: Clock, pace_ms: int = 0, publish: bool = True):
        self.run_id = run_id
        self.clock = clock
        self.pace_ms = pace_ms
        self.publish = publish
        with db.conn() as con:
            r = con.execute("SELECT COALESCE(MAX(seq), 0) AS m FROM run_events WHERE run_id=?", (run_id,)).fetchone()
            self.seq = int(r["m"])

    def emit(self, event: str, data: dict) -> dict:
        self.seq += 1
        ev = {"id": self.seq, "run_id": self.run_id, "event": event, "ts": self.clock.iso(), "data": data}
        with db.tx() as con:
            con.execute("INSERT INTO run_events (run_id, seq, ts, event, data) VALUES (?,?,?,?,?)",
                        (self.run_id, self.seq, ev["ts"], event, db.dumps(data)))
        if self.publish:
            BUS.publish(self.run_id, ev)
        return ev

    def tick(self, factor: float = 0.12) -> None:
        """Small pause between visible events so the live view is watchable (display pacing)."""
        if self.pace_ms > 0:
            time.sleep(min(0.09, self.pace_ms * factor / 1000.0))


def load_events(run_id: str, after_seq: int = 0) -> list[dict]:
    with db.conn() as con:
        return [{"id": r["seq"], "run_id": run_id, "event": r["event"], "ts": r["ts"], "data": db.loads(r["data"], {})}
                for r in con.execute("SELECT seq, event, ts, data FROM run_events WHERE run_id=? AND seq>? ORDER BY seq",
                                     (run_id, after_seq))]
