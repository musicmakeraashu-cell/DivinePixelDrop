from flask import (
    Flask,
    render_template,
    send_from_directory,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort
)

import os
import time

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

import database


app = Flask(__name__)


# ============================================================
# CONFIGURATION
# ============================================================

app.secret_key = "DivinePixelDrop-Admin-Secret-Key-Change-Later"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD_HASH = generate_password_hash("1234")

LOGIN_ATTEMPTS = {}

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60


# ============================================================
# IMAGE FOLDER
# ============================================================

IMAGE_FOLDER = os.path.join(
    app.static_folder,
    "images"
)

os.makedirs(
    IMAGE_FOLDER,
    exist_ok=True
)


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


def image_path(filename):
    """
    Safely create the full image path.
    """

    filename = clean_filename(filename)

    if not filename:
        return None

    full_path = os.path.abspath(
        os.path.join(
            IMAGE_FOLDER,
            filename
        )
    )

    image_folder_abs = os.path.abspath(
        IMAGE_FOLDER
    )

    try:
        if os.path.commonpath(
            [full_path, image_folder_abs]
        ) != image_folder_abs:
            return None
    except ValueError:
        return None

    return full_path


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

    images = []

    try:

        for filename in os.listdir(
            IMAGE_FOLDER
        ):

            file_path = image_path(
                filename
            )

            if not file_path:
                continue

            if not os.path.isfile(
                file_path
            ):
                continue

            if not is_allowed_image(
                filename
            ):
                continue

            images.append(filename)

    except Exception as error:

        print(
            "Image loading error:",
            error
        )

    images.sort(
        key=lambda name: name.lower()
    )

    return images


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

@app.route(
    "/images/<path:filename>"
)
def serve_image(filename):

    filename = clean_filename(
        filename
    )

    if not filename:
        abort(404)

    if not is_allowed_image(
        filename
    ):
        abort(404)

    file_path = image_path(
        filename
    )

    if not file_path:
        abort(404)

    if not os.path.isfile(
        file_path
    ):
        abort(404)

    return send_from_directory(
        IMAGE_FOLDER,
        filename
    )


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

        if (
            username == ADMIN_USERNAME
            and check_password_hash(
                ADMIN_PASSWORD_HASH,
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

    return render_template(
        "admin.html",
        logged_in=True,
        gallery=gallery
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
# UPLOAD WALLPAPERS
# ============================================================

@app.route(
    "/admin/upload",
    methods=["POST"]
)
def admin_upload():

    if not admin_logged_in():

        return redirect(
            url_for(
                "admin_login"
            )
        )

    files = request.files.getlist(
        "images"
    )

    uploaded_count = 0

    skipped_count = 0

    for file in files:

        if not file:
            skipped_count += 1
            continue

        original_filename = (
            file.filename or ""
        )

        filename = clean_filename(
            original_filename
        )

        if not filename:

            skipped_count += 1

            continue

        if not is_allowed_image(
            filename
        ):

            skipped_count += 1

            continue

        file_path = image_path(
            filename
        )

        if not file_path:

            skipped_count += 1

            continue

        try:

            file.save(
                file_path
            )

            database.save_metadata(
                filename,
                filename,
                "",
                "Uncategorized",
                "",
                0
            )

            uploaded_count += 1

        except Exception as error:

            print(
                "Upload error:",
                error
            )

            skipped_count += 1

    if uploaded_count > 0:

        message = (
            f"{uploaded_count} wallpaper(s) "
            f"uploaded successfully."
        )

        if skipped_count > 0:

            message += (
                f" {skipped_count} file(s) skipped."
            )

        flash(
            message,
            "success"
        )

    else:

        flash(
            "No valid image was uploaded.",
            "error"
        )

    return redirect(
        url_for(
            "admin_dashboard"
        )
    )


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

    file_path = image_path(
        filename
    )

    if not file_path or not os.path.isfile(
        file_path
    ):

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

    file_path = image_path(
        filename
    )

    if not file_path:

        flash(
            "Invalid wallpaper path.",
            "error"
        )

        return redirect(
            url_for(
                "admin_dashboard"
            )
        )

    try:

        if os.path.isfile(
            file_path
        ):

            os.remove(
                file_path
            )

            # Delete matching database metadata
            database.delete_metadata(
                filename
            )

            flash(
                "Wallpaper deleted successfully.",
                "success"
            )

        else:

            # Even if the image file is already gone,
            # remove any stale database metadata.

            try:

                database.delete_metadata(
                    filename
                )

            except Exception as db_error:

                print(
                    "Metadata cleanup error:",
                    db_error
                )

            flash(
                "Wallpaper was already missing.",
                "error"
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
# RUN SERVER
# ============================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )