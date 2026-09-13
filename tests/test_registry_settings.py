"""Processor registry + settings migration + updater version compare."""
from pathlib import Path

from metadata_writer_pro.app.metadata.base import build_default_registry
from metadata_writer_pro.app.services import settings as settings_mod
from metadata_writer_pro.app.services import updater as updater_mod


def test_registry_routes_image_and_video():
    reg = build_default_registry()
    assert reg.for_file(Path("a.jpg")) is not None
    assert reg.for_file(Path("b.PNG")) is not None
    assert reg.for_file(Path("c.mp4")) is not None
    assert reg.for_file(Path("d.MOV")) is not None
    assert reg.for_file(Path("e.avi")) is None
    names = {p.name for p in reg.processors}
    assert {"image", "video"} <= names


def test_settings_migration_v1_to_v2():
    migrated = settings_mod._migrate({"theme": "dark"})
    assert migrated["settings_version"] == settings_mod.DEFAULTS["settings_version"]
    assert migrated["theme"] == "dark"
    assert "write_fields" in migrated


def test_version_compare():
    assert updater_mod.is_newer("1.1.0", "1.0.0")
    assert not updater_mod.is_newer("1.0.0", "1.0.0")
    assert not updater_mod.is_newer("0.9.9", "1.0.0")
    assert updater_mod.is_newer("v2.0.0", "1.9.9")
