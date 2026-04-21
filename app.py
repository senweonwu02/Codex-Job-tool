"""
Codex - Personal Job Application & Achievement Tracker
Flask web application with SQLite backend.

Run with:  python app.py
Then open: http://localhost:5050
"""

import os
import json
import re
import urllib.request
import urllib.error
from html.parser import HTMLParser
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, send_from_directory, make_response
from flask_login import LoginManager, login_required, current_user, login_user, logout_user

import base64
import database as db
import generator as gen
import document_parser as dp
import auth

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "api_login"

@login_manager.user_loader
def load_user(user_id):
    user_data = db.get_user_by_id(int(user_id))
    return auth.User(user_data['id'], user_data['email']) if user_data else None

db.init_db()

# Get API key from environment
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("[WARNING] ANTHROPIC_API_KEY environment variable not set. API features will not work on Render.")

# Serve mockup files for preview
@app.route("/mockups/<path:filename>")
def serve_mockup(filename):
    return send_from_directory("mockups", filename)



# ── ACTIVE PROFILE HELPER ─────────────────────────────────────────────────────

def _active_pid():
    """Return the currently active profile ID."""
    return db.get_active_profile_id()


def _active_profile():
    """Return the currently active profile dict."""
    return db.get_profile(_active_pid()) or {}


# ── CLAUDE API HELPER ──────────────────────────────────────────────────────────

def _call_claude(prompt: str, max_tokens: int = 2048) -> str:
    """Call Claude API directly using embedded API key. Returns the response text."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set. Cannot make API calls.")

    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic library not installed. "
            "Open a terminal in the Codex folder and run: pip install anthropic"
        )
    model = db.get_setting("claude_model", "claude-sonnet-4-6") or "claude-sonnet-4-6"
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _call_claude_messages(system: str, messages: list, max_tokens: int = 800) -> str:
    """Call Claude API with multi-turn conversation history using embedded API key. Returns response text."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set. Cannot make API calls.")

    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError(
            "anthropic library not installed. "
            "Open a terminal in the Codex folder and run: pip install anthropic"
        )
    model = db.get_setting("claude_model", "claude-sonnet-4-6") or "claude-sonnet-4-6"
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
    )
    return msg.content[0].text


# ── AUTHENTICATION ────────────────────────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    """Register a new user account."""
    data = request.get_json()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    try:
        user_info = auth.register_user(email, password)
        return jsonify({"message": "Account created", "user": user_info}), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """Login with email and password."""
    data = request.get_json()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not email or not password:
        return jsonify({"error": "Email and password required"}), 400

    try:
        user_info = auth.verify_user(email, password)
        user = auth.User(user_info['user_id'], user_info['email'])
        login_user(user)
        return jsonify({"message": "Logged in", "user": user_info}), 200
    except ValueError:
        return jsonify({"error": "Invalid email or password"}), 401


@app.route("/api/auth/logout", methods=["POST"])
@login_required
def api_logout():
    """Logout current user."""
    logout_user()
    return jsonify({"message": "Logged out"}), 200


@app.route("/api/auth/verify", methods=["GET"])
def api_verify():
    """Check if user is authenticated."""
    if current_user.is_authenticated:
        return jsonify({
            "authenticated": True,
            "user": {
                "id": current_user.id,
                "email": current_user.email
            }
        }), 200
    return jsonify({"authenticated": False}), 200


@app.route("/api/auth/usage", methods=["GET"])
@login_required
def api_usage():
    """Get current month API usage for authenticated user."""
    usage_info = auth.get_usage_info(current_user.id)
    return jsonify(usage_info), 200


# ── USAGE LIMITING DECORATOR ──────────────────────────────────────────────────

