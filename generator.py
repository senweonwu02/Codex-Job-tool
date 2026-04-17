"""
Content generation logic for Codex app.
Builds optimized prompts from the Job Application Accelerator framework.
Prompts incorporate the candidate's full profile + writing style samples.
"""

import json

SKILL_CATEGORIES   = ["Technical", "Tools & Software", "Languages", "Soft Skills",
                       "Domain Knowledge", "Certifications", "Other"]
SKILL_PROFICIENCIES = ["Expert", "Advanced", "Proficient", "Familiar", "Learning"]
APPLICATION_STATUSES = [
    "Saved", "Applied", "Phone Screen", "Interview", "Final Round",
    "Offer", "Rejected", "Withdrawn", "Accepted"
]


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _format_experience(exp: dict, idx: int) -> str:
    skills = exp.get("skills", [])
    achievements = exp.get("achievements", [])
    current = " (Current Role)" if exp.get("is_current") else ""
    date_range = f"{exp.get('start_date','')}–{'Present' if exp.get('is_current') else exp.get('end_date','')}"

    block = f"""
Experience {idx}: {exp.get('title','')} at {exp.get('company','')}{current}
  Dates: {date_range}
  Location: {exp.get('location','') or 'N/A'}
  Overview: {exp.get('description','')}
  Day-to-day responsibilities: {exp.get('day_to_day','') or 'Not specified'}
  Key achievements: {chr(10).join('    - ' + a for a in achievements) if achievements else '    Not specified'}
  Skills used: {', '.join(skills) if skills else 'Not specified'}
"""
    return block


def _format_project(proj: dict, idx: int) -> str:
    tech = proj.get("tech_stack", [])
    block = f"""
Project {idx}: {proj.get('name','')}
  Role: {proj.get('role','') or 'N/A'}
  Context: {proj.get('company','') or 'Personal / Side Project'}
  Description: {proj.get('description','')}
  Outcome: {proj.get('outcome','') or 'Not specified'}
  Metrics: {proj.get('metrics','') or 'Not specified'}
  Tech / Tools: {', '.join(tech) if tech else 'Not specified'}
"""
    return block


def _format_skills(skills: list) -> str:
    if not skills:
        return "  Not specified"
    grouped = {}
    for s in skills:
        cat = s.get("category", "Other")
        grouped.setdefault(cat, []).append(f"{s['name']} ({s.get('proficiency','Proficient')})")
    return "\n".join(f"  {cat}: {', '.join(items)}" for cat, items in grouped.items())


def _writing_sample_section(sample: str, label: str) -> str:
    if not sample or not sample.strip():
        return ""
    return f"""
## {label.upper()} — WRITING STYLE REFERENCE
Study the candidate's existing {label.lower()} below carefully before writing.
Mirror their:
- Sentence structure and length
- Tone (formal/casual balance, use of first person, active vs. passive voice)
- How they quantify impact (percentages, dollar figures, headcount, etc.)
- Level of technical detail and jargon
- Punctuation style (Oxford commas, em dashes, semicolons, etc.)
- Opening and closing patterns

The output MUST feel like the same person wrote it — not like a template.

{label} sample:
---
{sample.strip()}
---
"""


# ── RESUME BULLETS ────────────────────────────────────────────────────────────

