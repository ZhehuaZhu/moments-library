# Moments Library

A full-stack Flask web app for running a private "Moments" space with media management, folder organization, edit history, geolocation, and a recycle bin.

This project is designed as a personal archive that feels part social feed, part knowledge library:
- publish text, images, videos, PDFs, and documents
- attach a readable location using browser geolocation plus reverse geocoding
- organize content into nested folders with descriptions
- assign one moment to multiple folders
- edit published moments with revision history
- soft-delete content and restore it from the recycle bin
- search across text, files, locations, and folder metadata

## Features

### Feed and Publishing
- public read-only feed
- admin-only publishing and management
- mixed file upload support for images, videos, PDFs, and documents
- UUID-based file renaming for safe storage
- in-feed image and video preview
- inline PDF preview
- document download/open links for other file types

### Folder System
- create folders with descriptions
- create nested child folders
- browse folders in a tree-style sidebar
- assign one moment to multiple folders
- delete folders without losing moments

### Editing and History
- edit existing moments after publishing
- keep revision snapshots of previous versions
- review edit history in a dedicated admin-only view

### Safety and Recovery
- soft delete instead of hard delete
- recycle bin view for deleted moments
- restore deleted moments
- CLI command to purge old recycle-bin content

### Search
- search by moment text
- search by location label
- search by attachment file name
- search by folder name and folder description

## Tech Stack

- Python 3.13
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-Login
- Flask-WTF
- SQLite
- HTML, CSS, and vanilla JavaScript

## Project Structure

```text
app/
  blueprints/        Routes for pages, auth, and APIs
  services/          Upload, geocoding, folder, and schema helpers
  static/            CSS, JS, and upload directory
  templates/         Jinja templates and reusable UI partials
tests/               Pytest coverage for core behavior
run.py               Local entry point with admin bootstrap
```

## Quick Start

### 1. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 2. Run the app

The easiest local entry point is:

```powershell
python run.py
```

On first launch, the app will:
- create the database schema
- ensure compatibility upgrades for the local SQLite database
- prompt you to create an admin account if none exists

The app runs at:

- [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Useful Commands

### Reset admin credentials

```powershell
python run.py --reset-admin
```

### Initialize the database manually

```powershell
python -m flask --app run.py init-db
```

### Create or update the admin account manually

```powershell
python -m flask --app run.py init-admin
```

### Purge old recycle-bin data

```powershell
python -m flask --app run.py purge-recycle-bin --days 30
```

## Testing

```powershell
python -m pytest
```

Current automated coverage includes:
- login behavior
- public/admin access control
- publishing with uploads
- nested folder creation
- multi-folder assignment
- folder deletion behavior
- moment editing and revision history
- recycle bin restore flow
- search behavior
- reverse geocoding API behavior

## Notes

- local SQLite data is stored under `instance/app.db`
- uploaded files are stored under `app/static/uploads/`
- the repository ignores the local database and uploaded content by default

## GitHub

Repository:

- [https://github.com/ZhehuaZhu/moments-library](https://github.com/ZhehuaZhu/moments-library)

## Production Update Flow

If the server was deployed from a Git checkout, future updates can use a simple pull-and-restart flow.

### One-command update on the server

```bash
cd /srv/moments/app
bash scripts/update-production.sh
```

The update script will:
- pull the latest `main` branch changes from GitHub
- install any updated Python dependencies into the existing virtual environment
- restart `moments.service`
- run a local HTTP health check on `127.0.0.1:8000`

### Important persistent paths

These paths should be preserved between deployments:

- `instance/app.db`
- `app/static/uploads/`
- `/etc/moments.env`

### If the server was deployed from a tarball first

Do one migration from the unpacked folder to a Git checkout:

1. Back up `instance/` and `app/static/uploads/`
2. Replace the app directory with a fresh `git clone`
3. Restore `instance/` and `app/static/uploads/`
4. Reuse the existing `.venv`, `/etc/moments.env`, `moments.service`, and nginx config if desired