def check_api_quota(f):
    """Check if user has exceeded API quota before executing endpoint."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        current_month = datetime.now().strftime("%Y-%m")
        count = db.get_api_usage_count(current_user.id, current_month)

        if count >= 25:
            return jsonify({
                "error": "Monthly API limit (25) exceeded",
                "usage": auth.get_usage_info(current_user.id)
            }), 429

        # Execute the endpoint
        result = f(*args, **kwargs)

        # Record the API usage
        auth.record_api_usage(current_user.id, request.path)

        return result
    return decorated_function


# ── PROFILES ──────────────────────────────────────────────────────────────────

@app.route("/api/profiles", methods=["GET"])
def api_profiles_list():
    profiles = db.get_profiles()
    active_id = db.get_active_profile_id()
    for p in profiles:
        p["is_active"] = (p["id"] == active_id)
    return jsonify(profiles)


@app.route("/api/profiles", methods=["POST"])
def api_profiles_create():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "Profile name is required"}), 400
    new_id = db.create_profile(data)
    return jsonify({"id": new_id, "message": "Profile created"}), 201


@app.route("/api/profiles/active", methods=["GET"])
def api_profiles_active():
    profile = _active_profile()
    if not profile:
        return jsonify({"error": "No active profile"}), 404
    profile["is_active"] = True
    return jsonify(profile)


@app.route("/api/profiles/<int:id>", methods=["PUT"])
def api_profiles_update(id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    db.update_profile(id, data)
    return jsonify({"message": "Updated"})


@app.route("/api/profiles/<int:id>", methods=["DELETE"])
def api_profiles_delete(id):
    if len(db.get_profiles()) <= 1:
        return jsonify({"error": "Cannot delete the last profile"}), 400
    active_id = db.get_active_profile_id()
    db.delete_profile(id)
    if active_id == id:
        remaining = db.get_profiles()
        if remaining:
            db.set_active_profile_id(remaining[0]["id"])
    return jsonify({"message": "Profile deleted"})


@app.route("/api/profiles/<int:id>/activate", methods=["POST"])
def api_profiles_activate(id):
    profile = db.get_profile(id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    db.set_active_profile_id(id)
    profile["is_active"] = True
    return jsonify({"message": "Profile activated", "profile": profile})


# ── PAGE ──────────────────────────────────────────────────────────────────────

@app.route("/")
@app.route("/ui")
def index():
    resp = make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    return resp

# ── STATS ─────────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    return jsonify(db.get_stats(_active_pid()))

# ── PROFILE: EXPERIENCE ───────────────────────────────────────────────────────

@app.route("/api/profile/experience", methods=["GET"])
def api_experiences_list():
    return jsonify(db.get_experiences(_active_pid()))


@app.route("/api/profile/experience", methods=["POST"])
def api_experiences_create():
    data = request.get_json()
    if not data or not data.get("company") or not data.get("title"):
        return jsonify({"error": "Company and title are required"}), 400
    new_id = db.create_experience(data, _active_pid())
    return jsonify({"id": new_id, "message": "Experience created"}), 201


@app.route("/api/profile/experience/<int:id>", methods=["GET"])
def api_experience_get(id):
    item = db.get_experience(id)
    if not item:
        return jsonify({"error": "Not found"}), 404
    return jsonify(item)


@app.route("/api/profile/experience/<int:id>", methods=["PUT"])
def api_experience_update(id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    db.update_experience(id, data)
    return jsonify({"message": "Updated"})


@app.route("/api/profile/experience/<int:id>", methods=["DELETE"])
def api_experience_delete(id):
    db.delete_experience(id)
    return jsonify({"message": "Deleted"})


# ── PROFILE: EXPERIENCE PROJECTS (sub-projects within a role) ────────────────

@app.route("/api/profile/experience/<int:exp_id>/projects", methods=["GET"])
def api_exp_projects_list(exp_id):
    return jsonify(db.get_experience_projects(exp_id))


@app.route("/api/profile/experience/<int:exp_id>/projects", methods=["POST"])
def api_exp_projects_create(exp_id):
    data = request.get_json()
    if not data or not data.get("title"):
        return jsonify({"error": "Title is required"}), 400
    new_id = db.create_experience_project(exp_id, data)
    return jsonify({"id": new_id, "message": "Project added"}), 201


@app.route("/api/profile/experience-projects/<int:id>", methods=["PUT"])
def api_exp_project_update(id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    db.update_experience_project(id, data)
    return jsonify({"message": "Updated"})


@app.route("/api/profile/experience-projects/<int:id>", methods=["DELETE"])
def api_exp_project_delete(id):
    db.delete_experience_project(id)
    return jsonify({"message": "Deleted"})


@app.route("/api/profile/experience-projects/all", methods=["GET"])
def api_all_exp_projects():
    """Return all experience projects grouped by experience_id."""
    return jsonify(db.get_all_experience_projects(_active_pid()))


# ── PROFILE: PROJECTS ─────────────────────────────────────────────────────────

@app.route("/api/profile/projects", methods=["GET"])
def api_projects_list():
    return jsonify(db.get_projects(_active_pid()))


@app.route("/api/profile/projects", methods=["POST"])
def api_projects_create():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "Project name is required"}), 400
    new_id = db.create_project(data, _active_pid())
    return jsonify({"id": new_id, "message": "Project created"}), 201


@app.route("/api/profile/projects/<int:id>", methods=["GET"])
def api_project_get(id):
    item = db.get_project(id)
    if not item:
        return jsonify({"error": "Not found"}), 404
    return jsonify(item)


@app.route("/api/profile/projects/<int:id>", methods=["PUT"])
def api_project_update(id):
    data = request.get_json()
    db.update_project(id, data)
    return jsonify({"message": "Updated"})


@app.route("/api/profile/projects/<int:id>", methods=["DELETE"])
def api_project_delete(id):
    db.delete_project(id)
    return jsonify({"message": "Deleted"})

# ── PROFILE: SKILLS ───────────────────────────────────────────────────────────

@app.route("/api/profile/skills", methods=["GET"])
def api_skills_list():
    return jsonify(db.get_skills(_active_pid()))


@app.route("/api/profile/skills", methods=["POST"])
def api_skills_create():
    data = request.get_json()
    if not data or not data.get("name"):
        return jsonify({"error": "Skill name required"}), 400
    new_id = db.create_skill(data, _active_pid())
    return jsonify({"id": new_id, "message": "Skill created"}), 201


@app.route("/api/profile/skills/<int:id>", methods=["PUT"])
def api_skill_update(id):
    data = request.get_json()
    db.update_skill(id, data)
    return jsonify({"message": "Updated"})


@app.route("/api/profile/skills/<int:id>", methods=["DELETE"])
def api_skill_delete(id):
    db.delete_skill(id)
    return jsonify({"message": "Deleted"})

# ── PROFILE: EDUCATION ────────────────────────────────────────────────────────

@app.route("/api/profile/education", methods=["GET"])
def api_education_list():
    return jsonify(db.get_education(_active_pid()))


@app.route("/api/profile/education", methods=["POST"])
def api_education_create():
    data = request.get_json()
    if not data or not data.get("institution"):
        return jsonify({"error": "Institution required"}), 400
    new_id = db.create_education(data, _active_pid())
    return jsonify({"id": new_id, "message": "Education created"}), 201


@app.route("/api/profile/education/<int:id>", methods=["PUT"])
def api_education_update(id):
    data = request.get_json()
    db.update_education(id, data)
    return jsonify({"message": "Updated"})


@app.route("/api/profile/education/<int:id>", methods=["DELETE"])
def api_education_delete(id):
    db.delete_education(id)
    return jsonify({"message": "Deleted"})

# ── URL FETCH ─────────────────────────────────────────────────────────────────

class _TextExtractor(HTMLParser):
    """Strip HTML tags and return visible text."""
    def __init__(self):
        super().__init__()
        self._text = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'nav', 'header', 'footer', 'noscript'):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'nav', 'header', 'footer', 'noscript'):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    def get_text(self):
        return '\n'.join(self._text)


def _try_job_board_api(url):
    """
    Try to fetch structured job data from known job board APIs.
    Returns (text, api_url) on success, (None, None) on failure.
    """
    import ssl

    # Greenhouse: boards.greenhouse.io/{company}/jobs/{id}
    m = re.match(r'https?://boards\.greenhouse\.io/(\w+)/jobs/(\d+)', url)
    if m:
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}"
        try:
            req = urllib.request.Request(api_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                title = data.get("title", "")
                loc = data.get("location", {}).get("name", "")
                # Content is HTML — strip tags
                content_html = data.get("content", "")
                p = _TextExtractor()
                p.feed(content_html)
                body = p.get_text()
                combined = f"Job Title: {title}\nLocation: {loc}\n\n{body}" if title else body
                return combined, api_url
        except Exception:
            pass

    # Lever: jobs.lever.co/{company}/{id}
    m = re.match(r'https?://jobs\.lever\.co/([\w-]+)/([\w-]+)', url)
    if m:
        api_url = f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}"
        try:
            req = urllib.request.Request(api_url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                title = data.get("text", "")
                cats = data.get("categories", {})
                loc = cats.get("location", "")
                team = cats.get("team", "")
                desc = data.get("descriptionPlain", "") or ""
                lists_text = ""
                for lst in data.get("lists", []):
                    lists_text += f"\n\n{lst.get('text', '')}:\n"
                    lists_text += lst.get("content", "")
                # Strip HTML from lists content
                if "<" in lists_text:
                    p = _TextExtractor()
                    p.feed(lists_text)
                    lists_text = p.get_text()
                combined = f"Job Title: {title}\nTeam: {team}\nLocation: {loc}\n\n{desc}{lists_text}"
                return combined, api_url
        except Exception:
            pass

    return None, None


@login_required
@check_api_quota
@app.route("/api/fetch-url", methods=["POST"])
def api_fetch_url():
    import ssl

    data = request.get_json()
    url  = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    # ── Try structured API for known job boards first ────────────────────────
    api_text, api_url = _try_job_board_api(url)
    if api_text:
        text = re.sub(r'\n{3,}', '\n\n', api_text).strip()
        if len(text) > 12000:
            text = text[:12000] + "\n\n[Content truncated at 12 000 characters]"
    else:
        # ── Generic HTML fetch ───────────────────────────────────────────────
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "identity",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                content_type = resp.headers.get_content_type()
                if "html" not in content_type:
                    return jsonify({"error": f"URL returned non-HTML content ({content_type})"}), 400
                raw = resp.read(2_000_000).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                return jsonify({"error": "This site blocks automated access (403 Forbidden). Please copy and paste the job description manually."}), 400
            if e.code == 429:
                return jsonify({"error": "Rate limited by the site. Wait a moment, then try again — or paste the job description manually."}), 400
            return jsonify({"error": f"HTTP {e.code}: {e.reason}. Try pasting the job description manually."}), 400
        except urllib.error.URLError as e:
            return jsonify({"error": f"Could not reach URL: {e.reason}. Check the URL and try again."}), 400
        except Exception as e:
            return jsonify({"error": f"Fetch failed: {str(e)}"}), 400

        parser = _TextExtractor()
        parser.feed(raw)
        text = parser.get_text()
        text = re.sub(r'\n{3,}', '\n\n', text).strip()

        if not text or len(text) < 50:
            return jsonify({"error": "Page returned very little text — it may require JavaScript to load. Please copy and paste the job description manually."}), 400

        if len(text) > 12000:
            text = text[:12000] + "\n\n[Content truncated at 12 000 characters]"

    result = {"text": text, "source_url": url, "extracted": None}

    # ── Use Claude to extract structured job data if API key is available ──
    if ANTHROPIC_API_KEY:
        extract_prompt = (
            "You are a job listing parser. Extract structured data from this job posting text.\n"
            "Return ONLY valid JSON with these fields (use empty string if not found):\n\n"
            '{\n'
            '  "role": "exact job title",\n'
            '  "company": "company name",\n'
            '  "location": "job location",\n'
            '  "salary_range": "salary/compensation if mentioned",\n'
            '  "job_description": "the full job description text only — responsibilities, '
            'requirements, qualifications, benefits. Exclude navigation, headers, footers, '
            'cookie notices, and other non-job content. Preserve the original structure with '
            'line breaks and bullet points."\n'
            '}\n\n'
            "PAGE TEXT:\n" + text
        )
        try:
            raw_json = _call_claude(extract_prompt, max_tokens=4000)
            cleaned = raw_json.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r'^```\w*\n?', '', cleaned)
                cleaned = re.sub(r'\n?```$', '', cleaned)
            extracted = json.loads(cleaned.strip())
            result["extracted"] = extracted
            if extracted.get("job_description"):
                result["text"] = extracted["job_description"]
        except Exception as e:
            pass  # Fall back to raw text — extraction is best-effort

    return jsonify(result)


# ── ROLE ANALYSIS ─────────────────────────────────────────────────────────────

@login_required
@check_api_quota
@app.route("/api/generate/analysis", methods=["POST"])
def api_generate_analysis():
    data           = request.get_json()
    jd             = data.get("job_description", "").strip()
    exp_ids        = data.get("experience_ids", [])  # empty = use all
    proj_ids       = data.get("project_ids", [])
    if not jd:
        return jsonify({"error": "Job description is required"}), 400

    pid = _active_pid()
    prof = _active_profile()

    # Use selected IDs or fall back to all
    if exp_ids:
        experiences = [e for e in [db.get_experience(i) for i in exp_ids] if e]
    else:
        experiences = db.get_experiences(pid)

    if proj_ids:
        projects = [p for p in [db.get_project(i) for i in proj_ids] if p]
    else:
        projects = db.get_projects(pid)

    skills         = db.get_skills(pid)
    candidate_name = prof.get("candidate_name", "")
    career_summary = prof.get("career_summary", "")

    prompt = gen.build_role_analysis_prompt(
        jd, experiences, projects, skills, candidate_name, career_summary
    )
    if ANTHROPIC_API_KEY:
        try:
            text = _call_claude(prompt, max_tokens=1800)
            return jsonify({"prompt": prompt, "text": text})
        except Exception as e:
            return jsonify({"prompt": prompt, "ai_error": str(e)})
    return jsonify({"prompt": prompt})


# ── AI INTERVIEW & IMPORT ─────────────────────────────────────────────────────

@app.route("/api/ai/parse-markdown", methods=["POST"])
def api_parse_markdown():
    data = request.get_json()
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"error": "No markdown content provided"}), 400
    prompt = gen.build_markdown_import_prompt(content)
    return jsonify({"prompt": prompt})


@login_required
@check_api_quota
@app.route("/api/ai/interview-start", methods=["POST"])
def api_interview_start():
    data = request.get_json()
    section_type = data.get("section_type", "experience")
    narrative    = data.get("narrative", "").strip()
    if not narrative:
        return jsonify({"error": "Please describe your experience first"}), 400
    prompt = gen.build_interview_round1_prompt(section_type, narrative)
    # Auto-fire if API key is available
    if ANTHROPIC_API_KEY:
        try:
            text = _call_claude(prompt, max_tokens=1200)
            return jsonify({"prompt": prompt, "questions": text})
        except Exception as e:
            return jsonify({"prompt": prompt, "ai_error": str(e)})
    return jsonify({"prompt": prompt})


@login_required
@check_api_quota
@app.route("/api/ai/interview-extract", methods=["POST"])
def api_interview_extract():
    data = request.get_json()
    section_type = data.get("section_type", "experience")
    narrative    = data.get("narrative", "").strip()
    qa_pairs     = data.get("qa_pairs", [])
    if not narrative:
        return jsonify({"error": "Missing initial narrative"}), 400
    prompt = gen.build_interview_extraction_prompt(section_type, narrative, qa_pairs)
    # Auto-fire if API key is available
    if ANTHROPIC_API_KEY:
        try:
            text = _call_claude(prompt, max_tokens=3000)
            return jsonify({"prompt": prompt, "json_text": text})
        except Exception as e:
            return jsonify({"prompt": prompt, "ai_error": str(e)})
    return jsonify({"prompt": prompt})


@login_required
@check_api_quota
@app.route("/api/ai/interview-chat", methods=["POST"])
def api_interview_chat():
    """Handle one turn of the conversational AI interview."""
    data           = request.get_json()
    section_type   = data.get("section_type", "experience")
    existing_entry = data.get("existing_entry", {})
    history        = data.get("history", [])   # [{role, content}, ...]
    user_message   = data.get("user_message")  # None for opening turn

    system = gen.build_interview_chat_system_prompt(section_type, existing_entry)

    # Build messages list for Claude
    if not history and not user_message:
        # Opening turn — send a trigger message to get Claude's first question
        messages = [{"role": "user", "content": "[BEGIN INTERVIEW]"}]
    else:
        # Continue conversation — rebuild history and append latest user message
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        if user_message:
            messages.append({"role": "user", "content": user_message})
    if ANTHROPIC_API_KEY:
        try:
            text = _call_claude_messages(system, messages, max_tokens=600)
            is_done = text.strip().startswith("✅ I think I have what I need")
            return jsonify({"assistant_message": text, "is_done": is_done})
        except Exception as e:
            return jsonify({"error": str(e), "fallback_system": system})
    else:
        return jsonify({"no_key": True, "fallback_system": system})


@login_required
@check_api_quota
@app.route("/api/ai/interview-finalize", methods=["POST"])
def api_interview_finalize():
    """Extract structured JSON from the completed conversation."""
    data           = request.get_json()
    section_type   = data.get("section_type", "experience")
    existing_entry = data.get("existing_entry", {})
    history        = data.get("history", [])

    prompt = gen.build_interview_finalize_prompt(section_type, existing_entry, history)
    if ANTHROPIC_API_KEY:
        try:
            text = _call_claude(prompt, max_tokens=3000)
            return jsonify({"json_text": text, "prompt": prompt})
        except Exception as e:
            return jsonify({"error": str(e), "prompt": prompt})
    return jsonify({"prompt": prompt})


@app.route("/api/import/profile", methods=["POST"])
def api_import_profile():
    """Bulk import parsed profile JSON into the database."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    pid    = _active_pid()
    counts = {"experiences": 0, "projects": 0, "skills": 0, "education": 0}

    for exp in data.get("experiences", []):
        if exp.get("company") and exp.get("title"):
            db.create_experience(exp, pid)
            counts["experiences"] += 1

    for proj in data.get("projects", []):
        if proj.get("name"):
            db.create_project(proj, pid)
            counts["projects"] += 1

    for skill in data.get("skills", []):
        if skill.get("name"):
            db.create_skill(skill, pid)
            counts["skills"] += 1

    for edu in data.get("education", []):
        if edu.get("institution"):
            db.create_education(edu, pid)
            counts["education"] += 1

    return jsonify({"message": "Import complete", "counts": counts})