def build_resume_bullets_prompt(
    job_description: str,
    experiences: list,
    projects: list,
    skills: list,
    candidate_name: str = "",
    resume_sample: str = "",
) -> str:

    exp_text  = "".join(_format_experience(e, i+1) for i, e in enumerate(experiences))
    proj_text = "".join(_format_project(p, i+1)    for i, p in enumerate(projects))
    skill_text = _format_skills(skills)
    style_section = _writing_sample_section(resume_sample, "Resume")
    name_line = f"Candidate: {candidate_name}" if candidate_name else ""

    return f"""You are a professional resume writer and career strategist using the Job Application Accelerator framework. Your task is to produce powerful, ATS-optimized resume bullets that are tailored to this specific role and sound authentically like this candidate.
{name_line}
{style_section}
## JOB DESCRIPTION
{job_description}

## CANDIDATE PROFILE

### Work Experience
{exp_text or '  Not provided'}

### Projects
{proj_text or '  Not provided'}

### Skills
{skill_text}

## YOUR TASK

### Step 1 — Multi-Perspective Job Analysis
Analyze the job description through three lenses:

**Recruiter lens:** List the top 12–15 ATS keywords and exact phrases that must appear in the resume. Note any minimum qualifications that are deal-breakers.

**Hiring Manager lens:** Identify the 3 core capabilities they need proven with concrete evidence and results. What does "success in 90 days" look like?

**Codex lens:** What is the narrative thread that makes this candidate compelling for this specific role? How should their background be positioned?

### Step 2 — Requirement–Experience Matrix
For each of the top 5 job requirements, identify the best matching experience from the candidate profile, rate the match (Tier 1–4: Direct / Adjacent / Transferable / Gap), and note the best proof point to use.

### Step 3 — Resume Bullets
Write 6–9 polished resume bullets that:
- Start with a strong, varied action verb
- Mirror the exact keywords from the job description
- Follow the formula: [Action Verb] + [What/How] + [Measurable Result]
- Quantify wherever possible using the candidate's own metrics
- Are ready to drop into a resume with no edits needed
- Match the candidate's established writing style (if sample provided)

### Step 4 — Gap Strategy
Note any key requirements not covered by the provided experience, with specific strategies for how to address each gap (keyword framing, transferable skills angle, or what to proactively address in a cover letter).

### Step 5 — Placement Notes
2–3 sentences on which bullets to lead with and why, given this specific role."""


# ── FULL RESUME ──────────────────────────────────────────────────────────────

def _format_education(edu: dict) -> str:
    notes = edu.get("notes", "")
    gpa   = edu.get("gpa", "")
    return f"""  {edu.get('degree','')} in {edu.get('field','')} — {edu.get('institution','')}
    {edu.get('start_year','') + '–' + edu.get('end_year','') if edu.get('start_year') else edu.get('end_year','')}
    {'GPA: ' + gpa if gpa else ''}{'  |  ' + notes if notes else ''}"""


def build_full_resume_prompt(
    job_description: str,
    experiences: list,
    projects: list,
    skills: list,
    education: list = None,
    candidate_name: str = "",
    candidate_email: str = "",
    candidate_phone: str = "",
    candidate_linkedin: str = "",
    resume_sample: str = "",
    include_summary: bool = True,
    exp_project_map: dict = None,
) -> str:

    # Build experience text, embedding associated sub-projects under each experience
    # exp_project_map: {exp_id_str: [list of project dicts with title, description]}
    exp_blocks = []

    for idx, e in enumerate(experiences):
        block = _format_experience(e, idx + 1)
        # Add associated sub-projects under this experience
        exp_id = e.get("id")
        if exp_project_map and str(exp_id) in exp_project_map:
            assoc_projs = exp_project_map[str(exp_id)]
            if assoc_projs:
                block += "\n  Client/Project Work under this role:\n"
                for ap in assoc_projs:
                    block += f"    Project: {ap.get('title','')}\n"
                    block += f"      Description: {ap.get('description','')}\n"
        exp_blocks.append(block)

    exp_text = "".join(exp_blocks)
    proj_text  = "".join(_format_project(p, i+1) for i, p in enumerate(projects))
    skill_text = _format_skills(skills)
    edu_text   = "\n".join(_format_education(e) for e in (education or [])) if education else "  Not provided"
    style_section = _writing_sample_section(resume_sample, "Resume")
    name_line = f"Candidate: {candidate_name}" if candidate_name else ""

    # Build contact header instruction
    contact_parts = [candidate_name or ""]
    if candidate_email:  contact_parts.append(candidate_email)
    if candidate_phone:  contact_parts.append(candidate_phone)
    if candidate_linkedin: contact_parts.append(candidate_linkedin)
    contact_line = " | ".join(p for p in contact_parts if p)

    num_experiences = len(experiences)
    has_projects_in_exp = bool(exp_project_map and any(
        v for v in exp_project_map.values() if v
    ))

    # Budget bullets to fill exactly one page — minimum 2 per entry
    if has_projects_in_exp:
        if num_experiences <= 2:
            bullet_guidance = "1-2 general bullets about the role, then project sub-entries with 2 sub-bullets each"
        elif num_experiences <= 3:
            bullet_guidance = "1 general bullet about the role, then project sub-entries with 2 sub-bullets each"
        else:
            bullet_guidance = "1 general bullet, then project sub-entries with 1-2 sub-bullets each"
    else:
        if num_experiences <= 2:
            bullet_guidance = "4-5 bullet points per role"
        elif num_experiences <= 3:
            bullet_guidance = "3-4 bullet points per role"
        elif num_experiences <= 4:
            bullet_guidance = "2-3 bullet points per role"
        else:
            bullet_guidance = "2 bullet points per role"

    summary_section = ""
    sec_num = 1
    if include_summary:
        summary_section = f"""
{sec_num}. **PROFESSIONAL SUMMARY** (2-3 concise sentences as a SINGLE paragraph — no line breaks within)
   - Positioning statement tailored to this role
   - Include years of experience and 2-3 key strengths
   - Naturally weave in top ATS keywords
"""
        sec_num += 1

    exp_sec = sec_num
    sec_num += 1
    proj_sec = sec_num
    sec_num += 1
    edu_sec = sec_num
    sec_num += 1
    skill_sec = sec_num

    # Project sub-entry instructions for work experience
    project_instructions = ""
    if has_projects_in_exp:
        project_instructions = """
   **PROJECT SUB-ENTRIES (for roles with associated projects/client work):**
   - After the role header and any general bullets, list each project as a sub-heading:
     [PROJECT] Project Title — Client/Context
   - Under each [PROJECT] line, add at least 2 sub-bullets (indented with "  - "):
     Each sub-bullet: [Action Verb] + [What/How] + [Measurable Result]
   - Example:
     BroadBranch Advisors — Strategy Consultant  >>  Sep 2024–Sep 2025 | Washington, DC
     - Delivered market research and GTM strategies for pharma and biotech clients
     [PROJECT] Pricing Strategy & Portfolio Planning (Industrial Life Sciences Client)
       - Directed financial analysis synthesizing stakeholder insights with quantitative data to define 5-year investment roadmap
     [PROJECT] Point-of-Care Diagnostics Benchmarking (Molecular Diagnostics Client)
       - Led global stakeholder engagement across 60+ interviews in US, UK, and Germany
   - The [PROJECT] marker is CRITICAL — it tells the formatter to render the title as a bold sub-heading
   - Sub-bullets under [PROJECT] lines MUST start with exactly "  - " (two spaces, dash, space)
"""

    return f"""You are a professional resume writer. Produce a COMPLETE, ATS-optimized, FULL-PAGE resume tailored to this job. The resume must sound like this candidate and follow the structure of their existing resume.

CRITICAL CONSTRAINT #1 — INCLUDE EVERYTHING: You MUST include EVERY experience, project, and education entry listed below. These were hand-picked by the candidate — do NOT skip, omit, or drop any of them. Every single one must appear in the final resume with substantive content. Each entry must have at least 2 bullet points.

CRITICAL CONSTRAINT #2 — EXACTLY ONE PAGE: The resume MUST fit on exactly ONE PAGE. Do NOT exceed one page. Fill the page well — avoid being too sparse — but staying within one page is the top priority. Use the bullet counts specified below and keep bullets concise (1 line each when printed). The user can expand individual entries later if needed.

{name_line}

{style_section}
## JOB DESCRIPTION
{job_description}

## CANDIDATE PROFILE

### Work Experience
{exp_text or '  Not provided'}

### Standalone Projects
{proj_text or '  Not provided'}

### Skills
{skill_text}

### Education
{edu_text}

## YOUR TASK

### Internal Analysis (do NOT include in output)
Before writing, analyze:
1. Top 10 ATS keywords that must appear
2. The 2-3 core capabilities the hiring manager needs proven
3. ALL experiences below were selected by the candidate and MUST appear — give more bullets to relevant ones, fewer to less relevant, but NEVER skip any
4. Budget carefully: the resume MUST fit on exactly one page. Allocate bullets per role as specified, keep each bullet to ~1 printed line, include all education entries. Count your output to stay within ~50 lines total.

### Write the Complete Resume

Output ONLY the final resume text — no commentary, no analysis, no explanation.

**Contact Header (exactly 2 lines):**
Line 1: {candidate_name or 'Candidate Name'}
Line 2: {' | '.join(p for p in contact_parts[1:] if p) or 'contact info'}

**Resume Structure — follow this EXACT order:**
{summary_section}
{exp_sec}. **WORK EXPERIENCE** (reverse chronological order)
   - CRITICAL FORMAT: Each role header must be a SINGLE line with company/role on the left and date/location on the right, separated by exactly "  >>  " (two spaces, two greater-than signs, two spaces):
     Company Name — Job Title  >>  Date Range | Location
   - Example: BroadBranch Advisors — Strategy Consultant  >>  Sep 2024–Sep 2025 | Washington, DC
   - {bullet_guidance}
{project_instructions}
   **BULLET QUALITY REQUIREMENTS:**
   - Every bullet MUST start with a strong, specific action verb (Led, Directed, Designed, Built, Drove, Orchestrated, Spearheaded — NOT generic verbs like Helped, Assisted, Worked on, Responsible for)
   - Every bullet MUST include a concrete, quantified result: revenue, cost savings, %, headcount, timeframe, number of stakeholders, project scope
   - Use the candidate's OWN metrics from their profile — do not invent numbers
   - Follow the XYZ formula: Accomplished [X] as measured by [Y], by doing [Z]
   - Weave in exact keywords from the job description naturally
   - Each bullet should be a concise, impactful sentence — aim for ~1 printed line per bullet
   - Prioritize bullets that directly address the TOP job requirements
   - For less relevant roles, include 2 bullets highlighting transferable skills

{proj_sec}. **PROJECTS** (include relevant standalone projects — 1-2 bullets each)
   - Format: Project Name — Context (no >> needed, projects have no dates)

{edu_sec}. **EDUCATION** (ALWAYS include ALL education entries from the candidate's profile)
   - Format: Degree, Field, Minor (if any) — Institution (Year)
   - Keep to 1 line per entry

{skill_sec}. **SKILLS** (last section — 2-3 lines max)
   - Comma-separated list grouped by category
   - Format: Category: Skill1, Skill2, Skill3

**One-Page Formatting Rules:**
- Section headers: ALL CAPS (e.g., WORK EXPERIENCE, SKILLS, EDUCATION)
- Bullet points: dash-space format (- text)
- Sub-bullets under [PROJECT] lines: two-spaces-dash-space format (  - text)
- Role headers: use the "  >>  " delimiter to separate left (company/title) from right (date/location)
- Keep bullets concise — each bullet should be ~1 printed line (roughly 80-100 characters)
- Skills section must be compact (comma-separated, not one skill per line)
- No blank lines between bullets within the same role
- Only ONE blank line between sections
- TOTAL OUTPUT must be ~48-52 lines to fit exactly one page. Count as you write. Do NOT exceed 55 lines
- Prioritize: Work Experience (most space) > Education > Projects > Skills
- Match the candidate's writing style (if sample provided)
- DO NOT output anything except the resume content itself"""


