# Moments Library

Moments Library is a private, single-user-first archive built with Flask, SQLite, server-rendered HTML, and vanilla JavaScript. It combines:

- a WeChat-Moments-like feed for text, images, video, PDFs, and small documents
- a folder system with nesting and multi-assignment
- long-form content modules for books, music, and videos
- a footprints map that aggregates location-based moments by city and country
- an admin-only authoring workflow on top of a public read-only presentation layer

This README is written for maintainers. It explains how the app is structured, how data flows through it, how the modules relate to each other, and what to be careful about in production.

## 1. Product Intent

The app is not a generic CMS. It is designed as a personal media archive with a soft social-feed presentation:

- the feed is the primary entry point
- books, music, and videos are parallel archive modules, not separate apps
- the footprints map is a geographic lens over feed content, not a GIS-first product
- the UI intentionally mixes library/archive semantics with lightweight social browsing

In practice, this means:

- feed content is the canonical source of "moments"
- media-heavy presentation matters almost as much as CRUD correctness
- maintainers should preserve the "personal archive" feel when changing layout or data flow

## 2. Current User-Facing Modules

### Feed (`/`)

The feed is the home page and central content surface.

What it does:

- renders moments in reverse chronological order
- supports text-only, citation-only, and mixed-media moments
- allows one moment to live in multiple folders
- supports admin publishing, editing, soft deletion, restore, and revision history
- supports in-feed image/video/PDF/document rendering
- uses an immersive media viewer for large image/video preview

Current interaction style:

- image/video previews open in an immersive overlay
- dynamic media tiles use thumbnails/previews rather than raw originals where possible
- the homepage prioritizes the feed over summary cards

### Folders / Structure

Folders are not just tags. They are hierarchical collections with descriptions and a "structure view".

What it does:

- create nested folders
- assign one moment to multiple folders
- calculate counts across descendants
- preserve moments when folders are deleted
- expose a folder tree and a folder-map-style panel in the sidebar

The left sidebar contains:

- top-level app modules: Feed, Footprints, Books, Music, Videos
- filter shortcuts: uncategorized, recycle bin
- search
- folder management and structure view

### Books (`/books`)

Books are library entries with reading state, optional cover art, optional generated reader assets, and anchored notes.

What it does:

- upload source files (`txt`, `md`, `pdf`, `docx`, `epub`, `mobi` through conversion paths)
- infer metadata where possible
- generate lightweight reader-ready assets
- open a dedicated reader page
- store annotations with text anchors when supported

Conceptually:

- Books are slower, deeper objects than moments
- The reader is a separate long-form consumption surface
- Book annotations can later be cited into the feed

### Music (`/music`)

Music entries are tracks with optional lyrics, optional cover art, and timestamped comments.

What it does:

- upload audio files
- optionally upload lyrics and cover art
- display a track detail page
- store timestamped reactions
- expose a mini floating player window

Conceptually:

- Tracks are "library items"
- Timestamp comments are the main interactive layer
- Tracks and comments can be cited from the moment composer

### Videos (`/videos`)

Videos are standalone library entries with poster/preview generation and timestamped notes.

What it does:

- upload videos
- generate browser-friendly previews and posters when needed
- render previews in the library view instead of blank placeholders
- store timestamped comments

Conceptually:

- Video library entries are separate from feed attachments, but they use similar preview ideas
- Video entries and video comments can be cited into the feed

### Footprints (`/footprints`)

Footprints is the geographic view over located moments.

What it does:

- group moments by place
- switch between city and country views
- aggregate multiple moments in one place
- render timeline/cards/popup views
- optionally display visited vs unvisited countries with a local GeoJSON overlay

Important design choice:

- the map uses aggregation first, not one-marker-per-post by default
- country mode can show visited/unvisited contrast
- city mode stays cleaner and only shows visited places

### Auth (`/login`, `/logout`)

The app has two modes:

- public read-only
- authenticated admin management

Only admins can:

- publish
- edit
- delete / restore
- create folders
- manage workspace labels
- create library entries and comments

## 3. High-Level Architecture

The app uses a classic Flask app-factory structure:

```text
run.py
app/
  __init__.py
  blueprints/
  services/
  templates/
  static/
  models.py
  extensions.py
tests/
scripts/
```

The main architectural split is:

- `blueprints/`: route handlers and page/API orchestration
- `services/`: reusable business logic and asset-processing helpers
- `models.py`: SQLAlchemy models and lightweight computed properties
- `templates/`: server-rendered Jinja pages and reusable includes
- `static/js/`: client-side enhancement modules
- `static/css/`: visual system and module-specific styling

There is no separate SPA frontend and no separate API backend. Most pages are server-rendered, then enhanced by JavaScript.

## 4. Runtime Flow

### Local startup

`run.py` is the local developer entry point.

What it does:

- sets local default environment values
- creates the app via `create_app()`
- creates tables and runs local schema compatibility updates
- prompts for an admin account if none exists
- runs Flask in debug mode

Use it for local development:

```powershell
python run.py
```

### Production startup

Production currently runs the Flask app through:

- `gunicorn`
- `systemd`
- `nginx`

Current deployment convention:

- app checkout: `/srv/moments/app`
- systemd service: `moments.service`
- environment file: `/etc/moments.env`
- local app bind: `127.0.0.1:8000`
- public entry: `https://app.zhzhehua.com`

### Request lifecycle

Typical page request flow:

1. `nginx` receives the request
2. proxies to `gunicorn`
3. Flask route in a blueprint loads DB objects
4. blueprint may call services to normalize or backfill metadata/previews
5. Jinja renders HTML
6. `app/static/js/app.js` initializes page-level behaviors on `DOMContentLoaded`

## 5. Core Files and Responsibilities

### Application factory

`app/__init__.py`

Responsibilities:

- configure Flask
- set SQLite path and upload folder
- initialize extensions
- register blueprints, template filters, i18n, CLI commands, and error handlers
- create tables and run schema compatibility upgrades

Important behavior:

- `ensure_local_schema()` runs automatically at startup
- this project currently uses schema compatibility code instead of full migration discipline for many incremental changes

### Data model

`app/models.py`

This file defines the persistent model layer.

Most important models:

- `User`
- `Category`
- `Moment`
- `MomentRevision`
- `Attachment`
- `Book`
- `BookAnnotation`
- `Track`
- `TrackComment`
- `VideoEntry`
- `VideoComment`

Important relationships:

- one `Moment` has many `Attachment`s
- one `Moment` has many `MomentRevision`s
- `Moment` to `Category` is both:
  - a legacy `category_id` primary category link
  - a many-to-many relationship through `moment_folders`
- `Book`, `Track`, and `VideoEntry` each belong to a `User` and optionally a `Category`
- comments/annotations hang off their parent library entities

Important computed properties:

- `Moment.assigned_categories`
- `Moment.primary_category`
- `Attachment.preview_asset_path`
- `Attachment.poster_asset_path`
- `Book.reader_asset_path`
- `VideoEntry.preview_asset_path`

These properties are important because templates rely on them to avoid conditional sprawl.

## 6. Blueprints

### `app/blueprints/main.py`

This is the feed-centric blueprint.

Key responsibilities:

- feed page (`/`)
- folder create/delete
- workspace label updates
- language switch
- create/edit/history for moments
- recycle bin
- footprints page

Important helper functions in this file:

- `build_sidebar_context()`
- `load_feed_query()`
- `apply_search_filter()`
- `snapshot_moment()`
- `ensure_feed_media_previews()`

`build_sidebar_context()` is especially important because it centralizes the shared left-sidebar and header state used across almost every major page.

### `app/blueprints/library.py`

This blueprint owns all three library modules:

- books
- music
- videos

Responsibilities:

- list pages
- create pages/forms
- detail pages
- reader/player helpers
- edit flows
- comments/annotations
- library-specific preview preparation

### `app/blueprints/auth.py`

Small authentication blueprint:

- login
- logout

### `app/blueprints/api.py`

Small JSON API surface used by the UI:

- reverse geocode endpoint
- citation search endpoint
- moment folder updates
- soft delete
- restore

The app is not API-first. These routes exist to support interactive UI pieces, not to expose a full client API.

## 7. Service Layer

The `app/services/` directory is the real business-logic layer. If a maintainer wants to understand behavior without reading templates, this is the place to start.

### `storage.py`

Responsibilities:

- validate uploads by extension
- normalize original filenames
- save uploaded files under `app/static/uploads/YYYY/MM/`
- compute mime type, media kind, relative paths, and size
- remove managed files when needed

Important note:

- `save_upload()` stores the uploaded file itself
- higher-level services are responsible for generating derivative assets such as previews or posters

### `image_previews.py`

Responsibilities:

- optimize uploaded images
- generate smaller preview assets for feed rendering
- backfill image previews for older attachments

Current behavior:

- uploaded images are optimized and, when possible, resized/compressed
- feed image tiles use preview assets instead of the raw original
- older image attachments get previews generated lazily when encountered in feed rendering

This service exists primarily because raw phone images were large enough to hurt scroll performance.

### `video_previews.py`

Responsibilities:

- detect problematic video codecs such as HEVC in `.mov`
- generate browser-friendly MP4 previews when needed
- generate poster frames for preview and library display

This service is used both by:

- feed attachments
- video library entries

### `folders.py`

Responsibilities:

- normalize folder input
- resolve selected folder IDs
- serialize folder snapshots
- build nested folder trees
- flatten trees for form selects
- calculate counts across descendants

This is the core of the "structure" experience.

### `footprints.py`

Responsibilities:

- normalize place fields
- infer metadata from loose location labels
- build place keys
- aggregate moments by city/country
- serialize footprint payloads for the map UI

Important design choice:

- the map payload is pre-aggregated server-side
- the frontend mostly renders and filters the payload, rather than building all grouping logic in JavaScript

### `geocoding.py`

Responsibilities:

- reverse geocode latitude/longitude into structured place information

This is used by the composer and footprints maintenance logic.

### `citations.py`

Responsibilities:

- search books, tracks, videos, and their notes/comments
- serialize citation results
- resolve a saved citation payload for a moment

This is what lets a moment cite:

- a book
- a highlighted book note
- a track
- a track comment
- a video
- a video note

### `books.py`

Responsibilities:

- normalize book uploads
- extract book identity metadata
- create reader-ready assets
- extract EPUB cover and section structure
- build rendered HTML reader fragments

This service is the core of the book-reader implementation.

### `library.py`

Responsibilities:

- library-specific parsing helpers
- timestamp parsing and formatting
- text asset reading
- audio/video extension sets

### `schema.py`

Responsibilities:

- perform additive local schema upgrades for SQLite
- create missing columns/indexes
- backfill certain compatibility structures

This file is extremely important operationally. It is why the app can often keep running through iterative schema changes without a formal migration step during local/early-stage development.

## 8. Template Architecture

### Base shell

`app/templates/base.html`

This file composes the shared app frame:

- sidebar
- app header
- flash messages
- page content block
- composer modal
- media viewer
- global audio player

The page structure is:

- sidebar on the left
- header/top quick navigation on the right frame
- main content panel under the header

### Reusable includes

Most UI consistency comes from the `templates/includes/` directory:

- `sidebar.html`: primary navigation, filters, folder tools, workspace panel
- `app_header.html`: top quick-nav and compact language switcher
- `composer_modal.html`: admin publishing UI
- `feed_list.html`: moment stream section
- `moment_card.html`: one feed card
- `moment_media_cluster.html`: image/video/document rendering inside a moment
- `media_viewer.html`: immersive image/video viewer
- `global_audio_player.html`: site-level music player

### Page templates

Main page templates:

- `index.html`
- `books.html`
- `book_detail.html`
- `book_reader.html`
- `tracks.html`
- `track_detail.html`
- `videos.html`
- `video_detail.html`
- `footprints.html`
- `edit_moment.html`
- `moment_history.html`
- `recycle_bin.html`
- `login.html`

## 9. Frontend JavaScript

The frontend entry point is:

- `app/static/js/app.js`

On page load it initializes:

- navigation
- composer modal
- media viewer
- moment menus
- feed interactions
- library features
- footprints map
- location binding on forms

Main modules:

- `composer.js`: publishing modal, attachment handling, citation search wiring
- `feed.js`: feed-specific interactions
- `media-viewer.js`: immersive preview overlay
- `navigation.js`: sidebar, header interactions, panels, language switcher
- `geolocation.js`: browser geolocation + reverse-geocode form binding
- `library.js`: book/music/video module interactions
- `footprints.js`: Leaflet-based footprints rendering, view/filter/sort/open mode handling

## 10. CSS Organization

The main stylesheet entry is:

- `app/static/css/style.css`

It imports module files such as:

- `foundation.css`
- `layout.css`
- `components.css`
- `feed.css`
- `forms.css`
- `library.css`
- `maps.css`
- `modal.css`
- `responsive.css`
- `i18n-layout.css`

Rough responsibility split:

- `foundation.css`: tokens and base timing/shadow variables
- `layout.css`: frame, header, sidebar, shared shell
- `components.css`: cards, buttons, shared UI primitives
- `feed.css`: moment cards and feed media
- `library.css`: books/music/videos presentation
- `maps.css`: footprints page
- `modal.css`: immersive media viewer and overlays
- `i18n-layout.css`: Chinese-specific spacing/layout fixes

## 11. Media Pipeline

This is one of the most important parts of the app.

### Feed attachment upload flow

When an admin posts a moment with files:

1. `main.create_moment()` receives `request.files`
2. each file goes through `save_upload()` in `storage.py`
3. an `Attachment` row is created
4. if it is an image:
   - `image_previews.py` may optimize the original
   - generates a preview asset for feed rendering
5. if it is a video:
   - `video_previews.py` may generate a browser-safe MP4 preview
   - generates a poster frame
6. attachment metadata is committed to SQLite

### Feed render flow

When the feed renders:

1. moments are loaded with attachments
2. `ensure_feed_media_previews()` may lazily backfill missing previews for older assets
3. `moment_media_cluster.html` uses `attachment.preview_asset_path`
4. the immersive media viewer opens the preview asset rather than always the raw original

### Library media flow

Books, music, and videos each have their own upload logic, but the same pattern appears repeatedly:

- store original source file
- generate derivative asset only when useful
- keep derivative path in the database
- render derivatives by default in browsing surfaces

## 12. Data and Storage Layout

### Database

Local and production SQLite database:

- `instance/app.db`

This file must be preserved across deployments.

### Uploads

All uploaded and generated assets live under:

- `app/static/uploads/`

Subdirectory pattern:

- `uploads/YYYY/MM/...`

This directory contains both:

- original uploads
- generated derivatives such as image previews, video previews, posters, generated readers, and covers

This directory must also be preserved across deployments.

## 13. Search Behavior

Feed search currently matches:

- moment text
- location label
- citation title/subtitle/excerpt
- attachment original filenames
- folder name
- folder description

Search is intentionally cross-cutting. It is not limited to full-text content.

## 14. Edit History and Recycle Bin

### Revisions

When an admin edits a moment:

- the old version is snapshotted into `MomentRevision`
- content, location, and folder snapshot are preserved
- history is visible on a dedicated revision page

### Delete behavior

Deletion is soft delete first:

- `Moment.is_deleted = True`
- `Moment.deleted_at` is set

Restore is possible from the recycle bin.

Permanent removal is done through CLI:

```powershell
python -m flask --app run.py purge-recycle-bin --days 30
```

This command also deletes managed attachment files for purged moments.

## 15. Footprints Map Design

The footprints module is intentionally not a raw post map.

Current design:

- city and country views are supported
- country view can show visited vs unvisited countries
- same-place moments are grouped
- detail content can open as timeline, cards, or popup-style views

The country overlay uses a local static asset:

- `app/static/data/world-countries.geojson`

This avoids requiring a third-party map polygon API just to color visited countries.

## 16. Local Development Guide

### Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### Start the app locally

```powershell
python run.py
```

On first launch:

- tables are created
- local schema compatibility updates run
- you are prompted to create an admin if none exists

### Reset admin

```powershell
python run.py --reset-admin
```

### Run tests

```powershell
python -m pytest -q
```

## 17. Production Deployment and Update Flow

### Current production stack

- Ubuntu 24.04
- `nginx`
- `gunicorn`
- `systemd`
- SQLite
- static uploads served from the app checkout

### Important production paths

- app checkout: `/srv/moments/app`
- persistent DB: `/srv/moments/app/instance/app.db`
- persistent uploads: `/srv/moments/app/app/static/uploads/`
- environment file: `/etc/moments.env`
- service file: `/etc/systemd/system/moments.service`

### One-command server update

```bash
cd /srv/moments/app
bash scripts/update-production.sh
```

What the script does:

- fetch latest code from GitHub
- fast-forward pull `origin/main`
- install/update dependencies in `.venv`
- restart `moments.service`
- run a health check

### Current operational note

The app uses SQLite, so production is intentionally conservative:

- a single gunicorn worker is preferred for stability
- the update script now waits before health checking because the app may need a moment after restart

### If Git warns about repository ownership

If updates are run as `root` but the repo is owned by another user, Git may require:

```bash
git config --global --add safe.directory /srv/moments/app
```

This is a one-time trust configuration, not an app bug.

## 18. Recommended Daily Maintenance Workflow

### Local code change

1. edit files in VS Code
2. review changes in GitHub Desktop
3. `Commit to main`
4. `Push origin`

### Server deployment

1. SSH into the server
2. run:

```bash
cd /srv/moments/app
bash scripts/update-production.sh
```

### Success signal

If the script ends with a healthy local HTTP response, the update is good.

## 19. Important Constraints and Tradeoffs

Maintainers should know these before making architectural changes:

- SQLite is simple and good for this scale, but it is not a high-concurrency choice
- schema evolution currently leans on additive compatibility logic in `schema.py`
- many page interactions are server-rendered first, JavaScript-enhanced second
- media storage is filesystem-based, not object-storage-based
- map aggregation is server-side by design
- some first-load preview backfills may happen during page requests

These tradeoffs are acceptable for the current scope, but they shape how new features should be added.

## 20. Common Pitfalls

### 1. Losing persistent data during deployment

Do not overwrite these casually:

- `instance/app.db`
- `app/static/uploads/`

### 2. Serving raw large images in the feed

This hurts scroll performance quickly. Feed code should prefer preview assets, not originals.

### 3. Reintroducing aggressive video preload

Inline video convenience is helpful, but excessive eager loading will make the feed feel heavy.

### 4. Forgetting schema compatibility

If you add columns or indexes, update `app/services/schema.py` unless you are also introducing a cleaner migration process.

### 5. Treating folders as simple tags

Folder behavior is more structural than tag-like. Count logic, tree rendering, and deletion semantics all assume hierarchy matters.

## 21. Suggested Reading Order for New Maintainers

If someone is new to the codebase, the fastest orientation path is:

1. `app/__init__.py`
2. `app/models.py`
3. `app/blueprints/main.py`
4. `app/templates/base.html`
5. `app/templates/includes/sidebar.html`
6. `app/templates/includes/moment_card.html`
7. `app/templates/includes/moment_media_cluster.html`
8. `app/blueprints/library.py`
9. `app/services/storage.py`
10. `app/services/image_previews.py`
11. `app/services/video_previews.py`
12. `app/services/footprints.py`
13. `app/static/js/app.js`
14. `tests/test_main.py`

That order gives a good balance of:

- runtime setup
- persistence model
- feed flow
- UI composition
- media pipeline
- library features
- tests as executable documentation

## 22. Repository

GitHub:

- [ZhehuaZhu/moments-library](https://github.com/ZhehuaZhu/moments-library)

## 23. Status

The project is currently a medium-sized personal archive application, not a prototype. It already includes:

- multiple content modules
- media preview pipelines
- structured location data
- revision history
- recycle-bin safety
- test coverage around the core flows

Future maintainers should treat it as a real product with a clear interaction model, not as a disposable demo.
