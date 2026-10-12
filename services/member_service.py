import os
import re
import sqlite3
import config
from database import get_db_connection

def get_possible_filenames(mem_id: str) -> list[str]:
    """
    Generates comprehensive candidate base filenames for a given member ID,
    including leading-zero stripped (e.g., '0045' -> '45'), padded, and compound formats.
    """
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

    # 1. Leading-zero stripped variants (e.g., '0045' -> '45', '01234' -> '1234')
    stripped_zero = clean_id.lstrip('0') or '0'
    if stripped_zero != clean_id:
        candidates.extend([
            stripped_zero,
            stripped_zero.lower(),
            stripped_zero.upper(),
            stripped_zero.replace("/", "_").replace("\\", "_"),
            stripped_zero.replace("/", "-").replace("\\", "-"),
            stripped_zero.replace(" ", "")
        ])

    # 2. Compound ID leading-zero normalization (e.g., 'M-0045' -> 'M-45', 'A/0012' -> 'A/12')
    compound_stripped = re.sub(r'(^|[^0-9])0+([0-9]+)', r'\1\2', clean_id)
    if compound_stripped != clean_id:
        candidates.extend([
            compound_stripped,
            compound_stripped.lower(),
            compound_stripped.upper(),
            compound_stripped.replace("/", "_").replace("\\", "_"),
            compound_stripped.replace("/", "-").replace("\\", "-"),
            compound_stripped.replace(" ", "")
        ])

    # 3. Padded variants for numeric IDs (e.g., if ID is '45', also checks '0045', '00045', '000045')
    if stripped_zero.isdigit():
        for pad_len in (3, 4, 5, 6):
            if pad_len > len(stripped_zero):
                candidates.append(stripped_zero.zfill(pad_len))

    # 4. Pure numeric segment extraction (e.g., 'M-0045' -> '45')
    num_only = re.sub(r'\D', '', clean_id).lstrip('0') or '0'
    if num_only and num_only != clean_id and num_only != stripped_zero:
        candidates.append(num_only)

    seen = set()
    result = []
    for c in candidates:
        c_str = str(c).strip()
        if c_str and c_str.lower() not in seen:
            seen.add(c_str.lower())
            result.append(c_str)
    return result

def find_member_photo_file(mem_id: str) -> str | None:
    """
    Searches config.MEMBER_PROFILE_IMG_DIR and config.PROFILE_DIR for an image
    matching mem_id. Returns relative path (using forward slashes) or None.
    Handles leading zeros (0, 00) normalization seamlessly.
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
                    stem_lower = stem.lower()
                    files_map[stem_lower] = os.path.join(directory, f)
                    stripped_stem = stem_lower.lstrip('0') or '0'
                    if stripped_stem not in files_map:
                        files_map[stripped_stem] = os.path.join(directory, f)

            for base in bases:
                base_lower = base.lower()
                if base_lower in files_map:
                    return files_map[base_lower].replace("\\", "/")
        except Exception:
            pass

    return None

def align_member_photos() -> dict:
    """
    Scans static/member_profile_img and static/profiles directories and updates all
    member records in the database where a photo file exists matching member Mem_id.
    Includes robust leading-zero (0, 00) normalization so files without zeros (e.g. 45.jpg)
    align with membership numbers like 0045, 01234, etc.
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
                        
                        keys = [
                            stem_lower,
                            stem_lower.replace("-", "_").replace("/", "_").replace(" ", "_"),
                            stem_lower.replace("_", "-").replace("/", "-").replace(" ", "-"),
                            stem_lower.replace(" ", "")
                        ]

                        # Leading-zero stripped (e.g. image '0045.jpg' matches '45')
                        stripped_stem = stem_lower.lstrip('0') or '0'
                        if stripped_stem != stem_lower:
                            keys.extend([
                                stripped_stem,
                                stripped_stem.replace("-", "_").replace("/", "_").replace(" ", "_"),
                                stripped_stem.replace("_", "-").replace("/", "-").replace(" ", "-"),
                                stripped_stem.replace(" ", "")
                            ])

                        # Compound normalization
                        compound_stem = re.sub(r'(^|[^0-9])0+([0-9]+)', r'\1\2', stem_lower)
                        if compound_stem != stem_lower:
                            keys.append(compound_stem)

                        for k in keys:
                            if k not in image_map:
                                image_map[k] = rel_path
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

                candidates = get_possible_filenames(mem_id)

                matched_pic = None
                for cand in candidates:
                    cand_lower = cand.lower()
                    if cand_lower in image_map:
                        matched_pic = image_map[cand_lower]
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
