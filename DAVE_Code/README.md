# DAVE (Documents and Applications Validation Engine)

## Overview
DAVE is a digital application verification system for Irish government and university workflows. It supports document upload, OCR, NER, AI validation, and admin review.

## Features
- User registration and login
- Application submission (SUSI, Visa, University, etc.)
- Document upload and OCR
- NER (spaCy, transformers, HuggingFace)
- Admin dashboard (per-type review)
- Application status change notifications (in-app, email)
- REST API (FastAPI)

## Setup
1. Clone the repo
2. Install Python 3.14+
3. `pip install -r requirements.txt`
4. Set up `.env` with MongoDB and API keys
5. Run `python backend/scripts/create_admin_users.py` to create admin users
6. Start backend: `python start_server.py`
7. Open `frontend/index.html` or `frontend/admin.html`

## Admin Users
- `susi@dave.ie` (SUSI applications)
- `visa@dave.ie` (Visa applications)
- `university@dave.ie` (University admissions)
- Password for all: `changeme123`

## API Docs
- Swagger UI: `/docs`
- Redoc: `/redoc`

## Deployment
- Local: `python start_server.py`
- Docker: *(add Dockerfile and docker-compose.yml)*
- Production: Use Gunicorn/Nginx (see FastAPI docs)

## Notifications
- In-app and email notifications on status change
- Webhook support: *(extend notification_service.py as needed)*

## Contributing
- PRs welcome. See issues for roadmap.

---
*For more details, see code comments and API docs.*
