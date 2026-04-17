# CareerCoach - Job Application & Achievement Tracker

A personal job application management system that leverages AI to create tailored, compelling application materials while tracking your professional journey.

---

## Problem Statement

Job searching is exhausting. Candidates face multiple challenges:

- **Repetitive Work**: Rewriting cover letters and resume bullets for every application wastes time on formatting and redundant content
- **Lack of Consistency**: Without a centralized system, it's hard to track which skills and achievements you've highlighted for different roles
- **Poor Targeting**: Generic applications rarely stand out. Creating truly customized materials for each role requires manual effort across multiple documents
- **Lost Context**: Achievements, experiences, and projects get buried in documents instead of being organized and reusable
- **Application Chaos**: Tracking the status of dozens of applications across different companies and interview stages is overwhelming

**CareerCoach** solves these problems by creating a unified platform for managing your professional profile, generating AI-powered tailored application materials, and tracking your job search journey.

---

## What It Accomplishes

### 🎯 **Centralized Profile Management**
- Create and manage multiple job application profiles (e.g., "Senior Engineer Track", "Product Manager Track")
- Store and organize your professional identity: work experience, education, skills, certifications, projects, and achievements
- Maintain writing samples to ensure generated content matches your authentic voice

### 📄 **AI-Powered Content Generation**
- Automatically generate customized cover letters aligned with job descriptions using Claude AI
- Transform raw experiences into polished resume bullets with measurable impact
- Leverage the Job Application Accelerator framework for strategic, compelling storytelling
- Generate content that reflects your unique skills and achievements for each specific opportunity

### 📋 **Template System**
- Upload resume or cover letter templates to maintain your preferred formatting, fonts, and page layout
- Automatically generate properly formatted .docx output documents that match your template structure
- Never lose your professional brand while customizing content for each role

### 🗂️ **Job Application Tracking**
- Track the status of every application through the pipeline: Saved → Applied → Phone Screen → Interview → Final Round → Offer/Rejected/Accepted
- Organize applications by company, role, and status
- Maintain a complete record of your job search activity

### 🧠 **Skill & Achievement Organization**
- Categorize skills: Technical, Tools & Software, Languages, Soft Skills, Domain Knowledge, Certifications
- Rate proficiency levels: Expert, Advanced, Proficient, Familiar, Learning
- Store achievements with metrics and outcomes for easy reference in applications
- Build a reusable library of your accomplishments

### 💾 **Persistent Local Storage**
- All data stored locally in SQLite—nothing is sent to external servers
- Full control over your professional information
- Works offline after initial setup

---

## Tech Stack

- **Backend**: Python Flask
- **Database**: SQLite
- **Frontend**: HTML/CSS/JavaScript
- **AI Integration**: Claude API (via Anthropic SDK)
- **Document Processing**: python-docx for template parsing and document generation

---

## Quick Start

### Prerequisites
- Python 3.8+
- pip

### Installation

1. Clone or download this repository
2. Navigate to the project directory
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the App

**On macOS/Linux:**
```bash
./start_app.sh
```

**On Windows:**
```bash
start_app.bat
```

**Or manually:**
```bash
python app.py
```

Then open your browser and navigate to: **http://localhost:5050**

---

## Features Snapshot

✅ Multiple job application profiles  
✅ Comprehensive professional profile builder  
✅ Claude AI-powered cover letter generation  
✅ Resume bullet point optimization  
✅ Document template upload and formatting  
✅ Job application status tracking  
✅ Skill inventory with proficiency levels  
✅ Achievement and project portfolio  
✅ Local SQLite database (privacy-first)  
✅ REST API endpoints for all core functions  

---

## Configuration

Set your Claude API key and preferred model in the app settings:

- Supported models: claude-opus-4-7, claude-sonnet-4-6, claude-haiku-4-5
- Default: claude-sonnet-4-6

---

## Privacy & Security

- **Local-First**: All your professional data stays on your machine
- **API Only**: Only prompts and content for generation are sent to Claude API
- **No Analytics**: No tracking or telemetry collection
- **Your Control**: Delete or modify any data at any time

---

## Project Structure

```
CareerCoach/
├── app.py                 # Main Flask application
├── database.py            # SQLite database schema and queries
├── generator.py           # Claude API integration & content generation
├── document_parser.py     # Template parsing & document formatting
├── requirements.txt       # Python dependencies
├── templates/             # HTML templates for the web interface
├── career_coach.db        # SQLite database (created on first run)
└── mockups/              # UI mockup files for preview
```

---

## Future Enhancements

- Export application history and metrics
- LinkedIn profile integration
- Interview preparation guides
- Salary negotiation templates
- Advanced application analytics

---

## Contributing

Found a bug? Have a feature idea? Feel free to open an issue or submit a pull request.

---

## License

This project is open source and available under the MIT License.

---

**Made with ❤️ to help job seekers win their dream roles.**
