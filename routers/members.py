import os
import math
import secrets
import sqlite3
import time
import pandas as pd
from fastapi import APIRouter, Request, HTTPException, File, UploadFile
import config
from database import get_db_connection
from services.member_service import align_member_photos, find_member_photo_file

router = APIRouter(prefix="/api", tags=["Members & Vehicles"])

@router.post("/align-member-photos")
@router.get("/align-member-photos")
async def trigger_align_member_photos():
    return align_member_photos()

@router.post("/add-member")
async def add_member(request: Request):
    body = await request.json()
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            epc = body.get('e_tag_id', '').strip().upper()
            mem_id = body.get('mem_id', '').strip()
            name = body.get('name', '').strip()
            car_number = body.get('car_number', '').strip()

            if not epc or not mem_id or not name or not car_number:
                raise HTTPException(400, "Member ID, Name, Car Number, and EPC Tag ID are required")

            clash = conn.execute(
                "SELECT Mem_id, Name FROM members WHERE UPPER(E_tag_id)=? AND Mem_id!=?",
                (epc, mem_id)
            ).fetchone()
            if clash:
                raise HTTPException(409, f"This EPC tag is already assigned to {clash['Mem_id']} ({clash['Name']})")

            profile_pic = body.get('profile_pic', '').strip()
            if not profile_pic:
                auto_pic = find_member_photo_file(mem_id)
                if auto_pic:
                    profile_pic = auto_pic

            with conn:
                conn.execute("""INSERT INTO members
                    (Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(E_tag_id) DO UPDATE SET
                        Mem_id=excluded.Mem_id, Name=excluded.Name, Car_number=excluded.Car_number,
                        Make_Model=excluded.Make_Model, Profile_pic=excluded.Profile_pic""",
                    (mem_id, name, car_number, body.get('make_model', ''), epc, 'Active', profile_pic))
            return {"ok": True}
        finally:
            conn.close()

@router.put("/update-member")
async def update_member(request: Request):
    body = await request.json()
    row_id = body.get("id")
    old_id = body.get("old_mem_id")
    epc = (body.get("e_tag_id") or "").strip().upper()
    mem_id = (body.get("mem_id") or old_id or "").strip()
    name = (body.get("name") or "").strip()
    car_number = (body.get("car_number") or "").strip()
    make_model = (body.get("make_model") or "").strip()
    profile_pic = body.get("profile_pic") or ""
    if not profile_pic and mem_id:
        auto_pic = find_member_photo_file(mem_id)
        if auto_pic:
            profile_pic = auto_pic

    if not row_id and not old_id:
        raise HTTPException(400, "Member identification (id or old_mem_id) is required")
    if not epc:
        raise HTTPException(400, "EPC Tag ID (e_tag_id) is required")

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            target = None
            if row_id:
                target = conn.execute("SELECT id, Mem_id, Car_number, E_tag_id FROM members WHERE id=?", (row_id,)).fetchone()

            if not target and old_id:
                if car_number:
                    target = conn.execute(
                        "SELECT id, Mem_id, Car_number, E_tag_id FROM members WHERE (Mem_id=? OR id=?) AND UPPER(Car_number)=?",
                        (old_id, old_id, car_number.upper())
                    ).fetchone()
                if not target:
                    target = conn.execute("SELECT id, Mem_id, Car_number, E_tag_id FROM members WHERE Mem_id=? OR id=?", (old_id, old_id)).fetchone()

            if not target:
                raise HTTPException(404, "Member record not found")

            target_id = target["id"]

            clash = conn.execute(
                "SELECT id, Mem_id, Name, Car_number FROM members WHERE UPPER(E_tag_id)=? AND id!=?",
                (epc, target_id)
            ).fetchone()
            if clash:
                raise HTTPException(409, f"This EPC tag '{epc}' is already assigned to Member {clash['Mem_id']} ({clash['Name']} - {clash['Car_number']})")

            with conn:
                conn.execute("""UPDATE members SET 
                    Mem_id=?, Name=?, Car_number=?, Make_Model=?, E_tag_id=?, Profile_pic=?
                    WHERE id=?""",
                    (mem_id, name, car_number, make_model, epc, profile_pic, target_id))

                if name:
                    conn.execute(
                        "UPDATE members SET Name=?, Profile_pic=COALESCE(NULLIF(?, ''), Profile_pic) WHERE Mem_id=? AND id!=?",
                        (name, profile_pic, mem_id, target_id)
                    )

            return {"ok": True, "message": "Member updated successfully"}
        except HTTPException:
            raise
        except sqlite3.IntegrityError as exc_integrity:
            raise HTTPException(409, f"Database constraint violation: {exc_integrity}")
        except Exception as exc_general:
            raise HTTPException(500, f"Update failed: {exc_general}")
        finally:
            conn.close()

