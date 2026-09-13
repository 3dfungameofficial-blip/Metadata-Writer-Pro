"""Central application metadata. Single source of truth for name/version."""

APP_NAME = "Metadata Writer Pro"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "Metadata Writer Pro"
APP_URL = "https://github.com/3dfungameofficial-blip/Metadata-Writer-Pro"

# ---- Official update source (single source of truth; HTTPS only) ----
GITHUB_OWNER = "3dfungameofficial-blip"
GITHUB_REPO = "Metadata-Writer-Pro"
UPDATE_CHECK_URL = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
# Exact installer asset name published by the release workflow. The updater
# only trusts this filename (or the versioned variant below) from the
# official release — never arbitrary URLs.
EXPECTED_INSTALLER_ASSET = "MetadataWriterPro-Setup.exe"
CHECKSUMS_ASSET = "SHA256SUMS.txt"

SETTINGS_SCHEMA_VERSION = 2

# Supported media extensions (lowercase, with dot)
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov"})
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
