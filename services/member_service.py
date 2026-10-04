import os
import sqlite3
import config
from database import get_db_connection

def get_possible_filenames(mem_id: str) -> list[str]:
    """Generates candidate base filenames for a given member ID."""
    if not mem_id:
        return []
    clean_id = str(mem_id).strip()
    candidates = [
        clean_id,
        clean_id.lower(),
        clean_id.upper(),
        clean_id.replace("/", "_").replace("\\", "_"),
        clean_id.replace("/", "-").replace("\\", "-"),
        clean_id.replace(" ", "_"),
        clean_id.replace(" ", "")
    ]
    seen = set()
    result = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return result

def find_member_photo_file(mem_id: str) -> str | None:
    """
    Searches config.MEMBER_PROFILE_IMG_DIR and config.PROFILE_DIR for an image
    matching mem_id. Returns relative path (using forward slashes) or None.
    """
    if not mem_id:
        return None

    search_dirs = [
        getattr(config, 'MEMBER_PROFILE_IMG_DIR', os.path.join(config.STATIC_DIR, "member_profile_img")),
        config.PROFILE_DIR
    ]
    
    extensions = [".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG", ".WEBP"]
    bases = get_possible_filenames(mem_id)

    for directory in search_dirs:
        if not os.path.exists(directory):
            continue
        
        # Check direct candidate paths
        for base in bases:
            for ext in extensions:
                filename = f"{base}{ext}"
                full_path = os.path.join(directory, filename)
                if os.path.isfile(full_path):
                    return full_path.replace("\\", "/")

        # Scan directory files for case-insensitive / normalized stem match
        try:
            dir_files = os.listdir(directory)
            files_map = {}
            for f in dir_files:
                stem, ext = os.path.splitext(f)
                if ext.lower() in [".jpg", ".jpeg", ".png", ".webp", ".bmp"]:
                    files_map[stem.lower()] = os.path.join(directory, f)

            for base in bases:
                if base.lower() in files_map:
                    return files_map[base.lower()].replace("\\", "/")
        except Exception:
            pass

    return None

def align_member_photos() -> dict:
    """
    Scans static/member_profile_img and static/profiles directories and updates all
    member records in the database where a photo file exists matching member Mem_id.
    """
    search_dirs = [
        getattr(config, 'MEMBER_PROFILE_IMG_DIR', os.path.join(config.STATIC_DIR, "member_profile_img")),
        config.PROFILE_DIR
    ]

    image_map = {}  # stem_lowercase -> relative_path
    valid_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

    for d in search_dirs:
        if not os.path.exists(d):
            continue
        try:
            for entry in os.scandir(d):
                if entry.is_file():
                    stem, ext = os.path.splitext(entry.name)
                    if ext.lower() in valid_exts:
                        rel_path = os.path.join(d, entry.name).replace("\\", "/")
                        stem_lower = stem.lower()
                        if stem_lower not in image_map:
                            image_map[stem_lower] = rel_path
                        
                        sanitized_underscore = stem_lower.replace("-", "_").replace("/", "_").replace(" ", "_")
                        sanitized_hyphen = stem_lower.replace("_", "-").replace("/", "-").replace(" ", "-")
                        if sanitized_underscore not in image_map:
                            image_map[sanitized_underscore] = rel_path
                        if sanitized_hyphen not in image_map:
                            image_map[sanitized_hyphen] = rel_path
        except Exception as exc:
            print(f"[SCAN MEMBER IMAGES ERROR] {exc}")

    aligned_count = 0
    updated_count = 0
    updates_to_make = []

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            members = conn.execute("SELECT id, Mem_id, Profile_pic FROM members").fetchall()
            total_members = len(members)

            for m in members:
                row_id = m["id"]
                mem_id = (m["Mem_id"] or "").strip()
                current_pic = m["Profile_pic"] or ""

                if not mem_id:
                    continue

                mem_id_lower = mem_id.lower()
                candidates = [
                    mem_id_lower,
                    mem_id_lower.replace("/", "_").replace("\\", "_").replace(" ", "_"),
                    mem_id_lower.replace("/", "-").replace("\\", "-").replace(" ", "-"),
                    mem_id_lower.replace(" ", ""),
                ]

                matched_pic = None
                for cand in candidates:
                    if cand in image_map:
                        matched_pic = image_map[cand]
                        break

                if matched_pic:
                    aligned_count += 1
                    if current_pic != matched_pic:
                        updates_to_make.append((matched_pic, row_id))
                        updated_count += 1
                elif current_pic and not os.path.exists(current_pic):
                    # Reset dead link if current file no longer exists
                    updates_to_make.append(("", row_id))

            if updates_to_make:
                with conn:
                    conn.executemany("UPDATE members SET Profile_pic=? WHERE id=?", updates_to_make)

        except Exception as exc:
            print(f"[ALIGN PHOTOS DB ERROR] {exc}")
            return {"ok": False, "error": str(exc)}
        finally:
            conn.close()

    return {
        "ok": True,
        "total_members": total_members,
        "aligned_photos": aligned_count,
        "updated_records": updated_count,
        "total_images_in_folder": len(image_map)
    }
