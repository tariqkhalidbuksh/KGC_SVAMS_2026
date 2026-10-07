import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta
import config
from database import get_db_connection

DEFAULT_USERS = [
    {
        "username": "admin",
        "password": "admin123",
        "full_name": "System Administrator",
        "role": "Admin",  # Full Administrative Rights
    },
    {
        "username": "operator",
        "password": "operator123",
        "full_name": "Gate Operator",
        "role": "Editor",  # Edit Rights (Manage Members, Fleet, Gates)
    },
    {
        "username": "security",
        "password": "security123",
        "full_name": "Security Guard",
        "role": "Viewer",  # View Rights (Read-only monitoring & audits)
    }
]

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    """Hashes password using PBKDF2 HMAC SHA-256 with 100,000 iterations."""
    if not salt:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    ).hex()
    return pw_hash, salt

def verify_password(password: str, pw_hash: str, salt: str) -> bool:
    """Verifies password against stored hash and salt."""
    calc_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(calc_hash, pw_hash)

def init_auth_tables():
    """Initializes user management and session tables in the database."""
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'Viewer',
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    last_login TIMESTAMP)""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")

                conn.execute("""CREATE TABLE IF NOT EXISTS user_sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT (datetime('now', 'localtime')),
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE)""")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at)")

                # Seed default users if users table is empty
                count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                if count == 0:
                    for u in DEFAULT_USERS:
                        pw_hash, salt = hash_password(u["password"])
                        conn.execute("""INSERT INTO users (username, password_hash, salt, full_name, role, is_active)
                                        VALUES (?, ?, ?, ?, ?, 1)""",
                                     (u["username"].lower(), pw_hash, salt, u["full_name"], u["role"]))
        finally:
            conn.close()

def authenticate_user(username: str, password: str) -> dict | None:
    """Authenticates username and password. Returns user dict on success, None on failure."""
    username = (username or "").strip().lower()
    if not username or not password:
        return None

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            row = conn.execute("SELECT * FROM users WHERE LOWER(username) = ?", (username,)).fetchone()
            if not row:
                return None
            if not row["is_active"]:
                return None
            if not verify_password(password, row["password_hash"], row["salt"]):
                return None

            # Update last_login
            with conn:
                conn.execute("UPDATE users SET last_login = datetime('now', 'localtime') WHERE id = ?", (row["id"],))

            return {
                "id": row["id"],
                "username": row["username"],
                "full_name": row["full_name"],
                "role": row["role"],
                "is_active": row["is_active"],
                "last_login": row["last_login"]
            }
        finally:
            conn.close()

def create_session(user_id: int, days_valid: int = 7) -> str:
    """Creates a persistent session token for user."""
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now() + timedelta(days=days_valid)).strftime("%Y-%m-%d %H:%M:%S")
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                # Remove expired sessions first
                conn.execute("DELETE FROM user_sessions WHERE expires_at < datetime('now', 'localtime')")
                conn.execute("INSERT INTO user_sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                             (token, user_id, expires_at))
            return token
        finally:
            conn.close()

def validate_session(token: str) -> dict | None:
    """Validates session token and returns user info if valid, else None."""
    if not token:
        return None
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            row = conn.execute("""
                SELECT u.id, u.username, u.full_name, u.role, u.is_active, s.expires_at
                FROM user_sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.token = ? AND s.expires_at > datetime('now', 'localtime') AND u.is_active = 1
            """, (token,)).fetchone()
            if not row:
                return None
            return {
                "id": row["id"],
                "username": row["username"],
                "full_name": row["full_name"],
                "role": row["role"],
                "is_active": row["is_active"]
            }
        finally:
            conn.close()

def destroy_session(token: str):
    """Deletes session token."""
    if not token:
        return
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
        finally:
            conn.close()

def list_users() -> list[dict]:
    """Returns list of all users without sensitive fields."""
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            rows = conn.execute("""
                SELECT id, username, full_name, role, is_active, created_at, last_login
                FROM users
                ORDER BY role = 'Admin' DESC, role = 'Editor' DESC, username ASC
            """).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

def create_user(username: str, password: str, full_name: str, role: str = "Viewer", is_active: int = 1) -> dict:
    """Creates a new user record."""
    username = (username or "").strip().lower()
    full_name = (full_name or "").strip()
    role = role if role in ("Admin", "Editor", "Viewer") else "Viewer"

    if not username:
        raise ValueError("Username cannot be empty")
    if not password or len(password) < 4:
        raise ValueError("Password must be at least 4 characters")
    if not full_name:
        raise ValueError("Full name cannot be empty")

    pw_hash, salt = hash_password(password)
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            with conn:
                cursor = conn.execute("""
                    INSERT INTO users (username, password_hash, salt, full_name, role, is_active)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (username, pw_hash, salt, full_name, role, 1 if is_active else 0))
                user_id = cursor.lastrowid
            return {
                "id": user_id,
                "username": username,
                "full_name": full_name,
                "role": role,
                "is_active": is_active
            }
        except sqlite3.IntegrityError:
            raise ValueError(f"Username '{username}' already exists")
        finally:
            conn.close()

def update_user(user_id: int, full_name: str = None, role: str = None, is_active: int = None, password: str = None) -> dict:
    """Updates user fields, and optionally changes password."""
    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                raise ValueError("User not found")

            updates = []
            params = []

            if full_name is not None and full_name.strip():
                updates.append("full_name = ?")
                params.append(full_name.strip())

            if role is not None and role in ("Admin", "Editor", "Viewer"):
                # Check that we do not remove the last Admin
                if user["role"] == "Admin" and role != "Admin":
                    admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin' AND is_active = 1").fetchone()[0]
                    if admin_count <= 1:
                        raise ValueError("Cannot remove admin rights from the only remaining administrator")
                updates.append("role = ?")
                params.append(role)

            if is_active is not None:
                val = 1 if is_active else 0
                if user["role"] == "Admin" and val == 0:
                    admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin' AND is_active = 1").fetchone()[0]
                    if admin_count <= 1:
                        raise ValueError("Cannot disable the only remaining active administrator")
                updates.append("is_active = ?")
                params.append(val)

            if password and password.strip():
                if len(password.strip()) < 4:
                    raise ValueError("Password must be at least 4 characters")
                pw_hash, salt = hash_password(password.strip())
                updates.append("password_hash = ?")
                params.append(pw_hash)
                updates.append("salt = ?")
                params.append(salt)

            if not updates:
                return dict(user)

            params.append(user_id)
            with conn:
                conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)

            updated = conn.execute("SELECT id, username, full_name, role, is_active, created_at, last_login FROM users WHERE id = ?", (user_id,)).fetchone()
            return dict(updated)
        finally:
            conn.close()

def delete_user(user_id: int, current_user_id: int = None) -> bool:
    """Deletes a user account with safety checks."""
    if current_user_id and user_id == current_user_id:
        raise ValueError("You cannot delete your own account while logged in")

    with config.DB_LOCK:
        conn = get_db_connection()
        try:
            user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not user:
                raise ValueError("User not found")

            if user["role"] == "Admin":
                admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'Admin' AND is_active = 1").fetchone()[0]
                if admin_count <= 1:
                    raise ValueError("Cannot delete the only remaining active administrator")

            with conn:
                conn.execute("DELETE FROM user_sessions WHERE user_id = ?", (user_id,))
                conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return True
        finally:
            conn.close()
