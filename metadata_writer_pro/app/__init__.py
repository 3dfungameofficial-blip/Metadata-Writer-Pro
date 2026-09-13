"""Central application metadata. Single source of truth for name/version."""

APP_NAME = "Metadata Writer Pro"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "Metadata Writer Pro"
APP_URL = ""

# Update server endpoint (GitHub Releases API style JSON). Empty means
# updates are NOT configured for this build — the UI will say so instead
# of inventing a repository. Publisher: set this to your real endpoint,
# e.g. "https://api.github.com/repos/YOUR_USERNAME/YOUR_REPO/releases/latest"
UPDATE_CHECK_URL = ""

SETTINGS_SCHEMA_VERSION = 2

# Supported media extensions (lowercase, with dot)
IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov"})
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