@router.get("/members")
async def get_members(page: int = 1, limit: int = 25, search: str = "", all: bool = False, grouped: bool = True):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            if all or limit == 0:
                rows = conn.execute(
                    "SELECT id, Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic FROM members ORDER BY Name ASC"
                ).fetchall()
                return [dict(r) for r in rows]

            page = max(1, page)
            limit = min(max(5, limit), 200)
            offset = (page - 1) * limit
            search_clean = search.strip()

            total_vehicles = conn.execute("SELECT COUNT(*) FROM members").fetchone()[0]
            unique_members = conn.execute("SELECT COUNT(DISTINCT Mem_id) FROM members WHERE Mem_id != '' AND Mem_id IS NOT NULL").fetchone()[0]
            total_active = conn.execute("SELECT COUNT(*) FROM members WHERE Status='Active' OR Status IS NULL OR Status=''").fetchone()[0]
            total_tagged = conn.execute("SELECT COUNT(*) FROM members WHERE E_tag_id != '' AND E_tag_id IS NOT NULL").fetchone()[0]

            if not grouped:
                if search_clean:
                    like_pat = f"%{search_clean}%"
                    total_records = conn.execute(
                        "SELECT COUNT(*) FROM members WHERE Name LIKE ? OR Mem_id LIKE ? OR Car_number LIKE ? OR E_tag_id LIKE ? OR Make_Model LIKE ?",
                        (like_pat, like_pat, like_pat, like_pat, like_pat)
                    ).fetchone()[0]
                    rows = conn.execute(
                        "SELECT id, Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic FROM members "
                        "WHERE Name LIKE ? OR Mem_id LIKE ? OR Car_number LIKE ? OR E_tag_id LIKE ? OR Make_Model LIKE ? "
                        "ORDER BY Name ASC LIMIT ? OFFSET ?",
                        (like_pat, like_pat, like_pat, like_pat, like_pat, limit, offset)
                    ).fetchall()
                else:
                    total_records = total_vehicles
                    rows = conn.execute(
                        "SELECT id, Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic FROM members "
                        "ORDER BY Name ASC LIMIT ? OFFSET ?",
                        (limit, offset)
                    ).fetchall()
                mem_list = [dict(r) for r in rows]
            else:
                if search_clean:
                    like_pat = f"%{search_clean}%"
                    total_records = conn.execute(
                        "SELECT COUNT(DISTINCT Mem_id) FROM members WHERE Name LIKE ? OR Mem_id LIKE ? OR Car_number LIKE ? OR E_tag_id LIKE ? OR Make_Model LIKE ?",
                        (like_pat, like_pat, like_pat, like_pat, like_pat)
                    ).fetchone()[0]
                    rows = conn.execute(
                        """SELECT m.Mem_id, m.Name, m.Profile_pic, m.Status,
                                  COUNT(m.id) as vehicle_count,
                                  SUM(CASE WHEN m.E_tag_id IS NOT NULL AND m.E_tag_id != '' THEN 1 ELSE 0 END) as tagged_count
                           FROM members m
                           WHERE m.Mem_id IN (
                               SELECT DISTINCT Mem_id FROM members
                               WHERE Name LIKE ? OR Mem_id LIKE ? OR Car_number LIKE ? OR E_tag_id LIKE ? OR Make_Model LIKE ?
                           )
                           GROUP BY m.Mem_id
                           ORDER BY m.Name ASC LIMIT ? OFFSET ?""",
                        (like_pat, like_pat, like_pat, like_pat, like_pat, limit, offset)
                    ).fetchall()
                else:
                    total_records = unique_members
                    rows = conn.execute(
                        """SELECT m.Mem_id, m.Name, m.Profile_pic, m.Status,
                                  COUNT(m.id) as vehicle_count,
                                  SUM(CASE WHEN m.E_tag_id IS NOT NULL AND m.E_tag_id != '' THEN 1 ELSE 0 END) as tagged_count
                           FROM members m
                           GROUP BY m.Mem_id
                           ORDER BY m.Name ASC LIMIT ? OFFSET ?""",
                        (limit, offset)
                    ).fetchall()

                mem_list = [dict(r) for r in rows]
                if mem_list:
                    mem_ids = [m["Mem_id"] for m in mem_list]
                    placeholders = ','.join('?' for _ in mem_ids)
                    v_rows = conn.execute(
                        f"SELECT id, Mem_id, Car_number, Make_Model, E_tag_id, Status FROM members WHERE Mem_id IN ({placeholders}) ORDER BY id ASC",
                        mem_ids
                    ).fetchall()
                    v_by_mem = {}
                    for v in v_rows:
                        v_by_mem.setdefault(v['Mem_id'], []).append(dict(v))
                    for m in mem_list:
                        m["vehicles"] = v_by_mem.get(m["Mem_id"], [])

            total_pages = math.ceil(total_records / limit) if total_records > 0 else 1

            return {
                "members": mem_list,
                "total": total_records,
                "total_vehicles": total_vehicles,
                "unique_members": unique_members,
                "page": page,
                "limit": limit,
                "total_pages": total_pages,
                "active_count": total_active,
                "tagged_count": total_tagged
            }
        finally:
            conn.close()

@router.get("/members/{mem_id}/vehicles")
async def get_member_vehicles(mem_id: str):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            member_rows = conn.execute(
                "SELECT id, Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic FROM members WHERE Mem_id=? ORDER BY id ASC",
                (mem_id,)
            ).fetchall()
            if not member_rows:
                raise HTTPException(404, f"Member with ID '{mem_id}' not found")
            vehicles = [dict(r) for r in member_rows]
            first = vehicles[0]
            return {
                "ok": True,
                "mem_id": first["Mem_id"],
                "name": first["Name"],
                "profile_pic": first["Profile_pic"],
                "status": first["Status"] or "Active",
                "vehicle_count": len(vehicles),
                "tagged_count": sum(1 for v in vehicles if v.get("E_tag_id")),
                "vehicles": vehicles
            }
        finally:
            conn.close()

@router.delete("/members/{identifier}")
async def delete_member(identifier: str):
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                if identifier.isdigit():
                    conn.execute("DELETE FROM members WHERE id=?", (int(identifier),))
                else:
                    conn.execute("DELETE FROM members WHERE E_tag_id=? OR Mem_id=?", (identifier, identifier))
            return {"ok": True}
        finally:
            conn.close()

@router.post("/enroll-mode")
async def toggle_enroll_mode(request: Request):
    body = await request.json()
    config.ENROLL_MODE["active"] = bool(body.get("active", False))
    return {"ok": True, "active": config.ENROLL_MODE["active"]}

@router.get("/waiting-tag")
async def get_waiting_tag():
    cutoff = time.time() - 15
    latest = None
    for item in config.RECENT_TAGS:
        if item.get("epoch", 0) > cutoff:
            latest = item
    return {
        "tag": latest["tag"] if latest else None,
        "time": latest["time"] if latest else None,
        "enroll_mode": config.ENROLL_MODE["active"]
    }