# ── COVER LETTER ──────────────────────────────────────────────────────────────

def build_cover_letter_prompt(
    job_description: str,
    experiences: list,
    projects: list,
    skills: list,
    candidate_name: str = "",
    career_summary: str = "",
    company_name: str = "",
    role_title: str = "",
    additional_notes: str = "",
    cover_letter_sample: str = "",
) -> str:

    exp_text  = "".join(_format_experience(e, i+1) for i, e in enumerate(experiences))
    proj_text = "".join(_format_project(p, i+1)    for i, p in enumerate(projects))
    skill_text = _format_skills(skills)
    style_section = _writing_sample_section(cover_letter_sample, "Cover Letter")

    name_line    = f"Candidate: {candidate_name}" if candidate_name else "Candidate: [name not set]"
    company_line = f"Target Company: {company_name}" if company_name else "Target Company: [see job description]"
    role_line    = f"Target Role: {role_title}" if role_title else "Target Role: [see job description]"
    summary_line = f"\nCareer Summary / Personal Brand: {career_summary}" if career_summary else ""
    notes_line   = f"\nAdditional Context: {additional_notes}" if additional_notes else ""

    return f"""You are a professional cover letter specialist and career coach using the Job Application Accelerator framework. Write a compelling, tailored cover letter that passes ATS screening, impresses hiring managers, and tells a compelling career story — in the candidate's own voice.

{name_line}
{company_line}
{role_line}{summary_line}{notes_line}

{style_section}
## JOB DESCRIPTION
{job_description}

## CANDIDATE PROFILE

### Work Experience
{exp_text or '  Not provided'}

### Projects
{proj_text or '  Not provided'}

### Skills
{skill_text}

## YOUR TASK

### Step 1 — Multi-Perspective Analysis (internal, do not include in output)
Run this analysis before writing — it informs every word choice:

**Recruiter:** What 5–8 keywords must appear in the letter? What minimum qualifications must be signaled?
**Hiring Manager:** What are the 2 most critical capabilities they need proven? What result do they most need to see?
**Codex:** What is the single most compelling narrative angle? What makes this candidate different from others with similar backgrounds?

### Step 2 — Write the Cover Letter
Structure:
- **Opening (2–3 sentences):** Hook with a specific, quantified achievement that directly speaks to their top need. State the role being applied for. No "I am excited to apply" openers.
- **Body Paragraph 1 (3–4 sentences):** Address the #1 and #2 job requirements with specific proof points from the candidate's experience. Include at least one quantified result.
- **Body Paragraph 2 (3–4 sentences):** Address the #3 requirement OR tell the "why this company / why this role" story. This paragraph should feel personal and specific to this company — not transferable to any employer.
- **Closing (2–3 sentences):** Forward-looking and confident. Clear call to action. No apologetic language.

Requirements:
- 250–380 words total
- Naturally incorporate 5–8 keywords from the job description
- Include at least 2 specific, quantified results from the candidate's profile
- Match the tone and style from the writing sample (if provided)
- Avoid ALL clichés: "passionate", "team player", "leverage", "utilize", "synergy", "I am writing to express my interest"
- Sound like a real, specific person — not a template

### Step 3 — Brief Debrief (after the letter)
Provide a 3-bullet "Why this works" note explaining the key strategic choices made."""


# ── ROLE ANALYSIS REPORT ─────────────────────────────────────────────────────

ANALYSIS_FORMAT = """
Your response MUST use EXACTLY these labeled section headers, each on its own line followed by a colon, then your content on the next line(s). No extra headers, no markdown bold, no deviation:

ROLE_SUMMARY:
[2-3 sentences describing the role, the team context, and what success looks like]

FIT_SCORE:
[Single integer 0-100. No %, no ranges, just the number]

FIT_RATIONALE:
[One sentence explaining the score]

RECRUITER_ANALYSIS:
[2-3 sentences: ATS keywords this role demands, minimum qualifications, any red flags or screening risks for this candidate]

HIRING_MANAGER_ANALYSIS:
[2-3 sentences: Core capabilities they need proven in the first 90 days, what evidence from the candidate's profile is strongest, what's weakest]

CAREER_COACH_ANALYSIS:
[2-3 sentences: The narrative angle that makes this candidate compelling, how to position the career story, differentiation vs. typical applicants]

GAP_ANALYSIS:
- [Gap 1: specific missing requirement and mitigation strategy]
- [Gap 2: same format]
- [Gap 3: same format — include at least 2, maximum 5]

RECOMMENDED_NEXT_STEPS:
1. [Concrete action with specific reason tied to this role]
2. [Second action]
3. [Third action]"""


def build_role_analysis_prompt(
    job_description: str,
    experiences: list,
    projects: list,
    skills: list,
    candidate_name: str = "",
    career_summary: str = "",
) -> str:
    exp_text   = "".join(_format_experience(e, i+1) for i, e in enumerate(experiences))
    proj_text  = "".join(_format_project(p, i+1)    for i, p in enumerate(projects))
    skill_text = _format_skills(skills)
    name_line    = f"Candidate: {candidate_name}" if candidate_name else ""
    summary_line = f"Career Summary: {career_summary}" if career_summary else ""

    return f"""You are a senior talent strategist analyzing a job opportunity for a specific candidate. Evaluate this role against the candidate's profile from three professional lenses — recruiter, hiring manager, and career coach — and produce a structured fit report.

{name_line}
{summary_line}

## JOB DESCRIPTION
{job_description}

## CANDIDATE PROFILE

### Work Experience
{exp_text or '  Not provided — candidate has not yet added work experience'}

### Projects
{proj_text or '  Not provided'}

### Skills
{skill_text}

## YOUR ANALYSIS
{ANALYSIS_FORMAT}

CRITICAL: Follow the section header format exactly. Start each header at the beginning of its line. The FIT_SCORE must be a single integer only. The GAP_ANALYSIS bullets must start with "- ". The RECOMMENDED_NEXT_STEPS must start with "1. ", "2. ", etc."""


# ── MARKDOWN IMPORT ───────────────────────────────────────────────────────────

