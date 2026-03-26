from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from io import BytesIO

from ebooklib import epub
from PIL import Image

from app.extensions import db
from app.models import (
    Attachment,
    Book,
    BookAnnotation,
    Category,
    Moment,
    MomentRevision,
    Track,
    TrackComment,
    User,
    VideoComment,
    VideoEntry,
)
from app.services.folders import serialize_folder_snapshot
from app.services.image_previews import ensure_attachment_image_preview
from app.services.storage import resolve_storage_path


def build_epub_bytes(title: str, chapter_title: str, body_text: str) -> bytes:
    book = epub.EpubBook()
    book.set_identifier(f"{title}-id")
    book.set_title(title)
    book.set_language("zh")

    chapter = epub.EpubHtml(title=chapter_title, file_name="chapter-1.xhtml", lang="zh")
    chapter.content = f"<h1>{chapter_title}</h1><p>{body_text}</p>"

    book.add_item(chapter)
    book.toc = (epub.Link("chapter-1.xhtml", chapter_title, "chapter-1"),)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    output = BytesIO()
    epub.write_epub(output, book)
    return output.getvalue()


def build_epub_with_front_matter_bytes(title: str) -> bytes:
    book = epub.EpubBook()
    book.set_identifier(f"{title}-front-matter-id")
    book.set_title(title)
    book.set_language("en")

    copyright_page = epub.EpubHtml(title="Copyright", file_name="copyright.xhtml", lang="en")
    copyright_page.content = "<h1>Copyright</h1><p>All rights reserved.</p>"

    contents_page = epub.EpubHtml(title="Contents", file_name="contents.xhtml", lang="en")
    contents_page.content = "<h1>Contents</h1><p>1. First Night</p>"

    chapter = epub.EpubHtml(title="First Night", file_name="chapter-1.xhtml", lang="en")
    chapter.content = "<h1>First Night</h1><p>The real story starts here.</p>"

    book.add_item(copyright_page)
    book.add_item(contents_page)
    book.add_item(chapter)
    book.toc = (
        epub.Link("copyright.xhtml", "Copyright", "copyright"),
        epub.Link("contents.xhtml", "Contents", "contents"),
        epub.Link("chapter-1.xhtml", "First Night", "chapter-1"),
    )
    book.spine = ["nav", copyright_page, contents_page, chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    output = BytesIO()
    epub.write_epub(output, book)
    return output.getvalue()


def build_photo_bytes(size: tuple[int, int] = (2400, 1600)) -> bytes:
    image = Image.effect_noise(size, 96).convert("RGB")
    output = BytesIO()
    image.save(output, format="JPEG", quality=96)
    return output.getvalue()


def test_guest_cannot_access_recycle_bin(client):
    response = client.get("/recycle-bin", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_admin_can_create_moment_with_structured_place_fields(admin_client, app):
    response = admin_client.post(
        "/moments",
        data={
            "content": "Pinned to the map.",
            "location_label": "巴登-符腾堡 曼海姆 Innenstadt/Jungbusch Bismarckstraße",
            "latitude": "49.48313",
            "longitude": "8.46133",
            "location_country_code": "DE",
            "location_country_name": "Germany",
            "location_admin_area": "巴登-符腾堡",
            "location_city_name": "曼海姆",
            "location_district_name": "Innenstadt/Jungbusch",
            "location_place_key": "mannheim-key",
            "location_source": "browser",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Moment published." in response.data

    with app.app_context():
        moment = Moment.query.filter_by(content="Pinned to the map.").one()
        assert moment.country_code == "DE"
        assert moment.country_name == "Germany"
        assert moment.admin_area == "巴登-符腾堡"
        assert moment.city_name == "曼海姆"
        assert moment.district_name == "Innenstadt/Jungbusch"
        assert moment.place_key == "mannheim-key"
        assert moment.location_source == "browser"


def test_geocode_api_returns_structured_place_fields(admin_client, monkeypatch):
    def fake_reverse_geocode(lat, lon, user_agent):
        assert lat == 49.5
        assert lon == 8.4
        return {
            "formatted_address": "巴登-符腾堡 曼海姆 Innenstadt/Jungbusch Bismarckstraße",
            "country": "Germany",
            "country_code": "DE",
            "province": "巴登-符腾堡",
            "city": "曼海姆",
            "district": "Innenstadt/Jungbusch",
            "road": "Bismarckstraße",
            "latitude": lat,
            "longitude": lon,
        }

    monkeypatch.setattr("app.blueprints.api.reverse_geocode", fake_reverse_geocode)

    response = admin_client.post("/api/geocode", json={"lat": 49.5, "lon": 8.4})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["country"] == "Germany"
    assert payload["country_code"] == "DE"
    assert payload["city"] == "曼海姆"
    assert payload["place_key"]
    assert payload["location_source"] == "browser"


def test_footprints_page_groups_moments_by_place(admin_client, app):
    with app.app_context():
        author = User.query.filter_by(username="admin").one()
        first = Moment(
            content="Morning light.",
            author_id=author.id,
            location_label="巴登-符腾堡 曼海姆 Innenstadt/Jungbusch Bismarckstraße",
            latitude=49.48313,
            longitude=8.46133,
            country_code="DE",
            country_name="Germany",
            admin_area="巴登-符腾堡",
            city_name="曼海姆",
            district_name="Innenstadt/Jungbusch",
            place_key="mannheim-key",
            location_source="browser",
        )
        second = Moment(
            content="Second pin in the same city.",
            author_id=author.id,
            location_label="巴登-符腾堡 曼海姆 Innenstadt/Jungbusch Paradeplatz",
            latitude=49.48700,
            longitude=8.46600,
            country_code="DE",
            country_name="Germany",
            admin_area="巴登-符腾堡",
            city_name="曼海姆",
            district_name="Innenstadt/Jungbusch",
            place_key="mannheim-key",
            location_source="browser",
        )
        third = Moment(
            content="Another city.",
            author_id=author.id,
            location_label="黑森 法兰克福 Innenstadt Zeil",
            latitude=50.1109,
            longitude=8.6821,
            country_code="DE",
            country_name="Germany",
            admin_area="黑森",
            city_name="法兰克福",
            district_name="Innenstadt",
            place_key="frankfurt-key",
            location_source="browser",
        )
        fourth = Moment(
            content="Across the border.",
            author_id=author.id,
            location_label="Paris France",
            latitude=48.8566,
            longitude=2.3522,
            country_code="FR",
            country_name="France",
            admin_area="Ile-de-France",
            city_name="Paris",
            district_name="1st arrondissement",
            place_key="paris-key",
            location_source="browser",
        )
        db.session.add_all([first, second, third, fourth])
        db.session.commit()

    response = admin_client.get("/footprints")
    assert response.status_code == 200
    assert b"data-footprints-shell" in response.data
    assert b"data-footprints-view" in response.data
    assert b"data-footprints-filter" in response.data
    assert b"data-footprints-visit-mode" in response.data
    assert b"data-footprints-sort" in response.data
    assert b"data-footprints-display-mode" in response.data
    assert b"data-footprints-open-mode" in response.data
    assert b"vendor/leaflet/leaflet.css" in response.data
    assert b"world-countries.geojson" in response.data
    assert b'"default_view": "city"' in response.data
    assert b'"place_count": 3' in response.data
    assert b'"place_count": 2' in response.data
    assert b'"moment_count": 2' in response.data
    assert b"Countries" in response.data
    assert b"Visited / unvisited" in response.data
    assert b"Timeline" in response.data
    assert b"Map popup" in response.data
    assert b"/footprints" in response.data


def test_footprints_country_overlay_asset_is_served(client):
    response = client.get("/static/data/world-countries.geojson")
    assert response.status_code == 200
    assert b'"type":"FeatureCollection"' in response.data[:128]


def test_admin_can_create_nested_folder_with_description(admin_client, app):
    with app.app_context():
        parent = Category(name="Library")
        db.session.add(parent)
        db.session.commit()
        parent_id = parent.id

    response = admin_client.post(
        "/categories",
        data={
            "name": "Research Notes",
            "description": "Long-term reading and papers.",
            "parent_id": str(parent_id),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Collection created." in response.data

    with app.app_context():
        folder = Category.query.filter_by(name="Research Notes").one()
        assert folder.description == "Long-term reading and papers."
        assert folder.parent_id == parent_id


def test_admin_feed_includes_composer_preview_workspace(admin_client):
    response = admin_client.get("/")
    assert response.status_code == 200
    assert b"data-composer-preview" in response.data
    assert b"data-composer-file-list" in response.data
    assert b"data-library-input" in response.data
    assert b"data-camera-input" in response.data
    assert b'capture="environment"' in response.data
    assert b"data-mobile-compose" in response.data
    assert b"Attachment Order" in response.data
    assert b"data-citation-toggle" in response.data
    assert b"data-citation-search" in response.data
    assert b"data-citation-results" in response.data
    assert b"vendor/mammoth.browser.min.js" not in response.data
    assert b"vendor/epub.min.js" not in response.data
    assert b"Add Citation" in response.data
    assert b"Choose Existing Media" in response.data
    assert b"Take Photo / Video" in response.data
    assert b"Cross-Post Assistant" in response.data
    assert b'name="cross_post_targets"' in response.data
    assert b"WeChat Moments" in response.data


def test_admin_feed_moment_menu_includes_share_choices(admin_client):
    create_response = admin_client.post(
        "/moments",
        data={
            "content": "Share from the overflow menu.",
            "files": (BytesIO(build_photo_bytes()), "share-menu.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert create_response.status_code == 200

    response = admin_client.get("/")
    assert response.status_code == 200
    assert b"data-toggle-share-platforms" in response.data
    assert b"Share To" in response.data
    assert b"Placeholder only for now" in response.data
    assert b"WeChat Moments" in response.data
    assert b"Instagram" in response.data
    assert b"Xiaohongshu" in response.data


def test_admin_can_prepare_cross_post_targets_for_moment(admin_client, app):
    response = admin_client.post(
        "/moments",
        data={
            "content": "Ready for other channels.",
            "cross_post_targets": ["wechat_moments", "instagram", "xiaohongshu"],
            "files": (BytesIO(build_photo_bytes()), "sunrise.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Moment published." in response.data
    assert b"Copy Caption" in response.data
    assert b"Mark Published" in response.data

    with app.app_context():
        moment = Moment.query.filter_by(content="Ready for other channels.").one()
        payload = json.loads(moment.cross_post_targets)
        assert payload["wechat_moments"]["selected"] is True
        assert payload["instagram"]["selected"] is True
        assert payload["xiaohongshu"]["selected"] is True


def test_cross_post_rules_block_instagram_for_text_only_moment(admin_client):
    response = admin_client.post(
        "/moments",
        data={
            "content": "Text only moment.",
            "cross_post_targets": "instagram",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Instagram" in response.data
    assert b"Blocked" in response.data
    assert b"This channel needs at least one image or video." in response.data


def test_admin_can_mark_and_reset_cross_post_publication(admin_client, app):
    create_response = admin_client.post(
        "/moments",
        data={
            "content": "Mark this as published elsewhere.",
            "cross_post_targets": ["instagram"],
            "files": (BytesIO(build_photo_bytes()), "publish.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert create_response.status_code == 200

    with app.app_context():
        moment = Moment.query.filter_by(content="Mark this as published elsewhere.").one()
        moment_id = moment.id

    publish_response = admin_client.post(
        f"/api/moments/{moment_id}/cross-post/instagram",
        json={"action": "publish"},
    )
    assert publish_response.status_code == 200

    with app.app_context():
        moment = db.session.get(Moment, moment_id)
        payload = json.loads(moment.cross_post_targets)
        assert payload["instagram"]["published_at"]

    reset_response = admin_client.post(
        f"/api/moments/{moment_id}/cross-post/instagram",
        json={"action": "reset"},
    )
    assert reset_response.status_code == 200

    with app.app_context():
        moment = db.session.get(Moment, moment_id)
        payload = json.loads(moment.cross_post_targets)
        assert payload["instagram"]["published_at"] is None


def test_admin_can_create_book_and_open_reader(admin_client, app):
    with app.app_context():
        folder = Category(name="Reading Shelf")
        db.session.add(folder)
        db.session.commit()
        folder_id = folder.id

    response = admin_client.post(
        "/books",
        data={
            "title": "Draft Novel",
            "author_name": "Zhehua",
            "status": "finished",
            "category_id": str(folder_id),
            "started_at": "2026-03-01",
            "finished_at": "2026-03-24",
            "overall_review": "A reflective first full pass.",
            "source_file": (BytesIO(b"First paragraph.\n\nSecond paragraph."), "novel.txt"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Book added to the library." in response.data
    assert b"Draft Novel" in response.data

    with app.app_context():
        book = Book.query.one()
        assert book.status == "finished"
        assert book.category.name == "Reading Shelf"
        book_id = book.id

    reader_response = admin_client.get(f"/books/{book_id}/reader")
    assert reader_response.status_code == 200
    assert b"First paragraph." in reader_response.data
    assert b"data-reader-shell" in reader_response.data
    assert b"data-reader-toggle-top" in reader_response.data
    assert b"data-reader-toggle-bottom" in reader_response.data
    assert b"data-book-selection-source" in reader_response.data
    assert b"reader-notes-drawer" in reader_response.data
    assert b"Reader modules" not in reader_response.data
    assert b'class="page-header"' not in reader_response.data


def test_books_page_uses_bookshelf_layout_and_cover_upload(admin_client, app):
    response = admin_client.get("/books")
    assert response.status_code == 200
    assert b"bookshelf-grid" in response.data
    assert b'name="cover_file"' in response.data
    assert b'data-open-folder-panel="book-create"' in response.data
    assert b'id="book-create-panel"' in response.data
    assert b'data-open-folder-panel="create"' in response.data
    assert b"Optional if the file already has a title" in response.data

    create_response = admin_client.post(
        "/books",
        data={
            "title": "Shelf Test",
            "status": "reading",
            "source_file": (BytesIO(b"Plain shelf text"), "shelf-test.txt"),
            "cover_file": (BytesIO(b"fake cover"), "cover.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert create_response.status_code == 200

    with app.app_context():
        book = Book.query.filter_by(title="Shelf Test").one()
        assert book.cover_relative_path is not None


def test_book_upload_can_infer_title_and_reader_marks_started(admin_client, app):
    response = admin_client.post(
        "/books",
        data={
            "title": "",
            "status": "want_to_read",
            "source_file": (BytesIO(b"Plain shelf text"), "quiet-atlas-notes.txt"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"quiet atlas notes" in response.data

    with app.app_context():
        book = Book.query.filter_by(original_name="quiet-atlas-notes.txt").one()
        book_id = book.id
        assert book.title == "quiet atlas notes"
        assert book.started_at is None
        assert book.status == "want_to_read"

    reader_response = admin_client.get(f"/books/{book_id}/reader")
    assert reader_response.status_code == 200

    with app.app_context():
        book = db.session.get(Book, book_id)
        assert book.started_at == date.today()
        assert book.status == "reading"


def test_admin_can_edit_book_metadata_and_cover(admin_client, app):
    with app.app_context():
        category = Category(name="Edited Shelf")
        db.session.add(category)
        db.session.commit()
        category_id = category.id

    create_response = admin_client.post(
        "/books",
        data={
            "title": "Before Edit",
            "status": "want_to_read",
            "source_file": (BytesIO(b"Plain shelf text"), "before-edit.txt"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert create_response.status_code == 200

    with app.app_context():
        book = Book.query.filter_by(title="Before Edit").one()
        book_id = book.id

    update_response = admin_client.post(
        f"/books/{book_id}/edit",
        data={
            "title": "After Edit",
            "author_name": "Edited Author",
            "status": "finished",
            "category_id": str(category_id),
            "started_at": "2026-03-01",
            "finished_at": "2026-03-08",
            "description": "A cleaner shelf record.",
            "overall_review": "Now editable from the side panel.",
            "cover_file": (BytesIO(b"new cover"), "edited-cover.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert update_response.status_code == 200
    assert b"Book updated." in update_response.data
    assert b"After Edit" in update_response.data

    with app.app_context():
        book = db.session.get(Book, book_id)
        assert book.title == "After Edit"
        assert book.author_name == "Edited Author"
        assert book.status == "finished"
        assert book.category.name == "Edited Shelf"
        assert str(book.started_at) == "2026-03-01"
        assert str(book.finished_at) == "2026-03-08"
        assert book.cover_relative_path is not None


def test_admin_can_create_epub_book_and_open_epub_reader(admin_client, app):
    response = admin_client.post(
        "/books",
        data={
            "title": "EPUB Draft",
            "status": "reading",
            "source_file": (
                BytesIO(build_epub_bytes("EPUB Draft", "First Night", "A quick EPUB chapter.")),
                "draft.epub",
            ),
            "cover_file": (BytesIO(b"fake cover"), "draft-cover.png"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Book added to the library." in response.data

    with app.app_context():
        book = Book.query.filter_by(title="EPUB Draft").one()
        assert book.cover_relative_path is not None
        assert book.reader_format == "html"
        assert book.reader_relative_path is not None
        book_id = book.id

    reader_response = admin_client.get(f"/books/{book_id}/reader")
    assert reader_response.status_code == 200
    assert b"data-reader-shell" in reader_response.data
    assert b"data-section-reader" in reader_response.data
    assert b"reader-notes-drawer" in reader_response.data
    assert b'href="/books"' in reader_response.data
    assert b"data-reader-open-notes" in reader_response.data
    assert b"Reader modules" not in reader_response.data
    assert b'class="page-header"' not in reader_response.data
    assert b'data-section-initial-index="1"' in reader_response.data
    assert b"First Night" in reader_response.data
    assert reader_response.data.count(b"book-reader-section") == 2

    section_response = admin_client.get(f"/books/{book_id}/reader/section?index=1")
    assert section_response.status_code == 200
    payload = section_response.get_json()
    assert payload["number"] == 2
    assert "First Night" in payload["label"]


def test_html_reader_skips_front_matter_by_default(admin_client, app):
    response = admin_client.post(
        "/books",
        data={
            "title": "Front Matter Draft",
            "status": "reading",
            "source_file": (
                BytesIO(build_epub_with_front_matter_bytes("Front Matter Draft")),
                "front-matter.epub",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        book = Book.query.filter_by(title="Front Matter Draft").one()
        book_id = book.id

    reader_response = admin_client.get(f"/books/{book_id}/reader")
    assert reader_response.status_code == 200
    assert b'data-section-initial-index="3"' in reader_response.data
    assert b'"is_front_matter": true' in reader_response.data
    assert b"First Night" in reader_response.data
    assert b"(Front matter)" in reader_response.data


def test_html_reader_resumes_from_saved_progress(admin_client, app):
    response = admin_client.post(
        "/books",
        data={
            "title": "Resume Draft",
            "status": "reading",
            "source_file": (
                BytesIO(build_epub_with_front_matter_bytes("Resume Draft")),
                "resume.epub",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        book = Book.query.filter_by(title="Resume Draft").one()
        book_id = book.id

    progress_response = admin_client.post(
        f"/books/{book_id}/reader/progress",
        data=json.dumps({"section_index": 1, "scroll_ratio": 0.35}),
        content_type="application/json",
    )
    assert progress_response.status_code == 200
    assert progress_response.get_json()["ok"] is True

    with app.app_context():
        book = db.session.get(Book, book_id)
        assert book.last_read_section_index == 1
        assert book.last_read_scroll_ratio == 0.35
        assert book.last_read_at is not None

    reader_response = admin_client.get(f"/books/{book_id}/reader")
    assert reader_response.status_code == 200
    assert b'data-section-initial-index="1"' in reader_response.data
    assert b'data-reader-resume-scroll-ratio="0.350000"' in reader_response.data
    assert b'data-reader-progress-endpoint="/books/' in reader_response.data


def test_html_reader_annotation_persists_precise_anchor(admin_client, app):
    response = admin_client.post(
        "/books",
        data={
            "title": "Anchored EPUB",
            "status": "reading",
            "source_file": (
                BytesIO(build_epub_bytes("Anchored EPUB", "First Night", "A quick EPUB chapter.")),
                "anchored.epub",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        book = Book.query.filter_by(title="Anchored EPUB").one()
        book_id = book.id

    note_response = admin_client.post(
        f"/books/{book_id}/annotations",
        data={
            "next": f"/books/{book_id}/reader?section=1",
            "annotation_type": "text_anchor",
            "chapter_label": "First Night",
            "quoted_text": "quick EPUB",
            "comment": "Save this as a precise highlight.",
            "section_index": "0",
            "paragraph_id": "reader-section-1-p-1",
            "selection_start": "2",
            "selection_end": "12",
        },
        follow_redirects=True,
    )

    assert note_response.status_code == 200
    assert b"Reading note saved." in note_response.data

    with app.app_context():
        note = BookAnnotation.query.one()
        assert note.annotation_type == "text_anchor"
        assert note.section_index == 0
        assert note.paragraph_id == "reader-section-1-p-1"
        assert note.selection_start == 2
        assert note.selection_end == 12
        assert note.has_text_anchor is True
        note_id = note.id

    detail_response = admin_client.get(f"/books/{book_id}")
    assert detail_response.status_code == 200
    assert f"/books/{book_id}/reader?section=1&amp;annotation={note_id}".encode() in detail_response.data

    reader_response = admin_client.get(f"/books/{book_id}/reader?section=1&annotation={note_id}")
    assert reader_response.status_code == 200
    assert f'data-reader-focus-annotation-id="{note_id}"'.encode() in reader_response.data
    assert b"data-reader-annotations" in reader_response.data
    assert b"reader-section-1-p-1" in reader_response.data
    assert b"Precise Highlight" in reader_response.data


def test_admin_can_create_track_and_comment(admin_client, app):
    response = admin_client.post(
        "/music",
        data={
            "title": "Night Theme",
            "artist_name": "Zhehua",
            "mood": "Reflective",
            "overall_review": "The chorus finally feels balanced.",
            "audio_file": (BytesIO(b"fake audio"), "night-theme.mp3"),
            "cover_file": (BytesIO(b"fake cover"), "night-theme-cover.jpg"),
            "lyrics_file": (
                BytesIO(
                    b"[00:00.00]Intro line\n[01:24.50]The vocal texture opens up here."
                ),
                "night-theme.lrc",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Track added to the music library." in response.data
    assert b"data-lyrics-shell" in response.data
    assert b"Intro line" in response.data

    with app.app_context():
        track = Track.query.one()
        track_id = track.id
        assert track.has_lyrics is True
        assert track.lyrics_relative_path is not None
        assert track.cover_relative_path is not None

    comment_response = admin_client.post(
        f"/music/{track_id}/comments",
        data={"timestamp_seconds": "01:24", "comment": "The vocal texture opens up here."},
        follow_redirects=True,
    )
    assert comment_response.status_code == 200
    assert b"Track comment saved." in comment_response.data
    assert b"01:24" in comment_response.data
    assert b"The vocal texture opens up here." in comment_response.data


def test_admin_can_create_flac_track(admin_client, app):
    response = admin_client.post(
        "/music",
        data={
            "title": "Lossless Draft",
            "artist_name": "Zhehua",
            "audio_file": (BytesIO(b"fake flac"), "lossless-draft.flac"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Track added to the music library." in response.data
    assert b"Lossless Draft" in response.data

    with app.app_context():
        track = Track.query.filter_by(title="Lossless Draft").one()
        assert track.original_name.endswith(".flac")


def test_admin_can_edit_track_metadata_and_cover(admin_client, app):
    create_response = admin_client.post(
        "/music",
        data={
            "title": "Edit Me",
            "artist_name": "Before",
            "audio_file": (BytesIO(b"fake audio"), "edit-me.mp3"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert create_response.status_code == 200

    with app.app_context():
        track = Track.query.filter_by(title="Edit Me").one()
        track_id = track.id

    update_response = admin_client.post(
        f"/music/{track_id}/edit",
        data={
            "title": "Edited Track",
            "artist_name": "After",
            "mood": "Minimal",
            "description": "Now with a cleaner surface.",
            "overall_review": "The details page should feel more polished.",
            "cover_file": (BytesIO(b"new cover"), "edited-cover.png"),
            "lyrics_file": (BytesIO(b"[00:10.00]Updated line"), "edited.lrc"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert update_response.status_code == 200
    assert b"Track updated." in update_response.data
    assert b"Edited Track" in update_response.data
    assert b"track-detail-cover" in update_response.data

    with app.app_context():
        track = db.session.get(Track, track_id)
        assert track.title == "Edited Track"
        assert track.artist_name == "After"
        assert track.mood == "Minimal"
        assert track.cover_relative_path is not None
        assert track.lyrics_relative_path is not None


def test_music_player_window_renders_floating_shell(admin_client):
    response = admin_client.get("/music/player-window")
    assert response.status_code == 200
    assert b"data-player-floating-window" in response.data
    assert b"data-player-window-url" in response.data


def test_main_page_player_uses_collapsible_bubble_shell(admin_client):
    response = admin_client.get("/")
    assert response.status_code == 200
    assert b"data-player-bubble" in response.data
    assert b"data-player-collapse-toggle" in response.data
    assert b"data-player-drag-handle" in response.data
    assert b"data-player-artwork" in response.data
    assert b"data-player-settings-toggle" in response.data
    assert b"data-player-opacity-input" in response.data
    assert b"data-player-scale-input" in response.data


def test_admin_can_create_video_and_timestamp_note(admin_client, app):
    response = admin_client.post(
        "/videos",
        data={
            "title": "Travel Clip",
            "overall_review": "The opening shot still makes me smile.",
            "video_file": (BytesIO(b"fake video"), "travel.mp4"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Video added to the library." in response.data

    with app.app_context():
        video = VideoEntry.query.one()
        video_id = video.id

    note_response = admin_client.post(
        f"/videos/{video_id}/comments",
        data={"timestamp_seconds": "00:42", "comment": "This is exactly where the joke lands."},
        follow_redirects=True,
    )
    assert note_response.status_code == 200
    assert b"Video note saved." in note_response.data
    assert b"00:42" in note_response.data


def test_videos_page_renders_preview_media(admin_client, app):
    with app.app_context():
        video = VideoEntry(
            title="Preview Clip",
            owner_id=1,
            original_name="preview.mov",
            stored_name="preview.mov",
            relative_path="uploads/2026/03/preview.mov",
            mime_type="video/quicktime",
            preview_relative_path="uploads/2026/03/preview.mp4",
            preview_mime_type="video/mp4",
            poster_relative_path="uploads/2026/03/preview.jpg",
            poster_mime_type="image/jpeg",
            size_bytes=24,
        )
        db.session.add(video)
        db.session.commit()
        video_id = video.id

    response = admin_client.get("/videos")
    assert response.status_code == 200
    assert b"data-video-card-preview" in response.data
    assert b"uploads/2026/03/preview.mp4" in response.data
    assert b"uploads/2026/03/preview.jpg" in response.data

    detail_response = admin_client.get(f"/videos/{video_id}")
    assert detail_response.status_code == 200
    assert b"uploads/2026/03/preview.mp4" in detail_response.data
    assert b"uploads/2026/03/preview.jpg" in detail_response.data


def test_admin_can_create_moment_with_multiple_folders_and_uploads(admin_client, app):
    with app.app_context():
        root = Category(name="Study Docs", description="Main study materials.")
        child = Category(name="Python Notes", description="Language-specific notes.", parent=root)
        db.session.add_all([root, child])
        db.session.commit()
        root_id = root.id
        child_id = child.id

    response = admin_client.post(
        "/moments",
        data={
            "content": "Sorted two useful files today.",
            "folder_ids": [str(root_id), str(child_id)],
            "location_label": "Qingdao Laoshan District",
            "latitude": "36.111944",
            "longitude": "120.468611",
            "files": [
                (BytesIO(b"%PDF-1.4 demo"), "notes.pdf"),
                (BytesIO(b"fake image"), "cover.png"),
            ],
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200

    with app.app_context():
        moment = Moment.query.one()
        assert moment.content == "Sorted two useful files today."
        assert moment.location_label == "Qingdao Laoshan District"
        assert moment.primary_category.name == "Study Docs"
        assert {folder.name for folder in moment.assigned_categories} == {
            "Study Docs",
            "Python Notes",
        }
        assert len(moment.attachments) == 2
        assert all(attachment.stored_name != attachment.original_name for attachment in moment.attachments)
        assert {attachment.media_kind for attachment in moment.attachments} == {"document", "image"}


def test_moment_image_upload_generates_compressed_preview(admin_client, app):
    response = admin_client.post(
        "/moments",
        data={
            "content": "Compressed image upload",
            "files": [(BytesIO(build_photo_bytes()), "photo.jpg")],
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Moment published." in response.data

    with app.app_context():
        attachment = Attachment.query.one()
        assert attachment.media_kind == "image"
        assert attachment.preview_relative_path is not None
        assert attachment.preview_relative_path != attachment.relative_path
        assert attachment.preview_mime_type == "image/jpeg"

        source_path = resolve_storage_path(app.config["UPLOAD_FOLDER"], attachment.relative_path)
        preview_path = resolve_storage_path(
            app.config["UPLOAD_FOLDER"], attachment.preview_relative_path
        )
        assert source_path.exists()
        assert preview_path.exists()
        assert attachment.size_bytes == source_path.stat().st_size


def test_feed_request_backfills_preview_for_existing_image_attachment(client, app):
    with app.app_context():
        relative_path = "uploads/2026/03/backfill-photo.jpg"
        source_path = resolve_storage_path(app.config["UPLOAD_FOLDER"], relative_path)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(build_photo_bytes())

        moment = Moment(content="Backfill photo", author_id=1)
        db.session.add(moment)
        db.session.flush()

        attachment = Attachment(
            moment_id=moment.id,
            original_name="backfill-photo.jpg",
            stored_name="backfill-photo.jpg",
            relative_path=relative_path,
            mime_type="image/jpeg",
            media_kind="image",
            size_bytes=source_path.stat().st_size,
        )
        db.session.add(attachment)
        db.session.commit()
        attachment_id = attachment.id

    response = client.get("/")
    assert response.status_code == 200

    with app.app_context():
        attachment = db.session.get(Attachment, attachment_id)
        assert attachment is not None
        assert attachment.preview_relative_path is not None
        preview_path = resolve_storage_path(
            app.config["UPLOAD_FOLDER"], attachment.preview_relative_path
        )
        assert preview_path.exists()
        assert attachment.preview_relative_path.encode() in response.data


def test_existing_image_preview_skips_reoptimization(monkeypatch, app):
    with app.app_context():
        relative_path = "uploads/2026/03/already-optimized.jpg"
        preview_relative_path = "uploads/2026/03/already-optimized-preview.jpg"
        source_path = resolve_storage_path(app.config["UPLOAD_FOLDER"], relative_path)
        preview_path = resolve_storage_path(app.config["UPLOAD_FOLDER"], preview_relative_path)
        source_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(build_photo_bytes())
        preview_path.write_bytes(b"preview")

        attachment = Attachment(
            original_name="already-optimized.jpg",
            stored_name="already-optimized.jpg",
            relative_path=relative_path,
            preview_relative_path=preview_relative_path,
            mime_type="image/jpeg",
            preview_mime_type="image/jpeg",
            media_kind="image",
            size_bytes=source_path.stat().st_size,
            moment_id=1,
        )

        called = False

        def fake_optimize(_source_path):
            nonlocal called
            called = True
            return None

        monkeypatch.setattr("app.services.image_previews.optimize_uploaded_image", fake_optimize)

        created_paths = ensure_attachment_image_preview(attachment, app.config["UPLOAD_FOLDER"])

        assert created_paths == []
        assert called is False


def test_admin_can_publish_citation_only_moment(admin_client, app):
    with app.app_context():
        book = Book(
            title="Cited Book",
            author_name="Author",
            status="reading",
            owner_id=1,
            source_format="txt",
            original_name="cited.txt",
            stored_name="cited.txt",
            relative_path="uploads/2026/03/cited.txt",
            mime_type="text/plain",
            size_bytes=12,
        )
        db.session.add(book)
        db.session.commit()
        book_id = book.id

    response = admin_client.post(
        "/moments",
        data={
            "citation_kind": "book",
            "citation_target_id": str(book_id),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Moment published." in response.data
    assert b"Cited Book" in response.data
    assert b"Book" in response.data

    with app.app_context():
        moment = Moment.query.one()
        assert moment.content is None
        assert moment.citation_kind == "book"
        assert moment.citation_title == "Cited Book"


def test_track_citation_uses_music_card_presentation(admin_client, app):
    with app.app_context():
        track = Track(
            title="Garden Theme",
            artist_name="Zhehua",
            owner_id=1,
            original_name="garden-theme.mp3",
            stored_name="garden-theme.mp3",
            relative_path="uploads/2026/03/garden-theme.mp3",
            mime_type="audio/mpeg",
            size_bytes=12,
            cover_relative_path="uploads/2026/03/garden-theme-cover.jpg",
        )
        db.session.add(track)
        db.session.commit()
        track_id = track.id

    response = admin_client.post(
        "/moments",
        data={
            "citation_kind": "track",
            "citation_target_id": str(track_id),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"moment-citation--music" in response.data
    assert b"Garden Theme" in response.data
    assert b"Zhehua" in response.data


def test_citation_search_endpoint_returns_library_items(admin_client, app):
    with app.app_context():
        book = Book(
            title="Anchor Book",
            author_name="Dostoevsky",
            status="reading",
            owner_id=1,
            source_format="epub",
            original_name="anchor.epub",
            stored_name="anchor.epub",
            relative_path="uploads/2026/03/anchor.epub",
            mime_type="application/epub+zip",
            size_bytes=12,
        )
        track = Track(
            title="Anchor Track",
            artist_name="G.E.M.",
            owner_id=1,
            original_name="anchor.mp3",
            stored_name="anchor.mp3",
            relative_path="uploads/2026/03/anchor.mp3",
            mime_type="audio/mpeg",
            size_bytes=18,
        )
        video = VideoEntry(
            title="Anchor Video",
            owner_id=1,
            original_name="anchor.mp4",
            stored_name="anchor.mp4",
            relative_path="uploads/2026/03/anchor.mp4",
            mime_type="video/mp4",
            size_bytes=24,
        )
        db.session.add_all([book, track, video])
        db.session.flush()

        annotation = BookAnnotation(
            book_id=book.id,
            owner_id=1,
            annotation_type="text_anchor",
            chapter_label="First Night",
            section_index=1,
            paragraph_id="p-1",
            selection_start=0,
            selection_end=8,
            quoted_text="Anchor quote",
            comment="Anchor note",
        )
        track_note = TrackComment(track_id=track.id, owner_id=1, timestamp_seconds=42, comment="Anchor groove")
        video_note = VideoComment(video_id=video.id, owner_id=1, timestamp_seconds=24, comment="Anchor scene")
        db.session.add_all([annotation, track_note, video_note])
        db.session.commit()

    response = admin_client.get("/api/citations/search?q=Anchor")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["scope"] == "all"
    kinds = {item["kind"] for item in payload["items"]}
    assert "book" in kinds
    assert "book_annotation" in kinds
    assert "track" in kinds
    assert "track_comment" in kinds
    assert "video" in kinds
    assert "video_comment" in kinds


def test_feed_renders_mixed_visual_media_grid_and_document_section(client, app):
    with app.app_context():
        moment = Moment(content="Visual layout check", author_id=1)
        db.session.add(moment)
        db.session.flush()
        attachments = [
            Attachment(
                moment_id=moment.id,
                original_name="cover.png",
                stored_name="cover.png",
                relative_path="uploads/2026/03/cover.png",
                mime_type="image/png",
                media_kind="image",
                size_bytes=12,
            ),
            Attachment(
                moment_id=moment.id,
                original_name="clip.mp4",
                stored_name="clip.mp4",
                relative_path="uploads/2026/03/clip.mp4",
                mime_type="video/mp4",
                media_kind="video",
                size_bytes=18,
            ),
            Attachment(
                moment_id=moment.id,
                original_name="detail.jpg",
                stored_name="detail.jpg",
                relative_path="uploads/2026/03/detail.jpg",
                mime_type="image/jpeg",
                media_kind="image",
                size_bytes=10,
            ),
            Attachment(
                moment_id=moment.id,
                original_name="notes.pdf",
                stored_name="notes.pdf",
                relative_path="uploads/2026/03/notes.pdf",
                mime_type="application/pdf",
                media_kind="document",
                size_bytes=20,
            ),
        ]
        db.session.add_all(attachments)
        db.session.commit()

    response = client.get("/")
    assert response.status_code == 200
    assert b"media-cluster media-cluster--quad" in response.data
    assert b'data-media-preview' in response.data
    assert b'data-preview-group="moment-' in response.data
    assert b'data-preview-kind="image"' in response.data
    assert b'data-preview-kind="video"' in response.data
    assert b'data-preview-kind="pdf"' in response.data
    assert b"attachment-grid attachment-grid--documents" in response.data
    assert b"data-media-viewer-prev" in response.data
    assert b"data-media-viewer-next" in response.data


def test_admin_can_update_moment_folders_delete_and_restore(admin_client, app):
    with app.app_context():
        first = Category(name="Movie Picks")
        second = Category(name="Idea Archive")
        db.session.add_all([first, second])
        db.session.flush()
        moment = Moment(content="A moment waiting to be reorganized.", author_id=1)
        moment.set_categories([first])
        db.session.add(moment)
        db.session.commit()
        moment_id = moment.id
        first_id = first.id
        second_id = second.id

    patch_response = admin_client.patch(
        f"/api/moments/{moment_id}/folders",
        json={"folder_ids": [first_id, second_id]},
    )
    assert patch_response.status_code == 200
    payload = patch_response.get_json()
    assert payload["primary_folder_name"] == "Movie Picks"
    assert set(payload["folder_names"]) == {"Movie Picks", "Idea Archive"}

    delete_response = admin_client.delete(f"/api/moments/{moment_id}")
    assert delete_response.status_code == 200

    with app.app_context():
        moment = db.session.get(Moment, moment_id)
        assert moment.is_deleted is True
        assert moment.deleted_at is not None

    restore_response = admin_client.post(f"/api/moments/{moment_id}/restore")
    assert restore_response.status_code == 200

    with app.app_context():
        moment = db.session.get(Moment, moment_id)
        assert moment.is_deleted is False
        assert moment.deleted_at is None
        assert {folder.name for folder in moment.assigned_categories} == {
            "Movie Picks",
            "Idea Archive",
        }


def test_admin_can_delete_folder_and_preserve_moment_data(admin_client, app):
    with app.app_context():
        parent = Category(name="Projects")
        child = Category(name="2026", parent=parent)
        db.session.add_all([parent, child])
        db.session.flush()

        parent_only = Moment(content="Parent only", author_id=1)
        parent_only.set_categories([parent])
        mixed = Moment(content="Parent and child", author_id=1)
        mixed.set_categories([parent, child])
        db.session.add_all([parent_only, mixed])
        db.session.commit()
        parent_id = parent.id
        child_id = child.id
        parent_only_id = parent_only.id
        mixed_id = mixed.id

    response = admin_client.post(f"/categories/{parent_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert b"Collection deleted." in response.data

    with app.app_context():
        assert db.session.get(Category, parent_id) is None
        child = db.session.get(Category, child_id)
        assert child is not None
        assert child.parent_id is None

        parent_only = db.session.get(Moment, parent_only_id)
        mixed = db.session.get(Moment, mixed_id)
        assert parent_only.assigned_categories == []
        assert {folder.name for folder in mixed.assigned_categories} == {"2026"}


def test_sidebar_separates_modules_from_collections(admin_client):
    response = admin_client.get("/")
    assert response.status_code == 200
    assert b"Spaces" in response.data
    assert b"Filters" in response.data
    assert b"Folders" in response.data
    assert b"Quiet Atlas" in response.data
    assert b"Studio" in response.data
    assert b"Structure" in response.data
    assert b"Collection Structure" in response.data
    assert b"Footprints" in response.data
    assert b"Create Folder" in response.data
    assert b'data-open-folder-panel="map"' in response.data
    assert b'data-open-folder-panel="create"' in response.data
    assert b'data-open-folder-panel="workspace"' in response.data
    assert b"Open Books, Music, or Videos from the homepage" not in response.data
    assert b"Library" in response.data
    assert b'href="/footprints"' in response.data
    assert b'href="/books"' in response.data
    assert b'href="/music"' in response.data
    assert b'href="/videos"' in response.data
    assert b"Quick navigation" in response.data
    assert b"Collection created." not in response.data


def test_admin_can_switch_interface_language_to_chinese(admin_client):
    response = admin_client.post(
        "/preferences/language",
        data={"language": "zh", "next": "/"},
        follow_redirects=True,
    )

    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'lang="zh-CN"' in html
    assert "发布动态" in html
    assert "分区" in html
    assert "收藏夹" in html
    assert "资料库" in html


def test_admin_can_customize_workspace_labels(admin_client, app):
    response = admin_client.post(
        "/workspace/preferences",
        data={
            "workspace_name": "Soft Archive",
            "workspace_tagline": "Private rooms",
            "feed_label": "Journal",
            "books_label": "Shelf",
            "music_label": "Audio",
            "videos_label": "Screen",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Workspace style updated." in response.data
    assert b"Soft Archive" in response.data
    assert b"Journal" in response.data
    assert b"Shelf" in response.data
    assert b"Audio" in response.data
    assert b"Screen" in response.data

    with app.app_context():
        user = User.query.filter_by(username="admin").one()
        assert user.workspace_name == "Soft Archive"
        assert user.feed_label == "Journal"


def test_book_detail_uses_cleaner_header_copy(admin_client, app):
    response = admin_client.post(
        "/books",
        data={
            "title": "Clean Detail",
            "status": "reading",
            "source_file": (BytesIO(b"Plain book"), "clean.txt"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Clean Detail" in response.data
    assert b"A reading record with notes, dates, and source files." not in response.data
    assert b"Track the source file, reading dates, and your overall reaction." not in response.data
    assert b"Quoted passages, page notes, and reactions all stay together here." not in response.data
    assert b"data-history-back" in response.data
    assert b"Imported" in response.data
    assert b'data-open-folder-panel="book-edit"' in response.data


def test_admin_can_edit_moment_and_store_folder_history(admin_client, app):
    with app.app_context():
        original_primary = Category(name="Original Bucket")
        original_secondary = Category(name="Reference Shelf")
        updated_folder = Category(name="Updated Bucket")
        db.session.add_all([original_primary, original_secondary, updated_folder])
        db.session.flush()
        moment = Moment(
            content="Old content",
            location_label="Old Location",
            latitude=30.1,
            longitude=120.2,
            author_id=1,
        )
        moment.set_categories([original_primary, original_secondary])
        db.session.add(moment)
        db.session.commit()
        moment_id = moment.id
        updated_folder_id = updated_folder.id

    response = admin_client.post(
        f"/moments/{moment_id}/edit",
        data={
            "content": "New content with better wording.",
            "folder_ids": [str(updated_folder_id)],
            "location_label": "New Location",
            "latitude": "31.2",
            "longitude": "121.3",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Moment updated. A revision snapshot was saved." in response.data

    with app.app_context():
        moment = db.session.get(Moment, moment_id)
        revision = MomentRevision.query.filter_by(moment_id=moment_id).one()

        assert moment.content == "New content with better wording."
        assert {folder.name for folder in moment.assigned_categories} == {"Updated Bucket"}
        assert moment.location_label == "New Location"
        assert moment.latitude == 31.2
        assert moment.longitude == 121.3

        assert revision.content == "Old content"
        assert {item["name"] for item in revision.snapshot_categories} == {
            "Original Bucket",
            "Reference Shelf",
        }
        assert revision.location_label == "Old Location"
        assert revision.latitude == 30.1
        assert revision.longitude == 120.2
        assert revision.editor.username == "admin"


def test_admin_can_view_moment_history_with_folder_snapshot(admin_client, app):
    with app.app_context():
        first = Category(name="History Bucket")
        second = Category(name="Archive Child")
        db.session.add_all([first, second])
        db.session.flush()
        moment = Moment(content="Current content", author_id=1)
        moment.set_categories([first, second])
        db.session.add(moment)
        db.session.flush()
        revision = MomentRevision(
            moment_id=moment.id,
            content="Previous content",
            category_id=first.id,
            folder_snapshot=serialize_folder_snapshot([first, second]),
            edited_by_id=1,
        )
        db.session.add(revision)
        db.session.commit()
        moment_id = moment.id

    response = admin_client.get(f"/moments/{moment_id}/history")
    assert response.status_code == 200
    assert b"Moment Revision Timeline" in response.data
    assert b"Previous content" in response.data
    assert b"History Bucket" in response.data
    assert b"Archive Child" in response.data


def test_search_matches_moment_text_and_folder_metadata(client, app):
    with app.app_context():
        folder = Category(name="AI Papers", description="Transformers and vision research.")
        db.session.add(folder)
        db.session.flush()

        first = Moment(content="Vision transformer notes", author_id=1)
        first.set_categories([folder])
        second = Moment(content="A cooking log", author_id=1)
        db.session.add_all([first, second])
        db.session.commit()

    response = client.get("/?q=transformer")
    assert response.status_code == 200
    assert b"Vision transformer notes" in response.data
    assert b"A cooking log" not in response.data

    response = client.get("/?q=vision%20research")
    assert response.status_code == 200
    assert b"Vision transformer notes" in response.data


def test_geocode_api_returns_normalized_address(admin_client, monkeypatch):
    def fake_reverse_geocode(lat, lon, user_agent):
        return {
            "formatted_address": "Shandong Qingdao Laoshan Songling Road",
            "province": "Shandong",
            "city": "Qingdao",
            "district": "Laoshan",
            "road": "Songling Road",
            "latitude": lat,
            "longitude": lon,
        }

    monkeypatch.setattr("app.blueprints.api.reverse_geocode", fake_reverse_geocode)

    response = admin_client.post("/api/geocode", json={"lat": 36.1119, "lon": 120.4686})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["city"] == "Qingdao"
    assert payload["formatted_address"] == "Shandong Qingdao Laoshan Songling Road"


def test_purge_command_removes_soft_deleted_data(app):
    with app.app_context():
        moment = Moment(
            content="To be purged.",
            author_id=1,
            is_deleted=True,
            deleted_at=datetime.utcnow() - timedelta(days=31),
        )
        db.session.add(moment)
        db.session.flush()
        attachment = Attachment(
            moment_id=moment.id,
            original_name="old.txt",
            stored_name="deadbeef.txt",
            relative_path="uploads/2020/01/deadbeef.txt",
            mime_type="text/plain",
            media_kind="document",
            size_bytes=12,
        )
        db.session.add(attachment)
        db.session.commit()

    cli_runner = app.test_cli_runner()
    result = cli_runner.invoke(args=["purge-recycle-bin", "--days", "0"])
    assert result.exit_code == 0
    with app.app_context():
        assert Moment.query.count() == 0
