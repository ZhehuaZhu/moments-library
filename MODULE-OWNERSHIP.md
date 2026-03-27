# Module Ownership

This file defines which files each module should usually own.

The purpose is not to forbid all shared-file edits.  
The purpose is to make it obvious when a change is becoming cross-module and risky.

## 1. Feed / Moments

Primary workspace:

- `CODE-moments`

Usually owned files:

- `app/templates/index.html`
- `app/templates/edit_moment.html`
- `app/templates/moment_history.html`
- `app/templates/recycle_bin.html`
- `app/templates/includes/composer_modal.html`
- `app/templates/includes/moment_card.html`
- `app/templates/includes/moment_action_menu.html`
- `app/static/js/modules/composer.js`
- `app/static/js/modules/composer-file-controller.js`
- `app/static/js/modules/composer-file-utils.js`
- `app/static/js/modules/composer-citation-controller.js`
- `app/static/js/modules/composer-cross-post-controller.js`
- `app/static/js/modules/feed.js`
- `app/static/js/modules/moment-menu.js`
- `app/static/css/modules/feed.css`
- `app/static/css/modules/forms.css`

## 2. Footprints

Primary workspace:

- `CODE`

Usually owned files:

- `app/templates/footprints.html`
- `app/static/js/modules/footprints.js`
- `app/static/css/modules/maps.css`
- `app/services/footprints.py`

## 3. Books

Primary workspace:

- `CODE-books`

Usually owned files:

- `app/templates/books.html`
- `app/templates/book_detail.html`
- `app/templates/book_reader.html`
- book-specific sections inside `app/static/css/modules/library.css`
- book-specific sections inside `app/static/js/modules/library.js`
- book-specific routes in `app/blueprints/library.py`

## 4. Music

Primary workspace:

- `CODE-music`

Usually owned files:

- `app/templates/tracks.html`
- `app/templates/track_detail.html`
- `app/templates/includes/global_audio_player.html`
- `app/templates/music_player_window.html`
- music/player-specific sections inside `app/static/css/modules/library.css`
- music/player-specific sections inside `app/static/js/modules/library.js`
- `app/static/js/modules/library-player-utils.js`
- music-specific routes in `app/blueprints/library.py`

## 5. Videos

Primary workspace:

- `CODE-videos`

Usually owned files:

- `app/templates/videos.html`
- `app/templates/video_detail.html`
- video-specific sections inside `app/static/css/modules/library.css`
- video-specific sections inside `app/static/js/modules/library.js`
- `app/static/js/modules/library-video-previews.js`
- video-specific routes in `app/blueprints/library.py`

## 6. Mobile Polish

Primary workspace:

- `CODE-mobile-polish`

Usually owned files:

- `app/static/css/modules/responsive.css`
- mobile-only sections across templates and module CSS files

Important note:

- this branch should focus on mobile UX polish, not unrelated business logic

## 7. Refactor / Structure

Primary workspace:

- `CODE-refactor-low-conflict`

Usually owned files:

- `app/static/js/app.js`
- `app/static/js/modules/app-bootstrap.js`
- shared JS module splits
- shared CSS file splits
- structural improvements that reduce merge conflicts

## 8. Shared High-Risk Files

These files are cross-module hotspots.

Touch them carefully:

- `app/blueprints/main.py`
- `app/blueprints/library.py`
- `app/blueprints/api.py`
- `app/models.py`
- `app/services/i18n.py`
- `app/services/schema.py`
- `app/templates/base.html`
- `app/templates/includes/app_header.html`
- `app/static/css/modules/components.css`
- `app/static/css/modules/layout.css`
- `app/static/css/modules/responsive.css`
- `app/static/css/modules/library.css`
- `app/static/js/modules/library.js`

If you change one of these, assume the task is cross-module until proven otherwise.

## 9. Practical Rule

Before editing a file, ask:

1. Does this file clearly belong to one module?
2. If not, is this really a shared change?

If the answer is "this is shared", prefer:

- `CODE-preview` for integration-level work, or
- a short-lived feature branch created from the latest preview baseline
