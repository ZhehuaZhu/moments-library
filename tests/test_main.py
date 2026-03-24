from __future__ import annotations

import json
from datetime import datetime, timedelta
from io import BytesIO

from app.extensions import db
from app.models import Attachment, Category, Moment, MomentRevision
from app.services.folders import serialize_folder_snapshot


def test_guest_cannot_access_recycle_bin(client):
    response = client.get("/recycle-bin", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


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
    assert b"Folder created." in response.data

    with app.app_context():
        folder = Category.query.filter_by(name="Research Notes").one()
        assert folder.description == "Long-term reading and papers."
        assert folder.parent_id == parent_id


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
    assert b"Folder deleted." in response.data

    with app.app_context():
        assert db.session.get(Category, parent_id) is None
        child = db.session.get(Category, child_id)
        assert child is not None
        assert child.parent_id is None

        parent_only = db.session.get(Moment, parent_only_id)
        mixed = db.session.get(Moment, mixed_id)
        assert parent_only.assigned_categories == []
        assert {folder.name for folder in mixed.assigned_categories} == {"2026"}


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
