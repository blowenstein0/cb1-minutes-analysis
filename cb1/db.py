"""Load extracted meeting JSON into DuckDB + parquet exports."""

import json
import re
from pathlib import Path

import duckdb

from cb1 import config

DDL = """
CREATE OR REPLACE TABLE meetings (
    meeting_id VARCHAR PRIMARY KEY, date DATE, meeting_type VARCHAR,
    location_or_platform VARCHAR, attendance_count INT, quorum_noted BOOLEAN,
    chair VARCHAR, is_revised BOOLEAN, date_source VARCHAR,
    date_confidence DOUBLE, source_files VARCHAR[],
    text_source VARCHAR, pages_minutes_body INT, pages_attachments_dropped INT,
    input_tokens INT, output_tokens INT, cost_usd DOUBLE, warnings VARCHAR[]
);
CREATE OR REPLACE TABLE licenses (
    meeting_id VARCHAR, applicant_name VARCHAR, dba VARCHAR, address VARCHAR,
    application_type VARCHAR, license_class VARCHAR, features VARCHAR[],
    committee_recommendation VARCHAR, board_action VARCHAR, source_snippet VARCHAR
);
CREATE OR REPLACE TABLE votes (
    meeting_id VARCHAR, motion_text VARCHAR, topic_category VARCHAR,
    mover VARCHAR, seconder VARCHAR, yes INT, no INT, abstain INT, recusal INT,
    outcome VARCHAR, unanimous BOOLEAN, conditions VARCHAR[], source_snippet VARCHAR
);
CREATE OR REPLACE TABLE speakers (
    meeting_id VARCHAR, name VARCHAR, affiliation VARCHAR, topic VARCHAR,
    position VARCHAR, source_snippet VARCHAR
);
CREATE OR REPLACE TABLE incidents (
    meeting_id VARCHAR, person_name VARCHAR, incident_date VARCHAR,
    location VARCHAR, severity VARCHAR, source_snippet VARCHAR
);
CREATE OR REPLACE TABLE cannabis (
    meeting_id VARCHAR, applicant_name VARCHAR, address VARCHAR,
    application_type VARCHAR, source_snippet VARCHAR
);
"""

TABLES = ("meetings", "licenses", "votes", "speakers", "incidents", "cannabis")

# People named in the traffic-incident record didn't choose to enter a public
# process the way speakers and licence applicants did, so the published parquet
# exports drop the person_name index and mask those names out of every
# free-text column. The names stay in the local DuckDB, which is gitignored, so
# eval matching still keys on them.
PARQUET_DROP = {"incidents": ("person_name",)}
NAME_PLACEHOLDER = "[name withheld]"
HONORIFIC = re.compile(r"^(?:Mr|Ms|Mrs|Dr)\.?\s+")

# extraction-JSON key -> (table, columns in DDL order, after meeting_id)
RECORD_INSERTS = {
    "liquor_licenses": ("licenses", (
        "applicant_name", "dba", "address", "application_type", "license_class",
        "features", "committee_recommendation", "board_action", "source_snippet",
    )),
    "votes": ("votes", (
        "motion_text", "topic_category", "mover", "seconder", "yes", "no",
        "abstain", "recusal", "outcome", "unanimous", "conditions", "source_snippet",
    )),
    "public_speakers": ("speakers", (
        "name", "affiliation", "topic", "position", "source_snippet",
    )),
    "traffic_incidents": ("incidents", (
        "person_name", "incident_date", "location", "severity", "source_snippet",
    )),
    "cannabis_licenses": ("cannabis", (
        "applicant_name", "address", "application_type", "source_snippet",
    )),
}


def _insert(con, table: str, cols: tuple, mid: str, record: dict) -> None:
    con.execute(
        f"INSERT INTO {table} VALUES ({','.join('?' * (len(cols) + 1))})",
        [mid] + [record.get(c) for c in cols],
    )


def _name_masker(con):
    """Build the redactor for the parquet exports.

    Matches whole names only, with and without an honorific. Surnames alone are
    deliberately left in: 'Meyer' is inside Havemeyer Street, 'Ramirez' names a
    park and a taqueria, and board member Adam Meyers is a different person.
    """
    names = {
        n for (n,) in con.execute(
            "SELECT DISTINCT person_name FROM incidents WHERE person_name IS NOT NULL"
        ).fetchall()
    }
    variants = {v for n in names for v in (n, HONORIFIC.sub("", n)) if v}
    if not variants:
        return lambda s: s
    # Case-insensitive: the minutes render some names in all-caps headings.
    pattern = re.compile(
        r"\b(?:%s)\b" % "|".join(
            re.escape(v) for v in sorted(variants, key=len, reverse=True)
        ),
        re.IGNORECASE,
    )
    return lambda s: s if s is None else pattern.sub(NAME_PLACEHOLDER, s)


def _export_columns(con, table: str) -> str:
    """Column list for a table's parquet export: dropped columns removed, text
    columns (and text arrays) routed through mask_names."""
    drop = PARQUET_DROP.get(table, ())
    out = []
    for name, dtype in con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position", [table]
    ).fetchall():
        if name in drop:
            continue
        if dtype == "VARCHAR":
            out.append(f'mask_names("{name}") AS "{name}"')
        elif dtype == "VARCHAR[]":
            out.append(f'list_transform("{name}", x -> mask_names(x)) AS "{name}"')
        else:
            out.append(f'"{name}"')
    return ", ".join(out)


def load_db(extracted_dir: Path | None = None, db_path: Path | None = None) -> dict:
    extracted_dir = extracted_dir or config.EXTRACTED_DIR
    db_path = db_path or (config.DB_DIR / "cb1.duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(extracted_dir.glob("cb1-*.json"))
    con = duckdb.connect(str(db_path))
    con.execute(DDL)

    for f in files:
        d = json.loads(f.read_text())
        m, meta = d["meeting"], d["extraction_meta"]
        mid = m["meeting_id"]
        con.execute(
            "INSERT INTO meetings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                mid, m["date"], m["meeting_type"], m.get("location_or_platform"),
                m.get("attendance_count"), m.get("quorum_noted"), m.get("chair"),
                m.get("is_revised"), m.get("date_source"), m.get("date_confidence"),
                m.get("source_files", []),
                meta["text_source"], meta["pages_minutes_body"],
                meta["pages_attachments_dropped"], meta["input_tokens"],
                meta["output_tokens"], meta["cost_usd"], meta.get("warnings", []),
            ],
        )
        for key, (table, cols) in RECORD_INSERTS.items():
            for r in d.get(key, []):
                _insert(con, table, cols, mid, r)

    overrides_path = config.DATA_DIR / "vote_overrides.json"
    if overrides_path.exists():
        from cb1.models import Vote

        loaded = {r[0] for r in con.execute("SELECT meeting_id FROM meetings").fetchall()}
        entries = [
            e for e in json.loads(overrides_path.read_text())["add"]
            if e["meeting_id"] in loaded
        ]
        table, cols = RECORD_INSERTS["votes"]
        for e in entries:
            r = Vote.model_validate(e["vote"]).model_dump()
            _insert(con, table, cols, e["meeting_id"], r)
        print(f"load-db: applied {len(entries)} vote overrides")

    con.create_function("mask_names", _name_masker(con), ["VARCHAR"], "VARCHAR")

    counts = {}
    for t in TABLES:
        counts[t] = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        con.execute(
            f"COPY (SELECT {_export_columns(con, t)} FROM {t}) "
            f"TO '{db_path.parent / (t + '.parquet')}' (FORMAT PARQUET)"
        )
    con.close()
    print(f"load-db: {counts} -> {db_path} (+ parquet)")
    return counts
