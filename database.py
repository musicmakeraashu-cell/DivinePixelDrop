import time
import datetime
import cloudinary
import cloudinary.api
import cloudinary.uploader

# ============================================================
# WHY THIS FILE CHANGED
# ============================================================
#
# Render's free plan wipes the local disk on every restart, so a
# sqlite file (wallpapers.db) living next to app.py used to lose
# all its rows every time the server restarted -- even though the
# actual images were safe on Cloudinary the whole time.
#
# Fix: instead of a separate local database, we now store each
# wallpaper's title/description/category/tags/featured/downloads
# directly on the Cloudinary asset itself, using Cloudinary's
# built-in "context" (custom metadata) feature. Since Cloudinary
# never gets wiped, the metadata can never get orphaned again.
#
# Every function below keeps the EXACT same name/inputs/outputs
# that app.py already expects, so app.py and the templates do not
# need to change at all.

CLOUDINARY_FOLDER = "divinepixeldrop/wallpapers"

_cache = {"data": None, "time": 0}
CACHE_SECONDS = 30  # small cache so a page with many views doesn't
                     # hammer the Cloudinary API on every request


def init_db():
    # Nothing to create anymore -- Cloudinary is the source of truth.
    pass


def _fetch_all_resources():
    resources = []
    next_cursor = None
    while True:
        params = {
            "type": "upload",
            "prefix": CLOUDINARY_FOLDER + "/",
            "context": True,
            "max_results": 500,
        }
        if next_cursor:
            params["next_cursor"] = next_cursor
        result = cloudinary.api.resources(**params)
        resources.extend(result.get("resources", []))
        next_cursor = result.get("next_cursor")
        if not next_cursor:
            break
    return resources


def _resource_to_metadata(resource):
    context = resource.get("context", {})
    custom = context.get("custom", {}) if isinstance(context, dict) else {}

    filename = custom.get("filename") or resource.get("public_id", "").split("/")[-1]

    try:
        featured = int(custom.get("featured", 0))
    except (TypeError, ValueError):
        featured = 0

    try:
        downloads = int(custom.get("downloads", 0))
    except (TypeError, ValueError):
        downloads = 0

    try:
        likes = int(custom.get("likes", 0))
    except (TypeError, ValueError):
        likes = 0

    return {
        "filename": filename,
        "title": custom.get("title") or filename,
        "description": custom.get("description", ""),
        "category": custom.get("category") or "Uncategorized",
        "tags": custom.get("tags", ""),
        "featured": featured,
        "upload_date": custom.get("upload_date") or resource.get("created_at"),
        "downloads": downloads,
        "likes": likes,
        "image_url": resource.get("secure_url"),
        "public_id": resource.get("public_id"),
    }


def _get_all_cached(force=False):
    now = time.time()
    if force or _cache["data"] is None or (now - _cache["time"]) > CACHE_SECONDS:
        try:
            resources = _fetch_all_resources()
        except Exception as error:
            print("Cloudinary metadata fetch error:", error)
            return _cache["data"] or {}

        metadata_map = {}
        for resource in resources:
            meta = _resource_to_metadata(resource)
            metadata_map[meta["filename"]] = meta

        _cache["data"] = metadata_map
        _cache["time"] = now

    return _cache["data"]


def get_metadata(filename):
    metadata_map = _get_all_cached()
    if filename in metadata_map:
        return metadata_map[filename]
    return {
        "filename": filename,
        "title": filename,
        "description": "",
        "category": "Uncategorized",
        "tags": "",
        "featured": 0,
        "upload_date": None,
        "downloads": 0,
        "likes": 0,
        "image_url": None,
        "public_id": None,
    }


def get_all_metadata():
    return _get_all_cached()


def save_metadata(filename, title, description, category, tags, featured, image_url=None, public_id=None):
    if not public_id:
        existing = _get_all_cached().get(filename)
        if existing:
            public_id = existing.get("public_id")

    if not public_id:
        # We only reach here if we truly cannot find which Cloudinary
        # asset this filename belongs to (shouldn't normally happen,
        # since app.py always passes public_id right after upload).
        print("save_metadata: no public_id found for", filename, "- skipped")
        return

    existing = _get_all_cached().get(filename, {})
    upload_date = existing.get("upload_date") or datetime.datetime.now().isoformat()
    downloads = existing.get("downloads", 0)

    context = {
        "filename": filename,
        "title": title,
        "description": description,
        "category": category,
        "tags": tags,
        "featured": str(featured),
        "upload_date": str(upload_date),
        "downloads": str(downloads),
    }

    cloudinary.uploader.add_context(context, [public_id])

    _cache["time"] = 0  # force a fresh read next time


def increment_downloads(filename):
    metadata_map = _get_all_cached()
    meta = metadata_map.get(filename)
    if not meta or not meta.get("public_id"):
        return

    new_count = meta.get("downloads", 0) + 1
    cloudinary.uploader.add_context({"downloads": str(new_count)}, [meta["public_id"]])
    _cache["time"] = 0


def increment_likes(filename):
    """
    Adds one like to a wallpaper and saves it permanently on
    Cloudinary. Returns the new total, or None if the wallpaper
    couldn't be found.
    """
    metadata_map = _get_all_cached()
    meta = metadata_map.get(filename)
    if not meta or not meta.get("public_id"):
        return None

    new_count = meta.get("likes", 0) + 1
    cloudinary.uploader.add_context({"likes": str(new_count)}, [meta["public_id"]])
    _cache["time"] = 0
    return new_count


def delete_metadata(filename):
    # app.py already destroys the Cloudinary asset (image + its
    # context/metadata together) before calling this. We just make
    # sure the next read pulls fresh data instead of a stale cache.
    _cache["time"] = 0