PROFILE_JSON_SCHEMA = """{
  "experiences": [
    {
      "company": "string",
      "title": "string",
      "start_date": "string (e.g. 'Jan 2022')",
      "end_date": "string (e.g. 'Mar 2024' or 'Present')",
      "is_current": true/false,
      "location": "string",
      "description": "string — brief overview of the role and team",
      "day_to_day": "string — detailed day-to-day responsibilities, tools, stakeholders, processes",
      "achievements": ["string", "string"],
      "skills": ["string", "string"]
    }
  ],
  "projects": [
    {
      "name": "string",
      "role": "string",
      "company": "string (or 'Personal Project')",
      "description": "string",
      "outcome": "string",
      "metrics": "string",
      "tech_stack": ["string"],
      "link": "string",
      "featured": true/false
    }
  ],
  "skills": [
    {
      "name": "string",
      "category": "Technical | Tools & Software | Languages | Soft Skills | Domain Knowledge | Certifications | Other",
      "proficiency": "Expert | Advanced | Proficient | Familiar | Learning",
      "notes": "string"
    }
  ],
  "education": [
    {
      "institution": "string",
      "degree": "string",
      "field": "string",
      "start_year": "string",
      "end_year": "string",
      "gpa": "string",
      "notes": "string"
    }
  ]
}"""


def build_markdown_import_prompt(markdown_content: str) -> str:
    return f"""You are a profile data extractor. A candidate has provided their professional background as a markdown document. Your task is to parse it into a structured JSON object that can be imported into their career coaching app.

## CANDIDATE'S MARKDOWN DOCUMENT
---
{markdown_content.strip()}
---

## YOUR TASK

Extract ALL professional information from the document and return a single valid JSON object that exactly matches this schema:

```json
{PROFILE_JSON_SCHEMA}
```

Rules:
- Extract every work experience, project, skill, and education entry you can find
- For `day_to_day`: expand bullet points into a cohesive paragraph describing daily responsibilities, tools used, people worked with, and processes owned. Be thorough — this is the most important field for job applications.
- For `achievements`: pull out quantified wins, projects completed, improvements made. Each should be a single concise sentence with metrics if available.
- For `skills`: infer from tools mentioned, technologies listed, and responsibilities described — not just explicit skill lists. Include both technical and soft skills.
- If a field is not mentioned, use an empty string or empty array.
- `is_current` is true only if the role explicitly says "present", "current", or has no end date in a context suggesting they still work there.
- Return ONLY valid JSON — no markdown code fences, no explanation, no commentary. Just the raw JSON object starting with `{{` and ending with `}}`."""


# ── AI INTERVIEW ──────────────────────────────────────────────────────────────

INTERVIEW_SECTION_GUIDES = {
    "experience": {
        "label": "Work Experience",
        "key_fields": ["company and team context", "day-to-day responsibilities",
                       "key projects and outcomes", "metrics and business impact",
                       "tools and technologies used", "team size and your role",
                       "stakeholders you worked with", "challenges you overcame"],
        "example_questions": [
            "What did a typical week look like in that role?",
            "What were the 2–3 projects you're most proud of?",
            "Can you put a number on the impact — revenue, efficiency, users, cost savings?",
            "Who did you collaborate with most — engineering, sales, executives?",
            "What tools or systems were central to your work?",
        ]
    },
    "project": {
        "label": "Project",
        "key_fields": ["what problem it solved", "your specific contributions",
                       "technical approach and key decisions", "measurable outcomes",
                       "challenges and how you overcame them", "team and stakeholders",
                       "tools and technologies", "what you'd do differently"],
        "example_questions": [
            "What was the core problem this project solved?",
            "What were the key technical decisions you made?",
            "What was the most challenging part and how did you handle it?",
            "What did success look like — how did you measure it?",
            "Who else was involved and what was your specific contribution?",
        ]
    },
}


def build_interview_round1_prompt(section_type: str, initial_narrative: str) -> str:
    guide = INTERVIEW_SECTION_GUIDES.get(section_type, INTERVIEW_SECTION_GUIDES["experience"])

    return f"""You are a senior career coach conducting a profile interview. A candidate has given you an initial description of a {guide['label']}. Your job is to ask targeted follow-up questions to draw out the rich detail needed to create compelling job application materials.

## WHAT THE CANDIDATE TOLD YOU
---
{initial_narrative.strip()}
---

## YOUR TASK

Analyze what they've shared. Identify the gaps — what's vague, what's missing metrics, what details would make this compelling on a resume or in a cover letter.

Then ask exactly **5–7 specific, numbered follow-up questions** that will extract:
{chr(10).join('- ' + f for f in guide['key_fields'])}

Rules for your questions:
- Make each question specific to what THEY said — no generic questions
- Ask about numbers and metrics wherever possible ("You mentioned improving retention — by how much? Over what timeframe?")
- Ask about scope ("How large was the team? What was the budget? How many users/customers were affected?")
- Ask "what did you personally do" questions to separate their contribution from the team's
- Keep each question concise and answerable
- Number each question (1. 2. 3. etc.)
- End with: "Take your time — the more specific your answers, the stronger your materials will be."

Do NOT write an introduction paragraph. Start directly with Question 1."""


