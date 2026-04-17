"""
Database layer for Codex app.
Uses SQLite for local, persistent storage.
Supports multiple user profiles on the same machine.
"""

import sqlite3
import os
import json

_home_db = os.path.join(os.path.expanduser("~"), ".career_coach", "career_coach.db")
os.makedirs(os.path.dirname(_home_db), exist_ok=True)

DB_PATH = _home_db


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        try:
            conn.execute("PRAGMA journal_mode=DELETE")
        except Exception:
            pass
    return conn


def _safe_add_column(conn, table, column, definition):
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    except Exception:
        pass


def init_db():
    with get_db() as conn:
        conn.executescript("""
            -- ── PROFILES ─────────────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS profiles (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                name                TEXT NOT NULL DEFAULT 'Default',
                candidate_name      TEXT DEFAULT '',
                candidate_email     TEXT DEFAULT '',
                candidate_phone     TEXT DEFAULT '',
                candidate_linkedin  TEXT DEFAULT '',
                career_summary      TEXT DEFAULT '',
                resume_sample       TEXT DEFAULT '',
                cover_letter_sample TEXT DEFAULT '',
                created_at          TEXT DEFAULT (datetime('now'))
            );

            -- ── CANDIDATE PROFILE ────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS profile_experience (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id   INTEGER NOT NULL DEFAULT 1,
                company      TEXT NOT NULL,
                title        TEXT NOT NULL,
                start_date   TEXT DEFAULT '',
                end_date     TEXT DEFAULT '',
                is_current   INTEGER DEFAULT 0,
                location     TEXT DEFAULT '',
                description  TEXT DEFAULT '',
                day_to_day   TEXT DEFAULT '',
                achievements TEXT DEFAULT '[]',
                skills       TEXT DEFAULT '[]',
                sort_order   INTEGER DEFAULT 0,
                created_at   TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS profile_projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id  INTEGER NOT NULL DEFAULT 1,
                name        TEXT NOT NULL,
                role        TEXT DEFAULT '',
                company     TEXT DEFAULT '',
                description TEXT DEFAULT '',
                outcome     TEXT DEFAULT '',
                tech_stack  TEXT DEFAULT '[]',
                metrics     TEXT DEFAULT '',
                link        TEXT DEFAULT '',
                featured    INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS profile_skills (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id  INTEGER NOT NULL DEFAULT 1,
                name        TEXT NOT NULL,
                category    TEXT DEFAULT 'Technical',
                proficiency TEXT DEFAULT 'Proficient',
                notes       TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS profile_education (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id  INTEGER NOT NULL DEFAULT 1,
                institution TEXT NOT NULL,
                degree      TEXT DEFAULT '',
                field       TEXT DEFAULT '',
                start_year  TEXT DEFAULT '',
                end_year    TEXT DEFAULT '',
                gpa         TEXT DEFAULT '',
                notes       TEXT DEFAULT '',
                sort_order  INTEGER DEFAULT 0
            );

            -- ── APPLICATIONS ──────────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS applications (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id       INTEGER NOT NULL DEFAULT 1,
                company          TEXT NOT NULL,
                role             TEXT NOT NULL,
                job_url          TEXT DEFAULT '',
                status           TEXT DEFAULT 'Saved',
                date_applied     TEXT DEFAULT '',
                date_updated     TEXT DEFAULT (datetime('now')),
                job_description  TEXT DEFAULT '',
                notes            TEXT DEFAULT '',
                cover_letter     TEXT DEFAULT '',
                resume_bullets   TEXT DEFAULT '',
                salary_range     TEXT DEFAULT '',
                contact_name     TEXT DEFAULT '',
                contact_email    TEXT DEFAULT '',
                status_history   TEXT DEFAULT '[]',
                created_at       TEXT DEFAULT (datetime('now'))
            );

            -- ── SETTINGS (global) ─────────────────────────────────────────────
            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            -- ── EXPERIENCE SUB-PROJECTS ──────────────────────────────────────
            CREATE TABLE IF NOT EXISTS profile_experience_projects (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                experience_id INTEGER NOT NULL,
                title         TEXT NOT NULL,
                description   TEXT DEFAULT '',
                sort_order    INTEGER DEFAULT 0,
                FOREIGN KEY (experience_id) REFERENCES profile_experience(id) ON DELETE CASCADE
            );
        """)

        # Schema migrations — safe to run every time on existing DBs
        _safe_add_column(conn, "profile_experience", "profile_id", "INTEGER NOT NULL DEFAULT 1")
        _safe_add_column(conn, "profile_projects",   "profile_id", "INTEGER NOT NULL DEFAULT 1")
        _safe_add_column(conn, "profile_skills",     "profile_id", "INTEGER NOT NULL DEFAULT 1")
        _safe_add_column(conn, "profile_education",  "profile_id", "INTEGER NOT NULL DEFAULT 1")
        _safe_add_column(conn, "applications",       "profile_id", "INTEGER NOT NULL DEFAULT 1")
        _safe_add_column(conn, "applications",       "status_history", "TEXT DEFAULT '[]'")

        # Create default profile from existing settings if none exist yet
        count = conn.execute("SELECT COUNT(*) as c FROM profiles").fetchone()["c"]
        if count == 0:
            def _gs(k):
                r = conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
                return (r["value"] or "") if r else ""

            cname = _gs("candidate_name")
            conn.execute("""
                INSERT INTO profiles
                    (id, name, candidate_name, candidate_email, candidate_phone,
                     candidate_linkedin, career_summary, resume_sample, cover_letter_sample)
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cname or "Default",
                cname,
                _gs("candidate_email"),
                _gs("candidate_phone"),
                _gs("candidate_linkedin"),
                _gs("career_summary"),
                _gs("resume_sample"),
                _gs("cover_letter_sample"),
            ))
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('active_profile_id', '1')")

        # Ensure active_profile_id is always set
        active = conn.execute("SELECT value FROM settings WHERE key='active_profile_id'").fetchone()
        if not active or not active["value"]:
            first = conn.execute("SELECT id FROM profiles ORDER BY id LIMIT 1").fetchone()
            if first:
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_profile_id', ?)",
                    (str(first["id"]),)
                )

    print(f"[DB] Initialized at: {DB_PATH}")


# ── PROFILES ──────────────────────────────────────────────────────────────────

def get_profiles():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM profiles ORDER BY created_at").fetchall()
        return [dict(r) for r in rows]


def get_profile(profile_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id=?", (profile_id,)).fetchone()
        return dict(row) if row else None


def create_profile(data):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO profiles
                (name, candidate_name, candidate_email, candidate_phone,
                 candidate_linkedin, career_summary, resume_sample, cover_letter_sample)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("name", "New Profile"),
            data.get("candidate_name", ""),
            data.get("candidate_email", ""),
            data.get("candidate_phone", ""),
            data.get("candidate_linkedin", ""),
            data.get("career_summary", ""),
            data.get("resume_sample", ""),
            data.get("cover_letter_sample", ""),
        ))
        return cur.lastrowid


def update_profile(profile_id, data):
    with get_db() as conn:
        conn.execute("""
            UPDATE profiles SET
                name=?, candidate_name=?, candidate_email=?, candidate_phone=?,
                candidate_linkedin=?, career_summary=?, resume_sample=?, cover_letter_sample=?
            WHERE id=?
        """, (
            data.get("name", ""),
            data.get("candidate_name", ""),
            data.get("candidate_email", ""),
            data.get("candidate_phone", ""),
            data.get("candidate_linkedin", ""),
            data.get("career_summary", ""),
            data.get("resume_sample", ""),
            data.get("cover_letter_sample", ""),
            profile_id,
        ))


def delete_profile(profile_id):
    with get_db() as conn:
        exp_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM profile_experience WHERE profile_id=?", (profile_id,)
        ).fetchall()]
        for eid in exp_ids:
            conn.execute("DELETE FROM profile_experience_projects WHERE experience_id=?", (eid,))
        conn.execute("DELETE FROM profile_experience WHERE profile_id=?", (profile_id,))
        conn.execute("DELETE FROM profile_projects   WHERE profile_id=?", (profile_id,))
        conn.execute("DELETE FROM profile_skills     WHERE profile_id=?", (profile_id,))
        conn.execute("DELETE FROM profile_education  WHERE profile_id=?", (profile_id,))
        conn.execute("DELETE FROM applications       WHERE profile_id=?", (profile_id,))
        conn.execute("DELETE FROM profiles           WHERE id=?",         (profile_id,))


def get_active_profile_id():
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key='active_profile_id'").fetchone()
        if row and row["value"]:
            try:
                return int(row["value"])
            except (ValueError, TypeError):
                pass
        first = conn.execute("SELECT id FROM profiles ORDER BY id LIMIT 1").fetchone()
        return first["id"] if first else 1


def set_active_profile_id(profile_id):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_profile_id', ?)",
            (str(profile_id),)
        )


# ── PROFILE: EXPERIENCE ───────────────────────────────────────────────────────

def get_experiences(profile_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM profile_experience WHERE profile_id=? ORDER BY is_current DESC, start_date DESC, sort_order",
            (profile_id,)
        ).fetchall()
        items = [dict(r) for r in rows]
        for i in items:
            i["achievements"] = json.loads(i["achievements"]) if i["achievements"] else []
            i["skills"]       = json.loads(i["skills"])       if i["skills"]       else []
        return items


def get_experience(id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM profile_experience WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["achievements"] = json.loads(item["achievements"]) if item["achievements"] else []
        item["skills"]       = json.loads(item["skills"])       if item["skills"]       else []
        return item


def create_experience(data, profile_id=1):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO profile_experience
                (profile_id, company, title, start_date, end_date, is_current, location,
                 description, day_to_day, achievements, skills)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            profile_id,
            data.get("company", ""),
            data.get("title", ""),
            data.get("start_date", ""),
            data.get("end_date", ""),
            1 if data.get("is_current") else 0,
            data.get("location", ""),
            data.get("description", ""),
            data.get("day_to_day", ""),
            json.dumps(data.get("achievements", [])),
            json.dumps(data.get("skills", [])),
        ))
        return cur.lastrowid


def update_experience(id, data):
    with get_db() as conn:
        conn.execute("""
            UPDATE profile_experience SET
                company=?, title=?, start_date=?, end_date=?, is_current=?, location=?,
                description=?, day_to_day=?, achievements=?, skills=?
            WHERE id=?
        """, (
            data.get("company", ""),
            data.get("title", ""),
            data.get("start_date", ""),
            data.get("end_date", ""),
            1 if data.get("is_current") else 0,
            data.get("location", ""),
            data.get("description", ""),
            data.get("day_to_day", ""),
            json.dumps(data.get("achievements", [])),
            json.dumps(data.get("skills", [])),
            id,
        ))


def delete_experience(id):
    with get_db() as conn:
        conn.execute("DELETE FROM profile_experience_projects WHERE experience_id=?", (id,))
        conn.execute("DELETE FROM profile_experience WHERE id=?", (id,))


# ── PROFILE: EXPERIENCE PROJECTS ─────────────────────────────────────────────

def get_experience_projects(experience_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM profile_experience_projects WHERE experience_id=? ORDER BY sort_order, id",
            (experience_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_experience_projects(profile_id):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT ep.* FROM profile_experience_projects ep
               JOIN profile_experience e ON ep.experience_id = e.id
               WHERE e.profile_id = ?
               ORDER BY ep.experience_id, ep.sort_order, ep.id""",
            (profile_id,)
        ).fetchall()
        result = {}
        for r in rows:
            d = dict(r)
            eid = d["experience_id"]
            result.setdefault(eid, []).append(d)
        return result


def create_experience_project(experience_id, data):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO profile_experience_projects (experience_id, title, description, sort_order) VALUES (?,?,?,?)",
            (experience_id, data.get("title", ""), data.get("description", ""), data.get("sort_order", 0))
        )
        return cur.lastrowid


def update_experience_project(id, data):
    with get_db() as conn:
        conn.execute(
            "UPDATE profile_experience_projects SET title=?, description=?, sort_order=? WHERE id=?",
            (data.get("title", ""), data.get("description", ""), data.get("sort_order", 0), id)
        )


def delete_experience_project(id):
    with get_db() as conn:
        conn.execute("DELETE FROM profile_experience_projects WHERE id=?", (id,))


# ── PROFILE: PROJECTS ─────────────────────────────────────────────────────────

def get_projects(profile_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM profile_projects WHERE profile_id=? ORDER BY featured DESC, created_at DESC",
            (profile_id,)
        ).fetchall()
        items = [dict(r) for r in rows]
        for i in items:
            i["tech_stack"] = json.loads(i["tech_stack"]) if i["tech_stack"] else []
        return items


def get_project(id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM profile_projects WHERE id=?", (id,)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["tech_stack"] = json.loads(item["tech_stack"]) if item["tech_stack"] else []
        return item


def create_project(data, profile_id=1):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO profile_projects
                (profile_id, name, role, company, description, outcome, tech_stack, metrics, link, featured)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            profile_id,
            data.get("name", ""),
            data.get("role", ""),
            data.get("company", ""),
            data.get("description", ""),
            data.get("outcome", ""),
            json.dumps(data.get("tech_stack", [])),
            data.get("metrics", ""),
            data.get("link", ""),
            1 if data.get("featured") else 0,
        ))
        return cur.lastrowid


def update_project(id, data):
    with get_db() as conn:
        conn.execute("""
            UPDATE profile_projects SET
                name=?, role=?, company=?, description=?, outcome=?,
                tech_stack=?, metrics=?, link=?, featured=?
            WHERE id=?
        """, (
            data.get("name", ""),
            data.get("role", ""),
            data.get("company", ""),
            data.get("description", ""),
            data.get("outcome", ""),
            json.dumps(data.get("tech_stack", [])),
            data.get("metrics", ""),
            data.get("link", ""),
            1 if data.get("featured") else 0,
            id,
        ))


def delete_project(id):
    with get_db() as conn:
        conn.execute("DELETE FROM profile_projects WHERE id=?", (id,))


# ── PROFILE: SKILLS ───────────────────────────────────────────────────────────

def get_skills(profile_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM profile_skills WHERE profile_id=? ORDER BY category, name",
            (profile_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def create_skill(data, profile_id=1):
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO profile_skills (profile_id, name, category, proficiency, notes) VALUES (?,?,?,?,?)",
            (profile_id, data.get("name", ""), data.get("category", "Technical"),
             data.get("proficiency", "Proficient"), data.get("notes", ""))
        )
        return cur.lastrowid


def update_skill(id, data):
    with get_db() as conn:
        conn.execute(
            "UPDATE profile_skills SET name=?, category=?, proficiency=?, notes=? WHERE id=?",
            (data.get("name", ""), data.get("category", "Technical"),
             data.get("proficiency", "Proficient"), data.get("notes", ""), id)
        )


def delete_skill(id):
    with get_db() as conn:
        conn.execute("DELETE FROM profile_skills WHERE id=?", (id,))


# ── PROFILE: EDUCATION ────────────────────────────────────────────────────────

def get_education(profile_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM profile_education WHERE profile_id=? ORDER BY end_year DESC, sort_order",
            (profile_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def create_education(data, profile_id=1):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO profile_education
                (profile_id, institution, degree, field, start_year, end_year, gpa, notes)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            profile_id,
            data.get("institution", ""), data.get("degree", ""), data.get("field", ""),
            data.get("start_year", ""), data.get("end_year", ""),
            data.get("gpa", ""), data.get("notes", "")
        ))
        return cur.lastrowid


def update_education(id, data):
    with get_db() as conn:
        conn.execute("""
            UPDATE profile_education SET
                institution=?, degree=?, field=?, start_year=?, end_year=?, gpa=?, notes=?
            WHERE id=?
        """, (
            data.get("institution", ""), data.get("degree", ""), data.get("field", ""),
            data.get("start_year", ""), data.get("end_year", ""),
            data.get("gpa", ""), data.get("notes", ""), id
        ))


def delete_education(id):
    with get_db() as conn:
        conn.execute("DELETE FROM profile_education WHERE id=?", (id,))


# ── APPLICATIONS ──────────────────────────────────────────────────────────────

def get_applications(profile_id, status=None, search=None):
    with get_db() as conn:
        query = "SELECT * FROM applications WHERE profile_id=?"
        params = [profile_id]
        if status and status != "All":
            query += " AND status = ?"
            params.append(status)
        if search:
            query += " AND (company LIKE ? OR role LIKE ?)"
            s = f"%{search}%"
            params += [s, s]
        query += " ORDER BY date_applied DESC, created_at DESC"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_application(id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM applications WHERE id=?", (id,)).fetchone()
        return dict(row) if row else None


def create_application(data, profile_id=1):
    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO applications
                (profile_id, company, role, job_url, status, date_applied, job_description,
                 notes, cover_letter, resume_bullets, salary_range, contact_name, contact_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile_id,
            data.get("company", ""),
            data.get("role", ""),
            data.get("job_url", ""),
            data.get("status", "Saved"),
            data.get("date_applied", ""),
            data.get("job_description", ""),
            data.get("notes", ""),
            data.get("cover_letter", ""),
            data.get("resume_bullets", ""),
            data.get("salary_range", ""),
            data.get("contact_name", ""),
            data.get("contact_email", ""),
        ))
        return cursor.lastrowid


def update_application(id, data):
    import datetime as _dt
    with get_db() as conn:
        row = conn.execute("SELECT status, status_history FROM applications WHERE id=?", (id,)).fetchone()
        new_status = data.get("status", "Saved")
        history = []
        if row:
            try:
                history = json.loads(row["status_history"] or "[]")
            except Exception:
                history = []
            if row["status"] != new_status:
                history.append({
                    "status": new_status,
                    "date": _dt.datetime.now().strftime("%Y-%m-%d"),
                    "from": row["status"],
                })
        conn.execute("""
            UPDATE applications SET
                company=?, role=?, job_url=?, status=?, date_applied=?,
                job_description=?, notes=?, cover_letter=?, resume_bullets=?,
                salary_range=?, contact_name=?, contact_email=?,
                status_history=?, date_updated=datetime('now')
            WHERE id=?
        """, (
            data.get("company", ""),
            data.get("role", ""),
            data.get("job_url", ""),
            new_status,
            data.get("date_applied", ""),
            data.get("job_description", ""),
            data.get("notes", ""),
            data.get("cover_letter", ""),
            data.get("resume_bullets", ""),
            data.get("salary_range", ""),
            data.get("contact_name", ""),
            data.get("contact_email", ""),
            json.dumps(history),
            id,
        ))


def update_application_status(id, new_status):
    import datetime as _dt
    with get_db() as conn:
        row = conn.execute("SELECT status, status_history FROM applications WHERE id=?", (id,)).fetchone()
        if not row:
            return
        history = []
        try:
            history = json.loads(row["status_history"] or "[]")
        except Exception:
            pass
        if row["status"] != new_status:
            history.append({
                "status": new_status,
                "date": _dt.datetime.now().strftime("%Y-%m-%d"),
                "from": row["status"],
            })
        conn.execute(
            "UPDATE applications SET status=?, status_history=?, date_updated=datetime('now') WHERE id=?",
            (new_status, json.dumps(history), id)
        )


def delete_application(id):
    with get_db() as conn:
        conn.execute("DELETE FROM applications WHERE id=?", (id,))


# ── SETTINGS (global) ─────────────────────────────────────────────────────────

def get_setting(key, default=None):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )


# ── STATS ─────────────────────────────────────────────────────────────────────

def get_stats(profile_id):
    with get_db() as conn:
        total_exp    = conn.execute("SELECT COUNT(*) as c FROM profile_experience WHERE profile_id=?", (profile_id,)).fetchone()["c"]
        total_proj   = conn.execute("SELECT COUNT(*) as c FROM profile_projects   WHERE profile_id=?", (profile_id,)).fetchone()["c"]
        total_skills = conn.execute("SELECT COUNT(*) as c FROM profile_skills     WHERE profile_id=?", (profile_id,)).fetchone()["c"]
        total_apps   = conn.execute("SELECT COUNT(*) as c FROM applications       WHERE profile_id=?", (profile_id,)).fetchone()["c"]
        status_counts = conn.execute(
            "SELECT status, COUNT(*) as c FROM applications WHERE profile_id=? GROUP BY status",
            (profile_id,)
        ).fetchall()
        return {
            "total_experiences": total_exp,
            "total_projects":    total_proj,
            "total_skills":      total_skills,
            "total_applications": total_apps,
            "application_statuses": {r["status"]: r["c"] for r in status_counts},
        }
