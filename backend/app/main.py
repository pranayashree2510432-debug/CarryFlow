from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load configuration from .env if present
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.app.translator import (
    CANONICAL_FIELDS,
    FieldTranslator,
    MappingResult,
    get_translator,
)
from backend.app.passport import (
    FactCreateBody,
    FactUpdateBody,
    FactConfirmBody,
    FactPermissionsBody,
    list_passport_facts,
    add_or_version_fact,
    update_fact_value,
    confirm_fact_version,
    update_fact_permissions,
)

ROOT = Path(__file__).resolve().parents[2]
DB = Path(os.getenv("CARRYFLOW_DB", str(ROOT / "carryflow.db")))
NOW = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
ALLOWED = {"http://127.0.0.1:8000", "http://localhost:8000"}


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init()
    yield


app = FastAPI(title="CarryFlow", version="0.1.0", lifespan=lifespan)


class ResolveBody(BaseModel):
    fact_id: str
    version: int


class StartBody(BaseModel):
    user_goal: str = "Prepare two internship applications using my profile. Do not submit anything without asking."


class FillBody(BaseModel):
    origin: str
    observed: dict[str, str] = Field(default_factory=dict)


class TranslateBody(BaseModel):
    label: str
    description: str | None = None


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=10.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init() -> None:
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS facts(id TEXT, key TEXT, semantic_type TEXT, value TEXT, source_url TEXT, source_label TEXT, collected_at TEXT, version INTEGER, confidence REAL, verification TEXT, permitted_origins TEXT, purpose TEXT, user_confirmed INTEGER, last_confirmed_at TEXT, PRIMARY KEY(id,version));
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, kind TEXT, title TEXT, detail TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS receipts(id TEXT PRIMARY KEY, origin TEXT, source_fact_id TEXT, source_version INTEGER, source_field TEXT, destination_field TEXT, semantic_type TEXT, mapping_type TEXT, reason TEXT, confidence REAL, permission TEXT, status TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE, origin TEXT, action_type TEXT, payload_fingerprint TEXT, status TEXT, observed_result TEXT, verification TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS conflicts(id TEXT PRIMARY KEY, fact_id TEXT, old_version INTEGER, new_version INTEGER, resolved INTEGER DEFAULT 0, resolution_version INTEGER);
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        """)
        # Upgrade schema if needed
        info = c.execute("PRAGMA table_info(facts)").fetchall()
        if not next((col[5] for col in info if col[1] == "version"), 0):
            c.execute("ALTER TABLE facts RENAME TO facts_legacy")
            c.execute("CREATE TABLE facts(id TEXT, key TEXT, semantic_type TEXT, value TEXT, source_url TEXT, source_label TEXT, collected_at TEXT, version INTEGER, confidence REAL, verification TEXT, permitted_origins TEXT, purpose TEXT, user_confirmed INTEGER, last_confirmed_at TEXT, PRIMARY KEY(id,version))")
            c.execute("INSERT INTO facts(id, key, semantic_type, value, source_url, source_label, collected_at, version, confidence, verification, permitted_origins, purpose, user_confirmed) SELECT * FROM facts_legacy")
            c.execute("DROP TABLE facts_legacy")
        fact_columns = {col[1] for col in c.execute("PRAGMA table_info(facts)")}
        if "last_confirmed_at" not in fact_columns:
            c.execute("ALTER TABLE facts ADD COLUMN last_confirmed_at TEXT")
        action_columns = {col[1] for col in c.execute("PRAGMA table_info(actions)")}
        if "preconditions" not in action_columns:
            c.execute("ALTER TABLE actions ADD COLUMN preconditions TEXT NOT NULL DEFAULT '{}'")
        c.execute("INSERT OR IGNORE INTO meta VALUES('workflow_id',?)", (str(uuid.uuid4()),))
        c.execute("INSERT OR IGNORE INTO meta VALUES('status','PENDING')")
        c.execute("INSERT OR IGNORE INTO meta VALUES('current_origin','http://127.0.0.1:8000/portal/source')")
        c.execute("INSERT OR IGNORE INTO meta VALUES('user_goal',?)", (StartBody().user_goal,))


def startup() -> None:
    init()


def event(c: sqlite3.Connection, kind: str, title: str, detail: str = "") -> None:
    c.execute("INSERT INTO events VALUES(?,?,?,?,?)", (str(uuid.uuid4()), kind, title, detail, NOW()))


FACTS = [
    ("full_name", "person.name", "Aarav Mehta", "Full name", .99),
    ("email", "person.email", "aarav.mehta@example.test", "Email address", .99),
    ("phone", "person.phone", "9876543210", "Phone number", .99),
    ("education", "education.degree", "B.Tech Information Technology", "Degree", .97),
    ("graduation_year", "education.graduation_year", "2027", "Graduation year", .98),
    ("skills", "skills.technical", "Python, React, SQL", "Technical skills", .96),
    ("current_address", "address.current", "12 Lake View Road, Bengaluru", "Current address", .96),
    ("permanent_address", "address.permanent", "44 Park Street, Mysuru", "Permanent address", .96),
]
PORTALS = {
    "a": {"name": "Northstar Internships", "url": "http://127.0.0.1:8000/portal/a", "fields": [
        ("candidate_name", "Candidate name", "person.name"), ("academic_background", "Academic background", "education.degree"), ("expected_completion", "Expected completion", "education.graduation_year"), ("technical_competencies", "Technical competencies", "skills.technical"), ("contact_email", "Contact email", "person.email"), ("phone", "Phone number", "person.phone")]},
    "b": {"name": "Summit Talent", "url": "http://127.0.0.1:8000/portal/b", "fields": [
        ("applicant_name", "Applicant name", "person.name"), ("highest_qualification", "Highest qualification", "education.degree"), ("passing_year", "Passing year", "education.graduation_year"), ("core_competencies", "Core competencies", "skills.technical"), ("current_location", "Current location", "address.current"), ("location", "Location", "address.unknown")]}
}


def get_current_facts(c: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    """Return the active fact for each semantic type, honoring conflict resolutions."""
    resolved = {
        row["fact_id"]: row["resolution_version"]
        for row in c.execute("SELECT fact_id, resolution_version FROM conflicts WHERE resolved=1 ORDER BY rowid ASC").fetchall()
    }
    all_facts = c.execute("SELECT * FROM facts ORDER BY id, version DESC").fetchall()
    by_id: dict[str, list[sqlite3.Row]] = {}
    for f in all_facts:
        by_id.setdefault(f["id"], []).append(f)
    current: dict[str, sqlite3.Row] = {}
    for fid, f_list in by_id.items():
        chosen = None
        if fid in resolved and resolved[fid] is not None:
            chosen = next((f for f in f_list if f["version"] == resolved[fid]), None)
        if not chosen:
            non_superseded = [f for f in f_list if f["verification"] != "SUPERSEDED"]
            chosen = non_superseded[0] if non_superseded else f_list[0]
        if chosen:
            current[chosen["semantic_type"]] = chosen
    return current


app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")


@app.get("/portal/{which}", response_class=HTMLResponse)
def portal(which: str) -> str:
    if which not in {"source", "a", "b"}:
        raise HTTPException(404)
    if which == "source":
        fields = [(k, label, val) for k, label, val, _, _ in FACTS]
        title, sub = "Student profile", "Your information, ready to carry forward"
    else:
        p = PORTALS[which]
        fields = [(k, label, "") for k, label, _ in p["fields"]]
        title, sub = p["name"], "Internship application · Draft"
    html = [f'<main class="portal portal-{which}"><div class="pbrand"><span>✳</span> {"CARRYFLOW PROFILE" if which=="source" else "CAREERS / INTERNSHIPS"}</div><h1>{title}</h1><p>{sub}</p><section class="pform">']
    for k, label, val in fields:
        html.append(f'<label for="{k}">{label}<input id="{k}" name="{k}" value="{val}" autocomplete="off"></label>')
    html.append('<div class="pfoot"><span id="save-note">Draft saved locally</span><button type="button" id="submit-application">Submit application</button></div></section><p class="safe-note">Demo site · Synthetic student data · Submission stays under your control</p></main>')
    html.append('<script>document.querySelectorAll("input").forEach(i=>i.addEventListener("input",()=>{document.querySelector("#save-note").textContent="Unsaved changes"}));document.querySelector("#submit-application").onclick=()=>{document.querySelector("#save-note").textContent="Submission requires CarryFlow approval"};</script>')
    return "<!doctype html><meta charset=utf-8><link rel=stylesheet href=/static/portal.css><link rel=stylesheet href=/static/portal-variants.css>" + "".join(html)


@app.get("/api/state")
def state() -> dict[str, Any]:
    with db() as c:
        facts = [dict(r) for r in c.execute("SELECT * FROM facts ORDER BY key,version")]
        events = [dict(r) for r in c.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT 40")]
        receipts = [dict(r) for r in c.execute("SELECT * FROM receipts ORDER BY created_at DESC")]
        actions = [dict(r) for r in c.execute("SELECT * FROM actions ORDER BY created_at DESC")]
        conflicts = [dict(r) for r in c.execute("SELECT * FROM conflicts WHERE resolved=0")]
        meta = dict(c.execute("SELECT key,value FROM meta"))
    return {"facts": facts, "events": events, "receipts": receipts, "actions": actions, "conflicts": conflicts, "meta": meta, "portals": PORTALS}


# --- Smart Personal Data Passport Endpoints ---

@app.get("/api/passport")
def get_passport() -> dict[str, Any]:
    with db() as c:
        return list_passport_facts(c)


@app.post("/api/passport/fact")
def create_passport_fact(body: FactCreateBody) -> dict[str, Any]:
    with db() as c:
        res = add_or_version_fact(c, body)
        event(c, "passport", f"Fact '{body.label}' updated", f"Version {res['version']} recorded with status {res['verification']}.")
        return res


@app.put("/api/passport/fact/{fact_id}")
def update_passport_fact(fact_id: str, body: FactUpdateBody) -> dict[str, Any]:
    with db() as c:
        res = update_fact_value(c, fact_id, body)
        event(c, "passport", f"Fact '{fact_id}' edited", f"Action: {res['action']} (v{res['version']}).")
        return res


@app.post("/api/passport/fact/{fact_id}/confirm")
def confirm_passport_fact(fact_id: str, body: FactConfirmBody | None = None) -> dict[str, Any]:
    with db() as c:
        target_version = body.version if body else None
        res = confirm_fact_version(c, fact_id, target_version)
        event(c, "approval", f"Fact '{fact_id}' confirmed", f"User confirmed version {res['version']}.")
        return res


@app.post("/api/passport/fact/{fact_id}/permissions")
def update_passport_permissions(fact_id: str, body: FactPermissionsBody) -> dict[str, Any]:
    with db() as c:
        res = update_fact_permissions(c, fact_id, body)
        event(c, "passport", f"Permissions updated for '{fact_id}'", f"Origins allowed: {', '.join(body.permitted_origins)}.")
        return res


@app.post("/api/reset")
def reset() -> dict[str, bool]:
    with db() as c:
        for t in ("facts", "events", "receipts", "actions", "conflicts"):
            c.execute(f"DELETE FROM {t}")
        c.execute("UPDATE meta SET value=? WHERE key='workflow_id'", (str(uuid.uuid4()),))
        c.execute("UPDATE meta SET value='PENDING' WHERE key='status'")
        c.execute("UPDATE meta SET value=? WHERE key='current_origin'", (PORTALS["a"]["url"],))
        event(c, "system", "Demo reset", "Synthetic data cleared.")
    return {"ok": True}


@app.post("/api/start")
def start(body: StartBody | None = None) -> dict[str, Any]:
    goal = body.user_goal.strip() if body and body.user_goal.strip() else StartBody().user_goal
    with db() as c:
        if c.execute("SELECT count(*) FROM facts").fetchone()[0] == 0:
            now_iso = NOW()
            for key, typ, value, label, conf in FACTS:
                c.execute(
                    "INSERT INTO facts(id, key, semantic_type, value, source_url, source_label, collected_at, version, confidence, verification, permitted_origins, purpose, user_confirmed, last_confirmed_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (key, key, typ, value, PORTALS["a"]["url"].replace("/a", "/source"), label, now_iso, 1, conf, "VERIFIED", json.dumps(sorted(ALLOWED)), "internship application preparation", 1, now_iso)
                )
            event(c, "extract", "Profile facts verified", "8 synthetic facts recorded with source labels and permission scope.")
        c.execute("UPDATE meta SET value='RUNNING' WHERE key='status'")
        c.execute("UPDATE meta SET value=? WHERE key='user_goal'", (goal,))
        c.execute("UPDATE meta SET value=? WHERE key='current_origin'", (PORTALS["a"]["url"],))
        event(c, "checkpoint", "Workflow started", "Two local internship portals are in scope. Submissions require approval.")
    return state()


def semantic_for(label: str) -> str:
    """Intelligent semantic mapping for a field label."""
    res = get_translator().translate(label)
    return res.semantic_type or ("address.unknown" if "location" in label.casefold() else "unknown")


@app.post("/api/translate", response_model=MappingResult)
def translate_field(body: TranslateBody) -> MappingResult:
    """Direct field translation endpoint using Intelligent Field Translator."""
    return get_translator().translate(label=body.label, description=body.description)


@app.post("/api/prepare/{portal_key}")
def prepare(portal_key: str) -> dict[str, Any]:
    if portal_key not in PORTALS:
        raise HTTPException(404)
    origin, fields = PORTALS[portal_key]["url"], PORTALS[portal_key]["fields"]
    destination_origin = origin.split("/portal/")[0]
    translator = get_translator()
    with db() as c:
        c.execute("UPDATE meta SET value=? WHERE key='current_origin'", (origin,))
        current_facts = get_current_facts(c)
        for field, label, declared in fields:
            mapping = translator.translate(label)
            sem = mapping.semantic_type or declared

            # Check for ambiguous fields or fields requiring user review
            if sem == "address.unknown" or mapping.canonical_field is None or mapping.requires_user_confirmation:
                c.execute(
                    "INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        origin,
                        "",
                        0,
                        "Unresolved location" if sem == "address.unknown" else "Unresolved source",
                        field,
                        sem,
                        "AMBIGUOUS" if sem == "address.unknown" else "REQUIRES_USER",
                        mapping.explanation,
                        mapping.confidence,
                        "REQUIRES_USER",
                        "WAITING_FOR_USER",
                        NOW(),
                    ),
                )
                continue

            fact = current_facts.get(sem)
            if not fact:
                continue

            # USER CONTROL & SHARING CHECKS:
            # 1. Unconfirmed facts must NOT be automatically proposed/shared
            if not fact["user_confirmed"] or fact["verification"] in {"UNVERIFIED", "UNVERIFIED_CONFLICT"}:
                c.execute(
                    "INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid.uuid4()),
                        origin,
                        fact["id"],
                        fact["version"],
                        fact["source_label"],
                        field,
                        sem,
                        "UNCONFIRMED_FACT",
                        f"'{fact['source_label']}' is not confirmed by the user. Confirmation required before sharing.",
                        fact["confidence"],
                        "REQUIRES_USER",
                        "WAITING_FOR_USER",
                        NOW(),
                    ),
                )
                continue

            # 2. Check origin sharing permission
            permitted = destination_origin in json.loads(fact["permitted_origins"])
            reason = f"'{label}' refers to {sem.replace('.', ' ')}; mapped from verified profile field '{fact['source_label']}'."
            status = "APPROVED" if permitted else "DENIED"
            c.execute(
                "INSERT INTO receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    origin,
                    fact["id"],
                    fact["version"],
                    fact["source_label"],
                    field,
                    sem,
                    "SEMANTIC_EQUIVALENT",
                    reason,
                    min(fact["confidence"], mapping.confidence),
                    status,
                    "PROPOSED" if permitted else "BLOCKED",
                    NOW(),
                ),
            )
        event(c, "handoff", "Handoff receipts prepared", f"{PORTALS[portal_key]['name']}: semantic mappings recorded; ambiguous fields held for review.")
    return state()


@app.post("/api/resolve")
def resolve(body: ResolveBody) -> dict[str, Any]:
    with db() as c:
        row = c.execute("SELECT * FROM facts WHERE id=? AND version=?", (body.fact_id, body.version)).fetchone()
        if not row:
            raise HTTPException(404, "Fact version not found")
        now_iso = NOW()
        c.execute("UPDATE facts SET verification='USER_CONFIRMED',user_confirmed=1,last_confirmed_at=? WHERE id=? AND version=?", (now_iso, body.fact_id, body.version))
        c.execute("UPDATE facts SET verification='SUPERSEDED' WHERE id=? AND version!=? AND verification='UNVERIFIED_CONFLICT'", (body.fact_id, body.version))
        c.execute("UPDATE conflicts SET resolved=1,resolution_version=? WHERE fact_id=? AND resolved=0", (body.version, body.fact_id))
        event(c, "approval", "Conflict resolved", f"User selected {row['source_label']} version {body.version}; previous versions retained.")
    return state()


@app.post("/api/conflict")
def conflict() -> dict[str, Any]:
    with db() as c:
        row = c.execute("SELECT * FROM facts WHERE id='phone' ORDER BY version DESC LIMIT 1").fetchone()
        old = row["version"] if row else 0
        ver = old + 1
        now_iso = NOW()
        c.execute(
            "INSERT INTO facts(id, key, semantic_type, value, source_url, source_label, collected_at, version, confidence, verification, permitted_origins, purpose, user_confirmed, last_confirmed_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("phone", "phone", "person.phone", "9123456780", PORTALS["b"]["url"], "Updated phone number", now_iso, ver, .88, "UNVERIFIED_CONFLICT", json.dumps(sorted(ALLOWED)), "internship application preparation", 0, None)
        )
        c.execute("INSERT INTO conflicts VALUES(?,?,?,?,0,NULL)", (str(uuid.uuid4()), "phone", old, ver))
        event(c, "conflict", "Conflicting phone number detected", "The latest profile visit differs from the saved value. Choose a version before reuse.")
    return state()


@app.post("/api/fill")
def fill(body: FillBody) -> dict[str, Any]:
    if body.origin not in {p["url"] for p in PORTALS.values()}:
        raise HTTPException(403, "Origin is outside the approved local demo scope")
    with db() as c:
        current = get_current_facts(c)
        for rec in c.execute("SELECT * FROM receipts WHERE origin=? AND status='PROPOSED'", (body.origin,)).fetchall():
            fact = current.get(rec["semantic_type"])
            if not fact or fact["verification"] in {"UNVERIFIED", "UNVERIFIED_CONFLICT"} or not fact["user_confirmed"]:
                continue
            key = f"{rec['origin']}|{rec['destination_field']}|{fact['id']}|{fact['version']}"
            fp = hashlib.sha256(fact["value"].encode("utf-8")).hexdigest()
            prior = c.execute("SELECT * FROM actions WHERE idempotency_key=?", (key,)).fetchone()
            observed = body.observed.get(rec["destination_field"])
            if prior and prior["status"] == "VERIFIED" and observed == fact["value"]:
                c.execute("UPDATE receipts SET status='VERIFIED' WHERE id=?", (rec["id"],))
                continue
            if prior and prior["status"] in {"PREPARED", "UNCERTAIN"}:
                c.execute("UPDATE actions SET status='UNCERTAIN',observed_result=? WHERE id=?", (observed or "not observed", prior["id"]))
                continue
            if rec["permission"] != "APPROVED":
                continue
            aid = str(uuid.uuid4())
            c.execute("INSERT OR IGNORE INTO actions(id,idempotency_key,origin,action_type,payload_fingerprint,status,observed_result,verification,created_at,preconditions) VALUES(?,?,?,?,?,?,?,?,?,?)", (aid, key, body.origin, "FILL_FIELD", fp, "PREPARED", "Prepared fill; waiting for verified field observation", "PENDING", NOW(), json.dumps({"receipt_id": rec["id"], "fact_version": fact["version"], "field_empty_or_matching": True})))
            if observed is not None:
                verified = observed == fact["value"]
                c.execute("UPDATE actions SET status=?,observed_result=?,verification=? WHERE idempotency_key=?", ("VERIFIED" if verified else "UNCERTAIN", "Field value observed" if verified else "Observed field does not match intended value", "VERIFIED" if verified else "UNCERTAIN", key))
                c.execute("UPDATE receipts SET status=? WHERE id=?", ("VERIFIED" if verified else "UNCERTAIN", rec["id"]))
        event(c, "action", "Page state recorded", "Observed form fields were reconciled with authorized mappings.")
    return state()


@app.post("/api/recover")
def recover(body: FillBody) -> dict[str, Any]:
    if body.origin not in {p["url"] for p in PORTALS.values()}:
        raise HTTPException(403, "Origin not approved")
    with db() as c:
        completed = 0
        uncertain = 0
        for a in c.execute("SELECT * FROM actions WHERE origin=?", (body.origin,)).fetchall():
            parts = a["idempotency_key"].split("|")
            field = parts[1] if len(parts) > 2 else ""
            observed = body.observed.get(field)
            if a["status"] == "VERIFIED" and observed:
                completed += 1
            elif a["status"] == "VERIFIED" and not observed:
                uncertain += 1
                c.execute("UPDATE actions SET status='UNCERTAIN',observed_result='Previously verified field is absent from the inspected page; user review required' WHERE id=?", (a["id"],))
            elif a["status"] in {"PREPARED", "UNCERTAIN"}:
                if observed:
                    uncertain += 1
                    c.execute("UPDATE actions SET status='UNCERTAIN',observed_result='Value exists after interruption; reconcile before any repeat' WHERE id=?", (a["id"],))
                else:
                    c.execute("UPDATE actions SET status='PENDING',observed_result='Field absent on inspected page; safe to prepare again' WHERE id=?", (a["id"],))
        event(c, "recovery", "Page inspected before resume", f"Observed {len(body.observed)} actual form values. {completed} verified actions already present; {uncertain} action(s) require reconciliation. No submission was replayed.")
        c.execute("UPDATE meta SET value='REQUIRES_RECONCILIATION' WHERE key='status'")
    return state()


@app.post("/api/submit/prepare")
def submit_prepare() -> dict[str, Any]:
    with db() as c:
        origin = c.execute("SELECT value FROM meta WHERE key='current_origin'").fetchone()[0]
        key = f"{origin}:FINAL_SUBMISSION:demo-application"
        existing = c.execute("SELECT * FROM actions WHERE idempotency_key=?", (key,)).fetchone()
        if not existing:
            c.execute("INSERT INTO actions(id,idempotency_key,origin,action_type,payload_fingerprint,status,observed_result,verification,created_at,preconditions) VALUES(?,?,?,?,?,?,?,?,?,?)", (str(uuid.uuid4()), key, origin, "FINAL_SUBMISSION", "demo-application", "PREPARED", "Awaiting explicit user approval", "PENDING", NOW(), json.dumps({"explicit_user_approval_required": True})))
            event(c, "approval", "Submission prepared", "Review the website and approve explicitly. Preparation did not submit the application.")
    return state()


@app.post("/api/submit/approve")
def submit_approve() -> dict[str, Any]:
    with db() as c:
        row = c.execute("SELECT * FROM actions WHERE action_type='FINAL_SUBMISSION' ORDER BY created_at DESC LIMIT 1").fetchone()
        if not row:
            raise HTTPException(409, "Prepare submission first")
        if row["status"] != "PREPARED":
            raise HTTPException(409, "Submission outcome is not safe to retry")
        # Demo page is not actually submitted; this records approval and a deterministic confirmation.
        c.execute("UPDATE actions SET status='VERIFIED',observed_result='Approved locally; demo confirmation CF-DEMO-2048',verification='VERIFIED' WHERE id=?", (row["id"],))
        c.execute("UPDATE meta SET value='COMPLETED' WHERE key='status'")
        event(c, "verified", "Demo submission approved", "Confirmation CF-DEMO-2048 recorded; demo site did not send data externally.")
    return state()