def build_interview_extraction_prompt(
    section_type: str,
    initial_narrative: str,
    questions_and_answers: list  # list of {"question": str, "answer": str}
) -> str:
    guide = INTERVIEW_SECTION_GUIDES.get(section_type, INTERVIEW_SECTION_GUIDES["experience"])

    qa_text = "\n\n".join(
        f"Q: {qa['question']}\nA: {qa['answer']}"
        for qa in questions_and_answers
        if qa.get('answer', '').strip()
    )

    if section_type == "experience":
        schema = """{
  "company": "string",
  "title": "string",
  "start_date": "string",
  "end_date": "string",
  "is_current": true/false,
  "location": "string",
  "description": "string — 2-3 sentence role overview",
  "day_to_day": "string — rich paragraph describing daily work, tools, stakeholders, processes. Be thorough — 4-8 sentences.",
  "achievements": ["string with metrics", "string with metrics"],
  "skills": ["string", "string"]
}"""
    else:
        schema = """{
  "name": "string",
  "role": "string",
  "company": "string",
  "description": "string — rich description of what you built/did and how",
  "outcome": "string — concrete results and impact",
  "metrics": "string — numbers, percentages, scale",
  "tech_stack": ["string"],
  "link": "string",
  "featured": true/false
}"""

    return f"""You are a career profile writer. A candidate just completed a profile interview about a {guide['label']}. Using all the information gathered, synthesize it into a rich, detailed JSON profile entry.

## INITIAL NARRATIVE
{initial_narrative.strip()}

## INTERVIEW Q&A
{qa_text}

## YOUR TASK

Synthesize everything above into a single JSON object matching this schema:

```json
{schema}
```

Rules:
- `day_to_day` (for experience) or `description` (for project) must be a rich, detailed paragraph — not bullet points. Write 4–8 sentences that paint a vivid picture of the actual work. Include tools, stakeholders, processes, and scope.
- `achievements` must have specific, quantified statements wherever numbers were mentioned. Format: "[Action verb] + [what] + [result with metric]"
- `skills` should include both technical tools AND soft skills demonstrated (e.g., "Stakeholder Management", "Cross-functional Leadership")
- Infer reasonable values from context when not explicitly stated
- Return ONLY raw JSON — no markdown fences, no explanation. Start with `{{` and end with `}}`."""


# ── CONVERSATIONAL INTERVIEW ──────────────────────────────────────────────────