@app.route("/api/import/single", methods=["POST"])
def api_import_single():
    """Import a single experience or project extracted from an interview."""
    data = request.get_json()
    section_type = data.get("section_type", "experience")
    entry        = data.get("entry", {})

    pid = _active_pid()
    if section_type == "experience":
        if not entry.get("company") or not entry.get("title"):
            return jsonify({"error": "Company and title required"}), 400
        new_id = db.create_experience(entry, pid)
    elif section_type == "project":
        if not entry.get("name"):
            return jsonify({"error": "Project name required"}), 400
        new_id = db.create_project(entry, pid)
    else:
        return jsonify({"error": "Unknown section type"}), 400

    return jsonify({"id": new_id, "message": f"{section_type.capitalize()} imported"})


# ── APPLICATIONS ──────────────────────────────────────────────────────────────

@app.route("/api/applications", methods=["GET"])
def api_applications_list():
    status = request.args.get("status", "All").strip()
    search = request.args.get("search", "").strip()
    return jsonify(db.get_applications(_active_pid(), status=status or None, search=search or None))


@app.route("/api/applications", methods=["POST"])
def api_applications_create():
    data = request.get_json()
    if not data or not data.get("company") or not data.get("role"):
        return jsonify({"error": "Company and role are required"}), 400
    new_id = db.create_application(data, _active_pid())
    return jsonify({"id": new_id, "message": "Application created"}), 201


@app.route("/api/applications/<int:id>", methods=["GET"])
def api_application_get(id):
    item = db.get_application(id)
    if not item:
        return jsonify({"error": "Not found"}), 404
    return jsonify(item)


@app.route("/api/applications/<int:id>", methods=["PUT"])
def api_application_update(id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400
    db.update_application(id, data)
    return jsonify({"message": "Updated"})


@app.route("/api/applications/<int:id>", methods=["DELETE"])
def api_application_delete(id):
    db.delete_application(id)
    return jsonify({"message": "Deleted"})

# ── GENERATOR ─────────────────────────────────────────────────────────────────

@login_required
@check_api_quota
@app.route("/api/generate/bullets", methods=["POST"])
def api_generate_bullets():
    data = request.get_json()
    jd = data.get("job_description", "").strip()
    exp_ids  = data.get("experience_ids", [])
    proj_ids = data.get("project_ids", [])
    resume_sample = data.get("resume_sample", "").strip()

    if not jd:
        return jsonify({"error": "Job description is required"}), 400
    if not exp_ids and not proj_ids:
        return jsonify({"error": "Select at least one experience or project"}), 400

    experiences = [e for e in [db.get_experience(i) for i in exp_ids] if e]
    projects    = [p for p in [db.get_project(i)    for i in proj_ids] if p]
    prof        = _active_profile()
    skills      = db.get_skills(_active_pid())
    candidate_name = prof.get("candidate_name", "")

    prompt = gen.build_resume_bullets_prompt(jd, experiences, projects, skills, candidate_name, resume_sample)
    # Inject template formatting constraints if a resume template is stored
    tmpl_meta_raw = db.get_setting("resume_template_meta", "")
    if tmpl_meta_raw:
        try:
            tmpl_meta = json.loads(tmpl_meta_raw)
            prompt += dp.build_template_prompt_addon(tmpl_meta, "resume")
        except Exception:
            pass
    if ANTHROPIC_API_KEY:
        try:
            text = _call_claude(prompt, max_tokens=2500)
            return jsonify({"prompt": prompt, "text": text})
        except Exception as e:
            return jsonify({"prompt": prompt, "ai_error": str(e)})
    return jsonify({"prompt": prompt})


@login_required
@check_api_quota
@app.route("/api/generate/recommend-profile", methods=["POST"])
def api_recommend_profile():
    """Use Claude to recommend which profile items best fit the job description."""
    data = request.get_json()
    jd = data.get("job_description", "").strip()
    if not jd:
        return jsonify({"error": "Job description is required"}), 400
    if not api_key:
        # No API key — return empty (frontend falls back to all selected)
        return jsonify({"experience_ids": [], "project_ids": [], "skill_ids": []})

    pid = _active_pid()
    experiences = db.get_experiences(pid)
    projects    = db.get_projects(pid)
    skills      = db.get_skills(pid)

    # Build a compact summary for Claude
    exp_summary = "\n".join(
        f"  ID={e['id']}: {e.get('title','')} at {e.get('company','')} ({e.get('start_date','')}-{e.get('end_date','Present' if e.get('is_current') else '')})"
        for e in experiences
    )
    proj_summary = "\n".join(
        f"  ID={p['id']}: {p.get('name','')} — {p.get('description','')[:80]}"
        for p in projects
    )

    prompt = (
        "You are a career advisor. Given a job description and a candidate's profile items, "
        "select which experiences and projects are MOST relevant to this specific role. "
        "Be selective — only include items that directly strengthen the application.\n\n"
        f"## JOB DESCRIPTION\n{jd[:3000]}\n\n"
        f"## EXPERIENCES\n{exp_summary}\n\n"
        f"## PROJECTS\n{proj_summary}\n\n"
        "Return ONLY valid JSON with two arrays of integer IDs:\n"
        '{"experience_ids": [1, 3], "project_ids": [2]}\n\n'
        "Rules:\n"
        "- Include experiences that are relevant or transferable to the target role\n"
        "- Exclude experiences that have no connection to the role\n"
        "- Include projects only if they directly demonstrate relevant skills\n"
        "- Return ONLY the JSON — no explanation, no markdown fences"
    )

    try:
        raw = _call_claude(prompt, max_tokens=200)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```\w*\n?', '', cleaned)
            cleaned = re.sub(r'\n?```$', '', cleaned)
        result = json.loads(cleaned.strip())
        return jsonify({
            "experience_ids": result.get("experience_ids", []),
            "project_ids": result.get("project_ids", []),
        })
    except Exception:
        # Fallback — return all IDs
        return jsonify({
            "experience_ids": [e["id"] for e in experiences],
            "project_ids": [p["id"] for p in projects],
        })


@login_required
@check_api_quota
@app.route("/api/generate/resume", methods=["POST"])
def api_generate_resume():
    data = request.get_json()
    jd = data.get("job_description", "").strip()
    exp_ids  = data.get("experience_ids", [])
    proj_ids = data.get("project_ids", [])
    resume_sample   = data.get("resume_sample", "").strip()
    include_summary = data.get("include_summary", True)
    exp_project_map = data.get("exp_project_map", {})  # {exp_id: [proj_id, ...]}

    if not jd:
        return jsonify({"error": "Job description is required"}), 400
    if not exp_ids and not proj_ids:
        return jsonify({"error": "Select at least one experience or project"}), 400

    experiences = [e for e in [db.get_experience(i) for i in exp_ids] if e]
    projects    = [p for p in [db.get_project(i)    for i in proj_ids] if p]
    pid         = _active_pid()
    prof        = _active_profile()
    skills      = db.get_skills(pid)
    education   = db.get_education(pid)
    candidate_name     = prof.get("candidate_name", "")
    candidate_email    = prof.get("candidate_email", "")
    candidate_phone    = prof.get("candidate_phone", "")
    candidate_linkedin = prof.get("candidate_linkedin", "")

    # Resolve experience sub-projects from DB
    resolved_exp_projects = {}
    if exp_project_map:
        all_exp_projs = db.get_all_experience_projects(pid)
        for exp_id_str, selected_ids in exp_project_map.items():
            exp_id = int(exp_id_str)
            db_projs = all_exp_projs.get(exp_id, [])
            selected = [p for p in db_projs if p["id"] in selected_ids]
            if selected:
                resolved_exp_projects[exp_id_str] = selected

    prompt = gen.build_full_resume_prompt(
        jd, experiences, projects, skills, education,
        candidate_name, candidate_email, candidate_phone,
        candidate_linkedin, resume_sample, include_summary,
        resolved_exp_projects
    )
    # Inject template formatting constraints if a resume template is stored
    tmpl_meta_raw = db.get_setting("resume_template_meta", "")
    if tmpl_meta_raw:
        try:
            tmpl_meta = json.loads(tmpl_meta_raw)
            prompt += dp.build_template_prompt_addon(tmpl_meta, "resume")
        except Exception:
            pass
    if ANTHROPIC_API_KEY:
        try:
            text = _call_claude(prompt, max_tokens=4000)
            return jsonify({"prompt": prompt, "text": text})
        except Exception as e:
            return jsonify({"prompt": prompt, "ai_error": str(e)})
    return jsonify({"prompt": prompt})


@login_required
@check_api_quota
@app.route("/api/generate/cover-letter", methods=["POST"])
def api_generate_cover_letter():
    data = request.get_json()
    jd = data.get("job_description", "").strip()
    exp_ids  = data.get("experience_ids", [])
    proj_ids = data.get("project_ids", [])
    cover_sample   = data.get("cover_letter_sample", "").strip()
    company_name   = data.get("company_name", "").strip()
    role_title     = data.get("role_title", "").strip()
    notes          = data.get("additional_notes", "").strip()

    if not jd:
        return jsonify({"error": "Job description is required"}), 400
    if not exp_ids and not proj_ids:
        return jsonify({"error": "Select at least one experience or project"}), 400

    experiences = [e for e in [db.get_experience(i) for i in exp_ids] if e]
    projects    = [p for p in [db.get_project(i)    for i in proj_ids] if p]
    prof        = _active_profile()
    skills      = db.get_skills(_active_pid())
    candidate_name = prof.get("candidate_name", "")
    career_summary = prof.get("career_summary", "")

    prompt = gen.build_cover_letter_prompt(
        jd, experiences, projects, skills, candidate_name,
        career_summary, company_name, role_title, notes, cover_sample
    )
    # Inject template formatting constraints if a cover letter template is stored
    tmpl_meta_raw = db.get_setting("cover_letter_template_meta", "")
    if tmpl_meta_raw:
        try:
            tmpl_meta = json.loads(tmpl_meta_raw)
            prompt += dp.build_template_prompt_addon(tmpl_meta, "cover_letter")
        except Exception:
            pass
    if ANTHROPIC_API_KEY:
        try:
            text = _call_claude(prompt, max_tokens=2000)
            return jsonify({"prompt": prompt, "text": text})
        except Exception as e:
            return jsonify({"prompt": prompt, "ai_error": str(e)})
    return jsonify({"prompt": prompt})

# ── EXPAND ENTRY (inline AI enhancement) ─────────────────────────────────────

@login_required
@check_api_quota
@app.route("/api/generate/expand-entry", methods=["POST"])
def api_expand_entry():
    data = request.get_json()
    entry_text  = data.get("entry_text", "").strip()
    jd          = data.get("job_description", "").strip()
    full_resume = data.get("full_resume", "").strip()

    if not entry_text:
        return jsonify({"error": "No entry text provided"}), 400
    if not api_key:
        return jsonify({"error": "API key required — configure in Settings"}), 400

    # ── Match entry to profile data ──────────────────────────────────────
    entry_lower = entry_text.lower()
    profile_context = ""

    # Match work experiences by company/title
    pid = _active_pid()
    experiences = db.get_experiences(pid)
    all_exp_projs = db.get_all_experience_projects(pid)
    for exp in experiences:
        company_l = (exp.get("company") or "").lower()
        title_l = (exp.get("title") or "").lower()
        if company_l and company_l in entry_lower or title_l and title_l in entry_lower:
            profile_context += f"\n## PROFILE DATA FOR THIS ENTRY (use this to generate new bullets):\n"
            profile_context += f"Company: {exp.get('company','')}\n"
            profile_context += f"Title: {exp.get('title','')}\n"
            if exp.get("description"):
                profile_context += f"Role Description: {exp['description']}\n"
            if exp.get("day_to_day"):
                profile_context += f"Day-to-Day Responsibilities: {exp['day_to_day']}\n"
            if exp.get("achievements"):
                profile_context += f"Key Achievements: {', '.join(exp['achievements'])}\n"
            if exp.get("skills"):
                profile_context += f"Skills Used: {', '.join(exp['skills'])}\n"
            # Include sub-projects for this experience
            exp_projs = all_exp_projs.get(exp["id"], [])
            if exp_projs:
                profile_context += "Projects/Client Work:\n"
                for p in exp_projs:
                    profile_context += f"  - {p.get('title','')}: {p.get('description','')}\n"
            break

    # Match education by institution/degree
    if not profile_context:
        education = db.get_education(pid)
        for edu in education:
            inst_l = (edu.get("institution") or "").lower()
            degree_l = (edu.get("degree") or "").lower()
            field_l = (edu.get("field") or "").lower()
            if (inst_l and inst_l in entry_lower) or (field_l and field_l in entry_lower):
                profile_context += f"\n## PROFILE DATA FOR THIS ENTRY (use this to generate new bullets):\n"
                profile_context += f"Institution: {edu.get('institution','')}\n"
                profile_context += f"Degree: {edu.get('degree','')} in {edu.get('field','')}\n"
                if edu.get("gpa"):
                    profile_context += f"GPA: {edu['gpa']}\n"
                if edu.get("notes"):
                    profile_context += f"Additional Details: {edu['notes']}\n"
                break

    # Match skills by category name
    if not profile_context:
        skills = db.get_skills(pid)
        # Group skills by category
        cats = {}
        for s in skills:
            cats.setdefault(s.get("category", ""), []).append(s)
        for cat, cat_skills in cats.items():
            if cat.lower() in entry_lower:
                profile_context += f"\n## PROFILE DATA FOR THIS ENTRY (use this to generate new content):\n"
                profile_context += f"Category: {cat}\n"
                profile_context += f"All skills in this category: {', '.join(s.get('name','') + ' (' + s.get('level','') + ')' for s in cat_skills)}\n"
                break

    source_instruction = ""
    if profile_context:
        source_instruction = "IMPORTANT: Draw new bullet points ONLY from the PROFILE DATA provided below. Do not invent facts, metrics, or achievements that are not in the profile. Use the candidate's own descriptions, achievements, and skills to craft new bullets."
    else:
        source_instruction = "Note: No matching profile data was found for this entry. Generate plausible bullets based on the existing entry content and job description, but keep them conservative and factual."

    prompt = f"""You are editing a resume. Below is one entry from the resume. Add 2-3 additional detailed bullet points to this entry.

RULES:
- Keep ALL existing content EXACTLY as-is (do not rewrite, reorder, or remove anything)
- Add new bullets AFTER the existing bullets
- New bullets must complement (not duplicate) existing ones
- {source_instruction}
- Use strong action verbs and include quantified results where possible
- Tailor new bullets to the job description below
- Preserve exact formatting: dash-space for bullets (- text), two-space-dash-space for sub-bullets (  - text), [PROJECT] markers if present, >> delimiters for role headers
- Output ONLY the complete entry (original + new bullets) — no commentary
{profile_context}
JOB DESCRIPTION:
{jd}

FULL RESUME (for context — do not duplicate content from other entries):
{full_resume}

ENTRY TO EXPAND:
{entry_text}

OUTPUT THE COMPLETE EXPANDED ENTRY:"""

    try:
        text = _call_claude(prompt, max_tokens=800)
        return jsonify({"expanded_text": text.strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── UTILITIES ─────────────────────────────────────────────────────────────────

@app.route("/api/utils/extract-text", methods=["POST"])
def api_extract_text():
    """
    Extract plain text from a .docx or .pdf file (base64-encoded).
    Used to populate writing sample textareas in Settings.

    Body: { file_b64: str, filename: str }
    Returns: { text: str }
    """
    data     = request.get_json()
    file_b64 = data.get("file_b64", "").strip()
    filename = data.get("filename", "").strip().lower()

    if not file_b64:
        return jsonify({"error": "No file data received"}), 400

    try:
        file_bytes = base64.b64decode(file_b64)
    except Exception:
        return jsonify({"error": "Invalid base64 file data"}), 400

    if filename.endswith(".pdf"):
        meta = dp.parse_pdf_template(file_bytes)
    elif filename.endswith(".docx"):
        meta = dp.parse_docx_template(file_bytes)
    else:
        return jsonify({"error": "Unsupported file type. Please upload a .docx or .pdf file."}), 400

    if "error" in meta:
        return jsonify({"error": meta["error"]}), 500

    return jsonify({"text": meta.get("extracted_text", "").strip()})


@app.route("/api/applications/<int:id>/status", methods=["PATCH"])
def api_application_quick_status(id):
    """Quick status-only update for inline card dropdown."""
    data   = request.get_json()
    status = data.get("status", "").strip()
    if not status:
        return jsonify({"error": "Status is required"}), 400
    db.update_application_status(id, status)
    return jsonify({"message": "Status updated"})


# ── TEMPLATE UPLOAD / DOCX DOWNLOAD ──────────────────────────────────────────

@app.route("/api/settings/upload-template", methods=["POST"])
def api_upload_template():
    """
    Accept a base64-encoded .docx or .pdf, parse its structure,
    and store the metadata for future document generation.

    Body: { file_b64: str, filename: str, doc_type: "resume"|"cover_letter" }
    """
    data     = request.get_json()
    file_b64 = data.get("file_b64", "").strip()
    filename = data.get("filename", "").strip().lower()
    doc_type = data.get("doc_type", "resume").strip()

    if not file_b64:
        return jsonify({"error": "No file data received"}), 400
    if doc_type not in ("resume", "cover_letter"):
        return jsonify({"error": "doc_type must be 'resume' or 'cover_letter'"}), 400

    try:
        file_bytes = base64.b64decode(file_b64)
    except Exception:
        return jsonify({"error": "Invalid base64 file data"}), 400

    # Detect format and parse
    if filename.endswith(".pdf"):
        meta = dp.parse_pdf_template(file_bytes)
    elif filename.endswith(".docx"):
        meta = dp.parse_docx_template(file_bytes)
    else:
        return jsonify({"error": "Unsupported file type. Please upload a .docx or .pdf file."}), 400

    if "error" in meta:
        return jsonify({"error": meta["error"]}), 500

    # Strip extracted text before storing (can be large; we only needed it for display)
    meta_to_store = {k: v for k, v in meta.items() if k != "extracted_text"}

    setting_key = "resume_template_meta" if doc_type == "resume" else "cover_letter_template_meta"
    db.set_setting(setting_key, json.dumps(meta_to_store))

    # Build a human-readable summary
    page = meta.get("page", {})
    summary = {
        "font":         meta.get("primary_font", "Unknown"),
        "body_size_pt": meta.get("body_size_pt", 11),
        "line_spacing": meta.get("line_spacing", 1.0),
        "page_size":    f"{page.get('width_inches', 8.5)}\" × {page.get('height_inches', 11.0)}\"",
        "margins":      (
            f"top {page.get('margin_top', 1.0)}\""
            f" / bottom {page.get('margin_bottom', 1.0)}\""
            f" / left {page.get('margin_left', 1.0)}\""
            f" / right {page.get('margin_right', 1.0)}\""
        ),
        "source_type":  meta.get("source_type", "unknown"),
        "note":         meta.get("note", ""),
    }
    return jsonify({"ok": True, "summary": summary})


@login_required
@check_api_quota
@app.route("/api/generate/download-docx", methods=["POST"])
def api_download_docx():
    """
    Generate a formatted .docx from AI-produced text using stored template metadata.

    Body: { content: str, doc_type: "resume"|"cover_letter" }
    Returns the .docx file as a binary download.
    """
    from flask import Response
    data     = request.get_json()
    content  = data.get("content", "").strip()
    doc_type = data.get("doc_type", "cover_letter").strip()

    if not content:
        return jsonify({"error": "No content provided"}), 400

    setting_key = "resume_template_meta" if doc_type == "resume" else "cover_letter_template_meta"
    tmpl_meta_raw = db.get_setting(setting_key, "")

    template_meta = {}
    if tmpl_meta_raw:
        try:
            template_meta = json.loads(tmpl_meta_raw)
        except Exception:
            pass

    try:
        if doc_type == "resume":
            docx_bytes = dp.generate_resume_docx(content, template_meta)
            fname = "resume.docx"
        else:
            docx_bytes = dp.generate_cover_letter_docx(content, template_meta)
            fname = "cover_letter.docx"
    except Exception as e:
        return jsonify({"error": f"Could not generate .docx: {e}"}), 500

    return Response(
        docx_bytes,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── SETTINGS ──────────────────────────────────────────────────────────────────

# Per-profile candidate fields (stored in profiles table)
_PROFILE_CANDIDATE_FIELDS = [
    "candidate_name", "candidate_email", "candidate_phone", "candidate_linkedin",
    "career_summary", "resume_sample", "cover_letter_sample",
]


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    prof = _active_profile()
    result = {k: prof.get(k, "") for k in _PROFILE_CANDIDATE_FIELDS}
    result["claude_model"] = db.get_setting("claude_model", "claude-sonnet-4-6") or "claude-sonnet-4-6"
    stored_key = db.get_setting("api_key", "")
    result["api_key_configured"] = bool(stored_key)
    result["api_key"] = "[configured]" if stored_key else ""
    result["resume_template_meta"]       = db.get_setting("resume_template_meta", "")
    result["cover_letter_template_meta"] = db.get_setting("cover_letter_template_meta", "")
    return jsonify(result)


@app.route("/api/settings", methods=["POST"])
def api_settings_save():
    data = request.get_json()
    pid  = _active_pid()
    prof = _active_profile()

    # Write per-profile candidate fields
    profile_update = {k: data[k] for k in _PROFILE_CANDIDATE_FIELDS if k in data}
    if profile_update:
        merged = {**prof, **profile_update}
        db.update_profile(pid, merged)

    # Write global settings
    if "claude_model" in data:
        db.set_setting("claude_model", data["claude_model"])

    api_key = data.get("api_key", "").strip()
    if api_key and api_key != "[configured]":
        db.set_setting("api_key", api_key)
    elif api_key == "" and "api_key" in data:
        db.set_setting("api_key", "")

    return jsonify({"message": "Settings saved"})


@app.route("/api/test-connection", methods=["POST"])
def api_test_connection():
    """Test that the stored Claude API key works."""
    if not api_key:
        return jsonify({"error": "No API key configured. Add one in Settings."}), 400
    try:
        result = _call_claude("Reply with exactly: OK", max_tokens=10)
        return jsonify({"ok": True, "message": f"Connected! Model: {db.get_setting('claude_model','claude-sonnet-4-6')}"})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        err = str(e)
        if "authentication" in err.lower() or "401" in err:
            return jsonify({"error": "Invalid API key — check it at console.anthropic.com"}), 401
        return jsonify({"error": f"Connection failed: {err}"}), 500

# ── META ──────────────────────────────────────────────────────────────────────

@app.route("/api/skill-categories")
def api_skill_categories():
    return jsonify(gen.SKILL_CATEGORIES)


@app.route("/api/skill-proficiencies")
def api_skill_proficiencies():
    return jsonify(gen.SKILL_PROFICIENCIES)


@app.route("/api/statuses")
def api_statuses():
    return jsonify(gen.APPLICATION_STATUSES)

# ── RUN ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*55)
    print("  Codex is running!")
    print("  Open your browser at:  http://localhost:5050")
    print("="*55 + "\n")
    app.run(host="0.0.0.0", port=5050, debug=False)
