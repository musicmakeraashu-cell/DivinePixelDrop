from flask import (
    Flask,
    render_template,
    send_from_directory,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort,
    Response,
    jsonify
)

import os
import time
import cloudinary
import cloudinary.uploader
import cloudinary.utils

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

import database


app = Flask(__name__)
cloudinary.config(secure=True)


# ============================================================
# CONFIGURATION
# ============================================================

app.secret_key = "DivinePixelDrop-Admin-Secret-Key-Change-Later"

ADMIN_USERNAME = "admin"

# This is only the fallback used the very first time the site ever
# runs. Once someone uses the "Change Password" form in the admin
# panel, the real password hash lives permanently in Cloudinary
# (see database.get_password_hash / database.set_password_hash),
# so it survives Render restarts.
DEFAULT_ADMIN_PASSWORD_HASH = generate_password_hash("1234")

LOGIN_ATTEMPTS = {}

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60


# ============================================================
# DATABASE
# ============================================================

database.init_db()


# ============================================================
# ALLOWED IMAGE TYPES
# ============================================================

ALLOWED_EXTENSIONS = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif"
)


# ============================================================
# FILENAME HELPERS
# ============================================================

def clean_filename(filename):
    """
    Keep Unicode filenames such as:

    महादेव.jpg
    कृष्ण.png
    राधा कृष्ण.webp

    without using secure_filename(), because secure_filename()
    can remove non-Latin characters.

    We still remove path information so users cannot provide
    paths such as ../something.
    """

    if not filename:
        return ""

    filename = str(filename).replace("\\", "/")

    filename = os.path.basename(filename)

    filename = filename.strip()

    if filename in ("", ".", ".."):
        return ""

    return filename


def is_allowed_image(filename):
    """
    Check image extension.
    """

    filename = clean_filename(filename)

    if not filename:
        return False

    return filename.lower().endswith(
        ALLOWED_EXTENSIONS
    )


# ============================================================
# GET IMAGE LIST
# ============================================================

def get_images():
    try:
        metadata_map = database.get_all_metadata()
        images = [filename for filename, meta in metadata_map.items() if meta.get("image_url")]
        images.sort(key=lambda name: name.lower())
        return images
    except Exception as error:
        print("Image loading error:", error)
        return []


# ============================================================
# GET GALLERY DATA
# ============================================================

def get_gallery_data():

    filenames = get_images()

    metadata_map = database.get_all_metadata()

    gallery = []

    for filename in filenames:

        meta = metadata_map.get(
            filename
        )

        if meta:

            gallery.append(meta)

        else:

            gallery.append(
                {
                    "filename": filename,
                    "title": filename,
                    "description": "",
                    "category": "Uncategorized",
                    "tags": "",
                    "featured": 0,
                    "upload_date": None,
                    "downloads": 0
                }
            )

    for index, item in enumerate(
        gallery
    ):

        item["index"] = index

    return gallery


# ============================================================
# CATEGORIES
# ============================================================

def get_categories(gallery):

    categories = sorted(
        set(
            item["category"]
            for item in gallery
            if item.get("category")
        )
    )

    return categories


# ============================================================
# RECENT WALLPAPERS
# ============================================================

def get_recent(
    gallery,
    limit=10
):

    dated = [
        item
        for item in gallery
        if item.get("upload_date")
    ]

    dated.sort(
        key=lambda item: item["upload_date"],
        reverse=True
    )

    return dated[:limit]


# ============================================================
# ADMIN LOGIN CHECK
# ============================================================

def admin_logged_in():

    return (
        session.get(
            "admin_logged_in"
        ) is True
    )


# ============================================================
# VIEWER HOME PAGE
# ============================================================

@app.route("/")
def home():

    try:
        database.increment_visits()
    except Exception as error:
        print("Visit tracking error:", error)

    gallery = get_gallery_data()

    categories = get_categories(
        gallery
    )

    recent = get_recent(
        gallery
    )

    return render_template(
        "index.html",
        gallery=gallery,
        categories=categories,
        recent=recent
    )


# ============================================================
# SERVE WALLPAPER
# ============================================================

@app.route("/images/<path:filename>")
def serve_image(filename):
    filename = clean_filename(filename)
    if not filename or not is_allowed_image(filename):
        abort(404)
    try:
        meta = database.get_metadata(filename)
        if meta.get("image_url"):
            return redirect(meta["image_url"])
    except Exception as error:
        print("Cloudinary image loading error:", error)
    abort(404)


# ============================================================
# DOWNLOAD WALLPAPER (forces a real "Save As", not a preview)
# ============================================================
#
# The old /images/<filename> route just redirects straight to the
# Cloudinary image URL, which browsers treat as "open this image",
# not "download this file". This route instead builds a special
# Cloudinary URL with the "attachment" flag, which tells Cloudinary
# to send the image back with a header that forces the browser's
# save dialog, and also counts the download at the same time.