@router.post("/upload-profile")
async def upload_profile(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
        raise HTTPException(400, "Only JPG, PNG, or WEBP image formats are supported")
    ext = os.path.splitext(file.filename)[1]
    safe_name = f"{secrets.token_hex(6)}{ext}"
    target_path = os.path.join(config.PROFILE_DIR, safe_name)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(400, "Image file exceeds 5MB size limit")
    with open(target_path, "wb") as f_out:
        f_out.write(contents)
    return {"ok": True, "path": target_path.replace("\\", "/")}

@router.post("/import-members")
async def import_members(file: UploadFile = File(...)):
    filename_lower = file.filename.lower()
    if not filename_lower.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(400, "Only .csv or .xlsx spreadsheets are supported")
    contents = await file.read()
    temp_file = f"_import_{secrets.token_hex(4)}{os.path.splitext(filename_lower)[1]}"
    with open(temp_file, "wb") as f_out:
        f_out.write(contents)
    try:
        df = pd.read_excel(temp_file) if filename_lower.endswith(('.xlsx', '.xls')) else pd.read_csv(temp_file)
    except Exception as exc:
        try:
            os.remove(temp_file)
        except Exception:
            pass
        raise HTTPException(400, f"Failed reading spreadsheet: {exc}")

    colmap = {str(c).strip().lower().replace(' ', '_'): c for c in df.columns}

    def find_col(possible_keys):
        for key in possible_keys:
            if key in colmap:
                return colmap[key]
        return None

    c_mem = find_col(['mem_id', 'member_id', 'member_no', 'id', 'mem_no'])
    c_name = find_col(['name', 'member_name', 'full_name', 'driver_name'])
    c_car = find_col(['car_number', 'car_no', 'plate', 'vehicle_number', 'plate_no', 'reg_no'])
    c_epc = find_col(['e_tag_id', 'etag', 'tag_id', 'epc', 'rfid_tag', 'epc_tag'])
    c_make = find_col(['make_model', 'make', 'model', 'vehicle_model', 'car_model'])
    c_pic = find_col(['profile_pic', 'photo', 'picture', 'image'])

    if not (c_mem and c_name and c_car and c_epc):
        missing = []
        if not c_mem: missing.append('Member ID (mem_id)')
        if not c_name: missing.append('Name (name)')
        if not c_car: missing.append('Car Number (car_number)')
        if not c_epc: missing.append('E-Tag ID (e_tag_id)')
        try:
            os.remove(temp_file)
        except Exception:
            pass
        raise HTTPException(400, f"Missing required spreadsheet columns: {', '.join(missing)}")

    rows_to_insert = []
    skipped = 0
    for _, row in df.iterrows():
        m_id = str(row[c_mem]).strip() if pd.notna(row[c_mem]) else ''
        name = str(row[c_name]).strip() if pd.notna(row[c_name]) else ''
        car = str(row[c_car]).strip() if pd.notna(row[c_car]) else ''
        epc = str(row[c_epc]).strip().upper() if pd.notna(row[c_epc]) else ''
        make = str(row[c_make]).strip() if (c_make and pd.notna(row[c_make])) else ''
        pic = str(row[c_pic]).strip() if (c_pic and pd.notna(row[c_pic])) else ''

        if m_id and name and car and epc:
            rows_to_insert.append((m_id, name, car, make, epc, pic))
        else:
            skipped += 1

    imported = 0
    errors = []
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                conn.executemany("""INSERT INTO members
                    (Mem_id, Name, Car_number, Make_Model, E_tag_id, Status, Profile_pic)
                    VALUES (?, ?, ?, ?, ?, 'Active', ?)
                    ON CONFLICT(E_tag_id) DO UPDATE SET
                        Mem_id=excluded.Mem_id,
                        Name=excluded.Name,
                        Car_number=excluded.Car_number,
                        Make_Model=excluded.Make_Model,
                        Profile_pic=excluded.Profile_pic""",
                    rows_to_insert)
                imported = len(rows_to_insert)
        except Exception as exc_import:
            errors.append(str(exc_import))
        finally:
            conn.close()

    try:
        os.remove(temp_file)
    except Exception:
        pass

    try:
        align_member_photos()
    except Exception as exc_align:
        print(f"[IMPORT ALIGN ERROR] {exc_align}")

    return {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:10],
        "total_rows": len(df)
    }