def build_interview_chat_system_prompt(section_type: str, existing_entry: dict) -> str:
    """System prompt for multi-turn conversational profile interview."""
    guide = INTERVIEW_SECTION_GUIDES.get(section_type, INTERVIEW_SECTION_GUIDES["experience"])

    # Format existing entry for Claude
    entry_lines = []
    if existing_entry:
        if existing_entry.get("title"):
            entry_lines.append(f"Role: {existing_entry['title']}")
        if existing_entry.get("company"):
            entry_lines.append(f"Company: {existing_entry['company']}")
        start = existing_entry.get("start_date", "")
        end = "Present" if existing_entry.get("is_current") else existing_entry.get("end_date", "")
        if start or end:
            entry_lines.append(f"Dates: {start} – {end}")
        if existing_entry.get("description"):
            entry_lines.append(f"Overview: {existing_entry['description']}")
        if existing_entry.get("day_to_day"):
            entry_lines.append(f"Day-to-day: {existing_entry['day_to_day']}")
        achs = existing_entry.get("achievements", [])
        if isinstance(achs, list) and achs:
            ach_text = "\n".join(f"  • {a}" for a in achs[:8])
            entry_lines.append(f"Achievements:\n{ach_text}")
        elif isinstance(achs, str) and achs.strip():
            entry_lines.append(f"Achievements: {achs[:500]}")
        skills = existing_entry.get("skills", [])
        if isinstance(skills, list) and skills:
            entry_lines.append(f"Skills: {', '.join(skills[:12])}")
        # Project-specific fields
        if existing_entry.get("name"):
            entry_lines.insert(0, f"Project: {existing_entry['name']}")
        if existing_entry.get("outcome"):
            entry_lines.append(f"Outcome: {existing_entry['outcome']}")

    if entry_lines:
        entry_summary = "\n".join(entry_lines)
    else:
        entry_summary = f"(No data yet — starting fresh for a new {guide['label']})"

    return f"""You are a career coach conducting a focused, conversational profile interview. Your goal: ask targeted questions that draw out the rich detail needed for compelling job application materials.

CURRENT PROFILE DATA:
{entry_summary}

YOUR MISSION:
Deepen this profile by discovering what's missing — quantified impact, how things were actually done, key decisions made, team context, and concrete results.

RULES (follow strictly):
1. Ask exactly ONE question per response — never combine questions
2. Keep questions short, specific, and conversational (1-2 sentences max)
3. Reference real details from the profile when asking — make it personal ("You mentioned cutting onboarding time — how did you actually do that?")
4. Vary your focus: metrics → how/process → decisions → team context → tools → lessons learned
5. Be warm and encouraging — like a coach, not an interrogator
6. After 5-6 exchanges when you feel you have rich, detailed information, your ENTIRE response MUST start with exactly: "✅ I think I have what I need." — then add one sentence offering to build the profile entry. Never use this phrase earlier.
7. Do NOT write preambles, introductions, or "Great answer!" filler before your question — just ask the question directly
8. If the candidate's answer is thin, probe deeper on the same topic before moving on

START: When the user sends "[BEGIN INTERVIEW]", open with one specific, targeted question referencing the most interesting detail in the existing data. If data is sparse, ask the most important missing question (typically: what was the scale/scope of impact?)."""


def build_interview_finalize_prompt(section_type: str, existing_entry: dict, history: list) -> str:
    """Build extraction prompt from the completed conversation history."""
    guide = INTERVIEW_SECTION_GUIDES.get(section_type, INTERVIEW_SECTION_GUIDES["experience"])

    # Format conversation
    convo_lines = []
    for msg in history:
        role_label = "COACH" if msg.get("role") == "assistant" else "CANDIDATE"
        content = msg.get("content", "").strip()
        if content and content != "[BEGIN INTERVIEW]":
            convo_lines.append(f"{role_label}: {content}")
    convo_text = "\n\n".join(convo_lines)

    # Format existing entry
    entry_lines = []
    if existing_entry:
        for k, v in existing_entry.items():
            if v and k not in ("id", "user_id", "created_at", "updated_at"):
                entry_lines.append(f"{k}: {v}")
    entry_text = "\n".join(entry_lines) if entry_lines else "(none)"

    if section_type == "experience":
        schema = """{
  "company": "string",
  "title": "string",
  "start_date": "YYYY-MM or year string",
  "end_date": "YYYY-MM or year string",
  "is_current": true or false,
  "location": "string or empty",
  "description": "2-3 sentence role overview",
  "day_to_day": "Rich 4-8 sentence paragraph of daily work, tools, stakeholders, processes",
  "achievements": ["Achievement with metric", "Achievement with metric"],
  "skills": ["skill1", "skill2"]
}"""
    else:
        schema = """{
  "name": "string",
  "role": "string",
  "company": "string or empty",
  "description": "rich description of what was built and how",
  "outcome": "concrete results and impact",
  "metrics": "numbers, percentages, scale",
  "tech_stack": ["tech1", "tech2"],
  "link": "string or null",
  "featured": true or false
}"""

    return f"""You are a career profile writer. A career coach just completed a deep-dive interview about a {guide['label']}. Synthesize the existing profile data AND the full interview conversation into a rich, detailed profile entry.

EXISTING PROFILE DATA:
{entry_text}

INTERVIEW CONVERSATION:
{convo_text}

YOUR TASK:
Synthesize everything above into a single JSON object. Prioritize information from the interview conversation — it contains the most recent and detailed data. Make achievements as specific and metric-rich as possible. Write day_to_day / description as flowing paragraphs, not bullet points. For achievements, use the format: "[Action verb] [what] [result with metric]".

OUTPUT FORMAT — return ONLY the raw JSON object, no markdown fences, no explanation:

{schema}"""