@app.route("/download/<path:filename>")
def download_image(filename):
    filename = clean_filename(filename)
    if not filename or not is_allowed_image(filename):
        abort(404)
    try:
        meta = database.get_metadata(filename)
        public_id = meta.get("public_id")
        if public_id:
            download_url, _ = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type="image",
                flags="attachment",
                secure=True,
            )
            try:
                database.increment_downloads(filename)
            except Exception as error:
                print("Download tracking error:", error)
            return redirect(download_url)
    except Exception as error:
        print("Download error:", error)
    abort(404)


# ============================================================
# TRACK DOWNLOAD
# ============================================================

@app.route(
    "/track-download/<path:filename>",
    methods=["POST"]
)
def track_download(filename):

    filename = clean_filename(
        filename
    )

    if filename:

        try:

            database.increment_downloads(
                filename
            )

        except Exception as error:

            print(
                "Download tracking error:",
                error
            )

    return (
        "",
        204
    )


# ============================================================
# LIKE A WALLPAPER
# ============================================================
#
# Any visitor can call this (no login needed) to like a photo.
# It saves the new count permanently on Cloudinary and sends the
# updated number back so the page can update the heart/like count
# without a full reload.

@app.route("/like/<path:filename>", methods=["POST"])
def like_image(filename):
    filename = clean_filename(filename)
    if not filename:
        return jsonify({"error": "invalid filename"}), 400
    try:
        new_count = database.increment_likes(filename)
        if new_count is None:
            return jsonify({"error": "wallpaper not found"}), 404
        return jsonify({"likes": new_count}), 200
    except Exception as error:
        print("Like error:", error)
        return jsonify({"error": "could not save like"}), 500


# ============================================================
# ADMIN LOGIN
# ============================================================

@app.route(
    "/admin",
    methods=["GET", "POST"]
)
def admin_login():

    if admin_logged_in():

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    if request.method == "POST":

        client_ip = (
            request.remote_addr
            or "unknown"
        )

        now = time.time()

        attempt = LOGIN_ATTEMPTS.get(
            client_ip,
            {
                "count": 0,
                "locked_until": 0
            }
        )

        if now < attempt[
            "locked_until"
        ]:

            wait_seconds = int(
                attempt[
                    "locked_until"
                ] - now
            )

            flash(
                f"Too many failed attempts. "
                f"Try again in {wait_seconds} seconds.",
                "error"
            )

            return render_template(
                "admin.html"
            )

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        current_password_hash = database.get_password_hash(
            default_hash=DEFAULT_ADMIN_PASSWORD_HASH
        )

        if (
            username == ADMIN_USERNAME
            and check_password_hash(
                current_password_hash,
                password
            )
        ):

            session[
                "admin_logged_in"
            ] = True

            LOGIN_ATTEMPTS.pop(
                client_ip,
                None
            )

            return redirect(
                url_for(
                    "admin_dashboard"
                )
            )

        attempt["count"] += 1

        if attempt["count"] >= MAX_ATTEMPTS:

            attempt[
                "locked_until"
            ] = (
                now
                + LOCKOUT_SECONDS
            )

            attempt["count"] = 0

        LOGIN_ATTEMPTS[
            client_ip
        ] = attempt

        flash(
            "Invalid username or password.",
            "error"
        )

    return render_template(
        "admin.html"
    )


# ============================================================
# ADMIN DASHBOARD
# ============================================================

@app.route(
    "/admin/dashboard"
)
def admin_dashboard():

    if not admin_logged_in():

        return redirect(
            url_for(
                "admin_login"
            )
        )

    gallery = get_gallery_data()

    try:
        visits = database.get_visit_count()
    except Exception as error:
        print("Visit count error:", error)
        visits = 0

    return render_template(
        "admin.html",
        logged_in=True,
        gallery=gallery,
        visits=visits
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route(
    "/admin/logout"
)
def admin_logout():

    session.clear()

    return redirect(
        url_for(
            "admin_login"
        )
    )


# ============================================================
# CHANGE ADMIN PASSWORD
# ============================================================
#
# The new password is saved permanently on Cloudinary (via
# database.set_password_hash), so it survives Render restarts
# instead of resetting back to the old one.

@app.route("/admin/change-password", methods=["POST"])
def admin_change_password():

    if not admin_logged_in():
        return redirect(url_for("admin_login"))

    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    current_password_hash = database.get_password_hash(
        default_hash=DEFAULT_ADMIN_PASSWORD_HASH
    )

    if not check_password_hash(current_password_hash, current_password):
        flash("Current password is incorrect.", "error")
        return redirect(url_for("admin_dashboard"))

    if len(new_password) < 4:
        flash("New password must be at least 4 characters.", "error")
        return redirect(url_for("admin_dashboard"))

    if new_password != confirm_password:
        flash("New password and confirmation do not match.", "error")
        return redirect(url_for("admin_dashboard"))

    try:
        new_hash = generate_password_hash(new_password)
        database.set_password_hash(new_hash)
        flash("Password updated successfully.", "success")
    except Exception as error:
        print("Password update error:", error)
        flash("Could not update password. Please try again.", "error")

    return redirect(url_for("admin_dashboard"))


# ============================================================
# UPLOAD WALLPAPERS
# ============================================================

@app.route("/admin/upload", methods=["POST"])
def admin_upload():
    is_ajax = request.form.get("ajax") == "1"

    if not admin_logged_in():
        if is_ajax:
            return jsonify({"error": "not logged in"}), 401
        return redirect(url_for("admin_login"))

    files = request.files.getlist("images")

    # These are optional. The admin panel now sends the same title/
    # category with every file in a batch (the frontend uploads one
    # file per request), so a whole batch can be labelled together
    # without needing to edit each photo afterwards.
    title_input = request.form.get("title", "").strip()
    category_input = request.form.get("category", "").strip() or "Uncategorized"

    uploaded_count = 0
    skipped_count = 0

    for file in files:
        filename = clean_filename(file.filename or "")
        if not filename or not is_allowed_image(filename):
            skipped_count += 1
            continue
        try:
            result = cloudinary.uploader.upload(file, folder="divinepixeldrop/wallpapers", resource_type="image", use_filename=True, unique_filename=True)
            image_url = result.get("secure_url")
            public_id = result.get("public_id")
            if not image_url:
                raise RuntimeError("Cloudinary did not return an image URL")
            final_title = title_input or filename
            database.save_metadata(filename, final_title, "", category_input, "", 0, image_url=image_url, public_id=public_id)
            uploaded_count += 1
        except Exception as error:
            print("Cloudinary upload error:", error)
            skipped_count += 1

    if is_ajax:
        return jsonify({
            "uploaded": uploaded_count,
            "skipped": skipped_count
        }), 200

    if uploaded_count:
        msg=f"{uploaded_count} wallpaper(s) uploaded successfully."
        if skipped_count: msg += f" {skipped_count} file(s) skipped."
        flash(msg,"success")
    else:
        flash("No valid image was uploaded.","error")
    return redirect(url_for("admin_dashboard"))


# ============================================================
# EDIT WALLPAPER METADATA
# ============================================================

@app.route(
    "/admin/edit/<path:filename>",
    methods=["POST"]
)
def admin_edit(filename):

    if not admin_logged_in():

        return redirect(
            url_for(
                "admin_login"
            )
        )

    filename = clean_filename(
        filename
    )

    if not filename:

        flash(
            "Invalid wallpaper filename.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    existing_meta = database.get_all_metadata().get(filename)

    if not existing_meta or not existing_meta.get("image_url"):

        flash(
            "Wallpaper not found.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    title = (
        request.form.get(
            "title",
            ""
        ).strip()
        or filename
    )

    description = request.form.get(
        "description",
        ""
    ).strip()

    category = (
        request.form.get(
            "category",
            ""
        ).strip()
        or "Uncategorized"
    )

    tags = request.form.get(
        "tags",
        ""
    ).strip()

    featured = (
        1
        if request.form.get(
            "featured"
        ) == "on"
        else 0
    )

    try:

        database.save_metadata(
            filename,
            title,
            description,
            category,
            tags,
            featured
        )

        flash(
            "Wallpaper info updated.",
            "success"
        )

    except Exception as error:

        print(
            "Edit error:",
            error
        )

        flash(
            "Could not update wallpaper info.",
            "error"
        )

    return redirect(
        url_for(
            "admin_dashboard"
        )
    )


# ============================================================
# DELETE WALLPAPER
# ============================================================

@app.route(
    "/admin/delete/<path:filename>",
    methods=["POST"]
)
def admin_delete(filename):

    if not admin_logged_in():

        return redirect(
            url_for(
                "admin_login"
            )
        )

    # IMPORTANT:
    # Do NOT use secure_filename() here.
    # It can destroy Unicode filenames.

    filename = clean_filename(
        filename
    )

    if not filename:

        flash(
            "Invalid wallpaper filename.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    existing_meta = database.get_all_metadata().get(filename)

    if not existing_meta:

        # Nothing in the database for this filename.
        # Nothing to delete on Cloudinary either.

        flash(
            "Wallpaper was already missing.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    try:

        public_id = existing_meta.get("public_id")

        if public_id:

            try:

                cloudinary.uploader.destroy(
                    public_id,
                    resource_type="image"
                )

            except Exception as cloud_error:

                # Don't block metadata cleanup just because
                # the Cloudinary-side delete failed (e.g. the
                # asset was already removed on Cloudinary).

                print(
                    "Cloudinary delete error:",
                    cloud_error
                )

        database.delete_metadata(
            filename
        )

        flash(
            "Wallpaper deleted successfully.",
            "success"
        )

    except Exception as error:

        print(
            "Delete error:",
            error
        )

        flash(
            "Could not delete wallpaper.",
            "error"
        )

    return redirect(
        url_for(
            "admin_dashboard"
        )
    )


# ============================================================
# SEARCH ENGINE DISCOVERY
# ============================================================

@app.route("/robots.txt")
def robots():
    content = """User-agent: *
Allow: /

Sitemap: https://divinepixeldrop.onrender.com/sitemap.xml
"""
    return Response(content, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://divinepixeldrop.onrender.com/</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
"""
    return Response(content, mimetype="application/xml")


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.ico",
        mimetype="image/vnd.microsoft.icon"
    )


# ============================================================
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )