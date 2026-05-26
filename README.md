# MineMarshall

28th August 2025 - 19th May 2026
## PROJECT OVERVIEW
1. MineMarshall is a people management system for mine sites, built for OreFox AI. The project scope covered the full onboarding and compliance lifecycle for mine site workers: admins invite workers via tokenised email links, workers set up accounts and submit role-specific induction forms, and the system tracks credential validity (including driver's  OCR scanning), form submission status, and project-level compliance. A metrics dashboard gives admins an at-a-glance view of all workers across projects with filterable compliance status.
2. Demo video: https://www.notion.so/orefox/Handover-36505cef1f228091ba61e4fff5093c20
3. Notion Page: https://www.notion.so/orefox/MineMarshal-Mine-site-People-management-system-25b05cef1f22800389e8c26b7ac3da4f
## SET UP INSTRUCTIONS
### Additional Packages:
  #### Python Packages:
  - Django==5.2.6
  - django-environ==0.13.0
  - easyocr==1.7.2
  - ollama==0.6.1
  - psycopg2-binary==2.9.12
  #### System Packages (Linux/Windows(WSL) via apt):
  - postgresql, postgresql-contrib, postgis, gdal-bin, libgdal-dev, binutils, lobproj-dev - database server+dependencies
  - curl, zstd - used in Ollama installation
  #### System Packages (MacOS via Homebrew):
  - postgresql, postgis, gdal, proj, zstd - Equivalents of above
  #### Ollama:
  - Ollama with model llama3.2:3b
### File structure list, mentioning all the files and folders added to the project and what they do.  
  - `accounts/` — Django app for authentication and onboarding
    - `backends.py` — Custom case-insensitive email login backend
    - `forms.py` — User profile edit form
    - `models.py` — CustomUser model
    - `ocr.py` — Driver's licence OCR using easyOCR + Ollama
    - `views.py` — Login, profile, onboarding, and licence renewal views
    - `urls.py` — URL routes for the accounts app
    - `admin.py` — Django admin configuration for CustomUser
    - `templates/accounts/` — Onboarding, licence scan, and renewal templates
    - `templates/registration/login.html` — Login page
  - `dashboard/` — Django app for the main application
    - `models.py` — All core models
    - `views.py` — All main views
    - `services.py` — Business logic for user creation and licence reminders
    - `urls.py` — URL routes for the dashboard app
    - `admin.py` — Django admin configuration
    - `management/commands/send_licence_expiry_reminders.py` — Scheduled command for licence expiry emails
    - `templates/base.html` — Base layout (sidebar, header, toast notifications)
    - `templates/onboarding_base.html` — Simplified layout for onboarding/renewal flows
    - `templates/dashboard.html` — Main dashboard with project cards and attention panel
    - `templates/personnel.html` — Worker list with search, add, and induction
    - `templates/user_profile.html` — Worker profile with credentials and submissions
    - `templates/my_forms.html` — Form builder — create, edit, and view forms
    - `templates/view_form.html` — Form preview
    - `templates/metrics.html` — Project metrics and compliance dashboard
    - `templates/projects.html` — Admin project list and create project
    - `templates/project_detail.html` — Project roles, invites, and approval documents
    - `templates/project_submissions.html` — Submission list with approve/reject
    - `templates/view_submission.html` — Read-only submission review
    - `templates/my_projects.html` — Worker-facing project and invite list
    - `templates/project_invite_form.html` — Worker induction form with auto-save
    - `templates/submission_detail.html` — Detailed submission view (admin only)
    - `templates/forms/default_form.html` — Printable induction form
    - `templates/forms/onboarding_default_form.html` — Onboarding version of the induction form
  - `static/img/` — Orefox logo and favicon
  - `static/json/` — Reserved for future JSON files(none used in project)
  - `static/js/` — Reserved for future JavaScript files(no javascript files used in project)
  - `static/css/` — Reserved for future CSS files(no css directly used in project, styling was done through TailwindCSS and DaisyUI)
  - `MineMarshall/settings.py` — Project settings
  - `MineMarshall/urls.py` — Root URL configuration
  - `.env` — Environment variables and secrets
  - `requirements.txt` — Python dependencies
  - `MineMarshall Installation Guide.pdf/md` — Full setup and installation guide
## Installation
Please see MineMarshall Installation Guide.pdf for installation instructions 

## Incomplete Components
No components were left incompolete. 